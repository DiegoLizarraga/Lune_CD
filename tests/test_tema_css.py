"""
Tests del tema de color en los CSS y las páginas:

- scripts/tema_canales.py: convierte los rgba() de la paleta a canales con
  respaldo, es idempotente, conserva CRLF y no deja nada por convertir en los
  archivos del tema (tokens, componentes, páginas de la mascota y _ds_bundle.js).
- En esos archivos no quedan literales cian/azul (ni amarillo/tinta de la
  paleta) salvo como respaldo de var(), y todo var(--x-rgb) lleva un respaldo
  con los MISMOS números que el token: con el tema cian se ve exactamente igual.
- Las dos páginas de la mascota cargan tema.js antes de su código y definen
  window.luneTema (respaldo) y window.luneCabeza.
- Con Node: todo lo que genera nucleo/tema.py lo acepta la lista blanca de
  ui_web/tema.js (el mapa entero, para cada preset y combinación de banderas).
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import tema  # noqa: E402

UI = RAIZ / "ui_web"


def _script():
    spec = importlib.util.spec_from_file_location("tema_canales", RAIZ / "scripts" / "tema_canales.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tc = _script()
CANALES = tc.canales_de_colores()
RGB_TOKEN = {tuple(tema.canales(hx)): tok for tok, hx in tema.BASE.items()}


# ── El script ──────────────────────────────────────────────────────────────────

def test_el_script_lee_los_tokens_de_colors_css():
    assert CANALES == RGB_TOKEN, "mismos tokens que nucleo/tema.BASE"
    assert CANALES[(0, 229, 255)] == "cyan-500" and CANALES[(30, 85, 255)] == "blue-500"


def test_convertir_pasa_la_paleta_a_canales_y_deja_lo_demas():
    texto = ("a{background:rgba(0,229,255,.10)} b{box-shadow:0 0 0 1px rgba( 30 , 85 , 255 , 0.12 )}"
             " c{color:rgb(0,229,255)} d{background:rgba(15,20,36,.86)} e{x:rgba(61,116,255,55%)}"
             " f{color:rgba(0,0,0,.5);border-color:rgba(255,255,255,.1)} g{color:rgba(255,59,92,.4)}"
             " h{color:rgba(0,229,254,.5)}")
    nuevo, n = tc.convertir(texto, CANALES)
    assert n == 5
    assert "rgb(var(--cyan-500-rgb, 0 229 255) / .10)" in nuevo         # el alfa se copia tal cual
    assert "rgb(var(--blue-500-rgb, 30 85 255) / 0.12)" in nuevo
    assert "rgb(var(--cyan-500-rgb, 0 229 255))" in nuevo                # sin alfa
    assert "rgb(var(--ink-800-rgb, 15 20 36) / .86)" in nuevo            # tinta (tenir_fondo)
    assert "rgb(var(--blue-400-rgb, 61 116 255) / 55%)" in nuevo
    for queda in ("rgba(0,0,0,.5)", "rgba(255,255,255,.1)", "rgba(255,59,92,.4)", "rgba(0,229,254,.5)"):
        assert queda in nuevo, "negros, blancos, rojos y colores casi iguales no se tocan"
    otra, n2 = tc.convertir(nuevo, CANALES)
    assert (otra, n2) == (nuevo, 0), "idempotente"


def test_el_script_conserva_crlf_y_comprueba(tmp_path):
    f = tmp_path / "x.css"
    f.write_bytes(b"a{color:rgba(0,229,255,.5)}\r\nb{color:#fff}\r\n")
    assert tc.main(["--comprobar", str(f)]) == 1
    assert f.read_bytes() == b"a{color:rgba(0,229,255,.5)}\r\nb{color:#fff}\r\n", "--comprobar no escribe"
    assert tc.main([str(f)]) == 0
    assert f.read_bytes() == b"a{color:rgb(var(--cyan-500-rgb, 0 229 255) / .5)}\r\nb{color:#fff}\r\n"
    assert tc.main(["--comprobar", str(f)]) == 0
    antes = f.read_bytes()
    assert tc.main([str(f)]) == 0 and f.read_bytes() == antes


def test_los_archivos_del_tema_ya_estan_convertidos():
    archivos = tc.archivos_por_defecto()
    nombres = {p.relative_to(UI).as_posix() for p in archivos}
    assert {"tokens/base.css", "tokens/effects.css", "companion.html", "companion_vrm.html",
            "_ds_bundle.js", "components/core/Button.jsx", "components/feedback/StatusPill.jsx",
            "components/navigation/ProviderTab.jsx"} <= nombres
    assert "ui_kits/lune-desktop/index.html" not in nombres, "index.html es de otra tarjeta del corte"
    pendientes = {p.name: n for p, n in tc.procesar(archivos, CANALES, escribir=False).items() if n}
    assert not pendientes, f"quedan literales sin convertir: {pendientes}"


# ── Los archivos del tema ──────────────────────────────────────────────────────

_VAR_HEX = re.compile(r"var\(--[\w-]+\s*,\s*#[0-9A-Fa-f]{3,8}\s*\)")
_HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_LITERAL = re.compile(r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})")


def _hex6(h):
    return "".join(c * 2 for c in h) if len(h) == 3 else h


@pytest.mark.parametrize("ruta", tc.archivos_por_defecto(), ids=lambda p: p.relative_to(UI).as_posix())
def test_sin_literales_de_la_paleta_fuera_de_los_respaldos(ruta):
    texto = ruta.read_text(encoding="utf-8")
    # Los var(--x, #hex) son respaldos: con styles.css cargado no se usan.
    sin_respaldos = _VAR_HEX.sub("", texto)
    tokens_hex = {hx[1:].upper() for hx in tema.BASE.values()}
    sueltos = [h for h in _HEX.findall(sin_respaldos) if _hex6(h).upper() in tokens_hex]
    assert not sueltos, f"hex de la paleta sueltos en {ruta.name}: {sueltos}"
    # rgb()/rgba() con números de la paleta: solo dentro de var(--x-rgb, r g b)
    sin_canales = re.sub(r"var\(--[\w-]+-rgb\s*,\s*\d{1,3} \d{1,3} \d{1,3}\s*\)", "", texto)
    literales = [m for m in _LITERAL.findall(sin_canales) if tuple(map(int, m)) in RGB_TOKEN]
    assert not literales, f"rgb/rgba de la paleta en {ruta.name}: {literales}"


@pytest.mark.parametrize("ruta", tc.archivos_por_defecto(), ids=lambda p: p.relative_to(UI).as_posix())
def test_todo_canal_lleva_el_respaldo_del_token(ruta):
    """Con el tema cian se ve igual: el respaldo de var(--x-rgb, …) son los números
    de --x en colors.css (y colors.css define esos canales con los mismos)."""
    texto = ruta.read_text(encoding="utf-8")
    usos = re.findall(r"var\(--([a-z]+-\d+)-rgb([^)]*)\)", texto)
    for nombre, resto in usos:
        m = re.fullmatch(r"\s*,\s*(\d{1,3}) (\d{1,3}) (\d{1,3})\s*", resto)
        assert m, f"var(--{nombre}-rgb{resto}) sin respaldo «r g b» en {ruta.name}"
        assert nombre in tema.BASE, nombre
        assert tuple(map(int, m.groups())) == tema.canales(tema.BASE[nombre]), f"--{nombre}-rgb en {ruta.name}"


def test_el_bundle_y_sus_componentes_dicen_lo_mismo():
    """_ds_bundle.js lleva el CSS compilado de components/: tras el script, los
    mismos canales en los dos sitios (se editan juntos, el bundle solo por script)."""
    bundle = (UI / "_ds_bundle.js").read_text(encoding="utf-8")
    for jsx in ("components/core/Button.jsx", "components/feedback/StatusPill.jsx",
                "components/navigation/ProviderTab.jsx"):
        fuente = (UI / jsx).read_text(encoding="utf-8")
        for regla in re.findall(r"[^\n{}]*rgb\(var\(--[^\n]*", fuente):
            assert regla.strip() in bundle, (jsx, regla.strip())


# ── Las páginas de la mascota ──────────────────────────────────────────────────

@pytest.mark.parametrize("pagina", ["companion.html", "companion_vrm.html"])
def test_las_paginas_cargan_tema_js_y_exponen_la_api(pagina):
    html = (UI / pagina).read_text(encoding="utf-8")
    assert '<script src="tema.js"></script>' in html
    primer_codigo = min(i for i in (html.find("<script>"), html.find('<script type="module">')) if i >= 0)
    assert html.index('<script src="tema.js"></script>') < primer_codigo, "tema.js antes del código de la página"
    assert "window.luneTema =" in html, "respaldo mudo si tema.js no carga (y companion.py lo llama)"
    assert "window.luneCabeza =" in html
    assert (UI / "tema.js").is_file()


def test_la_animada_sigue_con_dos_scripts_en_linea():
    """tests/js/integracion_vrm.test.mjs cuenta los <script> en línea de companion.html."""
    html = (UI / "companion.html").read_text(encoding="utf-8")
    en_linea = [m for m in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html)
                if "src=" not in m[0] and m[1].strip()]
    assert len(en_linea) == 2


# ── Python ↔ tema.js ───────────────────────────────────────────────────────────

def test_tema_js_acepta_todo_lo_que_genera_python(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    casos = []
    for preset in tema.PRESETS:
        for pop in (False, True):
            for fondo in (False, True):
                cfg = {"preset": preset, "tenir_pop": pop, "tenir_fondo": fondo}
                casos.append(tema.css_json(cfg))
    casos.append(tema.css_json({"preset": "personalizado", "hue": 200, "saturacion": 0.4,
                                "tenir_pop": True, "tenir_fondo": True}))
    (tmp_path / "casos.json").write_text(json.dumps(casos), encoding="utf-8")
    prog = tmp_path / "probar.cjs"
    prog.write_text(
        "const fs = require('fs'), vm = require('vm');\n"
        f"const codigo = fs.readFileSync({json.dumps(str(UI / 'tema.js'))}, 'utf8');\n"
        "const casos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));\n"
        "const res = casos.map((texto) => {\n"
        "  const props = new Map();\n"
        "  const ctx = { document: { documentElement: { style: {\n"
        "    setProperty: (k, v) => props.set(k, v), removeProperty: (k) => props.delete(k) } } } };\n"
        "  ctx.window = ctx; vm.createContext(ctx); vm.runInContext(codigo, ctx);\n"
        "  const n = ctx.luneTema(texto);\n"
        "  return { n, props: Object.fromEntries(props) };\n"
        "});\n"
        "process.stdout.write(JSON.stringify(res));\n", encoding="utf-8")
    r = subprocess.run([node, str(prog), str(tmp_path / "casos.json")], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    for texto, res in zip(casos, json.loads(r.stdout)):
        esperado = json.loads(texto)
        if esperado is None:
            assert res == {"n": 0, "props": {}}
        else:
            assert res["n"] == len(esperado) and res["props"] == esperado
