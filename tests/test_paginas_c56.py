"""
Páginas de la mascota en los cortes 5 y 6 (companion.html y companion_vrm.html):

- enlazan grande.css, alarma.css y baile.css tras burbuja.css, y cargan lune_ritmo.js,
  lune_alarma.js y lune_pantalla.js después de tema.js y antes de su código;
- los módulos nuevos (pantalla grande y baile) son OPCIONALES: import() con .catch;
  three-vrm se pide con import() tolerante (si falta el colisionador, la página sigue);
- todo lo que llama ui/companion.py existe en las dos páginas (`window.x =`);
- los CSS nuevos no llevan literales de la paleta (cian, azul…) fuera de los respaldos
  y cada var(--x-rgb, r g b) lleva los números del token (el tema los recolorea);
- la burbuja de alarma es #FF4826 (--lune-alarma), 16 px y max-width min(600px, 92vw);
  en la animada el vídeo no se estira más allá de 1280 px de alto;
- los módulos JS no importan three (llega por ctx) y se cargan en Node.
El comportamiento se prueba en tests/js/{grande,baile_proc,anim_grande,anim_baile,
alarma,pantalla,ritmo}.test.mjs.
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
CSS = ("grande.css", "alarma.css", "baile.css")
CLASICOS = ("lune_ritmo.js", "lune_alarma.js", "lune_pantalla.js")
MODULOS = {
    "companion_vrm.html": ("./vrm/lune_grande.js", "./vrm/lune_baile_proc.js"),
    "companion.html": ("./anim/lune_anim_grande.js", "./anim/lune_anim_baile.js"),
}


def _html(pagina):
    return (UI / pagina).read_text(encoding="utf-8")


@pytest.mark.parametrize("pagina", PAGINAS)
def test_css_y_scripts_en_orden(pagina):
    html = _html(pagina)
    i_burbuja = html.index('href="css/burbuja.css"')
    for css in CSS:
        assert (UI / "css" / css).is_file(), css
        assert html.index(f'href="css/{css}"') > i_burbuja, f"{css} tras burbuja.css"
    i_tema = html.index('<script src="tema.js"></script>')
    codigo = min(i for i in (html.find("<script>"), html.find('<script type="module">')) if i >= 0)
    anterior = i_tema
    for js in CLASICOS:
        assert (UI / js).is_file(), js
        i = html.index(f'<script src="{js}"></script>')
        assert anterior < i < codigo, f"{js}: tras tema.js y antes del código de la página"
        anterior = i


@pytest.mark.parametrize("pagina", PAGINAS)
def test_modulos_opcionales(pagina):
    html = _html(pagina)
    for ruta in MODULOS[pagina]:
        assert (UI / ruta[2:]).is_file(), ruta
        assert f"import('{ruta}').catch(" in html, f"{ruta}: import() tolerante"
        assert f"from '{ruta}'" not in html, f"{ruta} no puede ser un import estático"


def test_vrm_importa_three_vrm_con_import_tolerante():
    html = _html("companion_vrm.html")
    assert "import('@pixiv/three-vrm').catch(" in html, "tolerante (Node y versiones sin colisionador)"
    assert "from '@pixiv/three-vrm'" not in html
    assert not re.search(r"import\s*\{[^}]*VRMSpringBoneCollider", html)
    assert "VRMLib.VRMSpringBoneCollider" in html and "VRMLib.VRMSpringBoneColliderShapeSphere" in html


@pytest.mark.parametrize("pagina", PAGINAS)
def test_todo_lo_que_llama_python_existe(pagina):
    html = _html(pagina)
    src = (RAIZ / "ui" / "companion.py").read_text(encoding="utf-8")
    nuevas = {"luneGrande", "luneHold", "luneSalvapantallas", "luneAlarma", "luneBailar", "lunePulso"}
    llamadas = set(re.findall(r"window\.(lune\w+)\b", src))
    assert nuevas <= llamadas, "companion.py las llama"
    # (en la animada, luneDrag/luneTouch/luneSleep y setEmocion los publica un módulo
    # JS: lo comprueba en ejecución tests/js/integracion_vrm.test.mjs)
    for fn in sorted(llamadas if pagina == "companion_vrm.html" else nuevas):
        assert f"window.{fn} =" in html, f"{pagina} no define window.{fn}"
    # lo pedido antes de cargar el módulo se guarda y se repite
    assert "window.__luneOcioPendiente = {};" in html and "window.__luneOcioPendiente = null;" in html


def test_la_animada_sigue_con_dos_scripts_en_linea_y_su_clase():
    html = _html("companion.html")
    en_linea = [m for m in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html)
                if "src=" not in m[0] and m[1].strip()]
    assert len(en_linea) == 2
    assert '<body class="lune-animada">' in html


# ── CSS ─────────────────────────────────────────────────────────────────────────
RGB_TOKEN = {tuple(tema.canales(hx)): tok for tok, hx in tema.BASE.items()}
_VAR_HEX = re.compile(r"var\(--[\w-]+\s*,\s*#[0-9A-Fa-f]{3,8}\s*\)")
_HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_LITERAL = re.compile(r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})")


def _hex6(h):
    return "".join(c * 2 for c in h) if len(h) == 3 else h


@pytest.mark.parametrize("nombre", CSS)
def test_css_sin_literales_de_la_paleta(nombre):
    texto = (UI / "css" / nombre).read_text(encoding="utf-8")
    sin_respaldos = _VAR_HEX.sub("", texto)
    tokens_hex = {hx[1:].upper() for hx in tema.BASE.values()}
    sueltos = [h for h in _HEX.findall(sin_respaldos) if _hex6(h).upper() in tokens_hex]
    assert not sueltos, f"hex de la paleta sueltos en {nombre}: {sueltos}"
    sin_canales = re.sub(r"var\(--[\w-]+-rgb\s*,\s*\d{1,3} \d{1,3} \d{1,3}\s*\)", "", texto)
    literales = [m for m in _LITERAL.findall(sin_canales) if tuple(map(int, m)) in RGB_TOKEN]
    assert not literales, f"rgb/rgba de la paleta en {nombre}: {literales}"
    for tok, resto in re.findall(r"var\(--([a-z]+-\d+)-rgb([^)]*)\)", texto):
        m = re.fullmatch(r"\s*,\s*(\d{1,3}) (\d{1,3}) (\d{1,3})\s*", resto)
        assert m, f"var(--{tok}-rgb{resto}) sin respaldo en {nombre}"
        assert tuple(map(int, m.groups())) == tema.canales(tema.BASE[tok]), f"--{tok}-rgb en {nombre}"


def test_alarma_css_de_mate_engine():
    css = (UI / "css" / "alarma.css").read_text(encoding="utf-8")
    assert "--lune-alarma: #FF4826;" in css and "--lune-alarma-rgb: 255 72 38;" in css
    assert "max-width: min(600px, 92vw);" in css
    assert re.search(r"font:\s*600 16px", css)
    assert "body.lune-grande .lune-alarma" in css


def test_grande_css_no_estira_el_video():
    css = (UI / "css" / "grande.css").read_text(encoding="utf-8")
    bloque = css[css.index("body.lune-animada.lune-grande #stage"):]
    bloque = bloque[:bloque.index("}")]
    assert "min(100vh, 1280px)" in bloque and "0.5625" in bloque
    assert "body.lune-salva-fondo" in css and ".lune-reloj" in css


# ── Módulos JS ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ruta", ["vrm/lune_grande.js", "vrm/lune_baile_proc.js",
                                  "anim/lune_anim_grande.js", "anim/lune_anim_baile.js"])
def test_modulos_sin_three(ruta):
    src = (UI / ruta).read_text(encoding="utf-8")
    imports = re.findall(r"^import .* from '([^']+)';", src, re.MULTILINE)
    assert imports, ruta
    assert all(i.startswith("./") for i in imports), f"{ruta}: {imports} (three llega por ctx)"
    assert "export function instalar(" in src
