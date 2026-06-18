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
    QApplication, QMessageBox, QStackedWidget,
    QSystemTrayIcon, QMenu, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QAction, QPixmap, QFontDatabase

from config import Config
from ai_manager import AIManager
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
from splash import PantallaInicio

logger = Logger()


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
        log_info(f"Lune CD v{APP_VERSION} iniciado")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle("Lune CD · IA Activa")
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
        self.sidebar_t1 = QLabel(f"<span style='color:{COLORS['text']};'>{nombre_bot.upper()} </span><span style='color:{COLORS['accent']};'>CD</span>")
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

        layout.addSpacing(16)  # aire entre la mascota y el botón de Telegram

        # ── TELEGRAM ──
        self.telegram_btn = QPushButton("  CONTINUAR EN TELEGRAM")
        self.telegram_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.telegram_btn.setFont(QFont(FONT_DISPLAY,10,QFont.Weight.Bold)); self.telegram_btn.setFixedHeight(42)
        self._set_telegram_btn_style(False)
        self.telegram_btn.clicked.connect(self._toggle_telegram)
        layout.addWidget(self.telegram_btn)
        self.telegram_status = QLabel("")
        self.telegram_status.setFont(QFont(FONT_MONO,8)); self.telegram_status.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;padding-left:8px;")
        self.telegram_status.setWordWrap(True)
        layout.addWidget(self.telegram_status)

        # ── ACCIONES: grid de tiles ──
        layout.addWidget(self._overline("// ACCIONES"))
        grid = QGridLayout(); grid.setSpacing(7)
        self._keys_btn = self._tile_btn("AJUSTES", "gear"); self._keys_btn.clicked.connect(self._toggle_keys_panel)
        opt_btn  = self._tile_btn("OPTIMIZAR", "bolt");  opt_btn.clicked.connect(self._toggle_optimizer)
        mem_btn  = self._tile_btn("MEMORIA", "brain");    mem_btn.clicked.connect(self._show_memoria)
        tools_btn= self._tile_btn("TOOLS", "tool");      tools_btn.clicked.connect(self._show_tools)
        grid.addWidget(self._keys_btn, 0, 0); grid.addWidget(opt_btn, 0, 1)
        grid.addWidget(mem_btn, 1, 0); grid.addWidget(tools_btn, 1, 1)
        if self.voice.available:
            self._voice_btn = self._tile_btn("VOZ: OFF", "volume_off"); self._voice_btn.clicked.connect(self._toggle_voice)
            grid.addWidget(self._voice_btn, 2, 0, 1, 2)
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

    def _set_telegram_btn_style(self, active):
        self.telegram_btn.setIconSize(QSize(15, 15))
        if active:
            self.telegram_btn.setText("  TELEGRAM · ACTIVO")
            self.telegram_btn.setIcon(icon("telegram", "#FFFFFF", 15))
            self.telegram_btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['telegram_dark']},stop:1 {COLORS['telegram']});color:white;border:none;border-radius:3px;text-align:left;padding-left:12px;font-weight:bold;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['telegram']};}}")
        else:
            self.telegram_btn.setText("  CONTINUAR EN TELEGRAM")
            self.telegram_btn.setIcon(icon("telegram", COLORS["telegram"], 15))
            self.telegram_btn.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['telegram']};border:2px solid {COLORS['telegram']}55;border-radius:3px;text-align:left;padding-left:12px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['telegram_dark']}44;border-color:{COLORS['telegram']};}}")

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
            self._set_telegram_btn_style(False); self.telegram_status.setText(""); return
        if not datos.telegram_token() or "TU_TOKEN" in datos.telegram_token():
            QMessageBox.warning(self,"Token faltante","Configura tu token de Telegram en la Configuración General."); return
        if not TelegramBotWorker.BOT_DIR.exists():
            QMessageBox.warning(self,"Carpeta no encontrada",f"No encontré la carpeta del bot en:\n{TelegramBotWorker.BOT_DIR}"); return
        self._tg_worker = TelegramBotWorker(); self._tg_worker.log_signal.connect(self._on_telegram_log); self._tg_worker.stopped.connect(self._on_telegram_stopped)
        self._tg_worker.start(); self._set_telegram_btn_style(True); self.telegram_status.setText("Iniciando...")

    def _on_telegram_log(self, line):
        log_info(f"[Telegram] {line}")
        if any(k in line for k in ["Bot iniciado","iniciado","Modelo:","Error"]): self.telegram_status.setText(line[:60])

    def _on_telegram_stopped(self):
        self._set_telegram_btn_style(False); self.telegram_status.setText("Bot detenido")
        QTimer.singleShot(3000, lambda: self.telegram_status.setText(""))

    # ── MAIN AREA ─────────────────────────────────────────────────────────────
    def _build_main(self):
        main = QFrame(); main.setStyleSheet(f"QFrame{{background:{COLORS['bg']};border:none;}}")
        layout = QVBoxLayout(main); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget(); self.stack.setStyleSheet("QStackedWidget{background:transparent;}")
        self.stack.addWidget(self._build_chat_page())       # 0
        self.stack.addWidget(self._build_keys_page())       # 1
        self.stack.addWidget(self._build_optimizer_page())  # 2
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

    def _build_input_bar(self):
        bar = QFrame(); bar.setFixedHeight(88)
        bar.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border-top:2px solid {COLORS['border']};}}")
        layout = QHBoxLayout(bar); layout.setContentsMargins(20,20,20,20); layout.setSpacing(10)

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

        layout.addWidget(glyph); layout.addWidget(self.input_field,1); layout.addWidget(self.send_btn); layout.addWidget(self.stop_btn)
        return bar

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

            self._set_status("INTERRUMPIDO", COLORS["warning"])
            self.lune_face.set_state("normal")

            self.stop_btn.hide(); self.send_btn.show()
            self.input_field.setEnabled(True); self.input_field.setFocus()

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text: return
        self.stack.setCurrentIndex(0)

        bubble = MessageBubble(text, is_user=True, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self.input_field.clear()

        respuesta_memoria = self.memoria.procesar_mensaje_usuario(text)
        if respuesta_memoria:
            bot_bubble = MessageBubble(respuesta_memoria, is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, bot_bubble)
            self.lune_face.set_state("happy", auto_revert_ms=4000); self._scroll_bottom(); return

        # Banco de respuestas instantáneas (saludos, gracias, hora, chistes…) — sin IA
        if self.config.feature("respuestas_predeterminadas", True):
            self.banco.set_nombre_usuario(self.memoria.get_nombre_usuario())
            rta_rapida = self.banco.responder(text)
            if rta_rapida:
                bot_bubble = MessageBubble(rta_rapida, is_user=False, provider_id=self.current_provider)
                self.messages_layout.insertWidget(self.messages_layout.count()-1, bot_bubble)
                self.lune_face.set_state("happy", auto_revert_ms=4000)
                self.voice.speak(rta_rapida); self._scroll_bottom(); return

        tool_result = self.tools.detectar_y_ejecutar(text)
        if tool_result:
            icono = "✓" if tool_result.ok else "✕"
            msg = f"{icono} {tool_result.mensaje}"
            bot_bubble = MessageBubble(msg, is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, bot_bubble)
            self.lune_face.set_state("happy" if tool_result.ok else "error", auto_revert_ms=5000); self._scroll_bottom(); return

        self.input_field.setEnabled(False)
        self.send_btn.hide(); self.stop_btn.show()

        if self.current_provider in self.ai_manager.providers:
            self.ai_manager.providers[self.current_provider].cancel_flag = False

        self._set_status("PROCESANDO", COLORS["warning"]); self.lune_face.set_state("thinking")

        self._typing_indicator = TypingIndicator(self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, self._typing_indicator)
        self._scroll_bottom()

        contexto_memoria = self.memoria.obtener_contexto_para_prompt()
        self.ai_worker = AIWorker(self.ai_manager, text, self.current_provider, extra_context=contexto_memoria)
        if self.config.feature("streaming_tokens", True):
            self.ai_worker.token_received.connect(self._on_token)
        self.ai_worker.response_ready.connect(self._on_response)
        self.ai_worker.error_occurred.connect(self._on_error)
        self.ai_worker.start()

    def _on_token(self, partial):
        if self._typing_indicator and self._current_bubble is None:
            self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
            self._current_bubble = MessageBubble(partial+" ▋", is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, self._current_bubble)
            self.lune_face.set_state("typing")
        elif self._current_bubble:
            self._current_bubble.update_text(partial+" ▋")
        self._scroll_bottom()

    def _on_response(self, response):
        respuesta_limpia, acciones_ia = self.tools.parsear_respuesta_ia(response)

        if self._typing_indicator: self._typing_indicator.stop(); self._typing_indicator.deleteLater(); self._typing_indicator = None
        if self._current_bubble:
            self._current_bubble.update_text(respuesta_limpia)
        else:
            # Sin streaming: creamos la burbuja con la respuesta completa
            bubble = MessageBubble(respuesta_limpia, is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count()-1, bubble)
        self._current_bubble = None

        self.stop_btn.hide(); self.send_btn.show()
        self._set_status("LISTO", COLORS["success"]); self.input_field.setEnabled(True); self.input_field.setFocus()

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

    def _on_keys_saved(self):
        self.ai_manager.reload_provider()
        self.stack.setCurrentIndex(0)

        personaje = datos.get_personaje(datos.get_bot().get("personaje_default", "Lune"))
        self.sidebar_t1.setText(personaje.get("nombre", "Lune AI"))
        if hasattr(self, 'welcome_t1'):
            self.welcome_t1.setText(personaje.get("nombre", "Lune AI"))
            nombre = self.memoria.get_nombre_usuario()
            saludo = personaje.get("fraseInicial", f"De vuelta, {nombre}. Dime qué necesitas." if nombre else "Lune en línea. Dime qué necesitas.")
            self.welcome_t2.setText(saludo)

        QMessageBox.information(self,"Guardado","Configuración guardada correctamente.")

    def _clear_chat(self):
        reply = QMessageBox.question(self,"Limpiar chat","¿Eliminar todos los mensajes?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            while self.messages_layout.count() > 1:
                item = self.messages_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            self.ai_manager.clear_history()
            self._add_welcome(); self.lune_face.set_state("normal")

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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")

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

    # Iniciamos con la pantalla de bienvenida (abre LuneCDWindow al terminar)
    ventana_inicio = PantallaInicio()
    ventana_inicio.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
