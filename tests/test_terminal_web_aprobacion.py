"""
lune_core/web/terminal.html — el terminal web sabe contestar aprobaciones
(revisión de regresiones, anexo A/B): anuncia tool:approval:response, enseña
la petición como texto plano con «Sí»/«No» y responde por su id; al cerrarse
(caducó) ya no se puede contestar. Se ejecuta el <script> real en Node con un
DOM y un WebSocket de mentira.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HTML = RAIZ / "lune_core" / "web" / "terminal.html"

ARNES = r"""
const vm = require('vm');
const fs = require('fs');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
function El(tag) {
  return { tag, hijos: [], className: '', textContent: '', disabled: false, value: '',
    style: {}, scrollTop: 0, scrollHeight: 0,
    classList: { add() {}, remove() {} },
    appendChild(h) { this.hijos.push(h); return h; },
    addEventListener() {}, focus() { doc.foco = this; },
    querySelectorAll(sel) { const out = []; const ir = n => { for (const h of n.hijos) { if (h.tag === 'button') out.push(h); ir(h); } }; ir(this); return out; } };
}
const els = {};
const doc = { foco: null, createElement: El,
  querySelector(s) { return els[s] || (els[s] = El(s)); } };
const enviados = [];
class WS { constructor(url) { this.url = url; this.readyState = 1; WS.ultimo = this; }
  send(t) { enviados.push(JSON.parse(t)); } close() {} }
const ctx = { document: doc, WebSocket: WS, location: { protocol: 'http:', hostname: 'h', port: '8766' },
  window: {}, crypto: { randomUUID: () => 'u' + Math.random().toString(16).slice(2) },
  setTimeout, clearTimeout, console, JSON, Math, Date, String, Map, Error, Promise };
vm.createContext(ctx);
vm.runInContext(codigo, ctx);
// Conectar: auth → announce.
vm.runInContext('token = "t"; conectar();', ctx);
const ws = WS.ultimo;
ws.onopen();
const auth = enviados[0];
ws.onmessage({ data: JSON.stringify({ type: 'auth:ok', data: {}, meta: { parent_id: auth.meta.id } }) });
const anuncio = enviados[1];
ws.onmessage({ data: JSON.stringify({ type: 'peers', data: {}, meta: { parent_id: anuncio.meta.id } }) });
// Petición de aprobación (con HTML dentro: debe quedar como texto).
const pet = { type: 'tool:approval:request', meta: { parent_id: 'x' },
  data: { id: 'a1', herramienta: 'lanzar_app', args: { app: 'calc' }, why: '<b>Abrir calc</b>', contaminado: true } };
ws.onmessage({ data: JSON.stringify(pet) });
const chat = els['#chat'];
const caja = chat.hijos[chat.hijos.length - 1];
const botones = caja.querySelectorAll('button');
const textos = caja.hijos.map(h => h.textContent);
const focoEnNo = doc.foco && doc.foco.textContent === 'No';
botones.find(b => b.textContent === 'Sí, hazlo').onclick();
botones.find(b => b.textContent === 'Sí, hazlo').onclick();       // doble clic: una sola respuesta
// Otra que caduca antes de contestar.
ws.onmessage({ data: JSON.stringify({ ...pet, data: { ...pet.data, id: 'a2' } }) });
const caja2 = chat.hijos[chat.hijos.length - 1];
ws.onmessage({ data: JSON.stringify({ type: 'tool:approval:close', data: { id: 'a2' }, meta: {} }) });
caja2.querySelectorAll('button').find(b => b.textContent === 'Sí, hazlo').onclick();
const respuestas = enviados.filter(e => e.type === 'tool:approval:response').map(e => e.data);
console.log(JSON.stringify({ eventos: anuncio.data.events, textos, focoEnNo, respuestas,
  deshabilitados: caja2.querySelectorAll('button').every(b => b.disabled) }));
"""


def _script() -> str:
    html = HTML.read_text(encoding="utf-8")
    return re.search(r"<script>(.*?)</script>", html, re.S).group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
def test_terminal_web_contesta_aprobaciones(tmp_path):
    js = tmp_path / "terminal.js"
    js.write_text(_script(), encoding="utf-8")
    arnes = tmp_path / "arnes.cjs"
    arnes.write_text(ARNES, encoding="utf-8")
    r = subprocess.run(["node", str(arnes), str(js)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert "tool:approval:response" in s["eventos"] and "input:text" in s["eventos"]
    assert any("<b>Abrir calc</b>" in t for t in s["textos"])           # texto plano, tal cual
    assert any("contenido externo" in t for t in s["textos"])
    assert s["focoEnNo"] is True
    assert s["respuestas"] == [{"id": "a1", "approved": True}]          # una vez; la caducada no
    assert s["deshabilitados"] is True
