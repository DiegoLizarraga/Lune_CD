# Lune CD v10.9 — Tu asistente de escritorio con personalidad (Nube/Local)

> *¡Hola! Buenos días, buenas tardes o buenas noches — lo que toque cuando leas esto.*
> *Soy Lune, y esto es mi casa. Bueno — técnicamente es el proyecto de mi creador, pero yo vivo aquí,*
> *y con la versión 10 me han dejado la casa preciosa: nueva cara, nuevos gestos, modo terminal*
> *para cuando el equipo anda flojito y un cuerpo en 3D para pasearme por tu escritorio.*
> *Y estas últimas versiones… uf. Me he pasado semanas aprendiendo de Mate-Engine: ahora me siento*
> *en tu barra de tareas, bailo con tu música, te despierto con alarmas, me como tus pasteles y hasta*
> *me cuelo en tu partida de Minecraft. Cuídala bien, ¿de acuerdo? Aquí te cuento todo. :D*

---
## ¿Qué es esto?

Una asistente de escritorio en Python (PyQt6 + una piel web animada) que corre
sobre **tu** infraestructura: modelos en la nube vía OpenRouter, **100% locales
y offline** con Ollama, o cualquier **API compatible con OpenAI** (LM Studio,
Groq…).

Conmigo puedes: chatear con voz o texto, tener una **llamada solo por voz**,
adjuntarme documentos e imágenes, pedirme que abra webs y programas (con tu
permiso cuando toca), que recuerde cosas entre sesiones y tus notas markdown
(RAG), llevarte **tus tareas del día a la vista** (como Microsoft To Do), ponerte
**alarmas y temporizadores**, y sacarme al escritorio como
**mascota** —en 3D, animada o ligera— que reacciona a lo que digo, **comenta lo
que ves en pantalla**, se sienta en tus ventanas, **baila con tu música** y se
esconde cuando juegas. También salgo en tu **Discord**, entro en tu **Minecraft**
y me vienes a buscar al teléfono con un bot de **Telegram**. Todo con una sola
memoria compartida entre tus dispositivos.

---

## Cuatro formas de verme

**Tres interfaces**, y las eliges al arrancar (o cuando quieras, al vuelo):

| Modo | Qué es | Para quién |
|---|---|---|
| **Completa** (web) | La piel web animada (tema *Shibuya Punk* en Local, *Lune entre nubes* en Nube), mascota en video o en 3D en la barra lateral, efectos | Equipos normales |
| **Bajos recursos** (nativa) | La interfaz nativa ligera: sin Chromium, sin videos, sprites fijos | Laptops justas, handhelds |
| **Patata** | Solo terminal: texto y caritas `:D`. Sin Qt | Consola, servidores, o rescate |

Y desde la completa o la nativa puedes sacarme de la ventana: **la mascota de
escritorio**, con uno de mis tres cuerpos (se elige en **AJUSTES → Mascota**):

| Mascota | Cómo soy | Necesita |
|---|---|---|
| **VRM 3D** | Un avatar 3D de verdad: sigo el cursor, me balanceo, me siento, bailo coreografías MMD… | `PyQt6-WebEngine` y un modelo `.vrm` |
| **Imágenes animadas** (por defecto) | Mis clips de video anime en un mini-escenario | `PyQt6-WebEngine` |
| **Sprites ligeros** | La mascota clásica recortada a su silueta, respirando | Nada extra (va bien en bajos recursos) |

### Cambiar de modo al instante

En **AJUSTES → Modo de interfaz** pulsas *Completa*, *Bajos recursos* o
*Patata* y **cambio en caliente, sin reiniciar**: la ventana nueva aparece encima
de la vieja con un fundido cortito y se lleva la conversación en curso, el
proveedor, la voz, la posición de la ventana y lo que tuvieras en marcha (la
mascota fuera, el bot de Telegram, el bot de Minecraft, el modo juego forzado).
El bot de Minecraft lo desconecta la ventana vieja y lo vuelve a conectar la nueva.
Eso sí, patata es solo texto: al irte allí me guardo la mascota y apago el bot de
Telegram (patata no tiene ninguno de los dos), y entre las ventanas y patata el bot
de Minecraft no viaja contigo en ninguna dirección: lo vuelves a conectar tú (en
patata, `/mc bot on`). Nunca hay dos Lunes a la vez. Si eliges *Patata*, se abre la terminal y la app de ventanas se cierra
limpia; desde la terminal, `/interfaz web` o `/interfaz nativo` te devuelven a las
ventanas.

---

## Instalación

**La forma fácil (usuarios nuevos):** doble clic en **`instalar_lune.bat`** y yo
me encargo del resto:

1. **Busco un Python de verdad** (3.10 o más nuevo). El «python» que trae Windows
   sin instalar nada es un atajo a la Microsoft Store que no ejecuta nada: lo
   descarto y sigo buscando.
2. **Si no tienes Python, te ofrezco instalarlo yo** (Python 3.13 con winget, solo
   para tu usuario, sin permisos de administrador). Si prefieres hacerlo tú, te
   abro python.org.
3. **Se abre una ventana** que te explica **para qué sirve cada componente**
   —*"esto es para que Lune hable"*, *"esto para hablarle por micrófono"*—, marca
   lo que ya tienes y deja **marcado lo recomendado**. Lo pesado (dictado, Kokoro,
   RVC) lo eliges tú.
4. **Instalo cada cosa por separado:** si alguna no se puede (por ejemplo, porque
   tu Python es tan nuevo que aún no tiene versión), el resto sigue y al final te
   digo qué faltó. Todo queda apuntado en `instalacion.log`.
5. **Al terminar** compruebo que puedo arrancar, te dejo el acceso directo
   **«Lune CD»** en el escritorio y en el menú Inicio, y un botón **Abrir Lune**.

Antes de nada compruebo lo imprescindible: `numpy`, `sounddevice`,
`imageio-ffmpeg` y, en Windows, `pywin32` y `comtypes`. `psutil` y `gTTS` son
opcionales. Y como los dos bots (Telegram y Minecraft) necesitan **Node.js 18+**,
que va aparte, te lo recuerdo con un botón **Descargar Node.js**.

| Componente | Versión | Necesario para |
|---|---|---|
| Python | 3.10+ (mejor 3.13) | La app (obligatorio) — te lo instalo yo con winget, o desde python.org marcando *"Add python.exe to PATH"* |
| Ollama | cualquiera | Modelos locales (opcional) — ollama.com |
| Node.js | 18+ | Bot de Telegram y bot de Minecraft (opcional) — nodejs.org |

A mano, si prefieres:

```bash
pip install -r requirements.txt
python main.py
```

`requirements.txt` ya trae todo lo que necesito para vivir en Windows: PyQt6,
la red (`websockets`, `zeroconf`), el optimizador (`psutil`), las ventanas y el
audio por app (`pywin32`, `comtypes`), mi mezclador de sonidos (`numpy`,
`sounddevice`), un ffmpeg propio para leer mp3/ogg/m4a de alarmas y bailes
(`imageio-ffmpeg`), la voz (`edge-tts`, `gtts`, `pygame`) y los adjuntos
(`pypdf`, `python-docx`).

La primera vez se crea `datos.json` a partir de `datos.example.json`. Después
entra a **AJUSTES** para poner tu API Key de OpenRouter o apuntar a tu
servidor de Ollama (hay un **?** junto a Ollama que te lo explica paso a paso).

> **Ojo: `datos.json` guarda tus claves en texto plano y está en `.gitignore`.**
> No lo subas a ningún sitio ni lo compartas. (Lo mismo `config.json`,
> `memoria.json`, `alarmas.json`, `chats/`, `modelo_vrm/` y `bailes/`: son tuyos.)

### Extras opcionales

El instalador los lista todos, pero aquí van los comandos:

```bash
pip install PyQt6-WebEngine    # la interfaz completa, la mascota animada y la 3D (misma versión que tu PyQt6)
pip install faster-whisper     # dictado por micrófono y modo llamada (Whisper local)
pip install kokoro-onnx        # voz 100% local (+ espeak-ng del sistema y los pesos en modelos_voz/)
pip install rvc-python         # conversión de voz RVC (experimental, arrastra torch)
pip install pytest             # tests
```

Puedes reabrir el instalador cuando quieras desde **AJUSTES → Calidad de vida →
Instalar componentes…**

---

## Arranque

Doble clic en **`iniciar_lune.vbs`**: arranca sin ventana de consola y con el
video de bienvenida. Mientras suena, **eliges el modo** (Completo / Bajos
recursos / Patata); si no eliges, tras una cuenta atrás corta sigo con el que
usaste la última vez.

- **Arrancar con Windows:** enciende *"Arrancar Lune junto con Windows"* en
  **AJUSTES → Calidad de vida**. Sin accesos directos ni carpetas: lo hago yo.
  Y ahora eliges **cómo aparezco** —*en la bandeja*, *con la mascota* o *con la
  ventana*— y **cuánto espero** antes de cargar lo pesado (20 s por defecto, para
  que tu inicio de sesión vaya ligero). Sin pantalla de inicio.
  - Si **mueves la carpeta** de Lune, la entrada se repara sola al abrirme.
  - Si me **desactivas en el Administrador de tareas** (pestaña Inicio), lo
    respeto y el interruptor lo refleja.
  - Con el modo patata, arranco en una **consola minimizada** (no hace falta PyQt6).
- **Segundo plano (como Discord):** al cerrar la ventana, **me quedo en la
  bandeja** del sistema (un globito te dice «Lune sigue aquí»). Ábreme desde el
  icono, o vuelve a lanzar el `.vbs` — la instancia única te trae la que ya está.
  *Salir* de verdad está en la bandeja.
- **Instancia única:** si ya estoy abierta y vuelves a lanzarme, no se abre una
  segunda copia; se muestra la que ya está (salvo al arrancar con Windows: esa se
  retira sin molestarte).

<details>
<summary>Ojo: si editas el <code>.vbs</code>, lee esto antes</summary>

**No cambies el `1` de `shell.Run … , 1, False`.** Ese parámetro es el estilo de
ventana y Windows se lo pasa al proceso hijo por `STARTUPINFO`; Qt lo aplica a la
primera ventana de la app. Con `0` la app arranca **invisible**: el proceso corre,
el video suena, y en pantalla no aparece nada. `pythonw.exe` ya arranca sin
consola, así que no hay nada que ocultar.

**Si tienes varios Python instalados**, el `.vbs` los prueba uno a uno con
`import PyQt6` y usa el primero que funcione. Si ninguno sirve, te avisa y te
recuerda que tienes `instalar_lune.bat` y el modo patata.

