"""
personajes.py — Gestor de personajes / modo Roleplay para Lune CD.
================================================================
Permite tener varias "personas" (no solo Lune), cambiar entre ellas,
y construir un system prompt rico para mantener al modelo en personaje.

También importa "character cards" en el formato estándar de la comunidad
de roleplay (TavernAI / SillyTavern), tanto en JSON como en PNG (el JSON
viene embebido en un chunk tEXt/iTXt con la clave "chara", base64).

Esto NO usa Character.AI ni nada no oficial: corre sobre tus propios
proveedores (OpenRouter / Ollama). Sin tokens, sin baneos, sin Chromium.

Estructura de un personaje (en datos.json -> "personajes"):
{
  "nombre": "Lune",
  "descripcion": "...",
  "systemPrompt": "...",      # instrucciones base (compatibilidad)
  "fraseInicial": "...",      # saludo / primer mensaje
  "personalidad": "...",      # opcional (de la card: personality)
  "escenario": "...",         # opcional (scenario)
  "ejemplos": "...",          # opcional (mes_example)
  "avatar_pack": "default"    # opcional: pack de lune_face/packs
}
"""
import json
import base64
import struct
from pathlib import Path
from typing import List, Dict, Optional

_ROOT = Path(__file__).parent
_PATH = _ROOT / "datos.json"


# ── Carga / guardado de datos.json ──────────────────────────────────────────────

def _load() -> dict:
    try:
        return json.loads(_PATH.read_text("utf-8"))
    except Exception:
        return {"apis": {}, "modelos": {}, "bot": {"personaje_default": "Lune"}, "personajes": []}


def _save(data: dict):
    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── API pública ─────────────────────────────────────────────────────────────────

def listar() -> List[Dict]:
    return _load().get("personajes", [])


def activo_nombre() -> str:
    return _load().get("bot", {}).get("personaje_default", "Lune")


def get(nombre: str) -> Dict:
    nl = (nombre or "").lower()
    personajes = listar()
    return next((p for p in personajes if p.get("nombre", "").lower() == nl),
                personajes[0] if personajes else {})


def get_activo() -> Dict:
    return get(activo_nombre())


def set_activo(nombre: str):
    data = _load()
    data.setdefault("bot", {})["personaje_default"] = nombre
    _save(data)


def eliminar(nombre: str) -> bool:
    data = _load()
    personajes = data.get("personajes", [])
    nl = (nombre or "").lower()
    nuevos = [p for p in personajes if p.get("nombre", "").lower() != nl]
    if len(nuevos) == len(personajes):
        return False
    data["personajes"] = nuevos
    # Si borramos el activo, volver al primero
    if data.get("bot", {}).get("personaje_default", "").lower() == nl:
        data.setdefault("bot", {})["personaje_default"] = nuevos[0]["nombre"] if nuevos else "Lune"
    _save(data)
    return True


def guardar_personaje(personaje: Dict) -> str:
    """Añade o reemplaza un personaje (por nombre). Devuelve el nombre final."""
    data = _load()
    personajes = data.setdefault("personajes", [])
    nl = personaje.get("nombre", "").lower()
    for i, p in enumerate(personajes):
        if p.get("nombre", "").lower() == nl:
            personajes[i] = personaje
            break
    else:
        personajes.append(personaje)
    _save(data)
    return personaje["nombre"]


# ── System prompt de roleplay ────────────────────────────────────────────────────

def build_system_prompt(personaje: Optional[Dict]) -> str:
    """Construye un system prompt rico para mantener al modelo en personaje."""
    if not personaje:
        return "Eres Lune, una asistente virtual."

    nombre = personaje.get("nombre", "Lune")
    base = (personaje.get("systemPrompt") or "").strip()
    desc = (personaje.get("descripcion") or "").strip()
    pers = (personaje.get("personalidad") or "").strip()
    esc  = (personaje.get("escenario") or "").strip()
    ej   = (personaje.get("ejemplos") or "").strip()

    # Personaje simple (solo systemPrompt) → úsalo tal cual
    if base and not (pers or esc or ej):
        return base

    partes = [f"Eres {nombre}. Mantente SIEMPRE en personaje y responde en español."]
    if base: partes.append(base)
    if desc: partes.append(f"Descripción: {desc}")
    if pers: partes.append(f"Personalidad: {pers}")
    if esc:  partes.append(f"Escenario: {esc}")
    if ej:   partes.append(f"Ejemplos de diálogo:\n{ej}")
    partes.append("No rompas el personaje ni digas que eres una IA, salvo que el escenario lo pida.")
    return "\n\n".join(partes)


# ── Importar character cards (TavernAI / SillyTavern) ────────────────────────────

def importar(path: str) -> Dict:
    """
    Importa un personaje desde un .json o .png (character card).
    Lo guarda en datos.json y devuelve el personaje resultante.
    Lanza ValueError si no se pudo leer.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError("El archivo no existe.")

    card = None
    if p.suffix.lower() == ".png":
        card = _png_chara(p)
        if card is None:
            raise ValueError("El PNG no contiene una character card embebida.")
    else:
        try:
            card = json.loads(p.read_text("utf-8"))
        except Exception as e:
            raise ValueError(f"JSON inválido: {e}")

    personaje = _card_a_personaje(card)
    if not personaje.get("nombre"):
        raise ValueError("La card no tiene nombre.")
    guardar_personaje(personaje)
    return personaje


def _card_a_personaje(card: Dict) -> Dict:
    """Convierte una card V1 (plana) o V2 ('data') al formato de Lune."""
    d = card.get("data", card) if isinstance(card, dict) else {}
    nombre = (d.get("name") or "").strip() or "Importado"
    return {
        "nombre": nombre,
        "descripcion": (d.get("description") or "").strip(),
        "personalidad": (d.get("personality") or "").strip(),
        "escenario": (d.get("scenario") or "").strip(),
        "ejemplos": (d.get("mes_example") or "").strip(),
        "fraseInicial": (d.get("first_mes") or "").strip() or f"Hola, soy {nombre}.",
        "systemPrompt": (d.get("system_prompt") or "").strip(),
        "avatar_pack": "default",
    }


def _png_chara(path: Path) -> Optional[Dict]:
    """Extrae el JSON de la card embebido en chunks tEXt/iTXt ('chara'/'ccv3')."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i = 8
    claves = (b"chara", b"ccv3")
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i+4])[0]
        ctype = data[i+4:i+8]
        chunk = data[i+8:i+8+length]
        if ctype == b"tEXt":
            kw, _, txt = chunk.partition(b"\x00")
            if kw.lower() in claves:
                obj = _decode_card(txt)
                if obj is not None:
                    return obj
        elif ctype == b"iTXt":
            partes = chunk.split(b"\x00", 5)
            if len(partes) == 6 and partes[0].lower() in claves:
                obj = _decode_card(partes[5])
                if obj is not None:
                    return obj
        i += 12 + length  # length + type(4) + data + crc(4)
    return None


def _decode_card(txt: bytes) -> Optional[Dict]:
    # Suele venir en base64; a veces JSON plano.
    for intento in (lambda: json.loads(base64.b64decode(txt).decode("utf-8")),
                    lambda: json.loads(txt.decode("utf-8"))):
        try:
            return intento()
        except Exception:
            continue
    return None
