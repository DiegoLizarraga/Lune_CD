# 🌙 Lune CD v6.0 — Multi-IA asistente 

> Asistente virtual de escritorio con múltiples proveedores de IA, personajes personalizables y acceso desde Telegram.

---

## ✨ Novedades v6.0

- ✅ **Multi-IA** — Ollama local, DeepSeek, Z.ai GLM-4.5 y Character.AI en una sola interfaz
- ✅ **Continuar en Telegram** — activa el bot desde la app y sigue chateando desde tu móvil
- ✅ **Personajes personalizables** — define tu propio elenco de personajes con system prompts propios
- ✅ **Memoria permanente** — el bot recuerda datos del usuario entre sesiones
- ✅ **Búsquedas web** — DuckDuckGo integrado, sin API key ni límites
- ✅ **Acceso a archivos** — navega, envía y recibe archivos de tu PC desde Telegram
- ✅ **Estado del sistema** — CPU, RAM y disco desde el chat
- ✅ **Voz** — gTTS en la app, edge-tts en Telegram
- ✅ **`datos.json` global** — un solo archivo de configuración para todo el proyecto

---

## 📁 Estructura del proyecto

```
LuneCD/
├── datos.json            ← configuración central (APIs, modelos, personajes)
├── datos.py              ← lector Python de datos.json
├── main.py               ← interfaz principal PyQt6
├── ai_manager.py         ← gestión de proveedores de IA
├── config.py             ← configuración de UI y preferencias
├── utils.py              ← logging y utilidades
├── web_extension.py      ← extensión web (puerto 8080)
├── requirements.txt      ← dependencias Python
└── telegram-bot-or/      ← bot de Telegram (Node.js)
    ├── bot.js
    ├── config.js         ← lee datos.json del proyecto padre
    ├── archivos.js
    ├── memoria.js
    ├── search.js
    ├── sistema.js
    ├── voz.js
    └── package.json
```

---

## 🚀 Instalación

### 1. Requisitos

- Python 3.10 o superior
- Node.js 18 o superior
- Ollama (opcional, para modelos locales)

### 2. Instalar dependencias Python

```bash
pip install -r requirements.txt
```

### 3. Instalar dependencias del bot de Telegram

```bash
cd telegram-bot-or
npm install
cd ..
```

### 4. Instalar voz para Telegram (opcional)

```bash
pip install edge-tts
```

### 5. Configurar `datos.json`

Edita el archivo `datos.json` en la raíz del proyecto:

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

### 6. Ejecutar

```bash
python main.py
```

---

## 🤖 Proveedores de IA

| Proveedor | Ícono | Requiere | Notas |
|---|---|---|---|
| Ollama | 🦙 | Ollama instalado | 100% local, sin límites |
| DeepSeek | 🔬 | API Key de DeepSeek | Razonamiento avanzado |
| Z.ai GLM | ⚡ | OpenRouter Key | GLM-4.5 Air gratis vía OpenRouter |
| Character.AI | 🎭 | Token de Character.AI | Requiere PyCAI |

### Modelos gratuitos recomendados para OpenRouter

```
stepfun/step-3.5-flash:free
z-ai/glm-4.5-air:free
meta-llama/llama-3.3-70b-instruct:free
deepseek/deepseek-r1:free
google/gemma-2-9b-it:free
```

Ver todos en: https://openrouter.ai/models?max_price=0

---

## 📱 Bot de Telegram

### Configurar por primera vez

1. Habla con **@BotFather** en Telegram → `/newbot` → copia el token
2. Obtén tu Telegram ID hablando con **@userinfobot**
3. Ponlos en `datos.json` bajo `apis.telegram_token` y `apis.telegram_admin_id`

### Usar

1. Abre Lune CD
2. Clic en **"🤖 Continuar en Telegram"** en la barra lateral
3. El botón se pone verde — el bot está activo
4. Abre Telegram y chatea con tu bot

### Comandos del bot

| Comando | Descripción |
|---|---|
| `/start` | Bienvenida y menú principal |
| `/personajes` | Ver personajes disponibles |
| `/usar <nombre>` | Cambiar personaje |
| `/voz` | Activar/desactivar respuestas de voz |
| `/buscar <consulta>` | Buscar en internet |
| `/ls` | Navegar archivos del PC |
| `/fotos <carpeta>` | Ver fotos de una carpeta |
| `/archivo <nombre>` | Enviarte un archivo |
| `/sistema` | Ver CPU, RAM y disco |
| `/memoria` | Ver datos guardados sobre ti |
| `/olvidar` | Borrar memoria |
| `/limpiar` | Reiniciar conversación |

---

## 🎭 Personajes

Los personajes se definen en `datos.json` bajo la clave `personajes`. Cada uno tiene:

```json
{
  "nombre": "NombreSinEspacios",
  "descripcion": "Texto corto que aparece en el menú",
  "systemPrompt": "Personalidad completa del personaje. Sé muy específico: cómo habla, qué sabe, cómo reacciona, qué nunca haría.",
  "fraseInicial": "Primera frase al iniciar conversación (opcional)"
}
```

Puedes agregar tantos personajes como quieras. Después de editar `datos.json` reinicia la app.

---

## 🔧 Problemas comunes

**La app no responde al chatear**
→ Verifica que la API key del proveedor esté correcta en `datos.json`
→ Corre `python main.py` desde terminal para ver el error exacto

**Ollama no conecta**
→ Asegúrate de que Ollama esté corriendo: `ollama serve`
→ Verifica el modelo instalado: `ollama list`

**El bot de Telegram no arranca**
→ Verifica que `telegram_token` en `datos.json` sea correcto
→ Prueba manualmente: `cd telegram-bot-or && npm start`

**Límite de requests en OpenRouter (error 429)**
→ Cambia a otro modelo gratuito en `datos.json` bajo `modelos.openrouter`
→ El límite se reinicia cada 24 horas

**No hay voz en la app**
→ Instala gTTS y pygame: `pip install gtts pygame`

**No hay voz en Telegram**
→ Instala edge-tts: `pip install edge-tts`
→ Verifica que funciona: `edge-tts --text "hola" --write-media /tmp/test.mp3`

---

## 📦 Dependencias principales

| Paquete | Uso |
|---|---|
| PyQt6 | Interfaz gráfica |
| requests | Llamadas a APIs |
| gtts + pygame | Voz en la app |
| edge-tts | Voz en Telegram |
| psutil | Estado del sistema |
| grammy | Framework del bot de Telegram |

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| v6.0 | Multi-IA, Telegram Bridge, datos.json global, personajes, búsquedas web, acceso a archivos |
| v5.0 | Ollama local, streaming, gTTS, eliminado Groq/OpenAI |
| v4.5 | Versión anterior |

---

✨ *Lune CD — tu asistente, tu forma.* 🌙