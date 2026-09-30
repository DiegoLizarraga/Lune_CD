"""
Tests del contrato de la asistente de los cortes 5 y 6 en ui/companion.py (animada y VRM):

- soporta_grande, geometria()/set_geometria() (sin guardar la posición ni devolverla
  a la pantalla) y grande_fase(fase, opciones) → la llamada JS luneGrande correcta;
- en pantalla grande: rueda, arrastre, clic «comentar», doble clic «chat», sueño y
  comentarios automáticos apagados; el clic izquierdo MANTENIDO → luneHold; el cursor
  se mide desde el 50 % del alto; 30 fps y, en «fin», vuelta a avatar.fps_max;
- set_salvapantallas duerme (sin la regla) y despierta; mostrar_alarma con retraso,
  ocultar_alarma, y con alarma el clic no comenta; bailar/pulso → luneBailar/lunePulso
  saneados; bailando no se duerme sola;
- al recargar la página se repite lo que estaba a la vista; al cerrar en grande se
  guarda la posición de antes.

Qt offscreen, sin Chromium (vista web falsa que anota el JS), como test_asistente_corte4.py.
"""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, pyqtSignal  # noqa: E402

PRESS, MOVE, RELEASE, DOBLE = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                               QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
IZQ, DER = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton


def raton(tipo, boton, x, y, botones=None):
    from PyQt6.QtGui import QMouseEvent
    p = QPointF(x, y)
    if botones is None:
        botones = Qt.MouseButton.NoButton if tipo == RELEASE else boton
    return QMouseEvent(tipo, p, p, boton, botones, Qt.KeyboardModifier.NoModifier)


def rueda(x, y, muescas=1):
    from PyQt6.QtGui import QWheelEvent
    p = QPointF(x, y)
    return QWheelEvent(p, p, QPoint(0, 0), QPoint(0, 120 * muescas), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)


def centro(w, dx=0, dy=0):
    c = w.frameGeometry().center()
    return c.x() + dx, c.y() + dy


@pytest.fixture
def lune_activa(monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})


