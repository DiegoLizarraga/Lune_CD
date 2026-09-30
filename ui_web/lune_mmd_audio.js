/*
 * ui_web/lune_mmd_audio.js — la canción de un baile MMD/VRMA en la propia página de la
 * asistente (corte 9; script clásico, como lune_ritmo.js). La usan ui_web/vrm/lune_mmd.js
 * (asistente VRM) y ui_web/anim/lune_anim_mmd.js (asistente animada: baila «a su manera» al
 * pulso analizado de la canción). Suena donde se ve: el audio manda el reloj del baile.
 *
 *   var a = LuneMMDAudio.crear({doc, crearAudio, emitir, ahora});
 *   a.cargar(url) → Promise<{ok, total, error}>   (espera 'loadedmetadata'; 'error' o 15 s → ok:false)
 *   a.reproducir() → Promise<bool> · a.pausar() · a.parar() (pausa y vuelve a 0)
 *   a.volumen(v 0..1) · a.duck(on) (× 0.35 suavizado mientras habla Lune) · a.offset(ms −500..500)
 *   a.t() → currentTime + offset (s) o null sin canción · a.total() · a.terminado() · a.sonando()
 *   a.paso() (aplica el suavizado del duck; también lo hacen t() y duck()) · a.liberar()
 *   liberar: pause + removeAttribute('src') + load() (suelta el decodificador y la memoria).
 *
 *   var r = LuneMMDAudio.crearReloj({tolerancia: 0.08, correccion: 0.1});
 *   r.avanzar(dt, tAudio|null) → t    t += dt; con audio: err = tAudio − t; |err| > 0.08 → salta
 *                                      a tAudio; si no, t += 0.1·err (sin tirones)
 *   r.reiniciar(t0) · r.t · r.salto (lo que saltó en el último avanzar; 0 si nada)
 *
 *   LuneMMDAudio.pulsoEn(t, {bpm, fase0}) → {bpm, fase}   fase = (fase0 + t·bpm/60) mod 1
 *
 * crearAudio por defecto: doc.createElement('audio') (o new Audio()). ahora() en ms (por
 * defecto performance.now): lo usa el suavizado del duck. emitir(tipo, datos) opcional: si
 * play() falla (política de autoplay…) → emitir('mmd_audio', {error}).
 * En Node se carga con vm.runInThisContext (tests/js/mmd_audio.test.mjs).
 */
