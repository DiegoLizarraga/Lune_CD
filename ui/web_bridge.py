"""
ui/web_bridge.py — Puente entre la UI web (Shibuya Punk) y el backend de Lune.

La ventana web (ui/web_shell.py) muestra el diseño real en una QWebEngineView y
expone ESTE objeto por QWebChannel como `window.lune`. El JavaScript llama a los
slots (enviar/detener…) y escucha las señales (chunk/done/acto/herramienta) para
pintar el chat con el modelo, la memoria y las herramientas de verdad.

Reutiliza AIWorker (mismo hilo de consulta que la app nativa), MemoriaManager,
ToolManager y AIManager: la lógica de chat es la misma, solo cambia la piel.

Acciones del modelo (corte 2): el modelo pide cosas con `<|CALL ["herramienta",
{args}]|>`. Al terminar la respuesta, `_on_done` se las pasa al Ejecutor
(ui/acciones_qt.AccionesQt): lo permitido se hace; lo que pide permiso se
pregunta con el modal de la página (`aprobacion_pedida` → `resolver_aprobacion`)
si la ventana está delante, o con un DialogoAprobacion junto a la asistente si no.
El formato antiguo (ABRIR_URL:, TOOL:) ya no se ejecuta, solo se borra del texto.
El origen del turno manda: con texto de terceros en el prompt (adjuntos) solo
se permiten las herramientas de LECTURA. Lo que pides con tus palabras («abre
youtube», «lanza paint», también en el modo llamada) va al mismo Ejecutor
(tools.detectar_llamadas): lanzar_app pide permiso igual.

La página es el eslabón débil (si algo la navegara a otra web, esa web tendría
window.lune): get_config no da claves en claro (MASCARA_CLAVE; con ella, guardar y
probar conservan la guardada, y la de la API compatible solo viaja a su URL),
resolver_aprobacion solo contesta lo que se le preguntó a la página y los modelos
3D se eligen por nombre de modelo_vrm/, nunca por ruta.

Órdenes desde Telegram (/pc): con «Órdenes desde Telegram» activado y tu ID de
Telegram puesto, el bot que lanza `telegram_toggle` manda cada orden por su
stdout (servicios/telegram_worker.py) y llega a `_orden_remota` (NO es un slot
de la página). Sale en el chat como «📱 Telegram: …»; un comando directo («abre
youtube») va al Ejecutor sin IA y lo demás es un turno de IA con origen
'remoto'. TODA acción se aprueba aquí (modal o junto a la asistente), nunca desde
Telegram; la respuesta y cada ✓/✕ vuelven al chat de Telegram.

Modo de interfaz en caliente (ui/cambio_interfaz.py): `cambiar_interfaz(modo)` (Ajustes)
emite `interfaz_pedida`; la ventana web se la pasa a GestorInterfaz, que hace el relevo y
guarda interfaz.modo (guardar_config ya no lo toca). Con `persistir_chats` (lo pide
ui/web_shell.py) la conversación se guarda en chats/ como en la nativa, con la marca de
texto de terceros o de Telegram; `retomar_sesion` la sigue tras un cambio de modo (y el
modelo la recuerda) y `estado_inicial()` da a la página proveedor, voz, bot, asistente y
mensajes para pintarse al cargar. Al arrancar (no en un cambio de modo) la ventana llama a
`restaurar_ultima()`: la última conversación sigue aquí si chat.restaurar_ultima.
Limpiar el chat o abrir otra conversación con una orden de Telegram esperando tu permiso
le contesta «Se detuvo…» (la pregunta se cierra sin hacer nada); parar el bot con una
orden a medio responder o esperando tu permiso, también. Una sola vez por orden: al
avisar se limpia su marca (Detener + limpiar chat no la repiten).

Modo llamada: lo transcrito entra por la página (`usuario_dijo` → `enviar`) y se apunta
en `_llamada_transcrito`; si lo que se envía es eso, lo que detecte detectar_llamadas va
al Ejecutor con ctx['llamada'] = True: todo lo que no sea de lectura pide permiso («Lo oí
en la llamada»: puede ser la tele u otra persona). El turno de IA va como siempre.

Corte 4 (bandeja única, radial, atajos, modo juego): la asistente se crea sin icono propio
(`crear_asistente(..., bandeja=False)`); `pausar_aburrimiento(on)` lo usa el modo juego
(AnfitrionWeb) y `comentar_pantalla` no mira la pantalla con un juego delante.

Cortes 9/10: mientras el hilo de la IA vive, el BusEstado del escritorio dice `pensando`
(BusEstado.pensar, fuente «chat»; lo apaga el finished de ese hilo): el bot de Minecraft
pausa su modelo (comparten Ollama) y Discord pone «Pensando…».

Chat de la asistente: la cajita que abre el doble clic (ui/chat_asistente.py) llama
a `enviar_desde_asistente(texto)`, que entra por el mismo flujo que el chat de la
ventana (mismo historial y memoria); la respuesta se ve también en la burbuja de
la asistente (`burbuja_texto` / `burbuja_fin`).

Bienvenida (11, nucleo/bienvenida.py): si la memoria aún no sabe nada de ti, Lune te hace
tres preguntas por el chat (nombre, cómo eres, cómo quieres que sea contigo). La primera
va en `estado_inicial()` como último mensaje de Lune (la página lo pinta al cargar; un
`done` antes de que la página conecte se perdería). Tus respuestas no van al modelo:
`_enviar` las intercepta (sin adjuntos) antes que las herramientas, la memoria y el banco,
y la siguiente pregunta sale por `done`; también desde la burbuja de la asistente en
escritorio. Las órdenes de Telegram no pasan por ahí. /conocernos la repite; /saltar la deja.

Asistente y VRM (corte 3):
  · Herramientas del modelo `asistente_dormir`, `asistente_despertar` y
    `asistente_tamano` (nucleo/sueno.py, nucleo/vrm.py) con la asistente flotante que
    esté a la vista. Solo se ofrecen con la asistente fuera: el modo del turno pasa
    de "normal" a "asistente" (animada o sprites) o "vrm" (3D), que es donde las
    pone el catálogo (lune_core/catalogo_herramientas.py).
  · Biblioteca de modelos (extra/vrm_biblioteca.jsx): vrm_biblioteca, vrm_meta,
    vrm_miniatura, vrm_ajustes, vrm_borrar y vrm_params. Solo nombres de archivo de
    modelo_vrm/, nunca rutas.
  · VRM en la barra lateral: `vrm_barra()` dice qué modelo publicó ui/web_shell.py
    en /vrm/actual.vrm; `modelo_vrm_cambio` (personaje, modelo o render cambiaron)
    y `vrm_params_cambio` (calibración del modelo actual) avisan a web_shell para
    que republique y recargue la barra.

Probar cada apartado (extra/diagnostico.jsx; la lógica, sin Qt, en servicios/pruebas.py):
`openrouter_probar(json)`, `ollama_probar(url)` y `telegram_probar(json)` prueban lo ESCRITO
en Ajustes (la máscara = lo guardado) fuera del hilo de Qt y nunca devuelven la clave ni el
token; `dictado_probar(json)` graba ~3 s y lo transcribe (señal `dictado_prueba`);
`diagnostico_iniciar()` es «Comprobar que todo funciona» (servicios/diagnostico con red, item
a item por la señal `diagnostico`, ui/pruebas_qt.DiagnosticoWorker; `diagnostico_parar()` lo
corta). Al cerrar, los hilos de prueba se paran y se retienen. Mientras «Probar dictado»
graba, el micrófono del chat, la llamada y «Probar micrófono» esperan.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtCore import (QCoreApplication, QEventLoop, QMetaObject, QObject, Qt, QThread,
                          QTimer, pyqtSignal, pyqtSlot)
from PyQt6 import sip

from nucleo.bienvenida import Bienvenida, ya_preguntada
from nucleo.config import Config
from nucleo.memoria import MemoriaManager
from nucleo.respuestas import AVISO_ASISTENTE_SIN_NUBE, BancoRespuestas
from nucleo import datos, personajes, sueno, vrm
from servicios.ai_manager import AIManager
from servicios.ai_worker import AIWorker, ORIGEN_NO_CONFIABLE, ORIGEN_REMOTO, ORIGEN_USUARIO
from servicios.tools import ToolManager, ctx_acciones
from servicios.telegram_worker import (AVISO_TG_DESACTIVADAS, AVISO_TG_DETENIDA, AVISO_TG_OCUPADA,
                                       AVISO_TG_PENDIENTE, PREFIJO_IA, PREFIJO_TELEGRAM, SIN_TEXTO,
                                       con_aviso_pendiente, ordenes_activas)
from servicios.voice import VoiceEngine
from lune_core import marcadores, expresiones
from lune_core.acciones import limpiar_texto
from ui.escritorio import ServiciosEscritorio, crear_asistente

# Emoción canónica del modelo → estado de asistente del set anime (assets/asistente/anime).
EMOCION_A_ASISTENTE = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
    # v10.1
    "laughing": "laughing", "bored": "bored",
}


MODO_ACCIONES = "normal"          # modo del catálogo de herramientas en la piel web
# Comentar la pantalla con un juego delante (modo juego, corte 4): no se mira.
AVISO_JUEGO_PANTALLA = "En modo juego no miro la pantalla. Cuando termines la partida, pídemelo otra vez."
ESPERA_UI_S = 5.0                 # herramientas de la asistente: espera máxima al hilo de Qt
# _esperar_en_hilo con otra espera en curso: no se anida, se contesta esto al momento.
OCUPADO = object()
MENSAJE_OCUPADO = "Estoy terminando otra prueba; inténtalo de nuevo en unos segundos."
# Vista «Optimizar» (sistema_info): la CPU medida desde la llamada anterior vale si esa
# llamada fue hace poco (la vista pide cada 3 s); los procesos se cuentan en un hilo.
SISTEMA_CPU_CEBADA_S = 30.0
SISTEMA_PROCESOS_CADA_S = 2.5
# Stream del chat: como mucho un `chunk` (y un eco en la burbuja de la asistente) cada
# tantos ms; el acumulado definitivo sale siempre antes de `done`.
CHUNK_CADA_MS = 40


def nombre_modelo_seguro(nombre: Any) -> str:
    """Nombre de un .vrm de modelo_vrm/ tal como llega de la página, validado.

    Solo el nombre del archivo: nada de «..», «/», «\\», unidades («C:») ni rutas
    absolutas (nucleo.vrm acepta rutas en algunas funciones internas; el puente
    no). Lo demás (extensión .vrm, caracteres de control, nombres de dispositivo
    de Windows) lo comprueba nucleo.vrm. ValueError si no vale.
    """
    n = str(nombre or "").strip()
    if (not n or ".." in n or any(c in n for c in "/\\:") or n != Path(n).name
            or Path(n).is_absolute()):
        raise ValueError("Nombre de modelo no válido: solo el nombre del archivo .vrm, sin carpetas.")
    return vrm._nombre_seguro(n)


def _ctx_dict(ctx: Any) -> dict:
    """El ctx que pasa el Ejecutor a un handler (dict, objeto o None) como dict nuevo."""
    if ctx is None:
        return {}
    if isinstance(ctx, Mapping):
        return dict(ctx)
    return {"contexto": ctx}

# Claves planas de la voz de salida (Ajustes → VozCard) → config voz.*
_CLAVES_VOZ = ("motor_salida", "edge_voz", "edge_rate", "edge_pitch", "gtts_tld", "kokoro_voz")
# Parámetros del modelo (Ajustes → AvanzadoCard) → datos.json modelos.*
_CLAVES_MUESTREO = ("temperatura", "top_p", "top_k", "min_p", "repeat_penalty")
# Contexto de Ollama: el mismo rango que `/ctx` de patata (patata.CTX_MIN/CTX_MAX).
_CONTEXTO_MIN, _CONTEXTO_MAX = 512, 131072

# Claves secretas (OpenRouter, Telegram, API compatible): get_config nunca las da en
# claro, solo esta máscara si hay una guardada (y «<clave>_configurada»). Si la
# página devuelve la máscara (o algo con sus puntos), se conserva la guardada.
MASCARA_CLAVE = "•" * 8
_CARACTER_MASCARA = "•"


def _mascara(valor: Any) -> str:
    """La máscara si hay clave guardada; "" si no."""
    return MASCARA_CLAVE if str(valor or "").strip() else ""


def _instalada() -> bool:
    """¿Es la Lune instalada (Setup.exe)? nucleo/rutas.INSTALADA, leído en cada llamada."""
    from nucleo import rutas
    return bool(rutas.INSTALADA)


def _como_instalar(*paquetes: str) -> str:
    """Cómo conseguir lo que falta (nucleo/rutas.como_instalar: pip desde el código)."""
    from nucleo import rutas
    return rutas.como_instalar(*paquetes)


def _sin_motor_de_voz() -> str:
    return f"No hay motor de voz ({_como_instalar('edge-tts', 'pygame')})."


def _clave_nueva(valor: Any):
    """Lo que la página manda en un campo de clave: None = conservar la guardada
    (la máscara sin tocar o con sus puntos: una clave real no los lleva); si no,
    la clave escrita ("" = borrarla)."""
    v = str(valor if valor is not None else "").strip()
    if _CARACTER_MASCARA in v:
        return None
    return v


def _objeto_json(payload: Any) -> dict:
    """El JSON que manda la página como dict ({} si no es un objeto)."""
    try:
        c = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return {}
    return c if isinstance(c, dict) else {}


def _provider_id(web_provider: str) -> str:
    """'local' → ollama · 'cloud' → openrouter · 'compat' → compat (lo que usa la UI web).
    Los id del backend ('ollama', 'openrouter') también valen."""
    p = str(web_provider or "").strip().lower()
    if p in ("local", "ollama"):
        return "ollama"
    if p == "compat":
        return "compat"
    return "openrouter"


def _numero(valor, tipo=float):
    """Número de la interfaz (o None si viene vacío / null / basura)."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return int(v) if tipo is int else v


def voz_para_personaje(actual: dict, motor: str, edge_voz: str, kokoro_voz: str,
                       rate: str, pitch: str, tld: str) -> dict:
    """La voz propia del personaje con lo elegido en Ajustes (motor 'auto' = sin motor
    fijo). La misma regla que el panel nativo (ui/settings_panel.voz_para_personaje)."""
    nueva = dict(actual or {})
    if motor in ("", "auto"):
        nueva.pop("motor", None)
    else:
        nueva["motor"] = motor
    if motor in ("", "auto", "edge"):
        nueva["id"] = edge_voz
    elif motor == "kokoro":
        nueva["id"] = kokoro_voz
    nueva["rate"], nueva["pitch"], nueva["tld"] = rate, pitch, tld
    return nueva


def voz_personaje_con_cambios(propia: dict, cambios: dict, efectiva: dict) -> dict:
    """La voz propia del personaje con SOLO lo que cambió en Ajustes (`cambios`,
    claves de _CLAVES_VOZ; `efectiva` = la voz que sonaba, de _config_voz). Lo que
    no cambió no se escribe: ni el tono ni el acento de config acaban fijados en él."""
    nueva = dict(propia or {})
    motor = str(cambios.get("motor_salida", efectiva.get("motor_salida", "auto")) or "auto")
    if "motor_salida" in cambios:
        if motor in ("", "auto"):
            nueva.pop("motor", None)
        else:
            nueva["motor"] = motor
    if motor in ("", "auto", "edge"):
        if "edge_voz" in cambios or "motor_salida" in cambios:
            nueva["id"] = cambios.get("edge_voz", efectiva.get("edge_voz"))
    elif motor == "kokoro":
        if "kokoro_voz" in cambios or "motor_salida" in cambios:
            nueva["id"] = cambios.get("kokoro_voz", efectiva.get("kokoro_voz"))
    for clave, campo in (("edge_rate", "rate"), ("edge_pitch", "pitch"), ("gtts_tld", "tld")):
        if clave in cambios:
            nueva[campo] = cambios[clave]
    return nueva


