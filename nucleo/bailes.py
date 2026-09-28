"""
nucleo/bailes.py — La biblioteca de bailes del usuario (reproductor MMD/VRMA, corte 9).

Carpeta `RAIZ/bailes/` (contenido del usuario; va a .gitignore). Dos maneras de
organizarla:

- una subcarpeta por baile: `bailes/<carpeta>/` con un `.vrma` o uno o más
  `.vmd`, una canción como mucho y `lune.json` opcional;
- archivos sueltos agrupados por nombre base: `X.vmd` + `X_lip.vmd` /
  `X.face.vmd` + `X.mp3` + `X.lune.json`.

Un VMD con solo morfos es de «cara» (labios y expresiones); uno con solo cámara
se ignora. La canción que se prefiere es la del mismo nombre base. La página
de la mascota reproduce `.mp3 .ogg .oga .opus .wav .flac`; `.m4a .aac .wma` se
convierten a Opus (`.ogg`) al importar o, si se dejaron a mano, en diferido a
`cache/bailes/<id>.ogg`.

Todo se valida por CABECERA y tamaño (VMD por saltos, VRMA como GLB sin `uri`,
audio por magia) y las rutas no salen nunca de la carpeta: nada de enlaces ni
junctions, ni nombres reservados de Windows, ni `..`, ni rutas de red (UNC).
Las URL que ve la página son `/bailes/<ruta codificada>` y
`/bailes_cache/<id>.ogg` (ui/servidor_web.py las sirve solo desde 127.0.0.1).

- `Biblioteca`: escanear (con caché por tamaño y fecha, fuera del cerrojo) y una FOTO
  que se lee sin esperar nunca (foto, de_la_foto, buscar_en_foto: el hilo de Qt), buscar,
  URL, metadatos (`lune.json`, escritura atómica), favoritos y desactivados (config
  `baile.favoritos` / `baile.desactivados`), importar (copia, nunca mueve; sin cerrojo),
  quitar (mueve a `bailes/.quitados/`, reversible), convertir el audio y el
  pulso de la canción (`analizar_pulso`, para las mascotas sin esqueleto: D1).
- `Cola`: siguiente / anterior / aleatorio sin repetir el actual.
- `herramienta_listar`: handler de la herramienta del modelo `listar_bailes`.
- `biblioteca_compartida()`: la de bailes/, una por proceso; `coincide_con_biblioteca(X)`
  («pon la canción X» sin comillas, servicios/tools.py).
- `ejecutar_proceso` / `matar_procesos`: ffmpeg que se mata al detener y al salir.

Sin Qt. ffmpeg, la ejecución de procesos, el reloj y la config son inyectables.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import stat
import struct
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import numpy as np

from nucleo import baile as _nb

_log = logging.getLogger("lune.bailes")

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "bailes"
CACHE = RAIZ / "cache" / "bailes"
PREFIJO_WEB = "/bailes/"
PREFIJO_CACHE = "/bailes_cache/"

EXT_MOV: Tuple[str, ...] = (".vmd", ".vrma")
EXT_AUDIO_WEB: Tuple[str, ...] = (".mp3", ".ogg", ".oga", ".opus", ".wav", ".flac")
EXT_AUDIO_CONV: Tuple[str, ...] = (".m4a", ".aac", ".wma")
EXT_AUDIO: Tuple[str, ...] = EXT_AUDIO_WEB + EXT_AUDIO_CONV
AL_TERMINAR: Tuple[str, ...] = ("parar", "siguiente", "repetir", "aleatorio")
AL_TERMINAR_DEFECTO = "parar"

TIPOS_AUDIO_WEB = frozenset({"mp3", "ogg", "wav", "flac"})
TIPOS_AUDIO_CONV = frozenset({"m4a", "aac", "wma"})

ID_RE = re.compile(r"^[0-9a-f]{12}$")

_MB = 1 << 20
MAX_VMD_BYTES = 32 * _MB
MAX_VRMA_BYTES = 32 * _MB
MAX_VRMA_JSON = 4 * _MB
MAX_AUDIO_BYTES = 64 * _MB
MAX_META_BYTES = 16 * 1024
MAX_HUESOS = 2_000_000
MAX_MORFOS = 1_000_000
MAX_FRAMES = 36_000               # 20 min a 30 fps
MAX_IK = 100_000
MAX_IK_POR_FRAME = 64
MAX_ARCHIVOS_BAILE = 8
MAX_BAILES = 500
MAX_NOMBRE = 120
MAX_MOVIMIENTO = 3                # VMD de cuerpo por baile (la página admite motion[0..2])
MAX_CARA = 2                      # VMD de cara por baile (cara[0..1])
MAX_URL = 1024
MAX_TEXTO = 80
FPS_VMD = 30.0

BPM_DEFECTO = 120.0
PULSO_SR = 11025
PULSO_HZ = 50
PULSO_MAX_S = 1200
PULSO_VERSION = 1
TIEMPO_FFMPEG_S = 120

LEEME = "LEEME.txt"
QUITADOS = ".quitados"
META = "lune.json"
SUFIJO_META = ".lune.json"

_RESERVADOS_WIN = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                             *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))})
_PROHIBIDOS_NOMBRE = frozenset('<>:"/\\|?*%')
_ANCHO_CERO = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
# Sufijos que agrupan los sueltos con su baile: X_lip.vmd, X.face.vmd, X-camera.vmd…
_SUFIJO_GRUPO = re.compile(
    r"[\s._\-]+(?:lip|lips|lipsync|face|facial|morph|morphs|expression|expr|cam|camera|motion|mot|dance|"
    r"表情|口パク|リップ|カメラ|モーション)$", re.IGNORECASE)
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400

META_DEFECTO: Dict[str, Any] = {
    "titulo": "", "autor_cancion": "", "autor_mmd": "",
    "offset_ms": 0, "brazo_a_grados": 35.0, "en_el_sitio": None, "bpm": None,
}

TEXTO_LEEME = """\
BAILES DE LUNE
==============

Aquí van tus bailes: un movimiento (MMD o VRM Animation) y, si quieres, su canción.
Lune los baila en la mascota 3D (VRM). En la animada y en los sprites no hay
esqueleto: suena la canción y Lune baila a su manera, al ritmo de la canción.

FORMATOS
- Movimiento: .vmd (MikuMikuDance; uno de cuerpo y, si hay, otro de cara/labios)
  o .vrma (VRM Animation, por ejemplo los de VRoid).
- Canción: .mp3 .ogg .opus .wav .flac. Los .m4a .aac .wma se convierten a .ogg
  (hace falta ffmpeg, que viene con Lune).
- Los VMD de solo cámara no se usan.

CÓMO ORGANIZARLOS
1. Una carpeta por baile (lo más cómodo):
     bailes/Senbonzakura/baile.vmd
     bailes/Senbonzakura/labios.vmd
     bailes/Senbonzakura/cancion.mp3
     bailes/Senbonzakura/lune.json      (opcional)
2. O archivos sueltos con el mismo nombre:
     bailes/X.vmd  bailes/X_lip.vmd  bailes/X.mp3  bailes/X.lune.json

lune.json (todo opcional):
  {"titulo": "…", "autor_cancion": "…", "autor_mmd": "…",
   "offset_ms": 0,          (−500 a 500: adelanta o retrasa el baile respecto a la canción)
   "brazo_a_grados": 35,    (25 a 45: ajusta los brazos si atraviesan el cuerpo)
   "en_el_sitio": null,     (true: baila sin desplazarse)
   "bpm": null}             (40 a 240: el ritmo, si el análisis automático falla)

LÍMITES
- .vmd y .vrma hasta 32 MB; canción hasta 64 MB; 8 archivos por baile; 500 bailes.
- Nada de accesos directos, enlaces ni carpetas de red.

LICENCIAS
Los movimientos MMD y las canciones tienen autor y condiciones de uso: respétalas
(muchos piden no redistribuirlos ni usarlos con fines comerciales). Lune solo los
usa en tu PC y nunca los sube a ningún sitio.

