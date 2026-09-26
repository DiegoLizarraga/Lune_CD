// tests/js/movimiento.test.mjs — módulo 'movimiento' del VRM (ui_web/vrm/lune_movimiento.js):
// balanceo con los valores de la escena de Mate-Engine, extremidades con retraso (±35°),
// pose colgada, caras por velocidad, cara sostenida y mareo.
// Sin DOM ni three: `node --test tests/js/movimiento.test.mjs`.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  instalar, Balanceo, DetectorMareo, PARAMS_SWAY, PARAMS_MOVIMIENTO, POSE_COLGADA, GESTO_MAREO,
  poseColgada, triangulo,
} from '../../ui_web/vrm/lune_movimiento.js';
import { crearBus } from '../../ui_web/vrm/lune_modulos.js';

const DT = 1 / 60;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

function difMax(a, b) {
  let m = 0;
  for (const h of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const pa = a[h] || [0, 0, 0], pb = b[h] || [0, 0, 0];
    for (let i = 0; i < 3; i++) m = Math.max(m, Math.abs((pa[i] || 0) - (pb[i] || 0)));
  }
  return m;
}

/** Módulo con un emisor que apunta los eventos. */
function montar(ctxExtra = {}, opciones = { semilla: 7 }) {
  const eventos = [];
  const ctx = { emitir: (t, d) => eventos.push({ t, d }), ...ctxExtra };
  return { mod: instalar(ctx, opciones), eventos, ctx };
}
const estArrastre = (extra = {}) => ({ drag: true, dragPeso: 1, dragVx: 0, dragVy: 0, sleepBlend: 0, ...extra });

/** Corre el módulo; velocidad(t) → [vx, vy]. Devuelve {t, poses, exprs}. */
function correr(mod, est, t0, seg, velocidad = null, { guardar = false } = {}) {
  let t = t0;
  const poses = [], exprs = [];
  for (let i = 0, n = Math.round(seg / DT); i < n; i++) {
    t += DT;
    if (velocidad) { const [vx, vy] = velocidad(t); est.dragVx = vx; est.dragVy = vy || 0; }
    const out = {};
    mod.pose(out, DT, t, est);
    const e = {};
    mod.expresiones((k, v) => { e[k] = Math.max(e[k] || 0, v); }, DT, t, est);
    if (guardar) { poses.push(out); exprs.push(e); }
  }
  return { t, poses, exprs };
}

/** Agitar en X: `tramos` tramos alternos de `dur` s a ±v px/s → tramos−1 inversiones. */
const agitar = (t0, tramos, dur = 0.2, v = 1200) => (t) => {
  const k = Math.floor((t - t0) / dur);
  if (t < t0 || k >= tramos) return [0, 0];
  return [(k % 2 ? -1 : 1) * v, 0];
};

// ── Parámetros ─────────────────────────────────────────────────────────────────

test('PARAMS_SWAY son los de la escena de Mate-Engine', () => {
  assert.equal(PARAMS_SWAY.swayFrec, 0.75);
  assert.equal(PARAMS_SWAY.swayZeta, 0.5);
  assert.equal(PARAMS_SWAY.swayMaxZ, 45);
  assert.equal(PARAMS_SWAY.swayMaxX, 20);
  cerca(PARAMS_SWAY.swayGanH, 1 / 60, 1e-4, '1 °/(px/frame) a 60 fps');
  assert.equal(PARAMS_SWAY.swayGanH, PARAMS_SWAY.swayGanV);
  assert.equal(PARAMS_SWAY.extremidadesMax, 35);
  assert.equal(PARAMS_SWAY.extremidadesRetraso, 6);
  assert.equal(PARAMS_MOVIMIENTO.mareoInversiones, 4);
});

test('balanceo: régimen = v·ganancia, tope 45°, y el muelle sobrepasa (ζ 0.5)', () => {
  const b = new Balanceo();
  let max = 0;
  for (let i = 0; i < 600; i++) { b.paso(DT, true, 600, 0); max = Math.max(max, b.leanZ); }
  cerca(b.leanZ, 600 * 0.0167, 0.05, 'régimen');
  assert.ok(max > b.leanZ * 1.1, `sin sobrepaso: ${max}`);
  const c = new Balanceo();
  for (let i = 0; i < 600; i++) c.paso(DT, true, 9000, -9000);
  cerca(c.leanZ, 45, 0.05, 'tope Z');
  cerca(c.leanX, -20, 0.05, 'tope X');
  for (let i = 0; i < 900; i++) c.paso(DT, false, 9000, 9000);
  cerca(c.leanZ, 0, 0.05, 'sin arrastre vuelve a 0');
});