@pytest.fixture
def config(tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    return cfg


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso que anota el JS (como en test_asistente_corte4.py)."""
    if not HAY_WEBENGINE:
        pytest.skip("la asistente web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is not None:
                cb("[]" if "luneEventos" in codigo else None)

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
    return FalsoWeb


@pytest.fixture
def asistente(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=object(), bandeja=False)
    c._aparecer_pendiente = False
    c.show()
    c._on_cargado(True)
    c.web.page().js.clear()
    yield c
    c.close()


def js(c):
    return c.web.page().js


def llamadas(c, fn):
    return [x for x in js(c) if f"window.{fn}(" in x]


def a_grande(c, monitor=QRect(0, 0, 1280, 720)):
    """Lo que hace ControlPantallaGrande: guarda, glide, geometría del monitor, entrar."""
    antes = c.geometria()
    c.grande_fase("glide", {"ms": 400})
    c.set_geometria(monitor)
    c.grande_fase("entrar", {"ms": 500})
    return antes


# ── Pantalla grande ────────────────────────────────────────────────────────────

def test_soporta_grande_y_geometria(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    try:
        assert c.soporta_grande is False, "sin la página cargada no"
        c.show(); c._on_cargado(True)
        assert c.soporta_grande is True
        g = c.geometria()
        assert isinstance(g, QRect) and g == c.geometry()
        g.moveTo(0, 0)
        assert c.geometry() != g or c.pos() == QPoint(0, 0), "geometria() es una copia"
    finally:
        c.close()
    assert c.soporta_grande is False, "cerrada no"


def test_set_geometria_no_guarda_la_posicion(asistente, config):
    c = asistente
    x0, y0 = config.get("avatar", "companion_x"), config.get("avatar", "companion_y")
    c.set_geometria(QRect(3, 4, 1280, 720))
    assert c.geometry() == QRect(3, 4, 1280, 720), "tal cual, sin devolverla a la pantalla"
    assert (config.get("avatar", "companion_x"), config.get("avatar", "companion_y")) == (x0, y0)
    c.set_geometria(QRect(0, 0, 0, 10))              # vacía: no hace nada
    c.set_geometria(None)
    assert c.geometry() == QRect(3, 4, 1280, 720)


def test_grande_fase_llama_a_la_pagina(asistente):
    c = asistente
    c.grande_fase("glide", {"ms": 400, "motivo": "manual", "lista": [1], "nan": float("nan"), "mal clave": 1})
    assert js(c)[-1] == 'window.luneGrande && window.luneGrande("glide", {"motivo": "manual", "ms": 400})'
    assert c.en_grande
    for f in ("entrar", "salir", "volver"):
        c.grande_fase(f)
        assert js(c)[-1] == f'window.luneGrande && window.luneGrande("{f}", {{}})'
    n = len(js(c))
    c.grande_fase("patata")                           # desconocida: nada
    c.grande_fase("GLIDE); alert(1); (")
    assert len(js(c)) == n
    c.grande_fase("fin")
    assert 'window.luneGrande && window.luneGrande("fin", {})' in js(c)[n:]
    assert not c.en_grande


def test_en_grande_30_fps_y_fin_vuelve_a_fps_max(asistente, config):
    c = asistente
    config.set("avatar", "fps_max", 90)
    c.aplicar_opciones()
    assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(90)"
    a_grande(c)
    assert "window.luneSetFPS && window.luneSetFPS(30)" in js(c)
    c.set_fps_max(120)                                # en grande sigue a 30
    assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(30)"
    c.grande_fase("fin")
    fin = [i for i, x in enumerate(js(c)) if '"fin"' in x][-1]
    assert js(c)[fin + 1] == "window.luneSetFPS && window.luneSetFPS(120)", "el fin de la página, y luego fps_max"


def test_en_grande_sin_rueda_arrastre_comentario_ni_chat(asistente, config, monkeypatch):
    c = asistente
    comentarios = []
    monkeypatch.setattr(c, "comentar_pantalla", lambda: comentarios.append(1))
    chats = []
    monkeypatch.setattr(c._chat, "abrir", lambda: chats.append(1))
    a_grande(c)
    g0 = c.geometry()
    js(c).clear()
    x, y = centro(c)
    # rueda: la consume y no escala
    assert c._rueda(rueda(x, y)) is True
    assert not c._timer_escala.isActive()
    # clic izquierdo mantenido → luneHold (y nada de arrastre ni comentario)
    c.eventFilter(c.web, raton(PRESS, IZQ, x, y))
    p = c.web.mapFromGlobal(QPoint(x, y))
    assert js(c)[-1] == f"window.luneHold && window.luneHold(true, {p.x()}, {p.y()})"
    assert c._arrastre is None
    c._hold_envio = 0.0                               # sin esperar al tope de 30 Hz
    c.eventFilter(c.web, raton(MOVE, Qt.MouseButton.NoButton, x + 80, y + 10, botones=IZQ))
    p2 = c.web.mapFromGlobal(QPoint(x + 80, y + 10))
    assert js(c)[-1] == f"window.luneHold && window.luneHold(true, {p2.x()}, {p2.y()})"
    assert c.geometry() == g0, "no se mueve la ventana"
    c.eventFilter(c.web, raton(RELEASE, IZQ, x + 80, y + 10))
    assert js(c)[-1] == "window.luneHold && window.luneHold(false, 0, 0)"
    assert not any("luneTouch" in s or "luneDrag" in s for s in js(c))
    # doble clic: sin chat
    c.eventFilter(c.web, raton(DOBLE, IZQ, x, y))
    c._clic_simple()
    assert chats == [] and comentarios == [] and not c._clic.pendiente()
    # el clic derecho sigue abriendo el radial (para «Salir de pantalla grande»)
    pedidos = []
    c.menu_pedido.connect(lambda t, q: pedidos.append(t))
    c.eventFilter(c.web, raton(PRESS, DER, x, y)); c.eventFilter(c.web, raton(RELEASE, DER, x, y))
    assert pedidos == ["principal"]
    # tras fin, todo vuelve
    c.grande_fase("fin")
    c.eventFilter(c.web, raton(PRESS, IZQ, x, y))
    assert c._arrastre is not None and not c._hold
    c.eventFilter(c.web, raton(RELEASE, IZQ, x, y))
    assert c._clic.pendiente(), "el clic limpio vuelve a comentar"
    c._clic.cancelar()


def test_hold_se_suelta_al_salir_de_grande_y_al_ocultarse(asistente):
    c = asistente
    a_grande(c)
    x, y = centro(c)
    c.eventFilter(c.web, raton(PRESS, IZQ, x, y))
    assert c._hold
    c.grande_fase("fin")
    assert not c._hold and "window.luneHold && window.luneHold(false, 0, 0)" in js(c)
    a_grande(c)
    c.eventFilter(c.web, raton(PRESS, IZQ, *centro(c)))
    js(c).clear()
    c.hide()
    assert "window.luneHold && window.luneHold(false, 0, 0)" in js(c)


def test_en_grande_cursor_al_50_y_sin_fantasma_automatico(asistente, monkeypatch):
    import ui.companion as comp
    c = asistente
    a_grande(c, QRect(0, 0, 1000, 800))
    g = c.geometry()
    punto = QPoint(g.center().x(), g.top() + int(g.height() * 0.5))
    monkeypatch.setattr(comp.QCursor, "pos", staticmethod(lambda: punto))
    c.isVisible = lambda: True
    js(c).clear()
    c._enviar_cursor()
    nx, ny = [float(v) for v in js(c)[-1].split("luneCursor(")[1].split(",")[:2]]
    assert abs(nx) < 0.01 and abs(ny) < 0.01, "el centro de la cara está al 50 % del alto"
    transparentes = []
    monkeypatch.setattr(c, "_aplicar_transparente", lambda on: transparentes.append(on))
    c._on_cursor_respuesta(False)                     # «no está sobre el modelo»
    assert transparentes == [], "en grande no deja pasar los clics"
    c.grande_fase("fin")
    c._on_cursor_respuesta(False)
    assert transparentes == [True]


def test_en_grande_sin_sueno_ni_comentarios_automaticos(asistente, config):
    c = asistente
    config.set("avatar", "dormir_min", 5)
    c.set_comentarios_auto(True)
    c._rearmar_sueno()
    assert c._timer.isActive() and c._timer_sueno.isActive()
    a_grande(c)
    assert not c._timer.isActive(), "comentarios automáticos apagados"
    assert not c._timer_sueno.isActive(), "sueño automático apagado"
    c.aplicar_opciones()                              # ni al guardar Ajustes
    c.set_hablando(True); c.set_hablando(False)       # ni al callar
    assert not c._timer.isActive() and not c._timer_sueno.isActive()
    assert c._motivo_no_dormir() == "está en pantalla grande"
    c._comentar_auto()
    assert not c._pensando
    c.grande_fase("fin")
    assert c._timer.isActive() and c._timer_sueno.isActive(), "al acabar vuelven"


def test_en_grande_cerrar_guarda_la_posicion_de_antes(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    c.show(); c._on_cargado(True)
    c.move(40, 50)
    antes = a_grande(c, QRect(0, 0, 1280, 720))
    assert c.pos() == QPoint(0, 0)
    c.aplicar_tamano("grande")                        # en grande no mueve la ventana
    c.llevar_a_esquina()
    assert c.geometry() == QRect(0, 0, 1280, 720)
    c.close()
    assert (config.get("avatar", "companion_x"), config.get("avatar", "companion_y")) == (antes.x(), antes.y())


# ── Salvapantallas ─────────────────────────────────────────────────────────────

def test_salvapantallas_la_duerme_y_la_despierta(asistente):
    c = asistente
    a_grande(c)
    js(c).clear()
    c.set_salvapantallas(True, fondo_oscuro=True, reloj=False)
    assert js(c)[0] == 'window.luneSalvapantallas && window.luneSalvapantallas(true, {"fondo": true, "reloj": false})'
    assert c.durmiendo and "window.luneSleep && window.luneSleep(true)" in js(c), "duerme aunque la regla bloquee en grande"
    assert c.salvapantallas
    assert c._frase("dormir") is None, "callada en el salvapantallas"
    c.set_salvapantallas(False)
    assert 'window.luneSalvapantallas && window.luneSalvapantallas(false, {"fondo": true, "reloj": true})' in js(c)
    assert not c.durmiendo and "window.luneSleep && window.luneSleep(false)" in js(c)


# ── Alarma ─────────────────────────────────────────────────────────────────────

def test_alarma_con_retraso_texto_seguro_y_clic_sin_comentario(asistente, monkeypatch):
    c = asistente
    comentarios = []
    monkeypatch.setattr(c, "comentar_pantalla", lambda: comentarios.append(1))
    c._dormir()
    js(c).clear()
    c.mostrar_alarma('Gimnasio "ya" </script>\n  <b>')
    llam = llamadas(c, "luneAlarma")
    assert llam == ['window.luneAlarma && window.luneAlarma("Gimnasio \\"ya\\" </script> <b>", '
                    '{"cps": 35, "retrasoMs": 3000})']
    assert not c.durmiendo, "la alarma la despierta"
    assert c.alarma_visible
    c._clic_simple()
    assert comentarios == [], "con alarma el clic no comenta"
    c.mostrar_alarma("Otra", retraso_ms=0)
    assert llamadas(c, "luneAlarma")[-1].endswith('{"cps": 35, "retrasoMs": 0})')
    c.mostrar_alarma("", retraso_ms="nada")
    assert llamadas(c, "luneAlarma")[-1] == 'window.luneAlarma && window.luneAlarma("Alarma", {"cps": 35, "retrasoMs": 3000})'
    c.mostrar_alarma("x" * 2000)
    assert len(json.loads(llamadas(c, "luneAlarma")[-1].split("luneAlarma(", 1)[1].rsplit(", {", 1)[0])) == 500
    c.ocultar_alarma()
    assert js(c)[-1] == "window.luneAlarma && window.luneAlarma(null)"
    assert not c.alarma_visible
    c._clic_simple()
    assert comentarios == [1]


# ── Baile ──────────────────────────────────────────────────────────────────────

def test_bailar_y_pulso(asistente, config):
    c = asistente
    config.set("avatar", "dormir_min", 5)
    c.bailar(True, {"estilo": "palmas", "cambiar": True, "cambiarS": 20, "particulas": False,
                    "raro": {"x": 1}, "__proto__": 1})
    assert js(c)[-1] == ('window.luneBailar && window.luneBailar(true, '
                         '{"__proto__": 1, "cambiar": true, "cambiarS": 20, "estilo": "palmas", "particulas": false})')
    assert c.bailando
    assert not c._timer_sueno.isActive() and c._motivo_no_dormir() == "está bailando"
    c._sueno_vencido()
    assert not c.durmiendo, "bailando no se duerme sola"
    assert c.dormir() is True, "pedido (herramienta) sí"
    c._despertar(usuario=True)
    js(c).clear()
    c.pulso(124.5, 1.25, 0.8)
    assert js(c) == ["window.lunePulso && window.lunePulso(124.50, 0.2500, 0.800)"]
    c.pulso(900, -0.25, 7)
    assert js(c)[-1] == "window.lunePulso && window.lunePulso(240.00, 0.7500, 1.000)"
    n = len(js(c))
    c.pulso(float("nan"), 0, 0)
    c.pulso("x", 0, 0)
    c.pulso(0, 0, 0)
    assert len(js(c)) == n, "sin bpm válido no se manda"
    c.bailar(False)
    assert js(c)[-1] == "window.luneBailar && window.luneBailar(false)"
    assert not c.bailando and c._timer_sueno.isActive()


def test_la_animada_no_cambia_de_cara_al_bailar(asistente):
    """El clip happy lo pone la página (capa 'baile'); Python no pisa la emoción base."""
    c = asistente
    c.set_estado("sad")
    js(c).clear()
    c.bailar(True, {})
    c.bailar(False)
    assert not any("setEmocion" in x for x in js(c))
    assert c._estado_visual == "sad"


# ── Recarga de la página ───────────────────────────────────────────────────────

def test_al_recargar_repite_lo_que_estaba_a_la_vista(asistente):
    c = asistente
    a_grande(c)
    c.mostrar_alarma("Pan")                           # (la alarma despierta: antes del salvapantallas)
    c.set_salvapantallas(True, reloj=False)
    c.bailar(True, {"estilo": "rebote"})
    js(c).clear()
    c._on_cargado(True)
    assert 'window.luneGrande && window.luneGrande("entrar", {"ms": 0})' in js(c)
    assert 'window.luneSalvapantallas && window.luneSalvapantallas(true, {"fondo": true, "reloj": false})' in js(c)
    assert 'window.luneAlarma && window.luneAlarma("Pan", {"cps": 35, "retrasoMs": 0})' in js(c)
    assert 'window.luneBailar && window.luneBailar(true, {"estilo": "rebote"})' in js(c)
    assert "window.luneSleep && window.luneSleep(true)" in js(c), "el salvapantallas la tiene dormida"
    assert "window.luneSetFPS && window.luneSetFPS(30)" in js(c)


def test_eventos_de_la_pagina_solo_al_log(asistente, monkeypatch):
    import ui.companion as comp
    c = asistente
    log = []
    monkeypatch.setattr(comp, "_log", log.append)
    c._on_eventos_js(json.dumps([{"t": "grande_fase", "d": {"fase": "entrar"}},
                                 {"t": "baile", "d": {"on": True, "estilo": "palmas"}}]))
    assert any("entrar" in x for x in log) and any("palmas" in x for x in log)


def test_cerrada_no_hace_nada(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    c.show(); c._on_cargado(True)
    c.close()
    n = len(js(c))
    c.grande_fase("glide"); c.set_salvapantallas(True); c.mostrar_alarma("x"); c.ocultar_alarma()
    c.bailar(True); c.pulso(120, 0, 1); c.set_geometria(QRect(0, 0, 100, 100))
    assert len(js(c)) == n
