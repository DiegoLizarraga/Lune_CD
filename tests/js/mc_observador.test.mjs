// tests/js/mc_observador.test.mjs — eventos del bot para Lune (minecraft-bot/src/observador.js)
// con un bot de mentira (EventEmitter), reloj e intervalo falsos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { requerirBot, BotFalso, Vec, reloj } from './mc_falsos.mjs';

const { crearObservador, leerMensaje } = requerirBot('./observador');

function montar() {
  const bot = new BotFalso({ username: 'Lune', pos: new Vec(0, 64, 0) });
  const emitidos = [];
  const r = reloj();
  const intervalos = [];
  const o = crearObservador({
    bot, dueno: 'Diego_01', emitir: (tipo, datos) => { emitidos.push({ tipo, ...datos }); return true; }, ahora: r.ahora,
    setInterval: (fn, ms) => { intervalos.push({ fn, ms, vivo: true }); return intervalos.length; },
    clearInterval: (id) => { intervalos[id - 1].vivo = false; },
  });
  o.start();
  const eventos = () => emitidos.map((e) => [e.evento, e.jugador, e.detalle]);
  return { bot, o, emitidos, eventos, r, intervalos };
}

const texto = (t) => ({ toString: () => t });

test('muerte y logro del dueño con translate (como los da mineflayer)', () => {
  const { bot, eventos, emitidos } = montar();
  bot.emit('message', { translate: 'death.attack.mob', with: [texto('Diego_01'), texto('Zombie')] }, 'system');
  bot.emit('message', { translate: 'chat.type.advancement.task', with: [texto('Diego_01'), texto('[Diamonds!]')] }, 'system');
  assert.deepEqual(eventos(), [['muerte', 'Diego_01', 'Zombie'], ['logro', 'Diego_01', 'Diamonds!']]);
  assert.ok(emitidos.every((e) => e.tipo === 'evento'));
});

test('sin translate: los mismos patrones que el log, en español e inglés', () => {
  const { bot, eventos } = montar();
  bot.emit('message', texto('Diego_01 fue asesinado por Zombi'), 'system');
  bot.emit('message', texto('Diego_01 ha conseguido el progreso [¡Diamantes!]'), 'system');
  bot.emit('message', texto('Diego_01 drowned'), 'system');
  assert.deepEqual(eventos(), [['muerte', 'Diego_01', 'Zombi'], ['logro', 'Diego_01', '¡Diamantes!'], ['muerte', 'Diego_01', '']]);
});

// Textos REALES del juego (lang es_* y en_us de 1.20.1–1.21.11; solo plantillas, sin logs ni nicks
// de nadie): los mismos que prueba tests/test_minecraft_log.py contra el lector del log.
const TEXTOS = JSON.parse(readFileSync(new URL('../datos/minecraft_textos_1_21.json', import.meta.url), 'utf8'));
const ASESINO_RARO = new Set(['%1$s cayó desde muy alto y %2$s acabó con él usando %3$s', '%1$s fue disparado(a) por un esqueleto %2$s',
  '%1$s fue víctima de %2$ss usando %3$s', '%1$s murió por arte de magia mientras trataba de escapar de de %2$s']);
const rellenar = (p) => p.replaceAll('%1$s', 'Alex_22').replaceAll('%2$s', 'Zombi').replaceAll('%3$s', '[Espada de hierro]');

test('sin translate: TODAS las muertes reales del juego (es_mx con «/a», es_es, en_us) y quién mata', () => {
  for (const grupo of ['muertes_es', 'muertes_en']) {
    assert.ok(TEXTOS[grupo].length > 100);
    const fallan = [];
    const asesinoMal = [];
    for (const p of TEXTOS[grupo]) {
      const e = leerMensaje(texto(rellenar(p)));
      if (!e || e.tipo !== 'muerte' || e.jugador !== 'Alex_22') fallan.push(p);
      else if (p.includes('%2$s') && !ASESINO_RARO.has(p) && e.detalle !== 'Zombi') asesinoMal.push([p, e.detalle]);
    }
    assert.deepEqual(fallan, [], grupo);
    assert.deepEqual(asesinoMal, [], grupo);
  }
  for (const p of TEXTOS.logros) {
    const e = leerMensaje(texto(p.replace('%s', 'Alex_22').replace('%s', '[¡Diamantes!]')));
    assert.deepEqual({ ...e }, { tipo: 'logro', jugador: 'Alex_22', detalle: '¡Diamantes!' }, p);
  }
  assert.deepEqual({ ...leerMensaje(texto('Alex_22 fue asesinado/a por Zombi con su [Espada]')) },
    { tipo: 'muerte', jugador: 'Alex_22', detalle: 'Zombi' });
  assert.deepEqual({ ...leerMensaje(texto('Esqueleto ha tirado a Alex_22 desde muy alto')) },
    { tipo: 'muerte', jugador: 'Alex_22', detalle: 'Esqueleto' });
  for (const t of ['Alex_22 fue expulsado del servidor', 'Alex_22 ha recibido un kit', 'Alex_22 se fue a dormir']) {
    assert.equal(leerMensaje(texto(t)), null, t);
  }
});

