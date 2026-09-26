// tests/js/idles.test.mjs — módulo 'idles' del VRM (ui_web/vrm/lune_idles.js):
// rueda sin repetir, fundido continuo, pesos, one-shots y microexpresiones.
// Sin DOM ni three: `node --test tests/js/idles.test.mjs`.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  instalar, VARIANTES, BOSTEZO, INDICE_ESTIRARSE, CONFIG_IDLES, espejar, envolvente, poseVariante,
} from '../../ui_web/vrm/lune_idles.js';
import { crearBus } from '../../ui_web/vrm/lune_modulos.js';

const DT = 1 / 60;
const RUEDA = VARIANTES.filter((v) => !v.unico).map((v) => v.nombre);

function difMax(a, b) {
  let m = 0;
  for (const h of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const pa = a[h] || [0, 0, 0], pb = b[h] || [0, 0, 0];
    for (let i = 0; i < 3; i++) m = Math.max(m, Math.abs((pa[i] || 0) - (pb[i] || 0)));
  }
  return m;
}
const magnitud = (p) => difMax(p, {});
function pasoMax(poses) {
  let m = 0;
  for (let i = 1; i < poses.length; i++) m = Math.max(m, difMax(poses[i - 1], poses[i]));
  return m;
}
const estBase = (extra = {}) => ({ gestoPeso: 0, dragPeso: 0, sleepBlend: 0, inactivo: 0, drag: false, dormida: false, hablando: false, cursor: { nx: 0, ny: 0 }, ...extra });

/** Avanza el módulo `seg` segundos desde t0; devuelve {t, poses?, exprs?}. */
function correr(mod, est, t0, seg, { guardar = false, alFrame, dt = DT } = {}) {
  let t = t0;
  const poses = [], exprs = [];
  const n = Math.round(seg / dt);
  for (let i = 0; i < n; i++) {
    t += dt;
    if (alFrame) alFrame(t, est, dt);
    const out = {};
    mod.pose(out, dt, t, est);
    const e = {};
    mod.expresiones((k, v) => { e[k] = Math.max(e[k] || 0, v); }, dt, t, est);
    if (guardar) { poses.push(out); exprs.push(e); }
  }
  return { t, poses, exprs };
}

test('hay 10 variantes; estirarse no entra en la rueda', () => {
  assert.equal(VARIANTES.length, 10);
  assert.equal(new Set(VARIANTES.map((v) => v.nombre)).size, 10);
  assert.equal(VARIANTES[INDICE_ESTIRARSE].nombre, 'estirarse');
  assert.equal(RUEDA.length, 9);
  assert.ok(!RUEDA.includes('estirarse'));
  for (const v of VARIANTES) {
    const p = poseVariante(v, 3.3, 1.2, 1);
    for (const h in p) for (const x of p[h]) assert.ok(Number.isFinite(x), `${v.nombre}.${h}`);
  }
});

test('la rueda no repite: tandas de 9 sin repetir, nunca dos seguidas, cada 8–14 s', () => {
  const mod = instalar({}, { semilla: 11 });
  correr(mod, estBase(), 0, 400);
  const h = mod.api.historial();
  assert.ok(h.length >= 30, `solo ${h.length} cambios`);
  for (let i = 1; i < h.length; i++) {
    assert.notEqual(h[i].nombre, h[i - 1].nombre, `repetida en ${i}`);
    const d = h[i].t - h[i - 1].t;
    assert.ok(d >= CONFIG_IDLES.cambioMin - DT && d <= CONFIG_IDLES.cambioMax + DT, `intervalo ${d}`);
  }
  for (let k = 0; k + 9 <= h.length; k += 9) {
    const tanda = h.slice(k, k + 9).map((x) => x.nombre);
    assert.deepEqual([...tanda].sort(), [...RUEDA].sort(), `tanda ${k / 9}`);
  }
  assert.ok(!h.some((x) => x.nombre === 'estirarse'), 'sin inactividad no se estira');
});

test('el fundido es continuo: el paso por frame es pequeño y baja con el dt (sin saltos)', () => {
  // Un salto no depende del dt; un fundido continuo sí: a 240 fps el paso es ~¼ del de 60.
  const a = correr(instalar({}, { semilla: 5 }), estBase(), 0, 200, { guardar: true });
  const b = correr(instalar({}, { semilla: 5 }), estBase(), 0, 200, { guardar: true, dt: 1 / 240 });
  const p60 = pasoMax(a.poses), p240 = pasoMax(b.poses);
  assert.ok(p60 < 0.08, `paso máximo a 60 fps ${p60}`);
  assert.ok(p240 < 0.025, `paso máximo a 240 fps ${p240}`);
  assert.ok(p240 < 0.35 * p60, `no escala con el dt: ${p60} → ${p240}`);
  const maxMag = Math.max(...a.poses.map(magnitud));
  assert.ok(maxMag > 0.5, `las variantes apenas mueven nada (${maxMag})`);
  // Nada aparece de golpe: el primer frame entra desde 0
  assert.ok(magnitud(a.poses[0]) < 0.01);
});

