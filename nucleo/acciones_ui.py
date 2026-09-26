"""
nucleo/acciones_ui.py — Catálogo común de acciones de la interfaz (corte 4).

Qué es
------
Las mismas acciones («sacar a la mascota», «voz», «modo juego», «dormir»…) se
piden desde cinco sitios: el menú de la bandeja, el menú radial de la mascota,
los atajos globales, las tarjetas de la web y el /menu de patata. En vez de que
cada uno sepa qué hacer, todos hablan con un `Despachador`:

    desp = Despachador()
    desp.registrar("voz", anfitrion.alternar_voz, marcado=anfitrion.voz_on)
    desp.ejecutar("voz")                      # True si se ejecutó sin fallar

- `ACCIONES`: el catálogo (id → Accion con etiqueta, icono, grupo, modos en los
  que existe, si es un interruptor ✔ y dónde puede ponerse: radial, bandeja,
  atajo). Contiene todos los ids que aparecen en DEFAULT_CONFIG
  (menu_radial.*, bandeja.acciones, atajos.lista), también los de cortes
  siguientes (bailar, alarma, pantalla_grande, bajar, comer_*…).
- Un id sin handler registrado NO sale en la bandeja, en el radial ni en los
  atajos: las funciones de cortes siguientes aparecen solas cuando su
  controlador registra el handler.
- Visibilidad por estado (reglas de Mate-Engine): sin ajustes ni chat en
  pantalla grande; «bajar» solo sentada; «dormir» pasa a «Despertar»; tamaño y
  encuadre solo con la mascota 3D; «llamada» solo en la piel web; expresiones y
  bailar también con Lune en la barra lateral de la web (`Contexto.mascota_barra`)…
- `items_radial()` y `menu_bandeja()` construyen lo que pintan el radial y la
  bandeja (datos puros; los widgets están en ui/menu_radial.py y ui/bandeja.py).

Sin Qt: lo usan también patata y los tests.

Contexto de la interfaz
-----------------------
`Contexto` es la foto de lo que no está en el BusEstado (qué anfitrión, si la voz
está encendida, el tema…). La construye quien monta los servicios
(ui/montaje_escritorio.py) cada vez que se abre un menú.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

_log = logging.getLogger("lune.acciones_ui")

# Modos de interfaz: "normal" (piel web), "br" (nativa de bajos recursos), "patata".
MODOS_VENTANA = frozenset({"normal", "br"})
MODOS_TODOS = frozenset({"normal", "br", "patata"})
SOLO_WEB = frozenset({"normal"})

# Dónde puede ponerse una acción.
USO_RADIAL, USO_BANDEJA, USO_ATAJO = "radial", "bandeja", "atajo"
USOS_TODOS = frozenset({USO_RADIAL, USO_BANDEJA, USO_ATAJO})

MAX_RADIAL = 10


@dataclass(frozen=True)
class Accion:
    """Una acción del catálogo.

    `interruptor`: se pinta con ✔ (voz, modo fantasma…). `etiqueta_on`: texto
    cuando está «encendida» si NO es un interruptor (Dormir → Despertar). `usos`:
    dónde puede elegirse (radial, bandeja, atajo); una acción interna (la
    expresión concreta del segundo radial) no tiene ninguno.
    """
    id: str
    etiqueta: str
    icono: str
    grupo: str
    modos: frozenset = MODOS_VENTANA
    interruptor: bool = False
    etiqueta_on: str = ""
    usos: frozenset = USOS_TODOS
    icono_on: str = ""


class Contexto(NamedTuple):
    """Lo que la interfaz sabe y el BusEstado no (se rehace al abrir cada menú)."""
    modo: str = "normal"                  # "normal" (web) · "br" (nativa) · "patata"
    render: str = ""                      # vrm · animado · sprites · "" (sin mascota)
    mascota_visible: bool = False
    voz_on: bool = False
    llamada_on: bool = False
    fantasma_on: bool = False
    comentarios_auto_on: bool = False
    siempre_encima: bool = True
    juego_forzado: Optional[bool] = None  # None = automático
    autoinicio_on: bool = False
    en_barra_on: bool = True
    varios_vrm: bool = False
    tema_preset: str = "cian"
    # Añadidos del corte 4 (con valor por defecto: no rompen a quien no los pase).
    juego_activo: bool = False
    juego_motivo: str = ""
    tamano: str = ""                      # avatar.vrm_tamano actual
    encuadre: str = ""                    # avatar.vrm_encuadre actual
    # Piel web con la flotante guardada: Lune se ve en la barra lateral de la ventana
    # (el radial SVG se abre sobre ella). Cuenta como mascota para expresiones y baile.
    mascota_barra: bool = False


@dataclass(frozen=True)
class ItemMenu:
    """Una entrada del menú de la bandeja. `hijos` = submenú; `separador` = línea."""
    id: str
    etiqueta: str
    arg: str = ""
    marcado: Optional[bool] = None        # None = sin ✔; True/False = con casilla
    habilitado: bool = True
    negrita: bool = False
    hijos: Tuple["ItemMenu", ...] = ()
    separador: bool = False


@dataclass(frozen=True)
class ItemRadial:
    """Un botón del menú radial."""
    id: str
    etiqueta: str
    icono: str
    arg: str = ""
    habilitado: bool = True
    marcado: Optional[bool] = None        # interruptores: punto de «encendido»


def _a(id_, etiqueta, icono, grupo, modos=MODOS_VENTANA, interruptor=False, etiqueta_on="",
       usos=USOS_TODOS, icono_on=""):
    return Accion(id_, etiqueta, icono, grupo, frozenset(modos), interruptor, etiqueta_on,
                  frozenset(usos), icono_on)


_R, _B, _T = USO_RADIAL, USO_BANDEJA, USO_ATAJO

# Orden = orden de presentación en el catálogo de la web. Modos: casi todo es de
# las ventanas (web y nativa); en patata (/menu) solo lo que la terminal sabe hacer:
# voz, modo juego, tema, autoinicio, liberar memoria y salir.
ACCIONES: Dict[str, Accion] = {a.id: a for a in (
    # ── Lune (ventana y app) ──
    _a("mostrar_lune", "Abrir Lune", "window", "lune", MODOS_VENTANA, usos={_R, _B, _T}),
    _a("ajustes", "Ajustes", "gear", "lune"),
    _a("menu_radial", "Menú radial", "radial", "lune", usos={_T}),
    _a("salir", "Salir", "log_out", "lune", MODOS_TODOS, usos={_R, _B}),
    # ── Mascota ──
    _a("mascota", "Sacar a la mascota", "user", "mascota", etiqueta_on="Guardar a la mascota"),
    _a("chat", "Escribirle", "message", "mascota"),
    _a("comentar", "Comentar la pantalla", "eye", "mascota"),
    _a("expresiones", "Expresiones", "smile", "mascota", usos={_R}),
    _a("expresion", "Expresión", "smile", "mascota", usos=()),
    _a("dormir", "Dormir", "moon", "mascota", etiqueta_on="Despertar", icono_on="sun"),
    _a("fantasma", "Modo fantasma", "ghost", "mascota", interruptor=True),
    _a("comentarios_auto", "Comentarios automáticos", "message_dots", "mascota", interruptor=True),
    _a("siempre_encima", "Siempre encima", "pin", "mascota", interruptor=True, usos={_R, _B}),
    _a("tamano", "Tamaño", "maximize", "mascota", usos={_R, _B}),
    _a("encuadre", "Encuadre", "frame", "mascota", usos={_R, _B}),
    _a("esquina", "Llevar a la esquina", "corner", "mascota"),
    _a("cerrar_mascota", "Cerrar mascota", "close", "mascota", usos={_R, _B}),
    _a("bajar", "Bajar", "arrow_down", "mascota"),                               # corte 7
    _a("pantalla_grande", "Pantalla grande", "monitor", "mascota",
       etiqueta_on="Salir de pantalla grande"),                                    # corte 5
    # ── Voz ──
    _a("voz", "Voz", "volume", "voz", MODOS_TODOS, interruptor=True, icono_on="volume"),
    _a("llamada", "Llamada", "phone", "voz", SOLO_WEB, interruptor=True),
    # ── Baile (corte 6) ──
    _a("bailar", "Bailar", "music", "baile", etiqueta_on="Parar el baile"),
    _a("baile_pausa", "Pausar el baile", "pause", "baile"),
    # ── Alarmas (corte 5) ──
    _a("alarma", "Alarmas", "alarm", "alarma"),
    _a("temporizador_rapido", "Temporizador rápido", "timer", "alarma"),
    # ── Comida (corte 8) ──
    _a("comida", "Comida", "cake", "comida"),
    _a("comer_batido", "Batido", "cup", "comida"),
    _a("comer_pastel", "Pastel", "cake", "comida"),
    _a("guardar_comida", "Guardar la comida", "package", "comida"),
    # ── Modo juego, tema y sistema ──
    _a("modo_juego_forzar", "Modo juego", "gamepad", "juego", MODOS_TODOS, interruptor=True),
    _a("tema", "Tema", "palette", "tema", MODOS_TODOS, usos={_B}),
    _a("autoinicio", "Arrancar con Windows", "power", "sistema", MODOS_TODOS, interruptor=True, usos={_B}),
    _a("liberar_memoria", "Liberar memoria", "cpu", "sistema", MODOS_TODOS),
    _a("en_barra_tareas", "Mostrar en la barra de tareas", "taskbar", "sistema",
       interruptor=True, usos={_B}),
    # ── Integraciones (corte 8 y 10) ──
    _a("discord", "Discord", "message", "integraciones", interruptor=True, usos={_B, _R}),
    _a("minecraft", "Minecraft", "box", "integraciones", interruptor=True, usos={_B, _R}),
)}

# Segundo radial de «expresiones»: (arg para set_estado, etiqueta, icono).
EXPRESIONES: Tuple[Tuple[str, str, str], ...] = (
    ("happy", "Contenta", "smile"),
    ("sad", "Triste", "frown"),
    ("angry", "Enfadada", "angry"),
    ("surprised", "Sorprendida", "surprised"),
    ("thinking", "Pensativa", "thinking"),
    ("wave", "Saludar", "hand"),
)
TAMANOS: Tuple[Tuple[str, str], ...] = (("pequeno", "Pequeña"), ("normal", "Normal"), ("grande", "Grande"))
ENCUADRES: Tuple[Tuple[str, str], ...] = (("retrato", "Retrato (cara y torso)"), ("cuerpo", "Cuerpo entero"))
NOMBRES_TEMA: Dict[str, str] = {
    "cian": "Cian", "magenta_mate": "Magenta mate", "violeta": "Violeta",
    "rojo_neon": "Rojo neón", "ambar": "Ámbar", "verde_acido": "Verde ácido",
    "personalizado": "Personalizado",
}
MOTIVOS_JUEGO: Dict[str, str] = {
    "quns3": "pantalla completa", "quns4": "presentación", "quns2": "vídeo a pantalla completa",
    "sin_bordes": "ventana sin bordes", "lista": "app de tu lista", "ruta": "juego instalado",
    "forzado": "forzado",
}

# Acciones que solo tienen sentido con la mascota a la vista (se ocultan si no).
_NECESITAN_MASCOTA = frozenset({"dormir", "esquina", "cerrar_mascota", "expresiones", "expresion",
                                "tamano", "encuadre", "bajar", "bailar", "baile_pausa",
                                "comer_batido", "comer_pastel", "guardar_comida"})
# Las que también hace Lune en la barra lateral de la web (sin la flotante a la vista):
# la barra pone la expresión y baila con el estado del baile. Dormir no: el sueño es de
# la flotante (BusEstado.durmiendo) y la barra no tiene a quién despertar.
_VALEN_CON_BARRA = frozenset({"expresiones", "expresion", "bailar", "baile_pausa"})
# Solo la mascota con página (animada o 3D) comenta la pantalla.
_SIN_SPRITES = frozenset({"comentar", "comentarios_auto"})


# ── Reglas puras ─────────────────────────────────────────────────────────────────

def en_modo(id_: str, modo: str) -> bool:
    """¿Existe la acción `id_` en el modo de interfaz `modo`?"""
    a = ACCIONES.get(id_)
    return a is not None and modo in a.modos


def hay_mascota(id_: str, ctx: Contexto) -> bool:
    """¿Hay a quién hacerle `id_`? La flotante a la vista, o (expresiones y baile) Lune
    en la barra lateral de la web."""
    return bool(ctx.mascota_visible or (ctx.mascota_barra and id_ in _VALEN_CON_BARRA))


def visible(id_: str, estado: Any, ctx: Contexto) -> bool:
    """¿Se enseña `id_` con este estado de la mascota y este contexto?

    No mira si hay handler (eso es `Despachador.disponibles`)."""
    a = ACCIONES.get(id_)
    if a is None or ctx.modo not in a.modos:
        return False
    grande = bool(getattr(estado, "grande", False))
    if id_ in ("ajustes", "chat") and grande:
        return False                                   # como ME: nada de ajustes en pantalla grande
    if id_ == "bajar" and not getattr(estado, "sentada", ""):
        return False
    if id_ in ("tamano", "encuadre") and ctx.render != "vrm":
        return False
    if id_ in _NECESITAN_MASCOTA and not hay_mascota(id_, ctx):
        return False
    if id_ in _SIN_SPRITES and ctx.render == "sprites":
        return False
    if id_ == "baile_pausa" and not getattr(estado, "bailando", ""):
        return False
    return True


def marcado_por_defecto(id_: str, estado: Any, ctx: Contexto) -> Optional[bool]:
    """Estado «encendido» de una acción a partir del contexto y del BusEstado."""
    m = {
        "voz": ctx.voz_on, "llamada": ctx.llamada_on, "fantasma": ctx.fantasma_on,
        "comentarios_auto": ctx.comentarios_auto_on, "siempre_encima": ctx.siempre_encima,
        "modo_juego_forzar": ctx.juego_activo, "autoinicio": ctx.autoinicio_on,
        "en_barra_tareas": ctx.en_barra_on, "mascota": ctx.mascota_visible,
    }
    if id_ in m:
        return bool(m[id_])
    if id_ == "dormir":
        return bool(getattr(estado, "durmiendo", False))
    if id_ == "bailar":
        return bool(getattr(estado, "bailando", ""))
    if id_ == "pantalla_grande":
        return bool(getattr(estado, "grande", False))
    return None


def etiqueta_de(id_: str, marcado: Optional[bool] = None) -> str:
    """Texto de la acción: `etiqueta_on` si está encendida y lo tiene."""
    a = ACCIONES.get(id_)
    if a is None:
        return str(id_)
    return a.etiqueta_on if (marcado and a.etiqueta_on) else a.etiqueta


def icono_de(id_: str, marcado: Optional[bool] = None) -> str:
    a = ACCIONES.get(id_)
    if a is None:
        return ""
    return a.icono_on if (marcado and a.icono_on) else a.icono


def nombre_tema(preset: str) -> str:
    return NOMBRES_TEMA.get(preset) or str(preset).replace("_", " ").capitalize()


def texto_motivo_juego(motivo: str) -> str:
    return MOTIVOS_JUEGO.get(motivo, motivo)


def validar_lista(ids: Any, *, maximo: Optional[int] = None, uso: Optional[str] = None) -> List[str]:
    """Lista limpia de ids: solo textos del catálogo, sin duplicados (se queda el
    primero), en su orden y como mucho `maximo`. Con `uso` ("radial", "bandeja",
    "atajo") descarta las que no pueden ponerse ahí. Lo que no es una lista → []."""
    if not isinstance(ids, (list, tuple)):
        return []
    vistos: List[str] = []
    for x in ids:
        if not isinstance(x, str) or x in vistos:
            continue
        a = ACCIONES.get(x)
        if a is None or (uso is not None and uso not in a.usos):
            continue
        vistos.append(x)
        if maximo is not None and len(vistos) >= int(maximo):
            break
    return vistos


# ── Despachador ──────────────────────────────────────────────────────────────────

def _acepta(fn: Callable) -> Tuple[bool, bool, frozenset]:
    """(acepta un posicional, acepta **kw, nombres de parámetros) de `fn`."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return True, False, frozenset()
    pos = kw = False
    nombres = set()
    for p in sig.parameters.values():
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL):
            pos = True
        if p.kind == p.VAR_KEYWORD:
            kw = True
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            nombres.add(p.name)
    return pos, kw, frozenset(nombres)


