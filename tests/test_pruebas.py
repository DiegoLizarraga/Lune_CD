"""
Tests de servicios/pruebas.py (los «Probar» de Ajustes, /probar de patata y las comprobaciones
de red del diagnóstico) con HTTP FALSO: nada sale a internet. Lo importante: cada prueba da
bien / mal / sin configurar con un mensaje que dice qué hacer, y ni la clave de OpenRouter ni
el token de Telegram aparecen NUNCA en lo que devuelven (tampoco cuando requests falla con la
URL, que en Telegram lleva el token dentro).
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from servicios import pruebas as P  # noqa: E402

# Clave FALSA, en dos trozos para que el guardián de secretos de CI no la tome por una de verdad.
CLAVE = "sk-or-v1-" + "0123456789abcdef" * 2
TOKEN = "123456789:AAH-secretoSecretoSecreto_12345"


class Resp:
    def __init__(self, codigo=200, datos=None):
        self.status_code = codigo
        self._datos = datos

    def json(self):
        if isinstance(self._datos, Exception):
            raise self._datos
        return self._datos


class HttpFalso:
    """requests.get falso: rutas[url que contiene X] = Resp o excepción. Apunta lo pedido."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.pedidas = []

    def __call__(self, url, headers=None, timeout=None):
        self.pedidas.append((url, dict(headers or {}), timeout))
        for trozo, r in self.rutas.items():
            if trozo in url:
                if isinstance(r, BaseException):
                    raise r
                return r
        raise AssertionError(f"URL inesperada: {url}")


class ConnectionError_(Exception):
    """Como requests.ConnectionError: su texto lleva la URL entera."""


ConnectionError_.__name__ = "ConnectionError"


def _sin_secretos(obj):
    texto = json.dumps(obj, ensure_ascii=False)
    assert CLAVE not in texto and TOKEN not in texto, texto
    assert "AAH-secreto" not in texto and "0123456789abcdef0123" not in texto, texto


# ── OpenRouter ───────────────────────────────────────────────────────────────

def test_openrouter_sin_clave_es_sin_configurar():
    http = HttpFalso({})
    r = P.probar_openrouter("", "openrouter/auto", http=http)
    assert r["ok"] is None and "openrouter.ai/keys" in r["mensaje"]
    assert http.pedidas == []                              # ni siquiera se pregunta


def test_openrouter_clave_buena_y_modelo_que_existe():
    http = HttpFalso({"/api/v1/key": Resp(200, {"data": {"label": f"sk-or-v1-012…{CLAVE[-3:]}", "usage": 1.5,
                                                         "limit": 10, "limit_remaining": 8.5,
                                                         "is_free_tier": False}}),
                      "/api/v1/models": Resp(200, {"data": [{"id": "openai/gpt-4o-mini"}, {"id": "x/y"}]})})
    r = P.probar_openrouter(CLAVE, "openai/gpt-4o-mini", http=http)
    assert r["ok"] is True and r["modelo_ok"] is True, r
    assert "funciona" in r["mensaje"] and "8.50" in r["mensaje"]
    url, cab, _ = http.pedidas[0]
    assert url == P.URL_OPENROUTER_CLAVE and cab["Authorization"] == f"Bearer {CLAVE}"
    assert "Authorization" not in http.pedidas[1][1]       # /models no lleva la clave
    _sin_secretos(r)
    assert CLAVE[-3:] not in r["mensaje"]                  # la «label» (con trozos de la clave) no sale


def test_openrouter_modelo_con_sufijo_de_ruta_cuenta():
    http = HttpFalso({"/api/v1/key": Resp(200, {"data": {}}),
                      "/api/v1/models": Resp(200, {"data": [{"id": "meta/llama"}]})})
    assert P.probar_openrouter(CLAVE, "meta/llama:nitro", http=http)["ok"] is True