test('forzar una variante a mitad de un fundido tampoco salta', () => {
  const mod = instalar({}, { semilla: 2 });
  const est = estBase();
  let { t } = correr(mod, est, 0, 3);
  let prev = mod.pose({}, DT, t += DT, est);
  let maxPaso = 0;
  const forzar = [[3.4, 'tocarsePelo'], [3.8, 'manosEspalda'], [4.1, 9], [4.3, 'mirarseMano']];
  while (t < 8) {
    t += DT;
    for (const [tf, n] of forzar) if (Math.abs(t - tf) < DT / 2) assert.ok(mod.api.variante(n));
    const p = mod.pose({}, DT, t, est);
    maxPaso = Math.max(maxPaso, difMax(prev, p)); prev = p;
  }
  assert.ok(maxPaso < 0.08, `salto ${maxPaso}`);
  assert.equal(mod.api.variante(), 'mirarseMano');
  assert.equal(mod.api.variante('noExiste'), null);
  assert.equal(mod.api.variante(99), null);
});

test('peso × (1−0.7·gestoPeso)(1−dragPeso)(1−sleepBlend)', () => {
  const mk = () => instalar({}, { semilla: 9 });
  const a = mk(), b = mk(), c = mk(), d = mk();
  const ea = estBase(), eb = estBase({ gestoPeso: 1 }), ec = estBase({ dragPeso: 1 }), ed = estBase({ sleepBlend: 0.5, gestoPeso: 0.5 });
  let t = 0;
  for (let i = 0; i < 600; i++) {
    t += DT;
    const pa = a.pose({}, DT, t, ea), pb = b.pose({}, DT, t, eb), pc = c.pose({}, DT, t, ec), pd = d.pose({}, DT, t, ed);
    for (const h in pa) for (let k = 0; k < 3; k++) {
      assert.ok(Math.abs(pb[h][k] - 0.3 * pa[h][k]) < 1e-9, 'gestoPeso 1 → ×0.3');
      assert.ok(Math.abs(pd[h][k] - 0.65 * 0.5 * pa[h][k]) < 1e-9, 'gesto 0.5 y sueño 0.5 → ×0.325');
    }
    assert.ok(magnitud(pc) < 1e-12, 'colgada no hay idle');
  }
  assert.ok(Math.abs(a.api.estado().peso - 1) < 1e-9);
});

test('est.inh.idle (otros módulos) apaga el idle con suavidad', () => {
  const mod = instalar({}, { semilla: 4 });
  const est = estBase();
  let { t } = correr(mod, est, 0, 3);
  est.inh = { idle: 0 };
  const r = correr(mod, est, t, 3, { guardar: true });
  assert.ok(magnitud(r.poses.at(-1)) < 0.01);
  assert.ok(pasoMax(r.poses) < 0.08, `paso ${pasoMax(r.poses)}`);
});

test('set({activo:false}) funde a 0 en 1 s y la rueda se para; activo:true vuelve', () => {
  const mod = instalar({}, { semilla: 3 });
  const est = estBase();
  let { t } = correr(mod, est, 0, 4);
  assert.deepEqual(mod.api.set({ activo: false }).activo, false);
  const r = correr(mod, est, t, 1.05, { guardar: true });
  t = r.t;
  assert.ok(magnitud(r.poses.at(-1)) < 1e-9, 'apagado');
  const n = mod.api.historial().length;
  correr(mod, est, t, 30);
  assert.equal(mod.api.historial().length, n, 'apagado no rota');
  mod.api.set({ activo: true, cambioMin: 2, cambioMax: 3 });
  correr(mod, est, t + 30, 10);
  assert.ok(mod.api.historial().length > n + 2, 'encendido con intervalos nuevos');
  assert.equal(mod.api.set({ cambioMin: 5, cambioMax: 1 }).cambioMax, 5, 'max ≥ min');
});

