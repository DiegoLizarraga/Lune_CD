"""
Tests de ui/acciones_qt.py: el Ejecutor enchufado a Qt (corte 2).

Con la ventana a la vista la pregunta es un QMessageBox no bloqueante; sin
ella, un DialogoAprobacion junto a la mascota. Lo que llega tras aprobar o al
caducar (hilo de un temporizador) se ejecuta en el hilo de Qt, y los
resultados salen por la señal `resultado`.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import acciones as A  # noqa: E402
from servicios.tools import ToolManager, ToolResult  # noqa: E402

CALL_APP = '<|CALL ["lanzar_app", {"app": "calc"}]|>'


class Temporizadores:
    """programar(seg, fn) falso: guarda los callbacks para dispararlos a mano."""
    def __init__(self):
        self.pendientes = []

    def __call__(self, segundos, fn):
        t = type("T", (), {"cancelado": False})()
        t.cancel = lambda t=t: setattr(t, "cancelado", True)
        self.pendientes.append((fn, t))
        return t

    def disparar(self):
        for fn, t in list(self.pendientes):
            if not t.cancelado:
                fn()


@pytest.fixture
def entorno(qapp, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.acciones_qt import AccionesQt

    tm = ToolManager()
    lanzadas = []
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, f"Abrí {n}"))
    tm.registrar_handler("lanzar_app", tm._h_lanzar_app)
    ventana = QWidget()
    timers = Temporizadores()
    visible = {"si": True}
    acc = AccionesQt(tm, ventana=ventana, ventana_visible=lambda: visible["si"],
                     ancla=lambda: None, opciones_dialogo={"armado_ms": 0},
                     audit_path=None, programar=timers)
    resultados = []
    acc.resultado.connect(resultados.append)
    yield {"acc": acc, "lanzadas": lanzadas, "res": resultados, "timers": timers,
           "visible": visible, "ventana": ventana, "tm": tm}
    acc.cerrar()
    ventana.deleteLater()


def _pedir(acc):
    _, llamadas = acc.procesar(CALL_APP, A.USUARIO, {"modo": "normal"})
    acc.ejecutar(llamadas, A.USUARIO, {"modo": "normal"})
    return llamadas


def _procesar_eventos(qapp, hasta, segundos=2.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin and not hasta():
        qapp.processEvents()
        time.sleep(0.01)
    return hasta()


def test_ventana_visible_pregunta_con_messagebox_y_ejecuta_al_decir_si(entorno):
    from PyQt6.QtWidgets import QMessageBox
    acc = entorno["acc"]
    _pedir(acc)
    (pid, caja), = acc.abiertas.items()
    assert isinstance(caja, QMessageBox)
    assert "Abrir la aplicación «calc»" in caja.text() and "60 s" in caja.text()
    assert caja.defaultButton() is caja.button(QMessageBox.StandardButton.No)
    assert entorno["lanzadas"] == []
    caja.button(QMessageBox.StandardButton.Yes).click()
    assert entorno["lanzadas"] == ["calc"]
    assert entorno["res"][-1].ok and entorno["res"][-1].pendiente_id == pid
    assert acc.abiertas == {}


def test_messagebox_no_o_cerrar_es_rechazo(entorno):
    from PyQt6.QtWidgets import QMessageBox
    acc = entorno["acc"]
    _pedir(acc)
    (_, caja), = acc.abiertas.items()
    caja.button(QMessageBox.StandardButton.No).click()
    assert entorno["lanzadas"] == [] and entorno["res"][-1].estado == A.RECHAZADA
    _pedir(acc)
    (_, caja), = acc.abiertas.items()
    caja.reject()                                   # Esc / cerrar
    assert entorno["lanzadas"] == [] and entorno["res"][-1].estado == A.RECHAZADA


def test_el_texto_del_modelo_no_se_interpreta_como_html(entorno):
    from PyQt6.QtCore import Qt
    acc = entorno["acc"]
    _, llamadas = acc.procesar('<|CALL ["abrir_url", {"url": "https://x.com/<b>hola</b>"}]|>',
                               A.NO_CONFIABLE, None)
    # abrir_url con origen no confiable ni siquiera llega a preguntar (solo lectura)
    acc.ejecutar(llamadas, A.NO_CONFIABLE, None)
    assert entorno["res"][-1].estado == A.NO_CONFIABLE_ESTADO and acc.abiertas == {}
    _pedir(acc)
    (_, caja), = acc.abiertas.items()
    assert caja.textFormat() == Qt.TextFormat.PlainText


def test_ventana_oculta_usa_el_dialogo_junto_a_la_mascota(entorno):
    from ui.aprobacion_qt import DialogoAprobacion
    entorno["visible"]["si"] = False
    acc = entorno["acc"]
    _pedir(acc)
    (pid, dlg), = acc.abiertas.items()
    assert isinstance(dlg, DialogoAprobacion) and dlg.isVisible() and dlg.id_aprobacion == pid
    dlg._armar()
    dlg.boton_si.click()
    assert entorno["lanzadas"] == ["calc"] and entorno["res"][-1].ok and acc.abiertas == {}


def test_caducar_cierra_la_pregunta_y_no_ejecuta(entorno):
    acc = entorno["acc"]
    for visible in (True, False):
        entorno["visible"]["si"] = visible
        _pedir(acc)
        (_, abierta), = acc.abiertas.items()
        entorno["timers"].disparar()                # 60 s sin respuesta
        assert acc.abiertas == {}
        assert entorno["res"][-1].estado == A.CADUCADA
        assert not abierta.isVisible()
    assert entorno["lanzadas"] == []


def test_caducidad_desde_otro_hilo_llega_al_hilo_de_qt(entorno, qapp):
    acc = entorno["acc"]
    _pedir(acc)
    hilos = []
    acc.resultado.connect(lambda r: hilos.append(threading.get_ident()))
    t = threading.Thread(target=entorno["timers"].disparar)
    t.start(); t.join()
    assert _procesar_eventos(qapp, lambda: bool(hilos))
    assert hilos == [threading.get_ident()] and acc.abiertas == {}
    assert entorno["res"][-1].estado == A.CADUCADA


def test_nueva_conversacion_cierra_sin_ejecutar(entorno):
    acc = entorno["acc"]
    _pedir(acc)
    (_, caja), = acc.abiertas.items()
    acc.ejecutor.sesion.gastado = 5
    acc.nueva_conversacion()
    assert acc.abiertas == {} and not caja.isVisible()
    assert entorno["lanzadas"] == [] and acc.ejecutor.sesion.gastado == 0
    assert acc.pendientes() == []


def test_pregunta_propia_con_la_ventana_visible_y_resolver_por_id(qapp, monkeypatch):
    """El patrón de la piel web: preguntar() emite al modal y la página contesta por id."""
    from PyQt6.QtWidgets import QWidget
    from ui.acciones_qt import AccionesQt
    tm = ToolManager()
    lanzadas = []
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, "ok"))
    tm.registrar_handler("lanzar_app", tm._h_lanzar_app)
    preguntas, cerradas = [], []
    timers = Temporizadores()
    acc = AccionesQt(tm, ventana=QWidget(), ventana_visible=lambda: True,
                     preguntar=lambda p, r: preguntas.append(p), cerrar_pregunta=cerradas.append,
                     audit_path=None, programar=timers)
    res = []
    acc.resultado.connect(res.append)
    _pedir(acc)
    assert preguntas and preguntas[0]["herramienta"] == "lanzar_app"
    assert acc.resolver(preguntas[0]["id"], True) and lanzadas == ["calc"] and res[-1].ok
    assert acc.resolver(preguntas[0]["id"], True) is False       # solo cuenta una vez
    _pedir(acc)
    timers.disparar()
    assert cerradas == [preguntas[1]["id"]] and res[-1].estado == A.CADUCADA
    acc.cerrar()


def test_sin_herramienta_con_handler_no_se_pregunta(entorno):
    acc = entorno["acc"]
    _, llamadas = acc.procesar('<|CALL ["mascota_dormir", {}]|>', A.USUARIO, {"modo": "normal"})
    acc.ejecutar(llamadas, A.USUARIO, {"modo": "normal"})
    assert entorno["res"][-1].estado == A.NO_DISPONIBLE and acc.abiertas == {}
