/*
 * ui_web/vrm/lune_vmd.js — movimientos de MikuMikuDance (.vmd) para la asistente VRM (corte 9).
 *
 * PURO: sin imports de three (THREE llega por parámetro donde hace falta) y sin DOM.
 * Se prueba en Node (tests/js/vmd.test.mjs) y lo usa ui_web/vrm/lune_mmd.js, que hornea
 * el VMD en un VRMAnimation SINTÉTICO de @pixiv/three-vrm-animation y lo reproduce por
 * el mismo camino que un .vrma (createVRMAnimationClip).
 *
 *   parsearVMD(buf, limites)  lee el archivo del usuario con topes: tamaño, cuentas que
 *                             tienen que caber en lo que queda, frames ≤ 36 000 (20 min),
 *                             IK ≤ 64 por frame. Error('…') en español, nunca un string.
 *                             v2 («Vocaloid Motion Data 0002», modelo de 20 B) y v1
 *                             («… file», 10 B). Nombres en Shift_JIS (TextDecoder) y NFKC.
 *   hornear(THREE, vmds, o)   junta cuerpo + labios, pasa a mano derecha, retarget a los
 *                             huesos NORMALIZADOS del VRM (convención VRM 1.0: el modelo
 *                             mira a +Z y su izquierda es +X) y muestrea a 30 fps en trozos
 *                             de 1500 frames con await entre ellos.
 *   aVRMAnimation(...)        el horneado → VRMAnimation (pistas por hueso y preset).
 *
 * Los VRM 0.x (rig girado 180°) NO se tratan aquí: createVRMAnimationClip niega x/z de
 * cuaterniones y posiciones con metaVersion '0'. lune_mmd.js le pasa la versión que
 * corresponde al signo sXZ que mide el motor (lune_vrm.js), igual que los demás módulos.
 *
 * Retarget (crítica c.3 del plan):
 *   hips   = 全ての親·センター·グルーブ·腰·下半身; posición = raíz·(reposo + s·(centro + surco))
 *   spine  = inv(下半身)·上半身  (en MMD son HERMANOS: meter 下半身 en hips sin contrarrotar
 *            la columna duplicaría el giro del torso)
 *   chest  = 上半身2, upperChest = 上半身3, neck = 首, head = 頭, ojos = 両目·左目/右目
 *   brazos: MMD nace en A-pose y el VRM en T-pose. A = Rz(−θ) (izq.) / Rz(+θ) (der.)
 *            upperArm = (腕·腕捩)·A, lowerArm = A⁻¹·(ひじ·手捩)·A, mano y dedos = A⁻¹·q·A
 *   piernas: IK analítica de dos huesos si hay claves de 足IK y la propiedad IK está
 *            encendida en ese frame (rodilla hacia delante de la cadera); si no, FK.
 *   Si el modelo no trae un hueso opcional (upperChest, chest, neck, hombros) su giro se
 *   pliega en el vecino para no perderlo.
 *   Huesos desconocidos, 肩P, los D, つま先IK y la cámara: se ignoran.
 */

export const LIMITES = Object.freeze({ bytes: 32 << 20, huesos: 2e6, morfos: 1e6, frames: 36000, ik: 1e5, ikPorFrame: 64 });
export const FPS = 30;
export const TROZO = 1500;                       // frames por trozo del horneado (await entre trozos)

const CABECERA_V2 = 'Vocaloid Motion Data 0002';
const CABECERA_V1 = 'Vocaloid Motion Data file';
export const TAM = Object.freeze({ hueso: 111, morfo: 23, camara: 61, luz: 28, sombra: 9, ik: 21 });

const G2R = Math.PI / 180;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ── Nombres ─────────────────────────────────────────────────────────────────────

/** NFKC + sin anchos cero ni controles + trim (ＩＫ→IK, ｳｨﾝｸ２右→ウィンク2右, 上半身２→上半身2). */
export function normalizarNombre(s) {
  let t = String(s ?? '');
  try { t = t.normalize('NFKC'); } catch (e) { /* sin ICU: tal cual */ }
  return t.replace(/[​-‍﻿]/g, '').replace(/[\u0000-\u001F\u007F]/g, '').trim();
}

let decodificador = null;
function decodificar(bytes) {
  if (decodificador === null) {
    try { decodificador = new TextDecoder('shift_jis'); } catch (e) { decodificador = false; }
  }
  if (decodificador) return decodificador.decode(bytes);
  // Sin Shift_JIS (no pasa en Chromium ni en Node con ICU completo): solo ASCII.
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += bytes[i] < 0x80 ? String.fromCharCode(bytes[i]) : '�';
  return s;
}

/** Texto de un campo fijo: hasta el primer NUL (lo de después es basura de MMD). */
function leerNombre(bytes, p, largo, cache) {
  let fin = p;
  const lim = p + largo;
  while (fin < lim && bytes[fin] !== 0) fin++;
  const crudo = bytes.subarray(p, fin);
  if (!cache) return normalizarNombre(decodificar(crudo));
  const clave = String.fromCharCode.apply(null, crudo);
  let s = cache.get(clave);
  if (s === undefined) { s = normalizarNombre(decodificar(crudo)); cache.set(clave, s); }
  return s;
}

// ── Parser ──────────────────────────────────────────────────────────────────────

function aBytes(buf) {
  if (buf instanceof Uint8Array) return buf;
  if (buf instanceof ArrayBuffer) return new Uint8Array(buf);
  if (ArrayBuffer.isView(buf)) return new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
  throw new Error('El VMD no es un archivo binario');
}

function unitario(x, y, z, w) {
  x = num(x); y = num(y); z = num(z); w = num(w, 1);
  const l = Math.hypot(x, y, z, w);
  if (!(l > 1e-8) || !finito(l)) return [0, 0, 0, 1];
  return [x / l, y / l, z / l, w / l];
}

