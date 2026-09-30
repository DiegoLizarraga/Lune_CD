"""
Integración final de los cortes 9 y 10 (reproductor de bailes MMD/VRMA y Minecraft) en las
ventanas, en main.py y en patata.

Web: `VentanaWeb.__init__` de verdad con Chromium sustituido (el arnés de
tests/test_anfitriones_corte4.py) → el objeto `escenario` del canal está antes de setUrl, se
enlaza con los controladores de verdad (tests/escenario_falso_c910.py: ControlMMD con la
Biblioteca de verdad en tmp, ControlMinecraft con un ProcesoBot falso) al montar y salir
desmonta una vez sin dejar «node» vivo. Cambio de interfaz en caliente (web → nativa → web):
nunca dos ControlMMD ni dos ControlMinecraft a la vez y el bot conectado se vuelve a conectar
en la nueva (sin instalar nada). Nativa: el escenario va con el corte 4; Ajustes nativos: el
panel de bailes y Minecraft recibe los servicios y «Guardar» escribe lo pendiente.
Chat (web y nativa): «conecta el bot de minecraft» sale como Llamada por el Ejecutor sin pasar
por la memoria; «¿cómo conecto el bot?» NO. Mientras la IA responde, el bus dice `pensando`
(el bot pausa su modelo). Patata: bailes y Minecraft sin Qt, /ayuda, /menu, el chat.
Nada de node, red, registro de Windows, config.json de verdad ni audio.
"""
import io
import json
import os
import subprocess
import sys
import textwrap
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

import escenario_falso_c910 as ef  # noqa: E402
import test_anfitriones_corte4 as c4  # noqa: E402
from test_anfitriones_corte4 import ajustes, entorno, sistema  # noqa: E402,F401  (fixtures)
from test_anfitriones_c78_int import patata_c78  # noqa: E402,F401  (fixture)
from nucleo.config import Config  # noqa: E402

CANAL_C910 = ["alarmas", "escenario", "escritorio", "lune", "musica", "tareas", "vida"]
ACCIONES = ("bailes", "minecraft", "minecraft_bot")
HERRAMIENTAS = ("listar_bailes", "minecraft_estado", "minecraft_orden", "minecraft_bot")


@pytest.fixture
def escenario(entorno, monkeypatch, tmp_path):
    """El arnés del corte 4 con el reproductor de bailes y Minecraft de verdad (dobles del sistema)."""
    reg = ef.Registro()
    fab = dict(c4.fabricas(), escenario=ef.fabricas_escenario(reg, tmp_path / "esc"))
    monkeypatch.setattr(entorno.ws.VentanaWeb, "FABRICAS_C4", fab)
    monkeypatch.setattr(entorno.main.LuneCDWindow, "FABRICAS_C4", fab)
    contador = {"desmontar": 0}
    from ui.montaje_escenario import ServiciosEscenario
    real = ServiciosEscenario.desmontar

    def desmontar(self):
        if not self.desmontado:
            contador["desmontar"] += 1
        return real(self)
    monkeypatch.setattr(ServiciosEscenario, "desmontar", desmontar)
    entorno.reg, entorno.cuenta, entorno.dir = reg, contador, tmp_path / "esc"
    return entorno


def _vivos(reg):
    return len(reg.mmds_vivos()), len(reg.mcs_vivos()), len(reg.nodes_vivos())


def _mc_de(ventana):
    return ventana._servicios_c4.escenario.minecraft


# ═══ Web ══════════════════════════════════════════════════════════════════════

