"""
Arreglos de la revisión final 7-10 (zona «vida»): `pensando` pegado (RR5) al cerrar la
mascota con un «Comentar pantalla» a medias, con el CompanionFlotante de verdad (vista
web falsa de tests/test_mascota_c78) y ServiciosEscritorio de verdad.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

from test_mascota_c78 import config, lune_activa, web_falso  # noqa: E402,F401  (fixtures)


def _comentando(config, monkeypatch):
    """Una mascota real a la vista que empieza «Comentar pantalla» y se queda a medias
    (el paso previo al comentario, _sondear, no acaba). 10.9: solo nube, así que con
    clave de OpenRouter (los tests ya no leen el datos.json de verdad)."""
    from nucleo import datos
    from nucleo.estado_mascota import BusEstado
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(datos, "openrouter_key", lambda: "sk-prueba")
    monkeypatch.setattr(datos, "ollama_model", lambda: "llava")
    monkeypatch.setattr(datos, "ollama_url", lambda: "http://127.0.0.1:9")
    c = CompanionFlotante(config, ai_manager=object(), bandeja=False)
    c._aparecer_pendiente = False
    c.show()
    c._on_cargado(True)
    sondeos = []
    monkeypatch.setattr(c, "_capturar", lambda: None)
    monkeypatch.setattr(c, "_sondear", lambda: sondeos.append(1))
    bus = BusEstado()
    c.set_bus_estado(bus)
    c._comentar(automatico=False)
    assert bus.actual().pensando is True and sondeos
    return c, bus


def test_cerrar_la_mascota_durante_el_sondeo_no_deja_pensando(qapp, web_falso, config, lune_activa, monkeypatch):
    c, bus = _comentando(config, monkeypatch)
    bus.pensar("chat", True)                         # el chat de la ventana también piensa
    c.close()                                        # «Cerrar mascota»
    assert bus.actual().pensando is True             # el chat sigue: esa fuente no es suya
    c._on_sondeo({"local": True, "ok": False, "vision": None})   # el hilo del sondeo acaba después
    bus.pensar("chat", False)
    assert bus.actual().pensando is False            # antes: pegado para siempre
    assert c._pensando is False


def test_el_sondeo_que_llega_tras_cerrar_tambien_la_suelta(qapp, web_falso, config, lune_activa, monkeypatch):
    """Aunque algo la marque cerrada sin pasar por closeEvent, la rama «cerrado» del
    sondeo deja de pensar."""
    c, bus = _comentando(config, monkeypatch)
    c.cerrado = True
    c._on_sondeo({"local": True, "ok": True, "vision": True})
    assert c._pensando is False and bus.actual().pensando is False
    c.cerrado = False
    c.close()


def test_mascota_destruida_apaga_su_fuente_de_pensando(qapp):
    from PyQt6 import sip
    from PyQt6.QtCore import QObject, pyqtSignal
    from ui.escritorio import ServiciosEscritorio

    class Mascota(QObject):
        visibilidad = pyqtSignal(bool)
        evento_js = pyqtSignal(str, dict)

        def isVisible(self):
            return True

    esc = ServiciosEscritorio(None)
    m = Mascota()
    esc.set_mascota(m, render="vrm")
    esc.estado.actualizar(pensando=True)             # comentando la pantalla
    esc.estado.pensar("chat", True)
    sip.delete(m)                                    # la ventana se destruye (destroyed)
    assert esc.mascota is None and esc.estado.actual().render == ""
    assert esc.estado.actual().pensando is True      # el chat sigue pensando
    esc.estado.pensar("chat", False)
    assert esc.estado.actual().pensando is False     # antes: la fuente «directo» se quedaba
    esc.cerrar()
