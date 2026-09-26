"""
Tests de la mascota 3D (VRM): nucleo/vrm.py, ui/servidor_web.py, ui/companion.py
y la página ui_web/companion_vrm.html + ui_web/vrm/lune_vrm.js.

Lo visual (el render 3D, el balanceo, la mirada) no se puede probar sin pantalla.
Sí se prueba: la validación GLB/VRM, qué modelo toca según personaje/config, el
http local que publica el .vrm, la ventana (render, señal de visibilidad, cierre,
fantasma automático, rueda) y que la página expone exactamente la API que
Python llama y cubre todos los estados que Python puede mandar.
"""
import json
import re
import struct
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = RAIZ / "ui_web" / "companion_vrm.html"
MOTOR = RAIZ / "ui_web" / "vrm" / "lune_vrm.js"


# ── Un .vrm sintético: GLB mínimo con la extensión VRM en el chunk JSON ─────────
def glb(doc: dict, longitud_falsa: int | None = None) -> bytes:
    js = json.dumps(doc).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js)
    return (b"glTF" + struct.pack("<II", 2, longitud_falsa or total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js)


def vrm1(nombre="Luna", autor="Diego") -> bytes:
    return glb({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                "extensions": {"VRMC_vrm": {"meta": {"name": nombre, "authors": [autor]}}}})


def vrm0(titulo="Vieja", autor="Alguien") -> bytes:
    return glb({"asset": {"version": "2.0"}, "extensionsUsed": ["VRM"],
                "extensions": {"VRM": {"meta": {"title": titulo, "author": autor}}}})


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """modelo_vrm/ de mentira con dos modelos válidos y uno roto."""
    from nucleo import vrm
    c = tmp_path / "modelo_vrm"; c.mkdir()
    (c / "a_luna.vrm").write_bytes(vrm1())
    (c / "b_vieja.vrm").write_bytes(vrm0())
    (c / "roto.vrm").write_bytes(b"esto no es un glb")
    monkeypatch.setattr(vrm, "CARPETA", c)
    return c


# ── Validación ─────────────────────────────────────────────────────────────────

def test_validar_acepta_vrm1_y_vrm0(tmp_path):
    from nucleo import vrm
    a = tmp_path / "a.vrm"; a.write_bytes(vrm1("Luna", "Diego"))
    ok, motivo, meta = vrm.validar(a)
    assert ok and motivo == "" and meta["version"] == "1"
    assert meta["nombre"] == "Luna" and meta["autor"] == "Diego"
    b = tmp_path / "b.vrm"; b.write_bytes(vrm0("Vieja", "Alguien"))
    ok, _, meta = vrm.validar(b)
    assert ok and meta["version"] == "0" and meta["nombre"] == "Vieja" and meta["autor"] == "Alguien"


@pytest.mark.parametrize("contenido, pista", [
    (b"", "vac"),
    (b"no soy un glb, soy texto", "glTF"),
    (glb({"asset": {"version": "2.0"}}), "VRM"),                       # glb sin extensión VRM
    (glb({"extensionsUsed": ["VRMC_vrm"]}, longitud_falsa=999), "incoherente"),
])
def test_validar_rechaza_archivos_malos(tmp_path, contenido, pista):
    from nucleo import vrm
    p = tmp_path / "x.vrm"; p.write_bytes(contenido)
    ok, motivo, _ = vrm.validar(p)
    assert not ok and pista.lower() in motivo.lower()


@pytest.mark.parametrize("doc", [[], "hola", 5, None, {"extensions": [1, 2]}, {"extensions": {"VRM": "x"}},
                                 {"extensionsUsed": "VRMC_vrm", "extensions": {"VRMC_vrm": {"meta": {"authors": "yo"}}}}])
def test_validar_no_revienta_con_json_raro(tmp_path, doc):
    """Un .vrm corrupto en modelo_vrm/ no puede tumbar Ajustes ni la mascota."""
    from nucleo import vrm
    p = tmp_path / "raro.vrm"; p.write_bytes(glb(doc))
    ok, motivo, meta = vrm.validar(p)
    assert isinstance(ok, bool) and isinstance(motivo, str)


def test_validar_archivo_inexistente():
    from nucleo import vrm
    ok, motivo, _ = vrm.validar(Path("no/existe.vrm"))
    assert not ok and "no existe" in motivo


def test_listar_modelos_solo_los_validos(carpeta):
    from nucleo import vrm
    assert vrm.listar_modelos() == ["a_luna.vrm", "b_vieja.vrm"]


# ── Qué modelo toca ────────────────────────────────────────────────────────────

def test_ruta_modelo_prioridad_personaje_config_primero(carpeta, tmp_path):
    from nucleo import vrm
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    # 3) sin nada: el primero de la carpeta
    assert vrm.ruta_modelo(cfg, personaje={}) == carpeta / "a_luna.vrm"
    # 2) el de config
    cfg.set("avatar", "vrm_archivo", "b_vieja.vrm")
    assert vrm.ruta_modelo(cfg, personaje={}) == carpeta / "b_vieja.vrm"
    # 1) el del personaje gana a todo
    assert vrm.ruta_modelo(cfg, personaje={"vrm": "a_luna.vrm"}) == carpeta / "a_luna.vrm"
    # un personaje con un modelo que no existe (o roto) cae al siguiente nivel
    assert vrm.ruta_modelo(cfg, personaje={"vrm": "fantasma.vrm"}) == carpeta / "b_vieja.vrm"
    assert vrm.ruta_modelo(cfg, personaje={"vrm": "roto.vrm"}) == carpeta / "b_vieja.vrm"


def test_ruta_modelo_acepta_rutas_absolutas(carpeta, tmp_path):
    from nucleo import vrm
    fuera = tmp_path / "otro_sitio" / "z.vrm"; fuera.parent.mkdir(); fuera.write_bytes(vrm1())
    assert vrm.ruta_modelo(None, personaje={"vrm": str(fuera)}) == fuera


def test_rutas_de_red_no_se_tocan(carpeta, tmp_path, monkeypatch):
    """Revisión S2: una ruta UNC (o de dispositivo) nunca llega a is_file()/stat: Windows
    mandaría el hash NTLM al equipo de la ruta. Tampoco se usa su nombre."""
    from nucleo import vrm
    (carpeta / "z.vrm").write_bytes(vrm1())                          # aunque el nombre exista dentro
    tocadas = []
    real_is_file, real_stat = Path.is_file, Path.stat
    monkeypatch.setattr(Path, "is_file", lambda self: (tocadas.append(str(self)), real_is_file(self))[1])
    monkeypatch.setattr(Path, "stat", lambda self, **k: (tocadas.append(str(self)), real_stat(self, **k))[1])
    for red in ("\\\\atacante\\s\\z.vrm", "//atacante/s/z.vrm", "\\/atacante\\s\\z.vrm",
                "\\\\?\\UNC\\atacante\\s\\z.vrm"):
        assert vrm.resolver(red) is None
        with pytest.raises(ValueError):
            vrm.ruta_ajustes(red)
        with pytest.raises(ValueError):
            vrm.guardar_ajustes_modelo(red, {"luz": 2})
        with pytest.raises(ValueError):
            vrm.importar_modelo(red)
        assert vrm._apunta_a(red, "z.vrm") is False
    assert not any("atacante" in t for t in tocadas), tocadas


def test_sin_modelos_devuelve_none(tmp_path, monkeypatch):
    from nucleo import vrm
    monkeypatch.setattr(vrm, "CARPETA", tmp_path / "vacia")
    assert vrm.ruta_modelo(None, personaje={}) is None
    assert vrm.listar_modelos() == []


def test_importar_modelo_copia_y_valida(carpeta, tmp_path):
    from nucleo import vrm
    bueno = tmp_path / "descargas" / "nuevo.vrm"; bueno.parent.mkdir(); bueno.write_bytes(vrm1("Nuevo"))
    assert vrm.importar_modelo(str(bueno)) == "nuevo.vrm"
    assert (carpeta / "nuevo.vrm").read_bytes() == bueno.read_bytes()
    malo = tmp_path / "descargas" / "malo.vrm"; malo.write_bytes(b"basura")
    with pytest.raises(ValueError):
        vrm.importar_modelo(str(malo))
    with pytest.raises(ValueError):
        vrm.importar_modelo(str(tmp_path / "descargas" / "foto.png"))


def test_asignar_a_personaje_guarda_solo_el_nombre(carpeta, monkeypatch):
    """El vrm del personaje se guarda como nombre (portable) y se puede quitar."""
    from nucleo import vrm, personajes, datos
    almacen = {"bot": {"personaje_default": "Lune"},
               "personajes": [{"nombre": "Lune", "systemPrompt": "x"}, {"nombre": "Aria", "systemPrompt": "y"}]}
    monkeypatch.setattr(personajes, "_load", lambda: json.loads(json.dumps(almacen)))
    monkeypatch.setattr(personajes, "_save", lambda d: almacen.update(d))
    monkeypatch.setattr(datos, "invalidar", lambda: None)

    p = vrm.asignar_a_personaje("Aria", str(carpeta / "b_vieja.vrm"))
    assert p["vrm"] == "b_vieja.vrm"
    assert next(x for x in almacen["personajes"] if x["nombre"] == "Aria")["vrm"] == "b_vieja.vrm"
    with pytest.raises(ValueError):
        vrm.asignar_a_personaje("Aria", "no_existe.vrm")
    with pytest.raises(ValueError):
        vrm.asignar_a_personaje("Nadie", "a_luna.vrm")
    p = vrm.asignar_a_personaje("Aria", "")
    assert "vrm" not in p


# ── El http local publica el .vrm que está fuera de ui_web/ ────────────────────

def test_servidor_publica_rutas_extra(tmp_path):
    from ui.servidor_web import ServidorEstatico
    web = tmp_path / "web"; web.mkdir(); (web / "index.html").write_text("<p>hola</p>", "utf-8")
    modelo = tmp_path / "modelo.vrm"; modelo.write_bytes(vrm1())
    srv = ServidorEstatico(web, rutas_extra={"/vrm/actual.vrm": modelo})
    assert srv.iniciar()
    try:
        with urllib.request.urlopen(srv.url("index.html")) as r:
            assert b"hola" in r.read()
        with urllib.request.urlopen(srv.url("vrm/actual.vrm") + "?v=1") as r:
            assert r.read() == modelo.read_bytes()
            assert r.headers.get("Content-Type", "").startswith("model/gltf-binary")
        # cambiar el modelo en caliente (otro personaje) sin reiniciar el servidor
        otro = tmp_path / "otro.vrm"; otro.write_bytes(vrm0())
        srv.publicar("/vrm/actual.vrm", otro)
        with urllib.request.urlopen(srv.url("vrm/actual.vrm")) as r:
            assert r.read() == otro.read_bytes()
        # HTTP Range (los <video> de la mascota animada lo necesitan)
        req = urllib.request.Request(srv.url("vrm/actual.vrm"), headers={"Range": "bytes=0-3"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 206 and r.read() == b"glTF"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(srv.url("vrm/nada.vrm"))
        assert e.value.code == 404
    finally:
        srv.detener()


def test_web_shell_sigue_exportando_los_nombres_antiguos():
    import ui.web_shell as ws
    from ui.servidor_web import ServidorEstatico, HandlerSilencioso, DIR_WEB, RAIZ as R
    assert ws._ServidorEstatico is ServidorEstatico and ws._HandlerSilencioso is HandlerSilencioso
    assert ws.DIR_WEB == DIR_WEB and ws.RAIZ == R


# ── La página: misma API que Python llama, y todos los estados cubiertos ───────

def _js(nombre):
    return (RAIZ / "ui_web" / "vrm" / nombre).read_text("utf-8")


def test_la_pagina_expone_la_api_que_python_usa():
    html = PAGINA.read_text("utf-8")
    for fn in ("setEmocion", "luneSpeak", "luneCursor", "luneDrag", "luneSleep", "luneTouch",
               "luneEncuadre", "luneCargarModelo", "luneSetFPS", "comentar", "pensando", "ocultarBurbuja"):
        assert f"window.{fn} =" in html, fn
    # y companion.py no llama a nada que la página no tenga
    src = (RAIZ / "ui" / "companion.py").read_text("utf-8")
    for fn in set(re.findall(r"window\.(lune\w+|setEmocion|comentar|pensando|ocultarBurbuja)\b", src)):
        assert f"window.{fn} =" in html, f"companion.py llama a window.{fn} y la página no lo define"


def test_la_pagina_carga_las_librerias_empaquetadas_sin_red():
    html = PAGINA.read_text("utf-8")
    assert "cdn." not in html and "https://" not in html
    for ruta in re.findall(r'"\./(vendor/[^"]+\.js)"', html):
        assert (RAIZ / "ui_web" / ruta).is_file(), ruta
    assert (RAIZ / "ui_web" / "vendor" / "three" / "loaders" / "GLTFLoader.js").is_file()
    assert (RAIZ / "ui_web" / "vendor" / "three" / "utils" / "BufferGeometryUtils.js").is_file()
    assert (RAIZ / "ui_web" / "vendor" / "three" / "LICENSE.three").is_file()
    motor = MOTOR.read_text("utf-8")
    # three-vrm 3.1.6 no trae combineSkeletons: el visor viejo lo llamaba y reventaba.
    # removeUnnecessaryJoints deforma algunos modelos: tampoco se usa.
    assert "VRMUtils.combineSkeletons(" not in motor
    assert "VRMUtils.removeUnnecessaryJoints(" not in motor
    # los VRM 0.x traen el rig girado: el signo de X/Z se mide al cargar (brazos en V si no)
    assert "sXZ" in motor and "invertirEjes" in motor and "leftLowerArm.position.x" in motor


def test_el_motor_cubre_todos_los_estados_que_python_manda():
    motor = MOTOR.read_text("utf-8")
    bloque = motor[motor.index("const EXPRESIONES = {"):motor.index("const ALIAS")]
    definidos = set(re.findall(r"^\s+(\w+):\s*\{", bloque, re.M))
    from ui.companion import EMOCION_A_ESTADO
    from ui.web_bridge import EMOCION_A_MASCOTA, LuneBridge
    from lune_core.marcadores import EMOCIONES
    esperados = set(EMOCION_A_ESTADO.values()) | set(EMOCION_A_MASCOTA.values())
    esperados |= set(LuneBridge._LLAMADA_A_MASCOTA.values())
    esperados |= {"bored", "typing", "error", "normal", "thinking", "talking", "listening"}
    faltan = esperados - definidos
    assert not faltan, f"estados sin expresión en lune_vrm.js: {faltan}"
    # y cada emoción canónica del protocolo tiene estado en companion
    for e in EMOCIONES:
        assert e in EMOCION_A_ESTADO


def test_el_puente_tiene_los_slots_nuevos():
    from ui.web_bridge import LuneBridge
    for slot in ("mascota_visible", "vrm_modelos", "vrm_importar", "personaje_vrm", "personajes_lista"):
        assert callable(getattr(LuneBridge, slot))
    src = (RAIZ / "ui" / "web_bridge.py").read_text("utf-8")
    # la mascota de escritorio recibe las emociones del chat (antes solo la de la barra lateral)
    assert "_mascota_estado(mascota" in src and "_mascota_estado(\"thinking\")" in src


def test_la_barra_lateral_se_apaga_cuando_lune_esta_fuera():
    app = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "app.jsx").read_text("utf-8")
    side = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "sidebar.jsx").read_text("utf-8")
    assert "mascota_estado.connect" in app and "mascotaFuera" in app
    assert "MascotFuera" in side and "mascotaFuera ?" in side
    ajustes = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "settings.jsx").read_text("utf-8")
    assert "próximamente" not in ajustes.split("Mascota")[1][:1200]
    main_py = (RAIZ / "main.py").read_text("utf-8")
    assert "_on_mascota_visible" in main_py and "lune_face.setVisible(not fuera)" in main_py


