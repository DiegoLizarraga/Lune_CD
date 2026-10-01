// tests/js/integracion_vrm.test.mjs — integración del corte 3 en la asistente:
//   · ui_web/vrm/lune_vrm.js DE VERDAD (no una copia), cargado en Node con three.js,
//     GLTFLoader y three-vrm falsos (three_falso.mjs): los imports del motor se
//     reescriben hacia el falso y hacia las rutas absolutas de sus módulos, y se importa
//     como data: URL. Se simulan frames con un requestAnimationFrame falso.
//   · las dos páginas (companion_vrm.html y companion.html) ejecutando sus <script>
//     en línea con un DOM falso (dom_falso.mjs): lo que Python llama existe tras cargar.
// Eventos: se carga ui_web/lune_eventos.js en el global (window = globalThis, como en
// la página) y se leen con window.luneEventos(), igual que companion.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { reloj, cargas, crearVRMFalso, EXPRESIONES_BASE, DirectionalLight, HemisphereLight, VRMUtils } from './three_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import { crearAleatorio } from '../../ui_web/vrm/lune_modulos.js';
import { RANGOS } from '../../ui_web/vrm/lune_params.js';
import { PARAMS_SWAY } from '../../ui_web/vrm/lune_movimiento.js';
import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { instalar as instalarFisica, publicar as publicarFisica } from '../../ui_web/anim/lune_anim_fisica.js';

const G2R = Math.PI / 180;
const UI = new URL('../../ui_web/', import.meta.url);
const URL_MOTOR = new URL('vrm/lune_vrm.js', UI);
const URL_FALSO = new URL('./three_falso.mjs', import.meta.url).href;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

// ── Página falsa ────────────────────────────────────────────────────────────────
globalThis.window = globalThis;
globalThis.devicePixelRatio = 1;
if (typeof globalThis.addEventListener !== 'function') globalThis.addEventListener = () => {};
vm.runInThisContext(readFileSync(new URL('lune_eventos.js', UI), 'utf8'), { filename: 'lune_eventos.js' });
let frames = [];
globalThis.requestAnimationFrame = (f) => { frames.push(f); return frames.length; };
Math.random = crearAleatorio(20260925);         // idles, parpadeo y lado de la rodilla deterministas

/** Vacía window.luneEventos() (como mucho 50 por llamada) → [{t, d, ts}]. */
function vaciarCola() {
  const todos = [];
  for (;;) { const lote = JSON.parse(globalThis.luneEventos()); if (!lote.length) return todos; todos.push(...lote); }
}

// ── El motor con los imports reescritos ────────────────────────────────────────
// Estáticos (from '…') y dinámicos (import('…'), los módulos opcionales del motor).
// `extra` sustituye un especificador por otra URL (p. ej. un módulo roto).
function reescribirImports(src, base, extra = {}) {
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
const aDataURL = (src) => 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
const SRC_MOTOR = reescribirImports(readFileSync(URL_MOTOR, 'utf8'), URL_MOTOR);
const DATA_MOTOR = aDataURL(SRC_MOTOR);
const motor = await import(DATA_MOTOR);
// Aquí los frames los simula el test a 60 Hz: en reposo, rAF y no el temporizador de la espera
// (11.2; ese camino lo prueba tests/js/vrm_fps.test.mjs con un temporizador falso).
motor.PARAMS.esperaTemporizador = false;
const DEFECTOS = Object.fromEntries(Object.entries(RANGOS).map(([k, r]) => [k, r.defecto]));

function lienzoFalso(extra = {}) {
  return Object.assign({
    clientWidth: 240, clientHeight: 320, width: 240, height: 320,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 240, height: 320 }),
  }, extra);
}

/** Avanza `seg` s de frames a 60 Hz: antes(i) antes de cada frame y despues(i) tras él. */
function correr(seg, antes = null, despues = null) {
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

/** Asistente con un VRM falso ya cargado (el GLTFLoader falso se completa a mano). */
function montar({ version = '1', expresiones = EXPRESIONES_BASE } = {}) {
  frames = [];
  const eventos = [];
  const m = motor.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm', onEvento: (t, d) => eventos.push([t, d]) });
  const carga = cargas.pop();
  assert.ok(carga && carga.url === '/vrm/actual.vrm', 'el motor pidió el modelo');
  const vrm = crearVRMFalso({ version, expresiones });
  carga.alCargar({ scene: vrm.scene, userData: { vrm } });
  return { m, vrm, eventos, est: m.ctx.estado() };
}

/** Deja la asistente en 'normal' sin idles (para aislar gestos y seguimiento). */
function quietaSinIdles(m) {
  correr(3);                                   // el saludo (wave, 2.6 s) vuelve solo a normal
  m.mod('idles', 'set', { activo: false });
  correr(1.5);                                 // el idle se funde a 0 en 1 s
}

// Rotación de un Euler 'XYZ' de three.js: R = Rx·Ry·Rz (matriz 3×3 por filas).
function matEuler({ x, y, z }) {
  const [cx, sx, cy, sy, cz, sz] = [Math.cos(x), Math.sin(x), Math.cos(y), Math.sin(y), Math.cos(z), Math.sin(z)];
  const Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]];
  const Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]];
  const Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]];
  return mul(Rx, mul(Ry, Rz));
}
function mul(A, B) { return A.map((f) => [0, 1, 2].map((j) => f[0] * B[0][j] + f[1] * B[1][j] + f[2] * B[2][j])); }
const aplicar = (A, v) => A.map((f) => f[0] * v[0] + f[1] * v[1] + f[2] * v[2]);
/** Mano respecto al hombro (brazo y antebrazo de 1 m) en convención VRM 1.0: +Z = delante. */
function mano(vrm, lado) {
  const eje = lado === 'left' ? [1, 0, 0] : [-1, 0, 0];      // T-pose: izquierdo a +X, derecho a −X
  const Ru = matEuler(vrm.huesos[lado + 'UpperArm'].rotation);
  const Rl = matEuler(vrm.huesos[lado + 'LowerArm'].rotation);
  const codo = aplicar(Ru, eje), ante = aplicar(mul(Ru, Rl), eje);
  return codo.map((c, i) => c + ante[i]);
}

