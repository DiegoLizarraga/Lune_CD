// tests/js/pagina_mmd.test.mjs — window.luneMMD en las páginas de la asistente (corte 9):
// · companion_vrm.html: antes del módulo se guarda el último «cargar» y sus banderas
//   (__luneOcioPendiente.mmd) y se repiten; lune_mmd.js + lune_vmd.js + three-vrm-animation +
//   GLTFLoader se importan (tolerantes) y se registran UNA vez al pedir el primer baile; el
//   «cargar» va sin autoplay y la página lo pone a sonar al acabar si nadie pidió pausa;
//   seguir con el baile listo = reproducir; «estado» en JSON; si el reproductor no carga →
//   evento 'mmd' error con el id. Con el lune_mmd.js DE VERDAD: una ruta de fuera → error.
// · companion.html (D1): lo mismo con anim/lune_anim_mmd.js: la canción en la página y
//   luneBailar/lunePulso de la propia página al pulso de la canción (≤ 2 Hz).
// Motor VRM con three falso (motor_vrm_falso.mjs); <audio> falso.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import {
  scriptsEnLinea, reescribirImports, aDataURL, DATA_MOTOR, UI, frames, lienzoFalso, vaciarCola, cargarClasico,
} from './motor_vrm_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import { GLTFLoader as GLTFFalso } from './three_falso.mjs';
import { URL_THREE } from './vmd_fabrica.mjs';

const ORIGEN = 'http://127.0.0.1:8765';
const ID = '0123456789ab';
const tics = async (n = 5) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };
cargarClasico('lune_mmd_audio.js');
const AUDIO_REAL = globalThis.LuneMMDAudio;

// lune_mmd.js falso: apunta las órdenes que le llegan por api.orden; «cargar» espera a resolver().
const MMD_FALSO = aDataURL(`
export const NOMBRE = 'mmd';
export function instalar(ctx, op) {
  const f = globalThis.__mmdFalso = globalThis.__mmdFalso || { instalaciones: 0, ordenes: [], fase: 'parado', pendientes: [] };
  f.instalaciones += 1; f.op = op; f.ctx = ctx;
  return { nombre: 'mmd', orden: 60, api: {
    orden(o, d) {
      f.ordenes.push([o, d === undefined ? null : JSON.parse(JSON.stringify(d))]);
      if (o === 'cargar') { f.fase = 'cargando'; return new Promise((r) => f.pendientes.push((ok) => { f.fase = ok ? 'listo' : 'error'; r(ok); })); }
      if (o === 'reproducir') { f.fase = 'sonando'; return true; }
      if (o === 'pausa') { if (d && d.on && f.fase === 'sonando') f.fase = 'pausado'; else if (d && !d.on && f.fase === 'pausado') f.fase = 'sonando'; return true; }
      if (o === 'parar') { f.fase = 'parado'; return true; }
      return true;
    },
    estado() { return { fase: f.fase, id: 'falso' }; },
  } };
}
`);
const VRMA_FALSO = aDataURL(`
export class VRMAnimation {}
export class VRMAnimationLoaderPlugin {}
export class VRMLookAtQuaternionProxy {}
export function createVRMAnimationClip() { return { tracks: [] }; }
`);
const MMD_ROTO = aDataURL('throw new Error("sin reproductor");\nexport const x = 1;');
// El lune_mmd.js DE VERDAD con el three del vendor (el motor de estos tests usa un three falso).
const MMD_REAL = aDataURL(`
import * as real from '${new URL('vrm/lune_mmd.js', UI).href}';
import * as THREE from '${URL_THREE}';
export function instalar(ctx, op) { return real.instalar(ctx, { ...op, THREE }); }
`);

function domVRM() {
  const body = crearElemento('body');
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(body);
  doc.body = body;
  globalThis.document = doc;
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=1', origin: ORIGEN };
}

async function paginaVRM(extra, sufijo) {
  domVRM();
  globalThis.LuneMMDAudio = AUDIO_REAL;
  const { html, scripts } = scriptsEnLinea('companion_vrm.html');
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion_vrm.html' });
  frames.length = 0;
  const pagina = new URL('companion_vrm.html', UI);
  return { html, cargarModulo: () => import(aDataURL(reescribirImports(scripts[1].codigo, pagina, { './vrm/lune_vrm.js': DATA_MOTOR, ...extra }) + sufijo)) };
}

