"""
lune_core/minecraft_log.py — Lo que pasa en tu partida de Minecraft, leído de
`latest.log`. Sin Qt: se prueba en seco.

CÓMO SE LEE (anticheat)
-----------------------
Solo es un ARCHIVO: nada de hooks, ni handles al proceso del juego, ni memoria
ajena. `LectorLog.poll()` se llama por sondeo (cada 1 s desde ui/minecraft_qt.py):
abre, busca donde se quedó, lee lo nuevo (≤256 KB) y cierra. No deja el archivo
abierto, así no bloquea la rotación de log4j (al arrancar el juego, latest.log se
renombra y se crea otro).

- Arranque: no se cuentan los eventos viejos. Se busca el último «Setting user: X»
  (quién eres) al principio del archivo y se salta al final. Salvo si se retoma
  (`instantanea()` / `retomar()`): quien suelta el lector tras 10 min sin cambios y
  vuelve a abrir el MISMO archivo sigue donde se quedó.
- Archivo más pequeño que lo leído o archivo distinto (rotación) → sesión nueva:
  se lee desde 0.
- La línea a medio escribir del final se guarda para el siguiente sondeo.
- UTF-8 con respaldo cp1252 por línea (el lanzador de Windows a veces escribe así).
- Líneas de más de 2 KB se ignoran.

QUÉ SE RECONOCE (1.20.1–1.21.x, en español y en inglés)
-------------------------------------------------------
Anclado en «]: », con «[System]» y «[Not Secure]» opcionales y «[CHAT] ». Los
patrones salen de los textos REALES del juego (es_es, es_mx y las demás variantes
es_* de 1.20.1 a 1.21.11, y en_us), con y sin tildes:
- muerte: las de es_mx y el resto de América («fue asesinado/a por», «fue
  disparado(a) por», «se ahogó», «murió»…: el juego escribe «/a» u «(a)» literal),
  las de es_es («ha sido víctima de», «ha muerto por un flechazo de», «se ha
  ahogado», «A X le ha caído un yunque», «Y ha tirado a X desde muy alto»…) y las
  inglesas («was slain by», «drowned», «fell from», «blew up», «died»…). El detalle
  es quién te mató (sin el arma) cuando el texto lo dice;
- logro («ha conseguido el progreso [X]», «completó el desafío [X]», «ha
  alcanzado el objetivo [X]», «acaba de conseguir el progreso [X]»… / «has made
  the advancement», «has completed the challenge», «has reached the goal»);
- conexion / desconexion («se ha unido a la partida», «se conectó», «ha abandonado
  la partida», «se desconectó», «joined/left the game», también con «(antes
  conocido como Y)»).
Fuera del chat: «Setting user: X» → quién eres; «Connecting to …» o «Starting
integrated minecraft server» → sesion_inicio (sin la IP); «Stopping!» o «Stopping
server» → sesion_fin.

El chat de jugadores («<nick> …») NUNCA genera eventos, y nada de este texto entra
en un turno del modelo: son reacciones con frases fijas (lune_core/minecraft.py).
El nick del bot de Lune nunca cuenta como «yo» (sus cosas llegan por el bot).
Muertes y logros: los tuyos siempre; los de otros solo con `otros=True`
(config minecraft.reaccionar_otros). Conexiones: siempre las de los demás.

Privacidad: el nick y lo que se lee se quedan en memoria; nada va a los logs de Lune.
"""
from __future__ import annotations

import dataclasses
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Mapping, Optional

MAX_LECTURA = 256 * 1024
MAX_LINEA = 2048
MAX_ARRANQUE = 1024 * 1024          # lo que se mira al principio buscando «Setting user»
MAX_CANDIDATAS = 64
NOMBRE_LOG = "latest.log"

_NICK = r"[A-Za-z0-9_]{3,16}"
_CABECERA = re.compile(r"\]:\s?(.*)$")
_CHAT = re.compile(r"^(?:\[(?:System|Not Secure)\]\s*)*\[CHAT\]\s?(?:\[(?:System|Not Secure)\]\s*)*(.*)$")
_USUARIO = re.compile(r"^Setting user:\s*([A-Za-z0-9_]{1,16})\s*$")
_SESION_INICIO = re.compile(r"^(?:Connecting to \S|Starting integrated minecraft server\b)")
_SESION_FIN = re.compile(r"^Stopping(?:!| server)\s*$")
_COLOR = re.compile(r"§.?")
_CONTROLES = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")

