"""
Tests de la asistente de sprites (ui/avatar_overlay.py) en los cortes 7 y 8: lo que aplica
del contrato de la asistente.

- el arrastre es NATIVO: `nativeEvent` con WM_ENTERSIZEMOVE / WM_EXITSIZEMOVE → la señal
  `arrastre_cambio` (solo en los cambios; devuelve (False, 0)); el arrastre de respaldo
  también avisa (al soltar, antes de guardar); NO tiene `set_arrastre_delegado`;
- `punto_asiento` y `cabeza` SÍNCRONOS (centro de abajo de la figura; la cabeza al 35 % y
  r = 0.22·ancho, en px globales); `hwnd`;
- `asiento`: sin balanceo sentada (la física se apaga y vuelve sin salto), con
  respiración, frases «sentarse»/«bajar», cara `sitting` solo si el pack la trae; el orden
  Z no se toca sentada salvo `restaurar_orden_z`; puede dormirse sentada (D5);
- clic central → menu_pedido('secundario'); `comer` → cara happy + frase y la despierta;
  con comida en la mano ni reacción al clic, ni chat, ni sueño;
- con el ControlAsiento de verdad (ventanas falsas): encaja en la barra al soltar.
Offscreen, sin tocar nada de Windows.
"""
import ctypes
import shutil
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402

PRESS, MOVE, RELEASE = QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease
IZQ, DER, MED = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton


def raton(tipo, boton, x, y, botones=None):
    from PyQt6.QtGui import QMouseEvent
    p = QPointF(x, y)
    if botones is None:
        botones = Qt.MouseButton.NoButton if tipo == RELEASE else boton
    return QMouseEvent(tipo, p, p, boton, botones, Qt.KeyboardModifier.NoModifier)


class FrasesSiempre:
    def __init__(self):
        self.pedidas = []

    def elegir(self, evento):
        self.pedidas.append(evento)
        return f"frase de {evento}"

    def set_personaje(self, p):
        pass


class WinVentanaFalsa:
    def __init__(self):
        self.llamadas = []

    def set_encima(self, hwnd, on, user32=None):
        self.llamadas.append(("encima", bool(on)))
        return True

    def al_fondo(self, hwnd, user32=None):
        self.llamadas.append(("fondo",))
        return True


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


@pytest.fixture
def win_ventana(monkeypatch):
    import servicios.win_ventana as wv
    import ui.avatar_overlay as ao
    falsa = WinVentanaFalsa()
    monkeypatch.setattr(wv, "set_encima", falsa.set_encima)
    monkeypatch.setattr(wv, "al_fondo", falsa.al_fondo)
    monkeypatch.setattr(ao, "_ventana_nativa", lambda: True)
    return falsa


def nativo(ov, mensaje, tipo=b"windows_generic_MSG"):
    msg = wintypes.MSG()
    msg.message = mensaje
    return ov.nativeEvent(tipo, ctypes.addressof(msg))


# ── Arrastre nativo ────────────────────────────────────────────────────────────

def test_sin_delegado_y_el_arrastre_nativo_avisa_por_nativeEvent(ov):
    from ui.avatar_overlay import WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE, mensaje_win
    assert not hasattr(ov, "set_arrastre_delegado"), "así ControlAsiento sabe que el arrastre es nativo"
    assert ov.render == "sprites"
    assert (WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE) == (0x0231, 0x0232)
    senales = []
    ov.arrastre_cambio.connect(senales.append)
    assert nativo(ov, WM_ENTERSIZEMOVE) == (False, 0), "Windows lo procesa igual"
    assert senales == [True]
    nativo(ov, WM_ENTERSIZEMOVE)
    assert senales == [True], "solo en los cambios"
    nativo(ov, 0x0200)                                  # WM_MOUSEMOVE: nada
    nativo(ov, WM_EXITSIZEMOVE, tipo=b"otra_cosa")      # otro tipo de evento: nada
    assert senales == [True]
    assert nativo(ov, WM_EXITSIZEMOVE) == (False, 0)
    assert senales == [True, False]
    assert ov.nativeEvent(b"windows_generic_MSG", 0) == (False, 0), "puntero nulo: nada"
    assert mensaje_win(0) is None and mensaje_win("x") is None
    msg = wintypes.MSG(); msg.message = 0x1234
    assert mensaje_win(ctypes.addressof(msg)) == 0x1234