def test_web_registra_el_puente_escenario_antes_de_cargar_y_lo_enlaza(escenario, sistema):
    v = escenario.web()
    assert v.web.objetos_al_cargar == CANAL_C910                        # window.luneEscenario
    s = v._servicios_c4
    e = s.escenario
    assert e is not None and e.mmd is escenario.reg.mmds[-1] and e.minecraft is escenario.reg.mcs[-1]
    pe = v._puente_escenario
    assert pe.mmd is e.mmd and pe.minecraft is e.minecraft
    for h in HERRAMIENTAS:
        assert v.bridge.tools.tiene_handler(h), h                      # el ToolManager del puente
    for a in ACCIONES:
        assert s.despachador.tiene(a), a
    assert _vivos(escenario.reg) == (1, 1, 0)
    # Lo que pide la página llega a los controladores de verdad.
    lista = json.loads(pe.bailes_lista(""))
    assert lista["servicio"] is True and sorted(b["titulo"] for b in lista["bailes"]) == ["Alfa", "Beta"]
    assert json.loads(pe.mc_estado_json())["servicio"] is True
    r = json.loads(pe.mc_bot_conectar())
    assert r["ok"] and escenario.reg.nodes_vivos() == [escenario.reg.procesos[-1]]
    assert escenario.reg.procesos[-1].instalaciones == 0
    # La vista «Mis bailes» (bandeja/radial) → la ventana y lune-vista «bailes».
    vistas = []
    pe.vista_pedida.connect(vistas.append)
    assert s.despachador.ejecutar("bailes") and vistas == ["bailes"]


def test_web_salir_desmonta_el_escenario_una_sola_vez_y_no_deja_node(escenario, sistema):
    v = escenario.web()
    canal, e, pe = v._canal, v._servicios_c4.escenario, v._puente_escenario
    assert json.loads(pe.mc_bot_conectar())["ok"] and len(escenario.reg.nodes_vivos()) == 1
    v.salir_de_verdad()
    v.bridge.cerrar_escritorio()
    assert escenario.cuenta["desmontar"] == 1 and e.desmontado
    assert _vivos(escenario.reg) == (0, 0, 0)                          # ni reproductor ni node
    assert escenario.reg.procesos[-1].paradas                          # el bot se paró (esperando)
    assert "escenario" not in canal.registrados and v._puente_escenario is None
    v._liberar_todo()
    assert escenario.cuenta["desmontar"] == 1


def test_web_diferida_registra_el_puente_pero_monta_al_final(escenario, sistema):
    vieja = escenario.web()
    nueva = escenario.web(diferir=True)
    assert nueva.web.objetos_al_cargar == CANAL_C910
    assert nueva._servicios_c4 is None and nueva._puente_escenario.mmd is None
    assert _vivos(escenario.reg)[:2] == (1, 1)                          # solo los de la vieja
    vieja.cerrar_para_cambio()
    assert _vivos(escenario.reg) == (0, 0, 0)
    nueva.iniciar_servicios({})
    assert nueva._puente_escenario.mmd is nueva._servicios_c4.escenario.mmd
    assert _vivos(escenario.reg) == (1, 1, 0)                          # sin bot: no lo conecta


def test_relevo_en_caliente_un_solo_reproductor_y_un_solo_bot_que_se_reconecta(escenario, sistema, qapp):
    from ui.cambio_interfaz import GestorInterfaz
    reg = escenario.reg
    reg.conectar = True                                                # el bot avisa «conectado» al entrar

    def fabrica(modo):
        return escenario.web(diferir=True) if modo == "web" else escenario.nativa()
    g = GestorInterfaz(fabrica, guardar_modo=lambda m: None, animar=lambda v, ms, fin: fin(),
                       fundido_ms=0, tope_carga_ms=10)
    web = escenario.web()
    g.adoptar(web)
    ok, _ = _mc_de(web).conectar_bot()
    assert ok and c4._esperar(qapp, lambda: _mc_de(web).bot_conectado)
    assert web.estado_para_cambio()["minecraft_bot"] is True

    def comprobar(ventana):
        e = ventana._servicios_c4.escenario
        assert e is not None and not e.desmontado
        assert reg.mmds_vivos() == [e.mmd] and reg.mcs_vivos() == [e.minecraft]
        assert reg.nodes_vivos() == [e.minecraft.proceso]              # un solo node: el de la nueva
        assert len(e.minecraft.proceso.arranques) == 1
        assert c4._esperar(qapp, lambda: e.minecraft.bot_conectado)
    assert g.cambiar("nativo") is True
    nat = g.ventana
    comprobar(nat)
    assert nat.estado_para_cambio()["minecraft_bot"] is True
    assert g.cambiar("web") is True
    assert c4._esperar(qapp, lambda: g.ventana is not nat and not g.cambiando)
    comprobar(g.ventana)
    assert len(reg.mmds) == 3 and len(reg.mcs) == 3 and len(reg.procesos) == 3   # una por ventana
    assert all(p.paradas for p in reg.procesos[:2]) and sum(p.instalaciones for p in reg.procesos) == 0


