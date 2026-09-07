"""
avatar_overlay.py — Lune como mascota flotante sobre el escritorio.

Ventana sin bordes, transparente, siempre encima y arrastrable que muestra a Lune
y reacciona a las emociones del modelo (<|ACT|>, ver lune_core/marcadores). Dos
formas de dibujarla, según config avatar.render:

    "sprites"  los PNG/MP4 de lune_face (2D). Se recorta a la SILUETA del personaje
               con una máscara por chroma-key (el fondo oscuro del sprite se vuelve
               transparente y deja pasar los clics fuera de la figura).
    "vrm"      un avatar 3D VRM renderizado con three-vrm dentro de una QWebEngineView
               (necesita PyQt6-WebEngine). El .vrm se sirve por un http local.

Además hay un "modo fantasma" (click-through total): la ventana deja pasar TODOS
los clics, útil sobre todo en modo VRM. En Windows se hace con WS_EX_TRANSPARENT.

Mecánica de ventana portada de la mascota Electron de AIRI a Qt:
    FramelessWindowHint | WindowStaysOnTopHint | Tool  ≈ frameless/always-on-top/panel
    WA_TranslucentBackground                            ≈ transparent, sin sombra
    windowHandle().startSystemMove()                    ≈ arrastre nativo
    setMask(QRegion)                                     ≈ recorte a la silueta
"""
from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QSystemTrayIcon, QApplication,
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QUrl, QEvent
from PyQt6.QtGui import QAction, QIcon, QRegion, QImage

from ui import lune_face

from ui.lune_face import LuneFaceWidget, estado_desde_emocion

# QWebEngineView es opcional: si PyQt6-WebEngine no está, el modo VRM cae a sprites.
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    _WEBENGINE_OK = True
except Exception:
    _WEBENGINE_OK = False


# Emoción canónica del protocolo <|ACT|> → expresión del avatar VRM (vrm.html).
EMOCION_A_VRM = {
    "happy": "happy", "sad": "sad", "angry": "angry", "surprised": "surprised",
    "think": "think", "question": "question", "curious": "curious",
    "awkward": "awkward", "neutral": "neutral",
    # v10: emociones nuevas del vocabulario (el VRM no tiene gesto propio; se aproximan).
    "nervous": "awkward", "wave": "happy", "dismiss": "angry",
}
# Estado visual de sprite (lune_face) → expresión VRM (para set_estado).
ESTADO_A_VRM = {
    "normal": "neutral", "happy": "happy", "sad": "sad", "error": "angry",
    "thinking": "think", "typing": "neutral", "reading": "curious", "confused": "awkward",
}

# Suma R+G+B por debajo de la cual un píxel del sprite se considera "fondo" (negro).
UMBRAL_FONDO = 45


def ruta_vrm(config=None) -> Optional[Path]:
    """El .vrm a usar: config avatar.vrm_archivo, o el primero de modelo_vrm/."""
    if config is not None:
        elegido = str(config.get("avatar", "vrm_archivo", "") or "").strip()
        if elegido and Path(elegido).exists():
            return Path(elegido)
    carpeta = Path("modelo_vrm")
    if carpeta.exists():
        vrms = sorted(carpeta.glob("*.vrm"))
        if vrms:
            return vrms[0]
    return None


class ServidorVRM:
    """http local mínimo que sirve vrm.html y el .vrm a la QWebEngineView."""

    def __init__(self, ruta_modelo: Path, host: str = "127.0.0.1"):
        self.ruta_modelo = Path(ruta_modelo)
        self.host = host
        self.puerto = 0
        self._httpd = None
        self._hilo = None

    def iniciar(self) -> bool:
        web_dir = Path(__file__).parent.parent / "lune_core" / "web"
        modelo = self.ruta_modelo

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                ruta = self.path.split("?", 1)[0]
                if ruta in ("/", "/vrm.html"):
                    self._enviar(web_dir / "vrm.html", "text/html; charset=utf-8")
                elif ruta in ("/model.vrm", "/modelo.vrm"):
                    self._enviar(modelo, "application/octet-stream")
                else:
                    self.send_error(404)

            def _enviar(self, p, ctype):
                try:
                    data = Path(p).read_bytes()
                except OSError:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        try:
            self._httpd = ThreadingHTTPServer((self.host, 0), Handler)
        except OSError:
            return False
        self.puerto = self._httpd.server_address[1]
        self._hilo = threading.Thread(target=self._httpd.serve_forever,
                                      name="lune-vrm", daemon=True)
        self._hilo.start()
        return True

    def url(self) -> str:
        return f"http://{self.host}:{self.puerto}/vrm.html?src=model.vrm"

    def detener(self):
        if self._httpd:
            try:
                self._httpd.shutdown(); self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


