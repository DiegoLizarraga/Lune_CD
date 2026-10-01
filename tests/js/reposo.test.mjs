// tests/js/reposo.test.mjs — «Lune en reposo» (ui_web/lune_reposo.js, 11.2): body.lune-quieta sin foco
// 20 s o sin usarla 90 s; cualquier entrada, el foco o estar ocupada la quitan al momento; lo que
// aparece mientras está quieta acaba sus animaciones finitas. DOM y reloj falsos (dom_falso.mjs).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { crearElemento, crearTemporizador } from './dom_falso.mjs';
import { senal } from './jsx_falso.mjs';

vm.runInThisContext(readFileSync(new URL('../../ui_web/lune_reposo.js', import.meta.url), 'utf8'), { filename: 'lune_reposo.js' });
const { LuneReposo } = globalThis;

function ventanaFalsa(extra = {}) {
  const oyentes = {};
  return Object.assign({
    addEventListener(t, f) { (oyentes[t] = oyentes[t] || []).push(f); },
    removeEventListener(t, f) { oyentes[t] = (oyentes[t] || []).filter((x) => x !== f); },
    dispatchEvent(e) { (oyentes[e.type] || []).slice().forEach((f) => f(e)); return true; },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    disparar(t) { this.dispatchEvent({ type: t }); },
    n: (t) => (oyentes[t] || []).length,
  }, extra);
}

class ObservadorFalso {
  static vivos = [];
  constructor(cb) { this.cb = cb; this.conectado = false; ObservadorFalso.vivos.push(this); }
  observe(nodo, opc) { this.conectado = true; this.nodo = nodo; this.opc = opc; }
  disconnect() { this.conectado = false; }
}

function montar(opc = {}) {
  const t = crearTemporizador();
  const body = crearElemento('body');
  const doc = { body, hasFocus: () => opc.focoInicial !== false };
  const win = ventanaFalsa(opc.win || {});
  const avisos = [];
  win.addEventListener('lune-quieta', (e) => avisos.push(e.detail));
  const r = LuneReposo.crear({
    win, doc, setTimeout: t.setTimeout, clearTimeout: t.clearTimeout, ahora: () => t.ahora,
    MutationObserver: ObservadorFalso, ...(opc.crear || {}),
  });
  return { r, t, body, win, avisos, quieta: () => body.classList.contains('lune-quieta') };
}

test('sin la página (Node) solo publica crear y los tiempos: 20 s sin foco y 90 s sin usarla', () => {
  assert.equal(typeof LuneReposo.crear, 'function');
  assert.deepEqual({ ...LuneReposo.TIEMPOS }, { sinFocoMs: 20000, sinUsoMs: 90000 });
  assert.equal(typeof globalThis.luneFoco, 'undefined', 'luneFoco solo con document');
});

test('con foco: 90 s sin tocar nada → quieta (clase en <body>, evento y suscriptores)', () => {
  const { r, t, avisos, quieta } = montar();
  const vistos = [];
  const quitar = r.suscribir((q) => vistos.push(q));
  t.avanzar(89000);
  assert.equal(quieta(), false);
  t.avanzar(1000);
  assert.equal(quieta(), true);
  assert.equal(r.quieta(), true);
  assert.deepEqual(avisos, [true]);
  assert.deepEqual(vistos, [true]);
  quitar();
  r.despertar();
  assert.deepEqual(vistos, [true], 'ya no escucha');
  assert.deepEqual(avisos, [true, false]);
});

test('sin foco: a los 20 s; recuperar el foco la despierta y cuenta otra vez 90 s', () => {
  const { r, t, quieta } = montar();
  t.avanzar(30000);
  r.foco(false);
  t.avanzar(19000);
  assert.equal(quieta(), false, 'la cuenta sin foco empieza al perderlo');
  t.avanzar(1000);
  assert.equal(quieta(), true);
  r.foco(true);
  assert.equal(quieta(), false, 'al momento');
  t.avanzar(89000);
  assert.equal(quieta(), false);
  t.avanzar(1000);
  assert.equal(quieta(), true);
});

