import datos
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

        def _call():
            try:
                response = requests.post(
                    f"{self.url}/api/chat",
                    json={"model": self.model, "messages": messages, "stream": True},
                    timeout=120,
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
                return full_response
            except requests.exceptions.Timeout:
                return "❌ Timeout: Ollama tardó demasiado"
            except requests.exceptions.ConnectionError:
                return "❌ No se pudo conectar a Ollama. Ejecuta: ollama serve"
            except Exception as e:
                return f"❌ Error Ollama: {str(e)}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        if not result.startswith("❌"):
            self.conversation_history.append({"role": "assistant", "content": result})
        return result

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
            return "❌ API key de DeepSeek no configurada."

        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        def _call():
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
                return full_response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    return "❌ API key de DeepSeek inválida"
                return f"❌ Error HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                return f"❌ Error DeepSeek: {str(e)}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        if not result.startswith("❌"):
            self.conversation_history.append({"role": "assistant", "content": result})
        return result

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def clear_history(self):
        self.conversation_history = []


# ── Z.ai GLM-4.5 Air via OpenRouter ──────────────────────────────────────────

class ZaiProvider(AIProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "z-ai/glm-4.5-air:free"):
        self.api_key = api_key
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return "❌ OpenRouter API key no configurada. Agrégala en api_keys.json bajo 'claude' → 'api_key'."

        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        def _call():
            try:
                response = requests.post(
                    self.BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://lunecd.local",
                        "X-Title": "Lune CD",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": 1024,
                        "stream": False,
                    },
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code
                if code == 401:
                    return "❌ OpenRouter API key inválida"
                if code == 429:
                    return "❌ Límite de requests alcanzado. Espera un momento."
                return f"❌ Error HTTP {code}: {e.response.text}"
            except Exception as e:
                return f"❌ Error Z.ai: {str(e)}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        if not result.startswith("❌"):
            if on_token:
                on_token(result)
            self.conversation_history.append({"role": "assistant", "content": result})
        return result

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def clear_history(self):
        self.conversation_history = []


# ── Character.AI ──────────────────────────────────────────────────────────────

class CharacterAIProvider(AIProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.conversation_history = []
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            import PyCAI  # noqa: F401
            self._client = "pycai"
        except ImportError:
            self._client = None

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key:
            return (
                "❌ Token de Character.AI no configurado.\n"
                "Agrégalo en api_keys.json bajo 'character_ai' → 'api_key'."
            )
        if self._client is None:
            return "❌ PyCAI no instalada.\nEjecuta: pip install PyCAI"

        try:
            from PyCAI import PyAsyncCAI
            client = PyAsyncCAI(self.api_key)
            response = await client.chat.send_message(char="", message=message)
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
        "deepseek":     "DeepSeek",
        "claude":       "Z.ai GLM",
        "ollama":       "Ollama Local",
    }

    def __init__(self, config=None):
        self.providers: Dict[str, AIProvider] = {}
        self.current_provider = "ollama"
        self._init_providers()

    def _init_providers(self):
        # Ollama
        try:
            self.providers["ollama"] = OllamaProvider(
                datos.ollama_url(), datos.ollama_model()
            )
        except Exception as e:
            print(f"Error inicializando Ollama: {e}")

        # DeepSeek
        try:
            self.providers["deepseek"] = DeepSeekProvider(
                datos.deepseek_key(), datos.deepseek_model()
            )
        except Exception as e:
            print(f"Error inicializando DeepSeek: {e}")

        # Z.ai via OpenRouter
        try:
            self.providers["claude"] = ZaiProvider(
                datos.openrouter_key(), datos.openrouter_model()
            )
        except Exception as e:
            print(f"Error inicializando Z.ai: {e}")

        # Character.AI
        try:
            self.providers["character_ai"] = CharacterAIProvider(
                datos.character_ai_key()
            )
        except Exception as e:
            print(f"Error inicializando Character.AI: {e}")

    def reload_provider(self, provider_id: str):
        if provider_id == "ollama":
            self.providers["ollama"] = OllamaProvider(
                datos.ollama_url(), datos.ollama_model()
            )
        elif provider_id == "deepseek":
            self.providers["deepseek"] = DeepSeekProvider(
                datos.deepseek_key(), datos.deepseek_model()
            )
        elif provider_id == "claude":
            self.providers["claude"] = ZaiProvider(
                datos.openrouter_key(), datos.openrouter_model()
            )
        elif provider_id == "character_ai":
            self.providers["character_ai"] = CharacterAIProvider(
                datos.character_ai_key()
            )

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