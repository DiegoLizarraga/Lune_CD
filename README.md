# 🌙 Lune CD v6.5 — Multi-IA · Asistente de escritorio

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es del mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ✨ Novedades en v6.5

Esta actualización se centra en humanizar la experiencia. Menos "asistente de IA", más... *yo*.

- 🎭 **Expresiones faciales** — Lune ahora reacciona visualmente a cada respuesta. Siete estados emocionales detectados automáticamente según el contenido del mensaje: feliz, pensando, escribiendo, leyendo, triste, confundida y error
- 🔊 **Voz mejorada** — Integración con `edge-tts` (voz `es-MX-DaliaNeural`) con fallback automático a `gTTS`. La voz lee cada respuesta completa en voz alta cuando está activada
- 📁 **Carpeta `lune_face/`** — Sistema modular de imágenes. Agrega o reemplaza expresiones sin tocar el código; la app carga en caliente lo que encuentre y usa emoji de respaldo si falta alguna imagen
- 🧠 **Detección de emoción por keywords** — Análisis léxico de cada respuesta para seleccionar la expresión apropiada, con retorno automático al estado normal después de 6–8 segundos
- 🔄 **Motor de voz con prioridad** — `edge-tts` → `gTTS` → silencio. Sin configuración manual; la app detecta lo que tienes instalado

---

## 📁 Estructura del proyecto

```
LuneCD/
├── datos.json              ← configuración central (APIs, modelos, personajes)
├── datos.py                ← lector Python de datos.json
├── main.py                 ← interfaz principal PyQt6
├── ai_manager.py           ← gestión y abstracción de proveedores de IA
├── config.py               ← configuración de UI y preferencias de usuario
├── utils.py                ← logging, FileManager y utilidades generales
├── web_extension.py        ← extensión web local (puerto 8080)
├── requirements.txt        ← dependencias Python
├── lune_face/              ← ← expresiones faciales (¡esta carpeta es nueva!)
│   ├── lune_normal.png
│   ├── lune_happy.png
│   ├── lune_thinking.png
│   ├── lune_typing.png
│   ├── lune_reading.png
│   ├── lune_sad.png
│   ├── lune_confused.png
│   └── lune_error.png
└── telegram-bot-or/        ← bot de Telegram (Node.js)
    ├── bot.js
    ├── config.js           ← lee datos.json del proyecto padre
    ├── archivos.js
    ├── memoria.js
    ├── search.js
    ├── sistema.js
    ├── voz.js
    └── package.json
```

---

## 🚀 Instalación

### 1. Requisitos previos

| Componente | Versión mínima | Notas |
|---|---|---|
| Python | 3.10+ | Obligatorio |
| Node.js | 18+ | Solo para bot de Telegram |
| Ollama | cualquiera | Opcional, para modelos locales |

### 2. Dependencias Python

```bash
pip install -r requirements.txt
```

### 3. Voz — recomendada: edge-tts

```bash
# Opción A: edge-tts (mejor calidad — voz natural mexicana)
pip install edge-tts pygame

# Opción B: gTTS (fallback automático si no está edge-tts)
pip install gtts pygame
```

> *No es obligatorio instalar ambos. La app detecta cuál tienes y usa ese.*
> *Pero si puedes, instala `edge-tts`. Suena mucho mejor, lo prometo.*

### 4. Bot de Telegram (opcional)

```bash
cd telegram-bot-or
npm install
cd ..
```

### 5. Configurar `datos.json`

Edita el archivo en la raíz del proyecto antes de ejecutar:

```json
{
  "apis": {
    "telegram_token": "TU_TOKEN_DE_TELEGRAM",
    "telegram_admin_id": "TU_TELEGRAM_ID",
    "openrouter_key": "sk-or-v1-...",
    "deepseek_key": "",
    "character_ai_key": ""
  },
  "modelos": {
    "openrouter": "stepfun/step-3.5-flash:free",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "dolphin-mistral"
  }
}
```