class Despachador:
    """Registro id → handler. Un handler es `fn()`, `fn(arg)` o `fn(arg, **kw)`:
    se le pasa lo que acepte. `marcado`: función sin argumentos que dice si la
    acción está encendida (para los ✔); si no se da, se deduce del Contexto."""

    def __init__(self):
        self._fns: Dict[str, Callable] = {}
        self._firmas: Dict[str, Tuple[bool, bool, frozenset]] = {}
        self._marcados: Dict[str, Callable[[], Any]] = {}

    def registrar(self, id_: str, fn: Callable, *, marcado: Optional[Callable[[], Any]] = None) -> None:
        if id_ not in ACCIONES:
            raise ValueError(f"acción desconocida: {id_!r}")
        if not callable(fn):
            raise TypeError(f"el handler de {id_!r} no es invocable")
        self._fns[id_] = fn
        self._firmas[id_] = _acepta(fn)
        if marcado is not None:
            self._marcados[id_] = marcado
        else:
            self._marcados.pop(id_, None)

    def quitar(self, id_: str) -> bool:
        self._marcados.pop(id_, None)
        self._firmas.pop(id_, None)
        return self._fns.pop(id_, None) is not None

    def tiene(self, id_: str) -> bool:
        return id_ in self._fns

    def ids(self) -> List[str]:
        return [i for i in ACCIONES if i in self._fns]

    def ejecutar(self, id_: str, arg: str = "", **kw) -> bool:
        """Ejecuta la acción. True si tenía handler y no falló (lo que devuelva el
        handler da igual: «alternar» puede devolver False y haberse hecho)."""
        fn = self._fns.get(id_)
        if fn is None:
            return False
        pos, var_kw, nombres = self._firmas.get(id_) or _acepta(fn)
        extra = kw if var_kw else {k: v for k, v in kw.items() if k in nombres}
        try:
            if pos:
                fn(str(arg or ""), **extra)
            else:
                fn(**extra)
        except Exception:
            _log.exception("acción %s falló", id_)
            return False
        return True

    def marcado(self, id_: str) -> Optional[bool]:
        f = self._marcados.get(id_)
        if f is None:
            return None
        try:
            v = f()
        except Exception:
            _log.exception("marcado de %s falló", id_)
            return None
        return None if v is None else bool(v)

    def marcado_en(self, id_: str, estado: Any, ctx: Contexto) -> Optional[bool]:
        """El del handler si lo dio; si no, el del contexto."""
        m = self.marcado(id_)
        return m if m is not None else marcado_por_defecto(id_, estado, ctx)

    def disponibles(self, estado: Any, ctx: Contexto, ids: Optional[Iterable[str]] = None) -> List[str]:
        """Ids con handler, del modo actual y visibles en este estado (en el orden
        de `ids` o del catálogo)."""
        lista = list(ACCIONES) if ids is None else [i for i in ids if isinstance(i, str)]
        return [i for i in lista if i in self._fns and visible(i, estado, ctx)]


