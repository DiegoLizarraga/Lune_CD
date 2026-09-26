// tests/js/vrm_barra.test.mjs — avatar VRM de la barra lateral
// (ui_web/ui_kits/lune-desktop/vrm_barra.js). Sin navegador ni three: el motor
// (crearMascota) es falso y se inyecta con opts.crearMascota; ventana, canvas,
// requestAnimationFrame, ResizeObserver y WEBGL_lose_context también son falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  mapearCursor, urlConVersion, filtrarParams, vaciarEscena, liberarMascota, proyectarCabeza,
  crear, destruir, params, recargar, activos, LuneVRMBarra, RUTA_MODELO, RUTA_MOTOR, DEFECTOS,
} from '../../ui_web/ui_kits/lune-desktop/vrm_barra.js';

const URL_MODULO = new URL('../../ui_web/ui_kits/lune-desktop/vrm_barra.js', import.meta.url);
const cerca = (a, b, tol = 1e-9, msg = '') => assert.ok(Math.abs(a - b) <= tol, `${msg} ${a} ≉ ${b} (±${tol})`);
const microtareas = async (n = 3) => { for (let i = 0; i < n; i++) await Promise.resolve(); };

// ── Entorno falso ───────────────────────────────────────────────────────────────

function evento(tipo, props = {}) { return Object.assign(new Event(tipo), props); }

class LienzoFalso extends EventTarget {
  constructor(rect = { left: 20, top: 100, width: 200, height: 400 }) {
    super();
    this.rect = rect; this.style = {};
    this.escuchas = new Map();
  }
  getBoundingClientRect() {
    const r = this.rect;
    return { left: r.left, top: r.top, width: r.width, height: r.height, x: r.left, y: r.top, right: r.left + r.width, bottom: r.top + r.height };
  }
  getContext() { return null; }
  addEventListener(t, fn, o) { this.escuchas.set(t, (this.escuchas.get(t) || 0) + 1); super.addEventListener(t, fn, o); }
  removeEventListener(t, fn, o) { this.escuchas.set(t, (this.escuchas.get(t) || 0) - 1); super.removeEventListener(t, fn, o); }
}

class VentanaFalsa extends EventTarget {
  constructor() {
    super();
    this.innerWidth = 1200; this.innerHeight = 800;
    this.frames = new Map(); this.sig = 1;
    this.observadores = [];
    this.escuchas = new Map();
    const v = this;
    this.ResizeObserver = class {
      constructor(cb) { this.cb = cb; this.objetivos = []; this.desconectado = false; v.observadores.push(this); }
      observe(el) { this.objetivos.push(el); }
      disconnect() { this.desconectado = true; }
      disparar() { if (!this.desconectado) this.cb([]); }
    };
  }
  requestAnimationFrame(fn) { const id = this.sig++; this.frames.set(id, fn); return id; }
  cancelAnimationFrame(id) { this.frames.delete(id); }
  pasarFrame() { const fs = [...this.frames.values()]; this.frames.clear(); for (const f of fs) f(16); }
  addEventListener(t, fn, o) { this.escuchas.set(t, (this.escuchas.get(t) || 0) + 1); super.addEventListener(t, fn, o); }
  removeEventListener(t, fn, o) { this.escuchas.set(t, (this.escuchas.get(t) || 0) - 1); super.removeEventListener(t, fn, o); }
}

// Extensión WEBGL_lose_context falsa: la pérdida y la restauración se despachan a
// mano (como en Chromium, llegan DESPUÉS, en otra tarea).
function extFalsa(lienzo) {
  const ext = {
    perdido: false, lose: 0, restore: 0, restorePrematuro: 0, eventoDespachado: false,
    loseContext() { ext.lose++; ext.perdido = true; ext.eventoDespachado = false; },
    restoreContext() {
      ext.restore++;
      if (!ext.perdido || !ext.eventoDespachado) { ext.restorePrematuro++; return; }   // INVALID_OPERATION
      ext.pendienteRestaurar = true;
    },
    despacharPerdida() { ext.eventoDespachado = true; lienzo.dispatchEvent(new Event('webglcontextlost')); },
    despacharRestaurado() { ext.perdido = false; ext.pendienteRestaurar = false; lienzo.dispatchEvent(new Event('webglcontextrestored')); },
  };
  return ext;
}

