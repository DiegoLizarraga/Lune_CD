import asyncio
import json
import requests
from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional
import datos

class AIProvider(ABC):
    def __init__(self):
        self.cancel_flag = False

    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str: pass
    @abstractmethod
    def is_available(self) -> bool: pass
    @abstractmethod
    def clear_history(self) -> None: pass

# ── Ollama (Local / Offline) ──────────────────────────────────────────────────
class OllamaProvider(AIProvider):
    def __init__(self, url: str, model: str):
        super().__init__()
        self.url = url
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not message or not message.strip(): return "❌ El mensaje está vacío"
        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt: messages.insert(0, {"role": "system", "content": system_prompt})

        def _call():
            try:
                response = requests.post(f"{self.url}/api/chat", json={"model": self.model, "messages": messages, "stream": True}, timeout=120, stream=True)
                response.raise_for_status()
                full_response = ""
                for line in response.iter_lines():
                    if self.cancel_flag: break 
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("message", {}).get("content", "")
                        full_response += token
                        if on_token: on_token(token)
                        if chunk.get("done"): break
                return full_response
            except Exception as e: return f"❌ Error Ollama: {str(e)}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        if not result.startswith("❌") and not self.cancel_flag:
            self.conversation_history.append({"role": "assistant", "content": result})
        return result

    def is_available(self) -> bool:
        try: return requests.get(f"{self.url}/api/tags", timeout=3).status_code == 200
        except: return False

    def clear_history(self): self.conversation_history = []

# ── OpenRouter (Nube / Automático) ────────────────────────────────────────────
class OpenRouterProvider(AIProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.conversation_history = []

    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not self.api_key: return "❌ API key de OpenRouter no configurada."
        self.conversation_history.append({"role": "user", "content": message})
        messages = self.conversation_history.copy()
        if system_prompt: messages.insert(0, {"role": "system", "content": system_prompt})

        def _call():
            try:
                response = requests.post(self.BASE_URL, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://lunecd.local", "X-Title": "Lune CD"}, json={"model": self.model, "messages": messages, "stream": True}, timeout=60, stream=True)
                response.raise_for_status()
                full_response = ""
                for line in response.iter_lines():
                    if self.cancel_flag: break 
                    if line:
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            data_str = decoded[6:]
                            if data_str.strip() == "[DONE]": break
                            try:
                                chunk = json.loads(data_str)
                                if "choices" in chunk and len(chunk["choices"]) > 0:
                                    token = chunk["choices"][0].get("delta", {}).get("content", "")
                                    if token:
                                        full_response += token
                                        if on_token: on_token(token)
                            except json.JSONDecodeError: pass
                return full_response
            except Exception as e: return f"❌ Error OpenRouter: {str(e)}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _call)
        if not result.startswith("❌") and not self.cancel_flag:
            self.conversation_history.append({"role": "assistant", "content": result})
        return result

    def is_available(self) -> bool: return bool(self.api_key and self.api_key.strip())
    def clear_history(self): self.conversation_history = []

# ── Manager ───────────────────────────────────────────────────────────────────
class AIManager:
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
        self._init_providers()

    def _init_providers(self):
        try: self.providers["ollama"] = OllamaProvider(datos.ollama_url(), datos.ollama_model())
        except Exception as e: print(f"Error Ollama: {e}")
        try: self.providers["openrouter"] = OpenRouterProvider(datos.openrouter_key(), datos.openrouter_model())
        except Exception as e: print(f"Error OpenRouter: {e}")

    def reload_provider(self, provider_id: str = None):
        self._init_providers()

    async def chat(self, message: str, system_prompt: str = "", provider: Optional[str] = "openrouter", on_token: Callable = None) -> str:
        if provider not in self.providers: return f"❌ Proveedor '{provider}' no disponible"
        return await self.providers[provider].chat(message, system_prompt, on_token=on_token)

    def clear_history(self, provider: Optional[str] = None):
        if provider and provider in self.providers: self.providers[provider].clear_history()
        else:
            for p in self.providers.values(): p.clear_history()