/**
 * Lee un VMD. → {version: 1|2, modelo, huesos: [{nombre, frame, pos: [3], rot: [4], ip: Uint8Array(64)}],
 *   morfos: [{nombre, frame, peso}], camara: n, luces: n, sombras: n, ik: [{frame, visible, ik: {nombre: bool}}],
 *   frames (máximo), duracion (s), soloCamara, soloMorfos}
 * Valores en la convención de MMD (mano izquierda): hornear() los pasa a mano derecha.
 * Las secciones después de los huesos pueden faltar (archivos viejos): cuentan 0.
 */
export function parsearVMD(buf, limites = LIMITES) {
  const L = { ...LIMITES, ...(limites && typeof limites === 'object' ? limites : {}) };
  const bytes = aBytes(buf);
  const total = bytes.byteLength;
  if (total > L.bytes) throw new Error(`El VMD pasa del tope de ${(L.bytes / 1048576).toFixed(0)} MiB`);
  const dv = new DataView(bytes.buffer, bytes.byteOffset, total);
  let p = 0;
  const quedan = () => total - p;
  const exigir = (n, que) => { if (n > quedan()) throw new Error(`El VMD está cortado (${que})`); };

  exigir(30, 'cabecera');
  let cab = '';
  for (let i = 0; i < 30 && bytes[i] !== 0; i++) cab += String.fromCharCode(bytes[i]);
  let version, largoModelo;
  if (cab.startsWith(CABECERA_V2)) { version = 2; largoModelo = 20; }
  else if (cab.startsWith(CABECERA_V1)) { version = 1; largoModelo = 10; }
  else throw new Error('No es un archivo VMD (cabecera desconocida)');
  p = 30;
  exigir(largoModelo, 'nombre del modelo');
  const modelo = leerNombre(bytes, p, largoModelo, null);
  p += largoModelo;

  const cuenta = (tam, max, que) => {
    exigir(4, que);
    const n = dv.getUint32(p, true);
    p += 4;
    if (n > max) throw new Error(`El VMD tiene demasiadas claves de ${que} (${n} > ${max})`);
    if (n * tam > quedan()) throw new Error(`El VMD está cortado (${n} claves de ${que} no caben)`);
    return n;
  };
  const frameValido = (f, que) => {
    if (f > L.frames) throw new Error(`El VMD es demasiado largo (${que} en el frame ${f}; tope ${L.frames})`);
    return f;
  };
  let maxFrame = 0;
  const cache = new Map();

  // Huesos (111 B): nombre 15, frame u32, pos f32×3, rot f32×4 (x, y, z, w), interpolación 64
  const nh = cuenta(TAM.hueso, L.huesos, 'hueso');
  const huesos = new Array(nh);
  for (let i = 0; i < nh; i++) {
    const nombre = leerNombre(bytes, p, 15, cache);
    const frame = frameValido(dv.getUint32(p + 15, true), 'un hueso');
    const pos = [num(dv.getFloat32(p + 19, true)), num(dv.getFloat32(p + 23, true)), num(dv.getFloat32(p + 27, true))];
    const rot = unitario(dv.getFloat32(p + 31, true), dv.getFloat32(p + 35, true), dv.getFloat32(p + 39, true), dv.getFloat32(p + 43, true));
    huesos[i] = { nombre, frame, pos, rot, ip: bytes.subarray(p + 47, p + 111) };
    if (frame > maxFrame) maxFrame = frame;
    p += TAM.hueso;
  }

  // Morfos (23 B): nombre 15, frame u32, peso f32
  let nm = 0;
  let morfos = [];
  if (quedan() >= 4) {
    nm = cuenta(TAM.morfo, L.morfos, 'morfo');
    morfos = new Array(nm);
    for (let i = 0; i < nm; i++) {
      const nombre = leerNombre(bytes, p, 15, cache);
      const frame = frameValido(dv.getUint32(p + 15, true), 'un morfo');
      morfos[i] = { nombre, frame, peso: num(dv.getFloat32(p + 19, true)) };
      if (frame > maxFrame) maxFrame = frame;
      p += TAM.morfo;
    }
  }

  // Cámara, luz y sombra: solo se cuentan (la cámara no se usa)
  const saltar = (tam, que) => {
    if (quedan() < 4) return 0;
    const n = cuenta(tam, Infinity, que);
    p += n * tam;
    return n;
  };
  const camara = saltar(TAM.camara, 'cámara');
  const luces = saltar(TAM.luz, 'luz');
  const sombras = saltar(TAM.sombra, 'sombra');

  // Propiedad (visible + IK on/off): frame u32, visible u8, nIK u32, nIK × (nombre 20, on u8)
  const ik = [];
  if (quedan() >= 4) {
    exigir(4, 'IK');
    const n = dv.getUint32(p, true);
    p += 4;
    if (n > L.ik) throw new Error(`El VMD tiene demasiados frames de IK (${n} > ${L.ik})`);
    for (let i = 0; i < n; i++) {
      exigir(9, 'IK');
      const frame = frameValido(dv.getUint32(p, true), 'un frame de IK');
      const visible = bytes[p + 4] !== 0;
      const k = dv.getUint32(p + 5, true);
      p += 9;
      if (k > L.ikPorFrame) throw new Error(`El VMD tiene demasiados IK en un frame (${k} > ${L.ikPorFrame})`);
      exigir(k * TAM.ik, 'IK');
      const mapa = {};
      for (let j = 0; j < k; j++) {
        const nombre = leerNombre(bytes, p, 20, cache);
        if (nombre && nombre !== '__proto__' && nombre !== 'constructor') mapa[nombre] = bytes[p + 20] !== 0;
        p += TAM.ik;
      }
      ik.push({ frame, visible, ik: mapa });
    }
  }

  return {
    version, modelo, huesos, morfos, camara, luces, sombras, ik,
    frames: maxFrame, duracion: maxFrame / FPS,
    soloCamara: nh === 0 && nm === 0 && camara > 0,
    soloMorfos: nh === 0 && nm > 0,
  };
}

// ── Mapas ───────────────────────────────────────────────────────────────────────

