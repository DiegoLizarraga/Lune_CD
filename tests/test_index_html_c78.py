"""
index.html de la piel web con los cortes 7 y 8, y extra/vida.jsx.

- Scripts: extra/vida.jsx (text/babel) después de los de los cortes 5/6 y antes de app.jsx; la ruta existe.
- Canal (se ejecuta el script de verdad en Node con un QWebChannel falso): window.luneVida =
  channel.objects.vida, o null si el backend no lo registra, y ya está cuando llega 'lune-ready'.
- vida.jsx: script clásico dentro de una IIFE que se registra solo en window; colores del tema por
  tokens (rgb(var(--x-rgb, r g b) / a), sin hex ni rgba de cian, azul o amarillo).
- El sandbox de tests/js/vida_web.test.mjs con `node --test` (tarjetas con y sin backend, ComidaWeb,
  app.jsx + sidebar.jsx).
Sin Node, lo que lo necesita se salta.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
HTML = KIT / "index.html"
VIDA = KIT / "extra" / "vida.jsx"


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def _scripts(html):
    out = []
    for attrs in re.findall(r"<script\b([^>]*)>", html):
        m = re.search(r'src="([^"]+)"', attrs)
        if m:
            out.append((m.group(1), attrs))
    return out


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    return node


def test_orden_de_scripts_y_ruta():
    s = _scripts(_html())
    i = {src: n for n, (src, _) in enumerate(s)}
    attrs = dict(s)
    assert "extra/vida.jsx" in i, 'falta <script src="extra/vida.jsx">'
    assert (KIT / "extra" / "vida.jsx").resolve().is_file()
    assert 'type="text/babel"' in attrs["extra/vida.jsx"]
    assert i["extra/baile.jsx"] < i["extra/vida.jsx"] < i["app.jsx"], "después de los cortes 5/6 y antes de app.jsx"
    assert list(i).count("extra/vida.jsx") == 1


ARNES_CANAL = r"""
const vm = require('vm');
const codigo = require('fs').readFileSync(process.argv[2], 'utf8');
function correr(objetos) {
  const eventos = [];
  const w = {
    qt: { webChannelTransport: {} },
    QWebChannel: function (transporte, cb) { cb({ objects: objetos }); },
    Event: function (t) { this.type = t; },
  };
  w.window = w;
  const id = (k) => (w[k] === undefined ? 'undefined' : w[k] === null ? null : w[k].id);
  w.dispatchEvent = (e) => { eventos.push({ tipo: e.type, lune: id('lune'), alarmas: id('luneAlarmas'), vida: id('luneVida') }); };
  vm.createContext(w);
  vm.runInContext(codigo, w);
  return eventos;
}
console.log(JSON.stringify({
  todo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' }, alarmas: { id: 'alarmas' }, musica: { id: 'musica' },
                 vida: { id: 'vida' } }),
  viejo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' }, alarmas: { id: 'alarmas' } }),
}));
"""


def test_canal_expone_luneVida_antes_de_lune_ready(tmp_path):
    node = _node()
    inline = [c for c in re.findall(r"<script>(.*?)</script>", _html(), re.S) if "new QWebChannel" in c]
    assert len(inline) == 1
    js = tmp_path / "canal.js"
    js.write_text(inline[0], encoding="utf-8")
    arnes = tmp_path / "arnes.cjs"
    arnes.write_text(ARNES_CANAL, encoding="utf-8")
    r = subprocess.run([node, str(arnes), str(js)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["todo"] == [{"tipo": "lune-ready", "lune": "lune", "alarmas": "alarmas", "vida": "vida"}]
    assert res["viejo"] == [{"tipo": "lune-ready", "lune": "lune", "alarmas": "alarmas", "vida": None}], \
        "backend sin el objeto: null, no undefined"


def test_vida_jsx_clasico_que_se_registra_solo():
    src = VIDA.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|export)\s", src, re.M), "script clásico: sin import/export"
    cuerpo = re.sub(r"^\s*/\*.*?\*/", "", src, count=1, flags=re.S).strip()
    assert cuerpo.startswith("(function () {") and cuerpo.rstrip().endswith("})();"), \
        "todo dentro de una IIFE (Babel convertiría los const de nivel superior en globales)"
    assert "Object.assign(window, {" in src


def test_vida_jsx_colores_por_tokens():
    """Sin rgba()/hex literales de cian, azul o amarillo: el tema los redefine (tokens/colors.css)."""
    src = VIDA.read_text(encoding="utf-8")
    css = (RAIZ / "ui_web" / "tokens" / "colors.css").read_text(encoding="utf-8")
    rgb = {k: tuple(int(x) for x in v) for k, *v in re.findall(r"--([a-z]+-\d+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)\s*;", css)}
    hexes = {v.upper(): k for k, v in re.findall(r"--([a-z]+-\d+):\s*#([0-9A-Fa-f]{6})\b", css)}
    de_tema = {v: k for k, v in rgb.items() if k.split("-")[0] in ("cyan", "blue", "yellow")}
    for m in re.finditer(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)", src):
        assert tuple(int(x) for x in m.groups()) not in de_tema, m.group(0)
    for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", src):
        nombre = hexes.get(m.group(1).upper(), "")
        assert nombre.split("-")[0] not in ("cyan", "blue", "yellow"), f"{m.group(0)} (= --{nombre}) sin var()"
    usados = re.findall(r"var\(--([a-z]+-\d+)-rgb,\s*(\d+)\s+(\d+)\s+(\d+)\s*\)", src)
    assert usados, "los colores con alfa van por canales"
    for nombre, *v in usados:
        assert tuple(int(x) for x in v) == rgb[nombre], f"respaldo de --{nombre}-rgb distinto del token"
    assert not re.search(r"var\(--[a-z]+-\d+-rgb\)", src), "todo var(--x-rgb) lleva respaldo"
    assert "rgba(" not in src, "canales con rgb(var(--x-rgb, r g b) / a), no rgba()"


def test_privacidad_de_discord_igual_en_python_y_en_la_pagina():
    """La lista fija de «Discord ve» de vida.jsx es la de servicios/discord_presencia (y la del puente)."""
    from servicios.discord_presencia import ESTADOS
    from ui import puente_vida as pv
    src = VIDA.read_text(encoding="utf-8")
    bloque = re.search(r"const ESTADOS_DISCORD = \[(.*?)\];", src, re.S).group(1)
    en_js = set(re.findall(r"'([^']+)'", bloque))
    assert en_js == {t for _, t in ESTADOS}
    detalles = set(re.findall(r"'([^']+)'", re.search(r"const DETALLES_DISCORD = \[(.*?)\];", src, re.S).group(1)))
    assert detalles == set(pv.DETALLES_DISCORD)


def test_sandbox_de_la_web_de_vida():
    node = _node()
    r = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/vida_web.test.mjs"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de vida_web:\n{salida}"
    assert c.get("pass", 0) >= 13, salida
    assert c.get("skipped", 0) == 0, salida
