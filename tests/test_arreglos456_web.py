"""
Arreglos de la revisión 4-5-6 — parte web (puente, ventana web, mascota web, Telegram,
cambio de interfaz, Ejecutor).

  · SB4: la vista de la mascota (ui/companion.py) lleva la guarda de navegación de la
    ventana principal (PaginaLune con el origen del servidor local de la mascota,
    NavigateOnDropEnabled apagado): soltar un enlace o file:/data: no navega; un enlace
    pulsado va al navegador del sistema.
  · SB2: lo transcrito en el modo llamada que detecta detectar_llamadas pide permiso
    («Lo oí en la llamada»), salvo la lectura; escrito a mano y el turno de IA, igual.
  · SB3: una orden remota en una conversación contaminada pregunta con los dos motivos.
  · VS3: guardar_config solo toca el autoinicio si cambió y sincroniza sistema.autoinicio
    con el estado real (la parte de la página está en tests/js/ajustes_guardar.test.mjs).
  · VS5/VS7: «Se detuvo…» a Telegram al parar el bot con una orden pendiente, una sola
    vez por orden (Detener + limpiar chat no la repiten).
  · VS6: el modo juego forzado pasa a la ventana nueva (estado_para_cambio → iniciar_servicios).
  · RH3: un cambio de interfaz pedido dentro del bucle anidado de _esperar_en_hilo no borra
    la ventana ni su puente con el slot en la pila: se hace al salir de la espera.
  · RH6: el bot no se lanza si lo paran durante el primer npm ci (y npm muere); responder_orden
    no bloquea aunque el bot no lea su stdin (cola; llena → se descarta con aviso).
  · VS1 (parte web): el puente `escritorio` filtra el radial con el contexto del montaje
    (Lune en la barra lateral cuenta para expresiones y baile).

Sin red, sin Telegram, sin Chromium cargando páginas y con datos.json / config.json en
carpetas temporales.
"""
import json
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (la crea conftest).
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QObject, QTimer, pyqtSignal  # noqa: E402

from lune_core import acciones as A  # noqa: E402
from lune_core import catalogo_herramientas as C  # noqa: E402
from lune_core import herramientas as H  # noqa: E402
from servicios import telegram_worker as tw  # noqa: E402
from servicios import tools as T  # noqa: E402
from servicios.tools import ToolManager, ToolResult  # noqa: E402


def esperar(app, cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    app.processEvents()
    return cond()


# ── Dobles del puente web ──────────────────────────────────────────────────────

class TgFalso:
    """El TelegramBotWorker visto desde la app: lo que se manda al bot y cuándo se para."""
    def __init__(self):
        self.enviados, self.eventos, self.vivo = [], [], True

    def responder_orden(self, oid, texto):
        if not self.vivo:
            return False
        self.enviados.append((oid, texto))
        self.eventos.append(("responder", oid))
        return True

    def isRunning(self):
        return self.vivo

    def stop(self):
        self.eventos.append(("stop",))
        self.vivo = False

    def requestInterruption(self):
        pass

    def wait(self, _ms=0):
        return True


class VozFalsa:
    def __init__(self):
        self._enabled, self.available = False, False
        self.on_error = self.al_hablar = None

    def cancelar(self):
        pass

    def invalidar_params(self):
        pass

    def reiniciar_motor(self):
        pass


class AIFalso:
    def __init__(self):
        self.providers = {}

    def clear_history(self):
        pass

    def reload_provider(self):
        pass


class WorkerFalso(QObject):
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    creados = []

    def __init__(self, motor, message, provider_id, **kw):
        super().__init__()
        self.message, self.kw, self.corriendo = message, kw, False
        WorkerFalso.creados.append(self)

    def start(self):
        self.corriendo = True               # sigue «vivo» hasta que el test diga (como tras Detener)

    def isRunning(self):
        return self.corriendo


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({
        "apis": {"telegram_token": "123:TG-FALSO", "telegram_admin_id": "777"},
        "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": "m"},
        "bot": {"personaje_default": "Lune"},
        "personajes": [{"nombre": "Lune", "systemPrompt": "Eres Lune."}],
    }), "utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