# ── La ventana (sin pantalla) ──────────────────────────────────────────────────
# Chromium (QWebEngineView) no arranca bien en el modo offscreen de los tests, así
# que se sustituye por un widget falso que anota lo que Python le manda por JS.
# Lo que se prueba es la lógica de la ventana, no el render.

pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="la mascota 3D necesita PyQt6-WebEngine")


@pytest.fixture
def web_falso(monkeypatch):
    from PyQt6.QtCore import QObject, QUrl, pyqtSignal
    from PyQt6.QtWidgets import QWidget
    import ui.companion as comp

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
    return FalsoWeb


@pytest.fixture
def config_vrm(carpeta, tmp_path):
    from nucleo.config import Config
    cfg = Config(config_path=str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "vrm")
    return cfg


def js_de(c):
    return "\n".join(c.web.page().js)


def test_companion_vrm_sirve_el_modelo_del_personaje(qapp, web_falso, config_vrm, carpeta, monkeypatch):
    from nucleo import personajes
    from ui.companion import CompanionFlotante, RUTA_MODELO
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Aria", "vrm": "b_vieja.vrm"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        assert c.render == "vrm" and c.modelo == carpeta / "b_vieja.vrm"
        url = c.web.url().toString()
        assert "companion_vrm.html" in url and f"src={RUTA_MODELO}" in url and "enc=retrato" in url
        with urllib.request.urlopen(c._servidor.url(RUTA_MODELO)) as r:
            assert r.read() == (carpeta / "b_vieja.vrm").read_bytes()
        # cambia el personaje activo → otro modelo, mismo servidor, sin cerrar la ventana
        monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune", "vrm": "a_luna.vrm"})
        c.recargar_modelo()
        assert c.modelo == carpeta / "a_luna.vrm"
        assert "luneCargarModelo" in js_de(c)
        with urllib.request.urlopen(c._servidor.url(RUTA_MODELO)) as r:
            assert r.read() == (carpeta / "a_luna.vrm").read_bytes()
        # mismo personaje otra vez: no recarga
        n = len(c.web.page().js); c.recargar_modelo()
        assert len(c.web.page().js) == n
    finally:
        c.close()


