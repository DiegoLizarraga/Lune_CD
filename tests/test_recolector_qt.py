"""
Tests de ui/recolector_qt.py: la basura con ciclos se recoge en el hilo de Qt, nunca en otro.

- revisar() recoge lo mismo que habría recogido el automático (generación 0, 1 o 2 según
  los contadores y los umbrales) y nada si aún no toca;
- iniciar() apaga el automático y arranca el temporizador; detener() lo deja como estaba;
- main.py lo pone justo después de crear la QApplication;
- y la propia suite corre sin automático (tests/conftest.py), igual que la app.
"""
import gc
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


class GcFalso:
    def __init__(self, cuenta=(0, 0, 0), umbral=(700, 10, 10), activo=True):
        self.cuenta, self.umbral, self.activo = cuenta, umbral, activo
        self.recogidas = []

    def get_threshold(self):
        return self.umbral

    def get_count(self):
        return self.cuenta

    def isenabled(self):
        return self.activo

    def disable(self):
        self.activo = False

    def enable(self):
        self.activo = True

    def collect(self, generacion=2):
        self.recogidas.append(generacion)
        return 0


@pytest.fixture
def RQ(qapp):
    from ui import recolector_qt
    return recolector_qt


@pytest.mark.parametrize("cuenta,esperada", [
    ((10, 0, 0), -1),            # aún no toca
    ((700, 0, 0), -1),           # justo en el umbral: el automático tampoco
    ((701, 0, 0), 0),
    ((701, 11, 0), 1),
    ((701, 11, 11), 2),
    ((701, 3, 11), 2),           # la más vieja que pasó su umbral, como el automático
])
def test_revisar_recoge_lo_que_habria_recogido_el_automatico(RQ, cuenta, esperada):
    g = GcFalso(cuenta=cuenta)
    r = RQ.RecolectorQt(gc_mod=g)
    assert r.revisar() == esperada
    assert g.recogidas == ([] if esperada < 0 else [esperada])


def test_iniciar_apaga_el_automatico_y_detener_lo_devuelve(RQ):
    g = GcFalso(activo=True)
    r = RQ.RecolectorQt(gc_mod=g, intervalo_ms=500)
    assert r.iniciar() is r and r.activo and g.activo is False
    assert r._timer.isActive() and r._timer.interval() == 500
    r.detener()
    assert g.activo is True and not r._timer.isActive() and not r.activo


def test_detener_no_enciende_lo_que_ya_estaba_apagado(RQ):
    g = GcFalso(activo=False)
    r = RQ.RecolectorQt(gc_mod=g).iniciar()
    r.detener()
    assert g.activo is False


def test_un_fallo_de_gc_no_tumba_el_temporizador(RQ):
    class Roto(GcFalso):
        def collect(self, generacion=2):
            raise RuntimeError("roto")
    r = RQ.RecolectorQt(gc_mod=Roto(cuenta=(5000, 0, 0)))
    assert r.revisar() == -1
    r = RQ.RecolectorQt(gc_mod=GcFalso(cuenta=None))
    assert r.revisar() == -1


def test_instalar_cuelga_de_la_app_y_arranca(RQ, qapp):
    viejo = gc.isenabled()
    try:
        r = RQ.instalar(qapp)
        assert r.parent() is qapp and r.activo and not gc.isenabled()
        r.detener()
    finally:
        (gc.enable if viejo else gc.disable)()


def test_main_lo_pone_justo_despues_de_crear_la_app():
    fuente = (RAIZ / "main.py").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("def main():"):]
    assert "from ui.recolector_qt import instalar" in cuerpo
    assert cuerpo.index("app = QApplication(sys.argv)") < cuerpo.index("_instalar_recolector(app)") \
        < cuerpo.index("_preparar_arranque(")


def test_la_suite_corre_sin_recolector_automatico():
    """tests/conftest.py lo apaga, como la app: la basura solo se recoge en el hilo principal."""
    assert not gc.isenabled()