// Motor falso con la API de lune_vrm.js que usa vrm_barra.js.
function motorFalso(lienzo, { conDestruir = false, conLuneParams = false, sobre = false, conBus = false } = {}) {
  const reg = { llamadas: [], creadas: 0, opciones: null, sobre, disposed: 0, perdidas: 0 };
  const ext = extFalsa(lienzo);
  const gl = { isContextLost: () => ext.perdido, getExtension: (n) => (n === 'WEBGL_lose_context' && !ext.perdido ? ext : null) };
  const camera = { fov: 24, actualizaciones: 0, updateProjectionMatrix() { this.actualizaciones++; } };
  const THREE = { Vector3: class { constructor() { this.x = 0; this.y = 0; this.z = 0; } } };
  const huesos = { head: { getWorldPosition: (v) => { v.x = 0; v.y = 1.4; v.z = 0; return v; } } };
  const PARAMS = { fov: 24, fpsActivo: 60, invertirEjes: 0, invertirH: 1, swayGanH: 0.012, gestoWatchdog: 0 };
  const log = (...a) => reg.llamadas.push(a);
  reg.ext = ext; reg.camera = camera; reg.PARAMS = PARAMS;
  reg.crearMascota = (o) => {
    reg.creadas++; reg.opciones = o;
    o.onEvento('cargando', o.src);                 // lune_vrm.js lo emite dentro de crearMascota
    const m = {
      setEstado: (e) => log('setEstado', e),
      setHablando: (on) => log('setHablando', on),
      setFPS: (n) => log('setFPS', n),
      cursor: (...a) => { log('cursor', ...a); return reg.sobre; },
      tocar: () => log('tocar'),
      encuadrar: (modo) => log('encuadrar', modo),
      cargar: (u) => log('cargar', u),
      PARAMS,
      bus: { llamar: (h) => log('bus', h) },
      ctx: {
        THREE, camera, huesos,
        renderer: { getContext: () => gl, dispose: () => { reg.disposed++; }, forceContextLoss: () => { reg.perdidas++; } },
        scene: { remove: () => log('scene.remove') },
        proyectar: (v) => ({ x: 120, y: 200 - (v.y - 1.4) * 100 }),
        vrm: () => null,
      },
    };
    if (conDestruir) m.destruir = () => log('destruir');
    if (conLuneParams) m.luneParams = (j) => { log('luneParams', j); return 'motor'; };
    if (conBus) {
      // Como lune_modulos.js: registrar(instalar) llama a instalar(ctx) y devuelve el módulo.
      m.registrar = (inst) => { const mod = typeof inst === 'function' ? inst(m.ctx) : inst; reg.ultimoModulo = mod; log('registrar', mod && mod.nombre); return mod; };
      m.mod = (nombre, metodo, ...args) => { log('mod', nombre, metodo, ...args); return `${nombre}.${metodo}`; };
    }
    reg.m = m;
    return m;
  };
  reg.de = (nombre) => reg.llamadas.filter((c) => c[0] === nombre);
  reg.ultima = (nombre) => { const l = reg.de(nombre); return l[l.length - 1]; };
  return reg;
}

function montar(opts = {}, motorOpts = {}) {
  const ventana = new VentanaFalsa();
  const lienzo = new LienzoFalso();
  const motor = motorFalso(lienzo, motorOpts);
  const errores = [], eventos = [];
  const diferidos = [];
  const h = crear(lienzo, opts.url === undefined ? RUTA_MODELO : opts.url, {
    ventana, crearMascota: motor.crearMascota,
    alError: (m) => errores.push(m), onEvento: (t, d) => eventos.push([t, d]),
    diferir: (fn) => diferidos.push(fn),
    ...opts,
  });
  const correrDiferidos = () => { while (diferidos.length) diferidos.shift()(); };
  return { ventana, lienzo, motor, h, errores, eventos, correrDiferidos };
}

// ── mapearCursor (lógica pura) ──────────────────────────────────────────────────

const RECT = { left: 20, top: 100, width: 200, height: 400 };
const VISTA = { ancho: 1200, alto: 800 };

test('mapearCursor: en la cara vale 0,0 y la escala es media ventana', () => {
  const cx = 20 + 100, cy = 100 + 400 * 0.35;
  const c = mapearCursor(cx, cy, RECT, VISTA);
  cerca(c.nx, 0); cerca(c.ny, 0);
  assert.equal(c.px, cx); assert.equal(c.py, cy);
  assert.equal(c.dentro, true);
  const d = mapearCursor(cx + 300, cy - 200, RECT, VISTA);
  cerca(d.nx, 300 / 600, 1e-12, 'nx a la derecha');
  cerca(d.ny, 200 / 400, 1e-12, 'ny positivo hacia arriba');
  const e = mapearCursor(cx - 60, cy + 40, RECT, VISTA);
  cerca(e.nx, -0.1); cerca(e.ny, -0.1);
});

test('mapearCursor: recorta a ±1.6 (o al tope) y respeta alcance y alturaCara', () => {
  const lejos = mapearCursor(5000, -5000, RECT, VISTA);
  assert.equal(lejos.nx, 1.6); assert.equal(lejos.ny, 1.6);
  const otro = mapearCursor(-5000, 5000, RECT, VISTA, { tope: 1 });
  assert.equal(otro.nx, -1); assert.equal(otro.ny, -1);
  const ancho = mapearCursor(120 + 600, 240, RECT, VISTA, { alcance: 2 });
  cerca(ancho.nx, 0.5);
  const alta = mapearCursor(120, 100, RECT, VISTA, { alturaCara: 0 });
  cerca(alta.ny, 0);
});

test('mapearCursor: centro explícito (cabeza proyectada) manda sobre el del rect', () => {
  const c = mapearCursor(300, 150, RECT, VISTA, { centro: { x: 300, y: 150 } });
  cerca(c.nx, 0); cerca(c.ny, 0);
  const malo = mapearCursor(120, 240, RECT, VISTA, { centro: { x: NaN, y: 'x' } });
  cerca(malo.nx, 0); cerca(malo.ny, 0);
});

test('mapearCursor: dentro solo sobre el canvas (bordes derecho e inferior excluidos)', () => {
  assert.equal(mapearCursor(20, 100, RECT, VISTA).dentro, true);
  assert.equal(mapearCursor(219.9, 499.9, RECT, VISTA).dentro, true);
  assert.equal(mapearCursor(220, 300, RECT, VISTA).dentro, false);
  assert.equal(mapearCursor(100, 500, RECT, VISTA).dentro, false);
  assert.equal(mapearCursor(19, 300, RECT, VISTA).dentro, false);
  assert.equal(mapearCursor(100, 300, { left: 0, top: 0, width: 0, height: 0 }, VISTA).dentro, false);
});

test('mapearCursor: entradas raras no rompen', () => {
  assert.equal(mapearCursor(NaN, 1, RECT, VISTA), null);
  assert.equal(mapearCursor(1, Infinity, RECT, VISTA), null);
  assert.equal(mapearCursor(1, 1, null, VISTA), null);
  const sinVista = mapearCursor(121, 240, RECT, null);          // semiejes de 1 px: satura
  assert.equal(sinVista.nx, 1);
  const domRect = mapearCursor(120, 240, { x: 20, y: 100, width: 200, height: 400 }, VISTA);
  cerca(domRect.nx, 0); cerca(domRect.ny, 0);
  for (const v of Object.values(mapearCursor(1e9, -1e9, RECT, { ancho: 0, alto: -5 }))) {
    if (typeof v === 'number') assert.ok(Number.isFinite(v));
  }
});

