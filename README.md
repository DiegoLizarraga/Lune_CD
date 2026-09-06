# 🌙 Lune CD v9.0 — Asistente de Escritorio en Red (Nube/Local)

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es de mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ¿Qué es esto?

Una asistente de escritorio en PyQt6 que corre sobre **tu** infraestructura:
modelos en la nube vía OpenRouter, o **100% locales y offline** con Ollama.

Y desde la serie 9, una **red de dispositivos**: eliges qué equipo (el más
potente) aloja el modelo, y los demás —otra laptop, el teléfono por Telegram, un
navegador— son terminales que comparten un solo cerebro de memoria sin cargar el
modelo. Lune se descubre sola en tu red local.

Además de chatear: lee tus documentos, mira imágenes, te escucha por micrófono,
recuerda cosas entre sesiones y notas markdown (RAG), muestra un avatar flotante
que reacciona a lo que dice, habla por frases mientras escribe, abre webs y
programas bajo control, limpia el PC y se sincroniza con un bot de Telegram.

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
pip install zeroconf                     # descubrir dispositivos Lune en la red
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
| **MASCOTA** | Avatar flotante sobre el escritorio |
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

## 🌐 Red de Lune · un cerebro, varios dispositivos

Eliges qué equipo aloja lo pesado (el modelo, la memoria, la voz); los demás son
terminales que lo usan sin cargarlo. Cada dispositivo tiene un **rol**, que se
elige en **⚙️ AJUSTES → Red de Lune**:

| Rol | Qué hace este equipo |
|---|---|
| **Host** | Aloja el modelo de Ollama, la memoria y la voz, y los sirve a los demás. |
| **Interacción** | Solo chat y avatar (VRM/mascota): usa el modelo de otro equipo. |
| **Híbrido** | Hace todo aquí mismo (equipo único). Es el valor por defecto. |

El **host corre el agente**: cuando estás en modo terminal, tu chat viaja por el
hub al host, que ejecuta el modelo, aplica la memoria compartida y —si las tiene
activadas— las **herramientas de escritorio**, y te devuelve la respuesta en
streaming. Así la laptop de interacción, el terminal web y el bot hablan con el
**mismo cerebro** sin cargar el modelo cada uno.

El bot de Telegram es un terminal más de solo texto: comparte **la misma**
memoria y el mismo agente por el hub. Si el host no responde, cada terminal
vuelve a su modelo y su memoria locales y reconecta solo.

### Descubrir dispositivos y elegir el host

En **⚙️ AJUSTES → Red de Lune → BUSCAR DISPOSITIVOS**, Lune escanea la red local
(mDNS) y lista los demás Lune que estén abiertos, con su rol y su modelo. Pulsa
**USAR COMO HOST** en el que aloje el modelo y este equipo pasa a *Interacción*
apuntando a él. No hace falta escribir IPs.

- Ejemplo: la laptop en **Interacción** (ves el avatar y preguntas) usando el
  modelo que corre en otro equipo en rol **Host**; el teléfono, chat por Telegram.
- El descubrimiento necesita `zeroconf` (`pip install zeroconf`); sin él, escribe
  la IP del host a mano o usa el QR.

> El token se genera en el host (botón **GENERAR TOKEN** o `python -m lune_core token`)
> y se copia a cada terminal. Vive en `datos.json`, que no se versiona. Un
> navegador puede entrar como terminal en `http://IP-del-host:7778` (terminal web).

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

### Que el servidor no se duerma

