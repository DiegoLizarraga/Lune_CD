"""
Páginas de la mascota en los cortes 7 y 8 (companion.html y companion_vrm.html):

- los módulos nuevos (sentarse y comida) son OPCIONALES: import() con .catch, nunca un
  import estático, y se registran la primera vez que se usan;
- las funciones que llama ui/companion.py (luneSentar, luneSeatPx, luneComer,
  luneComidaActiva) existen en las dos páginas ANTES del módulo (lo pedido se guarda en
  __luneVidaPendiente y se repite) y después;
- la animada enlaza css/sentarse.css tras burbuja.css y sigue con dos scripts en línea;
  el CSS solo usa tokens (--x-rgb con el respaldo del token);
- los módulos JS no importan three (llega por ctx) y exportan instalar.
El comportamiento se prueba en tests/js/{sentarse,comida_vrm,anim_sentarse,anim_comida}.test.mjs.
"""
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import tema  # noqa: E402

UI = RAIZ / "ui_web"
PAGINAS = ("companion.html", "companion_vrm.html")
MODULOS = {
    "companion_vrm.html": ("./vrm/lune_sentarse.js", "./vrm/lune_comida.js"),
    "companion.html": ("./anim/lune_anim_sentarse.js", "./anim/lune_anim_comida.js"),
}
NUEVAS = ("luneSentar", "luneSeatPx", "luneComer", "luneComidaActiva")


def _html(pagina):
    return (UI / pagina).read_text(encoding="utf-8")


def _en_linea(html):
    return [m for m in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html)
            if "src=" not in m[0] and "importmap" not in m[0] and m[1].strip()]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_modulos_opcionales_y_perezosos(pagina):
    html = _html(pagina)
    for ruta in MODULOS[pagina]:
        assert (UI / ruta[2:]).is_file(), ruta
        assert f"import('{ruta}').catch(" in html, f"{ruta}: import() tolerante"
        assert f"from '{ruta}'" not in html, f"{ruta} no puede ser un import estático"
    modulo = [c for a, c in _en_linea(html) if 'type="module"' in a][0]
    assert "function moduloSentarse()" in modulo and "function moduloComida()" in modulo, "se registran al usarse"


@pytest.mark.parametrize("pagina", PAGINAS)
def test_lo_que_llama_python_existe_antes_y_despues_del_modulo(pagina):
    html = _html(pagina)
    src = (RAIZ / "ui" / "companion.py").read_text(encoding="utf-8")
    llamadas = set(re.findall(r"window\.(lune\w+)\b", src))
    assert set(NUEVAS) <= llamadas, "companion.py las llama"
    assert "luneCabeza" in llamadas
    clasico, modulo = [c for _, c in _en_linea(html)][:2]
    for fn in NUEVAS:
        assert f"window.{fn} = function" in clasico, f"{pagina}: {fn} antes del módulo"
        assert f"window.{fn} = (" in modulo, f"{pagina}: {fn} en el módulo"
    assert "window.__luneVidaPendiente = {};" in clasico
    assert "window.__luneVidaPendiente = null;" in modulo
    assert "window.luneCabeza = " in html


def test_la_animada_enlaza_sentarse_css_y_sigue_con_dos_scripts():
    html = _html("companion.html")
    assert len(_en_linea(html)) == 2
    assert html.index('href="css/sentarse.css"') > html.index('href="css/burbuja.css"')
    assert (UI / "css" / "sentarse.css").is_file()
    assert '<body class="lune-animada">' in html
    css = (UI / "css" / "sentarse.css").read_text(encoding="utf-8")
    assert "#stage.lune-sentada" in css and "border-bottom-color: transparent" in css


# ── CSS con tokens (mismo criterio que test_paginas_c56) ──────────────────────
RGB_TOKEN = {tuple(tema.canales(hx)): tok for tok, hx in tema.BASE.items()}
_VAR_HEX = re.compile(r"var\(--[\w-]+\s*,\s*#[0-9A-Fa-f]{3,8}\s*\)")
_HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_LITERAL = re.compile(r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})")


def _hex6(h):
    return "".join(c * 2 for c in h) if len(h) == 3 else h


def test_sentarse_css_sin_literales_de_la_paleta():
    texto = (UI / "css" / "sentarse.css").read_text(encoding="utf-8")
    # (sin el comentario de cabecera: allí no hay colores, pero «#stage» no es un hex)
    cuerpo = re.sub(r"/\*[\s\S]*?\*/", "", texto)
    sin_respaldos = _VAR_HEX.sub("", cuerpo)
    tokens_hex = {hx[1:].upper() for hx in tema.BASE.values()}
    sueltos = [h for h in _HEX.findall(sin_respaldos) if _hex6(h).upper() in tokens_hex]
    assert not sueltos, f"hex de la paleta sueltos: {sueltos}"
    sin_canales = re.sub(r"var\(--[\w-]+-rgb\s*,\s*\d{1,3} \d{1,3} \d{1,3}\s*\)", "", cuerpo)
    literales = [m for m in _LITERAL.findall(sin_canales) if tuple(map(int, m)) in RGB_TOKEN]
    assert not literales, f"rgb/rgba de la paleta: {literales}"
    usados = re.findall(r"var\(--([a-z]+-\d+)-rgb([^)]*)\)", cuerpo)
    assert usados, "la sombra usa los canales del tema"
    for tok, resto in usados:
        m = re.fullmatch(r"\s*,\s*(\d{1,3}) (\d{1,3}) (\d{1,3})\s*", resto)
        assert m, f"var(--{tok}-rgb{resto}) sin respaldo"
        assert tuple(map(int, m.groups())) == tema.canales(tema.BASE[tok]), f"--{tok}-rgb"


# ── Módulos JS ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ruta", ["vrm/lune_sentarse.js", "vrm/lune_comida.js",
                                  "anim/lune_anim_sentarse.js", "anim/lune_anim_comida.js"])
def test_modulos_sin_three(ruta):
    src = (UI / ruta).read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from '([^']+)';", src, re.MULTILINE)
    assert all(i.startswith("./") for i in imports), f"{ruta}: {imports} (three llega por ctx)"
    assert "export function instalar(" in src
    assert "innerHTML" not in src
