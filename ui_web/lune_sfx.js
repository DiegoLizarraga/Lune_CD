/*
 * ui_web/lune_sfx.js — efectos de sonido cortos de las páginas (WebAudio).
 *
 * Para qué sirve: arrastrar, soltar, comer, abrir menús o sonar una alarma dentro
 * de la asistente o de la web sin pasar por Python ni por pygame (que es solo de la
 * voz). Cada archivo se descarga y decodifica una vez (caché por URL) y se toca
 * con un volumen y un tono (playbackRate) aleatorio dentro de un rango, para que
 * no suene siempre igual. Todo pasa por un GainNode maestro (volumen general).
 *
 * Script clásico: <script src="lune_sfx.js"> en companion.html, companion_vrm.html
 * o index.html. La base de URLs sale de la ubicación de ESTE archivo
 * (ui_web/assets/sfx/), así funciona igual desde cualquier página.
 *
 * API (window.luneSfx es a la vez función y objeto):
 *   luneSfx(nombre, opciones)            = luneSfx.tocar(...)
 *   luneSfx.tocar(nombre | [nombres], {vol=1, pitch=[min,max] | número, bucle=false, canal})
 *        → Promise<{detener()} | null>   ('trago_2' → assets/sfx/trago_2.wav; con
 *                                         lista elige uno al azar)
 *   luneSfx.setVolumen(v 0..1) · luneSfx.getVolumen()
 *   luneSfx.cargar(nombre) → Promise<AudioBuffer|null> · luneSfx.precargar([nombres])
 *   luneSfx.detenerCanal(canal) · luneSfx.detenerTodo()
 *   luneSfx.setBase(url) · luneSfx.url(nombre)
 *
 * Si no hay WebAudio o el archivo no existe, no lanza: devuelve null y reintenta
 * ese archivo como pronto a los 30 s.
 */
