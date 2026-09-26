// tests/js/baile_proc.test.mjs — módulo 'baileProc' del VRM (ui_web/vrm/lune_baile_proc.js,
// cortes 5 y 6): 8 estilos puros y acotados, fundidos de entrada/salida y entre estilos,
// el arrastre lo corta, inhibe/ocupado, encuadre temporal, bote, notas… y, con el motor
// de verdad y matrices (VRM 1.0 y 0.x), los brazos nunca pasan de la horizontal salvo
// el golpe breve de brazos_arriba.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  cargarClasico, montar, correr, quietaSinIdles, vaciarCola, brazoMundo,
} from './motor_vrm_falso.mjs';
import {
  instalar, poseEstilo, desplazamiento, ESTILOS, NOMBRE, ORDEN, PARAMS_BAILE, estiloValido,
} from '../../ui_web/vrm/lune_baile_proc.js';
import { crearAleatorio } from '../../ui_web/vrm/lune_modulos.js';

cargarClasico('lune_ritmo.js');                 // LuneRitmo en el global, como en la página
const DT = 1 / 60;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

// ── Lógica pura ────────────────────────────────────────────────────────────────

test('8 estilos: poses finitas, acotadas y que se mueven con el pulso', () => {
  assert.deepEqual([...ESTILOS], ['rebote', 'vaiven', 'brazos_arriba', 'palmas', 'cadera', 'cabeceo', 'puno_alterno', 'paso_lateral']);
  assert.equal(NOMBRE, 'baileProc');
  assert.equal(ORDEN, 40);
  for (const est of ESTILOS) {
    let cambia = 0;
    let prev = null;
    for (let b = 0; b < 8; b += 0.05) {
      for (const e of [0, 0.5, 1]) {
        const p = poseEstilo(est, b, e, {});
        for (const [h, r] of Object.entries(p)) {
          for (const v of r) {
            assert.ok(Number.isFinite(v), `${est} ${h} no finito`);
            assert.ok(Math.abs(v) <= 1.8, `${est} ${h} = ${v}`);
          }
        }
        const d = desplazamiento(est, b, e);
        assert.ok(Math.abs(d.x) <= 0.03 && Math.abs(d.y) <= 0.03, `${est}: ${JSON.stringify(d)}`);
      }
      const p = poseEstilo(est, b, 1, {});
      if (prev) cambia = Math.max(cambia, ...Object.keys(p).map((h) => Math.max(...p[h].map((v, i) => Math.abs(v - ((prev[h] || [0, 0, 0])[i]))))));
      prev = p;
    }
    assert.ok(cambia > 0.005, `${est} se mueve (${cambia})`);
  }
  assert.deepEqual(poseEstilo('no_existe', 0.3, 1), poseEstilo('rebote', 0.3, 1), 'desconocido → rebote');
  assert.deepEqual(poseEstilo('rebote', NaN, NaN), poseEstilo('rebote', 0, 0.5), 'NaN no rompe');
  assert.equal(estiloValido(' Palmas '), 'palmas');
  assert.equal(estiloValido('constructor'), null);
});

test('más energía = más amplitud; el paso lateral va a los dos lados', () => {
  const amp = (e) => Math.max(...[0, 0.25, 0.5].map((b) => Math.abs(poseEstilo('rebote', b, e).head[0])));
  assert.ok(amp(1) > amp(0) * 1.5);
  const xs = [0, 1, 2, 3].map((b) => desplazamiento('paso_lateral', b, 1).x);
  assert.ok(xs[1] > 0.02 && xs[3] < -0.02 && Math.abs(xs[0]) < 1e-9, JSON.stringify(xs));
  assert.ok(desplazamiento('rebote', 0, 1).y < -0.02 && Math.abs(desplazamiento('rebote', 0.5, 1).y) < 1e-6, 'bote abajo en el pulso');
});

// ── Módulo con un ctx falso ────────────────────────────────────────────────────

function modulo(opciones = {}) {
  const eventos = [], encuadres = [];
  const scene = { position: { x: 0.1, y: 0, z: 0 } };
  const ctx = {
    emitir: (t, d) => eventos.push([t, d]),
    encuadrar: (modo, temporal) => { encuadres.push([modo, temporal]); return modo; },
    vrm: () => ({ scene }),
  };
  const mod = instalar(ctx, { aleatorio: crearAleatorio(5), ...opciones });
  const est = { drag: false, sleepBlend: 0, grande: false };
  let t = 0;
  const pasos = (seg, fn = null) => {
    let out = {};
    for (let i = 0, n = Math.round(seg / DT); i < n; i++) {
      t += DT;
      if (fn) fn(t);
      out = {};
      scene.position.y = 0;                          // animar() lo reescribe cada frame
      mod.pose(out, DT, t, est);
      mod.trasPose(DT, t, est);
    }
    return out;
  };
  return { mod, ctx, est, eventos, encuadres, scene, pasos, t: () => t };
}