def test_relevo_sin_el_bot_conectado_no_lo_conecta(escenario, sistema, qapp):
    from ui.cambio_interfaz import GestorInterfaz
    g = GestorInterfaz(lambda modo: escenario.nativa(), guardar_modo=lambda m: None,
                       animar=lambda v, ms, fin: fin(), fundido_ms=0, tope_carga_ms=10)
    web = escenario.web()
    g.adoptar(web)
    assert web.estado_para_cambio()["minecraft_bot"] is False
    assert g.cambiar("nativo") is True
    assert all(p.arranques == [] for p in escenario.reg.procesos) and escenario.reg.nodes_vivos() == []


def test_la_cara_de_la_barra_no_sobrevive_al_puente(qapp):
    """La reacción de Minecraft (o de la comida) sin asistente pone la cara de la barra un rato;
    si en ese rato el puente se va (cambio de interfaz en caliente), su vuelta a «normal» se va
    con él: antes era un singleShot suelto que emitía en un objeto borrado (access violation)."""
    from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
    from ui.anfitrion_web import AnfitrionWeb

    class Puente(QObject):
        acto = pyqtSignal(str)
    b = Puente()
    vistos = []
    b.acto.connect(vistos.append)
    a = AnfitrionWeb(b, None)
    assert a.reaccion("happy", 200) is True and vistos == ["happy"]
    assert len(b.findChildren(QTimer)) == 1                            # el temporizador es del puente
    b.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    import time
    fin = time.monotonic() + 0.5
    while time.monotonic() < fin:
        qapp.processEvents()
        time.sleep(0.01)
    assert vistos == ["happy"]
    # Con el puente vivo, vuelve a «normal».
    b2 = Puente()
    b2.acto.connect(vistos.append)
    assert AnfitrionWeb(b2, None).expresion_barra("sad", 10)
    assert c4._esperar(qapp, lambda: vistos[-1] == "normal")
    b2.deleteLater()


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


def test_web_chat_conecta_el_bot_sale_como_llamada_y_la_pregunta_no(escenario, sistema):
    from lune_core.acciones import USUARIO
    v = escenario.web()
    b = v.bridge
    b.memoria, b.acciones = _Memoria(), _Acciones()
    ia = []
    b._arrancar_ia = lambda mensaje, *a, **k: ia.append(mensaje)
    assert b._enviar("conecta el bot de minecraft", b._provider_web) is True
    llamadas, origen, _ctx = b.acciones.ejecutadas[-1]
    assert origen == USUARIO and [(x.herramienta, x.args, x.directa) for x in llamadas] == [
        ("minecraft_bot", {"accion": "conectar"}, True)]
    assert b.memoria.vistos == [] and ia == []                         # antes que la memoria y sin IA
    b._enviar("ponme el baile de Alfa", b._provider_web)
    assert [(x.herramienta, x.args) for x in b.acciones.ejecutadas[-1][0]] == [
        ("asistente_bailar", {"segundos": 30, "cancion": "Alfa"})]
    # Una pregunta no es una orden: memoria y modelo, como siempre.
    b._enviar("¿cómo conecto el bot?", b._provider_web)
    assert len(b.acciones.ejecutadas) == 2
    assert b.memoria.vistos == ["¿cómo conecto el bot?"] and ia == ["¿cómo conecto el bot?"]


