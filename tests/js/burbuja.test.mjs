// tests/js/burbuja.test.mjs — burbuja de la asistente (ui_web/lune_burbuja.js).
// Script clásico evaluado en un contexto vm con DOM y temporizadores falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const CODIGO = readFileSync(fileURLToPath(new URL('../../ui_web/lune_burbuja.js', import.meta.url)), 'utf8');

function elemento() {
  const clases = new Set();
  const attrs = {};
  return {
    textContent: '', isConnected: true, scrollTop: 0, scrollHeight: 120,
    classList: { add: (c) => clases.add(c), remove: (c) => clases.delete(c), contains: (c) => clases.has(c) },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
  };
}

// Reloj falso: setTimeout/clearTimeout que solo avanzan con avanzar(ms).
function pagina() {
  let ahora = 0, sig = 1;
  const pendientes = new Map();
  const bub = elemento(), txt = elemento();
  const win = {
    document: { getElementById: (id) => (id === 'bubble' ? bub : id === 'btxt' ? txt : null) },
    setTimeout: (fn, ms) => { const id = sig++; pendientes.set(id, { fn, en: ahora + Math.max(0, ms || 0) }); return id; },
    clearTimeout: (id) => { pendientes.delete(id); },
  };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(CODIGO, win, { filename: 'lune_burbuja.js' });
  const avanzar = (ms) => {
    const fin = ahora + ms;
    for (;;) {
      let prox = null;
      for (const [id, p] of pendientes) if (p.en <= fin && (!prox || p.en < prox[1].en || (p.en === prox[1].en && id < prox[0]))) prox = [id, p];
      if (!prox) break;
      pendientes.delete(prox[0]);
      ahora = prox[1].en;
      prox[1].fn();
    }
    ahora = fin;
  };
  const boca = [];
  win.luneBurbuja.onBoca = (on) => boca.push(on);
  return { w: win, bub, txt, avanzar, boca, visible: () => bub.classList.contains('on') };
}

test('comentarTipeado escribe a cps letras por segundo, mueve la boca y cierra a los 8 s', () => {
  const p = pagina();
  p.w.comentarTipeado('Hola', 25);
  assert.equal(p.visible(), true);
  assert.equal(p.txt.textContent, '');
  assert.equal(p.bub.classList.contains('tipeando'), true);
  p.avanzar(40); assert.equal(p.txt.textContent, 'H');
  p.avanzar(40); assert.equal(p.txt.textContent, 'Ho');
  p.avanzar(80); assert.equal(p.txt.textContent, 'Hola');
  assert.equal(p.bub.classList.contains('tipeando'), false);
  assert.deepEqual(p.boca, [true, false]);
  p.avanzar(7999); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
});

test('pausa en la puntuación, ms explícito y emojis como una sola letra', () => {
  const p = pagina();
  p.w.comentarTipeado('a,b🙂', 10, 2000);           // 100 ms por letra; la coma espera ×3
  p.avanzar(100); assert.equal(p.txt.textContent, 'a');
  p.avanzar(100); assert.equal(p.txt.textContent, 'a,');
  p.avanzar(299); assert.equal(p.txt.textContent, 'a,');
  p.avanzar(1); assert.equal(p.txt.textContent, 'a,b');
  p.avanzar(100); assert.equal(p.txt.textContent, 'a,b🙂');
  p.avanzar(1999); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
});

test('burbujaTexto no programa cierre; burbujaFin usa max(8 s, 1 s por 15 caracteres)', () => {
  const p = pagina();
  p.w.burbujaTexto('trozo');
  p.w.burbujaTexto('x'.repeat(300));
  p.avanzar(60000);
  assert.equal(p.visible(), true, 'sin temporizador');
  assert.equal(p.txt.scrollTop, 120, 'baja el scroll al final');
  p.w.burbujaFin();
  p.avanzar(19999); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
  p.w.burbujaTexto('corto');
  p.w.burbujaFin(500);
  p.avanzar(500); assert.equal(p.visible(), false);
  assert.equal(p.w.luneBurbuja.msPorDefecto('abc'), 8000);
});

test('burbujaFin durante la escritura espera a que termine', () => {
  const p = pagina();
  p.w.comentarTipeado('abcd', 20);                   // 50 ms por letra → 200 ms
  p.w.burbujaFin(100);
  p.avanzar(199); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.txt.textContent, 'abcd');
  p.avanzar(99); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
});

