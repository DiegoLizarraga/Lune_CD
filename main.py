import sys
import asyncio
import threading
import io
import re
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QMenu, QTextEdit, QStackedWidget,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QFont, QCursor, QColor, QPainter, QPainterPath, QLinearGradient, QPalette

from config import Config
from ai_manager import AIManager
from utils import Logger, log_info, log_error

logger = Logger()

# ─────────────────────────────────────────────────────────────────────────────
#  PALETA DE COLORES
# ─────────────────────────────────────────────────────────────────────────────
COLORS = {
    "bg":           "#0e0f14",
    "surface":      "#161820",
    "surface2":     "#1e2130",
    "surface3":     "#252840",
    "border":       "#2a2d45",
    "border2":      "#353860",
    "text":         "#e8eaf6",
    "text_muted":   "#7b7fa8",
    "text_dim":     "#4a4e72",

    # Providers
    "char_ai":      "#f06292",
    "char_ai_dark": "#880e4f",
    "deepseek":     "#4fc3f7",
    "deepseek_dark":"#01579b",
    "claude":       "#ff9e64",
    "claude_dark":  "#b44800",
    "ollama":       "#69db7c",
    "ollama_dark":  "#1b5e20",

    "accent":       "#7c6af7",
    "accent2":      "#a78bfa",
    "success":      "#69db7c",
    "error":        "#ff6b6b",
    "warning":      "#ffd166",

    "user_bubble":  "#2a2d4a",
    "bot_bubble":   "#1e2035",
    "scrollbar":    "#2a2d45",
}

