"""
datos.py — Lector global de configuración para Lune CD
Lee datos.json que está en la raíz del proyecto.
Usado por main.py y ai_manager.py
"""
import json
from pathlib import Path

# datos.json está siempre en la carpeta raíz del proyecto
_ROOT = Path(__file__).parent
_PATH = _ROOT / "datos.json"


def _load() -> dict:
    if not _PATH.exists():
        raise FileNotFoundError(
            f"No encontré datos.json en {_ROOT}\n"
            "Asegúrate de que el archivo existe en la raíz del proyecto."
        )
    return json.loads(_PATH.read_text("utf-8"))


def get_apis() -> dict:
    return _load().get("apis", {})

def get_modelos() -> dict:
    return _load().get("modelos", {})

def get_bot() -> dict:
    return _load().get("bot", {})

def get_personajes() -> list:
    return _load().get("personajes", [])

def get_personaje(nombre: str) -> dict:
    personajes = get_personajes()
    nombre_lower = nombre.lower() if nombre else ""
    return next(
        (p for p in personajes if p["nombre"].lower() == nombre_lower),
        personajes[0] if personajes else {}
    )

# Atajos directos
def telegram_token() -> str:
    return get_apis().get("telegram_token", "")

def telegram_admin_id() -> str:
    return str(get_apis().get("telegram_admin_id", ""))

def openrouter_key() -> str:
    return get_apis().get("openrouter_key", "")

def deepseek_key() -> str:
    return get_apis().get("deepseek_key", "")

def character_ai_key() -> str:
    return get_apis().get("character_ai_key", "")

def ollama_url() -> str:
    return get_modelos().get("ollama_url", "http://localhost:11434")

def ollama_model() -> str:
    return get_modelos().get("ollama_model", "dolphin-mistral")

def openrouter_model() -> str:
    return get_modelos().get("openrouter", "stepfun/step-3.5-flash:free")

def deepseek_model() -> str:
    return get_modelos().get("deepseek", "deepseek-chat")
