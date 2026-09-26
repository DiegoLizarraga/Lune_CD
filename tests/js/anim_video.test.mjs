// tests/js/anim_video.test.mjs — clips de la mascota animada con doble búfer
// (ui_web/anim/lune_anim_video.js) y su CSS (ui_web/css/mascota_anim.css).
// Sin navegador: vídeos, stage, documento y temporizador falsos (dom_falso.mjs).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  MAPA, FUNDIDO, ESPERA_CARGA_MS, CARPETA, clipDe, srcDe, duracionFundido, clipDeSrc,
  normalizarIdles, candidatos, fijarCapa, quitarCapa, emocionEfectiva, crearDobleBufer,
  instalar, publicar, buscarVideos, asegurarZzz,
} from '../../ui_web/anim/lune_anim_video.js';
import { crearAleatorio } from '../../ui_web/anim/lune_anim_modulos.js';
import { crearElemento, crearDocumento, crearTemporizador } from './dom_falso.mjs';

const CSS = new URL('../../ui_web/css/mascota_anim.css', import.meta.url);
const src = (clip) => `${CARPETA}lune-${clip}.webm`;

function montar(opciones = {}) {
  const a = crearElemento('video', 'va');
  const b = crearElemento('video', 'vb');
  const stage = crearElemento('div', 'stage');
  stage.appendChild(a); stage.appendChild(b);
  const doc = crearDocumento(stage);
  const tm = crearTemporizador();
  const est = {};
  const ctx = { stage, estado: () => est, video: () => null };
  const mod = instalar(ctx, {
    videos: [a, b], temporizador: tm, documento: doc, cargarJSON: async () => null,
    aleatorio: crearAleatorio(7), ...opciones,
  });
  return { a, b, stage, doc, tm, est, ctx, mod };
}

// ── Lógica pura ─────────────────────────────────────────────────────────────────

test('duracionFundido: 250 ms por defecto, 500 hacia composed, 450 hacia sad/bored', () => {
  assert.deepEqual({ ...FUNDIDO }, { defecto: 250, idle: 500, triste: 450, dormir: 500 });
  for (const c of ['happy', 'angry', 'surprised', 'nervous', 'thinking', 'working', 'talking', '']) {
    assert.equal(duracionFundido(c), 250, c);
  }
  assert.equal(duracionFundido('composed'), 500);
  assert.equal(duracionFundido('sad'), 450);
  assert.equal(duracionFundido('bored'), 450);
  assert.equal(duracionFundido('sleeping'), 500);
  assert.equal(duracionFundido('composed-2', { idle: true }), 500);     // un idle de la rotación
});

test('clipDe: mapa de estados, mayúsculas y lo desconocido cae a composed', () => {
  assert.equal(clipDe('normal'), 'composed');
  assert.equal(clipDe('typing'), 'working');
  assert.equal(clipDe('reading'), 'curious');
  assert.equal(clipDe('error'), 'angry');
  assert.equal(clipDe('  HAPPY '), 'happy');
  assert.equal(clipDe('dizzy'), 'nervous');
  assert.equal(clipDe('no-existe'), 'composed');
  assert.equal(clipDe(null), 'composed');
  assert.equal(clipDe('toString'), 'composed');                        // nada del prototipo
  assert.equal(clipDe('x', { x: '../../etc/passwd' }), 'composed');    // un mapa con basura no sale de la carpeta
  assert.ok(Object.isFrozen(MAPA));
  assert.equal(srcDe('happy'), 'assets/mascot/anime-videos/lune-happy.webm');
  assert.equal(clipDeSrc('assets/mascot/anime-videos/lune-happy.webm?v=2'), 'happy');
  assert.equal(clipDeSrc('lune-composed-2.webm'), 'composed-2');
  assert.equal(clipDeSrc('nada.png'), '');
});

test('candidatos: el clip, su fundido y el respaldo composed; sleeping con sustituto', () => {
  const h = candidatos('happy');
  assert.deepEqual(h.map((c) => [c.clip, c.fundido, c.idle]), [['happy', 250, false], ['composed', 500, true]]);
  assert.equal(h[0].src, src('happy'));
  assert.deepEqual(candidatos('sad').map((c) => c.fundido), [450, 500]);
  assert.deepEqual(candidatos('normal').map((c) => c.clip), ['composed']);   // sin repetidos
  assert.deepEqual(candidatos('lo-que-sea').map((c) => c.clip), ['composed']);

  const s = candidatos('sleeping');
  assert.deepEqual(s.map((c) => [c.clip, c.velocidad, c.sustituto, c.fundido]),
    [['sleeping', 1, false, 500], ['bored', 0.6, true, 450], ['composed', 1, false, 500]]);

  // Los que ya dieron error se saltan
  const faltan = new Set([src('sleeping')]);
  assert.deepEqual(candidatos('sleeping', { faltan }).map((c) => c.clip), ['bored', 'composed']);
  // Con rotación de idles, normal usa el idle elegido
  const idle = `${CARPETA}lune-composed-2.webm`;
  const n = candidatos('normal', { idle });
  assert.equal(n[0].src, idle);
  assert.equal(n[0].fundido, 500);
  assert.equal(n[1].clip, 'composed');
});

test('normalizarIdles: nombres o .webm de la carpeta, sin rutas ni URLs ni repetidos', () => {
  assert.deepEqual(normalizarIdles(['composed', 'composed-2', 'lune-composed-3.webm', 'composed',
    '../fuera.webm', 'http://x/y.webm', 'sub/dir.webm', null, undefined, 'a b', '']),
  [src('composed'), src('composed-2'), `${CARPETA}lune-composed-3.webm`]);
  assert.deepEqual(normalizarIdles({ idles: ['composed-2'] }), [src('composed-2')]);
  assert.deepEqual(normalizarIdles(null), []);
  assert.deepEqual(normalizarIdles({ otra: 1 }), []);
});

test('capas de emoción: gana la de más prioridad y al quitarla vuelve la base', () => {
  const est = {};
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'happy');
  assert.equal(emocionEfectiva('', null), 'normal');
  fijarCapa(est, 'dormir', 'sleeping');
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'sleeping');
  fijarCapa(est, 'arrastre', 'nervous');                           // 80 > 40
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'nervous');
  fijarCapa(est, 'mareo', 'dizzy');                                // 90
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'dizzy');
  fijarCapa(est, 'propia', 'wave', 100);
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'wave');
  fijarCapa(est, 'propia', null);                                  // null = quitar
  quitarCapa(est, 'mareo');
  quitarCapa(est, 'arrastre');
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'sleeping');
  quitarCapa(est, 'dormir');
  assert.equal(emocionEfectiva('happy', est.capasEmocion), 'happy');
});

// ── Doble búfer ─────────────────────────────────────────────────────────────────

test('doble búfer: carga en el oculto, espera canplay, cruza y libera el saliente', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  const tm = crearTemporizador();
  const vistos = [];
  const buf = crearDobleBufer({ a, b, temporizador: tm, alMostrar: (o) => vistos.push(o.clip) });

  assert.equal(buf.mostrar(candidatos('happy')), true);
  assert.equal(a.getAttribute('src'), src('happy'));
  assert.ok(buf.cargando() && !buf.fundiendo());
  assert.equal(buf.activo(), null);                               // nada visible hasta canplay
  a.disparar('canplay');
  assert.equal(buf.activo(), a);
  assert.equal(a.oyentes('canplay') + a.oyentes('error'), 0);     // oyentes quitados
  assert.ok(a.classList.contains('activo'));
  assert.equal(a.style.props['--lune-fundido'], '250ms');
  assert.ok(a.reproducciones >= 1);
  tm.avanzar(300);
  assert.ok(!buf.fundiendo());

  // Hacia composed: 500 ms, el saliente se apaga y suelta el decodificador
  buf.mostrar(candidatos('normal'));
  assert.equal(b.getAttribute('src'), src('composed'));
  assert.equal(buf.activo(), a);                                  // sigue viéndose happy mientras carga
  b.disparar('canplay');
  assert.equal(buf.activo(), b);
  assert.equal(b.style.props['--lune-fundido'], '500ms');
  assert.equal(a.style.props['--lune-fundido'], '500ms');
  assert.ok(a.classList.contains('saliendo') && !a.classList.contains('activo'));
  const cargasA = a.cargas;
  tm.avanzar(500);
  assert.ok(buf.fundiendo());                                     // 500 ms + 40 de margen
  tm.avanzar(41);
  assert.ok(!buf.fundiendo());
  assert.equal(a.getAttribute('src'), null);                      // removeAttribute('src')…
  assert.equal(a.cargas, cargasA + 1);                            // …+ load()
  assert.ok(!a.classList.contains('saliendo'));

  // Hacia sad: 450 ms
  buf.mostrar(candidatos('sad'));
  a.disparar('canplay');
  assert.equal(a.style.props['--lune-fundido'], '450ms');
  assert.deepEqual(vistos, ['happy', 'composed', 'sad']);
});

test('si el clip no está listo en 800 ms cae a composed (sin darlo por perdido)', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  const tm = crearTemporizador();
  const buf = crearDobleBufer({ a, b, temporizador: tm });
  assert.equal(ESPERA_CARGA_MS, 800);
  buf.mostrar(candidatos('angry'));
  tm.avanzar(799);
  assert.equal(a.getAttribute('src'), src('angry'));
  tm.avanzar(1);
  assert.equal(a.getAttribute('src'), src('composed'));
  assert.equal(a.oyentes('canplay'), 1);                          // solo el del respaldo
  assert.ok(!buf.faltan.has(src('angry')));                       // tiempo agotado ≠ archivo roto
  a.disparar('canplay');
  assert.equal(buf.actual().clip, 'composed');
  assert.equal(buf.actual().fundido, 500);
});

test('un clip que da error se recuerda y la próxima vez va directo al respaldo', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  const tm = crearTemporizador();
  const buf = crearDobleBufer({ a, b, temporizador: tm });
  buf.mostrar(candidatos('wave'));
  a.disparar('error');
  assert.ok(buf.faltan.has(src('wave')));
  assert.equal(a.getAttribute('src'), src('composed'));
  a.disparar('canplay');
  tm.avanzar(600);
  assert.deepEqual(candidatos('wave', { faltan: buf.faltan }).map((c) => c.clip), ['composed']);
  // Ya se ve composed: pedirlo otra vez no recarga nada
  const cargas = a.cargas + b.cargas;
  buf.mostrar(candidatos('wave', { faltan: buf.faltan }));
  assert.equal(a.cargas + b.cargas, cargas);
  assert.ok(!buf.cargando());
});

test('sin ningún clip que cargue se queda lo que había', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  const tm = crearTemporizador();
  const buf = crearDobleBufer({ a, b, temporizador: tm });
  buf.mostrar(candidatos('happy'));
  a.disparar('canplay');
  tm.avanzar(300);
  buf.mostrar(candidatos('sad'));
  b.disparar('error');                                            // sad roto
  b.disparar('error');                                            // composed roto
  assert.equal(buf.activo(), a);
  assert.equal(buf.actual().clip, 'happy');
  assert.ok(!buf.cargando());
});

test('peticiones a mitad de carga o de fundido: gana la última y no hay saltos', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  const tm = crearTemporizador();
  const buf = crearDobleBufer({ a, b, temporizador: tm });
  buf.mostrar(candidatos('happy'));
  buf.mostrar(candidatos('angry'));                               // cancela la carga de happy
  assert.equal(a.getAttribute('src'), src('angry'));
  assert.equal(a.oyentes('canplay'), 1);
  a.disparar('canplay');
  assert.ok(buf.fundiendo());
  buf.mostrar(candidatos('sad'));                                 // durante el fundido: espera
  buf.mostrar(candidatos('wave'));                                // …y gana la última
  assert.equal(b.getAttribute('src'), null);
  tm.avanzar(300);
  assert.equal(b.getAttribute('src'), src('wave'));
  b.disparar('canplay');
  assert.equal(buf.actual().clip, 'wave');
});

test('el clip que la página ya había puesto en #v se adopta como visible', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  a.setAttribute('src', src('wave'));
  const buf = crearDobleBufer({ a, b, temporizador: crearTemporizador() });
  assert.equal(buf.activo(), a);
  assert.equal(buf.actual().clip, 'wave');
  assert.ok(a.classList.contains('activo'));
  buf.mostrar(candidatos('happy'));
  assert.equal(b.getAttribute('src'), src('happy'));              // carga en el otro
});

// ── Módulo del registro ─────────────────────────────────────────────────────────

test('instalar: pone .lune-doble, quita el onerror clásico y sirve el vídeo visible en ctx.video', () => {
  const a = crearElemento('video'), b = crearElemento('video');
  a.onerror = () => { throw new Error('el onerror clásico no debe seguir vivo'); };
  const stage = crearElemento('div');
  const tm = crearTemporizador();
  const ctx = { stage, estado: () => ({}), video: () => 'previo' };
  const m = instalar(ctx, { videos: [a, b], temporizador: tm, cargarJSON: async () => null });
  assert.equal(m.nombre, 'video');
  assert.ok(stage.classList.contains('lune-doble'));
  assert.equal(a.onerror, null);
  assert.equal(ctx.video(), 'previo');                            // aún no hay nada visible
  m.alEmocion('happy');
  a.disparar('canplay');
  assert.equal(ctx.video(), a);
  m.api.liberar();
  assert.ok(!stage.classList.contains('lune-doble'));
});