# ── Lo que pintan el radial y la bandeja ─────────────────────────────────────────

def items_radial(desp: Despachador, estado: Any, ctx: Contexto, ids: Any) -> List[ItemRadial]:
    """Botones del radial: los de `ids` (menu_radial.principal) validados, como
    mucho MAX_RADIAL, con handler y visibles ahora."""
    out: List[ItemRadial] = []
    for id_ in validar_lista(ids, maximo=MAX_RADIAL, uso=USO_RADIAL):
        if not desp.tiene(id_) or not visible(id_, estado, ctx):
            continue
        a = ACCIONES[id_]
        m = desp.marcado_en(id_, estado, ctx)
        out.append(ItemRadial(id_, etiqueta_de(id_, m), icono_de(id_, m),
                              marcado=m if a.interruptor else None))
    return out


def items_expresiones(desp: Despachador) -> List[ItemRadial]:
    """Segundo radial: una expresión por botón (acción `expresion` con arg)."""
    if not desp.tiene("expresion"):
        return []
    return [ItemRadial("expresion", etiqueta, icono, arg=arg) for arg, etiqueta, icono in EXPRESIONES]


_SEP = ItemMenu("", "", separador=True)


def _limpiar(items: Sequence[ItemMenu]) -> List[ItemMenu]:
    """Sin separadores al principio, al final ni seguidos."""
    out: List[ItemMenu] = []
    for it in items:
        if it.separador and (not out or out[-1].separador):
            continue
        out.append(it)
    while out and out[-1].separador:
        out.pop()
    return out


