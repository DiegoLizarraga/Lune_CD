// tests/js/vrm_fps.test.mjs — ritmo del bucle de ui_web/vrm/lune_vrm.js (11.2), con el motor DE
// VERDAD en Node (motor_vrm_falso.mjs): mover el cursor no lo sube a fpsActivo, dormida del todo
// baja a fpsDormida, y con FPS 0 el bucle se para (ni un requestAnimationFrame más) hasta que
// setFPS(n > 0) lo vuelve a arrancar. También la pantalla grande dormida (salvapantallas) y las
// «z z z» de companion_vrm.html, que se mueven en los frames del avatar y no con CSS infinito.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

import { reloj, cargas, crearVRMFalso } from './three_falso.mjs';
import {
  frames, correr, montar, quietaSinIdles, motor, lienzoFalso, scriptsEnLinea, reescribirImports, aDataURL,
  DATA_MOTOR, UI,
} from './motor_vrm_falso.mjs';
import { crearElemento, crearDocumento } from './dom_falso.mjs';
import { instalar as instalarGrande } from '../../ui_web/vrm/lune_grande.js';

const { PARAMS } = motor;

/** Frames que se pintaron en `seg` segundos de rAF a 60 Hz (antes(i) antes de cada uno). */
function pintados(m, seg, antes = null) {
  const r0 = m.ctx.renderer.renders;
  correr(seg, antes);
  return m.ctx.renderer.renders - r0;
}

test('PARAMS: reposo a 24 fps y dormida a 12', () => {
  assert.equal(PARAMS.fpsReposo, 24);
  assert.equal(PARAMS.fpsDormida, 12);
  assert.equal(PARAMS.fpsActivo, 60);
});

test('mover el cursor no cuenta como actividad: el bucle sigue a fpsReposo y la cabeza lo sigue igual', () => {
  const { m, vrm } = montar();
  quietaSinIdles(m);
  correr(5);                                            // más que reposoTras: en reposo
  // Parpadeos y demás suben a 60 fps unos frames sueltos: se compara con el mismo rato sin ratón.
  const quieto = pintados(m, 4);
  let i = 0;
  const n = pintados(m, 4, () => { i++; m.cursor(Math.sin(i / 10), 0.2 * Math.cos(i / 7), -1, -1, false); });
  assert.ok(n < 4 * 36, `lejos de 60 fps con el ratón en marcha (${n} frames en 4 s)`);
  assert.ok(n <= quieto + 12, `igual que sin mover el ratón (${n} con ratón, ${quieto} sin él)`);
  assert.ok(n >= 4 * 24 - 2, `al menos fpsReposo (${n})`);
  // El seguimiento sigue funcionando al ritmo de reposo
  m.cursor(1.5, 0, -1, -1, false);
  correr(2);
  assert.ok(Math.abs(vrm.huesos.head.rotation.y) > 0.05, 'la cabeza gira hacia el cursor');
  m.destruir();
});

test('lo que sí es actividad (tocarla) sube a fpsActivo un rato', () => {
  const { m } = montar();
  quietaSinIdles(m);
  correr(5);
  m.tocar();
  const n = pintados(m, 1);
  assert.ok(n >= 55, `a 60 fps tras tocarla (${n})`);
  m.destruir();
});

test('dormida del todo baja a fpsDormida; al despertar vuelve', () => {
  const { m } = montar();
  quietaSinIdles(m);
  m.dormir(true);
  correr(8);                                            // se funde el sueño (dormirEntrada) y pasa reposoTras
  const n = pintados(m, 2, () => m.cursor(0.3, 0.1, -1, -1, false));
  assert.ok(n >= 22 && n <= 26, `≈ 12 fps dormida (${n} frames en 2 s)`);
  m.dormir(false);
  const d = pintados(m, 1);
  assert.ok(d >= 55, `despertando, a todo ritmo (${d})`);
  m.destruir();
});

