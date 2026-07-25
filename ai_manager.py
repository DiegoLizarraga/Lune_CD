"""
ai_manager.py — Motor híbrido de Lune CD: nube (OpenRouter) y local (Ollama).

Cada proveedor mantiene su propio historial y su propia sesión HTTP. Lo de la
sesión por proveedor no es cosmético: `requests.Session` no es thread-safe y
aquí las llamadas salen desde un executor, así que compartir una sola sesión
entre proveedores era una carrera esperando a ocurrir.

El historial se recorta a `datos.max_historial()` turnos. Sin eso crecía sin
límite y con modelos locales acababa desbordando la ventana de contexto.
"""
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

import requests

import datos

_USER_AGENT = "LuneCD/8.4"


def _nueva_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _USER_AGENT})
    return s


class AIProvider(ABC):
    def __init__(self):
        self.cancel_flag = False
        self.conversation_history: List[dict] = []
        self._session = _nueva_sesion()

    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str: ...
    @abstractmethod
    def is_available(self) -> bool: ...

    def clear_history(self) -> None:
        self.conversation_history = []

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

    def _registrar_respuesta(self, texto: str, prefijo_error: str):
        if texto and not texto.startswith(prefijo_error) and not self.cancel_flag:
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

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not message or not message.strip():
            return "El mensaje está vacío"
        if not self.model:
            return (f"{self.ERROR} no hay ningún modelo local seleccionado. "
                    "Ve a Configuración → Red Neuronal · Local y pulsa «Buscar modelos».")

        messages = self._mensajes_para_envio(message, system_prompt)
        # Se leen en el hilo llamante para no tocar datos.py desde el executor.
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
        self._registrar_respuesta(result, self.ERROR)
        return result

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

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return "API key de OpenRouter no configurada."

        messages = self._mensajes_para_envio(message, system_prompt)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": datos.temperatura(),
            "max_tokens": datos.max_tokens(),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lunecd.local",
            "X-Title": "Lune CD",
        }

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
        self._registrar_respuesta(result, self.ERROR)
        return result

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
                   provider: Optional[str] = "openrouter", on_token: Callable = None) -> str:
        if provider not in self.providers:
            return f"Proveedor '{provider}' no disponible"
        return await self.providers[provider].chat(message, system_prompt, on_token=on_token)

    def clear_history(self, provider: Optional[str] = None):
        if provider and provider in self.providers:
            self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()