const DEDOS = [
  ['親指', 'Thumb', ['0', '1', '2'], ['Metacarpal', 'Proximal', 'Distal']],
  ['人指', 'Index', ['1', '2', '3'], ['Proximal', 'Intermediate', 'Distal']],
  ['中指', 'Middle', ['1', '2', '3'], ['Proximal', 'Intermediate', 'Distal']],
  ['薬指', 'Ring', ['1', '2', '3'], ['Proximal', 'Intermediate', 'Distal']],
  ['小指', 'Little', ['1', '2', '3'], ['Proximal', 'Intermediate', 'Distal']],
];
const LADOS = [['左', 'left'], ['右', 'right']];

/** Hueso MMD (tras NFKC) → huesos VRM a los que contribuye (la composición está en hornear). */
export const MAPA_HUESOS = Object.freeze((() => {
  const m = {
    '全ての親': ['hips'], 'センター': ['hips'], 'グルーブ': ['hips'], '腰': ['hips'], '下半身': ['hips', 'spine'],
    '上半身': ['spine'], '上半身2': ['chest'], '上半身3': ['upperChest'], '首': ['neck'], '頭': ['head'],
    '両目': ['leftEye', 'rightEye'],
  };
  for (const [j, v] of LADOS) {
    m[j + '目'] = [v + 'Eye'];
    m[j + '肩'] = [v + 'Shoulder'];
    m[j + '腕'] = [v + 'UpperArm']; m[j + '腕捩'] = [v + 'UpperArm'];
    m[j + 'ひじ'] = [v + 'LowerArm']; m[j + '手捩'] = [v + 'LowerArm'];
    m[j + '手首'] = [v + 'Hand'];
    for (const [dj, dv, sj, sv] of DEDOS) for (let i = 0; i < 3; i++) m[j + dj + sj[i]] = [v + dv + sv[i]];
    m[j + '足'] = [v + 'UpperLeg']; m[j + 'ひざ'] = [v + 'LowerLeg']; m[j + '足首'] = [v + 'Foot'];
    m[j + '足先EX'] = [v + 'Toes']; m[j + 'つま先'] = [v + 'Toes'];
    m[j + '足IK'] = [v + 'UpperLeg', v + 'LowerLeg', v + 'Foot'];
    m[j + '足IK親'] = [v + 'UpperLeg', v + 'LowerLeg', v + 'Foot'];
  }
  for (const k in m) Object.freeze(m[k]);
  return m;
})());

/** Morfo MMD (tras NFKC) → preset VRM (AvatarDanceShapeConverter.cs de Mate-Engine; exactos). */
export const MAPA_MORFOS = Object.freeze({
  'まばたき': 'blink', 'ウィンク': 'blinkLeft', 'ウィンク2': 'blinkLeft', 'ウィンク右': 'blinkRight', 'ウィンク2右': 'blinkRight',
  'あ': 'aa', 'い': 'ih', 'う': 'ou', 'え': 'ee', 'お': 'oh',
  'にこり': 'happy', '怒り': 'angry', '困る': 'sad', '真面目': 'neutral', '笑い': 'relaxed',
});

/** Huesos VRM que el horneado escribe siempre (los del motor): el baile manda en todo el cuerpo. */
export const HUESOS_BASE = Object.freeze(['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg']);

// Padre de cada hueso VRM (para posiciones de reposo en el mundo)
const PADRES = (() => {
  const p = { hips: null, spine: 'hips', chest: 'spine', upperChest: 'chest', neck: 'upperChest', head: 'neck' };
  for (const [, v] of LADOS) {
    p[v + 'Eye'] = 'head';
    p[v + 'Shoulder'] = 'upperChest'; p[v + 'UpperArm'] = v + 'Shoulder'; p[v + 'LowerArm'] = v + 'UpperArm';
    p[v + 'Hand'] = v + 'LowerArm';
    for (const [, dv, , sv] of DEDOS) { p[v + dv + sv[0]] = v + 'Hand'; p[v + dv + sv[1]] = v + dv + sv[0]; p[v + dv + sv[2]] = v + dv + sv[1]; }
    p[v + 'UpperLeg'] = 'hips'; p[v + 'LowerLeg'] = v + 'UpperLeg'; p[v + 'Foot'] = v + 'LowerLeg'; p[v + 'Toes'] = v + 'Foot';
  }
  return p;
})();

/** Esqueleto normalizado de reposo por defecto (VRM 1.0, m, posiciones locales): ~1.6 m. */
export const REPOSO_DEFECTO = Object.freeze((() => {
  const r = {
    hips: [0, 0.95, 0], spine: [0, 0.08, 0], chest: [0, 0.12, 0], upperChest: [0, 0.10, 0],
    neck: [0, 0.12, 0], head: [0, 0.08, 0],
  };
  for (const [, v] of LADOS) {
    const s = v === 'left' ? 1 : -1;
    r[v + 'Shoulder'] = [0.03 * s, 0.08, -0.01]; r[v + 'UpperArm'] = [0.10 * s, 0, 0];
    r[v + 'LowerArm'] = [0.25 * s, 0, 0]; r[v + 'Hand'] = [0.23 * s, 0, 0];
    r[v + 'UpperLeg'] = [0.09 * s, -0.06, 0]; r[v + 'LowerLeg'] = [0, -0.42, 0];
    r[v + 'Foot'] = [0, -0.40, 0]; r[v + 'Toes'] = [0, -0.05, 0.12];
  }
  return r;
})());

// ── Curvas ──────────────────────────────────────────────────────────────────────

/**
 * Curva bézier de un canal (0 X, 1 Y, 2 Z, 3 R) de la interpolación de 64 bytes de una
 * clave de hueso (la del tramo que ACABA en esa clave; como pushInterpolation de MMDLoader).
 */
export function curva(ip, canal) {
  const c = canal | 0;
  const g = (i) => num(ip && ip[i], 0) / 127;
  const x1 = g(c), y1 = g(c + 4), x2 = g(c + 8), y2 = g(c + 12);
  return { x1, y1, x2, y2, lineal: x1 === y1 && x2 === y2 };
}