@pytest.fixture
def puente(qapp, tmp_path, monkeypatch, datos_tmp):
    import ui.web_bridge as wb
    from nucleo.config import Config
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    urls, temporizadores, info = [], [], []
    monkeypatch.setattr(T.webbrowser, "open", lambda u, *a, **k: urls.append(u) or True)
    tm = ToolManager()
    monkeypatch.setattr(tm, "_cmd_sistema_info", lambda *a: info.append(1) or ToolResult(True, "CPU 5% | RAM 40%"))
    tm.registrar_handler("temporizador", lambda args, ctx=None: temporizadores.append(dict(args)) or "Listo")
    memoria = MagicMock()
    memoria.procesar_mensaje_usuario.return_value = None
    memoria.obtener_contexto_para_prompt.return_value = ""
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("telegram", "ordenes_pc", True)
    b = wb.LuneBridge(config=cfg, ai_manager=AIFalso(), memoria=memoria, tools=tm, voice=VozFalsa(),
                      opciones_acciones={"audit_path": None,
                                         "programar": lambda s, fn: MagicMock()})
    senales = {n: [] for n in ("done", "herramienta", "aprobacion_pedida", "usuario_dijo", "aviso")}
    for n, lista in senales.items():
        getattr(b, n).connect(lambda *a, l=lista: l.append(a if len(a) != 1 else a[0]))
    b._ventana_a_la_vista = lambda: True                        # la página está delante
    b._tg_worker = TgFalso()
    b.urls, b.temporizadores, b.info, b.senales = urls, temporizadores, info, senales
    yield b
    b.cerrar_escritorio()
    b.deleteLater()


def _pedidas(b):
    return [json.loads(x) for x in b.senales["aprobacion_pedida"]]


# ── SB2: modo llamada ───────────────────────────────────────────────────────────

def test_sb2_lo_oido_en_la_llamada_pide_permiso_y_lo_escrito_no(puente):
    b = puente
    b._llamada_transcrito("abre youtube")
    assert b.senales["usuario_dijo"] == ["abre youtube"]           # la página lo pinta y lo envía
    b.enviar("abre youtube", "local")
    assert b.urls == [] and WorkerFalso.creados == []               # sin IA y sin abrir nada aún
    p = _pedidas(b)[-1]
    assert p["herramienta"] == "abrir_url" and p["llamada"] is True
    assert A.AVISO_LLAMADA in p["motivo"] and p.get("remoto") is None
    assert b.resolver_aprobacion(p["id"], True) is True
    assert len(b.urls) == 1                                         # aprobada: ahora sí
    # Lo mismo escrito a mano (sin transcripción): como siempre, sin preguntar.
    n = len(b.senales["aprobacion_pedida"])
    b.enviar("abre youtube", "local")
    assert len(b.urls) == 2 and len(b.senales["aprobacion_pedida"]) == n


def test_sb2_temporizador_oido_no_se_pone_sin_permiso(puente):
    b = puente
    b._llamada_transcrito("  pon un temporizador de 5 minutos ")
    b.enviar("pon un temporizador de 5 minutos", "local")        # la página lo manda recortado
    assert b.temporizadores == []
    p = _pedidas(b)[-1]
    assert p["herramienta"] == "temporizador" and p["llamada"] is True
    b.resolver_aprobacion(p["id"], False)
    assert b.temporizadores == []


def test_sb2_la_lectura_oida_no_pregunta_y_la_marca_cuenta_una_vez(puente):
    b = puente
    b._llamada_transcrito("estado del pc")
    b.enviar("estado del pc", "local")
    assert b.info == [1] and b.senales["aprobacion_pedida"] == []   # lectura: sin preguntar
    # La marca ya se gastó: el mismo texto escrito después no cuenta como oído.
    b.enviar("abre youtube", "local")
    assert len(b.urls) == 1 and b.senales["aprobacion_pedida"] == []


def test_sb2_el_turno_de_ia_desde_la_llamada_sigue_igual(puente):
    b = puente
    b._llamada_transcrito("hola, ¿qué tal el día?")
    b.enviar("hola, ¿qué tal el día?", "local")
    assert len(WorkerFalso.creados) == 1
    w = WorkerFalso.creados[0]
    assert w.kw["origen"] == "usuario" and "llamada" not in w.kw["ctx"]


# ── SB3: orden remota en una conversación contaminada ──────────────────────────

