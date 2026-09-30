// tests/js/anim_grande.test.mjs — pantalla grande de la asistente animada
// (ui_web/anim/lune_anim_grande.js, cortes 5 y 6) y la página companion.html con las
// funciones nuevas (lo pedido antes de cargar se repite; los módulos van al usarse).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearRegistroAnim } from '../../ui_web/anim/lune_anim_modulos.js';
import { instalar, desplazamiento, NOMBRE, ORDEN, FUERA, TIEMPOS_MS } from '../../ui_web/anim/lune_anim_grande.js';
import { crearElemento, crearDocumento } from './dom_falso.mjs';

const UI = new URL('../../ui_web/', import.meta.url);
const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

test('desplazamiento por fase con smoothstep', () => {
  assert.equal(NOMBRE, 'grandeAnim');
  assert.equal(ORDEN, 60);
  assert.deepEqual({ ...TIEMPOS_MS }, { glide: 400, entrar: 500, salir: 500, volver: 400 });
  assert.deepEqual(desplazamiento('glide', 0), { y: 0, opacidad: 1 });
  assert.deepEqual(desplazamiento('glide', 1), { y: FUERA, opacidad: 1 });
  cerca(desplazamiento('glide', 0.25).y, FUERA * 0.15625, 1e-9, 'smoothstep');
  assert.deepEqual(desplazamiento('entrar', 0), { y: FUERA, opacidad: 0 });
  assert.deepEqual(desplazamiento('entrar', 1), { y: 0, opacidad: 1 });
  cerca(desplazamiento('entrar', 0.5).opacidad, 0.5, 1e-9);
  assert.deepEqual(desplazamiento('salir', 1), { y: FUERA, opacidad: 0 });
  assert.deepEqual(desplazamiento('volver', 0), { y: FUERA, opacidad: 1 });
  assert.deepEqual(desplazamiento('nada', 0.5), { y: 0, opacidad: 1 });
});

function registro() {
  const stage = crearElemento('div', 'stage');
  const eventos = [];
  let ms = 5000;                                     // el registro lleva un rato en marcha
  const reg = crearRegistroAnim({ stage, raf: () => 0, caf: () => {}, ahora: () => ms, emitir: (t, d) => eventos.push([t, d]) });
  reg.paso(ms);
  for (let i = 0; i < 120; i++) { ms += 1000 / 60; reg.paso(ms); }
  const mod = reg.registrar(instalar);
  const correr = (seg, fn = null) => {
    for (let i = 0, n = Math.round(seg * 60); i < n; i++) { ms += 1000 / 60; reg.paso(ms); if (fn) fn(); }
  };
  return { reg, mod, stage, eventos, correr };
}
const bajada = (tr) => { const m = /translate\(0px, (-?[\d.]+)%\)/.exec(String(tr || '')); return m ? Number(m[1]) : 0; };

test('glide → espera fuera → entrar → activa → salir → volver → fin, por el registro', () => {
  const { mod, stage, eventos, correr, reg } = registro();
  assert.equal(mod.api.fase('glide'), true);
  assert.equal(reg.est.grande, true);
  assert.equal(mod.ocupado(reg.est), true);
  const ys = [];
  correr(0.2, () => ys.push(bajada(stage.style.transform)));
  assert.ok(ys[0] < 5, `empieza en su sitio, sin salto (${ys[0]})`);
  cerca(ys[ys.length - 1], FUERA / 2, 12, 'a mitad del planeo');
  correr(0.4);
  cerca(bajada(stage.style.transform), FUERA, 1e-6, 'fuera y ahí se queda');
  correr(1);
  cerca(bajada(stage.style.transform), FUERA, 1e-6);
  mod.api.fase('entrar');
  correr(0.25);
  const op = Number(stage.style.opacity);
  assert.ok(op > 0.3 && op < 0.7, `apareciendo (${op})`);
  correr(0.4);
  assert.equal(stage.style.transform, '', 'activa: sin transformación');
  assert.equal(stage.style.opacity, '');
  assert.equal(mod.ocupado(reg.est), false);
  mod.api.fase('salir');
  correr(0.6);
  cerca(bajada(stage.style.transform), FUERA, 1e-6);
  assert.equal(stage.style.opacity, '0');
  mod.api.fase('volver');
  correr(0.5);
  assert.equal(stage.style.transform, '');
  mod.api.fase('fin');
  assert.equal(reg.est.grande, false);
  correr(0.1);
  assert.equal(stage.style.transform, '');
  assert.deepEqual(eventos.filter(([t]) => t === 'grande_fase').map(([, d]) => d.fase), ['glide', 'entrar', 'salir', 'volver', 'fin']);
  assert.equal(mod.api.fase('otra'), false);
  // fin a mitad: todo en su sitio
  mod.api.fase('glide'); correr(0.2); mod.api.fase('fin'); correr(0.1);   // en reposo el registro va a 15 fps
  assert.equal(stage.style.transform, '');
});

