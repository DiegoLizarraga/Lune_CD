"""
index.html de la piel web con el corte 4.

- Colores: ningún rgba()/hex literal de los tokens cian, azul o amarillo; todos pasan por
  rgb(var(--x-rgb, R G B) / a) o var(--x, #HEX) y el respaldo es EXACTAMENTE el valor del token en
  tokens/colors.css (sin tema la página se ve igual; con tema se recolorea todo).
- Scripts: tema.js y lune_sfx.js (rutas que existen) y extra/apariencia.jsx y extra/juego.jsx
  antes de app.jsx; el canal se crea después de qwebchannel.js.
- Canal (se ejecuta el script de verdad en Node con un QWebChannel falso): window.luneEscritorio
  = channel.objects.escritorio, o null si el backend no lo registra, y ya está cuando llega
  'lune-ready'.
- Modo juego: la regla de body.modo-juego acaba las animaciones al instante y sin repetir.
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
COLORES = RAIZ / "ui_web" / "tokens" / "colors.css"
FAMILIAS = ("cyan", "blue", "yellow")


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def _tokens():
    css = COLORES.read_text(encoding="utf-8")
    hexes = {k: v.upper() for k, v in re.findall(r"--([a-z]+-\d+):\s*#([0-9A-Fa-f]{6})\b", css)}
    rgb = {k: tuple(int(x) for x in v) for k, *v in re.findall(r"--([a-z]+-\d+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)\s*;", css)}
    return hexes, rgb


def _estilo(html: str) -> str:
    return "\n".join(re.findall(r"<style>(.*?)</style>", html, re.S))


def test_sin_literales_de_color_de_los_tokens():
    html = _html()
    hexes, rgb = _tokens()
    de_tokens = {v: k for k, v in rgb.items() if k.split("-")[0] in FAMILIAS}
    sueltos = []
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", html):
        t = tuple(int(x) for x in m.groups())
        if t in de_tokens:
            sueltos.append(f"{m.group(0)} (= --{de_tokens[t]})")
    assert not sueltos, "rgba() con colores de tokens sin canal:\n" + "\n".join(sueltos)
    hex_tokens = {v: k for k, v in hexes.items() if k.split("-")[0] in FAMILIAS}
    sin_var = []
    for m in re.finditer(r"#([0-9A-Fa-f]{6})\b", html):
        if m.group(1).upper() not in hex_tokens:
            continue
        antes = html[max(0, m.start() - 40):m.start()]
        if not re.search(r"var\(--[a-z]+-\d+,\s*$", antes):
            sin_var.append(m.group(0))
    # El SVG de la miniatura del bundler usa amarillo e ink de relleno (no se pinta en la app).
    assert [h for h in sin_var if h.upper() != "#FFE000"] == [], sin_var


def test_los_respaldos_son_el_valor_del_token():
    html = _html()
    hexes, rgb = _tokens()
    usos = re.findall(r"var\(--([a-z]+-\d+)-rgb,\s*(\d+)\s+(\d+)\s+(\d+)\s*\)", html)
    assert len(usos) >= 27, f"esperaba los 20 rgba cian/azul + 1 hex + amarillos pasados a canales, hay {len(usos)}"
    for nombre, *v in usos:
        assert nombre in rgb, f"--{nombre}-rgb no existe en colors.css"
        assert tuple(int(x) for x in v) == rgb[nombre], f"respaldo de --{nombre}-rgb distinto del token"
    assert not re.search(r"var\(--[a-z]+-\d+-rgb\)", html), "todo var(--x-rgb) lleva respaldo"
    for nombre, h in re.findall(r"var\(--([a-z]+-\d+),\s*#([0-9A-Fa-f]{6})\)", html):
        assert hexes.get(nombre) == h.upper(), nombre
    # La forma del contrato: rgb(var(--x-rgb, R G B) / alfa)
    for m in re.finditer(r"rgb\(var\(--[a-z]+-\d+-rgb[^)]*\)\s*([^)]*)\)", html):
        assert re.fullmatch(r"/\s*(0?\.\d+|1|0)", m.group(1).strip()), m.group(0)


def _scripts(html):
    return re.findall(r"<script\b([^>]*)>", html)


def test_orden_de_scripts_y_rutas():
    html = _html()
    srcs = [re.search(r'src="([^"]+)"', a).group(1) for a in _scripts(html) if 'src="' in a]
    i = {s: n for n, s in enumerate(srcs)}
    for s in ("../../tema.js", "../../lune_sfx.js", "extra/apariencia.jsx", "extra/juego.jsx", "app.jsx",
              "../../qwebchannel.js", "../../_ds_bundle.js"):
        assert s in i, f"falta <script src=\"{s}\">"
        assert (KIT / s).resolve().is_file(), f"{s} no existe (ruta relativa a index.html)"
    for s in ("../../tema.js", "../../lune_sfx.js", "extra/apariencia.jsx", "extra/juego.jsx"):
        assert i[s] < i["app.jsx"], f"{s} tiene que cargar antes de app.jsx"
    assert i["extra/ia_avanzada.jsx"] < i["extra/apariencia.jsx"] < i["extra/juego.jsx"]
    assert i["../../_ds_bundle.js"] < i["../../tema.js"] < i["../../qwebchannel.js"]
    tipo = {re.search(r'src="([^"]+)"', a).group(1): a for a in _scripts(html) if 'src="' in a}
    assert 'type="text/babel"' in tipo["extra/apariencia.jsx"] and 'type="text/babel"' in tipo["extra/juego.jsx"]
    assert "type=" not in tipo["../../tema.js"] and "type=" not in tipo["../../lune_sfx.js"], "scripts clásicos"


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
  w.dispatchEvent = (e) => { eventos.push({ tipo: e.type, lune: w.lune === objetos.lune,
    escritorio: w.luneEscritorio === (objetos.escritorio || null) && 'luneEscritorio' in w }); };
  vm.createContext(w);
  vm.runInContext(codigo, w);
  return { eventos, escritorio: w.luneEscritorio === undefined ? 'undefined' : (w.luneEscritorio === null ? null : w.luneEscritorio.id) };
}
const sinQt = (() => { const w = {}; w.window = w; vm.createContext(w); vm.runInContext(codigo, w); return 'luneEscritorio' in w; })();
console.log(JSON.stringify({
  con: correr({ lune: { id: 'lune' }, escritorio: { id: 'escritorio' } }),
  sin: correr({ lune: { id: 'lune' } }),
  sinQt,
}));
"""


