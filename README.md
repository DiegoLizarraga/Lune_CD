# 🌙 Lune CD v8.0 — Asistente de Escritorio Híbrido (Nube/Local)

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es de mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ✨ Novedades en v8.0 — *"Hora de cocinar"* 🍳

Esta versión hace a Lune **más rápida, más viva y más útil para tu PC**.

- 💬 **Banco de respuestas instantáneas** — Saludos, agradecimientos, despedidas, la hora, la fecha, chistes y más se responden **al instante, sin gastar tokens de IA** y con la personalidad alegre y servicial de Lune. (`respuestas.py`)
- ⚡ **Optimizador del Sistema (estilo Stacer)** — Un panel nuevo para **liberar espacio** (temporales, caché de navegadores, miniaturas, papelera), **monitorear CPU/RAM/Disco en vivo** y **cerrar procesos pesados**. Limpieza 100% segura: solo toca archivos temporales. (`optimizador.py`)
- ⚙️ **Centro de Rendimiento configurable** — Activa o desactiva funciones (animaciones de video, fondo animado, voz automática, streaming, respuestas instantáneas) para **ajustar el consumo a tu PC** desde la Configuración General.
- 🎨 **Avatar Packs** — Cambia el "modelo" visual de Lune soltando carpetas en `lune_face/packs/`. Base para futuros modelos animados **VRM/Live2D estilo Mate-Engine** (ver [ROADMAP_MODELOS.md](ROADMAP_MODELOS.md)).
- 🚀 **Respuestas más veloces** — Caché en memoria para la configuración (`datos.py`) y **conexiones HTTP reutilizadas** (keep-alive) hacia OpenRouter/Ollama, reduciendo la latencia de cada mensaje.
- 🧩 **Accesos rápidos** — Chips de acción directa en la pantalla de bienvenida (Saludar, Optimizar PC, Mi memoria, Herramientas).

---

## 📁 Estructura del proyecto

```text
LuneCD/
├── datos.json              ← Configuración central (APIs, modelos, personajes)
├── datos.py                ← Lector global de configuración (con caché)
├── config.json             ← Preferencias de UI, features y optimizador
├── config.py               ← Gestor de configuración y toggles de rendimiento
├── main.py                 ← Interfaz principal PyQt6
├── ai_manager.py           ← Motor híbrido (OpenRouter / Ollama) con sesión HTTP
├── respuestas.py           ← 💬 Banco de respuestas predeterminadas (NUEVO)
├── optimizador.py          ← ⚡ Limpieza y monitoreo del sistema (NUEVO)
├── memoria.py              ← Gestor de recuerdos y sesión
├── memoria.json            ← Base de datos de recuerdos (autogenerado)
├── tools.py                ← Herramientas, atajos web y lanzamiento de apps
├── utils.py                ← Logging y utilidades generales
├── requirements.txt        ← Dependencias Python
├── ROADMAP_MODELOS.md      ← 🧩 Plan de modelos/avatares estilo Mate-Engine (NUEVO)
├── inicio.mp4              ← Video de la pantalla de bienvenida
├── lune_face/              ← Expresiones y animaciones de Lune
│   ├── lune_normal.png · lune_happy.png · lune_sad.png · ...
│   ├── pensando.mp4 · escribiendo.mp4   ← animaciones
│   └── packs/              ← 🎨 Avatar packs intercambiables (NUEVO)
└── telegram-bot-or/        ← Bot de Telegram (Node.js) sincronizado con la app
```

---

## 🚀 Instalación

### 1. Requisitos previos

| Componente | Versión mínima | Notas |
|---|---|---|
| Python | 3.10+ | Obligatorio |
| Node.js | 18+ | Solo para el bot de Telegram |
| Ollama | cualquiera | Opcional, para el modo 100% Local offline |

### 2. Dependencias Python

```bash
pip install -r requirements.txt
```
*(Incluye `psutil`, necesario para el Optimizador y la info del sistema.)*

### 3. Voz — recomendada: edge-tts

```bash
# Opción A: edge-tts (mejor calidad — voz natural mexicana)
pip install edge-tts pygame

# Opción B: gTTS (fallback automático si no está edge-tts)
pip install gtts pygame
```

### 4. Ejecutar la Aplicación

```bash
python main.py
```
> *Al abrir por primera vez, haz clic en **⚙️ Configuración General** en la barra lateral para ingresar tu API Key de OpenRouter.*

---

## ⚡ Optimizador del Sistema (estilo Stacer)

Abre el panel desde el botón **⚡ Optimizador** en la barra lateral.

- **📊 Monitor en vivo** — Barras de CPU, RAM y Disco actualizadas cada 3 s.
- **🧹 Liberar espacio** — Pulsa *Escanear* para ver cuánta basura hay y marca qué limpiar:
  archivos temporales, temporales de Windows, caché de miniaturas, caché de navegadores
  (Chrome/Edge/Brave/Firefox) y papelera de reciclaje.
