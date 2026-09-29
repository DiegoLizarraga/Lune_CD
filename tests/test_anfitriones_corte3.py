"""
Tests del integrador de anfitriones del corte 3 (mascota + VRM):

  · Herramientas del modelo `mascota_dormir`, `mascota_despertar` y
    `mascota_tamano` en la piel web (ui/web_bridge.py) y en la nativa (main.py):
    registradas por ServiciosEscritorio, con la mascota a la vista (mock), error
    claro sin mascota, tamaño normalizado, en_ui desde otro hilo y el modo del
    turno ("mascota"/"vrm" con ella fuera; en "normal" no están disponibles).
  · Slots de la biblioteca VRM (vrm_biblioteca, vrm_meta, vrm_miniatura,
    vrm_ajustes, vrm_borrar, vrm_params, vrm_barra) sobre una carpeta temporal,
    rechazando nombres con rutas.
  · ui/web_shell.py publica y republica /vrm/actual.vrm y avisa a la página.
  · ui/settings_panel.py: el panel VRM solo con render «vrm».
  · patata.py: aviso de sueño tras una pausa larga (reloj falso).
  · sidebar.jsx: el avatar 3D de la barra (React de mentira en Node) y el index.html.

Sin red ni pantalla (offscreen). Sin Node, los tests de JS se saltan.
"""
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

# QtWebEngine tiene que importarse ANTES de crear la QApplication (la crea conftest).
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
    HAY_WEBENGINE = True
except ImportError:
    HAY_WEBENGINE = False

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from test_vrm_miniatura import vrm0_con_miniatura, vrm1_con_miniatura  # noqa: E402

KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
BABEL = RAIZ / "ui_web" / "vendor" / "babel.min.js"


# ── Falsos ───────────────────────────────────────────────────────────────────────

class MascotaFalsa:
    """Lo que el contrato pide a CompanionFlotante / AvatarOverlay (y poco más)."""

    def __init__(self, render="vrm", visible=True, dormir_ok=True, durmiendo=False):
        self.render = render
        self.visible = visible
        self.cerrado = False
        self.dormir_ok = dormir_ok
        self.durmiendo = durmiendo
        self.llamadas = []
        self.hilos = []

    def isVisible(self):
        return self.visible

    def set_estado(self, estado, ms=0):
        self.llamadas.append(("estado", estado))

    def dormir(self):
        self.llamadas.append(("dormir",))
        self.hilos.append(threading.get_ident())
        if self.dormir_ok:
            self.durmiendo = True
        return self.dormir_ok

    def despertar(self):
        self.llamadas.append(("despertar",))
        self.durmiendo = False
        return True

    def aplicar_tamano(self, t):
        self.llamadas.append(("tamano", t))

    def aplicar_params_vrm(self):
        self.llamadas.append(("params",))

    def recargar_modelo(self):
        self.llamadas.append(("recargar",))

    def nombres(self):
        return [ll[0] for ll in self.llamadas]


class VozFalsa:
    def __init__(self):
        self._enabled = False
        self.available = False
        self.on_error = None
        self.al_hablar = None

    def cancelar(self):
        pass

    def invalidar_params(self):
        pass

    def reiniciar_motor(self):
        pass


class AIFalso:
    def __init__(self):
        self.providers = {}

    def clear_history(self):
        pass

    def reload_provider(self):
        pass


ALMACEN = {"bot": {"personaje_default": "Lune"},
           "personajes": [{"nombre": "Lune", "systemPrompt": "x", "vrm": "a_luna.vrm"},
                          {"nombre": "Aria", "systemPrompt": "y", "vrm": "b_vieja.vrm"}]}


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    from nucleo import vrm
    c = tmp_path / "modelo_vrm"
    c.mkdir()
    (c / "a_luna.vrm").write_bytes(vrm1_con_miniatura())
    (c / "b_vieja.vrm").write_bytes(vrm0_con_miniatura())
    monkeypatch.setattr(vrm, "CARPETA", c)
    vrm._miniatura_url.cache_clear()
    return c


@pytest.fixture
def almacen(monkeypatch):
    from nucleo import datos, personajes
    alm = copy.deepcopy(ALMACEN)
    monkeypatch.setattr(personajes, "_load", lambda: alm)
    monkeypatch.setattr(personajes, "_save", lambda d: None)
    monkeypatch.setattr(datos, "invalidar", lambda: None)
    return alm


@pytest.fixture
def puente(qapp, tmp_path, monkeypatch, carpeta, almacen):
    from nucleo.config import Config
    from servicios.tools import ToolManager
    from ui.web_bridge import LuneBridge
    memoria = MagicMock()
    memoria.procesar_mensaje_usuario.return_value = None
    memoria.obtener_contexto_para_prompt.return_value = ""
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "vrm")
    b = LuneBridge(config=cfg, ai_manager=AIFalso(), memoria=memoria, tools=ToolManager(),
                   voice=VozFalsa(),
                   opciones_acciones={"audit_path": None, "programar": lambda s, fn: MagicMock()})
    senales = {n: [] for n in ("herramienta", "aviso", "modelo_vrm_cambio", "vrm_params_cambio", "done")}
    for n, lista in senales.items():
        getattr(b, n).connect(lambda *a, l=lista: l.append(a if len(a) != 1 else a[0]))
    b._ventana_a_la_vista = lambda: True
    b.senales = senales
    yield b
    b.cerrar_escritorio()
    b.deleteLater()


def _turno(b, modo):
    from servicios.tools import ctx_acciones
    b._turno = {"origen": "usuario", "ctx": ctx_acciones(b.ai, "ollama", modo), "mascota": False}


def _procesar_hasta(qapp, cond, t=5.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin and not cond():
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    return cond()


# ── Catálogo ─────────────────────────────────────────────────────────────────────

def test_las_tres_herramientas_estan_en_el_catalogo_con_su_nivel():
    from lune_core import catalogo_herramientas as cat
    from lune_core.herramientas import Riesgo
    for nombre in ("mascota_dormir", "mascota_despertar", "mascota_tamano"):
        h = cat.obtener(nombre)
        assert h is not None, nombre
        assert h.riesgo == Riesgo.ESCRITURA and h.requiere_aprobacion is False
        assert h.disponible_en("vrm")
        # G4: el tamaño solo existe en la 3D (con sprites/animada no se vería nada).
        assert h.disponible_en("mascota") is (nombre != "mascota_tamano")
        assert not h.disponible_en("normal") and not h.disponible_en("patata")
    assert cat.obtener("mascota_tamano").args["tamano"].enum == ("pequeno", "normal", "grande")


# ── Piel web: herramientas ───────────────────────────────────────────────────────

def test_web_registra_las_tres_herramientas(puente):
    b = puente
    for nombre in ("mascota_dormir", "mascota_despertar", "mascota_tamano"):
        assert nombre in b.tools.handlers
        assert nombre in b.acciones.ejecutor.handlers                # llegan al Ejecutor
    assert "cambiar_voz" in b.tools.handlers                         # lo del corte 2 sigue


def test_web_dormir_ok_falla_y_sin_mascota(puente):
    b = puente
    dormir = b.tools.handlers["mascota_dormir"]
    ov = MascotaFalsa()
    b._overlay = ov
    r = dormir({}, {"modo": "vrm"})
    assert isinstance(r, str) and "siesta" in r and ov.nombres() == ["dormir"]
    assert dormir({}, {"modo": "vrm"}) == "Ya estoy dormida. Shh."   # no la vuelve a dormir
    ov2 = MascotaFalsa(dormir_ok=False)
    b._overlay = ov2
    ok, motivo = dormir({}, None)
    assert ok is False and "no puedo dormirme" in motivo
    b._overlay = None
    ok, motivo = dormir({}, {"modo": "vrm"})
    assert ok is False and "No hay mascota" in motivo
    b._overlay = MascotaFalsa(visible=False)                          # oculta = no está fuera
    ok, _ = dormir({}, {})
    assert ok is False


def test_web_despertar(puente):
    b = puente
    ov = MascotaFalsa(durmiendo=True)
    b._overlay = ov
    r = b.tools.handlers["mascota_despertar"]({}, {"modo": "vrm"})
    assert "despierta" in r and ov.nombres() == ["despertar"] and ov.durmiendo is False
    assert b.tools.handlers["mascota_despertar"]({}, {}) == "Ya estaba despierta."
    b._overlay = None
    ok, motivo = b.tools.handlers["mascota_despertar"]({}, {})
    assert ok is False and "despertar" in motivo


def test_web_tamano_normalizado_y_sin_mascota(puente):
    b = puente
    ov = MascotaFalsa()
    b._overlay = ov
    ok, msg = b.tools.handlers["mascota_tamano"]({"tamano": "Pequeña"}, {"modo": "vrm"})
    assert ok is True and "pequeña" in msg
    assert ov.llamadas == [("tamano", "pequeno")]
    assert b.config.get("avatar", "vrm_tamano") == "pequeno"
    ok, msg = b.tools.handlers["mascota_tamano"]({"tamano": "enorme"}, {})
    assert ok is True and ov.llamadas[-1] == ("tamano", "grande")
    ok, _ = b.tools.handlers["mascota_tamano"]({"tamano": "gigantesca"}, {})
    assert ok is False
    b._overlay = None                                                 # sin mascota: se guarda
    ok, msg = b.tools.handlers["mascota_tamano"]({"tamano": "normal"}, {})
    assert ok is True and msg.startswith("Guardado") and b.config.get("avatar", "vrm_tamano") == "normal"


def test_web_herramienta_desde_otro_hilo_se_hace_en_el_de_qt(puente, qapp):
    b = puente
    ov = MascotaFalsa()
    b._overlay = ov
    res = {}
    hilo = threading.Thread(target=lambda: res.setdefault("r", b.tools.handlers["mascota_dormir"]({}, {})))
    hilo.start()
    assert _procesar_hasta(qapp, lambda: not hilo.is_alive())
    assert ov.hilos == [threading.get_ident()]                       # dormir() en el hilo de Qt
    assert isinstance(res["r"], str)
    # Sin nadie atendiendo la cola: TimeoutError, no se cuelga.
    caja = {}

    def sin_respuesta():
        try:
            b.en_ui(lambda: None, espera_s=0.05)
        except TimeoutError as e:
            caja["e"] = e
    h2 = threading.Thread(target=sin_respuesta)
    h2.start(); h2.join(3)
    assert isinstance(caja.get("e"), TimeoutError)
    qapp.processEvents()                                              # vacía lo encolado
    assert b.en_ui(lambda: 42) == 42                                 # en el hilo de Qt: directo


def test_web_modo_del_turno_y_ejecutor(puente, monkeypatch):
    b = puente
    assert b._modo_acciones() == "normal"
    ov = MascotaFalsa(render="vrm")
    b._overlay = ov
    assert b._modo_acciones() == "vrm"
    ov.render = "animado"
    assert b._modo_acciones() == "mascota"
    ov.visible = False
    assert b._modo_acciones() == "normal"
    ov.visible, ov.render = True, "vrm"
    # En modo "vrm" el Ejecutor la hace; en "normal" no está disponible.
    _turno(b, "vrm")
    b._on_done('Me echo una siesta. <|CALL ["mascota_dormir", {}]|>')
    ok, _i, _t, detalle = b.senales["herramienta"][-1]
    assert ok is True and "siesta" in detalle and "dormir" in ov.nombres()
    _turno(b, "normal")
    b._on_done('<|CALL ["mascota_despertar", {}]|>')
    ok, _i, _t, detalle = b.senales["herramienta"][-1]
    assert ok is False and "disponible" in detalle and "despertar" not in ov.nombres()
    # El envío usa el modo de la mascota (ctx y prompt del AIWorker).
    import ui.web_bridge as wb

    class Worker(QObject):
        token_received = pyqtSignal(str)
        response_ready = pyqtSignal(str)
        error_occurred = pyqtSignal(str)
        creados = []

        def __init__(self, *a, **kw):
            super().__init__()
            self.kw = kw
            Worker.creados.append(self)

        def start(self):
            pass

        def isRunning(self):
            return False
    monkeypatch.setattr(wb, "AIWorker", Worker)
    b.enviar("duérmete", "local")
    assert Worker.creados[-1].kw["modo"] == "vrm" and Worker.creados[-1].kw["ctx"]["modo"] == "vrm"


# ── Piel web: biblioteca VRM ─────────────────────────────────────────────────────

def test_nombre_modelo_seguro():
    from ui.web_bridge import nombre_modelo_seguro
    assert nombre_modelo_seguro(" a_luna.vrm ") == "a_luna.vrm"
    for malo in ("../a_luna.vrm", "..\\a_luna.vrm", "sub/a_luna.vrm", "sub\\a_luna.vrm",
                 "C:\\Windows\\a_luna.vrm", "C:/x/a_luna.vrm", "/etc/a_luna.vrm", "..", "",
                 "a..b.vrm", "a_luna.txt", "NUL.vrm", "C:a_luna.vrm", None):
        with pytest.raises(ValueError):
            nombre_modelo_seguro(malo)


def test_slots_de_la_biblioteca(puente, carpeta):
    b = puente
    bib = json.loads(b.vrm_biblioteca())
    assert [m["archivo"] for m in bib["modelos"]] == ["a_luna.vrm", "b_vieja.vrm"]
    assert bib["activo"] == "Lune" and bib["activo_vrm"] == "a_luna.vrm"
    f = json.loads(b.vrm_meta("a_luna.vrm"))
    assert f["ok"] is True and f["personajes"] == ["Lune"] and "efectivos" in f
    for malo in ("../a_luna.vrm", "C:\\x\\a_luna.vrm", "sub/a_luna.vrm"):
        assert json.loads(b.vrm_meta(malo))["ok"] is False
        assert b.vrm_miniatura(malo) == ""
    assert b.vrm_miniatura("a_luna.vrm").startswith("data:image/png;base64,")
    assert b.vrm_miniatura("no_existe.vrm") == ""
    p = json.loads(b.vrm_params("a_luna.vrm"))
    from nucleo import vrm
    assert set(p) == set(vrm.AJUSTES)
    assert json.loads(b.vrm_params("../a_luna.vrm"))["ok"] is False


def test_vrm_ajustes_guarda_aplica_y_rechaza_rutas(puente, carpeta, tmp_path):
    b = puente
    ov = MascotaFalsa()
    b._overlay = ov
    r = json.loads(b.vrm_ajustes("a_luna.vrm", json.dumps({"luz": 9, "pesoOjos": 0.3, "otra": 1})))
    assert r["ok"] is True and r["ajustes"] == {"luz": 3.0, "pesoOjos": 0.3}
    assert (carpeta / "a_luna.lune.json").is_file()
    assert ov.nombres() == ["params"]                                 # en vivo a la mascota 3D
    assert json.loads(b.senales["vrm_params_cambio"][-1])["luz"] == 3.0   # y a la barra (es el actual)
    # Otro modelo (no es el que se ve): la mascota se refresca, la barra no.
    n = len(b.senales["vrm_params_cambio"])
    assert json.loads(b.vrm_ajustes("b_vieja.vrm", '{"altura": 0.1}'))["ok"] is True
    assert len(b.senales["vrm_params_cambio"]) == n
    # Rutas: nada se escribe fuera de modelo_vrm/ (nucleo.vrm aceptaría una ruta absoluta).
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "a_luna.vrm").write_bytes(vrm1_con_miniatura())
    for malo in (str(fuera / "a_luna.vrm"), "../a_luna.vrm", "..\\a_luna.vrm", "x/a_luna.vrm"):
        r = json.loads(b.vrm_ajustes(malo, '{"luz": 2}'))
        assert r["ok"] is False and r["error"]
    assert not (fuera / "a_luna.lune.json").exists()
    assert json.loads(b.vrm_ajustes("no_existe.vrm", '{"luz": 2}'))["ok"] is False
    assert not (carpeta / "no_existe.lune.json").exists()
    assert json.loads(b.vrm_ajustes("a_luna.vrm", "{no es json"))["ok"] is False


