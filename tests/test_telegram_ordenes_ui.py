"""
Órdenes desde Telegram (/pc) en las dos interfaces: `_orden_remota` de la piel web
(ui/web_bridge.py) y de la nativa (main.py), con dobles.

  · Función desactivada (o sin tu ID) → «desactivadas» a Telegram, nada más.
  · Lune ocupada (respondiendo o esperando que apruebes otra orden) → «ocupada».
  · Comando directo («abre youtube»): SIN IA, por el Ejecutor con origen 'remoto';
    la aprobación se pide en el PC (modal de la página / pregunta de la ventana) y
    el ✓/✕ vuelve a Telegram, también si caduca o se rechaza.
  · Turno de IA con origen 'remoto': la respuesta limpia vuelve a Telegram y sus
    acciones piden permiso; un error de la IA también vuelve como texto.
  · telegram_toggle abre el canal según la config y conecta la orden (en cola).
  · Ajustes: interruptor y tu ID de Telegram.

Sin red, sin Telegram, con datos.json y config.json en carpetas temporales.
"""
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

# QtWebEngine tiene que importarse ANTES de crear la QApplication (la crea conftest).
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
except ImportError:
    pass

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from lune_core import acciones as A  # noqa: E402
from servicios import telegram_worker as tw  # noqa: E402
from servicios import tools as T  # noqa: E402
from servicios.tools import ToolManager, ToolResult  # noqa: E402


# ── Dobles ─────────────────────────────────────────────────────────────────────

class TgFalso:
    """El TelegramBotWorker visto desde la app: lo que se manda de vuelta al bot."""
    def __init__(self):
        self.enviados = []

    def responder_orden(self, oid, texto):
        self.enviados.append((oid, texto))
        return True

    def isRunning(self):
        return True

    def textos(self, oid=None):
        return [t for o, t in self.enviados if oid is None or o == oid]


class VozFalsa:
    def __init__(self):
        self._enabled = False
        self.available = False
        self.on_error = None
        self.al_hablar = None

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
        self.motor, self.message, self.provider_id, self.kw = motor, message, provider_id, kw
        self.corriendo = False
        WorkerFalso.creados.append(self)

    def start(self):
        self.corriendo = True

    def isRunning(self):
        return self.corriendo


def _herramientas(monkeypatch):
    urls, lanzadas = [], []
    monkeypatch.setattr(T.webbrowser, "open", lambda u, *a, **k: urls.append(u) or True)
    tm = ToolManager()
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, f"Abrí {n}"))
    monkeypatch.setattr(tm, "_cmd_sistema_info", lambda *a: ToolResult(True, "CPU 5% | RAM 40%"))
    return tm, urls, lanzadas


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


# ── Piel web (ui/web_bridge.py) ────────────────────────────────────────────────

@pytest.fixture
def puente(qapp, tmp_path, monkeypatch, datos_tmp):
    import ui.web_bridge as wb
    from nucleo.config import Config
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    tm, urls, lanzadas = _herramientas(monkeypatch)
    memoria = MagicMock()
    memoria.procesar_mensaje_usuario.return_value = None
    memoria.obtener_contexto_para_prompt.return_value = ""
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("telegram", "ordenes_pc", True)
    timers = []
    b = wb.LuneBridge(config=cfg, ai_manager=AIFalso(), memoria=memoria, tools=tm, voice=VozFalsa(),
                      opciones_acciones={"audit_path": None,
                                         "programar": lambda s, fn: timers.append(fn) or MagicMock()})
    senales = {n: [] for n in ("done", "herramienta", "aprobacion_pedida", "aprobacion_resuelta",
                               "usuario_mascota", "aviso")}
    for n, lista in senales.items():
        getattr(b, n).connect(lambda *a, l=lista: l.append(a if len(a) != 1 else a[0]))
    b._ventana_a_la_vista = lambda: True                        # la página está delante
    b._tg_worker = TgFalso()
    b.urls, b.lanzadas, b.senales, b.timers = urls, lanzadas, senales, timers
    yield b
    b.cerrar_escritorio()
    b.deleteLater()


def _pedida(b, i=-1):
    return json.loads(b.senales["aprobacion_pedida"][i])


