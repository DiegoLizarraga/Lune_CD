"""
Dobles de los tests de la biblioteca de bailes y del reproductor (corte 9):
test_bailes.py, test_bailes_pulso.py, test_cancion_python.py y test_mmd_qt.py.
No es un archivo de tests: lo importan.

- `vmd(...)`: escribe un VMD v1/v2 sintético (huesos, morfos, cámara, IK) con los
  nombres en Shift_JIS.
- `vrma(...)` / `glb(...)`: un .vrma (GLB) sintético, con o sin `uri`.
- `MP3`, `OGG`, `FLAC`, `M4A`, `wav(...)`: cabeceras de audio.
- `clics(bpm, ...)`: PCM s16le mono de una pista de clics (para el pulso).
- `EjecutarFalso`: el `subprocess.run` de ffmpeg: apunta los comandos; convertir →
  escribe un Ogg; `-f s16le` → devuelve el PCM que se le dé.
- `ConfigFalsa`: config.get/set en memoria.
- `hacer_baile(carpeta, nombre, ...)`: una carpeta de baile lista.
"""
from __future__ import annotations

import io
import json
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import numpy as np


def vmd(huesos: Sequence[Tuple[str, int]] = (("センター", 0), ("左腕", 90)),
        morfos: Sequence[Tuple[str, int]] = (), camara: int = 0,
        ik: Sequence[Tuple[int, Sequence[Tuple[str, bool]]]] = (), *, v2: bool = True,
        modelo: str = "初音ミク", cuenta_huesos: Optional[int] = None) -> bytes:
    out = bytearray()
    out += (b"Vocaloid Motion Data 0002" if v2 else b"Vocaloid Motion Data file").ljust(30, b"\0")
    out += modelo.encode("shift_jis")[: 20 if v2 else 10].ljust(20 if v2 else 10, b"\0")
    out += struct.pack("<I", len(huesos) if cuenta_huesos is None else cuenta_huesos)
    for nombre, frame in huesos:
        out += nombre.encode("shift_jis").ljust(15, b"\0") + struct.pack("<I", frame)
        out += struct.pack("<3f", 0.0, 0.0, 0.0) + struct.pack("<4f", 0.0, 0.0, 0.0, 1.0) + bytes(range(20, 84))
    out += struct.pack("<I", len(morfos))
    for nombre, frame in morfos:
        out += nombre.encode("shift_jis").ljust(15, b"\0") + struct.pack("<I", frame) + struct.pack("<f", 1.0)
    out += struct.pack("<I", camara)
    for k in range(camara):
        out += struct.pack("<I", k * 10) + bytes(57)
    out += struct.pack("<I", 0)          # luces
    out += struct.pack("<I", 0)          # sombra
    out += struct.pack("<I", len(ik))
    for frame, lista in ik:
        out += struct.pack("<IBI", frame, 1, len(lista))
        for nombre, on in lista:
            out += nombre.encode("shift_jis").ljust(20, b"\0") + bytes([1 if on else 0])
    return bytes(out)


def glb(j: dict, binario: bytes = b"") -> bytes:
    js = json.dumps(j).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binario += b"\0" * ((4 - len(binario) % 4) % 4)
    cuerpo = struct.pack("<II", len(js), 0x4E4F534A) + js
    if binario:
        cuerpo += struct.pack("<II", len(binario), 0x004E4942) + binario
    return b"glTF" + struct.pack("<II", 2, 12 + len(cuerpo)) + cuerpo


def vrma(duracion: float = 2.5, *, uri: Optional[str] = None, imagen_uri: Optional[str] = None,
         extension: bool = True) -> bytes:
    tiempos = np.array([0.0, duracion], np.float32).tobytes()
    rot = np.array([0, 0, 0, 1, 0, 0, 0, 1], np.float32).tobytes()
    buf = {"byteLength": len(tiempos) + len(rot)}
    if uri is not None:
        buf["uri"] = uri
    j = {
        "asset": {"version": "2.0"},
        "extensionsUsed": ["VRMC_vrm_animation"] if extension else [],
        "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0",
                                              "humanoid": {"humanBones": {"hips": {"node": 0}, "spine": {"node": 1}}},
                                              "expressions": {"preset": {"happy": {"node": 2}}},
                                              "lookAt": {"node": 3}}},
        "nodes": [{"name": "hips"}, {"name": "spine"}, {"name": "happy"}, {"name": "lookAt"}],
        "buffers": [buf],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(tiempos)},
                        {"buffer": 0, "byteOffset": len(tiempos), "byteLength": len(rot)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 2, "type": "SCALAR",
                       "min": [0.0], "max": [duracion]},
                      {"bufferView": 1, "componentType": 5126, "count": 2, "type": "VEC4"}],
        "animations": [{"channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}],
                        "samplers": [{"input": 0, "output": 1, "interpolation": "LINEAR"}]}],
    }
    if imagen_uri is not None:
        j["images"] = [{"uri": imagen_uri}]
    return glb(j, b"" if uri is not None else tiempos + rot)


MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(200)
OGG = b"OggS\x00\x02" + bytes(200)
FLAC = b"fLaC" + bytes(200)
M4A = b"\x00\x00\x00\x20ftypM4A " + bytes(200)
AAC_ADTS = b"\xff\xf1\x50\x80" + bytes(200)
MP3_SYNC = b"\xff\xfb\x90\x64" + bytes(200)
WMA = b"\x30\x26\xb2\x75\x8e\x66\xcf\x11" + bytes(200)


def wav(segundos: float = 0.2, sr: int = 8000) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(int(segundos * sr) * 2))
    return b.getvalue()


def clics(bpm: float, *, dur: float = 40.0, primero: float = 0.1, sr: int = 11025, ruido: float = 0.01,
          semilla: int = 1) -> np.ndarray:
    """PCM int16 mono con un clic (900 Hz, 30 ms) en cada golpe desde `primero`."""
    rng = np.random.default_rng(semilla)
    x = ruido * rng.standard_normal(int(sr * dur)).astype(np.float32)
    periodo = 60.0 / bpm
    n = int(0.03 * sr)
    env = 0.8 * np.exp(-np.arange(n) / (0.008 * sr)) * np.sin(2 * np.pi * 900 * np.arange(n) / sr)
    t = primero
    while t < dur - 0.05:
        i = int(round(t * sr))
        x[i:i + n] += env[: len(x[i:i + n])]
        t += periodo
    return (np.clip(x, -1, 1) * 32767).astype(np.int16)


class EjecutarFalso:
    """`subprocess.run` de ffmpeg: apunta cada comando y responde según lo pedido."""

    def __init__(self, pcm: Optional[np.ndarray] = None, *, rc: int = 0, salida_ogg: bytes = OGG):
        self.cmds: List[List[str]] = []
        self.kw: List[dict] = []
        self.pcm = pcm
        self.rc = rc
        self.salida_ogg = salida_ogg

    def __call__(self, cmd, **kw):
        self.cmds.append(list(cmd))
        self.kw.append(kw)
        if self.rc != 0:
            return SimpleNamespace(returncode=self.rc, stdout=b"", stderr=b"fallo de prueba")
        if "s16le" in cmd:
            datos = b"" if self.pcm is None else np.asarray(self.pcm, "<i2").tobytes()
            return SimpleNamespace(returncode=0, stdout=datos, stderr=b"")
        if "libopus" in cmd:
            Path(cmd[-1]).write_bytes(self.salida_ogg)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def de_tipo(self, marca: str) -> List[List[str]]:
        return [c for c in self.cmds if marca in c]


class ConfigFalsa:
    def __init__(self, **baile: Any):
        self.d = {"baile": {"volumen": 0.25, "en_el_sitio": True, "favoritos": [], "desactivados": [],
                            "auto": True, "umbral": 0.05, "apps": ["Spotify"], **baile}}
        self.escrituras: List[Tuple[str, str, Any]] = []

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.escrituras.append((sec, clave, valor))
        self.d.setdefault(sec, {})[clave] = valor


def escribir(ruta: Path, datos: bytes) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return ruta


def hacer_baile(bailes: Path, nombre: str, *, cuerpo: Optional[bytes] = None, cara: Optional[bytes] = None,
                audio: Optional[Tuple[str, bytes]] = ("cancion.mp3", MP3), meta: Optional[dict] = None,
                vrma_datos: Optional[bytes] = None) -> Path:
    """bailes/<nombre>/ con baile.vmd (o baile.vrma), labios.vmd, la canción y lune.json."""
    d = bailes / nombre
    d.mkdir(parents=True, exist_ok=True)
    if vrma_datos is not None:
        escribir(d / "baile.vrma", vrma_datos)
    else:
        escribir(d / "baile.vmd", cuerpo if cuerpo is not None else vmd())
    if cara is not None:
        escribir(d / "labios.vmd", cara)
    if audio is not None:
        escribir(d / audio[0], audio[1])
    if meta is not None:
        (d / "lune.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return d


def lista_ids(bailes: Iterable[Any]) -> List[str]:
    return [b.id for b in bailes]
