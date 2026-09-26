"""
Tests de la geometría pura del menú radial (ui/menu_radial.py): índice por
ángulo con zona muerta, posición de los iconos y lerps normalizados por dt.

Convención (la de CircleSelector de Mate-Engine y la que debe seguir
window.LuneRadial.indice en la web): ángulo en sentido HORARIO desde las 12 con
y de pantalla hacia abajo; el botón i ocupa [i·360/n, (i+1)·360/n) y su icono va
en el centro del sector; zona muerta = distancia <= 85 px.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from ui.menu_radial import (RADIO_ICONOS, ZONA_MUERTA, angulo, centro_sector, factor_lerp,  # noqa: E402
                            indice, posiciones)


def punto(grados, radio=120.0):
    a = math.radians(grados)
    return radio * math.sin(a), -radio * math.cos(a)


def test_angulo_horario_desde_las_12():
    assert angulo(0, -10) == pytest.approx(0)          # arriba
    assert angulo(10, 0) == pytest.approx(90)          # derecha (las 3)
    assert angulo(0, 10) == pytest.approx(180)         # abajo
    assert angulo(-10, 0) == pytest.approx(270)        # izquierda
    assert 0 <= angulo(-1e-12, -10) < 360


@pytest.mark.parametrize("n", range(1, 11))
def test_indice_en_el_centro_de_cada_boton(n):
    for i in range(n):
        dx, dy = punto(centro_sector(i, n))
        assert indice(dx, dy, n) == i


@pytest.mark.parametrize("n", range(2, 11))
def test_fronteras_entre_botones(n):
    sector = 360.0 / n
    for i in range(n):
        antes = punto(i * sector - 0.2)
        despues = punto(i * sector + 0.2)
        assert indice(*despues, n) == i
        assert indice(*antes, n) == (i - 1) % n


def test_tabla_n4():
    # las 12 → 0, las 3 → 1, las 6 → 2, las 9 → 3
    assert [indice(0, -100, 4), indice(100, 0, 4), indice(0, 100, 4), indice(-100, 0, 4)] == [0, 1, 2, 3]
    assert indice(70, -70, 4) == 0 and indice(70, 70, 4) == 1
    assert indice(-70, 70, 4) == 2 and indice(-70, -70, 4) == 3


def test_zona_muerta():
    assert indice(0, 0, 5) is None
    assert indice(0, -ZONA_MUERTA, 5) is None                 # en el borde: todavía muerta
    assert indice(0, -(ZONA_MUERTA + 0.01), 5) == 0
    assert indice(30, 40, 5) is None                          # 50 px
    assert indice(0, -60, 5, zona_muerta=50) == 0             # zona muerta configurable
    assert indice(0, -5000, 5) == 0                           # sin límite exterior (como ME)


def test_n_invalido_y_un_solo_boton():
    assert indice(100, 0, 0) is None
    assert indice(100, 0, -3) is None
    assert indice(100, 0, "x") is None
    for g in (0, 90, 180, 270, 359.9):
        assert indice(*punto(g), 1) == 0


@pytest.mark.parametrize("n", range(1, 11))
def test_posiciones(n):
    ps = posiciones(n)
    assert len(ps) == n
    for i, (x, y) in enumerate(ps):
        assert math.hypot(x, y) == pytest.approx(RADIO_ICONOS)
        assert indice(x, y, n) == i
    assert posiciones(0) == []


def test_factor_lerp_normalizado_por_dt():
    assert factor_lerp(0.2, 1 / 60) == pytest.approx(0.2)
    assert factor_lerp(0.54, 1 / 60) == pytest.approx(0.54)
    # dos frames de 60 fps = un frame de 30 fps
    uno = factor_lerp(0.2, 1 / 60)
    assert factor_lerp(0.2, 2 / 60) == pytest.approx(1 - (1 - uno) ** 2)
    assert factor_lerp(0.2, 0) == 0
    assert factor_lerp(0.2, -1) == 0
    assert factor_lerp(1.0, 1 / 60) == 1.0
    assert 0 <= factor_lerp(0.9, 10) <= 1
    assert factor_lerp(5, 1 / 60) == 1.0


# Misma tabla que tests/js/radial_web.test.mjs (window.LuneRadial.indice de la web).
_S = lambda g, r: (math.sin(math.radians(g)) * r, -math.cos(math.radians(g)) * r)  # noqa: E731
TABLA_PARIDAD = [
    (0, -100, 4, 0), (100, 0, 4, 1), (0, 100, 4, 2), (-100, 0, 4, 3),
    (1, -100, 4, 0), (-1, -100, 4, 3), (100, -1, 4, 0), (100, 1, 4, 1),
    (0, -85, 4, None), (0, -85.01, 4, 0), (60, 60, 4, None), (0, 0, 1, None),
    (0, -200, 1, 0), (0, 200, 1, 0), (-5, 300, 1, 0),
    (0, -500, 0, None), (0, -500, -3, None),
    (0, -120, 3, 0), (120, 70, 3, 1), (-120, 70, 3, 1), (-120, 40, 3, 2),
    (*_S(35.9, 120), 10, 0), (*_S(36.1, 120), 10, 1), (*_S(359.5, 120), 10, 9),
    (*_S(179.9, 90), 2, 0), (*_S(180.1, 90), 2, 1),
    (1e6, 1e6, 8, 3), (0, -100, 2.7, 0), (-0.0, -100, 4, 0),
]


@pytest.mark.parametrize("dx,dy,n,esperado", TABLA_PARIDAD)
def test_paridad_con_la_web(dx, dy, n, esperado):
    assert indice(dx, dy, n) == esperado


def test_valores_raros():
    assert indice(float("nan"), 5, 4) is None
    assert indice(float("inf"), 5, 4) is None
    assert indice("x", 5, 4) is None
    assert indice(0, -100, 4, 150) is None
