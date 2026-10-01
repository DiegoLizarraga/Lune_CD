"""
ui/puente_escritorio.py — segundo objeto del QWebChannel de la piel web.

Qué es
------
`PuenteEscritorio` se registra en el canal como `escritorio` y la página lo ve como
`window.luneEscritorio` (index.html: `channel.objects.escritorio || null`). Lleva lo
del corte 4 (tema, efectos, atajos, menú radial, bandeja, modo juego, rendimiento)
SIN tocar `ui/web_bridge.py` (`window.lune`), que cambia a la vez por otros motivos.
Las tarjetas de Ajustes (extra/apariencia.jsx y extra/juego.jsx) guardan desde aquí y
aplican al momento; no pasan por get_config/guardar_config.

Trabaja contra los controladores de `ServiciosCorte4` (montar_escritorio): despachador,
tema, atajos, juego, radial y bandeja. Todo por duck typing y `getattr` defensivo: si
falta un controlador (o el corte 4 no está montado), las ranuras devuelven un estado
por defecto y nunca lanzan hacia la página.

Validación estricta (la página es código que no controlamos del todo):
  · JSON con tope de tamaño (MAX_JSON), sin NaN/Infinity y del tipo esperado.
  · ids de acción con patrón y contra el catálogo (`nucleo.acciones_ui.ACCIONES`) y el
    despachador (sin handler = no existe).
  · combos con `servicios.atajos_globales.comprobar` (o `GestorAtajosQt.validar`).
  · apps con `servicios.modo_juego.normalizar_app`: solo nombres de .exe, NUNCA rutas.
  · números finitos y en rango, booleanos de verdad (no "true").

Ranuras (JS: los resultados llegan por callback, `escritorio.x(args…, cb)`):
    acciones_catalogo(tipo) → str   JSON [ {id, etiqueta, icono, arg, habilitado, marcado} ]
                                    tipo: radial · secundario (items_radial con la config) ·
                                    expresiones (items_expresiones: id «expresion» + arg) · todas
    accion_menu(id, arg) → bool     despachador.ejecutar(id, arg)
    tema_estado() → str             {cfg, vars (mapa CSS o null), presets}
    tema_previsualizar(json)        sin disco: ControlTema.previsualizar(cfg)
    tema_guardar(json) → str        {ok, error, estado: tema_estado}
    tema_restablecer() → str        {ok, error, estado}
    efectos() → str                 {fondo, barrido, micro, pausar_sin_foco} (config.efectos)
    efectos_guardar(json) → str     {ok, error, estado: efectos}
    atajos_estado() → str           {lista:[{id, etiqueta, combo, texto, error, aviso, disponible, siempre}],
                                     activo, pausar_en_juegos}
    atajo_validar(combo) → str      {ok, combo (normalizado), texto, error, aviso}
    atajo_guardar(id, combo) → str  {ok, error, aviso, estado: atajos_estado}; combo "" = sin atajo
    atajos_activar(bool) · atajos_capturando(bool)
    atajos_restablecer() → str      {ok, error, estado}
    radial_estado() → str           {principal, secundario, defecto, catalogo, max, sonidos, volumen}
    radial_guardar(json) → str      {ok, error, descartados, estado}
    bandeja_estado() → str          {acciones, defecto, catalogo, max}
    bandeja_guardar(json) → str     {ok, error, descartados, estado}
    juego_estado_json() → str       {activo, motivo, forzado, exe, disponible}
    juego_forzar(int)               1 = forzar juego · 0 = automático · -1 = forzar «sin juego»
    juego_config() → str            config.juego + pausar_atajos (atajos.pausar_en_juegos)
    juego_guardar(json) → str       {ok, error, estado: juego_config}
    juego_apps_visibles() → str     JSON ["game.exe", …] (apps con ventana, sin Lune)
    rendimiento() → str             {fps_max, siempre_encima, recorte_ram_auto, en_barra_tareas}
    rendimiento_guardar(json) → str {ok, error, estado: rendimiento}
    liberar_memoria() → str         {ok, error, antes, despues, liberado} (MB)
Señales:
    tema_cambio(str)    el mapa de variables CSS (JSON) o "null": va tal cual a window.luneTema
    juego_estado(str)   JSON de juego_estado_json()
    atajos_cambio(str)  JSON de atajos_estado()
    navegar(str)        vista de la página: chat · settings · … (opcional «#sección»)

`registrar_en_canal(canal, servicios, escritorio, config)` lo crea y lo registra; lo
llama web_shell en el __init__ de la ventana, ANTES de cargar la página (servicios puede
ser None: la ventana monta el corte 4 en iniciar_servicios y se los da después con
`usar_servicios(servicios)`). `cerrar()` lo suelta todo (se apunta solo en
ServiciosCorte4._deshacer: servicios.desmontar() lo llama). Sin servicios, el tema sale
de la config (nucleo.tema). Desde Python, `pedir_vista(vista)` emite `navegar` validado
(AnfitrionWeb.navegar se engancha solo).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import math
import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

_log = logging.getLogger("lune.puente_escritorio")

MAX_JSON = 16 * 1024                 # caracteres por payload de la página
MAX_TEXTO = 80                       # etiquetas, motivos, exes
MAX_COMBO = 64
MAX_APPS = 50                        # juego.apps
MAX_APPS_VISIBLES = 100
MAX_BANDEJA = 20
MAX_RADIAL_DEFECTO = 10              # si nucleo.acciones_ui aún no existe
FPS_JUEGO = (0, 60)
FPS_MAX = (15, 144)
SATURACION = (0.0, 2.0)
ACCIONES_JUEGO = ("ocultar", "fondo", "nada")
VISTAS = ("chat", "settings", "personajes", "memoria", "historial", "optimizar", "tools", "alarmas")
TIPOS_CATALOGO = ("radial", "secundario", "expresiones", "todas")
EFECTOS = ("fondo", "barrido", "micro", "pausar_sin_foco")   # pausar_sin_foco: Lune en reposo (11.2)

_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_ARG = re.compile(r"^[A-Za-z0-9_.:\-]{0,40}$")
_PRESET = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_SECCION = re.compile(r"^[a-z][a-z0-9_\-]{0,23}$")
_APP = re.compile(r"^[\w .\-()]{1,80}$")

# Segundo radial de «expresiones» si nucleo.acciones_ui no trae el suyo:
# (arg para set_estado, etiqueta, icono). El id de cada botón es «expresion» (con arg).
_EXPRESIONES = (
    ("happy", "Contenta", "smile"),
    ("sad", "Triste", "frown"),
    ("angry", "Enfadada", "angry"),
    ("surprised", "Sorprendida", "surprised"),
    ("thinking", "Pensativa", "thinking"),
    ("wave", "Saludar", "hand"),
)

# Presets de nucleo/tema.py (§1.5 del plan), por si ese módulo aún no está.
_PRESETS_RESPALDO = {
    "cian": 0.000, "magenta_mate": 0.316, "violeta": 0.233,
    "rojo_neon": 0.455, "ambar": 0.594, "verde_acido": 0.816,
}


# ── Utilidades puras ───────────────────────────────────────────────────────────

def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    """`obj.metodo(*args)` si existe; un fallo se registra y devuelve None."""
    if obj is None:
        return None
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("puente_escritorio: %s.%s falló", type(obj).__name__, metodo)
        return None


def _rechazar_constante(nombre: str):
    raise ValueError(f"constante no permitida: {nombre}")


def leer_json(texto: Any, tipo: type = dict) -> Any:
    """JSON de la página → objeto de `tipo`, o None si no vale (tamaño, NaN, tipo)."""
    if not isinstance(texto, str) or not texto or len(texto) > MAX_JSON:
        return None
    try:
        obj = json.loads(texto, parse_constant=_rechazar_constante)
    except (ValueError, TypeError, RecursionError):
        return None
    return obj if isinstance(obj, tipo) else None


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str)


def _es_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _numero(v: Any) -> Optional[float]:
    """Número finito (no bool) o None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _texto(v: Any, maximo: int = MAX_TEXTO) -> str:
    """Texto para la página: sin controles ni bidi, recortado."""
    if v is None:
        return ""
    s = str(v)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    return s[:maximo]