_VOCALES = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]",
            "á": "[aá]", "é": "[eé]", "í": "[ií]", "ó": "[oó]", "ú": "[uúü]"}


def _flex(fuente: str) -> str:
    """Un trozo de regex escrito como lo escribe el juego → acepta cada vocal con o sin
    tilde («murió» casa con «murio»). Los trozos no llevan clases [..]: el sufijo de los
    participios va aparte ({P})."""
    return "".join(_VOCALES.get(c, c) for c in fuente)


# «asesinado», «asesinada», «asesinado/a», «asesinado(a)»: el juego escribe el «/a» literal.
_P = r"(?:o|a)(?:/a|\(a\))?"
_PARTICIPIOS = (
    "alcanzad|aniquilad|aplastad|arrasad|asesinad|atravesad|borrad|calcinad|condenad|congelad|detonad|"
    "disparad|electrocutad|empalad|empujad|ensartad|espetad|explotad|golpead|impactad|matad|obliterad|"
    "perforad|picad|pinchad|quemad|rematad|reducid|reventad|rostizad|volad")
_FIN = r"(?!\w)"                       # fin de palabra (con «o(a)» \b no sirve)

_LOGRO = re.compile(
    r"^(" + _NICK + r") (?:has made the advancement|has completed the challenge|has reached the goal|"
    + _flex(r"(?:ha conseguido|consiguió|acaba de conseguir|ha obtenido) el (?:progreso|logro)|"
            r"(?:ha completado|completó|acaba de completar) el desafío|"
            r"(?:ha alcanzado|alcanzó|acaba de alcanzar) (?:el objetivo|la meta)")
    + r") \[(.{1,64}?)\]\s*$", re.IGNORECASE)
_ANTES = r"(?: \((?:antes conocido como|formerly known as) [^()]{1,40}\))?"
_CONEXION = re.compile(
    r"^(" + _NICK + r")" + _ANTES + r" (?:joined the game|"
    + _flex(r"se ha unido a la partida|se unió a la partida|se ha conectado|se conectó") + r")\s*$", re.IGNORECASE)
_DESCONEXION = re.compile(
    r"^(" + _NICK + r") (?:left the game|"
    + _flex(r"ha abandonado la partida|abandonó la partida|salió de la partida|se ha desconectado|"
            r"se desconectó") + r")\s*$", re.IGNORECASE)

