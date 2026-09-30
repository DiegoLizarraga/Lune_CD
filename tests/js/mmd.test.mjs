// tests/js/mmd.test.mjs — ui_web/vrm/lune_mmd.js (corte 9): el módulo 'mmd' del bus VRM que
// reproduce bailes .vmd/.vrma con su canción. three.js, GLTFLoader y three-vrm-animation son
// los DE VERDAD del vendor; el VRM es de Object3D reales (vmd_fabrica.mjs) y el <audio> es
// falso. Casi todo se prueba llamando a los hooks del módulo como lo hace lune_vrm.js (el
// «motor» del test reescribe en cada frame los huesos de HUESOS con la A-pose de reposo y
// las expresiones del motor); los brazos al acabar se comprueban además con el motor de
// verdad (lune_vrm.js) cargado con three real (motor_vrm_falso.mjs + brazoMundo).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import {
  THREE, VRMA, GLTFLoader, URL_THREE, aDataURL, escribirVMD, crearVRMA, crearVRMReal, qGrados, mundo, audioFalso,
} from './vmd_fabrica.mjs';
import {
  reescribirImports, frames, cargas, lienzoFalso, brazoMundo, quietaSinIdles, vaciarCola, correr as correrMotor,
} from './motor_vrm_falso.mjs';
import * as VMD from '../../ui_web/vrm/lune_vmd.js';
import * as MMD from '../../ui_web/vrm/lune_mmd.js';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_mmd_audio.js', import.meta.url), 'utf8'), { filename: 'lune_mmd_audio.js' });
const LuneMMDAudio = globalThis.LuneMMDAudio;

const ORIGEN = 'http://127.0.0.1:8765';
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const Q = (a) => new THREE.Quaternion(a[0], a[1], a[2], a[3]);
const angulo = (a, b) => {
  const d = new THREE.Quaternion(a.x, a.y, a.z, a.w).invert().multiply(new THREE.Quaternion(b.x, b.y, b.z, b.w));
  return 2 * Math.atan2(Math.hypot(d.x, d.y, d.z), Math.abs(d.w));
};
const MMDq = (q) => [-q[0], -q[1], q[2], q[3]];          // de three (mano derecha) al VMD (mano izquierda)
const HUESOS_MOTOR = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg'];
// La A-pose de reposo de lune_vrm.js (POSE_REPOSO): la escribe el «motor» del test en cada frame
const POSE_MOTOR = {
  leftUpperArm: [0, 0, -1.15], rightUpperArm: [0, 0, 1.15], leftLowerArm: [0, -0.28, 0], rightLowerArm: [0, 0.28, 0],
  leftHand: [0, 0, -0.08], rightHand: [0, 0, 0.08],
};
const qMotor = (h, s) => { const r = POSE_MOTOR[h] || [0, 0, 0]; return new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0] * s, r[1], r[2] * s)); };

const BRAZO_IZQ = qGrados(0, 0, 1, 95);        // con la A-pose (−35°) queda 60° por encima de la horizontal
const BRAZO_DER = qGrados(0, 0, 1, -95);
const ESCALA = 0.95 / 11;

function vmdBaile({ ultimo = 300, dedo = true, cadera = true, morfos = true, parpadeo = false } = {}) {
  const huesos = [
    { nombre: '左腕', frame: 0, rot: MMDq(BRAZO_IZQ) }, { nombre: '左腕', frame: ultimo, rot: MMDq(BRAZO_IZQ) },
    { nombre: '右腕', frame: 0, rot: MMDq(BRAZO_DER) },
  ];
  if (dedo) huesos.push({ nombre: '左人指１', frame: 0, rot: MMDq(qGrados(0, 0, 1, 40)) }, { nombre: '左肩', frame: 0, rot: MMDq(qGrados(0, 0, 1, 10)) });
  if (cadera) huesos.push({ nombre: 'センター', frame: 0, pos: [5, 1, 0] });
  const m = morfos ? [{ nombre: 'にこり', frame: 0, peso: 1 }, { nombre: 'あ', frame: 0, peso: 1 }] : [];
  if (parpadeo) m.push({ nombre: 'まばたき', frame: 0, peso: 1 });
  return escribirVMD({ huesos, morfos: m });
}

/** fetch falso sobre un mapa ruta → bytes | {bytes, largo, cuerpo: 'stream', espera: Promise}; apunta
 *  lo pedido (con `espera`, el archivo no llega hasta que se cumpla: un baile que tarda en cargar). */
function crearFetch(archivos) {
  const pedidas = [], leidos = [];
  const f = async (url) => {
    pedidas.push(url);
    const u = new URL(url);
    const a = archivos[decodeURIComponent(u.pathname)];
    if (!a) return { ok: false, status: 404, headers: { get: () => null } };
    if (a.espera) await a.espera;
    const bytes = a instanceof Uint8Array ? a : a.bytes;
    const largo = a instanceof Uint8Array ? String(bytes.length) : a.largo;
    const r = {
      ok: true, status: 200,
      headers: { get: (k) => (String(k).toLowerCase() === 'content-length' ? (largo ?? null) : null) },
      arrayBuffer: async () => { leidos.push(url); return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength); },
    };
    if (a.cuerpo === 'stream') {
      const trozo = 8 << 20;
      let p = 0;
      r.body = { getReader: () => ({
        read: async () => {
          if (p >= a.total) return { done: true, value: undefined };
          const n = Math.min(trozo, a.total - p); p += n; leidos.push(url);
          return { done: false, value: new Uint8Array(n) };
        },
        cancel: async () => { a.cancelado = true; },
      }) };
    }
    return r;
  };
  f.pedidas = pedidas; f.leidos = leidos;
  return f;
}

