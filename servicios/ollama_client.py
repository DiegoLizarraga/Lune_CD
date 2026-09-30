"""
ollama_client.py — Utilidades para hablar con un servidor Ollama.

Sirve tanto para la app local (`http://localhost:11434`) como para apuntar a
otra máquina de la red — que es justo el caso de tener un PC potente haciendo
de servidor de modelos y la laptop como cliente.

Para exponer Ollama en la red, en el equipo servidor:
    setx OLLAMA_HOST 0.0.0.0:11434      (Windows, reinicia Ollama después)
    export OLLAMA_HOST=0.0.0.0:11434    (Linux/macOS)
y en la app pon http://<ip-del-servidor>:11434
"""
import time
from typing import Dict, List, Optional, Tuple

import requests

# Sesión propia (no compartida con ai_manager) para los sondeos de la UI:
# son llamadas cortas y no deben competir con un streaming en curso.
_session = requests.Session()
_session.headers.update({"User-Agent": "LuneCD/ollama-probe"})

TIMEOUT_SONDEO = 6

# (url, modelo) → (soporta_vision, cuándo se consultó). Se recuerda 5 min: la
# asistente en escritorio pregunta antes de cada comentario de pantalla y /api/show
# no es gratis.
_cache_vision: Dict[Tuple[str, str], Tuple[Optional[bool], float]] = {}
_CACHE_VISION_S = 300
# Familias con proyector de imagen en versiones de Ollama sin "capabilities".
_FAMILIAS_VISION = ("clip", "mllama", "llava", "qwen2vl", "qwen25vl", "gemma3", "mistral3", "minicpm-v", "moondream")


def soporta_vision(url: str, modelo: str, timeout: int = TIMEOUT_SONDEO) -> Optional[bool]:
    """
    ¿El modelo puede ver imágenes? True / False, o None si no se pudo saber.
    Ollama recientes devuelven "capabilities" en /api/show (con "vision" si
    procede); en los viejos se mira si el modelo trae proyector/CLIP.
    Un modelo de solo texto rechaza las imágenes con un 400: mejor saberlo antes.
    """
    modelo = (modelo or "").strip()
    if not modelo:
        return None
    url = normalizar_url(url)
    clave = (url, modelo)
    ahora = time.monotonic()
    guardado = _cache_vision.get(clave)
    if guardado is not None and ahora - guardado[1] < _CACHE_VISION_S:
        return guardado[0]
    try:
        r = _session.post(f"{url}/api/show", json={"model": modelo, "name": modelo}, timeout=timeout)
        r.raise_for_status()
        d = r.json() or {}
    except Exception:
        return None
    res: Optional[bool] = None
    caps = d.get("capabilities")
    if isinstance(caps, list):
        res = "vision" in [str(c).lower() for c in caps]
    else:
        det = d.get("details") or {}
        fams = [str(f).lower() for f in (det.get("families") or [])] + [str(det.get("family") or "").lower()]
        info = d.get("model_info") or {}
        claves_info = [str(k).lower() for k in info] if isinstance(info, dict) else []
        if any(f in _FAMILIAS_VISION for f in fams if f) or any("projector" in k or "vision" in k for k in claves_info):
            res = True
        elif any(fams):
            res = False
    _cache_vision[clave] = (res, ahora)
    return res


def marcar_sin_vision(url: str, modelo: str):
    """Ollama rechazó una imagen: recordar que este modelo no ve (sin volver a preguntar)."""
    if modelo:
        _cache_vision[(normalizar_url(url), modelo.strip())] = (False, time.monotonic())


def olvidar_vision():
    _cache_vision.clear()


def normalizar_url(url: str) -> str:
    """Acepta «192.168.1.50», «localhost:11434» o una URL completa."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return "http://localhost:11434"
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    # Si no trae puerto, asumimos el de Ollama
    resto = url.split("://", 1)[1]
    host = resto.split("/", 1)[0]
    if ":" not in host:
        url = url.replace(host, f"{host}:11434", 1)
    return url


def listar_modelos(url: str, timeout: int = TIMEOUT_SONDEO) -> Tuple[bool, List[str], str]:
    """
    Consulta /api/tags. Devuelve (ok, modelos, mensaje).
    Nunca lanza: los errores vuelven en el mensaje para mostrarlos en la UI.
    """
    url = normalizar_url(url)
    try:
        r = _session.get(f"{url}/api/tags", timeout=timeout)
        r.raise_for_status()
        datos = r.json()
    except requests.exceptions.ConnectionError:
        return False, [], "No hay nadie escuchando ahí. ¿Está corriendo «ollama serve»?"
    except requests.exceptions.Timeout:
        return False, [], f"El servidor no respondió en {timeout}s."
    except Exception as e:
        return False, [], f"Error consultando Ollama: {e}"

    modelos = []
    for m in datos.get("models", []):
        nombre = m.get("name") or m.get("model")
        if nombre:
            modelos.append(nombre)
    modelos.sort()

    if not modelos:
        return True, [], "Conectado, pero no hay modelos descargados (usa «ollama pull»)."
    return True, modelos, f"Conectado · {len(modelos)} modelo(s) disponible(s)."
