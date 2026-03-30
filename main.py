import sys
import asyncio
import threading
import io
import re
import subprocess
import os
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QStackedWidget, QDialog,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

from config import Config
from ai_manager import AIManager
from utils import Logger, log_info, log_error
import datos

logger = Logger()

# ─────────────────────────────────────────────────────────────────────────────
#  COLORES
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
    "telegram":     "#29b6f6",
    "telegram_dark":"#0277bd",
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
        "system": lambda: datos.get_personaje(datos.get_bot().get("personaje_default","")).get("systemPrompt","Eres un asistente amigable. Responde en español."),
    },
    "deepseek": {
        "label": "DeepSeek",
        "icon": "🔬",
        "color": COLORS["deepseek"],
        "dark": COLORS["deepseek_dark"],
        "desc": "Razonamiento avanzado",
        "system": "Eres un asistente de IA altamente capaz. Responde en español.",
    },
    "claude": {
        "label": "Z.ai GLM",
        "icon": "⚡",
        "color": COLORS["claude"],
        "dark": COLORS["claude_dark"],
        "desc": "GLM-4.5 Air · Gratis",
        "system": "Eres Lune, una asistente inteligente, amigable y sin censura innecesaria. Responde en español de forma clara y útil.",
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
#  LUNE FACE — Detector de expresiones
# ─────────────────────────────────────────────────────────────────────────────

FACE_DIR = Path(__file__).parent / "lune_face"

FACE_FILES = {
    "normal":    "lune_normal.png",
    "happy":     "lune_happy.png",
    "thinking":  "lune_thinking.png",
    "typing":    "lune_typing.png",
    "reading":   "lune_reading.png",
    "sad":       "lune_sad.png",
    "confused":  "lune_confused.png",
    "error":     "lune_error.png",
}

# Palabras clave para detectar el estado emocional de la respuesta
EMOTION_KEYWORDS = {
    "happy": [
        "perfecto", "excelente", "claro", "con gusto", "por supuesto", "genial",
        "listo", "hecho", "entendido", "buena idea", "me alegra", "fantástico",
        "encantada", "encantado", "feliz", "contento", "maravilloso", "estupendo",
        "de acuerdo", "confirmado", "completado", "great", "sure", "perfect",
    ],
    "sad": [
        "lo siento", "disculpa", "disculpe", "perdón", "lamentablemente",
        "desafortunadamente", "imposible", "no puedo", "triste", "error grave",
        "problema serio", "fallé", "fallamos",
    ],
    "reading": [
        "según", "investigando", "información", "encontré que", "de acuerdo a",
        "datos", "fuentes", "documentación", "referencia", "basándome en",
        "he encontrado", "buscando", "análisis", "revisando",
    ],
    "typing": [
        "aquí está", "a continuación", "te presento", "redactando", "escribiendo",
        "el documento", "el texto", "el código", "el informe", "el resumen",
        "la lista", "el plan", "generando",
    ],
    "confused": [
        "no entiendo", "no estoy segura", "no estoy seguro", "podrías aclarar",
        "podrías especificar", "¿a qué te refieres", "es ambiguo", "no queda claro",
        "no comprendo", "¿puedes repetir", "¿qué quieres decir",
    ],
    "error": [
        "❌", "error:", "no se pudo", "falló", "timeout", "conexión rechazada",
        "api key", "sin respuesta", "excepción", "exception", "fallo crítico",
    ],
}


def detect_emotion(text: str) -> str:
    """Detecta la emoción apropiada basada en el contenido del texto."""
    text_lower = text.lower()

    # Error tiene prioridad máxima
    if any(kw in text_lower for kw in EMOTION_KEYWORDS["error"]):
        return "error"

    # Revisar cada categoría en orden de prioridad
    for emotion in ["sad", "confused", "happy", "reading", "typing"]:
        if any(kw in text_lower for kw in EMOTION_KEYWORDS[emotion]):
            return emotion

    return "normal"


def get_face_path(state: str) -> str | None:
    """Devuelve la ruta absoluta de la imagen de expresión, o None si no existe."""
    filename = FACE_FILES.get(state, FACE_FILES["normal"])
    path = FACE_DIR / filename
    return str(path) if path.exists() else None


# ─────────────────────────────────────────────────────────────────────────────
#  WIDGET DE LUNE FACE
# ─────────────────────────────────────────────────────────────────────────────

class LuneFaceWidget(QFrame):
    """Widget que muestra la imagen de Lune con transiciones suaves entre expresiones."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(196, 260)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self._current_state = "normal"
        self._pending_state = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Label que muestra la imagen
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label)

        # Fallback: emoji grande si no hay imagen
        self._fallback_label = QLabel("🌙")
        self._fallback_label.setFont(QFont("Segoe UI Emoji", 64))
        self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback_label.setStyleSheet("background: transparent; border: none;")
        self._fallback_label.hide()
        layout.addWidget(self._fallback_label)

        # Cargar imagen inicial
        self._load_face("normal")

        # Timer para volver a normal automáticamente después de ciertos estados temporales
        self._revert_timer = QTimer(self)
        self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(lambda: self.set_state("normal"))

    def _load_face(self, state: str):
        """Carga la imagen del estado dado."""
        path = get_face_path(state)
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Escalar manteniendo aspecto, máximo 190x250
                scaled = pixmap.scaled(
                    190, 250,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled)
                self.image_label.show()
                self._fallback_label.hide()
                return

        # Si no hay imagen, mostrar emoji fallback según estado
        fallback_emojis = {
            "normal":   "🌙",
            "happy":    "😊",
            "thinking": "🤔",
            "typing":   "⌨️",
            "reading":  "📖",
            "sad":      "😔",
            "confused": "😕",
            "error":    "❌",
        }
        self._fallback_label.setText(fallback_emojis.get(state, "🌙"))
        self._fallback_label.show()
        self.image_label.hide()

    def set_state(self, state: str, auto_revert_ms: int = 0):
        """
        Cambia la expresión de Lune.
        auto_revert_ms > 0 → vuelve a 'normal' después de ese tiempo.
        """
        if state == self._current_state:
            return
        self._current_state = state
        self._load_face(state)

        if auto_revert_ms > 0:
            self._revert_timer.start(auto_revert_ms)
        else:
            self._revert_timer.stop()

    def get_state(self) -> str:
        return self._current_state


# ─────────────────────────────────────────────────────────────────────────────
#  VOZ — TTS con prioridad: edge-tts → gTTS → sin voz
# ─────────────────────────────────────────────────────────────────────────────

class VoiceEngine:
    def __init__(self):
        self._enabled = False
        self._lock = threading.Lock()
        self._engine = None          # "edge", "gtts", None
        self._init_engine()

    def _init_engine(self):
        # Intentar edge-tts primero (mejor calidad)
        try:
            import edge_tts  # noqa: F401
            import pygame
            pygame.mixer.init()
            self._engine = "edge"
            log_info("Motor de voz: edge-tts ✓")
            return
        except ImportError:
            pass

        # Fallback a gTTS
        try:
            from gtts import gTTS
            import pygame
            pygame.mixer.init()
            self._engine = "gtts"
            log_info("Motor de voz: gTTS ✓")
            return
        except ImportError:
            pass

        log_error("Sin motor de voz. Instala: pip install edge-tts pygame  o  pip install gtts pygame")
        self._engine = None

    def speak(self, text: str):
        if not self._enabled or not self._engine:
            return
        clean = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', text, flags=re.UNICODE).strip()
        if not clean:
            return
        # Limitar a primeras 400 caracteres para no bloquear demasiado
        clean = clean[:400]
        threading.Thread(target=self._speak_blocking, args=(clean,), daemon=True).start()

    def _speak_blocking(self, text: str):
        with self._lock:
            if self._engine == "edge":
                self._speak_edge(text)
            elif self._engine == "gtts":
                self._speak_gtts(text)

    def _speak_edge(self, text: str):
        try:
            import asyncio
            import edge_tts
            import pygame
            import tempfile

            async def _synthesize():
                communicate = edge_tts.Communicate(text, voice="es-MX-DaliaNeural")
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()
                await communicate.save(tmp.name)
                return tmp.name

            path = asyncio.run(_synthesize())
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                threading.Event().wait(0.1)
            os.unlink(path)
        except Exception as e:
            log_error(f"edge-tts error: {e}")

    def _speak_gtts(self, text: str):
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
            log_error(f"gTTS error: {e}")

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    @property
    def available(self): return self._engine is not None
    @property
    def enabled(self): return self._enabled
    @property
    def engine_name(self): return self._engine or "sin voz"


# ─────────────────────────────────────────────────────────────────────────────
#  PROVIDER TAB
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
        else:
            self.setStyleSheet(f"""
                ProviderTab {{
                    background: transparent;
                    border-left: 3px solid transparent;
                    border-radius: 10px;
                }}
                ProviderTab:hover {{ background: {COLORS['surface2']}; }}
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
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.setSpacing(4)
            self.text_lbl = QLabel(text)
            self.text_lbl.setWordWrap(True)
            self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont("Segoe UI", 11))
            self.text_lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
            self.text_lbl.setMaximumWidth(520)
            bl.addWidget(self.text_lbl)
            ts = QLabel(datetime.now().strftime("%H:%M"))
            ts.setFont(QFont("Segoe UI", 8))
            ts.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
            ts.setAlignment(Qt.AlignmentFlag.AlignRight)
            bl.addWidget(ts)
            outer.addWidget(bubble)
        else:
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
            bl = QVBoxLayout(bubble)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.setSpacing(4)
            sender = QLabel(meta["label"])
            sender.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            sender.setStyleSheet(f"color: {color}; background: transparent;")
            bl.addWidget(sender)
            self.text_lbl = QLabel(text)
            self.text_lbl.setWordWrap(True)
            self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont("Segoe UI", 11))
            self.text_lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
            self.text_lbl.setMaximumWidth(520)
            bl.addWidget(self.text_lbl)
            ts = QLabel(datetime.now().strftime("%H:%M"))
            ts.setFont(QFont("Segoe UI", 8))
            ts.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
            bl.addWidget(ts)
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
            border-radius: 10px; border: 1px solid {meta['color']}55;
        """)
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        dots_frame = QFrame()
        dots_frame.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bot_bubble']};
                border-radius: 16px; border-top-left-radius: 4px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        dl = QHBoxLayout(dots_frame)
        dl.setContentsMargins(16, 12, 16, 12)
        dl.setSpacing(6)
        self.dots = []
        for _ in range(3):
            dot = QLabel("●")
            dot.setFont(QFont("Segoe UI", 9))
            dot.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
            dl.addWidget(dot)
            self.dots.append(dot)
        layout.addWidget(dots_frame)
        layout.addStretch()
        self._dot_idx = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(300)

    def _animate(self):
        c = COLORS["accent"]
        for i, dot in enumerate(self.dots):
            dot.setStyleSheet(f"color: {''+c if i == self._dot_idx else COLORS['text_dim']}; background: transparent;")
        self._dot_idx = (self._dot_idx + 1) % 3

    def stop(self): self._timer.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  AI WORKER
# ─────────────────────────────────────────────────────────────────────────────
class AIWorker(QThread):
    token_received  = pyqtSignal(str)
    response_ready  = pyqtSignal(str)
    error_occurred  = pyqtSignal(str)

    def __init__(self, ai_manager, message: str, provider_id: str):
        super().__init__()
        self.ai_manager  = ai_manager
        self.message     = message
        self.provider_id = provider_id
        self._buffer     = ""

    def run(self):
        try:
            sys_val = PROVIDER_META[self.provider_id]["system"]
            system_prompt = sys_val() if callable(sys_val) else sys_val

            def on_token(token):
                self._buffer += token
                self.token_received.emit(self._buffer)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    self.ai_manager.chat(
                        self.message, system_prompt,
                        provider=self.provider_id, on_token=on_token
                    )
                )
            finally:
                loop.close()

            self.response_ready.emit(response or "Sin respuesta")
        except Exception as e:
            log_error(f"AIWorker error: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  TELEGRAM BOT WORKER
# ─────────────────────────────────────────────────────────────────────────────
class TelegramBotWorker(QThread):
    log_signal    = pyqtSignal(str)
    stopped       = pyqtSignal()

    BOT_DIR = Path(__file__).parent / "telegram-bot-or"

    def __init__(self):
        super().__init__()
        self._process: subprocess.Popen | None = None

    def run(self):
        if not self.BOT_DIR.exists():
            self.log_signal.emit(f"❌ No encontré la carpeta: {self.BOT_DIR}")
            self.stopped.emit()
            return

        node_modules = self.BOT_DIR / "node_modules"
        if not node_modules.exists():
            self.log_signal.emit("📦 Instalando dependencias (npm install)...")
            try:
                subprocess.run(
                    ["npm", "install"],
                    cwd=str(self.BOT_DIR),
                    check=True,
                    capture_output=True,
                )
            except Exception as e:
                self.log_signal.emit(f"❌ npm install falló: {e}")
                self.stopped.emit()
                return

        self.log_signal.emit("🤖 Iniciando bot de Telegram...")
        try:
            self._process = subprocess.Popen(
                ["npm", "start"],
                cwd=str(self.BOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in self._process.stdout:
                self.log_signal.emit(line.rstrip())
                if not self.isInterruptionRequested():
                    continue
                break
        except Exception as e:
            self.log_signal.emit(f"❌ Error: {e}")
        finally:
            self.stop()
            self.stopped.emit()

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None


# ─────────────────────────────────────────────────────────────────────────────
#  API KEY PANEL
# ─────────────────────────────────────────────────────────────────────────────
class ApiKeyPanel(QFrame):
    saved = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setStyleSheet(f"""
            QFrame {{ background: {COLORS['surface']}; border-radius: 16px; border: 1px solid {COLORS['border']}; }}
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        title = QLabel("🔑  Configurar API Keys")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
        layout.addWidget(title)
        self.fields: dict[str, QLineEdit] = {}
        providers_fields = [
            ("character_ai", "🎭  Character.AI Token", "api_key"),
            ("deepseek",     "🔬  DeepSeek API Key",   "api_key"),
            ("claude",       "✦   Claude API Key",     "api_key"),
            ("ollama",       "🦙  Ollama URL",          "url"),
            ("ollama",       "🦙  Ollama Modelo",       "model"),
        ]
        for (provider, label_text, field) in providers_fields:
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
            inp = QLineEdit()
            inp.setText(self.config.get_key(provider, field))
            inp.setEchoMode(QLineEdit.EchoMode.Password if field == "api_key" else QLineEdit.EchoMode.Normal)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    background: {COLORS['surface2']}; border: 1px solid {COLORS['border']};
                    border-radius: 8px; padding: 8px 12px; color: {COLORS['text']};
                }}
                QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            """)
            self.fields[f"{provider}_{field}"] = inp
            layout.addWidget(lbl)
            layout.addWidget(inp)
        save_btn = QPushButton("💾  Guardar Keys")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        save_btn.setFixedHeight(44)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {COLORS['accent']}, stop:1 {COLORS['accent2']});
                color: white; border: none; border-radius: 10px;
            }}
            QPushButton:hover {{ background: {COLORS['accent2']}; }}
        """)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch()

    def _save(self):
        mapping = {
            "character_ai_api_key": ("character_ai", "api_key"),
            "deepseek_api_key":     ("deepseek",     "api_key"),
            "claude_api_key":       ("claude",        "api_key"),
            "ollama_url":           ("ollama",        "url"),
            "ollama_model":         ("ollama",        "model"),
        }
        for key, (prov, field) in mapping.items():
            if key in self.fields:
                self.config.set_key(prov, field, self.fields[key].text().strip())
        self.saved.emit()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class LuneCDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config          = Config()
        self.ai_manager      = AIManager()
        self.voice           = VoiceEngine()
        self.current_provider= "ollama"
        self.ai_worker       = None
        self._current_bubble = None
        self._typing_indicator = None
        self._tg_worker = None

        self._init_ui()
        log_info("Lune CD v7 iniciado")
        log_info(f"Motor de voz: {self.voice.engine_name}")
        log_info(f"Carpeta de expresiones: {FACE_DIR}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle("🌙 Lune CD v6 · Multi-IA")
        self.setGeometry(80, 60, 1200, 800)
        self.setMinimumSize(900, 640)
        self.setStyleSheet(f"QMainWindow, QWidget {{ background: {COLORS['bg']}; }}")

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lune_icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lune_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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

        lbl = QLabel("PROVEEDORES")
        lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent; padding: 4px 4px 4px 6px;")
        layout.addWidget(lbl)

        self.provider_tabs: dict[str, ProviderTab] = {}
        for pid, meta in PROVIDER_META.items():
            tab = ProviderTab(pid, meta)
            tab.clicked.connect(self._switch_provider)
            self.provider_tabs[pid] = tab
            layout.addWidget(tab)
        self.provider_tabs["ollama"].set_active(True)

        layout.addStretch()

        # ── LUNE FACE WIDGET ─────────────────────────────────────────────────
        self.lune_face = LuneFaceWidget()
        face_container = QHBoxLayout()
        face_container.setContentsMargins(0, 0, 0, 0)
        face_container.addStretch()
        face_container.addWidget(self.lune_face)
        face_container.addStretch()
        layout.addLayout(face_container)
        # ─────────────────────────────────────────────────────────────────────

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background: {COLORS['border']}; margin: 4px 0;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        self.telegram_btn = QPushButton("  🤖  Continuar en Telegram")
        self.telegram_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.telegram_btn.setFont(QFont("Segoe UI", 10))
        self.telegram_btn.setFixedHeight(42)
        self._set_telegram_btn_style(False)
        self.telegram_btn.clicked.connect(self._toggle_telegram)
        layout.addWidget(self.telegram_btn)

        self.telegram_status = QLabel("")
        self.telegram_status.setFont(QFont("Segoe UI", 8))
        self.telegram_status.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent; padding-left: 8px;")
        self.telegram_status.setWordWrap(True)
        layout.addWidget(self.telegram_status)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet(f"background: {COLORS['border']}; margin: 4px 0;")
        sep3.setFixedHeight(1)
        layout.addWidget(sep3)

        self._keys_btn = self._sidebar_btn("🔑", "API Keys")
        self._keys_btn.clicked.connect(self._toggle_keys_panel)
        layout.addWidget(self._keys_btn)

        clear_btn = self._sidebar_btn("🗑", "Limpiar chat")
        clear_btn.clicked.connect(self._clear_chat)
        layout.addWidget(clear_btn)

        if self.voice.available:
            icon_voz = "🔊" if self.voice.engine_name == "edge" else "📢"
            self._voice_btn = self._sidebar_btn(icon_voz, "Voz: OFF")
            self._voice_btn.clicked.connect(self._toggle_voice)
            layout.addWidget(self._voice_btn)

        return sidebar

    def _set_telegram_btn_style(self, active: bool):
        if active:
            self.telegram_btn.setText("  🟢  Telegram: Activo")
            self.telegram_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {COLORS['telegram_dark']}, stop:1 {COLORS['telegram']});
                    color: white; border: none; border-radius: 10px;
                    text-align: left; padding-left: 12px; font-weight: bold;
                }}
                QPushButton:hover {{ background: {COLORS['telegram']}; }}
            """)
        else:
            self.telegram_btn.setText("  🤖  Continuar en Telegram")
            self.telegram_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['surface2']};
                    color: {COLORS['telegram']};
                    border: 1px solid {COLORS['telegram']}55;
                    border-radius: 10px;
                    text-align: left; padding-left: 12px;
                }}
                QPushButton:hover {{
                    background: {COLORS['telegram_dark']}44;
                    border-color: {COLORS['telegram']};
                }}
            """)

    def _sidebar_btn(self, icon: str, label: str) -> QPushButton:
        btn = QPushButton(f"  {icon}  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 10))
        btn.setFixedHeight(38)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLORS['text_muted']};
                border: none; border-radius: 8px;
                text-align: left; padding-left: 8px;
            }}
            QPushButton:hover {{ background: {COLORS['surface2']}; color: {COLORS['text']}; }}
        """)
        return btn

    # ── TELEGRAM TOGGLE ───────────────────────────────────────────────────────

    def _toggle_telegram(self):
        if hasattr(self, "_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            self._tg_worker.stop()
            self._tg_worker.requestInterruption()
            self._tg_worker.wait(3000)
            self._tg_worker = None
            self._set_telegram_btn_style(False)
            self.telegram_status.setText("")
            log_info("Telegram bot detenido")
            return

        if not datos.telegram_token() or "TU_TOKEN" in datos.telegram_token():
            QMessageBox.warning(self, "Token faltante",
                "Agrega tu telegram_token en datos.json")
            return

        bot_dir = TelegramBotWorker.BOT_DIR
        if not bot_dir.exists():
            QMessageBox.warning(
                self, "Carpeta no encontrada",
                f"No encontré la carpeta del bot en:\n{bot_dir}\n\n"
                "Asegúrate de que la carpeta 'telegram-bot-or' esté dentro del proyecto."
            )
            return

        self._tg_worker = TelegramBotWorker()
        self._tg_worker.log_signal.connect(self._on_telegram_log)
        self._tg_worker.stopped.connect(self._on_telegram_stopped)
        self._tg_worker.start()
        self._set_telegram_btn_style(True)
        self.telegram_status.setText("Iniciando...")
        log_info("Telegram bot iniciando")

    def _on_telegram_log(self, line: str):
        log_info(f"[Telegram] {line}")
        if any(k in line for k in ["Bot iniciado", "iniciado", "Modelo:", "Error"]):
            self.telegram_status.setText(line[:60])

    def _on_telegram_stopped(self):
        self._set_telegram_btn_style(False)
        self.telegram_status.setText("Bot detenido")
        QTimer.singleShot(3000, lambda: self.telegram_status.setText(""))

    # ── MAIN AREA ─────────────────────────────────────────────────────────────

    def _build_main(self):
        main = QFrame()
        main.setStyleSheet(f"QFrame {{ background: {COLORS['bg']}; border: none; }}")
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.stack.addWidget(self._build_chat_page())
        self.stack.addWidget(self._build_keys_page())
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
        self.topbar_icon  = QLabel(meta["icon"])
        self.topbar_icon.setFont(QFont("Segoe UI Emoji", 18))
        self.topbar_icon.setStyleSheet("background: transparent;")
        self.topbar_title = QLabel(meta["label"])
        self.topbar_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.topbar_title.setStyleSheet(f"color: {meta['color']}; background: transparent;")
        self.topbar_desc  = QLabel("·  " + meta["desc"])
        self.topbar_desc.setFont(QFont("Segoe UI", 10))
        self.topbar_desc.setStyleSheet(f"color: {COLORS['text_muted']}; background: transparent;")
        layout.addWidget(self.topbar_icon)
        layout.addSpacing(8)
        layout.addWidget(self.topbar_title)
        layout.addWidget(self.topbar_desc)
        layout.addStretch()
        self.status_dot   = QLabel("●")
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
                border: none; background: {COLORS['surface']}; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['scrollbar']}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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
        self.input_field.setPlaceholderText("Escribe tu mensaje… (Enter para enviar)")
        self.input_field.setFont(QFont("Segoe UI", 11))
        self.input_field.setFixedHeight(44)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['surface2']}; border: 1px solid {COLORS['border2']};
                border-radius: 22px; padding: 0 18px; color: {COLORS['text']};
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; background: {COLORS['surface3']}; }}
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

    # ── WELCOME ───────────────────────────────────────────────────────────────

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
        t2 = QLabel("Selecciona un proveedor y empieza a chatear.\nUsa 'Continuar en Telegram' para chatear desde tu móvil.")
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
        self.stack.setCurrentIndex(0)

    def _update_send_btn_color(self):
        c = PROVIDER_META[self.current_provider]["color"]
        d = PROVIDER_META[self.current_provider]["dark"]
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {d}, stop:1 {c});
                color: white; border: none; border-radius: 22px;
            }}
            QPushButton:hover {{ background: {c}; }}
            QPushButton:disabled {{ background: {COLORS['surface3']}; color: {COLORS['text_dim']}; }}
        """)

    # ── SEND / RECEIVE ─────────────────────────────────────────────────────────

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.stack.setCurrentIndex(0)
        bubble = MessageBubble(text, is_user=True, provider_id=self.current_provider)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self._set_status("Procesando…", COLORS["warning"])

        # Expresión: pensando mientras procesa
        self.lune_face.set_state("thinking")

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
            self._typing_indicator.stop()
            self._typing_indicator.deleteLater()
            self._typing_indicator = None
            self._current_bubble = MessageBubble(
                partial + " ▋", is_user=False, provider_id=self.current_provider)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, self._current_bubble)

            # Expresión: escribiendo mientras llegan tokens
            self.lune_face.set_state("typing")

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

        # Detectar emoción y cambiar expresión (vuelve a normal después de 6s)
        emotion = detect_emotion(response)
        self.lune_face.set_state(emotion, auto_revert_ms=6000)

        # Voz: leer la respuesta en voz alta
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

        # Expresión de error (vuelve a normal después de 8s)
        self.lune_face.set_state("error", auto_revert_ms=8000)

        self._scroll_bottom()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _set_status(self, text: str, color: str):
        self.status_label.setText(text)
        self.status_dot.setStyleSheet(f"color: {color}; background: transparent;")

    def _toggle_voice(self):
        enabled = self.voice.toggle()
        icon_voz = "🔊" if self.voice.engine_name == "edge" else "📢"
        self._voice_btn.setText(f"  {icon_voz}  Voz: {'ON' if enabled else 'OFF'}")

    def _toggle_keys_panel(self):
        self.stack.setCurrentIndex(1 if self.stack.currentIndex() == 0 else 0)

    def _on_keys_saved(self):
        for pid in PROVIDER_META:
            self.ai_manager.reload_provider(pid)
        self.stack.setCurrentIndex(0)
        QMessageBox.information(self, "✅ Guardado", "API Keys guardadas.")

    def _clear_chat(self):
        reply = QMessageBox.question(self, "Limpiar chat", "¿Eliminar todos los mensajes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            while self.messages_layout.count() > 1:
                item = self.messages_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            self.ai_manager.clear_history()
            self._add_welcome()
            self.lune_face.set_state("normal")

    def closeEvent(self, event):
        if hasattr(self, "_tg_worker") and self._tg_worker and self._tg_worker.isRunning():
            self._tg_worker.stop()
            self._tg_worker.wait(3000)
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LuneCD.v6")
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "lune_icon.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(base_dir, "lune_icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,     QColor(COLORS["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base,       QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.Text,       QColor(COLORS["text"]))
    app.setPalette(palette)

    window = LuneCDWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()