/** Módulo instalado sobre un ctx como el de lune_vrm.js, con VRM real, fetch y <audio> falsos. */
function montar({ version = '1', archivos = {}, audio = {}, sinModelo = false } = {}) {
  const vrm = crearVRMReal(THREE, { version });
  const s = String(version) === '0' ? -1 : 1;
  const huesos = {};
  for (const n of HUESOS_MOTOR) huesos[n] = vrm.humanoid.getNormalizedBoneNode(n);
  const h = {
    vrm, s, huesos, t: 0, modelo: sinModelo ? null : vrm, eventos: [], encuadres: [], miradas: [], exprMotor: {}, els: [],
    est: { drag: false, hablando: false, baile: false, mmd: false },
  };
  // Cámara falsa: 'cuerpo' la aleja (z 3), retrato/null la acerca (z 1.2), como encuadrarCtx del motor
  h.camara = { position: { x: 0, y: 1.3, z: 1.2 } };
  h.ctx = {
    THREE, vrm: () => h.modelo, get huesos() { return huesos; }, sXZ: s, camera: h.camara,
    emitir: (tipo, datos) => h.eventos.push({ tipo, datos }),
    encuadrar: (modo, temporal) => { h.encuadres.push([modo, temporal]); h.camara.position.z = modo === 'cuerpo' ? 3 : 1.2; return modo; },
    setLookAt: (on) => h.miradas.push(on),
    estado: () => h.est,
  };
  h.fetch = crearFetch(archivos);
  const audioNS = {
    ...LuneMMDAudio,
    crear: (o) => LuneMMDAudio.crear({ ...o, crearAudio: () => { const el = audioFalso(audio); h.els.push(el); return el; } }),
  };
  h.m = MMD.instalar(h.ctx, {
    THREE, GLTFLoader, VRMAnimationLoaderPlugin: VRMA.VRMAnimationLoaderPlugin, createVRMAnimationClip: VRMA.createVRMAnimationClip,
    VRMAnimation: VRMA.VRMAnimation, VRMLookAtQuaternionProxy: VRMA.VRMLookAtQuaternionProxy,
    vmd: VMD, audio: audioNS, fetch: h.fetch, origen: ORIGEN, ceder: () => Promise.resolve(),
  });
  return h;
}

/** Un frame como lune_vrm.js: rotation.set de HUESOS, expresiones del motor, pose, trasPose y trasUpdate. */
function paso(h, dt = 1 / 60) {
  h.t += dt;
  for (const n in h.huesos) { const r = POSE_MOTOR[n] || [0, 0, 0]; h.huesos[n].rotation.set(r[0] * h.s, r[1], r[2] * h.s); }
  for (const e of MMD.EXPR_MOTOR) h.vrm.expressionManager.setValue(e, h.exprMotor[e] || 0);
  const el = h.els[h.els.length - 1];
  if (el) el.avanzar(dt);
  h.m.pose({}, dt, h.t, h.est);
  h.baileEnFrame = h.est.baile;              // lo que ve sentarse (orden 85) en este frame
  h.m.trasPose(dt, h.t, h.est);
  h.m.trasUpdate(dt, h.t, h.est);
}
const correr = (h, seg, cada = null) => { const n = Math.round(seg * 60); for (let i = 0; i < n; i++) { if (cada) cada(i); paso(h); } };
const mmd = (h) => h.eventos.filter((e) => e.tipo === 'mmd').map((e) => e.datos);
const fases = (h) => mmd(h).filter((d) => d.fase !== 't').map((d) => d.fase);
const peso = (h) => h.m.api.estado().peso;
const brazoArriba = (h) => angulo(h.huesos.leftUpperArm.quaternion, Q(qGrados(0, 0, h.s, 60)));
const enMotor = (h, hueso) => angulo(h.huesos[hueso].quaternion, qMotor(hueso, h.s));
const cargarVMD = (h, extra = {}) => h.m.api.cargar({ id: 'abcdef012345', tipo: 'vmd', motion: ['/bailes/b1/baile.vmd'], ...extra });

// ── Entrada, reproducción y salida ──────────────────────────────────────────────

test('cargar → listo → sonando: entra en ≈0.5 s y los huesos siguen al clip; encuadre, mirada y muelles', async () => {
  const h = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() } });
  assert.equal(await cargarVMD(h), true);
  assert.deepEqual(fases(h), ['cargando', 'listo', 'sonando']);
  assert.equal(mmd(h)[0].id, 'abcdef012345');
  assert.deepEqual(h.encuadres, [['cuerpo', true]]);
  assert.deepEqual(h.miradas, [false]);
  assert.ok(h.vrm.springBoneManager.reinicios >= 1, 'muelles reiniciados al entrar');
  assert.equal(h.fetch.pedidas[0], ORIGEN + '/bailes/b1/baile.vmd');
  correr(h, 0.25);
  const w = peso(h);
  assert.ok(w > 0.2 && w < 0.9, `a mitad de la entrada (${w})`);
  assert.equal(h.m.ocupado(), true);
  correr(h, 0.30);
  assert.ok(peso(h) >= 0.95, 'a 0.55 s ya ha entrado');
  assert.ok(brazoArriba(h) < 1e-3, 'brazo = 腕·A del clip');
  assert.ok(angulo(h.vrm.huesos.leftIndexProximal.quaternion, Q(qGrados(0, 0, 1, 40))) < 1e-3, 'dedo del clip');
  assert.ok(angulo(h.vrm.huesos.leftShoulder.quaternion, Q(qGrados(0, 0, 1, 10))) < 1e-3, 'hombro del clip');
  cerca(h.vrm.huesos.hips.position.x, 5 * ESCALA, 1e-4, 'cadera: centro × escala');
  cerca(h.vrm.huesos.hips.position.y, 0.95 + ESCALA, 1e-4);
  cerca(h.vrm.expressionManager.getValue('happy'), 1, 1e-6, 'にこり → happy');
  assert.deepEqual(h.m.inhibe(), { idle: 0, seguimiento: 0, caricia: 0, gesto: 0, parpadeo: 1 });
  assert.equal(h.est.mmd, true);
  assert.equal(h.baileEnFrame, true, 'est.baile durante el frame (sentarse no suelta el encuadre)');
  assert.equal(h.est.baile, false, 'y al acabar el frame vuelve a lo de los demás');
  const e = h.m.api.estado();
  assert.equal(e.fase, 'sonando');
  cerca(e.t, 0.55, 0.02);
  cerca(e.total, 10, 1e-6, 'sin canción, la duración del clip');
  correr(h, 0.5);
  assert.ok(mmd(h).some((d) => d.fase === 't' && d.t >= 1), 'evento t cada segundo');
});

test('parar → a 0.7 s los HUESOS igualan la pose del motor, el resto en identidad, cadera en reposo y expresiones del motor', async () => {
  const h = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() } });
  await cargarVMD(h);
  correr(h, 0.6);
  h.exprMotor.happy = 0.3;
  assert.equal(h.m.api.parar(), true);
  assert.equal(h.m.api.estado().fase, 'saliendo');
  correr(h, 0.3);
  const w = peso(h);
  assert.ok(w > 0 && w < 1, `saliendo (${w})`);
  assert.ok(brazoArriba(h) > 0.05, 'el brazo va bajando');
  correr(h, 0.4);
  assert.equal(h.m.api.estado().fase, 'parado');
  assert.equal(fases(h).at(-1), 'parado');
  for (const n of HUESOS_MOTOR) assert.ok(enMotor(h, n) < 1e-6, `${n} = pose del motor`);
  assert.ok(angulo(h.vrm.huesos.leftIndexProximal.quaternion, new THREE.Quaternion()) < 1e-9, 'dedo en identidad');
  assert.ok(angulo(h.vrm.huesos.leftShoulder.quaternion, new THREE.Quaternion()) < 1e-9, 'hombro en identidad');
  assert.deepEqual(h.vrm.huesos.hips.position.toArray(), [0, 0.95, 0]);
  cerca(h.vrm.expressionManager.getValue('happy'), 0.3, 1e-9, 'lo del motor');
  cerca(h.vrm.expressionManager.getValue('aa'), 0, 1e-9);
  assert.ok(h.vrm.humanoid.reinicios >= 1, 'resetNormalizedPose');
  assert.deepEqual(h.encuadres.at(-1), [null, undefined]);
  assert.equal(h.miradas.at(-1), true);
  assert.equal(h.m.ocupado(), false);
  assert.deepEqual(h.m.inhibe(), { idle: 1, seguimiento: 1, caricia: 1, gesto: 1, parpadeo: 1 });
  // Parado ya no escribe nada
  h.vrm.huesos.leftIndexProximal.rotation.set(0.3, 0, 0);
  correr(h, 0.1);
  cerca(h.vrm.huesos.leftIndexProximal.rotation.x, 0.3, 1e-9);
  assert.equal(h.m.api.parar(), false, 'parar dos veces');
});

test('fin → aguanta la pose 1.5 s y sale al reposo; con bucle da la vuelta sin fin y reinicia los muelles', async () => {
  const corto = escribirVMD({ huesos: [{ nombre: '左腕', frame: 0, rot: MMDq(BRAZO_IZQ) }, { nombre: '左腕', frame: 30, rot: MMDq(BRAZO_IZQ) }] });
  const h = montar({ archivos: { '/bailes/c/corto.vmd': corto } });
  await h.m.api.cargar({ id: '0123456789ab', tipo: 'vmd', motion: ['/bailes/c/corto.vmd'] });
  correr(h, 1.2);
  assert.equal(fases(h).filter((f) => f === 'fin').length, 1);
  assert.equal(h.m.api.estado().retencion, true);
  cerca(h.m.api.estado().t, 1, 1e-6, 't se queda en el final');
  correr(h, 1.2);
  assert.ok(peso(h) > 0.99 && brazoArriba(h) < 1e-3, 'aguanta la pose');
  correr(h, 0.8);
  assert.equal(h.m.api.estado().fase, 'parado');
  assert.ok(enMotor(h, 'leftUpperArm') < 1e-6, 'brazo abajo');

  const b = montar({ archivos: { '/bailes/c/corto.vmd': corto } });
  await b.m.api.cargar({ id: '0123456789ab', tipo: 'vmd', motion: ['/bailes/c/corto.vmd'], bucle: true });
  const r0 = b.vrm.springBoneManager.reinicios;
  correr(b, 2.6);
  assert.equal(fases(b).includes('fin'), false);
  assert.ok(b.vrm.springBoneManager.reinicios >= r0 + 2, 'reset en cada vuelta');
  assert.ok(b.m.api.estado().t < 1, 'dio la vuelta');
  assert.equal(b.m.api.bucle(false), false);
  correr(b, 1);
  assert.ok(fases(b).includes('fin'), 'sin bucle vuelve a acabar');
});

test('pausa (D5): reposo en 0.6 s con t congelado y la canción en pausa; al seguir, desde el mismo t', async () => {
  const h = montar({ archivos: { '/bailes/p/b.vmd': vmdBaile() }, audio: { duracion: 30 } });
  assert.equal(await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/p/b.vmd'], audio: '/bailes/p/cancion.mp3', volumen: 0.8 }), true);
  const el = h.els[0];
  assert.equal(el.src, ORIGEN + '/bailes/p/cancion.mp3');
  cerca(h.m.api.estado().total, 30, 1e-9, 'la duración la manda la canción');
  correr(h, 1);
  assert.equal(el.paused, false);
  cerca(h.m.api.estado().t, 1, 0.02, 'reloj del audio');
  assert.equal(h.m.api.pausa(true), true);
  assert.equal(el.paused, true);
  correr(h, 0.7);
  assert.equal(peso(h), 0);
  assert.ok(enMotor(h, 'leftUpperArm') < 1e-6 && enMotor(h, 'rightUpperArm') < 1e-6, 'brazos abajo en pausa');
  assert.ok(angulo(h.vrm.huesos.leftIndexProximal.quaternion, new THREE.Quaternion()) < 1e-9);
  const t1 = h.m.api.estado().t;
  correr(h, 0.5);
  assert.equal(h.m.api.estado().t, t1, 't congelado');
  assert.equal(h.m.ocupado(), false, 'en pausa y en reposo no hace falta ir a 60 fps');
  assert.equal(h.m.api.pausa(false), true);
  assert.equal(el.paused, false);
  correr(h, 0.6);
  assert.ok(peso(h) > 0.99);
  cerca(h.m.api.estado().t, t1 + 0.6, 0.03, 'sigue desde el mismo punto');
  assert.ok(brazoArriba(h) < 1e-3);
  assert.deepEqual(fases(h).slice(-2), ['pausado', 'sonando']);
  assert.equal(h.m.api.pausa(), true, 'sin argumento alterna');
  assert.equal(h.m.api.estado().fase, 'pausado');
});

test('arrastre: baja con suav(12) y la canción sigue; hablando: volumen × 0.35 y los visemas del clip a 0', async () => {
  const h = montar({ archivos: { '/bailes/p/b.vmd': vmdBaile() }, audio: { duracion: 30 } });
  await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/p/b.vmd'], audio: '/bailes/p/c.ogg', volumen: 1 });
  const el = h.els[0];
  correr(h, 0.6);
  h.est.drag = true;
  const t0 = h.m.api.estado().t;
  correr(h, 0.5);
  assert.ok(peso(h) < 0.01, `baja al arrastrar (${peso(h)})`);
  assert.equal(el.paused, false, 'la canción sigue');
  cerca(h.m.api.estado().t, t0 + 0.5, 0.03);
  assert.ok(enMotor(h, 'leftUpperArm') < 0.02);
  h.est.drag = false;
  correr(h, 0.6);
  assert.ok(peso(h) > 0.99, 'al soltar vuelve');

  h.exprMotor.aa = 0.5;
  h.est.hablando = true;
  correr(h, 1);
  cerca(el.volume, 0.35, 0.005, 'duck');
  cerca(h.vrm.expressionManager.getValue('aa'), 0.5, 0.005, 'la boca es la de Lune');
  cerca(h.vrm.expressionManager.getValue('happy'), 1, 1e-6, 'lo demás del clip sigue');
  h.est.hablando = false;
  correr(h, 1);
  cerca(el.volume, 1, 0.005);
  cerca(h.vrm.expressionManager.getValue('aa'), 1, 0.005, 'vuelve la boca del clip');
});

test('inhibe y ocupado; parpadeo del clip; enSitio; volumen/offset; alDescargar → error «modelo»', async () => {
  const h = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile({ parpadeo: true }) } });
  assert.equal(h.m.ocupado(), false);
  assert.deepEqual(h.m.inhibe(), { idle: 1, seguimiento: 1, caricia: 1, gesto: 1, parpadeo: 1 });
  await cargarVMD(h);
  correr(h, 0.6);
  assert.equal(h.m.inhibe().parpadeo, 0, 'el clip parpadea: se apaga el del motor');
  cerca(h.vrm.expressionManager.getValue('blink'), 1, 1e-6);
  assert.equal(h.m.api.enSitio(true), true);
  paso(h);
  cerca(h.vrm.huesos.hips.position.x, 0, 1e-9, 'en el sitio: x/z de reposo');
  cerca(h.vrm.huesos.hips.position.y, 0.95 + ESCALA, 1e-4, 'y sigue el clip');
  h.m.api.enSitio(false);
  paso(h);
  cerca(h.vrm.huesos.hips.position.x, 5 * ESCALA, 1e-4);
  assert.equal(h.m.api.volumen(3), 1);
  assert.equal(h.m.api.offset(-900), -500);
  const t = h.m.api.estado().t;
  h.m.api.offset(0);
  cerca(h.m.api.estado().t, t + 0.5, 1e-6, 'sin canción el offset mueve el reloj');
  h.m.alDescargar();
  assert.deepEqual(mmd(h).at(-1), { fase: 'error', id: 'abcdef012345', mensaje: 'modelo' });
  assert.equal(h.m.api.estado().fase, 'error');
  assert.deepEqual(h.encuadres.at(-1), [null, undefined]);
  assert.equal(h.miradas.at(-1), true);
  assert.equal(h.m.ocupado(), false);
  h.m.alDescargar();
  assert.equal(mmd(h).filter((d) => d.fase === 'error').length, 1, 'sin nada activo no avisa');
});

test('siguiente: transición de 0.5 s desde la pose que se ve; lo que el nuevo no mueve vuelve al reposo', async () => {
  const B = escribirVMD({ huesos: [{ nombre: '左腕', frame: 0, rot: MMDq(qGrados(0, 0, 1, -30)) }, { nombre: '左腕', frame: 300, rot: MMDq(qGrados(0, 0, 1, -30)) }] });
  const h = montar({ archivos: { '/bailes/a/a.vmd': vmdBaile(), '/bailes/b/b.vmd': B } });
  await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/a/a.vmd'] });
  correr(h, 0.6);
  const antes = h.huesos.leftUpperArm.quaternion.clone();
  assert.equal(await h.m.api.cargar({ id: 'bbbbbbbbbbbb', tipo: 'vmd', motion: ['/bailes/b/b.vmd'] }), true);
  assert.equal(h.m.api.estado().transicion, true);
  assert.equal(h.m.api.estado().id, 'bbbbbbbbbbbb');
  paso(h);
  assert.ok(angulo(h.huesos.leftUpperArm.quaternion, antes) < 0.05, 'sin salto');
  correr(h, 0.6);
  assert.equal(h.m.api.estado().transicion, false);
  assert.ok(angulo(h.huesos.leftUpperArm.quaternion, Q(qGrados(0, 0, 1, -65))) < 1e-3, 'la pose del nuevo');
  assert.ok(angulo(h.vrm.huesos.leftIndexProximal.quaternion, new THREE.Quaternion()) < 1e-6, 'el dedo del viejo vuelve a identidad');
  assert.ok(angulo(h.vrm.huesos.leftShoulder.quaternion, new THREE.Quaternion()) < 1e-6);
  cerca(h.vrm.expressionManager.getValue('happy'), 0, 1e-6, 'la cara del viejo se apaga');
  assert.deepEqual(fases(h), ['cargando', 'listo', 'sonando', 'cargando', 'listo', 'sonando']);
});

test('otro baile que tarda en cargar: tras pausa (D5) o parar, el viejo NO vuelve a peso 1 (brazos en reposo); sonando, aguanta su pose', async () => {
  const tarda = () => { let soltar; const espera = new Promise((r) => { soltar = r; }); return { espera, soltar }; };
  const angBrazo = (h) => enMotor(h, 'leftUpperArm') * 180 / Math.PI;
  // 1) En pausa y «siguiente»: mientras carga el nuevo, el viejo sigue en reposo (r910_pausa_cargar: 125.9° antes)
  let t = tarda();
  let h = montar({ archivos: { '/bailes/a/a.vmd': vmdBaile(), '/bailes/b/b.vmd': { bytes: vmdBaile(), espera: t.espera } } });
  await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/a/a.vmd'] });
  correr(h, 0.6);
  assert.ok(angBrazo(h) > 90 && peso(h) > 0.99, `sonando: brazo arriba (${angBrazo(h)}°)`);
  h.m.api.pausa(true);
  correr(h, 0.7);
  assert.equal(peso(h), 0);
  let p = h.m.api.cargar({ id: 'bbbbbbbbbbbb', tipo: 'vmd', motion: ['/bailes/b/b.vmd'] });
  await new Promise((r) => setTimeout(r, 5));
  correr(h, 0.7);
  assert.equal(h.m.api.estado().fase, 'cargando');
  assert.equal(peso(h), 0, 'en pausa + cargando: peso 0');
  assert.ok(angBrazo(h) < 1e-3, `brazo en reposo mientras carga (${angBrazo(h)}°)`);
  t.soltar();
  assert.equal(await p, true);
  correr(h, 0.6);
  assert.ok(peso(h) > 0.99 && brazoArriba(h) < 1e-3, 'el nuevo entra al llegar');
  assert.equal(h.m.api.estado().id, 'bbbbbbbbbbbb');

  // 2) Parar (a mitad de la salida, < 0.6 s) y otro cargar: sigue bajando al reposo mientras carga
  t = tarda();
  h = montar({ archivos: { '/bailes/a/a.vmd': vmdBaile(), '/bailes/b/b.vmd': { bytes: vmdBaile(), espera: t.espera } } });
  await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/a/a.vmd'] });
  correr(h, 0.6);
  h.m.api.parar();
  correr(h, 0.2);
  const w0 = peso(h);
  assert.ok(w0 > 0 && w0 < 1, `saliendo (${w0})`);
  p = h.m.api.cargar({ id: 'bbbbbbbbbbbb', tipo: 'vmd', motion: ['/bailes/b/b.vmd'] });
  await new Promise((r) => setTimeout(r, 5));
  correr(h, 0.2);
  assert.ok(peso(h) < w0, `no vuelve a subir (${peso(h)} < ${w0})`);
  correr(h, 0.6);
  assert.equal(peso(h), 0);
  assert.ok(angBrazo(h) < 1e-3, `brazo en reposo (${angBrazo(h)}°)`);
  t.soltar();
  assert.equal(await p, true);
  correr(h, 0.6);
  assert.ok(peso(h) > 0.99, 'y el nuevo entra');

  // 3) Sonando y «siguiente» que tarda: el viejo aguanta su pose (transición suave) …
  t = tarda();
  h = montar({ archivos: { '/bailes/a/a.vmd': vmdBaile(), '/bailes/b/b.vmd': { bytes: vmdBaile(), espera: t.espera } } });
  await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/a/a.vmd'] });
  correr(h, 0.6);
  p = h.m.api.cargar({ id: 'bbbbbbbbbbbb', tipo: 'vmd', motion: ['/bailes/b/b.vmd'] });
  await new Promise((r) => setTimeout(r, 5));
  correr(h, 0.5);
  assert.ok(peso(h) > 0.99 && brazoArriba(h) < 1e-3, 'sonando + cargando: aguanta la pose');
  // … salvo que Python lo pause mientras carga (cedido a un juego, pausa de la persona): al reposo
  h.m.api.pausa(true);
  correr(h, 0.7);
  assert.equal(peso(h), 0);
  assert.ok(angBrazo(h) < 1e-3, 'pausado mientras carga: reposo');
  t.soltar();
  assert.equal(await p, true);
});

test('encuadre: si el baile procedural que se funde lo quita, se vuelve a poner; al acabar no se suelta si ese baile sigue', async () => {
  const h = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() } });
  await cargarVMD(h);
  correr(h, 0.3);
  h.ctx.encuadrar(null);                     // baileProc al llegar su peso a 0 (soltarEncuadre)
  assert.equal(h.camara.position.z, 1.2);
  paso(h);
  assert.deepEqual(h.encuadres.at(-1), ['cuerpo', true]);
  assert.equal(h.camara.position.z, 3);
  h.est.grande = true;                       // en pantalla grande la cámara es de 'grande'
  h.camara.position.z = 7;
  paso(h);
  assert.equal(h.camara.position.z, 7);
  h.est.grande = false;
  paso(h);
  assert.equal(h.camara.position.z, 3);
  // Al acabar el MMD, Python reanuda el baile procedural: pone est.baile antes que nosotros
  h.m.api.parar();
  const n = h.encuadres.length;
  correr(h, 0.8, () => { h.est.baile = true; });
  assert.equal(h.m.api.estado().fase, 'parado');
  assert.equal(h.encuadres.slice(n).some((e) => e[0] === null), false, 'no le quita el encuadre al otro baile');
  assert.equal(h.miradas.at(-1), true);
  assert.equal(h.est.baile, true, 'el est.baile del otro no se toca');
});

// ── .vrma ───────────────────────────────────────────────────────────────────────

