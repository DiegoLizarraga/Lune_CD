"""
Tests de ui/montaje_ocio.py (montar_ocio, ServiciosOcio, EnHiloQt) con el
ServiciosEscritorio y el Despachador de verdad y fábricas falsas de las piezas
de los agentes A (alarmas) y C (baile); la pantalla grande, la de verdad o una
falsa. Offscreen.
"""
import copy
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from nucleo.acciones_ui import Despachador  # noqa: E402
from nucleo.config import Config  # noqa: E402
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from ui.montaje_ocio import EnHiloQt, ServiciosOcio, minutos_rapido, montar_ocio  # noqa: E402


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)


class Controlador(QObject):
    """Base de los dobles: anota el ciclo de vida."""

    def __init__(self, nombre, diario, kw):
        super().__init__(kw.get("parent"))
        self.nombre, self.diario, self.kw = nombre, diario, kw
        self.borrado = False
        self.destroyed.connect(lambda *_: None)

    def iniciar(self):
        self.diario.append((self.nombre, "iniciar"))

    def detener(self):
        self.diario.append((self.nombre, "detener"))

    def set_mascota(self, v):
        self.diario.append((self.nombre, "mascota", v is not None))

    def deleteLater(self):
        self.borrado = True
        super().deleteLater()


class GrandeFalsa(Controlador):
    pedir_apagar_alarma = pyqtSignal()
    pedir_posponer_alarma = pyqtSignal()
    cambio = pyqtSignal(bool, str)

    def __init__(self, diario, **kw):
        super().__init__("grande", diario, kw)
        self.activo = False

    def alternar(self):
        self.activo = not self.activo
        self.diario.append(("grande", "alternar"))
        return self.activo

    def herramientas(self):
        return {"mascota_pantalla_grande": lambda args, ctx=None: "ok"}


class AlarmasFalsas(Controlador):
    def __init__(self, diario, **kw):
        super().__init__("alarmas", diario, kw)

    def apagar(self, forzar=False):
        self.diario.append(("alarmas", "apagar", forzar))
        return True

    def posponer(self):
        self.diario.append(("alarmas", "posponer"))
        return True

    def abrir_dialogo(self, parent=None):
        self.diario.append(("alarmas", "dialogo"))

    def rapido(self, minutos=5):
        self.diario.append(("alarmas", "rapido", minutos))
        return {"ok": True}

    def herramientas(self):
        f = lambda args, ctx=None: "ok"  # noqa: E731
        return {"temporizador": f, "alarma": f, "cancelar_alarma": f, "listar_alarmas": f}


class BaileFalso(Controlador):
    def __init__(self, diario, **kw):
        super().__init__("baile", diario, kw)
        self.bailando = False

    def bailar(self, segundos=None, *, origen="manual"):
        self.bailando = True
        self.diario.append(("baile", "bailar"))
        return True

    def parar(self, *, silenciar_auto=True):
        self.bailando = False
        self.diario.append(("baile", "parar"))
        return True

    def pausa(self):
        self.diario.append(("baile", "pausa"))
        return True

    def herramientas(self):
        f = lambda args, ctx=None: "ok"  # noqa: E731
        return {"mascota_bailar": f, "parar_baile": f}


class AtajosFalsos:
    def __init__(self):
        self.recargas = 0

    def recargar(self):
        self.recargas += 1


class ToolsFalsas:
    def __init__(self):
        self.h = {}

    def registrar_handler(self, n, fn):
        self.h[n] = fn

    def quitar_handler(self, n):
        self.h.pop(n, None)


class AnfitrionFalso:
    def __init__(self, modo="normal", con_navegar=True):
        self.modo = modo
        self.diario = []
        self.navegar = (lambda v: self.diario.append(("navegar", v))) if con_navegar else None

    def mostrar_ventana(self):
        self.diario.append("mostrar")

    def mascota(self):
        return None

    def alternar_mascota(self):
        return False


def fabricas(diario, **extra):
    f = {
        "grande": lambda esc, cfg, **kw: GrandeFalsa(diario, **kw),
        "alarmas": lambda esc, cfg, **kw: AlarmasFalsas(diario, **kw),
        "baile": lambda esc, cfg, **kw: BaileFalso(diario, **kw),
    }
    f.update(extra)
    return f


def montar(qapp, *, modo="normal", con_navegar=True, iniciado=True, fab=None, diario=None):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tools = ToolsFalsas()
    esc.conectar_herramientas(tools)
    if iniciado:
        esc.iniciar()
    avisos = []
    s4 = SimpleNamespace(escritorio=esc, despachador=Despachador(), atajos=AtajosFalsos(),
                         anfitrion=AnfitrionFalso(modo, con_navegar), avisar=avisos.append, _deshacer=[])
    diario = diario if diario is not None else []
    ocio = montar_ocio(s4, cfg, voice="voz", fabricas=fab or fabricas(diario))
    return SimpleNamespace(cfg=cfg, esc=esc, s4=s4, ocio=ocio, diario=diario, tools=tools, avisos=avisos)


