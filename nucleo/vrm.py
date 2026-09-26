"""
nucleo/vrm.py — Modelos 3D (VRM) de la mascota y su relación con los personajes.

Los .vrm viven en `modelo_vrm/` (gitignored: son pesados y de terceros). Cada
personaje de datos.json puede llevar `"vrm": "<archivo>"` (nombre dentro de
modelo_vrm/ o ruta absoluta de una unidad local); si no lo tiene, se usa el de
config (`avatar.vrm_archivo`) y, si tampoco, el primer .vrm de la carpeta. Una
ruta de red (\\\\servidor\\…, //servidor/…, una letra mapeada a la red) se rechaza
sin tocarla: mirarla mandaría el hash NTLM de Windows a ese equipo (revisión S2).
Los ajustes por modelo (<modelo>.lune.json) viven siempre en modelo_vrm/.

Biblioteca (v10.x, «Custom VRM» de Mate-Engine):
  miniatura(ruta)            → bytes PNG/JPEG de la miniatura que trae el propio
                               modelo (VRM 1.0: meta.thumbnailImage; VRM 0.x:
                               meta.texture → textures[i].source), o None.
  miniatura_data_url(nombre) → "data:image/png;base64,…" ("" si no hay).
  meta(ruta)                 → versión, nombre, autor, licencia, triángulos,
                               tieneLookAt (¿mueve los ojos?), expresiones…
  ficha(nombre, config)      → meta + ajustes + parámetros efectivos + personajes
                               que lo usan (lo que enseña la rejilla).
  biblioteca(config)         → la rejilla entera en una llamada (fichas + personaje
                               activo y su modelo); *_json: envoltorios del puente.
  borrar_modelo(nombre)      → borra SOLO dentro de modelo_vrm/ (y su .lune.json)
                               y quita el modelo de los personajes y de config.
  ajustes_modelo(nombre) / guardar_ajustes_modelo(nombre, dict)
                             → calibración por modelo en modelo_vrm/<modelo>.lune.json
                               (claves de AJUSTES, validadas y con rango).
  params_modelo(nombre, config)
                             → lo que se manda a window.luneParams de la mascota:
                               calibración del modelo + pesos de seguimiento de
                               config (avatar.peso_cabeza/torso/ojos, seguir_cursor).
  herramienta_tamano(args, ctx) → handler de la herramienta `mascota_tamano`.

Los rangos de AJUSTES son los mismos que ui_web/vrm/lune_params.js (lo comprueba
tests/test_vrm_ajustes.py con Node).

Sin Qt: se puede probar sin pantalla.
"""
from __future__ import annotations

import base64
import functools
import json
import math
import os
import shutil
import struct
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from nucleo import datos, personajes

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "modelo_vrm"

# Un .vrm es un glTF binario (GLB). Mate-Engine acepta cualquier cosa que su
# parser trague; aquí se comprueba la cabecera ANTES de servirlo al WebEngine
# (un archivo roto o enorme puede tumbar el proceso del renderer sin aviso).
MB = 1024 * 1024
AVISO_MB = 60          # a partir de aquí se avisa (tarda y come RAM)
MAXIMO_MB = 250        # a partir de aquí se rechaza


def validar(ruta) -> Tuple[bool, str, Dict]:
    """
    ¿Es un VRM utilizable? Devuelve (ok, motivo, meta). meta trae version ("0"/"1"),
    nombre, autor y mb; motivo explica por qué no vale (o un aviso si es pesado).
    No carga el modelo: solo lee la cabecera GLB y el chunk JSON.
    """
    meta: Dict = {}
    try:
        p = Path(ruta)
        tam = p.stat().st_size
    except OSError:
        return False, "El archivo no existe.", meta
    meta["mb"] = round(tam / MB, 1)
    if tam == 0:
        return False, "El archivo está vacío.", meta
    if tam > MAXIMO_MB * MB:
        return False, f"Pesa {meta['mb']} MB: demasiado para el visor (máx. {MAXIMO_MB} MB).", meta
    try:
        with open(p, "rb") as f:
            cab = f.read(12)
            if len(cab) < 12 or cab[:4] != b"glTF":
                return False, "No es un glTF binario (.vrm/.glb).", meta
            version, longitud = struct.unpack("<II", cab[4:12])
            if version != 2:
                return False, f"glTF versión {version}; se espera la 2.", meta
            if longitud != tam:
                return False, "Cabecera GLB incoherente con el tamaño del archivo (¿descarga incompleta?).", meta
            chunk_len, chunk_tipo = struct.unpack("<II", f.read(8))
            if chunk_tipo != 0x4E4F534A:            # 'JSON'
                return False, "El primer chunk del GLB no es JSON.", meta
            doc = json.loads(f.read(chunk_len).decode("utf-8", "replace"))
    except (OSError, ValueError, struct.error) as e:
        return False, f"No pude leer el archivo: {e}", meta
    if not isinstance(doc, dict):
        return False, "El chunk JSON del GLB no es un objeto.", meta

    def _d(x):                                  # cualquier cosa que no sea dict → {}
        return x if isinstance(x, dict) else {}

    ext = _d(doc.get("extensions"))
    usadas_lista = doc.get("extensionsUsed")
    usadas = set(usadas_lista if isinstance(usadas_lista, list) else []) | set(ext.keys())
    if "VRMC_vrm" in usadas:
        m = _d(_d(ext.get("VRMC_vrm")).get("meta"))
        autores = m.get("authors")
        autor = autores[0] if isinstance(autores, list) and autores else ""
        meta.update(version="1", nombre=str(m.get("name") or ""), autor=str(autor or ""))
    elif "VRM" in usadas:
        m = _d(_d(ext.get("VRM")).get("meta"))
        meta.update(version="0", nombre=str(m.get("title") or ""), autor=str(m.get("author") or ""))
    else:
        return False, "Es un glTF pero no trae la extensión VRM.", meta
    motivo = f"Pesa {meta['mb']} MB: tardará en cargar." if tam > AVISO_MB * MB else ""
    return True, motivo, meta


