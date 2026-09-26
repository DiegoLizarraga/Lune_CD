"""
ui/sprites_baile.py — El baile de la mascota de sprites (ui/avatar_overlay.py).

Un sprite 2D solo puede girarse un poco y moverse arriba y abajo: cada estilo de
`nucleo.baile.ESTILOS` se aproxima con un giro de ±4° (pivote arriba, como el
balanceo) y unos saltitos de pocos píxeles al ritmo del pulso. El resultado lo
compone `SpriteRotado.componer(grados, dy)` (ui/sprites_fx.py) con su máscara:
girar no recorta la silueta.

- `BaileSprite.paso(fase, energia, t, estilo)` → (grados, dy): la pose en un
  instante (pura, sin Qt; cuenta los golpes para alternar lados).
- `BaileSpriteQt`: reloj propio que extrapola el pulso que llega a ≤ 2 Hz
  (corrige la fase como mucho un 20 % por pulso), fundido de entrada y salida y
  un QTimer de 30 Hz que SOLO corre mientras baila. Emite `cuadro(grados, dy)`.
  El arrastre corta el baile en seco (`set_arrastre(True)`) y al soltarla vuelve
  con fundido.
"""
from __future__ import annotations

import math
import random
import time
from typing import Callable, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal

from nucleo.baile import ESTILOS, estilo_valido

TOPE_GRADOS = 4.0        # giro máximo del baile (el lienzo tiene margen para 7.5°)
DY_MAX = 5               # saltito máximo hacia arriba (px)
DY_ABAJO = 1             # agachadita máxima (px)
HZ = 30
ENTRADA_S = 0.4          # fundido de entrada
SALIDA_S = 0.5           # fundido de salida
CRUCE_S = 2.0            # fundido entre estilos (cambiar)
CORRECCION = 0.2         # parte del error de fase que se corrige en cada pulso
SALTO_FASE = 0.25        # con más error que esto la fase salta (primer pulso, otra canción)
BPM_MIN, BPM_MAX = 40.0, 240.0


