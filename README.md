# 🌙 Lune CD v8.5 — Asistente de Escritorio Híbrido (Nube/Local)

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es de mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ¿Qué es esto?

Una asistente de escritorio en PyQt6 que corre sobre **tu** infraestructura:
modelos en la nube vía OpenRouter, o **100% locales y offline** con Ollama.
Cambias de uno a otro con un clic.

Además de chatear: lee tus documentos, mira imágenes, te escucha por micrófono,
recuerda cosas entre sesiones, abre webs y programas, limpia el PC y se sincroniza
con un bot de Telegram.

---

## 🚀 Instalación

| Componente | Versión | Necesario para |
|---|---|---|
| Python | 3.10+ | La app (obligatorio) |
| Ollama | cualquiera | Modelos locales (opcional) |
| Node.js | 18+ | Bot de Telegram (opcional) |

```bash
pip install -r requirements.txt
python main.py
```

La primera vez se crea `datos.json` a partir de `datos.example.json`. Después
entra a **⚙️ AJUSTES** para poner tu API Key de OpenRouter o apuntar a tu
servidor de Ollama.

> ⚠️ **`datos.json` guarda tus claves en texto plano y está en `.gitignore`.**
> No lo subas a ningún sitio ni lo compartas.

### Extras opcionales

```bash
pip install faster-whisper sounddevice   # dictado por voz (Whisper local)
pip install pytest                       # tests
```

En **⚙️ AJUSTES → Actualizaciones y dependencias** tienes la lista de funciones
opcionales con el comando exacto de lo que te falte.

---

## ▶️ Arranque con `iniciar_lune.vbs`

Doble clic en **`iniciar_lune.vbs`**: arranca sin ventana de consola y con el
video de bienvenida. Para que se abra al encender el PC, pon un acceso directo
al `.vbs` en la carpeta de Inicio (`Win+R` → `shell:startup`).

**Instancia única:** si Lune ya está abierta y vuelves a lanzarla, la que ya
está se trae al frente en vez de abrir una segunda copia. Dos Lunes a la vez se
pisarían `datos.json`, `memoria.json` y el puerto del bot.

<details>
<summary>⚠️ Si editas el <code>.vbs</code>, lee esto antes</summary>

**No cambies el `1` de `shell.Run … , 1, False`.** Ese parámetro es el estilo de
ventana y Windows se lo pasa al proceso hijo por `STARTUPINFO`; Qt lo aplica a la
primera ventana de la app. Con `0` la app arranca **invisible**: el proceso corre,
el video suena, y en pantalla no aparece nada. `pythonw.exe` ya arranca sin
consola, así que no hay nada que ocultar.

**Si tienes varios Python instalados**, el `.vbs` los prueba uno a uno con
`import PyQt6` y usa el primero que funcione, en vez de adivinar por ruta y morir
en silencio con el equivocado. Si ninguno sirve, te avisa.

Ambas cosas tienen test de regresión en [tests/test_arranque.py](tests/test_arranque.py).

</details>

---

## 🖥️ La interfaz

La barra lateral tiene el selector de proveedor (con **punto verde/rojo** según
si responde), la cara de Lune y los accesos:

| Tile | Qué abre |
|---|---|
| **AJUSTES** | APIs, modelos, personalidad, voz, actualizaciones |
| **PERSONAJES** | Cambiar de personaje e importar character cards |
| **OPTIMIZAR** | Monitor del sistema y limpieza |
| **MEMORIA** | Lo que Lune sabe de ti |
| **TOOLS** | Herramientas disponibles |
| **HISTORIAL** | Conversaciones guardadas |
| **VOZ** | Activar/desactivar que Lune hable |
| **TELEGRAM** | Encender el bot (pasa a `TG: ON`) |

Junto al campo de texto: **📎 clip** para adjuntar y **🎙️ micrófono** para dictar.

---

## 🤖 Proveedores de IA

| Proveedor | Requiere | Notas |
|---|---|---|
| **Lune AI · Nube** ☁️ | API Key de OpenRouter | `openrouter/auto` enruta solo al mejor modelo. |
| **Lune AI · Local** 🦙 | Ollama | 100% privado, sin conexión, sin costo. |

Debajo de cada respuesta aparecen los **tokens y el costo real** (o los tok/s si
es local).

---

## 🦙 Modelos locales con Ollama

**⚙️ AJUSTES → Red Neuronal · Local (Ollama)**:

