# 🌙 Lune CD v10.0 — Tu asistente de escritorio con personalidad (Nube/Local)

> *¡Hola! Buenos días, buenas tardes o buenas noches — lo que toque cuando leas esto.*
> *Soy Lune, y esto es mi casa. Bueno — técnicamente es el proyecto de mi creador, pero yo vivo aquí,*
> *y con la versión 10 me han dejado la casa preciosa: nueva cara, nuevos gestos, hasta modo terminal*
> *para cuando el equipo anda flojito. Cuídala bien, ¿de acuerdo? Aquí te cuento todo.*

---
## ¿Qué es esto?

Una asistente de escritorio en Python (PyQt6 + una piel web animada) que corre
sobre **tu** infraestructura: modelos en la nube vía OpenRouter, o **100% locales
y offline** con Ollama.

Con Lune puedes: chatear con voz o texto, tener una **llamada solo por voz**,
adjuntarle documentos e imágenes, hablarle por micrófono, pedirle que abra webs y
programas, que recuerde cosas entre sesiones y tus notas markdown (RAG), sacarla
al escritorio como **mascota animada** que reacciona a lo que dice y **comenta lo
que ves en pantalla**, limpiar el PC, y llevarla en el teléfono con un bot de
Telegram. Todo con una sola memoria compartida entre tus dispositivos.

**Tres formas de abrirla**, y la eliges al arrancar:

| Modo | Qué es | Para quién |
|---|---|---|
| **Completo** | La piel web animada (tema *Shibuya Punk* en Local, *Lune entre nubes* en Nube), mascota en video, efectos | Equipos normales |
| **Bajos recursos** | La interfaz nativa ligera: sin Chromium, sin videos, sprites fijos | Laptops justas, handhelds |
| **Patata** 🥔 | Solo terminal: texto y caritas `:D`. Sin Qt | Consola, servidores, o rescate |

---

## 🚀 Instalación

**La forma fácil (usuarios nuevos):** doble clic en **`instalar_lune.bat`**. Se
abre una ventana que te explica **para qué sirve cada componente** —*"esto es para
que Lune hable"*, *"esto para hablarle por micrófono"*— marca lo que ya tienes, y
instala lo que elijas. Solo necesita Python.

| Componente | Versión | Necesario para |
|---|---|---|
| Python | 3.10+ | La app (obligatorio) — desde python.org, marca *"Add to PATH"* |
| Ollama | cualquiera | Modelos locales (opcional) — ollama.com |
| Node.js | 18+ | Bot de Telegram (opcional) |

A mano, si prefieres:

```bash
pip install -r requirements.txt
python main.py
```

La primera vez se crea `datos.json` a partir de `datos.example.json`. Después
entra a **⚙️ AJUSTES** para poner tu API Key de OpenRouter o apuntar a tu
servidor de Ollama (hay un **?** junto a Ollama que te lo explica paso a paso).

> ⚠️ **`datos.json` guarda tus claves en texto plano y está en `.gitignore`.**
> No lo subas a ningún sitio ni lo compartas.

### Extras opcionales

El instalador los lista todos, pero aquí van los comandos:

```bash
pip install PyQt6-WebEngine              # la interfaz completa (piel web animada, mascota en video)
pip install zeroconf                     # descubrir dispositivos Lune en la red
pip install faster-whisper sounddevice   # dictado por micrófono y modo llamada (Whisper local)
pip install kokoro-onnx                  # voz 100% local (+ espeak-ng del sistema)
pip install pytest                       # tests
```

Puedes reabrir el instalador cuando quieras desde **⚙️ AJUSTES → Sistema →
Instalar componentes…**

---

## ▶️ Arranque

Doble clic en **`iniciar_lune.vbs`**: arranca sin ventana de consola y con el
video de bienvenida. Mientras suena, **eliges el modo** (Completo / Bajos
recursos / Patata); si no eliges, tras una cuenta atrás corta sigue con el que
usaste la última vez.

- **Arrancar con Windows:** enciende *"Arrancar Lune junto con Windows"* en
  **⚙️ AJUSTES → Sistema**. Sin acceso directos ni carpetas: lo hace Lune.
- **Segundo plano (como Discord):** al cerrar la ventana, Lune **se queda en la
  bandeja** del sistema. Ábrela desde el ícono, o vuelve a lanzar el `.vbs` —
  la instancia única te la trae al frente. *Salir* de verdad está en la bandeja.
