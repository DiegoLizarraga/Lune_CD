// tests/js/anim_mmd.test.mjs — los bailes de la biblioteca en la mascota ANIMADA
// (ui_web/anim/lune_anim_mmd.js, corte 9, D1): la canción suena en la página con el
// LuneMMDAudio de verdad (lune_mmd_audio.js; el <audio> es falso) y Lune baila el baile
// procedural (luneBailar/lunePulso) al pulso ANALIZADO: lunePulso ≤ 2 Hz con la fase de
// LuneMMDAudio.pulsoEn sobre el reloj del audio; pausa → deja de bailar y sigue desde el
// mismo punto; fin → 'fin' y sigue bailando 1.5 s esperando otro; bucle; errores; rutas.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import {
  instalar, orden, urlPermitida, opcionesAudio, NOMBRE, ORDEN, PARAMS_MMD_ANIM,
} from '../../ui_web/anim/lune_anim_mmd.js';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_mmd_audio.js', import.meta.url), 'utf8'), { filename: 'lune_mmd_audio.js' });
const LuneMMDAudio = globalThis.LuneMMDAudio;
const ORIGEN = 'http://127.0.0.1:8765';
const ID = '0123456789ab';
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);
const esperar = () => new Promise((r) => setTimeout(r, 0));

/** <audio> falso: 'loadedmetadata' al poner src; avanzar(s) mueve currentTime y acaba en la duración. */
function audioFalso({ duracion = 10, fallar = false, rechazarPlay = false } = {}) {
  const oyentes = {};
  let src = '';
  const el = {
    currentTime: 0, duration: NaN, paused: true, ended: false, volume: 1, preload: '', error: null,
    reproducciones: 0, pausas: 0, quitados: [],
    get src() { return src; },
    set src(v) {
      src = String(v);
      if (!src) return;
      queueMicrotask(() => {
        if (fallar) { el.error = { code: 4, message: 'formato no soportado' }; el.disparar('error'); }
        else { el.duration = duracion; el.disparar('loadedmetadata'); }
      });
    },
    addEventListener(t, f) { (oyentes[t] || (oyentes[t] = new Set())).add(f); },
    removeEventListener(t, f) { if (oyentes[t]) oyentes[t].delete(f); },
    disparar(t) { for (const f of [...(oyentes[t] || [])]) f({ type: t, target: el }); },
    play() {
      el.reproducciones++;
      if (rechazarPlay) return Promise.reject(new Error('NotAllowedError'));
      el.paused = false; el.ended = false;
      return Promise.resolve();
    },
    pause() { el.pausas++; el.paused = true; },
    load() {},
    removeAttribute(k) { el.quitados.push(k); if (k === 'src') src = ''; },
    avanzar(s) {
      if (el.paused || el.ended) return;
      el.currentTime = Math.min(el.duration, el.currentTime + s);
      if (el.currentTime >= el.duration) { el.ended = true; el.paused = true; }
    },
  };
  return el;
}

/** El módulo con un registro mínimo: bailar/pulso/eventos apuntados y pasos a 60 Hz. */
function montar(opciones = {}) {
  const audios = [];
  const fabrica = () => { const a = audioFalso(opciones.audio || {}); audios.push(a); return a; };
  const AUDIO = { ...LuneMMDAudio, crear: (o) => LuneMMDAudio.crear({ ...o, crearAudio: fabrica }) };
  const est = { hablando: false, drag: false };
  const eventos = [], bailes = [], pulsos = [];
  let t = 0;
  const mod = instalar({ estado: () => est, emitir: (tipo, d) => eventos.push([tipo, { ...d }]) }, {
    audio: AUDIO, origen: ORIGEN,
    bailar: (on, o) => bailes.push(o === undefined ? [on] : [on, o]),
    pulso: (b, f, e) => pulsos.push({ t, b, f, e, tAudio: audios.length ? audios[audios.length - 1].currentTime : 0 }),
  });
  const pasos = (seg, avanzarAudio = true) => {
    const dt = 1 / 60;
    for (let i = 0, n = Math.round(seg * 60); i < n; i++) {
      t += dt;
      if (avanzarAudio) for (const a of audios) a.avanzar(dt);
      mod.tick(dt, t, est);
    }
  };
  const fases = () => eventos.filter(([tipo]) => tipo === 'mmd').map(([, d]) => d.fase);
  return { mod, est, eventos, bailes, pulsos, audios, pasos, fases, get t() { return t; } };
}

