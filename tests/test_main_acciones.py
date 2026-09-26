"""
Tests de integración de la ventana nativa (main.py) con el corte 2:

  · _on_response procesa las <|CALL|> con el Ejecutor (AccionesQt) al terminar
    la respuesta; el formato antiguo ya no ejecuta nada; «Detener», acciones_ia
    apagado o el modo terminal (el host ya las hizo) no ejecutan.
  · El chat de la mascota (`on_chat`) entra por el flujo normal y la respuesta
    sale también en su burbuja.
  · La pestaña del proveedor 'compat' aparece y desaparece con la config.

Sin construir la ventana entera (red, voz, timers…): se enlazan los métodos
reales a un objeto de mentira, como en test_escritorio.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")

from lune_core import acciones as A  # noqa: E402
from servicios import tools as T  # noqa: E402
from servicios.tools import ToolManager, ToolResult  # noqa: E402


class ConfigFalsa:
    def __init__(self, **features):
        self.features = features

    def feature(self, clave, defecto=True):
        return self.features.get(clave, defecto)

    def get(self, seccion, clave, defecto=None):
        return defecto


def _enlazar(yo, *nombres):
    import main
    for n in nombres:
        setattr(yo, n, types.MethodType(getattr(main.LuneCDWindow, n), yo))
    return yo


@pytest.fixture
def ventana(qapp, monkeypatch):
    """Un «self» de LuneCDWindow con AccionesQt real y el resto de mentira."""
    from ui.acciones_qt import AccionesQt
    urls = []
    monkeypatch.setattr(T.webbrowser, "open", lambda u, *a, **k: urls.append(u) or True)
    tm = ToolManager()
    lanzadas = []
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, f"Abrí {n}"))
    tm.registrar_handler("lanzar_app", tm._h_lanzar_app)
    preguntas = []
    acc = AccionesQt(tm, ventana_visible=lambda: True,
                     preguntar=lambda p, r: preguntas.append((p, r)),
                     audit_path=None, programar=lambda s, fn: MagicMock())
    yo = MagicMock()
    yo.config = ConfigFalsa()
    yo.ai_manager = MagicMock(name="ai_manager")
    yo._motor_chat = yo.ai_manager
    yo.acciones = acc
    yo._typing_indicator = None
    yo._current_bubble = MagicMock(name="burbuja")
    yo._voz_stream = None
    yo._cancelado = False
    yo._overlay = None
    yo._turno = {"origen": A.USUARIO, "ctx": {"modo": "normal", "proveedor": "ollama", "url": ""},
                 "mascota": False}
    yo.ai_worker = None
    yo._gen = 0
    yo._esperando_corte = False
    resultados = []
    acc.resultado.connect(resultados.append)
    # _resultado_turno: la señal de verdad no existe en el MagicMock; se entrega directa.
    yo._resultado_turno = types.SimpleNamespace(emit=lambda r, i: yo._on_resultado_turno(r, i))
    _enlazar(yo, "_on_response", "_on_token", "_on_error", "_acciones_locales", "_eco_mascota",
             "_burbuja_mascota", "_chat_desde_mascota", "_ejecutar_acciones", "_on_resultado_turno",
             "_on_resultado_accion", "_worker_vivo", "_cancelar_worker", "_stop_generation",
             "_cortar_respuesta", "_al_terminar_worker")
    yield {"yo": yo, "acc": acc, "preguntas": preguntas, "lanzadas": lanzadas, "urls": urls,
           "res": resultados, "tm": tm}
    acc.cerrar()


def _texto_guardado(yo):
    rol, texto = yo._guardar_turno.call_args.args[:2]
    assert rol == "assistant"
    return texto


def test_on_response_ejecuta_los_call_al_terminar(ventana):
    yo = ventana["yo"]
    yo._on_response('Te abro YouTube. <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>')
    assert ventana["urls"] == ["https://www.youtube.com"]
    assert ventana["res"][-1].ok
    assert _texto_guardado(yo) == "Te abro YouTube."
    yo.memoria.procesar_respuesta_lune.assert_called_with("Te abro YouTube.")


def test_on_response_pide_permiso_para_lanzar_una_app(ventana):
    yo = ventana["yo"]
    yo._on_response('Va. <|CALL ["lanzar_app", {"app": "calc"}]|>')
    assert ventana["lanzadas"] == [] and len(ventana["preguntas"]) == 1
    pendiente, responder = ventana["preguntas"][0]
    assert pendiente["herramienta"] == "lanzar_app" and pendiente["args"] == {"app": "calc"}
    responder(True)
    assert ventana["lanzadas"] == ["calc"] and ventana["res"][-1].ok


def test_el_formato_antiguo_ya_no_se_ejecuta(ventana):
    yo = ventana["yo"]
    yo._on_response("Listo.\nABRIR_URL:https://malo.example\nTOOL:lanzar_app:calc")
    assert ventana["urls"] == [] and ventana["lanzadas"] == [] and ventana["preguntas"] == []
    assert _texto_guardado(yo) == "Listo."


def test_turno_no_confiable_solo_lectura(ventana):
    yo = ventana["yo"]
    yo._turno["origen"] = A.NO_CONFIABLE        # p. ej. con notas o adjuntos en el prompt
    yo._on_response('<|CALL ["abrir_url", {"url": "https://x.com"}]|>')
    assert ventana["urls"] == [] and ventana["res"][-1].estado == A.NO_CONFIABLE_ESTADO


@pytest.mark.parametrize("ajuste", ["cancelado", "sin_acciones", "terminal"])
def test_casos_en_que_no_se_ejecuta_nada(ventana, ajuste):
    yo = ventana["yo"]
    if ajuste == "cancelado":
        yo._cancelado = True
    elif ajuste == "sin_acciones":
        yo.config = ConfigFalsa(acciones_ia=False)
    else:
        yo._motor_chat = MagicMock(name="chat_remoto")     # el host ya las ejecutó
    yo._on_response('Hecho. <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>')
    assert ventana["urls"] == [] and ventana["res"] == []
    assert _texto_guardado(yo) == "Hecho."                  # la marca nunca se ve


def test_la_respuesta_del_chat_de_la_mascota_sale_en_su_burbuja(ventana):
    yo = ventana["yo"]
    ov = MagicMock()
    ov.cerrado = False
    yo._mascota_viva = lambda: ov
    yo._turno["mascota"] = True
    yo._on_response("¡Hola! <|ACT {\"emotion\": \"happy\"}|>")
    ov.burbuja_texto.assert_called_with("¡Hola!")
    assert ov.burbuja_fin.call_args.args[0] >= 8000
    ov.reset_mock()
    yo._current_bubble = MagicMock(name="burbuja")
    yo._turno["mascota"] = False                            # turno de la ventana: nada
    yo._on_response("Otra cosa.")
    ov.burbuja_texto.assert_not_called()


def test_chat_desde_mascota_usa_el_flujo_normal(ventana):
    yo = ventana["yo"]
    yo.ai_worker = None
    assert yo._chat_desde_mascota("  hola lune  ") is True
    yo._send_message.assert_called_once_with(texto="hola lune", desde_mascota=True)
    assert yo._chat_desde_mascota("   ") is False
    # Si aún está respondiendo, no se pisa: aviso en la burbuja.
    yo._send_message.reset_mock()
    yo.ai_worker = MagicMock()
    yo.ai_worker.isRunning.return_value = True
    ov = MagicMock()
    yo._mascota_viva = lambda: ov
    assert yo._chat_desde_mascota("otra") is False
    yo._send_message.assert_not_called()
    ov.burbuja_texto.assert_called_once()


def test_crear_mascota_le_pone_on_chat(qapp, tmp_path, monkeypatch):
    import main
    from nucleo.config import Config

    class Falsa:
        def __init__(self, config=None):
            self.config = config

    monkeypatch.setattr(main, "AvatarOverlay", Falsa)
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "sprites")
    yo = types.SimpleNamespace(config=cfg, ai_manager=None, escritorio=None, _overlay=None,
                               _on_mascota_visible=lambda v: None, _mascota_recrear=lambda: None,
                               _chat_desde_mascota=lambda t: True)
    _enlazar(yo, "_escritorio_mascota", "_crear_mascota")
    ov = yo._crear_mascota()
    assert ov.on_chat is yo._chat_desde_mascota


def test_pestana_compat_aparece_y_desaparece(qapp, monkeypatch):
    import main
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    from ui.chat_widgets import ProviderTab
    from ui.theme import PROVIDER_META
    monkeypatch.setattr(main.datos, "compat_model", lambda: "qwen2.5-7b")
    monkeypatch.setattr(main.datos, "compat_url", lambda: "http://localhost:1234/v1")
    monkeypatch.setattr(main.datos, "ollama_model", lambda: "llama3")
    caja = QWidget()
    layout = QVBoxLayout(caja)
    tabs = {}
    for pid, meta in PROVIDER_META.items():
        tabs[pid] = ProviderTab(pid, meta); layout.addWidget(tabs[pid])
    layout.addStretch()
    yo = types.SimpleNamespace(_sidebar_layout=layout, provider_tabs=tabs, current_provider="openrouter",
                               ai_manager=types.SimpleNamespace(providers={"ollama": 1, "openrouter": 2}))
    cambios = []
    yo._switch_provider = lambda pid: (cambios.append(pid), setattr(yo, "current_provider", pid))
    _enlazar(yo, "_sincronizar_tab_compat")
    yo._sincronizar_tab_compat()
    assert "compat" not in tabs
    yo.ai_manager.providers = {"ollama": 1, "openrouter": 2, "compat": 3}
    yo._sincronizar_tab_compat()
    tab = tabs["compat"]
    assert layout.indexOf(tab) == len(PROVIDER_META)          # justo tras las otras pestañas
    assert tab.desc_lbl.text() == "qwen2.5-7b" and "localhost:1234" in tab.toolTip()
    yo._sincronizar_tab_compat()                               # idempotente
    assert list(tabs).count("compat") == 1
    yo.current_provider = "compat"
    yo.ai_manager.providers = {"ollama": 1, "openrouter": 2}
    yo._sincronizar_tab_compat()
    assert "compat" not in tabs and cambios == ["ollama"]


def test_main_ya_no_llama_al_parser_antiguo():
    codigo = (Path(__file__).resolve().parent.parent / "main.py").read_text("utf-8")
    assert "parsear_respuesta_ia" not in codigo
    assert "self.tools.ejecutar(" not in codigo
    assert "conectar_herramientas(self.tools)" in codigo
    assert "self.voice.on_error" in codigo and "reiniciar_motor()" in codigo


def test_la_pregunta_va_junto_a_la_mascota_si_la_ventana_no_esta_delante():
    yo = types.SimpleNamespace(_turno={"mascota": False})
    estado = {"vis": True, "min": False, "act": True}
    yo.isVisible = lambda: estado["vis"]
    yo.isMinimized = lambda: estado["min"]
    yo.isActiveWindow = lambda: estado["act"]
    _enlazar(yo, "_ventana_a_la_vista")
    assert yo._ventana_a_la_vista() is True                     # QMessageBox sobre la ventana
    for clave, valor in (("vis", False), ("min", True), ("act", False)):
        estado.update({"vis": True, "min": False, "act": True, clave: valor})
        assert yo._ventana_a_la_vista() is False                # DialogoAprobacion
    estado.update({"vis": True, "min": False, "act": True})
    yo._turno["mascota"] = True                                 # chat de la mascota
    assert yo._ventana_a_la_vista() is False


# ── Revisión cortes 2+3: generación, cortes, proveedor, mascota y lo pedido ─────────

from unittest.mock import ANY  # noqa: E402

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


class WorkerFalso(QObject):
    """Lo que main.py toca de un AIWorker: sus señales, isRunning y provider_id."""
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, provider_id="ollama", *a, **k):
        super().__init__()
        self.provider_id = provider_id
        self.vivo = True

    def isRunning(self):
        return self.vivo

    def start(self):
        pass


def test_detener_y_reenviar_no_ejecuta_los_call_de_la_respuesta_detenida(ventana):
    """G1: tras «Detener», un envío rápido no arranca otro hilo mientras el viejo
    corta (ni le baja cancel_flag) y la respuesta detenida no ejecuta sus <|CALL|>."""
    yo = ventana["yo"]
    prov = types.SimpleNamespace(cancel_flag=False)
    yo.ai_manager.providers = {"ollama": prov}
    w = WorkerFalso("ollama")
    yo.ai_worker, yo._gen = w, 1
    w.response_ready.connect(lambda r, g=1: yo._on_response(r, g))
    yo._stop_generation()
    assert prov.cancel_flag is True and yo._cancelado is True
    _enlazar(yo, "_send_message")
    yo._send_message(texto="otra cosa")
    assert yo.ai_worker is w and prov.cancel_flag is True and yo._esperando_corte is True
    yo._set_status.assert_called_with("ESPERA · CORTANDO LO ANTERIOR", ANY)
    yo._guardar_turno.assert_not_called()                   # ni se apuntó el mensaje
    w.response_ready.emit('Vale <|CALL ["abrir_url", {"url": "https://ejemplo.com"}]|>')
    assert ventana["urls"] == [] and ventana["res"] == []
    assert _texto_guardado(yo) == "Vale"                    # la parcial sí se queda
    w.vivo = False
    yo._al_terminar_worker()
    assert yo._esperando_corte is False
    yo._set_status.assert_called_with("LISTO", ANY)


def test_las_senales_de_un_envio_cortado_se_ignoran(ventana, monkeypatch):
    """G1/P1: cada envío lleva su generación; tras cortarlo, su token/respuesta/error
    no pintan ni ejecutan nada y las señales quedan desconectadas."""
    import main
    yo = ventana["yo"]
    creados = []

    class AIWorkerFalso(WorkerFalso):
        def __init__(self, motor, texto, prov, **kw):
            super().__init__(prov)
            self.kw = kw
            creados.append(self)

    monkeypatch.setattr(main, "AIWorker", AIWorkerFalso)
    monkeypatch.setattr(main, "TypingIndicator", lambda p: MagicMock(name="indicador"))
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: MagicMock(name="burbuja"))
    yo.memoria.procesar_mensaje_usuario.return_value = None
    yo.memoria.obtener_contexto_para_prompt.return_value = ""
    yo.config = ConfigFalsa(respuestas_predeterminadas=False)
    yo.tools = ventana["tm"]
    yo.notas.activo = False
    yo._modo_red = "local"
    yo._modo_acciones = lambda: "normal"
    yo.current_provider = "ollama"
    prov = types.SimpleNamespace(cancel_flag=True)          # un «Detener» viejo
    yo.ai_manager.providers = {"ollama": prov}
    _enlazar(yo, "_send_message")
    yo._send_message(texto="hola")
    w = creados[-1]
    assert prov.cancel_flag is False and yo._turno["proveedor"] == "ollama"
    assert yo._turno["ctx"]["ai"] is yo.ai_manager                  # ctx con "ai" (taint)
    g = yo._gen
    yo._cortar_respuesta()                                          # p. ej. «Limpiar chat»
    assert yo._gen == g + 1 and prov.cancel_flag is True
    assert yo._typing_indicator is None and yo._current_bubble is None and yo._turno == {}
    yo._guardar_turno.reset_mock()
    w.token_received.emit("x")                                      # desconectadas
    w.response_ready.emit('Hecho <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>')
    yo._on_token("parcial", g)
    yo._on_response('Hecho <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>', g)
    yo._on_error("fallo", g)
    assert ventana["urls"] == [] and ventana["res"] == [] and not yo._guardar_turno.called


def test_conversacion_nueva_con_la_ia_escribiendo_no_toca_widgets_borrados(ventana, monkeypatch):
    """P1: LIMPIAR CHAT a mitad de respuesta borraba el indicador pero lo conservaba;
    el siguiente token hacía .stop() sobre un QTimer borrado → RuntimeError en un
    slot → PyQt6 cerraba la app."""
    import main
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    from ui.chat_widgets import TypingIndicator
    monkeypatch.setattr(main.datos, "get_bot", lambda: {"personaje_default": "Lune"})
    yo = ventana["yo"]
    caja = QWidget()
    yo.messages_layout = QVBoxLayout(caja)
    yo.messages_layout.addStretch()
    indicador = TypingIndicator("ollama")
    yo.messages_layout.insertWidget(0, indicador)
    yo._typing_indicator, yo._current_bubble = indicador, None
    prov = types.SimpleNamespace(cancel_flag=False)
    yo.ai_manager.providers = {"ollama": prov}
    w = WorkerFalso("ollama")
    yo.ai_worker, yo._gen = w, 3
    w.token_received.connect(lambda t, g=3: yo._on_token(t, g))
    _enlazar(yo, "_nueva_conversacion")
    yo._nueva_conversacion()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    w.token_received.emit("Hola")
    yo._on_token("Hola", 3)
    yo._on_response("Hola", 3)
    yo._on_token("Hola")                                    # aun sin generación: nada colgando
    assert prov.cancel_flag is True and yo._typing_indicator is None
    assert yo.messages_layout.count() == 1                  # solo el stretch (la bienvenida es de mentira)


def test_cambiar_de_proveedor_a_mitad_detiene_el_del_turno_y_el_uso_es_del_turno(ventana):
    """P2: «Detener» cancelaba el proveedor NUEVO y el uso se leía del nuevo."""
    yo = ventana["yo"]
    ollama, nube = types.SimpleNamespace(cancel_flag=False), types.SimpleNamespace(cancel_flag=False)
    yo.ai_manager.providers = {"ollama": ollama, "openrouter": nube}
    yo.current_provider = "ollama"
    yo._turno["proveedor"] = "ollama"
    yo.ai_worker = WorkerFalso("ollama")
    yo.provider_tabs = {}
    _enlazar(yo, "_switch_provider")
    yo._switch_provider("openrouter")
    assert ollama.cancel_flag is True and nube.cancel_flag is False
    assert yo.current_provider == "openrouter"
    yo._on_response("Hola.")
    yo.ai_manager.uso.assert_called_with("ollama")


def test_resultado_de_acciones_del_chat_de_la_mascota_sale_en_su_burbuja(ventana):
    """Funcional 4: el ✓/✕ de una acción (también tras aprobar) de un turno que salió
    de la mascota se ve en su burbuja, aunque entre tanto escribas en la ventana."""
    yo = ventana["yo"]
    ov = MagicMock()
    ov.cerrado = False
    ov.isVisible.return_value = True
    yo._mascota_viva = lambda: ov
    yo._turno["mascota"] = True
    yo._on_response('Va. <|CALL ["lanzar_app", {"app": "calc"}]|>')
    _pendiente, responder = ventana["preguntas"][0]
    yo._turno = {"origen": A.USUARIO, "ctx": None, "mascota": False}      # otro turno, de la ventana
    ov.reset_mock()
    responder(True)
    assert ventana["lanzadas"] == ["calc"]
    texto = ov.burbuja_texto.call_args.args[0]
    assert texto.startswith("✓") and "calc" in texto and ov.burbuja_fin.called
    yo._burbuja_bot.assert_called_with(texto)                              # y en el chat


def test_eco_de_la_mascota_nada_si_esta_oculta(ventana):
    """F2/R6: con la mascota oculta, la burbuja no reaparece sola en cada trozo."""
    yo = ventana["yo"]
    ov = MagicMock()
    ov.cerrado = False
    ov.isVisible.return_value = False
    yo._mascota_viva = lambda: ov
    yo._turno["mascota"] = True
    yo._eco_mascota("Hola", fin=True)
    yo._on_token("Hola, ¿qué")
    ov.burbuja_texto.assert_not_called()
    ov.burbuja_fin.assert_not_called()


def test_lo_pedido_con_palabras_va_por_el_ejecutor_y_se_guarda(ventana, monkeypatch):
    """«abre youtube»: detectar_llamadas → Ejecutor (sin IA); el ✓ sale en el chat, se
    guarda en la conversación y, si vino de la mascota, en su burbuja."""
    import main
    yo = ventana["yo"]
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: MagicMock(name="burbuja"))
    yo.memoria.procesar_mensaje_usuario.return_value = None
    yo.config = ConfigFalsa(respuestas_predeterminadas=False)
    yo.tools = ventana["tm"]
    yo.current_provider = "ollama"
    yo._modo_acciones = lambda: "normal"
    ov = MagicMock()
    ov.cerrado = False
    ov.isVisible.return_value = True
    yo._mascota_viva = lambda: ov
    _enlazar(yo, "_send_message")
    yo._send_message(texto="abre youtube", desde_mascota=True)
    assert ventana["urls"] == ["https://www.youtube.com"]
    assert yo.ai_worker is None                                            # sin IA
    assert yo._turno["ctx"]["ai"] is yo.ai_manager
    guardado = _texto_guardado(yo)
    assert guardado.startswith("✓") and ov.burbuja_texto.call_args.args[0] == guardado


def test_red_de_excepciones_la_app_sigue_tras_un_error_en_un_slot(tmp_path):
    """P1 (red de seguridad): con el excepthook de main() una excepción en un slot
    se registra y el proceso sigue (sin él, PyQt6 lo aborta)."""
    import subprocess
    script = tmp_path / "slot.py"
    script.write_text(
        "import os, sys\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        f"sys.path.insert(0, {str(RAIZ)!r})\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "from PyQt6.QtCore import QThread, QObject, QTimer, pyqtSignal\n"
        "app = QApplication(sys.argv)\n"
        "import main\n"
        "main.log_error = lambda m: print('LOG', m.splitlines()[0], flush=True)\n"
        "main._instalar_red_de_excepciones()\n"
        "class W(QThread):\n"
        "    listo = pyqtSignal(str)\n"
        "    def run(self):\n"
        "        self.listo.emit('x')\n"
        "class R(QObject):\n"
        "    def on(self, _):\n"
        "        raise RuntimeError('objeto borrado (simulado)')\n"
        "r = R(); w = W(); w.listo.connect(r.on); w.start()\n"
        "QTimer.singleShot(800, app.quit)\n"
        "app.exec()\n"
        "w.wait(2000)\n"
        "print('SIGUE_VIVA', flush=True)\n", "utf-8")
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       timeout=180, cwd=str(RAIZ), encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0 and "SIGUE_VIVA" in r.stdout, (r.stdout, r.stderr)
    assert "LOG [ui] excepción no capturada" in r.stdout and "simulado" in r.stderr


def test_on_hablando_llega_tambien_a_la_mascota_oculta():
    """Si se oculta la mascota mientras habla, el «ya calló» tiene que llegarle:
    si no, se queda «hablando» para siempre (no se duerme, sonidos callados)."""
    import main

    class MascotaOculta:
        def __init__(self):
            self.recibido = []

        def isVisible(self):
            return False

        def set_hablando(self, on):
            self.recibido.append(on)

    ov = MascotaOculta()
    falso = types.SimpleNamespace(_mascota_viva=lambda: ov)
    main.LuneCDWindow._on_hablando(falso, True)
    main.LuneCDWindow._on_hablando(falso, False)
    assert ov.recibido == [True, False]