def test_web_desactivada_contesta_y_no_hace_nada(puente, monkeypatch):
    b = puente
    b.config.set("telegram", "ordenes_pc", False)
    b._orden_remota("o1", "abre youtube")
    assert b._tg_worker.enviados == [("o1", tw.AVISO_TG_DESACTIVADAS)]
    # Encendida pero sin tu ID de Telegram: igual de desactivada.
    b.config.set("telegram", "ordenes_pc", True)
    from nucleo import datos
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "")
    b._orden_remota("o2", "abre youtube")
    assert b._tg_worker.enviados[-1] == ("o2", tw.AVISO_TG_DESACTIVADAS)
    assert b.urls == [] and b.senales["usuario_mascota"] == [] and WorkerFalso.creados == []
    assert b.senales["aprobacion_pedida"] == []


def test_web_ocupada(puente):
    b = puente
    b._worker = WorkerFalso(None, "otra cosa", "ollama")
    b._worker.start()
    b._orden_remota("o1", "abre youtube")
    assert b._tg_worker.enviados == [("o1", tw.AVISO_TG_OCUPADA)]
    assert b.senales["usuario_mascota"] == [] and b.senales["aprobacion_pedida"] == []


def test_web_comando_directo_sin_ia_se_aprueba_en_el_pc_y_vuelve_a_telegram(puente):
    b = puente
    b._orden_remota("o1", "abre youtube")
    assert b.senales["usuario_mascota"] == ["📱 Telegram: abre youtube"]   # burbuja en el chat
    assert WorkerFalso.creados == []                                      # sin IA
    assert b.urls == [] and len(b.senales["aprobacion_pedida"]) == 1      # aún no: se pregunta
    p = _pedida(b)
    assert p["herramienta"] == "abrir_url" and p["origen"] == "remoto" and p["remoto"] is True
    assert "Telegram" in p["motivo"]
    # Mientras espera tu respuesta, otra orden encuentra a Lune ocupada.
    b._orden_remota("o2", "abre github")
    assert b._tg_worker.enviados == [("o2", tw.AVISO_TG_OCUPADA)]
    assert b.resolver_aprobacion(p["id"], True) is True
    assert b.urls == ["https://www.youtube.com"]
    ok, _icono, _titulo, detalle = b.senales["herramienta"][-1]            # ✓ en el chat
    assert ok is True and "Youtube" in detalle
    assert b._tg_worker.textos("o1") == [f"✓ {detalle}"]                   # y en Telegram


def test_web_lectura_directa_tambien_pide_permiso_y_el_no_vuelve(puente):
    b = puente
    b._orden_remota("o1", "estado del pc")
    p = _pedida(b)
    assert p["herramienta"] == "sistema_info" and p["remoto"] is True
    assert b.resolver_aprobacion(p["id"], False) is True
    [texto] = b._tg_worker.textos("o1")
    assert texto.startswith("✕ No lo hice") and "rechazada por el usuario" in texto


def test_web_caducada_avisa_en_telegram(puente):
    b = puente
    b._orden_remota("o1", "abre youtube")
    pid = _pedida(b)["id"]
    b.timers[-1]()                                          # pasan los 60 s sin respuesta
    assert b.urls == []
    [texto] = b._tg_worker.textos("o1")
    assert texto.startswith("✕ Nadie respondió") and "abrir_url" in texto
    assert pid in b.senales["aprobacion_resuelta"]          # la página cierra el modal


def test_web_turno_de_ia_con_origen_remoto(puente):
    b = puente
    b._orden_remota("o2", "¿me abres youtube y me dices algo?")
    w = WorkerFalso.creados[-1]
    assert w.message == "[Desde Telegram] ¿me abres youtube y me dices algo?"
    assert w.kw["origen"] == "remoto" and w.kw["ctx"]["origen"] == "remoto"
    assert w.kw["ejecutor"] is b.acciones.ejecutor and b._turno["remoto"] == "o2"
    assert b.senales["usuario_mascota"] == ["📱 Telegram: ¿me abres youtube y me dices algo?"]
    w.response_ready.emit('Claro, te lo abro. <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>')
    # La respuesta limpia y, como la acción espera tu permiso, dicho (prueba real:
    # llegaba «te lo abro» antes de que nadie lo aprobara en el PC).
    assert b._tg_worker.textos("o2") == ["Claro, te lo abro.\n\n(pendiente de tu permiso en el PC)"]
    assert b.urls == [] and _pedida(b)["remoto"] is True
    b.resolver_aprobacion(_pedida(b)["id"], True)
    assert b.urls == ["https://www.youtube.com"]
    assert b._tg_worker.textos("o2")[-1].startswith("✓ ")


def test_web_remota_sin_acciones_no_dice_pendiente(puente):
    b = puente
    b._orden_remota("o5", "cuéntame algo")
    WorkerFalso.creados[-1].response_ready.emit('<|ACT {"emotion":"happy"}|>Había una vez…')
    assert b._tg_worker.textos("o5") == ["Había una vez…"]