test('estirarse tras 2 min sin actividad, una sola vez por periodo', () => {
  const mod = instalar({}, { semilla: 8 });
  const est = estBase({ inactivo: 119 });
  let { t } = correr(mod, est, 0, 2);
  assert.equal(mod.api.estado().unico, null);
  est.inactivo = 121;
  correr(mod, est, t, 0.1); t += 0.1;
  assert.equal(mod.api.estado().unico, 'estirarse');
  assert.equal(mod.ocupado(est), true);
  const r = correr(mod, est, t, 3.2, { guardar: true }); t = r.t;
  assert.ok(pasoMax(r.poses) < 0.1, `estirarse salta ${pasoMax(r.poses)}`);
  assert.ok(Math.max(...r.exprs.map((e) => e.blink || 0)) > 0.5, 'cierra los ojos al estirarse');
  assert.equal(mod.api.estado().unico, null);
  correr(mod, est, t, 20); t += 20;
  assert.equal(mod.api.historial().filter((h) => h.nombre === 'estirarse').length, 1, 'no se repite sin actividad');
  est.inactivo = 0; correr(mod, est, t, 0.5); t += 0.5;
  est.inactivo = 130; correr(mod, est, t, 0.5);
  assert.equal(mod.api.historial().filter((h) => h.nombre === 'estirarse').length, 2, 'se rearma con actividad');
});

test('sin est.inactivo la inactividad se deduce del cursor, el arrastre y el gesto', () => {
  const mod = instalar({}, { semilla: 1, config: { estirarTras: 10 } });
  const est = estBase(); delete est.inactivo;
  let { t } = correr(mod, est, 0, 9);
  assert.equal(mod.api.estado().unico, null);
  est.cursor = { nx: 0.3, ny: 0.1 };                 // se mueve: vuelve a contar
  correr(mod, est, t, 5); t += 5;
  assert.equal(mod.api.estado().unico, null);
  correr(mod, est, t, 6);
  assert.equal(mod.api.estado().unico, 'estirarse');
});

test('bostezo al empezar a dormir: se ve aunque sleepBlend llegue a 1', () => {
  const mod = instalar({}, { semilla: 6 });
  const est = estBase();
  let { t } = correr(mod, est, 0, 3);
  est.dormida = true;
  const r = correr(mod, est, t, 2.4, {
    guardar: true,
    alFrame: (_, e, dt) => { e.sleepBlend = Math.min(1, e.sleepBlend + dt); },
  });
  assert.equal(r.exprs.length, Math.round(2.4 / DT));
  const i = Math.round(1.2 / DT);                    // a mitad del bostezo, ya dormida del todo
  assert.equal(est.sleepBlend, 1);
  assert.ok(r.exprs[i].aa > 0.5, `boca ${r.exprs[i].aa}`);
  assert.ok(Math.abs(r.poses[i].rightLowerArm[2] - BOSTEZO.pose.rightLowerArm[2]) < 0.05, 'mano a la boca');
  assert.ok(pasoMax(r.poses) < 0.1, `bostezo salta ${pasoMax(r.poses)}`);
  correr(mod, est, r.t, 1);
  assert.equal(mod.api.estado().unico, null);
  assert.equal(mod.api.historial().filter((h) => h.nombre === 'bostezo').length, 1, 'uno por dormida');
});

test('hablando, el bostezo y el estiramiento no ponen expresión (boca y ojos son de la voz)', () => {
  for (const [api, nombre] of [['bostezar', 'bostezo'], ['estirar', 'estirarse']]) {
    const mod = instalar({}, { semilla: 5 });
    const est = estBase();
    let { t } = correr(mod, est, 0, 2);
    mod.api[api]();
    const r = correr(mod, est, t, 1.2, { guardar: true }); t = r.t;
    const e0 = r.exprs.at(-1);
    assert.ok(e0.blink > 0.5 && e0.aa > 0.3, `${nombre} callada: ojos y boca ${JSON.stringify(e0)}`);
    est.hablando = true;
    const rh = correr(mod, est, t, 0.6, { guardar: true });
    for (const e of rh.exprs) assert.ok(!(e.aa > 0) && !(e.blink > 0), `${nombre} hablando: ${JSON.stringify(e)}`);
    assert.equal(mod.api.estado().unico, nombre, 'la pose sigue');
  }
});

test('si la despiertan a mitad del bostezo, se funde fuera sin salto', () => {
  const mod = instalar({}, { semilla: 6 });
  const est = estBase();
  let { t } = correr(mod, est, 0, 3);
  est.dormida = true;
  const r = correr(mod, est, t, 0.6, { guardar: true, alFrame: (_, e, dt) => { e.sleepBlend = Math.min(1, e.sleepBlend + dt); } });
  t = r.t;
  assert.equal(mod.api.estado().unico, 'bostezo');
  est.dormida = false;                               // la voz (o un toque) la despierta
  const r2 = correr(mod, est, t, 1.0, { guardar: true, alFrame: (_, e, dt) => { e.sleepBlend = Math.max(0, e.sleepBlend - dt / 0.45); } });
  assert.equal(mod.api.estado().unico, null, 'el bostezo se suelta al despertar');
  assert.equal(mod.ocupado(est), false, 'y ya terminó de fundirse');
  assert.ok(pasoMax([r.poses.at(-1), ...r2.poses]) < 0.1, `salto ${pasoMax([r.poses.at(-1), ...r2.poses])}`);
  assert.ok(!(r2.exprs.at(-1).aa > 0), 'sin la boca del bostezo');
});