def test_companion_sin_modelo_cae_al_animado(qapp, web_falso, tmp_path, monkeypatch):
    from nucleo import vrm, personajes
    from nucleo.config import Config
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(vrm, "CARPETA", tmp_path / "vacia")
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    cfg = Config(config_path=str(tmp_path / "config.json")); cfg.set("avatar", "render", "vrm")
    c = CompanionFlotante(cfg, ai_manager=None)
    try:
        assert c.render == "animado" and "companion.html" in c.web.url().toString()
    finally:
        c.close()


def test_companion_visibilidad_cierre_y_fantasma(qapp, web_falso, config_vrm, monkeypatch):
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    vistos = []
    c.visibilidad.connect(vistos.append)
    try:
        c.show(); c.hide()
        assert vistos[:2] == [True, False]
        js = js_de(c)
        assert "luneSetFPS(60)" in js and "luneSetFPS(0)" in js     # oculta no renderiza
        # fantasma automático: la página dice "no estás sobre el avatar" → deja pasar clics
        c._sobre_modelo = True
        c._on_cursor_respuesta(False)
        assert c._fantasma_auto is True
        c._on_cursor_respuesta(True)
        assert c._fantasma_auto is False
        # en pleno arrastre nunca se conmuta (se perdería la captura del ratón)
        c._arrastre = {"movido": True}
        c._on_cursor_respuesta(False)
        assert c._fantasma_auto is False
        c._arrastre = None
        # con fantasma total activo, el sondeo no lo toca
        c.set_click_through(True)
        c._on_cursor_respuesta(True)
        assert c._click_through is True and c._fantasma_auto is True
        c.set_click_through(False)
        assert c._fantasma_auto is False
    finally:
        c.close()
    assert c.cerrado is True


