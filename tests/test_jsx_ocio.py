"""
Web principal de los cortes 5 y 6: extra/alarmas.jsx, extra/baile.jsx, app.jsx, sidebar.jsx y vrm_barra.js.

1. El sandbox de tests/js/ocio_web.test.mjs con `node --test` (React falso, reloj falso, puentes falsos):
   AlarmasPanel con y sin backend (payloads exactos, cuenta atrás con el reloj del backend), AlarmaBanner
   (el bloqueo desactiva «Apagar» con cuenta atrás), AlarmasCard, PantallaGrandeCard, BaileCard, useBaile y
   el reloj del pulso, app.jsx (vista «alarmas», banner, CommandMenu) y la mascota de la barra bailando en
   vídeo y en VRM.
2. tests/js/vrm_barra.test.mjs: h.registrar antes de que cargue el motor, h.mod y h.usarModulo.
3. Los .jsx siguen siendo scripts clásicos (sin import/export) que se registran solos en window dentro de
   una IIFE, y sus colores del tema van por tokens (el tema del corte 4 los tiñe).

Sin Node, se saltan.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
JSX = [KIT / "extra" / "alarmas.jsx", KIT / "extra" / "baile.jsx"]


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado: se saltan los tests de JSX")
    return node


def _tap(r) -> dict:
    return {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}


def _correr(archivo: str, minimo: int):
    node = _node()
    r = subprocess.run([node, "--test", "--test-reporter=tap", archivo], cwd=RAIZ, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = _tap(r)
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de {archivo}:\n{salida}"
    assert c.get("pass", 0) >= minimo, salida
    assert c.get("skipped", 0) == 0, salida


def test_sandbox_de_la_web_de_ocio():
    _correr("tests/js/ocio_web.test.mjs", 17)


def test_vrm_barra_registrar_mod_y_usar_modulo():
    _correr("tests/js/vrm_barra.test.mjs", 42)


@pytest.mark.parametrize("ruta", JSX, ids=lambda p: p.name)
def test_jsx_clasico_que_se_registra_solo(ruta):
    src = ruta.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|export)\s", src, re.M), "script clásico: sin import/export"
    cuerpo = re.sub(r"^\s*/\*.*?\*/", "", src, count=1, flags=re.S).strip()
    assert cuerpo.startswith("(function () {") and cuerpo.rstrip().endswith("})();"), \
        "todo dentro de una IIFE (Babel convertiría los const de nivel superior en globales)"
    assert "Object.assign(window, {" in src


@pytest.mark.parametrize("ruta", JSX, ids=lambda p: p.name)
def test_colores_por_tokens(ruta):
    """Sin rgba()/hex literales de cian, azul o amarillo: el tema los redefine (tokens/colors.css)."""
    src = ruta.read_text(encoding="utf-8")
    css = (RAIZ / "ui_web" / "tokens" / "colors.css").read_text(encoding="utf-8")
    rgb = {k: tuple(int(x) for x in v) for k, *v in re.findall(r"--([a-z]+-\d+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)\s*;", css)}
    hexes = {v.upper(): k for k, v in re.findall(r"--([a-z]+-\d+):\s*#([0-9A-Fa-f]{6})\b", css)}
    de_tema = {v: k for k, v in rgb.items() if k.split("-")[0] in ("cyan", "blue", "yellow")}
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", src):
        assert tuple(int(x) for x in m.groups()) not in de_tema, m.group(0)
    for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", src):
        nombre = hexes.get(m.group(1).upper(), "")
        assert nombre.split("-")[0] not in ("cyan", "blue", "yellow"), f"{m.group(0)} (= --{nombre}) sin var()"
    for nombre, *v in re.findall(r"var\(--([a-z]+-\d+)-rgb,\s*(\d+)\s+(\d+)\s+(\d+)\s*\)", src):
        assert tuple(int(x) for x in v) == rgb[nombre], f"respaldo de --{nombre}-rgb distinto del token"
    assert not re.search(r"var\(--[a-z]+-\d+-rgb\)", src), "todo var(--x-rgb) lleva respaldo"