def test_el_arrastre_de_respaldo_avisa_y_al_soltar_antes_de_guardar(ov, monkeypatch):
    orden = []
    ov.arrastre_cambio.connect(lambda on: orden.append(("señal", on)))
    guardar = ov._guardar_posicion
    monkeypatch.setattr(ov, "_guardar_posicion", lambda: (orden.append(("guardar",)), guardar()))
    monkeypatch.setattr(ov, "windowHandle", lambda: None)          # sin startSystemMove
    c = ov.frameGeometry().center()
    ov.mousePressEvent(raton(PRESS, IZQ, c.x(), c.y()))
    ov.mouseMoveEvent(raton(MOVE, IZQ, c.x() + 20, c.y(), IZQ))
    assert orden == [("señal", True)]
    ov.mouseMoveEvent(raton(MOVE, IZQ, c.x() + 40, c.y(), IZQ))
    ov.mouseReleaseEvent(raton(RELEASE, IZQ, c.x() + 40, c.y()))
    assert orden == [("señal", True), ("señal", False), ("guardar",)]


# ── Punto de asiento, cabeza, hwnd ─────────────────────────────────────────────

def test_punto_asiento_y_cabeza_sincronos(ov):
    from ui.avatar_overlay import ALTO_CABEZA, RADIO_CABEZA
    rec = []
    ov.punto_asiento(rec.append)
    assert len(rec) == 1, "síncrono"
    p = rec[0]
    assert p["asiento"] == p["sonda"]
    x, y = p["asiento"]
    fig = ov._rect_figura_ventana()
    assert (x, y) == (fig.x() + fig.width() / 2, fig.y() + fig.height())
    assert 0 < x < ov.width() and ov.height() / 2 < y <= ov.height(), "abajo, dentro de la ventana"
    cab = []
    ov.cabeza(cab.append)
    o = ov.mapToGlobal(QPoint(0, 0))
    cx, cy, r = cab[0]
    assert cx == pytest.approx(o.x() + x)
    assert cy == pytest.approx(o.y() + fig.y() + fig.height() * ALTO_CABEZA)
    assert r == pytest.approx(RADIO_CABEZA * fig.width())
    from nucleo import comida as nc
    assert nc.cabeza_valida(cab[0]) == cab[0], "lo que espera ControlComida"
    assert isinstance(ov.hwnd(), int)
    ov.punto_asiento(None); ov.cabeza(None)           # sin callback: nada


# ── Sentada ────────────────────────────────────────────────────────────────────

def test_sentada_sin_balanceo_con_respiracion_frases_y_cb(ov):
    assert ov._fx.habilitado
    rec = []
    ov.asiento(True, "ventana", 2, cb=rec.append)
    assert ov.sentada == "ventana"
    assert rec == [ov._punto_asiento()], "cb síncrono con el punto"
    assert ov._fx.habilitado is False, "la ventana la mueve ControlAsiento: sin balanceo"
    assert ov._resp.activo, "sigue respirando"
    assert ov._frases.pedidas == ["sentarse"]
    ov.move(ov.x() + 200, ov.y() - 50)                 # ControlAsiento la sigue: nada se balancea
    assert ov._angulo == 0.0 and not ov._fx.arrastrando
    ov.asiento(True, "barra", 3)                       # otra vez: sin frase
    assert ov._frases.pedidas == ["sentarse"] and ov.sentada == "barra"
    ov.asiento(False, cb=rec.append)
    assert rec[-1] is None and ov.sentada == ""
    assert ov._fx.habilitado, "de pie vuelve la física…"
    assert not ov._fx.arrastrando, "…sin el salto de lo que se movió sentada"
    assert ov._frases.pedidas[-1] == "bajar"
    n = len(ov._frases.pedidas)
    ov.asiento(False)
    assert len(ov._frases.pedidas) == n


