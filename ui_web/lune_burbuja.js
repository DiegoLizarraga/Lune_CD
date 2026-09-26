/*
 * ui_web/lune_burbuja.js — burbuja de diálogo de la mascota: máquina de escribir,
 * texto en streaming, cierre automático y lado espejado.
 *
 * Para qué sirve: companion.html (animada) y companion_vrm.html (3D) tienen una
 * burbuja #bubble con el texto en #btxt. Este script añade lo que les faltaba para
 * el chat en la burbuja, las alarmas y las reacciones:
 *
 *   comentarTipeado(texto, cps=25, ms)  escribe letra a letra (pausas en la
 *                                       puntuación) y luego se oculta como burbujaFin(ms)
 *   burbujaTexto(texto)                 pone el texto tal cual y NO programa el cierre
 *                                       (Python la llama con cada trozo del streaming)
 *   burbujaFin(ms)                      oculta a los `ms`; sin ms, a max(8 s, 1 s por cada
 *                                       15 caracteres). Si aún está escribiendo, espera.
 *   luneLado('izq'|'der'|null)          burbuja espejada (pegada a ese lado) cuando la
 *                                       mascota está junto al borde de la pantalla
 *
 * Modo streaming: burbujaTexto y comentarTipeado ponen la clase .stream en #bubble;
 * con ella (css/burbuja.css) el texto tiene alto máximo y se ve el FINAL (el scroll
 * baja con cada trozo). comentar() y pensando() la quitan: se ven enteros y desde el
 * principio, como siempre.
 *
 * Boca: mientras escribe llama a luneBurbuja.onBoca(true) y al acabar onBoca(false),
 * para que la página mueva la boca (p. ej. mascota.setHablando). Si suena la voz
 * (luneBurbuja.setVoz(true)) la boca es de la voz y el tecleo no la toca.
 *
 * Compatibilidad: window.comentar(t, ms=14000), window.pensando() y
 * window.ocultarBurbuja() se redefinen con el mismo comportamiento que tienen hoy en
 * las páginas, pero compartiendo el temporizador con lo nuevo (así un cierre viejo no
 * corta una escritura nueva). Si la página las define después de cargar este script,
 * siguen funcionando igual; luneBurbuja.instalarCompat() vuelve a poner estas.
 *
 * Script clásico: <script src="lune_burbuja.js"> + <link rel="stylesheet" href="css/burbuja.css">.
 */
