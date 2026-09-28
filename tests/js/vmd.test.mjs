// tests/js/vmd.test.mjs — ui_web/vrm/lune_vmd.js (corte 9): parser de VMD robusto a archivos
// del usuario, mapa MMD → VRM, curvas bézier, horneado a 30 fps (A-pose, columna, torsiones,
// IK de piernas, morfos) y paso a VRMAnimation + createVRMAnimationClip de verdad.
// Los VMD y el VRM son sintéticos (vmd_fabrica.mjs); three.js y three-vrm-animation son los
// del vendor. Las poses se comprueban con matrices de three (posiciones en el mundo).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  THREE, VRMA, escribirVMD, ipDe, qGrados, crearVRMReal, mundo, giroMundo, sjis,
} from './vmd_fabrica.mjs';
import * as V from '../../ui_web/vrm/lune_vmd.js';

const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const sinPausa = { ceder: () => Promise.resolve() };
const Q = (a) => new THREE.Quaternion(a[0], a[1], a[2], a[3]);
/** Ángulo entre dos orientaciones (rad). */
const angulo = (a, b) => {
  const d = new THREE.Quaternion(a.x, a.y, a.z, a.w).invert().multiply(new THREE.Quaternion(b.x, b.y, b.z, b.w));
  return 2 * Math.atan2(Math.hypot(d.x, d.y, d.z), Math.abs(d.w));
};
/** Cuaternión de MMD (mano izquierda) cuyo equivalente en three es q (x, y negadas). */
const aMMD = (q) => [-q[0], -q[1], q[2], q[3]];

/** Pone en el VRM el frame f del horneado (rotaciones y cadera). */
function aplicarFrame(vrm, hor, f) {
  for (const [h, a] of hor.rot) {
    const n = vrm.humanoid.getNormalizedBoneNode(h);
    if (n) n.quaternion.set(a[f * 4], a[f * 4 + 1], a[f * 4 + 2], a[f * 4 + 3]);
  }
  if (hor.cadera) vrm.huesos.hips.position.set(hor.cadera[f * 3], hor.cadera[f * 3 + 1], hor.cadera[f * 3 + 2]);
}
function restPoseDe(vrm) { return vrm.humanoid.normalizedRestPose; }

// ── Parser ──────────────────────────────────────────────────────────────────────

test('VMD v2: cuentas, nombres Shift_JIS con NFKC, frames de IK y secciones que se saltan', () => {
  const buf = escribirVMD({
    modelo: '初音ミク',
    huesos: [
      { nombre: 'センター', frame: 0, pos: [0, -2, 0] },
      { nombre: '左腕', frame: 10, rot: qGrados(0, 0, 1, 20) },
      { nombre: '上半身２', frame: 20 },
      { nombre: '左足ＩＫ', frame: 5, pos: [0, 1, 0] },
    ],
    morfos: [{ nombre: 'ｳｨﾝｸ２右', frame: 3, peso: 0.5 }, { nombre: 'まばたき', frame: 7, peso: 1 }],
    camara: 3, luces: 2, sombras: 1,
    ik: [{ frame: 0, ik: { '左足ＩＫ': true, '右足ＩＫ': false } }, { frame: 30, visible: false, ik: { '左足ＩＫ': false } }],
  });
  const v = V.parsearVMD(buf);
  assert.equal(v.version, 2);
  assert.equal(v.modelo, '初音ミク');
  assert.deepEqual(v.huesos.map((h) => h.nombre), ['センター', '左腕', '上半身2', '左足IK']);
  assert.deepEqual(v.morfos.map((m) => m.nombre), ['ウィンク2右', 'まばたき']);
  assert.equal(v.camara, 3); assert.equal(v.luces, 2); assert.equal(v.sombras, 1);
  assert.deepEqual(v.ik, [
    { frame: 0, visible: true, ik: { '左足IK': true, '右足IK': false } },
    { frame: 30, visible: false, ik: { '左足IK': false } },
  ]);
  assert.equal(v.frames, 20, 'la duración la marcan huesos y morfos (no la propiedad IK)');
  cerca(v.duracion, 20 / 30, 1e-9);
  assert.deepEqual(v.huesos[0].pos, [0, -2, 0]);
  cerca(v.huesos[1].rot[2], Math.sin(10 * Math.PI / 180), 1e-6);
  assert.equal(v.huesos[1].ip.length, 64);
  assert.equal(v.soloCamara, false);
  assert.equal(v.soloMorfos, false);
});