const cargaVMD = (extra = {}) => ({
  id: ID, tipo: 'vmd', motion: ['/bailes/Alfa/baile.vmd'], cara: [], audio: '/bailes/Alfa/cancion.mp3', offsetMs: 0,
  enSitio: true, brazoGrados: 35, volumen: 0.25, bucle: false, autoplay: true, titulo: 'Alfa', ...extra,
});

test('companion_vrm.html: luneMMD antes del módulo guarda el último cargar y sus banderas; se importa y registra una vez; autoplay y pausa los decide la página', async () => {
  const { html, cargarModulo } = await paginaVRM({ './vrm/lune_mmd.js': MMD_FALSO, '@pixiv/three-vrm-animation': VRMA_FALSO }, '\n// mmd-1');
  for (const ruta of ["'./vrm/lune_mmd.js'", "'./vrm/lune_vmd.js'", "'@pixiv/three-vrm-animation'", "'three/addons/loaders/GLTFLoader.js'"]) {
    assert.ok(html.includes(`import(${ruta}).catch(`), `${ruta}: import() tolerante`);
  }
  // Antes del módulo: pendiente
  assert.equal(globalThis.luneMMD('volumen', { volumen: 0.9 }), true);
  assert.equal(globalThis.luneMMD('cargar', cargaVMD({ id: 'aaaaaaaaaaaa' })), true);
  assert.equal(globalThis.luneMMD('cargar', cargaVMD()), true, 'el último cargar manda');
  assert.equal(globalThis.luneMMD('pausa', { on: true }), true);
  assert.equal(globalThis.luneMMD('pausa', { on: true }), true, 'una sola vez cada bandera');
  assert.equal(globalThis.luneMMD('inventada', {}), false);
  assert.deepEqual(JSON.parse(globalThis.luneMMD('estado')), { fase: 'cargando', pendiente: true });
  assert.deepEqual(globalThis.__luneOcioPendiente.mmd.banderas, [['pausa', { on: true }]], 'lo de antes del cargar se olvida');
  await cargarModulo();
  const asistente = globalThis.luneAsistente;
  try {
    await tics();
    const f = globalThis.__mmdFalso;
    assert.equal(globalThis.__luneOcioPendiente, null);
    assert.equal(f.instalaciones, 1);
    assert.ok(asistente.bus.lista().includes('mmd'), 'registrado en el bus del avatar');
    assert.equal(f.op.GLTFLoader, GLTFFalso, 'el GLTFLoader del importmap');
    assert.equal(typeof f.op.vmd.parsearVMD, 'function', 'lune_vmd.js');
    assert.equal(typeof f.op.VRMAnimation, 'function');
    assert.equal(typeof f.op.createVRMAnimationClip, 'function');
    assert.equal(f.op.audio, AUDIO_REAL, 'LuneMMDAudio de lune_mmd_audio.js');
    assert.deepEqual(f.ordenes, [['cargar', { ...cargaVMD(), autoplay: false }], ['pausa', { on: true }]],
      'el cargar sin autoplay y luego la pausa pendiente');
    f.pendientes.shift()(true);
    await tics();
    assert.equal(f.ordenes.length, 2, 'con pausa pedida no se pone a sonar');
    assert.equal(JSON.parse(globalThis.luneMMD('estado')).quiereSonar, false);
    assert.equal(globalThis.luneMMD('pausa', JSON.stringify({ on: false })), true);
    assert.deepEqual(f.ordenes.at(-1), ['reproducir', null], 'seguir con el baile listo = reproducir');
    // Otro baile: sin volver a registrar; suena al acabar de cargar
    assert.equal(globalThis.luneMMD('cargar', JSON.stringify(cargaVMD({ id: 'bbbbbbbbbbbb' }))), true);
    f.pendientes.shift()(true);
    await tics();
    assert.deepEqual(f.ordenes.slice(-2), [['cargar', { ...cargaVMD({ id: 'bbbbbbbbbbbb' }), autoplay: false }], ['reproducir', null]]);
    assert.equal(f.instalaciones, 1, 'una sola vez');
    // Un cargar que se para antes de acabar no se pone a sonar después
    globalThis.luneMMD('cargar', cargaVMD({ id: 'cccccccccccc' }));
    assert.equal(globalThis.luneMMD('parar', null), true);
    f.pendientes.shift()(true);
    await tics();
    assert.deepEqual(f.ordenes.slice(-2).map((o) => o[0]), ['cargar', 'parar']);
    // Banderas tal cual al api.orden del módulo
    globalThis.luneMMD('volumen', { volumen: 0.3 });
    globalThis.luneMMD('offset', { offsetMs: -120 });
    globalThis.luneMMD('en_sitio', { enSitio: false });
    globalThis.luneMMD('bucle', { bucle: true });
    assert.deepEqual(f.ordenes.slice(-4), [['volumen', { volumen: 0.3 }], ['offset', { offsetMs: -120 }],
      ['en_sitio', { enSitio: false }], ['bucle', { bucle: true }]]);
    const e = JSON.parse(globalThis.luneMMD('estado'));
    assert.equal(e.id, 'falso', 'el estado del módulo');
    assert.equal(e.quiereSonar, false, 'parado: nada que poner a sonar');
  } finally {
    try { asistente.destruir(); } catch (_) { /* sigue */ }
    delete globalThis.__mmdFalso;
  }
});

test('companion_vrm.html: si el reproductor no carga, el cargar acaba en un evento «mmd» error con su id', async () => {
  const { cargarModulo } = await paginaVRM({ './vrm/lune_mmd.js': MMD_ROTO, '@pixiv/three-vrm-animation': VRMA_FALSO }, '\n// mmd-2');
  await cargarModulo();
  const asistente = globalThis.luneAsistente;
  try {
    vaciarCola();
    assert.equal(globalThis.luneMMD('cargar', cargaVMD()), true);
    await tics();
    const ev = vaciarCola().filter((e) => e.t === 'mmd');
    assert.equal(ev.length, 1);
    assert.equal(ev[0].d.fase, 'error');
    assert.equal(ev[0].d.id, ID);
    assert.equal(asistente.bus.lista().includes('mmd'), false);
    assert.deepEqual(JSON.parse(globalThis.luneMMD('estado')), { fase: 'parado', pendiente: true });
  } finally {
    try { asistente.destruir(); } catch (_) { /* sigue */ }
  }
});

test('companion_vrm.html con el lune_mmd.js DE VERDAD: una ruta de fuera → evento «mmd» error y estado en JSON', async () => {
  const { cargarModulo } = await paginaVRM({ './vrm/lune_mmd.js': MMD_REAL, '@pixiv/three-vrm-animation': VRMA_FALSO }, '\n// mmd-3');
  await cargarModulo();
  const asistente = globalThis.luneAsistente;
  try {
    vaciarCola();
    assert.equal(globalThis.luneMMD('cargar', cargaVMD({ motion: ['http://evil.com/bailes/x.vmd'] })), true);
    await tics(10);
    assert.ok(asistente.bus.lista().includes('mmd'));
    const ev = vaciarCola().filter((e) => e.t === 'mmd');
    assert.ok(ev.some((e) => e.d.fase === 'error'), JSON.stringify(ev));
    const e = JSON.parse(globalThis.luneMMD('estado'));
    assert.equal(e.fase, 'error');
    assert.equal(e.quiereSonar, true);
    assert.equal(globalThis.luneMMD('parar'), false, 'nada que parar');
  } finally {
    try { asistente.destruir(); } catch (_) { /* sigue */ }
  }
});

// ── La animada (D1) ─────────────────────────────────────────────────────────────
function audioFalso(duracion = 30) {
  const oyentes = {};
  let src = '';
  const el = {
    currentTime: 0, duration: NaN, paused: true, ended: false, volume: 1, error: null,
    get src() { return src; },
    set src(v) { src = String(v); if (src) queueMicrotask(() => { el.duration = duracion; for (const f of [...(oyentes.loadedmetadata || [])]) f({}); }); },
    addEventListener(t, f) { (oyentes[t] || (oyentes[t] = new Set())).add(f); },
    removeEventListener(t, f) { if (oyentes[t]) oyentes[t].delete(f); },
    play() { el.paused = false; return Promise.resolve(); },
    pause() { el.paused = true; },
    load() {},
    removeAttribute(k) { if (k === 'src') src = ''; },
  };
  return el;
}

test('companion.html: luneMMD tipo «audio» → canción en la página y luneBailar/lunePulso al pulso (≤ 2 Hz); pausa y parar', async () => {
  globalThis.window = globalThis;
  globalThis.requestAnimationFrame = () => 0;
  globalThis.cancelAnimationFrame = () => {};
  globalThis.location = { search: '', origin: ORIGEN };
  const body = crearElemento('body');
  body.appendChild(crearElemento('div', 'bubble')).appendChild(crearElemento('span', 'btxt'));
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(crearElemento('video', 'v'));
  const doc = crearDocumento(body);
  doc.body = body;
  stage.ownerDocument = doc;
  globalThis.document = doc;
  const audios = [];
  globalThis.LuneMMDAudio = { ...AUDIO_REAL, crear: (o) => AUDIO_REAL.crear({ ...o, crearAudio: () => { const a = audioFalso(); audios.push(a); return a; } }) };
  const html = readFileSync(new URL('companion.html', UI), 'utf8');
  assert.ok(html.includes("import('./anim/lune_anim_mmd.js').catch("), 'módulo opcional');
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter((m) => !/\bsrc=/.test(m[1]) && m[2].trim()).map((m) => m[2]);
  assert.equal(scripts.length, 2, 'la animada sigue con dos scripts en línea');
  vm.runInThisContext(scripts[0], { filename: 'companion.html' });
  const carga = { id: ID, tipo: 'audio', audio: '/bailes/Alfa/cancion.mp3', bpm: 120, fase0: 0.5, offsetMs: 0,
    volumen: 0.25, bucle: false, autoplay: true, titulo: 'Alfa' };
  assert.equal(globalThis.luneMMD('cargar', carga), true, 'pendiente');
  assert.deepEqual(JSON.parse(globalThis.luneMMD('estado')), { fase: 'cargando', pendiente: true });
  const base = new URL('companion.html', UI);
  const codigo = scripts[1].replace(/from\s+'(\.[^']+)'/g, (m, esp) => `from '${new URL(esp, base).href}'`)
    .replace(/import\(\s*'(\.[^']+)'\s*\)/g, (m, esp) => `import('${new URL(esp, base).href}')`);
  await import(aDataURL(codigo + '\n// mmd-animada'));
  const reg = globalThis.luneAnim;
  const pulsos = [];
  const pulsoPagina = globalThis.lunePulso;
  globalThis.lunePulso = (b, f, e) => { pulsos.push({ b, f, e, t: audios[0] ? audios[0].currentTime : 0 }); return pulsoPagina(b, f, e); };
  try {
    await tics();
    assert.ok(reg.lista().includes('mmdAnim'), 'se registró con el cargar pendiente');
    assert.ok(reg.lista().includes('baileAnim'), 'luneBailar(true) de la página');
    assert.equal(audios.length, 1);
    assert.equal(audios[0].src, `${ORIGEN}/bailes/Alfa/cancion.mp3`);
    assert.equal(audios[0].paused, false);
    let ms = 1000;
    for (let i = 0; i < 180; i++) {               // 3 s a 60 Hz
      ms += 1000 / 60;
      audios[0].currentTime += 1 / 60;
      reg.paso(ms);
    }
    assert.ok(pulsos.length >= 5 && pulsos.length <= 7, `≈2 Hz (${pulsos.length})`);
    for (const p of pulsos) {
      assert.equal(p.b, 120);
      assert.ok(Math.abs(p.f - AUDIO_REAL.pulsoEn(p.t, { bpm: 120, fase0: 0.5 }).fase) < 1e-6, 'fase de pulsoEn');
    }
    assert.equal(reg.api('baileAnim', 'estado').activo, true);
    assert.equal(globalThis.luneMMD('pausa', { on: true }), true);
    assert.equal(audios[0].paused, true);
    assert.equal(reg.api('baileAnim', 'estado').activo, false, 'pausa → deja de bailar');
    assert.equal(JSON.parse(globalThis.luneMMD('estado')).fase, 'pausado');
    assert.equal(globalThis.luneMMD('pausa', { on: false }), true);
    assert.equal(reg.api('baileAnim', 'estado').activo, true);
    assert.equal(globalThis.luneMMD('parar', null), true);
    assert.equal(reg.api('baileAnim', 'estado').activo, false);
    const ev = JSON.parse(globalThis.luneEventos ? globalThis.luneEventos() : '[]').filter((e) => e.t === 'mmd').map((e) => e.d.fase);
    assert.ok(ev.includes('sonando') && ev.includes('pausado') && ev.at(-1) === 'parado', ev.join(','));
  } finally {
    globalThis.lunePulso = pulsoPagina;
    globalThis.luneSetFPS(0);
    globalThis.LuneMMDAudio = AUDIO_REAL;
  }
});