PROVIDER_META = {
    "character_ai": {
        "label": "Character.AI",
        "icon": "🎭",
        "color": COLORS["char_ai"],
        "dark": COLORS["char_ai_dark"],
        "desc": "Personajes y roles",
        "system": "Eres un asistente amigable y creativo. Responde en español.",
    },
    "deepseek": {
        "label": "DeepSeek",
        "icon": "🔬",
        "color": COLORS["deepseek"],
        "dark": COLORS["deepseek_dark"],
        "desc": "Razonamiento avanzado",
        "system": "Eres un asistente de IA altamente capaz, experto en razonamiento lógico y análisis. Responde en español.",
    },
    "claude": {
        "label": "Claude",
        "icon": "✦",
        "color": COLORS["claude"],
        "dark": COLORS["claude_dark"],
        "desc": "Anthropic · Preciso",
        "system": "Eres Claude, un asistente de IA creado por Anthropic. Responde en español de forma clara y útil.",
    },
    "ollama": {
        "label": "Ollama",
        "icon": "🦙",
        "color": COLORS["ollama"],
        "dark": COLORS["ollama_dark"],
        "desc": "Modelo local",
        "system": (
            "Eres Lune, una asistente virtual inteligente y amigable. "
            "Eres experta en escribir, investigar y automatizar tareas. "
            "Responde de manera clara, concisa y útil."
        ),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  VOZ (gTTS + pygame)
# ─────────────────────────────────────────────────────────────────────────────

class VoiceEngine:
    def __init__(self):
        self._enabled = False
        self._lock = threading.Lock()
        self._available = False
        self._init_engine()

    def _init_engine(self):
        try:
            from gtts import gTTS
            import pygame
            pygame.mixer.init()
            self._available = True
        except Exception as e:
            log_error(f"gTTS/pygame no disponible: {e}")

    def speak(self, text: str):
        if not self._enabled or not self._available:
            return
        clean = self._clean_text(text)
        if not clean.strip():
            return
        threading.Thread(target=self._speak_blocking, args=(clean,), daemon=True).start()

    def _speak_blocking(self, text: str):
        with self._lock:
            try:
                from gtts import gTTS
                import pygame
                tts = gTTS(text, lang="es")
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                pygame.mixer.music.load(fp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    threading.Event().wait(0.1)
            except Exception as e:
                log_error(f"Error de voz: {e}")

    def _clean_text(self, text: str) -> str:
        emoji_pattern = re.compile(
            "[" u"\U0001F600-\U0001F64F" u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF" u"\U0001F1E0-\U0001F1FF"
            u"\U00002702-\U000027B0" u"\U000024C2-\U0001F251" "]+",
            flags=re.UNICODE,
        )
        return emoji_pattern.sub("", text).replace("▋", "").replace("❌", "").replace("✅", "").strip()

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    @property
    def available(self):
        return self._available

    @property
    def enabled(self):
        return self._enabled


# ─────────────────────────────────────────────────────────────────────────────
#  PROVIDER TAB BUTTON
# ─────────────────────────────────────────────────────────────────────────────

class ProviderTab(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, provider_id: str, meta: dict, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.meta = meta
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self._build()
        self._apply_style(False)

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self.icon_lbl = QLabel(self.meta["icon"])
        self.icon_lbl.setFont(QFont("Segoe UI Emoji", 18))
        self.icon_lbl.setFixedWidth(30)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        self.name_lbl = QLabel(self.meta["label"])
        self.name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.desc_lbl = QLabel(self.meta["desc"])
        self.desc_lbl.setFont(QFont("Segoe UI", 9))

        text_col.addWidget(self.name_lbl)
        text_col.addWidget(self.desc_lbl)

        layout.addWidget(self.icon_lbl)
        layout.addLayout(text_col, 1)

    def _apply_style(self, active: bool):
        c = self.meta["color"]
        d = self.meta["dark"]
        if active:
            self.setStyleSheet(f"""
                ProviderTab {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {d}88, stop:1 {d}22);
                    border-left: 3px solid {c};
                    border-radius: 10px;
                }}
            """)
            self.name_lbl.setStyleSheet(f"color: {c}; background: transparent;")
            self.desc_lbl.setStyleSheet(f"color: {c}aa; background: transparent;")
            self.icon_lbl.setStyleSheet("background: transparent;")
        else:
            self.setStyleSheet(f"""
                ProviderTab {{
                    background: transparent;
                    border-left: 3px solid transparent;
                    border-radius: 10px;
                }}
                ProviderTab:hover {{
                    background: {COLORS['surface2']};
                }}
            """)
            self.name_lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
            self.desc_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
            self.icon_lbl.setStyleSheet("background: transparent;")

    def set_active(self, active: bool):
        self._active = active
        self._apply_style(active)

    def mousePressEvent(self, event):
        self.clicked.emit(self.provider_id)


# ─────────────────────────────────────────────────────────────────────────────
#  MESSAGE BUBBLE
# ─────────────────────────────────────────────────────────────────────────────

class MessageBubble(QFrame):
    def __init__(self, text: str, is_user: bool, provider_id: str = "ollama", parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.provider_id = provider_id
        self._build(text)

    def _build(self, text: str):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 4, 12, 4)
        outer.setSpacing(10)

        meta = PROVIDER_META.get(self.provider_id, PROVIDER_META["ollama"])
        color = meta["color"]

        if self.is_user:
            outer.addStretch()
            bubble = QFrame()
            bubble.setStyleSheet(f"""
                QFrame {{
                    background: {COLORS['user_bubble']};
                    border-radius: 16px;
                    border-bottom-right-radius: 4px;
                    border: 1px solid {COLORS['border2']};
                }}
            """)
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(14, 10, 14, 10)
            bubble_layout.setSpacing(4)

            self.text_lbl = QLabel(text)
            self.text_lbl.setWordWrap(True)
            self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont("Segoe UI", 11))
            self.text_lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
            self.text_lbl.setMaximumWidth(520)

            bubble_layout.addWidget(self.text_lbl)

            ts = QLabel(datetime.now().strftime("%H:%M"))
            ts.setFont(QFont("Segoe UI", 8))
            ts.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
            ts.setAlignment(Qt.AlignmentFlag.AlignRight)
            bubble_layout.addWidget(ts)

            outer.addWidget(bubble)

        else:
            # Avatar
            avatar = QLabel(meta["icon"])
            avatar.setFixedSize(36, 36)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFont(QFont("Segoe UI Emoji", 15))
            avatar.setStyleSheet(f"""
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {meta['dark']}, stop:1 {color}44);
                border-radius: 10px;
                border: 1px solid {color}55;
            """)
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

            bubble = QFrame()
            bubble.setStyleSheet(f"""
                QFrame {{
                    background: {COLORS['bot_bubble']};
                    border-radius: 16px;
                    border-top-left-radius: 4px;
                    border: 1px solid {COLORS['border']};
                }}
            """)
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(14, 10, 14, 10)
            bubble_layout.setSpacing(4)

            sender = QLabel(meta["label"])
            sender.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            sender.setStyleSheet(f"color: {color}; background: transparent;")
            bubble_layout.addWidget(sender)

            self.text_lbl = QLabel(text)
            self.text_lbl.setWordWrap(True)
            self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont("Segoe UI", 11))
            self.text_lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
            self.text_lbl.setMaximumWidth(520)
            bubble_layout.addWidget(self.text_lbl)

            ts = QLabel(datetime.now().strftime("%H:%M"))
            ts.setFont(QFont("Segoe UI", 8))
            ts.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
            bubble_layout.addWidget(ts)

            outer.addWidget(bubble)
            outer.addStretch()

    def update_text(self, text: str):
        self.text_lbl.setText(text)


# ─────────────────────────────────────────────────────────────────────────────
#  TYPING INDICATOR
# ─────────────────────────────────────────────────────────────────────────────

class TypingIndicator(QFrame):
    def __init__(self, provider_id: str = "ollama", parent=None):
        super().__init__(parent)
        meta = PROVIDER_META.get(provider_id, PROVIDER_META["ollama"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(10)

        avatar = QLabel(meta["icon"])
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFont(QFont("Segoe UI Emoji", 15))
        avatar.setStyleSheet(f"""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 {meta['dark']}, stop:1 {meta['color']}44);
            border-radius: 10px;
            border: 1px solid {meta['color']}55;
        """)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        dots_frame = QFrame()
        dots_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bot_bubble']};
                border-radius: 16px;
                border-top-left-radius: 4px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        dots_layout = QHBoxLayout(dots_frame)
        dots_layout.setContentsMargins(16, 12, 16, 12)
        dots_layout.setSpacing(6)

        self.dots = []
        for i in range(3):
            dot = QLabel("●")
            dot.setFont(QFont("Segoe UI", 9))
            dot.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
            dots_layout.addWidget(dot)
            self.dots.append(dot)

        layout.addWidget(dots_frame)
        layout.addStretch()

        self._dot_idx = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(300)

    def _animate(self):
        c = PROVIDER_META.get("ollama", {}).get("color", COLORS["accent"])
        for i, dot in enumerate(self.dots):
            if i == self._dot_idx:
                dot.setStyleSheet(f"color: {c}; background: transparent;")
            else:
                dot.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        self._dot_idx = (self._dot_idx + 1) % 3

    def stop(self):
        self._timer.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  AI WORKER
# ─────────────────────────────────────────────────────────────────────────────

class AIWorker(QThread):
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ai_manager, message: str, provider_id: str):
        super().__init__()
        self.ai_manager = ai_manager
        self.message = message
        self.provider_id = provider_id
        self._buffer = ""

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            system_prompt = PROVIDER_META[self.provider_id]["system"]

            def on_token(token):
                self._buffer += token
                self.token_received.emit(self._buffer)

            response = loop.run_until_complete(
                self.ai_manager.chat(
                    self.message,
                    system_prompt,
                    provider=self.provider_id,
                    on_token=on_token,
                )
            )
            self.response_ready.emit(response or "Sin respuesta")
        except Exception as e:
            log_error(f"Error en AIWorker: {e}")
            self.error_occurred.emit(f"Error: {e}")
        finally:
            if "loop" in dir():
                loop.close()


# ─────────────────────────────────────────────────────────────────────────────
#  API KEY EDITOR PANEL
# ─────────────────────────────────────────────────────────────────────────────

class ApiKeyPanel(QFrame):
    saved = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border-radius: 16px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("🔑  Configurar API Keys")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("Las keys se guardan en api_keys.json (no en el código).")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
        layout.addWidget(subtitle)

        self.fields: dict[str, QLineEdit] = {}

        providers_fields = [
            ("character_ai", "🎭  Character.AI Token", "api_key"),
            ("deepseek",     "🔬  DeepSeek API Key",   "api_key"),
            ("claude",       "✦   Claude API Key",     "api_key"),
            ("ollama",       "🦙  Ollama URL",          "url"),
            ("ollama",       "🦙  Ollama Modelo",       "model"),
        ]

        for (provider, label_text, field) in providers_fields:
            row = QVBoxLayout()
            row.setSpacing(4)

            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")

            inp = QLineEdit()
            key = f"{provider}_{field}"
            current = self.config.get_key(provider, field)
            inp.setText(current)
            inp.setEchoMode(
                QLineEdit.EchoMode.Password
                if field == "api_key"
                else QLineEdit.EchoMode.Normal
            )
            inp.setPlaceholderText(f"Ingresa {label_text.split('  ')[1]}…")
            inp.setFont(QFont("Segoe UI", 11))
            inp.setStyleSheet(f"""
                QLineEdit {{
                    background: {COLORS['surface2']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: {COLORS['text']};
                }}
                QLineEdit:focus {{
                    border: 1px solid {COLORS['accent']};
                }}
            """)
            self.fields[key] = inp
            row.addWidget(lbl)
            row.addWidget(inp)
            layout.addLayout(row)

        save_btn = QPushButton("💾  Guardar Keys")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        save_btn.setFixedHeight(44)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {COLORS['accent']}, stop:1 {COLORS['accent2']});
                color: white;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {COLORS['accent2']}, stop:1 {COLORS['accent']});
            }}
        """)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch()

    def _save(self):
        for key, inp in self.fields.items():
            parts = key.rsplit("_", 1)
            # map key back to provider/field
            # stored as "provider_field"
            pass

        # Re-map properly
        provider_field_map = {
            "character_ai_api_key": ("character_ai", "api_key"),
            "deepseek_api_key":     ("deepseek",     "api_key"),
            "claude_api_key":       ("claude",        "api_key"),
            "ollama_url":           ("ollama",        "url"),
            "ollama_model":         ("ollama",        "model"),
        }
        for key, (provider, field) in provider_field_map.items():
            if key in self.fields:
                self.config.set_key(provider, field, self.fields[key].text().strip())

        self.saved.emit()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────

class LuneCDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.config = Config()
            self.ai_manager = AIManager(self.config)
            self.voice = VoiceEngine()
            self.current_provider = "ollama"
            self.ai_worker = None
            self._current_bubble = None
            self._typing_indicator = None
            log_info("Aplicación iniciada")
            self._init_ui()
        except Exception as e:
            log_error(f"Error al inicializar: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
            sys.exit(1)

    # ── UI BUILD ─────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle("🌙 Lune CD v6 · Multi-IA")
        self.setGeometry(80, 60, 1200, 800)
        self.setMinimumSize(900, 640)
        self.setStyleSheet(f"QMainWindow, QWidget {{ background: {COLORS['bg']}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)

    # ── SIDEBAR ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border-right: 1px solid {COLORS['border']};
            }}
        """)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(4)

        # Logo
        logo_row = QHBoxLayout()
        moon = QLabel("🌙")
        moon.setFont(QFont("Segoe UI Emoji", 22))
        moon.setStyleSheet("background: transparent;")
        title = QVBoxLayout()
        t1 = QLabel("Lune CD")
        t1.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        t1.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
        t2 = QLabel("Multi-IA v6")
        t2.setFont(QFont("Segoe UI", 8))
        t2.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
        title.addWidget(t1)
        title.addWidget(t2)
        title.setSpacing(0)
        logo_row.addWidget(moon)
        logo_row.addLayout(title, 1)
        layout.addLayout(logo_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; margin: 8px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Section label
        lbl = QLabel("PROVEEDORES")
        lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; padding: 4px 4px 4px 6px;")
        layout.addWidget(lbl)

        # Provider tabs
        self.provider_tabs: dict[str, ProviderTab] = {}
        for pid, meta in PROVIDER_META.items():
            tab = ProviderTab(pid, meta)
            tab.clicked.connect(self._switch_provider)
            self.provider_tabs[pid] = tab
            layout.addWidget(tab)
        self.provider_tabs["ollama"].set_active(True)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background: {COLORS['border']}; margin: 4px 0;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Bottom actions
        self._keys_btn = self._sidebar_action_btn("🔑", "API Keys")
        self._keys_btn.clicked.connect(self._toggle_keys_panel)
        layout.addWidget(self._keys_btn)

        clear_btn = self._sidebar_action_btn("🗑", "Limpiar chat")
        clear_btn.clicked.connect(self._clear_chat)
        layout.addWidget(clear_btn)

        if self.voice.available:
            self._voice_btn = self._sidebar_action_btn("🔊", "Voz: OFF")
            self._voice_btn.clicked.connect(self._toggle_voice)
            layout.addWidget(self._voice_btn)

        return sidebar

    def _sidebar_action_btn(self, icon: str, label: str) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 10))
        btn.setFixedHeight(38)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_muted']};
                border: none;
                border-radius: 8px;
                text-align: left;
                padding-left: 8px;
            }}
            QPushButton:hover {{
                background: {COLORS['surface2']};
                color: {COLORS['text']};
            }}
        """)
        return btn

    # ── MAIN AREA ─────────────────────────────────────────────────────────────

    def _build_main(self):
        main = QFrame()
        main.setStyleSheet(f"QFrame {{ background: {COLORS['bg']}; border: none; }}")
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_topbar())

        # Stacked: chat vs keys panel
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.stack.addWidget(self._build_chat_page())   # index 0
        self.stack.addWidget(self._build_keys_page())   # index 1
        layout.addWidget(self.stack, 1)

        layout.addWidget(self._build_input_bar())
        return main

    def _build_topbar(self):
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border-bottom: 1px solid {COLORS['border']};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)

        meta = PROVIDER_META[self.current_provider]
        self.topbar_icon = QLabel(meta["icon"])
        self.topbar_icon.setFont(QFont("Segoe UI Emoji", 18))
        self.topbar_icon.setStyleSheet("background: transparent;")

        self.topbar_title = QLabel(meta["label"])
        self.topbar_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.topbar_title.setStyleSheet(f"color: {meta['color']}; background: transparent;")

        self.topbar_desc = QLabel("·  " + meta["desc"])
        self.topbar_desc.setFont(QFont("Segoe UI", 10))
        self.topbar_desc.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")

        layout.addWidget(self.topbar_icon)
        layout.addSpacing(8)
        layout.addWidget(self.topbar_title)
        layout.addWidget(self.topbar_desc)
        layout.addStretch()

        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Segoe UI", 10))
        self.status_dot.setStyleSheet(f"color: {COLORS['success']}; background: transparent;")
        self.status_label = QLabel("Listo")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
        layout.addWidget(self.status_dot)
        layout.addSpacing(4)
        layout.addWidget(self.status_label)

        return bar

    def _build_chat_page(self):
        page = QFrame()
        page.setStyleSheet("QFrame { background: transparent; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                border: none;
                background: {COLORS['surface']};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['scrollbar']};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        self.scroll.setWidgetResizable(True)

        self.chat_container = QFrame()
        self.chat_container.setStyleSheet("QFrame { background: transparent; }")
        self.messages_layout = QVBoxLayout(self.chat_container)
        self.messages_layout.setContentsMargins(0, 16, 0, 16)
        self.messages_layout.setSpacing(6)
        self.messages_layout.addStretch()

        self.scroll.setWidget(self.chat_container)
        layout.addWidget(self.scroll)

        self._add_welcome()
        return page

    def _build_keys_page(self):
        page = QFrame()
        page.setStyleSheet("QFrame { background: transparent; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)

        self.key_panel = ApiKeyPanel(self.config)
        self.key_panel.saved.connect(self._on_keys_saved)
        layout.addWidget(self.key_panel)
        return page

    def _build_input_bar(self):
        bar = QFrame()
        bar.setFixedHeight(76)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['surface']};
                border-top: 1px solid {COLORS['border']};
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Escribe tu mensaje… (Enter para enviar, Shift+Enter nueva línea)")
        self.input_field.setFont(QFont("Segoe UI", 11))
        self.input_field.setFixedHeight(44)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['surface2']};
                border: 1px solid {COLORS['border2']};
                border-radius: 22px;
                padding: 0 18px;
                color: {COLORS['text']};
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent']};
                background: {COLORS['surface3']};
            }}
            QLineEdit::placeholder {{
                color: {COLORS['text_dim']};
            }}
        """)
        self.input_field.returnPressed.connect(self._send_message)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(44, 44)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self._update_send_btn_color()
        self.send_btn.clicked.connect(self._send_message)

        layout.addWidget(self.input_field, 1)
        layout.addWidget(self.send_btn)
        return bar

    # ── WELCOME MESSAGE ───────────────────────────────────────────────────────

    def _add_welcome(self):
        welcome = QFrame()
        welcome.setStyleSheet("QFrame { background: transparent; }")
        wl = QVBoxLayout(welcome)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(8)

        moon = QLabel("🌙")
        moon.setFont(QFont("Segoe UI Emoji", 40))
        moon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        moon.setStyleSheet("background: transparent;")

        t1 = QLabel("Lune CD · Multi-IA")
        t1.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t1.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")

        t2 = QLabel("Selecciona un proveedor en la barra lateral y empieza a chatear.\nConfigura tus API Keys con el botón 🔑")
        t2.setFont(QFont("Segoe UI", 11))
        t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t2.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")

        wl.addStretch()
        wl.addWidget(moon)
        wl.addWidget(t1)
        wl.addWidget(t2)
        wl.addStretch()

        self.messages_layout.insertWidget(0, welcome)

    # ── PROVIDER SWITCH ───────────────────────────────────────────────────────

    def _switch_provider(self, provider_id: str):
        if provider_id == self.current_provider:
            return
        self.current_provider = provider_id
        for pid, tab in self.provider_tabs.items():
            tab.set_active(pid == provider_id)

        meta = PROVIDER_META[provider_id]
        self.topbar_icon.setText(meta["icon"])
        self.topbar_title.setText(meta["label"])
        self.topbar_title.setStyleSheet(f"color: {meta['color']}; background: transparent;")
        self.topbar_desc.setText("·  " + meta["desc"])
        self._update_send_btn_color()

        # Stack back to chat
        self.stack.setCurrentIndex(0)
        log_info(f"Proveedor cambiado a: {provider_id}")

    def _update_send_btn_color(self):
        c = PROVIDER_META[self.current_provider]["color"]
        d = PROVIDER_META[self.current_provider]["dark"]
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {d}, stop:1 {c});
                color: white;
                border: none;
                border-radius: 22px;
            }}
            QPushButton:hover {{
                background: {c};
            }}
            QPushButton:disabled {{
                background: {COLORS['surface3']};
                color: {COLORS['text_dim']};
            }}
        """)

    # ── SEND / RECEIVE ─────────────────────────────────────────────────────────

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.stack.setCurrentIndex(0)

        # User bubble
        bubble = MessageBubble(text, is_user=True, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self._set_status("Procesando…", COLORS["warning"])

        # Typing indicator
        self._typing_indicator = TypingIndicator(self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._typing_indicator)
        self._scroll_bottom()

        self.ai_worker = AIWorker(self.ai_manager, text, self.current_provider)
        self.ai_worker.token_received.connect(self._on_token)
        self.ai_worker.response_ready.connect(self._on_response)
        self.ai_worker.error_occurred.connect(self._on_error)
        self.ai_worker.start()

    def _on_token(self, partial: str):
        if self._typing_indicator and self._current_bubble is None:
            # Replace typing with real bubble
            self._typing_indicator.stop()
            self._typing_indicator.deleteLater()
            self._typing_indicator = None
            self._current_bubble = MessageBubble(
                partial + " ▋",
                is_user=False,
                provider_id=self.current_provider,
            )
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1,
                self._current_bubble,
            )
        elif self._current_bubble:
            self._current_bubble.update_text(partial + " ▋")
        self._scroll_bottom()

    def _on_response(self, response: str):
        if self._current_bubble:
            self._current_bubble.update_text(response)
        if self._typing_indicator:
            self._typing_indicator.stop()
            self._typing_indicator.deleteLater()
            self._typing_indicator = None
        self._current_bubble = None
        self._set_status("Listo", COLORS["success"])
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()
        self.voice.speak(response)
        self._scroll_bottom()

    def _on_error(self, error: str):
        if self._typing_indicator:
            self._typing_indicator.stop()
            self._typing_indicator.deleteLater()
            self._typing_indicator = None
        if self._current_bubble:
            self._current_bubble.update_text(f"❌ {error}")
        else:
            err_bubble = MessageBubble(f"❌ {error}", is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, err_bubble)
        self._current_bubble = None
        self._set_status("Error", COLORS["error"])
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()
        self._scroll_bottom()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_dot.setStyleSheet(f"color: {color}; background: transparent;")

    def _toggle_voice(self):
        enabled = self.voice.toggle()
        self._voice_btn.setText(f"  🔊  Voz: {'ON' if enabled else 'OFF'}")

    def _toggle_keys_panel(self):
        self.stack.setCurrentIndex(1 if self.stack.currentIndex() == 0 else 0)

    def _on_keys_saved(self):
        # Reload all providers with new keys
        for pid in PROVIDER_META:
            self.ai_manager.reload_provider(pid)
        self.stack.setCurrentIndex(0)
        QMessageBox.information(self, "✅ Guardado", "API Keys guardadas y proveedores recargados.")

    def _clear_chat(self):
        reply = QMessageBox.question(
            self, "Limpiar chat", "¿Eliminar todos los mensajes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            while self.messages_layout.count() > 1:
                item = self.messages_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.ai_manager.clear_history()
            self._add_welcome()


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")
    app.setApplicationVersion("6.0")

    # Global palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    app.setPalette(palette)

    window = LuneCDWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()