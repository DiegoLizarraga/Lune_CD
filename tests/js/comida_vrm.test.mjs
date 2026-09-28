// tests/js/comida_vrm.test.mjs — módulo 'comida' del VRM (ui_web/vrm/lune_comida.js, corte 8):
// beber = 'ou' ≤ 0.5 y 3 cabeceos a 1.4 Hz; comer = 'aa' ≤ 0.45 a 3 Hz durante 1.5 s;
// 'happy' ≤ 0.6; no toca los brazos; con la comida en la mano no hay caricia
// (inhibe {caricia: 0}) y est.comiendo. Con el motor de verdad y la página.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

import {
  montar, correr, quietaSinIdles, lienzoFalso, scriptsEnLinea, reescribirImports, aDataURL, DATA_MOTOR, UI,
  frames, cargas, crearVRMFalso,
} from './motor_vrm_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import {
  instalar, reaccionEn, envolvente, tipoValido, NOMBRE, ORDEN, PARAMS_COMIDA,
} from '../../ui_web/vrm/lune_comida.js';

const DT = 1 / 60;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

/** Máximos locales de una serie (con un umbral para no contar ruido). */
function picos(serie, umbral = 1e-4) {
  let n = 0;
  for (let i = 1; i < serie.length - 1; i++) if (serie[i] > umbral && serie[i] >= serie[i - 1] && serie[i] > serie[i + 1]) n++;
  return n;
}

test('reaccionEn: beber = ou ≤ 0.5 y 3 cabeceos de 0.08 rad; comer = aa ≤ 0.45 a 3 Hz en 1.5 s; happy ≤ 0.6', () => {
  assert.equal(NOMBRE, 'comida');
  assert.equal(ORDEN, 70);
  assert.equal(tipoValido('BEBER'), 'beber');
  assert.equal(tipoValido('x'), 'comer');
  const dur = 2.5;
  const cab = [], ou = [], aa = [], feliz = [];
  for (let t = 0; t < dur + 0.2; t += 0.005) {
    const b = reaccionEn('beber', t, dur), c = reaccionEn('comer', t, dur);
    cab.push(b.cabeza); ou.push(b.ou); aa.push(c.aa); feliz.push(Math.max(b.happy, c.happy));
    assert.equal(b.aa, 0); assert.equal(c.ou, 0); assert.equal(c.cabeza, 0, 'comer no cabecea');
    if (t > 1.5) assert.equal(c.aa, 0, 'mastica 1.5 s');
  }
  assert.ok(Math.max(...ou) <= PARAMS_COMIDA.ou + 1e-12 && Math.max(...ou) > 0.45);
  assert.equal(picos(cab), 3, '3 cabeceos');
  assert.ok(Math.max(...cab) <= 0.08 + 1e-12 && Math.max(...cab) > 0.07);
  assert.ok(Math.max(...aa) <= 0.45 + 1e-12 && Math.max(...aa) > 0.4);
  const n = picos(aa);
  assert.ok(n >= 4 && n <= 5, `≈3 Hz en 1.5 s (${n} picos)`);
  assert.ok(Math.max(...feliz) <= 0.6 + 1e-12 && Math.max(...feliz) > 0.55);
  assert.equal(envolvente(-0.1, dur), 0);
  assert.equal(envolvente(dur, dur), 0);
  cerca(envolvente(dur - 0.15, dur), 0.5, 1e-9, 'fundido de salida de 0.3 s');
});

function modulo() {
  const est = { comiendo: false };
  const mod = instalar({ estado: () => est });
  let t = 0;
  const caras = [];
  const pasos = (seg) => {
    let out = {};
    for (let i = 0, n = Math.round(seg / DT); i < n; i++) {
      t += DT;
      out = {};
      mod.pose(out, DT, t, est);
      mod.expresiones((nombre, v, modo) => caras.push([nombre, v, modo]), DT, t, est);
    }
    return out;
  };
  return { mod, est, pasos, caras };
}

