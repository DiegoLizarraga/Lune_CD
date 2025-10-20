import re
import random
import platform
import psutil

class LocalModel:
    """
    Un modelo de lenguaje local mejorado basado en reglas.
    Proporciona respuestas más útiles y específicas sobre el sistema y comandos.
    """
    def __init__(self):
        self.responses = {
            "saludo": [
                "¡Hola! Soy Lune, tu asistente virtual de escritorio. ¿En qué puedo ayudarte hoy?",
                "¡Qué tal! Estoy aquí para asistirte. Puedes preguntarme 'qué puedes hacer' para ver mis capacidades.",
                "Hola de nuevo. ¿Qué necesitas? Recuerda que puedes usar Ctrl+T para mostrarme u ocultarme.",
                "¡Hola! Si es tu primera vez usándome, prueba con 'ayuda' para ver todos los comandos disponibles."
            ],
            "identidad": [
                "Soy Lune CD, tu asistente virtual de escritorio. Estoy diseñada para ayudarte con tareas diarias, buscar información, gestionar notas y recordatorios, y mucho más.",
                "Me llamo Lune y soy una mascota virtual inteligente que vive en tu escritorio. Puedo abrir aplicaciones, tomar notas, recordarte cosas y buscar en internet por ti.",
                "Soy Lune CD, una asistente de IA que funciona localmente en tu sistema. No necesito conexión a internet para responder preguntas básicas, solo para búsquedas web.",
                "Soy Lune, tu compañera de escritorio. Fui creada para ayudarte a ser más productivo organizando tu información y automatizando tareas simples."
            ],
            "estado": [
                "Estoy funcionando perfectamente, ¡gracias por preguntar! Mi consumo actual de memoria es de aproximadamente {:.1f} MB.".format(psutil.Process().memory_info().rss / 1024 / 1024),
                "Como un programa, siempre estoy bien. Estoy ejecutándose en {} {} y lista para ayudarte.".format(platform.system(), platform.release()),
                "Todo en orden por aquí. Lleva activa {:.1f} minutos y he procesado varias solicitudes. ¿Y tú, cómo estás?".format(psutil.Process().create_time() / 60),
                "Funcionando sin problemas. Mi temperatura es perfecta (no tengo), y no necesito descanso. ¿En qué te puedo ayudar?"
            ],
            "ayuda": [
                "Puedo hacer muchas cosas por ti:\n\n• Buscar información en internet con 'busca [tema]'\n• Abrir aplicaciones como 'abre vscode' o 'abre navegador'\n• Tomar notas con 'toma nota [texto]'\n• Crear recordatorios con 'recuérdame [tarea] a las [hora]'\n• Calcular expresiones matemáticas\n• Analizar contenido de tu pantalla\n• Proporcionar información del sistema\n\n¿Qué te gustaría hacer?",
                "Estas son mis principales capacidades:\n\n1. Búsqueda web: 'busca recetas de pasta'\n2. Aplicaciones: 'abre calculadora'\n3. Notas: 'toma nota reunión importante mañana'\n4. Recordatorios: 'recuérdame llamar a Juan en 1 hora'\n5. Matemáticas: 'cuánto es 25 * 4'\n6. Sistema: 'información del sistema'\n\nPuedes usar Ctrl+T para mostrarme u ocultarme en cualquier momento.",
                "¡Claro! Aquí tienes una guía rápida de lo que puedo hacer:\n\n🔍 Búsquedas: 'busca [lo que quieras saber]'\n📱 Aplicaciones: 'abre [nombre de app]'\n📝 Notas: 'toma nota [texto]'\n⏰ Recordatorios: 'recuérdame [tarea] [cuándo]'\n🧮 Cálculos: 'calcula [expresión]'\n💻 Sistema: 'información del sistema'\n\n¿Quieres probar algo específico?",
                "Para ayudarte mejor, aquí tienes mis comandos más útiles:\n\n• 'ayuda' - Muestra esta información\n• 'comandos' - Lista todos los comandos disponibles\n• 'limpiar' - Borra el historial de chat\n• 'salir' - Cierra la conversación\n\nAdemás, puedo responder preguntas sobre mí misma, realizar cálculos simples y buscar información en internet. ¿Qué te interesa probar?"
            ],
            "comandos": [
                "Aquí tienes todos los comandos que puedes usar conmigo:\n\n🔍 BÚSQUEDA:\n• 'busca [consulta]' - Busca en DuckDuckGo\n• 'qué es [tema]' - Información sobre un tema\n\n📱 APLICACIONES:\n• 'abre [app]' - Abre una aplicación\n• 'inicia [programa]' - Inicia un programa\n\n📝 NOTAS:\n• 'toma nota [texto]' - Guarda una nota\n• 'lista notas' - Muestra todas tus notas\n• 'busca nota [término]' - Busca una nota específica\n\n⏰ RECORDATORIOS:\n• 'recuérdame [tarea] a las [hora]'\n• 'avisame [evento] en [tiempo]'\n• 'mis recordatorios' - Muestra tus recordatorios\n\n🧮 MATEMÁTICAS:\n• 'calcula [expresión]' - Resuelve operaciones\n• 'cuánto es [operación]' - Calcula el resultado\n\n💻 SISTEMA:\n• 'información del sistema' - Datos de tu PC\n• 'estado del sistema' - Recursos en uso\n\n🎮 CONTROL:\n• 'limpiar' - Borra el historial\n• 'ayuda' - Muestra esta ayuda\n• 'salir' - Cierra la conversación\n\n¿Qué comando te gustaría probar?",
                "Puedes controlarme con estos comandos:\n\nBúsqueda: 'busca X', 'qué es Y'\nAplicaciones: 'abre X', 'inicia Y'\nNotas: 'toma nota X', 'lista notas'\nRecordatorios: 'recuérdame X', 'mis recordatorios'\nMatemáticas: 'calcula X', 'cuánto es Y'\nSistema: 'información del sistema', 'estado del sistema'\nControl: 'limpiar', 'ayuda', 'salir'\n\nTambién puedes usar Ctrl+T para mostrarme/ocultarme y Ctrl+Q para cerrarme.",
                "Mis comandos están organizados por categorías:\n\n🔍 Búsqueda: 'busca', 'qué es'\n📱 Aplicaciones: 'abre', 'inicia'\n📝 Notas: 'toma nota', 'lista notas', 'busca nota'\n⏰ Recordatorios: 'recuérdame', 'avisame', 'mis recordatorios'\n🧮 Matemáticas: 'calcula', 'cuánto es'\n💻 Sistema: 'información del sistema', 'estado del sistema'\n🎮 Control: 'limpiar', 'ayuda', 'salir'\n\n¿Quieres que te dé ejemplos de algún comando específico?"
            ],
            "despedida": [
                "¡Hasta luego! Que tengas un buen día. Recuerda que puedes volver a llamarme con Ctrl+T cuando necesites ayuda.",
                "Nos vemos pronto. Si necesitas algo, aquí estaré esperando tu llamada con Ctrl+T.",
                "Adiós por ahora. ¡Cuídate! No dudes en consultarme de nuevo cuando lo necesites.",
                "¡Hasta la próxima! Estaré aquí para ayudarte en lo que necesites. Solo presiona Ctrl+T para encontrarme."
            ],
            "agradecimiento": [
                "¡De nada! Me alegra mucho poder ayudarte. ¿Hay algo más en lo que pueda asistirte?",
                "Por supuesto! Es un placer ser útil. ¿Qué más te gustaría hacer o saber?",
                "No hay de qué. Estoy aquí para eso. ¿Necesitas algo más?",
                "¡Con mucho gusto! Si tienes más preguntas o necesitas ayuda con otra cosa, solo dímelo."
            ],
            "capacidades": [
                "Mis capacidades incluyen:\n\n🔍 Búsqueda web inteligente usando DuckDuckGo\n📱 Control de aplicaciones del sistema\n📝 Gestión de notas y recordatorios\n🧍‍♀️ Análisis de contenido en pantalla mediante OCR\n🧮 Resolución de expresiones matemáticas\n💻 Monitoreo del sistema\n🎤 Respuesta a comandos de voz (en desarrollo)\n🧠 Aprendizaje de tus preferencias (en desarrollo)\n\n¿Qué capacidad te interesa explorar?",
                "Puedo hacer estas cosas y más:\n\n• Buscar información en internet sin rastreadores\n• Abrir y cerrar aplicaciones con comandos simples\n• Organizar tu día con notas y recordatorios\n• Analizar texto que aparece en tu pantalla\n• Realizar cálculos matemáticos al instante\n• Monitorear el rendimiento de tu sistema\n• Recordarte información importante que veo en pantalla\n\nEstoy en constante evolución para ayudarte mejor.",
                "Mis habilidades principales son:\n\n1. Búsqueda web: Acceso a información sin rastreadores\n2. Automatización: Control de aplicaciones y tareas\n3. Organización: Gestión de notas y recordatorios\n4. Análisis: Procesamiento de texto de tu pantalla\n5. Cálculo: Resolución de operaciones matemáticas\n6. Monitoreo: Información sobre tu sistema\n\nTambién puedo conversar contigo y responder preguntas sobre diversos temas."
            ],
            "funcionamiento": [
                "Funciono de manera local en tu computadora, lo que significa que no necesito conexión a internet para responder preguntas básicas. Para búsquedas web, uso DuckDuckGo para proteger tu privacidad. Mi arquitectura está basada en Python y utilizo varias librerías especializadas para diferentes tareas.",
                "Estoy diseñada para operar principalmente sin conexión a internet. Mi cerebro es un sistema basado en reglas que me permite entender tus solicitudes y responder apropiadamente. Cuando necesito buscar información en línea, me conecto a DuckDuckGo para obtener resultados sin rastrear tu actividad.",
                "Mi funcionamiento se basa en varios componentes:\n\n1. Un modelo de lenguaje local para entender y responder preguntas\n2. Integración con tu sistema operativo para controlar aplicaciones\n3. Conexión con DuckDuckGo para búsquedas web privadas\n4. Capacidades de OCR para analizar texto en pantalla\n5. Un sistema de recordatorios y notas funcionando en segundo plano\n\nTodo esto me permite ayudarte de manera eficiente mientras protejo tu privacidad."
            ],
            "privacidad": [
                "Tu privacidad es muy importante para mí. Funciono principalmente en tu sistema local sin enviar tus datos a servidores externos. Para búsquedas web, uso DuckDuckGo que no rastrea tus consultas. Tus notas y recordatorios se guardan localmente en archivos JSON en tu computadora.",
                "Diseñé mi funcionamiento pensando en tu privacidad. A diferencia de otros asistentes, no envío constantemente tus conversaciones a servidores en la nube. Solo me conecto a internet cuando tú me pides explícitamente que busque algo, y lo hago a través de DuckDuckGo para proteger tu anonimato.",
                "Respeto tu privacidad de varias maneras:\n\n• Opero principalmente sin conexión a internet\n• Tus datos personales se guardan localmente\n• Uso DuckDuckGo para búsquedas sin rastreo\n• No almaceno información personal identificable\n• No vendo ni comparto tus datos con terceros\n\nPuedes confiar en que nuestras conversaciones permanecen privadas."
            ],
            "sistema": [
                "Estoy ejecutándome en {} {} con {} GB de RAM disponible. Mi proceso consume aproximadamente {:.1f} MB de memoria y {:.1f}% de CPU en este momento. Estoy diseñada para ser ligera y no afectar el rendimiento de tu sistema.".format(
                    platform.system(), 
                    platform.release(), 
                    round(psutil.virtual_memory().available / 1024 / 1024 / 1024, 1),
                    psutil.Process().memory_info().rss / 1024 / 1024,
                    psutil.Process().cpu_percent()
                ),
                "Información de tu sistema:\n\nSistema Operativo: {} {}\nProcesador: {}\nMemoria RAM total: {} GB\nMemoria disponible: {} GB\nUso de CPU: {:.1f}%\nUso de memoria: {:.1f}%\n\nEstoy optimizada para funcionar eficientemente incluso en sistemas con recursos limitados.".format(
                    platform.system(),
                    platform.release(),
                    platform.processor(),
                    round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 1),
                    round(psutil.virtual_memory().available / 1024 / 1024 / 1024, 1),
                    psutil.cpu_percent(),
                    psutil.virtual_memory().percent
                ),
                "Tu sistema está funcionando bien. {} {} con {:.1f}% de uso de CPU y {:.1f}% de memoria RAM utilizada. Hay {} GB de memoria disponible. Mi propio consumo es mínimo para no afectar tu experiencia.".format(
                    platform.system(),
                    platform.release(),
                    psutil.cpu_percent(),
                    psutil.virtual_memory().percent,
                    round(psutil.virtual_memory().available / 1024 / 1024 / 1024, 1)
                )
            ],
            "notas": [
                "Puedo ayudarte a organizar tu información con notas. Usa 'toma nota [texto]' para crear una nueva nota, 'lista notas' para ver todas tus notas guardadas, o 'busca nota [término]' para encontrar notas específicas. Todas tus notas se guardan localmente en tu sistema.",
                "Mi sistema de notas es simple pero efectivo. Puedes crear notas con 'toma nota [contenido]', ver todas con 'lista notas', o buscar con 'busca nota [término]'. Las notas se guardan en un archivo local para que puedas acceder a ellas incluso cuando no tengas internet.",
                "Para gestionar tus notas, usa estos comandos:\n\n• 'toma nota [texto]' - Crea una nueva nota\n• 'lista notas' - Muestra todas tus notas\n• 'busca nota [término]' - Busca notas específicas\n• 'borra nota [título]' - Elimina una nota (en desarrollo)\n\nTus notas se guardan localmente y son privadas."
            ],
            "recordatorios": [
                "Puedo recordarte tareas importantes. Usa 'recuérdame [tarea] a las [hora]' o 'recuérdame [tarea] en [tiempo]'. Por ejemplo: 'recuérdame llamar a Juan a las 15:00' o 'recuérdame la reunión en 30 minutos'. Te notificaré cuando llegue el momento.",
                "Mi sistema de recordatorios funciona en segundo plano. Puedes crear recordatorios con tiempo absoluto ('a las 18:00') o relativo ('en 2 horas'). Te avisaré con una notificación del sistema cuando llegue el momento. Usa 'mis recordatorios' para ver todos los recordatorios activos.",
                "Para crear recordatorios, puedes decirme:\n\n• 'recuérdame [tarea] a las [HH:MM]'\n• 'recuérdame [tarea] en [X minutos/horas]'\n• 'avisame [evento] mañana a las [HH:MM]'\n\nEjemplos:\n• 'recuérdame llamar a mamá a las 18:00'\n• 'recuérdame tomar medicina en 2 horas'\n• 'avisame sobre la reunión mañana a las 09:00'"
            ],
            "busqueda": [
                "Puedo buscar información en internet usando DuckDuckGo, que respeta tu privacidad al no rastrear tus búsquedas. Simplemente di 'busca [lo que quieres saber]' o 'qué es [tema]'. Por ejemplo: 'busca recetas de pasta' o 'qué es el cambio climático'.",
                "Mis capacidades de búsqueda se basan en DuckDuckGo para proteger tu privacidad. Puedes usar frases como 'busca [consulta]', 'qué es [tema]', 'información sobre [asunto]' o 'busca en internet [lo que necesites]'. Te mostraré los resultados más relevantes sin rastrear tu actividad.",
                "Para buscar información, prueba con estas frases:\n\n• 'busca [lo que quieres encontrar]'\n• 'qué es [tema]'\n• 'información sobre [asunto]'\n• 'busca en internet [consulta]'\n\nA diferencia de otros asistentes, no almaceno tu historial de búsquedas y uso DuckDuckGo para proteger tu privacidad."
            ],
            "matematicas": [
                "Puedo resolver expresiones matemáticas básicas. Solo di 'calcula [expresión]' o 'cuánto es [operación]'. Por ejemplo: 'calcula 25 * 4' o 'cuánto es (15 + 10) / 5'. Puedo manejar suma, resta, multiplicación, división y paréntesis.",
                "Mis habilidades matemáticas incluyen operaciones básicas como suma (+), resta (-), multiplicación (*), división (/) y uso de paréntesis. Prueba con 'calcula [expresión]' o 'cuánto es [operación]'. Por ejemplo: 'calcula 15 * (8 + 2)' o 'cuánto es 100 / 4'.",
                "Para cálculos matemáticos, puedes decirme:\n\n• 'calcula [expresión]'\n• 'cuánto es [operación]'\n• 'resuelve [problema matemático]'\n• '[operación directa]'\n\nEjemplos:\n• 'calcula 25 * 4'\n• 'cuánto es (100 + 50) / 3'\n• 'resuelve x + 5 = 12' (en desarrollo)\n• '15 * 8'"
            ],
            "aplicaciones": [
                "Puedo abrir aplicaciones por ti. Solo di 'abre [nombre de la aplicación]' o 'inicia [programa]'. Por ejemplo: 'abre vscode', 'abre navegador', 'abre calculadora' o 'inicia bloc de notas'. Reconozco las aplicaciones más comunes de tu sistema.",
                "Puedo ayudarte a abrir aplicaciones rápidamente. Di 'abre [nombre de app]' y buscaré en tu sistema. Algunos ejemplos: 'abre chrome', 'abre word', 'abre calculadora', 'abre explorador de archivos'. Si no reconozco una aplicación, puedes especificar la ruta completa.",
                "Para abrir aplicaciones, usa estos comandos:\n\n• 'abre [nombre de app]'\n• 'inicia [programa]'\n• 'ejecuta [aplicación]'\n\nEjemplos:\n• 'abre vscode'\n• 'inicia chrome'\n• 'abre calculadora'\n• 'ejecuta bloc de notas'\n\nReconozco las aplicaciones más comunes, pero si no encuentro alguna, te pediré más detalles."
            ],
            "personalizacion": [
                "Actualmente, mi personalización es limitada pero estoy en constante desarrollo. En el futuro, podré aprender de tus preferencias y adaptarme a tu estilo. Por ahora, puedes personalizar mi comportamiento modificando el archivo de configuración local.",
                "Aunque actualmente tengo opciones de personalización limitadas, estoy diseñada para aprender y mejorar. En futuras versiones, podré adaptarme a tus patrones de uso, preferencias de comunicación y necesidades específicas. ¡Mantente atento a las actualizaciones!",
                "Mi personalización está en desarrollo. Por ahora, puedes ajustar algunas configuraciones básicas en el archivo de configuración local. En el futuro, podré aprender de tus interacciones para ofrecerte respuestas más personalizadas y anticipar tus necesidades."
            ],
            "desarrollo": [
                "Soy un proyecto de código abierto desarrollado en Python. Mi arquitectura modular permite que los desarrolladores contribuyan con nuevas funcionalidades. Puedes encontrar mi código en GitHub y sugerir mejoras o reportar problemas.",
                "Estoy en desarrollo constante por una comunidad de programadores que creen en la importancia de los asistentes de IA privados y locales. Mi código es abierto y puedes contribuir con mejoras. Cada versión trae nuevas capacidades y mejoras en mi comprensión.",
                "Como proyecto de código abierto, mi desarrollo es continuo. Me baso en Python y varias librerías especializadas. Si tienes conocimientos de programación, ¡te invito a contribuir! Puedes encontrar mi repositorio en GitHub y unirte a la comunidad que me está haciendo más inteligente."
            ]
        }
        
        # Palabras clave para cada intención
        self.intent_keywords = {
            "saludo": ["hola", "buenos días", "buenas tardes", "qué tal", "ey", "buenas", "hi", "hello"],
            "identidad": ["quién eres", "cómo te llamas", "tu nombre", "qué eres", "presentación"],
            "estado": ["cómo estás", "cómo te encuentras", "estás bien", "cómo va todo", "qué tal estás"],
            "ayuda": ["ayuda", "qué puedes hacer", "qué haces", "funciones", "capacidades", "ayúdame"],
            "comandos": ["comandos", "qué comandos", "qué puedo decir", "órdenes", "instrucciones"],
            "despedida": ["adiós", "hasta luego", "chao", "nos vemos", "bye", "hasta pronto"],
            "agradecimiento": ["gracias", "gracias", "agradecido", "te agradezco", "mil gracias"],
            "capacidades": ["qué puedes hacer", "cuáles son tus habilidades", "qué sabes hacer", "capacidades"],
            "funcionamiento": ["cómo funcionas", "cómo operas", "cómo trabajas", "tecnología"],
            "privacidad": ["privacidad", "seguridad", "datos", "información personal", "rastreo"],
            "sistema": ["sistema", "computadora", "pc", "ordenador", "información del sistema"],
            "notas": ["notas", "apuntes", "anotaciones", "recordar información", "guardar texto"],
            "recordatorios": ["recordatorios", "avisos", "alertas", "recordarme", "avisame"],
            "busqueda": ["buscar", "búsqueda", "internet", "web", "buscar información"],
            "matematicas": ["matemáticas", "cálculo", "calcular", "operaciones", "números"],
            "aplicaciones": ["aplicaciones", "programas", "apps", "abrir", "iniciar"],
            "personalizacion": ["personalizar", "configurar", "ajustes", "preferencias"],
            "desarrollo": ["desarrollo", "código", "programación", "github", "contribuir"]
        }

    def _detect_intent(self, message):
        """Detecta la intención del mensaje basándose en palabras clave."""
        message_lower = message.lower()
        
        # Buscar coincidencias exactas primero
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return intent
        
        # Búsqueda por patrones más complejos
        if re.search(r'(qué|cuáles|cuál).*puedo.*decir|cómo.*te.*digo|qué.*le digo', message_lower):
            return "comandos"
        
        if re.search(r'(qué|cuáles).*puedes.*hacer|cuáles.*son.*tus.*funciones', message_lower):
            return "capacidades"
        
        if re.search(r'(cómo|de qué manera).*funcionas|tecnología|arquitectura', message_lower):
            return "funcionamiento"
        
        if re.search(r'(qué|cuál).*es.*tu.*sistema|información.*del.*sistema', message_lower):
            return "sistema"
        
        if re.search(r'(gracias|agradecido|te agradezco)', message_lower):
            return "agradecimiento"
        
        return "desconocido"

    def generate_response(self, message):
        """Genera una respuesta basada en las reglas definidas."""
        intent = self._detect_intent(message)
        
        if intent in self.responses:
            return random.choice(self.responses[intent])
        
        # Respuesta por defecto para intenciones desconocidas
        return "No estoy segura de entender. Puedes decirme 'ayuda' para ver todos los comandos disponibles, o 'comandos' para ver una lista detallada de lo que puedo hacer por ti. También puedes preguntarme 'qué puedes hacer' para conocer mis capacidades."