// ── urlConVersion ───────────────────────────────────────────────────────────────

test('urlConVersion añade o sustituye v= y conserva el ancla', () => {
  assert.equal(urlConVersion('/vrm/actual.vrm', 17), '/vrm/actual.vrm?v=17');
  assert.equal(urlConVersion('/vrm/actual.vrm?x=1', 17), '/vrm/actual.vrm?x=1&v=17');
  assert.equal(urlConVersion('/vrm/actual.vrm?v=3&x=1', 9), '/vrm/actual.vrm?v=9&x=1');
  assert.equal(urlConVersion('/a.vrm?x=1&v=3', 'a b'), '/a.vrm?x=1&v=a%20b');
  assert.equal(urlConVersion('/a.vrm#k', 2), '/a.vrm?v=2#k');
  assert.equal(urlConVersion('/a.vrm', null), '/a.vrm');
  assert.equal(urlConVersion('/a.vrm', ''), '/a.vrm');
  assert.equal(urlConVersion('', 5), '');
  assert.equal(urlConVersion('/a.vrm', 0), '/a.vrm?v=0');
});

// ── filtrarParams ───────────────────────────────────────────────────────────────

test('filtrarParams: lista blanca sobre PARAMS numéricos, JSON o objeto', () => {
  const P = { fov: 24, invertirEjes: 0, invertirH: 1, swayGanH: 0.012, nombre: 'x' };
  const r = filtrarParams(P, '{"fov": 30, "swayGanH": "0.02", "desconocida": 5, "nombre": 3, "__proto__": {"a": 1}}');
  assert.deepEqual(r.aplicados, { fov: 30, swayGanH: 0.02 });
  assert.deepEqual(r.ignorados.sort(), ['__proto__', 'desconocida', 'nombre'].sort());
  assert.equal(r.error, null);
  assert.equal(({}).a, undefined, 'sin contaminar el prototipo');
});

test('filtrarParams: invertir* a signo, negativos y no numéricos fuera, tope', () => {
  const P = { invertirEjes: 0, invertirH: 1, invertirV: 1, fov: 24, peloVelRef: 2000 };
  const r = filtrarParams(P, { invertirEjes: -7, invertirH: -0.3, invertirV: 0, fov: -1, peloVelRef: 1e12 });
  assert.deepEqual(r.aplicados, { invertirEjes: -1, invertirH: -1, peloVelRef: 100000 });
  assert.deepEqual(r.ignorados.sort(), ['fov', 'invertirV']);
  const s = filtrarParams(P, { fov: null, invertirEjes: true, peloVelRef: '' , invertirH: [1] });
  assert.deepEqual(s.aplicados, {});
  assert.equal(s.ignorados.length, 4);
});

test('filtrarParams: JSON roto o no-objeto devuelve error sin aplicar nada', () => {
  assert.equal(filtrarParams({ fov: 1 }, '{fov:').error, 'JSON no válido');
  assert.equal(filtrarParams({ fov: 1 }, '[1,2]').error, 'se esperaba un objeto');
  assert.equal(filtrarParams({ fov: 1 }, null).error, 'se esperaba un objeto');
  assert.deepEqual(filtrarParams({ fov: 1 }, 'null').aplicados, {});
});

// ── Liberar memoria sin three ───────────────────────────────────────────────────

function escenaFalsa() {
  const cont = { geo: 0, mat: 0, tex: 0, close: 0, esq: 0, del: 0 };
  const img = { close: () => { cont.close++; } };
  const tex = (i = img) => ({ isTexture: true, image: i, source: { data: i }, dispose: () => { cont.tex++; } });
  const t1 = tex(), t2 = tex({});
  const geo = () => ({
    attributes: { position: {}, normal: {} }, morphAttributes: { position: [{}] }, index: {},
    dispose: () => { cont.geo++; }, deleteAttribute(k) { delete this.attributes[k]; cont.del++; }, setIndex(i) { this.index = i; },
  });
  const matA = { map: t1, dispose: () => { cont.mat++; } };
  const matB = { uniforms: { map: { value: t1 }, shadeMultiplyTexture: { value: t2 }, color: { value: 3 } }, dispose: () => { cont.mat++; } };
  const g1 = geo(), g2 = geo();
  const hijos = [
    { geometry: g1, material: matA },
    { geometry: g1, material: [matA, matB], skeleton: { dispose: () => { cont.esq++; } } },
    { geometry: g2, material: matB },
    { nada: true },
  ];
  let quitado = false;
  const raiz = { traverse: (fn) => { fn(raiz); hijos.forEach(fn); }, removeFromParent: () => { quitado = true; } };
  return { raiz, cont, g1, t1, quitado: () => quitado };
}

test('vaciarEscena: cada recurso una vez, texturas de uniforms incluidas, arrays soltados', () => {
  const { raiz, cont, g1, t1, quitado } = escenaFalsa();
  const r = vaciarEscena(raiz);
  assert.deepEqual(r, { geometrias: 2, materiales: 2, texturas: 2 });
  assert.equal(cont.geo, 2); assert.equal(cont.mat, 2); assert.equal(cont.tex, 2);
  assert.equal(cont.close, 1, 'ImageBitmap cerrado una vez');
  assert.equal(cont.esq, 1);
  assert.deepEqual(g1.attributes, {}); assert.equal(g1.index, null); assert.deepEqual(g1.morphAttributes, {});
  assert.equal(t1.source.data, null);
  assert.ok(quitado());
  assert.deepEqual(vaciarEscena(null), { geometrias: 0, materiales: 0, texturas: 0 });
});

