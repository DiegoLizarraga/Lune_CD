"""
ui/web_shell.py — La app de Lune con la piel web "Shibuya Punk".

Monta el diseño real (ui_web/ui_kits/lune-desktop/index.html) dentro de una
QWebEngineView y lo conecta al backend por QWebChannel (ver ui/web_bridge.py).
Se sirve por un http local para que las rutas relativas y el Babel-en-navegador
(que transpila los .jsx) funcionen igual que en el navegador.

Ejecutar en solitario para probar la Fase 1 (shell animado + chat real):
    python -m ui.web_shell
"""
from __future__ import annotations

import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QIcon, QAction

RAIZ = Path(__file__).resolve().parent.parent
DIR_WEB = RAIZ / "ui_web"
PAGINA = "ui_kits/lune-desktop/index.html"


class _ServidorEstatico:
    """Sirve ui_web/ en 127.0.0.1 (puerto aleatorio) en un hilo daemon."""

    def __init__(self, directorio: Path):
        self.directorio = str(directorio)
        self.puerto = 0
        self._httpd = None

    def iniciar(self) -> bool:
        try:
            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                partial(_HandlerSilencioso, directory=self.directorio))
        except OSError:
            return False
        self.puerto = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, name="lune-web-ui", daemon=True).start()
        return True

    def url(self) -> str:
        return f"http://127.0.0.1:{self.puerto}/{PAGINA}"

    def detener(self):
        if self._httpd:
            try:
                self._httpd.shutdown(); self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


class _HandlerSilencioso(SimpleHTTPRequestHandler):
    # Tipos MIME correctos para los assets de la UI (mp4 para la mascota animada).
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".jsx": "text/plain", ".js": "text/javascript",
        ".css": "text/css", ".html": "text/html",
    }

    def log_message(self, *a):
        pass

    def do_GET(self):
        # Soporta HTTP Range (206) para que los <video> grandes (mascota) reproduzcan
        # y loopeen sin cortes; el resto se sirve normal (200).
        import os
        import re
        rango = self.headers.get("Range")
        if not rango:
            return super().do_GET()
        ruta = self.translate_path(self.path.split("?", 1)[0])
        if not os.path.isfile(ruta):
            return super().do_GET()
        try:
            f = open(ruta, "rb")
        except OSError:
            self.send_error(404); return
        tam = os.fstat(f.fileno()).st_size
        m = re.match(r"bytes=(\d*)-(\d*)", rango)
        ini = int(m.group(1)) if m and m.group(1) else 0
        fin = int(m.group(2)) if m and m.group(2) else tam - 1
        fin = min(fin, tam - 1)
        if ini > fin or ini >= tam:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{tam}")
            self.end_headers(); f.close(); return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(ruta))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.end_headers()
        f.seek(ini)
        restante = fin - ini + 1
        while restante > 0:
            chunk = f.read(min(65536, restante))
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            restante -= len(chunk)
        f.close()


class VentanaWeb(QMainWindow):
    """Ventana principal con la UI web y el puente al backend."""

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lune CD")
        self.resize(1280, 820)
        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = RAIZ / "assets" / f"lune_icon.{ext}"
            if ruta.exists():
                self._icono = QIcon(str(ruta))
                self.setWindowIcon(self._icono)
                break
        self._salir = False   # True solo cuando el usuario elige "Salir" en la bandeja

        self._servidor = _ServidorEstatico(DIR_WEB)
        if not self._servidor.iniciar():
            raise RuntimeError("No pude servir la UI web (ui_web/).")

        # Puente backend ↔ web
        from ui.web_bridge import LuneBridge
        self.bridge = LuneBridge(config=config, ai_manager=ai_manager,
                                 memoria=memoria, tools=tools, parent=self)
        self._canal = QWebChannel()
        self._canal.registerObject("lune", self.bridge)

        self.web = QWebEngineView()
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web.page().setWebChannel(self._canal)
        self.web.setUrl(QUrl(self._servidor.url()))
        self.setCentralWidget(self.web)

        # Quedarse en segundo plano (como Discord): al cerrar, se oculta en la
        # bandeja y sigue viva; se reabre desde la bandeja o relanzando el .vbs.
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self._construir_bandeja()

    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self._icono, self)
        self.tray.setToolTip("Lune CD")
        menu = QMenu()
        act_abrir = QAction("Abrir Lune", self)
        act_abrir.triggered.connect(self._mostrar)
        act_salir = QAction("Salir", self)
        act_salir.triggered.connect(self._salir_de_verdad)
        menu.addAction(act_abrir)
        menu.addSeparator()
        menu.addAction(act_salir)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._mostrar() if r in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self.tray.show()

    def _mostrar(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def _salir_de_verdad(self):
        self._salir = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, ev):
        # Cerrar la ventana = ocultarla en la bandeja; solo "Salir" cierra de verdad.
        if not self._salir and getattr(self, "tray", None) is not None:
            self.hide()
            if not getattr(self, "_aviso_bandeja", False):
                self._aviso_bandeja = True
                try:
                    self.tray.showMessage("Lune sigue aquí",
                                          "Sigo en segundo plano. Ábreme desde la bandeja.",
                                          self._icono, 4000)
                except Exception:
                    pass
            ev.ignore()
            return
        self._servidor.detener()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        ev.accept()


def main() -> int:
    # QtWebEngine necesita compartir el contexto OpenGL antes de crear QApplication.
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Lune CD")
    ventana = VentanaWeb()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