def test_sentada_no_toca_el_orden_z_salvo_restaurar(ov, win_ventana):
    ov.asiento(True, "barra")
    win_ventana.llamadas.clear()
    ov.hide(); ov.show()
    ov.set_encima(False)
    assert win_ventana.llamadas == []
    ov.restaurar_orden_z()
    assert win_ventana.llamadas == [("encima", False)]
    ov.asiento(False)
    win_ventana.llamadas.clear()
    ov.hide(); ov.show()
    assert win_ventana.llamadas == [("encima", False)]


def test_cara_sitting_solo_si_el_pack_la_trae(ov, monkeypatch, tmp_path):
    from ui import lune_face
    import ui.avatar_overlay as ao
    assert lune_face.tiene_cara("sitting") is False, "el pack de serie no la trae"
    ov.asiento(True, "ventana")
    assert ov.cara._current_state == "normal", "sin lune_sitting.png, la de siempre"
    ov.asiento(False)
    # un pack con lune_sitting.png
    pack = tmp_path / "packs" / "sentada"
    pack.mkdir(parents=True)
    shutil.copy(lune_face.FACE_DIR / "lune_normal.png", pack / "lune_sitting.png")
    monkeypatch.setattr(lune_face, "PACKS_DIR", tmp_path / "packs")
    monkeypatch.setattr(lune_face, "_ACTIVE_PACK", "sentada")     # se deshace solo al acabar
    assert lune_face.tiene_cara("sitting") and ao.tiene_cara("sitting")
    assert lune_face.get_face_info("sitting")[0] == str(pack / "lune_sitting.png")
    ov.asiento(True, "ventana")
    assert ov.cara._current_state == "sitting"
    assert ov.cara.state_tag.text() == "月 SENTADA"
    ov.set_emocion("happy", 50)
    assert ov.cara._current_state == "happy"
    ov.cara._volver_a_normal()                     # la vuelta sola cae en la de sentada
    assert ov.cara._current_state == "sitting"
    ov._clic_simple()
    assert ov.cara._current_state == "happy", "el clic reacciona también sentada"
    ov.set_estado("normal")                        # la app pide el reposo: sentada es `sitting`
    assert ov.cara._current_state == "sitting"
    ov.asiento(False)
    assert ov.cara._current_state == "normal"
    ov.cara._volver_a_normal()
    assert ov.cara._current_state == "normal"


def test_puede_dormirse_sentada(ov):
    ov.asiento(True, "barra")
    assert ov._motivo_no_dormir() == ""
    ov._dormir()
    assert ov.durmiendo and ov.cara._current_state == "sleeping"
    assert ov.sentada == "barra"


# ── Menú secundario y comida ───────────────────────────────────────────────────

def test_clic_central_pide_el_menu_secundario(ov):
    pedidos = []
    ov.menu_pedido.connect(lambda tipo, p: pedidos.append((tipo, p)))
    c = ov.frameGeometry().center()
    ov.mousePressEvent(raton(PRESS, MED, c.x(), c.y()))
    assert pedidos == []
    ov.mouseReleaseEvent(raton(RELEASE, MED, c.x(), c.y()))
    assert pedidos == [("secundario", QPoint(c.x(), c.y()))]
    ov.mousePressEvent(raton(PRESS, DER, c.x(), c.y()))
    ov.mouseReleaseEvent(raton(RELEASE, DER, c.x(), c.y()))
    assert pedidos[-1][0] == "principal"
    ov.mousePressEvent(raton(PRESS, MED, c.x(), c.y()))
    ov.mouseReleaseEvent(raton(RELEASE, MED, -900, -900))    # fuera: se arrepintió
    assert len(pedidos) == 2


