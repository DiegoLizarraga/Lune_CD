"""
Tests del contrato de la asistente del corte 4 en ui/companion.py (animada/VRM) y
ui/avatar_overlay.py (sprites):

- bandeja=False no crea icono; quitar_bandeja() quita el que haya;
- clic derecho → menu_pedido('principal', QPoint) al SOLTAR (no arrastrándola, ni
  en modo fantasma, ni con el menú abierto); sin menú contextual (NoContextMenu);
- ancla_menu: luneCabeza de la página → mapToGlobal; sin ella, sin respuesta o
  sin página, la geometría (35 % del alto);
- set_menu_abierto: sin arrastre, sin dormirse sola (pero «dormir» del menú sí),
  sin fantasma automático;
- aplicar_plan_juego: ocultar y volver solo si lo ocultó el juego (el usuario
  gana), fondo (orden Z), FPS del juego, comentarios automáticos parados;
- capturas y comentarios bloqueados con BusEstado.juego;
- set_fps_max (15–144, en vez del 60 fijo), set_encima (reafirmado al mostrarse),
  aplicar_tema (cadena JS de luneTema, saneada, reaplicada al recargar),
  set_comentarios_auto, llevar_a_esquina, propiedades comentarios_auto y click_through.

Qt offscreen, sin Chromium (vista web falsa que anota el JS) y sin Win32 real
(win_ventana sustituida por un doble).
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

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, pyqtSignal  # noqa: E402

from servicios.modo_juego import PlanJuego  # noqa: E402


def plan(accion="ocultar", fps=0):
    return PlanJuego(accion=accion, fps=fps, silenciar_voz=True, prioridad_baja=True,
                     recortar_ram=True, pausar_atajos=True)


def raton(tipo, boton, x=100, y=120, botones=None):
    """QMouseEvent con posición GLOBAL (x, y) (la local no se usa)."""
    from PyQt6.QtGui import QMouseEvent
    p = QPointF(x, y)
    if botones is None:
        botones = Qt.MouseButton.NoButton if tipo == QEvent.Type.MouseButtonRelease else boton
    return QMouseEvent(tipo, p, p, boton, botones, Qt.KeyboardModifier.NoModifier)


def dentro(w, dx=0, dy=0):
    """Un punto global dentro de la ventana `w` (su centro, desplazado)."""
    c = w.frameGeometry().center()
    return c.x() + dx, c.y() + dy


PRESS, MOVE, RELEASE = QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease
DER, IZQ = Qt.MouseButton.RightButton, Qt.MouseButton.LeftButton


class TrayFalso(QObject):
    """QSystemTrayIcon falso: anota cuántos se crean y si se ven."""
    creados = []
    activated = pyqtSignal(object)

    def __init__(self, *args):
        super().__init__(args[-1] if args and isinstance(args[-1], QObject) else None)
        self.visible = False
        self.menu = None
        TrayFalso.creados.append(self)

    @staticmethod
    def isSystemTrayAvailable(): return True
    def setToolTip(self, t): self.tooltip = t
    def setContextMenu(self, m): self.menu = m
    def show(self): self.visible = True
    def hide(self): self.visible = False


class WinVentanaFalsa:
    def __init__(self):
        self.llamadas = []
    def set_encima(self, hwnd, on, user32=None): self.llamadas.append(("encima", bool(on))); return True
    def al_fondo(self, hwnd, user32=None): self.llamadas.append(("fondo",)); return True


@pytest.fixture
def win_ventana(monkeypatch):
    """win_ventana sin Win32 y las asistentes creyendo que hay HWND de verdad."""
    import servicios.win_ventana as wv
    import ui.avatar_overlay as ao
    falsa = WinVentanaFalsa()
    monkeypatch.setattr(wv, "set_encima", falsa.set_encima)
    monkeypatch.setattr(wv, "al_fondo", falsa.al_fondo)
    monkeypatch.setattr(ao, "_ventana_nativa", lambda: True)
    if HAY_WEBENGINE:
        import ui.companion as comp
        monkeypatch.setattr(comp, "_ventana_nativa", lambda: True)
    return falsa


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


# ── Asistente web (ui/companion.py) ──────────────────────────────────────────────

@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso: anota el JS; `pagina.cabeza` decide qué contesta
    luneCabeza (un JSON, None o "nunca" = no contesta)."""
    if not HAY_WEBENGINE:
        pytest.skip("la asistente web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []; self.cabeza = None

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneCabeza" in codigo:
                if self.cabeza != "nunca":
                    cb(self.cabeza)
            elif "luneEventos" in codigo:
                cb("[]")
            else:
                cb(None)

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
def animada(qapp, web_falso, config, lune_activa):
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


def test_companion_bandeja_opcional_y_quitar_bandeja(qapp, web_falso, config, lune_activa, monkeypatch):
    import ui.companion as comp
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(comp, "QSystemTrayIcon", TrayFalso)
    TrayFalso.creados = []
    sin = CompanionFlotante(config, ai_manager=None, bandeja=False)
    con = CompanionFlotante(config, ai_manager=None)
    try:
        assert sin.tray is None and len(TrayFalso.creados) == 1
        tray = con.tray
        assert tray is TrayFalso.creados[0] and tray.visible and tray.menu is not None
        con.quitar_bandeja()
        assert con.tray is None and con.act_auto is None and not tray.visible
        con.quitar_bandeja()                            # dos veces: nada
        # sin bandeja siguen funcionando lo que antes tocaba sus casillas
        sin.set_click_through(True); sin.set_click_through(False)
        sin.aplicar_opciones()
    finally:
        sin.close(); con.close()


def test_companion_sin_menu_contextual(animada):
    assert animada.web.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu
    assert animada.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu


def test_companion_clic_derecho_pide_el_menu_al_soltar(animada):
    c = animada
    pedidos = []
    c.menu_pedido.connect(lambda tipo, p: pedidos.append((tipo, p)))
    x, y = dentro(c, -10, -20)
    c.eventFilter(c.web, raton(PRESS, DER, x, y))
    assert pedidos == []                                # al pulsar, todavía no
    c.eventFilter(c.web, raton(RELEASE, DER, x, y))
    assert pedidos == [("principal", QPoint(x, y))]
    assert c._arrastre is None and not c._pensando      # ni arrastre ni comentario
    # pulsa sobre ella y suelta fuera: se arrepintió
    g = c.frameGeometry()
    c.eventFilter(c.web, raton(PRESS, DER, x, y))
    c.eventFilter(c.web, raton(RELEASE, DER, g.right() + 50, y))
    assert len(pedidos) == 1


def test_companion_clic_derecho_no_abre_arrastrando_fantasma_ni_abierto(animada):
    c = animada
    pedidos = []
    c.menu_pedido.connect(lambda tipo, p: pedidos.append(tipo))
    x, y = dentro(c)
    # arrastrándola con el izquierdo
    c.eventFilter(c.web, raton(PRESS, IZQ, x, y))
    c.eventFilter(c.web, raton(MOVE, Qt.MouseButton.NoButton, x + 40, y, botones=IZQ))
    assert c._arrastre and c._arrastre["movido"]
    x, y = dentro(c)                                     # la ventana se movió con el arrastre
    c.eventFilter(c.web, raton(PRESS, DER, x, y, botones=IZQ | DER))
    c.eventFilter(c.web, raton(RELEASE, DER, x, y, botones=IZQ))
    assert pedidos == [] and c._arrastre and c._arrastre["movido"]   # el soltar derecho no corta el arrastre
    c.eventFilter(c.web, raton(RELEASE, IZQ, x, y))

    def clic_derecho():
        px, py = dentro(c)
        c.eventFilter(c.web, raton(PRESS, DER, px, py))
        c.eventFilter(c.web, raton(RELEASE, DER, px, py))

    # menú ya abierto
    c.set_menu_abierto(True)
    clic_derecho()
    c.set_menu_abierto(False)
    # modo fantasma total
    c._click_through = True
    clic_derecho()
    c._click_through = False
    assert pedidos == []
    clic_derecho()
    assert pedidos == ["principal"]


def test_companion_menu_abierto_bloquea_arrastre_sueno_y_fantasma(animada, monkeypatch):
    c = animada
    transparente = []
    monkeypatch.setattr(c, "_aplicar_transparente", lambda on: transparente.append(on))
    assert c._timer_sueno.isActive()
    c.set_menu_abierto(True)
    assert transparente == [False] and not c._timer_sueno.isActive()
    c.eventFilter(c.web, raton(PRESS, IZQ))
    assert c._arrastre is None                          # sin arrastre ni caricia
    c._on_cursor_respuesta(False)                        # la página: «no estás sobre ella»
    assert transparente == [False]                       # con el menú abierto no se vuelve fantasma
    assert c._motivo_no_dormir() == "el menú está abierto"
    c._sueno_vencido()
    assert not c.durmiendo
    assert c._motivo_no_dormir(forzado=True) == ""      # «Dormir» del propio menú sí
    c.set_menu_abierto(False)
    assert c._timer_sueno.isActive() and c._motivo_no_dormir() == ""
    assert c.dormir() is True and c.durmiendo


def test_companion_ancla_con_lune_cabeza(animada):
    c = animada
    c.web.page().cabeza = json.dumps({"x": 120.4, "y": 60, "r": 30})
    puntos = []
    c.ancla_menu(puntos.append)
    assert puntos == [c.web.mapToGlobal(QPoint(120, 60))]
    assert any("luneCabeza" in x for x in js(c))
    # fuera de la ventana: se recorta a ella
    c.web.page().cabeza = json.dumps({"x": -50, "y": 99999})
    c.ancla_menu(puntos.append)
    assert puntos[-1] == c.web.mapToGlobal(QPoint(0, c.web.height() - 1))


def geometria(c):
    g = c.geometry()
    return QPoint(g.x() + g.width() // 2, g.y() + round(g.height() * 0.35))


@pytest.mark.parametrize("respuesta", [None, "no es json", json.dumps({"x": "NaN"}), json.dumps([1, 2])])
def test_companion_ancla_sin_lune_cabeza_usa_la_geometria(animada, respuesta):
    c = animada
    c.web.page().cabeza = respuesta
    puntos = []
    c.ancla_menu(puntos.append)
    assert puntos == [geometria(c)]


def test_companion_ancla_si_la_pagina_no_contesta_o_no_esta(animada, qapp):
    import time
    c = animada
    c.web.page().cabeza = "nunca"
    puntos = []
    c.ancla_menu(puntos.append)
    assert puntos == []
    fin = time.monotonic() + 2
    while not puntos and time.monotonic() < fin:
        qapp.processEvents(); time.sleep(0.01)
    assert puntos == [geometria(c)]
    c._pagina_lista = False                             # página recargándose: en el acto
    c.ancla_menu(puntos.append)
    assert len(puntos) == 2
    c.ancla_menu("no llamable")                          # se ignora


def test_companion_plan_juego_oculta_y_vuelve(animada):
    c = animada
    assert c.isVisible()
    c.aplicar_plan_juego(plan("ocultar"))
    assert not c.isVisible()
    c.aplicar_plan_juego(None)
    assert c.isVisible()


def test_companion_si_el_usuario_la_saca_en_partida_gana_el(animada):
    c = animada
    c.aplicar_plan_juego(plan("ocultar", fps=0))
    c.show()                                            # el usuario la saca a mano
    assert c.isVisible() and c._fps_efectivo() == 60    # con sus FPS de siempre
    c.aplicar_plan_juego(plan("ocultar", fps=0))        # el mismo plan otra vez (recargar): no la oculta
    assert c.isVisible()
    c.hide()                                            # y si la esconde él…
    c.aplicar_plan_juego(None)
    assert not c.isVisible()                            # …al acabar no reaparece


def test_companion_oculta_antes_de_la_partida_sigue_oculta(animada):
    c = animada
    c.hide()
    c.aplicar_plan_juego(plan("ocultar"))
    c.aplicar_plan_juego(None)
    assert not c.isVisible()


def test_companion_plan_fondo_y_encima(animada, win_ventana, config):
    c = animada
    c.aplicar_plan_juego(plan("fondo", fps=20))
    assert win_ventana.llamadas[-1] == ("fondo",)
    assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(20)"
    c.aplicar_plan_juego(None)
    assert win_ventana.llamadas[-1] == ("encima", True)
    assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(60)"
    # set_encima se guarda y se reafirma al mostrarse
    c.set_encima(False)
    assert config.get("avatar", "siempre_encima") is False and win_ventana.llamadas[-1] == ("encima", False)
    c.hide(); win_ventana.llamadas.clear()
    c.show()
    assert ("encima", False) in win_ventana.llamadas
    assert c.siempre_encima is False


def test_companion_plan_nada_con_fps_cero_pausa_la_pagina(animada):
    c = animada
    c.aplicar_plan_juego(plan("nada", fps=0))
    assert c.isVisible() and js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(0)"


def test_companion_fps_max_en_vez_del_60_fijo(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    config.set("avatar", "fps_max", 90)
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    try:
        c.show()
        assert "window.luneSetFPS && window.luneSetFPS(90)" in js(c)
        assert not any("luneSetFPS(60)" in x for x in js(c))
        c.set_fps_max(500)
        assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(144)"
        assert config.get("avatar", "fps_max") == 144
        c.set_fps_max(3)
        assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(15)"
        c.set_fps_max("mucho")                          # se ignora
        assert config.get("avatar", "fps_max") == 15
        c.hide()
        assert js(c)[-1] == "window.luneSetFPS && window.luneSetFPS(0)"
        n = len(js(c))
        c._on_cargado(True)                              # recarga oculta: no se despierta el render
        assert not any("luneSetFPS" in x for x in js(c)[n:])
    finally:
        c.close()


def _vrm_minimo() -> bytes:
    """GLB mínimo con la extensión VRMC_vrm (lo que nucleo/vrm.py valida)."""
    import struct
    datos = json.dumps({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                        "extensions": {"VRMC_vrm": {"meta": {"name": "Luna"}}}}).encode()
    datos += b" " * ((4 - len(datos) % 4) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(datos))
            + struct.pack("<II", len(datos), 0x4E4F534A) + datos)


def test_vrm_fps_cero_en_partida_para_tambien_el_cursor(qapp, web_falso, config, lune_activa,
                                                        tmp_path, monkeypatch):
    from nucleo import vrm
    from ui.companion import CompanionFlotante
    carpeta = tmp_path / "modelo_vrm"
    carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(_vrm_minimo())
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    config.set("avatar", "render", "vrm")
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    try:
        assert c.render == "vrm"
        c.show(); c._on_cargado(True)
        assert c._timer_cursor.isActive()
        c.aplicar_plan_juego(plan("nada", fps=0))
        assert not c._timer_cursor.isActive() and js(c)[-1].endswith("luneSetFPS(0)")
        c.aplicar_plan_juego(None)
        assert c._timer_cursor.isActive() and js(c)[-1].endswith("luneSetFPS(60)")
        c.web.page().cabeza = json.dumps({"x": 10, "y": 20, "r": 5})
        puntos = []
        c.ancla_menu(puntos.append)
        assert puntos == [c.web.mapToGlobal(QPoint(10, 20))]
    finally:
        c.close()


def test_companion_capturas_y_comentarios_bloqueados_en_juego(animada, monkeypatch):
    from nucleo import datos
    from nucleo.estado_asistente import BusEstado
    from PIL import ImageGrab
    c = animada
    # 10.9: la asistente comenta solo con la nube; sin clave ni lo intenta. Hermético: no
    # depende de que el datos.json de este equipo tenga clave.
    monkeypatch.setattr(datos, "openrouter_key", lambda: "sk-prueba")

    def no_capturar(*a, **k):
        raise AssertionError("en modo juego no se captura la pantalla")

    monkeypatch.setattr(ImageGrab, "grab", no_capturar)
    sondeos = []
    monkeypatch.setattr(c, "_sondear", lambda: sondeos.append(1))
    bus = BusEstado()
    c.set_bus_estado(bus)
    bus.actualizar(juego=True)
    assert c._capturar() is None
    c._comentar_auto()
    assert not c._pensando and sondeos == [] and not any("pensando" in x for x in js(c))
    c.comentar_pantalla()                                # el manual contesta en la burbuja
    assert not c._pensando and sondeos == []
    assert "En modo juego no miro la pantalla." in js(c)[-1]
    # con el plan aplicado (sin bus) también
    bus.actualizar(juego=False)
    c.aplicar_plan_juego(plan("nada", fps=30))
    c.comentar_pantalla()
    assert not c._pensando and sondeos == []
    c.aplicar_plan_juego(None)
    monkeypatch.setattr(c, "_capturar", lambda: "captura")
    c.comentar_pantalla()                                # sin partida: sí
    assert c._pensando and sondeos == [1]


def test_companion_comentarios_auto_parados_en_juego_y_publicos(animada, config):
    c = animada
    assert c.comentarios_auto is False and not c._timer.isActive()
    c.set_comentarios_auto(True)
    assert config.get("avatar", "comentarios_cada_min") == 3 and c._timer.isActive() and c.comentarios_auto
    c.aplicar_plan_juego(plan("nada", fps=30))
    assert not c._timer.isActive() and c.comentarios_auto      # parados, pero siguen puestos
    c.aplicar_plan_juego(None)
    assert c._timer.isActive() and c._timer.interval() == 3 * 60_000
    c.set_comentarios_auto(False)
    assert config.get("avatar", "comentarios_cada_min") == 0 and not c._timer.isActive()
    config.set("avatar", "comentarios_cada_min", 10)
    c.set_comentarios_auto(True)                          # conserva el intervalo que había
    assert c._timer.interval() == 10 * 60_000


def test_companion_tema_cadena_js_saneada_y_reaplicada(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None, bandeja=False)
    try:
        tema = json.dumps({"--cyan-500": "#ff00aa", "--cyan-500-rgb": "255 0 170",
                           "--x": 'red"); alert(1); ("', "color": "#fff", "--num": 5})
        c.aplicar_tema(tema)                            # página aún sin cargar: se guarda
        assert not any("luneTema" in x for x in js(c))
        c.show(); c._on_cargado(True)
        esperado = ('window.luneTema && window.luneTema('
                    '{"--cyan-500": "#ff00aa", "--cyan-500-rgb": "255 0 170"})')
        assert esperado in js(c)
        c.aplicar_tema("null")
        assert js(c)[-1] == "window.luneTema && window.luneTema(null)"
        n = len(js(c))
        c.aplicar_tema("esto no es json")               # se ignora (y se queda el anterior)
        c.aplicar_tema("[1, 2]")
        assert len(js(c)) == n
        js(c).clear()
        c._on_cargado(True)                              # la página recarga: se reaplica
        assert "window.luneTema && window.luneTema(null)" in js(c)
        c.aplicar_tema({"--blue-500": "#112233"})
        assert js(c)[-1] == 'window.luneTema && window.luneTema({"--blue-500": "#112233"})'
    finally:
        c.close()


def test_companion_llevar_a_esquina_y_propiedades(animada, config):
    c = animada
    c.move(5, 5)
    c.llevar_a_esquina()
    g = c.screen().availableGeometry()
    assert (c.x(), c.y()) == (g.right() - c.width() - 24, g.bottom() - c.height() - 24)
    assert (config.get("avatar", "companion_x"), config.get("avatar", "companion_y")) == (c.x(), c.y())
    assert c.click_through is False
    c.set_click_through(True)
    assert c.click_through is True
    c.set_click_through(False)


# ── Asistente de sprites (ui/avatar_overlay.py) ──────────────────────────────────

@pytest.fixture
def sprites(qapp, lune_activa, config):
    from ui.avatar_overlay import AvatarOverlay
    ov = AvatarOverlay(config=config, bandeja=False)
    ov.show()
    yield ov
    ov.close()


def test_sprites_bandeja_opcional_y_quitar_bandeja(qapp, lune_activa, monkeypatch):
    import ui.avatar_overlay as ao
    monkeypatch.setattr(ao, "QSystemTrayIcon", TrayFalso)
    TrayFalso.creados = []
    sin = ao.AvatarOverlay(bandeja=False)
    con = ao.AvatarOverlay()
    try:
        assert sin.tray is None and len(TrayFalso.creados) == 1
        tray = con.tray
        assert tray.visible
        con.quitar_bandeja()
        assert con.tray is None and con.act_fantasma is None and not tray.visible
    finally:
        sin.close(); con.close()


def test_sprites_clic_derecho_y_politica(sprites):
    ov = sprites
    assert ov.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu
    assert ov.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    pedidos = []
    ov.menu_pedido.connect(lambda tipo, p: pedidos.append((tipo, p)))
    x, y = dentro(ov, 5, -30)
    ov.mousePressEvent(raton(PRESS, DER, x, y))
    assert pedidos == []
    ov.mouseReleaseEvent(raton(RELEASE, DER, x, y))
    assert pedidos == [("principal", QPoint(x, y))]
    ov.set_menu_abierto(True)
    ov.mousePressEvent(raton(PRESS, DER, x, y)); ov.mouseReleaseEvent(raton(RELEASE, DER, x, y))
    ov.set_menu_abierto(False)
    ov._arrastrando = True                               # la física dice que la mueven
    ov.mousePressEvent(raton(PRESS, DER, x, y)); ov.mouseReleaseEvent(raton(RELEASE, DER, x, y))
    ov._arrastrando = False
    ov.mousePressEvent(raton(PRESS, DER, x, y))          # suelta fuera
    ov.mouseReleaseEvent(raton(RELEASE, DER, ov.frameGeometry().right() + 40, y))
    assert len(pedidos) == 1


def test_sprites_menu_abierto_bloquea_arrastre_y_sueno(sprites):
    ov = sprites
    ov.set_menu_abierto(True)
    ov.mousePressEvent(raton(PRESS, IZQ))
    assert ov._pulsado is None
    assert ov._motivo_no_dormir() == "el menú está abierto" and ov._motivo_no_dormir(forzado=True) == ""
    ov.set_menu_abierto(False)
    ov.mousePressEvent(raton(PRESS, IZQ))
    assert ov._pulsado is not None
    ov.mouseReleaseEvent(raton(RELEASE, IZQ))


def test_sprites_ancla_por_geometria(sprites):
    ov = sprites
    puntos = []
    ov.ancla_menu(puntos.append)
    fig = ov._rect_figura(ov.x(), ov.y())
    assert puntos == [QPoint(fig.x() + fig.width() // 2, fig.y() + round(fig.height() * 0.35))]


def test_sprites_plan_juego(sprites, win_ventana):
    ov = sprites
    assert ov._fisica_permitida
    ov.aplicar_plan_juego(plan("ocultar"))
    assert not ov.isVisible() and not ov._fisica_permitida
    ov.aplicar_plan_juego(None)
    assert ov.isVisible() and ov._fisica_permitida
    win_ventana.llamadas.clear()
    ov.aplicar_plan_juego(plan("fondo"))
    assert ov.isVisible() and win_ventana.llamadas[-1] == ("encima", False) and not ov._fisica_permitida
    ov.aplicar_plan_juego(None)
    assert win_ventana.llamadas[-1] == ("encima", True) and ov._fisica_permitida
    # la física que ya estaba apagada (ajuste) sigue apagada al acabar
    ov.set_habilitado_fisica(False)
    ov.aplicar_plan_juego(plan("nada")); ov.aplicar_plan_juego(None)
    assert not ov._fisica_permitida


def test_sprites_el_usuario_gana_en_partida(sprites):
    ov = sprites
    ov.aplicar_plan_juego(plan("ocultar"))
    ov.show()
    ov.aplicar_plan_juego(plan("ocultar"))
    assert ov.isVisible()
    ov.aplicar_plan_juego(None)
    assert ov.isVisible()


def test_sprites_encima_fps_comentarios_tema_y_esquina(sprites, win_ventana, config):
    ov = sprites
    ov.set_encima(False)
    assert config.get("avatar", "siempre_encima") is False and win_ventana.llamadas[-1] == ("encima", False)
    ov.hide(); win_ventana.llamadas.clear(); ov.show()
    assert win_ventana.llamadas == [("encima", False)]            # reafirmado al mostrarse
    ov.set_fps_max(1000)
    assert config.get("avatar", "fps_max") == 144
    ov.set_comentarios_auto(True)
    assert ov.comentarios_auto is False                           # los sprites no comentan la pantalla
    ov.burbuja_texto("hola")
    ov.aplicar_tema(json.dumps({"--cyan-500": "#FF00AA"}))
    assert "#FF00AA" in ov._burbuja.styleSheet()
    ov.aplicar_tema("basura")                                     # se ignora
    assert "#FF00AA" in ov._burbuja.styleSheet()
    ov.aplicar_tema(None)
    assert "#FF00AA" not in ov._burbuja.styleSheet()
    ov.move(3, 3)
    ov.llevar_a_esquina()
    assert config.get("avatar", "overlay_x") == ov.x() + ov._margen[0]
    assert ov.click_through is False


# ── Contrato común ─────────────────────────────────────────────────────────────

def test_contrato_comun_de_las_dos_asistentes():
    import inspect
    from ui.avatar_overlay import AvatarOverlay
    clases = [AvatarOverlay]
    if HAY_WEBENGINE:
        from ui.companion import CompanionFlotante
        clases.append(CompanionFlotante)
    for clase in clases:
        for metodo in ("quitar_bandeja", "ancla_menu", "set_menu_abierto", "aplicar_plan_juego",
                       "aplicar_tema", "set_encima", "set_fps_max", "set_comentarios_auto",
                       "llevar_a_esquina"):
            assert callable(getattr(clase, metodo)), (clase.__name__, metodo)
        for prop in ("comentarios_auto", "click_through"):
            assert isinstance(getattr(clase, prop), property), (clase.__name__, prop)
        assert inspect.signature(clase.__init__).parameters["bandeja"].default is True
        assert hasattr(clase, "menu_pedido")
