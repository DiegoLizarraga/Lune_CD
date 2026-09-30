"""
Tests de ui/sprites_baile: el baile de la asistente de sprites. Giro ±4° y
saltitos acotados en los 8 estilos, el temporizador de 30 Hz solo mientras
baila, fundidos, el arrastre que corta y el reloj que sigue el pulso
(corrección ≤ 20 % por pulso). Reloj falso y `_tick()` a mano.
"""
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.baile import ESTILOS  # noqa: E402
from ui.sprites_baile import DY_ABAJO, DY_MAX, TOPE_GRADOS, BaileSprite  # noqa: E402


class Reloj:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("estilo", ESTILOS)
def test_estilos_acotados_y_que_se_mueven(estilo):
    b = BaileSprite()
    vistos = set()
    for k in range(400):
        fase = (k * 0.037) % 1.0
        for e in (0.0, 0.5, 1.0, 7.0, float("nan")):
            g, dy = b.paso(fase, e, k * 0.02, estilo)
            assert math.isfinite(g) and -TOPE_GRADOS <= g <= TOPE_GRADOS
            assert isinstance(dy, int) and -DY_MAX <= dy <= DY_ABAJO
            vistos.add((round(g, 1), dy))
    assert len(vistos) > 5, "el estilo tiene que moverse"


def test_estilo_desconocido_es_rebote_y_cuenta_golpes():
    b = BaileSprite()
    assert b.paso(0.5, 1.0, 0, "no_existe") == BaileSprite().paso(0.5, 1.0, 0, "rebote")
    for f in (0.1, 0.6, 0.9, 0.05, 0.5, 0.95, 0.02):
        b.paso(f, 1.0, 0, "vaiven")
    assert b.golpes == 2


def test_vaiven_alterna_de_lado_en_cada_golpe():
    b = BaileSprite()
    g1, _ = b.paso(0.5, 1.0, 0, "puno_alterno")
    b.paso(0.99, 1.0, 0, "puno_alterno")
    g2, _ = b.paso(0.01, 1.0, 0, "puno_alterno")
    g3, _ = BaileSprite().paso(0.01, 1.0, 0, "puno_alterno")
    assert g2 * g3 < 0                                   # el segundo golpe va al otro lado


@pytest.fixture
def baile(qapp):
    from ui.sprites_baile import BaileSpriteQt
    reloj = Reloj()
    b = BaileSpriteQt(reloj=reloj, rng=random.Random(3))
    b.cuadros = []
    b.cuadro.connect(lambda g, dy: b.cuadros.append((g, dy)))
    b.reloj = reloj
    yield b
    b.detener()
    b.deleteLater()


def correr(b, s, paso=1 / 30):
    for _ in range(int(round(s / paso))):
        b.reloj.t += paso
        b._tick()


def test_temporizador_solo_mientras_baila_y_fundidos(baile):
    b = baile
    assert not b.activo
    b.bailar(True, {"estilo": "rebote"})
    assert b.activo and b._timer.interval() == 33
    correr(b, 0.2)
    assert 0.3 < b.peso < 0.7                            # entrando (0.4 s)
    correr(b, 1.0)
    assert b.peso == 1.0
    assert any(dy <= -2 for _, dy in b.cuadros)          # salta
    b.bailar(False)
    assert b.activo                                      # fundido de salida
    correr(b, 0.6)
    assert not b.activo and b.cuadros[-1] == (0.0, 0)    # acabó: recta y quieta


def test_arrastre_corta_en_seco_y_vuelve_con_fundido(baile):
    b = baile
    b.bailar(True, {"estilo": "vaiven"})
    correr(b, 1.0)
    b.set_arrastre(True)
    assert b.peso == 0.0 and b.cuadros[-1] == (0.0, 0)
    correr(b, 0.5)
    assert b.peso == 0.0 and b.cuadros[-1] == (0.0, 0)
    b.set_arrastre(False)
    correr(b, 0.1)
    assert 0.0 < b.peso < 1.0


def test_pulso_salta_la_primera_vez_y_luego_corrige_un_20(baile):
    b = baile
    b.bailar(True, {})
    b.pulso(120.0, 0.25, 0.9)
    assert b._pos(b.reloj.t) % 1.0 == pytest.approx(0.25)   # primer pulso: salta
    b.reloj.t += 0.5                                     # a 120 BPM, un golpe entero
    b.pulso(120.0, 0.35, 0.9)                            # error de +0.10
    assert b._pos(b.reloj.t) % 1.0 == pytest.approx(0.27)   # corrige 0.02 (20 %)
    b.pulso(120.0, 0.9, 0.9)                             # error enorme (otra canción): salta
    assert b._pos(b.reloj.t) % 1.0 == pytest.approx(0.9)
    b.pulso(float("nan"), 0.1, 0.1)                      # basura: se ignora
    assert b._bpm == 120.0


def test_detener_para_sin_fundido(baile):
    b = baile
    b.bailar(True, {})
    correr(b, 1.0)
    b.detener()
    assert not b.activo and not b.bailando and b.cuadros[-1] == (0.0, 0)


def test_cambiar_de_estilo_cada_n_segundos_con_cruce(baile):
    b = baile
    b.bailar(True, {"estilo": "rebote", "cambiar": True, "cambiarS": 5})
    correr(b, 4.9)
    assert b.estilo == "rebote"
    correr(b, 0.2)
    assert b.estilo != "rebote" and b.estilo in ESTILOS and b._estilo_prev == "rebote"
    correr(b, 2.1)
    assert b._estilo_prev is None


def test_nuevas_opciones_mientras_baila_cruzan_de_estilo(baile):
    b = baile
    b.bailar(True, {"estilo": "rebote"})
    correr(b, 0.5)
    b.bailar(True, {"estilo": "palmas"})
    assert b.estilo == "palmas" and b._estilo_prev == "rebote"