def test_openrouter_modelo_que_no_existe_falla_con_el_paso_siguiente():
    http = HttpFalso({"/api/v1/key": Resp(200, {"data": {}}),
                      "/api/v1/models": Resp(200, {"data": [{"id": "otro/modelo"}]})})
    r = P.probar_openrouter(CLAVE, "no/existe", http=http)
    assert r["ok"] is False and r["modelo_ok"] is False
    assert "no/existe" in r["mensaje"] and "openrouter/auto" in r["mensaje"]


def test_openrouter_auto_no_pide_la_lista():
    http = HttpFalso({"/api/v1/key": Resp(200, {"data": {"is_free_tier": True}})})
    r = P.probar_openrouter(CLAVE, "openrouter/auto", http=http)
    assert r["ok"] is True and r["modelo_ok"] is True and "gratuita" in r["mensaje"]
    assert len(http.pedidas) == 1


@pytest.mark.parametrize("codigo, frase", [(401, "no reconoce"), (403, "no reconoce"), (429, "espere"),
                                           (500, "HTTP 500")])
def test_openrouter_errores_http(codigo, frase):
    r = P.probar_openrouter(CLAVE, "", http=HttpFalso({"/api/v1/key": Resp(codigo, {"error": CLAVE})}))
    assert r["ok"] is False and frase in r["mensaje"]
    _sin_secretos(r)


def test_openrouter_sin_saldo():
    r = P.probar_openrouter(CLAVE, "", http=HttpFalso({"/api/v1/key": Resp(200, {"data": {"limit_remaining": 0}})}))
    assert r["ok"] is False and "saldo" in r["mensaje"]


def test_openrouter_sin_red_no_enseña_la_url_ni_la_clave():
    e = ConnectionError_(f"HTTPSConnectionPool(host='openrouter.ai'): Authorization: Bearer {CLAVE}")
    r = P.probar_openrouter(CLAVE, "", http=HttpFalso({"/api/v1/key": e}))
    assert r["ok"] is False and "no hay conexión" in r["mensaje"]
    _sin_secretos(r)


def test_openrouter_mascara_o_espacios_no_se_mandan():
    http = HttpFalso({})
    assert P.probar_openrouter("abc def", "", http=http)["ok"] is False
    assert P.probar_openrouter("••••••••", "", http=http)["ok"] is False
    assert http.pedidas == []


# ── Ollama ───────────────────────────────────────────────────────────────────

def test_ollama_responde_con_el_modelo():
    r = P.probar_ollama("localhost", "qwen2.5:7b", listar=lambda u: (True, ["llava", "qwen2.5:7b"], "ok"))
    assert r["ok"] is True and r["modelos"] == ["llava", "qwen2.5:7b"]
    assert r["url"] == "http://localhost:11434"


def test_ollama_latest_cuenta():
    assert P.probar_ollama("", "llama3", listar=lambda u: (True, ["llama3:latest"], ""))["ok"] is True


def test_ollama_sin_el_modelo_o_sin_modelos_o_apagado():
    r = P.probar_ollama("", "falta", listar=lambda u: (True, ["a"], ""))
    assert r["ok"] is False and "ollama pull falta" in r["mensaje"] and r["modelos"] == ["a"]
    assert P.probar_ollama("", "", listar=lambda u: (True, [], ""))["ok"] is False
    r = P.probar_ollama("", "", listar=lambda u: (False, [], "No hay nadie escuchando ahí."))
    assert r["ok"] is False and "No encuentro Ollama" in r["mensaje"]


def test_ollama_sin_modelo_elegido_da_la_lista():
    r = P.probar_ollama("http://10.0.0.5:11434", "", listar=lambda u: (True, ["b", "a"], ""))
    assert r["ok"] is True and "elige uno" in r["mensaje"]


# ── Telegram ─────────────────────────────────────────────────────────────────

def _node_ok():
    return {"ok": True, "version": "v20.11.0", "mensaje": ""}