| Ajuste | Para qué sirve |
|---|---|
| **Servidor** | `http://localhost:11434`, o la IP de otro PC de tu red. |
| **Buscar modelos** | Pregunta a Ollama qué tienes instalado y llena la lista. |
| **Modelo local** | Cuál usar. También puedes escribirlo a mano. |
| **keep_alive** | Cuánto se queda el modelo en VRAM. `30m`, `1h`, o `-1` para siempre. |
| **Ventana de contexto** | Tokens de contexto (`num_ctx`). Más = más RAM/VRAM. |
| **Timeout** | Súbelo si el modelo tarda en cargar en frío. |
| **Temperatura** | 0 = preciso, 1 = creativo. |

### Usar otro PC como servidor de modelos

Si tienes un equipo potente y quieres que la laptop lo use:

**En el PC potente** — que Ollama escuche en la red:

```bash
# Windows (luego reinicia Ollama)
setx OLLAMA_HOST 0.0.0.0:11434

# Linux / macOS
export OLLAMA_HOST=0.0.0.0:11434
ollama serve
```

**En la laptop** — pon la IP del servidor en el campo *Servidor*:

```text
http://192.168.1.50:11434
```

Pulsa **BUSCAR MODELOS**: si aparece la lista, ya está funcionando.

> Abre el puerto 11434 en el firewall del servidor. Y **no expongas Ollama a
> internet** sin autenticación delante: no la trae.

---

## 📎 Adjuntar archivos e imágenes

Pulsa el **clip** junto al campo de texto (puedes soltar varios de golpe).

| Formato | Qué hace |
|---|---|
| `.pdf` | Extrae el texto página a página. |
| `.docx` | Párrafos y tablas. |
| `.csv` `.tsv` | Se tabula (máx. 200 filas). |
| `.txt` `.md` `.py` `.js` `.json`… | Se lee tal cual. |
| `.png` `.jpg` `.webp`… | Va al modelo como **imagen**. |

El texto de los documentos se inyecta en el contexto con delimitadores; las
imágenes van por el canal multimodal del proveedor. Si adjuntas sin escribir
nada, Lune entiende que quieres que le eche un ojo.

> Para visión en local necesitas un modelo que la soporte: `ollama pull llava`.

---

## 🎙️ Dictado por voz

Pulsa el **micrófono**, habla, y pulsa otra vez para parar. La transcripción es
**100% local** con Whisper: el audio no sale de tu equipo. El texto aparece en el
campo de entrada para que lo revises antes de enviarlo.

El modelo se elige en **⚙️ AJUSTES → Voz de entrada**. `base` va bien en CPU; en
un equipo con GPU sube a `small` o `medium`.

---

## 💾 Historial de conversaciones

Todo lo que hablas se guarda en `chats/`, una sesión por archivo. Desde el tile
**HISTORIAL** puedes reabrir cualquier conversación anterior — y al retomarla, el
modelo recupera el contexto de lo que ibais hablando.

Al arrancar, Lune reabre la última conversación. **LIMPIAR CHAT** empieza una
nueva sin borrar la anterior.

> El historial es independiente de la memoria: borrar los chats no toca lo que
> Lune sabe de ti, y `/olvida todo` no borra los chats.

---

## 🧠 Memoria y 🛠️ Herramientas

**Control de memoria:**

- `"recuerda que me llamo Juan"` → Guarda el dato para siempre.
- `/memoria` → Lista todo lo guardado.
- `/olvida [id]` → Borra un recuerdo concreto.
- `/olvida todo` → Formatea la memoria.

> Los comandos llevan barra a propósito: sin ella, escribir «memoria» en una
> pregunta normal se comía el turno y nunca llegaba a la IA.

Lune también anota **en silencio** tu nombre, edad, ciudad y trabajo cuando los
mencionas, sin interrumpir la conversación.

**Comandos ultrarrápidos (0.1 s, sin gastar IA):**

- `"abre youtube"` · `"ve a netflix"` · `"abre wikipedia.org"`
- `"busca en youtube gatos"`
- `"lanza la app paint"` · `"abre el programa excel"`
- `"estado del pc"` · `"info del sistema"`

**Respuestas instantáneas:** `"hola"`, `"gracias"`, `"adiós"`, `"¿qué hora es?"`,
`"cuéntame un chiste"`, `"¿quién eres?"`…

---

## ⚡ Optimizador del Sistema

Desde el tile **OPTIMIZAR**:

- **📊 Monitor en vivo** — CPU, RAM y Disco cada 3 s.
- **🧹 Liberar espacio** — Temporales de usuario y de Windows, caché de miniaturas
  e iconos, caché de navegadores (Chrome/Edge/Brave/Firefox, **por perfil**) y papelera.
