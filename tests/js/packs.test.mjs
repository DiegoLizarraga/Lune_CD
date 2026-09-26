// tests/js/packs.test.mjs — packs de sonidos de reacción (ui_web/lune_packs.js).
// lune_sfx.js + lune_packs.js evaluados en un contexto vm con AudioContext, fetch,
// reloj y MutationObserver falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const SFX = leer('../../ui_web/lune_sfx.js');
const PACKS = leer('../../ui_web/lune_packs.js');
const DEFECTO_JSON = JSON.parse(leer('../../sonidos/default/pack.json'));

const ORIGEN = 'http://127.0.0.1:8000';

function pagina({ packs = {}, duracion = 0.5, conObserver = true } = {}) {
  const pedidas = [];
  const fuentes = [];
  const observadores = [];
  const btxt = { textContent: '' };
  class Param { constructor(v) { this.value = v; } setTargetAtTime(v) { this.value = v; } }
  class Nodo { constructor() { this.conectado = []; } connect(n) { this.conectado.push(n); } disconnect() { this.conectado = []; } }
  class FalsoAudioContext {
    constructor() { this.state = 'running'; this.currentTime = 0; this.destination = new Nodo(); }
    createGain() { const g = new Nodo(); g.gain = new Param(1); return g; }
    createBufferSource() {
      const f = new Nodo();
      f.playbackRate = new Param(1);
      f.parado = false;
      f.start = () => { f.url = f.buffer && f.buffer.url; };
      f.stop = () => { f.parado = true; };
      fuentes.push(f);
      return f;
    }
    decodeAudioData(datos) { return Promise.resolve({ url: datos, duration: duracion }); }
    resume() { return Promise.resolve(); }
  }
  class FalsoObserver {
    constructor(cb) { this.cb = cb; this.el = null; observadores.push(this); }
    observe(el) { this.el = el; }
    disconnect() { this.el = null; }
    disparar() { if (this.el) this.cb([]); }
  }
  const win = {
    document: {
      currentScript: { src: ORIGEN + '/lune_sfx.js' },
      baseURI: ORIGEN + '/companion.html',
      getElementById: (id) => (id === 'btxt' ? btxt : null),
    },
    fetch: (u) => {
      pedidas.push(u);
      if (Object.prototype.hasOwnProperty.call(packs, u)) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(packs[u]) });
      }
      if (/\.(wav|ogg)$/.test(u)) {
        return Promise.resolve({ ok: true, status: 200, arrayBuffer: () => Promise.resolve(u) });
      }
      return Promise.resolve({ ok: false, status: 404 });
    },
    console: { warn: () => {} },
    AudioContext: FalsoAudioContext,
    setInterval: () => 1,
    clearInterval: () => {},
    Promise, URL, Date, Math, Array, Object, Number, String, JSON,
  };
  if (conObserver) win.MutationObserver = FalsoObserver;
  win.window = win;
  vm.createContext(win);
  vm.runInContext(SFX, win, { filename: 'lune_sfx.js' });
  vm.runInContext(PACKS, win, { filename: 'lune_packs.js' });
  let reloj = 1000;
  win.luneSonidos.ahora = () => reloj;
  return {
    w: win, son: win.luneSonidos, sfx: win.luneSfx, pedidas, fuentes, observadores, btxt,
    avanzar: (ms) => { reloj += ms; },
    // URLs que han sonado (en orden), sin el origen.
    sonadas: () => fuentes.map((f) => String(f.url).replace(ORIGEN, '')),
  };
}

const base = (n) => '/assets/sfx/' + n;
// Arrays y objetos del contexto vm tienen otro prototipo: se comparan como JSON.
const plano = (x) => JSON.parse(JSON.stringify(x));

test('el pack por defecto de JS es el mismo que sonidos/default/pack.json', () => {
  const { son } = pagina();
  const d = son.defecto();
  assert.deepEqual(plano(d.eventos), DEFECTO_JSON.eventos);
  assert.deepEqual(plano(d.capas), DEFECTO_JSON.capas);
  assert.equal(son.pack().id, 'default');
  assert.ok(son.eventos().includes('tecleo'));
});

