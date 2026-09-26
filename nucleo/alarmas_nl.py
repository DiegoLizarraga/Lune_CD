"""
nucleo/alarmas_nl.py — «Avísame en 10 minutos», «pon una alarma a las 7» → herramienta.

    detectar("avísame en 5 min que saque la pizza")
        → ("temporizador", {"segundos": 300, "texto": "saque la pizza"})
    detectar("pon una alarma a las 7:30 de lunes a viernes para el gimnasio")
        → ("alarma", {"hora": "07:30", "dias": "lmxjv", "texto": "el gimnasio"})
    detectar("recuerda que mañana tengo cita")        → None (va a la memoria)

Solo si hay una DURACIÓN o una HORA explícitas: sin ellas, «recuérdame…» sigue
siendo un recuerdo para la memoria.

ESTRICTO (revisión 4-5-6): solo una PETICIÓN clara a Lune AL PRINCIPIO de la
frase (tras relleno como «oye Lune, porfa»): avísame · recuérdame · despiértame
· pon/crea/programa una alarma/un temporizador · «temporizador de 5 min» ·
«en 10 minutos avísame». Nunca con preguntas («¿…?», cómo, cuánto, por qué,
explica… salvo «¿me puedes avisar…?»), negaciones, cancelar/quitar/borrar/
parar/cambiar una alarma, pasado («ya sonó», «se me olvidó») ni otro
dispositivo o código («en mi celular», «en python»). En la duda, None: lo
decide el modelo con su herramienta (y el turno sigue siendo suyo).

Los argumentos cumplen el esquema del
catálogo (`temporizador` {segundos, texto}, `alarma` {hora, dias, texto}); la
alarma lleva además `fecha` («AAAA-MM-DD») con «mañana», «pasado mañana» o «el
lunes»: el catálogo la ignora si no la declara (y entonces suena la próxima vez
que llegue esa hora).

Horas sin «de la mañana/tarde/noche» ni am/pm entre la 1 y las 12: se toma la
próxima que llegue desde `ahora` («a las 5» a las 14:00 → 17:00). Con un día
concreto o días de la semana, tal cual (a las 7 → 07:00). «Despiértame a las 8»
es de mañana (08:00: si ya pasó, suena mañana). «Esta mañana/tarde/noche»
califica la hora (no es «mañana»).

Sin Qt. Lo engancha servicios/tools.py:_detectar_pedido como regla 0 (integración).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from nucleo.alarmas import DIAS, MAX_TEXTO, limpiar_texto, parsear_duracion

MAX_SEGUNDOS = 90000          # el máximo del catálogo para `temporizador`

# ── Normalización (1:1 con el original, para recortar el texto de verdad) ──────


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, con la MISMA longitud que `texto`."""
    salida = []
    for c in texto:
        base = unicodedata.normalize("NFD", c)
        sin = "".join(ch for ch in base if not unicodedata.combining(ch))
        salida.append((sin[:1] or c).lower() if len(sin) >= 1 else c.lower())
    n = "".join(salida)
    return n if len(n) == len(texto) else texto.lower()


# ── Números en palabras ─────────────────────────────────────────────────────────

_UNIDADES = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
             "siete": 7, "ocho": 8, "nueve": 9}
_PALABRAS = dict(_UNIDADES)
_PALABRAS.update({
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
    "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "noventa": 90, "cien": 100,
})
_DECENAS = ("treinta", "cuarenta", "cincuenta")
_ALT_PAL = "|".join(sorted(_PALABRAS, key=len, reverse=True))
_ALT_UNI = "|".join(sorted(_UNIDADES, key=len, reverse=True))
NUM = rf"(?:\d+(?:[.,]\d+)?|(?:{'|'.join(_DECENAS)})\s+y\s+(?:{_ALT_UNI})\b|(?:{_ALT_PAL})\b)"


def _numero(txt: str) -> Optional[float]:
    t = txt.strip()
    if re.fullmatch(r"\d+(?:[.,]\d+)?", t):
        return float(t.replace(",", "."))
    m = re.fullmatch(rf"({'|'.join(_DECENAS)})\s+y\s+({_ALT_UNI})", t)
    if m:
        return float(_PALABRAS[m.group(1)] + _UNIDADES[m.group(2)])
    return float(_PALABRAS[t]) if t in _PALABRAS else None


# ── Duraciones ─────────────────────────────────────────────────────────────────

