"""
avatar_overlay.py — Lune como mascota flotante ligera (sprites 2D) sobre el escritorio.

Ventana sin bordes, transparente, siempre encima y arrastrable que muestra los
PNG/MP4 de lune_face y reacciona a las emociones del modelo (<|ACT|>, ver
lune_core/marcadores). Se recorta a la SILUETA del personaje con una máscara por
chroma-key (el fondo oscuro del sprite se vuelve transparente y deja pasar los
clics fuera de la figura). Es la mascota de "bajos recursos": sin Chromium.

El avatar 3D (VRM) vive en ui/companion.py (render="vrm"): mismas llamadas
(set_estado / set_emocion / set_act / set_hablando / set_click_through, señal
`visibilidad`, atributo `cerrado`), así que quien las use no distingue una de otra.

Además hay un "modo fantasma" (click-through total): la ventana deja pasar TODOS
los clics. En Windows se hace con WS_EX_TRANSPARENT.

Mecánica de ventana portada de la mascota Electron de AIRI a Qt:
    FramelessWindowHint | WindowStaysOnTopHint | Tool  ≈ frameless/always-on-top/panel
    WA_TranslucentBackground                            ≈ transparent, sin sombra
    windowHandle().startSystemMove()                    ≈ arrastre nativo
    setMask(QRegion)                                     ≈ recorte a la silueta
"""
from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QSystemTrayIcon, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QRegion, QImage

from ui.lune_face import LuneFaceWidget, estado_desde_emocion

# Suma R+G+B por debajo de la cual un píxel del sprite se considera "fondo" (negro).
UMBRAL_FONDO = 45


