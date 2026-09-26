// tests/js/alarma.test.mjs — ui_web/lune_alarma.js (cortes 5 y 6): la burbuja roja de la
// alarma sale a los 3 s y se escribe a 35 c/s, siempre como texto; null la quita.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearElemento, crearDocumento, crearTemporizador } from './dom_falso.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_alarma.js', import.meta.url), 'utf8'), { filename: 'lune_alarma.js' });
const { LuneAlarma } = globalThis;

function montar() {
  const body = crearElemento('body');
  const doc = crearDocumento(body);
  doc.body = body;
  const tm = crearTemporizador();
  const a = LuneAlarma.crear({ doc, setTimeout: tm.setTimeout, clearTimeout: tm.clearTimeout });
  return { a, tm, body, doc };
}

test('constantes de Mate-Engine: 3 s de retraso y 35 caracteres por segundo', () => {
  assert.equal(LuneAlarma.RETRASO_MS, 3000);
  assert.equal(LuneAlarma.CPS, 35);
});

test('a los 3 s aparece y escribe a 35 c/s hasta el final', () => {
  const { a, tm, doc } = montar();
  const texto = 'x'.repeat(70);
  assert.equal(a.mostrar(texto), true);
  const el = doc.getElementById('lune-alarma');
  assert.ok(el, 'crea la burbuja en <body>');
  assert.equal(el.getAttribute('role'), 'alert');
  assert.equal(el.classList.contains('on'), false);
  tm.avanzar(2999);
  assert.equal(a.visible, false);
  assert.equal(a.texto, '', 'nada antes de los 3 s');
  tm.avanzar(1);
  assert.equal(a.visible, true);
  assert.equal(el.classList.contains('on'), true);
  assert.equal(a.texto.length, 1, 'la primera letra al aparecer');
  tm.avanzar(1000);
  assert.ok(Math.abs(a.texto.length - 36) <= 1, `≈35 letras en 1 s (${a.texto.length})`);
  assert.equal(a.completo, false);
  tm.avanzar(1000);
  assert.equal(a.texto, texto);
  assert.equal(a.completo, true);
  assert.equal(tm.pendientes(), 0, 'al acabar no deja temporizadores');
});

test('el texto va con textContent (sin innerHTML) y los emojis enteros', () => {
  const { a, tm, doc } = montar();
  const trampa = '<img src=x onerror="alert(1)"> ⏰🎉';
  a.mostrar(trampa, { retrasoMs: 0, cps: 1000 });
  tm.avanzar(1000);
  const el = doc.getElementById('lune-alarma');
  const txt = el.querySelector('.txt');
  assert.equal(txt.textContent, trampa);
  assert.equal(el.htmlCrudo, undefined);
  assert.equal(txt.htmlCrudo, undefined);
  assert.ok(!doc.creados.some((e) => e.tagName === 'IMG'));
  assert.equal(el.querySelector('.quien').textContent, '⏰ Alarma');
  // letra a letra no parte el emoji: cada paso es un texto válido
  const b = montar();
  const vistos = [];
  b.a.mostrar('🎉ab', { retrasoMs: 0, cps: 10 });
  vistos.push(b.a.texto);
  for (let i = 0; i < 3; i++) { b.tm.avanzar(100); vistos.push(b.a.texto); }
  assert.deepEqual(vistos, ['🎉', '🎉a', '🎉ab', '🎉ab']);
});

test('null / ocultar la quita y cancela lo pendiente; una nueva sustituye a la anterior', () => {
  const { a, tm, doc } = montar();
  a.mostrar('primera');
  tm.avanzar(3100);
  assert.equal(a.visible, true);
  assert.equal(a.ocultar(), true);
  const el = doc.getElementById('lune-alarma');
  assert.equal(el.classList.contains('on'), false);
  assert.equal(a.texto, '');
  assert.equal(tm.pendientes(), 0);
  assert.equal(a.ocultar(), false, 'ya no había');
  // Una segunda antes de que salga la primera: gana la segunda, con su propio retraso
  a.mostrar('uno');
  tm.avanzar(2000);
  a.mostrar('dos', { retrasoMs: 500, cps: 5 });
  tm.avanzar(600);
  assert.equal(a.texto, 'd', 'a los 500 ms la primera; luego una cada 200 ms');
  tm.avanzar(500);
  assert.equal(a.texto, 'dos');
  assert.equal(doc.creados.filter((e) => e.id === 'lune-alarma').length, 1, 'una sola burbuja');
  // Vacía → 'Alarma'; espacios colapsados y recorte
  a.mostrar('   ', { retrasoMs: 0, cps: 1000 });
  tm.avanzar(100);
  assert.equal(a.texto, 'Alarma');
  a.mostrar('a\n\n  b', { retrasoMs: 0, cps: 1000 });
  tm.avanzar(100);
  assert.equal(a.texto, 'a b');
  a.mostrar('z'.repeat(2000), { retrasoMs: 0, cps: 1000 });
  tm.avanzar(5000);
  assert.equal(a.texto.length, LuneAlarma.MAX_TEXTO);
});

test('sin documento no rompe', () => {
  const a = LuneAlarma.crear({ doc: null, setTimeout: () => 1, clearTimeout: () => {} });
  assert.equal(a.mostrar('hola'), true);
  assert.equal(a.ocultar(), true);
});