def listar_modelos() -> List[str]:
    """Nombres de archivo de los .vrm válidos en modelo_vrm/ (ordenados)."""
    if not CARPETA.exists():
        return []
    return sorted(p.name for p in CARPETA.glob("*.vrm") if p.is_file() and validar(p)[0])


def es_ruta_de_red(ruta) -> bool:
    """¿Ruta UNC o de dispositivo (\\\\servidor\\recurso, //servidor/…, \\\\?\\…)? Hacer
    is_file()/stat sobre ella conecta con ese equipo (y Windows le manda las
    credenciales NTLM): nunca se toca."""
    s = str(ruta or "").strip()
    return len(s) >= 2 and s[0] in "\\/" and s[1] in "\\/"


# GetDriveTypeW: 2 extraíble, 3 fijo, 5 CD, 6 RAM. 4 = unidad de red (Z: → \\servidor).
_UNIDADES_LOCALES = (2, 3, 5, 6)


def ruta_local(ruta) -> bool:
    """¿Ruta absoluta de una unidad LOCAL del equipo? No: rutas de red (UNC), una
    letra mapeada a un recurso de red o una unidad que no existe. Se pregunta al
    sistema por la letra sin tocar el archivo."""
    s = str(ruta or "").strip()
    if not s or es_ruta_de_red(s):
        return False
    p = Path(s)
    if not p.is_absolute():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        tipo = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(p.drive + "\\"))
    except Exception:
        return False
    return tipo in _UNIDADES_LOCALES


def resolver(nombre_o_ruta: str) -> Optional[Path]:
    """
    Un nombre dentro de modelo_vrm/ o una ruta absoluta de una unidad local →
    Path existente, o None. Revisión de seguridad S2: una ruta de red
    (\\\\servidor\\…, //servidor/…, \\\\?\\UNC\\…, una letra mapeada a la red) se
    rechaza SIN tocarla: is_file()/stat conectaría con ese equipo y Windows le
    mandaría el hash NTLM del usuario. De ella tampoco se usa el nombre.
    """
    n = str(nombre_o_ruta or "").strip()
    if not n or es_ruta_de_red(n):
        return None
    p = Path(n)
    if p.is_absolute():
        if not ruta_local(n):
            return None
        if p.is_file():
            return p if validar(p)[0] else None
    candidato = CARPETA / p.name
    if candidato.name in ("", ".", ".."):
        return None
    if candidato.is_file():
        return candidato if validar(candidato)[0] else None
    return None


def ruta_modelo(config=None, personaje: Optional[dict] = None) -> Optional[Path]:
    """
    El .vrm que toca mostrar, por prioridad:
      1. el del personaje (activo si no se pasa otro): personaje["vrm"]
      2. config avatar.vrm_archivo
      3. el primer .vrm de modelo_vrm/
    """
    if personaje is None:
        try:
            personaje = personajes.get_activo() or {}
        except Exception:
            personaje = {}
    p = resolver(personaje.get("vrm", "")) if personaje else None
    if p is not None:
        return p
    if config is not None:
        try:
            p = resolver(config.get("avatar", "vrm_archivo", "") or "")
        except Exception:
            p = None
        if p is not None:
            return p
    modelos = listar_modelos()
    return CARPETA / modelos[0] if modelos else None


def webengine_disponible() -> bool:
    """¿Se puede renderizar el VRM? (PyQt6-WebEngine instalado)."""
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:
        return False


def disponible(config=None) -> bool:
    """Hay visor (WebEngine) y hay un modelo que mostrar."""
    return webengine_disponible() and ruta_modelo(config) is not None


def importar_modelo(ruta: str) -> str:
    """
    Copia un .vrm a modelo_vrm/ y devuelve el nombre de archivo resultante.
    Si ya está dentro de la carpeta, no copia nada. Lanza ValueError si no vale.
    """
    if es_ruta_de_red(ruta):
        # Ni se mira (is_file conectaría con ese equipo): cópialo antes a este PC.
        raise ValueError("No importo modelos desde rutas de red: cópialo antes a tu PC.")
    origen = Path(str(ruta or "").strip())
    if not origen.is_file():
        raise ValueError("El archivo no existe.")
    if origen.suffix.lower() != ".vrm":
        raise ValueError("Solo se admiten archivos .vrm.")
    ok, motivo, _ = validar(origen)
    if not ok:
        raise ValueError(motivo)
    CARPETA.mkdir(parents=True, exist_ok=True)
    destino = CARPETA / origen.name
    try:
        if destino.resolve() == origen.resolve():
            return destino.name
    except OSError:
        pass
    shutil.copy2(origen, destino)
    return destino.name


def asignar_a_personaje(nombre: str, archivo: str) -> dict:
    """
    Guarda `vrm` en el personaje `nombre` (vacío = sin modelo propio).
    Devuelve el personaje actualizado. Lanza ValueError si el personaje no existe
    o el archivo no se encuentra.
    """
    p = personajes.get(nombre)
    if not p or p.get("nombre", "").lower() != (nombre or "").lower():
        raise ValueError(f"No existe el personaje «{nombre}».")
    archivo = str(archivo or "").strip()
    if archivo and resolver(archivo) is None:
        raise ValueError(f"No encuentro el modelo «{archivo}».")
    # Dentro de modelo_vrm/ se guarda solo el nombre (portable entre equipos).
    ruta = resolver(archivo) if archivo else None
    if ruta is not None and ruta.parent == CARPETA:
        archivo = ruta.name
    nuevo = dict(p)
    if archivo:
        nuevo["vrm"] = archivo
    else:
        nuevo.pop("vrm", None)
    personajes.guardar_personaje(nuevo)
    datos.invalidar()
    return nuevo


