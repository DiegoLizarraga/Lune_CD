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

VOCES
-----
VOCES_ES (prefijo «e») y VOCES_EN (americanas «a», británicas «b») son las de
voices-v1.0.bin. Si el archivo está, `voces_instaladas()` lee sus nombres sin
cargar el modelo y la voz pedida se valida contra ellos; si no se puede leer,
se valida contra estas listas. Una voz que no vale cae a VOZ_POR_DEFECTO.
El fonemizador sigue al idioma del TEXTO (voz.idioma, «es» en Lune), no al de
la voz: una voz inglesa leyendo español suena a acento, no a otro idioma.
Las carpetas relativas se anclan a la carpeta de datos del usuario (rutas.DATOS:
la raíz del proyecto desde el código), no al directorio de trabajo, para que la
app, patata y los tests encuentren los mismos pesos.
"""
from __future__ import annotations

import importlib.util
import tempfile
import threading
import wave
from pathlib import Path
from typing import Dict, List, Optional

from nucleo import rutas

# Los pesos los descarga el usuario: van con sus datos (desde el código, la raíz del repo).
RAIZ = rutas.DATOS

# Kokoro genera audio a 24 kHz.
SAMPLE_RATE = 24000

# Voces hispanas de Kokoro (prefijo 'e' = español). El oído decide cuál encaja.
VOCES_ES = {
    "ef_dora": "Dora (femenina)",
    "em_alex": "Alex (masculina)",
    "em_santa": "Santa (masculina)",
}
# Voces inglesas de Kokoro v1.0 ('a' = EE. UU., 'b' = Reino Unido; 'f'/'m' = género).
VOCES_EN = {
    "af_alloy": "Alloy (femenina, EE. UU.)", "af_aoede": "Aoede (femenina, EE. UU.)",
    "af_bella": "Bella (femenina, EE. UU.)", "af_heart": "Heart (femenina, EE. UU.)",
    "af_jessica": "Jessica (femenina, EE. UU.)", "af_kore": "Kore (femenina, EE. UU.)",
    "af_nicole": "Nicole (femenina, EE. UU.)", "af_nova": "Nova (femenina, EE. UU.)",
    "af_river": "River (femenina, EE. UU.)", "af_sarah": "Sarah (femenina, EE. UU.)",
    "af_sky": "Sky (femenina, EE. UU.)",
    "am_adam": "Adam (masculina, EE. UU.)", "am_echo": "Echo (masculina, EE. UU.)",
    "am_eric": "Eric (masculina, EE. UU.)", "am_fenrir": "Fenrir (masculina, EE. UU.)",
    "am_liam": "Liam (masculina, EE. UU.)", "am_michael": "Michael (masculina, EE. UU.)",
    "am_onyx": "Onyx (masculina, EE. UU.)", "am_puck": "Puck (masculina, EE. UU.)",
    "am_santa": "Santa (masculina, EE. UU.)",
    "bf_alice": "Alice (femenina, Reino Unido)", "bf_emma": "Emma (femenina, Reino Unido)",
    "bf_isabella": "Isabella (femenina, Reino Unido)", "bf_lily": "Lily (femenina, Reino Unido)",
    "bm_daniel": "Daniel (masculina, Reino Unido)", "bm_fable": "Fable (masculina, Reino Unido)",
    "bm_george": "George (masculina, Reino Unido)", "bm_lewis": "Lewis (masculina, Reino Unido)",
}
VOCES: Dict[str, str] = {**VOCES_ES, **VOCES_EN}
VOZ_POR_DEFECTO = "ef_dora"

# Carpeta y nombres por defecto de los pesos.
CARPETA_DEFECTO = "modelos_voz"
ARCHIVO_ONNX = "kokoro-v1.0.onnx"
ARCHIVO_VOCES = "voices-v1.0.bin"

_kokoro = None                 # instancia cacheada
_ruta_cargada = None           # (onnx, voces) con la que se cargó
_lock = threading.Lock()
_cache_instaladas: dict = {}   # (ruta, mtime) → lista de nombres


# ── Disponibilidad ─────────────────────────────────────────────────────────────

def dependencias_faltantes() -> List[str]:
    """Paquetes pip que faltan para la voz local."""
    faltan = []
    if importlib.util.find_spec("kokoro_onnx") is None:
        faltan.append("kokoro-onnx")
    return faltan


def _rutas(carpeta: Optional[str] = None):
    base = Path(carpeta or CARPETA_DEFECTO)
    if not base.is_absolute():
        base = RAIZ / base
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
        partes.append(f"\n    {rutas.como_instalar(*faltan)}")
        partes.append("    (y espeak-ng del sistema, para el español)")
    if not modelos_presentes(carpeta):
        onnx, voces = _rutas(carpeta)
        partes.append(f"\ny los pesos en «{onnx.parent}/»:")
        partes.append(f"    {ARCHIVO_ONNX} y {ARCHIVO_VOCES}")
        partes.append("    https://github.com/thewh1teagle/kokoro-onnx/releases")
    partes.append("\nMientras tanto, Lune sigue hablando con edge-tts.")
    return "\n".join(partes)


# ── Voces ───────────────────────────────────────────────────────────────────────

def voces_instaladas(carpeta: Optional[str] = None) -> List[str]:
    """
    Nombres de las voces que trae voices-v1.0.bin (un .npz), sin cargar el
    modelo. Lista vacía si no hay archivo, falta numpy o no se puede leer: en
    ese caso quien valida se conforma con VOCES.
    """
    _onnx, voces = _rutas(carpeta)
    with _lock:
        if _kokoro is not None and _ruta_cargada and _ruta_cargada[1] == str(voces):
            try:
                return sorted(_kokoro.get_voices())
            except Exception:
                pass
    try:
        clave = (str(voces), voces.stat().st_mtime)
    except OSError:
        return []
    if clave in _cache_instaladas:
        return list(_cache_instaladas[clave])
    try:
        import numpy as np
        with np.load(str(voces), allow_pickle=False) as npz:
            nombres = sorted(str(n) for n in npz.files)
    except Exception:
        nombres = []
    _cache_instaladas.clear()
    _cache_instaladas[clave] = nombres
    return list(nombres)


def es_voz_valida(voz: str, carpeta: Optional[str] = None, instaladas: Optional[List[str]] = None) -> bool:
    """¿Se puede usar `voz`? Contra lo instalado si se sabe; si no, contra VOCES."""
    if not isinstance(voz, str) or not voz:
        return False
    if instaladas is None:
        instaladas = voces_instaladas(carpeta)
    return voz in instaladas if instaladas else voz in VOCES


def validar_voz(voz: str, carpeta: Optional[str] = None, instaladas: Optional[List[str]] = None) -> str:
    """`voz` si vale; si no, VOZ_POR_DEFECTO (o la primera instalada si ni esa está)."""
    if instaladas is None:
        instaladas = voces_instaladas(carpeta)
    if es_voz_valida(voz, instaladas=instaladas):
        return voz
    if not instaladas or VOZ_POR_DEFECTO in instaladas:
        return VOZ_POR_DEFECTO
    return instaladas[0]


def idioma_fonemas(idioma: Optional[str], voz: str = "") -> str:
    """Código de idioma para Kokoro según el idioma del texto: «es», «en-us», «en-gb»…"""
    i = (idioma or "es").strip().lower().replace("_", "-")
    if i in ("en", "en-us", "en-gb"):
        if i == "en-gb" or (i == "en" and voz.startswith("b")):
            return "en-gb"
        return "en-us"
    # Los que entiende Kokoro v1.0; «auto» (Whisper) y lo desconocido → español.
    return {"es": "es", "fr": "fr-fr", "fr-fr": "fr-fr", "it": "it", "pt": "pt-br",
            "pt-br": "pt-br", "hi": "hi", "ja": "ja", "zh": "cmn", "cmn": "cmn"}.get(i, "es")


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
        try:
            instaladas = sorted(k.get_voices())
        except Exception:
            instaladas = []
        voz = validar_voz(voz, instaladas=instaladas)
        muestras, sr = k.create(texto, voice=voz, speed=float(velocidad or 1.0),
                                lang=idioma_fonemas(idioma, voz))
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