def test_companion_estados_y_vuelta_al_idle(qapp, web_falso, config_vrm, monkeypatch):
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        c.set_act({"emotion": "angry", "intensity": 1.0})
        assert 'setEmocion("angry")' in js_de(c)
        c.set_emocion("question")
        assert 'setEmocion("thinking")' in js_de(c)
        c.set_hablando(True)
        assert "luneSpeak(true)" in js_de(c)
        # con ms > 0 vuelve al idle; si entre medias llega otro estado, el viejo no lo pisa
        c.set_estado("happy", 5000)
        viejo = c._revert_token
        c.set_estado("surprised", 5000)
        c._revertir(viejo)
        assert "setEmocion('normal')" not in js_de(c)
        c._revertir(c._revert_token)
        assert "setEmocion('normal')" in js_de(c)
        # dormir / despertar
        c._dormir()
        assert c._durmiendo and "luneSleep(true)" in js_de(c)
        c.set_estado("happy")
        assert not c._durmiendo and "luneSleep(false)" in js_de(c)
    finally:
        c.close()


def test_companion_rueda_escala_y_tamanos(qapp, web_falso, config_vrm, monkeypatch):
    from PyQt6.QtCore import QPoint
    from nucleo import personajes
    from ui.companion import CompanionFlotante, TAMANOS_VRM
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        assert (c.width(), c.height()) == TAMANOS_VRM["normal"]

        class Rueda:
            def __init__(self, y): self._y = y
            def angleDelta(self): return QPoint(0, self._y)

        assert c._rueda(Rueda(120)) is True and abs(c._escala_obj - 1.1) < 1e-9
        for _ in range(200):
            c._paso_escala()
            if not c._timer_escala.isActive():
                break
        assert abs(c._escala - 1.1) < 1e-6
        assert c.width() == round(TAMANOS_VRM["normal"][0] * 1.1)
        assert abs(config_vrm.get("avatar", "vrm_escala") - 1.1) < 1e-6
        # tope inferior y superior
        for _ in range(30): c._rueda(Rueda(-120))
        assert c._escala_obj == c.ESCALA_MIN
        for _ in range(30): c._rueda(Rueda(120))
        assert c._escala_obj == c.ESCALA_MAX
        # no escala mientras se arrastra ni en modo fantasma
        c._arrastre = {"movido": True}
        assert c._rueda(Rueda(120)) is False
        c._arrastre = None
        # tamaños desde la bandeja
        c._escala = c._escala_obj = 1.0
        c.aplicar_tamano("grande")
        assert (c.width(), c.height()) == TAMANOS_VRM["grande"]
        assert config_vrm.get("avatar", "vrm_tamano") == "grande"
        c.aplicar_encuadre("cuerpo")
        assert 'luneEncuadre("cuerpo")' in js_de(c) and config_vrm.get("avatar", "vrm_encuadre") == "cuerpo"
    finally:
        c.close()


