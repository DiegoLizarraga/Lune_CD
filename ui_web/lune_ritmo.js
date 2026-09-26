/*
 * ui_web/lune_ritmo.js — reloj del pulso de la música y notas ♪ (script clásico).
 *
 * El pulso lo calcula Python (nucleo/pulso.py, cortes 5 y 6) y llega a las páginas
 * como mucho 2 veces por segundo: {bpm, fase, energia}, con `fase` en 0..1 dentro
 * del pulso actual. Entre medias cada página extrapola con su propio reloj. Este
 * archivo es ese reloj, compartido por la mascota VRM (ui_web/vrm/lune_baile_proc.js),
 * la animada (ui_web/anim/lune_anim_baile.js) y la barra lateral de la web
 * (index.html lo carga con <script src>).
 *
 *   var r = LuneRitmo.crearReloj({ bpm: 120 });
 *   r.pulso(124, 0.3, 0.8, t);    // medida de Python; t en SEGUNDOS del reloj de quien llama
 *   var e = r.avanzar(t);         // cada frame → {pulsos, fase, bpm, energia, golpe, velocidad}
 *
 *   - `pulsos` es la cuenta CONTINUA de pulsos (13.4 = 40 % del pulso 13): nunca salta.
 *     `fase` = pulsos mod 1 y `golpe` = en este paso se cruzó un pulso entero.
 *   - La primera medida recién creado o reiniciado (menos de ALINEAR_S s en marcha)
 *     alinea de golpe; las demás corrigen el error de fase cambiando la velocidad
 *     como mucho un ±20 % (CORRECCION_MAX) en vez de saltar: un error de medio
 *     pulso se come en unos 2.5 pulsos.
 *   - Un bpm nuevo se adopta al momento (la fase sigue continua).
 *   - Sin medidas va como un metrónomo al último bpm (o al de crearReloj).
 *
 * LuneNotas: notas ♪ ♫ que suben con cada pulso (baile.particulas), en el DOM y con
 * el color del tema (clase .lune-nota de ui_web/css/baile.css).
 *
 *   var n = LuneNotas.crear({ doc: document, contenedor: el });   // sin contenedor: #lune-notas en <body>
 *   n.golpe(energia) · n.limpiar() · n.cuantas
 *
 * Todo cuelga de globalThis (window en la página); en Node se carga con
 * vm.runInThisContext (tests/js/ritmo.test.mjs).
 */