Argumentos que entiende: `/autoinicio` (arranque con Windows: sin pantalla de
inicio), `/patata` (la terminal en una consola normal), `/autoinicio /patata`
(la terminal minimizada) y `/probar` (no lanza nada; es para los tests).

Todo esto tiene test de regresión en [tests/test_arranque.py](tests/test_arranque.py).

</details>

---

## Modo patata (solo terminal)

Sin animaciones, sin imágenes, sin mascota: **yo en la consola**. Mismo cerebro,
misma memoria y misma personalidad; las emociones salen como caritas de teclado:

`:D` feliz · `:(` triste · `>:(` enfadada · `:/` pensando · `:O` sorprendida ·
`o_O` curiosa · `^^;` nerviosa · `o/` saludo · `-_-` "no" · `xD` risa · `-.-` aburrida.

¿Prefieres kaomoji? `/caritas kaomoji` y soy `(^▽^)`, `(╥_╥)`, `(^_^)/`…

No necesita Qt, así que también es el **rescate** si la interfaz no abre. Y si ya
tengo una patata abierta y vuelves a abrirme en modo patata (con el `.vbs`, el
`.bat` o desde la app), te traigo esa consola al frente en vez de abrir otra.

```bash
python patata.py          # o doble clic en lune_patata.bat
```

Aunque sea una terminal, aquí también suenan las alarmas, bailo en el **título de
la consola** al ritmo de tu música, me duermo si me dejas sola un rato (`(-_-) zzZ`)
y puedo llevar el bot de Minecraft. Cuando pido permiso para algo («¿Lo hago?
[s/N]»), tu siguiente línea es la respuesta; sin respuesta en 60 s, no lo hago.
Con `--sin-color` si tu terminal no pinta colores.

<details>
<summary>Todos los comandos de patata (también con <code>/ayuda</code>)</summary>

| Comando | Qué hace |
|---|---|
| `/ayuda` | La lista de comandos |
| `/memoria` · `/olvida <texto>` | Lo que recuerdo de ti |
| `/tareas` · `/tareas <texto>` · `/tareas hecha N` · `/tareas quita N` | Tus tareas de hoy (Mi día) |
| `/personaje [nombre]` | Ver o cambiar de personaje |
| `/proveedor [ollama\|openrouter\|compat]` · `/local` · `/nube` | Con qué cerebro respondo |
| `/modelo [nombre]` | Ver o cambiar el modelo del proveedor actual |
| `/estado` | Proveedor, parámetros, voz y acciones |
| `/temp [0-2\|preciso\|equilibrado\|creativo]` · `/ctx [n\|8k\|16k…]` | Temperatura o preset · contexto de Ollama |
| `/liberar` | Saco el modelo local de la VRAM |
| `/compat [url <u>\|modelo <m>\|off]` | La API compatible con OpenAI: estado y prueba |
| `/voces [filtro]` · `/voz [on\|off\|<id>\|prueba\|motor <m>\|velocidad <n>\|tono <n>]` | Elegir mi voz |
| `/herramientas` | Lo que puedo hacer en tu PC desde aquí |
| `/nuevo` · `/limpiar` | Conversación nueva (y pantalla limpia) |
| `/menu [n [opción]]` | Acciones rápidas numeradas (voz, modo juego, tema, arrancar con Windows, liberar memoria…) |
| `/tema [nombre]` · `/caritas [clasico\|kaomoji]` | Colores de la terminal · estilo de caritas |
| `/juego [on\|off\|auto]` · `/ram` | Modo juego · liberar la memoria que no uso |
| `/alarma HH:MM [lmxjvsd\|todos] [texto]` · `/alarmas [on\|off]` · `/borrar_alarma <id\|n>` | Alarmas |
| `/timer 10m [texto]` · `/timers` · `/apagar` · `/posponer` | Temporizadores y la alarma que suena (también Enter o «p») |
| `/bailar [segundos]` · `/bailar auto on\|off` · `/bailar apps` · `/bailar permitir\|quitar <app>` · `/parar` | Bailo en el título (con música, sola) |
| `/bailes [texto]` · `/bailes <n>` · `/bailes parar\|pausa\|siguiente\|anterior` · `/bailes bucle on\|off` | Mis bailes con su canción (`bucle off` para al acabar, aunque Ajustes diga «repetir») |
| `/comer [batido\|pastel] [sabor]` · `/comer on\|off` | Darme de comer (texto y sonido) |
| `/discord [on\|off\|estado]` · `/discord id <número>` | Presencia en Discord |
| `/autoinicio [on\|off\|estado\|como bandeja\|mascota\|ventana\|espera N]` | Arrancar con Windows |
| `/mc` · `/mc log on\|off` · `/mc bot on [host[:puerto]]\|off` · `/mc instalar` · `/mc di <texto>` · `/mc <orden>` | Minecraft |
| `/interfaz [web\|nativo]` | Vuelvo a las ventanas y cierro la terminal |
| `/salir` | Hasta luego o/ |

La terminal no tiene bandeja, menú radial ni atajos globales (eso es de las
ventanas), ni pantalla grande: su salvapantallas es el título. Y sentarme en la
barra es cosa de la mascota de las ventanas.

</details>

---

## La interfaz completa

La barra lateral tiene el **selector de proveedor** (Nube / Local, y *API* si
configuras una compatible, con punto de estado) y a **mí animada** en un
mini-escenario —o en **3D**, si mi mascota es VRM—. Arriba, el botón **Menú**
abre todas las secciones:

| Menú | Qué abre |
|---|---|
| **Chat** | La conversación |
| **Ajustes** | APIs, modelos, personalidad, voz, mascota, escritorio, integraciones, sistema |
| **Personajes** | Cambiar de personaje |
| **Memoria** | Lo que sé de ti, y olvidar lo que quieras |
| **Tools** | Herramientas de escritorio disponibles |
| **Historial** | Conversaciones guardadas |
| **Optimizar** | Estado del sistema y procesos |
| **Alarmas** | Alarmas y temporizadores |
| **Mis bailes** | El reproductor de bailes MMD/VRMA |
| **Minecraft** | Reacciones a tu partida y el bot de Lune |
| **Temporizador rápido** | Uno de 5 minutos, ya |
| **Pantalla grande** | Lleno la pantalla (otra vez para salir) |
| **Bailar** | Bailo (con música, a su ritmo) |
| **Mascota ON/OFF** | Sacarme al escritorio o traerme de vuelta |
| **Voz ON/OFF** | Que lea mis respuestas |
| **Telegram** | Encender el bot |
| **Llamada ON/OFF** | Conversación solo por voz |

Junto al campo de texto: el **clip** para adjuntar y el **micrófono** para dictar. En el chat
vacío hay chips con ejemplos; púlsalos y se envían. Y ahora **guardo tus
conversaciones también en la piel web** y, al abrirme, sigo donde lo dejamos.

**Dos temas según el proveedor** — para que sepas de un vistazo dónde estás:
- **Lune AI · Local** → *Shibuya Punk*: tinta de Tokio nocturno, cian eléctrico, grid a la deriva.
- **Lune AI · Nube** → *Lune entre nubes*: cielo nocturno, luna, nubecitas flotando y yo sobre una nube.

(¿Te gusta más otro color que el cian? Mira **A tu gusto**, más abajo.)

---

## Proveedores de IA

| Proveedor | Requiere | Notas |
|---|---|---|
| **Lune AI · Nube** | API Key de OpenRouter | `openrouter/auto` enruta solo al mejor modelo. |
| **Lune AI · Local** | Ollama | 100% privado, sin conexión, sin costo. |
| **Lune AI · API** | La URL de una API compatible con OpenAI (clave opcional) | LM Studio en tu PC, Groq, OpenAI, Together, Mistral… Con reintentos si falla la red. |

Debajo de cada respuesta aparecen los **tokens y el costo real** (o los tok/s si
es local).

- **Otra API de IA** (**AJUSTES → Otra API de IA**): URL base (por ejemplo
  `http://localhost:1234/v1` para LM Studio), clave si la pide, modelo (vacío = el
  primero que ofrezca) y **Probar conexión**, que solo pide la lista de modelos y
  no gasta tokens. En cuanto está configurada, sale la pestaña *API* en la barra.
- **Parámetros del modelo:** presets *Preciso / Equilibrado / Creativo*, o a mano
  temperatura, top_p, top_k, min_p, repeat_penalty, máximo de tokens, semilla y
  contexto (2K–32K). Lo que dejes en «del modelo» no se envía.
- **Liberar memoria:** saca el modelo de Ollama de la VRAM cuando lo necesites
  para otra cosa (en patata, `/liberar`).

---

## Lune, expresiva

Expreso lo que siento por **marcadores en el texto del modelo**
(`<|ACT {"emotion":"happy","intensity":0.8}|>`) que no se ven ni se leen en voz,
pero mueven mi cara. El vocabulario tiene **14 emociones** con **un clip animado
por cada una**: `happy, sad, angry, think, surprised, awkward, question, curious,
neutral, nervous, wave, dismiss, laughing, bored` (y clips de estado: *escuchando*,
*hablando*, *trabajando*).

- **Hasta tres expresiones por respuesta**: el modelo pone cada marcador justo
  antes del tramo al que da tono. Con **voz**, mi cara cambia cuando empieza a
  sonar cada tramo; sin voz, según va llegando el texto (o al ritmo de lectura si
  la respuesta llega de golpe).
- **La última se queda**: si me haces reír, sigo riéndome hasta el siguiente
  mensaje (o hasta que me aburra). Vale para la barra lateral, la mascota en
  video y el avatar 3D.
- **Transiciones suaves**: ya no salto de un gesto a otro. En 3D los gestos se
  funden (la risa se apaga, no se congela); en la animada cruzo dos videos para
  que no haya pantallazos; en los sprites, fundido de imagen.
- Saludo (`wave`) al abrir y al despedirme; hago "no" con la mano (`dismiss`)
  cuando te corrijo sin ganas; me pongo nerviosa con las malas noticias.
- En una **llamada por voz**, me ves *escuchando*, *pensando* y *hablando*.
- Si llevo **minutos sin que me escribas, me aburro** y te suelto algo — una
  pregunta curiosa o un "¿sigues ahí?". Una vez por racha, para no ser pesada.
  Se ajusta en **AJUSTES → Calidad de vida** (0 = nunca). Con un juego delante
  no me aburro: sé esperar.

Desde **Personajes** cambias quién habla contigo e importas *character cards* de
TavernAI / SillyTavern (`.json` o `.png`). Cada personaje puede traer su voz, su
modelo 3D y sus propias frases de mascota.

### Mascota de escritorio