(function (w) {
  'use strict';

  var CPS_DEFECTO = 25;
  var MS_COMENTAR = 14000;        // lo que ya usaban las páginas
  var MIN_FIN_MS = 8000;
  var CARACTERES_POR_S = 15;
  var PAUSAS = { '.': 6, '!': 6, '?': 6, '…': 6, ',': 3, ';': 3, ':': 3, '\n': 4 };

  var el = { bub: null, txt: null };
  var tTecleo = null, tFin = null;
  var escribiendo = false, finPendiente = null;   // burbujaFin llegó mientras escribía
  var escrito = '';               // lo último que puso este script en #btxt
  var bocaTecleo = false, voz = false;
  var alTerminar = null;
  var enStream = false;           // streaming/máquina de escribir: alto máximo y el final a la vista

  function doc() { return w.document || null; }

  function elementos() {
    var d = doc();
    if (!d) return false;
    if (!el.bub || el.bub.isConnected === false) el.bub = d.getElementById('bubble');
    if (!el.txt || el.txt.isConnected === false) el.txt = d.getElementById('btxt');
    return !!(el.bub && el.txt);
  }

  function clase(nombre, on) {
    if (!el.bub || !el.bub.classList) return;
    if (on) el.bub.classList.add(nombre); else el.bub.classList.remove(nombre);
  }

  function poner(texto) {
    if (!elementos()) return;
    el.txt.textContent = texto;
    escrito = texto;
    // En streaming #btxt tiene alto máximo (burbuja.css): se ve el final del texto.
    // Fuera de él no hay recorte y el texto se lee desde el principio.
    try { el.txt.scrollTop = enStream ? (el.txt.scrollHeight || 0) : 0; } catch (e) { /* sin layout */ }
  }

  function modoStream(on) {
    enStream = !!on;
    clase('stream', enStream);
  }

  // La clase va ANTES del texto: con el alto máximo ya aplicado, el scroll al
  // final funciona (sin él, scrollTop se quedaría en 0).
  function mostrar(texto, stream) {
    if (!elementos()) return;
    modoStream(stream);
    poner(texto);
    clase('on', true);
  }

  function llamarBoca(on) {
    var api = w.luneBurbuja;
    var f = api && api.onBoca;
    if (typeof f !== 'function') return;
    try { f(!!on); } catch (e) { /* la página no debe romper la burbuja */ }
  }

  function setBocaTecleo(on) {
    if (bocaTecleo === on) return;
    bocaTecleo = on;
    if (!voz) llamarBoca(on);
  }

  function setVoz(on) {
    on = !!on;
    if (voz === on) return;
    voz = on;
    // Acabó la voz y aún escribe: la boca vuelve al tecleo.
    if (!on && bocaTecleo) llamarBoca(true);
  }

  function pararTecleo() {
    if (tTecleo !== null) { clearTimeout(tTecleo); tTecleo = null; }
    if (escribiendo) {
      escribiendo = false;
      clase('tipeando', false);
      setBocaTecleo(false);
    }
    finPendiente = null;
    alTerminar = null;
  }

  function pararFin() {
    if (tFin !== null) { clearTimeout(tFin); tFin = null; }
  }

  function ocultar() {
    pararTecleo();
    pararFin();
    if (elementos()) clase('on', false);
  }

  function msPorDefecto(texto) {
    var n = Array.from(String(texto || '')).length;
    return Math.max(MIN_FIN_MS, Math.round(n * 1000 / CARACTERES_POR_S));
  }

  // Programa el cierre. Solo oculta si el texto sigue siendo el que puso este
  // script: si otra función escribió en la burbuja, el cierre es suyo.
  function programarFin(ms, texto) {
    pararFin();
    var espera = Number(ms);
    if (!Number.isFinite(espera) || espera <= 0) espera = msPorDefecto(texto);
    var propio = escrito;
    tFin = setTimeout(function () {
      tFin = null;
      if (!elementos()) return;
      if (el.txt.textContent !== propio) return;
      clase('on', false);
    }, espera);
  }

  function comentarTipeado(texto, cps, ms, opciones) {
    var t = texto == null ? '' : String(texto);
    if (!t.trim()) return;
    ocultar();
    if (!elementos()) return;
    var o = opciones || {};
    var v = Number(cps);
    v = Number.isFinite(v) && v > 0 ? Math.min(400, Math.max(1, v)) : CPS_DEFECTO;
    var letras = Array.from(t);                  // emojis y acentos compuestos enteros
    var porLetra = 1000 / v;
    var lote = porLetra < 16 ? Math.ceil(16 / porLetra) : 1;   // a mucha velocidad, varias por tick
    var i = 0;
    alTerminar = typeof o.alTerminar === 'function' ? o.alTerminar : null;
    finPendiente = ms;
    escribiendo = true;
    mostrar('', true);          // máquina de escribir: modo streaming
    clase('tipeando', true);
    setBocaTecleo(true);

    function paso() {
      tTecleo = null;
      // Otra función cambió el texto (comentar de la página, un aviso): se rinde.
      if (!elementos() || el.txt.textContent !== escrito) { pararTecleo(); return; }
      var hasta = Math.min(letras.length, i + lote);
      var ultima = letras[hasta - 1];
      i = hasta;
      poner(letras.slice(0, i).join(''));
      if (i >= letras.length) {
        var fin = finPendiente, cb = alTerminar;
        escribiendo = false;
        finPendiente = null;
        alTerminar = null;
        clase('tipeando', false);
        setBocaTecleo(false);
        programarFin(fin, t);
        if (cb) { try { cb(); } catch (e) { /* callback de la página */ } }
        return;
      }
      tTecleo = setTimeout(paso, Math.max(1, porLetra * lote * (PAUSAS[ultima] || 1)));
    }
    tTecleo = setTimeout(paso, Math.max(1, porLetra * lote));
  }

  function burbujaTexto(texto) {
    var t = texto == null ? '' : String(texto);
    if (!t) return;
    pararTecleo();
    pararFin();
    mostrar(t, true);           // trozo del streaming
  }

  function burbujaFin(ms) {
    if (escribiendo) { finPendiente = ms; return; }   // se aplica al acabar de escribir
    if (!elementos()) return;
    programarFin(ms, el.txt.textContent);
  }

  function luneLado(lado) {
    if (!elementos()) return;
    if (lado === 'izq' || lado === 'der') el.bub.setAttribute('data-lado', lado);
    else el.bub.removeAttribute('data-lado');
  }

  // ── Compatibilidad con las funciones que ya usan Python y las páginas ─────────
  function comentar(t, ms) {
    if (!t || !elementos()) return;
    pararTecleo();
    mostrar(String(t), false);  // entera y desde el principio
    programarFin(ms || MS_COMENTAR, String(t));
  }

  function pensando() {
    if (!elementos()) return;
    pararTecleo();
    pararFin();
    mostrar('…', false);
  }

  function instalarCompat() {
    w.comentar = comentar;
    w.pensando = pensando;
    w.ocultarBurbuja = ocultar;
  }

  w.comentarTipeado = comentarTipeado;
  w.burbujaTexto = burbujaTexto;
  w.burbujaFin = burbujaFin;
  w.luneLado = luneLado;
  instalarCompat();

  w.luneBurbuja = {
    comentarTipeado: comentarTipeado,
    texto: burbujaTexto,
    fin: burbujaFin,
    lado: luneLado,
    ocultar: ocultar,
    comentar: comentar,
    pensando: pensando,
    setVoz: setVoz,
    instalarCompat: instalarCompat,
    escribiendo: function () { return escribiendo; },
    msPorDefecto: msPorDefecto,
    onBoca: (w.luneBurbuja && w.luneBurbuja.onBoca) || null,
  };
})(typeof window !== 'undefined' ? window : globalThis);
