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
  "avatar_pack": "default",   # opcional: pack de lune_face/packs
  "vrm": "nombre.vrm",        # opcional: su modelo 3D (en modelo_vrm/ o ruta absoluta; ver nucleo/vrm.py)
  "voz": {                    # opcional: su voz (ver voz_de() y servicios/voces.py)
    "motor": "edge",          #   auto · edge · gtts · kokoro (si falta, manda el de config)
    "id": "es-AR-ElenaNeural",  # ShortName de edge-tts o voz de Kokoro (ef_dora…)
    "rate": "+0%",            #   velocidad, -50%…+50% (también vale un número: -10)
    "pitch": "+0Hz",          #   tono, -50Hz…+50Hz
    "volumen": "+0%",         #   opcional
    "tld": "com.mx"           #   opcional: acento de gTTS (com.mx · es · us · com)
  },
  "frases_mascota": {         # opcional: frases de la mascota por evento (ver lune_core/frases_mascota.py)
    "arrastre": ["¡Eh, que me mareo!"],     # eventos: arrastre, soltar, caricia, dormir,
    "caricia": ["Jeje~"]                    #   despertar, mareo, aparecer, pudor, sentarse,
  },                          #   bajar, comer · las que falten salen de FRASES_BASE
  "frases_minecraft": {       # opcional (corte 10): reacciones a tu partida de Minecraft
    "muerte": ["Otra vez al suelo."],       # claves de lune_core/minecraft.FRASES: muerte, muerte_otro,
    "logro": ["«{logro}». Bien."]           #   logro, logro_otro, conexion, peligro, dia, noche, lluvia,
  }                           #   bot_*… · huecos {jugador} {logro} {mob} {causa} · las que falten, de serie
}

La voz del personaje manda sobre la de config (voz.edge_voz, edge_rate…), que a
su vez manda sobre la de por defecto (es-MX-DaliaNeural). La lee también el bot
de Telegram (telegram-bot-or/voz.js), así que suena igual en los dos sitios.
El bot de Minecraft usa el personaje (nombre para su nick y su prompt), pero nunca la
memoria: el chat del juego es público.
"""
import json
import base64
import struct
from pathlib import Path
from typing import List, Dict, Optional

from nucleo import datos



# ── Carga / guardado de datos.json ──────────────────────────────────────────────
# Se delega en datos.py para que haya un único lector/escritor del archivo y la
# caché en memoria nunca quede desincronizada del disco.

def _load() -> dict:
    data = datos.cargar()
    if not data:
        return {"apis": {}, "modelos": {}, "bot": {"personaje_default": "Lune"}, "personajes": []}
    return data


def _save(data: dict):
    datos.guardar(data)


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


def set_activo(nombre: str) -> str:
    """
    Activa un personaje que EXISTE en datos.json (sin distinguir mayúsculas) y
    devuelve su nombre tal como está guardado. Si no existe lanza ValueError y no
    toca nada: antes se guardaba cualquier cosa («/personaje Luen») y luego la
    voz, las frases o el .vrm del personaje «activo» fallaban por no encontrarlo.
    """
    data = _load()
    nl = (nombre or "").strip().lower()
    elegido = next((p for p in data.get("personajes", [])
                    if isinstance(p, dict) and nl and (p.get("nombre") or "").lower() == nl), None)
    if elegido is None:
        nombres = ", ".join(p.get("nombre", "") for p in data.get("personajes", [])
                            if isinstance(p, dict) and p.get("nombre")) or "ninguno"
        raise ValueError(f"No existe el personaje «{str(nombre or '').strip()[:60]}». "
                         f"Personajes: {nombres}.")
    data.setdefault("bot", {})["personaje_default"] = elegido["nombre"]
    _save(data)
    return elegido["nombre"]


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


# ── Voz del personaje ────────────────────────────────────────────────────────────

CAMPOS_VOZ = ("motor", "id", "rate", "pitch", "volumen", "tld")


def voz_de(p: Optional[Dict]) -> Dict:
    """
    La voz de un personaje, limpia: solo los CAMPOS_VOZ que tengan valor (texto
    sin espacios o, en rate/pitch/volumen, un número). Admite la forma corta
    `"voz": "es-AR-ElenaNeural"`. Devuelve {} si no trae voz propia. No valida
    que la voz exista: eso lo hace servicios/voces.resolver_voz.
    """
    if not isinstance(p, dict):
        return {}
    v = p.get("voz")
    if isinstance(v, str):
        v = {"id": v}
    if not isinstance(v, dict):
        return {}
    limpia = {}
    for clave in CAMPOS_VOZ:
        valor = v.get(clave)
        if isinstance(valor, bool) or valor is None:
            continue
        if isinstance(valor, (int, float)) and clave in ("rate", "pitch", "volumen"):
            limpia[clave] = valor
        elif isinstance(valor, str) and valor.strip():
            limpia[clave] = valor.strip()
    return limpia


def set_voz(nombre: str, voz: Optional[Dict]) -> bool:
    """Guarda (o quita, con None o {}) la voz de un personaje. False si no existe."""
    data = _load()
    nl = (nombre or "").lower()
    for p in data.get("personajes", []):
        if p.get("nombre", "").lower() == nl:
            limpia = voz_de({"voz": voz}) if voz else {}
            if limpia:
                p["voz"] = limpia
            else:
                p.pop("voz", None)
            _save(data)
            return True
    return False


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
