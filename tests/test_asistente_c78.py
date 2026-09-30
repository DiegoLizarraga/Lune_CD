"""
Tests del contrato de la mascota de los cortes 7 y 8 en ui/companion.py (animada y VRM):

- clic CENTRAL soltado sobre ella → menu_pedido('secundario', QPoint) (y no lo ve Chromium);
- `arrastre_cambio(True)` al pasar el umbral ANTES del delegado de ese MouseMove y
  `arrastre_cambio(False)` al soltar ANTES de devolverla a la pantalla y guardar; el
  delegado que devuelve True evita `self.move`; un arrastre cortado (menú, grande,
  ocultarla) también avisa; arrastrándola sentada, la página no se balancea;
- `asiento` → luneSentar y el cb con el punto analizado; frases «sentarse»/«bajar»;
  sentada → sin _asegurar_en_pantalla y showEvent/set_encima no tocan el orden Z (sí
  `restaurar_orden_z`); `punto_asiento` → luneSeatPx; `hwnd`;
- `cabeza` analiza luneCabeza(0.1) y la pasa a px globales; `comer` → luneComer + frase y
  la despierta; con comida en la mano el clic no comenta, el doble clic no abre el chat
  y no se duerme; se reaplica todo al recargar la página;
- con el ControlAsiento de verdad (ventanas falsas): el arrastre manual lo mueve el
  delegado y encaja en el borde del Bloc de notas.

Qt offscreen, sin Chromium: vista web falsa que anota el JS y contesta según el código.
"""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, pyqtSignal  # noqa: E402

PRESS, MOVE, RELEASE, DOBLE = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                               QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
IZQ, DER, MED = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton


def raton(tipo, boton, x, y, botones=None):
    from PyQt6.QtGui import QMouseEvent
    p = QPointF(x, y)
    if botones is None:
        botones = Qt.MouseButton.NoButton if tipo in (RELEASE,) else boton
    return QMouseEvent(tipo, p, p, boton, botones, Qt.KeyboardModifier.NoModifier)


def centro(w, dx=0, dy=0):
    c = w.frameGeometry().center()
    return c.x() + dx, c.y() + dy


class FrasesSiempre:
    """Frases de la mascota que siempre dicen algo (para ver qué evento se pidió)."""

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
def lune_activa(monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})