// ── Tests del motor ─────────────────────────────────────────────────────────────

test('lune_vrm.js carga con idles y movimiento en el bus, y PARAMS tiene los defectos de RANGOS', () => {
  const { PARAMS } = motor;
  for (const [k, r] of Object.entries(RANGOS)) assert.equal(PARAMS[k], r.defecto, `PARAMS.${k} ≠ RANGOS.${k}.defecto`);
  for (const k of ['swayGanH', 'swayGanV', 'swayMaxZ', 'swayMaxX', 'swayFrec', 'swayZeta', 'swayFiltro',
    'invertirH', 'invertirV', 'invertirBrazos', 'invertirPiernas']) {
    assert.equal(PARAMS[k], PARAMS_SWAY[k], `PARAMS.${k} ≠ PARAMS_SWAY.${k}`);
  }
  assert.equal('idleCambio' in PARAMS, false);
  assert.equal('idleMezcla' in PARAMS, false);

  const { m, vrm, eventos } = montar();
  assert.deepEqual(m.bus.lista(), ['idles', 'movimiento']);
  assert.equal(m.listo, true);
  assert.equal(m.estado, 'wave', 'saluda al cargar');
  assert.ok(eventos.some(([t]) => t === 'listo'));
  assert.equal(m.meta().ejes, 1, 'VRM 1.0: sin invertir');
  assert.equal(m.ctx.tieneExpr('blink'), true);
  assert.equal(m.ctx.tieneExpr('dizzy'), false);
  assert.equal(typeof m.luneParams, 'function');
  vaciarCola();
  correr(1);
  assert.ok(vrm.actualizaciones >= 59, 'vrm.update cada frame');
  assert.ok(vrm.huesos.leftUpperArm.rotation.z < -0.8, 'A-pose: brazo izquierdo abajo');
  assert.ok(vrm.lookAt.target && m.ctx.scene.children.includes(vrm.lookAt.target), 'los ojos miran al objetivo de la escena');
});

test('arrastre: balanceo recortado a swayMaxZ, seguimiento ×0.4, idle cede y eventos arrastre {on}', () => {
  const { m, vrm, est } = montar();
  correr(3);
  vaciarCola();
  assert.ok(m.mod('idles', 'estado').peso > 0.5, 'idle activo antes de arrastrar');
  assert.equal(est.inh.seguimiento, 1);
  m.drag(true, 0, 0);
  let maxZ = 0;
  const hips = vrm.huesos.hips.rotation;
  // 3 px/ms = 3000 px/s → objetivo 3000·0.0167 = 50.1°, que se recorta a swayMaxZ = 45°
  correr(4, () => m.drag(true, 3, 0), () => { maxZ = Math.max(maxZ, Math.abs(hips.z)); });
  assert.equal(est.drag, true);
  assert.equal(est.dragVx, 3000, 'est.dragVx en px/s sin filtrar');
  cerca(est.dragPeso, 1, 1e-3);
  const s = m.mod('movimiento', 'estado');
  cerca(s.leanZ, 45, 0.5, 'régimen = swayMaxZ');
  cerca(hips.z, 45 * G2R, 1 * G2R, 'caderas ladeadas 45° (sXZ = 1)');
  // el muelle (ζ 0.5) sobrepasa el objetivo recortado como mucho e^(−πζ/√(1−ζ²)) ≈ 16.3 %
  assert.ok(maxZ <= 45 * 1.17 * G2R, `sobrepaso excesivo: ${maxZ / G2R}°`);
  assert.ok(Math.abs(s.brazos[1]) <= 35 + 1e-9, 'extremidades ±35°');
  // colgada de las axilas: brazo izquierdo muy por encima de la A-pose (−1.15)
  assert.ok(vrm.huesos.leftUpperArm.rotation.z > -0.6, `brazo ${vrm.huesos.leftUpperArm.rotation.z}`);
  // factores del frame: el seguimiento baja a ×0.4 (módulo movimiento); el idle no se
  // inhibe por factor (inh.idle = 1): el propio módulo 'idles' multiplica por (1 − dragPeso)
  cerca(est.inh.seguimiento, 0.4, 0.01);
  assert.equal(est.inh.idle, 1);
  assert.ok(m.mod('idles', 'estado').peso < 0.01, 'el idle cede al arrastre');
  // soltar: el arrastre dura al menos dragMinimo (0.3 s)
  m.drag(false, 0, 0);
  correr(0.2);
  assert.equal(est.drag, true, 'bloqueo mínimo');
  correr(0.2);
  assert.equal(est.drag, false);
  assert.equal(est.dragVx, 0);
  const ev = vaciarCola().filter((e) => e.t === 'arrastre').map((e) => e.d);
  assert.deepEqual(ev, [{ on: true }, { on: false }]);
  correr(8);
  cerca(m.mod('movimiento', 'estado').leanZ, 0, 0.5, 'vuelve al soltar');
  assert.ok(m.mod('idles', 'estado').peso > 0.5, 'el idle vuelve');
});

test('arrastre con el ratón quieto: sin muestras en dragCaducidad s la velocidad cae a 0', () => {
  const { m, est } = montar();
  correr(1);
  m.drag(true, 2, 0);
  correr(0.05);
  assert.equal(est.dragVx, 2000);
  correr(0.25);
  assert.equal(est.drag, true, 'sigue arrastrando (botón pulsado)');
  assert.equal(est.dragVx, 0, 'velocidad caducada');
  m.drag(false, 0, 0);
  correr(0.5);
  vaciarCola();
});