def test_web_remota_con_marca_no_entendida_avisa_y_no_dice_pendiente(puente):
    """Una marca inventada (<|CHANGE_VOCES …|>) no se pide ni se da por hecha: a
    Telegram llega la respuesta limpia y después «✕ No entendí la acción…»."""
    b = puente
    b._orden_remota("o6", "cámbiate la voz")
    WorkerFalso.creados[-1].response_ready.emit('¡Listo! <|CHANGE_VOCES {"voice": "x"}|>')
    textos = b._tg_worker.textos("o6")
    assert textos[0] == "¡Listo!"
    assert any(t.startswith("✕ No entendí la acción «CHANGE_VOCES»") for t in textos[1:])
    assert b.senales["aprobacion_pedida"] == []


def test_web_error_de_la_ia_vuelve_legible(puente):
    b = puente
    b._orden_remota("o3", "cuéntame un chiste")
    WorkerFalso.creados[-1].error_occurred.emit("No pude conectar con Ollama en http://localhost:11434")
    assert b._tg_worker.textos("o3") == ["✕ No pude responder: No pude conectar con Ollama en "
                                         "http://localhost:11434"]


def test_web_detener_avisa_y_lo_que_llegue_despues_no_se_manda(puente):
    b = puente
    b._orden_remota("o4", "cuéntame un chiste")
    w = WorkerFalso.creados[-1]
    b.detener()
    assert b._tg_worker.textos("o4") == [tw.AVISO_TG_DETENIDA]
    w.response_ready.emit("Había una vez…")
    assert b._tg_worker.textos("o4") == [tw.AVISO_TG_DETENIDA]


def test_web_orden_remota_no_es_un_slot_de_la_pagina(qapp):
    from PyQt6.QtCore import QMetaMethod
    from ui.web_bridge import LuneBridge
    mo = LuneBridge.staticMetaObject
    nombres = {bytes(mo.method(i).name()).decode() for i in range(mo.methodCount())
               if mo.method(i).methodType() == QMetaMethod.MethodType.Slot}
    assert "_orden_remota" not in nombres and "_responder_telegram" not in nombres
    assert "enviar" in nombres                                           # los de la página, sí


class BotFalso(QObject):
    log_signal = pyqtSignal(str)
    stopped = pyqtSignal()
    orden_recibida = pyqtSignal(str, str)
    BOT_DIR = RAIZ
    creados = []

    def __init__(self, ordenes=False):
        super().__init__()
        self.ordenes, self.enviados = ordenes, []
        BotFalso.creados.append(self)

    def start(self):
        pass

    def isRunning(self):
        return True

    def responder_orden(self, oid, texto):
        self.enviados.append((oid, texto))
        return True


def test_web_telegram_toggle_abre_el_canal_y_conecta_la_orden(puente, monkeypatch, qapp):
    b = puente
    b._tg_worker = None
    BotFalso.creados = []
    monkeypatch.setattr(tw, "TelegramBotWorker", BotFalso)
    assert json.loads(b.telegram_toggle())["running"] is True
    bot = BotFalso.creados[-1]
    assert bot.ordenes is True and b._tg_worker is bot
    bot.orden_recibida.emit("o5", "abre youtube")
    assert b.senales["aprobacion_pedida"] == []                        # en cola: aún no
    qapp.processEvents()
    assert _pedida(b)["remoto"] is True
    b._tg_worker = None
    b.config.set("telegram", "ordenes_pc", False)
    b.telegram_toggle()
    assert BotFalso.creados[-1].ordenes is False                        # apagada: sin canal


def test_web_ajustes_interruptor_y_tu_id(puente):
    from nucleo import datos
    b = puente
    cfg = json.loads(b.get_config())
    assert cfg["telegram_ordenes_pc"] is True and cfg["telegram_admin_id"] == "777"
    b.guardar_config(json.dumps({"telegram_ordenes_pc": False, "telegram_admin_id": " 123456 "}))
    assert b.config.get("telegram", "ordenes_pc") is False
    assert datos.telegram_admin_id() == "123456"
    assert "Reinicia el bot de Telegram para aplicar el cambio." in b.senales["aviso"]
    b.guardar_config(json.dumps({"telegram_admin_id": "@diego"}))       # no es un ID
    assert datos.telegram_admin_id() == "123456"
    assert any("solo números" in a for a in b.senales["aviso"])
    assert datos.telegram_token() == "123:TG-FALSO"                     # lo demás, intacto


