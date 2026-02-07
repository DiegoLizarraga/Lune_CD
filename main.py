import sys
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMessageBox, QMenu, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import (
    QIcon, QFont, QColor, QPalette, QPixmap,
    QCursor
)

from config import Config
from ai_manager import AIManager
from utils import Logger, log_info, log_error


logger = Logger()


class TaskItem(QFrame):
    """Widget para mostrar un elemento de tarea/mensaje"""
    
    def __init__(self, icon_text: str, title: str, description: str, 
                 timestamp: str, status: str = "pending", parent=None):
        super().__init__(parent)
        self.status = status
        self.setStyleSheet(self._get_stylesheet())
        
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Ícono
        icon_label = QLabel(icon_text)
        icon_label.setStyleSheet(self._get_icon_stylesheet())
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(40, 40)
        
        # Contenido
        content_layout = QVBoxLayout()
        
        # Título
        title_label = QLabel(title)
        title_font = QFont("Arial", 11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2d3748;")
        
        # Descripción
        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #718096; font-size: 12px;")
        desc_label.setWordWrap(True)
        
        # Timestamp
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("color: #a0aec0; font-size: 11px;")
        
        content_layout.addWidget(title_label)
        content_layout.addWidget(desc_label)
        content_layout.addWidget(time_label)
        content_layout.setSpacing(5)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(icon_label)
        layout.addLayout(content_layout, 1)
        layout.addStretch()
    
    def _get_stylesheet(self) -> str:
        """Obtener stylesheet según el estado"""
        bg_color = "#f8f9fa"
        border_color = "#e9ecef"
        
        if self.status == "error":
            bg_color = "#ffe0e0"
            border_color = "#ffcccc"
        
        return f"""
            TaskItem {{
                background-color: {bg_color};
                border-radius: 10px;
                border: 1px solid {border_color};
                padding: 12px;
                margin: 5px 0px;
            }}
            TaskItem:hover {{
                background-color: #f0f3f7;
                border: 1px solid #d9e0e7;
            }}
        """
    
    def _get_icon_stylesheet(self) -> str:
        """Obtener stylesheet del ícono"""
        color = "#667eea"
        
        if self.status == "error":
            color = "#ff6b6b"
        elif self.status == "working":
            color = "#4299e1"
        elif self.status == "completed":
            color = "#48bb78"
        
        return f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 20px;
                padding: 8px;
                font-weight: bold;
                font-size: 18px;
            }}
        """


class AIWorker(QThread):
    """Worker para procesar IA en background"""
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ai_manager: AIManager, message: str):
        super().__init__()
        self.ai_manager = ai_manager
        self.message = message
    
    def run(self):
        try:
            # Ejecutar llamada asíncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            system_prompt = """Eres Lune, una asistente virtual inteligente y amigable. 
