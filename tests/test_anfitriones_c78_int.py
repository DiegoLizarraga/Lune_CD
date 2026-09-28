"""
Integración final de los cortes 7 y 8 en las ventanas, en main.py y en patata.

Web: `VentanaWeb.__init__` de verdad con Chromium sustituido (el arnés de
tests/test_anfitriones_corte4.py) → el objeto `vida` del canal está antes de setUrl, se
enlaza con los controladores de verdad (tests/vida_falsa_c78.py) al montar y salir
desmonta una vez. Cambio de interfaz en caliente (web → nativa → web): nunca dos
ControlAsiento ni dos presencias de Discord a la vez, y la entrada de arranque con
Windows sigue al modo. Nativa: la vida va con el corte 4. Ajustes nativos: el panel de
vida recibe los servicios, «Guardar» escribe lo pendiente y la casilla del autoinicio deja
`sistema.autoinicio` como el registro. Chat (web y nativa): «siéntate en la barra» sale
como Llamada por el Ejecutor sin pasar por la memoria; «¿te puedes sentar?» NO.
main.py: plan de arranque (splash, bandeja, mascota, ventana, espera), instancia única
silenciosa, reparar la entrada al arrancar y al cambiar de modo, patata minimizada.
Patata: comida y Discord/autoinicio sin Qt, /ayuda, «Pensando…», --autoinicio.
Nada de registro de Windows, config.json de verdad, audio ni Discord.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("PyQt6.QtWidgets")
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
except ImportError:
    pass

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

import test_anfitriones_corte4 as c4  # noqa: E402
import vida_falsa_c78 as vf  # noqa: E402
from test_anfitriones_corte4 import ajustes, entorno, sistema  # noqa: E402,F401  (fixtures)
from nucleo.config import Config  # noqa: E402

CANAL_C78 = ["alarmas", "escenario", "escritorio", "lune", "musica", "vida"]
ACCIONES_VIDA = ("sentarse", "bajar", "comer_batido", "comer_pastel", "guardar_comida", "comida", "discord")
ID_DISCORD = "123456789012345678"


@pytest.fixture
def vida(entorno, monkeypatch):
    """El arnés del corte 4 con sentarse, comida y Discord de verdad (dobles del sistema)."""
    reg = vf.Registro()
    fab = dict(c4.fabricas(), vida=vf.fabricas_vida(reg))
    monkeypatch.setattr(entorno.ws.VentanaWeb, "FABRICAS_C4", fab)
    monkeypatch.setattr(entorno.main.LuneCDWindow, "FABRICAS_C4", fab)
    contador = {"desmontar": 0}
    from ui.montaje_vida import ServiciosVida
    real = ServiciosVida.desmontar

    def desmontar(self):
        if not self.desmontado:
            contador["desmontar"] += 1
        return real(self)
    monkeypatch.setattr(ServiciosVida, "desmontar", desmontar)
    entorno.reg, entorno.cuenta = reg, contador
    return entorno


def _vivos(reg):
    return len(reg.asientos_vivos()), len(reg.comidas_vivas()), len(reg.discords_vivos())


# ═══ Web ══════════════════════════════════════════════════════════════════════

def test_web_registra_el_puente_vida_antes_de_cargar_y_lo_enlaza(vida, sistema):
    v = vida.web()
    assert v.web.objetos_al_cargar == CANAL_C78                         # window.luneVida
    s = v._servicios_c4
    vv = s.vida
    assert vv is not None and vv.asiento is vida.reg.asientos[-1] and vv.comida is vida.reg.comidas[-1]
    pv = v._puente_vida
    assert pv.asiento is vv.asiento and pv.comida is vv.comida and pv.discord is vv.discord
    for h in ("mascota_sentarse", "dar_de_comer"):
        assert v.bridge.tools.tiene_handler(h), h                      # el ToolManager del puente
    for a in ACCIONES_VIDA:
        assert s.despachador.tiene(a), a
    assert _vivos(vida.reg) == (1, 1, 1)
    # Lo que pide la página llega a los controladores de verdad.
    assert json.loads(pv.comida_estado())["servicio"] is True
    r = json.loads(pv.comida_alternar("pastel"))
    assert r["ok"] and r["accion"] == "aparece" and vv.comida.activa[0] == "pastel"
    assert pv.comida_guardar() is True and vv.comida.activa is None


def test_web_salir_desmonta_la_vida_una_sola_vez(vida, sistema):
    v = vida.web()
    canal, vv = v._canal, v._servicios_c4.vida
    v.salir_de_verdad()
    v.bridge.cerrar_escritorio()
    assert vida.cuenta["desmontar"] == 1 and vv.desmontado
    assert _vivos(vida.reg) == (0, 0, 0) and vida.reg.presencias_publicando() == []
    assert "vida" not in canal.registrados and v._puente_vida is None
    v._liberar_todo()
    assert vida.cuenta["desmontar"] == 1


def test_web_diferida_registra_el_puente_pero_monta_al_final(vida, sistema):
    vieja = vida.web()
    nueva = vida.web(diferir=True)
    assert nueva.web.objetos_al_cargar == CANAL_C78
    assert nueva._servicios_c4 is None and nueva._puente_vida.asiento is None
    assert _vivos(vida.reg) == (1, 1, 1)                               # solo los de la vieja
    vieja.cerrar_para_cambio()
    assert _vivos(vida.reg) == (0, 0, 0)
    nueva.iniciar_servicios({})
    assert nueva._puente_vida.asiento is nueva._servicios_c4.vida.asiento
    assert _vivos(vida.reg) == (1, 1, 1)


def test_relevo_en_caliente_un_solo_asiento_y_una_presencia_y_repara_el_autoinicio(vida, sistema, qapp,
                                                                                     monkeypatch, tmp_path):
    import main
    import nucleo.config as nc
    from servicios import autoinicio
    from ui.cambio_interfaz import GestorInterfaz
    Real = nc.Config
    monkeypatch.setattr(nc, "Config", lambda *a, **k: Real(str(tmp_path / "config_gestor.json")))
    reparados = []
    monkeypatch.setattr(autoinicio, "reparar", lambda config=None, modo=None, reg=None: reparados.append(modo) or "")
    vida.cfg.set("discord", "activo", True)
    vida.cfg.set("discord", "client_id", ID_DISCORD)

    def fabrica(modo):
        return vida.web(diferir=True) if modo == "web" else vida.nativa()
    g = GestorInterfaz(fabrica, guardar_modo=main._guardar_modo_interfaz, animar=lambda v, ms, fin: fin(),
                       fundido_ms=0, tope_carga_ms=10)
    reg = vida.reg
    web = vida.web()
    g.adoptar(web)

    def comprobar(ventana):
        vv = ventana._servicios_c4.vida
        assert vv is not None and not vv.desmontado
        assert reg.asientos_vivos() == [vv.asiento] and reg.discords_vivos() == [vv.discord]
        assert reg.comidas_vivas() == [vv.comida]
        assert len(reg.presencias_publicando()) == 1                   # nunca dos publicando
    comprobar(web)
    assert g.cambiar("nativo") is True
    nat = g.ventana
    comprobar(nat)
    assert reparados == ["nativo"]                                     # la entrada Run sigue al modo
    assert Real(str(tmp_path / "config_gestor.json")).get("interfaz", "modo") == "nativo"
    assert g.cambiar("web") is True
    assert c4._esperar(qapp, lambda: g.ventana is not nat and not g.cambiando)
    comprobar(g.ventana)
    assert reparados == ["nativo", "web"]
    assert len(reg.asientos) == 3 and len(reg.presencias) == 3        # una por ventana, las viejas cerradas
    assert all(p.cerrada >= 1 for p in reg.presencias[:2])


class _Acciones:
    def __init__(self):
        self.ejecutadas, self.ejecutor = [], None

    def ejecutar(self, llamadas, origen, ctx):
        self.ejecutadas.append((llamadas, origen, ctx))

    def pendientes(self):
        return []

    def cerrar(self):
        pass


class _Memoria:
    def __init__(self, respuesta=None):
        self.vistos, self.respuesta = [], respuesta

    def procesar_mensaje_usuario(self, t):
        self.vistos.append(t)
        return self.respuesta

    def obtener_contexto_para_prompt(self):
        return ""


def test_web_chat_sientate_sale_como_llamada_y_la_pregunta_no(vida, sistema):
    from lune_core.acciones import USUARIO
    v = vida.web()
    b = v.bridge
    b.memoria, b.acciones = _Memoria(), _Acciones()
    ia = []
    b._arrancar_ia = lambda mensaje, *a, **k: ia.append(mensaje)
    assert b._enviar("siéntate en la barra", b._provider_web) is True
    llamadas, origen, _ctx = b.acciones.ejecutadas[-1]
    assert origen == USUARIO and [(x.herramienta, x.args, x.directa) for x in llamadas] == [
        ("mascota_sentarse", {"sitio": "barra"}, True)]
    assert b.memoria.vistos == [] and ia == []                         # antes que la memoria y sin IA
    b._enviar("toma un pastel", b._provider_web)
    assert [x.herramienta for x in b.acciones.ejecutadas[-1][0]] == ["dar_de_comer"]
    # Una pregunta no es una orden: memoria y modelo, como siempre.
    b._enviar("¿te puedes sentar?", b._provider_web)
    assert len(b.acciones.ejecutadas) == 2
    assert b.memoria.vistos == ["¿te puedes sentar?"] and ia == ["¿te puedes sentar?"]


# ═══ Nativa ═══════════════════════════════════════════════════════════════════

def test_nativa_monta_la_vida_y_salir_la_desmonta_una_vez(vida, sistema):
    panel = c4.PanelFalso()
    yo = vida.nativa(panel=panel)
    yo.iniciar_servicios({})
    s = yo._servicios_c4
    assert panel.recibidos == [s] and s.vida is not None
    assert {"asiento", "comida", "discord"} <= set(yo.escritorio.controladores())
    for a in ACCIONES_VIDA:
        assert s.despachador.tiene(a), a
    assert _vivos(vida.reg) == (1, 1, 1)
    yo._quit_real = True
    yo.closeEvent(c4.Evento())
    assert vida.cuenta["desmontar"] == 1 and _vivos(vida.reg) == (0, 0, 0)


def test_nativa_chat_sientate_va_al_ejecutor_y_la_pregunta_no(qapp, monkeypatch):
    import main
    from lune_core.acciones import USUARIO
    from servicios.tools import ToolManager
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: object())
    ejecutadas = []
    memoria = _Memoria(respuesta="(la memoria contesta)")          # así la pregunta no llega al modelo
    texto = {"t": "Lune, siéntate en la barra"}
    yo = types.SimpleNamespace(
        _worker_vivo=lambda: False, _set_status=lambda *a: None, current_provider="ollama", _turno={},
        stack=types.SimpleNamespace(setCurrentIndex=lambda i: None), _cancelar_plan=lambda: None,
        voice=types.SimpleNamespace(cancelar=lambda: None),
        messages_layout=types.SimpleNamespace(insertWidget=lambda *a: None, count=lambda: 1),
        input_field=types.SimpleNamespace(text=lambda: texto["t"], clear=lambda: None),
        _adjuntos=[], _refrescar_adjuntos=lambda: None, _guardar_turno=lambda *a, **k: None,
        memoria=memoria, tools=ToolManager(), ai_manager=types.SimpleNamespace(providers={}),
        _modo_acciones=lambda: "vrm", _scroll_bottom=lambda: None, _burbuja_bot=lambda t: None,
        _eco_mascota=lambda *a, **k: None,
        lune_face=types.SimpleNamespace(set_state=lambda *a, **k: None),
        _ejecutar_acciones=lambda ll, origen, ctx, **kw: ejecutadas.append((ll, origen, dict(ctx), kw)))
    main.LuneCDWindow._send_message(yo)
    ll, origen, ctx, kw = ejecutadas[-1]
    assert origen == USUARIO and kw["directo"] is True and memoria.vistos == [] and ctx["modo"] == "vrm"
    assert [(x.herramienta, x.args) for x in ll] == [("mascota_sentarse", {"sitio": "barra"})]
    texto["t"] = "¿te puedes sentar?"
    main.LuneCDWindow._send_message(yo)
    assert len(ejecutadas) == 1 and memoria.vistos == ["¿te puedes sentar?"]


# ═══ Ajustes nativos ══════════════════════════════════════════════════════════

class _Ctl:
    def __init__(self, estado=None):
        self.llamadas, self._estado = [], estado or {}

    def recargar_config(self):
        self.llamadas.append("recargar_config")

    def estado(self):
        return dict(self._estado)


def test_ajustes_nativos_enlazan_y_guardan_el_panel_de_vida(ajustes, monkeypatch):
    from servicios import autoinicio
    from ui.panel_vida_nativo import PanelVidaNativo
    caja = {"s": None}
    p = ajustes.crear(lambda: caja["s"])
    panel = p.vida_panel
    try:
        assert isinstance(panel, PanelVidaNativo) and panel.asiento is None and panel.discord is None
        vv = types.SimpleNamespace(asiento=_Ctl({"sentada": ""}), comida=_Ctl({"activa": False}),
                                   discord=_Ctl({"activo": False}))
        s = types.SimpleNamespace(vida=vv, ocio=None, atajos=None, _deshacer=[], desmontar=lambda: None)
        caja["s"] = s
        p.usar_servicios(s)
        assert panel.asiento is vv.asiento and panel.comida is vv.comida and panel.discord is vv.discord
        # «Guardar configuración» escribe lo pendiente del panel y lo aplica en caliente.
        panel._poner("asiento", "avatar", "sentarse_offset_px", 12)
        # La casilla «Arrancar Lune junto con Windows»: sistema.autoinicio queda como el registro.
        monkeypatch.setattr(autoinicio, "establecer", lambda quiere, modo=None, reg=None: bool(quiere))
        p.autoinicio_check.setChecked(True)
        p._save()
        assert vv.asiento.llamadas == ["recargar_config"]
        guardada = Config(str(ajustes.cfg.config_path))
        assert guardada.get("avatar", "sentarse_offset_px") == 12
        assert guardada.get("sistema", "autoinicio") is True
        # Al desmontar los servicios, el panel los suelta.
        for f in s._deshacer:
            f()
        assert panel.asiento is None and panel.comida is None and panel.discord is None
    finally:
        panel._timer.stop()


def test_web_bridge_autoinicio_set_sincroniza_la_config_solo_si_cambia(vida, monkeypatch):
    from servicios import autoinicio
    v = vida.web()
    b = v.bridge
    escrituras = []
    real_set = b.config.set

    def set_(s, k, valor):
        escrituras.append((s, k, valor))
        return real_set(s, k, valor)
    monkeypatch.setattr(b.config, "set", set_)
    monkeypatch.setattr(autoinicio, "establecer", lambda quiere, modo=None, reg=None: False)
    assert b.autoinicio_set(True) is False                             # Windows no lo dejó
    assert escrituras == []                                            # ya era False: nada que escribir
    monkeypatch.setattr(autoinicio, "establecer", lambda quiere, modo=None, reg=None: True)
    assert b.autoinicio_set(True) is True
    assert escrituras == [("sistema", "autoinicio", True)]


# ═══ main.py: arranque ════════════════════════════════════════════════════════

def test_plan_de_arranque_a_mano_y_con_windows(tmp_path):
    import main
    cfg = Config(str(tmp_path / "config.json"))
    opc, plan, c = main._preparar_arranque([], config=cfg)
    assert c is cfg and opc.autoinicio is False and plan.splash is True and plan.mostrar_ventana is True
    cfg.set("sistema", "autoinicio_como", "mascota")
    cfg.set("sistema", "autoinicio_retraso_s", 7)
    opc, plan, _ = main._preparar_arranque(["--autoinicio"], config=cfg)
    assert opc.autoinicio is True
    assert (plan.splash, plan.mostrar_ventana, plan.abrir_mascota, plan.retraso_s, plan.silencioso) == (
        False, False, True, 7, True)


class _VentanaFalsa:
    def __init__(self, tray=True, desp=None):
        self.diario, self.tray = [], (object() if tray else None)
        self._servicios_c4 = types.SimpleNamespace(despachador=desp) if desp is not None else None
        self._estado = 0

    def show(self):
        self.diario.append("show")

    def windowState(self):
        from PyQt6.QtCore import Qt
        return Qt.WindowState.WindowNoState

    def setWindowState(self, e):
        pass

    def showNormal(self):
        self.diario.append("showNormal")

    def raise_(self):
        pass

    def activateWindow(self):
        pass


class _Desp:
    def __init__(self, ok=True):
        self.ejecutadas, self.ok = [], ok

    def ejecutar(self, id_, *a):
        self.ejecutadas.append(id_)
        return self.ok


def test_presentar_la_ventana_segun_el_plan():
    import main
    from nucleo import arranque
    normal = arranque.PLAN_NORMAL

    def plan(como):
        return arranque.plan_arranque({"sistema": {"autoinicio_como": como}}, arranque.Opciones(True))
    w = _VentanaFalsa()
    assert main._presentar_principal(w, normal) == "ventana" and "show" in w.diario
    w = _VentanaFalsa()
    assert main._presentar_principal(w, plan("bandeja")) == "bandeja" and w.diario == []   # solo el icono
    w = _VentanaFalsa()
    assert main._presentar_principal(w, plan("bandeja"), mostrar=True) == "ventana"          # la abriste tú
    w = _VentanaFalsa()
    assert main._presentar_principal(w, plan("ventana")) == "ventana"
    d = _Desp()
    w = _VentanaFalsa(desp=d)
    assert main._presentar_principal(w, plan("mascota")) == "mascota" and d.ejecutadas == ["mascota"]
    assert w.diario == []
    # Sin icono de bandeja nunca queda invisible (ni si la mascota no pudo salir).
    w = _VentanaFalsa(tray=False)
    assert main._presentar_principal(w, plan("bandeja")) == "ventana" and "show" in w.diario
    w = _VentanaFalsa(tray=False, desp=_Desp(ok=False))
    assert main._presentar_principal(w, plan("mascota")) == "ventana"


def test_presentar_con_la_ventana_web_de_verdad_en_la_bandeja_o_con_la_mascota(entorno, sistema):
    import main
    from nucleo import arranque
    v = entorno.web()
    plan = arranque.plan_arranque({"sistema": {"autoinicio_como": "bandeja"}}, arranque.Opciones(True))
    assert main._presentar_principal(v, plan) == "bandeja"
    assert not v.isVisible() and v.tray is v._servicios_c4.bandeja.icono_tray and len(sistema.iconos) == 1
    plan = arranque.plan_arranque({"sistema": {"autoinicio_como": "mascota"}}, arranque.Opciones(True))
    assert main._presentar_principal(v, plan) == "mascota"
    assert not v.isVisible() and c4.MascotaFalsa.creadas and c4.MascotaFalsa.creadas[-1].visible


class _Servidor(QObject):
    newConnection = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.pendientes = []

    def hasPendingConnections(self):
        return bool(self.pendientes)

    def nextPendingConnection(self):
        return self.pendientes.pop(0) if self.pendientes else None

    def llega(self, s):
        self.pendientes.append(s)
        self.newConnection.emit()


class _Socket(QObject):
    readyRead = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, datos=b""):
        super().__init__()
        self.buf = bytearray(datos)
        self.borrado = False

    def bytesAvailable(self):
        return len(self.buf)

    def readAll(self):
        d, self.buf = bytes(self.buf), bytearray()
        return d

    def escribe(self, d):
        self.buf += d
        self.readyRead.emit()

    def deleteLater(self):
        self.borrado = True


def test_avisos_de_instancia_solo_callan_con_silencio(qapp):
    import main
    srv = _Servidor()
    avisos = main._AvisosInstancia(srv)
    vistos = []
    avisos.newConnection.connect(lambda: vistos.append(1))
    assert avisos.hasPendingConnections() is False and avisos.nextPendingConnection() is None
    s = _Socket(main.PEDIR_MOSTRAR)                                    # abriste Lune otra vez
    srv.llega(s)
    assert vistos == [1]
    s.disconnected.emit()
    assert vistos == [1] and s.borrado                                 # una vez por conexión
    s = _Socket(main.PEDIR_SILENCIO)                                   # el arranque con Windows
    srv.llega(s)
    s.disconnected.emit()
    assert vistos == [1] and s.borrado
    tarde = _Socket()                                                  # los datos llegan después
    srv.llega(tarde)
    assert vistos == [1]
    tarde.escribe(b"most")
    tarde.escribe(b"rar")
    assert vistos == [1, 1]
    tarde.escribe(b"mostrar")
    tarde.disconnected.emit()
    assert vistos == [1, 1]
    muda = _Socket()                                                   # una Lune de antes, o sin datos
    srv.llega(muda)
    muda.disconnected.emit()
    assert vistos == [1, 1, 1]


class _SocketYaCerrado(_Socket):
    """Escribió y se desconectó ANTES de que _AvisosInstancia conectara `disconnected`:
    esa señal ya no llegará nunca."""

    def state(self):
        from PyQt6.QtNetwork import QLocalSocket
        return QLocalSocket.LocalSocketState.UnconnectedState


def test_avisos_de_instancia_con_un_socket_que_ya_se_fue(qapp):
    """Sospecha de la revisión 7-10: su entrada se quedaba en _leidos para siempre (y un id
    reciclado la mezclaba con otra conexión) y el socket no se borraba; una Lune de antes
    (sin datos) que se iba enseguida no traía la primera al frente."""
    import main
    srv = _Servidor()
    avisos = main._AvisosInstancia(srv)
    vistos = []
    avisos.newConnection.connect(lambda: vistos.append(1))
    s = _SocketYaCerrado(main.PEDIR_SILENCIO)
    srv.llega(s)
    assert vistos == [] and avisos._leidos == {} and s.borrado
    s = _SocketYaCerrado()                                             # muda: como siempre, al frente
    srv.llega(s)
    assert vistos == [1] and avisos._leidos == {} and s.borrado
    s = _SocketYaCerrado(main.PEDIR_MOSTRAR)
    srv.llega(s)
    assert vistos == [1, 1] and avisos._leidos == {} and s.borrado


SERVIDOR_INSTANCIA = r'''
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, {raiz!r})
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
app = QApplication([])
import main
print("LISTO", main._ya_hay_una_instancia(clave={clave!r}), flush=True)
avisos = main._AvisosInstancia(main.__dict__["_servidor_instancia"])
avisos.newConnection.connect(lambda: print("MOSTRAR", flush=True))
QTimer.singleShot({ms}, app.quit)
app.exec()
print("FIN", flush=True)
'''


def test_instancia_unica_silenciosa_entre_procesos(qapp, tmp_path):
    """La primera Lune (otro proceso con su bucle de Qt) solo se trae al frente con una
    segunda normal; la del arranque con Windows se va sin tocarla."""
    import time
    import uuid
    import main
    clave = f"LuneCD-test-{uuid.uuid4().hex}"
    guion = tmp_path / "servidor_instancia.py"
    guion.write_text(SERVIDOR_INSTANCIA.format(raiz=str(RAIZ), clave=clave, ms=6000), encoding="utf-8")
    srv = subprocess.Popen([sys.executable, str(guion)], stdout=subprocess.PIPE, text=True,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        assert srv.stdout.readline().strip() == "LISTO False"
        time.sleep(0.3)
        assert main._ya_hay_una_instancia(silencioso=True, clave=clave) is True
        time.sleep(0.8)
        assert main._ya_hay_una_instancia(clave=clave) is True
        salida = srv.communicate(timeout=30)[0]
    finally:
        if srv.poll() is None:
            srv.kill()
    assert salida.split() == ["MOSTRAR", "FIN"], salida


def test_esperar_y_abrir_una_vez_o_ya_si_la_abres(qapp):
    import main
    programados = []

    def programar(ms, fn):
        programados.append((ms, fn))
    abiertas = []
    avisos = main._AvisosInstancia(_Servidor())
    main._abrir_tras_espera(20, lambda mostrar=False: abiertas.append(mostrar), avisos, programar=programar)
    assert programados[0][0] == 20000 and abiertas == []
    programados[0][1]()                                                # vence la espera
    assert abiertas == [False]
    avisos.newConnection.emit()                                        # ya abierta: el gestor se encarga
    programados[0][1]()
    assert abiertas == [False]
    # Si la abres a mano durante la espera: ya y a la vista; al vencer, nada más.
    programados.clear()
    abiertas.clear()
    main._abrir_tras_espera(20, lambda mostrar=False: abiertas.append(mostrar), avisos, programar=programar)
    avisos.newConnection.emit()
    assert abiertas == [True]
    programados[0][1]()
    assert abiertas == [True]


class _AutoFalso:
    def __init__(self, motivo="", activo=False):
        self.reparados, self.motivo, self._activo = [], motivo, activo

    def reparar(self, config=None, modo=None, reg=None):
        self.reparados.append((config, modo))
        return self.motivo

    def activo(self, reg=None):
        return self._activo


def test_reparar_autoinicio_al_arrancar_sigue_al_modo_y_sincroniza_la_config(tmp_path):
    import main
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("interfaz", "modo", "patata")
    cfg.set("sistema", "autoinicio", True)
    mod = _AutoFalso(motivo="ruta", activo=False)                     # deshabilitada en el Administrador
    assert main._reparar_autoinicio(cfg, mod=mod) == "ruta"
    assert mod.reparados == [(cfg, "patata")] and cfg.get("sistema", "autoinicio") is False
    mod = _AutoFalso(activo=True)
    assert main._reparar_autoinicio(cfg, "web", mod=mod) == "" and cfg.get("sistema", "autoinicio") is True
    assert mod.reparados == [(cfg, "web")]

    class Roto:
        def reparar(self, *a, **k):
            raise OSError("registro")
    assert main._reparar_autoinicio(cfg, mod=Roto()) == ""            # nunca tumba el arranque


def test_guardar_el_modo_de_interfaz_repara_la_entrada_y_el_gestor_lo_usa(monkeypatch, tmp_path):
    import main
    import nucleo.config as nc
    from servicios import autoinicio
    Real = nc.Config
    ruta = str(tmp_path / "config.json")
    monkeypatch.setattr(nc, "Config", lambda *a, **k: Real(ruta))
    reparados = []
    monkeypatch.setattr(autoinicio, "reparar", lambda config=None, modo=None, reg=None: reparados.append(
        (config, modo)) or "modo")
    g = main._crear_gestor_interfaz()
    assert g._guardar_modo is main._guardar_modo_interfaz and g._lanzar_patata is main._lanzar_patata
    g._guardar("patata")                                               # lo que hace el cambio en caliente
    assert Real(ruta).get("interfaz", "modo") == "patata" and reparados == [(None, "patata")]


def test_lanzar_patata_con_windows_va_minimizada(monkeypatch):
    import main
    llamadas = []

    class Popen:
        def __init__(self, args, **kw):
            llamadas.append((list(args), kw))
    monkeypatch.setattr(subprocess, "Popen", Popen)
    monkeypatch.setattr(main, "_patata_ya_abierta", lambda mostrar=True: False)   # sin mirar una real
    assert main._lanzar_patata() is True
    args, kw = llamadas[-1]
    assert args[-1].endswith("patata.py") and "startupinfo" not in kw
    assert main._lanzar_patata(autoinicio=True) is True
    args, kw = llamadas[-1]
    assert args[-2].endswith("patata.py") and args[-1] == "--autoinicio"
    if os.name == "nt":
        si = kw["startupinfo"]
        assert si.wShowWindow == 7 and si.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert kw["creationflags"] & subprocess.CREATE_NEW_CONSOLE


def test_crear_ventana_principal_en_patata_con_windows(monkeypatch, tmp_path):
    import main
    import nucleo.config as nc
    Real = nc.Config
    ruta = str(tmp_path / "config.json")
    Real(ruta).set("interfaz", "modo", "patata")
    monkeypatch.setattr(nc, "Config", lambda *a, **k: Real(ruta))
    pedidas = []
    monkeypatch.setattr(main, "_lanzar_patata", lambda autoinicio=False: pedidas.append(autoinicio) or True)
    assert main._crear_ventana_principal(autoinicio=True) is None and pedidas == [True]
    assert main._crear_ventana_principal() is None and pedidas == [True, False]


def test_main_sigue_usando_el_gestor_y_el_plan():
    import inspect
    import main
    fuente = inspect.getsource(main.main)
    for trozo in ("_preparar_arranque(sys.argv[1:])", "_ya_hay_una_instancia(silencioso=plan.silencioso)",
                  "_reparar_autoinicio(cfg)", "_presentar_principal(", "_abrir_tras_espera(",
                  "_crear_gestor_interfaz()", "gestor.adoptar(ventana)", "gestor.conectar_servidor("):
        assert trozo in fuente, trozo


# ═══ Patata ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def patata_c78(tmp_path, monkeypatch):
    import patata
    import test_patata as tp
    from nucleo import datos
    from nucleo.consola import ConsolaAsincrona
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    creadas = []

    def crear(**kw):
        entrada, out, api = tp.EntradaBloqueante(), io.StringIO(), tp.ApiFalsa()
        consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=api, ansi=False)
        cfg = Config(str(tmp_path / "config.json"))
        for pieza in ("alarmas", "baile", "salvapantallas"):
            kw.setdefault(pieza, None)
        kw.setdefault("memoria", _Memoria())
        kw.setdefault("ai", tp.AIFalsa("Vale :D"))
        kw.setdefault("juego", c4.DetectorFalso())
        kw.setdefault("prioridad", lambda baja: None)
        kw.setdefault("autoinicio", AutoPatata())
        p = patata.Patata(color=False, consola=consola, config=cfg, voice=None, audit_path=None, **kw)
        p.entrada, p.out, p.api, p.cfg = entrada, out, api, cfg
        creadas.append(p)
        return p
    yield crear
    for p in creadas:
        p.entrada.put(None)
        p.cerrar()
    datos.invalidar()


class AutoPatata:
    """servicios.autoinicio para patata (sin registro)."""

    def __init__(self):
        self.on, self.modos, self.reparados = False, [], []

    def activo(self, reg=None):
        return self.on

    def establecer(self, quiere, modo=None, reg=None):
        self.on = bool(quiere)
        self.modos.append(modo)
        return self.on

    def estado(self, modo=None, reg=None):
        return {"activo": self.on, "registrado": self.on, "aprobado": True, "ruta_ok": True, "modo_ok": True}

    def reparar(self, config=None, modo=None, reg=None):
        self.reparados.append(modo)
        return ""


def _cmd(p, linea):
    antes = len(p.out.getvalue())
    p.comando(linea)
    return p.out.getvalue()[antes:]


def _con_comida_y_sistema(p, mez=None, presencia=None):
    from servicios.comida_terminal import ComidaTerminal
    from servicios.sistema_terminal import SistemaTerminal
    import random
    p.comida = ComidaTerminal(p.consola, p.cfg, colores=p.c, mezclador=mez or vf.MezFalso(), en_juego=p._en_juego,
                              azar=random.Random(5), lanzar_sonido=lambda f: f())
    if p.tools is not None:
        p.comida.registrar_herramientas(p.tools)
    p.sistema = SistemaTerminal(p.consola, p.cfg, en_juego=p._en_juego, pensando=lambda: bool(p._pensando),
                                presencia=presencia or vf.PresenciaFalsa(), autoinicio=p._autoinicio)
    p._desp = None
    return p


def test_patata_por_defecto_trae_comida_y_sistema_y_registra_dar_de_comer(patata_c78):
    from servicios.comida_terminal import ComidaTerminal
    from servicios.sistema_terminal import SistemaTerminal
    from servicios.tools import ToolManager
    tm = ToolManager()
    p = patata_c78(tools=tm)
    assert isinstance(p.comida, ComidaTerminal) and isinstance(p.sistema, SistemaTerminal)
    assert tm.tiene_handler("dar_de_comer")
    assert p.sistema._autoinicio is p._autoinicio                     # el mismo (inyectable) que /menu
    q = patata_c78(tools=tm, comida=None, sistema=None)
    assert q.comida is None and q.sistema is None
    assert "Comando desconocido" in _cmd(q, "/comer")


def test_patata_comandos_ayuda_y_menu(patata_c78):
    from servicios.tools import ToolManager
    mez = vf.MezFalso()
    p = _con_comida_y_sistema(patata_c78(tools=ToolManager()), mez=mez)
    r = _cmd(p, "/comer batido de mango")
    assert "glup" in r.lower() and "mango" in r and mez.reproducidos
    assert "Comida apagada" in _cmd(p, "/comer off") and p.cfg.get("comida", "activa") is False
    assert "apagada" in _cmd(p, "/comer pastel")
    _cmd(p, "/comer on")
    assert "Discord: apagado" in _cmd(p, "/discord")
    assert "Application ID guardado" in _cmd(p, f"/discord id {ID_DISCORD}")
    assert p.cfg.get("discord", "client_id") == ID_DISCORD
    assert "Lune arrancará con Windows" in _cmd(p, "/autoinicio on") and p._autoinicio.modos[-1] == "patata"
    assert "Sentarse es cosa de la mascota" in _cmd(p, "/sentarse")
    ayuda = _cmd(p, "/ayuda")
    for c in ("/comer [batido|pastel]", "/discord [on|off|estado]", "/autoinicio [on|off|estado",
              "Sentarse en la barra o en una ventana es cosa de la mascota"):
        assert c in ayuda, c
    # /menu: Discord con su ✓ (y lo alterna la presencia de patata).
    texto = _cmd(p, "/menu")
    lineas = [x.strip() for x in texto.splitlines() if x.strip()[:1].isdigit()]
    n = next(int(x.split(".")[0]) for x in lineas if x.split(". ", 1)[1].startswith("Discord"))
    _cmd(p, f"/menu {n}")
    assert p.cfg.get("discord", "activo") is True and p.sistema.discord_activo
    p.sistema.iniciar()
    assert p.sistema._presencia.habilitada is True


def test_patata_chat_toma_un_batido_sientate_y_la_pregunta(patata_c78):
    import test_patata as tp
    from servicios.tools import ToolManager
    ai = tp.AIFalsa("Claro :D")
    memoria = _Memoria()
    mez = vf.MezFalso()
    p = _con_comida_y_sistema(patata_c78(tools=ToolManager(), ai=ai, memoria=memoria), mez=mez)
    p.responder("toma un batido")                                      # Llamada → Ejecutor → dar_de_comer
    assert tp.esperar(lambda: "glup" in p.out.getvalue().lower())
    assert ai.system == "" and memoria.vistos == [] and mez.reproducidos
    antes = len(p.out.getvalue())
    p.responder("siéntate")                                            # eso es de la mascota
    assert "Sentarse es cosa de la mascota" in p.out.getvalue()[antes:] and ai.system == ""
    p.responder("¿te puedes sentar?")                                  # no es una orden: el modelo
    assert ai.system != "" and memoria.vistos == ["¿te puedes sentar?"]


def test_patata_pensando_para_discord(patata_c78):
    import test_patata as tp
    from servicios.tools import ToolManager
    vistos = []

    class AI(tp.AIFalsa):
        async def chat(self, *a, **k):
            vistos.append(("chat", p._pensando))
            return await super().chat(*a, **k)
    p = patata_c78(tools=ToolManager(), ai=AI("Hola"))

    class Sistema:
        def actualizar(self):
            vistos.append(("actualizar", p._pensando))

        def comando(self, linea):
            return None
    p.sistema = Sistema()
    p.responder("hola")
    assert vistos == [("actualizar", True), ("chat", True), ("actualizar", False)]
    assert p._pensando is False


def test_patata_arranca_y_para_comida_y_sistema(patata_c78):
    diario = []

    class Pieza:
        def __init__(self, n):
            self.n = n

        def iniciar(self):
            diario.append((self.n, "iniciar"))

        def detener(self):
            diario.append((self.n, "detener"))

        def comando(self, linea):
            return None

        def registrar_herramientas(self, tools):
            pass
    p = patata_c78(comida=Pieza("comida"), sistema=Pieza("sistema"))
    p.iniciar_ocio()
    assert ("comida", "iniciar") in diario and ("sistema", "iniciar") in diario
    p.detener_ocio()
    assert ("comida", "detener") in diario and ("sistema", "detener") in diario


def test_patata_autoinicio_repara_y_si_ya_no_es_patata_abre_la_app(tmp_path, monkeypatch):
    import patata
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("interfaz", "modo", "patata")
    auto = AutoPatata()
    lanzadas = []
    assert patata.arranque_con_windows(config=cfg, autoinicio=auto, lanzar=lambda: lanzadas.append(1)) is None
    assert auto.reparados == ["patata"] and lanzadas == []            # sigue en la terminal
    cfg.set("interfaz", "modo", "web")
    assert patata.arranque_con_windows(config=cfg, autoinicio=auto, lanzar=lambda: lanzadas.append(1) or True) == 0
    assert auto.reparados == ["patata", "web"] and lanzadas == [1]

    def falla():
        raise RuntimeError("sin PyQt6")
    assert patata.arranque_con_windows(config=cfg, autoinicio=auto, lanzar=falla) is None   # se queda aquí
    # lanzar_app_qt lleva --autoinicio a main.py.
    popen = []

    class Proc:
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("x", timeout)
    monkeypatch.setattr("importlib.util.find_spec", lambda n: object())
    patata.lanzar_app_qt("web", popen=lambda args, **kw: popen.append(args) or Proc(), extra=("--autoinicio",))
    assert popen[-1][-1] == "--autoinicio" and popen[-1][-2].endswith("main.py")


def test_patata_main_con_autoinicio(monkeypatch):
    import patata
    creadas = []

    class P:
        def __init__(self, color=True, con_windows=False):
            creadas.append(con_windows)

        def correr(self):
            return 0
    monkeypatch.setattr(patata, "Patata", P)
    # Nada de mutex de verdad (una patata real abierta cambiaría el test).
    monkeypatch.setattr(patata, "_nueva_instancia", lambda: type("Inst", (), {
        "adquirir": lambda self: True, "escuchar": lambda self, fn: True, "liberar": lambda self: None})())
    monkeypatch.setattr(patata, "arranque_con_windows", lambda **k: 0)
    assert patata.main(["--autoinicio"]) == 0 and creadas == []       # abrió la app de ventanas y se va
    monkeypatch.setattr(patata, "arranque_con_windows", lambda **k: None)
    assert patata.main(["--autoinicio"]) == 0 and creadas == [True]   # sigue aquí, con el banner corto
    assert patata.main([]) == 0 and creadas == [True, False]


GUION_SIN_QT = r'''
import io, random, shutil, sys, types
from pathlib import Path
RAIZ = Path({raiz!r}); TMP = Path({tmp!r})
sys.path.insert(0, str(RAIZ))
from nucleo import datos
shutil.copyfile(RAIZ / "datos.example.json", TMP / "datos.json")
datos._PATH = TMP / "datos.json"; datos.invalidar()
import patata
from nucleo.config import Config
from nucleo.consola import ConsolaAsincrona
from servicios.comida_terminal import ComidaTerminal
from servicios.sistema_terminal import SistemaTerminal
from servicios.tools import ToolManager

class Api:
    def habilitar_vt(self): return True
    def es_consola_entrada(self): return False
    def titulo(self, t): return True
    def parpadear(self, *a, **k): return True
    def leer_tecla(self): return ""
class Mez:
    n = 0
    def cargar_wav(self, r): return b""
    def reproducir(self, *a, **k):
        Mez.n += 1
        return 1
class Presencia:
    habilitada = False
    def habilitar(self, on): self.habilitada = on
    def actualizar(self): pass
    def estado(self): return {{}}
    def cerrar(self, timeout=1.0): self.habilitada = False
class Auto:
    def activo(self, reg=None): return False
    def establecer(self, q, modo=None, reg=None): return bool(q)
    def estado(self, modo=None, reg=None): return {{}}
    def reparar(self, *a, **k): return ""

out = io.StringIO()
consola = ConsolaAsincrona("> ", stdout=out, stdin=io.StringIO(""), api=Api(), ansi=False)
cfg = Config(str(TMP / "config.json"))
tm = ToolManager()
comida = ComidaTerminal(consola, cfg, mezclador=Mez(), azar=random.Random(1), lanzar_sonido=lambda f: f())
sistema = SistemaTerminal(consola, cfg, presencia=Presencia(), autoinicio=Auto())
p = patata.Patata(color=False, consola=consola, config=cfg, ai=types.SimpleNamespace(providers={{}}),
                  memoria=types.SimpleNamespace(procesar_mensaje_usuario=lambda t: None), voice=None,
                  tools=tm, audit_path=None, juego=None, alarmas=None, baile=None, salvapantallas=None,
                  comida=comida, sistema=sistema, autoinicio=Auto())
for linea in ("/comer batido", "/comer pastel fresa", "/discord on", "/discord estado", "/autoinicio",
              "/sentarse", "/ayuda"):
    p.comando(linea)
p.iniciar_ocio()
p.responder("toma un pastel")
import time
fin = time.monotonic() + 5
while time.monotonic() < fin and Mez.n < 3:
    time.sleep(0.02)
p.cerrar()
print("SONIDOS", Mez.n, "DAR_DE_COMER", tm.tiene_handler("dar_de_comer"))
print("QT" if any(m.startswith("PyQt") for m in sys.modules) else "SIN_QT")
'''


def test_patata_con_comida_y_sistema_sin_qt(tmp_path):
    guion = tmp_path / "guion_c78.py"
    guion.write_text(textwrap.dedent(GUION_SIN_QT.format(raiz=str(RAIZ), tmp=str(tmp_path))), encoding="utf-8")
    r = subprocess.run([sys.executable, str(guion)], cwd=str(RAIZ), capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr[-2000:]
    lineas = r.stdout.strip().splitlines()
    assert lineas[-1] == "SIN_QT", r.stdout[-800:]
    assert lineas[-2] == "SONIDOS 3 DAR_DE_COMER True", r.stdout[-800:]
