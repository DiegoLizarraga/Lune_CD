// tests/js/vmd_fabrica.mjs — fábrica de datos sintéticos para los tests del reproductor MMD
// (corte 9): escribe VMD v1/v2 con huesos, morfos, cámara, luz, sombra e IK (nombres en
// Shift_JIS con una tabla mínima en bytes literales: en Node no hay codificador SJIS), GLB
// .vrma con VRMC_vrm_animation, y un VRM «falso» hecho con Object3D DE VERDAD de three.js
// (huesos normalizados, expresiones con peso, mirada y muelles) para createVRMAnimationClip, y
// un <audio> falso para la canción. También carga three r160, GLTFLoader y three-vrm-animation del vendor con los imports
// reescritos (en Node no hay importmap). No es un test (no acaba en .test.mjs).
import { readFileSync } from 'node:fs';

// ── three.js del vendor, GLTFLoader y three-vrm-animation (una sola instancia de three) ──
const VENDOR = new URL('../../ui_web/vendor/three/', import.meta.url);
export const URL_THREE = new URL('three.module.min.js', VENDOR).href;
export const aDataURL = (src) => 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
const conThree = (src) => src.replace(/from\s*(['"])three\1/g, `from '${URL_THREE}'`);

export const THREE = await import(URL_THREE);
const DATA_BGU = aDataURL(conThree(readFileSync(new URL('utils/BufferGeometryUtils.js', VENDOR), 'utf8')));
export const { GLTFLoader } = await import(aDataURL(conThree(readFileSync(new URL('loaders/GLTFLoader.js', VENDOR), 'utf8'))
  .replace(/from\s*'\.\.\/utils\/BufferGeometryUtils\.js'/g, `from '${DATA_BGU}'`)));
export const VRMA = await import(aDataURL(conThree(readFileSync(new URL('three-vrm-animation.module.min.js', VENDOR), 'utf8'))));

// ── Shift_JIS (cp932) de los nombres que usan los tests ──────────────────────────
export const SJIS = Object.freeze({
  '全ての親': '915382c482cc9065', 'センター': '835a8393835e815b', 'グルーブ': '834f838b815b8375', '腰': '8d98',
  '下半身': '89ba94bc9067', '上半身': '8fe394bc9067', '上半身２': '8fe394bc90678251', '上半身2': '8fe394bc906732',
  '上半身３': '8fe394bc90678252', '首': '8ef1', '頭': '93aa', '両目': '97bc96da', '左目': '8db696da', '右目': '894596da',
  '左肩': '8db68ca8', '右肩': '89458ca8', '左肩P': '8db68ca850', '左腕': '8db69872', '右腕': '89459872',
  '左腕捩': '8db698729d80', '右腕捩': '894598729d80', '左ひじ': '8db682d082b6', '右ひじ': '894582d082b6',
  '左手捩': '8db68ee89d80', '右手捩': '89458ee89d80', '左手首': '8db68ee88ef1', '右手首': '89458ee88ef1',
  '左親指０': '8db690658e77824f', '左親指１': '8db690658e778250', '左親指２': '8db690658e778251',
  '左人指１': '8db6906c8e778250', '左人指２': '8db6906c8e778251', '左人指３': '8db6906c8e778252', '右人指１': '8945906c8e778250',
  '左足': '8db691ab', '右足': '894591ab', '左ひざ': '8db682d082b4', '右ひざ': '894582d082b4',
  '左足首': '8db691ab8ef1', '右足首': '894591ab8ef1', '左足先EX': '8db691ab90e64558', '右足先EX': '894591ab90e64558',
  '左足ＩＫ': '8db691ab8268826a', '右足ＩＫ': '894591ab8268826a', '左つま先ＩＫ': '8db682c282dc90e68268826a',
  '右つま先ＩＫ': '894582c282dc90e68268826a', '左足IK親': '8db691ab494b9065', '右足IK親': '894591ab494b9065', '左足D': '8db691ab44',
  'まばたき': '82dc82ce82bd82ab', 'ウィンク': '834583428393834e', 'ウィンク２': '834583428393834e8251',
  'ウィンク右': '834583428393834e8945', 'ｳｨﾝｸ２右': 'b3a8ddb882518945', 'あ': '82a0', 'い': '82a2', 'う': '82a4',
  'え': '82a6', 'お': '82a8', 'にこり': '82c982b182e8', '怒り': '937b82e8', '困る': '8da282e9', '真面目': '905e96ca96da',
  '笑い': '8fce82a2', '眉上': '94fb8fe3', '初音ミク': '8f8989b9837e834e',
});

const hexABytes = (h) => Uint8Array.from(h.match(/../g).map((b) => parseInt(b, 16)));

/** Nombre → bytes: Uint8Array tal cual, ASCII tal cual, o de la tabla SJIS (si no está, error). */
export function sjis(nombre) {
  if (nombre instanceof Uint8Array) return nombre;
  const s = String(nombre);
  if (Object.prototype.hasOwnProperty.call(SJIS, s)) return hexABytes(SJIS[s]);
  if (/^[\x20-\x7e]*$/.test(s)) return Uint8Array.from(s, (c) => c.charCodeAt(0));
  throw new Error(`vmd_fabrica: falta «${s}» en la tabla SJIS`);
}

/** Interpolación de 64 B: curvas = [{x1,y1,x2,y2}] para X, Y, Z, R en 0..127 (fila 0 + 3 copias desplazadas). */
export function ipDe(curvas = null) {
  const c = curvas || [0, 1, 2, 3].map(() => ({ x1: 20, y1: 20, x2: 107, y2: 107 }));
  const fila = new Uint8Array(16);
  for (let k = 0; k < 4; k++) {
    const q = c[k] || c[0];
    fila[k] = q.x1; fila[k + 4] = q.y1; fila[k + 8] = q.x2; fila[k + 12] = q.y2;
  }
  const ip = new Uint8Array(64);
  for (let r = 0; r < 4; r++) for (let i = 0; i < 16; i++) ip[r * 16 + i] = i + r < 16 ? fila[i + r] : 0;
  return ip;
}
export const IP_LINEAL = ipDe();

/** Cuaternión [x, y, z, w] de eje (se normaliza) y ángulo en grados. */
export const qGrados = (x, y, z, grados) => {
  const l = Math.hypot(x, y, z) || 1, a = grados * Math.PI / 180, s = Math.sin(a / 2) / l;
  return [x * s, y * s, z * s, Math.cos(a / 2)];
};

class Escritor {
  constructor() { this.partes = []; this.largo = 0; }
  bytes(b) { this.partes.push(Uint8Array.from(b)); this.largo += b.length; }
  u8(v) { this.bytes([v & 255]); }
  u32(v) { const b = new Uint8Array(4); new DataView(b.buffer).setUint32(0, v >>> 0, true); this.bytes(b); }
  f32(v) { const b = new Uint8Array(4); new DataView(b.buffer).setFloat32(0, v, true); this.bytes(b); }
  campo(bytes, largo) { const b = new Uint8Array(largo); b.set(bytes.subarray(0, largo)); this.bytes(b); }
  fin() { const out = new Uint8Array(this.largo); let p = 0; for (const x of this.partes) { out.set(x, p); p += x.length; } return out; }
}

/**
 * VMD sintético. huesos: [{nombre, frame, pos=[0,0,0], rot=[0,0,0,1], ip}] (en convención MMD, mano
 * izquierda), morfos: [{nombre, frame, peso}], camara/luces/sombras: cuántos registros vacíos,
 * ik: null (sin sección) o [{frame, visible, ik: {nombre: bool}}]. cuentas: {huesos, morfos,
 * ik} sobrescribe la cuenta escrita (para archivos rotos). version 1 = cabecera vieja (modelo 10 B).
 */
export function escribirVMD({ version = 2, modelo = 'Lune', huesos = [], morfos = [], camara = 0, luces = 0, sombras = 0, ik = null, cuentas = {}, sinMorfos = false } = {}) {
  const e = new Escritor();
  const cab = version === 1 ? 'Vocaloid Motion Data file' : 'Vocaloid Motion Data 0002';
  e.campo(sjis(cab), 30);
  e.campo(sjis(modelo), version === 1 ? 10 : 20);
  e.u32(cuentas.huesos ?? huesos.length);
  for (const h of huesos) {
    e.campo(sjis(h.nombre), 15);
    e.u32(h.frame | 0);
    for (const v of h.pos || [0, 0, 0]) e.f32(v);
    for (const v of h.rot || [0, 0, 0, 1]) e.f32(v);
    e.bytes(h.ip || IP_LINEAL);
  }
  if (sinMorfos) return e.fin();
  e.u32(cuentas.morfos ?? morfos.length);
  for (const m of morfos) { e.campo(sjis(m.nombre), 15); e.u32(m.frame | 0); e.f32(m.peso); }
  e.u32(camara);
  for (let i = 0; i < camara; i++) { e.u32(i); e.bytes(new Uint8Array(57)); }
  e.u32(luces);
  for (let i = 0; i < luces; i++) { e.u32(i); e.bytes(new Uint8Array(24)); }
  e.u32(sombras);
  for (let i = 0; i < sombras; i++) { e.u32(i); e.bytes(new Uint8Array(5)); }
  if (ik) {
    e.u32(cuentas.ik ?? ik.length);
    for (const f of ik) {
      e.u32(f.frame | 0); e.u8(f.visible === false ? 0 : 1);
      const nombres = Object.keys(f.ik || {});
      e.u32(f.cuantos ?? nombres.length);
      for (const n of nombres) { e.campo(sjis(n), 20); e.u8(f.ik[n] ? 1 : 0); }
    }
  }
  return e.fin();
}

// ── GLB / VRMA ──────────────────────────────────────────────────────────────────

/** Contenedor GLB: JSON (relleno con espacios) + BIN opcional (relleno con ceros). */
export function escribirGLB(json, bin = null) {
  const texto = new TextEncoder().encode(JSON.stringify(json));
  const jl = Math.ceil(texto.length / 4) * 4;
  const bl = bin ? Math.ceil(bin.length / 4) * 4 : 0;
  const total = 12 + 8 + jl + (bin ? 8 + bl : 0);
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, 0x46546C67, true); dv.setUint32(4, 2, true); dv.setUint32(8, total, true);
  dv.setUint32(12, jl, true); dv.setUint32(16, 0x4E4F534A, true);
  out.fill(0x20, 20, 20 + jl); out.set(texto, 20);
  if (bin) {
    const p = 20 + jl;
    dv.setUint32(p, bl, true); dv.setUint32(p + 4, 0x004E4942, true);
    out.set(bin, p + 8);
  }
  return out;
}

// Esqueleto normalizado de reposo (VRM 1.0: mira a +Z, izquierda = +X): [padre, posición local]
export const ESQUELETO = (() => {
  const e = {
    hips: [null, [0, 0.95, 0]], spine: ['hips', [0, 0.08, 0]], chest: ['spine', [0, 0.12, 0]],
    upperChest: ['chest', [0, 0.10, 0]], neck: ['upperChest', [0, 0.12, 0]], head: ['neck', [0, 0.08, 0]],
  };
  for (const [v, s] of [['left', 1], ['right', -1]]) {
    e[v + 'Eye'] = ['head', [0.03 * s, 0.06, 0.07]];
    e[v + 'Shoulder'] = ['upperChest', [0.03 * s, 0.08, -0.01]];
    e[v + 'UpperArm'] = [v + 'Shoulder', [0.10 * s, 0, 0]];
    e[v + 'LowerArm'] = [v + 'UpperArm', [0.25 * s, 0, 0]];
    e[v + 'Hand'] = [v + 'LowerArm', [0.23 * s, 0, 0]];
    e[v + 'ThumbMetacarpal'] = [v + 'Hand', [0.02 * s, -0.01, 0.02]];
    e[v + 'ThumbProximal'] = [v + 'ThumbMetacarpal', [0.03 * s, 0, 0.01]];
    e[v + 'ThumbDistal'] = [v + 'ThumbProximal', [0.02 * s, 0, 0]];
    e[v + 'IndexProximal'] = [v + 'Hand', [0.08 * s, 0, 0.02]];
    e[v + 'IndexIntermediate'] = [v + 'IndexProximal', [0.03 * s, 0, 0]];
    e[v + 'IndexDistal'] = [v + 'IndexIntermediate', [0.02 * s, 0, 0]];
    e[v + 'UpperLeg'] = ['hips', [0.09 * s, -0.06, 0]];
    e[v + 'LowerLeg'] = [v + 'UpperLeg', [0, -0.42, 0]];
    e[v + 'Foot'] = [v + 'LowerLeg', [0, -0.40, 0]];
    e[v + 'Toes'] = [v + 'Foot', [0, -0.05, 0.12]];
  }
  return e;
})();

export const EXPRESIONES_VRM = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral',
  'aa', 'ih', 'ou', 'ee', 'oh', 'blink', 'blinkLeft', 'blinkRight', 'propia'];

/**
 * .vrma sintético. pistas: {rot: {hueso: {t: [s], v: [x,y,z,w,…]}}, cadera: {t, v: [x,y,z,…]},
 * expr: {preset: {t, v: [peso,…]}}, exprCustom: {nombre: {t, v}}, mirada: {t, v: [x,y,z,w,…]}}. uri: pone buffers[0].uri (y sin
 * BIN) para probar el rechazo; sinExtension: sin VRMC_vrm_animation.
 */
export function crearVRMA({ pistas = {}, uri = null, sinExtension = false, imagenUri = null } = {}) {
  const nombres = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head', 'leftUpperArm', 'leftLowerArm', 'leftHand',
    'rightUpperArm', 'rightLowerArm', 'rightHand', 'leftUpperLeg', 'leftLowerLeg', 'leftFoot', 'rightUpperLeg', 'rightLowerLeg', 'rightFoot'];
  const nodos = [], indice = {};
  for (const h of nombres) { indice[h] = nodos.length; nodos.push({ name: h, translation: ESQUELETO[h][1].slice() }); }
  for (const h of nombres) {
    const padre = ESQUELETO[h][0];
    const p = padre === 'leftShoulder' || padre === 'rightShoulder' ? 'upperChest' : padre;
    if (p) (nodos[indice[p]].children || (nodos[indice[p]].children = [])).push(indice[h]);
  }
  // Los brazos cuelgan de upperChest (sin hombros): su traslación suma la del hombro
  for (const v of ['left', 'right']) {
    const t = nodos[indice[v + 'UpperArm']].translation, h = ESQUELETO[v + 'Shoulder'][1];
    nodos[indice[v + 'UpperArm']].translation = [t[0] + h[0], t[1] + h[1], t[2] + h[2]];
  }
  const exprNodos = {}, customNodos = {};
  for (const p of Object.keys(pistas.expr || {})) { exprNodos[p] = nodos.length; nodos.push({ name: 'expr_' + p }); }
  for (const p of Object.keys(pistas.exprCustom || {})) { customNodos[p] = nodos.length; nodos.push({ name: 'custom_' + p }); }
  const miradaNodo = nodos.length; nodos.push({ name: 'lookAt' });

  const bin = [], accessors = [], bufferViews = [];
  let largo = 0;
  const acc = (arr, tipo, conMinMax = false) => {
    const f = Float32Array.from(arr);
    const b = new Uint8Array(f.buffer);
    bufferViews.push({ buffer: 0, byteOffset: largo, byteLength: b.length });
    bin.push(b); largo += b.length;
    const comp = { SCALAR: 1, VEC3: 3, VEC4: 4 }[tipo];
    const a = { bufferView: bufferViews.length - 1, componentType: 5126, count: f.length / comp, type: tipo };
    if (conMinMax) { a.min = [Math.min(...f)]; a.max = [Math.max(...f)]; }
    accessors.push(a);
    return accessors.length - 1;
  };
  const channels = [], samplers = [];
  const canal = (nodo, camino, t, v, tipo) => {
    samplers.push({ input: acc(t, 'SCALAR', true), output: acc(v, tipo), interpolation: 'LINEAR' });
    channels.push({ sampler: samplers.length - 1, target: { node: nodo, path: camino } });
  };
  for (const [h, p] of Object.entries(pistas.rot || {})) canal(indice[h], 'rotation', p.t, p.v, 'VEC4');
  if (pistas.cadera) canal(indice.hips, 'translation', pistas.cadera.t, pistas.cadera.v, 'VEC3');
  for (const [pr, p] of Object.entries(pistas.expr || {})) canal(exprNodos[pr], 'translation', p.t, p.v.flatMap((x) => [x, 0, 0]), 'VEC3');
  for (const [pr, p] of Object.entries(pistas.exprCustom || {})) canal(customNodos[pr], 'translation', p.t, p.v.flatMap((x) => [x, 0, 0]), 'VEC3');
  if (pistas.mirada) canal(miradaNodo, 'rotation', pistas.mirada.t, pistas.mirada.v, 'VEC4');

  const humanBones = {};
  for (const h of nombres) humanBones[h] = { node: indice[h] };
  const preset = {}, custom = {};
  for (const [p, i] of Object.entries(exprNodos)) preset[p] = { node: i };
  for (const [p, i] of Object.entries(customNodos)) custom[p] = { node: i };
  const json = {
    asset: { version: '2.0', generator: 'vmd_fabrica' },
    scene: 0,
    scenes: [{ nodes: [indice.hips, ...Object.values(exprNodos), ...Object.values(customNodos), miradaNodo] }],
    nodes: nodos, accessors, bufferViews,
    buffers: [{ byteLength: largo }],
    animations: channels.length ? [{ channels, samplers }] : [],
  };
  if (!sinExtension) {
    json.extensionsUsed = ['VRMC_vrm_animation'];
    json.extensions = { VRMC_vrm_animation: { specVersion: '1.0', humanoid: { humanBones }, expressions: { preset, custom }, lookAt: { node: miradaNodo } } };
  }
  if (imagenUri) json.images = [{ uri: imagenUri }];
  const datos = new Uint8Array(largo);
  let p = 0;
  for (const b of bin) { datos.set(b, p); p += b.length; }
  if (uri) { json.buffers[0].uri = uri; return escribirGLB(json, null); }
  return escribirGLB(json, datos);
}

