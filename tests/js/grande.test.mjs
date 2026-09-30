// tests/js/grande.test.mjs — módulo 'grande' del VRM (ui_web/vrm/lune_grande.js, cortes 5 y 6)
// con el motor de verdad: distancia de encuadre (h = 0.12 y 0.25), fases con smoothstep,
// pixelRatio 1 y 30 fps al entrar, fin → encuadre del usuario, FOV y pixelRatio de antes;
// el colisionador del ratón sin duplicar en joints que comparten colliderGroups y que se
// quita al soltar y en alDescargar. Y la página companion_vrm.html con sus funciones nuevas.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  montar, correr, quietaSinIdles, vaciarCola, lienzoFalso, cargarClasico, scriptsEnLinea,
  aDataURL, reescribirImports, DATA_MOTOR, UI, cargas, crearVRMFalso, frames,
} from './motor_vrm_falso.mjs';
import { Vector3 } from './three_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import {
  instalar, alturaCabeza, distanciaEncuadre, curva, puntoRayo, PARAMS_GRANDE, NOMBRE, ORDEN,
} from '../../ui_web/vrm/lune_grande.js';
import vm from 'node:vm';

const G2R = Math.PI / 180;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

// Clases de three-vrm falsas: lo justo para el colisionador.
class ColFalso {
  constructor(shape) { this.shape = shape; this.position = new Vector3(); this.actualizado = 0; }
  updateMatrixWorld() { this.actualizado++; }
}
class EsferaFalsa { constructor(o) { Object.assign(this, o); } }
const DEPS = { VRMSpringBoneCollider: ColFalso, VRMSpringBoneColliderShapeSphere: EsferaFalsa };

test('encuadre de la cabeza: h = max(0.12, |head − neck|) y d = (1.4·h/2)/tan(fov/2)', () => {
  assert.equal(NOMBRE, 'grande');
  assert.equal(ORDEN, 60);
  cerca(alturaCabeza(1.40, 1.28), 0.12, 1e-12);
  cerca(alturaCabeza(1.40, 1.35), 0.12, 1e-12, 'mínimo 0.12');
  cerca(alturaCabeza(1.40, 1.15), 0.25, 1e-12);
  assert.equal(alturaCabeza(1.4, NaN), PARAMS_GRANDE.hDefecto, 'sin cuello');
  cerca(distanciaEncuadre(0.12, 24), (1.4 * 0.12 / 2) / Math.tan(12 * G2R), 1e-12);
  cerca(distanciaEncuadre(0.12, 24), 0.3952, 1e-4);
  cerca(distanciaEncuadre(0.25, 24), 0.8234, 1e-4);
  cerca(distanciaEncuadre(0.25, 60), (0.175) / Math.tan(30 * G2R), 1e-12, 'otro FOV');
  // curva: smoothstep del avance
  assert.equal(curva(0, 0, 500), 0);
  cerca(curva(0.25, 0, 500), 0.5, 1e-12);
  cerca(curva(0.125, 0, 500), 0.15625, 1e-12);
  assert.equal(curva(9, 0, 500), 1);
  assert.equal(curva(0, 0, 0), 1);
});

test('puntoRayo: centro de la pantalla a `prof` delante; esquina según FOV y aspecto', () => {
  const rect = { left: 0, top: 0, width: 1920, height: 1080 };
  const cam = { x: 0.1, y: 1.5, z: 0.6 };
  const c = puntoRayo({ px: 960, py: 540, rect, cam, fov: 24, aspect: 1920 / 1080, prof: 0.4 });
  cerca(c.x, 0.1, 1e-12); cerca(c.y, 1.5, 1e-12); cerca(c.z, 0.2, 1e-12);
  const e = puntoRayo({ px: 1920, py: 0, rect, cam, fov: 24, aspect: 1920 / 1080, prof: 1 });
  cerca(e.y - 1.5, Math.tan(12 * G2R), 1e-12, 'borde de arriba');
  cerca(e.x - 0.1, Math.tan(12 * G2R) * 1920 / 1080, 1e-12, 'borde derecho');
});

/** Motor con el módulo grande y un canvas que se puede «redimensionar». */
function conGrande({ version = '1', h = 0.12 } = {}) {
  const canvas = lienzoFalso();
  const r = montar({ version, canvas });
  quietaSinIdles(r.m);
  r.vrm.huesos.neck.position.y = r.vrm.huesos.head.position.y - h;
  const mod = r.m.registrar((ctx) => instalar(ctx, DEPS));
  vaciarCola();
  return { ...r, canvas, mod, cam: r.m.ctx.camera, renderer: r.m.ctx.renderer };
}
const cabeza = (vrm) => vrm.huesos.head.getWorldPosition(new Vector3());