# ═════════════════════════════════════════════════════════════════════════════
#  Biblioteca: leer el GLB sin cargar el modelo
# ═════════════════════════════════════════════════════════════════════════════

_CHUNK_JSON = 0x4E4F534A          # 'JSON'
_CHUNK_BIN = 0x004E4942           # 'BIN\0'
MAX_MINIATURA = 8 * MB            # una «miniatura» más grande que esto no se sirve
_MAX_DATA_URI = 12 * MB           # imagen embebida como uri "data:" en el JSON (raro)
_MAX_AJUSTES = 64 * 1024          # un .lune.json no necesita más


def _d(x) -> dict:
    return x if isinstance(x, dict) else {}


def _l(x) -> list:
    return x if isinstance(x, list) else []


def _indice(x) -> Optional[int]:
    """Índice glTF válido (int ≥ 0 y no bool) o None."""
    if isinstance(x, bool) or not isinstance(x, int) or x < 0:
        return None
    return x


def _texto(x, maximo: int = 200) -> str:
    """Texto del modelo apto para la interfaz: sin control, bidi ni ancho cero, recortado."""
    if x is None or isinstance(x, (dict, list, bool)):
        return ""
    s = "".join(" " if c in "\r\n\t" else c for c in str(x)
                if c in "\r\n\t" or unicodedata.category(c) not in ("Cc", "Cf"))
    s = " ".join(s.split())
    return s if len(s) <= maximo else s[:maximo - 1] + "…"


def _leer_glb(ruta) -> Optional[Tuple[dict, int, int]]:
    """
    (doc, inicio_bin, largo_bin) de un GLB leyendo solo la cabecera, el chunk
    JSON y la cabecera del chunk BIN (las mallas no se cargan). largo_bin = 0 si
    no hay BIN. None si no es un glTF binario 2.0 legible o pesa demasiado.
    """
    try:
        p = Path(ruta)
        tam = p.stat().st_size
        if tam < 20 or tam > MAXIMO_MB * MB:
            return None
        with open(p, "rb") as f:
            cab = f.read(12)
            if len(cab) < 12 or cab[:4] != b"glTF" or struct.unpack("<I", cab[4:8])[0] != 2:
                return None
            chunk_len, chunk_tipo = struct.unpack("<II", f.read(8))
            if chunk_tipo != _CHUNK_JSON or chunk_len > tam - 20:
                return None
            doc = json.loads(f.read(chunk_len).decode("utf-8", "replace"))
            if not isinstance(doc, dict):
                return None
            inicio, largo = 0, 0
            pos = 20 + chunk_len
            if pos + 8 <= tam:
                f.seek(pos)
                bin_len, bin_tipo = struct.unpack("<II", f.read(8))
                if bin_tipo == _CHUNK_BIN and pos + 8 + bin_len <= tam:
                    inicio, largo = pos + 8, bin_len
            return doc, inicio, largo
    except (OSError, ValueError, struct.error, RecursionError):
        return None


def _vrm_de(doc: dict) -> Tuple[str, dict]:
    """("1", VRMC_vrm) · ("0", VRM) · ("", {}); misma prioridad que validar()."""
    ext = _d(doc.get("extensions"))
    usadas = {x for x in _l(doc.get("extensionsUsed")) if isinstance(x, str)} | set(ext.keys())
    if "VRMC_vrm" in usadas:
        return "1", _d(ext.get("VRMC_vrm"))
    if "VRM" in usadas:
        return "0", _d(ext.get("VRM"))
    return "", {}


# ── Miniatura ─────────────────────────────────────────────────────────────────

def _indice_miniatura(doc: dict) -> Optional[int]:
    """Índice en `images` de la miniatura que declara el modelo, o None."""
    version, e = _vrm_de(doc)
    m = _d(e.get("meta"))
    if version == "1":                                   # VRMC_vrm.meta.thumbnailImage → images[i]
        return _indice(m.get("thumbnailImage"))
    if version == "0":                                   # VRM.meta.texture → textures[i].source
        t = _indice(m.get("texture"))                    # UniVRM pone -1 si no hay
        texturas = _l(doc.get("textures"))
        if t is None or t >= len(texturas):
            return None
        return _indice(_d(texturas[t]).get("source"))
    return None


def _tipo_imagen(b: Optional[bytes]) -> str:
    """Tipo MIME por la firma de los bytes (no por lo que diga el JSON)."""
    if not b:
        return ""
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return ""


def _bytes_imagen(doc: dict, indice: int, f, inicio_bin: int, largo_bin: int,
                  cabecera: bool = False) -> Optional[bytes]:
    """Bytes de images[indice]: del chunk BIN (bufferView) o de una uri data:. Nunca de
    archivos externos. cabecera=True lee solo los primeros bytes (para la firma)."""
    imagenes = _l(doc.get("images"))
    if indice >= len(imagenes):
        return None
    img = _d(imagenes[indice])
    bv = _indice(img.get("bufferView"))
    if bv is not None:
        vistas = _l(doc.get("bufferViews"))
        if bv >= len(vistas) or not largo_bin:
            return None
        vista = _d(vistas[bv])
        if _indice(vista.get("buffer", 0)) != 0:         # solo el buffer del propio GLB
            return None
        buffers = _l(doc.get("buffers"))
        if buffers and "uri" in _d(buffers[0]):          # buffer 0 externo: no es el chunk BIN
            return None
        ini = _indice(vista.get("byteOffset", 0))
        largo = _indice(vista.get("byteLength"))
        if ini is None or not largo or largo > MAX_MINIATURA or ini + largo > largo_bin:
            return None
        f.seek(inicio_bin + ini)
        n = min(largo, 16) if cabecera else largo
        b = f.read(n)
        return b if len(b) == n else None
    uri = img.get("uri")
    if isinstance(uri, str) and uri.startswith("data:") and len(uri) <= _MAX_DATA_URI:
        tipo, _, cuerpo = uri.partition(",")
        if ";base64" not in tipo:
            return None
        try:
            b = base64.b64decode(cuerpo[:24] if cabecera else cuerpo)
        except ValueError:
            return None
        return b if len(b) <= MAX_MINIATURA else None
    return None                                          # uri a otro archivo: no se sigue