const carga = (extra = {}) => ({
  id: ID, tipo: 'audio', audio: '/bailes/Senbonzakura/cancion.mp3', bpm: 150, fase0: 0.25,
  offsetMs: 0, volumen: 0.5, bucle: false, autoplay: true, titulo: 'Senbonzakura', ...extra,
});

test('urlPermitida y opcionesAudio: solo /bailes/ y /bailes_cache/ del mismo origen; rangos', () => {
  assert.equal(NOMBRE, 'mmdAnim');
  assert.equal(ORDEN, 60);
  assert.equal(urlPermitida('/bailes/A/c.mp3', ORIGEN), `${ORIGEN}/bailes/A/c.mp3`);
  assert.equal(urlPermitida('/bailes_cache/0123456789ab.ogg', ORIGEN), `${ORIGEN}/bailes_cache/0123456789ab.ogg`);
  assert.equal(urlPermitida('/bailes/%E5%8D%83%E6%9C%AC%E6%A1%9C/c.mp3', ORIGEN) !== null, true, 'japonés codificado');
  for (const malo of ['http://evil.com/bailes/a.mp3', '//evil.com/bailes/a.mp3', '/bailes/../ui/x.js', '/bailes/a%2f..%2fb.mp3',
    '/bailes/a.mp3?x=1', '/bailes/a.mp3#h', '/ui/a.mp3', '/bailes/', '/bailes/a b.mp3', '/bailes\\a.mp3', 'file:///c:/a.mp3',
    'data:audio/mp3,xx', '/bailes/' + 'a'.repeat(1100), 42, null]) {
    assert.equal(urlPermitida(malo, ORIGEN), null, String(malo).slice(0, 60));
  }
  assert.equal(urlPermitida('/bailes/a.mp3', 'file:///c:/x'), null, 'origen que no es http');
  const { datos } = opcionesAudio(JSON.stringify(carga({ bpm: 999, fase0: 1, offsetMs: -9000, volumen: 7, id: 'ab<c>d' })), ORIGEN);
  assert.deepEqual(datos, {
    id: 'abcd', audio: `${ORIGEN}/bailes/Senbonzakura/cancion.mp3`, bpm: 240, fase0: 0, offsetMs: -500, volumen: 1,
    bucle: false, autoplay: true,
  });
  assert.equal(opcionesAudio(carga({ tipo: 'vmd' }), ORIGEN).error.includes('audio'), true);
  assert.equal(opcionesAudio(carga({ audio: 'http://evil.com/bailes/x.mp3' }), ORIGEN).error, 'ruta no permitida');
  assert.equal(opcionesAudio('{mal', ORIGEN).error, 'datos no válidos');
  assert.equal(opcionesAudio(carga({ bpm: true }), ORIGEN).datos.bpm, PARAMS_MMD_ANIM.bpm, 'un bool no es un número');
});