def _ejecutor():
    registro = C.registro_completo()
    sesion = H.Sesion(registro, audit_path=None)
    preguntas, resultados, hechos = [], [], []
    handlers = {n: (lambda n: lambda args, ctx: hechos.append(n) or "ok")(n) for n in C.CATALOGO}
    ej = A.Ejecutor(registro, sesion, handlers, lambda p, r: preguntas.append((p, r)),
                    programar=lambda s, fn: MagicMock())
    return ej, preguntas, resultados, hechos


def _call(nombre, args=None):
    return "<|CALL " + json.dumps([nombre, args or {}]) + "|>"


def test_sb3_remoto_y_contaminado_pregunta_con_los_dos_motivos(qapp):
    from ui.acciones_qt import texto_pregunta
    ej, preguntas, resultados, hechos = _ejecutor()
    ctx = {"modo": "normal", "contaminado": True}
    _t, llamadas = ej.procesar(_call("abrir_url", {"url": "https://x.com"}), A.REMOTO, ctx)
    ej.ejecutar_llamadas(llamadas, A.REMOTO, ctx, resultados.append)
    assert hechos == [] and len(preguntas) == 1
    p = preguntas[0][0]
    assert p["remoto"] is True and p["contaminado"] is True
    assert A.AVISO_REMOTO in p["motivo"] and A.AVISO_CONTAMINADO in p["motivo"]
    texto = texto_pregunta(p)
    assert A.AVISO_REMOTO in texto and A.AVISO_CONTAMINADO in texto


def test_sb3_remoto_lectura_o_directa_no_cuentan_como_contaminado(qapp):
    ej, preguntas, resultados, _ = _ejecutor()
    ctx = {"modo": "normal", "contaminado": True}
    _t, llamadas = ej.procesar(_call("sistema_info"), A.REMOTO, ctx)
    ej.ejecutar_llamadas(llamadas, A.REMOTO, ctx, resultados.append)
    ej.ejecutar_llamadas(ToolManager().detectar_llamadas("abre youtube"), A.REMOTO, ctx, resultados.append)
    assert len(preguntas) == 2
    for p, _r in preguntas:
        assert p["remoto"] is True and not p.get("contaminado") and p["motivo"] == A.AVISO_REMOTO


def test_sb3_sin_canal_el_rechazo_dice_los_dos_motivos(qapp):
    registro = C.registro_completo()
    ej = A.Ejecutor(registro, H.Sesion(registro, audit_path=None),
                    {n: (lambda a, c: "ok") for n in C.CATALOGO}, None)
    res = []
    ctx = {"modo": "normal", "contaminado": True}
    _t, llamadas = ej.procesar(_call("abrir_url", {"url": "https://x.com"}), A.REMOTO, ctx)
    ej.ejecutar_llamadas(llamadas, A.REMOTO, ctx, res.append)
    assert not res[-1].ok and "Telegram" in res[-1].mensaje and "contenido externo" in res[-1].mensaje


# ── VS3: autoinicio solo si cambió, y sistema.autoinicio al día ────────────────

def test_vs3_guardar_config_no_reescribe_el_autoinicio_si_no_cambio(puente, monkeypatch):
    from servicios import autoinicio
    real = {"on": True}                                  # se activó desde la bandeja con Ajustes abierto
    llamadas = []

    def establecer(quiere, *a, **k):
        llamadas.append(bool(quiere))
        real["on"] = bool(quiere) and not real.get("bloqueado")
        return real["on"]

    monkeypatch.setattr(autoinicio, "activo", lambda *a, **k: real["on"])
    monkeypatch.setattr(autoinicio, "establecer", establecer)
    b = puente
    r = json.loads(b.guardar_config(json.dumps({"autoinicio": True})))
    assert r["ok"] and llamadas == []
    assert not any("Windows" in str(a) or "Autoinicio" in str(a) for a in b.senales["aviso"])
    b.guardar_config(json.dumps({"autoinicio": False}))
    assert llamadas == [False] and b.config.get("sistema", "autoinicio") is False
    # Windows no lo deja (Administrador de tareas): la config sigue al estado real.
    real["bloqueado"] = True
    b.guardar_config(json.dumps({"autoinicio": True}))
    assert llamadas == [False, True] and b.config.get("sistema", "autoinicio") is False


# ── VS5 / VS7: «Se detuvo…» a Telegram, una vez por orden ──────────────────────

def test_vs5_parar_el_bot_con_una_orden_esperando_permiso_avisa_antes(puente):
    b = puente
    tg = b._tg_worker
    b._orden_remota("o1", "abre youtube")
    assert _pedidas(b)[-1]["remoto"] is True                        # espera tu permiso
    b.telegram_toggle()
    assert tg.enviados == [("o1", tw.AVISO_TG_DETENIDA)]
    assert tg.eventos.index(("responder", "o1")) < tg.eventos.index(("stop",))
    assert b._tg_worker is None


def test_vs5_parar_el_bot_a_media_respuesta_avisa_una_vez(puente):
    b = puente
    tg = b._tg_worker
    b._orden_remota("o2", "cuéntame un chiste")
    assert WorkerFalso.creados and WorkerFalso.creados[-1].isRunning()
    b.telegram_toggle()
    assert tg.enviados == [("o2", tw.AVISO_TG_DETENIDA)]
    nuevo = TgFalso()                                              # si vuelves a encender el bot…
    b._tg_worker = nuevo
    b.limpiar_chat()                                               # …no se repite
    assert nuevo.enviados == []


def test_vs7_detener_y_luego_limpiar_chat_no_repite_el_aviso(puente):
    b = puente
    tg = b._tg_worker
    b._orden_remota("o3", "cuéntame un chiste")
    b.detener()
    assert tg.enviados == [("o3", tw.AVISO_TG_DETENIDA)]
    assert WorkerFalso.creados[-1].isRunning()                     # el worker aún no cortó
    b.limpiar_chat()
    assert tg.enviados == [("o3", tw.AVISO_TG_DETENIDA)]


# ── VS6: modo juego forzado en el relevo ───────────────────────────────────────

class JuegoFalso:
    def __init__(self, forzado=None, con_propiedad=True):
        self.forzados = []
        if con_propiedad:
            self.forzado = forzado
        self._est = {"activo": bool(forzado), "motivo": "", "forzado": forzado}

    def estado(self):
        return dict(self._est)

    def forzar(self, v):
        self.forzados.append(v)


def test_vs6_el_modo_juego_forzado_pasa_a_la_ventana_nueva(qapp):
    import ui.web_shell as ws
    bridge = types.SimpleNamespace(_provider_web="local", voice=None, chats=None, _tg_worker=None,
                                   mascota_visible=lambda: False)
    for forzado, con_propiedad in ((True, True), (False, False), (None, True)):
        vieja = types.SimpleNamespace(bridge=bridge, MODO_INTERFAZ="web",
                                      _servicios_c4=types.SimpleNamespace(juego=JuegoFalso(forzado, con_propiedad)))
        estado = ws.VentanaWeb.estado_para_cambio(vieja)
        assert estado["juego_forzado"] is forzado
        juego = JuegoFalso()
        nb = types.SimpleNamespace(escritorio=None, mascota_visible=lambda: False, _tg_worker=None)
        nueva = types.SimpleNamespace(_servicios=False, bridge=nb, tray=None,
                                      _servicios_c4=types.SimpleNamespace(juego=juego, bandeja=object()))
        ws.VentanaWeb.iniciar_servicios(nueva, dict(estado))
        assert juego.forzados == ([] if forzado is None else [forzado])
    sin = types.SimpleNamespace(bridge=bridge, MODO_INTERFAZ="web", _servicios_c4=None)
    assert ws.VentanaWeb.estado_para_cambio(sin)["juego_forzado"] is None


# ── RH3: cambio de interfaz dentro del bucle anidado de _esperar_en_hilo ────────