def test_comer_cara_feliz_frase_y_la_despierta(ov):
    ov._dormir()
    assert ov.durmiendo
    ov.comer("beber", 2500)
    assert not ov.durmiendo
    assert ov.cara._current_state == "happy"
    assert ov._base[0] == "happy" and ov._base[1] is not None, "vuelve sola a los ms"
    assert ov._frases.pedidas[-1] == "comer"
    ov.comer("comer", "x")                              # ms raros: los de siempre
    assert ov.cara._current_state == "happy"


def test_con_comida_en_la_mano_ni_clic_ni_chat_ni_sueno(ov, monkeypatch):
    chats = []
    monkeypatch.setattr(ov._chat, "abrir", lambda: chats.append(1))
    ov.set_comida_activa(True)
    assert ov.comida_activa
    ov._clic_simple()
    assert ov.cara._current_state == "normal", "el clic no reacciona"
    c = ov.frameGeometry().center()
    from PyQt6.QtGui import QMouseEvent
    doble = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(c), QPointF(c), IZQ, IZQ,
                        Qt.KeyboardModifier.NoModifier)
    ov.mouseDoubleClickEvent(doble)
    assert chats == []
    assert ov._motivo_no_dormir() == "está comiendo"
    ov._rearmar_sueno()
    assert not ov._timer_sueno.isActive()
    ov.set_comida_activa(False)
    assert ov._timer_sueno.isActive()
    ov.mouseDoubleClickEvent(doble)
    assert chats == [1]


# ── Con el ControlAsiento de verdad ────────────────────────────────────────────

def test_con_control_asiento_real_encaja_en_la_barra_al_soltar(ov):
    from ventanas_falsas_c78 import ApiVentanasFalsa, Config, EntradaFalsa, PantallaFalsa, Reloj, VentanaPropiaFalsa
    from servicios.win_pantalla import Rect
    from ui.asiento_qt import ControlAsiento
    from ui.avatar_overlay import WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE
    from ui.escritorio import ServiciosEscritorio
    import random
    cfg = Config()
    esc = ServiciosEscritorio(cfg)
    h = ov.hwnd()
    win = VentanaPropiaFalsa({h: (100, 100, 100 + ov.width(), 100 + ov.height())})
    cursor, reloj = EntradaFalsa(500, 500), Reloj()
    ctl = ControlAsiento(esc, cfg, api=ApiVentanasFalsa({}), ventana=win, entrada=cursor, pantalla=PantallaFalsa(),
                         hwnd_principal=lambda: 0, reloj=reloj, azar=random.Random(3))
    esc.registrar("asiento", ctl, ("sentada",))
    esc.iniciar()
    try:
        esc.set_asistente(ov)
        nativo(ov, WM_ENTERSIZEMOVE)
        assert ctl.estado()["arrastrando"] is True
        # el SO la dejó con los pies sobre la barra (Shell_TrayWnd arriba en y = 1032)
        px, py = ov._punto_asiento()["sonda"]
        x0, y0 = int(560 - px), int(1030 - py)
        win.rects[h] = Rect(x0, y0, x0 + ov.width(), y0 + ov.height())
        cursor.c = (560, 950)
        reloj.t += 0.3
        nativo(ov, WM_EXITSIZEMOVE)
        assert ov.sentada == "barra", "encajó al soltar con el punto síncrono"
        assert esc.estado.actual().sentada == "barra"
        assert ov._fx.habilitado is False
        nativo(ov, WM_ENTERSIZEMOVE)                   # arrastrarla otra vez la levanta
        assert ov.sentada == ""
        nativo(ov, WM_EXITSIZEMOVE)
    finally:
        esc.cerrar()
        ctl.deleteLater()