/** y de la bézier (0,0)-(x1,y1)-(x2,y2)-(1,1) en x: bisección de 15 iteraciones, eps 1e-5 (MMDLoader). */
export function bezier(c, x) {
  if (!(x > 0)) return 0;
  if (x >= 1) return 1;
  if (!c || c.lineal || (c.x1 === c.y1 && c.x2 === c.y2)) return x;
  const x1 = c.x1, x2 = c.x2, y1 = c.y1, y2 = c.y2;
  let paso = 0.5, t = 0.5, s = 0.5, sst3 = 0, stt3 = 0, ttt = 0;
  for (let i = 0; i < 15; i++) {
    sst3 = 3 * s * s * t; stt3 = 3 * s * t * t; ttt = t * t * t;
    const ft = sst3 * x1 + stt3 * x2 + ttt - x;
    if (Math.abs(ft) < 1e-5) break;
    paso /= 2;
    t += ft < 0 ? paso : -paso;
    s = 1 - t;
  }
  return sst3 * y1 + stt3 * y2 + ttt;
}

/** MMD (mano izquierda) → three.js (mano derecha): pos.z = −z; rot.x = −x; rot.y = −y. Copia. */
export function aManoDerecha(clave) {
  const p = clave.pos || [0, 0, 0], r = clave.rot || [0, 0, 0, 1];
  return { ...clave, pos: [p[0], p[1], -p[2]], rot: [-r[0], -r[1], r[2], r[3]] };
}

// ── Cuaterniones ([x, y, z, w]) y vectores ───────────────────────────────────────

const IDENT = Object.freeze([0, 0, 0, 1]);
const cp4 = (o, q) => { o[0] = q[0]; o[1] = q[1]; o[2] = q[2]; o[3] = q[3]; return o; };
const CERO = Object.freeze([0, 0, 0]);

export function qMul(a, b, o = [0, 0, 0, 1]) {
  const ax = a[0], ay = a[1], az = a[2], aw = a[3], bx = b[0], by = b[1], bz = b[2], bw = b[3];
  o[0] = ax * bw + aw * bx + ay * bz - az * by;
  o[1] = ay * bw + aw * by + az * bx - ax * bz;
  o[2] = az * bw + aw * bz + ax * by - ay * bx;
  o[3] = aw * bw - ax * bx - ay * by - az * bz;
  return o;
}
export function qInv(q, o = [0, 0, 0, 1]) { o[0] = -q[0]; o[1] = -q[1]; o[2] = -q[2]; o[3] = q[3]; return o; }
export function qEje(x, y, z, ang) { const s = Math.sin(ang / 2); return [x * s, y * s, z * s, Math.cos(ang / 2)]; }
export function qRot(q, v, o = [0, 0, 0]) {
  const qx = q[0], qy = q[1], qz = q[2], qw = q[3], vx = v[0], vy = v[1], vz = v[2];
  const tx = 2 * (qy * vz - qz * vy), ty = 2 * (qz * vx - qx * vz), tz = 2 * (qx * vy - qy * vx);
  o[0] = vx + qw * tx + qy * tz - qz * ty;
  o[1] = vy + qw * ty + qz * tx - qx * tz;
  o[2] = vz + qw * tz + qx * ty - qy * tx;
  return o;
}
export function qSlerp(a, b, t, o = [0, 0, 0, 1]) {
  let bx = b[0], by = b[1], bz = b[2], bw = b[3];
  let cos = a[0] * bx + a[1] * by + a[2] * bz + a[3] * bw;
  if (cos < 0) { cos = -cos; bx = -bx; by = -by; bz = -bz; bw = -bw; }
  let k0, k1;
  if (cos > 0.9995) { k0 = 1 - t; k1 = t; }
  else {
    const th = Math.acos(Math.min(1, cos)), s = Math.sin(th);
    k0 = Math.sin((1 - t) * th) / s; k1 = Math.sin(t * th) / s;
  }
  o[0] = a[0] * k0 + bx * k1; o[1] = a[1] * k0 + by * k1; o[2] = a[2] * k0 + bz * k1; o[3] = a[3] * k0 + bw * k1;
  const l = Math.hypot(o[0], o[1], o[2], o[3]) || 1;
  o[0] /= l; o[1] /= l; o[2] /= l; o[3] /= l;
  return o;
}
const sumaV = (a, b, o = [0, 0, 0]) => { o[0] = a[0] + b[0]; o[1] = a[1] + b[1]; o[2] = a[2] + b[2]; return o; };
const restaV = (a, b, o = [0, 0, 0]) => { o[0] = a[0] - b[0]; o[1] = a[1] - b[1]; o[2] = a[2] - b[2]; return o; };
const escV = (a, s, o = [0, 0, 0]) => { o[0] = a[0] * s; o[1] = a[1] * s; o[2] = a[2] * s; return o; };
const puntoV = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const largoV = (a) => Math.hypot(a[0], a[1], a[2]);
const cruzV = (a, b, o = [0, 0, 0]) => {
  const x = a[1] * b[2] - a[2] * b[1], y = a[2] * b[0] - a[0] * b[2], z = a[0] * b[1] - a[1] * b[0];
  o[0] = x; o[1] = y; o[2] = z; return o;
};
function normV(a, o = [0, 0, 0]) { const l = largoV(a); if (l > 1e-12) escV(a, 1 / l, o); else { o[0] = 0; o[1] = 0; o[2] = 0; } return o; }
/** a sin su componente sobre d (d unitario), normalizado. */
function ortoV(a, d, o = [0, 0, 0]) { const k = puntoV(a, d); o[0] = a[0] - k * d[0]; o[1] = a[1] - k * d[1]; o[2] = a[2] - k * d[2]; return normV(o, o); }