test('VMD v1 (cabecera vieja, modelo de 10 bytes) y archivos sin las secciones del final', () => {
  const v1 = V.parsearVMD(escribirVMD({ version: 1, modelo: 'Lune', huesos: [{ nombre: '頭', frame: 4 }] }));
  assert.equal(v1.version, 1);
  assert.equal(v1.modelo, 'Lune');
  assert.equal(v1.huesos[0].nombre, '頭');
  // Solo huesos (sin cuenta de morfos): las secciones que faltan cuentan 0
  const corto = V.parsearVMD(escribirVMD({ huesos: [{ nombre: '首', frame: 1 }], sinMorfos: true }));
  assert.equal(corto.morfos.length, 0);
  assert.equal(corto.camara, 0);
  assert.deepEqual(corto.ik, []);
});

test('normalizarNombre: NFKC, sin anchos cero ni controles y sin espacios alrededor', () => {
  assert.equal(V.normalizarNombre('左足ＩＫ'), '左足IK');
  assert.equal(V.normalizarNombre('ｳｨﾝｸ２右'), 'ウィンク2右');
  assert.equal(V.normalizarNombre(' ​セン‌ター﻿ '), 'センター');
  assert.equal(V.normalizarNombre('上半身２\u0001'), '上半身2');
  assert.equal(V.normalizarNombre(null), '');
});

test('el nombre se corta en el primer NUL (lo de después es basura de MMD)', () => {
  const raro = new Uint8Array(15);
  raro.set(sjis('首'));
  raro[2] = 0; raro.fill(0xFD, 3);
  const v = V.parsearVMD(escribirVMD({ huesos: [{ nombre: raro, frame: 0 }] }));
  assert.equal(v.huesos[0].nombre, '首');
});

test('truncado en cualquier punto → Error (nunca un string ni un cuelgue); dentro de los huesos siempre falla', () => {
  const buf = escribirVMD({
    huesos: [{ nombre: 'センター', frame: 0 }, { nombre: '左腕', frame: 3 }],
    morfos: [{ nombre: 'あ', frame: 1, peso: 1 }], camara: 1, ik: [{ frame: 0, ik: { '左足ＩＫ': true } }],
  });
  const finHuesos = 30 + 20 + 4 + 2 * 111;
  for (let n = 0; n < buf.length; n++) {
    let r = null, err = null;
    try { r = V.parsearVMD(buf.subarray(0, n)); } catch (e) { err = e; }
    if (err) {
      assert.ok(err instanceof Error, `corte en ${n}: lanza un Error, no ${typeof err}`);
      assert.match(err.message, /VMD/);
    } else {
      assert.ok(r && Array.isArray(r.huesos), `corte en ${n}`);
    }
    if (n < finHuesos) assert.ok(err, `corte en ${n} (dentro de los huesos) tiene que fallar`);
  }
});

test('cuentas enormes, topes y cabeceras falsas → Error enseguida', () => {
  const t0 = Date.now();
  assert.throws(() => V.parsearVMD(escribirVMD({ cuentas: { huesos: 0xFFFFFFFF } })), /demasiadas claves de hueso/);
  assert.throws(() => V.parsearVMD(escribirVMD({ cuentas: { huesos: 1_000_000 } })), /cortado/);
  assert.throws(() => V.parsearVMD(escribirVMD({ cuentas: { morfos: 0x7FFFFFFF } })), /demasiadas claves de morfo/);
  assert.throws(() => V.parsearVMD(escribirVMD({ ik: [{ frame: 0, ik: {} }], cuentas: { ik: 1e6 } })), /demasiados frames de IK/);
  assert.throws(() => V.parsearVMD(escribirVMD({ ik: [{ frame: 0, ik: {}, cuantos: 65 }] })), /demasiados IK/);
  assert.throws(() => V.parsearVMD(escribirVMD({ huesos: [{ nombre: '首', frame: 36001 }] })), /demasiado largo/);
  assert.throws(() => V.parsearVMD(escribirVMD({ huesos: [{ nombre: '首', frame: 0 }] }), { bytes: 100 }), /tope/);
  const falso = escribirVMD();
  falso[0] = 0x58;
  assert.throws(() => V.parsearVMD(falso), /No es un archivo VMD/);
  assert.throws(() => V.parsearVMD('Vocaloid Motion Data 0002'), /binario/);
  assert.throws(() => V.parsearVMD(new Uint8Array(10)), /cortado/);
  assert.ok(Date.now() - t0 < 2000, 'sin recorrer 4 000 millones de claves');
});

