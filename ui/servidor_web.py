"""
ui/servidor_web.py — Servidor http local para las páginas web de Lune.

Sirve `ui_web/` en 127.0.0.1 (puerto aleatorio) en un hilo daemon. Lo usan la
ventana principal con la piel web (ui/web_shell.py) y la asistente flotante
(ui/companion.py). Vive aparte de web_shell para que la asistente pueda importarlo
sin arrastrar PyQt6-WebEngine en el módulo (la interfaz nativa no lo tiene).

Qué más sirve, además de `ui_web/`:
- Rutas extra: archivos sueltos que están FUERA de ui_web/ (el modelo .vrm de la
  asistente, que vive en modelo_vrm/ o donde el usuario lo tenga) se publican con
  `rutas_extra={"/vrm/actual.vrm": Path(...)}` o `publicar(ruta, archivo)`.
- Carpetas publicadas: `publicar_carpeta("/bailes/", carpeta)` sirve los archivos
  de esa carpeta bajo ese prefijo (bailes .vmd/.vrma, packs de sonido, biblioteca
  de VRM…). Nunca se sale de la carpeta: se rechazan `..`, rutas absolutas,
  unidades (`C:`), barras invertidas, `%2e%2e` y dobles codificaciones, y al final
  se comprueba con resolve() que el archivo queda dentro. Tampoco lista directorios.

Seguridad: NO se manda `Access-Control-Allow-Origin` (todas las páginas de Lune se
sirven de este mismo origen, así que no lo necesitan) y solo se responde a
peticiones cuyo `Host` sea 127.0.0.1/localhost/::1. Así otra web abierta en el
navegador no puede leer bailes, sonidos o el VRM por el puerto local, ni siquiera
con DNS rebinding.

Se conserva el soporte de HTTP Range (206): los <video> de la asistente animada y
los audios largos lo necesitan para reproducir y hacer bucle sin cortes.
"""
from __future__ import annotations

import os
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Mapping, Optional, Union
from urllib.parse import unquote

from nucleo import rutas

# Lo que trae Lune (solo se lee). Los nombres se conservan: web_shell y companion los
# importan. Lo del usuario (VRM, bailes, sonidos) vive en rutas.DATOS y se publica con
# su ruta absoluta (publicar/publicar_carpeta).
RAIZ = rutas.RECURSOS
DIR_WEB = RAIZ / "ui_web"

# Hosts con los que se acepta una petición (la página siempre usa 127.0.0.1).
HOSTS_LOCALES = frozenset({"127.0.0.1", "localhost", "::1"})

# Nombres de dispositivo de Windows: abrir «carpeta/NUL» abre el dispositivo.
_RESERVADOS_WIN = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})


class _Rechazada:
    """Centinela: la ruta cae en una carpeta publicada pero intenta salirse de ella."""
    __slots__ = ()

    def __repr__(self):
        return "RECHAZADA"

    def __bool__(self):
        return False


RECHAZADA = _Rechazada()


def normalizar_prefijo(prefijo_url: str) -> str:
    """'/bailes', 'bailes' o '/bailes/' → '/bailes/'. ValueError si no es válido."""
    p = str(prefijo_url or "").strip()
    if not p.startswith("/"):
        p = "/" + p
    if not p.endswith("/"):
        p += "/"
    segmentos = p.strip("/").split("/")
    if p == "/" or any(not _segmento_valido(s) for s in segmentos):
        raise ValueError(f"prefijo de carpeta no válido: {prefijo_url!r}")
    return p


def _segmento_valido(seg: str) -> bool:
    """Un trozo de ruta que no puede escaparse ni apuntar a otra unidad o dispositivo."""
    if not seg or seg.strip(" .") == "":           # '', '.', '..', '...', '. .'
        return False
    if any(c in seg for c in ("\\", ":", "%", "\x00")):
        return False
    if seg.split(".", 1)[0].strip().upper() in _RESERVADOS_WIN:
        return False
    return True


def resolver_en_carpetas(ruta_url: str, carpetas: Mapping[str, Path]) -> Union[Path, None, _Rechazada]:
    """Traduce una ruta de URL a un archivo dentro de alguna carpeta publicada.

    Devuelve el Path (exista o no: si no existe el servidor da 404), None si
    ninguna carpeta publicada cubre esa ruta (se sirve de ui_web/ como siempre) o
    RECHAZADA si la ruta cae bajo un prefijo publicado pero intenta salirse de la
    carpeta o pide el propio directorio. `carpetas` es {prefijo normalizado: carpeta}.
    """
    limpio = ruta_url.split("?", 1)[0].split("#", 1)[0]
    ruta = unquote(limpio)   # una sola vez: '%2e%2e' → '..'; '%252e' → '%2e' (y se rechaza)
    candidatas = [(p, c) for p, c in tuple(carpetas.items())
                  if ruta.startswith(p) or ruta == p[:-1]]
    if not candidatas:
        return None
    prefijo, carpeta = max(candidatas, key=lambda pc: len(pc[0]))
    resto = ruta[len(prefijo):]
    if not resto or resto.startswith("/") or not all(_segmento_valido(s) for s in resto.split("/")):
        return RECHAZADA
    try:
        base = Path(carpeta).resolve()
        destino = (base / resto).resolve()
    except (OSError, ValueError, RuntimeError):
        return RECHAZADA
    if destino == base or not destino.is_relative_to(base) or destino.is_dir():
        return RECHAZADA
    return destino


