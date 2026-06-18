"""
splash.py — Pantalla de inicio (pixel art) con video de bienvenida.
Al terminar el video (o al pulsar saltar) abre la ventana principal.
"""
import random
from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QFrame, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QPainter

from config import Config

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_OK = True
except ImportError:
    _MULTIMEDIA_OK = False


class FondoEstrellasPixeladas(QWidget):
    def __init__(self, parent=None, animar=True):
        super().__init__(parent)
        self.estrellas = []
        self.colores = [QColor("#FFE000"), QColor("#00E5FF")] # Amarillo y Azul Cian
        self.animar = animar

        if animar:
            for _ in range(100):
                self.crear_estrella()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.animar_estrellas)
            self.timer.start(16)

    def crear_estrella(self):
        x = random.randint(0, 2000)
        y = random.randint(0, 1500)
        tamano = random.randint(2, 4)
        velocidad = random.uniform(0.5, 2.0)
        color = random.choice(self.colores)
        self.estrellas.append([x, y, tamano, velocidad, color])

    def animar_estrellas(self):
        for estrella in self.estrellas:
            estrella[1] += estrella[3]
            if estrella[1] > self.height():
                estrella[1] = 0
                estrella[0] = random.randint(0, self.width())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080B16"))
        for x, y, tamano, _, color in self.estrellas:
            painter.fillRect(int(x), int(y), tamano, tamano, color)
        painter.end()


class PantallaInicio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lune CD - Iniciando Sistema...")
        self.resize(800, 600)

        try:
            animar = Config().feature("fondo_estrellas", True)
        except Exception:
            animar = True
        self.fondo = FondoEstrellasPixeladas(self, animar=animar)
        self.setCentralWidget(self.fondo)

        layout_principal = QVBoxLayout(self.fondo)
        layout_principal.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Marco del video pixel art
        self.marco_video = QFrame()
        self.marco_video.setFixedSize(640, 360)
        self.marco_video.setStyleSheet("""
            QFrame {
                background-color: #0F1424;
                border: 4px solid #00E5FF;
                padding: 4px;
            }
        """)
        layout_marco = QVBoxLayout(self.marco_video)
        layout_marco.setContentsMargins(0, 0, 0, 0)

        if _MULTIMEDIA_OK:
            self.video_widget = QVideoWidget()
            self.reproductor = QMediaPlayer()
            self.salida_audio = QAudioOutput()

            self.reproductor.setAudioOutput(self.salida_audio)
            self.reproductor.setVideoOutput(self.video_widget)

            ruta_video = Path("inicio.mp4").absolute()
            self.reproductor.setSource(QUrl.fromLocalFile(str(ruta_video)))

            # --- LA MAGIA: CONECTAR EL FINAL DEL VIDEO CON LA APP PRINCIPAL ---
            self.reproductor.mediaStatusChanged.connect(self._revisar_estado_video)

            layout_marco.addWidget(self.video_widget)
            layout_principal.addWidget(self.marco_video)
            self.reproductor.play()
        else:
            error_lbl = QLabel("Multimedia no disponible. Faltan librerías.")
            error_lbl.setStyleSheet("color: white;")
            layout_marco.addWidget(error_lbl)
            layout_principal.addWidget(self.marco_video)

        self.titulo = QLabel("L U N E  C D")
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titulo.setStyleSheet("color: #FFE000; font-size: 32px; font-weight: bold; letter-spacing: 4px;")
        layout_principal.addWidget(self.titulo)

        # Botón para saltar el video
        self.boton_entrar = QPushButton("SALTAR VIDEO / INICIAR SISTEMA")
        self.boton_entrar.setFixedSize(300, 50)
        self.boton_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_entrar.setStyleSheet("""
            QPushButton {
                background-color: #080B16; color: #00E5FF; border: 3px solid #00E5FF;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #00E5FF; color: #080B16; }
        """)
        self.boton_entrar.clicked.connect(self.abrir_app_principal)
        layout_principal.addWidget(self.boton_entrar, alignment=Qt.AlignmentFlag.AlignCenter)

    def _revisar_estado_video(self, status):
        """Verifica si el video ha terminado de reproducirse."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.abrir_app_principal()

    def abrir_app_principal(self):
        """Detiene el video, muestra el chat principal y cierra esta ventana."""
        if _MULTIMEDIA_OK:
            self.reproductor.stop()

        # Import diferido para evitar dependencia circular con main.py
        from main import LuneCDWindow
        self.ventana_principal = LuneCDWindow()
        self.ventana_principal.show()

        # Cerramos la pantalla de inicio
        self.close()
