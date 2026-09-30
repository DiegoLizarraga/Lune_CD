// tests/js/tema.test.mjs — tema de color en la página y ancla de la cabeza:
//   · ui_web/tema.js (script clásico, en un contexto vm con un <html> falso):
//     window.luneTema(mapa | JSON | null) con lista blanca y validación.
//   · window.luneCabeza(offsetY) de las dos páginas de la asistente:
//     companion.html (geometría del vídeo) ejecutando su <script> clásico en un vm,
//     y companion_vrm.html ejecutando su módulo con three.js DE VERDAD (ui_web/vendor)
//     y un motor falso que expone el ctx (huesos.head, camera, proyectar) de lune_vrm.js.
// La fórmula del color está solo en Python (nucleo/tema.py); tests/test_tema_css.py
// comprueba con Node que todo lo que genera Python pasa esta lista blanca.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import * as THREE from '../../ui_web/vendor/three/three.module.min.js';
import { crearElemento, crearDocumento } from './dom_falso.mjs';

const UI = new URL('../../ui_web/', import.meta.url);
const CODIGO_TEMA = readFileSync(new URL('tema.js', UI), 'utf8');
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

// ── tema.js ─────────────────────────────────────────────────────────────────────

function paginaTema({ conDocumento = true } = {}) {
  const props = new Map();
  const estilo = {
    setProperty: (k, v) => { props.set(k, v); },
    removeProperty: (k) => { props.delete(k); },
    getPropertyValue: (k) => (props.has(k) ? props.get(k) : ''),
  };
  const ctx = { console };
  if (conDocumento) ctx.document = { documentElement: { style: estilo } };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(CODIGO_TEMA, ctx, { filename: 'tema.js' });
  return { w: ctx, props };
}

const MAGENTA = {
  '--cyan-500': '#FE00FF', '--cyan-500-rgb': '254 0 255',
  '--blue-500': '#FF1E6C', '--blue-500-rgb': '255 30 108',
};

test('luneTema aplica en <html> las variables de la lista blanca y devuelve cuántas', () => {
  const { w, props } = paginaTema();
  assert.equal(typeof w.luneTema, 'function');
  assert.equal(w.luneTema(MAGENTA), 4);
  assert.equal(props.get('--cyan-500'), '#FE00FF');
  assert.equal(props.get('--cyan-500-rgb'), '254 0 255');
  assert.deepEqual([...w.luneTema.puestas()].sort(), Object.keys(MAGENTA).sort());
  // También como texto JSON (lo que manda Python con runJavaScript)
  assert.equal(w.luneTema(JSON.stringify({ '--ink-800': '#1A1026', '--ink-800-rgb': '26 16 38', '--yellow-500': '#0FF' })), 3);
  assert.equal(props.get('--ink-800'), '#1A1026');
  assert.equal(props.get('--yellow-500'), '#0FF');
});

test('luneTema ignora lo que no es un token del tema o no es un color válido', () => {
  const { w, props } = paginaTema();
  const n = w.luneTema({
    '--accent': '#FF0000',                   // alias semántico: no se toca (sale de --cyan-500)
    '--bg': '#000000',
    '--red-500': '#00FF00',                  // el rojo de error no es del tema
    'color': 'red',
    '--cyan-500': 'red',                     // nombre de color
    '--cyan-400': 'url(javascript:alert(1))',
    '--cyan-300': '#12345',                  // hex de 5
    '--blue-500-rgb': '300 0 0',             // canal fuera de rango
    '--blue-400-rgb': '1,2,3',               // con comas
    '--blue-300-rgb': '1 2 3; background: red',
    '--cyan-600': 123,                       // no es texto
    '__proto__': '#FFFFFF',
    '--cyan-700': ' #0091AB ',               // con espacios: se recortan y vale
  });
  assert.equal(n, 1);
  assert.deepEqual([...props.keys()], ['--cyan-700']);
  assert.equal(props.get('--cyan-700'), '#0091AB');
});

