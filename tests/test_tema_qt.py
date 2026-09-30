"""
Tests de ui/tema_qt.py (ControlTema) y ui/tema_qss.py.

Offscreen y con un config de mentira que cuenta las escrituras (y uno real de
nucleo.config en una carpeta temporal): la vista previa no toca el disco, varios
guardados seguidos son UNA escritura a los 400 ms (aquí, a los pocos ms), la
asistente recibe el tema al engancharse y en cada cambio, y el QSS y los colores del
radial salen de la paleta.
"""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import tema  # noqa: E402


class ConfigFalsa:
    """Como nucleo.config.Config: secciones en .config y save() para escribir."""

    def __init__(self, tema_=None):
        self.config = {"tema": dict(tema_ or tema.DEFECTO)}
        self.escrituras = []
        self.recargas = 0

    def save(self):
        self.escrituras.append(json.loads(json.dumps(self.config["tema"])))

    def recargar(self):
        self.recargas += 1
        return False


class AsistenteFalsa:
    def __init__(self):
        self.temas = []

    def aplicar_tema(self, css):
        self.temas.append(css)


@pytest.fixture
def control(qapp):
    from ui.tema_qt import ControlTema
    cfg = ConfigFalsa()
    c = ControlTema(cfg, retardo_ms=15)
    c.emitidos = []
    c.cambio.connect(c.emitidos.append)
    yield c
    c._timer.stop()
    c.deleteLater()


def esperar(qapp, ms=80):
    from PyQt6.QtTest import QTest
    QTest.qWait(ms)


def test_arranca_con_lo_guardado_y_el_cian_es_null(control):
    assert control.actual() == tema.DEFECTO
    assert control.css_json() == "null"
    assert control.estado()["identidad"] is True and control.estado()["css"] is None
    assert [p["id"] for p in control.estado()["presets"]] == list(tema.PRESETS)
    from ui.tema_qt import ControlTema
    otro = ControlTema(ConfigFalsa({"preset": "violeta"}))
    assert otro.actual()["preset"] == "violeta"
    assert json.loads(otro.css_json())["--cyan-500"] == tema.paleta("violeta")["cyan-500"]


def test_previsualizar_no_escribe_y_descartar_vuelve(qapp, control):
    cfg = control.config
    r = control.previsualizar({"preset": "magenta_mate"})
    assert r["preset"] == "magenta_mate" and control.previsualizando
    assert len(control.emitidos) == 1 and json.loads(control.emitidos[0])["--cyan-500"] == "#FE00FF"
    control.previsualizar('{"preset": "magenta_mate"}')                # igual: no reemite
    assert len(control.emitidos) == 1
    control.previsualizar({"hue": 200})                                # tono sin preset → personalizado
    assert control.actual()["preset"] == tema.PERSONALIZADO and control.actual()["hue"] == 200
    esperar(qapp)
    assert cfg.escrituras == [] and control.guardado() == tema.DEFECTO
    assert control.descartar_vista() == tema.DEFECTO
    assert control.emitidos[-1] == "null" and not control.previsualizando


def test_guardado_diferido_escribe_una_vez(qapp, control):
    cfg = control.config
    control.guardar({"preset": "violeta"})
    control.guardar({"saturacion": 1.5})
    control.guardar({"tenir_pop": True})
    assert cfg.escrituras == [] and control.pendiente
    esperar(qapp)
    assert len(cfg.escrituras) == 1
    assert cfg.escrituras[0] == {"preset": "violeta", "hue": round(tema.PRESETS["violeta"] * 360, 2),
                                 "saturacion": 1.5, "tenir_pop": True, "tenir_fondo": False}
    assert not control.pendiente
    control.guardar({"tenir_pop": True})                               # lo mismo: no escribe
    esperar(qapp)
    assert len(cfg.escrituras) == 1
    # La vista previa se guarda con guardar() sin argumentos
    control.previsualizar({"preset": "ambar"})
    control.guardar()
    esperar(qapp)
    assert cfg.escrituras[-1]["preset"] == "ambar" and len(cfg.escrituras) == 2


def test_quien_escucha_cambio_ya_ve_lo_guardado(qapp, control):
    """El panel nativo lee guardado() dentro del aviso `cambio`: tiene que ver ya
    el tema nuevo, no el anterior."""
    vistos = []
    control.cambio.connect(lambda _css: vistos.append(control.guardado()["preset"]))
    control.guardar({"preset": "magenta_mate"})
    assert vistos == ["magenta_mate"]