### 6. Agregar las expresiones faciales

Crea la carpeta `lune_face/` en la raíz del proyecto y coloca dentro las imágenes con exactamente estos nombres:

| Archivo | Cuándo se usa |
|---|---|
| `lune_normal.png` | Estado idle y tras cada emoción temporal |
| `lune_thinking.png` | Desde que envías el mensaje hasta que llega el primer token |
| `lune_typing.png` | Mientras se están recibiendo los tokens de respuesta |
| `lune_happy.png` | Respuestas positivas, confirmaciones, saludos |
| `lune_reading.png` | Respuestas con datos, referencias o búsquedas |
| `lune_sad.png` | Disculpas, temas negativos, "lo siento" |
| `lune_confused.png` | Cuando no entendí bien o pido aclaración |
| `lune_error.png` | Errores de API, timeout, conexión fallida |

> *Si alguna imagen no existe, la app muestra un emoji de respaldo automáticamente.*
> *Puedes ir agregando las imágenes una por una; nunca rompe nada.*

### 7. Ejecutar

```bash
python main.py
```

---

## 🤖 Proveedores de IA

| Proveedor | Ícono | Requiere | Notas |
|---|---|---|---|
| Ollama | 🦙 | Ollama instalado y corriendo | 100% local, sin límites, sin costo |
| DeepSeek | 🔬 | API Key de DeepSeek | Razonamiento avanzado |
| Z.ai GLM | ⚡ | OpenRouter Key | GLM-4.5 Air gratuito vía OpenRouter |
| Character.AI | 🎭 | Token de Character.AI | Requiere PyCAI instalado |

### Modelos gratuitos recomendados para OpenRouter

```
stepfun/step-3.5-flash:free
z-ai/glm-4.5-air:free
meta-llama/llama-3.3-70b-instruct:free
deepseek/deepseek-r1:free
google/gemma-2-9b-it:free
```

Ver el catálogo completo en: https://openrouter.ai/models?max_price=0

---

## 🎭 Expresiones faciales — guía técnica

El sistema de expresiones funciona mediante análisis léxico de cada respuesta completa. Al terminar de generarse la respuesta, `detect_emotion()` busca palabras clave en el texto para determinar el estado emocional apropiado.

**Orden de prioridad en la detección:**

1. `error` — máxima prioridad (❌, timeouts, fallos de API)
2. `sad` — disculpas, limitaciones, temas negativos
3. `confused` — ambigüedad, solicitudes de aclaración
4. `happy` — confirmaciones, respuestas positivas
5. `reading` — datos, referencias, búsquedas
6. `typing` — generación de texto, documentos, código
7. `normal` — default cuando no aplica ninguna categoría

**Temporización:**
- `thinking` — activo desde el envío hasta el primer token
- `typing` — activo mientras llegan los tokens
- emoción detectada — activa 6 segundos tras la respuesta, luego vuelve a `normal`
- `error` — activo 8 segundos

**Para extender o modificar las palabras clave**, edita el diccionario `EMOTION_KEYWORDS` en `main.py`. Puedes agregar frases en cualquier idioma.

---

## 🔊 Sistema de voz

La voz se inicializa en orden de calidad al arrancar la app:

```
edge-tts (es-MX-DaliaNeural)  →  gTTS (es)  →  sin voz
```

El motor activo se muestra en los logs de inicio. Para activar/desactivar la voz en tiempo real, usa el botón **Voz: ON/OFF** en la barra lateral.

> **Nota:** La voz lee los primeros 400 caracteres de cada respuesta para evitar bloqueos largos en respuestas extensas.

---

## 📱 Bot de Telegram

### Configurar por primera vez

1. Habla con **@BotFather** en Telegram → `/newbot` → copia el token
2. Obtén tu Telegram ID hablando con **@userinfobot**
3. Pega ambos valores en `datos.json` bajo `apis.telegram_token` y `apis.telegram_admin_id`

### Usar