test('módulo: fundidos por destino al cambiar de emoción', () => {
  const { a, b, tm, mod } = montar();
  mod.alEmocion('sad');
  a.disparar('canplay');
  assert.equal(a.style.props['--lune-fundido'], '450ms');
  tm.avanzar(500);
  mod.alEmocion('normal');
  b.disparar('canplay');
  assert.equal(b.style.props['--lune-fundido'], '500ms');
  tm.avanzar(600);
  mod.alEmocion('thinking');
  a.disparar('canplay');
  assert.equal(a.style.props['--lune-fundido'], '250ms');
  const e = mod.api.estado();
  assert.equal(e.base, 'thinking');
  assert.equal(e.clip, 'thinking');
});

test('módulo: las capas (arrastre) mandan sobre la emoción base y al quitarlas vuelve', () => {
  const { a, b, tm, est, mod } = montar();
  mod.alEmocion('happy');
  a.disparar('canplay');
  tm.avanzar(300);
  fijarCapa(est, 'arrastre', 'surprised');
  mod.tick(0.016, 1);
  assert.equal(b.getAttribute('src'), src('surprised'));
  b.disparar('canplay');
  tm.avanzar(300);
  fijarCapa(est, 'arrastre', 'nervous');
  mod.tick(0.016, 1.5);
  assert.equal(a.getAttribute('src'), src('nervous'));
  a.disparar('canplay');
  tm.avanzar(300);
  quitarCapa(est, 'arrastre');
  mod.tick(0.016, 2);
  assert.equal(b.getAttribute('src'), src('happy'));
  assert.equal(mod.api.estado().efectiva, 'happy');
});

test('módulo: sleeping usa lune-sleeping y, si no existe, bored a 0.6x con zzz', () => {
  const { a, b, stage, tm, est, mod } = montar();
  mod.alEmocion('sleeping');
  assert.equal(est.capasEmocion.dormir.estado, 'sleeping');
  assert.equal(a.getAttribute('src'), src('sleeping'));
  a.disparar('error');                                            // no hay lune-sleeping.webm
  assert.equal(a.getAttribute('src'), src('bored'));
  assert.equal(a.playbackRate, 0.6);
  assert.ok(a.classList.contains('lune-sueno-sustituto'));
  a.disparar('canplay');
  assert.equal(stage.getAttribute('data-sueno'), 'sustituto');
  assert.ok(stage.querySelector('.lune-zzz'), 'zzz creados');
  assert.equal(stage.querySelector('.lune-zzz').children.length, 3);
  assert.equal(a.style.props['--lune-fundido'], '450ms');
  tm.avanzar(500);

  mod.alEmocion('normal');                                        // 'normal' no despierta (como el VRM)
  assert.ok(est.capasEmocion.dormir);
  mod.alEmocion('happy');                                         // otra emoción sí
  assert.ok(!est.capasEmocion.dormir);
  b.disparar('canplay');
  assert.equal(stage.getAttribute('data-sueno'), null);
  assert.equal(b.playbackRate, 1);

  // Con el clip propio no hay sustituto
  const m2 = montar();
  m2.mod.alEmocion('sleeping');
  m2.a.disparar('canplay');
  assert.equal(m2.stage.getAttribute('data-sueno'), 'clip');
  assert.ok(!m2.a.classList.contains('lune-sueno-sustituto'));
  assert.equal(m2.a.style.props['--lune-fundido'], '500ms');
});

test('rotación de idles: con idles.json rota cada 12–18 s sin repetir; sin json no hace nada', async () => {
  const json = ['composed', 'composed-2', 'composed-3'];
  const { a, b, tm, mod } = montar({ cargarJSON: async (url) => (url.endsWith('idles.json') ? json : null) });
  assert.equal(await mod.alIniciar(), 3);
  const cargado = () => (a.getAttribute('src') || b.getAttribute('src'));
  const vistos = [];
  let t = 0;
  let ultimo = null;
  for (let i = 0; i < 80 * 10; i++) {                             // 80 s a 10 fps
    t += 0.1;
    mod.tick(0.1, t);
    for (const v of [a, b]) if (v.oyentes('canplay')) v.disparar('canplay');
    tm.avanzar(100);
    const s = mod.api.estado().src;
    if (s && s !== ultimo) { vistos.push({ s, t }); ultimo = s; }
  }
  assert.ok(cargado());
  assert.ok(vistos.length >= 4, `rotó ${vistos.length} veces`);
  for (let i = 1; i < vistos.length; i++) {
    assert.notEqual(vistos[i].s, vistos[i - 1].s);
    if (i >= 2) {
      const dt = vistos[i].t - vistos[i - 1].t;
      assert.ok(dt >= 12 - 0.2 && dt <= 18 + 1.2, `intervalo ${dt}`);
    }
  }
  const usados = new Set(vistos.map((v) => v.s));
  assert.ok(usados.size === 3, [...usados].join(','));

  // Fuera de normal no rota
  mod.alEmocion('happy');
  for (const v of [a, b]) if (v.oyentes('canplay')) v.disparar('canplay');
  tm.avanzar(400);
  const antes = mod.api.estado().src;
  for (let i = 0; i < 400; i++) { mod.tick(0.1, t += 0.1); tm.avanzar(100); }
  assert.equal(mod.api.estado().src, antes);

  // Sin json: nada
  const m2 = montar();
  assert.equal(await m2.mod.alIniciar(), 0);
  m2.mod.alEmocion('normal');
  for (const v of [m2.a, m2.b]) if (v.oyentes('canplay')) v.disparar('canplay');
  const cargas = m2.a.cargas + m2.b.cargas;
  for (let i = 0; i < 400; i++) { m2.mod.tick(0.1, i * 0.1); m2.tm.avanzar(100); }
  assert.equal(m2.a.cargas + m2.b.cargas, cargas);
});

