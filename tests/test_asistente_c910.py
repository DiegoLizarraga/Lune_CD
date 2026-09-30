"""
Tests del contrato de la asistente de los cortes 9 y 10 (ui/companion.py y ui/avatar_overlay.py):

- `datos_mmd_seguros`: acepta el payload EXACTO de ui/mmd_qt.ControlMMD (listas motion/cara o
  los planos motion0..2/cara0..1) y rechaza http:, '..', '/ui/', '//', '\\', query, %2f,
  URL de más de 1024, ids que no son 12 hex y números fuera de rango;
- `mmd(orden, datos)` → window.luneMMD con el JSON exacto; la VRM baila vmd/vrma y la
  animada «audio»; publica bailes/ y cache/bailes/ UNA vez en el servidor local (se sirven
  por http, nunca file://, y no se sale de la carpeta); bailando no se duerme ni se libera la
  página oculta; antes de cargar la página se guarda y se repite (sin «recarga»); si la
  página RECARGA con un baile → evento 'mmd' error «recarga»; oculta → pausa y al volver sigue;
  la animada avisa una vez de que no tiene esqueleto;
- `decir_reaccion`: burbuja a máquina a 35 c/s con su cara; no pisa la burbuja de la IA; oculta,
  grande, salvapantallas, alarma o menú → False; en sprites, la burbuja nativa;
- contratos de verdad: ControlMMD (VRM y animada, eventos, recarga sin aviso) y
  ControlMinecraft (una muerte en el log → decir_reaccion).
Qt offscreen, sin Chromium (vista web falsa que anota el JS).
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

ID = "0123456789ab"
PAYLOAD_VRM = {  # el de tests/test_mmd_qt.py::test_vrm_prioridad_y_payload_exacto
    "id": ID, "tipo": "vmd", "motion": ["/bailes/Alfa/baile.vmd"], "cara": ["/bailes/Alfa/labios.vmd"],
    "audio": "/bailes/Alfa/cancion.mp3", "offsetMs": 0, "enSitio": True, "brazoGrados": 35.0, "volumen": 0.25,
    "bucle": False, "autoplay": True, "titulo": "Alfa"}
PAYLOAD_AUDIO = {"id": ID, "tipo": "audio", "audio": "/bailes_cache/0123456789ab.ogg", "bpm": 120.0, "fase0": 0.25,
                 "offsetMs": -40, "volumen": 0.25, "bucle": True, "autoplay": True, "titulo": "Beta"}


class FrasesNunca:
    def elegir(self, evento):
        return None

    def set_personaje(self, p):
        pass


@pytest.fixture
def lune_activa(monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})


@pytest.fixture
def bailes_tmp(tmp_path, monkeypatch):
    """bailes/ y cache/bailes/ en una carpeta temporal (lo que publica la asistente)."""
    from nucleo import bailes as nbl
    carpeta, cache = tmp_path / "bailes", tmp_path / "cache" / "bailes"
    (carpeta / "Alfa").mkdir(parents=True)
    (carpeta / "Alfa" / "cancion.mp3").write_bytes(b"ID3cancion")
    cache.mkdir(parents=True)
    (cache / "0123456789ab.ogg").write_bytes(b"OggS...")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")
    monkeypatch.setattr(nbl, "CARPETA", carpeta)
    monkeypatch.setattr(nbl, "CACHE", cache)
    return carpeta, cache


@pytest.fixture
def web_falso(monkeypatch):
    """QWebEngineView falso: anota el JS; `pagina.respuestas` = [(trozo, valor)]."""
    if not HAY_WEBENGINE:
        pytest.skip("la asistente web necesita PyQt6-WebEngine")
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

    class Pagina(QObject):
        class LifecycleState:
            Active, Frozen, Discarded = 0, 1, 2

        def __init__(self):
            super().__init__()
            self.js = []
            self.respuestas = []
            self.estado = 0

        def setBackgroundColor(self, *_):
            pass

        def runJavaScript(self, codigo, cb=None):
            self.js.append(codigo)
            if cb is None:
                return
            if "luneEventos" in codigo:
                cb("[]")
                return
            for trozo, valor in self.respuestas:
                if trozo in codigo:
                    cb(valor(codigo) if callable(valor) else valor)
                    return
            cb(None)

        def setLifecycleState(self, e):
            self.estado = e

        def lifecycleState(self):
            return self.estado

    class Ajustes:
        def setAttribute(self, *_):
            pass

    class FalsoWeb(QWidget):
        loadFinished = pyqtSignal(bool)

        def __init__(self):
            super().__init__()
            self._pagina = Pagina()
            self._url = QUrl()

        def page(self):
            return self._pagina

        def settings(self):
            return Ajustes()

        def setUrl(self, url):
            self._url = url

        def url(self):
            return self._url

        def focusProxy(self):
            return None

    monkeypatch.setattr(comp, "QWebEngineView", FalsoWeb)
    return FalsoWeb


@pytest.fixture
def config(tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    return cfg


@pytest.fixture
def modelo_vrm(tmp_path, monkeypatch):
    from nucleo import vrm
    ruta = tmp_path / "modelo" / "luna.vrm"
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"glTF")
    monkeypatch.setattr(vrm, "ruta_modelo", lambda *a, **k: ruta)
    return ruta


def _crear(config, render, cargada=True):
    from ui.companion import CompanionFlotante
    config.set("avatar", "render", render)
    c = CompanionFlotante(config, ai_manager=object(), bandeja=False)
    c._aparecer_pendiente = False
    c._frases = FrasesNunca()
    c.show()
    if cargada:
        c._on_cargado(True)
    c.web.page().js.clear()
    return c


@pytest.fixture
def animada(qapp, web_falso, config, lune_activa, bailes_tmp):
    c = _crear(config, "animado")
    assert c.render == "animado"
    yield c
    c.close()


@pytest.fixture
def vrm(qapp, web_falso, config, lune_activa, bailes_tmp, modelo_vrm):
    c = _crear(config, "vrm")
    assert c.render == "vrm"
    yield c
    c.close()


def js(c):
    return c.web.page().js


_RE_MMD = re.compile(r'window\.luneMMD && window\.luneMMD\("([a-z_]+)", (.*)\)$', re.S)


def ordenes_mmd(c):
    """[(orden, datos)] de las llamadas a window.luneMMD (el JSON analizado)."""
    res = []
    for x in js(c):
        m = _RE_MMD.fullmatch(x)
        if m:
            res.append((m.group(1), json.loads(m.group(2))))
    return res


def eventos(c):
    vistos = []
    c.evento_js.connect(lambda t, d: vistos.append((t, dict(d))))
    return vistos


# ── Validación ──────────────────────────────────────────────────────────────────

def test_datos_mmd_seguros_acepta_el_payload_de_controlmmd_y_los_planos():
    from ui.companion import datos_mmd_seguros
    assert datos_mmd_seguros(PAYLOAD_VRM) == PAYLOAD_VRM
    assert datos_mmd_seguros(PAYLOAD_AUDIO) == PAYLOAD_AUDIO
    planos = {k: v for k, v in PAYLOAD_VRM.items() if k not in ("motion", "cara")}
    planos.update(motion0="/bailes/Alfa/baile.vmd", motion1="/bailes/Alfa/brazos.vmd", cara0="/bailes/Alfa/labios.vmd",
                  extra="<script>", sobra={"x": 1})
    d = datos_mmd_seguros(planos)
    assert d["motion"] == ["/bailes/Alfa/baile.vmd", "/bailes/Alfa/brazos.vmd"] and d["cara"] == ["/bailes/Alfa/labios.vmd"]
    assert "extra" not in d and "sobra" not in d, "lo que no es del contrato se descarta"
    # japonés ya codificado, .vrma sin canción, título con controles y largo
    vrma = {"id": ID, "tipo": "vrma", "motion": ["/bailes/%E5%8D%83%E6%9C%AC%E6%A1%9C/baile.vrma"], "cara": [],
            "audio": None, "titulo": "Sen\x00bon\u200b" + "z" * 200}
    d = datos_mmd_seguros(vrma)
    assert d["audio"] is None and d["motion"][0].startswith("/bailes/%E5")
    assert len(d["titulo"]) == 80 and "\x00" not in d["titulo"]


MALOS_VRM = [
    {"id": "0123456789AB"}, {"id": "abc"}, {"id": 123}, {"tipo": "mp4"},
    {"motion": ["http://evil.com/bailes/a.vmd"]}, {"motion": ["/bailes/../config.json"]}, {"motion": ["/ui/x.vmd"]},
    {"motion": ["/bailes//a.vmd"]}, {"motion": ["/bailes/a\b.vmd"]}, {"motion": ["/bailes/a.vmd?x=1"]},
    {"motion": ["/bailes/a%2f..%2fb.vmd"]}, {"motion": ["/bailes/%2E%2E/a.vmd"]}, {"motion": ["/bailes/a%zz.vmd"]},
    {"motion": ["/bailes/" + "a" * 1100]}, {"motion": ["file:///c:/a.vmd"]}, {"motion": ["/bailes/a b.vmd"]},
    {"motion": []}, {"motion": ["/bailes/a.vmd"] * 4}, {"motion": "/bailes/a.vmd"}, {"cara": ["/bailes/c.vmd"] * 3},
    {"audio": "/sonidos/x.mp3"}, {"audio": "C:/bailes/x.mp3"},
    {"offsetMs": 600}, {"offsetMs": float("nan")}, {"brazoGrados": 50}, {"brazoGrados": 20}, {"volumen": 1.5},
    {"volumen": True}, {"enSitio": "sí"}, {"bucle": 1}, {"autoplay": 0}, {"titulo": 5},
]
MALOS_AUDIO = [{"bpm": 30}, {"bpm": 300}, {"bpm": "120"}, {"fase0": -0.1}, {"fase0": 1.5}, {"audio": "/bailes/../x.ogg"}]


@pytest.mark.parametrize("base,cambio", [(PAYLOAD_VRM, c) for c in MALOS_VRM] + [(PAYLOAD_AUDIO, c) for c in MALOS_AUDIO])
def test_datos_mmd_seguros_rechaza(base, cambio):
    from ui.companion import datos_mmd_seguros
    assert datos_mmd_seguros({**base, **cambio}) is None, cambio


def test_datos_mmd_seguros_por_tipo():
    from ui.companion import datos_mmd_seguros
    assert datos_mmd_seguros({**PAYLOAD_VRM, "tipo": "vrma", "motion": ["/bailes/a.vrma", "/bailes/b.vrma"]}) is None
    assert datos_mmd_seguros({**PAYLOAD_AUDIO, "motion": ["/bailes/a.vmd"]}) is None, "la animada no lleva movimiento"
    assert datos_mmd_seguros({**PAYLOAD_AUDIO, "audio": None}) is None, "sin canción no hay baile en la animada"
    assert datos_mmd_seguros(["no"]) is None and datos_mmd_seguros(None) is None


# ── mmd en la VRM ──────────────────────────────────────────────────────────────

def test_cargar_manda_el_json_exacto_y_publica_bailes_una_vez(vrm, bailes_tmp, monkeypatch):
    c = vrm
    carpeta, cache = bailes_tmp
    publicadas = []
    original = c._servidor.publicar_carpeta
    monkeypatch.setattr(c._servidor, "publicar_carpeta", lambda p, d: (publicadas.append(p), original(p, d))[1])
    assert c.mmd("cargar", PAYLOAD_VRM) is True
    assert ordenes_mmd(c) == [("cargar", PAYLOAD_VRM)]
    assert js(c)[-1] == 'window.luneMMD && window.luneMMD("cargar", ' + json.dumps(PAYLOAD_VRM, sort_keys=True) + ")"
    assert c.mmd_activo
    assert publicadas == ["/bailes/", "/bailes_cache/"]
    c.mmd("parar")
    c.mmd("cargar", PAYLOAD_VRM)
    assert publicadas == ["/bailes/", "/bailes_cache/"], "una sola vez"
    # El servidor local los sirve (http, dentro de la carpeta; nada de salir con ..)
    with urllib.request.urlopen(c._servidor.url("bailes/Alfa/cancion.mp3")) as r:
        assert r.read() == (carpeta / "Alfa" / "cancion.mp3").read_bytes()
    with urllib.request.urlopen(c._servidor.url("bailes_cache/0123456789ab.ogg")) as r:
        assert r.read() == b"OggS..."
    for malo in ("bailes/../secreto.txt", "bailes/%2e%2e/secreto.txt", "bailes_cache/../../secreto.txt"):
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(c._servidor.url(malo)).read()


def test_ordenes_validadas_y_un_cargar_que_no_es_de_esta_asistente(vrm, animada):
    c = vrm
    assert c.mmd("cargar", {**PAYLOAD_VRM, "motion": ["http://evil.com/x.vmd"]}) is False
    assert c.mmd("cargar", PAYLOAD_AUDIO) is False, "la VRM no baila «audio»"
    assert animada.mmd("cargar", PAYLOAD_VRM) is False, "la animada no tiene esqueleto"
    assert ordenes_mmd(c) == [] and not c.mmd_activo
    c.mmd("cargar", PAYLOAD_VRM)
    js(c).clear()
    assert c.mmd("pausa", {"on": True}) and c.mmd("pausa", {"on": False})
    assert c.mmd("volumen", {"volumen": 0.4}) and c.mmd("offset", {"offsetMs": -120})
    assert c.mmd("en_sitio", {"enSitio": False}) and c.mmd("bucle", {"bucle": True})
    for malo in (("pausa", {"on": "sí"}), ("volumen", {"volumen": 2}), ("volumen", {"volumen": True}),
                 ("offset", {"offsetMs": 900}), ("en_sitio", {"enSitio": 1}), ("bucle", None), ("borrar", {}),
                 ("cargar", None)):
        assert c.mmd(*malo) is False, malo
    assert ordenes_mmd(c) == [("pausa", {"on": True}), ("pausa", {"on": False}), ("volumen", {"volumen": 0.4}),
                              ("offset", {"offsetMs": -120}), ("en_sitio", {"enSitio": False}), ("bucle", {"bucle": True})]
    assert c.mmd("parar") is True
    assert ordenes_mmd(c)[-1] == ("parar", None) and not c.mmd_activo
    c.close()
    assert c.mmd("cargar", PAYLOAD_VRM) is False, "cerrada"


def test_bailando_no_se_duerme_y_al_acabar_vuelve_el_sueno(vrm):
    c = vrm
    c._rearmar_sueno()
    assert c._timer_sueno.isActive()
    c.mmd("cargar", PAYLOAD_VRM)
    assert not c._timer_sueno.isActive()
    assert c._motivo_no_dormir() == "está bailando"
    assert c.dormir() is False, "ni pidiéndoselo"
    c._rearmar_sueno()
    assert not c._timer_sueno.isActive()
    c.evento_js.emit("mmd", {"fase": "parado", "id": "ffffffffffff"})
    assert c.mmd_activo, "el «parado» de otro baile no cuenta"
    c.evento_js.emit("mmd", {"fase": "parado", "id": ID})
    assert not c.mmd_activo and c._timer_sueno.isActive()
    c.mmd("cargar", PAYLOAD_VRM)
    c.evento_js.emit("mmd", {"fase": "error", "id": ID, "mensaje": "modelo"})
    assert not c.mmd_activo


def test_antes_de_cargar_la_pagina_se_guarda_y_se_repite_sin_recarga(qapp, web_falso, config, lune_activa, bailes_tmp,
                                                                      modelo_vrm):
    c = _crear(config, "vrm", cargada=False)
    try:
        vistos = eventos(c)
        assert c.mmd("volumen", {"volumen": 0.9}) is True
        assert c.mmd("cargar", PAYLOAD_VRM) is True
        assert c.mmd("pausa", {"on": True}) and c.mmd("pausa", {"on": True})
        assert ordenes_mmd(c) == [], "sin página aún no se manda"
        c._on_cargado(True)
        assert ordenes_mmd(c) == [("cargar", PAYLOAD_VRM), ("pausa", {"on": True})]
        assert [e for e in vistos if e[0] == "mmd"] == [], "no es una recarga"
        assert c.mmd_activo
    finally:
        c.close()


def test_si_la_pagina_recarga_con_un_baile_avisa_recarga(vrm):
    c = vrm
    vistos = eventos(c)
    c.mmd("cargar", PAYLOAD_VRM)
    c._on_cargado(True)                              # la página recargó: el baile se perdió
    assert ("mmd", {"fase": "error", "id": ID, "mensaje": "recarga"}) in vistos
    assert not c.mmd_activo
    js(c).clear()
    c._on_cargado(True)
    assert [e for e in vistos if e[0] == "mmd"] == [("mmd", {"fase": "error", "id": ID, "mensaje": "recarga"})]
    assert ordenes_mmd(c) == [], "nada que repetir"


def test_oculta_se_pausa_y_sigue_al_volver_sin_pisar_la_pausa_del_controlador(vrm):
    c = vrm
    c.mmd("cargar", PAYLOAD_VRM)
    js(c).clear()
    c.hide()
    assert ordenes_mmd(c) == [("pausa", {"on": True})]
    assert not c._timer_liberar.isActive(), "con un baile no se libera la página"
    c._liberar_pagina()
    assert c.web.page().estado == 0 and not c._liberada
    c.mmd("pausa", {"on": False})                    # el controlador «reanuda» con ella oculta
    assert ordenes_mmd(c) == [("pausa", {"on": True})], "oculta sigue en pausa"
    c.show()
    assert ordenes_mmd(c)[-1] == ("pausa", {"on": False}), "al volver a verla sigue"
    # Con la pausa del controlador (juego, la persona) no se reanuda al mostrarla
    c.mmd("pausa", {"on": True})
    c.hide()
    c.show()
    assert ordenes_mmd(c)[-1] == ("pausa", {"on": True})
    # Un cargar con ella oculta llega en pausa; al acabar el baile oculta, se rearma liberar
    c.hide()
    js(c).clear()
    c.mmd("cargar", PAYLOAD_VRM)
    assert ordenes_mmd(c) == [("cargar", PAYLOAD_VRM), ("pausa", {"on": True})]
    c.mmd("parar")
    assert c._timer_liberar.isActive()


def test_la_animada_baila_audio_y_avisa_una_vez_sin_esqueleto(animada):
    from ui.companion import AVISO_SIN_ESQUELETO
    c = animada
    assert c.mmd("cargar", PAYLOAD_AUDIO) is True
    assert ordenes_mmd(c) == [("cargar", PAYLOAD_AUDIO)]
    avisos = [x for x in js(c) if AVISO_SIN_ESQUELETO in x]
    assert len(avisos) == 1 and "window.comentar" in avisos[0]
    c.mmd("cargar", PAYLOAD_AUDIO)
    assert len([x for x in js(c) if AVISO_SIN_ESQUELETO in x]) == 1, "una vez"


# ── decir_reaccion ──────────────────────────────────────────────────────────────

def test_decir_reaccion_escribe_a_35_cps_con_su_cara(animada):
    c = animada
    assert c.decir_reaccion("¿Otra vez? Esa dolió\nhasta aquí.", "sad", 6000) is True
    ultimo = [x for x in js(c) if "comentarTipeado" in x][-1]
    assert 'window.comentarTipeado("¿Otra vez? Esa dolió hasta aquí.", 35, 6000)' in ultimo
    assert any('window.setEmocion("sad")' in x for x in js(c))
    assert c._timer_revertir.isActive() and 5000 < c._timer_revertir.remainingTime() <= 6000
    c.decir_reaccion("x", "awkward", 10 ** 9)
    assert "35, 20000)" in js(c)[-1], "ms con tope"
    assert any('window.setEmocion("nervous")' in x for x in js(c))
    assert c.decir_reaccion("   ", "happy") is False


@pytest.mark.parametrize("estado", ["oculta", "ia", "pensando", "grande", "salvapantallas", "alarma", "menu", "cerrada"])
def test_decir_reaccion_no_pisa_nada(animada, estado):
    c = animada
    if estado == "oculta":
        c.hide()
    elif estado == "ia":
        c.burbuja_texto("Respuesta de la IA")
        c.burbuja_fin(4000)
    elif estado == "pensando":
        c._pensando = True
    elif estado == "grande":
        c.grande_fase("glide")
    elif estado == "salvapantallas":
        c.set_salvapantallas(True)
    elif estado == "alarma":
        c.mostrar_alarma("¡Hora!")
    elif estado == "menu":
        c.set_menu_abierto(True)
    elif estado == "cerrada":
        c.close()
    js(c).clear()
    assert c.decir_reaccion("Ha llegado Steve.", "wave") is False
    assert not any("comentarTipeado" in x for x in js(c))


def test_decir_reaccion_en_los_sprites_con_la_burbuja_nativa(qapp, monkeypatch):
    from nucleo import personajes
    from ui.avatar_overlay import AvatarOverlay
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    o = AvatarOverlay(config=None, bandeja=False)
    o.show()
    o._frases = FrasesNunca()
    try:
        assert not hasattr(o, "mmd"), "los sprites no tienen reproductor en la página (D1: ControlMMD usa bailar/pulso)"
        assert o.decir_reaccion("¡Logro! «Cazamonstruos». Me lo apunto.", "happy", 5000) is True
        b = o._burbuja
        assert b is not None and b.isVisible() and b.text() == "¡Logro! «Cazamonstruos». Me lo apunto."
        assert b._t_fin.isActive() and b._t_fin.interval() == 5000
        assert o.cara._current_state == "happy"
        o.burbuja_texto("La IA habla")
        assert o.decir_reaccion("otra", "sad") is False
        o.burbuja_fin(0)
        o._burbuja_ia_hasta = 0.0
        o.mostrar_alarma("Alarma")
        assert o.decir_reaccion("otra", "sad") is False
        o.ocultar_alarma()
        o.hide()
        assert o.decir_reaccion("otra", "sad") is False
    finally:
        o.close()


# ── Contratos con los controladores de verdad ──────────────────────────────────

@pytest.fixture
def control_mmd(qapp, tmp_path):
    import bailes_falsos as bf
    from nucleo import bailes as nbl
    from ui.escritorio import ServiciosEscritorio
    from ui.mmd_qt import ControlMMD
    carpeta = tmp_path / "biblio"
    bf.hacer_baile(carpeta, "Alfa", cara=bf.vmd([], [("あ", 5)]))
    cfg = bf.ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    bib = nbl.Biblioteca(carpeta, tmp_path / "cache_b", config=cfg, ffmpeg="ffm",
                         ejecutar=bf.EjecutarFalso(pcm=bf.clics(120, primero=0.1)))
    avisos = []

    class Anf:
        def aviso(self, t):
            avisos.append(t)

    ctl = ControlMMD(esc, cfg, biblioteca=bib, anfitrion=Anf(), hilo=False)
    esc.registrar("mmd", ctl, ("mmd",))
    esc.iniciar()
    ids = {b.titulo: b.id for b in bib.escanear()}
    yield esc, ctl, ids, avisos
    esc.cerrar()
    ctl.deleteLater()


def test_contrato_controlmmd_vrm_payload_aceptado_eventos_y_recarga(vrm, control_mmd):
    esc, ctl, ids, avisos = control_mmd
    c = vrm
    esc.set_asistente(c)
    ok, texto = ctl.reproducir(ids["Alfa"])
    assert ok, texto
    cargas = [d for o, d in ordenes_mmd(c) if o == "cargar"]
    assert len(cargas) == 1 and cargas[0]["id"] == ids["Alfa"] and cargas[0]["tipo"] == "vmd"
    assert cargas[0]["motion"] == ["/bailes/Alfa/baile.vmd"] and cargas[0]["cara"] == ["/bailes/Alfa/labios.vmd"]
    assert ctl.estado()["fase"] == "cargando" and c.mmd_activo
    # Los eventos de la página llegan a ControlMMD por evento_js → ServiciosEscritorio
    c.evento_js.emit("mmd", {"fase": "listo", "id": ids["Alfa"], "t": 0, "total": 30})
    c.evento_js.emit("mmd", {"fase": "sonando", "id": ids["Alfa"], "t": 0, "total": 30})
    assert ctl.estado()["fase"] == "sonando"
    ctl.pausa(True)
    assert ordenes_mmd(c)[-1] == ("pausa", {"on": True})
    ctl.pausa(False)
    assert ordenes_mmd(c)[-1] == ("pausa", {"on": False})
    # La página recarga: «recarga» → ControlMMD para sin avisar
    c._on_cargado(True)
    assert ctl.estado()["fase"] == "parado" and not c.mmd_activo
    assert avisos == []


def test_contrato_controlmmd_animada_tipo_audio(animada, control_mmd):
    esc, ctl, ids, avisos = control_mmd
    c = animada
    esc.set_asistente(c)
    ok, texto = ctl.reproducir(ids["Alfa"])
    assert ok, texto
    cargas = [d for o, d in ordenes_mmd(c) if o == "cargar"]
    assert len(cargas) == 1
    d = cargas[0]
    assert d["tipo"] == "audio" and d["audio"] == "/bailes/Alfa/cancion.mp3" and 40 <= d["bpm"] <= 240
    assert 0 <= d["fase0"] < 1 and "motion" not in d
    assert ctl.estado()["fase"] == "cargando" and ctl.estado()["sin_esqueleto"]
    c.evento_js.emit("mmd", {"fase": "parado", "id": ids["Alfa"]})
    assert ctl.estado()["fase"] == "parado" and not c.mmd_activo


def test_contrato_controlminecraft_una_muerte_sale_en_la_burbuja(animada, qapp):
    from lune_core.minecraft_log import Evento
    from ui.escritorio import ServiciosEscritorio
    from ui.minecraft_qt import ControlMinecraft

    class Cfg:
        d = {"minecraft": {"reaccionar": True, "decir_en_juego": True, "resumen_al_salir": True}}

        def get(self, s, k, d=None):
            return self.d.get(s, {}).get(k, d)

        def set(self, s, k, v):
            self.d.setdefault(s, {})[k] = v

    class Lector:
        ruta = Path("C:/juego/logs/latest.log")
        yo, otros, nombre_bot = "Diego_01", False, ""

        def __init__(self):
            self.pendientes = [Evento("muerte", "Diego_01", "Zombie", t=1.0, propio=True)]

        def poll(self):
            e, self.pendientes = self.pendientes, []
            return e

        def inactivo_s(self):
            return 0.0

    class Proceso:
        vivo = False
        on_evento = on_log = on_fin = None

        def requisitos(self, refrescar=False):
            return {"node": None, "node_ok": False, "npm": False, "instalado": False}

        def instalado(self):
            return False

    class Azar:
        def random(self):
            return 0.0

    esc = ServiciosEscritorio(None)
    ctl = ControlMinecraft(esc, Cfg(), proceso=Proceso(), lector=Lector(), rng=Azar(), reloj=lambda: 1000.0,
                           personaje=lambda: {"nombre": "Lune"}, llm=lambda: None, hilo=lambda fn, *a: fn())
    try:
        esc.set_asistente(animada)
        ctl.set_asistente(animada)
        js(animada).clear()
        ctl._leer()
        dichos = [x for x in js(animada) if "comentarTipeado" in x]
        assert len(dichos) == 1 and ", 35, " in dichos[0]
        assert any('window.setEmocion("sad")' in x for x in js(animada)), "muerte → cara triste"
        assert ctl.eventos_recientes()[-1]["entregado"] is True
    finally:
        esc.cerrar()
        ctl.deleteLater()