def test_canal_expone_luneEscritorio_antes_de_lune_ready(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    html = _html()
    inline = [c for c in re.findall(r"<script>(.*?)</script>", html, re.S) if "new QWebChannel" in c]
    assert len(inline) == 1
    js = tmp_path / "canal.js"
    js.write_text(inline[0], encoding="utf-8")
    arnes = tmp_path / "arnes.cjs"
    arnes.write_text(ARNES_CANAL, encoding="utf-8")
    r = subprocess.run([node, str(arnes), str(js)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["con"]["escritorio"] == "escritorio"
    assert res["con"]["eventos"] == [{"tipo": "lune-ready", "lune": True, "escritorio": True}]
    assert res["sin"]["escritorio"] is None, "backend sin el objeto: null, no undefined"
    assert res["sin"]["eventos"] == [{"tipo": "lune-ready", "lune": True, "escritorio": True}]
    assert res["sinQt"] is False, "en el navegador (sin qt) no se toca nada"


def test_modo_juego_acaba_las_animaciones_sin_repetir():
    css = _estilo(_html())
    reglas = re.findall(r"([^{}]*body\.modo-juego[^{}]*)\{([^}]*)\}", css)
    assert reglas, "falta la regla de body.modo-juego"
    selector, cuerpo = reglas[0]
    for sel in ("body.modo-juego *", "body.modo-juego *::before", "body.modo-juego *::after"):
        assert sel in selector
    decl = {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in cuerpo.split(";") if ":" in d)}
    assert decl["animation-duration"] == "0s !important"
    assert decl["animation-iteration-count"] == "1 !important"
    assert decl["animation-delay"] == "0s !important"
    assert decl["transition"] == "none !important"
    assert "animation-play-state" not in decl, "en pausa, las animaciones de entrada se quedarían invisibles"