_U_H = r"(?:horas?|hrs?|hs?)"
_U_M = r"(?:minutos?|mins?|m)"
_U_S = r"(?:segundos?|segs?|s)"
_TROZO = re.compile(
    r"(?:"
    r"(?P<tres>tres\s+cuartos\s+de\s+hora)"
    r"|(?P<cuarto>(?:un\s+)?cuarto\s+de\s+hora)"
    r"|(?P<media>media\s+hora)"
    r"|(?P<reloj>\d{1,3}:\d{2}(?::\d{2})?)"
    rf"|(?:(?P<nh>{NUM})\s*)?(?P<h>{_U_H})\b(?:\s+y\s+(?P<fh>media|cuarto)\b)?"
    rf"|(?:(?P<nm>{NUM})\s*)?(?P<m>{_U_M})\b(?:\s+y\s+(?P<fm>medio)\b)?"
    rf"|(?P<ns>{NUM})\s*(?P<s>{_U_S})\b"
    r")")
_SEP_TROZO = re.compile(r"\s*(?:,|\by\b)?\s*")


def _valor_trozo(m: "re.Match") -> Optional[float]:
    if m.group("tres"):
        return 2700.0
    if m.group("cuarto"):
        return 900.0
    if m.group("media"):
        return 1800.0
    if m.group("reloj"):
        try:
            return float(parsear_duracion(m.group("reloj")))
        except ValueError:
            return None
    if m.group("h"):
        if m.group("nh") is None and not m.group("h").startswith("hora"):
            return None
        n = _numero(m.group("nh")) if m.group("nh") else 1.0
        if n is None:
            return None
        extra = {"media": 0.5, "cuarto": 0.25}.get(m.group("fh") or "", 0.0)
        return (n + extra) * 3600.0
    if m.group("m"):
        if m.group("nm") is None and not m.group("m").startswith("minuto"):
            return None
        n = _numero(m.group("nm")) if m.group("nm") else 1.0
        if n is None:
            return None
        return n * 60.0 + (30.0 if m.group("fm") else 0.0)
    if m.group("s"):
        n = _numero(m.group("ns"))
        return None if n is None else n
    return None


def leer_duracion(n: str, i: int) -> Optional[Tuple[int, int]]:
    """Duración que empieza en `n[i]` → (segundos, fin). None si no hay."""
    total = 0.0
    fin = None
    pos = i
    while True:
        m = _TROZO.match(n, pos)
        if not m or m.end() == pos:
            break
        v = _valor_trozo(m)
        if v is None:
            break
        total += v
        fin = m.end()
        sep = _SEP_TROZO.match(n, fin)
        pos = sep.end() if sep else fin
    if fin is None:
        return None
    seg = int(round(total))
    return (seg, fin) if seg >= 1 else None


# ── Petición: el disparador tiene que abrir la frase ───────────────────────────

_T_NOMBRE = r"temporizador|timer|cronometro|cuenta\s+atras|recordatorio|alarma|aviso|despertador"
_CONECTOR_DUR = re.compile(r"\s*(?:de|en|dentro\s+de|para\s+dentro\s+de|por|durante|pa)\s+")

# Relleno que puede ir delante: «oye Lune, porfa», «¿me puedes…», «quiero que…».
_RELLENO = (r"oye|oiga|lune|hey|ey|eh|hola|porfa|porfis|por\s+favor|ok|okay|vale|bueno|venga|anda|y"
            r"|(?:me\s+|nos\s+)?(?:puedes|podrias|podras)|quiero\s+que|necesito\s+que")
_INICIO = re.compile(rf"^[\W_]*(?:(?:{_RELLENO})\b[\W_]*)*")
_CORTESIA = re.compile(r"\b(?:puedes|podrias|podras)\b")       # «¿me puedes avisar…?» sí es una petición
# Verbos de aviso en imperativo (o subjuntivo tras «quiero que»); el infinitivo solo tras «me puedes…».
_P_VERBO = re.compile(
    r"(?:avisame|avisarme|avisanos|recuerdame|recordarme|recuerdanos|despiertame|despertarme|despiertanos"
    r"|llamame|llamarme|(?:me|nos)\s+(?:avises|recuerdes|despiertes|llames))\b")
