"""
ui/baile_qt.py — `ControlBaile`: Lune baila con la música del PC (o a mano).

El controlador del baile de ServiciosEscritorio (ui/escritorio.py), actividad
`baile` de la tabla de prioridades. Une:

- el detector (servicios/musica_detector.DetectorMusica, en su hilo): «suena
  música en una app permitida» y su pulso. Sus avisos pasan al hilo de Qt con
  señales en cola;
- la tabla de prioridades: con música, `prioridad.iniciar("baile", "musica")`;
  si no se permite (pantalla grande, alarma, juego, sentada, comida…) no baila y
  lo vuelve a intentar cuando cambie el estado. Dormida NO baila y no se la
  despierta (decisión D5): baila al despertar si la música sigue;
- la asistente: `asistente.bailar(True, opciones)` y `asistente.pulso(bpm, fase,
  energia)` (≤ 2 Hz; las páginas y los sprites extrapolan con su reloj). Sin
  asistente, la barra web y la carita nativa lo pintan con `estado_cambio`/`pulso`.

Baile a mano (`bailar(segundos)`, herramienta `asistente_bailar`, acción
`bailar`): `prioridad.iniciar("baile", "manual")`, el detector sigue el pulso
de lo que más suene (aunque su app no esté permitida) y, sin música, un
metrónomo de 120 BPM. `parar()` para y no vuelve a bailar sola hasta que la
música se calle (igual que `pausa()`, la acción `baile_pausa`).

`ceder` (la tabla le quita el baile): fuera lo visual. `reanudar`: solo si la
música sigue; si no, suelta la actividad.

Señales (JSON en texto, para el puente web):
    estado_cambio(str)   {bailando, origen: auto|manual|"", musica, app, estilo,
                          bpm, energia, auto, pausado_hasta_silencio, disponible}
    pulso(str)           {bpm, fase, energia}, como mucho 2 veces por segundo
    apps_cambio(str)     ["Spotify", …] que suenan ahora
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from nucleo import baile as nb
from nucleo.estado_asistente import BAILE_MUSICA
from nucleo.pulso import Pulso, metronomo
from servicios.musica_detector import DetectorMusica, leer_config, normalizar_nombre_app

_log = logging.getLogger("lune.baile")

BAILE_MANUAL = "manual"
PULSO_MS = 500                  # ≤ 2 Hz hacia la asistente y las páginas
CONF_MIN = 0.3                  # pulso del detector que se da por bueno
VIGENCIA_PULSO_S = 12.0         # un pulso bueno se sigue extrapolando este tiempo


class ControlBaile(QObject):
    """Controlador del baile (ver la cabecera del módulo)."""

    estado_cambio = pyqtSignal(str)
    pulso = pyqtSignal(str)
    apps_cambio = pyqtSignal(str)

    # Del hilo del detector al de Qt (conexión automática → en cola).
    _musica_hilo = pyqtSignal(bool, str)
    _pulso_hilo = pyqtSignal(object)
    _sesiones_hilo = pyqtSignal(object)

    def __init__(self, escritorio: Any, config: Any, *, detector: Any = None,
                 en_ui: Optional[Callable] = None, reloj: Callable[[], float] = time.monotonic,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self._detector = detector
        self._en_ui = en_ui
        self._reloj = reloj
        self._asistente: Any = None
        self._iniciado = False
        self._bailando = False
        self._origen = ""
        self._opciones: Dict[str, Any] = {}
        self._musica = False
        self._app = ""
        self._pausado = False                  # pausado hasta que la música se calle
        self._pulso_det: Optional[Pulso] = None     # el último del detector
        self._pulso_ref: Optional[Pulso] = None     # el último bueno (confianza ≥ CONF_MIN)
        self._metro: Callable[[float], Pulso] = metronomo(120.0, reloj())
        self._ultimo_pulso: Optional[Pulso] = None
        self._apps: List[str] = []
        self._ultimo_estado = ""
        self.ultimo_motivo = ""
        self._t_fin = QTimer(self)
        self._t_fin.setSingleShot(True)
        self._t_fin.timeout.connect(self._fin_manual)
        self._t_pulso = QTimer(self)
        self._t_pulso.setInterval(PULSO_MS)
        self._t_pulso.timeout.connect(self._tic_pulso)
        self._musica_hilo.connect(self._on_musica)
        self._pulso_hilo.connect(self._on_pulso)
        self._sesiones_hilo.connect(self._on_sesiones)
        self._bus_conectado = False
        self._empezando = False                # dentro de bailar(): el bus avisa antes de _bailando

    # ── Acceso a lo compartido ───────────────────────────────────────────────────
    def _bus(self) -> Any:
        return getattr(self.escritorio, "estado", None)

    def _estado_bus(self) -> Any:
        bus = self._bus()
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _dormida(self) -> bool:
        est = self._estado_bus()
        if est is not None and getattr(est, "durmiendo", False):
            return True
        v = getattr(self._asistente, "durmiendo", None)
        return v is True

    def _en_juego(self) -> bool:
        est = self._estado_bus()
        return bool(est is not None and getattr(est, "juego", False))

    def _prioridad(self) -> Any:
        return getattr(self.escritorio, "prioridad", None)

    def _auto(self) -> bool:
        return leer_config(self.config)["auto"]

    @property
    def detector(self) -> Any:
        return self._detector

    @property
    def bailando(self) -> bool:
        return self._bailando

    # ── Ciclo de vida (contrato de ServiciosEscritorio) ─────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        if self._detector is None:
            self._detector = DetectorMusica(self.config, en_juego=self._en_juego)
        d = self._detector
        d.on_cambio = self._desde_hilo_musica
        d.on_pulso = self._desde_hilo_pulso
        d.on_sesiones = self._desde_hilo_sesiones
        try:
            d.iniciar()
        except Exception:
            _log.exception("baile: no pude arrancar el detector de música")
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and not self._bus_conectado:
            try:
                senal.connect(self._on_bus)
                self._bus_conectado = True
            except (TypeError, RuntimeError):
                pass

    def detener(self) -> None:
        if not self._iniciado:
            return
        self._iniciado = False
        if self._bailando:
            self.parar(silenciar_auto=False)
        d = self._detector
        if d is not None:
            d.on_cambio = d.on_pulso = d.on_sesiones = None
            try:
                d.detener()
            except Exception:
                _log.exception("baile: no pude parar el detector")
        if self._bus_conectado:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._bus_conectado = False
        self._musica = False
        self._app = ""
        self._pausado = False
        self._emitir_estado()

    def set_asistente(self, v: Any) -> None:
        self._asistente = v
        if v is not None and self._bailando:
            self._asistente_bailar(True)
            self._enviar_pulso(self._pulso_actual(self._reloj()))

    def ceder(self, c: Any) -> None:
        """La tabla le quita el baile (grande, alarma, juego…): fuera lo visual."""
        if not self._bailando:
            return
        self._apagar_visual()
        self._emitir_estado()

    def reanudar(self, c: Any) -> None:
        """Acabó lo que la interrumpió (la tabla ya volvió a marcar `baile`)."""
        if self._bailando:
            return
        if self._iniciado and self._musica and self._auto() and not self._pausado and not self._dormida():
            self._encender_visual("auto")
            valor = getattr(c, "valor", None)
            if valor != BAILE_MUSICA:
                self._actualizar_bus(bailando=BAILE_MUSICA)
            self._emitir_estado()
            return
        pr = self._prioridad()
        if pr is not None:
            try:
                pr.terminar("baile")                   # sin música: se suelta la actividad
            except Exception:
                _log.exception("baile: no pude soltar la actividad")

    def recargar_config(self) -> None:
        if self._bailando and self._origen == "auto" and not self._auto():
            self.parar(silenciar_auto=False)
        if self._bailando:
            self._opciones = nb.opciones_pagina(self.config, self._opciones.get("estilo"))
            self._asistente_bailar(True)
        d = self._detector
        if d is not None and self._iniciado:
            try:
                d.pedir_sondeo()
            except Exception:
                pass
        self._intentar_auto()
        self._emitir_estado()

    # ── Órdenes ──────────────────────────────────────────────────────────────────
    def bailar(self, segundos: Optional[int] = None, *, origen: str = "manual") -> bool:
        """Empieza a bailar. `origen` "manual" (N s; sin música, metrónomo) o "auto"."""
        origen = "auto" if origen == "auto" else "manual"
        if self._bailando:
            if origen == "manual":
                self._armar_fin(segundos)
                if self._origen != "manual":
                    self._origen = "manual"
                    self._forzar(True)
                    self._emitir_estado()
            return True
        if origen == "auto" and self._dormida():
            self.ultimo_motivo = "durmiendo"
            return False
        pr = self._prioridad()
        if pr is not None:
            # prioridad.iniciar avisa al bus y estado_cambio llega AQUÍ MISMO a _on_bus:
            # sin la marca, con música, _intentar_auto empezaría otro baile (otro estilo)
            # antes de que este marque _bailando.
            self._empezando = True
            try:
                r = pr.iniciar("baile", BAILE_MUSICA if origen == "auto" else BAILE_MANUAL)
            finally:
                self._empezando = False
            if not r:
                self.ultimo_motivo = str(getattr(r, "motivo", "") or "")
                self._emitir_estado()
                return False
        self.ultimo_motivo = ""
        if origen == "manual":
            self._pausado = False
            m = self._asistente
            if m is not None and callable(getattr(m, "despertar", None)):
                try:
                    m.despertar()                      # se lo han pedido: se despierta
                except Exception:
                    pass
        self._opciones = nb.opciones_pagina(self.config)
        self._encender_visual(origen)
        if origen == "manual":
            self._armar_fin(segundos)
        self._emitir_estado()
        return True

    def parar(self, *, silenciar_auto: bool = True) -> bool:
        """Deja de bailar. `silenciar_auto`: no vuelve a bailar sola hasta que la
        música se calle. True si estaba bailando."""
        if not self._bailando:
            if silenciar_auto and self._musica and not self._pausado:
                self._silenciar()
                self._emitir_estado()
            return False
        self._apagar_visual()
        if silenciar_auto and self._musica:
            self._silenciar()
        pr = self._prioridad()
        if pr is not None:
            try:
                pr.terminar("baile")
            except Exception:
                _log.exception("baile: no pude terminar la actividad")
        self._emitir_estado()
        return True

    def pausa(self) -> bool:
        """Acción `baile_pausa`: bailando, para hasta que la música se calle; en
        pausa, lo deshace (vuelve a bailar si la música sigue)."""
        if self._bailando:
            return self.parar(silenciar_auto=True)
        if self._pausado:
            self._pausado = False
            d = self._detector
            if d is not None:
                try:
                    d.reanudar_auto()
                except Exception:
                    pass
            self._intentar_auto()
            self._emitir_estado()
            return True
        return False

    # ── Consultas ────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        p = self._ultimo_pulso or self._pulso_det
        d = self._detector
        return {
            "bailando": self._bailando,
            "origen": self._origen if self._bailando else "",
            "musica": self._musica,
            "app": self._app,
            "estilo": self._opciones.get("estilo", "") if self._bailando else "",
            "bpm": round(float(p.bpm), 1) if (p is not None and self._bailando) else None,
            "energia": round(float(p.energia), 3) if (p is not None and self._bailando) else 0.0,
            "auto": self._auto(),
            "pausado_hasta_silencio": self._pausado,
            "disponible": getattr(d, "disponible", None) if d is not None else None,
        }

    def apps_sonando(self, refrescar: bool = True) -> List[str]:
        """Las apps que sonaban en el último sondeo; `refrescar` pide otro (en su hilo)."""
        if refrescar and self._detector is not None and self._iniciado:
            try:
                self._detector.pedir_sondeo()
            except Exception:
                pass
        return list(self._apps)

    def _apps_config(self) -> List[str]:
        return list(leer_config(self.config)["apps"])

    def permitir_app(self, n: str) -> List[str]:
        """Añade una app a `baile.apps` (normalizada, sin repetir). Devuelve la lista."""
        nombre = normalizar_nombre_app(n)
        apps = self._apps_config()
        if nombre and nombre.lower() not in {a.lower() for a in apps}:
            apps.append(nombre)
            self._guardar_apps(apps)
        return apps

    def quitar_app(self, n: str) -> List[str]:
        """Quita una app de `baile.apps`. Devuelve la lista."""
        nombre = normalizar_nombre_app(n)
        apps = self._apps_config()
        if nombre:
            nuevas = [a for a in apps if a.lower() != nombre.lower()]
            if len(nuevas) != len(apps):
                apps = nuevas
                self._guardar_apps(apps)
        return apps

    def _guardar_apps(self, apps: List[str]) -> None:
        if self.config is not None:
            try:
                self.config.set("baile", "apps", list(apps))
            except Exception:
                _log.exception("baile: no pude guardar las apps")
        if self._detector is not None and self._iniciado:
            try:
                self._detector.pedir_sondeo()
            except Exception:
                pass

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["baile"] = self
        # El reproductor de bailes (corte 9, ui/mmd_qt.ControlMMD), si está montado:
        # «bailar {cancion}» busca en tus bailes y «parar_baile» lo para primero.
        obtener = getattr(self.escritorio, "obtener", None)
        if callable(obtener):
            try:
                mmd = obtener("mmd")
            except Exception:
                mmd = None
            if mmd is not None:
                base["mmd"] = mmd
        if self._en_ui is not None:
            base["en_ui"] = self._en_ui
        return base

    def herramientas(self) -> dict:
        """{nombre: handler(args, ctx)} de `asistente_bailar` y `parar_baile` (con
        ctx["mmd"] si el reproductor de bailes está montado)."""
        return {
            "asistente_bailar": lambda args=None, ctx=None: nb.herramienta_bailar(args, self._ctx(ctx)),
            "parar_baile": lambda args=None, ctx=None: nb.herramienta_parar(args, self._ctx(ctx)),
        }

    # ── Del detector (hilo propio) al hilo de Qt ─────────────────────────────────
    def _desde_hilo_musica(self, activa: bool, app: str) -> None:
        try:
            self._musica_hilo.emit(bool(activa), str(app or ""))
        except RuntimeError:
            pass                                       # el QObject ya no existe

    def _desde_hilo_pulso(self, p: Pulso) -> None:
        try:
            self._pulso_hilo.emit(p)
        except RuntimeError:
            pass

    def _desde_hilo_sesiones(self, apps: list) -> None:
        try:
            self._sesiones_hilo.emit(list(apps))
        except RuntimeError:
            pass

    def _on_musica(self, activa: bool, app: str) -> None:
        if not self._iniciado:
            return
        self._musica = bool(activa)
        self._app = str(app or "") if activa else ""
        if not activa:
            self._pausado = False                      # la música se calló: fin de la pausa
            self._pulso_ref = None
            if self._bailando and self._origen == "auto":
                self.parar(silenciar_auto=False)
                return
            if not self._bailando:
                pr = self._prioridad()
                if pr is not None:
                    try:
                        pr.olvidar("baile")            # nada que reanudar sin música
                    except Exception:
                        pass
            self._emitir_estado()
            return
        self._intentar_auto()
        self._emitir_estado()

    def _on_pulso(self, p: Any) -> None:
        if not isinstance(p, Pulso):
            return
        self._pulso_det = p
        if p.confianza >= CONF_MIN:
            self._pulso_ref = p

    def _on_sesiones(self, apps: Any) -> None:
        lista = [str(a) for a in (apps or [])]
        if lista != self._apps:
            self._apps = lista
            self.apps_cambio.emit(json.dumps(lista, ensure_ascii=False))

    def _on_bus(self, estado: Any = None, cambios: Any = None) -> None:
        """Cambió el estado de la asistente: ¿ahora sí se puede bailar con la música?"""
        if self._musica and not self._bailando:
            self._intentar_auto()

    # ── Internos ─────────────────────────────────────────────────────────────────
    def _intentar_auto(self) -> None:
        if self._empezando or not (self._iniciado and self._musica and not self._bailando and not self._pausado):
            return
        if not self._auto() or self._dormida():
            return
        pr = self._prioridad()
        if pr is not None:
            try:
                if not pr.puede("baile"):
                    return
            except Exception:
                return
        self.bailar(origen="auto")

    def _encender_visual(self, origen: str) -> None:
        self._bailando = True
        self._origen = origen
        if not self._opciones:
            self._opciones = nb.opciones_pagina(self.config)
        t = self._reloj()
        self._metro = metronomo(self._pulso_ref.bpm if self._pulso_ref else 120.0, t)
        self._forzar(origen == "manual")
        self._asistente_bailar(True)
        self._t_pulso.start()
        self._tic_pulso()

    def _apagar_visual(self) -> None:
        self._t_fin.stop()
        self._t_pulso.stop()
        self._forzar(False)
        self._bailando = False
        self._origen = ""
        self._asistente_bailar(False)

    def _forzar(self, on: bool) -> None:
        d = self._detector
        if d is not None:
            try:
                d.forzar_pulso(bool(on))
            except Exception:
                pass

    def _silenciar(self) -> None:
        self._pausado = True
        d = self._detector
        if d is not None:
            try:
                d.silenciar_hasta_silencio()
            except Exception:
                pass

    def _armar_fin(self, segundos: Optional[int]) -> None:
        self._t_fin.start(nb.segundos_validos(segundos) * 1000)

    def _fin_manual(self) -> None:
        """Acabó el baile a mano: si suena música permitida, sigue bailando con ella."""
        if not self._bailando:
            return
        if self._musica and self._auto() and not self._pausado:
            self._origen = "auto"
            self._forzar(False)
            self._actualizar_bus(bailando=BAILE_MUSICA)
            self._emitir_estado()
            return
        self.parar(silenciar_auto=False)

    def _actualizar_bus(self, **campos) -> None:
        bus = self._bus()
        if bus is not None:
            try:
                bus.actualizar(**campos)
            except Exception:
                pass

    def _asistente_bailar(self, on: bool) -> None:
        m = self._asistente
        f = getattr(m, "bailar", None) if m is not None else None
        if not callable(f):
            return
        try:
            if on:
                f(True, dict(self._opciones))
            else:
                f(False)
        except Exception:
            _log.exception("baile: la asistente no pudo %s", "bailar" if on else "parar")

    def _pulso_actual(self, t: float) -> Pulso:
        """El pulso en `t`: el último bueno del detector extrapolado o el metrónomo."""
        ref = self._pulso_ref
        if ref is not None and t - ref.t <= VIGENCIA_PULSO_S:
            det = self._pulso_det
            energia = det.energia if det is not None and t - det.t <= 2.0 else ref.energia
            return Pulso(ref.bpm, ref.fase_en(t), energia, ref.confianza, t)
        return self._metro(t)

    def _tic_pulso(self) -> None:
        if not self._bailando:
            self._t_pulso.stop()
            return
        self._enviar_pulso(self._pulso_actual(self._reloj()))

    def _enviar_pulso(self, p: Pulso) -> None:
        self._ultimo_pulso = p
        m = self._asistente
        f = getattr(m, "pulso", None) if m is not None else None
        if callable(f):
            try:
                f(float(p.bpm), float(p.fase), float(p.energia))
            except Exception:
                _log.debug("baile: la asistente no aceptó el pulso", exc_info=True)
        self.pulso.emit(json.dumps(p.a_dict()))

    def _emitir_estado(self) -> None:
        txt = json.dumps(self.estado(), ensure_ascii=False, sort_keys=True)
        if txt != self._ultimo_estado:
            self._ultimo_estado = txt
            self.estado_cambio.emit(txt)


__all__ = ("ControlBaile", "BAILE_MANUAL")
