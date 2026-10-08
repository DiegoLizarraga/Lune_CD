"""
main.py — Ventana principal de Lune CD y punto de entrada.
El código está por capas: nucleo/ (datos, config, memoria…), servicios/
(ai_manager, voice, tools…) y ui/ (paneles y widgets Qt). El núcleo de red
está en lune_core/.

Asistente (corte 3): herramientas del modelo `asistente_dormir`, `asistente_despertar`
y `asistente_tamano` con la asistente flotante a la vista (solo se ofrecen con ella
fuera: el modo del turno pasa a "asistente"/"vrm"), y el panel de modelos VRM de
Configuración recarga la asistente 3D y le aplica la calibración.

Corte 4 (modo juego, bandeja única, menú radial, atajos globales y tema): el tema se
aplica a COLORS antes de construir la interfaz (ui.theme.aplicar_tema); `_build_tray`
monta los servicios (ui/montaje_escritorio.montar_escritorio con
ui/anfitrion_nativo.AnfitrionNativo) en iniciar_servicios: UN icono de bandeja siempre
(features.minimizar_a_bandeja solo decide si cerrar oculta la ventana), la asistente sin
icono propio y el panel de Ajustes con sus apartados de escritorio
(ui/escritorio_panel_nativo.py). cerrar_para_cambio y salir los desmontan una vez.

Cortes 5 y 6 (alarmas y temporizadores, pantalla grande y salvapantallas, baile): van
dentro del montaje del corte 4 (ServiciosCorte4.ocio, ui/montaje_ocio.py). Aquí solo:
el tile ALARMAS (despachador «alarma» → el editor de alarmas), el panel de Ajustes
(PanelOcioNativo, vía usar_servicios), la carita contenta y «♪ BAILANDO» mientras
baila (_on_baile) y «avísame en 10 minutos» escrito en el chat → Ejecutor antes que
la memoria.

Cortes 7 y 8 (sentarse, comida, Discord): también dentro del montaje del corte 4
(ServiciosCorte4.vida, ui/montaje_vida.py) y el panel de Ajustes (PanelVidaNativo, vía
usar_servicios). Arranque con Windows (nucleo/arranque.py, servicios/autoinicio.py):
`main.py --autoinicio` no enseña la pantalla de inicio, espera
`sistema.autoinicio_retraso_s` y abre en la bandeja, con la asistente o con la ventana
(si mientras tanto vuelves a abrir Lune, abre ya y se ve); una segunda instancia
lanzada así se va sin traer la primera al frente. Al arrancar y al cambiar de
interfaz se repara la entrada de arranque (carpeta movida, modo cambiado).

Cortes 9 y 10 (reproductor de bailes MMD/VRMA y Minecraft): también dentro del montaje
del corte 4 (ServiciosCorte4.escenario, ui/montaje_escenario.py) y el panel de Ajustes
(PanelEscenarioNativo, vía usar_servicios). El bot de Minecraft conectado se vuelve a
conectar tras un cambio de interfaz en caliente (estado_para_cambio → "minecraft_bot").
Mientras la IA responde, el BusEstado dice `pensando` (fuente «chat»): el bot de
Minecraft pausa su modelo (comparten Ollama) y Discord pone «Pensando…».
"""
import sys
import os
import json
import threading
import time
from collections.abc import Mapping
from datetime import datetime

# ANTES de PyQt6: precarga el runtime de C++ de Windows. Si no, PyQt6 mete su
# MSVCP140.dll de 2020 y Whisper (ctranslate2) revienta el proceso al dictar.
# Detalle y motivo en nucleo/runtime_win.py.
from nucleo.runtime_win import precargar_msvc
precargar_msvc()

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QStackedWidget, QFileDialog,
    QSystemTrayIcon, QMenu, QGridLayout,
)
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QAction, QPixmap, QFontDatabase

from nucleo import adjuntos as adj

from servicios import voz_entrada

from nucleo.config import Config
from servicios.ai_manager import AIManager
from nucleo.conversaciones import GestorConversaciones
from ui.historial_panel import HistorialPanel
from nucleo.utils import Logger, log_info, log_error
from nucleo import datos, rutas

from nucleo.memoria import MemoriaManager
from nucleo.bienvenida import Bienvenida, ya_preguntada
from servicios.tools import ToolManager, ctx_acciones
from nucleo.respuestas import AVISO_ASISTENTE_SIN_NUBE, BancoRespuestas

from ui.theme import (
    COLORS, APP_VERSION, PROVIDER_META,
    FONT_DISPLAY, FONT_BODY, FONT_MONO, FONT_JP, FONT_FALLBACKS,
)
from ui import lune_face

from lune_core import marcadores, expresiones
from servicios.notas_service import NotasService
from servicios.red_service import RedService
from ui.avatar_overlay import AvatarOverlay
from ui.escritorio import ServiciosEscritorio, crear_asistente
from ui.lune_face import LuneFaceWidget, detect_emotion
from ui.icons import icon, icon_pixmap
from ui.effects import apply_glow, clear_glow
from servicios.voice import VoiceEngine, VozStreaming
from servicios.telegram_worker import (TelegramBotWorker, ordenes_activas, PREFIJO_TELEGRAM, PREFIJO_IA,
                                       AVISO_TG_DESACTIVADAS, AVISO_TG_OCUPADA, AVISO_TG_DETENIDA,
                                       SIN_TEXTO, con_aviso_pendiente)
from ui.chat_widgets import ProviderTab, MessageBubble, TypingIndicator
from servicios.ai_worker import (AIWorker, ORIGEN_NO_CONFIABLE, ORIGEN_REMOTO, ORIGEN_USUARIO,
                                 meta_proveedor)
from ui.acciones_qt import AccionesQt
from lune_core.acciones import limpiar_texto
from ui.settings_panel import SettingsPanel
from ui.optimizer_panel import OptimizadorPanel
from ui.personajes_panel import PersonajesPanel
from nucleo import personajes
from nucleo import sueno, vrm

from ui.splash import PantallaInicio
from ui.cambio_interfaz import (GestorInterfaz, bot_minecraft_de, callar_voz, cerrar_asistente,
                                desmontar_servicios_c4, detener_bot, detener_hilo_ia, hilo_vivo,
                                instantanea_sesion, ordenes_cortadas, parar_temporizadores,
                                quitar_bandeja, reconectar_bot_minecraft, retomar_sesion, soltar_hilos)

logger = Logger()

# Punto de estado de los proveedores: cada cuánto se sondea con la ventana a la vista.
SONDEO_PROVEEDORES_MS = 60000


# ─────────────────────────────────────────────────────────────────────────────
#  WORKERS AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────
class TranscripcionWorker(QThread):
    """Transcribe el audio grabado sin congelar la UI (Whisper tarda lo suyo)."""
    listo = pyqtSignal(str)
    fallo = pyqtSignal(str)

    def __init__(self, ruta_wav, modelo: str, idioma: str):
        super().__init__()
        self.ruta_wav = ruta_wav; self.modelo = modelo; self.idioma = idioma

    def run(self):
        try:
            self.listo.emit(voz_entrada.transcribir(self.ruta_wav, self.modelo, self.idioma))
        except Exception as e:
            self.fallo.emit(str(e))


class SondeoProveedoresWorker(QThread):
    """Pregunta a cada proveedor si está vivo, para el punto de estado."""
    listo = pyqtSignal(object)     # {provider_id: bool}

    def __init__(self, providers):
        super().__init__()
        self.providers = providers

    def run(self):
        try:
            self.listo.emit({pid: p.is_available() for pid, p in self.providers.items()})
        except Exception:
            self.listo.emit({})


# ─────────────────────────────────────────────────────────────────────────────
#  ÓRDENES DE TELEGRAM SIN RESPUESTA Y MODO JUEGO EN EL RELEVO
#  (funciones sueltas: sirven con la ventana de verdad y con sus dobles de test)
# ─────────────────────────────────────────────────────────────────────────────
def olvidar_ordenes_avisadas(ventana, ids) -> None:
    """Tras mandar «Se detuvo…» a Telegram, la marca del turno remoto y la última
    orden aceptada se limpian: ninguna vuelve a avisarse (un aviso por orden, el
    mismo criterio que la web). La respuesta que aún llegue ya no va a Telegram."""
    ids = {str(i) for i in (ids or ()) if i}
    if not ids:
        return
    turno = getattr(ventana, "_turno", None)
    if isinstance(turno, dict) and str(turno.get("remoto") or "") in ids:
        turno.pop("remoto", None)
    if str(getattr(ventana, "_ultima_orden_tg", "") or "") in ids:
        ventana._ultima_orden_tg = ""


def avisar_ordenes_cortadas(ventana) -> list:
    """La ventana se cierra (salir, patata, cambio de interfaz) o se para el bot con
    una orden de Telegram sin respuesta: la que se está respondiendo y la que espera
    tu permiso reciben «Se detuvo…» UNA vez. Antes de cerrar las preguntas y de parar
    el bot. Devuelve los ids avisados."""
    try:
        pend = ventana.acciones.pendientes()
    except Exception:
        pend = []
    try:
        vivo = bool(ventana._worker_vivo())
    except Exception:
        vivo = False
    ids = ordenes_cortadas(getattr(ventana, "_turno", None), vivo, pend,
                           getattr(ventana, "_ultima_orden_tg", ""))
    for oid in ids:
        ventana._responder_telegram(oid, AVISO_TG_DETENIDA)
    olvidar_ordenes_avisadas(ventana, ids)
    return ids


def juego_forzado_de(servicios):
    """El modo juego forzado a mano de los servicios del corte 4: None (detectar),
    True o False. Viaja en el cambio de interfaz (estado_para_cambio)."""
    juego = getattr(servicios, "juego", None) if servicios is not None else None
    try:
        f = getattr(juego, "forzado", None) if juego is not None else None
    except Exception:
        return None
    return f if isinstance(f, bool) else None