_P_INFINITIVO = re.compile(r"(?:avisar|recordar|despertar)\b")
_P_PONER = re.compile(
    r"(?:pon(?:me|nos|le)?|poner(?:me|nos)?|(?:me\s+|nos\s+)?pongas|crea(?:me)?|crear(?:me)?|programa(?:me)?"
    r"|programar(?:me)?|configura(?:me)?|configurar(?:me)?|agrega(?:me)?|agregar(?:me)?|anade(?:me)?|anadir(?:me)?)"
    rf"\s+(?:(?:una?|el|la|mi|otra|otro|nueva?)\s+)?(?:{_T_NOMBRE})\b")
# «temporizador de 90 segundos», «alarma a las 7 todos los días» (el nombre solo, y detrás la duración o la hora).
_P_NOMBRE = re.compile(r"(?:una?\s+)?(?:alarma|temporizador|timer|despertador|cronometro|cuenta\s+atras)\b"
                       r"(?=\s+(?:de|para|a|al|en|por|durante)\b)")
_DESPERTAR = re.compile(r"despiert|despert")

# Lo que nunca es una petición de alarma (aunque empiece bien): mejor que lo decida el modelo.
_NO_PETICION = re.compile(
    r"\b(?:no|nunca|jamas|tampoco|ni)\b"                                               # negaciones
    r"|\b(?:como|cuanto|cuanta|cuantos|cuantas|cuando|cual|cuales|donde|quien|quienes|por\s*que"
    r"|explica\w*|funciona\w*|sirve|sabes|significa)\b"                                # preguntas
    r"|\b(?:ayer|anoche|anteayer|antier|sono|sonaron|sonado|sonaba|olvido|olvide|olvidaste|olvidaron"
    r"|puse|pusiste|puso|pusimos|pusieron|habia|habias)\b"                             # pasado
    r"|\b(?:celular|movil|telefono|smartphone|iphone|android|ipad|tablet|tableta|smartwatch|alexa|siri"
    r"|cortana|python|javascript|java|html|css|excel|arduino|codigo|script|programacion)\b"
    r"|\bgoogle\s+home\b|\ben\s+(?:mi|el|tu|su)\s+reloj\b")                          # otro dispositivo o código
_CANCELAR = re.compile(
    r"\b(?:cancel|quit|borr|elimin|desactiv|deten|detien|paus|pospon|posterg|anul|cambi|modific|edit|muev"
    r"|mover|retras|adelant|apag)\w*(?:\s+\w+){0,3}?"
    rf"\s+(?:(?:{_T_NOMBRE})\b|(?:la|el|las|los)\s+del?\b)"
    rf"|\bpar(?:a|ar|e|en)\s+(?:de\s+sonar|(?:el|la|los|las|mi|mis|ese|esa|este|esta)\s+(?:{_T_NOMBRE}))\b")
_QUE_TILDE = re.compile(r"(?<!\w)(?:qué|cuál|cuánto|cuánta|cómo|dónde|cuándo|quién)(?!\w)")


def _inicio(original: str, n: str) -> Optional[Tuple[int, bool]]:
    """(posición tras el relleno, ¿hubo «me puedes…»?) o None si la frase no es una
    petición (pregunta, negación, cancelar, pasado, otro dispositivo)."""
    if _NO_PETICION.search(n) or _CANCELAR.search(n) or _QUE_TILDE.search(original.lower()):
        return None
    rel = _INICIO.match(n)
    pos = rel.end() if rel else 0
    cortesia = bool(_CORTESIA.search(n[:pos]))
    if re.search(r"[¿?]", original) and not cortesia:
        return None                                       # una pregunta que no es «¿me puedes…?»
    return pos, cortesia


def _disparador(n: str, pos: int, cortesia: bool) -> Optional[Tuple[int, int]]:
    """El tramo del disparador que abre la frase en `pos`, o None."""
    for patron in (_P_VERBO, _P_PONER, _P_NOMBRE):
        m = patron.match(n, pos)
        if m:
            return m.span()
    if cortesia:
        m = _P_INFINITIVO.match(n, pos)
        if m:
            return m.span()
    return None