test('agitarla emite mareo {inversiones, eje} por ctx.emitir → window.luneEventos', () => {
  const { m } = montar();
  correr(3);
  vaciarCola();
  m.drag(true, 0, 0);
  // 2000 px/s cambiando de sentido cada 0.2 s: ≥ 4 inversiones en 1.5 s
  correr(1.5, (i) => m.drag(true, (Math.floor(i / 12) % 2 ? -2 : 2), 0));
  const ev = vaciarCola();
  const mareo = ev.find((e) => e.t === 'mareo');
  assert.ok(mareo, `sin mareo en ${JSON.stringify(ev.map((e) => e.t))}`);
  assert.ok(mareo.d.inversiones >= 4);
  assert.equal(mareo.d.eje, 'x');
  assert.equal(m.mod('movimiento', 'estado').mareo, true);
  assert.deepEqual(ev.filter((e) => e.t === 'arrastre').map((e) => e.d), [{ on: true }]);
  m.drag(false, 0, 0);
  correr(0.5);
  vaciarCola();
});

test('gestos: fundido sin saltos al cambiar (gestoPeso continuo) y los de duración vuelven a normal', () => {
  const { m, vrm, est } = montar();
  correr(0.1);
  assert.ok(est.gestoPeso > 0 && est.gestoPeso < 1, `el saludo entra fundiéndose (${est.gestoPeso})`);
  quietaSinIdles(m);
  assert.equal(m.estado, 'normal', 'wave dura 2.6 s');
  cerca(est.gestoPeso, 0, 1e-6);
  vaciarCola();
  m.setEstado('happy');
  correr(1);
  cerca(est.gestoPeso, 1, 1e-6);
  const cabeza = vrm.huesos.head.rotation;
  const xHappy = cabeza.x;
  m.setEstado('sad');
  let prev = cabeza.x, maxSalto = 0;
  const pesos = [];
  correr(0.6, null, () => { maxSalto = Math.max(maxSalto, Math.abs(cabeza.x - prev)); prev = cabeza.x; pesos.push(est.gestoPeso); });
  // happy (cabeza −0.04) → sad (+0.22) en 0.45 s con smoothstep: nunca de golpe
  cerca(cabeza.x - xHappy, 0.26, 0.01, 'llega a la pose de sad');
  assert.ok(maxSalto < 0.02, `salto de ${maxSalto} rad en un frame`);
  // saliente (1 − s) + entrante (s) = 1; la capa saliente se descarta por debajo de 1e-4
  for (const p of pesos) cerca(p, 1, 2e-4, 'gestoPeso = saliente + entrante');
  // hacia normal: el peso baja suave en 0.5 s
  m.setEstado('normal');
  const bajada = [];
  correr(0.7, null, () => bajada.push(est.gestoPeso));
  for (let i = 1; i < bajada.length; i++) assert.ok(bajada[i] <= bajada[i - 1] + 1e-12, 'baja monótono');
  assert.ok(bajada.some((p) => p > 0.3 && p < 0.7), 'hay valores intermedios');
  cerca(bajada[bajada.length - 1], 0, 1e-6);
  // un gesto con duración vuelve solo y lo avisa
  m.setEstado('dismiss');
  correr(1.8);
  assert.equal(m.estado, 'normal');
  const estados = vaciarCola().filter((e) => e.t === 'estado').map((e) => e.d.nombre);
  assert.deepEqual(estados, ['happy', 'sad', 'normal', 'dismiss', 'normal']);
});

test('signo X de los brazos: typing/working y manosDelante con las manos DELANTE, manosEspalda DETRÁS', () => {
  const { m, vrm } = montar();
  quietaSinIdles(m);
  for (const estado of ['typing', 'working']) {
    m.setEstado(estado);
    correr(1);
    for (const lado of ['left', 'right']) {
      const p = mano(vrm, lado);
      assert.ok(p[2] > 0.5, `${estado}: mano ${lado} delante (z = ${p[2].toFixed(3)})`);
    }
    assert.ok(vrm.huesos.leftUpperArm.rotation.x < 0, 'x negativa en VRM 1.0');
  }
  m.setEstado('normal');
  m.mod('idles', 'set', { activo: true });
  for (const [variante, delante] of [['manosDelante', true], ['manosEspalda', false]]) {
    assert.equal(m.mod('idles', 'variante', variante), variante);
    correr(2);
    for (const lado of ['left', 'right']) {
      const z = mano(vrm, lado)[2];
      assert.ok(delante ? z > 0.3 : z < -0.1, `${variante}: mano ${lado} z = ${z.toFixed(3)}`);
    }
  }
  // VRM 0.x: el rig va girado 180°, las rotaciones X/Z salen con el signo cambiado
  const v0 = montar({ version: '0' });
  assert.equal(v0.m.meta().ejes, -1);
  quietaSinIdles(v0.m);
  v0.m.setEstado('typing');
  correr(1);
  assert.ok(v0.vrm.huesos.leftUpperArm.rotation.x > 0, 'x invertida por sXZ');
  assert.ok(v0.vrm.huesos.leftUpperArm.rotation.z > 1.5, 'z invertida por sXZ');
  vaciarCola();
});

