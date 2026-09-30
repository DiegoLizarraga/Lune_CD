"""
Arreglos de la revisión de los cortes 2+3 en la piel web y las asistentes
(ui/web_bridge.py, ui/companion.py, ui/avatar_overlay.py, ui/lune_face.py).

  · Seguridad: get_config no da las claves en claro (máscara + «configurada»);
    guardar/probar con la máscara conservan la guardada (la de la API compatible,
    solo con su URL); resolver_aprobacion solo contesta lo que se preguntó a la
    página; personaje_vrm y vrm_archivo solo aceptan modelos de modelo_vrm/; lo que
    pides con tus palabras («abre youtube», «lanza calc») pasa por el Ejecutor.
  · Funcional: voz y caras con la asistente oculta, resultado de acciones en la
    burbuja, «duérmete» con tramos de voz largos, borrar el último modelo 3D,
    Detener, esperas sin anidar, eventos de estado viejos, VRM oculta liberada.
  · Arranque: guardar Ajustes no pisa la voz global ni recorta el contexto; un
    vrm_archivo obsoleto no avisa en cada guardado.
  · Sprites: vídeo centrado como el sprite, máscara donde Qt pinta, etiqueta pegada
    a la figura, posición lógica (sin el salto del margen), vuelta a normal.

Sin red ni pantalla (offscreen); vista web falsa que anota el JS.
"""
import copy
import json
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
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal  # noqa: E402



def vrm_minimo() -> bytes:
    """GLB mínimo con la extensión VRMC_vrm (lo que nucleo/vrm.py valida)."""
    import struct
    js = json.dumps({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                     "extensions": {"VRMC_vrm": {"meta": {"name": "Luna", "authors": ["Diego"]}}}}).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js))
            + struct.pack("<II", len(js), 0x4E4F534A) + js)


# ── Falsos ─────────────────────────────────────────────────────────────────────