// ── VRM falso con three.js de verdad ────────────────────────────────────────────

/**
 * VRM con Object3D reales: huesos normalizados 'Normalized_<hueso>' (identidad en reposo) bajo
 * vrm.scene, humanoid {getNormalizedBoneNode, normalizedRestPose, resetNormalizedPose},
 * expresiones como Object3D 'VRMExpression_<n>' con `weight`, lookAt {yaw, pitch}, muelles con
 * reset(). version '0': el rig nace girado 180° (x/z de las posiciones negadas) y la escena va
 * girada (lo que hace rotateVRM0). sin: huesos que el modelo no trae (sus hijos cuelgan del abuelo).
 */
export function crearVRMReal(T = THREE, { version = '1', expresiones = EXPRESIONES_VRM, sin = [], conMalla = true } = {}) {
  const v0 = String(version) === '0';
  const scene = new T.Group(); scene.name = 'VRMRaiz';
  const raiz = new T.Object3D(); raiz.name = 'NormalizedRoot'; scene.add(raiz);
  const huesos = {}, rest = {};
  for (const [h, [padre, off]] of Object.entries(ESQUELETO)) {
    if (sin.includes(h)) continue;
    const o = off.slice();
    let p = padre;
    while (p && !huesos[p]) { const [pp, po] = ESQUELETO[p]; o[0] += po[0]; o[1] += po[1]; o[2] += po[2]; p = pp; }
    const pos = v0 ? [-o[0], o[1], -o[2]] : o;
    const n = new T.Object3D(); n.name = 'Normalized_' + h;
    n.position.set(pos[0], pos[1], pos[2]);
    (p ? huesos[p] : raiz).add(n);
    huesos[h] = n;
    rest[h] = { position: pos.slice(), rotation: [0, 0, 0, 1] };
  }
  if (v0) scene.rotation.y = Math.PI;
  if (conMalla) { const m = new T.Mesh(new T.BoxGeometry(0.6, 1.6, 0.3)); m.position.y = 0.8; scene.add(m); }
  class Expresion extends T.Object3D {
    constructor(n) { super(); this.expressionName = n; this.name = 'VRMExpression_' + n; this.weight = 0; }
  }
  const lista = expresiones.map((n) => new Expresion(n));
  for (const e of lista) scene.add(e);
  const porNombre = new Map(lista.map((e) => [e.expressionName, e]));
  const expressionManager = {
    expressions: lista,
    getExpression: (n) => porNombre.get(n) || null,
    getExpressionTrackName: (n) => { const e = porNombre.get(n); return e ? `${e.name}.weight` : null; },
    setValue: (n, v) => { const e = porNombre.get(n); if (e) e.weight = Math.min(1, Math.max(0, Number(v) || 0)); },
    getValue: (n) => { const e = porNombre.get(n); return e ? e.weight : null; },
    valores: () => Object.fromEntries(lista.map((e) => [e.expressionName, e.weight])),
  };
  const humanoid = {
    reinicios: 0,
    getNormalizedBoneNode: (h) => huesos[h] || null,
    normalizedRestPose: rest,
    resetNormalizedPose() {
      this.reinicios++;
      for (const h in huesos) { huesos[h].position.fromArray(rest[h].position); huesos[h].quaternion.identity(); }
    },
  };
  return {
    scene, huesos, humanoid, expressionManager,
    lookAt: { target: null, yaw: 0, pitch: 0, autoUpdate: true, reset() { this.yaw = 0; this.pitch = 0; } },
    springBoneManager: { joints: [], reinicios: 0, reset() { this.reinicios++; } },
    meta: { metaVersion: String(version), name: 'Prueba', authors: ['Test'] },
    actualizaciones: 0,
    update() { this.actualizaciones++; },
  };
}

