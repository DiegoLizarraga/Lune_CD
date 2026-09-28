// tests/js/mc_comandos.test.mjs — órdenes del chat y de Lune (minecraft-bot/src/commands.js) por
// inyección: habilidades de mentira, minecraft-data de mentira y un bot EventEmitter. Sin mineflayer.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requerirBot, skillsFalsas, mcDataFalso, BotFalso, Vec, reloj, esperar } from './mc_falsos.mjs';

const { crearComandos, interpretar, clean } = requerirBot('./commands');
const { crearCharla } = requerirBot('./chatter');

function montar({ soloDueno = true, nombres = ['Lune'], entidades = {} } = {}) {
  const skills = skillsFalsas({ entidades });
  const dichos = [];
  const r = reloj();
  const charla = crearCharla({ decir: (t) => dichos.push(t), ahora: r.ahora, azar: () => 0, nombre: 'Lune' });
  const cmd = crearComandos({
    skills, mcData: mcDataFalso(), charla, decir: (t) => { dichos.push(t); return true; },
    dueno: 'Diego_01', soloDueno, nombres, ahora: r.ahora,
  });
  const bot = new BotFalso();
  return { cmd, skills, dichos, bot, r };
}

test('el dueño es FIJO: que hable otro no lo cambia (Another-craft lo cambiaba)', async () => {
  const { cmd, skills, bot } = montar({ soloDueno: false });
  await cmd.handleCommand(bot, 'Steve', 'hola');
  await cmd.handleCommand(bot, 'Diego_01', 'sígueme');
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'follow'), ['follow', 'Diego_01']);
  assert.equal(cmd.esDueno('diego_01'), true);
  assert.equal(cmd.esDueno('Steve'), false);
});

test('solo_dueno: una orden de otro QUE MENCIONA al bot se contesta «Solo obedezco a …» y no se hace', async () => {
  const { cmd, skills, bot } = montar();
  for (const texto of ['Lune, sígueme', 'lune ven aquí', 'mina hierro Lune', 'Lune ataca zombi', 'Lune, dame madera',
    '¿dónde estás, Lune?', 'oye Lune inventario']) {
    const r = await cmd.handleCommand(bot, 'Steve', texto);
    assert.equal(r.handled, true, texto);
  }
  assert.deepEqual(skills.nombres().filter((n) => n !== 'nearestHostile'), []);
  const { cmd: cmd2, bot: bot2 } = montar();
  assert.equal((await cmd2.handleCommand(bot2, 'Steve', 'Lune, sígueme')).reply, 'Solo obedezco a Diego_01.');
});

test('BM7: a un jugador que NO menciona al bot no se le contesta (ni «Solo obedezco…»)', async () => {
  const { cmd, skills, bot, dichos } = montar();
  for (const texto of ['esto es para ti', 'espera un momento', 'ven aquí', 'sígueme', 'para', 'mina hierro', '¡hola!',
    'gracias', 'voy para casa', 'come algo y vuelve']) {
    assert.equal(await cmd.handleCommand(bot, 'Steve', texto), null, texto);
  }
  assert.deepEqual(skills.nombres(), []);
  assert.deepEqual(dichos, []);
});

test('BM7: del dueño solo cuenta la orden AL PRINCIPIO; «para» solo si es todo el mensaje', async () => {
  const { cmd, skills, bot } = montar();
  for (const texto of ['voy para casa', 'esto es para ti', 'espera un momento que vuelvo', 'para qué sirve esto',
    'luego te sigo', 'qué bonito, ven a verlo', 'mañana minamos hierro']) {
    assert.equal(await cmd.handleCommand(bot, 'Diego_01', texto), null, texto);
  }
  assert.deepEqual(skills.nombres(), [], 'nada se ha parado ni movido');
  for (const texto of ['¡para!', 'para ya', 'Lune, para', 'para, Lune', 'quédate ahí', 'espera']) {
    const r = await cmd.handleCommand(bot, 'Diego_01', texto);
    assert.equal(r && r.handled, true, texto);
  }
  assert.equal(skills.nombres().filter((n) => n === 'stopAll').length, 6);
  const { cmd: c2, skills: s2, bot: b2 } = montar();
  await c2.handleCommand(b2, 'Diego_01', 'oye Lune, sígueme porfa');
  await c2.handleCommand(b2, 'Diego_01', 'mina 3 hierro, Lune');
  assert.deepEqual(s2.llamadas.find((l) => l[0] === 'follow'), ['follow', 'Diego_01']);
  assert.deepEqual(s2.llamadas.find((l) => l[0] === 'mineNearest'), ['mineNearest', 'iron_ore', 3]);
  assert.equal(await c2.handleCommand(b2, 'Diego_01', 'Lune, voy para casa'), null, 'mencionado pero sin orden: al modelo');
});

test('solo_dueno: los demás sí reciben respuestas sociales si mencionan al bot', async () => {
  const { cmd, bot } = montar();
  const r = await cmd.handleCommand(bot, 'Steve', '¡hola, Lune!');
  assert.equal(r.handled, true);
  assert.equal(typeof r.reply, 'string');
  assert.ok(r.reply.length > 0);
  const chiste = await montar().cmd.handleCommand(bot, 'Steve', 'Lune, cuéntame un chiste');
  assert.ok(chiste.reply);
});