def test_vrm_borrar_recarga_la_mascota_y_la_barra(puente, carpeta, almacen):
    b = puente
    ov = MascotaFalsa()
    b._overlay = ov
    for malo in ("../b_vieja.vrm", "C:\\b_vieja.vrm", str(carpeta / "b_vieja.vrm")):
        assert json.loads(b.vrm_borrar(malo))["ok"] is False
    assert (carpeta / "b_vieja.vrm").is_file() and ov.llamadas == []
    r = json.loads(b.vrm_borrar("b_vieja.vrm"))
    assert r["ok"] is True and r["personajes"] == ["Aria"] and r["modelos"] == ["a_luna.vrm"]
    assert not (carpeta / "b_vieja.vrm").exists()
    assert "vrm" not in almacen["personajes"][1]
    assert ov.nombres() == ["recargar"] and len(b.senales["modelo_vrm_cambio"]) == 1
    assert json.loads(b.vrm_borrar("b_vieja.vrm"))["ok"] is False    # ya no está


def test_modelo_vrm_cambio_con_personaje_y_asignacion(puente, almacen):
    b = puente
    ov = MascotaFalsa()
    b._overlay = ov
    assert b.personaje_activar("Aria") is True
    assert almacen["bot"]["personaje_default"] == "Aria"
    assert ov.nombres() == ["recargar"] and len(b.senales["modelo_vrm_cambio"]) == 1
    assert json.loads(b.personaje_vrm("Aria", "a_luna.vrm"))["ok"] is True
    assert len(b.senales["modelo_vrm_cambio"]) == 2
    assert json.loads(b.personaje_vrm("Lune", ""))["ok"] is True     # no es el activo: nada
    assert len(b.senales["modelo_vrm_cambio"]) == 2


def test_vrm_barra_da_lo_que_publico_web_shell(puente):
    b = puente
    i = json.loads(b.vrm_barra())
    assert i == {"url": "", "v": "", "archivo": "", "params": "", "render": "vrm"}
    b.vrm_barra_info = {"url": "/vrm/actual.vrm", "v": "1a-2b", "archivo": "a_luna.vrm",
                        "params": "{}", "render": "animado", "otra": 1}
    i = json.loads(b.vrm_barra())
    assert i["url"] == "/vrm/actual.vrm" and i["v"] == "1a-2b" and i["render"] == "vrm"
    assert "otra" not in i


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


def test_guardar_config_seguir_cursor_y_render(qapp, tmp_path, monkeypatch, carpeta, datos_tmp):
    from nucleo.config import Config
    from servicios.tools import ToolManager
    from ui.web_bridge import LuneBridge
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "animado")
    b = LuneBridge(config=cfg, ai_manager=AIFalso(), memoria=MagicMock(), tools=ToolManager(),
                   voice=VozFalsa(), opciones_acciones={"audit_path": None})
    try:
        cambios, params = [], []
        b.modelo_vrm_cambio.connect(lambda: cambios.append(1))
        b.vrm_params_cambio.connect(params.append)
        ov = MascotaFalsa(render="animado")
        b._overlay = ov
        assert json.loads(b.get_config())["seguir_cursor"] is True
        assert json.loads(b.guardar_config(json.dumps({"seguir_cursor": False})))["ok"] is True
        assert cfg.get("avatar", "seguir_cursor") is False
        assert "params" in ov.nombres()
        assert params and json.loads(params[-1])["pesoCabeza"] == 0.0     # sin seguimiento
        assert cambios == []
        monkeypatch.setattr(b, "_mascota_recrear", lambda: None)
        assert json.loads(b.guardar_config(json.dumps({"mascota_render": "vrm"})))["ok"] is True
        assert cfg.get("avatar", "render") == "vrm" and cambios == [1]
        assert json.loads(b.guardar_config(json.dumps({"vrm_archivo": "b_vieja.vrm"})))["ok"] is True
        assert cfg.get("avatar", "vrm_archivo") == "b_vieja.vrm" and cambios == [1, 1]
        assert json.loads(b.guardar_config(json.dumps({"vrm_archivo": "b_vieja.vrm"})))["ok"] is True
        assert cambios == [1, 1]                                           # sin cambio, sin aviso
    finally:
        b.cerrar_escritorio()
        b.deleteLater()


# ── web_shell: /vrm/actual.vrm ───────────────────────────────────────────────────

class _Pagina:
    def __init__(self):
        self.js = []

    def runJavaScript(self, codigo, *a):
        self.js.append(codigo)