def destruir(w):
    """Cierra y borra DE VERDAD un widget del test (sin dejar temporizadores vivos que
    salten luego en otro test): close + deleteLater + los DeferredDelete pendientes."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    try:
        w.close()
        w.deleteLater()
    except RuntimeError:
        return
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


class VozFalsa:
    def __init__(self):
        self._enabled = False
        self.available = False
        self.on_error = None
        self.al_hablar = None
        self.reinicios = 0

    def cancelar(self):
        pass

    def invalidar_params(self):
        pass

    def reiniciar_motor(self):
        self.reinicios += 1


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
    creados = []

    def __init__(self, ai, message, provider_id, **kw):
        super().__init__()
        self.ai, self.message, self.provider_id, self.kw = ai, message, provider_id, kw
        self.corriendo = False
        WorkerFalso.creados.append(self)

    def start(self):
        self.corriendo = True

    def isRunning(self):
        return self.corriendo


class AsistenteFalsa:
    def __init__(self, visible=True):
        self.cerrado = False
        self.visible = visible
        self.textos, self.fines, self.hablando, self.estados = [], [], [], []

    def isVisible(self):
        return self.visible

    def frameGeometry(self):
        return QRect(50, 60, 200, 300)

    def set_estado(self, estado, ms=0):
        self.estados.append(estado)

    def set_hablando(self, on):
        self.hablando.append(on)

    def burbuja_texto(self, t, tipeado=False):
        self.textos.append(t)

    def burbuja_fin(self, ms=None):
        self.fines.append(ms)

    def recargar_modelo(self):
        pass


DATOS = {
    "apis": {"openrouter_key": "sk-or-SECRETA", "telegram_token": "123:TG-SECRETO"},
    "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": "m",
                "compat_url": "https://api.groq.com/openai/v1", "compat_key": "gsk-SECRETA",
                "compat_model": "llama"},
    "bot": {"personaje_default": "Lune"},
    "personajes": [{"nombre": "Lune", "systemPrompt": "Eres Lune."}],
}


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps(DATOS), "utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


@pytest.fixture
def puente(qapp, tmp_path, monkeypatch, datos_tmp):
    from nucleo.config import Config
    from servicios import tools as T
    from servicios.tools import ToolManager, ToolResult
    from ui.web_bridge import LuneBridge
    urls, lanzadas = [], []
    monkeypatch.setattr(T.webbrowser, "open", lambda u, *a, **k: urls.append(u) or True)
    tm = ToolManager()
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, f"Abrí {n}"))
    memoria = MagicMock()
    memoria.procesar_mensaje_usuario.return_value = None
    memoria.obtener_contexto_para_prompt.return_value = ""
    programados = []                                   # temporizadores de caducidad del Ejecutor
    b = LuneBridge(config=Config(str(tmp_path / "config.json")), ai_manager=AIFalso(),
                   memoria=memoria, tools=tm, voice=VozFalsa(),
                   opciones_acciones={"audit_path": None,
                                      "programar": lambda s, fn: programados.append(fn) or MagicMock()})
    b.programados = programados
    senales = {n: [] for n in ("done", "herramienta", "aprobacion_pedida", "aprobacion_resuelta",
                               "aviso", "estado", "personaje_cambio")}
    for n, lista in senales.items():
        getattr(b, n).connect(lambda *a, l=lista: l.append(a if len(a) != 1 else a[0]))
    b._ventana_a_la_vista = lambda: True
    b.urls, b.lanzadas, b.senales = urls, lanzadas, senales
    yield b
    b.cerrar_escritorio()
    b.deleteLater()


def _turno(b, asistente=False):
    from servicios.tools import ctx_acciones
    b._turno = {"origen": "usuario", "ctx": ctx_acciones(b.ai, "ollama", "normal"), "asistente": asistente}


# ── S2: claves, aprobaciones y rutas ───────────────────────────────────────────

def test_get_config_no_da_las_claves_en_claro(puente):
    from ui.web_bridge import MASCARA_CLAVE
    texto = puente.get_config()
    assert "SECRET" not in texto and "sk-or" not in texto and "gsk-" not in texto
    cfg = json.loads(texto)
    assert cfg["openrouter_key"] == cfg["telegram_token"] == cfg["compat_key"] == MASCARA_CLAVE
    assert cfg["openrouter_key_configurada"] and cfg["telegram_token_configurado"] and cfg["compat_key_configurada"]


def test_guardar_con_la_mascara_conserva_y_lo_escrito_se_guarda(puente):
    from nucleo import datos
    b = puente
    cfg = json.loads(b.get_config())
    assert json.loads(b.guardar_config(json.dumps(cfg)))["ok"] is True     # Ajustes reenvía todo
    datos.invalidar()
    assert datos.openrouter_key() == "sk-or-SECRETA" and datos.telegram_token() == "123:TG-SECRETO"
    assert datos.compat_key() == "gsk-SECRETA"
    # con algo tecleado encima de los puntos: sigue siendo la guardada (una clave no los lleva)
    b.guardar_config(json.dumps({"openrouter_key": cfg["openrouter_key"] + "x"}))
    datos.invalidar()
    assert datos.openrouter_key() == "sk-or-SECRETA"
    b.guardar_config(json.dumps({"openrouter_key": " sk-or-NUEVA ", "telegram_token": ""}))
    datos.invalidar()
    assert datos.openrouter_key() == "sk-or-NUEVA" and datos.telegram_token() == ""
    assert json.loads(b.get_config())["telegram_token"] == ""


def test_la_clave_compat_no_viaja_a_otra_url(puente):
    from nucleo import datos
    b = puente
    cfg = json.loads(b.get_config())
    b.guardar_config(json.dumps({"compat_url": "https://malo.example/v1", "compat_key": cfg["compat_key"]}))
    datos.invalidar()
    assert datos.compat_url() == "https://malo.example/v1" and datos.compat_key() == ""
    assert any("vuelve a escribir su clave" in a for a in b.senales["aviso"])
    # con la clave escrita a la vez, sí
    b.guardar_config(json.dumps({"compat_url": "https://api.groq.com/openai/v1", "compat_key": "gsk-OTRA"}))
    datos.invalidar()
    assert datos.compat_key() == "gsk-OTRA"


def test_probar_conexion_con_la_mascara_usa_la_guardada_solo_en_su_url(puente, monkeypatch):
    from ui.web_bridge import MASCARA_CLAVE
    from servicios import ai_manager
    usadas = []
    monkeypatch.setattr(ai_manager.CompatProvider, "probar",
                        lambda self: usadas.append((self.base_url, getattr(self, "api_key", None)
                                                    or getattr(self, "key", None))) or {"ok": True})
    b = puente
    b.compat_borrador(json.dumps({"compat_url": "https://api.groq.com/openai/v1",
                                  "compat_key": MASCARA_CLAVE, "compat_model": "llama"}))
    assert b._compat_borrador[1] == "gsk-SECRETA"
    b.compat_borrador(json.dumps({"compat_url": "https://malo.example/v1",
                                  "compat_key": MASCARA_CLAVE, "compat_model": "llama"}))
    assert b._compat_borrador[1] == ""
    assert json.loads(b.compat_probar())["ok"] is True


def test_resolver_aprobacion_solo_lo_que_se_pregunto_a_la_pagina(puente, monkeypatch):
    import ui.aprobacion_qt as aq
    dialogos = []

    class Dialogo(QObject):
        resuelto = pyqtSignal(bool)

        def __init__(self, herramienta, resumen="", args=None, **kw):
            super().__init__()
            self.id = kw.get("id_aprobacion")
            dialogos.append(self)

        def mostrar_junto_a(self, rect):
            pass

        def descartar(self):
            pass

    monkeypatch.setattr(aq, "DialogoAprobacion", Dialogo)
    b = puente
    b._ventana_a_la_vista = lambda: False                  # pregunta junto a la asistente
    _turno(b)
    b._on_done('<|CALL ["lanzar_app", {"app": "calc"}]|>')
    assert len(dialogos) == 1 and b.senales["aprobacion_pedida"] == []
    pid = b.acciones.pendientes()[0]["id"]
    assert b.resolver_aprobacion(pid, True) is False        # no se le preguntó a la página
    assert b.resolver_aprobacion("inventado", True) is False
    assert b.lanzadas == [] and b.acciones.pendientes()
    # la que sí se preguntó a la página, sí
    b._ventana_a_la_vista = lambda: True
    b._on_done('<|CALL ["lanzar_app", {"app": "notepad"}]|>')
    p = json.loads(b.senales["aprobacion_pedida"][-1])
    assert b.resolver_aprobacion(p["id"], True) is True and b.lanzadas == ["notepad"]


def test_personaje_vrm_y_vrm_archivo_rechazan_rutas_unc_y_de_fuera(puente, tmp_path, monkeypatch):
    from nucleo import vrm
    carpeta = tmp_path / "modelo_vrm"
    carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(vrm_minimo())
    fuera = tmp_path / "fuera.vrm"
    fuera.write_bytes(vrm_minimo())
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    tocadas = []
    real = vrm.resolver
    monkeypatch.setattr(vrm, "resolver", lambda n: tocadas.append(n) or real(n))
    b = puente
    for malo in ("\\\\atacante\\s\\a.vrm", "//atacante/s/a.vrm", str(fuera), "..\\a.vrm", "C:a.vrm"):
        r = json.loads(b.personaje_vrm("Lune", malo))
        assert r["ok"] is False, malo
        b.guardar_config(json.dumps({"vrm_archivo": malo}))
        assert b.config.get("avatar", "vrm_archivo", "") == "", malo
    assert tocadas == []                                    # ni un is_file() sobre la ruta
    assert json.loads(b.personaje_vrm("Lune", "a.vrm"))["ok"] is True
    b.guardar_config(json.dumps({"vrm_archivo": "a.vrm"}))
    assert b.config.get("avatar", "vrm_archivo") == "a.vrm"


# ── S5: lo que pides con tus palabras pasa por el Ejecutor ─────────────────────

def test_abre_youtube_por_el_ejecutor_y_lanza_pide_permiso(puente):
    b = puente
    b.enviar("abre youtube", "local")
    assert b.urls == ["https://www.youtube.com"]
    assert b.senales["done"][-1] == ("", "happy") and b.senales["herramienta"][-1][0] is True
    assert b._turno["ctx"]["ai"] is b.ai                      # ctx de ctx_acciones (taint)
    b.enviar("lanza calc", "local")                            # también lo del modo llamada
    assert b.lanzadas == [] and len(b.senales["aprobacion_pedida"]) == 1
    p = json.loads(b.senales["aprobacion_pedida"][-1])
    assert p["herramienta"] == "lanzar_app"
    assert b.resolver_aprobacion(p["id"], True) is True and b.lanzadas == ["calc"]


# ── Funcional: asistente oculta, burbuja, Detener, esperas ───────────────────────

def test_la_voz_llega_a_la_asistente_aunque_este_oculta(puente):
    b = puente
    ov = AsistenteFalsa(visible=False)
    b._overlay = ov
    b._on_hablando(True)
    b._on_hablando(False)
    assert ov.hablando == [True, False]


def test_el_eco_no_sale_con_la_asistente_oculta(puente):
    b = puente
    ov = AsistenteFalsa(visible=False)
    b._overlay = ov
    _turno(b, asistente=True)
    b._eco_asistente("hola", fin=True)
    assert ov.textos == [] and ov.fines == []
    ov.visible = True
    b._eco_asistente("hola", fin=True)
    assert ov.textos == ["hola"]


def test_el_resultado_de_una_accion_sale_en_la_burbuja_de_la_asistente(puente):
    b = puente
    ov = AsistenteFalsa()
    b._overlay = ov
    _turno(b, asistente=True)
    b._on_done('Te lo abro. <|CALL ["abrir_url", {"url": "https://www.youtube.com"}]|>')
    assert ov.textos[-1].startswith("Te lo abro.") and "\n✓ " in ov.textos[-1]
    # rechazada: ✕ debajo
    b._on_done('Va. <|CALL ["lanzar_app", {"app": "calc"}]|>')
    p = json.loads(b.senales["aprobacion_pedida"][-1])
    b._turno["asistente"] = True
    b.resolver_aprobacion(p["id"], False)
    assert "\n✕ " in ov.textos[-1] and ov.textos[-1].startswith("Va.")
    # turno de la ventana: nada en la burbuja
    n = len(ov.textos)
    _turno(b, asistente=False)
    b._on_done('<|CALL ["abrir_url", {"url": "https://www.google.com"}]|>')
    assert len(ov.textos) == n


def test_enviar_con_el_worker_viejo_vivo_no_deja_la_pagina_pensando(puente, monkeypatch):
    import ui.web_bridge as wb
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    b = puente
    b.enviar("cuéntame algo largo", "local")
    b.detener()                                              # el worker sigue vivo
    n = len(b.senales["done"])
    b.enviar("otra cosa", "local")
    assert len(WorkerFalso.creados) == 1
    assert len(b.senales["done"]) == n + 1 and b.senales["done"][-1][0] == b.AVISO_OCUPADA
    assert b.senales["estado"][-1] == "live"


def test_esperar_en_hilo_no_se_anida_y_respeta_el_tope(puente):
    from ui.web_bridge import OCUPADO
    b = puente
    dentro = []
    suelta = threading.Event()

    def lenta():
        suelta.wait(5)
        return "fuera"

    from PyQt6.QtCore import QTimer
    # mientras espera la de fuera, llega otra llamada (la página pide otra prueba)
    QTimer.singleShot(50, lambda: (dentro.append(b._esperar_en_hilo(lambda: "dentro", 5.0)), suelta.set()))
    t0 = time.monotonic()
    r = b._esperar_en_hilo(lenta, 5.0)
    assert r == "fuera" and dentro == [OCUPADO] and time.monotonic() - t0 < 2
    # tope: no espera más de lo pedido
    t0 = time.monotonic()
    assert b._esperar_en_hilo(lambda: time.sleep(2) or 1, 0.2) is None
    assert time.monotonic() - t0 < 1.0
    assert json.loads(b.compat_probar()).get("mensaje")        # y vuelve a estar libre


def test_la_cuenta_atras_la_cierra_el_backend_como_caducada(puente):
    """El modal ya no llama a resolver_aprobacion al llegar a 0: el Ejecutor la da por
    CADUCADA, avisa a la página (aprobacion_resuelta) y lo dice en el chat."""
    b = puente
    _turno(b)
    b._on_done('<|CALL ["lanzar_app", {"app": "calc"}]|>')
    pid = json.loads(b.senales["aprobacion_pedida"][-1])["id"]
    assert b.programados
    b.programados[-1]()                                       # pasan los 60 s
    assert pid in b.senales["aprobacion_resuelta"] and b.lanzadas == []
    ok, _i, _t, detalle = b.senales["herramienta"][-1]
    assert ok is False and "Nadie respondió" in detalle           # CADUCADA, no «rechazada»
    assert b.resolver_aprobacion(pid, True) is False


def test_vaciar_la_clave_compat_borra_tambien_el_alias(puente):
    from nucleo import datos
    d = datos.cargar()
    d["apis"]["compat_key"] = "alias-VIEJA"
    datos.guardar(d)
    puente.guardar_config(json.dumps({"compat_key": ""}))
    datos.invalidar()
    assert datos.compat_key() == "" and "compat_key" not in datos.cargar()["apis"]


def test_personaje_inexistente_se_explica(puente, monkeypatch):
    from nucleo import personajes

    def set_activo(n):
        raise ValueError(f"No existe el personaje «{n}». Personajes: Lune")

    monkeypatch.setattr(personajes, "set_activo", set_activo)
    assert puente.personaje_activar("Luen") is False
    assert puente.senales["aviso"][-1].startswith("No existe el personaje «Luen»")
    assert puente.senales["personaje_cambio"] == []


def test_personaje_activar_avisa_a_la_barra(puente, monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "set_activo", lambda n: None)
    assert puente.personaje_activar("Lune") is True
    assert puente.senales["personaje_cambio"] == ["Lune"]


# ── Arranque A1/A2/A4 ──────────────────────────────────────────────────────────

CLAVES_VOZ = ("motor_salida", "edge_voz", "edge_rate", "edge_pitch", "gtts_tld", "kokoro_voz")


def _con_voz_propia(voz):
    from nucleo import datos
    d = datos.cargar()
    d["personajes"][0]["voz"] = voz
    datos.guardar(d)


def test_guardar_ajustes_sin_tocar_la_voz_no_pisa_la_global_ni_el_personaje(puente):
    from nucleo import datos, personajes
    b = puente
    b.config.set("voz", "motor_salida", "kokoro")
    b.config.set("voz", "kokoro_voz", "ef_dora")
    _con_voz_propia({"motor": "edge", "id": "es-MX-JorgeNeural"})
    cfg = json.loads(b.get_config())
    assert cfg["edge_voz"] == "es-MX-JorgeNeural" and cfg["motor_salida"] == "edge"
    globales = {k: b.config.get("voz", k, None) for k in CLAVES_VOZ}
    b.guardar_config(json.dumps(cfg))                          # «Guardar» sin tocar la voz
    assert b.config.get("voz", "motor_salida") == "kokoro"     # la global sigue igual
    assert {k: b.config.get("voz", k, None) for k in CLAVES_VOZ} == globales
    datos.invalidar()
    assert personajes.get_activo()["voz"] == {"motor": "edge", "id": "es-MX-JorgeNeural"}
    assert b.voice.reinicios == 0
    # cambiar solo la velocidad: va al personaje (solo rate), la global no se toca
    cfg["edge_rate"] = "+20%"
    b.guardar_config(json.dumps(cfg))
    datos.invalidar()
    assert personajes.get_activo()["voz"] == {"motor": "edge", "id": "es-MX-JorgeNeural", "rate": "+20%"}
    assert {k: b.config.get("voz", k, None) for k in CLAVES_VOZ} == globales and b.voice.reinicios == 1


def test_sin_voz_propia_solo_se_escribe_lo_que_cambio(puente):
    b = puente
    b.config.set("voz", "edge_voz", "")                        # vacía: suena la de por defecto
    cfg = json.loads(b.get_config())
    antes = {k: b.config.get("voz", k, None) for k in CLAVES_VOZ}
    b.guardar_config(json.dumps(cfg))
    assert {k: b.config.get("voz", k, None) for k in CLAVES_VOZ} == antes   # nada fijado de más
    assert b.voice.reinicios == 0
    cfg["edge_pitch"] = "-5Hz"
    b.guardar_config(json.dumps(cfg))
    despues = {k: b.config.get("voz", k, None) for k in CLAVES_VOZ}
    assert despues == {**antes, "edge_pitch": "-5Hz"} and b.voice.reinicios == 1


def test_contexto_de_ollama_sin_recortar_ni_tocar_si_no_cambia(puente):
    from nucleo import datos
    b = puente
    d = datos.cargar()
    d["modelos"]["ollama_num_ctx"] = 65536                     # /ctx 64k en patata
    datos.guardar(d)
    cfg = json.loads(b.get_config())
    assert cfg["ollama_num_ctx"] == 65536
    b.guardar_config(json.dumps(cfg))
    datos.invalidar()
    assert datos.ollama_num_ctx() == 65536
    d = datos.cargar()
    del d["modelos"]["ollama_num_ctx"]
    datos.guardar(d)
    b.guardar_config(json.dumps({"ollama_num_ctx": 8192}))     # el efectivo por defecto: no se escribe
    assert "ollama_num_ctx" not in datos.cargar()["modelos"]
    b.guardar_config(json.dumps({"ollama_num_ctx": 100}))
    datos.invalidar()
    assert datos.ollama_num_ctx() == 512


def test_vrm_archivo_obsoleto_no_avisa_en_cada_guardado(puente):
    b = puente
    b.config.set("avatar", "vrm_archivo", "borrado.vrm")
    b.guardar_config(json.dumps({"vrm_archivo": "borrado.vrm"}))
    assert not any("No encuentro el modelo" in a for a in b.senales["aviso"])
    b.guardar_config(json.dumps({"vrm_archivo": "otro_que_no_esta.vrm"}))
    assert any("No encuentro el modelo" in a for a in b.senales["aviso"])


# ── Asistente web (companion.py) ─────────────────────────────────────────────────

@pytest.fixture
def web_falso(monkeypatch):
    if not HAY_WEBENGINE:
        pytest.skip("la asistente web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Estado:
        Active, Frozen, Discarded = 0, 1, 2

    class Pagina(QObject):
        LifecycleState = Estado

        def __init__(self):
            super().__init__(); self.js = []; self.cola = []; self.estado = Estado.Active

        def setBackgroundColor(self, *_):
            pass

        def lifecycleState(self):
            return self.estado

        def setLifecycleState(self, e):
            self.estado = e

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                self.pendiente = cb                     # la respuesta llega cuando el test quiera
            else:
                cb(None)

    class Ajustes:
        def setAttribute(self, *_):
            pass

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
    return FalsoWeb


@pytest.fixture
def lune_activa(monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})


def _companion(tmp_path, render="animado"):
    from nucleo.config import Config
    from ui.companion import CompanionFlotante
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", render)
    c = CompanionFlotante(cfg, ai_manager=None)
    c._aparecer_pendiente = False
    c.show()
    c._on_cargado(True)
    return c


def _js(c):
    return "\n".join(c.web.page().js)


def test_companion_hablando_oculta_no_se_queda_pegado(qapp, tmp_path, web_falso, lune_activa):
    c = _companion(tmp_path)
    try:
        c.set_hablando(True)
        c.hide()
        c.set_hablando(False)                                  # la voz acaba con ella oculta
        assert c._hablando is False and not c._motivo_no_dormir()
        c.web.page().js.clear()
        c.show()
        assert "window.luneSpeak && window.luneSpeak(false)" in _js(c)   # la página se resincroniza
    finally:
        destruir(c)


def test_companion_ocultar_a_mitad_de_respuesta_no_deja_typing(qapp, tmp_path, web_falso, lune_activa):
    c = _companion(tmp_path)
    try:
        c.set_estado("typing")
        assert c._motivo_no_dormir()                           # escribiendo: no se duerme
        c.hide()
        c.show()
        assert c._estado_visual == "normal" and not c._motivo_no_dormir()
    finally:
        destruir(c)


def test_companion_duermete_no_caduca_con_un_tramo_de_voz_largo(qapp, tmp_path, web_falso, lune_activa,
                                                                monkeypatch):
    import ui.companion as comp
    reloj = [1000.0]
    monkeypatch.setattr(comp.time, "monotonic", lambda: reloj[0])
    c = _companion(tmp_path)
    try:
        c.set_hablando(True)
        assert c.dormir() is True and not c.durmiendo          # se dormirá al callar
        reloj[0] += comp.GRACIA_SUENO_S + 30                   # un tramo de voz de 60 s
        c.set_hablando(False)
        assert c._timer_sueno_pedido.isActive()
        c._volver_a_dormir()
        assert c.durmiendo
    finally:
        destruir(c)


def test_companion_borrar_el_ultimo_modelo_recrea_la_asistente(qapp, tmp_path, web_falso, lune_activa,
                                                            monkeypatch):
    from nucleo import vrm
    carpeta = tmp_path / "modelo_vrm"
    carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(vrm_minimo())
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    c = _companion(tmp_path, render="vrm")
    try:
        assert c.render == "vrm"
        recreada = []
        c.recrear.connect(lambda: recreada.append(True))
        (carpeta / "a.vrm").unlink()
        c.recargar_modelo()
        assert recreada == [True]
    finally:
        destruir(c)


def test_companion_estado_viejo_de_la_pagina_no_pisa_una_emocion_nueva(qapp, tmp_path, web_falso, lune_activa):
    from nucleo.estado_asistente import BusEstado
    c = _companion(tmp_path)
    try:
        bus = BusEstado()
        c.set_bus_estado(bus)
        pag = c.web.page()
        c._eventos_en_vuelo = 0.0
        c._vaciar_eventos()                                   # sale la petición de eventos…
        c.set_estado("happy")                                 # …y Python pide otra cara
        pag.pendiente(json.dumps([{"t": "estado", "d": {"nombre": "normal"}}]))   # lote de antes
        assert c._estado_visual == "happy" and bus.actual().emocion == "happy"
        c._vaciar_eventos()                                   # lote nuevo: ya cuenta
        pag.pendiente(json.dumps([{"t": "estado", "d": {"nombre": "normal"}}]))
        assert c._estado_visual == "normal" and bus.actual().emocion == "neutral"
    finally:
        destruir(c)


def test_companion_vrm_oculta_un_rato_libera_la_pagina(qapp, tmp_path, web_falso, lune_activa, monkeypatch):
    from nucleo import vrm
    carpeta = tmp_path / "modelo_vrm"
    carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(vrm_minimo())
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    c = _companion(tmp_path, render="vrm")
    try:
        pag = c.web.page()
        c.hide()
        assert c._timer_liberar.isActive()
        c._liberar_pagina()                                   # pasó LIBERAR_OCULTA_MS
        assert pag.estado == pag.LifecycleState.Discarded and not c._pagina_lista
        c.show()
        assert pag.estado == pag.LifecycleState.Active and not c._timer_liberar.isActive()
        # la animada no se libera (no tiene WebGL)
    finally:
        destruir(c)


# ── Asistente de sprites (avatar_overlay.py / lune_face.py) ──────────────────────

@pytest.fixture
def sprites(qapp, lune_activa):
    from ui.avatar_overlay import AvatarOverlay
    ov = AvatarOverlay(config=None)
    ov.show()
    for _ in range(3):
        qapp.processEvents()
    yield ov
    destruir(ov)


def test_sprites_voz_y_typing_con_la_asistente_oculta(sprites):
    ov = sprites
    ov.set_hablando(True)
    ov.set_estado("typing")
    ov.hide()
    ov.set_hablando(False)
    assert ov._hablando is False and ov._base[0] == "normal"
    ov.show()
    assert not ov._motivo_no_dormir()


def test_sprites_burbuja_no_reaparece_oculta(sprites):
    ov = sprites
    ov.hide()
    ov.burbuja_texto("respuesta en streaming")
    assert ov._burbuja is None or not ov._burbuja.isVisible()


def test_sprites_duermete_no_caduca_con_voz_larga(sprites, monkeypatch):
    import ui.avatar_overlay as ao
    reloj = [5000.0]
    monkeypatch.setattr(ao.time, "monotonic", lambda: reloj[0])
    ov = sprites
    ov.set_hablando(True)
    assert ov.dormir() is True
    reloj[0] += ao.GRACIA_SUENO_S + 30
    ov.set_hablando(False)
    ov._volver_a_dormir()
    assert ov.durmiendo


def test_sprites_video_centrado_como_el_sprite(sprites, qapp):
    ov = sprites
    if ov._sr is None or ov.cara.video_widget is None:
        pytest.skip("sin sprite o sin QtMultimedia")
    lbl = ov.cara.image_label
    r = ov._rect_pintado(lbl, lbl.pixmap())
    mx, my = ov._sr.margen
    w0, h0 = ov.cara._pixmap_actual.width(), ov.cara._pixmap_actual.height()
    centro_sprite = (r.x() + mx + w0 / 2, r.y() + my + h0 / 2)
    assert lbl.height() >= r.height()                      # el lienzo cabe entero (sin pies cortados)
    ov.cara.set_state("thinking")
    for _ in range(3):
        qapp.processEvents()
    vw = ov.cara.video_widget
    if not vw.isVisible():
        pytest.skip("sin vídeo de «pensando»")
    p = vw.mapTo(ov, QPoint(0, 0))
    centro_video = (p.x() + vw.width() / 2, p.y() + vw.height() / 2)
    assert abs(centro_video[0] - centro_sprite[0]) <= 1 and abs(centro_video[1] - centro_sprite[1]) <= 1


def test_sprites_mascara_donde_qt_pinta_y_etiqueta_pegada(sprites):
    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtWidgets import QStyle
    ov = sprites
    if ov._sr is None:
        pytest.skip("sin sprite")
    lbl = ov.cara.image_label
    pm = lbl.pixmap()
    qt = QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, lbl.alignment(),
                            QSize(pm.width(), pm.height()), lbl.contentsRect())
    assert ov._rect_pintado(lbl, pm).topLeft() == lbl.mapTo(ov, qt.topLeft())
    # la máscara no pasa de lo que se ve de la etiqueta de la imagen
    assert ov.mask().boundingRect().bottom() <= lbl.mapTo(ov, lbl.contentsRect().bottomLeft()).y()
    # «月 EN LÍNEA» justo encima de la figura, no en la esquina de la ventana crecida
    tag = ov.cara.state_tag
    t = tag.mapTo(ov, QPoint(0, 0))
    fig = ov._rect_figura_en_cara()
    f = ov.cara.mapTo(ov, fig.topLeft())
    assert abs(t.x() - f.x()) <= 3 and 0 <= f.y() - (t.y() + tag.height()) <= 3
    assert ov.mask().contains(QPoint(t.x() + 2, t.y() + 2))


def test_sprites_posicion_logica_esquina_y_bordes(qapp, tmp_path, lune_activa):
    from PyQt6.QtWidgets import QApplication
    from nucleo.config import Config
    from ui.avatar_overlay import AvatarOverlay
    g = QApplication.primaryScreen().availableGeometry()
    cfg = Config(config_path=str(tmp_path / "config.json"))
    # posición guardada por la 10.2 (ventana sin margen): sin salto
    cfg.set("avatar", "overlay_x", g.left() + 200)
    cfg.set("avatar", "overlay_y", g.top() + 150)
    ov = AvatarOverlay(config=cfg)
    mx, my = ov._margen
    assert (ov.x(), ov.y()) == (g.left() + 200 - mx, g.top() + 150 - my)
    # «Llevar a la esquina»: la figura (sin el margen) a 24 px del borde
    ov._esquina_inferior_derecha()
    fig = ov._rect_figura(ov.x(), ov.y())
    assert g.right() - fig.right() - 1 == 24 and g.bottom() - fig.bottom() - 1 == 24   # 24 px de hueco
    destruir(ov)
    # figura pegada al borde izquierdo / cabeza al borde de arriba: se respeta
    cfg.set("avatar", "overlay_x", g.left() - 50)
    cfg.set("avatar", "overlay_y", g.top() - 30)
    ov = AvatarOverlay(config=cfg)
    assert (ov.x(), ov.y()) == (g.left() - 50 - mx, g.top() - 30 - my)
    destruir(ov)


def test_lune_face_la_misma_cara_manda_en_su_vuelta_a_normal(qapp):
    from ui.lune_face import LuneFaceWidget
    cara = LuneFaceWidget()
    cara.set_state("sad", auto_revert_ms=6000)
    assert cara._revert_timer.isActive()
    cara.set_state("sad")                                      # la de arrastre (la misma) sin vuelta
    assert not cara._revert_timer.isActive()
    cara.set_state("sad", auto_revert_ms=1500)
    assert cara._revert_timer.isActive() and cara._revert_timer.interval() == 1500
    destruir(cara)
