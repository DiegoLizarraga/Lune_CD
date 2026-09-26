// tests/js/ritmo.test.mjs — ui_web/lune_ritmo.js (cortes 5 y 6): el reloj del pulso que
// extrapola lo que manda Python (≤ 2 Hz) y las notas ♪ del baile.
// Script clásico: se carga en el global con vm, como en la página.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearElemento, crearDocumento, crearTemporizador } from './dom_falso.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_ritmo.js', import.meta.url), 'utf8'), { filename: 'lune_ritmo.js' });
const { LuneRitmo, LuneNotas } = globalThis;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const DT = 1 / 60;

test('LuneRitmo y LuneNotas cuelgan del global', () => {
  assert.equal(typeof LuneRitmo.crearReloj, 'function');
  assert.equal(typeof LuneNotas.crear, 'function');
  assert.equal(LuneRitmo.CORRECCION_MAX, 0.2);
  assert.deepEqual(LuneRitmo.normalizar(400, 1.25, 7), { bpm: 240, fase: 0.25, energia: 1 });
  assert.deepEqual(LuneRitmo.normalizar(10, -0.25, -1), { bpm: 40, fase: 0.75, energia: 0 });
  assert.equal(LuneRitmo.normalizar('x', 0, 0), null);
  assert.equal(LuneRitmo.normalizar(0, 0, 0), null);
});

test('sin medidas es un metrónomo continuo y marca cada pulso entero', () => {
  const r = LuneRitmo.crearReloj({ bpm: 120 });
  let t = 0, golpes = 0;
  r.avanzar(t);
  for (let i = 0; i < 600; i++) { t += DT; if (r.avanzar(t).golpe) golpes++; }
  const e = r.estado();
  cerca(e.pulsos, 20, 1e-6, '10 s a 120 BPM');
  assert.equal(golpes, 20);
  cerca(e.velocidad, 2, 1e-9);
  assert.ok(e.fase >= 0 && e.fase < 1);
});

test('la primera medida al empezar alinea de golpe; el bpm nuevo se adopta al momento', () => {
  const r = LuneRitmo.crearReloj();
  r.avanzar(0);
  assert.equal(r.pulso(90, 0.4, 0.8, 0.05), true);
  cerca(r.estado().fase, 0.4, 1e-9, 'alineado');
  assert.equal(r.estado().bpm, 90);
  for (let i = 1; i <= 60; i++) r.avanzar(0.05 + i / 60);
  cerca(r.estado().pulsos, 0.4 + 1.5, 1e-9, '1 s a 90 BPM = 1.5 pulsos');
  r.avanzar(10);
  cerca(r.estado().pulsos, 1.9 + 0.75, 1e-9, 'un hueco de ~9 s cuenta como 0.5 s (pestaña dormida)');
  assert.equal(r.pulso('nada', 0, 0, 1.1), false, 'una medida sin bpm no cuenta');
});

test('corrección de fase: continua y con la velocidad dentro de ±20 %', () => {
  const r = LuneRitmo.crearReloj({ bpm: 120 });
  let t = 0;
  r.avanzar(t);
  for (let i = 0; i < 60; i++) { t += DT; r.avanzar(t); }      // 1 s en marcha: ya no alinea de golpe
  // La música va 0.45 pulsos por delante de lo que cree el reloj
  const verdad = (tt) => (tt * 2 + 0.45);
  let previo = r.estado().pulsos, maxRel = 0, minRel = Infinity;
  for (let i = 0; i < 480; i++) {                              // 8 s, medidas a 2 Hz
    t += DT;
    if (i % 30 === 0) r.pulso(120, verdad(t) % 1, 0.7, t);
    const e = r.avanzar(t);
    const paso = e.pulsos - previo;
    previo = e.pulsos;
    assert.ok(paso > 0, 'nunca va hacia atrás');
    if (i % 30 !== 0) {                                        // el frame de la medida ya avanzó dentro de pulso()
      maxRel = Math.max(maxRel, paso / (2 * DT));
      minRel = Math.min(minRel, paso / (2 * DT));
    }
    assert.ok(e.velocidad <= 2 * 1.2 + 1e-9 && e.velocidad >= 2 * 0.8 - 1e-9, `velocidad ${e.velocidad}`);
  }
  assert.ok(maxRel <= 1.2 + 1e-9 && minRel >= 0.8 - 1e-9, `${minRel}..${maxRel}`);
  assert.ok(maxRel > 1.1, 'la corrección llegó a actuar');
  const err = Math.abs(((r.estado().pulsos - verdad(t)) % 1 + 1.5) % 1 - 0.5);
  assert.ok(err < 0.02, `el error de fase se comió (${err})`);
});

test('energía suavizada y reiniciar', () => {
  const r = LuneRitmo.crearReloj();
  r.avanzar(0);
  r.pulso(120, 0, 1, 0);
  let t = 0;
  for (let i = 0; i < 120; i++) { t += DT; r.avanzar(t); }
  assert.ok(r.estado().energia > 0.99);
  r.reiniciar();
  assert.equal(r.estado().pulsos, 0);
  assert.equal(r.estado().medidas, 0);
  assert.equal(r.metronomo(60), true);
  assert.equal(r.estado().bpm, 60);
});

test('LuneNotas: una nota por pulso (según la energía), como texto, con tope y que se va sola', () => {
  const raiz = crearElemento('body');
  const doc = crearDocumento(raiz);
  doc.body = raiz;
  raiz.removeChild = (c) => { raiz.children = raiz.children.filter((x) => x !== c); c.parentNode = null; };
  const tm = crearTemporizador();
  let azar = 0.1;
  const notas = LuneNotas.crear({ doc, aleatorio: () => azar, max: 3, vidaMs: 1500, setTimeout: tm.setTimeout, clearTimeout: tm.clearTimeout });
  const n = notas.golpe(1);
  const capa = doc.getElementById('lune-notas');
  assert.ok(capa && capa.className === 'lune-notas', 'crea su capa en <body>');
  assert.equal(capa.getAttribute('aria-hidden'), 'true');
  assert.ok(['♪', '♫'].includes(n.textContent));
  assert.equal(n.className, 'lune-nota');
  assert.equal(n.htmlCrudo, undefined, 'sin innerHTML');
  assert.match(n.style.props['--nota-x'], /%$/);
  assert.equal(n.style.props['--nota-dur'], '1.50s');
  capa.removeChild = (c) => { capa.children = capa.children.filter((x) => x !== c); c.parentNode = null; };
  notas.golpe(1); notas.golpe(1); notas.golpe(1);
  assert.equal(notas.cuantas, 3, 'tope de notas a la vez');
  assert.equal(capa.children.length, 3);
  azar = 0.95;
  assert.equal(notas.golpe(0.2), null, 'con poca energía no siempre sale');
  tm.avanzar(1600);
  assert.equal(notas.cuantas, 0, 'se quitan al acabar su animación');
  assert.equal(capa.children.length, 0);
  azar = 0.1;
  notas.golpe(1); notas.golpe(1);
  notas.limpiar();
  assert.equal(notas.cuantas, 0);
  assert.equal(tm.pendientes(), 0, 'limpiar cancela sus temporizadores');
});

test('LuneNotas sin documento no rompe', () => {
  const notas = LuneNotas.crear({ doc: null });
  assert.equal(notas.golpe(1), null);
  notas.limpiar();
});
