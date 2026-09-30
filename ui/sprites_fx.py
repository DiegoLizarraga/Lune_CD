"""
ui/sprites_fx.py — Movimiento de la asistente de sprites (bajos recursos).

PARA QUÉ SIRVE
--------------
La asistente de sprites (`ui/avatar_overlay.py`) es una imagen fija: al
arrastrarla no se inmuta y en reposo parece un recorte pegado. Aquí están las
piezas para que se mueva como las otras, sin Chromium y casi sin CPU:

Lógica pura (sin Qt, se prueba en seco):
- `FisicaSprite`: balanceo de péndulo al arrastrar. La velocidad sale de
  Δposición/Δtiempo de la VENTANA (moveEvent: con `startSystemMove` no llegan
  eventos de ratón) y el ángulo la sigue con un `nucleo.fisica.Muelle`
  (0.9 Hz, ζ 0.5, como el balanceo 2D de la asistente animada). Ganancia de
  Mate-Engine (0.0167 °/(px/s)) con saturación suave a ±6° (crítica c.6: más
  giro no cabe en la ventana). Al parar, el objetivo vuelve a 0 y el muelle
  rebota (≈16 % de sobrepaso) y se asienta.
  Convenio: grados de Qt (positivo = horario en pantalla, como `QPainter.rotate`).
  Moviéndola a la derecha el ángulo es positivo: la parte de abajo se queda atrás.
- `ClasificadorVelocidad`: cara según la velocidad del arrastre (tranquila
  < 400 px/s ≤ preocupada < 1500 ≤ asustada), con histéresis.
- `DetectorMareo`: 4 inversiones de sentido a más de 800 px/s en 1.5 s → mareo
  (enfriamiento de 10 s). Los mismos números que el módulo `movimiento` del VRM.
- `RespiracionSprite`: sube y baja ±1–2 px con periodo de 4 s (6 s dormida) y un
  desfase al azar; el cambio de ritmo no da saltos.
- `lado_mirada(cursor_global, rect)` → 'izq' | 'der', con histéresis opcional.
- `margen_lienzo(w, h, grados, pivote)`: cuánto margen necesita el sprite para
  girar sin salirse de su lienzo.

Adaptadores Qt:
- `FisicaSpriteQt(QObject)`: `vigilar(ventana)` escucha sus Move; QTimer de 30 Hz
  SOLO mientras se mueve o el muelle no se ha asentado. Señales `angulo(float)`,
  `movimiento(bool)` (empieza/acaba el arrastre), `cara(str)` y `mareo()`.
- `RespiracionSpriteQt(QObject)`: QTimer de 10 Hz y señal `dy(int)` solo cuando
  cambia el píxel.
- `SpriteRotado`: compone el sprite girado/desplazado/espejado dentro de un
  lienzo con margen y devuelve también su región de clic. Resuelve la crítica
  c.8: girar la imagen dejando la máscara de silueta congelada la recorta. Aquí
  el fondo oscuro del sprite se convierte en alfa UNA vez (mismo chroma-key por
  filas que `AvatarOverlay._region_silueta`) y la región se recalcula del alfa
  de cada fotograma compuesto (con caché por ángulo cuantizado).
"""
from __future__ import annotations

import math
import random
import time
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Optional, Tuple

from PyQt6.QtCore import QEvent, QObject, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QRegion

from nucleo.fisica import Muelle, clamp, suav

# ── Constantes (Mate-Engine y plan P02) ──────────────────────────────────────────
GANANCIA = 0.0167        # °/(px/s): la de la escena de ME, en los dos ejes
F_HZ = 0.9               # muelle del balanceo 2D (asistente animada: 0.9 Hz, ζ 0.5)
ZETA = 0.5
TOPE_GRADOS = 6.0        # crítica c.6: con más giro el sprite se sale de la ventana
PIVOTE = (0.5, 0.06)     # centro arriba: cuelga de donde la agarras

