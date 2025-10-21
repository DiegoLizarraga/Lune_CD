"""
Enhanced Local Model usando Ollama y LangChain
Proporciona respuestas más inteligentes y contextuales
"""

import os
from datetime import datetime
from typing import List, Dict, Optional
import json

try:
    from langchain_community.llms import Ollama
    from langchain.memory import ConversationBufferWindowMemory
    from langchain.chains import ConversationChain
    from langchain.prompts import PromptTemplate
    from langchain.callbacks.manager import CallbackManager
    from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠️ Ollama/LangChain no disponibles. Instala con: pip install langchain langchain-community ollama-python")

import platform
import psutil


class EnhancedLocalModel:
    """
    Modelo local mejorado con Ollama y LangChain.
    Fallback al modelo basado en reglas si Ollama no está disponible.
    """
    
    def __init__(self, model_name: str = "llama3.2:3b", use_ollama: bool = True):
        """
        Inicializa el modelo
        
        Args:
            model_name: Nombre del modelo de Ollama (llama3.2:3b, mistral, phi3, etc.)
            use_ollama: Si True, intenta usar Ollama. Si False o no disponible, usa fallback
        """
        self.model_name = model_name
        self.use_ollama = use_ollama and OLLAMA_AVAILABLE
        self.conversation_chain = None
        self.memory = None
        
        # Información del sistema para contexto
        self.system_info = self._get_system_info()
        
        # Inicializar el modelo
        if self.use_ollama:
            self._initialize_ollama()
        else:
            self._initialize_fallback()
    
    def _initialize_ollama(self):
        """Inicializa Ollama con LangChain"""
        try:
            # Verificar si Ollama está corriendo
            import requests
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code != 200:
                    raise Exception("Ollama no responde")
            except:
                print("⚠️ Ollama no está corriendo. Inicia Ollama con: ollama serve")
                print("   Luego descarga un modelo: ollama pull llama3.2:3b")
                self.use_ollama = False
                self._initialize_fallback()
                return
            
            # Configurar LLM con streaming
            callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
            
            self.llm = Ollama(
                model=self.model_name,
                callback_manager=callback_manager,
                temperature=0.7,
                top_p=0.9,
            )
            
            # Configurar memoria conversacional (últimas 5 interacciones)
            self.memory = ConversationBufferWindowMemory(
                k=5,
                return_messages=True,
                memory_key="chat_history"
            )
            
            # Prompt template personalizado para Lune
            template = """Eres Lune, una asistente virtual de escritorio amigable y útil. Tu personalidad es:
- Amable, profesional y servicial
- Concisa pero informativa (respuestas de 2-4 oraciones máximo)
- Enfocada en ayudar con tareas de productividad
- Conocedora del sistema del usuario

Contexto del sistema:
- Sistema Operativo: {os_info}
- Fecha actual: {current_date}

IMPORTANTE: 
- Mantén respuestas breves y directas
- No uses emojis excesivamente
- Si no sabes algo, sé honesta
- Para búsquedas web, información técnica específica o comandos del sistema, indica que el usuario debe usar los comandos específicos de Lune

Historial de conversación:
{chat_history}

Usuario: {input}
Lune:"""

            prompt = PromptTemplate(
                input_variables=["chat_history", "input", "os_info", "current_date"],
                template=template
            )
            
            # Crear cadena de conversación
            self.conversation_chain = ConversationChain(
                llm=self.llm,
                memory=self.memory,
                prompt=prompt,
                verbose=False
            )
            
            print(f"✅ Modelo Ollama '{self.model_name}' inicializado correctamente")
            
        except Exception as e:
            print(f"⚠️ Error al inicializar Ollama: {str(e)}")
            print("   Cayendo al modelo basado en reglas...")
            self.use_ollama = False
            self._initialize_fallback()
    
    def _initialize_fallback(self):
        """Inicializa el modelo de respaldo basado en reglas"""
        from local_model import LocalModel
        self.fallback_model = LocalModel()
        print("✅ Modelo de respaldo (reglas) inicializado")
    
    def _get_system_info(self) -> str:
        """Obtiene información del sistema para contexto"""
        try:
            return f"{platform.system()} {platform.release()}"
        except:
            return "Sistema desconocido"
    
    def generate_response(self, message: str) -> str:
        """
        Genera una respuesta al mensaje del usuario
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Respuesta generada
        """
        if self.use_ollama and self.conversation_chain:
            return self._generate_with_ollama(message)
        else:
            return self._generate_with_fallback(message)
    
    def _generate_with_ollama(self, message: str) -> str:
        """Genera respuesta usando Ollama"""
        try:
            # Preparar variables adicionales para el prompt
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Generar respuesta
            response = self.conversation_chain.predict(
                input=message,
                os_info=self.system_info,
                current_date=current_date
            )
            
            # Limpiar respuesta (remover prefijos comunes)
            response = response.strip()
            if response.startswith("Lune:"):
                response = response[5:].strip()
            
            return response
            
        except Exception as e:
            print(f"⚠️ Error con Ollama: {str(e)}")
            print("   Usando modelo de respaldo...")
            self.use_ollama = False
            return self._generate_with_fallback(message)
    
    def _generate_with_fallback(self, message: str) -> str:
        """Genera respuesta usando el modelo de respaldo"""
        return self.fallback_model.generate_response(message)
    
    def clear_memory(self):
        """Limpia el historial de conversación"""
        if self.memory:
            self.memory.clear()
            return "Historial de conversación limpiado."
        return "Memoria limpiada."
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Obtiene el historial de conversación"""
        if self.memory:
            messages = self.memory.load_memory_variables({})
            return messages.get("chat_history", [])
        return []
    
    def switch_model(self, model_name: str) -> str:
        """
        Cambia el modelo de Ollama
        
        Args:
            model_name: Nombre del nuevo modelo
            
        Returns:
            Mensaje de confirmación
        """
        if not self.use_ollama:
            return "Ollama no está disponible. No se puede cambiar de modelo."
        
        try:
            self.model_name = model_name
            self._initialize_ollama()
            return f"Modelo cambiado a '{model_name}'"
        except Exception as e:
            return f"Error al cambiar modelo: {str(e)}"
    
    def get_available_models(self) -> List[str]:
        """Obtiene lista de modelos disponibles en Ollama"""
        if not self.use_ollama:
            return []
        
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except:
            return []


# Modelos recomendados para diferentes casos de uso
RECOMMENDED_MODELS = {
    "rapido": "llama3.2:3b",      # Más rápido, menos preciso (3GB RAM)
    "balanceado": "llama3.2:7b",  # Balance entre velocidad y calidad (7GB RAM)
    "preciso": "llama3.1:8b",     # Más preciso, más lento (8GB RAM)
    "ligero": "phi3:mini",        # Muy ligero para PCs con pocos recursos (2GB RAM)
    "espanol": "nous-hermes2",    # Mejor para español
}


def get_recommended_model() -> str:
    """Recomienda un modelo basado en los recursos del sistema"""
    try:
        ram_gb = psutil.virtual_memory().total / (1024**3)
        
        if ram_gb < 6:
            return RECOMMENDED_MODELS["ligero"]
        elif ram_gb < 10:
            return RECOMMENDED_MODELS["rapido"]
        elif ram_gb < 16:
            return RECOMMENDED_MODELS["balanceado"]
        else:
            return RECOMMENDED_MODELS["preciso"]
    except:
        return RECOMMENDED_MODELS["rapido"]


if __name__ == "__main__":
    # Test del modelo
    print("🧪 Probando Enhanced Local Model...")
    
    # Obtener modelo recomendado
    recommended = get_recommended_model()
    print(f"Modelo recomendado para tu sistema: {recommended}")
    
    # Inicializar modelo
    model = EnhancedLocalModel(model_name=recommended)
    
    # Probar algunas interacciones
    test_messages = [
        "Hola, ¿cómo estás?",
        "¿Qué puedes hacer por mí?",
        "Cuéntame sobre ti"
    ]
    
    print("\n--- Probando conversaciones ---")
    for msg in test_messages:
        print(f"\nUsuario: {msg}")
        response = model.generate_response(msg)
        print(f"Lune: {response}")
    
    # Mostrar historial
    print("\n--- Historial ---")
    history = model.get_conversation_history()
    print(f"Mensajes en memoria: {len(history)}")