"""
Tests de integración de servicios/tools.py con el Ejecutor (corte 2).

ToolManager es quien tiene los handlers (firma `fn(args, ctx)`) de las cuatro
herramientas de siempre y de las que se enchufan después (cambiar_voz…). Cada
modo crea su Ejecutor con `crear_ejecutor`, que recibe también los handlers que
se registren más tarde. El formato antiguo ya no ejecuta nada.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import tools as T  # noqa: E402
from servicios.tools import ToolManager, ToolResult, ctx_acciones  # noqa: E402
from lune_core import herramientas as H  # noqa: E402
from lune_core import acciones as A  # noqa: E402


@pytest.fixture
def abiertas(monkeypatch):
    """Nada de abrir el navegador de verdad: se anotan las URL."""
    urls = []
    monkeypatch.setattr(T.webbrowser, "open", lambda u, *a, **k: urls.append(u) or True)
    return urls


class TimerFalso:
    def __init__(self):
        self.cancelado = False

    def cancel(self):
        self.cancelado = True


def _ejecutor(tm, pedir=None, **kw):
    return tm.crear_ejecutor(pedir, audit_path=None,
                             programar=lambda s, fn: TimerFalso(), **kw)


# ── Registro por defecto ─────────────────────────────────────────────────────────

def test_registro_por_defecto_incluye_el_catalogo():
    from lune_core import catalogo_herramientas as C
    assert set(H.registro_por_defecto().nombres()) == set(C.CATALOGO)
    assert set(H.registro_basico().nombres()) == set(C.EXISTENTES)


def test_sesion_reiniciar(tmp_path):
    s = H.Sesion(H.registro_por_defecto(), audit_path=tmp_path / "a.jsonl")
    s.solicitar("abrir_url", {"url": "https://x.com"})
    pid = s.solicitar("lanzar_app", {"app": "paint"})["pendiente_id"]
    assert s.gastado == 1 and pid in s.pendientes
    assert s.reiniciar() == 1
    assert s.gastado == 0 and not s.pendientes
    assert "reinicio" in (tmp_path / "a.jsonl").read_text("utf-8")


# ── Handlers ─────────────────────────────────────────────────────────────────────

def test_handlers_de_las_cuatro_de_siempre():
    tm = ToolManager()
    assert set(tm.handlers) == {"sistema_info", "buscar_web", "abrir_url", "lanzar_app"}
    assert tm.tiene_handler("abrir_url") and not tm.tiene_handler("cambiar_voz")


def test_buscar_web_en_youtube_y_google(abiertas):
    tm = ToolManager()
    r = tm.handlers["buscar_web"]({"consulta": "gatos", "sitio": "youtube"}, None)
    assert r.ok and abiertas[-1].startswith("https://www.youtube.com/results?search_query=gatos")
    r = tm.handlers["buscar_web"]({"consulta": "pozole"}, None)
    assert r.ok and abiertas[-1].startswith("https://www.google.com/search?q=pozole")
    assert tm.handlers["buscar_web"]({"consulta": ""}, None).ok is False


def test_abrir_url_por_handler_sigue_rechazando_esquemas_peligrosos(abiertas):
    tm = ToolManager()
    assert tm.handlers["abrir_url"]({"url": "javascript:alert(1)"}, None).ok is False
    assert abiertas == []


def test_registrar_handler_y_ejecutar_con_dict():
    tm = ToolManager()
    vistos = []
    tm.registrar_handler("temporizador", lambda a, ctx: vistos.append((a, ctx)) or "listo")
    r = tm.ejecutar("temporizador", args={"segundos": "300", "texto": "pizza", "extra": 1})
    assert r.ok and r.mensaje == "listo"
    # validado contra el esquema: número convertido y clave desconocida fuera
    assert vistos == [({"segundos": 300, "texto": "pizza"}, None)]
    r = tm.ejecutar("temporizador", segundos=0)
    assert r.ok is False and "Argumentos no válidos" in r.mensaje
    with pytest.raises(TypeError):
        tm.registrar_handler("x", "no soy una función")


def test_ejecutar_sigue_aceptando_texto_y_rechaza_lo_desconocido(abiertas):
    tm = ToolManager()
    assert tm.ejecutar("abrir_url", args="https://x.com").ok
    assert tm.ejecutar("abrir_url", args={"url": "https://y.com"}).ok
    assert abiertas == ["https://x.com", "https://y.com"]
    assert tm.ejecutar("no_existe", args="x").ok is False


def test_handler_que_lanza_es_un_fallo_controlado():
    tm = ToolManager()

    def roto(a, ctx):
        raise ValueError("voz inexistente")
    tm.registrar_handler("cambiar_voz", roto)
    r = tm.ejecutar("cambiar_voz", voz="es-XX-NadaNeural")
    assert r.ok is False and "voz inexistente" in r.mensaje


def test_listar_disponibles_sale_del_registro():
    tm = ToolManager()
    texto = tm.listar_disponibles()
    assert "Abrir una aplicación del PC (pide permiso)" in texto
    assert "Cambiar tu voz" not in texto
    tm.registrar_handler("cambiar_voz", lambda a, c: "ok")
    assert "Cambiar tu voz" in tm.listar_disponibles()


def test_disponibles_por_modo():
    tm = ToolManager()
    tm.registrar_handler("asistente_dormir", lambda a, c: "zzz")
    assert "asistente_dormir" in tm.disponibles("vrm")
    assert "asistente_dormir" not in tm.disponibles("patata")


def test_ctx_acciones_lee_la_url_del_proveedor():
    class P:
        url = "http://localhost:11434"

    class C:
        base_url = "https://api.groq.com/openai/v1"

    class AI:
        providers = {"ollama": P(), "compat": C()}
    ai = AI()
    # `ai` va en el ctx: el Ejecutor mira al ejecutar si el contexto está contaminado.
    assert ctx_acciones(ai, "ollama", "br") == {"modo": "br", "proveedor": "ollama",
                                                "url": "http://localhost:11434", "ai": ai}
    assert ctx_acciones(AI(), "compat", "patata")["url"].startswith("https://api.groq.com")
    assert ctx_acciones(None, "openrouter", "")["url"] == ""


# ── crear_ejecutor ───────────────────────────────────────────────────────────────

def test_crear_ejecutor_procesa_un_call_y_no_el_formato_antiguo(abiertas):
    tm = ToolManager()
    ej = _ejecutor(tm)
    texto, llamadas = ej.procesar(
        'Voy. ABRIR_URL:https://viejo.example <|CALL ["abrir_url", {"url": "https://x.com"}]|>',
        "usuario", {"modo": "br"})
    assert "ABRIR_URL" not in texto and "CALL" not in texto
    res = []
    ej.ejecutar_llamadas(llamadas, "usuario", {"modo": "br"}, res.append)
    assert [r.estado for r in res] == [A.HECHA]
    assert abiertas == ["https://x.com"]


def test_los_handlers_registrados_despues_llegan_al_ejecutor():
    tm = ToolManager()
    ej = _ejecutor(tm)
    assert "temporizador" not in ej.handlers
    tm.registrar_handler("temporizador", lambda a, c: f"en {a['segundos']} s")
    assert "temporizador" in ej.handlers
    _, llamadas = ej.procesar('<|CALL ["temporizador", {"segundos": 5}]|>', "usuario", None)
    res = []
    ej.ejecutar_llamadas(llamadas, "usuario", None, res.append)
    assert res[0].ok and res[0].mensaje == "en 5 s"
    tm.quitar_handler("temporizador")
    assert "temporizador" not in ej.handlers


def test_lanzar_app_pide_permiso_y_se_ejecuta_al_aprobar(monkeypatch):
    tm = ToolManager()
    lanzadas = []
    monkeypatch.setattr(tm, "_cmd_lanzar_app", lambda n: lanzadas.append(n) or ToolResult(True, "ok"))
    tm.registrar_handler("lanzar_app", tm._h_lanzar_app)       # ahora apunta al parche
    preguntas = []
    ej = _ejecutor(tm, lambda p, responder: preguntas.append((p, responder)))
    _, llamadas = ej.procesar('<|CALL ["lanzar_app", {"app": "calc"}]|>', "usuario", None)
    res = []
    ej.ejecutar_llamadas(llamadas, "usuario", None, res.append)
    assert len(preguntas) == 1 and lanzadas == [] and res == []
    assert preguntas[0][0]["resumen"] == "Abrir la aplicación «calc»"
    preguntas[0][1](True)
    assert lanzadas == ["calc"] and res[0].ok


def test_turno_no_confiable_no_abre_nada(abiertas):
    tm = ToolManager()
    ej = _ejecutor(tm)
    _, llamadas = ej.procesar('<|CALL ["abrir_url", {"url": "https://malo.example"}]|>',
                              "no_confiable", None)
    res = []
    ej.ejecutar_llamadas(llamadas, "no_confiable", None, res.append)
    assert res[0].estado == A.NO_CONFIABLE_ESTADO and abiertas == []


def test_crear_ejecutor_audita_en_logs_por_defecto():
    assert T.AUDIT_POR_DEFECTO == T.RAIZ / "logs" / "audit.jsonl"


# ── cambiar_voz ──────────────────────────────────────────────────────────────────

def test_conectar_voz_registra_cambiar_voz(monkeypatch):
    from servicios import voces
    llamadas = []
    monkeypatch.setattr(voces, "herramienta_cambiar_voz",
                        lambda args, ctx: llamadas.append((args, ctx)) or "Listo: voz nueva.")
    tm = ToolManager()
    config, voice = object(), object()
    tm.conectar_voz(config, voice)
    ej = _ejecutor(tm)
    _, ll = ej.procesar('<|CALL ["cambiar_voz", {"voz": "es-AR-ElenaNeural"}]|>', "usuario",
                        {"modo": "patata"})
    res = []
    ej.ejecutar_llamadas(ll, "usuario", {"modo": "patata"}, res.append)
    assert res[0].ok and res[0].mensaje == "Listo: voz nueva."
    assert llamadas == [({"voz": "es-AR-ElenaNeural"}, {"config": config, "voice": voice})]


def test_servicios_escritorio_conecta_las_herramientas_de_la_app(qapp):
    """ServiciosEscritorio.conectar_herramientas: cambiar_voz (config + voz de la app)
    y las que registren los controladores, antes o después de conectar."""
    from ui.escritorio import ServiciosEscritorio
    config, voice = object(), object()
    esc = ServiciosEscritorio(config, voice=voice)
    antes = lambda args, ctx: "antes"                      # noqa: E731
    esc.registrar_herramienta("temporizador", antes)
    tm = ToolManager()
    ej = _ejecutor(tm)
    esc.conectar_herramientas(tm)
    assert {"cambiar_voz", "temporizador"} <= set(tm.handlers)
    assert ej.handlers["temporizador"] is antes              # llega al Ejecutor ya creado
    despues = lambda args, ctx: "después"                  # noqa: E731
    esc.registrar_herramienta("listar_alarmas", despues)
    assert tm.handlers["listar_alarmas"] is despues and ej.handlers["listar_alarmas"] is despues
    esc.quitar_herramienta("listar_alarmas")
    assert "listar_alarmas" not in tm.handlers and "listar_alarmas" not in ej.handlers
    esc.cerrar()


# ── Revisión cortes 2+3: S5 (comandos del usuario por el Ejecutor) y S4 (alias) ──

@pytest.fixture
def lanzados(monkeypatch):
    """Nada de lanzar programas de verdad: se anotan."""
    procs = []
    monkeypatch.setattr(T.subprocess, "Popen", lambda args, **k: procs.append(list(args)))
    monkeypatch.setattr(T.shutil, "which", lambda n: f"C:\\bin\\{n}.exe")
    return procs


@pytest.mark.parametrize("texto, herramienta, args", [
    ("abre youtube", "abrir_url", {"url": "https://www.youtube.com"}),
    ("ve a Wikipedia.org/Luna", "abrir_url", {"url": "Wikipedia.org/Luna"}),
    ("lanza paint", "lanzar_app", {"app": "paint"}),
    ("abre la app Calculadora", "lanzar_app", {"app": "Calculadora"}),
    ("busca recetas de Pozole", "buscar_web", {"consulta": "recetas de Pozole", "sitio": "google"}),
    ("busca en youtube lofi", "buscar_web", {"consulta": "lofi", "sitio": "youtube"}),
    ("estado del pc", "sistema_info", {}),
])
def test_detectar_llamadas_no_ejecuta_nada(texto, herramienta, args, abiertas, lanzados):
    llamadas = ToolManager().detectar_llamadas(texto)
    assert len(llamadas) == 1 and isinstance(llamadas[0], A.Llamada)
    ll = llamadas[0]
    assert (ll.herramienta, ll.args, ll.origen, ll.directa, ll.valida) == (
        herramienta, args, "usuario", True, True)
    assert abiertas == [] and lanzados == []


def test_detectar_llamadas_texto_normal():
    tm = ToolManager()
    assert tm.detectar_llamadas("hola, ¿qué tal?") == []
    assert tm.detectar_llamadas("abre tu corazón") == []           # ni atajo ni dominio
    assert tm.detectar_llamadas("") == []


def test_lanza_pasa_por_el_ejecutor_y_pide_permiso(abiertas, lanzados):
    """S5: «lanza X» (también dictado en modo llamada) ya no lanza sin preguntar."""
    tm = ToolManager()
    preguntas, res = [], []
    ej = _ejecutor(tm, pedir=lambda p, r: preguntas.append((p, r)))
    ej.ejecutar_llamadas(tm.detectar_llamadas("lanza paint"), "usuario", {"modo": "normal"},
                         res.append)
    assert lanzados == [] and len(preguntas) == 1 and res == []
    preguntas[0][1](True)                                           # el humano dice que sí
    assert lanzados == [["C:\\bin\\mspaint.exe"]] and res[0].ok


def test_detectar_y_ejecutar_ya_no_hace_nada_solo(abiertas, lanzados):
    tm = ToolManager()
    for texto in ("abre youtube", "lanza powershell", "estado del pc", "busca gatos"):
        assert tm.detectar_y_ejecutar(texto) is None
    assert abiertas == [] and lanzados == []
    # Con un ejecutor, delega en él (y pasa por su Política).
    res = []
    ej = _ejecutor(tm)
    tr = tm.detectar_y_ejecutar("abre youtube", ej, {"modo": "normal"}, res.append)
    assert tr is not None and tr.ok and abiertas == ["https://www.youtube.com"]
    assert res and res[0].ok


def test_alias_se_resuelve_antes_de_la_denegacion(lanzados):
    """S4: «terminal»/«consola» son cmd: se deniegan como cmd, sin llegar a preguntar."""
    tm = ToolManager()
    preguntas, res = [], []
    ej = _ejecutor(tm, pedir=lambda p, r: preguntas.append(p))
    for app in ("terminal", "Consola", "cmd", "pwsh"):
        ej.ejecutar_llamadas([A.Llamada("lanzar_app", {"app": app})], "usuario",
                             {"modo": "normal"}, res.append)
    assert preguntas == [] and lanzados == []
    assert [r.estado for r in res] == [A.DENEGADA] * 4
    assert H.Politica().evaluar(H.registro_basico().get("lanzar_app"),
                                {"app": "terminal"}).decision == H.Decision.DENEGAR


def test_la_aprobacion_muestra_el_programa_real():
    from lune_core import catalogo_herramientas as C
    assert C.resumen("lanzar_app", {"app": "paint"}) == "Abrir la aplicación «paint» (programa: mspaint)"
    assert C.resumen("lanzar_app", {"app": "notepad"}) == "Abrir la aplicación «notepad»"
    tm = ToolManager()
    preguntas = []
    ej = _ejecutor(tm, pedir=lambda p, r: preguntas.append(p))
    ej.ejecutar_llamadas([A.Llamada("lanzar_app", {"app": "bloc de notas"})], "usuario",
                         {"modo": "normal"}, lambda r: None)
    assert "notepad" in preguntas[0]["resumen"]