class _Web:
    def __init__(self):
        self.pagina = _Pagina()

    def page(self):
        return self.pagina


def _ventana_falsa(tmp_path, config):
    pytest.importorskip("PyQt6.QtWebEngineWidgets")
    import ui.web_shell as ws
    from ui.servidor_web import ServidorEstatico
    yo = types.SimpleNamespace(_servidor=ServidorEstatico(tmp_path), web=_Web(), _vrm_info=None,
                               bridge=types.SimpleNamespace(config=config, vrm_barra_info={}))
    for n in ("_publicar_vrm", "_vrm_params", "_js"):
        setattr(yo, n, types.MethodType(getattr(ws.VentanaWeb, n), yo))
    return yo


def test_publicar_vrm_publica_republica_y_despublica(tmp_path, carpeta, almacen):
    pytest.importorskip("PyQt6.QtWebEngineWidgets")
    from test_vrm_miniatura import ConfigFalsa
    import ui.web_shell as ws
    from ui.servidor_web import ServidorEstatico
    srv = ServidorEstatico(tmp_path)
    cfg = ConfigFalsa({"peso_torso": 0.5})
    i = ws.publicar_vrm(srv, cfg)
    assert srv.rutas_extra["/vrm/actual.vrm"] == carpeta / "a_luna.vrm"
    assert i["url"] == "/vrm/actual.vrm" and i["archivo"] == "a_luna.vrm" and i["v"]
    assert json.loads(i["params"])["pesoTorso"] == 0.5
    almacen["bot"]["personaje_default"] = "Aria"                        # otro personaje, otro .vrm
    i2 = ws.publicar_vrm(srv, cfg)
    assert srv.rutas_extra["/vrm/actual.vrm"] == carpeta / "b_vieja.vrm" and i2["v"] != i["v"]
    for f in carpeta.glob("*.vrm"):
        f.unlink()
    for p in almacen["personajes"]:
        p.pop("vrm", None)
    i3 = ws.publicar_vrm(srv, cfg)
    assert i3["url"] == "" and "/vrm/actual.vrm" not in srv.rutas_extra


def test_ventana_avisa_a_la_pagina_solo_si_cambia(tmp_path, carpeta, almacen):
    from nucleo.config import Config
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "vrm")
    yo = _ventana_falsa(tmp_path, cfg)
    info = yo._publicar_vrm()
    js = yo.web.pagina.js
    assert len(js) == 1 and "LuneVRMBarra.recargar(i.url, i.v)" in js[0] and "/vrm/actual.vrm" in js[0]
    assert info["v"] in js[0] and "lune-vrm-modelo" in js[0]
    assert yo.bridge.vrm_barra_info["url"] == "/vrm/actual.vrm" and yo.bridge.vrm_barra_info["render"] == "vrm"
    yo._publicar_vrm()
    assert len(js) == 1                                                # nada cambió: no se recarga
    time.sleep(0.01)
    (carpeta / "a_luna.vrm").write_bytes(vrm1_con_miniatura(nombre="Otra"))   # el archivo cambió
    info2 = yo._publicar_vrm()
    assert len(js) == 2 and info2["v"] != info["v"] and info2["v"] in js[1]
    yo._vrm_params('{"luz": 2.0}')
    assert "LuneVRMBarra.params(p)" in js[-1] and yo.bridge.vrm_barra_info["params"] == '{"luz": 2.0}'
    cfg.set("avatar", "render", "animado")
    yo._publicar_vrm()
    assert len(js) == 4 and '"render": "animado"' in js[-1]
    yo.web = None                                                      # antes de crear la página
    yo._publicar_vrm()                                                 # no revienta


def test_js_vrm_barra_escapa_el_cierre_de_script():
    pytest.importorskip("PyQt6.QtWebEngineWidgets")
    import ui.web_shell as ws
    js = ws.js_vrm_barra({"url": "/vrm/actual.vrm", "v": "1", "archivo": "</script><b>.vrm", "params": ""})
    assert "</script>" not in js and "<\\/script>" in js
    assert "</" not in ws.js_vrm_params('{"x": "</script>"}')


def test_web_shell_conecta_las_senales_del_puente():
    src = (RAIZ / "ui" / "web_shell.py").read_text("utf-8")
    assert "modelo_vrm_cambio.connect(self._publicar_vrm)" in src
    assert "vrm_params_cambio.connect(self._vrm_params)" in src
    # se publica antes de cargar la página (la página lo pide con vrm_barra())
    assert src.index("self._publicar_vrm()") < src.index("self.web.setUrl(")


# ── Nativa (main.py) ─────────────────────────────────────────────────────────────

class _Emisor(QObject):
    senal = pyqtSignal(object)


def _ventana_nativa(ov, config=None):
    import main
    W = main.LuneCDWindow
    emisor = _Emisor()
    emisor.senal.connect(W._correr_en_ui)
    esc = MagicMock()
    yo = types.SimpleNamespace(_overlay=ov, config=config, MODO_ACCIONES="normal", ESPERA_UI_S=2.0,
                               _hilo_qt=threading.get_ident(), _en_ui_senal=emisor.senal,
                               escritorio=esc, _emisor=emisor)
    for n in ("_mascota_viva", "_mascota_a_la_vista", "_modo_acciones", "en_ui", "_ctx_mascota",
              "_h_mascota_dormir", "_h_mascota_despertar", "_h_mascota_tamano", "_on_vrm_cambiado",
              "_registrar_herramientas_mascota"):
        setattr(yo, n, types.MethodType(getattr(W, n), yo))
    return yo


def test_nativa_registra_las_herramientas_en_escritorio(qapp):
    yo = _ventana_nativa(None)
    yo._registrar_herramientas_mascota()
    nombres = [c.args[0] for c in yo.escritorio.registrar_herramienta.call_args_list]
    assert nombres == ["mascota_dormir", "mascota_despertar", "mascota_tamano"]
    src = (RAIZ / "main.py").read_text("utf-8")
    assert src.index("self._registrar_herramientas_mascota()") < src.index(
        "self.escritorio.conectar_herramientas(self.tools)")


def test_nativa_dormir_despertar_tamano(qapp, tmp_path):
    from nucleo.config import Config
    cfg = Config(str(tmp_path / "config.json"))
    ov = MascotaFalsa()
    yo = _ventana_nativa(ov, cfg)
    assert "siesta" in yo._h_mascota_dormir({}, {"modo": "vrm"})
    assert "despierta" in yo._h_mascota_despertar({}, {"modo": "vrm"})
    ov.dormir_ok = False
    ok, motivo = yo._h_mascota_dormir({}, None)
    assert ok is False and "no puedo" in motivo
    ok, msg = yo._h_mascota_tamano({"tamano": "GRANDE"}, {})
    assert ok is True and ov.llamadas[-1] == ("tamano", "grande") and cfg.get("avatar", "vrm_tamano") == "grande"
    yo._overlay = None
    ok, motivo = yo._h_mascota_dormir({}, {})
    assert ok is False and "No hay mascota" in motivo
    ok, msg = yo._h_mascota_tamano({"tamano": "mediana"}, {})
    assert ok is True and cfg.get("avatar", "vrm_tamano") == "normal"


