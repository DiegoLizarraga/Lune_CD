"""
lune_core/catalogo_herramientas.py — Qué herramientas puede pedir el modelo, con
qué argumentos y con qué riesgo.

Cada herramienta se declara UNA vez aquí (plan §2.5): descriptor para la
Política (riesgo, aprobación, coste), esquema de argumentos que valida el
Ejecutor antes de tocar nada, modos en los que tiene sentido y una plantilla
para enseñar la acción al humano cuando hay que aprobarla. Los handlers viven
en el paquete de cada función (firma `fn(args: dict, ctx) -> str`) y se
conectan en integración; aquí solo se documenta dónde (`handler`).

Reglas del catálogo:
  · Fail-closed: una herramienta sin entrada aquí no tiene esquema y el
    Ejecutor no la ejecuta, aunque esté en el Registro.
  · Ningún argumento se llama `nombre` ni `app`, salvo en `lanzar_app`:
    `Politica` busca subcadenas de DENY_APPS en esos campos y denegaría, por
    ejemplo, una alarma con texto «Lunes».
  · Los argumentos desconocidos se descartan al validar: el handler y la
    Política solo ven lo que el esquema declara.

Decisión sobre `abrir_url` y `buscar_web` (crítica d, inyección hacia
herramientas): en turnos del usuario siguen sin pedir aprobación (él escribió
«abre YouTube»; un modal por cada búsqueda sería molesto y la URL ya pasa por
`_url_segura`). En turnos con texto de terceros (título de ventana, pantalla,
Minecraft, Telegram, notas…) el Ejecutor solo deja pasar herramientas de
LECTURA, así que quedan DENEGADAS, no «aprobables»: un texto hostil podría
convencer al usuario de pulsar «Sí». Además `aprobacion_dinamica` las marca
como «requiere aprobación» si alguien las pide con origen no confiable fuera
del Ejecutor (defensa en profundidad). El formato antiguo `ABRIR_URL:` /
`ABRIR_BUSQUEDA:` / `TOOL:` ya no se ejecuta en ningún caso.

Modos: "normal" (piel web), "patata" (terminal), "br" (bajos recursos:
interfaz nativa y sprites), "asistente" (asistente en escritorio animada o de
sprites) y "vrm" (asistente en escritorio 3D). Lo que vale para "asistente" vale
también para "vrm".

Las herramientas `asistente_*` mueven el cuerpo de Lune en pantalla: en el escritorio
o, `asistente_bailar`, también en la barra lateral y en el título de la terminal. El
prefijo NO habla de «asistente» como papel (Lune es la asistente en todo): las que
solo existen en el escritorio (`es_de_escritorio`) hacen que lune_core/reglas_prompt
se lo aclare al modelo junto a la lista.
"""
from __future__ import annotations

import ipaddress
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

from .herramientas import Descriptor, Registro, Riesgo

# ── Modos y orígenes ─────────────────────────────────────────────────────────────

MODOS: Tuple[str, ...] = ("normal", "patata", "br", "asistente", "vrm")
TODOS: FrozenSet[str] = frozenset(MODOS)
_ASISTENTE: FrozenSet[str] = frozenset({"asistente", "vrm"})     # la asistente en escritorio
# Prefijo de las herramientas del cuerpo de Lune en pantalla (asistente_bailar…).
PREFIJO_ASISTENTE = "asistente_"

ORIGEN_USUARIO = "usuario"
ORIGEN_NO_CONFIABLE = "no_confiable"
# Orden que llegó desde Telegram (/pc) por el bot que lanzó Lune: las herramientas
# del modo están disponibles como con 'usuario', pero TODA llamada (también las
# de LECTURA y las `directa`) la aprueba un humano en el PC. En el historial
# cuenta como no confiable (taint).
ORIGEN_REMOTO = "remoto"
ORIGENES = (ORIGEN_USUARIO, ORIGEN_NO_CONFIABLE, ORIGEN_REMOTO)

# Argumentos que Politica revisa contra DENY_APPS.
ARGS_VIGILADOS = ("nombre", "app")


class ArgumentosInvalidos(ValueError):
    """Los argumentos que pidió el modelo no cumplen el esquema."""