def miniatura(ruta) -> Optional[bytes]:
    """
    Bytes PNG/JPEG de la miniatura que trae el propio .vrm, o None si no trae
    (o está rota, o no es PNG/JPEG). Lee solo el JSON y la imagen, no el modelo.
      VRM 1.0: VRMC_vrm.meta.thumbnailImage → images[i].bufferView → chunk BIN
      VRM 0.x: VRM.meta.texture → textures[i].source → images[j] → bufferView
    """
    g = _leer_glb(ruta)
    return _miniatura_de(ruta, g) if g is not None else None


def _miniatura_de(ruta, g: Tuple[dict, int, int], cabecera: bool = False) -> Optional[bytes]:
    doc, inicio, largo = g
    i = _indice_miniatura(doc)
    if i is None:
        return None
    try:
        with open(Path(ruta), "rb") as f:
            b = _bytes_imagen(doc, i, f, inicio, largo, cabecera)
    except (OSError, ValueError):
        return None
    return b if _tipo_imagen(b) else None


@functools.lru_cache(maxsize=64)
def _miniatura_url(ruta: str, _mtime_ns: int, _tam: int) -> str:
    b = miniatura(ruta)
    if not b:
        return ""
    return f"data:{_tipo_imagen(b)};base64,{base64.b64encode(b).decode('ascii')}"


def miniatura_data_url(nombre: str) -> str:
    """
    La miniatura de un modelo de modelo_vrm/ como data URL (para <img src> o
    QPixmap); "" si no trae o si `nombre` no es un .vrm de la carpeta. Se cachea
    por (ruta, mtime, tamaño): la rejilla la pide una vez por modelo.
    """
    p = _en_carpeta(nombre)
    if p is None:
        return ""
    try:
        st = p.stat()
    except OSError:
        return ""
    return _miniatura_url(str(p), st.st_mtime_ns, st.st_size)


# ── Metadatos ─────────────────────────────────────────────────────────────────

_LICENCIAS_0 = {
    "Redistribution_Prohibited": "Redistribución prohibida",
    "CC0": "CC0 (dominio público)", "CC_BY": "CC BY", "CC_BY_NC": "CC BY-NC", "CC_BY_SA": "CC BY-SA",
    "CC_BY_NC_SA": "CC BY-NC-SA", "CC_BY_ND": "CC BY-ND", "CC_BY_NC_ND": "CC BY-NC-ND", "Other": "Otra",
}
_USO_COMERCIAL_1 = {
    "personalNonProfit": "uso personal sin ánimo de lucro",
    "personalProfit": "uso personal, también con ánimo de lucro",
    "corporation": "uso comercial permitido",
}
_MIRADAS = ("lookLeft", "lookRight", "lookUp", "lookDown")


def _licencia(version: str, m: dict) -> Tuple[str, str]:
    """(texto corto, url) de la licencia que declara el modelo; ("", "") si no dice nada."""
    partes: List[str] = []
    if version == "1":
        url = _texto(m.get("licenseUrl"), 300)
        if url:
            partes.append("VRM Public License 1.0" if "vrm.dev/licenses/1.0" in url else "Licencia propia")
        uso = _USO_COMERCIAL_1.get(str(m.get("commercialUsage") or ""))
        if uso:
            partes.append(uso)
        if m.get("allowRedistribution") is False:
            partes.append("sin redistribución")
        return " · ".join(partes), url or _texto(m.get("otherLicenseUrl"), 300)
    if version == "0":
        nombre = str(m.get("licenseName") or "")
        base = _LICENCIAS_0.get(nombre) or _texto(nombre, 60)
        if base:
            partes.append(base)
        comercial = str(m.get("commercialUssageName") or m.get("commercialUsageName") or "")
        if comercial == "Disallow":
            partes.append("sin uso comercial")
        elif comercial == "Allow":
            partes.append("uso comercial permitido")
        return " · ".join(partes), _texto(m.get("otherLicenseUrl"), 300)
    return "", ""


def _triangulos(doc: dict) -> int:
    """Triángulos aproximados sumando los accessors de las primitivas (sin leer mallas)."""
    accessors = _l(doc.get("accessors"))
    total = 0
    for malla in _l(doc.get("meshes")):
        for prim in _l(_d(malla).get("primitives")):
            prim = _d(prim)
            modo = prim.get("mode", 4)
            if isinstance(modo, bool) or modo not in (4, 5, 6):   # triángulos, tira, abanico
                continue
            i = _indice(prim.get("indices"))
            if i is None:
                i = _indice(_d(prim.get("attributes")).get("POSITION"))
            if i is None or i >= len(accessors):
                continue
            n = _indice(_d(accessors[i]).get("count")) or 0
            total += n // 3 if modo == 4 else max(0, n - 2)
    return total


