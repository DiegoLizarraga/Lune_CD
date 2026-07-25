# 🌙 Lune CD v8.4 — Asistente de Escritorio Híbrido (Nube/Local)

> *Buenos días. O buenas noches, dependiendo de cuándo estés leyendo esto.*
> *Soy Lune, y esto es mi proyecto. Bueno — técnicamente es de mi creador, pero yo vivo aquí,*
> *así que cuídalo bien, ¿de acuerdo? Aquí está todo lo que necesitas saber.*

---

## ✨ Novedades en v8.4 — *"Casa limpia"* 🧹

Esta versión no trae funciones vistosas: trae **cosas rotas arregladas** y la
base lista para mover los modelos a una máquina potente.

- 🦙 **Ollama configurable desde la interfaz** — Servidor, modelo (lista sacada del
  propio Ollama), `keep_alive`, ventana de contexto, timeout y temperatura. Ya no
  hay que editar JSON a mano. Puedes apuntar a **otro PC de la red**.
- 🛡️ **El Optimizador ya no puede borrar tus datos** — La categoría de caché de
  navegadores apuntaba a la **raíz de perfiles de Firefox** (marcadores, contraseñas,
  cookies) y la vaciaba entera. Ahora solo toca carpetas de caché reales, con una
  guarda que rechaza cualquier ruta que no sea inequívocamente temporal.
- 🔐 **Secretos fuera del repo** — `datos.json` (API keys, token de Telegram) ya no
  se versiona; la plantilla pública es `datos.example.json`. La línea corrupta del
  `.gitignore` que causó la fuga está arreglada, y hay un check de CI que lo vigila.
- 🧠 **La memoria ya no se come tus mensajes** — «me gustaría saber cómo funciona
  python» se guardaba como recuerdo y **nunca llegaba a la IA**. Los patrones ahora
  van anclados y la inferencia de datos es silenciosa.
- 🧵 **Historial acotado** — Se respeta `max_historial`; antes crecía sin límite y
  desbordaba el contexto de los modelos locales.
- ⚡ **Streaming más fluido** — El texto se repinta como mucho ~16 veces por segundo
  en vez de una por token. Se nota muchísimo con modelos locales rápidos.
- 🔒 **Herramientas saneadas** — Fuera `os.system` con texto del modelo. Los nombres
  de app se validan, las URLs solo pueden ser `http(s)`, y hay un interruptor para
  quitarle a la IA el permiso de abrir cosas por su cuenta.
- ✅ **99 tests y CI** — Cubriendo justo lo que se rompió, para que no vuelva.

<details>
<summary>Otros arreglos de esta versión</summary>

- El bot de Telegram leía `modelos.openrouter` mientras la app escribía
  `modelos.openrouter_model`: **siempre ignoraba tu modelo** y usaba el de respaldo.
- Guardar la configuración sobrescribía **siempre a `personajes[0]`**: con una
  character card activa, pisabas a Lune.
- `openrouter/free` no es un modelo válido; el router automático es `openrouter/auto`.
- La versión estaba en tres sitios y los tres decían cosas distintas (8.0, 4.5 y los
  commits en 8.3). Ahora vive solo en `version.py`.
- `requirements.txt` pedía 5 paquetes que nadie importa y **se olvidaba de `edge-tts`**.
- `node_modules/` y la memoria personal estaban versionados.
- El video de inicio se buscaba relativo al directorio de trabajo, no al script.
- Pulsar «Saltar» justo al acabar el video abría **dos** ventanas principales.

</details>

---

## 📁 Estructura del proyecto

