"""
ui/web_bridge.py: los avisos de la voz (voice.al_hablar / voice.on_error) llegan del hilo
de audio y pueden llegar con el puente ya borrado (cambio de interfaz, salir). Antes se
guardaba la señal ligada (self._hablando.emit): llamarla tras borrar el puente daba
AttributeError o una violación de acceso (mismo patrón que RR1 con Discord). Ahora el
aviso comprueba que el puente siga vivo y cerrar_escritorio lo desengancha.

Sin red, sin voz real, con datos.json y config.json en carpetas temporales.
"""
import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de crear la QApplication)
except ImportError:
    pass

from PyQt6 import sip  # noqa: E402


class VozFalsa:
    def __init__(self):
        self._enabled = False
        self.available = False
        self.on_error = None
        self.al_hablar = None

    def cancelar(self):
        pass

    def invalidar_params(self):
        pass

    def reiniciar_motor(self):
        pass


class AIFalso:
    providers = {}

    def clear_history(self):
        pass

    def reload_provider(self):
        pass


@pytest.fixture
def crear_puente(qapp, tmp_path, monkeypatch):
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({"apis": {}, "modelos": {}, "bot": {},
                                "personajes": [{"nombre": "Lune", "systemPrompt": "Eres Lune."}]}), "utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    import ui.web_bridge as wb
    from nucleo.config import Config

    def crear():
        memoria = MagicMock()
        memoria.obtener_contexto_para_prompt.return_value = ""
        voz = VozFalsa()
        b = wb.LuneBridge(config=Config(str(tmp_path / "config.json")), ai_manager=AIFalso(),
                          memoria=memoria, voice=voz,
                          opciones_acciones={"audit_path": None, "programar": lambda s, fn: MagicMock()})
        return b, voz

    yield crear
    datos.invalidar()


def _desde_otro_hilo(*llamadas):
    """Llama a cada (fn, arg) desde un hilo (como el de audio): las excepciones que salgan."""
    errores = []

    def correr():
        for fn, arg in llamadas:
            try:
                fn(arg)
            except BaseException as e:            # noqa: BLE001 — queremos verlas todas
                errores.append(e)

    h = threading.Thread(target=correr)
    h.start()
    h.join(10)
    return errores


def test_los_avisos_de_la_voz_llegan_con_el_puente_vivo(qapp, crear_puente):
    b, voz = crear_puente()
    hablando, errores_voz = [], []
    b._hablando.connect(hablando.append)
    b.aviso.connect(errores_voz.append)
    assert _desde_otro_hilo((voz.al_hablar, True), (voz.on_error, "sin red")) == []
    for _ in range(20):
        qapp.processEvents()
    assert hablando == [True] and errores_voz == ["Voz: sin red"]
    b.cerrar_escritorio()
    sip.delete(b)


def test_aviso_de_la_voz_tras_borrar_el_puente_no_revienta(qapp, crear_puente):
    """El hilo de voz ya tenía el aviso en la mano cuando se borró el puente."""
    b, voz = crear_puente()
    al_hablar, on_error = voz.al_hablar, voz.on_error
    sip.delete(b)
    qapp.processEvents()
    assert sip.isdeleted(b)
    assert _desde_otro_hilo((al_hablar, True), (al_hablar, False), (on_error, "sin red")) == []
    qapp.processEvents()


def test_cerrar_escritorio_desengancha_la_voz_solo_si_es_suya(qapp, crear_puente):
    b, voz = crear_puente()
    assert voz.al_hablar is not None and voz.on_error is not None
    b.cerrar_escritorio()                                      # aboutToQuit / cambio de interfaz
    assert voz.al_hablar is None and voz.on_error is None
    # Una voz que ya avisa a otro (la ventana nueva) no se toca.
    b2, voz2 = crear_puente()
    otro = lambda *a: None                                     # noqa: E731
    voz2.al_hablar = otro
    b2.cerrar_escritorio()
    assert voz2.al_hablar is otro and voz2.on_error is None
    for x in (b, b2):
        sip.delete(x)
