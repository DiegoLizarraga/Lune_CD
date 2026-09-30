// tests/js/anim_comida.test.mjs — la reacción de la asistente ANIMADA al comer
// (ui_web/anim/lune_anim_comida.js, corte 8): capa de emoción 'comida' = happy con
// prioridad 60 (sobre dormir, bajo arrastre y mareo) durante ms, un rebote de escala
// ≤ ×1.04 por el registro (el módulo no escribe style), est.comiendo y la página.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { instalar, escalaRebote, NOMBRE, ORDEN, PARAMS_COMIDA_ANIM } from '../../ui_web/anim/lune_anim_comida.js';
import { emocionEfectiva, fijarCapa, PRIORIDAD_CAPA } from '../../ui_web/anim/lune_anim_video.js';
import { crearElemento, crearDocumento } from './dom_falso.mjs';

const UI = new URL('../../ui_web/', import.meta.url);
const escalas = (tr) => [...String(tr || '').matchAll(/scale\(([\d.]+), ([\d.]+)\)/g)].map((m) => Number(m[2]));

test('escalaRebote: de 1 a 1.04 y vuelta en 0.35 s', () => {
  assert.equal(NOMBRE, 'comidaAnim');
  assert.equal(ORDEN, 70);
  let max = 0;
  for (let t = -0.1; t < 0.6; t += 0.005) {
    const s = escalaRebote(t);
    assert.ok(s >= 1 && s <= 1.04 + 1e-12, `${t}: ${s}`);
    max = Math.max(max, s);
  }
  assert.ok(max > 1.039);
  assert.equal(escalaRebote(0.35), 1);
  assert.equal(escalaRebote(NaN), 1);
});

function registro() {
  const escrituras = [];
  const stage = crearElemento('div', 'stage');
  stage.style = new Proxy({}, { set(o, k, v) { escrituras.push([k, v]); o[k] = v; return true; } });
  let ms = 0;
  const reg = crearRegistroAnim({ stage, raf: () => 0, caf: () => {}, ahora: () => ms, emitir: () => {} });
  const mod = reg.registrar(instalar);
  reg.paso(ms);
  const correr = (seg, fn = null) => {
    for (let i = 0, n = Math.round(seg * 60); i < n; i++) { ms += 1000 / 60; reg.paso(ms); if (fn) fn(); }
  };
  return { reg, mod, stage, escrituras, correr };
}

test('comer: capa comida = happy (prioridad 60) durante ms, rebote ≤ ×1.04 por el registro y luego se quita', () => {
  const { reg, mod, stage, escrituras, correr } = registro();
  assert.equal(mod.ocupado(), false);
  assert.equal(mod.api.comer('beber', 2000), true);
  assert.deepEqual(reg.est.capasEmocion.comida, { estado: 'happy', prioridad: PARAMS_COMIDA_ANIM.prioridad });
  assert.equal(PARAMS_COMIDA_ANIM.prioridad, 60);
  assert.equal(reg.est.comiendo, true);
  // prioridades: sobre dormir (40), bajo arrastre (80) y mareo (90)
  fijarCapa(reg.est, 'dormir', 'sleeping');
  assert.equal(emocionEfectiva('normal', reg.est.capasEmocion), 'happy');
  fijarCapa(reg.est, 'arrastre', 'nervous');
  assert.equal(emocionEfectiva('normal', reg.est.capasEmocion), 'nervous');
  assert.ok(PRIORIDAD_CAPA.arrastre > 60 && PRIORIDAD_CAPA.dormir < 60);
  delete reg.est.capasEmocion.arrastre; delete reg.est.capasEmocion.dormir;
  let max = 1;
  correr(0.5, () => { for (const s of escalas(stage.style.transform)) max = Math.max(max, s); });
  assert.ok(max > 1.03 && max <= 1.04 + 1e-9, `rebote ${max}`);
  assert.equal(stage.style.transform, '', 'acabado el rebote, sin piezas');
  assert.ok(escrituras.every(([k]) => ['transform', 'transformOrigin', 'filter', 'opacity'].includes(k)), 'solo el registro escribe');
  assert.equal(mod.ocupado(), true, 'la reacción sigue');
  correr(1.6);
  assert.equal(reg.est.capasEmocion.comida, undefined, 'a los 2 s se quita la capa');
  assert.equal(reg.est.comiendo, false);
  assert.equal(mod.ocupado(), false);
});

test('activa(on) marca est.comiendo; oculta (alDetener) la reacción acaba', () => {
  const { reg, mod } = registro();
  mod.api.activa(true);
  assert.equal(reg.est.comiendo, true);
  mod.api.comer('comer');
  reg.iniciar();
  reg.detener();
  assert.equal(reg.est.capasEmocion.comida, undefined);
  assert.equal(reg.est.comiendo, true, 'sigue con la comida en la mano');
  mod.api.activa(false);
  assert.equal(reg.est.comiendo, false);
});

test('companion.html: luneComer/luneComidaActiva antes y después del módulo; se registra al usarse', async () => {
  globalThis.window = globalThis;
  globalThis.requestAnimationFrame = () => 0;
  globalThis.cancelAnimationFrame = () => {};
  const body = crearElemento('body');
  body.appendChild(crearElemento('div', 'bubble')).appendChild(crearElemento('span', 'btxt'));
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(crearElemento('video', 'v'));
  const doc = crearDocumento(body);
  doc.body = body;
  stage.ownerDocument = doc;
  globalThis.document = doc;
  const html = readFileSync(new URL('companion.html', UI), 'utf8');
  assert.ok(html.includes("import('./anim/lune_anim_comida.js').catch("), 'módulo opcional');
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter((m) => !/\bsrc=/.test(m[1]) && m[2].trim()).map((m) => m[2]);
  vm.runInThisContext(scripts[0], { filename: 'companion.html' });
  assert.equal(globalThis.luneComidaActiva(true), false, 'pendiente');
  assert.equal(globalThis.luneComer('comer', 2500), false);
  const base = new URL('companion.html', UI);
  const codigo = scripts[1].replace(/from\s+'(\.[^']+)'/g, (m, esp) => `from '${new URL(esp, base).href}'`)
    .replace(/import\(\s*'(\.[^']+)'\s*\)/g, (m, esp) => `import('${new URL(esp, base).href}')`);
  await import('data:text/javascript;base64,' + Buffer.from(codigo + '\n// comida', 'utf8').toString('base64'));
  const reg = globalThis.luneAnim;
  try {
    assert.equal(globalThis.__luneVidaPendiente, null);
    assert.ok(reg.lista().includes('comidaAnim'));
    assert.equal(reg.lista().includes('sentarseAnim'), false, 'sentarse no se registra si no se usa');
    assert.equal(reg.est.comiendo, true);
    assert.equal(reg.est.capasEmocion.comida.estado, 'happy', 'la reacción pendiente se repitió');
    assert.equal(globalThis.luneComidaActiva(false), true);
    assert.equal(globalThis.luneComer('beber', 1000), true);
  } finally {
    globalThis.luneSetFPS(0);
  }
});