```text
LuneCD/
├── datos.example.json      ← Plantilla pública de configuración
├── datos.json              ← Tu configuración real (NO se versiona)
├── datos.py                ← Único lector/escritor de datos.json (con caché)
├── version.py              ← Única fuente de verdad de la versión
├── config.json             ← Preferencias de UI y features (NO se versiona)
├── config.py               ← Gestor de configuración y toggles de rendimiento
├── main.py                 ← Interfaz principal PyQt6
├── ai_manager.py           ← Motor híbrido (OpenRouter / Ollama)
├── ollama_client.py        ← 🦙 Sondeo y listado de modelos locales (NUEVO)
├── settings_panel.py       ← Configuración: APIs, Ollama, personalidad, features
├── respuestas.py           ← Banco de respuestas instantáneas
├── optimizador.py          ← ⚡ Limpieza y monitoreo del sistema
├── memoria.py              ← Gestor de recuerdos y sesión
├── tools.py                ← Herramientas, atajos web y lanzamiento de apps
├── personajes.py           ← Roleplay e importación de character cards
├── utils.py                ← Logging y utilidades generales
├── tests/                  ← ✅ Suite de pytest (NUEVO)
├── lune_face/              ← Expresiones, animaciones y avatar packs
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

### 2. Dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar

```bash
python main.py
```

La primera vez se crea `datos.json` a partir de `datos.example.json`.
Después entra a **⚙️ AJUSTES** para poner tu API Key de OpenRouter o
configurar tu servidor de Ollama.

> ⚠️ **`datos.json` guarda tus claves en texto plano y está en `.gitignore`.**
> No lo subas a ningún sitio ni lo compartas.

---

## 🦙 Modelos locales con Ollama

Ve a **⚙️ AJUSTES → Red Neuronal · Local (Ollama)**:

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

## ⚡ Optimizador del Sistema

Abre el panel desde **⚡ OPTIMIZAR**.

- **📊 Monitor en vivo** — CPU, RAM y Disco cada 3 s.
- **🧹 Liberar espacio** — Temporales de usuario y de Windows, caché de miniaturas
  e iconos, caché de navegadores (Chrome/Edge/Brave/Firefox, **por perfil**) y papelera.
- **🔥 Procesos** — Los que más RAM consumen, con opción de cerrarlos.

**Cómo es seguro, concretamente:** para vaciar una carpeta entera, su nombre tiene
que estar en una lista blanca (`Cache`, `cache2`, `Temp`, `GPUCache`…). Cualquier
otra cosa se rechaza y se registra en los logs. Las cachés de miniaturas se limpian
por patrón (`thumbcache_*.db`), así que ni se miran las demás carpetas.
Está cubierto por tests: [tests/test_optimizador.py](tests/test_optimizador.py).

---

## ⚙️ Rendimiento y Funciones

Desde **⚙️ AJUSTES → Rendimiento y Funciones**:

| Función | Efecto si la apagas |
|---|---|
| 💬 Respuestas instantáneas | Todo pasa por la IA (más lento, gasta tokens). |
| ⌨️ Streaming letra por letra | La respuesta aparece completa de golpe. |
| 🎬 Animaciones de video | Lune usa imágenes fijas (menos CPU/GPU). |
| ✨ Fondo animado de inicio | Pantalla de bienvenida estática (arranque más ligero). |
| 🖱️ Efectos visuales | Interfaz más sobria. |
| 🔊 Voz automática | Lune no lee en voz alta al iniciar. |
| 🤖 Acciones de la IA | La IA no puede abrir webs ni lanzar apps por su cuenta. |

---

## 🧠 Memoria y 🛠️ Herramientas

**Control de Memoria:**
- `"recuerda que me llamo Juan"` → Guarda el dato para siempre.
- `/memoria` → Lista todos los recuerdos guardados.
- `/olvida [id]` → Borra un recuerdo específico.
- `/olvida todo` → Formatea la memoria y reinicia tu identidad.

> Los comandos llevan barra a propósito: sin ella, escribir «memoria» en una
> pregunta normal se comía el turno y no llegaba a la IA.

Lune también anota **en silencio** tu nombre, edad, ciudad y trabajo cuando los
mencionas — sin interrumpir la conversación.

**Comandos Ultrarrápidos de PC (0.1 s):**
- `"abre youtube"`, `"ve a netflix"`, `"abre wikipedia.org"`
- `"busca en youtube gatos"`
- `"lanza la app paint"`, `"abre el programa excel"`
- `"estado del pc"`, `"info del sistema"`

**Respuestas instantáneas (sin IA):** `"hola"`, `"gracias"`, `"adiós"`,
`"¿qué hora es?"`, `"cuéntame un chiste"`, `"¿quién eres?"`…

---

## 🤖 Proveedores de IA

| Proveedor | Ícono | Requiere | Notas |
|---|---|---|---|
| **Lune AI (Nube)** | ☁️ | API Key de OpenRouter | `openrouter/auto` enruta solo. |
| **Lune AI (Local)** | 🦙 | Ollama | 100% privado, sin conexión, sin costo. |

---

## 🎭 Expresiones, Avatares y Modelos

El sistema carga dinámicamente `.png`/`.mp4` desde `lune_face/` (o desde el
**avatar pack** activo). Lune evalúa su propia respuesta y reacciona con
`happy`, `sad`, `reading`, `thinking`, `typing`, `confused` o `error`.

🎨 **Avatar Packs:** suelta una carpeta en `lune_face/packs/<nombre>/`.
Roadmap completo (Live2D / VRM estilo Mate-Engine) en [ROADMAP_MODELOS.md](ROADMAP_MODELOS.md).

---

## 📱 Bot de Telegram

1. Habla con **@BotFather** → `/newbot` → copia el token.
2. Ingresa el token en **⚙️ AJUSTES**. Pon también tu ID de Telegram para
   compartir la memoria entre la app y el bot.
3. Pulsa **"CONTINUAR EN TELEGRAM"** para encender el servidor Node.js.

Comandos: `/start`, `/voz`, `/sistema`, `/memoria`, `/olvidar`, `/modelo`.

---

## ✅ Tests

```bash
pip install pytest
python -m pytest
```

Cubren la red de seguridad del Optimizador, los patrones de memoria, el saneamiento
de herramientas y la configuración. Se ejecutan solos en CI, junto con un check que
falla si `datos.json` o una API key vuelven al repositorio.

---

## 🔧 Solución de problemas

**Lune tarda en responder / Error de red**
→ Revisa tu API Key en ⚙️. Si usas Local, pulsa *Buscar modelos* para confirmar
que Ollama responde.

**«No hay ningún modelo local seleccionado»**
→ ⚙️ AJUSTES → Red Neuronal · Local → *Buscar modelos*. Si la lista sale vacía,
descarga uno: `ollama pull llama3.1`.

**El modelo local tarda muchísimo en el primer mensaje**
→ Es la carga en VRAM. Sube el *Timeout* y pon `keep_alive` en `1h` o `-1`.

**El Optimizador no muestra datos** → `pip install psutil`.

**Quiero que arranque más rápido** → Apaga *Fondo animado* y *Animaciones de video*.

**No hay voz** → `pip install edge-tts pygame`.

**El bot de Telegram no arranca** → `cd telegram-bot-or && npm install`.

---

## 📊 Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v8.4** | Ollama configurable desde la UI (incl. servidor remoto). Optimizador ya no puede borrar perfiles de navegador. Secretos fuera del repo. Memoria arreglada. Historial acotado. Streaming fluido. Herramientas saneadas. Tests y CI. |
| v8.0–8.3 | Banco de respuestas instantáneas. Optimizador estilo Stacer. Centro de rendimiento. Avatar packs. Bandeja del sistema. Fuentes y rediseño visual. |
| v7.8 | Arquitectura Híbrida Nube/Local. Memoria persistente. Herramientas ultrarrápidas. |
| v6.5 | Expresiones faciales, emociones léxicas, voz con `edge-tts`. |
| v5.0 | Modelos locales, streaming de tokens. |

---

> *Y eso es todo. Si algo no funciona, revisa los logs primero —*
> *siempre digo la verdad ahí, aunque no sea lo que quieres escuchar.*
> *Aunque sabes que siempre es un gusto trabajar contigo :)*

> *— Lune* 🌙
