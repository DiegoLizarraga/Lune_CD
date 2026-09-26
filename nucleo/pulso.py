"""
nucleo/pulso.py — El pulso de la música (BPM y fase) a partir del medidor de pico.

Lo único que Lune sabe de la música del PC es el PICO de la sesión de audio de la
app que suena, leído ~50 veces por segundo (servicios/audio_sesiones.py; sin
capturar audio, decisión D4). Con eso basta para seguir el golpe:

1. Fuerza de inicio: la diferencia POSITIVA del logaritmo de la envolvente (un
   golpe de bombo es un salto brusco hacia arriba; la caída no cuenta).
2. Cada 0.5 s, autocorrelación de esa fuerza sobre los últimos 8 s, entre 70 y
   180 BPM, con un pequeño empujón hacia 120 (lo que suele bailarse).
3. Afinado del periodo con la transformada de las fuerzas en sus instantes
   reales (no hace falta que las lecturas lleguen a ritmo exacto) y corrección
   de octava hacia 90–150 BPM si el doble o la mitad también encaja.
4. Fase: la del primer armónico en el periodo elegido (dónde caen los golpes).
5. Con confianza baja se mantiene el último BPM (o 120).

Es la ÚNICA fuente del pulso: VRM, animada, sprites, barra web y patata reciben
`Pulso(bpm, fase, energia, confianza, t)` como mucho 2 veces por segundo y
extrapolan la fase con su propio reloj (`Pulso.fase_en(t)`).

Sin Qt; numpy.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional, Tuple

import numpy as np

EPS_LOG = 1e-3            # suelo del logaritmo (el pico va de 0 a 1)
SILENCIO = 0.004          # por debajo de esto (máximo de la ventana) no hay música


@dataclass(frozen=True)
class Pulso:
    """El pulso en el instante `t`: `fase` 0..1 (0 = en el golpe), `energia` 0..1."""
    bpm: float
    fase: float
    energia: float
    confianza: float
    t: float

    @property
    def periodo(self) -> float:
        return 60.0 / self.bpm if self.bpm > 0 else 0.5

    def fase_en(self, t: float) -> float:
        """La fase extrapolada al instante `t` (mismo reloj que `self.t`)."""
        return (self.fase + (t - self.t) * self.bpm / 60.0) % 1.0

    def golpes_en(self, t: float) -> float:
        """Golpes transcurridos desde `self.t` hasta `t` más la fase inicial (continuo)."""
        return self.fase + (t - self.t) * self.bpm / 60.0

    def a_dict(self) -> dict:
        """Lo que se manda a las páginas: {bpm, fase, energia}."""
        return {"bpm": round(float(self.bpm), 2), "fase": round(float(self.fase), 4),
                "energia": round(float(self.energia), 3)}


def metronomo(bpm: float = 120.0, t0: float = 0.0, energia: float = 0.6) -> Callable[[float], Pulso]:
    """Pulso fijo (baile manual sin música): `fn(t) -> Pulso` con el golpe en `t0`."""
    b = float(bpm) if bpm and bpm > 0 else 120.0

    def fn(t: float) -> Pulso:
        return Pulso(b, ((t - t0) * b / 60.0) % 1.0, float(energia), 1.0, float(t))
    return fn


def _prior(bpm: float) -> float:
    """Empujón suave hacia 120 BPM (log-gaussiana de una octava)."""
    return math.exp(-0.5 * (math.log2(max(1e-6, bpm) / 120.0)) ** 2)


class SeguidorPulso:
    """Sigue BPM y fase alimentado con picos (`alimentar(pico, t)`, ~50 Hz).

        s = SeguidorPulso()
        s.alimentar(0.42, t)         # cada lectura del medidor
        p = s.estimar(t)             # recalcula como mucho cada CADA_S; si no, extrapola
    """

    HZ = 50
    VENTANA_S = 8.0
    BPM_MIN, BPM_MAX = 70, 180
    BPM_DEFECTO = 120.0
    CADA_S = 0.5
    CONF_MIN = 0.3
    MIN_DATOS_S = 3.0
    RANGO_PREFERIDO = (90.0, 150.0)
    RES_AC = 4               # la rejilla de la autocorrelación es RES_AC veces más fina que hz
    SIGMA_S = 0.010          # cada golpe se reparte con una gaussiana de 10 ms (media lectura)

    def __init__(self, *, hz: int = HZ, ventana_s: float = VENTANA_S):
        self.hz = int(hz)
        self.ventana_s = float(ventana_s)
        self._muestras: Deque[Tuple[float, float]] = deque()
        self.reiniciar()

    def reiniciar(self) -> None:
        self._muestras.clear()
        self._bpm = self.BPM_DEFECTO
        self._t_golpe: Optional[float] = None       # instante de un golpe (referencia de fase)
        self._conf = 0.0
        self._energia = 0.0
        self._t_calc: Optional[float] = None

    # ── Entrada ──────────────────────────────────────────────────────────────────
    def alimentar(self, pico: float, t: float) -> None:
        try:
            p = float(pico)
        except (TypeError, ValueError):
            return
        if not math.isfinite(p):
            return
        p = 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)
        t = float(t)
        if self._muestras and t <= self._muestras[-1][0]:
            return                                    # reloj que no avanza: se ignora
        self._muestras.append((t, p))
        limite = t - self.ventana_s - 1.0
        while self._muestras and self._muestras[0][0] < limite:
            self._muestras.popleft()

    # ── Salida ───────────────────────────────────────────────────────────────────
    @property
    def bpm(self) -> float:
        return self._bpm

    @property
    def confianza(self) -> float:
        return self._conf

    def estimar(self, t: float) -> Pulso:
        """El pulso en `t`. Recalcula si han pasado CADA_S desde el último cálculo."""
        t = float(t)
        if self._t_calc is None or t - self._t_calc >= self.CADA_S or t < self._t_calc:
            self._calcular(t)
        periodo = 60.0 / self._bpm
        if self._t_golpe is None:
            fase = 0.0
        else:
            fase = ((t - self._t_golpe) / periodo) % 1.0
        return Pulso(float(self._bpm), float(fase), float(self._energia), float(self._conf), t)

    # ── Cálculo ──────────────────────────────────────────────────────────────────
    def _ventana(self, t: float):
        datos = [(ti, pi) for ti, pi in self._muestras if t - self.ventana_s <= ti <= t]
        if len(datos) < 3:
            return None, None
        arr = np.asarray(datos, dtype=float)
        return arr[:, 0], arr[:, 1]

    def _calcular(self, t: float) -> None:
        self._t_calc = t
        ts, ps = self._ventana(t)
        if ts is None or float(ps.max()) < SILENCIO:
            self._conf = 0.0
            self._energia = 0.0
            return
        self._energia = self._medir_energia(ts, ps, t)
        if ts[-1] - ts[0] < self.MIN_DATOS_S:
            self._conf = 0.0
            return
        # Suelo del logaritmo relativo al nivel de la ventana: el ruido de fondo,
        # comprimido, no se confunde con golpes (sus saltos quedan pequeños).
        suelo = max(EPS_LOG, 0.1 * float(np.percentile(ps, 95)))
        le = np.log(ps + suelo)
        fuerza = np.maximum(0.0, np.diff(le))
        t_ini = 0.5 * (ts[1:] + ts[:-1])              # el golpe cayó entre las dos lecturas
        if float(fuerza.sum()) <= 1e-9:
            self._conf = 0.0
            return
        res = self._tempo(fuerza, t_ini, t)
        if res is None:
            self._conf = 0.0
            return
        bpm, conf, t_golpe = res
        if conf < self.CONF_MIN:
            self._conf = conf
            return                                    # se mantiene el último BPM y su fase
        self._bpm = float(bpm)
        self._conf = float(conf)
        self._t_golpe = float(t_golpe)

    def _medir_energia(self, ts, ps, t: float) -> float:
        reciente = ps[ts >= t - 1.5]
        if reciente.size == 0:
            return 0.0
        nivel = float(np.percentile(reciente, 80))
        ref = max(0.02, float(np.percentile(ps, 95)))
        if nivel < SILENCIO:
            return 0.0
        return float(min(1.0, max(0.0, 0.25 + 0.75 * nivel / ref)))

    def _autocorrelacion(self, fuerza, t_ini, t: float):
        """Autocorrelación de la fuerza de inicio en una rejilla fina y uniforme.

        Cada inicio se suma en su instante real y se suaviza con una gaussiana: así
        un periodo que no cae en un número entero de lecturas (170 BPM a 50 Hz son
        17.6) no se reparte entre dos retardos. Devuelve (ac, res) con ac[L] el
        retardo L/res segundos."""
        res = self.hz * self.RES_AC
        t0 = t - self.ventana_s
        n = int(math.ceil(self.ventana_s * res)) + 1
        idx = np.rint((t_ini - t0) * res).astype(int)
        ok = (idx >= 0) & (idx < n)
        rej = np.bincount(idx[ok], weights=fuerza[ok], minlength=n)[:n]
        sig = max(0.5, self.SIGMA_S * res)
        k = np.arange(-int(3 * sig) - 1, int(3 * sig) + 2)
        nucleo = np.exp(-0.5 * (k / sig) ** 2)
        x = np.convolve(rej, nucleo / nucleo.sum(), mode="same")
        x = x - x.mean()
        maxlag = min(n - 2, int(math.ceil(2 * res * 60.0 / self.BPM_MIN)) + 4)
        tam = 1 << int(math.ceil(math.log2(2 * n)))
        f = np.fft.rfft(x, tam)
        ac = np.fft.irfft(f * np.conj(f), tam)[:maxlag + 1] / n
        return ac, res

    @staticmethod
    def _ac_en(ac, lag: float) -> float:
        """Autocorrelación interpolada en un retardo fraccionario."""
        if lag < 0 or lag > len(ac) - 1:
            return 0.0
        i = int(math.floor(lag))
        f = lag - i
        if i + 1 >= len(ac):
            return float(ac[i])
        return float(ac[i] * (1 - f) + ac[i + 1] * f)

    def _tempo(self, fuerza, t_ini, t: float):
        ac, hz = self._autocorrelacion(fuerza, t_ini, t)
        if ac[0] <= 1e-12:
            return None
        l_min = max(2, int(math.floor(hz * 60.0 / self.BPM_MAX)))
        l_max = min(len(ac) - 2, int(math.ceil(hz * 60.0 / self.BPM_MIN)))
        if l_max <= l_min:
            return None
        mejor, mejor_s = None, -np.inf
        for L in range(l_min, l_max + 1):
            # El doble del periodo también tiene que encajar: así un tempo rápido no
            # se confunde con su mitad (y al revés, la mitad no gana sin sus golpes).
            s = (ac[L] + 0.5 * self._ac_en(ac, 2.0 * L)) * _prior(60.0 * hz / L)
            if s > mejor_s and ac[L] >= ac[L - 1] and ac[L] >= ac[L + 1]:
                mejor, mejor_s = L, s
        if mejor is None:
            return None
        # Refinado parabólico del retardo.
        a, b, c = ac[mejor - 1], ac[mejor], ac[mejor + 1]
        den = a - 2 * b + c
        lag = mejor + (0.5 * (a - c) / den if den < 0 else 0.0)
        acn = max(0.0, min(1.0, self._ac_en(ac, lag) / ac[0]))
        periodo = lag / hz
        # Afinado con la transformada en los instantes reales (4 armónicos).
        periodo = self._afinar(fuerza, t_ini - t, periodo)
        bpm = 60.0 / periodo
        # Corrección de octava: fuera de 90–150, si el doble o la mitad encaja casi igual.
        lo, hi = self.RANGO_PREFERIDO
        if not (lo <= bpm <= hi):
            ref = self._ac_en(ac, hz * periodo)
            for f in (2.0, 0.5):
                alt = bpm * f
                if self.BPM_MIN <= alt <= self.BPM_MAX and lo <= alt <= hi:
                    if self._ac_en(ac, hz * 60.0 / alt) >= 0.5 * ref:
                        bpm = alt
                        periodo = 60.0 / bpm
                        break
        bpm = min(float(self.BPM_MAX), max(float(self.BPM_MIN), bpm))
        periodo = 60.0 / bpm
        # Fase: primer armónico, con los golpes fuertes pesando más (fuerza²).
        rel = t_ini - t
        w = fuerza * fuerza
        z = complex(np.sum(w * np.exp(-2j * np.pi * rel / periodo)))
        coh = abs(z) / max(1e-12, float(w.sum()))
        t_golpe = t + (-math.atan2(z.imag, z.real) / (2 * math.pi)) * periodo
        conf = max(0.0, min(1.0, math.sqrt(acn * min(1.0, 1.5 * coh))))
        return bpm, conf, t_golpe

    @staticmethod
    def _afinar(fuerza, rel, periodo: float) -> float:
        """El periodo (±4 %) que más concentra la fuerza en fase (suma de 4 armónicos)."""
        cands = periodo * np.linspace(0.96, 1.04, 81)
        fases = -2j * np.pi * rel[None, :] / cands[:, None]
        score = np.zeros(len(cands))
        for h in (1, 2, 3, 4):
            score += np.abs((fuerza[None, :] * np.exp(fases * h)).sum(axis=1))
        return float(cands[int(np.argmax(score))])


__all__ = ("Pulso", "SeguidorPulso", "metronomo", "SILENCIO")
