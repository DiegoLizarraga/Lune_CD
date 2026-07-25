"""
datos.py — Lector/escritor global de configuración para Lune CD.

Es el ÚNICO módulo que toca datos.json. El resto de la app (personajes.py,
settings_panel.py, theme.py…) pasa por aquí, para que la caché en memoria
nunca quede desincronizada del disco.

datos.json no está versionado (lleva las API keys). Si no existe, se crea
automáticamente a partir de datos.example.json al importar este módulo.
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).parent
_PATH = _ROOT / "datos.json"
_EJEMPLO = _ROOT / "datos.example.json"

# Caché en memoria: evita releer el disco en cada llamada. Se invalida sola
# cuando datos.json cambia por fuera (mtime) y explícitamente al guardar.
_cache: dict = {}
_cache_mtime: float = -1.0


# ── Arranque en frío ───────────────────────────────────────────────────────────

def _bootstrap():
    """Crea datos.json desde la plantilla la primera vez que se ejecuta la app."""
    if _PATH.exists() or not _EJEMPLO.exists():
        return
    try:
        shutil.copyfile(_EJEMPLO, _PATH)
    except OSError:
        pass


_bootstrap()


# ── Carga / guardado ───────────────────────────────────────────────────────────

def _load() -> dict:
    """Lee datos.json con caché basada en mtime. Mucho más rápido en ráfagas."""
    global _cache, _cache_mtime
    if not _PATH.exists():
        return {}
    try:
        mtime = _PATH.stat().st_mtime
    except OSError:
        mtime = -1.0
    if mtime != _cache_mtime or not _cache:
        try:
            _cache = json.loads(_PATH.read_text("utf-8"))
            _cache_mtime = mtime
        except (json.JSONDecodeError, OSError):
            return _cache or {}
    return _cache


def cargar() -> dict:
    """Copia mutable de datos.json (para editar y devolver con `guardar`)."""
    return json.loads(json.dumps(_load()))


def guardar(data: dict):
    """Escribe datos.json e invalida la caché para que el cambio se vea ya."""
    global _cache, _cache_mtime
    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache = data
    try:
        _cache_mtime = _PATH.stat().st_mtime
    except OSError:
        _cache_mtime = -1.0


def invalidar():
    """Fuerza una relectura del disco en la próxima consulta."""
    global _cache, _cache_mtime
    _cache, _cache_mtime = {}, -1.0


# ── Secciones ──────────────────────────────────────────────────────────────────

def get_apis() -> dict: return _load().get("apis", {})
def get_modelos() -> dict: return _load().get("modelos", {})
def get_bot() -> dict: return _load().get("bot", {})
def get_personajes() -> list: return _load().get("personajes", [])


def get_personaje(nombre: str) -> dict:
    personajes = get_personajes()
    nombre_lower = nombre.lower() if nombre else ""
    return next((p for p in personajes if p.get("nombre", "").lower() == nombre_lower),
                personajes[0] if personajes else {})


def _num(valor: Any, defecto: float) -> float:
    """Convierte a número tolerando strings y valores vacíos de la UI."""
    try:
        return type(defecto)(valor)
    except (TypeError, ValueError):
        return defecto


# ── Atajos: APIs ──
def telegram_token() -> str: return get_apis().get("telegram_token", "")
def telegram_admin_id() -> str: return str(get_apis().get("telegram_admin_id", ""))
def openrouter_key() -> str: return get_apis().get("openrouter_key", "")

# ── Atajos: OpenRouter ──
def openrouter_model() -> str: return get_modelos().get("openrouter_model") or "openrouter/auto"

# ── Atajos: Ollama (modelos locales) ──
def ollama_url() -> str: return (get_modelos().get("ollama_url") or "http://localhost:11434").rstrip("/")
def ollama_model() -> str: return get_modelos().get("ollama_model", "")


def ollama_keep_alive() -> str:
    """
    Cuánto mantiene Ollama el modelo cargado en VRAM tras responder.
    Sin esto Ollama lo descarga a los 5 min y pagas la recarga completa
    en el siguiente mensaje — muy notorio con modelos grandes.
    """
    return str(get_modelos().get("ollama_keep_alive") or "30m")


def ollama_num_ctx() -> int:
    """Ventana de contexto del modelo local (tokens)."""
    return int(_num(get_modelos().get("ollama_num_ctx"), 8192))


def ollama_timeout() -> int:
    """
    Segundos de espera. Generoso a propósito: cargar un modelo grande en frío
    puede tardar minutos antes del primer token.
    """
    return int(_num(get_modelos().get("ollama_timeout"), 300))


def temperatura() -> float:
    return float(_num(get_modelos().get("temperatura"), 0.7))


# ── Atajos: comportamiento ──
def max_historial() -> int:
    """Turnos de conversación que se conservan antes de recortar los viejos."""
    return int(_num(get_bot().get("max_historial"), 20))


def max_tokens() -> int:
    return int(_num(get_bot().get("max_tokens"), 1024))
