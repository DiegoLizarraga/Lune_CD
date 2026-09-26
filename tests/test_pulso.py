"""
Tests de nucleo/pulso: BPM y fase a partir del medidor de pico (~50 Hz).

Pistas de clics sintéticas a 90, 120 y 150 BPM leídas a 50 Hz con jitter en el
instante de cada lectura y ruido de fondo: ±3 BPM y error de fase < 60 ms.
Silencio → confianza 0 y 120 BPM; ruido → confianza baja.
"""
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.pulso import Pulso, SeguidorPulso, metronomo  # noqa: E402


def pista(bpm, dur=12.0, hz=50, jitter=0.004, ruido=0.05, fase0=0.137, tau=0.08, semilla=1, amp=0.8):
    """[(t, pico)] de una pista de clics con decaimiento exponencial."""
    rng = random.Random(semilla)
    periodo = 60.0 / bpm
    out = []
    for k in range(int(dur * hz)):
        t = k / hz + rng.uniform(-jitter, jitter)
        n = math.floor((t - fase0) / periodo)
        v = ruido * rng.random()
        if n >= 0:
            v += amp * math.exp(-(t - (fase0 + n * periodo)) / tau)
        out.append((t, min(1.0, v)))
    return out, periodo, fase0


def error_fase(p: Pulso, periodo: float, fase0: float) -> float:
    golpe = p.t - p.fase * 60.0 / p.bpm              # el último golpe según el pulso
    n = round((golpe - fase0) / periodo)
    return golpe - (fase0 + n * periodo)


@pytest.mark.parametrize("bpm", [90, 120, 150])
@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_clics_sinteticos_bpm_y_fase(bpm, semilla):
    datos, periodo, fase0 = pista(bpm, semilla=semilla)
    s = SeguidorPulso()
    for t, v in datos:
        s.alimentar(v, t)
    p = s.estimar(datos[-1][0])
    assert abs(p.bpm - bpm) <= 3.0
    assert abs(error_fase(p, periodo, fase0)) < 0.060
    assert p.confianza >= SeguidorPulso.CONF_MIN
    assert 0.0 < p.energia <= 1.0


def test_silencio_confianza_cero_y_120():
    s = SeguidorPulso()
    for k in range(500):
        s.alimentar(0.0, k / 50)
    p = s.estimar(10.0)
    assert p.confianza == 0.0 and p.bpm == 120.0 and p.energia == 0.0


def test_ruido_confianza_baja_y_mantiene_el_ultimo_bpm():
    datos, _, _ = pista(150, semilla=4)
    s = SeguidorPulso()
    for t, v in datos:
        s.alimentar(v, t)
    assert abs(s.estimar(datos[-1][0]).bpm - 150) <= 3
    rng = random.Random(7)
    t0 = datos[-1][0]
    for k in range(1, 600):                          # 12 s de ruido: la ventana de 8 s ya no tiene clics
        s.alimentar(0.2 + 0.3 * rng.random(), t0 + k / 50)
    p = s.estimar(t0 + 12.0)
    assert p.confianza < SeguidorPulso.CONF_MIN
    assert abs(p.bpm - 150) <= 3                     # con confianza baja se queda el último


def test_recalcula_como_mucho_cada_medio_segundo_y_extrapola_la_fase():
    datos, periodo, _ = pista(120)
    s = SeguidorPulso()
    for t, v in datos:
        s.alimentar(v, t)
    t = datos[-1][0]
    p1 = s.estimar(t)
    calc = s._t_calc
    p2 = s.estimar(t + 0.2)
    assert s._t_calc == calc                         # no recalculó
    assert p2.fase == pytest.approx((p1.fase + 0.2 * p1.bpm / 60.0) % 1.0, abs=1e-6)
    assert p1.fase_en(t + 0.2) == pytest.approx(p2.fase, abs=1e-6)


def test_pocos_datos_no_da_confianza():
    datos, _, _ = pista(120, dur=2.0)
    s = SeguidorPulso()
    for t, v in datos:
        s.alimentar(v, t)
    assert s.estimar(2.0).confianza == 0.0


def test_ignora_lecturas_raras_y_reiniciar():
    s = SeguidorPulso()
    s.alimentar(float("nan"), 0.0)
    s.alimentar("x", 0.1)
    s.alimentar(0.5, 1.0)
    s.alimentar(0.6, 0.5)                            # reloj hacia atrás: fuera
    s.alimentar(3.0, 2.0)                            # se acota a 1
    assert list(s._muestras) == [(1.0, 0.5), (2.0, 1.0)]
    s.reiniciar()
    assert not s._muestras and s.bpm == 120.0


def test_metronomo():
    m = metronomo(120.0, t0=10.0)
    assert m(10.0).fase == 0.0 and m(10.25).fase == pytest.approx(0.5)
    assert m(11.0).bpm == 120.0 and m(11.0).confianza == 1.0
    assert metronomo(0)(1.0).bpm == 120.0


def test_pulso_a_dict():
    d = Pulso(123.456, 0.123456, 0.87654, 0.9, 5.0).a_dict()
    assert d == {"bpm": 123.46, "fase": 0.1235, "energia": 0.877}