test('liberarMascota: FPS 0, alDescargar, fuera de escena, dispose y pérdida de contexto', () => {
  const { raiz, cont } = escenaFalsa();
  const log = [];
  const m = {
    setFPS: (n) => log.push(['fps', n]),
    bus: { llamar: (h) => log.push(['bus', h]) },
    ctx: {
      vrm: () => ({ scene: raiz }),
      scene: { remove: (s) => log.push(['remove', s === raiz]) },
      renderer: { dispose: () => log.push(['dispose']), forceContextLoss: () => { log.push(['perder']); throw new Error('ya perdido'); } },
    },
  };
  assert.equal(liberarMascota(m), true);
  assert.deepEqual(log, [['fps', 0], ['bus', 'alDescargar'], ['remove', true], ['dispose'], ['perder']]);
  assert.equal(cont.geo, 2);
  assert.equal(liberarMascota(null), false);
  assert.equal(liberarMascota({}), true, 'sin ctx no lanza');
});

test('liberarMascota: con m.destruir() usa solo eso, una vez; si lanza, el respaldo (sin repetir destruir)', () => {
  const log = [];
  const m = {
    destruir: () => log.push('destruir'),
    setFPS: () => log.push('fps'),
    bus: { llamar: (h) => log.push(h) },
    ctx: { vrm: () => ({ scene: { traverse() {} } }), scene: { remove: () => log.push('remove') },
      renderer: { dispose: () => log.push('dispose'), forceContextLoss: () => log.push('perder') } },
  };
  assert.equal(liberarMascota(m), true);
  assert.deepEqual(log, ['destruir'], 'nada del respaldo: el motor ya lo hace');
  log.length = 0;
  m.destruir = () => { log.push('destruir'); throw new Error('roto'); };
  const warn = console.warn;
  console.warn = () => {};
  try { assert.equal(liberarMascota(m), true); } finally { console.warn = warn; }
  assert.deepEqual(log, ['destruir', 'fps', 'alDescargar', 'remove', 'dispose', 'perder']);
});

test('proyectarCabeza: usa el hueso de la cabeza + altura de ojos; null sin cabeza', () => {
  const lienzo = new LienzoFalso();
  const motor = motorFalso(lienzo);
  const m = motor.crearMascota({ onEvento: () => {} });
  const p = proyectarCabeza(m);
  cerca(p.x, 120); cerca(p.y, 194, 1e-9, 'cabeza 1.4 m + 0.06 m → 200 - 6');
  assert.equal(proyectarCabeza({ ctx: { huesos: {} } }), null);
  assert.equal(proyectarCabeza(null), null);
  assert.equal(proyectarCabeza({ ctx: { ...m.ctx, proyectar: () => { throw new Error('x'); } } }), null);
});

// ── crear(): ciclo de vida con motor falso ──────────────────────────────────────

test('crear: el motor se crea en una microtarea con src versionado, encuadre y FPS de la barra', async () => {
  const { h, motor, lienzo } = montar({ version: 42, encuadre: 'cuerpo' });
  assert.equal(motor.creadas, 0, 'todavía no: espera al import');
  assert.equal(lienzo.style.width, '100%'); assert.equal(lienzo.style.height, '100%');
  await microtareas();
  assert.equal(motor.creadas, 1);
  assert.equal(motor.opciones.canvas, lienzo);
  assert.equal(motor.opciones.src, '/vrm/actual.vrm?v=42');
  assert.equal(motor.opciones.encuadre, 'cuerpo');
  assert.deepEqual(motor.ultima('setFPS'), ['setFPS', DEFECTOS.fps]);
  assert.equal(h.mascota, motor.m);
  assert.equal(h.listo, false);
  h.destruir();
});

test('setEstado/setHablando antes de "listo": se guardan y se aplican al cargar', async () => {
  const { h, motor } = montar();
  h.setEstado('Thinking'); h.setHablando(true);
  await microtareas();
  assert.equal(motor.de('setEstado').length, 0, 'sin modelo no se manda (el saludo lo pisaría)');
  assert.deepEqual(motor.ultima('setHablando'), ['setHablando', true]);
  motor.opciones.onEvento('listo', { nombre: 'x' });
  assert.equal(h.listo, true);
  assert.deepEqual(motor.ultima('setEstado'), ['setEstado', 'thinking']);
  h.setEstado('happy');
  assert.deepEqual(motor.ultima('setEstado'), ['setEstado', 'happy']);
  h.destruir();
});

test('al cargar con cara "normal" no se reenvía: el motor saluda (wave)', async () => {
  const { h, motor } = montar();
  await microtareas();
  motor.opciones.onEvento('listo', {});
  assert.equal(motor.de('setEstado').length, 0);
  h.destruir();
});

test('error del modelo antes de listo → alError y onEvento; alListo al cargar', async () => {
  const listos = [];
  const { h, motor, errores, eventos } = montar({ alListo: (m) => listos.push(m) });
  await microtareas();
  motor.opciones.onEvento('error', '404');
  assert.deepEqual(errores, ['404']);
  assert.ok(eventos.some(([t, d]) => t === 'error' && d === '404'));
  assert.ok(eventos.some(([t]) => t === 'cargando'), 'el evento síncrono de crearMascota también llega');
  motor.opciones.onEvento('listo', { v: 1 });
  assert.deepEqual(listos, [{ v: 1 }]);
  h.destruir();
});

