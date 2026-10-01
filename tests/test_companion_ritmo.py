"""
Ritmo de los sondeos de la asistente en escritorio (ui/companion.py, 11.2).

Cada runJavaScript despierta al renderer y al hilo de Qt: la cola de eventos se vacía a
12 Hz solo mientras pasa algo (arrastre, menú, chat, comida y ~2 s tras un evento o tras
tocarla), a 4 Hz en reposo y a 1,5 Hz dormida; el cursor va a 30 Hz y dormida a 10 Hz.
"""
import json
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="la asistente necesita PyQt6-WebEngine")


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso (como en test_asistente_eventos.py): anota el JS y responde a
    luneEventos() con lo que se le prepare."""
    from PyQt6.QtCore import QObject, QUrl, pyqtSignal
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []; self.cola = []
        def setBackgroundColor(self, *_): pass
        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                lote, self.cola = self.cola, []
                cb(json.dumps(lote))
            else:
                cb(None)

    class Ajustes:
        def setAttribute(self, *_): pass

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)
        def __init__(self):
            super().__init__(); self._pagina = Pagina(); self._url = QUrl(); self._ajustes = Ajustes()
        def page(self): return self._pagina
        def settings(self): return self._ajustes
        def setUrl(self, url): self._url = url
        def url(self): return self._url
        def focusProxy(self): return None

    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    return FalsoWeb


@pytest.fixture
def asistente(qapp, web_falso, tmp_path):
    from nucleo.config import Config
    from ui.companion import CompanionFlotante
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    c = CompanionFlotante(cfg, ai_manager=None)
    yield c
    c.close()


def _hace_rato(c):
    """Como si el último evento o gesto fuera de hace 10 s."""
    c._actividad_t = time.monotonic() - 10


def test_constantes():
    from ui.companion import CompanionFlotante as C
    assert (C.EVENTOS_HZ, C.EVENTOS_REPOSO_HZ, C.EVENTOS_DORMIDA_HZ) == (12, 4, 1.5)
    assert (C.CURSOR_HZ, C.CURSOR_DORMIDA_HZ) == (30, 10)
    assert C.EVENTOS_ACTIVA_S == 2.0


def test_rapido_al_aparecer_y_en_reposo_despues(asistente):
    c = asistente
    assert c._timer_eventos.interval() == 1000 // 12
    c.show()
    assert c._timer_eventos.isActive()
    assert c._timer_eventos.interval() == 1000 // 12, "recién sacada: a todo ritmo un rato"
    _hace_rato(c)
    c._vaciar_eventos()                                   # cada sondeo ajusta el siguiente
    assert c._timer_eventos.interval() == 250, "en reposo, 4 Hz"
    assert c._timer_eventos.isActive()
    assert c._timer_cursor.interval() == 1000 // 30


def test_un_evento_de_la_pagina_lo_acelera(asistente):
    c = asistente
    c.show()
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 250
    c.web.page().cola = [{"t": "caricia", "d": {"lado": 1}}]
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 1000 // 12, "detrás de un evento suelen venir más"
    _hace_rato(c)
    c._vaciar_eventos()                                   # lote vacío: vuelve al reposo
    assert c._timer_eventos.interval() == 250


def test_dormida_lento_y_cursor_a_10_hz(asistente):
    c = asistente
    c.show()
    c._dormir()
    assert c._durmiendo
    assert c._timer_cursor.interval() == 100, "dormida no sigue al cursor: 10 Hz"
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == int(1000 / 1.5)
    c._despertar(usuario=True)
    assert c._timer_eventos.interval() == 1000 // 12, "despertarla es actividad"
    assert c._timer_cursor.interval() == 1000 // 30


def test_menu_comida_y_chat_mantienen_el_ritmo_alto(asistente, monkeypatch):
    c = asistente
    c.show()
    _hace_rato(c)
    c.set_menu_abierto(True)
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 1000 // 12, "menú abierto"
    c.set_menu_abierto(False)
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 250
    c.set_comida_activa(True)
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 1000 // 12, "comida en la mano"
    c.set_comida_activa(False)
    monkeypatch.setattr(c._chat, "abierta", lambda: True)
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 1000 // 12, "chat abierto"
    monkeypatch.setattr(c._chat, "abierta", lambda: False)
    c._arrastre = {"origen": None}
    _hace_rato(c)
    c._vaciar_eventos()
    assert c._timer_eventos.interval() == 1000 // 12, "arrastrándola"
    c._arrastre = None


def test_oculta_para_y_al_volver_acelera(asistente):
    c = asistente
    c.show()
    _hace_rato(c)
    c._vaciar_eventos()
    c.hide()
    assert not c._timer_eventos.isActive()
    c.show()
    assert c._timer_eventos.isActive() and c._timer_eventos.interval() == 1000 // 12
