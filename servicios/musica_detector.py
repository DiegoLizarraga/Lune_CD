"""
servicios/musica_detector.py — ¿Suena música en el PC? Y, si suena, su pulso.

Como Mate-Engine (AvatarAnimatorController.cs): cada 2 s se miran las sesiones
de audio y, si una app PERMITIDA (baile.apps: «empieza por», sin mayúsculas ni
«.exe») suena por encima de `baile.umbral`, Lune baila. Diferencias:

- Se miran TODAS las salidas de audio activas, no solo la de por defecto
  (crítica c.21), y nunca las de la propia Lune (`PidsLune`: su proceso, donde
  suenan la voz y el mezclador, y sus hijos QtWebEngine): su voz no la hace bailar.
- Histéresis: entra con 2 lecturas seguidas por encima del umbral y sale tras
  6 s por debajo de 0.25·umbral (una pausa entre canciones no la para).
- Mientras hay música, un bucle rápido (50 Hz) lee UNA llamada COM (el medidor
  de esa sesión, en caché) y alimenta `nucleo.pulso.SeguidorPulso`; el pulso se
  entrega como mucho 2 veces por segundo.
- Con un juego delante (`en_juego()`) no se llama a COM: ni enumera ni mide.
- `baile.auto = False` apaga el sondeo automático (solo se sondea si se pide).
- `forzar_pulso(True)` (baile a mano): se sigue el pulso de la sesión más fuerte
  que no sea de Lune, aunque su app no esté permitida.
- `silenciar_hasta_silencio()` (baile_pausa): no vuelve a avisar de música hasta
  que la que suena se calle.

Todo lo de COM ocurre en el hilo del detector (servicios/audio_sesiones.py), salvo
el primer `import comtypes`, que se hace al construirlo (en el hilo principal). Los
avisos (`on_cambio`, `on_pulso`, `on_sesiones`) llegan en ESE hilo: quien los
use en Qt tiene que pasarlos al hilo de Qt (ui/baile_qt.py lo hace con señales).
`sondear(t)` y `rapido(t)` son los pasos sueltos, para los tests. Sin Qt.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from typing import Any, Callable, Iterable, List, Optional, Sequence, Set, Tuple

from nucleo.pulso import Pulso, SeguidorPulso

_log = logging.getLogger("lune.musica")

APPS_DEFECTO = ("Spotify", "MusicBee", "foobar2000", "vlc", "AppleMusic")
UMBRAL_DEFECTO = 0.05        # D1 (como DEFAULT_CONFIG baile.umbral)
UMBRAL_MIN, UMBRAL_MAX = 0.005, 1.0
UMBRAL_SONANDO = 0.01          # «suena ahora» (lista de apps de la interfaz)
UMBRAL_FORZADO = 0.01          # baile a mano: la sesión más fuerte por encima de esto
MAX_APPS = 40

_RE_APP = re.compile(r"[\w .+\-()&']{1,60}")


# ── Apps ─────────────────────────────────────────────────────────────────────────
def _base(nombre: Any) -> str:
    """«Spotify.EXE» → «spotify» (para comparar)."""
    if not isinstance(nombre, str):
        return ""
    n = nombre.strip().lower()
    return n[:-4].strip() if n.endswith(".exe") else n


def normalizar_nombre_app(nombre: Any) -> Optional[str]:
    """Nombre de app para `baile.apps`: sin comillas, ruta ni «.exe», con su
    mayúscula («C:\\\\…\\\\Spotify.exe» → «Spotify»). None si no vale."""
    if not isinstance(nombre, str):
        return None
    n = nombre.strip().strip('"\'').strip()
    n = re.split(r"[\\/]", n)[-1].strip()
    if n.lower().endswith(".exe"):
        n = n[:-4].strip()
    if not n or not _RE_APP.fullmatch(n) or not n.strip(". "):
        return None
    return n


def coincide_app(exe: str, apps: Iterable[str]) -> Optional[str]:
    """La app permitida con la que coincide `exe` («empieza por», sin mayúsculas
    ni «.exe», como Mate-Engine), o None."""
    e = _base(exe)
    if not e:
        return None
    for a in apps or ():
        b = _base(a)
        if b and e.startswith(b):
            return a
    return None


def elegir(sesiones: Sequence[Any], apps: Iterable[str], excluir: Set[int], umbral: float) -> Optional[Any]:
    """La sesión más fuerte (≥ umbral) de una app permitida que no sea de Lune.

    Si una app tiene varias sesiones (Spotify), gana la más fuerte."""
    apps = list(apps or ())
    mejor = None
    for s in sesiones:
        pid = int(getattr(s, "pid", 0) or 0)
        if pid <= 0 or pid in excluir:
            continue
        if not coincide_app(getattr(s, "exe", ""), apps):
            continue
        if s.pico < umbral:
            continue
        if mejor is None or s.pico > mejor.pico:
            mejor = s
    return mejor


def leer_config(config: Any) -> dict:
    """{auto, umbral, apps} de la sección `baile` (valores por defecto si falta o no vale)."""
    def get(clave, defecto):
        try:
            return config.get("baile", clave, defecto) if config is not None else defecto
        except Exception:
            return defecto
    try:
        umbral = float(get("umbral", UMBRAL_DEFECTO))
        if not math.isfinite(umbral):
            raise ValueError
    except (TypeError, ValueError):
        umbral = UMBRAL_DEFECTO
    umbral = min(UMBRAL_MAX, max(UMBRAL_MIN, umbral))
    apps = get("apps", list(APPS_DEFECTO))
    if not isinstance(apps, (list, tuple)):
        apps = list(APPS_DEFECTO)
    apps = [a for a in (normalizar_nombre_app(x) for x in apps) if a][:MAX_APPS]
    return {"auto": bool(get("auto", True)), "umbral": umbral, "apps": apps}


def _nombre_de(s: Any, apps: Sequence[str]) -> str:
    """Lo que se enseña: el exe de la sesión («Spotify») o la app permitida."""
    return str(getattr(s, "exe", "") or coincide_app(getattr(s, "exe", ""), apps) or "")


# ── Histéresis ───────────────────────────────────────────────────────────────────
class Histeresis:
    """Entra con ENTRAR lecturas seguidas ≥ umbral; sale tras SALIR_S por debajo
    de FACTOR_SALIDA·umbral."""

    ENTRAR = 2
    SALIR_S = 6.0
    FACTOR_SALIDA = 0.25

    def __init__(self, entrar: int = ENTRAR, salir_s: float = SALIR_S, factor: float = FACTOR_SALIDA):
        self.entrar = max(1, int(entrar))
        self.salir_s = float(salir_s)
        self.factor = float(factor)
        self.reiniciar()

    def reiniciar(self) -> None:
        self.activa = False
        self._seguidas = 0
        self._t_bajo: Optional[float] = None

    def paso(self, pico: float, t: float, umbral: float) -> Tuple[bool, bool]:
        """Una lectura. Devuelve (cambió, activa)."""
        if not self.activa:
            if pico >= umbral:
                self._seguidas += 1
                if self._seguidas >= self.entrar:
                    self.activa = True
                    self._seguidas = 0
                    self._t_bajo = None
                    return True, True
            else:
                self._seguidas = 0
            return False, False
        if pico < self.factor * umbral:
            if self._t_bajo is None:
                self._t_bajo = t
            elif t - self._t_bajo >= self.salir_s:
                self.reiniciar()
                return True, False
        else:
            self._t_bajo = None
        return False, True


# ── Detector ─────────────────────────────────────────────────────────────────────
class DetectorMusica:
    """Sondea las sesiones de audio en su hilo y avisa de la música y de su pulso.

        d = DetectorMusica(config)
        d.on_cambio = lambda activa, app: ...     # en el hilo del detector
        d.on_pulso = lambda pulso: ...            # ≤ PULSO_MAX_HZ
        d.on_sesiones = lambda apps: ...          # ["Spotify", "firefox"] que suenan ahora
        d.iniciar() … d.detener()
    """

    INTERVALO_S = 2.0
    RAPIDO_HZ = 50
    PULSO_MAX_HZ = 2

    def __init__(self, config: Any, *, medidor: Any = None, pids: Any = None,
                 reloj: Callable[[], float] = time.monotonic, en_juego: Callable[[], bool] = lambda: False,
                 dormir: Callable[[float], Any] = time.sleep):
        self.config = config
        self._medidor = medidor
        self._pids = pids
        self._reloj = reloj
        self._en_juego = en_juego
        self._dormir = dormir
        self.on_cambio: Optional[Callable[[bool, str], None]] = None
        self.on_pulso: Optional[Callable[[Pulso], None]] = None
        self.on_sesiones: Optional[Callable[[list], None]] = None
        self._lock = threading.RLock()
        self._hist = Histeresis()
        self._seguidor = SeguidorPulso()
        self._activa = False
        self._app = ""
        self._clave: Optional[str] = None
        self._umbral = UMBRAL_DEFECTO
        self._forzado = False
        self._clave_forzada: Optional[str] = None
        self._silenciado = False
        self._sonando: List[str] = []
        self._pulso: Optional[Pulso] = None
        self._t_pulso = -math.inf
        self._disponible: Optional[bool] = None
        self._abierto = False
        self._hilo: Optional[threading.Thread] = None
        self._parar = threading.Event()
        self._despertar = threading.Event()
        self._pedido = threading.Event()
        if medidor is None:
            # El medidor de verdad (comtypes) se abrirá en el hilo del detector; comtypes
            # se importa YA, en el hilo que construye (el de Qt o el de patata): ver
            # servicios/audio_sesiones.preparar_comtypes.
            try:
                from servicios.audio_sesiones import preparar_comtypes
                preparar_comtypes()
            except Exception:
                _log.debug("musica: no pude preparar comtypes", exc_info=True)

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._parar.clear()
            self._hilo = threading.Thread(target=self._bucle, name="lune-musica", daemon=True)
            self._hilo.start()

    def detener(self, espera_s: float = 2.0) -> None:
        self._parar.set()
        self._despertar.set()
        h = self._hilo
        if h is not None and h is not threading.current_thread():
            h.join(max(0.0, espera_s))
        self._hilo = None
        if h is None:
            self._cerrar()                     # se usó a pasos sueltos (tests)
        with self._lock:
            self._activa = False
            self._app = ""
            self._clave = None
            self._clave_forzada = None
            self._forzado = False
            self._silenciado = False
            self._hist.reiniciar()
            self._seguidor.reiniciar()

    @property
    def disponible(self) -> Optional[bool]:
        """None sin probar; False si no hay medidor (sin comtypes, fuera de Windows)."""
        return self._disponible

    @property
    def activa(self) -> bool:
        return self._activa

    # ── Órdenes (cualquier hilo) ─────────────────────────────────────────────────
    def forzar_pulso(self, on: bool) -> None:
        """Baile a mano: seguir el pulso de la sesión más fuerte que no sea de Lune."""
        with self._lock:
            self._forzado = bool(on)
            if not on:
                self._clave_forzada = None
        if on:
            self._pedido.set()
        self._despertar.set()

    def silenciar_hasta_silencio(self) -> None:
        """No avisar de música hasta que la que suena se calle (baile_pausa)."""
        with self._lock:
            if self._activa:
                self._silenciado = True
        self._despertar.set()

    def reanudar_auto(self) -> None:
        """Deshace `silenciar_hasta_silencio`: si sigue la música, vuelve a avisar."""
        eventos = []
        with self._lock:
            if not self._silenciado:
                return
            self._silenciado = False
            if self._activa:
                eventos.append(("cambio", True, self._app))
        self._emitir(eventos)
        self._despertar.set()

    def pedir_sondeo(self) -> None:
        """Que el hilo sondee cuanto antes (p. ej. para refrescar las apps que suenan)."""
        self._pedido.set()
        self._despertar.set()

    def apps_sonando(self) -> List[str]:
        with self._lock:
            return list(self._sonando)

    def estado(self) -> dict:
        with self._lock:
            p = self._pulso
            return {
                "disponible": self._disponible, "activa": self._activa, "app": self._app,
                "forzado": self._forzado, "silenciado": self._silenciado,
                "auto": leer_config(self.config)["auto"], "sonando": list(self._sonando),
                "bpm": round(p.bpm, 1) if p else None, "energia": round(p.energia, 3) if p else 0.0,
                "confianza": round(p.confianza, 3) if p else 0.0,
            }

    # ── Pasos ────────────────────────────────────────────────────────────────────
    def sondear(self, t: Optional[float] = None) -> Tuple[bool, str]:
        """Sondeo lento: enumera las sesiones y decide si hay música."""
        t = self._reloj() if t is None else float(t)
        eventos: list = []
        with self._lock:
            if self._juego():
                if self._activa:
                    self._desactivar(eventos)
                self._clave_forzada = None
                res = (self._activa, self._app)
            elif not self._abrir():
                res = (False, "")
            else:
                cfg = leer_config(self.config)
                self._umbral = cfg["umbral"]
                excl = self._excluir()
                sesiones = [s for s in self._medir(cfg["umbral"]) if int(s.pid or 0) > 0 and s.pid not in excl]
                sonando = sorted({s.exe for s in sesiones if s.exe and s.pico >= UMBRAL_SONANDO}, key=str.lower)
                if sonando != self._sonando:
                    self._sonando = sonando
                    eventos.append(("sesiones", list(sonando)))
                if cfg["auto"]:
                    self._paso_auto(sesiones, cfg, excl, t, eventos)
                elif self._activa:
                    self._desactivar(eventos)
                if self._silenciado and not self._activa:
                    self._silenciado = False
                if self._forzado:
                    self._elegir_forzada(sesiones)
                res = (self._activa, self._app)
        self._emitir(eventos)
        return res

    def rapido(self, t: Optional[float] = None) -> None:
        """Paso rápido (50 Hz): una lectura del medidor → pulso y salida de la histéresis."""
        t = self._reloj() if t is None else float(t)
        eventos: list = []
        with self._lock:
            if not self._rapido_activo() or self._juego() or not self._abierto:
                return
            if self._activa and self._clave:
                clave = self._clave
            elif self._forzado:
                clave = self._clave_forzada
            else:
                clave = None
            pico = None
            if clave is not None:
                pico = self._medidor.pico(clave)
                if pico is None:                       # la sesión murió: se re-elige al sondear
                    if clave == self._clave:
                        self._clave = None
                    if clave == self._clave_forzada:
                        self._clave_forzada = None
            pico = 0.0 if pico is None else float(pico)
            self._seguidor.alimentar(pico, t)
            if self._activa:
                cambio, activa = self._hist.paso(pico, t, self._umbral)
                if cambio and not activa:
                    self._desactivar(eventos)
            if t - self._t_pulso >= 1.0 / self.PULSO_MAX_HZ - 1e-6:
                self._t_pulso = t
                self._pulso = self._seguidor.estimar(t)
                eventos.append(("pulso", self._pulso))
        self._emitir(eventos)

    # ── Internos ─────────────────────────────────────────────────────────────────
    def _juego(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _abrir(self) -> bool:
        if self._abierto:
            return True
        if self._disponible is False:
            return False
        if self._medidor is None:
            from servicios.audio_sesiones import MedidorSesiones
            self._medidor = MedidorSesiones()
        try:
            self._medidor.abrir()
        except Exception as e:                         # sin comtypes / fuera de Windows
            self._disponible = False
            _log.info("Sin medidor de audio (%s): no hay baile con la música.", e)
            return False
        self._abierto = True
        self._disponible = True
        return True

    def _cerrar(self) -> None:
        with self._lock:
            if not self._abierto:
                return
            self._abierto = False
            try:
                self._medidor.cerrar()
            except Exception:
                _log.debug("musica: no pude cerrar el medidor", exc_info=True)

    def _excluir(self) -> Set[int]:
        p = self._pids
        try:
            if p is None:
                from servicios.win_pantalla import PidsLune
                p = self._pids = PidsLune()
            if hasattr(p, "pids"):
                return {int(x) for x in p.pids()}
            if callable(p):
                return {int(x) for x in p()}
            return {int(x) for x in p}
        except Exception:
            import os
            return {os.getpid()}

    def _medir(self, umbral: float) -> list:
        try:
            try:
                return list(self._medidor.sesiones(umbral_nombre=umbral))
            except TypeError:
                return list(self._medidor.sesiones())
        except Exception:
            _log.debug("musica: no pude leer las sesiones", exc_info=True)
            return []

    def _paso_auto(self, sesiones, cfg, excl, t, eventos) -> None:
        apps, umbral = cfg["apps"], cfg["umbral"]
        if not self._activa:
            s = elegir(sesiones, apps, excl, umbral)
            cambio, activa = self._hist.paso(s.pico if s else 0.0, t, umbral)
            if cambio and activa and s is not None:
                self._activa = True
                self._clave = s.clave
                self._app = _nombre_de(s, apps)
                self._seguidor.reiniciar()
                self._t_pulso = -math.inf
                if not self._silenciado:
                    eventos.append(("cambio", True, self._app))
            elif cambio and activa:
                self._hist.reiniciar()
            return
        s = elegir(sesiones, apps, excl, 0.0)          # la más fuerte de las permitidas
        if s is None:
            self._clave = None
            pico = 0.0
        else:
            pico = s.pico
            if s.clave != self._clave:
                self._clave = s.clave
                app = _nombre_de(s, apps)
                if app != self._app:
                    self._app = app
                    if not self._silenciado:
                        eventos.append(("cambio", True, app))
        cambio, activa = self._hist.paso(pico, t, umbral)
        if cambio and not activa:
            self._desactivar(eventos)

    def _elegir_forzada(self, sesiones) -> None:
        if self._activa and self._clave:
            self._clave_forzada = self._clave
            return
        fuertes = [s for s in sesiones if s.pico >= UMBRAL_FORZADO]
        self._clave_forzada = max(fuertes, key=lambda s: s.pico).clave if fuertes else None

    def _desactivar(self, eventos) -> None:
        app = self._app
        self._activa = False
        self._app = ""
        self._clave = None
        self._silenciado = False
        self._hist.reiniciar()
        eventos.append(("cambio", False, app))

    def _rapido_activo(self) -> bool:
        return bool(self._abierto and ((self._activa and not self._silenciado) or self._forzado))

    def _toca_sondear(self) -> bool:
        with self._lock:
            return bool(self._activa or self._forzado or leer_config(self.config)["auto"])

    def _emitir(self, eventos) -> None:
        for ev in eventos:
            try:
                if ev[0] == "cambio" and self.on_cambio:
                    self.on_cambio(bool(ev[1]), str(ev[2] or ""))
                elif ev[0] == "pulso" and self.on_pulso:
                    self.on_pulso(ev[1])
                elif ev[0] == "sesiones" and self.on_sesiones:
                    self.on_sesiones(ev[1])
            except Exception:
                _log.exception("musica: error en un aviso del detector")

    def _esperar(self, s: float) -> None:
        if self._dormir is time.sleep:
            self._despertar.wait(max(0.0, s))
            self._despertar.clear()
        else:
            self._dormir(max(0.0, s))

    def _bucle(self) -> None:
        proximo = -math.inf
        try:
            while not self._parar.is_set():
                t = self._reloj()
                pedido = self._pedido.is_set()
                if pedido or t >= proximo:
                    self._pedido.clear()
                    if pedido or self._toca_sondear():
                        try:
                            self.sondear(t)
                        except Exception:
                            _log.exception("musica: fallo al sondear")
                    proximo = t + self.INTERVALO_S
                if self._parar.is_set():
                    break
                with self._lock:
                    rapido = self._rapido_activo() and not self._juego()
                if rapido:
                    try:
                        self.rapido(t)
                    except Exception:
                        _log.exception("musica: fallo en el bucle rápido")
                    espera = 1.0 / self.RAPIDO_HZ - (self._reloj() - t)
                else:
                    espera = proximo - self._reloj()
                self._esperar(max(0.001, min(self.INTERVALO_S, espera)))
        finally:
            self._cerrar()


__all__ = (
    "APPS_DEFECTO", "UMBRAL_DEFECTO", "UMBRAL_SONANDO", "normalizar_nombre_app", "coincide_app", "elegir",
    "leer_config", "Histeresis", "DetectorMusica",
)