def test_rh3_el_relevo_espera_a_que_acabe_la_espera_anidada(qapp):
    from PyQt6.QtWidgets import QMainWindow
    from ui.cambio_interfaz import GestorInterfaz
    from ui.web_bridge import LuneBridge

    log = []

    class Puente(QObject):
        _esperar_en_hilo = LuneBridge._esperar_en_hilo
        _esperar_en_hilo_sin_anidar = staticmethod(LuneBridge._esperar_en_hilo_sin_anidar)

        def __init__(self, parent):
            super().__init__(parent)
            self._esperando_hilo = False

        def compat_probar(self):
            """Como «Probar conexión»: espera a un hilo en un bucle anidado."""
            r = self._esperar_en_hilo(lambda: (time.sleep(0.6), "ok")[1], 5.0)
            try:
                self.objectName()
                log.append(("slot vuelve", "vivo", r))
            except RuntimeError:
                log.append(("slot vuelve", "BORRADO", r))

    class Vieja(QMainWindow):
        MODO_INTERFAZ = "web"

        def __init__(self):
            super().__init__()
            self.bridge = Puente(self)

        def estado_para_cambio(self):
            return {}

        def cerrar_para_cambio(self):
            log.append(("cerrar vieja",))
            return {}

    class Nueva:
        MODO_INTERFAZ = "nativo"

        def al_estar_lista(self, cb, _tope):
            cb()

        def show(self):
            log.append(("mostrar nueva",))

        def iniciar_servicios(self, _estado):
            log.append(("servicios nueva",))

    vieja = Vieja()
    borrada = []
    vieja.destroyed.connect(lambda *_: borrada.append(1))
    gestor = GestorInterfaz(lambda m: Nueva(), guardar_modo=lambda m: None, fundido_ms=0)
    gestor.adoptar(vieja, "web")
    # Mientras el slot espera (bucle anidado), la página pide otro modo.
    QTimer.singleShot(100, lambda: log.append(("pedir", gestor.pedir("nativo"))))
    vieja.bridge.compat_probar()
    assert ("pedir", True) in log
    assert log[-1][:2] == ("slot vuelve", "vivo"), log                # el puente seguía vivo
    assert ("cerrar vieja",) not in log                                # el relevo no se hizo dentro
    assert esperar(qapp, lambda: gestor.modo == "nativo" and borrada, 5.0), log
    orden = [e[0] for e in log]
    assert orden.index("slot vuelve") < orden.index("cerrar vieja") < orden.index("servicios nueva")
    assert gestor._espera is None and gestor._guarda is None      # sin temporizadores colgando
    gestor.deleteLater()
    qapp.processEvents()


# ── RH6: telegram_worker ───────────────────────────────────────────────────────

def test_rh6_parar_durante_npm_install_no_lanza_el_bot(qapp, tmp_path, monkeypatch):
    w = tw.TelegramBotWorker(ordenes=True)
    w.BOT_DIR = tmp_path                                           # sin node_modules: instala
    w._node = "node"
    (tmp_path / "package-lock.json").write_text("{}", "utf-8")
    monkeypatch.setattr(tw, "comando_npm", lambda node, which=None: ["npm-falso"])
    lanzados, parados = [], []
    w.stopped.connect(lambda: parados.append(1))

    class NpmFalso:                                                # `npm ci` a medias
        pid, returncode, matado = None, None, False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode, self.matado = 1, True

        kill = terminate

        def wait(self, timeout=None):
            return self.returncode

        def communicate(self, timeout=None):
            w.stop()                                              # cambio de interfaz a mitad
            return "", None

    npm = NpmFalso()

    def popen(args, **k):
        lanzados.append(args)
        return npm if len(lanzados) == 1 else MagicMock()

    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w.run()
    assert lanzados == [["npm-falso", *tw.ARGS_NPM_CI]] and parados == [1]   # el bot, no
    assert npm.matado and w._instalador is None                  # stop() mató a npm


def test_rh6_parar_justo_al_lanzar_cierra_el_bot(qapp, tmp_path, monkeypatch):
    (tmp_path / "node_modules" / "grammy").mkdir(parents=True)
    (tmp_path / "node_modules" / "grammy" / "package.json").write_text("{}", "utf-8")
    w = tw.TelegramBotWorker(ordenes=True)
    w.BOT_DIR = tmp_path
    w._node = "node"

    class Stdin:
        cerrado = False

        def close(self):
            self.cerrado = True

    class Proc:
        def __init__(self):
            self.stdin, self.stdout, self.vivo = Stdin(), iter(["no debería leerse\n"]), True

        def poll(self):
            return None if self.vivo else 0

        def wait(self, timeout=None):
            if self.stdin.cerrado:
                self.vivo = False
            if self.vivo:
                raise subprocess.TimeoutExpired("npm", timeout)
            return 0

        def terminate(self):
            self.vivo = False

        def kill(self):
            self.vivo = False

    procs, logs = [], []
    w.log_signal.connect(logs.append)

    def popen(*a, **k):
        w._parar.set()                                            # stop() llega mientras arranca
        procs.append(Proc())
        return procs[-1]

    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w.run()
    assert procs and procs[0].stdin.cerrado and not procs[0].vivo
    assert "no debería leerse" not in logs


