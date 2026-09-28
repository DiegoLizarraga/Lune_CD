// tests/js/mc_canal.test.mjs — el canal del bot de Minecraft con Lune (minecraft-bot/src/canal.js)
// y el arranque de bot.js (token, configuración, --probar). Sin mineflayer, sin red:
// stdin de mentira (PassThrough), salida apuntada y reloj/temporizadores falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { requerirBot, esperar } from './mc_falsos.mjs';

const { crearCanal, jsonAscii, MARCA, MAX_LINEA, MAX_ENTRADA } = requerirBot('./canal');
const { main, textoMotivo, explicar } = requerirBot('./bot');

const TOKEN = '0123456789abcdef0123456789abcdef';

function canal(extra = {}) {
  const lineas = [];
  const salidas = [];
  const recibidos = [];
  const c = crearCanal({
    token: TOKEN, escribir: (l) => lineas.push(l), salir: (codigo) => salidas.push(codigo),
    ahora: () => 42, alRecibir: (m) => recibidos.push(m), ...extra,
  });
  return { c, lineas, salidas, recibidos };
}

function parsear(linea) {
  assert.ok(linea.startsWith(`${MARCA} ${TOKEN} `), linea);
  const json = linea.slice(`${MARCA} ${TOKEN} `.length);
  assert.match(json, /^[\x20-\x7e]*$/, 'el JSON va en ASCII');
  return JSON.parse(json);
}

test('emitir: marca al principio, token, tipo y t; el JSON en ASCII (tildes y emojis escapados)', () => {
  const { c, lineas } = canal();
  assert.equal(c.emitir('chat', { de: 'Steve', texto: 'hola ñandú 💎' }), true);
  const m = parsear(lineas[0]);
  assert.deepEqual(m, { de: 'Steve', texto: 'hola ñandú 💎', tipo: 'chat', t: 42 });
  assert.equal(jsonAscii({ a: 'é' }), '{"a":"\\u00e9"}');
});

test('emitir: los datos no pueden cambiar el tipo; tipos desconocidos y sin token no salen', () => {
  const { c, lineas } = canal();
  c.emitir('evento', { tipo: 'config', evento: 'muerte' });
  assert.equal(parsear(lineas[0]).tipo, 'evento');
  assert.equal(c.emitir('orden', {}), false);          // tipo de Lune → bot: no sale
  assert.equal(c.emitir('cualquiera', {}), false);
  const sin = crearCanal({ token: '', escribir: (l) => lineas.push(l) });
  assert.equal(sin.emitir('listo', {}), false);
  assert.equal(lineas.length, 1);
});

test('emitir: una línea de más de 8 KB se cambia por un error corto', () => {
  const { c, lineas } = canal();
  c.emitir('desconectado', { motivo: 'x'.repeat(MAX_LINEA) });
  const m = parsear(lineas[0]);
  assert.equal(m.tipo, 'error');
  assert.ok(lineas[0].length < 200);
  assert.equal(c.emitir('error', { mensaje: 'y'.repeat(MAX_LINEA) }), false);
});

test('recibir: solo objetos con un tipo de Lune y de tamaño razonable', () => {
  const { c } = canal();
  assert.deepEqual(c.recibir('{"tipo":"orden","id":"a1","texto":"sigueme"}'), { tipo: 'orden', id: 'a1', texto: 'sigueme' });
  assert.equal(c.recibir('no es json'), null);
  assert.equal(c.recibir('[1,2]'), null);
  assert.equal(c.recibir('{"tipo":"chat"}'), null);           // tipo del bot, no de Lune
  assert.equal(c.recibir('{"sin":"tipo"}'), null);
  assert.equal(c.recibir(JSON.stringify({ tipo: 'decir', texto: 'x'.repeat(MAX_ENTRADA) })), null);
  assert.equal(c.recibir(''), null);
});

test('escuchar: cada línea válida llega a alRecibir; al cerrarse stdin, salir(0) y ya no emite', async () => {
  const entrada = new PassThrough();
  const { c, recibidos, salidas, lineas } = canal({ entrada });
  c.escuchar();
  entrada.write('{"tipo":"estado"}\nbasura\n{"tipo":"pausa_llm","on":true}\n');
  await esperar();
  assert.deepEqual(recibidos.map((m) => m.tipo), ['estado', 'pausa_llm']);
  entrada.end();
  await esperar();
  assert.deepEqual(salidas, [0]);
  assert.equal(c.cerrado, true);
  assert.equal(c.emitir('listo', {}), false);
  assert.equal(lineas.length, 0);
});

// ── bot.js: arranque ───────────────────────────────────────────────────────────

