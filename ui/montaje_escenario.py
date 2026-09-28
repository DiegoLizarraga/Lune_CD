"""
ui/montaje_escenario.py — Monta el reproductor de bailes MMD/VRMA (corte 9) y Minecraft
(corte 10) sobre los servicios del corte 4.

Un solo enganche, como ui/montaje_ocio.py y ui/montaje_vida.py: la integración llama a
`montar_escenario` al final de `montar_escritorio` (ui/montaje_escritorio.py), justo
después de `montar_vida`, y guarda el resultado en `ServiciosCorte4.escenario`. Web y
nativa lo reciben sin cambios propios y el cambio de interfaz en caliente lo desmonta
solo (para el baile y el bot): `montar_escenario` apunta su `desmontar` en
`servicios_c4._deshacer`.

    esc = montar_escenario(servicios_c4, config, voice=voice)
    esc.mmd.reproducir(id_); esc.minecraft.alternar_reacciones(); esc.minecraft.conectar_bot()
    esc.desmontar()                  # idempotente (también lo hace servicios_c4.desmontar())

Qué hace, en este orden:
 1. crea `mmd` (ui/mmd_qt.ControlMMD) y `minecraft` (ui/minecraft_qt.ControlMinecraft).
    Se importan en diferido: si una pieza falta o falla, la otra sigue (queda None). Las
    dos con el mismo `en_ui` (EnHiloQt de ui/montaje_ocio): las herramientas del modelo
    llegan desde el hilo del Ejecutor;
 2. las registra en ServiciosEscritorio: mmd → ("mmd",) (prioridad 40: cede ante juego,
    alarma y pantalla grande, y le quita el sitio a la sentada, la comida y el baile
    automático); minecraft → ninguna (solo lee el bus);
 3. handlers del Despachador (aparecen solos en el radial, la bandeja y los atajos):
      bailes         → la biblioteca: en la web enseña la ventana y `mmd.pedir_vista()`
                       (el puente `escenario` lleva a la vista «bailes»); en la nativa,
                       `anfitrion.abrir_ajustes("escenario")`
      minecraft      → minecraft.alternar_reacciones() + aviso; ✔ = reaccionando
      minecraft_bot  → minecraft.alternar_bot(): conecta o desconecta el bot + aviso con lo
                       que diga (nunca lo instala: D3); ✔ = bot conectado
    («bailar» y «baile_pausa» siguen en montaje_ocio, que ya enruta al MMD si suena);
 4. las herramientas del modelo (`herramientas()` de los dos: listar_bailes y
    minecraft_estado/orden/bot) con `escritorio.registrar_herramienta`;
 5. `atajos.recargar()`: las acciones nuevas ya tienen handler.
Al desmontar, en orden inverso: herramientas, acciones y controladores fuera (el de
Minecraft para el bot esperando: no queda node huérfano) y lo último, `deleteLater` de
los objetos de Qt.

Todo es inyectable con `fabricas` (tests y la integración):
    mmd(escritorio, config, *, anfitrion, en_ui, parent)                → ControlMMD
    minecraft(escritorio, config, *, anfitrion, voice, en_ui, parent)   → ControlMinecraft
    en_ui()                                                             → callable en_ui(fn, espera_s)
Una fábrica a False = sin esa pieza.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject

_log = logging.getLogger("lune.montaje_escenario")

# Controlador → actividades de nucleo/estado_mascota.PRIORIDAD que hace físicamente.
ACTIVIDADES: Dict[str, Tuple[str, ...]] = {
    "mmd": ("mmd",),
    "minecraft": (),
}
ORDEN = ("mmd", "minecraft")
SECCION_AJUSTES = "escenario"           # anfitrion.abrir_ajustes(...) en la nativa
VISTA_BAILES = "bailes"


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("montaje escenario: %s.%s falló", type(obj).__name__, metodo)
        return None


@dataclass
class ServiciosEscenario:
    """Lo montado por montar_escenario. `desmontar()` lo quita todo (idempotente)."""
    mmd: Any = None
    minecraft: Any = None
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
                _log.exception("montaje escenario: un paso de desmontar falló")

    detener = desmontar


# ── Fábricas por defecto (importación diferida) ──────────────────────────────────

def _mmd_defecto(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
    from ui.mmd_qt import ControlMMD                                     # agente C
    return ControlMMD(escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent)


def _minecraft_defecto(escritorio, config, *, anfitrion=None, voice=None, en_ui=None, parent=None):
    from ui.minecraft_qt import ControlMinecraft                         # agente D
    return ControlMinecraft(escritorio, config, anfitrion=anfitrion, voice=voice, en_ui=en_ui, parent=parent)


def _en_ui_defecto(parent):
    from ui.montaje_ocio import EnHiloQt
    return EnHiloQt(parent)


FABRICAS_DEFECTO: Dict[str, Callable[..., Any]] = {"mmd": _mmd_defecto, "minecraft": _minecraft_defecto}


def _crear(nombre: str, fabrica: Callable[[], Any]) -> Any:
    try:
        return fabrica()
    except Exception:
        _log.exception("montaje escenario: no pude crear %s (sigue sin él)", nombre)
        return None


# ── Montaje ──────────────────────────────────────────────────────────────────────

def montar_escenario(servicios_c4: Any, config: Any, *, voice: Any = None,
                     fabricas: Optional[Dict[str, Any]] = None) -> ServiciosEscenario:
    """Crea, registra y conecta el reproductor de bailes y Minecraft (ver el docstring)."""
    fab = dict(fabricas or {})
    s4 = servicios_c4
    escritorio = getattr(s4, "escritorio", None)
    anfitrion = getattr(s4, "anfitrion", None)
    desp = getattr(s4, "despachador", None)
    avisar = getattr(s4, "avisar", None)
    parent = escritorio if isinstance(escritorio, QObject) else None

    en_ui = _crear("en_ui", lambda: fab.get("en_ui", lambda: _en_ui_defecto(parent))())
    esc = ServiciosEscenario(en_ui=en_ui)
    d = esc._deshacer

    # 1. Controladores (una fábrica a False = sin esa pieza).
    f_mmd = fab.get("mmd", _mmd_defecto)
    if f_mmd is not False:
        esc.mmd = _crear("mmd", lambda: f_mmd(escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent))
    f_mc = fab.get("minecraft", _minecraft_defecto)
    if f_mc is not False:
        esc.minecraft = _crear("minecraft", lambda: f_mc(escritorio, config, anfitrion=anfitrion, voice=voice,
                                                         en_ui=en_ui, parent=parent))

    # Al desmontar (en orden inverso a como se apuntan): lo último que se hace es
    # soltar los objetos de Qt.
    def soltar_objetos():
        for obj in (esc.minecraft, esc.mmd, esc.en_ui):
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
        ctl = getattr(esc, nombre)
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
            _log.exception("montaje escenario: no pude registrar %s", nombre)

    def quitar_controladores():
        for nombre in reversed(ORDEN):
            ctl = getattr(esc, nombre)
            if ctl is None:
                continue
            quitado = False
            if any(c is ctl for _, c in registrados):
                try:
                    if escritorio.obtener(nombre) is ctl:
                        quitado = bool(escritorio.quitar(nombre)) and bool(getattr(escritorio, "iniciado", False))
                except Exception:
                    _log.exception("montaje escenario: no pude quitar %s del escritorio", nombre)
            if not quitado:                                # detener es idempotente en los dos
                _llamar(ctl, "detener")
    d.append(quitar_controladores)

    # 3. Handlers del Despachador.
    if desp is not None:
        _registrar_acciones(esc, desp, anfitrion, avisar, d)

    # 4. Herramientas del modelo.
    if escritorio is not None:
        herramientas: List[str] = []
        for ctl in (esc.mmd, esc.minecraft):
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
                    _log.exception("montaje escenario: no pude registrar la herramienta %s", nombre)

        def quitar_herramientas():
            for nombre in herramientas:
                _llamar(escritorio, "quitar_herramienta", nombre)
        d.append(quitar_herramientas)

    # 5. Los atajos que ahora tienen handler se registran.
    recargar_atajos()

    # 6. Que el cambio de interfaz (servicios_c4.desmontar) lo quite también.
    deshacer_c4 = getattr(s4, "_deshacer", None)
    if isinstance(deshacer_c4, list):
        deshacer_c4.append(esc.desmontar)
    return esc


def _registrar_acciones(esc: ServiciosEscenario, desp: Any, anfitrion: Any,
                        avisar: Optional[Callable[[str], None]], deshacer: List[Callable[[], None]]) -> None:
    m, mc = esc.mmd, esc.minecraft
    propios: List[Tuple[str, Callable]] = []

    def reg(id_: str, fn: Callable, marcado: Optional[Callable[[], Any]] = None) -> None:
        try:
            desp.registrar(id_, fn, marcado=marcado)
            propios.append((id_, fn))
        except Exception:
            _log.exception("montaje escenario: no pude registrar la acción %s", id_)

    def aviso(texto: Any) -> None:
        if not texto:
            return
        if callable(avisar):
            try:
                avisar(str(texto))
                return
            except Exception:
                _log.exception("montaje escenario: el aviso falló")
        _llamar(anfitrion, "aviso", str(texto))

    if m is not None:
        def bailes() -> None:
            """La biblioteca: en la web, la ventana con la vista «bailes» (la lleva el puente
            `escenario` con vista_pedida); en la nativa, Ajustes (apartado BAILES). La lista la
            vuelve a mirar cada panel al abrirse (mmd.refrescar)."""
            if str(getattr(anfitrion, "modo", "normal") or "normal") == "normal":
                _llamar(anfitrion, "mostrar_ventana")
                if callable(getattr(m, "pedir_vista", None)):
                    m.pedir_vista()
                else:
                    _llamar(anfitrion, "navegar", VISTA_BAILES)
                return
            if callable(getattr(anfitrion, "abrir_ajustes", None)):
                anfitrion.abrir_ajustes(SECCION_AJUSTES)
            else:
                _llamar(anfitrion, "mostrar_ventana")
        reg("bailes", bailes)

    if mc is not None:
        def minecraft() -> bool:
            on = bool(mc.alternar_reacciones())
            aviso("Reacciono a tu partida de Minecraft." if on else "Ya no reacciono a Minecraft.")
            return on
        reg("minecraft", minecraft, marcado=lambda: bool(getattr(mc, "reaccionando", False)))

        def minecraft_bot() -> bool:
            """Conecta o desconecta el bot (`mc.alternar_bot()`, del agente D). Lo pide la persona
            (bandeja, radial): sin aprobación. Nunca lo instala (D3): sin instalar, el aviso lo
            manda a Ajustes → Minecraft."""
            alternar = getattr(mc, "alternar_bot", None)
            if callable(alternar):
                r = alternar()
            elif bool(getattr(mc, "bot_conectado", False)) or _bot_vivo(mc):
                r = (bool(mc.desconectar_bot()), "Desconecto el bot de Minecraft.")
            else:
                r = mc.conectar_bot()
            ok, texto = (r if isinstance(r, tuple) and len(r) == 2 else (bool(r), ""))
            aviso(texto)
            return bool(ok)
        reg("minecraft_bot", minecraft_bot, marcado=lambda: bool(getattr(mc, "bot_conectado", False)))

    def quitar_acciones():
        for id_, fn in propios:
            try:
                if getattr(desp, "_fns", {}).get(id_, fn) is fn:
                    desp.quitar(id_)
            except Exception:
                _log.exception("montaje escenario: no pude quitar la acción %s", id_)
    deshacer.append(quitar_acciones)


def _bot_vivo(mc: Any) -> bool:
    """¿Hay un proceso del bot en marcha (conectando)? Sin él, «minecraft_bot» conecta."""
    proceso = getattr(mc, "proceso", None)
    try:
        return bool(getattr(proceso, "vivo", False))
    except Exception:
        return False


__all__ = ("ServiciosEscenario", "montar_escenario", "ACTIVIDADES", "ORDEN", "FABRICAS_DEFECTO",
           "SECCION_AJUSTES")