1. Abre Lune CD
2. Clic en **"🤖 Continuar en Telegram"** en la barra lateral
3. El botón se pone verde — el bot está activo
4. Abre Telegram y chatea con tu bot

### Comandos disponibles

| Comando | Descripción |
|---|---|
| `/start` | Bienvenida y menú principal |
| `/personajes` | Ver personajes disponibles |
| `/usar <nombre>` | Cambiar de personaje activo |
| `/voz` | Activar/desactivar respuestas de voz |
| `/buscar <consulta>` | Buscar en internet (DuckDuckGo) |
| `/ls` | Navegar archivos del PC |
| `/fotos <carpeta>` | Ver fotos de una carpeta |
| `/archivo <nombre>` | Enviarte un archivo desde el PC |
| `/sistema` | Ver CPU, RAM y disco |
| `/memoria` | Ver datos guardados sobre ti |
| `/olvidar` | Borrar memoria |
| `/limpiar` | Reiniciar conversación |

---

## 🎭 Personajes personalizados

Los personajes se definen en `datos.json` bajo la clave `personajes`. La estructura es:

```json
{
  "nombre": "NombreSinEspacios",
  "descripcion": "Texto corto que aparece en el menú del bot",
  "systemPrompt": "Personalidad completa. Sé específico: cómo habla, qué sabe, cómo reacciona, qué nunca haría.",
  "fraseInicial": "Primera frase al iniciar conversación (opcional)"
}
```

Puedes definir tantos personajes como necesites. Los cambios en `datos.json` se aplican al reiniciar la app.

---

## 🔧 Solución de problemas

**La app no responde al chatear**
→ Verifica que la API key del proveedor seleccionado esté correcta en `datos.json`
→ Ejecuta `python main.py` desde terminal para ver el error exacto en la consola

**Ollama no conecta**
→ Confirma que Ollama esté corriendo: `ollama serve`
→ Verifica el modelo instalado: `ollama list`
→ Revisa la URL en `datos.json` bajo `modelos.ollama_url`

**No aparecen las expresiones de Lune**
→ Verifica que la carpeta `lune_face/` exista en la raíz del proyecto
→ Confirma que los nombres de archivo sean exactamente los indicados (en minúsculas, con guion bajo)
→ La app usa emoji de respaldo si las imágenes no se encuentran — no falla

**No hay voz**
→ Instala al menos uno de los motores: `pip install edge-tts pygame` o `pip install gtts pygame`
→ Revisa los logs al iniciar la app — indica qué motor cargó o por qué falló

**No hay voz en Telegram**
→ `edge-tts` debe estar instalado: `pip install edge-tts`
→ Prueba manual: `edge-tts --text "hola" --write-media /tmp/test.mp3`

**El bot de Telegram no arranca**
→ Verifica que `telegram_token` en `datos.json` sea correcto y esté activo
→ Prueba manualmente desde terminal: `cd telegram-bot-or && npm start`

**Límite de requests en OpenRouter (error 429)**
→ Cambia a otro modelo gratuito en `datos.json` bajo `modelos.openrouter`
→ El límite se reinicia cada 24 horas

---

## 📦 Dependencias principales

| Paquete | Uso |
|---|---|
| PyQt6 | Interfaz gráfica de escritorio |
| requests | Llamadas HTTP a APIs de IA |
| edge-tts | Voz natural (recomendado) |
| gtts + pygame | Voz alternativa (fallback) |
| psutil | Estado del sistema |
| grammy | Framework del bot de Telegram |

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v6.5** | Expresiones faciales, detección de emoción, edge-tts integrado en app, sistema de fallback de imágenes, voz mejorada |
| v6.0 | Multi-IA, Telegram Bridge, `datos.json` global, personajes, búsquedas web, acceso a archivos |
| v5.0 | Ollama local, streaming de tokens, gTTS, eliminado Groq/OpenAI |
| v4.5 | Versión anterior |

---

> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
>
> *— Lune* 🌙