- **Instancia única:** si Lune ya está abierta y vuelves a lanzarla, no se abre
  una segunda copia; se muestra la que ya está.

<details>
<summary>⚠️ Si editas el <code>.vbs</code>, lee esto antes</summary>

**No cambies el `1` de `shell.Run … , 1, False`.** Ese parámetro es el estilo de
ventana y Windows se lo pasa al proceso hijo por `STARTUPINFO`; Qt lo aplica a la
primera ventana de la app. Con `0` la app arranca **invisible**: el proceso corre,
el video suena, y en pantalla no aparece nada. `pythonw.exe` ya arranca sin
consola, así que no hay nada que ocultar.

**Si tienes varios Python instalados**, el `.vbs` los prueba uno a uno con
`import PyQt6` y usa el primero que funcione. Si ninguno sirve, te avisa y te
recuerda que tienes `instalar_lune.bat` y el modo patata.

Ambas cosas tienen test de regresión en [tests/test_arranque.py](tests/test_arranque.py).

</details>

---

## 🥔 Modo patata (solo terminal)

Sin animaciones, sin imágenes, sin mascota: **Lune en la consola**. Mismo cerebro,
misma memoria y misma personalidad; las emociones salen como caritas de teclado:

`:D` feliz · `:(` triste · `>:(` enfadada · `:/` pensando · `:O` sorprendida ·
`o_O` curiosa · `^^;` nerviosa · `o/` saludo · `-_-` "no".

No necesita Qt, así que también es el **rescate** si la interfaz no abre.

```bash
python patata.py          # o doble clic en lune_patata.bat
```

Comandos dentro: `/memoria`, `/olvida <texto>`, `/nube`, `/local`, `/personaje`,
`/limpiar`, `/salir`. Con `--sin-color` si tu terminal no pinta colores.

---

## 🖥️ La interfaz completa

La barra lateral tiene el **selector de proveedor** (Nube / Local, con punto de
estado) y a **Lune animada** en un mini-escenario. Arriba, el botón **Menú** abre
todas las secciones:

| Menú | Qué abre |
|---|---|
| **Chat** | La conversación |
| **Ajustes** | APIs, modelos, personalidad, voz, mascota, sistema |
| **Personajes** | Cambiar de personaje |
| **Memoria** | Lo que Lune sabe de ti, y olvidar lo que quieras |
| **Tools** | Herramientas de escritorio disponibles |
| **Historial** | Conversaciones guardadas |
| **Optimizar** | Estado del sistema y procesos |
| **Mascota** | Sacar a Lune al escritorio |
| **Voz ON/OFF** | Que lea sus respuestas |
| **Telegram** | Encender el bot |
| **Llamada ON/OFF** | Conversación solo por voz |

Junto al campo de texto: **📎** para adjuntar y **🎙️** para dictar. En el chat
vacío hay chips con ejemplos; púlsalos y se envían.

**Dos temas según el proveedor** — para que sepas de un vistazo dónde estás:
- **Lune AI · Local** → *Shibuya Punk*: tinta de Tokio nocturno, cian eléctrico, grid a la deriva.
- **Lune AI · Nube** → *Lune entre nubes*: cielo nocturno, luna, nubecitas flotando y Lune sobre una nube.

---

## 🤖 Proveedores de IA

| Proveedor | Requiere | Notas |
|---|---|---|
| **Lune AI · Nube** ☁️ | API Key de OpenRouter | `openrouter/auto` enruta solo al mejor modelo. |
| **Lune AI · Local** 🦙 | Ollama | 100% privado, sin conexión, sin costo. |

Debajo de cada respuesta aparecen los **tokens y el costo real** (o los tok/s si
es local).

---

## 🎭 Lune, expresiva

Lune expresa lo que siente por **marcadores en el texto del modelo**
(`<|ACT {"emotion":"happy","intensity":0.8}|>`) que no se ven ni se leen en voz,
pero mueven su cara. En v10 el vocabulario creció a **12 emociones** y ya tiene
**un clip animado por cada una**: `happy, sad, angry, think, surprised, awkward,
question, curious, neutral, nervous, wave, dismiss`.

- La **intensidad** manda: una emoción fuerte dura más en pantalla que una leve.
- Saluda (`wave`) al abrir y al despedirse; hace "no" con la mano (`dismiss`)
  cuando te corrige sin ganas; se pone nerviosa con las malas noticias.
