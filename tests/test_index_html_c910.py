"""
index.html de la piel web con los cortes 9 y 10, extra/bailes_mmd.jsx y extra/minecraft.jsx.

- Scripts: los dos .jsx (text/babel) después de extra/vida.jsx y antes de app.jsx; las rutas existen.
- Canal (se ejecuta el script de verdad en Node con un QWebChannel falso): window.luneEscenario =
  channel.objects.escenario, o null si el backend no lo registra, y ya está cuando llega 'lune-ready'.
- Los dos .jsx: scripts clásicos dentro de una IIFE que se registran solos en window; colores del tema por
  tokens (rgb(var(--x-rgb, r g b) / a), sin hex ni rgba de cian, azul o amarillo); nunca HTML crudo.
- Paridad con Python: cada ranura que piden (`pedir('x'…)`) y cada señal que escuchan (`conectar('x'…)`) existe
  en ui/puente_escenario.PuenteEscenario (y app.jsx escucha vista_pedida).
- app.jsx y apariencia.jsx conocen las vistas «bailes» y «minecraft».
- El sandbox de tests/js/escenario_web.test.mjs con `node --test`.
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
JSX = {"bailes": KIT / "extra" / "bailes_mmd.jsx", "minecraft": KIT / "extra" / "minecraft.jsx"}


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


def test_orden_de_scripts_y_rutas():
    s = _scripts(_html())
    i = {src: n for n, (src, _) in enumerate(s)}
    attrs = dict(s)
    for src in ("extra/bailes_mmd.jsx", "extra/minecraft.jsx"):
        assert src in i, f'falta <script src="{src}">'
        assert (KIT / src).resolve().is_file()
        assert 'type="text/babel"' in attrs[src]
        assert i["extra/vida.jsx"] < i[src] < i["app.jsx"], "después de los cortes 7/8 y antes de app.jsx"
        assert list(i).count(src) == 1


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
  w.dispatchEvent = (e) => { eventos.push({ tipo: e.type, lune: id('lune'), vida: id('luneVida'), escenario: id('luneEscenario') }); };
  vm.createContext(w);
  vm.runInContext(codigo, w);
  return eventos;
}
console.log(JSON.stringify({
  todo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' }, alarmas: { id: 'alarmas' }, musica: { id: 'musica' },
                 vida: { id: 'vida' }, escenario: { id: 'escenario' } }),
  viejo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' }, vida: { id: 'vida' } }),
}));
"""


def test_canal_expone_luneEscenario_antes_de_lune_ready(tmp_path):
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
    assert res["todo"] == [{"tipo": "lune-ready", "lune": "lune", "vida": "vida", "escenario": "escenario"}]
    assert res["viejo"] == [{"tipo": "lune-ready", "lune": "lune", "vida": "vida", "escenario": None}], \
        "backend sin el objeto: null, no undefined"


@pytest.mark.parametrize("nombre", sorted(JSX))
def test_jsx_clasico_que_se_registra_solo_y_sin_html_crudo(nombre):
    src = JSX[nombre].read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|export)\s", src, re.M), "script clásico: sin import/export"
    cuerpo = re.sub(r"^\s*/\*.*?\*/", "", src, count=1, flags=re.S).strip()
    assert cuerpo.startswith("(function () {") and cuerpo.rstrip().endswith("})();"), \
        "todo dentro de una IIFE (Babel convertiría los const de nivel superior en globales)"
    assert "Object.assign(window, {" in src
    for prohibido in ("dangerouslySetInnerHTML", "innerHTML", "eval(", "new Function"):
        assert prohibido not in src, f"{prohibido}: los títulos y el chat del juego van como texto"