test('arrastre: clip del pack por defecto con tono 0.9–1.1 y volumen = propio × pack', async () => {
  const { son, sfx, fuentes, sonadas } = pagina();
  const valores = [0, 1 - 1e-9];
  let i = 0;
  sfx.aleatorio = () => valores[i++ % 2];
  son.setVolumen(0.5);
  const r = await son.tocar('arrastre_inicio');
  await son.tocar('arrastre_fin');
  assert.ok(r && r.voz && r.capa === null);
  assert.deepEqual(sonadas(), [base('drag_start.wav'), base('drag_stop.wav')]);
  assert.deepEqual(fuentes.map((f) => Math.round(f.playbackRate.value * 100) / 100), [0.9, 1.1]);
  assert.equal(fuentes[0].conectado[0].gain.value, 0.5);
  // Otros eventos, sin tono al azar.
  await son.tocar('beber');
  assert.equal(fuentes[2].playbackRate.value, 1);
  assert.equal(await son.tocar('no_existe'), null);
});

test('cargar(url) resuelve junto al pack.json, descarta rutas peligrosas y aplica el mapeo en ciclo', async () => {
  const url = ORIGEN + '/sonidos/gata/pack.json';
  const { son, sfx, sonadas } = pagina({
    packs: {
      [url]: {
        nombre: 'Gata', mapeo: 'ciclo', volumen: 0.8,
        eventos: {
          beber: ['glup_a.ogg', 'glup_b.wav', '../fuera.wav', 'http://malo/x.wav', 'x.mp3', 'a\\b.wav', '%2e%2e/y.wav', '//h/z.wav'],
          'Mal-Nombre': ['n.wav'],
        },
      },
    },
  });
  assert.equal(await son.cargar('/sonidos/gata/pack.json'), true);
  assert.equal(son.pack().nombre, 'Gata');
  assert.equal(son.pack().volumen, 0.8);
  const gata = ORIGEN + '/sonidos/gata/';
  assert.deepEqual(plano(son.clips('beber')), [gata + 'glup_a.ogg', gata + 'glup_b.wav', gata + 'glup_a.ogg'],
    'ciclo: 3 del de por defecto → a, b, a');
  assert.deepEqual(plano(son.clips('comer')), DEFECTO_JSON.eventos.comer, 'lo que no trae sigue con el de por defecto');
  assert.ok(!son.eventos().includes('Mal-Nombre'));
  sfx.aleatorio = () => 0.99;
  son.aleatorio = () => 0.4;               // índice 1 de 3
  await son.tocar('beber');
  assert.deepEqual(sonadas(), ['/sonidos/gata/glup_b.wav']);
});

test('mapeo reemplazar, base permitida y rechazos (base ajena, sin archivos, 404)', async () => {
  const u1 = ORIGEN + '/sonidos/r/pack.json';
  const u2 = ORIGEN + '/sonidos/malo/pack.json';
  const u3 = ORIGEN + '/sonidos/vacio/pack.json';
  const u4 = ORIGEN + '/sonidos/sfx/pack.json';
  const { son } = pagina({
    packs: {
      [u1]: { mapeo: 'reemplazar', eventos: { beber: ['uno.ogg'] } },
      [u2]: { base: 'C:/Users', eventos: { beber: ['uno.ogg'] } },
      [u3]: { eventos: { beber: ['nada.mp3'] } },
      [u4]: { base: 'ui_web/assets/sfx', eventos: { beber: ['blip.wav'] } },
    },
  });
  assert.equal(await son.cargar(u1), true);
  assert.deepEqual(plano(son.clips('beber')), [ORIGEN + '/sonidos/r/uno.ogg']);
  assert.equal(await son.cargar(u2), false, 'base no permitida');
  assert.equal(await son.cargar(u3), false, 'ningún archivo válido');
  assert.equal(await son.cargar(ORIGEN + '/sonidos/no/pack.json'), false, '404');
  assert.deepEqual(plano(son.clips('beber')), [ORIGEN + '/sonidos/r/uno.ogg'], 'se queda el pack anterior');
  assert.equal(await son.cargar(u4), true);
  assert.deepEqual(plano(son.clips('beber')), ['blip.wav', 'blip.wav', 'blip.wav'], 'relativo a assets/sfx/');
  son.reiniciar();
  assert.deepEqual(plano(son.clips('beber')), DEFECTO_JSON.eventos.beber);
});

