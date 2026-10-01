"""
Tests de «Lune en reposo» y del consumo de la piel web (11.2):

- ui/web_shell.py: VentanaWeb le dice a la página si es la ventana activa
  (window.luneFoco) al activarse o no, al enseñarse, al ocultarse y al cargar la página
  (la lógica de quedarse quieta es de ui_web/lune_reposo.js: tests/js/reposo.test.mjs).
- Carga perezosa: oculta al arrancar (bandeja o asistente fuera), la página llega al primer
  showEvent; el canal, la bandeja y los servicios, igual que siempre.
- config: efectos.pausar_sin_foco (sí por defecto), también en get_config.
- Fuentes en local (ui_web/fonts con su OFL) y sin peticiones a Google.
- La asistente 3D: las «z z z» solo existen dormida.
- Los vídeos de la asistente: VP9 480×854 a 24 fps, sin alfa.
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
UI = RAIZ / "ui_web"

from test_anfitriones_corte4 import entorno, sistema  # noqa: E402,F401  (fixtures: VentanaWeb de prueba)


# ── Config ─────────────────────────────────────────────────────────────────────
def test_pausar_sin_foco_por_defecto(tmp_path):
    from nucleo.config import Config
    assert Config.DEFAULT_CONFIG["efectos"]["pausar_sin_foco"] is True
    cfg = Config(config_path=str(tmp_path / "config.json"))
    assert cfg.get("efectos", "pausar_sin_foco") is True


def test_get_config_y_guardar_config_llevan_pausar_sin_foco():
    """Ajustes lo guarda al momento por luneEscritorio.efectos_guardar (como los demás efectos);
    get_config lo enseña y guardar_config también lo acepta."""
    fuente = (RAIZ / "ui" / "web_bridge.py").read_text("utf-8")
    assert '"pausar_sin_foco": bool(self.config.get("efectos", "pausar_sin_foco", True))' in fuente
    assert 'self.config.set("efectos", "pausar_sin_foco", bool(c["pausar_sin_foco"]))' in fuente
    ajustes = (UI / "ui_kits" / "lune-desktop" / "settings.jsx").read_text("utf-8")
    assert "Quedarme quieta cuando no me usas" in ajustes
    assert "setFxKey('quieta')" in ajustes
    apariencia = (UI / "ui_kits" / "lune-desktop" / "extra" / "apariencia.jsx").read_text("utf-8")
    assert "quieta: 'pausar_sin_foco'" in apariencia


# ── VentanaWeb → window.luneFoco ────────────────────────────────────────────────
def test_js_foco():
    import ui.web_shell as ws
    assert ws.js_foco(True) == "window.luneFoco && window.luneFoco(true)"
    assert ws.js_foco(False) == "window.luneFoco && window.luneFoco(false)"


@pytest.fixture
def ventana(qapp):
    """Una VentanaWeb sin su __init__ (ni servidor, ni puente, ni página): solo lo del foco."""
    from PyQt6.QtWidgets import QMainWindow
    import ui.web_shell as ws

    class VentanaSolo(ws.VentanaWeb):
        def __init__(self):
            QMainWindow.__init__(self)
            self.enviado = []
            self.activa = False
            self._pagina_cargada = False
            self._al_cargar_pend = []

        def _js(self, codigo):
            self.enviado.append(codigo)

        def isActiveWindow(self):
            return self.activa

    v = VentanaSolo()
    yield v
    v._relevada = True                                   # closeEvent: cerrar de verdad
    v.close()


def _enviar(v, tipo):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
    QApplication.sendEvent(v, QEvent(tipo))


def test_la_ventana_avisa_del_foco_al_cambiar(ventana):
    from PyQt6.QtCore import QEvent
    import ui.web_shell as ws
    v = ventana
    v.show()
    assert v.enviado[-1] == ws.js_foco(False)            # a la vista pero sin ser la activa
    n = len(v.enviado)
    v.activa = True
    _enviar(v, QEvent.Type.ActivationChange)
    assert v.enviado[-1] == ws.js_foco(True)
    _enviar(v, QEvent.Type.ActivationChange)
    assert len(v.enviado) == n + 1, "sin cambios no se repite"
    v.activa = False
    _enviar(v, QEvent.Type.WindowStateChange)            # minimizar también pasa por aquí
    assert v.enviado[-1] == ws.js_foco(False)
    v.activa = True
    _enviar(v, QEvent.Type.ActivationChange)
    v.hide()
    assert v.enviado[-1] == ws.js_foco(False), "oculta en la bandeja: sin foco"


def test_al_cargar_la_pagina_se_le_repite_el_foco(ventana):
    import ui.web_shell as ws
    v = ventana
    v.show()
    v.enviado.clear()
    v._al_cargar(True)
    assert v.enviado == [ws.js_foco(False)], "la página recién cargada no sabe nada: se le dice aunque no cambie"
    assert v._pagina_cargada is True


# ── Carga perezosa: oculta al arrancar, la página al primer showEvent ───────────
def _web_de_prueba(entorno, **kw):
    """VentanaWeb del montaje de prueba de test_anfitriones_corte4 (vista falsa que anota setUrl)."""
    from servicios.tools import ToolManager
    import test_anfitriones_corte4 as c4
    return entorno.ws.VentanaWeb(config=entorno.cfg, ai_manager=c4.AIFalso(), memoria=c4.MemFalsa(),
                                 tools=ToolManager(), **kw)


def _soltar(v):
    try:
        v._liberar_todo()
    finally:
        v._relevada = True
        v.deleteLater()


def test_carga_perezosa_la_pagina_llega_al_enseñarla(entorno, sistema):
    v = _web_de_prueba(entorno, cargar_al_mostrar=True)
    try:
        assert v.web.urls == [], "oculta: ni setUrl (sin proceso de render ni React)"
        # Lo demás arrancó igual: el canal entero, la bandeja y los servicios de escritorio.
        assert sorted(v._canal.registrados) == ["alarmas", "escenario", "escritorio", "lune", "musica",
                                                "tareas", "vida"]
        assert v._servicios and v.tray is not None
        v._js("window.x = 1")                            # lo que se manda antes se pierde sin romper nada
        v.show()
        assert len(v.web.urls) == 1 and v.web.urls[0] == v._url_pagina
        assert v.web.objetos_al_cargar == ["alarmas", "escenario", "escritorio", "lune", "musica", "tareas",
                                           "vida"], "los objetos del canal, registrados ANTES de cargar"
        v.hide()
        v.show()
        assert len(v.web.urls) == 1, "una sola vez"
    finally:
        _soltar(v)


def test_sin_carga_perezosa_la_pagina_va_ya(entorno, sistema):
    v = _web_de_prueba(entorno)
    try:
        assert len(v.web.urls) == 1
        v.show()
        assert len(v.web.urls) == 1
    finally:
        _soltar(v)


def test_carga_perezosa_al_estar_lista_no_se_queda_esperando(entorno, sistema, qapp):
    """Nadie espera una respuesta de la página antes de cargarla: al_estar_lista tiene su tope."""
    import test_anfitriones_corte4 as c4
    v = _web_de_prueba(entorno, cargar_al_mostrar=True)
    try:
        listo = []
        v.al_estar_lista(lambda: listo.append(1), tope_ms=30)
        assert c4._esperar(qapp, lambda: listo == [1])
        assert v.web.urls == []
    finally:
        _soltar(v)


def test_main_crea_la_ventana_web_oculta_con_carga_perezosa(monkeypatch):
    import main
    import ui.web_shell as ws
    pedidas = []

    class VentanaAnotada:
        def __init__(self, **kw):
            pedidas.append(kw)

    monkeypatch.setattr(ws, "VentanaWeb", VentanaAnotada)
    assert isinstance(main._crear_ventana_principal(autoinicio=True, oculta=True), VentanaAnotada)
    assert isinstance(main._crear_ventana_principal(), VentanaAnotada)
    assert pedidas == [{"cargar_al_mostrar": True}, {"cargar_al_mostrar": False}]
    # abrir_principal: oculta salvo que el plan la enseñe o alguien la haya abierto a mano
    fuente = (RAIZ / "main.py").read_text("utf-8")
    assert "oculta=not (mostrar or plan.mostrar_ventana)" in fuente


# ── Página: fuentes en local, sin Google ────────────────────────────────────────
_FUENTE = re.compile(r"url\('\.\./fonts/([^']+)'\)")


def test_sin_peticiones_a_google_fonts():
    for ruta in [UI / "styles.css", *(UI / "tokens").glob("*.css"), UI / "ui_kits" / "lune-desktop" / "index.html",
                 UI / "companion.html", UI / "companion_vrm.html"]:
        texto = ruta.read_text("utf-8")
        assert "googleapis" not in texto and "gstatic" not in texto, ruta.name
        assert 'rel="preconnect"' not in texto, ruta.name


def test_font_face_locales_con_licencia():
    css = (UI / "tokens" / "fonts.css").read_text("utf-8")
    archivos = _FUENTE.findall(css)
    assert len(archivos) >= 14
    for a in archivos:
        assert (UI / "fonts" / a).is_file(), a
        assert a.endswith(".woff2")
    for familia in ("Chakra Petch", "Space Grotesk", "Space Mono", "Noto Sans JP", "Exo 2", "JetBrains Mono"):
        assert f"font-family: '{familia}'" in css, familia
    # Las variantes que usa la interfaz: Chakra Petch 400–700 e itálicas 600/700, Space Mono itálica, JP 700/900
    for peso, estilo in ((400, "normal"), (500, "normal"), (600, "normal"), (700, "normal"), (600, "italic"), (700, "italic")):
        assert re.search(rf"'Chakra Petch'; font-style: {estilo}; font-weight: {peso};", css), (peso, estilo)
    assert re.search(r"'Noto Sans JP'; font-style: normal; font-weight: 900;", css)
    for lic in ("ChakraPetch", "SpaceGrotesk", "SpaceMono", "Exo2", "JetBrainsMono", "NotoSansJP"):
        texto = (UI / "fonts" / f"OFL-{lic}.txt").read_text("utf-8")
        assert "SIL OPEN FONT LICENSE" in texto.upper(), lic
    tipos = (UI / "tokens" / "typography.css").read_text("utf-8")
    assert "'Noto Sans JP', 'Yu Gothic UI', 'Meiryo'" in tipos, "lo que no está en el recorte cae a Windows"


def test_noto_sans_jp_recortada_trae_lo_que_usa_la_interfaz():
    fonttools = pytest.importorskip("fontTools.ttLib")
    usados = "月ルネ起動コマンド"
    for nombre in ("NotoSansJP-Bold-lune.woff2", "NotoSansJP-Black-lune.woff2"):
        f = fonttools.TTFont(str(UI / "fonts" / nombre))
        cmap = f.getBestCmap()
        assert all(ord(c) in cmap for c in usados), nombre
        assert f["OS/2"].usWeightClass in (700, 900)


def test_el_servidor_sirve_woff2_como_fuente():
    from ui.servidor_web import HandlerSilencioso
    assert HandlerSilencioso.extensions_map[".woff2"] == "font/woff2"


# ── Asistente 3D: las «z z z» solo dormida ──────────────────────────────────────
def test_zzz_solo_existen_dormida():
    html = (UI / "companion_vrm.html").read_text("utf-8")
    estilo = html[html.index("<style>"):html.index("</style>")]
    base = re.search(r"#zzz \{[^}]*\}", estilo).group(0)
    assert "display:none" in base
    assert re.search(r"#zzz\.on \{ display:block;", estilo)
    # Sin animación CSS infinita (antes giraban siempre con opacity 0, y dormida a 60 fps): las mueve
    # el módulo 'zzz' en los frames del avatar (tests/js/vrm_fps.test.mjs).
    assert "infinite" not in estilo
    assert not re.search(r"#zzz[^{]*span \{[^}]*animation", estilo)
    assert "nombre: 'zzz'" in html and "trasUpdate(dt, t)" in html


# ── Vídeos de la asistente ──────────────────────────────────────────────────────
def test_videos_de_la_asistente_480_24fps_vp9():
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    import subprocess
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    clips = sorted((UI / "assets" / "asistente" / "anime-videos").glob("lune-*.webm"))
    assert len(clips) >= 15
    for c in clips:
        r = subprocess.run([ff, "-hide_banner", "-i", str(c)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        linea = next(l for l in r.stderr.splitlines() if "Video:" in l)
        assert "vp9" in linea and "yuv420p" in linea, (c.name, linea)       # VP9 sin alfa (nunca H.264)
        assert "480x854" in linea and " 24 fps" in linea, (c.name, linea)


def test_convertir_asistente_reduce_solo_lo_grande():
    sys.path.insert(0, str(RAIZ / "scripts"))
    import convertir_asistente as ca
    assert ca.hace_falta_reducir(1080, 30) and ca.hace_falta_reducir(720, 24) and ca.hace_falta_reducir(480, 30)
    assert not ca.hace_falta_reducir(480, 24)
    orden = ca.orden_vp9("ffmpeg", Path("a.mp4"), Path("a.webm"))
    assert "libvpx-vp9" in orden and "yuv420p" in orden and "-an" in orden
    assert any("scale=480:-2" in x and "fps=24" in x for x in orden)