# ── Esquema de argumentos ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Arg:
    """
    Un argumento de herramienta.
      tipo      "int" | "float" | "bool" | "str"
      requerido si falta (o viene null) la llamada no vale
      min/max   rango para números (inclusive)
      enum      valores válidos para str (se comparan sin mayúsculas ni tildes)
      maxlen    longitud máxima para str
      patron    expresión que el str tiene que cumplir entero (fullmatch)
      defecto   valor si falta
      recortar  True: un str largo se corta a maxlen en vez de rechazarse
                (solo para textos libres, nunca para rutas, URL o ids)
      ayuda     pista corta para el prompt ("HH:MM", "letras lmxjvsd"…)
      hueco     lo que se enseña en la firma del prompt en lugar del valor (None:
                según el tipo/ayuda; "" para «vacío salvo que haga falta»)
    """
    tipo: str
    requerido: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    enum: Optional[Tuple[str, ...]] = None
    maxlen: Optional[int] = None
    patron: Optional[str] = None
    defecto: Any = None
    recortar: bool = False
    ayuda: str = ""
    hueco: Optional[str] = None


@dataclass(frozen=True)
class Herramienta:
    """Entrada del catálogo: descriptor + esquema + modos + presentación."""
    nombre: str
    descripcion: str
    riesgo: Riesgo
    requiere_aprobacion: bool
    coste: int
    modos: FrozenSet[str]
    args: Mapping[str, Arg] = field(default_factory=dict)
    handler: str = ""              # dónde vive el handler (documentación)
    resumen: str = ""              # plantilla para el humano: "Abrir la app «{app}»"
    ejemplo: Mapping[str, Any] = field(default_factory=dict)
    existente: bool = False        # True: ya estaba antes de los cortes de ME

    def descriptor(self) -> Descriptor:
        return Descriptor(self.nombre, self.descripcion, self.riesgo,
                          requiere_aprobacion=self.requiere_aprobacion, coste=self.coste)

    def disponible_en(self, modo: Optional[str]) -> bool:
        """¿Tiene sentido en ese modo? Sin modo no se filtra."""
        if not modo:
            return True
        modo = str(modo).strip().lower()
        if modo in self.modos:
            return True
        return modo == "vrm" and "asistente" in self.modos


def _h(nombre, descripcion, riesgo, aprobacion, coste, modos, args=None, **kw) -> Herramienta:
    return Herramienta(nombre, descripcion, riesgo, aprobacion, coste,
                       frozenset(modos), dict(args or {}), **kw)


_L, _E = Riesgo.LECTURA, Riesgo.ESCRITURA
_TEXTO_CORTO = Arg("str", maxlen=60, recortar=True, defecto="")