test('cada llamada quita lo de la anterior; null lo quita todo; JSON roto no toca nada', () => {
  const { w, props } = paginaTema();
  w.luneTema({ ...MAGENTA, '--yellow-500': '#00FFFF' });
  assert.equal(props.size, 5);
  w.luneTema({ '--cyan-500': '#7F00FF' });     // sin teñir el amarillo: el de antes se va
  assert.deepEqual([...props.keys()], ['--cyan-500']);
  assert.equal(w.luneTema('{roto'), -1);
  assert.deepEqual([...props.keys()], ['--cyan-500'], 'con JSON roto se queda como estaba');
  assert.equal(w.luneTema(null), 0);
  assert.equal(props.size, 0);
  w.luneTema(MAGENTA);
  assert.equal(w.luneTema('null'), 0);
  assert.equal(props.size, 0);
  assert.equal(w.luneTema([['--cyan-500', '#FFFFFF']]), 0, 'un array no es un mapa');
  assert.equal(props.size, 0);
});

test('como mucho 96 variables por llamada y sin documento no hace nada', () => {
  const { w, props } = paginaTema();
  const mucho = {};
  for (let i = 0; i < 300; i++) mucho[`--ink-${100 + i}`] = '#010203';
  assert.equal(w.luneTema(mucho), 96);
  assert.equal(props.size, 96);
  const sin = paginaTema({ conDocumento: false });
  assert.equal(sin.w.luneTema(MAGENTA), 0);
});

// ── luneCabeza en companion.html (vídeo) ───────────────────────────────────────

function scriptsEnLinea(pagina) {
  const html = readFileSync(new URL(pagina, UI), 'utf8');
  const res = [];
  for (const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (/\bsrc=/.test(m[1]) || /importmap/.test(m[1]) || !m[2].trim()) continue;
    res.push({ modulo: /type="module"/.test(m[1]), codigo: m[2] });
  }
  return res;
}

function paginaAnimada(rect, dims = { videoWidth: 720, videoHeight: 1280 }) {
  const raiz = crearElemento('body');
  const bub = raiz.appendChild(crearElemento('div', 'bubble'));
  bub.appendChild(crearElemento('span', 'btxt'));
  const stage = raiz.appendChild(crearElemento('div', 'stage'));
  const v = stage.appendChild(crearElemento('video', 'v'));
  if (rect) v.getBoundingClientRect = () => rect;
  Object.assign(v, dims);
  const ctx = { console, document: crearDocumento(raiz), Promise };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(scriptsEnLinea('companion.html')[0].codigo, ctx, { filename: 'companion.html' });
  return ctx;
}

test('companion.html: luneCabeza sale de la geometría del vídeo (contain, pegado abajo)', () => {
  // #stage de 210×290 con el vídeo al 97 %: 210×281.3 → contain de 720×1280 → 158.2×281.3
  const rect = { left: 12, top: 20, width: 210, height: 281.3 };
  const w = paginaAnimada(rect);
  assert.equal(typeof w.luneCabeza, 'function');
  assert.equal(typeof w.luneTema, 'function', 'respaldo mudo si tema.js no cargó');
  assert.equal(w.luneTema({ '--cyan-500': '#FFFFFF' }), 0);
  const s = Math.min(210 / 720, 281.3 / 1280), cw = 720 * s, ch = 1280 * s;
  const izq = 12 + (210 - cw) / 2, arriba = 20 + (281.3 - ch);
  const c = JSON.parse(w.luneCabeza());                 // offsetY = 0.1 por defecto
  cerca(c.x, izq + 0.505 * cw, 0.06, 'x centrada en la cara');
  cerca(c.y, arriba + (0.36 - 0.1 * 1.29) * ch, 0.06, 'y a la altura de la frente');
  cerca(c.r, 0.1732 * 1.29 * ch, 0.06, 'radio de la asistente 3D');
  // Más offset = más arriba; offset inválido = el de por defecto
  assert.ok(JSON.parse(w.luneCabeza(0.2)).y < c.y);
  assert.deepEqual(JSON.parse(w.luneCabeza('no')), c);
  // La cabeza cae dentro del vídeo
  assert.ok(c.x > izq && c.x < izq + cw && c.y > arriba && c.y < arriba + ch * 0.5);
});

