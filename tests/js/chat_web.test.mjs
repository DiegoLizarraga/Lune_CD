// tests/js/chat_web.test.mjs — el chat de la piel web (ui_kits/lune-desktop/chat.jsx, 11.2): cada
// mensaje es un React.memo que solo se vuelve a pintar si cambia su id, su texto, si sigue escribiéndose
// (streaming) u otro dato suyo; así cada trozo de la respuesta no repinta la conversación entera.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

import { crearSandbox, KIT, buscar, texto } from './jsx_falso.mjs';

function montar() {
  const S = crearSandbox({ archivos: [path.join(KIT, 'chat.jsx')] });
  const h = S.h;
  const pintadas = [];
  S.sb.LUNE.ChatBubble = ({ role, streaming, children }) => {
    pintadas.push(role);
    return h('div', { 'data-role': role, 'data-streaming': !!streaming }, children);
  };
  S.sb.LUNE.Avatar = () => h('img', null);
  return { S, h, pintadas };
}

test('Mensaje es un React.memo con el comparador del chat', () => {
  const { S } = montar();
  const { Mensaje, burbujaIgual } = S.sb.LuneChat;
  assert.equal(typeof Mensaje, 'function');
  assert.equal(Mensaje.igual, burbujaIgual, 'React.memo(MensajeChat, burbujaIgual)');
  assert.equal(typeof Mensaje.tipo, 'function');
});

test('burbujaIgual: el mismo objeto o los mismos datos no repintan; texto, streaming o id sí', () => {
  const { S } = montar();
  const { burbujaIgual: igual } = S.sb.LuneChat;
  const m = { id: 'm1', role: 'bot', provider: 'local', text: 'Hola', time: '10:00', streaming: true };
  assert.equal(igual({ m }, { m }), true);
  assert.equal(igual({ m }, { m: { ...m } }), true, 'copia igual (el updater de app.jsx)');
  assert.equal(igual({ m }, { m: { ...m, text: 'Hola, ¿qué' } }), false, 'un trozo más de la respuesta');
  assert.equal(igual({ m }, { m: { ...m, streaming: false } }), false, 'terminó de escribir');
  assert.equal(igual({ m }, { m: { ...m, id: 'm2' } }), false);
  assert.equal(igual({ m }, { m: { ...m, provider: 'cloud' } }), false);
  const tool = { ok: true, title: 'x' };
  const t1 = { id: 't', kind: 'tool', tool };
  assert.equal(igual({ m: t1 }, { m: { ...t1 } }), true);
  assert.equal(igual({ m: t1 }, { m: { ...t1, tool: { ...tool } } }), false);
  assert.equal(igual({ m: null }, { m }), false);
});

test('ChatStream pinta cada mensaje (usuario, bot escribiendo y herramienta) en orden', () => {
  const { S, h, pintadas } = montar();
  const iconos = { IconBolt: () => h('i', null) };
  Object.assign(S.sb, iconos);
  const mensajes = [
    { id: 'm1', role: 'user', text: 'abre youtube', time: '10:00' },
    { id: 'm2', kind: 'tool', tool: { ok: true, icon: 'bolt', title: 'Abriendo youtube', detail: 'ok' } },
    { id: 'm3', role: 'bot', provider: 'local', text: 'Listo', time: '10:00', streaming: true },
  ];
  const arbol = S.render(h(S.sb.ChatStream, { messages: mensajes, typing: false, provider: 'local' }));
  const burbujas = buscar(arbol, (n) => n.props && n.props['data-role']);
  assert.deepEqual(burbujas.map((b) => [b.props['data-role'], texto(b)]), [['user', 'abre youtube'], ['bot', 'Listo']]);
  assert.equal(burbujas[1].props['data-streaming'], true);
  assert.ok(texto(buscar(arbol, (n) => n.props && n.props.className === 'ln-tool-title')[0]).includes('Abriendo youtube'));
  assert.deepEqual(pintadas, ['user', 'bot']);
});