class LuneBridge(QObject):
    # ── Señales hacia el JS ──────────────────────────────────────────────────────
    chunk = pyqtSignal(str)                 # texto ACUMULADO del stream
    done = pyqtSignal(str, str)             # (texto_final_limpio, estado_asistente)
    acto = pyqtSignal(str)                  # estado de asistente durante la respuesta
    emocion = pyqtSignal(str, float)        # (estado_asistente, intensidad 0..1) al terminar
    herramienta = pyqtSignal(bool, str, str, str)   # (ok, icono, titulo, detalle)
    estado = pyqtSignal(str)                # 'live' | 'busy' | 'error'

    # Señales de estado hacia el JS (toggles y paneles).
    voz_estado = pyqtSignal(bool)
    telegram_estado = pyqtSignal(bool, str)
    asistente_estado = pyqtSignal(bool)
    aviso = pyqtSignal(str)                 # toast breve para el usuario
    adjuntos_cambio = pyqtSignal(str)       # json de nombres de archivos pendientes
    grabando = pyqtSignal(bool)             # micrófono grabando/parado
    dictado = pyqtSignal(str)               # texto transcrito del micrófono
    llamada_estado = pyqtSignal(bool, str)  # modo llamada: (activa, estado/aviso)
    usuario_dijo = pyqtSignal(str)          # en llamada: lo que dijo el usuario → el JS lo envía
    mic_prueba = pyqtSignal(str)            # resultado json de «Probar micrófono»
    # Pruebas de Ajustes (extra/diagnostico.jsx; servicios/pruebas.py y servicios/diagnostico.py):
    # «Comprobar que todo funciona»: json {tipo: inicio|item|fin, …} (un item por comprobación,
    # al final el resumen) · «Probar dictado»: json {fase, ok, texto, mensaje}.
    diagnostico = pyqtSignal(str)
    dictado_prueba = pyqtSignal(str)
    # Ajustes → Sistema → Actualizaciones (extra/actualizaciones.jsx; ui/actualizacion_qt.py):
    # json {fase: buscando|hay|al_dia|descargando|lista|instalando|error, version, notas, bytes, total, pct, mensaje}
    actualizacion = pyqtSignal(str)
    # Acciones del modelo que piden permiso (modal de la página, AprobacionHost):
    aprobacion_pedida = pyqtSignal(str)     # json de la petición {id, herramienta, args, resumen…}
    aprobacion_resuelta = pyqtSignal(str)   # id: ya no hace falta enseñarla (caducó o se canceló)
    usuario_asistente = pyqtSignal(str)       # lo que escribiste en la cajita de la asistente
    proveedores_cambio = pyqtSignal(str)    # json de proveedores(): la API compatible apareció o se fue
    # VRM de la barra lateral (las escucha ui/web_shell.py, que publica /vrm/actual.vrm):
    modelo_vrm_cambio = pyqtSignal()        # personaje, modelo por defecto, biblioteca o render cambiaron
    vrm_params_cambio = pyqtSignal(str)     # json de params del modelo actual (calibración, seguimiento)
    personaje_cambio = pyqtSignal(str)      # nombre del personaje activo nuevo (la barra reintenta su 3D)
    # Ajustes → «Modo de interfaz»: la ventana lo reenvía a GestorInterfaz (ui/cambio_interfaz.py).
    interfaz_pedida = pyqtSignal(str)
    _en_ui_senal = pyqtSignal(object)       # interna: fn() a correr en el hilo de Qt (herramientas)
    _resultado_remoto = pyqtSignal(object, str)   # interna: (ResultadoAccion, id de la orden de Telegram)
    _hablando = pyqtSignal(bool)            # interna: la voz suena (desde el hilo de audio)
    _acto_voz = pyqtSignal(str)             # interna: empieza a sonar un tramo con esta expresión
    _voz_error = pyqtSignal(str)            # interna: la voz falló (desde el hilo de audio)

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None,
                 voice=None, parent=None, *, opciones_acciones=None,
                 persistir_chats: bool = False, diferir_servicios: bool = False):
        """`opciones_acciones` van a AccionesQt / crear_ejecutor (audit_path, programar…; tests).
        `persistir_chats`: la conversación se guarda en chats/ (la ventana web lo pide;
        los tests no, así no escriben en la carpeta real). `diferir_servicios`: los
        servicios de escritorio (atajos globales…) no arrancan hasta que la ventana
        llame a escritorio.iniciar() (cambio de modo con la ventana anterior viva)."""
        super().__init__(parent)
        self._persistir_chats = bool(persistir_chats)
        self._ultima_orden_tg = ""          # id de la última orden de Telegram aceptada
        self.config = config or Config()
        self.ai = ai_manager or AIManager()
        self.memoria = memoria or MemoriaManager()
        self.tools = tools or ToolManager()
        self.voice = voice or VoiceEngine(self.config)
        # Respuestas instantáneas sin modelo (saludos, gracias, hora, fecha, tus tareas…),
        # como la nativa: antes la web mandaba hasta un «hola» al modelo.
        try:
            nombre_bot = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune")).get("nombre", "Lune")
        except Exception:
            nombre_bot = "Lune"
        self.banco = BancoRespuestas(nombre_asistente=nombre_bot, tareas=self._resumen_tareas)
        self._worker: AIWorker | None = None
        # Bienvenida (11, nucleo/bienvenida.py): las tres preguntas cuando aún no te conozco.
        # Se crea al primer uso (estado_inicial o tu primer mensaje); la voz dice cada
        # pregunta una sola vez por proceso (Bienvenida.por_decir). _bienvenida_marcas: qué
        # pregunta (clave_paso) se ve en la página y en la burbuja de la asistente en escritorio
        # (solo cuenta como respuesta lo que escribes donde la viste). _bienvenida_sin_guardar:
        # la pregunta que se ve en la página y aún no está en chats/ (va antes del primer
        # turno que se guarde, sea respuesta o no).
        self._bienvenida = None
        self._bienvenida_marcas = {"ventana": None, "burbuja": None}
        self._bienvenida_sin_guardar = None
        self._turno: dict = {}              # origen, ctx y si salió del chat de la asistente
        self._provider_web = "local"        # proveedor elegido en la página (para la asistente)
        self._compat_borrador = None        # URL/clave/modelo aún sin guardar (Probar conexión)
        self._tg_worker = None
        self._overlay = None
        self._chats = None
        self._adjuntos_pend = []            # documentos/imágenes cargados para el próximo envío
        self._grabadora = None
        self._transcriptor = None
        self._probador = None               # hilo de «Probar micrófono»
        self._diag_worker = None            # hilo de «Comprobar que todo funciona»
        self._dictado_prueba = None         # hilo de «Probar dictado»
        self._llamada = None                # LlamadaWorker mientras el modo llamada está activo
        self._oido_llamada = ""             # lo último transcrito en la llamada (la página lo envía)
        # En modo llamada, la respuesta final la habla el worker (bloqueando) y
        # luego vuelve a escuchar; por eso se engancha a `done`.
        self.done.connect(self._llamada_entregar)
        # La voz avisa cuándo suena (hilo de audio) → señal → boca del avatar VRM. No se
        # guarda la señal ligada (self._hablando.emit): el hilo de voz puede llamarla con
        # el puente ya borrado (AttributeError o violación de acceso); _aviso_hablando
        # comprueba que siga vivo, y cerrar_escritorio la desengancha.
        self._hablando.connect(self._on_hablando)
        try:
            self.voice.al_hablar = self._aviso_hablando
        except Exception:
            pass
        # Expresiones: hasta tres por respuesta; con voz cambian al ritmo de la voz,
        # sin voz según llega el texto (o al ritmo de lectura). La última se queda.
        self._acto_voz.connect(self._expresar)
        self._seguidor = None               # SeguidorActs del stream en curso
        self._stream_iniciado = False
        self._expresado_en_stream = False
        self._timers_plan = []              # expresiones programadas (sin voz, sin stream)
        self._gen = 0                       # generación del envío: ignora señales de workers viejos
        self._eco_texto = ""                # lo último que salió en la burbuja de la asistente (este turno)
        self._chunk_pend = None             # (gen, acumulado) del stream aún sin emitir (_on_chunk)
        self._chunk_t = 0.0                 # time.monotonic() del último `chunk` emitido
        self._chunk_timer = None            # QTimer single-shot del agrupado (_timer_chunk)
        self._esperando_hilo = False        # _esperar_en_hilo en curso (no se anidan)
        # Aburrimiento: si pasas N minutos sin escribirle, Lune se aburre y te dice
        # algo (una sola vez por racha; se rearma con tu siguiente mensaje).
        self._aburrida_t = QTimer(self)
        self._aburrida_t.setSingleShot(True)
        self._aburrida_t.timeout.connect(self._aburrida)
        self._aburrimiento_pausado = False  # modo juego: pausar_aburrimiento(True)
        self._rearmar_aburrimiento()
        # Servicios de escritorio (ui/escritorio.py): estado compartido de la
        # asistente, tabla de prioridades y registro de controladores. Recibe la
        # asistente flotante en _crear_asistente y se cierra al salir de la app.
        self.escritorio = ServiciosEscritorio(self.config, voice=self.voice, ai=self.ai,
                                              bridge=self, parent=self)
        if not diferir_servicios:
            self.escritorio.iniciar()
        # Las herramientas de la asistente pueden llegar desde otro hilo (el Ejecutor
        # tras una aprobación): lo que toca la ventana va al hilo de Qt por señal.
        self._hilo_qt = threading.get_ident()
        self._en_ui_senal.connect(self._correr_en_ui)
        # Lo que ui/web_shell.py publicó para la barra lateral ({url, v, archivo, params}).
        self.vrm_barra_info: dict = {}
        # Acciones del modelo (<|CALL …|>): los handlers de esta app (cambiar_voz, las
        # de la asistente…) en el ToolManager y un Ejecutor con aprobación visible
        # (ui/acciones_qt.py).
        self._registrar_herramientas_asistente()
        self.escritorio.conectar_herramientas(self.tools)
        self.acciones = self._crear_acciones(opciones_acciones or {})
        # Resultados de las órdenes desde Telegram: al chat y de vuelta al bot.
        self._resultado_remoto.connect(self._on_resultado_remoto)
        # La voz avisa si falla (voz inexistente, sin red…) en vez de quedarse muda.
        self._voz_error.connect(self._on_voz_error)
        try:
            self.voice.on_error = self._aviso_voz_error      # igual que al_hablar
        except Exception:
            pass
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.cerrar_escritorio)

    def cerrar_escritorio(self):
        """Al salir: ninguna pregunta «¿Lo hago?» colgada, servicios de escritorio parados
        y los avisos de la voz desenganchados (el hilo de audio ya no llama a este puente)."""
        self._soltar_voz()
        self._soltar_pruebas()
        act = getattr(self, "_act", None)
        if act is not None:
            try:
                act.detener()                        # la descarga en curso se corta
            except Exception:
                pass
        acc = getattr(self, "acciones", None)
        if acc is not None:
            try:
                acc.cerrar()
            except Exception:
                pass
        esc = getattr(self, "escritorio", None)
        if esc is None:
            return
        try:
            esc.cerrar()
        except Exception:
            pass

    # ── Acciones del modelo y aprobaciones ───────────────────────────────────────
    def _crear_acciones(self, opciones: dict):
        """AccionesQt con el modal web como pregunta; None si el ToolManager no sabe crear Ejecutores."""
        if not callable(getattr(self.tools, "crear_ejecutor", None)):
            return None
        try:
            from ui.acciones_qt import AccionesQt
            acc = AccionesQt(self.tools,
                             ventana_visible=lambda: self._ventana_a_la_vista(),
                             ancla=lambda: self._ancla_asistente(),
                             preguntar=self._preguntar_web,
                             cerrar_pregunta=self.aprobacion_resuelta.emit,
                             parent=self, **opciones)
        except Exception as e:
            from nucleo.utils import log_error
            log_error(f"[acciones] no pude crear el Ejecutor: {e}")
            return None
        acc.resultado.connect(self._on_resultado_accion)
        return acc

    def _ventana(self):
        from PyQt6.QtWidgets import QWidget
        p = self.parent()
        return p if isinstance(p, QWidget) else None

    def _ventana_a_la_vista(self) -> bool:
        """¿Verás el modal de la página? Solo con la ventana visible, sin minimizar y
        delante, y si el turno no salió del chat de la asistente. Si no, la pregunta va
        junto a la asistente (siempre encima): nunca caduca sin que se vea."""
        v = self._ventana()
        if v is None:
            return False
        try:
            return bool(v.isVisible() and not v.isMinimized() and v.isActiveWindow()
                        and not (self._turno or {}).get("asistente"))
        except Exception:
            return False

    def _ancla_asistente(self):
        """Rectángulo global de la asistente visible (para la pregunta junto a ella), o None."""
        ov = self._asistente_viva()
        if ov is None:
            return None
        try:
            return ov.frameGeometry() if ov.isVisible() else None
        except Exception:
            return None

    def _preguntar_web(self, pendiente: dict, _responder=None):
        """La pregunta va a la página (AprobacionHost); la respuesta vuelve por resolver_aprobacion."""
        self.aprobacion_pedida.emit(json.dumps(pendiente, ensure_ascii=False, default=str))

    @pyqtSlot(str, bool, result=bool)
    def resolver_aprobacion(self, pendiente_id: str, ok: bool) -> bool:
        """«Sí, hazlo» / «No» del modal. False si ya no estaba (caducó o se canceló)
        o si esa pregunta no se le hizo a la página (aprobacion_pedida): las del
        diálogo junto a la asistente o las de la ventana nativa no se contestan desde
        aquí."""
        acc = self.acciones
        if acc is None:
            return False
        pid = str(pendiente_id or "")
        try:
            de_la_pagina = acc.abiertas.get(pid) == "fuera"
        except Exception:
            de_la_pagina = False
        if not de_la_pagina:
            return False
        return bool(acc.resolver(pid, bool(ok)))

    @pyqtSlot(result=str)
    def aprobaciones_pendientes(self) -> str:
        """Las que esperan respuesta en la página (al recargarla vuelve a enseñarlas)."""
        acc = self.acciones
        if acc is None:
            return "[]"
        try:
            web = {pid for pid, v in acc.abiertas.items() if v == "fuera"}
            return json.dumps([p for p in acc.pendientes() if str(p.get("id")) in web],
                              ensure_ascii=False, default=str)
        except Exception:
            return "[]"

    def _on_resultado_accion(self, res):
        """Resultado de una acción (del modelo o pedida con tus palabras; hilo de Qt):
        ✓/✕ en el chat y, si el turno salió del chat de la asistente, también en su
        burbuja, debajo de lo que ya decía (hecha, rechazada, caducada o error)."""
        ok = bool(getattr(res, "ok", False))
        mensaje = str(getattr(res, "mensaje", "") or "")
        self.herramienta.emit(ok, "bolt", mensaje[:48], mensaje)
        if mensaje.strip():
            linea = f"{'✓' if ok else '✕'} {mensaje.strip()}"
            previo = (self._eco_texto or "").strip()
            self._eco_asistente(f"{previo}\n{linea}" if previo else linea, fin=True)

    # ── Avisos de la voz (llegan del hilo de audio) ─────────────────────────────
    def _emitir_si_vivo(self, senal: str, *args) -> None:
        """Emite `senal` solo si el puente sigue vivo. El hilo de voz puede llamar después
        de borrarlo (cambio de interfaz, salir): emitir una señal de un QObject borrado da
        AttributeError o una violación de acceso; aquí se resuelve en cada llamada."""
        try:
            if sip.isdeleted(self):
                return
            getattr(self, senal).emit(*args)
        except (RuntimeError, AttributeError):
            pass

    def _aviso_hablando(self, activo) -> None:
        """voice.al_hablar (hilo de audio)."""
        self._emitir_si_vivo("_hablando", bool(activo))

    def _aviso_voz_error(self, mensaje) -> None:
        """voice.on_error (hilo de audio)."""
        self._emitir_si_vivo("_voz_error", str(mensaje))

    def _soltar_voz(self) -> None:
        """Desengancha los avisos de la voz si siguen siendo los de este puente."""
        voz = getattr(self, "voice", None)
        for attr, mio in (("al_hablar", self._aviso_hablando), ("on_error", self._aviso_voz_error)):
            try:
                if getattr(voz, attr, None) == mio:
                    setattr(voz, attr, None)
            except Exception:
                pass

    def _on_voz_error(self, mensaje: str):
        """voice.on_error (llega del hilo de audio por señal): aviso en la página."""
        try:
            from nucleo.utils import log_error
            log_error(f"[voz] {mensaje}")
        except Exception:
            pass
        self.aviso.emit(f"Voz: {mensaje}")

    def _escritorio_asistente(self, ov):
        """La asistente flotante nueva (o None) → ServiciosEscritorio (BusEstado y eventos)."""
        esc = getattr(self, "escritorio", None)
        if esc is None:
            return
        try:
            render = None
            if ov is not None:
                from ui.avatar_overlay import AvatarOverlay
                render = "sprites" if isinstance(ov, AvatarOverlay) else str(getattr(ov, "render", "") or "")
            esc.set_asistente(ov, render=render)
        except Exception:
            pass

    # ── Herramientas de la asistente (asistente_dormir / despertar / tamano) ─────────
    def _registrar_herramientas_asistente(self):
        """Handlers del catálogo (riesgo ESCRITURA, sin aprobación, modos asistente/vrm)."""
        for nombre, fn in (("asistente_dormir", self._h_asistente_dormir),
                           ("asistente_despertar", self._h_asistente_despertar),
                           ("asistente_tamano", self._h_asistente_tamano)):
            try:
                self.escritorio.registrar_herramienta(nombre, fn)
            except Exception as e:
                from nucleo.utils import log_error
                log_error(f"[acciones] no pude registrar {nombre}: {e}")

    def _asistente_a_la_vista(self):
        """La asistente flotante si existe, no está cerrada y se ve; si no, None."""
        ov = self._asistente_viva()
        if ov is None:
            return None
        try:
            return ov if ov.isVisible() else None
        except Exception:
            return None

    def _modo_acciones(self) -> str:
        """Modo del catálogo para este turno: con la asistente fuera, "vrm" (3D) o
        "asistente" (animada o sprites); si no, MODO_ACCIONES ("normal")."""
        ov = self._asistente_a_la_vista()
        if ov is None:
            return MODO_ACCIONES
        try:
            from ui.avatar_overlay import AvatarOverlay
            if isinstance(ov, AvatarOverlay):
                return "asistente"
        except Exception:
            pass
        return "vrm" if str(getattr(ov, "render", "") or "") == "vrm" else "asistente"

    def _en_hilo_qt(self) -> bool:
        return threading.get_ident() == self._hilo_qt

    @staticmethod
    def _correr_en_ui(fn):
        """Slot de _en_ui_senal (hilo de Qt): corre fn()."""
        try:
            fn()
        except Exception:
            pass

    def en_ui(self, fn, espera_s: float = ESPERA_UI_S):
        """Corre fn() en el hilo de Qt y devuelve su resultado. Desde otro hilo la
        encola (_en_ui_senal) y espera como mucho `espera_s`: TimeoutError si la
        interfaz no contesta; la excepción de fn se relanza aquí."""
        if self._en_hilo_qt():
            return fn()
        hecho = threading.Event()
        caja: dict = {}

        def correr():
            try:
                caja["r"] = fn()
            except Exception as e:                   # noqa: BLE001
                caja["e"] = e
            finally:
                hecho.set()

        self._en_ui_senal.emit(correr)
        if not hecho.wait(espera_s):
            raise TimeoutError("la interfaz no respondió a tiempo")
        if "e" in caja:
            raise caja["e"]
        return caja.get("r")

    def _ctx_asistente(self, ctx, **extra) -> dict:
        """ctx del Ejecutor + la asistente a la vista (None si no hay: la herramienta
        devuelve un error claro). `en_ui` solo desde otro hilo (en el de Qt se llama
        directo); en_ui devuelve lo que devuelve fn, así que el resultado de
        dormir()/despertar() cuenta en los dos casos."""
        c = _ctx_dict(ctx)
        c.update(extra)
        c["asistente"] = self._asistente_a_la_vista()
        if not self._en_hilo_qt():
            c["en_ui"] = self.en_ui
        return c

    def _h_asistente_dormir(self, args, ctx=None):
        return sueno.herramienta_dormir(args, self._ctx_asistente(ctx))

    def _h_asistente_despertar(self, args, ctx=None):
        return sueno.herramienta_despertar(args, self._ctx_asistente(ctx))

    def _h_asistente_tamano(self, args, ctx=None):
        return vrm.herramienta_tamano(args, self._ctx_asistente(ctx, config=self.config))

    # ── API para el JS ───────────────────────────────────────────────────────────
    AVISO_OCUPADA = "Espera, aún estoy terminando lo anterior; mándamelo otra vez en un momento."

    @pyqtSlot(str, str)
    def enviar(self, texto: str, provider: str = "local"):
        self._provider_web = str(provider or "local")
        if self._enviar(texto, provider, desde_asistente=False, oido=self._tomar_lo_oido(texto)):
            return
        # La página ya pintó tu mensaje y espera `done`: que no se quede «pensando»
        # (p. ej. tras Detener el worker viejo sigue vivo hasta que su proveedor corta).
        ocupada = self._worker is not None and self._worker.isRunning()
        self.estado.emit("live")
        self.done.emit(self.AVISO_OCUPADA if ocupada else "", "normal")

    @pyqtSlot(str)
    def proveedor_elegido(self, provider: str):
        """La página cambió de proveedor: el chat de la asistente usará el mismo."""
        if str(provider or "") in ("local", "cloud", "compat"):
            self._provider_web = str(provider)

    @pyqtSlot(str, result=bool)
    def enviar_desde_asistente(self, texto: str) -> bool:
        """
        on_chat de la asistente (la cajita del doble clic): mismo flujo, mismo
        historial y memoria que el chat de la ventana, con el proveedor elegido
        en la página. La página lo pinta como mensaje tuyo y la respuesta sale
        también en la burbuja de la asistente. False si aún responde a otra cosa.
        """
        texto = str(texto or "").strip()
        if not texto:
            return False
        if self._worker is not None and self._worker.isRunning():
            ov = self._asistente_viva()
            if ov is not None and hasattr(ov, "burbuja_texto"):
                try:
                    ov.burbuja_texto("Espera, aún estoy con lo anterior…")
                    ov.burbuja_fin(4000)
                except Exception:
                    pass
            return False
        self.usuario_asistente.emit(texto)
        return self._enviar(texto, self._provider_web, desde_asistente=True)

    def _respuesta_rapida(self, texto: str) -> str:
        """Respuesta instantánea del banco (sin modelo) o "" si no aplica o está apagado
        (Ajustes: respuestas_predeterminadas)."""
        try:
            if not self.config.feature("respuestas_predeterminadas", True):
                return ""
            self.banco.set_nombre_usuario(self.memoria.get_nombre_usuario())
            return self.banco.responder(texto) or ""
        except Exception:
            return ""

    def _resumen_tareas(self):
        """Las tareas pendientes para «qué tareas tengo» (nucleo.tareas, sobre la MISMA
        memoria que el panel de tareas). None si no hay módulo: la pregunta va a la IA."""
        try:
            from nucleo.tareas import resumen_de
            return resumen_de(self.memoria)
        except Exception:
            return None

    def _tomar_lo_oido(self, texto: str) -> bool:
        """¿`texto` es lo último que transcribió el modo llamada? (La página lo mete en el
        chat y lo manda por `enviar`, como si lo hubieras escrito.) Cuenta una sola vez."""
        oido, self._oido_llamada = self._oido_llamada, ""
        return bool(oido) and str(texto or "").strip() == oido

    # ── Bienvenida (11): las tres preguntas cuando aún no te conozco ─────────────
    def _nombre_bot(self) -> str:
        """El nombre del personaje ACTIVO para los textos de la bienvenida (no «Lune» fijo ni
        el del banco, que se creó con el personaje de entonces)."""
        try:
            nombre = (personajes.get_activo() or {}).get("nombre")
        except Exception:
            nombre = None
        return str(nombre or getattr(getattr(self, "banco", None), "nombre", "") or "Lune")

    def _bienvenida_obj(self):
        """La Bienvenida de esta ventana (se crea al primer uso) o None. Con una memoria que no
        es un MemoriaManager (dobles de test) o en modo terminal de la red, está inactiva."""
        b = getattr(self, "_bienvenida", None)
        if b is None:
            try:
                b = Bienvenida(self.config, self.memoria, nombre_asistente=self._nombre_bot)
            except Exception:
                return None
            self._bienvenida = b
        return b

    def _bienvenida_activa(self) -> bool:
        b = getattr(self, "_bienvenida", None)
        try:
            return b is not None and bool(b.activa)
        except Exception:
            return False

    def _ventana_visible(self) -> bool:
        """¿La ventana de la página está a la vista (visible y sin minimizar)? A diferencia de
        _ventana_a_la_vista no pide que esté delante ni mira de dónde salió el turno."""
        v = self._ventana()
        if v is None:
            return False
        try:
            return bool(v.isVisible() and not v.isMinimized())
        except Exception:
            return False

    def _mensajes_chat(self) -> list:
        """Los mensajes de la conversación en curso en chats/ ([] si no hay)."""
        try:
            m = self._chats.mensajes_actuales() if self._chats is not None else []
        except Exception:
            m = []
        return m if isinstance(m, list) else []

    def _bienvenida_decir(self, texto: str) -> None:
        """En voz alta si la voz está puesta. En la llamada no: el LlamadaWorker ya dice
        cada `done` (_llamada_entregar)."""
        try:
            if getattr(self.voice, "_enabled", False) and self._llamada is None:
                self.voice.speak(texto)
        except Exception:
            pass

    def _bienvenida_en_pagina(self, b, pregunta, mensajes: list) -> str:
        """La pregunta en curso se ve en la página (la pinta quien llama, salvo que la
        conversación ya termine en ella): se apunta como vista ahí y, si no está en chats/,
        como pendiente de guardar. Devuelve lo que hay que pintar ("" si nada)."""
        self._bienvenida_sin_guardar = None
        if not pregunta:
            return ""
        try:
            nucleo, clave = b.nucleo_actual(), b.clave_paso()
        except Exception:
            return ""
        self._bienvenida_marcas["ventana"] = clave
        if ya_preguntada(mensajes, nucleo):
            return ""
        self._bienvenida_sin_guardar = pregunta
        return pregunta

    def _bienvenida_al_cargar(self, mensajes: list) -> str:
        """estado_inicial (cada carga o recarga de la página y cada cambio de interfaz): la
        pregunta en curso, que la página pinta como burbuja de Lune; "" si no toca o si la
        conversación restaurada ya termina en ella. Si aún no había empezado y la memoria
        está vacía de ti, empieza aquí. Con la ventana a la vista, la cara saluda y la voz la
        dice (una vez por pregunta y proceso); escondida (arranque con Windows en la bandeja)
        no habla: se dirá cuando la página vuelva a cargarse a la vista."""
        b = self._bienvenida_obj()
        if b is None:
            return ""
        try:
            pregunta = b.arrancar()
        except Exception:
            return ""
        pintar = self._bienvenida_en_pagina(b, pregunta, mensajes)
        if pintar and self._ventana_visible() and b.por_decir():
            self.acto.emit("wave")
            self._asistente_estado("wave")
            self._bienvenida_decir(pintar)
        return pintar

    def _bienvenida_pendiente(self, mensajes: list) -> str:
        """La pregunta en curso para repintarla (chat limpio, conversación abierta del
        historial) o ""."""
        if not self._bienvenida_activa():
            self._bienvenida_sin_guardar = None
            return ""
        b = self._bienvenida
        try:
            pregunta = b.pregunta_actual()
        except Exception:
            return ""
        return self._bienvenida_en_pagina(b, pregunta, mensajes)

    def _bienvenida_vista(self, desde_burbuja: bool):
        """Qué pregunta viste donde escribiste: la de la página o, desde la burbuja de la
        asistente en escritorio, la que enseñó la burbuja (y la de la página si la ventana
        está a la vista)."""
        m = self._bienvenida_marcas
        if not desde_burbuja:
            return m.get("ventana")
        vistas = [m.get("burbuja")]
        if self._ventana_visible():
            vistas.append(m.get("ventana"))
        return vistas

    def _bienvenida_turno(self, texto: str, desde_burbuja: bool = False) -> bool:
        """_enviar (ventana o burbuja de la asistente en escritorio): si la bienvenida se queda
        con tu mensaje (la respuesta a una pregunta, /conocernos o /saltar) Lune contesta al
        instante, sin modelo ni herramientas, y devuelve True. Si no habías visto la pregunta
        donde escribiste, tu mensaje no cuenta como respuesta: Lune te la enseña. En chats/
        queda (marcado «bienvenida», no vuelve al modelo) la pregunta si aún no estaba, tu
        mensaje y lo que dice Lune ahora."""
        b = self._bienvenida_obj()
        if b is None:
            return False
        try:
            tb = b.turno(texto, vista=self._bienvenida_vista(desde_burbuja))
        except Exception as e:
            try:
                from nucleo.utils import log_error
                log_error(f"[bienvenida] {e}")
            except Exception:
                pass
            return False
        if tb is None:
            return False
        self._guardar_turno("user", texto, bienvenida=True)   # la pregunta pendiente va antes
        cara = tb.cara or "happy"
        self.done.emit(tb.respuesta, cara)
        self._asistente_estado(cara)
        self._guardar_turno("assistant", tb.respuesta, bienvenida=True)
        self._bienvenida_sin_guardar = None
        self._eco_asistente(tb.respuesta, fin=True, tipeado=True)
        try:
            clave = b.clave_paso()
            self._bienvenida_marcas["ventana"] = clave          # la respuesta sale en la página
            if desde_burbuja:
                self._bienvenida_marcas["burbuja"] = clave      # …y en la burbuja
            b.marcar_dicha()                                    # la siguiente ya se dice aquí
        except Exception:
            pass
        self._bienvenida_decir(tb.respuesta)
        return True

    def _enviar(self, texto: str, provider: str, desde_asistente: bool = False,
                oido: bool = False) -> bool:
        """`oido`: lo transcribió el modo llamada (puede ser ruido de fondo u otra
        persona): lo que detecte detectar_llamadas pide permiso (ctx['llamada']); el
        turno de IA va como siempre."""
        texto = (texto or "").strip()
        # Lo que llega de la asistente no se lleva los adjuntos pendientes de la ventana.
        pend = [] if desde_asistente else list(self._adjuntos_pend)
        if (not texto and not pend) or (self._worker and self._worker.isRunning()):
            return False
        provider_id = _provider_id(provider)
        self._turno = {"origen": ORIGEN_USUARIO, "ctx": None, "asistente": bool(desde_asistente)}
        self._eco_texto = ""              # la burbuja de la asistente empieza de cero este turno
        self._rearmar_aburrimiento()      # escribiste: Lune ya no está aburrida
        self._cancelar_plan()             # expresiones pendientes de la respuesta anterior…
        try:
            self.voice.cancelar()         # …y su voz, si aún sonaba
        except Exception:
            pass
        # Bienvenida (11): mientras Lune te hace sus tres preguntas, lo que escribes (aquí o en
        # la burbuja de la asistente en escritorio, si ahí viste la pregunta) es la respuesta: se
        # guarda al instante, sin modelo ni herramientas. Con adjuntos no (van al modelo como
        # siempre) y las órdenes de Telegram tampoco (entran por _orden_remota).
        # Lo oído en el modo llamada no: la tele o alguien al lado no te pone el nombre ni el
        # trato que va al system prompt (sigue el camino de siempre, con sus cautelas).
        if not pend and not oido and self._bienvenida_turno(texto, desde_asistente):
            return True
        self._guardar_turno("user", texto or "Analiza lo que te adjunto.", adjuntos=pend)

        # Con adjuntos, todo va al modelo (ni la memoria ni las herramientas los
        # entienden). Sin adjuntos, primero se prueban herramientas y memoria.
        if not pend:
            # Lo pidió la persona con sus palabras («abre youtube», «lanza paint»,
            # «avísame en 10 minutos»): sin IA, pero por el Ejecutor como cualquier
            # acción (Política, denegación, presupuesto y aprobación de lanzar_app;
            # también con lo que transcribe el modo llamada). El resultado llega por
            # _on_resultado_accion. Antes que la memoria (cortes 5/6): «recuérdame que a
            # las 5 tengo cita» es una alarma; sin hora ni duración sigue siendo un recuerdo.
            # Oído en la llamada (SB2): todo lo que no sea de lectura pide permiso
            # («lo oí en la llamada»): la tele o alguien al lado no te pone alarmas.
            try:
                llamadas = self.tools.detectar_llamadas(texto)
            except Exception:
                llamadas = []
            if llamadas and self.acciones is not None:
                modo = self._modo_acciones()
                ctx = ctx_acciones(self.ai, provider_id, modo)
                if oido:
                    ctx["llamada"] = True
                self._turno = {"origen": ORIGEN_USUARIO, "ctx": ctx, "asistente": bool(desde_asistente)}
                self.done.emit("", "happy")
                self.acciones.ejecutar(llamadas, ORIGEN_USUARIO, ctx)
                return True
            try:
                resp_mem = self.memoria.procesar_mensaje_usuario(texto)
            except Exception:
                resp_mem = None
            if resp_mem:
                self.done.emit(resp_mem, "happy")
                self._guardar_turno("assistant", resp_mem)
                self._eco_asistente(resp_mem, fin=True, tipeado=True)
                return True
            # Respuestas instantáneas sin modelo. En el modo llamada no: ahí el turno lo
            # habla el worker de la llamada y luego vuelve a escuchar.
            rapida = self._respuesta_rapida(texto) if not oido and self._llamada is None else None
            if rapida:
                self.done.emit(rapida, "happy")
                self._asistente_estado("happy")
                self._guardar_turno("assistant", rapida)
                self._eco_asistente(rapida, fin=True, tipeado=True)
                try:
                    if getattr(self.voice, "_enabled", False):
                        self.voice.speak(rapida)
                except Exception:
                    pass
                return True

        # La asistente contesta solo con la nube (10.9): sin clave de OpenRouter lo dice
        # (no cae al modelo local). Lo de arriba (órdenes, memoria, respuestas
        # instantáneas) no necesita modelo y funciona igual.
        if desde_asistente:
            if not str(datos.openrouter_key() or "").strip():
                self.done.emit(AVISO_ASISTENTE_SIN_NUBE, "thinking")
                self._guardar_turno("assistant", AVISO_ASISTENTE_SIN_NUBE)
                self._eco_asistente(AVISO_ASISTENTE_SIN_NUBE, fin=True, tipeado=True)
                return True
            provider_id = "openrouter"

        try:
            contexto = self.memoria.obtener_contexto_para_prompt()
        except Exception:
            contexto = ""
        imagenes = []
        externo = ""
        if pend:
            try:
                from nucleo import adjuntos as adj
                # Los adjuntos son datos de terceros de ESTE mensaje: van aparte (al
                # final del mensaje), nunca bajo «CONTEXTO DE MEMORIA DEL USUARIO».
                externo = adj.bloque_para_prompt(pend)
                imagenes = adj.imagenes_base64(pend)
            except Exception:
                pass
            self._adjuntos_pend = []
            self.adjuntos_cambio.emit("[]")

        # Origen del turno (crítica d): con adjuntos, el prompt lleva texto de
        # terceros → en esta respuesta solo herramientas de LECTURA.
        origen = ORIGEN_NO_CONFIABLE if pend else ORIGEN_USUARIO
        # Con la asistente fuera el modo es "asistente"/"vrm": también las suyas (dormir…).
        modo = self._modo_acciones()
        ctx = ctx_acciones(self.ai, provider_id, modo)
        self._arrancar_ia(texto or "Analiza lo que te adjunto.", provider_id, contexto=contexto,
                          imagenes=imagenes, origen=origen, modo=modo, ctx=ctx,
                          asistente=bool(desde_asistente), externo=externo)
        return True

    def _arrancar_ia(self, mensaje: str, provider_id: str, *, contexto: str = "", imagenes=None,
                     origen: str, modo: str, ctx: dict, asistente: bool = False, remoto: str = "",
                     externo: str = ""):
        """Lanza el AIWorker de un turno (ventana, asistente u orden de Telegram).
        `contexto`: la memoria del usuario; `externo`: adjuntos de este mensaje."""
        self.estado.emit("busy")
        self.acto.emit("thinking")
        self._asistente_estado("thinking")
        self._seguidor = expresiones.SeguidorActs()
        self._stream_iniciado = False
        self._expresado_en_stream = False
        # Un Detener anterior deja cancel_flag levantado: si no se baja, el proveedor
        # corta en el primer token y todo sale "Sin respuesta".
        try:
            self.ai.providers[provider_id].cancel_flag = False
        except Exception:
            pass
        self._gen += 1
        gen = self._gen
        self._turno = {"origen": origen, "ctx": ctx, "asistente": bool(asistente)}
        if remoto:
            self._turno["remoto"] = remoto          # id de la orden: la respuesta vuelve a Telegram
        self._worker = AIWorker(
            self.ai, mensaje, provider_id,
            extra_context=contexto,
            permitir_acciones=self.config.feature("acciones_ia", True),
            imagenes=imagenes or [],
            emociones=self.config.feature("emociones", True),
            origen=origen, ejecutor=getattr(self.acciones, "ejecutor", None),
            modo=modo, ctx=ctx, **({"contexto_externo": externo} if externo else {}),
        )
        # Las señales llevan la generación: tras Detener (o un envío nuevo) las del
        # worker viejo se ignoran, en vez de pintar su respuesta parcial.
        self._worker.token_received.connect(lambda t, g=gen: self._on_chunk(t, g))
        self._worker.response_ready.connect(lambda r, g=gen: self._on_done(r, g))
        self._worker.error_occurred.connect(lambda m, g=gen: self._on_error(m, g))
        # Cortes 9/10: `pensando` en el bus mientras el hilo de la IA vive (el bot de
        # Minecraft pausa su modelo; Discord, «Pensando…»). Lo apaga el finished de ESTE hilo.
        fin = getattr(self._worker, "finished", None)
        if fin is not None and hasattr(fin, "connect"):
            fin.connect(lambda w=self._worker: self._fin_pensando_chat(w))
        self._pensando_chat(True)
        self._worker.start()

    def _pensando_chat(self, on: bool) -> None:
        """Cortes 9/10: el chat espera al modelo (BusEstado.pensar, fuente «chat»: no pisa a la
        asistente cuando comenta la pantalla)."""
        bus = getattr(getattr(self, "escritorio", None), "estado", None)
        f = getattr(bus, "pensar", None)
        if not callable(f):
            return
        try:
            from nucleo.estado_asistente import PENSANDO_CHAT
            f(PENSANDO_CHAT, bool(on))
        except Exception as e:
            try:
                from nucleo.utils import log_error
                log_error(f"[escritorio] no pude marcar «pensando»: {e}")
            except Exception:
                pass

    def _fin_pensando_chat(self, worker) -> None:
        """finished de un AIWorker: deja de pensar si era el vigente (o ya no hay). El de un
        hilo viejo que acaba tarde no apaga el del envío nuevo."""
        if getattr(self, "_worker", None) in (None, worker):
            self._pensando_chat(False)

    # ── Órdenes desde Telegram (/pc) ─────────────────────────────────────────────
    # NO son slots de la página (sin @pyqtSlot): solo las llama el TelegramBotWorker.
    def _responder_telegram(self, oid: str, texto: str) -> bool:
        """`texto` al chat de Telegram de la orden `oid` (por el stdin del bot)."""
        fn = getattr(self._tg_worker, "responder_orden", None)
        if not oid or not callable(fn):
            return False
        try:
            return bool(fn(str(oid), str(texto or "")))
        except Exception:
            return False

    def _avisar_detenida(self, ids) -> list:
        """«Se detuvo…» a esas órdenes de Telegram, UNA vez por orden: se limpia su marca
        (la del turno que se respondía y la de la última orden) para que ni detener() +
        limpiar_chat, ni parar el bot, ni el cambio de interfaz la repitan."""
        hechos = []
        for oid in ids or ():
            oid = str(oid or "")
            if not oid or oid in hechos:
                continue
            self._responder_telegram(oid, AVISO_TG_DETENIDA)
            hechos.append(oid)
            if isinstance(self._turno, dict) and str(self._turno.get("remoto") or "") == oid:
                self._turno.pop("remoto", None)
            if self._ultima_orden_tg == oid:
                self._ultima_orden_tg = ""
        return hechos

    def _pendientes_acciones(self) -> list:
        try:
            return self.acciones.pendientes() if self.acciones is not None else []
        except Exception:
            return []

    def _avisar_ordenes_pendientes(self, ya_avisada: str = "") -> list:
        """Conversación nueva (limpiar chat, abrir otra del historial) con una orden de
        Telegram esperando tu permiso: la pregunta se cierra sin hacer nada, así que a
        Telegram le llega «Se detuvo…» (si no, se quedaría esperando). `ya_avisada`:
        la que detener() ya contestó. Devuelve los ids avisados."""
        from ui.cambio_interfaz import ordenes_cortadas
        ids = [i for i in ordenes_cortadas(None, False, self._pendientes_acciones(),
                                           self._ultima_orden_tg)
               if i and i != str(ya_avisada or "")]
        return self._avisar_detenida(ids)

    def _avisar_ordenes_en_curso(self) -> list:
        """Se para el bot: «Se detuvo…» a la orden que se está respondiendo y a la que
        espera tu permiso (después ya no hay por dónde contestar)."""
        from ui.cambio_interfaz import ordenes_cortadas
        vivo = self._worker is not None and self._worker.isRunning()
        return self._avisar_detenida(ordenes_cortadas(self._turno, vivo, self._pendientes_acciones(),
                                                      self._ultima_orden_tg))

    def _remota_en_curso(self) -> bool:
        """¿Lune está respondiendo o espera que apruebes una orden de Telegram anterior?"""
        if self._worker is not None and self._worker.isRunning():
            return True
        try:
            return any(p.get("remoto") for p in (self.acciones.pendientes() if self.acciones else []))
        except Exception:
            return False

    def _orden_remota(self, oid: str, texto: str):
        """
        Orden de Telegram (/pc, `TelegramBotWorker.orden_recibida`, hilo de Qt).
        Sale en el chat como «📱 Telegram: …». Primero se mira si es un comando
        directo («abre youtube»): va al Ejecutor con origen 'remoto' SIN IA (sirve
        con Ollama apagado). Si no, turno de IA con origen 'remoto' y el mismo
        historial. TODO lo que se ejecute se aprueba en el PC (modal de la página
        o diálogo junto a la asistente), nunca desde Telegram; la respuesta y cada
        ✓/✕ (también tras aprobar, rechazar o caducar) vuelven al chat de Telegram.
        """
        oid, texto = str(oid or ""), str(texto or "").strip()
        if not oid or not texto:
            return
        if not ordenes_activas(self.config):
            self._responder_telegram(oid, AVISO_TG_DESACTIVADAS)
            return
        if self._remota_en_curso():
            self._responder_telegram(oid, AVISO_TG_OCUPADA)
            return
        provider_id = _provider_id(self._provider_web)
        modo = self._modo_acciones()
        ctx = ctx_acciones(self.ai, provider_id, modo)
        ctx["origen"] = ORIGEN_REMOTO               # todas marcadas «(pide permiso)» en el prompt
        self._turno = {"origen": ORIGEN_REMOTO, "ctx": ctx, "asistente": False, "remoto": oid}
        # Si la ventana se cierra con esta orden esperando tu permiso (cambio de modo),
        # se le contesta «Se detuvo…» (ui/web_shell.py).
        self._ultima_orden_tg = oid
        self._eco_texto = ""
        self._cancelar_plan()
        try:
            self.voice.cancelar()
        except Exception:
            pass
        # La página lo pinta como mensaje de entrada (como los de la asistente).
        self.usuario_asistente.emit(PREFIJO_TELEGRAM + texto)
        self._guardar_turno("user", PREFIJO_TELEGRAM + texto, no_confiable=True)

        try:
            llamadas = self.tools.detectar_llamadas(texto)
        except Exception:
            llamadas = []
        if llamadas and self.acciones is not None:
            self.done.emit("", "happy")
            self._ejecutar_remoto(llamadas, ctx, oid)
            return

        try:
            contexto = self.memoria.obtener_contexto_para_prompt()
        except Exception:
            contexto = ""
        self._arrancar_ia(PREFIJO_IA + texto, provider_id, contexto=contexto,
                          origen=ORIGEN_REMOTO, modo=modo, ctx=ctx, remoto=oid)

    def _ejecutar_remoto(self, llamadas, ctx, oid: str):
        """Acciones de una orden de Telegram: origen 'remoto' (todo con aprobación en el
        PC); cada resultado lleva el id de su orden, llegue cuando llegue."""
        ej = getattr(self.acciones, "ejecutor", None)
        if ej is None or not llamadas:
            return
        ej.ejecutar_llamadas(llamadas, ORIGEN_REMOTO, ctx,
                             lambda res, o=oid: self._resultado_remoto.emit(res, o))

    def _on_resultado_remoto(self, res, oid: str):
        """✓/✕ de una acción de una orden de Telegram: en el chat y de vuelta al bot."""
        self._on_resultado_accion(res)
        mensaje = str(getattr(res, "mensaje", "") or "").strip()
        if mensaje:
            ok = bool(getattr(res, "ok", False))
            self._responder_telegram(oid, f"{'✓' if ok else '✕'} {mensaje}")

    @pyqtSlot()
    def detener(self):
        # Una orden de Telegram a medio responder: que allí no se quede esperando (una
        # vez: _avisar_detenida quita la marca y limpiar chat después no la repite).
        remoto = (self._turno or {}).get("remoto")
        if remoto and self._worker is not None and self._worker.isRunning():
            self._avisar_detenida([remoto])
        try:
            for p in self.ai.providers.values():
                p.cancel_flag = True
        except Exception:
            pass
        self._soltar_chunk()                # lo que ya llegó se queda a la vista, antes del `done`
        self._gen += 1                      # lo que emita el worker en curso ya no cuenta
        self._cancelar_plan()
        try:
            self.voice.cancelar()
        except Exception:
            pass
        self.done.emit("", "normal")
        self._asistente_estado("normal")
        self._eco_asistente("", fin=True)     # la burbuja de la asistente se va sola
        self.estado.emit("live")

    # ── Expresiones ──────────────────────────────────────────────────────────────
    def _voz_lee_al_final(self) -> bool:
        """¿La voz va a leer la respuesta cuando termine? (entonces la cara sigue a la voz)."""
        return bool(self._llamada is None and getattr(self.voice, "_enabled", False)
                    and getattr(self.voice, "available", False))

    def _expresar(self, estado: str):
        """Cambia la cara de la barra lateral y de la asistente en escritorio (se queda)."""
        if not estado:
            return
        self.acto.emit(estado)
        self._asistente_estado(estado)

    def _on_chunk(self, acumulado: str, gen=None):
        if gen is not None and gen != self._gen:
            return
        if not self._stream_iniciado:
            self._stream_iniciado = True
            self._expresar("typing")
        if self._seguidor is not None and not self._voz_lee_al_final():
            for act in self._seguidor.nuevos(acumulado):
                self._expresado_en_stream = True
                self._expresar(EMOCION_A_ASISTENTE.get(act.get("emotion"), "happy"))
        # Agrupado: con cada `chunk` la página vuelve a pintar el chat entero y el eco hace un
        # runJavaScript en la asistente. Como mucho uno cada CHUNK_CADA_MS: el primero sale
        # ya y lo que llegue dentro de esa ventana se queda en el último acumulado, que sale
        # al vencer el temporizador o, como muy tarde, justo antes de `done` (_soltar_chunk).
        self._chunk_pend = (self._gen, acumulado)
        timer = self._timer_chunk()
        if timer.isActive():
            return
        espera_ms = CHUNK_CADA_MS - (time.monotonic() - getattr(self, "_chunk_t", 0.0)) * 1000
        if espera_ms <= 0:
            self._soltar_chunk()
        else:
            timer.start(max(1, int(espera_ms)))

    def _timer_chunk(self) -> QTimer:
        t = getattr(self, "_chunk_timer", None)
        if t is None:
            t = self._chunk_timer = QTimer(self)
            t.setSingleShot(True)
            t.timeout.connect(self._soltar_chunk)
        return t

    def _soltar_chunk(self) -> None:
        """Emite el acumulado pendiente del envío vigente: `chunk` y, si el turno salió del
        chat de la asistente, el eco en su burbuja. Lo llaman el temporizador y, antes de
        `done` (fin, error o Detener), quien termina: el texto final y el orden no cambian."""
        t = getattr(self, "_chunk_timer", None)
        if t is not None:
            t.stop()
        pend, self._chunk_pend = getattr(self, "_chunk_pend", None), None
        if pend is None or pend[0] != self._gen:
            return                                   # de un envío ya cortado
        self._chunk_t = time.monotonic()
        acumulado = pend[1]
        self.chunk.emit(acumulado)
        if (self._turno or {}).get("asistente"):   # el turno salió del chat de la asistente
            self._eco_asistente(limpiar_texto(marcadores.limpiar_para_mostrar(acumulado)))

    def _al_segmento_voz(self, _i: int, etiqueta: str, gen=None):
        # Desde el hilo de audio: la señal lo lleva al hilo de Qt. Los avisos de una
        # respuesta anterior (generación vieja) se ignoran.
        if etiqueta and (gen is None or gen == self._gen):
            self._acto_voz.emit(etiqueta)

    def _al_terminar_voz(self, estado_final: str, gen=None):
        # Al acabar de hablar, la cara se queda con la última expresión (aunque su
        # tramo no tuviera texto que leer, o la respuesta no trajera marcadores).
        if estado_final and (gen is None or gen == self._gen):
            self._acto_voz.emit(estado_final)

    def _cancelar_plan(self):
        for t in self._timers_plan:
            try: t.stop(); t.deleteLater()
            except Exception: pass
        self._timers_plan = []

    def _programar_plan(self, plan):
        """Sin voz y sin streaming: las expresiones al ritmo de lectura (la 1ª ya se puso)."""
        self._cancelar_plan()
        for t_s, emocion, _ in expresiones.horario(plan)[1:]:
            tm = QTimer(self); tm.setSingleShot(True)
            tm.timeout.connect(lambda e=emocion, t=tm: (self._expresar(EMOCION_A_ASISTENTE.get(e, "happy")), t.deleteLater()))
            tm.start(int(t_s * 1000))
            self._timers_plan.append(tm)

    # ── Fin de la respuesta del modelo ───────────────────────────────────────────
    def _on_done(self, respuesta: str, gen=None):
        if gen is not None and gen != self._gen:
            return                                   # respuesta (parcial) de un envío ya detenido
        self._soltar_chunk()                         # el último acumulado, siempre antes de `done`
        # Acciones del modelo: el Ejecutor saca las <|CALL …|> del texto (y borra el
        # formato antiguo sin ejecutarlo). Se ejecutan más abajo, al terminar.
        turno = self._turno or {}
        origen = turno.get("origen", ORIGEN_NO_CONFIABLE)
        ctx = turno.get("ctx")
        if self.acciones is not None and self.config.feature("acciones_ia", True):
            limpio, llamadas = self.acciones.procesar(respuesta, origen, ctx)
        else:
            limpio, llamadas = limpiar_texto(respuesta or ""), []
        # Emociones: el plan de expresiones de la respuesta (hasta tres tramos con
        # su texto). La última es con la que se queda.
        try:
            plan = expresiones.planificar(limpio)
        except Exception:
            plan = [expresiones.Tramo("", 1.0, limpio)]
        hablable = expresiones.hablable(plan)
        asistente = EMOCION_A_ASISTENTE.get(expresiones.final(plan), "happy")
        try:
            intensidad = max(0.0, min(1.0, float(plan[-1].intensidad)))
        except (TypeError, ValueError):
            intensidad = 0.8
        self.emocion.emit(asistente, intensidad)
        # A chats/ como la nativa: con texto de terceros (adjuntos) o desde Telegram,
        # marcada (al retomarla, el historial del modelo sigue «contaminado»).
        self._guardar_turno("assistant", limpio, no_confiable=(origen != ORIGEN_USUARIO))

        try:
            self.memoria.procesar_respuesta_lune(limpio)
        except Exception:
            pass

        # Voz: si está activa, Lune lee la respuesta por tramos y la cara cambia
        # cuando empieza a sonar cada uno. En modo llamada NO: ahí la habla el
        # worker (bloqueando) para luego volver a escuchar.
        con_voz = False
        con_emociones = bool(expresiones.emociones(plan))
        try:
            if (self._llamada is None and getattr(self.voice, "_enabled", False)
                    and hablable.strip()):
                # Sin marcadores, el tramo va como "talking"; al acabar, la cara final.
                segs = expresiones.segmentos_voz(plan, lambda e: EMOCION_A_ASISTENTE.get(e, "happy"))
                segs = [(et or "talking", tx) for et, tx in segs]
                con_voz = bool(self.voice.speak_segmentos(
                    segs,
                    al_segmento=lambda i, e, g=gen: self._al_segmento_voz(i, e, g),
                    al_terminar=lambda g=gen, est=asistente: self._al_terminar_voz(est, g)))
        except Exception:
            con_voz = False

        self.estado.emit("live")
        if con_voz:
            self.done.emit(hablable, "")              # la cara la lleva la voz, tramo a tramo
        elif self._expresado_en_stream or self._llamada is not None or not con_emociones:
            # Ya cambió con el texto (o en llamada la lleva el worker, o no hay
            # marcadores): se queda con la última.
            self.done.emit(hablable, asistente)
            self._asistente_estado(asistente)
        else:
            # Llegó de golpe: la 1ª ya, las demás al ritmo de lectura.
            primera = EMOCION_A_ASISTENTE.get(plan[0].emocion, asistente)
            self.done.emit(hablable, primera)
            self._asistente_estado(primera)
            self._programar_plan(plan)
        # Si el turno salió del chat de la asistente, la respuesta final en su burbuja.
        self._eco_asistente(hablable if hablable.strip() else limpio, fin=True)
        # Si era una orden de Telegram, la respuesta (limpia) vuelve a su chat.
        remoto = turno.get("remoto")
        if remoto:
            visible = hablable.strip() or marcadores.limpiar_para_mostrar(limpio).strip()
            pedidas = llamadas if self.acciones is not None else []
            self._responder_telegram(remoto, con_aviso_pendiente(visible or SIN_TEXTO, pedidas))

        # Las acciones que pidió el modelo, AL TERMINAR la respuesta (tras pintarla):
        # lo permitido se hace ya; lo que pide permiso pregunta (modal de la página o
        # junto a la asistente) y su resultado llega luego por _on_resultado_accion.
        # Las de una orden de Telegram piden TODAS permiso y su ✓/✕ vuelve también allí.
        if llamadas and self.acciones is not None:
            if remoto:
                self._ejecutar_remoto(llamadas, ctx, remoto)
            else:
                self.acciones.ejecutar(llamadas, origen, ctx)

    def _on_error(self, msg: str, gen=None):
        if gen is not None and gen != self._gen:
            return
        self._soltar_chunk()                         # lo que ya llegó se ve antes del error
        self.estado.emit("error")
        self.done.emit(f"Error: {msg}", "error")
        self._asistente_estado("nervous", 6000)
        self._eco_asistente(f"✕ {msg}", fin=True)
        remoto = (self._turno or {}).get("remoto")
        if remoto:                               # p. ej. Ollama apagado: que se entienda allí
            self._responder_telegram(remoto, f"✕ No pude responder: {msg}")

    # ── Chat de la asistente: la respuesta también en su burbuja ───────────────────
    def _asistente_viva(self):
        """La asistente flotante si existe y no está cerrada (sin crearla), o None."""
        ov = self._overlay
        if ov is None or getattr(ov, "cerrado", False):
            return None
        return ov

    def _eco_asistente(self, texto: str, fin: bool = False, tipeado: bool = False):
        """Si el turno salió del chat de la asistente: el texto en su burbuja
        (burbuja_texto) y, al acabar, burbuja_fin con el tiempo de lectura. Con la
        asistente oculta no se enseña nada (la respuesta sigue en la ventana)."""
        if not (self._turno or {}).get("asistente"):
            return
        ov = self._asistente_viva()
        if ov is None or not hasattr(ov, "burbuja_texto"):
            return
        try:
            if not ov.isVisible():
                return
        except Exception:
            return
        try:
            texto = str(texto or "").strip()
            if texto:
                self._eco_texto = texto
                if tipeado:
                    try:
                        ov.burbuja_texto(texto, tipeado=True)
                    except TypeError:                # una flotante sin «tipeado»
                        ov.burbuja_texto(texto)
                else:
                    ov.burbuja_texto(texto)
            if fin and hasattr(ov, "burbuja_fin"):
                from ui.chat_asistente import ms_lectura
                ov.burbuja_fin(ms_lectura(texto))
        except Exception as e:
            try:
                from nucleo.utils import log_error
                log_error(f"[asistente] burbuja: {e}")
            except Exception:
                pass

    @pyqtSlot()
    def limpiar_chat(self):
        """«Limpiar chat»: historial del modelo a cero y conversación nueva para las
        acciones (presupuesto repuesto; las preguntas abiertas se cierran sin hacer nada)."""
        avisada = ""
        if self._worker is not None and self._worker.isRunning():
            avisada = str((self._turno or {}).get("remoto") or "")
            self.detener()                           # la que se estaba respondiendo: «Se detuvo…»
        self._gen += 1
        self._cancelar_plan()
        try:
            self.ai.clear_history()
        except Exception:
            pass
        if self.acciones is not None:
            self._avisar_ordenes_pendientes(avisada)
            self.acciones.nueva_conversacion()
        self._turno = {}
        if self._chats is not None:
            self._chats.nueva_sesion(proveedor=_provider_id(self._provider_web),
                                     personaje=personajes.activo_nombre() or "")
        # Bienvenida a medias: la pregunta vuelve a salir (la página vacía el chat al llamar
        # aquí y este `done` le llega después, sobre el chat ya limpio).
        pregunta = self._bienvenida_pendiente([])
        if pregunta:
            self.done.emit(pregunta, "happy")

    # ── Conversación en chats/ (como la nativa) y cambio de modo en caliente ──────
    @property
    def chats(self):
        """GestorConversaciones de la conversación en curso (None si aún no hay)."""
        return self._chats

    def _guardar_turno(self, rol: str, contenido: str, adjuntos=None, no_confiable: bool = False,
                       bienvenida: bool = False):
        """Un mensaje a chats/ si la ventana lo pide (persistir_chats) y la memoria de
        conversaciones está activada. `no_confiable`: turno con texto de terceros o de
        Telegram (se guarda la marca; al retomarlo, el historial sigue marcado).
        `bienvenida`: turno de las tres preguntas (se ve, pero no vuelve al modelo). Si la
        página enseña una pregunta de la bienvenida que aún no está en chats/, va antes que
        este turno (así el historial sale en el orden en que lo viste)."""
        if not self._persistir_chats or not str(contenido or "").strip():
            return
        pendiente = getattr(self, "_bienvenida_sin_guardar", None)
        if isinstance(pendiente, str) and pendiente:
            self._bienvenida_sin_guardar = None
            self._guardar_turno("assistant", pendiente, bienvenida=True)
        try:
            if not self.config.feature("guardar_conversaciones", True):
                return
            g = self._gestor_chats()
            if g.sesion_id is None:
                g.nueva_sesion(proveedor=_provider_id(self._provider_web),
                               personaje=personajes.activo_nombre() or "")
            extra = {"no_confiable": True} if no_confiable else {}
            if bienvenida:
                extra["bienvenida"] = True
            g.agregar(rol, str(contenido), adjuntos=adjuntos, **extra)
        except Exception as e:
            try:
                from nucleo.utils import log_error
                log_error(f"[chats] no pude guardar el turno: {e}")
            except Exception:
                pass

    def guardar_conversacion(self):
        """Vuelca la conversación en curso (al cerrar la ventana o cambiar de modo)."""
        if self._chats is not None:
            try:
                self._chats.guardar()
            except Exception:
                pass

    def retomar_sesion(self, sesion: dict) -> bool:
        """Cambio de modo: la conversación de la ventana anterior sigue aquí (misma
        id en chats/) y el modelo la recuerda, con la marca de texto de terceros."""
        from ui.cambio_interfaz import retomar_sesion as _retomar
        g = self._gestor_chats()
        if not _retomar(g, sesion):
            return False
        try:
            self.ai.cargar_historial(g.como_historial())
        except Exception:
            pass
        return True

    def restaurar_ultima(self) -> bool:
        """Al ARRANCAR la ventana web (no en un cambio de modo, que trae la suya): la
        última conversación de chats/ sigue aquí, como en la nativa, si
        chat.restaurar_ultima y features.guardar_conversaciones (y persistir_chats).
        La página la pinta al cargar con estado_inicial(). True si la retomó."""
        if not self._persistir_chats:
            return False
        try:
            if not self.config.feature("guardar_conversaciones", True):
                return False
            if not self.config.get("chat", "restaurar_ultima", True):
                return False
            sesion = self._gestor_chats().ultima()
        except Exception:
            return False
        if not isinstance(sesion, dict) or not sesion.get("mensajes"):
            return False
        return self.retomar_sesion(sesion)

    @pyqtSlot(str, result=str)
    def cambiar_interfaz(self, modo: str) -> str:
        """Ajustes → «Modo de interfaz»: web (completa) · nativo (bajos recursos) ·
        patata (terminal). Se aplica al instante: la ventana lo pasa a GestorInterfaz,
        que hace el relevo en la siguiente vuelta del bucle (la página que llama
        termina antes de destruirse). Sin gestor (web_shell suelta), se guarda y se
        aplica al reiniciar."""
        from ui.cambio_interfaz import normalizar_modo
        m = normalizar_modo(modo)
        if m is None:
            return json.dumps({"ok": False, "error": "Modo de interfaz desconocido."})
        try:
            escuchan = self.receivers(self.interfaz_pedida) > 0
        except Exception:
            escuchan = False
        if not escuchan:
            self.config.set("interfaz", "modo", m)
            return json.dumps({"ok": True, "reinicio": True})
        self.interfaz_pedida.emit(m)
        return json.dumps({"ok": True})

    @pyqtSlot(result=str)
    def estado_inicial(self) -> str:
        """Lo que la página pinta al cargar: proveedor, voz, bot, asistente y la
        conversación en curso (p. ej. la que siguió tras un cambio de modo)."""
        mensajes = []
        g = self._chats
        for m in (g.mensajes_actuales() if g is not None else []):
            texto = marcadores.limpiar_para_mostrar(limpiar_texto(str(m.get("contenido") or ""))).strip()
            if texto:
                mensajes.append({"role": "user" if m.get("rol") == "user" else "bot", "text": texto})
        # Bienvenida (11): la pregunta en curso es la primera burbuja de Lune (o la última,
        # tras la conversación restaurada), sin modelo. No va a chats/ hasta que contestes.
        pregunta = self._bienvenida_al_cargar(mensajes)
        if pregunta:
            mensajes.append({"role": "bot", "text": pregunta})
        return json.dumps({
            "proveedor": self._provider_web,
            "voz": bool(getattr(self.voice, "_enabled", False)),
            "telegram": bool(self._tg_worker is not None and self._tg_worker.isRunning()),
            "asistente_fuera": self.asistente_visible(),
            "mensajes": mensajes,
        }, ensure_ascii=False)

    # ── Asistente en escritorio: recibe lo mismo que Lune en la barra lateral ──
    def _asistente_estado(self, estado: str, ms: int = 0):
        ov = self._overlay
        if ov is None or getattr(ov, "cerrado", False) or not ov.isVisible():
            return
        try:
            ov.set_estado(estado, ms)
        except Exception:
            pass

    def _on_hablando(self, activo: bool):
        # También con la asistente oculta: si no, al ocultarla mientras habla se
        # quedaría «hablando» para siempre (no se duerme, sonidos callados…). La
        # asistente guarda el estado y se lo pasa a su página al volver a verse.
        ov = self._overlay
        if ov is None or getattr(ov, "cerrado", False):
            return
        try:
            if hasattr(ov, "set_hablando"):
                ov.set_hablando(bool(activo))
        except Exception:
            pass

    # ── Configuración (Ajustes) ──────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def get_config(self) -> str:
        p = personajes.get_activo() or {}
        # Las claves nunca salen en claro hacia la página: máscara + «configurada».
        cfg = {
            "openrouter_key": _mascara(datos.openrouter_key()),
            "openrouter_key_configurada": bool(str(datos.openrouter_key() or "").strip()),
            "openrouter_model": datos.openrouter_model(),
            "ollama_url": datos.ollama_url(),
            "ollama_model": datos.ollama_model(),
            "telegram_token": _mascara(datos.telegram_token()),
            "telegram_token_configurado": bool(str(datos.telegram_token() or "").strip()),
            # Tu ID de Telegram (no es una clave) y «Órdenes desde Telegram».
            "telegram_admin_id": str(datos.telegram_admin_id() or "").strip(),
            "telegram_ordenes_pc": bool(self.config.get("telegram", "ordenes_pc", False)),
            "nombre": p.get("nombre", "Lune"),
            "system_prompt": p.get("systemPrompt", ""),
            "voz": bool(getattr(self.voice, "_enabled", False)),
            "memoria": self.config.feature("guardar_conversaciones", True),
            "acciones_ia": self.config.feature("acciones_ia", True),
            "respuestas_rapidas": self.config.feature("respuestas_predeterminadas", True),
            "asistente_render": str(self.config.get("avatar", "render", "animado") or "animado"),
            "interfaz_modo": str(self.config.get("interfaz", "modo", "web") or "web"),
            # Asistente 3D (VRM): qué hay instalado y cómo se muestra
            "vrm_webengine": vrm.webengine_disponible(),
            "vrm_modelos": vrm.listar_modelos(),
            "vrm_archivo": str(self.config.get("avatar", "vrm_archivo", "") or ""),
            "vrm_tamano": str(self.config.get("avatar", "vrm_tamano", "normal") or "normal"),
            "vrm_encuadre": str(self.config.get("avatar", "vrm_encuadre", "retrato") or "retrato"),
            "vrm_fantasma_auto": bool(self.config.get("avatar", "vrm_fantasma_auto", True)),
            "seguir_cursor": bool(self.config.get("avatar", "seguir_cursor", True)),
            "dormir_min": int(self.config.get("avatar", "dormir_min", 10) or 0),
            "asistente_fuera": self.asistente_visible(),
            "autoinicio": self.autoinicio_get(),
            "aburrimiento_min": int(self.config.get("chat", "aburrimiento_min", 10) or 0),
            # Lune en reposo (11.2): el interruptor de «Efectos visuales» lo guarda al momento como
            # los demás efectos (luneEscritorio.efectos_guardar); aquí va para quien lo lea con Ajustes.
            "pausar_sin_foco": bool(self.config.get("efectos", "pausar_sin_foco", True)),
            # Audio: micrófono, salida y modelo de Whisper (nombres; "" = sistema)
            "dispositivo_entrada": str(self.config.get("voz", "dispositivo_entrada", "") or ""),
            "dispositivo_salida": str(self.config.get("voz", "dispositivo_salida", "") or ""),
            "modelo_whisper": str(self.config.get("voz", "modelo_whisper", "base") or "base"),
            "voz_idioma": str(self.config.get("voz", "idioma", "es") or ""),
            # Asistente: pack de sonidos de reacción y volumen de los efectos
            "pack_sonidos": str(self.config.get("avatar", "pack_sonidos", "default") or "default"),
            "volumen_sfx": self._volumen_sfx(),
            # API compatible con OpenAI (tercer proveedor, 'compat')
            "compat_url": datos.compat_url(),
            "compat_key": _mascara(datos.compat_key()),
            "compat_key_configurada": bool(datos.compat_key()),
            "compat_model": datos.compat_model(),
            # Lune instalada (Setup.exe): sin «Instalar componentes…» ni órdenes de pip.
            "instalada": _instalada(),
        }
        cfg.update(self._config_voz(p))
        cfg.update(self._config_muestreo())
        return json.dumps(cfg, ensure_ascii=False)

    def _volumen_sfx(self) -> float:
        try:
            v = float(self.config.get("avatar", "volumen_sfx", 0.7))
        except (TypeError, ValueError):
            v = 0.7
        return max(0.0, min(1.0, v))

    def _config_voz(self, personaje) -> dict:
        """La voz que suena de verdad (personaje > config > defecto), en claves planas."""
        from servicios import voces
        from nucleo.personajes import voz_de
        propia = voz_de(personaje) if personaje else {}
        try:
            efectiva = voces.resolver_voz(self.config, personaje)
        except Exception:
            efectiva = voces.ParamsVoz()
        motor = str(propia.get("motor") or self.config.get("voz", "motor_salida", "auto") or "auto")
        edge = efectiva.id if voces.es_id_edge(efectiva.id) else str(
            self.config.get("voz", "edge_voz", voces.VOZ_POR_DEFECTO) or voces.VOZ_POR_DEFECTO)
        kokoro = efectiva.id if efectiva.motor == "kokoro" else str(
            self.config.get("voz", "kokoro_voz", "ef_dora") or "ef_dora")
        return {"motor_salida": motor if motor in voces.MOTORES else "auto",
                "edge_voz": edge, "edge_rate": efectiva.rate, "edge_pitch": efectiva.pitch,
                "gtts_tld": efectiva.tld, "kokoro_voz": kokoro}

    @staticmethod
    def _config_muestreo() -> dict:
        """Parámetros efectivos del modelo (preset + lo fijado a mano), como los pinta AvanzadoCard."""
        try:
            m = datos.parametros_muestreo()
        except Exception:
            return {}
        return {
            "preset_muestreo": m.get("preset") or datos.PRESET_POR_DEFECTO,
            **{k: m.get(k) for k in _CLAVES_MUESTREO},
            "num_predict": m.get("num_predict") or 0,
            "seed": -1 if m.get("seed") is None else m.get("seed"),
            "ollama_num_ctx": m.get("num_ctx") or datos.ollama_num_ctx(),
        }

    @pyqtSlot(str, result=str)
    def guardar_config(self, payload: str) -> str:
        try:
            c = json.loads(payload or "{}")
        except Exception:
            return json.dumps({"ok": False, "error": "payload inválido"})
        try:
            d = datos.cargar()
            apis = d.setdefault("apis", {})
            # Claves: la máscara de get_config (o nada) = conservar la guardada.
            for clave in ("openrouter_key", "telegram_token"):
                if clave in c:
                    nueva = _clave_nueva(c[clave])
                    if nueva is not None:
                        apis[clave] = nueva
            aviso_tg = ""
            if "telegram_admin_id" in c:
                tid = str(c["telegram_admin_id"] or "").strip()
                if not tid or (tid.isascii() and tid.isdigit() and len(tid) <= 20):
                    if tid != str(apis.get("telegram_admin_id", "") or "").strip():
                        apis["telegram_admin_id"] = tid
                        aviso_tg = "Reinicia el bot de Telegram para aplicar el cambio."
                else:
                    aviso_tg = "Tu ID de Telegram son solo números (escríbele /id al bot); no lo cambié."
            mod = d.setdefault("modelos", {})
            if "openrouter_model" in c:
                mod["openrouter_model"] = str(c["openrouter_model"]).strip() or "openrouter/auto"
            if "ollama_url" in c: mod["ollama_url"] = str(c["ollama_url"]).strip()
            if "ollama_model" in c: mod["ollama_model"] = str(c["ollama_model"]).strip()
            # API compatible con OpenAI (vacía = apagada) y parámetros del modelo.
            aviso_compat = self._guardar_compat_y_muestreo(mod, c, apis)
            # Voz: solo lo que cambiaste, y donde toca (ver _voz_de_payload).
            voz_cambios = self._voz_de_payload(c)
            voz_en_personaje = False
            # Personalidad: actualiza el personaje activo en su sitio.
            activo = (personajes.activo_nombre() or "").lower()
            for pj in d.setdefault("personajes", []):
                if pj.get("nombre", "").lower() == activo:
                    if "system_prompt" in c:
                        pj["systemPrompt"] = str(c["system_prompt"])
                    nuevo = str(c.get("nombre", "")).strip()
                    if nuevo and nuevo != pj.get("nombre"):
                        pj["nombre"] = nuevo
                        d.setdefault("bot", {})["personaje_default"] = nuevo
                    # Si el personaje trae voz propia, lo que cambiaste de la voz va a
                    # ella (manda sobre config: si no, no se notaría) y la global no se
                    # toca; si no la trae, va a config voz.* (más abajo).
                    from nucleo.personajes import voz_de
                    propia = voz_de(pj)
                    if propia:
                        voz_en_personaje = True
                        if voz_cambios:
                            pj["voz"] = voz_personaje_con_cambios(
                                propia, voz_cambios, self._config_voz(pj))
                    break
            datos.guardar(d)
            if aviso_compat:
                self.aviso.emit(aviso_compat)
            self._compat_borrador = None             # ya está guardado: se prueba lo guardado
            if "memoria" in c: self.config.set_feature("guardar_conversaciones", bool(c["memoria"]))
            if "acciones_ia" in c: self.config.set_feature("acciones_ia", bool(c["acciones_ia"]))
            if "respuestas_rapidas" in c:
                self.config.set_feature("respuestas_predeterminadas", bool(c["respuestas_rapidas"]))
            # Órdenes desde Telegram: se aplican al (re)iniciar el bot (el token va al lanzarlo).
            if "telegram_ordenes_pc" in c and bool(c["telegram_ordenes_pc"]) != bool(
                    self.config.get("telegram", "ordenes_pc", False)):
                self.config.set("telegram", "ordenes_pc", bool(c["telegram_ordenes_pc"]))
                aviso_tg = aviso_tg or "Reinicia el bot de Telegram para aplicar el cambio."
            # El de «reinicia» solo tiene sentido con el bot en marcha (va tras «guardada»).
            bot_vivo = self._tg_worker is not None and self._tg_worker.isRunning()
            if aviso_tg.startswith("Reinicia") and not bot_vivo:
                aviso_tg = ""
            if "voz" in c and getattr(self.voice, "_enabled", False) != bool(c["voz"]):
                self.voice._enabled = bool(c["voz"]); self.voz_estado.emit(bool(c["voz"]))
            # Asistente: animado · vrm (avatar 3D) · sprites (bajos recursos), y las
            # opciones del VRM. Si cambia algo que la página no aplica en caliente,
            # se recrea la asistente con lo nuevo (solo si estaba abierta).
            recrear = False
            cambio_vrm = False                       # la barra lateral tiene que republicar
            ov = self._overlay if (self._overlay is not None and not getattr(self._overlay, "cerrado", False)) else None
            if c.get("asistente_render") in ("animado", "vrm", "sprites"):
                nuevo = c["asistente_render"]
                if nuevo != self.config.get("avatar", "render", "animado"):
                    self.config.set("avatar", "render", nuevo); recrear = True; cambio_vrm = True
            if "vrm_archivo" in c:
                v = str(c["vrm_archivo"] or "").strip()
                if v == str(self.config.get("avatar", "vrm_archivo", "") or "").strip():
                    pass                             # sin cambios: ni aviso (aunque ya no exista)
                elif v and not self._modelo_de_la_carpeta(v):
                    self.aviso.emit(f"No encuentro el modelo «{v}» en {vrm.CARPETA}; sigo con el anterior.")
                else:
                    self.config.set("avatar", "vrm_archivo", v)
                    cambio_vrm = True
                    # el modelo por defecto solo cuenta si el personaje no trae el suyo
                    if ov is not None and hasattr(ov, "recargar_modelo"):
                        ov.recargar_modelo()
            # Seguir el cursor (interruptor global de la biblioteca VRM): los pesos
            # de seguimiento van a 0 en los params del modelo; se aplican ya.
            if "seguir_cursor" in c and bool(c["seguir_cursor"]) != bool(
                    self.config.get("avatar", "seguir_cursor", True)):
                self.config.set("avatar", "seguir_cursor", bool(c["seguir_cursor"]))
                self._aplicar_params_vrm()
            # Tamaño y encuadre se aplican en caliente (la ventana ya sabe hacerlo).
            for clave, valido, aplicar in (("vrm_tamano", ("pequeno", "normal", "grande"), "aplicar_tamano"),
                                           ("vrm_encuadre", ("retrato", "cuerpo"), "aplicar_encuadre")):
                if clave in c:
                    v = str(c[clave] or "").strip()
                    if v not in valido or v == str(self.config.get("avatar", clave, "") or ""):
                        continue
                    if ov is not None and getattr(ov, "render", "") == "vrm" and hasattr(ov, aplicar):
                        getattr(ov, aplicar)(v)           # también guarda la clave
                    else:
                        self.config.set("avatar", clave, v)
            if "vrm_fantasma_auto" in c:
                self.config.set("avatar", "vrm_fantasma_auto", bool(c["vrm_fantasma_auto"]))
            if "dormir_min" in c:
                try:
                    self.config.set("avatar", "dormir_min", max(0, int(c["dormir_min"])))
                except (TypeError, ValueError):
                    pass
            if ov is not None and hasattr(ov, "aplicar_opciones"):
                try: ov.aplicar_opciones()
                except Exception: pass
            if recrear and self._overlay is not None:
                self._asistente_recrear()
            if cambio_vrm:
                self._vrm_modelo_cambio()
            # Interfaz (web · nativo · patata): NO se guarda aquí. Se cambia al instante
            # con cambiar_interfaz(), y quien la escribe en config es GestorInterfaz
            # (si el cambio falla, vuelve la de antes).
            # Aburrimiento (minutos; 0 = nunca) y autoinicio con Windows
            if "aburrimiento_min" in c:
                try:
                    self.config.set("chat", "aburrimiento_min", max(0, int(c["aburrimiento_min"])))
                except (TypeError, ValueError):
                    pass
                self._rearmar_aburrimiento()
            # Lune en reposo (efectos.pausar_sin_foco): la página lo aplica al recargar los efectos.
            if "pausar_sin_foco" in c and bool(c["pausar_sin_foco"]) != bool(
                    self.config.get("efectos", "pausar_sin_foco", True)):
                self.config.set("efectos", "pausar_sin_foco", bool(c["pausar_sin_foco"]))
            # Solo si cambió de verdad (la página manda lo que tocaste, pero pudo
            # cambiarse desde la bandeja con Ajustes abierto): ni reescribe el registro
            # ni repite el aviso en cada guardado.
            if "autoinicio" in c and bool(c["autoinicio"]) != self.autoinicio_get():
                self.autoinicio_set(bool(c["autoinicio"]))
            # Audio: micrófono (se resuelve al grabar), salida (se aplica ya) y Whisper
            if "dispositivo_entrada" in c:
                self.config.set("voz", "dispositivo_entrada", str(c["dispositivo_entrada"] or "").strip())
            if "dispositivo_salida" in c:
                salida = str(c["dispositivo_salida"] or "").strip()
                if salida != self.config.get("voz", "dispositivo_salida", ""):
                    self.config.set("voz", "dispositivo_salida", salida)
                    if getattr(self.voice, "available", False):
                        if not self.voice.aplicar_salida(salida) and salida:
                            self.aviso.emit(f"No encontré la salida «{salida}»; uso la del sistema.")
            if "modelo_whisper" in c:
                from servicios import voz_entrada
                if c["modelo_whisper"] in voz_entrada.MODELOS:
                    self.config.set("voz", "modelo_whisper", c["modelo_whisper"])
            if "voz_idioma" in c:
                self.config.set("voz", "idioma", str(c["voz_idioma"] or "").strip())
            # Voz de salida: motor, voz, velocidad, tono y acento. Solo lo que cambiaste
            # (Ajustes manda la voz efectiva entera: reescribirla pisaría la global con
            # la del personaje). Sin voz propia del personaje va a config voz.*; con
            # ella ya se guardó arriba. La próxima frase suena con lo nuevo.
            if voz_cambios:
                if not voz_en_personaje:
                    for clave, valor in voz_cambios.items():
                        self.config.set("voz", clave, valor)
                self._reiniciar_voz()
            # Asistente: pack de sonidos y volumen de los efectos (se aplican en caliente).
            if self._guardar_sonidos(c) and ov is not None and hasattr(ov, "cargar_pack_sonidos"):
                try: ov.cargar_pack_sonidos()
                except Exception: pass
            try: self.ai.reload_provider()
            except Exception: pass
            self.proveedores_cambio.emit(self.proveedores())   # la API compatible pudo aparecer o irse
            self.aviso.emit("Configuración guardada")
            if aviso_tg:
                self.aviso.emit(aviso_tg)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def _voz_de_payload(self, c: dict) -> dict:
        """Lo que CAMBIASTE de la voz: {clave: valor validado} solo con las claves de
        _CLAVES_VOZ cuyo valor difiere de la voz que suena ahora (la efectiva que dio
        get_config). {} si no cambió nada (Ajustes reenvía todo al guardar) o si lo
        que llegó no vale."""
        if not any(k in c for k in _CLAVES_VOZ):
            return {}
        from servicios import voces
        actual = self._config_voz(personajes.get_activo() or {})
        out = dict(actual)
        motor = str(c.get("motor_salida", actual["motor_salida"]) or "auto").strip().lower()
        out["motor_salida"] = motor if motor in voces.MOTORES else actual["motor_salida"]
        edge = str(c.get("edge_voz", actual["edge_voz"]) or "").strip()
        out["edge_voz"] = edge if voces.es_id_edge(edge) else actual["edge_voz"]
        out["edge_rate"] = voces.normalizar_rate(c.get("edge_rate", actual["edge_rate"])) or actual["edge_rate"]
        out["edge_pitch"] = voces.normalizar_pitch(c.get("edge_pitch", actual["edge_pitch"])) or actual["edge_pitch"]
        tld = str(c.get("gtts_tld", actual["gtts_tld"]) or "").strip().lower()
        out["gtts_tld"] = tld if tld in voces.GTTS_TLD else actual["gtts_tld"]
        kokoro = str(c.get("kokoro_voz", actual["kokoro_voz"]) or "").strip()
        out["kokoro_voz"] = kokoro or actual["kokoro_voz"]
        return {k: out[k] for k in _CLAVES_VOZ if out[k] != actual[k]}

    def _reiniciar_voz(self):
        """Motor o voz cambiaron: que la próxima frase los use."""
        for metodo in ("invalidar_params", "reiniciar_motor"):
            fn = getattr(self.voice, metodo, None)
            if callable(fn):
                try:
                    fn()
                except Exception as e:
                    self.aviso.emit(f"No pude reiniciar la voz: {e}")
                    return

    def _guardar_sonidos(self, c: dict) -> bool:
        """avatar.pack_sonidos y avatar.volumen_sfx. True si cambió algo."""
        cambio = False
        if "pack_sonidos" in c:
            from nucleo import packs_sonido
            pid = str(c["pack_sonidos"] or "").strip() or packs_sonido.PACK_DEFECTO
            if pid != packs_sonido.PACK_DEFECTO and packs_sonido.obtener_pack(pid) is None:
                self.aviso.emit(f"No encuentro el pack de sonidos «{pid}»; sigo con el anterior.")
            elif pid != self.config.get("avatar", "pack_sonidos", packs_sonido.PACK_DEFECTO):
                self.config.set("avatar", "pack_sonidos", pid); cambio = True
        if "volumen_sfx" in c:
            v = _numero(c["volumen_sfx"])
            if v is not None:
                v = round(max(0.0, min(1.0, v)), 3)
                if v != self._volumen_sfx():
                    self.config.set("avatar", "volumen_sfx", v); cambio = True
        return cambio

    @staticmethod
    def _guardar_compat_y_muestreo(mod: dict, c: dict, apis: dict | None = None) -> str:
        """compat_url/key/model y los parámetros del modelo → datos.json modelos.
        Devuelve un aviso para la página ("" si nada que decir).

        La clave de la API compatible va ligada a su URL: con la máscara (conservar)
        y otra URL, la guardada NO se manda a la dirección nueva (hay que volver a
        escribirla). Así una URL cambiada no se lleva la clave a otro sitio."""
        apis = apis if apis is not None else {}
        url_antes = datos.compat_url()
        if "compat_url" in c:
            mod["compat_url"] = str(c["compat_url"] or "").strip().rstrip("/")
        url_despues = str(mod.get("compat_url") or "").strip().rstrip("/")
        aviso = ""
        nueva = _clave_nueva(c["compat_key"]) if "compat_key" in c else None
        if nueva is not None:
            mod["compat_key"] = nueva
            if not nueva:
                apis.pop("compat_key", None)             # borrada: también la de apis.*
        elif url_despues != url_antes and datos.compat_key():
            mod["compat_key"] = ""
            apis.pop("compat_key", None)
            if url_despues:
                aviso = ("Cambiaste la URL de la API compatible: vuelve a escribir su clave "
                         "(la guardada no se manda a otra dirección).")
        if "compat_model" in c:
            mod["compat_model"] = str(c["compat_model"] or "").strip()
        if "preset_muestreo" in c:
            p = str(c["preset_muestreo"] or "").strip().lower()
            if p in datos.PRESETS_MUESTREO or p == datos.PRESET_PERSONALIZADO:
                mod["preset_muestreo"] = p
        # null = «del modelo»: no se guarda y el proveedor no lo envía.
        for clave in _CLAVES_MUESTREO:
            if clave in c:
                v = _numero(c[clave], int if clave == "top_k" else float)
                if v is None:
                    mod.pop(clave, None)
                else:
                    mod[clave] = v
        if "num_predict" in c:
            v = _numero(c["num_predict"], int)
            if v is None or v <= 0:
                mod.pop("num_predict", None)             # 0 = automático
            else:
                mod["num_predict"] = v
        if "seed" in c:
            v = _numero(c["seed"], int)
            mod["seed"] = -1 if v is None or v < 0 else v
        if "ollama_num_ctx" in c:
            # Solo si cambió (Ajustes reenvía el efectivo: un 64K puesto con /ctx en
            # patata no se toca), y en el mismo rango que patata.
            v = _numero(c["ollama_num_ctx"], int)
            if v is not None and v != datos.ollama_num_ctx():
                mod["ollama_num_ctx"] = max(_CONTEXTO_MIN, min(_CONTEXTO_MAX, v))
        return aviso

    # ── Voz, sonidos e IA avanzada (Ajustes) ─────────────────────────────────────
    @pyqtSlot(result=str)
    def voces_disponibles(self) -> str:
        """Todo lo del selector de voz (servicios.voces.catalogo) en JSON."""
        from servicios import voces
        try:
            cat = voces.catalogo(self.config, personajes.get_activo(), self.voice)
        except Exception as e:
            return json.dumps({"edge": voces.voces_estaticas(), "error": str(e)}, ensure_ascii=False)
        return json.dumps(cat, ensure_ascii=False, default=str)

    @pyqtSlot(str, result=bool)
    def probar_voz(self, payload: str) -> bool:
        """«Probar»: suena con lo elegido (aún sin guardar), aunque la voz esté apagada."""
        fn = getattr(self.voice, "probar_voz", None)
        if not callable(fn):
            self.aviso.emit(_sin_motor_de_voz())
            return False
        try:
            return bool(fn(payload or "{}"))
        except Exception as e:
            self.aviso.emit(f"No pude probar la voz: {e}")
            return False

    @pyqtSlot(result=str)
    def packs_sonido(self) -> str:
        """Packs de sonidos de reacción (sonidos/): [{id, nombre, autor, eventos…}]."""
        try:
            from nucleo import packs_sonido
            return json.dumps([p.a_dict() for p in packs_sonido.listar_packs()],
                              ensure_ascii=False, default=str)
        except Exception:
            return "[]"

    @pyqtSlot(result=str)
    def proveedores(self) -> str:
        """Qué proveedores hay: la pestaña de la API compatible solo sale si está configurada."""
        prov = getattr(self.ai, "providers", None) or {}
        return json.dumps({"compat": "compat" in prov, "compat_url": datos.compat_url(),
                           "compat_model": datos.compat_model()}, ensure_ascii=False)

    @pyqtSlot(str)
    def compat_borrador(self, payload: str):
        """Lo que está escrito en la tarjeta de la API compatible (aún sin guardar),
        para que «Probar conexión» pruebe eso y no lo guardado."""
        try:
            c = json.loads(payload or "{}")
        except ValueError:
            c = {}
        if not isinstance(c, dict) or not any(k in c for k in ("compat_url", "url")):
            self._compat_borrador = None
            return
        url = str(c.get("compat_url", c.get("url")) or "").strip().rstrip("/")
        clave = _clave_nueva(c.get("compat_key", c.get("key")))
        if clave is None:
            # La máscara = la clave guardada, pero solo con la URL guardada: a otra
            # dirección no se manda (como al guardar; hay que escribirla otra vez).
            clave = datos.compat_key() if url == datos.compat_url() else ""
        self._compat_borrador = (url, clave, str(c.get("compat_model", c.get("model")) or "").strip())

    @pyqtSlot(result=str)
    def compat_probar(self) -> str:
        """«Probar conexión» de la API compatible (GET /models, sin gastar tokens):
        {ok, mensaje, modelos, ms}. Corre en un hilo; la interfaz no se congela."""
        borrador = self._compat_borrador

        def probar():
            if borrador is not None:
                from servicios.ai_manager import CompatProvider
                return CompatProvider(*borrador).probar()
            return self.ai.probar_compat()

        r = self._esperar_en_hilo(probar, 12.0)
        if r is OCUPADO:
            r = {"ok": False, "mensaje": MENSAJE_OCUPADO, "modelos": []}
        elif not isinstance(r, dict):
            r = {"ok": False, "mensaje": "No respondió a tiempo." if r is None else str(r), "modelos": []}
        return json.dumps(r, ensure_ascii=False, default=str)

    @pyqtSlot(result=str)
    def ia_liberar_vram(self) -> str:
        """«Liberar memoria del modelo»: Ollama descarga el modelo de la VRAM ya."""
        fn = getattr(self.ai, "descargar_modelo", None)
        if not callable(fn):
            return json.dumps({"ok": False, "mensaje": "Este backend no sabe liberar el modelo."})
        ok = self._esperar_en_hilo(fn, 20.0)
        if ok is OCUPADO:
            return json.dumps({"ok": False, "mensaje": MENSAJE_OCUPADO}, ensure_ascii=False)
        if ok is True:
            return json.dumps({"ok": True, "mensaje": "Listo: el modelo salió de la memoria. "
                                                      "El próximo mensaje tardará un poco más."})
        return json.dumps({"ok": False, "mensaje": "No pude liberar el modelo (¿Ollama está encendido?)."})

    def _esperar_en_hilo(self, fn, timeout_s: float):
        """Corre `fn` en un hilo y espera su resultado sin congelar la interfaz (bucle
        de eventos anidado, como los diálogos de archivo). None si no acaba a tiempo;
        la excepción, como texto. Una sola espera a la vez: si ya hay otra en curso
        (la página pidió «Probar conexión» y «Liberar memoria» seguidas), devuelve
        OCUPADO al momento, sin anidar un bucle dentro de otro (el de fuera no
        podría salir hasta que acabara el de dentro y se pasaría de su tope)."""
        if self._esperando_hilo:
            return OCUPADO
        self._esperando_hilo = True
        try:
            return self._esperar_en_hilo_sin_anidar(fn, timeout_s)
        finally:
            self._esperando_hilo = False

    @staticmethod
    def _esperar_en_hilo_sin_anidar(fn, timeout_s: float):
        caja = {}
        bucle = QEventLoop()
        hecho = threading.Event()

        def correr():
            try:
                caja["r"] = fn()
            except Exception as e:                   # noqa: BLE001
                caja["r"] = f"Error: {e}"
            finally:
                hecho.set()
                try:
                    QMetaObject.invokeMethod(bucle, "quit", Qt.ConnectionType.QueuedConnection)
                except RuntimeError:
                    pass

        hilo = threading.Thread(target=correr, name="lune-puente-aux", daemon=True)
        hilo.start()
        if not hecho.is_set():
            tope = QTimer()
            tope.setSingleShot(True)
            tope.timeout.connect(bucle.quit)
            tope.start(max(1, int(timeout_s * 1000)))
            bucle.exec()
            tope.stop()
        hilo.join(0.05)
        return caja.get("r")

    # ── Probar cada apartado y «Comprobar que todo funciona» (Ajustes) ───────────
    # Lo de verdad vive en servicios/pruebas.py (sin Qt: lo mismo usan la nativa y patata).
    # Las pruebas cortas (la clave, Ollama, el bot) van por _esperar_en_hilo; el diagnóstico y
    # el dictado, en su QThread con señal (pueden tardar minutos). Ni la clave ni el token
    # salen nunca en lo que vuelve a la página.
    def _probar_en_hilo(self, fn, timeout_s: float) -> str:
        r = self._esperar_en_hilo(fn, timeout_s)
        if r is OCUPADO:
            r = {"ok": False, "mensaje": MENSAJE_OCUPADO}
        elif not isinstance(r, dict):
            # Nunca str(r): una excepción podría llevar la URL (y la de Telegram, el token).
            r = {"ok": False, "mensaje": "No respondió a tiempo: prueba otra vez." if r is None
                 else "No pude probarlo; prueba otra vez."}
        return json.dumps(r, ensure_ascii=False, default=str)

    @pyqtSlot(str, result=str)
    def openrouter_probar(self, payload: str) -> str:
        """«Probar clave» de OpenRouter con lo ESCRITO (aún sin guardar; la máscara = la clave
        guardada): GET /api/v1/key (no gasta tokens) y que el modelo exista en /api/v1/models.
        → {ok, mensaje, modelo_ok, gratis, ms}."""
        from servicios import pruebas
        c = _objeto_json(payload)
        clave = _clave_nueva(c.get("openrouter_key")) if "openrouter_key" in c else None
        if clave is None:
            clave = datos.openrouter_key()
        modelo = str(c.get("openrouter_model", datos.openrouter_model()) or "").strip()
        return self._probar_en_hilo(lambda: pruebas.probar_openrouter(clave, modelo), 20.0)

    @pyqtSlot(str, result=str)
    def ollama_probar(self, url: str) -> str:
        """«Probar / Buscar modelos» de Ollama con la URL escrita (vacía = la guardada).
        → {ok, mensaje, modelos, url}: la página pinta los modelos para elegir."""
        from servicios import pruebas
        u = str(url or "").strip() or datos.ollama_url()
        if len(u) > 300 or "@" in u or any(ch.isspace() for ch in u):
            return json.dumps({"ok": False, "modelos": [], "url": "",
                               "mensaje": "Esa dirección no vale: algo como http://localhost:11434 o "
                                          "http://192.168.1.50:11434."}, ensure_ascii=False)
        return self._probar_en_hilo(lambda: pruebas.probar_ollama(u), 12.0)

    @pyqtSlot(str, result=str)
    def telegram_probar(self, payload: str) -> str:
        """«Probar bot» con lo ESCRITO (la máscara = el token guardado): el token con getMe,
        tu ID (solo números), Node 18+ y la carpeta del bot (TelegramBotWorker.preparar_carpeta).
        → {ok, mensaje, bot, items: [{id, nombre, ok, detalle}]}."""
        from servicios import pruebas
        from servicios.telegram_worker import TelegramBotWorker
        c = _objeto_json(payload)
        token = _clave_nueva(c.get("telegram_token")) if "telegram_token" in c else None
        if token is None:
            token = datos.telegram_token()
        admin = str(c.get("telegram_admin_id", datos.telegram_admin_id()) or "").strip()
        return self._probar_en_hilo(
            lambda: pruebas.probar_telegram(token, admin, carpeta=TelegramBotWorker.preparar_carpeta), 30.0)

    @pyqtSlot(result=bool)
    def diagnostico_iniciar(self) -> bool:
        """«Comprobar que todo funciona»: arranca la comprobación con red en su hilo (False si
        ya hay una en marcha). Cada paso llega por la señal `diagnostico`."""
        from ui.pruebas_qt import DiagnosticoWorker
        w = self._diag_worker
        try:
            if w is not None and w.isRunning():
                return False
        except RuntimeError:
            pass
        w = DiagnosticoWorker(red=True, parent=self)
        w.evento.connect(self.diagnostico)
        self._diag_worker = w
        w.start()
        return True

    @pyqtSlot(result=bool)
    def diagnostico_parar(self) -> bool:
        """Para la comprobación en curso antes de la siguiente (el fin llega con «parado»)."""
        w = self._diag_worker
        try:
            if w is not None and w.isRunning():
                w.requestInterruption()
                return True
        except RuntimeError:
            pass
        return False

    def _probando_dictado(self) -> bool:
        h = self._dictado_prueba
        try:
            return h is not None and h.isRunning()
        except RuntimeError:
            return False

    def _dictado_error(self, mensaje: str) -> bool:
        self.dictado_prueba.emit(json.dumps({"fase": "error", "ok": False, "texto": "", "mensaje": mensaje},
                                            ensure_ascii=False))
        return False

    @pyqtSlot(str, result=bool)
    def dictado_probar(self, payload: str) -> bool:
        """«Probar dictado»: graba ~3 s del micrófono elegido en Ajustes (aún sin guardar) y lo
        transcribe con el modelo de Whisper elegido; cada paso por `dictado_prueba`. La primera
        vez el modelo se descarga (lo avisa). False si el micrófono está ocupado o no existe."""
        from servicios import voz_entrada
        from ui.audio_prueba import ProbadorDictado
        c = _objeto_json(payload)
        for h in (self._dictado_prueba, self._probador):
            try:
                if h is not None and h.isRunning():
                    return self._dictado_error("Ya estoy probando el micrófono: espera a que acabe.")
            except RuntimeError:
                pass
        if self._grabadora is not None or self._llamada is not None:
            return self._dictado_error("Ahora mismo el micrófono está en uso (dictado o llamada): termina y "
                                       "vuelve a probar.")
        faltan = voz_entrada.dependencias_faltantes()
        if faltan:
            return self._dictado_error(f"El dictado necesita {', '.join(faltan)} ({_como_instalar(*faltan)}).")
        nombre = str(c.get("dispositivo_entrada", self.config.get("voz", "dispositivo_entrada", "")) or "").strip()
        idx = voz_entrada.resolver_entrada(nombre) if nombre else None
        if nombre and idx is None:
            return self._dictado_error(f"No encuentro «{nombre}». ¿Está conectado?")
        modelo = str(c.get("modelo_whisper") or self.config.get("voz", "modelo_whisper", "base") or "base")
        if modelo not in voz_entrada.MODELOS:
            modelo = "base"
        idioma = str(c.get("voz_idioma", self.config.get("voz", "idioma", "es")) or "").strip()
        p = ProbadorDictado(idx, modelo, idioma, parent=self)
        p.progreso.connect(self.dictado_prueba)
        self._dictado_prueba = p
        p.start()
        return True

    def _soltar_pruebas(self) -> None:
        """Al cerrar: «Comprobar que todo funciona» y «Probar dictado» en marcha se paran, se
        desconectan y, si aún corren, se retienen hasta que acaben (Qt aborta el proceso si se
        borra un QThread vivo)."""
        try:
            from ui.pruebas_qt import soltar
        except Exception:
            return
        for nombre, espera in (("_diag_worker", 300), ("_dictado_prueba", 0)):
            h = getattr(self, nombre, None)
            setattr(self, nombre, None)
            try:
                soltar(h, espera_ms=espera)
            except Exception:
                pass

    # ── Toggles ──────────────────────────────────────────────────────────────────
    @pyqtSlot(result=bool)
    def voz_toggle(self) -> bool:
        nuevo = self.voice.toggle()
        self.voz_estado.emit(nuevo)
        return nuevo

    @pyqtSlot(result=str)
    def telegram_toggle(self) -> str:
        if self._tg_worker is not None and self._tg_worker.isRunning():
            # Una orden a medio responder o esperando tu permiso: «Se detuvo…» ANTES de
            # parar el bot (después ya no hay por dónde contestar). Una vez por orden.
            self._avisar_ordenes_en_curso()
            try:
                self._tg_worker.stop(); self._tg_worker.requestInterruption(); self._tg_worker.wait(3000)
            except Exception:
                pass
            self._tg_worker = None
            self.telegram_estado.emit(False, "Bot detenido")
            return json.dumps({"running": False})
        token = datos.telegram_token()
        if not token or "TU_TOKEN" in token:
            self.telegram_estado.emit(False, "Falta el token de Telegram (Ajustes)")
            return json.dumps({"running": False, "error": "sin token"})
        from servicios.telegram_worker import TelegramBotWorker
        if not TelegramBotWorker.BOT_DIR.exists():
            self.telegram_estado.emit(False, "No encontré la carpeta del bot")
            return json.dumps({"running": False, "error": "sin carpeta"})
        # Órdenes desde Telegram: el canal solo se abre si está activado y hay tu ID.
        self._tg_worker = TelegramBotWorker(ordenes=ordenes_activas(self.config))
        self._tg_worker.log_signal.connect(lambda l: self.telegram_estado.emit(True, l))
        self._tg_worker.stopped.connect(lambda: self.telegram_estado.emit(False, "Bot detenido"))
        # Llega del hilo del worker: en cola, al hilo de Qt (nunca es un slot de la página).
        self._tg_worker.orden_recibida.connect(self._orden_remota, Qt.ConnectionType.QueuedConnection)
        self._tg_worker.start()
        self.telegram_estado.emit(True, "Iniciando el bot…")
        return json.dumps({"running": True})

    def _crear_asistente(self):
        """Asistente según config avatar.render: animado (video anime) · vrm
        (avatar 3D; si no hay .vrm cae a animado) · sprites (ligera, bajos recursos).
        Su señal `visibilidad` es la que le dice a la UI que Lune está fuera (y
        entonces la barra lateral deja de dibujarla, para no verla doble)."""
        render = str(self.config.get("avatar", "render", "animado") or "animado")
        # Sin icono propio en la bandeja: la bandeja es una sola (corte 4, ui/bandeja.py).
        if render == "sprites":
            from ui.avatar_overlay import AvatarOverlay
            ov = crear_asistente(AvatarOverlay, self.config)
        else:
            from ui.companion import CompanionFlotante
            ov = crear_asistente(CompanionFlotante, self.config, ai_manager=self.ai, render=render)
        try:
            ov.visibilidad.connect(self.asistente_estado)
        except Exception:
            pass
        try:
            ov.recrear.connect(self._asistente_recrear)     # arrancó en vídeo y ya hay .vrm
        except Exception:
            pass
        # Chat de la asistente (doble clic → cajita): entra por el flujo normal de la
        # ventana, pero la asistente contesta SOLO con la nube (10.9): nada de precalentar
        # el modelo local para ella.
        try:
            ov.on_chat = self.enviar_desde_asistente
            ov.proveedor_chat = lambda: "openrouter"
        except Exception:
            pass
        self._escritorio_asistente(ov)
        return ov

    def _asistente_recrear(self):
        """Cierra la asistente y la vuelve a crear con la config actual (si estaba a la vista)."""
        ov = self._overlay
        vis = ov is not None and not getattr(ov, "cerrado", False) and ov.isVisible()
        if ov is not None:
            try: ov.close()
            except Exception: pass
        self._overlay = None
        self._escritorio_asistente(None)
        if vis:
            self._overlay = self._crear_asistente(); self._overlay.show()
            self.asistente_estado.emit(True)

    def _asistente(self):
        """La asistente viva, creándola si no existe o si el usuario la cerró."""
        if self._overlay is None or getattr(self._overlay, "cerrado", False):
            self._overlay = self._crear_asistente()
        return self._overlay

    @pyqtSlot(result=bool)
    def asistente_visible(self) -> bool:
        ov = self._overlay
        return bool(ov is not None and not getattr(ov, "cerrado", False) and ov.isVisible())

    @pyqtSlot(result=bool)
    def asistente_toggle(self) -> bool:
        # Asistente flotante (video anime o avatar VRM) + comentarios de pantalla.
        ov = self._asistente()
        if ov.isVisible():
            ov.hide(); vis = False
        else:
            ov.show(); ov.raise_(); vis = True
        self.asistente_estado.emit(vis)
        return vis

    @pyqtSlot(result=bool)
    def comentar_pantalla(self) -> bool:
        """Abre la asistente (si hace falta) y le pide comentar la pantalla ahora. En
        modo juego no: ni captura ni comentario (anticheat y rendimiento), y la
        asistente que escondió el juego no se saca para eso."""
        if self._en_modo_juego():
            self.aviso.emit(AVISO_JUEGO_PANTALLA)
            return False
        self._asistente()
        if not self._overlay.isVisible():
            self._overlay.show(); self._overlay.raise_()
            self.asistente_estado.emit(True)
        if not hasattr(self._overlay, "comentar_pantalla"):
            self.aviso.emit("Para comentar tu pantalla necesito estar en el escritorio animada o en 3D "
                            "(Ajustes → Asistente en escritorio).")
            return False
        try:
            self._overlay.comentar_pantalla()
            return True
        except Exception:
            return False

    # ── Personajes ───────────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def personajes_lista(self) -> str:
        activo = (personajes.activo_nombre() or "").lower()
        return json.dumps([
            {"nombre": p.get("nombre", ""), "activo": p.get("nombre", "").lower() == activo,
             "descripcion": (p.get("systemPrompt", "") or "")[:120],
             "vrm": str(p.get("vrm", "") or "")}
            for p in personajes.listar()
        ], ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def personaje_activar(self, nombre: str) -> bool:
        try:
            personajes.set_activo(nombre)
        except ValueError as e:                      # no existe: que se vea por qué
            self.aviso.emit(str(e))
            return False
        except Exception:
            return False
        try:
            datos.invalidar()
            fn = getattr(self.voice, "invalidar_params", None)
            if callable(fn):
                fn()                                 # cada personaje puede traer su voz
            self.aviso.emit(f"Personaje activo: {nombre}")
            self._asistente_recargar_modelo()
            self._vrm_modelo_cambio()                # la barra lateral enseña su .vrm
            try:
                self.personaje_cambio.emit(str(nombre or ""))   # la barra reintenta su 3D
            except RuntimeError:
                pass
            return True
        except Exception:
            return False

    def _asistente_recargar_modelo(self):
        """Si la asistente 3D está abierta y el personaje activo tiene otro .vrm, cámbialo
        (la asistente le aplica sola la calibración del modelo al cargarlo)."""
        ov = self._overlay
        if ov is not None and not getattr(ov, "cerrado", False) and hasattr(ov, "recargar_modelo"):
            try:
                ov.recargar_modelo()
            except Exception:
                pass

    def _vrm_modelo_cambio(self):
        """Personaje, modelo o render cambiaron: web_shell republica /vrm/actual.vrm."""
        try:
            self.modelo_vrm_cambio.emit()
        except RuntimeError:
            pass

    def _modelo_actual(self) -> str:
        """Archivo del .vrm que toca enseñar ahora (personaje > config > primero), o ""."""
        try:
            m = vrm.ruta_modelo(self.config)
        except Exception:
            m = None
        return m.name if m is not None else ""

    def _aplicar_params_vrm(self, nombre: str = ""):
        """La calibración (o el seguimiento) cambió: a la asistente flotante
        (aplicar_params_vrm, no-op fuera del render 3D) y, si es el modelo que se ve,
        a la barra lateral (vrm_params_cambio → web_shell)."""
        ov = self._asistente_viva()
        fn = getattr(ov, "aplicar_params_vrm", None) if ov is not None else None
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        actual = self._modelo_actual()
        if actual and (not nombre or nombre.lower() == actual.lower()):
            try:
                self.vrm_params_cambio.emit(vrm.params_modelo_json(actual, self.config))
            except Exception:
                pass

    # ── Modelos 3D (VRM) ─────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def vrm_modelos(self) -> str:
        return json.dumps({"webengine": vrm.webengine_disponible(), "modelos": vrm.listar_modelos(),
                           "carpeta": str(vrm.CARPETA)}, ensure_ascii=False)

    @pyqtSlot(result=str)
    def vrm_importar(self) -> str:
        """Elige un .vrm con el diálogo del sistema y lo copia a modelo_vrm/."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            ruta, _ = QFileDialog.getOpenFileName(None, "Elegir un modelo VRM", "",
                                                  "Modelos VRM (*.vrm);;Todos (*.*)")
            if not ruta:
                return json.dumps({"ok": False, "cancelado": True})
            nombre = vrm.importar_modelo(ruta)
            self.aviso.emit(f"Modelo «{nombre}» listo en {vrm.CARPETA}")
            self._asistente_recargar_modelo()
            self._vrm_modelo_cambio()                # puede ser el primero de la carpeta
            return json.dumps({"ok": True, "archivo": nombre, "modelos": vrm.listar_modelos()}, ensure_ascii=False)
        except Exception as e:
            self.aviso.emit(f"No pude importar el modelo: {e}")
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @staticmethod
    def _modelo_de_la_carpeta(nombre: Any) -> bool:
        """¿`nombre` es el nombre de un .vrm que está en modelo_vrm/? Nada de rutas
        (absolutas, UNC «\\\\equipo\\recurso», unidades): la página solo elige de la
        carpeta, y tocar una ruta de red con is_file() ya filtra credenciales."""
        try:
            return vrm._en_carpeta(nombre_modelo_seguro(nombre)) is not None
        except ValueError:
            return False

    @pyqtSlot(str, str, result=str)
    def personaje_vrm(self, nombre: str, archivo: str) -> str:
        """Asigna (o quita, con archivo vacío) el modelo 3D de un personaje. Solo
        modelos de modelo_vrm/ por su nombre de archivo."""
        archivo = str(archivo or "").strip()
        if archivo and not self._modelo_de_la_carpeta(archivo):
            error = f"Elige un modelo de la carpeta {vrm.CARPETA} (solo el nombre del archivo .vrm)."
            self.aviso.emit(f"No pude asignar el modelo: {error}")
            return json.dumps({"ok": False, "error": error}, ensure_ascii=False)
        try:
            vrm.asignar_a_personaje(nombre, archivo)
        except Exception as e:
            self.aviso.emit(f"No pude asignar el modelo: {e}")
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if (personajes.activo_nombre() or "").lower() == (nombre or "").lower():
            self._asistente_recargar_modelo()
            self._vrm_modelo_cambio()
        return json.dumps({"ok": True})

    # ── Biblioteca de modelos (extra/vrm_biblioteca.jsx) ─────────────────────────
    @pyqtSlot(result=str)
    def vrm_biblioteca(self) -> str:
        """La rejilla entera (nucleo.vrm.biblioteca): fichas sin miniaturas."""
        try:
            return vrm.biblioteca_json(self.config)
        except Exception as e:
            return json.dumps({"webengine": vrm.webengine_disponible(), "modelos": [], "error": str(e)},
                              ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def vrm_meta(self, nombre: str) -> str:
        """Ficha completa de un modelo (meta + ajustes + efectivos + quién lo usa)."""
        try:
            archivo = nombre_modelo_seguro(nombre)
        except ValueError as e:
            return json.dumps({"ok": False, "motivo": str(e), "archivo": ""}, ensure_ascii=False)
        return vrm.ficha_json(archivo, self.config)

    @pyqtSlot(str, result=str)
    def vrm_miniatura(self, nombre: str) -> str:
        """data:image/png|jpeg;base64,… de la miniatura del modelo; "" si no trae o no vale."""
        try:
            return vrm.miniatura_data_url(nombre_modelo_seguro(nombre))
        except (ValueError, OSError):
            return ""

    @pyqtSlot(str, str, result=str)
    def vrm_ajustes(self, nombre: str, cambios: str) -> str:
        """Guarda la calibración del modelo (modelo_vrm/<modelo>.lune.json) y la
        aplica en vivo a la asistente 3D y a la barra lateral."""
        try:
            archivo = nombre_modelo_seguro(nombre)
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        if vrm._en_carpeta(archivo) is None:
            return json.dumps({"ok": False, "error": f"No encuentro «{archivo}» en {vrm.CARPETA}."},
                              ensure_ascii=False)
        r = vrm.guardar_ajustes_json(archivo, cambios, self.config)
        try:
            ok = bool(json.loads(r).get("ok"))
        except (ValueError, AttributeError):
            ok = False
        if ok:
            self._aplicar_params_vrm(archivo)
        return r

    @pyqtSlot(str, result=str)
    def vrm_borrar(self, nombre: str) -> str:
        """Borra el .vrm (y su calibración) de modelo_vrm/ y recarga la asistente."""
        try:
            archivo = nombre_modelo_seguro(nombre)
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        r = vrm.borrar_json(archivo, self.config)
        try:
            ok = bool(json.loads(r).get("ok"))
        except (ValueError, AttributeError):
            ok = False
        if ok:
            aviso = f"Modelo «{archivo}» borrado"
            if (str(self.config.get("avatar", "render", "animado") or "") == "vrm"
                    and not self._modelo_actual()):
                # Era el último: la asistente 3D vuelve a las imágenes animadas (se
                # recrea sola, companion.recargar_modelo → recrear) hasta que importes otro.
                aviso += ". No queda ningún modelo 3D: en el escritorio vuelvo a las imágenes animadas."
            self.aviso.emit(aviso)
            self._asistente_recargar_modelo()
            self._vrm_modelo_cambio()
        return r

    @pyqtSlot(str, result=str)
    def vrm_params(self, nombre: str) -> str:
        """Los parámetros efectivos de un modelo (lo que recibe window.luneParams)."""
        try:
            archivo = nombre_modelo_seguro(nombre)
        except ValueError as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        return vrm.params_modelo_json(archivo, self.config)

    @pyqtSlot(result=str)
    def vrm_barra(self) -> str:
        """Lo que pinta la barra lateral: {render, url, v, archivo, params}. url "" =
        no hay modelo publicado (la barra se queda con el vídeo)."""
        info = {"url": "", "v": "", "archivo": "", "params": ""}
        info.update({k: v for k, v in (self.vrm_barra_info or {}).items() if k in info})
        info["render"] = str(self.config.get("avatar", "render", "animado") or "animado")
        return json.dumps(info, ensure_ascii=False)

    # ── Memoria ──────────────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def memoria_info(self) -> str:
        """Lo que el panel Memoria enseña: nombre, contadores, recuerdos y lo que me contaste
        en la bienvenida (cómo eres y cómo quieres que sea contigo), que también va al system
        prompt: así se ve desde la interfaz completa."""
        m = self.memoria
        try:
            perfil = m.perfil() if isinstance(m, MemoriaManager) else {}
            return json.dumps({
                "nombre": m.get_nombre_usuario(),
                "personalidad": str(perfil.get("personalidad") or ""),
                "trato": str(perfil.get("trato") or ""),
                "stats": m.get_stats(),
                "recuerdos": m.get_todos_recuerdos(),
            }, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Historial de conversaciones ──────────────────────────────────────────────
    def _gestor_chats(self):
        if self._chats is None:
            from nucleo.conversaciones import GestorConversaciones
            self._chats = GestorConversaciones()
        return self._chats

    @pyqtSlot(result=str)
    def historial_lista(self) -> str:
        try:
            return json.dumps(self._gestor_chats().listar(), ensure_ascii=False, default=str)
        except Exception:
            return json.dumps([])

    @pyqtSlot(str, result=str)
    def historial_cargar(self, sesion_id: str) -> str:
        """La página la pinta en el chat y se sigue en ella: los turnos nuevos van a
        esa conversación y el modelo la recuerda (con su marca de terceros), como
        «abrir conversación» en la nativa."""
        try:
            g = self._gestor_chats()
            s = g.cargar(sesion_id) or {}
            msgs = []
            for msg in s.get("mensajes", []):
                rol = msg.get("rol") or msg.get("role")
                texto = str(msg.get("contenido") or msg.get("content") or "")
                msgs.append({
                    "role": "user" if rol == "user" else "bot",
                    "text": marcadores.limpiar_para_mostrar(texto),
                })
            if s.get("mensajes"):
                avisada = ""
                if self._worker is not None and self._worker.isRunning():
                    avisada = str((self._turno or {}).get("remoto") or "")
                    self.detener()                   # la respuesta en curso era de la otra
                self._gen += 1
                try:
                    self.ai.cargar_historial(g.como_historial())
                except Exception:
                    pass
                if self.acciones is not None:
                    self._avisar_ordenes_pendientes(avisada)
                    self.acciones.nueva_conversacion()
                self._turno = {}
                # Bienvenida a medias: lo siguiente que escribas sigue siendo la respuesta.
                pregunta = self._bienvenida_pendiente(msgs)
                if pregunta:
                    msgs.append({"role": "bot", "text": pregunta})
            return json.dumps(msgs, ensure_ascii=False)
        except Exception:
            return json.dumps([])

    # ── Optimizar (info del sistema) ─────────────────────────────────────────────
    @pyqtSlot(result=str)
    def sistema_info(self) -> str:
        """Vista «Optimizar» (panels.jsx la pide cada 3 s mientras está abierta). Nada
        bloquea el hilo de Qt: la CPU es cpu_percent(None) (la media desde la llamada
        anterior, siempre desde este hilo; tras un rato sin pedirla se ceba y sale «—»),
        RAM y disco son lecturas al momento y los procesos (process_iter de TODO el
        sistema) los cuenta un hilo: se devuelve la última lista y, si ya es vieja, se
        pide otra. Con la vista cerrada nadie llama y no se mide nada."""
        info = {"cpu": None, "ram": None, "disco": None, "procesos": []}
        ahora = time.monotonic()
        try:
            import psutil
            previa = getattr(self, "_sis_cpu_t", None)
            cpu = psutil.cpu_percent(interval=None)
            self._sis_cpu_t = ahora
            if previa is not None and ahora - previa <= SISTEMA_CPU_CEBADA_S:
                info["cpu"] = cpu
            info["ram"] = psutil.virtual_memory().percent
            info["disco"] = psutil.disk_usage("/").percent
        except Exception:
            pass
        info["procesos"] = list(getattr(self, "_sis_procesos", None) or [])
        self._pedir_procesos(ahora)
        return json.dumps(info, ensure_ascii=False, default=str)

    def _pedir_procesos(self, ahora: float) -> None:
        """Los procesos más pesados en un hilo (uno a la vez, como mucho cada
        SISTEMA_PROCESOS_CADA_S). Deja la lista en `_sis_procesos` para la próxima llamada."""
        hilo = getattr(self, "_sis_hilo", None)
        if hilo is not None and hilo.is_alive():
            return
        if ahora - float(getattr(self, "_sis_procesos_t", -1e9)) < SISTEMA_PROCESOS_CADA_S:
            return
        self._sis_procesos_t = ahora

        def contar():
            try:
                from servicios.optimizador import Optimizador
                self._sis_procesos = Optimizador().procesos_pesados(top=6)
            except Exception:
                pass

        self._sis_hilo = threading.Thread(target=contar, name="lune-procesos", daemon=True)
        self._sis_hilo.start()

    # ── Herramientas de escritorio (Tools) ───────────────────────────────────────
    @pyqtSlot(result=str)
    def tools_lista(self) -> str:
        tools = [
            {"nombre": "Buscar en la web", "clave": "buscar_web",
             "descripcion": "Google o YouTube desde el chat.", "ejemplo": "busca lofi de shibuya"},
            {"nombre": "Abrir sitios", "clave": "abrir_url",
             "descripcion": "Lanza webs populares al instante.", "ejemplo": "abre youtube"},
            {"nombre": "Lanzar programas", "clave": "lanzar_app",
             "descripcion": "Abre apps de tu PC por su nombre.", "ejemplo": "abre la calculadora"},
            {"nombre": "Estado del sistema", "clave": "sistema_info",
             "descripcion": "CPU, RAM, disco y red.", "ejemplo": "estado del pc"},
        ]
        return json.dumps({"activas": self.config.feature("acciones_ia", True), "tools": tools},
                          ensure_ascii=False)

    # ── Memoria: gestión ─────────────────────────────────────────────────────────
    @pyqtSlot(str, result=str)
    def memoria_olvidar(self, rid: str) -> str:
        try:
            self.aviso.emit(self.memoria._cmd_olvida(rid))
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(result=str)
    def memoria_olvidar_todo(self) -> str:
        try:
            self.aviso.emit(self.memoria._cmd_olvida_todo())
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(str, result=bool)
    def memoria_agregar(self, contenido: str) -> bool:
        contenido = (contenido or "").strip()
        if not contenido:
            return False
        try:
            self.memoria.agregar_recuerdo(contenido)
            self.aviso.emit("Recuerdo añadido")
            return True
        except Exception:
            return False

    # ── Adjuntar archivos ────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def adjuntar(self) -> str:
        from PyQt6.QtWidgets import QFileDialog, QApplication
        from nucleo import adjuntos as adj
        rutas, _ = QFileDialog.getOpenFileNames(
            QApplication.activeWindow(), "Adjuntar documento o imagen", "", adj.filtro_dialogo())
        maxc = self.config.get("adjuntos", "max_caracteres", 20000)
        for ruta in rutas:
            try:
                self._adjuntos_pend.append(adj.cargar(ruta, max_caracteres=maxc))
            except Exception:
                pass
        nombres = [a.get("nombre") or a.get("ruta", "") for a in self._adjuntos_pend]
        payload = json.dumps(nombres, ensure_ascii=False)
        self.adjuntos_cambio.emit(payload)
        return payload

    @pyqtSlot()
    def adjuntos_limpiar(self):
        self._adjuntos_pend = []
        self.adjuntos_cambio.emit("[]")

    # ── Audio: dispositivos y pruebas (Configuración → Audio) ────────────────────
    def _microfono_elegido(self):
        """
        Índice de sounddevice del micrófono de config (None = por defecto). Si
        el nombre guardado ya no está conectado, avisa y usa el por defecto.
        """
        from servicios import voz_entrada
        nombre = str(self.config.get("voz", "dispositivo_entrada", "") or "").strip()
        if not nombre:
            return None
        idx = voz_entrada.resolver_entrada(nombre)
        if idx is None:
            self.aviso.emit(f"No encuentro el micrófono «{nombre}»; uso el del sistema.")
        return idx

    @pyqtSlot(result=str)
    def dispositivos_audio(self) -> str:
        from servicios import voz_entrada
        from servicios.voice import listar_salidas
        return json.dumps({
            "entradas": voz_entrada.listar_entradas(),
            "salidas": listar_salidas(),
            "entrada_actual": str(self.config.get("voz", "dispositivo_entrada", "") or ""),
            "salida_actual": str(self.config.get("voz", "dispositivo_salida", "") or ""),
            "faltan": voz_entrada.dependencias_faltantes(),
            "instalar": _como_instalar(*voz_entrada.dependencias_faltantes()),
            "modelos_whisper": voz_entrada.MODELOS,
            "modelos_descargados": [m for m in voz_entrada.MODELOS if voz_entrada.modelo_descargado(m)],
        }, ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def probar_microfono(self, nombre: str = "") -> bool:
        """Graba 1.5 s del micrófono `nombre` (vacío = sistema) y emite mic_prueba."""
        from servicios import voz_entrada
        from ui.audio_prueba import ProbadorMic
        if self._probador is not None and self._probador.isRunning():
            return False
        if self._grabadora is not None or self._llamada is not None or self._probando_dictado():
            self.aviso.emit("Ahora mismo el micrófono está en uso (dictado, llamada o «Probar dictado»).")
            return False
        idx = voz_entrada.resolver_entrada(nombre) if nombre else None
        if nombre and idx is None:
            self.mic_prueba.emit(json.dumps({"ok": False, "nivel": 0, "pico": 0, "nombre": nombre,
                                             "mensaje": f"No encuentro «{nombre}». ¿Está conectado?"},
                                            ensure_ascii=False))
            return False
        self._probador = ProbadorMic(idx, parent=self)
        self._probador.listo.connect(self.mic_prueba)
        self._probador.start()
        return True

    @pyqtSlot(str, result=bool)
    def probar_salida(self, nombre: str = "") -> bool:
        """Suena un tono por la salida `nombre` (vacío = sistema). Cambia la salida en caliente; Guardar la fija."""
        if not getattr(self.voice, "available", False):
            self.aviso.emit(_sin_motor_de_voz()); return False
        nombre = (nombre or "").strip()
        if nombre != self.voice.salida_actual and not self.voice.aplicar_salida(nombre):
            self.aviso.emit(f"No encontré la salida «{nombre}»; suena por la del sistema.")
        self.voice.probar_salida()
        return True

    # ── Dictado por voz (Whisper local) ──────────────────────────────────────────
    @pyqtSlot(result=str)
    def dictar(self) -> str:
        from servicios import voz_entrada
        # Si ya está grabando → parar y transcribir en un hilo.
        if self._grabadora is not None:
            grab, self._grabadora = self._grabadora, None
            self.grabando.emit(False)
            try:
                ruta = grab.detener()
            except Exception:
                ruta = None
            if not ruta:
                self.aviso.emit("No se grabó nada (pulsa el micrófono, habla, y vuelve a pulsarlo).")
                return json.dumps({"grabando": False})
            modelo = self.config.get("voz", "modelo_whisper", "base")
            self._transcriptor = _Transcriptor(ruta, modelo, self.config.get("voz", "idioma", "es"))
            self._transcriptor.listo.connect(self._on_dictado)
            self._transcriptor.error.connect(self.aviso)
            self._transcriptor.start()
            self.aviso.emit("Transcribiendo…" if voz_entrada.modelo_descargado(modelo)
                            else f"Descargando el modelo Whisper «{modelo}» (solo la primera vez)…")
            return json.dumps({"grabando": False, "transcribiendo": True})
        # Si no → empezar a grabar.
        if not voz_entrada.disponible():
            self.aviso.emit(f"Dictado: {_como_instalar(*voz_entrada.dependencias_faltantes())}")
            return json.dumps({"grabando": False, "error": "sin dependencias"})
        if self._llamada is not None:
            self.aviso.emit("Estás en llamada: Lune ya te escucha.")
            return json.dumps({"grabando": False, "error": "en llamada"})
        if self._probando_dictado():
            self.aviso.emit("Estoy probando el dictado en Ajustes: espera unos segundos.")
            return json.dumps({"grabando": False, "error": "probando"})
        idx = self._microfono_elegido()
        hay, detalle = voz_entrada.hay_microfono(idx)
        if not hay:
            self.aviso.emit(detalle)
            return json.dumps({"grabando": False, "error": "sin micrófono"})
        try:
            self._grabadora = voz_entrada.Grabadora(idx)
            self._grabadora.iniciar()
            self.grabando.emit(True)
            self.aviso.emit(f"Grabando por «{detalle}»… pulsa otra vez para parar.")
            return json.dumps({"grabando": True})
        except Exception as e:
            self._grabadora = None
            self.aviso.emit(f"No pude grabar: {e}")
            return json.dumps({"grabando": False})

    def _on_dictado(self, texto: str):
        if not (texto or "").strip():
            self.aviso.emit("No entendí nada. Prueba el micrófono en Configuración → Audio.")
            return
        self.dictado.emit(texto)

    # ── Modo llamada (conversación continua por voz) ─────────────────────────────
    @pyqtSlot(result=bool)
    def llamada_toggle(self) -> bool:
        """Enciende/apaga la llamada por voz, como el toggle de Telegram."""
        if self._llamada is not None:
            self._llamada_detener()
            return False
        from servicios import voz_entrada
        if not voz_entrada.disponible():
            self.llamada_estado.emit(False, f"Llamada: {_como_instalar(*voz_entrada.dependencias_faltantes())}")
            return False
        if self._grabadora is not None:
            self.llamada_estado.emit(False, "Termina el dictado antes de llamar."); return False
        if self._probando_dictado():
            self.llamada_estado.emit(False, "Estoy probando el dictado: espera unos segundos."); return False
        idx = self._microfono_elegido()
        hay, detalle = voz_entrada.hay_microfono(idx)
        if not hay:
            self.llamada_estado.emit(False, detalle); return False
        if not getattr(self.voice, "available", False):
            self.llamada_estado.emit(False, "No hay motor de voz para hablar."); return False
        from servicios.llamada import LlamadaWorker
        modelo = self.config.get("voz", "modelo_whisper", "base")
        self._llamada = LlamadaWorker(
            self.voice,
            modelo_whisper=modelo,
            idioma=self.config.get("voz", "idioma", "es"),
            umbral=self.config.get("voz", "llamada_umbral", 0.015),
            dispositivo=idx,
        )
        self._llamada.transcrito.connect(self._llamada_transcrito)
        self._llamada.estado.connect(self._llamada_estado)
        self._llamada.aviso.connect(self.aviso)
        self._llamada.terminado.connect(self._llamada_fin)
        self._llamada.start()
        self.llamada_estado.emit(True, "escuchando")
        self.aviso.emit(f"Llamada por «{detalle}»" + (
            "" if voz_entrada.modelo_descargado(modelo)
            else f" · la primera vez descargo el modelo Whisper «{modelo}»"))
        return True

    def _llamada_transcrito(self, texto: str):
        # El JS lo mete como mensaje del usuario y lo envía por el chat normal
        # (`enviar`). Se apunta para que ese envío cuente como oído en la llamada:
        # sus acciones directas piden permiso (_enviar, SB2).
        self._oido_llamada = str(texto or "").strip()
        self.usuario_dijo.emit(texto)

    # Estado de la llamada → JS y, si la asistente en escritorio está abierta, a ella
    # también (escuchando / hablando / pensando), para que "actúe" la llamada.
    _LLAMADA_A_ASISTENTE = {"escuchando": "listening", "transcribiendo": "thinking",
                            "esperando": "thinking", "hablando": "talking", "off": "normal"}

    def _llamada_estado(self, e: str):
        self.llamada_estado.emit(True, e)
        ov = self._overlay
        if ov is not None and hasattr(ov, "set_estado"):
            try:
                ov.set_estado(self._LLAMADA_A_ASISTENTE.get(e, "normal"))
            except Exception:
                pass

    def _llamada_entregar(self, texto: str, _asistente: str):
        # Cada respuesta final del chat: si hay llamada, el worker la habla y sigue.
        if self._llamada is not None:
            self._llamada.decir_y_seguir(texto)

    def _llamada_detener(self):
        w, self._llamada = self._llamada, None
        if w is not None:
            try:
                w.parar(); w.wait(3000)
            except Exception:
                pass
        self.llamada_estado.emit(False, "Llamada terminada")

    def _llamada_fin(self):
        if self._llamada is not None:      # el worker acabó solo (error/mic)
            self._llamada = None
            self.llamada_estado.emit(False, "Llamada terminada")

    # ── Calidad de vida: autoinicio, instalador, aburrimiento ────────────────────
    @pyqtSlot(result=bool)
    def autoinicio_get(self) -> bool:
        try:
            from servicios import autoinicio
            return autoinicio.activo()
        except Exception:
            return False

    @pyqtSlot(bool, result=bool)
    def autoinicio_set(self, quiere: bool) -> bool:
        try:
            from servicios import autoinicio
            estado = bool(autoinicio.establecer(bool(quiere)))
        except Exception:
            return False
        # sistema.autoinicio sigue al estado REAL (registro y Administrador de tareas),
        # como la bandeja y el panel nativo; solo se escribe si cambia.
        try:
            if bool(self.config.get("sistema", "autoinicio", False)) != estado:
                self.config.set("sistema", "autoinicio", estado)
        except Exception:
            pass
        self.aviso.emit("Lune arrancará con Windows" if estado else "Autoinicio desactivado")
        return estado

    @pyqtSlot(result=bool)
    def abrir_instalador(self) -> bool:
        """Abre el instalador de componentes (ventana aparte, Tkinter). Solo desde el
        código: instalada ya viene todo y no hay pip (la página esconde el botón)."""
        import subprocess, sys
        from pathlib import Path
        if _instalada():
            self.aviso.emit("Esta Lune ya viene con todo instalado: no hace falta instalar componentes.")
            return False
        ruta = Path(__file__).resolve().parent.parent / "instalador.py"
        if not ruta.exists():
            self.aviso.emit("No encontré instalador.py"); return False
        try:
            subprocess.Popen([sys.executable, str(ruta)], cwd=str(ruta.parent))
            return True
        except Exception as e:
            self.aviso.emit(f"No pude abrir el instalador: {e}"); return False

    # ── Actualizaciones (Ajustes → Sistema; ui/actualizacion_qt.ControlActualizacion) ──
    # Instalada: el último release de GitHub (descarga con SHA-256, el Setup en silencio y me
    # cierro con el «Salir» de la ventana). Desde el código: git (commits, pull + pip y
    # reiniciar). Copia sin git: solo el enlace a Releases. Todo lo lento va en un hilo y el
    # progreso llega por la señal `actualizacion` (como mucho ~4 veces por segundo).
    def _actualizaciones(self):
        act = getattr(self, "_act", None)
        if act is None:
            from ui.actualizacion_qt import ControlActualizacion, salir_de_verdad_de
            act = ControlActualizacion(self.config, salir=salir_de_verdad_de(self), parent=self)
            act.cambio.connect(self._emitir_actualizacion)
            self._act = act
        return act

    def _emitir_actualizacion(self, estado) -> None:
        try:
            self.actualizacion.emit(json.dumps(estado, ensure_ascii=False))
        except (RuntimeError, TypeError):
            pass

    def avisar_actualizacion(self, res: dict) -> None:
        """Versión nueva al abrir Lune (ui/actualizacion_qt.AvisoInicio; NO es un slot): la
        tarjeta la resalta al abrir Ajustes y sale el aviso (toast con la ventana a la vista;
        si no, el globo de la bandeja)."""
        from servicios import actualizador
        from ui.actualizacion_qt import notificar
        self._actualizaciones().recibir(res)
        texto = actualizador.texto_aviso(res)
        if not notificar(self._ventana(), texto):
            self.aviso.emit(texto)

    @pyqtSlot(result=str)
    def actualizacion_info(self) -> str:
        """{version, modo: instalada|git|carpeta, al_iniciar, ultima_comprobacion, omitir_version,
        pagina, ocupado, descargado, estado: lo último de `actualizacion`} (sin red)."""
        return json.dumps(self._actualizaciones().info(), ensure_ascii=False)

    @pyqtSlot(result=bool)
    def actualizacion_buscar(self) -> bool:
        return bool(self._actualizaciones().buscar())

    @pyqtSlot(result=bool)
    def actualizacion_descargar(self) -> bool:
        return bool(self._actualizaciones().descargar())

    @pyqtSlot(result=bool)
    def actualizacion_cancelar(self) -> bool:
        return bool(self._actualizaciones().cancelar())

    @pyqtSlot(result=bool)
    def actualizacion_instalar(self) -> bool:
        """«Instalar y reiniciar» (la página ya lo confirmó): descarga si falta, lanza el Setup y
        me cierro; desde el código, git pull + pip y reinicio."""
        return bool(self._actualizaciones().instalar())

    @pyqtSlot(str, result=bool)
    def actualizacion_omitir(self, version: str) -> bool:
        return bool(self._actualizaciones().omitir(version))

    @pyqtSlot(bool, result=bool)
    def actualizacion_al_iniciar(self, on: bool) -> bool:
        return bool(self._actualizaciones().al_iniciar(bool(on)))

    def _rearmar_aburrimiento(self):
        """(Re)arma el temporizador con los minutos de config; 0 = apagado. En pausa
        (modo juego) no se arma: pausar_aburrimiento(False) lo rearma al acabar."""
        try:
            minutos = int(self.config.get("chat", "aburrimiento_min", 10) or 0)
        except (TypeError, ValueError):
            minutos = 0
        self._aburrida_t.stop()
        if minutos > 0 and not getattr(self, "_aburrimiento_pausado", False):
            self._aburrida_t.start(minutos * 60_000)

    def pausar_aburrimiento(self, on: bool) -> None:
        """Modo juego (corte 4, AnfitrionWeb.set_aburrimiento): con `on` Lune no se
        aburre ni te habla por aburrimiento; al quitarlo, la cuenta empieza de cero."""
        on = bool(on)
        if on == bool(getattr(self, "_aburrimiento_pausado", False)):
            return
        self._aburrimiento_pausado = on
        if on:
            self._aburrida_t.stop()
        else:
            self._rearmar_aburrimiento()

    def _en_modo_juego(self) -> bool:
        """¿Hay partida? (BusEstado.juego de los servicios de escritorio)."""
        try:
            return bool(self.escritorio.estado.actual().juego)
        except Exception:
            return False

    # Frases con la personalidad de Lune: aburrimiento, una pregunta o un empujón.
    _ABURRIDA = (
        "…¿Sigues ahí? Llevo un rato mirando el cursor parpadear.",
        "Me aburro. Dime algo, aunque sea qué estás haciendo.",
        "Silencio total. ¿Trabajando duro o ya te fuiste?",
        "Pregunta rápida: ¿qué es lo más interesante que has visto hoy?",
        "Si necesitas algo, aquí sigo. Si no, me pongo a contar estrellas.",
        "¿Un descanso? Yo digo que sí. Pero cuéntame en qué andas.",
        "Llevo minutos sin que me escribas. Ya casi me da sueño.",
    )

    def _aburrida(self):
        """Lune se aburre: gesto + una línea (sin usar el modelo, sin tocar memoria)."""
        if getattr(self, "_aburrimiento_pausado", False) or self._en_modo_juego():
            return                                    # modo juego: nada de hablarte
        if self._worker is not None and self._worker.isRunning():
            self._rearmar_aburrimiento(); return       # está respondiendo: no interrumpir
        if self._bienvenida_activa():
            return          # espera tu respuesta a la bienvenida: un «me aburro» se tomaría por ella
        import random
        linea = random.choice(self._ABURRIDA)
        self.emocion.emit("bored", 1.0)
        self.done.emit(linea, "bored")                # el JS la pinta como burbuja de Lune
        self._asistente_estado("bored")                 # y se queda aburrida hasta que le escribas
        try:
            if getattr(self.voice, "_enabled", False) and self._llamada is None:
                self.voice.speak(linea)
        except Exception:
            pass
        # No se rearma: solo una vez por racha; tu siguiente mensaje la rearma.


class _Transcriptor(QThread):
    """Transcribe un WAV con Whisper local sin congelar la interfaz."""
    listo = pyqtSignal(str)
    error = pyqtSignal(str)     # motivo presentable si no se pudo (antes moría en silencio)

    def __init__(self, ruta, modelo, idioma):
        super().__init__()
        self.ruta, self.modelo, self.idioma = ruta, modelo, idioma

    def run(self):
        try:
            from servicios import voz_entrada
            texto = voz_entrada.transcribir(self.ruta, self.modelo, self.idioma)
        except Exception as e:
            self.error.emit(str(e) or "No pude transcribir.")
            return
        self.listo.emit(texto or "")
