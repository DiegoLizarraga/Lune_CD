"""
ai_manager.py — Motor híbrido de Lune CD: nube (OpenRouter) y local (Ollama).

Cada proveedor mantiene su propio historial y su propia sesión HTTP. Lo de la
sesión por proveedor no es cosmético: `requests.Session` no es thread-safe y
aquí las llamadas salen desde un executor, así que compartir una sola sesión
entre proveedores era una carrera esperando a ocurrir.

El historial se recorta a `datos.max_historial()` turnos. Sin eso crecía sin
límite y con modelos locales acababa desbordando la ventana de contexto.

Visión: las imágenes se adjuntan SOLO al mensaje que se está enviando; en el
historial queda la versión de texto. Guardar el base64 turno tras turno haría
crecer el contexto sin parar y reenviaría la misma imagen en cada mensaje.
"""
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

import requests

from nucleo import datos


_USER_AGENT = "LuneCD/8.5"


def _nueva_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _USER_AGENT})
    return s


class AIProvider(ABC):
    ERROR = "Error:"

    def __init__(self):
        self.cancel_flag = False
        self.conversation_history: List[dict] = []
        self.ultimo_uso: Dict = {}
        self._session = _nueva_sesion()

    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None) -> str: ...
    @abstractmethod
    def is_available(self) -> bool: ...

    def clear_history(self) -> None:
        self.conversation_history = []
        self.ultimo_uso = {}

    def cargar_historial(self, mensajes: List[dict]):
        """Reinyecta una conversación guardada para poder retomarla."""
        self.conversation_history = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in mensajes if m.get("content")
        ]
        self._recortar_historial()

    # ── Historial ─────────────────────────────────────────────────────────────
    def _recortar_historial(self):
        """
        Conserva los últimos N turnos (user + assistant). Recorta desde el
        principio, que es lo más viejo y menos relevante.
        """
        limite = max(1, datos.max_historial()) * 2
        if len(self.conversation_history) > limite:
            self.conversation_history = self.conversation_history[-limite:]

    def _mensajes_para_envio(self, message: str, system_prompt: str) -> List[dict]:
        self.conversation_history.append({"role": "user", "content": message})
        self._recortar_historial()
        mensajes = list(self.conversation_history)
        if system_prompt:
            mensajes.insert(0, {"role": "system", "content": system_prompt})
        return mensajes

    def _registrar_respuesta(self, texto: str):
        if texto and not texto.startswith(self.ERROR) and not self.cancel_flag:
            self.conversation_history.append({"role": "assistant", "content": texto})
            self._recortar_historial()


# ── Ollama (Local / Offline) ──────────────────────────────────────────────────
class OllamaProvider(AIProvider):
    ERROR = "Error Ollama:"

    def __init__(self, url: str, model: str):
        super().__init__()
        self.url = url
        self.model = model

    def configurar(self, url: str, model: str):
        self.url, self.model = url, model

    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None) -> str:
        if not message or not message.strip():
            return "El mensaje está vacío"
        if not self.model:
            return (f"{self.ERROR} no hay ningún modelo local seleccionado. "
                    "Ve a Configuración → Red Neuronal · Local y pulsa «Buscar modelos».")

        messages = self._mensajes_para_envio(message, system_prompt)
        if imagenes:
            # Ollama espera las imágenes en el propio mensaje, en base64 plano.
            messages[-1] = {**messages[-1], "images": imagenes}

        timeout = datos.ollama_timeout()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            # keep_alive evita que Ollama descargue el modelo de VRAM entre
            # mensajes; sin esto se paga la recarga completa cada pocos minutos.
            "keep_alive": datos.ollama_keep_alive(),
            "options": {
                "num_ctx": datos.ollama_num_ctx(),
                "temperature": datos.temperatura(),
            },
        }
        self.ultimo_uso = {}

        def _call():
            try:
                response = self._session.post(
                    f"{self.url}/api/chat", json=payload, timeout=timeout, stream=True
                )
                response.raise_for_status()
                full_response = ""
                for line in response.iter_lines():
                    if self.cancel_flag:
                        break
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        return f"{self.ERROR} {chunk['error']}"
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        full_response += token
                        if on_token:
                            on_token(token)
                    if chunk.get("done"):
                        self.ultimo_uso = self._uso_desde(chunk)
                        break
                return full_response
            except requests.exceptions.ConnectionError:
                return (f"{self.ERROR} no pude conectar con {self.url}. "
                        "¿Está corriendo «ollama serve»?")
            except requests.exceptions.Timeout:
                return (f"{self.ERROR} el modelo no respondió en {timeout}s. "
                        "Si es grande y arranca en frío, sube el timeout en Configuración.")
            except Exception as e:
                return f"{self.ERROR} {e}"

        result = await asyncio.get_event_loop().run_in_executor(None, _call)
        self._registrar_respuesta(result)
        return result

    @staticmethod
    def _uso_desde(chunk: dict) -> dict:
        entrada = chunk.get("prompt_eval_count", 0) or 0
        salida = chunk.get("eval_count", 0) or 0
        # eval_duration viene en nanosegundos
        dur = (chunk.get("eval_duration") or 0) / 1e9
        return {
            "entrada": entrada,
            "salida": salida,
            "total": entrada + salida,
            "tokens_por_segundo": round(salida / dur, 1) if dur > 0 else None,
            "costo": 0.0,     # local = gratis
            "local": True,
        }

    def is_available(self) -> bool:
        try:
            return self._session.get(f"{self.url}/api/tags", timeout=3).status_code == 200
        except Exception:
            return False