test('cargar(objeto) de Python: URLs de la raíz; esquemas y «..» fuera', async () => {
  const { son } = pagina();
  const ok = await son.cargar({
    id: 'gata', nombre: 'Gata', mapeo: 'ciclo', volumen: 1, resuelto: true,
    eventos: { caricia: ['/sonidos/gata/miau.ogg', 'javascript:alert(1).wav', '/sonidos/../datos.wav', 'data:x.wav'] },
    capas: { caricia: ['/sonidos/gata/ronroneo.wav'] },
  });
  assert.equal(ok, true);
  assert.deepEqual(plano(son.clips('caricia')), ['/sonidos/gata/miau.ogg']);
  assert.deepEqual(plano(son.clips('caricia', true)), ['/sonidos/gata/ronroneo.wav']);
  assert.equal(son.pack().id, 'gata');
});

test('voz de reacción: solo si no suena otra ni la voz TTS; las capas siempre', async () => {
  const { son, sonadas, avanzar } = pagina({ duracion: 0.5 });
  await son.cargar({
    eventos: { caricia: ['/p/miau.ogg'] },
    capas: { caricia: ['/p/ronroneo.wav'] },
  });
  const a = son.tocar('caricia');
  const b = son.tocar('caricia');               // la primera aún está cargando: ocupada
  const [ra, rb] = await Promise.all([a, b]);
  assert.ok(ra.voz && ra.capa);
  assert.equal(rb.voz, null);
  assert.ok(rb.capa);
  avanzar(200);
  assert.equal((await son.tocar('caricia')).voz, null, 'sigue sonando (0.5 s)');
  avanzar(400);
  assert.ok((await son.tocar('caricia')).voz, 'ya acabó');
  avanzar(1000);
  son.hablando(true);
  const r = await son.tocar('caricia');
  assert.equal(r.voz, null, 'con TTS no hay voz de reacción');
  assert.ok(r.capa);
  son.hablando(false);
  assert.ok((await son.tocar('caricia')).voz);
  const s = sonadas();
  assert.equal(s.filter((u) => u === '/p/miau.ogg').length, 3);
  assert.equal(s.filter((u) => u === '/p/ronroneo.wav').length, 6);
});

test('tecleo: un blip cada 2 letras, tono 0.95–1.05, sin ráfagas y nunca con TTS', async () => {
  const { son, sfx, fuentes, observadores, btxt, avanzar } = pagina();
  sfx.aleatorio = () => 0;
  assert.equal(son.letras(1), 0);
  assert.equal(son.letras(1), 1, 'la 2ª letra suena');
  avanzar(10);
  assert.equal(son.letras(2), 0, 'menos de 35 ms desde el anterior');
  avanzar(40);
  assert.equal(son.letras(50), 1, 'un trozo grande da un solo blip');
  son.hablando(true);
  avanzar(100);
  assert.equal(son.letras(4), 0, 'con la voz TTS no hay tecleo');
  son.hablando(false);
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  assert.ok(fuentes.length >= 2);
  assert.ok(fuentes.every((f) => Math.abs(f.playbackRate.value - 0.95) < 1e-9));
  assert.ok(fuentes.every((f) => String(f.url).endsWith('/assets/sfx/blip.wav')));

  // Siguiendo #btxt con MutationObserver.
  assert.equal(son.tecleo(true), true);
  assert.equal(observadores.length, 1);
  const antes = fuentes.length;
  avanzar(100);
  btxt.textContent = 'Ho';
  observadores[0].disparar();
  avanzar(100);
  btxt.textContent = 'Hola';
  observadores[0].disparar();
  avanzar(100);
  btxt.textContent = 'x';                           // texto nuevo: vuelve a contar
  observadores[0].disparar();
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(fuentes.length - antes, 2);
  assert.equal(son.tecleo(false), false);
  assert.equal(observadores[0].el, null, 'se suelta el observador');
});

test('volumen: se acota a 0..1 y con 0 no suena nada', async () => {
  const { son, fuentes } = pagina();
  assert.equal(son.setVolumen(3), 1);
  assert.equal(son.setVolumen('x'), 1);
  assert.equal(son.setVolumen(0), 0);
  assert.equal(await son.tocar('beber'), null);
  assert.equal(son.letras(10), 0);
  assert.equal(fuentes.length, 0);
});

test('sin luneSfx no lanza; cargar el script dos veces conserva la instancia', async () => {
  const { w, son } = pagina();
  vm.runInContext(PACKS, w);
  assert.equal(w.luneSonidos, son);
  w.luneSfx = undefined;                        // (delete no llega al global del contexto vm)
  assert.equal(await son.tocar('beber'), null);
  assert.equal(son.letras(2), 0);
});