test('solo cámara → soloCamara; solo morfos → soloMorfos', () => {
  assert.equal(V.parsearVMD(escribirVMD({ camara: 3 })).soloCamara, true);
  const m = V.parsearVMD(escribirVMD({ morfos: [{ nombre: 'あ', frame: 0, peso: 1 }] }));
  assert.equal(m.soloMorfos, true);
  assert.equal(m.soloCamara, false);
});

test('floats rotos (NaN/∞) se sanean: posición 0 y rotación identidad', () => {
  const v = V.parsearVMD(escribirVMD({ huesos: [{ nombre: '首', frame: 0, pos: [NaN, Infinity, 1], rot: [NaN, 0, 0, NaN] }] }));
  assert.deepEqual(v.huesos[0].pos, [0, 0, 1]);
  assert.deepEqual(v.huesos[0].rot, [0, 0, 0, 1]);
});

// ── Mapa, curvas y mano derecha ─────────────────────────────────────────────────

test('mapa: nombres exactos tras NFKC; 肩P y los D se ignoran; morfos de Mate-Engine', () => {
  assert.deepEqual(V.MAPA_HUESOS['上半身2'], ['chest']);
  assert.deepEqual(V.MAPA_HUESOS['上半身'], ['spine']);
  assert.deepEqual(V.MAPA_HUESOS['左親指0'], ['leftThumbMetacarpal']);
  assert.deepEqual(V.MAPA_HUESOS['右人指3'], ['rightIndexDistal']);
  assert.deepEqual(V.MAPA_HUESOS['左足先EX'], ['leftToes']);
  assert.equal(V.MAPA_HUESOS['左肩P'], undefined);
  assert.equal(V.MAPA_HUESOS['左足D'], undefined);
  assert.equal(V.MAPA_HUESOS['左つま先IK'], undefined);
  assert.equal(V.MAPA_MORFOS['ウィンク2右'], 'blinkRight');
  assert.equal(V.MAPA_MORFOS['笑い'], 'relaxed');
  assert.equal(V.MAPA_MORFOS['眉上'], undefined);
});

test('curva() lee el bloque de 64 bytes como MMDLoader (x1, y1, x2, y2 por canal)', () => {
  const ip = ipDe([{ x1: 1, y1: 2, x2: 3, y2: 4 }, { x1: 5, y1: 6, x2: 7, y2: 8 }, { x1: 9, y1: 10, x2: 11, y2: 12 }, { x1: 13, y1: 14, x2: 15, y2: 16 }]);
  const c = V.curva(ip, 3);
  cerca(c.x1, 13 / 127, 1e-12); cerca(c.y1, 14 / 127, 1e-12); cerca(c.x2, 15 / 127, 1e-12); cerca(c.y2, 16 / 127, 1e-12);
  const c0 = V.curva(ip, 0);
  cerca(c0.x1, 1 / 127, 1e-12); cerca(c0.y2, 4 / 127, 1e-12);
});