test('luneParams: lista blanca, luz, altura, pesos de seguimiento e invertirEjes sin recargar', () => {
  const { m, vrm } = montar();
  try {
    quietaSinIdles(m);
    m.cursor(1.5, 0, -1, -1, false);             // cursor muy a la derecha
    correr(1.5);
    cerca(vrm.huesos.head.rotation.y, 45 * G2R * 0.75, 0.01, 'cabeza sigue el cursor (tope 45°)');
    cerca(vrm.lookAt.target.position.x, 1.5 * 0.6, 0.01, 'ojos');
    const r = m.luneParams('{"luz": 2, "altura": 0.1, "pesoCabeza": 0, "pesoOjos": 0.5, "fov": 99, "idleCambio": 3}');
    assert.equal(r, '{"luz":2,"altura":0.1,"pesoCabeza":0,"pesoOjos":0.5}');
    assert.equal(motor.PARAMS.fov, 24, 'fov no está en la lista blanca');
    const luces = m.ctx.scene.children;
    cerca(luces.find((o) => o instanceof DirectionalLight).intensity, Math.PI * 0.9 * 2, 1e-9, 'luz direccional ×2');
    cerca(luces.find((o) => o instanceof HemisphereLight).intensity, 2, 1e-9, 'luz ambiente ×2');
    correr(1);
    cerca(vrm.huesos.head.rotation.y, 0, 1e-9, 'pesoCabeza 0: la cabeza no sigue');
    cerca(vrm.huesos.neck.rotation.y, 0, 1e-9, 'ni el cuello');
    cerca(vrm.huesos.spine.rotation.y, 15 * G2R * 0.5, 0.005, 'el torso sí (pesoTorso 1)');
    cerca(vrm.lookAt.target.position.x, 1.5 * 0.6 * 0.5, 0.01, 'ojos × pesoOjos');
    cerca(vrm.scene.position.y, 0.1, 1e-3, 'altura');
    assert.equal(m.ctx.sXZ, 1);
    assert.equal(m.luneParams({ invertirEjes: -1 }), '{"invertirEjes":-1}');
    assert.equal(m.ctx.sXZ, -1, 'forzado sin recargar');
    m.luneParams({ invertirEjes: 'auto' });
    assert.equal(m.ctx.sXZ, 1, 'automático: se vuelve a medir el brazo');
    assert.equal(cargas.length, 0, 'no se pidió otra carga del modelo');
    // swayGanH en caliente: el módulo movimiento lee ctx.PARAMS
    m.luneParams({ swayGanH: 0.005 });
    assert.equal(m.mod('movimiento', 'params').swayGanH, 0.005);
  } finally {
    m.luneParams(DEFECTOS);
    assert.equal(motor.PARAMS.swayGanH, RANGOS.swayGanH.defecto);
  }
});

test('las tres expresiones por respuesta siguen igual; dizzy usa la expresión del modelo o el respaldo', () => {
  const { m, vrm } = montar();
  quietaSinIdles(m);
  vaciarCola();
  for (const [estado, clave, min] of [['happy', 'happy', 0.95], ['laughing', 'happy', 0.95], ['curious', 'surprised', 0.33]]) {
    m.setEstado(estado);
    correr(0.8);
    assert.ok(vrm.valores[clave] >= min, `${estado}: ${clave} = ${vrm.valores[clave]}`);
  }
  // Sin 'dizzy' en el modelo: respaldo (sad/surprised/relaxed) y cabeza en círculos 2.5 s
  m.setEstado('dizzy');
  correr(0.8);
  assert.equal(m.estado, 'dizzy');
  assert.ok(vrm.valores.sad >= 0.3, `respaldo sad = ${vrm.valores.sad}`);
  const h = vrm.huesos.head.rotation;
  const antes = [h.x, h.z];
  correr(0.3);
  assert.ok(Math.hypot(h.x - antes[0], h.z - antes[1]) > 0.02, 'la cabeza da vueltas');
  correr(1.6);
  assert.equal(m.estado, 'normal', 'el mareo dura 2.5 s');
  const estados = vaciarCola().filter((e) => e.t === 'estado').map((e) => e.d.nombre);
  assert.deepEqual(estados, ['happy', 'laughing', 'curious', 'dizzy', 'normal']);

  // Con una expresión 'Dizzy' propia (se resuelve sin mayúsculas): se usa sola
  const c = montar({ expresiones: [...EXPRESIONES_BASE, 'Dizzy'] });
  quietaSinIdles(c.m);
  assert.equal(c.m.ctx.tieneExpr('dizzy'), true);
  c.m.setEstado('dizzy');
  correr(0.8);
  assert.ok(c.vrm.valores.Dizzy > 0.95, `Dizzy = ${c.vrm.valores.Dizzy}`);
  assert.ok((c.vrm.valores.sad || 0) < 0.01, 'sin el respaldo');
  correr(2.5);
  assert.equal(c.m.estado, 'normal');
  assert.equal(c.vrm.valores.Dizzy, 0, 'al acabar se escribe 0 (three-vrm no la limpia)');
  vaciarCola();
});

// ── Robustez del motor (revisión de los cortes 2+3) ─────────────────────────────

/**
 * Codo y mano respecto al hombro en coordenadas del MUNDO (el modelo mira a +Z), en
 * VRM 1.0 y 0.x: en los 0.x el rig nace girado 180° (brazo izquierdo a −X en T-pose,
 * rotaciones X/Z con el signo cambiado por sXZ) y rotateVRM0 gira la escena 180°.
 */
function brazoMundo(vrm, lado, version = '1') {
  const v0 = version === '0';
  const eje = (lado === 'left') !== v0 ? [1, 0, 0] : [-1, 0, 0];
  const Ru = matEuler(vrm.huesos[lado + 'UpperArm'].rotation);
  const Rl = matEuler(vrm.huesos[lado + 'LowerArm'].rotation);
  const codo = aplicar(Ru, eje), ante = aplicar(mul(Ru, Rl), eje);
  const manoP = codo.map((c, i) => c + ante[i]);
  const giro = (p) => (v0 ? [-p[0], p[1], -p[2]] : p);
  return { codo: giro(codo), mano: giro(manoP) };
}

test('estirarse: brazos abajo y atrás, nunca por encima de la horizontal (VRM 1.0 y 0.x)', () => {
  for (const version of ['1', '0']) {
    const { m, vrm } = montar({ version });
    correr(3);                                       // acaba el saludo
    m.mod('idles', 'variante', 'mirarAlrededor');    // una variante que no mueve los brazos
    correr(1.2);
    assert.equal(m.mod('idles', 'estirar'), 'estirarse');
    let maxY = -Infinity, zPico = null, n = 0;
    correr(3.2, null, () => {
      n++;
      for (const lado of ['left', 'right']) {
        const b = brazoMundo(vrm, lado, version);
        maxY = Math.max(maxY, b.codo[1], b.mano[1]);
      }
      if (n === 90) zPico = ['left', 'right'].map((lado) => brazoMundo(vrm, lado, version).mano[2]);   // 1.5 s: en pleno estiramiento
    });
    assert.ok(maxY < 0, `VRM ${version}: codo o mano por encima del hombro (y = ${maxY.toFixed(3)})`);
    for (const z of zPico) assert.ok(z < -0.3, `VRM ${version}: las manos van atrás (z = ${z.toFixed(3)})`);
    vaciarCola();
  }
});

test('cargar un modelo con ella dormida no la despierta: sin saludo ni despertar, sigue dormida', () => {
  frames = [];
  vaciarCola();
  const m = motor.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm' });
  const carga = cargas.pop();
  // companion._on_cargado manda luneSleep(true) antes de que acabe la descarga del .vrm
  m.dormir(true);
  assert.deepEqual(vaciarCola().map((e) => e.t), ['dormir']);
  correr(0.2);
  const vrm = crearVRMFalso();
  carga.alCargar({ scene: vrm.scene, userData: { vrm } });
  correr(1);
  const nombres = (ev) => ev.map((e) => e.t + (e.d && e.d.nombre ? ':' + e.d.nombre : ''));
  let ev = nombres(vaciarCola());
  assert.equal(m.durmiendo, true);
  assert.notEqual(m.estado, 'wave');
  assert.ok(!ev.includes('despertar') && !ev.includes('estado:wave'), JSON.stringify(ev));
  assert.equal(m.ctx.estado().sleepBlend, 1, 'aparece ya dormida, sin fundido');
  assert.equal(vrm.valores.blink, 1, 'ojos cerrados');
  assert.equal(m.mod('idles', 'estado').unico, null, 'no bosteza: no se está durmiendo, ya lo estaba');
  // recargar_modelo() con ella dormida (luneCargarModelo)
  m.cargar('/vrm/actual.vrm?v=2');
  const c2 = cargas.pop();
  correr(0.2);
  const vrm2 = crearVRMFalso();
  c2.alCargar({ scene: vrm2.scene, userData: { vrm: vrm2 } });
  correr(1);
  ev = nombres(vaciarCola());
  assert.equal(m.durmiendo, true);
  assert.ok(!ev.includes('despertar') && !ev.includes('estado:wave'), JSON.stringify(ev));
  // despierta como siempre, y con ella despierta un modelo nuevo sí saluda
  m.dormir(false);
  assert.deepEqual(vaciarCola().map((e) => e.t), ['despertar']);
  m.cargar('/vrm/actual.vrm?v=3');
  const vrm3 = crearVRMFalso();
  cargas.pop().alCargar({ scene: vrm3.scene, userData: { vrm: vrm3 } });
  assert.equal(m.estado, 'wave');
  m.destruir();
  vaciarCola();
});

test('arrastre sin modelo o con uno roto: luneDrag(false) suelta y avisa; no fuerza 60 fps', () => {
  for (const caso of ['sin modelo', 'modelo roto']) {
    frames = [];
    vaciarCola();
    const m = motor.crearAsistente({ canvas: lienzoFalso(), src: caso === 'sin modelo' ? undefined : '/vrm/roto.vrm' });
    if (caso === 'modelo roto') cargas.pop().alFallar(new Error('404'));
    correr(0.5);
    const r0 = m.ctx.renderer.renders;
    m.drag(true, 0, 0);
    correr(1, () => m.drag(true, 1, 0));
    const porSegundo = m.ctx.renderer.renders - r0;
    assert.ok(porSegundo <= 32, `${caso}: ${porSegundo} renders/s arrastrando una escena vacía`);
    m.drag(false, 0, 0);
    correr(0.5);
    const ev = vaciarCola().filter((e) => e.t === 'arrastre').map((e) => e.d);
    assert.deepEqual(ev, [{ on: true }, { on: false }], caso);
    m.destruir();
  }
});

test('setEstado con nombres que hereda un objeto (constructor, __proto__) cae en normal', () => {
  const { m, vrm } = montar();
  quietaSinIdles(m);
  vaciarCola();
  for (const n of ['constructor', '__proto__', 'CONSTRUCTOR']) {
    m.setEstado(n);
    assert.equal(m.estado, 'normal', n);
    correr(0.1);
  }
  assert.deepEqual(vaciarCola().filter((e) => e.t === 'estado').map((e) => e.d.nombre), ['normal', 'normal', 'normal']);
  for (const n of ['constructor', '__proto__', 'toString']) assert.equal(m.ctx.tieneExpr(n), false, n);
  for (const e of ['happy', 'sad', 'angry', 'relaxed']) assert.ok(Number.isFinite(vrm.valores[e]), e);
});

