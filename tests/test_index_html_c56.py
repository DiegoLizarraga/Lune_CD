"""
index.html de la piel web con los cortes 5 y 6.

- Scripts: ../../lune_ritmo.js (clásico, antes de los .jsx) y extra/alarmas.jsx y extra/baile.jsx (text/babel,
  después de los del corte 4 y antes de app.jsx); rutas que existen.
- Canal (se ejecuta el script de verdad en Node con un QWebChannel falso): window.luneAlarmas =
  channel.objects.alarmas y window.luneMusica = channel.objects.musica, o null si el backend no los registra,
  y ya están cuando llega 'lune-ready' (junto a lune y luneEscritorio).
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


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def _scripts(html):
    """[(src, atributos)] de los <script src> en orden."""
    out = []
    for attrs in re.findall(r"<script\b([^>]*)>", html):
        m = re.search(r'src="([^"]+)"', attrs)
        if m:
            out.append((m.group(1), attrs))
    return out


def test_orden_de_scripts_y_rutas():
    s = _scripts(_html())
    i = {src: n for n, (src, _) in enumerate(s)}
    attrs = dict(s)
    for src in ("../../lune_ritmo.js", "extra/alarmas.jsx", "extra/baile.jsx", "app.jsx", "sidebar.jsx", "vrm_barra.js"):
        assert src in i, f"falta <script src=\"{src}\">"
        assert (KIT / src).resolve().is_file(), f"{src} no existe (ruta relativa a index.html)"
    assert "type=" not in attrs["../../lune_ritmo.js"], "lune_ritmo.js es un script clásico (globalThis.LuneRitmo)"
    assert i["../../lune_ritmo.js"] < i["sidebar.jsx"] and i["../../lune_ritmo.js"] < i["extra/baile.jsx"]
    assert i["../../_ds_bundle.js"] < i["../../lune_ritmo.js"] < i["../../qwebchannel.js"]
    for jsx in ("extra/alarmas.jsx", "extra/baile.jsx"):
        assert 'type="text/babel"' in attrs[jsx]
        assert i["extra/juego.jsx"] < i[jsx] < i["app.jsx"], f"{jsx}: después del corte 4 y antes de app.jsx"
    assert 'type="module"' in attrs["vrm_barra.js"]


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
  w.dispatchEvent = (e) => { eventos.push({ tipo: e.type, lune: id('lune'), escritorio: id('luneEscritorio'),
    alarmas: id('luneAlarmas'), musica: id('luneMusica') }); };
  vm.createContext(w);
  vm.runInContext(codigo, w);
  return eventos;
}
console.log(JSON.stringify({
  todo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' }, alarmas: { id: 'alarmas' }, musica: { id: 'musica' } }),
  viejo: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' } }),
}));
"""


def test_canal_expone_luneAlarmas_y_luneMusica_antes_de_lune_ready(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    inline = [c for c in re.findall(r"<script>(.*?)</script>", _html(), re.S) if "new QWebChannel" in c]
    assert len(inline) == 1
    js = tmp_path / "canal.js"
    js.write_text(inline[0], encoding="utf-8")
    arnes = tmp_path / "arnes.cjs"
    arnes.write_text(ARNES_CANAL, encoding="utf-8")
    r = subprocess.run([node, str(arnes), str(js)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["todo"] == [{"tipo": "lune-ready", "lune": "lune", "escritorio": "escritorio", "alarmas": "alarmas",
                            "musica": "musica"}]
    assert res["viejo"] == [{"tipo": "lune-ready", "lune": "lune", "escritorio": "escritorio", "alarmas": None,
                             "musica": None}], "backend sin los objetos: null, no undefined"