test('cargar → listo → sonando: la canción suena, baila y lunePulso ≤ 2 Hz con la fase de pulsoEn', async () => {
  const m = montar();
  assert.equal(await m.mod.api.cargar(carga({ offsetMs: 120 })), true);
  assert.deepEqual(m.fases(), ['cargando', 'listo', 'sonando']);
  const a = m.audios[0];
  assert.equal(a.src, `${ORIGEN}/bailes/Senbonzakura/cancion.mp3`);
  assert.equal(a.paused, false);
  cerca(a.volume, 0.5, 1e-9, 'volumen');
  assert.deepEqual(m.bailes, [[true, { particulas: true }]], 'luneBailar(true) una vez');
  assert.equal(m.mod.ocupado(), true);
  m.pasos(4);
  const n = m.pulsos.length;
  assert.ok(n >= 8 && n <= 10, `≈2 Hz en 4 s (${n})`);
  for (let i = 1; i < n; i++) assert.ok(m.pulsos[i].t - m.pulsos[i - 1].t >= 0.5 - 1e-6, 'nunca más de 2 Hz');
  for (const p of m.pulsos.slice(1)) {
    const esperado = LuneMMDAudio.pulsoEn(p.tAudio + 0.12, { bpm: 150, fase0: 0.25 });
    assert.equal(p.b, 150);
    cerca(p.f, esperado.fase, 1e-9, 'fase = pulsoEn(t del audio + offset)');
    assert.equal(p.e, 0.7);
  }
  const ts = m.eventos.filter(([, d]) => d.fase === 't').map(([, d]) => d.t);
  assert.ok(ts.length >= 3 && ts.every((t, i) => i === 0 || t > ts[i - 1]), `'t' cada segundo: ${ts}`);
  assert.equal(m.est.mmd, true);
  const e = JSON.parse(orden(m.mod.api, 'estado'));
  assert.equal(e.fase, 'sonando');
  assert.equal(e.id, ID);
  assert.equal(e.bailando, true);
  cerca(e.total, 10, 1e-9);
});

test('pausa (D5): deja de bailar con la canción en pausa; al seguir, desde el mismo t y a bailar', async () => {
  const m = montar();
  await m.mod.api.cargar(carga());
  m.pasos(2);
  const a = m.audios[0];
  assert.equal(orden(m.mod.api, 'pausa', { on: true }), true);
  assert.equal(a.paused, true);
  assert.deepEqual(m.bailes.at(-1), [false], 'luneBailar(false): al reposo');
  assert.equal(m.fases().at(-1), 'pausado');
  const t0 = a.currentTime, pulsos = m.pulsos.length;
  m.pasos(2);
  assert.equal(a.currentTime, t0, 't congelado');
  assert.equal(m.pulsos.length, pulsos, 'en pausa no hay pulsos');
  assert.equal(m.est.mmd, false);
  assert.equal(orden(m.mod.api, 'pausa', JSON.stringify({ on: false })), true);
  assert.equal(a.paused, false);
  assert.equal(m.bailes.at(-1)[0], true);
  assert.equal(m.fases().at(-1), 'sonando');
  cerca(a.currentTime, t0, 1e-9, 'desde el mismo punto');
  assert.ok(m.pulsos.length > pulsos, 'un pulso al seguir');
});

test('una pausa pedida MIENTRAS carga no se pierde: queda lista y quieta; seguir = reproducir', async () => {
  const m = montar();
  const p = m.mod.api.cargar(carga());
  assert.equal(orden(m.mod.api, 'pausa', { on: true }), true);
  assert.equal(await p, true);
  assert.deepEqual(m.fases(), ['cargando', 'listo']);
  assert.equal(m.audios[0].reproducciones, 0, 'no suena');
  assert.deepEqual(m.bailes, [], 'no baila');
  orden(m.mod.api, 'pausa', { on: false });
  assert.deepEqual(m.fases(), ['cargando', 'listo', 'sonando']);
  assert.equal(m.audios[0].paused, false);
  assert.deepEqual(m.bailes, [[true, { particulas: true }]]);
});

test('fin: «fin» y sigue bailando 1.5 s esperando otro; si no llega, deja de bailar y «parado»', async () => {
  const m = montar({ audio: { duracion: 2 } });
  await m.mod.api.cargar(carga());
  m.pasos(2.1);
  assert.equal(m.fases().filter((f) => f === 'fin').length, 1);
  assert.equal(m.bailes.length, 1, 'sigue bailando mientras espera');
  m.pasos(1.3);
  assert.equal(m.fases().includes('parado'), false);
  m.pasos(0.4);
  assert.equal(m.fases().at(-1), 'parado');
  assert.deepEqual(m.bailes.at(-1), [false]);
  assert.ok(m.audios[0].quitados.includes('src'), 'la canción se suelta');
  assert.equal(m.mod.ocupado(), false);
});

