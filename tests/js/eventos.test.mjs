// tests/js/eventos.test.mjs — cola de eventos página → Python (ui_web/lune_eventos.js).
// El archivo es un script clásico: se evalúa en un contexto vm con un `window` falso.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const RUTA = fileURLToPath(new URL('../../ui_web/lune_eventos.js', import.meta.url));
const CODIGO = readFileSync(RUTA, 'utf8');

function pagina(previo = {}) {
  const win = { ...previo };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(CODIGO, win, { filename: 'lune_eventos.js' });
  return win;
}

// Los objetos creados dentro del contexto vm tienen otro prototipo: se comparan como JSON.
const json = (x) => JSON.parse(JSON.stringify(x));

test('emitir encola {t, d, ts} y luneEventos devuelve JSON y vacía la cola', () => {
  const w = pagina();
  assert.equal(w.luneEventos(), '[]');
  const antes = Date.now();
  assert.equal(w.luneEmitir('caricia', { fuerza: 1 }), true);
  w.luneEventos.emitir('dormir', true);
  assert.equal(w.__luneEventos.length, 2);
  const lote = JSON.parse(w.luneEventos());
  assert.deepEqual(lote.map((e) => [e.t, e.d]), [['caricia', { fuerza: 1 }], ['dormir', true]]);
  assert.ok(lote[0].ts >= antes && lote[0].ts <= Date.now());
  assert.equal(w.__luneEventos.length, 0);
  assert.equal(w.luneEventos(), '[]');
});

test('como mucho 50 por vaciado, los más antiguos primero', () => {
  const w = pagina();
  for (let i = 0; i < 120; i++) w.luneEmitir('e' + i, i);
  const a = JSON.parse(w.luneEventos());
  assert.equal(a.length, 50);
  assert.equal(a[0].t, 'e0');
  assert.equal(a[49].t, 'e49');
  assert.equal(w.luneEventos.pendientes(), 70);
  const b = JSON.parse(w.luneEventos());
  assert.equal(b[0].t, 'e50');
  assert.equal(JSON.parse(w.luneEventos()).length, 20);
  assert.equal(w.luneEventos(), '[]');
});

test('con más de 200 se descartan los más viejos y se cuentan', () => {
  const w = pagina();
  for (let i = 0; i < 250; i++) w.luneEmitir('e' + i, null);
  assert.equal(w.__luneEventos.length, 200);
  assert.equal(w.__luneEventosPerdidos, 50);
  assert.equal(JSON.parse(w.luneEventos())[0].t, 'e50');
  // También si otro script empuja directamente a la cola sin pasar por emitir.
  for (let i = 0; i < 300; i++) w.__luneEventos.push({ t: 'x' + i, d: null, ts: 1 });
  const lote = JSON.parse(w.luneEventos());
  assert.equal(lote.length, 50);
  assert.equal(w.luneEventos.pendientes(), 150);
});

test('los datos se copian al emitir: undefined → null, circulares → texto, mutaciones posteriores no cuentan', () => {
  const w = pagina();
  const datos = { n: 1 };
  w.luneEmitir('a', datos);
  datos.n = 2;
  w.luneEmitir('b');
  const circular = { yo: null }; circular.yo = circular;
  w.luneEmitir('c', circular);
  w.luneEmitir('d', () => 1);
  assert.equal(w.luneEmitir(''), false, 'sin tipo no encola');
  assert.equal(w.luneEmitir(null), false);
  const lote = JSON.parse(w.luneEventos());
  assert.deepEqual(json(lote.map((e) => e.d)), [{ n: 1 }, null, '[object Object]', null]);
});

test('un evento no serializable empujado a mano no pierde el lote', () => {
  const w = pagina();
  const malo = { yo: null }; malo.yo = malo;
  w.luneEmitir('bueno', 1);
  w.__luneEventos.push({ t: 'malo', d: malo, ts: 5 });
  const lote = JSON.parse(w.luneEventos());
  assert.deepEqual(json(lote.map((e) => [e.t, e.d])), [['bueno', 1], ['malo', '[object Object]']]);
});

test('cargar el script otra vez no vacía la cola ni cambia su referencia', () => {
  const w = pagina();
  w.luneEmitir('antes', 1);
  const cola = w.__luneEventos;
  vm.runInContext(CODIGO, w);
  assert.equal(w.__luneEventos, cola);
  assert.equal(JSON.parse(w.luneEventos())[0].t, 'antes');
});

test('respeta una cola creada antes de cargar el script (p. ej. por lune_modulos.js)', () => {
  const w = pagina({ __luneEventos: [{ t: 'previo', d: null, ts: 1 }] });
  assert.equal(JSON.parse(w.luneEventos())[0].t, 'previo');
});