# Hora: «a las 7», «para las 7:30», «a la una y media», «a las 8 menos cuarto», «a las 19h»
_HORA_PAL = "una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce"
_MIN_PAL = "cinco|diez|veinte|veinticinco|quince"
_RE_HORA = re.compile(
    rf"\b(?:a|para|sobre)\s+la(?:s)?\s+(?P<h>\d{{1,2}}|{_HORA_PAL})\b"
    r"(?:\s*(?::|\.|h)\s*(?P<m>\d{2})\b"
    rf"|\s+y\s+(?P<fr>media|cuarto|\d{{1,2}}|{_MIN_PAL})(?:\s+minutos?)?\b"
    rf"|\s+menos\s+(?P<me>cuarto|\d{{1,2}}|{_MIN_PAL})(?:\s+minutos?)?\b)?"
    r"(?:\s*(?P<suf>a\.?\s?m\.?|p\.?\s?m\.?|am|pm)(?=\W|$))?"
    r"(?:\s*(?:hrs|horas|h)\b)?"
    r"(?:\s+(?:en\s+punto)\b)?")
_RE_MEDIODIA = re.compile(r"\b(?:al|a|para el)\s+mediodia\b|\ba\s+(?:la\s+)?medianoche\b")
_RE_CALIF = re.compile(
    r"\b(?:de|por|en)\s+la\s+(?P<c>manana|madrugada|tarde|noche)\b|\bdel\s+mediodia\b"
    r"|\btodas\s+las\s+(?P<c2>mananas|tardes|noches)\b"
    r"|\besta\s+(?P<c3>manana|tarde|noche)\b")          # «esta mañana a las 11» no es «mañana»

_DIA_N = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "sabados": 5,
          "domingo": 6, "domingos": 6}
_ALT_DIA = "lunes|martes|miercoles|jueves|viernes|sabados?|domingos?"
_RE_TODOS = re.compile(r"\b(?:todos\s+los\s+dias|cada\s+dia|diariamente|a\s+diario|todas\s+las\s+"
                       r"(?:mananas|tardes|noches))\b")
_RE_LABORABLES = re.compile(r"\b(?:entre\s+semana|(?:los\s+)?dias\s+(?:laborables|de\s+semana|de\s+diario)"
                            r"|(?:los\s+)?laborables)\b")
_RE_FINDE = re.compile(r"\b(?:(?:los|cada|todos\s+los)\s+fines?\s+de\s+semana)\b")
_RE_RANGO = re.compile(rf"\bde\s+(?P<a>{_ALT_DIA})\s+a\s+(?P<b>{_ALT_DIA})\b")
_RE_LISTA = re.compile(rf"\b(?:los|cada|todos\s+los)\s+(?P<l>(?:{_ALT_DIA})(?:\s*(?:,|y)\s*(?:los\s+)?(?:{_ALT_DIA}))*)\b")
_RE_UN_DIA = re.compile(rf"\b(?:el|este|el\s+proximo|el\s+siguiente|este\s+proximo)\s+(?P<d>{_ALT_DIA})\b")
_RE_PASADO = re.compile(r"\bpasado\s+manana\b")
_RE_MANANA = re.compile(r"(?<!la )(?<!esta )\bmanana\b")
_RE_HOY = re.compile(r"\bhoy\b")

_CONECTORES_INICIO = re.compile(r"^(?:\W|que|de\s+que|para\s+que|para|pa|a|de|y|por\s+favor|porfa)+\b\W*")
_FIN = re.compile(r"[\s,.;:!?¡¿…\-]+$")


def _quitar(original: str, tramos: List[Tuple[int, int]]) -> str:
    """El original sin los tramos (se juntan con un espacio)."""
    partes = []
    pos = 0
    for a, b in sorted(tramos):
        if a < pos:
            a = pos
        if a > pos:
            partes.append(original[pos:a])
        pos = max(pos, b)
    partes.append(original[pos:])
    return " ".join(p.strip() for p in partes if p.strip())


def _limpiar(texto: str) -> str:
    """Quita conectores del principio («que», «para», «de»…) y signos del final."""
    t = texto.strip()
    for _ in range(3):
        n = _normalizar(t)
        m = _CONECTORES_INICIO.match(n)
        if not m or not m.end():
            break
        t = t[m.end():].lstrip()
    t = _FIN.sub("", t).strip()
    t = re.sub(r"^[¿¡\s]+", "", t)
    return limpiar_texto(t, MAX_TEXTO)


# ── Temporizador ───────────────────────────────────────────────────────────────

