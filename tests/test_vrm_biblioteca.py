"""
Tests de la biblioteca VRM de la interfaz web
(ui_web/ui_kits/lune-desktop/extra/vrm_biblioteca.jsx) contra nucleo/vrm.py.

La rejilla valida en el navegador con los mismos rangos que el backend: aquí se
transpila el .jsx con el Babel vendorizado (como hace la página), se ejecuta en un
sandbox de `vm` con un React vacío (solo hacen falta las utilidades puras de
window.LuneVrm) y se compara con nucleo.vrm.AJUSTES / validar_valor.

Sin Node, se salta. Sin red ni pantalla.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import vrm  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
JSX = RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "extra" / "vrm_biblioteca.jsx"
BABEL = RAIZ / "ui_web" / "vendor" / "babel.min.js"

ARNES = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const [rutaBabel, rutaJsx, casosJson] = process.argv.slice(1);   // con -e no hay ruta de script
const m = { exports: {} };
new Function('module', 'exports', 'self', 'window', fs.readFileSync(rutaBabel, 'utf8'))(m, m.exports, {}, {});
const code = m.exports.transform(fs.readFileSync(rutaJsx, 'utf8'), {
  presets: ['react', 'env'],
  plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'],
  filename: 'vrm_biblioteca.jsx',
}).code;
const sb = { React: {}, console, LUNE: {} };
sb.window = sb;
vm.createContext(sb);
vm.runInContext(code, sb, { filename: 'vrm_biblioteca.jsx' });
const L = sb.LuneVrm;
const casos = JSON.parse(casosJson);
console.log(JSON.stringify({
  componente: typeof sb.VrmBiblioteca,
  rangos: L.RANGOS,
  defectos: L.DEFECTOS,
  validar: casos.validar.map(([k, v]) => L.validarValor(k, v)),
  archivo: casos.archivo.map((a) => L.archivoValido(a)),
  url: casos.url.map((u) => L.urlMiniatura(u)),
}));
"""

CASOS_VALIDAR = [
    ["luz", 9], ["luz", 0], ["luz", "1,5"], ["luz", " 2.25 "], ["luz", "x"], ["luz", True], ["luz", None],
    ["altura", -0.25], ["altura", -3], ["altura", 0.123456],
    ["pesoCabeza", 0.5], ["pesoTorso", 2], ["pesoOjos", -1], ["pesoOjos", "0,3333333"],
    ["invertirH", True], ["invertirH", False], ["invertirH", -0.2], ["invertirH", 3], ["invertirH", "no"],
    ["invertirV", 0], ["invertirBrazos", -5], ["invertirPiernas", "1"],
    ["invertirEjes", "auto"], ["invertirEjes", "Automático"], ["invertirEjes", 0.4], ["invertirEjes", 0.5],
    ["invertirEjes", -0.5], ["invertirEjes", -7], ["invertirEjes", 9], ["invertirEjes", "x"],
    ["fov", 60], ["__proto__", 1], ["toString", 1],
]
CASOS_ARCHIVO = ["a_luna.vrm", "A.VRM", "../fuera.vrm", "sub/x.vrm", "c:x.vrm", ".vrm", "x.glb", "", "x" * 197 + ".vrm"]
CASOS_URL = ["data:image/png;base64,iVBORw0KGgo=", "data:image/jpeg;base64,/9j/4AA=", "http://x/y.png",
             "javascript:alert(1)", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,<script>", ""]


@pytest.fixture(scope="module")
def js():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    casos = json.dumps({"validar": CASOS_VALIDAR, "archivo": CASOS_ARCHIVO, "url": CASOS_URL})
    r = subprocess.run([node, "-e", ARNES, str(BABEL), str(JSX), casos], cwd=RAIZ, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_se_registra(js):
    assert js["componente"] == "function"


def test_rangos_identicos_a_nucleo_vrm(js):
    assert list(js["rangos"]) == list(vrm.AJUSTES)
    for clave, r in vrm.AJUSTES.items():
        j = js["rangos"][clave]
        assert j["tipo"] == r["tipo"], clave
        assert j["defecto"] == r["defecto"], clave
        if r["tipo"] == "real":
            assert (j["min"], j["max"]) == (r["min"], r["max"]), clave
        if r["tipo"] == "opcion":
            assert sorted(j["valores"]) == sorted(r["valores"]), clave
    assert js["defectos"] == {k: r["defecto"] for k, r in vrm.AJUSTES.items()}


def test_valida_igual_que_el_backend(js):
    for (clave, valor), v_js in zip(CASOS_VALIDAR, js["validar"]):
        v_py = vrm.validar_valor(clave, valor)
        assert v_js == v_py, (clave, valor, v_js, v_py)


def test_nombres_de_archivo_y_miniaturas_seguras(js):
    for nombre, ok_js in zip(CASOS_ARCHIVO, js["archivo"]):
        try:
            vrm._nombre_seguro(nombre)
            ok_py = True
        except ValueError:
            ok_py = False
        assert ok_js == ok_py, nombre
    assert js["url"][:2] == CASOS_URL[:2]
    assert js["url"][2:] == [""] * (len(CASOS_URL) - 2)