# Muertes con la víctima delante: «<nick> <frase>…». Sacadas de los textos del juego.
_FRASES_MUERTE_EN = (
    "was slain by", "was shot by", "was killed", "was blown up by", "blew up", "drowned",
    "fell from", "fell off", "fell out of the world", "fell while climbing", "fell too far",
    "hit the ground too hard", "burned to death", "was burned to a crisp", "was burnt to a crisp",
    "went up in flames", "walked into fire", "walked into a cactus", "walked into the danger zone",
    "tried to swim in lava", "starved to death", "suffocated in a wall", "was struck by lightning",
    "froze to death", "was frozen to death", "was pricked to death", "was poked to death", "withered away",
    "was squashed", "was squished", "was impaled", "was skewered", "was fireballed by", "was stung to death",
    "was pummeled by", "was smashed by", "was speared by", "was roasted in dragon's breath",
    "experienced kinetic energy", "was obliterated", "discovered the floor was lava", "was doomed to fall",
    "went off with a bang", "left the confines of this world", "didn't want to live in the same world as",
    "died",
)
_FRASES_MUERTE_ES = tuple(_flex(f).replace("{P}", _P) for f in (
    # es_mx y el resto de América: «fue <participio>» (con «o», «a», «o/a» u «o(a)»)
    "fue (?:" + _PARTICIPIOS + "){P}", "fue víctima de",
    # es_es: «ha sido <participio>», «ha muerto…»
    "ha sido (?:" + _PARTICIPIOS + "){P}", "ha sido víctima de",
    "se ha muerto", "ha muerto", "se murió", "murió",
    "se ha ahogado", "se ahogó", "se ha asfixiado", "se asfixió", "se sofocó",
    "se ha calcinado", "se asó en", "se ha quemado", "se quemó", "se prendió fuego",
    "ha ardido", "ardió",
    "ha explotado", "explotó", "ha estallado", "reventó", "ha pegado un estallido",
    "voló con fuegos artificiales", "se fue con un bang", "se convirtió en un fuego artificial",
    "se ha convertido en fuegos artificiales",
    "se ha caído", "se cayó", "ha caído (?:de|desde)", "cayó (?:a|de|del|desde|fuera|demasiado)",
    "se ha estampado contra", "se golpeó", "se dio con", "se dio contra", "se chocó contra", "chocó contra el piso",
    "ha experimentado la energía cinética", "experimentó la energía cinética",
    "ha intentado nadar en", "intentó nadar en", "trató de nadar en",
    "ha descubierto que el suelo era lava", "descubrió que el (?:suelo|piso) era lava",
    "ha pisado (?:un cactus|una zona de peligro)",
    "caminó (?:cerca de un cactus|en fuego|hacia el fuego|hacia un cactus|por la zona peligrosa|sobre una zona peligrosa)",
    "ha recibido (?:una paliza|un empujón)",
    "recibió (?:la ira de|un proyectil|un tiro|una bola de fuego|una piña)",
    "ha sufrido una gran presión", "sufrió (?:hambruna|la ira del wither|una caída)",
    "(?:ha abandonado|abandona|abandonó|dejó) los (?:bordes|confines)", "salió de los límites del mundo",
    "no (?:quería|volverá a) vivir en el mismo mundo", "metió la pata",
    "se congeló", "se ha descompuesto", "se descompuso", "se ha reducido a cenizas", "se redujo a cenizas",
    "se pinchó", "se quedó pegado a un cactus",
))
_MUERTE = re.compile(r"^(" + _NICK + r") (" + "|".join(_FRASES_MUERTE_EN + _FRASES_MUERTE_ES) + r")" + _FIN
                     + r"(?: (.*))?$", re.IGNORECASE)
# es_es: «A <nick> le ha caído un yunque / un bloque / un rayo…» (y «le cayó un rayo»).
_MUERTE_A = re.compile(r"^" + _flex("A") + r" (" + _NICK + r") " + _flex(r"le (?:ha caído|cayó) un (?:yunque|bloque|rayo)")
                       + _FIN + r"(?: (.*))?$", re.IGNORECASE)
# Quien mata delante: «<quien> ha tirado a <nick> desde muy alto» (es_es), «<quien> hizo
# explotar a <nick>», «<quien> mandó a volar a <nick> con su [X]» (América).
_MUERTE_POR = re.compile(r"^(.{1,40}?) (?:" + _flex(r"ha tirado a") + r" (" + _NICK + r") " + _flex("desde muy alto")
                         + r"|" + _flex(r"(?:hizo explotar|mandó a volar) a") + r" (" + _NICK + r"))" + _FIN
                         + r"(?: (.*))?$", re.IGNORECASE)
# El arma del final («con su [X]», «usando [X]»…; en el chat va entre corchetes) no es
# quién te mató; tampoco la coletilla que algunas variantes ponen detrás.
_ARMA = re.compile(_flex(r"\s+(?:con su|y su|con|usando|utilizando|equipado con|empuñando|using|wielding|with)\s+\[.*$|"
                         r"\s+(?:con su|y su|usando|utilizando|equipado con|empuñando|using|wielding)\s+.*$"),
                   re.IGNORECASE)
_COLA = re.compile(_flex(r"\s+(?:de un lugar muy alto|desde muy alto|con una bola de fuego|mientras|while|whilst)\b.*$"),
                   re.IGNORECASE)