test('bézier: (20, 20, 107, 107) ≈ identidad; curvas monótonas con error ≤ 1e-3', () => {
  const lin = V.curva(ipDe(), 0);
  for (let x = 0; x <= 1.0001; x += 0.01) cerca(V.bezier(lin, x), Math.min(1, x), 1e-3, `x=${x}`);
  // Referencia: invertir x(t) con 60 bisecciones
  const ref = (c, x) => {
    const bx = (t) => 3 * (1 - t) ** 2 * t * c.x1 + 3 * (1 - t) * t * t * c.x2 + t ** 3;
    let a = 0, b = 1;
    for (let i = 0; i < 60; i++) { const m = (a + b) / 2; if (bx(m) < x) a = m; else b = m; }
    const t = (a + b) / 2;
    return 3 * (1 - t) ** 2 * t * c.y1 + 3 * (1 - t) * t * t * c.y2 + t ** 3;
  };
  for (const [x1, y1, x2, y2] of [[127, 0, 0, 127], [64, 0, 64, 127], [10, 100, 90, 20], [127, 127, 0, 0], [0, 127, 127, 0]]) {
    const c = { x1: x1 / 127, y1: y1 / 127, x2: x2 / 127, y2: y2 / 127 };
    let antes = -1;
    for (let x = 0; x <= 1.0001; x += 0.02) {
      const y = V.bezier(c, Math.min(1, x));
      cerca(y, ref(c, Math.min(1, x)), 1e-3, `curva ${[x1, y1, x2, y2]} en ${x}`);
      assert.ok(y >= antes - 1e-6, 'monótona');
      antes = y;
    }
  }
  assert.equal(V.bezier(lin, -1), 0);
  assert.equal(V.bezier(lin, 2), 1);
});

test('aManoDerecha: z de la posición y x/y de la rotación cambian de signo (copia)', () => {
  const k = { nombre: '首', frame: 3, pos: [1, 2, 3], rot: [0.1, 0.2, 0.3, 0.9] };
  const r = V.aManoDerecha(k);
  assert.deepEqual(r.pos, [1, 2, -3]);
  assert.deepEqual(r.rot, [-0.1, -0.2, 0.3, 0.9]);
  assert.deepEqual(k.pos, [1, 2, 3], 'el original no cambia');
  assert.equal(r.frame, 3);
});

// ── Retarget ────────────────────────────────────────────────────────────────────

async function hornear1(huesos, extra = {}, vrm = crearVRMReal()) {
  const v = V.parsearVMD(escribirVMD({ huesos, ...(extra.vmd || {}) }));
  const hor = await V.hornear(THREE, [v], { restPose: restPoseDe(vrm), ...sinPausa, ...(extra.opciones || {}) });
  return { hor, vrm };
}

test('VMD identidad → brazos en la A-pose de MMD con FK (mano ≈ L·sin θ bajo el hombro); brazoGrados la cambia', async () => {
  for (const grados of [35, 45]) {
    const { hor, vrm } = await hornear1([{ nombre: 'センター', frame: 0 }], { opciones: { brazoGrados: grados } });
    aplicarFrame(vrm, hor, 0);
    for (const lado of ['left', 'right']) {
      const hombro = mundo(vrm, lado + 'UpperArm'), mano = mundo(vrm, lado + 'Hand');
      const L = 0.25 + 0.23;
      cerca(mano.y - hombro.y, -L * Math.sin(grados * Math.PI / 180), 1e-4, `${lado} ${grados}°`);
      cerca(Math.abs(mano.x - hombro.x), L * Math.cos(grados * Math.PI / 180), 1e-4);
      assert.equal(Math.sign(mano.x - hombro.x), lado === 'left' ? 1 : -1, 'cada brazo hacia su lado');
    }
  }
});

test('下半身 30°Y + 上半身 0 → spine −30°Y y el pecho sin girar en el mundo (hermanos en MMD)', async () => {
  const { hor, vrm } = await hornear1([{ nombre: '下半身', frame: 0, rot: aMMD(qGrados(0, 1, 0, 30)) }]);
  aplicarFrame(vrm, hor, 0);
  assert.ok(angulo(vrm.huesos.hips.quaternion, Q(qGrados(0, 1, 0, 30))) < 1e-5, 'caderas giradas 30°');
  assert.ok(angulo(vrm.huesos.spine.quaternion, Q(qGrados(0, 1, 0, -30))) < 1e-5, 'columna contrarrotada');
  assert.ok(angulo(giroMundo(vrm, 'chest'), new THREE.Quaternion()) < 1e-5, 'pecho recto en el mundo');
  assert.ok(angulo(giroMundo(vrm, 'leftUpperLeg'), Q(qGrados(0, 1, 0, 30))) < 1e-5, 'las piernas siguen a 下半身');
});

