"""
ui/servidor_web.py — Servidor http local para las páginas web de Lune.

Sirve `ui_web/` en 127.0.0.1 (puerto aleatorio) en un hilo daemon. Lo usan la
ventana principal con la piel web (ui/web_shell.py) y la mascota flotante
(ui/companion.py). Vive aparte de web_shell para que la mascota pueda importarlo
sin arrastrar PyQt6-WebEngine en el módulo (la interfaz nativa no lo tiene).

Rutas extra: archivos que están FUERA de ui_web/ (el modelo .vrm de la mascota,
que vive en modelo_vrm/ o donde el usuario lo tenga) se publican con
`rutas_extra={"/vrm/actual.vrm": Path(...)}`. Solo se sirven las rutas listadas,
nunca un directorio entero.
"""
from __future__ import annotations

import os
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

RAIZ = Path(__file__).resolve().parent.parent
DIR_WEB = RAIZ / "ui_web"


class ServidorEstatico:
    """Sirve un directorio (y rutas extra sueltas) en 127.0.0.1:<aleatorio>."""

    def __init__(self, directorio: Path = DIR_WEB, rutas_extra: Optional[Dict[str, Path]] = None):
        self.directorio = str(directorio)
        self.rutas_extra: Dict[str, Path] = {k: Path(v) for k, v in (rutas_extra or {}).items()}
        self.puerto = 0
        self._httpd = None

    def iniciar(self) -> bool:
        try:
            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                partial(HandlerSilencioso, directory=self.directorio, rutas_extra=self.rutas_extra))
        except OSError:
            return False
        self.puerto = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, name="lune-web-ui", daemon=True).start()
        return True

    def url(self, pagina: str = "") -> str:
        return f"http://127.0.0.1:{self.puerto}/{pagina.lstrip('/')}"

    def publicar(self, ruta_url: str, archivo: Path):
        """Añade (o cambia) una ruta extra en caliente, p. ej. otro modelo .vrm."""
        self.rutas_extra[ruta_url] = Path(archivo)

    def detener(self):
        if self._httpd:
            try:
                self._httpd.shutdown(); self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


class HandlerSilencioso(SimpleHTTPRequestHandler):
    # Tipos MIME correctos para los assets de la UI (webm para la mascota animada,
    # .vrm es glTF binario).
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".jsx": "text/plain", ".js": "text/javascript", ".mjs": "text/javascript",
        ".css": "text/css", ".html": "text/html",
        ".vrm": "model/gltf-binary", ".glb": "model/gltf-binary",
    }

    def __init__(self, *args, rutas_extra: Optional[Dict[str, Path]] = None, **kwargs):
        # El dict es el MISMO objeto que tiene el servidor: publicar() se ve al instante.
        self.rutas_extra = rutas_extra if rutas_extra is not None else {}
        super().__init__(*args, **kwargs)

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        limpio = path.split("?", 1)[0].split("#", 1)[0]
        extra = self.rutas_extra.get(limpio)
        if extra is not None:
            return str(extra)
        return super().translate_path(path)

    def end_headers(self):
        # Los módulos ES y el .vrm se cargan por fetch desde la misma página; CORS
        # abierto no expone nada (solo escucha en 127.0.0.1) y evita sorpresas.
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self):
        # Soporta HTTP Range (206) para que los <video> grandes (mascota) reproduzcan
        # y loopeen sin cortes; el resto se sirve normal (200).
        rango = self.headers.get("Range")
        if not rango:
            return super().do_GET()
        ruta = self.translate_path(self.path)
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
