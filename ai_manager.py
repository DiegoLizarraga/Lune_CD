import asyncio
from typing import Optional, Dict, Callable
from abc import ABC, abstractmethod
import requests
import json


class AIProvider(ABC):
    """Clase base para proveedores de IA"""
    
    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        pass
    
    @abstractmethod
    def clear_history(self) -> None:
        pass


class OllamaProvider(AIProvider):
    """Proveedor Ollama con streaming"""
    
    def __init__(self, url: str = "http://localhost:11434", model: str = "nova"):
        self.url = url
        self.model = model
        self.conversation_history = []
    
    async def chat(self, message: str, system_prompt: str = "", on_token: Callable = None) -> str:
        if not message or not message.strip():
            return "❌ El mensaje está vacío"
        
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        messages = self.conversation_history.copy()
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        
        try:
            response = requests.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True
                },
                timeout=60,
                stream=True
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
            
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })
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
    
    def clear_history(self) -> None:
        self.conversation_history = []


class AIManager:
    """Gestor central de IA"""
    
    def __init__(self, config):
        self.config = config
        self.providers = {}
        self._init_providers()
        self.current_provider = "ollama"
    
    def _init_providers(self):
        try:
            ollama_url = self.config.get("ai", "ollama", "url", default="http://localhost:11434")
            ollama_model = self.config.get("ai", "ollama", "model", default="nova")
            self.providers["ollama"] = OllamaProvider(ollama_url, ollama_model)
        except Exception as e:
            print(f"Error inicializando Ollama: {e}")
    
    async def chat(self, message: str, system_prompt: str = "", provider: Optional[str] = None, on_token: Callable = None) -> str:
        provider_name = provider or self.current_provider
        
        if provider_name not in self.providers:
            return f"❌ Proveedor '{provider_name}' no disponible"
        
        provider_obj = self.providers[provider_name]
        
        if not provider_obj.is_available():
            return "❌ Ollama no está disponible. Ejecuta: ollama serve"
        
        return await provider_obj.chat(message, system_prompt, on_token=on_token)
    
    def get_available_providers(self) -> list:
        return [name for name, p in self.providers.items() if p.is_available()]
    
    def get_provider_status(self) -> Dict[str, bool]:
        return {name: p.is_available() for name, p in self.providers.items()}
    
    def clear_history(self, provider: Optional[str] = None):
        if provider:
            if provider in self.providers:
                self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()