"""
ui/modo_juego_qt.py — El modo juego en la app: detector cada 2 s y el plan aplicado.

`ControlModoJuego` es un controlador de `ServiciosEscritorio` (ui/escritorio.py):
lo registra `montar_escritorio` (ui/montaje_escritorio.py) y recibe
`set_asistente`, `iniciar` y `detener` como los demás. Cada `intervalo_ms` pide
una lectura a `servicios.modo_juego.DetectorJuego` (reglas + histéresis) y al
cambiar entra o sale del modo juego.

AL ENTRAR (en este orden; al salir se deshace al revés):
  1. `escritorio.prioridad.iniciar("juego")` → BusEstado.juego = True y ceden la
     pantalla grande, sentada, MMD… (tabla de nucleo/estado_asistente.py).
  2. `asistente.aplicar_plan_juego(plan)`: ocultar / al fondo / nada, FPS, sin
     comentarios ni capturas. La asistente solo vuelve a mostrarse si la ocultó
     el modo juego (si el usuario la saca a mano durante la partida, gana él).
  3. `voice.silenciar(True)` si `juego.silenciar` (y solo si no lo estaba ya).
  4. `aplicar_prioridad(True)`: BELOW_NORMAL a Lune y sus QtWebEngineProcess.
  5. Suelta los modelos (11.3): Whisper si no dictas ni hay llamada
     (servicios/voz_entrada.soltar_modelo) y, si el chat usa Ollama EN ESTE PC y el bot
     de Minecraft no piensa mientras juegas (minecraft.pensar_en_juego con el bot vivo),
     `ai.descargar_modelo()` (keep_alive 0) en un hilo: es lo que más GPU le quita al
     juego. No se deshace al salir: el siguiente mensaje lo vuelve a cargar.
  6. `recortar()` 1.5 s después, en un hilo (gc.collect antes, en este hilo).
  7. log «[juego] entra: <motivo>» y `cambio(True, motivo)`: quien monta los
     servicios pausa ahí los atajos y el aburrimiento.
AL SALIR: lo anterior al revés y `prioridad.terminar("juego")` (reanuda lo que
cedió), log «[juego] sale» y `cambio(False, "")`. `detener()` también sale.

Además lleva el recorte periódico de `sistema.recorte_ram_auto`
(servicios.recorte_ram.ProgramadorRecorte), que se mira en el mismo tic.
"""
from __future__ import annotations

import gc
import logging
import threading
from typing import Any, Callable, List, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from servicios import modo_juego as mj
from servicios import recorte_ram as rr
from servicios import win_pantalla as wp

_log = logging.getLogger("lune.juego")

RETRASO_RECORTE_MS = 1500
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def proveedor_activo(escritorio: Any) -> str:
    """El proveedor del chat de la ventana ('ollama', 'openrouter', 'compat'; "" si no
    se sabe): el que eligió la página (web: bridge._provider_web) o el de la ventana
    nativa (current_provider, la dueña de ServiciosEscritorio)."""
    puente = getattr(escritorio, "bridge", None)
    p = getattr(puente, "_provider_web", None) if puente is not None else None
    if p:
        p = str(p).strip().lower()
        return "ollama" if p in ("local", "ollama") else ("compat" if p == "compat" else "openrouter")
    dueno = None
    try:
        f = getattr(escritorio, "parent", None)
        dueno = f() if callable(f) else None
    except Exception:
        dueno = None
    p = getattr(dueno, "current_provider", None) if dueno is not None else None
    return str(p or "")


def ollama_es_local(url: Optional[str] = None) -> bool:
    """¿Ollama corre en este PC? (con uno en otro equipo, descargarlo no libera nada aquí)."""
    if url is None:
        try:
            from nucleo import datos
            url = datos.ollama_url()
        except Exception:
            return False
    try:
        from urllib.parse import urlparse
        host = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return host in HOSTS_LOCALES or host.startswith("127.")


def _log_info(msg: str) -> None:
    try:
        from nucleo.utils import log_info
        log_info(msg)
    except Exception:
        _log.info(msg)


def _llamar(obj: Any, metodo: str, *args) -> Any:
    f = getattr(obj, metodo, None)
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("modo juego: %s.%s falló", type(obj).__name__, metodo)
        return None