test('extremidades con retraso: nunca pasan de ±35° (y el ladeo sí pasa de 35)', () => {
  const b = new Balanceo();
  let maxLean = 0, maxExt = 0, t = 0;
  for (let i = 0; i < 1200; i++) {
    t += DT;
    const v = (Math.floor(t / 0.9) % 2 ? -1 : 1) * 20000;
    b.paso(DT, true, v, -v);
    maxLean = Math.max(maxLean, Math.abs(b.leanZ));
    for (const [aditivo, sgn] of [[1, 1], [1, -1], [2.5, 1]]) {
      const [x, z] = b.extremidad(aditivo, sgn);
      maxExt = Math.max(maxExt, Math.abs(x), Math.abs(z));
      assert.ok(Math.abs(x) <= 35 + 1e-9 && Math.abs(z) <= 35 + 1e-9, `extremidad ${x}, ${z}`);
    }
  }
  assert.ok(maxLean > 35, `el tope no llegó a actuar (${maxLean})`);
  cerca(maxExt, 35, 1e-9, 'se llega al tope');
  // Retraso: tras un escalón, limb va detrás de −lean
  const r = new Balanceo();
  r.paso(DT, true, 3000, 0); r.paso(DT, true, 3000, 0);
  assert.ok(Math.abs(r.limbZ) < Math.abs(r.leanZ));
  assert.ok(Math.sign(r.limbZ) === -Math.sign(r.leanZ));
  // Signo y aditivo
  for (let i = 0; i < 120; i++) r.paso(DT, true, 3000, 0);
  const [, z1] = r.extremidad(1, 1), [, z2] = r.extremidad(1, -1), [, z0] = r.extremidad(0, 1);
  assert.equal(z1, -z2);
  assert.ok(Object.is(z0, 0), 'aditivo 0 → 0 (sin -0)');
});

test('el módulo aplica ±35° a brazos y piernas también con ctx.PARAMS extremos', () => {
  const { mod } = montar({ PARAMS: { swayGanH: 0.05, swayMaxZ: 60, invertirBrazos: -1 } });
  const est = estArrastre();
  let maxB = 0, maxP = 0;
  correr(mod, est, 0, 8, (t) => [(Math.floor(t / 1.1) % 2 ? -1 : 1) * 5000, 0]);
  for (let i = 0; i < 300; i++) {
    const out = {};
    est.dragVx = (i % 80 < 40 ? 1 : -1) * 5000;
    mod.pose(out, DT, 8 + i * DT, est);
    const s = mod.api.estado();
    maxB = Math.max(maxB, ...s.brazos.map(Math.abs)); maxP = Math.max(maxP, ...s.piernas.map(Math.abs));
  }
  assert.ok(maxB <= 35 + 1e-9 && maxP <= 35 + 1e-9, `${maxB} / ${maxP}`);
  const s = mod.api.estado();
  assert.equal(Math.sign(s.brazos[1]), -Math.sign(s.piernas[1]), 'invertirBrazos = −1 invierte solo los brazos');
});

test('prioridad de parámetros: api.params > ctx.PARAMS > PARAMS_SWAY', () => {
  const ctx = { PARAMS: { swayGanH: 0.03 } };
  const { mod } = montar(ctx);
  const est = estArrastre();
  let { t } = correr(mod, est, 0, 10, () => [600, 0]);
  cerca(mod.api.estado().leanZ, 18, 0.1, 'ctx.PARAMS');
  assert.equal(mod.api.params({ swayGanH: 0.01, swayFrec: '1.5', basura: 3 }).swayGanH, 0.01);
  ({ t } = correr(mod, est, t, 10, () => [600, 0]));
  cerca(mod.api.estado().leanZ, 6, 0.1, 'api.params');
  assert.equal(mod.api.params().swayFrec, 1.5);
  assert.equal('basura' in mod.api.params(), false);
  mod.api.params('{"swayGanH": null}');
  assert.equal(mod.api.params().swayGanH, 0.03, 'null vuelve a ctx.PARAMS');
  ctx.PARAMS.swayGanH = 'x';
  assert.equal(mod.api.params().swayGanH, PARAMS_SWAY.swayGanH, 'lo no numérico cae al defecto');
});

// ── Mareo ──────────────────────────────────────────────────────────────────────