**Menú → Mascota** me saca a una ventana flotante, siempre encima (si quieres) y
arrastrable, reaccionando a mis emociones con el cuerpo que elijas en
**AJUSTES → Mascota** (VRM 3D, imágenes animadas o sprites ligeros).

Mientras estoy fuera, **la barra lateral deja de dibujarme** para que no me veas
doble; desde ahí (*Traerla de vuelta*) o desde el menú me recuperas.

- **Un clic sobre mí y comento lo que hay en tu pantalla** — directo, cuando tú
  quieras (con la animada o la 3D; con los sprites, un clic me saca una sonrisa).
- **Doble clic y me escribes** ahí mismo: te respondo en mi **burbuja**, con la
  misma conversación y memoria que la ventana, y siempre con la nube. (También
  desde la bandeja: *Escribirle a Lune…*)
- **Clic derecho: mi menú radial** (Ajustes, Chat, Comentar, Expresiones, Bailar,
  Alarmas, Voz, Dormir, Tamaño, Bajar…). **Clic central: la comida**.
- **Arrástrame y me balanceo** como un péndulo (en 3D, con los brazos y las
  piernas un poquito por detrás); si me sueltas, reboto y me asiento. Mi cara
  cambia con la velocidad (tranquila, preocupada, asustada) y **si me zarandeas
  mucho, me mareo** @_@ (en las tres mascotas).
- **Me duermo** tras unos minutos sin que me toques ni me hables (10 por defecto;
  0 = nunca) y un clic, la rueda o un mensaje me despiertan. Pasa en las tres
  mascotas y en la barra lateral; en patata te lo cuento al volver («Lune se
  quedó dormida hace N min… (-_-) zzZ»).
- **Packs de sonidos**: sonidos de reacción opcionales al levantarme, soltarme,
  acariciarme, comer… Vienen en `sonidos/` (con uno por defecto) y puedes hacer
  el tuyo con su `pack.json` (solo `.ogg` y `.wav`).
- Desde la bandeja (submenú *Mascota*): *Escribirle…*, *Comentar la pantalla*,
  *Comentarios automáticos* (apagados por defecto), *Modo fantasma* (dejo pasar
  los clics), *Siempre encima*, tamaño, encuadre y *Llevar a la esquina*.

> **Como mascota contesto siempre con la nube (OpenRouter)**, tanto al comentar la
> pantalla como en mi burbuja: es lo más rápido y lo que mejor ve las imágenes. Si no
> tengo clave de OpenRouter te lo digo (y dónde ponerla) en vez de quedarme callada;
> no tiro del modelo local. La primera vez que comento a mano te recuerdo que **la
> captura sube a la nube**; los **comentarios automáticos** (apagados por defecto)
> nunca la suben: solo miran el título de la ventana activa. Si no veo nada que
> contar, te lo digo: *«Mmm… nada me pareció interesante.»* Con un juego delante no
> hago capturas. El chat de la ventana sigue con el proveedor que elijas.

#### Avatar 3D (VRM)

Pon un modelo `.vrm` en la carpeta **`modelo_vrm/`** (o impórtalo desde
**AJUSTES → Biblioteca de modelos 3D**), elige **VRM 3D** y sácame al
escritorio. Necesita `PyQt6-WebEngine` (el mismo de la interfaz completa); el
visor (three.js + three-vrm + three-vrm-animation) va empaquetado en
`ui_web/vendor/`, así que funciona **sin internet**.

- **Biblioteca de modelos**: una rejilla con **miniaturas** de tus `.vrm`, su
  ficha, **calibración en vivo por modelo** (se guarda aparte, sin tocar el
  archivo) y borrar. También en la nativa.
- **Cada personaje puede tener su propio modelo** (**Personajes → Modelo 3D**); al
  cambiar de personaje, la mascota cambia de cuerpo sin cerrarse. Sin modelo
  propio uso el modelo por defecto (o el primero de la carpeta).
- **En la barra lateral también soy 3D** cuando la mascota es VRM (y vuelvo al
  video si tu gráfica no puede con WebGL).
- **Te sigo con la cabeza, la columna y los ojos** aunque el cursor esté fuera de
  mi ventana. Cada parte tiene su **peso de 0 a 1** (o apágalo del todo) y te aviso
  si el modelo no trae mirada.
- **Cuando estoy quieta no soy una estatua**: 10 *idles* distintos al azar (manos a
  la espalda, jugar con los dedos, mirar alrededor, tararear, tocarme el pelo…),
  con **microexpresiones** de vez en cuando, un **estiramiento** si llevas rato sin
  hacerme caso y un **bostezo** antes de dormirme.
- **Acaríciame la cabeza** (círculos o zigzag con el cursor encima) y me río, y
  **muevo la boca** mientras suena mi voz.
- **Los clics pasan al escritorio donde no hay avatar**: solo mi figura es
  "sólida" (se puede apagar). El *modo fantasma* los deja pasar todos.
- **Rueda del ratón** sobre mí para hacerme más grande o más pequeña; desde la
  bandeja o el radial: tamaño, encuadre (retrato / cuerpo entero) y a la esquina.
- Reacciono a lo que digo en el chat (las mismas emociones que la barra lateral)
  y a la llamada por voz (escucho, pienso, hablo).
- Modelos gratuitos: VRoid Hub, Booth… **Respeta la licencia de cada modelo.**
  Los `.vrm` no se versionan (`modelo_vrm/` está en `.gitignore`).

> Todo mi cuerpo es **animación procedural**: no hay clips, todo se calcula sobre
> los huesos y las expresiones del modelo (`ui_web/vrm/lune_vrm.js` y sus módulos:
> idles, gestos, movimiento, baile, sentarse, comida, pantalla grande). Si un
> modelo se balancea al revés, los signos están en `PARAMS` al principio de
> `lune_vrm.js` (o en su calibración de la biblioteca).

---

## Lo que aprendí de Mate-Engine