Al quitar un baile desde Lune se mueve a la carpeta .quitados (no se borra).
"""


class ErrorBailes(Exception):
    """Error con un texto apto para enseñar al usuario."""


# ── Utilidades de texto y nombres ────────────────────────────────────────────────

def normalizar(texto: Any) -> str:
    """Para buscar: NFKC, sin ancho cero, sin tildes (latinas), minúsculas y un espacio."""
    s = unicodedata.normalize("NFKC", str(texto or "")).translate(_ANCHO_CERO)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not ("̀" <= c <= "ͯ"))
    s = unicodedata.normalize("NFC", s).casefold()
    return " ".join(s.split())


def texto_limpio(v: Any, maximo: int = MAX_TEXTO) -> str:
    """Sin controles (→ espacio) ni marcas de formato como el ancho cero o las bidi (fuera),
    espacios colapsados y recortado."""
    if v is None:
        return ""
    s = "".join(ch if unicodedata.category(ch)[0] != "C" else (" " if unicodedata.category(ch) == "Cc" else "")
                for ch in str(v))
    return " ".join(s.split())[:maximo]


def titulo_seguro(v: Any, maximo: int = MAX_TEXTO) -> str:
    """Texto que viene de nombres de archivo y va al modelo: limpio y sin marcadores."""
    s = texto_limpio(v, maximo)
    try:
        from lune_core.prompt import neutralizar_marcadores
        s = neutralizar_marcadores(s)
    except Exception:                                   # pragma: no cover - sin lune_core
        s = s.replace("<|", "< |")
    return s


def id_valido(v: Any) -> bool:
    return isinstance(v, str) and bool(ID_RE.match(v))


def _id_de(clave: str) -> str:
    return hashlib.sha1(clave.lower().encode("utf-8")).hexdigest()[:12]


def id_carpeta(nombre: str) -> str:
    """id de un baile en su carpeta: sha1(nombre de la carpeta en minúsculas)[:12]."""
    return _id_de(nombre)


def id_suelto(clave: str) -> str:
    """id de un grupo de archivos sueltos (`clave` = nombre base sin sufijo)."""
    return _id_de(clave + ".*")


def motivo_nombre(nombre: str) -> str:
    """"" si el nombre de archivo o carpeta es seguro de servir; si no, el motivo."""
    n = str(nombre or "")
    if not n or n.strip(" .") == "":
        return "nombre vacío"
    if len(n) > MAX_NOMBRE:
        return f"nombre de más de {MAX_NOMBRE} caracteres"
    if any(unicodedata.category(c)[0] == "C" for c in n):
        return "caracteres de control en el nombre"
    if ".." in n:
        return "«..» en el nombre"
    if any(c in _PROHIBIDOS_NOMBRE for c in n):
        return "carácter no permitido en el nombre (% : \\ / …)"
    if n.endswith((" ", ".")):
        return "el nombre acaba en espacio o punto"
    if n.split(".", 1)[0].strip().upper() in _RESERVADOS_WIN:
        return "nombre reservado de Windows"
    return ""


def nombre_seguro(nombre: str, *, defecto: str = "baile", carpeta: bool = False) -> str:
    """Nombre de archivo (o de carpeta, sin extensión) saneado para importar (se
    conservan los japoneses)."""
    s = "".join(c for c in str(nombre or "") if unicodedata.category(c)[0] != "C")
    s = "".join("_" if c in _PROHIBIDOS_NOMBRE else c for c in s)
    while ".." in s:
        s = s.replace("..", ".")
    s = " ".join(s.split()).strip(" .")
    base, punto, ext = s.rpartition(".")
    if carpeta or not punto or not base:
        base, ext = s, ""
    ext = ext.lower()[:8]
    maximo = MAX_NOMBRE - (len(ext) + 1 if ext else 0)
    base = base[:maximo].strip(" .") or defecto
    if base.split(".", 1)[0].strip().upper() in _RESERVADOS_WIN:
        base = "_" + base
    return f"{base}.{ext}" if ext else base


def es_unc(p: Any) -> bool:
    """¿Ruta de red (\\\\servidor\\…) o de dispositivo (\\\\?\\…, \\\\.\\…)?"""
    s = str(p or "")
    return s.startswith("\\\\") or s.startswith("//")


def es_enlace(p: Any) -> bool:
    """¿Enlace simbólico, junction o cualquier reparse point? (o no se puede mirar)."""
    try:
        st = os.lstat(p)
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def clave_grupo(nombre_archivo: str) -> Tuple[str, str]:
    """(clave en minúsculas, base original) de un archivo suelto: X_lip.vmd → ('x', 'X')."""
    n = str(nombre_archivo)
    if n.lower().endswith(SUFIJO_META):
        stem = n[: -len(SUFIJO_META)]
    else:
        stem = n.rsplit(".", 1)[0] if "." in n else n
    base = _SUFIJO_GRUPO.sub("", stem) or stem
    return base.lower(), base


def fase_en(t: float, bpm: float, fase0: float) -> float:
    """Fase del pulso (0 = en el golpe) en el segundo `t` de la canción."""
    try:
        b = float(bpm)
        if not (math.isfinite(b) and b > 0):
            b = BPM_DEFECTO
        return (float(fase0) + float(t) * b / 60.0) % 1.0
    except (TypeError, ValueError):
        return 0.0


def _sin_ventana() -> Dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def _ffmpeg_defecto() -> Optional[str]:
    try:
        from servicios.mezclador import ruta_ffmpeg
        return ruta_ffmpeg()
    except Exception:
        return shutil.which("ffmpeg")


# ── ffmpeg que se puede matar ────────────────────────────────────────────────────
# convertir_audio, el pulso y la canción de los sprites (servicios/cancion_python) lanzaban
# ffmpeg con subprocess.run en un hilo daemon: al salir de Lune (o al desmontar el
# reproductor) el hilo moría, pero ffmpeg seguía convirtiendo por su cuenta hasta 120 s.

_PROCESOS: set = set()
_LOCK_PROCESOS = threading.Lock()


def ejecutar_proceso(cmd: List[str], *, capture_output: bool = False, timeout: Optional[float] = None,
                     **kw: Any) -> subprocess.CompletedProcess:
    """Como subprocess.run (misma firma para lo que usa este módulo), pero el proceso queda
    apuntado hasta que acaba: `matar_procesos()` (al detener el reproductor y al salir) lo mata."""
    if capture_output:
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    kw.setdefault("stdin", subprocess.DEVNULL)
    p = subprocess.Popen(cmd, **kw)
    with _LOCK_PROCESOS:
        _PROCESOS.add(p)
    try:
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err) from None
        except BaseException:
            p.kill()
            raise
        return subprocess.CompletedProcess(cmd, p.returncode, out, err)
    finally:
        with _LOCK_PROCESOS:
            _PROCESOS.discard(p)


def matar_procesos() -> int:
    """Mata los ffmpeg de `ejecutar_proceso` que sigan vivos. Devuelve cuántos mató."""
    with _LOCK_PROCESOS:
        vivos = list(_PROCESOS)
    n = 0
    for p in vivos:
        try:
            if p.poll() is None:
                p.kill()
                n += 1
        except OSError:
            pass
    return n


atexit.register(matar_procesos)


# ── Validadores por cabecera ─────────────────────────────────────────────────────

_MAGIA_VMD2 = b"Vocaloid Motion Data 0002"
_MAGIA_VMD1 = b"Vocaloid Motion Data file"


def _leer_limitado(ruta: Path, max_bytes: int, que: str) -> bytes:
    try:
        tam = ruta.stat().st_size
    except OSError as e:
        raise ValueError(f"no puedo leer el {que}: {e.strerror or e}") from e
    if tam > max_bytes:
        raise ValueError(f"el {que} pesa {tam / _MB:.1f} MB (máximo {max_bytes // _MB} MB)")
    with open(ruta, "rb") as f:
        datos = f.read(max_bytes + 1)
    if len(datos) > max_bytes:
        raise ValueError(f"el {que} pesa más de {max_bytes // _MB} MB")
    return datos


def info_vmd_bytes(datos: bytes) -> Dict[str, Any]:
    """Lo que dice la cabecera de un VMD (ver `info_vmd`). ValueError con texto."""
    n_total = len(datos)
    if n_total < 30:
        raise ValueError("no es un VMD (demasiado corto)")
    magia = datos[:30].split(b"\0", 1)[0]
    if magia.startswith(_MAGIA_VMD2):
        version, largo_modelo = 2, 20
    elif magia.startswith(_MAGIA_VMD1):
        version, largo_modelo = 1, 10
    else:
        raise ValueError("no es un VMD (cabecera desconocida)")
    off = 30 + largo_modelo
    if n_total < off:
        raise ValueError("VMD truncado (cabecera)")
    modelo = datos[30:off].split(b"\0", 1)[0].decode("shift_jis", "replace")

    cuentas: Dict[str, int] = {}
    inicios: Dict[str, int] = {}
    for nombre, tam, tope in (("huesos", 111, MAX_HUESOS), ("morfos", 23, MAX_MORFOS),
                              ("camara", 61, None), ("luces", 28, None), ("sombras", 9, None)):
        if n_total - off < 4:                          # secciones opcionales al final
            cuentas[nombre] = 0
            off = n_total
            continue
        n = struct.unpack_from("<I", datos, off)[0]
        off += 4
        if tope is not None and n > tope:
            raise ValueError(f"demasiadas claves de {nombre} ({n}; máximo {tope})")
        if n * tam > n_total - off:
            raise ValueError(f"VMD truncado ({nombre}: {n} claves no caben)")
        cuentas[nombre] = n
        inicios[nombre] = off
        off += n * tam

    frames_ik: List[int] = []
    n_ik = 0
    if n_total - off >= 4:
        n_ik = struct.unpack_from("<I", datos, off)[0]
        off += 4
        if n_ik > MAX_IK:
            raise ValueError(f"demasiados frames de IK ({n_ik}; máximo {MAX_IK})")
        for _ in range(n_ik):
            if n_total - off < 9:
                raise ValueError("VMD truncado (frames de IK)")
            frame, _visible, n_nombres = struct.unpack_from("<IBI", datos, off)
            off += 9
            if n_nombres > MAX_IK_POR_FRAME:
                raise ValueError(f"un frame de IK trae {n_nombres} IK (máximo {MAX_IK_POR_FRAME})")
            if n_nombres * 21 > n_total - off:
                raise ValueError("VMD truncado (frames de IK)")
            off += n_nombres * 21
            frames_ik.append(frame)

    def max_frame(seccion: str, tam: int, desplazamiento: int) -> int:
        n = cuentas.get(seccion, 0)
        if not n:
            return 0
        vista = np.ndarray((n,), dtype="<u4", buffer=datos, offset=inicios[seccion] + desplazamiento,
                           strides=(tam,))
        return int(vista.max())

    frames = max(max_frame("huesos", 111, 15), max_frame("morfos", 23, 15), max(frames_ik, default=0))
    if frames > MAX_FRAMES:
        raise ValueError(f"el VMD dura más de {int(MAX_FRAMES / FPS_VMD / 60)} minutos")
    huesos, morfos, camara = cuentas["huesos"], cuentas["morfos"], cuentas["camara"]
    if huesos == 0 and morfos == 0 and camara == 0:
        raise ValueError("el VMD está vacío")
    return {
        "version": version, "modelo": texto_limpio(modelo, 40),
        "huesos": huesos, "morfos": morfos, "camara": camara,
        "luces": cuentas["luces"], "sombras": cuentas["sombras"], "ik": n_ik,
        "frames": frames, "duracion": round(frames / FPS_VMD, 3),
        "solo_camara": huesos == 0 and morfos == 0 and camara > 0,
        "solo_morfos": huesos == 0 and morfos > 0,
    }


def info_vmd(ruta: Any, *, max_bytes: int = MAX_VMD_BYTES) -> Dict[str, Any]:
    """{version, modelo, huesos, morfos, camara, luces, sombras, ik, frames, duracion,
    solo_camara, solo_morfos}. Las cuentas se recorren por saltos y cada una tiene que
    caber en lo que queda. ValueError con texto si no vale."""
    return info_vmd_bytes(_leer_limitado(Path(ruta), max_bytes, "VMD"))


def info_vrma_bytes(datos: bytes) -> Dict[str, Any]:
    """Lo que dice un .vrma (GLB). ValueError con texto."""
    inicio = datos[:64].lstrip()
    if inicio[:1] == b"{" or inicio[:4] == b"\xef\xbb\xbf{":
        raise ValueError("es un .gltf de texto: hace falta el .vrma binario (GLB)")
    if len(datos) < 20 or datos[:4] != b"glTF":
        raise ValueError("no es un .vrma (falta la cabecera glTF)")
    version, largo = struct.unpack_from("<II", datos, 4)
    if version != 2:
        raise ValueError(f"glTF versión {version} (solo la 2)")
    if largo > len(datos) or largo < 20:
        raise ValueError("el .vrma está truncado")
    clen, ctipo = struct.unpack_from("<II", datos, 12)
    if ctipo != 0x4E4F534A:
        raise ValueError("el .vrma no empieza por su JSON")
    if clen > MAX_VRMA_JSON:
        raise ValueError(f"el JSON del .vrma pesa más de {MAX_VRMA_JSON // _MB} MB")
    if 20 + clen > largo:
        raise ValueError("el .vrma está truncado (JSON)")
    try:
        j = json.loads(datos[20:20 + clen].decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise ValueError("el JSON del .vrma está roto") from e
    if not isinstance(j, dict):
        raise ValueError("el JSON del .vrma está roto")
    usados = j.get("extensionsUsed")
    if not isinstance(usados, list) or "VRMC_vrm_animation" not in usados:
        raise ValueError("no es una animación VRM (falta VRMC_vrm_animation)")
    for seccion in ("buffers", "images"):
        lista = j.get(seccion) or []
        if not isinstance(lista, list):
            raise ValueError(f"«{seccion}» mal formado")
        for item in lista:
            if isinstance(item, dict) and "uri" in item:
                raise ValueError("el .vrma pide archivos de fuera (uri): no se admite")
    accessors = j.get("accessors") if isinstance(j.get("accessors"), list) else []
    duracion = 0.0
    for anim in j.get("animations") or []:
        if not isinstance(anim, dict):
            continue
        for s in anim.get("samplers") or []:
            idx = s.get("input") if isinstance(s, dict) else None
            if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(accessors):
                acc = accessors[idx]
                mx = acc.get("max") if isinstance(acc, dict) else None
                if isinstance(mx, list) and mx and isinstance(mx[0], (int, float)) and math.isfinite(mx[0]):
                    duracion = max(duracion, float(mx[0]))
    ext = (j.get("extensions") or {}).get("VRMC_vrm_animation") if isinstance(j.get("extensions"), dict) else None
    ext = ext if isinstance(ext, dict) else {}
    humanoid = ext.get("humanoid") if isinstance(ext.get("humanoid"), dict) else {}
    huesos = humanoid.get("humanBones") if isinstance(humanoid.get("humanBones"), dict) else {}
    expr = ext.get("expressions") if isinstance(ext.get("expressions"), dict) else {}
    n_expr = sum(len(v) for k, v in expr.items() if k in ("preset", "custom") and isinstance(v, dict))
    return {"duracion": round(duracion, 3), "huesos": len(huesos), "expresiones": n_expr,
            "mirada": "lookAt" in ext}


def info_vrma(ruta: Any, *, max_bytes: int = MAX_VRMA_BYTES) -> Dict[str, Any]:
    """{duracion, huesos, expresiones, mirada}: magia GLB v2, `VRMC_vrm_animation`
    usada y NINGÚN `uri` en buffers ni imágenes. ValueError con texto."""
    return info_vrma_bytes(_leer_limitado(Path(ruta), max_bytes, ".vrma"))


def tipo_audio_bytes(b: bytes) -> Optional[str]:
    if len(b) < 4:
        return None
    if b[:3] == b"ID3":
        return "mp3"
    if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:
        return "aac" if (b[1] & 0x06) == 0 else "mp3"   # ADTS (capa 00) o MPEG audio
    if b[:4] == b"OggS":
        return "ogg"
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "wav"
    if b[:4] == b"fLaC":
        return "flac"
    if b[4:8] == b"ftyp":
        return "m4a"
    if b[:8] == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11":
        return "wma"
    return None


def tipo_audio(ruta: Any) -> Optional[str]:
    """'mp3'|'ogg'|'wav'|'flac'|'m4a'|'aac'|'wma'|None, por la magia (no por la extensión)."""
    try:
        with open(ruta, "rb") as f:
            return tipo_audio_bytes(f.read(16))
    except OSError:
        return None


# ── Metadatos (lune.json) ────────────────────────────────────────────────────────

def _numero(v: Any, lo: float, hi: float, clave: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            if isinstance(v, str) and v.strip():
                v = float(v)
            else:
                raise ValueError
        except ValueError:
            raise ValueError(f"«{clave}» tiene que ser un número") from None
    f = float(v)
    if not math.isfinite(f) or f < lo or f > hi:
        raise ValueError(f"«{clave}» fuera de rango ({lo:g} a {hi:g})")
    return f


def validar_meta(cambios: Any, *, estricto: bool = True) -> Dict[str, Any]:
    """Las claves conocidas de `cambios`, validadas. `estricto`: ValueError si un valor
    no vale; si no, se descarta (al leer un lune.json escrito a mano)."""
    if not isinstance(cambios, dict):
        if estricto:
            raise ValueError("los metadatos tienen que ser un objeto")
        return {}
    out: Dict[str, Any] = {}
    for clave, v in cambios.items():
        try:
            if clave in ("titulo", "autor_cancion", "autor_mmd"):
                out[clave] = texto_limpio(v, MAX_TEXTO)
            elif clave == "offset_ms":
                out[clave] = int(round(_numero(v, -500, 500, clave)))
            elif clave == "brazo_a_grados":
                out[clave] = round(_numero(v, 25, 45, clave), 1)
            elif clave == "en_el_sitio":
                if v is not None and not isinstance(v, bool):
                    raise ValueError("«en_el_sitio» tiene que ser sí, no o vacío")
                out[clave] = v
            elif clave == "bpm":
                out[clave] = None if v is None or v == "" else round(_numero(v, 40, 240, clave), 2)
        except ValueError:
            if estricto:
                raise
    return out


def leer_meta(ruta: Optional[Path]) -> Dict[str, Any]:
    """lune.json → META_DEFECTO con lo que valga del archivo (lo roto se ignora)."""
    meta = dict(META_DEFECTO)
    if ruta is None:
        return meta
    try:
        if es_enlace(ruta) or ruta.stat().st_size > MAX_META_BYTES:
            return meta
        with open(ruta, "r", encoding="utf-8-sig") as f:
            crudo = json.load(f)
    except (OSError, ValueError, RecursionError):
        return meta
    meta.update(validar_meta(crudo, estricto=False))
    return meta


def escribir_json_atomico(ruta: Path, obj: Any) -> None:
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, ruta)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


# ── Pulso de la canción (mascotas sin esqueleto, D1) ─────────────────────────────

def envolvente_pico(pcm: Any, sr: int = PULSO_SR, hz: int = PULSO_HZ) -> Tuple[np.ndarray, np.ndarray]:
    """(t, pico) a `hz`: el pico absoluto de cada trozo (0..1), con t en su centro."""
    x = np.asarray(pcm)
    if x.size == 0:
        return np.zeros(0), np.zeros(0)
    if x.dtype.kind in "iu":
        a = np.abs(x.astype(np.int32)).astype(np.float32) / 32768.0
    else:
        a = np.abs(x.astype(np.float32))
    hop = sr / float(hz)
    n = int(len(a) / hop)
    if n < 2:
        return np.zeros(0), np.zeros(0)
    ini = np.floor(np.arange(n) * hop).astype(np.int64)
    fin = int(math.floor(n * hop))
    picos = np.maximum.reduceat(a[:fin], ini)
    t = (np.arange(n) + 0.5) / float(hz)
    return t, np.minimum(picos, 1.0).astype(np.float64)


def _fuerza_inicio(t: np.ndarray, picos: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Como nucleo/pulso: diferencia positiva del logaritmo de la envolvente."""
    from nucleo.pulso import EPS_LOG
    suelo = max(EPS_LOG, 0.1 * float(np.percentile(picos, 95)))
    le = np.log(picos + suelo)
    fuerza = np.maximum(0.0, np.diff(le))
    t_ini = 0.5 * (t[1:] + t[:-1])
    ok = fuerza > 1e-6
    return fuerza[ok], t_ini[ok]