test('mousemove de la página → cursor mapeado (un envío por frame) respecto a la cabeza', async () => {
  const { h, motor, ventana } = montar();
  await microtareas();
  ventana.dispatchEvent(evento('mousemove', { clientX: 500, clientY: 50 }));
  ventana.dispatchEvent(evento('mousemove', { clientX: 720, clientY: 60 }));
  const antes = motor.de('cursor').length;
  ventana.pasarFrame();
  assert.equal(motor.de('cursor').length, antes + 1, 'coalescido por requestAnimationFrame');
  // Sin modelo cargado: centro = rect (20 + 100, 100 + 0.35·400) = (120, 240)
  let [, nx, ny, px, py, dentro] = motor.ultima('cursor');
  cerca(nx, (720 - 120) / 600); cerca(ny, (240 - 60) / 400);
  assert.equal(px, 720); assert.equal(py, 60); assert.equal(dentro, false);
  // Con modelo: centro = cabeza proyectada (120, 194)
  motor.opciones.onEvento('listo', {});
  ventana.dispatchEvent(evento('mousemove', { clientX: 120, clientY: 194 }));
  ventana.pasarFrame();
  [, nx, ny, px, py, dentro] = motor.ultima('cursor');
  cerca(nx, 0); cerca(ny, 0); assert.equal(dentro, true);
  h.destruir();
});

test('fuera de la ventana se queda el último nx/ny con dentro=false', async () => {
  const { h, motor, ventana } = montar();
  await microtareas();
  ventana.dispatchEvent(evento('mousemove', { clientX: 150, clientY: 300 }));
  ventana.pasarFrame();
  const [, nx, ny] = motor.ultima('cursor');
  ventana.dispatchEvent(evento('mouseout', { relatedTarget: {} }));   // a otro elemento: no cuenta
  ventana.pasarFrame();
  assert.equal(motor.ultima('cursor')[5], true);
  ventana.dispatchEvent(evento('mouseout', { relatedTarget: null }));
  ventana.pasarFrame();
  assert.deepEqual(motor.ultima('cursor'), ['cursor', nx, ny, -1, -1, false]);
  ventana.dispatchEvent(evento('mousemove', { clientX: 150, clientY: 300 }));
  ventana.pasarFrame();
  assert.equal(motor.ultima('cursor')[5], true, 'al volver, se mapea otra vez');
  h.destruir();
});

test('clic en el canvas toca a Lune solo si el cursor está sobre el modelo', async () => {
  const { h, motor, lienzo } = montar();
  await microtareas();
  motor.opciones.onEvento('listo', {});
  h.cursor(120, 300);
  lienzo.dispatchEvent(new Event('click'));
  assert.equal(motor.de('tocar').length, 0, 'píxel transparente');
  motor.sobre = true;
  lienzo.dispatchEvent(new Event('click'));
  assert.equal(motor.de('tocar').length, 1);
  h.destruir();
  const h2 = montar({ clicToca: false }, { sobre: true });
  await microtareas();
  h2.motor.opciones.onEvento('listo', {});
  h2.h.cursor(120, 300);
  h2.lienzo.dispatchEvent(new Event('click'));
  assert.equal(h2.motor.de('tocar').length, 0);
  h2.h.destruir();
});

test('ResizeObserver del canvas → reencuadre en el siguiente frame', async () => {
  const { h, motor, ventana, lienzo } = montar({ encuadre: 'retrato' });
  await microtareas();
  const ro = ventana.observadores[0];
  assert.deepEqual(ro.objetivos, [lienzo]);
  ro.disparar(); ro.disparar();
  ventana.pasarFrame();
  assert.equal(motor.de('encuadrar').length, 1);
  assert.deepEqual(motor.ultima('encuadrar'), ['encuadrar', 'retrato']);
  assert.equal(h.encuadrar('cuerpo'), 'cuerpo');
  assert.deepEqual(motor.ultima('encuadrar'), ['encuadrar', 'cuerpo']);
  h.destruir();
  assert.equal(ro.desconectado, true);
});

test('pausar: FPS 0, suelta el contexto y lo restaura solo tras el evento de pérdida', async () => {
  const { h, motor, ventana, correrDiferidos, eventos } = montar({ fps: 24 });
  await microtareas();
  const ext = motor.ext;
  assert.equal(h.pausar(true), true);
  assert.deepEqual(motor.ultima('setFPS'), ['setFPS', 0]);
  assert.equal(ext.lose, 1);
  assert.equal(h.contexto, 'perdiendo');
  // Con la pausa, el ratón no llega al motor.
  const n = motor.de('cursor').length;
  ventana.dispatchEvent(evento('mousemove', { clientX: 10, clientY: 10 }));
  ventana.pasarFrame();
  assert.equal(motor.de('cursor').length, n);
  // Reanudar ANTES de que llegue 'webglcontextlost': no se puede restaurar aún.
  h.pausar(false);
  assert.deepEqual(motor.ultima('setFPS'), ['setFPS', 24]);
  assert.equal(ext.restore, 0);
  ext.despacharPerdida();
  assert.equal(ext.restore, 0, 'dentro del evento tampoco: three hace preventDefault ahí');
  correrDiferidos();
  assert.equal(ext.restore, 1);
  assert.equal(ext.restorePrematuro, 0);
  assert.equal(h.contexto, 'restaurando');
  ext.despacharRestaurado();
  correrDiferidos();
  assert.equal(h.contexto, 'vivo');
  assert.ok(eventos.some(([t, d]) => t === 'contexto' && d === 'perdido'));
  assert.ok(eventos.some(([t, d]) => t === 'contexto' && d === 'vivo'));
  h.destruir();
});

test('pausar otra vez mientras se restaura: vuelve a soltarlo al llegar el contexto', async () => {
  const { h, motor, correrDiferidos } = montar();
  await microtareas();
  const ext = motor.ext;
  h.pausar(true); ext.despacharPerdida(); correrDiferidos();
  h.pausar(false); assert.equal(ext.restore, 1);
  h.pausar(true);                                  // aún 'restaurando'
  assert.equal(ext.lose, 1);
  ext.despacharRestaurado(); correrDiferidos();
  assert.equal(ext.lose, 2, 'sigue en pausa: lo suelta otra vez');
  h.destruir();
});

