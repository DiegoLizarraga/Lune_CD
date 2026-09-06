"""
lune_core/voz/kokoro_backend.py — Voz de salida 100% local con Kokoro (ONNX).

Alternativa a edge-tts que no necesita internet: sintetiza en tu máquina con el
modelo Kokoro-82M vía onnxruntime (ligero, sin PyTorch). Se enchufa detrás de la
MISMA interfaz que usa voice.py, así que el pipeline por frases lo hereda tal cual.

Dependencias de carga diferida — si faltan, la app arranca igual y Lune sigue
hablando con edge-tts:
    pip install kokoro-onnx
    (y espeak-ng del sistema, para fonemizar español)

Además hacen falta los pesos, que NO van en el repo (pon la ruta en Configuración
o déjalos en la carpeta por defecto `modelos_voz/`):
    kokoro-v1.0.onnx      (~310 MB; hay versiones int8 más ligeras)
    voices-v1.0.bin       (~26 MB, trae las voces multilingües)

Descarga (una vez):
    https://github.com/thewh1teagle/kokoro-onnx/releases

El modelo se carga UNA vez y se queda en memoria: la primera frase tarda unos
segundos y las siguientes son rápidas.
"""
from __future__ import annotations

import importlib.util
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Optional

# Kokoro genera audio a 24 kHz.
SAMPLE_RATE = 24000

# Voces hispanas de Kokoro (prefijo 'e' = español). El oído decide cuál encaja.
VOCES_ES = {
    "ef_dora": "Dora (femenina)",
    "em_alex": "Alex (masculina)",
    "em_santa": "Santa (masculina)",
}
VOZ_POR_DEFECTO = "ef_dora"

# Carpeta y nombres por defecto de los pesos.
CARPETA_DEFECTO = "modelos_voz"
ARCHIVO_ONNX = "kokoro-v1.0.onnx"
ARCHIVO_VOCES = "voices-v1.0.bin"

_kokoro = None                 # instancia cacheada
_ruta_cargada = None           # (onnx, voces) con la que se cargó
_lock = threading.Lock()


# ── Disponibilidad ─────────────────────────────────────────────────────────────

def dependencias_faltantes() -> List[str]:
    """Paquetes pip que faltan para la voz local."""
    faltan = []
    if importlib.util.find_spec("kokoro_onnx") is None:
        faltan.append("kokoro-onnx")
    return faltan


def _rutas(carpeta: Optional[str] = None):
    base = Path(carpeta or CARPETA_DEFECTO)
    return base / ARCHIVO_ONNX, base / ARCHIVO_VOCES


def modelos_presentes(carpeta: Optional[str] = None) -> bool:
    onnx, voces = _rutas(carpeta)
    return onnx.exists() and voces.exists()


def disponible(carpeta: Optional[str] = None) -> bool:
    return not dependencias_faltantes() and modelos_presentes(carpeta)


def mensaje_instalacion(carpeta: Optional[str] = None) -> str:
    faltan = dependencias_faltantes()
    partes = ["Para hablar con voz 100% local (Kokoro) necesito:"]
    if faltan:
        partes.append(f"\n    pip install {' '.join(faltan)}")
        partes.append("    (y espeak-ng del sistema, para el español)")
    if not modelos_presentes(carpeta):
        onnx, voces = _rutas(carpeta)
        partes.append(f"\ny los pesos en «{onnx.parent}/»:")
        partes.append(f"    {ARCHIVO_ONNX} y {ARCHIVO_VOCES}")
        partes.append("    https://github.com/thewh1teagle/kokoro-onnx/releases")
    partes.append("\nMientras tanto, Lune sigue hablando con edge-tts.")
    return "\n".join(partes)


# ── Carga y síntesis ────────────────────────────────────────────────────────────

def cargar(carpeta: Optional[str] = None):
    """Carga (y cachea) el modelo Kokoro. Lanza RuntimeError con mensaje claro."""
    global _kokoro, _ruta_cargada
    if dependencias_faltantes():
        raise RuntimeError(mensaje_instalacion(carpeta))
    onnx, voces = _rutas(carpeta)
    if not (onnx.exists() and voces.exists()):
        raise RuntimeError(mensaje_instalacion(carpeta))

    clave = (str(onnx), str(voces))
    with _lock:
        if _kokoro is not None and _ruta_cargada == clave:
            return _kokoro
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(onnx), str(voces))
        _ruta_cargada = clave
        return _kokoro


def sintetizar(texto: str, voz: str = VOZ_POR_DEFECTO, velocidad: float = 1.0,
               carpeta: Optional[str] = None, idioma: str = "es") -> Optional[str]:
    """
    Sintetiza `texto` a un WAV temporal (24 kHz) y devuelve su ruta, o None.
    No reproduce nada. Pensado para _sintetizar_a_archivo de voice.py.
    """
    if not (texto or "").strip():
        return None
    try:
        import numpy as np
        k = cargar(carpeta)
        if voz not in VOCES_ES:
            voz = VOZ_POR_DEFECTO
        muestras, sr = k.create(texto, voice=voz, speed=float(velocidad or 1.0), lang=idioma)
        muestras = np.asarray(muestras, dtype=np.float32)
        # float32 [-1, 1] → int16 PCM
        pcm = np.clip(muestras, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype("<i2")

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sr or SAMPLE_RATE))
            w.writeframes(pcm.tobytes())
        return tmp.name
    except Exception:
        # Cualquier fallo (deps/pesos ausentes, espeak-ng, voz inválida…) →
        # devolver None para que voice.py caiga a edge-tts sin romperse.
        return None


def descargar():
    """Suelta el modelo de memoria."""
    global _kokoro, _ruta_cargada
    with _lock:
        _kokoro = None
        _ruta_cargada = None