class StdinLento:
    """Un bot que no lee su stdin: write se queda esperando hasta `soltar`."""
    def __init__(self):
        self.soltar = threading.Event()
        self.escrito, self.cerrado = [], False

    def write(self, s):
        self.soltar.wait(20)
        self.escrito.append(s)

    def flush(self):
        pass

    def close(self):
        self.cerrado = True


class ProcesoLento:
    def __init__(self):
        self.stdin, self.vivo, self.terminado = StdinLento(), True, False

    def poll(self):
        return None if self.vivo else 0

    def wait(self, timeout=None):
        if self.vivo:
            raise subprocess.TimeoutExpired("npm", timeout)
        return 0

    def terminate(self):
        self.terminado, self.vivo = True, False

    def kill(self):
        self.vivo = False


def _con_tope(fn, tope_s=2.0):
    """fn() en un hilo: (terminó a tiempo, resultado)."""
    caja = {}
    h = threading.Thread(target=lambda: caja.setdefault("r", fn()), daemon=True)
    h.start()
    h.join(tope_s)
    return (not h.is_alive()), caja.get("r")


def test_rh6_responder_orden_no_bloquea_aunque_el_bot_no_lea(qapp, monkeypatch):
    monkeypatch.setattr(tw, "COLA_RESPUESTAS", 4)
    w = tw.TelegramBotWorker(ordenes=True)
    logs = []
    w.log_signal.connect(logs.append)
    p = ProcesoLento()
    w._process = p
    try:
        a_tiempo, r = _con_tope(lambda: w.responder_orden("ab12", "primera"))
        assert a_tiempo and r is True                             # el escritor se queda esperando, no Qt
        fin = time.monotonic() + 5
        while w._cola.qsize() and time.monotonic() < fin:      # el escritor ya la tiene (atascado)
            time.sleep(0.01)
        resultados = [w.responder_orden("ab12", f"m{i}") for i in range(8)]
        assert resultados[:4] == [True] * 4 and resultados[4:] == [False] * 4   # cola llena: fuera
        assert logs.count(tw.AVISO_COLA_LLENA) == 1               # un aviso, no uno por mensaje
        # Parar con el escritor atascado tampoco bloquea: no cierra el stdin, termina el bot.
        a_tiempo, _ = _con_tope(w.stop, 6.0)
        assert a_tiempo and p.terminado and not p.stdin.cerrado
    finally:
        p.stdin.soltar.set()
    assert w.esperar_envios(5)
    assert json.loads(p.stdin.escrito[0])["texto"] == "primera"
    h = w._escritor                                                # sin bot ya: el escritor se va solo
    if h is not None:
        h.join(5)
        assert not h.is_alive()


# ── SB4: la vista de la mascota con la guarda de navegación ────────────────────
# Sin crear páginas de WebEngine de verdad (en este entorno un QWebEnginePage suelto
# tumba el proceso): PaginaLune se sustituye por una que usa SU MISMA
# acceptNavigationRequest y apunta los ajustes; asegurar_pagina es la real.

@pytest.fixture
def web_con_pagina(monkeypatch):
    """QWebEngineView falso que acepta setPage, y PaginaLune de mentira con la lógica real."""
    if not HAY_WEBENGINE:
        pytest.skip("la mascota web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp
    import ui.web_shell as ws

    class Ajustes:
        def __init__(self):
            self.attrs = {}

        def setAttribute(self, a, v):
            self.attrs[a] = v

    class PaginaFalsa(QObject):
        acceptNavigationRequest = ws.PaginaLune.acceptNavigationRequest   # la guarda de verdad

        def __init__(self, origen, parent=None, abrir_fuera=None):
            super().__init__(parent)
            self.origen, self._abrir_fuera, self.rechazadas = QUrl(origen), abrir_fuera, []
            self.ajustes, self.js = Ajustes(), []

        def settings(self):
            return self.ajustes

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)

        def __init__(self):
            super().__init__()
            self._pagina, self._url = None, QUrl()

        def setPage(self, p):
            self._pagina = p

        def page(self):
            return self._pagina

        def settings(self):
            return self._pagina.settings() if self._pagina is not None else Ajustes()

        def setUrl(self, url):
            self._url = url

        def url(self):
            return self._url

        def focusProxy(self):
            return None

    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    monkeypatch.setattr(ws, "PaginaLune", PaginaFalsa)
    return PaginaFalsa


