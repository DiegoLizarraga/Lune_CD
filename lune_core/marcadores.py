"""
lune_core/marcadores.py — Canal de control dentro del texto del modelo.

Portado de core-agent/runtime/llm-marker-parser.ts y pipelines-audio de AIRI.
El modelo intercala en su respuesta tokens de control que NO se leen en voz ni
se muestran como texto:

    Me alegro mucho <|ACT {"emotion":"happy","intensity":0.8}|> de verte.
    Un momento… <|DELAY 1.5|> ya está.

`ParserMarcadores.consumir(chunk)` recibe el stream en trozos y devuelve una
lista de piezas `(clase, valor)` donde clase es:
    "texto"    → texto hablable/mostrable, tal cual
    "act"      → dict {emotion, intensity, motion} normalizado
    "delay"    → float segundos
    "call"     → [nombre, args?]  (herramienta que pide el modelo; 9.5)
    "invalida" → nombre (str): una marca con INTENCIÓN de acción que no se pudo
                 interpretar (quien ejecuta avisa «no entendí la acción»)

Es incremental y a prueba de cortes: si un chunk termina a mitad de una marca,
retiene la cola hasta el siguiente chunk. Sin dependencias (el catálogo de
herramientas se consulta perezosamente, solo para la tolerancia).

TOLERANCIA (prueba real con qwen2.5:7b, 2026-09): los modelos locales pequeños
escriben las marcas mal a menudo. Se aceptan, y se traducen a la forma buena:
    |<ACT {…}>|  |<ACT {…}>  |<ACT {…}|>  |ACT {…}|  <ACT {…}>  |<|ACT …|>|
    <|mascota_bailar(segundos=60)|>   <|listar_bailes|>   <|abrir_url "https://…"|>
    <|NOMBRE {…}|> con NOMBRE del catálogo (o un alias inglés evidente: OPEN_URL…)
    <|CALL […]|> con JSON algo roto (llaves de más o de menos, comillas simples)
Una marca con pinta de acción que no se entiende (`<|CHANGE_VOICE {…}|>`) sale
como "invalida"; cualquier otra basura con forma de marca (`<|im_end|>`,
`<|SMILE|>`, un ACT ilegible) desaparece. NUNCA queda en el texto visible ni en
la voz. Lo neutralizado a propósito (`< |CALL …|>`, contenido de terceros) no
se reconoce como marca.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, Iterable, List, Optional, Tuple

Pieza = Tuple[str, Any]
Trozo = Tuple[str, Any, str]          # (clase, valor, texto crudo de la marca)

# Vocabulario canónico de emociones (AIRI stage-ui/constants/emotions.ts).
EMOCIONES = ("happy", "sad", "angry", "think", "surprised",
             "awkward", "question", "curious", "neutral",
             # v10 — expresividad: coinciden con los clips animados de la mascota.
             "nervous",   # nerviosa / con duda (gota de sudor)
             "wave",      # saludo / despedida
             "dismiss",   # rechaza o corrige sin ganas (gesto de "no")
             # v10.1 — clips nuevos de la mascota
             "laughing",  # se ríe de verdad (chiste, algo absurdo, complicidad)
             "bored")     # aburrida / desganada

# Estados que ya usaba lune_face → emoción canónica.
ALIAS_EMOCION = {
    "normal": "neutral", "typing": "think", "reading": "think",
    "confused": "question", "error": "sad", "thinking": "think",
    "surprise": "surprised", "fun": "happy", "joy": "happy",
    "sorrow": "sad", "excited": "happy",
    # v10
    "hello": "wave", "hi": "wave", "greet": "wave", "greeting": "wave",
    "bye": "wave", "goodbye": "wave", "adios": "wave", "hola": "wave",
    "worried": "nervous", "anxious": "nervous", "nervioso": "nervous",
    "nerviosa": "nervous", "unamused": "dismiss", "dismissive": "dismiss",
    "rechazo": "dismiss", "no": "dismiss", "annoyed": "dismiss",
    # v10.1
    "laugh": "laughing", "laughs": "laughing", "lol": "laughing", "jaja": "laughing",
    "jajaja": "laughing", "risa": "laughing", "giggle": "laughing", "amused": "laughing",
    "funny": "laughing", "haha": "laughing", "riendo": "laughing",
    "boring": "bored", "aburrida": "bored", "aburrido": "bored", "meh": "bored",
    "tired": "bored", "sleepy": "bored", "cansada": "bored", "sueño": "bored",
}

# Nombres ingleses evidentes que los modelos inventan en vez del de la lista. Solo
# los inequívocos: lo demás (CHANGE_VOCES, ALERTA…) es "invalida" → «no entendí».
ALIAS_HERRAMIENTA = {
    "open_url": "abrir_url", "openurl": "abrir_url", "open": "abrir_url",
    "open_link": "abrir_url", "browse": "abrir_url",
    "alarm": "alarma", "set_alarm": "alarma",
    "timer": "temporizador", "set_timer": "temporizador",
    "web_search": "buscar_web", "search": "buscar_web",
}

# Tokens especiales de las plantillas de chat que a veces se cuelan: basura.
_ESPECIALES = {"im_start", "im_end", "endoftext", "end_of_text", "eot_id", "eos", "bos",
               "begin_of_text", "start_header_id", "end_header_id", "pad", "end", "start",
               "system", "user", "assistant", "tool", "tool_call", "tool_calls"}

_ABRE = "<|"
_CIERRA = "|>"
_MAX_CUERPO = 600                     # más largo que esto no es una marca: es texto
_NADA = object()                      # «no se pudo leer» (None es un JSON válido: null)

# Formas de marca (la buena y las toleradas). El orden importa: la primera que casa.
#   a  <|…|>        con | sueltos alrededor (|<|ACT …|>|); dentro, una palabra pegada o
#                   ACT/DELAY/CALL (así «x <| f |>» de F# no es una marca)
#   b  |<NOMBRE …>| |<NOMBRE …>  |<NOMBRE …|>
#   c  |ACT …|      (solo ACT/DELAY: nunca tras «<» o «< », que es lo neutralizado)
#   d  <ACT …>      <DELAY …>  <CALL …>
_CLAVE = r"(?:[Aa][Cc][Tt]|[Dd][Ee][Ll][Aa][Yy]|[Cc][Aa][Ll][Ll])\b"
#   e  <|ACT {…}    sin cerrar, pero con su JSON entero (si no, se comería el texto
#                   hasta la marca siguiente)
_MARCA = re.compile(
    r"\|?<\|(?=\s*" + _CLAVE + r"|[A-Za-z_])(?P<a>(?:(?!<\|)[\s\S]){0,%d}?)\|>\|?"
    r"|\|<(?P<b>[A-Za-z_][^<>|\n]{0,%d}?)(?:>\|?|\|>)"
    r"|(?<![<\w])(?<!<\s)>?\|(?P<c>(?:ACT|DELAY)\b[^|<>\n]{0,%d}?)\|(?!>)"
    r"|<(?P<d>(?:ACT|DELAY|CALL)\b[^<>\n]{0,%d}?)>"
    r"|\|?<\|(?P<e>\s*ACT\b\s*:?\s*\{[^{}<>|\n]{0,%d}\})"
    % (_MAX_CUERPO, _MAX_CUERPO, _MAX_CUERPO, _MAX_CUERPO, _MAX_CUERPO))

# Streaming: dónde puede empezar una marca que aún no se ha cerrado (se retiene).
_PARCIAL = r"(?:A(?:CT?)?|D(?:E(?:L(?:AY?)?)?)?|C(?:A(?:LL?)?)?)"
_INICIO_ABIERTO = re.compile(
    r"<\|"
    r"|\|<(?=[A-Za-z_|]|$)"
    r"|(?<![<\w])(?<!<\s)>?\|(?=(?:ACT|DELAY)\b|(?:A(?:C)?|D(?:E(?:L(?:A)?)?)?)?$)"
    r"|<(?=(?:ACT|DELAY|CALL)\b|" + _PARCIAL + r"?$)")
# Texto ya completo: solo arranques «fuertes» de marca (un «|» o un «<» sueltos al
# final son texto, p. ej. una tabla; «<| f» de F# también).
_INICIO_FUERTE = re.compile(
    r"<\|(?:\s*" + _CLAVE + r"|[A-Za-z_]|$)|\|<(?:[A-Za-z_|]|$)"
    r"|(?<![<\w])(?<!<\s)>?\|(?:ACT|DELAY)\b|<(?:ACT|DELAY|CALL)\b")


def normalizar_emocion(nombre: Optional[str]) -> str:
    n = (nombre or "").strip().lower()
    n = ALIAS_EMOCION.get(n, n)
    return n if n in EMOCIONES else "neutral"


def es_emocion(nombre: Optional[str]) -> bool:
    n = (nombre or "").strip().lower()
    return n in EMOCIONES or n in ALIAS_EMOCION


def normalizar_act(payload: Any) -> dict:
    """
    Acepta las formas que emiten los modelos y devuelve siempre
    {emotion: str∈EMOCIONES, intensity: float∈[0,1], motion: str|None}.
      "happy"                                    → emoción simple
      {"emotion":"happy","intensity":0.8}
      {"emotion":{"name":"happy","intensity":1},"motion":"wave"}
    """
    emocion, intensidad, motion = "neutral", 1.0, None
    if isinstance(payload, str):
        emocion = payload
    elif isinstance(payload, dict):
        e = payload.get("emotion", payload.get("name"))
        if isinstance(e, dict):
            emocion = e.get("name", "neutral")
            intensidad = e.get("intensity", payload.get("intensity", 1.0))
        else:
            emocion = e if e is not None else "neutral"
            intensidad = payload.get("intensity", 1.0)
        motion = payload.get("motion")
    try:
        intensidad = float(intensidad)
    except (TypeError, ValueError):
        intensidad = 1.0
    intensidad = max(0.0, min(1.0, intensidad))
    return {"emotion": normalizar_emocion(emocion), "intensity": intensidad,
            "motion": (str(motion) if motion else None)}


# ── JSON y argumentos tolerantes ─────────────────────────────────────────────────

def _equilibrar(s: str) -> str:
    """Quita cierres que sobran y añade los que faltan (fuera de las cadenas)."""
    pares = {"}": "{", "]": "["}
    pila: List[str] = []
    salida = []
    en_cadena = escape = False
    for ch in s:
        if en_cadena:
            salida.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                en_cadena = False
            continue
        if ch == '"':
            en_cadena = True
        elif ch in "{[":
            pila.append(ch)
        elif ch in "}]":
            if not pila or pila[-1] != pares[ch]:
                continue                     # cierre que sobra: fuera
            pila.pop()
        salida.append(ch)
    if en_cadena:
        salida.append('"')
    for ch in reversed(pila):
        salida.append("}" if ch == "{" else "]")
    return "".join(salida)


def _literal_python(s: str) -> Any:
    """Literal estilo Python (comillas simples, True/False/None o true/false/null)."""
    t = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", re.sub(r"\bnull\b", "None", s)))
    try:
        return ast.literal_eval(t)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return _NADA


def json_tolerante(s: str) -> Any:
    """JSON (o casi): el valor, o `_NADA` si no hay forma de leerlo."""
    s = (s or "").strip()
    if not s or len(s) > 4000:
        return _NADA
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        pass
    arreglado = _equilibrar(s)
    if arreglado != s:
        try:
            return json.loads(arreglado)
        except (ValueError, TypeError):
            pass
    if s[:1] in "[{'\"" or s[:1].isdigit():
        return _literal_python(arreglado)
    return _NADA


def _valor_suelto(v: str) -> Any:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    bajo = v.lower()
    if bajo in ("true", "false"):
        return bajo == "true"
    if bajo in ("null", "none"):
        return None
    if re.fullmatch(r"[+-]?\d+", v):
        return int(v)
    if re.fullmatch(r"[+-]?\d*\.\d+", v):
        return float(v)
    return v


_KWARG = re.compile(r"([A-Za-z_]\w*)\s*[=:]\s*(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s,)]+)")


def _args_python(s: str) -> Optional[Tuple[list, dict]]:
    """`a=1, b="x"` / `"x", 5` / `sitio="barra" minutos=3` → (posicionales, nombrados)."""
    s = (s or "").strip()
    if len(s) > 1000:
        return None
    if not s:
        return [], {}
    try:
        nodo = ast.parse(f"f({s})", mode="eval").body
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        nodo = None
    if isinstance(nodo, ast.Call):
        def lit(n):
            try:
                return ast.literal_eval(n)
            except (ValueError, SyntaxError, TypeError):
                if isinstance(n, ast.Name):
                    return _valor_suelto(n.id)
                raise
        try:
            pos = [lit(a) for a in nodo.args]
            nom = {k.arg: lit(k.value) for k in nodo.keywords if k.arg}
            return pos, nom
        except (ValueError, SyntaxError, TypeError):
            pass
    pares = _KWARG.findall(s)
    if pares and _KWARG.sub("", s).strip(" ,;") == "":
        return [], {k: _valor_suelto(v) for k, v in pares}
    return None


def _herramientas_conocidas() -> Iterable[str]:
    try:
        from .catalogo_herramientas import CATALOGO
        return CATALOGO.keys()
    except Exception:
        return ()


def nombre_herramienta(nombre: Any) -> Optional[str]:
    """Nombre del catálogo para lo que escribió el modelo (mayúsculas, guiones, alias)."""
    if not isinstance(nombre, str):
        return None
    clave = re.sub(r"[\s\-]+", "_", nombre.strip()).lower()
    if not clave:
        return None
    conocidas = set(_herramientas_conocidas())
    if clave in conocidas:
        return clave
    alias = ALIAS_HERRAMIENTA.get(clave)
    return alias if alias in conocidas else None


def _payload_desde_args(nombre: str, resto: str) -> Optional[list]:
    """Argumentos que siguen al nombre de una herramienta → payload de CALL."""
    resto = resto.strip()
    if resto.startswith(":"):
        resto = resto[1:].strip()
    if not resto:
        return [nombre]
    if resto.startswith("(") and resto.endswith(")"):
        r = _args_python(resto[1:-1])
        if r is None:
            return None
        pos, nom = r
        return [nombre, *pos] + ([nom] if nom else [])
    if resto[0] in "{[\"'":
        v = json_tolerante(resto)
        if v is _NADA:
            return None
        if isinstance(v, list):
            if v and isinstance(v[0], str) and nombre_herramienta(v[0]) == nombre:
                v = v[1:]                     # <|alarma ["alarma", {…}]|>
            return [nombre, *v]
        return [nombre, v]
    if "=" in resto:
        r = _args_python(resto)
        if r is None:
            return None
        pos, nom = r
        return [nombre, *pos] + ([nom] if nom else [])
    if "\n" in resto or len(resto) > 500:
        return None
    return [nombre, _valor_suelto(resto)]      # <|abrir_url https://…|>


def _payload_call(resto: str) -> Tuple[Optional[list], str]:
    """Lo que va tras CALL → (payload o None, nombre para el aviso)."""
    v = json_tolerante(resto)
    if isinstance(v, dict):
        nombre = v.get("name") or v.get("tool") or v.get("herramienta") or v.get("function")
        args = v.get("arguments", v.get("args", v.get("parameters", {})))
        if isinstance(args, str):
            a = json_tolerante(args)
            args = a if a is not _NADA else args
        if isinstance(nombre, str) and nombre.strip():
            v = [nombre, args] if args not in (None, {}) else [nombre, {}]
        else:
            return None, "CALL"
    if isinstance(v, list):
        if not v:
            return None, "CALL"
        if isinstance(v[0], str):
            conocido = nombre_herramienta(v[0])
            if conocido and conocido != v[0]:
                v = [conocido, *v[1:]]
        return v, (v[0] if isinstance(v[0], str) else "CALL")
    # JSON ilegible, pero se ve el nombre: ["abrir_url", {url: nope}] → aviso con su nombre.
    m = re.match(r"\[\s*[\"']([A-Za-z_][\w\-]*)", resto.strip())
    if m:
        return None, nombre_herramienta(m.group(1)) or m.group(1)
    # <|CALL abrir_url {"url": …}|>, <|CALL temporizador(segundos=5)|>
    m = re.match(r"([A-Za-z_][\w\-]*)", resto.strip())
    if m:
        conocido = nombre_herramienta(m.group(1))
        if conocido:
            return _payload_desde_args(conocido, resto.strip()[m.end():]), conocido
        return None, m.group(1)
    return None, "CALL"


def interpretar_cuerpo(cuerpo: str) -> Optional[Pieza]:
    """
    Lo que va entre los delimitadores de una marca → pieza ("act"|"delay"|"call"|
    "invalida", valor) o None (basura: se quita sin más).
    """
    b = (cuerpo or "").strip().strip("|<>").strip()
    if not b:
        return None
    m = re.match(r"(ACT|DELAY|CALL)(?![A-Za-z0-9_])\s*:?\s*", b, re.IGNORECASE)
    if m:
        clase = m.group(1).upper()
        resto = b[m.end():].strip()
        if clase == "DELAY":
            try:
                v = float(resto)
            except ValueError:
                return None
            return ("delay", max(0.0, v)) if v == v and v != float("inf") else None
        if clase == "ACT":
            if not resto:
                return ("act", normalizar_act(None))
            payload = json_tolerante(resto)
            if payload is _NADA:
                if re.fullmatch(r"[A-Za-z_]+", resto):
                    payload = resto
                else:
                    return None
            if not isinstance(payload, (str, dict)):
                return None
            return ("act", normalizar_act(payload))
        payload, nombre = _payload_call(resto)
        if isinstance(payload, list) and payload:
            return ("call", payload)
        return ("invalida", nombre)
    m = re.match(r"([A-Za-z_][\w\-]*)", b)
    if not m:
        return None
    nombre = m.group(1)
    resto = b[m.end():].strip()
    clave = nombre.lower()
    if clave in _ESPECIALES:
        return None
    conocido = nombre_herramienta(nombre)
    if conocido:
        payload = _payload_desde_args(conocido, resto)
        return ("call", payload) if payload else ("invalida", conocido)
    if not resto:
        # <|QUESTION|> es una cara; <|SMILE|> o <|OPEN_URL|> sin nada, basura.
        return ("act", normalizar_act(clave)) if es_emocion(clave) else None
    # <|ALERTA ["alarm", {…}]|>: dentro va una llamada con forma de CALL.
    v = json_tolerante(resto)
    if isinstance(v, list) and v and nombre_herramienta(v[0]):
        return ("call", [nombre_herramienta(v[0]), *v[1:]])
    return ("invalida", nombre)


def _cuerpo_de(m: "re.Match") -> str:
    for g in ("a", "b", "c", "d", "e"):
        if m.group(g) is not None:
            return m.group(g)
    return ""


def _abierta_al_final(resto: str, fuerte: bool = True) -> int:
    """Índice donde empieza una marca sin cerrar al final de `resto` (o len).
    `fuerte` (texto completo): solo una cola corta, de una línea y con pinta de marca."""
    patron = _INICIO_FUERTE if fuerte else _INICIO_ABIERTO
    for m in patron.finditer(resto):
        cola = resto[m.start():]
        if len(cola) > _MAX_CUERPO + 8 or (fuerte and "\n" in cola.rstrip()):
            continue                              # demasiado larga para ser una marca
        return m.start()
    return len(resto)


def _invalida_abierta(cola: str) -> Optional[Pieza]:
    """Marca cortada al final (respuesta truncada): si era una acción, "invalida"
    (NUNCA se intenta completar: un «segundos: 12» cortado no es un 120)."""
    b = cola.lstrip("|<> \t")
    es_call = re.match(r"CALL(?![A-Za-z0-9_])", b, re.IGNORECASE)
    if es_call:
        m = re.match(r"[\s:]*\[?\s*[\"']?([A-Za-z_][\w\-]*)", b[es_call.end():])
        nombre = m.group(1) if m else ""
        return ("invalida", nombre_herramienta(nombre) or nombre or "CALL")
    m = re.match(r"([A-Za-z_][\w\-]*)", b)
    conocido = nombre_herramienta(m.group(1)) if m else None
    return ("invalida", conocido) if conocido else None


def _puede_crecer(m: "re.Match") -> bool:
    """¿A esta marca, que acaba justo al final del búfer, le puede seguir un «|»
    suelto (|<|ACT …|>| o |<ACT …>|)? La buena (<|…|>) se da por cerrada ya."""
    if m.group("e") is not None:
        return True                        # <|ACT {…} sin cerrar: el «|>» puede venir ahora
    t = m.group(0)
    return t.startswith("|") and not t.endswith("|>|") and not t.endswith(">|")


def trocear(texto: str, final: bool = True) -> Tuple[List[Trozo], str]:
    """
    Texto → ([(clase, valor, crudo)], resto_sin_resolver). Clases: "texto", "act",
    "delay", "call", "invalida" y "basura" (marca que se quita sin más).
    `final=False` (streaming): una marca que puede no estar completa se deja en el
    resto; también una que acaba justo al final (le puede seguir un «|» suelto).
    """
    trozos: List[Trozo] = []
    pos = 0
    texto = texto or ""
    for m in _MARCA.finditer(texto):
        if not final and m.end() >= len(texto) and _puede_crecer(m):
            break
        if m.start() > pos:
            trozos.append(("texto", texto[pos:m.start()], texto[pos:m.start()]))
        pieza = interpretar_cuerpo(_cuerpo_de(m))
        crudo = m.group(0)
        if pieza is None:
            trozos.append(("basura", None, crudo))
        else:
            trozos.append((pieza[0], pieza[1], crudo))
        pos = m.end()
    resto = texto[pos:]
    if final:
        corte = _abierta_al_final(resto, fuerte=True)
        if corte < len(resto):
            if corte:
                trozos.append(("texto", resto[:corte], resto[:corte]))
            cola = resto[corte:]
            p = _invalida_abierta(cola)
            trozos.append((p[0], p[1], cola) if p else ("basura", None, cola))
        elif resto:
            trozos.append(("texto", resto, resto))
        return trozos, ""
    corte = _abierta_al_final(resto, fuerte=False)
    if corte:
        trozos.append(("texto", resto[:corte], resto[:corte]))
    return trozos, resto[corte:]


class ParserMarcadores:
    def __init__(self):
        self._buffer = ""

    def consumir(self, chunk: str) -> List[Pieza]:
        """Procesa un trozo del stream y devuelve las piezas completas de él."""
        self._buffer += chunk or ""
        trozos, self._buffer = trocear(self._buffer, final=False)
        return [(c, v) for c, v, _ in trozos if c != "basura"]

    def vaciar(self) -> List[Pieza]:
        """Al terminar el stream: lo que quede (una marca sin cerrar no se enseña)."""
        resto, self._buffer = self._buffer, ""
        if not resto:
            return []
        trozos, _ = trocear(resto, final=True)
        return [(c, v) for c, v, _ in trozos if c != "basura"]


def limpiar_para_mostrar(texto: str) -> str:
    """
    Quita los marcadores (buenos, tolerados o basura) de un texto que se está
    mostrando en vivo, incluida una marca sin cerrar al final del buffer (para que
    no parpadee mientras el modelo aún la está escribiendo).
    """
    texto = texto or ""
    trozos, _ = trocear(texto, final=True)
    return "".join(crudo for c, _, crudo in trozos if c == "texto")


def canonica(clase: str, valor: Any) -> str:
    """Una pieza de control escrita en su forma buena (<|ACT …|>, <|CALL …|>…)."""
    if clase == "act":
        v = valor if isinstance(valor, dict) else normalizar_act(valor)
        d = {"emotion": v.get("emotion", "neutral"), "intensity": round(float(v.get("intensity", 1.0)), 2)}
        if v.get("motion"):
            d["motion"] = v["motion"]
        return "<|ACT " + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "|>"
    if clase == "delay":
        return f"<|DELAY {float(valor):g}|>"
    if clase == "call":
        return "<|CALL " + json.dumps(valor, ensure_ascii=False) + "|>"
    return ""


def _es_forma_buena(crudo: str) -> bool:
    return crudo.startswith(_ABRE) and crudo.endswith(_CIERRA)


def ordenar_espacios(texto: str) -> str:
    """Sin espacios dobles ni líneas en blanco de más donde había marcas."""
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"[ \t]+(?=\n)", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def normalizar(texto: str, *, con_calls: bool = True, con_delay: bool = False) -> str:
    """
    La respuesta con sus marcas en la forma buena y sin basura: para guardarla en
    el historial (el modelo no «aprende» de sus propias marcas rotas). ACT se
    quedan (canónicos si venían tolerados); CALL también (canónicos) salvo
    `con_calls=False`; DELAY fuera salvo `con_delay`; lo inválido, fuera.
    """
    texto = "" if texto is None else str(texto)
    trozos, _ = trocear(texto, final=True)
    salida: List[str] = []
    tocado = False
    for clase, valor, crudo in trozos:
        if clase == "texto":
            salida.append(crudo)
        elif clase == "act" or (clase == "call" and con_calls) or (clase == "delay" and con_delay):
            forma = crudo if (_es_forma_buena(crudo) and clase != "call") else canonica(clase, valor)
            tocado = tocado or forma != crudo
            salida.append(forma)
        else:
            tocado = True
    limpio = "".join(salida)
    return ordenar_espacios(limpio) if tocado else limpio


def separar(texto: str) -> Tuple[str, List[Pieza]]:
    """
    Atajo para texto ya completo (no streaming): devuelve
    (texto_hablable, [piezas de control]).
    """
    parser = ParserMarcadores()
    piezas = parser.consumir(texto) + parser.vaciar()
    hablable = "".join(v for c, v in piezas if c == "texto")
    control = [(c, v) for c, v in piezas if c != "texto"]
    return hablable, control