@pytest.mark.parametrize("nombre", sorted(JSX))
def test_jsx_colores_por_tokens(nombre):
    """Sin rgba()/hex literales de cian, azul o amarillo: el tema los redefine (tokens/colors.css)."""
    src = JSX[nombre].read_text(encoding="utf-8")
    css = (RAIZ / "ui_web" / "tokens" / "colors.css").read_text(encoding="utf-8")
    rgb = {k: tuple(int(x) for x in v) for k, *v in re.findall(r"--([a-z]+-\d+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)\s*;", css)}
    hexes = {v.upper(): k for k, v in re.findall(r"--([a-z]+-\d+):\s*#([0-9A-Fa-f]{6})\b", css)}
    de_tema = {v: k for k, v in rgb.items() if k.split("-")[0] in ("cyan", "blue", "yellow")}
    for m in re.finditer(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)", src):
        assert tuple(int(x) for x in m.groups()) not in de_tema, m.group(0)
    for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", src):
        n = hexes.get(m.group(1).upper(), "")
        assert n.split("-")[0] not in ("cyan", "blue", "yellow"), f"{m.group(0)} (= --{n}) sin var()"
    usados = re.findall(r"var\(--([a-z]+-\d+)-rgb,\s*(\d+)\s+(\d+)\s+(\d+)\s*\)", src)
    assert usados, "los colores con alfa van por canales"
    for n, *v in usados:
        assert tuple(int(x) for x in v) == rgb[n], f"respaldo de --{n}-rgb distinto del token"
    assert not re.search(r"var\(--[a-z]+-\d+-rgb\)", src), "todo var(--x-rgb) lleva respaldo"
    assert "rgba(" not in src, "canales con rgb(var(--x-rgb, r g b) / a), no rgba()"


def test_paridad_de_ranuras_y_senales_con_el_puente():
    pytest.importorskip("PyQt6.QtCore")
    from ui.puente_escenario import PuenteEscenario
    meta = PuenteEscenario.staticMetaObject
    ranuras, senales = set(), set()
    for i in range(meta.methodOffset(), meta.methodCount()):
        m = meta.method(i)
        nombre = bytes(m.name()).decode()
        (senales if m.methodType() == m.MethodType.Signal else ranuras).add(nombre)
    usadas, escuchadas = set(), set()
    for ruta in JSX.values():
        src = ruta.read_text(encoding="utf-8")
        usadas |= set(re.findall(r"pedir\('([a-z_]+)'", src))
        escuchadas |= set(re.findall(r"conectar\('([a-z_]+)'", src))
    assert usadas and usadas <= ranuras, sorted(usadas - ranuras)
    assert escuchadas and escuchadas <= senales, sorted(escuchadas - senales)
    app = (KIT / "app.jsx").read_text(encoding="utf-8")
    assert "luneEscenario.vista_pedida" in app and "vista_pedida" in senales
    # el puente falso de los tests de JS tiene las mismas ranuras y señales que el de verdad
    js = (RAIZ / "tests" / "js" / "escenario_web.test.mjs").read_text(encoding="utf-8")
    lista = lambda n: set(re.findall(r"'([a-z_]+)'", re.search(rf"const {n} = \[(.*?)\];", js, re.S).group(1)))  # noqa: E731
    assert lista("RANURAS") == ranuras, sorted(lista("RANURAS") ^ ranuras)
    assert lista("SENALES") == senales, sorted(lista("SENALES") ^ senales)


def test_app_y_apariencia_conocen_las_vistas_nuevas():
    app = (KIT / "app.jsx").read_text(encoding="utf-8")
    vistas = re.search(r"const VISTAS_APP = \[(.*?)\];", app, re.S).group(1)
    assert "'bailes'" in vistas and "'minecraft'" in vistas
    ap = (KIT / "extra" / "apariencia.jsx").read_text(encoding="utf-8")
    vistas = re.search(r"const VISTAS = \[(.*?)\];", ap, re.S).group(1)
    assert "'bailes'" in vistas and "'minecraft'" in vistas
    assert re.search(r"^\s*film: \[", ap, re.M), "icono «film» de «Mis bailes» en el radial SVG"


def test_sandbox_de_la_web_del_escenario():
    node = _node()
    r = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/escenario_web.test.mjs"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de escenario_web:\n{salida}"
    assert c.get("pass", 0) >= 17, salida
    assert c.get("skipped", 0) == 0, salida