(function (w) {
  'use strict';

  if (w.luneSfx && w.luneSfx.__lune) return;   // ya cargado: no perder la caché

  var MAX_VOCES = 24;             // sonidos simultáneos; al pasar se corta el más viejo
  var REINTENTO_MS = 30000;
  var EXT_DEFECTO = '.wav';

  function baseDefecto() {
    try {
      var s = w.document && w.document.currentScript;
      if (s && s.src) return new URL('assets/sfx/', s.src).href;
    } catch (e) { /* sin document o URL */ }
    return 'assets/sfx/';
  }

  var base = baseDefecto();
  var volumen = 1;
  var ctx = null, maestro = null;
  var cache = {};                 // url → Promise<AudioBuffer|null>
  var fallos = {};                // url → ms del último fallo
  var voces = [];                 // [{fuente, ganancia, canal}]

  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function ahora() { return Date.now(); }

  function contexto() {
    if (ctx) return ctx;
    var AC = w.AudioContext || w.webkitAudioContext;
    if (!AC) return null;
    try {
      ctx = new AC();
      maestro = ctx.createGain();
      maestro.gain.value = volumen;
      maestro.connect(ctx.destination);
    } catch (e) {
      ctx = null; maestro = null;
    }
    return ctx;
  }

  function url(nombre) {
    var n = String(nombre || '').trim();
    if (/^([a-z]+:|\/)/i.test(n)) return n;                      // absoluta
    if (!/\.[a-z0-9]{2,4}$/i.test(n)) n += EXT_DEFECTO;
    return base.replace(/\/?$/, '/') + n;
  }

  function decodificar(c, datos) {
    return new Promise(function (ok, mal) {
      var r = c.decodeAudioData(datos, ok, mal);                  // forma antigua con callbacks…
      if (r && typeof r.then === 'function') r.then(ok, mal);     // …y la de promesa
    });
  }

  function cargar(nombre) {
    var u = url(nombre);
    if (cache[u]) return cache[u];
    if (fallos[u] && ahora() - fallos[u] < REINTENTO_MS) return Promise.resolve(null);
    var c = contexto();
    if (!c || typeof w.fetch !== 'function') return Promise.resolve(null);
    var p = w.fetch(u)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.arrayBuffer();
      })
      .then(function (datos) { return decodificar(c, datos); })
      .catch(function (e) {
        delete cache[u];
        fallos[u] = ahora();
        try { console.warn('[luneSfx] no se pudo cargar', u, String((e && e.message) || e)); } catch (e2) { /* sin consola */ }
        return null;
      });
    cache[u] = p;
    return p;
  }

  function precargar(nombres) {
    return Promise.all((nombres || []).map(cargar));
  }

  function tono(pitch) {
    var api = w.luneSfx;
    var azar = api && typeof api.aleatorio === 'function' ? api.aleatorio : Math.random;
    var r;
    if (typeof pitch === 'number') r = pitch;
    else if (pitch && pitch.length === 2) {
      var a = Number(pitch[0]), b = Number(pitch[1]);
      r = a + (b - a) * azar();
    } else r = 1;
    return Number.isFinite(r) && r > 0 ? clamp(r, 0.25, 4) : 1;
  }

  function quitarVoz(v) {
    var i = voces.indexOf(v);
    if (i >= 0) voces.splice(i, 1);
    try { v.ganancia.disconnect(); } catch (e) { /* ya desconectada */ }
  }

  function detenerVoz(v) {
    try { v.fuente.stop(); } catch (e) { /* ya parada */ }
    quitarVoz(v);
  }

  function tocar(nombre, opciones) {
    var o = opciones || {};
    if (Array.isArray(nombre)) {
      if (!nombre.length) return Promise.resolve(null);
      var api = w.luneSfx;
      var azar = api && typeof api.aleatorio === 'function' ? api.aleatorio : Math.random;
      nombre = nombre[clamp(Math.floor(azar() * nombre.length), 0, nombre.length - 1)];
    }
    var c = contexto();
    if (!c || !nombre) return Promise.resolve(null);
    if (c.state === 'suspended' && typeof c.resume === 'function') {
      try { var r = c.resume(); if (r && r.catch) r.catch(function () {}); } catch (e) { /* sin gesto */ }
    }
    return cargar(nombre).then(function (buf) {
      if (!buf) return null;
      while (voces.length >= MAX_VOCES) detenerVoz(voces[0]);
      var fuente = c.createBufferSource();
      fuente.buffer = buf;
      fuente.loop = !!o.bucle;
      fuente.playbackRate.value = tono(o.pitch);
      var ganancia = c.createGain();
      var vol = Number(o.vol);
      ganancia.gain.value = Number.isFinite(vol) ? clamp(vol, 0, 2) : 1;
      fuente.connect(ganancia);
      ganancia.connect(maestro);
      var voz = { fuente: fuente, ganancia: ganancia, canal: o.canal == null ? null : String(o.canal) };
      fuente.onended = function () { quitarVoz(voz); };
      voces.push(voz);
      fuente.start(0);
      return { detener: function () { detenerVoz(voz); }, canal: voz.canal };
    });
  }

  function detenerCanal(canal) {
    var c = String(canal);
    voces.slice().forEach(function (v) { if (v.canal === c) detenerVoz(v); });
  }

  function detenerTodo() {
    voces.slice().forEach(detenerVoz);
  }

  function setVolumen(v) {
    var n = Number(v);
    if (!Number.isFinite(n)) return volumen;
    volumen = clamp(n, 0, 1);
    if (maestro) {
      try {
        // Rampa corta: cambiar el volumen de golpe hace "clic".
        maestro.gain.setTargetAtTime(volumen, ctx.currentTime, 0.015);
      } catch (e) {
        maestro.gain.value = volumen;
      }
    }
    return volumen;
  }

  function luneSfx(nombre, opciones) { return tocar(nombre, opciones); }
  luneSfx.__lune = true;
  luneSfx.tocar = tocar;
  luneSfx.cargar = cargar;
  luneSfx.precargar = precargar;
  luneSfx.setVolumen = setVolumen;
  luneSfx.getVolumen = function () { return volumen; };
  luneSfx.detenerCanal = detenerCanal;
  luneSfx.detenerTodo = detenerTodo;
  luneSfx.setBase = function (u) { if (u) base = String(u); return base; };
  luneSfx.url = url;
  luneSfx.sonando = function () { return voces.length; };
  luneSfx.aleatorio = Math.random;

  w.luneSfx = luneSfx;
})(typeof window !== 'undefined' ? window : globalThis);