test('secuencia completa: glide → entrar (cara) → activa → salir → volver → fin', () => {
  const { m, vrm, mod, cam, canvas, renderer, est } = conGrande({ h: 0.12 });
  assert.equal(mod.nombre, 'grande');
  const y0 = cam.position.y, z0 = cam.position.z;
  renderer.pixelRatio = 2;
  // glide: sube la cámara (el modelo se va por abajo); pixelRatio 1 y 30 fps
  assert.equal(m.mod('grande', 'fase', 'glide', { ms: 400 }), true);
  assert.equal(renderer.pixelRatio, 1);
  assert.equal(est.grande, true);
  const off = m.mod('grande', 'estado').normal.off;
  cerca(off, Math.max(0.5, 2 * z0 * Math.tan(12 * G2R)), 1e-6, 'desplazamiento = alto visible del encuadre');
  const planeo = [];
  correr(0.2, null, () => planeo.push(cam.position.y - y0));
  // (a 30 fps y empezando en el siguiente frame: ±1 frame de 60 Hz)
  cerca(cam.position.y, y0 + off * 0.5, off * 0.2, 'a mitad del planeo');
  const primeros = planeo.filter((v) => v > 1e-9);
  assert.ok(primeros[0] < off * 0.05, `smoothstep: empieza despacio (${primeros[0]})`);
  for (let i = 1; i < planeo.length; i++) assert.ok(planeo[i] >= planeo[i - 1] - 1e-12, 'sube sin volver atrás');
  assert.equal(m.mod('grande', 'estado').fase, 'glide');
  correr(0.3);
  cerca(cam.position.y, y0 + off, 1e-9, 'fuera de la vista');
  cerca(cam.position.z, z0, 1e-9);
  // Qt pone la ventana del monitor y manda entrar
  canvas.clientWidth = 1920; canvas.clientHeight = 1080;
  m.mod('grande', 'fase', 'entrar', { ms: 500 });
  let yMedio = null, primero = null;
  const ts = [];
  correr(0.6, null, (i) => {
    const hc = cabeza(vrm);
    const base = hc.y + 0.08;
    if (primero === null) primero = cam.position.y - base;
    if (i === 14) yMedio = cam.position.y - base;      // 0.25 s
    ts.push(cam.position.y - base);
  });
  assert.ok(primero > 0.45, `empieza 0.5 m por encima (${primero})`);
  cerca(yMedio, 0.25, 0.06, 'mitad del fundido con smoothstep');
  for (let i = 1; i < ts.length; i++) assert.ok(ts[i] <= ts[i - 1] + 1e-9, 'baja sin rebotes');
  const hc = cabeza(vrm);
  cerca(cam.position.y, hc.y + 0.08, 1e-3, 'camY = head.y + 0.08');
  cerca(cam.position.z - hc.z, 0.3952, 1e-3, 'd con h = 0.12');
  assert.deepEqual([cam.rotation.x, cam.rotation.y, cam.rotation.z], [0, 0, 0], 'mira en horizontal');
  assert.equal(m.mod('grande', 'estado').fase, 'activa');
  // activa: sigue a la cabeza suavizando; con h = 0.25 se aleja
  vrm.huesos.head.position.x = 0.05;
  vrm.huesos.neck.position.y = vrm.huesos.head.position.y - 0.25;
  correr(2);
  cerca(cam.position.x, 0.05, 2e-3, 'x sigue a la cabeza');
  cerca(cam.position.z - cabeza(vrm).z, 0.8234, 2e-3, 'd con h = 0.25');
  vrm.huesos.head.position.x = 0;
  // salir: vuelve a subir 0.5 m en 500 ms
  m.mod('grande', 'fase', 'salir');
  correr(0.6);
  cerca(cam.position.y, cabeza(vrm).y + 0.08 + 0.5, 1e-3, 'fuera de la vista');
  // Qt restaura la ventana; el resize llega DESPUÉS de 'volver' (Chromium): se relee
  m.mod('grande', 'fase', 'volver');
  correr(0.05);
  canvas.clientWidth = 240; canvas.clientHeight = 320;
  correr(0.5);
  cerca(cam.position.y, y0, 1e-6, 'acaba en el encuadre normal');
  cerca(cam.position.z, z0, 1e-6);
  assert.equal(est.grande, true, 'hasta fin sigue en grande');
  // fin: encuadre del usuario, FOV y pixelRatio de antes, fps activos
  globalThis.devicePixelRatio = 1.5;
  cam.fov = 40;                                        // alguien lo tocó: fin lo devuelve
  m.mod('grande', 'fase', 'fin');
  globalThis.devicePixelRatio = 1;
  assert.equal(cam.fov, 24);
  assert.equal(renderer.pixelRatio, 1.5);
  assert.equal(est.grande, false);
  assert.equal(m.mod('grande', 'estado').fase, null);
  correr(0.2);
  cerca(cam.position.y, y0, 1e-6); cerca(cam.position.z, z0, 1e-6);
  const fases = vaciarCola().filter((e) => e.t === 'grande_fase').map((e) => e.d.fase);
  assert.deepEqual(fases, ['glide', 'entrar', 'salir', 'volver', 'fin']);
  assert.equal(m.mod('grande', 'fase', 'patata'), false);
  m.destruir();
});

