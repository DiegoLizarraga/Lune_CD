"""
avatar_overlay.py — Lune como mascota flotante sobre el escritorio.

Ventana sin bordes, transparente, siempre encima y arrastrable que muestra la
cara de Lune (los sprites/vídeos de lune_face) y reacciona a las emociones del
modelo (<|ACT|>, ver lune_core/marcadores). Es la base del "modo mascota" del
ROADMAP; el render VRM 3D se enchufará aquí cuando PyQt6-WebEngine funcione en
este equipo (hoy su DLL choca con PyQt6 6.11).

Mecánica de ventana portada de la mascota Electron de AIRI a sus equivalentes Qt:
    FramelessWindowHint | WindowStaysOnTopHint | Tool  ≈ frameless/always-on-top/panel
    WA_TranslucentBackground                            ≈ transparent, sin sombra
    windowHandle().startSystemMove()                    ≈ arrastre nativo
    QSystemTrayIcon                                     ≈ icono de bandeja

Lo que NO se hace aún (necesita verse en pantalla para ajustarlo): click-through
con hit-test por alpha. Aquí la ventana es interactiva y arrastrable.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QSystemTrayIcon, QApplication,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QIcon

import lune_face
from lune_face import LuneFaceWidget, estado_desde_emocion


class AvatarOverlay(QMainWindow):
    """Mascota flotante. `config` persiste su posición (sección 'avatar')."""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool                 # fuera de la barra de tareas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        central = QWidget()
        central.setStyleSheet("background:transparent;")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)

        self.cara = LuneFaceWidget()
        # En el overlay el "escenario" es transparente, sin el marco neón.
        self.cara.setStyleSheet("LuneFaceWidget{background:transparent;border:none;}")
        lay.addWidget(self.cara)

        self.resize(210, 280)
        self._restaurar_posicion()
        self._construir_bandeja()

        self._arrastrando_desde = None

    # ── Emoción ────────────────────────────────────────────────────────────────
    def set_emocion(self, emocion: str, ms: int = 6000):
        """Recibe una emoción canónica (<|ACT|>) y la muestra."""
        self.cara.set_state(estado_desde_emocion(emocion), auto_revert_ms=ms)

    def set_estado(self, estado: str, ms: int = 0):
        """Recibe un estado directo de lune_face (thinking, typing…)."""
        self.cara.set_state(estado, auto_revert_ms=ms)

    # ── Arrastre (nativo) ──────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            wh = self.windowHandle()
            if wh is not None and hasattr(wh, "startSystemMove"):
                wh.startSystemMove()          # arrastre nativo del SO (Qt ≥ 5.15)
            else:
                self._arrastrando_desde = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        # Respaldo por si startSystemMove no está disponible.
        if self._arrastrando_desde is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._arrastrando_desde)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._arrastrando_desde = None
        self._guardar_posicion()
        super().mouseReleaseEvent(ev)

    # ── Posición persistida ────────────────────────────────────────────────────
    def _restaurar_posicion(self):
        if not self.config:
            self._esquina_inferior_derecha()
            return
        x = self.config.get("avatar", "overlay_x", None)
        y = self.config.get("avatar", "overlay_y", None)
        if isinstance(x, int) and isinstance(y, int) and self._dentro_de_pantalla(x, y):
            self.move(x, y)
        else:
            self._esquina_inferior_derecha()

    def _guardar_posicion(self):
        if self.config:
            self.config.set("avatar", "overlay_x", self.x())
            self.config.set("avatar", "overlay_y", self.y())

    def _dentro_de_pantalla(self, x, y) -> bool:
        for s in QApplication.screens():
            if s.availableGeometry().contains(QPoint(x + 20, y + 20)):
                return True
        return False

    def _esquina_inferior_derecha(self):
        pantalla = self.screen() or QApplication.primaryScreen()
        if pantalla:
            g = pantalla.availableGeometry()
            self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)

    # ── Bandeja ────────────────────────────────────────────────────────────────
    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        icono = QIcon()
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lune_icon.png")
        if os.path.exists(ruta):
            icono = QIcon(ruta)
        self.tray = QSystemTrayIcon(icono, self)
        self.tray.setToolTip("Lune · mascota")
        menu = QMenu()
        act_mostrar = QAction("Mostrar / ocultar", self)
        act_mostrar.triggered.connect(self._alternar)
        act_centrar = QAction("Llevar a la esquina", self)
        act_centrar.triggered.connect(lambda: (self._esquina_inferior_derecha(), self._guardar_posicion()))
        act_cerrar = QAction("Cerrar mascota", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_mostrar); menu.addAction(act_centrar)
        menu.addSeparator(); menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._alternar() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _alternar(self):
        self.hide() if self.isVisible() else (self.showNormal(), self.raise_())

    def closeEvent(self, ev):
        self._guardar_posicion()
        if getattr(self, "tray", None):
            self.tray.hide()
        if getattr(self.cara, "_player", None):
            self.cara._player.stop()
        ev.accept()
