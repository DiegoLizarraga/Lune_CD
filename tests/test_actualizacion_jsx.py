"""
La tarjeta «Actualizaciones» de la web (extra/actualizaciones.jsx) en el sandbox de Node
(tests/js/actualizaciones.test.mjs, con el Babel vendorizado y un window.lune falso), y que las
ranuras del falso son las de verdad de LuneBridge. Sin Node, se salta.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def test_el_falso_tiene_las_ranuras_de_verdad():
    pytest.importorskip("PyQt6.QtCore")
    from PyQt6.QtCore import QMetaMethod
    from ui.web_bridge import LuneBridge
    mo = LuneBridge.staticMetaObject
    ranuras = {bytes(mo.method(i).name()).decode() for i in range(mo.methodCount())
               if mo.method(i).methodType() == QMetaMethod.MethodType.Slot}
    js = (RAIZ / "tests" / "js" / "actualizaciones.test.mjs").read_text(encoding="utf-8")
    falsas = set(re.findall(r"'([a-z_]+)'", re.search(r"const RANURAS = \[(.*?)\];", js, re.S).group(1)))
    assert falsas == {n for n in ranuras if n.startswith("actualizacion_")}


def test_sandbox_de_la_tarjeta_de_actualizaciones():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    r = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/actualizaciones.test.mjs"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de actualizaciones.jsx:\n{salida}"
    assert c.get("pass", 0) >= 8, salida
    assert c.get("skipped", 0) == 0, salida