def test_companion_animado_no_tiene_extras_vrm(qapp, web_falso, tmp_path, monkeypatch):
    """En modo animado la rueda no hace nada y el sueño no se arma."""
    from PyQt6.QtCore import QPoint
    from nucleo.config import Config
    from ui.companion import CompanionFlotante, TAMANO_ANIMADO
    cfg = Config(config_path=str(tmp_path / "config.json")); cfg.set("avatar", "render", "animado")
    c = CompanionFlotante(cfg, ai_manager=None)
    try:
        assert c.render == "animado" and (c.width(), c.height()) == TAMANO_ANIMADO

        class Rueda:
            def angleDelta(self): return QPoint(0, 120)
        assert c._rueda(Rueda()) is False
        c._rearmar_sueno()
        assert not c._timer_sueno.isActive()
    finally:
        c.close()


def test_companion_fantasma_total_se_guarda_y_restaura(qapp, web_falso, config_vrm, monkeypatch):
    """El modo fantasma de la bandeja persiste en avatar.click_through (como la de sprites)."""
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    # Sin pantalla no hay bandeja (ni casilla): la casilla se comprueba solo si existe.
    casilla = lambda m: getattr(m, "act_fantasma", None)
    try:
        assert c._click_through is False and (casilla(c) is None or not casilla(c).isChecked())
        c.set_click_through(True)
        assert config_vrm.get("avatar", "click_through") is True
        assert casilla(c) is None or casilla(c).isChecked()
        c.set_click_through(False)
        assert config_vrm.get("avatar", "click_through") is False
    finally:
        c.close()
    config_vrm.set("avatar", "click_through", True)
    c2 = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        assert c2._cfg_bool("click_through", False) is True
        assert casilla(c2) is None or casilla(c2).isChecked()
        # y a los 300 ms se aplica sola (QTimer.singleShot): forzamos el efecto
        c2.set_click_through(True)
        assert c2._click_through is True
    finally:
        c2.close()