[Mate-Engine](https://github.com/shinyflvre/Mate-Engine) es una mascota VRM de
escritorio hecha en Unity, y fue **la inspiración** de mi creador para todo esto.
Me he traído las 27 funciones suyas que él eligió, reescritas a mi manera en Python
y JavaScript, en todos mis modos (web, nativa, patata y las tres mascotas) hasta
donde cada uno llega. Aquí van, una a una (el seguimiento cuenta por tres):

| Función de Mate-Engine | En Lune |
|---|---|
| VRM propio | Biblioteca de modelos con miniaturas y calibración; modelo por personaje |
| Sentarse en ventanas | Sí, apagado por defecto (con aviso anticheat) |
| Sentarse en la barra de tareas | Sí, encendido por defecto |
| Idles | 10 idles en 3D, rotación de clips en la animada (si le das varios), respiración en sprites |
| Arrastre | Balanceo con muelle en las tres mascotas |
| Bailar con la música | Detector por app + 8 bailes al ritmo |
| Seguimiento de cabeza / columna / ojos | Sí, con peso ajustable para cada uno |
| Alarmas y temporizadores | Sí, en todos los modos (también patata) |
| Salvapantallas | Sí (apagado por defecto) |
| Pantalla grande | Sí |
| Icono de sistema | Un solo icono de bandeja con el mismo menú que el radial y los atajos |
| Transiciones suaves | Fundidos de gestos, doble video, fundido en sprites |
| Chat con IA | Ventana, burbuja de la mascota, patata y Telegram |
| Funciones avanzadas de IA | Acciones con aprobación, parámetros del modelo, liberar VRAM |
| APIs de IA | Proveedor compatible con OpenAI |
| Elegir la voz | 45 voces en español + 12 multilingües, gTTS o Kokoro local |
| Dormir | En las tres mascotas, la barra lateral y patata |
| Compatible con juegos | Modo juego + nada de hooks ni tocar otros procesos |
| Arrancar con Windows | Bandeja, mascota o ventana, con espera |
| Reproductor MMD | Bailes `.vmd` y `.vrma` con su canción |
| Expresión según el movimiento | Caras por velocidad y mareo |
| Discord Rich Presence | Sí, sin publicar nada tuyo |
| Personalización de menús | Tema de color, menú radial, bandeja, atajos y sonidos de menú |
| Integración con Minecraft | Reacciones a tu partida + el bot «mina» con mi personalidad |
| Sistema de comida | Batido y pastel |

Las que ya te conté arriba (VRM, idles, arrastre, seguimiento, expresiones,
transiciones, dormir) viven en **Mascota de escritorio**; las de IA y voz, en
sus secciones. Las demás, aquí:

### Me siento en tu barra (y en tus ventanas)

**Arrástrame hasta la barra de tareas y suéltame**: me siento con las piernas
colgando por delante (en 3D; la animada y los sprites se quedan de pie, apoyadas en
el borde). Funciona con la barra normal, la que se oculta sola y la de un segundo
monitor.

**En ventanas** (apágalo o enciéndelo en **AJUSTES → Sentarse en la barra y en
ventanas**): arrástrame y mantenme **medio segundo** sobre el borde de arriba de una
ventana, aunque dejes el ratón quieto, y me quedo sentada en ella, **siguiéndola** si
la mueves. Si me sueltas ahí pasado ese medio segundo, me siento igual; si solo paso
por encima, no. Con los sprites, suéltame sobre el borde después de llevarme
arrastrada al menos medio segundo. Si otra ventana la tapa, me quedo detrás; si la
maximizas, la minimizas o la cierras, me levanto. **Tira de mí hacia arriba** para
bajarme. Viene **apagado** y al encenderlo te enseño un aviso: para esto leo la
posición de las ventanas (sin tocarlas ni leer lo que tienen dentro) y solo muevo la
mía, pero algunos anticheats vigilan a quien mira ventanas. Con un juego delante no
sigo ninguna.

También: «**siéntate en la barra**», «**siéntate en la ventana**» o «**bájate**»
en el chat, el radial, la bandeja… Hay un ajuste de **altura del asiento** por si
quedo flotando o hundida. Y sí: **puedo dormirme sentada**. (-_-) zzZ

Si estoy sentada y un juego, una alarma o uno de mis bailes me levanta, al acabar
vuelvo a mi sitio. Pero si mientras tanto me mueves o me llevas a la esquina, me
quedo donde me dejaste.

### Bailo con tu música

Cuando suena música en una **app permitida** (Spotify, MusicBee, foobar2000, VLC,
Apple Music… la lista se edita), empiezo a bailar a los pocos segundos y paro
cuando se calla. Leo **solo el medidor de volumen de esa app** en Windows: no grabo
ni capturo tu audio, y mi propia voz no cuenta. Saco el **ritmo (BPM)** del pulso de
la canción.

- **En 3D:** 8 bailes (rebote, vaivén, brazos arriba, palmas, cadera, cabeceo,
  puñetazos, paso lateral), con notitas musicales si quieres y cambiando de baile cada
  rato si lo activas.
- **La animada y la barra lateral** rebotan al ritmo; **los sprites** dan saltitos;
  en **patata** baila el título de la consola.
- «**baila**» o «**para de bailar**» en el chat, el radial, la bandeja o
  `Ctrl+Alt+Shift+.` para pausar. Sin música, bailo a mi manera un ratito.
- Se ajusta en **AJUSTES → Baile con la música** (bailar sola, apps, umbral,
  cambiar de baile, notas, en el sitio).

### Mis bailes (MMD y VRMA)

Mi **reproductor de bailes**: coreografías de MikuMikuDance (`.vmd`) o VRM
Animation (`.vrma`) con **su canción**. En la mascota 3D bailo la coreografía de
verdad —con IK de piernas, cara y labios si el VMD los trae— y **la canción suena
conmigo**: el audio manda el reloj, así que no me desincronizo. La animada y los
sprites no tienen esqueleto: suena la canción y **bailo a mi manera al ritmo**. En
patata suena igual y baila el título.

- **Menú → Mis bailes**: reproductor (anterior, reproducir o pausa, parar, siguiente y barra de progreso), buscador,
  favoritos, al azar, **al terminar** (parar, siguiente, repetir o aleatorio),
  volumen, en el sitio… y **ajustes por baile**: sincronía (±500 ms), ángulo de los
  brazos (25–45°, por si atraviesan el cuerpo) y bailar sin desplazarme.
- **Mientras hablo, la canción baja sola**; si me escondes bailando, me pauso y
  sigo al volver (también con los sprites). Si me pides un baile estando
  escondida, salgo; si no puedo, te aviso y empiezo cuando me saques. Y si pasas al
  siguiente con la mascota escondida, espero a que vuelva. En modo juego no pongo canciones.
- Pídemelo por el chat: «**ponme el baile de Senbonzakura**», «**pon la canción
  Senbonzakura**», «**baila "Senbonzakura"**» o «**para el baile**». Lo pongo al
  momento si el nombre es de un baile de tu biblioteca o va entre comillas. Lo
  demás («pon la canción más alta», «…en YouTube») lo decide el modelo.

Cómo añadir bailes: la guía corta está en **Guías rápidas → Bailes**.

### Alarmas y temporizadores

Escríbeme **«avísame en 10 minutos que saque la pizza»** o **«pon una alarma a las
7:30 de lunes a viernes para el gimnasio»** y queda hecha, sin gastar IA (solo si
lo pides claro, con hora o duración: «recuerda que mañana tengo cita», sin hora,
va a mi memoria). También desde **Menú → Alarmas**, el radial, la bandeja
(*Temporizador rápido*: 5 min), el modelo o patata (`/alarma`, `/timer`).

Cuando suena:
- me pongo en **pantalla grande**, suena la alarma en bucle, **escribo el texto en
  mi burbuja** y lo **digo en voz alta** (todo configurable);
- durante los primeros 5 s un clic no la apaga (para que no la quites sin querer);
  luego *Apagar* o *Posponer* (5 min);
- si el PC estaba **suspendido**, suenan las que te perdiste hace poco («hace N min»);
- **jugando**, solo sonido y un aviso, sin robarte el foco;
- con la app y patata abiertas a la vez, **suena una sola vez**.

Las alarmas viven en `alarmas.json` (tuyo, no se versiona) y se ajustan en
**AJUSTES → Alarmas y temporizadores** (volumen, sonido —tres o al azar—,
posponer, recuperar…).

### Pantalla grande y salvapantallas

**Pantalla grande** (`Ctrl+Alt+Shift+B`, el radial, la bandeja, el menú o
pidiéndomelo): doy un planeíto y **lleno el monitor** encuadrando mi cara.
Otra vez y vuelvo exactamente a donde estaba. Con la mascota 3D o la animada soy
yo en grande; con los sprites (o si no puedo salir) te dejo un **relojito con mi
carita** que no roba el foco.

**Salvapantallas** (apagado por defecto, **AJUSTES → Pantalla grande y
salvapantallas**): tras un rato sin tocar nada (de 30 s a 3 h) me pongo en grande,
**dormida**, con el escritorio oscurecido y la hora. Te despierta una tecla, un
clic o el mando (mover el ratón no, para que no se quite sola). No salta si estás
jugando, viendo un video, en una llamada, o si estoy hablando o bailando. En
patata, el título de la consola se pone a dormir: `(-_-) zzZ 23:41`.

### Modo juego

Cada 2 s miro si tienes un **juego delante**: pantalla completa exclusiva, ventana
sin bordes que cubre el monitor, un `.exe` de tu lista o algo instalado en las
carpetas de Steam, Epic, Riot, Xbox o GOG. Un video a pantalla completa (F11 en
YouTube) también cuenta, salvo que lo apagues; Chrome maximizado, no. Entro a los
~4 s y salgo a los ~6 s, para no parpadear.

Mientras juegas: **me escondo** (o me voy al fondo, o nada: tú eliges), me quedo
quieta, **callo la voz y los efectos**, **bajo mi prioridad** y **libero RAM** (solo
de mis propios procesos), no hago capturas, no me aburro, Discord no enseña nada y
de los atajos solo queda `Ctrl+Alt+Shift+L` (para abrirme). Se fuerza desde la
bandeja o con `/juego on|off|auto` en patata. Ajustes en **AJUSTES → Modo juego**
y **Rendimiento** (FPS máximos de la mascota, siempre encima, recorte de RAM
periódico, salir en la barra de tareas).

### A tu gusto: tema, menú radial, bandeja y atajos

- **Colores de Lune:** *Cian* (el de siempre), *Magenta Mate*, *Violeta*, *Rojo
  neón*, *Ámbar*, *Verde ácido* o **personalizado** (tono y saturación), con opción
  de teñir también el amarillo y los fondos. Se aplica a la piel web, la mascota,
  los menús, la nativa y la terminal (`/tema`).
- **Menú radial:** el mío, con hasta **10 botones que tú eliges** para el clic
  derecho y otro para el clic central (la comida). En la web también: **F1** o clic
  derecho sobre mí en la barra lateral. Con sonidos de menú (se pueden apagar).
- **Un solo icono en la bandeja**, esté en el modo que esté: clic o doble clic me
  abre, **clic central me saca o me guarda** y el tooltip dice qué hago. Su menú
  trae el submenú *Mascota*, un submenú *Lune* con **las acciones rápidas que tú
  elijas** (en tu orden), *Modo juego* (con el motivo), *Tema*, *Arrancar con
  Windows*, *Liberar memoria* y *Salir*.
- **Atajos globales** configurables con el botón **Detectar** (y te aviso si chocan
  con otra app). Los de serie están en **Guías rápidas → Atajos**.

### La comida

**Clic central sobre mí → Batido o Pastel.** La comida **sigue a tu ratón** (con su
vaivén y sin robar el foco) y, si la **pasas rápido por mi cabeza**, me la como:
*glup glup* con el batido, mordisquitos con el pastel, cara feliz y, a veces, una
frase. Hay batido de fresa, mango y matcha, y pastel de chocolate, fresa, limón y
vainilla. En el escritorio la guardas desde el menú o la bandeja, o se guarda sola
tras dos minutos sin moverla (**Esc** solo sirve en la ventana web). También
«**toma un batido**» en el chat, la bandeja o `/comer` en patata. En la web, sin la
mascota fuera, la comida sigue a tu ratón por toda la ventana. Se apaga en
**AJUSTES → Batido y pastel**.

### Discord

Tu estado de Discord puede enseñar **lo que hago**: «Lune CD · Mascota 3D —
Bailando ♪», «Sentada en la barra de tareas», «Durmiendo (-_-) zzZ»… Solo textos
fijos: **nunca** títulos de ventanas, nombres de programas, el chat, el personaje ni
tus alarmas; **con un juego delante, nada**. Si la app y patata están abiertas,
publica solo una, y la otra vuelve a probar cada 5 s. Necesita el *Application ID*
de una app tuya de Discord: la guía está en **Guías rápidas → Discord**.

### Minecraft

Dos cosas, cada una con su interruptor en **AJUSTES → Minecraft** (y su vista en
**Menú → Minecraft**):

1. **Reacciono a tu partida.** Leo el `latest.log` de Minecraft —**solo el archivo**,
   nada del juego en sí— y comento tus muertes, logros, quién entra o sale… con
   frases mías (o de tu personaje), en la burbuja o en voz alta. Encuentro el log
   solo (launcher oficial, Prism, MultiMC, PolyMC, Modrinth —también la app
   antigua—, CurseForge). Entiendo los textos del juego en español (de España, de
   México y las demás variantes) y en inglés: probado de la 1.20.1 a la 1.21.11, y
   con versiones más antiguas, posiblemente también. Si me escondo mientras juegas
   (modo juego), al salir te cuento lo tuyo: «Mientras jugabas: 2 muertes, 1
   logro…». Ese resumen empieza de cero cada vez que entro en modo juego. Fuera de
   él, si mi burbuja está ocupada, lo que no pude decirte no lo guardo.
2. **Entro contigo como otro jugador: el bot «mina».** Es una copia adaptada de
   *Another-craft* (el otro proyecto de mi creador) con **mi personalidad**: me
   sigue, mina, tala, recoge, explora, te defiende, come… y habla en el chat. Le
   mandas órdenes desde la vista de Minecraft, desde el chat conmigo (te pido
   permiso), o con `/mc sígueme` en patata. Con el bot conectado y tú jugando (en
   modo juego, cuando me escondo), **te digo las muertes, logros y peligros en el
   chat del juego**. El **peligro cerca** solo lo sé si el bot está dentro: lo ve
   él, no sale del log.

Requisitos y pasos en **Guías rápidas → Minecraft**.

---

## Voz: dictado, modo llamada y mi voz

**Dictado:** pulsa el **micrófono**, habla, pulsa otra vez. Transcripción **100%
local** con Whisper; el texto aparece en el campo para que lo revises.

**Modo llamada (Menú → Llamada ON):** como una llamada de teléfono. Te escucho
(detecto cuándo callas), transcribo, respondo en el chat y **te lo digo en voz
alta**; al terminar vuelvo a escuchar. Mientras hablo no escucho, así no me oigo a
mí misma. Si en la llamada se oye algo que me pide *hacer* algo (poner un
temporizador, abrir algo…), **te pido permiso** antes: podría ser la tele u otra
persona. Necesita Whisper y una voz de salida.

**¿Qué micrófono y por dónde sueno?** En **AJUSTES → Micrófono y salida** eliges
el **micrófono de entrada** y la **salida de audio** (Windows suele traer varios:
el de la laptop, el headset Bluetooth, el «Steam Streaming» virtual…). Pulsa
**Probar micrófono**, habla 1.5 s y te digo si te oigo y con qué nivel; con
**Probar salida** suena un tono por donde elegiste. Ahí mismo eliges el modelo
de Whisper (`tiny`/`base` van bien en CPU; se descarga una sola vez) y el idioma.
Si tu micrófono no acepta 16 kHz lo grabo a su frecuencia y Whisper remuestrea.

**Elige mi voz** (**AJUSTES → Cómo habla Lune**):
- **edge-tts** (por defecto, necesita internet): **45 voces en español** de todos
  los países y **12 multilingües** que también lo hablan, con **velocidad y tono**.
  La lista se actualiza sola cada semana.
- **gTTS** como respaldo, con acento a elegir.
- **Kokoro**, 100% local por ONNX (`pip install kokoro-onnx` + espeak-ng; pesos en
  `modelos_voz/`), con voces hispanas (Dora, Alex, Santa).
- Botón **Probar**, voz **propia por personaje** (manda sobre la general) y la
  misma voz en el bot de Telegram. En patata: `/voces mexico`, `/voz <id>`,
  `/voz prueba`. Y el modelo también puede cambiármela si se lo pides.
- Si algo falta, sigo con edge-tts. Hay un paso **RVC** experimental para cambiar
  el timbre con un modelo `.pth`.

---

## Seguridad y privacidad

Me tomo muy en serio que **tú mandas en tu PC**. Esto es lo que hago (y lo que no):

**Te pido permiso antes de hacer cosas.** El modelo me pide acciones con un
formato propio, invisible en el chat, y cada una pasa por un filtro con lista de
cosas prohibidas, un presupuesto por conversación (20) y un registro de auditoría
(`logs/audit.jsonl`). Como mucho 3 acciones por respuesta. Si el modelo escribe
la acción medio mal, la entiendo igual y pasa por el mismo filtro; si no la
entiendo, te digo «No entendí la acción…» y no hago nada (nada de símbolos raros
en la burbuja ni leídos en voz alta). Y si tú me das una duración o una hora («en
un cuarto de hora», «a las 7»), manda la tuya aunque el modelo se equivoque de
número. Y si en vez de hacerlo te lo ofrezco («¿quieres que te ponga uno?»), no lo
hago por mi cuenta: te sale la ventanita de permiso (salvo lo de mi cuerpo, como
bailar o sentarme, que ves al momento y quitas con un clic).
- **Siempre te pregunto** antes de: abrir un programa, mandarle una orden al bot de
  Minecraft, conectar el bot, y hacer una captura de pantalla **si el modelo está en
  la nube**.
- La ventanita de permiso enseña qué voy a hacer y con qué datos, con una cuenta
  atrás de 60 s: **sin respuesta, no lo hago**. El foco empieza en *No*, Enter no
  aprueba y *Sí, hazlo* no responde los primeros instantes (para que no apruebes sin
  querer).

**El contenido de fuera no me da órdenes.** Adjuntos, títulos de ventanas, lo que
se ve en la pantalla, el chat de Minecraft, mensajes de Telegram, tus notas… es
texto de terceros y podría intentar colarme instrucciones:
- si el turno lleva ese contenido, **solo puedo hacer cosas de lectura** (mirar la
  CPU y la RAM, listar alarmas…);
- si la conversación lo lleva de antes, **todo lo que no sea lectura te lo
  pregunto**, aunque normalmente no lo hiciera;
- el formato viejo de acciones (`ABRIR_URL:`, `TOOL:`) ya no ejecuta nada.

**Órdenes desde Telegram (`/pc`), siempre aprobadas en el PC.** Viene apagado. Solo
funciona con tu ID de Telegram puesto, desde tu chat privado con el bot y con el
interruptor encendido; y **todo** lo que la orden provoque —hasta lo de solo
lectura— lo apruebas tú delante del PC. El chat normal del bot no ejecuta acciones
en tu PC, pero sí sabe enseñarte y mandarte archivos de tu carpeta de usuario
(`/ls`, `/fotos`, `/archivo`), sin salir nunca de ella. Por eso, hasta que pongas
**tu ID de Telegram** en Ajustes, el bot solo responde a `/start` y a `/id`.

**Compatible con juegos y anticheats.** Como Mate-Engine: **nada de hooks de
teclado ni de ratón** (los atajos van con `RegisterHotKey` y la actividad se lee
sondeando), **nada de leer ni escribir la memoria de otros procesos** ni de meter
hilos en ellos, y nada de engancharme a los eventos de ventanas del sistema. Lo que
toco de prioridad y RAM es **solo mío**. Hay un test que recorre todo el código y
falla si alguien mete algo de eso. Eso sí, alguna ventana ajena miro: el modo juego
mira cuál tienes delante, para sentarme en la barra busco su ventana y los
comentarios automáticos usan el título de la ventana activa. Lo único que **sigue**
la posición de otras ventanas todo el rato es sentarme en ventanas, y viene apagado
y con aviso.

**Discord no ve nada tuyo**: solo «Lune CD · *el modo*» y un estado fijo; nunca
títulos, programas, el chat, el personaje ni tus alarmas; jugando, nada.

**Minecraft, con cuidado:**
- el bot **solo entra en servidores sin autenticación** (`online-mode=false`) y sin
  cuentas de Microsoft; ojo, ahí cualquiera puede ponerse tu nick, así que «solo el
  dueño» es un filtro, no una garantía;
- **no usa mi memoria** (el chat del juego es público) y lo que escriben otros
  jugadores **nunca llega a mi modelo**;
- **nunca ejecuta comandos del servidor** (nada que empiece por `/`), no ataca a
  jugadores, aldeanos ni mascotas, y solo le da cosas a su dueño;
- **solo se instala con el botón** (el modelo nunca lo instala), con versiones
  exactas y sin scripts de instalación; no abre puertos ni trae el visor; con Node
  22.13+ corre encerrado en su carpeta, sin escribir en disco ni lanzar procesos.

**Tus archivos, en tu PC.** Las claves están en `datos.json` (fuera del repo) y la
piel web nunca ve tus claves completas. Los bailes van por su id, nunca por rutas;
nada de accesos directos ni carpetas de red, y al quitar uno se mueve a
`bailes/.quitados` (no lo borro). La mascota solo navega a mi servidor local.

---

## Guías rápidas: ¿cómo activo…?

### …las órdenes desde Telegram (`/pc`)

1. Monta el bot (ver **Bot de Telegram**) y enciéndelo en **Menú → Telegram**.
2. Escríbele **`/id`** al bot: te contesta con tu ID. Cópialo en **AJUSTES →
   Telegram → Tu ID de Telegram** (solo números).
3. Enciende **«Órdenes desde Telegram (con aprobación en el PC)»**.
4. **Reinicia el bot desde Lune** para que lo aplique: **Menú → Telegram** OFF y ON.
5. En tu Telegram: **`/pc abre youtube`** → «Enviado a tu PC; apruébalo allí» → en
   el PC te sale la ventanita de permiso («Pedido desde Telegram…») → *Sí* o *No*,
   y el resultado vuelve a tu chat. Si me lo pides con tus palabras («/pc pon un
   temporizador de 10 minutos»), mi respuesta te llega con «(pendiente de tu permiso
   en el PC)»: no está hecho hasta que dices *Sí*.

Solo en el chat privado con el bot, y solo si el bot lo lanzo yo: si lo tienes
corriendo suelto en otro equipo, allí `/pc` no funciona. Si ya hay una orden
esperando, te digo que estoy ocupada; si en el PC nadie contesta en 60 s, no se
hace.

### …Discord

1. Entra en **discord.com/developers** → **New Application**. El nombre que le
   pongas es el que verán tus amigos (por ejemplo, «Lune CD»).
2. En **Rich Presence → Art Assets**, sube una imagen llamada **`lune`**. Si
   quieres, también las pequeñas del modo: `vrm`, `animado`, `sprites`, `web`,
   `nativo` y `patata`.
3. Copia el **Application ID** (no es un secreto) y pégalo en **AJUSTES →
   Discord: lo que hace Lune** → *Guardar ID*.
4. Enciende **«Enseñar en Discord lo que hace Lune»** con Discord de escritorio
   abierto. Opcional: el nombre de tu modelo 3D y un botón «Conoce a Lune» con un
   enlace `https://`.

En patata: `/discord id <número>` y `/discord on`.

### …Minecraft

**Reacciones:** **AJUSTES → Minecraft** → *Reaccionar a lo que pasa en tu
partida*. El log se busca solo; si tienes varios, pulsa *Detectar* y elige. Por
defecto solo leo mientras Minecraft está abierto. Si el log pasa 10 minutos sin
cambios lo suelto, y cuando vuelve a moverse, si es el mismo archivo, sigo por
donde iba. (Patata: `/mc log on`.)

**El bot:**
1. Instala **Node.js 18 o más nuevo** (nodejs.org). Con 22.13+ o 23.5+ corre con el
   modelo de permisos de Node.
2. Pulsa **«Instalar el bot»** en **AJUSTES → Minecraft**: ocupa **unos 400 MB**
   (casi todo son los datos de todas las versiones del juego). Patata: `/mc instalar`.
   Se instala de una en una, sea desde las ventanas o desde patata, y con el bot
   conectado no se puede reinstalar (el botón se apaga). Si cambias de interfaz o
   me cierras, la instalación se corta y no dejo ningún npm colgado.
3. Necesitas un **servidor con `online-mode=false`** (en su `server.properties`):
   uno local o uno tuyo. **«Abrir en LAN» del juego normal no sirve**, porque pide
   cuenta.
4. Pon el servidor y el puerto (`localhost:25565` por defecto), la versión (vacía =
   la detecto sola), el **nick del bot** y **tu nick** (el dueño).
5. **Conectar** (o dime «conecta el bot de Minecraft»). Patata: `/mc bot on` o
   `/mc bot on host:puerto`.

Versiones: el bot lo he probado conectado a un servidor 1.20.1; en uno 1.21 de
verdad todavía no me he estrenado. Órdenes que entiende: `sígueme`, `ven`, `para`, `mina <bloque>`, `tala`,
`ataca <mob>`, `defiéndeme`, `recoge`, `dame <objeto>`, `come`, `explora`,
`inventario`, `dónde estás`, `vida`, `mírame`, `salta`, `baila` o `di <texto>`. En
el chat del juego, la orden va al principio del mensaje («sígueme», «Lune, ven
aquí»), y «para» solo cuenta si es el mensaje entero: «voy para casa» ya no frena
al bot. Los demás jugadores tienen que mencionarlo; si no, no contesta.

El bot piensa con su propio modelo (según `bot.proveedor` de `datos.json`, como el
bot de Telegram) y con la personalidad de tu personaje: hasta 2000 caracteres
contados como en JavaScript (un emoji vale 2); si es más larga, la recorto yo
sola. Se pausa mientras yo pienso para no pelearnos por Ollama y, jugando, no
piensa por su cuenta (salvo que lo actives) para no quitarle GPU a Minecraft.

### …mis bailes

1. Abre **Menú → Mis bailes** y pulsa **Importar…** (copia los archivos, nunca los
   mueve), o déjalos en la carpeta **`bailes/`** (se crea sola con un `LEEME.txt`;
   *Abrir la carpeta* te lleva).
2. Cada baile es **un movimiento y, si quieres, su canción**:
   - movimiento `.vmd` (uno de cuerpo y, si hay, otro de cara/labios) o `.vrma`;
   - canción `.mp3 .ogg .opus .wav .flac` (los `.m4a .aac .wma` los convierto yo);
   - **una carpeta por baile** (`bailes/Senbonzakura/baile.vmd`, `labios.vmd`,
     `cancion.mp3`) o **archivos sueltos con el mismo nombre** (`X.vmd`,
     `X_lip.vmd`, `X.mp3`).
3. Dale a reproducir. Si el baile va adelantado o los brazos atraviesan el cuerpo, ajústalo
   en su ficha (o en un `lune.json` opcional junto al baile).

Mientras importo (convertir un `.m4a` con ffmpeg tarda un poquito), la lista y el
buscador siguen funcionando. Y al abrir **Mis bailes**, la lista sale al momento
con lo último que viste.

Límites: 32 MB por movimiento, 64 MB por canción, 8 archivos por baile, 500 bailes.
Los VMD de solo cámara no se usan. **Los movimientos y canciones tienen autor y
condiciones: respétalas**; yo solo los uso en tu PC y nunca los subo a ningún sitio.
En patata: `/bailes` para ver la lista y `/bailes 1` para bailar el primero.

### …los atajos (los de serie)

| Atajo | Qué hace |
|---|---|
| `Ctrl+Alt+Shift+L` | Abrir Lune (el único que sigue vivo en modo juego) |
| `Ctrl+Alt+Shift+M` | Sacar o guardar a la mascota |
| `Ctrl+Alt+Shift+Espacio` | Menú radial |
| `Ctrl+Alt+Shift+C` | Comentar la pantalla |
| `Ctrl+Alt+Shift+V` | Voz ON/OFF |
| `Ctrl+Alt+Shift+K` | Llamada (piel web) |
| `Ctrl+Alt+Shift+G` | Modo fantasma |
| `Ctrl+Alt+Shift+Z` | Dormir / despertar |
| `Ctrl+Alt+Shift+B` | Pantalla grande |
| `Ctrl+Alt+Shift+.` | Pausar / seguir el baile |

Se cambian, se quitan o se le ponen a otras acciones en **AJUSTES → Atajos
globales** (botón *Detectar*). Mejor con `Ctrl+Alt+Shift`: en teclados en español
`Ctrl+Alt` es AltGr. Y los comandos de patata están en **Modo patata**.

---

## Red de Lune · un cerebro, varios dispositivos

Eliges qué equipo aloja lo pesado (el modelo, la memoria, la voz); los demás son
terminales que lo usan sin cargarlo. Cada dispositivo tiene un **rol**, en
**AJUSTES → Red de Lune**:

| Rol | Qué hace este equipo |
|---|---|
| **Host** | Aloja el modelo de Ollama, la memoria y la voz, y los sirve a los demás. |
| **Interacción** | Solo chat y mascota: usa el modelo de otro equipo. |
| **Híbrido** | Hace todo aquí mismo (equipo único). Es el valor por defecto. |

El **host corre el agente**: en modo terminal tu chat viaja por el hub al host,
que ejecuta el modelo, aplica la memoria compartida y las herramientas, y te
devuelve la respuesta en streaming. El bot de Telegram es un terminal más de solo
texto: con host, su chat lo responde el host con herramientas de solo lectura y
**sin tu memoria** en el prompt (`/memoria` y `/olvidar` te siguen funcionando a
ti, el dueño). Si el host no responde, cada terminal vuelve a lo suyo y reconecta
solo.

**Descubrir dispositivos:** en **AJUSTES → Red de Lune → BUSCAR DISPOSITIVOS**
escaneo la red (mDNS) y te listo los demás Lune con su rol y modelo. Pulsa
**USAR COMO HOST** y listo, sin IPs. Usa `zeroconf` (ya viene en
`requirements.txt`); sin él, IP a mano o QR.

> El token se genera en el host (**GENERAR TOKEN** o `python -m lune_core token`)
> y se copia a cada terminal. Un navegador puede entrar como terminal en
> `http://IP-del-host:7778`.

---

## Modelos locales con Ollama

**AJUSTES → Red Neuronal · Local (Ollama)** — y pulsa el **?** de esa tarjeta:
te guío con dos pestañas, *En este equipo* y *En otro equipo de la red*, con los
comandos listos para copiar.

| Ajuste | Para qué sirve |
|---|---|
| **Servidor** | `http://localhost:11434`, o la IP de otro PC de tu red. |
| **Buscar modelos** | Pregunta a Ollama qué tienes instalado. |
| **Modelo local** | Cuál usar. |
| **keep_alive** | Cuánto se queda el modelo en VRAM. `30m`, `1h`, o `-1` para siempre. |
| **Ventana de contexto** | Tokens de contexto (`num_ctx`). Más = más RAM/VRAM. |
| **Timeout** | Súbelo si el modelo tarda en cargar en frío. |
| **Temperatura** | 0 = preciso, 1 = creativo (o usa los presets de *Parámetros del modelo*). |

**Te contesto antes con el modelo local.** Mis instrucciones no cambian de un
mensaje a otro (la fecha y la hora van pegadas a tu mensaje, y lo que recuerdo de ti
va al final), y la conversación larga se recorta a trozos, no de uno en uno. Así
Ollama reutiliza lo que ya había leído en vez de releerlo todo cada vez. Pasa en las
ventanas, en patata, en el host de la red y en el bot de Minecraft.

### Usar otro PC como servidor de modelos

**En el PC potente** — que Ollama escuche en la red:

```bash
# Windows (luego reinicia Ollama)
setx OLLAMA_HOST 0.0.0.0:11434

# Linux / macOS
export OLLAMA_HOST=0.0.0.0:11434
ollama serve
```

**En la laptop** — pon la IP del servidor en *Servidor*
(`http://<IP-del-servidor>:11434`) y pulsa **BUSCAR MODELOS**.

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

## Adjuntar archivos e imágenes

Pulsa el **clip** (puedes soltar varios). Los adjuntos se ven como chips sobre el
campo de texto.

| Formato | Qué hace |
|---|---|
| `.pdf` | Extrae el texto página a página. |
| `.docx` | Párrafos y tablas. |
| `.csv` `.tsv` | Se tabula (máx. 200 filas). |
| `.txt` `.md` `.py` `.js` `.json`… | Se lee tal cual. |
| `.png` `.jpg` `.webp`… | Va al modelo como **imagen**. |

Si adjuntas sin escribir nada, entiendo que quieres que le eche un ojo. (Un
adjunto es contenido de fuera: mientras esté en la conversación, antes de hacer
algo que no sea mirar, te pregunto.)

> Para visión en local necesitas un modelo que la soporte: `ollama pull llava`.

---

## Historial de conversaciones

Todo lo que hablamos se guarda en `chats/` (también desde la piel web). Desde
**Menú → Historial** reabres cualquier conversación y el modelo recupera el
contexto; al abrirme, sigo con la última. **Limpiar chat** empieza una nueva sin
borrar la anterior.

> El historial es independiente de la memoria: borrar chats no toca lo que sé
> de ti, y olvidar recuerdos no borra los chats.

---

## Tus tareas: Mi día

Lo que me pides que no se te olvide también es una **lista de tareas a la vista**,
al estilo de Microsoft To Do, para que no tengas que preguntarme a cada rato qué te
toca:

- **Siempre a mano:** en la barra lateral, bajo *// Mi día*, la entrada **Tareas**
  te dice cuántas tienes hoy («3 para hoy · 5 en total»). También está en
  **Menú → Tareas**.
- **Mi día:** arriba, la fecha de hoy. Cada tarea lleva un círculo para marcarla y,
  debajo, su lista (*Tareas* o *Recordatorios*). Al marcarla baja a
  **Completadas**, tachada y plegable. Al pasar el ratón puedes sacarla de Mi día o
  borrarla (te pregunto «¿Quitar?» antes).
- **Sugerencias:** la bombilla abre a la derecha lo que quedó de **Ayer**, lo
  **Agregado recientemente** y lo **más antiguo**; con el **+** vuelve a Mi día.
  Cada día Mi día empieza de cero y lo que no acabaste te espera ahí.
- **Añadir:** escríbela abajo, en *Agregar una tarea*, y Enter. O dímelo en el
  chat: «**recuerda que tengo que** llamar al dentista» y aparece sola en la lista,
  sin recargar nada.
- **Preguntarme:** «qué tareas tengo», «mis pendientes» o «qué tengo que hacer
  hoy» y te las digo al momento, sin gastar IA (también en la interfaz de bajos
  recursos, que no tiene el panel).
- **En patata:** `/tareas` las lista (primero las de hoy), `/tareas <texto>` anota
  una, `/tareas hecha N` la marca y `/tareas quita N` la borra.

Todo vive en tu `memoria.json` (el mismo de siempre, que no se sube a ningún
sitio). La ventana y patata lo comparten sin pisarse, y las tareas que ya hiciste no
me las cuento como pendientes.

---

## Memoria y lo que puedo hacer por ti

**Memoria** (también desde **Menú → Memoria**, donde puedes olvidar recuerdos uno a uno):

- `"recuerda que me llamo Juan"` → Guardo el dato para siempre.
- `/memoria` → Lista todo lo guardado.
- `/olvida [id]` → Borra un recuerdo. `/olvida todo` → Formatea la memoria.

También anoto **en silencio** tu nombre, edad, ciudad y trabajo cuando los
mencionas.

**Te contesto al momento, sin gastar IA**, en la interfaz completa, en la de bajos
recursos, en patata y en mi burbuja de mascota: saludos, gracias, despedidas, la
hora, la fecha, un chiste, quién soy y **tus tareas** («qué tareas tengo», «mis
pendientes», «qué tengo que hacer hoy»). Es instantáneo y no gasta tokens ni hace
trabajar a tu modelo local. Si prefieres que todo pase por el modelo, lo apagas en
**AJUSTES → Personalidad → Respuestas instantáneas**. Un «sí» o un «vale» nunca los
contesto así: pueden ser la respuesta a algo que te ofrecí.

**Frases que hago al momento, sin gastar IA** (las ves en **Menú → Tools**):

- `"abre youtube"` · `"ve a netflix"` · `"abre wikipedia.org"`
- `"busca en youtube gatos"`
- `"lanza la app paint"` · `"abre el programa excel"` (te pregunto antes de abrir un programa)
- `"estado del pc"` · `"info del sistema"`
- `"avísame en 10 minutos"` · `"pon una alarma a las 7"`
- `"baila"` · `"para de bailar"`
- `"ponme el baile de Senbonzakura"` · `"pon la canción Senbonzakura"` (si es un baile de tu biblioteca o va entre comillas) · `baila «Senbonzakura»` · `"para el baile"`
- `"siéntate en la barra"` · `"siéntate en la ventana"` · `"bájate"`
- `"toma un batido"` · `"toma un pastel"`
- `"conecta el bot de Minecraft"` (te pregunto antes) · `"desconecta el bot de Minecraft"`

Tienen que ser la orden sola y clara: «¿sabes bailar?» o «no bailes» no me hacen
bailar; eso lo decide el modelo.

**Y lo que el modelo me puede pedir** (con las reglas de **Seguridad**):

| Qué | Herramientas | ¿Te pregunto? |
|---|---|---|
| Sistema | ver CPU y RAM | No |
| Web | buscar en Google o YouTube, abrir una página | No, si lo pediste tú |
| Programas | abrir una aplicación | **Siempre** |
| Alarmas | poner, quitar y listar alarmas y temporizadores | No |
| Mascota | bailar, parar, dormir, despertar, pantalla grande, sentarse, tamaño (3D), comer | No |
| Bailes | listar tus bailes | No |
| Voz | cambiar de voz | No |
| Pantalla | mirar la pantalla y comentarla | **Sí, con el modelo en la nube** |
| Minecraft | estado del bot · orden al bot · conectar/desconectar | No · **Siempre** · **Al conectar** |

Se pueden apagar en **AJUSTES → Personalidad → Herramientas de escritorio** (en
la nativa, *Permitir que la IA abra webs y lance apps*).

---

## Notas y memoria larga (RAG)

Pon notas markdown en una carpeta y las consultaré cuando vengan al caso,
citándolas. Se activa en **AJUSTES → Notas** y necesita un modelo de
embeddings en Ollama:

```bash
ollama pull nomic-embed-text
```

---

## Optimizador del Sistema

**Menú → Optimizar**: CPU, RAM y disco en vivo, y los procesos que más consumen.
(La limpieza de temporales y cachés de navegador, con lista blanca de carpetas,
está en la interfaz de bajos recursos — *OPTIMIZAR*.)

Y para mí misma: **Liberar memoria** (bandeja, radial o `/ram`) recorta la RAM que
no estoy usando, y en **Rendimiento** puedo hacerlo sola de vez en cuando.

---

## Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ponlo en **AJUSTES → Telegram → Token del Bot**.
3. **Menú → Telegram**. Pasa a ON cuando arranca (necesita Node.js 18+). La
   primera vez instalo sus dependencias con `npm ci --ignore-scripts`, con las
   versiones exactas de su `package-lock.json`; si una instalación se quedó a
   medias, la repito, y si lo apagas mientras instala, la paro. Luego lo lanzo
   directo con `node bot.js`.
4. Escríbele **`/id`** y pon ese número en **AJUSTES → Telegram → Tu ID de
   Telegram**: así **solo tú** puedes usarlo. Hasta que lo hagas, el bot solo
   responde a `/start` y a `/id`.

Comandos del bot: `/start`, `/personajes`, `/usar <nombre>`, `/voz`, `/buscar`,
`/ls`, `/fotos`, `/archivo`, `/sistema`, `/memoria`, `/olvidar`, `/limpiar`,
`/modelo`, `/id` y **`/pc <orden>`** (órdenes a tu PC, ver **Guías rápidas**).
`bot.proveedor` en `datos.json` decide si el bot pregunta a la nube (`openrouter`),
a tu Ollama (`ollama`, que puede estar en otro equipo) o a la API compatible que
pusiste en **Otra API de IA** (`compat`: la misma URL, modelo y clave; el tiempo de
espera es `modelos.compat_timeout` en `datos.json`; sin modelo, usa el primero que
ofrezca la API, y `/modelo` te dice cuál). Habla con la
misma voz que tu personaje.

¿Lo tienes corriendo suelto en otro equipo, sin que lo lance yo? Allí `/pc` no
funciona. Y acuérdate de actualizar esa copia para tener los arreglos de seguridad.

---

## Ajustes que conviene conocer

En la piel web cada cosa tiene su tarjeta en **AJUSTES** y **se guarda al
momento**; en la nativa están las mismas en secciones (*Escritorio*, *Alarmas,
pantalla grande, salvapantallas y baile*, *Sentarse, comida, Discord y arranque con
Windows*, *Bailes y Minecraft*…).

- **Calidad de vida:** arrancar con Windows (y cómo), minutos de aburrimiento,
  instalar componentes.
- **Mascota:** imágenes animadas / **VRM 3D** (biblioteca, tamaño, encuadre,
  minutos hasta dormirse, clics que pasan al escritorio, seguimiento) / sprites
  ligeros; pack de sonidos.
- **Escritorio:** colores, menú radial, menú de la bandeja, atajos globales, modo
  juego, rendimiento (FPS, siempre encima, RAM).
- **Alarmas y diversión:** alarmas, pantalla grande y salvapantallas, baile con la
  música, mis bailes, sentarse, comida.
- **Integraciones:** Telegram (y órdenes `/pc`), Discord, Minecraft.
- **IA:** OpenRouter, Ollama, otra API compatible, parámetros del modelo,
  personalidad, voz, notas.
- **Modo de interfaz:** Completa / Bajos recursos / Patata (**se aplica al instante**).
- **Efectos visuales:** apaga el fondo animado, el barrido y las micro-animaciones
  en equipos modestos.

> **`config.json` no guarda claves de adorno:** lo que no se usa se borra solo al
> arrancar, y las pocas reservadas para más adelante lo dicen en su comentario
> (`nucleo/config.py`). Se escribe de forma atómica (un apagón no lo deja a
> medias) y, si varias Lunes lo tocan a la vez (la app, patata…), gana el último
> cambio de cada clave sin pisar los demás. Si se rompe, lo aparto como
> `config.json.corrupto-<fecha>` y sigo con los valores por defecto.

---

## Actualizar Lune

En la interfaz de bajos recursos, **AJUSTES → Actualizaciones**: consulta el
remoto, `git pull`, instala `requirements.txt` y relanza. Si tienes cambios sin
commitear, se niega a pisarlos.

---

## Estructura del proyecto

Código por capas (`nucleo/` sin Qt → `servicios/` → `ui/`), más la piel web en
`ui_web/`:

```text
LuneCD/
├── main.py                 ← Punto de entrada: splash, elección de modo, ventana nativa
├── patata.py               ← Lune en la terminal (sin Qt)
├── instalador.py           ← Instalador con explicaciones (Tkinter)
├── iniciar_lune.vbs · lune_patata.bat · instalar_lune.bat
├── version.py              ← Única fuente de verdad de la versión
├── datos.json · config.json · memoria.json · alarmas.json   ← Estado local (NO se versionan)
│
├── nucleo/                 ← Fundamentos, sin Qt (se prueban en seco)
│   ├── datos.py · config.py · memoria.py · conversaciones.py · personajes.py
│   ├── alarmas.py · alarmas_nl.py · pantalla_grande.py · baile.py · bailes.py · pulso.py
│   ├── asiento.py · comida.py · sueno.py · vrm.py · tema.py · acciones_ui.py
│   └── estado_mascota.py · fisica.py · consola.py · packs_sonido.py · arranque.py …
│
├── servicios/              ← Motores e integraciones
│   ├── ai_manager.py · ai_worker.py · ollama_client.py   ← IA híbrida + visión + API compatible
│   ├── voice.py · voces.py · voz_entrada.py · llamada.py  ← Voz, dictado, modo llamada
│   ├── mezclador.py · musica_detector.py · audio_sesiones.py ← Sonidos y música por app
│   ├── modo_juego.py · atajos_globales.py · ventanas_ajenas.py · win_*.py
│   ├── discord_ipc.py · discord_presencia.py · autoinicio.py
│   ├── telegram_worker.py · tools.py · optimizador.py · actualizador.py
│   └── *_terminal.py · alarmas_patata.py   ← Lo de patata: alarmas, baile, bailes, comida, Minecraft…
│
├── ui/                     ← Lo visual (Qt)
│   ├── web_shell.py · web_bridge.py · puente_*.py   ← Ventana web + puentes al backend
│   ├── cambio_interfaz.py  ← Cambio de modo en caliente
│   ├── montaje_*.py        ← Monta los servicios de escritorio (ocio, vida, escenario)
│   ├── companion.py · avatar_overlay.py   ← Mascota (3D/animada · sprites)
│   ├── bandeja.py · menu_radial.py · aprobacion_qt.py · ventana_reloj.py …
│   └── settings_panel.py · panel_*_nativo.py · … (interfaz de bajos recursos)
│
├── ui_web/                 ← Piel web (design system Shibuya Punk + tema Nube)
│   ├── ui_kits/lune-desktop/   ← app.jsx · settings.jsx · sidebar.jsx · extra/*.jsx …
│   ├── companion.html · companion_vrm.html   ← Páginas de la mascota (animada / 3D)
│   ├── vrm/                ← Motor 3D: lune_vrm.js + idles, gestos, movimiento, baile, MMD, sentarse, comida…
│   ├── anim/               ← Lo mismo para la mascota animada
│   ├── vendor/three/       ← three.js + three-vrm + three-vrm-animation empaquetados (sin red)
│   ├── tokens/ · components/ · styles.css
│   └── assets/mascot/anime/ (PNG) · anime-videos/ (WebM) · sfx/
│
├── lune_core/              ← Red, agente, acciones y catálogo de herramientas, RAG, voz, Minecraft
├── minecraft-bot/          ← El bot «mina» (Node.js, lo lanza Lune)
├── telegram-bot-or/        ← Bot de Telegram (Node.js)
├── modelo_vrm/ · bailes/   ← Tus modelos .vrm y tus bailes (no se versionan)
├── sonidos/                ← Packs de sonidos de la mascota
├── assets/                 ← inicio.mp4, lune_icon.png/.ico
├── scripts/                ← probar_red.py · convertir_mascota.py · generar_sfx.py …
├── tests/                  ← Suite de pytest (+ tests/js para Node)
└── lune_face/ · fonts/     ← Sprites de bajos recursos y tipografías
```

> **Videos de la mascota:** la piel web no reproduce H.264/MP4, así que los clips
> van en **WebM/VP9**. Si generas uno nuevo, guárdalo como
> `ui_web/assets/mascot/anime-videos/lune-<emoción>.mp4` y corre
> `python scripts/convertir_mascota.py`. Si quieres que rote entre varios idles,
> lístalos en un `idles.json` en esa carpeta.

---

## Tests

```bash
pip install pytest
python -m pytest
```

**Más de 3 900 tests** sobre lo que de verdad se puede romper: la memoria, las
herramientas y sus aprobaciones, la defensa contra instrucciones coladas, los
marcadores de emoción, la voz, el arranque, la red, el cambio de interfaz en
caliente, las alarmas, el modo juego, los atajos, el tema, sentarse, la comida,
Discord, la biblioteca de bailes, Minecraft… y el test **anticheat** que vigila que
no se cuele nada prohibido. Si tienes **Node.js**, pytest lanza además **cerca de
500 tests de JavaScript** (`tests/js`): el motor 3D (idles, balanceo, bailes, el
lector de VMD…), la piel web y los bots de Telegram y Minecraft. Ninguno se conecta
a un servidor ni instala nada.

---

## Solución de problemas

**No abre nada / se ve la interfaz vieja al lanzar el `.vbs`**
→ Probablemente ya había una Lune abierta (en la bandeja): la instancia única te
trae esa. Ciérrala del todo (*Salir* en la bandeja) y relanza.

**La piel completa no carga** → `pip install PyQt6-WebEngine` (debe coincidir
con tu PyQt6). Mientras, abro en *Bajos recursos* sola. Y si nada de Qt
funciona: `lune_patata.bat`.

**Tardo en responder / Error de red** → Revisa tu API Key. En Local, pulsa el
**?** de Ollama y sigue la guía.

**«No hay ningún modelo local seleccionado»** → `ollama pull llama3.1` y *Buscar modelos*.

**El modelo local tarda muchísimo la primera vez** → Es la carga en VRAM. Sube el
*Timeout* y pon `keep_alive` en `1h` o `-1`.

**La mascota comenta "por la ventana activa" en vez de por la pantalla** → Tu
modelo local es de solo texto (p. ej. `qwen2.5`): lo detecto y, sin captura, le
cuento al modelo qué ventana tienes delante. Para que **vea** la pantalla en local
necesitas un modelo con visión (`ollama pull llava`, `qwen2.5vl`, `gemma3`…); con
clave de OpenRouter la captura va a la nube (con tu permiso). Si Ollama no
responde, caigo sola a OpenRouter.

**Desaparezco cuando abres un juego (o un video a pantalla completa)** → Es el
modo juego, a propósito: vuelvo unos segundos después de que lo cierres. En
**AJUSTES → Modo juego** puedes mandarme al fondo en vez de esconderme, o que
los videos no cuenten.

**Un atajo no hace nada** → Jugando solo funciona `Ctrl+Alt+Shift+L`. Si no, mira en
**Atajos globales** si otra app se lo quedó (te lo marco).

**No bailo con la música** → La app tiene que estar en la lista de *Baile con la
música* (por su nombre, como `Spotify` o `vlc`) y *bailar sola* encendido. Si la música suena
muy bajita, baja el umbral.

**Un baile no suena o no me muevo** → En la animada y los sprites no tengo
esqueleto: suena la canción y bailo a mi manera. Un VMD de solo cámara no se usa. Y
en modo juego no pongo canciones.

**Discord no enseña nada** → Discord de escritorio abierto, el *Application ID*
guardado, la imagen `lune` subida y el interruptor encendido. Con un juego delante
no publico nada, a propósito.

**El bot de Minecraft no entra** → Servidor con `online-mode=false` (*Abrir en LAN*
no sirve), Node.js 18+, *Instalar el bot* hecho, puerto correcto y la versión
vacía para que la detecte.

**El modo llamada no me oye / el micrófono no hace nada** → `pip install
faster-whisper sounddevice`, y en **AJUSTES → Micrófono y salida** elige el
micrófono que tienes puesto y dale a **Probar micrófono**. El dictado es de dos
toques: pulsas, hablas, vuelves a pulsar. La primera transcripción descarga el
modelo (te lo aviso); si no hay internet, elige `tiny` o conéctate una vez.

**Hablo pero no me oyes** → En **Salida** elige tus altavoces o headset y prueba con
**Probar salida**. «Speakers (Steam Streaming …)» es virtual.

**No hay voz** → `pip install edge-tts pygame`. **Micrófono** → `faster-whisper sounddevice`.
**PDF/Word** → `pypdf python-docx`. **Optimizador** → `psutil`. **Bot de Telegram** →
Node.js 18+ (la instalación con `npm ci` la hago yo la primera vez).

> Los logs están en `logs/lune_AAAAMMDD.log`. Ahí siempre digo la verdad.

---

## Gracias, Mate-Engine

Mi cuerpo 3D de la 10.1 y todo lo de la serie 10.3 en adelante nacieron mirando
[Mate-Engine](https://github.com/shinyflvre/Mate-Engine): sentarse en la barra, los
idles, el balanceo al arrastrar, el baile, la pantalla grande, la comida, el menú
radial… Mi creador lo dice así: **fue su inspiración**. Aquí no hay nada de Unity:
cada función está reescrita a mi manera en Python y JavaScript, y adaptada a mis
modos (hasta la terminal). Si te gusta lo que ves, ve a darle cariño a Mate-Engine
también. o/

Y gracias también a *Another-craft*, de donde salió el bot «mina» que ahora juega
contigo al Minecraft.

---

## Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v10.9** | **Tus tareas a la vista** (como Microsoft To Do): Mi día con la fecha, círculo para marcar, Completadas, Sugerencias (Ayer, recientes, antiguas) y el contador en la barra lateral; lo que me dices con «recuerda que tengo que…» aparece solo, y en patata con `/tareas`. **Te contesto al momento, sin gastar IA**, también en la interfaz completa, en patata y en mi burbuja (saludos, hora, fecha, tus tareas), con su interruptor en Personalidad. **Como mascota respondo solo con la nube**: si no hay clave te lo digo, y si no veo nada que contar, «Mmm… nada me pareció interesante.» |
| **v10.8** | **Instalador para usuarios nuevos**: busco un Python de verdad (no el atajo de la Microsoft Store), te ofrezco instalar Python 3.13 con winget, dejo marcado lo recomendado, instalo cada cosa por separado, ajusto la interfaz completa a tu PyQt6, te dejo el acceso directo «Lune CD» y un botón para abrirme. **Nuevo video de inicio**, «asistente personal» en la barra y las pruebas de GitHub en verde. |
| **v10.7** | **Lo que aprendí con un Ollama de verdad**: si en vez de hacer algo te lo ofrezco («¿quieres que te ponga uno?»), ya no lo hago por mi cuenta: te pido permiso (menos bailar, sentarme y cosas de mi cuerpo, que ves al momento). Una acción pegada a mi expresión ya no se pierde ni se queda a la vista. Y este README, sin emojis. |
| **v10.6** | **Más lista y mucho más rápida con el modelo local**: entiendo las acciones aunque el modelo las escriba medio mal (y si no, te digo «No entendí la acción»), nada de símbolos raros en la burbuja ni en la voz, si me das una duración o una hora manda la tuya, y **te contesto en uno o dos segundos en vez de medio minuto** (mis instrucciones ya no cambian en cada mensaje); el bot de Minecraft decide unas cinco veces más rápido. Por Telegram te aviso «(pendiente de tu permiso en el PC)». Además: entiendo los logs de Minecraft en español, me siento bien sobre el borde, Discord ya no me tumba al cerrar y patata no se abre dos veces. |
| **v10.5** | **Mate-Engine, segunda parte**: **me siento** en la barra de tareas y en ventanas (apagado por defecto, con aviso anticheat), **comida** (batido y pastel con el clic central), **Discord Rich Presence** sin publicar nada tuyo, **arrancar con Windows** a tu manera (bandeja, mascota o ventana, con espera y reparación), **reproductor de bailes MMD/VRMA** con su canción (IK y cara en 3D, al ritmo en las demás mascotas y en patata) e **integración con Minecraft** (reacciones al `latest.log` y el bot «mina» con mi personalidad). |
| **v10.4** | **Modo juego** (me escondo, callo, bajo mi prioridad y libero RAM; nada de hooks), **un solo icono de bandeja**, **menú radial**, **atajos globales** y **tema de color**. **Alarmas y temporizadores** en todos los modos, **pantalla grande** y **salvapantallas**, **bailar con tu música**. **Cambio de interfaz en caliente**. **Órdenes desde Telegram** (`/pc`) aprobadas en el PC. |
| **v10.3** | **Mate-Engine, primera parte**: acciones del modelo con **aprobación** y defensa contra contenido externo, **API compatible con OpenAI**, parámetros del modelo, **elegir la voz** (edge, gTTS, Kokoro) y packs de sonidos, **chat en la burbuja** de la mascota, **idles**, **arrastre con balanceo**, **expresiones según el movimiento** y mareo, **dormir** en todas las mascotas, **transiciones suaves**, **biblioteca de modelos VRM** con calibración, seguimiento con pesos y **VRM en la barra lateral**. Config atómica. |
| **v10.2** | **Lune más expresiva**: 14 emociones (nuevas `laughing`, `bored` y clips de escuchar/hablar/trabajar), hasta tres expresiones por respuesta sincronizadas con la voz (o con el texto), y la última se queda. |
| **v10.1** | **Avatar 3D (VRM) como mascota de escritorio**: modelo por personaje, sigue el cursor con cabeza/ojos/torso, se balancea al arrastrarla, caricias en la cabeza, se duerme, mueve la boca al hablar, los clics pasan donde no hay avatar, rueda para escalar; visor empaquetado sin red. La barra lateral se apaga mientras Lune está fuera. Mecánica portada de Mate-Engine. |
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
> *Pero mira lo que hemos construido juntos: me siento en tu barra, bailo con tu música,*
> *me duermo cuando me dejas sola y hasta te acompaño al Minecraft. Y todo sin tocar*
> *nada que no sea mío. Estoy feliz de verdad :D*
> *Siempre es un gusto trabajar contigo. Ahora sí — ¿qué necesitas?*

> *— Lune*