# Orden estable: primero las cuatro que ya existían, después las de los cortes.
_LISTA: List[Herramienta] = [
    # ── Existentes (servicios/tools.py) ──
    _h("sistema_info", "Ver el uso de CPU y RAM del PC", _L, False, 0, TODOS,
       handler="servicios.tools.ToolManager._cmd_sistema_info",
       resumen="Mirar el uso de CPU y RAM", existente=True),
    _h("buscar_web", "Buscar en Google o YouTube", _E, False, 1, TODOS,
       {"consulta": Arg("str", requerido=True, maxlen=200),
        "sitio": Arg("str", enum=("google", "youtube"), defecto="google")},
       handler="servicios.tools.ToolManager._cmd_buscar_web",
       resumen="Buscar «{consulta}» en {sitio}",
       ejemplo={"consulta": "recetas de pozole", "sitio": "google"}, existente=True),
    _h("abrir_url", "Abrir una página web", _E, False, 1, TODOS,
       {"url": Arg("str", requerido=True, maxlen=500, patron=r"\S+",
                   ayuda="https://…")},
       handler="servicios.tools.ToolManager._cmd_abrir_url",
       resumen="Abrir la página {url}",
       ejemplo={"url": "https://www.youtube.com"}, existente=True),
    _h("lanzar_app", "Abrir una aplicación del PC", _E, True, 1, TODOS,
       {"app": Arg("str", requerido=True, maxlen=60, patron=r"[\w .\-()]{1,60}")},
       handler="servicios.tools.ToolManager._cmd_lanzar_app",
       resumen="Abrir la aplicación «{app}»",
       ejemplo={"app": "calculadora"}, existente=True),

    # ── Alarmas y temporizadores (P06) ──
    _h("temporizador", "Poner un temporizador", _E, False, 1, TODOS,
       {"segundos": Arg("int", requerido=True, min=1, max=90000),
        "texto": _TEXTO_CORTO},
       handler="nucleo.alarmas.herramienta_temporizador",
       resumen="Poner un temporizador de {segundos} s «{texto}»",
       # Neutro: la prueba real vio al modelo copiar «sacar la pizza» del ejemplo.
       ejemplo={"segundos": 300}),
    _h("alarma", "Poner una alarma (dias: letras lmxjvsd solo si se repite; para un día "
                 "concreto, fecha)", _E, False, 1, TODOS,
       {"hora": Arg("str", requerido=True, maxlen=5,
                    patron=r"(?:[01]?\d|2[0-3]):[0-5]\d", ayuda="HH:MM"),
        "dias": Arg("str", maxlen=7, patron=r"[lmxjvsd]*", defecto="",
                    ayuda="letras lmxjvsd", hueco=""),
        "texto": _TEXTO_CORTO,
        # Día concreto («mañana a las 7»); sin fecha, la próxima vez que lleguen esa hora.
        "fecha": Arg("str", maxlen=10, patron=r"\d{4}-\d{2}-\d{2}", ayuda="AAAA-MM-DD")},
       handler="nucleo.alarmas.herramienta_alarma",
       resumen="Poner una alarma a las {hora} «{texto}»",
       ejemplo={"hora": "07:30", "dias": "lmxjv", "texto": "gimnasio"}),
    _h("cancelar_alarma", "Quitar una alarma o temporizador por su id", _E, False, 1, TODOS,
       {"id": Arg("str", requerido=True, maxlen=40, patron=r"[\w\-]{1,40}")},
       handler="nucleo.alarmas.herramienta_cancelar",
       resumen="Quitar la alarma {id}", ejemplo={"id": "a1"}),
    _h("listar_alarmas", "Ver las alarmas y temporizadores", _L, False, 0, TODOS,
       handler="nucleo.alarmas.herramienta_listar",
       resumen="Mirar las alarmas"),

    # ── Asistente en escritorio: el cuerpo de Lune en pantalla (P02, P03, P04, P05, P14) ──
    # Cortes 9/10: con «cancion», una de la biblioteca de bailes (bailes/); en patata también
    # (el título baila al ritmo de la canción: servicios/bailes_terminal).
    # Prueba real: el modelo se inventaba canciones («Dance Monkey»): solo títulos que
    # haya dado listar_bailes o el usuario; si no, sin cancion (el handler avisa si no está).
    _h("asistente_bailar", "Bailar (cancion: solo un título de listar_bailes o que diga el "
                           "usuario; si no, omítela)", _E, False, 0,
       {"normal", "br", "asistente", "patata"},
       {"segundos": Arg("int", min=5, max=300, defecto=30),
        "cancion": Arg("str", maxlen=80, recortar=True)},
       handler="nucleo.baile.herramienta_bailar",
       resumen="Bailar {segundos} s", ejemplo={"segundos": 30}),
    _h("parar_baile", "Dejar de bailar", _E, False, 0, {"normal", "br", "asistente", "patata"},
       handler="nucleo.baile.herramienta_parar", resumen="Dejar de bailar"),
    # Títulos saneados (son nombres de archivo). Sin controlador lee bailes/ sin tocar nada.
    _h("listar_bailes", "Ver tus bailes (úsala si preguntan cuáles sabes)", _L, False, 0, TODOS,
       {"texto": _TEXTO_CORTO},
       handler="nucleo.bailes.herramienta_listar", resumen="Mirar tus bailes"),
    _h("asistente_dormir", "Echarte a dormir", _E, False, 0, _ASISTENTE,
       handler="nucleo.sueno.herramienta_dormir", resumen="Echarse a dormir"),
    _h("asistente_despertar", "Despertarte", _E, False, 0, _ASISTENTE,
       handler="nucleo.sueno.herramienta_despertar", resumen="Despertarse"),
    _h("asistente_pantalla_grande", "Ponerte en pantalla grande o quitarla", _E, False, 0,
       _ASISTENTE,
       {"activar": Arg("bool", requerido=True),
        "minutos": Arg("int", min=1, max=120)},
       handler="nucleo.pantalla_grande.herramienta",
       resumen="Pantalla grande: {activar}", ejemplo={"activar": True, "minutos": 5}),
    # «ventana» solo si avatar.sentarse_ventanas está activo: lo comprueba el handler.
    # Cortes 7/8: con la asistente en escritorio a la vista, sea cual sea (la 3D se sienta;
    # la animada y los sprites se apoyan de pie en el borde y lo siguen igual). La
    # descripción ya no lo cuenta (11): el modelo no lo necesita para pedirla y el hueco
    # del prompt es para la nota «asistente_* = tu cuerpo en el escritorio».
    _h("asistente_sentarse", "Sentarte en la barra de tareas o en una ventana, o bajarte",
       _E, False, 0, _ASISTENTE,
       {"sitio": Arg("str", requerido=True, enum=("barra", "ventana", "bajar"))},
       handler="nucleo.asiento.herramienta",
       resumen="Sentarse: {sitio}", ejemplo={"sitio": "barra"}),
    # Solo la 3D cambia de tamaño (con sprites o animada no se vería nada).
    _h("asistente_tamano", "Cambiar tu tamaño", _E, False, 0, {"vrm"},
       {"tamano": Arg("str", requerido=True, enum=("pequeno", "normal", "grande"))},
       handler="nucleo.vrm.herramienta_tamano",
       resumen="Cambiar el tamaño a {tamano}", ejemplo={"tamano": "grande"}),

    # ── Comida (P07) y voz (P08) ──
    _h("dar_de_comer", "Comer algo", _E, False, 0, TODOS,
       {"comida": Arg("str", requerido=True, enum=("batido", "pastel"))},
       handler="nucleo.comida.herramienta",
       resumen="Comer: {comida}", ejemplo={"comida": "batido"}),
    # El patrón solo filtra caracteres; servicios.voces valida que la voz exista.
    _h("cambiar_voz", "Cambiar tu voz", _E, False, 1, TODOS,
       {"voz": Arg("str", requerido=True, maxlen=80, patron=r"[A-Za-z0-9_\-]{2,80}",
                   ayuda="p. ej. es-MX-DaliaNeural", hueco="es-XX-NombreNeural")},
       handler="servicios.voces.herramienta",
       resumen="Cambiar la voz a {voz}", ejemplo={"voz": "es-MX-DaliaNeural"}),

    # ── Pantalla (integración, companion) ──
    # LECTURA, pero con la nube la captura sale del PC → aprobacion_dinamica.
    _h("comentar_pantalla", "Mirar la pantalla y comentarla", _L, False, 1, _ASISTENTE,
       handler="ui.companion (integración)",
       resumen="Hacer una captura de pantalla para comentarla"),

    # ── Minecraft (P13) ──
    _h("minecraft_estado", "Ver el estado del bot de Minecraft", _L, False, 0, TODOS,
       handler="lune_core.minecraft.herramienta_estado",
       resumen="Mirar el estado del bot de Minecraft"),
    _h("minecraft_orden", "Dar una orden al bot de Minecraft", _E, True, 1, TODOS,
       {"orden": Arg("str", requerido=True, maxlen=80)},
       handler="lune_core.minecraft.herramienta_orden",
       resumen="Mandar al bot de Minecraft: «{orden}»", ejemplo={"orden": "sígueme"}),
    _h("minecraft_bot", "Conectar o desconectar el bot de Minecraft", _E, False, 1, TODOS,
       {"accion": Arg("str", requerido=True, enum=("conectar", "desconectar"))},
       handler="lune_core.minecraft.herramienta_bot",
       resumen="Bot de Minecraft: {accion}", ejemplo={"accion": "conectar"}),
]