test('腕捩 y 手捩 plegados: la mano en el mundo coincide con la cadena de MMD', async () => {
  const k = {
    '左腕': qGrados(0.3, 0.2, 0.93, -40), '左腕捩': qGrados(1, 0, 0, 50), '左ひじ': qGrados(0, 1, 0, -70),
    '左手捩': qGrados(1, 0, 0, -30), '左手首': qGrados(0, 0.6, 0.8, 25),
  };
  const huesos = Object.entries(k).map(([nombre, q]) => ({ nombre, frame: 0, rot: aMMD(q) }));
  const { hor, vrm } = await hornear1(huesos);
  aplicarFrame(vrm, hor, 0);
  const A = Q(qGrados(0, 0, 1, -35));
  const cadena = Q(k['左腕']).multiply(Q(k['左腕捩'])).multiply(Q(k['左ひじ'])).multiply(Q(k['左手捩'])).multiply(Q(k['左手首'])).multiply(A);
  assert.ok(angulo(giroMundo(vrm, 'leftHand'), cadena) < 1e-4, 'orientación de la mano');
  const codo = Q(k['左腕']).multiply(Q(k['左腕捩'])).multiply(A);
  assert.ok(angulo(giroMundo(vrm, 'leftUpperArm'), codo) < 1e-4, 'brazo = (腕·腕捩)·A');
});

test('IK: センター −2 → rodillas dobladas hacia +Z y el tobillo a ≤ 1 cm del objetivo', async () => {
  const huesos = [
    { nombre: 'センター', frame: 0, pos: [0, -2, 0] },
    { nombre: '左足ＩＫ', frame: 0 }, { nombre: '右足ＩＫ', frame: 0 },
  ];
  const vrm = crearVRMReal();
  const pies0 = { left: mundo(vrm, 'leftFoot'), right: mundo(vrm, 'rightFoot') };
  const { hor } = await hornear1(huesos, {}, vrm);
  assert.equal(hor.conIK, true);
  aplicarFrame(vrm, hor, 0);
  cerca(vrm.huesos.hips.position.y, 0.95 - 2 * hor.escala, 1e-6, 'la cadera baja 2 unidades MMD escaladas');
  for (const lado of ['left', 'right']) {
    const cad = mundo(vrm, lado + 'UpperLeg'), rod = mundo(vrm, lado + 'LowerLeg'), pie = mundo(vrm, lado + 'Foot');
    assert.ok(rod.z > cad.z + 0.02 && rod.z > pie.z + 0.02, `${lado}: rodilla delante (z ${rod.z.toFixed(3)})`);
    assert.ok(pie.distanceTo(pies0[lado]) <= 0.01, `${lado}: pie a ${pie.distanceTo(pies0[lado]).toFixed(4)} m del objetivo`);
  }
});

test('IK apagada por la propiedad → FK con 足/ひざ/足首; objetivo inalcanzable → finito y estirada', async () => {
  const rodilla = qGrados(1, 0, 0, 40);
  const huesos = [
    { nombre: 'センター', frame: 0, pos: [0, -2, 0] }, { nombre: '左足ＩＫ', frame: 0 }, { nombre: '左ひざ', frame: 0, rot: aMMD(rodilla) },
    { nombre: '左足ＩＫ', frame: 10, pos: [0, -50, 0] },
  ];
  const { hor, vrm } = await hornear1(huesos, { vmd: { ik: [{ frame: 0, ik: { '左足ＩＫ': false } }, { frame: 10, ik: { '左足ＩＫ': true } }] } });
  aplicarFrame(vrm, hor, 0);
  assert.ok(angulo(vrm.huesos.leftLowerLeg.quaternion, Q(rodilla)) < 1e-5, 'FK: la rodilla es la del VMD');
  aplicarFrame(vrm, hor, 10);
  for (const [h, a] of hor.rot) for (let i = 0; i < a.length; i++) assert.ok(Number.isFinite(a[i]), `${h} finito`);
  const cad = mundo(vrm, 'leftUpperLeg'), rod = mundo(vrm, 'leftLowerLeg'), pie = mundo(vrm, 'leftFoot');
  const recta = cad.distanceTo(pie), suma = cad.distanceTo(rod) + rod.distanceTo(pie);
  assert.ok(recta > suma * 0.999, 'la pierna se estira hacia el objetivo');
  assert.ok(pie.y < cad.y, 'hacia abajo');
});