def test_telegram_token_bueno_id_node_y_carpeta():
    http = HttpFalso({"/getMe": Resp(200, {"ok": True, "result": {"username": "MiLuneBot"}})})
    r = P.probar_telegram(TOKEN, "12345678", http=http, node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is True and r["bot"] == "MiLuneBot" and "@MiLuneBot" in r["mensaje"]
    assert [i["id"] for i in r["items"]] == ["token", "id", "node", "carpeta"]
    assert all(i["ok"] is True for i in r["items"])
    _sin_secretos(r)


def test_telegram_sin_token_es_sin_configurar():
    r = P.probar_telegram("", "", http=HttpFalso({}), node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is None and "@BotFather" in r["mensaje"]


def test_telegram_token_con_mala_forma_no_se_manda():
    http = HttpFalso({})
    r = P.probar_telegram("hola", "1", http=http, node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is False and http.pedidas == []


def test_telegram_token_rechazado_y_fallos_de_red_sin_token():
    r = P.probar_telegram(TOKEN, "1", http=HttpFalso({"/getMe": Resp(401, {"ok": False})}),
                          node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is False and "no reconoce" in r["mensaje"]
    _sin_secretos(r)
    e = ConnectionError_(f"Max retries exceeded with url: /bot{TOKEN}/getMe")
    r = P.probar_telegram(TOKEN, "1", http=HttpFalso({"/getMe": e}), node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is False and "no hay conexión" in r["mensaje"]
    _sin_secretos(r)


def test_telegram_id_node_viejo_y_sin_carpeta():
    http = HttpFalso({"/getMe": Resp(200, {"ok": True, "result": {"username": "b"}})})
    r = P.probar_telegram(TOKEN, "no-numerico", http=http, node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is False and "solo números" in r["mensaje"]
    viejo = lambda: {"ok": False, "version": "v16.0.0", "mensaje": ""}       # noqa: E731
    r = P.probar_telegram(TOKEN, "1", http=http, node=viejo, carpeta=lambda: True)
    assert r["ok"] is False and "v16.0.0" in r["mensaje"] and "nodejs.org" in r["mensaje"]
    r = P.probar_telegram(TOKEN, "1", http=http, node=_node_ok, carpeta=lambda: False)
    assert r["ok"] is False and "carpeta" in r["mensaje"]


def test_telegram_sin_id_funciona_pero_avisa():
    http = HttpFalso({"/getMe": Resp(200, {"ok": True, "result": {}})})
    r = P.probar_telegram(TOKEN, "", http=http, node=_node_ok, carpeta=lambda: True)
    assert r["ok"] is True and "/id" in r["mensaje"]


def test_node_no_necesario_no_falla():
    falta = lambda: {"ok": False, "version": "", "mensaje": ""}               # noqa: E731
    assert P.probar_node(falta, necesario=False)["ok"] is None
    assert P.probar_node(falta)["ok"] is False
    assert P.probar_node(_node_ok)["ok"] is True


def test_tapar():
    assert P.tapar(f"x {TOKEN} y {TOKEN}", TOKEN) == "x ••• y •••"
    assert P.tapar("abc", "") == "abc" and P.tapar(None, TOKEN) == ""


# ── Internet, sonido, Whisper y disco ────────────────────────────────────────

def test_internet():
    assert P.probar_internet(http=HttpFalso({"api.github.com": Resp(200, {})}))["ok"] is True
    assert P.probar_internet(http=HttpFalso({"api.github.com": Resp(403, {})}))["ok"] is True   # hay red
    r = P.probar_internet(http=HttpFalso({"api.github.com": ConnectionError_("x")}))
    assert r["ok"] is False and "Wi-Fi" in r["mensaje"]


def _sd(dispositivos):
    return SimpleNamespace(query_devices=lambda: dispositivos)


def test_audio():
    mic = {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0}
    alt = {"name": "Altavoces", "max_input_channels": 0, "max_output_channels": 2}
    assert P.probar_audio(_sd([mic, alt, dict(mic)]))["ok"] is True
    assert P.probar_audio(_sd([mic, alt]))["mensaje"] == "Veo 1 micrófono y 1 salida."
    assert P.probar_audio(_sd([alt]))["ok"] is None
    assert P.probar_audio(_sd([mic]))["ok"] is None
    assert P.probar_audio(_sd([]))["ok"] is None

    def roto():
        raise OSError("PortAudio")
    assert P.probar_audio(SimpleNamespace(query_devices=roto))["ok"] is None


def test_audio_cuenta_cada_aparato_una_vez_en_windows():
    """Windows repite cada aparato por API (MME, WASAPI…): se cuentan los de MME, como Ajustes."""
    disp = [{"name": "Mic (Realtek)", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 0},
            {"name": "Altavoces (Realtek)", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 0},
            {"name": "Mic (Realtek Audio)", "max_input_channels": 2, "max_output_channels": 0, "hostapi": 1},
            {"name": "Altavoces (Realtek Audio)", "max_input_channels": 0, "max_output_channels": 2, "hostapi": 1}]
    sd = SimpleNamespace(query_devices=lambda: disp,
                         query_hostapis=lambda: [{"name": "MME"}, {"name": "Windows WASAPI"}])
    assert P.probar_audio(sd)["mensaje"] == "Veo 1 micrófono y 1 salida."


def test_whisper():
    r = P.probar_whisper("base", descargado=lambda m: False, faltan=[])
    assert r["ok"] is None and "145 MB" in r["mensaje"] and "primera vez" in r["mensaje"]
    assert P.probar_whisper("small", descargado=lambda m: True, faltan=[])["ok"] is True
    assert P.probar_whisper("base", descargado=lambda m: True, faltan=["faster-whisper"])["ok"] is None


def test_espacio_libre(tmp_path):
    poco = lambda ruta: SimpleNamespace(total=10, used=9, free=100 * 1024 ** 2)      # noqa: E731
    mucho = lambda ruta: (10, 1, 50 * 1024 ** 3)                                     # noqa: E731
    r = P.espacio_libre(tmp_path / "no" / "existe", uso=poco)
    assert r["ok"] is False and "100 MB" in r["mensaje"]
    r = P.espacio_libre(tmp_path, uso=mucho)
    assert r["ok"] is True and "50 GB" in r["mensaje"]
    assert P.espacio_libre(tmp_path)["ok"] in (True, False)                          # el de verdad


def test_probar_salida():
    class Voz:
        available = True
        salida_actual = ""

        def __init__(self):
            self.aplicadas = []

        def aplicar_salida(self, n):
            self.aplicadas.append(n)
            return n == "Auriculares"

        def probar_salida(self):
            return True
    v = Voz()
    r = P.probar_salida(v, "Auriculares")
    assert r["ok"] is True and "¿me oyes?" in r["mensaje"] and v.aplicadas == ["Auriculares"]
    r = P.probar_salida(Voz(), "No existe")
    assert r["ok"] is True and "No encontré" in r["mensaje"]
    assert P.probar_salida(None)["ok"] is False
    assert P.probar_salida(SimpleNamespace(available=False))["ok"] is False


def test_los_mensajes_se_imprimen_en_cp1252():
    """patata y la consola de Windows: nada de flechas ni emojis en lo que se enseña."""
    http = HttpFalso({"/api/v1/key": Resp(401, {}), "/getMe": Resp(401, {}), "github": Resp(200, {})})
    for r in (P.probar_openrouter(CLAVE, "", http=http), P.probar_internet(http=http),
              P.probar_telegram(TOKEN, "x", http=http, node=lambda: {"ok": False}, carpeta=lambda: False),
              P.probar_ollama("", "m", listar=lambda u: (False, [], "nada")),
              P.probar_whisper("base", descargado=lambda m: False, faltan=[]),
              P.probar_audio(_sd([]))):
        r["mensaje"].encode("cp1252")
        for i in r.get("items", []):
            i["detalle"].encode("cp1252")


def test_importar_pruebas_no_carga_nada_pesado():
    codigo = ("import sys; import servicios.pruebas; "
              "print(sorted(m for m in ('PyQt6', 'requests', 'sounddevice', 'faster_whisper') if m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"
