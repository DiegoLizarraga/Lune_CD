"""
datos.py — Lector global de configuración para Lune CD
Lee datos.json que está en la raíz del proyecto.
"""
import json
from pathlib import Path

_ROOT = Path(__file__).parent
_PATH = _ROOT / "datos.json"

def _load() -> dict:
    if not _PATH.exists():
        return {}
    return json.loads(_PATH.read_text("utf-8"))

def get_apis() -> dict: return _load().get("apis", {})
def get_modelos() -> dict: return _load().get("modelos", {})
def get_bot() -> dict: return _load().get("bot", {})
def get_personajes() -> list: return _load().get("personajes", [])

def get_personaje(nombre: str) -> dict:
    personajes = get_personajes()
    nombre_lower = nombre.lower() if nombre else ""
    return next((p for p in personajes if p.get("nombre", "").lower() == nombre_lower), personajes[0] if personajes else {})

# ── Atajos directos ──
def telegram_token() -> str: return get_apis().get("telegram_token", "")
def telegram_admin_id() -> str: return str(get_apis().get("telegram_admin_id", ""))
def openrouter_key() -> str: return get_apis().get("openrouter_key", "")

def openrouter_model() -> str: return get_modelos().get("openrouter_model", "openrouter/auto")
def ollama_url() -> str: return get_modelos().get("ollama_url", "http://localhost:11434")
def ollama_model() -> str: return get_modelos().get("ollama_model", "nova")