test('pausar sin liberarAlPausar solo pone FPS 0', async () => {
  const { h, motor } = montar({ liberarAlPausar: false });
  await microtareas();
  h.pausar(true);
  assert.equal(motor.ext.lose, 0);
  assert.deepEqual(motor.ultima('setFPS'), ['setFPS', 0]);
  assert.equal(h.pausar(true), true, 'idempotente');
  h.destruir();
});

test('pausado desde el principio: no crea el motor hasta pausar(false)', async () => {
  const { h, motor } = montar({ pausado: true });
  await microtareas();
  assert.equal(motor.creadas, 0);
  h.pausar(false);
  await microtareas();
  assert.equal(motor.creadas, 1);
  h.destruir();
});

test('destruir antes del import: el canvas no se toca y se puede reutilizar', async () => {
  const { h, motor, lienzo, ventana } = montar();
  assert.equal(destruir(h), true);
  assert.equal(destruir(h), false, 'idempotente');
  await microtareas();
  assert.equal(motor.creadas, 0);
  assert.equal(ventana.escuchas.get('mousemove'), 0);
  const motor2 = motorFalso(lienzo);
  const errores = [];
  const h2 = crear(lienzo, RUTA_MODELO, { ventana, crearMascota: motor2.crearMascota, alError: (e) => errores.push(e) });
  await microtareas();
  assert.equal(motor2.creadas, 1, 'StrictMode de React: montar-desmontar-montar funciona');
  assert.deepEqual(errores, []);
  h2.destruir();
});

test('destruir con motor: quita listeners y usa m.destruir() si existe', async () => {
  const { h, motor, ventana, lienzo } = montar({}, { conDestruir: true });
  await microtareas();
  const n = activos();
  h.destruir();
  assert.equal(activos(), n - 1);
  assert.equal(motor.de('destruir').length, 1);
  assert.equal(motor.disposed, 0, 'no hace falta el respaldo');
  for (const t of ['mousemove', 'mouseout']) assert.equal(ventana.escuchas.get(t), 0, t);
  for (const t of ['click', 'webglcontextlost', 'webglcontextrestored']) assert.equal(lienzo.escuchas.get(t), 0, t);
  assert.equal(h.mascota, null);
  h.setEstado('happy'); h.setHablando(true); h.pausar(true);
  assert.equal(h.cargar('/otro.vrm'), false);
  assert.equal(h.luneParams({ fov: 3 }), null);
  assert.equal(motor.de('setEstado').length, 0, 'tras destruir no se llama al motor');
});

test('destruir sin m.destruir(): respaldo que libera renderer y contexto', async () => {
  const { h, motor } = montar();
  await microtareas();
  h.destruir();
  assert.equal(motor.disposed, 1);
  assert.equal(motor.perdidas, 1);
  assert.deepEqual(motor.ultima('setFPS'), ['setFPS', 0]);
});

test('un canvas con un avatar ya destruido no se reutiliza (su contexto no vuelve)', async () => {
  const { h, lienzo, ventana } = montar();
  await microtareas();
  h.destruir();
  const motor2 = motorFalso(lienzo);
  const errores = [];
  const h3 = crear(lienzo, RUTA_MODELO, { ventana, crearMascota: motor2.crearMascota, alError: (e) => errores.push(e) });
  await microtareas();
  assert.equal(motor2.creadas, 0);
  assert.equal(errores.length, 1, 'se avisa en crear() (síncrono)');
  assert.match(errores[0], /canvas/);
  h3.destruir();
  // Un <canvas> nuevo (lo que hace React al volver a montar) sí vale.
  const h4 = crear(new LienzoFalso(), RUTA_MODELO, { ventana, crearMascota: motor2.crearMascota, alError: (e) => errores.push(e) });
  await microtareas();
  assert.equal(motor2.creadas, 1);
  assert.equal(errores.length, 1);
  h4.destruir();
});

test('motor que no carga (importmap ausente) → alError con el motivo', async () => {
  const errores = [];
  const ventana = new VentanaFalsa();
  const h = crear(new LienzoFalso(), RUTA_MODELO, {
    ventana, cargarMotor: () => Promise.reject(new Error('Failed to resolve module specifier "three"')),
    alError: (e) => errores.push(e),
  });
  await microtareas(5);
  assert.equal(errores.length, 1);
  assert.match(errores[0], /visor 3D.*three/);
  h.destruir();
  const errores2 = [];
  const h2 = crear(new LienzoFalso(), RUTA_MODELO, { ventana, cargarMotor: () => ({}), alError: (e) => errores2.push(e) });
  await microtareas(5);
  assert.match(errores2[0], /crearMascota/);
  h2.destruir();
});

test('sin URL no arranca; cargar(url, v) lo arranca y luego cambia de modelo en el mismo contexto', async () => {
  const { h, motor } = montar({ url: '' });
  await microtareas();
  assert.equal(motor.creadas, 0);
  assert.equal(h.cargar(''), false);
  assert.equal(h.cargar('/vrm/actual.vrm', 5), true);
  await microtareas();
  assert.equal(motor.creadas, 1);
  assert.equal(motor.opciones.src, '/vrm/actual.vrm?v=5');
  motor.opciones.onEvento('listo', {});
  assert.equal(h.cargar('/vrm/actual.vrm', 6), true);
  assert.deepEqual(motor.ultima('cargar'), ['cargar', '/vrm/actual.vrm?v=6']);
  assert.equal(h.listo, false);
  assert.equal(recargar('/vrm/actual.vrm', 7), activos());
  assert.deepEqual(motor.ultima('cargar'), ['cargar', '/vrm/actual.vrm?v=7']);
  h.destruir();
});

// ── luneParams ──────────────────────────────────────────────────────────────────