test('el chat de jugadores, otros jugadores y el propio bot no generan eventos de dueño', () => {
  const { bot, eventos } = montar();
  bot.emit('message', texto('Diego_01 was slain by Zombie'), 'chat');
  bot.emit('message', { translate: 'death.attack.mob', with: [texto('Steve'), texto('Zombie')] }, 'system');
  bot.emit('message', { translate: 'death.attack.mob', with: [texto('Lune'), texto('Zombie')] }, 'system');
  bot.emit('message', { translate: 'death.attack.mob', with: [texto('<script>'), texto('x')] }, 'system');
  assert.deepEqual(eventos(), []);
  assert.equal(leerMensaje({ translate: 'chat.type.text', with: [texto('Diego_01'), texto('hola')] }), null);
});

test('día/noche al cambiar (no al empezar) y lluvia al empezar a llover', () => {
  const { bot, o, eventos, intervalos } = montar();
  assert.equal(intervalos[0].ms, 2000);
  o.revisar();
  bot.time.timeOfDay = 14000;
  o.revisar();
  o.revisar();
  bot.time.timeOfDay = 500;
  intervalos[0].fn();
  bot.isRaining = true;
  bot.emit('rain');
  bot.isRaining = false;
  bot.emit('rain');
  assert.deepEqual(eventos().map((e) => e[0]), ['noche', 'dia', 'lluvia']);
});

test('peligro: hostil a ≤8 bloques del dueño, como mucho cada 20 s', () => {
  const { bot, o, eventos, r } = montar();
  bot.jugador('Diego_01', new Vec(100, 64, 100));
  bot.mob(1, 'zombie', new Vec(120, 64, 100));
  bot.mob(2, 'cow', new Vec(101, 64, 100));
  o.revisarPeligro();
  assert.deepEqual(eventos(), [], 'lejos (20 bloques) o no hostil');
  bot.mob(3, 'skeleton', new Vec(105, 64, 100));
  o.revisarPeligro();
  r.avanzar(10_000);
  o.revisarPeligro();
  r.avanzar(11_000);
  o.revisarPeligro();
  assert.deepEqual(eventos(), [['peligro', 'Diego_01', 'skeleton'], ['peligro', 'Diego_01', 'skeleton']]);
});

test('lo del bot: muerte, mata, mineral, herida y nivel', () => {
  const { bot, eventos } = montar();
  bot.emit('death');
  bot.emit('entityDead', { name: 'zombie', position: new Vec(3, 64, 0) });
  bot.emit('entityDead', { name: 'zombie', position: new Vec(30, 64, 0) });
  bot.emit('entityDead', { name: 'cow', position: new Vec(1, 64, 0) });
  bot.emit('diggingCompleted', { name: 'deepslate_diamond_ore' });
  bot.emit('diggingCompleted', { name: 'stone' });
  bot.health = 13;
  bot.emit('health');
  bot.health = 12;
  bot.emit('health');
  bot.experience.level = 3;
  bot.emit('experience');
  bot.emit('experience');
  assert.deepEqual(eventos(), [
    ['bot_muerte', 'Lune', ''], ['bot_mata', 'Lune', 'zombie'], ['bot_mineral', 'Lune', 'diamond'],
    ['bot_herida', 'Lune', '13'], ['bot_nivel', 'Lune', '3'],
  ]);
});

test('stop quita los oyentes y el intervalo', () => {
  const { bot, o, intervalos, eventos } = montar();
  const antes = bot.listenerCount('message');
  o.stop();
  assert.equal(bot.listenerCount('message'), antes - 1);
  assert.equal(intervalos[0].vivo, false);
  bot.emit('death');
  assert.deepEqual(eventos(), []);
});
