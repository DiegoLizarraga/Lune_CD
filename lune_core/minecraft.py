"""
lune_core/minecraft.py — Qué dice Lune de tu partida de Minecraft y qué le deja
mandar al bot. Sin Qt: se prueba en seco.

REACCIONES (frases fijas, sin modelo)
-------------------------------------
Los eventos llegan del lector de latest.log (lune_core/minecraft_log.py) y del bot
(minecraft-bot/src/observador.js). `reaccion(ev)` elige una frase en el tono de Lune
(o la del personaje, `frases_minecraft[clave]`) y la cara; `Cadencia` decide si toca
decir algo ahora (global 4 s; por tipo; probabilidad) y DESCARTA lo que no toca:
nunca encola. Muertes y logros tuyos «siempre» (solo su propio enfriamiento).

Todo lo que viene del juego es texto de terceros: el nick pasa por [A-Za-z0-9_]{3,16},
los títulos y mobs se recortan sin «§» ni controles y el resultado pasa por
`neutralizar_marcadores`. Estas frases van a la burbuja, a la voz o al chat del
juego; NUNCA a un turno del modelo (minecraft.comentar_con_ia queda reservada).

`Resumen` cuenta lo tuyo mientras la mascota no está (modo juego) para decirlo al
volver: «Mientras jugabas: 2 muertes, 1 logro (Cazamonstruos).»

ÓRDENES AL BOT
--------------
`clasificar_orden(texto)`: lista blanca por verbo (sin tildes, en minúsculas). Lo que
no esté en la lista → None. «di X» (≤100) hace que el bot lo diga en el chat (saneado
allí otra vez). Las herramientas del modelo (`minecraft_estado`, `minecraft_orden`,
`minecraft_bot`) usan `ctx["minecraft"]` (ui/minecraft_qt.ControlMinecraft) y, si
viene, `ctx["en_ui"]` para correr en el hilo de Qt. La aprobación de `minecraft_orden`
(siempre) y de «conectar» la pide el Ejecutor (catalogo_herramientas).
"""
from __future__ import annotations

import random
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from lune_core.prompt import neutralizar_marcadores

EVENTOS: Tuple[str, ...] = (
    "sesion_inicio", "sesion_fin", "muerte", "logro", "conexion", "desconexion", "peligro", "dia", "noche",
    "lluvia", "bot_conectado", "bot_desconectado", "bot_muerte", "bot_mata", "bot_mineral", "bot_herida",
    "bot_nivel",
)

# Huecos: {jugador} {logro} {mob} {causa} {mineral} {nivel} {nombre}
FRASES: Dict[str, List[str]] = {
    "sesion_inicio": ["¿Minecraft? Vale, te miro.", "A ver qué construyes hoy.", "Otra partida. No te mueras mucho."],
    "sesion_fin": ["¿Ya está? Buena partida.", "Se acabó el Minecraft por hoy."],
    "muerte": ["¿Otra vez? Esa dolió hasta aquí.", "Te han matado... {causa} 1, tú 0.", "Descansa en paz. Bueno, reaparece.",
               "Eso ha sido una muerte muy tuya.", "Tranquilo, tus cosas siguen ahí. Corre."],
    "muerte_otro": ["{jugador} ha caído.", "Pobre {jugador}.", "Uno menos: {jugador}."],
    "logro": ["¡Logro! «{logro}». Me lo apunto.", "«{logro}». Nada mal.", "Mira tú: «{logro}».",
              "¡Bien! «{logro}» desbloqueado."],
    "logro_otro": ["{jugador} consiguió «{logro}».", "Anda, {jugador} con «{logro}»."],
    "conexion": ["Ha llegado {jugador}.", "Mira quién entra: {jugador}.", "Hola, {jugador}."],
    "desconexion": ["{jugador} se ha ido.", "Adiós, {jugador}."],
    "peligro": ["Cuidado, tienes un {mob} cerca.", "Ojo: {mob} al lado.", "Hay un {mob} rondando. Atento."],
    "dia": ["Amaneció. Sobreviviste.", "De día otra vez."],
    "noche": ["Se hace de noche. Ojo con lo que sale.", "Noche. Los monstruos ya están despiertos."],
    "lluvia": ["Empieza a llover.", "Lluvia en el juego. Qué ambiente."],
    "bot_conectado": ["Ya estoy dentro del mundo.", "Entré. ¿Qué hacemos?"],
    "bot_desconectado": ["Me he salido del mundo.", "Me desconecté del servidor."],
    "bot_muerte": ["Me han matado en el juego. Vuelvo enseguida.", "Morí. Que no se repita."],
    "bot_mata": ["Un {mob} menos.", "Me cargué a un {mob}."],
    "bot_mineral": ["¡Encontré {mineral}!", "Mira: {mineral}."],
    "bot_herida": ["Me están haciendo daño en el juego.", "Au. Eso dolió."],
    "bot_nivel": ["Subí a nivel {nivel}.", "Nivel {nivel}. De nada."],
}