test('DetectorMareo: 4 inversiones en 1.5 s sí; 3 no', () => {
  const muestras = (det, tramos, dur = 0.2, v = 1000) => {
    let disparos = 0;
    for (let i = 0; i < tramos * dur * 60; i++) {
      const t = i / 60, k = Math.floor(t / dur);
      if (det.muestra((k % 2 ? -1 : 1) * v, 0, t)) disparos++;
    }
    return disparos;
  };
  assert.equal(muestras(new DetectorMareo(), 5), 1, '5 tramos = 4 inversiones');
  assert.equal(muestras(new DetectorMareo(), 4), 0, '4 tramos = 3 inversiones');
  assert.equal(muestras(new DetectorMareo(), 5, 0.55), 0, '4 inversiones en 1.65 s: no caben en la ventana');
  assert.equal(muestras(new DetectorMareo(), 5, 0.45), 1, '4 inversiones en 1.35 s: sí');
  assert.equal(muestras(new DetectorMareo(), 9, 0.2, 700), 0, 'por debajo de 800 px/s no cuenta');
});

test('DetectorMareo: cooldown de 10 s, ejes por separado y huecos lentos', () => {
  const det = new DetectorMareo();
  const serie = (t0, n, v = 1000, eje = 'x') => {
    let r = false;
    for (let k = 0; k < n; k++) {
      for (let i = 0; i < 12; i++) {
        const s = (k % 2 ? -1 : 1) * v;
        r = det.muestra(eje === 'x' ? s : 0, eje === 'y' ? s : (eje === 'xy' ? s : 0), t0 + (k * 12 + i) / 60) || r;
      }
    }
    return r;
  };
  assert.equal(serie(0, 5), true);
  assert.equal(det.disparo.eje, 'x');
  assert.equal(det.disparo.inversiones, 4);
  assert.equal(serie(5, 5), false, 'en cooldown');
  assert.equal(serie(11, 5, 1000, 'y'), true, 'pasado el cooldown, y en el eje Y');
  assert.equal(det.disparo.eje, 'y');
  const d2 = new DetectorMareo();
  assert.equal(serie(0, 3, 1000, 'xy'), false, 'en diagonal no cuenta doble (2+2 no son 4)');
  // Un tramo lento entre medias no rompe la cuenta (el signo se recuerda)
  const d3 = new DetectorMareo();
  let r = false, t = 0;
  for (const v of [1000, 0, -1000, 100, 1000, -300, -1000, 1000]) { for (let i = 0; i < 10; i++) { r = d3.muestra(v, 0, t) || r; t += 1 / 60; } }
  assert.equal(r, true, `inversiones ${d3.ultimas}`);
});

test('el módulo se marea con 4 inversiones (emite "mareo", 2.5 s) y no con 3', () => {
  const a = montar();
  const est = estArrastre();
  correr(a.mod, est, 0, 1.2, agitar(0, 5));
  assert.deepEqual(a.eventos.map((e) => e.t), ['mareo']);
  assert.deepEqual(a.eventos[0].d, { inversiones: 4, eje: 'x' });
  assert.equal(a.mod.api.estado().mareo, true);
  const r = correr(a.mod, est, 1.2, 1.3, null, { guardar: true });
  assert.ok(r.exprs.some((e) => (e.blink || 0) > 0.3), 'ojos entrecerrados');
  assert.ok(Math.max(...r.poses.map((p) => Math.abs(p.head[2] - POSE_COLGADA.head[2]))) > 0.02, 'cabeza en círculos');
  // Se disparó con la 4.ª inversión (t ≈ 0.8 s): sigue a los 3.2 s y termina a los 3.3 s
  correr(a.mod, est, 2.5, 0.7);
  assert.equal(a.mod.api.estado().mareo, true, 'aún mareada a los 3.2 s');
  correr(a.mod, est, 3.2, 0.2);
  assert.equal(a.mod.api.estado().mareo, false, 'dura 2.5 s');
  correr(a.mod, est, 3.4, 1.2, agitar(3.4, 5));
  assert.equal(a.eventos.length, 1, 'cooldown de 10 s');

  const b = montar();
  correr(b.mod, estArrastre(), 0, 2, agitar(0, 4));
  assert.equal(b.eventos.length, 0, '3 inversiones no marean');
  assert.equal(b.mod.api.estado().mareo, false);
  // Sin arrastre no cuenta aunque llegue velocidad
  const c = montar();
  correr(c.mod, estArrastre({ drag: false, dragPeso: 0 }), 0, 2, agitar(0, 7));
  assert.equal(c.eventos.length, 0);
});

