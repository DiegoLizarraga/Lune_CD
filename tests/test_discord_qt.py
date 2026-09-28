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
    from ui.discord_qt import ESPERA_DETENER_S
    assert p.cierres == [ESPERA_DETENER_S] and ESPERA_DETENER_S <= 0.25   # el hilo de Qt no espera 1 s
    escritorio.estado.actualizar(hablando=True)
    assert p.actualizaciones == 0
    c.detener()                                       # idempotente
    assert p.cierres == [ESPERA_DETENER_S]


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


# ── Revisión 7-10 (RR1): el hilo de la presencia sobrevive al desmontaje ───────

def test_tras_detener_el_hilo_de_la_presencia_ya_no_avisa(qapp, escritorio):
    """El hilo lee `on_estado` ANTES de que `detener` la cierre y avisa DESPUÉS (Discord
    lento). Ese aviso ya no llega al controlador, que el montaje borra justo después:
    antes era el `emit` ligado de su señal (access violation sobre el objeto borrado)."""
    c, p = _control(escritorio)
    c.iniciar()
    emitidos = []
    c.estado_cambio.connect(emitidos.append)
    aviso = p.on_estado                              # lo que el hilo ya tenía en la mano
    c.detener()
    assert p.on_estado is None
    hilo = threading.Thread(target=lambda: aviso({"conectado": False}))
    hilo.start()
    hilo.join()
    for _ in range(20):
        qapp.processEvents()
    assert emitidos == []
    # un iniciar posterior vuelve a enganchar un puente nuevo
    c.iniciar()
    assert callable(p.on_estado) and p.on_estado is not aviso
    hilo = threading.Thread(target=lambda: p.on_estado({"conectado": True}))
    hilo.start()
    hilo.join()
    for _ in range(20):
        qapp.processEvents()
        if emitidos:
            break
    assert emitidos
    c.detener()


def test_el_puente_no_toca_un_objeto_borrado(qapp):
    from PyQt6 import sip
    from PyQt6.QtCore import QObject, pyqtSignal
    from ui.escritorio import PuenteHilo

    class Emisor(QObject):
        senal = pyqtSignal(object)

    e = Emisor()
    puente = PuenteHilo(e, "senal")
    sip.delete(e)
    hilo = threading.Thread(target=lambda: puente({"x": 1}))   # sin excepción ni caída
    hilo.start()
    hilo.join()
    assert puente.abierto is False


_GUION_DESMONTAJE = '''
import os, sys, threading, time, faulthandler
faulthandler.enable()
sys.path.insert(0, sys.argv[1])
from PyQt6.QtCore import QObject, QCoreApplication, QEventLoop
app = QCoreApplication(sys.argv[:1])
from servicios import discord_presencia as dp
from ui.discord_qt import ControlDiscord
en_set = threading.Semaphore(0)

class Cfg:
    def get(self, s, k, d=None):
        return {"activo": True, "client_id": "123456789012345678"}.get(k, d) if s == "discord" else d
    def set(self, *a):
        pass

class ClienteLento:
    """Discord no contesta al SET_ACTIVITY: el cliente espera su tope entero."""
    conectado, usuario, error, codigo_cierre = True, "yo", "", 0
    def __init__(self, cid):
        pass
    def conectar(self, timeout_s=5.0, *, cancelar=None):
        return {"ok": True, "usuario": "yo"}
    def set_activity(self, act, pid, **kw):
        en_set.release()
        time.sleep(1.2)
        return {"ok": False, "error": "sin respuesta"}
    def atender(self):
        pass
    def cerrar(self, limpiar=True):
        if limpiar:
            self.set_activity(None, 0)

class Mutex:
    def __init__(self, n):
        pass
    def adquirir(self):
        return True
    def liberar(self):
        pass

def procesar(s):
    fin = time.monotonic() + s
    while time.monotonic() < fin:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        app.sendPostedEvents(None, 52)          # QEvent.DeferredDelete
        time.sleep(0.01)

padres = [QObject() for _ in range(3)]
pres = [dp.Presencia(Cfg(), lambda: {}, cliente=ClienteLento, mutex=Mutex) for _ in padres]
ctl = [ControlDiscord(None, Cfg(), presencia=p, parent=padre) for p, padre in zip(pres, padres)]
for c in ctl:
    c.iniciar()
for _ in ctl:
    assert en_set.acquire(timeout=10)            # los tres hilos, dentro de set_activity
espera, basura = 0.0, []
for c, padre in zip(ctl, padres):
    t0 = time.monotonic()
    c.detener()                                  # el hilo sigue vivo (Discord lento)
    espera = max(espera, time.monotonic() - t0)
    padre.deleteLater()                          # soltar_objetos del montaje
    procesar(0.05)
    # la ventana nueva crea lo suyo: la memoria liberada se recicla
    basura += [ControlDiscord(None, Cfg(), presencia=dp.Presencia(Cfg(), lambda: {}, cliente=ClienteLento,
                                                                   mutex=Mutex, hilo=False))
               for _ in range(100)]
fin = time.monotonic() + 8
while time.monotonic() < fin and any(h.name == "LuneDiscordRPC" for h in threading.enumerate()):
    procesar(0.05)
vivos = sum(h.name == "LuneDiscordRPC" for h in threading.enumerate())
print("FIN_NORMAL vivos=%d espera=%.2f" % (vivos, espera), flush=True)
'''


def test_desmontar_con_discord_lento_no_tumba_la_app(tmp_path):
    """RR1 de punta a punta, en otro proceso (la caída mataba pytest): ControlDiscord y
    Presencia de verdad, Discord que no contesta, desmontaje como el de un cambio de
    interfaz (detener + deleteLater) y memoria reciclada mientras los hilos terminan.
    Antes: access violation 3 de cada 4 veces por controlador."""
    import os
    import subprocess
    raiz = str(Path(__file__).resolve().parent.parent)
    guion = tmp_path / "desmontaje_discord.py"
    guion.write_text(_GUION_DESMONTAJE, encoding="utf-8")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(guion), raiz], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=90, env=env, cwd=raiz)
    assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-3000:])
    linea = [x for x in r.stdout.splitlines() if x.startswith("FIN_NORMAL")]
    assert linea, r.stdout
    vivos = int(linea[0].split("vivos=")[1].split()[0])
    espera = float(linea[0].split("espera=")[1])
    assert vivos == 0                               # cerraron solos, sin avisar a nadie
    assert espera < 0.5                             # detener no deja el hilo de Qt 1 s parado


def test_discord_ve_se_refresca_aunque_la_presencia_no_avise(qapp, escritorio):
    """Sospecha de la revisión 7-10: con Discord cerrado la presencia no cambia de estado
    (no avisa) y la línea «Discord ve: …» de la tarjeta se quedaba con lo de antes."""
    c, p = _control(escritorio)
    c.iniciar()
    emitidos = []
    c.estado_cambio.connect(lambda s: emitidos.append(json.loads(s)))
    escritorio.estado.actualizar(sentada="barra")
    assert emitidos and emitidos[-1]["vista_previa"]["state"] == "Sentada en la barra de tareas"
    n = len(emitidos)
    escritorio.estado.actualizar(emocion="happy")          # no cambia lo publicado
    escritorio.estado.actualizar(llamada=False)            # ni esto (ya lo era)
    assert len(emitidos) == n
    escritorio.estado.actualizar(juego=True)
    assert emitidos[-1]["vista_previa"] is None            # con un juego, nada
    c.detener()
    escritorio.estado.actualizar(juego=False)              # detenido: ya no emite
    assert emitidos[-1]["vista_previa"] is None