def _puntuar_periodo(fuerza: np.ndarray, t_ini: np.ndarray, periodo: float) -> float:
    s = 0.0
    for h in (1, 2, 3, 4):
        s += abs(complex(np.sum(fuerza * np.exp(-2j * np.pi * h * t_ini / periodo))))
    return s


def _afinar_global(fuerza: np.ndarray, t_ini: np.ndarray, periodo: float) -> float:
    """El periodo que más concentra la fuerza en fase en toda la canción (dos pasadas)."""
    for margen, pasos in ((0.015, 61), (0.0006, 25)):
        cands = periodo * np.linspace(1.0 - margen, 1.0 + margen, pasos)
        puntos = [_puntuar_periodo(fuerza, t_ini, float(p)) for p in cands]
        periodo = float(cands[int(np.argmax(puntos))])
    return periodo


def analizar_pcm(pcm: Any, sr: int = PULSO_SR, *, bpm_fijo: Optional[float] = None) -> Dict[str, float]:
    """{bpm, fase0, confianza} de una canción en PCM mono.

    1. Envolvente de pico a 50 Hz → `nucleo.pulso.SeguidorPulso` (t = tiempo de la
       muestra), estimando cada ≥1 s; `bpm` = mediana de las estimaciones con
       confianza ≥ 0.3 (o `bpm_fijo`, el del lune.json).
    2. Afinado del periodo en toda la canción y `fase0` (la fase en t = 0) con el
       primer armónico de la fuerza de inicio: con el tempo de toda la canción la
       fase no se desvía al final.
    Sin pulso claro: 120 BPM, fase 0, confianza 0."""
    from nucleo.pulso import SILENCIO, SeguidorPulso
    res = {"bpm": float(bpm_fijo) if bpm_fijo else BPM_DEFECTO, "fase0": 0.0, "confianza": 0.0}
    t, picos = envolvente_pico(pcm, sr)
    if len(t) < 3 * PULSO_HZ or float(picos.max()) < SILENCIO:
        return res
    s = SeguidorPulso(hz=PULSO_HZ)
    buenas: List[Tuple[float, float]] = []
    n_est = 0
    paso = max(1.0, float(t[-1]) / 300.0)
    proximo = SeguidorPulso.MIN_DATOS_S + 1.0
    for ti, pi in zip(t.tolist(), picos.tolist()):
        s.alimentar(pi, ti)
        if ti >= proximo:
            proximo = ti + paso
            p = s.estimar(ti)
            n_est += 1
            if p.confianza >= SeguidorPulso.CONF_MIN:
                buenas.append((p.bpm, p.confianza))
    fuerza, t_ini = _fuerza_inicio(t, picos)
    if bpm_fijo:
        bpm = float(bpm_fijo)
        frac = 1.0
    elif buenas:
        bpm = float(np.median([b for b, _ in buenas]))
        frac = len(buenas) / max(1, n_est)
    else:
        return res
    if fuerza.size < 4:
        res["bpm"] = round(bpm, 2)
        return res
    periodo = 60.0 / bpm
    if not bpm_fijo:
        periodo = _afinar_global(fuerza, t_ini, periodo)
        bpm = 60.0 / periodo
    w = fuerza * fuerza
    z = complex(np.sum(w * np.exp(-2j * np.pi * t_ini / periodo)))
    coh = abs(z) / max(1e-12, float(w.sum()))
    fase0 = (math.atan2(z.imag, z.real) / (2 * math.pi)) % 1.0
    conf = math.sqrt(max(0.0, min(1.0, frac * min(1.0, 1.5 * coh))))
    return {"bpm": round(bpm, 2), "fase0": round(fase0 % 1.0, 4), "confianza": round(conf, 3)}


