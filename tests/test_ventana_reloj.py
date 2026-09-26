"""
Tests de ui/ventana_reloj.VentanaReloj (offscreen): banderas de ventana que no
roba el foco, pantalla completa en la pantalla pedida, modos, la burbuja de la
alarma (3 s de retraso, 35 c/s, Apagar bloqueado y Posponer), clic → señal,
fundido de salida y pintado sin errores con y sin PNG.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QPixmap  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from ui import ventana_reloj as vr  # noqa: E402
from ui.ventana_reloj import VentanaReloj  # noqa: E402


class Reloj:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def ventana(qapp):
    creadas = []

    def crear(**kw):
        kw.setdefault("hora", lambda: datetime(2026, 9, 26, 23, 41))
        kw.setdefault("cargar", lambda estado: None)
        v = VentanaReloj(**kw)
        creadas.append(v)
        return v
    yield crear
    for v in creadas:
        v.ocultar(0)
        v.deleteLater()


def test_banderas_no_roba_el_foco(ventana):
    v = ventana()
    f = v.windowFlags()
    for bandera in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint,
                    Qt.WindowType.Tool, Qt.WindowType.WindowDoesNotAcceptFocus):
        assert f & bandera
    assert v.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert v.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_mostrar_ocupa_la_pantalla_y_cambia_de_modo(ventana):
    v = ventana()
    scr = QGuiApplication.primaryScreen()
    v.mostrar("salvapantallas", pantalla=scr, fondo_oscuro=True, reloj=True)
    assert v.isVisible()
    assert v.geometry() == scr.geometry()
    assert v.modo == "salvapantallas" and v.cara == "sleeping"
    v.mostrar("grande", pantalla=scr, fondo_oscuro=False, reloj=False)
    assert v.modo == "grande" and not v.fondo_oscuro and not v.con_reloj
    assert v.cara == "happy"
    v.mostrar("raro")
    assert v.modo == "grande"                              # modo desconocido → grande


def test_la_carita_se_pide_una_vez_por_estado(ventana):
    pedidas = []

    def cargar(estado):
        pedidas.append(estado)
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.white)
        return pm
    v = ventana(cargar=cargar)
    v.mostrar("salvapantallas")
    v.mostrar("salvapantallas")
    v.mostrar("grande", cara="dormida")
    assert pedidas == ["sleeping"]                         # «dormida» es sleeping: ya estaba
    v.mostrar("alarma")
    assert pedidas == ["sleeping", "normal"]


def test_alarma_espera_3_s_y_escribe_a_35_cps(ventana):
    v = ventana()
    v.mostrar("alarma")
    v.set_alarma("sacar la pizza")
    assert v._timer_retraso.isActive() and v._timer_retraso.interval() == 3000
    assert v.alarma_visible == "" and not v._botones.isVisible()
    assert v._timer_letras.interval() == round(1000 / 35)
    v._timer_retraso.timeout.emit()                        # pasan los 3 s
    assert v.alarma_visible == "s" and v._botones.isVisible()
    for _ in range(4):
        v._timer_letras.timeout.emit()
    assert v.alarma_visible == "sacar"
    for _ in range(50):
        v._timer_letras.timeout.emit()
    assert v.alarma_visible == "sacar la pizza"
    assert not v._timer_letras.isActive()
    v.set_alarma(None)
    assert v.alarma_texto is None and v.alarma_visible == "" and not v._botones.isVisible()


def test_apagar_bloqueado_durante_el_bloqueo_y_posponer(ventana):
    reloj = Reloj(100.0)
    v = ventana(reloj=reloj)
    v.mostrar("alarma")
    apagadas, pospuestas = [], []
    v.apagar.connect(lambda: apagadas.append(1))
    v.posponer.connect(lambda: pospuestas.append(1))
    v.set_alarma("gimnasio", bloqueo_ms=5000, retraso_ms=0)
    assert not v.btn_apagar.isEnabled()
    assert v.btn_apagar.text() == "APAGAR (5)"
    v._pulsar_apagar()
    assert apagadas == []
    reloj.t = 103.2
    v._pintar_boton_apagar()
    assert v.btn_apagar.text() == "APAGAR (2)"
    reloj.t = 105.0
    v._pintar_boton_apagar()
    assert v.btn_apagar.isEnabled() and v.btn_apagar.text() == "APAGAR"
    QTest.mouseClick(v.btn_apagar, Qt.MouseButton.LeftButton)
    assert apagadas == [1]
    QTest.mouseClick(v.btn_posponer, Qt.MouseButton.LeftButton)
    assert pospuestas == [1]


def test_posponer_bloqueado_durante_el_bloqueo(ventana):
    # MO13: como la tarjeta nativa, Posponer no hace nada (ni se puede pulsar) en el bloqueo.
    reloj = Reloj(100.0)
    v = ventana(reloj=reloj)
    v.mostrar("alarma")
    pospuestas = []
    v.posponer.connect(lambda: pospuestas.append(1))
    v.set_alarma("gimnasio", bloqueo_ms=5000, retraso_ms=0)
    assert not v.btn_posponer.isEnabled()
    QTest.mouseClick(v.btn_posponer, Qt.MouseButton.LeftButton)
    v._pulsar_posponer()
    assert pospuestas == []
    reloj.t = 105.0
    v._pintar_boton_apagar()
    assert v.btn_posponer.isEnabled()
    QTest.mouseClick(v.btn_posponer, Qt.MouseButton.LeftButton)
    assert pospuestas == [1]
    v.set_alarma("sin bloqueo", bloqueo_ms=0, retraso_ms=0)
    assert v.btn_posponer.isEnabled()


def test_cambiar_a_otro_modo_quita_la_alarma(ventana):
    v = ventana()
    v.mostrar("alarma")
    v.set_alarma("x", retraso_ms=0)
    v.mostrar("grande")
    assert v.alarma_texto is None


def test_clic_pide_cerrar(ventana):
    v = ventana()
    v.mostrar("grande")
    pedidos = []
    v.cerrar_pedido.connect(lambda: pedidos.append(1))
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert pedidos == [1]
    QTest.mouseClick(v, Qt.MouseButton.RightButton, pos=QPoint(5, 5))
    assert pedidos == [1]                                  # solo el izquierdo


def test_ocultar_con_fundido_y_ya(ventana):
    v = ventana()
    v.mostrar("salvapantallas")
    v.ocultar(40)
    assert v.ocultandose
    for _ in range(100):
        if not v.isVisible():
            break
        QTest.qWait(20)
    assert not v.isVisible() and not v.ocultandose
    assert v.windowOpacity() == pytest.approx(1.0)
    v.mostrar("grande")
    v.ocultar(0)
    assert not v.isVisible()
    assert not v._timer_hora.isActive()


def test_mostrar_durante_el_fundido_de_salida_lo_cancela(ventana):
    v = ventana()
    v.mostrar("grande")
    v.ocultar(400)
    v.mostrar("alarma")
    assert not v.ocultandose
    QTest.qWait(60)
    assert v.isVisible()


@pytest.mark.parametrize("modo", vr.MODOS)
@pytest.mark.parametrize("con_png", [False, True])
def test_pinta_todos_los_modos_sin_errores(ventana, modo, con_png):
    def cargar(estado):
        if not con_png:
            return None
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.cyan)
        return pm
    v = ventana(cargar=cargar)
    v.mostrar(modo, fondo_oscuro=(modo != "grande"))
    if modo == "alarma":
        v.set_alarma("una alarma con un texto largo que hay que partir en varias líneas", retraso_ms=0)
    img = v.grab()
    assert not img.isNull()


def test_cargar_cara_de_verdad_y_texto_fecha(qapp):
    raiz = Path(__file__).resolve().parent.parent / "lune_face"
    if (raiz / "lune_happy.png").is_file():
        pm = vr.cargar_cara("happy")
        assert pm is not None and not pm.isNull()
    if (raiz / "lune_thinking.png").is_file():
        pm = vr.cargar_cara("thinking")                    # es un vídeo: usa la imagen fija
        assert pm is not None and not pm.isNull()
    assert vr.texto_fecha(datetime(2026, 9, 26)) == "sábado, 26 de septiembre"
