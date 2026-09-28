// tests/js/mmd_audio.test.mjs — ui_web/lune_mmd_audio.js (corte 9): la canción del baile MMD
// en la página de la mascota (script clásico → globalThis.LuneMMDAudio), su reloj con
// corrección de deriva, el duck mientras habla Lune y el pulso para la mascota animada.
// Con un <audio> falso (sin decodificar nada) y temporizadores virtuales.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearDocumento, crearTemporizador } from './dom_falso.mjs';
import { audioFalso } from './vmd_fabrica.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_mmd_audio.js', import.meta.url), 'utf8'), { filename: 'lune_mmd_audio.js' });
const { LuneMMDAudio } = globalThis;
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const microtareas = () => new Promise((r) => setImmediate(r));

test('LuneMMDAudio cuelga del global con sus constantes', () => {
  assert.equal(typeof LuneMMDAudio.crear, 'function');
  assert.equal(typeof LuneMMDAudio.crearReloj, 'function');
  assert.equal(typeof LuneMMDAudio.pulsoEn, 'function');
  assert.equal(LuneMMDAudio.TOLERANCIA, 0.08);
  assert.equal(LuneMMDAudio.DUCK, 0.35);
});

test('reloj: deriva > 80 ms salta al audio; < 80 ms corrige un 10 %; sin audio avanza con dt', () => {
  const r = LuneMMDAudio.crearReloj({ tolerancia: 0.08, correccion: 0.1 });
  assert.equal(r.reiniciar(0), 0);
  cerca(r.avanzar(0.1, 0.25), 0.25, 1e-12, 'salto');
  cerca(r.salto, 0.15, 1e-12);
  cerca(r.avanzar(0.1, 0.4), 0.35 + 0.1 * 0.05, 1e-12, 'corrección suave');
  assert.equal(r.salto, 0);
  cerca(r.avanzar(0.1, null), 0.455, 1e-12, 'sin audio');
  cerca(r.avanzar(0.1, 0.4), 0.4, 1e-12, 'hacia atrás más de 80 ms también salta');
  cerca(r.salto, -0.155, 1e-12);
  cerca(r.t, 0.4, 1e-12);
  cerca(r.avanzar(NaN, undefined), 0.4, 1e-12, 'dt roto no mueve');
  assert.equal(r.reiniciar('x'), 0);
});

test('pulsoEn: fase = (fase0 + t·bpm/60) mod 1, bpm acotado y valores por defecto', () => {
  const p = LuneMMDAudio.pulsoEn(1.5, { bpm: 120, fase0: 0.25 });
  assert.equal(p.bpm, 120);
  cerca(p.fase, 0.25, 1e-12);
  cerca(LuneMMDAudio.pulsoEn(0.25, { bpm: 60, fase0: 0.9 }).fase, 0.15, 1e-12);
  assert.equal(LuneMMDAudio.pulsoEn(1, { bpm: 900 }).bpm, 240);
  assert.equal(LuneMMDAudio.pulsoEn(1, { bpm: 'x' }).bpm, 120);
  cerca(LuneMMDAudio.pulsoEn(-0.25, { bpm: 120, fase0: 0 }).fase, 0.5, 1e-12, 'fase siempre en 0..1');
});

test('cargar: espera loadedmetadata → {ok, total}; preload auto; volumen aplicado', async () => {
  const el = audioFalso({ duracion: 183.5 });
  const a = LuneMMDAudio.crear({ crearAudio: () => el, ahora: () => 0 });
  a.volumen(0.6);
  const r = await a.cargar('/bailes/x/cancion.mp3');
  assert.deepEqual(r, { ok: true, total: 183.5, error: '' });
  assert.equal(el.src, '/bailes/x/cancion.mp3');
  assert.equal(el.preload, 'auto');
  cerca(el.volume, 0.6, 1e-12);
  assert.equal(a.total(), 183.5);
  assert.equal(el.oyentes('loadedmetadata'), 0, 'sin oyentes colgando');
});

test('cargar con error del <audio> o sin respuesta en 15 s → ok:false con el motivo', async () => {
  const a = LuneMMDAudio.crear({ crearAudio: () => audioFalso({ fallar: true }), ahora: () => 0 });
  const r = await a.cargar('/bailes/x/raro.m4a');
  assert.equal(r.ok, false);
  assert.match(r.error, /formato no soportado/);
  assert.equal((await a.cargar('')).ok, false, 'sin URL');

  const tmp = crearTemporizador();
  const b = LuneMMDAudio.crear({ crearAudio: () => audioFalso({ silencioso: true }), ahora: () => 0, setTimeout: tmp.setTimeout, clearTimeout: tmp.clearTimeout });
  const p = b.cargar('/bailes/x/lenta.ogg');
  tmp.avanzar(14999);
  let hecho = false; p.then(() => { hecho = true; });
  await microtareas();
  assert.equal(hecho, false);
  tmp.avanzar(2);
  const r2 = await p;
  assert.deepEqual(r2, { ok: false, total: 0, error: 'la canción no carga' });
});

