// tests/js/anim_fisica.test.mjs — arrastre, toque y sueño de la asistente animada
// (ui_web/anim/lune_anim_fisica.js), solo y junto a lune_anim_video.js en el registro.
// Sin navegador: stage, vídeos, documento y temporizador falsos (dom_falso.mjs).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  PARAMS_FISICA, anguloObjetivo, anguloCSS, estironObjetivo, CaraArrastre, DetectorMareo,
  reboteToque, bamboleoMareo, instalar, publicar,
} from '../../ui_web/anim/lune_anim_fisica.js';
import { instalar as instalarVideo, CARPETA } from '../../ui_web/anim/lune_anim_video.js';
import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { crearElemento, crearDocumento, crearTemporizador } from './dom_falso.mjs';

const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const DT = 1 / 60;

/** Grados del rotate() de las piezas de transform (0 si no hay). */
function rotacion(out) {
  for (const p of out.transform) {
    const m = /rotate\((-?[\d.]+)deg\)/.exec(p);
    if (m) return Number(m[1]);
  }
  return 0;
}

function montar(params) {
  const stage = crearElemento('div', 'stage');
  const doc = crearDocumento(stage);
  const est = {};
  const eventos = [];
  const ctx = { stage, estado: () => est, emitir: (t, d) => eventos.push([t, d]) };
  const mod = instalar(ctx, { documento: doc, params });
  let t = 0;
  mod.tick(0, 0);
  const avanzar = (s, cada = null) => {
    const n = Math.round(s / DT);
    for (let i = 0; i < n; i++) {
      t += DT;
      if (cada) cada(t, i);
      mod.tick(DT, t);
    }
    return t;
  };
  const pose = () => { const out = { transform: [], filtro: [], opacidad: 1 }; mod.pose(out, DT, t, est); return out; };
  return { stage, doc, est, eventos, mod, avanzar, pose, ahora: () => t };
}

// ── Lógica pura ─────────────────────────────────────────────────────────────────

test('ángulo objetivo: −vx·0.0167 °/(px/s) recortado a ±6°', () => {
  assert.equal(PARAMS_FISICA.maxAngulo, 6);
  assert.equal(PARAMS_FISICA.frec, 0.9);
  assert.equal(PARAMS_FISICA.zeta, 0.5);
  cerca(anguloObjetivo(100), -1.67, 1e-9);
  cerca(anguloObjetivo(-200), 3.34, 1e-9);
  assert.equal(anguloObjetivo(0), 0);
  assert.ok(!Object.is(anguloObjetivo(0), -0));
  for (const vx of [360, 1000, 5000, 1e9]) {
    assert.equal(anguloObjetivo(vx), -6, `vx ${vx}`);
    assert.equal(anguloObjetivo(-vx), 6, `vx -${vx}`);
  }
  assert.equal(anguloObjetivo(NaN), 0);
  assert.equal(anguloObjetivo(1000, { ...PARAMS_FISICA, invertir: -1 }), 6);
  assert.equal(anguloObjetivo(1000, { ...PARAMS_FISICA, maxAngulo: 20 }), -16.7);
  // CSS: positivo = horario; moverla a la derecha → el cuerpo cuelga detrás (rotate +)
  assert.equal(anguloCSS(anguloObjetivo(300)), 5.01);
  assert.equal(anguloCSS(0), 0);
  assert.ok(!Object.is(anguloCSS(0), -0));
  // Estirón: subir (vy < 0) estira; limitado a ±2.5 %
  assert.ok(estironObjetivo(-500) > 0);
  assert.equal(estironObjetivo(-1e6), 0.025);
  assert.equal(estironObjetivo(1e6), -0.025);
});

test('cara de arrastre: surprised 0.4 s y luego nervous mientras dure', () => {
  const c = new CaraArrastre();
  assert.equal(c.actualizar(0, 0), null);                        // sin arrastre, nada
  assert.equal(c.iniciar(10), 'surprised');
  assert.equal(c.actualizar(10.2, 300), 'surprised');
  assert.equal(c.actualizar(10.39, 300), 'surprised');
  assert.equal(c.actualizar(10.4, 300), 'nervous');
  for (let t = 10.5; t < 20; t += 0.5) assert.equal(c.actualizar(t, 500), 'nervous');
  c.terminar();
  assert.equal(c.cara, null);
});