/** Cuaternión de una matriz de rotación 3×3 por filas (m00 m01 m02 m10 …). */
function qDeMatriz(m, o = [0, 0, 0, 1]) {
  const m11 = m[0], m12 = m[1], m13 = m[2], m21 = m[3], m22 = m[4], m23 = m[5], m31 = m[6], m32 = m[7], m33 = m[8];
  const tr = m11 + m22 + m33;
  if (tr > 0) {
    const s = 0.5 / Math.sqrt(tr + 1);
    o[3] = 0.25 / s; o[0] = (m32 - m23) * s; o[1] = (m13 - m31) * s; o[2] = (m21 - m12) * s;
  } else if (m11 > m22 && m11 > m33) {
    const s = 2 * Math.sqrt(1 + m11 - m22 - m33);
    o[3] = (m32 - m23) / s; o[0] = 0.25 * s; o[1] = (m12 + m21) / s; o[2] = (m13 + m31) / s;
  } else if (m22 > m33) {
    const s = 2 * Math.sqrt(1 + m22 - m11 - m33);
    o[3] = (m13 - m31) / s; o[0] = (m12 + m21) / s; o[1] = 0.25 * s; o[2] = (m23 + m32) / s;
  } else {
    const s = 2 * Math.sqrt(1 + m33 - m11 - m22);
    o[3] = (m21 - m12) / s; o[0] = (m13 + m31) / s; o[1] = (m23 + m32) / s; o[2] = 0.25 * s;
  }
  return o;
}

/** Rotación que lleva la base (a0, b0) a (a1, b1): a = eje del hueso, b = «delante» (se ortogonaliza). */
function qDeBases(a0, b0, a1, b1, o = [0, 0, 0, 1]) {
  const u0 = normV(a0), v0 = ortoV(b0, u0), w0 = cruzV(u0, v0);
  const u1 = normV(a1), v1 = ortoV(b1, u1), w1 = cruzV(u1, v1);
  // M = B1 · B0ᵀ (columnas u, v, w)
  const m = new Array(9);
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) m[i * 3 + j] = u1[i] * u0[j] + v1[i] * v0[j] + w1[i] * w0[j];
  }
  qDeMatriz(m, o);
  const l = Math.hypot(o[0], o[1], o[2], o[3]);
  if (!(l > 1e-8) || !finito(l)) { o[0] = 0; o[1] = 0; o[2] = 0; o[3] = 1; return o; }
  o[0] /= l; o[1] /= l; o[2] /= l; o[3] /= l;
  return o;
}

// ── IK de dos huesos ────────────────────────────────────────────────────────────

/**
 * Pierna analítica (ley de cosenos). H = articulación de la cadera, T = objetivo del tobillo
 * (mundo del rig), polo = «delante» de la cadera (la rodilla se dobla hacia ahí).
 * a0/b0: dirección de reposo del muslo y de la espinilla. Si no llega, la pierna se estira
 * hacia el objetivo. → {q1, q2} rotaciones de MUNDO (respecto al reposo) del muslo y la espinilla.
 */
export function resolverPierna(H, T, L1, L2, polo, a0 = [0, -1, 0], b0 = [0, -1, 0]) {
  const u = restaV(T, H);
  let d = largoV(u);
  if (d > 1e-9) escV(u, 1 / d, u); else { u[0] = 0; u[1] = -1; u[2] = 0; d = 0; }
  const min = Math.abs(L1 - L2) + 1e-6, max = (L1 + L2) * (1 - 1e-6);
  const dc = clamp(d, min, Math.max(min, max));
  const a = (L1 * L1 - L2 * L2 + dc * dc) / (2 * dc);
  const h = Math.sqrt(Math.max(0, L1 * L1 - a * a));
  let n = ortoV(polo, u);
  if (largoV(n) < 1e-6) n = ortoV([0, 0, 1], u);
  if (largoV(n) < 1e-6) n = ortoV([1, 0, 0], u);
  const K = [H[0] + u[0] * a + n[0] * h, H[1] + u[1] * a + n[1] * h, H[2] + u[2] * a + n[2] * h];
  const P = [H[0] + u[0] * dc, H[1] + u[1] * dc, H[2] + u[2] * dc];
  const d1 = normV(restaV(K, H)), d2 = normV(restaV(P, K));
  const adelante = [0, 0, 1];
  const q1 = qDeBases(a0, adelante, d1, polo);
  const q2 = qDeBases(b0, adelante, d2, polo);
  return { q1, q2, rodilla: K, pie: P };
}

// ── Horneado ────────────────────────────────────────────────────────────────────

/** Canal de un hueso MMD con claves ordenadas: muestreo en frames crecientes (puntero). */
function crearCanal(claves) {
  let i = 0;
  const pos = [0, 0, 0], rot = [0, 0, 0, 1];
  return {
    claves, pos, rot,
    en(f) {
      const c = claves, n = c.length;
      while (i + 1 < n && c[i + 1].frame <= f) i++;
      const a = c[i];
      if (f <= a.frame || i + 1 >= n) {
        pos[0] = a.pos[0]; pos[1] = a.pos[1]; pos[2] = a.pos[2];
        rot[0] = a.rot[0]; rot[1] = a.rot[1]; rot[2] = a.rot[2]; rot[3] = a.rot[3];
        return this;
      }
      const b = c[i + 1];
      const r = (f - a.frame) / (b.frame - a.frame);
      for (let k = 0; k < 3; k++) pos[k] = a.pos[k] + (b.pos[k] - a.pos[k]) * bezier(b.curvas[k], r);
      qSlerp(a.rot, b.rot, bezier(b.curvas[3], r), rot);
      return this;
    },
  };
}

function crearCanalMorfo(claves) {
  let i = 0;
  return (f) => {
    const c = claves, n = c.length;
    while (i + 1 < n && c[i + 1].frame <= f) i++;
    const a = c[i];
    if (f <= a.frame || i + 1 >= n) return a.peso;
    const b = c[i + 1];
    return a.peso + (b.peso - a.peso) * ((f - a.frame) / (b.frame - a.frame));
  };
}

