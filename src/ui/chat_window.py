"""
Ventana de chat para interactuar con Lune
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QLineEdit, QPushButton, QLabel)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

class ChatWorker(QThread):
    """Worker para procesar mensajes en background"""
    response_ready = pyqtSignal(str)
    
    def __init__(self, ai_manager, message):
        super().__init__()
        self.ai_manager = ai_manager
        self.message = message
        
    def run(self):
        response = self.ai_manager.get_response(self.message)
        self.response_ready.emit(response)

class ChatWindow(QWidget):
    """Ventana de chat moderna"""
    
    def __init__(self, ai_manager, parent=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.chat_history = []
        self.init_ui()
        
    def init_ui(self):
        """Inicializar interfaz"""
        self.setWindowTitle("💬 Chat con Lune")
        self.setGeometry(100, 100, 500, 600)
        
        # Layout principal
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QLabel("🌙 Lune CD - Tu Asistente Virtual")
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                padding: 15px;
                border-radius: 10px;
            }
        """)
        layout.addWidget(header)
        
        # Área de chat
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 2px solid #e9ecef;
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.chat_display)
        
        # Input área
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Escribe tu mensaje aquí...")
        self.message_input.setStyleSheet("""
            QLineEdit {
                padding: 12px;
                border: 2px solid #667eea;
                border-radius: 20px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #764ba2;
            }
        """)
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Enviar 🚀")
        self.send_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 20px;
                padding: 12px 25px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5568d3, stop:1 #63398b);
            }
            QPushButton:pressed {
                background: #4c5cbc;
            }
        """)
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        
        layout.addLayout(input_layout)
        
        self.setLayout(layout)
        
        # Mensaje de bienvenida
        self.add_message("Lune", "¡Hola! 👋 Soy Lune, tu asistente virtual. ¿En qué puedo ayudarte hoy?")
        
    def send_message(self):
        """Enviar mensaje"""
        message = self.message_input.text().strip()
        if not message:
            return
            
        # Mostrar mensaje del usuario
        self.add_message("Tú", message)
        self.message_input.clear()
        
        # Deshabilitar input mientras procesa
        self.message_input.setEnabled(False)
        self.send_button.setEnabled(False)
        
        # Mostrar indicador de "escribiendo..."
        self.add_message("Lune", "💭 Pensando...")
        
        # Procesar en background
        self.worker = ChatWorker(self.ai_manager, message)
        self.worker.response_ready.connect(self.display_response)
        self.worker.start()
        
    def display_response(self, response):
        """Mostrar respuesta de la IA"""
        # Remover "pensando..."
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.select(cursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()  # Eliminar línea vacía
        
        # Mostrar respuesta
        self.add_message("Lune", response)
        
        # Rehabilitar input
        self.message_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.message_input.setFocus()
        
    def add_message(self, sender, message):
        """Agregar mensaje al chat"""
        is_lune = sender == "Lune"
        
        html = f"""
        <div style='margin: 10px 0;'>
            <div style='
                background: {"#667eea" if is_lune else "#e9ecef"};
                color: {"white" if is_lune else "black"};
                padding: 12px 15px;
                border-radius: 18px;
                max-width: 80%;
                float: {"left" if is_lune else "right"};
                clear: both;
            '>
                <strong>{sender}:</strong><br>
                {message}
            </div>
            <div style='clear: both;'></div>
        </div>
        """
        
        self.chat_display.append(html)
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )