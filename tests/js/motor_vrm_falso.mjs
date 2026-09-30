// tests/js/motor_vrm_falso.mjs — arnés para probar módulos del bus con el motor VRM
// DE VERDAD (ui_web/vrm/lune_vrm.js) en Node, como tests/js/integracion_vrm.test.mjs:
// three.js, GLTFLoader y three-vrm falsos (three_falso.mjs), imports reescritos y un
// requestAnimationFrame falso. Lo usan baile_proc.test.mjs y grande.test.mjs (cortes 5 y 6).
// No es un test (no acaba en .test.mjs).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { reloj, cargas, crearVRMFalso, EXPRESIONES_BASE } from './three_falso.mjs';
import { crearAleatorio } from '../../ui_web/vrm/lune_modulos.js';

export const UI = new URL('../../ui_web/', import.meta.url);
const URL_MOTOR = new URL('vrm/lune_vrm.js', UI);
const URL_FALSO = new URL('./three_falso.mjs', import.meta.url).href;

globalThis.window = globalThis;
globalThis.devicePixelRatio = 1;
if (typeof globalThis.addEventListener !== 'function') globalThis.addEventListener = () => {};
if (typeof globalThis.luneEventos !== 'function') {
  vm.runInThisContext(readFileSync(new URL('lune_eventos.js', UI), 'utf8'), { filename: 'lune_eventos.js' });
}
export const frames = [];
globalThis.requestAnimationFrame = (f) => { frames.push(f); return frames.length; };
Math.random = crearAleatorio(20260926);

/** Carga un script clásico de ui_web/ en el global (lune_ritmo.js, lune_alarma.js…). */
export function cargarClasico(nombre) {
  vm.runInThisContext(readFileSync(new URL(nombre, UI), 'utf8'), { filename: nombre });
}

export function reescribirImports(src, base, extra = {}) {
  const destino = (esp) => {
    if (esp in extra) return extra[esp];
    if (esp === 'three' || esp.startsWith('three/addons/') || esp === '@pixiv/three-vrm') return URL_FALSO;
    if (esp.startsWith('./') || esp.startsWith('../')) return new URL(esp, base).href;
    return null;
  };
  return src
    .replace(/from\s+'([^']+)'/g, (m, esp) => { const d = destino(esp); return d ? `from '${d}'` : m; })
    .replace(/import\(\s*'([^']+)'\s*\)/g, (m, esp) => { const d = destino(esp); return d ? `import('${d}')` : m; });
}
export const aDataURL = (src) => 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
export const DATA_MOTOR = aDataURL(reescribirImports(readFileSync(URL_MOTOR, 'utf8'), URL_MOTOR));
export const motor = await import(DATA_MOTOR);

export function lienzoFalso(extra = {}) {
  return Object.assign({
    clientWidth: 240, clientHeight: 320, width: 240, height: 320,
    getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; },
  }, extra);
}

/** Avanza `seg` s de frames a 60 Hz: antes(i) antes de cada frame y despues(i) tras él. */
export function correr(seg, antes = null, despues = null) {
  const n = Math.round(seg * 60);
  for (let i = 0; i < n; i++) {
    reloj.ms += 1000 / 60;
    if (antes) antes(i);
    const f = frames.shift();
    assert.equal(typeof f, 'function', 'el bucle pidió su siguiente frame');
    f(reloj.ms);
    if (despues) despues(i);
  }
}

/** Asistente con un VRM falso ya cargado. */
export function montar({ version = '1', expresiones = EXPRESIONES_BASE, canvas = null } = {}) {
  frames.length = 0;
  const m = motor.crearAsistente({ canvas: canvas || lienzoFalso(), src: '/vrm/actual.vrm' });
  const carga = cargas.pop();
  const vrm = crearVRMFalso({ version, expresiones });
  carga.alCargar({ scene: vrm.scene, userData: { vrm } });
  return { m, vrm, est: m.ctx.estado() };
}

/** Deja la asistente quieta en 'normal' y sin variantes de idle. */
export function quietaSinIdles(m) {
  correr(3);
  m.mod('idles', 'set', { activo: false });
  correr(1.5);
}

/** Vacía window.luneEventos() → [{t, d, ts}]. */
export function vaciarCola() {
  const todos = [];
  for (;;) { const lote = JSON.parse(globalThis.luneEventos()); if (!lote.length) return todos; todos.push(...lote); }
}

// ── Brazos con matrices (Euler 'XYZ' de three.js: R = Rx·Ry·Rz) ────────────────
export function matEuler({ x, y, z }) {
  const [cx, sx, cy, sy, cz, sz] = [Math.cos(x), Math.sin(x), Math.cos(y), Math.sin(y), Math.cos(z), Math.sin(z)];
  const Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]];
  const Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]];
  const Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]];
  return mul(Rx, mul(Ry, Rz));
}
function mul(A, B) { return A.map((f) => [0, 1, 2].map((j) => f[0] * B[0][j] + f[1] * B[1][j] + f[2] * B[2][j])); }
const aplicar = (A, v) => A.map((f) => f[0] * v[0] + f[1] * v[1] + f[2] * v[2]);

/**
 * Codo y mano respecto al hombro en coordenadas del MUNDO (el modelo mira a +Z;
 * brazo y antebrazo de 1 m), en VRM 1.0 y 0.x: en los 0.x el rig nace girado 180°
 * (brazo izquierdo a −X en T-pose y X/Z con el signo cambiado por sXZ) y rotateVRM0
 * gira la escena 180°. Mismo cálculo que integracion_vrm.test.mjs.
 */
export function brazoMundo(vrm, lado, version = '1') {
  const v0 = version === '0';
  const eje = (lado === 'left') !== v0 ? [1, 0, 0] : [-1, 0, 0];
  const Ru = matEuler(vrm.huesos[lado + 'UpperArm'].rotation);
  const Rl = matEuler(vrm.huesos[lado + 'LowerArm'].rotation);
  const codo = aplicar(Ru, eje), ante = aplicar(mul(Ru, Rl), eje);
  const manoP = codo.map((c, i) => c + ante[i]);
  const giro = (p) => (v0 ? [-p[0], p[1], -p[2]] : p);
  return { codo: giro(codo), mano: giro(manoP) };
}

// ── Páginas ─────────────────────────────────────────────────────────────────────
/** <script> en línea de una página (sin src ni importmap): [{modulo, codigo}]. */
export function scriptsEnLinea(pagina) {
  const html = readFileSync(new URL(pagina, UI), 'utf8');
  const res = [];
  for (const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
    const attrs = m[1];
    if (/\bsrc=/.test(attrs) || /importmap/.test(attrs) || !m[2].trim()) continue;
    res.push({ modulo: /type="module"/.test(attrs), codigo: m[2] });
  }
  return { html, scripts: res };
}

/** Ejecuta los scripts en línea de la página (el módulo con los imports reescritos). */
export async function ejecutarPagina(pagina, documento, extraImports = {}, sufijo = '') {
  const { scripts } = scriptsEnLinea(pagina);
  globalThis.document = documento;
  const base = new URL(pagina, UI);
  for (const s of scripts) {
    if (!s.modulo) vm.runInThisContext(s.codigo, { filename: pagina });
    else await import(aDataURL(reescribirImports(s.codigo, base, extraImports) + sufijo));
  }
}

export { reloj, cargas, crearVRMFalso };
