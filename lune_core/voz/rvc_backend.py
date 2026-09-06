"""
lune_core/voz/rvc_backend.py — Conversión de voz (RVC) sobre el audio ya sintetizado.

EXPERIMENTAL y opcional. Toma el WAV que produce Kokoro (o cualquier TTS) y lo
pasa por un modelo RVC entrenado (.pth + su .index) para que suene con OTRO timbre.
Es lo que necesita "el oído del usuario": el timbre objetivo, el transpose (tono)
y el index_rate se afinan escuchando.

Depende de `rvc-python`, que arrastra torch (pesado). Carga diferida: si no está,
Lune sigue con la voz de Kokoro/edge sin conversión.
    pip install rvc-python

El modelo .pth de la voz deseada NO viene incluido (se consigue o se entrena
aparte) y NO debe commitearse.

Regla de oro: si RVC falla por lo que sea, se devuelve el audio SIN convertir para
no romper la frase.
"""
from __future__ import annotations

import importlib.util
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

_rvc = None
_modelo_cargado = None
_lock = threading.Lock()


def dependencias_faltantes() -> List[str]:
    faltan = []
    if importlib.util.find_spec("rvc_python") is None:
        faltan.append("rvc-python")
    return faltan


def disponible(modelo_pth: Optional[str] = None) -> bool:
    if dependencias_faltantes():
        return False
    return bool(modelo_pth) and Path(modelo_pth).exists()


def mensaje_instalacion() -> str:
    faltan = dependencias_faltantes()
    partes = ["Conversión de voz (RVC) — experimental:"]
    if faltan:
        partes.append(f"\n    pip install {' '.join(faltan)}")
    partes.append("\nAdemás necesitas un modelo de voz .pth (con su .index) y")
    partes.append("apuntarlo en Configuración. Sin él, Lune usa la voz de Kokoro tal cual.")
    return "\n".join(partes)


def _cargar(modelo_pth: str):
    """Carga (y cachea) el motor RVC con el modelo dado. Puede lanzar."""
    global _rvc, _modelo_cargado
    with _lock:
        if _rvc is not None and _modelo_cargado == modelo_pth:
            return _rvc
        from rvc_python.infer import RVCInference
        try:
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu:0"
        except Exception:
            device = "cpu:0"
        rvc = RVCInference(device=device)
        rvc.load_model(modelo_pth)
        _rvc, _modelo_cargado = rvc, modelo_pth
        return rvc


def convertir(ruta_wav_in: str, modelo_pth: str, transpose: int = 0,
              index_rate: float = 0.5) -> str:
    """
    Convierte `ruta_wav_in` con el modelo RVC y devuelve la ruta del WAV resultante.
    Si algo falla, devuelve `ruta_wav_in` sin tocar (degradación silenciosa).
    """
    if not disponible(modelo_pth):
        return ruta_wav_in
    try:
        rvc = _cargar(modelo_pth)
        try:
            rvc.set_params(f0up_key=int(transpose), index_rate=float(index_rate))
        except Exception:
            pass  # API varía entre versiones; los parámetros son opcionales
        salida = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        salida.close()
        rvc.infer_file(ruta_wav_in, salida.name)
        return salida.name
    except Exception:
        return ruta_wav_in


def descargar():
    global _rvc, _modelo_cargado
    with _lock:
        _rvc = None
        _modelo_cargado = None