# ── El baile ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Baile:
    """Un baile de la biblioteca. Las rutas son absolutas y están dentro de la carpeta."""
    id: str
    titulo: str
    tipo: str                                 # 'vmd' | 'vrma' ('' si no hay movimiento válido)
    movimiento: Tuple[Path, ...]
    cara: Tuple[Path, ...]
    audio: Optional[Path]                     # la canción original
    audio_web: Optional[Path]                 # la que suena en la página (la misma o la convertida)
    carpeta: Path                             # la del baile (o la de bailes/ si son sueltos)
    meta: Dict[str, Any]
    duracion: Optional[float]
    favorito: bool
    desactivado: bool
    problema: str                             # '' o el motivo por el que no se puede bailar
    aviso: str = ""                           # notas que no impiden bailarlo
    archivos: Tuple[Path, ...] = ()           # todos los del baile (para quitarlo)
    suelto: bool = False
    tipo_audio: str = ""
    ruta_meta: Optional[Path] = field(default=None, compare=False)

    @property
    def jugable(self) -> bool:
        return not self.problema and bool(self.movimiento)

    @property
    def autor(self) -> str:
        return str(self.meta.get("autor_cancion") or "")


def baile_a_dict(b: Baile) -> Dict[str, Any]:
    """Lo que ven el panel y el modelo (los textos vienen de nombres de archivo)."""
    m = b.meta or {}
    return {
        "id": b.id, "titulo": texto_limpio(b.titulo), "tipo": b.tipo,
        "autor_cancion": texto_limpio(m.get("autor_cancion")), "autor_mmd": texto_limpio(m.get("autor_mmd")),
        "duracion": round(float(b.duracion), 1) if b.duracion else None,
        "audio": b.audio is not None, "audio_web": b.audio_web is not None,
        "favorito": bool(b.favorito), "desactivado": bool(b.desactivado),
        "problema": texto_limpio(b.problema, 200), "aviso": texto_limpio(b.aviso, 200),
        "offset_ms": int(m.get("offset_ms") or 0), "brazo_a_grados": float(m.get("brazo_a_grados") or 35.0),
        "en_el_sitio": m.get("en_el_sitio"), "bpm": m.get("bpm"), "suelto": bool(b.suelto),
    }


def _orden(b: Baile) -> Tuple[Any, ...]:
    return (not b.favorito, normalizar(b.titulo), b.id)


def _heno(b: Baile) -> str:
    """Donde se busca: título, autores y carpeta, normalizados (se guarda con la foto)."""
    return normalizar(" ".join((b.titulo, str(b.meta.get("autor_cancion") or ""),
                                str(b.meta.get("autor_mmd") or ""), b.carpeta.name if not b.suelto else "")))


# ── La biblioteca ────────────────────────────────────────────────────────────────