def test_companion_degradada_pide_que_la_recreen_cuando_aparece_un_modelo(qapp, web_falso, tmp_path, monkeypatch):
    from nucleo import vrm, personajes
    from nucleo.config import Config
    from ui.companion import CompanionFlotante
    carpeta = tmp_path / "modelo_vrm"; carpeta.mkdir()
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    cfg = Config(config_path=str(tmp_path / "config.json")); cfg.set("avatar", "render", "vrm")
    c = CompanionFlotante(cfg, ai_manager=None)
    pedidos = []
    c.recrear.connect(lambda: pedidos.append(1))
    try:
        assert c.render == "animado" and c.render_pedido == "vrm"
        c.recargar_modelo()                      # sigue sin modelo: nada
        assert pedidos == []
        (carpeta / "nuevo.vrm").write_bytes(vrm1())
        c.recargar_modelo()                      # ahora sí: que la recreen como VRM
        assert pedidos == [1]
    finally:
        c.close()


def test_companion_rueda_guarda_config_solo_al_final(qapp, web_falso, config_vrm, monkeypatch):
    from PyQt6.QtCore import QPoint
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        class Rueda:
            def angleDelta(self): return QPoint(0, 120)
        c._rueda(Rueda())
        c._paso_escala()                          # primer tick: geometría sí, config no
        assert c._timer_escala.isActive()
        assert abs(float(config_vrm.get("avatar", "vrm_escala", 1.0)) - 1.0) < 1e-9
        for _ in range(200):
            if not c._timer_escala.isActive():
                break
            c._paso_escala()
        assert abs(float(config_vrm.get("avatar", "vrm_escala")) - 1.1) < 1e-6
    finally:
        c.close()