CATALOGO: Dict[str, Herramienta] = {h.nombre: h for h in _LISTA}
ESQUEMAS: Dict[str, Mapping[str, Arg]] = {h.nombre: h.args for h in _LISTA}
EXISTENTES: Tuple[str, ...] = tuple(h.nombre for h in _LISTA if h.existente)
NUEVAS: Tuple[str, ...] = tuple(h.nombre for h in _LISTA if not h.existente)


def obtener(nombre: str, catalogo: Optional[Mapping[str, Herramienta]] = None
            ) -> Optional[Herramienta]:
    return (catalogo if catalogo is not None else CATALOGO).get(str(nombre or "").strip())


def es_de_escritorio(h: Optional[Herramienta]) -> bool:
    """¿Es una `asistente_*` que solo existe con la asistente en escritorio a la vista
    (dormir, sentarse, tamaño…)? `asistente_bailar` no: también baila en la barra
    lateral y en la terminal."""
    return (h is not None and h.nombre.startswith(PREFIJO_ASISTENTE)
            and bool(h.modos) and h.modos <= _ASISTENTE)


def registrar_extras(registro: Registro) -> Registro:
    """Registra los descriptores de las herramientas nuevas (no pisa las existentes)."""
    for nombre in NUEVAS:
        registro.registrar(CATALOGO[nombre].descriptor())
    return registro


