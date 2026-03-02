import sys
import asyncio
import threading
import io
import re
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QCursor

from config import Config
from ai_manager import AIManager
from utils import Logger, log_info, log_error

logger = Logger()


# ─────────────────────────────────────────
#  VOZ (gTTS + pygame)
# ─────────────────────────────────────────
class VoiceEngine:
    def __init__(self):
        self._enabled = True
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
            flags=re.UNICODE
        )
        text = emoji_pattern.sub("", text)
        return text.replace("▋", "").replace("❌", "").replace("✅", "").strip()

    def toggle(self) -> bool:
        self._enabled = not self._enabled
        return self._enabled

    @property
    def available(self): return self._available

    @property
    def enabled(self): return self._enabled


# ─────────────────────────────────────────
#  TASK ITEM
# ─────────────────────────────────────────
class TaskItem(QFrame):
    def __init__(self, icon_text, title, description, timestamp, status="pending", parent=None):
        super().__init__(parent)
        self.status = status
        self.setStyleSheet(self._get_stylesheet())

        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        icon_label = QLabel(icon_text)
        icon_label.setStyleSheet(self._get_icon_stylesheet())
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(40, 40)

        content_layout = QVBoxLayout()
        title_label = QLabel(title)
        f = QFont("Arial", 11); f.setBold(True)
        title_label.setFont(f)
        title_label.setStyleSheet("color: #2d3748;")

        self.desc_label = QLabel(description)
        self.desc_label.setStyleSheet("color: #718096; font-size: 12px;")
        self.desc_label.setWordWrap(True)

        time_label = QLabel(timestamp)
        time_label.setStyleSheet("color: #a0aec0; font-size: 11px;")

        content_layout.addWidget(title_label)
        content_layout.addWidget(self.desc_label)
        content_layout.addWidget(time_label)
        content_layout.setSpacing(5)
        content_layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(icon_label)
        layout.addLayout(content_layout, 1)
        layout.addStretch()

    def update_text(self, text: str):
        self.desc_label.setText(text)

    def _get_stylesheet(self):
        bg, border = "#f8f9fa", "#e9ecef"
        if self.status == "error":
            bg, border = "#ffe0e0", "#ffcccc"
        return f"""
            TaskItem {{ background-color: {bg}; border-radius: 10px;
                border: 1px solid {border}; padding: 12px; margin: 5px 0px; }}
            TaskItem:hover {{ background-color: #f0f3f7; border: 1px solid #d9e0e7; }}
        """

    def _get_icon_stylesheet(self):
        color = {"error": "#ff6b6b", "working": "#4299e1", "completed": "#48bb78"}.get(self.status, "#667eea")
        return f"""QLabel {{ background-color: {color}; color: white; border-radius: 20px;
            padding: 8px; font-weight: bold; font-size: 18px; }}"""


# ─────────────────────────────────────────
#  AI WORKER
# ─────────────────────────────────────────
class AIWorker(QThread):
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ai_manager, message):
        super().__init__()
        self.ai_manager = ai_manager
        self.message = message
        self._buffer = ""

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            system_prompt = (
                "Eres Lune, una asistente virtual inteligente y amigable. "
                "Eres experta en escribir, investigar y automatizar tareas. "
                "Responde de manera clara, concisa y útil. Siempre sé amable y profesional."
            )

            def on_token(token):
                self._buffer += token
                self.token_received.emit(self._buffer)

            response = loop.run_until_complete(
                self.ai_manager.chat(self.message, system_prompt, on_token=on_token)
            )
            if response:
                self.response_ready.emit(response)
            else:
                self.error_occurred.emit("La IA no retornó respuesta")
        except Exception as e:
            log_error(f"Error en AIWorker: {e}")
            self.error_occurred.emit(f"Error: {e}")
        finally:
            if 'loop' in locals():
                loop.close()


