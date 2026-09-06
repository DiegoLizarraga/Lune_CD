"""
Tests de la mascota flotante (avatar_overlay.py).

No se puede verificar lo visual (transparencia, siempre-encima) sin pantalla,
pero sí la construcción, las banderas de ventana, el mapeo de emoción y la
persistencia de posición.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def overlay(qapp):
    from avatar_overlay import AvatarOverlay
    ov = AvatarOverlay(config=None)
    yield ov
    ov.close()


def test_banderas_de_ventana(overlay):
    from PyQt6.QtCore import Qt
    flags = overlay.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.Tool
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_emocion_mueve_la_cara(overlay):
    overlay.set_emocion("happy")
    assert overlay.cara._current_state == "happy"
    overlay.set_emocion("angry")     # angry → error en el mapa de la cara
    assert overlay.cara._current_state == "error"
    overlay.set_emocion("neutral")
    assert overlay.cara._current_state == "normal"


def test_estado_directo(overlay):
    overlay.set_estado("thinking")
    assert overlay.cara._current_state == "thinking"


def test_persistencia_de_posicion(qapp, tmp_path):
    from avatar_overlay import AvatarOverlay
    from config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))

    ov = AvatarOverlay(config=cfg)
    ov.move(300, 200)
    ov._guardar_posicion()
    assert cfg.get("avatar", "overlay_x") == 300
    assert cfg.get("avatar", "overlay_y") == 200
    ov.close()

    # una nueva mascota restaura esa posición
    ov2 = AvatarOverlay(config=cfg)
    assert (ov2.x(), ov2.y()) == (300, 200)
    ov2.close()


def test_posicion_fuera_de_pantalla_se_ignora(qapp, tmp_path):
    from avatar_overlay import AvatarOverlay
    from config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "overlay_x", 99999)   # fuera de cualquier pantalla
    cfg.set("avatar", "overlay_y", 99999)
    ov = AvatarOverlay(config=cfg)
    # no queda en la posición absurda: cae a la esquina
    assert ov.x() < 99999
    ov.close()
