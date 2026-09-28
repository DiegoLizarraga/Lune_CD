"""
Órdenes desde Telegram (/pc): el canal del bot y la política 'remoto'.

  · servicios/telegram_worker.py: las líneas «@@LUNE_ORDEN <token> <json>» con el
    token bueno se convierten en `orden_recibida(id, texto)` y NUNCA salen al log
    (con token malo tampoco); las demás líneas siguen al log sin el token;
    `responder_orden` deja JSON en la cola que un hilo escritor pasa al stdin del
    bot (thread-safe, sin bloquear ni romper si el proceso murió o no lee) y
    `stop()` cierra el stdin antes de terminar.
  · De punta a punta con Node (sin Telegram): el worker y telegram-bot-or/ordenes.js
    se entienden por stdin/stdout, con acentos y emoji, y el bot lanzado por Lune
    se cierra al cerrarse su stdin.
  · lune_core/acciones.py: con origen 'remoto' las herramientas del modo están
    disponibles, pero TODO pide aprobación en el PC (también la LECTURA y las
    `directa`); sin canal de aprobación se rechaza; caduca como las demás.
  · Taint: un turno remoto queda marcado en el historial.

Sin red, sin Telegram y sin tocar datos.json ni config.json reales.
"""
import asyncio
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtCore")

from lune_core import acciones as A  # noqa: E402
from lune_core import catalogo_herramientas as C  # noqa: E402
from lune_core import herramientas as H  # noqa: E402
from nucleo import datos  # noqa: E402
from servicios import telegram_worker as tw  # noqa: E402

MARCA = tw.MARCA_ORDEN
ADMIN = "5"


@pytest.fixture(autouse=True)
def _tu_id(monkeypatch):
    """Nada del datos.json real: tu ID de Telegram de mentira."""
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: ADMIN)


def _json(oid="ab12", texto="abre youtube", chat_id=int(ADMIN)):
    return json.dumps({"id": oid, "texto": texto, "chat_id": chat_id})


def _worker(ordenes=True):
    w = tw.TelegramBotWorker(ordenes=ordenes)
    logs, recibidas = [], []
    w.log_signal.connect(logs.append)
    w.orden_recibida.connect(lambda i, t: recibidas.append((i, t)))
    return w, logs, recibidas


# ── Parser de la salida del bot ─────────────────────────────────────────────────

def test_linea_con_token_bueno_es_una_orden_y_no_va_al_log(qapp):
    w, logs, rec = _worker()
    w.procesar_linea(f"{MARCA} {w._token} {_json(texto='  abre youtube  ')}\r\n")
    assert rec == [("ab12", "abre youtube")]
    assert logs == []


def test_token_malo_o_linea_rara_se_ignoran_y_tampoco_van_al_log(qapp):
    w, logs, rec = _worker()
    for linea in (f"{MARCA} {'0' * 32} {_json()}",                   # token de otro
                  f"{MARCA} {_json()}",                              # sin token
                  f"{MARCA} {w._token} {{no es json",
                  f"{MARCA} {w._token} {_json(oid='../../x')}",       # id raro
                  f"{MARCA} {w._token} {_json(texto='   ')}",         # orden vacía
                  f"{MARCA} {w._token} [1, 2]",
                  f"{MARCA} {w._token} {json.dumps({'id': 'a1', 'texto': 7})}",
                  f"basura antes {MARCA} {'1' * 32} {_json()}"):
        w.procesar_linea(linea)
    assert rec == [] and logs == []


def test_la_orden_tiene_que_venir_de_tu_chat(qapp, monkeypatch):
    w, logs, rec = _worker()
    w.procesar_linea(f"{MARCA} {w._token} {_json(chat_id=999)}")
    assert rec == [] and len(logs) == 1 and "no viene de tu chat" in logs[0]
    assert w._token not in logs[0]
    w.procesar_linea(f"{MARCA} {w._token} {_json(chat_id=ADMIN)}")   # como texto también vale
    assert rec == [("ab12", "abre youtube")]
    # Sin tu ID (no debería pasar: el bot lo exige) pasa y la app dirá «desactivadas».
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "")
    w.procesar_linea(f"{MARCA} {w._token} {_json(oid='cd34', chat_id=999)}")
    assert rec[-1] == ("cd34", "abre youtube")


def test_sin_canal_de_ordenes_ninguna_linea_marcada_cuenta(qapp):
    w, logs, rec = _worker(ordenes=False)
    assert w.ordenes is False and w._token == ""
    w.procesar_linea(f"{MARCA}  {_json()}")
    w.procesar_linea(f"{MARCA} cualquiera {_json()}")
    assert rec == [] and logs == []


def test_lineas_normales_siguen_al_log_sin_el_token(qapp):
    w, logs, rec = _worker()
    w.procesar_linea("Bot iniciado | ollama · qwen\n")
    w.procesar_linea(f"Error: LUNE_ORDENES_TOKEN={w._token} en el entorno\n")
    assert logs == ["Bot iniciado | ollama · qwen", "Error: LUNE_ORDENES_TOKEN=*** en el entorno"]
    assert rec == [] and all(w._token not in l for l in logs)


def test_la_orden_se_recorta(qapp):
    w, _logs, rec = _worker()
    w.procesar_linea(f"{MARCA} {w._token} {_json(texto='x' * 5000)}")
    assert len(rec[0][1]) == tw.MAX_ORDEN


def test_entorno_token_solo_con_ordenes_y_nunca_heredado(monkeypatch):
    monkeypatch.setenv(tw.ENV_TOKEN, "heredado-de-fuera")
    con = tw.TelegramBotWorker(ordenes=True)
    env = con._entorno()
    assert env[tw.ENV_TOKEN] == con._token and len(con._token) == 32
    assert env[tw.ENV_HIJO] == "1"
    sin = tw.TelegramBotWorker()
    env = sin._entorno()
    assert tw.ENV_TOKEN not in env and env[tw.ENV_HIJO] == "1"
    assert tw.TelegramBotWorker(ordenes=True)._token != con._token      # aleatorio cada vez


def test_ordenes_activas_exige_interruptor_y_tu_id(tmp_path, monkeypatch):
    from nucleo.config import Config
    cfg = Config(str(tmp_path / "config.json"))
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "123456789")
    assert cfg.get("telegram", "ordenes_pc") is False               # apagado por defecto
    assert tw.ordenes_activas(cfg) is False
    cfg.set("telegram", "ordenes_pc", True)
    assert tw.ordenes_activas(cfg) is True
    for malo in ("", "   ", "@diego", "12a4"):
        monkeypatch.setattr(datos, "telegram_admin_id", lambda m=malo: m)
        assert tw.ordenes_activas(cfg) is False, malo


# ── Respuestas por stdin ────────────────────────────────────────────────────────

class StdinFalso:
    def __init__(self, romper=False):
        self.escrito, self.cerrado, self.romper = [], False, romper

    def write(self, s):
        if self.romper:
            raise BrokenPipeError("tubería rota")
        if self.cerrado:
            raise ValueError("I/O operation on closed file")
        self.escrito.append(s)

    def flush(self):
        pass

    def close(self):
        self.cerrado = True


class ProcesoFalso:
    """Popen de mentira: se «cierra solo» al cerrarle el stdin (como el bot hijo de Lune)."""
    def __init__(self, vivo=True, stdin=None, ignora_eof=False):
        self.vivo, self.stdin, self.ignora_eof = vivo, stdin or StdinFalso(), ignora_eof
        self.terminado = False
        self.stdout = iter(())

    def poll(self):
        return None if self.vivo else 0

    def wait(self, timeout=None):
        if self.stdin.cerrado and not self.ignora_eof:
            self.vivo = False
        if self.vivo:
            raise subprocess.TimeoutExpired("npm", timeout)
        return 0

    def terminate(self):
        self.terminado, self.vivo = True, False

    def kill(self):
        self.vivo = False


def _parar_y_soltar(w, tope_s=5.0):
    """stop() y espera a que el hilo escritor (sin bot ya) termine: no quedan hilos vivos."""
    h = w._escritor
    w.stop()
    if h is not None:
        h.join(tope_s)
        assert not h.is_alive()


