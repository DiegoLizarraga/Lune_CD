"""
ui/montaje_ocio.py — Monta los servicios de ocio de los cortes 5 y 6 (alarmas,
pantalla grande y salvapantallas, baile) sobre los del corte 4.

Un solo enganche: la integración llama a `montar_ocio` al final de
`montar_escritorio` (ui/montaje_escritorio.py) y guarda el resultado en
`ServiciosCorte4.ocio`. Así web y nativa lo reciben sin cambios propios y el
cambio de interfaz en caliente lo desmonta solo: `montar_ocio` apunta su
`desmontar` en `servicios_c4._deshacer`, que se ejecuta antes de soltar los
controladores del corte 4.

    ocio = montar_ocio(servicios_c4, config, voice=voice)
    ocio.grande.alternar(); ocio.alarmas.rapido(5); ocio.baile.bailar()
    ocio.desmontar()                 # idempotente (también lo hace servicios_c4.desmontar())

Qué hace, en este orden:
 1. crea `grande` (ui/pantalla_grande_qt.ControlPantallaGrande), luego `alarmas`
    (ui/alarmas_qt.ControlAlarmasQt, con `grande=` y `avisar=servicios_c4.avisar`)
    y luego `baile` (ui/baile_qt.ControlBaile). Se importan en diferido: si una
    pieza falta o falla, las demás siguen (queda None). Las tres reciben el
    mismo `en_ui` (EnHiloQt): las herramientas del modelo llegan desde el hilo
    del Ejecutor y lo visual tiene que ir al de Qt.
 2. las registra en ServiciosEscritorio con sus actividades de la tabla de
    prioridades: grande → ("grande", "salvapantallas"), alarmas → ("alarma",),
    baile → ("baile",);
 3. handlers del Despachador: pantalla_grande, bailar, baile_pausa, alarma y
    temporizador_rapido (aparecen solos en el radial, la bandeja y los atajos);
 4. las herramientas del modelo de cada controlador (`herramientas()`) con
    `escritorio.registrar_herramienta`;
 5. `atajos.recargar()`: pantalla_grande y baile_pausa ya tienen handler;
 6. los botones de VentanaReloj → la alarma: pedir_apagar_alarma →
    alarmas.apagar(forzar=True), pedir_posponer_alarma → alarmas.posponer().
Al desmontar, lo último: borrar (deleteLater) las ventanas que abrieron sus
acciones (el editor de alarmas de la nativa, sin padre: si no, quedaría huérfano
tras un cambio de interfaz) y los objetos de Qt de los controladores.

Todo es inyectable con `fabricas` (tests y la integración):
    grande(escritorio, config, *, anfitrion, en_ui, parent)          → ControlPantallaGrande
    alarmas(escritorio, config, *, voice, grande, avisar, en_ui, parent) → ControlAlarmasQt
    baile(escritorio, config, *, en_ui, parent)                       → ControlBaile
    en_ui()                                                           → callable en_ui(fn, espera_s)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, Qt, pyqtSignal

_log = logging.getLogger("lune.montaje_ocio")

ESPERA_UI_S = 5.0
# Controlador → actividades de nucleo/estado_mascota.PRIORIDAD que hace físicamente.
ACTIVIDADES: Dict[str, Tuple[str, ...]] = {
    "grande": ("grande", "salvapantallas"),
    "alarmas": ("alarma",),
    "baile": ("baile",),
}
ORDEN = ("grande", "alarmas", "baile")
MINUTOS_RAPIDO = 5
MINUTOS_RAPIDO_MAX = 180


def _llamar(obj: Any, metodo: str, *args, **kw) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args, **kw)
    except Exception:
        _log.exception("montaje ocio: %s.%s falló", type(obj).__name__, metodo)
        return None


class EnHiloQt(QObject):
    """`en_ui(fn, espera_s=5.0)`: corre fn() en el hilo de Qt y devuelve su
    resultado. Desde el hilo de Qt, directo; desde otro, en cola, esperando como
    mucho `espera_s` (TimeoutError si la interfaz no contesta). La excepción de fn
    se relanza en quien llama. Igual que web_bridge.LuneBridge.en_ui."""

    _pedir = pyqtSignal(object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._hilo = threading.get_ident()
        self._pedir.connect(self._correr, Qt.ConnectionType.QueuedConnection)

    def en_hilo_qt(self) -> bool:
        return threading.get_ident() == self._hilo

    def __call__(self, fn: Callable[[], Any], espera_s: float = ESPERA_UI_S) -> Any:
        if self.en_hilo_qt():
            return fn()
        hecho = threading.Event()
        caja: Dict[str, Any] = {}

        def correr():
            try:
                caja["r"] = fn()
            except Exception as e:                    # noqa: BLE001
                caja["e"] = e
            finally:
                hecho.set()

        try:
            self._pedir.emit(correr)
        except RuntimeError as e:                     # el QObject ya se destruyó
            raise TimeoutError("la interfaz ya no está") from e
        if not hecho.wait(espera_s):
            raise TimeoutError("la interfaz no respondió a tiempo")
        if "e" in caja:
            raise caja["e"]
        return caja.get("r")

    @staticmethod
    def _correr(fn) -> None:
        try:
            fn()
        except Exception:
            pass


@dataclass
class ServiciosOcio:
    """Lo montado por montar_ocio. `desmontar()` lo quita todo (idempotente)."""
    alarmas: Any = None
    grande: Any = None
    baile: Any = None
    en_ui: Any = None
    ventanas: List[Any] = field(default_factory=list, repr=False)    # abiertas por sus acciones
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
                _log.exception("montaje ocio: un paso de desmontar falló")

    detener = desmontar


# ── Fábricas por defecto (importación diferida) ──────────────────────────────────

def _grande_defecto(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
    from ui.pantalla_grande_qt import ControlPantallaGrande           # agente B
    return ControlPantallaGrande(escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent)


def _alarmas_defecto(escritorio, config, *, voice=None, grande=None, avisar=None, en_ui=None, parent=None):
    from ui.alarmas_qt import ControlAlarmasQt                        # agente A
    return ControlAlarmasQt(escritorio, config, voice=voice, grande=grande, avisar=avisar,
                            en_ui=en_ui, parent=parent)


def _baile_defecto(escritorio, config, *, en_ui=None, parent=None):
    from ui.baile_qt import ControlBaile                              # agente C
    return ControlBaile(escritorio, config, en_ui=en_ui, parent=parent)


def _crear(nombre: str, fabrica: Callable[[], Any]) -> Any:
    try:
        return fabrica()
    except Exception:
        _log.exception("montaje ocio: no pude crear %s (sigue sin él)", nombre)
        return None


def _conectar(deshacer: List[Callable[[], None]], senal: Any, slot: Callable) -> None:
    if senal is None or not hasattr(senal, "connect"):
        return
    try:
        senal.connect(slot)
    except (TypeError, RuntimeError):
        return

    def quitar():
        try:
            senal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    deshacer.append(quitar)


def minutos_rapido(arg: Any) -> int:
    """«5», «10m», "" → minutos del temporizador rápido (1–180; 5 si no vale)."""
    texto = str(arg or "").strip().lower().rstrip("m").strip()
    try:
        n = int(float(texto))
    except (TypeError, ValueError):
        return MINUTOS_RAPIDO
    return min(max(n, 1), MINUTOS_RAPIDO_MAX)


# ── Montaje ──────────────────────────────────────────────────────────────────────

def montar_ocio(servicios_c4: Any, config: Any, *, voice: Any = None,
                fabricas: Optional[Dict[str, Any]] = None) -> ServiciosOcio:
    """Crea, registra y conecta alarmas, pantalla grande y baile (ver el docstring)."""
    fab = dict(fabricas or {})
    s4 = servicios_c4
    escritorio = getattr(s4, "escritorio", None)
    anfitrion = getattr(s4, "anfitrion", None)
    desp = getattr(s4, "despachador", None)
    avisar = getattr(s4, "avisar", None)
    parent = escritorio if isinstance(escritorio, QObject) else None

    en_ui = _crear("en_ui", lambda: fab.get("en_ui", lambda: EnHiloQt(parent))())
    ocio = ServiciosOcio(en_ui=en_ui)
    d = ocio._deshacer

    # 1. Controladores (grande antes que alarmas: las alarmas lo usan).
    ocio.grande = _crear("grande", lambda: fab.get("grande", _grande_defecto)(
        escritorio, config, anfitrion=anfitrion, en_ui=en_ui, parent=parent))
    ocio.alarmas = _crear("alarmas", lambda: fab.get("alarmas", _alarmas_defecto)(
        escritorio, config, voice=voice, grande=ocio.grande, avisar=avisar, en_ui=en_ui, parent=parent))
    ocio.baile = _crear("baile", lambda: fab.get("baile", _baile_defecto)(
        escritorio, config, en_ui=en_ui, parent=parent))

    # Al desmontar (en orden inverso a como se apuntan): lo último que se hace es
    # soltar los objetos de Qt.
    def soltar_objetos():
        ventanas, ocio.ventanas = list(ocio.ventanas), []
        for w in ventanas:
            for metodo in ("close", "deleteLater"):
                try:
                    getattr(w, metodo)()
                except (RuntimeError, AttributeError):   # ya borrada
                    pass
        for obj in (ocio.baile, ocio.alarmas, ocio.grande, ocio.en_ui):
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
        ctl = getattr(ocio, nombre)
        if ctl is None or escritorio is None:
            continue
        try:
            try:
                escritorio.registrar(nombre, ctl, ACTIVIDADES[nombre])
            except TypeError:                           # un escritorio sin tabla de actividades
                escritorio.registrar(nombre, ctl)
            registrados.append((nombre, ctl))
        except Exception:
            _log.exception("montaje ocio: no pude registrar %s", nombre)

    def quitar_controladores():
        for nombre, ctl in reversed(registrados):
            quitado = False
            try:
                if escritorio.obtener(nombre) is ctl:
                    quitado = bool(escritorio.quitar(nombre)) and bool(getattr(escritorio, "iniciado", False))
            except Exception:
                _log.exception("montaje ocio: no pude quitar %s del escritorio", nombre)
            if not quitado:
                _llamar(ctl, "detener")
    d.append(quitar_controladores)

    # 6. Botones de VentanaReloj → la alarma.
    g, a, b = ocio.grande, ocio.alarmas, ocio.baile
    if g is not None and a is not None:
        _conectar(d, getattr(g, "pedir_apagar_alarma", None), lambda: _llamar(a, "apagar", forzar=True))
        _conectar(d, getattr(g, "pedir_posponer_alarma", None), lambda: _llamar(a, "posponer"))

    # 3. Handlers del Despachador.
    if desp is not None:
        _registrar_acciones(ocio, desp, anfitrion, avisar, d)

    # 4. Herramientas del modelo.
    if escritorio is not None:
        herramientas: List[str] = []
        for ctl in (g, a, b):
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
                    _log.exception("montaje ocio: no pude registrar la herramienta %s", nombre)

        def quitar_herramientas():
            for nombre in herramientas:
                _llamar(escritorio, "quitar_herramienta", nombre)
        d.append(quitar_herramientas)

    # 5. Los atajos que ahora tienen handler se registran.
    recargar_atajos()

    # 7. Que el cambio de interfaz (servicios_c4.desmontar) lo quite también.
    deshacer_c4 = getattr(s4, "_deshacer", None)
    if isinstance(deshacer_c4, list):
        deshacer_c4.append(ocio.desmontar)
    return ocio


def _registrar_acciones(ocio: ServiciosOcio, desp: Any, anfitrion: Any,
                        avisar: Optional[Callable[[str], None]], deshacer: List[Callable[[], None]]) -> None:
    g, a, b = ocio.grande, ocio.alarmas, ocio.baile
    propios: List[Tuple[str, Callable]] = []

    def reg(id_: str, fn: Callable, marcado: Optional[Callable[[], Any]] = None) -> None:
        try:
            desp.registrar(id_, fn, marcado=marcado)
            propios.append((id_, fn))
        except Exception:
            _log.exception("montaje ocio: no pude registrar la acción %s", id_)

    def aviso(texto: str) -> None:
        if callable(avisar):
            try:
                avisar(texto)
            except Exception:
                _log.exception("montaje ocio: el aviso falló")

    if g is not None:
        reg("pantalla_grande", lambda: g.alternar(), marcado=lambda: bool(getattr(g, "activo", False)))

    if b is not None:
        def bailar():
            if getattr(b, "bailando", False):
                b.parar()
            else:
                b.bailar()
        reg("bailar", bailar, marcado=lambda: bool(getattr(b, "bailando", False)))
        reg("baile_pausa", lambda: b.pausa())

    if a is not None:
        def abrir_alarmas():
            navegar = getattr(anfitrion, "navegar", None)
            if str(getattr(anfitrion, "modo", "")) == "normal" and callable(navegar):
                _llamar(anfitrion, "mostrar_ventana")
                navegar("alarmas")
                return
            w = a.abrir_dialogo()
            if isinstance(w, QObject) and w not in ocio.ventanas:
                ocio.ventanas.append(w)                 # se borra al desmontar
        reg("alarma", abrir_alarmas)

        def temporizador_rapido(arg: str = ""):
            n = minutos_rapido(arg)
            a.rapido(n)
            aviso(f"⏲ {n} min")
        reg("temporizador_rapido", temporizador_rapido)

    def quitar_acciones():
        for id_, fn in propios:
            try:
                if getattr(desp, "_fns", {}).get(id_, fn) is fn:
                    desp.quitar(id_)
            except Exception:
                _log.exception("montaje ocio: no pude quitar la acción %s", id_)
    deshacer.append(quitar_acciones)


__all__ = ("EnHiloQt", "ServiciosOcio", "montar_ocio", "ACTIVIDADES", "minutos_rapido")