QUIETO_S = 0.12          # sin Move en este tiempo → la ventana está quieta
HUECO_S = 0.25           # un Move tras más de esto empieza un tramo nuevo (sin velocidad)
DT_MIN_S = 0.004         # Move más seguidos se acumulan (evita velocidades absurdas)
SALTO_PX = 400.0         # salto de más de esto en un Move = colocación por código
V_MAX = 8000.0           # px/s
K_VEL = 20.0             # suavizado de la velocidad (1/s)
K_FRENO = 18.0           # la velocidad cae a 0 así cuando deja de moverse
EPS_ANGULO = 0.05        # ° para darla por asentada…
EPS_VEL_ANG = 0.5        # …y °/s

UMBRALES_VELOCIDAD = (400.0, 1500.0)
CARAS_VELOCIDAD = ("tranquila", "preocupada", "asustada")

MAREO_INVERSIONES = 4
MAREO_VENTANA_S = 1.5
MAREO_V_MIN = 800.0
MAREO_COOLDOWN_S = 10.0

# Cara de lune_face sugerida para cada situación (los sprites no tienen más).
CARA_SPRITE = {
    "tranquila": "sad",        # la cara sostenida de arrastre («déjame en el suelo»)
    "preocupada": "confused",
    "asustada": "error",
    "mareada": "confused",
    "soltar": "happy",
}

HZ_FISICA = 30
HZ_RESPIRACION = 10
V_ARRANQUE = 60.0        # px/s para dar por empezado un arrastre
FIN_S = 0.30             # quieta este tiempo (y sin botón pulsado) → acabó el arrastre


def _xy(p: Any) -> Tuple[float, float]:
    """(x, y) de un QPoint/QPointF o de una tupla."""
    if hasattr(p, "x") and callable(p.x):
        return float(p.x()), float(p.y())
    return float(p[0]), float(p[1])


def _rect(r: Any) -> Tuple[float, float, float, float]:
    """(x, y, w, h) de un QRect/QRectF o de una tupla."""
    if hasattr(r, "x") and callable(r.x):
        return float(r.x()), float(r.y()), float(r.width()), float(r.height())
    return float(r[0]), float(r[1]), float(r[2]), float(r[3])