class WorkerFalso(QObject):
    """AIWorker de mentira: las señales de verdad, sin hilo."""
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    creados: list = []

    def __init__(self, *a, **k):
        super().__init__()
        self.arrancado = False
        WorkerFalso.creados.append(self)

    def start(self):
        self.arrancado = True

    def isRunning(self):
        return self.arrancado


def test_web_pensando_mientras_responde_pausa_el_modelo_del_bot(escenario, sistema, qapp, monkeypatch):
    import ui.web_bridge as wb
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    v = escenario.web()
    b = v.bridge
    bus = b.escritorio.estado
    assert json.loads(v._puente_escenario.mc_bot_conectar())["ok"]
    p = escenario.reg.procesos[-1]
    b._arrancar_ia("hola", "ollama", origen="usuario", modo="normal", ctx={})
    w1 = WorkerFalso.creados[-1]
    assert w1.arrancado and bus.actual().pensando is True
    assert c4._esperar(qapp, lambda: ("llm", True) in p.pausas)       # el bot no compite por Ollama
    # Un hilo viejo que acaba tarde no apaga el del envío nuevo.
    b._arrancar_ia("otra", "ollama", origen="usuario", modo="normal", ctx={})
    w2 = WorkerFalso.creados[-1]
    w1.finished.emit()
    assert bus.actual().pensando is True
    # La asistente que comenta la pantalla y acaba no apaga el del chat.
    bus.actualizar(pensando=True)
    bus.actualizar(pensando=False)
    assert bus.actual().pensando is True
    w2.finished.emit()
    assert bus.actual().pensando is False
    assert c4._esperar(qapp, lambda: p.pausas[-1] == ("llm", False))


# ═══ Nativa ═══════════════════════════════════════════════════════════════════

def test_nativa_monta_el_escenario_y_salir_lo_desmonta_una_vez_sin_node(escenario, sistema):
    panel = c4.PanelFalso()
    yo = escenario.nativa(panel=panel)
    yo.iniciar_servicios({})
    s = yo._servicios_c4
    assert panel.recibidos == [s] and s.escenario is not None
    assert {"mmd", "minecraft"} <= set(yo.escritorio.controladores())
    for a in ACCIONES:
        assert s.despachador.tiene(a), a
    assert s.despachador.ejecutar("minecraft_bot")                     # conectar desde la bandeja
    assert _vivos(escenario.reg) == (1, 1, 1)
    assert yo.estado_para_cambio()["minecraft_bot"] is True
    yo._quit_real = True
    yo.closeEvent(c4.Evento())
    assert escenario.cuenta["desmontar"] == 1 and _vivos(escenario.reg) == (0, 0, 0)


def test_nativa_iniciar_servicios_reconecta_el_bot_del_estado(escenario, sistema):
    yo = escenario.nativa(panel=c4.PanelFalso())
    yo.iniciar_servicios({"minecraft_bot": True})
    mc = _mc_de(yo)
    assert mc.proceso.vivo and len(mc.proceso.arranques) == 1 and mc.proceso.instalaciones == 0


def _nativa_chat(main, texto, memoria, ejecutadas):
    from servicios.tools import ToolManager
    return types.SimpleNamespace(
        _worker_vivo=lambda: False, _set_status=lambda *a: None, current_provider="ollama", _turno={},
        stack=types.SimpleNamespace(setCurrentIndex=lambda i: None), _cancelar_plan=lambda: None,
        voice=types.SimpleNamespace(cancelar=lambda: None, available=False, _enabled=False),
        messages_layout=types.SimpleNamespace(insertWidget=lambda *a: None, count=lambda: 1),
        input_field=types.SimpleNamespace(text=lambda: texto["t"], clear=lambda: None, setEnabled=lambda v: None),
        _adjuntos=[], _refrescar_adjuntos=lambda: None, _guardar_turno=lambda *a, **k: None,
        memoria=memoria, tools=ToolManager(), ai_manager=types.SimpleNamespace(providers={}),
        _modo_acciones=lambda: "normal", _scroll_bottom=lambda: None, _burbuja_bot=lambda t: None,
        _eco_asistente=lambda *a, **k: None,
        lune_face=types.SimpleNamespace(set_state=lambda *a, **k: None),
        _ejecutar_acciones=lambda ll, origen, ctx, **kw: ejecutadas.append((ll, origen, dict(ctx), kw)))


