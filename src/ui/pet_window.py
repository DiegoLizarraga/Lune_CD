"""
Ventana principal de la mascota Lune
Siempre visible, transparente, draggable
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QMenu
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor, QPainter, QMovie
from src.ui.chat_window import ChatWindow
from src.ai.ai_manager import AIManager

class LunePetWindow(QWidget):
    """Ventana flotante de la mascota Lune"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.ai_manager = AIManager(config)
        self.chat_window = None
        self.dragging = False
        self.offset = QPoint()
        
        self.init_ui()
        self.init_animations()
        self.init_behaviors()
        
    def init_ui(self):
        """Inicializar interfaz"""
        # Configuración de ventana
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |      # Sin bordes
            Qt.WindowType.WindowStaysOnTopHint |     # Siempre encima
            Qt.WindowType.Tool                        # No aparece en taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # Transparente
        
        # Tamaño de la mascota
        self.setFixedSize(150, 150)
        
        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label para el sprite de Lune
        self.sprite_label = QLabel()
        self.sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sprite_label)
        
        self.setLayout(layout)
        
        # Posición inicial (esquina inferior derecha)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 200, screen.height() - 200)
        
        # Tooltip
        self.setToolTip("🌙 Soy Lune!\n✨ Click para hablar\n👉 Click derecho para opciones")
        
    def init_animations(self):
        """Inicializar animaciones"""
        # Cargar GIF animado de Lune
        self.movie = QMovie("src/assets/animations/lune_idle.gif")
        self.sprite_label.setMovie(self.movie)
        self.movie.start()
        
        # Timer para animaciones aleatorias
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.random_animation)
        self.animation_timer.start(5000)  # Cada 5 segundos
        
    def init_behaviors(self):
        """Inicializar comportamientos"""
        # Estados de la mascota
        self.state = "idle"  # idle, talking, thinking, happy, sleeping
        
        # Frases aleatorias
        self.random_phrases = [
            "💭 ¿En qué piensas?",
            "✨ ¡Hola! ¿Necesitas ayuda?",
            "🌙 Estoy aquí para ti",
            "💫 ¿Qué quieres saber?",
            "🎯 ¡Pregúntame lo que quieras!"
        ]
        
    def random_animation(self):
        """Ejecutar animación aleatoria"""
        import random
        animations = ["bounce", "wave", "spin", "blink"]
        animation = random.choice(animations)
        
        if animation == "bounce":
            self.bounce_animation()
        elif animation == "wave":
            self.wave_animation()
            
    def bounce_animation(self):
        """Animación de rebote"""
        original_y = self.y()
        
        # Animación simple usando QTimer
        step = 0
        def animate():
            nonlocal step
            if step < 10:
                offset = abs(5 - step) * 3
                self.move(self.x(), original_y - offset)
                step += 1
                QTimer.singleShot(50, animate)
            else:
                self.move(self.x(), original_y)
                
        animate()
        
    def wave_animation(self):
        """Animación de saludo"""
        # Cambiar sprite temporalmente
        self.movie.stop()
        wave_movie = QMovie("src/assets/animations/lune_wave.gif")
        self.sprite_label.setMovie(wave_movie)
        wave_movie.start()
        
        # Volver a idle después de 2 segundos
        QTimer.singleShot(2000, lambda: self.return_to_idle())
        
    def return_to_idle(self):
        """Volver a estado idle"""
        self.sprite_label.setMovie(self.movie)
        self.movie.start()
        self.state = "idle"
        
    def mousePressEvent(self, event):
        """Manejar clicks del mouse"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Click izquierdo: abrir chat
            self.open_chat()
        elif event.button() == Qt.MouseButton.RightButton:
            # Click derecho: mostrar menú
            self.show_context_menu(event.globalPosition().toPoint())
        else:
            # Iniciar drag
            self.dragging = True
            self.offset = event.position().toPoint()
            
    def mouseReleaseEvent(self, event):
        """Soltar mouse"""
        self.dragging = False
        
    def mouseMoveEvent(self, event):
        """Mover ventana arrastrando"""
        if self.dragging:
            self.move(self.mapToGlobal(event.position().toPoint() - self.offset))
            
    def open_chat(self):
        """Abrir ventana de chat"""
        if self.chat_window is None or not self.chat_window.isVisible():
            self.chat_window = ChatWindow(self.ai_manager, self)
            self.chat_window.show()
        else:
            self.chat_window.activateWindow()
            
    def show_context_menu(self, position):
        """Mostrar menú contextual"""
        menu = QMenu()
        
        # Opciones del menú
        chat_action = menu.addAction("💬 Abrir Chat")
        menu.addSeparator()
        
        settings_action = menu.addAction("⚙️ Configuración")
        about_action = menu.addAction("ℹ️ Acerca de")
        menu.addSeparator()
        
        exit_action = menu.addAction("❌ Salir")
        
        # Ejecutar menú
        action = menu.exec(position)
        
        if action == chat_action:
            self.open_chat()
        elif action == settings_action:
            self.open_settings()
        elif action == about_action:
            self.show_about()
        elif action == exit_action:
            self.close_application()
            
    def open_settings(self):
        """Abrir configuración"""
        from src.ui.settings_window import SettingsWindow
        settings = SettingsWindow(self.config, self)
        settings.exec()
        # Añadir import al inicio
from src.agents.agent_orchestrator import AgentOrchestrator

# En __init__, después de self.ai_manager:
self.orchestrator = AgentOrchestrator(self.ai_manager)

# Actualizar método open_chat:
def open_chat(self):
    """Abrir ventana de chat con agentes"""
    if self.chat_window is None or not self.chat_window.isVisible():
        # Importar la nueva ventana de chat
        from src.ui.enhanced_chat_window import EnhancedChatWindow
        self.chat_window = EnhancedChatWindow(self.ai_manager, self)
        self.chat_window.show()
    else:
        self.chat_window.activateWindow()
        
    def show_about(self):
        """Mostrar información"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Acerca de Lune CD",
            "🌙 Lune CD v4.0\n\n"
            "Tu mascota virtual inteligente\n"
            "Powered by Groq & Ollama\n\n"
            "Creado con ❤️ por Diego Lizarraga"
        )
        
    def close_application(self):
        """Cerrar aplicación"""
        QApplication.quit()