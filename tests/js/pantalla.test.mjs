// tests/js/pantalla.test.mjs — ui_web/lune_pantalla.js (cortes 5 y 6): la clase de pantalla
// grande según la fase y el salvapantallas (fondo oscuro y reloj que cuenta solo mientras se ve).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearElemento, crearDocumento } from './dom_falso.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_pantalla.js', import.meta.url), 'utf8'), { filename: 'lune_pantalla.js' });
const { LunePantalla } = globalThis;

function montar(fecha = new Date(2026, 8, 26, 7, 5, 0)) {
  const body = crearElemento('body');
  const doc = crearDocumento(body);
  doc.body = body;
  let ahora = fecha;
  const intervalos = new Map();
  let sig = 1;
  const p = LunePantalla.crear({
    doc, ahora: () => ahora,
    setInterval: (f, ms) => { intervalos.set(sig, { f, ms }); return sig++; },
    clearInterval: (id) => { intervalos.delete(id); },
  });
  return { p, body, doc, intervalos, poner: (d) => { ahora = d; }, tic: () => { for (const x of intervalos.values()) x.f(); } };
}

test('horaTexto y diaTexto en español con ceros', () => {
  const d = new Date(2026, 8, 26, 7, 5);
  assert.equal(LunePantalla.horaTexto(d), '07:05');
  assert.equal(LunePantalla.diaTexto(d), 'sábado 26');
});

test('body.lune-grande solo mientras la ventana es la del monitor', () => {
  const { p, body } = montar();
  const vistas = [];
  for (const f of ['glide', 'entrar', 'salir', 'volver', 'fin']) {
    p.fase(f);
    vistas.push(body.classList.contains('lune-grande'));
  }
  assert.deepEqual(vistas, [false, true, true, false, false]);
  p.fase('entrar');
  p.fase('patata');                                   // desconocida: no cambia nada
  assert.equal(body.classList.contains('lune-grande'), true);
  p.fase('fin');
  assert.equal(p.estado().grande, false);
});

test('salvapantallas: fondo oscuro y reloj que se actualiza cada segundo; al salir se para', () => {
  const { p, body, doc, intervalos, poner, tic } = montar();
  p.salvapantallas(true, { fondo: true, reloj: true });
  assert.equal(body.classList.contains('lune-salva'), true);
  assert.equal(body.classList.contains('lune-salva-fondo'), true);
  const reloj = doc.getElementById('lune-reloj');
  assert.ok(reloj && reloj.classList.contains('on'));
  assert.equal(reloj.querySelector('.hora').textContent, '07:05');
  assert.equal(reloj.querySelector('.dia').textContent, 'sábado 26');
  assert.equal(reloj.htmlCrudo, undefined, 'como texto');
  assert.equal(intervalos.size, 1);
  assert.equal([...intervalos.values()][0].ms, 1000);
  poner(new Date(2026, 8, 26, 23, 41, 0));
  tic();
  assert.equal(reloj.querySelector('.hora').textContent, '23:41');
  assert.equal(p.estado().hora, '23:41');
  p.salvapantallas(false);
  assert.equal(body.classList.contains('lune-salva'), false);
  assert.equal(body.classList.contains('lune-salva-fondo'), false);
  assert.equal(reloj.classList.contains('on'), false);
  assert.equal(intervalos.size, 0, 'el reloj deja de contar');
  // Sin fondo ni reloj
  p.salvapantallas(true, { fondo: false, reloj: false });
  assert.equal(body.classList.contains('lune-salva'), true);
  assert.equal(body.classList.contains('lune-salva-fondo'), false);
  assert.equal(intervalos.size, 0);
  assert.deepEqual(p.estado(), { grande: false, salva: true, fondo: false, reloj: false, hora: '23:41' });
  // Dos veces seguidas no crea dos relojes ni dos intervalos
  p.salvapantallas(true); p.salvapantallas(true);
  assert.equal(intervalos.size, 1);
  assert.equal(doc.creados.filter((e) => e.id === 'lune-reloj').length, 1);
});

test('sin DOM no rompe', () => {
  const p = LunePantalla.crear({ doc: null, setInterval: () => 1, clearInterval: () => {} });
  assert.equal(p.fase('entrar'), true);
  assert.equal(p.salvapantallas(true), true);
  assert.equal(p.salvapantallas(false), false);
});