const VRMA_OK = crearVRMA({ pistas: {
  rot: { leftUpperArm: { t: [0, 2], v: [...qGrados(0, 0, 1, 60), ...qGrados(0, 0, 1, 60)] } },
  cadera: { t: [0, 2], v: [0, 0.95, 0.1, 0, 0.95, 0.1] },
  expr: { happy: { t: [0, 2], v: [0.7, 0.7] } },
  exprCustom: { propia: { t: [0, 2], v: [1, 1] } },
  mirada: { t: [0, 2], v: [...qGrados(0, 1, 0, 20), ...qGrados(0, 1, 0, 20)] },
} });

test('.vrma por GLTFLoader real + VRMAnimationLoaderPlugin: huesos, cadera, expresiones, mirada; VRM 0.x igual en el mundo', async () => {
  const manos = {};
  for (const version of ['1', '0']) {
    const h = montar({ version, archivos: { '/bailes/v/baile.vrma': VRMA_OK } });
    assert.equal(await h.m.api.cargar({ id: 'cccccccccccc', tipo: 'vrma', motion: ['/bailes/v/baile.vrma'] }), true);
    correr(h, 0.6);
    manos[version] = mundo(h.vrm, 'leftHand');
    const proxy = h.vrm.scene.children.find((o) => o instanceof VRMA.VRMLookAtQuaternionProxy);
    assert.ok(proxy, 'VRMLookAtQuaternionProxy en la escena');
    if (version === '1') {
      assert.ok(angulo(h.huesos.leftUpperArm.quaternion, Q(qGrados(0, 0, 1, 60))) < 1e-3);
      cerca(h.vrm.lookAt.yaw, 20, 0.01, 'mirada del clip');
      cerca(h.vrm.huesos.hips.position.z, 0.1, 1e-4);
    }
    cerca(h.vrm.expressionManager.getValue('happy'), 0.7, 1e-6);
    cerca(h.vrm.expressionManager.getValue('propia'), 1, 1e-6);
    h.m.api.parar();
    correr(h, 0.7);
    assert.equal(h.m.api.estado().fase, 'parado');
    cerca(h.vrm.expressionManager.getValue('propia'), 0, 1e-9, 'expresión ajena al motor a 0');
    assert.equal(h.vrm.scene.children.includes(proxy), false, 'fuera el proxy');
    assert.equal(h.vrm.lookAt.yaw, 0);
    assert.ok(enMotor(h, 'leftUpperArm') < 1e-6);
  }
  assert.ok(manos['0'].distanceTo(manos['1']) < 1e-4, 'con VRM 0.x la mano queda en el mismo sitio del mundo');
});

test('.vrma + VMD de labios: la cara del VMD se suma sin pisar la del .vrma; si no vale, el baile sigue sin ella', async () => {
  const labios = escribirVMD({ morfos: [{ nombre: 'まばたき', frame: 0, peso: 1 }, { nombre: 'にこり', frame: 0, peso: 0.1 }] });
  const archivos = { '/bailes/v/baile.vrma': VRMA_OK, '/bailes/v/labios.vmd': labios, '/bailes/v/roto.vmd': new Uint8Array(8) };
  const h = montar({ archivos });
  assert.equal(await h.m.api.cargar({ id: 'cccccccccccc', tipo: 'vrma', motion: ['/bailes/v/baile.vrma'], cara: ['/bailes/v/labios.vmd'] }), true);
  correr(h, 0.6);
  cerca(h.vrm.expressionManager.getValue('blink'), 1, 1e-6, 'まばたき del VMD');
  cerca(h.vrm.expressionManager.getValue('happy'), 0.7, 1e-6, 'la del .vrma manda');
  assert.equal(h.m.inhibe().parpadeo, 0);
  const r = montar({ archivos });
  assert.equal(await r.m.api.cargar({ id: 'cccccccccccc', tipo: 'vrma', motion: ['/bailes/v/baile.vrma'], cara: ['/bailes/v/roto.vmd'] }), true);
  correr(r, 0.6);
  assert.ok(angulo(r.huesos.leftUpperArm.quaternion, Q(qGrados(0, 0, 1, 60))) < 1e-3);
});

test('.vrma con uri externa o sin VRMC_vrm_animation → error sin pedir nada fuera; topes de tamaño', async () => {
  const pista = { rot: { leftUpperArm: { t: [0, 1], v: [0, 0, 0, 1, 0, 0, 0, 1] } } };
  const casos = [
    ['/bailes/v/uri.vrma', crearVRMA({ pistas: pista, uri: 'http://malo.example/robo.bin' }), /uri/],
    ['/bailes/v/img.vrma', crearVRMA({ pistas: pista, imagenUri: 'file:///C:/secreto.png' }), /uri/],
    ['/bailes/v/sin.vrma', crearVRMA({ pistas: pista, sinExtension: true }), /VRMC_vrm_animation/],
    ['/bailes/v/basura.vrma', new Uint8Array(64), /no es un GLB/],
  ];
  for (const [ruta, bytes, motivo] of casos) {
    const h = montar({ archivos: { [ruta]: bytes } });
    assert.equal(await h.m.api.cargar({ id: 'dddddddddddd', tipo: 'vrma', motion: [ruta] }), false, ruta);
    const ultimo = mmd(h).at(-1);
    assert.equal(ultimo.fase, 'error');
    assert.match(ultimo.mensaje, motivo);
    assert.deepEqual(h.fetch.pedidas, [ORIGEN + ruta], 'solo se pidió el propio archivo');
    assert.equal(h.m.api.estado().fase, 'error');
  }
  // Content-Length de más: ni se lee el cuerpo
  const g = montar({ archivos: { '/bailes/g/g.vmd': { bytes: new Uint8Array(10), largo: String(33 << 20) } } });
  assert.equal(await g.m.api.cargar({ id: 'eeeeeeeeeeee', tipo: 'vmd', motion: ['/bailes/g/g.vmd'] }), false);
  assert.match(mmd(g).at(-1).mensaje, /demasiado grande/);
  assert.deepEqual(g.fetch.leidos, []);
  // Sin Content-Length: se corta al pasar de 32 MiB leyendo
  const arch = { cuerpo: 'stream', total: 40 << 20, bytes: new Uint8Array(0), largo: null };
  const s = montar({ archivos: { '/bailes/g/s.vmd': arch } });
  assert.equal(await s.m.api.cargar({ id: 'eeeeeeeeeeee', tipo: 'vmd', motion: ['/bailes/g/s.vmd'] }), false);
  assert.match(mmd(s).at(-1).mensaje, /demasiado grande/);
  assert.equal(arch.cancelado, true);
  assert.ok(s.fetch.leidos.length <= 5, 'no lee los 40 MiB');
  // VMD roto y 404
  const r = montar({ archivos: { '/bailes/r/r.vmd': new Uint8Array(40) } });
  assert.equal(await r.m.api.cargar({ id: 'ffffffffffff', tipo: 'vmd', motion: ['/bailes/r/r.vmd'] }), false);
  assert.match(mmd(r).at(-1).mensaje, /VMD/);
  assert.equal(await r.m.api.cargar({ id: 'ffffffffffff', tipo: 'vmd', motion: ['/bailes/r/no.vmd'] }), false);
  assert.match(mmd(r).at(-1).mensaje, /404/);
});