test('huesos opcionales que el modelo no trae: su giro se pliega (sin upperChest → chest = 上半身2·上半身3)', async () => {
  const q2 = qGrados(1, 0, 0, 10), q3 = qGrados(1, 0, 0, 15);
  const vrm = crearVRMReal(THREE, { sin: ['upperChest'] });
  const { hor } = await hornear1([{ nombre: '上半身２', frame: 0, rot: aMMD(q2) }, { nombre: '上半身３', frame: 0, rot: aMMD(q3) }], {
    opciones: { huesosModelo: (h) => !!vrm.humanoid.getNormalizedBoneNode(h) },
  }, vrm);
  assert.equal(hor.rot.has('upperChest'), false);
  aplicarFrame(vrm, hor, 0);
  assert.ok(angulo(vrm.huesos.chest.quaternion, Q(qGrados(1, 0, 0, 25))) < 1e-5);
});

test('morfos: exactos (los desconocidos fuera), lineales, máximo por preset y cuerpo + labios juntos', async () => {
  const cuerpo = V.parsearVMD(escribirVMD({ huesos: [{ nombre: '頭', frame: 20 }] }));
  const labios = V.parsearVMD(escribirVMD({
    morfos: [
      { nombre: 'まばたき', frame: 0, peso: 0 }, { nombre: 'まばたき', frame: 10, peso: 1 },
      { nombre: 'ウィンク', frame: 0, peso: 0.2 }, { nombre: 'ウィンク２', frame: 0, peso: 0.7 },
      { nombre: 'ｳｨﾝｸ２右', frame: 0, peso: 2 }, { nombre: '眉上', frame: 0, peso: 1 }, { nombre: 'あ', frame: 5, peso: 0.4 },
    ],
  }));
  const hor = await V.hornear(THREE, [cuerpo, labios], sinPausa);
  assert.deepEqual([...hor.expr.keys()].sort(), ['aa', 'blink', 'blinkLeft', 'blinkRight']);
  cerca(hor.expr.get('blink')[5], 0.5, 1e-6, 'lineal');
  cerca(hor.expr.get('blink')[15], 1, 1e-6, 'después de la última clave, la última');
  cerca(hor.expr.get('blinkLeft')[0], 0.7, 1e-6, 'máximo de ウィンク y ウィンク2');
  cerca(hor.expr.get('blinkRight')[0], 1, 1e-6, 'recortado a 0..1');
  cerca(hor.expr.get('aa')[0], 0.4, 1e-6, 'antes de la primera clave, la primera');
  assert.ok(hor.rot.has('head'), 'el cuerpo también está');
  assert.equal(hor.frames, 20);
});

test('horneado: duración, 30 fps, cuaterniones unitarios y finitos, trozos de 1500 frames y cancelación', async () => {
  const huesos = [];
  for (let f = 0; f <= 3200; f += 400) huesos.push({ nombre: '左腕', frame: f, rot: qGrados(0, 0, 1, (f % 800) ? 30 : -30) });
  const v = V.parsearVMD(escribirVMD({ huesos }));
  let pausas = 0;
  const hor = await V.hornear(THREE, [v], { ceder: () => { pausas++; return Promise.resolve(); } });
  assert.equal(pausas, 2, 'cede en los frames 1500 y 3000');
  cerca(hor.duracion, 3200 / 30, 1e-9);
  assert.equal(hor.tiempos.length, 3201);
  cerca(hor.tiempos[30], 1, 1e-6);
  for (const [h, a] of hor.rot) {
    for (let f = 0; f < 3201; f += 97) {
      const l = Math.hypot(a[f * 4], a[f * 4 + 1], a[f * 4 + 2], a[f * 4 + 3]);
      cerca(l, 1, 1e-5, `${h}@${f}`);
    }
  }
  let n = 0;
  await assert.rejects(V.hornear(THREE, [v], { ceder: () => Promise.resolve(), cancelado: () => ++n > 1 }), /cancelado/);
  await assert.rejects(V.hornear(THREE, [V.parsearVMD(escribirVMD({ camara: 2 }))], sinPausa), /no tiene movimiento/);
  const raro = V.parsearVMD(escribirVMD({ huesos: [{ nombre: 'Bone01', frame: 0 }, { nombre: '左肩P', frame: 3 }], morfos: [{ nombre: '眉上', frame: 0, peso: 1 }] }));
  await assert.rejects(V.hornear(THREE, [raro], sinPausa), /no tiene movimiento/, 'esqueleto que no es el de MMD');
});

