"""
Tarjetas web del corte 4 (extra/apariencia.jsx y extra/juego.jsx) y el menú radial SVG.

1. Sandbox de las seis tarjetas con y sin backend (tests/js/tarjetas_c4.mjs, con `node --test`):
   vista previa del tema ≤ 1 llamada cada 50 ms y guardado diferido, «Detectar» con
   atajos_capturando(true/false) al empezar/acabar/Esc/perder el foco/15 s, radial y bandeja,
   modo juego (forzar 1/0/-1, apps sin rutas) y rendimiento.
2. Paridad de window.LuneRadial.indice con ui/menu_radial.indice: la tabla se genera aquí con el
   Python real (miles de puntos, n = 0–11, cerca de la zona muerta y lejos) y el JS tiene que
   dar lo mismo en todos.
3. Los .jsx transpilan con el Babel vendorizado (ui_web/vendor/babel.min.js), siguen siendo
   scripts clásicos y se registran solos.

Sin Node, se saltan. Sin red ni pantalla.
"""
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
TARJETAS = RAIZ / "tests" / "js" / "tarjetas_c4.mjs"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado: se saltan los tests de JSX")
    return node


def _tap(r) -> dict:
    cuenta = {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}
    return cuenta


def _tabla_radial():
    """[[dx, dy, n, índice]] con ui/menu_radial.indice (None si ese módulo no está)."""
    try:
        from ui import menu_radial as mr
    except Exception:
        return None
    filas = []
    for n in range(0, 12):
        for k in range(240):
            a = math.radians(0.25 + k * 1.5)
            for r in (84.99, 85.01, 120.0, 400.0):
                dx, dy = r * math.sin(a), -r * math.cos(a)
                filas.append([dx, dy, n, mr.indice(dx, dy, n)])
        for dx, dy in ((0.0, -100.0), (100.0, 0.0), (0.0, 100.0), (-100.0, 0.0), (0.0, 0.0), (1e6, -1e6)):
            filas.append([dx, dy, n, mr.indice(dx, dy, n)])
    return filas


def test_tarjetas_y_paridad_del_radial(tmp_path):
    node = _node()
    env = dict(os.environ)
    tabla = _tabla_radial()
    if tabla is not None:
        ruta = tmp_path / "tabla_radial.json"
        ruta.write_text(json.dumps(tabla), encoding="utf-8")
        env["LUNE_TABLA_RADIAL"] = str(ruta)
    r = subprocess.run([node, "--test", "--test-reporter=tap", TARJETAS.relative_to(RAIZ).as_posix()], cwd=RAIZ,
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = _tap(r)
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de las tarjetas:\n{salida}"
    assert c.get("pass", 0) >= 8, salida
    if tabla is not None:
        assert c.get("skipped", 0) == 0, "la paridad con ui/menu_radial.indice no corrió:\n" + salida


def test_tabla_radial_cubre_zona_muerta_y_todos_los_botones():
    tabla = _tabla_radial()
    if tabla is None:
        pytest.skip("ui/menu_radial.py aún no está")
    assert any(f[3] is None for f in tabla if f[2] > 0), "hay puntos en la zona muerta"
    for n in range(1, 11):
        assert {f[3] for f in tabla if f[2] == n and f[3] is not None} == set(range(n)), n


ARNES_TRANSPILAR = r"""
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(process.argv[2], 'utf8');
const m = { exports: {} };
new Function('module', 'exports', 'self', 'window', src)(m, m.exports, {}, {});
const res = {};
for (const f of process.argv.slice(3)) {
  try {
    const code = m.exports.transform(fs.readFileSync(f, 'utf8'), { presets: ['react', 'env'],
      plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'], filename: path.basename(f) }).code;
    res[path.basename(f)] = { ok: true, clasico: !/\brequire\(|\bexports\.|^\s*import\s/m.test(code), registra: /Object\.assign\(\s*window\s*,/.test(code) };
  } catch (e) { res[path.basename(f)] = { ok: false, error: String(e.message).slice(0, 300) }; }
}
console.log(JSON.stringify(res));
"""


def test_jsx_del_corte4_transpilan_con_el_babel_vendorizado(tmp_path):
    node = _node()
    arnes = tmp_path / "transpilar.cjs"
    arnes.write_text(ARNES_TRANSPILAR, encoding="utf-8")
    archivos = [KIT / "extra" / "apariencia.jsx", KIT / "extra" / "juego.jsx", KIT / "app.jsx", KIT / "sidebar.jsx"]
    r = subprocess.run([node, str(arnes), str(RAIZ / "ui_web" / "vendor" / "babel.min.js"), *map(str, archivos)],
                       cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    lineas = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    assert lineas, (r.stdout or "") + (r.stderr or "")
    res = json.loads(lineas[-1])
    for nombre, v in res.items():
        assert v["ok"], f"{nombre}: {v.get('error')}"
        assert v["clasico"], f"{nombre}: tiene que seguir siendo un script clásico"
    assert res["apariencia.jsx"]["registra"] and res["juego.jsx"]["registra"]