@pytest.fixture
def config(tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    return cfg


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso: anota el JS; `pagina.respuestas` = [(trozo, valor)] decide qué
    contesta un runJavaScript con callback (la primera coincidencia; si no, None)."""
    if not HAY_WEBENGINE:
        pytest.skip("la mascota web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__()
            self.js = []
            self.respuestas = []

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                cb("[]")
                return
            for trozo, valor in self.respuestas:
                if trozo in codigo:
                    cb(valor(codigo) if callable(valor) else valor)
                    return
            cb(None)

    class Ajustes:
        def setAttribute(self, *_):
            pass

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)

        def __init__(self):
            super().__init__()
            self._pagina = Pagina()
            self._url = QUrl()

        def page(self):
            return self._pagina

        def settings(self):
            return Ajustes()

        def setUrl(self, url):
            self._url = url

        def url(self):
            return self._url

        def focusProxy(self):
            return None

    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    return FalsoWeb


@pytest.fixture
def mascota(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=object(), bandeja=False)
    c._aparecer_pendiente = False
    c.show()
    c._on_cargado(True)
    c._frases = FrasesSiempre()
    c.web.page().js.clear()
    yield c
    c.close()


@pytest.fixture
def win_ventana(monkeypatch):
    """win_ventana sin Win32 y la mascota creyendo que hay HWND de verdad."""
    import servicios.win_ventana as wv
    import ui.companion as comp
    falsa = WinVentanaFalsa()
    monkeypatch.setattr(wv, "set_encima", falsa.set_encima)
    monkeypatch.setattr(wv, "al_fondo", falsa.al_fondo)
    monkeypatch.setattr(comp, "_ventana_nativa", lambda: True)
    return falsa


def js(c):
    return c.web.page().js


def llamadas(c, fn):
    return [x for x in js(c) if f"window.{fn}(" in x or f"window.{fn} ?" in x]


def filtro(c, tipo, boton, x, y, botones=None):
    """Un evento de ratón por el filtro de la vista (lo que ve la mascota sobre la página)."""
    return c.eventFilter(c.web, raton(tipo, boton, x, y, botones))


def comentarios(c):
    return [x for x in js(c) if "window.comentar(" in x]


# ── Clic central → menú secundario ─────────────────────────────────────────────

def test_clic_central_soltado_pide_el_menu_secundario(mascota):
    c = mascota
    pedidos = []
    c.menu_pedido.connect(lambda tipo, p: pedidos.append((tipo, p)))
    x, y = centro(c)
    assert filtro(c, PRESS, MED, x, y) is True, "el central no llega a Chromium (autoscroll)"
    assert pedidos == [], "se abre al SOLTAR"
    assert filtro(c, RELEASE, MED, x, y) is True
    assert pedidos == [("secundario", QPoint(x, y))]
    # el derecho sigue siendo el principal
    filtro(c, PRESS, DER, x, y); filtro(c, RELEASE, DER, x, y)
    assert pedidos[-1][0] == "principal"
    # soltado fuera, en modo fantasma o con el menú abierto: nada
    filtro(c, PRESS, MED, x, y); filtro(c, RELEASE, MED, -500, -500)
    c.set_click_through(True)
    filtro(c, PRESS, MED, x, y); filtro(c, RELEASE, MED, x, y)
    c.set_click_through(False)
    c.set_menu_abierto(True)
    filtro(c, PRESS, MED, x, y); filtro(c, RELEASE, MED, x, y)
    c.set_menu_abierto(False)
    assert len(pedidos) == 2


# ── Arrastre: señal, delegado y soltar ─────────────────────────────────────────

def test_arrastre_cambio_en_el_umbral_y_al_soltar_antes_de_devolverla_y_guardar(mascota, monkeypatch):
    c = mascota
    orden = []
    c.arrastre_cambio.connect(lambda on: orden.append(("señal", on)))
    asegurar, guardar = c._asegurar_en_pantalla, c._guardar_posicion
    monkeypatch.setattr(c, "_asegurar_en_pantalla", lambda: (orden.append(("asegurar",)), asegurar()))
    monkeypatch.setattr(c, "_guardar_posicion", lambda: (orden.append(("guardar",)), guardar()))
    x, y = centro(c)
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 3, y, IZQ)
    assert orden == [], "por debajo del umbral es un clic"
    filtro(c, MOVE, IZQ, x + 30, y + 5, IZQ)
    assert orden == [("señal", True)]
    filtro(c, MOVE, IZQ, x + 40, y + 5, IZQ)
    assert orden == [("señal", True)], "una sola vez por arrastre"
    filtro(c, RELEASE, IZQ, x + 40, y + 5)
    assert orden == [("señal", True), ("señal", False), ("asegurar",), ("guardar",)]
    # un clic sin moverse no avisa
    orden.clear()
    filtro(c, PRESS, IZQ, x, y); filtro(c, RELEASE, IZQ, x, y)
    assert orden == []


def test_el_delegado_se_pone_en_la_senal_y_mueve_en_ese_mismo_movimiento(mascota):
    c = mascota
    llamadas_del = []

    def delegado():
        llamadas_del.append(c.pos())
        return True                                  # ya movió la ventana (ControlAsiento)

    def poner(on):
        c.set_arrastre_delegado(delegado if on else None)
    c.arrastre_cambio.connect(poner)
    pos0 = c.pos()
    x, y = centro(c)
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 50, y + 20, IZQ)
    assert len(llamadas_del) == 1, "el delegado corre en el MouseMove que pasa el umbral"
    filtro(c, MOVE, IZQ, x + 80, y + 20, IZQ)
    assert len(llamadas_del) == 2
    assert c.pos() == pos0, "delegado True: sin self.move"
    arrastres = llamadas(c, "luneDrag")
    assert any("luneDrag(true" in a for a in arrastres), "luneDrag sigue"
    filtro(c, RELEASE, IZQ, x + 80, y + 20)
    assert c._delegado_arrastre is None
    c.arrastre_cambio.disconnect(poner)
    # un delegado que no mueve (False) → se mueve como siempre
    c.set_arrastre_delegado(lambda: False)
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 60, y + 30, IZQ)
    assert c.pos() == pos0 + QPoint(60, 30)
    filtro(c, RELEASE, IZQ, x + 60, y + 30)
    # un delegado que falla tampoco rompe el arrastre
    c.set_arrastre_delegado(lambda: 1 / 0)
    antes = c.pos()
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x - 20, y, IZQ)
    assert c.pos() == antes + QPoint(-20, 0)
    filtro(c, RELEASE, IZQ, x - 20, y)
    c.set_arrastre_delegado("no es callable")
    assert c._delegado_arrastre is None


def test_arrastre_cortado_tambien_avisa(mascota):
    c = mascota
    senales = []
    c.arrastre_cambio.connect(senales.append)
    x, y = centro(c)
    for cortar in (lambda: c.set_menu_abierto(True), lambda: c.hide()):
        filtro(c, PRESS, IZQ, x, y)
        filtro(c, MOVE, IZQ, x + 40, y, IZQ)
        cortar()
        assert senales[-2:] == [True, False]
        assert c._arrastre is None
        c.set_menu_abierto(False); c.show()
    # en pantalla grande
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 40, y, IZQ)
    c.grande_fase("glide")
    assert senales[-1] is False
    c.grande_fase("fin")


def test_arrastrandola_sentada_no_se_balancea(mascota):
    c = mascota
    c.asiento(True, "ventana", 1)
    c.set_arrastre_delegado(lambda: True)
    x, y = centro(c)
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 40, y, IZQ)
    js(c).clear()
    import time
    time.sleep(0.02)
    filtro(c, MOVE, IZQ, x + 90, y + 10, IZQ)
    envios = llamadas(c, "luneDrag")
    assert envios and all("luneDrag(true, 0.000, 0.000)" in e for e in envios), envios
    filtro(c, RELEASE, IZQ, x + 90, y + 10)


# ── Sentarse ───────────────────────────────────────────────────────────────────

PUNTO = '{"asiento":{"x":120,"y":300.5},"sonda":{"x":120,"y":330}}'


def test_asiento_llama_a_luneSentar_analiza_el_cb_y_dice_las_frases(mascota):
    c = mascota
    c.web.page().respuestas = [("luneSentar", PUNTO)]
    recibidos = []
    c.asiento(True, "ventana", 2, cb=recibidos.append)
    assert js(c)[0] == 'window.luneSentar ? window.luneSentar("ventana", 2) : null'
    assert recibidos == [{"asiento": [120.0, 300.5], "sonda": [120.0, 330.0]}]
    assert c.sentada == "ventana"
    assert c._frases.pedidas == ["sentarse"]
    c.asiento(True, "ventana", 3, cb=recibidos.append)     # otra vez (reanudar): sin frase
    assert c._frases.pedidas == ["sentarse"]
    c.asiento(True, "BARRA", 3)
    assert js(c)[-1] == 'window.luneSentar ? window.luneSentar("barra", 0) : null', "la barra no tiene variantes"
    c.asiento(True, "tejado", 99)
    assert js(c)[-1] == 'window.luneSentar ? window.luneSentar("ventana", 3) : null', "modo raro → ventana; variante acotada"
    c.web.page().respuestas = [("luneSentar", "null")]
    c.asiento(True, "ventana", 0, cb=recibidos.append)
    c.web.page().respuestas = [("luneSentar", "{basura")]
    c.asiento(True, "ventana", 0, cb=recibidos.append)
    assert recibidos[-2:] == [None, None]
    js(c).clear()
    c.asiento(False)
    assert js(c) == ["window.luneSentar && window.luneSentar(null)"] + comentarios(c)
    assert c.sentada == "" and c._frases.pedidas[-1] == "bajar"
    n = len(js(c))
    c.asiento(False)                                       # ya de pie: nada
    assert len(js(c)) == n


def test_asiento_con_la_pagina_sin_cargar_contesta_none_y_se_repite_al_cargar(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    try:
        recibidos = []
        c.asiento(True, "barra", cb=recibidos.append)
        assert recibidos == [None]
        c.punto_asiento(recibidos.append)
        assert recibidos == [None, None]
        c.set_comida_activa(True)
        c.show()
        c.web.page().js.clear()
        c._on_cargado(True)
        assert 'window.luneSentar && window.luneSentar("barra", 0)' in js(c)
        assert "window.luneComidaActiva && window.luneComidaActiva(true)" in js(c)
    finally:
        c.close()
    rec = []
    c.asiento(True, "ventana", cb=rec.append)
    c.cabeza(rec.append)
    c.punto_asiento(rec.append)
    assert rec == [None, None, None], "cerrada: todo None"
    assert c.hwnd() == 0


def test_punto_asiento_lee_luneSeatPx(mascota):
    c = mascota
    c.web.page().respuestas = [("luneSeatPx", '{"asiento":[100,200],"sonda":{"x":101,"y":260}}')]
    rec = []
    c.punto_asiento(rec.append)
    assert rec == [{"asiento": [100.0, 200.0], "sonda": [101.0, 260.0]}]
    c.web.page().respuestas = [("luneSeatPx", '{"asiento":{"x":1}}')]
    c.punto_asiento(rec.append)
    c.web.page().respuestas = [("luneSeatPx", '{"asiento":{"x":5,"y":6}}')]
    c.punto_asiento(rec.append)
    assert rec[1:] == [None, {"asiento": [5.0, 6.0], "sonda": [5.0, 6.0]}], "sin sonda: la del asiento"
    c.punto_asiento(None)                                  # sin callback: nada


def test_sentada_no_la_devuelve_a_la_pantalla_ni_toca_el_orden_z(mascota, win_ventana, config):
    c = mascota
    c.asiento(True, "ventana", 0)
    c.move(-5000, -5000)
    c._asegurar_en_pantalla()
    assert (c.x(), c.y()) == (-5000, -5000), "sentada: ControlAsiento manda en la posición"
    win_ventana.llamadas.clear()
    c.hide(); c.show()
    assert win_ventana.llamadas == [], "showEvent no pisa el orden Z sentada"
    c.set_encima(False)
    assert config.get("avatar", "siempre_encima") is False and win_ventana.llamadas == [], "se guarda, no se aplica"
    c.restaurar_orden_z()
    assert win_ventana.llamadas == [("encima", False)]
    c.asiento(False)
    c._asegurar_en_pantalla()
    assert (c.x(), c.y()) != (-5000, -5000), "de pie vuelve a la pantalla"
    win_ventana.llamadas.clear()
    c.hide(); c.show()
    assert win_ventana.llamadas == [("encima", False)]
    assert isinstance(c.hwnd(), int)


def test_soltar_sentada_no_la_devuelve_a_la_pantalla(mascota):
    c = mascota
    c.arrastre_cambio.connect(lambda on: c.asiento(True, "ventana", 1) if not on else None)
    x, y = centro(c)
    filtro(c, PRESS, IZQ, x, y)
    filtro(c, MOVE, IZQ, x + 40, y, IZQ)
    c.move(-4000, -4000)                                   # la clavó ControlAsiento
    filtro(c, RELEASE, IZQ, x + 40, y)
    assert c.sentada == "ventana" and (c.x(), c.y()) == (-4000, -4000)


# ── Comida ─────────────────────────────────────────────────────────────────────

def test_cabeza_lee_luneCabeza_y_la_da_en_px_globales(mascota):
    from nucleo import comida as nc
    c = mascota
    c.web.page().respuestas = [("luneCabeza(0.1)", '{"x":100.5,"y":50,"r":20}')]
    rec = []
    c.cabeza(rec.append)
    o = c.web.mapToGlobal(QPoint(0, 0))
    assert rec == [(o.x() + 100.5, o.y() + 50.0, 20.0)]
    assert nc.cabeza_valida(rec[0]) == rec[0], "lo que espera ControlComida"
    for mala in ("null", '{"x":1,"y":2,"r":0}', '{"x":"a","y":2,"r":3}', "{", None):
        c.web.page().respuestas = [("luneCabeza(0.1)", mala)]
        c.cabeza(rec.append)
    assert rec[1:] == [None] * 5


def test_comer_llama_a_luneComer_dice_la_frase_y_la_despierta(mascota):
    c = mascota
    c._dormir()
    assert c.durmiendo
    js(c).clear()
    c.comer("beber", 2500)
    assert not c.durmiendo
    assert "window.luneSleep && window.luneSleep(false)" in js(c)
    assert 'window.luneComer && window.luneComer("beber", 2500)' in js(c)
    assert c._frases.pedidas[-1] == "comer"
    c.comer("<script>", 10 ** 9)
    assert 'window.luneComer && window.luneComer("comer", 10000)' in js(c), "tipo raro → comer; ms acotados"
    c.comer("comer", "x")
    assert 'window.luneComer && window.luneComer("comer", 2500)' in js(c)


def test_con_comida_en_la_mano_ni_comenta_ni_chat_ni_sueno(mascota, monkeypatch):
    c = mascota
    comentados, chats = [], []
    monkeypatch.setattr(c, "comentar_pantalla", lambda: comentados.append(1))
    monkeypatch.setattr(c._chat, "abrir", lambda: chats.append(1))
    c.set_comida_activa(True)
    assert js(c)[-1] == "window.luneComidaActiva && window.luneComidaActiva(true)"
    assert c.comida_activa
    c._clic_simple()
    assert comentados == []
    x, y = centro(c)
    filtro(c, DOBLE, IZQ, x, y)
    assert chats == [], "el doble clic no abre el chat"
    assert c._motivo_no_dormir() == "está comiendo"
    assert c._motivo_no_dormir(forzado=True) == "está comiendo"
    c._rearmar_sueno()
    assert not c._timer_sueno.isActive()
    assert c.dormir() is False
    c.set_comida_activa(False)
    assert js(c)[-1] == "window.luneComidaActiva && window.luneComidaActiva(false)"
    assert c._timer_sueno.isActive(), "vuelve a contar el sueño"
    c._clic_simple()
    assert comentados == [1]
    filtro(c, DOBLE, IZQ, x, y)
    assert chats == [1]


def test_recargar_la_pagina_repite_sentada_y_comida(mascota):
    c = mascota
    c.asiento(True, "ventana", 3)
    c.set_comida_activa(True)
    js(c).clear()
    c._on_cargado(True)
    assert 'window.luneSentar && window.luneSentar("ventana", 3)' in js(c)
    assert "window.luneComidaActiva && window.luneComidaActiva(true)" in js(c)
    c.asiento(False); c.set_comida_activa(False)
    js(c).clear()
    c._on_cargado(True)
    assert not llamadas(c, "luneSentar") and not llamadas(c, "luneComidaActiva")


# ── Con el ControlAsiento de verdad ────────────────────────────────────────────

def test_con_control_asiento_real_el_delegado_mueve_y_encaja_en_el_bloc(mascota, config):
    from ventanas_falsas_c78 import ApiVentanasFalsa, EntradaFalsa, PantallaFalsa, Reloj, V, VentanaPropiaFalsa
    from ui.asiento_qt import ControlAsiento
    from ui.escritorio import ServiciosEscritorio
    import random
    c = mascota
    config.set("avatar", "sentarse_ventanas", True)
    esc = ServiciosEscritorio(config)
    api = ApiVentanasFalsa({2: V((300, 400, 1100, 900))})
    h = c.hwnd()
    win = VentanaPropiaFalsa({h: (100, 100, 400, 600)})
    cursor, reloj = EntradaFalsa(500, 500), Reloj()
    ctl = ControlAsiento(esc, config, api=api, ventana=win, entrada=cursor, pantalla=PantallaFalsa(),
                         hwnd_principal=lambda: 0, reloj=reloj, azar=random.Random(3))
    esc.registrar("asiento", ctl, ("sentada",))
    esc.iniciar()
    try:
        c.web.page().respuestas = [("luneSeatPx", '{"asiento":{"x":150,"y":400},"sonda":{"x":150,"y":420}}'),
                                   ("luneSentar", '{"asiento":{"x":150,"y":380},"sonda":{"x":150,"y":420}}')]
        esc.set_mascota(c)
        pos0 = c.pos()
        x, y = centro(c)
        filtro(c, PRESS, IZQ, x, y)
        cursor.c = (510, 505)                          # el cursor (px físicos) al pasar el umbral
        filtro(c, MOVE, IZQ, x + 10, y + 5, IZQ)
        assert c._delegado_arrastre is not None, "ControlAsiento puso su delegado"
        assert win.de("mover")[-1] == ("mover", h, 100, 100), "el delegado corre en ese mismo movimiento"
        cursor.c = (540, 525)
        filtro(c, MOVE, IZQ, x + 40, y + 25, IZQ)
        assert win.de("mover")[-1] == ("mover", h, 130, 120), "lo movió el delegado (px físicos)"
        assert c.pos() == pos0, "y la mascota no hizo move"
        cursor.c = (960, 395)
        filtro(c, MOVE, IZQ, x + 460, y - 105, IZQ)     # llega al borde del Bloc…
        assert c.sentada == ""
        reloj.t += 0.5                                 # …y la deja quieta medio segundo (sin MouseMove)
        ctl._tic_arrastre()
        assert c.sentada == "ventana", "encajó en el borde del Bloc"
        assert any("luneSentar(\"ventana\"" in s for s in js(c))
        assert esc.estado.actual().sentada == "ventana"
        filtro(c, RELEASE, IZQ, x + 450, y - 110)
        assert c._delegado_arrastre is None
        assert c.sentada == "ventana", "al soltar queda sentada"
        assert ctl.bajar() is True
        assert c.sentada == "" and "window.luneSentar && window.luneSentar(null)" in js(c)
    finally:
        esc.cerrar()
        ctl.deleteLater()