test('cara de arrastre: muy deprisa vuelve a surprised, con histéresis y 0.8 s por cara', () => {
  const c = new CaraArrastre();
  c.iniciar(0);
  assert.equal(c.actualizar(0.5, 300), 'nervous');
  assert.equal(c.actualizar(0.9, 2000), 'nervous');               // aún no pasaron 0.8 s
  assert.equal(c.actualizar(1.3, 2000), 'surprised');
  assert.equal(c.actualizar(1.5, 1200), 'surprised');             // 1200 > 1100: sigue rápida
  assert.equal(c.actualizar(2.0, 1000), 'surprised');             // < 1100, pero solo 0.7 s en esta cara
  assert.equal(c.actualizar(2.2, 1000), 'nervous');               // 0.9 s ≥ 0.8
});

test('mareo: 4 inversiones a > 800 px/s en 1.5 s sí; 3 no; las lentas no cuentan', () => {
  const agitar = (d, n, v = 1500, paso = 0.3) => {
    let dis = false;
    for (let i = 0; i <= n; i++) dis = d.muestra(i * paso, i % 2 ? -v : v, 0) || dis;
    return dis;
  };
  assert.equal(agitar(new DetectorMareo(), 3), false);            // 3 inversiones
  assert.equal(agitar(new DetectorMareo(), 4), true);             // 4 inversiones en 1.2 s
  assert.equal(agitar(new DetectorMareo(), 6, 600), false);       // demasiado lentas
  assert.equal(agitar(new DetectorMareo(), 4, 1500, 0.55), false); // 4 inversiones pero en 1.65 s
  // Enfriamiento de 10 s
  const d = new DetectorMareo();
  assert.equal(agitar(d, 4), true);
  let otra = false;
  for (let i = 0; i < 20; i++) otra = d.muestra(2 + i * 0.3, i % 2 ? -1500 : 1500, 0) || otra;
  assert.equal(otra, false);                                      // dentro del enfriamiento
  let tras = false;
  for (let i = 0; i < 8; i++) tras = d.muestra(12 + i * 0.3, i % 2 ? -1500 : 1500, 0) || tras;
  assert.equal(tras, true);
  // También en vertical
  const dv = new DetectorMareo();
  let v = false;
  for (let i = 0; i <= 4; i++) v = dv.muestra(i * 0.3, 0, i % 2 ? -1500 : 1500) || v;
  assert.equal(v, true);
});

test('rebote del toque y bamboleo del mareo: acotados y terminan', () => {
  assert.equal(reboteToque(-0.1), null);
  assert.equal(reboteToque(0.7), null);
  assert.equal(reboteToque(Infinity), null);
  const r = reboteToque(0.05);
  assert.ok(r.y < 0 && r.y > -5, `sube ${r.y}`);
  assert.ok(r.sy > 1 && r.sx < 1);
  for (let t = 0; t < 0.7; t += 0.01) assert.ok(Math.abs(reboteToque(t).y) <= 5);
  assert.equal(bamboleoMareo(2.5), 0);
  assert.equal(bamboleoMareo(-1), 0);
  for (let t = 0; t < 2.5; t += 0.05) assert.ok(Math.abs(bamboleoMareo(t)) <= 3);
});

// ── Módulo ──────────────────────────────────────────────────────────────────────

test('arrastre: capa surprised → nervous, evento arrastre on/off y soltar tras 0.3 s', () => {
  const { est, eventos, mod, avanzar } = montar();
  mod.api.drag(true, 0, 0);
  assert.equal(est.drag, true);
  assert.equal(est.capasEmocion.arrastre.estado, 'surprised');
  assert.deepEqual(eventos[0], ['arrastre', { on: true }]);
  const muestra = () => mod.api.drag(true, 0.3, 0);               // 300 px/s
  avanzar(0.35, muestra);
  assert.equal(est.capasEmocion.arrastre.estado, 'surprised');
  avanzar(0.1, muestra);
  assert.equal(est.capasEmocion.arrastre.estado, 'nervous');
  assert.equal(mod.api.estado().cara, 'nervous');
  avanzar(2, muestra);
  assert.equal(est.capasEmocion.arrastre.estado, 'nervous');

  mod.api.drag(false, 0, 0);
  assert.equal(est.drag, true);                                   // dura 0.3 s desde la última muestra
  avanzar(0.35);
  assert.equal(est.drag, false);
  assert.ok(!est.capasEmocion.arrastre);
  assert.deepEqual(eventos.filter(([t]) => t === 'arrastre').map(([, d]) => d.on), [true, false]);
});

