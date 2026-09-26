// tests/js/three_falso.mjs — three.js, GLTFLoader y @pixiv/three-vrm FALSOS, con lo justo
// para cargar ui_web/vrm/lune_vrm.js en Node (tests/js/integracion_vrm.test.mjs).
// No es un test (no acaba en .test.mjs): lo importa el test tras reescribir los
// imports del motor ('three', 'three/addons/…', '@pixiv/three-vrm') hacia este archivo.
//
// - El reloj (Clock.getDelta) sigue a `reloj.ms`, que el test avanza a la vez que llama
//   al requestAnimationFrame falso: el tiempo simulado es el de los frames.
// - GLTFLoader.load no carga nada: apunta la petición en `cargas` y el test la completa
//   con un VRM falso (crearVRMFalso).

export const reloj = { ms: 0 };
export const cargas = [];

export const SRGBColorSpace = 'srgb';

export class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  setScalar(s) { this.x = s; this.y = s; this.z = s; return this; }
  copy(v) { this.x = v.x; this.y = v.y; this.z = v.z; return this; }
  clone() { return new Vector3(this.x, this.y, this.z); }
  multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
  addScaledVector(v, s) { this.x += v.x * s; this.y += v.y * s; this.z += v.z * s; return this; }
  length() { return Math.hypot(this.x, this.y, this.z); }
  normalize() { const l = this.length() || 1; return this.multiplyScalar(1 / l); }
  project() { return this; }                                  // proyección ficticia
  setFromMatrixColumn() { return this.set(1, 0, 0); }
}

export class Euler {
  constructor() { this.x = 0; this.y = 0; this.z = 0; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
}

export class Object3D {
  constructor() {
    this.position = new Vector3(); this.rotation = new Euler(); this.scale = new Vector3(1, 1, 1);
    this.children = []; this.parent = null; this.visible = true; this.matrixWorld = {};
  }
  add(o) { this.children.push(o); o.parent = this; return this; }
  remove(o) { this.children = this.children.filter((c) => c !== o); if (o) o.parent = null; return this; }
  traverse(fn) { fn(this); for (const c of this.children) c.traverse(fn); }
  /** Suma de posiciones hasta la raíz (sin rotaciones: basta para el encuadre). */
  getWorldPosition(v) {
    v.set(0, 0, 0);
    for (let o = this; o; o = o.parent) { v.x += o.position.x; v.y += o.position.y; v.z += o.position.z; }
    return v;
  }
  updateMatrixWorld() {}
  lookAt() {}
}

export class Scene extends Object3D {}
export class PerspectiveCamera extends Object3D {
  constructor(fov = 50, aspect = 1) { super(); this.fov = fov; this.aspect = aspect; }
  updateProjectionMatrix() {}
}
export class DirectionalLight extends Object3D {
  constructor(color, intensity = 1) { super(); this.color = color; this.intensity = intensity; }
}
export class HemisphereLight extends Object3D {
  constructor(cielo, suelo, intensity = 1) { super(); this.intensity = intensity; }
}

export class Box3 {
  constructor() { this.min = new Vector3(); this.max = new Vector3(); }
  setFromObject() { this.min.set(-0.3, 0, -0.15); this.max.set(0.3, 1.6, 0.15); return this; }
}

export class Clock {
  constructor() { this.prev = reloj.ms; }
  getDelta() { const d = (reloj.ms - this.prev) / 1000; this.prev = reloj.ms; return Math.max(0, d); }
}

export class WebGLRenderer {
  constructor(opciones = {}) {
    this.domElement = opciones.canvas; this.renders = 0; this.pixelRatio = 1; this.liberado = 0; this.perdido = 0;
  }
  setPixelRatio(r) { this.pixelRatio = r; }
  setClearColor() {}
  setSize() {}
  getContext() { return { RGBA: 1, UNSIGNED_BYTE: 2, readPixels: (x, y, w, h, f, t, px) => { px[3] = 255; } }; }
  render() { this.renders++; }
  dispose() { this.liberado++; }
  forceContextLoss() { this.perdido++; }
}

// ── three/addons/loaders/GLTFLoader.js ─────────────────────────────────────────
export class GLTFLoader {
  register() { return this; }
  load(url, alCargar, alProgreso, alFallar) { cargas.push({ url, alCargar, alFallar }); }
}

// ── @pixiv/three-vrm ────────────────────────────────────────────────────────────
export class VRMLoaderPlugin { constructor(parser) { this.parser = parser; } }
/** deepDispose apunta lo que libera en `liberadas` (las escenas de los modelos soltados). */
export const VRMUtils = { liberadas: [], removeUnnecessaryVertices() {}, rotateVRM0() {}, deepDispose(o) { VRMUtils.liberadas.push(o); } };

// ── VRM falso para completar una carga ─────────────────────────────────────────
export const HUESOS_VRM = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg'];
export const EXPRESIONES_BASE = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral',
  'aa', 'ih', 'ou', 'ee', 'oh', 'blink', 'blinkLeft', 'blinkRight'];

/**
 * VRM falso: humanoide con los huesos normalizados (Object3D con rotation.set), un
 * expressionManager que guarda los valores en `valores`, lookAt y un spring bone.
 * version '0' pone el antebrazo izquierdo en −X (rig girado de los VRM 0.x).
 */
export function crearVRMFalso({ version = '1', expresiones = EXPRESIONES_BASE } = {}) {
  const scene = new Object3D();
  const huesos = {};
  for (const h of HUESOS_VRM) { const n = new Object3D(); huesos[h] = n; scene.add(n); }
  huesos.hips.position.y = 0.9; huesos.head.position.y = 1.4;
  huesos.leftLowerArm.position.x = version === '0' ? -0.25 : 0.25;
  const valores = {};
  const lista = expresiones.map((n) => ({ expressionName: n }));
  const expressionManager = {
    expressions: lista,
    getExpression: (n) => (expresiones.includes(n) ? { expressionName: n } : null),
    setValue: (n, v) => { valores[n] = v; },
    getValue: (n) => valores[n] || 0,
  };
  const junta = { settings: { gravityDir: new Vector3(0, -1, 0), gravityPower: 0.5 } };
  return {
    scene, huesos, valores,
    meta: { metaVersion: version, name: 'Prueba', authors: ['Test'] },
    humanoid: { getNormalizedBoneNode: (h) => huesos[h] || null },
    expressionManager,
    lookAt: { target: null },
    springBoneManager: { joints: [junta] },
    junta,
    actualizaciones: 0,
    update() { this.actualizaciones++; },
  };
}
