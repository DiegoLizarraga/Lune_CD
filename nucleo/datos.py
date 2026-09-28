"""
datos.py — Lector/escritor global de configuración para Lune CD.

Es el ÚNICO módulo que toca datos.json. El resto de la app (personajes.py,
settings_panel.py, theme.py…) pasa por aquí, para que la caché en memoria
nunca quede desincronizada del disco.

datos.json no está versionado (lleva las API keys). Si no existe, se crea
automáticamente a partir de datos.example.json al importar este módulo.
"""
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).parent.parent
_PATH = _ROOT / "datos.json"
_EJEMPLO = _ROOT / "datos.example.json"

# Caché en memoria: evita releer el disco en cada llamada. Se invalida sola
# cuando datos.json cambia por fuera (mtime) y explícitamente al guardar.
_cache: dict = {}
_cache_mtime: float = -1.0

# Leer → cambiar → guardar de los atajos de aquí: dos a la vez (Ajustes y
# `/mc bot on`, p. ej.) guardaban cada uno su copia y se perdía un cambio.
_CERROJO = threading.RLock()


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
    """
    Escribe datos.json e invalida la caché para que el cambio se vea ya.

    Escritura atómica (temporal + os.replace): datos.json lleva las API keys y
    lo leen a la vez la app, patata y el bot de Telegram; un corte a mitad de
    escritura dejaba el JSON truncado. Si Windows no deja reemplazar (el otro
    proceso lo tiene abierto justo en ese instante) se escribe directo, como antes.
    """
    global _cache, _cache_mtime
    texto = json.dumps(data, ensure_ascii=False, indent=2)
    with _CERROJO:
        tmp = _PATH.with_name(_PATH.name + ".tmp")
        try:
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, _PATH)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            _PATH.write_text(texto, encoding="utf-8")
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
    """Temperatura efectiva (la explícita o la del preset), limitada a 0–2."""
    return float(parametros_muestreo()["temperatura"])


# ── Atajos: proveedor compatible con OpenAI ('compat') ──
# Cualquier servidor que hable /v1/chat/completions: LM Studio, llama.cpp,
# Groq, OpenAI, Together, Mistral… Se configura en `modelos.compat_*`; la clave
# se acepta también en `apis.compat_key`, junto a las demás, por si la UI la
# guarda ahí.

def compat_url() -> str:
    """URL base tal como la escribió el usuario (sin barra final). Vacía = sin proveedor."""
    return str(get_modelos().get("compat_url") or "").strip().rstrip("/")


def compat_key() -> str:
    return str(get_modelos().get("compat_key") or get_apis().get("compat_key") or "").strip()


def compat_model() -> str:
    return str(get_modelos().get("compat_model") or "").strip()


def compat_timeout() -> int:
    """Segundos de espera por respuesta del proveedor compatible (mínimo 5)."""
    return max(5, int(_num(get_modelos().get("compat_timeout"), 120)))


# ── Atajos: parámetros de muestreo (IA avanzada) ──
# Un preset da valores de partida; lo que el usuario fije a mano en `modelos`
# manda sobre el preset (así el campo de temperatura del panel nativo sigue
# funcionando). Para CAMBIAR de preset usa `aplicar_preset_muestreo`, que
# reescribe sus valores. Lo que ni el preset ni el usuario fijan queda en None:
# el proveedor no lo envía y el modelo usa su propio valor por defecto.

PRESETS_MUESTREO: Dict[str, Dict[str, float]] = {
    "preciso": {"temperatura": 0.2, "top_p": 0.9, "top_k": 40, "min_p": 0.05,
                "repeat_penalty": 1.1},
    "equilibrado": {"temperatura": 0.7},
    "creativo": {"temperatura": 1.0},
}
PRESET_POR_DEFECTO = "equilibrado"
PRESET_PERSONALIZADO = "personalizado"