# Lo que va justo antes de quien mata. Gana el ÚLTIMO del texto («ha muerto por un flechazo de
# Esqueleto» → Esqueleto; «…disparado desde [X] por Steve» → Steve). Las frases largas van
# antes que «por»/«by» sueltos (si no, «por culpa de» se quedaría en «por»).
_ANTES_DEL_ASESINO = re.compile(
    r"(?<!\w)(?:" + _flex(
        r"víctima de|flechazo de|disparo de|tiro de|mazazo de|picadura de|paliza de|calavera de|cráneo de|"
        r"bola de fuego de|aliento de dragón de|aliento del dragón de|proyectil del wither de|piña de|la magia de|"
        r"huir de|escapar de|escapaba de|por culpa de|debido a|a causa de|luchaba contra|luchaba con|"
        r"peleaba contra|peleaba con|luchando contra|golpear a|atacar a|pegarle a|mismo mundo que|por un\(a\)") +
    r"|\bescape|\bfighting|\bhurt|\bdue to|\bbecause of|\bsame world as|\bskull from|\bby|\b" + _flex("por") + r")\s+",
    re.IGNORECASE)


def _asesino(resto: str) -> str:
    """Quién te mató según el texto de la muerte (sin el arma), o ''."""
    r = _ARMA.sub("", resto or "")
    ultimo = None
    for ultimo in _ANTES_DEL_ASESINO.finditer(r):
        pass
    return _COLA.sub("", r[ultimo.end():]).strip()[:40] if ultimo is not None else ""


@dataclass(frozen=True)
class Evento:
    tipo: str
    jugador: str = ""
    detalle: str = ""
    t: float = 0.0
    fuente: str = "log"
    propio: bool = False            # es tuyo (jugador == «yo»), no de otro


