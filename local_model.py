import re

class LocalModel:
    """
    Un modelo de lenguaje local muy simple basado en reglas.
    Esta es una base sobre la cual se puede construir un modelo más complejo.
    """
    def __init__(self):
        self.responses = {
            "saludo": [
                "¡Hola! Soy Lune, ¿en qué puedo ayudarte?",
                "¡Qué tal! Estoy aquí para asistirte.",
                "Hola de nuevo. ¿Qué necesitas?"
            ],
            "identidad": [
                "Soy Lune CD, tu asistente virtual de escritorio.",
                "Me llamo Lune y estoy aquí para ayudarte con tus tareas.",
                "Soy una mascota virtual inteligente creada para ti."
            ],
            "estado": [
                "Estoy funcionando perfectamente, ¡gracias por preguntar!",
                "Como un programa, siempre estoy bien. ¿Y tú?",
                "Lista y esperando tus comandos."
            ],
            "ayuda": [
                "Puedes pedirme que abra aplicaciones, tome notas, te recuerde cosas o busque en internet.",
                "Intenta decirme 'abre el navegador' o 'toma nota de mi reunión'.",
                "Estoy aquí para ayudarte. ¡Solo pregunta!"
            ],
            "despedida": [
                "¡Hasta luego! Que tengas un buen día.",
                "Nos vemos pronto. Si necesitas algo, aquí estaré.",
                "Adiós. ¡Cuídate!"
            ]
        }

    def _detect_intent(self, message):
        """Detecta la intención del mensaje basándose en palabras clave."""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["hola", "buenos días", "buenas tardes", "qué tal", "ey"]):
            return "saludo"
        if any(word in message_lower for word in ["quién eres", "cómo te llamas", "tu nombre", "qué eres"]):
            return "identidad"
        if any(word in message_lower for word in ["cómo estás", "cómo te encuentras", "estás bien"]):
            return "estado"
        if any(word in message_lower for word in ["ayuda", "qué puedes hacer", "qué haces", "funciones"]):
            return "ayuda"
        if any(word in message_lower for word in ["adiós", "hasta luego", "chao", "nos vemos"]):
            return "despedida"
        
        return "desconocido"

    def generate_response(self, message):
        """Genera una respuesta basada en las reglas definidas."""
        intent = self._detect_intent(message)
        
        if intent in self.responses:
            import random
            return random.choice(self.responses[intent])
        
        # Respuesta por defecto para intenciones desconocidas
        return "Entiendo. Si necesitas buscar algo en internet, dime 'busca [tu consulta]'. Si quieres que haga algo específico, ¡intenta con mis comandos!"