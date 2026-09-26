// tests/js/gestos.test.mjs — mezclador de gestos con fundidos por destino
// (ui_web/vrm/lune_gestos.js). Sin DOM ni three: `node --test tests/js/gestos.test.mjs`.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { crearMezcladorGestos, duracionFundido, TIEMPOS_FUNDIDO } from '../../ui_web/vrm/lune_gestos.js';
import { sumar } from '../../ui_web/vrm/lune_modulos.js';

const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

// Copia de algunos GESTOS de lune_vrm.js (no se puede importar: importa 'three').
const add = sumar;
const GESTOS = {
  happy:    { pose: { head: [-0.04, 0, 0.06], spine: [-0.03, 0, 0] }, bob: 0.012, dur: 0 },
  sad:      { pose: { head: [0.22, 0, 0], neck: [0.06, 0, 0], spine: [0.10, 0, 0], leftUpperArm: [0, 0, 0.08], rightUpperArm: [0, 0, -0.08] }, dur: 0 },
  angry:    { pose: { head: [0.08, 0, 0], spine: [0.08, 0, 0], leftUpperArm: [0, 0, 0.25], rightUpperArm: [0, 0, -0.25], leftLowerArm: [0, -0.5, 0], rightLowerArm: [0, 0.5, 0] }, dur: 0 },
  nervous:  { pose: { head: [0.06, 0, -0.08], leftUpperArm: [0, 0, 0.12], rightUpperArm: [0, 0, -0.12], leftLowerArm: [0, -0.5, 0.2], rightLowerArm: [0, 0.5, -0.2] }, dur: 0,
              fn: (t, o) => { add(o, 'head', 0, 0, 0.025 * Math.sin(t * 22)); } },
  laughing: { pose: { head: [-0.15, 0, 0], spine: [-0.04, 0, 0] }, dur: 0, bob: 0.02,
              fn: (t, o) => { add(o, 'spine', 0.035 * Math.sin(t * 2 * Math.PI * 4), 0, 0); add(o, 'upperChest', 0, 0.02 * Math.sin(t * 2 * Math.PI * 2), 0); } },
  bored:    { pose: { head: [0.12, 0, 0.16], neck: [0.05, 0, 0], spine: [0.10, 0, 0] }, dur: 0,
              fn: (t, o) => { add(o, 'head', 0, 0.12 * Math.sin(t * 0.5), 0); } },
  wave:     { pose: { rightUpperArm: [0, 0, -2.2], rightLowerArm: [0, 0, -1.1] }, dur: 2600, bob: 0.008 },
};

/** Máxima diferencia absoluta entre dos poses (unión de huesos; lo que falta vale 0). */
function difMax(a, b) {
  let m = 0;
  for (const h of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const pa = a[h] || [0, 0, 0], pb = b[h] || [0, 0, 0];
    for (let i = 0; i < 3; i++) m = Math.max(m, Math.abs((pa[i] || 0) - (pb[i] || 0)));
  }
  return m;
}
const poseEn = (mg, t) => mg.pose({}, t);

test('duraciones de fundido por destino y por origen', () => {
  assert.equal(duracionFundido('normal', 'happy'), 0.25);
  assert.equal(duracionFundido('happy', 'normal'), 0.5);
  assert.equal(duracionFundido('happy', 'sad'), 0.45);
  assert.equal(duracionFundido('angry', 'bored'), 0.45);
  assert.equal(duracionFundido('laughing', 'happy'), 1.0);
  assert.equal(duracionFundido('laughing', 'normal'), 1.0, 'manda la regla más lenta');
  assert.equal(TIEMPOS_FUNDIDO.defecto, 0.25);
  const mg = crearMezcladorGestos(GESTOS, null, { tiempos: { hacia: { angry: 0.1 } } });
  assert.equal(mg.duracion('normal', 'angry'), 0.1, 'se pueden sobrescribir');
  assert.equal(mg.duracion('happy', 'normal'), 0.5, 'y el resto se conserva');
  assert.equal(mg.cambiar('happy', 0), 0.25, 'cambiar devuelve la duración');
  assert.equal(mg.cambiar('normal', 1), 0.5);
});

test('la entrada es un smoothstep y al terminar queda la pose pura del gesto', () => {
  const mg = crearMezcladorGestos(GESTOS);
  mg.cambiar('angry', 10);
  cerca(mg.peso(10), 0, 1e-12);
  cerca(mg.peso(10 + 0.125), 0.5, 1e-9, 'a mitad de 0.25 s');
  cerca(mg.peso(10 + 0.0625), 0.15625, 1e-9, 'smoothstep(0.25)');
  const p = poseEn(mg, 11);
  assert.ok(difMax(p, GESTOS.angry.pose) < 1e-12);
  assert.equal(mg.peso(11), 1);
  assert.equal(mg.fundiendo(11), false);
  mg.cambiar('normal', 11);
  assert.equal(mg.fundiendo(11.2), true);
  assert.ok(difMax(poseEn(mg, 12), {}) < 1e-12, 'hacia normal todo acaba en 0');
  assert.equal(mg.peso(12), 0);
  assert.deepEqual(mg.capas(12), []);
});