IDS = ("pantalla_grande", "bailar", "baile_pausa", "alarma", "temporizador_rapido")
HERRAMIENTAS = ("mascota_pantalla_grande", "temporizador", "alarma", "cancelar_alarma",
                "listar_alarmas", "mascota_bailar", "parar_baile")


def test_controladores_y_actividades_registrados(qapp):
    h = montar(qapp)
    esc, o = h.esc, h.ocio
    assert esc.obtener("grande") is o.grande
    assert esc.obtener("alarmas") is o.alarmas
    assert esc.obtener("baile") is o.baile
    assert esc._controlador_de_actividad("grande") is o.grande
    assert esc._controlador_de_actividad("salvapantallas") is o.grande
    assert esc._controlador_de_actividad("alarma") is o.alarmas
    assert esc._controlador_de_actividad("baile") is o.baile
    # arrancaron (el escritorio ya estaba iniciado) en orden: grande, alarmas, baile
    assert [x[0] for x in h.diario if x[1] == "iniciar"] == ["grande", "alarmas", "baile"]


def test_inyeccion_de_dependencias(qapp):
    h = montar(qapp)
    o = h.ocio
    assert isinstance(o.en_ui, EnHiloQt)
    for ctl in (o.grande, o.alarmas, o.baile):
        assert ctl.kw["en_ui"] is o.en_ui
        assert ctl.kw["parent"] is h.esc
    assert o.grande.kw["anfitrion"] is h.s4.anfitrion
    assert o.alarmas.kw["grande"] is o.grande
    assert o.alarmas.kw["avisar"] is h.s4.avisar
    assert o.alarmas.kw["voice"] == "voz"


def test_ids_del_despachador_con_handler(qapp):
    h = montar(qapp)
    desp = h.s4.despachador
    for id_ in IDS:
        assert desp.tiene(id_), id_
    desp.ejecutar("pantalla_grande")
    assert h.ocio.grande.activo and desp.marcado("pantalla_grande") is True
    desp.ejecutar("bailar")
    assert h.ocio.baile.bailando and desp.marcado("bailar") is True
    desp.ejecutar("bailar")
    assert not h.ocio.baile.bailando
    desp.ejecutar("baile_pausa")
    desp.ejecutar("temporizador_rapido", "10")
    desp.ejecutar("temporizador_rapido")
    assert ("alarmas", "rapido", 10) in h.diario and ("alarmas", "rapido", 5) in h.diario
    assert h.avisos == ["⏲ 10 min", "⏲ 5 min"]
    assert ("baile", "pausa") in h.diario


def test_accion_alarma_web_navega_y_nativa_abre_el_dialogo(qapp):
    h = montar(qapp, modo="normal")
    h.s4.despachador.ejecutar("alarma")
    assert h.s4.anfitrion.diario == ["mostrar", ("navegar", "alarmas")]
    assert ("alarmas", "dialogo") not in h.diario
    n = montar(qapp, modo="br", con_navegar=False)
    n.s4.despachador.ejecutar("alarma")
    assert ("alarmas", "dialogo") in n.diario


def test_herramientas_en_el_escritorio_y_en_el_toolmanager(qapp):
    h = montar(qapp)
    for n in HERRAMIENTAS:
        assert n in h.esc._herramientas, n
        assert n in h.tools.h, n


def test_atajos_recargados(qapp):
    h = montar(qapp)
    assert h.s4.atajos.recargas == 1


def test_botones_del_reloj_llevan_a_la_alarma(qapp):
    h = montar(qapp)
    h.ocio.grande.pedir_apagar_alarma.emit()
    h.ocio.grande.pedir_posponer_alarma.emit()
    assert ("alarmas", "apagar", True) in h.diario
    assert ("alarmas", "posponer") in h.diario


def test_desmontar_idempotente_lo_quita_todo(qapp):
    h = montar(qapp)
    o, esc, desp = h.ocio, h.esc, h.s4.despachador
    assert o.desmontar in h.s4._deshacer
    o.desmontar()
    assert o.desmontado
    for id_ in IDS:
        assert not desp.tiene(id_), id_
    for n in HERRAMIENTAS:
        assert n not in esc._herramientas and n not in h.tools.h
    for n in ("grande", "alarmas", "baile"):
        assert esc.obtener(n) is None
    assert esc._controlador_de_actividad("alarma") is None
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["baile", "alarmas", "grande"]
    assert h.s4.atajos.recargas == 2
    assert o.grande.borrado and o.alarmas.borrado and o.baile.borrado
    # desconectado: los botones ya no llegan a la alarma
    n = len(h.diario)
    h.ocio.grande.pedir_apagar_alarma.emit()
    assert len(h.diario) == n
    o.desmontar()                                         # otra vez: nada
    assert h.s4.atajos.recargas == 2