// ── VRMAnimation y clip ─────────────────────────────────────────────────────────

/** Aplica un AnimationClip de three en t sobre el VRM (por nombre de nodo, como el mixer). */
function aplicarClip(vrm, clip, t) {
  for (const tr of clip.tracks) {
    const i = tr.name.lastIndexOf('.');
    const nodo = vrm.scene.getObjectByName(tr.name.slice(0, i)), prop = tr.name.slice(i + 1);
    assert.ok(nodo, `la pista ${tr.name} apunta a un nodo del VRM`);
    const v = tr.createInterpolant().evaluate(t);
    if (prop === 'quaternion') nodo.quaternion.set(v[0], v[1], v[2], v[3]);
    else if (prop === 'position') nodo.position.set(v[0], v[1], v[2]);
    else nodo[prop] = v[0];
  }
}

test('aVRMAnimation + createVRMAnimationClip reales: pistas → nodos normalizados; metaVersion 0 niega x/z', async () => {
  const brazo = qGrados(0.2, 0.5, 0.84, -60);
  const vmd = V.parsearVMD(escribirVMD({
    huesos: [{ nombre: '左腕', frame: 0, rot: aMMD(brazo) }, { nombre: '左腕', frame: 30 }, { nombre: 'センター', frame: 0, pos: [1, 0, 2] }],
    morfos: [{ nombre: 'にこり', frame: 0, peso: 0.8 }],
  }));
  const vrm1 = crearVRMReal(THREE, { version: '1' });
  const hor = await V.hornear(THREE, [vmd], { restPose: restPoseDe(vrm1), ...sinPausa });
  const anim = V.aVRMAnimation(VRMA.VRMAnimation, THREE, hor, restPoseDe(vrm1).hips.position);
  assert.ok(anim instanceof VRMA.VRMAnimation);
  cerca(anim.duration, 1, 1e-9);
  cerca(anim.restHipsPosition.y, 0.95, 1e-9);
  const clip1 = VRMA.createVRMAnimationClip(anim, { ...vrm1, lookAt: null });
  const nombres = clip1.tracks.map((t) => t.name);
  assert.ok(nombres.includes('Normalized_leftUpperArm.quaternion'));
  assert.ok(nombres.includes('Normalized_hips.position'));
  assert.ok(nombres.includes('VRMExpression_happy.weight'));
  aplicarClip(vrm1, clip1, 0);
  const A = Q(qGrados(0, 0, 1, -35));
  assert.ok(angulo(vrm1.huesos.leftUpperArm.quaternion, Q(brazo).multiply(A)) < 1e-4);
  cerca(vrm1.expressionManager.getValue('happy'), 0.8, 1e-6);

  // VRM 0.x: mismas pistas con x/z negadas, y en el MUNDO la mano queda en el mismo sitio
  const vrm0 = crearVRMReal(THREE, { version: '0' });
  const clip0 = VRMA.createVRMAnimationClip(anim, { ...vrm0, lookAt: null });
  const q1 = clip1.tracks.find((t) => t.name === 'Normalized_leftUpperArm.quaternion').values;
  const q0 = clip0.tracks.find((t) => t.name === 'Normalized_leftUpperArm.quaternion').values;
  cerca(q0[0], -q1[0], 1e-7); cerca(q0[1], q1[1], 1e-7); cerca(q0[2], -q1[2], 1e-7); cerca(q0[3], q1[3], 1e-7);
  aplicarClip(vrm0, clip0, 0);
  for (const h of ['leftHand', 'rightHand', 'head', 'hips']) {
    assert.ok(mundo(vrm0, h).distanceTo(mundo(vrm1, h)) < 1e-4, `${h} igual en el mundo con VRM 0.x y 1.0`);
  }
});
