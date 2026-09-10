"""
nucleo/vrm.py — Modelos 3D (VRM) de la mascota y su relación con los personajes.

Los .vrm viven en `modelo_vrm/` (gitignored: son pesados y de terceros). Cada
personaje de datos.json puede llevar `"vrm": "<archivo>"` (nombre dentro de
modelo_vrm/ o ruta absoluta); si no lo tiene, se usa el de config
(`avatar.vrm_archivo`) y, si tampoco, el primer .vrm de la carpeta.

Sin Qt: se puede probar sin pantalla.
"""
from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def resolver(nombre_o_ruta: str) -> Optional[Path]:
    """Un nombre dentro de modelo_vrm/ o una ruta absoluta → Path existente, o None."""
    n = str(nombre_o_ruta or "").strip()
    if not n:
        return None
    p = Path(n)
    if p.is_absolute() and p.is_file():
        return p if validar(p)[0] else None
    candidato = CARPETA / p.name
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