def _id_valido(v: Any) -> bool:
    return isinstance(v, str) and bool(_ID.match(v))


def _sin_duplicados(ids: Iterable[str]) -> List[str]:
    vistos, out = set(), []
    for i in ids:
        if i not in vistos:
            vistos.add(i)
            out.append(i)
    return out


def _normalizar_app_respaldo(nombre: Any) -> Optional[str]:
    """Como modo_juego.normalizar_app: «Game.EXE» → «game.exe»; None si no vale."""
    if not isinstance(nombre, str):
        return None
    s = nombre.strip().lower()
    return s if _APP.match(s) else None


def _campo(item: Any, nombre: str, defecto: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(nombre, defecto)
    return getattr(item, nombre, defecto)


def item_a_dict(item: Any) -> Optional[Dict[str, Any]]:
    """ItemRadial (dataclass), dict o parecido → dict seguro para la página."""
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        item = dataclasses.asdict(item)
    iid = _campo(item, "id")
    if not _id_valido(iid):
        return None
    out: Dict[str, Any] = {
        "id": iid,
        "etiqueta": _texto(_campo(item, "etiqueta", iid)) or iid,
        "icono": _texto(_campo(item, "icono", ""), 40),
        "arg": _texto(_campo(item, "arg", ""), 40),
        "habilitado": _campo(item, "habilitado", True) is not False,
    }
    for extra in ("grupo", "etiqueta_on"):
        v = _campo(item, extra, None)
        if v is not None:
            out[extra] = _texto(v)
    for extra in ("interruptor", "disponible", "visible"):
        v = _campo(item, extra, None)
        if isinstance(v, bool):
            out[extra] = v
    marcado = _campo(item, "marcado", None)
    out["marcado"] = marcado if isinstance(marcado, bool) else None
    usos = _campo(item, "usos", None)
    if isinstance(usos, (list, tuple, set, frozenset)):
        out["usos"] = sorted(str(u)[:12] for u in usos)[:6]
    return out


# ── Puente ─────────────────────────────────────────────────────────────────────

class PuenteEscritorio(QObject):
    """Objeto `escritorio` del QWebChannel (window.luneEscritorio)."""

    tema_cambio = pyqtSignal(str)
    juego_estado = pyqtSignal(str)
    atajos_cambio = pyqtSignal(str)
    navegar = pyqtSignal(str)

    def __init__(self, servicios: Any = None, escritorio: Any = None, config: Any = None, *,
                 anfitrion: Any = None, contexto: Optional[Callable[[], Any]] = None,
                 acciones_ui: Any = None, tema_mod: Any = None, modo_juego_mod: Any = None,
                 apps_visibles: Optional[Callable[[], Sequence[str]]] = None,
                 recortar: Optional[Callable[[], Tuple[float, float]]] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.servicios = servicios
        self.escritorio = escritorio
        self.config = config
        self.anfitrion = anfitrion if anfitrion is not None else getattr(servicios, "anfitrion", None)
        self._contexto_fn = contexto
        self._acciones_ui = acciones_ui
        self._tema_mod = tema_mod
        self._modo_juego_mod = modo_juego_mod
        self._apps_visibles = apps_visibles
        self._recortar = recortar
        self._conexiones: List[Tuple[Any, Callable]] = []
        self._tema_emitido = False
        self._canal: Any = None                    # lo pone registrar_en_canal
        self._navegar_puesto = False
        self._conectar_senales()

    # ── Controladores (siempre por getattr: pueden faltar) ────────────────────
    def _ctl(self, nombre: str) -> Any:
        return getattr(self.servicios, nombre, None) if self.servicios is not None else None

    @property
    def despachador(self) -> Any:
        return self._ctl("despachador")

    @property
    def tema(self) -> Any:
        return self._ctl("tema")

    @property
    def atajos(self) -> Any:
        return self._ctl("atajos")

    @property
    def juego(self) -> Any:
        return self._ctl("juego")

    def _asistente(self) -> Any:
        return getattr(self.escritorio, "asistente", None) if self.escritorio is not None else None

    # Módulos de otros agentes, en diferido e inyectables (tests con dobles).
    def _modulo(self, attr: str, nombre: str) -> Any:
        mod = getattr(self, attr)
        if mod is None:
            try:
                import importlib
                mod = importlib.import_module(nombre)
            except Exception:
                mod = False                    # no existe todavía: no reintentar
            setattr(self, attr, mod)
        return mod or None

    def _mod_acciones(self) -> Any:
        return self._modulo("_acciones_ui", "nucleo.acciones_ui")

    def _mod_tema(self) -> Any:
        return self._modulo("_tema_mod", "nucleo.tema")

    def _mod_juego(self) -> Any:
        return self._modulo("_modo_juego_mod", "servicios.modo_juego")

    def _contexto(self) -> Any:
        """Contexto de nucleo.acciones_ui para filtrar el catálogo: el del montaje
        (ServiciosCorte4.contexto) o, si no hay, uno por defecto de la piel web."""
        candidatos = [self._contexto_fn, getattr(self.servicios, "contexto", None)]
        for nombre in ("radial", "bandeja"):
            ctl = self._ctl(nombre)
            candidatos += [getattr(ctl, "contexto", None), getattr(ctl, "_contexto", None)]
        for c in candidatos:
            if callable(c):
                try:
                    ctx = c()
                except Exception:
                    _log.exception("puente_escritorio: contexto falló")
                    continue
                if ctx is not None:
                    return ctx
        mod = self._mod_acciones()
        contexto_cls = getattr(mod, "Contexto", None) if mod else None
        if callable(contexto_cls):
            try:
                return contexto_cls(modo="normal")
            except Exception:
                return None
        return None

    def _estado_foto(self) -> Any:
        """EstadoAsistente actual (lo que esperan las reglas de nucleo.acciones_ui)."""
        bus = getattr(self.escritorio, "estado", None) if self.escritorio is not None else None
        actual = getattr(bus, "actual", None)
        if callable(actual):
            try:
                return actual()
            except Exception:
                _log.exception("puente_escritorio: estado de la asistente")
                return None
        return bus

    # ── Config ─────────────────────────────────────────────────────────────────
    def _cfg(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        c = self.config
        if c is None:
            return defecto
        try:
            if hasattr(c, "get") and hasattr(c, "config"):
                return c.get(seccion, clave, defecto)
            if isinstance(c, dict):
                return (c.get(seccion) or {}).get(clave, defecto)
        except Exception:
            _log.exception("puente_escritorio: leer config %s.%s", seccion, clave)
        return defecto

    def _cfg_set(self, seccion: str, clave: str, valor: Any) -> bool:
        c = self.config
        if c is None:
            return False
        try:
            if hasattr(c, "set") and hasattr(c, "config"):
                c.set(seccion, clave, valor)
            elif isinstance(c, dict):
                c.setdefault(seccion, {})[clave] = valor
            else:
                return False
            return True
        except Exception:
            _log.exception("puente_escritorio: guardar config %s.%s", seccion, clave)
            return False

    def _defecto(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        base = getattr(self.config, "DEFAULT_CONFIG", None)
        if not isinstance(base, dict):
            try:
                from nucleo.config import Config
                base = Config.DEFAULT_CONFIG
            except Exception:
                return defecto
        v = (base.get(seccion) or {}).get(clave, defecto)
        return json.loads(json.dumps(v)) if isinstance(v, (list, dict)) else v

    # ── Señales de los controladores → señales de la página ───────────────────
    def _conectar(self, obj: Any, senal: str, slot: Callable) -> None:
        s = getattr(obj, senal, None) if obj is not None else None
        if s is None or not hasattr(s, "connect"):
            return
        try:
            s.connect(slot)
            self._conexiones.append((s, slot))
        except (TypeError, RuntimeError):
            _log.debug("puente_escritorio: no pude conectar %s", senal)

    def _conectar_senales(self) -> None:
        self._conectar(self.tema, "cambio", self._on_tema_cambio)
        self._conectar(self.juego, "cambio", self._on_juego_cambio)
        self._conectar(self.atajos, "cambio", self._on_atajos_cambio)

    def usar_servicios(self, servicios: Any, *, anfitrion: Any = None,
                       contexto: Optional[Callable[[], Any]] = None) -> None:
        """Servicios del corte 4 que llegan DESPUÉS de registrar el puente.

        La ventana web registra el puente en el canal antes de cargar la página (el
        JS solo ve lo registrado al crear su QWebChannel), pero monta la bandeja, los
        atajos y el detector de juegos en `iniciar_servicios`: en un cambio de
        interfaz en caliente, cuando la ventana vieja ya soltó los suyos. Aquí se
        enganchan: señales de los controladores, `anfitrion.navegar` y `cerrar()` en
        `servicios._deshacer` (desmontar() lo desregistra, una sola vez). Si la
        página ya estaba cargada, recibe el tema, el modo juego y los atajos."""
        conexiones, self._conexiones = self._conexiones, []
        for s, slot in conexiones:
            try:
                s.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.servicios = servicios
        if anfitrion is not None:
            self.anfitrion = anfitrion
        elif self.anfitrion is None:
            self.anfitrion = getattr(servicios, "anfitrion", None)
        if contexto is not None:
            self._contexto_fn = contexto
        self._conectar_senales()
        self.enganchar_anfitrion()
        deshacer = getattr(servicios, "_deshacer", None)
        if isinstance(deshacer, list) and self.cerrar not in deshacer:
            deshacer.append(self.cerrar)
        if servicios is not None:
            self._on_tema_cambio()
            self._on_juego_cambio()
            self._on_atajos_cambio()

    def enganchar_anfitrion(self) -> bool:
        """AnfitrionWeb.abrir_ajustes navega con `anfitrion.navegar(vista)`: si nadie lo
        puso, se engancha a pedir_vista (validado). True si lo enganchó."""
        anf = self.anfitrion
        if anf is None or not hasattr(anf, "navegar") or getattr(anf, "navegar", None) is not None:
            return False
        try:
            anf.navegar = self.pedir_vista
        except (AttributeError, TypeError):
            return False
        self._navegar_puesto = True
        return True

    def cerrar(self) -> None:
        """Lo suelta todo (cambio de interfaz, salir): señales de los controladores,
        el registro en el canal y el enganche del anfitrión. Idempotente."""
        conexiones, self._conexiones = self._conexiones, []
        for s, slot in conexiones:
            try:
                s.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        canal, self._canal = self._canal, None
        dereg = getattr(canal, "deregisterObject", None) if canal is not None else None
        if callable(dereg):
            try:
                dereg(self)
            except (TypeError, RuntimeError):
                pass
        if self._navegar_puesto:
            self._navegar_puesto = False
            anf = self.anfitrion
            try:
                if getattr(anf, "navegar", None) == self.pedir_vista:
                    anf.navegar = None
            except (AttributeError, TypeError, RuntimeError):
                pass

    def _css_actual(self) -> Any:
        """css_json del tema visible: el de ControlTema o, sin él (servicios aún sin
        montar), el de la config con nucleo.tema. Así la página arranca ya con su
        color y no con el cian de siempre."""
        if self.tema is not None:
            return _llamar(self.tema, "css_json")
        mod = self._mod_tema()
        f = getattr(mod, "css_json", None) if mod else None
        if not callable(f):
            return None
        try:
            return f(self._tema_actual())
        except Exception:
            _log.exception("puente_escritorio: tema.css_json de la config")
            return None

    def _on_tema_cambio(self, css: Any = None) -> None:
        texto = css if isinstance(css, str) else self._css_actual()
        vars_ = self._vars_css(texto)
        self._tema_emitido = True
        self.tema_cambio.emit(_dump(vars_))

    def _on_juego_cambio(self, *_args) -> None:
        self.juego_estado.emit(self.juego_estado_json())

    def _on_atajos_cambio(self, *_args) -> None:
        self.atajos_cambio.emit(self.atajos_estado())

    # ── Navegación (desde Python: AnfitrionWeb.abrir_ajustes / mostrar chat) ──
    def pedir_vista(self, vista: str) -> bool:
        """Emite `navegar` si `vista` es una de VISTAS (opcional «#sección»)."""
        if not isinstance(vista, str):
            return False
        base, _, seccion = vista.partition("#")
        if base not in VISTAS or (seccion and not _SECCION.match(seccion)):
            return False
        self.navegar.emit(vista)
        return True

    # ═══ Catálogo de acciones y despachador ══════════════════════════════════
    def _acciones_conocidas(self) -> Optional[set]:
        mod = self._mod_acciones()
        acc = getattr(mod, "ACCIONES", None) if mod else None
        return set(acc) if isinstance(acc, dict) else None

    def _max_radial(self) -> int:
        mod = self._mod_acciones()
        n = getattr(mod, "MAX_RADIAL", None) if mod else None
        return n if isinstance(n, int) and 1 <= n <= 20 else MAX_RADIAL_DEFECTO

    def _id_de_accion(self, iid: Any) -> bool:
        """Id con patrón, en el catálogo (si se conoce) y con handler en el despachador."""
        if not _id_valido(iid):
            return False
        conocidas = self._acciones_conocidas()
        if conocidas is not None and iid not in conocidas:
            return False
        d = self.despachador
        if d is None:
            return False
        tiene = getattr(d, "tiene", None)
        if callable(tiene):
            try:
                return bool(tiene(iid))
            except Exception:
                return False
        return True

    def _etiqueta(self, iid: str) -> Tuple[str, str]:
        mod = self._mod_acciones()
        acc = (getattr(mod, "ACCIONES", None) or {}) if mod else {}
        a = acc.get(iid) if isinstance(acc, dict) else None
        return (_texto(getattr(a, "etiqueta", iid)) or iid, _texto(getattr(a, "icono", ""), 40))

    def _items_simples(self, ids: Iterable[Any]) -> List[Dict[str, Any]]:
        """Sin nucleo.acciones_ui o sin contexto: ids con handler, etiqueta del catálogo."""
        out = []
        for iid in ids:
            if self._id_de_accion(iid):
                et, ic = self._etiqueta(iid)
                out.append({"id": iid, "etiqueta": et, "icono": ic, "arg": "", "habilitado": True})
        return out

    def _items_radial(self, ids: List[str]) -> List[Dict[str, Any]]:
        mod, d, ctx = self._mod_acciones(), self.despachador, self._contexto()
        f = getattr(mod, "items_radial", None) if mod else None
        if callable(f) and d is not None and ctx is not None:
            try:
                crudos = f(d, self._estado_foto(), ctx, ids)
                return [x for x in (item_a_dict(i) for i in (crudos or [])) if x][: self._max_radial()]
            except Exception:
                _log.exception("puente_escritorio: items_radial falló")
        return self._items_simples(ids)[: self._max_radial()]

    def _items_expresiones(self) -> List[Dict[str, Any]]:
        mod, d = self._mod_acciones(), self.despachador
        f = getattr(mod, "items_expresiones", None) if mod else None
        if callable(f) and d is not None:
            try:
                return [x for x in (item_a_dict(i) for i in (f(d) or [])) if x][: self._max_radial()]
            except Exception:
                _log.exception("puente_escritorio: items_expresiones falló")
        propias = getattr(mod, "EXPRESIONES", None) if mod else None
        filas: List[Tuple[str, str, str]] = []
        if isinstance(propias, dict):
            filas = [(k, str(v), "") for k, v in propias.items()]
        elif isinstance(propias, (list, tuple)):
            for p in propias:
                if isinstance(p, (list, tuple)) and p:
                    filas.append((str(p[0]), str(p[1]) if len(p) > 1 else str(p[0]),
                                  str(p[2]) if len(p) > 2 else ""))
                elif isinstance(p, str):
                    filas.append((p, p, ""))
        if not filas:
            filas = list(_EXPRESIONES)
        if not self._id_de_accion("expresion"):
            return []
        out = []
        for arg, et, ic in filas:
            if _ARG.match(arg) and arg:
                out.append({"id": "expresion", "etiqueta": _texto(et) or arg, "icono": _texto(ic, 40),
                            "arg": arg, "habilitado": True})
        return out[: self._max_radial()]

    def _catalogo(self, uso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Acciones para elegir en las tarjetas (las de `uso`: radial · bandeja · atajo),
        solo las que tienen handler en este modo (`disponible`)."""
        mod, d, ctx = self._mod_acciones(), self.despachador, self._contexto()
        f = getattr(mod, "catalogo", None) if mod else None
        if callable(f) and d is not None and ctx is not None:
            try:
                crudos = f(d, self._estado_foto(), ctx, uso) if uso else f(d, self._estado_foto(), ctx)
                return [x for x in (item_a_dict(i) for i in (crudos or []))
                        if x and x.get("disponible") is not False]
            except Exception:
                _log.exception("puente_escritorio: catalogo falló")
        acc = getattr(mod, "ACCIONES", None) if mod else None
        if isinstance(acc, dict):
            ids = [i for i, a in acc.items() if uso is None or uso in (getattr(a, "usos", None) or (uso,))]
            return self._items_simples(ids)
        return []

    def _lista_config(self, seccion: str, clave: str) -> List[str]:
        v = self._cfg(seccion, clave, None)
        if not isinstance(v, list):
            v = self._defecto(seccion, clave, []) or []
        return [i for i in v if _id_valido(i)]

    @pyqtSlot(str, result=str)
    def acciones_catalogo(self, tipo: str) -> str:
        if tipo not in TIPOS_CATALOGO:
            return "[]"
        try:
            if tipo == "radial":
                items = self._items_radial(self._lista_config("menu_radial", "principal"))
            elif tipo == "secundario":
                items = self._items_radial(self._lista_config("menu_radial", "secundario"))
            elif tipo == "expresiones":
                items = self._items_expresiones()
            else:
                items = self._catalogo()
        except Exception:
            _log.exception("puente_escritorio: acciones_catalogo(%s)", tipo)
            items = []
        return _dump(items)

    @pyqtSlot(str, str, result=bool)
    def accion_menu(self, id_: str, arg: str) -> bool:
        if not self._id_de_accion(id_):
            return False
        if not isinstance(arg, str) or not _ARG.match(arg):
            return False
        r = _llamar(self.despachador, "ejecutar", id_, arg)
        return bool(r)

    # ═══ Tema ════════════════════════════════════════════════════════════════
    def _presets(self) -> Dict[str, float]:
        mod = self._mod_tema()
        p = getattr(mod, "PRESETS", None) if mod else None
        if isinstance(p, dict) and p:
            return {str(k): float(v) for k, v in p.items() if _numero(v) is not None}
        return dict(_PRESETS_RESPALDO)

    def _tema_actual(self) -> Dict[str, Any]:
        cfg = _llamar(self.tema, "actual")
        if not isinstance(cfg, dict):
            cfg = {k: self._cfg("tema", k, self._defecto("tema", k))
                   for k in ("preset", "hue", "saturacion", "tenir_pop", "tenir_fondo")}
        return {k: v for k, v in cfg.items() if isinstance(v, (str, int, float, bool)) or v is None}

    @staticmethod
    def _vars_css(texto: Any) -> Optional[Dict[str, str]]:
        """css_json de ControlTema → dict {--var: valor} o None (tema identidad)."""
        if isinstance(texto, dict):
            obj = texto
        else:
            obj = leer_json(texto, dict) if isinstance(texto, str) and texto != "null" else None
        if not obj:
            return None
        return {str(k): str(v) for k, v in obj.items()
                if isinstance(k, str) and k.startswith("--") and isinstance(v, (str, int, float))}

    def validar_tema(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Payload de la página → cambios de tema validados (parcial) o None.
        ControlTema.previsualizar/guardar los mezclan con lo visible."""
        if not isinstance(obj, dict):
            return None
        nuevo: Dict[str, Any] = {}
        if "preset" in obj:
            p = obj["preset"]
            if not isinstance(p, str) or not _PRESET.match(p):
                return None
            if p != "personalizado" and p not in self._presets():
                return None
            nuevo["preset"] = p
        if "hue" in obj:
            h = _numero(obj["hue"])
            if h is None:
                return None
            nuevo["hue"] = round(h % 360.0, 3)
        if "saturacion" in obj:
            s = _numero(obj["saturacion"])
            if s is None:
                return None
            nuevo["saturacion"] = round(min(SATURACION[1], max(SATURACION[0], s)), 3)
        for k in ("tenir_pop", "tenir_fondo"):
            if k in obj:
                if not _es_bool(obj[k]):
                    return None
                nuevo[k] = obj[k]
        return nuevo or None

    def _fusionar_tema(self, parcial: Dict[str, Any]) -> Dict[str, Any]:
        """Como ControlTema._fusionar: mover el tono sin preset = «personalizado»."""
        cfg = self._tema_actual()
        if "hue" in parcial and "preset" not in parcial:
            cfg["preset"] = "personalizado"
        cfg.update(parcial)
        mod = self._mod_tema()
        f = getattr(mod, "normalizar", None) if mod else None
        if callable(f):
            try:
                return dict(f(cfg))
            except Exception:
                _log.exception("puente_escritorio: tema.normalizar")
        return cfg

    def _tema_estado(self) -> Dict[str, Any]:
        return {
            "cfg": self._tema_actual(),
            "vars": self._vars_css(self._css_actual()),
            "presets": self._presets(),
        }

    @pyqtSlot(result=str)
    def tema_estado(self) -> str:
        return _dump(self._tema_estado())

    @pyqtSlot(str)
    def tema_previsualizar(self, payload: str) -> None:
        """Vista previa SIN disco. La página la limita a 1 llamada cada 50 ms."""
        cfg = self.validar_tema(leer_json(payload))
        if cfg is None or self.tema is None:
            return
        self._tema_emitido = False
        _llamar(self.tema, "previsualizar", cfg)
        if not self._tema_emitido:
            # ControlTema no avisó: la página necesita el mapa de la vista previa igual.
            mod = self._mod_tema()
            f = getattr(mod, "css_json", None) if mod else None
            css = None
            if callable(f):
                try:
                    css = f(self._fusionar_tema(cfg))
                except Exception:
                    _log.exception("puente_escritorio: tema.css_json")
            self.tema_cambio.emit(_dump(self._vars_css(css)))

    @pyqtSlot(str, result=str)
    def tema_guardar(self, payload: str) -> str:
        cfg = self.validar_tema(leer_json(payload))
        if cfg is None:
            return _dump({"ok": False, "error": "Tema no válido.", "estado": self._tema_estado()})
        if self.tema is None:
            ok = all(self._cfg_set("tema", k, v) for k, v in self._fusionar_tema(cfg).items()
                     if k in ("preset", "hue", "saturacion", "tenir_pop", "tenir_fondo"))
            return _dump({"ok": ok, "error": "" if ok else "No pude guardar el tema.",
                          "estado": self._tema_estado()})
        r = _llamar(self.tema, "guardar", cfg)
        ok = r is not None
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar el tema.", "estado": self._tema_estado()})

    @pyqtSlot(result=str)
    def tema_restablecer(self) -> str:
        if self.tema is None:
            for k in ("preset", "hue", "saturacion", "tenir_pop", "tenir_fondo"):
                self._cfg_set("tema", k, self._defecto("tema", k))
            return _dump({"ok": True, "error": "", "estado": self._tema_estado()})
        r = _llamar(self.tema, "restablecer")
        ok = r is not None
        return _dump({"ok": ok, "error": "" if ok else "No pude restablecer el tema.",
                      "estado": self._tema_estado()})

    # ═══ Efectos de la web (antes en localStorage) ═══════════════════════════
    def _efectos(self) -> Dict[str, bool]:
        return {k: bool(self._cfg("efectos", k, True)) for k in EFECTOS}

    @pyqtSlot(result=str)
    def efectos(self) -> str:
        return _dump(self._efectos())

    @pyqtSlot(str, result=str)
    def efectos_guardar(self, payload: str) -> str:
        obj = leer_json(payload)
        if not obj or any(k not in EFECTOS or not _es_bool(v) for k, v in obj.items()):
            return _dump({"ok": False, "error": "Efectos no válidos.", "estado": self._efectos()})
        actuales = self._efectos()
        ok = True
        for k, v in obj.items():
            if actuales.get(k) != v:
                ok = self._cfg_set("efectos", k, v) and ok
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._efectos()})

    # ═══ Atajos globales ═════════════════════════════════════════════════════
    def _ids_atajos(self) -> List[str]:
        lista = self._cfg("atajos", "lista", None)
        if not isinstance(lista, list):
            lista = self._defecto("atajos", "lista", []) or []
        ids = [e.get("id") for e in lista if isinstance(e, dict)]
        ids += [e.get("id") for e in (self._defecto("atajos", "lista", []) or []) if isinstance(e, dict)]
        mod = self._mod_acciones()
        acc = getattr(mod, "ACCIONES", None) if mod else None
        if isinstance(acc, dict):
            ids += [i for i, a in acc.items() if "atajo" in (getattr(a, "usos", None) or ())]
        return _sin_duplicados(i for i in ids if _id_valido(i))

    def _fila_atajo(self, e: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(e, dict) or not _id_valido(e.get("id")):
            return None
        combo = e.get("combo") if isinstance(e.get("combo"), str) else ""
        return {
            "id": e["id"],
            "etiqueta": _texto(e.get("etiqueta") or self._etiqueta(e["id"])[0]),
            "combo": _texto(combo, MAX_COMBO),
            "texto": _texto(e.get("texto") or combo, MAX_COMBO),
            "error": _texto(e.get("error") or "", 300) or None,
            "aviso": _texto(e.get("aviso") or "", 300) or None,
            "disponible": e.get("disponible") is not False,
            "siempre": e.get("siempre") is True,
        }

    def _atajos_estado(self) -> Dict[str, Any]:
        crudo = _llamar(self.atajos, "estado")
        if not isinstance(crudo, list):
            # Sin gestor: lo guardado, con el texto de atajos_globales (y sin registrar).
            crudo = []
            lista = self._cfg("atajos", "lista", None)
            for e in (lista if isinstance(lista, list) else []):
                if isinstance(e, dict):
                    v = self._validar_combo(e.get("combo") or "")
                    crudo.append({"id": e.get("id"), "combo": v["combo"] or e.get("combo") or "",
                                  "texto": v["texto"], "error": v["error"], "aviso": v["aviso"],
                                  "disponible": False})
        filas = [f for f in (self._fila_atajo(e) for e in crudo) if f]
        return {
            "lista": filas,
            "activo": bool(self._cfg("atajos", "activo", True)),
            "pausar_en_juegos": bool(self._cfg("atajos", "pausar_en_juegos", True)),
        }

    @pyqtSlot(result=str)
    def atajos_estado(self) -> str:
        return _dump(self._atajos_estado())

    def _validar_combo(self, combo: Any, id_: Optional[str] = None) -> Dict[str, Any]:
        vacio = {"ok": False, "combo": "", "texto": "", "error": "El atajo está vacío.", "aviso": None}
        if not isinstance(combo, str) or not combo.strip():
            return vacio
        if len(combo) > MAX_COMBO or not combo.isprintable():
            return {**vacio, "error": "Ese atajo no es válido."}
        from servicios import atajos_globales as ag
        error, aviso = ag.comprobar(combo)
        norm, texto = "", ""
        if not error:
            try:
                norm = ag.normalizar(combo)
                texto = ag.texto_combo(*ag.parsear_combo(norm))
            except ValueError as e:
                error = str(e)
        # El gestor de la app sabe además si otra acción de Lune ya lo usa.
        extra = _llamar(self.atajos, "validar", norm, id_) if not error else None
        if isinstance(extra, dict):
            error = extra.get("error") or error
            aviso = extra.get("aviso") or aviso
            otro = extra.get("conflicto")
            if not error and isinstance(otro, str) and otro:
                error = f"{texto or norm} ya lo usa «{self._etiqueta(otro)[0]}»."
        return {"ok": not error, "combo": norm if not error else "", "texto": texto,
                "error": _texto(error, 300) or None, "aviso": _texto(aviso, 300) or None}

    @pyqtSlot(str, result=str)
    def atajo_validar(self, combo: str) -> str:
        return _dump(self._validar_combo(combo))

    @pyqtSlot(str, str, result=str)
    def atajo_guardar(self, id_: str, combo: str) -> str:
        """Guarda el atajo de `id_` (normalizado). combo "" = dejarlo sin atajo."""
        if not _id_valido(id_) or id_ not in self._ids_atajos() or not isinstance(combo, str):
            return _dump({"ok": False, "error": "Ese atajo no existe.", "estado": self._atajos_estado()})
        if combo == "":
            v = {"ok": True, "combo": "", "aviso": None}
        else:
            v = self._validar_combo(combo, id_)
        if not v["ok"]:
            return _dump({"ok": False, "error": v["error"], "estado": self._atajos_estado()})
        cambiar = getattr(self.atajos, "cambiar", None) if self.atajos is not None else None
        if callable(cambiar):
            try:
                err = cambiar(id_, v["combo"])        # None = guardado (normalizado) y registrado
            except Exception:
                _log.exception("puente_escritorio: atajos.cambiar")
                err = "No pude guardar el atajo."
            ok = err is None
            error = "" if ok else _texto(err, 300)
        else:
            ok, error = self._guardar_combo_config(id_, v["combo"]), ""
            if not ok:
                error = "No pude guardar el atajo."
        return _dump({"ok": ok, "error": error, "aviso": v["aviso"], "estado": self._atajos_estado()})

    def _guardar_combo_config(self, id_: str, combo: str) -> bool:
        lista = self._cfg("atajos", "lista", None)
        lista = [dict(e) for e in lista if isinstance(e, dict)] if isinstance(lista, list) else []
        for e in lista:
            if e.get("id") == id_:
                e["combo"] = combo
                break
        else:
            lista.append({"id": id_, "combo": combo})
        return self._cfg_set("atajos", "lista", lista)

    @pyqtSlot(bool)
    def atajos_activar(self, on: bool) -> None:
        if not _es_bool(on):
            return
        if callable(getattr(self.atajos, "activar", None)):
            _llamar(self.atajos, "activar", on)
        else:
            self._cfg_set("atajos", "activo", on)

    @pyqtSlot(bool)
    def atajos_capturando(self, on: bool) -> None:
        """«Detectar» en la página: con True se pausan TODOS los atajos (se reanudan
        solos a los 15 s si la página no manda False)."""
        if _es_bool(on):
            _llamar(self.atajos, "capturando", on)

    @pyqtSlot(result=str)
    def atajos_restablecer(self) -> str:
        if callable(getattr(self.atajos, "restablecer", None)):
            _llamar(self.atajos, "restablecer")
        else:
            self._cfg_set("atajos", "lista", self._defecto("atajos", "lista", []))
        return _dump({"ok": True, "error": "", "estado": self._atajos_estado()})

    # ═══ Menú radial y bandeja ═══════════════════════════════════════════════
    def _validar_ids(self, obj: Any, maximo: Optional[int],
                     uso: Optional[str] = None) -> Tuple[Optional[List[str]], List[Any]]:
        """Lista de ids de la página → (válidos en orden, descartados). None si no es lista."""
        if not isinstance(obj, list) or len(obj) > 64:
            return None, []
        pedidos = [i for i in obj if isinstance(i, str)]
        mod = self._mod_acciones()
        f = getattr(mod, "validar_lista", None) if mod else None
        if callable(f):
            try:
                validos = list(f(pedidos, maximo=maximo, uso=uso))
            except TypeError:                           # validar_lista sin `uso`
                validos = list(f(pedidos, maximo=maximo))
            except Exception:
                _log.exception("puente_escritorio: validar_lista")
                validos = []
        else:
            conocidas = self._acciones_conocidas()
            validos = _sin_duplicados(i for i in pedidos if _id_valido(i)
                                      and (conocidas is None or i in conocidas))
        validos = [i for i in validos if _id_valido(i)]
        if maximo:
            validos = validos[:maximo]
        descartados = [_texto(i, 40) for i in obj if i not in validos]
        return validos, descartados

    def _radial_estado(self) -> Dict[str, Any]:
        vol = _numero(self._cfg("menu", "volumen", 0.6))
        return {
            "principal": self._lista_config("menu_radial", "principal"),
            "secundario": self._lista_config("menu_radial", "secundario"),
            "defecto": [i for i in (self._defecto("menu_radial", "principal", []) or []) if _id_valido(i)],
            "catalogo": self._catalogo("radial"),
            "max": self._max_radial(),
            "sonidos": bool(self._cfg("menu", "sonidos", True)),
            "volumen": min(1.0, max(0.0, vol if vol is not None else 0.6)),
        }

    @pyqtSlot(result=str)
    def radial_estado(self) -> str:
        return _dump(self._radial_estado())

    @pyqtSlot(str, result=str)
    def radial_guardar(self, payload: str) -> str:
        obj = leer_json(payload)
        falla = lambda msg: _dump({"ok": False, "error": msg, "descartados": [], "estado": self._radial_estado()})  # noqa: E731
        if not obj or any(k not in ("principal", "secundario", "sonidos", "volumen") for k in obj):
            return falla("Menú radial no válido.")
        cambios: List[Tuple[str, str, Any]] = []
        descartados: List[Any] = []
        for clave in ("principal", "secundario"):
            if clave in obj:
                if isinstance(obj[clave], list) and len(obj[clave]) > self._max_radial():
                    return falla(f"Como mucho {self._max_radial()} botones.")
                ids, desc = self._validar_ids(obj[clave], self._max_radial(), "radial")
                if ids is None:
                    return falla("Menú radial no válido.")
                descartados += desc
                cambios.append(("menu_radial", clave, ids))
        if "sonidos" in obj:
            if not _es_bool(obj["sonidos"]):
                return falla("Menú radial no válido.")
            cambios.append(("menu", "sonidos", obj["sonidos"]))
        if "volumen" in obj:
            v = _numero(obj["volumen"])
            if v is None:
                return falla("Menú radial no válido.")
            cambios.append(("menu", "volumen", round(min(1.0, max(0.0, v)), 3)))
        ok = all(self._cfg_set(s, k, v) for s, k, v in cambios)
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar.",
                      "descartados": descartados, "estado": self._radial_estado()})

    def _bandeja_estado(self) -> Dict[str, Any]:
        return {
            "acciones": self._lista_config("bandeja", "acciones"),
            "defecto": [i for i in (self._defecto("bandeja", "acciones", []) or []) if _id_valido(i)],
            "catalogo": self._catalogo("bandeja"),
            "max": MAX_BANDEJA,
        }

    @pyqtSlot(result=str)
    def bandeja_estado(self) -> str:
        return _dump(self._bandeja_estado())

    @pyqtSlot(str, result=str)
    def bandeja_guardar(self, payload: str) -> str:
        obj = leer_json(payload)
        if not obj or set(obj) != {"acciones"}:
            return _dump({"ok": False, "error": "Bandeja no válida.", "descartados": [],
                          "estado": self._bandeja_estado()})
        if isinstance(obj["acciones"], list) and len(obj["acciones"]) > MAX_BANDEJA:
            return _dump({"ok": False, "error": f"Como mucho {MAX_BANDEJA} acciones.", "descartados": [],
                          "estado": self._bandeja_estado()})
        ids, desc = self._validar_ids(obj["acciones"], MAX_BANDEJA, "bandeja")
        if ids is None:
            return _dump({"ok": False, "error": "Bandeja no válida.", "descartados": [],
                          "estado": self._bandeja_estado()})
        ok = self._cfg_set("bandeja", "acciones", ids)
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar.", "descartados": desc,
                      "estado": self._bandeja_estado()})

    # ═══ Modo juego ══════════════════════════════════════════════════════════
    def normalizar_app(self, nombre: Any, *, desde_ruta: bool = False) -> Optional[str]:
        """Nombre de .exe para juego.apps; None si no vale. Nunca una ruta: lo que
        escribe la página con ruta se rechaza; lo que da el propio backend (el exe
        del detector, las ventanas abiertas) se queda solo con el nombre del archivo."""
        if not isinstance(nombre, str) or len(nombre) > 260:
            return None
        if "\\" in nombre or "/" in nombre or ":" in nombre:
            if not desde_ruta:
                return None
            nombre = re.split(r"[\\/:]", nombre)[-1]
        mod = self._mod_juego()
        f = getattr(mod, "normalizar_app", None) if mod else None
        if callable(f):
            try:
                r = f(nombre)
            except Exception:
                r = None
        else:
            r = _normalizar_app_respaldo(nombre)
        if not isinstance(r, str) or not _APP.match(r):
            return None
        return r

    def _juego_estado(self) -> Dict[str, Any]:
        e = _llamar(self.juego, "estado")
        if not isinstance(e, dict):
            return {"activo": False, "motivo": "", "forzado": None, "exe": "", "disponible": self.juego is not None}
        forzado = e.get("forzado")
        return {
            "activo": bool(e.get("activo")),
            "motivo": _texto(e.get("motivo") or "", 24),
            "forzado": forzado if isinstance(forzado, bool) else None,
            "exe": self.normalizar_app(e.get("exe") or "", desde_ruta=True) or "",
            "disponible": True,
        }

    @pyqtSlot(result=str)
    def juego_estado_json(self) -> str:
        return _dump(self._juego_estado())

    @pyqtSlot(int)
    def juego_forzar(self, valor: int) -> None:
        """1 = forzar modo juego · 0 = automático (detector) · -1 = forzar «sin juego»."""
        mapa = {1: True, 0: None, -1: False}
        if isinstance(valor, bool) or valor not in mapa:
            return
        _llamar(self.juego, "forzar", mapa[valor])

    def _juego_config(self) -> Dict[str, Any]:
        d = lambda k, v: self._cfg("juego", k, v)  # noqa: E731
        accion = d("accion", "ocultar")
        fps = _numero(d("fps", 0))
        apps = d("apps", [])
        return {
            "activo": bool(d("activo", True)),
            "accion": accion if accion in ACCIONES_JUEGO else "ocultar",
            "fps": int(min(FPS_JUEGO[1], max(FPS_JUEGO[0], fps if fps is not None else 0))),
            "apps": [a for a in (self.normalizar_app(x) for x in (apps if isinstance(apps, list) else [])) if a],
            "rutas_juego": bool(d("rutas_juego", True)),
            "incluir_videos": bool(d("incluir_videos", True)),
            "prioridad_baja": bool(d("prioridad_baja", True)),
            "recortar_ram": bool(d("recortar_ram", True)),
            "silenciar": bool(d("silenciar", True)),
            "pausar_atajos": bool(self._cfg("atajos", "pausar_en_juegos", True)),
        }

    @pyqtSlot(result=str)
    def juego_config(self) -> str:
        return _dump(self._juego_config())

    _BOOLS_JUEGO = ("activo", "rutas_juego", "incluir_videos", "prioridad_baja", "recortar_ram", "silenciar")

    @pyqtSlot(str, result=str)
    def juego_guardar(self, payload: str) -> str:
        obj = leer_json(payload)
        permitidas = set(self._BOOLS_JUEGO) | {"accion", "fps", "apps", "pausar_atajos"}

        def falla(msg: str) -> str:
            return _dump({"ok": False, "error": msg, "estado": self._juego_config()})

        if not obj or any(k not in permitidas for k in obj):
            return falla("Ajustes del modo juego no válidos.")
        cambios: List[Tuple[str, str, Any]] = []
        for k in self._BOOLS_JUEGO:
            if k in obj:
                if not _es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios.append(("juego", k, obj[k]))
        if "accion" in obj:
            if obj["accion"] not in ACCIONES_JUEGO:
                return falla("Acción no válida (ocultar, fondo o nada).")
            cambios.append(("juego", "accion", obj["accion"]))
        if "fps" in obj:
            f = _numero(obj["fps"])
            if f is None or f != int(f) or not FPS_JUEGO[0] <= f <= FPS_JUEGO[1]:
                return falla(f"FPS en juego entre {FPS_JUEGO[0]} y {FPS_JUEGO[1]}.")
            cambios.append(("juego", "fps", int(f)))
        if "apps" in obj:
            apps = obj["apps"]
            if not isinstance(apps, list) or len(apps) > MAX_APPS:
                return falla(f"Como mucho {MAX_APPS} apps.")
            norm = [self.normalizar_app(a) for a in apps]
            if any(a is None for a in norm):
                return falla("Solo nombres de programa (por ejemplo juego.exe), sin rutas.")
            cambios.append(("juego", "apps", _sin_duplicados(norm)))
        if "pausar_atajos" in obj:
            if not _es_bool(obj["pausar_atajos"]):
                return falla("«pausar_atajos» tiene que ser sí o no.")
            cambios.append(("atajos", "pausar_en_juegos", obj["pausar_atajos"]))
        ok = all(self._cfg_set(s, k, v) for s, k, v in cambios)
        _llamar(self.juego, "recargar_config")
        if any(s == "atajos" for s, _, _ in cambios):
            _llamar(self.atajos, "recargar")
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._juego_config()})

    @pyqtSlot(result=str)
    def juego_apps_visibles(self) -> str:
        f = self._apps_visibles
        if f is None:
            mod = self._mod_juego()
            f = getattr(mod, "apps_con_ventana", None) if mod else None
        crudas: Sequence[Any] = []
        if callable(f):
            try:
                crudas = f() or []
            except Exception:
                _log.exception("puente_escritorio: apps_con_ventana")
        apps = sorted(set(a for a in (self.normalizar_app(x, desde_ruta=True) for x in list(crudas)[:500]) if a))
        return _dump(apps[:MAX_APPS_VISIBLES])

    # ═══ Rendimiento ═════════════════════════════════════════════════════════
    def _rendimiento(self) -> Dict[str, Any]:
        fps = _numero(self._cfg("avatar", "fps_max", 60))
        return {
            "fps_max": int(min(FPS_MAX[1], max(FPS_MAX[0], fps if fps is not None else 60))),
            "siempre_encima": bool(self._cfg("avatar", "siempre_encima", True)),
            "recorte_ram_auto": bool(self._cfg("sistema", "recorte_ram_auto", False)),
            "en_barra_tareas": bool(self._cfg("interfaz", "en_barra_tareas", True)),
        }

    @pyqtSlot(result=str)
    def rendimiento(self) -> str:
        return _dump(self._rendimiento())

    _RUTAS_RENDIMIENTO = {
        "fps_max": ("avatar", "fps_max"),
        "siempre_encima": ("avatar", "siempre_encima"),
        "recorte_ram_auto": ("sistema", "recorte_ram_auto"),
        "en_barra_tareas": ("interfaz", "en_barra_tareas"),
    }

    @pyqtSlot(str, result=str)
    def rendimiento_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return _dump({"ok": False, "error": msg, "estado": self._rendimiento()})

        if not obj or any(k not in self._RUTAS_RENDIMIENTO for k in obj):
            return falla("Ajustes de rendimiento no válidos.")
        valores: Dict[str, Any] = {}
        if "fps_max" in obj:
            f = _numero(obj["fps_max"])
            if f is None or f != int(f) or not FPS_MAX[0] <= f <= FPS_MAX[1]:
                return falla(f"FPS máximos entre {FPS_MAX[0]} y {FPS_MAX[1]}.")
            valores["fps_max"] = int(f)
        for k in ("siempre_encima", "recorte_ram_auto", "en_barra_tareas"):
            if k in obj:
                if not _es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                valores[k] = obj[k]
        antes = self._rendimiento()
        ok = all(self._cfg_set(*self._RUTAS_RENDIMIENTO[k], v) for k, v in valores.items())
        self._aplicar_rendimiento({k: v for k, v in valores.items() if antes.get(k) != v})
        return _dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._rendimiento()})

    def _aplicar_rendimiento(self, cambios: Dict[str, Any]) -> None:
        """Al momento, sin reiniciar: asistente, recorte periódico y barra de tareas."""
        m = self._asistente()
        if "fps_max" in cambios:
            _llamar(m, "set_fps_max", cambios["fps_max"])
        if "siempre_encima" in cambios:
            _llamar(m, "set_encima", cambios["siempre_encima"])
        if "recorte_ram_auto" in cambios:
            _llamar(self.juego, "recargar_config")      # su ProgramadorRecorte lee sistema.recorte_ram_auto
        if "en_barra_tareas" in cambios:
            _llamar(self.anfitrion, "set_en_barra", cambios["en_barra_tareas"])

    @pyqtSlot(result=str)
    def liberar_memoria(self) -> str:
        f = self._recortar
        if f is None:
            try:
                from servicios.recorte_ram import recortar as f  # noqa: N813
            except Exception:
                f = None
        if not callable(f):
            return _dump({"ok": False, "error": "El recorte de memoria no está disponible.",
                          "antes": 0.0, "despues": 0.0, "liberado": 0.0})
        try:
            antes, despues = f()
            antes, despues = float(antes), float(despues)
            if not (math.isfinite(antes) and math.isfinite(despues)):
                raise ValueError("MB no finitos")
        except Exception as e:
            _log.warning("puente_escritorio: liberar_memoria: %s", e)
            return _dump({"ok": False, "error": "No pude liberar memoria.", "antes": 0.0, "despues": 0.0,
                          "liberado": 0.0})
        return _dump({"ok": True, "error": "", "antes": round(antes, 1), "despues": round(despues, 1),
                      "liberado": round(max(0.0, antes - despues), 1)})


