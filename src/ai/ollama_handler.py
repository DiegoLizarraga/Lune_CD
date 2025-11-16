"""
Handler para Ollama local
"""

import httpx

class OllamaHandler:
    """Manejador de Ollama local"""
    
    def __init__(self, base_url):
        self.base_url = base_url
        self.model = "llama2"
        self.conversation_history = []
        
    def chat(self, message):
        """Enviar mensaje a Ollama"""
        # Agregar mensaje al historial
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Eres Lune, una asistente virtual amigable."
                            },
                            *self.conversation_history
                        ],
                        "stream": False
                    }
                )
                
                response.raise_for_status()
                result = response.json()
                assistant_message = result["message"]["content"]
                
                # Agregar respuesta al historial
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                
                return assistant_message
                
        except httpx.ConnectError:
            return "❌ No se puede conectar a Ollama. ¿Está corriendo?"
        except Exception as e:
            return f"❌ Error con Ollama: {str(e)}"
            
    def clear_history(self):
        """Limpiar historial"""
        self.conversation_history = []