# ── OpenRouter (Nube / Automático) ────────────────────────────────────────────
class OpenRouterProvider(AIProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    ERROR = "Error OpenRouter:"

    def __init__(self, api_key: str, model: str):
        super().__init__()
        self.api_key = api_key
        self.model = model

    def configurar(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None) -> str:
        if not self.api_key:
            return "API key de OpenRouter no configurada."

        messages = self._mensajes_para_envio(message, system_prompt)
        if imagenes:
            # OpenRouter usa el formato de contenido por partes de OpenAI.
            partes = [{"type": "text", "text": message}]
            for img in imagenes:
                partes.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img}"},
                })
            messages[-1] = {"role": "user", "content": partes}

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": datos.temperatura(),
            "max_tokens": datos.max_tokens(),
            # Pide que el chunk final traiga tokens y costo real.
            "usage": {"include": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lunecd.local",
            "X-Title": "Lune CD",
        }
        self.ultimo_uso = {}

        def _call():
            try:
                response = self._session.post(
                    self.BASE_URL, headers=headers, json=payload, timeout=60, stream=True
                )
                response.raise_for_status()
                full_response = ""
                for line in response.iter_lines():
                    if self.cancel_flag:
                        break
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    data_str = decoded[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        self.ultimo_uso = self._uso_desde(chunk["usage"])
                    opciones = chunk.get("choices") or []
                    if not opciones:
                        continue
                    token = opciones[0].get("delta", {}).get("content", "")
                    if token:
                        full_response += token
                        if on_token:
                            on_token(token)
                return full_response
            except requests.exceptions.HTTPError as e:
                codigo = e.response.status_code if e.response is not None else "?"
                if codigo == 401:
                    return f"{self.ERROR} API key inválida o revocada."
                if codigo == 402:
                    return f"{self.ERROR} sin créditos en tu cuenta de OpenRouter."
                if codigo == 429:
                    return f"{self.ERROR} demasiadas peticiones, espera un momento."
                return f"{self.ERROR} HTTP {codigo}."
            except requests.exceptions.ConnectionError:
                return f"{self.ERROR} sin conexión a internet."
            except Exception as e:
                return f"{self.ERROR} {e}"

        result = await asyncio.get_event_loop().run_in_executor(None, _call)
        self._registrar_respuesta(result)
        return result

    @staticmethod
    def _uso_desde(uso: dict) -> dict:
        entrada = uso.get("prompt_tokens", 0) or 0
        salida = uso.get("completion_tokens", 0) or 0
        return {
            "entrada": entrada,
            "salida": salida,
            "total": uso.get("total_tokens", entrada + salida),
            "tokens_por_segundo": None,
            "costo": float(uso.get("cost", 0) or 0),
            "local": False,
        }

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


# ── Manager ───────────────────────────────────────────────────────────────────
class AIManager:
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {
            "ollama": OllamaProvider(datos.ollama_url(), datos.ollama_model()),
            "openrouter": OpenRouterProvider(datos.openrouter_key(), datos.openrouter_model()),
        }

    def reload_provider(self, provider_id: str = None):
        """
        Reaplica la configuración sin recrear los proveedores, para que un
        cambio de ajustes no borre la conversación en curso.
        """
        self.providers["ollama"].configurar(datos.ollama_url(), datos.ollama_model())
        self.providers["openrouter"].configurar(datos.openrouter_key(), datos.openrouter_model())

    async def chat(self, message: str, system_prompt: str = "",
                   provider: Optional[str] = "openrouter", on_token: Callable = None,
                   imagenes: Optional[List[str]] = None) -> str:
        if provider not in self.providers:
            return f"Proveedor '{provider}' no disponible"
        return await self.providers[provider].chat(
            message, system_prompt, on_token=on_token, imagenes=imagenes
        )

    def uso(self, provider: str) -> dict:
        p = self.providers.get(provider)
        return p.ultimo_uso if p else {}

    def clear_history(self, provider: Optional[str] = None):
        if provider and provider in self.providers:
            self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()

    def cargar_historial(self, mensajes: List[dict]):
        for p in self.providers.values():
            p.cargar_historial(mensajes)