ESTADO: Dict[str, str] = {
    "sesion_inicio": "curious", "sesion_fin": "wave", "muerte": "sad", "logro": "happy", "conexion": "wave",
    "desconexion": "wave", "peligro": "nervous", "dia": "happy", "noche": "nervous", "lluvia": "bored",
    "bot_conectado": "happy", "bot_desconectado": "neutral", "bot_muerte": "awkward", "bot_mata": "happy",
    "bot_mineral": "surprised", "bot_herida": "nervous", "bot_nivel": "happy",
}

GLOBAL_S = 4.0
ENFRIAMIENTO_S: Dict[str, float] = {
    "sesion_inicio": 60, "sesion_fin": 60, "muerte": 8, "logro": 3, "conexion": 20, "desconexion": 20,
    "peligro": 20, "dia": 60, "noche": 60, "lluvia": 60, "bot_conectado": 5, "bot_desconectado": 5,
    "bot_muerte": 20, "bot_mata": 20, "bot_mineral": 20, "bot_herida": 20, "bot_nivel": 20,
}
PROBABILIDAD: Dict[str, float] = {
    "sesion_inicio": 0.8, "sesion_fin": 0.8, "muerte": 1.0, "logro": 1.0, "conexion": 0.6, "desconexion": 0.6,
    "peligro": 1.0, "dia": 0.4, "noche": 0.4, "lluvia": 0.4, "bot_conectado": 1.0, "bot_desconectado": 1.0,
    "bot_muerte": 0.5, "bot_mata": 0.5, "bot_mineral": 0.5, "bot_herida": 0.5, "bot_nivel": 0.5,
}
SIEMPRE = frozenset({"muerte", "logro", "bot_conectado", "bot_desconectado"})   # sin la espera global

MINERALES = {"coal": "carbón", "copper": "cobre", "iron": "hierro", "gold": "oro", "redstone": "redstone",
             "lapis": "lapislázuli", "diamond": "diamantes", "emerald": "esmeraldas", "nether_quartz": "cuarzo",
             "quartz": "cuarzo", "nether_gold": "oro del Nether", "ancient_debris": "escombros ancestrales"}

_NICK = re.compile(r"[A-Za-z0-9_]{3,16}")
_ID_MC = re.compile(r"[a-z0-9_]{1,40}")
_CONTROLES = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_HUECO = re.compile(r"\{(jugador|logro|mob|causa|mineral|nivel|nombre)\}")


@dataclass(frozen=True)
class Reaccion:
    texto: str
    estado: str
    ms: int
    evento: str