def test_companion_aplicar_opciones_en_caliente(qapp, web_falso, config_vrm, monkeypatch):
    from nucleo import personajes
    from ui.companion import CompanionFlotante
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    c = CompanionFlotante(config_vrm, ai_manager=None)
    try:
        c._on_cargado(True)                       # como si la página hubiera cargado
        assert c._timer_sueno.isActive()
        config_vrm.set("avatar", "dormir_min", 0)
        c.aplicar_opciones()
        assert not c._timer_sueno.isActive()      # 0 = nunca
        # con el fantasma automático apagado, si estaba dejando pasar clics vuelve a recibirlos
        c._on_cursor_respuesta(False)
        assert c._fantasma_auto is True
        config_vrm.set("avatar", "vrm_fantasma_auto", False)
        c.aplicar_opciones()
        assert c._fantasma_auto is False
        c._on_cursor_respuesta(False)             # y ya no vuelve a conmutar
        assert c._fantasma_auto is False
    finally:
        c.close()


def test_main_nativo_conecta_la_voz_con_la_boca():
    src = (RAIZ / "main.py").read_text("utf-8")
    assert "_hablando = pyqtSignal(bool)" in src
    assert "self.voice.al_hablar = self._hablando.emit" in src
    assert "def _on_hablando" in src and "ov.recrear.connect(self._mascota_recrear)" in src


def test_letra_de_unidad_de_red_no_se_toca(carpeta, monkeypatch):
    """Una letra mapeada a un recurso de red (GetDriveTypeW = 4) tampoco se mira."""
    from nucleo import vrm
    monkeypatch.setattr(vrm, "ruta_local", lambda r: False)
    tocadas = []
    real = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: (tocadas.append(str(self)), real(self))[1])
    assert vrm.resolver(r"Z:\modelos\a_luna.vrm") is None
    assert not any(t.startswith("Z:") for t in tocadas)


def test_ruta_local_distingue_unidades():
    from nucleo import vrm
    assert vrm.ruta_local(str(Path(__file__).resolve())) is True
    assert vrm.ruta_local(r"\\servidor\recurso\a.vrm") is False
    assert vrm.ruta_local("//servidor/recurso/a.vrm") is False
    assert vrm.ruta_local("a.vrm") is False
