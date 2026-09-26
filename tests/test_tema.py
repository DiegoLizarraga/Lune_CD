"""
Tests de nucleo/tema.py (la fórmula ThemeManager.Adjust de Mate-Engine sobre los
tokens de Lune) y de ui.theme.aplicar_tema (la paleta en la interfaz nativa).

Sin Qt ni disco: la fórmula se comprueba con colores conocidos (rojo → verde al
girar 1/3), sus propiedades (da la vuelta, conserva V y alfa, limita la
saturación) y la identidad del tema cian (nada cambia en ningún sitio).
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import tema  # noqa: E402

COLORES = RAIZ / "ui_web" / "tokens" / "colors.css"
NOMBRE_JS = re.compile(r"^--(?:cyan|blue|yellow|ink)-\d{2,3}(?:-rgb)?$")    # lista blanca de tema.js


def _tokens_css():
    css = COLORES.read_text(encoding="utf-8")
    return {n: "#" + h.upper() for n, h in re.findall(r"--((?:cyan|blue|yellow|ink)-\d+):\s*#([0-9A-Fa-f]{6})\b", css)}


# ── Base e identidad ───────────────────────────────────────────────────────────

def test_base_es_copia_de_colors_css():
    assert tema.BASE == _tokens_css()
    assert set(tema.GRUPOS["senal"]) == {t for t in tema.BASE if t.startswith(("cyan-", "blue-"))}
    assert len(tema.GRUPOS["senal"]) == 10 and len(tema.GRUPOS["pop"]) == 4 and len(tema.GRUPOS["fondo"]) == 9


@pytest.mark.parametrize("cfg", [
    None, {}, dict(tema.DEFECTO), "cian", {"preset": "cian", "tenir_pop": True, "tenir_fondo": True},
    {"preset": "personalizado", "hue": 0, "saturacion": 1}, {"preset": "personalizado", "hue": 360},
    {"tema": dict(tema.DEFECTO), "avatar": {}},              # el config.json entero
])
def test_el_tema_cian_es_la_identidad(cfg):
    assert tema.es_identidad(cfg)
    assert tema.paleta(cfg) == tema.BASE
    assert tema.css_json(cfg) == "null"
    assert tema.variables_css(tema.paleta(cfg)) == {}


def test_la_formula_sin_atajo_tambien_deja_la_base_igual():
    """Aunque ajustar() no pasa por HSV con tono 0 y saturación 1, la ida y vuelta
    RGB→HSV→RGB de la fórmula tampoco movería ningún token (redondeo incluido)."""
    for hx in tema.BASE.values():
        casi = tema.ajustar(hx, 1e-12 + 1.0, 1.0)            # una vuelta entera
        assert casi == hx
        vuelta = tema.ajustar(tema.ajustar(hx, 0.5, 1.0), 0.5, 1.0)
        assert all(abs(a - b) <= 1 for a, b in zip(tema.canales(vuelta), tema.canales(hx))), (hx, vuelta)


# ── La fórmula de Mate-Engine ──────────────────────────────────────────────────

def test_ajustar_rota_el_tono_como_mate_engine():
    assert tema.ajustar("#FF0000", 1 / 3, 1.0) == "#00FF00"
    assert tema.ajustar("#FF0000", 2 / 3, 1.0) == "#0000FF"
    assert tema.ajustar("#00FFFF", 0.5, 1.0) == "#FF0000"
    assert tema.ajustar("#f00", 1 / 3, 1.0) == "#00FF00"                 # #RGB también
    # Los presets sobre el cian eléctrico de Lune
    assert tema.ajustar("#00E5FF", tema.PRESETS["magenta_mate"], 1.0) == "#FE00FF"
    assert tema.ajustar("#00E5FF", tema.PRESETS["ambar"], 1.0) == "#FFAA00"
    assert tema.ajustar("#00E5FF", tema.PRESETS["verde_acido"], 1.0) == "#01FF00"


def test_el_tono_da_la_vuelta():
    for hx in ("#00E5FF", "#1E55FF", "#7DF5FF"):
        a = tema.ajustar(hx, 0.25, 1.0)
        assert tema.ajustar(hx, 1.25, 1.0) == a
        assert tema.ajustar(hx, -0.75, 1.0) == a
    assert tema.tono({"preset": "personalizado", "hue": 450}) == pytest.approx(0.25)
    assert tema.tono({"preset": "personalizado", "hue": -90}) == pytest.approx(0.75)
    assert tema.normalizar({"preset": "personalizado", "hue": 720})["hue"] == 0.0
    assert tema.es_identidad({"preset": "personalizado", "hue": 720})


def test_la_saturacion_se_limita():
    assert tema.normalizar({"saturacion": 5})["saturacion"] == tema.SAT_MAX == 2.0
    assert tema.normalizar({"saturacion": -1})["saturacion"] == tema.SAT_MIN == 0.0
    assert tema.ajustar("#40FF40", 0.0, 2.0) == "#00FF00"                 # s·2 > 1 → 1
    assert tema.ajustar("#40FF40", 0.0, 9.0) == "#00FF00"                 # el multiplicador también se limita
    assert tema.ajustar("#00E5FF", 0.3, 0.0) == "#FFFFFF"                 # s = 0 → gris del mismo V
    assert tema.ajustar("#0091AB", 0.0, 0.0) == "#ABABAB"
    medio = tema.canales(tema.ajustar("#FF8080", 0.0, 0.5))
    assert medio[0] == 255 and medio[1] == medio[2] and medio[1] > 0x80


def test_conserva_v_y_alfa():
    for hx in tema.BASE.values():
        for t, s in ((0.316, 1.0), (0.594, 1.6), (0.8, 0.3)):
            nuevo = tema.canales(tema.ajustar(hx, t, s))
            assert abs(max(nuevo) - max(tema.canales(hx))) <= 1, (hx, t, s)
    assert tema.ajustar("#00E5FF80", 0.5, 1.0).endswith("80")
    assert len(tema.ajustar("#00E5FF80", 0.5, 1.0)) == 9
    assert tema.ajustar("#00e5ff", 0, 1) == "#00E5FF"                     # siempre en mayúsculas
    with pytest.raises(ValueError):
        tema.ajustar("rojo", 0.1, 1.0)


# ── Configuración ──────────────────────────────────────────────────────────────

class ConfigFalsa:
    """Como nucleo.config.Config: .config con las secciones."""

    def __init__(self, tema_=None):
        self.config = {"tema": dict(tema_ or {})}


class SoloGet:
    def __init__(self, datos):
        self.datos = datos

    def get(self, seccion, clave, defecto=None):
        return self.datos.get(clave, defecto) if seccion == "tema" else defecto


def test_normalizar_acepta_de_todo():
    assert tema.normalizar(None) == tema.DEFECTO
    assert tema.normalizar("violeta")["preset"] == "violeta"
    assert tema.normalizar(ConfigFalsa({"preset": "rojo_neon"}))["preset"] == "rojo_neon"
    assert tema.normalizar(SoloGet({"preset": "ambar", "tenir_pop": "sí"})) == {
        "preset": "ambar", "hue": round(tema.PRESETS["ambar"] * 360, 2), "saturacion": 1.0,
        "tenir_pop": True, "tenir_fondo": False}
    raro = tema.normalizar({"preset": "ROSA", "hue": float("nan"), "saturacion": "mucha",
                            "tenir_pop": "false", "tenir_fondo": [1]})
    assert raro == dict(tema.DEFECTO)
    assert tema.normalizar({"hue": 120})["preset"] == tema.PERSONALIZADO   # sin preset, con tono
    assert tema.normalizar({"hue": True})["preset"] == "cian"               # un bool no es un número
    # Con preset, el tono es el suyo (el hue guardado solo lo refleja en grados)
    n = tema.normalizar({"preset": "magenta_mate", "hue": 10})
    assert n["hue"] == pytest.approx(113.76) and tema.tono(n) == tema.PRESETS["magenta_mate"]
    assert tema.tono({"preset": "personalizado", "hue": 10}) == pytest.approx(10 / 360)


def test_los_presets_para_las_interfaces():
    ps = tema.presets()
    assert [p["id"] for p in ps] == list(tema.PRESETS) == [
        "cian", "magenta_mate", "violeta", "rojo_neon", "ambar", "verde_acido"]
    assert ps[0]["muestra"] == "#00E5FF" and ps[0]["etiqueta"] == "Cian"
    assert all(p["muestra"] != "#00E5FF" for p in ps[1:])
    assert tema.PRESETS == {"cian": 0.0, "magenta_mate": 0.316, "violeta": 0.233, "rojo_neon": 0.455,
                            "ambar": 0.594, "verde_acido": 0.816}


# ── Variables CSS y grupos ─────────────────────────────────────────────────────

@pytest.mark.parametrize("preset", [p for p in tema.PRESETS if p != "cian"])
def test_css_json_con_canales_iguales_al_hex(preset):
    for pop in (False, True):
        for fondo in (False, True):
            cfg = {"preset": preset, "tenir_pop": pop, "tenir_fondo": fondo}
            mapa = json.loads(tema.css_json(cfg))
            assert mapa and all(NOMBRE_JS.match(k) for k in mapa), "todo pasa la lista blanca de tema.js"
            for k, v in mapa.items():
                if k.endswith("-rgb"):
                    continue
                assert re.fullmatch(r"#[0-9A-F]{6}", v)
                assert mapa[k + "-rgb"] == " ".join(str(c) for c in tema.canales(v)), k
            senal = {k for k in mapa if not k.endswith("-rgb")}
            assert {f"--{t}" for t in tema.GRUPOS["senal"]} <= senal
            assert any(k.startswith("--yellow-") for k in senal) == pop, "el amarillo solo con tenir_pop"
            assert any(k.startswith("--ink-") for k in senal) == fondo, "los fondos solo con tenir_fondo"
            assert len(mapa) <= 46


def test_tenir_deja_el_amarillo_y_la_tinta_si_no_se_pide():
    pal = tema.paleta("magenta_mate")
    assert all(pal[t] == tema.BASE[t] for t in tema.GRUPOS["pop"] + tema.GRUPOS["fondo"])
    assert all(pal[t] != tema.BASE[t] for t in tema.GRUPOS["senal"])
    pop = tema.paleta({"preset": "magenta_mate", "tenir_pop": True})
    assert pop["yellow-500"] == tema.ajustar("#FFE000", tema.PRESETS["magenta_mate"], 1.0) != "#FFE000"
    fondo = tema.paleta({"preset": "magenta_mate", "tenir_fondo": True})
    assert fondo["ink-900"] != tema.BASE["ink-900"] and fondo["yellow-500"] == "#FFE000"


def test_ansi_truecolor():
    assert tema.ansi("#00E5FF") == "\x1b[38;2;0;229;255m"
    assert tema.ansi("#1E55FF", fondo=True) == "\x1b[48;2;30;85;255m"
    assert tema.ansi(tema.paleta("rojo_neon")["cyan-500"]) == "\x1b[38;2;255;0;43m"


# ── Interfaz nativa ────────────────────────────────────────────────────────────

def test_colores_nativos_solo_acentos():
    from ui import theme
    base = theme._COLORS_BASE
    ident = tema.colores_nativos(tema.paleta(None))
    assert set(ident) == set(tema.NATIVOS_SENAL)
    assert all(ident[k] == base[k] for k in ident), "con el cian, los mismos hex que ui/theme.COLORS"
    for claves in (tema.NATIVOS_SENAL, tema.NATIVOS_POP, tema.NATIVOS_FONDO):
        assert set(claves) <= set(base)
        assert all(base[k] == tema.BASE[t] for k, t in claves.items()), "el mapa coincide con COLORS"
    magenta = tema.colores_nativos(tema.paleta("magenta_mate"))
    assert set(magenta) == set(tema.NATIVOS_SENAL)
    assert magenta["accent"] == tema.paleta("magenta_mate")["cyan-500"]
    assert not {"text", "text_muted", "text_dim", "error"} & set(magenta)
    todo = tema.colores_nativos(tema.paleta({"preset": "violeta", "tenir_pop": True, "tenir_fondo": True}))
    assert set(todo) == set(tema.NATIVOS_SENAL) | set(tema.NATIVOS_POP) | set(tema.NATIVOS_FONDO)
    assert "text" not in todo and "error" not in todo
    assert tema.colores_nativos({}) == ident, "una paleta vacía es la base"


@pytest.fixture
def theme_limpio():
    from ui import theme
    yield theme
    theme.aplicar_tema(None)


def test_aplicar_tema_muta_colors_y_proveedores_en_sitio(theme_limpio):
    theme = theme_limpio
    colors = theme.COLORS
    antes = dict(colors)
    theme.aplicar_tema({"tema": {"preset": "magenta_mate"}})
    assert theme.COLORS is colors, "en sitio: los que importaron COLORS lo ven"
    pal = tema.paleta("magenta_mate")
    assert colors["accent"] == pal["cyan-500"] and colors["blue"] == pal["blue-500"]
    assert colors["text"] == antes["text"] and colors["error"] == antes["error"]
    assert colors["yellow"] == antes["yellow"] and colors["bg"] == antes["bg"]
    assert theme.PROVIDER_META["ollama"]["color"] == colors["cyan"]
    assert theme.PROVIDER_META["openrouter"]["dark"] == colors["blue_dark"]
    # Con fondos y vuelta al cian: todo como estaba
    theme.aplicar_tema(ConfigFalsa({"preset": "violeta", "tenir_fondo": True}))
    assert colors["bg"] != antes["bg"]
    theme.aplicar_tema(ConfigFalsa({"preset": "cian"}))
    assert colors == antes
    assert theme.PROVIDER_META["ollama"]["color"] == antes["cyan"]


def test_aplicar_tema_nunca_lanza(theme_limpio):
    theme = theme_limpio

    class Rota:
        @property
        def config(self):
            raise RuntimeError("config rota")

    antes = dict(theme.COLORS)
    theme.aplicar_tema(Rota())
    theme.aplicar_tema(42)
    assert theme.COLORS == antes