# ── Ventana nativa (main.py) ───────────────────────────────────────────────────

class ConfigFalsa:
    def __init__(self, valores=None, **features):
        self.valores = dict(valores or {})
        self.features = features

    def feature(self, clave, defecto=True):
        return self.features.get(clave, defecto)

    def get(self, seccion, clave, defecto=None):
        return self.valores.get((seccion, clave), defecto)


def _enlazar(yo, *nombres):
    import main
    for n in nombres:
        f = main.LuneCDWindow.__dict__[n]
        setattr(yo, n, f.__func__ if isinstance(f, staticmethod) else types.MethodType(f, yo))
    return yo


@pytest.fixture
def nativa(qapp, monkeypatch):
    import main
    from nucleo import datos
    from ui.acciones_qt import AccionesQt
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "777")
    WorkerFalso.creados = []
    monkeypatch.setattr(main, "AIWorker", WorkerFalso)
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: MagicMock(name="burbuja"))
    monkeypatch.setattr(main, "TypingIndicator", lambda p: MagicMock(name="indicador"))
    tm, urls, lanzadas = _herramientas(monkeypatch)
    preguntas, timers = [], []
    acc = AccionesQt(tm, ventana_visible=lambda: True,
                     preguntar=lambda p, r: preguntas.append((p, r)),
                     audit_path=None, programar=lambda s, fn: timers.append(fn) or MagicMock())
    yo = MagicMock()
    yo.config = ConfigFalsa({("telegram", "ordenes_pc"): True}, respuestas_predeterminadas=False)
    yo.ai_manager = MagicMock(name="ai_manager")
    yo.ai_manager.providers = {"ollama": types.SimpleNamespace(cancel_flag=True)}
    yo._motor_chat = None
    yo.acciones, yo.tools = acc, tm
    yo._typing_indicator, yo._current_bubble, yo._voz_stream = None, None, None
    yo._cancelado, yo._overlay, yo.ai_worker = False, None, None
    yo._turno, yo._gen, yo._esperando_corte = {}, 0, False
    yo.current_provider, yo._modo_red = "ollama", "local"
    yo._chat_remoto = None
    yo._modo_acciones = lambda: "normal"
    yo.notas.activo = False
    yo.memoria.obtener_contexto_para_prompt.return_value = ""
    yo._tg_worker = TgFalso()
    yo._resultado_turno = types.SimpleNamespace(emit=lambda r, i: yo._on_resultado_turno(r, i))
    _enlazar(yo, "_orden_remota", "_send_message", "_remota_en_curso", "_responder_telegram",
             "_texto_telegram", "_ejecutar_acciones", "_on_resultado_turno", "_on_resultado_accion",
             "_on_response", "_on_error", "_acciones_locales", "_eco_mascota", "_burbuja_mascota",
             "_worker_vivo", "_cancelar_worker", "_stop_generation")
    yield {"yo": yo, "acc": acc, "preguntas": preguntas, "timers": timers, "urls": urls,
           "lanzadas": lanzadas, "tg": yo._tg_worker}
    acc.cerrar()


def _guardados(yo):
    return [(c.args, c.kwargs) for c in yo._guardar_turno.call_args_list]