def _detectar_temporizador(original: str, n: str, inicio: int,
                           disp: Optional[Tuple[int, int]]) -> Optional[Tuple[str, dict]]:
    if disp is not None:
        # 1) disparador + (de|en|dentro de…) + duración + resto
        pos = disp[1]
        con = _CONECTOR_DUR.match(n, pos)
        if con:
            d = leer_duracion(n, con.end())
            if d:
                seg, fin = d
                texto = _limpiar(original[fin:])
                return _temporizador(seg, texto)
        # 2) disparador + texto + (en|dentro de) + duración al final
        for m in re.finditer(r"\s(?:en|dentro\s+de)\s+", n[pos:]):
            ini = pos + m.end()
            d = leer_duracion(n, ini)
            if not d:
                continue
            seg, fin = d
            if _FIN.sub("", n[fin:]).strip():
                continue
            if re.search(r"\ba\s+las?\s+\d|\ba\s+las?\s+(?:" + _HORA_PAL + r")\b", n[pos:pos + m.start()]):
                return None                                  # es una hora: lo mira la alarma
            texto = _limpiar(original[pos:pos + m.start()])
            return _temporizador(seg, texto)
        return None
    # 3) «en 10 minutos avísame (que …)»
    m = re.compile(r"(?:en|dentro\s+de)\s+").match(n, inicio)
    if m:
        d = leer_duracion(n, m.end())
        if d:
            seg, fin = d
            verbo = re.compile(r"\s*,?\s*").match(n, fin)
            v = _P_VERBO.match(n, verbo.end())
            if v:
                texto = _limpiar(original[v.end():])
                return _temporizador(seg, texto)
    return None


def _temporizador(seg: int, texto: str) -> Optional[Tuple[str, dict]]:
    if not 1 <= seg <= MAX_SEGUNDOS:
        return None
    return "temporizador", {"segundos": int(seg), "texto": texto}


# ── Alarma ─────────────────────────────────────────────────────────────────────

def _hora_num(txt: str) -> Optional[int]:
    if txt.isdigit():
        return int(txt)
    return {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
            "nueve": 9, "diez": 10, "once": 11, "doce": 12}.get(txt)


def _min_num(txt: str) -> Optional[int]:
    if txt.isdigit():
        return int(txt)
    return {"cinco": 5, "diez": 10, "quince": 15, "veinte": 20, "veinticinco": 25,
            "media": 30, "cuarto": 15}.get(txt)


def _leer_hora(n: str) -> Optional[Tuple[int, int, bool, Tuple[int, int]]]:
    """(h, m, ambigua, tramo) de la primera hora del texto."""
    m = _RE_HORA.search(n)
    if m is None:
        mm = _RE_MEDIODIA.search(n)
        if mm is None:
            return None
        return (0 if "medianoche" in mm.group(0) else 12), 0, False, mm.span()
    h = _hora_num(m.group("h"))
    if h is None:
        return None
    mi = 0
    ambigua = True
    if m.group("m"):
        mi = int(m.group("m"))
    elif m.group("fr"):
        v = _min_num(m.group("fr"))
        if v is None:
            return None
        mi = v
    elif m.group("me"):
        v = _min_num(m.group("me"))
        if v is None or v >= 60:
            return None
        h, mi = (h - 1) % 24, 60 - v
        if h == 0 and m.group("h") in ("1", "una"):
            h = 12
    suf = (m.group("suf") or "").replace(".", "").replace(" ", "")
    if suf:
        if not 1 <= h <= 12:
            return None
        h = (h % 12) + (12 if suf == "pm" else 0)
        ambigua = False
    elif h == 0 or h > 12:
        ambigua = False
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return h, mi, ambigua, m.span()


def _calificar(h: int, calif: str) -> int:
    if calif in ("tarde", "tardes"):
        return h + 12 if 1 <= h <= 11 else h
    if calif in ("noche", "noches"):
        if h == 12:
            return 0
        return h + 12 if 7 <= h <= 11 else h
    if calif == "madrugada":
        return 0 if h == 12 else h
    if calif == "mediodia":
        return 12 if h == 12 else (h + 12 if 1 <= h <= 4 else h)
    return h                                            # mañana(s): tal cual