- **🔥 Procesos** — Los que más RAM consumen, con opción de cerrarlos.

**Cómo es seguro, concretamente:** para vaciar una carpeta entera, su nombre tiene
que estar en una lista blanca (`Cache`, `cache2`, `Temp`, `GPUCache`…). Cualquier
otra cosa se rechaza y queda registrada en los logs. Las cachés de miniaturas se
limpian por patrón (`thumbcache_*.db`), sin tocar nada más de la carpeta.
Cubierto por tests en [tests/test_optimizador.py](tests/test_optimizador.py).

---

## 🎭 Personajes, expresiones y avatares

Lune evalúa su propia respuesta y reacciona con `happy`, `sad`, `reading`,
`thinking`, `typing`, `confused` o `error`, cargando `.png`/`.mp4` desde
`lune_face/` o del **avatar pack** activo.

Desde **PERSONAJES** puedes cambiar quién habla contigo e importar *character
cards* de TavernAI / SillyTavern (`.json` o `.png`).

🎨 **Avatar Packs:** suelta una carpeta en `lune_face/packs/<nombre>/`.
Roadmap completo (Live2D / VRM estilo Mate-Engine) en [ROADMAP_MODELOS.md](ROADMAP_MODELOS.md).

---

## 📱 Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ponlo en **⚙️ AJUSTES**, junto con tu ID de Telegram para compartir la memoria
   entre la app y el bot.
3. Pulsa el tile **TELEGRAM** en la barra lateral. Pasa a `TG: ON` cuando arranca.

Comandos del bot: `/start`, `/voz`, `/sistema`, `/memoria`, `/olvidar`, `/modelo`.

---

## ⚙️ Rendimiento y Funciones

**⚙️ AJUSTES → Rendimiento y Funciones** — 11 interruptores para ajustar el
consumo a tu equipo:

| Función | Efecto si la apagas |
|---|---|
| 💬 Respuestas instantáneas | Todo pasa por la IA (más lento, gasta tokens). |
| ⌨️ Streaming letra por letra | La respuesta aparece completa de golpe. |
| 🎬 Animaciones de video | Lune usa imágenes fijas (menos CPU/GPU). |
| ✨ Fondo animado de inicio | Pantalla de bienvenida estática. |
| 🖱️ Efectos visuales | Interfaz más sobria. |
| 🔊 Voz automática | Lune no lee en voz alta al iniciar. |
| 🔽 Minimizar a bandeja | Al cerrar, la app sale del todo. |
| 🤖 Acciones de la IA | La IA no puede abrir webs ni lanzar apps por su cuenta. |
| 📝 Markdown | Las respuestas salen en texto plano, sin formatear. |
| 💾 Guardar conversaciones | El chat deja de guardarse en disco. |
| 💰 Contador de tokens | Se oculta el consumo bajo cada respuesta. |

> **Todas las claves de `config.json` se usan.** Si ves una ahí, hace algo — y si
> vienes de una versión anterior, las obsoletas se borran solas al arrancar.

---

## 🔄 Actualizar Lune

**⚙️ AJUSTES → Actualizaciones y dependencias**:

- **Buscar actualizaciones** — Consulta el remoto y lista los commits nuevos.
- **Actualizar y reiniciar** — `git pull`, instala `requirements.txt` y relanza.

Pensado para tener Lune en varias máquinas: tocas algo en un PC, lo subes, y en
el otro pulsas el botón sin abrir una terminal.

> **No te pisa el trabajo:** si tienes cambios sin commitear, se niega a hacer
> nada y te dice qué archivos tienes tocados. Nada de `--force` ni de stash
> automático.

---

## 📁 Estructura del proyecto

