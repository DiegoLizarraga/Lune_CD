"""
Tests de nucleo/fisica: SmoothDamp de Unity, el muelle amortiguado y los
suavizados. Sin pantalla: son cuentas.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import fisica as F  # noqa: E402


# ── smooth_damp ──────────────────────────────────────────────────────────────────
def test_smooth_damp_un_paso_contra_valores_de_referencia():
    """Un paso calculado a mano con la fórmula de Mathf.SmoothDamp.

    ω = 2/0.3, x = ω/60, exp = 1/(1 + x + 0.48x² + 0.235x³) = 0.894967
    temp = −ω·10/60 = −1.11111 → vel = ω·1.11111·exp = 6.62939
    salida = 10 − 11.11111·exp = 0.055920
    """
    x, v = F.smooth_damp(0.0, 10.0, 0.0, 0.3, math.inf, 1 / 60)
    assert x == pytest.approx(0.055920, abs=1e-5)
    assert v == pytest.approx(6.629387, abs=1e-5)


def test_smooth_damp_tras_smooth_time_va_por_el_59_por_ciento():
    """Críticamente amortiguado con ω = 2/T: en t = T lleva 1 − 3e⁻² ≈ 59.4 %."""
    x, v = 0.0, 0.0
    for _ in range(60):                       # 1 s a 60 fps con T = 1 s
        x, v = F.smooth_damp(x, 1.0, v, 1.0, math.inf, 1 / 60)
    assert x == pytest.approx(1 - 3 * math.exp(-2), abs=0.01)


@pytest.mark.parametrize("dt", [1 / 144, 1 / 60, 1 / 30, 1 / 10])
def test_smooth_damp_no_sobrepasa_y_converge(dt):
    x, v = 0.0, 0.0
    maximo = 0.0
    for _ in range(int(3.0 / dt)):
        x, v = F.smooth_damp(x, 100.0, v, 0.25, math.inf, dt)
        maximo = max(maximo, x)
    assert maximo <= 100.0
    assert x == pytest.approx(100.0, abs=0.01)


def test_smooth_damp_hacia_abajo_tampoco_sobrepasa():
    x, v = 50.0, 0.0
    minimo = x
    for _ in range(300):
        x, v = F.smooth_damp(x, -20.0, v, 0.2, math.inf, 1 / 60)
        minimo = min(minimo, x)
    assert minimo >= -20.0
    assert x == pytest.approx(-20.0, abs=1e-3)


def test_smooth_damp_con_velocidad_inicial_contraria_no_se_pasa():
    """Aunque venga lanzado hacia el objetivo, se planta en él sin cruzarlo."""
    x, v = 0.0, 500.0
    for _ in range(300):
        x, v = F.smooth_damp(x, 10.0, v, 0.3, math.inf, 1 / 60)
        assert x <= 10.0
    assert x == pytest.approx(10.0, abs=1e-3)


def test_smooth_damp_respeta_la_velocidad_maxima():
    x, v = 0.0, 0.0
    for _ in range(60):                       # 1 s con tope de 2 unidades/s
        x, v = F.smooth_damp(x, 1000.0, v, 0.1, 2.0, 1 / 60)
    assert x <= 2.0 + 1e-9
    assert x > 1.5


def test_smooth_damp_dt_cero_no_hace_nada():
    assert F.smooth_damp(3.0, 10.0, 1.5, 0.3, math.inf, 0.0) == (3.0, 1.5)


def test_smooth_damp_2d_no_va_mas_rapido_en_diagonal():
    """Con tope de velocidad, en diagonal recorre lo mismo que en recto."""
    recto = diag = (0.0, 0.0)
    vr = vd = (0.0, 0.0)
    for _ in range(30):
        recto, vr = F.smooth_damp_2d(recto, (1000.0, 0.0), vr, 0.1, 100.0, 1 / 60)
        diag, vd = F.smooth_damp_2d(diag, (1000.0, 1000.0), vd, 0.1, 100.0, 1 / 60)
    assert math.hypot(*diag) == pytest.approx(recto[0], rel=1e-6)


def test_smooth_damp_2d_coincide_con_el_escalar_en_un_eje():
    p, v = (0.0, 5.0), (0.0, 0.0)
    x, vx = 0.0, 0.0
    for _ in range(40):
        p, v = F.smooth_damp_2d(p, (80.0, 5.0), v, 0.3, math.inf, 1 / 60)
        x, vx = F.smooth_damp(x, 80.0, vx, 0.3, math.inf, 1 / 60)
        assert p[0] == pytest.approx(x, abs=1e-9)
        assert p[1] == 5.0


def test_smooth_damp_2d_converge_sin_pasarse():
    p, v = (0.0, 0.0), (0.0, 0.0)
    for _ in range(400):
        p, v = F.smooth_damp_2d(p, (300.0, -120.0), v, 0.2, math.inf, 1 / 60)
        assert p[0] <= 300.0 and p[1] >= -120.0
    assert p[0] == pytest.approx(300.0, abs=1e-3)
    assert p[1] == pytest.approx(-120.0, abs=1e-3)


# ── Muelle ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("f_hz, dt", [(0.75, 1 / 30), (2.6, 1 / 60), (1.5, 1 / 144)])
def test_muelle_zeta_035_sobrepasa_un_31_por_ciento(f_hz, dt):
    m = F.Muelle(f_hz, 0.35)
    pico = max(m.paso(1.0, dt) for _ in range(int(4.0 / dt)))
    assert pico - 1.0 == pytest.approx(0.31, abs=0.02)
    assert F.sobrepaso_teorico(0.35) == pytest.approx(0.309, abs=1e-3)


def test_muelle_critico_no_sobrepasa_y_llega():
    m = F.Muelle(2.0, 1.0)
    valores = [m.paso(1.0, 1 / 60) for _ in range(240)]
    assert max(valores) <= 1.0 + 1e-6
    assert valores[-1] == pytest.approx(1.0, abs=1e-3)


def test_muelle_resultado_independiente_de_los_fps():
    """Con subpasos de ≤ 1/120 s, 30 fps y 144 fps dan casi lo mismo."""
    a, b = F.Muelle(0.75, 0.5), F.Muelle(0.75, 0.5)
    for _ in range(30):
        xa = a.paso(1.0, 1 / 30)
    for _ in range(144):
        xb = b.paso(1.0, 1 / 144)
    assert xa == pytest.approx(xb, abs=0.01)


def test_muelle_dt_enorme_no_diverge_ni_se_congela():
    m = F.Muelle(2.6, 0.35)
    x = m.paso(1.0, 3600.0)                   # una hora de suspensión
    assert math.isfinite(x) and math.isfinite(m.v)
    assert abs(x - 1.0) < 1.0


def test_muelle_parametros_extremos_siguen_estables():
    m = F.Muelle(60.0, 3.0)                   # muy rígido y muy amortiguado
    for _ in range(120):
        x = m.paso(5.0, 1 / 60)
        assert math.isfinite(x)
    assert x == pytest.approx(5.0, abs=1e-3)


@pytest.mark.parametrize("malo", [float("nan"), float("inf"), -float("inf")])
def test_muelle_ignora_objetivo_o_dt_no_validos(malo):
    m = F.Muelle(1.0, 0.5, x=2.0)
    assert m.paso(malo, 1 / 60) == 2.0
    assert m.paso(1.0, malo) == 2.0
    assert m.paso(1.0, -0.1) == 2.0
    assert math.isfinite(m.v)


def test_muelle_si_revienta_se_planta_en_el_objetivo():
    m = F.Muelle(1.0, 0.5)
    m.v = float("inf")                        # estado corrompido desde fuera
    assert m.paso(3.0, 1 / 60) == 3.0
    assert m.v == 0.0


def test_muelle_tope_recorta():
    m = F.Muelle(3.0, 0.2, tope=90)
    for _ in range(120):
        assert abs(m.paso(500.0, 1 / 60)) <= 90


def test_muelle_reiniciar():
    m = F.Muelle(1.0, 0.5)
    m.paso(10.0, 0.5)
    m.reiniciar(4.0)
    assert (m.x, m.v) == (4.0, 0.0)


# ── smoothstep, suav ─────────────────────────────────────────────────────────────
def test_smoothstep():
    assert F.smoothstep(0, 1, -1) == 0.0
    assert F.smoothstep(0, 1, 0.5) == 0.5
    assert F.smoothstep(0, 1, 2) == 1.0
    assert F.smoothstep(0, 1, 0.25) == pytest.approx(0.15625)
    assert F.smoothstep(10, 20, 15) == 0.5
    assert F.smoothstep(1, 0, 0.25) == pytest.approx(1 - 0.15625)   # bordes invertidos
    assert F.smoothstep(2, 2, 1.9) == 0.0 and F.smoothstep(2, 2, 2) == 1.0


def test_suav_es_independiente_de_los_fps():
    """Aplicar suav a 30 fps durante 1 s deja lo mismo que a 144 fps."""
    def filtrar(fps):
        x = 0.0
        for _ in range(fps):
            x += (1.0 - x) * F.suav(1 / fps, 5.0)
        return x
    assert filtrar(30) == pytest.approx(filtrar(144), abs=1e-9)
    assert filtrar(60) == pytest.approx(1 - math.exp(-5.0), abs=1e-9)


def test_suav_bordes():
    assert F.suav(0.0, 10.0) == 0.0
    assert F.suav(-1.0, 10.0) == 0.0
    assert F.suav(0.1, 0.0) == 0.0
    assert F.suav(float("nan"), 1.0) == 0.0
    assert 0.0 < F.suav(1 / 60, 10.0) < 1.0
    assert F.suav(1e6, 10.0) == pytest.approx(1.0)


def test_clamp_y_lerp():
    assert F.clamp(5, 0, 3) == 3 and F.clamp(-1, 0, 3) == 0 and F.clamp(2, 0, 3) == 2
    assert F.lerp(10, 20, 0.25) == 12.5
