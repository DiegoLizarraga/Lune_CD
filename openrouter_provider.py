"""
openrouter_provider.py — Integración completa OpenRouter + Claude Code
Soporta modelos gratuitos y de pago en OpenRouter.

Documentación: https://openrouter.ai/docs/guides/coding-agents/claude-code-integration
API: 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

Modelos gratuitos recomendados:
  - openrouter/free (Free Models Router)
  - google/gemini-2.0-flash-lite-preview-02-05:free
  - nousresearch/nous-hermes-2-mixtral-8x7b-dpo:free
  - meta-llama/llama-3.1-70b-instruct:free
  - microsoft/phi-3.5-mini-instruct:free
"""

import asyncio
import json
import requests
from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class OpenRouterConfig:
    """Configuración de OpenRouter"""
    api_key: str
    model: str = "openrouter/free"  # Modelo por defecto: Free Models Router
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 4096
    temperature: float = 0.7
    enable_claude_code: bool = True  # Activar soporte para Claude Code
    custom_headers: Dict[str, str] = None

    def __post_init__(self):
        if self.custom_headers is None:
            self.custom_headers = {}


class OpenRouterProvider(ABC):
    """Clase base para proveedores OpenRouter"""
    
    def __init__(self, config: OpenRouterConfig):
        self.config = config
        self.conversation_history = []
        self._last_error = None
        self._request_count = 0

    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        pass

    def is_available(self) -> bool:
        return bool(self.config.api_key and self.config.api_key.strip())

    def clear_history(self) -> None:
        self.conversation_history = []

    def get_request_count(self) -> int:
        return self._request_count

    def get_last_error(self) -> Optional[str]:
        return self._last_error


