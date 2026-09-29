"""
lune_core/acciones.py — Ejecutor de las acciones que pide el modelo.

El modelo pide herramientas con UN solo formato, dentro de su respuesta:

    Te aviso en cinco minutos. <|CALL ["temporizador", {"segundos": 300}]|>

`Ejecutor.procesar(texto)` saca esas marcas del texto visible y hablado y las
convierte en `Llamada`s validadas contra el esquema del catálogo
(lune_core/catalogo_herramientas.py). `Ejecutor.ejecutar_llamadas(...)` las
corre AL TERMINAR la respuesta, pasando cada una por la Política y la Sesión de
lune_core/herramientas.py (fail-closed, deny-list, presupuesto y auditoría).

Reglas (plan §2.5 y crítica d):
  · Máximo 3 CALL por respuesta; el resto se descarta sin ejecutar.
  · Tolerancia (prueba real con modelos locales): las formas mal escritas que
    lune_core/marcadores.py sabe leer (<|mascota_bailar(segundos=60)|>,
    <|OPEN_URL https://…|>, |<CALL …>|, JSON con una llave de más…) se
    interpretan y pasan por AQUÍ como cualquier CALL: misma Política, misma
    aprobación, mismo origen.
  · Un CALL (o una marca con intención de acción) que no se entiende —JSON
    ilegible, cortado, nombre inventado— desaparece del texto, NO se ejecuta y
    vuelve como Llamada inválida: la persona ve «No entendí la acción…» en vez de
    creer que se hizo.
  · Cotejo: si la persona escribió una duración u hora (ctx['mensaje_usuario']) y
    la llamada a temporizador/alarma la contradice, manda la de la persona
    (catalogo_herramientas.cotejar; queda en `Llamada.corregidos` y en la auditoría).
  · El formato antiguo (`ABRIR_URL:`, `ABRIR_BUSQUEDA:`, `TOOL:`) ya NO se
    ejecuta: se salta la neutralización de marcadores. Solo se borra del texto.
  · Origen del turno: 'usuario', 'no_confiable' o 'remoto'. Si el prompt llevaba
    texto de terceros (título de ventana, pantalla, Minecraft, Telegram, notas…),
    el turno es 'no_confiable' y solo pasan herramientas de LECTURA. Un origen
    desconocido cuenta como no confiable.
  · Origen 'remoto' (orden desde Telegram con /pc): las herramientas del modo
    están disponibles como con 'usuario', pero TODA llamada, también las de
    LECTURA y las `directa`, la aprueba un humano en el PC (motivo AVISO_REMOTO,
    «Pedido desde Telegram»); sin canal de aprobación, rechazada. Mezclado con
    'no_confiable' manda lo más restrictivo de los dos: solo LECTURA, y con
    aprobación.
  · Contexto contaminado (taint): un turno 'usuario' cuya conversación enviada
    lleva texto de terceros (el historial del AIManager lo marca) no es de fiar
    del todo: LECTURA sigue libre y TODO lo demás pide aprobación humana, aunque
    el catálogo no la pida; sin canal de aprobación, se rechaza con el motivo.
    Se mira al ejecutar (`contexto_contaminado(ctx)`). Las llamadas `directa`
    (las escribió la persona: «abre youtube») no cuentan. En una orden 'remoto'
    también se mira: la pregunta lleva los dos motivos (AVISO_REMOTO y
    AVISO_CONTAMINADO).
  · Modo llamada (ctx['llamada'] = True): lo transcrito del micrófono puede ser
    ruido de fondo u otra persona. LECTURA sigue libre y lo demás pide aprobación
    (motivo AVISO_LLAMADA), también las `directa` («pon un temporizador…»).
  · Lo que requiere aprobación se pregunta a un HUMANO con
    `pedir_aprobacion(pendiente, responder)`; sin respuesta en 60 s, rechazada.
    Las llamadas de una misma respuesta van en orden: la siguiente espera a que
    se resuelva la aprobación de la anterior.
  · Presupuesto de 20 unidades por conversación (`nueva_conversacion()`).
  · Nunca lanza: los fallos vuelven como `ResultadoAccion(ok=False)`.

Hilos: los handlers permitidos se ejecutan en el hilo que llama a
`ejecutar_llamadas`. Lo que llega después de una aprobación (o de su caducidad)
pasa por `despachar(fn)`; por defecto se ejecuta en el hilo que respondió o en
el del temporizador. La integración Qt debe pasar un `despachar` que lo lleve al
hilo de la interfaz, y patata uno que lo saque del hilo lector de la consola.
`al_resultado` puede llamarse desde cualquiera de esos hilos.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from . import catalogo_herramientas as cat
from . import marcadores
from .herramientas import (Decision, Descriptor, Pendiente, Registro, Riesgo,
                           Sesion, asdict_veredicto)

MAX_POR_RESPUESTA = 3
PRESUPUESTO = 20
TIMEOUT_APROBACION = 60.0

# Motivo de la pregunta cuando el contexto del turno lleva texto de terceros.
AVISO_CONTAMINADO = ("La conversación contiene contenido externo (adjuntos, mensajes de "
                     "otros, notas…) que pudo influir en la respuesta. Confirma solo si "
                     "esto lo pediste tú.")
# Motivo de la pregunta cuando la orden llegó desde Telegram (origen 'remoto').
AVISO_REMOTO = ("Pedido desde Telegram, no desde este PC. Apruébalo solo si fuiste tú "
                "quien lo pidió.")
# Motivo de la pregunta cuando lo pedido se oyó en el modo llamada (ctx['llamada']).
AVISO_LLAMADA = ("Lo oí en la llamada (puede ser ruido de fondo, la tele u otra persona). "
                 "Apruébalo solo si lo pediste tú.")
# Motivo de la pregunta cuando el modelo OFRECE la acción («¿quieres que te ponga
# uno?») y a la vez la pide: la prueba real (2026-09-28) lo vio poner temporizadores
# que nadie había pedido. No se tira (a veces es una pregunta de más tras un pedido
# de verdad): se pregunta.
AVISO_OFRECIDA = "Te lo ofrecí yo en la respuesta; no me consta que lo pidieras."
# Lo que hace el cuerpo de la mascota: se ve al momento y se deshace con un clic, así que
# aunque lo ofrezca no se pregunta («baila» → «¿quieres que bailemos?» + la marca era un
# pedido de verdad en la prueba real). Lo que dura o sale de Lune (temporizador, alarma,
# web, voz, tamaño, bot de Minecraft) sí se pregunta.
_OFRECIDA_SIN_PREGUNTA = frozenset({
    "mascota_bailar", "parar_baile", "mascota_dormir", "mascota_despertar",
    "mascota_sentarse", "mascota_pantalla_grande", "dar_de_comer"})
# Formas vistas en 4 rondas de la prueba real: «¿Quieres que te ponga uno?», «¿O prefieres
# que busque…?», «¿Te interesa programar algo?», «¿Te lo pongo?», «Puedo ponerte uno de 5
# minutos, ¿te interesa?». Una pregunta cualquiera NO basta: el modelo acaba con «¿algo
# más?» en la mitad de las acciones pedidas de verdad (se preguntaría sin motivo).
_OFERTA = re.compile(
    r"¿\s*(?:[oy]\s+)?(?:(?:quieres|te\s+gustar[ií]a|te\s+interesa|prefieres|deseas|te\s+parece\s+bien)"
    r"\s+(?:que|si)\b|te\s+interesa\s+\w+(?:ar|er|ir)\b|te\s+interesa\s*\?"
    r"|(?:te\s+)?(?:lo|la|los|las|le|uno|una)?\s*(?:pongo|abro|busco|programo)\b)"
    # «Puedo ponerte uno, ¿te interesa?»; «¿En qué puedo ayudarte?» no es ofrecer nada.
    r"|(?<!qu[eé]\s)\bpuedo\s+(?!ayudar)\w+(?:ar|er|ir)(?:te|lo|la|le|les)?\b[^.!?\n]{0,80}\?",
    re.IGNORECASE)


def ofrece_accion(texto: str) -> bool:
    """¿La respuesta (lo que se ve) le ofrece hacer algo al usuario en vez de hacerlo?"""
    try:
        return bool(_OFERTA.search(marcadores.limpiar_para_mostrar(texto or "")))
    except Exception:
        return False

USUARIO = cat.ORIGEN_USUARIO
NO_CONFIABLE = cat.ORIGEN_NO_CONFIABLE
REMOTO = cat.ORIGEN_REMOTO

# Estados de ResultadoAccion
HECHA = "hecha"
ERROR = "error"
DENEGADA = "denegada"
NO_CONFIABLE_ESTADO = "solo_lectura"
RECHAZADA = "rechazada"
CADUCADA = "caducada"
SIN_PRESUPUESTO = "sin_presupuesto"
INVALIDA = "invalida"
NO_DISPONIBLE = "no_disponible"
LIMITE = "limite"

# Error de una marca con intención de acción que no se pudo interpretar (el
# mensaje que ve la persona es «No entendí la acción «X»: …»).
NO_ENTENDIDA = "la marca no es válida y no la hice"


# ── Datos ────────────────────────────────────────────────────────────────────────

@dataclass
class Llamada:
    """Una herramienta pedida por el modelo, ya interpretada."""
    herramienta: str
    args: Dict[str, Any] = field(default_factory=dict)
    crudo: Any = None
    error: Optional[str] = None
    motivo: str = ""                 # INVALIDA | NO_DISPONIBLE | LIMITE si hay error
    origen: str = USUARIO
    ignorados: Tuple[str, ...] = ()
    # True: la escribió la persona tal cual («abre youtube»,
    # servicios.tools.detectar_llamadas), no el modelo. Un historial con texto de
    # terceros no la afecta (el modelo no intervino). procesar() nunca la pone.
    directa: bool = False
    # Cotejo con lo que escribió la persona (catalogo_herramientas.cotejar): los
    # argumentos que se cambiaron, {clave: (lo que pidió el modelo, lo que se usa)}.
    corregidos: Dict[str, Any] = field(default_factory=dict)
    # True: la respuesta OFRECE hacerlo («¿quieres que…?») a la vez que lo pide; lo
    # que no sea de lectura se pregunta (AVISO_OFRECIDA). Lo pone procesar().
    ofrecida: bool = False

    @property
    def valida(self) -> bool:
        return self.error is None


@dataclass
class ResultadoAccion:
    ok: bool
    mensaje: str
    herramienta: str
    estado: str = HECHA
    args: Dict[str, Any] = field(default_factory=dict)
    pendiente_id: Optional[str] = None

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Aprobacion:
    pid: str
    llamada: Llamada
    pendiente: dict
    ctx: dict
    al_resultado: Optional[Callable]
    generacion: int
    continuar: Callable[[], None]
    creado: float
    temporizador: Any = None


# ── Texto: sacar las marcas ──────────────────────────────────────────────────────

_ABRE, _CIERRA = "<|", "|>"
# Restos que no se ejecutan ni se enseñan: marcas neutralizadas («< |CALL …|>», el
# eco de un texto de terceros) y un CALL neutralizado sin cerrar al final.
_RESTO_CALL = re.compile(r"<\s+\|\s*(?:CALL|ACT|DELAY)(?![A-Za-z0-9_]).*?\|>",
                         re.IGNORECASE | re.DOTALL)
_RESTO_CALL_ABIERTO = re.compile(r"<\s+\|\s*CALL(?![A-Za-z0-9_])[^\n]*$", re.IGNORECASE)
# Formato antiguo: se borra, nunca se ejecuta.
_LEGADO = (
    # Línea entera con solo el comando: se va también su salto de línea.
    re.compile(r"(?m)^[ \t]*(?:ABRIR_BUSQUEDA[ \t]*:[^\n]*|ABRIR_URL[ \t]*:[ \t]*\S*[ \t]*"
               r"|TOOL[ \t]*:[^\n]*)(?:\n|\Z)"),
    re.compile(r"[ \t]?ABRIR_BUSQUEDA[ \t]*:[^\n]*"),
    re.compile(r"[ \t]?ABRIR_URL[ \t]*:[ \t]*\S*"),
    re.compile(r"(?m)^[ \t]*TOOL[ \t]*:[^\n]*"),
    re.compile(r"[ \t]?\bTOOL:[a-z_]+\b(?::[^\n]*)?"),
)


def _unir(piezas: List[str]) -> str:
    """Junta los trozos que quedan sin dejar dobles espacios donde había marca."""
    salida = ""
    for p in piezas:
        if salida and p and salida[-1] in " \t" and p[0] in " \t":
            p = p.lstrip(" \t")
        salida += p
    return salida


def _ordenar(texto: str) -> str:
    texto = re.sub(r"[ \t]+(?=\n)", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def separar_acciones(texto: str) -> Tuple[str, List[Any], List[str]]:
    """
    Quita del texto las marcas de acción (CALL y sus formas toleradas, ver
    lune_core/marcadores.py), la basura con forma de marca y el formato antiguo.
    Devuelve (texto_limpio, payloads_en_orden, nombres_no_entendidos): lo último
    son marcas con intención de acción que no se pudieron interpretar (JSON roto,
    marca cortada, nombre inventado con argumentos…); quien ejecuta avisa «no
    entendí la acción» en vez de darla por hecha. ACT y DELAY se quedan para quien
    los procese después: tal cual si venían bien escritos, en su forma buena si
    venían tolerados (|<ACT …>|, |ACT …|…).
    """
    texto = "" if texto is None else str(texto)
    trozos, _ = marcadores.trocear(texto, final=True)
    piezas: List[str] = []
    payloads: List[Any] = []
    fallidas: List[str] = []
    tocado = False
    for clase, valor, crudo in trozos:
        if clase == "texto":
            piezas.append(crudo)
        elif clase in ("act", "delay"):
            bien = crudo.startswith(_ABRE) and crudo.endswith(_CIERRA)
            piezas.append(crudo if bien else marcadores.canonica(clase, valor))
            tocado = tocado or not bien
        else:
            if clase == "call":
                payloads.append(valor)
            elif clase == "invalida":
                fallidas.append(str(valor or ""))
            tocado = True

    limpio = _unir(piezas)
    for patron in (_RESTO_CALL, _RESTO_CALL_ABIERTO, *_LEGADO):
        limpio, n = patron.subn("", limpio)
        tocado = tocado or n > 0
    if tocado:
        limpio = _ordenar(limpio)
    return limpio, payloads, fallidas


def separar_llamadas(texto: str) -> Tuple[str, List[Any], int]:
    """(texto_limpio, payloads_en_orden, n_no_entendidas): ver separar_acciones."""
    limpio, payloads, fallidas = separar_acciones(texto)
    return limpio, payloads, len(fallidas)


def limpiar_texto(texto: str) -> str:
    """Solo el texto, sin marcas de acción, basura ni formato antiguo (para mostrar o hablar)."""
    try:
        return separar_llamadas(texto)[0]
    except Exception:
        return texto or ""


# ── Utilidades ───────────────────────────────────────────────────────────────────

def _origen(o: Any) -> str:
    """'usuario' y 'remoto' solo si lo dicen tal cual; cualquier otra cosa, no confiable."""
    t = str(o or "").strip().lower()
    return t if t in (USUARIO, REMOTO) else NO_CONFIABLE


def _origen_efectivo(origenes: List[Any]) -> str:
    """El más restrictivo: no_confiable > remoto > usuario (sin ninguno: usuario)."""
    norm = [_origen(o) for o in origenes]
    if NO_CONFIABLE in norm:
        return NO_CONFIABLE
    return REMOTO if REMOTO in norm else USUARIO


def _a_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v == 1
    return str(v or "").strip().lower() in {"s", "si", "sí", "y", "yes", "true", "1", "ok"}


def _args_de(resto: List[Any], h: cat.Herramienta) -> Optional[Dict[str, Any]]:
    """
    Lo que va tras el nombre en el payload → objeto de argumentos (sin validar):
      [{…}]                  el de siempre
      ["https://…"]          un valor suelto → al único argumento requerido (o al único)
      ["6:30", {"dias": …}]  valores sueltos → a los argumentos en orden (primero los
                             requeridos que falten), más lo nombrado
    None si no se puede (p. ej. varios sueltos para una herramienta sin argumentos).
    """
    nombrados: Dict[str, Any] = {}
    sueltos: List[Any] = []
    for x in resto:
        if isinstance(x, Mapping):
            nombrados.update(x)
        elif x is None:
            continue
        elif isinstance(x, (str, int, float)):
            sueltos.append(x)
        else:
            return None
    if not sueltos or not h.args:
        return nombrados                 # <|sistema_info("cpu")|>: sin argumentos, se ignora
    requeridos = [k for k, a in h.args.items() if a.requerido]
    if len(sueltos) == 1 and not nombrados and not isinstance(sueltos[0], bool):
        destino = requeridos or list(h.args)
        if len(destino) == 1:
            return {destino[0]: sueltos[0]}
    libres = [k for k in requeridos + [k for k in h.args if k not in requeridos]
              if k not in nombrados]
    if len(sueltos) > len(libres):
        return None
    return {**nombrados, **dict(zip(libres, sueltos))}


def _programar_hilo(segundos: float, fn: Callable[[], None]):
    t = threading.Timer(max(0.0, float(segundos)), fn)
    t.daemon = True
    t.start()
    return t


def _normalizar_salida(salida: Any) -> Tuple[bool, str]:
    """Lo que devuelve un handler → (ok, mensaje). Acepta str, ToolResult, dict o tupla."""
    if salida is None:
        return True, "Hecho."
    if isinstance(salida, str):
        return True, salida
    if isinstance(salida, Mapping) and "ok" in salida:
        return bool(salida.get("ok")), str(salida.get("mensaje", "") or "")
    if isinstance(salida, tuple) and len(salida) == 2 and isinstance(salida[0], bool):
        return salida[0], str(salida[1])
    if hasattr(salida, "ok") and hasattr(salida, "mensaje"):
        return bool(salida.ok), str(salida.mensaje)
    return True, str(salida)


# ── Ejecutor ─────────────────────────────────────────────────────────────────────

class Ejecutor:
    """
    registro          Registro de descriptores (fail-closed).
    sesion            Sesion con Política, presupuesto y auditoría.
    handlers          {nombre: fn(args: dict, ctx: dict) -> str}.
    pedir_aprobacion  fn(pendiente: dict, responder: fn(bool)) -> None. Tiene que
                      enseñar la pregunta a un humano; `responder` se puede llamar
                      desde cualquier hilo y solo cuenta la primera respuesta.
                      Sin esta función, todo lo que requiere aprobación se rechaza.
    reloj             time.monotonic (inyectable en tests).
    programar         fn(segundos, callback) -> objeto con cancel(); por defecto
                      un threading.Timer demonio. Sirve para el timeout de 60 s.
    despachar         fn(callback) que lleva lo que pasa tras una aprobación al
                      hilo adecuado. Por defecto, en línea.
    cerrar_aprobacion fn(pendiente_id) para cerrar la pregunta en la interfaz
                      cuando caduca o se cancela por conversación nueva.
    """

    def __init__(self, registro: Registro, sesion: Sesion,
                 handlers: Optional[Dict[str, Callable[[dict, Any], Any]]] = None,
                 pedir_aprobacion: Optional[Callable[[dict, Callable[[bool], None]], None]] = None,
                 reloj: Callable[[], float] = time.monotonic, *,
                 max_por_respuesta: int = MAX_POR_RESPUESTA,
                 presupuesto: Optional[int] = PRESUPUESTO,
                 timeout_aprobacion: float = TIMEOUT_APROBACION,
                 programar: Optional[Callable[[float, Callable[[], None]], Any]] = None,
                 despachar: Optional[Callable[[Callable[[], None]], None]] = None,
                 cerrar_aprobacion: Optional[Callable[[str], None]] = None,
                 catalogo: Optional[Mapping[str, cat.Herramienta]] = None):
        self.registro = registro
        self.sesion = sesion
        self.handlers: Dict[str, Callable] = dict(handlers or {})
        self.pedir_aprobacion = pedir_aprobacion
        self._reloj = reloj
        self.max_por_respuesta = max(0, int(max_por_respuesta))
        self.presupuesto = sesion.presupuesto if presupuesto is None else int(presupuesto)
        self.sesion.presupuesto = self.presupuesto
        self.timeout = float(timeout_aprobacion)
        self._programar = programar or _programar_hilo
        self._despachar_fn = despachar
        self.cerrar_aprobacion = cerrar_aprobacion
        self.catalogo = catalogo if catalogo is not None else cat.CATALOGO
        self._lock = threading.RLock()
        self._aprob: Dict[str, _Aprobacion] = {}
        self._generacion = 0

    # ── Handlers ──
    def registrar_handler(self, nombre: str, fn: Callable[[dict, Any], Any]) -> None:
        self.handlers[str(nombre)] = fn

    def quitar_handler(self, nombre: str) -> None:
        self.handlers.pop(str(nombre), None)

    def disponibles(self, modo: Optional[str] = None) -> List[str]:
        """Herramientas con handler, registradas y válidas en `modo`."""
        return cat.disponibles_en(modo, self.handlers, self.registro, self.catalogo)

    # ── Texto → llamadas ──
    def procesar(self, texto: str, origen: str = USUARIO, ctx: Any = None
                 ) -> Tuple[str, List[Llamada]]:
        """
        Devuelve (texto_limpio, llamadas). El texto ya no tiene marcas CALL ni
        formato antiguo (las ACT/DELAY se quedan). Cada llamada viene validada;
        las que no valen traen `error` y no se ejecutarán.
        """
        try:
            origen = _origen(origen)
            limpio, payloads, fallidas = separar_acciones(texto)
            if fallidas:
                self._auditar("call_invalido", cantidad=len(fallidas), nombres=fallidas[:5])
            llamadas: List[Llamada] = []
            # Dos temporizadores en la misma respuesta: el cotejo no sabría cuál es cuál.
            nombres = [p[0] for p in payloads if isinstance(p, list) and p and isinstance(p[0], str)]
            repetidas = {n for n in nombres if nombres.count(n) > 1}
            for i, payload in enumerate(payloads):
                repetida = isinstance(payload, list) and bool(payload) and payload[0] in repetidas
                ll = self._interpretar(payload, origen, ctx, cotejar=not repetida)
                if i >= self.max_por_respuesta:
                    ll.error = f"máximo {self.max_por_respuesta} acciones por respuesta"
                    ll.motivo = LIMITE
                llamadas.append(ll)
            if len(payloads) > self.max_por_respuesta:
                self._auditar("limite_por_respuesta", pedidas=len(payloads),
                              maximo=self.max_por_respuesta)
            if llamadas and ofrece_accion(limpio):
                for ll in llamadas:
                    ll.ofrecida = True
            # Intención de acción que no se entendió: no se hace, pero se AVISA
            # («No entendí la acción…»), para que nadie la dé por hecha. Una por nombre.
            for nombre in dict.fromkeys(fallidas):
                llamadas.append(Llamada(nombre, crudo=nombre, error=NO_ENTENDIDA,
                                        motivo=INVALIDA, origen=origen))
            return limpio, llamadas
        except Exception:
            return limpiar_texto(texto), []

    def _interpretar(self, payload: Any, origen: str, ctx: Any, cotejar: bool = True) -> Llamada:
        if (not isinstance(payload, list) or not payload
                or not isinstance(payload[0], str)):
            return Llamada("", crudo=payload, error="forma de CALL inválida",
                           motivo=INVALIDA, origen=origen)
        nombre = payload[0].strip()
        ll = Llamada(nombre, crudo=payload, origen=origen)
        h = cat.obtener(nombre, self.catalogo)
        if h is None or self.registro.get(nombre) is None:
            ll.error, ll.motivo = "herramienta desconocida", INVALIDA
            return ll
        crudo_args = _args_de(payload[1:], h)
        if crudo_args is None:
            ll.error, ll.motivo = "los argumentos tienen que ser un objeto {…}", INVALIDA
            return ll
        try:
            ll.args, ignorados = cat.validar(crudo_args, h.args)
            ll.ignorados = tuple(ignorados)
        except cat.ArgumentosInvalidos as e:
            ll.error, ll.motivo = str(e), INVALIDA
            return ll
        # Lo que escribió la persona manda sobre lo que entendió el modelo («en veinte
        # minutos» son 1200 s aunque el modelo pida 45; «mañana» no es «todos los lunes»).
        try:
            nuevos, cambios = cat.cotejar(nombre, ll.args, ctx) if cotejar else (ll.args, {})
            if cambios:
                ll.args, _ = cat.validar(nuevos, h.args)
                ll.corregidos = cambios
                self._auditar("cotejo", herramienta=nombre,
                              cambios={k: list(v) for k, v in cambios.items()})
        except Exception:
            pass
        modo = cat.valor_ctx(ctx, "modo")
        if modo and not h.disponible_en(modo):
            ll.error, ll.motivo = "no disponible en este modo", NO_DISPONIBLE
        elif nombre not in self.handlers:
            ll.error, ll.motivo = "no disponible aquí", NO_DISPONIBLE
        return ll

    # ── Ejecución ──
    def ejecutar_llamadas(self, llamadas: List[Llamada], origen: Optional[str] = None,
                          ctx: Any = None,
                          al_resultado: Optional[Callable[[ResultadoAccion], None]] = None
                          ) -> None:
        """
        Ejecuta las llamadas en orden. Cada resultado llega por `al_resultado`
        (también los rechazos y errores). No bloquea esperando aprobaciones.
        Manda el origen más restrictivo entre `origen` y el de cada llamada
        (no_confiable > remoto > usuario); si alguno es 'remoto', todo pide
        aprobación aunque el efectivo sea no_confiable.
        """
        try:
            lista = [ll for ll in (llamadas or []) if isinstance(ll, Llamada)]
            origenes = [ll.origen for ll in lista] + ([origen] if origen is not None else [])
            origen_ef = _origen_efectivo(origenes)
            ctx_ef = self._ctx(ctx, origen_ef)
            if REMOTO in (_origen(o) for o in origenes):
                ctx_ef["remoto"] = True
            with self._lock:
                gen = self._generacion
            self._continuar(lista, origen_ef, ctx_ef, al_resultado, gen)
        except Exception:
            pass

    def _continuar(self, cola: List[Llamada], origen: str, ctx: dict,
                   al_resultado, gen: int) -> None:
        while cola:
            with self._lock:
                if gen != self._generacion:
                    return
            ll = cola.pop(0)

            def seguir(cola=cola):
                self._continuar(cola, origen, ctx, al_resultado, gen)

            try:
                espera = self._una(ll, origen, ctx, al_resultado, gen, seguir)
            except Exception as e:
                self._emitir(al_resultado, ResultadoAccion(
                    False, f"Falló «{ll.herramienta}»: {e}"[:300], ll.herramienta, ERROR,
                    dict(ll.args)))
                espera = False
            if espera:
                return

    def _una(self, ll: Llamada, origen: str, ctx: dict, al_resultado, gen: int,
             seguir: Callable[[], None]) -> bool:
        """Procesa una llamada. True si queda esperando una aprobación."""
        nombre = ll.herramienta
        if not ll.valida:
            estado = ll.motivo or INVALIDA
            if estado == LIMITE:
                msg = f"No hago «{nombre}»: {ll.error}."
            elif estado == NO_DISPONIBLE:
                msg = f"«{nombre}» no está disponible aquí."
            else:
                msg = f"No entendí la acción «{nombre or '?'}»: {ll.error}."
            self._emitir(al_resultado, ResultadoAccion(False, msg, nombre, estado, dict(ll.args)))
            return False

        h = cat.obtener(nombre, self.catalogo)
        desc = self.registro.get(nombre)
        fn = self.handlers.get(nombre)
        if h is None or desc is None:
            self._emitir(al_resultado, ResultadoAccion(
                False, f"No entendí la acción «{nombre}».", nombre, INVALIDA, dict(ll.args)))
            return False
        if fn is None or not h.disponible_en(cat.valor_ctx(ctx, "modo")):
            self._emitir(al_resultado, ResultadoAccion(
                False, f"«{nombre}» no está disponible aquí.", nombre, NO_DISPONIBLE,
                dict(ll.args)))
            return False

        # Turno con texto de terceros: solo lectura (crítica d).
        lectura = desc.riesgo == Riesgo.LECTURA and h.riesgo == Riesgo.LECTURA
        if origen not in (USUARIO, REMOTO) and not lectura:
            self._auditar("denegada_origen", herramienta=nombre, args=ll.args, origen=origen)
            self._emitir(al_resultado, ResultadoAccion(
                False, f"No hago «{nombre}»: la petición salió de un texto externo, "
                       "no de ti.", nombre, NO_CONFIABLE_ESTADO, dict(ll.args)))
            return False

        # Orden desde Telegram: TODO lo aprueba un humano en el PC (también la
        # lectura y lo que se escribió tal cual en /pc).
        remoto = origen == REMOTO or cat.valor_ctx(ctx, "remoto") is True
        if remoto:
            self._auditar("remoto", herramienta=nombre, args=ll.args)
        # La conversación que vio el modelo lleva texto de terceros (taint): lo que no
        # sea de lectura lo aprueba un humano, siempre. También en una orden remota
        # (ya pide permiso por venir de Telegram): la pregunta dice los dos motivos.
        contaminado = (not lectura and not ll.directa and self.contexto_contaminado(ctx))
        if contaminado:
            self._auditar("contexto_contaminado", herramienta=nombre, args=ll.args)
        # Modo llamada: se oyó por el micrófono (quizá no fuiste tú): lo que no sea de
        # lectura lo aprueba un humano, aunque sea `directa`.
        oida = not lectura and cat.valor_ctx(ctx, "llamada") is True
        if oida:
            self._auditar("oida_en_llamada", herramienta=nombre, args=ll.args)
        # El modelo lo ofreció («¿quieres que…?») y lo pidió a la vez: se pregunta.
        ofrecida = (not lectura and not ll.directa and ll.ofrecida
                    and nombre not in _OFRECIDA_SIN_PREGUNTA)
        if ofrecida:
            self._auditar("ofrecida", herramienta=nombre, args=ll.args)
        forzar = (remoto or contaminado or oida or ofrecida
                  or cat.aprobacion_dinamica(nombre, ctx, ll.args))
        with self._lock:
            r = self._solicitar(nombre, ll.args, desc, forzar)
        estado = r.get("estado")
        veredicto = r.get("veredicto") or {}
        if estado == "denegada":
            self._emitir(al_resultado, ResultadoAccion(
                False, veredicto.get("resumen") or f"No puedo hacer «{nombre}».", nombre,
                DENEGADA, dict(ll.args)))
            return False
        if estado == "sin_presupuesto":
            self._emitir(al_resultado, ResultadoAccion(
                False, "Ya hice demasiadas acciones en esta conversación; empieza una "
                       "nueva para seguir.", nombre, SIN_PRESUPUESTO, dict(ll.args)))
            return False
        if estado == "permitida" and not remoto:
            self._emitir(al_resultado, self._ejecutar_handler(fn, nombre, ll.args, ctx))
            return False
        if estado == "aprobacion_requerida" and r.get("pendiente_id"):
            self._pedir(ll, r["pendiente_id"], veredicto, origen, ctx, al_resultado, gen, seguir,
                        contaminado=contaminado, remoto=remoto, oida=oida, ofrecida=ofrecida)
            return True
        if remoto:
            # No debería pasar (forzar = aprobación obligatoria), pero una orden remota
            # nunca se ejecuta sin que alguien la apruebe en el PC.
            self._emitir(al_resultado, ResultadoAccion(
                False, f"No hago «{nombre}»: una orden desde Telegram necesita tu permiso "
                       "en el PC.", nombre, RECHAZADA, dict(ll.args)))
            return False
        self._emitir(al_resultado, ResultadoAccion(
            False, f"No puedo hacer «{nombre}».", nombre, DENEGADA, dict(ll.args)))
        return False

    def _solicitar(self, nombre: str, args: dict, desc: Descriptor, forzar: bool) -> dict:
        """Sesion.solicitar, o su versión con aprobación obligatoria (dinámica)."""
        if not forzar:
            return self.sesion.solicitar(nombre, args)
        desc_f = Descriptor(desc.nombre, desc.descripcion, desc.riesgo,
                            requiere_aprobacion=True, coste=desc.coste)
        v = self.sesion.politica.evaluar(desc_f, args)
        self._auditar("solicitud", herramienta=nombre, args=args, dinamica=True,
                      decision=v.decision.value, motivo=v.motivo)
        if v.decision == Decision.DENEGAR:
            return {"estado": "denegada", "veredicto": asdict_veredicto(v)}
        if self.sesion.gastado + desc.coste > self.sesion.presupuesto:
            self._auditar("sin_presupuesto", herramienta=nombre,
                          gastado=self.sesion.gastado, presupuesto=self.sesion.presupuesto)
            return {"estado": "sin_presupuesto", "veredicto": asdict_veredicto(v)}
        pid = uuid.uuid4().hex[:12]
        self.sesion.pendientes[pid] = Pendiente(pid, nombre, dict(args),
                                                asdict_veredicto(v), time.time())
        self._auditar("encolada", herramienta=nombre, pendiente_id=pid, dinamica=True)
        return {"estado": "aprobacion_requerida", "pendiente_id": pid,
                "veredicto": asdict_veredicto(v)}

    @staticmethod
    def contexto_contaminado(ctx: Any) -> bool:
        """
        ¿El contexto que vio el modelo en este turno lleva texto de terceros?
        Se calcula AL EJECUTAR: ctx['contaminado'] (True) o el AIManager del ctx
        (`ctx['ai'].contexto_contaminado(ctx['proveedor'])`, lo pone
        servicios.tools.ctx_acciones). Sin forma de saberlo: False. Si la consulta
        falla: True (fail-closed).
        """
        if cat.valor_ctx(ctx, "contaminado") is True:
            return True
        ai = cat.valor_ctx(ctx, "ai")
        if ai is None and isinstance(ctx, Mapping):
            ai = cat.valor_ctx(ctx.get("contexto"), "ai")
        fn = getattr(ai, "contexto_contaminado", None)
        if not callable(fn):
            return False
        try:
            return bool(fn(cat.valor_ctx(ctx, "proveedor") or None))
        except Exception:
            return True

    def _pedir(self, ll: Llamada, pid: str, veredicto: dict, origen: str, ctx: dict,
               al_resultado, gen: int, seguir: Callable[[], None], *,
               contaminado: bool = False, remoto: bool = False, oida: bool = False,
               ofrecida: bool = False) -> None:
        h = cat.obtener(ll.herramienta, self.catalogo)
        # Todos los motivos que apliquen, en orden (remoto + contaminado a la vez, p. ej.).
        motivos = [m for m, si in ((AVISO_REMOTO, remoto), (AVISO_LLAMADA, oida),
                                   (AVISO_CONTAMINADO, contaminado),
                                   (AVISO_OFRECIDA, ofrecida)) if si]
        motivo = " ".join(motivos) if motivos else veredicto.get("resumen", "")
        pendiente = {
            "id": pid,
            "herramienta": ll.herramienta,
            "args": dict(ll.args),
            "resumen": cat.resumen(ll.herramienta, ll.args, ctx, self.catalogo),
            "descripcion": h.descripcion if h else ll.herramienta,
            "riesgo": veredicto.get("riesgo", ""),
            "motivo": motivo,
            "origen": origen,
            "timeout": self.timeout,
            "pregunta": "¿Lo hago?",
        }
        if contaminado:
            pendiente["contaminado"] = True
        if remoto:
            pendiente["remoto"] = True               # «Pedido desde Telegram» en la pregunta
        if oida:
            pendiente["llamada"] = True              # «Lo oí en la llamada» en la pregunta
        if ofrecida:
            pendiente["ofrecida"] = True             # «Te lo ofrecí yo…» en la pregunta
        turno = cat.valor_ctx(ctx, "turno")
        if turno:
            pendiente["turno"] = str(turno)          # el host enruta la pregunta a ese turno
        ap = _Aprobacion(pid, ll, pendiente, ctx, al_resultado, gen, seguir, self._reloj())
        with self._lock:
            self._aprob[pid] = ap
        extra = "".join(t for t, si in (("pedido desde Telegram y ", remoto),
                                        ("oído en la llamada y ", oida),
                                        ("la conversación contiene contenido externo y ", contaminado))
                        if si)
        if self.pedir_aprobacion is None:
            self._resolver(pid, False, RECHAZADA, f"{extra}no hay a quién pedir permiso")
            return
        try:
            ap.temporizador = self._programar(self.timeout, lambda: self._caducar(pid))
        except Exception:
            ap.temporizador = None
        try:
            self.pedir_aprobacion(dict(pendiente), self._responder_para(pid))
        except Exception as e:
            self._resolver(pid, False, RECHAZADA, f"{extra}no se pudo pedir permiso ({e})")

    def _responder_para(self, pid: str) -> Callable[[Any], None]:
        def responder(ok: Any = False) -> None:
            try:
                self._resolver(pid, _a_bool(ok), RECHAZADA, "rechazada por el usuario")
            except Exception:
                pass
        return responder

    def resolver(self, pendiente_id: str, ok: Any) -> bool:
        """Respuesta que llega por id (p. ej. el modal web). False si ya no estaba."""
        try:
            return self._resolver(str(pendiente_id), _a_bool(ok), RECHAZADA,
                                  "rechazada por el usuario")
        except Exception:
            return False

    def _caducar(self, pid: str) -> None:
        try:
            self._resolver(pid, False, CADUCADA, f"sin respuesta en {self.timeout:g} s")
        except Exception:
            pass

    def revisar_caducadas(self) -> int:
        """Rechaza las aprobaciones que llevan `timeout` s sin respuesta (según `reloj`)."""
        ahora = self._reloj()
        with self._lock:
            vencidas = [pid for pid, ap in self._aprob.items()
                        if ahora - ap.creado >= self.timeout]
        for pid in vencidas:
            self._caducar(pid)
        return len(vencidas)

    def _resolver(self, pid: str, ok: bool, estado_no: str, motivo: str) -> bool:
        with self._lock:
            ap = self._aprob.pop(pid, None)
            if ap is None:
                return False           # ya resuelta, caducada o cancelada
            vigente = ap.generacion == self._generacion
            r = None
            if vigente and ok:
                r = self.sesion.aprobar(pid)
            else:
                self.sesion.rechazar(pid, motivo)
        self._cancelar_temporizador(ap)
        if not vigente:
            return True
        ll = ap.llamada

        def efecto():
            if ok and r is not None and r.get("ok"):
                fn = self.handlers.get(ll.herramienta)
                if fn is None:
                    res = ResultadoAccion(False, f"«{ll.herramienta}» ya no está disponible.",
                                          ll.herramienta, NO_DISPONIBLE, dict(ll.args), pid)
                else:
                    res = self._ejecutar_handler(fn, ll.herramienta, r.get("args") or ll.args,
                                                 ap.ctx)
                    res.pendiente_id = pid
            elif ok:
                res = ResultadoAccion(False, "Ya hice demasiadas acciones en esta "
                                             "conversación; empieza una nueva para seguir.",
                                      ll.herramienta, SIN_PRESUPUESTO, dict(ll.args), pid)
            else:
                if estado_no == CADUCADA:
                    self._cerrar(pid)
                    msg = f"Nadie respondió en {self.timeout:g} s: no hice «{ll.herramienta}»."
                else:
                    msg = f"No lo hice: {ap.pendiente.get('resumen') or ll.herramienta} ({motivo})."
                res = ResultadoAccion(False, msg, ll.herramienta, estado_no, dict(ll.args), pid)
            self._emitir(ap.al_resultado, res)
            ap.continuar()

        self._despachar(efecto)
        return True

    def _ejecutar_handler(self, fn: Callable, nombre: str, args: dict, ctx: Any
                          ) -> ResultadoAccion:
        try:
            ok, mensaje = _normalizar_salida(fn(dict(args), ctx))
            estado = HECHA if ok else ERROR
        except Exception as e:
            ok, mensaje, estado = False, f"Falló «{nombre}»: {e}"[:300], ERROR
        try:
            with self._lock:
                self.sesion.registrar_resultado(nombre, ok, mensaje)
        except Exception:
            pass
        return ResultadoAccion(ok, mensaje, nombre, estado, dict(args))

    # ── Conversación ──
    def nueva_conversacion(self) -> None:
        """Presupuesto a cero gastado y fuera las aprobaciones pendientes."""
        try:
            with self._lock:
                self._generacion += 1
                aps = list(self._aprob.values())
                self._aprob.clear()
                for ap in aps:
                    self.sesion.rechazar(ap.pid, "conversación nueva")
                self.sesion.pendientes.clear()
                self.sesion.gastado = 0
                self.sesion.presupuesto = self.presupuesto
            for ap in aps:
                self._cancelar_temporizador(ap)
                self._despachar(lambda pid=ap.pid: self._cerrar(pid))
            self._auditar("nueva_conversacion")
        except Exception:
            pass

    def pendientes(self) -> List[dict]:
        """Aprobaciones esperando respuesta (para volver a enseñarlas en otra vista)."""
        with self._lock:
            return [dict(ap.pendiente) for ap in self._aprob.values()]

    # ── Internos ──
    @staticmethod
    def _ctx(ctx: Any, origen: str) -> dict:
        if ctx is None:
            base: dict = {}
        elif isinstance(ctx, Mapping):
            base = dict(ctx)
        else:
            base = {k: getattr(ctx, k) for k in ("proveedor", "url", "base_url", "nube", "modo")
                    if hasattr(ctx, k)}
            base["contexto"] = ctx
        base["origen"] = origen
        return base

    def _emitir(self, al_resultado, res: ResultadoAccion) -> None:
        if al_resultado is None:
            return
        try:
            al_resultado(res)
        except Exception:
            pass

    def _despachar(self, fn: Callable[[], None]) -> None:
        def seguro():
            try:
                fn()
            except Exception:
                pass
        if self._despachar_fn is not None:
            try:
                self._despachar_fn(seguro)
                return
            except Exception:
                pass
        seguro()

    def _cerrar(self, pid: str) -> None:
        if self.cerrar_aprobacion is None:
            return
        try:
            self.cerrar_aprobacion(pid)
        except Exception:
            pass

    @staticmethod
    def _cancelar_temporizador(ap: _Aprobacion) -> None:
        cancelar = getattr(ap.temporizador, "cancel", None)
        if callable(cancelar):
            try:
                cancelar()
            except Exception:
                pass

    def _auditar(self, evento: str, **datos) -> None:
        auditar = getattr(self.sesion, "_auditar", None)
        if not callable(auditar):
            return
        try:
            with self._lock:
                auditar(evento, **datos)
        except Exception:
            pass