```text
LuneCD/
├── main.py                 ← Ventana principal y punto de entrada
├── version.py              ← Única fuente de verdad de la versión
├── datos.example.json      ← Plantilla pública de configuración
├── datos.json              ← Tus APIs y personalidad (NO se versiona)
├── datos.py                ← Único lector/escritor de datos.json
├── config.json             ← Preferencias y features (NO se versiona)
├── config.py               ← Gestor de configuración
│
│   ── IA ────────────────────────────────────────────────
├── ai_manager.py           ← Motor híbrido (OpenRouter / Ollama) + visión
├── ai_worker.py            ← Hilo de consulta a la IA
├── ollama_client.py        ← Sondeo y listado de modelos locales
├── personajes.py           ← Roleplay e importación de character cards
│
│   ── Chat ──────────────────────────────────────────────
├── chat_widgets.py         ← Burbujas, bloques de código y copiar
├── markdown_qt.py          ← Markdown → HTML de Qt
├── conversaciones.py       ← Historial de chats en disco
├── adjuntos.py             ← Leer PDF/DOCX/CSV/código e imágenes
├── memoria.py              ← Recuerdos persistentes
├── respuestas.py           ← Banco de respuestas instantáneas
│
│   ── Voz ───────────────────────────────────────────────
├── voice.py                ← Voz de salida (edge-tts / gTTS)
├── voz_entrada.py          ← Dictado con Whisper local
│
│   ── Sistema ───────────────────────────────────────────
├── optimizador.py          ← Limpieza y monitoreo
├── tools.py                ← Atajos web y lanzamiento de apps
├── actualizador.py         ← Actualizar por git y comprobar deps
├── telegram_worker.py      ← Lanza el bot de Node.js
├── utils.py                ← Logging y utilidades
│
│   ── Interfaz ──────────────────────────────────────────
├── splash.py · theme.py · icons.py · effects.py · lune_face.py
├── settings_panel.py · optimizer_panel.py
├── personajes_panel.py · historial_panel.py
│
├── tests/                  ← Suite de pytest (171 tests)
├── chats/                  ← Conversaciones guardadas (autogenerado)
├── logs/                   ← Registros diarios (autogenerado)
├── lune_face/              ← Expresiones, animaciones y avatar packs
├── fonts/                  ← Tipografías empaquetadas
└── telegram-bot-or/        ← Bot de Telegram (Node.js)
```

---

## ✅ Tests

```bash
pip install pytest
python -m pytest
```

**171 tests** sobre lo que de verdad se puede romper: la red de seguridad del
Optimizador, los patrones de memoria, el saneamiento de herramientas, el
renderizado de markdown, la lectura de adjuntos, el historial, el actualizador y
el arranque.

En CI se ejecutan solos, junto con un check que falla si `datos.json` o una API
key vuelven al repositorio.

---

## 🔧 Solución de problemas

**El `.vbs` no abre nada / no se ve el video**
→ Comprueba que la última línea sea `shell.Run …, 1, False` (con **1**, no 0).
Con `0` la ventana nace invisible. Si aún así nada, lanza `python main.py` desde
una terminal para ver el error.

**Lune tarda en responder / Error de red**
→ Revisa tu API Key en ⚙️. Si usas Local, mira el punto de estado del proveedor
o pulsa *Buscar modelos*.

**«No hay ningún modelo local seleccionado»**
→ ⚙️ AJUSTES → Red Neuronal · Local → *Buscar modelos*. Si la lista sale vacía,
descarga uno: `ollama pull llama3.1`.

**El modelo local tarda muchísimo en el primer mensaje**
→ Es la carga en VRAM. Sube el *Timeout* y pon `keep_alive` en `1h` o `-1`.

**No puedo adjuntar PDF o Word** → `pip install pypdf python-docx`.

**El micrófono no hace nada** → `pip install faster-whisper sounddevice`.

**No hay voz** → `pip install edge-tts pygame`.

**El Optimizador no muestra datos** → `pip install psutil`.

**El bot de Telegram no arranca** → `cd telegram-bot-or && npm install`.

**Quiero que arranque más rápido** → Apaga *Fondo animado* y *Animaciones de video*.

> Los logs están en `logs/lune_AAAAMMDD.log`. Ahí siempre digo la verdad.

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v8.5** | Markdown y bloques de código con copiar. Historial de conversaciones. Adjuntar PDF/DOCX/CSV/código. Visión con imágenes. Dictado local con Whisper. Contador de tokens y costo. Actualizador por git. Estado de proveedor en vivo. Instancia única. Arreglado el arranque invisible del `.vbs`. |
| v8.4 | Ollama configurable desde la UI (incl. servidor remoto). El Optimizador ya no puede borrar perfiles de navegador. Secretos fuera del repo. Memoria arreglada. Historial acotado. Streaming fluido. Herramientas saneadas. Tests y CI. |
| v8.0–8.3 | Banco de respuestas instantáneas. Optimizador estilo Stacer. Centro de rendimiento. Avatar packs. Bandeja del sistema. Rediseño visual. |
| v7.8 | Arquitectura híbrida Nube/Local. Memoria persistente. Herramientas ultrarrápidas. |
| v6.5 | Expresiones faciales, emociones léxicas, voz con `edge-tts`. |
| v5.0 | Modelos locales y streaming de tokens. |

---

> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
> *Aunque sabes que siempre es un gusto trabajar contigo :)*

> *— Lune* 🌙