def test_nativa_chat_conecta_el_bot_va_al_ejecutor_y_la_pregunta_no(qapp, monkeypatch):
    import main
    from lune_core.acciones import USUARIO
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: object())
    ejecutadas = []
    memoria = _Memoria(respuesta="(la memoria contesta)")          # así la pregunta no llega al modelo
    texto = {"t": "Lune, conecta el bot de Minecraft"}
    yo = _nativa_chat(main, texto, memoria, ejecutadas)
    main.LuneCDWindow._send_message(yo)
    ll, origen, ctx, kw = ejecutadas[-1]
    assert origen == USUARIO and kw["directo"] is True and memoria.vistos == []
    assert [(x.herramienta, x.args) for x in ll] == [("minecraft_bot", {"accion": "conectar"})]
    texto["t"] = "¿cómo conecto el bot?"
    main.LuneCDWindow._send_message(yo)
    assert len(ejecutadas) == 1 and memoria.vistos == ["¿cómo conecto el bot?"]


def test_nativa_pensando_mientras_el_hilo_de_la_ia_vive(qapp, monkeypatch, tmp_path):
    import main
    from ui.escritorio import ServiciosEscritorio
    WorkerFalso.creados = []
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: object())
    monkeypatch.setattr(main, "TypingIndicator", lambda *a, **k: types.SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(main, "AIWorker", WorkerFalso)
    texto = {"t": "cuéntame algo"}
    yo = _nativa_chat(main, texto, _Memoria(), [])
    cfg = Config(str(tmp_path / "config.json"))
    yo.config = types.SimpleNamespace(feature=lambda n, d=True: False if n in (
        "respuestas_predeterminadas", "voz_streaming") else d)
    yo.escritorio = ServiciosEscritorio(cfg)
    yo.send_btn = yo.stop_btn = types.SimpleNamespace(hide=lambda: None, show=lambda: None)
    yo._overlay = None
    yo.notas = types.SimpleNamespace(activo=False)
    yo._modo_red, yo._chat_remoto = "local", None
    yo.acciones = types.SimpleNamespace(ejecutor=None)
    yo._gen, yo.ai_worker = 0, None
    for n in ("_on_token", "_on_response", "_on_error", "_al_terminar_worker"):
        setattr(yo, n, lambda *a, **k: None)
    for n in ("_pensando_chat", "_fin_pensando_chat"):
        setattr(yo, n, types.MethodType(getattr(main.LuneCDWindow, n), yo))
    bus = yo.escritorio.estado
    main.LuneCDWindow._send_message(yo)
    w1 = WorkerFalso.creados[-1]
    assert w1.arrancado and yo.ai_worker is w1 and bus.actual().pensando is True
    yo.ai_worker = w2 = WorkerFalso()                                  # un envío nuevo (el viejo acaba tarde)
    yo._pensando_chat(True)
    w1.finished.emit()
    assert bus.actual().pensando is True
    w2.finished.connect(lambda w=w2: yo._fin_pensando_chat(w))
    w2.finished.emit()
    assert bus.actual().pensando is False
    yo.escritorio.cerrar()


# ═══ Ajustes nativos ══════════════════════════════════════════════════════════

class _Ctl:
    def __init__(self, estado=None):
        self.llamadas, self._estado = [], estado or {}

    def recargar_config(self):
        self.llamadas.append("recargar_config")

    def refrescar(self):
        self.llamadas.append("refrescar")

    def estado(self):
        return dict(self._estado)

    def lista(self, texto=""):
        return []


def test_ajustes_nativos_enlazan_y_guardan_el_panel_de_escenario(ajustes):
    from ui.panel_escenario_nativo import PanelEscenarioNativo
    caja = {"s": None}
    p = ajustes.crear(lambda: caja["s"])
    panel = p.escenario_panel
    try:
        assert isinstance(panel, PanelEscenarioNativo) and panel.mmd is None and panel.minecraft is None
        mmd, mc = _Ctl({"fase": "parado"}), _Ctl({"reaccionar": False})
        s = types.SimpleNamespace(escenario=types.SimpleNamespace(mmd=mmd, minecraft=mc), vida=None, ocio=None,
                                  atajos=None, escritorio=None, _deshacer=[], desmontar=lambda: None)
        caja["s"] = s
        p.usar_servicios(s)
        assert panel.mmd is mmd and panel.minecraft is mc and "refrescar" in mmd.llamadas
        # «Guardar configuración» escribe lo pendiente del panel y lo aplica en caliente.
        panel._poner("bailes", "baile", "al_terminar", "siguiente")
        panel._poner("minecraft", "minecraft", "decir_en_juego", False)
        p._save()
        assert mmd.llamadas.count("recargar_config") == 1 and mc.llamadas.count("recargar_config") == 1
        guardada = Config(str(ajustes.cfg.config_path))
        assert guardada.get("baile", "al_terminar") == "siguiente"
        assert guardada.get("minecraft", "decir_en_juego") is False
        # Al desmontar los servicios, el panel los suelta.
        for f in list(s._deshacer):
            f()
        assert panel.mmd is None and panel.minecraft is None
    finally:
        panel._timer.stop()


# ═══ Patata ═══════════════════════════════════════════════════════════════════

def _cmd(p, linea):
    antes = len(p.out.getvalue())
    p.comando(linea)
    return p.out.getvalue()[antes:]


def _con_bailes_y_minecraft(p, tmp_path, proceso=None):
    from servicios.bailes_terminal import BailesTerminal
    from servicios.minecraft_terminal import MinecraftTerminal
    p.bailes = BailesTerminal(p.consola, p.cfg, biblioteca=ef.biblioteca(tmp_path / "pat", p.cfg),
                              cancion=lambda: ef.CancionFalsa(), colores=p.c, en_juego=p._en_juego, baile=p.baile, hilo=False)
    p.minecraft = MinecraftTerminal(p.consola, p.cfg, proceso=proceso or ef.ProcesoFalso(), colores=p.c,
                                    en_juego=p._en_juego, pensando=lambda: bool(p._pensando), rutas=lambda: [],
                                    datos_mc=lambda: {"host": "localhost", "port": 25565, "dueno": ef.DUENO},
                                    guardar_mc=lambda cambios: cambios, personaje=lambda: {"nombre": "Lune"},
                                    llm=lambda: None, hilo=False)
    if p.tools is not None:
        p.bailes.registrar_herramientas(p.tools)
        p.minecraft.registrar_herramientas(p.tools)
    p._desp = None
    return p


def test_patata_por_defecto_trae_bailes_y_minecraft_y_sus_herramientas(patata_c78):
    from servicios.bailes_terminal import BailesTerminal
    from servicios.minecraft_terminal import MinecraftTerminal
    from servicios.tools import ToolManager
    tm = ToolManager()
    p = patata_c78(tools=tm)
    assert isinstance(p.bailes, BailesTerminal) and isinstance(p.minecraft, MinecraftTerminal)
    assert p.bailes.baile is p.baile                                  # la MISMA capa del título
    for h in ("listar_bailes", "asistente_bailar", "parar_baile") + HERRAMIENTAS[1:]:
        assert tm.tiene_handler(h), h
    assert "asistente_bailar" in tm.disponibles("patata") and "listar_bailes" in tm.disponibles("patata")
    q = patata_c78(tools=tm, bailes=None, minecraft=None)
    assert q.bailes is None and q.minecraft is None
    assert "Comando desconocido" in _cmd(q, "/bailes") and "Comando desconocido" in _cmd(q, "/mc")


def test_patata_bailes_mc_ayuda_menu_y_parar(patata_c78, tmp_path):
    from servicios import bailes_terminal, minecraft_terminal
    from servicios.tools import ToolManager
    proceso = ef.ProcesoFalso()
    p = _con_bailes_y_minecraft(patata_c78(tools=ToolManager()), tmp_path, proceso)
    ayuda = _cmd(p, "/ayuda")
    assert bailes_terminal.AYUDA in ayuda and minecraft_terminal.AYUDA in ayuda
    lista = _cmd(p, "/bailes")
    assert "Alfa" in lista
    r = _cmd(p, "/bailes 1")
    assert "Pongo" in r and p.bailes.activo
    # /parar con una canción puesta: la para (bailes va antes que el baile del título).
    assert "paro la canción" in _cmd(p, "/parar") and not p.bailes.activo
    assert "Comando desconocido" not in _cmd(p, "/mc")
    assert "Conectando el bot" in _cmd(p, "/mc bot on") and proceso.vivo and proceso.instalaciones == 0
    proceso.on_evento({"tipo": "conectado", "nick": "Lune"})          # el bot entra (su hilo lector)
    assert p.minecraft.bot_conectado
    # /menu: «Mis bailes», las reacciones y el bot (con su ✓).
    texto = _cmd(p, "/menu")
    etiquetas = {x.split(". ", 1)[1].split("  ")[0]: x for x in (l.strip() for l in texto.splitlines())
                 if x[:1].isdigit()}
    assert {"Mis bailes", "Reacciones a Minecraft", "Bot de Minecraft"} <= set(etiquetas)
    assert etiquetas["Bot de Minecraft"].endswith("✓")
    n = int(etiquetas["Bot de Minecraft"].split(".")[0])
    assert "Desconecto el bot" in _cmd(p, f"/menu {n}") and not proceso.vivo
    n = int(etiquetas["Reacciones a Minecraft"].split(".")[0])
    _cmd(p, f"/menu {n}")
    assert p.cfg.get("minecraft", "reaccionar") is True
    p.minecraft.set_reacciones(False)


def test_patata_chat_ponme_el_baile_y_conecta_el_bot(patata_c78, tmp_path):
    import test_patata as tp
    from servicios.tools import ToolManager
    ai = tp.AIFalsa("Claro :D")
    memoria = _Memoria()
    proceso = ef.ProcesoFalso()
    p = _con_bailes_y_minecraft(patata_c78(tools=ToolManager(), ai=ai, memoria=memoria), tmp_path, proceso)
    p.responder("ponme el baile de Alfa")                              # sin IA ni Ejecutor: la biblioteca
    assert "Alfa" in p.out.getvalue() and p.bailes.activo and ai.system == "" and memoria.vistos == []
    antes = len(p.out.getvalue())
    p.responder("para el baile")
    assert not p.bailes.activo and "dejo de bailar" in p.out.getvalue()[antes:].lower()
    p.responder("conecta el bot de minecraft")                         # Llamada → Ejecutor → pide permiso
    assert tp.esperar(lambda: "Contesta s o n" in p.out.getvalue())
    assert not proceso.vivo and ai.system == "" and memoria.vistos == []
    p.entrada.put("s\n")
    assert tp.esperar(lambda: proceso.vivo) and proceso.instalaciones == 0
    assert tp.esperar(lambda: "Conectando el bot" in p.out.getvalue())
    p.responder("¿cómo conecto el bot?")                               # no es una orden: el modelo
    assert ai.system != "" and memoria.vistos == ["¿cómo conecto el bot?"]


def test_patata_arranca_y_para_bailes_y_minecraft_en_orden(patata_c78):
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
    p = patata_c78(bailes=Pieza("bailes"), minecraft=Pieza("minecraft"), baile=Pieza("baile"))
    p.iniciar_ocio()
    assert {("bailes", "iniciar"), ("minecraft", "iniciar"), ("baile", "iniciar")} <= set(diario)
    diario.clear()
    p.detener_ocio()
    orden = [n for n, _ in diario]
    assert orden.index("minecraft") < orden.index("baile") and orden.index("bailes") < orden.index("baile")


GUION_SIN_QT = r'''
import io, shutil, sys, types
from pathlib import Path
RAIZ = Path({raiz!r}); TMP = Path({tmp!r})
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "tests"))
from nucleo import datos
shutil.copyfile(RAIZ / "datos.example.json", TMP / "datos.json")
datos._PATH = TMP / "datos.json"; datos.invalidar()
import patata
import escenario_falso_c910 as ef
from nucleo.config import Config
from nucleo.consola import ConsolaAsincrona
from servicios.bailes_terminal import BailesTerminal
from servicios.minecraft_terminal import MinecraftTerminal
from servicios.tools import ToolManager

class Api:
    def habilitar_vt(self): return True
    def es_consola_entrada(self): return False
    def titulo(self, t): return True
    def parpadear(self, *a, **k): return True
    def leer_tecla(self): return ""

out = io.StringIO()
consola = ConsolaAsincrona("> ", stdout=out, stdin=io.StringIO(""), api=Api(), ansi=False)
cfg = Config(str(TMP / "config.json"))
tm = ToolManager()
bailes = BailesTerminal(consola, cfg, biblioteca=ef.biblioteca(TMP / "b", cfg), cancion=lambda: ef.CancionFalsa(), hilo=False)
proceso = ef.ProcesoFalso()
mc = MinecraftTerminal(consola, cfg, proceso=proceso, rutas=lambda: [], hilo=False,
                       datos_mc=lambda: {{"host": "localhost", "port": 25565, "dueno": ef.DUENO}},
                       personaje=lambda: {{"nombre": "Lune"}}, llm=lambda: None)
p = patata.Patata(color=False, consola=consola, config=cfg, ai=types.SimpleNamespace(providers={{}}),
                  memoria=types.SimpleNamespace(procesar_mensaje_usuario=lambda t: None), voice=None,
                  tools=tm, audit_path=None, juego=None, alarmas=None, baile=None, salvapantallas=None,
                  comida=None, sistema=None, bailes=bailes, minecraft=mc, autoinicio=types.SimpleNamespace(
                      activo=lambda reg=None: False))
for linea in ("/bailes", "/bailes 1", "/parar", "/mc", "/mc bot on", "/mc bot off", "/ayuda"):
    p.comando(linea)
p.iniciar_ocio()
p.responder("ponme el baile de Beta")
p.cerrar()
print("BAILES", len(bailes.biblioteca.escanear()), "ARRANQUES", len(proceso.arranques), "NODE", proceso.vivo,
      "LISTAR", tm.tiene_handler("listar_bailes"), "MC", tm.tiene_handler("minecraft_bot"))
print("QT" if any(m.startswith("PyQt") for m in sys.modules) else "SIN_QT")
'''


def test_patata_con_bailes_y_minecraft_sin_qt(tmp_path):
    guion = tmp_path / "guion_c910.py"
    guion.write_text(textwrap.dedent(GUION_SIN_QT.format(raiz=str(RAIZ), tmp=str(tmp_path))), encoding="utf-8")
    r = subprocess.run([sys.executable, str(guion)], cwd=str(RAIZ), capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr[-2000:]
    lineas = r.stdout.strip().splitlines()
    assert lineas[-1] == "SIN_QT", r.stdout[-800:]
    assert lineas[-2] == "BAILES 2 ARRANQUES 1 NODE False LISTAR True MC True", r.stdout[-800:]