test('comentar/pensando/ocultarBurbuja se comportan como antes y comparten temporizador', () => {
  const p = pagina();
  p.w.comentar('');                                   // vacío: no hace nada
  assert.equal(p.visible(), false);
  p.w.comentarTipeado('una frase larga que se está escribiendo', 25);
  p.avanzar(100);
  p.w.comentar('frase fija', 3000);                  // corta la escritura
  assert.equal(p.txt.textContent, 'frase fija');
  assert.equal(p.bub.classList.contains('tipeando'), false);
  assert.deepEqual(p.boca, [true, false]);
  p.avanzar(2999); assert.equal(p.txt.textContent, 'frase fija'); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
  p.w.comentar('sin ms');
  p.avanzar(13999); assert.equal(p.visible(), true);
  p.avanzar(1); assert.equal(p.visible(), false);
  p.w.pensando();
  assert.equal(p.txt.textContent, '…');
  p.avanzar(60000); assert.equal(p.visible(), true);
  p.w.ocultarBurbuja();
  assert.equal(p.visible(), false);
});

test('un cierre viejo no oculta un texto nuevo de otra función', () => {
  const p = pagina();
  p.w.comentar('primero', 1000);
  p.avanzar(500);
  p.txt.textContent = 'otra función escribió';        // p. ej. la página con su propio comentar
  p.avanzar(600);
  assert.equal(p.visible(), true);
});

test('si otro escribe en la burbuja mientras teclea, la escritura se rinde', () => {
  const p = pagina();
  p.w.comentarTipeado('hola mundo', 25);
  p.avanzar(80);
  p.txt.textContent = 'ajeno';
  p.avanzar(1000);
  assert.equal(p.txt.textContent, 'ajeno');
  assert.deepEqual(p.boca, [true, false]);
});

test('con la voz sonando el tecleo no toca la boca; al callar la voz la retoma', () => {
  const p = pagina();
  p.w.luneBurbuja.setVoz(true);
  p.w.comentarTipeado('abcdef', 10);
  p.avanzar(250);
  assert.deepEqual(p.boca, []);
  p.w.luneBurbuja.setVoz(false);
  assert.deepEqual(p.boca, [true]);
  p.avanzar(1000);
  assert.deepEqual(p.boca, [true, false]);
});

test('streaming y máquina de escribir van en modo .stream (se ve el final); comentar/pensando no', () => {
  const p = pagina();
  const stream = () => p.bub.classList.contains('stream');
  p.w.burbujaTexto('trozo largo del streaming');
  assert.equal(stream(), true);
  assert.equal(p.txt.scrollTop, 120, 'el final a la vista');
  // Un comentario normal se lee entero y desde el principio: sin alto máximo ni scroll.
  p.w.comentar('un comentario largo que no debe perder el principio', 3000);
  assert.equal(stream(), false);
  assert.equal(p.txt.scrollTop, 0);
  p.w.comentarTipeado('hola', 25);
  assert.equal(stream(), true);
  p.avanzar(200);
  assert.equal(p.txt.textContent, 'hola');
  assert.equal(p.txt.scrollTop, 120);
  p.w.pensando();
  assert.equal(stream(), false);
  assert.equal(p.txt.scrollTop, 0);
  p.w.burbujaTexto('otra vez');
  assert.equal(stream(), true);
});

test('burbuja.css no pisa el ancho de las páginas y solo recorta en modo .stream', () => {
  const css = readFileSync(fileURLToPath(new URL('../../ui_web/css/burbuja.css', import.meta.url)), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '');                // sin comentarios
  const reglas = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ sel: m[1].trim(), decl: m[2] }));
  assert.ok(reglas.length > 3, 'se leyeron las reglas');
  for (const r of reglas) {
    // El ancho y la caja los define cada página (230 px en la animada, 92 % en la VRM).
    assert.doesNotMatch(r.decl, /\b(max-width|width|box-sizing|padding)\s*:/, r.sel);
    if (/max-height|overflow\s*:/.test(r.decl)) {
      assert.match(r.sel, /\.stream\b/, `alto máximo fuera de .stream: ${r.sel}`);
    }
  }
});

test('luneLado pone data-lado izq/der y lo quita con otro valor', () => {
  const p = pagina();
  p.w.luneLado('der');
  assert.equal(p.bub.getAttribute('data-lado'), 'der');
  p.w.luneLado('izq');
  assert.equal(p.bub.getAttribute('data-lado'), 'izq');
  p.w.luneLado(null);
  assert.equal(p.bub.getAttribute('data-lado'), null);
});

test('sin #bubble en la página no lanza', () => {
  const programados = [];
  const win = { document: { getElementById: () => null }, setTimeout: (fn, ms) => programados.push(ms), clearTimeout: () => {} };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(CODIGO, win);
  win.comentarTipeado('hola');
  win.burbujaTexto('x');
  win.burbujaFin(10);
  win.luneLado('der');
  win.comentar('y');
  win.pensando();
  win.ocultarBurbuja();
  assert.deepEqual(programados, [], 'sin burbuja no deja temporizadores colgando');
});
