"""
Lanza los tests de JavaScript de la interfaz web (tests/js/*.test.mjs) con el
runner de Node (`node --test`) y comprueba el contrato de tokens de color.

Los módulos JS de la asistente (bus del VRM, registro de la asistente animada, cola
de eventos, burbuja, efectos de sonido) no necesitan navegador: se prueban en
Node con DOM y audio falsos. Si Node no está instalado, el test se salta.

El contrato de tokens (tokens/colors.css) se comprueba aquí sin Node: cada canal
`--x-rgb` tiene que ser "R G B" del mismo color que `--x` en hex, porque los CSS
nuevos usan rgb(var(--x-rgb) / alfa) y el tema los redefine juntos.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_JS = RAIZ / "tests" / "js"
COLORES = RAIZ / "ui_web" / "tokens" / "colors.css"

CANALES_OBLIGATORIOS = [
    *(f"cyan-{n}" for n in (300, 400, 500, 600, 700)),
    *(f"blue-{n}" for n in (300, 400, 500, 600, 700)),
    "yellow-500",
    "ink-950",
]


def test_js_con_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado: se saltan los tests JS")
    archivos = sorted(CARPETA_JS.glob("*.test.mjs"))
    assert archivos, "no hay tests en tests/js"
    # Equivale a `node --test tests/js`, pero con la lista explícita: Node 22+
    # trata los argumentos como patrones y no acepta una carpeta. Rutas relativas
    # a la raíz en formato POSIX. Reporter TAP para tener un resumen estable.
    rutas = [p.relative_to(RAIZ).as_posix() for p in archivos]
    r = subprocess.run(
        [node, "--test", "--test-reporter=tap", *rutas],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    assert r.returncode == 0, f"fallaron tests JS:\n{salida}"
    assert re.search(r"^# fail 0\s*$", r.stdout, re.MULTILINE), salida


def test_tokens_rgb_coinciden_con_hex():
    css = COLORES.read_text(encoding="utf-8")
    hexes = dict(re.findall(r"--([a-z]+-\d+):\s*#([0-9A-Fa-f]{6})\b", css))
    canales = {
        m[0]: m[1:]
        for m in re.findall(r"--([a-z]+-\d+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)\s*;", css)
    }
    faltan = [n for n in CANALES_OBLIGATORIOS if n not in canales]
    assert not faltan, f"faltan canales RGB en colors.css: {faltan}"
    for nombre, rgb in canales.items():
        assert nombre in hexes, f"--{nombre}-rgb no tiene --{nombre} en hex"
        h = hexes[nombre]
        esperado = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        assert tuple(int(c) for c in rgb) == esperado, f"--{nombre}-rgb no coincide con #{h}"


def test_css_nuevo_usa_canales_con_respaldo():
    """burbuja.css no usa rgba() con cian literal y todo var(--*-rgb) lleva respaldo."""
    css = (RAIZ / "ui_web" / "css" / "burbuja.css").read_text(encoding="utf-8")
    usos = re.findall(r"var\(--([a-z]+-\d+)-rgb([^)]*)\)", css)
    assert usos, "burbuja.css debería usar los canales RGB"
    for nombre, resto in usos:
        assert resto.strip().startswith(","), f"var(--{nombre}-rgb) sin respaldo"
    assert "rgba(0,229,255" not in css.replace(" ", "")
    # El ancho es de cada página: con `body #bubble { max-width: 92% }` la animada
    # perdía su 230 px (la burbuja se estrechaba). burbuja.css no lo toca.
    assert not re.search(r"max-width\s*:", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    paginas = {"companion.html": "max-width:230px", "companion_vrm.html": "max-width:92%"}
    for pagina, ancho in paginas.items():
        html = (RAIZ / "ui_web" / pagina).read_text(encoding="utf-8").replace(" ", "")
        assert "#bubble{" + ancho in html, pagina