test('luneFoco(false) repetido no reinicia la cuenta', () => {
  const { r, t, quieta } = montar();
  r.foco(false);
  t.avanzar(15000);
  r.foco(false);
  t.avanzar(5000);
  assert.equal(quieta(), true);
});

test('cualquier entrada (pointermove, pointerdown, keydown, wheel, touchstart) aplaza y despierta', () => {
  const { t, win, quieta } = montar();
  for (const e of ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart']) assert.equal(win.n(e), 1, e);
  t.avanzar(60000);
  win.disparar('pointermove');
  t.avanzar(89000);
  assert.equal(quieta(), false, 'cuenta desde la última entrada');
  t.avanzar(1000);
  assert.equal(quieta(), true);
  win.disparar('keydown');
  assert.equal(quieta(), false, 'una tecla la despierta al momento');
  t.avanzar(90000);
  assert.equal(quieta(), true);
  win.disparar('wheel');
  assert.equal(quieta(), false);
});

test('el blur/focus de window cuentan como el foco de Python', () => {
  const { t, win, quieta } = montar();
  win.disparar('blur');
  t.avanzar(20000);
  assert.equal(quieta(), true);
  win.disparar('focus');
  assert.equal(quieta(), false);
});

test('ocupada (escribiendo, hablando…): nunca quieta; al acabar cuenta desde entonces', () => {
  const { r, t, quieta } = montar();
  r.foco(false);
  t.avanzar(25000);
  assert.equal(quieta(), true);
  r.ocupada('escribiendo', true);
  assert.equal(quieta(), false, 'escribir la despierta al momento');
  t.avanzar(300000);
  assert.equal(quieta(), false);
  r.ocupada('hablando', true);
  r.ocupada('escribiendo', false);
  t.avanzar(60000);
  assert.equal(quieta(), false, 'aún habla');
  r.ocupada('hablando', false);
  t.avanzar(19000);
  assert.equal(quieta(), false);
  t.avanzar(1000);
  assert.equal(quieta(), true);
  assert.deepEqual(r.estado().ocupadas, []);
});

test('activar(false) («Quedarme quieta cuando no me usas» apagado): nunca, y la quita si estaba', () => {
  const { r, t, quieta } = montar();
  r.foco(false);
  t.avanzar(20000);
  assert.equal(quieta(), true);
  r.activar(false);
  assert.equal(quieta(), false);
  t.avanzar(600000);
  assert.equal(quieta(), false);
  assert.equal(r.estado().activo, false);
  r.activar(true);
  t.avanzar(20000);
  assert.equal(quieta(), true, 'otra vez activa: sin foco, a los 20 s');
});

test('la alarma que suena (window.luneAlarmas) la tiene ocupada hasta que se apaga', () => {
  const alarmas = { alarma_sonando: senal(), alarma_apagada: senal() };
  const { r, t, win, quieta } = montar({ win: { luneAlarmas: alarmas } });
  assert.equal(alarmas.alarma_sonando.oyentes, 1);
  r.foco(false);
  t.avanzar(20000);
  assert.equal(quieta(), true);
  alarmas.alarma_sonando.emit('{}');
  assert.equal(quieta(), false);
  t.avanzar(120000);
  assert.equal(quieta(), false);
  alarmas.alarma_apagada.emit();
  t.avanzar(20000);
  assert.equal(quieta(), true);
  r.destruir();
  assert.equal(alarmas.alarma_sonando.oyentes, 0);
  assert.equal(win.n('pointermove'), 0, 'destruir quita los oyentes');
});

test('sin luneAlarmas al arrancar, se cablea con lune-ready', () => {
  const { win } = montar();
  const alarmas = { alarma_sonando: senal(), alarma_apagada: senal() };
  win.luneAlarmas = alarmas;
  win.disparar('lune-ready');
  assert.equal(alarmas.alarma_sonando.oyentes, 1);
});

test('lo que aparece quieta termina sus animaciones finitas; las infinitas siguen en pausa', () => {
  ObservadorFalso.vivos.length = 0;
  const { r, t, body } = montar();
  r.foco(false);
  t.avanzar(20000);
  const obs = ObservadorFalso.vivos.at(-1);
  assert.ok(obs && obs.conectado && obs.nodo === body && obs.opc.subtree && obs.opc.childList);
  const an = (vueltas) => ({ fin: 0, effect: { getTiming: () => ({ iterations: vueltas }) }, finish() { this.fin++; } });
  const entrada = an(1), bucle = an(Infinity);
  const toast = { nodeType: 1, getAnimations: (o) => { assert.deepEqual(o, { subtree: true }); return [entrada, bucle]; } };
  obs.cb([{ addedNodes: [toast, { nodeType: 3 }] }]);
  assert.equal(entrada.fin, 1, 'el aviso se ve ya en su estado final');
  assert.equal(bucle.fin, 0);
  r.despertar();
  assert.equal(obs.conectado, false, 'despierta: se deja de observar');
});

test('terminarAnimaciones aguanta nodos raros y animaciones que lanzan', () => {
  const T = LuneReposo.terminarAnimaciones;
  assert.equal(T(null), 0);
  assert.equal(T({ nodeType: 1 }), 0);
  assert.equal(T({ nodeType: 1, getAnimations() { throw new Error('x'); } }), 0);
  const rota = { effect: { getTiming() { throw new Error('y'); } }, finish() {} };
  const buena = { effect: { getTiming: () => ({ iterations: 2 }) }, hecho: false, finish() { this.hecho = true; } };
  assert.equal(T({ nodeType: 1, getAnimations: () => [rota, buena] }), 1);
  assert.equal(buena.hecho, true);
});

test('index.html: carga lune_reposo.js tras tema.js y congela todo con body.lune-quieta', () => {
  const html = readFileSync(new URL('../../ui_web/ui_kits/lune-desktop/index.html', import.meta.url), 'utf8');
  const i = html.indexOf('<script src="../../lune_reposo.js"></script>');
  assert.ok(i > html.indexOf('<script src="../../tema.js"></script>'));
  assert.ok(i < html.indexOf('<script type="text/babel"'), 'antes que los .jsx (app.jsx la usa al montar)');
  assert.match(html, /body\.lune-quieta \*, body\.lune-quieta \*::before, body\.lune-quieta \*::after\{ animation-play-state:paused !important; \}/);
  // El tema Nube también se apaga con «Fondo animado» y el LED respeta las micro-animaciones
  assert.match(html, /\.fx-no-bg \.nube-stars\{ animation:none; \}/);
  assert.match(html, /\.fx-no-bg \.nube-cloud\{ display:none; \}/);
  assert.match(html, /\.fx-no-micro \.lune-status \.led::after\{ animation:none; display:none; \}/);
});

test('app.jsx y sidebar.jsx: ocupada escribiendo/hablando, activar con fx.quieta y la barra en pausa', () => {
  const app = readFileSync(new URL('../../ui_web/ui_kits/lune-desktop/app.jsx', import.meta.url), 'utf8');
  assert.match(app, /R\.ocupada\('escribiendo', busy \|\| typing\)/);
  assert.match(app, /R\.ocupada\('hablando', asistente === 'talking'/);
  assert.match(app, /R\.activar\(fx\.quieta !== false\)/);
  assert.match(app, /quieta=\{quieta\}/);
  const barra = readFileSync(new URL('../../ui_web/ui_kits/lune-desktop/sidebar.jsx', import.meta.url), 'utf8');
  assert.match(barra, /<AsistenteVideo state=\{state\} pausado=\{modoJuego \|\| quieta\}/);
  assert.match(barra, /reposo=\{quieta\}/);
  assert.match(barra, /h\.reposar\(!!reposo\)/);
});
