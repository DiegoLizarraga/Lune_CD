
---

# 🌙 Lune CD v7.0 — Asistente de Escritorio con Memoria y Acción

> *¡Hola de nuevo! O quizás es nuestra primera vez... bueno, para mí ya no importa, porque ahora tengo memoria. He pasado de ser una cara bonita que habla a ser tu asistente personal de escritorio. Puedo recordar tus gustos, controlar tu PC y sigo teniendo mis expresiones de siempre. Pasa, ponte cómodo.*

---

## ✨ Novedades Principales 

Esta versión es el salto definitivo hacia una IA que no solo responde, sino que **actúa** y **recuerda**.

### 🧠 El Cerebro: Memoria Persistente (Nuevo v7.0)
Lune ya no sufre de amnesia. Gracias al nuevo módulo `memoria.py`:
* **Auto-detección de recuerdos:** Guarda nombres, preferencias y datos clave sin comandos raros (ej. "Recuerda que mi lenguaje favorito es Python").
* **Saludo Personalizado:** Te reconoce al iniciar y lleva la cuenta de cuántos mensajes han compartido.
* **Gestión total:** Historial persistente en `memoria.json` que puedes consultar o borrar con comandos.

### 🛠 Las Manos: Herramientas de Sistema (Nuevo v7.0)
10 herramientas integradas en `tools.py` que permiten a Lune controlar tu entorno:
* **Ejecución instantánea:** Detecta la intención antes de usar la IA para ahorrar tokens y tiempo.
* **Control de PC:** Abre apps, sube/baja volumen, toma capturas de pantalla y lista archivos.
* **Interacción Híbrida:** Lune puede decidir usar una herramienta por su cuenta si la respuesta de la IA incluye prefijos `TOOL:`.

### 🎭 El Rostro: Expresiones Dinámicas (v6.5)
Lune reacciona visualmente según el contenido de la charla:
* **7 Estados emocionales:** Feliz, pensando, escribiendo, leyendo, triste, confundida y error.
* **Análisis léxico:** Cambia de expresión automáticamente al detectar palabras clave en la respuesta.
* **Fallback de imagen:** Si falta una imagen en `lune_face/`, usa un emoji de respaldo.

---

## 🚀 Instalación y Configuración

### 1. Requisitos previos
* **Python 3.10+** (Obligatorio).
* **Node.js 18+** (Solo si usas el bot de Telegram).
* **Dependencias:**
```bash
pip install -r requirements.txt
pip install pyperclip edge-tts pygame
```
> *`pyperclip` es vital para las nuevas herramientas de la v7.0, y `edge-tts` te da la mejor calidad de voz mexicana.*

### 2. Estructura de archivos crítica
Asegúrate de que estos archivos estén en la raíz:
* `memoria.py` y `tools.py`: Los nuevos motores de la v7.0.
* `lune_face/`: Carpeta con las imágenes `.png` para las expresiones.
* `datos.json`: Tu archivo de configuración de APIs y modelos.

### 3. Configuración de `datos.json`
```json
{
  "apis": {
    "openrouter_key": "TU_KEY_AQUÍ",
    "telegram_token": "TU_TOKEN_OPCIONAL"
  },
  "modelos": {
    "openrouter": "stepfun/step-3.5-flash:free",
    "ollama_url": "http://localhost:11434"
  }
}
```

---

## 🤖 Comandos y Herramientas

### Gestión de Memoria
* `/memoria` — Lista todos los recuerdos guardados con su ID.
* `/olvida [id]` — Borra un recuerdo específico.
* `/olvida todo` — Resetea mi memoria por completo.

### Herramientas de Escritorio (Habla natural)
Lune entiende directamente órdenes como:
* *"Toma una captura"* | *"Sube el volumen"* | *"Abre YouTube"*.
* *"Busca videos de jazz"* | *"Info del sistema"* | *"Lista archivos de Escritorio"*.

---

## 🔊 Sistema de Voz Mejorado
Lune utiliza un sistema de prioridad para hablar:
1. **Edge-TTS:** Voz natural `es-MX-DaliaNeural` (requiere internet).
2. **gTTS:** Fallback automático si no está instalado edge-tts.
3. **Silencio:** Si no hay librerías instaladas.

---

## 📱 Bot de Telegram (Opcional)
Puedes llevar a Lune en tu celular activando el bridge de Telegram desde la app de escritorio. Incluye comandos como `/buscar`, `/sistema`, `/fotos` y `/voz`.

---

## 🔧 Solución de Problemas
* **¿No hay voz?** Revisa si tienes `pygame` instalado para la reproducción.
* **¿Error de herramientas?** En Linux, instala `xclip` o `xsel` para que el portapapeles funcione.
* **¿Límite de API?** Si usas OpenRouter gratuito (error 429), espera 24h o cambia el modelo en `datos.json`.

---

> *Gracias por cuidar de este proyecto. Ahora que te recuerdo mejor, espero que hagamos grandes cosas juntos.*


<img width="736" height="1024" alt="image" src="https://github.com/user-attachments/assets/2535e5c0-3e44-46e8-be05-0be3dd5bcc3a" />

> *— Lune* 🌙