(function (g) {
  'use strict';

  var TOLERANCIA = 0.08;        // s de deriva a partir de los que el reloj salta al audio
  var CORRECCION = 0.1;         // fracción del error que se corrige por paso
  var DUCK = 0.35;              // volumen × esto mientras habla Lune
  var DUCK_K = 8;               // 1/s del suavizado del duck
  var ESPERA_MS = 15000;        // tope para 'loadedmetadata'
  var OFFSET_MAX = 500;         // ms

  function finito(v) { return typeof v === 'number' && isFinite(v); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function ahoraPorDefecto() {
    try { if (g.performance && typeof g.performance.now === 'function') return g.performance.now(); } catch (e) { /* sin performance */ }
    return Date.now();
  }

  function crear(opciones) {
    opciones = opciones || {};
    var doc = opciones.doc || g.document || null;
    var crearAudio = typeof opciones.crearAudio === 'function' ? opciones.crearAudio : function () {
      if (doc && typeof doc.createElement === 'function') return doc.createElement('audio');
      return new g.Audio();
    };
    var emitir = typeof opciones.emitir === 'function' ? opciones.emitir : null;
    var ahora = typeof opciones.ahora === 'function' ? opciones.ahora : ahoraPorDefecto;
    var poner = typeof opciones.setTimeout === 'function' ? opciones.setTimeout : g.setTimeout;
    var quitar = typeof opciones.clearTimeout === 'function' ? opciones.clearTimeout : g.clearTimeout;
    var esperaMs = finito(opciones.esperaMs) ? opciones.esperaMs : ESPERA_MS;

    var el = null, base = 1, duckObj = 1, duckAct = 1, tDuck = null, offsetS = 0, error = '';
    var pendiente = null;                         // {resolver, limpiar} de la carga en curso

    function aplicarVolumen() {
      var t = Number(ahora());
      if (tDuck !== null && finito(t)) {
        var dt = Math.max(0, (t - tDuck) / 1000);
        duckAct += (duckObj - duckAct) * (1 - Math.exp(-DUCK_K * dt));
        if (Math.abs(duckAct - duckObj) < 1e-3) duckAct = duckObj;
      }
      tDuck = finito(t) ? t : tDuck;
      if (el) { try { el.volume = clamp(base * duckAct, 0, 1); } catch (e) { /* sin volumen */ } }
    }

    function soltar(e) {
      if (!e) return;
      try { e.pause(); } catch (x) { /* ya parado */ }
      try { e.removeAttribute('src'); } catch (x) { /* sin atributos */ }
      try { e.load(); } catch (x) { /* sin load */ }
    }

    function terminarPendiente(res) {
      if (!pendiente) return;
      var p = pendiente;
      pendiente = null;
      p.limpiar();
      p.resolver(res);
    }

    function cargar(url) {
      terminarPendiente({ ok: false, total: 0, error: 'reemplazado' });
      soltar(el);
      el = null;
      error = '';
      if (typeof url !== 'string' || !url) return Promise.resolve({ ok: false, total: 0, error: 'sin URL' });
      var e;
      try { e = crearAudio(); } catch (x) { return Promise.resolve({ ok: false, total: 0, error: String((x && x.message) || x) }); }
      if (!e) return Promise.resolve({ ok: false, total: 0, error: 'sin <audio>' });
      el = e;
      return new Promise(function (resolver) {
        var temporizador = null;
        function alCargar() {
          if (el !== e) return;
          var d = Number(e.duration);
          terminarPendiente({ ok: true, total: finito(d) && d > 0 ? d : 0, error: '' });
        }
        function alFallar() {
          if (el !== e) return;
          var m = e.error && (e.error.message || e.error.code) ? String(e.error.message || ('código ' + e.error.code)) : 'no se pudo abrir la canción';
          error = m;
          terminarPendiente({ ok: false, total: 0, error: m });
        }
        pendiente = {
          resolver: resolver,
          limpiar: function () {
            try { e.removeEventListener('loadedmetadata', alCargar); e.removeEventListener('error', alFallar); } catch (x) { /* sin oyentes */ }
            if (temporizador !== null) { try { quitar(temporizador); } catch (x) { /* sin temporizador */ } temporizador = null; }
          },
        };
        try {
          e.addEventListener('loadedmetadata', alCargar);
          e.addEventListener('error', alFallar);
        } catch (x) { /* sin eventos: solo el tope */ }
        try { if (poner) temporizador = poner(function () { if (el === e) { error = 'la canción no carga'; terminarPendiente({ ok: false, total: 0, error: error }); } }, esperaMs); } catch (x) { /* sin tope */ }
        try { e.preload = 'auto'; } catch (x) { /* sin preload */ }
        aplicarVolumen();
        try { e.src = url; } catch (x) { error = String((x && x.message) || x); terminarPendiente({ ok: false, total: 0, error: error }); return; }
        try { if (typeof e.load === 'function') e.load(); } catch (x) { /* el src ya carga */ }
      });
    }

    function reproducir() {
      if (!el) return Promise.resolve(false);
      aplicarVolumen();
      var r;
      try { r = el.play(); } catch (x) { r = Promise.reject(x); }
      return Promise.resolve(r).then(function () { return true; }, function (x) {
        error = String((x && x.message) || x || 'play');
        if (emitir) { try { emitir('mmd_audio', { error: error.slice(0, 200) }); } catch (y) { /* sin canal */ } }
        return false;
      });
    }

    return {
      cargar: cargar,
      reproducir: reproducir,
      pausar: function () { if (el) { try { el.pause(); } catch (x) { /* ya */ } } return !!el; },
      parar: function () {
        if (!el) return false;
        try { el.pause(); } catch (x) { /* ya */ }
        try { el.currentTime = 0; } catch (x) { /* sin buscar */ }
        return true;
      },
      volumen: function (v) { var n = Number(v); if (finito(n)) base = clamp(n, 0, 1); aplicarVolumen(); return base; },
      duck: function (on) { duckObj = on ? DUCK : 1; aplicarVolumen(); return duckObj; },
      offset: function (ms) { var n = Number(ms); if (finito(n)) offsetS = clamp(n, -OFFSET_MAX, OFFSET_MAX) / 1000; return offsetS * 1000; },
      t: function () {
        if (!el) return null;
        aplicarVolumen();
        var c = Number(el.currentTime);
        return (finito(c) ? c : 0) + offsetS;
      },
      total: function () { var d = el ? Number(el.duration) : 0; return finito(d) && d > 0 ? d : 0; },
      terminado: function () { return !!(el && el.ended); },
      sonando: function () { return !!(el && !el.paused && !el.ended); },
      paso: function () { aplicarVolumen(); return el ? el.volume : 0; },
      liberar: function () { terminarPendiente({ ok: false, total: 0, error: 'liberado' }); soltar(el); el = null; },
      get elemento() { return el; },
      get error() { return error; },
      get volumenEfectivo() { return clamp(base * duckAct, 0, 1); },
    };
  }

  function crearReloj(opciones) {
    opciones = opciones || {};
    var tol = finito(opciones.tolerancia) ? Math.max(0, opciones.tolerancia) : TOLERANCIA;
    var corr = finito(opciones.correccion) ? clamp(opciones.correccion, 0, 1) : CORRECCION;
    var t = finito(opciones.t0) ? opciones.t0 : 0;
    var salto = 0;
    return {
      avanzar: function (dt, tAudio) {
        salto = 0;
        var d = Number(dt);
        if (finito(d) && d > 0) t += d;
        var a = tAudio === null || tAudio === undefined ? NaN : Number(tAudio);
        if (finito(a)) {
          var err = a - t;
          if (Math.abs(err) > tol) { salto = err; t = a; } else t += corr * err;
        }
        return t;
      },
      reiniciar: function (t0) { var n = Number(t0); t = finito(n) ? n : 0; salto = 0; return t; },
      get t() { return t; },
      get salto() { return salto; },
    };
  }

  function pulsoEn(t, datos) {
    datos = datos || {};
    var b = Number(datos.bpm), f0 = Number(datos.fase0), tt = Number(t);
    b = finito(b) && b > 0 ? clamp(b, 40, 240) : 120;
    f0 = finito(f0) ? f0 : 0;
    tt = finito(tt) ? tt : 0;
    var fase = f0 + tt * b / 60;
    fase -= Math.floor(fase);
    return { bpm: b, fase: fase };
  }

  g.LuneMMDAudio = {
    TOLERANCIA: TOLERANCIA, CORRECCION: CORRECCION, DUCK: DUCK, OFFSET_MAX: OFFSET_MAX,
    crear: crear, crearReloj: crearReloj, pulsoEn: pulsoEn,
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