class ControlModoJuego(QObject):
    """Detector de juegos + plan del modo juego sobre la asistente, la voz y el proceso."""

    cambio = pyqtSignal(bool, str)          # (activo, motivo)

    def __init__(self, escritorio, config, *, voice=None, detector=None,
                 recortar: Callable[..., Any] = rr.recortar,
                 prioridad: Callable[[bool], Any] = mj.aplicar_prioridad,
                 intervalo_ms: int = 2000, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.voice = voice
        self._recortar = recortar
        self._prioridad = prioridad
        self._pids = None
        if detector is None:
            self._pids = wp.PidsLune()
            detector = mj.DetectorJuego(config, pids=self._pids,
                                        lune_a_pantalla_completa=self._lune_a_pantalla_completa)
        self.detector = detector
        self._asistente = getattr(escritorio, "asistente", None)
        self._activo = False
        self._motivo = ""
        self._plan: Optional[mj.PlanJuego] = None
        self._deshacer: List[Callable[[], Any]] = []
        self._iniciado = False
        self._recortando = False
        self._programador = rr.ProgramadorRecorte()

        self._timer = QTimer(self)
        self._timer.setInterval(max(50, int(intervalo_ms)))
        self._timer.timeout.connect(self._tic)
        self._timer_recorte = QTimer(self)
        self._timer_recorte.setSingleShot(True)
        self._timer_recorte.timeout.connect(self._recortar_ahora)

    # ── Contrato de controlador (ui/escritorio.py) ─────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        self.recargar_config()
        self._timer.start()

    def detener(self) -> None:
        self._iniciado = False
        self._timer.stop()
        self._timer_recorte.stop()
        self._programador.activar(False)
        if self._activo:
            self._salir()

    def set_asistente(self, v) -> None:
        """La asistente cambió. Si hay partida, la nueva recibe el plan (si se crea
        oculta y el usuario la muestra, gana él). La vieja se suelta tal cual."""
        if v is self._asistente:
            return
        self._asistente = v
        if self._activo and v is not None and self._plan is not None:
            _llamar(v, "aplicar_plan_juego", self._plan)

    # ── API ─────────────────────────────────────────────────────────────────────
    def forzar(self, on: Optional[bool]) -> None:
        """True/False: modo juego a mano (manda sobre la detección); None: detectar.
        Se aplica ya, sin esperar al siguiente tic (también antes de `iniciar`: el
        forzado queda en el detector y el tic lo sigue respetando)."""
        self.detector.forzar(on)
        self._evaluar()

    @property
    def forzado(self) -> Optional[bool]:
        """None = detectar; True/False = a mano (bandeja, radial, atajo, /menu). El
        cambio de interfaz lo lleva a la ventana nueva (estado_para_cambio)."""
        try:
            if hasattr(self.detector, "forzado"):
                f = self.detector.forzado
            else:
                f = self.estado().get("forzado")
        except Exception:
            return None
        return None if f is None else bool(f)

    def activo(self) -> bool:
        return self._activo

    def estado(self) -> dict:
        try:
            est = dict(self.detector.estado())
        except Exception:
            est = {}
        est["activo"] = self._activo
        est["motivo"] = self._motivo
        est.setdefault("forzado", None)
        est.setdefault("exe", "")
        return est

    def recargar_config(self) -> None:
        """Ajustes cambiados (juego.*, sistema.recorte_ram_auto): el detector lee la
        config en cada lectura; aquí se aplica al momento lo que no espera al tic."""
        self._programador.activar(self._cfg("sistema", "recorte_ram_auto", False) and self._iniciado)
        if self._activo and not self._detectando():
            self._evaluar()                          # detector apagado: sale ya
        elif self._activo:
            nuevo = mj.plan(self.config)
            if nuevo != self._plan:                  # otro plan con la partida en marcha
                self._plan = nuevo
                if self._asistente is not None:
                    _llamar(self._asistente, "aplicar_plan_juego", nuevo)

    # ── Tic ─────────────────────────────────────────────────────────────────────
    def _tic(self) -> None:
        if self._detectando() or self._activo:       # apagado en partida: una lectura para salir
            self._evaluar()
        if self._programador.activo and not self._activo:
            if self._programador.toca(self._animando()):
                self._recortar_ahora()

    def _detectando(self) -> bool:
        f = getattr(self.detector, "detectando", None)
        if callable(f):
            try:
                return bool(f())
            except Exception:
                return True
        return True

    def _evaluar(self) -> None:
        try:
            cambio, activo, motivo = self.detector.evaluar()
        except Exception:
            _log.exception("modo juego: la lectura del detector falló")
            return
        if activo and not self._activo:
            self._entrar(motivo)
        elif not activo and self._activo:
            self._salir()
        elif activo:
            self._motivo = motivo or self._motivo

    # ── Entrar y salir ──────────────────────────────────────────────────────────
    def _entrar(self, motivo: str) -> None:
        self._activo = True
        self._motivo = motivo or ""
        self._deshacer = []
        plan = self._plan = mj.plan(self.config)
        prioridad = getattr(self.escritorio, "prioridad", None)
        if prioridad is not None:
            prioridad.iniciar("juego")
            self._deshacer.append(lambda: prioridad.terminar("juego"))
        else:
            _llamar(getattr(self.escritorio, "estado", None), "actualizar", juego=True)
        if self._asistente is not None:
            _llamar(self._asistente, "aplicar_plan_juego", plan)
        self._deshacer.append(self._devolver_asistente)
        voz = self.voice
        if plan.silenciar_voz and voz is not None and not getattr(voz, "silenciada", False):
            _llamar(voz, "silenciar", True)
            self._deshacer.append(lambda: _llamar(voz, "silenciar", False))
        if plan.prioridad_baja:
            self._llamar_prioridad(True)
            self._deshacer.append(lambda: self._llamar_prioridad(False))
        self._soltar_modelos()
        if plan.recortar_ram:
            self._timer_recorte.start(RETRASO_RECORTE_MS)
            self._deshacer.append(self._timer_recorte.stop)
        _log_info(f"[juego] entra: {self._motivo or '?'}")
        self.cambio.emit(True, self._motivo)

    def _salir(self) -> None:
        self._activo = False
        self._motivo = ""
        pasos, self._deshacer = self._deshacer, []
        for paso in reversed(pasos):
            try:
                paso()
            except Exception:
                _log.exception("modo juego: no pude deshacer un paso")
        self._plan = None
        _log_info("[juego] sale")
        self.cambio.emit(False, "")

    def _devolver_asistente(self) -> None:
        if self._asistente is not None:
            _llamar(self._asistente, "aplicar_plan_juego", None)

    def _llamar_prioridad(self, baja: bool) -> None:
        try:
            self._prioridad(baja)
        except Exception:
            _log.exception("modo juego: no pude cambiar la prioridad")

    # ── Modelos: Whisper y Ollama fuera al entrar ──────────────────────────────
    def _soltar_modelos(self) -> None:
        try:
            rr.soltar_whisper()                      # no hace nada con un dictado o una llamada
        except Exception:
            _log.exception("modo juego: no pude soltar el modelo de dictado")
        if not self._ollama_descargable():
            return
        ai = getattr(self.escritorio, "ai", None)

        def descargar():
            try:
                if ai.descargar_modelo():
                    _log_info("[juego] modelo de Ollama descargado de la memoria")
            except Exception:
                _log.exception("modo juego: no pude descargar el modelo de Ollama")

        threading.Thread(target=descargar, name="lune-ollama-descargar", daemon=True).start()

    def _ollama_descargable(self) -> bool:
        """¿Descargar el modelo de Ollama? Solo si el chat lo usa, corre en este PC y el
        bot de Minecraft no lo está usando (pensar_en_juego con el bot vivo)."""
        ai = getattr(self.escritorio, "ai", None)
        if ai is None or not callable(getattr(ai, "descargar_modelo", None)):
            return False
        if proveedor_activo(self.escritorio) != "ollama" or not ollama_es_local():
            return False
        return not self._minecraft_piensa()

    def _minecraft_piensa(self) -> bool:
        if not bool(self._cfg("minecraft", "pensar_en_juego", False)):
            return False
        obtener = getattr(self.escritorio, "obtener", None)
        try:
            mc = obtener("minecraft") if callable(obtener) else None
        except Exception:
            return True                              # no se sabe: mejor no quitárselo
        if mc is None:
            return False                             # sin bot montado, nadie piensa
        vivo = getattr(mc, "_bot_vivo", None)
        try:
            if callable(vivo):
                return bool(vivo())
            return bool(getattr(getattr(mc, "proceso", None), "vivo", False))
        except Exception:
            return True

    # ── Recorte de RAM ──────────────────────────────────────────────────────────
    def _recortar_ahora(self) -> None:
        """gc.collect aquí (hilo de Qt) y EmptyWorkingSet en un hilo aparte."""
        if self._recortando:
            return
        self._recortando = True
        try:
            gc.collect()
        except Exception:
            pass

        def trabajo():
            try:
                r = self._recortar()
                if isinstance(r, tuple) and len(r) == 2:
                    _log_info(f"[juego] RAM: {r[0]:.0f} → {r[1]:.0f} MB")
            except Exception:
                _log.exception("modo juego: el recorte de RAM falló")
            finally:
                self._recortando = False

        threading.Thread(target=trabajo, name="lune-recorte-ram", daemon=True).start()

    # ── Ayudas ──────────────────────────────────────────────────────────────────
    def _estado_actual(self):
        bus = getattr(self.escritorio, "estado", None)
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _lune_a_pantalla_completa(self) -> bool:
        est = self._estado_actual()
        return bool(est is not None and (est.grande or est.salvapantallas))

    def _animando(self) -> bool:
        est = self._estado_actual()
        if est is None:
            return False
        return bool(est.arrastrando or est.bailando or est.grande or est.salvapantallas
                    or est.comiendo or est.hablando)

    def _cfg(self, seccion: str, clave: str, defecto):
        try:
            return self.config.get(seccion, clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto
