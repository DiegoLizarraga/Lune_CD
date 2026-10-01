"""
lune_core/web_server.py — Sirve el terminal web (una sola página estática).

Va aparte del hub a propósito: intentar servir HTTP desde el mismo `websockets`
resultó frágil entre versiones. Aquí un http.server mínimo en un hilo sirve
terminal.html en el puerto del hub + 1 (por defecto), inyectando el puerto del
WebSocket para que la página se conecte al hub correcto.

    ws  → ws://host:7777/ws   (el hub)
    web → http://host:7778/   (esta página, que habla con el hub de arriba)
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from nucleo import rutas

# Lo trae Lune (solo se lee).
_HTML = rutas.recurso("lune_core", "web", "terminal.html")


def _pagina(puerto_ws: int) -> bytes:
    try:
        html = _HTML.read_text("utf-8")
    except OSError:
        html = "<h1>terminal no disponible</h1>"
    # La página usa location.host para el WS; si el web va en otro puerto,
    # se le dice cuál es el del hub con una variable global.
    inyeccion = f"<script>window.LUNE_WS_PORT={puerto_ws};</script>"
    if "</head>" in html:
        html = html.replace("</head>", inyeccion + "</head>", 1)
    else:
        html = inyeccion + html
    return html.encode("utf-8")


class ServidorWeb:
    def __init__(self, puerto_ws: int, host: str = "0.0.0.0", puerto: Optional[int] = None):
        self.puerto_ws = puerto_ws
        self.host = host
        self.puerto = puerto if puerto is not None else puerto_ws + 1
        self._httpd = None
        self._hilo = None

    def iniciar(self) -> bool:
        pagina = _pagina(self.puerto_ws)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(pagina)))
                self.end_headers()
                self.wfile.write(pagina)
            def log_message(self, *a):
                pass   # sin ruido en consola

        try:
            self._httpd = ThreadingHTTPServer((self.host, self.puerto), Handler)
        except OSError:
            return False
        # el sistema puede haber elegido el puerto (si se pidió 0)
        self.puerto = self._httpd.server_address[1]
        self._hilo = threading.Thread(target=self._httpd.serve_forever,
                                      name="lune-web", daemon=True)
        self._hilo.start()
        return True

    def detener(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