Eres experta en escribir, investigar y automatizar tareas. 
Responde de manera clara, concisa y útil.
Siempre sé amable y profesional."""
            
            response = loop.run_until_complete(
                self.ai_manager.chat(self.message, system_prompt)
            )
            
            if response:
                self.response_ready.emit(response)
            else:
                self.error_occurred.emit("La IA no retornó una respuesta")
                
        except Exception as e:
            log_error(f"Error en AIWorker: {str(e)}")
            self.error_occurred.emit(f"Error: {str(e)}")
        finally:
            if 'loop' in locals():
                loop.close()


class LuneCDWindow(QMainWindow):
    """Ventana principal de Lune CD v4.5"""
    
    def __init__(self):
        super().__init__()
        
        try:
            # Cargar configuración
            self.config = Config()
            self.ai_manager = AIManager(self.config)
            
            # Variables
            self.tasks = []
            self.ai_worker = None
            self.tasks_layout = None
            self.tasks_container = None
            
            log_info("Aplicación iniciada")
            
            # Inicializar UI
            self.init_ui()
            self.apply_theme()
            self.check_ai_providers()
            
        except Exception as e:
            log_error(f"Error al inicializar: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error al inicializar la aplicación: {str(e)}")
            sys.exit(1)
    
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        
        # Configurar ventana
        self.setWindowTitle("🌙 Lune CD v4.5 - Virtual Assistant")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(700, 600)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ===== HEADER =====
        header = self._create_header()
        main_layout.addWidget(header)
        
        # ===== ÁREA DE TAREAS/CHAT =====
        tasks_area = self._create_tasks_area()
        main_layout.addWidget(tasks_area, 1)
        
        # ===== INPUT AREA =====
        input_area = self._create_input_area()
        main_layout.addWidget(input_area)
        
        central_widget.setLayout(main_layout)
    
    def _create_header(self) -> QFrame:
        """Crear barra de encabezado"""
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea,
                    stop:1 #764ba2
                );
                border-bottom: 2px solid #5568d3;
            }
        """)
        header.setMaximumHeight(60)
        
        layout = QHBoxLayout(header)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # Logo/Título
        title = QLabel("🌙 Virtual Assistant")
        title_font = QFont("Arial", 16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: white;")
        
        subtitle = QLabel("Powered by AI")
        subtitle_font = QFont("Arial", 10)
        subtitle.setFont(subtitle_font)
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.8);")
        
        title_layout = QVBoxLayout()
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        title_layout.setSpacing(0)
        
        layout.addLayout(title_layout)
        layout.addStretch()
        
        # Botón de menú
        menu_button = QPushButton("⋮")
        menu_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.4);
            }
        """)
        menu_button.clicked.connect(self.show_menu)
        menu_button.setFixedSize(40, 40)
        
        layout.addWidget(menu_button)
        
        return header
    
    def _create_tasks_area(self) -> QFrame:
        """Crear área de tareas"""
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f8f9fa;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background-color: #cbd5e0;
                border-radius: 4px;
            }
        """)
        scroll.setWidgetResizable(True)
        
        self.tasks_container = QFrame()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setSpacing(8)
        self.tasks_layout.setContentsMargins(15, 15, 15, 15)
        
        # Mensaje de bienvenida
        welcome_label = QLabel("👋 ¡Hola! Soy Lune, tu asistente virtual.\n¿En qué puedo ayudarte hoy?")
        welcome_label.setStyleSheet("""
            QLabel {
                color: #718096;
                font-size: 14px;
                padding: 20px;
            }
        """)
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tasks_layout.addWidget(welcome_label)
        
        self.tasks_layout.addStretch()
        
        scroll.setWidget(self.tasks_container)
        layout.addWidget(scroll)
        
        return container
    
    def _create_input_area(self) -> QFrame:
        """Crear área de entrada"""
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-top: 1px solid #e9ecef;
            }
        """)
        container.setMaximumHeight(80)
        
        layout = QHBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 12, 15, 12)
        
        # Input
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Escribe tu mensaje aquí...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #f8f9fa;
                border: 2px solid #e9ecef;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 13px;
                color: #2d3748;
            }
            QLineEdit:focus {
                border: 2px solid #667eea;
                background-color: white;
            }
            QLineEdit::placeholder {
                color: #a0aec0;
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        
        # Botón enviar
        self.send_button = QPushButton("🚀")
        self.send_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea,
                    stop:1 #764ba2
                );
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5568d3,
                    stop:1 #63398b
                );
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4c5cbc,
                    stop:1 #5528aa
                );
            }
        """)
        self.send_button.setFixedSize(44, 44)
        self.send_button.clicked.connect(self.send_message)
        
        layout.addWidget(self.input_field, 1)
        layout.addWidget(self.send_button)
        
        return container
    
    def send_message(self):
        """Enviar mensaje"""
        message = self.input_field.text().strip()
        
        if not message:
            QMessageBox.warning(self, "Aviso", "Por favor escribe un mensaje")
            return
        
        log_info(f"Usuario envía: {message[:50]}...")
        
        # Agregar tarea del usuario
        timestamp = datetime.now().strftime("%H:%M %p")
        self.add_task("👤", "Tú", message, timestamp, "completed")
        
        # Limpiar input
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        
        # Mostrar tarea de procesamiento
        self.add_task("⚙️", "Lune", "Procesando tu mensaje...", timestamp, "working")
        
        # Procesar en background
        self.ai_worker = AIWorker(self.ai_manager, message)
        self.ai_worker.response_ready.connect(self.on_response_ready)
        self.ai_worker.error_occurred.connect(self.on_error)
        self.ai_worker.start()
    
    def on_response_ready(self, response: str):
        """Procesar respuesta de la IA"""
        try:
            # Remover tarea de procesamiento
            if self.tasks_layout.count() > 1:
                item = self.tasks_layout.itemAt(self.tasks_layout.count() - 2)
                if item and item.widget():
                    item.widget().deleteLater()
            
            # Agregar respuesta
            timestamp = datetime.now().strftime("%H:%M %p")
            self.add_task("✨", "Lune", response, timestamp, "completed")
            
            log_info("Respuesta completada")
            
        except Exception as e:
            log_error(f"Error en on_response_ready: {str(e)}")
        finally:
            # Habilitar input
            self.input_field.setEnabled(True)
            self.send_button.setEnabled(True)
            self.input_field.setFocus()
            self._scroll_to_bottom()
    
    def on_error(self, error: str):
        """Manejar error"""
        log_error(f"Error en AI: {error}")
        
        timestamp = datetime.now().strftime("%H:%M %p")
        self.add_task("❌", "Error", f"Error: {error}", timestamp, "error")
        
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_field.setFocus()
        self._scroll_to_bottom()
    
    def add_task(self, icon: str, title: str, description: str, 
                 timestamp: str, status: str = "pending"):
        """Agregar tarea a la lista"""
        task = TaskItem(icon, title, description, timestamp, status)
        
        # Insertar antes del stretch
        self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, task)
        self.tasks.append(task)
        
        # Scroll al final
        self._scroll_to_bottom()
    
    def _scroll_to_bottom(self):
        """Scroll al final"""
        scroll_area = self.tasks_container.parent()
        if isinstance(scroll_area, QScrollArea):
            QTimer.singleShot(100, lambda: scroll_area.verticalScrollBar().setValue(
                scroll_area.verticalScrollBar().maximum()
            ))
    
    def check_ai_providers(self):
        """Verificar disponibilidad de proveedores IA"""
        providers = self.ai_manager.get_available_providers()
        
        if not providers:
            QMessageBox.warning(
                self,
                "⚠️ Aviso",
                "No hay proveedores de IA disponibles.\n\n"
                "Por favor, configura tu API Key de Groq en config.json o\n"
                "asegúrate de que Ollama esté corriendo en http://localhost:11434"
            )
            log_error("No hay proveedores IA disponibles")
        else:
            log_info(f"Proveedores disponibles: {', '.join(providers)}")
    
    def show_menu(self):
        """Mostrar menú contextual"""
        menu = QMenu()
        
        # Información de proveedores
        status = self.ai_manager.get_provider_status()
        status_text = "Estado de proveedores:\n"
        for name, available in status.items():
            status_text += f"  {name}: {'✅' if available else '❌'}\n"
        
        menu.addAction("📊 Estado de Proveedores")
        
        # Opciones
        menu.addAction("💬 Limpiar Chat", self.clear_chat)
        menu.addAction("⚙️ Configuración", self.open_settings)
        menu.addAction("ℹ️ Acerca de", self.show_about)
        menu.addSeparator()
        menu.addAction("❌ Salir", self.close_application)
        
        menu.exec(QCursor.pos())
    
    def clear_chat(self):
        """Limpiar chat"""
        reply = QMessageBox.question(
            self,
            "Limpiar Chat",
            "¿Estás seguro de que quieres limpiar todo el chat?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Limpiar tareas
            for task in self.tasks:
                task.deleteLater()
            self.tasks.clear()
            
            # Agregar mensaje de bienvenida
            welcome_label = QLabel("👋 ¡Hola de nuevo! ¿En qué puedo ayudarte?")
            welcome_label.setStyleSheet("""
                QLabel {
                    color: #718096;
                    font-size: 14px;
                    padding: 20px;
                }
            """)
            welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tasks_layout.insertWidget(0, welcome_label)
            
            self.ai_manager.clear_history()
            log_info("Chat limpiado")
    
    def open_settings(self):
        """Abrir configuración"""
        QMessageBox.information(
            self,
            "Configuración",
            "La configuración se edita en el archivo config.json\n\n"
            "Ubicación: ./config.json\n\n"
            "Después de hacer cambios, reinicia la aplicación."
        )
    
    def show_about(self):
        """Mostrar acerca de"""
        info = self.ai_manager.get_provider_status()
        providers_text = "\n".join([f"  • {k}: {'Disponible ✅' if v else 'No disponible ❌'}" 
                                     for k, v in info.items()])
        
        QMessageBox.information(
            self,
            "Acerca de Lune CD v4.5",
            f"🌙 Lune CD v4.5\n\n"
            f"Tu asistente virtual inteligente\n"
            f"Powered by IA\n\n"
            f"Proveedores disponibles:\n{providers_text}\n\n"
            f"Creado con ❤️\n\n"
            f"© 2024 - Todos los derechos reservados"
        )
    
    def apply_theme(self):
        """Aplicar tema"""
        theme = self.config.get("ui", "theme", default="light")
        
        if theme == "dark":
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #1a202c;
                }
            """)
    
    def close_application(self):
        """Cerrar aplicación"""
        log_info("Aplicación cerrada")
        self.close()
        QApplication.quit()


def main():
    """Función principal"""
    app = QApplication(sys.argv)
    
    # Configuración de la aplicación
    app.setApplicationName("Lune CD")
    app.setApplicationVersion("4.5")
    
    # Crear ventana principal
    window = LuneCDWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()