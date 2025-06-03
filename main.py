import requests
import json
import re
import math
from datetime import datetime
import sys

class GroqChatBot:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions" 
        self.conversation_history = []
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def search_web(self, query):
        try:
            # Aquí puedes integrar con APIs como Google Custom Search, Bing, etc.
            # Por ahora retorna un mensaje indicativo
            return f"Busqueda web para '{query}': Funcion de busqueda disponible para integrar con APIs externas."
        except Exception as e:
            return f"Error en búsqueda web: {str(e)}"
    
    def solve_math(self, expression):
        """Resuelve expresiones matematicas básicas"""
        try:
            # Limpia la expresión matemática
            clean_expr = re.sub(r'[^0-9+\-*/().\s]', '', expression)
            # Evalúa expresiones matemáticas seguras
            allowed_names = {
                k: v for k, v in math.__dict__.items() 
                if not k.startswith("__")
            }
            allowed_names.update({"abs": abs, "round": round})
            
            result = eval(clean_expr, {"__builtins__": {}}, allowed_names)
            return f"Resultado: {result}"
        except Exception as e:
            return f"No puede chavo: {str(e)}"
    
    def detect_intent(self, message):
        """Detecta la intención del mensaje"""
        message_lower = message.lower()
        
        # Detecta búsqueda web
        web_keywords = ['buscar', 'busca', 'search', 'google', 'web', 'internet', 'información sobre']
        if any(keyword in message_lower for keyword in web_keywords):
            return 'web_search'
        
        # Detecta matemáticas
        math_keywords = ['calcular', 'resolver', 'matemática', 'suma', 'resta', 'multiplicar', 'dividir']
        if any(keyword in message_lower for keyword in math_keywords) or re.search(r'[\d+\-*/()]', message):
            return 'math'
        
        return 'conversation'
    
    def call_groq_api(self, messages):
        """Llama a la API de Groq"""
        try:
            payload = {
                "model": "llama3-8b-8192",  #uso del groq gratis
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7,
                "stream": False
            }
            
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"Error de API: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error de conexión: {str(e)}"
    
    def process_message(self, user_message):
        """Procesa el mensaje del usuario"""
        intent = self.detect_intent(user_message)
        
        # Añade mensaje del usuario al historial
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        if intent == 'web_search':
            # Extrae términos de busqueda
            search_terms = user_message.lower()
            for keyword in ['buscar', 'busca', 'search', 'información sobre']:
                search_terms = search_terms.replace(keyword, '').strip()
            
            web_result = self.search_web(search_terms)
            
            # Envía resultado a DeepSeek si se necesita
            enhanced_message = f"Usuario pregunta: {user_message}\nInformación encontrada: {web_result}\nPor favor, proporciona una respuesta útil basada en esta información."
            
            messages = self.conversation_history[:-1] + [{
                "role": "user",
                "content": enhanced_message
            }]
            
        elif intent == 'math':
            # Intenta resolver matemáticas
            math_result = self.solve_math(user_message)
            
            # Envía a DeepSeek para explicación adicional
            enhanced_message = f"Usuario solicita: {user_message}\n{math_result}\nPuedes explicar o ampliar esta respuesta matemática?"
            
            messages = self.conversation_history[:-1] + [{
                "role": "user", 
                "content": enhanced_message
            }]
            
        else:
            # Conversación normal
            messages = self.conversation_history
        
        # Obtiene respuesta de Groq
        response = self.call_groq_api(messages)
        
        # Añade respuesta al historial
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        return response
    
    def chat_loop(self):
        """Bucle principal del chat"""
        print("hola soy un chatbot Lune_CD")
        print("'salir' para terminar la conversacion\n")
        
        while True:
            try:
                user_input = input("Tú: ").strip()
                
                if user_input.lower() in ['salir', 'exit', 'quit']:
                    print("Saliendo del chat...")
                    break
                
                if not user_input:
                    continue
                
                print("Ta pensando...")
                response = self.process_message(user_input)
                print(f"Bot: {response}\n")
                
            except KeyboardInterrupt:
                print("\nSaliendo del chat...")
                break
            except Exception as e:
                print(f"Error: {str(e)}\n")

def main():
    # Configuración
    print("=== Chatbot con Lune_CD ===")
    print("consigue la key para conversar https://console.groq.com/keys\n")
    
    api_key = input("Ingresa API key: ").strip()
    
    if not api_key:
        print("Necesitas una API key para usar el chatbot de Lune_CD")
        return
    
    # Inicializa y ejecuta el chatbot
    bot = GroqChatBot(api_key)
    bot.chat_loop()

if __name__ == "__main__":
    main()