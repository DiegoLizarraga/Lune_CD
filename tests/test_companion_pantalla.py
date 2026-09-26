"""
Tests del comentario de pantalla de la mascota (ui/companion.py) y de la
detección de visión del modelo local (servicios/ollama_client.soporta_vision).

Caso real que motivó esto: el chat local con Ollama iba bien, pero el modelo
(qwen2.5) es de solo texto, rechazaba la captura con un 400 y ese error acababa
escrito en la burbuja de la mascota. Ahora: se pregunta antes si el modelo ve; si
no ve, la nube (con clave) o Ollama en modo texto (ventana activa); y un error
del proveedor nunca se enseña tal cual.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── soporta_vision: formatos nuevo (capabilities) y viejo (families) ───────────

class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code}")
    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _sin_cache():
    from servicios import ollama_client
    ollama_client.olvidar_vision()
    yield
    ollama_client.olvidar_vision()


@pytest.mark.parametrize("respuesta, esperado", [
    ({"capabilities": ["completion", "tools"]}, False),                       # qwen2.5:7b real
    ({"capabilities": ["completion", "vision"]}, True),                       # llava / gemma3 en Ollama nuevo
    ({"details": {"family": "llama", "families": ["llama", "clip"]}}, True),  # Ollama viejo, llava
    ({"details": {"family": "qwen2", "families": ["qwen2"]}}, False),
    ({"details": {"family": "x", "families": ["x"]}, "model_info": {"llava.vision.image_size": 336}}, True),
    ({}, None),                                                               # sin datos: no se sabe
])
def test_soporta_vision_interpreta_api_show(monkeypatch, respuesta, esperado):
    from servicios import ollama_client
    llamadas = []
    monkeypatch.setattr(ollama_client._session, "post", lambda url, **kw: (llamadas.append((url, kw)), _Resp(respuesta))[1])
    assert ollama_client.soporta_vision("192.168.1.50", "m:latest") is esperado
    assert llamadas[0][0] == "http://192.168.1.50:11434/api/show"
    assert llamadas[0][1]["json"]["model"] == "m:latest"


def test_soporta_vision_cachea_y_tolera_fallos(monkeypatch):
    from servicios import ollama_client
    n = {"v": 0}
    def post(url, **kw):
        n["v"] += 1
        return _Resp({"capabilities": ["vision"]})
    monkeypatch.setattr(ollama_client._session, "post", post)
    assert ollama_client.soporta_vision("localhost", "a") is True
    assert ollama_client.soporta_vision("localhost", "a") is True
    assert n["v"] == 1                                    # la segunda vez sale de la caché
    assert ollama_client.soporta_vision("localhost", "") is None
    monkeypatch.setattr(ollama_client._session, "post", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
    assert ollama_client.soporta_vision("localhost", "b") is None
    ollama_client.marcar_sin_vision("localhost", "b")
    assert ollama_client.soporta_vision("localhost", "b") is False


# ── La mascota: qué proveedor y si manda captura ───────────────────────────────

pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="la mascota necesita PyQt6-WebEngine")


@pytest.fixture
def mascota(qapp, tmp_path, monkeypatch):
    """CompanionFlotante animado con la vista web falsa y un AIWorker que no arranca."""
    from PyQt6.QtCore import QObject, QUrl, pyqtSignal
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp
    from nucleo.config import Config

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []
        def setBackgroundColor(self, *_): pass
        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is not None: cb(None)

    class Ajustes:
        def setAttribute(self, *_): pass

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)
        def __init__(self):
            super().__init__(); self._pagina = Pagina(); self._url = QUrl()
        def page(self): return self._pagina
        def settings(self): return Ajustes()
        def setUrl(self, url): self._url = url
        def url(self): return self._url
        def focusProxy(self): return None

    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    cfg = Config(config_path=str(tmp_path / "config.json")); cfg.set("avatar", "render", "animado")
    c = comp.CompanionFlotante(cfg, ai_manager=object())
    lanzados = []
    monkeypatch.setattr(c, "_lanzar", lambda proveedor, con_imagen=True: lanzados.append((proveedor, con_imagen)))
    monkeypatch.setattr(c, "_capturar", lambda: "captura-base64")
    c.lanzados = lanzados
    yield c
    c.close()


def _js(c):
    return "\n".join(c.web.page().js)


def _comentar(c, auto=False, tope_s=5.0):
    """comentar_pantalla() (o el automático) y espera al sondeo de Ollama, que va en
    un hilo aparte (R9: el hilo de Qt no se congela)."""
    import time
    from PyQt6.QtWidgets import QApplication
    antes = len(c.lanzados)
    (c._comentar_auto if auto else c.comentar_pantalla)()
    fin = time.monotonic() + tope_s
    while len(c.lanzados) == antes and c._pensando and time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.005)


def _ollama(monkeypatch, *, modelo="qwen2.5:7b", responde=True, vision=None, nube=""):
    from nucleo import datos
    from servicios import ollama_client
    monkeypatch.setattr(datos, "ollama_model", lambda: modelo)
    monkeypatch.setattr(datos, "ollama_url", lambda: "http://192.168.1.50:11434")
    monkeypatch.setattr(datos, "openrouter_key", lambda: nube)
    monkeypatch.setattr(ollama_client, "listar_modelos", lambda url, timeout=6: (responde, ["x"], ""))
    monkeypatch.setattr(ollama_client, "soporta_vision", lambda url, modelo, timeout=6: vision)


def test_modelo_local_con_vision_manda_la_captura(mascota, monkeypatch):
    _ollama(monkeypatch, vision=True)
    _comentar(mascota)
    assert mascota.lanzados == [("ollama", True)] and mascota._b64 == "captura-base64"


def test_modelo_local_sin_vision_y_sin_nube_comenta_por_la_ventana(mascota, monkeypatch):
    _ollama(monkeypatch, vision=False, nube="")
    _comentar(mascota)
    assert mascota.lanzados == [("ollama", False)] and mascota._b64 is None
    assert "no ve imágenes" in _js(mascota)
    # el aviso se da una sola vez
    mascota._pensando = False
    _comentar(mascota)
    assert _js(mascota).count("no ve imágenes") == 1


def test_modelo_local_sin_vision_con_nube_usa_la_nube(mascota, monkeypatch):
    _ollama(monkeypatch, vision=False, nube="sk-or-xxx")
    _comentar(mascota)
    assert mascota.lanzados == [("openrouter", True)]


def test_vision_desconocida_se_intenta_en_local(mascota, monkeypatch):
    _ollama(monkeypatch, vision=None)
    _comentar(mascota)
    assert mascota.lanzados == [("ollama", True)]


def test_ollama_caido_cae_a_la_nube_si_hay_clave(mascota, monkeypatch):
    _ollama(monkeypatch, responde=False, nube="sk-or-xxx")
    _comentar(mascota)
    assert mascota.lanzados == [("openrouter", True)]
    assert "Ollama no responde" in _js(mascota)


def test_el_error_del_proveedor_no_va_a_la_burbuja(mascota, monkeypatch):
    """El 400 de Ollama por la imagen se reintenta en modo texto, sin enseñar el error."""
    _ollama(monkeypatch, vision=None, nube="")
    from servicios import ollama_client
    marcados = []
    monkeypatch.setattr(ollama_client, "marcar_sin_vision", lambda url, modelo: marcados.append(modelo))
    _comentar(mascota)
    assert mascota.lanzados == [("ollama", True)]
    mascota._provider_actual, mascota._con_imagen = "ollama", True
    mascota._on_comentario("Error Ollama: 400 Client Error: Bad Request for url: http://192.168.1.50:11434/api/chat")
    assert mascota.lanzados[-1] == ("ollama", False)
    assert marcados == ["qwen2.5:7b"]
    assert "400 Client Error" not in _js(mascota) and "no ve imágenes" in _js(mascota)
    # si el reintento también falla, Lune lo dice con gracia y deja de pensar
    mascota._provider_actual, mascota._con_imagen = "ollama", False
    mascota._on_comentario("Error Ollama: no pude conectar")
    assert "algo falló" in _js(mascota) and mascota._pensando is False
    assert "Error Ollama" not in _js(mascota)


def test_un_error_con_nube_reintenta_en_la_nube(mascota, monkeypatch):
    _ollama(monkeypatch, vision=None, nube="sk-or-xxx")
    _comentar(mascota)
    mascota._provider_actual, mascota._con_imagen = "ollama", True
    mascota._on_error("timeout")
    assert mascota.lanzados[-1] == ("openrouter", True)


def test_prompt_de_ventana_y_contexto():
    from ui.companion import _PROMPT_VENTANA, _contexto_ventana, _es_error, _parece_sin_vision
    assert isinstance(_contexto_ventana(), str)
    assert "{contexto}" in _PROMPT_VENTANA
    assert _es_error("Error Ollama: 400") and _es_error("Error OpenRouter: 401") and not _es_error("Hola, todo bien")
    assert _parece_sin_vision("400 Client Error") and _parece_sin_vision("this model does not support images")
    assert not _parece_sin_vision("no pude conectar")


# ── Arreglos de la revisión 2+3: S6 (automáticos sin nube), R9 (sin congelar), S1 ──

def test_comentario_automatico_nunca_sube_la_captura_a_la_nube(mascota, monkeypatch):
    # Modelo local sin visión y con nube: el MANUAL usa la nube con captura…
    _ollama(monkeypatch, vision=False, nube="sk-or-xxx")
    _comentar(mascota)
    assert mascota.lanzados[-1] == ("openrouter", True)
    # …el AUTOMÁTICO comenta en local por la ventana activa (texto).
    mascota._pensando = False
    _comentar(mascota, auto=True)
    assert mascota.lanzados[-1] == ("ollama", False) and mascota._b64 is None
    # Ollama caído: el automático va a la nube SIN imagen y sin avisar cada vez.
    _ollama(monkeypatch, responde=False, nube="sk-or-xxx")
    mascota._pensando = False
    mascota.web.page().js.clear()
    _comentar(mascota, auto=True)
    assert mascota.lanzados[-1] == ("openrouter", False) and mascota._b64 is None
    assert "Ollama no responde" not in _js(mascota)
    # Sin modelo local: igual.
    _ollama(monkeypatch, modelo="", nube="sk-or-xxx")
    mascota._pensando = False
    _comentar(mascota, auto=True)
    assert mascota.lanzados[-1] == ("openrouter", False)


def test_reintento_del_automatico_no_sube_la_captura(mascota, monkeypatch):
    """Ollama rechaza la imagen en un automático: se reintenta en local en texto, no en la nube."""
    _ollama(monkeypatch, vision=None, nube="sk-or-xxx")
    from servicios import ollama_client
    monkeypatch.setattr(ollama_client, "marcar_sin_vision", lambda url, modelo: None)
    _comentar(mascota, auto=True)
    assert mascota.lanzados[-1] == ("ollama", True)                # local con visión: se intenta
    mascota._provider_actual, mascota._con_imagen = "ollama", True
    mascota._on_comentario("Error Ollama: 400 Client Error: this model does not support images")
    assert mascota.lanzados[-1] == ("ollama", False)


def test_el_temporizador_lanza_el_automatico(mascota):
    llamados = []
    mascota._comentar = lambda automatico: llamados.append(automatico)
    mascota._timer.timeout.emit()
    mascota.comentar_pantalla()
    assert llamados == [True, False]


def test_el_sondeo_de_ollama_no_congela_el_hilo_de_qt(mascota, monkeypatch):
    import time
    from servicios import ollama_client
    _ollama(monkeypatch, vision=True)
    monkeypatch.setattr(ollama_client, "listar_modelos",
                        lambda url, timeout=6: (time.sleep(0.6), (True, ["x"], ""))[1])
    t0 = time.monotonic()
    mascota.comentar_pantalla()
    assert time.monotonic() - t0 < 0.3                  # antes: hasta 3 + 3 s con Ollama apagado
    assert mascota._pensando and mascota.lanzados == []  # pensando mientras pregunta
    _esperar = time.monotonic() + 5
    from PyQt6.QtWidgets import QApplication
    while not mascota.lanzados and time.monotonic() < _esperar:
        QApplication.processEvents(); time.sleep(0.01)
    assert mascota.lanzados == [("ollama", True)]


def test_el_comentario_de_pantalla_es_efimero_y_automatico_sin_imagen_a_la_nube(mascota, monkeypatch):
    """_lanzar de verdad: AIWorker con efimero=True (el título de la ventana no entra en
    el historial del chat) y, si es automático, nunca con imagen hacia la nube."""
    from PyQt6.QtCore import QObject, pyqtSignal
    import servicios.ai_worker as aw
    import ui.companion as comp

    creados = []

    class WorkerFalso(QObject):
        response_ready = pyqtSignal(str)
        error_occurred = pyqtSignal(str)

        def __init__(self, ai, prompt, provider, **kw):
            super().__init__()
            self.provider, self.kw = provider, kw
            creados.append(self)

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(aw, "AIWorker", WorkerFalso)
    c = mascota
    c._b64, c._automatico = "captura", False
    comp.CompanionFlotante._lanzar(c, "openrouter", True)
    assert creados[-1].kw["efimero"] is True and creados[-1].kw["imagenes"] == ["captura"]
    assert creados[-1].kw["origen"] == "no_confiable" and creados[-1].kw["permitir_acciones"] is False
    c._automatico = True
    comp.CompanionFlotante._lanzar(c, "openrouter", True)
    assert creados[-1].kw["imagenes"] == [] and c._con_imagen is False
    comp.CompanionFlotante._lanzar(c, "ollama", True)
    assert creados[-1].kw["imagenes"] == ["captura"]              # a Ollama (local) sí
