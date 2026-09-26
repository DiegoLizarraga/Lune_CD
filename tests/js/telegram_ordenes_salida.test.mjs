// tests/js/telegram_ordenes_salida.test.mjs — al cerrarse stdin (Lune paró el bot, p. ej.
// al cambiar de interfaz), el bot termina de mandar lo que estaba en vuelo («Se detuvo…»)
// antes de salir, con tope. Sin Telegram: responder y salir de mentira.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';

const { CanalOrdenes, TIPO_MENSAJE, ESPERA_SALIDA_MS } = await import('../../telegram-bot-or/ordenes.js');

const mensaje = (id, texto) => JSON.stringify({ tipo: TIPO_MENSAJE, id, texto });

test('al cerrarse stdin espera al envío en vuelo antes de salir', async () => {
  const pasos = [];
  let soltar;
  const c = new CanalOrdenes({
    token: 'tok', escribir: () => {}, nuevoId: () => 'o1',
    responder: (chatId, texto) => new Promise((r) => { soltar = () => { pasos.push(['enviado', chatId, texto]); r(); }; }),
  });
  const id = c.pedirOrden('abre youtube', 7);
  const entrada = new PassThrough();
  c.escuchar({ entrada, salirAlCerrar: true, salir: (codigo) => pasos.push(['salir', codigo]) });
  entrada.write(mensaje(id, 'Se detuvo la respuesta en el PC.') + '\n');
  entrada.end();
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(pasos, []);                 // aún mandando: no sale
  soltar();
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(pasos, [['enviado', 7, 'Se detuvo la respuesta en el PC.'], ['salir', 0]]);
});

test('sin nada en vuelo sale enseguida y con un envío colgado sale al tope', async () => {
  assert.ok(ESPERA_SALIDA_MS > 0 && ESPERA_SALIDA_MS < 3000);   // Lune espera 3 s al proceso
  const c = new CanalOrdenes({ token: 'tok', escribir: () => {} });
  const salidas = [];
  const entrada = new PassThrough();
  c.escuchar({ entrada, salirAlCerrar: true, salir: (codigo) => salidas.push(codigo) });
  entrada.end();
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(salidas, [0]);

  const colgado = new CanalOrdenes({ token: 'tok', escribir: () => {}, nuevoId: () => 'x',
    responder: () => new Promise(() => {}) });
  const oid = colgado.pedirOrden('hola', 1);
  colgado.recibirLinea(mensaje(oid, 'algo'));
  const t0 = Date.now();
  await colgado.terminarEnvios(40);
  assert.ok(Date.now() - t0 >= 35);
  assert.equal(colgado.enVuelo.size, 1);       // sigue colgado, pero ya no se espera
});