def test_sb4_la_mascota_web_solo_navega_por_su_servidor(qapp, tmp_path, web_con_pagina, monkeypatch):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from nucleo import personajes
    from nucleo.config import Config
    import ui.web_shell as ws
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    c = CompanionFlotante(cfg, ai_manager=None, bandeja=False)
    try:
        pagina = c.web.page()
        assert isinstance(pagina, web_con_pagina)
        assert ws.mismo_origen(QUrl(c._url_pagina()), pagina.origen)
        assert pagina.origen.port() == c._servidor.puerto
        attr = getattr(QWebEngineSettings.WebAttribute, "NavigateOnDropEnabled", None)
        if attr is not None:
            assert pagina.ajustes.attrs.get(attr) is False
        abiertas = []
        pagina._abrir_fuera = lambda u: abiertas.append(u.toString())
        T_ = QWebEnginePage.NavigationType
        aceptar = pagina.acceptNavigationRequest
        assert aceptar(QUrl(c._url_pagina()), T_.NavigationTypeReload, True) is True
        # Soltar un enlace o un archivo sobre ella (en grande, todo el monitor): nada.
        assert aceptar(QUrl("https://evil.example/soltado"), T_.NavigationTypeTyped, True) is False
        assert aceptar(QUrl("file:///C:/Users/x/pagina.html"), T_.NavigationTypeTyped, True) is False
        assert aceptar(QUrl("data:text/html,<b>x</b>"), T_.NavigationTypeLinkClicked, True) is False
        assert aceptar(QUrl("https://evil.example/"), T_.NavigationTypeRedirect, True) is False
        assert abiertas == []
        # Un enlace pulsado: al navegador del sistema, no en la mascota.
        assert aceptar(QUrl("https://www.youtube.com/"), T_.NavigationTypeLinkClicked, True) is False
        assert abiertas == ["https://www.youtube.com/"]
    finally:
        c.close()
        c.deleteLater()


# ── VS1 (parte web): el radial de la web cuenta a Lune en la barra lateral ─────

def test_vs1_el_puente_filtra_el_radial_con_el_contexto_del_montaje(qapp, tmp_path):
    acc = pytest.importorskip("nucleo.acciones_ui")
    if "mascota_barra" not in getattr(acc.Contexto, "_fields", ()):
        pytest.skip("nucleo.acciones_ui aún sin Contexto.mascota_barra (agente NATIVA)")
    from nucleo.config import Config
    from ui.puente_escritorio import PuenteEscritorio
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("menu_radial", "principal", ["expresiones", "bailar", "dormir", "voz"])
    desp = acc.Despachador()
    hechos = []
    for i in ("expresiones", "bailar", "dormir", "voz"):
        desp.registrar(i, lambda i=i: hechos.append(i))
    desp.registrar("expresion", lambda arg="": hechos.append(("expresion", arg)))
    caja = {"ctx": acc.Contexto(modo="normal", render="animado", mascota_visible=False, mascota_barra=True)}
    serv = types.SimpleNamespace(despachador=desp, tema=None, atajos=None, juego=None, radial=None,
                                 bandeja=None, contexto=lambda: caja["ctx"])
    esc = types.SimpleNamespace(estado=None, mascota=None)
    p = PuenteEscritorio(serv, esc, cfg)
    ids = [i["id"] for i in json.loads(p.acciones_catalogo("radial"))]
    assert "expresiones" in ids and "bailar" in ids and "dormir" not in ids
    assert p.accion_menu("expresion", "happy") and hechos[-1] == ("expresion", "happy")
    # Sin Lune en la barra (ni la flotante): nada de expresiones ni baile.
    caja["ctx"] = acc.Contexto(modo="normal", render="animado", mascota_visible=False, mascota_barra=False)
    ids = [i["id"] for i in json.loads(p.acciones_catalogo("radial"))]
    assert "expresiones" not in ids and "bailar" not in ids and "voz" in ids