test('luneParams: filtra, aplica sobre PARAMS y actualiza la cámara si cambia el fov', async () => {
  const { h, motor } = montar({ encuadre: 'cuerpo' });
  await microtareas();
  const r = h.luneParams('{"fov": 30, "swayGanH": 0.02, "raro": 1}');
  assert.deepEqual(r, { fov: 30, swayGanH: 0.02 });
  assert.equal(motor.PARAMS.fov, 30); assert.equal(motor.PARAMS.swayGanH, 0.02);
  assert.equal(motor.PARAMS.raro, undefined);
  assert.equal(motor.camera.fov, 30); assert.equal(motor.camera.actualizaciones, 1);
  assert.deepEqual(motor.ultima('encuadrar'), ['encuadrar', 'cuerpo']);
  h.luneParams({ fov: 30 });
  assert.equal(motor.camera.actualizaciones, 1, 'mismo fov: nada');
  h.destruir();
});

test('luneParams: cambiar invertirEjes recarga el modelo (los ejes se miden al cargar)', async () => {
  const { h, motor } = montar({ version: 3 });
  await microtareas();
  h.luneParams({ invertirEjes: -1 });
  assert.deepEqual(motor.ultima('cargar'), ['cargar', '/vrm/actual.vrm?v=3']);
  const n = motor.de('cargar').length;
  h.luneParams({ invertirEjes: -1 });
  assert.equal(motor.de('cargar').length, n, 'sin cambio no recarga');
  h.destruir();
});

test('luneParams: antes del motor queda pendiente; opts.params y validarParams', async () => {
  const { h, motor } = montar({ params: { swayGanV: 1 }, validarParams: (j) => ({ ...j, pesoCabeza: 0.5 }) });
  assert.deepEqual(h.luneParams({ fov: 20 }), { pendiente: true });
  await microtareas();
  assert.equal(motor.PARAMS.fov, 20);
  assert.equal(motor.PARAMS.swayGanV, 1);
  assert.equal(motor.PARAMS.pesoCabeza, 0.5, 'validarParams de fuera manda');
  h.destruir();
});

test('luneParams: si el motor trae luneParams, se delega en él', async () => {
  const { h, motor } = montar({}, { conLuneParams: true });
  await microtareas();
  assert.equal(h.luneParams('{"fov": 1}'), 'motor');
  assert.deepEqual(motor.ultima('luneParams'), ['luneParams', '{"fov": 1}']);
  assert.equal(motor.PARAMS.fov, 24);
  h.destruir();
});

test('params(json) global: a los vivos y a los que se crean después', async () => {
  const a = montar();
  await microtareas();
  params({ swayGanH: 0.05 });
  assert.equal(a.motor.PARAMS.swayGanH, 0.05);
  const b = montar();
  await microtareas();
  assert.equal(b.motor.PARAMS.swayGanH, 0.05);
  a.h.destruir(); b.h.destruir();
  params(null);
});

// ── Bus de módulos: registrar y mod (cortes 5/6: baile en la barra) ─────────────

const instalarBaile = (ctx, opciones) => ({ nombre: 'baileProc', orden: 40, ctxRecibido: ctx, opciones, api: {} });

test('registrar y mod antes del motor: se encolan y, al crearlo, primero los registros y luego las llamadas', async () => {
  const { h, motor } = montar({}, { conBus: true });
  assert.equal(h.registrar(instalarBaile), null, 'sin motor: pendiente');
  assert.equal(h.registrar(instalarBaile), null);
  assert.equal(h.mod('baileProc', 'bailar', true, { estilo: 'rebote' }), undefined);
  h.mod('baileProc', 'pulso', 124, 0.25, 0.8);
  assert.equal(motor.creadas, 0);
  await microtareas();
  assert.equal(motor.creadas, 1);
  const orden = motor.llamadas.filter((c) => c[0] === 'registrar' || c[0] === 'mod').map((c) => c.slice(0, 3));
  assert.deepEqual(orden, [['registrar', 'baileProc'], ['mod', 'baileProc', 'bailar'], ['mod', 'baileProc', 'pulso']],
    'el mismo instalador no se registra dos veces');
  assert.deepEqual(motor.ultima('mod'), ['mod', 'baileProc', 'pulso', 124, 0.25, 0.8]);
  assert.equal(motor.ultima('mod').length, 6);
  // Con motor: directo, y devuelve lo del bus
  const r = h.registrar(instalarBaile);
  assert.equal(r.nombre, 'baileProc');
  assert.equal(r.ctxRecibido, motor.m.ctx, 'instalar recibe el ctx del motor');
  assert.equal(h.mod('baileProc', 'estado'), 'baileProc.estado');
  h.destruir();
  assert.equal(h.mod('baileProc', 'estado'), undefined, 'destruido: nada');
  assert.equal(h.registrar(instalarBaile), null);
});

test('mod: la cola guarda solo las 32 últimas; un motor sin bus no rompe', async () => {
  const a = montar({}, { conBus: true });
  for (let i = 0; i < 40; i++) a.h.mod('baileProc', 'pulso', 100 + i, 0, 1);
  await microtareas();
  const pulsos = a.motor.de('mod').map((c) => c[3]);
  assert.equal(pulsos.length, 32);
  assert.deepEqual([pulsos[0], pulsos[31]], [108, 139]);
  a.h.destruir();
  const b = montar();                          // motor viejo: sin registrar ni mod
  b.h.registrar(instalarBaile);
  b.h.mod('baileProc', 'bailar', true);
  await microtareas();
  assert.equal(b.motor.creadas, 1);
  assert.equal(b.h.mod('baileProc', 'bailar', false), undefined);
  assert.equal(b.h.registrar(instalarBaile), null);
  assert.deepEqual(b.errores, []);
  b.h.destruir();
});