def _dias(n: str, ahora: datetime) -> Tuple[str, Optional[str], List[Tuple[int, int]]]:
    """(letras de días repetidos, fecha única, tramos a quitar)."""
    tramos: List[Tuple[int, int]] = []
    m = _RE_TODOS.search(n)
    if m:
        tramos.append(m.span())
        return DIAS, None, tramos
    m = _RE_RANGO.search(n)
    if m:
        a, b = _DIA_N[m.group("a")], _DIA_N[m.group("b")]
        letras = ""
        i = a
        while True:
            letras += DIAS[i]
            if i == b:
                break
            i = (i + 1) % 7
        tramos.append(m.span())
        return "".join(c for c in DIAS if c in letras), None, tramos
    m = _RE_LABORABLES.search(n)
    if m:
        tramos.append(m.span())
        return "lmxjv", None, tramos
    m = _RE_FINDE.search(n)
    if m:
        tramos.append(m.span())
        return "sd", None, tramos
    m = _RE_LISTA.search(n)
    if m:
        dias = {DIAS[_DIA_N[d]] for d in re.findall(_ALT_DIA, m.group("l"))}
        tramos.append(m.span())
        return "".join(c for c in DIAS if c in dias), None, tramos
    m = _RE_PASADO.search(n)
    if m:
        tramos.append(m.span())
        return "", (ahora.date() + timedelta(days=2)).isoformat(), tramos
    m = _RE_MANANA.search(n)
    if m:
        tramos.append(m.span())
        return "", (ahora.date() + timedelta(days=1)).isoformat(), tramos
    m = _RE_UN_DIA.search(n)
    if m:
        objetivo = _DIA_N[m.group("d")]
        delta = (objetivo - ahora.weekday()) % 7 or 7
        tramos.append(m.span())
        return "", (ahora.date() + timedelta(days=delta)).isoformat(), tramos
    m = _RE_HOY.search(n)
    if m:
        tramos.append(m.span())
    return "", None, tramos


def _detectar_alarma(original: str, n: str, ahora: datetime,
                     disp: Optional[Tuple[int, int]]) -> Optional[Tuple[str, dict]]:
    if disp is None:
        return None
    hora = _leer_hora(n)
    if hora is None or hora[3][0] < disp[1]:
        return None
    h, mi, ambigua, tramo_hora = hora
    tramos = [(0, disp[1]), tramo_hora]                 # el relleno y el disparador, fuera del texto
    calif = ""
    c = _RE_CALIF.search(n)
    if c:
        calif = c.group("c") or c.group("c2") or c.group("c3") or "mediodia"
        tramos.append(c.span())
    letras, fecha, tramos_dias = _dias(n, ahora)
    tramos.extend(tramos_dias)
    if ambigua and calif:
        h = _calificar(h, calif)
        ambigua = False
    if ambigua and _DESPERTAR.search(n[disp[0]:disp[1]]):
        # «Despiértame a las 8» es por la mañana (si ya pasó hoy, suena mañana).
        ambigua = False
    if ambigua and not letras and not fecha:
        # «a las 5» sin más: la próxima 5 que llegue (05:00 o 17:00).
        cands = sorted({h % 12, (h % 12) + 12})
        minuto_ahora = ahora.hour * 60 + ahora.minute
        futuras = [x for x in cands if x * 60 + mi > minuto_ahora]
        h = futuras[0] if futuras else cands[0]
    elif ambigua and h == 12 and not calif:
        h = 12
    texto = _limpiar(_quitar(original, tramos))
    args: Dict[str, str] = {"hora": f"{h:02d}:{mi:02d}", "dias": letras, "texto": texto}
    if fecha:
        args["fecha"] = fecha
    return "alarma", args


# ── API ─────────────────────────────────────────────────────────────────────────

def detectar(texto: str, ahora: Optional[datetime] = None) -> Optional[Tuple[str, dict]]:
    """("temporizador", {segundos, texto}) | ("alarma", {hora, dias, texto[, fecha]}) | None.

    None si no hay una hora ni una duración explícitas, o si la frase no es una
    petición clara a Lune al principio (lo demás sigue su camino: memoria,
    comandos, el modelo con su herramienta)."""
    original = str(texto or "").strip()
    if not original or len(original) > 300:
        return None
    n = _normalizar(original)
    if not re.search(r"\d|\b(?:" + _ALT_PAL + r"|media|cuarto|mediodia|medianoche)\b", n):
        return None
    ahora = ahora or datetime.now()
    try:
        ini = _inicio(original, n)
        if ini is None:
            return None
        pos, cortesia = ini
        disp = _disparador(n, pos, cortesia)
        r = _detectar_temporizador(original, n, pos, disp)
        if r is not None:
            return r
        return _detectar_alarma(original, n, ahora, disp)
    except Exception:
        return None


__all__ = ("detectar", "leer_duracion")