test('companion.html: sin tamaño todavía, o sin vídeo, luneCabeza dice "null"', () => {
  assert.equal(paginaAnimada({ left: 0, top: 0, width: 0, height: 0 }).luneCabeza(), 'null');
  const sinVideo = paginaAnimada(null);
  sinVideo.document.getElementById('v').getBoundingClientRect = undefined;
  assert.equal(sinVideo.luneCabeza(), 'null');
  // videoWidth aún en 0 (no ha cargado): se asume 720×1280
  const r = { left: 0, top: 0, width: 210, height: 281.3 };
  assert.deepEqual(JSON.parse(paginaAnimada(r, { videoWidth: 0, videoHeight: 0 }).luneCabeza()),
    JSON.parse(paginaAnimada(r).luneCabeza()));
});

// ── luneCabeza en companion_vrm.html (hueso de la cabeza) ───────────────────────

const LIENZO = { left: 0, top: 0, width: 240, height: 320 };

/** Escena mínima como la de lune_vrm.js: cámara, raíz del modelo y hueso head. */
function escena({ inclinacion = 0, escala = 1 } = {}) {
  const camera = new THREE.PerspectiveCamera(30, LIENZO.width / LIENZO.height, 0.05, 30);
  camera.position.set(0.05, 1.3, 1.6);
  camera.lookAt(0, 1.25, 0);
  camera.updateMatrixWorld(true);
  const raiz = new THREE.Object3D();
  raiz.scale.setScalar(escala);
  const cuello = new THREE.Object3D();
  cuello.position.set(0, 1.3, 0);
  const head = new THREE.Object3D();
  head.position.set(0, 0.06, 0);
  head.rotation.z = inclinacion;
  raiz.add(cuello); cuello.add(head);
  raiz.updateMatrixWorld(true);
  const proyectar = (p) => {                       // = proyectar() de lune_vrm.js
    const v = p.clone().project(camera);
    return { x: LIENZO.left + (v.x + 1) / 2 * LIENZO.width, y: LIENZO.top + (1 - v.y) / 2 * LIENZO.height };
  };
  return { camera, head, proyectar };
}

let paginaVRM = null;
async function cargarPaginaVRM() {
  if (paginaVRM) return paginaVRM;
  const raiz = crearElemento('body');
  const stage = raiz.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(crearElemento('canvas', 'c'));
  stage.appendChild(crearElemento('div', 'zzz'));
  stage.appendChild(crearElemento('div', 'aviso'));
  globalThis.window = globalThis;
  globalThis.document = crearDocumento(raiz);
  globalThis.location = { search: '' };
  if (typeof globalThis.addEventListener !== 'function') globalThis.addEventListener = () => {};
  const estado = { asistente: null };
  globalThis.__motorFalsoTema = (opts) => {
    estado.opts = opts;
    const m = { listo: false, ctx: null, luneParams: () => null, setEstado() {}, setHablando() {} };
    estado.asistente = m;
    return m;
  };
  const motor = 'data:text/javascript;base64,' + Buffer.from(
    'export function crearAsistente(o) { return globalThis.__motorFalsoTema(o); }', 'utf8').toString('base64');
  const scripts = scriptsEnLinea('companion_vrm.html');
  for (const s of scripts) {
    if (!s.modulo) { vm.runInThisContext(s.codigo, { filename: 'companion_vrm.html' }); continue; }
    const codigo = s.codigo.replace(/from\s+'\.\/vrm\/lune_vrm\.js'/, `from '${motor}'`);
    await import('data:text/javascript;base64,' + Buffer.from(codigo, 'utf8').toString('base64'));
  }
  paginaVRM = estado;
  return estado;
}

