"""
main.py — Ventana principal de Lune CD y punto de entrada.
La UI está repartida en módulos:
  theme.py · lune_face.py · voice.py · telegram_worker.py
  chat_widgets.py · ai_worker.py · settings_panel.py
  optimizer_panel.py · splash.py
"""
import sys
import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QStackedWidget, QFileDialog,
    QSystemTrayIcon, QMenu, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QAction, QPixmap, QFontDatabase

import adjuntos as adj
import voz_entrada
from config import Config
from ai_manager import AIManager
from conversaciones import GestorConversaciones
from historial_panel import HistorialPanel
from utils import Logger, log_info, log_error
import datos
from memoria import MemoriaManager
from tools import ToolManager
from respuestas import BancoRespuestas

from theme import (
    COLORS, APP_VERSION, PROVIDER_META,
    FONT_DISPLAY, FONT_BODY, FONT_MONO, FONT_JP, FONT_FALLBACKS,
)
import lune_face
from lune_face import LuneFaceWidget, detect_emotion
from icons import icon, icon_pixmap
from effects import apply_glow, clear_glow
from voice import VoiceEngine
from telegram_worker import TelegramBotWorker
from chat_widgets import ProviderTab, MessageBubble, TypingIndicator
from ai_worker import AIWorker
from settings_panel import SettingsPanel
from optimizer_panel import OptimizadorPanel
from personajes_panel import PersonajesPanel
import personajes
from splash import PantallaInicio

