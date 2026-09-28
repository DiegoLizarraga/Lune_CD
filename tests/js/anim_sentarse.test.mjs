// tests/js/anim_sentarse.test.mjs — la mascota ANIMADA «apoyada» en el borde
// (ui_web/anim/lune_anim_sentarse.js, corte 7, decisión D2): la clase .lune-sentada y
// data-sentada en el #stage por el registro (el módulo NO escribe style.transform),
// est.sentada, y el punto de asiento = centro de abajo del #stage (luneSeatPx) con el
// DOM falso. Al final, la página (companion.html).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { instalar, puntos, modoValido, NOMBRE, ORDEN, CLASE } from '../../ui_web/anim/lune_anim_sentarse.js';
import { crearElemento, crearDocumento } from './dom_falso.mjs';

const UI = new URL('../../ui_web/', import.meta.url);

/** Elemento falso con un rect (el #stage de 210×290 dentro de una ventana de 240×430). */
function conRect(el, r = { left: 15, top: 132, width: 210, height: 290 }) {
  el.getBoundingClientRect = () => ({ ...r, right: r.left + r.width, bottom: r.top + r.height });
  return el;
}

test('puntos(): asiento = sonda = centro de abajo del #stage; sin rect o sin tamaño, null', () => {
  assert.equal(NOMBRE, 'sentarseAnim');
  assert.equal(ORDEN, 85);
  assert.equal(CLASE, 'lune-sentada');
  const st = conRect(crearElemento('div', 'stage'));
  assert.deepEqual(puntos(st), { asiento: { x: 120, y: 422 }, sonda: { x: 120, y: 422 } });
  assert.equal(puntos(crearElemento('div')), null);
  assert.equal(puntos(conRect(crearElemento('div'), { left: 0, top: 0, width: 0, height: 10 })), null);
  assert.equal(puntos(null), null);
  assert.equal(modoValido('VENTANA'), 'ventana');
  assert.equal(modoValido('suelo'), null);
});

test('el registro: la clase y data-sentada en el #stage, est.sentada y NINGUNA escritura en style', () => {
  const escrituras = [];
  const stage = conRect(crearElemento('div', 'stage'));
  stage.style = new Proxy({}, { set(o, k, v) { escrituras.push(k); o[k] = v; return true; } });
  const eventos = [];
  let ms = 0;
  const reg = crearRegistroAnim({ stage, raf: () => 0, caf: () => {}, ahora: () => ms, emitir: (t, d) => eventos.push([t, d]) });
  const mod = reg.registrar(instalar);
  const p = mod.api.sentar('barra', 3);
  assert.deepEqual(p, puntos(stage));
  assert.equal(stage.classList.contains('lune-sentada'), true);
  assert.equal(stage.getAttribute('data-sentada'), 'barra');
  assert.equal(reg.est.sentada, 'barra');
  assert.deepEqual(mod.api.estado(), { sentada: 'barra', variante: 0 }, 'la barra no tiene variantes');
  for (let i = 0; i < 30; i++) { ms += 16; reg.paso(ms); }
  assert.ok(escrituras.every((k) => ['transform', 'transformOrigin', 'filter', 'opacity'].includes(k)), 'solo el registro escribe');
  assert.equal(stage.style.transform, '', 'sentada no añade piezas: ni giro ni desplazamiento');
  const n = escrituras.length;
  for (let i = 0; i < 10; i++) { ms += 16; reg.paso(ms); }
  assert.equal(escrituras.length, n, 'nada cambia frame a frame');
  mod.api.sentar('ventana', 2);
  assert.equal(stage.getAttribute('data-sentada'), 'ventana');
  assert.deepEqual(eventos.map(([t, d]) => [t, d.modo]), [['sentada', 'barra'], ['sentada', 'ventana']]);
  mod.api.sentar('ventana', 2);                       // igual: sin evento nuevo
  assert.equal(eventos.length, 2);
  assert.equal(mod.api.sentar('patata'), null, 'modo desconocido: se levanta');
  assert.equal(stage.classList.contains('lune-sentada'), false);
  assert.equal(stage.getAttribute('data-sentada'), null);
  assert.equal(reg.est.sentada, false);
  assert.equal(mod.api.levantar(), false, 'ya de pie');
  assert.deepEqual(mod.api.puntos(), puntos(stage));
});

test('companion.html: luneSentar/luneSeatPx antes y después del módulo; se registra al usarse', async () => {
  globalThis.window = globalThis;
  globalThis.requestAnimationFrame = () => 0;
  globalThis.cancelAnimationFrame = () => {};
  const body = crearElemento('body');
  body.appendChild(crearElemento('div', 'bubble')).appendChild(crearElemento('span', 'btxt'));
  const stage = conRect(body.appendChild(crearElemento('div', 'stage')));
  stage.appendChild(crearElemento('video', 'v'));
  const doc = crearDocumento(body);
  doc.body = body;
  stage.ownerDocument = doc;
  globalThis.document = doc;
  const html = readFileSync(new URL('companion.html', UI), 'utf8');
  assert.ok(html.includes('href="css/sentarse.css"'));
  assert.ok(html.includes("import('./anim/lune_anim_sentarse.js').catch("), 'módulo opcional');
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter((m) => !/\bsrc=/.test(m[1]) && m[2].trim()).map((m) => m[2]);
  assert.equal(scripts.length, 2);
  vm.runInThisContext(scripts[0], { filename: 'companion.html' });
  assert.deepEqual(JSON.parse(globalThis.luneSeatPx()), puntos(stage), 'el punto ya se sabe (el #stage)');
  assert.equal(globalThis.luneSentar('ventana', 1), 'null', 'pendiente');
  const base = new URL('companion.html', UI);
  const codigo = scripts[1].replace(/from\s+'(\.[^']+)'/g, (m, esp) => `from '${new URL(esp, base).href}'`)
    .replace(/import\(\s*'(\.[^']+)'\s*\)/g, (m, esp) => `import('${new URL(esp, base).href}')`);
  await import('data:text/javascript;base64,' + Buffer.from(codigo + '\n// sentarse', 'utf8').toString('base64'));
  const reg = globalThis.luneAnim;
  try {
    assert.equal(globalThis.__luneVidaPendiente, null);
    assert.ok(reg.lista().includes('sentarseAnim'), 'registrado al repetir lo pendiente');
    assert.equal(stage.classList.contains('lune-sentada'), true);
    assert.equal(reg.est.sentada, 'ventana');
    assert.deepEqual(JSON.parse(globalThis.luneSentar('barra', 0)), puntos(stage));
    assert.deepEqual(JSON.parse(globalThis.luneSeatPx()), puntos(stage));
    assert.equal(globalThis.luneSentar(null), 'null');
    assert.equal(stage.classList.contains('lune-sentada'), false);
  } finally {
    globalThis.luneSetFPS(0);
  }
});
