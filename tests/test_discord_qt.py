"""
Tests de ControlDiscord (ui/discord_qt.py): el controlador de escritorio de la presencia.

Con el ServiciosEscritorio de verdad (su BusEstado y su señal estado_cambio) y una
presencia falsa que anota lo que le piden. Un par de tests usan la Presencia real
para comprobar que sin Application ID no se crea ningún hilo (D1).
"""
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discord_falso import ID, ConfigFalsa  # noqa: E402


class PresenciaFalsa:
    def __init__(self):
        self.estado_fn = None
        self.on_estado = None
        self.habilitaciones = []
        self.actualizaciones = 0
        self.cierres = []
        self.e = {"activo": False, "conectado": False, "usuario": "", "error": "",
                  "publicando": None, "sin_id": False}

    def habilitar(self, on):
        self.habilitaciones.append(bool(on))

    def actualizar(self):
        self.actualizaciones += 1

    def estado(self):
        return dict(self.e)

    def cerrar(self, timeout=1.0):
        self.cierres.append(timeout)


@pytest.fixture
def escritorio(qapp):
    from ui.escritorio import ServiciosEscritorio
    e = ServiciosEscritorio(None)
    yield e
    e.deleteLater()


def _control(escritorio, config=None, presencia=None, **kw):
    from ui.discord_qt import ControlDiscord
    p = presencia if presencia is not None else PresenciaFalsa()
    c = ControlDiscord(escritorio, config or ConfigFalsa(activo=True, client_id=ID), presencia=p, **kw)
    return c, p


def test_iniciar_habilita_segun_la_config_y_da_la_foto(escritorio):
    c, p = _control(escritorio, modo="br")
    c.iniciar()
    assert p.habilitaciones == [True]
    assert callable(p.estado_fn) and callable(p.on_estado)
    foto = p.estado_fn()
    assert foto["modo"] == "br" and foto["juego"] is False
    c.detener()


def test_un_cambio_del_bus_despierta_a_la_presencia(escritorio):
    c, p = _control(escritorio)
    c.iniciar()
    escritorio.estado.actualizar(arrastrando=True)
    assert p.actualizaciones == 1
    assert p.estado_fn()["arrastrando"] is True
    escritorio.estado.actualizar(sentada="barra", durmiendo=True)
    assert p.actualizaciones == 2
    c.detener()


def test_la_emocion_sola_no_despierta(escritorio):
    c, p = _control(escritorio)
    c.iniciar()
    escritorio.estado.actualizar(emocion="happy")
    assert p.actualizaciones == 0
    c.detener()


def test_apagada_no_despierta(escritorio):
    c, p = _control(escritorio, ConfigFalsa(activo=False, client_id=ID))
    c.iniciar()
    assert p.habilitaciones == [False]
    escritorio.estado.actualizar(hablando=True)
    assert p.actualizaciones == 0
    assert p.estado_fn()["hablando"] is True          # la foto sí se mantiene al día
    c.detener()


def test_alternar_guarda_y_enciende_o_apaga(escritorio):
    cfg = ConfigFalsa(activo=False, client_id=ID)
    c, p = _control(escritorio, cfg)
    c.iniciar()
    emitidos = []
    c.estado_cambio.connect(emitidos.append)
    assert c.alternar() is True
    assert cfg.get("discord", "activo") is True and c.activo is True
    assert c.alternar() is False
    assert cfg.sets == [("discord", "activo", True), ("discord", "activo", False)]
    assert p.habilitaciones == [False, True, False]
    assert json.loads(emitidos[-1])["activo"] is False
    c.detener()


def test_detener_cierra_la_presencia_y_deja_de_escuchar(escritorio):
    c, p = _control(escritorio)
    c.iniciar()
    c.detener()
    assert p.cierres == [1.0]
    escritorio.estado.actualizar(hablando=True)
    assert p.actualizaciones == 0
    c.detener()                                       # idempotente
    assert p.cierres == [1.0]


def test_recargar_config_mira_otra_vez_sin_reiniciar(escritorio):
    cfg = ConfigFalsa(activo=True, client_id="")
    c, p = _control(escritorio, cfg)
    c.iniciar()
    cfg.set("discord", "client_id", ID)
    c.recargar_config()
    assert p.habilitaciones == [True, True]
    assert p.actualizaciones == 1
    c.detener()


def test_estado_con_client_id_ok_y_lo_que_ve_discord(escritorio):
    cfg = ConfigFalsa(activo=True, client_id=ID)
    c, _p = _control(escritorio, cfg)
    c.iniciar()
    escritorio.estado.actualizar(render="vrm", visible=True)
    e = c.estado()
    assert e["activo"] is True and e["client_id_ok"] is True and e["sin_id"] is False
    assert e["vista_previa"] == {"details": "Lune CD · Mascota 3D", "state": "En el escritorio"}
    escritorio.estado.actualizar(juego=True)
    assert c.estado()["vista_previa"] is None
    cfg.set("discord", "client_id", "")
    e = c.estado()
    assert e["client_id_ok"] is False and e["sin_id"] is True
    c.detener()


def test_el_modelo_solo_si_se_pide(escritorio):
    cfg = ConfigFalsa(activo=True, client_id=ID)
    c, p = _control(escritorio, cfg, nombre_modelo=lambda: "Aria")
    c.iniciar()
    escritorio.estado.actualizar(render="vrm", visible=True)
    assert p.estado_fn()["modelo"] == ""
    cfg.set("discord", "mostrar_modelo", True)
    c.recargar_config()
    assert p.estado_fn()["modelo"] == "Aria"
    assert c.estado()["vista_previa"]["details"] == "Lune CD · Mascota 3D"
    c.detener()


def test_el_estado_de_la_presencia_llega_al_hilo_de_qt(qapp, escritorio):
    c, p = _control(escritorio)
    c.iniciar()
    emitidos = []
    c.estado_cambio.connect(emitidos.append)
    p.e.update(conectado=True, usuario="Diego",
               publicando={"details": "Lune CD · Ventana", "state": "Charlando"})
    hilo = threading.Thread(target=lambda: p.on_estado(p.estado()))
    hilo.start()
    hilo.join()
    for _ in range(20):
        qapp.processEvents()
        if emitidos:
            break
    assert emitidos, "estado_cambio no llegó"
    e = json.loads(emitidos[-1])
    assert e["conectado"] is True and e["publicando"]["state"] == "Charlando"
    c.detener()


def test_set_mascota_actualiza(escritorio):
    c, p = _control(escritorio)
    c.iniciar()
    c.set_mascota(object())
    assert p.actualizaciones == 1
    c.detener()


# ── Con la Presencia real ──────────────────────────────────────────────────────

def test_con_la_presencia_real_sin_id_no_hay_hilo(escritorio):
    from ui.discord_qt import ControlDiscord
    cfg = ConfigFalsa(activo=True, client_id="")
    c = ControlDiscord(escritorio, cfg)
    c.iniciar()
    escritorio.estado.actualizar(hablando=True)
    assert c._presencia._hilo is None
    e = c.estado()
    assert e["activo"] is True and e["sin_id"] is True and e["conectado"] is False and e["error"] == ""
    c.detener()


def test_con_la_presencia_real_apagada_no_hay_hilo(escritorio):
    from ui.discord_qt import ControlDiscord
    c = ControlDiscord(escritorio, ConfigFalsa(activo=False, client_id=ID))
    c.iniciar()
    escritorio.estado.actualizar(hablando=True)
    assert c._presencia._hilo is None
    assert c.estado()["activo"] is False
    c.detener()
