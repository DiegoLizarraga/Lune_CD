// tests/js/sfx.test.mjs — efectos de sonido WebAudio (ui_web/lune_sfx.js).
// Script clásico evaluado en un contexto vm con AudioContext y fetch falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const CODIGO = readFileSync(fileURLToPath(new URL('../../ui_web/lune_sfx.js', import.meta.url)), 'utf8');

function pagina({ existentes = ['drag_start.wav', 'trago_1.wav', 'trago_2.wav', 'alarma_1.wav'], conAudio = true } = {}) {
  const pedidas = [];
  const fuentes = [];
  const decodificados = [];
  class Param { constructor(v) { this.value = v; } setTargetAtTime(v) { this.value = v; } }
  class Nodo { constructor() { this.conectado = []; } connect(n) { this.conectado.push(n); } disconnect() { this.conectado = []; } }
  class FalsoAudioContext {
    constructor() { this.state = 'running'; this.currentTime = 0; this.destination = new Nodo(); }
    createGain() { const g = new Nodo(); g.gain = new Param(1); return g; }
    createBufferSource() {
      const f = new Nodo();
      f.playbackRate = new Param(1);
      f.parado = false; f.empezado = false;
      f.start = () => { f.empezado = true; };
      f.stop = () => { f.parado = true; };
      fuentes.push(f);
      return f;
    }
    decodeAudioData(datos) { decodificados.push(datos); return Promise.resolve({ buffer: datos }); }
    resume() { this.state = 'running'; return Promise.resolve(); }
  }
  const win = {
    document: { currentScript: { src: 'http://127.0.0.1:8000/lune_sfx.js' } },
    fetch: (u) => {
      pedidas.push(u);
      const archivo = u.split('/').pop();
      return Promise.resolve(existentes.includes(archivo)
        ? { ok: true, status: 200, arrayBuffer: () => Promise.resolve(archivo) }
        : { ok: false, status: 404 });
    },
    console: { warn: () => {} },
    Promise, URL, Date, Math,
  };
  if (conAudio) win.AudioContext = FalsoAudioContext;
  win.window = win;
  vm.createContext(win);
  vm.runInContext(CODIGO, win, { filename: 'lune_sfx.js' });
  return { w: win, sfx: win.luneSfx, pedidas, fuentes, decodificados };
}

test('la base sale de la ubicación del script y el nombre sin extensión es .wav', () => {
  const { sfx } = pagina();
  assert.equal(sfx.url('drag_start'), 'http://127.0.0.1:8000/assets/sfx/drag_start.wav');
  assert.equal(sfx.url('musica/intro.ogg'), 'http://127.0.0.1:8000/assets/sfx/musica/intro.ogg');
  assert.equal(sfx.url('/bailes/x.mp3'), '/bailes/x.mp3');
  sfx.setBase('packs/gato');
  assert.equal(sfx.url('blip'), 'packs/gato/blip.wav');
});

test('tocar descarga y decodifica una vez (caché por URL) y aplica volumen y tono en el rango', async () => {
  const { sfx, pedidas, fuentes, decodificados } = pagina();
  const valores = [0, 0.5, 1 - 1e-9];
  let i = 0;
  sfx.aleatorio = () => valores[i++ % valores.length];
  const h1 = await sfx.tocar('drag_start', { vol: 0.4, pitch: [0.9, 1.1] });
  await sfx('drag_start', { pitch: [0.9, 1.1] });            // también se puede llamar directamente
  await sfx.tocar('drag_start', { pitch: [0.9, 1.1], vol: 9 });
  assert.equal(pedidas.length, 1, 'una sola descarga');
  assert.equal(decodificados.length, 1, 'una sola decodificación');
  assert.equal(fuentes.length, 3);
  assert.ok(fuentes.every((f) => f.empezado));
  assert.deepEqual(fuentes.map((f) => Math.round(f.playbackRate.value * 1000) / 1000), [0.9, 1, 1.1]);
  assert.equal(fuentes[0].conectado[0].gain.value, 0.4);
  assert.equal(fuentes[2].conectado[0].gain.value, 2, 'volumen acotado');
  assert.equal(typeof h1.detener, 'function');
  h1.detener();
  assert.equal(fuentes[0].parado, true);
});

test('una lista de nombres elige uno al azar; el volumen maestro se acota a 0..1', async () => {
  const { sfx, pedidas } = pagina();
  sfx.aleatorio = () => 0.99;
  await sfx.tocar(['trago_1', 'trago_2']);
  assert.ok(pedidas[0].endsWith('/trago_2.wav'));
  assert.equal(sfx.setVolumen(1.7), 1);
  assert.equal(sfx.setVolumen(-1), 0);
  assert.equal(sfx.setVolumen('nada'), 0, 'un valor no numérico no cambia nada');
  assert.equal(sfx.setVolumen(0.6), 0.6);
  assert.equal(sfx.getVolumen(), 0.6);
});

test('canales y bucle: detenerCanal solo para los de ese canal', async () => {
  const { sfx, fuentes } = pagina();
  await sfx.tocar('alarma_1', { bucle: true, canal: 'alarma' });
  await sfx.tocar('drag_start');
  assert.equal(fuentes[0].loop, true);
  assert.equal(sfx.sonando(), 2);
  sfx.detenerCanal('alarma');
  assert.equal(fuentes[0].parado, true);
  assert.equal(fuentes[1].parado, false);
  assert.equal(sfx.sonando(), 1);
  sfx.detenerTodo();
  assert.equal(sfx.sonando(), 0);
});

test('archivo que falta o sin WebAudio → null sin lanzar, y no se reintenta enseguida', async () => {
  const { sfx, pedidas } = pagina();
  assert.equal(await sfx.tocar('no_existe'), null);
  assert.equal(await sfx.tocar('no_existe'), null);
  assert.equal(pedidas.length, 1, 'el fallo reciente no se vuelve a pedir');
  const sinAudio = pagina({ conAudio: false });
  assert.equal(await sinAudio.sfx.tocar('drag_start'), null);
  assert.equal(sinAudio.pedidas.length, 0);
});

test('cargar el script dos veces conserva la misma instancia', () => {
  const { w, sfx } = pagina();
  vm.runInContext(CODIGO, w);
  assert.equal(w.luneSfx, sfx);
});
