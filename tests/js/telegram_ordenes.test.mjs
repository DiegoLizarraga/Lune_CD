// tests/js/telegram_ordenes.test.mjs — órdenes desde Telegram (telegram-bot-or/ordenes.js).
// Sin Telegram ni Lune: escribir/responder/reloj/ids de mentira y un stdin de mentira.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';

const oyentesAntes = process.stdin.listenerCount('data') + process.stdin.listenerCount('readable');
const {
  CanalOrdenes, MARCA, TIPO_MENSAJE, CADUCIDAD_MS, MAX_MENSAJE, lineaOrden, jsonAscii,
} = await import('../../telegram-bot-or/ordenes.js');

const esperar = () => new Promise((r) => setImmediate(r));

function canal(extra = {}) {
  const escritas = [];
  const enviados = [];
  let t = 1_000_000;
  let n = 0;
  const c = new CanalOrdenes({
    token: 'tok123',
    escribir: (l) => escritas.push(l),
    responder: async (chatId, texto) => { enviados.push([chatId, texto]); },
    ahora: () => t,
    nuevoId: () => `id${++n}`,
    ...extra,
  });
  return { c, escritas, enviados, avanzar: (ms) => { t += ms; } };
}

const mensaje = (id, texto, tipo = TIPO_MENSAJE) => JSON.stringify({ tipo, id, texto });

test('importar ordenes.js no tiene efectos: no escucha stdin', () => {
  assert.equal(process.stdin.listenerCount('data') + process.stdin.listenerCount('readable'), oyentesAntes);
});

test('pedirOrden escribe la línea marcada con el token y devuelve el id', () => {
  const { c, escritas } = canal();
  assert.equal(c.activo(), true);
  const id = c.pedirOrden('  abre youtube  ', 42);
  assert.equal(id, 'id1');
  assert.equal(escritas.length, 1);
  const [marca, token, ...resto] = escritas[0].split(' ');
  assert.equal(marca, MARCA);
  assert.equal(token, 'tok123');
  assert.deepEqual(JSON.parse(resto.join(' ')), { id: 'id1', texto: 'abre youtube', chat_id: 42 });
});

test('la línea va en ASCII: acentos y emoji como \\uXXXX', () => {
  const l = lineaOrden('t', { id: 'a', texto: 'ñandú 📱 «hola»', chat_id: 1 });
  assert.match(l, /^[\x20-\x7e]*$/);
  assert.equal(JSON.parse(l.split(' ').slice(2).join(' ')).texto, 'ñandú 📱 «hola»');
  assert.equal(JSON.parse(jsonAscii({ x: 'é' })).x, 'é');
});

test('sin token el canal está cerrado: ni escribe ni recuerda nada', () => {
  const { c, escritas } = canal({ token: '' });
  assert.equal(c.activo(), false);
  assert.equal(c.pedirOrden('abre youtube', 1), null);
  assert.deepEqual(escritas, []);
  assert.equal(c.pendientes.size, 0);
});

test('orden vacía o sin chat: no se manda', () => {
  const { c, escritas } = canal();
  assert.equal(c.pedirOrden('   ', 1), null);
  assert.equal(c.pedirOrden('abre youtube', undefined), null);
  assert.deepEqual(escritas, []);
});

test('orden:mensaje con un id conocido va a su chat (varias veces)', async () => {
  const { c, enviados } = canal();
  const a = c.pedirOrden('abre youtube', 42);
  const b = c.pedirOrden('estado del pc', 7);
  assert.equal(c.recibirLinea(mensaje(b, '✓ CPU 5% | RAM 40%')), true);
  assert.equal(c.recibirLinea(mensaje(a, 'Enviado; esperando tu permiso')), true);
  assert.equal(c.recibirLinea(mensaje(a, '✓ Abriendo Youtube...')), true);
  await esperar();
  assert.deepEqual(enviados, [
    [7, '✓ CPU 5% | RAM 40%'],
    [42, 'Enviado; esperando tu permiso'],
    [42, '✓ Abriendo Youtube...'],
  ]);
});

test('id desconocido, JSON roto, otro tipo o texto vacío se ignoran', async () => {
  const { c, enviados } = canal();
  const id = c.pedirOrden('abre youtube', 42);
  for (const linea of [
    mensaje('otro', 'hola'),
    '{no es json',
    '',
    mensaje(id, 'hola', 'orden:otra'),
    mensaje(id, '   '),
    JSON.stringify({ tipo: TIPO_MENSAJE, id: '../x', texto: 'hola' }),
    JSON.stringify({ tipo: TIPO_MENSAJE, id, texto: 5 }),
    JSON.stringify([TIPO_MENSAJE, id, 'hola']),
  ]) {
    assert.equal(c.recibirLinea(linea), false, linea);
  }
  await esperar();
  assert.deepEqual(enviados, []);
});

test('el mapa caduca a los 5 min sin noticias y cada mensaje lo renueva', async () => {
  const { c, enviados, avanzar } = canal();
  const id = c.pedirOrden('abre youtube', 42);
  avanzar(CADUCIDAD_MS - 1000);
  assert.equal(c.recibirLinea(mensaje(id, 'uno')), true);      // renueva
  avanzar(CADUCIDAD_MS - 1000);
  assert.equal(c.recibirLinea(mensaje(id, 'dos')), true);      // aún vale
  avanzar(CADUCIDAD_MS);
  assert.equal(c.recibirLinea(mensaje(id, 'tres')), false);    // caducada: se ignora
  assert.equal(c.pendientes.has(id), false);
  await esperar();
  assert.deepEqual(enviados.map(([, t]) => t), ['uno', 'dos']);
});

test('un texto larguísimo se recorta para Telegram', async () => {
  const { c, enviados } = canal();
  const id = c.pedirOrden('estado', 1);
  c.recibirLinea(mensaje(id, 'x'.repeat(MAX_MENSAJE + 500)));
  await esperar();
  assert.equal(enviados[0][1].length, MAX_MENSAJE);
  assert.ok(enviados[0][1].endsWith('…'));
});

test('si Telegram falla al responder, no revienta', async () => {
  const errores = [];
  const original = console.error;
  console.error = (...a) => errores.push(a.join(' '));
  try {
    const { c } = canal({ responder: async () => { throw new Error('sin red'); } });
    const id = c.pedirOrden('abre youtube', 1);
    assert.equal(c.recibirLinea(mensaje(id, 'hola')), true);
    await esperar(); await esperar();
  } finally {
    console.error = original;
  }
  assert.ok(errores.some((e) => e.includes('sin red')));
});

test('escuchar lee la entrada línea a línea y avisa al cerrarse', async () => {
  const { c, enviados } = canal();
  const id = c.pedirOrden('abre youtube', 42);
  const entrada = new PassThrough();
  let cerrado = false;
  c.escuchar({ entrada, alCerrar: () => { cerrado = true; } });
  entrada.write(mensaje(id, 'primero') + '\n' + mensaje('nadie', 'x') + '\r\n');
  entrada.write(mensaje(id, 'segundo').slice(0, 10));
  entrada.write(mensaje(id, 'segundo').slice(10) + '\n');
  entrada.end();
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(cerrado, true);
  assert.deepEqual(enviados, [[42, 'primero'], [42, 'segundo']]);
});