class AvatarOverlay(QMainWindow):
    """Mascota flotante de sprites. `config` persiste su posición y el modo fantasma."""

    visibilidad = pyqtSignal(bool)       # se muestra / se oculta o cierra

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.cerrado = False
        self.render = "sprites"

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
        self.cara.estado_cambiado.connect(self._actualizar_mascara)
        lay.addWidget(self.cara)

        self.resize(210, 280)
        self._restaurar_posicion()
        self._construir_bandeja()

        self._arrastrando_desde = None
        self._click_through = False
        # Aplicar el modo fantasma inicial (config) una vez mostrada la ventana.
        if self.config and self.config.get("avatar", "click_through", False):
            QTimer.singleShot(300, lambda: self.set_click_through(True))

    # ── Emoción ────────────────────────────────────────────────────────────────
    def set_emocion(self, emocion: str, ms: int = 6000):
        """Recibe una emoción canónica (<|ACT|>) y la muestra."""
        self.cara.set_state(estado_desde_emocion(emocion), auto_revert_ms=ms)

    def set_estado(self, estado: str, ms: int = 0):
        """Recibe un estado directo de lune_face (thinking, typing…)."""
        self.cara.set_state(estado, auto_revert_ms=ms)

    def set_act(self, act: dict, ms: int = 6000):
        """Recibe el ACT completo {emotion, intensity, motion} del modelo."""
        if not isinstance(act, dict):
            return
        self.cara.set_state(estado_desde_emocion(str(act.get("emotion", "neutral"))), auto_revert_ms=ms)

    def set_hablando(self, hablando: bool):
        """Los sprites no tienen boca animada: no-op (misma interfaz que el VRM)."""

    # ── Máscara de silueta ─────────────────────────────────────────────────────
    def _actualizar_mascara(self, *args):
        """Recorta la ventana a la silueta del personaje (deja pasar clics fuera)."""
        if self.cara is None:
            return
        region = QRegion()
        # La etiqueta de estado (caja opaca) se mantiene clicable/arrastrable.
        tag = getattr(self.cara, "state_tag", None)
        if tag is not None and tag.isVisible():
            p = tag.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), tag.width(), tag.height()))
        # Silueta del sprite por chroma-key sobre el pixmap realmente mostrado.
        lbl = getattr(self.cara, "image_label", None)
        pm = getattr(self.cara, "_pixmap_actual", None)
        if lbl is not None and lbl.isVisible() and pm is not None and not pm.isNull():
            base = lbl.mapTo(self, QPoint(0, 0))
            ox = base.x() + (lbl.width() - pm.width()) // 2
            oy = base.y() + (lbl.height() - pm.height()) // 2
            region = region.united(self._region_silueta(pm).translated(ox, oy))
        # Vídeo (thinking/typing): no se puede enmascarar por frame → rect completo.
        vw = getattr(self.cara, "video_widget", None)
        if vw is not None and vw.isVisible():
            p = vw.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), vw.width(), vw.height()))
        fb = getattr(self.cara, "_fallback_label", None)
        if fb is not None and fb.isVisible():
            p = fb.mapTo(self, QPoint(0, 0))
            region = region.united(QRegion(p.x(), p.y(), fb.width(), fb.height()))

        if region.isEmpty():
            self.clearMask()
        else:
            self.setMask(region)

    def _region_silueta(self, pixmap) -> QRegion:
        """QRegion del personaje: fondo oscuro fuera, con relleno por filas."""
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w, h = img.width(), img.height()
        try:
            import numpy as np
            ptr = img.constBits()
            ptr.setsize(h * img.bytesPerLine())
            arr = np.frombuffer(ptr, np.uint8).reshape((h, img.bytesPerLine() // 4, 4))[:, :w, :]
            # ARGB32 en little-endian se guarda como BGRA.
            lum = arr[:, :, 0].astype(np.int16) + arr[:, :, 1] + arr[:, :, 2]
            fg = lum >= UMBRAL_FONDO
            region = QRegion()
            for y in range(h):
                cols = np.nonzero(fg[y])[0]
                if cols.size:
                    x0, x1 = int(cols[0]), int(cols[-1])
                    region = region.united(QRegion(x0, y, x1 - x0 + 1, 1))
            return region if not region.isEmpty() else QRegion(0, 0, w, h)
        except Exception:
            return QRegion(0, 0, w, h)

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._actualizar_mascara)
        self.visibilidad.emit(True)

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.visibilidad.emit(False)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._actualizar_mascara()

    # ── Modo fantasma (click-through total) ──────────────────────────────────────
    def set_click_through(self, activo: bool):
        self._click_through = bool(activo)
        if sys.platform == "win32":
            try:
                import win32gui, win32con
                hwnd = int(self.winId())
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if activo:
                    ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
                else:
                    ex &= ~win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            except Exception:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)
        if self.config:
            self.config.set("avatar", "click_through", self._click_through)

    def _alternar_fantasma(self, checked):
        self.set_click_through(checked)

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
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "lune_icon.png")
        if os.path.exists(ruta):
            icono = QIcon(ruta)
        self.tray = QSystemTrayIcon(icono, self)
        self.tray.setToolTip("Lune · mascota")
        menu = QMenu()
        act_mostrar = QAction("Mostrar / ocultar", self)
        act_mostrar.triggered.connect(self._alternar)
        act_centrar = QAction("Llevar a la esquina", self)
        act_centrar.triggered.connect(lambda: (self._esquina_inferior_derecha(), self._guardar_posicion()))
        self.act_fantasma = QAction("Modo fantasma (dejar pasar clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.setChecked(bool(self.config and self.config.get("avatar", "click_through", False)))
        self.act_fantasma.toggled.connect(self._alternar_fantasma)
        act_cerrar = QAction("Cerrar mascota", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_mostrar); menu.addAction(act_centrar)
        menu.addAction(self.act_fantasma)
        menu.addSeparator(); menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._alternar() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _alternar(self):
        self.hide() if self.isVisible() else (self.showNormal(), self.raise_())

    def closeEvent(self, ev):
        self.cerrado = True
        self._guardar_posicion()
        if getattr(self, "tray", None):
            self.tray.hide()
        if self.cara is not None and getattr(self.cara, "_player", None):
            self.cara._player.stop()
        ev.accept()