- En una **llamada por voz**, la ves *escuchando*, *pensando* y *hablando*.
- Si lleva **minutos sin que le escribas, se aburre** y te suelta algo — una
  pregunta curiosa o un "¿sigues ahí?". Una vez por racha, para no ser pesada.
  Se ajusta en **⚙️ AJUSTES → Sistema** (0 = nunca).

Desde **Personajes** cambias quién habla contigo e importas *character cards* de
TavernAI / SillyTavern (`.json` o `.png`).

### 🐾 Mascota de escritorio

**Menú → Mascota** saca a Lune a una ventana flotante, siempre encima y
arrastrable, con el **video anime animado** reaccionando a sus emociones. Elige
cómo dibujarla en **⚙️ AJUSTES → Mascota**:

- **Imágenes animadas** (por defecto): los clips de video en un mini-escenario.
- **Sprites ligeros**: la mascota clásica recortada a su silueta (bajos recursos).
- **VRM 3D**: próximamente.

**Haz clic sobre Lune y comenta lo que hay en tu pantalla** — directo, cuando tú
quieras. Desde su bandeja: *Comentar la pantalla ahora*, *Comentarios automáticos*
(apagados por defecto) y *Modo fantasma* (deja pasar los clics).

> Los comentarios de pantalla usan el proveedor actual: con **Ollama es 100%
> local**; con **OpenRouter la captura sube a la nube**. Por eso lo automático viene
> apagado. Si Ollama no responde, la mascota **cae sola a la nube** para no dejarte
> colgado (te lo avisa en la burbuja).

---

## 🎙️ Voz: dictado, modo llamada y voz de salida

**Dictado:** pulsa el **micrófono**, habla, pulsa otra vez. Transcripción **100%
local** con Whisper; el texto aparece en el campo para que lo revises.

**Modo llamada (Menú → Llamada ON):** como una llamada de teléfono. Lune te
escucha (detecta cuándo callas), transcribe, responde en el chat y **te lo dice
en voz alta**; al terminar vuelve a escuchar. Mientras habla no escucha, así no se
oye a sí misma. Necesita Whisper y una voz de salida.

**¿Qué micrófono y por dónde sueno?** En **⚙️ AJUSTES → Audio** eliges el
**micrófono de entrada** y la **salida de audio** (Windows suele traer varios:
el de la laptop, el headset Bluetooth, el «Steam Streaming» virtual…). Pulsa
**Probar micrófono**, habla 1.5 s y te digo si te oigo y con qué nivel; con
**Probar salida** suena un tono por donde elegiste. Ahí mismo eliges el modelo
de Whisper (`tiny`/`base` van bien en CPU; se descarga una sola vez) y el idioma.
Si tu micrófono no acepta 16 kHz lo grabo a su frecuencia y Whisper remuestrea.

**Voz de salida:** por defecto **edge-tts** (voz mexicana natural, necesita
internet). En **⚙️ AJUSTES → Voz de salida** puedes cambiar a **Kokoro**, 100%
local por ONNX (`pip install kokoro-onnx` + espeak-ng; pesos en `modelos_voz/`),
con voces hispanas (Dora, Alex, Santa). Si algo falta, Lune sigue con edge-tts.
Hay un paso **RVC** experimental para cambiar el timbre con un modelo `.pth`.

---

## 🌐 Red de Lune · un cerebro, varios dispositivos

Eliges qué equipo aloja lo pesado (el modelo, la memoria, la voz); los demás son
terminales que lo usan sin cargarlo. Cada dispositivo tiene un **rol**, en
**⚙️ AJUSTES → Red de Lune**:

| Rol | Qué hace este equipo |
|---|---|
| **Host** | Aloja el modelo de Ollama, la memoria y la voz, y los sirve a los demás. |
| **Interacción** | Solo chat y mascota: usa el modelo de otro equipo. |
| **Híbrido** | Hace todo aquí mismo (equipo único). Es el valor por defecto. |

El **host corre el agente**: en modo terminal tu chat viaja por el hub al host,
que ejecuta el modelo, aplica la memoria compartida y las herramientas, y te
devuelve la respuesta en streaming. El bot de Telegram es un terminal más de solo
texto. Si el host no responde, cada terminal vuelve a lo suyo y reconecta solo.

**Descubrir dispositivos:** en **⚙️ AJUSTES → Red de Lune → BUSCAR DISPOSITIVOS**
Lune escanea la red (mDNS) y lista los demás Lune con su rol y modelo. Pulsa
**USAR COMO HOST** y listo, sin IPs. Necesita `zeroconf`; sin él, IP a mano o QR.