// ── companion.html ────────────────────────────────────────────────────────────

test('companion.html: funciones nuevas antes y después del módulo, lazy y capa happy al bailar', async () => {
  for (const f of ['lune_ritmo.js', 'lune_alarma.js', 'lune_pantalla.js', 'lune_eventos.js']) {
    vm.runInThisContext(readFileSync(new URL(f, UI), 'utf8'), { filename: f });
  }
  globalThis.window = globalThis;
  const frames = [];
  globalThis.requestAnimationFrame = (f) => { frames.push(f); return frames.length; };
  globalThis.cancelAnimationFrame = () => {};
  const body = crearElemento('body');
  body.appendChild(crearElemento('div', 'bubble')).appendChild(crearElemento('span', 'btxt'));
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(crearElemento('video', 'v'));
  const doc = crearDocumento(body);
  doc.body = body;
  stage.ownerDocument = doc;
  globalThis.document = doc;
  const html = readFileSync(new URL('companion.html', UI), 'utf8');
  assert.match(html, /<body class="lune-animada">/);
  const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
    .filter((m) => !/\bsrc=/.test(m[1]) && m[2].trim()).map((m) => ({ modulo: /type="module"/.test(m[1]), codigo: m[2] }));
  assert.equal(scripts.length, 2);
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion.html' });
  for (const fn of ['luneGrande', 'luneHold', 'luneSalvapantallas', 'luneAlarma', 'luneBailar', 'lunePulso']) {
    assert.equal(typeof globalThis[fn], 'function', fn);
  }
  assert.equal(globalThis.luneHold(true, 1, 1), false, 'sujetar el pelo es solo del VRM');
  globalThis.luneBailar(true, { particulas: false });
  globalThis.luneGrande('glide');
  const codigo = scripts[1].codigo.replace(/from\s+'(\.[^']+)'/g, (m, esp) => `from '${new URL(esp, new URL('companion.html', UI)).href}'`)
    .replace(/import\(\s*'(\.[^']+)'\s*\)/g, (m, esp) => `import('${new URL(esp, new URL('companion.html', UI)).href}')`);
  await import('data:text/javascript;base64,' + Buffer.from(codigo, 'utf8').toString('base64'));
  const reg = globalThis.luneAnim;
  try {
    assert.deepEqual(reg.lista(), ['video', 'fisica', 'baileAnim', 'grandeAnim'], 'registrados al repetir lo pendiente');
    assert.equal(globalThis.__luneOcioPendiente, null);
    assert.equal(reg.est.capasEmocion.baile.estado, 'happy', 'clip happy mientras baila');
    assert.equal(reg.est.grande, true);
    globalThis.luneGrande('entrar');
    assert.equal(body.classList.contains('lune-grande'), true, 'el #stage crece por CSS');
    globalThis.luneGrande('fin');
    assert.equal(body.classList.contains('lune-grande'), false);
    assert.equal(reg.est.grande, false);
    assert.equal(globalThis.lunePulso(100, 0.5, 0.7), true);
    globalThis.luneBailar(false);
    assert.equal(reg.est.capasEmocion.baile, undefined);
    globalThis.luneSalvapantallas(true, { fondo: true, reloj: true });
    assert.equal(body.classList.contains('lune-salva-fondo'), true);
    assert.ok(doc.getElementById('lune-reloj'));
    globalThis.luneSalvapantallas(false);
    globalThis.luneAlarma('Pastilla', { retrasoMs: 0, cps: 1000 });
    assert.ok(doc.getElementById('lune-alarma').classList.contains('on'));
    globalThis.luneAlarma(null);
    assert.equal(doc.getElementById('lune-alarma').classList.contains('on'), false);
  } finally {
    globalThis.luneSetFPS(0);
  }
});