test('rutas: solo /bailes/ y /bailes_cache/ del mismo origen; nada se pide si no valen', async () => {
  const h = montar();
  for (const url of ['/ui/index.html', 'http://evil.example/bailes/x.vmd', '/bailes/../ui/x.vmd', '/bailes/%2e%2e/ui/x.vmd',
    'file:///C:/x.vmd', '/bailes//x.vmd', 'bailes/x.vmd', '/bailes/x.vmd?a=1', '/bailes\\x.vmd', '/bailes/', 'x'.repeat(2000)]) {
    assert.equal(await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: [url] }), false, url);
    assert.equal(mmd(h).at(-1).mensaje, 'ruta no permitida', url);
  }
  assert.equal(await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'vmd', motion: ['/bailes/x.vmd'], audio: 'http://evil.example/a.mp3' }), false);
  assert.equal(await h.m.api.cargar({ id: 'aaaaaaaaaaaa', tipo: 'audio', motion: ['/bailes/x.vmd'] }), false, 'tipo audio es de la animada');
  assert.equal(await h.m.api.cargar('{no json'), false);
  assert.deepEqual(h.fetch.pedidas, []);
  assert.equal(MMD.urlPermitida('/bailes_cache/abc.ogg', ORIGEN), ORIGEN + '/bailes_cache/abc.ogg');
  assert.equal(MMD.urlPermitida(ORIGEN + '/bailes/%E5%8D%83/a.vmd', ORIGEN), ORIGEN + '/bailes/%E5%8D%83/a.vmd');
  assert.equal(MMD.urlPermitida('blob:' + ORIGEN + '/1234', ORIGEN), null);
  assert.equal(MMD.urlPermitida('/bailes/a.vmd', 'file:///C:/'), null, 'origen raro');
});

test('api.orden: las órdenes de Python (ui/companion.py mmd → window.luneMMD) tal cual', async () => {
  const h = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() }, audio: { duracion: 30 } });
  // El payload exacto de datos_mmd_seguros (bpm, fase0 y titulo son de la animada: se ignoran)
  assert.equal(await h.m.api.orden('cargar', {
    id: 'abcdef012345', tipo: 'vmd', audio: '/bailes/b1/c.mp3', motion: ['/bailes/b1/baile.vmd'], cara: [],
    volumen: 0.5, offsetMs: 0, brazoGrados: 35, enSitio: false, bucle: false, bpm: 120, fase0: 0.2, titulo: 'Senbonzakura',
  }), true);
  correr(h, 0.6);
  cerca(h.els[0].volume, 0.5, 1e-6);
  assert.equal(h.m.api.orden('pausa', { on: true }), true);
  assert.equal(h.m.api.estado().fase, 'pausado');
  assert.equal(h.m.api.orden('pausa', { on: false }), true);
  assert.equal(h.m.api.estado().fase, 'sonando');
  assert.equal(h.m.api.orden('volumen', { volumen: 0.25 }), 0.25);
  paso(h);
  cerca(h.els[0].volume, 0.25, 1e-6);
  assert.equal(h.m.api.orden('offset', { offsetMs: 120 }), 120);
  assert.equal(h.m.api.orden('en_sitio', { enSitio: true }), true);
  assert.equal(h.m.api.orden('bucle', { bucle: true }), true);
  assert.equal(h.m.api.estado().bucle, true);
  assert.equal(h.m.api.orden('borrar', {}), false);
  assert.equal(h.m.api.orden('parar', null), true);
  assert.equal(h.m.api.estado().fase, 'saliendo');
});

test('opcionesCarga: listas o planos (motion0..2, cara0..1), JSON, rangos y id saneado', () => {
  const r = MMD.opcionesCarga(JSON.stringify({
    id: 'abc<script>', tipo: 'vmd', motion0: '/bailes/a/1.vmd', motion1: '/bailes/a/2.vmd', cara0: '/bailes/a/labios.vmd',
    audio: '/bailes_cache/0123456789ab.ogg', offsetMs: 9999, brazoGrados: 10, volumen: -1, enSitio: 1, bucle: 0, autoplay: false,
  }), ORIGEN);
  assert.deepEqual(r.datos, {
    id: 'abcscript', tipo: 'vmd', motion: [ORIGEN + '/bailes/a/1.vmd', ORIGEN + '/bailes/a/2.vmd'], cara: [ORIGEN + '/bailes/a/labios.vmd'],
    audio: ORIGEN + '/bailes_cache/0123456789ab.ogg', offsetMs: 500, enSitio: true, bucle: false, brazoGrados: 25, volumen: 0, autoplay: false,
  });
  assert.equal(MMD.opcionesCarga({ tipo: 'vrma', motion: ['/bailes/a.vrma', '/bailes/b.vrma'] }, ORIGEN).error, 'archivos no válidos');
  assert.equal(MMD.opcionesCarga({ tipo: 'vmd', motion: [] }, ORIGEN).error, 'archivos no válidos');
  const d = MMD.opcionesCarga({ tipo: 'vmd', motion: ['/bailes/a.vmd'] }, ORIGEN).datos;
  assert.equal(d.brazoGrados, 35); assert.equal(d.volumen, 1); assert.equal(d.offsetMs, 0); assert.equal(d.autoplay, true);
});

