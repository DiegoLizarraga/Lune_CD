"""
nucleo/fisica.py — Suavizados y muelles para todo lo que se mueve en Lune.

PARA QUÉ SIRVE
--------------
Una sola copia de las cuentas que usan los adaptadores de la mascota: la
ventana que sigue a la barra de tareas o a otra ventana al sentarse, la comida
que persigue al cursor, el balanceo de los sprites al arrastrarlos, los
fundidos entre poses... Sin Qt ni ventanas: son funciones puras que se prueban
en seco. `ui_web/vrm/lune_modulos.js` tiene las mismas fórmulas en JS para el
VRM; si se cambia una, hay que cambiar la otra.

QUÉ HAY
-------
- `smooth_damp()` / `smooth_damp_2d()`: la fórmula LITERAL de `Mathf.SmoothDamp`
  y `Vector2.SmoothDamp` de Unity (Game Programming Gems 4, cap. 1.10). Es la
  que usa Mate-Engine para mover la ventana. Críticamente amortiguado: llega
  sin pasarse. `smooth_time` es, aproximadamente, lo que tarda en llegar.
- `Muelle(f_hz, zeta)`: oscilador amortiguado (el AvatarSwayController de ME).
  Con ζ < 1 se pasa y rebota: con ζ 0.35 el primer sobrepaso es ≈31 %.
  Integración de Euler semi-implícito en subpasos de ≤ 1/120 s y protección
  contra NaN, igual que el `Muelle` de `lune_vrm.js`.
- `smoothstep(a, b, x)`: la de GLSL.
- `suav(dt, k)`: factor de un filtro exponencial independiente de los FPS,
  `1 − e^(−k·dt)`. `x += (obj − x) · suav(dt, k)` va igual a 30 que a 144 fps.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

# Subpaso máximo del muelle. Con dt grandes (ventana congelada, 10 fps, un
# arrastre que bloquea el hilo) el Euler explícito diverge y acaba en NaN.
PASO_MAX_S = 1.0 / 120.0

# Un dt mayor que esto se recorta: tras una suspensión o un bloqueo de varios
# segundos, simular horas de muelle en subpasos congelaría el hilo, y lo único
# que importa es que el muelle acabe cerca del objetivo.
DT_MAX_S = 1.0

Vec2 = Tuple[float, float]


def clamp(x: float, lo: float, hi: float) -> float:
    """`x` recortado a [lo, hi]."""
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    """Interpolación lineal (t no se recorta)."""
    return a + (b - a) * t


def suav(dt: float, k: float) -> float:
    """Factor de suavizado exponencial para un paso de `dt` s con rapidez `k` (1/s).

    Uso: `x += (objetivo - x) * suav(dt, k)`. k=10 recorre ~63 % de la distancia
    en 0.1 s, a cualquier tasa de frames. dt ≤ 0 o k ≤ 0 → 0 (no se mueve).
    """
    if not (dt > 0.0) or not (k > 0.0):
        return 0.0
    return 1.0 - math.exp(-k * dt)


def smoothstep(a: float, b: float, x: float) -> float:
    """Transición suave de 0 a 1 entre `a` y `b` (la de GLSL: 3t² − 2t³).

    Con a == b hace de escalón: 0 antes de `a` y 1 desde `a`.
    """
    if a == b:
        return 0.0 if x < a else 1.0
    t = clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smooth_damp(actual: float, objetivo: float, vel: float, smooth_time: float,
                max_speed: float = math.inf, dt: float = 1.0 / 60.0) -> Tuple[float, float]:
    """Un paso de `Mathf.SmoothDamp` de Unity. Devuelve `(nuevo, vel)`.

    `vel` es el estado entre llamadas (el `ref currentVelocity` de C#): se pasa
    el que devolvió el paso anterior, y 0 al empezar. `max_speed` en unidades/s.
    La única diferencia con C# es que dt ≤ 0 no hace nada (C# dividiría por 0).
    """
    if not (dt > 0.0):
        return actual, vel
    smooth_time = max(0.0001, smooth_time)
    omega = 2.0 / smooth_time

    x = omega * dt
    exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
    cambio = actual - objetivo
    destino_original = objetivo

    # Recorta la velocidad máxima
    max_cambio = max_speed * smooth_time
    cambio = clamp(cambio, -max_cambio, max_cambio)
    objetivo = actual - cambio

    temp = (vel + omega * cambio) * dt
    vel = (vel - omega * temp) * exp
    salida = objetivo + (cambio + temp) * exp

    # Evita pasarse del objetivo
    if (destino_original - actual > 0.0) == (salida > destino_original):
        salida = destino_original
        vel = (salida - destino_original) / dt
    return salida, vel


def smooth_damp_2d(actual: Vec2, objetivo: Vec2, vel: Vec2, smooth_time: float,
                   max_speed: float = math.inf, dt: float = 1.0 / 60.0) -> Tuple[Vec2, Vec2]:
    """Un paso de `Vector2.SmoothDamp` de Unity. Devuelve `((x, y), (vx, vy))`.

    A diferencia de llamar dos veces a `smooth_damp`, la velocidad máxima se
    aplica a la magnitud del vector y el «no pasarse» mira el producto escalar:
    en diagonal no va más rápido que en recto. Es lo que conviene para mover
    ventanas (posición en px).
    """
    if not (dt > 0.0):
        return (actual[0], actual[1]), (vel[0], vel[1])
    smooth_time = max(0.0001, smooth_time)
    omega = 2.0 / smooth_time

    x = omega * dt
    exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)

    cx = actual[0] - objetivo[0]
    cy = actual[1] - objetivo[1]
    ox, oy = objetivo

    max_cambio = max_speed * smooth_time
    dist2 = cx * cx + cy * cy
    if dist2 > max_cambio * max_cambio:
        mag = math.sqrt(dist2)
        cx = cx / mag * max_cambio
        cy = cy / mag * max_cambio

    tx = actual[0] - cx
    ty = actual[1] - cy

    temp_x = (vel[0] + omega * cx) * dt
    temp_y = (vel[1] + omega * cy) * dt

    vx = (vel[0] - omega * temp_x) * exp
    vy = (vel[1] - omega * temp_y) * exp

    sx = tx + (cx + temp_x) * exp
    sy = ty + (cy + temp_y) * exp

    if (ox - actual[0]) * (sx - ox) + (oy - actual[1]) * (sy - oy) > 0.0:
        sx, sy = ox, oy
        vx = (sx - ox) / dt
        vy = (sy - oy) / dt
    return (sx, sy), (vx, vy)


class Muelle:
    """Muelle amortiguado de un grado de libertad: `x'' = ω²(obj − x) − 2ζω·x'`.

    `f_hz` es la frecuencia natural (oscilaciones por segundo sin rozamiento) y
    `zeta` el amortiguamiento: 1 llega sin pasarse, < 1 rebota, > 1 llega lento.
    `tope` recorta |x| (p. ej. 90 para ángulos en grados); por defecto no hay.

        m = Muelle(0.75, 0.5)          # balanceo del arrastre de Mate-Engine
        angulo = m.paso(objetivo, dt)  # en cada frame
    """

    def __init__(self, f_hz: float, zeta: float, x: float = 0.0, tope: Optional[float] = None):
        self.f_hz = max(0.01, float(f_hz))
        self.zeta = max(0.0, float(zeta))
        self.x = float(x)
        self.v = 0.0
        self.tope = None if tope is None else abs(float(tope))

    @property
    def omega(self) -> float:
        """Frecuencia angular ω = 2πf (rad/s)."""
        return 2.0 * math.pi * self.f_hz

    def reiniciar(self, x: float = 0.0, v: float = 0.0) -> None:
        """Coloca el muelle en `x` con velocidad `v` (p. ej. al soltar la ventana)."""
        self.x, self.v = float(x), float(v)

    def paso(self, objetivo: float, dt: float) -> float:
        """Avanza `dt` segundos hacia `objetivo` y devuelve la nueva posición.

        Nunca devuelve NaN: si el objetivo o dt no son números válidos, no se
        mueve; si la integración revienta, se planta en el objetivo en reposo.
        """
        if not math.isfinite(objetivo) or not math.isfinite(dt) or dt <= 0.0:
            return self.x
        dt = min(dt, DT_MAX_S)
        w = self.omega
        z = self.zeta
        # Subpaso: ≤ 1/120 s como en lune_vrm.js y, además, lo bastante corto
        # para que el semi-implícito sea estable con f o ζ muy altos.
        paso_max = min(PASO_MAX_S, 0.5 / (w * (1.0 + z)))
        n = max(1, math.ceil(dt / paso_max))
        h = dt / n
        x, v = self.x, self.v
        for _ in range(n):
            a = w * w * (objetivo - x) - 2.0 * z * w * v
            v += a * h           # primero la velocidad…
            x += v * h           # …y la posición con la velocidad NUEVA (semi-implícito)
        if not (math.isfinite(x) and math.isfinite(v)):
            x, v = objetivo, 0.0
        if self.tope is not None:
            x = clamp(x, -self.tope, self.tope)
        self.x, self.v = x, v
        return x


def sobrepaso_teorico(zeta: float) -> float:
    """Primer sobrepaso de un muelle subamortiguado ante un escalón (fracción).

    `e^(−ζπ/√(1−ζ²))`: 0.309 con ζ 0.35, 0.163 con ζ 0.5, 0 con ζ ≥ 1.
    """
    if zeta >= 1.0:
        return 0.0
    if zeta <= 0.0:
        return 1.0
    return math.exp(-zeta * math.pi / math.sqrt(1.0 - zeta * zeta))