def _item(desp: Despachador, estado: Any, ctx: Contexto, id_: str, *, etiqueta: str = "",
          arg: str = "", negrita: bool = False) -> Optional[ItemMenu]:
    """ItemMenu de la acción si tiene handler y se ve; si no, None."""
    if not desp.tiene(id_) or not visible(id_, estado, ctx):
        return None
    a = ACCIONES[id_]
    m = desp.marcado_en(id_, estado, ctx)
    return ItemMenu(id_, etiqueta or etiqueta_de(id_, m), arg=arg,
                    marcado=(bool(m) if a.interruptor else None), negrita=negrita)


def _submenu_opciones(desp, estado, ctx, id_: str, titulo: str, opciones, actual: str) -> Optional[ItemMenu]:
    if not desp.tiene(id_) or not visible(id_, estado, ctx):
        return None
    hijos = tuple(ItemMenu(id_, etiqueta, arg=clave, marcado=(clave == actual)) for clave, etiqueta in opciones)
    return ItemMenu("", titulo, hijos=hijos)


def menu_bandeja(desp: Despachador, estado: Any, ctx: Contexto, rapidas: Any,
                 presets: Iterable[Any]) -> List[ItemMenu]:
    """El menú de la bandeja (se reconstruye cada vez que se abre).

    Abrir Lune (negrita) · Mascota ▸ · Lune ▸ (rápidas de bandeja.acciones) ·
    Modo juego ✔ · Tema ▸ · Arrancar con Windows ✔ · Liberar memoria · Mostrar en
    la barra de tareas ✔ · Salir. `presets`: nombres de tema o pares (id, texto).
    """
    def it(id_, **kw):
        return _item(desp, estado, ctx, id_, **kw)

    items: List[Optional[ItemMenu]] = [it("mostrar_lune", negrita=True), _SEP]

    # Mascota ▸
    mascota = [it("mascota"), it("chat", etiqueta="Escribirle…"), it("comentar"), it("dormir"), _SEP,
               it("fantasma"), it("comentarios_auto"), it("siempre_encima"), _SEP,
               _submenu_opciones(desp, estado, ctx, "tamano", "Tamaño", TAMANOS, ctx.tamano),
               _submenu_opciones(desp, estado, ctx, "encuadre", "Encuadre", ENCUADRES, ctx.encuadre),
               it("esquina"), _SEP, it("cerrar_mascota")]
    hijos = tuple(_limpiar([x for x in mascota if x is not None]))
    if hijos:
        items.append(ItemMenu("", "Mascota", hijos=hijos))

    # Lune ▸ (acciones rápidas configurables)
    rap = tuple(x for x in (it(i) for i in validar_lista(rapidas, uso=USO_BANDEJA)) if x is not None)
    if rap:
        items.append(ItemMenu("", "Lune", hijos=rap))

    # Modo juego (forzar) con el motivo
    j = it("modo_juego_forzar")
    if j is not None:
        extra = ""
        if ctx.juego_forzado is True:
            extra = " (forzado)"
        elif ctx.juego_forzado is False:
            extra = " (apagado a mano)"
        elif ctx.juego_activo and ctx.juego_motivo:
            extra = f" ({texto_motivo_juego(ctx.juego_motivo)})"
        items.append(ItemMenu(j.id, j.etiqueta + extra, marcado=j.marcado))

    # Tema ▸
    if desp.tiene("tema") and visible("tema", estado, ctx):
        temas = []
        for p in presets or ():
            clave, texto = (p[0], p[1]) if isinstance(p, (tuple, list)) and len(p) >= 2 else (p, nombre_tema(p))
            temas.append(ItemMenu("tema", str(texto), arg=str(clave), marcado=(clave == ctx.tema_preset)))
        if temas:
            items.append(ItemMenu("", "Tema", hijos=tuple(temas)))

    items += [_SEP, it("autoinicio"), it("liberar_memoria"), it("en_barra_tareas"), _SEP, it("salir")]
    return _limpiar([x for x in items if x is not None])


def catalogo(desp: Despachador, estado: Any, ctx: Contexto, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
    """El catálogo para la web y /menu: una entrada por acción (las de `tipo`
    — "radial", "bandeja" o "atajo" — si se da) con si tiene handler en este modo
    (`disponible`), si se ve ahora (`visible`) y su ✔ (`marcado`)."""
    out: List[Dict[str, Any]] = []
    for a in ACCIONES.values():
        if tipo is not None and tipo not in a.usos:
            continue
        m = desp.marcado_en(a.id, estado, ctx) if desp.tiene(a.id) else None
        out.append({
            "id": a.id,
            "etiqueta": etiqueta_de(a.id, m),
            "icono": icono_de(a.id, m),
            "grupo": a.grupo,
            "interruptor": a.interruptor,
            "usos": sorted(a.usos),
            "disponible": desp.tiene(a.id) and ctx.modo in a.modos,
            "visible": desp.tiene(a.id) and visible(a.id, estado, ctx),
            "marcado": m if a.interruptor else None,
        })
    return out