def _host_local(cabecera: Optional[str]) -> bool:
    """True si la cabecera Host apunta a esta máquina (o falta, como en HTTP/1.0)."""
    if not cabecera:
        return True
    h = cabecera.strip().lower()
    if h.startswith("["):                       # [::1]:puerto
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:                     # 127.0.0.1:puerto / localhost:puerto
        h = h.split(":", 1)[0]
    return h.rstrip(".") in HOSTS_LOCALES


class ServidorEstatico:
    """Sirve un directorio, rutas extra sueltas y carpetas publicadas en 127.0.0.1:<aleatorio>."""

    def __init__(self, directorio: Path = DIR_WEB, rutas_extra: Optional[Dict[str, Path]] = None):
        self.directorio = str(directorio)
        self.rutas_extra: Dict[str, Path] = {k: Path(v) for k, v in (rutas_extra or {}).items()}
        self.carpetas: Dict[str, Path] = {}
        self.puerto = 0
        self._httpd = None

    def iniciar(self) -> bool:
        try:
            self._httpd = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                partial(HandlerSilencioso, directory=self.directorio,
                        rutas_extra=self.rutas_extra, carpetas=self.carpetas))
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

    def publicar_carpeta(self, prefijo_url: str, carpeta: Path) -> str:
        """Sirve los archivos de `carpeta` bajo `prefijo_url` (en caliente).

        Devuelve el prefijo normalizado ('/bailes/'). Las rutas extra exactas tienen
        prioridad; entre carpetas gana el prefijo más largo. ValueError si el prefijo
        no es válido o tapa algo que ya existe en ui_web/ (p. ej. '/vrm/'). Una
        carpeta relativa se toma desde RAIZ (lo que trae Lune), nunca desde el cwd;
        las carpetas del usuario (rutas.DATOS) se publican siempre con ruta absoluta.
        """
        prefijo = normalizar_prefijo(prefijo_url)
        if (Path(self.directorio) / prefijo.strip("/")).exists():
            raise ValueError(f"el prefijo {prefijo!r} taparía {prefijo.strip('/')} de {self.directorio}")
        carpeta = Path(carpeta)
        self.carpetas[prefijo] = (carpeta if carpeta.is_absolute() else RAIZ / carpeta).resolve()
        return prefijo

    def quitar_carpeta(self, prefijo_url: str) -> bool:
        """Deja de servir la carpeta publicada en ese prefijo. True si estaba."""
        try:
            prefijo = normalizar_prefijo(prefijo_url)
        except ValueError:
            return False
        return self.carpetas.pop(prefijo, None) is not None

    def detener(self):
        if self._httpd:
            try:
                self._httpd.shutdown(); self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


class HandlerSilencioso(SimpleHTTPRequestHandler):
    # Tipos MIME explícitos: el registro de Windows da a veces tipos raros (.js como
    # text/plain) y WebAudio/three necesitan los correctos. .vrm/.vrma son glTF binario.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".jsx": "text/plain", ".js": "text/javascript", ".mjs": "text/javascript",
        ".css": "text/css", ".html": "text/html", ".json": "application/json",
        ".vrm": "model/gltf-binary", ".glb": "model/gltf-binary", ".vrma": "model/gltf-binary",
        ".vmd": "application/octet-stream",
        ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".opus": "audio/ogg",
        ".wav": "audio/wav", ".flac": "audio/flac",
        # Fuentes locales de la piel web (ui_web/fonts, 11.2)
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    }

    def __init__(self, *args, rutas_extra: Optional[Dict[str, Path]] = None,
                 carpetas: Optional[Dict[str, Path]] = None, **kwargs):
        # Los dicts son los MISMOS objetos que tiene el servidor: publicar() y
        # publicar_carpeta() se ven al instante en las peticiones siguientes.
        self.rutas_extra = rutas_extra if rutas_extra is not None else {}
        self.carpetas = carpetas if carpetas is not None else {}
        self._rechazada = False
        super().__init__(*args, **kwargs)

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        self._rechazada = False
        limpio = path.split("?", 1)[0].split("#", 1)[0]
        extra = self.rutas_extra.get(limpio)
        if extra is not None:
            return str(extra)
        destino = resolver_en_carpetas(path, self.carpetas)
        if destino is RECHAZADA:
            # Se marca y send_head/do_GET responden 404 sin tocar el disco.
            self._rechazada = True
            return os.path.join(self.directory, "∅rechazada")
        if destino is not None:
            return str(destino)
        return super().translate_path(path)

    def _host_rechazado(self) -> bool:
        """Responde 403 y devuelve True si la petición no viene dirigida a 127.0.0.1."""
        if _host_local(self.headers.get("Host")):
            return False
        self.send_error(403, "Host no permitido")
        return True

    def send_head(self):
        # Lo usan do_GET (sin Range) y do_HEAD.
        if self._host_rechazado():
            return None
        self.translate_path(self.path)
        if self._rechazada:
            self.send_error(404)
            return None
        return super().send_head()

    def do_GET(self):
        # Soporta HTTP Range (206) para que los <video> grandes (asistente) reproduzcan
        # y loopeen sin cortes; el resto se sirve normal (200).
        rango = self.headers.get("Range")
        if not rango:
            return super().do_GET()
        if self._host_rechazado():
            return
        ruta = self.translate_path(self.path)
        if self._rechazada:
            self.send_error(404); return
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