function arrancar({ argv = [], env = { LUNE_MC_TOKEN: TOKEN }, requerir = null } = {}) {
  const entrada = new PassThrough();
  const lineas = [];
  const salidas = [];
  const timers = [];
  const r = main({
    argv, env, stdin: entrada, escribir: (l) => lineas.push(l), exit: (c) => salidas.push(c),
    requerir: requerir || ((m) => { throw Object.assign(new Error(`no instalado: ${m}`), { code: 'MODULE_NOT_FOUND' }); }),
    ahora: () => 7,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].fn = null; },
  });
  const mensajes = () => lineas.filter((l) => l.startsWith(MARCA)).map(parsear);
  return { r, entrada, lineas, salidas, timers, mensajes, env };
}

const CONFIG = { tipo: 'config', host: 'localhost', port: 25565, nick: 'Lune', dueno: 'Diego_01', persona: { nombre: 'Lune', prompt: 'Eres Lune.' } };

test('bot.js: sin LUNE_MC_TOKEN (o con uno raro) no arranca', () => {
  for (const env of [{}, { LUNE_MC_TOKEN: 'corto' }, { LUNE_MC_TOKEN: 'ZZZZZZZZZZZZZZZZZZZZ' }]) {
    const a = arrancar({ env });
    assert.equal(a.r, null);
    assert.deepEqual(a.salidas, [2]);
  }
});

test('bot.js: borra el token de su entorno y espera la configuración 10 s; si no llega, sale', () => {
  const a = arrancar();
  assert.equal(a.env.LUNE_MC_TOKEN, undefined);
  assert.equal(a.timers[0].ms, 10000);
  a.timers[0].fn();
  assert.deepEqual(a.mensajes().map((m) => [m.tipo, m.fatal]), [['error', true]]);
  assert.deepEqual(a.salidas, [1]);
});

test('bot.js: una configuración inválida → error con el motivo y sale(1)', async () => {
  const a = arrancar();
  a.entrada.write(JSON.stringify({ ...CONFIG, dueno: '' }) + '\n');
  await esperar();
  const [m] = a.mensajes();
  assert.equal(m.tipo, 'error');
  assert.match(m.mensaje, /dueño/);
  assert.deepEqual(a.salidas, [1]);
});

test('bot.js: antes de la configuración ignora las órdenes; «salir» sale limpio', async () => {
  const a = arrancar();
  a.entrada.write('{"tipo":"orden","id":"x","texto":"sigueme"}\n{"tipo":"salir"}\n');
  await esperar();
  assert.deepEqual(a.mensajes(), []);
  assert.deepEqual(a.salidas, [0]);
});

test('bot.js --probar: carga las dependencias, emite listo {probar} y sale sin conectarse', async () => {
  const pedidos = [];
  const a = arrancar({ argv: ['--probar'], requerir: (m) => { pedidos.push(m); return {}; } });
  a.entrada.write(JSON.stringify(CONFIG) + '\n');
  await esperar();
  assert.deepEqual(pedidos, ['mineflayer', 'mineflayer-pathfinder', 'minecraft-data', 'vec3']);
  const [m] = a.mensajes();
  assert.equal(m.tipo, 'listo');
  assert.equal(m.probar, true);
  assert.deepEqual(a.salidas, [0]);
  assert.equal(a.timers[0].fn, null, 'el temporizador de la configuración se cancela');
});

test('bot.js --probar sin dependencias instaladas → error que manda a instalar', async () => {
  const a = arrancar({ argv: ['--probar'] });
  a.entrada.write(JSON.stringify(CONFIG) + '\n');
  await esperar();
  const errores = a.mensajes().filter((m) => m.tipo === 'error');
  assert.match(errores[0].mensaje, /instálalo en Ajustes/);
  assert.deepEqual(a.salidas, [1]);
});

test('bot.js: sin mineflayer, conectar también dice que falta instalar', async () => {
  const a = arrancar();
  a.entrada.write(JSON.stringify(CONFIG) + '\n');
  await esperar();
  assert.match(a.mensajes()[0].mensaje, /instálalo en Ajustes/);
  assert.deepEqual(a.salidas, [1]);
});

test('textoMotivo y explicar: expulsiones en JSON de chat → texto limpio; online-mode avisado', () => {
  assert.equal(textoMotivo('{"text":"Kicked: ","extra":[{"text":"§cspam"}]}'), 'Kicked: spam');
  assert.equal(textoMotivo({ text: '/op yo' }), 'op yo');
  assert.match(explicar('Failed to verify username!'), /online-mode=false/);
  assert.match(explicar('connect ECONNREFUSED 127.0.0.1:25565', { host: 'localhost', port: 25565 }), /localhost:25565/);
});