test('pausar: alDetener pausa el visible y alIniciar lo reanuda (salvo pausa manual)', async () => {
  const { a, mod } = montar();
  mod.alEmocion('happy');
  a.disparar('canplay');
  const pausas = a.pausas;
  mod.alDetener();
  assert.equal(a.pausas, pausas + 1);
  assert.ok(mod.api.estado().pausado);
  await mod.alIniciar();
  assert.ok(!mod.api.estado().pausado);
  mod.api.pausar(true);
  await mod.alIniciar();
  assert.ok(mod.api.estado().pausado);
});

test('buscarVideos: con solo el #v de siempre crea #vb a su lado; asegurarZzz una vez', () => {
  const stage = crearElemento('div', 'stage');
  const v = crearElemento('video', 'v');
  stage.appendChild(v);
  const doc = crearDocumento(stage);
  const [a, b] = buscarVideos(stage, doc);
  assert.equal(a, v);
  assert.equal(b.id, 'vb');
  assert.equal(stage.children[1], b);
  assert.ok(a.classList.contains('lune-vid') && b.classList.contains('lune-vid'));
  assert.equal(b.getAttribute('preload'), 'auto');
  const z1 = asegurarZzz(stage, doc);
  const z2 = asegurarZzz(stage, doc);
  assert.equal(z1, z2);
  assert.equal(asegurarZzz(null, doc), null);
});

test('publicar: window.setEmocion pasa por el registro y aplica la emoción pendiente', () => {
  const llamadas = [];
  const reg = { emocion: (s) => llamadas.push(s) };
  const win = { __luneEmocionPendiente: 'wave' };
  publicar(win, reg);
  assert.deepEqual(llamadas, ['wave']);
  assert.equal(win.__luneEmocionPendiente, null);
  win.setEmocion('happy');
  assert.deepEqual(llamadas, ['wave', 'happy']);
});

// ── CSS ─────────────────────────────────────────────────────────────────────────

test('mascota_anim.css: doble búfer con .lune-doble, fundido por variable y colores con respaldo', () => {
  const css = readFileSync(CSS, 'utf8');
  const sinComentarios = css.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.match(sinComentarios, /#stage\.lune-doble \.lune-vid\s*\{[^}]*opacity:\s*0/);
  assert.match(sinComentarios, /\.lune-doble \.lune-vid\.activo\s*\{[^}]*opacity:\s*1/);
  assert.match(sinComentarios, /var\(--lune-fundido/);
  assert.match(sinComentarios, /\.lune-sueno-sustituto\s*\{[^}]*brightness\(\.75\)/);
  assert.match(sinComentarios, /\.lune-zzz/);
  const usos = [...sinComentarios.matchAll(/var\(--([a-z]+-\d+)-rgb([^)]*)\)/g)];
  assert.ok(usos.length > 0);
  for (const [, nombre, resto] of usos) assert.ok(resto.trim().startsWith(','), `var(--${nombre}-rgb) sin respaldo`);
  assert.ok(!/rgba\(\s*0\s*,\s*229\s*,\s*255/.test(sinComentarios), 'nada de cian literal');
  // El registro es el dueño de transform/filter/opacity de #stage: el CSS no los declara
  for (const regla of sinComentarios.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const sel = regla[1].trim();
    if (/#stage(\.[\w-]+|\[[^\]]+\])*$/.test(sel)) {
      assert.ok(!/(^|;|\s)(transform|filter|opacity)\s*:/.test(regla[2]), `${sel} no debe tocar transform/filter/opacity`);
    }
  }
});