test('entra con suav(5), sale con suav(8); inhibe, ocupado, cara y est.baile', () => {
  const { mod, est, eventos, encuadres, pasos } = modulo();
  assert.equal(mod.ocupado(est), false);
  assert.deepEqual(mod.inhibe(est), { idle: 1, seguimiento: 1 });
  mod.api.bailar(true, { estilo: 'cabeceo' });
  assert.deepEqual(encuadres, [['cuerpo', true]], 'encuadre de cuerpo entero, temporal');
  assert.deepEqual(eventos, [['baile', { on: true, estilo: 'cabeceo' }]]);
  assert.equal(mod.ocupado(est), true);
  pasos(0.2);
  cerca(mod.api.estado().peso, 1 - Math.exp(-1), 1e-6, 'suav 5');
  assert.equal(est.baile, true);
  pasos(3);
  assert.equal(mod.api.estado().peso, 1);
  assert.deepEqual(mod.inhibe(est), { idle: 0, seguimiento: 1 - PARAMS_BAILE.seguimiento });
  const caras = [];
  mod.expresiones((n, v, modo) => caras.push([n, v, modo]));
  assert.deepEqual(caras, [['happy', 0.3, 'max']]);
  mod.api.bailar(false);
  assert.deepEqual(eventos[1], ['baile', { on: false, estilo: 'cabeceo' }]);
  pasos(0.2);
  cerca(mod.api.estado().peso, Math.exp(-1.6), 1e-6, 'suav 8');
  assert.equal(encuadres.length, 1, 'el encuadre sigue mientras se funde');
  pasos(1.5);
  assert.equal(mod.api.estado().peso, 0);
  assert.equal(mod.ocupado(est), false);
  assert.equal(est.baile, false);
  assert.deepEqual(encuadres, [['cuerpo', true], [null, undefined]], 'al acabar vuelve al encuadre del usuario');
  const inh = mod.inhibe(est);
  assert.equal(inh.idle, 1); assert.equal(inh.seguimiento, 1);
  // Sin encuadre (barra lateral)
  const b = modulo({ encuadrar: false });
  b.mod.api.bailar(true); b.pasos(1); b.mod.api.bailar(false); b.pasos(2);
  assert.deepEqual(b.encuadres, []);
});

test('arrastrarla lo corta (peso 0) y vuelve al soltar; dormida o en grande no baila', () => {
  const { mod, est, pasos } = modulo();
  mod.api.bailar(true);
  pasos(2);
  est.drag = true;
  pasos(0.25);
  assert.ok(mod.api.estado().peso < Math.exp(-2.9), `corte rápido (${mod.api.estado().peso})`);
  pasos(1);
  assert.equal(mod.api.estado().peso, 0);
  assert.equal(mod.api.estado().activo, true, 'sigue bailando: al soltarla vuelve');
  est.drag = false;
  pasos(2);
  assert.ok(mod.api.estado().peso > 0.99);
  est.sleepBlend = 1;
  pasos(2);
  assert.equal(mod.api.estado().peso, 0);
  est.sleepBlend = 0; est.grande = true;
  pasos(2);
  assert.equal(mod.api.estado().peso, 0);
});

test('bote en scene.position.y y paso lateral en x que se deshace al acabar', () => {
  const { mod, scene, pasos } = modulo();
  mod.api.bailar(true, { estilo: 'rebote' });
  let minY = 0;
  pasos(3, () => { minY = Math.min(minY, scene.position.y); });
  assert.ok(minY < -0.015, `bota (${minY})`);
  mod.api.estilo('paso_lateral');
  const xs = [];
  pasos(6, () => xs.push(scene.position.x));
  assert.ok(Math.max(...xs) > 0.1 + 0.015 && Math.min(...xs) < 0.1 - 0.015, 'se desplaza a los dos lados');
  mod.api.bailar(false);
  pasos(3);
  cerca(scene.position.x, 0.1, 1e-9, 'x vuelve a donde estaba');
  assert.equal(scene.position.y, 0);
});

test('cambiar cada N s con 2 s de fundido (smoothstep), sin repetir estilo', () => {
  const { mod, pasos } = modulo();
  mod.api.bailar(true, { estilo: 'vaiven', cambiar: true, cambiarS: 5 });
  pasos(4.9);
  assert.equal(mod.api.estado().estilo, 'vaiven');
  pasos(0.2);
  const s = mod.api.estado();
  assert.notEqual(s.estilo, 'vaiven');
  assert.equal(s.previo, 'vaiven');
  pasos(1 - 0.1);
  cerca(mod.api.estado().mezcla, 0.5, 0.06, 'a mitad del fundido');
  pasos(1.2);
  assert.equal(mod.api.estado().previo, null);
  assert.equal(mod.api.estado().mezcla, 1);
  const vistos = new Set([s.estilo]);
  for (let i = 0; i < 7; i++) { pasos(5); vistos.add(mod.api.estado().estilo); }
  assert.ok(vistos.size >= 6, `recorre los estilos (${[...vistos]})`);
  // cambiar_s acotado y alias de Python
  mod.api.bailar(true, { cambiar_s: 1 });
  assert.equal(mod.api.estado().cambiarS, PARAMS_BAILE.cambiarMin);
});

