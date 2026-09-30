"""
Tests de la integración del corte 1 en la asistente (v10.3):

- ui_web/vrm/lune_vrm.js crea el bus de módulos y llama a sus hooks en el sitio
  justo del frame (pose antes de rotation.set, trasPose antes de vrm.update,
  trasUpdate antes de render, expresiones en su bloque), con ocupado/inhibe
  combinados y los eventos de siempre encolados hacia Python.
- companion_vrm.html y companion.html cargan lune_eventos/lune_sfx/lune_burbuja y
  burbuja.css, exponen luneMod, luneEventos y luneSfx y mantienen su API.
- ui/companion.py vacía la cola con un QTimer propio a 12 Hz en los dos renders
  (señal evento_js), lo para al ocultarse, deja sonar audio sin gesto y mantiene
  un BusEstado si se le pasa.

Lo visual no se prueba aquí (hace falta pantalla); se prueba el cableado.
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

MOTOR = RAIZ / "ui_web" / "vrm" / "lune_vrm.js"
PAGINA_VRM = RAIZ / "ui_web" / "companion_vrm.html"
PAGINA_ANIM = RAIZ / "ui_web" / "companion.html"


# ── lune_vrm.js: hooks del bus en su sitio ─────────────────────────────────────

def _cuerpo(js: str, firma: str) -> str:
    """Texto de la función que empieza en `firma` hasta su llave de cierre."""
    i = js.index(firma)
    j = js.index("{", i)
    nivel = 0
    for k in range(j, len(js)):
        if js[k] == "{":
            nivel += 1
        elif js[k] == "}":
            nivel -= 1
            if nivel == 0:
                return js[i:k + 1]
    raise AssertionError(f"sin cierre: {firma}")


def test_el_motor_crea_el_bus_con_el_ctx_del_plan():
    js = MOTOR.read_text("utf-8")
    assert "import { crearBus, emitirPorDefecto } from './lune_modulos.js';" in js
    assert "const bus = crearBus(ctx);" in js
    ctx = js[js.index("const ctx = {"):js.index("const bus = crearBus(ctx);")]
    for clave in ("THREE", "scene", "camera", "renderer", "canvas", "PARAMS", "emitir", "vrm:",
                  "get huesos()", "get sXZ()", "proyectar:", "encuadrar:", "setFPS:",
                  "setPixelRatio:", "setLookAt:", "estado:"):
        assert clave in ctx, clave


def test_hooks_del_frame_en_orden():
    js = MOTOR.read_text("utf-8")
    animar = _cuerpo(js, "function animar(dt)")
    # pose: después de gesto, caricia y seguimiento (los idles son el módulo 'idles'
    # del bus); antes de rotation.set
    i_pose = animar.index("bus.llamar('pose', out, dt, ahora, est)")
    for antes in ("mezGestos.pose(out, ahora, wG)", "pat.peso * inh.caricia",
                  "add(out, 'head', -cabezaPitch"):
        assert animar.index(antes) < i_pose, antes
    assert i_pose < animar.index("huesos[h].rotation.set(")
    # expresiones: dentro del bloque de expresiones, al final
    i_expr = animar.index("bus.llamar('expresiones', setExprMod, dt, ahora, est)")
    assert animar.index("const em = vrm.expressionManager;") < i_expr
    assert animar.index("setExpr('blinkRight'") < i_expr
    # trasPose antes de vrm.update, trasUpdate después y antes de render
    tick = _cuerpo(js, "function tick(now)")
    assert (tick.index("animar(dt)") < tick.index("bus.llamar('trasPose'")
            < tick.index("vrm.update(dt)") < tick.index("bus.llamar('trasUpdate'")
            < tick.index("renderer.render(scene, camera)"))


def test_ocupado_inhibe_y_ciclo_del_modelo():
    js = MOTOR.read_text("utf-8")
    assert "return bus.ocupado(actualizarEst());" in _cuerpo(js, "function ocupado()")
    animar = _cuerpo(js, "function animar(dt)")
    assert "bus.inhibe(est, inh);" in animar
    for factor in ("inh.idle", "inh.seguimiento", "inh.caricia", "inh.parpadeo", "inh.gesto"):
        assert factor in js, factor
    assert "inh.caricia <= 0.001" in _cuerpo(js, "function procesarCaricia(px, py)")
    descargar = _cuerpo(js, "function descargar()")
    assert descargar.index("bus.llamar('alDescargar')") < descargar.index("scene.remove(vrm.scene)")
    assert "bus.llamar('alCargar', v);" in _cuerpo(js, "function cargar(url)")
    # API pública nueva
    ret = js[js.rindex("return {"):]
    assert "mod: (nombre, metodo, ...args) => bus.api(nombre, metodo, ...args)" in ret
    assert "registrar:" in ret and "bus, ctx" in ret


def test_los_eventos_de_siempre_se_encolan_para_python():
    js = MOTOR.read_text("utf-8")
    ev = _cuerpo(js, "function evento(tipo, dato)")
    assert "onEvento(tipo, dato)" in ev
    for tipo in ("'caricia'", "'arrastre'", "'dormir'", "'despertar'", "'estado'", "'error'"):
        assert tipo in ev, tipo
    # nadie llama ya a onEvento a pelo (se perdería el evento para Python)
    llamadas = [m.start() for m in re.finditer(r"\bonEvento\(", js)]
    assert len(llamadas) == 1, "todas las llamadas deben pasar por evento()"


# ── Las páginas ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pagina", [PAGINA_VRM, PAGINA_ANIM], ids=["vrm", "animado"])
def test_las_paginas_cargan_los_scripts_compartidos(pagina):
    html = pagina.read_text("utf-8")
    assert 'href="css/burbuja.css"' in html
    for script in ("lune_eventos.js", "lune_sfx.js", "lune_burbuja.js"):
        assert f'<script src="{script}"></script>' in html, script
        assert (RAIZ / "ui_web" / script).is_file()
    for api in ("window.luneEventos =", "window.luneSfx =", "window.luneMod =", "window.luneSpeak =",
                "window.luneSetFPS =", "window.setEmocion ="):
        assert api in html, api
    # los scripts clásicos van antes que el módulo que usa sus APIs
    assert html.index("lune_burbuja.js") < html.index('<script type="module">')


def test_la_burbuja_del_vrm_delega_en_lune_burbuja():
    html = PAGINA_VRM.read_text("utf-8")
    assert "burbuja.comentar(t, ms)" in html and "burbuja.pensando()" in html and "burbuja.ocultar()" in html
    assert "burbuja.onBoca" in html and "luneBurbuja.setVoz" in html
    assert "let bt" not in html                           # sin temporizador propio que pise al compartido


def test_la_pagina_animada_crea_el_registro_de_modulos():
    html = PAGINA_ANIM.read_text("utf-8")
    assert "import { crearRegistroAnim } from './anim/lune_anim_modulos.js';" in html
    assert "window.luneAnim = reg;" in html and "reg.emocion(s)" in html
    # la API de siempre sigue ahí (y el saludo al aparecer)
    assert "window.setEmocion('wave');" in html
    assert "window.comentar = function" in html          # respaldo si lune_burbuja.js no carga


def test_web_shell_deja_sonar_audio_sin_gesto():
    src = (RAIZ / "ui" / "web_shell.py").read_text("utf-8")
    assert "PlaybackRequiresUserGesture, False" in src


# ── companion.py ───────────────────────────────────────────────────────────────

def _vrm_minimo() -> bytes:
    """GLB mínimo con la extensión VRMC_vrm (lo que nucleo/vrm.py valida)."""
    import struct
    js = json.dumps({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                     "extensions": {"VRMC_vrm": {"meta": {"name": "Luna", "authors": ["Diego"]}}}}).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js))
            + struct.pack("<II", len(js), 0x4E4F534A) + js)


def test_parsear_eventos_tolera_de_todo():
    from ui.companion import _parsear_eventos
    assert _parsear_eventos(None) == [] and _parsear_eventos("") == [] and _parsear_eventos("{roto") == []
    assert _parsear_eventos("{}") == [] and _parsear_eventos(True) == []
    crudo = json.dumps([
        {"t": "caricia", "d": {"lado": 1}, "ts": 1},
        {"t": "estado", "d": "happy"},
        {"t": "dormir", "d": None},
        {"t": "", "d": {}}, {"d": {}}, "basura", {"t": 3},
    ])
    assert _parsear_eventos(crudo) == [("caricia", {"lado": 1}), ("estado", {"valor": "happy"}), ("dormir", {})]
    assert _parsear_eventos([{"t": "x", "d": [1, 2]}]) == [("x", {"valor": [1, 2]})]


pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="la asistente necesita PyQt6-WebEngine")


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso: anota el JS, responde a luneEventos() con lo que se le
    prepare y registra los atributos de los ajustes."""
    from PyQt6.QtCore import QObject, QUrl, pyqtSignal
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []; self.cola = []; self.pendiente = None
        def setBackgroundColor(self, *_): pass
        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                if self.pendiente == "retener":            # la respuesta no llega aún
                    self.pendiente = cb
                    return
                lote, self.cola = self.cola, []
                cb(json.dumps(lote))
            else:
                cb(None)

    class Ajustes:
        vistos = {}
        def setAttribute(self, attr, valor): Ajustes.vistos[attr] = valor

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)
        def __init__(self):
            super().__init__(); self._pagina = Pagina(); self._url = QUrl(); self._ajustes = Ajustes()
        def page(self): return self._pagina
        def settings(self): return self._ajustes
        def setUrl(self, url): self._url = url
        def url(self): return self._url
        def focusProxy(self): return None

    Ajustes.vistos = {}
    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    FalsoWeb.Ajustes = Ajustes
    return FalsoWeb