test('cambiar de gesto a mitad no salta: 0 en el instante y < ε por frame', () => {
  const mg = crearMezcladorGestos(GESTOS);
  const dt = 1 / 60;
  // Cambios a mitad de fundido, incluidos gestos dinámicos y salir de laughing
  const cambios = new Map([[0, 'happy'], [0.1, 'angry'], [0.2, 'nervous'], [0.3, 'laughing'], [1.2, 'sad'], [1.5, 'bored'], [1.6, 'angry'], [2.0, 'normal'], [2.2, 'happy']]);
  const EPS = 0.06;                     // rad por frame a 60 fps (un salto directo angry↔normal es 0.5)
  let prev = poseEn(mg, 0), maxDif = 0, saltoEnCambio = 0;
  for (let i = 0; i <= Math.round(4 / dt); i++) {
    const t = +(i * dt).toFixed(6);
    for (const [tc, g] of cambios) {
      if (Math.abs(t - tc) < dt / 2) {
        const antes = poseEn(mg, t);
        mg.cambiar(g, t);
        saltoEnCambio = Math.max(saltoEnCambio, difMax(antes, poseEn(mg, t)));
      }
    }
    const p = poseEn(mg, t);
    maxDif = Math.max(maxDif, difMax(prev, p));
    prev = p;
  }
  assert.ok(saltoEnCambio < 1e-9, `salto en el instante del cambio: ${saltoEnCambio}`);
  assert.ok(maxDif < EPS, `máximo por frame ${maxDif} ≥ ${EPS}`);
  assert.ok(mg.peso(4) === 1 && mg.actual === 'happy');
});

test('sin mezclador (salto directo) la misma secuencia sí saltaría', () => {
  // Referencia para que el ε de arriba signifique algo.
  assert.ok(difMax(GESTOS.angry.pose, GESTOS.happy.pose) > 0.4);
});

test('las capas salientes suman ≤ 1 y se limpian al terminar el fundido', () => {
  const mg = crearMezcladorGestos(GESTOS, null, { maxCapas: 3 });
  let t = 0;
  for (const g of ['happy', 'angry', 'sad', 'nervous', 'bored', 'laughing', 'angry']) { mg.cambiar(g, t); t += 0.03; }
  const capas = mg.capas(t);
  assert.ok(capas.length <= 4, `capas: ${capas.length}`);          // 3 salientes + la actual
  const suma = capas.reduce((s, c) => s + c.peso, 0);
  assert.ok(suma <= 1 + 1e-9, `suma ${suma}`);
  mg.pose({}, t + 2);
  assert.deepEqual(mg.capas(t + 2).map((c) => c.nombre), ['angry']);
});

test('el mismo gesto persistente no reinicia; uno con dur (wave) sí, y vence', () => {
  const mg = crearMezcladorGestos(GESTOS);
  mg.cambiar('happy', 0);
  assert.equal(mg.cambiar('happy', 1), 0);
  assert.equal(mg.tLocal(2), 2, 'sigue contando desde el primero');
  mg.cambiar('wave', 3);
  assert.equal(mg.vencido(5), false);
  assert.equal(mg.vencido(5.7), true, 'wave dura 2.6 s');
  assert.ok(mg.cambiar('wave', 5.7) > 0, 'repetir wave vuelve a empezar');
  assert.equal(mg.vencido(6), false);
  mg.cambiar('normal', 9);
  assert.equal(mg.vencido(20), false, 'normal no vence');
});

test('dinamico() y el término fn siguen vivos en la capa saliente', () => {
  const mg = crearMezcladorGestos(GESTOS);
  mg.cambiar('laughing', 0);
  assert.equal(mg.dinamico(), true);
  mg.cambiar('normal', 2);
  assert.equal(mg.dinamico(), true, 'la risa sigue apagándose');
  // A mitad del fundido de 1 s la risa aún oscila (no está congelada)
  const a = poseEn(mg, 2.4).spine[0], b = poseEn(mg, 2.43).spine[0];
  assert.notEqual(a, b);
  mg.pose({}, 3.5);
  assert.equal(mg.dinamico(), false);
});

test('bob: sigue con suav(dt, 10), sin saltos, y vuelve a 0 con normal', () => {
  const mg = crearMezcladorGestos(GESTOS);
  const dt = 1 / 60;
  let y = 0, maxY = 0, maxPaso = 0;
  mg.cambiar('laughing', 0);
  for (let i = 1; i <= 180; i++) {
    const t = i * dt;
    const y2 = mg.bob(y, dt, t);
    maxPaso = Math.max(maxPaso, Math.abs(y2 - y)); y = y2; maxY = Math.max(maxY, y);
  }
  assert.ok(maxY > 0.005 && maxY <= 0.02, `bob máx ${maxY}`);
  assert.ok(maxPaso < 0.005, `paso máx ${maxPaso}`);
  mg.cambiar('normal', 3);
  for (let i = 1; i <= 240; i++) y = mg.bob(y, dt, 3 + i * dt);
  cerca(y, 0, 1e-4);
  assert.equal(mg.bob(NaN, dt, 10), 0, 'NaN no se propaga');
});

test('el multiplicador w escala la mezcla y el reloj se usa si no se pasa t', () => {
  let reloj = 0;
  const mg = crearMezcladorGestos(GESTOS, () => reloj);
  mg.cambiar('angry');
  reloj = 1;
  const p = mg.pose({}, undefined, 0.5);
  cerca(p.leftLowerArm[1], -0.25, 1e-12);
  assert.deepEqual(mg.pose({}, undefined, 0), {});
  mg.reiniciar('sad', 2);
  assert.equal(mg.peso(2), 1, 'reiniciar corta sin fundido');
  assert.equal(mg.actual, 'sad');
});

test('nombres desconocidos cuentan como "sin gesto"', () => {
  const mg = crearMezcladorGestos(GESTOS);
  mg.cambiar('angry', 0);
  mg.cambiar('sleeping', 1);
  assert.equal(mg.actual, 'sleeping');
  assert.equal(mg.gesto, null);
  mg.pose({}, 2);
  assert.equal(mg.peso(2), 0);
  mg.cambiar('__proto__', 3);
  assert.equal(mg.gesto, null);
});
