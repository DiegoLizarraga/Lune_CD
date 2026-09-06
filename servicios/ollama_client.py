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
from typing import List, Tuple

import requests

# Sesión propia (no compartida con ai_manager) para los sondeos de la UI:
# son llamadas cortas y no deben competir con un streaming en curso.
_session = requests.Session()
_session.headers.update({"User-Agent": "LuneCD/ollama-probe"})

TIMEOUT_SONDEO = 6


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