def registrar_en_canal(canal: Any, servicios: Any, escritorio: Any, config: Any, **kw) -> PuenteEscritorio:
    """Crea el puente y lo registra en `canal` (QWebChannel) como «escritorio».

    `kw` opcionales (keyword-only): anfitrion (si no, servicios.anfitrion), contexto
    (si no, servicios.contexto) y los inyectables de los tests. El puente queda como
    hijo del canal: vive lo mismo que él. Además:
      · engancha `anfitrion.navegar` (AnfitrionWeb) a `pedir_vista` si está vacío;
      · se apunta en `servicios._deshacer` (ServiciosCorte4): `servicios.desmontar()`
        (cambio de interfaz en caliente) lo desregistra del canal y lo desconecta.
    Hay que llamarlo antes de que la página cree su QWebChannel (antes de setUrl, o
    en el mismo tic de __init__): un objeto registrado después no lo ve el JS.
    """
    puente = PuenteEscritorio(servicios, escritorio, config,
                              parent=canal if isinstance(canal, QObject) else None, **kw)
    reg = getattr(canal, "registerObject", None)
    if callable(reg):
        reg("escritorio", puente)
        puente._canal = canal
    puente.enganchar_anfitrion()
    deshacer = getattr(servicios, "_deshacer", None)
    if isinstance(deshacer, list):
        deshacer.append(puente.cerrar)
    return puente
