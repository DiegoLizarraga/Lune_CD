"""
nucleo/bienvenida.py — Las tres preguntas de Lune cuando aún no te conoce (versión 11).

Qué es
------
La primera vez que abres Lune (su memoria no sabe nada de ti) te pregunta, por el chat:
  1. tu nombre («me llamo X», «soy X», «mi nombre es X», «X es mi nombre» o solo «X»);
  2. cómo eres tú (texto libre corto);
  3. cómo quieres que sea contigo (más formal, con humor, al grano, con cariño…).
Y cierra con «¡Listo, {nombre}! …». Es un flujo DETERMINISTA, sin modelo: lo que
contestas no va a la IA ni a las herramientas; se guarda en la memoria y sale la
siguiente pregunta al instante. Las tres interfaces (web, nativa y patata) solo lo
conectan: esta lógica no tiene Qt (patata la importa).

Cuándo
------
  · Empieza al arrancar (Bienvenida.arrancar) SOLO si la memoria local está vacía de ti
    (MemoriaManager.vacia_de_ti: sin nombre, recuerdos ni datos clave) y la bienvenida no
    está hecha. Si la memoria no está vacía, se marca hecha: a quien ya conozco no le
    pregunto nunca. Tampoco si empezó con la memoria vacía y, antes de contestar nada, la
    memoria se llenó (la restauraste de otro equipo, el bot de Telegram anotó algo): se
    marca hecha en vez de preguntarte el nombre (salvo que la pidieras con /conocernos).
  · Sigue por config (bienvenida.paso), NO por la memoria: tras la pregunta 1 el nombre ya
    está guardado. Si cierras a medias, al volver sigue por la misma pregunta. Cada turno
    relee config.json (patata y la ventana pueden ir a la vez).
  · Solo se toma tu mensaje como respuesta si la pregunta en curso se ve donde escribes
    (`vista`: la clave de la pregunta que enseñó esa ventana o esa burbuja). Si no la has
    visto (el chat flotante con la ventana escondida, la otra interfaz ya avanzó), Lune te
    la enseña en vez de tragarse tu mensaje.
  · «saltar», «ahora no» o «/saltar» la terminan (se queda lo guardado); «prefiero no
    decirlo», «no quiero», «paso», «siguiente»… saltan solo esa pregunta. Si ya tenía algo
    apuntado de eso (una segunda ronda), «paso» o «siguiente» lo conservan y negarte
    («prefiero no decirlo», «no quiero») lo olvida. «/conocernos» la vuelve a empezar.
  · Si el nombre no parece un nombre, lo pregunta una vez más con otras palabras; a la
    segunda sigue sin él.
  · Las líneas «/…» que no son suyas (/memoria, /olvida…) siguen su camino.
  · En modo terminal de la red (la memoria vive en el host) no se hace. Con una memoria
    que no es un MemoriaManager (la remota, dobles de test) o sin config con set(), está
    inactiva: nunca se come un mensaje.

Dónde se guarda
---------------
memoria.json (MemoriaManager.guardar_perfil): usuario.nombre (donde ya lo guardaba
«me llamo…» y de donde lo lee el bot de Telegram), usuario.personalidad y usuario.trato.
Limpio y acotado (va al bloque de memoria del system prompt, al final y estable):
«Cómo es {nombre}: …» y «Cómo quiere {nombre} que te comportes: …».
El estado, en config.json → "bienvenida": {hecha, paso, reintento_nombre, pedida}.

API
---
    b = Bienvenida(config, memoria, nombre_asistente="Lune")   # o una función que lo dé
    b.arrancar()        → la pregunta que toca (y empieza si procede) o None
    b.activa            → ¿espera una respuesta?
    b.pregunta_actual() → el texto de la pregunta en curso (para repintarla) o None
    b.nucleo_actual()   → la frase clave de esa pregunta (para no pintarla dos veces)
    b.clave_paso()      → (paso, reintento): qué pregunta se enseñó en cada sitio
    b.por_decir()       → ¿aún no se dijo en voz alta en este proceso? (y la apunta)
    b.turno(texto, vista=…) → Turno(pregunta, nucleo, respuesta, termino, repetida) si lo
                          consume; None si no
    ya_preguntada(mensajes, nucleo) → ¿el último mensaje del chat ya es esa pregunta?
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple, Union

SECCION = "bienvenida"
DEFECTOS = {"hecha": False, "paso": 0, "reintento_nombre": False, "pedida": False}
PASO_NOMBRE, PASO_PERSONALIDAD, PASO_TRATO = 1, 2, 3
PASOS = (PASO_NOMBRE, PASO_PERSONALIDAD, PASO_TRATO)
MAX_NOMBRE = 40
MAX_PALABRAS_NOMBRE = 4                              # «Juan Carlos Pérez García»
COMANDO_CONOCERNOS = "/conocernos"
COMANDO_SALTAR = "/saltar"

# ── Textos (la voz de Lune: primera persona, cercana, sin emojis) ────────────────
# Cada pregunta lleva su «núcleo»: la frase que la identifica aunque cambie la entradilla
# (así no se pinta dos veces si la conversación restaurada ya termina en ella).
NUCLEO_NOMBRE = "¿cómo te llamas?"
NUCLEO_NOMBRE_OTRA_VEZ = "¿cómo quieres que te llame?"
NUCLEO_PERSONALIDAD = "¿cómo eres tú?"
NUCLEO_TRATO = "¿cómo quieres que sea contigo?"

TXT_PRIMERA = ("¡Hola! Soy {asistente} y todavía no sé nada de ti. Antes de empezar te hago tres "
               "preguntas rápidas para conocerte; si ahora no te apetece, escribe «saltar». "
               "La primera: " + NUCLEO_NOMBRE)
CUERPO_NOMBRE = "Primera pregunta: " + NUCLEO_NOMBRE
CUERPO_NOMBRE_OTRA_VEZ = "¿Cómo quieres que te llame? Con el nombre me basta, por ejemplo: Ana."
TXT_NOMBRE_OTRA_VEZ = "Perdona, no me quedó claro tu nombre. " + CUERPO_NOMBRE_OTRA_VEZ
CUERPO_PERSONALIDAD = ("Segunda pregunta: " + NUCLEO_PERSONALIDAD + " Cuéntamelo en una frase: si "
                       "te van las bromas o vas más al grano, qué te gusta, en qué andas estos días…")
CUERPO_TRATO = ("Última pregunta: " + NUCLEO_TRATO + " Más formal, con humor, al grano, con "
                "cariño… tú decides.")
TXT_CON_NOMBRE = "¡Qué gusto conocerte, {nombre}! " + CUERPO_PERSONALIDAD
TXT_NOMBRE_SALTADO = "Sin problema, no hace falta. " + CUERPO_PERSONALIDAD
TXT_NOMBRE_OLVIDADO = "Sin problema, no hace falta: olvido el nombre que tenía apuntado. " + CUERPO_PERSONALIDAD
TXT_NOMBRE_SE_QUEDA = "Vale, te sigo llamando {nombre}. " + CUERPO_PERSONALIDAD
TXT_NOMBRE_SIN_ENTENDER = "No pasa nada, ya me lo dirás cuando quieras. " + CUERPO_PERSONALIDAD
TXT_CON_PERSONALIDAD = "¡Me encanta saberlo! " + CUERPO_TRATO
TXT_PERSONALIDAD_SALTADA = "Vale, esa nos la saltamos. " + CUERPO_TRATO
TXT_PERSONALIDAD_OLVIDADA = ("Vale, esa nos la saltamos y olvido lo que tenía apuntado de cómo eres. "
                             + CUERPO_TRATO)
TXT_PERSONALIDAD_SE_QUEDA = "Vale, me quedo con lo que ya sabía de cómo eres. " + CUERPO_TRATO
TXT_TRATO_OLVIDADO = "Vale, olvido cómo querías que fuera contigo. "
TXT_SEGUIMOS = "Sigamos donde lo dejamos. "
TXT_LISTO = ("¡Listo{coma_nombre}! Ya lo tengo apuntado y lo tendré en cuenta cada vez que "
             "hablemos. Si algún día quieres cambiarlo, escribe /conocernos. ¿En qué te ayudo?")
TXT_LISTO_SIN_NADA = ("¡Listo! No pasa nada si prefieres no contarme más: nos iremos conociendo "
                      "poco a poco. Si algún día te apetece, escribe /conocernos. ¿En qué te ayudo?")
TXT_SALTADA_CON_ALGO = ("Vale, lo dejamos aquí; me quedo con lo que ya me contaste. Cuando quieras "
                        "seguir, escribe /conocernos. ¿En qué te ayudo?")
TXT_SALTADA = ("Vale, lo dejamos para otro momento. Cuando quieras que nos conozcamos, escribe "
               "/conocernos. ¿En qué te ayudo?")
TXT_OTRA_VEZ = ("¡Me encanta la idea! Vamos allá; si cambias de opinión, escribe «saltar». "
                + CUERPO_NOMBRE)
TXT_NADA_QUE_SALTAR = ("No estábamos en nada que saltar. Si quieres que nos conozcamos, escribe "
                       "/conocernos.")
TXT_EN_TERMINAL = ("En este equipo tu memoria vive en el host de la red, así que eso me lo cuentas "
                   "desde allí.")
TXT_SIN_MEMORIA = ("Ahora mismo no puedo guardar lo que me cuentes, así que mejor lo dejamos para "
                   "otro momento.")

# ── Qué cuenta como «saltar» ─────────────────────────────────────────────────────
# Comparadas en plano (minúsculas, sin tildes ni puntuación; ver _plano).
SALTAR_TODO = frozenset({
    "saltar", "/saltar", "salta", "saltalas", "saltatelas", "saltar todo", "omitir",
    "ahora no", "ahorita no", "ahora mismo no", "mas tarde", "luego", "despues",
    "en otro momento", "otro dia",
})
# Saltar UNA pregunta negándote a contestarla: si ya tenía algo apuntado de eso, lo olvido.
NEGARSE = frozenset({
    "prefiero no decirlo", "prefiero no decirtelo", "prefiero no decir", "prefiero no contestar",
    "prefiero no responder", "prefiero no contarlo", "prefiero no contartelo", "prefiero no",
    "prefiero que no", "prefiero guardarmelo", "me lo reservo", "no quiero decirlo",
    "no quiero decirtelo", "no quiero decir", "no quiero contestar", "no quiero responder",
    "no quiero", "no contesto", "no respondo", "mejor no", "sin comentarios", "no", "no gracias",
    "nop", "nope", "nel", "nada", "ninguno", "ninguna",
})
# Saltar UNA pregunta sin más («la siguiente»): si ya tenía algo apuntado, se queda.
PASAR = frozenset({
    "paso", "siguiente", "siguiente pregunta", "la siguiente", "otra", "otra pregunta", "skip",
    "next", "pass", "no se", "no lo se", "ni idea", "nose", "idk", "no sabria decirte",
})
_RE_PASAR = re.compile(r"^(?:salta(?:r|te)?\s+(?:esta|esa|la)(?:\s+pregunta)?|saltar?\s+pregunta|"
                       r"pasa(?:mos)?\s+a\s+la\s+siguiente)$")
SALTAR_UNA = NEGARSE | PASAR
_CORTESIA_FINAL = ("gracias", "por favor", "porfa", "porfavor", "plis", "please")
_CORTESIA_INICIAL = ("mejor", "vale", "ok", "okay", "bueno", "pues")

# ── Nombre ───────────────────────────────────────────────────────────────────────
_RE_SALUDO = re.compile(
    r"^(?:hola+|holi(?:s)?|hey|ey|oye|oiga|buenas(?:\s+(?:tardes|noches))?|buenos\s+d[ií]as|"
    r"qu[eé]\s+tal|saludos|hi|hello)\b[\s,.;:!¡¿?…]*", re.IGNORECASE)
# Muletillas de delante («claro, soy Ana», «ok, me llamo Ana», «ehh soy Ana»): fuera, solo si
# detrás viene algo más.
_RE_MULETILLA = re.compile(
    r"^(?:claro(?:\s+que\s+s[ií])?|ok(?:ay|ey)?|vale|bueno|pues|s[ií]|e+h+|e+m+|m+h*m+|"
    r"a\s+ver|oh|ah+|este|perd[oó]n|disculpa)\b[\s,.;:!¡¿?…]*", re.IGNORECASE)
_RE_PREFIJO = re.compile(
    r"^(?:(?:yo\s+)?me\s+llamo|mi\s+nombre\s+es|(?:yo\s+)?soy|ll[aá]mame|puedes\s+llamarme|"
    r"me\s+puedes\s+llamar|me\s+dicen|me\s+llaman|mi\s+nombre|my\s+name\s+is|call\s+me|"
    r"i\s+am|i['’]m)\b[\s,:]*", re.IGNORECASE)
# «Diego es mi nombre», «Ana, así me llamo».
_RE_SUFIJO = re.compile(r"[\s,]+(?:es\s+mi\s+nombre|(?:as[ií]\s+)?me\s+llamo|es\s+como\s+me\s+llamo)"
                        r"[\s.!]*$", re.IGNORECASE)
# Tratamientos delante del nombre: se conservan («Dr. House», «Doña Rosa»).
_RE_TITULO = re.compile(r"^(dr|dra|sr|sra|srta|lic|ing|prof|profe|don|do[nñ]a)(\.?)\s+(?=\S)",
                        re.IGNORECASE)
_TITULOS = {"dr": "Dr.", "dra": "Dra.", "sr": "Sr.", "sra": "Sra.", "srta": "Srta.", "lic": "Lic.",
            "ing": "Ing.", "prof": "Prof.", "profe": "Profe", "don": "Don", "dona": "Doña"}
_RE_PALABRA = re.compile(r"^(?=(?:.*[^\W\d_]){2})[^\W\d_]{1,20}(?:['’\-][^\W\d_]{1,20})*$")
_RE_CORTE = re.compile(r"[,.;:!?¡¿()\[\]{}\"«»/\\|<>=+*#@&%$~^`]")
# «María de los Ángeles»: partículas solo en medio (no cuentan como palabra del nombre).
_PARTICULAS = frozenset({"de", "del", "la", "las", "los"})
# Palabras que cortan: lo que sigue ya no es el nombre («Ana y tengo 30 años» → Ana).
_CORTES = frozenset({
    "y", "e", "pero", "que", "porque", "aunque", "pues", "entonces", "gracias", "tengo", "vivo",
    "trabajo", "estoy", "me", "mi", "te", "soy", "para", "por", "con", "desde", "aqui", "jaja",
    "jajaja", "xd", "lol", "bueno", "ok", "vale", "es",
})
# Respuestas que NO son un nombre: saludos, síes y noes, órdenes y verbos («cierra chrome»,
# «dime la hora», «prefiero que no»), adverbios («mañana», «ahorita»), muletillas, lo que
# alguien dice de sí («soy muy tímido», «soy programador») y lo que se pide a menudo.
# Ojo: nada que sea también un nombre corriente (Leo, Mira, Paz, Luz, Rosa, Salva…).
_NO_NOMBRE = frozenset("""
hola holi holis hey ey oye oiga buenas buenos saludos hi hello si no nada nadie ok okay vale bien
mal gracias jaja jajaja jeje jiji xd lol yo tu usted el ella un una uno que quien como cual donde
cuando por para usuario usuaria humano humana persona anonimo anonima nombre ninguno ninguna test
prueba asdf claro perdon espera listo lista genial igual tambien tampoco adios chao bye porque pues
eso esto aqui alli alla ahi entonces
abre abrir abreme cierra cerrar cierrame apaga apagar enciende encender prende pon ponme poner
reproduce reproducir busca buscar buscame dime di decir cuentame contar hablame habla hablar
prefiero preferiria quiero queria quisiera necesito salta saltate saltar lanza ejecuta inicia arranca
sube baja muestra muestrame ensename explica explicame ayuda ayudame haz hazme crea creame escribe
escribeme manda envia llama recuerda recuerdame avisame anota apunta guarda olvida olvidate borra
elimina limpia tengo estoy voy vamos puedo puedes podrias sabes eres es son hay escucha calla
callate detente deten sigue continua cambia activa desactiva instala descarga traduce calcula
pregunta responde contesta dame pasame ven vete cancela juega jugar canta baila bailar dibuja
hoy manana ahorita ahora luego despues ayer siempre nunca ya aun todavia casi solo mejor peor asi
bastante muy mas menos super algo poco mucho mucha muchos muchas tanto todo toda todos todas
eh ehh ah oh mmm mhm uff ups nose idk ns skip next pass nel nop nope yes yeah sure
hora clima tiempo musica cancion video pc computadora ordenador chrome youtube spotify google
whatsapp discord steam volumen alarma tarea nota chiste noticias
estudiante programador programadora ingeniero ingeniera nuevo nueva normal profesor profesora
doctor doctora medico medica gamer jugador jugadora hombre mujer chico chica nino nina senor senora
joven mayor timido timida tranquilo tranquila curioso curiosa feliz alegre serio seria callado
callada divertido divertida gracioso graciosa amable nervioso nerviosa introvertido introvertida
extrovertido extrovertida sociable raro rara cansado cansada aburrido aburrida
dr dra sr sra srta lic ing prof profe dona
""".split())

# Voz: qué pregunta se dijo ya en voz alta en ESTE proceso (por config.json). Así un
# cambio de interfaz en caliente (web ↔ nativa) no la repite, y la vuelve a decir al
# abrir Lune otro día.
_DICHAS: dict = {}
_CANDADO_DICHAS = threading.Lock()
_SIN_VISTA = object()


def _plano(texto: Any) -> str:
    """Para comparar: minúsculas, sin tildes, sin puntuación (la «/» de delante se queda)
    y espacios juntos. «¡Prefiero no decirlo!» → «prefiero no decirlo»."""
    s = unicodedata.normalize("NFD", str(texto or "").strip().casefold())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    barra = s.startswith("/")
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s)
    s = " ".join(s.split())
    return ("/" + s) if barra and s else s


def _es_salto(s: str) -> bool:
    return s in SALTAR_TODO or s in SALTAR_UNA or bool(_RE_PASAR.match(s))


def _sin_cortesia(plano: str) -> str:
    """«saltar por favor» → «saltar»; «mejor no» se queda (es una frase entera)."""
    s = plano
    cambio = True
    while cambio:
        cambio = False
        for c in _CORTESIA_FINAL:
            if s.endswith(" " + c):
                s, cambio = s[: -len(c) - 1].strip(), True
    for c in _CORTESIA_INICIAL:
        if s.startswith(c + " ") and _es_salto(s[len(c) + 1:]):
            s = s[len(c) + 1:]
    return s


def es_saltar_todo(texto: Any) -> bool:
    return _sin_cortesia(_plano(texto)) in SALTAR_TODO


def es_negarse(texto: Any) -> bool:
    """«prefiero no decirlo», «no quiero», «no gracias», «nada»…: no me lo quieres contar."""
    return _sin_cortesia(_plano(texto)) in NEGARSE


def es_pasar(texto: Any) -> bool:
    """«paso», «siguiente», «salta esta», «no sé»…: a la siguiente, sin más."""
    s = _sin_cortesia(_plano(texto))
    return s in PASAR or bool(_RE_PASAR.match(s))


def es_saltar_una(texto: Any) -> bool:
    return es_negarse(texto) or es_pasar(texto)


def _solo_texto(texto: Any) -> str:
    """Sin símbolos (emojis incluidos) ni caracteres de control; espacios juntos."""
    s = "".join(" " if unicodedata.category(ch)[0] in ("S", "C") else ch for ch in str(texto or ""))
    return " ".join(s.split())


def _capitalizar(palabra: str) -> str:
    """«maría» → «María», «jean-luc» → «Jean-Luc», «o'connor» → «O'Connor», «DIEGO» →
    «Diego». Si la persona ya mezcló mayúsculas y minúsculas («McDonald», «O'Brien»), se
    respeta tal cual."""
    letras = [c for c in palabra if c.isalpha()]
    if letras and not (all(c.islower() for c in letras) or all(c.isupper() for c in letras)):
        return palabra
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), palabra)


def extraer_nombre(texto: Any, asistente: str = "Lune") -> Optional[str]:
    """El nombre de la respuesta a «¿cómo te llamas?», limpio y con mayúsculas, o None si no
    parece un nombre. Acepta «me llamo X», «soy X», «mi nombre es X», «llámame X», «X es mi
    nombre» o solo «X» (hasta cuatro palabras, con «de/del/la/los» en medio y un tratamiento
    delante: «Dr. House»), con un saludo o una muletilla delante («hola Lune, soy Ana»,
    «claro, soy Ana»). Rechaza saludos sueltos, frases, órdenes, verbos, adverbios y el
    nombre de la asistente."""
    s = _solo_texto(texto).strip(" \t,.;:!¡¿?\"'()-—…")
    if not s:
        return None
    patron_asistente = None
    if str(asistente or "").strip():
        patron_asistente = re.compile(rf"^{re.escape(str(asistente).strip())}\b[\s,.;:!¡¿?]*", re.IGNORECASE)
    for _ in range(6):                                # «hola, buenas, Lune: claro, soy Ana»
        m = _RE_SALUDO.match(s)
        if m:
            s = s[m.end():]
            continue
        # El nombre de la asistente o una muletilla delante de algo más («Lune, soy Ana»,
        # «ok, me llamo Ana») fuera; «Lune» a secas se queda (y abajo se rechaza: me está
        # saludando, no presentándose).
        quitado = False
        for patron in (patron_asistente, _RE_MULETILLA):
            mm = patron.match(s) if patron is not None else None
            if mm and mm.end() < len(s):
                s, quitado = s[mm.end():], True
                break
        if not quitado:
            break
    s = s.strip(" ,.;:!¡¿?")
    explicito = False
    msuf = _RE_SUFIJO.search(s)
    if msuf and msuf.start() > 0:
        s, explicito = s[: msuf.start()], True
    m = _RE_PREFIJO.match(s)
    if m:
        s, explicito = s[m.end():], True
    if explicito:
        s = re.sub(r"^(?:el|la)\s+(?=\S)", "", s, flags=re.IGNORECASE)   # «soy el Diego», «soy la Dra. Pérez»
    titulo = ""
    mt = _RE_TITULO.match(s)
    if mt:
        titulo, s = _TITULOS.get(_plano(mt.group(1)), ""), s[mt.end():]
    s = _RE_CORTE.split(s, maxsplit=1)[0]
    palabras = s.split()
    if not palabras or _plano(palabras[0]) in _CORTES:
        return None                                   # «me gustaría que…», «y tú?»
    tomadas = []
    for p in palabras:
        if tomadas and _plano(p) in _CORTES:
            break
        tomadas.append(p)
    if not explicito and len(palabras) - len(tomadas) > 2:
        return None                                   # «Ana y tengo 30 años y…»: una frase
    if explicito:                                     # «me llamo Ana García López Pérez de…» → 4 palabras
        cuenta, recorte = 0, []
        for p in tomadas:
            if _plano(p) not in _PARTICULAS:
                if cuenta == MAX_PALABRAS_NOMBRE:
                    break
                cuenta += 1
            recorte.append(p)
        tomadas = recorte
    while tomadas and _plano(tomadas[-1]) in _PARTICULAS:
        tomadas.pop()
    if not tomadas or _plano(tomadas[0]) in _PARTICULAS:
        return None
    nucleo = [p for p in tomadas if _plano(p) not in _PARTICULAS]
    if len(nucleo) > MAX_PALABRAS_NOMBRE or len(tomadas) > MAX_PALABRAS_NOMBRE + 3:
        return None                                   # una frase, no un nombre
    if not all(_RE_PALABRA.match(p) for p in nucleo):
        return None
    if any(_plano(p) in _NO_NOMBRE for p in nucleo):
        return None
    nombre = " ".join(_capitalizar(p) if p in nucleo else _plano(p) for p in tomadas)
    if not explicito and _plano(nombre) == _plano(asistente):
        return None                                   # «Lune» a secas: me saluda, no se presenta
    if titulo:
        nombre = f"{titulo} {nombre}"
    if len(nombre) > MAX_NOMBRE:
        return None
    return nombre


def ya_preguntada(mensajes: Any, nucleo: str) -> bool:
    """¿El último mensaje de `mensajes` (chats/: {rol, contenido}; página: {role, text}) es de
    Lune y ya lleva esa pregunta? Así no se pinta dos veces tras restaurar la conversación."""
    if not nucleo or not isinstance(mensajes, (list, tuple)) or not mensajes:
        return False
    m = mensajes[-1]
    if not isinstance(m, dict):
        return False
    rol = m.get("rol") or m.get("role")
    if rol not in ("assistant", "bot"):
        return False
    texto = str(m.get("contenido") or m.get("text") or "")
    return nucleo.casefold() in texto.casefold()


@dataclass
class Turno:
    """Lo que pasó con tu mensaje: `pregunta` es la que estabas contestando ("" si ninguna),
    `nucleo` su frase clave, `respuesta` lo que dice Lune ahora y `termino` si la bienvenida
    acabó. `repetida`: no habías visto la pregunta donde escribiste, así que tu mensaje no
    cuenta como respuesta y `respuesta` es la propia pregunta."""
    pregunta: str
    nucleo: str
    respuesta: str
    termino: bool = False
    cara: str = "happy"
    repetida: bool = False


class Bienvenida:
    """Estado en config (sección «bienvenida»), respuestas en la memoria. Sin Qt."""

    def __init__(self, config: Any, memoria: Any, *,
                 nombre_asistente: Union[str, Callable[[], str], None] = "Lune",
                 terminal: Union[bool, Callable[[], bool], None] = None):
        """`terminal`: ¿modo terminal de la red? (None = nucleo.datos.hub_modo())."""
        self.config = config
        self.memoria = memoria
        self._asistente = nombre_asistente
        self._terminal = terminal

    # ── Piezas ─────────────────────────────────────────────────────────────────────
    def nombre_asistente(self) -> str:
        n = self._asistente
        try:
            n = n() if callable(n) else n
        except Exception:
            n = None
        n = " ".join(str(n or "").split())[:40]
        return n or "Lune"

    def _config_ok(self) -> bool:
        c = self.config
        return c is not None and callable(getattr(c, "get", None)) and callable(getattr(c, "set", None))

    def _memoria_ok(self) -> bool:
        """Solo una MemoriaManager de verdad: la remota (terminal de la red) y los dobles de
        los tests no, así nunca se come un mensaje donde no puede guardar."""
        try:
            from nucleo.memoria import MemoriaManager
        except Exception:                             # pragma: no cover
            return False
        return isinstance(self.memoria, MemoriaManager)

    def _es_terminal(self) -> bool:
        t = self._terminal
        try:
            if callable(t):
                return bool(t())
            if t is not None:
                return bool(t)
            from nucleo import datos
            return datos.hub_modo() == "terminal"
        except Exception:
            return False

    def disponible(self) -> bool:
        """¿Puede haber bienvenida aquí? (config que guarda, memoria local de verdad y no
        es un terminal de la red)."""
        return self._config_ok() and self._memoria_ok() and not self._es_terminal()

    # ── Estado (config) ────────────────────────────────────────────────────────────
    def _recargar(self) -> None:
        """Relee config.json si otro proceso lo cambió (patata y la ventana a la vez): un
        stat y el mutex. Sin esto, el que va atrasado tomaría tu mensaje por la respuesta a
        una pregunta ya contestada (o a una bienvenida ya terminada)."""
        recargar = getattr(self.config, "recargar", None)
        if callable(recargar):
            try:
                recargar()
            except Exception:
                pass

    def _estado(self) -> Tuple[bool, int, bool]:
        """(hecha, paso, reintento_nombre) validados: lo raro cuenta como por defecto."""
        try:
            hecha = self.config.get(SECCION, "hecha", False)
            paso = self.config.get(SECCION, "paso", 0)
            reintento = self.config.get(SECCION, "reintento_nombre", False)
        except Exception:
            return False, 0, False
        if not (isinstance(paso, int) and not isinstance(paso, bool) and 0 <= paso <= 3):
            paso = 0
        return hecha is True, paso, reintento is True

    def _pedida(self) -> bool:
        """¿Esta ronda la pediste con /conocernos? (entonces ya te conozco)."""
        try:
            return self.config.get(SECCION, "pedida", False) is True
        except Exception:
            return False

    def _escribir(self, **valores) -> None:
        """Cambia claves de la sección y guarda (Config.set: atómico y sin pisar a patata o
        a la otra ventana), en el orden dado. Solo escribe lo que cambia."""
        for clave, valor in valores.items():
            try:
                actual = self.config.get(SECCION, clave, None)
            except Exception:                         # la sección no es un dict: set la repara
                actual = None
            if type(actual) is type(valor) and actual == valor:
                continue
            try:
                self.config.set(SECCION, clave, valor)
            except Exception:
                pass

    @property
    def activa(self) -> bool:
        """¿Espero la respuesta a una de mis preguntas? (con lo último leído de config)."""
        if not self.disponible():
            return False
        hecha, paso, _ = self._estado()
        return not hecha and paso in PASOS

    def clave_paso(self) -> Optional[Tuple[int, bool]]:
        """(paso, reintento) mientras está activa: qué pregunta se enseñó (o se dijo) en
        cada sitio."""
        if not self.activa:
            return None
        _, paso, reintento = self._estado()
        return paso, reintento

    # ── Voz: cada pregunta, una vez por proceso ────────────────────────────────────
    def _clave_registro(self) -> str:
        ruta = getattr(self.config, "config_path", None)
        return str(ruta) if ruta else f"id:{id(self.config)}"

    def por_decir(self) -> bool:
        """True (y la apunta como dicha) si la pregunta en curso aún no se dijo en voz alta
        en este proceso; False si ya se dijo o no hay pregunta."""
        clave = self.clave_paso()
        if clave is None:
            return False
        k = self._clave_registro()
        with _CANDADO_DICHAS:
            if _DICHAS.get(k) == clave:
                return False
            _DICHAS[k] = clave
            return True

    def marcar_dicha(self) -> None:
        """La pregunta en curso ya se dijo (iba en la respuesta que acaba de sonar)."""
        clave = self.clave_paso()
        with _CANDADO_DICHAS:
            _DICHAS[self._clave_registro()] = clave

    # ── Arranque ───────────────────────────────────────────────────────────────────
    def arrancar(self) -> Optional[str]:
        """Al abrir una interfaz: la pregunta que toca o None. Si aún no había empezado y la
        memoria está vacía de ti, empieza (paso 1); si ya te conozco, la marca hecha para no
        preguntarte nunca. Se puede llamar muchas veces (cada carga de la página)."""
        if not self.disponible():
            return None
        self._recargar()                              # patata o la otra ventana pudieron avanzarla
        hecha, paso, _ = self._estado()
        if hecha:
            return None
        if paso in PASOS:
            if paso == PASO_NOMBRE and not self._pedida():
                # Empezó con la memoria vacía y aún no contestaste nada: si entretanto la
                # memoria se llenó (restaurada de otro equipo, el bot de Telegram…), ya te
                # conozco y no te pregunto «¿cómo te llamas?».
                try:
                    vacia = self.memoria.vacia_de_ti()
                except Exception:
                    vacia = None
                if vacia is False:
                    self._escribir(hecha=True, paso=0, reintento_nombre=False, pedida=False)
                    return None
            return self._pregunta()
        try:
            vacia = self.memoria.vacia_de_ti()
        except Exception:
            return None
        if vacia is True:
            self._escribir(pedida=False, reintento_nombre=False, paso=PASO_NOMBRE)
            return self._pregunta()
        if vacia is False:
            self._escribir(hecha=True)
        return None

    def _pregunta(self) -> Optional[str]:
        if not self.activa:
            return None
        _, paso, reintento = self._estado()
        if paso == PASO_NOMBRE:
            if reintento:
                return TXT_SEGUIMOS + CUERPO_NOMBRE_OTRA_VEZ
            if self._pedida():
                return TXT_SEGUIMOS + CUERPO_NOMBRE
            return TXT_PRIMERA.format(asistente=self.nombre_asistente())
        if paso == PASO_PERSONALIDAD:
            return TXT_SEGUIMOS + CUERPO_PERSONALIDAD
        return TXT_SEGUIMOS + CUERPO_TRATO

    def pregunta_actual(self) -> Optional[str]:
        """El texto de la pregunta en curso tal como se pinta al (re)abrir o al limpiar el
        chat; None si no hay bienvenida en marcha. Relee config.json antes."""
        if not self.disponible():
            return None
        self._recargar()
        return self._pregunta()

    def nucleo_actual(self) -> str:
        """La frase clave de la pregunta en curso ("" si no hay)."""
        if not self.activa:
            return ""
        _, paso, reintento = self._estado()
        if paso == PASO_NOMBRE:
            return NUCLEO_NOMBRE_OTRA_VEZ if reintento else NUCLEO_NOMBRE
        return NUCLEO_PERSONALIDAD if paso == PASO_PERSONALIDAD else NUCLEO_TRATO

    def _vista_ok(self, vista: Any) -> bool:
        """¿La pregunta en curso se ve donde escribiste? `vista`: la clave que enseñó ese
        sitio (o una lista de claves: la burbuja y, si se ve, la ventana)."""
        if vista is _SIN_VISTA:
            return True
        clave = self.clave_paso()
        if isinstance(vista, (list, set, frozenset)):
            return clave in vista
        return vista == clave

    # ── Tu mensaje ─────────────────────────────────────────────────────────────────
    def turno(self, texto: Any, vista: Any = _SIN_VISTA) -> Optional[Turno]:
        """Tu mensaje del chat. Devuelve el Turno si es de la bienvenida (una respuesta, o
        /conocernos, /saltar) o None si sigue su camino de siempre (no hay bienvenida en
        marcha, o es otro comando «/…»). Con `vista` (la clave de la pregunta que enseñó
        el sitio donde escribiste; ver clave_paso), si no es la pregunta en curso tu mensaje
        no cuenta como respuesta: Lune te enseña la pregunta (Turno.repetida)."""
        t = str(texto or "").strip()
        if not t:
            return None
        if self.disponible():
            self._recargar()
        plano = _plano(t)
        activa = self.activa
        pregunta = self._pregunta() if activa else None
        nucleo = self.nucleo_actual() if activa else ""
        if plano == COMANDO_CONOCERNOS:
            return Turno(pregunta or "", nucleo, self.reiniciar(), cara="happy")
        if not activa:
            if plano == COMANDO_SALTAR:
                return Turno("", "", TXT_NADA_QUE_SALTAR, cara="normal")
            return None
        if es_saltar_todo(t):
            return Turno(pregunta or "", nucleo, self._saltar_todo(), termino=True)
        if t.startswith("/"):
            return None                                   # /memoria, /olvida…: siguen su camino
        if not self._vista_ok(vista):
            return Turno("", nucleo, pregunta or "", repetida=True)
        _, paso, reintento = self._estado()
        if paso == PASO_NOMBRE:
            respuesta = self._contestar_nombre(t, reintento)
        elif paso == PASO_PERSONALIDAD:
            respuesta = self._contestar_personalidad(t)
        else:
            respuesta = self._contestar_trato(t)
        return Turno(pregunta or "", nucleo, respuesta, termino=not self.activa)

    def responder(self, texto: Any) -> Optional[str]:
        """Como turno(), solo el texto de Lune (o None)."""
        tb = self.turno(texto)
        return tb.respuesta if tb is not None else None

    def _guardar(self, **campos) -> None:
        try:
            self.memoria.guardar_perfil(**campos)
        except Exception:
            pass

    def _perfil(self) -> dict:
        try:
            p = self.memoria.perfil()
            return p if isinstance(p, dict) else {}
        except Exception:
            return {}

    def _contestar_nombre(self, texto: str, reintento: bool) -> str:
        if es_saltar_una(texto):
            antes = self._perfil().get("nombre") or ""
            self._escribir(paso=PASO_PERSONALIDAD, reintento_nombre=False)
            if antes and es_negarse(texto):
                self._guardar(nombre="")
                return TXT_NOMBRE_OLVIDADO
            if antes:
                return TXT_NOMBRE_SE_QUEDA.format(nombre=antes)
            return TXT_NOMBRE_SALTADO
        nombre = extraer_nombre(texto, self.nombre_asistente())
        if nombre is None:
            if not reintento:
                self._escribir(reintento_nombre=True)
                return TXT_NOMBRE_OTRA_VEZ
            self._escribir(paso=PASO_PERSONALIDAD, reintento_nombre=False)
            return TXT_NOMBRE_SIN_ENTENDER
        self._guardar(nombre=nombre)
        self._escribir(paso=PASO_PERSONALIDAD, reintento_nombre=False)
        return TXT_CON_NOMBRE.format(nombre=nombre)

    def _contestar_personalidad(self, texto: str) -> str:
        from nucleo.memoria import limpiar_dato_perfil
        limpio = limpiar_dato_perfil(texto)
        if es_saltar_una(texto) or not limpio:
            antes = self._perfil().get("personalidad") or ""
            self._escribir(paso=PASO_TRATO)
            if antes and es_negarse(texto):
                self._guardar(personalidad="")
                return TXT_PERSONALIDAD_OLVIDADA
            if antes:
                return TXT_PERSONALIDAD_SE_QUEDA
            return TXT_PERSONALIDAD_SALTADA
        self._guardar(personalidad=limpio)
        self._escribir(paso=PASO_TRATO)
        return TXT_CON_PERSONALIDAD

    def _contestar_trato(self, texto: str) -> str:
        from nucleo.memoria import limpiar_dato_perfil
        limpio = limpiar_dato_perfil(texto)
        prefijo = ""
        if limpio and not es_saltar_una(texto):
            self._guardar(trato=limpio)
        elif es_negarse(texto) and self._perfil().get("trato"):
            self._guardar(trato="")
            prefijo = TXT_TRATO_OLVIDADO
        return prefijo + self._terminar()

    def _terminar(self) -> str:
        self._escribir(hecha=True, paso=0, reintento_nombre=False, pedida=False)
        p = self._perfil()
        if not any(p.get(c) for c in ("nombre", "personalidad", "trato")):
            return TXT_LISTO_SIN_NADA
        nombre = p.get("nombre") or ""
        return TXT_LISTO.format(coma_nombre=f", {nombre}" if nombre else "")

    def _saltar_todo(self) -> str:
        self._escribir(hecha=True, paso=0, reintento_nombre=False, pedida=False)
        p = self._perfil()
        return TXT_SALTADA_CON_ALGO if any(p.get(c) for c in ("nombre", "personalidad", "trato")) else TXT_SALTADA

    def reiniciar(self) -> str:
        """/conocernos: vuelve a empezar (aunque ya estuviera hecha) y da la primera pregunta.
        «hecha» se escribe la última: el otro proceso nunca ve «sin hacer y sin empezar»."""
        if self._es_terminal():
            return TXT_EN_TERMINAL
        if not (self._config_ok() and self._memoria_ok()):
            return TXT_SIN_MEMORIA
        self._escribir(pedida=True, reintento_nombre=False, paso=PASO_NOMBRE, hecha=False)
        return TXT_OTRA_VEZ


def es_bienvenida(obj: Any) -> bool:
    """¿`obj` es una Bienvenida? (las ventanas lo miran así: un doble de test con MagicMock
    nunca cuenta)."""
    return isinstance(obj, Bienvenida)


__all__ = ["Bienvenida", "Turno", "extraer_nombre", "ya_preguntada", "es_bienvenida",
           "es_saltar_todo", "es_saltar_una", "es_negarse", "es_pasar", "SECCION", "DEFECTOS",
           "COMANDO_CONOCERNOS", "COMANDO_SALTAR"]