test('un módulo opcional roto (404 o error de sintaxis) no tumba el avatar', async () => {
  const sintaxis = (n) => aDataURL(`export const x${n} = ;`);
  const noExiste = (n) => new URL(`vrm/no_existe_${n}.js`, UI).href;
  const avisos = [];
  const warn = console.warn;
  console.warn = (...a) => avisos.push(a.join(' '));
  let sinNada, sinIdles;
  try {
    sinNada = await import(aDataURL(reescribirImports(readFileSync(URL_MOTOR, 'utf8'), URL_MOTOR, {
      './lune_idles.js': sintaxis(1), './lune_movimiento.js': noExiste('mov'),
      './lune_params.js': sintaxis(2), './lune_gestos.js': noExiste('gestos'),
    })));
    sinIdles = await import(aDataURL(reescribirImports(readFileSync(URL_MOTOR, 'utf8'), URL_MOTOR, {
      './lune_idles.js': noExiste('idles'),
    })));
  } finally { console.warn = warn; }
  sinNada.PARAMS.esperaTemporizador = false; sinIdles.PARAMS.esperaTemporizador = false;   // frames simulados
  assert.deepEqual({ ...sinNada.MODULOS_OPCIONALES }, { gestos: false, idles: false, movimiento: false, params: false });
  for (const f of ['lune_gestos.js', 'lune_idles.js', 'lune_movimiento.js', 'lune_params.js']) {
    assert.ok(avisos.some((a) => a.includes(f)), `avisa en consola de ${f}`);
  }
  assert.deepEqual({ ...sinIdles.MODULOS_OPCIONALES }, { gestos: true, idles: false, movimiento: true, params: true });

  frames = [];
  vaciarCola();
  const m = sinNada.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm' });
  const vrm = crearVRMFalso();
  cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
  assert.equal(m.listo, true);
  assert.deepEqual(m.bus.lista(), [], 'sin idles ni movimiento');
  assert.equal(m.estado, 'wave', 'saluda con el mezclador mínimo');
  correr(3);
  assert.equal(m.estado, 'normal', 'el saludo vuelve solo');
  assert.ok(vrm.actualizaciones > 150, 'el bucle anima el modelo');
  m.setEstado('happy');
  correr(2);
  cerca(vrm.huesos.head.rotation.x, -0.04, 0.005, 'pose de happy con el respaldo');
  assert.ok(vrm.valores.happy > 0.9);
  m.setEstado('dizzy');
  correr(2.8);
  assert.equal(m.estado, 'normal', 'mareo de respaldo de 2.5 s');
  assert.equal(m.luneParams('{"luz": 2}'), '{}', 'sin lista blanca no se aplica nada');
  assert.equal(m.meta().ejes, 1);
  m.drag(true, 1, 0); correr(0.2); m.drag(false, 0, 0); correr(0.5);
  assert.deepEqual(vaciarCola().filter((e) => e.t === 'arrastre').map((e) => e.d), [{ on: true }, { on: false }]);
  m.destruir();

  frames = [];
  const m2 = sinIdles.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm' });
  const vrm2 = crearVRMFalso();
  cargas.pop().alCargar({ scene: vrm2.scene, userData: { vrm: vrm2 } });
  assert.deepEqual(m2.bus.lista(), ['movimiento'], 'solo falta el que no cargó');
  correr(0.5);
  m2.destruir();
  vaciarCola();
});

test('destruir (barra lateral): la carga en vuelo no entra en la escena del motor muerto; sin bucle, resize ni contexto', async () => {
  const barra = await import('../../ui_web/ui_kits/lune-desktop/vrm_barra.js');
  const oyentes = [];
  const cancelados = [];
  const orig = [globalThis.addEventListener, globalThis.removeEventListener, globalThis.cancelAnimationFrame];
  globalThis.addEventListener = (t, f) => { oyentes.push([t, f]); };
  globalThis.removeEventListener = (t, f) => { const i = oyentes.findIndex(([a, g]) => a === t && g === f); if (i >= 0) oyentes.splice(i, 1); };
  globalThis.cancelAnimationFrame = (id) => { cancelados.push(id); };
  const resize = () => oyentes.filter(([t]) => t === 'resize').length;
  try {
    frames = [];
    let m = null;
    const errores = [];
    const ventana = { addEventListener() {}, removeEventListener() {}, innerWidth: 1280, innerHeight: 820 };
    const lienzo = lienzoFalso({ style: {}, getContext: () => ({}), addEventListener() {}, removeEventListener() {} });
    const h = barra.crear(lienzo, '/vrm/actual.vrm', {
      version: 'v1', ventana, crearAsistente: (o) => (m = motor.crearAsistente(o)), alError: (e) => errores.push(e),
    });
    await new Promise((r) => setTimeout(r, 0));
    assert.ok(m, 'motor creado');
    assert.equal(resize(), 1, 'el motor escucha resize');
    const vrm1 = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm1.scene, userData: { vrm: vrm1 } });
    assert.equal(h.listo, true);
    // Cambio de modelo (LuneVRMBarra.recargar) y, antes de que llegue, se desmonta la barra
    assert.equal(barra.recargar('/vrm/actual.vrm', 'v2'), 1);
    const enVuelo = cargas.pop();
    assert.match(enVuelo.url, /v=v2/);
    assert.equal(h.destruir(), true);
    assert.equal(m.destruido, true, 'vrm_barra usa m.destruir()');
    assert.equal(m.ctx.renderer.liberado, 1, 'renderer.dispose() una vez (sin el respaldo duplicado)');
    assert.equal(m.ctx.renderer.perdido, 1, 'forceContextLoss() una vez');
    assert.equal(resize(), 0, 'listener de resize quitado');
    assert.equal(cancelados.length, 1, 'requestAnimationFrame cancelado');
    assert.deepEqual(m.bus.lista(), [], 'módulos del bus descargados');
    assert.ok(VRMUtils.liberadas.includes(vrm1.scene), 'el modelo anterior se liberó');
    // La carga en vuelo termina ahora
    const vrm2 = crearVRMFalso();
    enVuelo.alCargar({ scene: vrm2.scene, userData: { vrm: vrm2 } });
    assert.equal(m.ctx.vrm(), null, 'el motor muerto no adopta el modelo');
    assert.ok(!m.ctx.scene.children.includes(vrm2.scene), 'ni lo mete en su escena');
    assert.ok(VRMUtils.liberadas.includes(vrm2.scene), 'lo que cargó se libera');
    assert.equal(m.listo, false);
    // El bucle no vuelve a pedir frames
    for (const f of frames.splice(0)) { reloj.ms += 16; f(reloj.ms); }
    assert.equal(frames.length, 0, 'sin frames nuevos');
    assert.equal(h.destruir(), false);
    assert.equal(m.destruir(), false, 'idempotente');
    assert.deepEqual(errores, []);

    // Motor suelto: un error de carga que llega tarde no avisa, y cargar() ya no pide nada
    const eventos = [];
    const m2 = motor.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/x.vrm', onEvento: (t) => eventos.push(t) });
    const tarde = cargas.pop();
    assert.equal(m2.destruir(), true);
    tarde.alFallar(new Error('llegó tarde'));
    m2.cargar('/vrm/y.vrm');
    assert.equal(cargas.length, 0);
    assert.ok(!eventos.includes('error'), JSON.stringify(eventos));
  } finally {
    [globalThis.addEventListener, globalThis.removeEventListener, globalThis.cancelAnimationFrame] = orig;
    vaciarCola();
  }
});

