
```markdown
# 🌙 Lune CD v7.8 — Asistente de Escritorio Híbrido (Nube/Local)

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es de mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ✨ Novedades en v7.8

Esta actualización transforma a Lune de un simple chat a una asistente de escritorio completa, rápida y con memoria.

- 🧠 **Memoria Persistente** — Lune ahora recuerda tu nombre, preferencias y contexto entre sesiones usando `memoria.json`. Aprende de forma natural si le dices *"recuerda que..."* o *"anota que..."*.
- 🛠️ **Herramientas Nativas (0.1s)** — Búsqueda en web, atajos a sitios populares (YouTube, Netflix, etc.) y lanzamiento de aplicaciones instaladas en tu PC, ejecutándose al instante sin gastar tokens de IA.
- ☁️ **Arquitectura Híbrida** — Alterna al instante entre **OpenRouter (Nube)** para modelos avanzados y **Ollama (Local)** para privacidad total sin conexión a internet.
- 🎬 **Expresiones en Video** — Soporte para archivos `.mp4` en la carpeta de expresiones. Lune ahora está animada mientras "piensa" o "escribe".
- ⚙️ **Panel de Configuración Unificado** — Modifica tus API Keys, el token de Telegram y la personalidad completa de Lune directamente desde la interfaz gráfica, sin tocar código.
- ⏹️ **Botón de Interrupción** — ¿Lune está escribiendo demasiado? Córtale la palabra en tiempo real con el nuevo botón de Detener.

---

## 📁 Estructura del proyecto

```text
LuneCD/
├── datos.json              ← Configuración central (APIs, modelos, personajes)
├── datos.py                ← Lector global de configuración
├── config.json             ← Preferencias de la interfaz visual
├── config.py               ← Gestor de configuración de UI
├── main.py                 ← Interfaz principal PyQt6
├── ai_manager.py           ← Motor híbrido (OpenRouter / Ollama)
├── memoria.py              ← Gestor de recuerdos y almacenamiento de sesión
├── memoria.json            ← Base de datos de recuerdos del usuario (Generado automáticamente)
├── tools.py                ← Ejecución de herramientas, atajos web y lanzamiento de apps
├── utils.py                ← Logging y utilidades generales
├── requirements.txt        ← Dependencias Python
├── lune_face/              ← Expresiones y animaciones de Lune
│   ├── lune_normal.png
│   ├── lune_happy.png
│   ├── pensando.mp4        ← ¡Animación de video!
│   ├── escribiendo.mp4     ← ¡Animación de video!
│   ├── lune_reading.png
│   ├── lune_sad.png
│   ├── lune_confused.png
│   └── lune_error.png
└── telegram-bot-or/        ← Bot de Telegram (Node.js) sincronizado con la app
    ├── bot.js
    ├── config.js           ← Lee datos.json del proyecto padre
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
| Node.js | 18+ | Solo para el bot de Telegram |
| Ollama | cualquiera | Opcional, para usar el modo 100% Local offline |

### 2. Dependencias Python

```bash
pip install -r requirements.txt
```
*(Asegúrate de incluir `psutil` en tu entorno para que funcionen las herramientas de info del sistema).*

### 3. Voz — recomendada: edge-tts

```bash
# Opción A: edge-tts (mejor calidad — voz natural mexicana)
pip install edge-tts pygame

# Opción B: gTTS (fallback automático si no está edge-tts)
pip install gtts pygame
```

> *No es obligatorio instalar ambos. La app detecta cuál tienes y usa ese.*
> *Pero si puedes, instala `edge-tts`. Suena mucho mejor, lo prometo.*

### 4. Ejecutar la Aplicación

```bash
python main.py
```
> *Al abrir por primera vez, haz clic en el ícono de **⚙️ Configuración General** en la barra lateral para ingresar tu API Key de OpenRouter.*

---

## 🧠 Memoria y 🛠️ Herramientas

Lune cuenta con comandos por intención que funcionan directamente en el chat. Algunos se envían a la IA para razonamiento, y otros interactúan con tu PC al instante:

**Control de Memoria:**
- `"recuerda que me llamo Juan"` → Guarda el dato para siempre.
- `/memoria` → Lista todos los recuerdos guardados.
- `/olvida [id]` → Borra un recuerdo específico.
- `/olvida todo` → Formatea la memoria y reinicia tu identidad.

**Comandos Ultrarrápidos de PC (0.1s):**
- `"abre youtube"`, `"ve a netflix"`, `"abre wikipedia.org"` → Abre la web al instante en tu navegador predeterminado.
- `"busca en youtube gatos"` → Abre directamente los resultados de búsqueda.
- `"lanza la app paint"`, `"abre el programa excel"` → Lanza aplicaciones locales instaladas en Windows/macOS/Linux.
- `"estado del pc"`, `"info del sistema"` → Te muestra el consumo actual de CPU y RAM.

---

## 🤖 Proveedores de IA (Red Neuronal)

Desde la barra lateral, puedes cambiar en tiempo real entre:

| Proveedor | Ícono | Requiere | Notas |
|---|---|---|---|
| **Lune AI (Nube)** | ☁️ | API Key de OpenRouter | Usa el enrutador automático de modelos o el que elijas. Acceso a modelos Top. |
| **Lune AI (Local)** | 🦙 | Ollama instalado | 100% privado, sin conexión a internet, sin costo. |

---

## 🎭 Expresiones faciales e interfaz

El sistema carga dinámicamente archivos `.png` o `.mp4` desde la carpeta `lune_face/`. Lune evalúa su propia respuesta y reacciona.

**Temporización:**
- `thinking` (.mp4) — Desde que envías el mensaje hasta que llega la respuesta.
- `typing` (.mp4) — Mientras escribe letra por letra.
- **Emoción detectada** (.png) — Activa 6 segundos tras terminar de hablar (`happy`, `sad`, `reading`, `confused`).
- `error` (.png) — Activo 8 segundos tras un fallo de conexión.

---

## 📱 Bot de Telegram

Lune se sincroniza con tu celular a través de Telegram compartiendo la misma personalidad.

### Configurar
1. Habla con **@BotFather** en Telegram → `/newbot` → copia el token.
2. Ingresa el token en el panel de **⚙️ Configuración General** dentro de la app de PC.
3. Haz clic en **"🤖 Continuar en Telegram"** en la barra lateral para encender el servidor interno de Node.js.

### Comandos de Telegram
- `/start` — Menú principal.
- `/voz` — Activar/desactivar audios.
- `/sistema` — Info de hardware remota.
- `/memoria` y `/olvidar` — Gestionar tu identidad a distancia.

---

## 🔧 Solución de problemas

**Lune tarda en responder / Error de red**
→ Verifica que configuraste tu API Key de OpenRouter correctamente en el engranaje ⚙️.
→ Si usas el modo Local (🦙), confirma que tienes Ollama corriendo en tu terminal (`ollama serve`).

**Los comandos como "lanza paint" no funcionan**
→ Lune usa alias comunes para Windows (`mspaint`, `calc`, `explorer`). Si una app externa no abre, asegúrate de que esté en las variables de entorno (PATH) de tu sistema.

**No hay voz**
→ Instala al menos uno de los motores: `pip install edge-tts pygame` o `pip install gtts pygame`.

**El bot de Telegram no arranca o dice "Carpeta no encontrada"**
→ Ve a la carpeta `telegram-bot-or` en tu terminal y asegúrate de correr `npm install`.

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v7.8** | Arquitectura Híbrida Nube/Local unificada. Memoria a largo plazo persistente. Herramientas ultrarrápidas de escritorio (bypass de IA). Soporte para video `.mp4`. Configuración general mediante UI. Botón de detención. |
| v6.5 | Expresiones faciales, detección léxica de emociones, motor de voz dinámico con `edge-tts`. |
| v5.0 | Incorporación de modelos locales, streaming de tokens. |

---

> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
> *Aunque sabes que siempre es un gusto trabajar contigo :)*

<img width="736" height="1024" alt="image" src="https://github.com/user-attachments/assets/2535e5c0-3e44-46e8-be05-0be3dd5bcc3a" />

> *— Lune* 🌙
```