def test_nativa_modo_y_otro_hilo(qapp):
    from ui.avatar_overlay import AvatarOverlay
    ov = MascotaFalsa(render="vrm")
    yo = _ventana_nativa(ov)
    assert yo._modo_acciones() == "vrm"
    ov.render = "animado"
    assert yo._modo_acciones() == "mascota"
    ov.visible = False
    assert yo._modo_acciones() == "normal"
    sprites = MagicMock(spec=AvatarOverlay)
    sprites.isVisible.return_value = True
    sprites.cerrado = False
    yo._overlay = sprites
    assert yo._modo_acciones() == "mascota"
    ov = MascotaFalsa()
    yo._overlay = ov
    res = {}
    hilo = threading.Thread(target=lambda: res.setdefault("r", yo._h_mascota_dormir({}, {})))
    hilo.start()
    assert _procesar_hasta(qapp, lambda: not hilo.is_alive())
    assert ov.hilos == [threading.get_ident()] and isinstance(res["r"], str)
    src = (RAIZ / "main.py").read_text("utf-8")
    assert "modo = self._modo_acciones()" in src and "modo=modo, ctx=ctx" in src


def test_nativa_panel_vrm_recarga_y_aplica_params(qapp):
    ov = MascotaFalsa()
    yo = _ventana_nativa(ov)
    yo._on_vrm_cambiado()
    assert ov.nombres() == ["recargar", "params"]
    yo._overlay = types.SimpleNamespace(cerrado=False)                  # sprites: sin métodos 3D
    yo._on_vrm_cambiado()
    yo._overlay = None
    yo._on_vrm_cambiado()
    src = (RAIZ / "main.py").read_text("utf-8")
    assert "senal_vrm.connect(self._on_vrm_cambiado)" in src


# ── Ajustes nativos: panel VRM ───────────────────────────────────────────────────

@pytest.fixture
def ajustes(qapp, tmp_path, monkeypatch, carpeta, almacen):
    from nucleo.config import Config
    from servicios import autoinicio, voces
    from ui import settings_panel as SP
    datos_panel = {"apis": {"openrouter_key": ""},
                   "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": ""},
                   "bot": {"personaje_default": "Lune"},
                   "personajes": [{"nombre": "Lune", "systemPrompt": "x", "fraseInicial": "hola"}]}
    guardados = []
    monkeypatch.setattr(SP.datos, "cargar", lambda: copy.deepcopy(datos_panel))
    monkeypatch.setattr(SP.datos, "guardar", lambda d: guardados.append(d))
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(autoinicio, "establecer", lambda on: None)
    monkeypatch.setattr(voces, "_voz_personaje", lambda p: SP.voz_de(p))
    cfg = Config(str(tmp_path / "config.json"))
    creados = []

    def crear(render):
        cfg.set("avatar", "render", render)
        p = SP.SettingsPanel(cfg, voice=None)
        creados.append(p)
        return p
    yield types.SimpleNamespace(crear=crear, cfg=cfg, guardados=guardados)
    for p in creados:
        p.vrm_panel._timer.stop()
        p.deleteLater()


def test_ajustes_panel_vrm_solo_con_render_vrm(ajustes):
    p = ajustes.crear("sprites")
    assert p.vrm_panel.isHidden()
    p.render_combo.setCurrentIndex(p.render_combo.findData("vrm"))
    assert not p.vrm_panel.isHidden()
    assert p.vrm_panel.combo.count() == 2                           # los .vrm de la carpeta
    p.render_combo.setCurrentIndex(p.render_combo.findData("animado"))
    assert p.vrm_panel.isHidden()
    p2 = ajustes.crear("vrm")
    assert not p2.vrm_panel.isHidden()


def test_ajustes_propaga_cambiado_y_guarda_lo_pendiente(ajustes, carpeta):
    p = ajustes.crear("vrm")
    avisos = []
    p.vrm_cambiado.connect(lambda: avisos.append(1))
    p.vrm_panel.cambiado.emit()
    assert avisos == [1]
    s = p.vrm_panel.sliders["pesoCabeza"]
    s.setValue(40)                                                   # espera 250 ms para escribir
    assert p.vrm_panel.pendiente
    p._save()
    assert not p.vrm_panel.pendiente                                 # Guardar lo escribió ya
    from nucleo import vrm
    assert vrm.ajustes_modelo(p.vrm_panel.modelo)["pesoCabeza"] == 0.4
    assert avisos[-1] == 1 and len(avisos) >= 2


# ── Patata: aviso de sueño ───────────────────────────────────────────────────────

@pytest.fixture
def patata_falsa(tmp_path, datos_tmp):
    import patata
    from nucleo.config import Config
    from nucleo.consola import ConsolaAsincrona
    from test_patata import AIFalsa, ApiFalsa, EntradaBloqueante, MemFalsa
    creadas = []

    def crear(dormir_min=10, texto="Hola"):
        reloj = {"t": 1000.0}
        entrada = EntradaBloqueante()
        out = io.StringIO()
        consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=ApiFalsa(), ansi=False)
        cfg = Config(str(tmp_path / "config.json"))
        cfg.set("avatar", "dormir_min", dormir_min)
        p = patata.Patata(color=False, consola=consola, config=cfg, ai=AIFalsa(texto),
                          memoria=MemFalsa(), voice=None, tools=None,
                          reloj_sueno=lambda: reloj["t"])
        p.reloj, p.out, p.entrada = reloj, out, entrada
        creadas.append(p)
        return p
    yield crear
    for p in creadas:
        p.entrada.put(None)
        p.cerrar()


class _FrasesFalsas:
    def __init__(self, frase):
        self.frase = frase
        self.pedidas = []

    def elegir(self, evento, forzar=False):
        self.pedidas.append(evento)
        return self.frase


def test_patata_avisa_si_se_durmio_antes_de_responder(patata_falsa):
    p = patata_falsa(dormir_min=10, texto="Aquí estoy")
    p._frases = _FrasesFalsas("Mmh… ¿ya es de día?")
    p.reloj["t"] += 25 * 60                                          # 25 min sin escribirle
    p.responder("cuéntame algo")                                     # «hola»: instantánea
    salida = p.out.getvalue()
    assert "Lune se quedó dormida hace 15 min" in salida and "zzZ" in salida
    assert "Mmh… ¿ya es de día?" in salida and "-.-" in salida
    assert salida.index("se quedó dormida") < salida.index("Aquí estoy")
    assert p._frases.pedidas == ["despertar"]
    p.reloj["t"] += 60                                               # un minuto: despierta
    antes = len(p.out.getvalue())
    p.responder("¿sigues?")
    assert "dormida" not in p.out.getvalue()[antes:]
    assert p._frases.pedidas == ["despertar"]                        # sin pausa no se tira el dado


