"""
telegram-bot-or/hub.js — enrutado de eventos de un turno de chat (revisión de
regresiones, anexo B): lo que no es delta/act/done (tool:approval:request,
tool:result…) llega a los oyentes por tipo en vez de tragárselo el stream.
Se ejecuta el módulo real con Node.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HUB = (RAIZ / "telegram-bot-or" / "hub.js").as_uri()

SCRIPT = """
import { HubCliente } from %s;
const h = new HubCliente({ url: 'ws://127.0.0.1:1', token: 't', nombre: 'bot' });
const vistos = [];
let deltas = '';
h.on('tool:approval:request', ev => vistos.push('oyente:' + ev.type + ':' + ev.data.id));
h.on('tool:result', ev => vistos.push('oyente:' + ev.type));
h.chats.set('turno1', { resolve: ev => vistos.push('done:' + ev.data.text), reject() {},
                        timer: null, onDelta: t => { deltas += t; } });
const m = (type, pid, data = {}) => ({ data: JSON.stringify({ type, data, meta: { parent_id: pid } }) });
h._onMensaje(m('output:chat:delta', 'turno1', { text: 'ho' }));
h._onMensaje(m('tool:approval:request', 'turno1', { id: 'a1' }));
h._onMensaje(m('output:chat:act', 'turno1', { emotion: 'happy' }));
h._onMensaje(m('output:chat:done', 'turno1', { text: 'hola' }));
h._onMensaje(m('tool:result', 'turno1', { ok: true }));
console.log(JSON.stringify({ vistos, deltas, abiertos: h.chats.size }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
def test_eventos_de_herramientas_de_un_turno_llegan_a_los_oyentes():
    r = subprocess.run(["node", "--input-type=module", "-e", SCRIPT % json.dumps(HUB)],
                       capture_output=True, text=True, timeout=30, cwd=str(RAIZ))
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida["deltas"] == "ho" and salida["abiertos"] == 0
    assert salida["vistos"] == ["oyente:tool:approval:request:a1", "done:hola", "oyente:tool:result"]