test('el pulso de Python manda en el reloj y las notas salen en cada golpe si hay partículas', () => {
  const golpes = [];
  const { mod, pasos } = modulo({ alGolpe: (e) => golpes.push(e) });
  mod.api.bailar(true, { estilo: 'rebote', particulas: true });
  pasos(1);
  assert.equal(mod.api.pulso(90, 0.25, 0.9), true);
  pasos(4);
  const s = mod.api.estado();
  assert.equal(s.bpm, 90);
  assert.ok(s.energia > 0.85);
  assert.ok(golpes.length >= 6 && golpes.length <= 8, `≈6 golpes a 90 BPM en 4 s (${golpes.length})`);
  assert.equal(mod.api.pulso('x', 0, 0), false);
  golpes.length = 0;
  mod.api.bailar(true, { particulas: false });
  pasos(2);
  assert.equal(golpes.length, 0);
});

// ── Con el motor de verdad: brazos con matrices ────────────────────────────────

test('en el motor: los brazos no pasan de la horizontal (VRM 1.0 y 0.x); brazos_arriba solo un golpe breve', () => {
  for (const version of ['1', '0']) {
    const { m, vrm, est } = montar({ version });
    quietaSinIdles(m);
    const mod = m.registrar(instalar);
    assert.equal(mod.nombre, 'baileProc');
    assert.ok(m.bus.lista().includes('baileProc'));
    for (const estilo of ESTILOS) {
      m.mod('baileProc', 'bailar', true, { estilo });
      m.mod('baileProc', 'pulso', 120, 0, 1);
      correr(1.5);                                   // entra (y funde desde el anterior)
      assert.ok(m.mod('baileProc', 'estado').peso > 0.99, `${estilo}: bailando del todo`);
      cerca(est.inh.idle, 0, 0.01, 'el idle cede');
      let arriba = 0, racha = 0, maxRacha = 0, n = 0, maxY = -Infinity;
      correr(4, null, () => {                        // 8 pulsos a 120 BPM
        n++;
        let sube = false;
        for (const lado of ['left', 'right']) {
          const b = brazoMundo(vrm, lado, version);
          const y = Math.max(b.codo[1], b.mano[1]);
          maxY = Math.max(maxY, y);
          if (y > 0) sube = true;
          // hacia el centro solo por DELANTE del cuerpo (nada de atravesarlo)
          const haciaDentro = lado === 'left' ? -b.mano[0] : b.mano[0];
          if (haciaDentro > 0.3) assert.ok(b.mano[2] > 0.5, `${estilo} (VRM ${version}): mano ${lado} cruza por detrás (z ${b.mano[2].toFixed(2)})`);
        }
        if (sube) { arriba++; racha++; maxRacha = Math.max(maxRacha, racha); } else racha = 0;
      });
      if (estilo === 'brazos_arriba') {
        assert.ok(arriba > 0, 'brazos_arriba sí sube');
        assert.ok(arriba / n <= 0.2, `${estilo}: arriba el ${(100 * arriba / n).toFixed(0)} % del tiempo`);
        assert.ok(maxRacha / 60 <= 0.8, `${estilo}: ${maxRacha / 60} s seguidos arriba`);
      } else {
        assert.ok(maxY < -0.1, `${estilo} (VRM ${version}): codo o mano sobre el hombro (y = ${maxY.toFixed(3)})`);
      }
    }
    // el bote llega a la escena y se funde al parar
    m.mod('baileProc', 'bailar', true, { estilo: 'rebote' });
    correr(1);
    let minY = 0;
    correr(1, null, () => { minY = Math.min(minY, vrm.scene.position.y); });
    assert.ok(minY < -0.01, `bote (${minY})`);
    m.mod('baileProc', 'bailar', false);
    correr(2);
    assert.equal(m.mod('baileProc', 'estado').peso, 0);
    cerca(vrm.scene.position.x, 0, 1e-9);
    assert.equal(est.baile, false);
    // arrastrarla lo corta dentro del motor
    m.mod('baileProc', 'bailar', true);
    correr(1.5);
    m.drag(true, 1, 0);
    correr(1, () => m.drag(true, 1, 0));
    assert.equal(m.mod('baileProc', 'estado').peso, 0);
    m.drag(false, 0, 0);
    m.mod('baileProc', 'bailar', false);
    correr(1);
    const ev = vaciarCola().filter((e) => e.t === 'baile');
    assert.ok(ev.length >= 2 && ev.every((e) => typeof e.d.on === 'boolean'), JSON.stringify(ev.slice(0, 3)));
    m.destruir();
  }
});