def soltar_avisos_voz(ventana) -> None:
    """Desengancha `voice.al_hablar` y `voice.on_error` si siguen siendo los avisos de
    `ventana` (LuneCDWindow._aviso_hablando / _aviso_voz_error): al salir, el hilo de
    audio ya no llama a la ventana que se borra."""
    voz = getattr(ventana, "voice", None)
    for attr, nombre in (("al_hablar", "_aviso_hablando"), ("on_error", "_aviso_voz_error")):
        mio = getattr(ventana, nombre, None)
        try:
            if mio is not None and getattr(voz, attr, None) == mio:
                setattr(voz, attr, None)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class LuneCDWindow(QMainWindow):
    _hablando = pyqtSignal(bool)     # la voz suena (hilo de audio) → boca de la asistente 3D
    _acto_voz = pyqtSignal(str)      # empieza a sonar un tramo con esta emoción
    _voz_error = pyqtSignal(str)     # la voz falló (hilo de audio) → aviso en la ventana
    _en_ui_senal = pyqtSignal(object)  # fn() a correr en el hilo de Qt (herramientas de la asistente)
    # (ResultadoAccion, {asistente, directo}): resultado de una acción con destino propio
    # (chat de la asistente o pedida por la persona); llega de cualquier hilo.
    _resultado_turno = pyqtSignal(object, object)
    # Ajustes pidió otro modo de interfaz (lo hace GestorInterfaz, ui/cambio_interfaz.py).
    cambio_interfaz_pedido = pyqtSignal(str)
    MODO_INTERFAZ = "nativo"         # «Bajos recursos» en Ajustes
    MODO_ACCIONES = "normal"         # modo del catálogo de herramientas en la nativa
    ESPERA_UI_S = 5.0                # herramientas de la asistente: espera máxima al hilo de Qt
    FABRICAS_C4 = None               # fábricas de montar_escritorio (tests); None = las de verdad
    def __init__(self, *, diferir_servicios: bool = False):
        """`diferir_servicios`: la construye GestorInterfaz con la ventana anterior aún
        viva; la bandeja y los servicios de escritorio (atajos globales…) arrancan
        después, en iniciar_servicios(). Ver «Cambio de modo en caliente» abajo."""
        super().__init__()
        self._relevada = False           # cerrada por un cambio de modo: sin bandeja ni quit
        self._servicios_listos = False   # bandeja y servicios de escritorio arrancados
        # Corte 4 (bandeja única, atajos, radial, modo juego, tema): lo monta _build_tray
        # en iniciar_servicios (ui/montaje_escritorio.montar_escritorio).
        self._servicios_c4 = None
        self._ultima_orden_tg = ""       # id de la última orden de Telegram aceptada
        self._hilo_qt = threading.get_ident()
        self._en_ui_senal.connect(self._correr_en_ui)
        # Config visual/features (config.json) + APIs/personalidad (datos.json)
        self.config           = Config()
        # Tema de color (sección tema, nucleo/tema.py) en COLORS ANTES de construir la
        # interfaz: los widgets nativos toman el color al crearse.
        from ui.theme import aplicar_tema
        aplicar_tema(self.config)
        self.ai_manager       = AIManager()
        self.voice = VoiceEngine(self.config)
        # La voz avisa cuándo suena (hilo de audio) → señal → boca del avatar 3D.
        # Nunca el `emit` ligado: el hilo de audio puede llamar después de borrarse esta
        # ventana (cambio de interfaz, salir) → _emitir_si_vivo.
        self._hablando.connect(self._on_hablando)
        self.voice.al_hablar = self._aviso_hablando
        self._acto_voz.connect(self._expresar)
        # Y avisa si falla (voz inexistente, sin red…) en vez de quedarse muda.
        self._voz_error.connect(self._on_voz_error)
        self.voice.on_error = self._aviso_voz_error
        # Servicios de escritorio (ui/escritorio.py): estado compartido de la
        # asistente, tabla de prioridades y registro de controladores. Recibe la
        # asistente flotante en _crear_asistente y se cierra en closeEvent.
        self.escritorio = ServiciosEscritorio(self.config, voice=self.voice,
                                              ai=self.ai_manager, parent=self)
        self._seguidor = None            # <|ACT|> vistos en el stream en curso
        self._expresado_en_stream = False
        self._timers_plan = []
        self.current_provider = "openrouter"
        self.ai_worker        = None
        self._current_bubble  = None
        self._voz_stream      = None
        self._overlay         = None
        self._typing_indicator= None
        self._tg_worker       = None
        self.tray             = None
        self._quit_real       = False
        self.memoria          = MemoriaManager()
        self.tools            = ToolManager()
        # Acciones del modelo (<|CALL …|>): handlers de esta app (cambiar_voz…) en
        # el ToolManager y un Ejecutor con aprobación visible (ui/acciones_qt.py):
        # QMessageBox con la ventana delante, DialogoAprobacion junto a la asistente
        # si no. El formato antiguo (ABRIR_URL:, TOOL:) ya no se ejecuta.
        self._registrar_herramientas_asistente()
        self.escritorio.conectar_herramientas(self.tools)
        self.acciones = AccionesQt(self.tools, ventana=self, ventana_visible=self._ventana_a_la_vista,
                                   ancla=self._ancla_asistente, parent=self)
        self.acciones.resultado.connect(self._on_resultado_accion)
        self._resultado_turno.connect(self._on_resultado_turno)
        self._turno = {}                # origen, ctx, proveedor y si salió del chat de la asistente
        # Generación del envío en curso: lo que emita un worker de un envío ya cortado
        # (conversación nueva, otro personaje…) se ignora. Ver _cortar_respuesta.
        self._gen = 0
        self._esperando_corte = False   # quisiste enviar mientras el worker viejo cortaba
        # Red de Lune: host (sirvo a otros), terminal (memoria del host) o local
        self._hub_en_hilo     = None
        self._hub_cliente     = None
        self._chat_remoto     = None    # chat vía el host (modo terminal)
        self._motor_chat      = None    # motor usado en el último envío (para el uso)
        self._modo_red        = datos.hub_modo()
        self._configurar_red()
        self._adjuntos        = []      # archivos pendientes de enviar
        self._grabadora       = None
        self._transcriptor    = None
        self._sondeo_prov     = None

        # Historial de conversaciones en disco
        self.chats = GestorConversaciones(
            max_sesiones=self.config.get("chat", "max_sesiones", 50)
        )

        # Notas + RAG (memoria larga). Perezoso: solo indexa si está activo.
        # Los arranques diferidos van por métodos de la ventana: si se cierra antes
        # (cambio de interfaz), ni se reabre el índice ni se anuncia una red ya parada.
        self.notas = NotasService(self.config)
        if self.notas.activo:
            QTimer.singleShot(1500, self._reindexar_notas)

        # Presencia en la red local: anunciarse para que otros Lune lo descubran.
        self.red = RedService(self.config)
        QTimer.singleShot(1200, self._anunciar_red)

        # Banco de respuestas instantáneas con la personalidad de Lune
        nombre_bot = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune")).get("nombre", "Lune")
        self.banco = BancoRespuestas(nombre_asistente=nombre_bot,
                                     nombre_usuario=self.memoria.get_nombre_usuario(),
                                     tareas=getattr(self, "_resumen_tareas", None))

        # Aplicar preferencias de rendimiento antes de construir la UI
        lune_face.set_active_pack(self.config.get("avatar", "pack", "default"))
        lune_face.set_anim_video(self.config.feature("animaciones_video", True))
        if self.config.feature("voz_auto", False) and self.voice.available:
            self.voice.toggle()

        self._init_ui()
        if not diferir_servicios:
            self.iniciar_servicios()         # bandeja y servicios de escritorio
        self._restaurar_o_iniciar_sesion()

        # Bienvenida (11, nucleo/bienvenida.py): si la memoria aún no sabe nada de ti, Lune te
        # hace tres preguntas por el chat. La primera sale en la siguiente vuelta del bucle
        # (temporizador hijo): después de aplicar_estado (el cambio de interfaz en caliente
        # repinta el chat) y de decidir si la ventana se ve. En modo terminal de la red (la
        # memoria es la del host) no se hace.
        self._bienvenida = Bienvenida(self.config, self.memoria, nombre_asistente=self._nombre_bot)
        # Qué pregunta (clave_paso) se ve en la ventana y en la burbuja de la asistente en
        # escritorio (solo cuenta como respuesta lo que escribes donde la viste) y cuál se ve
        # en el chat sin estar aún en chats/ (va antes del próximo turno que se guarde).
        self._bienvenida_marcas = {"ventana": None, "burbuja": None}
        self._bienvenida_sin_guardar = None
        self._timer_bienvenida = QTimer(self)
        self._timer_bienvenida.setSingleShot(True)
        self._timer_bienvenida.timeout.connect(self._arrancar_bienvenida)
        self._timer_bienvenida.start(0)

        # Punto de estado de cada proveedor, para no enterarte de que Ollama está caído al
        # mandar un mensaje: cada 60 s, pero SOLO con la ventana a la vista (showEvent lo
        # arranca y sondea; oculta en la bandeja o minimizada se para: pedía /api/tags a
        # Ollama y /models a la API compatible, que puede ser remota, sin que nadie lo viera)
        # y antes de enviar si el último sondeo es viejo (_sondear_si_viejo).
        self._timer_estado = QTimer(self)
        self._timer_estado.setInterval(SONDEO_PROVEEDORES_MS)
        self._timer_estado.timeout.connect(self._sondear_proveedores)
        self._sondeo_prov_t = None       # time.monotonic() del último sondeo lanzado

        # El aviso de versión nueva al abrir (ui/actualizacion_qt.AvisoInicio) lo programa
        # main() para las dos interfaces de ventanas: llega por avisar_actualizacion.
        log_info(f"Lune CD v{APP_VERSION} iniciado")

    def _cerrandose(self) -> bool:
        """¿Relevada por un cambio de interfaz o saliendo? (notas y red ya cerradas)."""
        return bool(getattr(self, "_relevada", False) or getattr(self, "_quit_real", False))

    def _reindexar_notas(self):
        if not self._cerrandose():
            self.notas.reindexar()

    def _anunciar_red(self):
        if not self._cerrandose():
            self.red.anunciar()

    # ── Actualizaciones ───────────────────────────────────────────────────────
    def avisar_actualizacion(self, res):
        """Versión nueva (o commits nuevos, desde el código) al abrir Lune: lo llama
        ui/actualizacion_qt.AvisoInicio (~45 s después, una vez al día, nunca en modo
        juego). El globo de la bandeja o, sin bandeja, la burbuja; Ajustes la enseña."""
        if not isinstance(res, dict) or not res.get("hay_novedades"):
            return
        from servicios import actualizador
        texto = actualizador.texto_aviso(res)
        log_info(f"[actualizaciones] {texto}")
        panel = getattr(self, "settings_panel", None)
        recibir = getattr(panel, "recibir_novedad", None)
        if callable(recibir):
            try:
                recibir(res)
            except Exception as e:
                log_error(f"[actualizaciones] Ajustes no pudo enseñarla: {e}")
        bandeja = getattr(getattr(self, "_servicios_c4", None), "bandeja", None)
        try:
            if bandeja is not None and bandeja.mostrar_aviso("Lune CD", texto, 8000):
                return
        except Exception:
            pass
        if self.tray is not None:
            self.tray.showMessage("Lune CD", texto, QSystemTrayIcon.MessageIcon.Information, 8000)
        else:
            self._burbuja_bot(f"Por cierto: {texto}")

    # ── Red de Lune (hub) ─────────────────────────────────────────────────────
    def _configurar_red(self):
        """
        host     → levanta el hub en un hilo y sirve la memoria de este equipo.
        terminal → la memoria pasa a ser la del host (con respaldo local si no
                   responde, sin bloquear la interfaz).
        local    → nada nuevo.
        """
        modo = self._modo_red
        if modo == "host":
            try:
                from lune_core import Hub, HubEnHilo, ServicioMemoria
                token = datos.asegurar_token_hub()
                hub = Hub(token, host="0.0.0.0", puerto=datos.hub_puerto())
                hub.estado_extra = {"busy": False, "model": datos.ollama_model()}
                memoria_local = self.memoria
                self._hub_en_hilo = HubEnHilo(hub, servicios=lambda h: ServicioMemoria(h, memoria_local))
                if self._hub_en_hilo.iniciar(timeout=5):
                    log_info(f"[red] host: hub sirviendo en el puerto {hub.puerto}")
                else:
                    log_error("[red] host: el hub no arrancó a tiempo")
            except Exception as e:
                log_error(f"[red] host: no pude levantar el hub: {e}")
                self._hub_en_hilo = None
        elif modo == "terminal":
            url = datos.hub_url_host()
            if not url:
                log_error("[red] terminal sin URL de host: sigo en local")
                return
            try:
                import socket
                from lune_core import ClienteEnHilo
                from lune_core.memoria_remota import MemoriaRemota
                nombre = f"app-{socket.gethostname()}".lower()
                self._hub_cliente = ClienteEnHilo(
                    url, datos.hub_token(), nombre=nombre, kind="app",
                    eventos_emitidos=["input:text"],
                    on_evento=lambda ev: log_info(f"[red] evento {ev.type} de {ev.meta.source.id}"),
                    on_estado=lambda e: log_info(f"[red] cliente: {e}"),
                )
                # Espera corta: si el host no está, la app arranca igual con la
                # memoria local y el cliente sigue reintentando por detrás.
                conectado = self._hub_cliente.iniciar(timeout=4)
                self.memoria = MemoriaRemota(self._hub_cliente, respaldo=self.memoria)
                # El chat también pasa por el host: la app no carga el modelo.
                from lune_core.chat_remota import ChatRemoto
                self._chat_remoto = ChatRemoto(self._hub_cliente)
                log_info(f"[red] terminal: {'conectado a' if conectado else 'sin conexión aún con'} {url}")
            except Exception as e:
                log_error(f"[red] terminal: {e}")
                self._hub_cliente = None

    def _estado_red(self) -> str:
        if self._modo_red == "host" and self._hub_en_hilo:
            n = len(self._hub_en_hilo.hub.peers)
            return f"host · {n} conectado(s)"
        if self._modo_red == "terminal" and self._hub_cliente:
            return f"terminal · {self._hub_cliente.estado}"
        return "local"

    # ── Sesión de chat ────────────────────────────────────────────────────────
    def _restaurar_o_iniciar_sesion(self):
        """Reabre la última conversación si procede; si no, empieza una nueva."""
        if not self.config.feature("guardar_conversaciones", True):
            return
        if self.config.get("chat", "restaurar_ultima", True):
            sesion = self.chats.ultima()
            if sesion and sesion.get("mensajes"):
                self._pintar_sesion(sesion)
                return
        self.chats.nueva_sesion(
            proveedor=self.current_provider,
            personaje=datos.get_bot().get("personaje_default", "Lune"),
        )

    def _pintar_sesion(self, sesion):
        """Vuelca una conversación guardada en el chat y en el contexto del modelo."""
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        markdown = self.config.feature("markdown", True)
        for m in sesion.get("mensajes", []):
            burbuja = MessageBubble(
                m.get("contenido", ""), is_user=(m.get("rol") == "user"),
                provider_id=sesion.get("proveedor") or self.current_provider,
                markdown=markdown,
            )
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, burbuja)

        # El modelo también tiene que saber de qué iba la conversación
        self.ai_manager.cargar_historial(self.chats.como_historial())
        self._scroll_bottom()

    def _nueva_conversacion(self):
        avisada = (self._turno or {}).get("remoto") if self._worker_vivo() else ""
        self._cortar_respuesta()                 # si la IA estaba escribiendo, eso ya no cuenta
        self.chats.nueva_sesion(
            proveedor=self.current_provider,
            personaje=datos.get_bot().get("personaje_default", "Lune"),
        )
        self.ai_manager.clear_history()
        # Presupuesto de acciones repuesto y fuera las preguntas pendientes (una orden
        # de Telegram que esperaba tu permiso recibe «Se detuvo…»).
        self._avisar_ordenes_pendientes(avisada)
        self.acciones.nueva_conversacion()
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._add_welcome()
        if isinstance(getattr(self, "_bienvenida", None), Bienvenida):
            self._repintar_pregunta_bienvenida([])    # bienvenida a medias: sigue su pregunta
        self.lune_face.set_state("normal")
        self.stack.setCurrentIndex(0)
        if hasattr(self, "historial_panel"):
            self.historial_panel.refrescar()

    def _abrir_conversacion(self, sesion_id):
        sesion = self.chats.cargar(sesion_id)
        if not sesion:
            QMessageBox.warning(self, "No pude abrirla", "Esa conversación ya no está."); return
        avisada = (self._turno or {}).get("remoto") if self._worker_vivo() else ""
        self._cortar_respuesta()                 # la respuesta en curso era de la otra
        self._avisar_ordenes_pendientes(avisada)
        self.acciones.nueva_conversacion()       # otra conversación: presupuesto propio
        self._pintar_sesion(sesion)
        if isinstance(getattr(self, "_bienvenida", None), Bienvenida):
            # Bienvenida a medias: lo siguiente que escribas sigue siendo la respuesta, así
            # que la pregunta tiene que verse (salvo que esa conversación ya termine en ella).
            self._repintar_pregunta_bienvenida(sesion.get("mensajes") or [])
            self._scroll_bottom()
        self.stack.setCurrentIndex(0)
        self.historial_panel.refrescar()

    def _guardar_turno(self, rol, contenido, adjuntos=None, uso=None, no_confiable=False,
                       bienvenida=False):
        if self.config.feature("guardar_conversaciones", True):
            # Las marcas solo viajan si hace falta (dobles de test con la firma vieja).
            # «bienvenida»: turno de las tres preguntas (se ve, pero no vuelve al modelo).
            extra = {"no_confiable": True} if no_confiable else {}
            if bienvenida:
                extra["bienvenida"] = True
            self.chats.agregar(rol, contenido, adjuntos=adjuntos, uso=uso, **extra)

    # ── Estado de los proveedores ─────────────────────────────────────────────
    def _sondear_proveedores(self):
        if self._sondeo_prov and self._sondeo_prov.isRunning():
            return
        self._sondeo_prov_t = time.monotonic()
        self._sondeo_prov = SondeoProveedoresWorker(self.ai_manager.providers)
        self._sondeo_prov.listo.connect(self._on_estado_proveedores)
        self._sondeo_prov.start()

    def _sondear_si_viejo(self):
        """Antes de enviar (o al volver a verse): sondea si el último tiene más de un
        intervalo (o nunca hubo), para que el punto de estado no mienta."""
        t = getattr(self, "_sondeo_prov_t", None)
        if t is None or time.monotonic() - t >= SONDEO_PROVEEDORES_MS / 1000:
            self._sondear_proveedores()

    def _ventana_se_ve(self) -> bool:
        try:
            return bool(self.isVisible() and not self.isMinimized())
        except RuntimeError:
            return False

    def _al_cambiar_visibilidad(self):
        """showEvent/hideEvent/minimizar: el sondeo periódico solo con la ventana a la vista."""
        timer = getattr(self, "_timer_estado", None)
        if timer is None or self._cerrandose():
            return
        if self._ventana_se_ve():
            if not timer.isActive():
                timer.start()
                self._sondear_si_viejo()
        else:
            timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._al_cambiar_visibilidad()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._al_cambiar_visibilidad()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._al_cambiar_visibilidad()

    def _on_estado_proveedores(self, estados):
        for pid, disponible in (estados or {}).items():
            tab = self.provider_tabs.get(pid)
            if not tab:
                continue
            if pid == "ollama":
                detalle = (f"Ollama responde en {datos.ollama_url()}" if disponible
                           else f"Sin respuesta de {datos.ollama_url()}")
            elif pid == "compat":
                detalle = (f"Responde en {datos.compat_url()}" if disponible
                           else f"Sin respuesta de {datos.compat_url()}")
            else:
                detalle = "API key configurada" if disponible else "Falta la API key"
            tab.set_estado(disponible, detalle)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(f"Lune CD · IA Activa · {self._estado_red()}")
        self.setGeometry(80, 60, 1200, 800)
        self.setMinimumSize(900, 640)
        self.setStyleSheet(f"QMainWindow,QWidget{{background:{COLORS['bg']};}}")

        for ext in ("ico","png"):
            icon_path = str(rutas.recurso("assets", f"lune_icon.{ext}"))
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path)); break

        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        sidebar = QFrame(); sidebar.setFixedWidth(248)
        sidebar.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border-right:2px solid {COLORS['border']};}}")
        layout = QVBoxLayout(sidebar); layout.setContentsMargins(12,20,12,16); layout.setSpacing(4)

        # ── MARCA: logo en caja + "LUNE CD" (CD en cyan) ──
        logo_row = QHBoxLayout(); logo_row.setSpacing(11)
        mark = QLabel(); mark.setFixedSize(42, 42)
        icon_path = str(rutas.recurso("assets", "lune_icon.png"))
        if os.path.exists(icon_path):
            pm = QPixmap(icon_path).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            mark.setPixmap(pm); mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            mark.setText("月"); mark.setFont(QFont(FONT_JP, 20, QFont.Weight.Bold)); mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"background:{COLORS['bg']};border:2px solid {COLORS['cyan_dark']};border-radius:2px;color:{COLORS['yellow']};")
        title = QVBoxLayout(); title.setSpacing(2)
        nombre_bot = datos.get_personaje(datos.get_bot().get("personaje_default","Lune")).get("nombre", "Lune")
        self.sidebar_t1 = QLabel(self._marca_sidebar(nombre_bot))
        self.sidebar_t1.setFont(QFont(FONT_DISPLAY,15,QFont.Weight.Bold)); self.sidebar_t1.setStyleSheet("background:transparent;letter-spacing:2px;")
        t2 = QLabel(f"ルネ · HÍBRIDO v{APP_VERSION}"); t2.setFont(QFont(FONT_MONO,8)); t2.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;letter-spacing:1px;")
        title.addWidget(self.sidebar_t1); title.addWidget(t2)
        logo_row.addWidget(mark); logo_row.addLayout(title,1)
        layout.addLayout(logo_row)

        layout.addWidget(self._overline("// RED NEURONAL"))

        self.provider_tabs = {}
        self._sidebar_layout = layout
        for pid, meta in PROVIDER_META.items():
            tab = ProviderTab(pid, meta)
            tab.clicked.connect(self._switch_provider)
            self.provider_tabs[pid] = tab
            layout.addWidget(tab)
        self.provider_tabs["openrouter"].set_active(True)
        # Tercera pestaña: API compatible con OpenAI, solo si está configurada.
        self._sincronizar_tab_compat()

        layout.addStretch()

        # ── ESCENARIO DE LUNE (su cara en la barra lateral) ──
        self.lune_face = LuneFaceWidget()
        fc = QHBoxLayout(); fc.setContentsMargins(0,0,0,0)
        fc.addStretch(); fc.addWidget(self.lune_face); fc.addStretch()
        layout.addLayout(fc)

        # ── ACCIONES: grid de tiles ──
        layout.addWidget(self._overline("// ACCIONES"))
        grid = QGridLayout(); grid.setSpacing(7)
        self._keys_btn = self._tile_btn("AJUSTES", "gear"); self._keys_btn.clicked.connect(self._toggle_keys_panel)
        pers_btn = self._tile_btn("PERSONAJES", "user"); pers_btn.clicked.connect(self._toggle_personajes)
        opt_btn  = self._tile_btn("OPTIMIZAR", "bolt");  opt_btn.clicked.connect(self._toggle_optimizer)
        mem_btn  = self._tile_btn("MEMORIA", "brain");    mem_btn.clicked.connect(self._show_memoria)
        tools_btn= self._tile_btn("TOOLS", "tool");      tools_btn.clicked.connect(self._show_tools)
        hist_btn = self._tile_btn("HISTORIAL", "history"); hist_btn.clicked.connect(self._toggle_historial)
        # Asistente en escritorio: sacarla o guardarla («ASISTENTE» a secas era ambiguo: la app
        # entera es la asistente).
        masc_btn = self._tile_btn("ESCRITORIO", "user"); masc_btn.clicked.connect(self._toggle_overlay)
        masc_btn.setToolTip("Asistente en escritorio: sácame al escritorio o guárdame")
        # Cortes 5/6: alarmas y temporizadores (el editor, por el despachador «alarma»).
        alarm_btn = self._tile_btn("ALARMAS", "alarm"); alarm_btn.clicked.connect(self._abrir_alarmas)
        # El tile de Telegram era relleno visual sin acción y solo aparecía si
        # había voz. Ahora es el que enciende y apaga el bot, en lugar del botón
        # ancho que se salía de la barra lateral.
        self._telegram_tile = self._tile_btn("TELEGRAM", "telegram")
        self._telegram_tile.clicked.connect(self._toggle_telegram)
        self._set_telegram_btn_style(False)

        grid.addWidget(self._keys_btn, 0, 0); grid.addWidget(pers_btn, 0, 1)
        grid.addWidget(opt_btn, 1, 0); grid.addWidget(mem_btn, 1, 1)
        grid.addWidget(tools_btn, 2, 0); grid.addWidget(hist_btn, 2, 1)
        grid.addWidget(masc_btn, 4, 0); grid.addWidget(alarm_btn, 4, 1)
        if self.voice.available:
            self._voice_btn = self._tile_btn("VOZ: OFF", "volume_off")
            self._voice_btn.clicked.connect(self._toggle_voice)
            grid.addWidget(self._voice_btn, 3, 0)
            grid.addWidget(self._telegram_tile, 3, 1)
        else:
            grid.addWidget(self._telegram_tile, 3, 0)
        layout.addLayout(grid)

        # ── LIMPIAR CHAT (ancho completo, hover rojo) ──
        clear_btn = QPushButton(" LIMPIAR CHAT"); clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setIcon(icon("trash", COLORS["text_dim"], 15)); clear_btn.setIconSize(QSize(15, 15))
        clear_btn.setFont(QFont(FONT_DISPLAY,10,QFont.Weight.Bold)); clear_btn.setFixedHeight(36)
        clear_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{COLORS['text_dim']};border:2px solid {COLORS['border']};border-radius:2px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['error']}22;color:{COLORS['error']};border-color:{COLORS['error']};}}")
        clear_btn.clicked.connect(self._clear_chat); layout.addWidget(clear_btn)

        return sidebar

    def _overline(self, texto):
        lbl = QLabel(texto); lbl.setFont(QFont(FONT_MONO,8,QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;padding:6px 4px 2px 6px;letter-spacing:2px;")
        return lbl

    def _tile_btn(self, label, svg=None):
        b = QPushButton(" " + label); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont(FONT_MONO,8,QFont.Weight.Bold)); b.setFixedHeight(48)
        if svg:
            from PyQt6.QtCore import QSize
            b.setIcon(icon(svg, COLORS["text_muted"], 18)); b.setIconSize(QSize(18, 18))
        b.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['text_dim']};border:2px solid {COLORS['border']};border-radius:2px;letter-spacing:1px;text-align:center;}}QPushButton:hover{{background:{COLORS['surface3']};color:{COLORS['accent']};border-color:{COLORS['cyan_dark']};}}")
        return b

    def _set_telegram_btn_style(self, active, detalle=""):
        """Pinta el tile de Telegram según esté el bot encendido o apagado."""
        self._telegram_tile.setIconSize(QSize(18, 18))
        if active:
            self._telegram_tile.setText(" TG: ON")
            self._telegram_tile.setIcon(icon("telegram", COLORS["bg"], 18))
            self._telegram_tile.setStyleSheet(
                f"QPushButton{{background:{COLORS['telegram']};color:{COLORS['bg']};"
                f"border:2px solid {COLORS['telegram']};border-radius:2px;"
                f"letter-spacing:1px;text-align:center;font-weight:bold;}}"
                f"QPushButton:hover{{background:{COLORS['telegram_dark']};color:#FFFFFF;}}"
            )
        else:
            self._telegram_tile.setText(" TELEGRAM")
            self._telegram_tile.setIcon(icon("telegram", COLORS["text_muted"], 18))
            self._telegram_tile.setStyleSheet(
                f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['text_dim']};"
                f"border:2px solid {COLORS['border']};border-radius:2px;"
                f"letter-spacing:1px;text-align:center;}}"
                f"QPushButton:hover{{background:{COLORS['surface3']};"
                f"color:{COLORS['telegram']};border-color:{COLORS['telegram']};}}"
            )
        self._telegram_tile.setToolTip(
            detalle or ("Bot de Telegram activo · clic para apagarlo"
                        if active else "Encender el bot de Telegram")
        )

    def _sidebar_btn(self, label):
        btn = QPushButton(f"  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor); btn.setFont(QFont(FONT_MONO,9,QFont.Weight.Bold)); btn.setFixedHeight(38)
        btn.setStyleSheet(f"QPushButton{{background:transparent;color:{COLORS['text_muted']};border:none;border-left:2px solid transparent;border-radius:0px;text-align:left;padding-left:10px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface2']};color:{COLORS['accent']};border-left:2px solid {COLORS['accent']};}}")
        return btn

    def _show_memoria(self):
        texto = self.memoria._cmd_listar()
        bubble = MessageBubble(texto, is_user=False, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.lune_face.set_state("reading", auto_revert_ms=5000); self._scroll_bottom()

    def _abrir_alarmas(self):
        """Tile ALARMAS: el editor de alarmas y temporizadores (ControlAlarmasQt, por la
        acción «alarma» del despachador). Sin los servicios de ocio, un aviso."""
        desp = getattr(getattr(self, "_servicios_c4", None), "despachador", None)
        try:
            if desp is not None and desp.tiene("alarma") and desp.ejecutar("alarma"):
                return
        except Exception as e:
            log_error(f"[alarmas] no pude abrir el editor: {e}")
        QMessageBox.information(self, "Alarmas", "Las alarmas no están disponibles ahora mismo.")

    def _on_baile(self, js: str):
        """ControlBaile.estado_cambio (cortes 5/6): mientras baila, la carita contenta y
        «♪ BAILANDO» en la barra de estado; al parar, lo de antes (si nadie lo cambió)."""
        try:
            e = json.loads(js) if isinstance(js, str) else {}
        except (TypeError, ValueError):
            return
        bailando = bool(isinstance(e, dict) and e.get("bailando"))
        try:                                         # slot de una señal: nunca lanza
            if bailando:
                app = str(e.get("app") or "")[:24]
                self._bailando_ui = True
                self._set_status("♪ BAILANDO" + (f" · {app.upper()}" if app else ""), COLORS["accent"])
                self.lune_face.set_state("happy")
            elif getattr(self, "_bailando_ui", False):
                self._bailando_ui = False
                if str(self.status_label.text()).startswith("♪ BAILANDO"):
                    self._set_status("LISTO", COLORS["success"])
                    self.lune_face.set_state("normal")
        except Exception as ex:
            log_error(f"[baile] no pude pintar el estado del baile: {ex}")

    def _show_tools(self):
        texto = self.tools.listar_disponibles()
        bubble = MessageBubble(texto, is_user=False, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.lune_face.set_state("reading", auto_revert_ms=5000); self._scroll_bottom()

    # ── TELEGRAM ──────────────────────────────────────────────────────────────
    def _toggle_telegram(self):
        if hasattr(self,"_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            # Una /pc sin respuesta se entera antes de que el bot se vaya («Se detuvo…», una vez).
            avisar_ordenes_cortadas(self)
            self._tg_worker.stop(); self._tg_worker.requestInterruption(); self._tg_worker.wait(3000); self._tg_worker = None
            self._set_telegram_btn_style(False); return
        if not datos.telegram_token() or "TU_TOKEN" in datos.telegram_token():
            QMessageBox.warning(self,"Token faltante","Configura tu token de Telegram en la Configuración General."); return
        if not TelegramBotWorker.preparar_carpeta():
            QMessageBox.warning(self,"Carpeta no encontrada",f"No encontré la carpeta del bot en:\n{TelegramBotWorker.BOT_DIR}"); return
        # Órdenes desde Telegram (/pc): el canal solo se abre si está activado y hay tu ID.
        self._tg_worker = TelegramBotWorker(ordenes=ordenes_activas(self.config)); self._tg_worker.log_signal.connect(self._on_telegram_log); self._tg_worker.stopped.connect(self._on_telegram_stopped)
        self._tg_worker.orden_recibida.connect(self._orden_remota, Qt.ConnectionType.QueuedConnection)
        self._tg_worker.start(); self._set_telegram_btn_style(True, "Iniciando el bot…")

    def _on_telegram_log(self, line):
        log_info(f"[Telegram] {line}")
        # El detalle va al tooltip del tile; ya no hay etiqueta de estado.
        if any(k in line for k in ["Bot iniciado","iniciado","Modelo:","Error"]):
            self._telegram_tile.setToolTip(line[:120])

    def _on_telegram_stopped(self):
        self._set_telegram_btn_style(False, "Bot detenido")

    # ── MAIN AREA ─────────────────────────────────────────────────────────────
    def _build_main(self):
        main = QFrame(); main.setStyleSheet(f"QFrame{{background:{COLORS['bg']};border:none;}}")
        layout = QVBoxLayout(main); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget(); self.stack.setStyleSheet("QStackedWidget{background:transparent;}")
        self.stack.addWidget(self._build_chat_page())        # 0
        self.stack.addWidget(self._build_keys_page())        # 1
        self.stack.addWidget(self._build_optimizer_page())   # 2
        self.stack.addWidget(self._build_personajes_page())  # 3
        self.stack.addWidget(self._build_historial_page())   # 4
        layout.addWidget(self.stack,1); layout.addWidget(self._build_input_bar())
        return main

    def _build_topbar(self):
        bar = QFrame(); bar.setFixedHeight(60)
        bar.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border-bottom:2px solid {COLORS['border']};}}")
        layout = QHBoxLayout(bar); layout.setContentsMargins(20,0,20,0)
        meta = meta_proveedor(self.current_provider)
        self.topbar_icon = QLabel(meta["icon"]); self.topbar_icon.setFixedSize(30,30)
        self.topbar_icon.setFont(QFont(FONT_DISPLAY,13,QFont.Weight.Bold)); self.topbar_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._style_topbar_icon(meta)
        self.topbar_title = QLabel(meta["label"]); self.topbar_title.setFont(QFont(FONT_DISPLAY,13,QFont.Weight.Bold)); self.topbar_title.setStyleSheet(f"color:{meta['color']};background:transparent;letter-spacing:1px;")
        self.topbar_desc = QLabel("·  "+meta["desc"]); self.topbar_desc.setFont(QFont(FONT_MONO,9)); self.topbar_desc.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;")
        layout.addWidget(self.topbar_icon); layout.addSpacing(8); layout.addWidget(self.topbar_title); layout.addWidget(self.topbar_desc); layout.addStretch()
        self.status_dot = QLabel("●"); self.status_dot.setFont(QFont("Segoe UI",10)); self.status_dot.setStyleSheet(f"color:{COLORS['success']};background:transparent;")
        self.status_label = QLabel("LISTO"); self.status_label.setFont(QFont(FONT_MONO,9,QFont.Weight.Bold)); self.status_label.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;letter-spacing:1px;")
        layout.addWidget(self.status_dot); layout.addSpacing(4); layout.addWidget(self.status_label)
        return bar

    def _style_topbar_icon(self, meta):
        c, d = meta["color"], meta["dark"]
        self.topbar_icon.setStyleSheet(
            f"background:{d}33;border:2px solid {c};border-radius:2px;"
        )
        if meta.get("svg"):
            self.topbar_icon.setPixmap(icon_pixmap(meta["svg"], c, 16))
        apply_glow(self.topbar_icon, c, radius=14, alpha=130)

    def _build_chat_page(self):
        page = QFrame(); page.setStyleSheet("QFrame{background:transparent;}")
        layout = QVBoxLayout(page); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setStyleSheet(f"QScrollArea{{border:none;background:transparent;}}QScrollBar:vertical{{border:none;background:{COLORS['surface']};width:6px;border-radius:3px;}}QScrollBar::handle:vertical{{background:{COLORS['scrollbar']};border-radius:3px;min-height:20px;}}QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        self.scroll.setWidgetResizable(True)
        self.chat_container = QFrame(); self.chat_container.setStyleSheet("QFrame{background:transparent;}")
        self.messages_layout = QVBoxLayout(self.chat_container); self.messages_layout.setContentsMargins(0,16,0,16); self.messages_layout.setSpacing(6); self.messages_layout.addStretch()
        self.scroll.setWidget(self.chat_container); layout.addWidget(self.scroll); self._add_welcome()
        return page

    def _build_keys_page(self):
        page = QFrame(); page.setStyleSheet("QFrame{background:transparent;}")
        layout = QVBoxLayout(page); layout.setContentsMargins(10,10,10,10)
        # Servicios del corte 4 (atajos, modo juego, tema…): se montan después, en
        # iniciar_servicios; el panel los lee cuando los necesita.
        self.settings_panel = SettingsPanel(self.config, voice=self.voice,
                                            servicios=lambda: getattr(self, "_servicios_c4", None))
        self.settings_panel.saved.connect(self._on_keys_saved); layout.addWidget(self.settings_panel)
        # Panel de modelos VRM (importar, asignar, seguimiento) → la asistente 3D al día.
        senal_vrm = getattr(self.settings_panel, "vrm_cambiado", None)
        if senal_vrm is not None:
            senal_vrm.connect(self._on_vrm_cambiado)
        return page

    def _build_optimizer_page(self):
        page = QFrame(); page.setStyleSheet("QFrame{background:transparent;}")
        layout = QVBoxLayout(page); layout.setContentsMargins(10,10,10,10)
        self.optimizer_panel = OptimizadorPanel(self.config); layout.addWidget(self.optimizer_panel)
        return page

    def _build_personajes_page(self):
        page = QFrame(); page.setStyleSheet("QFrame{background:transparent;}")
        layout = QVBoxLayout(page); layout.setContentsMargins(10,10,10,10)
        self.personajes_panel = PersonajesPanel()
        self.personajes_panel.elegido.connect(self._switch_character)
        layout.addWidget(self.personajes_panel)
        return page

    def _build_historial_page(self):
        page = QFrame(); page.setStyleSheet("QFrame{background:transparent;}")
        layout = QVBoxLayout(page); layout.setContentsMargins(10,10,10,10)
        self.historial_panel = HistorialPanel(self.chats)
        self.historial_panel.abrir.connect(self._abrir_conversacion)
        self.historial_panel.nueva.connect(self._nueva_conversacion)
        layout.addWidget(self.historial_panel)
        return page

    def _build_input_bar(self):
        bar = QFrame(); bar.setFixedHeight(118)
        bar.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border-top:2px solid {COLORS['border']};}}")
        externo = QVBoxLayout(bar); externo.setContentsMargins(20, 8, 20, 14); externo.setSpacing(6)

        # Fila de adjuntos pendientes (oculta si no hay ninguno)
        self.fila_adjuntos = QFrame()
        self.fila_adjuntos.setStyleSheet("QFrame{background:transparent;border:none;}")
        self.layout_adjuntos = QHBoxLayout(self.fila_adjuntos)
        self.layout_adjuntos.setContentsMargins(0, 0, 0, 0); self.layout_adjuntos.setSpacing(6)
        self.layout_adjuntos.addStretch()
        self.fila_adjuntos.hide()
        externo.addWidget(self.fila_adjuntos)

        fila = QWidget(); fila.setStyleSheet("background:transparent;")
        layout = QHBoxLayout(fila); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(10)

        glyph = QLabel(">"); glyph.setFont(QFont(FONT_MONO,15,QFont.Weight.Bold))
        glyph.setStyleSheet(f"color:{COLORS['accent']};background:transparent;")

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Dime qué necesitas…  (Enter para enviar)")
        self.input_field.setFont(QFont(FONT_BODY,11)); self.input_field.setFixedHeight(46)
        self.input_field.setStyleSheet(f"QLineEdit{{background:{COLORS['surface2']};border:2px solid {COLORS['border']};border-radius:3px;padding:0 16px;color:{COLORS['text']};}}QLineEdit:focus{{border:2px solid {COLORS['accent']};background:{COLORS['surface3']};}}")
        self.input_field.returnPressed.connect(self._send_message)
        self.input_field.installEventFilter(self)

        self.send_btn = QPushButton(); self.send_btn.setFixedSize(46,46)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setIcon(icon("send", COLORS["bg"], 20)); self.send_btn.setIconSize(QSize(20, 20))
        self._update_send_btn_color()
        self.send_btn.clicked.connect(self._send_message)

        self.stop_btn = QPushButton(); self.stop_btn.setFixedSize(46, 46)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setIcon(icon("stop", COLORS["bg"], 16)); self.stop_btn.setIconSize(QSize(16, 16))
        self.stop_btn.setStyleSheet(f"QPushButton{{background:{COLORS['error']};color:{COLORS['bg']};border:none;border-radius:3px;}}QPushButton:hover{{background:#ff5c78;}}")
        self.stop_btn.clicked.connect(self._stop_generation)
        self.stop_btn.hide()

        # Adjuntar documentos e imágenes
        self.clip_btn = QPushButton(); self.clip_btn.setFixedSize(46, 46)
        self.clip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clip_btn.setIcon(icon("clip", COLORS["text_muted"], 18)); self.clip_btn.setIconSize(QSize(18, 18))
        self.clip_btn.setToolTip("Adjuntar documento o imagen")
        self.clip_btn.setStyleSheet(self._estilo_btn_secundario())
        self.clip_btn.clicked.connect(self._elegir_adjunto)

        # Dictado por voz
        self.mic_btn = QPushButton(); self.mic_btn.setFixedSize(46, 46)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setIcon(icon("mic", COLORS["text_muted"], 18)); self.mic_btn.setIconSize(QSize(18, 18))
        self.mic_btn.setToolTip("Dictar (clic para empezar, clic para parar)")
        self.mic_btn.setStyleSheet(self._estilo_btn_secundario())
        self.mic_btn.clicked.connect(self._toggle_dictado)

        layout.addWidget(glyph); layout.addWidget(self.input_field, 1)
        layout.addWidget(self.clip_btn); layout.addWidget(self.mic_btn)
        layout.addWidget(self.send_btn); layout.addWidget(self.stop_btn)
        externo.addWidget(fila)
        return bar

    def _estilo_btn_secundario(self, activo=False):
        if activo:
            return (f"QPushButton{{background:{COLORS['error']};border:2px solid {COLORS['error']};"
                    f"border-radius:3px;}}QPushButton:hover{{background:#ff5c78;}}")
        return (f"QPushButton{{background:{COLORS['surface2']};border:2px solid {COLORS['border']};"
                f"border-radius:3px;}}QPushButton:hover{{background:{COLORS['surface3']};"
                f"border-color:{COLORS['accent']};}}")

    # ── Adjuntos ──────────────────────────────────────────────────────────────
    def _elegir_adjunto(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Adjuntar archivos", "", adj.filtro_dialogo()
        )
        for ruta in rutas:
            try:
                a = adj.cargar(ruta, max_caracteres=self.config.get("adjuntos", "max_caracteres", 20000))
            except ValueError as e:
                QMessageBox.warning(self, "No pude leer el archivo", str(e))
                continue
            self._adjuntos.append(a)
        self._refrescar_adjuntos()

    def _refrescar_adjuntos(self):
        while self.layout_adjuntos.count() > 1:
            item = self.layout_adjuntos.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._adjuntos:
            self.fila_adjuntos.hide()
            return

        for i, a in enumerate(self._adjuntos):
            chip = QFrame()
            chip.setStyleSheet(
                f"QFrame{{background:{COLORS['surface2']};border:1px solid {COLORS['cyan_dark']};"
                f"border-radius:2px;}}"
            )
            cl = QHBoxLayout(chip); cl.setContentsMargins(8, 3, 4, 3); cl.setSpacing(6)
            nombre = a["nombre"]
            detalle = f"{a['bytes']//1024} KB" if a["tipo"] == "imagen" else f"{a['caracteres']} car."
            lbl = QLabel(f"{'🖼' if a['tipo'] == 'imagen' else '📄'} {nombre}  ·  {detalle}")
            lbl.setFont(QFont(FONT_MONO, 8))
            lbl.setStyleSheet(f"color:{COLORS['accent']};background:transparent;border:none;")
            quitar = QPushButton(); quitar.setFixedSize(16, 16)
            quitar.setCursor(Qt.CursorShape.PointingHandCursor)
            quitar.setIcon(icon("close", COLORS["text_dim"], 10)); quitar.setIconSize(QSize(10, 10))
            quitar.setStyleSheet("QPushButton{background:transparent;border:none;}")
            quitar.clicked.connect(lambda _=False, idx=i: self._quitar_adjunto(idx))
            cl.addWidget(lbl); cl.addWidget(quitar)
            self.layout_adjuntos.insertWidget(self.layout_adjuntos.count() - 1, chip)

        self.fila_adjuntos.show()

    def _quitar_adjunto(self, idx):
        if 0 <= idx < len(self._adjuntos):
            self._adjuntos.pop(idx)
        self._refrescar_adjuntos()

    # ── Dictado ───────────────────────────────────────────────────────────────
    def _toggle_dictado(self):
        if self._grabadora and self._grabadora.grabando:
            self._parar_dictado()
            return

        faltan = voz_entrada.dependencias_faltantes()
        if faltan:
            QMessageBox.information(self, "Falta instalar algo", voz_entrada.mensaje_instalacion())
            return
        hay_mic, detalle = voz_entrada.hay_microfono()
        if not hay_mic:
            QMessageBox.warning(self, "Sin micrófono", detalle); return

        try:
            self._grabadora = voz_entrada.Grabadora()
            self._grabadora.iniciar()
        except Exception as e:
            QMessageBox.warning(self, "No pude grabar", str(e)); return

        self.mic_btn.setIcon(icon("mic", "#FFFFFF", 18))
        self.mic_btn.setStyleSheet(self._estilo_btn_secundario(activo=True))
        self.mic_btn.setToolTip("Grabando… clic para parar")
        self._set_status("GRABANDO", COLORS["error"])
        self.lune_face.set_state("reading")

    def _parar_dictado(self):
        wav = self._grabadora.detener() if self._grabadora else None
        self._grabadora = None
        self.mic_btn.setIcon(icon("mic", COLORS["text_muted"], 18))
        self.mic_btn.setStyleSheet(self._estilo_btn_secundario())
        self.mic_btn.setToolTip("Dictar (clic para empezar, clic para parar)")

        if wav is None:
            self._set_status("LISTO", COLORS["success"])
            self.lune_face.set_state("normal")
            return

        self._set_status("TRANSCRIBIENDO", COLORS["warning"])
        self.mic_btn.setEnabled(False)
        self._transcriptor = TranscripcionWorker(
            wav,
            self.config.get("voz", "modelo_whisper", "base"),
            self.config.get("voz", "idioma", "es"),
        )
        self._transcriptor.listo.connect(self._on_transcrito)
        self._transcriptor.fallo.connect(self._on_transcripcion_fallo)
        self._transcriptor.start()

    def _on_transcrito(self, texto):
        self.mic_btn.setEnabled(True)
        self._set_status("LISTO", COLORS["success"])
        self.lune_face.set_state("normal")
        if not texto.strip():
            self._set_status("NO TE OÍ", COLORS["warning"]); return
        # Se deja en el campo para que puedas corregir antes de enviar
        actual = self.input_field.text().strip()
        self.input_field.setText(f"{actual} {texto}".strip())
        self.input_field.setFocus()

    def _on_transcripcion_fallo(self, error):
        self.mic_btn.setEnabled(True)
        self._set_status("LISTO", COLORS["success"])
        self.lune_face.set_state("normal")
        QMessageBox.warning(self, "No pude transcribir", error)

    def _add_welcome(self):
        welcome = QFrame(); welcome.setStyleSheet("QFrame{background:transparent;}")
        wl = QVBoxLayout(welcome); wl.setAlignment(Qt.AlignmentFlag.AlignCenter); wl.setSpacing(8)

        # Marca de bienvenida: logo/月 en un escenario enmarcado (estilo del UI kit)
        mark = QLabel(); mark.setFixedSize(140, 140); mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wicon = str(rutas.recurso("assets", "lune_icon.png"))
        if os.path.exists(wicon):
            mark.setPixmap(QPixmap(wicon).scaled(118, 118, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            mark.setText("月"); mark.setFont(QFont(FONT_JP, 56, QFont.Weight.Bold))
        mark.setStyleSheet(f"background:{COLORS['bg']};border:2px solid {COLORS['cyan_dark']};border-radius:3px;color:{COLORS['yellow']};")
        apply_glow(mark, COLORS["cyan"], radius=28, alpha=120)
        mark_row = QHBoxLayout(); mark_row.addStretch(); mark_row.addWidget(mark); mark_row.addStretch()

        jp = QLabel("ルネ"); jp.setFont(QFont(FONT_JP,14,QFont.Weight.Bold)); jp.setAlignment(Qt.AlignmentFlag.AlignCenter); jp.setStyleSheet(f"color:{COLORS['yellow']};background:transparent;letter-spacing:4px;")

        personaje = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune"))
        self.welcome_t1 = QLabel(personaje.get("nombre", "Lune AI").upper())
        self.welcome_t1.setFont(QFont(FONT_DISPLAY,22,QFont.Weight.Bold)); self.welcome_t1.setAlignment(Qt.AlignmentFlag.AlignCenter); self.welcome_t1.setStyleSheet(f"color:{COLORS['text']};background:transparent;letter-spacing:3px;")

        nombre = self.memoria.get_nombre_usuario()
        saludo = personaje.get("fraseInicial", f"De vuelta, {nombre}. Dime qué necesitas." if nombre else "Lune en línea. Dime qué necesitas.")
        stats  = self.memoria.get_stats()
        total  = stats.get("total_mensajes", 0)
        sub    = saludo + (f"\n\n{total} mensajes en total." if total else "")

        self.welcome_t2 = QLabel(sub); self.welcome_t2.setFont(QFont(FONT_MONO,10)); self.welcome_t2.setAlignment(Qt.AlignmentFlag.AlignCenter); self.welcome_t2.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;")
        wl.addStretch(); wl.addLayout(mark_row); wl.addWidget(jp); wl.addWidget(self.welcome_t1); wl.addWidget(self.welcome_t2)

        # Chips de acción rápida (mejora visual + accesos directos)
        chips_row = QHBoxLayout(); chips_row.setSpacing(8); chips_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chips = [
            ("SALUDAR", lambda: self._chip_enviar("Hola Lune")),
            ("OPTIMIZAR PC", self._toggle_optimizer),
            ("MI MEMORIA", self._show_memoria),
            ("HERRAMIENTAS", self._show_tools),
        ]
        for texto, accion in chips:
            chip = QPushButton(texto); chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); chip.setFixedHeight(34)
            chip.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['text_muted']};border:2px solid {COLORS['border']};border-radius:2px;padding:0 16px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};color:{COLORS['accent']};}}")
            chip.clicked.connect(accion); chips_row.addWidget(chip)
        wl.addSpacing(12); wl.addLayout(chips_row)

        wl.addStretch(); self.messages_layout.insertWidget(0, welcome)
        self._panel_inicio = welcome             # la bienvenida lo esconde (sus chips la pisarían)

    def _chip_enviar(self, texto):
        self.input_field.setText(texto); self._send_message()

    def eventFilter(self, obj, event):
        # Glow cyan en el input cuando tiene el foco
        if obj is getattr(self, "input_field", None):
            if event.type() == QEvent.Type.FocusIn:
                apply_glow(self.input_field, COLORS["accent"], radius=16, alpha=120)
            elif event.type() == QEvent.Type.FocusOut:
                clear_glow(self.input_field)
        return super().eventFilter(obj, event)

    # ── PROVIDER SWITCH ───────────────────────────────────────────────────────

    def _switch_provider(self, provider_id):
        if provider_id == self.current_provider: return
        # Con una respuesta en marcha, primero se detiene (P2): si no, «Detener» y el
        # uso de tokens irían al proveedor nuevo y no al que está respondiendo.
        if self._worker_vivo():
            self._stop_generation()
        self.current_provider = provider_id
        for pid, tab in self.provider_tabs.items(): tab.set_active(pid==provider_id)
        meta = meta_proveedor(provider_id)
        self._style_topbar_icon(meta)
        self.topbar_title.setText(meta["label"])
        self.topbar_title.setStyleSheet(f"color:{meta['color']};background:transparent;letter-spacing:1px;")
        self.topbar_desc.setText("·  "+meta["desc"])
        self._update_send_btn_color(); self.stack.setCurrentIndex(0)

    def _sincronizar_tab_compat(self):
        """
        Pestaña del proveedor 'compat' (LM Studio, Groq, OpenAI…): aparece si hay
        URL configurada (AIManager lo registra) y se quita si ya no. Si era el
        proveedor activo y desaparece, se vuelve a Ollama u OpenRouter.
        """
        layout = getattr(self, "_sidebar_layout", None)
        if layout is None:
            return
        hay = "compat" in self.ai_manager.providers
        tab = self.provider_tabs.get("compat")
        if hay and tab is None:
            tab = ProviderTab("compat", meta_proveedor("compat"))
            tab.clicked.connect(self._switch_provider)
            otras = [t for p, t in self.provider_tabs.items() if p != "compat"]
            idx = layout.indexOf(otras[-1]) + 1 if otras else layout.count()
            layout.insertWidget(idx, tab)
            self.provider_tabs["compat"] = tab
            tab.set_active(self.current_provider == "compat")
        elif not hay and tab is not None:
            if self.current_provider == "compat":
                self._switch_provider("ollama" if datos.ollama_model() else "openrouter")
            self.provider_tabs.pop("compat", None)
            layout.removeWidget(tab); tab.deleteLater()
        tab = self.provider_tabs.get("compat")
        if tab is not None:
            modelo = datos.compat_model() or "modelo del servidor"
            tab.desc_lbl.setText(modelo if len(modelo) <= 28 else modelo[:27] + "…")
            tab.setToolTip(f"API compatible con OpenAI · {datos.compat_url()}")

    def _update_send_btn_color(self):
        meta = meta_proveedor(self.current_provider)
        c = meta["color"]
        d = meta["dark"]
        self.send_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {d},stop:1 {c});color:{COLORS['bg']};border:none;border-radius:3px;}}QPushButton:hover{{background:{c};}}QPushButton:disabled{{background:{COLORS['surface3']};color:{COLORS['text_dim']};}}")
        apply_glow(self.send_btn, c, radius=22, alpha=150)

    # ── SEND / RECEIVE / STOP ─────────────────────────────────────────────────

    def _worker_vivo(self) -> bool:
        """¿Sigue corriendo el hilo de la IA (aunque se haya pulsado «Detener»)?"""
        w = self.ai_worker
        if w is None:
            return False
        try:
            return bool(w.isRunning())
        except RuntimeError:                     # el QThread ya no existe
            return False

    def _cancelar_worker(self):
        """Pide al proveedor del worker en curso que corte (el del turno, no el de la
        pestaña elegida ahora: pudo cambiar a mitad de respuesta)."""
        prov = getattr(self.ai_worker, "provider_id", None)
        if not isinstance(prov, str):
            prov = (self._turno or {}).get("proveedor") or self.current_provider
        p = self.ai_manager.providers.get(prov) if isinstance(self.ai_manager.providers, dict) else None
        if p is not None:
            p.cancel_flag = True

    def _al_terminar_worker(self):
        """finished del AIWorker: si intentaste enviar mientras cortaba, ya puedes."""
        if self._esperando_corte:
            self._esperando_corte = False
            self._set_status("LISTO", COLORS["success"])

    def _pensando_chat(self, on: bool) -> None:
        """Cortes 9/10: el chat de esta ventana espera al modelo (BusEstado.pensar, fuente
        «chat»: no pisa a la asistente cuando comenta la pantalla)."""
        bus = getattr(getattr(self, "escritorio", None), "estado", None)
        f = getattr(bus, "pensar", None)
        if not callable(f):
            return
        try:
            from nucleo.estado_asistente import PENSANDO_CHAT
            f(PENSANDO_CHAT, bool(on))
        except Exception as e:
            log_error(f"[escritorio] no pude marcar «pensando»: {e}")

    def _fin_pensando_chat(self, worker) -> None:
        """finished de un AIWorker: deja de pensar si era el vigente (o ya no hay). El de un
        hilo viejo que acaba tarde no apaga el del envío nuevo."""
        if getattr(self, "ai_worker", None) in (None, worker):
            self._pensando_chat(False)

    def _cortar_respuesta(self):
        """
        Conversación nueva, abrir otra o cambiar de personaje con la IA escribiendo
        (P1): lo que emita ese worker ya no cuenta (generación nueva y señales
        desconectadas), se le pide que corte y se sueltan la burbuja y el indicador
        en curso, que se borran con el resto del chat. Antes el siguiente token
        tocaba un widget borrado → RuntimeError en un slot → PyQt cerraba la app.
        """
        self._gen += 1
        w = self.ai_worker
        vivo = self._worker_vivo()
        remoto = (self._turno or {}).get("remoto")
        if vivo and remoto:                      # orden de Telegram a medio responder
            self._responder_telegram(remoto, AVISO_TG_DETENIDA)
        if vivo:
            self._cancelar_worker()
            for senal in (w.token_received, w.response_ready, w.error_occurred):
                try:
                    senal.disconnect()
                except (TypeError, RuntimeError):
                    pass
            try: self.voice.cancelar()
            except Exception: pass
        if self._voz_stream is not None:
            try: self._voz_stream.cancelar()
            except Exception: pass
            self._voz_stream = None
        self._seguidor = None; self._cancelar_plan()
        indicador = self._typing_indicator
        self._typing_indicator = None; self._current_bubble = None
        if indicador is not None:
            try: indicador.stop()
            except RuntimeError: pass
        self._turno = {}
        self.stop_btn.hide(); self.send_btn.show(); self.input_field.setEnabled(True)
        if vivo:
            self._set_status("INTERRUMPIDO", COLORS["warning"])

    def _stop_generation(self):
        if self._worker_vivo():
            remoto = (self._turno or {}).get("remoto")
            if remoto:                           # orden de Telegram: que allí no se quede esperando
                self._responder_telegram(remoto, AVISO_TG_DETENIDA)
                # Una sola vez: ni cerrar_para_cambio ni limpiar el chat (con el hilo aún
                # cortando) vuelven a avisarla.
                olvidar_ordenes_avisadas(self, [remoto])
            self._cancelar_worker()

            # El hilo tarda un momento en cortar y luego emite response_ready.
            # Sin esta bandera, _on_response pisaba el estado con "LISTO" y
            # parecía que la interrupción no había funcionado.
            self._cancelado = True
            self._seguidor = None; self._cancelar_plan()
            try: self.voice.cancelar()
            except Exception: pass
            if self._voz_stream is not None:
                self._voz_stream.cancelar(); self._voz_stream = None
            self._set_status("INTERRUMPIDO", COLORS["warning"])
            self.lune_face.set_state("normal")

            self.stop_btn.hide(); self.send_btn.show()
            self.input_field.setEnabled(True); self.input_field.setFocus()

    def _burbuja_bot(self, texto):
        """Respuesta que no viene de la IA (memoria, banco, herramientas)."""
        b = MessageBubble(texto, is_user=False, provider_id=self.current_provider,
                          markdown=self.config.feature("markdown", True))
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, b)
        return b

    # ── Bienvenida (11): las tres preguntas cuando aún no te conozco ──────────
    def _nombre_bot(self) -> str:
        """El nombre del personaje activo para los textos de la bienvenida."""
        return str(getattr(getattr(self, "banco", None), "nombre", "") or "Lune")

    def _marcas_bienvenida(self) -> dict:
        """{"ventana": clave, "burbuja": clave}: qué pregunta se ve en cada sitio."""
        m = getattr(self, "_bienvenida_marcas", None)
        if not isinstance(m, dict):
            m = self._bienvenida_marcas = {"ventana": None, "burbuja": None}
        return m

    def _ventana_se_ve(self) -> bool:
        """¿La ventana está a la vista (visible y sin minimizar)?"""
        try:
            return bool(self.isVisible() and not self.isMinimized())
        except Exception:
            return False

    def _ocultar_panel_inicio(self):
        """Mientras Lune hace sus preguntas, fuera el panel de inicio («Dime qué necesitas»)
        y sus chips: SALUDAR mandaría «Hola Lune» como respuesta a tu nombre."""
        panel = getattr(self, "_panel_inicio", None)
        if panel is None:
            return
        try:
            panel.hide()
        except Exception:                            # ya borrado (deleteLater)
            pass

    def _pintar_pregunta_bienvenida(self, b, pregunta, mensajes) -> bool:
        """La pregunta en curso en el chat de la ventana (salvo que la conversación ya termine
        en ella): se apunta como vista aquí y, si no está en chats/, como pendiente de
        guardar. True si la pintó."""
        self._bienvenida_sin_guardar = None
        if not pregunta:
            return False
        try:
            nucleo, clave = b.nucleo_actual(), b.clave_paso()
        except Exception:
            return False
        self._marcas_bienvenida()["ventana"] = clave
        if ya_preguntada(mensajes, nucleo):
            return False
        self._burbuja_bot(pregunta)
        self._bienvenida_sin_guardar = pregunta
        self._ocultar_panel_inicio()
        return True

    def _arrancar_bienvenida(self):
        """Temporizador de arranque: si toca, la pregunta en curso como burbuja de Lune (sin
        modelo). No se repite si la conversación restaurada ya termina en ella. Se dice en
        voz alta solo con la ventana a la vista (arrancar con Windows en la bandeja no
        habla) y una vez por proceso (un cambio de interfaz en caliente no la repite). No va
        a chats/ hasta el próximo turno. Si solo usas el chat de la asistente en escritorio,
        tu primer mensaje ahí recibe la pregunta (no la habías visto)."""
        if self._cerrandose():
            return
        b = getattr(self, "_bienvenida", None)
        if not isinstance(b, Bienvenida):
            return
        try:
            pregunta = b.arrancar()
        except Exception as e:
            log_error(f"[bienvenida] {e}")
            return
        try:
            previos = self.chats.mensajes_actuales()
        except Exception:
            previos = []
        if not self._pintar_pregunta_bienvenida(b, pregunta, previos):
            return
        self.lune_face.set_state("happy", auto_revert_ms=4000)
        if self._ventana_se_ve() and b.por_decir():
            self.voice.speak(pregunta)
        self._scroll_bottom()

    def _repintar_pregunta_bienvenida(self, mensajes=None) -> bool:
        """Chat vaciado (conversación nueva, otro personaje) o conversación abierta del
        historial con la bienvenida a medias: la pregunta vuelve a salir, porque lo siguiente
        que escribas sigue siendo la respuesta. True si la pintó."""
        b = getattr(self, "_bienvenida", None)
        if not isinstance(b, Bienvenida):
            return False
        try:
            pregunta = b.pregunta_actual()
        except Exception:
            return False
        return self._pintar_pregunta_bienvenida(b, pregunta, mensajes or [])

    def _vista_bienvenida(self, desde_burbuja):
        """Qué pregunta viste donde escribiste: la de la ventana o, desde la burbuja de la
        asistente en escritorio, la que enseñó la burbuja (y la de la ventana si se ve)."""
        m = self._marcas_bienvenida()
        if not desde_burbuja:
            return m.get("ventana")
        vistas = [m.get("burbuja")]
        if self._ventana_se_ve():
            vistas.append(m.get("ventana"))
        return vistas

    def _guardar_pregunta_bienvenida(self):
        """La pregunta que se ve en el chat y aún no está en chats/, antes del turno que se va
        a guardar (sea tu respuesta, /memoria o una orden de Telegram)."""
        pendiente = getattr(self, "_bienvenida_sin_guardar", None)
        if isinstance(pendiente, str) and pendiente:
            self._bienvenida_sin_guardar = None
            self._guardar_turno("assistant", pendiente, bienvenida=True)

    def _send_message(self, *_senal, texto=None, desde_asistente=False, remoto=""):
        """
        Envía lo escrito en la barra de la ventana o, con `texto`, lo que llega
        de fuera (el chat de la asistente): mismo flujo, mismo historial. Lo de
        fuera no se lleva los adjuntos pendientes ni borra lo que estés
        escribiendo. Con `desde_asistente`, la respuesta sale también en su burbuja.

        Con `remoto` (id de una orden de Telegram, ver _orden_remota): burbuja
        «📱 Telegram: …» guardada como no confiable; sin memoria, banco de
        respuestas ni notas; primero el comando directo («abre youtube», sin IA) y
        si no, turno de IA con origen 'remoto' y el motor local (en modo terminal
        el host no aplicaría la política de esta orden). Todo pide permiso en el PC
        y la respuesta y los ✓/✕ vuelven a Telegram.
        """
        de_fuera = texto is not None
        text = (texto if de_fuera else self.input_field.text()).strip()
        adjuntos_envio = [] if de_fuera else list(self._adjuntos)
        # Adjuntar un archivo sin escribir nada es una petición implícita
        if not text and adjuntos_envio:
            text = "Échale un ojo a esto, por favor."
        if not text:
            return
        # Tras «Detener» (o una conversación nueva) el hilo viejo tarda un momento en
        # cortar. Hasta entonces no se envía: el proveedor comparte cancel_flag (bajarlo
        # le quitaría el corte al viejo) y soltar un QThread vivo tumba el proceso.
        # Lo escrito se queda en la barra.
        if self._worker_vivo():
            self._esperando_corte = True
            self._set_status("ESPERA · CORTANDO LO ANTERIOR", COLORS["warning"])
            return
        # El punto de estado del proveedor, fresco al enviar: el sondeo periódico solo corre
        # con la ventana a la vista (los dobles de test sin él no sondean).
        sondear = getattr(self, "_sondear_si_viejo", None)
        if callable(sondear):
            sondear()
        self._turno = {"origen": ORIGEN_REMOTO if remoto else ORIGEN_USUARIO, "ctx": None,
                       "asistente": bool(desde_asistente), "proveedor": self.current_provider}
        if remoto:
            self._turno["remoto"] = remoto
        self.stack.setCurrentIndex(0)
        # Lo pendiente de la respuesta anterior no debe pisar esta: expresiones
        # programadas, marcadores del stream viejo y voz por tramos.
        self._cancelar_plan(); self._expresado_en_stream = False; self._seguidor = None
        try: self.voice.cancelar()
        except Exception: pass

        visible = PREFIJO_TELEGRAM + text if remoto else text
        bubble = MessageBubble(visible, is_user=True, provider_id=self.current_provider,
                               markdown=False, adjuntos=adjuntos_envio)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        if not de_fuera:
            self.input_field.clear()
            self._adjuntos = []
            self._refrescar_adjuntos()
        # Bienvenida (11, nucleo/bienvenida.py): mientras Lune te hace sus tres preguntas, lo
        # que escribes (aquí o en el chat de la burbuja, si ahí viste la pregunta) es la
        # respuesta: se guarda al instante, sin IA ni herramientas (va antes que el comando
        # directo: «abre…» no es un nombre). Si no la habías visto, Lune te la enseña. Ni los
        # adjuntos ni las órdenes de Telegram pasan por aquí. isinstance: una ventana de
        # mentira (MagicMock) nunca tiene bienvenida.
        bienv = getattr(self, "_bienvenida", None)
        turno_b = None
        if not remoto and not adjuntos_envio and isinstance(bienv, Bienvenida):
            try:
                turno_b = bienv.turno(text, vista=self._vista_bienvenida(desde_asistente))
            except Exception as e:
                log_error(f"[bienvenida] {e}")
        if isinstance(bienv, Bienvenida):
            self._guardar_pregunta_bienvenida()          # la pregunta que se veía, antes que esto
        if remoto:
            self._guardar_turno("user", visible, adjuntos=adjuntos_envio, no_confiable=True)
        elif turno_b is not None:
            self._guardar_turno("user", text, adjuntos=adjuntos_envio, bienvenida=True)
        else:
            self._guardar_turno("user", text, adjuntos=adjuntos_envio)
        if turno_b is not None:
            respuesta_b = turno_b.respuesta
            self._burbuja_bot(respuesta_b)
            self._guardar_turno("assistant", respuesta_b, bienvenida=True)
            self._eco_asistente(respuesta_b, fin=True)
            try:
                clave = bienv.clave_paso()
                marcas = self._marcas_bienvenida()
                marcas["ventana"] = clave                 # la respuesta sale en la ventana
                if desde_asistente:
                    marcas["burbuja"] = clave             # …y en la burbuja
                bienv.marcar_dicha()                      # la siguiente ya se dice aquí
            except Exception as e:
                log_error(f"[bienvenida] {e}")
            self.lune_face.set_state(turno_b.cara or "happy", auto_revert_ms=4000)
            self.voice.speak(respuesta_b); self._scroll_bottom(); return

        if not adjuntos_envio:
            # Lo pidió la persona con sus palabras («abre youtube», «avísame en 10
            # minutos»): sin IA, pero por el Ejecutor como cualquier acción (política,
            # presupuesto, aprobación y auditoría). El ✓/✕ llega por _on_resultado_turno
            # (ya o tras aprobar). Desde Telegram, con origen 'remoto': pide permiso aquí
            # aunque sea directa. Antes que la memoria (cortes 5/6): «recuérdame que a
            # las 5 tengo cita» es una alarma; sin hora ni duración sigue siendo un recuerdo.
            try:
                llamadas = self.tools.detectar_llamadas(text)
            except Exception as e:
                log_error(f"[acciones] detectar_llamadas: {e}")
                llamadas = []
            if llamadas:
                ctx = ctx_acciones(self.ai_manager, self.current_provider, self._modo_acciones())
                if remoto:
                    ctx["origen"] = ORIGEN_REMOTO
                self._turno["ctx"] = ctx
                self._ejecutar_acciones(llamadas, ORIGEN_REMOTO if remoto else ORIGEN_USUARIO, ctx,
                                        asistente=bool(desde_asistente), directo=True, remoto=remoto)
                self._scroll_bottom(); return

        # Con archivos adjuntos siempre va a la IA: ni la memoria ni el banco
        # de respuestas saben qué hacer con un PDF. Una orden de Telegram tampoco
        # pasa por ellos: comando directo o IA.
        if not adjuntos_envio and not remoto:
            respuesta_memoria = self.memoria.procesar_mensaje_usuario(text)
            if respuesta_memoria:
                self._burbuja_bot(respuesta_memoria)
                self._guardar_turno("assistant", respuesta_memoria)
                self._eco_asistente(respuesta_memoria, fin=True)
                self.lune_face.set_state("happy", auto_revert_ms=4000); self._scroll_bottom(); return

            # Banco de respuestas instantáneas (saludos, gracias, hora…) — sin IA
            if self.config.feature("respuestas_predeterminadas", True):
                self.banco.set_nombre_usuario(self.memoria.get_nombre_usuario())
                rta_rapida = self.banco.responder(text)
                if rta_rapida:
                    self._burbuja_bot(rta_rapida)
                    self._guardar_turno("assistant", rta_rapida)
                    self._eco_asistente(rta_rapida, fin=True)
                    self.lune_face.set_state("happy", auto_revert_ms=4000)
                    self.voice.speak(rta_rapida); self._scroll_bottom(); return

        # La asistente contesta solo con la nube (10.9): sin clave de OpenRouter lo dice y
        # no cae al modelo local. Lo de arriba (órdenes, memoria, respuestas
        # instantáneas) no necesita modelo y funciona igual. La ventana, con el suyo.
        proveedor = self.current_provider
        if desde_asistente and not remoto:
            if not str(datos.openrouter_key() or "").strip():
                self._burbuja_bot(AVISO_ASISTENTE_SIN_NUBE)
                self._guardar_turno("assistant", AVISO_ASISTENTE_SIN_NUBE)
                self._eco_asistente(AVISO_ASISTENTE_SIN_NUBE, fin=True)
                self._scroll_bottom(); return
            proveedor = "openrouter"

        self.input_field.setEnabled(False)
        self.send_btn.hide(); self.stop_btn.show()

        if proveedor in self.ai_manager.providers:
            self.ai_manager.providers[proveedor].cancel_flag = False

        self._set_status("PROCESANDO", COLORS["warning"]); self.lune_face.set_state("thinking")
        self._cancelar_plan(); self._expresado_en_stream = False
        self._seguidor = expresiones.SeguidorActs()
        if self._overlay is not None and self._overlay.isVisible():
            self._overlay.set_estado("thinking")

        self._typing_indicator = TypingIndicator(proveedor)

        # Voz por frases mientras escribe (opcional). Si falla, se usa la de siempre.
        self._voz_stream = None
        if self.config.feature("voz_streaming", False) and self.voice.available and self.voice._enabled:
            vs = VozStreaming(self.voice)
            if vs.iniciar():
                self._voz_stream = vs
        self.messages_layout.insertWidget(self.messages_layout.count()-1, self._typing_indicator)
        self._scroll_bottom()

        self._cancelado = False
        contexto_memoria = self.memoria.obtener_contexto_para_prompt()
        # El texto de los documentos va en el system prompt; las imágenes van
        # por el canal multimodal del proveedor.
        contexto_archivos = adj.bloque_para_prompt(adjuntos_envio)
        # Notas relevantes (RAG): se añaden como [Contexto] envuelto/no confiable.
        contexto_notas = ""
        if self.notas.activo and not remoto:
            frags = self.notas.contexto_para(text)
            if frags:
                from lune_core.prompt import bloque_contexto
                contexto_notas = "\n\n" + bloque_contexto(frags)
        # En modo terminal (conectado al host), el chat va por el host: la app no
        # carga el modelo. Si el host no está, se usa el motor local de siempre.
        # Una orden de Telegram, siempre con el local (sus acciones las aprueba este PC).
        if (not remoto and self._modo_red == "terminal" and self._chat_remoto is not None
                and self._chat_remoto.conectado):
            self._motor_chat = self._chat_remoto
        else:
            self._motor_chat = self.ai_manager
        # Origen del turno (crítica d): con adjuntos o notas el prompt lleva texto
        # de terceros → solo herramientas de LECTURA en esta respuesta. Desde
        # Telegram, 'remoto': todas, y todas con aprobación en el PC.
        if remoto:
            origen = ORIGEN_REMOTO
        else:
            origen = ORIGEN_NO_CONFIABLE if (adjuntos_envio or contexto_notas) else ORIGEN_USUARIO
        # Con la asistente fuera el modo es "asistente"/"vrm": también las suyas (dormir…).
        modo = self._modo_acciones()
        ctx = ctx_acciones(self.ai_manager, proveedor, modo)
        if remoto:
            ctx["origen"] = ORIGEN_REMOTO           # todas marcadas «(pide permiso)» en el prompt
        self._turno = {"origen": origen, "ctx": ctx, "asistente": bool(desde_asistente),
                       "proveedor": proveedor}
        if remoto:
            self._turno["remoto"] = remoto
        # Generación de este envío: las señales llevan la suya y, si ya no es la
        # vigente (conversación nueva, otro personaje…), se ignoran (G1/P1).
        self._gen += 1
        gen = self._gen
        self.ai_worker = AIWorker(
            self._motor_chat, PREFIJO_IA + text if remoto else text, proveedor,
            extra_context=contexto_memoria + contexto_archivos + contexto_notas,
            permitir_acciones=self.config.feature("acciones_ia", True),
            imagenes=adj.imagenes_base64(adjuntos_envio),
            emociones=self.config.feature("emociones", True),
            origen=origen, ejecutor=self.acciones.ejecutor, modo=modo, ctx=ctx,
        )
        if self.config.feature("streaming_tokens", True):
            self.ai_worker.token_received.connect(lambda t, g=gen: self._on_token(t, g))
        self.ai_worker.response_ready.connect(lambda r, g=gen: self._on_response(r, g))
        self.ai_worker.error_occurred.connect(lambda e, g=gen: self._on_error(e, g))
        self.ai_worker.finished.connect(self._al_terminar_worker)
        # Cortes 9/10: `pensando` en el bus mientras el hilo de la IA vive (el bot de
        # Minecraft pausa su modelo; Discord, «Pensando…»). Lo apaga el finished de ESTE hilo.
        w = self.ai_worker
        self.ai_worker.finished.connect(lambda w=w: self._fin_pensando_chat(w))
        self._pensando_chat(True)
        self.ai_worker.start()

    # `gen` (None = sin generación): la de la señal; si no es la vigente, el envío ya
    # se cortó (conversación nueva, otro personaje…) y lo que traiga no cuenta.
    def _on_token(self, partial, gen=None):
        if gen is not None and gen != self._gen:
            return
        # En streaming se pinta texto plano: reconstruir los widgets de markdown
        # 16 veces por segundo sería carísimo. Al terminar se formatea de golpe.
        # Los marcadores <|ACT|>/<|DELAY|> se ocultan mientras se escribe.
        visible = marcadores.limpiar_para_mostrar(partial)
        if self._voz_stream is not None:
            self._voz_stream.escribir(visible)
        self._eco_asistente(visible)          # si el turno salió del chat de la asistente
        # La cara cambia según llegan los <|ACT|> (salvo que la voz vaya a leer la
        # respuesta al final: entonces cambia al ritmo de la voz).
        if self._seguidor is not None and not self._voz_lee_al_final():
            for act in self._seguidor.nuevos(partial):
                self._expresado_en_stream = True
                self._expresar(act.get("emotion", "neutral"))
        if self._typing_indicator and self._current_bubble is None:
            self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
            self._current_bubble = MessageBubble(
                visible + " ▋", is_user=False,
                provider_id=(self._turno or {}).get("proveedor") or self.current_provider,
                markdown=self.config.feature("markdown", True))
            self.messages_layout.insertWidget(self.messages_layout.count()-1, self._current_bubble)
            if not self._expresado_en_stream:
                self.lune_face.set_state("typing")
        elif self._current_bubble:
            self._current_bubble.update_text(visible + " ▋", streaming=True)
        self._scroll_bottom()

    def _on_response(self, response, gen=None):
        if gen is not None and gen != self._gen:
            return          # respuesta de un envío ya cortado: ni se pinta ni ejecuta sus <|CALL|>
        # Acciones del modelo: el Ejecutor saca las <|CALL …|> del texto (y borra
        # el formato antiguo sin ejecutarlo). Se ejecutan más abajo, al terminar.
        turno = self._turno or {}
        origen = turno.get("origen", ORIGEN_NO_CONFIABLE)
        ctx = turno.get("ctx")
        proveedor = turno.get("proveedor") or self.current_provider   # el del turno (P2)
        if self._acciones_locales():
            respuesta_limpia, llamadas = self.acciones.procesar(response, origen, ctx)
        else:
            respuesta_limpia, llamadas = limpiar_texto(response or ""), []

        if self._typing_indicator: self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
        if self._current_bubble:
            # streaming=False → aquí sí se renderiza el markdown
            self._current_bubble.update_text(respuesta_limpia)
            burbuja = self._current_bubble
        else:
            # Sin streaming: creamos la burbuja con la respuesta completa
            burbuja = MessageBubble(respuesta_limpia, is_user=False, provider_id=proveedor,
                                    markdown=self.config.feature("markdown", True))
            self.messages_layout.insertWidget(self.messages_layout.count()-1, burbuja)
        self._current_bubble = None

        uso = (self._motor_chat or self.ai_manager).uso(proveedor)
        if uso and self.config.feature("contador_tokens", True):
            burbuja.set_pie(self._texto_uso(uso))
        # Turno con texto de terceros (o una orden de Telegram): marcado al guardarlo.
        self._guardar_turno("assistant", respuesta_limpia, uso=uso,
                            no_confiable=(origen != ORIGEN_USUARIO))

        self.stop_btn.hide(); self.send_btn.show()
        if not getattr(self, "_cancelado", False):
            self._set_status("LISTO", COLORS["success"])
        self.input_field.setEnabled(True); self.input_field.setFocus()

        # Una orden de Telegram: la respuesta limpia vuelve a su chat (tras «Detener»
        # ya se avisó allí de que se cortó). Si pide acciones, dice que esperan tu
        # permiso en el PC: «He programado…» aún no es verdad.
        remoto = turno.get("remoto") or ""
        if remoto and not getattr(self, "_cancelado", False):
            self._responder_telegram(remoto, con_aviso_pendiente(self._texto_telegram(respuesta_limpia),
                                                                 llamadas))

        # Las acciones que pide la IA solo se ejecutan si el usuario las tiene
        # permitidas en Configuración → Rendimiento, y nunca tras «Detener». Lo
        # que pide permiso pregunta (QMessageBox o junto a la asistente) y su
        # resultado llega después por _on_resultado_accion.
        if llamadas and not getattr(self, "_cancelado", False):
            self._ejecutar_acciones(llamadas, origen, ctx, asistente=bool(turno.get("asistente")),
                                    remoto=remoto)

        self.memoria.procesar_respuesta_lune(respuesta_limpia)

        # Emoción: el plan de expresiones del modelo (hasta tres tramos); sin
        # marcadores, la heurística léxica de siempre. El texto hablable no los
        # incluye. La última expresión SE QUEDA (no vuelve sola al idle).
        plan = expresiones.planificar(respuesta_limpia)
        hablable = expresiones.hablable(plan)
        con_acts = bool(expresiones.emociones(plan))
        if con_acts and hablable.strip():
            burbuja.update_text(hablable)   # la burbuja final sin marcadores
        self._eco_asistente(hablable if hablable.strip() else respuesta_limpia, fin=True)
        hablo = False
        cancelado = getattr(self, "_cancelado", False)
        if self._voz_stream is not None:
            self._voz_stream.terminar()   # emite lo que quede y cierra
            self._voz_stream = None
        elif cancelado:
            pass                          # interrumpida: ni habla ni programa expresiones
        elif con_acts:
            # Por tramos: la cara cambia cuando empieza a sonar cada uno y, al
            # acabar, se queda con la última (aunque su tramo no tenga texto).
            hablo = self.voice.speak_segmentos(
                expresiones.segmentos_voz(plan),
                al_segmento=lambda _i, e: self._emitir_si_vivo("_acto_voz", e),
                al_terminar=lambda f=expresiones.final(plan): self._emitir_si_vivo("_acto_voz", f))
        else:
            self.voice.speak(hablable)
        if not hablo and not cancelado:
            if con_acts and not self._expresado_en_stream:
                self._programar_plan(plan)             # de golpe: al ritmo de lectura
            elif con_acts:
                self._expresar(expresiones.final(plan))
            else:
                self._expresar_estado(detect_emotion(respuesta_limpia))
        self._scroll_bottom()

    # ── Expresiones (hasta tres por respuesta; la última se queda) ──────────────
    def _voz_lee_al_final(self) -> bool:
        return bool(getattr(self.voice, "available", False) and getattr(self.voice, "_enabled", False)
                    and self._voz_stream is None)

    # Estados de PROCESO de los sprites (escribiendo, leyendo, error…): no son una
    # emoción y sí vuelven solos al idle; las emociones (feliz, triste…) se quedan.
    _ESTADOS_PROCESO = ("typing", "reading", "thinking", "error", "confused")

    def _expresar(self, emocion: str):
        """Emoción canónica del modelo → cara del escenario y asistente (se queda)."""
        if not emocion:
            return
        estado = lune_face.estado_desde_emocion(emocion)
        self.lune_face.set_state(estado, auto_revert_ms=6000 if estado in self._ESTADOS_PROCESO else 0)
        ov = self._asistente_viva()
        if ov is not None and ov.isVisible():
            ov.set_emocion(emocion, 0)     # la asistente sí tiene clip/gesto para cada emoción

    def _expresar_estado(self, estado: str):
        ms = 6000 if estado in self._ESTADOS_PROCESO else 0
        self.lune_face.set_state(estado, auto_revert_ms=ms)
        ov = self._asistente_viva()
        if ov is not None and ov.isVisible():
            ov.set_estado(estado, ms)

    def _cancelar_plan(self):
        for t in getattr(self, "_timers_plan", []):
            try: t.stop()
            except Exception: pass
        self._timers_plan = []

    def _programar_plan(self, plan):
        """Sin voz y sin streaming: las expresiones al ritmo de lectura."""
        self._cancelar_plan()
        horario = expresiones.horario(plan)
        if not horario:
            return
        self._expresar(horario[0][1])
        for t_s, emocion, _ in horario[1:]:
            tm = QTimer(self); tm.setSingleShot(True)
            tm.timeout.connect(lambda e=emocion: self._expresar(e))
            tm.start(int(t_s * 1000)); self._timers_plan.append(tm)

    def _on_error(self, error, gen=None):
        if gen is not None and gen != self._gen:
            return
        if self._typing_indicator: self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
        if self._current_bubble: self._current_bubble.update_text(f"✕ {error}")
        else:
            err_bubble = MessageBubble(f"✕ {error}", is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, err_bubble)
        self._current_bubble = None
        self.stop_btn.hide(); self.send_btn.show()
        self._set_status("ERROR", COLORS["error"]); self.input_field.setEnabled(True); self.input_field.setFocus()
        self.lune_face.set_state("error", auto_revert_ms=8000)
        self._eco_asistente(f"✕ {error}", fin=True)
        remoto = (self._turno or {}).get("remoto")
        if remoto:                               # p. ej. Ollama apagado: que se entienda allí
            self._responder_telegram(remoto, f"✕ No pude responder: {error}")
        self._scroll_bottom()

    # ── ACCIONES DEL MODELO, VOZ Y CHAT DE LA ASISTENTE ───────────────────────────
    def _acciones_locales(self) -> bool:
        """¿Procesa esta app las <|CALL|>? No si están apagadas (acciones_ia) ni si
        respondió el host (modo terminal): allí ya se ejecutaron y el texto llega limpio."""
        if not self.config.feature("acciones_ia", True):
            return False
        motor = self._motor_chat
        return motor is None or motor is self.ai_manager

    def _on_resultado_accion(self, res) -> str:
        """Resultado de una acción del modelo (siempre en el hilo de Qt): ✓/✕ en el chat."""
        texto = f"{'✓' if res.ok else '✕'} {res.mensaje}"
        self._burbuja_bot(texto)
        self._scroll_bottom()
        return texto

    def _ejecutar_acciones(self, llamadas, origen, ctx, *, asistente: bool = False,
                           directo: bool = False, remoto: str = "") -> None:
        """
        Corre las acciones de un turno. Las del chat de la asistente, las que pidió la
        persona con sus palabras y las de una orden de Telegram (`remoto` = su id)
        llevan su destino con el resultado (llegue en línea, tras aprobar o al
        caducar): el ✓/✕ sale también en la burbuja de la asistente aunque entre
        tanto hayas escrito en la ventana, el de lo pedido se guarda en la
        conversación y el de una orden vuelve a Telegram. El resto, por
        AccionesQt.resultado como siempre.
        """
        if not llamadas:
            return
        if not (asistente or directo or remoto):
            self.acciones.ejecutar(llamadas, origen, ctx)
            return
        info = {"asistente": bool(asistente), "directo": bool(directo)}
        if remoto:
            info["remoto"] = str(remoto)
            origen = ORIGEN_REMOTO                   # todo con aprobación en el PC
        self.acciones.ejecutor.ejecutar_llamadas(
            llamadas, origen, ctx, lambda res, i=info: self._resultado_turno.emit(res, i))

    def _on_resultado_turno(self, res, info):
        """Slot de _resultado_turno (hilo de Qt): el ✓/✕ en el chat y donde toque."""
        info = info if isinstance(info, dict) else {}
        texto = self._on_resultado_accion(res)
        remoto = info.get("remoto")
        if info.get("directo"):
            if remoto:
                self._guardar_turno("assistant", texto, no_confiable=True)
            else:
                self._guardar_turno("assistant", texto)
            self.lune_face.set_state("happy" if res.ok else "error", auto_revert_ms=5000)
        if info.get("asistente"):
            self._burbuja_asistente(texto, fin=True)
        if remoto:
            self._responder_telegram(remoto, texto)

    # ── ÓRDENES DESDE TELEGRAM (/pc) ───────────────────────────────────────────
    def _responder_telegram(self, oid, texto) -> bool:
        """`texto` al chat de Telegram de la orden `oid` (por el stdin del bot)."""
        fn = getattr(self._tg_worker, "responder_orden", None)
        if not oid or not callable(fn):
            return False
        try:
            return bool(fn(str(oid), str(texto or "")))
        except Exception as e:
            log_error(f"[telegram] no pude responder la orden: {e}")
            return False

    @staticmethod
    def _texto_telegram(respuesta_limpia: str) -> str:
        """Lo que se ve de la respuesta (sin <|ACT|> ni marcas) para mandarlo a Telegram."""
        try:
            texto = expresiones.hablable(expresiones.planificar(respuesta_limpia)).strip()
        except Exception:
            texto = ""
        if not texto:
            texto = marcadores.limpiar_para_mostrar(respuesta_limpia or "").strip()
        return texto or SIN_TEXTO

    def _avisar_ordenes_pendientes(self, ya_avisada: str = "") -> list:
        """Conversación nueva (limpiar chat, abrir otra, otro personaje) con una orden
        de Telegram esperando tu permiso: la pregunta se cierra sin hacer nada, así que
        a Telegram le llega «Se detuvo…» (si no, se quedaría esperando). `ya_avisada`:
        la que _cortar_respuesta ya contestó. Devuelve los ids avisados."""
        try:
            pend = self.acciones.pendientes()
        except Exception:
            pend = []
        ids = [i for i in ordenes_cortadas(None, False, pend, self._ultima_orden_tg)
               if i and i != str(ya_avisada or "")]
        for oid in ids:
            self._responder_telegram(oid, AVISO_TG_DETENIDA)
        return ids

    def _remota_en_curso(self) -> bool:
        """¿Lune está respondiendo o espera que apruebes una orden de Telegram anterior?"""
        if self._worker_vivo():
            return True
        try:
            return any(p.get("remoto") for p in self.acciones.pendientes())
        except Exception:
            return False

    def _orden_remota(self, oid, texto):
        """
        Orden de Telegram (/pc, TelegramBotWorker.orden_recibida, hilo de Qt). Con
        la función apagada (o sin tu ID) se contesta que está desactivada; si Lune
        está respondiendo, que está ocupada. Si no, entra por _send_message con
        `remoto`: burbuja «📱 Telegram: …», comando directo sin IA o turno de IA
        con origen 'remoto'. TODO se aprueba en el PC (QMessageBox con la ventana
        delante o junto a la asistente), nunca desde Telegram.
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
        # Si la ventana se cierra con esta orden esperando tu permiso (cambio de modo),
        # se le contesta «Se detuvo…» (cerrar_para_cambio).
        self._ultima_orden_tg = oid
        self._send_message(texto=texto, remoto=oid)
        self._scroll_bottom()

    def _ventana_a_la_vista(self) -> bool:
        """¿Se verá un QMessageBox sobre la ventana? Solo si está visible, sin
        minimizar y activa, y el turno no salió del chat de la asistente. Si no, la
        pregunta va junto a la asistente (siempre encima): nunca caduca sin verse."""
        try:
            return bool(self.isVisible() and not self.isMinimized() and self.isActiveWindow()
                        and not (self._turno or {}).get("asistente"))
        except Exception:
            return False

    def _ancla_asistente(self):
        """Rectángulo global de la asistente visible (para la pregunta «¿Lo hago?»), o None."""
        ov = self._asistente_viva()
        if ov is None or not ov.isVisible():
            return None
        try:
            return ov.frameGeometry()
        except Exception:
            return None

    # ── Avisos de la voz (hilo de audio) → señales ────────────────────────────
    def _emitir_si_vivo(self, senal: str, *args) -> None:
        """Emite `senal` solo si la ventana sigue viva. El hilo de voz puede llamar después
        de borrarla (cambio de interfaz, salir): emitir una señal ligada de un QObject
        borrado da AttributeError o una violación de acceso; aquí se resuelve en cada
        llamada (como el puente web, ui/web_bridge.py)."""
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
        """Desengancha los avisos de la voz si siguen siendo los de esta ventana."""
        soltar_avisos_voz(self)

    def _on_voz_error(self, mensaje: str):
        """voice.on_error (llega del hilo de audio por señal): estado + aviso."""
        log_error(f"[voz] {mensaje}")
        self._set_status("VOZ ✕", COLORS["warning"])
        self.status_label.setToolTip(mensaje)
        if self.tray is not None and not self.isVisible():
            self.tray.showMessage("Lune CD · voz", mensaje, QSystemTrayIcon.MessageIcon.Warning, 5000)

    def _resumen_tareas(self):
        """Las tareas pendientes para «qué tareas tengo» (nucleo.tareas, sobre la MISMA
        memoria). None si no se puede: la pregunta va a la IA."""
        try:
            from nucleo.tareas import resumen_de
            return resumen_de(self.memoria)
        except Exception:
            return None

    def _chat_desde_asistente(self, texto: str) -> bool:
        """
        on_chat de la asistente (EntradaChat bajo ella): lo que escribes ahí va por
        el flujo normal de la ventana (mismo historial y memoria) y la respuesta
        se ve también en su burbuja. False si aún está respondiendo a otra cosa.
        """
        texto = str(texto or "").strip()
        if not texto:
            return False
        if self._worker_vivo():                  # también mientras corta tras «Detener»
            ov = self._asistente_viva()
            if ov is not None and hasattr(ov, "burbuja_texto"):
                try:
                    ov.burbuja_texto("Espera, aún estoy con lo anterior…")
                    ov.burbuja_fin(4000)
                except Exception:
                    pass
            return False
        self._send_message(texto=texto, desde_asistente=True)
        return True

    def _eco_asistente(self, texto: str, fin: bool = False):
        """Si el turno salió del chat de la asistente: el texto en su burbuja
        (burbuja_texto) y, al acabar, burbuja_fin con el tiempo de lectura."""
        if not (self._turno or {}).get("asistente"):
            return
        self._burbuja_asistente(texto, fin)

    def _burbuja_asistente(self, texto: str, fin: bool = False):
        """El texto en la burbuja de la asistente, solo si está a la vista: oculta, cada
        trozo del streaming la hacía reaparecer sola junto a una asistente invisible."""
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
                ov.burbuja_texto(texto)
            if fin and hasattr(ov, "burbuja_fin"):
                ov.burbuja_fin(max(8000, len(texto) * 1000 // 15))
        except Exception as e:
            log_error(f"[asistente] burbuja: {e}")

    # ── HELPERS ───────────────────────────────────────────────────────────────

    @staticmethod
    def _texto_uso(uso: dict) -> str:
        """Pie de la burbuja: hora, tokens y costo (o velocidad, si es local)."""
        hora = datetime.now().strftime("%H:%M")
        partes = [hora, f"{uso.get('entrada', 0)}→{uso.get('salida', 0)} tokens"]
        if uso.get("local"):
            if uso.get("tokens_por_segundo"):
                partes.append(f"{uso['tokens_por_segundo']} tok/s")
            partes.append("local · gratis")
        else:
            costo = uso.get("costo", 0) or 0
            partes.append(f"${costo:.5f}" if costo else "sin costo reportado")
        return "  ·  ".join(partes)

    def _scroll_bottom(self):
        # Método de la ventana (no una lambda): si la ventana se borra antes de los
        # 60 ms (cambio de interfaz), Qt descarta el aviso en vez de tocar un widget muerto.
        QTimer.singleShot(60, self._al_fondo_del_chat)

    def _al_fondo_del_chat(self):
        barra = self.scroll.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _set_status(self, text, color):
        self.status_label.setText(text); self.status_dot.setStyleSheet(f"color:{color};background:transparent;")

    def _toggle_voice(self):
        self.voice.toggle()
        self._pintar_voz()

    def _pintar_voz(self):
        """El tile de la voz según esté encendida (también si la encendió otro: el
        cambio de modo trae la de la ventana anterior)."""
        btn = getattr(self, "_voice_btn", None)
        if btn is None:
            return
        enabled = bool(getattr(self.voice, "_enabled", False))
        btn.setText(f" VOZ: {'ON' if enabled else 'OFF'}")
        col = COLORS["accent"] if enabled else COLORS["text_muted"]
        btn.setIcon(icon("volume" if enabled else "volume_off", col, 18))

    def _toggle_keys_panel(self):
        self.stack.setCurrentIndex(1 if self.stack.currentIndex()!=1 else 0)

    def _toggle_optimizer(self):
        self.stack.setCurrentIndex(2 if self.stack.currentIndex()!=2 else 0)

    def _toggle_personajes(self):
        if self.stack.currentIndex() != 3:
            self.personajes_panel.refrescar()
            self.stack.setCurrentIndex(3)
        else:
            self.stack.setCurrentIndex(0)

    def _toggle_overlay(self):
        """Muestra u oculta la asistente flotante (avatar sobre el escritorio).
        Con avatar.render = "vrm" es el avatar 3D (ui/companion.py); si no, los
        sprites ligeros. Mientras está fuera, el escenario lateral no la dibuja."""
        if self._overlay is None or getattr(self._overlay, "cerrado", False):
            self._overlay = self._crear_asistente()
        if self._overlay.isVisible():
            self._overlay.hide()
        else:
            self._overlay.show(); self._overlay.raise_()

    def _crear_asistente(self):
        render = str(self.config.get("avatar", "render", "sprites") or "sprites")
        ov = None
        # Sin icono propio en la bandeja: la bandeja es una sola (corte 4, ui/bandeja.py).
        if render == "vrm":
            try:
                from ui.companion import CompanionFlotante
                ov = crear_asistente(CompanionFlotante, self.config, ai_manager=self.ai_manager,
                                     render="vrm")
            except Exception as e:
                log_error(f"[asistente] no pude abrir el avatar 3D ({e}); uso sprites")
                ov = None
        if ov is None:
            ov = crear_asistente(AvatarOverlay, self.config)
        try:
            ov.visibilidad.connect(self._on_asistente_visible)
        except Exception:
            pass
        try:
            ov.recrear.connect(self._asistente_recrear)      # arrancó en vídeo y ya hay .vrm
        except Exception:
            pass
        # Chat de la asistente (doble clic → EntradaChat): envía por el flujo normal
        # de la ventana. La asistente llama a `on_chat(texto)` si lo tiene puesto.
        on_chat = getattr(self, "_chat_desde_asistente", None)
        if callable(on_chat):
            try:
                ov.on_chat = on_chat
            except Exception:
                pass
        self._escritorio_asistente(ov)
        return ov

    def _escritorio_asistente(self, ov):
        """La asistente flotante nueva (o None) → ServiciosEscritorio (BusEstado y eventos)."""
        esc = getattr(self, "escritorio", None)
        if esc is None:
            return
        try:
            render = None if ov is None else (
                "sprites" if isinstance(ov, AvatarOverlay) else str(getattr(ov, "render", "") or ""))
            esc.set_asistente(ov, render=render)
        except Exception as e:
            log_error(f"[escritorio] no pude enganchar la asistente: {e}")

    def _on_asistente_visible(self, fuera: bool):
        """Lune fuera → el escenario de la barra lateral se apaga (no verla doble)."""
        if hasattr(self, "lune_face"):
            self.lune_face.setVisible(not fuera)

    def _asistente_viva(self):
        ov = self._overlay
        return ov if (ov is not None and not getattr(ov, "cerrado", False)) else None

    # ── Herramientas de la asistente (asistente_dormir / despertar / tamano) ──────
    def _registrar_herramientas_asistente(self):
        """Handlers del catálogo (riesgo ESCRITURA, sin aprobación, modos asistente/vrm)
        por el registro de ServiciosEscritorio (llegan al ToolManager y al Ejecutor)."""
        for nombre, fn in (("asistente_dormir", self._h_asistente_dormir),
                           ("asistente_despertar", self._h_asistente_despertar),
                           ("asistente_tamano", self._h_asistente_tamano)):
            try:
                self.escritorio.registrar_herramienta(nombre, fn)
            except Exception as e:
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
        "asistente" (sprites); si no, MODO_ACCIONES ("normal")."""
        ov = self._asistente_a_la_vista()
        if ov is None:
            return self.MODO_ACCIONES
        if isinstance(ov, AvatarOverlay):
            return "asistente"
        return "vrm" if str(getattr(ov, "render", "") or "") == "vrm" else "asistente"

    @staticmethod
    def _correr_en_ui(fn):
        """Slot de _en_ui_senal (hilo de Qt): corre fn()."""
        try:
            fn()
        except Exception:
            pass

    def en_ui(self, fn, espera_s: float = None):
        """Corre fn() en el hilo de Qt y devuelve su resultado. Desde otro hilo la
        encola (_en_ui_senal) y espera como mucho ESPERA_UI_S: TimeoutError si la
        ventana no contesta; la excepción de fn se relanza aquí."""
        if threading.get_ident() == self._hilo_qt:
            return fn()
        hecho = threading.Event()
        caja = {}

        def correr():
            try:
                caja["r"] = fn()
            except Exception as e:                   # noqa: BLE001
                caja["e"] = e
            finally:
                hecho.set()

        self._en_ui_senal.emit(correr)
        if not hecho.wait(self.ESPERA_UI_S if espera_s is None else espera_s):
            raise TimeoutError("la interfaz no respondió a tiempo")
        if "e" in caja:
            raise caja["e"]
        return caja.get("r")

    def _ctx_asistente(self, ctx, **extra) -> dict:
        """ctx del Ejecutor + la asistente a la vista (None si no hay: la herramienta
        devuelve un error claro). `en_ui` solo desde otro hilo: en el de Qt se llama
        directo y el resultado de dormir()/despertar() cuenta."""
        if ctx is None:
            c = {}
        elif isinstance(ctx, Mapping):
            c = dict(ctx)
        else:
            c = {"contexto": ctx}
        c.update(extra)
        c["asistente"] = self._asistente_a_la_vista()
        if threading.get_ident() != self._hilo_qt:
            c["en_ui"] = self.en_ui
        return c

    def _h_asistente_dormir(self, args, ctx=None):
        return sueno.herramienta_dormir(args, self._ctx_asistente(ctx))

    def _h_asistente_despertar(self, args, ctx=None):
        return sueno.herramienta_despertar(args, self._ctx_asistente(ctx))

    def _h_asistente_tamano(self, args, ctx=None):
        return vrm.herramienta_tamano(args, self._ctx_asistente(ctx, config=self.config))

    def _on_vrm_cambiado(self):
        """El panel de modelos VRM importó, asignó o guardó el seguimiento: la asistente
        3D carga el modelo que toque (si cambió) y aplica la calibración."""
        ov = self._asistente_viva()
        if ov is None:
            return
        for metodo in ("recargar_modelo", "aplicar_params_vrm"):
            fn = getattr(ov, metodo, None)
            if callable(fn):
                try:
                    fn()
                except Exception as e:
                    log_error(f"[asistente] {metodo}: {e}")

    def _on_hablando(self, activo: bool):
        # También con la asistente oculta: si no, al ocultarla mientras habla se
        # quedaría «hablando» para siempre (no se duerme, sonidos callados…). La
        # asistente guarda el estado y se lo pasa a su página al volver a verse.
        ov = self._asistente_viva()
        if ov is not None and hasattr(ov, "set_hablando"):
            try:
                ov.set_hablando(bool(activo))
            except Exception:
                pass

    def _asistente_recrear(self):
        ov = self._overlay
        vis = ov is not None and not getattr(ov, "cerrado", False) and ov.isVisible()
        if ov is not None:
            try: ov.close()
            except Exception: pass
        self._overlay = None
        self._escritorio_asistente(None)
        if vis:
            self._overlay = self._crear_asistente(); self._overlay.show(); self._overlay.raise_()

    def _toggle_historial(self):
        if self.stack.currentIndex() != 4:
            self.historial_panel.refrescar()
            self.stack.setCurrentIndex(4)
        else:
            self.stack.setCurrentIndex(0)

    def _switch_character(self, nombre):
        """Cambia el personaje activo: recarga prompt, limpia historial y saluda."""
        try:
            nombre = personajes.set_activo(nombre)      # solo uno que exista (con su nombre guardado)
        except ValueError as e:
            QMessageBox.warning(self, "Personaje", str(e)); return
        avisada = (self._turno or {}).get("remoto") if self._worker_vivo() else ""
        self._cortar_respuesta()                 # la respuesta en curso era del anterior
        datos.invalidar()
        self.ai_manager.clear_history()
        self._avisar_ordenes_pendientes(avisada)
        self.acciones.nueva_conversacion()
        self.voice.invalidar_params()            # cada personaje puede traer su voz

        p = personajes.get_activo()
        # Cambiar avatar pack si el personaje define uno
        pack = p.get("avatar_pack", "default")
        lune_face.set_active_pack(pack); self.config.set("avatar", "pack", pack)
        ov = self._asistente_viva()
        if ov is not None and hasattr(ov, "recargar_modelo"):
            ov.recargar_modelo()                 # el personaje puede traer su propio .vrm

        # Refrescar marca, banco y bienvenida
        self.sidebar_t1.setText(self._marca_sidebar(nombre))
        self.banco = BancoRespuestas(nombre_asistente=nombre, nombre_usuario=self.memoria.get_nombre_usuario(),
                                     tareas=getattr(self, "_resumen_tareas", None))

        # Limpiar chat y mostrar saludo del personaje
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._add_welcome()
        # Bienvenida a medias: sigue su pregunta, que ya presenta al personaje (sin el
        # «Dime qué necesitas» delante, que la contradice).
        if not (isinstance(getattr(self, "_bienvenida", None), Bienvenida)
                and self._repintar_pregunta_bienvenida([])):
            saludo = p.get("fraseInicial") or f"Soy {nombre}. Dime qué necesitas."
            bubble = MessageBubble(saludo, is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.lune_face.set_state("happy", auto_revert_ms=4000)
        self.stack.setCurrentIndex(0); self._scroll_bottom()

    def _marca_sidebar(self, nombre):
        """Rótulo de la barra lateral: nombre en blanco + «CD» en cyan."""
        return (f"<span style='color:{COLORS['text']};'>{nombre.upper()} </span>"
                f"<span style='color:{COLORS['accent']};'>CD</span>")

    def _on_keys_saved(self):
        if hasattr(self, 'red'):
            self.red.reanunciar()
        # datos.guardar() ya invalidó la caché, así que esto lee lo recién escrito.
        self.ai_manager.reload_provider()
        self._sincronizar_tab_compat()           # la API compatible pudo aparecer o irse
        # Salida de audio elegida en Configuración → se aplica sin reiniciar.
        if self.voice.available:
            self.voice.aplicar_salida(self.config.get("voz", "dispositivo_salida", "") or "")
        # Motor, voz, velocidad o tono pudieron cambiar: que la próxima frase los use.
        try:
            self.voice.reiniciar_motor()
        except Exception as e:
            log_error(f"[voz] no pude reiniciar el motor: {e}")
        self.stack.setCurrentIndex(0)

        personaje = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune"))
        nombre_bot = personaje.get("nombre", "Lune")
        self.sidebar_t1.setText(self._marca_sidebar(nombre_bot))
        self.banco = BancoRespuestas(nombre_asistente=nombre_bot,
                                     nombre_usuario=self.memoria.get_nombre_usuario(),
                                     tareas=getattr(self, "_resumen_tareas", None))
        if hasattr(self, 'welcome_t1'):
            self.welcome_t1.setText(nombre_bot.upper())
            nombre = self.memoria.get_nombre_usuario()
            saludo = personaje.get("fraseInicial") or (
                f"De vuelta, {nombre}. Dime qué necesitas." if nombre else "Lune en línea. Dime qué necesitas.")
            self.welcome_t2.setText(saludo)

        # Otro modo de interfaz: se aplica al instante (GestorInterfaz). Sin cajas
        # modales: el relevo es la confirmación (y la ventana nueva ya aplica el
        # modo de red que se acaba de guardar).
        modo = getattr(self.settings_panel, "modo_interfaz_pedido", None)
        if modo:
            self.settings_panel.modo_interfaz_pedido = None
            if modo != self.MODO_INTERFAZ:
                self.cambio_interfaz_pedido.emit(str(modo))
                return
        if datos.hub_modo() != self._modo_red:
            QMessageBox.information(self, "Guardado",
                "Configuración guardada. El modo de red cambió: reinicia Lune para aplicarlo.")
            return
        QMessageBox.information(self,"Guardado","Configuración guardada correctamente.")

    def _clear_chat(self):
        guardando = self.config.feature("guardar_conversaciones", True)
        texto = ("¿Empezar una conversación nueva?\n\n"
                 "La actual queda guardada en el Historial."
                 if guardando else "¿Eliminar todos los mensajes?")
        reply = QMessageBox.question(self, "Limpiar chat", texto,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._nueva_conversacion()

    # ── BANDEJA DEL SISTEMA (hidden items) ────────────────────────────────────
    @property
    def tray(self):
        """El icono de la bandeja: el de la bandeja única (corte 4, ui/bandeja.py) si
        está montada y en marcha; si no, el de respaldo. Se lee cada vez: tras
        detener/iniciar los servicios de escritorio el icono es otro."""
        s = getattr(self, "_servicios_c4", None)
        t = getattr(getattr(s, "bandeja", None), "icono_tray", None) if s is not None else None
        return t if t is not None else getattr(self, "_tray_respaldo", None)

    @tray.setter
    def tray(self, valor):
        self._tray_respaldo = valor

    def _build_tray(self):
        """Corte 4: bandeja única (un icono SIEMPRE, con el menú de nucleo/acciones_ui),
        atajos globales, menú radial, modo juego y tema, montados sobre
        self.escritorio (arrancan con escritorio.iniciar()). features.minimizar_a_bandeja
        ya no quita el icono: solo decide si cerrar la ventana la oculta. Si el montaje
        falla, el icono de siempre como respaldo."""
        if getattr(self, "_servicios_c4", None) is None:
            self._montar_servicios_c4()
        if getattr(getattr(self, "_servicios_c4", None), "bandeja", None) is not None:
            return
        self._build_tray_respaldo()

    def _montar_servicios_c4(self):
        """montar_escritorio con AnfitrionNativo; los servicios van también al panel
        de Ajustes (atajos para «Detectar»). Devuelve ServiciosCorte4 o None."""
        try:
            from ui.montaje_escritorio import montar_escritorio
            from ui.anfitrion_nativo import AnfitrionNativo
            s = montar_escritorio(self.escritorio, AnfitrionNativo(self), self.config,
                                  voice=self.voice, icono=self.windowIcon(),
                                  fabricas=self.FABRICAS_C4)
        except Exception as e:
            log_error(f"[corte4] no pude montar bandeja/atajos/radial/modo juego: {e}")
            self._servicios_c4 = None
            return None
        self._servicios_c4 = s
        panel = getattr(self, "settings_panel", None)
        usar = getattr(panel, "usar_servicios", None)
        if callable(usar):
            try:
                usar(s)                              # también el panel de ocio (cortes 5/6)
            except Exception as e:
                log_error(f"[corte4] el panel de Ajustes no tomó los servicios: {e}")
        # Apartados de escritorio: el tema y las casillas que cambian la bandeja, el
        # radial o un atajo se ven en Ajustes al momento (y no se pisan al guardar).
        enlazar = getattr(getattr(panel, "escritorio_panel", None), "enlazar_servicios", None)
        if callable(enlazar):
            try:
                enlazar(s)
            except Exception as e:
                log_error(f"[corte4] el panel de escritorio no tomó los servicios: {e}")
        self._conectar_baile(s)
        return s

    def _conectar_baile(self, s):
        """Cortes 5/6: estado del baile → carita y barra de estado (_on_baile); se
        desconecta al desmontar los servicios (cambio de interfaz o salir)."""
        baile = getattr(getattr(s, "ocio", None), "baile", None)
        senal = getattr(baile, "estado_cambio", None)
        if senal is None or not hasattr(senal, "connect"):
            return
        try:
            senal.connect(self._on_baile)
        except (TypeError, RuntimeError):
            return

        def soltar():
            try:
                senal.disconnect(self._on_baile)
            except (TypeError, RuntimeError):
                pass
        deshacer = getattr(s, "_deshacer", None)
        if isinstance(deshacer, list):
            deshacer.append(soltar)

    def _build_tray_respaldo(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.windowIcon() if not self.windowIcon().isNull() else QIcon())
        self.tray.setToolTip("Lune CD · IA Activa")

        menu = QMenu()
        act_open = QAction("Abrir Lune CD", self); act_open.triggered.connect(self._restore_from_tray)
        act_cfg  = QAction("Configuración", self);  act_cfg.triggered.connect(lambda: (self._restore_from_tray(), self._toggle_keys_panel()))
        act_quit = QAction("Salir", self);          act_quit.triggered.connect(self._quit_app)
        menu.addAction(act_open); menu.addAction(act_cfg); menu.addSeparator(); menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        # Doble clic o clic izquierdo restaura la ventana
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def _quit_app(self):
        self._quit_real = True
        self.close()

    def salir_de_verdad(self):
        """«Salir» (bandeja o cambio a patata): cierra la app entera."""
        self._quit_app()

    # ── Cambio de modo en caliente (GestorInterfaz, ui/cambio_interfaz.py) ─────
    def iniciar_servicios(self, estado=None):
        """Bandeja y servicios de escritorio (atajos globales, controladores) y lo que
        estaba en marcha en la ventana anterior: la asistente fuera (en su posición
        guardada) y el bot de Telegram (con el modo de órdenes de la config). Una vez."""
        if self._servicios_listos:
            return
        self._servicios_listos = True
        estado = estado if isinstance(estado, dict) else {}
        if self.tray is None:
            self._build_tray()
        try:
            self.escritorio.iniciar()
        except Exception as e:
            log_error(f"[interfaz] servicios de escritorio: {e}")
        if estado.get("asistente_fuera") and self._asistente_a_la_vista() is None:
            try:
                self._toggle_overlay()
            except Exception as e:
                log_error(f"[interfaz] no pude volver a sacar a la asistente: {e}")
        if estado.get("telegram") and not hilo_vivo(self._tg_worker):
            try:
                self._toggle_telegram()
            except Exception as e:
                log_error(f"[interfaz] no pude relanzar el bot de Telegram: {e}")
        # El modo juego forzado a mano (bandeja, radial, atajo) sigue forzado. Al final:
        # con la asistente ya fuera, el plan la esconde (si se sacara después, contaría
        # como sacada a mano en plena partida).
        forzado = estado.get("juego_forzado")
        juego = getattr(getattr(self, "_servicios_c4", None), "juego", None)
        if isinstance(forzado, bool) and callable(getattr(juego, "forzar", None)):
            try:
                juego.forzar(forzado)
            except Exception as e:
                log_error(f"[interfaz] no pude volver a forzar el modo juego: {e}")
        # Cortes 9/10: el bot de Minecraft que estaba conectado se vuelve a conectar (la
        # ventana vieja lo paró al desmontar; nunca se instala solo).
        if estado.get("minecraft_bot"):
            ok, texto = reconectar_bot_minecraft(getattr(self, "_servicios_c4", None))
            if not ok and texto:
                log_error(f"[interfaz] no pude volver a conectar el bot de Minecraft: {texto}")

    def estado_para_cambio(self) -> dict:
        """Lo que hereda la ventana del modo nuevo (la geometría la toma el gestor)."""
        return {
            "modo": self.MODO_INTERFAZ,
            "proveedor": self.current_provider,
            "voz": bool(getattr(self.voice, "_enabled", False)),
            "sesion": instantanea_sesion(getattr(self, "chats", None)),
            "asistente_fuera": self._asistente_a_la_vista() is not None,
            "telegram": hilo_vivo(self._tg_worker),
            "juego_forzado": juego_forzado_de(getattr(self, "_servicios_c4", None)),
            "minecraft_bot": bot_minecraft_de(getattr(self, "_servicios_c4", None)),
        }

    def aplicar_estado(self, estado) -> None:
        """Antes de enseñarse: proveedor, voz y la conversación de la ventana anterior
        (misma id en chats/; el modelo la recuerda con su marca de terceros)."""
        estado = estado if isinstance(estado, dict) else {}
        prov = str(estado.get("proveedor") or "")
        if prov and prov != self.current_provider and prov in self.provider_tabs:
            self._switch_provider(prov)
        if "voz" in estado:
            quiere = bool(estado.get("voz")) and bool(getattr(self.voice, "available", False))
            if bool(getattr(self.voice, "_enabled", False)) != quiere:
                self.voice._enabled = quiere
            self._pintar_voz()
        sesion = estado.get("sesion")
        if sesion and retomar_sesion(self.chats, sesion):
            self._pintar_sesion(sesion)          # pinta y recarga el historial del modelo

    def aviso_cambio(self, texto: str) -> None:
        QMessageBox.warning(self, "Modo de interfaz", str(texto))

    def cambio_fallido(self, modo: str, motivo: str) -> None:
        """El cambio no se hizo: el combo de Ajustes vuelve al modo actual."""
        panel = getattr(self, "settings_panel", None)
        fn = getattr(panel, "mostrar_modo_interfaz", None)
        if callable(fn):
            fn(self.MODO_INTERFAZ)

    def cerrar_para_cambio(self) -> dict:
        """Cambio de modo: suelta todo lo que la ventana nueva vuelve a crear y se
        cierra de verdad SIN salir de la app (sin bandeja ni QApplication.quit).
        Devuelve lo que estaba en marcha (asistente fuera, bot) para relanzarlo."""
        self._relevada = True
        # Órdenes de Telegram sin respuesta (la que se está respondiendo y la que espera
        # tu permiso): «Se detuvo…» una vez, antes de parar el bot. La marca se limpia:
        # _cortar_respuesta ya no la repite (ni si «Detener» ya la avisó).
        try:
            avisar_ordenes_cortadas(self)
        except Exception as e:
            log_error(f"[interfaz] al avisar a Telegram: {e}")
        # Corte 4 (bandeja única, atajos, detector de juego, radial, tema), una sola vez
        # y antes que el resto: la ventana nueva monta los suyos en iniciar_servicios
        # (dos a la vez no pueden: RegisterHotKey fallaría) y el modo juego devuelve lo
        # que cambió (prioridad, voz y la asistente que escondió, que cuenta como «fuera»).
        desmontar_servicios_c4(self)
        # IA en curso: cortada (generación nueva, señales fuera: ni pinta ni ejecuta
        # sus <|CALL|>), voz por frases y expresiones programadas fuera; el hilo se
        # retiene hasta que acabe. Si algo de esto falla, el resto se suelta igual (si no,
        # el bot, la asistente o el hub seguirían vivos y la ventana nueva los duplicaría).
        w = self.ai_worker
        try:
            self._cortar_respuesta()
        except Exception as e:
            log_error(f"[interfaz] al cortar la respuesta: {e}")
        detener_hilo_ia(w, getattr(getattr(self, "ai_manager", None), "providers", None))
        self.ai_worker = None
        try:
            self.acciones.cerrar()               # «¿Lo hago?» abiertas: se cierran sin hacer nada
        except Exception:
            pass
        if self._grabadora is not None:
            try:
                self._grabadora.cancelar()
            except Exception:
                pass
            self._grabadora = None
        soltar_hilos(self._transcriptor, self._sondeo_prov, getattr(self, "_git_check", None))
        parar_temporizadores(getattr(self, "_timer_estado", None), getattr(self, "_timer_bienvenida", None))
        try:
            self._cancelar_plan()
        except Exception as e:
            log_error(f"[interfaz] al parar las expresiones programadas: {e}")
        if getattr(self.lune_face, "_player", None):
            try:
                self.lune_face._player.stop()
            except Exception:
                pass
        callar_voz(self.voice)                   # corta y suelta al_hablar/on_error
        # La conversación queda en chats/ (la nueva la retoma); notas y red, parados.
        for fn in (self.chats.guardar, self.notas.cerrar, self.red.detener):
            try:
                fn()
            except Exception as e:
                log_error(f"[interfaz] al cerrar: {e}")
        # Asistente y bot: la ventana nueva los relanza si estaban en marcha.
        fuera = cerrar_asistente(self._asistente_viva())
        self._overlay = None
        telegram = detener_bot(self._tg_worker)
        self._tg_worker = None
        # Servicios de escritorio (atajos globales, controladores) y el hub.
        try:
            self.escritorio.cerrar()
        except Exception:
            pass
        for hub in (self._hub_cliente, self._hub_en_hilo):
            if hub is not None:
                try:
                    hub.detener()
                except Exception as e:
                    log_error(f"[interfaz] no pude parar el hub: {e}")
        self._hub_cliente = self._hub_en_hilo = None
        quitar_bandeja(self.tray)                # la de respaldo (la única se fue con el corte 4)
        self.tray = None
        self.hide()
        self.close()
        return {"asistente_fuera": fuera, "telegram": telegram}

    def closeEvent(self, event):
        if getattr(self, "_relevada", False):
            event.accept()                       # cambio de modo: ya soltó todo
            return
        # Minimizar a la bandeja en vez de salir (features.minimizar_a_bandeja y hay
        # bandeja; el icono de la bandeja única está siempre).
        if (self.tray is not None and not self._quit_real
                and self.config.feature("minimizar_a_bandeja", True)):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Lune CD", "Sigo aquí en la bandeja. Doble clic para abrirme.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            return

        # Salir de verdad (bandeja, patata, cerrar sin bandeja) con una orden de Telegram
        # sin respuesta: «Se detuvo…» una vez, antes de cerrar las preguntas y el bot.
        try:
            avisar_ordenes_cortadas(self)
        except Exception as e:
            log_error(f"[salir] al avisar a Telegram: {e}")

        if hasattr(self, "memoria"):
            stats = self.memoria.get_stats()
            resumen = f"Sesión del {datetime.now().strftime('%d/%m/%Y')}. Mensajes intercambiados hoy: {stats.get('total_mensajes', 0)}."
            self.memoria.cerrar_sesion(resumen)

        # Cortar el dictado y volcar la conversación antes de irnos
        if self._grabadora is not None:
            self._grabadora.cancelar()
        if hasattr(self, "chats"):
            self.chats.guardar()
        if hasattr(self, "notas"):
            self.notas.cerrar()
        if hasattr(self, "red"):
            self.red.detener()
        if hasattr(self, "acciones"):
            self.acciones.cerrar()               # ninguna pregunta «¿Lo hago?» colgada
        # Corte 4 (bandeja única, atajos, detector de juego, radial, tema), una vez y
        # antes que los servicios de escritorio: el modo juego devuelve lo que cambió.
        desmontar_servicios_c4(self)
        if hasattr(self, "escritorio"):
            self.escritorio.cerrar()
        if self._overlay is not None:
            self._overlay.close()
        if hasattr(self, "_timer_estado"):
            self._timer_estado.stop()
        if getattr(self, "_timer_bienvenida", None) is not None:
            self._timer_bienvenida.stop()
        if self._hub_cliente is not None:
            self._hub_cliente.detener()
        if self._hub_en_hilo is not None:
            self._hub_en_hilo.detener()

        if hasattr(self,"lune_face") and self.lune_face._player: self.lune_face._player.stop()
        if hasattr(self,"_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            self._tg_worker.stop(); self._tg_worker.wait(3000)
        if self.tray is not None:                # la de respaldo, si la hubo
            self.tray.hide()
        soltar_avisos_voz(self)                  # el hilo de audio ya no avisa a esta ventana
        event.accept()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────
def _cargar_fuentes():
    """Registra las fuentes Shibuya Punk empaquetadas en fonts/ para esta app."""
    import glob
    fonts_dir = str(rutas.recurso("fonts"))
    if not os.path.isdir(fonts_dir):
        return
    for ttf in glob.glob(os.path.join(fonts_dir, "*.ttf")):
        QFontDatabase.addApplicationFont(ttf)


CLAVE_INSTANCIA = "LuneCD-instancia-unica"


def _mostrar_de_verdad(ventana):
    """
    Muestra una ventana ignorando el estado que herede del lanzador.

    Windows pasa al proceso hijo el «estilo de ventana» con el que se lanzó
    (STARTUPINFO), y Qt lo aplica a la primera ventana de nivel superior. Si
    alguien arranca Lune en modo oculto —como hacía el .vbs con `Run cmd, 0`—
    la app corría con la ventana invisible: se oía el video y no se veía nada.
    Esto lo deshace explícitamente.
    """
    ventana.show()
    ventana.setWindowState(
        ventana.windowState() & ~Qt.WindowState.WindowMinimized
    )
    ventana.showNormal()
    ventana.raise_()
    ventana.activateWindow()


PEDIR_MOSTRAR = b"mostrar"          # lo que manda una segunda instancia normal
PEDIR_SILENCIO = b"silencio"        # la del arranque con Windows: no trae nada al frente


def _ya_hay_una_instancia(silencioso: bool = False, clave: str = CLAVE_INSTANCIA) -> bool:
    """
    ¿Hay otra Lune corriendo?

    Se lanza desde un .vbs y desde la carpeta de Inicio, así que abrirla dos
    veces es facilísimo (doble clic, o arrancar a mano lo que ya estaba). En vez
    de tener dos Lunes peleándose por datos.json, memoria.json y el mismo puerto
    del bot, la segunda avisa a la primera y se va.

    `silencioso` (arranque con Windows, nucleo/arranque.Plan.silencioso): se va igual,
    pero sin pedir a la primera que se enseñe (a quien arrancó el PC no le salta una
    ventana). La primera solo trae al frente con «mostrar» (ver _AvisosInstancia).
    """
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(clave)
    if socket.waitForConnected(300):
        # Ya hay una viva: le pedimos que se muestre (o no) y nos retiramos.
        socket.write(PEDIR_SILENCIO if silencioso else PEDIR_MOSTRAR)
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True

    # Un servidor huérfano (de un cierre a lo bruto) bloquearía el arranque.
    QLocalServer.removeServer(clave)
    servidor = QLocalServer()
    servidor.listen(clave)
    # Referencia global para que no lo recoja el recolector de basura
    globals()["_servidor_instancia"] = servidor
    return False


class _AvisosInstancia(QObject):
    """El servidor de instancia única, filtrado: `newConnection` cuando otra Lune pide
    «mostrar» (o se va sin decir nada, como las de antes). La del arranque con Windows
    («silencio») no trae nada al frente.
    Se pasa a GestorInterfaz.conectar_servidor como si fuera el servidor (no deja
    conexiones pendientes: las lee y las suelta aquí)."""

    newConnection = pyqtSignal()

    def __init__(self, servidor, parent=None):
        super().__init__(parent)
        self._servidor = servidor
        self._leidos = {}
        senal = getattr(servidor, "newConnection", None)
        if senal is not None and hasattr(senal, "connect"):
            senal.connect(self._nuevas)

    def hasPendingConnections(self) -> bool:
        return False

    def nextPendingConnection(self):
        return None

    def _nuevas(self) -> None:
        srv = self._servidor
        try:
            while srv.hasPendingConnections():
                s = srv.nextPendingConnection()
                if s is None:
                    break
                self._leidos[id(s)] = b""
                s.readyRead.connect(lambda s=s: self._leer(s))
                s.disconnected.connect(lambda s=s: self._soltar(s))
                self._leer(s)                        # lo que ya hubiera llegado
                if self._ya_desconectado(s):
                    # Se fue antes de que esto conectara `disconnected` (escribió y cerró
                    # enseguida): esa señal ya no llegará. Sin esto, su entrada se quedaba en
                    # _leidos (y el id reciclado la mezclaba con otra) y el socket, sin borrar.
                    self._soltar(s)
        except Exception as e:
            log_error(f"[instancia] no pude leer una conexión: {e}")

    @staticmethod
    def _ya_desconectado(s) -> bool:
        estado = getattr(s, "state", None)
        if not callable(estado):
            return False
        try:
            from PyQt6.QtNetwork import QLocalSocket
            return estado() == QLocalSocket.LocalSocketState.UnconnectedState
        except Exception:
            return False

    def _leer(self, s) -> None:
        clave = id(s)
        if clave not in self._leidos:
            return
        try:
            if s.bytesAvailable() > 0:
                self._leidos[clave] += bytes(s.readAll())
        except Exception:
            return
        if PEDIR_MOSTRAR in self._leidos[clave]:
            self._leidos.pop(clave, None)            # una vez por conexión
            self.newConnection.emit()

    def _soltar(self, s) -> None:
        self._leer(s)
        datos = self._leidos.pop(id(s), None)
        # Se fue sin decir nada legible (una Lune vieja, o los datos no llegaron): como
        # siempre, se trae al frente. Solo «silencio» (arranque con Windows) no lo hace.
        if datos is not None and PEDIR_SILENCIO not in datos:
            self.newConnection.emit()
        try:
            s.deleteLater()
        except Exception:
            pass


def _patata_ya_abierta(mostrar: bool = True) -> bool:
    """¿Ya hay una patata viva (servicios/instancia_patata)? Con `mostrar`, se le pide que
    traiga su consola al frente (si Windows no deja, parpadea y dice «¡Sigo aquí!»)."""
    try:
        from servicios import instancia_patata as ip
        if not ip.patata_viva():
            return False
        if mostrar:
            ip.pedir_mostrar()
        return True
    except Exception as e:
        log_error(f"[ui] no pude mirar si ya había una patata: {e}")
        return False


def _lanzar_patata(autoinicio: bool = False) -> bool:
    """Abre la terminal (patata) en una consola NUEVA y devuelve si pudo: desde el
    código, patata.py con el python.exe hermano (desde el .vbs corremos con pythonw,
    sin consola); instalada, LunePatata.exe (nucleo/rutas.orden_patata). Con
    `autoinicio` (arranque con Windows y la entrada aún en su variante de ventanas)
    va con --autoinicio y la consola se abre minimizada, sin quitar el foco (D3).
    Si ya hay una patata viva (la del arranque con Windows, u otra), no se abre otra
    terminal: se trae al frente la que hay (con `autoinicio`, ni eso) y cuenta como hecho."""
    import subprocess
    if _patata_ya_abierta(mostrar=not autoinicio):
        log_info("[ui] modo patata: Lune ya estaba en una terminal; no abro otra")
        return True
    orden = rutas.orden_patata(*(["--autoinicio"] if autoinicio else []))
    lanzador = orden[0] if rutas.INSTALADA else orden[1]     # LunePatata.exe o patata.py
    if not os.path.exists(lanzador):
        log_error(f"[ui] no encuentro {os.path.basename(lanzador)}")
        return False
    try:
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
        kw = {"cwd": str(rutas.PROGRAMA), "creationflags": flags}
        if autoinicio and os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7                   # SW_SHOWMINNOACTIVE: minimizada, sin foco
            kw["startupinfo"] = si
        subprocess.Popen(orden, **kw)
        log_info("[ui] modo patata: Lune abierta en la terminal")
        return True
    except Exception as e:
        log_error(f"[ui] no pude lanzar {os.path.basename(lanzador)}: {e}")
        return False


def _crear_ventana_principal(autoinicio: bool = False, oculta: bool = False):
    """
    Ventana principal. Por defecto la piel web "Shibuya Punk" (QWebEngineView);
    con interfaz.modo="nativo" en config.json, o si la web falla, la PyQt clásica.
    En modo patata abre la terminal (minimizada si `autoinicio`) y devuelve None.
    `oculta` (arranque con Windows a la bandeja o con la asistente fuera): la web no
    carga su página hasta que la ventana se enseñe (VentanaWeb cargar_al_mostrar, 11.2).
    """
    try:
        from nucleo.config import Config
        modo = str(Config().get("interfaz", "modo", "web"))
    except Exception:
        modo = "web"
    if modo == "patata":
        # Modo patata: Lune en la terminal, sin Qt. Se abre en una consola nueva
        # (venimos de pythonw, sin consola) y esta app se retira.
        if _lanzar_patata(autoinicio=autoinicio):
            return None
        log_error("[ui] no pude abrir el modo patata; uso la interfaz nativa")
        return LuneCDWindow()
    if modo == "web":
        try:
            from ui.web_shell import VentanaWeb
            return VentanaWeb(cargar_al_mostrar=bool(oculta))
        except Exception as e:
            log_error(f"[ui] no pude abrir la piel web ({e}); uso la interfaz nativa")
    return LuneCDWindow()


def _fabrica_ventana(modo: str):
    """Fábrica de GestorInterfaz: la ventana de `modo` SIN sus servicios exclusivos
    (bandeja, atajos…): la anterior aún los tiene; el gestor llama a
    iniciar_servicios() cuando la anterior los suelta. Si falla, lanza (y el gestor
    deja la anterior); aquí NO se cae a la nativa como al arrancar."""
    if modo == "web":
        from ui.web_shell import VentanaWeb
        return VentanaWeb(diferir_servicios=True)
    if modo == "nativo":
        return LuneCDWindow(diferir_servicios=True)
    raise ValueError(f"modo de interfaz desconocido: {modo}")


def _reparar_autoinicio(cfg=None, modo=None, *, mod=None) -> str:
    """Arranque con Windows: si la entrada Run existe pero apunta a otra carpeta o a
    la variante de otro modo, se reescribe (servicios/autoinicio.reparar: nunca la
    crea ni toca StartupApproved). Con `cfg`, `sistema.autoinicio` queda como el
    registro de verdad (el Administrador de tareas puede haberla deshabilitado).
    Devuelve "", "ruta" o "modo". Nunca lanza."""
    try:
        if mod is None:
            from servicios import autoinicio as mod
        if modo is None:
            modo = str(cfg.get("interfaz", "modo", "web") or "web") if cfg is not None else None
        motivo = str(mod.reparar(cfg, modo) or "")
        if motivo:
            log_info(f"[autoinicio] entrada de arranque con Windows reparada ({motivo})")
        if cfg is not None:
            activo = bool(mod.activo())
            if bool(cfg.get("sistema", "autoinicio", False)) != activo:
                cfg.set("sistema", "autoinicio", activo)
        return motivo
    except Exception as e:
        log_error(f"[autoinicio] no pude revisar la entrada de arranque: {e}")
        return ""


def _guardar_modo_interfaz(modo: str) -> None:
    """guardar_modo de GestorInterfaz: interfaz.modo en config.json y, si Lune arranca
    con Windows, la entrada Run en la variante del modo nuevo (patata → consola
    minimizada sin PyQt6; web/nativo → la app). También en el cambio en caliente."""
    from nucleo.config import Config
    Config().set("interfaz", "modo", modo)
    _reparar_autoinicio(None, modo)


def _crear_gestor_interfaz():
    """GestorInterfaz de la app: cambio de modo en caliente (Ajustes → Modo de
    interfaz). interfaz.fundido_ms en config.json (por defecto 180; 0 = sin fundido)."""
    try:
        from nucleo.config import Config
        fundido = int(Config().get("interfaz", "fundido_ms", 180))
    except Exception:
        fundido = 180
    return GestorInterfaz(_fabrica_ventana, guardar_modo=_guardar_modo_interfaz,
                          lanzar_patata=_lanzar_patata, fundido_ms=fundido)


def _preparar_arranque(argv, config=None):
    """(opciones, plan, config) del arranque (nucleo/arranque.py): a mano, el de
    siempre; con --autoinicio, sin pantalla de inicio y tras la espera. `config`
    None → Config() (None si no se puede leer: plan con los valores por defecto)."""
    from nucleo import arranque
    opc = arranque.parsear_args(argv)
    cfg = config
    if cfg is None:
        try:
            from nucleo.config import Config
            cfg = Config()
        except Exception as e:
            log_error(f"[arranque] no pude leer config.json: {e}")
            cfg = None
    return opc, arranque.plan_arranque(cfg, opc), cfg


def _presentar_principal(ventana, plan, *, mostrar: bool = False) -> str:
    """Enseña la ventana recién creada según el plan de arranque: "ventana" (a la
    vista), "asistente" (oculta y la asistente fuera) o "bandeja" (oculta, solo el icono;
    los servicios y la bandeja ya arrancaron en el constructor). `mostrar` (alguien
    abrió Lune durante la espera) manda. Sin icono de bandeja nunca queda invisible."""
    if mostrar or plan.mostrar_ventana:
        _mostrar_de_verdad(ventana)
        return "ventana"
    if plan.abrir_asistente:
        desp = getattr(getattr(ventana, "_servicios_c4", None), "despachador", None)
        ok = False
        try:
            ok = bool(desp.ejecutar("asistente")) if desp is not None else False
        except Exception as e:
            log_error(f"[arranque] no pude sacar a la asistente: {e}")
        if ok:
            return "asistente"
    if getattr(ventana, "tray", None) is None:
        _mostrar_de_verdad(ventana)              # ni bandeja: que se vea algo
        return "ventana"
    return "bandeja"


def _abrir_tras_espera(retraso_s, abrir, avisos=None, *, programar=None) -> dict:
    """Arranque con Windows: `abrir()` a los `retraso_s` segundos. Si mientras tanto
    otra Lune pide «mostrar» (la abriste a mano), `abrir(mostrar=True)` ya. Una vez."""
    estado = {"hecho": False}

    def soltar():
        senal = getattr(avisos, "newConnection", None)
        if senal is not None:
            try:
                senal.disconnect(abrir_ya)
            except (TypeError, RuntimeError):
                pass

    def abrir_ya():
        soltar()
        if not estado["hecho"]:
            estado["hecho"] = True
            abrir(mostrar=True)

    def al_vencer():
        soltar()
        if not estado["hecho"]:
            estado["hecho"] = True
            abrir()

    senal = getattr(avisos, "newConnection", None)
    if senal is not None and hasattr(senal, "connect"):
        senal.connect(abrir_ya)
    (programar or QTimer.singleShot)(max(0, int(retraso_s or 0)) * 1000, al_vencer)
    return estado


def _instalar_red_de_excepciones():
    """
    Red de seguridad: con el sys.excepthook de serie, PyQt6 ABORTA el proceso ante
    una excepción no capturada en un slot (se cerraba Lune entera, sin rastro).
    Con este gancho el error se registra en el log (y en la consola, si hay) y la
    app sigue. Solo lo instala main(): los tests no pasan por aquí, así que allí
    los errores se siguen viendo como siempre. Devuelve el gancho.
    """
    import traceback

    def gancho(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            log_error(f"[ui] excepción no capturada (la app sigue):\n{texto}")
        except Exception:
            pass
        if sys.stderr is not None:              # con pythonw no hay consola
            try:
                sys.stderr.write(texto)
            except Exception:
                pass

    sys.excepthook = gancho
    return gancho


def _fijar_aumid(shell32=None) -> bool:
    """AppUserModelID fijo (nucleo/rutas.AUMID, el mismo que el acceso directo del menú
    Inicio): con uno por versión, el icono anclado a la barra de tareas dejaba de ser
    Lune tras cada actualización. Antes de enseñar ninguna ventana. Nunca lanza."""
    try:
        if shell32 is None:
            import ctypes
            shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID(rutas.AUMID)
        return True
    except Exception:
        return False


def _esperar_a_la_anterior(opc, esperar=None) -> bool:
    """Tras un reinicio (servicios/actualizador.reiniciar llega con --esperar-pid N):
    espera a que la Lune de antes termine de cerrarse ANTES de mirar la instancia
    única; si no, esta se conectaba al servidor de la vieja y se iba sin abrir nada."""
    pid = int(getattr(opc, "esperar_pid", 0) or 0)
    if pid <= 0:
        return True
    if esperar is None:
        from nucleo import arranque
        esperar = arranque.esperar_a_que_muera
    ok = bool(esperar(pid))
    if not ok:
        log_info(f"[arranque] la Lune anterior (PID {pid}) tarda en cerrarse; sigo igual")
    return ok


def _programar_aviso_actualizacion(gestor, config=None, *, fabrica=None):
    """El aviso de versión nueva al abrir Lune (ui/actualizacion_qt.AvisoInicio), uno por
    proceso y colgado del GestorInterfaz: ~45 s después, como mucho una vez cada 24 h
    (actualizaciones.ultima_comprobacion) y nunca en modo juego. Instalada mira GitHub
    Releases; desde el código, git. Devuelve el AvisoInicio (None si no toca). Nunca lanza."""
    try:
        if fabrica is None:
            from ui.actualizacion_qt import AvisoInicio as fabrica
        if config is None:
            from nucleo.config import Config
            config = Config()
        aviso = fabrica(config, ventana=lambda: getattr(gestor, "ventana", None), parent=gestor)
        return aviso if aviso.iniciar() else None
    except Exception as e:
        log_error(f"[actualizaciones] no pude programar el aviso al iniciar: {e}")
        return None


def _marcar_abierta() -> int:
    """El mutex «Lune está abierta» (servicios/mutex_win.marcar_abierta): el instalador
    espera a que desaparezca antes de reemplazar archivos. Vive hasta salir. Nunca lanza."""
    try:
        from servicios.mutex_win import marcar_abierta
        return marcar_abierta()
    except Exception as e:
        log_error(f"[arranque] no pude marcar Lune como abierta: {e}")
        return 0


def main():
    # Instalada (Lune.exe): freeze_support, HF_HOME, carpeta de trabajo en tus datos y
    # stdout/stderr (nucleo/arranque.preparar_instalada). Desde el código no hace nada.
    from nucleo import arranque
    arranque.preparar_instalada()
    _fijar_aumid()
    # QtWebEngine (avatar VRM) necesita compartir el contexto OpenGL; hay que
    # pedirlo ANTES de crear QApplication. Inofensivo si no se usa el VRM.
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")
    _instalar_red_de_excepciones()
    # La basura con ciclos (ventanas y diálogos cerrados) se recoge solo en este hilo: con
    # el recolector automático podía recogerse dentro de un hilo de fondo (la voz, la
    # música, el diagnóstico…) y Qt tumbaba el proceso (ui/recolector_qt.py).
    try:
        from ui.recolector_qt import instalar as _instalar_recolector
        globals()["_recolector_qt"] = _instalar_recolector(app)
    except Exception as e:                       # noqa: BLE001 (sin él, Lune sigue como antes)
        log_error(f"[ui] no pude poner el recolector en el hilo de Qt: {e}")

    # A mano o con Windows (--autoinicio desde iniciar_lune.vbs /autoinicio o Lune.exe
    # --autoinicio). Tras un reinicio, primero que la Lune de antes acabe de irse.
    opc, plan, cfg = _preparar_arranque(sys.argv[1:])
    _esperar_a_la_anterior(opc)
    if _ya_hay_una_instancia(silencioso=plan.silencioso):
        log_info("Lune ya estaba abierta: no abro una segunda")
        return
    _marcar_abierta()
    # La entrada de arranque con Windows sigue a la carpeta y al modo de interfaz.
    _reparar_autoinicio(cfg)

    # Tipografía Shibuya Punk: cargar las fuentes empaquetadas en fonts/.
    _cargar_fuentes()
    # Si alguna no estuviera, Qt la sustituye por una del sistema (fallback).
    for familia, fallback in FONT_FALLBACKS.items():
        QFont.insertSubstitution(familia, fallback)
    app.setFont(QFont(FONT_BODY, 10))

    for ext in ("ico","png"):
        icon_path = str(rutas.recurso("assets", f"lune_icon.{ext}"))
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,     QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base,       QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text,       QColor(COLORS["text"]))
    app.setPalette(palette)

    # La ventana principal la crea main(), no la pantalla de inicio: así nunca hay
    # dos ventanas vivas a la vez y la referencia no depende de un objeto que se
    # está destruyendo. La conserva el GestorInterfaz (ui/cambio_interfaz.py), que
    # la cambia en caliente por la de otro modo (Ajustes → Modo de interfaz); aquí
    # no se guarda otra referencia (retendría la vieja tras un cambio).
    ventanas = {"gestor": _crear_gestor_interfaz()}
    # Las conexiones de otra Lune que piden «mostrar» (no las del arranque con Windows).
    srv = globals().get("_servidor_instancia")
    avisos = _AvisosInstancia(srv) if srv is not None else None
    ventanas["avisos"] = avisos

    def abrir_principal(mostrar=False):
        gestor = ventanas["gestor"]
        if ventanas.get("abierta"):
            return
        ventanas["abierta"] = True
        # Nace oculta (bandeja o asistente fuera) si nadie la pidió: la página web, al enseñarla.
        ventana = _crear_ventana_principal(autoinicio=opc.autoinicio,
                                           oculta=not (mostrar or plan.mostrar_ventana))
        if ventana is None:
            # Modo patata: Lune ya vive en la terminal; esta app Qt se retira.
            QApplication.instance().quit()
            return
        gestor.adoptar(ventana)
        # A la vista, o (arranque con Windows) en la bandeja o con la asistente fuera.
        _presentar_principal(ventana, plan, mostrar=mostrar)
        # Versión nueva: ~45 s después, una vez al día y nunca en modo juego (a la ventana
        # que haya entonces, aunque cambies de interfaz en medio).
        ventanas["actualizaciones"] = _programar_aviso_actualizacion(gestor)

        # Si intentas abrir Lune otra vez, se trae al frente la ventana ACTUAL
        # (también después de un cambio de modo).
        gestor.conectar_servidor(avisos)

    if plan.splash:
        ventana_inicio = PantallaInicio(al_terminar=abrir_principal)
        ventanas["inicio"] = ventana_inicio
        _mostrar_de_verdad(ventana_inicio)
    else:
        # Arranque con Windows: sin pantalla de inicio y tras la espera (patata, que no
        # carga Qt pesado, sin esperar); abrir Lune a mano mientras tanto abre ya.
        modo = str(cfg.get("interfaz", "modo", "web") or "web") if cfg is not None else "web"
        retraso = 0 if modo == "patata" else plan.retraso_s
        ventanas["espera"] = _abrir_tras_espera(retraso, abrir_principal, avisos)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