test('salida inmediata (fin a mitad) y una fase nueva arranca desde donde está la cámara', () => {
  const { m, cam, est } = conGrande();
  const y0 = cam.position.y;
  m.mod('grande', 'fase', 'glide');
  correr(0.1);
  m.mod('grande', 'fase', 'fin');
  assert.equal(est.grande, false);
  correr(0.1);
  cerca(cam.position.y, y0, 1e-6, 'fin en pleno planeo: encuadre normal');
  // salir en pleno 'entrar': sin salto
  m.mod('grande', 'fase', 'glide'); correr(0.5);
  m.mod('grande', 'fase', 'entrar'); correr(0.2);
  const antes = cam.position.y;
  m.mod('grande', 'fase', 'salir');
  correr(1 / 60 * 2);
  assert.ok(Math.abs(cam.position.y - antes) < 0.05, 'continua');
  m.mod('grande', 'fase', 'fin');
  m.destruir();
});

test('sujetar el pelo: un grupo por array distinto de colliderGroups, se quita al soltar y en alDescargar', () => {
  const { m, vrm, cam, canvas } = conGrande();
  const A = [{ colliders: [], name: 'pelo' }], B = [];
  const joints = [{ colliderGroups: A }, { colliderGroups: A }, { colliderGroups: A }, { colliderGroups: B }, {}];
  vrm.springBoneManager.joints = joints;
  assert.equal(m.mod('grande', 'hold', true, 10, 10), false, 'fuera de pantalla grande no hace nada');
  m.mod('grande', 'fase', 'glide'); correr(0.5);
  assert.equal(m.mod('grande', 'hold', true, 10, 10), false, 'en el planeo tampoco');
  canvas.clientWidth = 1920; canvas.clientHeight = 1080;
  m.mod('grande', 'fase', 'entrar'); correr(0.7);
  assert.equal(m.mod('grande', 'hold', true, 960, 540), true);
  assert.equal(A.length, 2, 'el array compartido lo recibe UNA vez');
  assert.equal(B.length, 1);
  const grupo = B[0];
  assert.equal(A[1], grupo);
  const col = grupo.colliders[0];
  assert.ok(col instanceof ColFalso);
  assert.equal(col.shape.radius, 0.04);
  correr(0.1);
  // En el centro, a max(0.4, profundidad de la cabeza) de la cámara
  const prof = Math.max(0.4, cam.position.z - cabeza(vrm).z);
  cerca(col.position.x, cam.position.x, 1e-3);
  cerca(col.position.y, cam.position.y, 1e-3);
  cerca(col.position.z, cam.position.z - prof, 1e-3);
  assert.ok(col.actualizado > 0);
  m.mod('grande', 'hold', true, 1920, 540);            // se mueve con el ratón
  correr(0.05);
  assert.ok(col.position.x > cam.position.x + 0.05);
  m.mod('grande', 'hold', true, 900, 500);              // repetir no duplica
  assert.equal(A.length, 2); assert.equal(B.length, 1);
  assert.equal(m.mod('grande', 'hold', false), true);
  assert.deepEqual(A.map((g) => g.name), ['pelo']);
  assert.equal(B.length, 0);
  // otra vez y cambio de modelo: alDescargar lo quita
  m.mod('grande', 'hold', true, 960, 540);
  assert.equal(A.length, 2);
  m.cargar('/vrm/otro.vrm');
  assert.deepEqual(A.map((g) => g.name), ['pelo']);
  assert.equal(B.length, 0);
  assert.equal(m.mod('grande', 'estado').hold, false);
  const v2 = crearVRMFalso();
  cargas.pop().alCargar({ scene: v2.scene, userData: { vrm: v2 } });
  // al salir de grande también se suelta
  const C = [];
  v2.springBoneManager.joints = [{ colliderGroups: C }];
  m.mod('grande', 'hold', true, 960, 540);
  assert.equal(C.length, 1);
  m.mod('grande', 'fase', 'fin');
  assert.equal(C.length, 0);
  // sin las clases de three-vrm no hace nada (y no rompe)
  const r2 = conGrande();
  r2.m.bus.quitar('grande');
  r2.m.registrar((ctx) => instalar(ctx, {}));
  r2.vrm.springBoneManager.joints = [{ colliderGroups: [] }];
  r2.m.mod('grande', 'fase', 'glide'); r2.m.mod('grande', 'fase', 'entrar'); correr(0.7);
  assert.equal(r2.m.mod('grande', 'hold', true, 1, 1), false);
  m.destruir(); r2.m.destruir();
});

