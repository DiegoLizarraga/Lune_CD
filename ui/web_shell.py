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
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QIcon

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
    def log_message(self, *a):
        pass


class VentanaWeb(QMainWindow):
    """Ventana principal con la UI web y el puente al backend."""

    def __init__(self, config=None, ai_manager=None, memoria=None, tools=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lune CD · Shibuya Punk")
        self.resize(1280, 820)
        for ext in ("ico", "png"):
            icono = RAIZ / "assets" / f"lune_icon.{ext}"
            if icono.exists():
                self.setWindowIcon(QIcon(str(icono)))
                break

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

    def closeEvent(self, ev):
        self._servidor.detener()
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