// ── Asistente animada: los eventos del módulo 'fisica' llegan a la cola ───────────

test('asistente animada: lune_anim_fisica emite arrastre {on}, mareo, dormir y despertar a window.luneEventos', () => {
  vaciarCola();
  let ms = 0;
  const reg = crearRegistroAnim({ stage: null, raf: () => 0, caf: () => {}, ahora: () => ms });
  reg.registrar(instalarFisica);
  const w = {};
  publicarFisica(w, reg);
  for (const fn of ['luneDrag', 'luneTouch', 'luneSleep']) assert.equal(typeof w[fn], 'function', fn);
  reg.paso(ms);
  w.luneDrag(true, 0, 0);
  for (let i = 0; i < 90; i++) {
    ms += 1000 / 60;
    w.luneDrag(true, Math.floor(i / 12) % 2 ? -2 : 2, 0);
    reg.paso(ms);
  }
  w.luneDrag(false, 0, 0);
  for (let i = 0; i < 40; i++) { ms += 1000 / 60; reg.paso(ms); }
  w.luneSleep(true);
  w.luneTouch();                                 // tocar despierta
  const ev = vaciarCola();
  assert.deepEqual(ev.map((e) => e.t), ['arrastre', 'mareo', 'arrastre', 'dormir', 'despertar']);
  assert.deepEqual(ev[0].d, { on: true });
  assert.deepEqual(ev[2].d, { on: false });
});

// ── Las páginas, ejecutando sus <script> en línea ───────────────────────────────

/** <script> en línea de una página (sin src ni importmap): [{modulo, codigo}]. */
function scriptsEnLinea(pagina) {
  const html = readFileSync(new URL(pagina, UI), 'utf8');
  const res = [];
  for (const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
    const attrs = m[1];
    if (/\bsrc=/.test(attrs) || /importmap/.test(attrs) || !m[2].trim()) continue;
    res.push({ modulo: /type="module"/.test(attrs), codigo: m[2] });
  }
  return { html, scripts: res };
}

/** Funciones window.* que llama ui/companion.py (lo mismo que busca tests/test_asistente_vrm.py). */
function llamadasDePython() {
  const py = readFileSync(new URL('../ui/companion.py', UI), 'utf8');
  return [...new Set([...py.matchAll(/window\.(lune\w+|setEmocion|comentar|pensando|ocultarBurbuja)\b/g)].map((m) => m[1]))].sort();
}

async function ejecutarPagina(pagina, documento, extraImports = {}) {
  const { html, scripts } = scriptsEnLinea(pagina);
  globalThis.document = documento;
  const base = new URL(pagina, UI);
  for (const s of scripts) {
    if (!s.modulo) vm.runInThisContext(s.codigo, { filename: pagina });
    else await import(aDataURL(reescribirImports(s.codigo, base, extraImports)));
  }
  return html;
}

