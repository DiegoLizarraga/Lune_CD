"""
Tests de la integración del corte 3 en las asistentes en escritorio:

- ui/companion.py (animada y VRM): los eventos de la página (arrastre, soltar,
  caricia, mareo, dormir, despertar, estado) → frase de lune_core/frases_asistente
  en la burbuja (window.comentar(t, 3500)) con cooldown, sin pisar una respuesta
  de la IA; «aparecer» al mostrarse con la página cargada; sueño en los dos
  renders con nucleo/sueno.ReglaSueno (no se duerme arrastrándola, hablando,
  pensando ni en llamada); dormir()/despertar()/durmiendo para las herramientas;
  un «duérmete» no lo deshace la propia respuesta; aplicar_params_vrm solo en
  VRM; recargar_modelo cambia el personaje de las frases.
- ui/avatar_overlay.py (sprites): física (arrastre, caras por velocidad, mareo →
  cara mareada + frase), sprite compuesto girado con su máscara (crítica c.8),
  física apagada con vídeo o en modo juego, sueño con cara dormida y frases.
- Las páginas cargan lune_packs.js y companion.py ya no lo inyecta.

Qt offscreen, sin Chromium (vista web falsa que anota el JS), con reloj y azar
fijos para las frases.
"""
import json
import struct
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

# QtWebEngine tiene que importarse ANTES de crear la QApplication (la crea conftest).
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from lune_core import frases_asistente as fm  # noqa: E402


