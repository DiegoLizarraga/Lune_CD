"""
Páginas de la asistente en los cortes 9 y 10 (companion.html y companion_vrm.html):

- CSP: connect-src 'self' blob: data: (fetch/XHR solo al servidor local de la asistente);
- lune_mmd_audio.js (script clásico) tras lune_pantalla.js y antes del código de la página;
- la VRM: importmap con @pixiv/three-vrm-animation (el archivo vendorizado existe) y el
  reproductor (lune_mmd.js, lune_vmd.js, three-vrm-animation, GLTFLoader) con import()
  TOLERANTE, nunca estático, registrado la primera vez que se pide un baile;
- la animada: anim/lune_anim_mmd.js opcional y registrado al usarse; sigue con dos scripts
  en línea;
- window.luneMMD existe ANTES del módulo (guarda el último cargar y sus banderas en
  __luneOcioPendiente.mmd) y después, en las dos;
- lune_anim_mmd.js no importa three, exporta instalar y no usa innerHTML.
El comportamiento se prueba en tests/js/pagina_mmd.test.mjs y tests/js/anim_mmd.test.mjs.
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

UI = RAIZ / "ui_web"
PAGINAS = ("companion.html", "companion_vrm.html")
CSP = """<meta http-equiv="Content-Security-Policy" content="connect-src 'self' blob: data:" />"""


def _html(pagina):
    return (UI / pagina).read_text(encoding="utf-8")


def _en_linea(html):
    return [m for m in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html)
            if "src=" not in m[0] and "importmap" not in m[0] and m[1].strip()]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_csp_en_la_cabecera(pagina):
    html = _html(pagina)
    assert html.count(CSP) == 1
    assert html.index(CSP) < html.index("<title>") < html.index("</head>")


@pytest.mark.parametrize("pagina", PAGINAS)
def test_lune_mmd_audio_antes_del_codigo(pagina):
    html = _html(pagina)
    assert (UI / "lune_mmd_audio.js").is_file()
    i = html.index('<script src="lune_mmd_audio.js"></script>')
    assert html.index('<script src="lune_pantalla.js"></script>') < i
    codigo = min(x for x in (html.find("<script>"), html.find('<script type="module">')) if x >= 0)
    assert i < codigo


def test_importmap_de_la_vrm_con_three_vrm_animation():
    html = _html("companion_vrm.html")
    m = re.search(r'<script type="importmap">([\s\S]*?)</script>', html)
    mapa = json.loads(m.group(1))["imports"]
    ruta = mapa["@pixiv/three-vrm-animation"]
    assert ruta == "./vendor/three/three-vrm-animation.module.min.js"
    assert (UI / ruta[2:]).is_file()
    assert html.index('<script type="importmap">') < html.index('<script type="module">')


def test_reproductor_de_la_vrm_opcional_y_perezoso():
    html = _html("companion_vrm.html")
    modulo = [c for a, c in _en_linea(html) if 'type="module"' in a][0]
    for esp in ("./vrm/lune_mmd.js", "./vrm/lune_vmd.js", "@pixiv/three-vrm-animation", "three/addons/loaders/GLTFLoader.js"):
        assert f"import('{esp}').catch(" in modulo, f"{esp}: import() tolerante"
        assert f"from '{esp}'" not in html, f"{esp} no puede ser un import estático"
    for ruta in ("vrm/lune_mmd.js", "vrm/lune_vmd.js", "vendor/three/loaders/GLTFLoader.js"):
        assert (UI / ruta).is_file(), ruta
    # dentro de una función que solo se llama con el primer «cargar»
    i_imp = modulo.index("import('./vrm/lune_mmd.js')")
    assert modulo.rfind("function importarMMD()", 0, i_imp) >= 0
    assert "LuneMMDAudio" in modulo and "api.orden(" in modulo


def test_reproductor_de_la_animada_opcional():
    html = _html("companion.html")
    assert (UI / "anim" / "lune_anim_mmd.js").is_file()
    assert "import('./anim/lune_anim_mmd.js').catch(" in html
    assert "from './anim/lune_anim_mmd.js'" not in html
    assert len(_en_linea(html)) == 2, "la animada sigue con dos scripts en línea"
    modulo = _en_linea(html)[1][1]
    assert "function moduloMMD()" in modulo and "window.luneBailar(" in modulo and "window.lunePulso(" in modulo


@pytest.mark.parametrize("pagina", PAGINAS)
def test_lune_mmd_antes_y_despues_del_modulo(pagina):
    html = _html(pagina)
    src = (RAIZ / "ui" / "companion.py").read_text(encoding="utf-8")
    assert "window.luneMMD" in src, "companion.py la llama"
    clasico, modulo = [c for _, c in _en_linea(html)][:2]
    assert "window.luneMMD = function" in clasico
    assert "p.mmd || (p.mmd = { cargar: null, banderas: [] })" in clasico, "guarda el último cargar y sus banderas"
    assert "window.luneMMD = (" in modulo
    assert "ocioPendiente.mmd" in modulo, "lo pedido antes se repite"
    for fn in ("luneMMD", "luneGrande", "luneBailar", "lunePulso", "luneSentar", "luneComer"):
        assert f"window.{fn} =" in html


def test_todo_lo_que_llama_companion_existe_en_la_vrm():
    """(como test_paginas_c56: en la VRM, todas las window.lune* que llama companion.py)"""
    html = _html("companion_vrm.html")
    src = (RAIZ / "ui" / "companion.py").read_text(encoding="utf-8")
    for fn in sorted(set(re.findall(r"window\.(lune\w+)\b", src))):
        assert f"window.{fn} =" in html, fn


def test_lune_anim_mmd_sin_three_ni_innerhtml():
    src = (UI / "anim" / "lune_anim_mmd.js").read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from '([^']+)';", src, re.MULTILINE)
    assert imports and all(i.startswith("./") for i in imports), imports
    assert "export function instalar(" in src and "export function orden(" in src
    assert "innerHTML" not in src
    assert "style." not in src, "el registro es el dueño de los estilos"