def test_nativa_desactivada_y_ocupada(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo.config.valores[("telegram", "ordenes_pc")] = False
    yo._orden_remota("o1", "abre youtube")
    assert tg.enviados == [("o1", tw.AVISO_TG_DESACTIVADAS)]
    yo.config.valores[("telegram", "ordenes_pc")] = True
    yo.ai_worker = WorkerFalso(None, "otra", "ollama")
    yo.ai_worker.start()
    yo._orden_remota("o2", "abre youtube")
    assert tg.enviados[-1] == ("o2", tw.AVISO_TG_OCUPADA)
    assert nativa["preguntas"] == [] and not yo._guardar_turno.called


def test_nativa_comando_directo_sin_ia(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo._orden_remota("o1", "abre youtube")
    assert WorkerFalso.creados == [] and nativa["urls"] == []
    assert _guardados(yo)[0] == (("user", "📱 Telegram: abre youtube"),
                                 {"adjuntos": [], "no_confiable": True})
    [(pendiente, responder)] = nativa["preguntas"]
    assert pendiente["remoto"] is True and pendiente["herramienta"] == "abrir_url"
    yo._orden_remota("o2", "estado del pc")                  # espera tu respuesta: ocupada
    assert tg.enviados == [("o2", tw.AVISO_TG_OCUPADA)]
    responder(True)
    assert nativa["urls"] == ["https://www.youtube.com"]
    [texto] = tg.textos("o1")
    assert texto.startswith("✓ ") and "Youtube" in texto
    assert _guardados(yo)[-1] == (("assistant", texto), {"no_confiable": True})
    yo._burbuja_bot.assert_called_with(texto)                # y en el chat


def test_nativa_caducada(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo._orden_remota("o1", "abre youtube")
    nativa["timers"][-1]()
    assert nativa["urls"] == []
    assert tg.textos("o1")[0].startswith("✕ Nadie respondió")


def test_nativa_turno_de_ia_remoto_usa_el_motor_local(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo._modo_red = "terminal"                                 # aunque haya host conectado
    yo._chat_remoto = types.SimpleNamespace(conectado=True)
    yo._orden_remota("o2", "¿cómo va el PC?")
    w = WorkerFalso.creados[-1]
    assert w.motor is yo.ai_manager and w.message == "[Desde Telegram] ¿cómo va el PC?"
    assert w.kw["origen"] == "remoto" and w.kw["ctx"]["origen"] == "remoto"
    assert yo._turno["remoto"] == "o2" and yo._turno["origen"] == "remoto"
    yo._on_response('Te miro. <|ACT {"emotion": "happy"}|> <|CALL ["sistema_info", {}]|>', yo._gen)
    assert tg.textos("o2") == ["Te miro.\n\n" + tw.AVISO_TG_PENDIENTE]   # como en la web
    assert _guardados(yo)[-1][1]["no_confiable"] is True
    [(pendiente, responder)] = nativa["preguntas"]           # también la LECTURA pregunta
    assert pendiente["herramienta"] == "sistema_info" and pendiente["remoto"] is True
    responder(True)
    assert tg.textos("o2")[-1] == "✓ CPU 5% | RAM 40%"


def test_nativa_remota_sin_acciones_no_dice_pendiente(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo._orden_remota("o5", "¿qué tal?")
    yo._on_response('Muy bien. <|ACT {"emotion": "happy"}|>', yo._gen)
    assert tg.textos("o5") == ["Muy bien."] and not nativa["preguntas"]


def test_nativa_error_y_detener(nativa):
    yo, tg = nativa["yo"], nativa["tg"]
    yo._orden_remota("o3", "cuéntame algo")
    yo._on_error("Ollama no responde", yo._gen)
    assert tg.textos("o3") == ["✕ No pude responder: Ollama no responde"]
    yo.ai_worker = None
    yo._orden_remota("o4", "cuéntame otra")
    yo._stop_generation()
    assert tg.textos("o4") == [tw.AVISO_TG_DETENIDA]
    yo._on_response("Había una vez…", yo._gen)               # la parcial ya no va a Telegram
    assert tg.textos("o4") == [tw.AVISO_TG_DETENIDA]


def test_nativa_toggle_abre_el_canal_segun_la_config(qapp, monkeypatch):
    import main
    from nucleo import datos
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "777")
    monkeypatch.setattr(datos, "telegram_token", lambda: "123:TG-FALSO")
    BotFalso.creados = []
    monkeypatch.setattr(main, "TelegramBotWorker", BotFalso)
    yo = MagicMock()
    yo._tg_worker = None
    yo.config = ConfigFalsa({("telegram", "ordenes_pc"): True})
    _enlazar(yo, "_toggle_telegram")
    yo._toggle_telegram()
    assert BotFalso.creados[-1].ordenes is True
    yo._tg_worker = None
    yo.config.valores[("telegram", "ordenes_pc")] = False
    yo._toggle_telegram()
    assert BotFalso.creados[-1].ordenes is False


def test_panel_nativo_guarda_el_interruptor(qapp, tmp_path, monkeypatch, datos_tmp):
    from nucleo.config import Config
    from servicios import autoinicio, voces
    from ui import settings_panel as SP
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(autoinicio, "establecer", lambda on: None)
    monkeypatch.setattr(voces, "_voz_personaje", lambda p: SP.voz_de(p))
    cfg = Config(str(tmp_path / "config.json"))
    panel = SP.SettingsPanel(cfg, voice=None)
    assert panel.ordenes_tg_check.isChecked() is False
    panel.ordenes_tg_check.setChecked(True)
    panel._save()
    assert Config(str(tmp_path / "config.json")).get("telegram", "ordenes_pc") is True
    from nucleo import datos
    assert datos.telegram_admin_id() == "777"               # solo se guardó lo que cambió
    panel.deleteLater()