def _campo(texto: Any, tope: int = 64) -> str:
    """Texto del juego (título de logro, causa…): sin «§x», controles ni marcadores."""
    t = re.sub(r"§.?", "", str(texto or ""))
    t = _CONTROLES.sub("", t)
    t = re.sub(r"[<>{}\[\]|`]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return neutralizar_marcadores(t[:tope].rstrip())


def _nick(n: Any) -> str:
    s = str(n or "").strip()
    return s if _NICK.fullmatch(s) else ""


def _mob(n: Any) -> str:
    s = str(n or "").strip().lower().replace(" ", "_")
    return s.replace("_", " ") if _ID_MC.fullmatch(s) else _campo(n, 32)


class Cadencia:
    """¿Toca reaccionar ahora a `tipo`? Descarta (nunca encola). Reloj y azar inyectables."""

    def __init__(self, reloj: Callable[[], float] = time.monotonic, rng: Any = None):
        self._reloj = reloj
        self._rng = rng if rng is not None else random.Random()
        self._ultimo_global = float("-inf")
        self._ultimo: Dict[str, float] = {}

    def admite(self, tipo: str) -> bool:
        if tipo not in ENFRIAMIENTO_S:
            return False
        t = self._reloj()
        if t - self._ultimo.get(tipo, float("-inf")) < ENFRIAMIENTO_S[tipo]:
            return False
        if tipo not in SIEMPRE and t - self._ultimo_global < GLOBAL_S:
            return False
        p = PROBABILIDAD.get(tipo, 1.0)
        if p < 1.0 and self._rng.random() >= p:
            return False
        self._ultimo[tipo] = t
        self._ultimo_global = t
        return True

    def reiniciar(self) -> None:
        self._ultimo_global = float("-inf")
        self._ultimo.clear()


def _pool(clave: str, personaje: Optional[Mapping]) -> List[str]:
    propias = (personaje or {}).get("frases_minecraft") if isinstance(personaje, Mapping) else None
    if isinstance(propias, Mapping):
        lista = propias.get(clave)
        if isinstance(lista, list):
            ok = [str(f)[:160] for f in lista if isinstance(f, str) and f.strip()]
            if ok:
                return ok
    return FRASES.get(clave, [])


def reaccion(ev: Any, *, personaje: Optional[Mapping] = None, rng: Any = None) -> Optional[Reaccion]:
    """La reacción a un Evento (minecraft_log.Evento o equivalente) o None si no hay frase."""
    tipo = str(getattr(ev, "tipo", "") or "")
    if tipo not in EVENTOS:
        return None
    propio = bool(getattr(ev, "propio", False))
    clave = tipo + ("_otro" if tipo in ("muerte", "logro") and not propio else "")
    pool = _pool(clave, personaje)
    if not pool:
        return None
    r = rng if rng is not None else random
    plantilla = pool[int(r.random() * len(pool)) % len(pool)]
    detalle = getattr(ev, "detalle", "")
    base_mineral = str(detalle or "").lower().replace("deepslate_", "").replace("_ore", "")
    valores = {
        "jugador": _nick(getattr(ev, "jugador", "")) or "alguien",
        "logro": _campo(detalle) or "un logro",
        "causa": _campo(detalle, 32) or "el juego",
        "mob": _mob(detalle) or "bicho",
        "mineral": MINERALES.get(base_mineral, _campo(detalle, 24) or "algo"),
        "nivel": str(int(detalle)) if str(detalle).isdigit() and len(str(detalle)) <= 4 else "otro",
        "nombre": _campo((personaje or {}).get("nombre", "Lune") if isinstance(personaje, Mapping) else "Lune", 40) or "Lune",
    }
    texto = _HUECO.sub(lambda m: valores[m.group(1)], plantilla)
    texto = neutralizar_marcadores(_CONTROLES.sub("", texto)).strip()[:200]
    if not texto:
        return None
    ms = max(4000, min(10000, 2500 + 60 * len(texto)))
    return Reaccion(texto=texto, estado=ESTADO.get(tipo, "neutral"), ms=int(ms), evento=tipo)


class Resumen:
    """Lo tuyo mientras la mascota no estaba (modo juego): muertes y logros."""

    MAX_LOGROS = 20

    def __init__(self):
        self.muertes = 0
        self.logros: List[str] = []

    def anotar(self, ev: Any) -> bool:
        tipo = getattr(ev, "tipo", "")
        if not getattr(ev, "propio", False):
            return False
        if tipo == "muerte":
            self.muertes += 1
            return True
        if tipo == "logro":
            if len(self.logros) < self.MAX_LOGROS:
                self.logros.append(_campo(getattr(ev, "detalle", "")))
            return True
        return False

    @property
    def vacio(self) -> bool:
        return not self.muertes and not self.logros

    def texto(self) -> Optional[str]:
        if self.vacio:
            return None
        partes = []
        if self.muertes:
            partes.append(f"{self.muertes} muerte" + ("" if self.muertes == 1 else "s"))
        if self.logros:
            n = len(self.logros)
            con_nombre = [x for x in self.logros if x]
            nombres = con_nombre[:3]
            s = f"{n} logro" + ("" if n == 1 else "s")
            if nombres:
                lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
                s += f" ({lista}{'…' if len(con_nombre) > 3 else ''})"
            partes.append(s)
        return neutralizar_marcadores("Mientras jugabas: " + ", ".join(partes) + ".")

    def reiniciar(self) -> None:
        self.muertes = 0
        self.logros = []


# ── Órdenes al bot (lista blanca) ──────────────────────────────────────────────

ORDENES: Tuple[str, ...] = ("sigueme", "ven", "para", "mina", "tala", "ataca", "defiendeme", "recoge", "suelta",
                            "dame", "come", "explora", "inventario", "donde estas", "vida", "mirame", "salta",
                            "baila", "di")
MAX_DI = 100
AYUDA_ORDENES = ("sígueme, ven, para, mina <bloque>, tala, ataca <mob>, defiéndeme, recoge, dame <objeto>, "
                 "come, explora, inventario, dónde estás, vida, mírame, salta, baila o «di <texto>»")

_SINONIMOS = {
    "sigueme": "sigueme", "sigue me": "sigueme", "ven conmigo": "sigueme", "acompaname": "sigueme",
    "ven": "ven", "ven aqui": "ven", "ven aca": "ven", "acercate": "ven",
    "para": "para", "parate": "para", "detente": "para", "quieta": "para", "quieto": "para", "alto": "para",
    "quedate quieta": "para", "quedate ahi": "para",
    "defiendeme": "defiendeme", "protegeme": "defiendeme",
    "recoge": "recoge", "recoge todo": "recoge", "recoge las cosas": "recoge",
    "come": "come", "come algo": "come",
    "explora": "explora", "ve a explorar": "explora", "pasea": "explora",
    "inventario": "inventario", "que llevas": "inventario", "que tienes": "inventario",
    "donde estas": "donde estas", "posicion": "donde estas", "coordenadas": "donde estas",
    "vida": "vida", "tu vida": "vida", "como estas de vida": "vida",
    "mirame": "mirame", "salta": "salta", "baila": "baila",
    "tala": "tala", "tala un arbol": "tala", "tala arbol": "tala", "tala madera": "tala",
}
_CON_ARG = {"mina": "mina", "pica": "mina", "consigue": "mina", "consigueme": "mina",
            "ataca": "ataca", "mata": "ataca",
            "tala": "tala",
            "suelta": "suelta", "tira": "suelta", "dame": "dame", "pasame": "dame"}
_PALABRA = re.compile(r"[a-z0-9_]{1,30}")


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[¡!¿?.,;:\"'«»()]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clasificar_orden(texto: Any) -> Optional[str]:
    """La orden para el bot en su forma canónica («mina 10 hierro», «sigueme», «di hola»)
    o None si no está en la lista blanca."""
    if not isinstance(texto, str):
        return None
    crudo = _CONTROLES.sub("", texto).strip()
    if not crudo or len(crudo) > 200:
        return None
    m = re.match(r"(?i)^\s*di(?:le)?\s*[:,]?\s+(.+)$", crudo)
    if m:
        dicho = re.sub(r"\s+", " ", m.group(1)).strip().lstrip("/\\ ").strip()
        dicho = neutralizar_marcadores(re.sub(r"§.?", "", dicho))
        if not dicho or len(dicho) > MAX_DI:
            return None
        return "di " + dicho
    t = _normalizar(crudo)
    if not t:
        return None
    t = re.sub(r"^(?:por favor|porfa|oye|venga)\s+", "", t)
    t = re.sub(r"\s+(?:por favor|porfa)$", "", t)
    if t in _SINONIMOS:
        return _SINONIMOS[t]
    palabras = t.split(" ")
    verbo = _CON_ARG.get(palabras[0])
    if verbo is None:
        return None
    resto = [p for p in palabras[1:] if p not in ("el", "la", "los", "las", "un", "una", "unos", "unas", "al", "a", "de")]
    if verbo == "tala" and not resto:
        return "tala"
    if not resto or len(resto) > 3 or not all(_PALABRA.fullmatch(p) for p in resto):
        return None
    if verbo == "mina" and resto[0].isdigit():
        n = max(1, min(64, int(resto[0])))
        if len(resto) < 2:
            return None
        return f"mina {n} {resto[1]}"
    return f"{verbo} {resto[0]}"


def texto_estado(estado: Mapping) -> str:
    """El estado para el modelo: sin chat de terceros, sin el servidor ni el motivo de
    una expulsión (texto del servidor)."""
    e = estado if isinstance(estado, Mapping) else {}
    bot = e.get("bot") if isinstance(e.get("bot"), Mapping) else {}
    log = e.get("log") if isinstance(e.get("log"), Mapping) else {}
    req = e.get("requisitos") if isinstance(e.get("requisitos"), Mapping) else {}
    partes = []
    if bot.get("conectado"):
        s = "Bot de Minecraft: conectado"
        nick = _nick(bot.get("nick"))
        if nick:
            s += f" como {nick}"
        datos = []
        for clave, nombre in (("vida", "vida"), ("hambre", "hambre")):
            v = bot.get(clave)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                datos.append(f"{nombre} {int(v)}/20")
        if isinstance(bot.get("dia"), bool):
            datos.append("de día" if bot.get("dia") else "de noche")
        if bot.get("lluvia") is True:
            datos.append("llueve")
        if datos:
            s += " (" + ", ".join(datos) + ")"
        partes.append(s + ".")
    elif bot.get("conectando"):
        partes.append("Bot de Minecraft: conectándose.")
    elif bot.get("instalando"):
        partes.append("Bot de Minecraft: instalándose.")
    elif not bot.get("instalado"):
        if req.get("node_ok") is False:
            partes.append("Bot de Minecraft: falta Node.js 18 o más nuevo.")
        else:
            partes.append("Bot de Minecraft: sin instalar (se instala en Ajustes → Minecraft, ~400 MB).")
    else:
        partes.append("Bot de Minecraft: desconectado." + (" Hubo un error (míralo en Ajustes → Minecraft)."
                                                         if bot.get("error") else ""))
    if e.get("reaccionar"):
        partes.append("Reacciones a la partida: activas" + (", leyendo el registro del juego." if log.get("activo")
                                                             else " (Minecraft no está abierto)."))
    else:
        partes.append("Reacciones a la partida: apagadas.")
    return " ".join(partes)


# ── Herramientas del modelo ────────────────────────────────────────────────────

def _de_ctx(ctx: Any, clave: str) -> Any:
    if ctx is None:
        return None
    v = ctx.get(clave) if isinstance(ctx, Mapping) else getattr(ctx, clave, None)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        c = ctx.get("contexto")
        v = c.get(clave) if isinstance(c, Mapping) else getattr(c, clave, None)
    return v


def _en_ui(ctx: Any, fn: Callable[[], Any]) -> Any:
    en_ui = _de_ctx(ctx, "en_ui")
    return en_ui(fn) if callable(en_ui) else fn()


Resultado = Union[str, Tuple[bool, str]]
NO_DISPONIBLE = "Minecraft no está disponible aquí."


def herramienta_estado(args: Any = None, ctx: Any = None) -> Resultado:
    """Handler de `minecraft_estado` ({})."""
    mc = _de_ctx(ctx, "minecraft")
    if mc is None or not callable(getattr(mc, "estado", None)):
        return False, NO_DISPONIBLE
    try:
        est = _en_ui(ctx, mc.estado)
    except Exception as e:
        return False, f"No pude mirar el estado: {e}"[:200]
    return texto_estado(est or {})


def herramienta_orden(args: Any = None, ctx: Any = None) -> Resultado:
    """Handler de `minecraft_orden` ({orden ≤80}): lista blanca → ControlMinecraft.orden."""
    mc = _de_ctx(ctx, "minecraft")
    if mc is None or not callable(getattr(mc, "orden", None)):
        return False, NO_DISPONIBLE
    args = args if isinstance(args, Mapping) else {}
    orden = clasificar_orden(str(args.get("orden") or "")[:80])
    if orden is None:
        return False, f"El bot no entiende esa orden. Puede: {AYUDA_ORDENES}."
    try:
        r = _en_ui(ctx, lambda: mc.orden(orden, origen="modelo"))
    except Exception as e:
        return False, f"No pude mandar la orden: {e}"[:200]
    ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (bool(r), ""))
    if not ok:
        return False, str(texto or "No pude mandar la orden al bot.")
    return "Se lo he mandado al bot (la respuesta sale en el panel de Minecraft)."


def herramienta_bot(args: Any = None, ctx: Any = None) -> Resultado:
    """Handler de `minecraft_bot` ({accion: conectar|desconectar}). Nunca instala."""
    mc = _de_ctx(ctx, "minecraft")
    if mc is None:
        return False, NO_DISPONIBLE
    args = args if isinstance(args, Mapping) else {}
    accion = str(args.get("accion") or "").strip().lower()
    if accion == "conectar":
        try:
            r = _en_ui(ctx, mc.conectar_bot)
        except Exception as e:
            return False, f"No pude conectar el bot: {e}"[:200]
        ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (bool(r), ""))
        return str(texto or "Conectando el bot…") if ok else (False, str(texto or "No pude conectar el bot."))
    if accion == "desconectar":
        try:
            ok = _en_ui(ctx, mc.desconectar_bot)
        except Exception as e:
            return False, f"No pude desconectar el bot: {e}"[:200]
        return "Desconecto el bot de Minecraft." if ok else "El bot no estaba conectado."
    return False, "Acción desconocida: usa «conectar» o «desconectar»."


__all__ = ("EVENTOS", "FRASES", "ESTADO", "PROBABILIDAD", "ENFRIAMIENTO_S", "GLOBAL_S", "SIEMPRE", "Reaccion",
           "Cadencia", "reaccion", "Resumen", "ORDENES", "clasificar_orden", "texto_estado",
           "herramienta_estado", "herramienta_orden", "herramienta_bot", "AYUDA_ORDENES")
