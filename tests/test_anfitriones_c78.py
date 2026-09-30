"""
Cortes 7/8 en los anfitriones (ui/anfitrion_web.py y ui/anfitrion_nativo.py):

- `hwnd_principal()`: el HWND de la ventana principal para que la asistente pueda sentarse
  en ella (ControlAsiento la permite aunque sea del mismo proceso). No crea la ventana
  nativa si aún no existe (WA_WState_Created), 0 sin ventana o si ya se borró.
- `reaccion(estado, ms)`: comer sin la asistente a la vista. Web → la cara de Lune de la
  barra (señal `acto`) durante ms y vuelve a «normal»; nativa → la carita de la ventana
  (lune_face.set_state con auto_revert_ms). Estados raros y ms fuera de rango, acotados.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, Qt, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from ui.anfitrion_nativo import AnfitrionNativo  # noqa: E402
from ui.anfitrion_web import AnfitrionWeb, hwnd_de  # noqa: E402
from ui.montaje_vida import hwnd_principal_de  # noqa: E402


class Ventana:
    def __init__(self, h=4242):
        self.h = h

    def winId(self):
        if isinstance(self.h, Exception):
            raise self.h
        return self.h


class PuenteFalso(QObject):
    acto = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._worker = None


def test_hwnd_de():
    assert hwnd_de(Ventana(1234)) == 1234
    assert hwnd_de(None) == 0
    assert hwnd_de(Ventana(RuntimeError("wrapped C/C++ object has been deleted"))) == 0
    assert hwnd_de(Ventana(None)) == 0
    assert hwnd_de(SimpleNamespace(winId=lambda: 55)) == 55
    assert hwnd_de(SimpleNamespace()) == 0


def test_hwnd_principal_no_crea_la_ventana_nativa(qapp):
    w = QWidget()
    try:
        assert not w.testAttribute(Qt.WidgetAttribute.WA_WState_Created)
        assert AnfitrionWeb(SimpleNamespace(), w).hwnd_principal() == 0
        assert not w.testAttribute(Qt.WidgetAttribute.WA_WState_Created), "no la crea para preguntar"
        w.show()
        h = AnfitrionWeb(SimpleNamespace(), w).hwnd_principal()
        assert h == int(w.winId()) and h > 0
        assert AnfitrionNativo(w).hwnd_principal() == h
    finally:
        w.close()
        w.deleteLater()


def test_hwnd_principal_web_y_nativa():
    assert AnfitrionWeb(SimpleNamespace(), Ventana(77)).hwnd_principal() == 77
    assert AnfitrionWeb(SimpleNamespace(), None).hwnd_principal() == 0
    assert AnfitrionNativo(Ventana(88)).hwnd_principal() == 88
    # el montaje lo usa para ControlAsiento
    assert hwnd_principal_de(AnfitrionWeb(SimpleNamespace(), Ventana(77)))() == 77


def test_reaccion_web_pone_la_cara_de_la_barra_y_vuelve(qapp):
    b = PuenteFalso()
    caras = []
    b.acto.connect(caras.append)
    a = AnfitrionWeb(b, None)
    assert a.reaccion("happy", 200) is True
    assert caras == ["happy"]
    QTest.qWait(80)
    assert caras == ["happy"], "dura lo que dure la reacción"
    QTest.qWait(250)
    assert caras == ["happy", "normal"]


def test_reaccion_web_acota_y_rechaza(qapp):
    b = PuenteFalso()
    caras = []
    b.acto.connect(caras.append)
    a = AnfitrionWeb(b, None)
    for malo in ("", "<b>", "happy; x", "a" * 40, None):
        assert a.reaccion(malo, 100) is False, malo
    assert caras == []
    assert a.reaccion("HAPPY", 0) is True and caras == ["happy"]      # ms < 200 → 200
    QTest.qWait(80)
    assert caras == ["happy"]
    QTest.qWait(250)
    assert caras[-1] == "normal"
    assert AnfitrionWeb(SimpleNamespace(), None).reaccion("happy", 500) is False   # sin puente


def test_reaccion_nativa_con_la_carita(qapp):
    llamadas = []
    cara = SimpleNamespace(set_state=lambda e, auto_revert_ms=0: llamadas.append((e, auto_revert_ms)))
    a = AnfitrionNativo(SimpleNamespace(lune_face=cara))
    assert a.reaccion("happy", 2500) is True
    assert a.reaccion("happy", 99999) is True
    assert a.reaccion("happy", "x") is True
    assert llamadas == [("happy", 2500), ("happy", 10000), ("happy", 2500)]
    assert a.reaccion("<script>", 100) is False and len(llamadas) == 3
    assert AnfitrionNativo(SimpleNamespace()).reaccion("happy", 100) is False       # sin carita

    def rompe(*_a, **_k):
        raise RuntimeError("borrada")
    assert AnfitrionNativo(SimpleNamespace(lune_face=SimpleNamespace(set_state=rompe))).reaccion("happy") is False


def test_comida_sin_asistente_reacciona_por_el_anfitrion(qapp):
    """ControlComida (agente C) llama a anfitrion.reaccion(estado, ms) sin la asistente a la vista."""
    from nucleo import comida as nc
    from ui.comida_qt import ControlComida
    llamadas = []
    cara = SimpleNamespace(set_state=lambda e, auto_revert_ms=0: llamadas.append((e, auto_revert_ms)))
    anf = AnfitrionNativo(SimpleNamespace(lune_face=cara, config=None))
    c = ControlComida(SimpleNamespace(estado=None, prioridad=None, asistente=None), {"comida": {"activa": True}},
                      anfitrion=anf, lanzar_sonido=lambda f: None)
    try:
        c._reaccionar(nc.Reaccion("beber", "happy", 2500, "trago_1", 1.0, "*glup glup*"))
    finally:
        c.detener()
    assert llamadas == [("happy", 2500)]