def test_patata_sin_frase_o_sin_sueno(patata_falsa):
    p = patata_falsa(dormir_min=10)
    p._frases = _FrasesFalsas(None)                                  # esta vez calla al despertar
    p.reloj["t"] += 3 * 3600
    p.responder("hola")
    salida = p.out.getvalue()
    assert "hace 2 h 50 min" in salida and "-.-" not in salida
    q = patata_falsa(dormir_min=0)                                   # 0 = nunca se duerme
    q._frases = _FrasesFalsas("zz")
    q.reloj["t"] += 10 * 3600
    q.responder("hola")
    assert "dormida" not in q.out.getvalue() and q._frases.pedidas == []


def test_patata_frases_de_verdad_y_sin_qt(patata_falsa):
    p = patata_falsa(dormir_min=1)
    f = p._frases_mascota()
    assert f is not None and hasattr(f, "elegir")
    p.reloj["t"] += 600
    assert p._avisar_si_durmio().startswith("Lune se quedó dormida hace 9 min")
    r = subprocess.run([sys.executable, "-c",
                        "import sys, patata; print(any(m.startswith('PyQt') for m in sys.modules))"],
                       cwd=str(RAIZ), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip().endswith("False"), r.stderr


# ── index.html ───────────────────────────────────────────────────────────────────

def test_index_importmap_modulo_y_biblioteca():
    html = (KIT / "index.html").read_text("utf-8")
    i_map = html.index('<script type="importmap">')
    i_mod = html.index('<script type="module" src="vrm_barra.js"></script>')
    assert i_map < i_mod and html.count('<script type="module" src=') == 1
    bloque = html[i_map:html.index("</script>", i_map)]
    imports = json.loads(bloque[bloque.index("{"):])["imports"]
    assert imports == {"three": "../../vendor/three/three.module.min.js",
                       "three/addons/": "../../vendor/three/",
                       "@pixiv/three-vrm": "../../vendor/three/three-vrm.module.min.js"}
    for ruta in imports.values():                                   # existen desde lune-desktop/
        assert (KIT / ruta).resolve().exists(), ruta
    assert (KIT / "../../vendor/three/loaders/GLTFLoader.js").resolve().is_file()
    bib = '<script type="text/babel" src="extra/vrm_biblioteca.jsx"></script>'
    assert bib in html and html.index(bib) < html.index('src="settings.jsx"')
    assert (KIT / "extra" / "vrm_biblioteca.jsx").is_file()
    assert "canvas.ln-mascot-vrm" in html


def test_settings_enseña_la_biblioteca_con_render_vrm():
    src = (KIT / "settings.jsx").read_text("utf-8")
    assert "c.mascota_render==='vrm' && window.VrmBiblioteca && <window.VrmBiblioteca cfg={c} set={set} />" in src
    assert "seguir_cursor:true" in src


# ── sidebar.jsx en Node (React de mentira con hooks, efectos y refs) ─────────────

ARNES_BARRA = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const [rutaBabel, rutaBarra, rutaJs] = process.argv.slice(2);
const mod = { exports: {} };
new Function('module', 'exports', 'self', 'window', fs.readFileSync(rutaBabel, 'utf8'))(mod, mod.exports, {}, {});
const Babel = mod.exports;
const OPC = { presets: ['react', 'env'], plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'] };
const fallos = []; let checks = 0;
const check = (n, c, d) => { checks++; if (!c) fallos.push(n + (d === undefined ? '' : ' -> ' + JSON.stringify(d))); };

// ── React de mentira: estado por instancia (ruta en el árbol), efectos y refs ──
const Fragment = Symbol('Fragment');
let instancias = new Map(), vistas = null, pendientes = [], actual = null, sucio = false;
const lienzos = new Map();
const cambiaron = (a, b) => !a || !b || a.length !== b.length || a.some((x, i) => !Object.is(x, b[i]));
function slot() { const s = actual; return [s, s.i++]; }
const React = {
  Fragment,
  createElement(type, props, ...children) {
    const p = { ...(props || {}) };
    if (children.length) p.children = children.length === 1 ? children[0] : children;
    return { type, props: p };
  },
  useState(init) {
    const [s, i] = slot();
    if (!(i in s.v)) s.v[i] = typeof init === 'function' ? init() : init;
    return [s.v[i], (v) => { const nv = typeof v === 'function' ? v(s.v[i]) : v; if (!Object.is(nv, s.v[i])) { s.v[i] = nv; sucio = true; } }];
  },
  useRef(v) { const [s, i] = slot(); if (!(i in s.v)) s.v[i] = { current: v }; return s.v[i]; },
  useMemo(fn, deps) { const [s, i] = slot(); if (!(i in s.v) || cambiaron(s.v[i].deps, deps)) s.v[i] = { deps, v: fn() }; return s.v[i].v; },
  useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
  useEffect(fn, deps) {
    const [s, i] = slot();
    if (!(i in s.v)) s.v[i] = { efecto: true, deps: undefined, limpiar: null, hecho: false };
    const e = s.v[i];
    if (!e.hecho || cambiaron(e.deps, deps)) {
      e.deps = deps; e.hecho = true;
      pendientes.push(() => { if (typeof e.limpiar === 'function') e.limpiar(); const r = fn(); e.limpiar = typeof r === 'function' ? r : null; });
    }
  },
};
function expandir(el, ruta) {
  if (el == null || el === false || el === true) return [];
  if (typeof el === 'string' || typeof el === 'number') return [String(el)];
  if (Array.isArray(el)) return el.flatMap((x, i) => expandir(x, ruta + '[' + i + ']'));
  if (el.type === Fragment) return expandir(el.props.children, ruta + '/F');
  if (typeof el.type === 'function') {
    const clave = ruta + '/' + el.type.name + (el.props.key != null ? '#' + el.props.key : '');
    let inst = instancias.get(clave);
    if (!inst) { inst = { v: {}, i: 0 }; instancias.set(clave, inst); }
    vistas.add(clave);
    inst.i = 0;
    const previo = actual; actual = inst;
    let r;
    try { r = el.type(el.props); } finally { actual = previo; }
    return expandir(r, clave);
  }
  const clave = ruta + '/' + el.type;
  vistas.add(clave);
  if (el.props.ref) {
    if (!lienzos.has(clave)) lienzos.set(clave, { tipo: el.type, id: lienzos.size + 1, style: {}, getContext() { return {}; }, addEventListener() {}, removeEventListener() {} });
    el.props.ref.current = lienzos.get(clave);
  }
  return [{ type: el.type, props: el.props, hijos: expandir(el.props.children, clave) }];
}
function desmontar() {
  for (const [clave, inst] of [...instancias]) {
    if (vistas.has(clave)) continue;
    for (const e of Object.values(inst.v)) if (e && e.efecto && typeof e.limpiar === 'function') { try { e.limpiar(); } catch (x) {} }
    instancias.delete(clave);
  }
  for (const clave of [...lienzos.keys()]) if (!vistas.has(clave)) lienzos.delete(clave);
}
function reiniciar() { vistas = new Set(); desmontar(); }
function renderizar(el) {
  let arbol = [], n = 0;
  do {
    sucio = false; vistas = new Set(); pendientes = [];
    arbol = expandir(el, '');
    desmontar();
    for (const f of pendientes) f();
  } while (sucio && ++n < 20);
  return arbol;
}
function buscar(nodos, pred, out = []) {
  for (const n of nodos) { if (n && typeof n === 'object') { if (pred(n)) out.push(n); buscar(n.hijos || [], pred, out); } }
  return out;
}
const tipos = (arbol) => buscar(arbol, () => true).map((n) => n.type);

// ── window de mentira (eventos) y LuneVRMBarra de mentira ──
const oyentes = {};
const ctx = { React, console, JSON, Math, Date, Object, Array, String, Number, Boolean, Promise, Symbol, Set, Map,
  setTimeout: () => 0, clearTimeout: () => {},
  addEventListener(t, f) { (oyentes[t] = oyentes[t] || []).push(f); },
  removeEventListener(t, f) { oyentes[t] = (oyentes[t] || []).filter((x) => x !== f); },
  dispatchEvent(ev) { (oyentes[ev.type] || []).slice().forEach((f) => f(ev)); return true; },
};
ctx.window = ctx;
ctx.CustomEvent = class { constructor(type, o) { this.type = type; this.detail = o && o.detail; } };
ctx.Event = class { constructor(type) { this.type = type; } };
vm.createContext(ctx);
const code = Babel.transform(fs.readFileSync(rutaBarra, 'utf8'), { ...OPC, filename: 'sidebar.jsx' }).code;
vm.runInContext(code, ctx, { filename: 'sidebar.jsx' });
const W = ctx;
const comp = (nombre) => function (props) { return { type: nombre, props }; };
W.LUNE = { ProviderTab: comp('ProviderTab') };
W.IconCloud = W.IconCpu = W.IconBolt = comp('Icon');

let creados = [], destruidos = [];
function barraFalsa() {
  creados = []; destruidos = [];
  return {
    crear(canvas, url, opts) {
      const h = { canvas, url, opts, estados: [], pausas: [],
        setEstado(e) { this.estados.push(e); }, pausar(on) { this.pausas.push(on); return on; } };
      creados.push(h); return h;
    },
    destruir(h) { destruidos.push(h); return true; },
  };
}
const stage = (props) => renderizar(React.createElement(ctx.__MascotStage, props));

check('sidebar: registra Sidebar y LuneBarra', typeof W.Sidebar === 'function' && !!W.LuneBarra);
const N = W.LuneBarra.normalizarVrmBarra;
check('normalizar: url solo del http local', N({ url: 'http://x/y.vrm', render: 'vrm' }).url === '' && N({ url: '//x/y.vrm' }).url === ''
  && N({ url: '/\\x' }).url === '' && N('{"url":"/vrm/actual.vrm"}').url === '/vrm/actual.vrm');
check('normalizar: basura → null', N('no json') === null && N(null) === null);
ctx.__MascotStage = vm.runInContext('MascotStage', ctx);

// 1. Sin VRM: vídeo
W.LuneVRMBarra = barraFalsa();
let a = stage({ state: 'normal' });
check('sin info: vídeo', tipos(a).includes('video') && !tipos(a).includes('canvas'), tipos(a));

// 2. Info en window.__luneVrmBarra con render vrm → canvas y crear
reiniciar();
W.__luneVrmBarra = { render: 'vrm', url: '/vrm/actual.vrm', v: 'a1', archivo: 'a.vrm', params: '{"luz":2}' };
a = stage({ state: 'happy', mascotaFuera: false });
check('vrm: canvas', tipos(a).includes('canvas') && !tipos(a).includes('video'), tipos(a));
check('vrm: crear una vez', creados.length === 1, creados.length);
const h1 = creados[0];
check('vrm: url, versión, params y sin pausa', h1 && h1.url === '/vrm/actual.vrm' && h1.opts.version === 'a1'
  && h1.opts.params === '{"luz":2}' && h1.opts.pausado === false && h1.canvas && h1.canvas.tipo === 'canvas', h1 && h1.opts);
check('vrm: estado inicial', h1 && h1.estados[0] === 'happy', h1 && h1.estados);
a = stage({ state: 'thinking', mascotaFuera: false });
check('vrm: cambia de estado sin recrear', creados.length === 1 && h1.estados[h1.estados.length - 1] === 'thinking', h1.estados);

// 3. Mascota fuera: pausa, sigue montado; vuelve: reanuda
a = stage({ state: 'thinking', mascotaFuera: true });
check('fuera: pausar(true) y el canvas sigue', h1.pausas[h1.pausas.length - 1] === true && tipos(a).includes('canvas') && destruidos.length === 0, h1.pausas);
a = stage({ state: 'thinking', mascotaFuera: false });
check('dentro: pausar(false)', h1.pausas[h1.pausas.length - 1] === false && creados.length === 1, h1.pausas);

// 4. Cambio de modelo (evento de web_shell): misma instancia (ya recargada por LuneVRMBarra.recargar)
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'vrm', url: '/vrm/actual.vrm', v: 'b2', params: '' } }));
a = stage({ state: 'thinking', mascotaFuera: false });
check('modelo nuevo: no recrea (lo recarga vrm_barra.js)', creados.length === 1 && destruidos.length === 0);

