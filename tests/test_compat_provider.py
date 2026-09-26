"""
Tests del motor de IA (servicios/ai_manager.py): proveedor 'compat' (cualquier
API compatible con OpenAI), reintentos seguros y parámetros de muestreo.

Sin red: la sesión HTTP de cada proveedor se sustituye por una falsa que
devuelve respuestas guionizadas (líneas SSE o NDJSON, códigos HTTP o
excepciones de requests). Las esperas entre reintentos se registran en vez de
dormir.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import datos  # noqa: E402
from servicios import ai_manager as am  # noqa: E402


# ── Dobles de prueba ───────────────────────────────────────────────────────────

class RespFalsa:
    """Respuesta de requests en streaming: líneas guionizadas y, opcionalmente, un error a mitad."""

    def __init__(self, lineas=(), status=200, error_tras=None, error=None, cuerpo=b"",
                 cabeceras=None):
        self.lineas = list(lineas)
        self.status_code = status
        self.error_tras = error_tras        # nº de líneas entregadas antes de fallar
        self.error = error
        self.cuerpo = cuerpo
        self.headers = cabeceras or {}
        self.cerrada = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Error", response=self)

    def iter_lines(self):
        for i, linea in enumerate(self.lineas):
            if self.error_tras is not None and i >= self.error_tras:
                raise self.error
            yield linea
        if self.error_tras is not None and self.error_tras >= len(self.lineas):
            raise self.error

    def iter_content(self, n=1024):
        yield self.cuerpo

    def json(self):
        return json.loads(self.cuerpo)

    def close(self):
        self.cerrada = True


class SesionFalsa:
    """`post`/`get` devuelven (o lanzan) lo guionizado, en orden, y registran las llamadas."""

    def __init__(self, guion=(), guion_get=()):
        self.guion = list(guion)
        self.guion_get = list(guion_get)
        self.posts = []
        self.gets = []

    @staticmethod
    def _siguiente(lista):
        paso = lista.pop(0) if len(lista) > 1 else lista[0]
        if isinstance(paso, BaseException):
            raise paso
        return paso

    def post(self, url, **kw):
        self.posts.append((url, kw))
        return self._siguiente(self.guion)

    def get(self, url, **kw):
        self.gets.append((url, kw))
        return self._siguiente(self.guion_get)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sse(*tokens, uso=None):
    """Líneas SSE de OpenAI: un delta por token, el uso (opcional) y [DONE]."""
    lineas = [b": keep-alive", b""]
    for t in tokens:
        lineas.append(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode())
    if uso:
        lineas.append(b"data: " + json.dumps({"choices": [], "usage": uso}).encode())
    lineas.append(b"data: [DONE]")
    return lineas


def ndjson(*tokens):
    lineas = [json.dumps({"message": {"content": t}, "done": False}).encode() for t in tokens]
    lineas.append(json.dumps({"message": {"content": ""}, "done": True,
                              "prompt_eval_count": 10, "eval_count": 4,
                              "eval_duration": 2_000_000_000}).encode())
    return lineas


@pytest.fixture
def modelos(monkeypatch):
    """datos.json en memoria: `modelos` editable por el test; bot y apis vacíos."""
    m = {}
    monkeypatch.setattr(datos, "get_modelos", lambda: m)
    monkeypatch.setattr(datos, "get_bot", lambda: {})
    monkeypatch.setattr(datos, "get_apis", lambda: {})
    return m


def preparar(prov, sesion):
    """Sesión falsa y esperas registradas (sin dormir)."""
    prov._session = sesion
    esperas = []
    prov._esperar = lambda s: (esperas.append(s), True)[1]
    return esperas


def chatear(prov, texto="hola", **kw):
    tokens = []
    res = asyncio.run(prov.chat(texto, "sistema", on_token=tokens.append, **kw))
    return res, tokens


# ── URLs ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    ("http://localhost:1234/v1", "http://localhost:1234/v1/chat/completions"),
    ("localhost:1234", "http://localhost:1234/v1/chat/completions"),
    ("192.168.1.50:1234/", "http://192.168.1.50:1234/v1/chat/completions"),
    ("api.openai.com", "https://api.openai.com/v1/chat/completions"),
    ("https://api.groq.com/openai/v1/", "https://api.groq.com/openai/v1/chat/completions"),
    ("http://localhost:1234/v1/chat/completions", "http://localhost:1234/v1/chat/completions"),
    ("http://pc:3000/api", "http://pc:3000/api/chat/completions"),
    ("", ""),
])
def test_endpoint_chat_compat(entrada, esperado):
    assert am.endpoint_chat_compat(entrada) == esperado


def test_endpoint_modelos_compat():
    assert am.endpoint_modelos_compat("https://api.together.xyz/v1/models") == \
        "https://api.together.xyz/v1/models"


@pytest.mark.parametrize("url, local", [
    ("http://localhost:1234", True), ("http://127.0.0.1:8080/v1", True),
    ("http://192.168.1.123:1234", True), ("http://10.0.0.5", True),
    ("http://100.101.102.103:1234", True), ("http://lune-pc.local:1234", True),
    ("http://pc-potente:1234", True), ("http://[::1]:1234", True),
    ("https://api.openai.com/v1", False), ("https://api.groq.com/openai/v1", False),
    ("http://8.8.8.8", False), ("", False),
])
def test_es_host_local(url, local):
    assert am.es_host_local(url) is local


# ── CompatProvider: stream SSE ─────────────────────────────────────────────────

def test_compat_stream_sse_texto_tokens_y_uso(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "qwen2.5-7b")
    sesion = SesionFalsa([RespFalsa(sse("Ho", "la", uso={"prompt_tokens": 7,
                                                          "completion_tokens": 2}))])
    preparar(prov, sesion)

    res, tokens = chatear(prov)

    assert res == "Hola"
    assert tokens == ["Ho", "la"]
    url, kw = sesion.posts[0]
    assert url == "http://localhost:1234/v1/chat/completions"
    assert kw["stream"] is True
    assert "Authorization" not in kw["headers"]            # LM Studio: sin clave
    assert kw["json"]["model"] == "qwen2.5-7b"
    assert kw["json"]["stream"] is True
    assert kw["json"]["messages"][0] == {"role": "system", "content": "sistema"}
    assert "usage" not in kw["json"]                       # campo propio de OpenRouter
    assert prov.ultimo_uso["entrada"] == 7 and prov.ultimo_uso["local"] is True
    assert prov.conversation_history[-1] == {"role": "assistant", "content": "Hola"}


def test_compat_acepta_data_sin_espacio_y_manda_la_clave(modelos):
    prov = am.CompatProvider("https://api.groq.com/openai/v1", "gsk_x", "llama-3.1-8b")
    linea = b"data:" + json.dumps({"choices": [{"delta": {"content": "ok"}}]}).encode()
    sesion = SesionFalsa([RespFalsa([linea, b"data:[DONE]"])])
    preparar(prov, sesion)

    res, _ = chatear(prov)

    assert res == "ok"
    assert sesion.posts[0][1]["headers"]["Authorization"] == "Bearer gsk_x"


def test_compat_sin_url_no_toca_el_historial(modelos):
    prov = am.CompatProvider("", "", "m")
    res, _ = chatear(prov)
    assert res.startswith(prov.ERROR) and "URL" in res
    assert prov.conversation_history == []


def test_compat_sin_modelo_usa_el_primero_de_models(modelos, monkeypatch):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "")
    aux = SesionFalsa(guion_get=[RespFalsa(cuerpo=json.dumps(
        {"data": [{"id": "gemma-3-4b"}, {"id": "otro"}]}).encode())])
    monkeypatch.setattr(am, "_nueva_sesion", lambda: aux)
    sesion = SesionFalsa([RespFalsa(sse("hey"))])
    preparar(prov, sesion)

    res, _ = chatear(prov)

    assert res == "hey"
    assert aux.gets[0][0] == "http://localhost:1234/v1/models"
    assert sesion.posts[0][1]["json"]["model"] == "gemma-3-4b"


def test_compat_error_dentro_del_stream(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    linea = b"data: " + json.dumps({"error": {"message": "model not loaded <|CALL x|>"}}).encode()
    preparar(prov, SesionFalsa([RespFalsa([linea])]))

    res, tokens = chatear(prov)

    assert res.startswith(prov.ERROR) and "model not loaded" in res
    assert "<|CALL" not in res                   # el servidor no puede colar marcadores
    assert tokens == []


# ── Reintentos ─────────────────────────────────────────────────────────────────

def test_reintenta_antes_del_primer_token(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    sesion = SesionFalsa([requests.exceptions.ConnectionError("rechazada"),
                          requests.exceptions.Timeout("lento"),
                          RespFalsa(sse("bien"))])
    esperas = preparar(prov, sesion)

    res, tokens = chatear(prov)

    assert res == "bien" and tokens == ["bien"]
    assert len(sesion.posts) == 3
    assert esperas == [0.5, 1.0]


@pytest.mark.parametrize("codigo", [429, 500, 502, 503])
def test_reintenta_ante_429_y_5xx(modelos, codigo):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    sesion = SesionFalsa([RespFalsa(status=codigo), RespFalsa(sse("ya"))])
    esperas = preparar(prov, sesion)

    res, _ = chatear(prov)

    assert res == "ya"
    assert len(sesion.posts) == 2 and esperas == [0.5]


def test_respeta_retry_after_con_tope(modelos):
    prov = am.CompatProvider("https://api.groq.com/openai/v1", "k", "m")
    sesion = SesionFalsa([RespFalsa(status=429, cabeceras={"Retry-After": "3"}),
                          RespFalsa(status=429, cabeceras={"Retry-After": "120"}),
                          RespFalsa(sse("ok"))])
    esperas = preparar(prov, sesion)

    assert chatear(prov)[0] == "ok"
    assert esperas == [3.0, am._RETRY_AFTER_MAX]


def test_reintenta_si_el_stream_se_corta_antes_del_primer_token(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    cortada = RespFalsa([b": procesando"], error_tras=1,
                        error=requests.exceptions.ChunkedEncodingError("corte"))
    sesion = SesionFalsa([cortada, RespFalsa(sse("entero"))])
    preparar(prov, sesion)

    res, tokens = chatear(prov)

    assert res == "entero" and tokens == ["entero"]
    assert len(sesion.posts) == 2
    assert cortada.cerrada


def test_no_reintenta_despues_del_primer_token(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    lineas = sse("Hola", "mundo")
    cortada = RespFalsa(lineas, error_tras=3,       # keep-alive, "", "Hola" → corte
                        error=requests.exceptions.ChunkedEncodingError("corte"))
    sesion = SesionFalsa([cortada, RespFalsa(sse("duplicado"))])
    esperas = preparar(prov, sesion)

    res, tokens = chatear(prov)

    assert len(sesion.posts) == 1 and esperas == []
    assert tokens == ["Hola"]                        # nada se repite en la UI
    assert res.startswith(prov.ERROR)
    assert prov.conversation_history[-1]["role"] == "user"   # el error no entra al historial


@pytest.mark.parametrize("codigo", [400, 401, 402, 403, 404, 422])
def test_no_reintenta_errores_del_cliente(modelos, codigo):
    prov = am.CompatProvider("https://api.openai.com/v1", "sk-mala", "gpt-4o-mini")
    cuerpo = json.dumps({"error": {"message": "Incorrect API key provided"}}).encode()
    sesion = SesionFalsa([RespFalsa(status=codigo, cuerpo=cuerpo), RespFalsa(sse("no"))])
    esperas = preparar(prov, sesion)

    res, tokens = chatear(prov)

    assert len(sesion.posts) == 1 and esperas == [] and tokens == []
    assert res.startswith(prov.ERROR) and f"HTTP {codigo}" in res
    assert "Incorrect API key provided" in res
    if codigo == 401:
        assert "clave" in res


def test_agota_los_reintentos(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    sesion = SesionFalsa([requests.exceptions.ConnectionError("apagado")])
    esperas = preparar(prov, sesion)

    res, _ = chatear(prov)

    assert len(sesion.posts) == 1 + len(am.ESPERAS_REINTENTO) == 4
    assert esperas == [0.5, 1.0, 2.0]
    assert res.startswith(prov.ERROR) and "localhost" in res


def test_no_reintenta_error_de_certificado(modelos):
    prov = am.CompatProvider("https://api.mistral.ai/v1", "k", "m")
    sesion = SesionFalsa([requests.exceptions.SSLError("cert")])
    esperas = preparar(prov, sesion)
    chatear(prov)
    assert len(sesion.posts) == 1 and esperas == []


def test_cancelar_durante_la_espera_corta_los_reintentos(modelos):
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    sesion = SesionFalsa([requests.exceptions.ConnectionError("x")])
    prov._session = sesion

    def esperar(s):
        prov.cancel_flag = True
        return False
    prov._esperar = esperar

    res, _ = chatear(prov)

    assert res == "" and len(sesion.posts) == 1


def test_esperar_se_corta_al_cancelar():
    prov = am.CompatProvider("http://x", "", "m")
    prov.cancel_flag = True
    assert prov._esperar(10) is False


def test_openrouter_401_mantiene_su_mensaje_y_no_reintenta(modelos):
    prov = am.OpenRouterProvider("sk-or-mala", "openrouter/auto")
    sesion = SesionFalsa([RespFalsa(status=401)])
    esperas = preparar(prov, sesion)

    res, _ = chatear(prov)

    assert res == "Error OpenRouter: API key inválida o revocada."
    assert len(sesion.posts) == 1 and esperas == []


def test_ollama_reintenta_conexion_pero_no_timeout_de_lectura(modelos):
    prov = am.OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    sesion = SesionFalsa([requests.exceptions.ConnectionError("x"), RespFalsa(ndjson("Hola"))])
    esperas = preparar(prov, sesion)
    res, _ = chatear(prov)
    assert res == "Hola" and esperas == [0.5]
    assert prov.ultimo_uso["salida"] == 4 and prov.ultimo_uso["tokens_por_segundo"] == 2.0

    prov2 = am.OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    sesion2 = SesionFalsa([requests.exceptions.ReadTimeout("300 s"), RespFalsa(ndjson("x"))])
    esperas2 = preparar(prov2, sesion2)
    res2, _ = chatear(prov2)
    assert len(sesion2.posts) == 1 and esperas2 == []
    assert "no respondió" in res2


def test_ollama_timeout_de_conexion_corto(modelos):
    modelos["ollama_timeout"] = 300
    prov = am.OllamaProvider("http://localhost:11434", "m")
    sesion = SesionFalsa([RespFalsa(ndjson("a"))])
    preparar(prov, sesion)
    chatear(prov)
    assert sesion.posts[0][1]["timeout"] == (am.OllamaProvider.TIMEOUT_CONEXION, 300)


# ── Parámetros de muestreo ─────────────────────────────────────────────────────

def test_sin_ajustes_nuevos_las_peticiones_no_cambian(modelos):
    """Mismo payload que antes de la IA avanzada: nada que no estuviera se envía."""
    o = am.OllamaProvider("http://localhost:11434", "m")
    so = SesionFalsa([RespFalsa(ndjson("a"))])
    preparar(o, so)
    chatear(o)
    assert so.posts[0][1]["json"]["options"] == {"num_ctx": 8192, "temperature": 0.7}
    assert so.posts[0][1]["json"]["keep_alive"] == "30m"

    r = am.OpenRouterProvider("sk-or", "openrouter/auto")
    sr = SesionFalsa([RespFalsa(sse("a"))])
    preparar(r, sr)
    chatear(r)
    carga = sr.posts[0][1]["json"]
    assert set(carga) == {"model", "messages", "stream", "temperature", "max_tokens", "usage"}
    assert carga["temperature"] == 0.7 and carga["max_tokens"] == 1024
    assert sr.posts[0][1]["headers"]["X-Title"] == "Lune CD"


def _preset_preciso(modelos):
    modelos.update({"preset_muestreo": "preciso", "seed": 42, "num_predict": 256,
                    "ollama_num_ctx": 16384})


def test_opciones_avanzadas_en_ollama(modelos):
    _preset_preciso(modelos)
    prov = am.OllamaProvider("http://localhost:11434", "m")
    sesion = SesionFalsa([RespFalsa(ndjson("a"))])
    preparar(prov, sesion)
    chatear(prov)
    assert sesion.posts[0][1]["json"]["options"] == {
        "num_ctx": 16384, "temperature": 0.2, "top_p": 0.9, "top_k": 40, "min_p": 0.05,
        "repeat_penalty": 1.1, "num_predict": 256, "seed": 42,
    }


def test_opciones_avanzadas_en_openrouter(modelos):
    _preset_preciso(modelos)
    prov = am.OpenRouterProvider("sk-or", "openrouter/auto")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["temperature"] == 0.2 and carga["top_p"] == 0.9
    assert carga["top_k"] == 40 and carga["min_p"] == 0.05
    assert carga["repetition_penalty"] == 1.1
    assert carga["seed"] == 42 and carga["max_tokens"] == 256
    assert carga["usage"] == {"include": True}


def test_opciones_en_compat_local_incluyen_las_extendidas(modelos):
    _preset_preciso(modelos)
    prov = am.CompatProvider("http://localhost:1234/v1", "", "m")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["top_k"] == 40 and carga["min_p"] == 0.05
    assert carga["repeat_penalty"] == 1.1 and "repetition_penalty" not in carga
    assert carga["max_tokens"] == 256 and carga["seed"] == 42


def test_opciones_en_compat_de_nube_solo_estandar(modelos):
    _preset_preciso(modelos)
    prov = am.CompatProvider("https://api.groq.com/openai/v1", "k", "m")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["temperature"] == 0.2 and carga["top_p"] == 0.9 and carga["seed"] == 42
    assert not {"top_k", "min_p", "repeat_penalty", "repetition_penalty"} & set(carga)
    assert carga["max_tokens"] == 256


def test_openai_usa_max_completion_tokens(modelos):
    prov = am.CompatProvider("https://api.openai.com/v1", "sk", "gpt-4o-mini")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["max_completion_tokens"] == 1024 and "max_tokens" not in carga
    assert carga["temperature"] == 0.7 and "reasoning_effort" not in carga


@pytest.mark.parametrize("modelo, razona", [
    ("gpt-5-mini", True), ("gpt-5", True), ("GPT-5.1", True), ("o3", True),
    ("o4-mini", True), ("o1", True), ("gpt-5-chat-latest", False),
    ("gpt-4o-mini", False), ("gpt-4.1", False), ("omni-moderation-latest", False), ("", False),
])
def test_es_razonamiento_openai(modelo, razona):
    assert am.es_razonamiento_openai(modelo) is razona


def test_openai_razonamiento_sin_temperatura(modelos):
    """o1/o3/o4 y gpt-5 dan 400 con temperature ≠ 1 o con top_p: no se mandan."""
    _preset_preciso(modelos)
    prov = am.CompatProvider("https://api.openai.com/v1", "sk", "gpt-5-mini")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert "temperature" not in carga and "top_p" not in carga
    assert carga["reasoning_effort"] == "low"
    assert carga["max_completion_tokens"] == 256 and carga["seed"] == 42


def test_razonamiento_solo_en_la_api_de_openai(modelos):
    """Un «gpt-5» servido por otro (proxy, Together…) recibe los campos de siempre."""
    prov = am.CompatProvider("http://localhost:4000/v1", "", "gpt-5-mini")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["temperature"] == 0.7 and "reasoning_effort" not in carga


def test_mistral_recibe_random_seed(modelos):
    modelos["seed"] = 42
    prov = am.CompatProvider("https://api.mistral.ai/v1", "k", "mistral-small-latest")
    sesion = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov, sesion)
    chatear(prov)
    carga = sesion.posts[0][1]["json"]
    assert carga["random_seed"] == 42 and "seed" not in carga
    assert carga["max_tokens"] == 1024

    modelos.pop("seed")
    prov2 = am.CompatProvider("https://api.mistral.ai/v1", "k", "mistral-small-latest")
    sesion2 = SesionFalsa([RespFalsa(sse("a"))])
    preparar(prov2, sesion2)
    chatear(prov2)
    assert not {"seed", "random_seed"} & set(sesion2.posts[0][1]["json"])


# ── Memoria del modelo local ───────────────────────────────────────────────────

def test_descargar_modelo_y_precalentar(modelos, monkeypatch):
    aux = SesionFalsa([RespFalsa()])
    monkeypatch.setattr(am, "_nueva_sesion", lambda: aux)
    prov = am.OllamaProvider("http://192.168.1.50:11434", "qwen2.5:7b")

    assert prov.descargar_modelo() is True
    url, kw = aux.posts[0]
    assert url == "http://192.168.1.50:11434/api/generate"
    assert kw["json"] == {"model": "qwen2.5:7b", "keep_alive": 0, "stream": False}

    assert prov.precalentar() is True
    kw = aux.posts[1][1]
    assert kw["json"]["keep_alive"] == "30m" and "prompt" not in kw["json"]

    assert am.OllamaProvider("http://x", "").descargar_modelo() is False
    aux.guion = [requests.exceptions.ConnectionError("off")]
    assert prov.precalentar() is False


def test_en_segundo_plano_entrega_el_resultado():
    recibido = []
    hilo = am.en_segundo_plano(lambda: 42, recibido.append)
    hilo.join(2)
    assert recibido == [42]


# ── AIManager ──────────────────────────────────────────────────────────────────

def test_manager_registra_compat_solo_con_url(modelos):
    assert "compat" not in am.AIManager().providers

    modelos.update({"compat_url": "http://localhost:1234/v1", "compat_model": "m"})
    mgr = am.AIManager()
    assert isinstance(mgr.providers["compat"], am.CompatProvider)
    assert mgr.providers["compat"].model == "m"

    anterior = mgr.providers
    modelos["compat_model"] = "otro"
    mgr.reload_provider()
    assert mgr.providers["compat"].model == "otro"

    modelos["compat_url"] = ""
    mgr.reload_provider()
    assert "compat" not in mgr.providers
    assert "compat" in anterior          # el dict viejo (sondeo en curso) no se muta


def test_probar_compat(modelos, monkeypatch):
    aux = SesionFalsa(guion_get=[RespFalsa(cuerpo=json.dumps(
        {"data": [{"id": "a"}, {"id": "b"}]}).encode())])
    monkeypatch.setattr(am, "_nueva_sesion", lambda: aux)
    modelos.update({"compat_url": "localhost:1234", "compat_model": "c"})

    r = am.AIManager().probar_compat()
    assert r["ok"] is True and r["modelos"] == ["a", "b"]
    assert r["url"] == "http://localhost:1234/v1/chat/completions"
    assert "no aparece" in r["mensaje"]
    assert isinstance(r["ms"], int) and r["ms"] >= 0      # latencia para la UI

    aux.guion_get = [RespFalsa(status=401)]
    r = am.CompatProvider("http://localhost:1234", "k", "").probar()
    assert r["ok"] is False and "clave" in r["mensaje"] and isinstance(r["ms"], int)
    aux.guion_get = [requests.exceptions.ConnectionError("off")]
    r = am.CompatProvider("http://localhost:1234", "k", "").probar()
    assert r["ok"] is False and r["ms"] is None and r["modelos"] == []
    r = am.CompatProvider("", "", "").probar()
    assert r["ok"] is False and r["ms"] is None and set(r) == {"ok", "mensaje", "modelos",
                                                              "url", "ms"}


def test_is_available_compat(monkeypatch):
    aux = SesionFalsa(guion_get=[RespFalsa(status=404)])
    monkeypatch.setattr(am, "_nueva_sesion", lambda: aux)
    assert am.CompatProvider("http://localhost:1234", "", "m").is_available() is True
    aux.guion_get = [RespFalsa(status=401)]
    assert am.CompatProvider("http://localhost:1234", "", "m").is_available() is False
    aux.guion_get = [requests.exceptions.ConnectionError("x")]
    assert am.CompatProvider("http://localhost:1234", "", "m").is_available() is False
    assert am.CompatProvider("", "", "m").is_available() is False


# ── Revisión cortes 2+3: conexión rechazada, tope total, 5xx de Ollama y claves ──

def test_conexion_rechazada_no_se_reintenta(modelos):
    """A3: nadie escucha en el puerto → un solo intento (antes 4 y ~11.7 s)."""
    prov = am.OllamaProvider("http://localhost:11434", "m")
    rechazada = requests.exceptions.ConnectionError(ConnectionRefusedError(10061, "rechazada"))
    sesion = SesionFalsa([rechazada, RespFalsa(ndjson("no"))])
    esperas = preparar(prov, sesion)
    res, _ = chatear(prov)
    assert len(sesion.posts) == 1 and esperas == []
    assert "no pude conectar" in res


def test_conexion_rechazada_de_verdad_falla_rapido(modelos):
    """Con un puerto cerrado de verdad (sin sesión falsa): un intento y pocos segundos."""
    import socket
    import time
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()                                           # nadie escucha ahí
    prov = am.OllamaProvider(f"http://127.0.0.1:{puerto}", "m")
    real = prov._session.post
    intentos = []
    prov._session.post = lambda *a, **k: (intentos.append(1), real(*a, **k))[1]
    inicio = time.monotonic()
    res, _ = chatear(prov)
    assert len(intentos) == 1 and "no pude conectar" in res
    assert time.monotonic() - inicio < 6


def test_tope_total_de_reintentos(modelos, monkeypatch):
    """A3: un equipo apagado (timeout de conexión de 5 s) no pasa de ~10 s en total."""
    prov = am.OllamaProvider("http://192.168.1.250:11434", "m")
    reloj = {"t": 0.0}
    monkeypatch.setattr(am.time, "monotonic", lambda: reloj["t"])

    def post(url, **kw):
        reloj["t"] += 5.0                               # cada intento agota los 5 s de conexión
        raise requests.exceptions.ConnectTimeout("apagado")
    sesion = SesionFalsa()
    sesion.post = post
    prov._session = sesion
    esperas = []

    def esperar(s):
        esperas.append(s)
        reloj["t"] += s
        return True
    prov._esperar = esperar
    res, _ = chatear(prov)
    assert esperas == [0.5]                             # 5 + 0.5 + 5 = 10.5 s, no ~24
    assert reloj["t"] <= am.TOPE_REINTENTOS_S + 5.5
    assert res.startswith(prov.ERROR)


@pytest.mark.parametrize("codigo, reintenta", [(500, False), (502, True), (503, True), (504, True)])
def test_ollama_solo_reintenta_502_503_504(modelos, codigo, reintenta):
    """D: un 500 de Ollama (p. ej. sin memoria) no se reenvía; el detalle llega al mensaje."""
    prov = am.OllamaProvider("http://localhost:11434", "m")
    cuerpo = json.dumps({"error": "model requires more system memory (9.1 GiB)"}).encode()
    sesion = SesionFalsa([RespFalsa(status=codigo, cuerpo=cuerpo), RespFalsa(ndjson("ya"))])
    esperas = preparar(prov, sesion)
    res, _ = chatear(prov)
    if reintenta:
        assert res == "ya" and esperas == [0.5]
    else:
        assert len(sesion.posts) == 1 and esperas == []
        assert res.startswith(prov.ERROR) and "HTTP 500" in res
        assert "more system memory" in res


def test_error_con_la_clave_no_la_muestra_ni_la_guarda(modelos):
    """Sospecha de fuga: requests.InvalidHeader lleva «Bearer <clave>» en el texto."""
    clave = "sk-or-v1-secreta1234567890\n"
    prov = am.OpenRouterProvider(clave, "openrouter/auto")
    error = requests.exceptions.InvalidHeader(
        f"Invalid leading whitespace, reserved character(s), or return character(s) in header "
        f"value: 'Bearer {clave}'")
    sesion = SesionFalsa([error])
    preparar(prov, sesion)
    res, _ = chatear(prov)
    assert res.startswith(prov.ERROR)
    assert "secreta1234567890" not in res and "Bearer ***" in res
    assert all("secreta" not in str(m.get("content")) for m in prov.conversation_history)


def test_ai_manager_redacta_la_clave_configurada(modelos, monkeypatch):
    monkeypatch.setattr(datos, "openrouter_key", lambda: "sk-or-v1-abcdefgh12345")
    monkeypatch.setattr(datos, "compat_key", lambda: "")
    ai = am.AIManager.__new__(am.AIManager)
    ai.providers = {}
    assert ai.redactar("fallo: Bearer sk-or-v1-abcdefgh12345") == "fallo: Bearer ***"
    assert "abcdefgh" not in ai.redactar("clave=sk-or-v1-abcdefgh12345")
    # En una respuesta normal solo se quitan los valores exactos, no la forma.
    assert am.redactar_secretos("Usa Authorization: Bearer TU_TOKEN", (), formas=False) == \
        "Usa Authorization: Bearer TU_TOKEN"
