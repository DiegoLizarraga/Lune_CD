/*
 * ui_web/tema.js — Tema de color de Lune en la página (script clásico).
 *
 * La fórmula (ThemeManager.Adjust de Mate-Engine: rotar el tono y escalar la
 * saturación en HSV) se calcula UNA vez en Python (nucleo/tema.py). Aquí solo se
 * aplica su resultado: un mapa de variables CSS que pisa los tokens de
 * tokens/colors.css en <html> (estilo en línea, gana a :root):
 *
 *   window.luneTema({"--cyan-500": "#FE00FF", "--cyan-500-rgb": "254 0 255", …})
 *   window.luneTema('{"--cyan-500": …}')     // también como texto JSON
 *   window.luneTema(null)                     // quita el tema: vuelve el cian
 *
 * Los CSS usan esos tokens directamente (var(--cyan-500)) o sus canales con alfa
 * (rgb(var(--cyan-500-rgb, 0 229 255) / .5)), así que todo se recolorea sin
 * filter: hue-rotate (que teñiría también a la mascota y costaría GPU).
 *
 * Lista blanca: solo --cyan-*, --blue-*, --yellow-* e --ink-* (con o sin -rgb);
 * los hex tienen que ser #RGB, #RRGGBB o #RRGGBBAA y los canales "R G B" (0–255).
 * Lo demás se ignora. Cada llamada quita primero lo que puso la anterior.
 * Devuelve cuántas variables aplicó (-1 si el texto no era JSON: no toca nada).
 * La usan index.html (vía window.luneEscritorio) y las dos páginas de la mascota
 * (ui/companion.py → aplicar_tema).
 */
(function (w) {
  'use strict';

  var NOMBRE = /^--(?:cyan|blue|yellow|ink)-\d{2,3}(?:-rgb)?$/;
  var HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
  var CANAL = /^(\d{1,3}) (\d{1,3}) (\d{1,3})$/;
  var MAXIMO = 96;              // variables por llamada (hoy son ≤ 46)
  var puestas = [];

  function estiloRaiz() {
    var d = w.document;
    var r = d && d.documentElement;
    return r && r.style && typeof r.style.setProperty === 'function' ? r.style : null;
  }

  function valorValido(nombre, valor) {
    if (typeof valor !== 'string') return false;
    if (/-rgb$/.test(nombre)) {
      var m = CANAL.exec(valor);
      return !!m && +m[1] <= 255 && +m[2] <= 255 && +m[3] <= 255;
    }
    return HEX.test(valor);
  }

  function quitar(estilo) {
    for (var i = 0; i < puestas.length; i++) {
      try { estilo.removeProperty(puestas[i]); } catch (e) { /* sigue */ }
    }
    puestas = [];
  }

  function luneTema(entrada) {
    var mapa = entrada;
    if (typeof mapa === 'string') {
      try { mapa = JSON.parse(mapa); } catch (e) { return -1; }
    }
    var estilo = estiloRaiz();
    if (!estilo) return 0;
    quitar(estilo);
    if (!mapa || typeof mapa !== 'object' || Array.isArray(mapa)) return 0;
    var claves = Object.keys(mapa);
    var n = 0;
    for (var i = 0; i < claves.length && n < MAXIMO; i++) {
      var k = claves[i];
      var v = mapa[k];
      if (typeof v === 'string') v = v.trim();
      if (!NOMBRE.test(k) || !valorValido(k, v)) continue;
      estilo.setProperty(k, v);
      puestas.push(k);
      n++;
    }
    return n;
  }

  /** Variables que puso la última llamada (para depurar y para los tests). */
  luneTema.puestas = function () { return puestas.slice(); };

  w.luneTema = luneTema;
})(typeof window !== 'undefined' ? window : globalThis);