class AvatarOverlay(QMainWindow):
    """Mascota flotante. `config` persiste su posición y el modo de render."""

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

        self.cara = None                 # LuneFaceWidget (modo sprites)
        self.web = None                  # QWebEngineView (modo VRM)
        self._servidor_vrm = None
        self._vrm_listo = False
        self._modo = self._modo_render()

        if self._modo == "vrm":
            self._construir_vrm(lay)
        if self.web is None:             # sprites, o VRM no disponible
            self._modo = "sprites"
            self._construir_sprites(lay)

        tam = (320, 440) if self._modo == "vrm" else (210, 280)
        self.resize(*tam)
        self._restaurar_posicion()
        self._construir_bandeja()

        self._arrastrando_desde = None
        self._click_through = False
        # Aplicar el modo fantasma inicial (config) una vez mostrada la ventana.
        if self.config and self.config.get("avatar", "click_through", False):
            QTimer.singleShot(300, lambda: self.set_click_through(True))

    # ── Construcción según modo ─────────────────────────────────────────────────
    def _modo_render(self) -> str:
        modo = "sprites"
        if self.config:
            modo = str(self.config.get("avatar", "render", "sprites") or "sprites")
        return "vrm" if modo == "vrm" else "sprites"

    def _construir_sprites(self, lay):
        self.cara = LuneFaceWidget()
        # En el overlay el "escenario" es transparente, sin el marco neón.
        self.cara.setStyleSheet("LuneFaceWidget{background:transparent;border:none;}")
        self.cara.estado_cambiado.connect(self._actualizar_mascara)
        lay.addWidget(self.cara)

    def _construir_vrm(self, lay):
        if not _WEBENGINE_OK:
            from nucleo.utils import log_info
            log_info("[overlay] modo VRM pedido pero PyQt6-WebEngine no está: uso sprites")
            return
        modelo = ruta_vrm(self.config)
        if modelo is None:
            from nucleo.utils import log_info
            log_info("[overlay] modo VRM pedido pero no hay .vrm en modelo_vrm/: uso sprites")
            return
        self._servidor_vrm = ServidorVRM(modelo)
        if not self._servidor_vrm.iniciar():
            self._servidor_vrm = None
            return
        self.web = QWebEngineView()
        self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        try:
            from PyQt6.QtGui import QColor
            self.web.page().setBackgroundColor(QColor(0, 0, 0, 0))
            s = self.web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        except Exception:
            pass
        self.web.loadFinished.connect(self._on_vrm_cargado)
        self.web.setUrl(QUrl(self._servidor_vrm.url()))
        lay.addWidget(self.web)

    def _on_vrm_cargado(self, ok):
        self._vrm_listo = bool(ok)
        # Permitir arrastrar la ventana pinchando sobre el avatar 3D.
        try:
            fp = self.web.focusProxy()
            if fp is not None:
                fp.installEventFilter(self)
        except Exception:
            pass

    # ── Emoción ────────────────────────────────────────────────────────────────
    def set_emocion(self, emocion: str, ms: int = 6000):
        """Recibe una emoción canónica (<|ACT|>) y la muestra."""
        if self._modo == "vrm":
            self._vrm_emocion(EMOCION_A_VRM.get((emocion or "").lower(), "neutral"))
        elif self.cara:
            self.cara.set_state(estado_desde_emocion(emocion), auto_revert_ms=ms)

    def set_estado(self, estado: str, ms: int = 0):
        """Recibe un estado directo de lune_face (thinking, typing…)."""
        if self._modo == "vrm":
            self._vrm_emocion(ESTADO_A_VRM.get(estado, "neutral"))
        elif self.cara:
            self.cara.set_state(estado, auto_revert_ms=ms)

    def set_act(self, act: dict, ms: int = 6000):
        """Recibe el ACT completo {emotion, intensity, motion} del modelo."""
        if not isinstance(act, dict):
            return
        emocion = str(act.get("emotion", "neutral"))
        intensidad = float(act.get("intensity", 1.0) or 1.0)
        if self._modo == "vrm":
            self._vrm_emocion(EMOCION_A_VRM.get(emocion.lower(), "neutral"), intensidad)
        elif self.cara:
            self.cara.set_state(estado_desde_emocion(emocion), auto_revert_ms=ms)

    def set_hablando(self, hablando: bool):
        """Mueve la boca del avatar VRM mientras Lune habla (no-op en sprites)."""
        if self._modo == "vrm" and self.web is not None:
            self._js(f"window.luneSpeak && window.luneSpeak({'true' if hablando else 'false'})")

    def _vrm_emocion(self, nombre: str, intensidad: float = 1.0):
        self._js(f"window.luneSetEmotion && window.luneSetEmotion({nombre!r}, {float(intensidad):.3f})")

    def _js(self, codigo: str):
        if self.web is not None:
            try:
                self.web.page().runJavaScript(codigo)
            except Exception:
                pass

    # ── Máscara de silueta (modo sprites) ───────────────────────────────────────
    def _actualizar_mascara(self, *args):
        """Recorta la ventana a la silueta del personaje (deja pasar clics fuera)."""
        if self._modo != "sprites" or self.cara is None:
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

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._actualizar_mascara()

    # ── Modo fantasma (click-through total, sobre todo para VRM) ─────────────────
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
    def eventFilter(self, obj, ev):
        # En modo VRM el render 3D se come los clics: arrastramos desde su superficie.
        if (self.web is not None and not self._click_through
                and ev.type() == QEvent.Type.MouseButtonPress):
            try:
                if ev.button() == Qt.MouseButton.LeftButton:
                    wh = self.windowHandle()
                    if wh is not None and hasattr(wh, "startSystemMove"):
                        wh.startSystemMove()
            except Exception:
                pass
        return super().eventFilter(obj, ev)

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
        self._guardar_posicion()
        if getattr(self, "tray", None):
            self.tray.hide()
        if self.cara is not None and getattr(self.cara, "_player", None):
            self.cara._player.stop()
        if self._servidor_vrm is not None:
            self._servidor_vrm.detener()
        ev.accept()