def _limpio(texto: Any, tope: int = 64) -> str:
    t = _COLOR.sub("", str(texto or ""))
    t = _CONTROLES.sub("", t.replace("§", ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:tope].rstrip()


def _mismo(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.lower() == b.lower()


def parsear_linea(linea: Any, yo: str, nombre_bot: str = "", *, otros: bool = False) -> Optional[Evento]:
    """Una línea de latest.log → Evento o None (ver el docstring del módulo).

    Tipos: muerte, logro, conexion, desconexion, sesion_inicio, sesion_fin y el interno
    `usuario` (el «Setting user», que LectorLog usa para saber quién eres)."""
    if not isinstance(linea, str) or len(linea) > MAX_LINEA:
        return None
    m = _CABECERA.search(linea.rstrip("\r\n"))
    if not m:
        return None
    resto = m.group(1).strip()
    c = _CHAT.match(resto)
    if c is None:
        u = _USUARIO.match(resto)
        if u:
            return Evento("usuario", u.group(1))
        if _SESION_INICIO.match(resto):
            return Evento("sesion_inicio")
        if _SESION_FIN.match(resto):
            return Evento("sesion_fin")
        return None
    texto = _limpio(c.group(1), 400)
    if not texto or texto.startswith("<"):
        return None                                  # chat de un jugador: nunca eventos

    def filtro(tipo: str, jugador: str, detalle: str = "") -> Optional[Evento]:
        if _mismo(jugador, nombre_bot):
            return None                              # lo del bot llega por el bot
        propio = _mismo(jugador, yo)
        if tipo in ("muerte", "logro"):
            if not propio and not otros:
                return None
        elif propio:
            return None                              # tu propia conexión es el inicio de sesión
        return Evento(tipo, jugador, _limpio(detalle), propio=propio)

    x = _LOGRO.match(texto)
    if x:
        return filtro("logro", x.group(1), x.group(2))
    x = _CONEXION.match(texto)
    if x:
        return filtro("conexion", x.group(1))
    x = _DESCONEXION.match(texto)
    if x:
        return filtro("desconexion", x.group(1))
    x = _MUERTE.match(texto)
    if x:
        return filtro("muerte", x.group(1), _asesino(x.group(2) + " " + (x.group(3) or "")))
    x = _MUERTE_A.match(texto)
    if x:
        return filtro("muerte", x.group(1), _asesino(x.group(2) or ""))
    x = _MUERTE_POR.match(texto)
    if x:
        return filtro("muerte", x.group(2) or x.group(3), x.group(1).strip()[:40])
    return None


def _decodificar(crudo: bytes) -> str:
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("cp1252", errors="replace")


class LectorLog:
    """Sondeo de un latest.log (ver el docstring del módulo)."""

    def __init__(self, ruta: Any, *, abrir: Callable[..., Any] = open, ahora: Callable[[], float] = time.time,
                 nombre_bot: str = "", otros: bool = False):
        self.ruta = Path(ruta)
        self._abrir = abrir
        self._ahora = ahora
        self.nombre_bot = str(nombre_bot or "")
        self.otros = bool(otros)
        self.yo = ""
        self.offset = 0
        self._pendiente = b""
        self._iniciado = False
        self._id: Any = None
        self.ultimo_cambio = ahora()
        self.error = ""

    def inactivo_s(self) -> float:
        """Segundos sin que el archivo crezca."""
        return max(0.0, self._ahora() - self.ultimo_cambio)

    def instantanea(self) -> dict:
        """Dónde se quedó (para retomar el MISMO archivo con otro lector tras soltarlo por
        inactividad: sin esto el nuevo saltaría al final y perdería lo que lo despertó)."""
        return {"ruta": str(self.ruta), "offset": max(0, self.offset - len(self._pendiente)), "id": self._id,
                "yo": self.yo, "iniciado": self._iniciado}

    def retomar(self, foto: Any) -> bool:
        """Sigue desde `instantanea()` si es de este mismo archivo. Si entretanto rotó o se
        truncó, el primer sondeo lo verá y leerá la sesión nueva desde 0."""
        if not isinstance(foto, dict) or not foto.get("iniciado") or str(foto.get("ruta")) != str(self.ruta):
            return False
        try:
            offset = int(foto.get("offset") or 0)
        except (TypeError, ValueError):
            return False
        self.offset = max(0, offset)
        self._id = foto.get("id")
        self.yo = str(foto.get("yo") or "")
        self._pendiente = b""
        self._iniciado = True
        return True

    @staticmethod
    def _tam_e_id(f: Any):
        try:
            st = os.fstat(f.fileno())
            ident = (st.st_ino, st.st_dev) if st.st_ino else None
            return st.st_size, ident
        except (AttributeError, OSError, ValueError):
            f.seek(0, 2)
            return f.tell(), None

    def _buscar_usuario(self, f: Any, tam: int) -> None:
        f.seek(0)
        bloque = f.read(min(tam, MAX_ARRANQUE))
        for crudo in bloque.split(b"\n"):
            if b"Setting user" not in crudo or len(crudo) > MAX_LINEA:
                continue
            ev = parsear_linea(_decodificar(crudo.rstrip(b"\r")), "")
            if ev is not None and ev.tipo == "usuario":
                self.yo = ev.jugador

    def poll(self) -> List[Evento]:
        """Abre, lee lo nuevo (≤256 KB), cierra. → eventos nuevos (sin el interno `usuario`)."""
        try:
            f = self._abrir(self.ruta, "rb")
        except OSError as e:
            self.error = str(e)[:200]
            return []
        self.error = ""
        with f:
            tam, ident = self._tam_e_id(f)
            if not self._iniciado:
                self._buscar_usuario(f, tam)
                self.offset = tam
                self._pendiente = b""
                self._id = ident
                self._iniciado = True
                return []
            if (ident is not None and self._id is not None and ident != self._id) or tam < self.offset:
                # Rotación o truncado: sesión nueva desde 0 (su «Setting user» dirá quién eres).
                self.offset = 0
                self._pendiente = b""
                self.yo = ""
            self._id = ident
            if tam == self.offset:
                return []
            f.seek(self.offset)
            datos = f.read(min(MAX_LECTURA, tam - self.offset))
        if not datos:
            return []
        self.offset += len(datos)
        self.ultimo_cambio = self._ahora()
        trozos = (self._pendiente + datos).split(b"\n")
        self._pendiente = trozos.pop()
        if len(self._pendiente) > MAX_LINEA:
            self._pendiente = b""                    # una línea gigante sin fin: fuera
        eventos: List[Evento] = []
        t = self._ahora()
        for crudo in trozos:
            crudo = crudo.rstrip(b"\r")
            if not crudo or len(crudo) > MAX_LINEA:
                continue
            ev = parsear_linea(_decodificar(crudo), self.yo, self.nombre_bot, otros=self.otros)
            if ev is None:
                continue
            if ev.tipo == "usuario":
                self.yo = ev.jugador
                continue
            eventos.append(dataclasses.replace(ev, t=t))
        return eventos


# ── Dónde está latest.log ──────────────────────────────────────────────────────

def _es_unc(s: str) -> bool:
    return s.startswith("\\\\") or s.startswith("//")


def ruta_valida(ruta: Any) -> Optional[Path]:
    """La ruta de la config si es un latest.log local (no UNC, no enlace). No mira si existe."""
    if not isinstance(ruta, str):
        return None
    s = ruta.strip().strip('"')
    if not s or _es_unc(s) or "\x00" in s:
        return None
    p = Path(s)
    if p.name.lower() != NOMBRE_LOG:
        return None
    try:
        if p.is_symlink():
            return None
    except OSError:
        return None
    return p


def rutas_candidatas(env: Mapping[str, str] = os.environ) -> List[Path]:
    """Los latest.log que existen en los sitios habituales (≤64): .minecraft,
    instancias de PrismLauncher/MultiMC ((.)minecraft/logs), perfiles de Modrinth (la app
    nueva y la antigua, com.modrinth.theseus) y de CurseForge."""
    out: List[Path] = []
    vistos = set()

    def meter(p: Path) -> bool:
        if len(out) >= MAX_CANDIDATAS:
            return False
        try:
            if p.is_file() and not _es_unc(str(p)):
                clave = str(p).lower()
                if clave not in vistos:
                    vistos.add(clave)
                    out.append(p)
        except OSError:
            pass
        return True

    def instancias(base: Path, subrutas: Iterable[str]) -> None:
        try:
            dirs = sorted(d for d in base.iterdir() if d.is_dir())
        except OSError:
            return
        for d in dirs[:200]:
            for sub in subrutas:
                if not meter(d / sub / "logs" / NOMBRE_LOG):
                    return

    appdata = env.get("APPDATA") or ""
    perfil = env.get("USERPROFILE") or env.get("HOME") or ""
    if appdata:
        a = Path(appdata)
        meter(a / ".minecraft" / "logs" / NOMBRE_LOG)
        for lanzador in ("PrismLauncher", "MultiMC", "PolyMC"):
            instancias(a / lanzador / "instances", (".minecraft", "minecraft"))
        instancias(a / "ModrinthApp" / "profiles", ("",))
        instancias(a / "com.modrinth.theseus" / "profiles", ("",))     # Modrinth App antigua
    if perfil:
        instancias(Path(perfil) / "curseforge" / "minecraft" / "Instances", ("",))
    return out[:MAX_CANDIDATAS]


def elegir_log(config_ruta: Any, candidatas: Iterable[Path], *, ahora: Any = None,
               reciente_s: Optional[float] = 600) -> Optional[Path]:
    """La ruta configurada (si es válida y existe; configurada y mala → None) o, sin
    configurar, la candidata con el mtime más reciente (con `reciente_s`, solo si se
    tocó en esos segundos; None = sin límite)."""
    if isinstance(config_ruta, str) and config_ruta.strip():
        p = ruta_valida(config_ruta)
        try:
            return p if p is not None and p.is_file() else None
        except OSError:
            return None
    t = ahora() if callable(ahora) else (float(ahora) if ahora is not None else time.time())
    mejor, mejor_m = None, None
    for c in candidatas:
        try:
            m = Path(c).stat().st_mtime
        except OSError:
            continue
        if reciente_s is not None and t - m > reciente_s:
            continue
        if mejor_m is None or m > mejor_m:
            mejor, mejor_m = Path(c), m
    return mejor


__all__ = ("Evento", "parsear_linea", "LectorLog", "rutas_candidatas", "elegir_log", "ruta_valida",
           "MAX_LECTURA", "MAX_LINEA", "NOMBRE_LOG")