test('el módulo: la reacción dura ms, solo toca la cabeza (nada de brazos) y pone las caras con "max"', () => {
  const { mod, est, pasos, caras } = modulo();
  assert.equal(mod.ocupado(), false);
  assert.equal(mod.api.comer('beber', 2500), true);
  assert.equal(est.comiendo, true, 'mientras reacciona');
  assert.equal(mod.ocupado(), true);
  const tocados = new Set();
  for (let i = 0; i < 150; i++) { const out = pasos(DT); Object.keys(out).forEach((h) => tocados.add(h)); }
  assert.deepEqual([...tocados], ['head'], 'solo la cabeza');
  assert.ok(caras.every(([, , modo]) => modo === 'max'));
  assert.ok(caras.some(([n]) => n === 'ou') && caras.some(([n]) => n === 'happy'));
  pasos(0.1);
  assert.equal(mod.ocupado(), false, 'acabó a los 2.5 s');
  assert.equal(est.comiendo, false);
  caras.length = 0;
  pasos(0.2);
  assert.deepEqual(caras, [], 'sin reacción no pone caras');
  mod.api.comer('comer', 50);                       // ms mínimos: 100
  pasos(0.2);
  assert.equal(mod.ocupado(), false);
});

test('activa(on): inhibe la caricia y marca est.comiendo', () => {
  const { mod, est, pasos } = modulo();
  assert.deepEqual(mod.inhibe(est), {});
  mod.api.activa(true);
  assert.deepEqual(mod.inhibe(est), { caricia: 0 });
  pasos(0.1);
  assert.equal(est.comiendo, true);
  assert.equal(mod.api.estado().activa, true);
  mod.api.activa(false);
  pasos(0.1);
  assert.equal(est.comiendo, false);
  assert.deepEqual(mod.inhibe(est), {});
});

test('en el motor: beber pone ou y happy, cabecea, no cambia los brazos y la caricia queda a 0 con la comida en la mano', () => {
  for (const version of ['1', '0']) {
    const { m, vrm, est } = montar({ version });
    quietaSinIdles(m);
    const brazos = () => ['leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm'].map((h) => {
      const r = vrm.huesos[h].rotation; return [r.x, r.y, r.z];
    });
    const antes = brazos();
    const mod = m.registrar(instalar);
    assert.equal(mod.nombre, 'comida');
    m.mod('comida', 'activa', true);
    correr(0.1);
    assert.equal(est.inh.caricia, 0, 'sin caricia con la comida');
    assert.equal(est.comiendo, true);
    m.mod('comida', 'comer', 'beber', 2500);
    let ou = 0, feliz = 0, cab = 0;
    correr(2.4, null, () => {
      ou = Math.max(ou, vrm.valores.ou || 0); feliz = Math.max(feliz, vrm.valores.happy || 0);
      cab = Math.max(cab, Math.abs(vrm.huesos.head.rotation.x));
    });
    assert.ok(ou > 0.4 && ou <= 0.5 + 1e-9, `ou ${ou}`);
    assert.ok(feliz >= 0.55, `happy ${feliz}`);
    assert.ok(cab > 0.05, 'cabecea');
    assert.deepEqual(brazos(), antes, `VRM ${version}: los brazos, igual`);
    m.mod('comida', 'activa', false);
    correr(0.5);
    assert.equal(est.inh.caricia, 1);
    assert.equal(est.comiendo, false);
    m.destruir();
  }
});

test('companion_vrm.html: luneComer/luneComidaActiva antes y después del módulo; se registra al usarse', async () => {
  const body = crearElemento('body');
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(body);
  doc.body = body;
  globalThis.document = doc;
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=1' };
  const { html, scripts } = scriptsEnLinea('companion_vrm.html');
  assert.ok(html.includes("import('./vrm/lune_comida.js').catch("), 'módulo opcional');
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion_vrm.html' });
  assert.equal(globalThis.luneComidaActiva(true), false, 'pendiente');
  assert.equal(globalThis.luneComer('comer', 2500), false);
  frames.length = 0;
  await import(aDataURL(reescribirImports(scripts[1].codigo, new URL('companion_vrm.html', UI), { './vrm/lune_vrm.js': DATA_MOTOR }) + '\n// comida'));
  const mascota = globalThis.luneMascota;
  try {
    assert.ok(mascota.bus.lista().includes('comida'));
    assert.equal(mascota.bus.lista().includes('sentarse'), false, 'sentarse no se registra si no se usa');
    const s = globalThis.luneMod('comida', 'estado');
    assert.equal(s.activa, true);
    assert.equal(s.reaccion, 'comer', 'la reacción pendiente se repitió');
    const vrm = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    correr(0.5);
    assert.equal(globalThis.luneComer('beber', 1000), true);
    assert.equal(globalThis.luneComidaActiva(false), true);
    assert.equal(globalThis.luneMod('comida', 'estado').activa, false);
  } finally {
    try { mascota.destruir(); } catch (_) { /* sigue */ }
  }
});
