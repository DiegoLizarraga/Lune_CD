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
    from ui.avatar_overlay import AvatarOverlay
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
    from ui.avatar_overlay import AvatarOverlay
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))

    ov = AvatarOverlay(config=cfg)
    ov.move(300, 200)
    ov._guardar_posicion()
    # se guarda la posición lógica (la ventana sin el margen de giro, como en la 10.2)
    assert cfg.get("avatar", "overlay_x") == 300 + ov._margen[0]
    assert cfg.get("avatar", "overlay_y") == 200 + ov._margen[1]
    ov.close()

    # una nueva mascota restaura esa posición
    ov2 = AvatarOverlay(config=cfg)
    assert (ov2.x(), ov2.y()) == (300, 200)
    ov2.close()


def test_posicion_fuera_de_pantalla_se_ignora(qapp, tmp_path):
    from ui.avatar_overlay import AvatarOverlay
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "overlay_x", 99999)   # fuera de cualquier pantalla
    cfg.set("avatar", "overlay_y", 99999)
    ov = AvatarOverlay(config=cfg)
    # no queda en la posición absurda: cae a la esquina
    assert ov.x() < 99999
    ov.close()


# ── Silueta por chroma-key (click-through en modo sprites) ──────────────────────

def test_region_silueta_recorta_el_fondo_oscuro(overlay):
    """Un sprite opaco con fondo negro y figura clara → región solo de la figura."""
    from PyQt6.QtGui import QPixmap, QImage, QColor
    from PyQt6.QtCore import QPoint
    w, h = 40, 30
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(2, 2, 2))                       # fondo casi negro (como los PNG reales)
    for y in range(h):                              # barra clara en el centro (cols 15..24)
        for x in range(15, 25):
            img.setPixelColor(x, y, QColor(240, 240, 240))
    region = overlay._region_silueta(QPixmap.fromImage(img))
    assert not region.isEmpty()
    assert region.contains(QPoint(20, 15))          # dentro de la figura
    assert not region.contains(QPoint(2, 15))       # en el fondo, no
    assert region.boundingRect().width() <= 12      # más estrecha que el rectángulo


# ── Modo fantasma (click-through total) ─────────────────────────────────────────

def test_modo_fantasma_persiste_en_config(qapp, tmp_path):
    from ui.avatar_overlay import AvatarOverlay
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    ov = AvatarOverlay(config=cfg)
    ov.set_click_through(True)
    assert ov._click_through is True
    assert cfg.get("avatar", "click_through") is True
    ov.set_click_through(False)
    assert cfg.get("avatar", "click_through") is False
    ov.close()


# ── Misma interfaz que la mascota 3D (ui/companion.py) ───────────────────────────

def test_interfaz_comun_con_el_companion(overlay):
    """El puente y main.py no distinguen sprites de VRM: mismas llamadas y señal."""
    for metodo in ("set_estado", "set_emocion", "set_act", "set_hablando", "set_click_through"):
        assert callable(getattr(overlay, metodo))
    assert hasattr(overlay, "visibilidad") and overlay.cerrado is False
    overlay.set_hablando(True)          # no-op en sprites, pero no revienta


def test_visibilidad_y_cierre(overlay):
    vistos = []
    overlay.visibilidad.connect(vistos.append)
    overlay.show(); overlay.hide()
    assert vistos[:2] == [True, False]
    overlay.close()
    assert overlay.cerrado is True


def test_set_act_no_rompe_en_sprites(overlay):
    """set_act con el dict del modelo funciona también en modo sprites."""
    overlay.set_act({"emotion": "happy", "intensity": 0.9, "motion": None})
    assert overlay.cara._current_state == "happy"
    overlay.set_act({"emotion": "angry", "intensity": 1.0})
    assert overlay.cara._current_state == "error"
