/*
 * ui_web/lune_alarma.js — burbuja de ALARMA de la asistente (script clásico, cortes 5 y 6).
 *
 * Como AvatarBigScreenTimer de Mate-Engine: cuando suena una alarma, la burbuja
 * roja (#FF4826 = --lune-alarma, ui_web/css/alarma.css) aparece a los 3 s y el texto
 * se escribe a 35 caracteres por segundo. max-width: min(600px, 92vw), para que quepa
 * también en la ventana pequeña (crítica c.6). El texto va SIEMPRE con textContent.
 *
 *   var a = LuneAlarma.crear({ doc: document, contenedor: document.body });
 *   a.mostrar('Gimnasio', { retrasoMs: 3000, cps: 35 });   // → true
 *   a.ocultar();
 *
 * Las páginas lo publican como window.luneAlarma(texto | null, opts)
 * (ui/companion.py → mostrar_alarma / ocultar_alarma). setTimeout/clearTimeout son
 * inyectables (tests/js/alarma.test.mjs).
 */
(function (g) {
  'use strict';

  var RETRASO_MS = 3000, CPS = 35, MAX_TEXTO = 500;

  function finito(v) { return typeof v === 'number' && isFinite(v); }

  function crear(opciones) {
    opciones = opciones || {};
    var doc = opciones.doc || g.document || null;
    var poner = typeof opciones.setTimeout === 'function' ? opciones.setTimeout : function (f, ms) { return g.setTimeout(f, ms); };
    var quitar = typeof opciones.clearTimeout === 'function' ? opciones.clearTimeout : function (id) { g.clearTimeout(id); };
    var contenedor = opciones.contenedor || null;
    var el = null, txt = null, temporizador = null;
    var letras = [], escritas = 0, visible = false, activa = false;

    function asegurar() {
      if (el || !doc || typeof doc.createElement !== 'function') return el;
      var padre = contenedor || doc.body || null;
      if (!padre) return null;
      el = doc.createElement('div');
      el.id = 'lune-alarma';
      el.className = 'lune-alarma';
      if (typeof el.setAttribute === 'function') { el.setAttribute('role', 'alert'); el.setAttribute('aria-live', 'assertive'); }
      var quien = doc.createElement('span');
      quien.className = 'quien';
      quien.textContent = '⏰ Alarma';           // ⏰
      txt = doc.createElement('span');
      txt.className = 'txt';
      el.appendChild(quien);
      el.appendChild(txt);
      padre.appendChild(el);
      return el;
    }

    function parar() {
      if (temporizador !== null) { try { quitar(temporizador); } catch (e) { /* sigue */ } temporizador = null; }
    }

    function clase(on) {
      if (!el || !el.classList) return;
      if (on) el.classList.add('on'); else el.classList.remove('on');
    }

    function escribir(msPorLetra) {
      temporizador = null;
      if (!activa) return;
      escritas += 1;
      if (txt) txt.textContent = letras.slice(0, escritas).join('');
      if (escritas < letras.length) temporizador = poner(function () { escribir(msPorLetra); }, msPorLetra);
    }

    /** Muestra la alarma: tras retrasoMs aparece y se escribe a cps. */
    function mostrar(texto, o) {
      o = o || {};
      parar();
      var t = String(texto == null ? '' : texto).replace(/\s+/g, ' ').trim().slice(0, MAX_TEXTO);
      if (!t) t = 'Alarma';
      letras = Array.from ? Array.from(t) : t.split('');   // emojis enteros
      escritas = 0;
      activa = true;
      asegurar();
      if (txt) txt.textContent = '';
      var retraso = finito(o.retrasoMs) ? Math.max(0, o.retrasoMs) : RETRASO_MS;
      var cps = finito(o.cps) && o.cps > 0 ? Math.min(1000, o.cps) : CPS;
      var msPorLetra = 1000 / cps;
      var arrancar = function () {
        temporizador = null;
        if (!activa) return;
        visible = true;
        clase(true);
        escribir(msPorLetra);
      };
      if (retraso > 0) { visible = false; clase(false); temporizador = poner(arrancar, retraso); }
      else arrancar();
      return true;
    }

    function ocultar() {
      var habia = activa;
      parar();
      activa = false; visible = false; letras = []; escritas = 0;
      clase(false);
      if (txt) txt.textContent = '';
      return habia;
    }

    return {
      mostrar: mostrar, ocultar: ocultar,
      get activa() { return activa; },
      get visible() { return visible; },
      get texto() { return txt ? txt.textContent : ''; },
      get completo() { return letras.length > 0 && escritas >= letras.length; },
      get elemento() { return el; },
    };
  }

  g.LuneAlarma = { crear: crear, RETRASO_MS: RETRASO_MS, CPS: CPS, MAX_TEXTO: MAX_TEXTO };
})(typeof globalThis !== 'undefined' ? globalThis : this);