def test_responder_orden_escribe_json_en_el_stdin_del_bot(qapp):
    w, _l, _r = _worker()
    p = ProcesoFalso()
    w._process = p
    assert w.responder_orden("ab12", "✓ Abriendo Youtube… ¿algo más?") is True
    assert w.esperar_envios(5)                                      # lo escribe el hilo escritor
    linea = p.stdin.escrito[-1]
    assert linea.endswith("\n") and linea.isascii()                # \uXXXX: no depende del código de página
    assert json.loads(linea) == {"tipo": "orden:mensaje", "id": "ab12",
                                 "texto": "✓ Abriendo Youtube… ¿algo más?"}
    assert w.responder_orden("ab12", "x" * 10000) is True           # Telegram admite 4096
    assert w.esperar_envios(5)
    assert len(json.loads(p.stdin.escrito[-1])["texto"]) == tw.MAX_RESPUESTA
    _parar_y_soltar(w)


def test_responder_orden_no_revienta(qapp):
    w, _l, _r = _worker()
    assert w.responder_orden("ab12", "hola") is False               # aún no hay proceso
    w._process = ProcesoFalso(vivo=False)
    assert w.responder_orden("ab12", "hola") is False               # el bot murió
    w._process = ProcesoFalso(stdin=StdinFalso(romper=True))
    w.responder_orden("ab12", "hola")                               # a la cola: se rompe al escribir
    assert w.esperar_envios(5)
    assert w.responder_orden("ab12", "hola") is False               # tubería rota
    w._process = ProcesoFalso()
    assert w.responder_orden("../x", "hola") is False               # id raro
    assert w.responder_orden("ab12", "   ") is False                # nada que decir
    sin, _l, _r = _worker(ordenes=False)
    sin._process = ProcesoFalso()
    assert sin.responder_orden("ab12", "hola") is False             # sin canal, nada
    assert sin._process.stdin.escrito == []
    _parar_y_soltar(w)
    _parar_y_soltar(sin)


