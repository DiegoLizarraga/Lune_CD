╔═══════════════════════════════════════════════════════════════════════════╗
║                   🌙 LUNE CD v5.0 - ASISTENTE VIRTUAL                     ║
║                        Powered by Ollama + gTTS                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

📋 ARCHIVOS INCLUIDOS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 CÓDIGO FUENTE:
  ├── main.py               ← Interfaz principal (PyQt6) + Voz (gTTS)
  ├── config.py             ← Gestor de configuración
  ├── ai_manager.py         ← Proveedor de IA (Ollama con streaming)
  └── utils.py              ← Utilidades (logging, archivos, etc.)

⚙️ CONFIGURACIÓN:
  ├── config.json           ← Configuración del modelo Ollama
  ├── requirements.txt      ← Dependencias (pip install -r)
  └── .gitignore            ← Archivos a ignorar

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 INICIO RÁPIDO (3 PASOS):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PASO 1: INSTALAR DEPENDENCIAS
  $ pip install -r requirements.txt
  $ sudo apt install alsa-utils -y

PASO 2: CONFIGURAR OLLAMA
  1. Instala Ollama: https://ollama.ai
  2. Crea tu modelo personalizado:
       $ nano mi_agente.modelfile
     Contenido:
       FROM dolphin-mistral
       SYSTEM """
       Eres Nova, una asistente inteligente y amigable.
       Hablas en español y tienes conocimientos en tecnología.
       """
  3. Crea el modelo:
       $ ollama create nova -f mi_agente.modelfile
  4. Verifica que esté corriendo:
       $ ollama serve

PASO 3: EJECUTAR
  $ python main.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ NOVEDADES v5.0:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Motor de IA 100% local con Ollama (sin APIs externas)
✅ Streaming de respuestas en tiempo real (token a token)
✅ Voz femenina en español con gTTS (Google Text-to-Speech)
✅ Botón 🔊/🔇 para activar/desactivar voz desde la UI
✅ Cursor animado ▋ mientras la IA escribe
✅ Eliminado Groq/OpenAI - arquitectura simplificada
✅ Sin necesidad de API Keys
✅ Funciona completamente offline (excepto gTTS)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 DEPENDENCIAS PRINCIPALES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PyQt6        → Interfaz gráfica
  requests     → Comunicación con Ollama
  gtts         → Voz femenina en español
  pygame       → Reproducción de audio
  alsa-utils   → Backend de audio (Linux)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❓ PROBLEMAS COMUNES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ "No se conecta a Ollama"
  → Ejecuta en otra terminal: ollama serve

❌ "aplay: not found" (sin audio)
  → Ejecuta: sudo apt install alsa-utils -y

❌ "No se instala PyQt6 (Linux)"
  → Ejecuta: sudo apt-get install python3-pyqt6

❌ "La voz no suena"
  → Verifica conexión a internet (gTTS requiere internet)
  → Prueba: python3 -c "from gtts import gTTS; import pygame, io; tts = gTTS('hola', lang='es'); fp = io.BytesIO(); tts.write_to_fp(fp); fp.seek(0); pygame.mixer.init(); pygame.mixer.music.load(fp); pygame.mixer.music.play(); import time; time.sleep(3)"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 ESTADÍSTICAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Versión anterior:    v4.5
  Versión actual:      v5.0
  Proveedores de IA:   1 (Ollama local)
  Voces disponibles:   Español (es) vía gTTS
  Dependencias externas de API: 0 ✅

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✨ ¡TODO LISTO! ¡A USAR! 🌙