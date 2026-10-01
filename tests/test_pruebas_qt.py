"""
Los «Probar» de Ajustes y «Comprobar que todo funciona» con Qt (offscreen), 11.3:

- El puente de la piel web (ui/web_bridge.LuneBridge): ranuras y señales con la firma que usa
  extra/diagnostico.jsx (QMetaMethod), openrouter_probar / telegram_probar con lo ESCRITO (la
  máscara = lo guardado) y sin devolver nunca la clave ni el token, ollama_probar con los modelos,
  diagnostico_iniciar item a item por la señal (una sola a la vez, se para al cerrar),
  dictado_probar y el micrófono ocupado.
- ui/audio_prueba.ProbadorDictado (grabar y transcribir, con voz_entrada falso) y ui/pruebas_qt
  (PruebaWorker, DiagnosticoWorker y el diálogo de la nativa).
- La nativa (ui/settings_panel.py): PROBAR CLAVE, PROBAR BOT, PROBAR SALIDA, PROBAR DICTADO y
  COMPROBAR QUE TODO FUNCIONA.
- Discord «Reconectar»: Presencia.reconectar, ControlDiscord.reconectar, PuenteVida.discord_reconectar,
  el botón de PanelVidaNativo y los motivos (Discord cerrado, sin ID, otra Lune ya publica).
Sin red: HTTP, Node, Whisper, el micrófono y Discord son falsos.
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("PyQt6.QtWidgets")
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de crear la QApplication)
except ImportError:
    pass

from PyQt6.QtCore import QMetaMethod, QObject, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from test_web_bridge_voz_borrado import crear_puente  # noqa: E402,F401  (fixture)
from test_settings_voz_compat import panel  # noqa: E402,F401  (fixture)
from discord_falso import ID, ConfigFalsa, FabricaClientes, MutexFalso, Reloj  # noqa: E402

JSX = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
CLAVE = "sk-or-v1-claveSecretaDePrueba0123456789"
TOKEN = "123456789:AAH-tokenSecretoDePrueba_0123456"


def esperar(cond, ms=4000):
    fin = time.monotonic() + ms / 1000
    while time.monotonic() < fin:
        if cond():
            return True
        QTest.qWait(10)
    return cond()


def _qt_de(obj):
    """{nombre: (tipos de los parámetros, tipo devuelto)} de ranuras y señales (lo que ve QWebChannel)."""
    mo = obj.metaObject()
    ranuras, senales = {}, {}
    for i in range(mo.methodCount()):
        m = mo.method(i)
        nombre = bytes(m.name()).decode()
        firma = ([bytes(t).decode() for t in m.parameterTypes()], m.typeName())
        if m.methodType() == QMetaMethod.MethodType.Slot:
            ranuras[nombre] = firma
        elif m.methodType() == QMetaMethod.MethodType.Signal:
            senales[nombre] = firma
    return ranuras, senales


class Resp:
    def __init__(self, codigo=200, datos=None):
        self.status_code, self._datos = codigo, datos

    def json(self):
        return self._datos


def _http(rutas, pedidas):
    def get(url, headers=None, timeout=None):
        pedidas.append((url, dict(headers or {})))
        for trozo, r in rutas.items():
            if trozo in url:
                return r(url) if callable(r) else r
        raise AssertionError(url)
    return get


def _guardar_apis(**apis):
    from nucleo import datos
    d = datos.cargar()
    d.setdefault("apis", {}).update(apis)
    datos.guardar(d)


# ── El puente de la web ──────────────────────────────────────────────────────

def test_contrato_del_puente_con_diagnostico_jsx(crear_puente):
    b, _ = crear_puente()
    ranuras, senales = _qt_de(b)
    assert ranuras["openrouter_probar"] == (["QString"], "QString")
    assert ranuras["ollama_probar"] == (["QString"], "QString")
    assert ranuras["telegram_probar"] == (["QString"], "QString")
    assert ranuras["diagnostico_iniciar"] == ([], "bool")
    assert ranuras["diagnostico_parar"] == ([], "bool")
    assert ranuras["dictado_probar"] == (["QString"], "bool")
    assert ranuras["probar_microfono"] == (["QString"], "bool")
    assert ranuras["probar_salida"] == (["QString"], "bool")
    assert senales["diagnostico"][0] == ["QString"] and senales["dictado_prueba"][0] == ["QString"]
    texto = (JSX / "extra" / "diagnostico.jsx").read_text(encoding="utf-8")
    pedidas = set(re.findall(r"\bllamar\('([a-z_]+)'", texto)) | set(re.findall(r"\busePrueba\('([a-z_]+)'", texto))
    escuchadas = set(re.findall(r"\bconectar\('([a-z_]+)'", texto))
    assert {"diagnostico_iniciar", "openrouter_probar", "ollama_probar", "telegram_probar", "dictado_probar"} <= pedidas
    assert pedidas <= set(ranuras), pedidas - set(ranuras)
    assert escuchadas == {"diagnostico", "dictado_prueba"} and escuchadas <= set(senales)
    # index.html la carga (antes de app.jsx) y settings.jsx la pinta.
    html = (JSX / "index.html").read_text(encoding="utf-8")
    assert html.index('src="extra/diagnostico.jsx"') < html.index('src="app.jsx"')
    ajustes = (JSX / "settings.jsx").read_text(encoding="utf-8")
    for c in ("DiagnosticoCard", "ProbarOpenRouter", "ProbarOllama", "ProbarTelegram", "ProbarDictado"):
        assert f"window.{c} && <window.{c}" in ajustes, c
    b.cerrar_escritorio()


def test_openrouter_probar_con_lo_escrito_y_la_mascara(crear_puente, monkeypatch):
    from servicios import pruebas
    _guardar_apis(openrouter_key=CLAVE)
    pedidas = []
    codigo = {"v": 200}
    monkeypatch.setattr(pruebas, "_http_real", lambda: _http(
        {"/api/v1/key": lambda u: Resp(codigo["v"], {"data": {"label": CLAVE[:14]}})}, pedidas))
    b, _ = crear_puente()
    r = json.loads(b.openrouter_probar(json.dumps({"openrouter_key": "••••••••", "openrouter_model": "openrouter/auto"})))
    assert r["ok"] is True and pedidas[-1][1]["Authorization"] == f"Bearer {CLAVE}"       # la guardada
    r = json.loads(b.openrouter_probar(json.dumps({"openrouter_key": "sk-escrita-12345", "openrouter_model": ""})))
    assert pedidas[-1][1]["Authorization"] == "Bearer sk-escrita-12345"                  # la escrita
    codigo["v"] = 401
    r = json.loads(b.openrouter_probar(json.dumps({"openrouter_key": "••••••••"})))
    assert r["ok"] is False and "no reconoce" in r["mensaje"]
    assert json.loads(b.openrouter_probar(json.dumps({"openrouter_key": ""})))["ok"] is None   # borrada: sin clave
    for p in (b.openrouter_probar("{}"), b.openrouter_probar("basura")):
        assert CLAVE not in p and CLAVE[:14] not in p
    b.cerrar_escritorio()


def test_ollama_probar_da_los_modelos(crear_puente, monkeypatch):
    from servicios import ollama_client
    urls = []
    monkeypatch.setattr(ollama_client, "listar_modelos", lambda u, timeout=6: urls.append(u) or (True, ["b", "a"], "ok"))
    b, _ = crear_puente()
    r = json.loads(b.ollama_probar("http://192.168.1.50:11434"))
    assert r["ok"] is True and r["modelos"] == ["b", "a"] and urls == ["http://192.168.1.50:11434"]
    assert json.loads(b.ollama_probar(""))["ok"] is True and urls[-1] == "http://localhost:11434"   # la guardada
    r = json.loads(b.ollama_probar("http://usuario:clave@host"))
    assert r["ok"] is False and len(urls) == 2
    b.cerrar_escritorio()


def test_telegram_probar_sin_devolver_el_token(crear_puente, monkeypatch):
    from servicios import actualizador, pruebas
    from servicios.telegram_worker import TelegramBotWorker
    _guardar_apis(telegram_token=TOKEN, telegram_admin_id="42")
    pedidas = []
    monkeypatch.setattr(pruebas, "_http_real", lambda: _http(
        {"/getMe": lambda u: Resp(200, {"ok": True, "result": {"username": "LuneBot"}}) if TOKEN in u
         else Resp(401, {"ok": False})}, pedidas))
    monkeypatch.setattr(actualizador, "estado_node", lambda: {"ok": True, "version": "v20.1.0", "mensaje": ""})
    monkeypatch.setattr(TelegramBotWorker, "preparar_carpeta", classmethod(lambda cls: True))
    b, _ = crear_puente()
    crudo = b.telegram_probar(json.dumps({"telegram_token": "••••••••", "telegram_admin_id": "42"}))
    r = json.loads(crudo)
    assert r["ok"] is True and r["bot"] == "LuneBot" and TOKEN not in crudo
    assert [i["ok"] for i in r["items"]] == [True, True, True, True]
    crudo = b.telegram_probar(json.dumps({"telegram_token": "999999:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}))
    assert json.loads(crudo)["ok"] is False and "no reconoce" in json.loads(crudo)["mensaje"]
    assert "AAAAAAAAAAAAAAAAAAAA" not in crudo
    n = len(pedidas)
    assert json.loads(b.telegram_probar(json.dumps({"telegram_token": "hola"})))["ok"] is False
    assert len(pedidas) == n                                         # con mala forma no se manda
    b.cerrar_escritorio()


def _falso_comprobar(items=(("internet", True), ("openrouter", None))):
    def comprobar(red, ctx=None, al_avanzar=None, parar=None):
        hechos = []
        for id_, ok in items:
            it = {"id": id_, "seccion": "red", "nombre": id_, "ok": ok, "detalle": f"detalle de {id_}"}
            hechos.append(it)
            if al_avanzar:
                al_avanzar(it)
        return {"ok": all(i["ok"] is not False for i in hechos), "version": "11.3", "modo": "codigo", "items": hechos}
    return comprobar


def _lento(llamadas):
    def comprobar(red, ctx=None, al_avanzar=None, parar=None):
        llamadas.append(red)
        while not parar():
            time.sleep(0.01)
        return {"ok": True, "version": "11.3", "modo": "codigo", "items": [], "parado": True}
    return comprobar


def test_diagnostico_iniciar_item_a_item(crear_puente, monkeypatch):
    from servicios import diagnostico as D
    monkeypatch.setattr(D, "comprobar", _falso_comprobar())
    monkeypatch.setattr(D, "contexto_en_app", lambda: None)
    b, _ = crear_puente()
    vistos = []
    b.diagnostico.connect(vistos.append)
    assert b.diagnostico_iniciar() is True
    assert esperar(lambda: any(json.loads(v)["tipo"] == "fin" for v in vistos))
    ev = [json.loads(v) for v in vistos]
    assert [e["tipo"] for e in ev] == ["inicio", "item", "item", "fin"]
    assert ev[0]["secciones"][-1]["id"] == "red"
    assert ev[1]["id"] == "internet" and ev[1]["ok"] is True and ev[2]["ok"] is None
    assert ev[3]["ok"] is True and "Todo en orden" in ev[3]["resumen"]
    b.cerrar_escritorio()


def test_diagnostico_una_vez_parar_y_cerrar(crear_puente, monkeypatch):
    from servicios import diagnostico as D
    llamadas = []
    monkeypatch.setattr(D, "comprobar", _lento(llamadas))
    monkeypatch.setattr(D, "contexto_en_app", lambda: None)
    b, _ = crear_puente()
    vistos = []
    b.diagnostico.connect(vistos.append)
    assert b.diagnostico_iniciar() is True
    assert b.diagnostico_iniciar() is False                         # ya hay una
    assert esperar(lambda: llamadas == [True])
    assert b.diagnostico_parar() is True
    assert esperar(lambda: any(json.loads(v).get("parado") for v in vistos))
    assert b.diagnostico_parar() is False
    # Otra en marcha y se cierra la ventana: se para y nadie la espera colgado.
    assert b.diagnostico_iniciar() is True
    w = b._diag_worker
    assert esperar(lambda: len(llamadas) == 2)
    b.cerrar_escritorio()
    assert b._diag_worker is None
    assert esperar(lambda: not w.isRunning())


def test_dictado_probar_con_el_micro_ocupado_o_sin_whisper(crear_puente, monkeypatch):
    from servicios import voz_entrada
    b, _ = crear_puente()
    vistos = []
    b.dictado_prueba.connect(vistos.append)
    b._grabadora = object()
    assert b.dictado_probar("{}") is False
    assert json.loads(vistos[-1])["fase"] == "error" and "en uso" in json.loads(vistos[-1])["mensaje"]
    b._grabadora = None
    monkeypatch.setattr(voz_entrada, "dependencias_faltantes", lambda: ["faster-whisper"])
    assert b.dictado_probar("{}") is False and "faster-whisper" in json.loads(vistos[-1])["mensaje"]
    monkeypatch.setattr(voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(voz_entrada, "resolver_entrada", lambda n: None)
    assert b.dictado_probar(json.dumps({"dispositivo_entrada": "Headset X"})) is False
    assert "Headset X" in json.loads(vistos[-1])["mensaje"]
    b.cerrar_escritorio()


def test_mientras_prueba_el_dictado_el_micro_espera(crear_puente, monkeypatch):
    from servicios import voz_entrada
    b, _ = crear_puente()
    avisos = []
    b.aviso.connect(avisos.append)
    b._dictado_prueba = SimpleNamespace(isRunning=lambda: True)
    assert b.probar_microfono("") is False and "Probar dictado" in avisos[-1]
    monkeypatch.setattr(voz_entrada, "disponible", lambda: True)
    assert json.loads(b.dictar())["error"] == "probando"
    b._dictado_prueba = None
    b.cerrar_escritorio()


# ── ProbadorDictado ──────────────────────────────────────────────────────────

class GrabadoraFalsa:
    ruta = None

    def __init__(self, dispositivo=None):
        self.dispositivo = dispositivo

    def iniciar(self):
        pass

    def detener(self):
        return GrabadoraFalsa.ruta


def _probar_dictado(qapp, monkeypatch, tmp_path, *, transcribir, descargado=False, ruta=True):
    from servicios import voz_entrada
    from ui.audio_prueba import ProbadorDictado
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF")
    GrabadoraFalsa.ruta = wav if ruta else None
    monkeypatch.setattr(voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(voz_entrada, "Grabadora", GrabadoraFalsa)
    monkeypatch.setattr(voz_entrada, "modelo_descargado", lambda m: descargado)
    monkeypatch.setattr(voz_entrada, "transcribir", transcribir)
    p = ProbadorDictado(None, "base", "es", segundos=0.01)
    vistos = []
    p.progreso.connect(vistos.append)
    p.start()
    assert esperar(lambda: p.isFinished())
    QTest.qWait(20)
    return [json.loads(v) for v in vistos]


def test_probar_dictado_la_primera_vez_avisa_de_la_descarga(qapp, monkeypatch, tmp_path):
    ev = _probar_dictado(qapp, monkeypatch, tmp_path, transcribir=lambda r, m, i: "hola lune")
    assert [e["fase"] for e in ev] == ["grabando", "descargando", "listo"]
    assert "145 MB" in ev[0]["mensaje"] and "primera vez" in ev[0]["mensaje"]
    assert ev[-1]["ok"] is True and ev[-1]["texto"] == "hola lune" and "funciona" in ev[-1]["mensaje"]


def test_probar_dictado_errores(qapp, monkeypatch, tmp_path):
    def falla(r, m, i):
        raise RuntimeError("No pude descargar el modelo Whisper «base» (necesita internet la primera vez).")
    ev = _probar_dictado(qapp, monkeypatch, tmp_path, transcribir=falla, descargado=True)
    assert [e["fase"] for e in ev] == ["grabando", "transcribiendo", "error"] and "internet" in ev[-1]["mensaje"]
    ev = _probar_dictado(qapp, monkeypatch, tmp_path, transcribir=lambda r, m, i: "x", ruta=False)
    assert ev[-1]["fase"] == "error" and "No grabé nada" in ev[-1]["mensaje"]
    ev = _probar_dictado(qapp, monkeypatch, tmp_path, transcribir=lambda r, m, i: "  ", descargado=True)
    assert ev[-1]["fase"] == "listo" and ev[-1]["ok"] is False


# ── ui/pruebas_qt ────────────────────────────────────────────────────────────

def test_prueba_worker(qapp):
    from ui.pruebas_qt import PruebaWorker
    res = []
    w = PruebaWorker(lambda: {"ok": True, "mensaje": "bien"})
    w.listo.connect(res.append)
    w.start()
    assert esperar(lambda: res)

    def lanza():
        raise ValueError(CLAVE)
    w2 = PruebaWorker(lanza)
    w2.listo.connect(res.append)
    w2.start()
    assert esperar(lambda: len(res) == 2)
    assert res[0]["ok"] is True and res[1]["ok"] is False and CLAVE not in res[1]["mensaje"]


def test_dialogo_diagnostico_pinta_item_a_item(qapp):
    from ui.pruebas_qt import DiagnosticoWorker, DialogoDiagnostico
    fabrica = lambda red, parent: DiagnosticoWorker(red, parent, comprobar=_falso_comprobar(  # noqa: E731
        (("piel_web", True), ("openrouter", False), ("ollama", None))), contexto=lambda: None)
    d = DialogoDiagnostico(None, worker=fabrica)
    assert d.iniciar() is True
    assert esperar(lambda: d.fin is not None)
    assert [i["id"] for i in d.items] == ["piel_web", "openrouter", "ollama"]
    assert "Me falla 1" in d.lbl_estado.text() and d.btn_otra.isEnabled()
    textos = [d.lista.itemAt(i).widget().text() for i in range(d.lista.count() - 1)]
    assert any("MAL" in t and "openrouter" in t for t in textos) and any("NO APLICA" in t for t in textos)
    assert d.iniciar() is True                                          # «Comprobar otra vez»
    assert esperar(lambda: d.fin is not None and len(d.items) == 3)
    d.close()


def test_dialogo_diagnostico_se_para_al_cerrar(qapp):
    from ui.pruebas_qt import DiagnosticoWorker, DialogoDiagnostico
    llamadas = []
    hilos = []

    def fabrica(red, parent):
        hilos.append(DiagnosticoWorker(red, parent, comprobar=_lento(llamadas), contexto=lambda: None))
        return hilos[-1]
    d = DialogoDiagnostico(None, worker=fabrica)
    d.iniciar()
    assert esperar(lambda: llamadas)
    assert d.iniciar() is False                                         # ya está comprobando
    d.close()
    assert esperar(lambda: not hilos[0].isRunning())


# ── La nativa ────────────────────────────────────────────────────────────────

def test_panel_nativo_tiene_los_probar(panel, monkeypatch):
    from servicios import pruebas
    p = panel["crear"]()
    for n in ("btn_probar_or", "btn_probar_tg", "btn_probar_salida", "btn_probar_dictado", "btn_diagnostico"):
        assert getattr(p, n).text().startswith(("PROBAR", "COMPROBAR")), n
    pedidas = []
    monkeypatch.setattr(pruebas, "probar_openrouter", lambda k, m: pedidas.append((k, m)) or
                        {"ok": False, "mensaje": "OpenRouter no reconoce esa clave."})
    p.fields["openrouter_api_key"].setText("sk-escrita")
    p.fields["openrouter_model"].setText("openrouter/auto")
    assert p._probar_openrouter() is True
    assert esperar(lambda: "no reconoce" in p.lbl_probar_or.text())
    assert pedidas == [("sk-escrita", "openrouter/auto")] and p.btn_probar_or.isEnabled()
    monkeypatch.setattr(pruebas, "probar_telegram", lambda t, a, carpeta=None: {
        "ok": False, "mensaje": "Falta Node.js 18 o más nuevo.",
        "items": [{"nombre": "Carpeta del bot", "ok": False, "detalle": "No encuentro la carpeta del bot."}]})
    assert p._probar_telegram() is True
    assert esperar(lambda: "Node.js" in p.lbl_probar_tg.text())
    assert "carpeta" in p.lbl_probar_tg.text()
    # La voz falsa del fixture no tiene motor: PROBAR SALIDA lo dice.
    assert p._probar_salida() is False and "motor de voz" in p.lbl_probar_salida.text()


def test_panel_nativo_abre_el_informe(panel, monkeypatch):
    from servicios import diagnostico as D
    monkeypatch.setattr(D, "comprobar", _falso_comprobar())
    monkeypatch.setattr(D, "contexto_en_app", lambda: None)
    p = panel["crear"]()
    d = p._abrir_diagnostico()
    assert esperar(lambda: d.fin is not None) and len(d.items) == 2
    assert p._abrir_diagnostico() is d                                 # uno solo a la vez
    d.close()


# ── Discord «Reconectar» ─────────────────────────────────────────────────────

def test_presencia_reconectar_no_espera_al_siguiente_intento():
    from servicios import discord_presencia as dp
    fab, reloj = FabricaClientes("sin_discord", "ok"), Reloj()
    p = dp.Presencia(ConfigFalsa(activo=True, client_id=ID), lambda: {"modo": "normal"}, cliente=fab,
                     mutex=MutexFalso(), reloj=reloj, hilo=False, pid=1, inicio_ms=0)
    p.habilitar(True)
    assert p.paso() == pytest.approx(dp.REINTENTOS_S[0])                # Discord cerrado: 15 s
    assert p.estado()["error"] == "Discord no está abierto."
    assert "app de escritorio de Discord" in dp.motivo(p.estado())
    reloj.t = 1.0
    p.paso()
    assert len(fab.clientes) == 1                                       # aún espera
    p.reconectar()
    p.paso()
    assert len(fab.clientes) == 2 and p.estado()["conectado"] is True


def test_motivos_de_discord():
    from servicios import discord_presencia as dp
    assert dp.motivo({"conectado": True}) == ""
    assert "apagada" in dp.motivo({"activo": False})
    assert "Application ID" in dp.motivo({"activo": True, "sin_id": True})
    assert "Otra Lune" in dp.motivo({"activo": True, "error": dp.TXT_OTRA_LUNE})
    assert "no acepta" in dp.motivo({"activo": True, "error": dp.TXT_RECHAZADO})
    assert "no responde" in dp.motivo({"activo": True, "error": "Discord no responde."})
    for m in (dp.motivo({"activo": True, "error": dp.TXT_OTRA_LUNE}), dp.motivo({"activo": True, "sin_id": True})):
        m.encode("cp1252")


class PresenciaFalsa:
    def __init__(self):
        self.estado_fn = self.on_estado = None
        self.reconexiones = 0
        self.e = {"activo": True, "conectado": False, "usuario": "", "error": "Discord no está abierto.",
                  "publicando": None, "sin_id": False}

    def habilitar(self, on):
        pass

    def actualizar(self):
        pass

    def reconectar(self):
        self.reconexiones += 1

    def estado(self):
        return dict(self.e)

    def cerrar(self, timeout=1.0):
        pass


def test_control_discord_reconectar(qapp):
    from ui.discord_qt import ControlDiscord
    from ui.escritorio import ServiciosEscritorio
    esc = ServiciosEscritorio(None)
    pres = PresenciaFalsa()
    c = ControlDiscord(esc, ConfigFalsa(activo=True, client_id=ID), presencia=pres)
    r = c.reconectar()
    assert r["ok"] is False and "app abierta" in r["motivo"] and pres.reconexiones == 0     # sin iniciar
    c.iniciar()
    assert "app de escritorio" in c.estado()["motivo"]
    r = c.reconectar()
    assert r["ok"] is True and pres.reconexiones == 1
    c.config.set("discord", "client_id", "")
    assert "Application ID" in c.reconectar()["motivo"]
    c.config.set("discord", "activo", False)
    assert "apagada" in c.reconectar()["motivo"] and pres.reconexiones == 1
    c.detener()
    esc.deleteLater()


class DiscordCtl(QObject):
    estado_cambio = pyqtSignal(str)

    def __init__(self, r):
        super().__init__()
        self.r = r
        self.llamadas = 0

    def estado(self):
        return {"activo": True, "conectado": False, "error": "Otra Lune ya publica en Discord.",
                "motivo": "Otra Lune ya publica en Discord (otra ventana o la terminal): ciérrala."}

    def reconectar(self):
        self.llamadas += 1
        return dict(self.r)

    def recargar_config(self):
        pass


def test_puente_vida_discord_reconectar(qapp):
    from ui.puente_vida import PuenteVida
    p = PuenteVida(None)
    r = json.loads(p.discord_reconectar())
    assert r["ok"] is False and "app abierta" in r["texto"]
    ctl = DiscordCtl({"ok": False, "texto": "", "motivo": "Falta el Application ID: crea una app."})
    p._discord = ctl
    visto = []
    p.discord_cambio.connect(visto.append)
    r = json.loads(p.discord_reconectar())
    assert r["ok"] is False and "Application ID" in r["texto"] and ctl.llamadas == 1 and visto
    assert "Otra Lune" in r["estado"]["motivo"]
    ctl.r = {"ok": True, "texto": "Lo intento ahora.", "motivo": ""}
    assert json.loads(p.discord_reconectar()) ["texto"] == "Lo intento ahora."
    p._discord = None
    p.cerrar()


def test_panel_vida_nativo_reconectar(qapp):
    from test_panel_vida_nativo import AutoinicioFalso, ConfigDisco
    from ui.panel_vida_nativo import PanelVidaNativo
    ctl = DiscordCtl({"ok": False, "texto": "", "motivo": "Discord no está abierto: abre la app."})
    cfg = ConfigDisco()
    cfg.config["discord"].update(activo=True, client_id=ID)
    pv = PanelVidaNativo(cfg, discord=ctl, autoinicio=AutoinicioFalso(), retardo_ms=30)
    assert "Otra Lune" in pv.estado_discord.text()                     # el motivo, no el error a secas
    pv.btn_reconectar.click()
    assert ctl.llamadas == 1 and "no está abierto" in pv.estado_discord.text()
    ctl.r = {"ok": True, "texto": "Lo intento ahora: en unos segundos sale «Conectado».", "motivo": ""}
    assert pv.reconectar_discord() is True and "Lo intento" in pv.estado_discord.text()
    sin = PanelVidaNativo(ConfigDisco(), autoinicio=AutoinicioFalso(), retardo_ms=30)
    assert sin.reconectar_discord() is False and "app abierta" in sin.estado_discord.text()
