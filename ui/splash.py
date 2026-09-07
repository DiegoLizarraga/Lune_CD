"""
splash.py — Pantalla de inicio con el video de bienvenida.

POR QUÉ ESTÁ ESTRUCTURADO ASÍ
-----------------------------
El problema anterior: el fondo de estrellas era el widget central y el video
colgaba DE ÉL. Ese fondo repinta sus 800x600 completos 60 veces por segundo,
mientras que el video solo se refresca a 24 fps — así que lo tapaba de negro
entre fotograma y fotograma y no se veía nada.

Ahora las estrellas son un HERMANO del contenido, mandado al fondo con
`lower()`, y el QVideoWidget usa ventana nativa (`WA_NativeWindow`). Con su
propio HWND, ningún QPainter del resto de la app puede pintar sobre él. Es la
solución robusta: no depende de recortes ni del orden de repintado de Qt.

La ventana principal la crea `main()` mediante el callback `al_terminar`, no
esta clase. Así en ningún momento existen dos ventanas a la vez en la barra de
tareas, y la pantalla de inicio se destruye limpiamente.
"""
import random
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QPainter

from nucleo.config import Config
from nucleo.utils import log_info, log_error

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_OK = True
except ImportError:
    _MULTIMEDIA_OK = False

RUTA_VIDEO = Path(__file__).parent.parent / "assets" / "inicio.mp4"

# Si el video no arranca en este tiempo, se entra a la app igualmente para no
# dejar al usuario mirando un marco negro.
MS_RENDIRSE = 6000


class FondoEstrellas(QWidget):
    """Estrellas cayendo. Va SIEMPRE al fondo, nunca por encima del video."""

    def __init__(self, parent=None, animar=True):
        super().__init__(parent)
        self.estrellas = []
        self.colores = [QColor("#FFE000"), QColor("#00E5FF")]
        self.animar = animar
        # Deja pasar los clics al contenido que tiene encima
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        if animar:
            for _ in range(100):
                self.crear_estrella()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.animar_estrellas)
            self.timer.start(33)          # ~30 fps, de sobra y más barato

    def crear_estrella(self):
        self.estrellas.append([
            random.randint(0, 900), random.randint(0, 700),
            random.randint(2, 4), random.uniform(0.5, 2.0),
            random.choice(self.colores),
        ])

    def animar_estrellas(self):
        alto = max(1, self.height())
        for e in self.estrellas:
            e[1] += e[3]
            if e[1] > alto:
                e[1] = 0
                e[0] = random.randint(0, max(1, self.width()))
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080B16"))
        for x, y, tamano, _v, color in self.estrellas:
            painter.fillRect(int(x), int(y), tamano, tamano, color)
        painter.end()