/** Posición de un hueso en el mundo (m). */
export function mundo(vrm, hueso) {
  vrm.scene.updateMatrixWorld(true);
  return vrm.huesos[hueso].getWorldPosition(new THREE.Vector3());
}
/** Orientación de un hueso en el mundo. */
export function giroMundo(vrm, hueso) {
  vrm.scene.updateMatrixWorld(true);
  return vrm.huesos[hueso].getWorldQuaternion(new THREE.Quaternion());
}

// ── <audio> falso ───────────────────────────────────────────────────────────────

/** <audio> falso: al poner src dispara 'loadedmetadata' (o 'error') en una microtarea. */
export function audioFalso({ duracion = 10, fallar = false, silencioso = false, rechazarPlay = false } = {}) {
  const oyentes = {};
  let src = '';
  const el = {
    currentTime: 0, duration: NaN, paused: true, ended: false, volume: 1, preload: '', error: null,
    reproducciones: 0, pausas: 0, cargas: 0, quitados: [],
    get src() { return src; },
    set src(v) {
      src = String(v);
      if (silencioso || !src) return;
      queueMicrotask(() => {
        if (fallar) { el.error = { code: 4, message: 'formato no soportado' }; el.disparar('error'); }
        else { el.duration = duracion; el.disparar('loadedmetadata'); }
      });
    },
    addEventListener(t, f) { (oyentes[t] || (oyentes[t] = new Set())).add(f); },
    removeEventListener(t, f) { if (oyentes[t]) oyentes[t].delete(f); },
    oyentes: (t) => (oyentes[t] ? oyentes[t].size : 0),
    disparar(t) { for (const f of [...(oyentes[t] || [])]) f({ type: t, target: el }); },
    play() {
      el.reproducciones++;
      if (rechazarPlay) return Promise.reject(new Error('NotAllowedError: sin gesto del usuario'));
      el.paused = false; el.ended = false;
      return Promise.resolve();
    },
    pause() { el.pausas++; el.paused = true; },
    load() { el.cargas++; },
    removeAttribute(k) { el.quitados.push(k); if (k === 'src') src = ''; },
    /** Simula que la canción avanza `s` segundos (y acaba al llegar a la duración). */
    avanzar(s) {
      if (el.paused || el.ended) return;
      el.currentTime = Math.min(el.duration, el.currentTime + s);
      if (el.currentTime >= el.duration) { el.ended = true; el.paused = true; }
    },
  };
  return el;
}