class Biblioteca:
    """La carpeta de bailes (ver la cabecera del módulo). Segura entre hilos.

    La FOTO (los bailes del último escaneo) se lee sin esperar nunca a un escaneo ni a un
    importar: `foto`, `de_la_foto`, `buscar_en_foto` (lo que usa el reproductor desde el hilo
    de Qt) no escanean jamás; `bailes`, `obtener` y `buscar` solo la primera vez. El escaneo
    lee los VMD FUERA del cerrojo de la foto (construye la lista nueva y la cambia de golpe) y
    `importar` copia y convierte sin cerrojo (la carpeta de destino se reserva creándola).
    Cerrojos, siempre en este orden: `_lock_carpeta` (guardar_meta, quitar) → `_lock_escaneo`
    (un escaneo a la vez) → `_lock` (la foto y la caché de info: solo un momento)."""

    def __init__(self, carpeta: Any = CARPETA, cache: Any = CACHE, *, config: Any = None,
                 ffmpeg: Optional[str] = None, ejecutar: Callable = ejecutar_proceso,
                 reloj: Callable[[], float] = time.time):
        self.carpeta = Path(carpeta)
        self.cache = Path(cache)
        self.config = config
        self._ffmpeg = ffmpeg
        self._ejecutar = ejecutar
        self._reloj = reloj
        self._lock = threading.RLock()
        self._lock_escaneo = threading.Lock()
        self._lock_carpeta = threading.RLock()
        self._lock_marcas = threading.Lock()
        self._infos: Dict[Tuple[str, int, int], Tuple[bool, Any]] = {}
        # La foto se cambia entera (copia al escribir): quien la lee se lleva una referencia.
        self._bailes: Dict[str, Baile] = {}
        self._foto: List[Baile] = []
        self._henos: Dict[str, str] = {}
        self._escaneada = False
        self._version = 0             # cambios hechos aquí (meta, quitar…): el escaneo en vuelo repite
        self._fav_mem: List[str] = []
        self._des_mem: List[str] = []
        self.error = ""
        self.truncada = False

    # ── Carpeta ──────────────────────────────────────────────────────────────────
    def _resolver(self) -> Tuple[Optional[Path], str]:
        """(carpeta resuelta o None si no sirve, error)."""
        red = "La carpeta de bailes no puede estar en la red."
        if es_unc(self.carpeta):
            return None, red
        try:
            base = self.carpeta.resolve()
        except (OSError, RuntimeError):
            return None, ""
        if es_unc(base):
            return None, red
        return (base if base.is_dir() else None), ""

    def _base(self) -> Optional[Path]:
        """La carpeta resuelta, o None si no sirve (de red, o no es una carpeta)."""
        base, error = self._resolver()
        if error:
            self.error = error
        return base

    def asegurar_carpeta(self) -> bool:
        """Crea bailes/ con su LEEME.txt si no existe. False si no se pudo."""
        if es_unc(self.carpeta):
            self.error = "La carpeta de bailes no puede estar en la red."
            return False
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            leeme = self.carpeta / LEEME
            if not leeme.exists():
                leeme.write_text(TEXTO_LEEME, encoding="utf-8")
        except OSError as e:
            self.error = f"No pude crear la carpeta de bailes: {e.strerror or e}"
            return False
        return self._base() is not None

    # ── Config (favoritos, desactivados) ─────────────────────────────────────────
    def _lista_cfg(self, clave: str) -> List[str]:
        if self.config is None:
            return list(self._fav_mem if clave == "favoritos" else self._des_mem)
        try:
            v = self.config.get("baile", clave, [])
        except Exception:
            v = []
        return [x for x in (v if isinstance(v, list) else []) if id_valido(x)][:MAX_BAILES]

    def _guardar_cfg(self, clave: str, lista: List[str]) -> None:
        if self.config is None:
            if clave == "favoritos":
                self._fav_mem = list(lista)
            else:
                self._des_mem = list(lista)
            return
        self.config.set("baile", clave, list(lista))

    def _marcar(self, clave: str, id_: str, on: bool) -> List[str]:
        if not id_valido(id_):
            raise ValueError("id de baile no válido")
        with self._lock_marcas:
            lista = self._lista_cfg(clave)
            if on and id_ not in lista:
                lista.append(id_)
            elif not on and id_ in lista:
                lista = [x for x in lista if x != id_]
            else:
                return lista
            self._guardar_cfg(clave, lista[:MAX_BAILES])
        # (un escaneo en vuelo vuelve a mirar la config al cambiar la foto: no se pierde)
        with self._lock:
            b = self._bailes.get(id_)
            if b is not None:
                cambio = {"favorito": on} if clave == "favoritos" else {"desactivado": on}
                self._cambiar_foto(id_, _reemplazar(b, **cambio), version=False)
        return lista

    def favorito(self, id_: str, on: bool) -> List[str]:
        """Marca o desmarca un favorito (config baile.favoritos). Devuelve la lista."""
        return self._marcar("favoritos", id_, bool(on))

    def desactivar(self, id_: str, on: bool) -> List[str]:
        """Un desactivado no sale en siguiente/aleatorio (config baile.desactivados)."""
        return self._marcar("desactivados", id_, bool(on))

    # ── Escaneo ──────────────────────────────────────────────────────────────────
    def _info(self, p: Path, tipo: str) -> Tuple[bool, Any]:
        """(True, info) o (False, motivo), con caché por ruta, tamaño y fecha."""
        try:
            st = p.stat()
        except OSError as e:
            return False, f"no se puede leer ({e.strerror or e})"
        clave = (str(p), int(st.st_size), int(st.st_mtime_ns))
        with self._lock:
            hit = self._infos.get(clave)
        if hit is not None:
            return hit
        try:                                        # leer el archivo, sin cerrojo
            if tipo == "vmd":
                r: Tuple[bool, Any] = (True, info_vmd(p, max_bytes=MAX_VMD_BYTES))
            elif tipo == "vrma":
                r = (True, info_vrma(p, max_bytes=MAX_VRMA_BYTES))
            else:
                if st.st_size > MAX_AUDIO_BYTES:
                    raise ValueError(f"la canción pesa {st.st_size / _MB:.1f} MB (máximo {MAX_AUDIO_BYTES // _MB} MB)")
                t = tipo_audio(p)
                if t is None:
                    raise ValueError("no reconozco el formato de la canción")
                r = (True, {"tipo": t})
        except ValueError as e:
            r = (False, str(e))
        except OSError as e:
            r = (False, f"no se puede leer ({e.strerror or e})")
        with self._lock:
            if len(self._infos) > 4 * MAX_BAILES * MAX_ARCHIVOS_BAILE:
                self._infos.clear()
            self._infos[clave] = r
        return r

    def escanear(self, forzar: bool = False) -> List[Baile]:
        """Recorre la carpeta (un nivel de subcarpetas) y devuelve los bailes ordenados
        (favoritos primero y luego por título). No crea la carpeta. Lee FUERA del cerrojo de
        la foto: quien la mira mientras tanto ve la de antes (nunca espera)."""
        with self._lock_escaneo:
            return self._escanear_ya(forzar)

    def _escanear_ya(self, forzar: bool = False) -> List[Baile]:
        """El escaneo (con `_lock_escaneo` ya cogido). Si mientras se leía cambió algo por aquí
        (guardar_meta, quitar, convertir_audio), se vuelve a leer: la foto vieja no pisa el cambio."""
        if forzar:
            with self._lock:
                self._infos.clear()
        for intento in range(3):
            version = self._version
            bailes, error, truncada = self._recorrer()
            with self._lock:
                if self._version == version or intento == 2:
                    self._poner_foto(bailes)
                    self.error, self.truncada = error, truncada
                    return list(self._foto)
        return self.foto()                              # (no se llega)

    def _recorrer(self) -> Tuple[List[Baile], str, bool]:
        """(bailes, error, truncada) de la carpeta tal como está ahora. Sin cerrojos."""
        base, error = self._resolver()
        if base is None:
            return [], error, False
        favs = set(self._lista_cfg("favoritos"))
        dess = set(self._lista_cfg("desactivados"))
        try:
            entradas = sorted(os.scandir(base), key=lambda e: e.name.lower())
        except OSError as e:
            return [], f"No pude leer la carpeta de bailes: {e.strerror or e}", False
        bailes: List[Baile] = []
        sueltos: Dict[str, Dict[str, Any]] = {}
        for e in entradas:
            nombre = e.name
            if nombre.startswith(".") or nombre.lower() == LEEME.lower():
                continue
            ruta = Path(e.path)
            if es_enlace(ruta):
                _log.info("bailes: me salto %s (es un enlace o una junction)", nombre)
                continue
            try:
                es_dir = e.is_dir(follow_symlinks=False)
                es_arch = e.is_file(follow_symlinks=False)
            except OSError:
                continue
            if es_dir:
                b = self._baile_carpeta(base, ruta, favs, dess)
                if b is not None:
                    bailes.append(b)
            elif es_arch:
                low = nombre.lower()
                if not (low.endswith(EXT_MOV) or low.endswith(EXT_AUDIO) or low.endswith(SUFIJO_META)):
                    continue
                clave, base_nombre = clave_grupo(nombre)
                g = sueltos.setdefault(clave, {"nombre": base_nombre, "archivos": []})
                g["archivos"].append(ruta)
        for clave, g in sueltos.items():
            b = self._baile_suelto(base, clave, g["nombre"], g["archivos"], favs, dess)
            if b is not None:
                bailes.append(b)
        error, truncada = "", False
        if len(bailes) > MAX_BAILES:
            truncada = True
            error = f"Hay más de {MAX_BAILES} bailes: solo se ven {MAX_BAILES}."
            bailes = sorted(bailes, key=lambda x: normalizar(x.titulo))[:MAX_BAILES]
        return bailes, error, truncada

    # ── La foto ──────────────────────────────────────────────────────────────────
    def _poner_foto(self, bailes: Iterable[Baile]) -> None:
        """Cambia la foto entera (con `_lock`). Favoritos y desactivados, los de la config de
        AHORA (pudieron cambiar mientras se escaneaba)."""
        favs = set(self._lista_cfg("favoritos"))
        dess = set(self._lista_cfg("desactivados"))
        lista = []
        for b in bailes:
            if b.favorito != (b.id in favs) or b.desactivado != (b.id in dess):
                b = _reemplazar(b, favorito=b.id in favs, desactivado=b.id in dess)
            lista.append(b)
        lista.sort(key=_orden)
        self._bailes = {b.id: b for b in lista}
        self._henos = {b.id: _heno(b) for b in lista}
        self._foto = lista
        self._escaneada = True

    def _cambiar_foto(self, id_: str, nuevo: Optional[Baile], *, version: bool = True) -> None:
        """Un baile de la foto cambia (None: se va), sin escanear. `version`: el escaneo que
        esté leyendo la carpeta vuelve a empezar (su foto no lleva este cambio)."""
        with self._lock:
            bailes = dict(self._bailes)
            henos = dict(self._henos)
            if nuevo is None:
                bailes.pop(id_, None)
                henos.pop(id_, None)
            else:
                bailes[nuevo.id] = nuevo
                henos[nuevo.id] = _heno(nuevo)
            self._bailes = bailes
            self._henos = henos
            self._foto = sorted(bailes.values(), key=_orden)
            if version:
                self._version += 1

    @property
    def escaneada(self) -> bool:
        """¿Hay foto? (se escaneó al menos una vez)."""
        return self._escaneada

    def foto(self) -> List[Baile]:
        """Los bailes del último escaneo, ordenados. NUNCA escanea ni espera ([] si aún no hay)."""
        return list(self._foto)

    def de_la_foto(self, id_: Any) -> Optional[Baile]:
        """El baile `id_` de la foto (sin escanear nunca)."""
        return self._bailes.get(id_) if id_valido(id_) else None

    def filtrar(self, bailes: Iterable[Baile], texto: Any) -> List[Baile]:
        """Por título, autores y carpeta (normalizados; todas las palabras). Vacío = todos."""
        lista = list(bailes)
        q = normalizar(texto)
        if not q:
            return lista
        palabras = q.split()
        henos = self._henos
        out = []
        for b in lista:
            heno = henos.get(b.id)
            if heno is None:
                heno = _heno(b)
            if all(p in heno for p in palabras):
                out.append(b)
        return out

    def buscar_en_foto(self, texto: Any) -> List[Baile]:
        """`buscar` sobre la foto, sin escanear nunca (el panel y el modelo desde el hilo de Qt)."""
        return self.filtrar(self._foto, texto)

    def _primer_escaneo(self) -> None:
        with self._lock_escaneo:                         # si otro hilo ya escanea, se espera a ese
            if not self._escaneada:
                self._escanear_ya()

    def bailes(self) -> List[Baile]:
        """Los del último escaneo (escanea solo si aún no se hizo nunca)."""
        if not self._escaneada:
            self._primer_escaneo()
        return self.foto()

    def obtener(self, id_: Any) -> Optional[Baile]:
        """El baile `id_` de la foto (escanea solo si aún no se hizo nunca: un id que no está
        no reescanea; para ver lo nuevo de la carpeta, `escanear`)."""
        if not id_valido(id_):
            return None
        if not self._escaneada:
            self._primer_escaneo()
        return self._bailes.get(id_)

    def buscar(self, texto: Any) -> List[Baile]:
        """`filtrar` sobre la foto (escanea solo si aún no se hizo nunca)."""
        return self.filtrar(self.bailes(), texto)

    def _archivos_carpeta(self, carpeta: Path) -> List[Path]:
        out = []
        try:
            for e in sorted(os.scandir(carpeta), key=lambda e: e.name.lower()):
                low = e.name.lower()
                if e.name.startswith("."):
                    continue
                if not (low.endswith(EXT_MOV) or low.endswith(EXT_AUDIO) or low == META):
                    continue
                p = Path(e.path)
                if es_enlace(p) or not e.is_file(follow_symlinks=False):
                    continue
                out.append(p)
        except OSError:
            pass
        return out

    def _baile_carpeta(self, base: Path, carpeta: Path, favs: set, dess: set) -> Optional[Baile]:
        archivos = self._archivos_carpeta(carpeta)
        if not archivos:
            return None
        id_ = id_carpeta(carpeta.name)
        metas = [p for p in archivos if p.name.lower() == META]
        meta_ruta = metas[0] if metas else carpeta / META
        otros = [p for p in archivos if p.name.lower() != META]
        if not otros:
            return None
        problema = ""
        motivo = motivo_nombre(carpeta.name)
        if motivo:
            problema = f"la carpeta no vale: {motivo}"
        elif len(archivos) > MAX_ARCHIVOS_BAILE:
            problema = f"demasiados archivos ({len(archivos)}; máximo {MAX_ARCHIVOS_BAILE})"
        preferidas = {carpeta.name.lower()}
        return self._construir(base, id_, carpeta.name, carpeta, otros, meta_ruta if metas else None,
                               meta_destino=meta_ruta, suelto=False, favs=favs, dess=dess,
                               problema_previo=problema, preferidas=preferidas, todos=archivos)

    def _baile_suelto(self, base: Path, clave: str, nombre: str, archivos: List[Path],
                      favs: set, dess: set) -> Optional[Baile]:
        metas = [p for p in archivos if p.name.lower().endswith(SUFIJO_META)]
        otros = [p for p in archivos if p not in metas]
        if not any(p.suffix.lower() in EXT_MOV for p in otros):
            return None                                     # una canción suelta no es un baile
        problema = ""
        if len(archivos) > MAX_ARCHIVOS_BAILE:
            problema = f"demasiados archivos ({len(archivos)}; máximo {MAX_ARCHIVOS_BAILE})"
        return self._construir(base, id_suelto(clave), nombre, base, otros, metas[0] if metas else None,
                               meta_destino=metas[0] if metas else base / f"{nombre}{SUFIJO_META}",
                               suelto=True, favs=favs, dess=dess, problema_previo=problema,
                               preferidas={clave}, todos=archivos)

    def _construir(self, base: Path, id_: str, nombre: str, carpeta: Path, archivos: List[Path],
                   meta_ruta: Optional[Path], *, meta_destino: Path, suelto: bool, favs: set, dess: set,
                   problema_previo: str, preferidas: set, todos: List[Path]) -> Baile:
        movs: List[Tuple[Path, dict]] = []
        caras: List[Tuple[Path, dict]] = []
        vrmas: List[Tuple[Path, dict]] = []
        audios: List[Tuple[Path, str]] = []
        avisos: List[str] = []
        errores: List[str] = []
        for p in archivos:
            ext = p.suffix.lower()
            motivo = motivo_nombre(p.name)
            if motivo:
                errores.append(f"{p.name}: {motivo}")
                continue
            try:
                if not p.resolve().is_relative_to(base):
                    errores.append(f"{p.name}: fuera de la carpeta")
                    continue
            except (OSError, RuntimeError, ValueError):
                errores.append(f"{p.name}: no se puede leer")
                continue
            if ext == ".vmd":
                ok, info = self._info(p, "vmd")
                if not ok:
                    errores.append(f"{p.name}: {info}")
                elif info["solo_camara"]:
                    avisos.append(f"{p.name}: cámara (no se usa)")
                elif info["solo_morfos"]:
                    caras.append((p, info))
                else:
                    movs.append((p, info))
            elif ext == ".vrma":
                ok, info = self._info(p, "vrma")
                if ok:
                    vrmas.append((p, info))
                else:
                    errores.append(f"{p.name}: {info}")
            elif ext in EXT_AUDIO:
                ok, info = self._info(p, "audio")
                if ok:
                    audios.append((p, info["tipo"]))
                else:
                    errores.append(f"{p.name}: {info}")

        meta = leer_meta(meta_ruta)
        titulo = meta.get("titulo") or texto_limpio(nombre, MAX_TEXTO) or "Baile"
        tipo = ""
        movimiento: Tuple[Path, ...] = ()
        cara: Tuple[Path, ...] = ()
        duraciones: List[float] = []
        problema = problema_previo
        if movs:
            tipo = "vmd"
            if len(movs) > MAX_MOVIMIENTO:
                avisos.append(f"hay {len(movs)} VMD de movimiento: uso {MAX_MOVIMIENTO}")
            if len(caras) > MAX_CARA:
                avisos.append(f"hay {len(caras)} VMD de cara: uso {MAX_CARA}")
            if vrmas:
                avisos.append("hay VMD y .vrma: uso los VMD")
            movimiento = tuple(p for p, _ in movs[:MAX_MOVIMIENTO])
            cara = tuple(p for p, _ in caras[:MAX_CARA])
            duraciones = [i["duracion"] for _, i in movs[:MAX_MOVIMIENTO] + caras[:MAX_CARA]]
        elif vrmas:
            tipo = "vrma"
            if len(vrmas) > 1:
                avisos.append(f"hay {len(vrmas)} .vrma: uso {vrmas[0][0].name}")
            movimiento = (vrmas[0][0],)
            duraciones = [vrmas[0][1]["duracion"]]
        elif not problema:
            if errores:
                problema = errores[0]
            elif caras:
                problema = "solo hay cara: falta el VMD de movimiento"
            else:
                problema = "falta el movimiento (.vmd o .vrma)"
        if errores and movimiento:
            avisos.extend(errores[:2])

        audio: Optional[Path] = None
        t_audio = ""
        if audios:
            def preferencia(item: Tuple[Path, str]) -> Tuple[int, int, str]:
                p, t = item
                mismo = clave_grupo(p.name)[0] in preferidas or p.stem.lower() in preferidas
                return (0 if mismo else 1, 0 if t in TIPOS_AUDIO_WEB else 1, p.name.lower())
            elegido = sorted(audios, key=preferencia)[0]
            audio, t_audio = elegido
            if len(audios) > 1:
                avisos.append(f"hay {len(audios)} canciones: uso {audio.name}")
        audio_web: Optional[Path] = None
        if audio is not None:
            if t_audio in TIPOS_AUDIO_WEB:
                audio_web = audio
            else:
                conv = self.cache / f"{id_}.ogg"
                try:
                    if conv.is_file() and conv.stat().st_mtime_ns >= audio.stat().st_mtime_ns:
                        audio_web = conv
                    else:
                        avisos.append("la canción se convertirá a .ogg al bailarla")
                except OSError:
                    pass
        b = Baile(
            id=id_, titulo=titulo, tipo=tipo, movimiento=movimiento, cara=cara, audio=audio,
            audio_web=audio_web, carpeta=carpeta, meta=meta,
            duracion=max(duraciones) if duraciones else None,
            favorito=id_ in favs, desactivado=id_ in dess, problema=problema,
            aviso="; ".join(avisos)[:300], archivos=tuple(todos), suelto=suelto, tipo_audio=t_audio,
            ruta_meta=meta_destino,
        )
        if not b.problema:
            u = self._urls(base, b)
            if any(len(x) > MAX_URL for x in u["motion"] + u["cara"] + ([u["audio"]] if u["audio"] else [])):
                b = _reemplazar(b, problema="nombres demasiado largos para servirlos (acórtalos)")
        return b

    # ── URL ──────────────────────────────────────────────────────────────────────
    def _urls(self, base: Path, b: Baile) -> Dict[str, Any]:
        def url(p: Path) -> str:
            return PREFIJO_WEB + quote(p.relative_to(base).as_posix(), safe="/")
        audio = None
        if b.audio_web is not None:
            try:
                if b.audio_web.parent.resolve() == self.cache.resolve():
                    audio = PREFIJO_CACHE + quote(b.audio_web.name, safe="")
                else:
                    audio = url(b.audio_web)
            except (OSError, ValueError):
                audio = None
        return {"motion": [url(p) for p in b.movimiento], "cara": [url(p) for p in b.cara], "audio": audio}

    def urls(self, b: Baile) -> Dict[str, Any]:
        """{"motion": ["/bailes/…"], "cara": [...], "audio": url|None}, codificadas con
        `quote(ruta_posix, safe="/")` (ASCII; el servidor las decodifica una vez)."""
        base = self._base() or self.carpeta
        return self._urls(base, b)

    # ── Metadatos ────────────────────────────────────────────────────────────────
    def guardar_meta(self, id_: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        """Valida `cambios` y escribe el lune.json del baile (atómico). Devuelve la meta
        completa. ValueError con texto si algo no vale."""
        nuevos = validar_meta(cambios, estricto=True)
        with self._lock_carpeta:
            b = self.obtener(id_)
            if b is None:
                raise ValueError("No encuentro ese baile.")
            base = self._base()
            destino = b.ruta_meta
            if base is None or destino is None:
                raise ValueError("No puedo escribir en la carpeta de bailes.")
            try:
                ok = destino.parent.resolve().is_relative_to(base) and not motivo_nombre(destino.name)
            except (OSError, ValueError):
                ok = False
            if not ok or (destino.exists() and es_enlace(destino)):
                raise ValueError("No puedo escribir los datos de ese baile.")
            meta = dict(b.meta)
            meta.update(nuevos)
            try:
                escribir_json_atomico(destino, meta)
            except OSError as e:
                raise ValueError(f"No pude guardar: {e.strerror or e}") from e
            nb_ = self._releer(base, b, destino)
            return dict(nb_.meta) if nb_ is not None else meta

    def _releer(self, base: Path, b: Baile, ruta_meta: Path) -> Optional[Baile]:
        """Vuelve a leer UN baile (tras escribir su lune.json) y lo cambia en la foto, sin
        escanear la carpeta entera (guardar_meta va en el hilo de Qt)."""
        favs = set(self._lista_cfg("favoritos"))
        dess = set(self._lista_cfg("desactivados"))
        if not b.suelto:
            nb_ = self._baile_carpeta(base, b.carpeta, favs, dess)
        else:
            # Sus archivos más el lune.json (ya existe); el nombre base, el del primero por
            # orden, como al escanear.
            archivos = sorted(set(b.archivos) | {ruta_meta}, key=lambda p: p.name.lower())
            clave, nombre = clave_grupo(archivos[0].name)
            if id_suelto(clave) != b.id:                  # (no debería) → escaneo entero
                self.escanear()
                return self.de_la_foto(b.id)
            nb_ = self._baile_suelto(base, clave, nombre, archivos, favs, dess)
        self._cambiar_foto(b.id, nb_)
        return nb_

    # ── ffmpeg ───────────────────────────────────────────────────────────────────
    def _exe(self) -> str:
        exe = self._ffmpeg or _ffmpeg_defecto()
        if not exe:
            raise ErrorBailes("Hace falta ffmpeg (pip install imageio-ffmpeg).")
        return exe

    def _convertir(self, origen: Path, destino: Path) -> None:
        """Audio → Ogg Opus con ffmpeg (sin shell, -nostdin, 120 s)."""
        exe = self._exe()
        tmp = destino.with_name(destino.name + ".tmp")
        cmd = [exe, "-nostdin", "-v", "error", "-y", "-i", str(origen), "-vn", "-map", "0:a:0",
               "-map_metadata", "-1", "-c:a", "libopus", "-b:a", "128k", "-f", "ogg", str(tmp)]
        try:
            r = self._ejecutar(cmd, capture_output=True, timeout=TIEMPO_FFMPEG_S, **_sin_ventana())
        except subprocess.TimeoutExpired as e:
            raise ErrorBailes("ffmpeg tardó demasiado en convertir la canción.") from e
        except OSError as e:
            raise ErrorBailes(f"No pude ejecutar ffmpeg: {e}") from e
        try:
            if getattr(r, "returncode", 1) != 0:
                err = (getattr(r, "stderr", b"") or b"").decode("utf-8", "replace").strip().splitlines()
                raise ErrorBailes(f"ffmpeg no pudo convertir {origen.name}: {err[-1] if err else 'error'}"[:300])
            if tipo_audio(tmp) != "ogg":
                raise ErrorBailes("la conversión no dio un .ogg válido")
            os.replace(tmp, destino)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def convertir_audio(self, b: Baile) -> Tuple[bool, str, Optional[Path]]:
        """Conversión diferida de .m4a/.aac/.wma a cache/bailes/<id>.ogg."""
        if b.audio is None:
            return False, "Este baile no tiene canción.", None
        if b.audio_web is not None:
            return True, "", b.audio_web
        destino = self.cache / f"{b.id}.ogg"
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            self._convertir(b.audio, destino)
        except ErrorBailes as e:
            return False, str(e), None
        except OSError as e:
            return False, f"No pude convertir la canción: {e.strerror or e}", None
        with self._lock:
            actual = self._bailes.get(b.id) if id_valido(b.id) else None
            if actual is not None:
                self._cambiar_foto(b.id, _reemplazar(actual, audio_web=destino))
        return True, "", destino

    def _decodificar_pulso(self, ruta: Path) -> np.ndarray:
        exe = self._exe()
        cmd = [exe, "-nostdin", "-v", "error", "-i", str(ruta), "-vn", "-map", "0:a:0",
               "-ac", "1", "-ar", str(PULSO_SR), "-t", str(PULSO_MAX_S), "-f", "s16le", "pipe:1"]
        try:
            r = self._ejecutar(cmd, capture_output=True, timeout=TIEMPO_FFMPEG_S, **_sin_ventana())
        except subprocess.TimeoutExpired as e:
            raise ErrorBailes("ffmpeg tardó demasiado en leer la canción.") from e
        except OSError as e:
            raise ErrorBailes(f"No pude ejecutar ffmpeg: {e}") from e
        if getattr(r, "returncode", 1) != 0:
            raise ErrorBailes(f"ffmpeg no pudo leer {ruta.name}.")
        raw = getattr(r, "stdout", b"") or b""
        return np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2")

    def analizar_pulso(self, b: Baile) -> Dict[str, Any]:
        """{bpm, fase0, confianza} de la canción del baile (D1: animada, sprites, patata).
        Con caché en cache/bailes/<id>.pulso.json (se rehace si cambia la canción o el
        bpm del lune.json). Si falla: 120 BPM (o el del lune.json) y confianza 0."""
        bpm_meta = b.meta.get("bpm") if isinstance(b.meta, dict) else None
        defecto = {"bpm": float(bpm_meta) if bpm_meta else BPM_DEFECTO, "fase0": 0.0, "confianza": 0.0}
        if b.audio is None or not id_valido(b.id):
            return dict(defecto)
        try:
            st = b.audio.stat()
        except OSError:
            return dict(defecto)
        firma = {"v": PULSO_VERSION, "audio": b.audio.name, "tam": int(st.st_size),
                 "mtime": int(st.st_mtime_ns), "bpm_meta": bpm_meta}
        ruta = self.cache / f"{b.id}.pulso.json"
        try:
            if ruta.is_file() and ruta.stat().st_size < 4096:
                guardado = json.loads(ruta.read_text(encoding="utf-8"))
                if isinstance(guardado, dict) and all(guardado.get(k) == v for k, v in firma.items()):
                    return {"bpm": float(guardado["bpm"]), "fase0": float(guardado["fase0"]),
                            "confianza": float(guardado["confianza"])}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            pcm = self._decodificar_pulso(b.audio)
            res = analizar_pcm(pcm, PULSO_SR, bpm_fijo=bpm_meta)
        except Exception as e:                                   # noqa: BLE001
            _log.info("bailes: sin pulso para %s: %s", b.id, e)
            return {**defecto, "error": str(e)[:200]}
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            escribir_json_atomico(ruta, {**firma, **res})
        except OSError:
            pass
        return res

    # ── Importar y quitar ────────────────────────────────────────────────────────
    def importar(self, rutas: Iterable[Any]) -> Tuple[bool, str, Optional[str]]:
        """Copia (nunca mueve) los archivos elegidos a bailes/<nombre>/, validándolos
        ANTES de copiar. .m4a/.aac/.wma se convierten a .ogg. (ok, texto, id)."""
        vistas: List[Path] = []
        for r in rutas or []:
            p = Path(str(r))
            if p not in vistas:
                vistas.append(p)
        if not vistas:
            return False, "No elegiste ningún archivo.", None
        if len(vistas) > MAX_ARCHIVOS_BAILE:
            return False, f"Como mucho {MAX_ARCHIVOS_BAILE} archivos por baile.", None
        movs: List[Path] = []
        caras: List[Path] = []
        audios: List[Tuple[Path, str]] = []
        notas: List[str] = []
        for p in vistas:
            nombre = texto_limpio(p.name, 60) or "archivo"
            if es_unc(p):
                return False, f"{nombre}: no importo desde carpetas de red.", None
            try:
                if es_enlace(p) or not p.is_file():
                    return False, f"{nombre}: no es un archivo normal.", None
            except OSError:
                return False, f"{nombre}: no se puede leer.", None
            ext = p.suffix.lower()
            try:
                if ext == ".vmd":
                    info = info_vmd(p)
                    if info["solo_camara"]:
                        notas.append(f"{nombre} es de cámara y no se usa")
                        continue
                    (caras if info["solo_morfos"] else movs).append(p)
                elif ext == ".vrma":
                    info_vrma(p)
                    movs.append(p)
                elif ext in EXT_AUDIO:
                    if p.stat().st_size > MAX_AUDIO_BYTES:
                        raise ValueError(f"la canción pesa más de {MAX_AUDIO_BYTES // _MB} MB")
                    t = tipo_audio(p)
                    if t is None:
                        raise ValueError("no reconozco el formato de la canción")
                    audios.append((p, t))
                else:
                    return False, f"{nombre}: formato no admitido (.vmd, .vrma o una canción).", None
            except ValueError as e:
                return False, f"{nombre}: {e}", None
            except OSError as e:
                return False, f"{nombre}: no se puede leer ({e.strerror or e}).", None
        if not movs:
            return False, "Falta el movimiento (.vmd o .vrma).", None
        if len(audios) > 1:
            return False, "Elige una sola canción.", None
        base_original = clave_grupo(movs[0].name)[1]
        # Sin cerrojos mientras se copia y ffmpeg convierte (hasta 120 s): la foto se sigue
        # leyendo y buscando. La carpeta de destino se RESERVA creándola (mkdir falla si ya
        # existe: dos importar a la vez no se pisan) y solo se borra la que se creó aquí.
        if not self.asegurar_carpeta():
            return False, self.error or "No puedo usar la carpeta de bailes.", None
        base = self._base()
        if base is None:
            return False, self.error or "No puedo usar la carpeta de bailes.", None
        if len(self.escanear()) >= MAX_BAILES:
            return False, f"Ya tienes {MAX_BAILES} bailes: quita alguno antes.", None
        slug = nombre_seguro(base_original, carpeta=True)
        destino = base / slug
        n = 1
        while True:
            if not motivo_nombre(destino.name):
                try:
                    destino.mkdir()
                    break
                except FileExistsError:
                    pass
                except OSError as e:
                    return False, f"No pude importar: {e.strerror or e}", None
            n += 1
            if n > 200:
                return False, "No encuentro un nombre libre para el baile.", None
            destino = base / nombre_seguro(f"{slug} ({n})", carpeta=True)
        usados: set = set()

        def nombre_libre(nombre: str) -> str:
            n_ = nombre_seguro(nombre, defecto="archivo")
            stem, punto, ext = n_.rpartition(".")
            i = 2
            while n_.lower() in usados or n_.lower() == META:
                n_ = f"{stem} ({i}){punto}{ext}"
                i += 1
            usados.add(n_.lower())
            return n_

        try:
            for p in movs + caras:
                dst = destino / nombre_libre(p.name)
                shutil.copyfile(p, dst)
            for p, t in audios:
                if t in TIPOS_AUDIO_CONV:
                    dst = destino / nombre_libre(p.stem + ".ogg")
                    try:
                        self._convertir(p, dst)
                    except ErrorBailes as e:
                        notas.append(f"no pude convertir la canción ({e}); la copio tal cual")
                        usados.discard(dst.name.lower())
                        shutil.copyfile(p, destino / nombre_libre(p.name))
                else:
                    shutil.copyfile(p, destino / nombre_libre(p.name))
            if slug != base_original:
                escribir_json_atomico(destino / META, {"titulo": texto_limpio(base_original, MAX_TEXTO)})
        except (OSError, shutil.Error) as e:
            shutil.rmtree(destino, ignore_errors=True)
            return False, f"No pude importar: {getattr(e, 'strerror', None) or e}", None
        self.escanear()
        id_ = id_carpeta(destino.name)
        b = self.de_la_foto(id_)
        titulo = b.titulo if b is not None else destino.name
        texto = f"Importado «{texto_limpio(titulo)}»."
        if notas:
            texto += " (" + "; ".join(notas) + ")"
        if b is not None and b.problema:
            texto += f" Ojo: {b.problema}."
        return True, texto, id_

    def quitar(self, id_: str) -> Tuple[bool, str]:
        """Mueve el baile a bailes/.quitados/<nombre>-<fecha>/ (reversible). Sale de la foto
        sin reescanear (va en el hilo de Qt)."""
        with self._lock_carpeta:
            b = self.obtener(id_)
            base = self._base()
            if b is None or base is None:
                return False, "No encuentro ese baile."
            fecha = time.strftime("%Y%m%d-%H%M%S", time.localtime(self._reloj()))
            papelera = base / QUITADOS
            if b.suelto:
                primero = (b.movimiento or b.archivos or (b.carpeta,))[0]
                nombre = nombre_seguro(clave_grupo(primero.name)[1], carpeta=True)
            else:
                nombre = nombre_seguro(b.carpeta.name, carpeta=True)
            destino = papelera / f"{nombre}-{fecha}"
            n = 2
            while destino.exists():
                destino = papelera / f"{nombre}-{fecha}-{n}"
                n += 1
            try:
                papelera.mkdir(exist_ok=True)
                if b.suelto:
                    destino.mkdir()
                    for p in b.archivos:
                        if p.exists() and not es_enlace(p) and p.parent.resolve() == base:
                            shutil.move(str(p), str(destino / p.name))
                else:
                    if es_enlace(b.carpeta) or not b.carpeta.resolve().is_relative_to(base):
                        return False, "Ese baile no está en la carpeta."
                    shutil.move(str(b.carpeta), str(destino))
            except (OSError, shutil.Error) as e:
                return False, f"No pude quitarlo: {getattr(e, 'strerror', None) or e}"
            for extra in (f"{b.id}.ogg", f"{b.id}.pulso.json"):
                try:
                    (self.cache / extra).unlink()
                except OSError:
                    pass
            self._cambiar_foto(b.id, None)
        return True, f"Quitado «{texto_limpio(b.titulo)}» (está en bailes/{QUITADOS})."


def _reemplazar(b: Baile, **cambios: Any) -> Baile:
    from dataclasses import replace
    return replace(b, **cambios)


# ── La biblioteca de siempre (una por proceso) ───────────────────────────────────

_COMPARTIDA: Optional[Biblioteca] = None
_LOCK_COMPARTIDA = threading.Lock()


def biblioteca_compartida(config: Any = None) -> Biblioteca:
    """La de la carpeta de siempre (bailes/), UNA por proceso: la usan el reproductor
    (ui/mmd_qt.ControlMMD), los bailes de patata y listar_bailes sin reproductor, y su foto es
    la que mira `coincide_con_biblioteca`. Con `config`, favoritos y desactivados van a ella."""
    global _COMPARTIDA
    with _LOCK_COMPARTIDA:
        if _COMPARTIDA is None:
            _COMPARTIDA = Biblioteca(config=config)
        elif config is not None:
            _COMPARTIDA.config = config
        return _COMPARTIDA


def coincide_con_biblioteca(texto: Any) -> bool:
    """¿`texto` nombra un baile (que se puede bailar) de tu biblioteca? Todas sus palabras,
    ENTERAS, en el título, los autores o la carpeta de alguno. Para «pon la canción X» sin
    comillas (servicios/tools.py): si no, lo decide el modelo. Solo mira la FOTO de la
    biblioteca compartida (nunca escanea aquí: sin foto, False)."""
    bib = _COMPARTIDA
    if bib is None or not bib.escaneada:
        return False
    palabras = re.findall(r"\w+", normalizar(texto))
    if not palabras:
        return False
    henos = bib._henos
    for b in bib.foto():
        if not b.jugable:
            continue
        enteras = set(re.findall(r"\w+", henos.get(b.id) or _heno(b)))
        if all(p in enteras for p in palabras):
            return True
    return False


# ── Cola ─────────────────────────────────────────────────────────────────────────

class Cola:
    """Qué baile va después (el orden es el de la lista: favoritos y título)."""

    def __init__(self, biblioteca: Biblioteca, *, rng: Optional[random.Random] = None,
                 fuente: Optional[Callable[[], Iterable[Baile]]] = None):
        self.biblioteca = biblioteca
        self._rng = rng or random.Random()
        self._fuente = fuente                  # el reproductor: la foto (nunca escanea)

    def _todos(self) -> List[Baile]:
        return list(self._fuente() if self._fuente is not None else self.biblioteca.bailes())

    @staticmethod
    def _vale(b: Baile, admite: Optional[Callable[[Baile], bool]]) -> bool:
        if not b.jugable:
            return False
        try:
            return admite is None or bool(admite(b))
        except Exception:
            return False

    def siguiente(self, actual: Optional[str], modo: str,
                  admite: Optional[Callable[[Baile], bool]] = None) -> Optional[str]:
        """El que va después de `actual` con `modo` (AL_TERMINAR): parar → None;
        repetir → el mismo; aleatorio → otro al azar (nunca el actual si hay más);
        siguiente → el siguiente de la lista (da la vuelta). Los desactivados y los que
        tienen problema no salen (con `admite`, tampoco los que no admita)."""
        if modo == "parar":
            return None
        todos = self._todos()
        if modo == "repetir":
            for b in todos:
                if b.id == actual and self._vale(b, admite):
                    return actual
        pool = [b.id for b in todos if self._vale(b, admite) and not b.desactivado]
        if not pool:
            return None
        if modo == "aleatorio":
            otros = [i for i in pool if i != actual]
            return self._rng.choice(otros) if otros else pool[0]
        return self._paso(todos, pool, actual, +1)

    def anterior(self, actual: Optional[str], admite: Optional[Callable[[Baile], bool]] = None) -> Optional[str]:
        todos = self._todos()
        pool = [b.id for b in todos if self._vale(b, admite) and not b.desactivado]
        if not pool:
            return None
        return self._paso(todos, pool, actual, -1)

    @staticmethod
    def _paso(todos: List[Baile], pool: List[str], actual: Optional[str], dir_: int) -> Optional[str]:
        ids = [b.id for b in todos]
        if actual not in ids:
            return pool[0] if dir_ > 0 else pool[-1]
        i = ids.index(actual)
        permitidos = set(pool)
        for k in range(1, len(ids) + 1):
            c = ids[(i + dir_ * k) % len(ids)]
            if c in permitidos:
                return c
        return None


# ── Herramienta del modelo ───────────────────────────────────────────────────────

MAX_LISTA_MODELO = 10


def _lista_de_ctx(ctx: Any, texto: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    mmd = _nb._de_ctx(ctx, "mmd")
    if mmd is not None and callable(getattr(mmd, "lista", None)):
        return list(mmd.lista(texto) or []), ""
    bib = _nb._de_ctx(ctx, "biblioteca")
    if bib is None:
        bib = biblioteca_compartida()            # antes, una Biblioteca nueva (en frío) por llamada
    if isinstance(bib, Biblioteca):
        lista = bib.filtrar(bib.escanear(), texto)   # el modelo pregunta: lo que hay AHORA
    elif callable(getattr(bib, "buscar", None)):
        lista = bib.buscar(texto) if texto else bib.escanear()
    else:
        return None, "Aquí no tengo biblioteca de bailes."
    return [baile_a_dict(b) for b in lista], ""


def herramienta_listar(args: Any = None, ctx: Any = None) -> Any:
    """Handler de `listar_bailes` ({texto?}): ≤10 títulos saneados (son nombres de
    archivo: nada de marcadores). ctx["mmd"] (ControlMMD) o ctx["biblioteca"]."""
    args = args if isinstance(args, dict) else {}
    texto = texto_limpio(args.get("texto"), 60)
    try:
        items, error = _lista_de_ctx(ctx, texto)
    except Exception as e:                                       # noqa: BLE001
        return False, f"No pude mirar tus bailes: {e}"[:300]
    if items is None:
        return False, error
    if not items:
        if texto:
            return f"No encontré «{titulo_seguro(texto, 60)}» en tus bailes."
        return ("Aún no tienes bailes. Mételos en la carpeta «bailes» de Lune (un .vmd o .vrma con su "
                "canción) o impórtalos desde «Mis bailes».")
    buenos = [i for i in items if not i.get("problema")]
    rotos = len(items) - len(buenos)
    partes = []
    for i in (buenos or items)[:MAX_LISTA_MODELO]:
        s = f"«{titulo_seguro(i.get('titulo'))}»"
        autor = titulo_seguro(i.get("autor_cancion"), 60)
        if autor:
            s += f" ({autor})"
        if i.get("favorito"):
            s += " ★"
        if i.get("problema"):
            s += " [no se puede bailar]"
        partes.append(s)
    total = len(buenos) if buenos else len(items)
    cab = "Tus bailes" + (f" con «{titulo_seguro(texto, 60)}»" if texto else "") + f" ({total}): "
    out = cab + "; ".join(partes)
    if total > MAX_LISTA_MODELO:
        out += f"; y {total - MAX_LISTA_MODELO} más"
    out += "."
    if rotos and buenos:
        out += f" Hay {rotos} que no se pueden bailar."
    return out


__all__ = (
    "CARPETA", "CACHE", "PREFIJO_WEB", "PREFIJO_CACHE", "EXT_MOV", "EXT_AUDIO_WEB", "EXT_AUDIO_CONV",
    "AL_TERMINAR", "AL_TERMINAR_DEFECTO", "Baile", "Biblioteca", "Cola", "ErrorBailes", "info_vmd",
    "info_vmd_bytes", "info_vrma", "info_vrma_bytes", "tipo_audio", "normalizar", "texto_limpio",
    "titulo_seguro", "id_valido", "id_carpeta", "id_suelto", "motivo_nombre", "nombre_seguro", "es_unc",
    "es_enlace", "clave_grupo", "fase_en", "validar_meta", "leer_meta", "analizar_pcm", "envolvente_pico",
    "baile_a_dict", "herramienta_listar", "META_DEFECTO", "biblioteca_compartida", "coincide_con_biblioteca",
    "ejecutar_proceso", "matar_procesos",
)