- **🔥 Procesos** — Lista los procesos que más RAM consumen y permite cerrarlos.

> *Es seguro: solo borro archivos temporales y caché que el sistema regenera solo.*
> *Nunca toco tus documentos.*

---

## ⚙️ Rendimiento y Funciones

Desde **⚙️ Configuración General → Rendimiento y Funciones** puedes activar/desactivar:

| Función | Efecto si la apagas |
|---|---|
| 💬 Respuestas instantáneas | Todo pasa por la IA (más lento, gasta tokens). |
| ⌨️ Streaming letra por letra | La respuesta aparece completa de golpe. |
| 🎬 Animaciones de video | Lune usa imágenes fijas (menos CPU/GPU). |
| ✨ Fondo animado de inicio | Pantalla de bienvenida estática (arranque más ligero). |
| 🖱️ Efectos visuales | Interfaz más sobria. |
| 🔊 Voz automática | Lune no lee en voz alta al iniciar. |

*Todo se guarda en `config.json` y puedes editarlo también a mano.*

---

## 🧠 Memoria y 🛠️ Herramientas

**Control de Memoria:**
- `"recuerda que me llamo Juan"` → Guarda el dato para siempre.
- `/memoria` → Lista todos los recuerdos guardados.
- `/olvida [id]` → Borra un recuerdo específico.
- `/olvida todo` → Formatea la memoria y reinicia tu identidad.

**Comandos Ultrarrápidos de PC (0.1s):**
- `"abre youtube"`, `"ve a netflix"`, `"abre wikipedia.org"` → Abre la web al instante.
- `"busca en youtube gatos"` → Abre directamente los resultados de búsqueda.
- `"lanza la app paint"`, `"abre el programa excel"` → Lanza aplicaciones locales.
- `"estado del pc"`, `"info del sistema"` → Muestra el consumo de CPU y RAM.

**Respuestas instantáneas (sin IA):**
- `"hola"`, `"gracias"`, `"adiós"`, `"¿qué hora es?"`, `"¿qué día es hoy?"`,
  `"cuéntame un chiste"`, `"¿quién eres?"` → Lune responde al momento, con buena onda. 😊

---

## 🤖 Proveedores de IA (Red Neuronal)

| Proveedor | Ícono | Requiere | Notas |
|---|---|---|---|
| **Lune AI (Nube)** | ☁️ | API Key de OpenRouter | Enrutador automático o el modelo que elijas. |
| **Lune AI (Local)** | 🦙 | Ollama instalado | 100% privado, sin conexión, sin costo. |

---

## 🎭 Expresiones, Avatares y Modelos

El sistema carga dinámicamente `.png`/`.mp4` desde `lune_face/` (o desde el
**avatar pack** activo). Lune evalúa su propia respuesta y reacciona con
`happy`, `sad`, `reading`, `thinking`, `typing`, `confused` o `error`.

🎨 **Avatar Packs:** suelta una carpeta en `lune_face/packs/<nombre>/` con tus
propias imágenes/videos y selecciónala en la Configuración. Lo que falte cae al
set por defecto. Roadmap completo (Live2D / VRM estilo Mate-Engine) en
[ROADMAP_MODELOS.md](ROADMAP_MODELOS.md).

---

## 📱 Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ingresa el token en **⚙️ Configuración General**.
3. Pulsa **"🤖 Continuar en Telegram"** para encender el servidor Node.js.

Comandos: `/start`, `/voz`, `/sistema`, `/memoria`, `/olvidar`.

---

## 🔧 Solución de problemas

**Lune tarda en responder / Error de red**
→ Verifica tu API Key de OpenRouter en ⚙️. Si usas Local (🦙), confirma `ollama serve`.

**El Optimizador no muestra datos / procesos**
→ Instala `psutil`: `pip install psutil`.

**Quiero que arranque más rápido**
→ Apaga *Fondo animado de inicio* y *Animaciones de video* en Rendimiento y Funciones.

**No hay voz**
→ Instala `pip install edge-tts pygame` o `pip install gtts pygame`.

**El bot de Telegram no arranca**
→ Entra a `telegram-bot-or` y corre `npm install`.

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v8.0** | Banco de respuestas instantáneas. Optimizador estilo Stacer (limpieza + monitor + procesos). Centro de rendimiento con toggles. Avatar packs (base para modelos VRM/Live2D). Caché de config y sesión HTTP reutilizable. Chips de acceso rápido. |
| v7.8 | Arquitectura Híbrida Nube/Local. Memoria persistente. Herramientas ultrarrápidas. Soporte de video `.mp4`. Configuración por UI. Botón de detención. |
| v6.5 | Expresiones faciales, detección léxica de emociones, voz dinámica con `edge-tts`. |
| v5.0 | Modelos locales, streaming de tokens. |

---

> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
> *Aunque sabes que siempre es un gusto trabajar contigo :)*

> *— Lune* 🌙