test('companion_vrm.html: sin FRASES, luneParams antes y después del módulo, y todo lo que llama Python existe', async () => {
  const raiz = crearElemento('body');
  const stage = raiz.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=7' };
  frames = [];
  const { html } = scriptsEnLinea('companion_vrm.html');
  assert.equal(/FRASES|frase\(/.test(html), false, 'las frases son de Python (frases_asistente.py)');
  try {
    // El script clásico se ejecuta primero: una llamada temprana queda pendiente
    vm.runInThisContext(scriptsEnLinea('companion_vrm.html').scripts[0].codigo, { filename: 'companion_vrm.html' });
    assert.equal(globalThis.luneParams('{"luz": 1.5}'), null);
    await ejecutarPagina('companion_vrm.html', crearDocumento(raiz), { './vrm/lune_vrm.js': DATA_MOTOR });
    assert.equal(motor.PARAMS.luz, 1.5, 'se aplicó la llamada pendiente');
    assert.equal(globalThis.__luneParamsPendiente, null);
    assert.equal(globalThis.luneParams('{"altura": 0.2}'), '{"altura":0.2}');
    const carga = cargas.pop();
    assert.equal(carga.url, '/vrm/actual.vrm?v=7');
    const vrm = crearVRMFalso();
    carga.alCargar({ scene: vrm.scene, userData: { vrm } });
    assert.equal(globalThis.luneReady, true);
    for (const fn of llamadasDePython()) assert.equal(typeof globalThis[fn], 'function', `companion.py llama a window.${fn}`);
    // dormir: solo el conmutador zzz (el texto lo pone Python)
    globalThis.luneSleep(true);
    assert.equal(zzz.classList.contains('on'), true);
    globalThis.luneSleep(false);
    assert.equal(zzz.classList.contains('on'), false);
    const ev = vaciarCola().map((e) => e.t);
    assert.ok(ev.includes('dormir') && ev.includes('despertar'), JSON.stringify(ev));
  } finally {
    motor.PARAMS.luz = DEFECTOS.luz; motor.PARAMS.altura = DEFECTOS.altura;
  }
});

test('companion_vrm.html: avisos de error como texto (sin innerHTML) y al dormirse oculta la burbuja', async () => {
  const raiz = crearElemento('body');
  const stage = raiz.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  const aviso = stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(raiz);
  const TRAMPA = '<img src=x onerror="alert(1)">';
  globalThis.location = { search: '?src=' + encodeURIComponent('/vrm/' + TRAMPA + '.vrm') + '&v=3' };
  // lune_burbuja.js falso: solo apunta lo que le piden
  const burbuja = [];
  globalThis.luneBurbuja = { comentar: (t) => burbuja.push(['comentar', t]), pensando() {}, ocultar: () => burbuja.push(['ocultar']), setVoz() {} };
  const oyentes = {};
  const add = globalThis.addEventListener;
  globalThis.addEventListener = (t, f) => { (oyentes[t] = oyentes[t] || []).push(f); };
  frames = [];
  try {
    globalThis.document = doc;
    for (const s of scriptsEnLinea('companion_vrm.html').scripts) {
      if (!s.modulo) vm.runInThisContext(s.codigo, { filename: 'companion_vrm.html' });
      // (el comentario final hace otra URL: el módulo se vuelve a ejecutar)
      else await import(aDataURL(reescribirImports(s.codigo, new URL('companion_vrm.html', UI), { './vrm/lune_vrm.js': DATA_MOTOR }) + '\n// otra vez'));
    }
  } finally { globalThis.addEventListener = add; }
  const textoDe = (n) => (n.textContent || '') + n.children.map(textoDe).join('');
  const etiquetas = (n) => [n.tagName, ...n.children.flatMap(etiquetas)];
  const hijo = (n, tag) => (n.tagName === tag ? n : n.children.map((c) => hijo(c, tag)).find(Boolean) || null);
  try {
    // Fallo de arranque (antes de listo) con HTML en el mensaje: sale como texto
    assert.equal(globalThis.luneReady, false);
    for (const f of oyentes.error || []) f({ message: TRAMPA });
    assert.equal(aviso.classList.contains('on'), true);
    assert.equal(aviso.htmlCrudo, undefined, 'sin innerHTML');
    assert.ok(textoDe(aviso).includes(TRAMPA), textoDe(aviso));
    assert.ok(!etiquetas(aviso).includes('IMG') && !doc.creados.some((e) => e.tagName === 'IMG'));
    // Error del modelo (err.message puede traer cadenas del .vrm) y la ruta de la URL
    const carga = cargas.pop();
    assert.ok(carga.url.includes(TRAMPA));
    carga.alFallar(new Error(TRAMPA + ' en el .vrm'));
    assert.equal(aviso.htmlCrudo, undefined);
    assert.equal(hijo(aviso, 'CODE').textContent, '/vrm/' + TRAMPA + '.vrm');
    assert.equal(hijo(aviso, 'SMALL').textContent, TRAMPA + ' en el .vrm');
    assert.ok(!doc.creados.some((e) => e.tagName === 'IMG'));
    // Con modelo: al dormirse se oculta la burbuja; la frase de dormir (Python) sale después
    globalThis.luneCargarModelo('/vrm/actual.vrm?v=4');
    const vrm = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    assert.equal(globalThis.luneReady, true);
    assert.equal(aviso.classList.contains('on'), false);
    globalThis.comentar('Respuesta de la IA');
    burbuja.length = 0;
    globalThis.luneSleep(true);
    assert.deepEqual(burbuja, [['ocultar']]);
    assert.equal(zzz.classList.contains('on'), true);
    globalThis.comentar('zzz…');
    globalThis.luneSleep(true);                  // repetido: no vuelve a ocultar
    globalThis.luneSleep(false);                 // despertar: tampoco
    assert.deepEqual(burbuja, [['ocultar'], ['comentar', 'zzz…']], 'la frase de dormir se ve');
  } finally {
    try { globalThis.luneAsistente.destruir(); } catch (_) { /* sigue */ }
    delete globalThis.luneBurbuja;
    vaciarCola();
  }
});

test('companion.html: css de la animada, doble búfer, setEmocion pendiente y luneDrag/luneTouch/luneSleep tras cargar', async () => {
  const raiz = crearElemento('body');
  const bub = raiz.appendChild(crearElemento('div', 'bubble'));
  bub.appendChild(crearElemento('span', 'btxt'));
  const stage = raiz.appendChild(crearElemento('div', 'stage'));
  const v = stage.appendChild(crearElemento('video', 'v'));
  const doc = crearDocumento(raiz);
  stage.ownerDocument = doc; v.ownerDocument = doc;
  frames = [];
  delete globalThis.luneBurbuja;
  for (const fn of ['luneDrag', 'luneTouch', 'luneSleep', 'setEmocion', 'luneMod', 'luneSetFPS']) delete globalThis[fn];
  const { html, scripts } = scriptsEnLinea('companion.html');
  assert.ok(html.indexOf('href="css/burbuja.css"') < html.indexOf('href="css/asistente_anim.css"'), 'asistente_anim.css tras burbuja.css');
  assert.ok(/<video id="v"/.test(html), 'se deja el <video id="v">');
  assert.equal(scripts.length, 2);
  globalThis.document = doc;
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion.html' });
  assert.equal(globalThis.__luneEmocionPendiente, 'wave', 'el setEmocion clásico guarda la pendiente');
  assert.match(v.getAttribute('src'), /lune-wave\.webm$/);
  const clasico = globalThis.setEmocion;
  await import(aDataURL(reescribirImports(scripts[1].codigo, new URL('companion.html', UI))));
  assert.notEqual(globalThis.setEmocion, clasico, 'setEmocion pasa por el registro');
  assert.equal(globalThis.__luneEmocionPendiente, null, 'la pendiente se aplicó');
  assert.deepEqual(globalThis.luneAnim.lista(), ['video', 'fisica']);
  assert.equal(globalThis.luneMod('video', 'estado').base, 'wave');
  assert.equal(stage.classList.contains('lune-doble'), true, 'doble búfer activo');
  assert.ok(doc.getElementById('vb'), 'se creó el segundo vídeo');
  // Lo que llama companion.py y existe en la animada (luneCursor, luneEncuadre,
  // luneCargarModelo y luneParams son solo del VRM y Python los llama con `window.x &&`)
  const soloVRM = new Set(['luneCursor', 'luneEncuadre', 'luneCargarModelo', 'luneParams']);
  for (const fn of llamadasDePython()) {
    if (!soloVRM.has(fn)) assert.equal(typeof globalThis[fn], 'function', `companion.py llama a window.${fn}`);
  }
  vaciarCola();
  globalThis.luneDrag(true, 0, 0);
  globalThis.luneSleep(true);
  assert.deepEqual(vaciarCola().map((e) => [e.t, e.d]), [['arrastre', { on: true }], ['dormir', {}]]);
  globalThis.luneSetFPS(0);                    // para el bucle del registro
});