test('destruir antes del motor vacía las colas: no se registra nada', async () => {
  const { h, motor } = montar({}, { conBus: true });
  h.registrar(instalarBaile);
  h.mod('baileProc', 'bailar', true);
  h.destruir();
  await microtareas();
  assert.equal(motor.creadas, 0);
  assert.equal(motor.de('registrar').length + motor.de('mod').length, 0);
});

test('cargarModulo y usarModulo: import perezoso por nombre, en caché, una vez por avatar; un fallo se reintenta', async () => {
  const pedidas = [];
  let falla = true;
  const importar = async (ruta) => {
    pedidas.push(ruta);
    if (falla) throw new Error('404');
    return { instalar: instalarBaile };
  };
  assert.equal(await LuneVRMBarra.cargarModulo('noExiste', importar), null);
  assert.equal(LuneVRMBarra.RUTAS_MODULOS.baileProc, '../../vrm/lune_baile_proc.js');
  const { h, motor } = montar({}, { conBus: true });
  await microtareas();
  assert.equal(await h.usarModulo('baileProc', { importar }), false, 'el import falla');
  assert.equal(motor.de('registrar').length, 0);
  falla = false;
  assert.equal(await h.usarModulo('baileProc', { importar }), true, 'se reintenta');
  assert.equal(await h.usarModulo('baileProc', { importar }), true);
  assert.deepEqual(motor.de('registrar').map((c) => c[1]), ['baileProc'], 'registrado una sola vez');
  const registrado = motor.m.registrar((ctx) => ({ nombre: 'sonda', ctx }));
  assert.equal(registrado.ctx, motor.m.ctx);
  // La barra instala baileProc con {encuadrar: false} (OPCIONES_MODULOS); se puede pedir otra cosa
  assert.deepEqual(motor.m.registrar === undefined ? null : motor.ultimoModulo.nombre, 'sonda');
  const d = montar({}, { conBus: true });
  await microtareas();
  await d.h.usarModulo('baileProc', { importar });                  // en caché: instalarBaile
  assert.deepEqual(d.motor.ultimoModulo.opciones, { encuadrar: false });
  assert.equal(d.motor.ultimoModulo.ctxRecibido, d.motor.m.ctx);
  const e = montar({}, { conBus: true });
  await microtareas();
  await e.h.usarModulo('baileProc', { importar, opciones: { encuadrar: true, x: 1 } });
  assert.deepEqual(e.motor.ultimoModulo.opciones, { encuadrar: true, x: 1 });
  e.h.destruir();
  assert.deepEqual(LuneVRMBarra.OPCIONES_MODULOS.baileProc, { encuadrar: false });
  d.h.destruir();
  assert.deepEqual(pedidas, ['../../vrm/lune_baile_proc.js', '../../vrm/lune_baile_proc.js'], 'en caché tras cargar');
  // Otro avatar lo registra en SU motor sin volver a importarlo
  const b = montar({}, { conBus: true });
  await microtareas();
  assert.equal(await b.h.usarModulo('baileProc', { importar }), true);
  assert.equal(b.motor.de('registrar').length, 1);
  assert.equal(pedidas.length, 2);
  h.destruir(); b.h.destruir();
  assert.equal(await b.h.usarModulo('baileProc', { importar }), false, 'destruido: nada');
  // Destruido mientras se cargaba (aunque esté en caché, resuelve en una microtarea): no registra
  const c = montar({}, { conBus: true });
  await microtareas();
  const p = c.h.usarModulo('baileProc', { importar });
  c.h.destruir();
  assert.equal(await p, false);
  assert.equal(c.motor.de('registrar').length, 0);
  assert.equal(pedidas.length, 2, 'en caché: no vuelve a importar');
  // La ruta existe relativa al módulo cuando el agente de la mascota la haya creado
  const ruta = fileURLToPath(new URL(LuneVRMBarra.RUTAS_MODULOS.baileProc, URL_MODULO));
  assert.match(ruta.replace(/\\/g, '/'), /ui_web\/vrm\/lune_baile_proc\.js$/);
});

// ── Publicación y rutas ─────────────────────────────────────────────────────────

test('sin imports estáticos (three llega con import() perezoso) y rutas del importmap válidas', () => {
  const src = readFileSync(fileURLToPath(URL_MODULO), 'utf8');
  assert.equal(/^\s*import\s[^(]/m.test(src), false, 'no debe haber import estático');
  assert.ok(src.includes('import(RUTA_MOTOR)'));
  assert.ok(existsSync(fileURLToPath(new URL(RUTA_MOTOR, URL_MODULO))), 'lune_vrm.js existe relativo al módulo');
  for (const rel of ['../../vendor/three/three.module.min.js', '../../vendor/three/three-vrm.module.min.js',
    '../../vendor/three/loaders/GLTFLoader.js']) {
    assert.ok(existsSync(fileURLToPath(new URL(rel, URL_MODULO))), rel);
  }
});

test('se publica en window.LuneVRMBarra y avisa con el evento lune-vrm-barra', async () => {
  const previo = globalThis.window;
  const win = new EventTarget();
  let avisos = 0;
  win.addEventListener('lune-vrm-barra', () => { avisos++; });
  globalThis.window = win;
  try {
    const mod = await import(URL_MODULO.href + '?publicar=1');
    assert.equal(win.LuneVRMBarra, mod.LuneVRMBarra);
    assert.equal(typeof win.LuneVRMBarra.crear, 'function');
    assert.equal(typeof win.LuneVRMBarra.destruir, 'function');
    assert.equal(avisos, 1);
    assert.ok(Object.isFrozen(win.LuneVRMBarra));
  } finally {
    if (previo === undefined) delete globalThis.window; else globalThis.window = previo;
  }
  assert.equal(LuneVRMBarra.RUTA_MODELO, '/vrm/actual.vrm');
});
