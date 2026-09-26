"""
Tests de la mascota de sprites (ui/avatar_overlay.py) en los cortes 5 y 6: el
contrato de la mascota que aplica a los sprites.

- `bailar(on, opciones)` / `pulso(...)`: cara feliz, sin respiración, cuadros del
  baile compuestos con SpriteRotado (los saltitos caben en el lienzo), el
  arrastre corta, oculta no baila y al volver sigue, no se duerme bailando.
- `mostrar_alarma(texto, retraso_ms)` / `ocultar_alarma()`: burbuja roja tras el
  retraso, escrita a 35 c/s; frases, chat y clic no la tapan.
- `soporta_grande` es False (la pantalla grande de los sprites es VentanaReloj).
Offscreen, sin tocar nada de Windows.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FrasesSiempre:
    """Frases de la mascota que siempre dicen algo (para ver si la alarma las tapa)."""

    def __init__(self):
        self.pedidas = []

    def elegir(self, evento):
        self.pedidas.append(evento)
        return f"frase de {evento}"

    def set_personaje(self, p):
        pass


@pytest.fixture
def ov(qapp, monkeypatch):
    from nucleo import personajes
    from ui.avatar_overlay import AvatarOverlay
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    o = AvatarOverlay(config=None)
    o.show()
    o._frases = FrasesSiempre()
    yield o
    o.close()


def test_no_soporta_pantalla_grande(ov):
    assert ov.soporta_grande is False


def test_el_lienzo_tiene_hueco_para_los_saltitos(ov):
    from ui.avatar_overlay import LIENZO_DY_PX, RESP_PX
    from ui.sprites_baile import DY_MAX
    assert LIENZO_DY_PX >= max(RESP_PX, DY_MAX)
    assert ov._sr is not None and ov._sr.resp_px == LIENZO_DY_PX
    img, _ = ov._sr.componer(0.0, -DY_MAX)
    img2, _ = ov._sr.componer(0.0, -LIENZO_DY_PX - 3)
    assert img.size() == img2.size()                     # el lienzo no cambia de tamaño
    assert ov._sr.componer(0.0, -DY_MAX) is not ov._sr.componer(0.0, -2)   # no se recorta a ±2


def test_bailar_cara_feliz_sin_respiracion_y_compone_el_cuadro(ov):
    assert ov._resp.activo
    ov.bailar(True, {"estilo": "rebote", "cambiar": False, "cambiarS": 15, "particulas": True})
    assert ov.bailando and ov._baile.activo and ov._baile.estilo == "rebote"
    assert ov.cara._current_state == "happy"
    assert not ov._resp.activo
    ov._baile.cuadro.emit(3.0, -4)                        # un cuadro del baile
    assert ov._baile_cuadro == (3.0, -4)
    assert ov._img_compuesta is ov._sr.componer(3.0, -4)[0]
    assert ov._motivo_no_dormir() == "está bailando"
    ov.pulso(128.0, 0.5, 0.9)
    assert ov._baile._bpm == 128.0


def test_el_arrastre_corta_el_baile_y_al_soltar_vuelve(ov):
    ov.bailar(True, {"estilo": "vaiven"})
    ov._baile.cuadro.emit(3.0, -4)
    ov._fx.movimiento.emit(True)                         # la cogen
    assert ov._baile.peso == 0.0 and ov._arrastrando
    ov._on_angulo(2.0)                                   # manda la física
    assert ov._pose() == (2.0, ov._dy)
    ov._fx.movimiento.emit(False)
    assert not ov._baile._arrastre and ov._baile.activo
    assert ov.cara._current_state == "happy"             # al soltar sigue feliz (baila)


def test_parar_con_fundido_y_vuelve_la_respiracion(ov):
    ov.bailar(True, {})
    ov._baile._peso = 1.0
    ov.bailar(False)
    assert not ov.bailando and ov._baile.activo          # fundido de salida
    ov._baile.detener()                                  # fin del fundido
    assert ov._resp.activo and ov._baile_cuadro == (0.0, 0)
    assert ov.cara._current_state == "normal"


def test_oculta_no_baila_y_al_mostrarse_sigue(ov):
    ov.bailar(True, {"estilo": "palmas"})
    ov.hide()
    assert not ov._baile.activo and ov.bailando
    ov.show()
    assert ov._baile.activo and ov._baile.estilo == "palmas" and not ov._resp.activo


def test_modo_juego_no_enciende_la_respiracion_bailando(ov):
    ov.bailar(True, {})
    ov.set_habilitado_fisica(False)
    ov.set_habilitado_fisica(True)
    assert not ov._resp.activo


def test_bailar_despierta_si_dormia(ov):
    ov._dormir()
    assert ov.durmiendo
    ov.bailar(True, {})
    assert not ov.durmiendo and ov.cara._current_state == "happy"


def test_alarma_burbuja_roja_tras_el_retraso_a_35_cps(ov):
    from ui.avatar_overlay import ALARMA_ANCHO_MAX, COLOR_ALARMA
    ov._dormir()
    ov.mostrar_alarma("Sacar la ropa", retraso_ms=3000)
    assert not ov.durmiendo                              # la alarma la despierta
    assert ov._t_alarma.isActive() and ov._t_alarma.interval() == 3000
    assert ov._burbuja is None or not ov._burbuja.isVisible()
    assert ov._t_tipeo.interval() == round(1000 / 35)
    ov._empezar_alarma()                                 # pasaron los 3 s
    b = ov._burbuja
    assert b.isVisible() and b.text() == "S"
    assert COLOR_ALARMA in b.styleSheet() and b.maximumWidth() <= ALARMA_ANCHO_MAX
    for _ in range(len("Sacar la ropa")):
        ov._tipear_alarma()
    assert b.text() == "Sacar la ropa" and not ov._t_tipeo.isActive()
    assert ov._motivo_no_dormir() == "hay una alarma sonando"


def test_con_alarma_ni_frases_ni_chat_ni_clic_la_tapan(ov):
    ov.mostrar_alarma("Gimnasio", retraso_ms=0)
    ov._empezar_alarma()
    for _ in range(10):
        ov._tipear_alarma()
    b = ov._burbuja
    assert ov._frase("arrastre") is None
    ov.burbuja_texto("respuesta de la IA")
    ov.burbuja_fin(10)
    assert b.text() == "Gimnasio" and b.isVisible() and not b._t_fin.isActive()
    ov.cara.set_state("normal")
    ov._clic_simple()
    assert ov.cara._current_state == "normal"            # el clic no reacciona (la apaga el control)


def test_ocultar_alarma_quita_la_burbuja_y_el_estilo(ov):
    from ui.chat_mascota import BurbujaQt
    ov.mostrar_alarma("Pan", retraso_ms=0)
    ov._empezar_alarma()
    ov._tipear_alarma(); ov._tipear_alarma(); ov._tipear_alarma()
    ov.ocultar_alarma()
    b = ov._burbuja
    assert not b.isVisible() and "#FF4826" not in b.styleSheet()
    assert b.maximumWidth() == BurbujaQt.ANCHO_MAX
    assert ov._alarma_texto is None and not ov._t_alarma.isActive() and not ov._t_tipeo.isActive()
    assert ov._frase("arrastre") == "frase de arrastre"  # las frases vuelven
    ov.ocultar_alarma()                                  # dos veces: nada


def test_alarma_antes_del_retraso_se_puede_ocultar(ov):
    ov.mostrar_alarma("x", retraso_ms=3000)
    ov.ocultar_alarma()
    assert not ov._t_alarma.isActive()
    ov._empezar_alarma()                                 # un disparo tardío no la saca
    assert ov._burbuja is None or not ov._burbuja.isVisible()


def test_alarma_oculta_la_escribe_y_la_ensena_al_volver(ov):
    ov.mostrar_alarma("Hola", retraso_ms=0)
    ov.hide()
    ov._empezar_alarma()
    for _ in range(4):
        ov._tipear_alarma()
    assert ov._burbuja is None or not ov._burbuja.isVisible()
    ov.show()
    assert ov._burbuja.isVisible() and ov._burbuja.text() == "Hola"


def test_cerrar_para_baile_y_alarma(ov):
    ov.bailar(True, {})
    ov.mostrar_alarma("x", retraso_ms=3000)
    ov.close()
    assert not ov._baile.activo and not ov._t_alarma.isActive()
    ov.bailar(True, {})                                  # cerrada: nada
    ov.mostrar_alarma("y")
    assert not ov._baile.activo and not ov._t_alarma.isActive()