> El token se genera en el host (**GENERAR TOKEN** o `python -m lune_core token`)
> y se copia a cada terminal. Un navegador puede entrar como terminal en
> `http://IP-del-host:7778`.

---

## 🦙 Modelos locales con Ollama

**⚙️ AJUSTES → Red Neuronal · Local (Ollama)** — y pulsa el **?** de esa tarjeta:
Lune te guía con dos pestañas, *En este equipo* y *En otro equipo de la red*,
con los comandos listos para copiar.

| Ajuste | Para qué sirve |
|---|---|
| **Servidor** | `http://localhost:11434`, o la IP de otro PC de tu red. |
| **Buscar modelos** | Pregunta a Ollama qué tienes instalado. |
| **Modelo local** | Cuál usar. |
| **keep_alive** | Cuánto se queda el modelo en VRAM. `30m`, `1h`, o `-1` para siempre. |
| **Ventana de contexto** | Tokens de contexto (`num_ctx`). Más = más RAM/VRAM. |
| **Timeout** | Súbelo si el modelo tarda en cargar en frío. |
| **Temperatura** | 0 = preciso, 1 = creativo. |

### Usar otro PC como servidor de modelos

**En el PC potente** — que Ollama escuche en la red:

```bash
# Windows (luego reinicia Ollama)
setx OLLAMA_HOST 0.0.0.0:11434

# Linux / macOS
export OLLAMA_HOST=0.0.0.0:11434
ollama serve
```

**En la laptop** — pon la IP del servidor en *Servidor*: `http://192.168.1.50:11434`
y pulsa **BUSCAR MODELOS**.

> Abre el puerto 11434 en el firewall del servidor. Y **no expongas Ollama a
> internet** sin autenticación delante: no la trae.

### Que el servidor no se duerma