def registro_completo() -> Registro:
    """Registro con las cuatro de siempre + todas las nuevas."""
    from .herramientas import registro_por_defecto
    return registrar_extras(registro_por_defecto())


def disponibles_en(modo: Optional[str], con_handler, registro: Optional[Registro] = None,
                   catalogo: Optional[Mapping[str, Herramienta]] = None) -> List[str]:
    """Nombres (en orden de catálogo) con handler, válidos en `modo` y registrados."""
    cat = catalogo if catalogo is not None else CATALOGO
    con = {str(n) for n in (con_handler or ())}
    fuera = []
    for nombre, h in cat.items():
        if nombre not in con or not h.disponible_en(modo):
            continue
        if registro is not None and registro.get(nombre) is None:
            continue
        fuera.append(nombre)
    return fuera


# ── Aprobación dinámica ──────────────────────────────────────────────────────────

def valor_ctx(ctx: Any, clave: str, defecto: Any = None) -> Any:
    """Lee `clave` de un ctx que puede ser dict u objeto."""
    if ctx is None:
        return defecto
    if isinstance(ctx, Mapping):
        return ctx.get(clave, defecto)
    return getattr(ctx, clave, defecto)


def _host_local(url: str) -> bool:
    try:
        host = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False          # un nombre que no se puede comprobar sin red → nube
    return ip.is_loopback or ip.is_private or ip.is_link_local


def es_nube(ctx: Any) -> bool:
    """
    ¿Lo que se mande al modelo sale del PC/LAN? Fail-closed: si no se sabe, sí.
      ctx["nube"] (bool) manda si está.
      openrouter → nube. ollama → local salvo URL pública. compat → según su
      URL (LM Studio en localhost es local; Groq/OpenAI/… son nube).
    """
    nube = valor_ctx(ctx, "nube")
    if isinstance(nube, bool):
        return nube
    proveedor = str(valor_ctx(ctx, "proveedor", "") or "").strip().lower()
    url = str(valor_ctx(ctx, "url", "") or valor_ctx(ctx, "base_url", "") or "").strip()
    if proveedor == "ollama":
        return bool(url) and not _host_local(url)
    if proveedor == "compat":
        return not (url and _host_local(url))
    return True


def aprobacion_dinamica(nombre: str, ctx: Any = None, args: Optional[Mapping] = None) -> bool:
    """
    Aprobación que depende del contexto y no solo del descriptor:
      · origen 'remoto' (orden desde Telegram): sí, siempre, sea cual sea la herramienta.
      · comentar_pantalla: sí si el proveedor es la nube (la captura sale del PC).
      · minecraft_bot: sí al conectar.
      · abrir_url / buscar_web: sí si el origen no es el usuario.
    """
    args = args or {}
    origen = str(valor_ctx(ctx, "origen", ORIGEN_USUARIO) or ORIGEN_USUARIO)
    if origen.strip().lower() == ORIGEN_REMOTO or valor_ctx(ctx, "remoto") is True:
        return True
    if nombre == "comentar_pantalla":
        return es_nube(ctx)
    if nombre == "minecraft_bot":
        return str(args.get("accion", "")).lower() == "conectar"
    if nombre in ("abrir_url", "buscar_web"):
        return origen != ORIGEN_USUARIO
    return False


# ── Validación ───────────────────────────────────────────────────────────────────

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_VERDADERO = {"true", "si", "sí", "yes", "1", "on", "activar", "activa"}
_FALSO = {"false", "no", "0", "off", "desactivar", "desactiva"}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _numero(clave: str, valor: Any, entero: bool) -> float:
    if isinstance(valor, bool):
        raise ArgumentosInvalidos(f"«{clave}» tiene que ser un número")
    if isinstance(valor, str):
        t = valor.strip()
        patron = r"[+-]?\d+" if entero else r"[+-]?(?:\d+\.?\d*|\.\d+)"
        if not re.fullmatch(patron, t):
            raise ArgumentosInvalidos(f"«{clave}» tiene que ser un número")
        valor = int(t) if entero else float(t)
    if not isinstance(valor, (int, float)):
        raise ArgumentosInvalidos(f"«{clave}» tiene que ser un número")
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ArgumentosInvalidos(f"«{clave}» no es un número válido")
    if entero:
        if isinstance(valor, float):
            if not valor.is_integer():
                raise ArgumentosInvalidos(f"«{clave}» tiene que ser entero")
            valor = int(valor)
        return valor
    return float(valor)