/** Ordena por frame (estable) y deja la ÚLTIMA clave de cada frame repetido. */
function ordenarUnicas(lista) {
  const conIndice = lista.map((c, i) => [c, i]);
  conIndice.sort((a, b) => (a[0].frame - b[0].frame) || (a[1] - b[1]));
  const out = [];
  for (const [c] of conIndice) {
    if (out.length && out[out.length - 1].frame === c.frame) out[out.length - 1] = c;
    else out.push(c);
  }
  return out;
}

/** Posiciones locales de reposo (VRM 1.0) desde normalizedRestPose de three-vrm o un mapa simple. */
function reposoDe(restPose) {
  const r = {};
  if (restPose && typeof restPose === 'object') {
    for (const k of Object.keys(PADRES)) {
      const e = restPose[k];
      if (!e) continue;
      const v = Array.isArray(e) ? e : (Array.isArray(e.position) ? e.position : (e.position && finito(e.position.x) ? [e.position.x, e.position.y, e.position.z] : null));
      if (v && v.length >= 3 && v.every((x) => finito(Number(x)))) r[k] = [Number(v[0]), Number(v[1]), Number(v[2])];
    }
  }
  if (!r.hips || !r.leftUpperLeg || !r.leftLowerLeg || !r.leftFoot || !r.rightUpperLeg || !r.rightLowerLeg || !r.rightFoot) {
    for (const k of Object.keys(REPOSO_DEFECTO)) if (!r[k]) r[k] = REPOSO_DEFECTO[k].slice();
  }
  return r;
}

/** Posición de reposo en el mundo del rig (suma de locales: las rotaciones normalizadas son identidad). */
function mundoReposo(r, hueso) {
  const v = [0, 0, 0];
  for (let h = hueso; h; h = PADRES[h]) if (r[h]) sumaV(v, r[h], v);
  return v;
}

const esperaPorDefecto = () => new Promise((res) => setTimeout(res, 0));

/**
 * Hornea uno o varios VMD (cuerpo + labios) a 30 fps en los huesos normalizados del VRM.
 * opciones: {brazoGrados = 35, restPose (normalizedRestPose de three-vrm, ya en convención
 *   VRM 1.0), alturaCaderaMMD = 11.0, escala (por defecto caderaVRM.y / alturaCaderaMMD),
 *   piesReposo {left, right} (mundo, m), largos {muslo, espinilla} (m), huesosModelo
 *   (Set|Array|fn: huesos que trae el modelo; sin él, todos), soloCara (solo expresiones),
 *   ceder () → Promise (entre trozos), cancelado () → bool}
 * → {fps: 30, frames, duracion, tiempos: Float32Array(n), rot: Map<hueso VRM, Float32Array(n·4)>,
 *    cadera: Float32Array(n·3) | null, expr: Map<preset, Float32Array(n)>, conIK, escala}
 */