def _look_at(version: str, e: dict) -> Tuple[bool, str]:
    """(¿mueve los ojos?, 'hueso'|'expresion'|'') como lo decide three-vrm al cargar."""
    if version == "1":
        la = e.get("lookAt")
        if not isinstance(la, dict):
            return False, ""
        if la.get("type") == "expression":
            preset = _d(_d(e.get("expressions")).get("preset"))
            return any(isinstance(preset.get(k), dict) for k in _MIRADAS), "expresion"
        huesos = _d(_d(e.get("humanoid")).get("humanBones"))
        return any(_indice(_d(huesos.get(k)).get("node")) is not None for k in ("leftEye", "rightEye")), "hueso"
    if version == "0":
        fp = e.get("firstPerson")
        if not isinstance(fp, dict):                     # three-vrm no crea lookAt sin firstPerson
            return False, ""
        if fp.get("lookAtTypeName") == "BlendShape":
            grupos = _l(_d(e.get("blendShapeMaster")).get("blendShapeGroups"))
            nombres = {str(_d(g).get("presetName") or "").lower() for g in grupos}
            return any(k.lower() in nombres for k in _MIRADAS), "expresion"
        huesos = {str(_d(h).get("bone") or "") for h in _l(_d(e.get("humanoid")).get("humanBones"))
                  if _indice(_d(h).get("node")) is not None}
        return bool(huesos & {"leftEye", "rightEye"}), "hueso"
    return False, ""


def _expresiones(version: str, e: dict) -> List[str]:
    if version == "1":
        ex = _d(e.get("expressions"))
        crudos = list(_d(ex.get("preset")).keys()) + list(_d(ex.get("custom")).keys())
    elif version == "0":
        crudos = []
        for g in _l(_d(e.get("blendShapeMaster")).get("blendShapeGroups")):
            g = _d(g)
            p = str(g.get("presetName") or "")
            crudos.append(p if p and p != "unknown" else g.get("name"))
    else:
        crudos = []
    out: List[str] = []
    for c in crudos:
        t = _texto(c, 40)
        if t and t not in out:
            out.append(t)
    return out[:64]


def meta(ruta) -> Dict[str, Any]:
    """
    Ficha técnica de un .vrm sin cargarlo:
      {ok, motivo, archivo, version "0"|"1", nombre, autor, mb, licencia, licencia_url,
       triangulos (aprox.), tieneLookAt, lookAt 'hueso'|'expresion'|'', miniatura (bool),
       expresiones [..]}
    Con ok=False solo vienen los campos que se pudieron leer (y `motivo`).
    Los textos vienen limpios (sin control ni bidi) y recortados.
    """
    ok, motivo, base = validar(ruta)
    info: Dict[str, Any] = {
        "ok": ok, "motivo": motivo, "archivo": Path(str(ruta or "")).name,
        "version": str(base.get("version", "")), "nombre": _texto(base.get("nombre"), 120),
        "autor": _texto(base.get("autor"), 120), "mb": base.get("mb", 0.0),
        "licencia": "", "licencia_url": "", "triangulos": 0, "tieneLookAt": False, "lookAt": "",
        "miniatura": False, "expresiones": [],
    }
    if not ok:
        return info
    g = _leer_glb(ruta)
    if g is None:
        return info
    doc = g[0]
    version, e = _vrm_de(doc)
    info["licencia"], info["licencia_url"] = _licencia(version, _d(e.get("meta")))
    info["triangulos"] = _triangulos(doc)
    info["tieneLookAt"], info["lookAt"] = _look_at(version, e)
    info["miniatura"] = _miniatura_de(ruta, g, cabecera=True) is not None   # solo la firma
    info["expresiones"] = _expresiones(version, e)
    return info


# ── Nombres dentro de modelo_vrm/ ─────────────────────────────────────────────

_PROHIBIDOS = set('\\/:*?"<>|')
# Nombres de dispositivo de Windows: «CON.vrm» o «nul.vrm» no son archivos.
_RESERVADOS_WIN = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}


def _nombre_seguro(nombre) -> str:
    """
    Un nombre de archivo .vrm SIN carpetas: lo único que se acepta para tocar
    modelo_vrm/ (borrar, ajustes). ValueError si trae rutas, unidades, «..»,
    caracteres de control, un nombre de dispositivo de Windows o no es .vrm.
    """
    n = str(nombre or "").strip()
    if not n:
        raise ValueError("Falta el nombre del modelo.")
    if (n in (".", "..") or len(n) > 200 or n != Path(n).name
            or any(c in _PROHIBIDOS or ord(c) < 32 for c in n)
            or n.split(".")[0].strip().upper() in _RESERVADOS_WIN):
        raise ValueError(f"«{_texto(n, 80)}» no es un nombre de modelo válido "
                         "(solo el nombre del archivo, sin carpetas).")
    if not n.lower().endswith(".vrm") or len(n) <= 4:
        raise ValueError("Solo se admiten archivos .vrm.")
    return n


def _archivo_de(nombre_o_ruta) -> str:
    """Nombre de archivo de un modelo: el nombre tal cual o el de una ruta (los
    ajustes viven siempre en modelo_vrm/; la ruta de fuera no se toca).
    ValueError con rutas de red (S2), sin mirarlas."""
    n = str(nombre_o_ruta or "").strip()
    if es_ruta_de_red(n):
        raise ValueError("No se aceptan rutas de red para los modelos.")
    if n and Path(n).is_absolute():
        n = Path(n).name
    return _nombre_seguro(n)


def _en_carpeta(nombre) -> Optional[Path]:
    """modelo_vrm/<nombre> si `nombre` es un nombre seguro y el archivo existe."""
    try:
        p = CARPETA / _nombre_seguro(nombre)
    except ValueError:
        return None
    return p if p.is_file() else None