@pytest.fixture
def config_animado(tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    return cfg


def test_canal_de_eventos_independiente_en_animado(qapp, web_falso, config_animado):
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from ui.companion import CompanionFlotante, EVENTOS_JS
    c = CompanionFlotante(config_animado, ai_manager=None)
    recibidos = []
    c.evento_js.connect(lambda t, d: recibidos.append((t, d)))
    try:
        assert web_falso.Ajustes.vistos.get(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture) is False
        assert c._timer_eventos.interval() == 1000 // 12
        assert not c._timer_eventos.isActive()
        c.show()
        assert c._timer_eventos.isActive()               # también en animado (antes: solo VRM)
        pagina = c.web.page()
        pagina.cola = [{"t": "baile_fin", "d": {"id": "x"}}, {"t": "dormir", "d": None}]
        c._vaciar_eventos()
        assert EVENTOS_JS == "window.luneEventos ? window.luneEventos() : '[]'"
        assert pagina.js[-1] == EVENTOS_JS
        assert recibidos == [("baile_fin", {"id": "x"}), ("dormir", {})]
        # una petición a la vez: si la respuesta no llega, no se amontonan
        pagina.pendiente = "retener"
        c._vaciar_eventos()
        n = len(pagina.js)
        c._vaciar_eventos()
        assert len(pagina.js) == n
        pagina.pendiente(json.dumps([{"t": "caricia", "d": {"lado": -1}}]))
        assert recibidos[-1] == ("caricia", {"lado": -1})
        # la respuesta None (página recargando) no rompe nada
        c._on_eventos_js(None)
        c.hide()
        assert not c._timer_eventos.isActive()
        c.show()
        assert c._timer_eventos.isActive()
    finally:
        c.close()
    assert not c._timer_eventos.isActive()


def test_el_bus_de_estado_sigue_a_la_asistente(qapp, web_falso, config_animado):
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from nucleo.estado_asistente import BusEstado
    from ui.companion import CompanionFlotante
    bus = BusEstado()
    c = CompanionFlotante(config_animado, ai_manager=None, bus_estado=bus)
    try:
        assert bus.actual().render == "animado" and bus.actual().visible is False
        c.show()
        assert bus.actual().visible is True
        c.set_hablando(True)
        assert bus.actual().hablando is True
        c.set_hablando(False)
        c.set_emocion("awkward")
        assert bus.actual().emocion == "awkward"
        c.set_estado("thinking")
        assert bus.actual().emocion == "think"
        c._revertir(c._revert_token)
        assert bus.actual().emocion == "neutral"

        class Raton:
            def __init__(self, x, y, boton=Qt.MouseButton.LeftButton, botones=Qt.MouseButton.LeftButton):
                self._p = QPointF(x, y); self._b = boton; self._bs = botones
            def button(self): return self._b
            def buttons(self): return self._bs
            def globalPosition(self): return self._p

        c.comentar_pantalla = lambda: None              # un clic limpio comentaría la pantalla
        c._raton_press(Raton(100, 100))
        assert bus.actual().arrastrando is False        # pulsar no es arrastrar
        c._raton_move(Raton(130, 100))
        assert bus.actual().arrastrando is True
        c._raton_release(Raton(130, 100))
        assert bus.actual().arrastrando is False
        c.hide()
        assert bus.actual().visible is False
    finally:
        c.close()


def test_el_bus_de_estado_en_vrm_duerme_y_despierta(qapp, web_falso, tmp_path, monkeypatch):
    from nucleo import personajes, vrm
    from nucleo.config import Config
    from nucleo.estado_asistente import BusEstado
    from ui.companion import CompanionFlotante
    carpeta = tmp_path / "modelo_vrm"; carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(_vrm_minimo())
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    cfg = Config(config_path=str(tmp_path / "config.json")); cfg.set("avatar", "render", "vrm")
    c = CompanionFlotante(cfg, ai_manager=None)
    bus = BusEstado()
    try:
        assert c.render == "vrm"
        c.set_bus_estado(bus)                           # como hace ServiciosEscritorio.set_asistente
        assert bus.actual().render == "vrm"
        c._dormir()
        assert bus.actual().durmiendo is True
        c.set_estado("happy")
        assert bus.actual().durmiendo is False and bus.actual().emocion == "happy"
        c.set_bus_estado(None)
        c._dormir()
        assert bus.actual().durmiendo is False          # ya no lo sigue
    finally:
        c.close()


def test_sin_bus_no_cambia_nada(qapp, web_falso, config_animado):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config_animado, ai_manager=None)
    try:
        assert c._bus_estado is None
        c.show(); c.set_hablando(True); c.set_emocion("happy"); c.hide()   # no lanza
    finally:
        c.close()