def _acotar(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _envolver(x: float) -> float:
    """Diferencia de fase en [-0.5, 0.5)."""
    return (x + 0.5) % 1.0 - 0.5


def pose_estilo(estilo: str, fase: float, golpes: int, energia: float) -> Tuple[float, float]:
    """(grados, dy) sin acotar ni redondear para un estilo, la fase dentro del
    golpe (0..1), el número de golpe (para alternar) y la energía (0..1)."""
    f = fase % 1.0
    lado = 1.0 if golpes % 2 == 0 else -1.0
    amp = 0.45 + 0.55 * _acotar(energia, 0.0, 1.0)
    arriba = math.sin(math.pi * f)              # 0 en el golpe, 1 a mitad
    golpe = (1.0 - f) ** 3                      # pico en el golpe, cae rápido
    continuo = math.sin(math.pi * (golpes + f)) # vaivén de dos golpes, continuo
    if estilo == "vaiven":
        return TOPE_GRADOS * 0.9 * amp * continuo, -1.5 * amp * arriba
    if estilo == "brazos_arriba":
        return 1.5 * lado * amp * arriba, -DY_MAX * amp * (0.35 + 0.65 * arriba)
    if estilo == "palmas":
        return 0.8 * lado * amp * golpe, DY_ABAJO * golpe - 2.0 * amp * arriba
    if estilo == "cadera":
        return 3.2 * amp * lado * arriba, -1.0 * amp * arriba
    if estilo == "cabeceo":
        return 2.2 * amp * golpe * lado, DY_ABAJO * golpe - 0.8 * amp * arriba
    if estilo == "puno_alterno":
        return TOPE_GRADOS * amp * lado * golpe, -2.5 * amp * golpe
    if estilo == "paso_lateral":
        return 3.0 * amp * continuo, -DY_MAX * 0.6 * amp * arriba
    # rebote (y cualquier otro)
    return 0.6 * lado * amp * arriba, -DY_MAX * amp * arriba


class BaileSprite:
    """La pose del baile en cada instante. Cuenta los golpes (vueltas de la fase)."""

    def __init__(self):
        self.reiniciar()

    def reiniciar(self) -> None:
        self._golpes = 0
        self._fase_ant: Optional[float] = None

    @property
    def golpes(self) -> int:
        return self._golpes

    def paso(self, fase: float, energia: float, t: float, estilo: str) -> Tuple[float, int]:
        """(grados ±TOPE_GRADOS, dy en px entre -DY_MAX y DY_ABAJO)."""
        try:
            f = float(fase) % 1.0
        except (TypeError, ValueError):
            f = 0.0
        if not math.isfinite(f):
            f = 0.0
        if self._fase_ant is not None and f < self._fase_ant - 0.5:
            self._golpes += 1
        self._fase_ant = f
        try:
            e = float(energia)
        except (TypeError, ValueError):
            e = 0.5
        g, dy = pose_estilo(estilo_valido(estilo) or "rebote", f, self._golpes, e if math.isfinite(e) else 0.5)
        return (_acotar(g, -TOPE_GRADOS, TOPE_GRADOS),
                int(round(_acotar(dy, -DY_MAX, DY_ABAJO))))


class BaileSpriteQt(QObject):
    """El baile de los sprites con su reloj: `cuadro(grados, dy)` a 30 Hz mientras baila.

        b = BaileSpriteQt(ventana)
        b.cuadro.connect(...)
        b.bailar(True, {"estilo": "rebote", "cambiar": False, "cambiarS": 15})
        b.pulso(124.0, 0.3, 0.8)          # ≤ 2 Hz
        b.bailar(False)                   # fundido de salida; al acabar emite (0.0, 0) (siempre)
    """

    cuadro = pyqtSignal(float, int)

    def __init__(self, parent: Optional[QObject] = None, *, reloj: Callable[[], float] = time.monotonic,
                 hz: int = HZ, rng: Optional[random.Random] = None):
        super().__init__(parent)
        self._reloj = reloj
        self._rng = rng or random.Random()
        self._sprite = BaileSprite()
        self._on = False
        self._arrastre = False
        self._peso = 0.0
        self._estilo = "rebote"
        self._estilo_prev: Optional[str] = None
        self._t_estilo = 0.0
        self._cambiar = False
        self._cambiar_s = 15.0
        self._bpm = 120.0
        self._pos_ref = 0.0                  # golpes (continuos) en _t_ref
        self._t_ref = reloj()
        self._con_pulso = False
        self._energia = 0.6
        self._energia_obj = 0.6
        self._t_tic: Optional[float] = None
        self._ultimo: Tuple[float, int] = (0.0, 0)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, int(round(1000 / max(1, hz)))))
        self._timer.timeout.connect(self._tick)

    # ── Estado ──
    @property
    def activo(self) -> bool:
        """¿Corre el temporizador? (bailando o en el fundido de salida)."""
        return self._timer.isActive()

    @property
    def bailando(self) -> bool:
        return self._on

    @property
    def estilo(self) -> str:
        return self._estilo

    @property
    def peso(self) -> float:
        return self._peso

    # ── Órdenes ──
    def bailar(self, on: bool, opciones: Optional[dict] = None) -> None:
        on = bool(on)
        if on:
            op = opciones if isinstance(opciones, dict) else {}
            estilo = estilo_valido(op.get("estilo")) or (self._estilo if self._on else "rebote")
            if self._on and estilo != self._estilo:
                self._cambiar_estilo(estilo)
            elif not self._on:
                self._estilo = estilo
                self._estilo_prev = None
                self._sprite.reiniciar()
            self._cambiar = bool(op.get("cambiar", False))
            try:
                self._cambiar_s = _acotar(float(op.get("cambiarS", 15)), 5.0, 120.0)
            except (TypeError, ValueError):
                self._cambiar_s = 15.0
            if not self._on:
                self._t_estilo = self._reloj()
            self._on = True
            if not self._timer.isActive():
                self._t_tic = None
                self._timer.start()
        else:
            self._on = False
            if self._peso <= 0.0:
                self.detener()
            elif not self._timer.isActive():
                self._t_tic = None
                self._timer.start()

    def pulso(self, bpm: float, fase: float, energia: float) -> None:
        """Pulso de la música (bpm, fase 0..1 en este instante, energía 0..1)."""
        try:
            b, f, e = float(bpm), float(fase), float(energia)
        except (TypeError, ValueError):
            return
        if not (math.isfinite(b) and math.isfinite(f) and math.isfinite(e)):
            return
        t = self._reloj()
        actual = self._pos(t)
        err = _envolver(f - actual)
        if not self._con_pulso or abs(err) > SALTO_FASE:
            nueva = actual + err
        else:
            nueva = actual + CORRECCION * err
        self._pos_ref = nueva
        self._t_ref = t
        self._bpm = _acotar(b, BPM_MIN, BPM_MAX)
        self._energia_obj = _acotar(e, 0.0, 1.0)
        self._con_pulso = True

    def set_arrastre(self, on: bool) -> None:
        """La están arrastrando: el baile se corta en seco (y vuelve con fundido al soltar)."""
        self._arrastre = bool(on)
        if self._arrastre:
            self._peso = 0.0
            self._emitir(0.0, 0)

    def detener(self) -> None:
        """Para ya, sin fundido, y la deja recta."""
        self._on = False
        self._timer.stop()
        self._peso = 0.0
        self._t_tic = None
        self._emitir(0.0, 0, forzar=True)            # siempre: avisa de que acabó

    # ── Internos ──
    def _pos(self, t: float) -> float:
        return self._pos_ref + (t - self._t_ref) * self._bpm / 60.0

    def _cambiar_estilo(self, nuevo: str) -> None:
        self._estilo_prev = self._estilo
        self._estilo = nuevo
        self._t_estilo = self._reloj()

    def _emitir(self, g: float, dy: int, forzar: bool = False) -> None:
        c = (round(float(g), 2), int(dy))
        if forzar or c != self._ultimo:
            self._ultimo = c
            self.cuadro.emit(c[0], c[1])

    def _tick(self) -> None:
        t = self._reloj()
        dt = 0.0 if self._t_tic is None else max(0.0, min(0.25, t - self._t_tic))
        self._t_tic = t
        objetivo = 1.0 if (self._on and not self._arrastre) else 0.0
        if self._peso < objetivo:
            self._peso = min(objetivo, self._peso + dt / ENTRADA_S)
        elif self._peso > objetivo:
            self._peso = max(objetivo, self._peso - dt / SALIDA_S)
        if not self._on and self._peso <= 0.0:
            self.detener()
            return
        # energía suavizada (~0.3 s)
        self._energia += (self._energia_obj - self._energia) * min(1.0, dt / 0.3)
        if self._on and self._cambiar and t - self._t_estilo >= self._cambiar_s:
            otros = [e for e in ESTILOS if e != self._estilo]
            self._cambiar_estilo(self._rng.choice(otros))
        fase = self._pos(t) % 1.0
        g, dy = self._sprite.paso(fase, self._energia, t, self._estilo)
        if self._estilo_prev is not None:
            mezcla = _acotar((t - self._t_estilo) / CRUCE_S, 0.0, 1.0)
            if mezcla >= 1.0:
                self._estilo_prev = None
            else:
                g0, dy0 = pose_estilo(self._estilo_prev, fase, self._sprite.golpes, self._energia)
                g = (1 - mezcla) * _acotar(g0, -TOPE_GRADOS, TOPE_GRADOS) + mezcla * g
                dy = (1 - mezcla) * _acotar(dy0, -DY_MAX, DY_ABAJO) + mezcla * dy
        self._emitir(_acotar(g * self._peso, -TOPE_GRADOS, TOPE_GRADOS),
                     int(round(_acotar(dy * self._peso, -DY_MAX, DY_ABAJO))))


__all__ = ("TOPE_GRADOS", "DY_MAX", "DY_ABAJO", "pose_estilo", "BaileSprite", "BaileSpriteQt")
