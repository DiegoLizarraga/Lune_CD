"""
Handler para Groq API
"""

import requests

class GroqHandler:
    """Manejador de Groq API"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        self.conversation_history = []
        
    def chat(self, message):
        """Enviar mensaje a Groq"""
        if not self.api_key:
            return "⚠️ API Key de Groq no configurada"
            
        # Agregar mensaje al historial
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # Preparar request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Eres Lune, una asistente virtual amigable, inteligente y útil. Respondes de forma concisa pero completa."
                },
                *self.conversation_history
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }
        
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            assistant_message = result["choices"][0]["message"]["content"]
            
            # Agregar respuesta al historial
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except requests.exceptions.RequestException as e:
            return f"❌ Error de conexión con Groq: {str(e)}"
        except Exception as e:
            return f"❌ Error inesperado: {str(e)}"
            
    def clear_history(self):
        """Limpiar historial de conversación"""
        self.conversation_history = []