test('FPS 0 para el bucle: sin requestAnimationFrame; setFPS(n > 0) lo arranca sin salto', () => {
  const { m } = montar();
  quietaSinIdles(m);
  m.setFPS(0);
  // El frame que ya estaba pedido corre una vez y ya no pide otro
  for (const f of frames.splice(0)) { reloj.ms += 16; f(reloj.ms); }
  assert.equal(frames.length, 0, 'parado: ni un frame más');
  const r0 = m.ctx.renderer.renders;
  reloj.ms += 60000;                                    // un minuto parado
  assert.equal(frames.length, 0);
  m.setFPS(30);
  assert.equal(frames.length, 1, 'setFPS(30) vuelve a pedir un frame');
  m.setFPS(30);
  assert.equal(frames.length, 1, 'sin bucles duplicados');
  const inactivo0 = m.ctx.estado().inactivo;
  correr(0.5);
  assert.ok(m.ctx.renderer.renders > r0, 'vuelve a pintar');
  assert.ok(m.ctx.estado().inactivo - inactivo0 < 1, 'el reloj interno no salta el minuto parado');
  m.destruir();
  for (const f of frames.splice(0)) { reloj.ms += 16; f(reloj.ms); }
  assert.equal(frames.length, 0, 'destruido: nada');
});

test('el limitador no pinta de más cuando el frame llega un pelín antes del intervalo', () => {
  const { m } = montar();
  quietaSinIdles(m);
  m.dormir(true);
  correr(8);                                            // dormida del todo: objetivo fpsDormida (83.3 ms)
  // Frames de 16.66 ms (un monitor de 60 Hz con su jitter): cinco son 83.3 ms, un pelín por debajo
  // del intervalo de 83.33 pero dentro de la tolerancia (medio ms). Antes `pasado % intervalo` dejaba
  // entonces ultimoFrame donde estaba y el frame siguiente también se pintaba (≈ 16 fps en vez de 12;
  // a 60 Hz exactos, la mitad de las veces según el redondeo).
  const r0 = m.ctx.renderer.renders;
  const base = reloj.ms;
  for (let k = 1; k <= 180; k++) {
    reloj.ms = base + k * 16.66;
    frames.shift()(reloj.ms);
  }
  const n = m.ctx.renderer.renders - r0;                // 3 s
  assert.ok(n >= 34 && n <= 37, `≈ 12 fps (${n} frames en 3 s)`);
  m.destruir();
});

test('pantalla grande y salvapantallas: dormida baja a fpsDormida aunque el módulo pida 30 fps', () => {
  const { m } = montar();
  quietaSinIdles(m);
  const mod = m.registrar((ctx) => instalarGrande(ctx, {}));
  assert.equal(mod.nombre, 'grande');
  m.mod('grande', 'fase', 'glide', { ms: 100 });
  correr(0.3);
  m.mod('grande', 'fase', 'entrar', { ms: 100 });
  correr(0.5);
  assert.equal(m.mod('grande', 'estado').fase, 'activa');
  m.dormir(true);
  correr(8);
  const n = pintados(m, 2);
  assert.ok(n >= 22 && n <= 26, `≈ 12 fps dormida en pantalla grande (${n} frames en 2 s)`);
  m.dormir(false);
  correr(0.2);
  const d = pintados(m, 1);
  assert.ok(d >= 28 && d <= 32, `despierta, los 30 fps de la pantalla grande (${d})`);
  m.mod('grande', 'fase', 'fin');
  m.destruir();
});

/** companion_vrm.html en Node con el DOM falso (como comida_vrm.test.mjs); con tres <span> en #zzz. */
async function paginaVrm(sufijo) {
  const body = crearElemento('body');
  const stage = body.appendChild(crearElemento('div', 'stage'));
  stage.appendChild(Object.assign(crearElemento('canvas', 'c'), lienzoFalso()));
  const zzz = stage.appendChild(crearElemento('div', 'zzz'));
  for (let i = 0; i < 3; i++) zzz.appendChild(crearElemento('span'));
  zzz.classList.toggle = (c, on) => { if (on) zzz.classList.add(c); else zzz.classList.remove(c); };
  stage.appendChild(crearElemento('div', 'aviso'));
  const doc = crearDocumento(body);
  doc.body = body;
  globalThis.document = doc;
  globalThis.location = { search: '?src=/vrm/actual.vrm&v=1' };
  const { html, scripts } = scriptsEnLinea('companion_vrm.html');
  vm.runInThisContext(scripts[0].codigo, { filename: 'companion_vrm.html' });
  frames.length = 0;
  await import(aDataURL(reescribirImports(scripts[1].codigo, new URL('companion_vrm.html', UI),
    { './vrm/lune_vrm.js': DATA_MOTOR }) + `\n// ${sufijo}`));
  return { html, zzz, a: globalThis.luneAsistente };
}