test('sin solo_dueno, otro jugador puede pedir que lo siga (a él) mencionándolo', async () => {
  const { cmd, skills, bot } = montar({ soloDueno: false });
  assert.equal(await cmd.handleCommand(bot, 'Steve', 'sigueme'), null, 'sin mención: hablaba con otro');
  await cmd.handleCommand(bot, 'Steve', 'Lune sigueme');
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'follow'), ['follow', 'Steve']);
});

test('nunca ataca a jugadores ni a lo que no está en la lista blanca', async () => {
  const { cmd, skills, bot } = montar();
  bot.jugador('Steve', new Vec(2, 64, 0));
  for (const [texto, esperado] of [['ataca player', 'A jugadores no los ataco.'], ['ataca a Steve', 'A jugadores no los ataco.'],
    ['mata al aldeano', 'Eso no lo ataco.'], ['ataca armor_stand', 'Eso no lo ataco.'], ['ataca al perro', 'Eso no lo ataco.']]) {
    const r = await cmd.handleCommand(bot, 'Diego_01', texto);
    assert.equal(r.reply, esperado, texto);
  }
  assert.equal(skills.nombres().includes('attackNearest'), false);
  await cmd.handleCommand(bot, 'Diego_01', 'ataca al zombi');
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'attackNearest'), ['attackNearest', 'zombie']);
});

test('«mina hierro» es minar aunque el bot se llame Mina; la mención usa nick y personaje', async () => {
  const { cmd, skills, bot } = montar({ nombres: ['Mina', 'Lune'] });
  const r = await cmd.handleCommand(bot, 'Diego_01', 'mina hierro');
  assert.equal(r.handled, true);
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'mineNearest'), ['mineNearest', 'iron_ore', 1]);
  assert.equal(await cmd.handleCommand(bot, 'Diego_01', 'mina, ¿qué tal?'), null, 'no es una orden: la piensa el modelo');
  assert.equal(cmd.mencionado('Mina, ¿qué tal?'), true);
  assert.equal(cmd.mencionado('hola lune'), true);
  assert.equal(cmd.mencionado('LUNE!'), true);
  assert.equal(cmd.mencionado('los lunes llueve'), false, 'palabra entera, con letras Unicode');
  assert.equal(cmd.mencionado('minando'), false);
  assert.equal(cmd.mencionado('Lúne'), false);
});

test('órdenes de Lune: cuentan como del dueño y solo ellas pueden usar «di»', async () => {
  const { cmd, skills, bot, dichos } = montar();
  await cmd.handleCommand(bot, 'Diego_01', 'sigueme', { origen: 'lune' });
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'follow'), ['follow', 'Diego_01']);
  const r = await cmd.handleCommand(bot, 'Diego_01', 'di /op a todos §c<b>hola</b>', { origen: 'lune' });
  assert.equal(r.handled, true);
  assert.equal(dichos.at(-1), 'op a todos <b>hola</b>', 'saneado: sin «/» ni colores (el juego no interpreta HTML)');
  const n = dichos.length;
  const deJugador = await cmd.handleCommand(bot, 'Diego_01', 'di algo raro');
  assert.equal(dichos.length, n, 'un jugador no hace que el bot repita lo que quiera');
  assert.equal(deJugador, null);
});

test('«dame» solo al dueño; sin solo_dueno, otro recibe una negativa', async () => {
  const { cmd, skills, bot } = montar({ soloDueno: false });
  const otro = await cmd.handleCommand(bot, 'Steve', 'Lune, dame madera');
  assert.equal(otro.reply, 'Solo le doy cosas a Diego_01.');
  await cmd.handleCommand(bot, 'Diego_01', 'dame madera');
  await esperar();
  assert.deepEqual(skills.llamadas.find((l) => l[0] === 'dropItem'), ['dropItem', 'oak_log', 'Diego_01']);
});

test('lo que no es una orden devuelve null; «para» detiene todo', async () => {
  const { cmd, skills, bot } = montar();
  assert.equal(await cmd.handleCommand(bot, 'Diego_01', 'qué bonito atardecer'), null);
  assert.equal(await cmd.handleCommand(bot, 'Diego_01', ''), null);
  bot.lune.busy = true;
  await cmd.handleCommand(bot, 'Diego_01', '¡para!');
  assert.equal(bot.lune.busy, false);
  assert.ok(skills.nombres().includes('stopAll'));
});

test('respuestas sociales con anti-spam (2.5 s)', async () => {
  const { cmd, bot, r } = montar({ soloDueno: false });
  const a = await cmd.handleCommand(bot, 'Steve', 'hola Lune');
  const b = await cmd.handleCommand(bot, 'Alex', 'hola Lune');
  assert.ok(a.reply);
  assert.equal(b.reply, null);
  r.avanzar(2600);
  assert.ok((await cmd.handleCommand(bot, 'Alex', 'gracias, Lune')).reply);
});

test('interpretar y clean: sin tildes ni signos; cantidades acotadas', () => {
  assert.equal(clean('¿Dónde ESTÁS?'), 'donde estas');
  const real = (w) => (w === 'hierro' ? 'iron_ore' : null);
  assert.deepEqual(interpretar('mina 500 hierro', { realBlock: real, realMob: () => null }), { tipo: 'mina', bloque: 'iron_ore', cantidad: 64 });
  assert.equal(interpretar('di hola', { realBlock: real, realMob: () => null }), null, 'un jugador no hace hablar al bot');
  assert.equal(interpretar('di hola', { realBlock: real, realMob: () => null, origen: 'lune' }).tipo, 'di');
});