/** Lo que tiene que salir, calculado a mano: offset girado con el hueso y proyectado. */
function esperado({ camera, head, proyectar }, oy) {
  const pos = head.getWorldPosition(new THREE.Vector3());
  const q = head.getWorldQuaternion(new THREE.Quaternion());
  const esc = head.getWorldScale(new THREE.Vector3());
  const centro = pos.clone().add(new THREE.Vector3(0, oy * esc.y, 0).applyQuaternion(q));
  const derecha = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.getWorldQuaternion(new THREE.Quaternion()));
  const c = proyectar(centro);
  const b = proyectar(centro.clone().addScaledVector(derecha, 0.1 * esc.length()));
  return { x: c.x, y: c.y, r: Math.hypot(b.x - c.x, b.y - c.y) };
}

test('companion_vrm.html: luneCabeza proyecta el hueso Head + (0, offsetY, 0) en su espacio local', async () => {
  const pagina = await cargarPaginaVRM();
  assert.equal(typeof globalThis.luneCabeza, 'function');
  assert.equal(typeof globalThis.luneTema, 'function', 'respaldo mudo si tema.js no cargó');
  // Sin modelo cargado todavía
  assert.equal(globalThis.luneCabeza(), 'null');
  const esc = escena();
  pagina.asistente.ctx = { THREE, huesos: { head: esc.head }, camera: esc.camera, proyectar: esc.proyectar };
  assert.equal(globalThis.luneCabeza(), 'null', 'hasta que el motor está listo');
  pagina.asistente.listo = true;
  const c = JSON.parse(globalThis.luneCabeza());
  const e = esperado(esc, 0.1);
  cerca(c.x, e.x, 0.06, 'x'); cerca(c.y, e.y, 0.06, 'y'); cerca(c.r, e.r, 0.06, 'r');
  assert.ok(c.r > 5 && c.r < 200, `radio razonable: ${c.r}`);
  // offsetY: 0 = el hueso; más offset, más arriba en pantalla
  const e0 = esperado(esc, 0);
  const c0 = JSON.parse(globalThis.luneCabeza(0));
  cerca(c0.y, e0.y, 0.06, 'offset 0');
  assert.ok(c.y < c0.y);
  assert.deepEqual(JSON.parse(globalThis.luneCabeza('x')), c, 'offset inválido = 0.1');
});

test('companion_vrm.html: luneCabeza sigue la inclinación de la cabeza y la escala del modelo', async () => {
  const pagina = await cargarPaginaVRM();
  pagina.asistente.listo = true;
  const inclinada = escena({ inclinacion: 0.5 });
  pagina.asistente.ctx = { THREE, huesos: { head: inclinada.head }, camera: inclinada.camera, proyectar: inclinada.proyectar };
  const c = JSON.parse(globalThis.luneCabeza());
  const e = esperado(inclinada, 0.1);
  cerca(c.x, e.x, 0.06, 'x inclinada'); cerca(c.y, e.y, 0.06, 'y inclinada');
  const recta = esperado(escena(), 0.1);
  assert.ok(c.x < recta.x - 1, 'girada en z positivo, el offset se va a la izquierda');
  // El doble de grande: el radio escala con |escala del hueso|
  const grande = escena({ escala: 2 });
  pagina.asistente.ctx = { THREE, huesos: { head: grande.head }, camera: grande.camera, proyectar: grande.proyectar };
  const g = JSON.parse(globalThis.luneCabeza());
  cerca(g.r, esperado(grande, 0.1).r, 0.06, 'r con escala 2');
  // Sin hueso de cabeza o con una proyección rota: "null", nunca una excepción
  pagina.asistente.ctx = { THREE, huesos: {}, camera: grande.camera, proyectar: grande.proyectar };
  assert.equal(globalThis.luneCabeza(), 'null');
  pagina.asistente.ctx = { THREE, huesos: { head: grande.head }, camera: grande.camera, proyectar: () => ({ x: NaN, y: 0 }) };
  assert.equal(globalThis.luneCabeza(), 'null');
  pagina.asistente.ctx = { THREE, huesos: { head: grande.head }, camera: grande.camera, proyectar: () => { throw new Error('x'); } };
  assert.equal(globalThis.luneCabeza(), 'null');
});