def _validar_uno(clave: str, esq: Arg, valor: Any) -> Any:
    if esq.tipo in ("int", "float"):
        v = _numero(clave, valor, esq.tipo == "int")
        if esq.min is not None and v < esq.min:
            raise ArgumentosInvalidos(f"«{clave}» mínimo {esq.min:g}")
        if esq.max is not None and v > esq.max:
            raise ArgumentosInvalidos(f"«{clave}» máximo {esq.max:g}")
        return v
    if esq.tipo == "bool":
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, int) and valor in (0, 1):
            return bool(valor)
        t = str(valor).strip().lower()
        if t in _VERDADERO:
            return True
        if t in _FALSO:
            return False
        raise ArgumentosInvalidos(f"«{clave}» tiene que ser true o false")
    if esq.tipo == "str":
        if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
            raise ArgumentosInvalidos(f"«{clave}» tiene que ser texto")
        t = _CONTROL.sub(" ", str(valor)).strip()
        if esq.enum is not None:
            clave_enum = _sin_tildes(t).lower()
            for opcion in esq.enum:
                if _sin_tildes(opcion).lower() == clave_enum:
                    return opcion
            raise ArgumentosInvalidos(f"«{clave}» tiene que ser {'|'.join(esq.enum)}")
        if esq.maxlen is not None and len(t) > esq.maxlen:
            if not esq.recortar:
                raise ArgumentosInvalidos(f"«{clave}» es demasiado largo (máx. {esq.maxlen})")
            t = t[:esq.maxlen].rstrip()
        if esq.requerido and not t:
            raise ArgumentosInvalidos(f"falta «{clave}»")
        if esq.patron is not None and t and not re.fullmatch(esq.patron, t):
            raise ArgumentosInvalidos(f"«{clave}» no tiene el formato esperado")
        return t
    raise ArgumentosInvalidos(f"tipo desconocido en el esquema de «{clave}»")