export async function hornear(THREE, vmds, opciones = {}) {
  const o = opciones && typeof opciones === 'object' ? opciones : {};
  const lista = (Array.isArray(vmds) ? vmds : [vmds]).filter((v) => v && typeof v === 'object');
  const soloCara = !!o.soloCara;
  const theta = clamp(num(Number(o.brazoGrados), 35), 0, 90) * G2R;
  const ceder = typeof o.ceder === 'function' ? o.ceder : esperaPorDefecto;
  const cancelado = typeof o.cancelado === 'function' ? o.cancelado : () => false;
  const hm = o.huesosModelo;
  const tiene = typeof hm === 'function' ? (h) => !!hm(h)
    : hm instanceof Set ? (h) => hm.has(h)
      : Array.isArray(hm) ? ((s) => (h) => s.has(h))(new Set(hm)) : () => true;

  // Agrupar por nombre (ya en NFKC), en mano derecha
  const porHueso = new Map(), porMorfo = new Map(), porIK = new Map();
  let maxFrame = 0;
  for (const v of lista) {
    if (!soloCara) {
      for (const k of v.huesos || []) {
        if (!k || !MAPA_HUESOS[k.nombre]) continue;           // desconocidos, 肩P, D, つま先IK: fuera
        const c = aManoDerecha(k);
        c.curvas = [curva(k.ip, 0), curva(k.ip, 1), curva(k.ip, 2), curva(k.ip, 3)];
        let l = porHueso.get(k.nombre);
        if (!l) porHueso.set(k.nombre, (l = []));
        l.push(c);
        if (k.frame > maxFrame) maxFrame = k.frame;
      }
      for (const f of v.ik || []) {
        for (const nombre in (f && f.ik) || {}) {
          let l = porIK.get(nombre);
          if (!l) porIK.set(nombre, (l = []));
          l.push({ frame: f.frame, on: !!f.ik[nombre] });
        }
      }
    }
    for (const k of v.morfos || []) {
      if (!k || !MAPA_MORFOS[k.nombre]) continue;
      let l = porMorfo.get(k.nombre);
      if (!l) porMorfo.set(k.nombre, (l = []));
      l.push({ frame: k.frame, peso: clamp(num(k.peso), 0, 1) });
      if (k.frame > maxFrame) maxFrame = k.frame;
    }
  }
  if (!porHueso.size && !porMorfo.size) {
    // Solo cámara, o huesos/morfos de un esqueleto que no es el estándar de MMD
    throw new Error('El VMD no tiene movimiento ni cara que Lune entienda');
  }

  const canales = new Map();
  for (const [n, l] of porHueso) canales.set(n, crearCanal(ordenarUnicas(l)));
  const morfos = new Map();
  for (const [n, l] of porMorfo) morfos.set(n, crearCanalMorfo(ordenarUnicas(l)));
  const ikListas = new Map();
  for (const [n, l] of porIK) ikListas.set(n, { claves: ordenarUnicas(l), i: 0 });

  const n = maxFrame + 1;
  const tiempos = new Float32Array(n);
  for (let f = 0; f < n; f++) tiempos[f] = f / FPS;

  // Reposo del modelo y escala
  const rest = reposoDe(o.restPose);
  const cadera0 = rest.hips.slice();
  const alturaMMD = num(Number(o.alturaCaderaMMD), 11.0) > 0 ? num(Number(o.alturaCaderaMMD), 11.0) : 11.0;
  const escala = num(Number(o.escala), 0) > 0 ? Number(o.escala) : Math.max(1e-4, cadera0[1]) / alturaMMD;

  // Salida
  const rot = new Map();
  const expr = new Map();
  const cadera = soloCara ? null : new Float32Array(n * 3);
  const querer = (h) => { if (tiene(h) && !rot.has(h)) rot.set(h, new Float32Array(n * 4)); };
  const hayCanal = (nombre) => canales.has(nombre);
  if (!soloCara) {
    for (const h of HUESOS_BASE) querer(h);
    for (const [mmd, vrms] of Object.entries(MAPA_HUESOS)) {
      if (!hayCanal(mmd)) continue;
      if (mmd.endsWith('IK') || mmd.endsWith('IK親')) continue;          // la IK se decide abajo
      for (const h of vrms) querer(h);
    }
  }
  const presets = new Map();          // preset → [canales de morfo]
  for (const [mmd, fn] of morfos) {
    const p = MAPA_MORFOS[mmd];
    let l = presets.get(p);
    if (!l) { presets.set(p, (l = [])); expr.set(p, new Float32Array(n)); }
    l.push(fn);
  }

  // IK por lado: hay claves de 足IK → se usa en los frames con la propiedad encendida
  const lados = LADOS.map(([j, v]) => {
    const nIK = j + '足IK';
    const L1 = largoV(rest[v + 'LowerLeg']), L2 = largoV(rest[v + 'Foot']);
    const piesO = o.piesReposo && o.piesReposo[v];
    const larg = o.largos && typeof o.largos === 'object' ? o.largos : null;
    return {
      j, v, nIK, conIK: !soloCara && hayCanal(nIK),
      L1: larg && num(Number(larg.muslo), 0) > 0 ? Number(larg.muslo) : L1,
      L2: larg && num(Number(larg.espinilla), 0) > 0 ? Number(larg.espinilla) : L2,
      a0: normV(rest[v + 'LowerLeg']), b0: normV(rest[v + 'Foot']),
      pie0: Array.isArray(piesO) && piesO.length >= 3 ? piesO.map(Number) : mundoReposo(rest, v + 'Foot'),
      muslo0: rest[v + 'UpperLeg'].slice(),
      A: qEje(0, 0, 1, v === 'left' ? -theta : theta),
      Ai: qEje(0, 0, 1, v === 'left' ? theta : -theta),
    };
  });
  for (const l of lados) if (l.conIK) { querer(l.v + 'UpperLeg'); querer(l.v + 'LowerLeg'); querer(l.v + 'Foot'); }
  let conIK = false;

  function ikEncendida(nombre, f) {
    const l = ikListas.get(nombre);
    if (!l) return true;
    const c = l.claves;
    while (l.i + 1 < c.length && c[l.i + 1].frame <= f) l.i++;
    if (f < c[0].frame) return true;
    return c[l.i].on;
  }

  // Temporales
  const R = (nombre) => { const c = canales.get(nombre); return c ? c.rot : IDENT; };
  const Pz = (nombre) => { const c = canales.get(nombre); return c ? c.pos : CERO; };
  const t1 = [0, 0, 0, 1], t2 = [0, 0, 0, 1], t3 = [0, 0, 0, 1];
  const qHips = [0, 0, 0, 1], qSpine = [0, 0, 0, 1], qChest = [0, 0, 0, 1], qUC = [0, 0, 0, 1];
  const qNeck = [0, 0, 0, 1], qHead = [0, 0, 0, 1], qOjos = [0, 0, 0, 1];
  const v1 = [0, 0, 0], v2 = [0, 0, 0], v3 = [0, 0, 0], H = [0, 0, 0], T = [0, 0, 0], polo = [0, 0, 0];
  const escribir = (h, f, q) => {
    const a = rot.get(h);
    if (!a) return;
    let x = q[0], y = q[1], z = q[2], w = q[3];
    const l = Math.hypot(x, y, z, w);
    if (!(l > 1e-8) || !finito(l)) { x = 0; y = 0; z = 0; w = 1; } else { x /= l; y /= l; z /= l; w /= l; }
    const i = f * 4;
    a[i] = x; a[i + 1] = y; a[i + 2] = z; a[i + 3] = w;
  };
  const conA = (Ai, q, A, o2) => qMul(qMul(Ai, q, t3), A, o2);

  for (let f = 0; f < n; f++) {
    if (f > 0 && f % TROZO === 0) {
      await ceder();
      if (cancelado()) throw new Error('cancelado');
    }
    for (const c of canales.values()) c.en(f);

    // Morfos: máximo de los que van al mismo preset, 0..1
    for (const [p, fns] of presets) {
      let m = 0;
      for (const fn of fns) { const v = fn(f); if (v > m) m = v; }
      expr.get(p)[f] = clamp(m, 0, 1);
    }
    if (soloCara) continue;

    // Tronco
    const qRoot = R('全ての親'), qC = R('センター'), qG = R('グルーブ'), qW = R('腰'), qLB = R('下半身');
    qMul(qRoot, qC, t1); qMul(t1, qG, t2); qMul(t2, qW, t1); qMul(t1, qLB, qHips);
    qMul(qInv(qLB, t1), R('上半身'), qSpine);
    const c2 = R('上半身2'), c3 = R('上半身3');
    cp4(qChest, c2);
    cp4(qUC, c3);
    const nk = R('首'), hd = R('頭');
    cp4(qNeck, nk);
    cp4(qHead, hd);
    // Huesos opcionales que el modelo no trae: su giro se pliega en el vecino
    if (!tiene('upperChest')) { qMul(qChest, qUC, t1); cp4(qChest, t1); }
    if (!tiene('chest')) { qMul(qSpine, qChest, t1); cp4(qSpine, t1); }
    if (!tiene('neck')) { qMul(qNeck, qHead, t1); cp4(qHead, t1); }
    escribir('hips', f, qHips); escribir('spine', f, qSpine); escribir('chest', f, qChest);
    escribir('upperChest', f, qUC); escribir('neck', f, qNeck); escribir('head', f, qHead);
    const oj = R('両目');
    cp4(qOjos, oj);
    escribir('leftEye', f, qMul(qOjos, R('左目'), t1));
    escribir('rightEye', f, qMul(qOjos, R('右目'), t1));

    // Cadera: reposo + s·(centro + surco + cintura), por la raíz
    const pC = Pz('センター'), pG = Pz('グルーブ'), pW = Pz('腰'), pR = Pz('全ての親');
    sumaV(qRot(qG, pW, v1), pG, v1);
    sumaV(qRot(qC, v1, v2), pC, v2);
    sumaV(cadera0, escV(v2, escala, v2), v2);
    qRot(qRoot, v2, v3);
    const pos = sumaV(v3, escV(pR, escala, v1), v1);
    cadera[f * 3] = num(pos[0]); cadera[f * 3 + 1] = num(pos[1], cadera0[1]); cadera[f * 3 + 2] = num(pos[2]);
    const hipsPos = [cadera[f * 3], cadera[f * 3 + 1], cadera[f * 3 + 2]];

    for (const l of lados) {
      const { j, v, A, Ai } = l;
      // Brazos: (腕·腕捩)·A, A⁻¹·(ひじ·手捩)·A, A⁻¹·手首·A, dedos A⁻¹·q·A
      const qHombro = R(j + '肩');
      qMul(qMul(R(j + '腕'), R(j + '腕捩'), t1), A, t2);
      if (!tiene(v + 'Shoulder')) { qMul(qHombro, t2, t1); cp4(t2, t1); }
      else escribir(v + 'Shoulder', f, qHombro);
      escribir(v + 'UpperArm', f, t2);
      escribir(v + 'LowerArm', f, conA(Ai, qMul(R(j + 'ひじ'), R(j + '手捩'), t1), A, t2));
      escribir(v + 'Hand', f, conA(Ai, R(j + '手首'), A, t2));
      for (const [dj, dv, sj, sv] of DEDOS) {
        for (let i = 0; i < 3; i++) {
          const nombre = j + dj + sj[i];
          if (hayCanal(nombre)) escribir(v + dv + sv[i], f, conA(Ai, R(nombre), A, t2));
        }
      }
      // Piernas
      const toes = hayCanal(j + '足先EX') ? R(j + '足先EX') : R(j + 'つま先');
      escribir(v + 'Toes', f, toes);
      if (l.conIK && ikEncendida(l.nIK, f)) {
        conIK = true;
        // Objetivo = raíz·(pie de reposo + s·(IK親 + IK))
        const pIK = Pz(l.nIK), pP = Pz(l.nIK + '親');
        const qP = R(l.nIK + '親');
        sumaV(qRot(qP, pIK, v2), pP, v2);
        sumaV(l.pie0, escV(v2, escala, v2), v2);
        qRot(qRoot, v2, v3);
        sumaV(v3, escV(pR, escala, T), T);
        sumaV(hipsPos, qRot(qHips, l.muslo0, H), H);
        qRot(qHips, [0, 0, 1], polo);
        const { q1, q2 } = resolverPierna(H, T, l.L1, l.L2, polo, l.a0, l.b0);
        escribir(v + 'UpperLeg', f, qMul(qInv(qHips, t1), q1, t2));
        escribir(v + 'LowerLeg', f, qMul(qInv(q1, t1), q2, t2));
        // Pie en el mundo = raíz·IK親·IK → local = inv(mundo de la espinilla)·pie
        qMul(qMul(qRoot, qP, t1), R(l.nIK), t2);
        escribir(v + 'Foot', f, qMul(qInv(q2, t1), t2, t3));
      } else {
        escribir(v + 'UpperLeg', f, R(j + '足'));
        escribir(v + 'LowerLeg', f, R(j + 'ひざ'));
        escribir(v + 'Foot', f, R(j + '足首'));
      }
    }
  }

  return { fps: FPS, frames: maxFrame, duracion: maxFrame / FPS, tiempos, rot, cadera, expr, conIK, escala };
}