test('una carga nueva sustituye a la anterior: la vieja acaba en «reemplazado» y su <audio> se suelta', async () => {
  const els = [audioFalso({ silencioso: true }), audioFalso({ duracion: 5 })];
  let i = 0;
  const a = LuneMMDAudio.crear({ crearAudio: () => els[i++], ahora: () => 0 });
  const p1 = a.cargar('/bailes/a.mp3');
  const p2 = a.cargar('/bailes/b.mp3');
  assert.deepEqual(await p1, { ok: false, total: 0, error: 'reemplazado' });
  assert.equal((await p2).ok, true);
  assert.ok(els[0].quitados.includes('src') && els[0].cargas >= 1, 'pause + removeAttribute(src) + load() en el viejo');
  assert.equal(a.elemento, els[1]);
});

test('reproducir, pausar, parar, offset y t(): el reloj del baile es currentTime + offset', async () => {
  const el = audioFalso({ duracion: 20 });
  const a = LuneMMDAudio.crear({ crearAudio: () => el, ahora: () => 0 });
  assert.equal(a.t(), null, 'sin canción');
  await a.cargar('/bailes/c.ogg');
  assert.equal(await a.reproducir(), true);
  assert.equal(a.sonando(), true);
  el.avanzar(3);
  assert.equal(a.offset(120), 120);
  cerca(a.t(), 3.12, 1e-12);
  assert.equal(a.offset(-9000), -500, 'offset acotado');
  cerca(a.t(), 2.5, 1e-12);
  a.pausar();
  assert.equal(a.sonando(), false);
  a.parar();
  assert.equal(el.currentTime, 0);
  a.reproducir();
  el.avanzar(25);
  assert.equal(a.terminado(), true);
  assert.equal(a.sonando(), false);
});

test('duck: × 0.35 suavizado con el reloj inyectado y vuelta al volumen normal', async () => {
  const el = audioFalso();
  let ms = 0;
  const a = LuneMMDAudio.crear({ crearAudio: () => el, ahora: () => ms });
  await a.cargar('/bailes/d.mp3');
  a.volumen(0.8);
  a.duck(true);
  cerca(el.volume, 0.8, 1e-9, 'no salta de golpe');
  for (let i = 0; i < 60; i++) { ms += 1000 / 60; a.paso(); }
  assert.ok(el.volume < 0.8 * 0.36 && el.volume >= 0.8 * 0.35 - 1e-9, `en 1 s baja a ×0.35 (${el.volume})`);
  a.duck(false);
  for (let i = 0; i < 60; i++) { ms += 1000 / 60; a.t(); }
  cerca(el.volume, 0.8, 0.002, 'vuelve');
  cerca(a.volumenEfectivo, 0.8, 0.002);
});

test('liberar: pause + removeAttribute(src) + load(); play() rechazado → false y aviso', async () => {
  const el = audioFalso();
  const a = LuneMMDAudio.crear({ crearAudio: () => el, ahora: () => 0 });
  await a.cargar('/bailes/e.mp3');
  a.liberar();
  assert.ok(el.pausas >= 1);
  assert.ok(el.quitados.includes('src'));
  assert.ok(el.cargas >= 1);
  assert.equal(a.t(), null);
  assert.equal(await a.reproducir(), false);

  const avisos = [];
  const b = LuneMMDAudio.crear({ crearAudio: () => audioFalso({ rechazarPlay: true }), ahora: () => 0, emitir: (t, d) => avisos.push([t, d]) });
  await b.cargar('/bailes/f.mp3');
  assert.equal(await b.reproducir(), false);
  assert.equal(avisos.length, 1);
  assert.equal(avisos[0][0], 'mmd_audio');
  assert.match(avisos[0][1].error, /NotAllowedError/);
  assert.match(b.error, /NotAllowedError/);
});

test('sin crearAudio usa document.createElement("audio")', async () => {
  const doc = crearDocumento();
  const a = LuneMMDAudio.crear({ doc, ahora: () => 0, esperaMs: 50 });
  const p = a.cargar('/bailes/g.mp3');
  assert.equal(doc.creados.length, 1);
  assert.equal(doc.creados[0].tagName, 'AUDIO');
  doc.creados[0].duration = 7;
  doc.creados[0].disparar('loadedmetadata');
  assert.deepEqual(await p, { ok: true, total: 7, error: '' });
});