def test_desmontar_borra_el_editor_de_alarmas_que_abrio_la_accion(qapp):
    # VS8: el editor de alarmas de la nativa (sin padre) no queda huérfano tras el cambio.
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QWidget
    editores = []

    class AlarmasConEditor(AlarmasFalsas):
        def abrir_dialogo(self, parent=None):
            if not editores or sip.isdeleted(editores[-1]) or not editores[-1].isVisible():
                editores.append(QWidget())
            editores[-1].show()
            return editores[-1]
    diario = []
    h = montar(qapp, modo="br", con_navegar=False,
               fab=fabricas(diario, alarmas=lambda esc, cfg, **kw: AlarmasConEditor(diario, **kw)))
    h.s4.despachador.ejecutar("alarma")
    h.s4.despachador.ejecutar("alarma")                   # el mismo: uno solo en la lista
    assert len(editores) == 1 and h.ocio.ventanas == editores
    h.ocio.desmontar()
    assert not editores[0].isVisible() and h.ocio.ventanas == []
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert sip.isdeleted(editores[0])


def test_desmontar_sin_escritorio_iniciado_detiene_igual(qapp):
    h = montar(qapp, iniciado=False)
    h.ocio.desmontar()
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["baile", "alarmas", "grande"]


def test_no_quita_un_handler_que_ya_no_es_suyo(qapp):
    h = montar(qapp)
    otro = lambda: None  # noqa: E731
    h.s4.despachador.registrar("bailar", otro)
    h.ocio.desmontar()
    assert h.s4.despachador.tiene("bailar")


def test_una_pieza_que_falla_no_tumba_las_demas(qapp):
    diario = []

    def rota(*a, **kw):
        raise ImportError("ui.alarmas_qt aún no existe")
    h = montar(qapp, fab=fabricas(diario, alarmas=rota), diario=diario)
    assert h.ocio.alarmas is None
    assert h.ocio.grande is not None and h.ocio.baile is not None
    desp = h.s4.despachador
    assert desp.tiene("pantalla_grande") and desp.tiene("bailar")
    assert not desp.tiene("alarma") and not desp.tiene("temporizador_rapido")
    h.ocio.grande.pedir_apagar_alarma.emit()              # sin alarmas: no conectado, no falla
    h.ocio.desmontar()


def test_con_servicios_corte4_de_verdad_el_cambio_de_interfaz_lo_desmonta(qapp):
    from ui.montaje_escritorio import ServiciosCorte4
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    diario = []
    s4 = ServiciosCorte4(despachador=Despachador(), escritorio=esc, anfitrion=AnfitrionFalso(),
                         avisar=lambda t: None)
    s4.atajos = AtajosFalsos()
    ocio = montar_ocio(s4, cfg, fabricas=fabricas(diario))
    assert s4.despachador.tiene("pantalla_grande")
    s4.desmontar()
    assert ocio.desmontado
    assert not s4.despachador.tiene("pantalla_grande")
    assert esc.obtener("grande") is None


def test_con_la_pantalla_grande_de_verdad(qapp):
    diario = []
    f = fabricas(diario)
    del f["grande"]                                       # la de verdad (agente B)
    h = montar(qapp, fab=f, diario=diario)
    from ui.pantalla_grande_qt import ControlPantallaGrande
    assert isinstance(h.ocio.grande, ControlPantallaGrande)
    assert h.ocio.grande._en_ui is h.ocio.en_ui
    assert h.ocio.grande.anfitrion is h.s4.anfitrion
    assert "mascota_pantalla_grande" in h.esc._herramientas
    h.ocio.desmontar()


# ── EnHiloQt ──────────────────────────────────────────────────────────────────

def test_en_hilo_qt_directo_en_el_hilo_de_qt(qapp):
    e = EnHiloQt()
    assert e(lambda: 42) == 42
    with pytest.raises(ValueError):
        e(lambda: (_ for _ in ()).throw(ValueError("x")))
    e.deleteLater()


def test_en_hilo_qt_desde_otro_hilo(qapp):
    e = EnHiloQt()
    hilos = []
    caja = {}

    def trabajo():
        try:
            caja["r"] = e(lambda: hilos.append(threading.get_ident()) or "hecho")
        except Exception as ex:                          # noqa: BLE001
            caja["e"] = ex
    t = threading.Thread(target=trabajo)
    t.start()
    fin = time.monotonic() + 3
    while t.is_alive() and time.monotonic() < fin:
        QTest.qWait(10)
    t.join(1)
    assert caja.get("r") == "hecho"
    assert hilos == [threading.get_ident()]              # corrió en el hilo de Qt
    e.deleteLater()


def test_en_hilo_qt_sin_respuesta_da_timeout(qapp):
    e = EnHiloQt()
    caja = {}

    def trabajo():
        try:
            e(lambda: 1, espera_s=0.05)                  # nadie procesa eventos
        except TimeoutError as ex:
            caja["e"] = ex
    t = threading.Thread(target=trabajo)
    t.start()
    t.join(2)
    assert isinstance(caja.get("e"), TimeoutError)
    QTest.qWait(20)                                       # vaciar la cola
    e.deleteLater()


def test_minutos_rapido():
    assert minutos_rapido("") == 5
    assert minutos_rapido("10") == 10
    assert minutos_rapido("15m") == 15
    assert minutos_rapido("0") == 1
    assert minutos_rapido("9999") == 180
    assert minutos_rapido("x") == 5


def test_servicios_ocio_vacio():
    o = ServiciosOcio()
    o.desmontar()
    o.detener()
    assert o.desmontado