// 5. Falla WebGL o el modelo → vídeo; con otra versión se reintenta en un canvas nuevo
h1.opts.alError('WebGL no disponible');
a = stage({ state: 'thinking', mascotaFuera: false });
check('fallo: vuelve al vídeo y destruye', tipos(a).includes('video') && !tipos(a).includes('canvas') && destruidos[0] === h1, tipos(a));
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'vrm', url: '/vrm/actual.vrm', v: 'c3', params: '' } }));
a = stage({ state: 'thinking', mascotaFuera: false });
check('reintento con otra versión: canvas nuevo', creados.length === 2 && creados[1].canvas !== h1.canvas && creados[1].opts.version === 'c3', creados.length);

// 6. Sin modelo (url vacía) → vídeo; con Lune fuera y vídeo → nada
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'vrm', url: '', v: '' } }));
a = stage({ state: 'normal', mascotaFuera: false });
check('sin modelo: vídeo y destruido', tipos(a).includes('video') && destruidos.includes(creados[1]), tipos(a));
a = stage({ state: 'normal', mascotaFuera: true });
check('fuera con vídeo: no dibuja nada', tipos(a).length === 0, tipos(a));

// 7. Render animado → vídeo
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'animado', url: '/vrm/actual.vrm', v: 'd4' } }));
a = stage({ state: 'normal' });
check('render animado: vídeo', tipos(a).includes('video') && creados.length === 2, tipos(a));