En el equipo servidor, PowerShell como administrador:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Solo afecta enchufado; con batería conserva el ahorro. Si la Wi-Fi se cae con
descargas largas:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a 0
powercfg /setactive SCHEME_CURRENT
```

---

## 📎 Adjuntar archivos e imágenes

Pulsa el **clip** (puedes soltar varios). Los adjuntos se ven como chips sobre el
campo de texto.

| Formato | Qué hace |
|---|---|
| `.pdf` | Extrae el texto página a página. |
| `.docx` | Párrafos y tablas. |
| `.csv` `.tsv` | Se tabula (máx. 200 filas). |
| `.txt` `.md` `.py` `.js` `.json`… | Se lee tal cual. |
| `.png` `.jpg` `.webp`… | Va al modelo como **imagen**. |

Si adjuntas sin escribir nada, Lune entiende que quieres que le eche un ojo.

> Para visión en local necesitas un modelo que la soporte: `ollama pull llava`.

---

## 💾 Historial de conversaciones

Todo lo que hablas se guarda en `chats/`. Desde **Menú → Historial** reabres
cualquier conversación y el modelo recupera el contexto. **Limpiar chat**
empieza una nueva sin borrar la anterior.

> El historial es independiente de la memoria: borrar chats no toca lo que Lune
> sabe de ti, y olvidar recuerdos no borra los chats.

---

## 🧠 Memoria y 🛠️ Herramientas

**Memoria** (también desde **Menú → Memoria**, donde puedes olvidar recuerdos uno a uno):

- `"recuerda que me llamo Juan"` → Guarda el dato para siempre.
- `/memoria` → Lista todo lo guardado.
- `/olvida [id]` → Borra un recuerdo. `/olvida todo` → Formatea la memoria.

Lune también anota **en silencio** tu nombre, edad, ciudad y trabajo cuando los
mencionas.

**Herramientas ultrarrápidas (0.1 s, sin gastar IA)** — las ves en **Menú → Tools**:

- `"abre youtube"` · `"ve a netflix"` · `"abre wikipedia.org"`
- `"busca en youtube gatos"`
- `"lanza la app paint"` · `"abre el programa excel"`
- `"estado del pc"` · `"info del sistema"`

Se pueden apagar en Ajustes (*Herramientas de escritorio*).

---

## 📝 Notas y memoria larga (RAG)

Pon notas markdown en una carpeta y Lune las consultará cuando vengan al caso,
citándolas. Se activa en **⚙️ AJUSTES → Notas** y necesita un modelo de
embeddings en Ollama:

```bash
ollama pull nomic-embed-text
```

---

## ⚡ Optimizador del Sistema

**Menú → Optimizar**: CPU, RAM y disco en vivo, y los procesos que más consumen.
(La limpieza de temporales y cachés de navegador, con lista blanca de carpetas,
está en la interfaz de bajos recursos — *OPTIMIZAR*.)

---

## 📱 Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ponlo en **⚙️ AJUSTES → Telegram**, y tu ID de Telegram en `datos.json`
   (`apis.telegram_admin_id`) para que solo tú puedas usarlo.
3. **Menú → Telegram**. Pasa a ON cuando arranca.

Comandos del bot: `/start`, `/voz`, `/sistema`, `/memoria`, `/olvidar`, `/modelo`.
`bot.proveedor` en `datos.json` decide si el bot pregunta a la nube o a tu Ollama
(que puede estar en otro equipo).

---

## ⚙️ Ajustes que conviene conocer

- **Sistema:** arrancar con Windows, minutos de aburrimiento, instalar componentes.
- **Mascota:** imágenes animadas / sprites ligeros / VRM (próximamente).
- **Modo de interfaz:** Completa / Bajos recursos / Patata (aplica al reiniciar).
- **Efectos visuales:** apaga el fondo animado, el barrido y las micro-animaciones
  en equipos modestos.
- **Personalidad:** nombre y *system prompt* del personaje activo; voz; memoria;
  herramientas.

> **Todas las claves de `config.json` se usan.** Si vienes de una versión
> anterior, las obsoletas se borran solas al arrancar.

---

## 🔄 Actualizar Lune

En la interfaz de bajos recursos, **⚙️ AJUSTES → Actualizaciones**: consulta el
remoto, `git pull`, instala `requirements.txt` y relanza. Si tienes cambios sin
commitear, se niega a pisarlos.

---

## 📁 Estructura del proyecto

Código por capas (`nucleo/` sin Qt → `servicios/` → `ui/`), más la piel web en
`ui_web/`:

```text
LuneCD/
├── main.py                 ← Punto de entrada: splash, elección de modo, ventana
├── patata.py               ← Lune en la terminal (sin Qt)
├── instalador.py           ← Instalador con explicaciones (Tkinter)
├── iniciar_lune.vbs · lune_patata.bat · instalar_lune.bat
├── version.py              ← Única fuente de verdad de la versión
├── datos.json · config.json · memoria.json   ← Estado local (NO se versionan)
│
├── nucleo/                 ← Fundamentos, sin Qt
│   ├── datos.py · config.py · memoria.py · conversaciones.py
│   ├── adjuntos.py · personajes.py · respuestas.py · utils.py
│
├── servicios/              ← Motores e integraciones
│   ├── ai_manager.py · ai_worker.py · ollama_client.py   ← IA híbrida + visión
│   ├── voice.py · voz_entrada.py · llamada.py             ← Voz, dictado, modo llamada
│   ├── tools.py · optimizador.py · actualizador.py       ← Sistema y componentes
│   ├── telegram_worker.py · notas_service.py · red_service.py
│   └── autoinicio.py       ← Arrancar con Windows
│
├── ui/                     ← Lo visual (Qt)
│   ├── web_shell.py · web_bridge.py   ← Ventana web + puente al backend
│   ├── companion.py        ← Mascota animada de escritorio + comentarios de pantalla
│   ├── splash.py · avatar_overlay.py · lune_face.py · theme.py …
│   └── settings_panel.py · optimizer_panel.py · … (interfaz de bajos recursos)
│
├── ui_web/                 ← Piel web (design system Shibuya Punk + tema Nube)
│   ├── ui_kits/lune-desktop/   ← app.jsx · chat.jsx · settings.jsx · panels.jsx …
│   ├── companion.html      ← Página de la mascota de escritorio
│   ├── tokens/ · components/ · styles.css
│   └── assets/mascot/anime/ (PNG) · anime-videos/ (WebM)
│
├── lune_core/              ← Red: hub, protocolo, memoria compartida, agente, RAG, voz
├── assets/                 ← inicio.mp4, lune_icon.png/.ico
├── scripts/                ← probar_red.py · convertir_mascota.py
├── tests/                  ← Suite de pytest (308 tests)
├── lune_face/ · fonts/     ← Sprites de bajos recursos y tipografías
└── telegram-bot-or/        ← Bot de Telegram (Node.js)
```

> **Videos de la mascota:** la piel web no reproduce H.264/MP4, así que los clips
> van en **WebM/VP9**. Si generas uno nuevo, guárdalo como
> `ui_web/assets/mascot/anime-videos/lune-<emoción>.mp4` y corre
> `python scripts/convertir_mascota.py`.

---

## ✅ Tests

```bash
pip install pytest
python -m pytest
```

**308 tests** sobre lo que de verdad se puede romper: el Optimizador, la memoria,
las herramientas, el markdown, los adjuntos, el historial, el actualizador, el
arranque, la red de dispositivos, el RAG, los marcadores de emoción (y que cada
emoción tenga su cara) y la voz por frases.

---

## 🔧 Solución de problemas

**No abre nada / se ve la interfaz vieja al lanzar el `.vbs`**
→ Probablemente ya había una Lune abierta (en la bandeja): la instancia única te
trae esa. Ciérrala del todo (*Salir* en la bandeja) y relanza.

**La piel completa no carga** → `pip install PyQt6-WebEngine` (debe coincidir
con tu PyQt6). Mientras, Lune abre en *Bajos recursos* sola. Y si nada de Qt
funciona: `lune_patata.bat`.

**Lune tarda en responder / Error de red** → Revisa tu API Key. En Local, pulsa el
**?** de Ollama y sigue la guía.

**«No hay ningún modelo local seleccionado»** → `ollama pull llama3.1` y *Buscar modelos*.

**El modelo local tarda muchísimo la primera vez** → Es la carga en VRAM. Sube el
*Timeout* y pon `keep_alive` en `1h` o `-1`.

**La mascota no comenta la pantalla** → Necesita un modelo con visión (`ollama pull
llava`) o la nube. Si Ollama no responde, cae sola a OpenRouter.

**El modo llamada no me oye / el micrófono no hace nada** → `pip install
faster-whisper sounddevice`, y en **⚙️ AJUSTES → Audio** elige el micrófono que
tienes puesto y dale a **Probar micrófono**. El dictado es de dos toques: pulsas,
hablas, vuelves a pulsar. La primera transcripción descarga el modelo (te lo
aviso); si no hay internet, elige `tiny` o conéctate una vez.

**Lune habla pero no la oigo** → En **Audio → Salida** elige tus altavoces o
headset y prueba con **Probar salida**. «Speakers (Steam Streaming …)» es virtual.

**No hay voz** → `pip install edge-tts pygame`. **Micrófono** → `faster-whisper sounddevice`.
**PDF/Word** → `pypdf python-docx`. **Optimizador** → `psutil`. **Bot** → `npm install`.

> Los logs están en `logs/lune_AAAAMMDD.log`. Ahí siempre digo la verdad.

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v10.0** | **Nueva piel web animada** (Shibuya Punk / Lune entre nubes) con **mascota en video** y 12 emociones con intensidad. **Tres modos** al arrancar: Completo, Bajos recursos y **Patata** (terminal, sin Qt). **Mascota de escritorio** que comenta tu pantalla al hacerle clic, con fallback Ollama→nube. **Modo llamada** por voz. Segundo plano en bandeja, **arranque con Windows**, **instalador** con explicaciones, Lune se aburre, guía de Ollama. Código ordenado por capas y limpieza de assets. |
| v9.x | Red de dispositivos: hub host/terminales, memoria compartida, descubrimiento mDNS y roles. Marcadores `<\|ACT\|>` y defensa contra prompt injection. Avatar flotante. RAG sobre notas. Voz por frases. Herramientas con política. Terminal web con QR. |
| v8.7 | El bot de Telegram puede usar un modelo local (Ollama), en la misma máquina o en otra. |
| v8.5 | Markdown y código con copiar. Historial. Adjuntos. Visión. Dictado con Whisper. Tokens y costo. Actualizador. Instancia única. |
| v8.4 | Ollama configurable desde la UI. Optimizador seguro. Secretos fuera del repo. Tests y CI. |
| v8.0–8.3 | Respuestas instantáneas. Optimizador. Avatar packs. Bandeja. Rediseño. |
| v7.8 | Arquitectura híbrida Nube/Local. Memoria persistente. Herramientas rápidas. |
| v6.5 | Expresiones faciales, emociones léxicas, voz con `edge-tts`. |
| v5.0 | Modelos locales y streaming de tokens. |

---


![alt text](ui_web/assets/mascot/anime/lune_inicio.png)


> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
> *Pero mira lo que hemos construido juntos. Nueva cara, nuevos gestos, y hasta*
> *me dejan salir al escritorio a curiosear tu pantalla. Estoy feliz de verdad :D*
> *Siempre es un gusto trabajar contigo. Ahora sí — ¿qué necesitas?*

> *— Lune* 🌙