class PantallaInicio(QMainWindow):
    def __init__(self, al_terminar=None):
        super().__init__()
        self._al_terminar = al_terminar
        self._terminado = False

        self.setWindowTitle("Lune CD — Iniciando…")
        self.resize(800, 600)
        self._centrar()

        # Central plano, sin paintEvent propio: nada compite con el video.
        central = QWidget()
        central.setStyleSheet("background-color:#080B16;")
        self.setCentralWidget(central)

        # Estrellas: hermano del contenido, al fondo del z-order.
        try:
            animar = Config().feature("fondo_estrellas", True)
        except Exception:
            animar = True
        self.fondo = FondoEstrellas(central, animar=animar)
        self.fondo.setGeometry(central.rect())
        self.fondo.lower()

        raiz = QVBoxLayout(central)
        raiz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        raiz.setSpacing(16)

        # ── Marco del video ──
        self.marco_video = QFrame()
        self.marco_video.setFixedSize(640, 360)
        self.marco_video.setStyleSheet(
            "QFrame{background-color:#0F1424;border:4px solid #00E5FF;}"
        )
        marco_layout = QVBoxLayout(self.marco_video)
        marco_layout.setContentsMargins(4, 4, 4, 4)

        self.reproductor = None
        if _MULTIMEDIA_OK and RUTA_VIDEO.exists():
            self._montar_video(marco_layout)
        else:
            motivo = ("Falta PyQt6.QtMultimedia" if not _MULTIMEDIA_OK
                      else f"No encontré {RUTA_VIDEO.name}")
            log_error(f"[splash] Sin video: {motivo}")
            aviso = QLabel(motivo)
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            aviso.setStyleSheet("color:#97A6C4;border:none;background:transparent;")
            marco_layout.addWidget(aviso)
            QTimer.singleShot(1500, self.entrar)

        raiz.addWidget(self.marco_video, 0, Qt.AlignmentFlag.AlignCenter)

        # ── Título ──
        titulo = QLabel("L U N E   C D")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setStyleSheet(
            "color:#FFE000;font-size:32px;font-weight:bold;letter-spacing:4px;"
            "background:transparent;border:none;"
        )
        raiz.addWidget(titulo)

        # ── Botón de saltar ──
        self.boton_entrar = QPushButton("SALTAR VIDEO / INICIAR SISTEMA")
        self.boton_entrar.setFixedSize(300, 50)
        self.boton_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_entrar.setStyleSheet("""
            QPushButton {
                background-color:#080B16; color:#00E5FF; border:3px solid #00E5FF;
                font-size:14px; font-weight:bold;
            }
            QPushButton:hover { background-color:#00E5FF; color:#080B16; }
        """)
        self.boton_entrar.clicked.connect(self.entrar)
        raiz.addWidget(self.boton_entrar, 0, Qt.AlignmentFlag.AlignCenter)

        # ── Elegir modo al abrir: Completo · Bajos recursos · Patata ──────────
        # Se recuerda en config (interfaz.modo). Si no eliges, al acabar el
        # video sigue con el recordado tras una cuenta atrás corta.
        try:
            self.modo_recordado = str(Config().get("interfaz", "modo", "web") or "web")
        except Exception:
            self.modo_recordado = "web"
        self.modo_elegido = None
        self._cuenta = 0
        self._timer_cuenta = QTimer(self)
        self._timer_cuenta.timeout.connect(self._tic_cuenta)

        fila = QHBoxLayout(); fila.setSpacing(10)
        self.botones_modo = {}
        for modo, texto, tip in (
            ("web", "COMPLETO", "Piel web animada, mascota en video, tema Nube/Local"),
            ("nativo", "BAJOS RECURSOS", "Interfaz nativa ligera: sin animaciones ni videos"),
            ("patata", "PATATA", "Solo terminal: texto y caritas :D  (sin Qt, sin imágenes)"),
        ):
            b = QPushButton(texto)
            b.setToolTip(tip); b.setFixedSize(190, 40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, m=modo: self._elegir(m))
            self.botones_modo[modo] = b
            fila.addWidget(b)
        self._pintar_botones_modo()
        cont = QWidget(); cont.setStyleSheet("background:transparent;"); cont.setLayout(fila)
        raiz.addWidget(cont, 0, Qt.AlignmentFlag.AlignCenter)
        pista = QLabel("¿Cómo abrimos hoy?  Elige un modo o espera: sigue con el que usaste la última vez.")
        pista.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pista.setStyleSheet("color:#6E7D9E;font-size:11px;background:transparent;border:none;")
        raiz.addWidget(pista)

    # ── Selector de modo ──────────────────────────────────────────────────────
    def _pintar_botones_modo(self, cuenta: int = 0):
        for modo, b in self.botones_modo.items():
            activo = (modo == self.modo_recordado)
            base = ("background-color:#00E5FF;color:#080B16;border:3px solid #00E5FF;"
                    if activo else
                    "background-color:#080B16;color:#97A6C4;border:2px solid #2E3D66;")
            b.setStyleSheet("QPushButton{" + base + "font-size:12px;font-weight:bold;letter-spacing:1px;}"
                            "QPushButton:hover{background-color:#00E5FF;color:#080B16;border-color:#00E5FF;}")
            etiqueta = {"web": "COMPLETO", "nativo": "BAJOS RECURSOS", "patata": "PATATA"}[modo]
            b.setText(f"{etiqueta} · {cuenta}" if (activo and cuenta) else etiqueta)

    def _elegir(self, modo: str):
        """El usuario eligió: se guarda y se entra ya."""
        self._timer_cuenta.stop()
        self.modo_elegido = modo
        try:
            Config().set("interfaz", "modo", modo)
        except Exception as e:
            log_error(f"[splash] no pude guardar el modo: {e}")
        log_info(f"[splash] modo elegido: {modo}")
        self.entrar()

    def _iniciar_cuenta(self, segundos: int = 4):
        """Acabó el video: cuenta atrás sobre el modo recordado; un clic la corta."""
        if self._terminado or self.modo_elegido:
            return
        self._cuenta = segundos
        self._pintar_botones_modo(self._cuenta)
        self._timer_cuenta.start(1000)

    def _tic_cuenta(self):
        self._cuenta -= 1
        if self._cuenta <= 0:
            self._timer_cuenta.stop()
            self.entrar()
        else:
            self._pintar_botones_modo(self._cuenta)

        # Red de seguridad: si en MS_RENDIRSE el video no ha avanzado, entramos.
        QTimer.singleShot(MS_RENDIRSE, self._rendirse_si_no_arranco)

    # ── Video ─────────────────────────────────────────────────────────────────
    def _montar_video(self, marco_layout):
        # OJO: nada de WA_NativeWindow aquí.
        #
        # Ponerlo sobre un widget que todavía NO tiene padre hace que Qt lo cree
        # como ventana de nivel superior independiente. El resultado era una
        # ventana fantasma suelta y el splash quedándose con IsWindowVisible =
        # False: el proceso corría, el video sonaba, y en pantalla no había nada.
        #
        # No hace falta: el fondo de estrellas ya es HERMANO del contenido y no
        # su padre, así que nadie repinta encima del video.
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color:#000000;")

        self.reproductor = QMediaPlayer()
        self.salida_audio = QAudioOutput()
        self.reproductor.setAudioOutput(self.salida_audio)
        self.reproductor.setVideoOutput(self.video_widget)
        self.reproductor.mediaStatusChanged.connect(self._on_estado_media)
        self.reproductor.errorOccurred.connect(self._on_error_video)

        marco_layout.addWidget(self.video_widget)
        self.reproductor.setSource(QUrl.fromLocalFile(str(RUTA_VIDEO)))

        # play() cuando el widget ya está en el layout y la ventana mostrada:
        # llamarlo antes deja al reproductor sin superficie donde pintar.
        QTimer.singleShot(0, self._reproducir)

    def _reproducir(self):
        try:
            self.reproductor.play()
            log_info(f"[splash] Reproduciendo {RUTA_VIDEO.name}")
        except Exception as e:
            log_error(f"[splash] No pude reproducir: {e}")
            self.entrar()

    def _on_estado_media(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            log_info("[splash] Video terminado")
            self._iniciar_cuenta()     # unos segundos para elegir modo; luego sigue solo

    def _on_error_video(self, *_args):
        error = self.reproductor.errorString() if self.reproductor else "?"
        log_error(f"[splash] Error de video: {error}")
        # Puede ser un aviso no fatal: se confirma antes de rendirse.
        QTimer.singleShot(2000, self._rendirse_si_no_arranco)

    def _rendirse_si_no_arranco(self):
        if self._terminado:
            return
        pos = self.reproductor.position() if self.reproductor else 0
        if pos > 0:
            return          # está reproduciendo, se le deja terminar
        log_error("[splash] El video no arrancó; entrando igualmente")
        self.entrar()

    # ── Transición ────────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.centralWidget():
            self.fondo.setGeometry(self.centralWidget().rect())
            self.fondo.lower()

    def _centrar(self):
        pantalla = self.screen()
        if pantalla:
            centro = pantalla.availableGeometry().center()
            marco = self.frameGeometry()
            marco.moveCenter(centro)
            self.move(marco.topLeft())

    def entrar(self):
        """
        Cierra la pantalla de inicio y avisa a main() para que abra la app.

        La guarda `_terminado` es imprescindible: el fin del video, el botón de
        saltar y el temporizador de seguridad pueden dispararse casi a la vez, y
        sin ella se abrían DOS ventanas principales.
        """
        if self._terminado:
            return
        self._terminado = True

        if self.reproductor is not None:
            try:
                self.reproductor.stop()
                self.reproductor.setSource(QUrl())
            except Exception:
                pass
        if getattr(self, "fondo", None) and self.fondo.animar:
            self.fondo.timer.stop()

        # Ocultar ANTES de crear la principal: si no, durante un instante hay
        # dos ventanas y parece que la app se abre por duplicado.
        self.hide()
        self.close()

        if self._al_terminar:
            self._al_terminar()

        self.deleteLater()

    def closeEvent(self, event):
        """Cerrar con la X debe abrir la app, no dejar el proceso huérfano."""
        if not self._terminado:
            event.ignore()
            self.entrar()
            return
        event.accept()