// 7b. Un fallo pasajero no deja la barra en vídeo para siempre: volver a render vrm
//     (mismo modelo, misma versión) o cambiar de personaje lo reintenta.
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'vrm', url: '/vrm/actual.vrm', v: 'd4' } }));
a = stage({ state: 'normal' });
const hFallo = creados[creados.length - 1];
check('7b: vrm otra vez', tipos(a).includes('canvas') && creados.length === 3, creados.length);
hFallo.opts.alError('WebGL perdido un momento');
a = stage({ state: 'normal' });
check('7b: fallo → vídeo', tipos(a).includes('video') && !tipos(a).includes('canvas'), tipos(a));
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'animado', url: '/vrm/actual.vrm', v: 'd4' } }));
a = stage({ state: 'normal' });
W.dispatchEvent(new ctx.CustomEvent('lune-vrm-modelo', { detail: { render: 'vrm', url: '/vrm/actual.vrm', v: 'd4' } }));
a = stage({ state: 'normal' });
check('7b: volver a render vrm reintenta el mismo modelo', tipos(a).includes('canvas') && creados.length === 4, creados.length);

// 8. El módulo carga tarde: vídeo y, con 'lune-vrm-barra', el avatar
reiniciar();
delete W.LuneVRMBarra;
W.__luneVrmBarra = { render: 'vrm', url: '/vrm/actual.vrm', v: 'e5' };
a = stage({ state: 'normal' });
check('sin módulo: vídeo', tipos(a).includes('video'), tipos(a));
W.LuneVRMBarra = barraFalsa();
W.dispatchEvent(new ctx.Event('lune-vrm-barra'));
a = stage({ state: 'normal' });
check('módulo tardío: canvas y crear', tipos(a).includes('canvas') && creados.length === 1 && creados[0].opts.version === 'e5', tipos(a));

// 9. El puente: vrm_barra() al montar
reiniciar();
delete W.__luneVrmBarra;
W.LuneVRMBarra = barraFalsa();
let pedidas = 0;
W.lune = { vrm_barra(cb) { pedidas++; cb(JSON.stringify({ render: 'vrm', url: '/vrm/actual.vrm', v: 'f6', params: '' })); } };
a = stage({ state: 'normal' });
check('puente: pide vrm_barra y monta el avatar', pedidas === 1 && tipos(a).includes('canvas') && creados[0].opts.version === 'f6', { pedidas, t: tipos(a) });
delete W.lune;

// 9b. Cambio de personaje (señal personaje_cambio del puente) con el mismo modelo: tras un
//     fallo pasajero, la barra lo reintenta.
reiniciar();
W.__luneVrmBarra = { render: 'vrm', url: '/vrm/actual.vrm', v: 'h8' };
W.LuneVRMBarra = barraFalsa();
let alPers = null;
W.lune = { vrm_barra(cb) { cb(JSON.stringify(W.__luneVrmBarra)); },
  personaje_cambio: { connect(f) { alPers = f; }, disconnect() {} } };
a = stage({ state: 'normal' });
check('9b: escucha personaje_cambio', typeof alPers === 'function' && creados.length === 1, creados.length);
if (creados[0]) creados[0].opts.alError('contexto WebGL perdido');
a = stage({ state: 'normal' });
check('9b: fallo → vídeo', tipos(a).includes('video'), tipos(a));
if (alPers) alPers('Aria');
a = stage({ state: 'normal' });
check('9b: cambio de personaje reintenta', tipos(a).includes('canvas') && creados.length === 2, creados.length);
delete W.lune;

// 10. Sidebar: con Lune fuera, aviso + escenario (el avatar en pausa)
reiniciar();
W.__luneVrmBarra = { render: 'vrm', url: '/vrm/actual.vrm', v: 'g7' };
W.LuneVRMBarra = barraFalsa();
a = renderizar(React.createElement(W.Sidebar, { provider: 'local', onProvider() {}, mascotState: 'normal', mascotaFuera: true, onTraer() {} }));
const t = tipos(a);
check('sidebar fuera: aviso y canvas en pausa', t.includes('canvas') && JSON.stringify(a).includes('Lune está en tu escritorio')
  && creados.length === 1 && creados[0].opts.pausado === true, t);

// JS de web_shell (js_vrm_barra) en una página de mentira
if (rutaJs) {
  const llamadas = [];
  const pag = { eventos: [] };
  pag.window = pag;
  pag.LuneVRMBarra = { params(p) { llamadas.push(['params', p]); }, recargar(u, v) { llamadas.push(['recargar', u, v]); return 1; } };
  pag.CustomEvent = class { constructor(type, o) { this.type = type; this.detail = o && o.detail; } };
  pag.dispatchEvent = (ev) => { pag.eventos.push(ev); return true; };
  pag.Object = Object;
  vm.createContext(pag);
  vm.runInContext(fs.readFileSync(rutaJs, 'utf8'), pag);
  check('web_shell js: guarda la info', pag.__luneVrmBarra && pag.__luneVrmBarra.v === 'zz9');
  check('web_shell js: params y recargar', JSON.stringify(llamadas) === JSON.stringify([['params', '{"luz":1.5}'], ['recargar', '/vrm/actual.vrm', 'zz9']]), llamadas);
  check('web_shell js: evento con recargados', pag.eventos.length === 1 && pag.eventos[0].type === 'lune-vrm-modelo' && pag.eventos[0].detail.recargados === 1);
}

console.log(JSON.stringify({ checks, fallos }));
process.exit(fallos.length ? 1 : 0);
"""


def test_sidebar_avatar_vrm_en_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado: se saltan los tests de JSX")
    rutas_js = []
    if HAY_WEBENGINE:
        import ui.web_shell as ws
        js = tmp_path / "web_shell.js"
        js.write_text(ws.js_vrm_barra({"url": "/vrm/actual.vrm", "v": "zz9", "archivo": "a.vrm",
                                       "params": '{"luz":1.5}', "render": "vrm"}), encoding="utf-8")
        rutas_js.append(str(js))
    arnes = tmp_path / "arnes_barra.cjs"
    arnes.write_text(ARNES_BARRA, encoding="utf-8")
    r = subprocess.run([node, str(arnes), str(BABEL), str(KIT / "sidebar.jsx"), *rutas_js],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    lineas = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    salida = (r.stdout or "")[-3000:] + "\n" + (r.stderr or "")[-3000:]
    assert lineas, f"el arnés de Node no dio resultado:\n{salida}"
    res = json.loads(lineas[-1])
    assert r.returncode == 0 and not res["fallos"], "fallos:\n  " + "\n  ".join(res["fallos"]) + f"\n{salida}"
    assert res["checks"] >= 20
