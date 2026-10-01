/*
 * ui_web/lune_reposo.js — «Lune en reposo» en la ventana web (11.2, script clásico).
 *
 * En QtWebEngine dentro de un QWidget, CADA frame que produce Chromium pasa por Qt (y en
 * ventanas translúcidas se copia de la GPU a la CPU). Una animación infinita, por pequeña que
 * sea (el fondo, las nubes del tema Nube, el LED de «Listo»), obliga a 60 frames por segundo y
 * cuesta de 1 a 3 núcleos con la ventana a la vista aunque nadie la use. Aquí se decide cuándo
 * Lune se queda quieta:
 *   · sin foco 20 s: ui/web_shell.py avisa con window.luneFoco(true|false) al activarse o no
 *     la ventana, al enseñarla, al ocultarla y al cargar la página (y el blur/focus de window
 *     cuentan igual);
 *   · con foco pero sin tocar nada (pointermove, pointerdown, keydown, wheel, touchstart) 90 s.
 * Entonces <body> lleva la clase `lune-quieta` (index.html: animation-play-state: paused en
 * todo, sin saltos) y se avisa a quien escuche (suscribir) y con el evento de window
 * 'lune-quieta' ({detail: bool}): app.jsx se lo pasa a la barra, que pausa el vídeo y deja el
 * avatar 3D a 0 fps. Cualquier entrada, recuperar el foco o que Lune esté ocupada
 * (ocupada('escribiendo'|'hablando'|…, true): lo pone app.jsx; la alarma que suena la mira
 * este archivo en window.luneAlarmas) la quitan al momento, y al volver todo sigue donde estaba.
 *
 * Lo que aparezca mientras está quieta (un aviso, un modal que manda Python) se ve ya en su
 * estado final: sus animaciones finitas se terminan (finish) en vez de quedarse en pausa en el
 * primer fotograma, invisibles. Las infinitas nuevas siguen en pausa.
 *
 * Con efectos.pausar_sin_foco = false (Ajustes → Efectos visuales → «Quedarme quieta cuando no
 * me usas») nunca se queda quieta: LuneReposo.activar(false).
 *
 * API: window.luneFoco(bool) · window.LuneReposo = instancia de la página con
 *   activar(bool) · foco(bool) · ocupada(motivo, bool) · despertar() · quieta() → bool ·
 *   suscribir(fn(bool)) → quitar · estado() → {activo, foco, quieta, ocupadas} · destruir()
 *   y además LuneReposo.crear(opciones) (los tests: tests/js/reposo.test.mjs) y TIEMPOS.
 * opciones de crear: win, doc, setTimeout, clearTimeout, ahora() → ms, MutationObserver,
 *   sinFocoMs, sinUsoMs, activo, foco.
 */
