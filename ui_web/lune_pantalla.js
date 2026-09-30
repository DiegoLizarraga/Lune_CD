/*
 * ui_web/lune_pantalla.js — lo que la PÁGINA pinta en pantalla grande y en el
 * salvapantallas (script clásico, cortes 5 y 6; lo cargan las dos páginas de la asistente).
 *
 *   var p = LunePantalla.crear({ doc: document, raiz: document.body });
 *   p.fase('entrar')                 clase body.lune-grande mientras la ventana es del
 *                                    monitor (entrar, salir); fuera en volver y fin
 *   p.salvapantallas(true, { fondo: true, reloj: true })
 *                                    body.lune-salva (+ .lune-salva-fondo: escritorio
 *                                    oscurecido) y un reloj HH:MM con el día, que se
 *                                    actualiza cada segundo mientras se ve
 *   p.salvapantallas(false)          todo fuera (el reloj deja de contar)
 *   p.estado() → {grande, salva, fondo, reloj, hora}
 *
 * Los estilos están en ui_web/css/grande.css. Qt la lleva al monitor y la duerme
 * (ui/companion.py → grande_fase, set_salvapantallas); aquí nada decide nada.
 * El reloj va con textContent. `ahora` (() → Date) y setInterval/clearInterval son
 * inyectables (tests/js/pantalla.test.mjs).
 */
(function (g) {
  'use strict';

  var DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  var FASES_GRANDE = { glide: null, entrar: true, salir: true, volver: false, fin: false };

  function dos(n) { return (n < 10 ? '0' : '') + n; }
  function horaTexto(d) { return dos(d.getHours()) + ':' + dos(d.getMinutes()); }
  function diaTexto(d) { return DIAS[d.getDay()] + ' ' + d.getDate(); }

  function clase(el, nombre, on) {
    if (!el || !el.classList) return;
    if (on) el.classList.add(nombre); else el.classList.remove(nombre);
  }

  function crear(opciones) {
    opciones = opciones || {};
    var doc = opciones.doc || g.document || null;
    var raiz = opciones.raiz || (doc && doc.body) || null;
    var ahora = typeof opciones.ahora === 'function' ? opciones.ahora : function () { return new Date(); };
    var cadaSeg = typeof opciones.setInterval === 'function' ? opciones.setInterval : function (f, ms) { return g.setInterval(f, ms); };
    var pararSeg = typeof opciones.clearInterval === 'function' ? opciones.clearInterval : function (id) { g.clearInterval(id); };
    var st = { grande: false, salva: false, fondo: false, reloj: false };
    var el = null, hora = null, dia = null, intervalo = null, ultimo = '';

    function asegurarReloj() {
      if (el || !doc || typeof doc.createElement !== 'function' || !raiz) return el;
      el = doc.createElement('div');
      el.id = 'lune-reloj';
      el.className = 'lune-reloj';
      if (typeof el.setAttribute === 'function') el.setAttribute('aria-hidden', 'true');
      hora = doc.createElement('span'); hora.className = 'hora';
      dia = doc.createElement('span'); dia.className = 'dia';
      el.appendChild(hora); el.appendChild(dia);
      raiz.appendChild(el);
      return el;
    }

    function pintar() {
      var d = ahora();
      if (!d || typeof d.getHours !== 'function') return;
      var h = horaTexto(d), t = h + '|' + diaTexto(d);
      if (t === ultimo) return;
      ultimo = t;
      if (hora) hora.textContent = h;
      if (dia) dia.textContent = diaTexto(d);
    }

    function relojOn(on) {
      if (on) {
        asegurarReloj();
        ultimo = '';
        pintar();
        clase(el, 'on', true);
        if (intervalo === null) intervalo = cadaSeg(pintar, 1000);
      } else {
        clase(el, 'on', false);
        if (intervalo !== null) { try { pararSeg(intervalo); } catch (e) { /* sigue */ } intervalo = null; }
      }
    }

    function fase(f) {
      var k = String(f == null ? '' : f).toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(FASES_GRANDE, k)) return st.grande;
      var v = FASES_GRANDE[k];
      if (v === null) return st.grande;                // glide: la ventana aún es la pequeña
      st.grande = v;
      clase(raiz, 'lune-grande', v);
      return st.grande;
    }

    function salvapantallas(on, o) {
      o = o || {};
      on = !!on;
      st.salva = on;
      st.fondo = on && o.fondo !== false;
      st.reloj = on && o.reloj !== false;
      clase(raiz, 'lune-salva', on);
      clase(raiz, 'lune-salva-fondo', st.fondo);
      relojOn(st.reloj);
      return on;
    }

    return {
      fase: fase, salvapantallas: salvapantallas,
      estado: function () {
        return { grande: st.grande, salva: st.salva, fondo: st.fondo, reloj: st.reloj, hora: hora ? hora.textContent : '' };
      },
    };
  }

  g.LunePantalla = { crear: crear, horaTexto: horaTexto, diaTexto: diaTexto };
})(typeof globalThis !== 'undefined' ? globalThis : this);