test('ocupado solo en las transiciones', () => {
  const { m, mod } = conGrande();
  assert.equal(mod.ocupado(), false);
  m.mod('grande', 'fase', 'glide');
  assert.equal(mod.ocupado(), true);
  m.mod('grande', 'fase', 'entrar'); correr(0.7);
  assert.equal(mod.ocupado(), false, 'activa: puede bajar a fpsReposo');
  m.mod('grande', 'fase', 'fin');
  m.destruir();
});

// ── La página ─────────────────────────────────────────────────────────────────

test('companion_vrm.html: las funciones nuevas, lo pedido antes de cargar se repite y los módulos van al usarse', async () => {
  cargarClasico('lune_ritmo.js');
  cargarClasico('lune_alarma.js');
  cargarClasico('lune_pantalla.js');
  const body = crearElemento('body');
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(body);
  doc.body = body;
  globalThis.document = doc;
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=1' };
  const { html, scripts } = scriptsEnLinea('companion_vrm.html');
  assert.equal(scripts.length, 2);
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion_vrm.html' });
  // Python llama antes de que cargue el módulo
  for (const fn of ['luneGrande', 'luneHold', 'luneSalvapantallas', 'luneAlarma', 'luneBailar', 'lunePulso']) {
    assert.equal(typeof globalThis[fn], 'function', fn);
  }
  globalThis.luneGrande('glide', { ms: 400 });
  globalThis.luneBailar(true, { estilo: 'palmas', particulas: true });
  globalThis.lunePulso(128, 0.5, 0.9);
  assert.equal(globalThis.luneSalvapantallas(true, { fondo: true, reloj: false }), true, 'el DOM va ya');
  assert.equal(body.classList.contains('lune-salva-fondo'), true);
  globalThis.luneSalvapantallas(false);
  frames.length = 0;
  await import(aDataURL(reescribirImports(scripts[1].codigo, new URL('companion_vrm.html', UI), { './vrm/lune_vrm.js': DATA_MOTOR })));
  const asistente = globalThis.luneAsistente;
  try {
    assert.deepEqual(asistente.bus.lista(), ['idles', 'movimiento', 'baileProc', 'grande'], 'registrados al repetir lo pendiente');
    assert.equal(globalThis.__luneOcioPendiente, null);
    assert.equal(globalThis.luneMod('baileProc', 'estado').estilo, 'palmas');
    assert.equal(globalThis.luneMod('grande', 'estado').fase, 'glide');
    const vrm = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    correr(0.1);
    assert.equal(globalThis.luneMod('baileProc', 'estado').bpm, 128, 'el pulso pendiente llegó al reloj');
    assert.equal(globalThis.luneHold(true, 5, 5), false, 'three-vrm falso sin colisionador: no hace nada');
    // pantalla grande: clase en <body> mientras la ventana es la del monitor
    globalThis.luneGrande('entrar', { ms: 500 });
    assert.equal(body.classList.contains('lune-grande'), true);
    globalThis.luneGrande('fin');
    assert.equal(body.classList.contains('lune-grande'), false);
    // alarma: burbuja con el texto; null la quita
    globalThis.luneAlarma('Gimnasio', { retrasoMs: 0, cps: 1000 });
    const burbuja = doc.getElementById('lune-alarma');
    assert.ok(burbuja && burbuja.classList.contains('on'));
    globalThis.luneAlarma(null);
    assert.equal(burbuja.classList.contains('on'), false);
    globalThis.luneBailar(false);
    assert.equal(globalThis.luneMod('baileProc', 'estado').activo, false);
    const ev = vaciarCola().map((e) => e.t);
    assert.ok(ev.includes('grande_fase') && ev.includes('baile'), JSON.stringify(ev));
    assert.ok(html.includes("import('./vrm/lune_grande.js').catch("), 'módulo opcional');
  } finally {
    try { asistente.destruir(); } catch (_) { /* sigue */ }
  }
});