test('companion_vrm.html: las «z z z» no llevan animación CSS infinita y solo existen dormida', async () => {
  const { html, a } = await paginaVrm('zzz css');
  try {
    const estilo = html.slice(html.indexOf('<style>'), html.indexOf('</style>'));
    assert.ok(!/infinite/.test(estilo), 'ninguna animación infinita en la página');
    assert.match(estilo, /#zzz \{[^}]*display:none/);
    assert.match(estilo, /#zzz\.on \{ display:block;/);
    assert.match(estilo, /#zzz span \{[^}]*opacity:0;/, 'antes del primer frame no se ven');
  } finally {
    a.destruir();
  }
});

test('companion_vrm.html: dormida, las «z z z» se mueven SOLO en los frames que pinta el avatar', async () => {
  const { zzz, a } = await paginaVrm('zzz frames');
  try {
    const vrm = crearVRMFalso();
    cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
    quietaSinIdles(a);
    assert.equal(a.bus.lista().includes('zzz'), false, 'despierta: sin módulo (se registra al dormirse)');
    globalThis.luneSleep(true);
    assert.equal(zzz.classList.contains('on'), true);
    assert.ok(a.bus.lista().includes('zzz'));
    correr(8);                                          // fundido del sueño y reposoTras
    const r0 = a.ctx.renderer.renders;
    let cambios = 0, previo = zzz.children[0].style.transform;
    correr(2, null, () => {
      const t = zzz.children[0].style.transform;
      if (t !== previo) { cambios++; previo = t; }
    });
    const n = a.ctx.renderer.renders - r0;
    assert.ok(n >= 22 && n <= 26, `≈ 12 fps dormida (${n})`);
    assert.ok(cambios >= n - 1 && cambios <= n, `una pose por frame pintado, ni una más (${cambios} de ${n})`);
    assert.match(zzz.children[1].style.transform, /^translate\(-?[\d.]+px, -?[\d.]+px\) rotate\(-?[\d.]+deg\)$/);
    // El recorrido de antes (2,4 s): nace transparente, a .9 al 15 % y se apaga subiendo 46 px.
    const en = (t, d) => globalThis.luneMod('zzz', 'en', t, d);
    assert.deepEqual(en(0, 0), { transform: 'translate(0.0px, 0.0px) rotate(0.0deg)', opacity: '0.000' });
    assert.equal(en(0.36, 0).opacity, '0.900');
    assert.equal(en(2.4, 0).opacity, '0.000', 'periódico');
    assert.equal(en(1.2, 0).transform, 'translate(7.0px, -23.0px) rotate(9.0deg)');
    assert.deepEqual(en(0.4, 0.8), en(1.2, 0), 'desfasadas 0,8 s');
    // Al despertar se ocultan y ya no se tocan
    globalThis.luneSleep(false);
    assert.equal(zzz.classList.contains('on'), false);
    const quieto = zzz.children[0].style.transform;
    correr(1);
    assert.equal(zzz.children[0].style.transform, quieto);
  } finally {
    a.destruir();
  }
});

// ── En reposo, el frame siguiente con un temporizador (sin rAF a 60/s entre medias) ──────────────
function temporizadorFalso() {
  let n = 0;
  const lista = new Map();
  return {
    poner(fn, ms) { const id = ++n; lista.set(id, { id, fn, at: reloj.ms + ms }); return id; },
    quitar(id) { lista.delete(id); },
    proximo() { let m = null; for (const x of lista.values()) if (!m || x.at < m.at) m = x; return m; },
    sacar(x) { lista.delete(x.id); },
    get pendientes() { return lista.size; },
  };
}

/** Asistente con el temporizador falso; quieta y sin idles (con rAF), y luego con la espera encendida. */
function montarConEspera() {
  frames.length = 0;
  const t = temporizadorFalso();
  const m = motor.crearAsistente({ canvas: lienzoFalso(), src: '/vrm/actual.vrm', temporizador: t, ahoraMs: () => reloj.ms });
  const vrm = crearVRMFalso();
  cargas.pop().alCargar({ scene: vrm.scene, userData: { vrm } });
  quietaSinIdles(m);
  correr(5);                                            // más que reposoTras: en reposo
  PARAMS.esperaTemporizador = true;
  return { m, t };
}

/** `seg` s de reloj: los rAF en cada refresco de 60 Hz y los temporizadores cuando vencen. */
function simular(t, m, seg) {
  let rafs = 0, timers = 0, dobles = 0;
  const r0 = m.ctx.renderer.renders;
  const fin = reloj.ms + seg * 1000;
  while (reloj.ms < fin - 1e-6) {
    const vsync = reloj.ms + 1000 / 60;
    for (let x = t.proximo(); x && x.at <= vsync; x = t.proximo()) {
      reloj.ms = Math.max(reloj.ms, x.at); t.sacar(x); timers++; x.fn();
    }
    reloj.ms = vsync;
    for (const f of frames.splice(0)) { rafs++; f(reloj.ms); }
    if (frames.length && t.pendientes) dobles++;
  }
  return { rafs, timers, dobles, renders: m.ctx.renderer.renders - r0 };
}

test('en reposo el frame siguiente va con temporizador: ~24 frames por segundo y casi ningún rAF', () => {
  const { m, t } = montarConEspera();
  try {
    simular(t, m, 0.5);
    const r = simular(t, m, 4);
    // Un parpadeo pone unos frames a 60 con rAF (ocupado); el resto, al ritmo de reposo con el temporizador.
    assert.ok(r.renders >= 4 * 24 - 3 && r.renders <= 4 * 24 + 12, `≈ fpsReposo (${r.renders} en 4 s)`);
    assert.ok(r.rafs <= 20, `sin el bucle a 60/s: ${r.rafs} rAF en 4 s (antes, 240)`);
    assert.ok(r.timers >= 90, `${r.timers} temporizadores`);
    assert.equal(r.dobles, 0, 'nunca rAF y temporizador a la vez (un solo bucle)');
    // Dormida del todo: ≈ 12
    m.dormir(true);
    simular(t, m, 8);
    const d = simular(t, m, 4);
    assert.ok(d.renders >= 4 * 12 - 2 && d.renders <= 4 * 12 + 1, `≈ fpsDormida (${d.renders} en 4 s)`);
    assert.ok(d.rafs <= 2, `${d.rafs} rAF dormida`);
  } finally {
    PARAMS.esperaTemporizador = false;
    m.destruir();
  }
});

test('lo que la despierta corta la espera: tocarla pide el frame ya y vuelve a rAF a 60', () => {
  const { m, t } = montarConEspera();
  try {
    simular(t, m, 0.5);
    assert.equal(t.pendientes, 1, 'esperando al siguiente');
    m.tocar();
    assert.equal(t.pendientes, 0, 'espera cortada');
    assert.equal(frames.length, 1, 'frame ya');
    const r = simular(t, m, 1);
    assert.ok(r.renders >= 55, `a todo ritmo (${r.renders})`);
    assert.ok(r.rafs >= 55 && r.timers <= 2, `con rAF (${r.rafs} rAF, ${r.timers} temporizadores)`);
    // Una llamada a un módulo también (puede ponerlo en marcha)
    simular(t, m, 6);
    assert.equal(t.pendientes, 1);
    m.mod('idles', 'estado');
    assert.equal(t.pendientes, 0);
    assert.equal(frames.length, 1);
  } finally {
    PARAMS.esperaTemporizador = false;
    m.destruir();
  }
});

test('setFPS(0) y destruir quitan la espera; con la página oculta, rAF (Chromium no lo llama)', () => {
  const { m, t } = montarConEspera();
  try {
    simular(t, m, 0.5);
    assert.equal(t.pendientes, 1);
    m.setFPS(0);
    assert.equal(t.pendientes, 0, 'FPS 0: ni temporizador');
    simular(t, m, 1);
    assert.equal(frames.length + t.pendientes, 0, 'parado');
    m.setFPS(30);
    assert.equal(frames.length, 1);
    globalThis.document = { hidden: true };
    simular(t, m, 1);
    assert.equal(t.pendientes, 0, 'oculta: sin temporizador');
    assert.equal(frames.length, 1, 'oculta: un rAF esperando a que se vea');
    globalThis.document = { hidden: false };
    simular(t, m, 1);
    assert.equal(t.pendientes, 1);
    m.destruir();
    assert.equal(t.pendientes, 0, 'destruida: nada pendiente');
  } finally {
    delete globalThis.document;
    PARAMS.esperaTemporizador = false;
    m.destruir();
  }
});