(function (g) {
  'use strict';

  var BPM_MIN = 40, BPM_MAX = 240, BPM_DEFECTO = 120;
  var CORRECCION_MAX = 0.2;          // ±20 % de velocidad para corregir la fase
  var HORIZONTE = 1;                 // pulsos en los que se intenta comer el error
  var PASO_MAX = 0.5;                // s: un hueco mayor (pestaña dormida) cuenta como esto
  var ALINEAR_S = 0.25;              // s en marcha en los que la primera medida aún alinea de golpe

  function finito(v) { return typeof v === 'number' && isFinite(v); }
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function frac(v) { return v - Math.floor(v); }
  /** Diferencia de fase envuelta a [-0.5, 0.5). */
  function envolver(d) { return d - Math.floor(d + 0.5); }

  /** Normaliza una medida de Python: bpm 40–240, fase 0..1, energía 0..1 (null si el bpm no vale). */
  function normalizar(bpm, fase, energia) {
    var b = Number(bpm), f = Number(fase), e = Number(energia);
    if (!finito(b) || b <= 0) return null;
    return {
      bpm: clamp(b, BPM_MIN, BPM_MAX),
      fase: finito(f) ? frac(f) : 0,
      energia: finito(e) ? clamp(e, 0, 1) : 0.5,
    };
  }

  function crearReloj(opciones) {
    opciones = opciones || {};
    var ahora = typeof opciones.ahora === 'function' ? opciones.ahora
      : function () { var p = g.performance; return (p && p.now ? p.now() : Date.now()) / 1000; };
    var bpmInicial = normalizar(opciones.bpm === undefined ? BPM_DEFECTO : opciones.bpm, 0, 0);
    var st = {};

    function reiniciar() {
      st.pulsos = 0; st.bpm = bpmInicial ? bpmInicial.bpm : BPM_DEFECTO;
      st.t = null; st.error = 0; st.recorrido = 0;
      st.energia = 0; st.energiaObj = 0.6;
      st.golpe = false; st.velocidad = st.bpm / 60; st.medidas = 0;
      return reloj;
    }

    function estado() {
      return {
        pulsos: st.pulsos, fase: frac(st.pulsos), bpm: st.bpm, energia: st.energia,
        golpe: st.golpe, velocidad: st.velocidad, medidas: st.medidas,
      };
    }

    /** Avanza hasta t (s). Devuelve el estado; `golpe` solo vale para ESTE paso. */
    function avanzar(t) {
      if (!finito(t)) t = ahora();
      st.golpe = false;
      if (st.t === null) { st.t = t; return estado(); }
      var dt = t - st.t;
      st.t = t;
      if (!(dt > 0)) return estado();
      dt = Math.min(dt, PASO_MAX);
      st.recorrido += dt;
      var base = st.bpm / 60;
      var paso = base * dt;
      if (Math.abs(st.error) > 1e-6) {
        // Corrección = error / horizonte (en pulsos por pulso), tope ±20 % de la velocidad.
        var c = clamp(st.error / HORIZONTE, -CORRECCION_MAX, CORRECCION_MAX);
        var extra = c * paso;
        if (Math.abs(extra) > Math.abs(st.error)) extra = st.error;
        st.error -= extra;
        paso += extra;
      }
      var antes = st.pulsos;
      st.pulsos += paso;
      st.velocidad = paso / dt;
      st.golpe = Math.floor(st.pulsos) > Math.floor(antes);
      st.energia += (st.energiaObj - st.energia) * (1 - Math.exp(-4 * dt));
      return estado();
    }

    /** Medida de Python. t (s) = cuándo llega, en el mismo reloj que avanzar(). */
    function pulso(bpm, fase, energia, t) {
      var m = normalizar(bpm, fase, energia);
      if (!m) return false;
      avanzar(finito(t) ? t : ahora());
      st.bpm = m.bpm;
      st.energiaObj = m.energia;
      if (st.medidas === 0 && st.recorrido < ALINEAR_S) {
        st.pulsos = Math.floor(st.pulsos) + m.fase;   // recién empezado: se alinea de golpe
        st.error = 0;
      } else {
        st.error = envolver(m.fase - frac(st.pulsos));
      }
      st.medidas += 1;
      return true;
    }

    /** Sin música (baile manual): metrónomo a `bpm` desde la fase actual. */
    function metronomo(bpm) {
      var m = normalizar(bpm === undefined ? BPM_DEFECTO : bpm, 0, 0.6);
      if (!m) return false;
      st.bpm = m.bpm; st.error = 0; st.energiaObj = m.energia;
      return true;
    }

    var reloj = { avanzar: avanzar, pulso: pulso, metronomo: metronomo, reiniciar: reiniciar, estado: estado };
    return reiniciar();
  }

  // ── Notas ♪ ─────────────────────────────────────────────────────────────────
  var SIMBOLOS = ['♪', '♫'];        // ♪ ♫

  function quitarNodo(n) {
    try {
      if (typeof n.remove === 'function') n.remove();
      else if (n.parentNode && typeof n.parentNode.removeChild === 'function') n.parentNode.removeChild(n);
    } catch (e) { /* ya no está */ }
  }

  function crearNotas(opciones) {
    opciones = opciones || {};
    var doc = opciones.doc || g.document || null;
    var aleatorio = typeof opciones.aleatorio === 'function' ? opciones.aleatorio : Math.random;
    var poner = typeof opciones.setTimeout === 'function' ? opciones.setTimeout : g.setTimeout;
    var quitarT = typeof opciones.clearTimeout === 'function' ? opciones.clearTimeout : g.clearTimeout;
    var max = finito(opciones.max) ? Math.max(1, opciones.max | 0) : 6;
    var vidaMs = finito(opciones.vidaMs) ? Math.max(100, opciones.vidaMs) : 1600;
    var contenedor = opciones.contenedor || null;
    var vivas = [];

    function capa() {
      if (contenedor || !doc) return contenedor;
      var c = typeof doc.getElementById === 'function' ? doc.getElementById('lune-notas') : null;
      if (!c && doc.body && typeof doc.createElement === 'function') {
        c = doc.createElement('div');
        c.id = 'lune-notas';
        c.className = 'lune-notas';
        if (typeof c.setAttribute === 'function') c.setAttribute('aria-hidden', 'true');
        doc.body.appendChild(c);
      }
      contenedor = c || null;
      return contenedor;
    }

    function quitar(n) {
      var i = vivas.indexOf(n);
      if (i >= 0) vivas.splice(i, 1);
      if (n && n.__luneT && quitarT) { try { quitarT(n.__luneT); } catch (e) { /* sigue */ } }
      quitarNodo(n);
    }

    /** Un pulso: con probabilidad según la energía sale una nota (máximo `max` a la vez). */
    function golpe(energia) {
      var c = capa();
      if (!c || !doc || typeof doc.createElement !== 'function') return null;
      var e = finito(energia) ? clamp(energia, 0, 1) : 0.5;
      if (aleatorio() > 0.3 + 0.6 * e) return null;
      if (vivas.length >= max) quitar(vivas[0]);
      var n = doc.createElement('span');
      n.className = 'lune-nota';
      n.textContent = SIMBOLOS[aleatorio() < 0.5 ? 0 : 1];
      if (n.style && typeof n.style.setProperty === 'function') {
        n.style.setProperty('--nota-x', (12 + 76 * aleatorio()).toFixed(1) + '%');
        n.style.setProperty('--nota-giro', ((aleatorio() - 0.5) * 40).toFixed(1) + 'deg');
        n.style.setProperty('--nota-dur', (vidaMs / 1000).toFixed(2) + 's');
      }
      c.appendChild(n);
      vivas.push(n);
      if (poner) n.__luneT = poner(function () { quitar(n); }, vidaMs);
      return n;
    }

    function limpiar() { vivas.slice().forEach(quitar); }

    return {
      golpe: golpe, limpiar: limpiar,
      get cuantas() { return vivas.length; },
      get contenedor() { return contenedor; },
    };
  }

  g.LuneRitmo = {
    BPM_MIN: BPM_MIN, BPM_MAX: BPM_MAX, BPM_DEFECTO: BPM_DEFECTO,
    CORRECCION_MAX: CORRECCION_MAX, ALINEAR_S: ALINEAR_S,
    crearReloj: crearReloj, normalizar: normalizar,
  };
  g.LuneNotas = { crear: crearNotas };
})(typeof globalThis !== 'undefined' ? globalThis : this);
