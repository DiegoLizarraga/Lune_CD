"""
ui/montaje_vida.py — Monta sentarse (corte 7), la comida y Discord (corte 8) sobre
los servicios del corte 4.

Un solo enganche, como ui/montaje_ocio.py: la integración llama a `montar_vida` al
final de `montar_escritorio` (ui/montaje_escritorio.py), justo después de
`montar_ocio`, y guarda el resultado en `ServiciosCorte4.vida`. Web y nativa lo
reciben sin cambios propios y el cambio de interfaz en caliente lo desmonta solo:
`montar_vida` apunta su `desmontar` en `servicios_c4._deshacer`.

    vida = montar_vida(servicios_c4, config, voice=voice)
    vida.asiento.sentar("barra"); vida.comida.alternar("batido"); vida.discord.alternar()
    vida.desmontar()                 # idempotente (también lo hace servicios_c4.desmontar())

Qué hace, en este orden:
 1. crea `asiento` (ui/asiento_qt.ControlAsiento, con `hwnd_principal` = la ventana
    principal de Lune, que sí puede ser asiento aunque sea del mismo proceso),
    `comida` (ui/comida_qt.ControlComida, con el anfitrión: sin mascota a la vista
    reacciona con `anfitrion.reaccion` y en la web la dibuja la página) y `discord`
    (ui/discord_qt.ControlDiscord, con el modo del anfitrión). Se importan en
    diferido: si una pieza falta o falla, las demás siguen (queda None). Todas con
    el mismo `en_ui` (EnHiloQt de ui/montaje_ocio): las herramientas del modelo
    llegan desde el hilo del Ejecutor;
 2. las registra en ServiciosEscritorio con sus actividades de la tabla de
    prioridades: asiento → ("sentada",), comida → ("comida",), discord → ninguna;
 3. handlers del Despachador (aparecen solos en el radial, la bandeja y los atajos):
      sentarse        → asiento.sentar("barra") (arg «ventana» para una ventana) + aviso
      bajar           → asiento.bajar()
      comer_batido / comer_pastel → comida.alternar(id)
      guardar_comida  → comida.guardar()
      comida          → comida.alternar(la última o «batido»), marcado = hay comida
      discord         → discord.alternar(), marcado = discord.activo
    En la web con la ventana oculta y sin la mascota flotante, la comida que aparece
    enseña antes la ventana (si no, la página la dibujaría donde nadie la ve).
    «esquina» (de montar_escritorio) se envuelve: con Lune sentada (o cedida: de pie
    por un juego o un baile, pendiente de volver a su sitio), primero
    asiento.bajar("usuario"); si no, ControlAsiento la volvería a clavar en el borde.
    Lo mismo con lo que la coloca por código FUERA del Despachador (el «Llevar a la
    esquina» del menú propio de la mascota): la mascota emite `antes_de_colocar` y aquí,
    siguiendo a la actual por `escritorio.mascota_cambio`, se baja antes;
 4. las herramientas del modelo (`herramientas()`: mascota_sentarse y dar_de_comer)
    con `escritorio.registrar_herramienta`;
 5. `atajos.recargar()`: las acciones nuevas ya tienen handler.
Al desmontar, en orden inverso: herramientas, acciones y controladores fuera y lo
último, `deleteLater` de los objetos de Qt.

Todo es inyectable con `fabricas` (tests y la integración):
    asiento(escritorio, config, *, hwnd_principal, en_ui, parent)   → ControlAsiento
    comida(escritorio, config, *, anfitrion, en_ui, parent)          → ControlComida
    discord(escritorio, config, *, modo, nombre_modelo, parent)      → ControlDiscord
    en_ui()                                                          → callable en_ui(fn, espera_s)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject

_log = logging.getLogger("lune.montaje_vida")

# Controlador → actividades de nucleo/estado_mascota.PRIORIDAD que hace físicamente.
ACTIVIDADES: Dict[str, Tuple[str, ...]] = {
    "asiento": ("sentada",),
    "comida": ("comida",),
    "discord": (),
}
ORDEN = ("asiento", "comida", "discord")
SITIOS = ("barra", "ventana")
COMIDA_DEFECTO = "batido"


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("montaje vida: %s.%s falló", type(obj).__name__, metodo)
        return None


@dataclass
class ServiciosVida:
    """Lo montado por montar_vida. `desmontar()` lo quita todo (idempotente)."""
    asiento: Any = None
    comida: Any = None
    discord: Any = None
    en_ui: Any = None
    _deshacer: List[Callable[[], None]] = field(default_factory=list, repr=False)
    _desmontado: bool = field(default=False, repr=False)

    @property
    def desmontado(self) -> bool:
        return self._desmontado

    def desmontar(self) -> None:
        if self._desmontado:
            return
        self._desmontado = True
        pasos, self._deshacer = self._deshacer, []
        for f in reversed(pasos):
            try:
                f()
            except Exception:
                _log.exception("montaje vida: un paso de desmontar falló")

    detener = desmontar


# ── Fábricas por defecto (importación diferida) ──────────────────────────────────

def _asiento_defecto(escritorio, config, *, hwnd_principal=None, en_ui=None, parent=None):
    from ui.asiento_qt import ControlAsiento                              # agente A
    return ControlAsiento(escritorio, config, hwnd_principal=hwnd_principal, en_ui=en_ui, parent=parent)


def _comida_defecto(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
    from ui.comida_qt import ControlComida                                # agente C
    return ControlComida(escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent)


def _discord_defecto(escritorio, config, *, modo="normal", nombre_modelo=None, parent=None):
    from ui.discord_qt import ControlDiscord                              # agente D
    return ControlDiscord(escritorio, config, modo=modo, nombre_modelo=nombre_modelo, parent=parent)


def _en_ui_defecto(parent):
    from ui.montaje_ocio import EnHiloQt
    return EnHiloQt(parent)


def _crear(nombre: str, fabrica: Callable[[], Any]) -> Any:
    try:
        return fabrica()
    except Exception:
        _log.exception("montaje vida: no pude crear %s (sigue sin él)", nombre)
        return None


def hwnd_principal_de(anfitrion: Any) -> Callable[[], int]:
    """callable → HWND de la ventana principal: `anfitrion.hwnd_principal()` o, con un
    anfitrión de antes, el de `anfitrion.ventana` (web) / `anfitrion.win` (nativa)."""
    def hwnd() -> int:
        f = getattr(anfitrion, "hwnd_principal", None)
        if callable(f):
            try:
                return max(0, int(f() or 0))
            except Exception:
                return 0
        from ui.anfitrion_web import hwnd_de
        return hwnd_de(getattr(anfitrion, "ventana", None) or getattr(anfitrion, "win", None))
    return hwnd


def _visible(w: Any) -> bool:
    if w is None or getattr(w, "cerrado", False):
        return False
    try:
        return bool(w.isVisible())
    except Exception:
        return False


# ── Montaje ──────────────────────────────────────────────────────────────────────

def montar_vida(servicios_c4: Any, config: Any, *, voice: Any = None,
                fabricas: Optional[Dict[str, Any]] = None) -> ServiciosVida:
    """Crea, registra y conecta sentarse, comida y Discord (ver el docstring)."""
    fab = dict(fabricas or {})
    s4 = servicios_c4
    escritorio = getattr(s4, "escritorio", None)
    anfitrion = getattr(s4, "anfitrion", None)
    desp = getattr(s4, "despachador", None)
    avisar = getattr(s4, "avisar", None)
    parent = escritorio if isinstance(escritorio, QObject) else None
    modo = str(getattr(anfitrion, "modo", "normal") or "normal")

    en_ui = _crear("en_ui", lambda: fab.get("en_ui", lambda: _en_ui_defecto(parent))())
    vida = ServiciosVida(en_ui=en_ui)
    d = vida._deshacer

    # 1. Controladores.
    vida.asiento = _crear("asiento", lambda: fab.get("asiento", _asiento_defecto)(
        escritorio, config, hwnd_principal=hwnd_principal_de(anfitrion), en_ui=en_ui, parent=parent))
    vida.comida = _crear("comida", lambda: fab.get("comida", _comida_defecto)(
        escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent))
    vida.discord = _crear("discord", lambda: fab.get("discord", _discord_defecto)(
        escritorio, config, modo=modo, nombre_modelo=None, parent=parent))

    # Al desmontar (en orden inverso a como se apuntan): lo último que se hace es
    # soltar los objetos de Qt.
    def soltar_objetos():
        for obj in (vida.discord, vida.comida, vida.asiento, vida.en_ui):
            if isinstance(obj, QObject):
                try:
                    obj.deleteLater()
                except RuntimeError:
                    pass
    d.append(soltar_objetos)

    def recargar_atajos():
        _llamar(getattr(s4, "atajos", None), "recargar")
    d.append(recargar_atajos)

    # 2. Registro en ServiciosEscritorio (arrancan ya si el escritorio estaba iniciado).
    registrados: List[Tuple[str, Any]] = []
    for nombre in ORDEN:
        ctl = getattr(vida, nombre)
        if ctl is None or escritorio is None:
            continue
        try:
            if ACTIVIDADES[nombre]:
                try:
                    escritorio.registrar(nombre, ctl, ACTIVIDADES[nombre])
                except TypeError:                       # un escritorio sin tabla de actividades
                    escritorio.registrar(nombre, ctl)
            else:
                escritorio.registrar(nombre, ctl)
            registrados.append((nombre, ctl))
        except Exception:
            _log.exception("montaje vida: no pude registrar %s", nombre)

    def quitar_controladores():
        for nombre in reversed(ORDEN):
            ctl = getattr(vida, nombre)
            if ctl is None:
                continue
            quitado = False
            if any(c is ctl for _, c in registrados):
                try:
                    if escritorio.obtener(nombre) is ctl:
                        quitado = bool(escritorio.quitar(nombre)) and bool(getattr(escritorio, "iniciado", False))
                except Exception:
                    _log.exception("montaje vida: no pude quitar %s del escritorio", nombre)
            if not quitado:                                # detener es idempotente en los tres
                _llamar(ctl, "detener")
    d.append(quitar_controladores)

    # 3. Handlers del Despachador.
    if desp is not None:
        _registrar_acciones(vida, desp, anfitrion, avisar, d)
    if vida.asiento is not None and escritorio is not None:
        _bajar_al_colocar_mascota(vida.asiento, escritorio, d)

    # 4. Herramientas del modelo.
    if escritorio is not None:
        herramientas: List[str] = []
        for ctl in (vida.asiento, vida.comida):
            h = _llamar(ctl, "herramientas") if ctl is not None else None
            if not isinstance(h, dict):
                continue
            for nombre, fn in h.items():
                if not callable(fn):
                    continue
                try:
                    escritorio.registrar_herramienta(str(nombre), fn)
                    herramientas.append(str(nombre))
                except Exception:
                    _log.exception("montaje vida: no pude registrar la herramienta %s", nombre)

        def quitar_herramientas():
            for nombre in herramientas:
                _llamar(escritorio, "quitar_herramienta", nombre)
        d.append(quitar_herramientas)

    # 5. Los atajos que ahora tienen handler se registran.
    recargar_atajos()

    # 6. Que el cambio de interfaz (servicios_c4.desmontar) lo quite también.
    deshacer_c4 = getattr(s4, "_deshacer", None)
    if isinstance(deshacer_c4, list):
        deshacer_c4.append(vida.desmontar)
    return vida


def _registrar_acciones(vida: ServiciosVida, desp: Any, anfitrion: Any,
                        avisar: Optional[Callable[[str], None]], deshacer: List[Callable[[], None]]) -> None:
    a, c, dc = vida.asiento, vida.comida, vida.discord
    propios: List[Tuple[str, Callable]] = []

    def reg(id_: str, fn: Callable, marcado: Optional[Callable[[], Any]] = None) -> None:
        try:
            desp.registrar(id_, fn, marcado=marcado)
            propios.append((id_, fn))
        except Exception:
            _log.exception("montaje vida: no pude registrar la acción %s", id_)

    def aviso(texto: Any) -> None:
        if not texto:
            return
        if callable(avisar):
            try:
                avisar(str(texto))
                return
            except Exception:
                _log.exception("montaje vida: el aviso falló")
        _llamar(anfitrion, "aviso", str(texto))

    if a is not None:
        def sentarse(arg: str = "") -> bool:
            sitio = str(arg or "").strip().lower()
            r = a.sentar(sitio if sitio in SITIOS else "barra")
            ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (bool(r), ""))
            aviso(texto)
            return bool(ok)
        reg("sentarse", sentarse)
        reg("bajar", lambda: bool(a.bajar()))
        _bajar_antes_de_colocar(a, desp, deshacer)

    if c is not None:
        def asegurar_vista() -> None:
            """Web sin la flotante a la vista y con la ventana oculta: la comida la dibuja
            la página, así que primero se enseña la ventana."""
            if getattr(c, "activa", None) is not None or str(getattr(anfitrion, "modo", "")) != "normal":
                return
            m = _llamar(anfitrion, "mascota")
            if _visible(m):
                return
            if _llamar(anfitrion, "ventana_visible") is False:
                _llamar(anfitrion, "mostrar_ventana")

        def comer(id_: str) -> str:
            asegurar_vista()
            return str(c.alternar(id_) or "")

        reg("comer_batido", lambda: comer("batido"))
        reg("comer_pastel", lambda: comer("pastel"))
        reg("guardar_comida", lambda: bool(c.guardar()))
        reg("comida", lambda: comer(getattr(c, "ultima", "") or COMIDA_DEFECTO),
            marcado=lambda: getattr(c, "activa", None) is not None)

    if dc is not None:
        reg("discord", lambda: bool(dc.alternar()), marcado=lambda: bool(getattr(dc, "activo", False)))

    def quitar_acciones():
        for id_, fn in propios:
            try:
                if getattr(desp, "_fns", {}).get(id_, fn) is fn:
                    desp.quitar(id_)
            except Exception:
                _log.exception("montaje vida: no pude quitar la acción %s", id_)
    deshacer.append(quitar_acciones)


# Acciones del corte 4 que colocan la mascota por código: con Lune sentada, ControlAsiento
# la volvería a clavar en el borde, así que primero se baja (motivo «usuario»).
COLOCAN_MASCOTA = ("esquina",)


def _hay_que_bajar(asiento: Any) -> bool:
    """Sentada, o cedida (de pie por un juego, un baile… y con `reanudar` pendiente: al
    acabar cruzaría la pantalla de vuelta a su ventana)."""
    return bool(getattr(asiento, "sentada_en", "") or getattr(asiento, "cedida", False))


def _bajar_antes_de_colocar(asiento: Any, desp: Any, deshacer: List[Callable[[], None]]) -> None:
    """Envuelve los handlers de COLOCAN_MASCOTA que ya estén registrados (montar_escritorio
    los pone antes): si está sentada, `asiento.bajar("usuario")` y luego el de siempre, con
    los mismos argumentos y el mismo ✔. Al desmontar vuelve el original (si nadie lo cambió)."""
    from nucleo.acciones_ui import Despachador
    fns = getattr(desp, "_fns", None)
    marcados = getattr(desp, "_marcados", None)
    if not isinstance(fns, dict):
        return
    for id_ in COLOCAN_MASCOTA:
        original = fns.get(id_)
        if original is None:
            continue
        marcado = marcados.get(id_) if isinstance(marcados, dict) else None
        interno = Despachador()                       # reparte los argumentos como el de verdad
        interno.registrar(id_, original)

        def envoltura(arg: str = "", _id=id_, _interno=interno, **kw) -> bool:
            if _hay_que_bajar(asiento):
                _llamar(asiento, "bajar", "usuario")
            if not _interno.ejecutar(_id, arg, **kw):
                raise RuntimeError(f"la acción {_id} falló")    # el Despachador de fuera lo apunta
            return True

        try:
            desp.registrar(id_, envoltura, marcado=marcado)
        except Exception:
            _log.exception("montaje vida: no pude envolver la acción %s", id_)
            continue

        def restaurar(_id=id_, _env=envoltura, _orig=original, _marc=marcado) -> None:
            try:
                if getattr(desp, "_fns", {}).get(_id) is _env:
                    desp.registrar(_id, _orig, marcado=_marc)
            except Exception:
                _log.exception("montaje vida: no pude devolver la acción %s", _id)
        deshacer.append(restaurar)


def _bajar_al_colocar_mascota(asiento: Any, escritorio: Any, deshacer: List[Callable[[], None]]) -> None:
    """La mascota colocada por código sin pasar por el Despachador (su propio menú «Llevar a
    la esquina»): emite `antes_de_colocar` antes de moverse y, si está sentada, aquí se baja
    (motivo «usuario»). Sigue a la mascota actual por `escritorio.mascota_cambio`; al
    desmontar se desconecta todo."""
    senal_cambio = getattr(escritorio, "mascota_cambio", None)
    if senal_cambio is None or not hasattr(senal_cambio, "connect"):
        return
    actual: Dict[str, Any] = {"m": None}

    def bajar() -> None:
        if _hay_que_bajar(asiento):
            _llamar(asiento, "bajar", "usuario")

    def poner(m: Any) -> None:
        vieja, actual["m"] = actual["m"], None
        if vieja is not None:
            try:
                vieja.antes_de_colocar.disconnect(bajar)
            except (TypeError, RuntimeError, AttributeError):
                pass
        s = getattr(m, "antes_de_colocar", None) if m is not None else None
        if s is not None and hasattr(s, "connect"):
            try:
                s.connect(bajar)
                actual["m"] = m
            except (TypeError, RuntimeError):
                pass

    try:
        senal_cambio.connect(poner)
    except (TypeError, RuntimeError):
        return
    poner(getattr(escritorio, "mascota", None))

    def soltar() -> None:
        try:
            senal_cambio.disconnect(poner)
        except (TypeError, RuntimeError):
            pass
        poner(None)
    deshacer.append(soltar)


__all__ = ("ServiciosVida", "montar_vida", "ACTIVIDADES", "ORDEN", "COLOCAN_MASCOTA", "hwnd_principal_de")
