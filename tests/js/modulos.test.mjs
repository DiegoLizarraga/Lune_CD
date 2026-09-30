// tests/js/modulos.test.mjs — bus de módulos del VRM, registro de la asistente animada
// y utilidades de física (ui_web/vrm/lune_modulos.js, ui_web/anim/lune_anim_modulos.js).
// Sin DOM ni three: se ejecuta con `node --test tests/js`.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  crearBus, crearRegistro, FACTORES, Muelle, smoothDamp, Bolsa, crearAleatorio,
  suav, smoothstep, sumar, mezclarPoses, interpolarPoses, emitirPorDefecto,
} from '../../ui_web/vrm/lune_modulos.js';
import {
  crearRegistroAnim, rotarEn, escalarEn, mover, Muelle as MuelleAnim,
} from '../../ui_web/anim/lune_anim_modulos.js';

const cerca = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} ≉ ${b} (±${tol})`);

function busConEventos() {
  const eventos = [];
  const bus = crearBus({ emitir: (t, d) => eventos.push({ t, d }) });
  return { bus, eventos };
}

// ── Bus: orden y hooks ─────────────────────────────────────────────────────────

test('los hooks se llaman por orden ascendente y, a igual orden, por orden de registro', () => {
  const { bus } = busConEventos();
  const log = [];
  const mod = (nombre, orden) => ({ nombre, orden, pose: (out) => { log.push(nombre); out.n = (out.n || 0) + 1; } });
  bus.registrar(mod('c', 40));
  bus.registrar(mod('a', 10));
  bus.registrar(mod('b', 10));
  bus.registrar({ nombre: 'sinOrden', pose: () => log.push('sinOrden') });   // orden 50 por defecto
  bus.registrar({ nombre: 'sinPose', orden: 0 });                          // no tiene el hook
  const out = {};
  bus.llamar('pose', out, 0.016, 1, {});
  assert.deepEqual(log, ['a', 'b', 'c', 'sinOrden']);
  assert.equal(out.n, 3);
  assert.deepEqual(bus.lista(), ['sinPose', 'a', 'b', 'c', 'sinOrden']);
});

test('llamar pasa los argumentos y devuelve los valores definidos en orden', () => {
  const { bus } = busConEventos();
  bus.registrar({ nombre: 'x', orden: 2, trasUpdate: (dt, t, est) => `x:${dt}:${t}:${est.k}` });
  bus.registrar({ nombre: 'y', orden: 1, trasUpdate: () => undefined });
  bus.registrar({ nombre: 'z', orden: 3, trasUpdate: () => 0 });
  assert.deepEqual(bus.llamar('trasUpdate', 0.5, 2, { k: 'e' }), ['x:0.5:2:e', 0]);
  assert.deepEqual(bus.llamar('hookQueNadieTiene'), []);
});

test('registrar acepta instalar(ctx) y el namespace de un módulo', () => {
  const ctx = { THREE: { marca: 1 } };
  const bus = crearBus(ctx);
  let recibido = null;
  const instalar = (c) => { recibido = c; return { nombre: 'porFuncion' }; };
  assert.equal(bus.registrar(instalar).nombre, 'porFuncion');
  assert.equal(recibido, ctx);
  assert.equal(typeof ctx.emitir, 'function', 'crearBus completa ctx.emitir');
  bus.registrar({ instalar: () => ({ nombre: 'porNamespace' }) });
  assert.deepEqual(bus.lista().sort(), ['porFuncion', 'porNamespace']);
  const avisoOriginal = console.warn;
  console.warn = () => {};
  try {
    assert.equal(bus.registrar({ orden: 1 }), null, 'sin nombre no se registra');
    assert.equal(bus.registrar(() => { throw new Error('instalar roto'); }), null, 'instalar que lanza no rompe');
  } finally {
    console.warn = avisoOriginal;
  }
  assert.equal(bus.lista().length, 2);
});

test('alCargar llega a los módulos registrados tarde; sustituir llama a alDescargar del viejo', () => {
  const { bus } = busConEventos();
  const log = [];
  const vrm = { id: 'modelo' };
  bus.registrar({ nombre: 'temprano', alCargar: (v) => log.push(['temprano', v.id]) });
  bus.llamar('alCargar', vrm);
  bus.registrar({ nombre: 'tarde', alCargar: (v) => log.push(['tarde', v.id]), alDescargar: () => log.push(['tarde-fuera']) });
  bus.registrar({ nombre: 'tarde', alCargar: (v) => log.push(['tarde2', v.id]) });
  bus.llamar('alDescargar');
  bus.registrar({ nombre: 'trasDescargar', alCargar: () => log.push(['no debería']) });
  assert.deepEqual(log, [['temprano', 'modelo'], ['tarde', 'modelo'], ['tarde-fuera'], ['tarde2', 'modelo']]);
  assert.equal(bus.quitar('tarde'), true);
  assert.equal(bus.quitar('noExiste'), false);
});

test('un módulo que lanza no corta a los demás: se avisa una vez y a los 30 fallos se desactiva', () => {
  const { bus, eventos } = busConEventos();
  const log = [];
  const avisoOriginal = console.warn;
  console.warn = () => {};
  try {
    bus.registrar({ nombre: 'roto', orden: 1, pose: () => { throw new Error('pum'); } });
    bus.registrar({ nombre: 'bien', orden: 2, pose: () => log.push('bien') });
    for (let i = 0; i < 40; i++) bus.llamar('pose', {}, 0.016, i, {});
  } finally {
    console.warn = avisoOriginal;
  }
  assert.equal(log.length, 40);
  const errores = eventos.filter((e) => e.t === 'error');
  assert.equal(errores.length, 2, 'un aviso normal + uno de desactivado');
  assert.deepEqual(errores[0].d, { modulo: 'roto', hook: 'pose', mensaje: 'pum', desactivado: false });
  assert.equal(errores[1].d.desactivado, true);
  assert.equal(bus.activo('roto'), false);
  assert.equal(bus.reactivar('roto'), true);
  assert.equal(bus.activo('roto'), true);
});

// ── Bus: ocupado, inhibe y api ─────────────────────────────────────────────────

test('inhibe multiplica los factores por clave (0..1) y deja 1 lo que nadie inhibe', () => {
  const { bus } = busConEventos();
  bus.registrar({ nombre: 'a', inhibe: () => ({ idle: 0.5, gesto: 0.2 }) });
  bus.registrar({ nombre: 'b', inhibe: (est) => ({ idle: est.baile ? 0.5 : 1, parpadeo: 0 }) });
  bus.registrar({ nombre: 'c', inhibe: () => ({ seguimiento: 7, caricia: -3, idle: NaN, otra: 0 }) });
  bus.registrar({ nombre: 'd', inhibe: () => null });
  const r = bus.inhibe({ baile: true });
  assert.deepEqual(Object.keys(r).sort(), [...FACTORES].sort());
  cerca(r.idle, 0.25, 1e-12, 'idle');
  assert.equal(r.seguimiento, 1, 'se recorta a 1');
  assert.equal(r.caricia, 0, 'se recorta a 0');
  assert.equal(r.parpadeo, 0);
  cerca(r.gesto, 0.2, 1e-12, 'gesto');
  assert.equal(bus.inhibe({ baile: false }).idle, 0.5);
});

test('ocupado es el OR de los módulos', () => {
  const { bus } = busConEventos();
  bus.registrar({ nombre: 'quieto', ocupado: () => false });
  assert.equal(bus.ocupado({}), false);
  bus.registrar({ nombre: 'bailando', ocupado: (est) => !!est.baile });
  assert.equal(bus.ocupado({ baile: false }), false);
  assert.equal(bus.ocupado({ baile: true }), true);
});

test('api llama a mod.api[metodo] y exponer crea window.luneMod', () => {
  const { bus } = busConEventos();
  bus.registrar({ nombre: 'idles', api: { variante(n) { return `v${n}`; }, suma: (a, b) => a + b } });
  assert.equal(bus.api('idles', 'variante', 3), 'v3');
  const avisoOriginal = console.warn;
  console.warn = () => {};
  try {
    assert.equal(bus.api('idles', 'noExiste'), undefined);
    assert.equal(bus.api('nadie', 'variante'), undefined);
  } finally {
    console.warn = avisoOriginal;
  }
  const win = {};
  bus.exponer(win, 'luneMod');
  assert.equal(win.luneMod('idles', 'suma', 2, 3), 5);
});

test('crearRegistro sin emitir usa la cola global __luneEventos', () => {
  delete globalThis.luneEmitir;
  globalThis.__luneEventos = [];
  const reg = crearRegistro({});
  reg.ctx.emitir('sentada', { modo: 'barra' });
  emitirPorDefecto('baile_fin', undefined);
  assert.equal(globalThis.__luneEventos.length, 2);
  assert.deepEqual(globalThis.__luneEventos[0].d, { modo: 'barra' });
  assert.equal(globalThis.__luneEventos[1].d, null);
  assert.equal(typeof globalThis.__luneEventos[0].ts, 'number');
  delete globalThis.__luneEventos;
});

// ── Bolsa ──────────────────────────────────────────────────────────────────────

test('Bolsa saca todos antes de repetir y nunca repite seguido', () => {
  const b = new Bolsa(5, { semilla: 42 });
  let anterior;
  for (let tanda = 0; tanda < 40; tanda++) {
    const vistos = [];
    for (let i = 0; i < 5; i++) {
      const x = b.siguiente();
      assert.notEqual(x, anterior, 'no repite dos veces seguidas (ni entre tandas)');
      anterior = x;
      vistos.push(x);
    }
    assert.deepEqual(vistos.sort(), [0, 1, 2, 3, 4], 'cada tanda es una permutación');
  }
});

test('Bolsa es determinista con semilla y admite un aleatorio inyectado', () => {
  const a = new Bolsa(['x', 'y', 'z', 'w'], { semilla: 7 });
  const b = new Bolsa(['x', 'y', 'z', 'w'], { semilla: 7 });
  const sa = Array.from({ length: 12 }, () => a.siguiente());
  const sb = Array.from({ length: 12 }, () => b.siguiente());
  assert.deepEqual(sa, sb);
  // Aleatorio degenerado (siempre 0.9999999 o fuera de rango): no se sale del array ni repite.
  for (const r of [() => 0.9999999, () => 1, () => -5, () => NaN]) {
    const c = new Bolsa([1, 2, 3], { aleatorio: r });
    let prev;
    for (let i = 0; i < 12; i++) {
      const x = c.siguiente();
      assert.ok([1, 2, 3].includes(x));
      assert.notEqual(x, prev);
      prev = x;
    }
  }
  assert.equal(new Bolsa([]).siguiente(), undefined);
  const uno = new Bolsa(['solo']);
  assert.deepEqual([uno.siguiente(), uno.siguiente()], ['solo', 'solo']);
});

test('crearAleatorio da valores en [0, 1)', () => {
  const r = crearAleatorio(123);
  for (let i = 0; i < 1000; i++) { const x = r(); assert.ok(x >= 0 && x < 1); }
});

// ── Muelle ─────────────────────────────────────────────────────────────────────

test('Muelle con ζ 0.35 sobrepasa ~31 % (analítico 30.9 %)', () => {
  const m = new Muelle(1, 0.35);
  let max = 0;
  for (let i = 0; i < 180; i++) max = Math.max(max, m.paso(1, 1 / 60));
  cerca(max - 1, 0.309, 0.015, 'sobrepaso');
  cerca(m.x, 1, 0.02, 'se asienta en el objetivo');
});

test('Muelle integra en subpasos ≤ 1/120 s: un dt grande equivale a varios pequeños', () => {
  const a = new Muelle(2.6, 0.35), b = new Muelle(2.6, 0.35);
  a.paso(10, 0.1);
  for (let i = 0; i < 12; i++) b.paso(10, 1 / 120);
  cerca(a.x, b.x, 1e-9, 'misma posición');
  cerca(a.v, b.v, 1e-9, 'misma velocidad');
});

test('Muelle es NaN-safe y no se cuelga con dt enormes', () => {
  const m = new Muelle(2.6, 0.35);
  m.paso(5, 1 / 60);
  const x = m.x;
  assert.equal(m.paso(NaN, 1 / 60) === m.x, true);
  assert.ok(Number.isFinite(m.x));
  assert.equal(m.paso(5, NaN), m.x);
  assert.equal(m.paso(5, -1), m.x);
  m.x = NaN;
  assert.equal(m.paso(5, 1 / 60), 0, 'estado corrupto → se reinicia');
  const t0 = Date.now();
  const r = m.paso(5, 1e6);
  assert.ok(Number.isFinite(r) && Date.now() - t0 < 200);
  assert.ok(Math.abs(new Muelle(50, 0, 3).paso(1000, 0.5)) <= 3, 'respeta el tope');
  assert.ok(x > 0);
  assert.equal(MuelleAnim, Muelle, 'el registro animado reexporta el mismo Muelle');
});

// ── smoothDamp (Unity) ─────────────────────────────────────────────────────────

test('smoothDamp coincide con Mathf.SmoothDamp de Unity', () => {
  // Valores de referencia calculados aparte con la fórmula de Unity (Python, doble precisión).
  const sd = { v: 0 };
  const x1 = smoothDamp(0, 10, sd, 0.3, 1 / 60);
  cerca(x1, 0.05592010361485755, 1e-12, 'x tras 1 paso');
  cerca(sd.v, 6.629386597590097, 1e-9, 'v tras 1 paso');

  let x = 0; const r = { v: 0 };
  for (let i = 0; i < 10; i++) x = smoothDamp(x, 10, r, 0.3, 1 / 60);
  cerca(x, 3.040432745112329, 1e-9, 'x tras 10 pasos');
  cerca(r.v, 24.41953422767604, 1e-8, 'v tras 10 pasos');

  x = 0; r.v = 0;
  for (let i = 0; i < 10; i++) x = smoothDamp(x, 10, r, 0.3, 1 / 60, 5);
  cerca(x, 0.4905360732805526, 1e-9, 'x con velocidad máxima 5');
});

test('smoothDamp converge sin sobrepasar y es NaN-safe', () => {
  let x = 0; const r = { v: 0 };
  for (let i = 0; i < 600; i++) {
    x = smoothDamp(x, 100, r, 0.25, 1 / 60);
    assert.ok(x <= 100, 'no sobrepasa');
  }
  cerca(x, 100, 1e-3, 'llega');
  assert.equal(smoothDamp(3, 10, r, 0.3, 0), 3, 'dt 0 no mueve');
  assert.equal(smoothDamp(NaN, 10, r, 0.3, 1 / 60), 10, 'actual NaN → objetivo');
  assert.equal(r.v, 0);
  assert.equal(smoothDamp(4, NaN, r, 0.3, 1 / 60), 4, 'objetivo NaN → se queda');
  assert.ok(Number.isFinite(smoothDamp(0, 1, null, 0.3, 1 / 60)), 'sin ref no lanza');
});

// ── Otras utilidades ───────────────────────────────────────────────────────────

test('suav, smoothstep y poses', () => {
  cerca(suav(1 / 60, 10), 1 - Math.exp(-10 / 60), 1e-15);
  assert.equal(suav(NaN, 10), 0);
  assert.equal(suav(-1, 10), 0);
  assert.equal(smoothstep(0), 0);
  assert.equal(smoothstep(1), 1);
  assert.equal(smoothstep(0.5), 0.5);
  assert.equal(smoothstep(2), 1);
  assert.equal(smoothstep(0, 2, 1), 0.5);
  assert.equal(smoothstep(NaN), 0);

  const out = {};
  sumar(out, 'head', 0.1, 0, NaN);
  mezclarPoses(out, { head: [0.2, 0.4, 0], spine: [1, 0, 0] }, 0.5);
  mezclarPoses(out, { head: [9, 9, 9] }, 0);        // peso 0 no suma
  mezclarPoses(out, { head: [9, 9, 9] }, NaN);      // peso NaN no suma
  cerca(out.head[0], 0.2, 1e-12); cerca(out.head[1], 0.2, 1e-12); assert.equal(out.head[2], 0);
  assert.deepEqual(out.spine, [0.5, 0, 0]);

  const medio = interpolarPoses({ head: [0, 0, 1] }, { head: [1, 0, 0], neck: [0, 2, 0] }, 0.5);
  assert.deepEqual(medio, { head: [0.5, 0, 0.5], neck: [0, 1, 0] });
});

// ── Registro de la asistente animada ─────────────────────────────────────────────

function registroAnim(extra = {}) {
  const stage = { style: {} };
  const eventos = [];
  const reg = crearRegistroAnim({ stage, video: { id: 'va' }, burbuja: {}, emitir: (t, d) => eventos.push({ t, d }), raf: () => 1, caf: () => {}, ...extra });
  return { reg, stage, eventos };
}

test('registro animado: mismo patrón (orden, api) y ctx con stage/video', () => {
  const { reg } = registroAnim();
  const log = [];
  let ctxRecibido = null;
  reg.registrar((ctx) => { ctxRecibido = ctx; return { nombre: 'baile', orden: 40, tick: () => log.push('baile'), api: { on: (x) => `baile:${x}` } }; });
  reg.registrar({ nombre: 'arrastre', orden: 10, tick: () => log.push('arrastre') });
  reg.llamar('tick', 0.016, 0, reg.est);
  assert.deepEqual(log, ['arrastre', 'baile']);
  assert.equal(reg.api('baile', 'on', 1), 'baile:1');
  assert.deepEqual(ctxRecibido.video(), { id: 'va' });
  reg.setVideo({ id: 'vb' });
  assert.deepEqual(ctxRecibido.video(), { id: 'vb' });
  assert.equal(ctxRecibido.estado(), reg.est);
});

test('registro animado: compone transform/filter de varios módulos en una sola escritura', () => {
  const { reg, stage } = registroAnim();
  reg.registrar({ nombre: 'balanceo', orden: 10, pose: (out) => out.transform.push(rotarEn(5, '50%', '6%')) });
  reg.registrar({ nombre: 'rebote', orden: 20, pose: (out) => { out.transform.push(mover(0, -4)); out.filtro.push('brightness(.75)'); out.opacidad *= 0.5; } });
  reg.componer(0.016);
  assert.equal(stage.style.transform,
    'translate(50%, 6%) rotate(5deg) translate(-50%, -6%) translate(0px, -4px)');
  assert.equal(stage.style.transformOrigin, '0 0');
  assert.equal(stage.style.filter, 'brightness(.75)');
  assert.equal(stage.style.opacity, '0.5');
  assert.equal(escalarEn(1.02, 12, '100%'), 'translate(12px, 100%) scale(1.02, 1.02) translate(-12px, -100%)');
  reg.quitar('balanceo'); reg.quitar('rebote');
  reg.componer(0.016);
  assert.equal(stage.style.transform, '');
  assert.equal(stage.style.opacity, '');
});

test('registro animado: el bucle va a fpsReposo sin módulos ocupados y a todos los frames si alguno lo está', () => {
  const { reg } = registroAnim({ fpsReposo: 15 });
  let ticks = 0, ocupado = false;
  const dts = [];
  reg.registrar({ nombre: 'm', tick: (dt) => { ticks++; dts.push(dt); }, ocupado: () => ocupado });
  for (let ms = 0; ms <= 1000; ms += 1000 / 60) reg.paso(ms);
  assert.ok(ticks >= 14 && ticks <= 16, `reposo ≈ 15 ticks/s, fueron ${ticks}`);
  ticks = 0; ocupado = true;
  for (let ms = 2000; ms < 3000; ms += 1000 / 60) reg.paso(ms);
  assert.ok(ticks >= 59 && ticks <= 61, `ocupado ≈ 60 ticks/s, fueron ${ticks}`);
  assert.ok(dts.every((d) => d >= 0 && d <= 0.1), 'dt acotado a 0.1 s');
  reg.estado({ drag: true, cursor: { nx: 0.5 } });
  assert.equal(reg.est.drag, true);
  assert.equal(reg.est.cursor.nx, 0.5);
  assert.equal(reg.est.cursor.ny, 0, 'cursor se mezcla, no se sustituye');
});

test('registro animado: iniciar/detener llaman a alIniciar/alDetener una vez', () => {
  const log = [];
  const { reg } = registroAnim();
  reg.registrar({ nombre: 'm', alIniciar: () => log.push('ini'), alDetener: () => log.push('fin'), alEmocion: (e) => log.push(e) });
  assert.equal(reg.iniciar(), true);
  assert.equal(reg.iniciar(), false);
  reg.emocion('happy');
  assert.equal(reg.detener(), true);
  assert.equal(reg.detener(), false);
  assert.deepEqual(log, ['ini', 'happy', 'fin']);
});