test('el mareo entra y sale sin saltos e inhibe el seguimiento', () => {
  const { mod, eventos } = montar();
  const est = estArrastre({ drag: false, dragPeso: 0 });
  correr(mod, est, 0, 0.5);
  assert.equal(mod.api.mareo(), true);
  assert.equal(eventos.at(-1).d.forzado, true);
  const r = correr(mod, est, 0.5, 3, null, { guardar: true });
  for (let i = 1; i < r.poses.length; i++) assert.ok(difMax(r.poses[i - 1], r.poses[i]) < 0.03);
  const m = montar().mod;
  m.pose({}, DT, 1, est); m.api.mareo(); m.pose({}, DT, 1.5, est);
  assert.ok(m.inhibe(est).seguimiento < 0.4, 'mareada casi no sigue el cursor');
  assert.ok(typeof GESTO_MAREO.fn === 'function' && GESTO_MAREO.dur === 2500);
});

// ── Pose colgada y caras ───────────────────────────────────────────────────────

test('pose colgada con movimiento: una rodilla doblada, cabeza que mira alrededor', () => {
  const p0 = poseColgada(0, 1), p1 = poseColgada(1.6, 1), pe = poseColgada(0, -1);
  assert.ok(p0.rightLowerLeg[0] > 0.5 && p0.leftLowerLeg[0] < 0.3, 'rodilla derecha');
  assert.ok(pe.leftLowerLeg[0] > 0.5 && pe.rightLowerLeg[0] < 0.3, 'espejo: la izquierda');
  assert.ok(Math.abs(p1.head[1] - p0.head[1]) > 0.1, 'la cabeza gira');
  assert.ok(Math.abs(p1.leftHand[0] - p0.leftHand[0]) > 0.01 || Math.abs(poseColgada(0.3, 1).leftHand[0]) > 0.1, 'manos a 0.9 Hz');
  // En el módulo: × dragPeso, y sin arrastre no hay nada
  const { mod } = montar();
  const out = mod.pose({}, DT, 1, estArrastre({ dragPeso: 0.5 }));
  cerca(out.leftUpperArm[2], 0.5 * POSE_COLGADA.leftUpperArm[2], 0.05);
  const nada = mod.pose({}, DT, 1.1, { drag: false, dragPeso: 0, sleepBlend: 0 });
  assert.ok(difMax(nada, {}) < 0.05);
  assert.equal(mod.inhibe(estArrastre()).seguimiento, 0.4, 'seguimiento ×0.4 colgada');
  assert.equal(mod.inhibe({ dragPeso: 0 }).seguimiento, 1);
});

test('agarrar y soltar no salta (dragPeso sube y baja como en el motor)', () => {
  // dragPeso sube a 8/s (el motor): los brazos suben 1.6 rad en ~0.3 s. Es rápido pero
  // continuo: a 240 fps el paso máximo baja a ~¼ del de 60 (un salto no bajaría).
  const pasoMax = (dt) => {
    const { mod } = montar();
    const est = { drag: false, dragPeso: 0, dragVx: 0, dragVy: 0, sleepBlend: 0 };
    let t = 0, prev = mod.pose({}, dt, t, est), m = 0;
    for (let i = 0, n = Math.round(6 / dt); i < n; i++) {
      t += dt;
      est.drag = t > 0.5 && t < 3;
      est.dragPeso += ((est.drag ? 1 : 0) - est.dragPeso) * (1 - Math.exp(-(est.drag ? 8 : 3) * dt));
      est.dragVx = est.drag ? 900 * Math.sin(t * 3) : 0;
      const p = mod.pose({}, dt, t, est);
      m = Math.max(m, difMax(prev, p)); prev = p;
    }
    return m;
  };
  const p60 = pasoMax(1 / 60), p240 = pasoMax(1 / 240);
  assert.ok(p60 < 0.25, `paso a 60 fps ${p60}`);
  assert.ok(p240 < 0.35 * p60, `no escala con el dt (salto): ${p60} → ${p240}`);
});