test('arrastre: el balanceo nunca pasa de ±6° y vuelve a 0 al soltar', () => {
  const { mod, avanzar, pose } = montar();
  let max = 0;
  let signo = 0;
  mod.api.drag(true, 0, 0);
  avanzar(1.5, () => {
    mod.api.drag(true, 3, -2);                                    // 3000 px/s a la derecha, subiendo
    const r = rotacion(pose());
    max = Math.max(max, Math.abs(r));
    if (r) signo = Math.sign(r);
  });
  assert.ok(max > 5 && max <= 6, `máximo ${max}`);
  assert.equal(signo, 1);                                         // a la derecha → rotate(+)
  assert.ok(mod.ocupado());
  mod.api.drag(false, 0, 0);
  let min = 0;
  avanzar(6, () => { min = Math.min(min, rotacion(pose())); });
  assert.ok(min < 0, 'rebota al otro lado al soltar');
  assert.ok(Math.abs(rotacion(pose())) < 0.01);
  assert.ok(!mod.ocupado());
  // Hacia la izquierda, el signo contrario
  mod.api.drag(true, 0, 0);
  avanzar(1, () => { mod.api.drag(true, -3, 0); });
  assert.ok(rotacion(pose()) < 0 && rotacion(pose()) >= -6);
});

test('la velocidad caduca si Python deja de mandarla (ratón quieto con el botón pulsado)', () => {
  const { mod, avanzar, pose } = montar();
  mod.api.drag(true, 0, 0);
  avanzar(1, () => mod.api.drag(true, 2, 0));
  assert.ok(Math.abs(rotacion(pose())) > 3);
  mod.api.drag(true, 2, 0);                                       // última muestra; sigue arrastrando
  avanzar(5);
  assert.ok(mod.api.estado().drag);
  assert.ok(Math.abs(rotacion(pose())) < 0.05, `sin muestras vuelve a 0: ${rotacion(pose())}`);
});

test('mareo al agitarla: capa dizzy 2.5 s, evento mareo y enfriamiento', () => {
  const { est, eventos, mod, avanzar } = montar();
  mod.api.drag(true, 0, 0);
  avanzar(1.6, (t) => mod.api.drag(true, Math.floor(t / 0.15) % 2 ? -2 : 2, 0));
  assert.equal(eventos.filter(([t]) => t === 'mareo').length, 1);
  assert.equal(est.capasEmocion.mareo.estado, 'dizzy');
  assert.ok(mod.api.estado().mareo);
  mod.api.drag(false, 0, 0);
  avanzar(3);
  assert.ok(!est.capasEmocion.mareo);
  assert.equal(eventos.filter(([t]) => t === 'mareo').length, 1);
});

test('sueño: clase y capa, despierta al tocar o arrastrar; setEmocion como en el VRM', () => {
  const { stage, est, eventos, mod, avanzar, pose } = montar();
  assert.equal(mod.api.dormir(true), true);
  assert.equal(mod.api.dormir(true), false);                      // ya dormida
  assert.ok(stage.classList.contains('lune-dormida'));
  assert.ok(stage.querySelector('.lune-zzz'));
  assert.equal(est.capasEmocion.dormir.estado, 'sleeping');
  assert.equal(est.dormida, true);
  avanzar(2);
  const escalaY = pose().transform.find((p) => p.includes('scale(1, '));
  assert.ok(escalaY, 'respira dormida');
  mod.api.tocar();
  assert.ok(!stage.classList.contains('lune-dormida'));
  assert.ok(!est.capasEmocion.dormir);
  assert.deepEqual(eventos.map(([t]) => t), ['dormir', 'despertar']);
  avanzar(0.05);
  assert.ok(pose().transform.some((p) => p.startsWith('translate(0px, -')), 'minirrebote');

  mod.alEmocion('sleeping');
  assert.ok(est.dormida);
  mod.alEmocion('normal');                                        // normal no despierta
  assert.ok(est.dormida);
  mod.alEmocion('happy');
  assert.ok(!est.dormida);
  mod.alEmocion('sleeping');
  mod.api.drag(true, 0, 0);                                       // arrastrar despierta
  assert.ok(!est.dormida);
});