def test_responder_orden_desde_varios_hilos_no_mezcla_lineas(qapp):
    w, _l, _r = _worker()
    p = ProcesoFalso()
    w._process = p

    def mandar(n):
        for i in range(40):
            w.responder_orden(f"o{n}", f"mensaje {i} del hilo {n} " + "ñ" * 30)

    hilos = [threading.Thread(target=mandar, args=(n,)) for n in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert w.esperar_envios(10)
    assert len(p.stdin.escrito) == 240
    assert all(json.loads(l)["tipo"] == "orden:mensaje" for l in p.stdin.escrito)
    _parar_y_soltar(w)


def test_stop_cierra_el_stdin_y_es_idempotente(qapp):
    w, _l, _r = _worker()
    p = ProcesoFalso()
    w._process = p
    w.stop()
    assert p.stdin.cerrado and not p.terminado and w._process is None   # salió solo al ver EOF
    w.stop()                                                            # otra vez: nada
    assert w.responder_orden("ab12", "tarde") is False
    terco = ProcesoFalso(ignora_eof=True)                               # no se va: se termina
    w._process = terco
    w.stop()
    assert terco.stdin.cerrado and terco.terminado


def test_run_lanza_node_con_stdin_y_token_y_filtra_las_ordenes(qapp, tmp_path, monkeypatch):
    (tmp_path / "node_modules" / "grammy").mkdir(parents=True)          # ya instalado
    (tmp_path / "node_modules" / "grammy" / "package.json").write_text("{}", "utf-8")
    w, logs, rec = _worker()
    w.BOT_DIR = tmp_path
    w._node = "C:/node/node.exe"
    lanzados = []

    def popen(args, **kw):
        tok = kw["env"][tw.ENV_TOKEN]
        p = ProcesoFalso()
        p.stdout = iter(["Arrancando\n",
                         f"{MARCA} {tok} {_json(oid='x1', texto='hola')}\n",
                         "Bot iniciado | modelo\n"])
        lanzados.append((args, kw, p))
        return p

    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    parados = []
    w.stopped.connect(lambda: parados.append(1))
    w.run()
    assert len(lanzados) == 1                                     # sin npm: ya estaba instalado
    args, kw, p = lanzados[0]
    # node directo, SIN shell (con shell, terminate() mataba cmd.exe y dejaba node huérfano).
    assert args == ["C:/node/node.exe", "bot.js"] and not kw.get("shell")
    assert kw["stdin"] is subprocess.PIPE
    assert kw["encoding"] == "utf-8" and kw["env"][tw.ENV_HIJO] == "1"
    assert rec == [("x1", "hola")]
    assert logs[-2:] == ["Arrancando", "Bot iniciado | modelo"]
    assert not any(w._token in l or MARCA in l for l in logs)
    assert p.stdin.cerrado and parados == [1]


# ── De punta a punta con Node (ordenes.js real, sin Telegram) ───────────────────

SCRIPT_NODE = """
import { CanalOrdenes } from %s;
const canal = new CanalOrdenes({
  token: process.env.LUNE_ORDENES_TOKEN || "",
  responder: async (chatId, texto) => { console.log("RESPONDIDO " + JSON.stringify({ chatId, texto })); },
});
canal.escuchar({ salirAlCerrar: process.env.LUNE_BOT_HIJO === "1" });
console.log("activo=" + canal.activo());
canal.pedirOrden("abre la calculadora, ñandú 📱", 42);
"""


def _lector(p):
    cola = queue.Queue()

    def leer():
        for linea in p.stdout:
            cola.put(linea)
        cola.put(None)

    threading.Thread(target=leer, daemon=True).start()
    return cola


def _siguiente(cola, timeout=20):
    return cola.get(timeout=timeout)


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
def test_de_punta_a_punta_con_ordenes_js(qapp, monkeypatch):
    monkeypatch.setattr(datos, "telegram_admin_id", lambda: "42")      # el chat del script
    w, logs, rec = _worker()
    uri = (RAIZ / "telegram-bot-or" / "ordenes.js").as_uri()
    p = subprocess.Popen(["node", "--input-type=module", "-e", SCRIPT_NODE % json.dumps(uri)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1,
                         env=w._entorno(), cwd=str(RAIZ))
    w._process = p
    cola = _lector(p)
    try:
        while not rec:
            linea = _siguiente(cola)
            assert linea is not None, logs
            w.procesar_linea(linea)
        assert "activo=true" in logs
        oid, texto = rec[0]
        assert texto == "abre la calculadora, ñandú 📱"
        assert w.responder_orden("desconocida1", "esto no llega a ningún chat") is True
        assert w.responder_orden(oid, "✓ Abriendo la calculadora…") is True
        respuestas = []
        while not respuestas:
            linea = _siguiente(cola)
            assert linea is not None, logs
            if linea.startswith("RESPONDIDO "):
                respuestas.append(json.loads(linea[len("RESPONDIDO "):]))
        assert respuestas == [{"chatId": 42, "texto": "✓ Abriendo la calculadora…"}]
        # Lune para el bot: cierra el stdin y el bot (hijo de Lune) se va solo.
        w.stop()
        assert p.wait(timeout=20) == 0
        resto = []
        while True:
            linea = _siguiente(cola)
            if linea is None:
                break
            resto.append(linea)
        assert not any("ningún chat" in l for l in resto)
    finally:
        if p.poll() is None:
            p.kill()


# ── Política 'remoto' en el Ejecutor ────────────────────────────────────────────

def call(nombre, args=None):
    return "<|CALL " + json.dumps([nombre, args or {}], ensure_ascii=False) + "|>"


class Entorno:
    def __init__(self, pedir=True):
        self.registro = C.registro_completo()
        self.sesion = H.Sesion(self.registro, audit_path=None)
        self.llamados, self.preguntas, self.resultados, self.timers = [], [], [], []
        handlers = {n: self._handler(n) for n in C.CATALOGO}
        self.ej = A.Ejecutor(self.registro, self.sesion, handlers,
                             self._pedir if pedir else None,
                             programar=lambda s, fn: self.timers.append(fn) or MagicMock())

    def _handler(self, nombre):
        def fn(args, ctx):
            self.llamados.append((nombre, dict(args), dict(ctx)))
            return f"{nombre} hecho"
        return fn

    def _pedir(self, pendiente, responder):
        self.preguntas.append((pendiente, responder))

    def correr(self, texto, origen="remoto", ctx=None, origen_ej=None):
        _limpio, llamadas = self.ej.procesar(texto, origen, ctx)
        self.ej.ejecutar_llamadas(llamadas, origen_ej, ctx, self.resultados.append)
        return llamadas

    def nombres(self):
        return [n for n, _, _ in self.llamados]


def test_remoto_tambien_pide_permiso_para_la_lectura():
    e = Entorno()
    llamadas = e.correr(call("sistema_info"))
    assert llamadas[0].origen == A.REMOTO
    assert e.llamados == [] and len(e.preguntas) == 1
    pendiente, responder = e.preguntas[0]
    assert pendiente["remoto"] is True and pendiente["origen"] == A.REMOTO
    assert pendiente["motivo"] == A.AVISO_REMOTO and "Telegram" in pendiente["motivo"]
    responder(True)
    assert e.nombres() == ["sistema_info"] and e.resultados[-1].ok
    assert e.llamados[0][2]["origen"] == A.REMOTO and e.llamados[0][2]["remoto"] is True


def test_remoto_tiene_las_herramientas_del_modo_pero_con_aprobacion():
    e = Entorno()
    e.correr(call("abrir_url", {"url": "https://www.youtube.com"}))
    assert e.llamados == [] and len(e.preguntas) == 1               # no se deniega: se pregunta
    e.preguntas[0][1](True)
    assert e.nombres() == ["abrir_url"]
    # Un «No» no hace nada y lo dice.
    e.correr(call("lanzar_app", {"app": "calc"}))
    e.preguntas[-1][1](False)
    assert e.nombres() == ["abrir_url"]
    r = e.resultados[-1]
    assert not r.ok and r.estado == A.RECHAZADA and "rechazada por el usuario" in r.mensaje


def test_remoto_la_llamada_directa_no_se_salta_la_aprobacion():
    from servicios.tools import ToolManager
    e = Entorno()
    llamadas = ToolManager().detectar_llamadas("abre youtube")
    assert llamadas[0].directa and llamadas[0].origen == A.USUARIO
    e.ej.ejecutar_llamadas(llamadas, A.REMOTO, {"modo": "normal"}, e.resultados.append)
    assert e.llamados == [] and len(e.preguntas) == 1
    assert e.preguntas[0][0]["remoto"] is True
    e.preguntas[0][1](True)
    assert e.nombres() == ["abrir_url"] and e.resultados[-1].ok


def test_remoto_cada_ejecucion_pregunta_la_suya_tambien_la_lectura_directa():
    from servicios.tools import ToolManager
    e = Entorno()
    tm = ToolManager()
    e.ej.ejecutar_llamadas(tm.detectar_llamadas("abre youtube"), A.REMOTO, None, e.resultados.append)
    e.ej.ejecutar_llamadas(tm.detectar_llamadas("estado del pc"), A.REMOTO, None, e.resultados.append)
    assert [p["herramienta"] for p, _ in e.preguntas] == ["abrir_url", "sistema_info"]
    assert e.llamados == []
    e.preguntas[1][1](True)
    assert e.nombres() == ["sistema_info"]


def test_remoto_sin_canal_de_aprobacion_se_rechaza():
    e = Entorno(pedir=False)
    e.correr(call("sistema_info"))
    r = e.resultados[-1]
    assert e.llamados == [] and not r.ok and r.estado == A.RECHAZADA
    assert "Telegram" in r.mensaje and "no hay a quién pedir permiso" in r.mensaje


def test_remoto_caduca_si_nadie_responde():
    e = Entorno()
    e.correr(call("abrir_url", {"url": "https://x.com"}))
    assert len(e.timers) == 1
    e.timers[0]()
    r = e.resultados[-1]
    assert e.llamados == [] and r.estado == A.CADUCADA and "Nadie respondió" in r.mensaje


def test_remoto_mezclado_con_no_confiable_es_lo_mas_restrictivo():
    e = Entorno()
    e.correr(call("abrir_url", {"url": "https://x.com"}), origen="no_confiable", origen_ej="remoto")
    assert e.llamados == [] and e.resultados[-1].estado == A.NO_CONFIABLE_ESTADO
    e.correr(call("sistema_info"), origen="no_confiable", origen_ej="remoto")
    assert e.llamados == [] and len(e.preguntas) == 1               # lectura, pero pregunta
    assert e.preguntas[0][0]["remoto"] is True


def test_origen_desconocido_sigue_siendo_no_confiable():
    e = Entorno()
    e.correr(call("abrir_url", {"url": "https://x.com"}), origen="telegram")
    assert e.llamados == [] and e.resultados[-1].estado == A.NO_CONFIABLE_ESTADO
    assert A._origen(" REMOTO ") == A.REMOTO and A._origen("remota") == A.NO_CONFIABLE


def test_usuario_sigue_igual():
    e = Entorno()
    e.correr(call("sistema_info"), origen="usuario")
    e.correr(call("abrir_url", {"url": "https://www.youtube.com"}), origen="usuario")
    assert e.nombres() == ["sistema_info", "abrir_url"] and e.preguntas == []


def test_aprobacion_dinamica_con_origen_remoto():
    assert C.ORIGEN_REMOTO in C.ORIGENES
    for nombre in ("sistema_info", "listar_alarmas", "temporizador", "dar_de_comer"):
        assert C.aprobacion_dinamica(nombre, {"origen": "remoto"}) is True
        assert C.aprobacion_dinamica(nombre, {"origen": "usuario"}) is False


def test_la_pregunta_dice_pedido_desde_telegram(qapp):
    from ui.acciones_qt import texto_pregunta
    e = Entorno()
    e.correr(call("lanzar_app", {"app": "calc"}))
    texto = texto_pregunta(e.preguntas[0][0])
    assert texto.startswith("Pedido desde Telegram: Abrir la aplicación")
    assert A.AVISO_REMOTO in texto and "texto externo" not in texto


# ── AIWorker y taint ────────────────────────────────────────────────────────────

def test_ai_worker_ofrece_todas_las_del_modo_marcadas_pide_permiso(qapp):
    from servicios.ai_worker import AIWorker, normalizar_origen, reglas_para
    assert normalizar_origen("remoto") == "remoto" and normalizar_origen(" Remoto ") == "remoto"
    assert normalizar_origen("telegram") == "no_confiable"
    e = Entorno()
    remoto = reglas_para(e.ej, "normal", "remoto", {"modo": "normal", "proveedor": "ollama"})
    lineas = [l for l in remoto.splitlines() if l.startswith("- ")]
    assert any(l.startswith("- abrir_url(") for l in lineas)
    assert lineas and all(l.endswith("(pide permiso)") for l in lineas)
    solo = reglas_para(e.ej, "normal", "no_confiable", {"modo": "normal"})
    assert "abrir_url(" not in solo and "sistema_info" in solo
    w = AIWorker(MagicMock(), "hola", "ollama", origen="remoto", ejecutor=e.ej, modo="normal",
                 ctx={"modo": "normal"})
    assert w.origen == "remoto"


@pytest.fixture
def modelos(monkeypatch):
    m = {"max_historial": 5}
    monkeypatch.setattr(datos, "get_modelos", lambda: m)
    monkeypatch.setattr(datos, "get_bot", lambda: m)
    monkeypatch.setattr(datos, "get_apis", lambda: {})
    monkeypatch.setattr(datos, "max_historial", lambda: m["max_historial"])
    return m


class _Resp:
    status_code = 200
    headers = {}

    def __init__(self, texto):
        self._lineas = [json.dumps({"message": {"content": texto}, "done": False}).encode(),
                        json.dumps({"message": {"content": ""}, "done": True}).encode()]

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self._lineas

    def close(self):
        pass


class _Sesion:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)

    def post(self, url, **kw):
        return _Resp(self.respuestas.pop(0))


def test_turno_remoto_marca_el_historial_y_los_siguientes_piden_permiso(modelos):
    from servicios import ai_manager as am
    assert am.es_no_confiable("remoto") is True
    ai = am.AIManager.__new__(am.AIManager)
    prov = am.OllamaProvider("http://localhost:11434", "m")
    prov._session = _Sesion("Te lo abro.", "Hola")
    ai.providers = {"ollama": prov}
    asyncio.run(ai.chat("[Desde Telegram] abre youtube", "sistema", provider="ollama", origen="remoto"))
    usuario, respuesta = prov.conversation_history
    assert usuario[am.MARCA_NO_CONFIABLE] and respuesta[am.MARCA_NO_CONFIABLE]
    asyncio.run(ai.chat("hola", "sistema", provider="ollama", origen="usuario"))
    assert ai.contexto_contaminado("ollama") is True
    # Turno local siguiente: lo que no es de lectura pide permiso mientras siga en la ventana.
    e = Entorno()
    e.correr(call("abrir_url", {"url": "https://x.com"}), origen="usuario",
             ctx={"ai": ai, "proveedor": "ollama"})
    assert e.llamados == [] and len(e.preguntas) == 1 and e.preguntas[0][0].get("contaminado")
