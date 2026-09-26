// tests/js/anim_baile.test.mjs — módulo 'baileAnim' de la mascota animada
// (ui_web/anim/lune_anim_baile.js, cortes 5 y 6): translateY −6..0 px, giro ±4° alterno,
// aplastado en el golpe, todo por el registro (el módulo no escribe style.transform),
// clip happy con una capa de emoción, el arrastre lo corta y dormida no baila.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { instalar, paso, NOMBRE, ORDEN, PARAMS_BAILE_ANIM } from '../../ui_web/anim/lune_anim_baile.js';
import { emocionEfectiva } from '../../ui_web/anim/lune_anim_video.js';
import { crearElemento } from './dom_falso.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_ritmo.js', import.meta.url), 'utf8'), { filename: 'lune_ritmo.js' });
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

test('paso(): giro alterno ±4°, sube entre pulsos (−6..0 px) y aplasta en el golpe', () => {
  assert.equal(NOMBRE, 'baileAnim');
  assert.equal(ORDEN, 40);
  let maxG = 0, minY = 0, maxY = -Infinity;
  for (let b = 0; b < 8; b += 0.01) {
    for (const e of [0, 0.5, 1, NaN, 7]) {
      const s = paso(b, e);
      for (const v of Object.values(s)) assert.ok(Number.isFinite(v));
      maxG = Math.max(maxG, Math.abs(s.grados));
      minY = Math.min(minY, s.dy); maxY = Math.max(maxY, s.dy);
      assert.ok(s.sy <= 1 && s.sx >= 1);
    }
  }
  cerca(maxG, 4, 1e-9, 'tope ±4°');
  cerca(minY, -6, 1e-6, '−6 px');
  assert.ok(maxY <= 0, 'nunca baja de su sitio');
  assert.ok(paso(0, 1).grados > 0 && paso(1, 1).grados < 0, 'un pulso a cada lado');
  cerca(paso(0, 1).dy, 0, 1e-12, 'en el pulso, abajo');
  cerca(paso(0.5, 1).dy, -6, 1e-12, 'a mitad, arriba');
  assert.ok(paso(0, 1).sy < 0.97 && Math.abs(paso(0.5, 1).sy - 1) < 1e-6, 'aplasta en el golpe');
  assert.ok(Math.abs(paso(0, 0).grados) < Math.abs(paso(0, 1).grados), 'la energía da amplitud');
});

/** Registro con el stage falso y un reloj que avanza a mano. */
function registro(opciones = {}) {
  const stage = crearElemento('div', 'stage');
  const eventos = [];
  let ms = 0;
  const reg = crearRegistroAnim({ stage, raf: () => 0, caf: () => {}, ahora: () => ms, emitir: (t, d) => eventos.push([t, d]) });
  const mod = reg.registrar((ctx) => instalar(ctx, opciones));
  reg.paso(ms);
  const correr = (seg, fn = null) => {
    for (let i = 0, n = Math.round(seg * 60); i < n; i++) { ms += 1000 / 60; reg.paso(ms); if (fn) fn(); }
  };
  return { reg, mod, stage, eventos, correr };
}
const giros = (tr) => [...String(tr || '').matchAll(/rotate\((-?[\d.]+)deg\)/g)].map((m) => Number(m[1]));

test('el registro compone la transformación: giro ≤ ±6°, sube y baja, y el módulo no toca style', () => {
  // El módulo solo añade piezas: con un stage cuyo style anota escrituras, pose/tick no escriben.
  const escrituras = [];
  const style = new Proxy({}, { set(o, k, v) { escrituras.push(k); o[k] = v; return true; } });
  const est = { capasEmocion: {} };
  const suelto = instalar({ stage: { style }, estado: () => est });
  suelto.api.bailar(true);
  for (let i = 0; i < 30; i++) { suelto.tick(1 / 60, i / 60, est); suelto.pose({ transform: [], filtro: [], opacidad: 1 }); }
  assert.deepEqual(escrituras, [], 'nada de style.transform directo');

  const { mod, stage, eventos, correr, reg } = registro();
  mod.api.bailar(true, { estilo: 'rebote' });
  assert.deepEqual(eventos, [['baile', { on: true, estilo: 'rebote' }]]);
  const vistos = [], alturas = [];
  let alguno = false;
  correr(4, () => {
    const tr = stage.style.transform;
    if (tr) alguno = true;
    vistos.push(...giros(tr));
    for (const m of String(tr || '').matchAll(/translate\((-?[\d.]+)px, (-?[\d.]+)px\)/g)) {
      if (Number(m[1]) === 0) alturas.push(Number(m[2]));   // mover(0, dy); los pivotes llevan %
    }
  });
  assert.ok(alguno, 'hay transformación');
  assert.equal(stage.style.transformOrigin, '0 0', 'la pone el registro');
  assert.ok(vistos.length > 0);
  assert.ok(Math.max(...vistos.map(Math.abs)) <= 6 + 1e-9, `giro ${Math.max(...vistos)}`);
  assert.ok(Math.max(...vistos) > 2 && Math.min(...vistos) < -2, 'a los dos lados');
  assert.ok(alturas.length && Math.min(...alturas) < -4 && Math.max(...alturas) <= 0, `sube hasta −6 px (${Math.min(...alturas)})`);
  assert.equal(reg.est.baile, true);
});

test('capa happy mientras baila; el arrastre lo corta, dormida no baila y al parar se funde', () => {
  const { mod, correr, reg, stage } = registro();
  const est = reg.est;
  mod.api.bailar(true);
  assert.equal(emocionEfectiva('normal', est.capasEmocion), 'happy', 'clip happy');
  assert.equal(est.capasEmocion.baile.prioridad, PARAMS_BAILE_ANIM.prioridad);
  correr(0.2);
  cerca(mod.api.estado().peso, 1 - Math.exp(-1), 0.02, 'entra con suav 5');
  correr(2);
  assert.ok(mod.api.estado().peso > 0.99);
  reg.estado({ drag: true });
  correr(0.6);
  assert.equal(mod.api.estado().peso, 0, 'arrastrarla lo corta');
  reg.estado({ drag: false });
  correr(2);
  assert.ok(mod.api.estado().peso > 0.99);
  reg.estado({ dormida: true });
  correr(1.5);
  assert.equal(mod.api.estado().peso, 0);
  reg.estado({ dormida: false });
  correr(2);
  mod.api.bailar(false);
  assert.equal(emocionEfectiva('sad', est.capasEmocion), 'sad', 'vuelve la emoción base');
  correr(0.2);
  cerca(mod.api.estado().peso, Math.exp(-1.6), 0.02, 'sale con suav 8');
  correr(1.5);
  assert.equal(mod.api.estado().peso, 0);
  assert.equal(mod.ocupado(est), false);
  assert.equal(est.baile, false);
  assert.equal(giros(stage.style.transform).length, 0, 'sin giro al acabar');
});

test('el pulso de Python llega en el siguiente tick; notas en cada golpe con partículas', () => {
  const golpes = [];
  const { mod, correr } = registro({ alGolpe: (e) => golpes.push(e) });
  mod.api.bailar(true, { particulas: true });
  assert.equal(mod.api.pulso(90, 0, 0.8), true);
  assert.equal(mod.api.pulso(0, 0, 0), false);
  correr(4);
  assert.equal(mod.api.estado().bpm, 90);
  assert.ok(golpes.length >= 5 && golpes.length <= 7, `≈6 golpes a 90 BPM en 4 s (${golpes.length})`);
  golpes.length = 0;
  mod.api.bailar(true, { particulas: false });
  correr(2);
  assert.equal(golpes.length, 0);
});