# ── Balanceo ─────────────────────────────────────────────────────────────────────
class FisicaSprite:
    """Péndulo del sprite: posición de la ventana → ángulo (grados de Qt).

        f = FisicaSprite()
        f.mover(x, y, t)        # en cada moveEvent (t en s, reloj monótono fino)
        angulo = f.paso(t)      # a 30 Hz mientras no esté en reposo
        f.reposo                # True cuando ya no hace falta el temporizador

    `saltar(x, y, t)`: la ventana se colocó por código (restaurar posición,
    pegarla a otra ventana…): cambia la referencia sin balancearse.
    """

    def __init__(self, ganancia: float = GANANCIA, f_hz: float = F_HZ, zeta: float = ZETA,
                 tope: float = TOPE_GRADOS, invertir: bool = False, quieto_s: float = QUIETO_S,
                 k_vel: float = K_VEL):
        self.ganancia = float(ganancia)
        self.tope = abs(float(tope))
        self.signo = -1.0 if invertir else 1.0
        self.quieto_s = float(quieto_s)
        self.k_vel = float(k_vel)
        # El muelle puede pasarse del objetivo al rebotar: tope duro algo mayor.
        self.muelle = Muelle(f_hz, zeta, tope=self.tope * 1.5 if self.tope > 0 else None)
        self.reiniciar()

    def reiniciar(self) -> None:
        """Quieta y recta, sin referencia de posición."""
        self.muelle.reiniciar(0.0, 0.0)
        self._ref: Optional[Tuple[float, float, float]] = None
        self.vx = self.vy = 0.0              # velocidad suavizada (px/s)
        self.vx_inst = self.vy_inst = 0.0    # la del último tramo, sin suavizar
        self.t_ultimo_mov = -math.inf
        self._t_paso: Optional[float] = None
        self.reposo = True

    @property
    def angulo(self) -> float:
        return self.muelle.x

    @property
    def rapidez(self) -> float:
        """Módulo de la velocidad suavizada (px/s)."""
        return math.hypot(self.vx, self.vy)

    def moviendo(self, t: float) -> bool:
        """¿Hubo un Move hace menos de `quieto_s`?"""
        return (t - self.t_ultimo_mov) <= self.quieto_s

    def saltar(self, x: float, y: float, t: float) -> None:
        """Nueva referencia sin velocidad (colocación por código)."""
        self._ref = (float(x), float(y), float(t))
        self.vx = self.vy = self.vx_inst = self.vy_inst = 0.0

    def mover(self, x: float, y: float, t: float) -> bool:
        """Registra la posición de la ventana en `t`. True si dio una muestra de velocidad."""
        try:
            x, y, t = float(x), float(y), float(t)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(t)):
            return False
        if self._ref is None:
            self._ref = (x, y, t)
            return False
        rx, ry, rt = self._ref
        dt = t - rt
        if dt < 0.0 or dt > HUECO_S:
            self.saltar(x, y, t)                 # tramo nuevo: sin velocidad todavía
            return False
        if dt < DT_MIN_S:
            return False                         # se acumula con el siguiente
        dx, dy = x - rx, y - ry
        if math.hypot(dx, dy) > SALTO_PX:
            self.saltar(x, y, t)
            return False
        self._ref = (x, y, t)
        if dx == 0.0 and dy == 0.0:
            return False
        vxi = clamp(dx / dt, -V_MAX, V_MAX)
        vyi = clamp(dy / dt, -V_MAX, V_MAX)
        k = suav(dt, self.k_vel)
        self.vx += (vxi - self.vx) * k
        self.vy += (vyi - self.vy) * k
        self.vx_inst, self.vy_inst = vxi, vyi
        if self.reposo:
            self._t_paso = t                     # el paso siguiente no arrastra un dt viejo
        self.t_ultimo_mov = t
        self.reposo = False
        return True

    def objetivo(self) -> float:
        """Ángulo al que tira el muelle con la velocidad actual (saturación suave)."""
        a = self.ganancia * self.vx
        if self.tope > 0:
            a = self.tope * math.tanh(a / self.tope)
        return self.signo * a

    def paso(self, t: float) -> float:
        """Avanza el muelle hasta `t` y devuelve el ángulo (0.0 exacto en reposo)."""
        try:
            t = float(t)
        except (TypeError, ValueError):
            return self.angulo
        if not math.isfinite(t):
            return self.angulo
        if self._t_paso is None:
            self._t_paso = t
            return self.angulo
        dt = t - self._t_paso
        self._t_paso = t
        if not (dt > 0.0):
            return self.angulo
        dt = min(dt, 0.1)                        # un tirón del hilo no dispara el muelle
        moviendo = self.moviendo(t)
        if not moviendo:
            freno = 1.0 - suav(dt, K_FRENO)
            self.vx *= freno
            self.vy *= freno
            if abs(self.vx) < 1.0 and abs(self.vy) < 1.0:
                self.vx = self.vy = 0.0
        a = self.muelle.paso(self.objetivo(), dt)
        if (not moviendo and self.vx == 0.0 and abs(a) < EPS_ANGULO
                and abs(self.muelle.v) < EPS_VEL_ANG):
            self.muelle.reiniciar(0.0, 0.0)
            self.reposo = True
            return 0.0
        return a


class ClasificadorVelocidad:
    """Cara según la rapidez del arrastre, con histéresis y permanencia mínima.

    Sube de nivel en cuanto se pasa el umbral; baja cuando cae por debajo del
    umbral × `histeresis` y lleva `permanencia_s` en el nivel (no parpadea).
    """

    def __init__(self, umbrales: Tuple[float, float] = UMBRALES_VELOCIDAD,
                 histeresis: float = 0.8, permanencia_s: float = 0.4):
        self.umbrales = tuple(float(u) for u in umbrales)
        self.histeresis = float(histeresis)
        self.permanencia_s = float(permanencia_s)
        self.reiniciar()

    def reiniciar(self) -> None:
        self.nivel = 0
        self._t_nivel: Optional[float] = None

    @property
    def cara(self) -> str:
        return CARAS_VELOCIDAD[self.nivel]

    def actualizar(self, rapidez: float, t: float) -> str:
        v = float(rapidez) if math.isfinite(rapidez) else 0.0
        n = self.nivel
        while n < len(self.umbrales) and v >= self.umbrales[n]:
            n += 1
        while n > 0 and v < self.umbrales[n - 1] * self.histeresis:
            n -= 1
        if n > self.nivel:
            self.nivel, self._t_nivel = n, t
        elif n < self.nivel:
            if self._t_nivel is None or t - self._t_nivel >= self.permanencia_s:
                self.nivel, self._t_nivel = n, t
        elif self._t_nivel is None:
            self._t_nivel = t
        return self.cara