# clave en datos.json → (tipo, mínimo, máximo, «≤0 significa sin valor»)
_PARAMS_MUESTREO = {
    "temperatura":    (float, 0.0, 2.0, False),
    "top_p":          (float, 0.01, 1.0, False),
    "top_k":          (int, 1, 1000, True),
    "min_p":          (float, 0.0, 1.0, False),
    "repeat_penalty": (float, 0.5, 2.0, False),
    "num_predict":    (int, 1, 131072, True),
    "seed":           (int, 0, 2**31 - 1, False),
}
# Los que un preset reescribe (seed, num_predict y el contexto no son del preset).
_CLAVES_DE_PRESET = ("temperatura", "top_p", "top_k", "min_p", "repeat_penalty")


def _opcional(valor: Any, tipo, minimo, maximo, cero_es_nada: bool):
    """Número validado y limitado a [minimo, maximo]; None si falta o es basura."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    if tipo is int:
        v = int(v)
    if cero_es_nada and v <= 0:
        return None
    if v < 0 and minimo >= 0 and tipo is int:
        return None          # seed negativa = aleatoria
    return tipo(min(max(v, minimo), maximo))


def preset_muestreo() -> str:
    """'preciso' · 'equilibrado' · 'creativo' · 'personalizado' (desconocido → por defecto)."""
    p = str(get_modelos().get("preset_muestreo") or PRESET_POR_DEFECTO).strip().lower()
    return p if p in PRESETS_MUESTREO or p == PRESET_PERSONALIZADO else PRESET_POR_DEFECTO


def parametros_muestreo() -> Dict[str, Any]:
    """
    Parámetros efectivos del modelo:
    {preset, temperatura, top_p, top_k, min_p, repeat_penalty, num_predict,
     seed, num_ctx}. temperatura y num_ctx siempre tienen valor; el resto puede
    ser None (= no enviarlo).
    """
    m = get_modelos()
    preset = preset_muestreo()
    base = PRESETS_MUESTREO.get(preset, {})
    out: Dict[str, Any] = {"preset": preset}
    for clave, (tipo, minimo, maximo, cero_es_nada) in _PARAMS_MUESTREO.items():
        valor = _opcional(m.get(clave), tipo, minimo, maximo, cero_es_nada)
        if valor is None and clave in base:
            valor = tipo(base[clave])
        out[clave] = valor
    if out["temperatura"] is None:
        out["temperatura"] = 0.7
    out["num_ctx"] = ollama_num_ctx()
    return out


def aplicar_preset_muestreo(nombre: str) -> Dict[str, Any]:
    """
    Guarda el preset y reescribe sus valores en datos.json. Lo que el preset no
    define (p. ej. top_k en 'creativo') se borra para que vuelva al valor del
    modelo. 'personalizado' solo cambia la etiqueta. Devuelve los parámetros
    efectivos resultantes.
    """
    nombre = str(nombre or "").strip().lower()
    if nombre not in PRESETS_MUESTREO and nombre != PRESET_PERSONALIZADO:
        raise ValueError(f"preset de muestreo desconocido: {nombre!r}")
    with _CERROJO:
        d = cargar()
        m = d.setdefault("modelos", {})
        m["preset_muestreo"] = nombre
        if nombre != PRESET_PERSONALIZADO:
            valores = PRESETS_MUESTREO[nombre]
            for clave in _CLAVES_DE_PRESET:
                if clave in valores:
                    m[clave] = valores[clave]
                else:
                    m.pop(clave, None)
        guardar(d)
    return parametros_muestreo()


# ── Atajos: comportamiento ──
def max_historial() -> int:
    """Turnos de conversación que se conservan antes de recortar los viejos."""
    return int(_num(get_bot().get("max_historial"), 20))


def max_tokens() -> int:
    return int(_num(get_bot().get("max_tokens"), 1024))


# ── Atajos: Minecraft (bot de Lune, `minecraft-bot/`) ──
# Solo la conexión del bot y su carácter. Lo de la mascota (reaccionar al log,
# UDP de Mate-Engine…) vive en config.json. OJO: `solo_dueno` compara el nick,
# y en un servidor con online-mode=false el nick se puede suplantar; no es una
# garantía de seguridad, solo un filtro.

MINECRAFT_DEFECTO: Dict[str, Any] = {
    "host": "localhost",
    "port": 25565,
    "version": "",            # vacío = la detecta mineflayer
    "usuario": "",            # nick del bot; vacío = el del personaje
    "dueno": "",              # nick de quien manda al bot
    "pensar_cada_s": 45,      # cadencia del «cerebro» (comparte Ollama con el chat)
    "defender": True,
    "solo_dueno": True,
    "estilo_frases": "personaje",
    "visor": False,           # prismarine-viewer (dependencia opcional)
}


def _bool(valor: Any, defecto: bool) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        v = valor.strip().lower()
        if v in ("1", "true", "si", "sí", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off"):
            return False
    return defecto


def minecraft() -> Dict[str, Any]:
    """Sección `minecraft` de datos.json validada y con valores por defecto."""
    crudo = _load().get("minecraft")
    crudo = crudo if isinstance(crudo, dict) else {}
    d = MINECRAFT_DEFECTO
    out: Dict[str, Any] = {k: v for k, v in crudo.items() if k not in d and not k.startswith("_")}
    out["host"] = str(crudo.get("host") or "").strip() or d["host"]
    puerto = _opcional(crudo.get("port"), int, 1, 10**6, True)
    out["port"] = puerto if puerto is not None and puerto <= 65535 else d["port"]
    for clave in ("version", "usuario", "dueno"):
        out[clave] = str(crudo.get(clave) or "").strip()
    pensar = _opcional(crudo.get("pensar_cada_s"), int, 10, 3600, True)
    out["pensar_cada_s"] = pensar if pensar is not None else d["pensar_cada_s"]
    for clave in ("defender", "solo_dueno", "visor"):
        out[clave] = _bool(crudo.get(clave), d[clave])
    out["estilo_frases"] = str(crudo.get("estilo_frases") or "").strip().lower() or d["estilo_frases"]
    return out


# Lo que acepta guardar_minecraft (el bot lo vuelve a validar en minecraft-bot/src/config.js).
_MC_NICK = re.compile(r"[A-Za-z0-9_]{3,16}")
_MC_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")
_MC_ETIQUETA = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_MC_IPV4 = re.compile(r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}")
_MC_IPV6 = re.compile(r"[0-9A-Fa-f:]{2,39}")
MC_ESTILOS = ("personaje", "sobrio")


def _mc_host(valor: Any) -> str:
    h = str(valor if isinstance(valor, str) else "").strip()
    if not h or len(h) > 253:
        raise ValueError("El servidor tiene que ser un nombre o una IP (sin http:// ni rutas).")
    if _MC_IPV4.fullmatch(h):
        return h
    if ":" in h:
        if _MC_IPV6.fullmatch(h) and h.count(":") >= 2:
            return h
        raise ValueError("El puerto va en su propio campo, no pegado al servidor.")
    if not all(_MC_ETIQUETA.fullmatch(e) for e in h.split(".")):
        raise ValueError("El servidor tiene que ser un nombre o una IP (sin http:// ni rutas).")
    return h


def _mc_entero(valor: Any, minimo: int, maximo: int, texto: str) -> int:
    if isinstance(valor, bool):
        raise ValueError(texto)
    try:
        f = float(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(texto) from None
    if f != int(f) or not minimo <= int(f) <= maximo:
        raise ValueError(texto)
    return int(f)


def _mc_bool(valor: Any, clave: str) -> bool:
    b = _bool(valor, None)          # type: ignore[arg-type]
    if b is None:
        raise ValueError(f"«{clave}» tiene que ser sí o no.")
    return b


def guardar_minecraft(cambios: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida `cambios` de la sección `minecraft` (host, port, version, usuario, dueno,
    pensar_cada_s 30–3600, defender, solo_dueno, estilo_frases) y los guarda con la
    escritura atómica de `guardar`. Las claves que no son de la sección (o `visor`, que
    ya no se usa) se ignoran: nunca llegan a datos.json. Si algo no vale, ValueError
    con el texto para el usuario y NO se guarda nada. → `minecraft()` resultante.
    """
    if not isinstance(cambios, dict):
        raise ValueError("Los cambios de Minecraft tienen que ser un objeto.")
    limpios: Dict[str, Any] = {}
    for clave, valor in cambios.items():
        if clave == "host":
            limpios["host"] = _mc_host(valor)
        elif clave == "port":
            limpios["port"] = _mc_entero(valor, 1, 65535, "El puerto tiene que estar entre 1 y 65535.")
        elif clave == "version":
            v = str(valor or "").strip() if isinstance(valor, (str, type(None))) else None
            if v is None or (v and not _MC_VERSION.fullmatch(v)):
                raise ValueError("La versión tiene que ser como 1.21.1 (o vacía para autodetectarla).")
            limpios["version"] = v
        elif clave in ("usuario", "dueno"):
            n = str(valor or "").strip() if isinstance(valor, (str, type(None))) else None
            if n is None or (n and not _MC_NICK.fullmatch(n)):
                quien = "del bot" if clave == "usuario" else "tuyo (dueño)"
                raise ValueError(f"El nick {quien} tiene que tener 3–16 letras, números o _.")
            limpios[clave] = n
        elif clave == "pensar_cada_s":
            limpios[clave] = _mc_entero(valor, 30, 3600, "«Pensar cada» tiene que estar entre 30 y 3600 s.")
        elif clave in ("defender", "solo_dueno"):
            limpios[clave] = _mc_bool(valor, clave)
        elif clave == "estilo_frases":
            e = str(valor or "").strip().lower()
            if e not in MC_ESTILOS:
                raise ValueError("El estilo de frases es «personaje» o «sobrio».")
            limpios[clave] = e
    with _CERROJO:
        d = cargar()
        mc = d.get("minecraft")
        mc = dict(mc) if isinstance(mc, dict) else {}
        usuario = limpios.get("usuario", str(mc.get("usuario") or "").strip())
        dueno = limpios.get("dueno", str(mc.get("dueno") or "").strip())
        if usuario and dueno and usuario.lower() == dueno.lower():
            raise ValueError("El bot no puede llamarse igual que tú (su dueño).")
        if not limpios:
            return minecraft()
        mc.update(limpios)
        d["minecraft"] = mc
        guardar(d)
        return minecraft()


# ── Atajos: hub (red de Lune: host y terminales) ──
def get_hub() -> dict: return _load().get("hub", {})


def hub_modo() -> str:
    """'local' (todo aquí) · 'host' (sirvo a otros) · 'terminal' (me conecto a otro)."""
    m = str(get_hub().get("modo") or "local").lower()
    return m if m in ("local", "host", "terminal") else "local"


def hub_puerto() -> int: return int(_num(get_hub().get("puerto"), 7777))
def hub_token() -> str: return str(get_hub().get("token") or "")
def hub_url_host() -> str: return str(get_hub().get("url_host") or "").rstrip("/")


def asegurar_token_hub() -> str:
    """Devuelve el token del hub; si no hay, genera uno y lo guarda en datos.json."""
    token = hub_token()
    if token:
        return token
    from lune_core.protocolo import generar_token
    with _CERROJO:
        token = hub_token()            # otro hilo pudo generarlo mientras esperábamos
        if token:
            return token
        d = cargar()
        d.setdefault("hub", {})["token"] = generar_token()
        guardar(d)
    return d["hub"]["token"]