class Reloj:
    """Reloj monótono falso para el cooldown de las frases."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avanzar(self, s: float) -> None:
        self.t += s


class AzarFijo:
    """random.Random de mentira: random() siempre devuelve lo mismo.
    0.0 → el dado siempre sale (y la Bolsa saca en orden fijo); 0.99 → solo p = 1."""

    def __init__(self, valor: float):
        self.valor = valor

    def random(self) -> float:
        return self.valor


def frases(reloj=None, azar=0.0, personaje=None):
    return fm.FrasesAsistente(personaje, reloj=reloj or Reloj(), rng=AzarFijo(azar))


# ── Las páginas ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pagina", ["companion.html", "companion_vrm.html"])
def test_las_paginas_cargan_lune_packs(pagina):
    html = (RAIZ / "ui_web" / pagina).read_text("utf-8")
    assert '<script src="lune_packs.js"></script>' in html
    # junto a lune_sfx.js (lo usa para sonar) y antes del módulo de la página
    assert html.index("lune_sfx.js") < html.index("lune_packs.js") < html.index('<script type="module">')
    assert (RAIZ / "ui_web" / "lune_packs.js").is_file()


def test_companion_ya_no_inyecta_lune_packs():
    src = (RAIZ / "ui" / "companion.py").read_text("utf-8")
    assert "createElement('script')" not in src and "el.src = 'lune_packs.js'" not in src


# ── Asistente web (ui/companion.py) ──────────────────────────────────────────────

def _vrm_minimo() -> bytes:
    """GLB mínimo con la extensión VRMC_vrm (lo que nucleo/vrm.py valida)."""
    js = json.dumps({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                     "extensions": {"VRMC_vrm": {"meta": {"name": "Luna", "authors": ["Diego"]}}}}).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    return (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js))
            + struct.pack("<II", len(js), 0x4E4F534A) + js)


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso: anota el JS (runJavaScript) y responde a luneEventos()."""
    if not HAY_WEBENGINE:
        pytest.skip("la asistente web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QObject, QUrl, pyqtSignal
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        def __init__(self):
            super().__init__(); self.js = []; self.cola = []

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                lote, self.cola = self.cola, []
                cb(json.dumps(lote))
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


@pytest.fixture
def config(tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    return cfg


@pytest.fixture
def animada(qapp, web_falso, config, lune_activa):
    """CompanionFlotante animada, visible y con la página «cargada»; frases con
    reloj falso y el dado que siempre sale."""
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None)
    c.reloj = Reloj()
    c._frases = frases(c.reloj)
    c._aparecer_pendiente = False            # el «aparecer» se prueba aparte
    c.show()
    c._on_cargado(True)
    c.web.page().js.clear()
    yield c
    c.close()


@pytest.fixture
def carpeta_vrm(tmp_path, monkeypatch):
    from nucleo import vrm
    carpeta = tmp_path / "modelo_vrm"
    carpeta.mkdir()
    (carpeta / "a.vrm").write_bytes(_vrm_minimo())
    (carpeta / "b.vrm").write_bytes(_vrm_minimo() + b"")
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    return carpeta


@pytest.fixture
def config_vrm(config):
    config.set("avatar", "render", "vrm")
    return config


def js_de(c) -> str:
    return "\n".join(c.web.page().js)


def comentarios(c) -> list:
    """Textos que la asistente puso en la burbuja con window.comentar(t, 3500)."""
    out = []
    for codigo in c.web.page().js:
        if codigo.startswith("window.comentar && window.comentar(") and codigo.endswith(", 3500)"):
            out.append(json.loads(codigo[len("window.comentar && window.comentar("):-len(", 3500)")]))
    return out


def evento(c, tipo, datos=None):
    """Un evento de la página por el camino de verdad (luneEventos → evento_js)."""
    c._on_eventos_js(json.dumps([{"t": tipo, "d": datos if datos is not None else {}}]))


def test_eventos_de_la_pagina_dicen_su_frase_con_cooldown(animada):
    c = animada
    evento(c, "arrastre", {"on": True})
    dichas = comentarios(c)
    assert len(dichas) == 1 and dichas[0] in fm.FRASES_BASE["arrastre"]
    # cooldown global de 20 s: soltar y caricia callan…
    evento(c, "arrastre", {"on": False})
    evento(c, "caricia", {"lado": 1})
    assert len(comentarios(c)) == 1
    # …salvo el mareo (prioritario)
    evento(c, "mareo", {"inversiones": 4, "eje": "x"})
    assert comentarios(c)[-1] in fm.FRASES_BASE["mareo"] and len(comentarios(c)) == 2
    c.reloj.avanzar(20.5)
    evento(c, "arrastre", {"on": False})
    assert comentarios(c)[-1] in fm.FRASES_BASE["soltar"]
    c.reloj.avanzar(20.5)
    evento(c, "caricia", {"lado": -1})
    assert comentarios(c)[-1] in fm.FRASES_BASE["caricia"]


def test_con_el_dado_en_contra_solo_habla_el_mareo(animada):
    c = animada
    c._frases = frases(c.reloj, azar=0.99)
    for tipo, datos in (("arrastre", {"on": True}), ("arrastre", {"on": False}), ("caricia", {})):
        evento(c, tipo, datos)
    assert comentarios(c) == []
    evento(c, "mareo")
    assert len(comentarios(c)) == 1 and comentarios(c)[0] in fm.FRASES_BASE["mareo"]


def test_la_frase_no_pisa_una_respuesta_de_la_ia(animada):
    c = animada
    c.burbuja_texto("Te respondo esto")               # streaming de la IA en curso
    evento(c, "caricia")
    assert comentarios(c) == [] and not c._frases.en_cooldown()   # ni gasta el cooldown
    c.burbuja_fin(5000)                               # la deja 5 s a la vista
    evento(c, "mareo")
    assert comentarios(c) == []
    c._burbuja_ia_hasta = time.monotonic() - 1        # ya se ocultó
    evento(c, "caricia")
    assert comentarios(c) and comentarios(c)[0] in fm.FRASES_BASE["caricia"]
    # el comentario de pantalla también reserva la burbuja
    c.reloj.avanzar(30)
    c._decir("Qué ordenado.", "happy")
    evento(c, "mareo")
    assert comentarios(c)[-1] in fm.FRASES_BASE["caricia"]


def test_aparecer_al_mostrarse_con_la_pagina_cargada(qapp, web_falso, config, lune_activa):
    from ui.companion import CompanionFlotante
    c = CompanionFlotante(config, ai_manager=None)
    c.reloj = Reloj()
    c._frases = frases(c.reloj)
    try:
        c.show()
        assert comentarios(c) == []                   # sin página no hay burbuja
        c._on_cargado(True)
        assert len(comentarios(c)) == 1 and comentarios(c)[0] in fm.FRASES_BASE["aparecer"]
        c._on_cargado(True)                           # una vez por aparición
        assert len(comentarios(c)) == 1
        c.hide(); c.reloj.avanzar(25); c.show()
        assert len(comentarios(c)) == 2
    finally:
        c.close()


def test_dormir_y_despertar_publicos_en_la_animada(animada):
    from nucleo import sueno
    from nucleo.estado_asistente import BusEstado
    c = animada
    bus = BusEstado()
    c.set_bus_estado(bus)
    assert c.durmiendo is False
    assert c.dormir() is True and c.durmiendo is True
    assert "luneSleep(true)" in js_de(c) and bus.actual().durmiendo is True
    assert c.dormir() is True                         # ya dormía
    assert c.despertar() is True and c.durmiendo is False
    assert "luneSleep(false)" in js_de(c) and bus.actual().durmiendo is False
    # las herramientas del modelo (nucleo/sueno.py) usan ese contrato
    assert sueno.herramienta_dormir({}, {"asistente": c}) == "Vale, me echo una siesta. Una caricia y vuelvo."
    assert c.durmiendo is True
    assert sueno.herramienta_dormir({}, {"asistente": c}) == "Ya estoy dormida. Shh."
    assert sueno.herramienta_despertar({}, {"asistente": c}) == "Ya estoy despierta. ¿Qué pasa?"
    assert c.durmiendo is False
    c.close()
    assert c.dormir() is False and c.despertar() is False


def test_no_se_duerme_arrastrando_pensando_ni_en_llamada(animada):
    from nucleo import sueno
    from nucleo.estado_asistente import BusEstado
    from ui.companion import REINTENTO_SUENO_MS
    c = animada
    c._arrastre = {"movido": True}
    assert c.dormir() is False and not c.durmiendo
    assert sueno.herramienta_dormir({}, {"asistente": c})[0] is False
    c._sueno_vencido()                                # vence el sueño arrastrándola: se reintenta
    assert not c.durmiendo and c._timer_sueno.isActive() and c._timer_sueno.interval() == REINTENTO_SUENO_MS
    c._arrastre = None
    c._pensando = True
    assert c.dormir() is False
    c._pensando = False
    bus = BusEstado()
    c.set_bus_estado(bus)
    bus.actualizar(llamada=True)
    assert c.dormir() is False
    c._sueno_vencido()
    assert not c.durmiendo
    bus.actualizar(llamada=False)
    c._sueno_vencido()
    assert c.durmiendo


def test_hablando_no_se_duerme_sola_y_el_duermete_espera_a_que_calle(animada):
    c = animada
    c.set_hablando(True)
    c._sueno_vencido()
    assert not c.durmiendo                            # la regla: nunca con la voz sonando
    assert c.dormir() is True and not c.durmiendo     # pedido: se dormirá al callar
    c.set_hablando(False)
    assert c._timer_sueno_pedido.isActive()
    c._volver_a_dormir()                              # vence la pausa tras la voz
    assert c.durmiendo


def test_la_respuesta_a_un_duermete_no_la_desvela(animada):
    c = animada
    assert c.dormir() is True and c.durmiendo
    c.web.page().js.clear()
    # la voz de la respuesta la despierta en la página: sin frase de despertar
    c.set_hablando(True)
    evento(c, "despertar")
    assert not c.durmiendo and comentarios(c) == []
    c.set_estado("happy")                             # emoción de la misma respuesta
    c.set_hablando(False)
    assert c._timer_sueno_pedido.isActive()
    c._volver_a_dormir()
    assert c.durmiendo
    # si el usuario la toca, se olvida el «duérmete»
    c._despertar(usuario=True)
    assert not c.durmiendo and c._sueno_pedido_t is None
    c._volver_a_dormir()
    assert not c.durmiendo
    # y pasada la gracia tampoco vuelve a dormirse
    c.dormir()
    c._sueno_pedido_t = time.monotonic() - 60
    c.set_estado("happy")
    c._volver_a_dormir()
    assert not c.durmiendo


def test_sueno_por_inactividad_en_la_animada(animada, config):
    from ui.companion import REINTENTO_SUENO_MS
    c = animada
    assert c._timer_sueno.isActive() and c._timer_sueno.interval() == 10 * 60_000
    config.set("avatar", "dormir_min", 2)
    c.aplicar_opciones()
    assert c._timer_sueno.interval() == 2 * 60_000
    # a mitad de una actividad (pensando la respuesta) no; una emoción vieja sí
    c.set_estado("thinking")
    c._sueno_vencido()
    assert not c.durmiendo and c._timer_sueno.interval() == REINTENTO_SUENO_MS
    c.set_estado("happy")
    c._sueno_vencido()
    assert c.durmiendo and "luneSleep(true)" in js_de(c)
    assert not c._timer_sueno.isActive()              # dormida no cuenta
    c._raton_press(_Raton())                          # tocarla la despierta y rearma
    assert not c.durmiendo and c._timer_sueno.interval() == 2 * 60_000
    c._raton_release(_Raton())


class _Raton:
    def __init__(self, x=100, y=100):
        from PyQt6.QtCore import QPointF, Qt
        self._p = QPointF(x, y); self._b = Qt.MouseButton.LeftButton

    def button(self): return self._b
    def buttons(self): return self._b
    def globalPosition(self): return self._p


def test_eventos_dormir_despertar_y_estado_de_la_pagina(animada):
    from nucleo.estado_asistente import BusEstado
    c = animada
    bus = BusEstado()
    c.set_bus_estado(bus)
    evento(c, "dormir")
    assert c.durmiendo and bus.actual().durmiendo is True and not c._timer_sueno.isActive()
    assert comentarios(c)[-1] in fm.FRASES_BASE["dormir"]
    c.reloj.avanzar(25)
    evento(c, "despertar")
    assert not c.durmiendo and bus.actual().durmiendo is False and c._timer_sueno.isActive()
    assert comentarios(c)[-1] in fm.FRASES_BASE["despertar"]
    c.set_emocion("happy")
    assert bus.actual().emocion == "happy"
    evento(c, "estado", {"nombre": "normal"})       # el gesto acabó en la página
    assert c._estado_visual == "normal" and bus.actual().emocion == "neutral"


def test_aplicar_params_vrm_solo_en_vrm(qapp, web_falso, config_vrm, carpeta_vrm, monkeypatch):
    from nucleo import personajes, vrm
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune", "vrm": "a.vrm"})
    (carpeta_vrm / "a.lune.json").write_text(json.dumps({"luz": 2, "altura": 0.1}), "utf-8")
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        assert c.render == "vrm"
        c._on_cargado(True)                           # al cargar la página
        llamadas = [j for j in c.web.page().js if "window.luneParams" in j]
        assert len(llamadas) == 1
        esperado = vrm.params_modelo_json("a.vrm", config_vrm)
        assert llamadas[0] == f"window.luneParams && window.luneParams({json.dumps(esperado)})"
        params = json.loads(json.loads(llamadas[0][len("window.luneParams && window.luneParams("):-1]))
        assert params["luz"] == 2.0 and params["altura"] == 0.1 and params["pesoCabeza"] == 1.0
        # los pesos globales de Ajustes también llegan (aplicar_opciones)
        config_vrm.set("avatar", "seguir_cursor", False)
        c.web.page().js.clear()
        c.aplicar_opciones()
        params = json.loads(json.loads(c.web.page().js[-1][len("window.luneParams && window.luneParams("):-1]))
        assert params["pesoCabeza"] == params["pesoTorso"] == params["pesoOjos"] == 0.0
    finally:
        c.close()
    c.web.page().js.clear()
    c.aplicar_params_vrm()                            # cerrada: nada
    assert c.web.page().js == []


def test_aplicar_params_vrm_es_no_op_en_la_animada(animada):
    c = animada
    c.aplicar_params_vrm()
    c.aplicar_opciones()
    assert not any("luneParams" in j for j in c.web.page().js)


def test_recargar_modelo_cambia_el_personaje_de_las_frases(qapp, web_falso, config_vrm, carpeta_vrm,
                                                           monkeypatch):
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune", "vrm": "a.vrm"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        assert c._frases.nombre == "Lune"
        monkeypatch.setattr(personajes, "get_activo", lambda: {
            "nombre": "Aria", "vrm": "b.vrm", "frases_asistente": {"caricia": ["Jeje"]}})
        c.web.page().js.clear()
        c.recargar_modelo()
        assert c._frases.nombre == "Aria" and c._frases.frases("caricia") == ["Jeje"]
        js = js_de(c)
        assert "luneCargarModelo" in js and "window.luneParams" in js     # modelo nuevo + su calibración
        assert js.index("luneCargarModelo") < js.index("window.luneParams")
        # mismo modelo, otro personaje: frases nuevas sin recargar nada en la página
        monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Nyx", "vrm": "b.vrm"})
        c.web.page().js.clear()
        c.recargar_modelo()
        assert c._frases.nombre == "Nyx" and c.web.page().js == []
    finally:
        c.close()


def test_recargar_modelo_en_la_animada_tambien_cambia_las_frases(animada, monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Aria", "frases_asistente": {"mareo": ["Uy"]}})
    animada.recargar_modelo()
    assert animada._frases.nombre == "Aria"
    evento(animada, "mareo")
    assert comentarios(animada) == ["Uy"]


def test_herramienta_tamano_usa_aplicar_tamano_en_vrm(qapp, web_falso, config_vrm, carpeta_vrm, lune_activa):
    from nucleo import vrm
    from ui.companion import CompanionFlotante, TAMANOS_VRM
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        ok, msg = vrm.herramienta_tamano({"tamano": "grande"}, {"asistente": c, "config": config_vrm})
        assert ok and (c.width(), c.height()) == TAMANOS_VRM["grande"]
    finally:
        c.close()


# ── Asistente de sprites (ui/avatar_overlay.py) ──────────────────────────────────

@pytest.fixture
def sprites(qapp, lune_activa):
    from ui.avatar_overlay import AvatarOverlay
    ov = AvatarOverlay(config=None)
    ov.reloj = Reloj()
    ov._frases = frases(ov.reloj, azar=0.99)          # callada salvo el mareo (p = 1)
    ov.show()
    yield ov
    ov.close()


def texto_burbuja(ov):
    b = ov._burbuja
    return b.text() if b is not None and b.isVisible() else None


def test_sprites_mareo_pone_la_cara_mareada_y_dice_su_frase(sprites):
    from ui.sprites_fx import CARA_SPRITE
    from ui.avatar_overlay import MS_MAREO
    ov = sprites
    assert ov.cara._current_state == "normal"
    ov._fx.mareo.emit()
    assert ov.cara._current_state == CARA_SPRITE["mareada"]
    assert ov._timer_mareo.isActive() and ov._timer_mareo.interval() == MS_MAREO
    assert texto_burbuja(ov) in fm.FRASES_BASE["mareo"]
    ov._fin_mareo()                                   # pasan los 2.5 s
    assert ov.cara._current_state == "normal"


def test_sprites_arrastre_caras_por_velocidad_y_soltar(sprites):
    from nucleo.estado_asistente import BusEstado
    from ui.sprites_fx import CARA_SPRITE
    ov = sprites
    ov._frases = frases(ov.reloj, azar=0.0)
    bus = BusEstado()
    ov.set_bus_estado(bus)
    assert bus.actual().render == "sprites"
    ov._fx.movimiento.emit(True)
    assert ov._arrastrando and bus.actual().arrastrando is True
    assert texto_burbuja(ov) in fm.FRASES_BASE["arrastre"]
    ov._fx.cara.emit("asustada")
    assert ov.cara._current_state == CARA_SPRITE["asustada"]
    ov.set_emocion("sad", 60_000)                     # la IA pide otra cara: se verá al acabar
    assert ov.cara._current_state == CARA_SPRITE["asustada"]
    ov._fx.cara.emit("")
    ov._fx.movimiento.emit(False)
    assert not ov._arrastrando and bus.actual().arrastrando is False
    assert ov.cara._current_state == "sad"            # vuelve la pedida (con su vuelta a normal)
    ov.set_estado("normal")
    ov._fx.movimiento.emit(True); ov._fx.movimiento.emit(False)
    assert ov.cara._current_state == CARA_SPRITE["soltar"]   # en reposo: la de soltar


def test_sprites_giro_compone_el_sprite_con_su_mascara(sprites):
    """Crítica c.8: al girar, la imagen y la máscara salen del mismo fotograma."""
    from PyQt6.QtCore import QPoint
    ov = sprites
    if ov._sr is None:
        pytest.skip("sin lune_face/lune_normal.png no hay sprite que girar")
    recto = ov._img_compuesta
    assert recto is not None and ov.cara.image_label.pixmap().size() == recto.size()
    assert (recto.width(), recto.height()) == ov._sr.lienzo
    ov._fx.angulo.emit(6.0)
    girado = ov._img_compuesta
    assert girado is not recto and ov._angulo == 6.0
    assert ov._region_sprite == ov._sr.componer(6.0, ov._dy)[1]
    # la máscara de la ventana es la región del fotograma girado, donde se pinta
    # donde QLabel lo pinta de verdad: QStyle.alignedRect (W/2 - w/2), no (W - w) // 2
    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtWidgets import QStyle
    lbl = ov.cara.image_label
    pintado = QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, lbl.alignment(),
                                 QSize(girado.width(), girado.height()), lbl.contentsRect())
    base = lbl.mapTo(ov, pintado.topLeft())
    ox, oy = base.x(), base.y()
    r = ov._region_sprite.boundingRect()
    y = r.center().y()
    x = next(x for x in range(r.left(), r.right() + 1) if ov._region_sprite.contains(QPoint(x, y)))
    assert ov.mask().contains(QPoint(ox + x, oy + y))              # figura: recibe clics
    assert not ov.mask().contains(QPoint(ox + r.left() - 1, oy + y))  # fuera: pasan al escritorio
    ov._fx.angulo.emit(0.0)
    assert ov._region_sprite == ov._sr.componer(0.0, ov._dy)[1]
    # la ventana creció el margen del giro una vez (el sprite no se sale al girar)
    assert ov.width() >= 210 + 2 * ov._margen[0] - 1


def test_sprites_fisica_apagada_con_video_y_en_modo_juego(sprites):
    ov = sprites
    assert ov._fx.habilitado and ov._resp.activo
    ov.set_estado("thinking")
    assert ov._fx.habilitado is (not ov.cara.video_activo())
    ov.set_estado("normal")
    assert ov._fx.habilitado
    ov.set_habilitado_fisica(False)                   # modo juego (corte 4)
    assert not ov._fx.habilitado and not ov._resp.activo
    ov.set_habilitado_fisica(True)
    assert ov._fx.habilitado and ov._resp.activo


def test_sprites_dormir_y_despertar(sprites):
    from nucleo import sueno
    ov = sprites
    assert ov.dormir() is True and ov.durmiendo is True
    assert ov.cara._current_state == "sleeping" and ov._resp.respiracion.dormida
    assert ov.dormir() is True
    assert ov.despertar() is True and ov.durmiendo is False
    assert ov.cara._current_state == "normal" and not ov._resp.respiracion.dormida
    assert sueno.herramienta_dormir({}, {"asistente": ov}) == "Vale, me echo una siesta. Una caricia y vuelvo."
    assert ov.durmiendo
    ov.set_emocion("happy")                           # la IA le habla: se despierta
    assert not ov.durmiendo and ov.cara._current_state == "happy"
    # arrastrándola no
    ov._fx.movimiento.emit(True)
    assert ov.dormir() is False and sueno.herramienta_dormir({}, {"asistente": ov})[0] is False
    ov._fx.movimiento.emit(False)


def test_sprites_sueno_por_inactividad_y_frases(sprites):
    ov = sprites
    ov._frases = frases(ov.reloj, azar=0.0)
    assert ov._timer_sueno.isActive() and ov._timer_sueno.interval() == 10 * 60_000
    ov.set_hablando(True)
    ov._sueno_vencido()
    assert not ov.durmiendo                           # hablando no
    ov.set_hablando(False)
    ov._sueno_vencido()
    assert ov.durmiendo and texto_burbuja(ov) in fm.FRASES_BASE["dormir"]
    ov.reloj.avanzar(25)
    ov.mousePressEvent(_evento_raton())               # tocarla la despierta
    assert not ov.durmiendo and texto_burbuja(ov) in fm.FRASES_BASE["despertar"]
    # la respuesta de la IA en la burbuja no la pisa una frase
    ov.reloj.avanzar(25)
    ov.burbuja_texto("Hola, te respondo")
    ov._fx.mareo.emit()
    assert texto_burbuja(ov) == "Hola, te respondo"
    ov._fin_mareo()


def _evento_raton():
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    p = QPointF(100, 100)
    return QMouseEvent(QEvent.Type.MouseButtonPress, p, p, Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_sprites_recargar_modelo_y_contrato_comun(sprites, monkeypatch):
    from nucleo import personajes, vrm
    from ui.avatar_overlay import AvatarOverlay
    clases = [AvatarOverlay]
    if HAY_WEBENGINE:
        from ui.companion import CompanionFlotante
        clases.append(CompanionFlotante)
    ov = sprites
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Aria", "frases_asistente": {"mareo": ["Uy"]}})
    ov.recargar_modelo()
    assert ov._frases.nombre == "Aria" and ov._frases.frases("mareo") == ["Uy"]
    # mismo contrato en las dos clases (lo usan main.py, web_bridge.py y las herramientas)
    for clase in clases:
        for metodo in ("dormir", "despertar", "aplicar_params_vrm", "recargar_modelo", "aplicar_tamano",
                       "aplicar_opciones", "set_bus_estado", "burbuja_texto", "burbuja_fin", "abrir_chat"):
            assert callable(getattr(clase, metodo)), (clase.__name__, metodo)
        assert isinstance(getattr(clase, "durmiendo"), property)
    assert callable(AvatarOverlay.set_habilitado_fisica)
    ov.aplicar_params_vrm()                           # no-op
    ok, msg = vrm.herramienta_tamano({"tamano": "grande"}, {"asistente": ov})
    assert ok is False                                # sprites y sin config: nada que guardar


def test_sprites_cara_dormida_cae_a_la_mas_cercana():
    from ui import lune_face
    ruta, tipo = lune_face.get_face_info("sleeping")
    propia = lune_face.FACE_DIR / "lune_sleeping.png"
    if propia.exists():
        assert Path(ruta) == propia
    else:
        assert ruta == lune_face.get_face_info(lune_face.FACE_FALLBACK_STATE["sleeping"])[0]
    assert tipo == "image"
