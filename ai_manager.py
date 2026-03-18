import asyncio
import json
import requests
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional


class AIProvider(ABC):
    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def clear_history(self) -> None:
        pass


# ── Ollama ────────────────────────────────────────────────────────────────────

class OllamaProvider(AIProvider):
    def __init__(self, url: str = "http://localhost:11434", model: str = "nova"):
        self.url = url
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not message or not message.strip():
            return "❌ El mensaje está vacío"

        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        try:
            response = requests.post(
                f"{self.url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=60,
                stream=True,
            )
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("message", {}).get("content", "")
                    full_response += token
                    if on_token:
                        on_token(token)
                    if chunk.get("done"):
                        break

            self.conversation_history.append({"role": "assistant", "content": full_response})
            return full_response

        except requests.exceptions.Timeout:
            return "❌ Timeout: Ollama tardó demasiado"
        except requests.exceptions.ConnectionError:
            return "❌ No se pudo conectar a Ollama. Ejecuta: ollama serve"
        except requests.exceptions.HTTPError as e:
            return f"❌ Error HTTP {e.response.status_code}"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            return r.status_code == 200
        except:
            return False

    def clear_history(self):
        self.conversation_history = []


# ── DeepSeek ──────────────────────────────────────────────────────────────────

class DeepSeekProvider(AIProvider):
    BASE_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return "❌ API key de DeepSeek no configurada. Agrégala en api_keys.json"

        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        try:
            response = requests.post(
                self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "messages": messages, "stream": True},
                timeout=60,
                stream=True,
            )
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                full_response += token
                                if on_token:
                                    on_token(token)
                        except json.JSONDecodeError:
                            pass

            self.conversation_history.append({"role": "assistant", "content": full_response})
            return full_response

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return "❌ API key de DeepSeek inválida"
            return f"❌ Error HTTP {e.response.status_code}: {e.response.text}"
        except Exception as e:
            return f"❌ Error DeepSeek: {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def clear_history(self):
        self.conversation_history = []


# ── Claude (Anthropic) ────────────────────────────────────────────────────────

class ClaudeProvider(AIProvider):
    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return "❌ API key de Claude no configurada. Agrégala en api_keys.json"

        self.conversation_history.append({"role": "user", "content": message})

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": self.conversation_history.copy(),
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(
                self.BASE_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
                stream=True,
            )
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            if event.get("type") == "content_block_delta":
                                token = event.get("delta", {}).get("text", "")
                                if token:
                                    full_response += token
                                    if on_token:
                                        on_token(token)
                        except json.JSONDecodeError:
                            pass

            self.conversation_history.append({"role": "assistant", "content": full_response})
            return full_response

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return "❌ API key de Claude inválida"
            return f"❌ Error HTTP {e.response.status_code}"
        except Exception as e:
            return f"❌ Error Claude: {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def clear_history(self):
        self.conversation_history = []


# ── Character.AI ──────────────────────────────────────────────────────────────

class CharacterAIProvider(AIProvider):
    """
    Character.AI no ofrece una API oficial pública.
    Esta implementación usa PyCAI si está instalada, si no, informa al usuario.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key  # token de Character.AI
        self.conversation_history = []
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            # Intentar usar la librería PyCAI (pip install PyCAI)
            import PyCAI  # noqa: F401
            self._client = "pycai"
        except ImportError:
            self._client = None

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return (
                "❌ Token de Character.AI no configurado.\n"
                "Agrégalo en api_keys.json bajo 'character_ai' → 'api_key'.\n"
                "Puedes obtener tu token iniciando sesión en Character.AI y copiando "
                "el valor de la cookie '__Secure-next-auth.session-token'."
            )

        if self._client is None:
            return (
                "❌ PyCAI no está instalada.\n"
                "Ejecuta: pip install PyCAI\n\n"
                "Character.AI no tiene API oficial, se accede via PyCAI."
            )

        try:
            from PyCAI import PyAsyncCAI
            client = PyAsyncCAI(self.api_key)
            response = await client.chat.send_message(
                char="",
                message=message,
            )
            reply = response["replies"][0]["text"] if response.get("replies") else "Sin respuesta"
            if on_token:
                on_token(reply)
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            return f"❌ Error Character.AI: {str(e)}"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def clear_history(self):
        self.conversation_history = []


# ── Manager ───────────────────────────────────────────────────────────────────

class AIManager:
    PROVIDER_NAMES = {
        "character_ai": "Character.AI",
        "deepseek": "DeepSeek",
        "claude": "Claude",
        "ollama": "Ollama Local",
    }

    def __init__(self, config):
        self.config = config
        self.providers: Dict[str, AIProvider] = {}
        self.current_provider = "ollama"
        self._init_providers()

    def _init_providers(self):
        cfg = self.config

        # Ollama
        try:
            url = cfg.get_key("ollama", "url") or "http://localhost:11434"
            model = cfg.get_key("ollama", "model") or "nova"
            self.providers["ollama"] = OllamaProvider(url, model)
        except Exception as e:
            print(f"Error inicializando Ollama: {e}")

        # DeepSeek
        try:
            key = cfg.get_key("deepseek", "api_key")
            model = cfg.get_key("deepseek", "model") or "deepseek-chat"
            self.providers["deepseek"] = DeepSeekProvider(key, model)
        except Exception as e:
            print(f"Error inicializando DeepSeek: {e}")

        # Claude
        try:
            key = cfg.get_key("claude", "api_key")
            model = cfg.get_key("claude", "model") or "claude-3-5-haiku-20241022"
            self.providers["claude"] = ClaudeProvider(key, model)
        except Exception as e:
            print(f"Error inicializando Claude: {e}")

        # Character.AI
        try:
            key = cfg.get_key("character_ai", "api_key")
            self.providers["character_ai"] = CharacterAIProvider(key)
        except Exception as e:
            print(f"Error inicializando Character.AI: {e}")

    def reload_provider(self, provider_id: str):
        """Recargar un proveedor tras cambiar su API key."""
        cfg = self.config
        if provider_id == "ollama":
            url = cfg.get_key("ollama", "url") or "http://localhost:11434"
            model = cfg.get_key("ollama", "model") or "nova"
            self.providers["ollama"] = OllamaProvider(url, model)
        elif provider_id == "deepseek":
            key = cfg.get_key("deepseek", "api_key")
            model = cfg.get_key("deepseek", "model") or "deepseek-chat"
            self.providers["deepseek"] = DeepSeekProvider(key, model)
        elif provider_id == "claude":
            key = cfg.get_key("claude", "api_key")
            model = cfg.get_key("claude", "model") or "claude-3-5-haiku-20241022"
            self.providers["claude"] = ClaudeProvider(key, model)
        elif provider_id == "character_ai":
            key = cfg.get_key("character_ai", "api_key")
            self.providers["character_ai"] = CharacterAIProvider(key)

    async def chat(
        self,
        message: str,
        system_prompt: str = "",
        provider: Optional[str] = None,
        on_token: Callable = None,
    ) -> str:
        provider_name = provider or self.current_provider
        if provider_name not in self.providers:
            return f"❌ Proveedor '{provider_name}' no disponible"
        return await self.providers[provider_name].chat(message, system_prompt, on_token=on_token)

    def get_provider_status(self) -> Dict[str, bool]:
        return {name: p.is_available() for name, p in self.providers.items()}

    def clear_history(self, provider: Optional[str] = None):
        if provider and provider in self.providers:
            self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()