def test_presets_restablecer_y_entradas_raras(qapp, control):
    control.guardar({"saturacion": 0.5, "tenir_fondo": True})
    r = control.aplicar_preset("rojo_neon")
    assert r["preset"] == "rojo_neon" and r["saturacion"] == 0.5 and r["tenir_fondo"] is True
    assert control.aplicar_preset("no-existe") == r
    assert control.previsualizar("x" * 5000) == r, "JSON gigante: se ignora"
    assert control.previsualizar("{roto") == r
    assert control.previsualizar(["no", "es", "dict"]) == r
    assert control.previsualizar({"desconocida": 1}) == r
    assert control.restablecer() == tema.DEFECTO
    assert control.css_json() == "null" and control.emitidos[-1] == "null"
    control.detener()                                                  # escribe ya lo pendiente
    assert control.config.escrituras[-1] == tema.DEFECTO
    assert len(control.config.escrituras) == 1


def test_la_asistente_recibe_el_tema(control):
    m = AsistenteFalsa()
    control.set_asistente(m)
    assert m.temas == ["null"], "al engancharse, el tema actual"
    control.previsualizar({"preset": "violeta"})
    assert len(m.temas) == 2 and json.loads(m.temas[-1]) == json.loads(control.css_json())
    control.previsualizar({"preset": "violeta"})
    assert len(m.temas) == 2, "sin cambio no se reenvía"

    class Destruida:
        def aplicar_tema(self, css):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    control.set_asistente(Destruida())
    assert control._asistente is None
    control.set_asistente(object())                                     # sin aplicar_tema: se ignora
    control.previsualizar({"preset": "cian"})
    control.set_asistente(None)


def test_recargar_lee_lo_que_escribio_otro(control):
    cfg = control.config
    cfg.config["tema"] = {"preset": "verde_acido", "tenir_pop": "true"}
    r = control.recargar()
    assert r["preset"] == "verde_acido" and r["tenir_pop"] is True
    assert cfg.recargas == 1 and control.emitidos[-1] == control.css_json() != "null"
    assert not control.previsualizando


def test_con_config_real_en_carpeta_temporal(qapp, tmp_path):
    from nucleo.config import Config
    from ui.tema_qt import ControlTema, escribir_claves
    ruta = tmp_path / "config.json"
    cfg = Config(str(ruta))
    c = ControlTema(cfg, retardo_ms=5)
    c.guardar({"preset": "magenta_mate", "tenir_pop": True})
    esperar(qapp, 60)
    disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert disco["tema"]["preset"] == "magenta_mate" and disco["tema"]["tenir_pop"] is True
    assert disco["avatar"] == Config.DEFAULT_CONFIG["avatar"], "el resto no se toca"
    assert escribir_claves(cfg, {("juego", "fps"): 5, ("menu", "volumen"): 0.3})
    disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert disco["juego"]["fps"] == 5 and disco["menu"]["volumen"] == 0.3
    assert not escribir_claves(None, {("a", "b"): 1}) and not escribir_claves(cfg, {})
    c.detener()


def test_escribir_claves_con_set_por_clave():
    from ui.tema_qt import escribir_claves

    class SoloSet:
        def __init__(self):
            self.puestos = []

        def set(self, s, k, v):
            self.puestos.append((s, k, v))

    c = SoloSet()
    assert escribir_claves(c, {("tema", "preset"): "ambar", ("tema", "hue"): 10})
    assert c.puestos == [("tema", "preset", "ambar"), ("tema", "hue", 10)]


# ── QSS y colores del radial ───────────────────────────────────────────────────

def test_qss_y_radial_salen_de_la_paleta(control):
    from ui import tema_qss
    base = tema_qss.qss_menu(tema.paleta(None))
    assert "QMenu" in base and "#0091AB" in base and "#0F1424" in base          # cyan-700 y tinta-800
    assert "rgba(0, 229, 255, 41)" in base                                      # selección: cian al 16 %
    assert base == tema_qss.qss_menu(None) == control.qss_menu()
    rad = control.colores_radial()
    assert rad["acento"] == "#00E5FF" and rad["fondo"] == "#0B0F1E" and rad["pop"] == "#FFE000"
    assert set(rad) == {"acento", "acento_claro", "acento_oscuro", "secundario", "fondo", "fondo_borde",
                        "texto", "texto_tenue", "deshabilitado", "pop"}
    control.previsualizar({"preset": "magenta_mate"})
    pal = tema.paleta("magenta_mate")
    q = control.qss_menu()
    assert pal["cyan-700"] in q and "#0091AB" not in q
    assert control.colores_radial()["acento"] == pal["cyan-500"]
    assert control.colores_radial()["fondo"] == "#0B0F1E", "los fondos solo con tenir_fondo"
    assert control.colores_radial()["texto"] == rad["texto"]
    # Paleta parcial o con basura: se completa con la base
    assert tema_qss.colores_radial({"cyan-500": "no"})["acento"] == "#00E5FF"