class OpenRouterChatProvider(OpenRouterProvider):
    """
    Proveedor OpenRouter estándar para chat.
    Soporta cualquier modelo en el catálogo de OpenRouter.
    """

    async def chat(
        self,
        message: str,
        system_prompt: str = "",
        on_token: Callable = None,
    ) -> str:
        """
        Envía un mensaje a OpenRouter y retorna la respuesta.
        
        Args:
            message: Mensaje del usuario
            system_prompt: Prompt del sistema (contexto)
            on_token: Callback para tokens streaming (opcional)
        
        Returns:
            Respuesta del modelo
        """
        if not self.config.api_key:
            return "❌ OpenRouter API key no configurada. Agrégala en datos.json bajo 'apis' → 'openrouter_key'."

        if not message or not message.strip():
            return "❌ El mensaje está vacío"

        # Agregar mensaje a historial
        self.conversation_history.append({"role": "user", "content": message})

        # Preparar mensajes (incluir contexto anterior)
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        def _call():
            try:
                self._request_count += 1
                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://lunecd.local",
                    "X-Title": "Lune CD v7.0",
                    **self.config.custom_headers,
                }

                payload = {
                    "model": self.config.model,
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "stream": False,  # Non-streaming por compatibilidad
                }

                response = requests.post(
                    f"{self.config.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )

                response.raise_for_status()
                data = response.json()

                # Extraer respuesta
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    if on_token:
                        on_token(content)
                    self._last_error = None
                    return content
                else:
                    error_msg = "Respuesta vacía de OpenRouter"
                    self._last_error = error_msg
                    return f"❌ {error_msg}"

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code
                error_text = e.response.text if hasattr(e.response, 'text') else str(e)
                
                errors = {
                    401: "❌ OpenRouter API key inválida. Revisa tu clave en datos.json",
                    429: "❌ Límite de requests alcanzado. Espera un momento o usa un modelo de pago.",
                    500: "❌ Error en servidor de OpenRouter. Intenta más tarde.",
                    503: "❌ OpenRouter temporalmente no disponible.",
                }
                
                error_msg = errors.get(code, f"❌ Error HTTP {code}")
                self._last_error = error_msg
                
                if code == 429:
                    print(f"\n⚠️  {error_msg}")
                    print("   Modelos gratuitos tienen límite. Opciones:")
                    print("   1. Espera 24 horas")
                    print("   2. Usa un modelo diferente de openrouter/free")
                    print("   3. Agrega tu propia API key de un proveedor de pago")
                
                return error_msg

            except requests.exceptions.ConnectionError:
                error_msg = "❌ No hay conexión a OpenRouter. Revisa tu internet."
                self._last_error = error_msg
                return error_msg

            except requests.exceptions.Timeout:
                error_msg = "❌ OpenRouter tardó demasiado. Intenta de nuevo."
                self._last_error = error_msg
                return error_msg

            except json.JSONDecodeError as e:
                error_msg = f"❌ Respuesta JSON inválida de OpenRouter: {str(e)}"
                self._last_error = error_msg
                return error_msg

            except Exception as e:
                error_msg = f"❌ Error OpenRouter: {str(e)}"
                self._last_error = error_msg
                return error_msg

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        
        # Guardar en historial solo si no es error
        if not result.startswith("❌"):
            self.conversation_history.append({"role": "assistant", "content": result})
        
        return result


class OpenRouterClaudeCodeProvider(OpenRouterProvider):
    """
    Proveedor especializado OpenRouter + Claude Code.
    Permite ejecutar código directamente desde el chat.
    
    Integración con Claude Code CLI:
    https://openrouter.ai/docs/guides/coding-agents/claude-code-integration
    """

    async def chat(
        self,
        message: str,
        system_prompt: str = "",
        on_token: Callable = None,
    ) -> str:
        """
        Chat con soporte para Claude Code.
        El modelo detecta automáticamente cuándo ejecutar código.
        """
        if not self.config.api_key:
            return "❌ OpenRouter API key no configurada."

        # Agregar instrucción especial para Claude Code
        enhanced_system = system_prompt + "\n\n[SYSTEM: You have access to execute code through Claude Code. When appropriate, use code blocks or suggest code execution.]"
        
        return await OpenRouterChatProvider(self.config).chat(
            message=message,
            system_prompt=enhanced_system,
            on_token=on_token
        )


# Funciones de utilidad
async def test_connection(api_key: str, model: str = "openrouter/free") -> Dict[str, Any]:
    """
    Prueba la conexión a OpenRouter y devuelve información del modelo.
    
    Returns:
        {
            "success": bool,
            "model": str,
            "message": str,
            "status": str
        }
    """
    config = OpenRouterConfig(api_key=api_key, model=model)
    provider = OpenRouterChatProvider(config)

    try:
        result = await provider.chat(
            message="Di solo: OK",
            system_prompt="Responde con una palabra."
        )
        
        if result.startswith("❌"):
            return {
                "success": False,
                "model": model,
                "message": result,
                "status": "error"
            }
        
        return {
            "success": True,
            "model": model,
            "message": f"Conexión exitosa. Respuesta del modelo: {result}",
            "status": "ok"
        }
    
    except Exception as e:
        return {
            "success": False,
            "model": model,
            "message": f"Error de conexión: {str(e)}",
            "status": "error"
        }


def list_free_models() -> list:
    """
    Lista modelos gratuitos disponibles en OpenRouter.
    """
    return [
        {
            "id": "openrouter/free",
            "name": "Free Models Router",
            "description": "Automáticamente rota entre modelos gratuitos disponibles",
            "type": "free"
        },
        {
            "id": "google/gemini-2.0-flash-lite-preview-02-05:free",
            "name": "Google Gemini 2.0 Flash Lite",
            "description": "Modelo rápido y eficiente de Google",
            "type": "free"
        },
        {
            "id": "nousresearch/nous-hermes-2-mixtral-8x7b-dpo:free",
            "name": "Nous Hermes 2 Mixtral",
            "description": "Modelo de Nous Research optimizado",
            "type": "free"
        },
        {
            "id": "meta-llama/llama-3.1-70b-instruct:free",
            "name": "Meta Llama 3.1 70B",
            "description": "Gran modelo de Meta, muy capaz",
            "type": "free"
        },
        {
            "id": "microsoft/phi-3.5-mini-instruct:free",
            "name": "Microsoft Phi 3.5 Mini",
            "description": "Modelo compacto y rápido",
            "type": "free"
        },
    ]