test('con el modelo cargado ya dormida no bosteza; al volver a dormirse, sí', () => {
  const est = estBase({ dormida: true, sleepBlend: 1 });
  const mod = instalar({ estado: () => est }, { semilla: 3 });
  mod.alCargar();
  correr(mod, est, 0, 3);
  const bostezos = () => mod.api.historial().filter((h) => h.nombre === 'bostezo').length;
  assert.equal(bostezos(), 0);
  Object.assign(est, { dormida: false, sleepBlend: 0 });
  correr(mod, est, 3, 3);
  est.dormida = true;
  correr(mod, est, 6, 1);
  assert.equal(bostezos(), 1);
});

test('un one-shot que sustituye a otro a medias se funde (sin salto)', () => {
  const pasos = (dt) => {
    const mod = instalar({}, { semilla: 12 });
    const est = estBase();
    let { t } = correr(mod, est, 0, 2, { dt });
    mod.api.estirar();
    const r1 = correr(mod, est, t, 1.5, { guardar: true, dt }); t = r1.t;
    mod.api.bostezar();
    const r2 = correr(mod, est, t, 1.5, { guardar: true, dt });
    return pasoMax([r1.poses.at(-1), ...r2.poses]);
  };
  const p60 = pasos(1 / 60), p240 = pasos(1 / 240);
  assert.ok(p60 < 0.12, `paso a 60 fps ${p60}`);
  assert.ok(p240 < 0.35 * p60, `no escala con el dt (salto): ${p60} → ${p240}`);
});

test('microexpresiones cada 7–13 s, nunca hablando', () => {
  const mod = instalar({}, { semilla: 21 });
  const r = correr(mod, estBase(), 0, 60, { guardar: true });
  const inicios = [];
  let activo = false;
  r.exprs.forEach((e, i) => {
    const on = (e.ee || 0) > 0.01 || ((e.blink || 0) > 0.01 && (e.blink || 0) <= 0.25 + 1e-9);
    if (on && !activo) inicios.push(i * DT);
    activo = on;
  });
  assert.ok(inicios.length >= 3, `microexpresiones: ${inicios.length}`);
  for (let i = 1; i < inicios.length; i++) {
    const d = inicios[i] - inicios[i - 1];
    assert.ok(d >= 7 - 0.1 && d <= 13 + 2, `separación ${d}`);
  }
  assert.ok(Math.max(...r.exprs.map((e) => e.happy || 0)) <= 0.25 + 1e-9);
  const hab = instalar({}, { semilla: 21 });
  const rh = correr(hab, estBase({ hablando: true }), 0, 60, { guardar: true });
  assert.ok(rh.exprs.every((e) => !(e.ee > 0) && !(e.blink > 0)), 'hablando no hay microexpresiones');
});

test('ctx.tieneExpr: sin "blink" entrecierra con blinkLeft/blinkRight', () => {
  const mod = instalar({ tieneExpr: (n) => n !== 'blink' }, { semilla: 3 });
  mod.api.estirar();
  const r = correr(mod, estBase(), 0, 1.5, { guardar: true });
  const e = r.exprs.at(-1);
  assert.equal(e.blink, undefined);
  assert.ok(e.blinkLeft > 0.3 && e.blinkRight > 0.3);
});

test('espejar y envolvente', () => {
  assert.deepEqual(espejar({ leftUpperArm: [0.1, 0.2, 0.3], head: [0.4, 0.5, 0.6] }),
    { rightUpperArm: [0.1, -0.2, -0.3], head: [0.4, -0.5, -0.6] });
  assert.equal(envolvente(0, 1, 1, 1), 0);
  assert.equal(envolvente(0.5, 1, 1, 1), 0.5);
  assert.equal(envolvente(1.5, 1, 1, 1), 1);
  assert.equal(envolvente(2.5, 1, 1, 1), 0.5);
  assert.equal(envolvente(3, 1, 1, 1), 0);
});

test('se registra en el bus y responde por api', () => {
  const bus = crearBus({ emitir: () => {} });
  const mod = bus.registrar(instalar);
  assert.equal(mod.nombre, 'idles');
  const out = {};
  for (let i = 1; i <= 90; i++) bus.llamar('pose', out, DT, i * DT, estBase());
  assert.ok(RUEDA.includes(bus.api('idles', 'variante')));
  assert.equal(bus.api('idles', 'variante', 'tararear'), 'tararear');
  assert.equal(bus.api('idles', 'set', { activo: false }).activo, false);
  assert.equal(bus.activo('idles'), true, 'ningún hook ha fallado');
});