test('siguiente durante la espera: transición sin dejar de bailar', async () => {
  const m = montar({ audio: { duracion: 1 } });
  await m.mod.api.cargar(carga());
  m.pasos(1.2);
  assert.equal(m.fases().at(-1), 'fin');
  await m.mod.api.cargar(carga({ id: 'ba9876543210', audio: '/bailes_cache/ba9876543210.ogg', bpm: 90 }));
  assert.deepEqual(m.bailes, [[true, { particulas: true }]], 'nunca luneBailar(false) entre medias');
  assert.equal(m.fases().at(-1), 'sonando');
  m.pasos(1);
  assert.equal(m.pulsos.at(-1).b, 90, 'el pulso de la nueva');
  assert.equal(JSON.parse(orden(m.mod.api, 'estado')).id, 'ba9876543210');
});

test('bucle: vuelve a empezar sin «fin»; parar → deja de bailar, «parado» y suelta la canción', async () => {
  const m = montar({ audio: { duracion: 1 } });
  await m.mod.api.cargar(carga({ bucle: true }));
  m.pasos(3);
  assert.equal(m.fases().includes('fin'), false);
  assert.ok(m.audios[0].reproducciones >= 3, 'suena otra vez');
  orden(m.mod.api, 'bucle', { bucle: false });
  m.pasos(1.1);
  assert.equal(m.fases().includes('fin'), true);
  assert.equal(orden(m.mod.api, 'parar'), true);
  assert.equal(m.fases().at(-1), 'parado');
  assert.deepEqual(m.bailes.at(-1), [false]);
  assert.equal(orden(m.mod.api, 'parar'), false, 'ya estaba parado');
});

test('hablando: la canción al 35 %; volumen y offset en caliente; enSitio no aplica', async () => {
  const m = montar();
  await m.mod.api.cargar(carga({ volumen: 0.8 }));
  m.est.hablando = true;
  m.pasos(1);
  cerca(m.audios[0].volume, 0.8 * 0.35, 0.01, 'duck');
  m.est.hablando = false;
  m.pasos(1);
  cerca(m.audios[0].volume, 0.8, 0.01);
  orden(m.mod.api, 'volumen', { volumen: 0.2 });
  m.pasos(0.1);
  cerca(m.audios[0].volume, 0.2, 0.01);
  orden(m.mod.api, 'offset', { offsetMs: -300 });
  assert.equal(JSON.parse(orden(m.mod.api, 'estado')).offsetMs, -300);
  assert.equal(m.mod.api.enSitio(true), false);
});

test('errores: ruta de fuera, canción que no carga o play rechazado → «error» y sin bailar', async () => {
  const m = montar();
  assert.equal(await m.mod.api.cargar(carga({ audio: 'http://evil.com/bailes/x.mp3' })), false);
  assert.deepEqual(m.fases(), ['error']);
  assert.equal(m.audios.length, 0, 'no se pidió nada');
  const m2 = montar({ audio: { fallar: true } });
  assert.equal(await m2.mod.api.cargar(carga()), false);
  assert.deepEqual(m2.fases(), ['cargando', 'error']);
  assert.match(m2.eventos.at(-1)[1].mensaje, /no se puede reproducir/);
  assert.deepEqual(m2.bailes, []);
  const m3 = montar({ audio: { rechazarPlay: true } });
  await m3.mod.api.cargar(carga());
  await esperar();
  assert.equal(m3.fases().at(-1), 'error');
  assert.deepEqual(m3.bailes, [[true, { particulas: true }], [false]], 'no baila en silencio');
  assert.equal(orden(null, 'estado'), false);
  assert.equal(orden(m3.mod.api, 'inventada'), false);
  assert.equal(orden(m3.mod.api, 'cargar', '[1,2]'), false);
});