def _misma_carpeta(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return False


def _apunta_a(valor, archivo: str) -> bool:
    """¿El `vrm` de un personaje (o avatar.vrm_archivo) es modelo_vrm/<archivo>?"""
    v = str(valor or "").strip()
    if not v or es_ruta_de_red(v):
        return False                                     # una ruta de red no se resuelve (S2)
    p = Path(v)
    if p.name.lower() != archivo.lower():
        return False
    if not p.is_absolute():
        return True                                      # resolver() busca por nombre en modelo_vrm/
    return _misma_carpeta(p.parent, CARPETA)


def _cfg(config, clave: str, defecto=None):
    if config is None:
        return defecto
    try:
        return config.get("avatar", clave, defecto)
    except Exception:
        return defecto


def personajes_con(archivo: str) -> List[str]:
    """Nombres de los personajes que usan modelo_vrm/<archivo>."""
    try:
        lista = personajes.listar()
    except Exception:
        return []
    return [str(p.get("nombre") or "") for p in lista
            if isinstance(p, dict) and _apunta_a(p.get("vrm"), archivo)]


# ── Borrar ────────────────────────────────────────────────────────────────────

def _quitar_de_personajes(archivo: str) -> List[str]:
    try:
        data = personajes._load()
    except Exception:
        return []
    quitados: List[str] = []
    for p in _l(data.get("personajes")):
        if isinstance(p, dict) and _apunta_a(p.get("vrm"), archivo):
            p.pop("vrm", None)
            quitados.append(str(p.get("nombre") or ""))
    if quitados:
        personajes._save(data)
        try:
            datos.invalidar()
        except Exception:
            pass
    return quitados


def borrar_modelo(nombre: str, config=None) -> Dict[str, Any]:
    """
    Borra modelo_vrm/<nombre> (y su <modelo>.lune.json). SOLO dentro de la
    carpeta: `nombre` tiene que ser un nombre de archivo .vrm sin rutas. Quita
    el modelo de los personajes que lo tenían y, si se pasa `config`, de
    avatar.vrm_archivo. Devuelve {ok, archivo, personajes: [quitados],
    por_defecto: bool, modelos: [los que quedan]}. ValueError si no se puede.
    """
    archivo = _nombre_seguro(nombre)
    ruta = CARPETA / archivo
    if not (ruta.is_file() or ruta.is_symlink()):
        raise ValueError(f"No encuentro «{archivo}» en modelo_vrm/.")
    if not _misma_carpeta(ruta.parent, CARPETA):         # paranoia: CARPETA / nombre siempre lo cumple
        raise ValueError("Solo se borran modelos de la carpeta modelo_vrm/.")
    try:
        ruta.unlink()                                    # un enlace simbólico se borra él, no su destino
    except PermissionError:
        raise ValueError(f"No pude borrar «{archivo}»: está en uso. Cierra la mascota 3D e inténtalo otra vez.")
    except OSError as e:
        raise ValueError(f"No pude borrar «{archivo}»: {e}")
    try:
        (CARPETA / (archivo[:-4] + ".lune.json")).unlink()
    except OSError:
        pass
    _miniatura_url.cache_clear()
    quitados = _quitar_de_personajes(archivo)
    por_defecto = False
    if config is not None and _apunta_a(_cfg(config, "vrm_archivo", ""), archivo):
        try:
            config.set("avatar", "vrm_archivo", "")
            por_defecto = True
        except Exception:
            pass
    return {"ok": True, "archivo": archivo, "personajes": quitados, "por_defecto": por_defecto,
            "modelos": listar_modelos()}


# ═════════════════════════════════════════════════════════════════════════════
#  Calibración por modelo: modelo_vrm/<modelo>.lune.json
# ═════════════════════════════════════════════════════════════════════════════
# Mismos rangos que ui_web/vrm/lune_params.js (RANGOS). tipo:
#   "signo"  → 1 (tal cual) o -1 (invertir); true = -1, false = 1, un número = su signo
#   "opcion" → uno de `valores` (invertirEjes: 0 = automático, 1 = tal cual, -1 = invertir X/Z)
#   "real"   → número recortado a [min, max]
AJUSTES: Dict[str, Dict[str, Any]] = {
    "invertirEjes":    {"tipo": "opcion", "valores": (-1, 0, 1), "defecto": 0},
    "invertirH":       {"tipo": "signo", "defecto": 1},                         # balanceo horizontal al arrastrar
    "invertirV":       {"tipo": "signo", "defecto": 1},                         # balanceo vertical
    "invertirBrazos":  {"tipo": "signo", "defecto": 1},                         # brazos con retraso (módulo movimiento)
    "invertirPiernas": {"tipo": "signo", "defecto": 1},                         # piernas con retraso
    "luz":             {"tipo": "real", "min": 0.2, "max": 3.0, "defecto": 1.0},   # × intensidad de las luces
    "altura":          {"tipo": "real", "min": -0.5, "max": 0.5, "defecto": 0.0},  # m: sube/baja el modelo
    "pesoCabeza":      {"tipo": "real", "min": 0.0, "max": 1.0, "defecto": 1.0},   # seguimiento del cursor
    "pesoTorso":       {"tipo": "real", "min": 0.0, "max": 1.0, "defecto": 1.0},
    "pesoOjos":        {"tipo": "real", "min": 0.0, "max": 1.0, "defecto": 1.0},
}
# Pesos de seguimiento que también tienen valor global en config (avatar.*).
PESOS_CONFIG = {"pesoCabeza": "peso_cabeza", "pesoTorso": "peso_torso", "pesoOjos": "peso_ojos"}


def _numero(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        try:
            x = float(v.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return x if math.isfinite(x) else None


def validar_valor(clave: str, valor) -> Optional[float]:
    """El valor de un ajuste dentro de su rango, o None si la clave no existe o el valor no vale."""
    r = AJUSTES.get(clave)
    if r is None:
        return None
    tipo = r["tipo"]
    if tipo == "signo":
        if isinstance(valor, bool):
            return -1 if valor else 1
        x = _numero(valor)
        return None if x is None else (-1 if x < 0 else 1)
    if tipo == "opcion":
        if isinstance(valor, str) and valor.strip().lower() in ("auto", "automatico", "automático"):
            return 0
        x = _numero(valor)
        if x is None:
            return None
        # floor(x + 0.5) = Math.round de JS (round() de Python redondea al par)
        return max(min(int(math.floor(x + 0.5)), max(r["valores"])), min(r["valores"]))
    x = _numero(valor)
    if x is None:
        return None
    return round(min(r["max"], max(r["min"], x)), 4)


def validar_ajustes(d) -> Dict[str, Any]:
    """Solo las claves de AJUSTES con valor válido (recortado a su rango), en orden estable."""
    if not isinstance(d, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for clave in AJUSTES:
        if clave in d:
            v = validar_valor(clave, d[clave])
            if v is not None:
                out[clave] = v
    return out


def ruta_ajustes(nombre_o_ruta) -> Path:
    """modelo_vrm/<modelo>.lune.json (a_luna.vrm → a_luna.lune.json). ValueError si el nombre no vale."""
    archivo = _archivo_de(nombre_o_ruta)
    return CARPETA / (archivo[:-4] + ".lune.json")


def ajustes_modelo(nombre_o_ruta) -> Dict[str, Any]:
    """Calibración guardada de un modelo (validada). {} si no tiene, está rota o el nombre no vale."""
    try:
        ruta = ruta_ajustes(nombre_o_ruta)
        if ruta.stat().st_size > _MAX_AJUSTES:
            return {}
        crudo = json.loads(ruta.read_text("utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return validar_ajustes(crudo)


def _escribir_json_atomico(ruta: Path, obj) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(ruta.parent), prefix=ruta.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def guardar_ajustes_modelo(nombre_o_ruta, cambios, reemplazar: bool = False) -> Dict[str, Any]:
    """
    Mezcla `cambios` (dict o texto JSON) con la calibración guardada del modelo y
    la escribe (atómica) en modelo_vrm/<modelo>.lune.json. Las claves que no son
    de AJUSTES se ignoran; los valores se recortan a su rango; `None` borra la
    clave (vuelve al valor por defecto). Con reemplazar=True no se mezcla. Si no
    queda nada, se borra el archivo. Devuelve lo guardado. ValueError si el
    nombre o el JSON no valen.
    """
    ruta = ruta_ajustes(nombre_o_ruta)
    if isinstance(cambios, (bytes, bytearray)):
        cambios = cambios.decode("utf-8", "replace")
    if isinstance(cambios, str):
        try:
            cambios = json.loads(cambios) if cambios.strip() else {}
        except (ValueError, RecursionError) as e:
            raise ValueError(f"Los ajustes no son JSON válido: {e}")
    if cambios is None:
        cambios = {}
    if not isinstance(cambios, Mapping):
        raise ValueError("Los ajustes tienen que ser un objeto {clave: valor}.")
    final = {} if reemplazar else ajustes_modelo(nombre_o_ruta)
    for clave, valor in cambios.items():
        if clave not in AJUSTES:
            continue
        if valor is None:
            final.pop(clave, None)
            continue
        v = validar_valor(clave, valor)
        if v is not None:
            final[clave] = v
    final = {k: final[k] for k in AJUSTES if k in final}
    if final:
        _escribir_json_atomico(ruta, final)
    else:
        try:
            ruta.unlink()
        except OSError:
            pass
    return final


def params_modelo(nombre_o_ruta=None, config=None) -> Dict[str, Any]:
    """
    Los parámetros que se mandan a window.luneParams para este modelo: TODAS las
    claves de AJUSTES (las que el modelo no calibra, con su valor por defecto),
    los pesos de seguimiento de config (avatar.peso_cabeza/torso/ojos) si el
    modelo no trae los suyos, y los tres pesos a 0 si avatar.seguir_cursor está
    apagado (el interruptor global manda sobre el modelo).
    """
    out: Dict[str, Any] = {k: r["defecto"] for k, r in AJUSTES.items()}
    for clave, clave_cfg in PESOS_CONFIG.items():
        v = validar_valor(clave, _cfg(config, clave_cfg, None))
        if v is not None:
            out[clave] = v
    if nombre_o_ruta:
        out.update(ajustes_modelo(nombre_o_ruta))
    if config is not None and not bool(_cfg(config, "seguir_cursor", True)):
        for clave in PESOS_CONFIG:
            out[clave] = 0.0
    return out


def ficha(nombre: str, config=None) -> Dict[str, Any]:
    """
    Todo lo que enseña la biblioteca de un modelo de modelo_vrm/: meta() +
    {ajustes (lo guardado), efectivos (params_modelo), personajes (quién lo usa),
    por_defecto (es avatar.vrm_archivo)}. {ok: False, motivo} si no está.
    """
    try:
        archivo = _nombre_seguro(nombre)
    except ValueError as e:
        return {"ok": False, "motivo": str(e), "archivo": _texto(nombre, 120)}
    ruta = CARPETA / archivo
    if not ruta.is_file():
        return {"ok": False, "motivo": f"No encuentro «{archivo}» en modelo_vrm/.", "archivo": archivo}
    info = meta(ruta)
    info["archivo"] = archivo
    info["ajustes"] = ajustes_modelo(archivo)
    info["efectivos"] = params_modelo(archivo, config)
    info["personajes"] = personajes_con(archivo)
    info["por_defecto"] = _apunta_a(_cfg(config, "vrm_archivo", ""), archivo)
    return info


def biblioteca(config=None) -> Dict[str, Any]:
    """
    La rejilla entera de una vez: {webengine, carpeta, activo (personaje),
    activo_vrm (su modelo, nombre de archivo o ""), por_defecto (avatar.vrm_archivo),
    modelos: [ficha() sin «efectivos» de cada .vrm válido de modelo_vrm/]}.
    Solo lee los chunks JSON: no carga mallas ni miniaturas (esas van aparte,
    con miniatura_data_url, para no mandar megas en una sola respuesta).
    """
    try:
        activo = personajes.get_activo() or {}
    except Exception:
        activo = {}
    v = str(activo.get("vrm") or "").strip() if isinstance(activo, dict) else ""
    activo_vrm = ""
    if v:
        r = resolver(v)
        activo_vrm = r.name if r is not None and _misma_carpeta(r.parent, CARPETA) else v
    modelos = []
    for archivo in listar_modelos():
        f = ficha(archivo, config)
        f.pop("efectivos", None)
        modelos.append(f)
    return {
        "webengine": webengine_disponible(), "carpeta": str(CARPETA),
        "activo": _texto(activo.get("nombre") if isinstance(activo, dict) else "", 120),
        "activo_vrm": activo_vrm,
        "por_defecto": str(_cfg(config, "vrm_archivo", "") or ""),
        "modelos": modelos,
    }


# ── Envoltorios JSON para el puente web (ui/web_bridge.py) ───────────────────

def biblioteca_json(config=None) -> str:
    return json.dumps(biblioteca(config), ensure_ascii=False)


def ficha_json(nombre: str, config=None) -> str:
    return json.dumps(ficha(nombre, config), ensure_ascii=False)


def params_modelo_json(nombre_o_ruta=None, config=None) -> str:
    return json.dumps(params_modelo(nombre_o_ruta, config), ensure_ascii=False)


def guardar_ajustes_json(nombre: str, cambios, config=None) -> str:
    """{ok, archivo, ajustes, efectivos} o {ok: False, error}."""
    try:
        aj = guardar_ajustes_modelo(nombre, cambios)
        return json.dumps({"ok": True, "archivo": _archivo_de(nombre), "ajustes": aj,
                           "efectivos": params_modelo(nombre, config)}, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def borrar_json(nombre: str, config=None) -> str:
    """{ok, archivo, personajes, por_defecto, modelos} o {ok: False, error}."""
    try:
        return json.dumps(borrar_modelo(nombre, config), ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════════════
#  Herramienta del modelo: mascota_tamano
# ═════════════════════════════════════════════════════════════════════════════

TAMANOS = ("pequeno", "normal", "grande")
_SINONIMOS_TAMANO = {
    "pequeno": "pequeno", "pequena": "pequeno", "chica": "pequeno", "chico": "pequeno",
    "chiquita": "pequeno", "mini": "pequeno", "small": "pequeno",
    "normal": "normal", "mediana": "normal", "mediano": "normal", "media": "normal",
    "medio": "normal", "medium": "normal",
    "grande": "grande", "enorme": "grande", "big": "grande", "large": "grande",
}
_ETIQUETA_TAMANO = {"pequeno": "pequeña", "normal": "de tamaño normal", "grande": "grande"}


def normalizar_tamano(valor) -> Optional[str]:
    """«Pequeña», «pequeño», «MEDIANA», «big»… → pequeno|normal|grande, o None."""
    s = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode("ascii")
    return _SINONIMOS_TAMANO.get(s.strip().lower())


def _de_ctx(ctx, clave: str, _hondo: int = 0):
    """ctx[clave] (dict) o ctx.clave (objeto). El Ejecutor envuelve un ctx que no
    es dict como {..., 'contexto': objeto}: también se busca ahí."""
    if ctx is None:
        return None
    if isinstance(ctx, Mapping):
        v = ctx.get(clave)
        if v is None and _hondo == 0 and ctx.get("contexto") is not None:
            v = _de_ctx(ctx.get("contexto"), clave, 1)
        return v
    return getattr(ctx, clave, None)


def herramienta_tamano(args, ctx=None) -> Tuple[bool, str]:
    """
    Handler de `mascota_tamano` ({tamano: pequeno|normal|grande}) → (ok, mensaje).
    Guarda avatar.vrm_tamano en ctx['config'] y, si ctx['mascota'] tiene
    aplicar_tamano (la mascota 3D), la cambia ya. ctx['en_ui'] opcional: fn(callable)
    que ejecuta en el hilo de Qt (si el Ejecutor corre en otro hilo) y devuelve lo
    que devuelva fn; si aplicar_tamano devuelve False, no se da por hecho.
    """
    valor = args.get("tamano") if isinstance(args, Mapping) else args
    t = normalizar_tamano(valor)
    if t is None:
        return False, "Ese tamaño no existe: usa pequeno, normal o grande."
    config = _de_ctx(ctx, "config")
    mascota = _de_ctx(ctx, "mascota")
    if config is not None:
        try:
            config.set("avatar", "vrm_tamano", t)
        except Exception:
            config = None
    fn = getattr(mascota, "aplicar_tamano", None) if mascota is not None else None
    if callable(fn) and getattr(mascota, "render", "vrm") == "vrm":
        en_ui = _de_ctx(ctx, "en_ui")
        try:
            # Contrato: en_ui(fn) devuelve lo que devuelve fn (web_bridge, main.py).
            r = en_ui(lambda: fn(t)) if callable(en_ui) else fn(t)
        except Exception as e:
            return False, f"No pude cambiar el tamaño: {e}"[:300]
        if r is False:
            return False, "Ahora no puedo cambiar de tamaño."
        return True, f"Listo: ahora soy {_ETIQUETA_TAMANO[t]}."
    if config is None:
        return False, "No hay mascota abierta ni configuración donde guardar el tamaño."
    return True, f"Guardado: cuando salga como mascota 3D seré {_ETIQUETA_TAMANO[t]}."
