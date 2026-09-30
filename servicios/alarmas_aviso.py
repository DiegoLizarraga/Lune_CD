"""
servicios/alarmas_aviso.py — Lo que pasa cuando suena una alarma (sin Qt).

`ControlAviso` lleva una alarma sonando y la cola de las que esperan:

- `disparar(d)`: si no suena nada, empieza (sonido en bucle por el canal
  «alarma» del Mezclador y `on_mostrar(d)`); si ya suena otra, a la cola FIFO
  (como Mate-Engine). False = se encoló.
- Bloqueo de `bloqueo_s` (5 s): durante ese rato `puede_apagar()` es False y ni
  un clic ni una tecla la apagan (el botón de la tarjeta enseña la cuenta atrás).
- `apagar()`: calla, la quita de `sonando` en alarmas.json, dice el texto
  (`on_voz`) y pasa a la siguiente de la cola (`on_mostrar(siguiente)`) o, si no
  queda ninguna, `on_ocultar(d)`.
- `posponer()`: como apagar, pero crea un temporizador «pospuesta» de
  `posponer_min` (en el almacén: sobrevive a un reinicio) y no habla.
- `tick()` (1 Hz): corta la alarma a los `max_sonando_s` (15 min) y dispara las
  pospuestas en memoria si no hay almacén.
- `detener()`: calla y olvida lo de memoria SIN tocar `sonando` del archivo: al
  volver a arrancar (o tras un cambio de interfaz) se recupera.

El sonido: WAV `ui_web/assets/sfx/alarma_1..3.wav` (uno al azar o el elegido),
siempre por el Mezclador (nunca por la página ni por pygame.mixer.music, que es
de la voz). Abrir el dispositivo puede tardar: se hace en un hilo (`lanzar`).
Suena también en modo juego (decisión D3): el modo juego solo quita lo visual.

`elegir_visual()` decide cómo se enseña: `discreto` (solo sonido y aviso de
bandeja: hay un juego), `grande` (pantalla grande: asistente o VentanaReloj) o
`burbuja` (burbuja de la asistente + tarjeta DialogoAlarma).
"""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, List, Optional, Tuple

from nucleo.alarmas import Disparo

_log = logging.getLogger("lune.alarmas")

RAIZ = Path(__file__).resolve().parent.parent
DIR_SFX = RAIZ / "ui_web" / "assets" / "sfx"
SONIDOS = ("alarma_1", "alarma_2", "alarma_3")
CANAL = "alarma"


def elegir_visual(*, juego: bool, pantalla_grande: bool, render: str = "",
                  asistente_visible: bool = False) -> str:
    """discreto | grande | burbuja.

    - Con un juego delante: `discreto` (sonido + aviso de bandeja, nada en pantalla).
    - `alarmas.pantalla_grande` activado: `grande` (con la asistente VRM/animada a la
      vista, ella; si no, la VentanaReloj: eso lo decide ControlPantallaGrande).
      En patata no hay pantalla grande: `discreto`.
    - Si no: `burbuja` (burbuja roja en la asistente si está a la vista + la tarjeta).
    """
    if juego:
        return "discreto"
    if str(render or "") == "patata":
        return "discreto"
    if pantalla_grande:
        return "grande"
    return "burbuja"


def _lanzar_hilo(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="LuneAlarmaSonido", daemon=True).start()