test('cara sostenida: tras 0.3 s y rampa de 0.2 s, sad 0.7 + oh en triángulo (4 s)', () => {
  const { mod } = montar();
  const est = estArrastre();
  const r = correr(mod, est, 0, 8, () => [0, 0], { guardar: true });
  const en = (s) => r.exprs[Math.round(s / DT) - 1];
  assert.equal(en(0.25).sad, undefined, 'antes de 0.3 s nada');
  assert.ok(en(0.4).sad > 0.05 && en(0.4).sad < 0.65, `rampa ${en(0.4).sad}`);
  cerca(en(1).sad, 0.7, 1e-6);
  cerca(en(2).oh, 0.4, 0.01, 'cima del triángulo a los 2 s');
  cerca(en(4).oh, 0, 0.01, 'vuelve a 0 a los 4 s');
  cerca(en(3).oh, 0.2, 0.01);
  assert.ok(en(3).relaxed > 0.25, 'quieta en el aire: relajada');
  cerca(triangulo(1, 0.4, 4), 0.2, 1e-12);
  // Al soltar se va apagando (no de golpe)
  est.drag = false;
  const s = correr(mod, est, r.t, 1, null, { guardar: true });
  assert.ok(s.exprs[0].sad > 0.6 && !(s.exprs.at(-1).sad > 0.05));
  // Dormida no pone cara
  const d = montar().mod;
  const rd = correr(d, estArrastre({ sleepBlend: 1 }), 0, 1, null, { guardar: true });
  assert.equal(rd.exprs.at(-1).sad, undefined);
});

test('caras por velocidad: <400 relajada, 400–1500 preocupada, >1500 asustada', () => {
  const cara = (v) => {
    const { mod } = montar();
    const r = correr(mod, estArrastre(), 0, 3, () => [v, 0], { guardar: true });
    return { c: mod.api.estado().caras, e: r.exprs.at(-1) };
  };
  const lenta = cara(200), media = cara(900), rapida = cara(2600);
  assert.ok(lenta.c.relajada > 0.95, JSON.stringify(lenta.c));
  assert.ok(media.c.preocupada > 0.95, JSON.stringify(media.c));
  assert.ok(rapida.c.asustada > 0.95, JSON.stringify(rapida.c));
  assert.ok(lenta.e.relaxed > 0.25 && !(lenta.e.surprised > 0.05));
  assert.ok(media.e.surprised > 0.2 && media.e.surprised < 0.3 && media.e.sad >= 0.69);
  assert.ok(rapida.e.surprised > 0.75 && rapida.e.oh >= 0.49 && rapida.e.sad < 0.35);
  const neg = cara(-2600);
  assert.ok(neg.c.asustada > 0.95, 'la dirección no importa');
});

test('sentada no se balancea; activo:false funde a cero', () => {
  const { mod } = montar();
  correr(mod, estArrastre({ sentada: true }), 0, 3, () => [3000, 0]);
  cerca(mod.api.estado().leanZ, 0, 1e-9);
  const b = montar().mod;
  const est = estArrastre();
  let { t } = correr(b, est, 0, 2, () => [3000, 0]);
  assert.equal(b.api.set({ activo: false }).activo, false);
  const r = correr(b, est, t, 3, () => [3000, 0], { guardar: true });
  assert.ok(difMax(r.poses.at(-1), {}) < 1e-6, 'apagado no suma nada');
  assert.equal(b.ocupado(est), false);
});

test('ctx.tieneExpr: sin "blink" el mareo entrecierra con blinkLeft/Right', () => {
  const { mod } = montar({ tieneExpr: (n) => n !== 'blink' });
  const est = estArrastre({ drag: false, dragPeso: 0 });
  mod.pose({}, DT, 1, est); mod.api.mareo();
  const r = correr(mod, est, 1, 1, null, { guardar: true });
  const e = r.exprs.at(-1);
  assert.equal(e.blink, undefined);
  assert.ok(e.blinkLeft > 0.3 && e.blinkRight > 0.3);
});

test('se registra en el bus: inhibe, ocupado y api', () => {
  const eventos = [];
  const bus = crearBus({ emitir: (t, d) => eventos.push(t) });
  assert.equal(bus.registrar(instalar).nombre, 'movimiento');
  const est = estArrastre();
  let t = 0;
  for (let i = 0; i < 90; i++) {
    t += DT;
    const [vx] = agitar(0, 5)(t); est.dragVx = vx;
    bus.llamar('pose', {}, DT, t, est);
    bus.llamar('expresiones', () => {}, DT, t, est);
  }
  assert.deepEqual(eventos, ['mareo']);
  assert.ok(bus.inhibe(est).seguimiento < 0.4);
  assert.equal(bus.ocupado(est), true);
  assert.equal(bus.api('movimiento', 'estado').mareo, true);
  assert.equal(bus.activo('movimiento'), true, 'ningún hook ha fallado');
});