(function (g) {
  'use strict';

  var TIEMPOS = { sinFocoMs: 20000, sinUsoMs: 90000 };
  var ENTRADAS = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart'];
  var CLASE = 'lune-quieta';

  function num(v, d) { return typeof v === 'number' && isFinite(v) && v >= 0 ? v : d; }

  /** Las animaciones finitas de `n` y sus hijos (y de sus ::before/::after) acaban ya. */
  function terminarAnimaciones(n) {
    if (!n || n.nodeType !== 1 || typeof n.getAnimations !== 'function') return 0;
    var lista;
    try { lista = n.getAnimations({ subtree: true }); } catch (e) { return 0; }
    var hechas = 0;
    for (var i = 0; i < lista.length; i++) {
      var a = lista[i];
      try {
        var vueltas = a.effect && typeof a.effect.getTiming === 'function' ? a.effect.getTiming().iterations : 1;
        if (vueltas === Infinity) continue;
        a.finish();
        hechas++;
      } catch (e) { /* sigue con las demás */ }
    }
    return hechas;
  }

  function crear(o) {
    o = o || {};
    var win = o.win || g;
    var doc = o.doc || (win && win.document) || null;
    var ponerT = typeof o.setTimeout === 'function' ? o.setTimeout : function (f, ms) { return win.setTimeout(f, ms); };
    var quitarT = typeof o.clearTimeout === 'function' ? o.clearTimeout : function (id) { win.clearTimeout(id); };
    var reloj = typeof o.ahora === 'function' ? o.ahora : function () { return Date.now(); };
    var Observador = o.MutationObserver || (win && win.MutationObserver) || null;
    var t = { sinFocoMs: num(o.sinFocoMs, TIEMPOS.sinFocoMs), sinUsoMs: num(o.sinUsoMs, TIEMPOS.sinUsoMs) };

    var activo = o.activo !== false;
    var foco = o.foco !== undefined ? !!o.foco
      : (doc && typeof doc.hasFocus === 'function' ? !!doc.hasFocus() : true);
    var quieta = false;
    var timer = null;
    var desde = reloj();               // última entrada, cambio de foco o fin de lo que la tenía ocupada
    var ocupadas = {};
    var nOcupadas = 0;
    var oyentes = [];
    var observador = null;
    var quitarOyentes = [];

    function cuerpo() { return doc && doc.body ? doc.body : null; }

    function ponerClase(on) {
      var b = cuerpo();
      if (!b || !b.classList) return;
      try { if (on) b.classList.add(CLASE); else b.classList.remove(CLASE); } catch (e) { /* sin clases */ }
    }

    function avisar() {
      var copia = oyentes.slice();
      for (var i = 0; i < copia.length; i++) {
        try { copia[i](quieta); } catch (e) { /* un oyente roto no corta al resto */ }
      }
      try {
        if (win && typeof win.dispatchEvent === 'function' && typeof win.CustomEvent === 'function') {
          win.dispatchEvent(new win.CustomEvent('lune-quieta', { detail: quieta }));
        }
      } catch (e) { /* sin eventos */ }
    }

    // Lo que se añade al DOM mientras está quieta: sus entradas (toast, modal…) acaban ya.
    function alMutar(registros) {
      for (var i = 0; i < registros.length; i++) {
        var nuevos = registros[i].addedNodes || [];
        for (var j = 0; j < nuevos.length; j++) terminarAnimaciones(nuevos[j]);
      }
    }
    function observar(on) {
      if (!on) {
        if (observador) { try { observador.disconnect(); } catch (e) { /* ya estaba */ } }
        observador = null;
        return;
      }
      var b = cuerpo();
      if (observador || !b || typeof Observador !== 'function') return;
      try {
        observador = new Observador(alMutar);
        observador.observe(b, { childList: true, subtree: true });
      } catch (e) { observador = null; }
    }

    function limite() { return foco ? t.sinUsoMs : t.sinFocoMs; }

    function pararTimer() {
      if (timer !== null) { try { quitarT(timer); } catch (e) { /* ya salió */ } }
      timer = null;
    }

    function programar() {
      pararTimer();
      if (!activo || nOcupadas || quieta) return;
      timer = ponerT(vencer, Math.max(0, desde + limite() - reloj()));
    }

    // Una entrada no reprograma nada (pointermove llega sin parar): solo mueve `desde`. Al
    // vencer se mira cuánto falta de verdad y, si hubo entradas, se vuelve a esperar lo que quede.
    function vencer() {
      timer = null;
      if (!activo || nOcupadas || quieta) return;
      var falta = desde + limite() - reloj();
      if (falta > 0) { timer = ponerT(vencer, falta); return; }
      quieta = true;
      ponerClase(true);
      observar(true);
      avisar();
    }

    function salir() {
      if (!quieta) return;
      quieta = false;
      ponerClase(false);
      observar(false);
      avisar();
    }

    function despertar() {
      desde = reloj();
      salir();
      programar();
      return quieta;
    }

    function entrada() {
      desde = reloj();
      if (quieta) { salir(); programar(); } else if (timer === null) programar();
    }

    function ponerFoco(on) {
      on = !!on;
      var cambio = on !== foco;
      foco = on;
      if (on) { despertar(); return quieta; }
      if (cambio) { desde = reloj(); programar(); }
      return quieta;
    }

    function ocupada(motivo, on) {
      var k = String(motivo || '');
      if (!k) return nOcupadas > 0;
      if (on) {
        if (!ocupadas[k]) { ocupadas[k] = true; nOcupadas++; }
        pararTimer();
        salir();
      } else if (ocupadas[k]) {
        delete ocupadas[k];
        nOcupadas--;
        if (!nOcupadas) { desde = reloj(); programar(); }
      }
      return nOcupadas > 0;
    }

    function activar(on) {
      activo = on !== false;
      if (!activo) { pararTimer(); salir(); } else { desde = reloj(); programar(); }
      return activo;
    }

    function suscribir(fn) {
      if (typeof fn !== 'function') return function () {};
      oyentes.push(fn);
      return function () { var i = oyentes.indexOf(fn); if (i >= 0) oyentes.splice(i, 1); };
    }

    // Entradas del usuario y foco de la página (además de lo que diga Python con luneFoco).
    function escuchar(nombre, fn) {
      if (!win || typeof win.addEventListener !== 'function') return;
      var opc = { capture: true, passive: true };
      try { win.addEventListener(nombre, fn, opc); } catch (e) { return; }
      quitarOyentes.push(function () { try { win.removeEventListener(nombre, fn, opc); } catch (e) { /* ya no está */ } });
    }
    for (var i = 0; i < ENTRADAS.length; i++) escuchar(ENTRADAS[i], entrada);
    escuchar('focus', function () { ponerFoco(true); });
    escuchar('blur', function () { ponerFoco(false); });

    // La alarma que suena (window.luneAlarmas, cortes 5/6): ocupada mientras suena.
    function cablearAlarmas() {
      var a = win && win.luneAlarmas;
      if (!a) return;
      var conectar = function (senal, fn) {
        var s = a[senal];
        if (!s || typeof s.connect !== 'function') return;
        try { s.connect(fn); } catch (e) { return; }
        quitarOyentes.push(function () { try { s.disconnect(fn); } catch (e) { /* ya no está */ } });
      };
      conectar('alarma_sonando', function () { ocupada('alarma', true); });
      conectar('alarma_apagada', function () { ocupada('alarma', false); });
    }
    if (o.alarmas !== false) {
      if (win && win.luneAlarmas) cablearAlarmas();
      else escuchar('lune-ready', cablearAlarmas);
    }

    programar();

    return {
      activar: activar,
      foco: ponerFoco,
      ocupada: ocupada,
      despertar: despertar,
      quieta: function () { return quieta; },
      suscribir: suscribir,
      estado: function () {
        return { activo: activo, foco: foco, quieta: quieta, ocupadas: Object.keys(ocupadas) };
      },
      destruir: function () {
        pararTimer();
        salir();
        quitarOyentes.splice(0).forEach(function (f) { f(); });
        oyentes = [];
      },
    };
  }

  // La instancia de la página (sin document, como en los tests, no se crea).
  if (g.document) {
    var pagina = crear();
    pagina.crear = crear;
    pagina.TIEMPOS = TIEMPOS;
    pagina.terminarAnimaciones = terminarAnimaciones;
    g.LuneReposo = pagina;
    g.luneFoco = function (on) { return pagina.foco(on); };
  } else {
    g.LuneReposo = { crear: crear, TIEMPOS: TIEMPOS, terminarAnimaciones: terminarAnimaciones };
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