test('params: lista blanca de números; los textos (pivote) no se tocan', () => {
  const { mod, avanzar, pose } = montar();
  const p = mod.api.params({ maxAngulo: 3, pivoteX: '0%', foo: 1, frec: 'x' });
  assert.equal(p.maxAngulo, 3);
  assert.equal(p.pivoteX, '50%');
  assert.equal(p.frec, 0.9);
  assert.ok(!('foo' in p));
  mod.api.drag(true, 0, 0);
  avanzar(1, () => mod.api.drag(true, 5, 0));
  assert.ok(rotacion(pose()) <= 3);
});

test('publicar: luneDrag/luneTouch/luneSleep llaman al registro con la firma del VRM', () => {
  const llamadas = [];
  const reg = { api: (...a) => { llamadas.push(a); return true; } };
  const win = {};
  publicar(win, reg);
  win.luneDrag(1, 0.5, -0.2);
  win.luneTouch();
  win.luneSleep(0);
  assert.deepEqual(llamadas, [['fisica', 'drag', true, 0.5, -0.2], ['fisica', 'tocar'], ['fisica', 'dormir', false]]);
});

// ── Juntos en el registro: física + vídeo ───────────────────────────────────────

test('registro completo: al arrastrar se ve surprised y luego nervous; al soltar vuelve la emoción', () => {
  const stage = crearElemento('div', 'stage');
  const a = crearElemento('video', 'va');
  const b = crearElemento('video', 'vb');
  stage.appendChild(a); stage.appendChild(b);
  const doc = crearDocumento(stage);
  const tm = crearTemporizador();
  const eventos = [];
  const reg = crearRegistroAnim({
    stage, video: () => a, emitir: (t) => eventos.push(t), raf: () => 0, caf: () => {}, ahora: () => 0,
  });
  reg.registrar((ctx) => instalarVideo(ctx, { videos: [a, b], temporizador: tm, documento: doc, cargarJSON: async () => null }));
  reg.registrar((ctx) => instalar(ctx, { documento: doc }));
  assert.deepEqual(reg.lista(), ['video', 'fisica']);
  publicar(globalThis, reg);

  const src = (c) => `${CARPETA}lune-${c}.webm`;
  const listos = () => { for (const v of [a, b]) if (v.oyentes('canplay')) v.disparar('canplay'); };
  let ms = 0;
  const pasos = (s, cada) => {
    for (let i = 0; i < Math.round(s * 60); i++) {
      ms += 1000 / 60;
      if (cada) cada();
      reg.paso(ms);
      listos();
      tm.avanzar(1000 / 60);
    }
  };

  reg.emocion('happy');
  reg.paso(0);
  listos();
  pasos(0.5);
  assert.equal(reg.api('video', 'estado').clip, 'happy');

  globalThis.luneDrag(true, 0, 0);
  pasos(0.2, () => globalThis.luneDrag(true, 0.3, 0));
  assert.equal(reg.api('video', 'estado').clip, 'surprised');
  pasos(0.6, () => globalThis.luneDrag(true, 0.3, 0));
  assert.equal(reg.api('video', 'estado').clip, 'nervous');
  assert.ok(/rotate\(/.test(stage.style.transform), `transform del stage: ${stage.style.transform}`);
  const grados = Number(/rotate\((-?[\d.]+)deg\)/.exec(stage.style.transform)[1]);
  assert.ok(grados > 0 && grados <= 6, `${grados}`);
  assert.equal(stage.style.transformOrigin, '0 0');

  globalThis.luneDrag(false, 0, 0);
  pasos(1);
  assert.equal(reg.api('video', 'estado').clip, 'happy');
  assert.equal(reg.api('video', 'estado').src, src('happy'));

  globalThis.luneSleep(true);
  pasos(0.3);
  assert.equal(reg.api('video', 'estado').efectiva, 'sleeping');
  assert.ok(eventos.includes('dormir'));
  globalThis.luneTouch();
  pasos(0.8);
  assert.equal(reg.api('video', 'estado').clip, 'happy');
  delete globalThis.luneDrag; delete globalThis.luneTouch; delete globalThis.luneSleep;
});