class DetectorMareo:
    """Agitarla marea: `inversiones` cambios de sentido a más de `v_min` px/s en
    `ventana_s` (en cualquiera de los dos ejes). Después, `cooldown_s` sin avisar."""

    def __init__(self, inversiones: int = MAREO_INVERSIONES, ventana_s: float = MAREO_VENTANA_S,
                 v_min: float = MAREO_V_MIN, cooldown_s: float = MAREO_COOLDOWN_S):
        self.inversiones = max(1, int(inversiones))
        self.ventana_s = float(ventana_s)
        self.v_min = float(v_min)
        self.cooldown_s = float(cooldown_s)
        self._t_mareo = -math.inf
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida las inversiones (no el enfriamiento)."""
        self._signo = [0, 0]
        self._marcas: Tuple[Deque[float], Deque[float]] = (deque(), deque())

    def actualizar(self, vx: float, vy: float, t: float) -> bool:
        """Una muestra de velocidad. True justo cuando se marea."""
        disparo = False
        for eje, v in enumerate((vx, vy)):
            if not math.isfinite(v) or abs(v) < self.v_min:
                continue
            s = 1 if v > 0 else -1
            marcas = self._marcas[eje]
            if self._signo[eje] and s != self._signo[eje]:
                marcas.append(t)
            self._signo[eje] = s
            while marcas and t - marcas[0] > self.ventana_s:
                marcas.popleft()
            if len(marcas) >= self.inversiones and t - self._t_mareo >= self.cooldown_s:
                disparo = True
        if disparo:
            self._t_mareo = t
            self.reiniciar()
        return disparo


# ── Respiración y mirada ─────────────────────────────────────────────────────────
class RespiracionSprite:
    """Sube y baja el sprite: `dy(t)` en px (negativo = arriba, como en Qt).

    Amplitud 1–2 px y periodo de 4 s; dormida, 2 px y 6 s. El desfase inicial es
    al azar (con `rng`) para que no respiren igual dos asistentes ni al abrirla. La
    fase se acumula: cambiar de ritmo (`set_dormida`) no da saltos.
    """

    def __init__(self, amplitud: float = 1.5, periodo: float = 4.0, desfase: Optional[float] = None,
                 rng: Optional[random.Random] = None, amplitud_dormida: float = 2.0,
                 periodo_dormida: float = 6.0, t0: float = 0.0):
        self.amplitud_despierta = clamp(float(amplitud), 1.0, 2.0)
        self.periodo_despierta = max(0.5, float(periodo))
        self.amplitud_dormida = clamp(float(amplitud_dormida), 1.0, 2.0)
        self.periodo_dormida = max(0.5, float(periodo_dormida))
        if desfase is None:
            desfase = (rng or random.Random()).random() * 2.0 * math.pi
        self.dormida = False
        self._t_ref = float(t0)
        self._fase_ref = float(desfase)

    @property
    def amplitud(self) -> float:
        return self.amplitud_dormida if self.dormida else self.amplitud_despierta

    @property
    def periodo(self) -> float:
        return self.periodo_dormida if self.dormida else self.periodo_despierta

    def fase(self, t: float) -> float:
        return self._fase_ref + 2.0 * math.pi * (float(t) - self._t_ref) / self.periodo

    def set_dormida(self, dormida: bool, t: float) -> None:
        """Cambia de ritmo en `t` conservando la fase."""
        dormida = bool(dormida)
        if dormida == self.dormida:
            return
        self._fase_ref = self.fase(t) % (2.0 * math.pi)
        self._t_ref = float(t)
        self.dormida = dormida

    def dy(self, t: float) -> float:
        return -self.amplitud * math.sin(self.fase(t))

    def dy_px(self, t: float) -> int:
        return int(round(self.dy(t)))


def lado_mirada(cursor_global: Any, rect: Any, actual: Optional[str] = None,
                histeresis: float = 0.0) -> str:
    """'izq' si el cursor está a la izquierda del centro de `rect`, si no 'der'.

    `cursor_global`: QPoint/QPointF o (x, y). `rect`: QRect/QRectF o (x, y, w, h),
    en las mismas coordenadas (las globales de la ventana: `frameGeometry()`).
    Con `actual` y `histeresis` (px), dentro de esa franja se queda como estaba.
    """
    cx, _ = _xy(cursor_global)
    x, _y, w, _h = _rect(rect)
    dx = cx - (x + w / 2.0)
    if actual in ("izq", "der") and abs(dx) <= histeresis:
        return actual
    return "izq" if dx < 0 else "der"


def margen_lienzo(w: float, h: float, grados: float, pivote: Tuple[float, float] = PIVOTE
                  ) -> Tuple[int, int]:
    """Margen (mx, my), simétrico, para girar un sprite w×h ±`grados` sobre `pivote`
    (fracciones de w y h) sin salirse del lienzo. Simétrico para que, sin giro,
    el sprite quede en el mismo sitio que antes (centrado)."""
    px, py = pivote[0] * w, pivote[1] * h
    esquinas = ((-px, -py), (w - px, -py), (-px, h - py), (w - px, h - py))
    mx = my = 0.0
    for g in (-abs(grados), abs(grados)):
        r = math.radians(g)
        c, s = math.cos(r), math.sin(r)
        for ex, ey in esquinas:
            x = ex * c - ey * s + px
            y = ex * s + ey * c + py
            mx = max(mx, -x, x - w)
            my = max(my, -y, y - h)
    return int(math.ceil(mx - 1e-9)), int(math.ceil(my - 1e-9))


# ── Imagen: chroma-key, región y composición ─────────────────────────────────────
def _vista(img: QImage, escribir: bool = False):
    """Vista numpy (alto, ancho, 4) BGRA de una QImage ARGB32/ARGB32_Premultiplied.

    Solo lectura salvo con `escribir` (bits() desacopla la imagen si está compartida)."""
    import numpy as np
    w, h = img.width(), img.height()
    ptr = img.bits() if escribir else img.constBits()
    ptr.setsize(img.sizeInBytes())
    return np.frombuffer(ptr, np.uint8).reshape((h, img.bytesPerLine() // 4, 4))[:, :w, :]


def recortar_fondo(imagen: QImage, umbral: int = 45) -> QImage:
    """El sprite con el fondo oscuro convertido en transparente (ARGB32 premultiplicada).

    Mismo criterio que `AvatarOverlay._region_silueta`: en cada fila es figura
    todo lo que va del primer al último píxel con R+G+B ≥ `umbral` (así el pelo
    o los ojos oscuros no se agujerean). Si el PNG ya trae alfa, se respeta.
    Sin numpy se devuelve la imagen tal cual (opaca), como el respaldo del overlay.
    """
    img = imagen.convertToFormat(QImage.Format.Format_ARGB32)
    try:
        import numpy as np
        a = _vista(img, escribir=True)
        lum = a[:, :, 0].astype(np.int16) + a[:, :, 1] + a[:, :, 2]
        fg = (lum >= umbral) & (a[:, :, 3] > 0)
        hay = fg.any(axis=1)
        x0 = np.argmax(fg, axis=1)
        x1 = fg.shape[1] - 1 - np.argmax(fg[:, ::-1], axis=1)
        cols = np.arange(fg.shape[1])[None, :]
        dentro = hay[:, None] & (cols >= x0[:, None]) & (cols <= x1[:, None])
        a[:, :, 3] = np.where(dentro, a[:, :, 3], 0).astype(np.uint8)
    except Exception:
        pass
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def region_silueta(img: QImage, alfa_min: int = 1) -> QRegion:
    """Región de clic de una imagen con alfa: por filas, del primer al último
    píxel con alfa ≥ `alfa_min`. Rect completo si no hay numpy; vacía si no hay figura."""
    w, h = img.width(), img.height()
    try:
        import numpy as np
        if img.format() not in (QImage.Format.Format_ARGB32, QImage.Format.Format_ARGB32_Premultiplied):
            img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        fg = _vista(img)[:, :, 3] >= alfa_min
        hay = fg.any(axis=1)
        x0 = np.argmax(fg, axis=1)
        x1 = fg.shape[1] - 1 - np.argmax(fg[:, ::-1], axis=1)
        rects = [QRect(int(x0[y]), y, int(x1[y] - x0[y] + 1), 1) for y in np.nonzero(hay)[0].tolist()]
    except Exception:
        return QRegion(0, 0, w, h)
    region = QRegion()
    if not rects:
        return region
    try:
        region.setRects(rects)                   # filas de 1 px ordenadas: bandas válidas
    except Exception:
        for r in rects:
            region = region.united(QRegion(r))
    return region


class SpriteRotado:
    """El sprite dentro de un lienzo con margen, girado, desplazado y espejado a
    voluntad, con su región de clic. Para la asistente de sprites (crítica c.8).

        sr = SpriteRotado(cara._pixmap_actual.toImage())
        img, region = sr.componer(grados=angulo, dy=respiracion, espejo=lado == 'izq')
        # img: QImage del tamaño sr.lienzo (w + 2·mx, h + 2·my), centrada igual que
        #      el sprite sin girar; region: en coordenadas de img.

    `recortar=True` pasa el fondo oscuro a alfa (sprites de lune_face). El giro se
    limita a ±`tope_grados` y `dy` a ±`resp_px`. Caché LRU pequeña (`cache`
    fotogramas) con el ángulo cuantizado a `paso_grados`: en reposo solo cambia
    `dy` (5 valores) y no se recompone nada.
    """

    def __init__(self, imagen: QImage, tope_grados: float = TOPE_GRADOS * 1.25,
                 pivote: Tuple[float, float] = PIVOTE, resp_px: int = 2, umbral_fondo: int = 45,
                 paso_grados: float = 0.25, cache: int = 12, recortar: bool = True):
        self.base = (recortar_fondo(imagen, umbral_fondo) if recortar
                     else imagen.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        self._espejada: Optional[QImage] = None
        self.tope_grados = abs(float(tope_grados))
        self.pivote = (float(pivote[0]), float(pivote[1]))
        self.resp_px = max(0, int(resp_px))
        self.paso_grados = max(0.01, float(paso_grados))
        self._max_cache = max(1, int(cache))
        self._cache: "OrderedDict[tuple, Tuple[QImage, QRegion]]" = OrderedDict()
        w, h = self.base.width(), self.base.height()
        mx, my = margen_lienzo(w, h, self.tope_grados, self.pivote)
        self.margen = (mx, my + self.resp_px)
        self.lienzo = (w + 2 * self.margen[0], h + 2 * self.margen[1])

    @property
    def tamano_sprite(self) -> Tuple[int, int]:
        return self.base.width(), self.base.height()

    def _fuente(self, espejo: bool) -> QImage:
        if not espejo:
            return self.base
        if self._espejada is None:
            try:
                self._espejada = self.base.flipped(Qt.Orientation.Horizontal)
            except AttributeError:                                  # Qt < 6.9
                self._espejada = self.base.mirrored(True, False)
        return self._espejada

    def componer(self, grados: float = 0.0, dy: int = 0, espejo: bool = False,
                 atenuar: float = 0.0) -> Tuple[QImage, QRegion]:
        """(imagen del lienzo, región de clic). `atenuar` 0..1 oscurece (dormida)."""
        g = clamp(float(grados) if math.isfinite(grados) else 0.0, -self.tope_grados, self.tope_grados)
        paso = int(round(g / self.paso_grados))
        d = int(clamp(int(round(dy)), -self.resp_px, self.resp_px))
        at = int(round(clamp(float(atenuar), 0.0, 1.0) * 20))
        clave = (paso, d, bool(espejo), at)
        hit = self._cache.get(clave)
        if hit is not None:
            self._cache.move_to_end(clave)
            return hit
        res = self._pintar(paso * self.paso_grados, d, bool(espejo), at / 20.0)
        self._cache[clave] = res
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return res

    def _pintar(self, grados: float, dy: int, espejo: bool, atenuar: float) -> Tuple[QImage, QRegion]:
        src = self._fuente(espejo)
        w, h = src.width(), src.height()
        px = (1.0 - self.pivote[0] if espejo else self.pivote[0]) * w
        py = self.pivote[1] * h
        out = QImage(self.lienzo[0], self.lienzo[1], QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.translate(self.margen[0] + px, self.margen[1] + py + dy)
            if grados:
                p.rotate(grados)
            p.translate(-px, -py)
            p.drawImage(0, 0, src)
            if atenuar > 0:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                p.fillRect(0, 0, w, h, QColor(0, 0, 0, int(round(255 * atenuar))))
        finally:
            p.end()
        return out, region_silueta(out)


# ── Adaptadores Qt ───────────────────────────────────────────────────────────────
class FisicaSpriteQt(QObject):
    """`FisicaSprite` + caras + mareo con un QTimer de 30 Hz que solo corre
    mientras la ventana se mueve o el muelle no se ha asentado.

        fx = FisicaSpriteQt(ventana, boton=win_entrada.api_defecto().boton_izquierdo)
        fx.vigilar(ventana)                  # escucha sus QEvent.Move
        fx.angulo.connect(...)               # grados de Qt; 0.0 al asentarse
        fx.movimiento.connect(...)           # True al empezar el arrastre, False al acabar
        fx.cara.connect(...)                 # 'tranquila'|'preocupada'|'asustada' ('' al acabar)
        fx.mareo.connect(...)

    `boton()` (opcional) dice si el botón izquierdo sigue pulsado: con él, parar
    el ratón sin soltar no da el arrastre por acabado. Sin él, se acaba a los
    `fin_s` quieta. Para colocar la ventana por código sin balanceo: `saltar()`.
    """

    angulo = pyqtSignal(float)
    movimiento = pyqtSignal(bool)
    cara = pyqtSignal(str)
    mareo = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None, *, fisica: Optional[FisicaSprite] = None,
                 reloj: Callable[[], float] = time.perf_counter, hz: int = HZ_FISICA,
                 boton: Optional[Callable[[], bool]] = None, fin_s: float = FIN_S,
                 clasificador: Optional[ClasificadorVelocidad] = None,
                 detector_mareo: Optional[DetectorMareo] = None):
        super().__init__(parent)
        self.fisica = fisica if fisica is not None else FisicaSprite()
        self.clasificador = clasificador if clasificador is not None else ClasificadorVelocidad()
        self.detector_mareo = detector_mareo if detector_mareo is not None else DetectorMareo()
        self._reloj = reloj
        self._boton = boton
        self.fin_s = float(fin_s)
        self._habilitado = True
        self._arrastrando = False
        self._cara = ""
        self._ultimo = 0.0
        self._widget: Optional[QObject] = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(1, int(round(1000 / max(1, hz)))))
        self._timer.timeout.connect(self._tick)

    # ── Ventana vigilada ──
    def vigilar(self, widget: QObject) -> None:
        """Escucha los QEvent.Move de `widget` (la ventana de la asistente)."""
        self.dejar()
        self._widget = widget
        widget.installEventFilter(self)
        try:
            self.fisica.saltar(widget.x(), widget.y(), self._reloj())
        except Exception:
            pass

    def dejar(self) -> None:
        if self._widget is not None:
            try:
                self._widget.removeEventFilter(self)
            except RuntimeError:
                pass
        self._widget = None

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is self._widget and ev.type() == QEvent.Type.Move:
            p = ev.pos()
            self.mover(p.x(), p.y())
        return False

    # ── Estado ──
    @property
    def activo(self) -> bool:
        """¿Corre el temporizador?"""
        return self._timer.isActive()

    @property
    def arrastrando(self) -> bool:
        return self._arrastrando

    @property
    def habilitado(self) -> bool:
        return self._habilitado

    def set_habilitado(self, on: bool) -> None:
        """Apagado (modo juego, vídeo en pantalla, ajuste desactivado): recta y quieta."""
        on = bool(on)
        if on == self._habilitado:
            return
        self._habilitado = on
        if not on:
            self.detener()

    def detener(self) -> None:
        """Para el temporizador y la deja recta (emite 0.0 y fin de arrastre si hacía falta)."""
        self._timer.stop()
        self.fisica.reiniciar()
        if self._widget is not None:
            try:
                self.fisica.saltar(self._widget.x(), self._widget.y(), self._reloj())
            except Exception:
                pass
        self.clasificador.reiniciar()
        self.detector_mareo.reiniciar()
        if self._ultimo != 0.0:
            self._ultimo = 0.0
            self.angulo.emit(0.0)
        self._fin_arrastre()

    # ── Entrada ──
    def mover(self, x: float, y: float) -> None:
        """La ventana está en (x, y) (px lógicos). Llamar en cada moveEvent."""
        if not self._habilitado:
            return
        t = self._reloj()
        if not self.fisica.mover(x, y, t):
            return
        f = self.fisica
        if not self._arrastrando and f.rapidez >= V_ARRANQUE:
            self._arrastrando = True
            self.movimiento.emit(True)
            self._set_cara(self.clasificador.actualizar(f.rapidez, t))
        if self.detector_mareo.actualizar(f.vx_inst, f.vy_inst, t):
            self.mareo.emit()
        if not self._timer.isActive():
            self._timer.start()

    def saltar(self, x: float, y: float) -> None:
        """Colocación por código: nueva referencia sin balanceo."""
        self.fisica.saltar(x, y, self._reloj())

    # ── Internos ──
    def _set_cara(self, cara: str) -> None:
        if cara != self._cara:
            self._cara = cara
            self.cara.emit(cara)

    def _fin_arrastre(self) -> None:
        if self._arrastrando:
            self._arrastrando = False
            self.clasificador.reiniciar()
            self._set_cara("")
            self.movimiento.emit(False)

    def _tick(self) -> None:
        t = self._reloj()
        f = self.fisica
        a = f.paso(t)
        if self._arrastrando:
            quieta = (t - f.t_ultimo_mov) > self.fin_s
            pulsado = False
            if quieta and self._boton is not None:
                try:
                    pulsado = bool(self._boton())
                except Exception:
                    pulsado = False
            if quieta and not pulsado:
                self._fin_arrastre()
            else:
                self._set_cara(self.clasificador.actualizar(0.0 if quieta else f.rapidez, t))
        if abs(a - self._ultimo) >= 0.02 or (a == 0.0 and self._ultimo != 0.0):
            self._ultimo = a
            self.angulo.emit(a)
        if f.reposo and not self._arrastrando:
            self._timer.stop()


class RespiracionSpriteQt(QObject):
    """`RespiracionSprite` con un QTimer de 10 Hz; `dy(int)` solo cuando cambia el píxel.

        resp = RespiracionSpriteQt(ventana)
        resp.dy.connect(...)
        resp.iniciar()              # detener() en modo juego u oculta
        resp.set_dormida(True)      # más lenta y honda
    """

    dy = pyqtSignal(int)

    def __init__(self, parent: Optional[QObject] = None, *, respiracion: Optional[RespiracionSprite] = None,
                 reloj: Callable[[], float] = time.monotonic, hz: int = HZ_RESPIRACION,
                 rng: Optional[random.Random] = None):
        super().__init__(parent)
        self._reloj = reloj
        self.respiracion = respiracion if respiracion is not None else RespiracionSprite(rng=rng, t0=reloj())
        self._ultimo: Optional[int] = None
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(round(1000 / max(1, hz)))))
        self._timer.timeout.connect(self._tick)

    @property
    def activo(self) -> bool:
        return self._timer.isActive()

    def iniciar(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self._tick()

    def detener(self) -> None:
        """Para y la deja en su sitio (emite 0 si hacía falta)."""
        self._timer.stop()
        if self._ultimo not in (None, 0):
            self._ultimo = 0
            self.dy.emit(0)

    def set_dormida(self, dormida: bool) -> None:
        self.respiracion.set_dormida(dormida, self._reloj())

    def _tick(self) -> None:
        v = self.respiracion.dy_px(self._reloj())
        if v != self._ultimo:
            self._ultimo = v
            self.dy.emit(v)


__all__ = (
    "GANANCIA", "F_HZ", "ZETA", "TOPE_GRADOS", "PIVOTE", "UMBRALES_VELOCIDAD", "CARAS_VELOCIDAD",
    "CARA_SPRITE", "FisicaSprite", "ClasificadorVelocidad", "DetectorMareo", "RespiracionSprite",
    "lado_mirada", "margen_lienzo", "recortar_fondo", "region_silueta", "SpriteRotado",
    "FisicaSpriteQt", "RespiracionSpriteQt",
)