/**
 * Horneado → VRMAnimation de three-vrm-animation: pistas por hueso (nombre VRM; createVRMAnimationClip
 * las pasa a los nodos normalizados), 'hips' en posición y presets de expresión. restCadera =
 * cadera de reposo del VRM (escala 1: la animación ya está a la medida del modelo).
 */
export function aVRMAnimation(VRMAnimation, THREE, horneado, restCadera) {
  const h = horneado;
  const anim = new VRMAnimation();
  anim.duration = num(h.duracion, 0);
  const rc = Array.isArray(restCadera) ? restCadera
    : restCadera && finito(restCadera.x) ? [restCadera.x, restCadera.y, restCadera.z]
      : h.cadera && h.cadera.length >= 3 ? [h.cadera[0], h.cadera[1], h.cadera[2]] : REPOSO_DEFECTO.hips;
  if (anim.restHipsPosition && typeof anim.restHipsPosition.set === 'function') anim.restHipsPosition.set(rc[0], rc[1], rc[2]);
  else anim.restHipsPosition = new THREE.Vector3(rc[0], rc[1], rc[2]);
  const optimizar = (tr) => { try { return typeof tr.optimize === 'function' ? tr.optimize() : tr; } catch (e) { return tr; } };
  for (const [hueso, valores] of h.rot || []) {
    anim.humanoidTracks.rotation.set(hueso, optimizar(new THREE.QuaternionKeyframeTrack(hueso, h.tiempos, valores)));
  }
  if (h.cadera) anim.humanoidTracks.translation.set('hips', optimizar(new THREE.VectorKeyframeTrack('hips', h.tiempos, h.cadera)));
  for (const [preset, valores] of h.expr || []) {
    anim.expressionTracks.preset.set(preset, optimizar(new THREE.NumberKeyframeTrack(preset, h.tiempos, valores)));
  }
  return anim;
}