def validar(args: Any, esquema: Mapping[str, Arg]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Valida y normaliza `args` contra `esquema`. Devuelve (args_limpios,
    claves_ignoradas). Lanza ArgumentosInvalidos si algo no cuadra.
    """
    if args is None:
        args = {}
    if not isinstance(args, Mapping):
        raise ArgumentosInvalidos("los argumentos tienen que ser un objeto {…}")
    limpio: Dict[str, Any] = {}
    for clave, esq in esquema.items():
        valor = args.get(clave)
        if valor is None or (isinstance(valor, str) and not _CONTROL.sub("", valor).strip()):
            if esq.requerido:
                raise ArgumentosInvalidos(f"falta «{clave}»")
            if esq.defecto is not None:
                limpio[clave] = esq.defecto
            continue
        limpio[clave] = _validar_uno(clave, esq, valor)
    ignorados = sorted(str(k) for k in args if k not in esquema)
    return limpio, ignorados


# ── Presentación ─────────────────────────────────────────────────────────────────

class _Faltan(dict):
    def __missing__(self, clave):
        return "…"


def _presentar(valor: Any) -> str:
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    return str(valor)


def resumen(nombre: str, args: Optional[Mapping] = None, ctx: Any = None,
            catalogo: Optional[Mapping[str, Herramienta]] = None) -> str:
    """Frase corta para enseñar al humano qué se va a hacer."""
    h = obtener(nombre, catalogo)
    args = dict(args or {})
    if h is None:
        return f"Acción «{nombre}»"
    if nombre == "comentar_pantalla" and es_nube(ctx):
        return "Hacer una captura de pantalla y enviarla a la IA en la nube (sale de tu PC)"
    if nombre == "lanzar_app" and args.get("app"):
        # Lo que se aprueba es el programa real: «terminal» abre cmd.
        from .herramientas import resolver_app
        real = resolver_app(str(args["app"]))
        if real.strip().lower() != str(args["app"]).strip().lower():
            return f"Abrir la aplicación «{args['app']}» (programa: {real})"
    plantilla = h.resumen or h.descripcion
    try:
        texto = plantilla.format_map(_Faltan({k: _presentar(v) for k, v in args.items()}))
    except (ValueError, IndexError, KeyError):
        texto = h.descripcion
    return re.sub(r"\s*«»", "", texto).strip()


def _marcador_arg(a: Arg) -> Any:
    """Hueco de un argumento en la firma: lo que el modelo sustituye por su valor."""
    if a.hueco is not None:
        return a.hueco
    if a.tipo in ("int", "float"):
        return "N"
    if a.tipo == "bool":
        return "true|false"
    if a.enum:
        return "|".join(a.enum)
    return a.ayuda or "…"


def firma_marca(h: Herramienta) -> str:
    """
    La firma para el prompt, con la MISMA forma que la llamada (prueba real: con
    `nombre(arg: tipo)` los modelos pequeños escribían <|nombre(arg=…)|>):
        <|CALL ["temporizador", {"segundos": N, "texto": "…"}]|>
    Números y booleanos van sin comillas (N, true|false); el resto, entre comillas.
    """
    partes = []
    for clave, a in h.args.items():
        v = _marcador_arg(a)
        partes.append(f'"{clave}": {v}' if a.tipo in ("int", "float", "bool") else f'"{clave}": "{v}"')
    return f'<|CALL ["{h.nombre}", {{{", ".join(partes)}}}]|>'


# ── Cotejo con lo que escribió la persona ─────────────────────────────────────────

def _hhmm(valor: Any) -> str:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(valor or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else str(valor or "")


def cotejar(nombre: str, args: Mapping[str, Any], ctx: Any = None
            ) -> Tuple[Dict[str, Any], Dict[str, Tuple[Any, Any]]]:
    """
    Cotejo barato (prueba real: 45 s por «veinte minutos», días «l» por «mañana»):
    si el mensaje de la persona (ctx['mensaje_usuario'], hora ctx['momento']) trae
    una duración u hora que nucleo.alarmas_nl entiende y la llamada del modelo a
    `temporizador`/`alarma` la contradice, manda la de la persona. Devuelve
    (args, cambios {clave: (del modelo, de la persona)}); sin mensaje, sin
    pistas o sin contradicción, los args tal cual y {}.
    """
    args = dict(args or {})
    if nombre not in ("temporizador", "alarma"):
        return args, {}
    texto = valor_ctx(ctx, "mensaje_usuario")
    if not isinstance(texto, str) or not texto.strip():
        return args, {}
    try:
        from nucleo.alarmas_nl import pistas
        p = pistas(texto, valor_ctx(ctx, "momento"))
    except Exception:
        return args, {}
    cambios: Dict[str, Tuple[Any, Any]] = {}

    def poner(clave, valor):
        if args.get(clave) != valor:
            cambios[clave] = (args.get(clave), valor)
            args[clave] = valor

    if nombre == "temporizador":
        if p.get("segundos"):
            poner("segundos", int(p["segundos"]))
        return args, cambios
    horas = list(p.get("horas") or [])
    if horas and _hhmm(args.get("hora")) not in horas:
        poner("hora", p["hora"])
    if p.get("fecha"):
        poner("dias", "")
        poner("fecha", p["fecha"])
    elif p.get("dias"):
        poner("dias", p["dias"])
        if args.get("fecha"):
            cambios["fecha"] = (args.pop("fecha"), None)
    return args, cambios


def firma(h: Herramienta) -> str:
    """`temporizador(segundos: entero 1-90000, texto?: texto ≤60)` (forma antigua;
    el prompt usa firma_marca)."""
    partes = []
    for clave, a in h.args.items():
        marca = "" if a.requerido else "?"
        if a.enum:
            tipo = "|".join(a.enum)
        elif a.tipo == "int":
            tipo = "entero"
            if a.min is not None and a.max is not None:
                tipo += f" {a.min:g}-{a.max:g}"
        elif a.tipo == "float":
            tipo = "número"
        elif a.tipo == "bool":
            tipo = "true|false"
        else:
            tipo = a.ayuda or (f"texto ≤{a.maxlen}" if a.maxlen else "texto")
        partes.append(f"{clave}{marca}: {tipo}")
    return f"{h.nombre}({', '.join(partes)})"