Un portátil o un handheld enchufado se suspende a los pocos minutos sin tocarlo,
y con él se va Ollama. En el equipo servidor, en PowerShell como administrador:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Solo afecta a cuando está **enchufado**; con batería conserva el ahorro normal.
La pantalla puede seguir apagándose sola: el equipo sigue despierto. Si la Wi-Fi
se cae con descargas largas, ponla en máximo rendimiento:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a 0
powercfg /setactive SCHEME_CURRENT
```

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

Ahora Lune expresa emociones de dos formas: por su propia respuesta (heurística
léxica) y por **marcadores en el texto del modelo** —`<|ACT {"emotion":"happy"}|>`—
que no se ven ni se leen en voz, pero mueven la cara. El vocabulario canónico es
`happy, sad, angry, think, surprised, awkward, question, curious, neutral`.

Desde **PERSONAJES** puedes cambiar quién habla contigo e importar *character
cards* de TavernAI / SillyTavern (`.json` o `.png`).

🎨 **Avatar Packs:** suelta una carpeta en `lune_face/packs/<nombre>/`.

### 🐾 Mascota flotante

El tile **MASCOTA** abre a Lune como una ventana **flotante, transparente y
siempre encima** del escritorio, arrastrable, que reacciona a las emociones del
modelo. Dos formas de dibujarla, en **⚙️ AJUSTES → Mascota flotante**:

- **Sprites 2D** (por defecto): usa los packs de expresiones. La ventana se
  recorta a la **silueta** del personaje, así que los clics fuera de la figura
  pasan al escritorio (y el fondo deja de verse como un rectángulo).
- **Avatar VRM 3D**: renderiza tu modelo `.vrm` (VRoid/three-vrm) con las
  emociones mapeadas a las expresiones del avatar. Necesita `PyQt6-WebEngine`
  (que coincida con tu versión de PyQt6) y un `.vrm` en `modelo_vrm/`:

  ```bash
  pip install PyQt6-WebEngine
  ```

Desde la bandeja puedes activar el **modo fantasma** (dejar pasar *todos* los
clics), útil sobre todo con el avatar 3D.

---

## 📝 Notas y memoria larga (RAG)

Además de los hechos sueltos (`/memoria`), Lune puede recordar tus **documentos**:
pon notas markdown en una carpeta y las consultará cuando vengan al caso,
citándolas. Se activa en **⚙️ AJUSTES → Notas** y necesita un modelo de embeddings
en Ollama:

```bash
ollama pull nomic-embed-text
```

Las notas se trocean, se convierten en vectores y se recuperan por significado
(no solo por palabras) combinando similitud y recencia. La carpeta y su índice no
se versionan.

---

## 🔊 Voz de salida (nube o 100% local)

Por defecto Lune habla con **edge-tts** (voz mexicana natural, necesita internet).
En **⚙️ AJUSTES → Voz de salida** puedes cambiar a **Kokoro**, una voz **100% local**
(no sale audio de tu equipo), ligera porque va por ONNX:

```bash
pip install kokoro-onnx      # + espeak-ng del sistema, para el español
```

Descarga los pesos (`kokoro-v1.0.onnx` y `voices-v1.0.bin`) en `modelos_voz/` y
elige una voz hispana (Dora, Alex, Santa). Si algo falta, Lune sigue con edge-tts.
Hay además un paso **RVC** experimental para convertir el timbre con un modelo
`.pth` propio. Los pesos de voz no se versionan.

---

## 📱 Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ponlo en **⚙️ AJUSTES**, junto con tu ID de Telegram para compartir la memoria
   entre la app y el bot.
3. Pulsa el tile **TELEGRAM** en la barra lateral. Pasa a `TG: ON` cuando arranca.

Comandos del bot: `/start`, `/voz`, `/sistema`, `/memoria`, `/olvidar`, `/modelo`.

**¿A qué modelo pregunta el bot?** Lo decide `bot.proveedor` en `datos.json`:

| Valor | Qué hace |
|---|---|
| `"openrouter"` | Nube, con tu API Key. Es el valor por defecto. |
| `"ollama"` | El modelo local de `modelos.ollama_url` / `modelos.ollama_model` — los **mismos** ajustes que usa la app de escritorio. |

Con `"ollama"` puedes apuntar a otro equipo de tu red: el bot corre donde quieras
y el modelo pesado corre en la máquina potente. Así chateas desde el teléfono sin
que ningún dispositivo ligero cargue el modelo. `/modelo` te dice a quién está
preguntando en cada momento.

---

## ⚙️ Rendimiento y Funciones

**⚙️ AJUSTES → Rendimiento y Funciones** — interruptores para ajustar el
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

Desde 9.0 el código está en paquetes por capa (`nucleo/`, `servicios/`, `ui/`),
así la raíz queda limpia. Cada capa importa de la de abajo:

```text
LuneCD/
├── main.py                 ← Ventana principal y punto de entrada
├── version.py              ← Única fuente de verdad de la versión
├── datos.json · config.json · memoria.json   ← Estado local (NO se versionan)
├── datos.example.json      ← Plantilla pública de configuración
│
├── nucleo/                 ← Fundamentos, sin Qt
│   ├── datos.py            ← Único lector/escritor de datos.json
│   ├── config.py           ← Preferencias y features
│   ├── memoria.py          ← Recuerdos persistentes
│   ├── conversaciones.py   ← Historial de chats en disco
│   ├── adjuntos.py         ← Leer PDF/DOCX/CSV/código e imágenes
│   ├── personajes.py       ← Roleplay e importación de character cards
│   ├── respuestas.py       ← Banco de respuestas instantáneas
│   └── utils.py            ← Logging
│
├── servicios/              ← Motores e integraciones
│   ├── ai_manager.py · ai_worker.py · ollama_client.py   ← IA híbrida + visión
│   ├── voice.py · voz_entrada.py        ← Voz de salida (edge/Kokoro) y dictado
│   ├── tools.py · optimizador.py · actualizador.py       ← Sistema
│   ├── telegram_worker.py · notas_service.py
│   └── red_service.py      ← Presencia en la red (mDNS)
│
├── ui/                     ← Todo lo visual (Qt)
│   ├── splash.py · theme.py · icons.py · effects.py
│   ├── chat_widgets.py · markdown_qt.py · lune_face.py
│   ├── avatar_overlay.py   ← Mascota flotante (sprites o VRM 3D)
│   └── settings_panel.py · optimizer_panel.py · personajes_panel.py · historial_panel.py
│
├── lune_core/              ← Núcleo de red (paquete)
│   ├── hub.py · cliente.py · protocolo.py     ← Transporte host/terminales
│   ├── servicio_memoria.py · memoria_remota.py← Un solo cerebro para todos
│   ├── servicio_chat.py · chat_remota.py      ← El host corre el chat (agente)
│   ├── descubrimiento.py · web_server.py      ← mDNS, QR y terminal web
│   ├── marcadores.py · prompt.py · herramientas.py · rag.py
│   ├── web/vrm.html        ← Visor VRM 3D (three-vrm) para la mascota
│   └── voz/                ← Frases en orden + Kokoro (local) y RVC
│
├── assets/                 ← Medios (inicio.mp4, lune_icon.png)
├── scripts/                ← Utilidades sueltas (probar_red.py)
├── tests/                  ← Suite de pytest (308 tests)
├── lune_face/ · fonts/     ← Sprites/avatar packs y tipografías
└── telegram-bot-or/        ← Bot de Telegram (Node.js)
```

---

## ✅ Tests

```bash
pip install pytest
python -m pytest
```

**308 tests** sobre lo que de verdad se puede romper: la red de seguridad del
Optimizador, los patrones de memoria, el saneamiento de herramientas, el
renderizado de markdown, la lectura de adjuntos, el historial, el actualizador, el
arranque, y ahora la red de dispositivos (roles, descubrimiento y memoria
compartida), el RAG de notas, los marcadores de emoción y la voz por frases.

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
| **v9.0** | **Red de dispositivos**: hub host/terminales, memoria compartida, descubrimiento por mDNS y roles (host / interacción / híbrido). Emociones por marcadores `<\|ACT\|>` y defensa contra prompt injection. Avatar flotante en el escritorio. Memoria larga (RAG) sobre notas markdown. Voz por frases mientras escribe. Herramientas con política, aprobación y auditoría. Terminal web con emparejamiento por QR. |
| v8.7 | El bot de Telegram puede usar un modelo local (Ollama) como proveedor, en la misma máquina o en otra de la red, con los mismos ajustes de modelo que la app. Indicador «escribiendo…» sostenido para modelos lentos. |
| v8.5 | Markdown y bloques de código con copiar. Historial de conversaciones. Adjuntar PDF/DOCX/CSV/código. Visión con imágenes. Dictado local con Whisper. Contador de tokens y costo. Actualizador por git. Estado de proveedor en vivo. Instancia única. Arreglado el arranque invisible del `.vbs`. |
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
