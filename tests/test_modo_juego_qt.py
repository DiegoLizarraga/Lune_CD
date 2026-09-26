"""
Tests de ui/modo_juego_qt.ControlModoJuego (offscreen, con ServiciosEscritorio de
verdad y detector, mascota, voz, prioridad y recorte falsos):

- entrar: BusEstado.juego, cede lo que la tabla dice, plan a la mascota, voz
  callada (solo si la config lo pide y no lo estaba), prioridad baja, recorte de
  RAM 1.5 s después en un hilo, señal `cambio(True, motivo)`;
- salir: todo al revés (y reanuda lo cedido), mascota con None, `cambio(False)`;
- el plan se aplica UNA vez por partida (si el usuario saca la mascota, no se
  vuelve a ocultar), la mascota nueva durante la partida recibe el plan;
- forzar al momento, detener() restaura, recargar_config con el detector
  apagado sale, recorte automático (sistema.recorte_ram_auto) fuera de partida.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")

from servicios import modo_juego as mj  # noqa: E402


class DetectorFalso:
    """Detector sin histéresis: `juego` manda (o `forzado`)."""

    def __init__(self):
        self.juego = False
        self.forzado = None
        self.activo = False
        self.motivo = ""
        self.lecturas = 0

    def detectando(self):
        return True

    def forzar(self, on):
        self.forzado = on

    def evaluar(self):
        self.lecturas += 1
        nuevo = self.forzado if self.forzado is not None else self.juego
        cambio = nuevo != self.activo
        self.activo = nuevo
        self.motivo = ("forzado" if self.forzado else "quns3") if nuevo else ""
        return (cambio, self.activo, self.motivo)

    def estado(self):
        return {"activo": self.activo, "motivo": self.motivo, "forzado": self.forzado, "exe": "juego.exe"}


class MascotaFalsa:
    def __init__(self, diario, nombre="m"):
        self.diario, self.nombre = diario, nombre
        self.planes = []

    def aplicar_plan_juego(self, plan):
        self.planes.append(plan)
        self.diario.append(("mascota", self.nombre, None if plan is None else plan.accion))


class VozFalsa:
    def __init__(self, diario, silenciada=False):
        self.diario = diario
        self.silenciada = silenciada

    def silenciar(self, on=True):
        self.silenciada = bool(on)
        self.diario.append(("voz", bool(on)))


class Sentada:
    """Controlador de «sentada»: el modo juego la levanta y al acabar la vuelve a sentar."""

    def __init__(self, diario):
        self.diario = diario

    def ceder(self, c): self.diario.append(("ceder", c.actividad, c.valor))
    def reanudar(self, c): self.diario.append(("reanudar", c.actividad, c.valor))


@pytest.fixture
def config(tmp_path):
    from nucleo.config import Config
    return Config(config_path=str(tmp_path / "config.json"))


@pytest.fixture
def montaje(qapp, config):
    """ServiciosEscritorio + ControlModoJuego registrado como lo hará montar_escritorio."""
    from ui.escritorio import ServiciosEscritorio
    from ui.modo_juego_qt import ControlModoJuego
    diario, recortes = [], []
    esc = ServiciosEscritorio(config)
    esc.estado.suscribir(lambda est, cambios: "juego" in cambios
                         and diario.append(("bus_juego", cambios["juego"][1])))
    det = DetectorFalso()
    voz = VozFalsa(diario)

    def recortar():
        recortes.append(threading.current_thread() is not threading.main_thread())
        return (500.0, 200.0)

    ctl = ControlModoJuego(esc, config, voice=voz, detector=det, recortar=recortar,
                           prioridad=lambda baja: diario.append(("prioridad", baja)), intervalo_ms=10_000)
    esc.registrar("juego", ctl, actividades=("juego",))
    cambios = []
    ctl.cambio.connect(lambda a, m: cambios.append((a, m)))
    esc.iniciar()
    m = MascotaFalsa(diario)
    esc.set_mascota(m)
    yield {"esc": esc, "ctl": ctl, "det": det, "voz": voz, "m": m, "diario": diario,
           "recortes": recortes, "cambios": cambios}
    esc.cerrar()


def esperar(cond, tope=3.0):
    from PyQt6.QtWidgets import QApplication
    fin = time.monotonic() + tope
    while not cond() and time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.005)
    return cond()


def test_entrar_y_salir_en_orden(montaje, monkeypatch):
    import ui.modo_juego_qt as mq
    monkeypatch.setattr(mq, "RETRASO_RECORTE_MS", 5)
    ctl, det, d, m = montaje["ctl"], montaje["det"], montaje["diario"], montaje["m"]
    d.clear()
    det.juego = True
    ctl._tic()
    assert ctl.activo() and montaje["esc"].estado.actual().juego is True
    assert d == [("bus_juego", True), ("mascota", "m", "ocultar"), ("voz", True), ("prioridad", True)]
    assert montaje["cambios"] == [(True, "quns3")]
    assert isinstance(m.planes[0], mj.PlanJuego) and m.planes[0] == mj.plan(ctl.config)
    # el recorte llega después, y en un hilo aparte
    assert esperar(lambda: montaje["recortes"]) and montaje["recortes"] == [True]
    d.clear()
    det.juego = False
    ctl._tic()
    assert not ctl.activo() and montaje["esc"].estado.actual().juego is False
    assert d == [("prioridad", False), ("voz", False), ("mascota", "m", None), ("bus_juego", False)]
    assert montaje["cambios"][-1] == (False, "")
    assert ctl.estado()["activo"] is False


def test_salir_antes_del_recorte_lo_cancela(montaje):
    ctl, det = montaje["ctl"], montaje["det"]
    det.juego = True
    ctl._tic()
    assert ctl._timer_recorte.isActive()
    det.juego = False
    ctl._tic()
    assert not ctl._timer_recorte.isActive()
    time.sleep(0.05)
    assert montaje["recortes"] == []


def test_el_plan_se_aplica_una_vez_por_partida(montaje):
    ctl, det, m = montaje["ctl"], montaje["det"], montaje["m"]
    det.juego = True
    for _ in range(5):
        ctl._tic()
    # si el usuario saca la mascota durante la partida, nadie la vuelve a ocultar
    assert len(m.planes) == 1 and det.lecturas == 5


def test_voz_solo_si_la_config_lo_pide_y_no_estaba_callada(montaje, config):
    ctl, det, voz, d = montaje["ctl"], montaje["det"], montaje["voz"], montaje["diario"]
    config.set("juego", "silenciar", False)
    d.clear()
    det.juego = True; ctl._tic()
    det.juego = False; ctl._tic()
    assert not [x for x in d if x[0] == "voz"]
    config.set("juego", "silenciar", True)
    voz.silenciada = True                              # ya estaba callada (por otra cosa)
    d.clear()
    det.juego = True; ctl._tic()
    det.juego = False; ctl._tic()
    assert not [x for x in d if x[0] == "voz"] and voz.silenciada is True


def test_sin_prioridad_ni_recorte_si_la_config_no_quiere(montaje, config):
    ctl, det, d = montaje["ctl"], montaje["det"], montaje["diario"]
    config.set("juego", "prioridad_baja", False)
    config.set("juego", "recortar_ram", False)
    d.clear()
    det.juego = True; ctl._tic()
    assert not [x for x in d if x[0] == "prioridad"] and not ctl._timer_recorte.isActive()


def test_cede_lo_que_manda_la_tabla_y_lo_reanuda(montaje):
    esc, ctl, det, d = montaje["esc"], montaje["ctl"], montaje["det"], montaje["diario"]
    esc.registrar("sentada", Sentada(d), actividades=("sentada",))
    assert esc.prioridad.iniciar("sentada", "barra")
    d.clear()
    det.juego = True; ctl._tic()
    assert ("ceder", "sentada", "barra") in d and esc.estado.actual().sentada == ""
    det.juego = False; ctl._tic()
    assert d[-1] == ("reanudar", "sentada", "barra") and esc.estado.actual().sentada == "barra"


def test_la_mascota_nueva_en_plena_partida_recibe_el_plan(montaje):
    esc, ctl, det, d, m = montaje["esc"], montaje["ctl"], montaje["det"], montaje["diario"], montaje["m"]
    det.juego = True; ctl._tic()
    nueva = MascotaFalsa(d, "nueva")
    esc.set_mascota(nueva)
    assert [p.accion for p in nueva.planes] == ["ocultar"]
    assert m.planes[-1] is not None                    # la vieja se suelta tal cual
    det.juego = False; ctl._tic()
    assert nueva.planes[-1] is None and len(m.planes) == 1


def test_forzar_se_aplica_al_momento(montaje):
    ctl, det = montaje["ctl"], montaje["det"]
    ctl.forzar(True)
    assert ctl.activo() and montaje["cambios"] == [(True, "forzado")]
    assert ctl.estado() == {"activo": True, "motivo": "forzado", "forzado": True, "exe": "juego.exe"}
    ctl.forzar(None)
    assert not ctl.activo() and montaje["cambios"][-1] == (False, "")


def test_detener_restaura(montaje):
    esc, ctl, det, d, m = montaje["esc"], montaje["ctl"], montaje["det"], montaje["diario"], montaje["m"]
    det.juego = True; ctl._tic()
    d.clear()
    esc.detener()
    assert not ctl.activo() and esc.estado.actual().juego is False
    assert ("prioridad", False) in d and ("voz", False) in d and m.planes[-1] is None
    assert montaje["cambios"][-1] == (False, "") and not ctl._timer.isActive()


def test_el_temporizador_evalua_solo(qapp, config):
    from ui.escritorio import ServiciosEscritorio
    from ui.modo_juego_qt import ControlModoJuego
    esc = ServiciosEscritorio(config)
    det = DetectorFalso()
    det.juego = True
    ctl = ControlModoJuego(esc, config, detector=det, recortar=lambda: (0.0, 0.0),
                           prioridad=lambda baja: None, intervalo_ms=10)
    ctl.iniciar()
    try:
        assert esperar(ctl.activo)
    finally:
        ctl.detener()
        esc.cerrar()


class _Api:
    """API de pantalla falsa mínima para el detector de verdad: QUNS 3."""
    def estado_notificaciones(self): return 3
    def ventana_activa(self): return 0
    def pid_propio(self): return 1000
    def hijos(self, pid): return []


def test_recargar_config_con_el_detector_apagado_sale(qapp, config):
    from servicios.win_pantalla import PidsLune
    from ui.escritorio import ServiciosEscritorio
    from ui.modo_juego_qt import ControlModoJuego
    esc = ServiciosEscritorio(config)
    api = _Api()
    det = mj.DetectorJuego(config, api, pids=PidsLune(api))
    ctl = ControlModoJuego(esc, config, detector=det, recortar=lambda: (0.0, 0.0),
                           prioridad=lambda baja: None, intervalo_ms=10_000)
    try:
        ctl._tic(); ctl._tic()
        assert ctl.activo() and ctl.estado()["motivo"] == "quns3"
        config.set("juego", "activo", False)
        ctl.recargar_config()
        assert not ctl.activo() and esc.estado.actual().juego is False
    finally:
        ctl.detener()
        esc.cerrar()


def test_recargar_config_con_otro_plan_en_partida(montaje, config):
    ctl, det, m = montaje["ctl"], montaje["det"], montaje["m"]
    det.juego = True; ctl._tic()
    config.set("juego", "accion", "fondo")
    ctl.recargar_config()
    assert [p.accion for p in m.planes] == ["ocultar", "fondo"]
    ctl.recargar_config()                              # mismo plan: no se repite
    assert len(m.planes) == 2


def test_recorte_automatico_fuera_de_partida_y_no_animando(montaje, config):
    ctl, det = montaje["ctl"], montaje["det"]
    config.set("sistema", "recorte_ram_auto", True)
    ctl.recargar_config()
    montaje["esc"].estado.actualizar(arrastrando=True)
    ctl._tic()
    time.sleep(0.05)
    assert montaje["recortes"] == []                   # arrastrándola no
    montaje["esc"].estado.actualizar(arrastrando=False)
    ctl._tic()
    assert esperar(lambda: montaje["recortes"])
    config.set("sistema", "recorte_ram_auto", False)
    ctl.recargar_config()
    assert not ctl._programador.activo