test('sin modelo, cargar espera a alCargar; la canción que no carga o no suena → error y reposo', async () => {
  const h = montar({ sinModelo: true, archivos: { '/bailes/b1/baile.vmd': vmdBaile() } });
  const p = cargarVMD(h);
  await new Promise((r) => setImmediate(r));
  assert.equal(h.m.api.estado().fase, 'cargando');
  h.modelo = h.vrm;
  h.m.alCargar(h.vrm);
  assert.equal(await p, true);
  assert.equal(h.m.api.estado().fase, 'sonando');

  const a = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() }, audio: { fallar: true } });
  assert.equal(await cargarVMD(a, { audio: '/bailes/b1/raro.m4a' }), false);
  assert.match(mmd(a).at(-1).mensaje, /canción/);
  assert.equal(fases(a).includes('listo'), false);
  assert.deepEqual(a.encuadres, [], 'ni siquiera entra');

  // El navegador rechaza play(): no baila en silencio para siempre
  const r = montar({ archivos: { '/bailes/b1/baile.vmd': vmdBaile() }, audio: { rechazarPlay: true } });
  assert.equal(await cargarVMD(r, { audio: '/bailes/b1/c.mp3' }), true);
  await new Promise((res) => setImmediate(res));
  assert.equal(r.m.api.estado().fase, 'error');
  assert.match(mmd(r).at(-1).mensaje, /no se puede reproducir.*NotAllowedError/);
  correr(r, 0.8);
  assert.equal(r.m.api.estado().peso, 0);
  assert.ok(enMotor(r, 'leftUpperArm') < 1e-6, 'y vuelve al reposo');
  assert.equal(fases(r).includes('parado'), false, 'tras un error no hay «parado»');
});

test('EXPR_MOTOR coincide con las expresiones que escribe lune_vrm.js en cada frame', () => {
  const src = readFileSync(new URL('../../ui_web/vrm/lune_vrm.js', import.meta.url), 'utf8');
  const lista = (nombre) => {
    const m = src.match(new RegExp(`const ${nombre} = \\[([^\\]]*)\\]`));
    assert.ok(m, `${nombre} en lune_vrm.js`);
    return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
  };
  const parpadeos = ['blink', 'blinkLeft', 'blinkRight'].filter((n) => new RegExp(`setExpr\\('${n}'`).test(src));
  assert.deepEqual([...MMD.EXPR_MOTOR].sort(), [...lista('EMOCIONES'), ...lista('VISEMAS'), ...parpadeos].sort());
});

// ── Con el motor de verdad ──────────────────────────────────────────────────────

const URL_MOTOR = new URL('../../ui_web/vrm/lune_vrm.js', import.meta.url);
const URL_FALSO = new URL('./three_falso.mjs', import.meta.url).href;
// three real con el renderizador y el reloj falsos (sin WebGL; el reloj lo mueve el test)
const HIBRIDO = aDataURL(`export * from '${URL_THREE}';\nexport { WebGLRenderer, Clock } from '${URL_FALSO}';\n`);
const motorReal = await import(aDataURL(reescribirImports(readFileSync(URL_MOTOR, 'utf8'), URL_MOTOR, { three: HIBRIDO })));

test('con el motor de verdad: bailando los brazos suben y al parar las manos acaban bajo los hombros (VRM 1.0 y 0.x)', async () => {
  const baile = vmdBaile({ dedo: true, cadera: false });
  for (const version of ['1', '0']) {
    frames.length = 0;
    const m = motorReal.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm' });
    const vrm = crearVRMReal(THREE, { version });
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    assert.equal(m.ctx.sXZ, version === '0' ? -1 : 1);
    quietaSinIdles(m);
    const f = crearFetch({ '/bailes/m/b.vmd': baile });
    const mod = m.registrar((ctx) => MMD.instalar(ctx, {
      GLTFLoader, VRMAnimationLoaderPlugin: VRMA.VRMAnimationLoaderPlugin, createVRMAnimationClip: VRMA.createVRMAnimationClip,
      VRMAnimation: VRMA.VRMAnimation, VRMLookAtQuaternionProxy: VRMA.VRMLookAtQuaternionProxy,
      vmd: VMD, audio: LuneMMDAudio, fetch: f, origen: ORIGEN, ceder: () => Promise.resolve(),
    }));
    assert.equal(mod.nombre, 'mmd');
    vaciarCola();
    assert.equal(await m.mod('mmd', 'cargar', { id: '0123456789ab', tipo: 'vmd', motion: ['/bailes/m/b.vmd'] }), true);
    correrMotor(1);
    for (const lado of ['left', 'right']) {
      const b = brazoMundo(vrm, lado, version);
      assert.ok(b.mano[1] > 0.5, `${lado} v${version}: bailando, mano por encima del hombro (${b.mano[1].toFixed(2)})`);
    }
    assert.equal(m.ctx.estado().mmd, true);
    m.mod('mmd', 'parar');
    correrMotor(0.8);
    assert.equal(m.mod('mmd', 'estado').fase, 'parado');
    for (const lado of ['left', 'right']) {
      const b = brazoMundo(vrm, lado, version);
      assert.ok(b.mano[1] < -0.5 && b.codo[1] < 0, `${lado} v${version}: mano bajo el hombro (${b.mano[1].toFixed(2)})`);
    }
    assert.ok(angulo(vrm.huesos.leftIndexProximal.quaternion, new THREE.Quaternion()) < 1e-6, 'dedo en identidad');
    const cola = vaciarCola().filter((e) => e.t === 'mmd').map((e) => e.d.fase);
    assert.deepEqual(cola.filter((x) => x !== 't'), ['cargando', 'listo', 'sonando', 'parado']);
    m.destruir();
  }
});
