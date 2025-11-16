"""
Gestor de IA que maneja Groq y Ollama
"""

from src.ai.groq_handler import GroqHandler
from src.ai.ollama_handler import OllamaHandler

class AIManager:
    """Administrador de proveedores de IA"""
    
    def __init__(self, config):
        self.config = config
        self.current_provider = config.get("ai_provider", "groq")
        
        # Inicializar handlers
        self.groq = GroqHandler(config.get("groq_api_key"))
        self.ollama = OllamaHandler(config.get("ollama_url", "http://localhost:11434"))
        
    def get_response(self, message):
        """Obtener respuesta de la IA"""
        try:
            if self.current_provider == "groq":
                return self.groq.chat(message)
            elif self.current_provider == "ollama":
                return self.ollama.chat(message)
            else:
                return "❌ Proveedor de IA no configurado"
        except Exception as e:
            return f"❌ Error: {str(e)}"
            
    def switch_provider(self, provider):
        """Cambiar proveedor de IA"""
        if provider in ["groq", "ollama"]:
            self.current_provider = provider
            self.config.set("ai_provider", provider)
            return True
        return False