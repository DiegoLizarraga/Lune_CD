import asyncio
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import requests


class AIProvider(ABC):
    """Clase base para proveedores de IA"""
    
    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "") -> str:
        """Enviar mensaje a la IA"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Verificar si el proveedor está disponible"""
        pass
    
    @abstractmethod
    def clear_history(self) -> None:
        """Limpiar historial de conversación"""
        pass


class GroqProvider(AIProvider):
    """Proveedor Groq"""
    
    def __init__(self, api_key: str, model: str = "mixtral-8x7b-32768"):
        self.api_key = api_key
        self.model = model
        self.conversation_history = []
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
    
    async def chat(self, message: str, system_prompt: str = "") -> str:
        """Enviar mensaje a Groq"""
        if not self.api_key or self.api_key == "COLOCA_TU_API_KEY_AQUI":
            return "❌ API Key de Groq no configurada. Edita config.json"
        
        if not message or not message.strip():
            return "❌ El mensaje está vacío"
        
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            messages = self.conversation_history.copy()
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2048
            }
            
            response = requests.post(
                self.base_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if "choices" not in result or len(result["choices"]) == 0:
                return "❌ Respuesta inválida de Groq"
            
            assistant_message = result["choices"][0]["message"]["content"]
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except requests.exceptions.Timeout:
            return "❌ Timeout: La solicitud tardó demasiado"
        except requests.exceptions.ConnectionError:
            return "❌ Error de conexión: No se pudo conectar a Groq"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                return "❌ Error 400: API Key inválida. Regenera en https://console.groq.com"
            elif e.response.status_code == 401:
                return "❌ Error 401: API Key expirada o inválida"
            elif e.response.status_code == 429:
                return "❌ Error 429: Rate limit excedido. Intenta más tarde"
            return f"❌ Error HTTP {e.response.status_code}"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Verificar disponibilidad"""
        return bool(self.api_key) and len(self.api_key) > 10 and self.api_key != "COLOCA_TU_API_KEY_AQUI"
    
    def clear_history(self) -> None:
        """Limpiar historial"""
        self.conversation_history = []


class AIManager:
    """Gestor central de IA"""
    
    def __init__(self, config):
        self.config = config
        self.providers = {}
        self._init_providers()
        self.current_provider = self.config.get("ai", "provider", default="groq")
    
    def _init_providers(self):
        """Inicializar proveedores"""
        try:
            groq_key = self.config.get("ai", "groq", "api_key", default="")
            groq_model = self.config.get("ai", "groq", "model", default="mixtral-8x7b-32768")
            self.providers["groq"] = GroqProvider(groq_key, groq_model)
        except Exception as e:
            print(f"Error inicializando proveedores: {e}")
    
    async def chat(self, message: str, system_prompt: str = "", provider: Optional[str] = None) -> str:
        """Enviar mensaje a la IA"""
        provider_name = provider or self.current_provider
        
        if provider_name not in self.providers:
            return f"❌ Proveedor '{provider_name}' no disponible"
        
        provider_obj = self.providers[provider_name]
        
        if not provider_obj.is_available():
            return "❌ API Key de Groq no configurada. Edita config.json con tu clave"
        
        return await provider_obj.chat(message, system_prompt)
    
    def switch_provider(self, provider: str) -> bool:
        """Cambiar proveedor"""
        if provider in self.providers and self.providers[provider].is_available():
            self.current_provider = provider
            self.config.set("ai", "provider", value=provider)
            return True
        return False
    
    def get_available_providers(self) -> list:
        """Obtener proveedores disponibles"""
        return [name for name, p in self.providers.items() if p.is_available()]
    
    def get_provider_status(self) -> Dict[str, bool]:
        """Obtener estado de todos los proveedores"""
        return {name: p.is_available() for name, p in self.providers.items()}
    
    def clear_history(self, provider: Optional[str] = None):
        """Limpiar historial"""
        if provider:
            if provider in self.providers:
                self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()