logger = Logger()


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
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class LuneCDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Config visual/features (config.json) + APIs/personalidad (datos.json)
        self.config           = Config()
        self.ai_manager       = AIManager()
        self.voice            = VoiceEngine()
        self.current_provider = "openrouter"
        self.ai_worker        = None
        self._current_bubble  = None
        self._typing_indicator= None
        self._tg_worker       = None
        self.tray             = None
        self._quit_real       = False
        self.memoria          = MemoriaManager()
        self.tools            = ToolManager()
        # Red de Lune: host (sirvo a otros), terminal (memoria del host) o local
        self._hub_en_hilo     = None
        self._hub_cliente     = None
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

        # Banco de respuestas instantáneas con la personalidad de Lune
        nombre_bot = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune")).get("nombre", "Lune")
        self.banco = BancoRespuestas(nombre_asistente=nombre_bot,
                                     nombre_usuario=self.memoria.get_nombre_usuario())

        # Aplicar preferencias de rendimiento antes de construir la UI
        lune_face.set_active_pack(self.config.get("avatar", "pack", "default"))
        lune_face.set_anim_video(self.config.feature("animaciones_video", True))
        if self.config.feature("voz_auto", False) and self.voice.available:
            self.voice.toggle()

        self._init_ui()
        self._build_tray()
        self._restaurar_o_iniciar_sesion()

        # Punto de estado de cada proveedor: se sondea al arrancar y cada 60 s,
        # para no enterarte de que Ollama está caído al mandar un mensaje.
        self._timer_estado = QTimer(self)
        self._timer_estado.timeout.connect(self._sondear_proveedores)
        self._timer_estado.start(60000)
        QTimer.singleShot(800, self._sondear_proveedores)

        if self.config.get("actualizaciones", "comprobar_al_iniciar", False):
            QTimer.singleShot(4000, self._comprobar_updates_silencioso)

        log_info(f"Lune CD v{APP_VERSION} iniciado")

    # ── Actualizaciones ───────────────────────────────────────────────────────
    def _comprobar_updates_silencioso(self):
        """
        Mira si hay versión nueva al arrancar, sin interrumpir.
        Solo avisa si hay algo; si no, ni se entera el usuario.
        """
        from settings_panel import GitWorker
        self._git_check = GitWorker("comprobar", self.config.get("actualizaciones", "rama", "master"))
        self._git_check.listo.connect(self._on_update_disponible)
        self._git_check.start()

    def _on_update_disponible(self, res):
        if not res.get("ok") or not res.get("hay_novedades"):
            return
        n = res.get("pendientes", 0)
        log_info(f"Hay {n} actualización(es) disponibles")
        if self.tray is not None:
            self.tray.showMessage(
                "Lune CD", f"Hay {n} actualización(es). Ve a Ajustes → Actualizaciones.",
                QSystemTrayIcon.MessageIcon.Information, 6000,
            )
        else:
            self._burbuja_bot(
                f"Por cierto: hay **{n} actualización(es)** esperando. "
                "Cuando quieras, entra en ⚙️ Ajustes → Actualizaciones."
            )

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
        self.chats.nueva_sesion(
            proveedor=self.current_provider,
            personaje=datos.get_bot().get("personaje_default", "Lune"),
        )
        self.ai_manager.clear_history()
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._add_welcome()
        self.lune_face.set_state("normal")
        self.stack.setCurrentIndex(0)
        if hasattr(self, "historial_panel"):
            self.historial_panel.refrescar()

    def _abrir_conversacion(self, sesion_id):
        sesion = self.chats.cargar(sesion_id)
        if not sesion:
            QMessageBox.warning(self, "No pude abrirla", "Esa conversación ya no está."); return
        self._pintar_sesion(sesion)
        self.stack.setCurrentIndex(0)
        self.historial_panel.refrescar()

    def _guardar_turno(self, rol, contenido, adjuntos=None, uso=None):
        if self.config.feature("guardar_conversaciones", True):
            self.chats.agregar(rol, contenido, adjuntos=adjuntos, uso=uso)

    # ── Estado de los proveedores ─────────────────────────────────────────────
    def _sondear_proveedores(self):
        if self._sondeo_prov and self._sondeo_prov.isRunning():
            return
        self._sondeo_prov = SondeoProveedoresWorker(self.ai_manager.providers)
        self._sondeo_prov.listo.connect(self._on_estado_proveedores)
        self._sondeo_prov.start()

    def _on_estado_proveedores(self, estados):
        for pid, disponible in (estados or {}).items():
            tab = self.provider_tabs.get(pid)
            if not tab:
                continue
            if pid == "ollama":
                detalle = (f"Ollama responde en {datos.ollama_url()}" if disponible
                           else f"Sin respuesta de {datos.ollama_url()}")
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
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"lune_icon.{ext}")
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
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lune_icon.png")
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
        for pid, meta in PROVIDER_META.items():
            tab = ProviderTab(pid, meta)
            tab.clicked.connect(self._switch_provider)
            self.provider_tabs[pid] = tab
            layout.addWidget(tab)
        self.provider_tabs["openrouter"].set_active(True)

        layout.addStretch()

        # ── ESCENARIO DE LA MASCOTA ──
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
        # El tile de Telegram era relleno visual sin acción y solo aparecía si
        # había voz. Ahora es el que enciende y apaga el bot, en lugar del botón
        # ancho que se salía de la barra lateral.
        self._telegram_tile = self._tile_btn("TELEGRAM", "telegram")
        self._telegram_tile.clicked.connect(self._toggle_telegram)
        self._set_telegram_btn_style(False)

        grid.addWidget(self._keys_btn, 0, 0); grid.addWidget(pers_btn, 0, 1)
        grid.addWidget(opt_btn, 1, 0); grid.addWidget(mem_btn, 1, 1)
        grid.addWidget(tools_btn, 2, 0); grid.addWidget(hist_btn, 2, 1)
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

    def _show_tools(self):
        texto = self.tools.listar_disponibles()
        bubble = MessageBubble(texto, is_user=False, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.lune_face.set_state("reading", auto_revert_ms=5000); self._scroll_bottom()

    # ── TELEGRAM ──────────────────────────────────────────────────────────────
    def _toggle_telegram(self):
        if hasattr(self,"_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            self._tg_worker.stop(); self._tg_worker.requestInterruption(); self._tg_worker.wait(3000); self._tg_worker = None
            self._set_telegram_btn_style(False); return
        if not datos.telegram_token() or "TU_TOKEN" in datos.telegram_token():
            QMessageBox.warning(self,"Token faltante","Configura tu token de Telegram en la Configuración General."); return
        if not TelegramBotWorker.BOT_DIR.exists():
            QMessageBox.warning(self,"Carpeta no encontrada",f"No encontré la carpeta del bot en:\n{TelegramBotWorker.BOT_DIR}"); return
        self._tg_worker = TelegramBotWorker(); self._tg_worker.log_signal.connect(self._on_telegram_log); self._tg_worker.stopped.connect(self._on_telegram_stopped)
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
        meta = PROVIDER_META[self.current_provider]
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
        self.settings_panel = SettingsPanel(self.config); self.settings_panel.saved.connect(self._on_keys_saved); layout.addWidget(self.settings_panel)
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
        wicon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lune_icon.png")
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
        self.current_provider = provider_id
        for pid, tab in self.provider_tabs.items(): tab.set_active(pid==provider_id)
        meta = PROVIDER_META[provider_id]
        self._style_topbar_icon(meta)
        self.topbar_title.setText(meta["label"])
        self.topbar_title.setStyleSheet(f"color:{meta['color']};background:transparent;letter-spacing:1px;")
        self.topbar_desc.setText("·  "+meta["desc"])
        self._update_send_btn_color(); self.stack.setCurrentIndex(0)

    def _update_send_btn_color(self):
        c = PROVIDER_META[self.current_provider]["color"]
        d = PROVIDER_META[self.current_provider]["dark"]
        self.send_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {d},stop:1 {c});color:{COLORS['bg']};border:none;border-radius:3px;}}QPushButton:hover{{background:{c};}}QPushButton:disabled{{background:{COLORS['surface3']};color:{COLORS['text_dim']};}}")
        apply_glow(self.send_btn, c, radius=22, alpha=150)

    # ── SEND / RECEIVE / STOP ─────────────────────────────────────────────────

    def _stop_generation(self):
        if self.ai_worker and self.ai_worker.isRunning():
            if self.current_provider in self.ai_manager.providers:
                self.ai_manager.providers[self.current_provider].cancel_flag = True

            # El hilo tarda un momento en cortar y luego emite response_ready.
            # Sin esta bandera, _on_response pisaba el estado con "LISTO" y
            # parecía que la interrupción no había funcionado.
            self._cancelado = True
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

    def _send_message(self):
        text = self.input_field.text().strip()
        adjuntos_envio = list(self._adjuntos)
        # Adjuntar un archivo sin escribir nada es una petición implícita
        if not text and adjuntos_envio:
            text = "Échale un ojo a esto, por favor."
        if not text:
            return
        self.stack.setCurrentIndex(0)

        bubble = MessageBubble(text, is_user=True, provider_id=self.current_provider,
                               markdown=False, adjuntos=adjuntos_envio)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.input_field.clear()
        self._adjuntos = []
        self._refrescar_adjuntos()
        self._guardar_turno("user", text, adjuntos=adjuntos_envio)

        # Con archivos adjuntos siempre va a la IA: ni la memoria ni el banco
        # de respuestas saben qué hacer con un PDF.
        if not adjuntos_envio:
            respuesta_memoria = self.memoria.procesar_mensaje_usuario(text)
            if respuesta_memoria:
                self._burbuja_bot(respuesta_memoria)
                self._guardar_turno("assistant", respuesta_memoria)
                self.lune_face.set_state("happy", auto_revert_ms=4000); self._scroll_bottom(); return

            # Banco de respuestas instantáneas (saludos, gracias, hora…) — sin IA
            if self.config.feature("respuestas_predeterminadas", True):
                self.banco.set_nombre_usuario(self.memoria.get_nombre_usuario())
                rta_rapida = self.banco.responder(text)
                if rta_rapida:
                    self._burbuja_bot(rta_rapida)
                    self._guardar_turno("assistant", rta_rapida)
                    self.lune_face.set_state("happy", auto_revert_ms=4000)
                    self.voice.speak(rta_rapida); self._scroll_bottom(); return

            tool_result = self.tools.detectar_y_ejecutar(text)
            if tool_result:
                icono = "✓" if tool_result.ok else "✕"
                msg = f"{icono} {tool_result.mensaje}"
                self._burbuja_bot(msg)
                self._guardar_turno("assistant", msg)
                self.lune_face.set_state("happy" if tool_result.ok else "error", auto_revert_ms=5000)
                self._scroll_bottom(); return

        self.input_field.setEnabled(False)
        self.send_btn.hide(); self.stop_btn.show()

        if self.current_provider in self.ai_manager.providers:
            self.ai_manager.providers[self.current_provider].cancel_flag = False

        self._set_status("PROCESANDO", COLORS["warning"]); self.lune_face.set_state("thinking")

        self._typing_indicator = TypingIndicator(self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, self._typing_indicator)
        self._scroll_bottom()

        self._cancelado = False
        contexto_memoria = self.memoria.obtener_contexto_para_prompt()
        # El texto de los documentos va en el system prompt; las imágenes van
        # por el canal multimodal del proveedor.
        contexto_archivos = adj.bloque_para_prompt(adjuntos_envio)
        self.ai_worker = AIWorker(
            self.ai_manager, text, self.current_provider,
            extra_context=contexto_memoria + contexto_archivos,
            permitir_acciones=self.config.feature("acciones_ia", True),
            imagenes=adj.imagenes_base64(adjuntos_envio),
        )
        if self.config.feature("streaming_tokens", True):
            self.ai_worker.token_received.connect(self._on_token)
        self.ai_worker.response_ready.connect(self._on_response)
        self.ai_worker.error_occurred.connect(self._on_error)
        self.ai_worker.start()

    def _on_token(self, partial):
        # En streaming se pinta texto plano: reconstruir los widgets de markdown
        # 16 veces por segundo sería carísimo. Al terminar se formatea de golpe.
        if self._typing_indicator and self._current_bubble is None:
            self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
            self._current_bubble = MessageBubble(
                partial + " ▋", is_user=False, provider_id=self.current_provider,
                markdown=self.config.feature("markdown", True))
            self.messages_layout.insertWidget(self.messages_layout.count()-1, self._current_bubble)
            self.lune_face.set_state("typing")
        elif self._current_bubble:
            self._current_bubble.update_text(partial + " ▋", streaming=True)
        self._scroll_bottom()

    def _on_response(self, response):
        respuesta_limpia, acciones_ia = self.tools.parsear_respuesta_ia(response)

        if self._typing_indicator: self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
        if self._current_bubble:
            # streaming=False → aquí sí se renderiza el markdown
            self._current_bubble.update_text(respuesta_limpia)
            burbuja = self._current_bubble
        else:
            # Sin streaming: creamos la burbuja con la respuesta completa
            burbuja = MessageBubble(respuesta_limpia, is_user=False, provider_id=self.current_provider,
                                    markdown=self.config.feature("markdown", True))
            self.messages_layout.insertWidget(self.messages_layout.count()-1, burbuja)
        self._current_bubble = None

        uso = self.ai_manager.uso(self.current_provider)
        if uso and self.config.feature("contador_tokens", True):
            burbuja.set_pie(self._texto_uso(uso))
        self._guardar_turno("assistant", respuesta_limpia, uso=uso)

        self.stop_btn.hide(); self.send_btn.show()
        if not getattr(self, "_cancelado", False):
            self._set_status("LISTO", COLORS["success"])
        self.input_field.setEnabled(True); self.input_field.setFocus()

        # Las acciones que pide la IA (abrir webs, lanzar apps) solo se ejecutan
        # si el usuario las tiene permitidas en Configuración → Rendimiento.
        if self.config.feature("acciones_ia", True) and not getattr(self, "_cancelado", False):
            for accion in acciones_ia:
                herramienta = accion.pop("herramienta", None)
                if herramienta:
                    result = self.tools.ejecutar(herramienta, **accion)
                    tool_bubble = MessageBubble(f"{'✓' if result.ok else '✕'} {result.mensaje}", is_user=False, provider_id=self.current_provider)
                    self.messages_layout.insertWidget(self.messages_layout.count()-1, tool_bubble)

        self.memoria.procesar_respuesta_lune(respuesta_limpia)
        emotion = detect_emotion(respuesta_limpia)
        self.lune_face.set_state(emotion, auto_revert_ms=6000)
        self.voice.speak(respuesta_limpia)
        self._scroll_bottom()

    def _on_error(self, error):
        if self._typing_indicator: self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
        if self._current_bubble: self._current_bubble.update_text(f"✕ {error}")
        else:
            err_bubble = MessageBubble(f"✕ {error}", is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, err_bubble)
        self._current_bubble = None
        self.stop_btn.hide(); self.send_btn.show()
        self._set_status("ERROR", COLORS["error"]); self.input_field.setEnabled(True); self.input_field.setFocus()
        self.lune_face.set_state("error", auto_revert_ms=8000)
        self._scroll_bottom()

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
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _set_status(self, text, color):
        self.status_label.setText(text); self.status_dot.setStyleSheet(f"color:{color};background:transparent;")

    def _toggle_voice(self):
        enabled = self.voice.toggle()
        self._voice_btn.setText(f" VOZ: {'ON' if enabled else 'OFF'}")
        col = COLORS["accent"] if enabled else COLORS["text_muted"]
        self._voice_btn.setIcon(icon("volume" if enabled else "volume_off", col, 18))

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

    def _toggle_historial(self):
        if self.stack.currentIndex() != 4:
            self.historial_panel.refrescar()
            self.stack.setCurrentIndex(4)
        else:
            self.stack.setCurrentIndex(0)

    def _switch_character(self, nombre):
        """Cambia el personaje activo: recarga prompt, limpia historial y saluda."""
        personajes.set_activo(nombre)
        datos.invalidar()
        self.ai_manager.clear_history()

        p = personajes.get_activo()
        # Cambiar avatar pack si el personaje define uno
        pack = p.get("avatar_pack", "default")
        lune_face.set_active_pack(pack); self.config.set("avatar", "pack", pack)

        # Refrescar marca, banco y bienvenida
        self.sidebar_t1.setText(self._marca_sidebar(nombre))
        self.banco = BancoRespuestas(nombre_asistente=nombre, nombre_usuario=self.memoria.get_nombre_usuario())

        # Limpiar chat y mostrar saludo del personaje
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._add_welcome()
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
        # datos.guardar() ya invalidó la caché, así que esto lee lo recién escrito.
        self.ai_manager.reload_provider()
        self.stack.setCurrentIndex(0)

        personaje = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune"))
        nombre_bot = personaje.get("nombre", "Lune")
        self.sidebar_t1.setText(self._marca_sidebar(nombre_bot))
        self.banco = BancoRespuestas(nombre_asistente=nombre_bot,
                                     nombre_usuario=self.memoria.get_nombre_usuario())
        if hasattr(self, 'welcome_t1'):
            self.welcome_t1.setText(nombre_bot.upper())
            nombre = self.memoria.get_nombre_usuario()
            saludo = personaje.get("fraseInicial") or (
                f"De vuelta, {nombre}. Dime qué necesitas." if nombre else "Lune en línea. Dime qué necesitas.")
            self.welcome_t2.setText(saludo)

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
    def _build_tray(self):
        if not self.config.feature("minimizar_a_bandeja", True):
            return
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

    def closeEvent(self, event):
        # Minimizar a la bandeja en vez de salir (si está activo y hay bandeja)
        if self.tray is not None and not self._quit_real:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Lune CD", "Sigo aquí en la bandeja. Doble clic para abrirme.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            return

        if hasattr(self, "memoria"):
            stats = self.memoria.get_stats()
            resumen = f"Sesión del {datetime.now().strftime('%d/%m/%Y')}. Mensajes intercambiados hoy: {stats.get('total_mensajes', 0)}."
            self.memoria.cerrar_sesion(resumen)

        # Cortar el dictado y volcar la conversación antes de irnos
        if self._grabadora is not None:
            self._grabadora.cancelar()
        if hasattr(self, "chats"):
            self.chats.guardar()
        if hasattr(self, "_timer_estado"):
            self._timer_estado.stop()
        if self._hub_cliente is not None:
            self._hub_cliente.detener()
        if self._hub_en_hilo is not None:
            self._hub_en_hilo.detener()

        if hasattr(self,"lune_face") and self.lune_face._player: self.lune_face._player.stop()
        if hasattr(self,"_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            self._tg_worker.stop(); self._tg_worker.wait(3000)
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────
def _cargar_fuentes():
    """Registra las fuentes Shibuya Punk empaquetadas en fonts/ para esta app."""
    import glob
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
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


def _ya_hay_una_instancia() -> bool:
    """
    ¿Hay otra Lune corriendo?

    Se lanza desde un .vbs y desde la carpeta de Inicio, así que abrirla dos
    veces es facilísimo (doble clic, o arrancar a mano lo que ya estaba). En vez
    de tener dos Lunes peleándose por datos.json, memoria.json y el mismo puerto
    del bot, la segunda avisa a la primera y se va.
    """
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(CLAVE_INSTANCIA)
    if socket.waitForConnected(300):
        # Ya hay una viva: le pedimos que se muestre y nos retiramos.
        socket.write(b"mostrar")
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True

    # Un servidor huérfano (de un cierre a lo bruto) bloquearía el arranque.
    QLocalServer.removeServer(CLAVE_INSTANCIA)
    servidor = QLocalServer()
    servidor.listen(CLAVE_INSTANCIA)
    # Referencia global para que no lo recoja el recolector de basura
    globals()["_servidor_instancia"] = servidor
    return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")

    if _ya_hay_una_instancia():
        log_info("Lune ya estaba abierta: no abro una segunda")
        return

    # Tipografía Shibuya Punk: cargar las fuentes empaquetadas en fonts/.
    _cargar_fuentes()
    # Si alguna no estuviera, Qt la sustituye por una del sistema (fallback).
    for familia, fallback in FONT_FALLBACKS.items():
        QFont.insertSubstitution(familia, fallback)
    app.setFont(QFont(FONT_BODY, 10))

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"LuneCD.v{APP_VERSION}")
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    for ext in ("ico","png"):
        icon_path = os.path.join(base_dir, f"lune_icon.{ext}")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,     QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base,       QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text,       QColor(COLORS["text"]))
    app.setPalette(palette)

    # La ventana principal la crea y la conserva main(), no la pantalla de
    # inicio: así nunca hay dos ventanas vivas a la vez y la referencia no
    # depende de un objeto que se está destruyendo.
    ventanas = {}

    def abrir_principal():
        if "principal" in ventanas:
            return
        ventana = LuneCDWindow()
        ventanas["principal"] = ventana
        _mostrar_de_verdad(ventana)

        # Si intentas abrir Lune otra vez, la que ya está se trae al frente.
        servidor = globals().get("_servidor_instancia")
        if servidor is not None:
            servidor.newConnection.connect(
                lambda: (ventana.showNormal(), ventana.raise_(), ventana.activateWindow())
            )

    ventana_inicio = PantallaInicio(al_terminar=abrir_principal)
    ventanas["inicio"] = ventana_inicio
    _mostrar_de_verdad(ventana_inicio)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