# ─────────────────────────────────────────
#  VENTANA PRINCIPAL
# ─────────────────────────────────────────
class LuneCDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.config = Config()
            self.ai_manager = AIManager(self.config)
            self.voice = VoiceEngine()
            self.tasks = []
            self.ai_worker = None
            self.tasks_layout = None
            self.tasks_container = None
            self._current_response_item = None
            log_info("Aplicación iniciada")
            self.init_ui()
            self.apply_theme()
            self.check_ai_providers()
        except Exception as e:
            log_error(f"Error al inicializar: {e}")
            QMessageBox.critical(self, "Error", f"Error: {e}")
            sys.exit(1)

    def init_ui(self):
        self.setWindowTitle("🌙 Lune CD v5 - Virtual Assistant")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(700, 600)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._create_header())
        layout.addWidget(self._create_tasks_area(), 1)
        layout.addWidget(self._create_input_area())

    def _create_header(self):
        header = QFrame()
        header.setStyleSheet("""
            QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #667eea,stop:1 #764ba2);
                border-bottom: 2px solid #5568d3; }
        """)
        header.setMaximumHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(15, 10, 15, 10)

        title = QLabel("🌙 Virtual Assistant")
        f = QFont("Arial", 16); f.setBold(True)
        title.setFont(f); title.setStyleSheet("color: white;")
        subtitle = QLabel("Powered by Ollama")
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setStyleSheet("color: rgba(255,255,255,0.8);")
        tl = QVBoxLayout(); tl.addWidget(title); tl.addWidget(subtitle); tl.setSpacing(0)
        layout.addLayout(tl)
        layout.addStretch()

        self.voice_btn = QPushButton("🔊")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setFixedSize(40, 40)
        self.voice_btn.setStyleSheet(self._voice_btn_style(True))
        self.voice_btn.clicked.connect(self._toggle_voice)
        if not self.voice.available:
            self.voice_btn.setEnabled(False)
            self.voice_btn.setToolTip("Instala: pip install gtts pygame")

        menu_btn = QPushButton("⋮")
        menu_btn.setFixedSize(40, 40)
        menu_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.2); color: white;
                border: 1px solid rgba(255,255,255,0.3); border-radius: 5px; font-size: 16px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.3); }
        """)
        menu_btn.clicked.connect(self.show_menu)

        layout.addWidget(self.voice_btn)
        layout.addWidget(menu_btn)
        return header

    def _voice_btn_style(self, active):
        bg = "rgba(255,255,255,0.35)" if active else "rgba(255,255,255,0.1)"
        return f"""QPushButton {{ background-color: {bg}; color: white;
            border: 1px solid rgba(255,255,255,0.4); border-radius: 5px; font-size: 18px; }}
            QPushButton:hover {{ background-color: rgba(255,255,255,0.45); }}"""

    def _toggle_voice(self):
        enabled = self.voice.toggle()
        self.voice_btn.setChecked(enabled)
        self.voice_btn.setStyleSheet(self._voice_btn_style(enabled))
        self.voice_btn.setText("🔊" if enabled else "🔇")

    def _create_tasks_area(self):
        container = QFrame()
        container.setStyleSheet("QFrame { background-color: #ffffff; }")
        layout = QVBoxLayout(container)
        layout.setSpacing(0); layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: #ffffff; }
            QScrollBar:vertical { border: none; background-color: #f8f9fa; width: 8px; }
            QScrollBar::handle:vertical { background-color: #cbd5e0; border-radius: 4px; }
        """)
        self.scroll.setWidgetResizable(True)

        self.tasks_container = QFrame()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setSpacing(8)
        self.tasks_layout.setContentsMargins(15, 15, 15, 15)

        welcome = QLabel("👋 ¡Hola! Soy Lune, tu asistente virtual.\n¿En qué puedo ayudarte hoy?")
        welcome.setStyleSheet("QLabel { color: #718096; font-size: 14px; padding: 20px; }")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tasks_layout.addWidget(welcome)
        self.tasks_layout.addStretch()

        self.scroll.setWidget(self.tasks_container)
        layout.addWidget(self.scroll)
        return container

    def _create_input_area(self):
        container = QFrame()
        container.setStyleSheet("QFrame { background-color: white; border-top: 1px solid #e9ecef; }")
        container.setMaximumHeight(80)
        layout = QHBoxLayout(container)
        layout.setSpacing(10); layout.setContentsMargins(15, 12, 15, 12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Escribe tu mensaje aquí...")
        self.input_field.setStyleSheet("""
            QLineEdit { background-color: #f8f9fa; border: 2px solid #e9ecef;
                border-radius: 20px; padding: 10px 15px; font-size: 13px; color: #2d3748; }
            QLineEdit:focus { border: 2px solid #667eea; background-color: white; }
        """)
        self.input_field.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("🚀")
        self.send_button.setFixedSize(44, 44)
        self.send_button.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #667eea,stop:1 #764ba2);
                color: white; border: none; border-radius: 20px; font-size: 16px; font-weight: bold; }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5568d3,stop:1 #63398b); }
            QPushButton:disabled { background: #cccccc; }
        """)
        self.send_button.clicked.connect(self.send_message)

        layout.addWidget(self.input_field, 1)
        layout.addWidget(self.send_button)
        return container

    def send_message(self):
        message = self.input_field.text().strip()
        if not message:
            return
        ts = datetime.now().strftime("%H:%M %p")
        self.add_task("👤", "Tú", message, ts, "completed")
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self._current_response_item = self.add_task("✨", "Lune", "▋", ts, "working")
        self.ai_worker = AIWorker(self.ai_manager, message)
        self.ai_worker.token_received.connect(self.on_token_received)
        self.ai_worker.response_ready.connect(self.on_response_ready)
        self.ai_worker.error_occurred.connect(self.on_error)
        self.ai_worker.start()

    def on_token_received(self, partial_text):
        if self._current_response_item:
            self._current_response_item.update_text(partial_text + " ▋")
            self._scroll_to_bottom()

    def on_response_ready(self, response):
        try:
            if self._current_response_item:
                self._current_response_item.update_text(response)
            log_info("Respuesta completada")
            self.voice.speak(response)
        except Exception as e:
            log_error(f"Error: {e}")
        finally:
            self._current_response_item = None
            self.input_field.setEnabled(True)
            self.send_button.setEnabled(True)
            self.input_field.setFocus()
            self._scroll_to_bottom()

    def on_error(self, error):
        log_error(f"Error en AI: {error}")
        if self._current_response_item:
            self._current_response_item.update_text(f"❌ {error}")
        self._current_response_item = None
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_field.setFocus()
        self._scroll_to_bottom()

    def add_task(self, icon, title, description, timestamp, status="pending"):
        task = TaskItem(icon, title, description, timestamp, status)
        self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, task)
        self.tasks.append(task)
        self._scroll_to_bottom()
        return task

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def check_ai_providers(self):
        if not self.ai_manager.get_available_providers():
            QMessageBox.warning(self, "⚠️ Aviso", "Ollama no disponible.\nEjecuta: ollama serve")

    def show_menu(self):
        menu = QMenu()
        menu.addAction("💬 Limpiar Chat", self.clear_chat)
        menu.addAction("ℹ️ Acerca de", self.show_about)
        menu.addSeparator()
        menu.addAction("❌ Salir", self.close_application)
        menu.exec(QCursor.pos())

    def clear_chat(self):
        reply = QMessageBox.question(self, "Limpiar Chat", "¿Limpiar todo el chat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for task in self.tasks:
                task.deleteLater()
            self.tasks.clear()
            welcome = QLabel("👋 ¡Hola de nuevo! ¿En qué puedo ayudarte?")
            welcome.setStyleSheet("QLabel { color: #718096; font-size: 14px; padding: 20px; }")
            welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tasks_layout.insertWidget(0, welcome)
            self.ai_manager.clear_history()

    def show_about(self):
        info = self.ai_manager.get_provider_status()
        pt = "\n".join([f"  • {k}: {'✅' if v else '❌'}" for k, v in info.items()])
        voz = "✅ gTTS activa" if self.voice.available else "❌ Instala: pip install gtts pygame"
        QMessageBox.information(self, "Acerca de", f"🌙 Lune CD v5\n\nProveedores:\n{pt}\n\nVoz: {voz}")

    def apply_theme(self):
        if self.config.get("ui", "theme", default="light") == "dark":
            self.setStyleSheet("QMainWindow, QWidget { background-color: #1a202c; }")

    def close_application(self):
        log_info("Aplicación cerrada")
        self.close()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")
    app.setApplicationVersion("5")
    window = LuneCDWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()