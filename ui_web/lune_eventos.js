/*
 * ui_web/lune_eventos.js — cola de eventos de la página hacia Python (sin QWebChannel).
 *
 * Para qué sirve: la asistente (VRM o animada) necesita avisar a Python de cosas que
 * pasan en la página aunque el cursor esté lejos (caricia, arrastre, dormir, fin de
 * un baile, fase de pantalla grande, error…). La página las encola aquí y Python
 * las recoge sondeando `luneEventos()` con runJavaScript a 10-15 Hz, en un
 * temporizador propio que no depende de dónde esté el cursor.
 *
 * Script clásico (no módulo): se incluye con <script src="lune_eventos.js"> en
 * companion.html y companion_vrm.html, y también lo pueden usar módulos ES.
 *
 * API:
 *   window.luneEmitir(tipo, datos)   encola {t: tipo, d: datos, ts: ms}; datos se copia
 *                                    como JSON en el momento (undefined → null)
 *   window.luneEventos()             → JSON (string) con los más antiguos, como mucho 50
 *                                    por llamada; los quita de la cola
 *   window.luneEventos.emitir        el mismo emitir, por comodidad
 *   window.luneEventos.pendientes()  → cuántos quedan
 *   window.__luneEventos             la cola (array); otros scripts pueden hacer push
 *                                    directamente con el mismo formato
 *   window.__luneEventosPerdidos     cuántos se descartaron por desbordamiento
 *
 * Si la cola pasa de 200 (Python no sondea, página congelada), se descartan los más
 * viejos. Cargar el script dos veces no vacía la cola.
 */
(function (w) {
  'use strict';

  var MAX_COLA = 200;
  var MAX_VACIADO = 50;

  if (!Array.isArray(w.__luneEventos)) w.__luneEventos = [];
  if (typeof w.__luneEventosPerdidos !== 'number') w.__luneEventosPerdidos = 0;

  function cola() {
    if (!Array.isArray(w.__luneEventos)) w.__luneEventos = [];
    return w.__luneEventos;
  }

  // Descarta los más viejos si sobran; en sitio, por si alguien guarda la referencia.
  function recortar(c) {
    var sobra = c.length - MAX_COLA;
    if (sobra > 0) {
      c.splice(0, sobra);
      w.__luneEventosPerdidos += sobra;
    }
  }

  // Copia JSON de los datos: congela su valor al emitir y evita referencias
  // circulares o funciones que romperían el JSON.stringify del vaciado.
  function copiar(d) {
    if (d === undefined) return null;
    try {
      var s = JSON.stringify(d);
      return s === undefined ? null : JSON.parse(s);
    } catch (e) {
      try { return String(d); } catch (e2) { return null; }
    }
  }

  function emitir(tipo, datos) {
    if (tipo === undefined || tipo === null || tipo === '') return false;
    var c = cola();
    c.push({ t: String(tipo), d: copiar(datos), ts: Date.now() });
    recortar(c);
    return true;
  }

  // Serializa un lote; si algún evento que otro script empujó a mano no se deja
  // convertir, se sanea uno por uno en vez de perder todo el lote.
  function serializar(lote) {
    try {
      return JSON.stringify(lote);
    } catch (e) {
      return JSON.stringify(lote.map(function (ev) {
        var o = ev && typeof ev === 'object' ? ev : { t: String(ev) };
        return { t: String(o.t), d: copiar(o.d), ts: typeof o.ts === 'number' ? o.ts : Date.now() };
      }));
    }
  }

  function luneEventos() {
    var c = cola();
    recortar(c);
    if (!c.length) return '[]';
    return serializar(c.splice(0, Math.min(c.length, MAX_VACIADO)));
  }

  luneEventos.emitir = emitir;
  luneEventos.pendientes = function () { return cola().length; };
  luneEventos.MAX_COLA = MAX_COLA;
  luneEventos.MAX_VACIADO = MAX_VACIADO;

  w.luneEmitir = emitir;
  w.luneEventos = luneEventos;
})(typeof window !== 'undefined' ? window : globalThis);