class ControlAviso:
    """Una alarma sonando + la cola FIFO de las que esperan. Seguro entre hilos
    (los callbacks se llaman fuera del lock, en el hilo que llamó)."""

    def __init__(self, *, mezclador: Any = None, almacen: Any = None,
                 reloj: Callable[[], float] = time.monotonic, bloqueo_s: float = 5.0,
                 volumen: float = 0.8, sonido: str = "azar", posponer_min: float = 5,
                 max_sonando_s: float = 900, on_mostrar: Optional[Callable[[Disparo], Any]] = None,
                 on_ocultar: Optional[Callable[[Disparo], Any]] = None,
                 on_voz: Optional[Callable[[Disparo], Any]] = None,
                 lanzar: Optional[Callable[[Callable[[], None]], Any]] = None,
                 dispositivo: Optional[str] = None, azar: Optional[random.Random] = None,
                 epoch: Callable[[], float] = time.time):
        self._mez = mezclador
        self.almacen = almacen
        self._reloj = reloj
        self._epoch = epoch
        self.bloqueo_s = float(bloqueo_s)
        self.volumen = float(volumen)
        self.sonido = str(sonido or "azar")
        self.posponer_min = float(posponer_min)
        self.max_sonando_s = float(max_sonando_s)
        self.on_mostrar = on_mostrar
        self.on_ocultar = on_ocultar
        self.on_voz = on_voz
        self._lanzar = lanzar or _lanzar_hilo
        self.dispositivo = dispositivo
        self._dispositivo_puesto: Optional[str] = None
        self._azar = azar or random.Random()
        self._lock = threading.RLock()
        self._sonando: Optional[Disparo] = None
        self._cola: Deque[Disparo] = deque()
        self._desde = 0.0
        self._gen = 0
        self._sid: Optional[int] = None
        self._pospuestas: List[Tuple[float, Disparo]] = []   # sin almacén: (reloj, disparo)
        self.motivo_fin = ""            # apagada | pospuesta | cortada (lo lee on_ocultar)
        self.ultimo_sonido = ""         # nombre del WAV que sonó (para el log y los tests)

    # ── Estado ──
    @property
    def sonando(self) -> Optional[Disparo]:
        return self._sonando

    @property
    def cola(self) -> Tuple[Disparo, ...]:
        with self._lock:
            return tuple(self._cola)

    def puede_apagar(self) -> bool:
        with self._lock:
            return self._sonando is not None and self._reloj() - self._desde >= self.bloqueo_s

    def restante_bloqueo(self) -> float:
        """Segundos que faltan para poder apagarla (0 si ya se puede o no suena nada)."""
        with self._lock:
            if self._sonando is None:
                return 0.0
            return max(0.0, self.bloqueo_s - (self._reloj() - self._desde))

    def segundos_sonando(self) -> float:
        with self._lock:
            return 0.0 if self._sonando is None else max(0.0, self._reloj() - self._desde)

    # ── Disparar ──
    def _repetida(self, d: Disparo) -> bool:
        def igual(x: Optional[Disparo]) -> bool:
            return (x is not None and x.origen == d.origen and x.tipo == d.tipo
                    and abs(float(x.t) - float(d.t)) < 0.5 and d.tipo != "prueba")
        return igual(self._sonando) or any(igual(x) for x in self._cola)

    def disparar(self, d: Disparo) -> bool:
        """Empieza a sonar `d` (True) o lo pone en la cola (False). Un disparo
        repetido (mismo origen y momento) se ignora (False)."""
        with self._lock:
            if self._repetida(d):
                return False
            if self._sonando is not None:
                self._cola.append(d)
                return False
            self._empezar_locked(d)
        self._llamar(self.on_mostrar, d)
        return True

    def _empezar_locked(self, d: Disparo) -> None:
        self._sonando = d
        self._desde = self._reloj()
        self.motivo_fin = ""
        self._gen += 1
        gen = self._gen
        self._lanzar(lambda: self._sonar(gen))

    # ── Sonido ──
    def _mezclador(self):
        if self._mez is None:
            from servicios.mezclador import Mezclador
            self._mez = Mezclador.instancia()
        return self._mez

    def _elegir_wav(self) -> Path:
        nombre = self.sonido if self.sonido in SONIDOS else self._azar.choice(SONIDOS)
        return DIR_SFX / f"{nombre}.wav"

    def _sonar(self, gen: int) -> None:
        try:
            with self._lock:
                if gen != self._gen or self._sonando is None:
                    return
            mez = self._mezclador()
            if self.dispositivo is not None and self.dispositivo != self._dispositivo_puesto:
                poner = getattr(mez, "set_dispositivo", None)
                if callable(poner):
                    poner(self.dispositivo)
                self._dispositivo_puesto = self.dispositivo
            ruta = self._elegir_wav()
            cargar = getattr(mez, "cargar_wav", None)
            if not callable(cargar):
                from servicios.mezclador import cargar_wav as cargar
            buf = cargar(ruta)
            with self._lock:
                if gen != self._gen or self._sonando is None:
                    return
            sid = mez.reproducir(buf, vol=max(0.0, min(1.0, self.volumen)), bucle=True, canal=CANAL)
            with self._lock:
                vigente = gen == self._gen and self._sonando is not None
                if vigente:
                    self._sid = sid
                    self.ultimo_sonido = ruta.stem
            if not vigente:
                mez.detener(sid)
        except Exception:
            _log.exception("alarmas: no pude hacer sonar la alarma")

    def _callar_locked(self) -> None:
        self._gen += 1
        sid, self._sid = self._sid, None
        mez = self._mez
        if mez is None:
            return
        try:
            if sid is not None:
                mez.detener(sid)
            mez.detener_canal(CANAL)
        except Exception:
            _log.debug("alarmas: detener el sonido falló", exc_info=True)

    # ── Apagar, posponer, cortar ──
    def _terminar(self, motivo: str, forzar: bool) -> Optional[Tuple[Disparo, Optional[Disparo]]]:
        """Quita la que suena. → (la que sonaba, la siguiente de la cola o None)."""
        with self._lock:
            d = self._sonando
            if d is None:
                return None
            if not forzar and self._reloj() - self._desde < self.bloqueo_s:
                return None
            self._callar_locked()
            self.motivo_fin = motivo
            siguiente = self._cola.popleft() if self._cola else None
            if siguiente is not None:
                self._empezar_locked(siguiente)
            else:
                self._sonando = None
        if self.almacen is not None:
            try:
                self.almacen.quitar_sonando(d)
            except Exception:
                _log.exception("alarmas: no pude quitarla de sonando")
        return d, siguiente

    def _despues(self, par: Tuple[Disparo, Optional[Disparo]]) -> None:
        d, siguiente = par
        if siguiente is not None:
            self._llamar(self.on_mostrar, siguiente)
        else:
            self._llamar(self.on_ocultar, d)

    def apagar(self, forzar: bool = False) -> bool:
        """Apaga la que suena (tras el bloqueo, o ya con `forzar`) y pasa a la
        siguiente. False si no suena nada o aún está bloqueada."""
        par = self._terminar("apagada", forzar)
        if par is None:
            return False
        self._despues(par)
        if par[0].tipo != "prueba":
            self._llamar(self.on_voz, par[0])
        return True

    def posponer(self, forzar: bool = False) -> bool:
        """Apaga la que suena y la vuelve a poner dentro de `posponer_min` (tipo
        «pospuesta»). La prueba solo se apaga."""
        par = self._terminar("pospuesta", forzar)
        if par is None:
            return False
        d = par[0]
        if d.tipo != "prueba":
            seg = max(1, int(round(self.posponer_min * 60)))
            creado = False
            if self.almacen is not None:
                try:
                    self.almacen.crear_temporizador(seg, d.texto, iniciar=True, una_vez=True, pospuesta=True)
                    creado = True
                except Exception:
                    _log.exception("alarmas: no pude guardar la pospuesta")
            if not creado:
                with self._lock:
                    self._pospuestas.append((self._reloj() + seg,
                                             Disparo(d.origen, d.texto, "pospuesta", 0.0, d.programado,
                                                     self._epoch() + seg)))
        self._despues(par)
        return True

    def tick(self) -> None:
        """Corta la alarma a los `max_sonando_s` y dispara las pospuestas en memoria."""
        par = None
        with self._lock:
            cortar = (self._sonando is not None and self.max_sonando_s > 0
                      and self._reloj() - self._desde >= self.max_sonando_s)
        if cortar:
            _log.info("alarmas: «%s» lleva %d s sonando: la corto", self._sonando.texto if self._sonando else "",
                      int(self.max_sonando_s))
            par = self._terminar("cortada", True)
        if par is not None:
            self._despues(par)
        with self._lock:
            ahora = self._reloj()
            listas = [d for t, d in self._pospuestas if t <= ahora]
            self._pospuestas = [(t, d) for t, d in self._pospuestas if t > ahora]
        for d in listas:
            self.disparar(d)

    def detener(self) -> None:
        """Calla y olvida la cola en memoria. NO borra `sonando` de alarmas.json:
        quien arranque después (esta app, otra interfaz o patata) la recupera."""
        with self._lock:
            self._callar_locked()
            self._sonando = None
            self._cola.clear()
            self._pospuestas.clear()

    # ── Internos ──
    @staticmethod
    def _llamar(fn: Optional[Callable], d: Disparo) -> None:
        if fn is None:
            return
        try:
            fn(d)
        except Exception:
            _log.exception("alarmas: callback de aviso falló")


__all__ = ("ControlAviso", "elegir_visual", "DIR_SFX", "SONIDOS", "CANAL")
