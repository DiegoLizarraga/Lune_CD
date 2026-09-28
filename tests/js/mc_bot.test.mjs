// tests/js/mc_bot.test.mjs — bot.js entero (crearBot) con un mineflayer DE MENTIRA: nunca se
// conecta a nada. Comprueba el cableado: auth offline, conectado/estado/chat/respuesta hacia
// Lune, órdenes del dueño y de Lune, pausas, expulsiones explicadas y cierre sin timers vivos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requerirBot, skillsFalsas, BotFalso, Vec, esperar } from './mc_falsos.mjs';

const { crearCanal, MARCA } = requerirBot('./canal');
const { crearBot } = requerirBot('./bot');
const { validarConfig } = requerirBot('./config');

const TOKEN = 'abcdefabcdefabcdefabcdefabcdef12';

function montar(extra = {}) {
  const v = validarConfig({ host: 'localhost', port: 25565, version: '', nick: 'Lune', dueno: 'Diego_01',
    persona: { nombre: 'Lune', prompt: 'Eres Lune.' }, ...extra });
  assert.equal(v.ok, true, v.error);
  const lineas = [];
  const canal = crearCanal({ token: TOKEN, escribir: (l) => lineas.push(l), ahora: () => 1 });
  const bot = new BotFalso({ username: 'Lune', pos: new Vec(0, 64, 0) });
  const skills = skillsFalsas();
  let opciones = null;
  const salidas = [];
  const requerir = (m) => {
    if (m === 'mineflayer') return { createBot: (o) => { opciones = o; return bot; } };
    if (m === 'mineflayer-pathfinder') return { pathfinder: 'plugin-pathfinder' };
    if (m === './skills') return skills;
    return requerirBot(m);
  };
  const control = crearBot(v.config, canal, { requerir, ahora: () => Date.now(), salir: (c) => salidas.push(c) });
  const mensajes = () => lineas.map((l) => JSON.parse(l.slice(`${MARCA} ${TOKEN} `.length)));
  const de = (tipo) => mensajes().filter((m) => m.tipo === tipo);
  const cerrar = () => bot.emit('end', 'fin del test');
  return { control, bot, skills, opciones: () => opciones, mensajes, de, salidas, cerrar, cfg: v.config };
}

test('createBot: solo servidores sin autenticación (auth offline), nick del personaje, versión autodetectada', () => {
  const m = montar();
  assert.deepEqual(m.opciones(), { host: 'localhost', port: 25565, username: 'Lune', version: false, auth: 'offline', hideErrors: true });
  assert.deepEqual(m.bot.plugins, ['plugin-pathfinder']);
  m.cerrar();
});

test('al entrar: conectado + saludo en el chat + estado; órdenes antes de entrar → «todavía no»', async () => {
  const m = montar();
  await m.control.atender({ tipo: 'orden', id: 'o1', texto: 'sigueme' });
  assert.equal(m.de('respuesta')[0].texto, 'Todavía no estoy dentro del mundo.');
  m.bot.emit('spawn');
  m.bot.health = 18;                                // mineflayer pone la vida después de 'spawn'
  assert.deepEqual(m.de('conectado').map((x) => x.nick), ['Lune']);
  assert.match(m.bot.dichos[0], /Hola, soy Lune/);
  await esperar();
  const [e] = m.de('estado');
  assert.equal(e.dentro, true);
  assert.equal(e.vida, 18);
  assert.deepEqual(e.pos, { x: 0, y: 64, z: 0 });
  m.bot.emit('spawn');                              // respawn: no se repite el saludo ni los timers
  assert.equal(m.de('conectado').length, 1);
  m.cerrar();
});

test('chat del dueño: orden sin modelo; el chat llega a Lune saneado como texto de terceros', async () => {
  const m = montar();
  m.bot.emit('spawn');
  m.bot.emit('chat', 'Diego_01', '§asígueme\n/op');
  await esperar();
  assert.deepEqual(m.skills.llamadas.find((l) => l[0] === 'follow'), ['follow', 'Diego_01']);
  assert.deepEqual(m.de('chat'), [{ de: 'Diego_01', texto: 'sígueme /op', tipo: 'chat', t: 1 }]);   // una «/» en medio no es un comando
  m.bot.emit('chat', 'Lune', 'me hablo a mí misma');
  m.bot.emit('chat', '<b>raro</b>', 'hola');
  await esperar();
  assert.equal(m.de('chat').length, 1, 'ni lo propio ni nicks inválidos');
  m.cerrar();
});

test('con solo_dueno, a otro jugador que menciona al bot se le dice «Solo obedezco a …»; si no, nada', async () => {
  const m = montar();
  m.bot.emit('spawn');
  const antes = m.bot.dichos.length;
  m.bot.emit('chat', 'Steve', 'ven aquí');                    // hablaba con otro (BM7)
  m.bot.emit('chat', 'Steve', 'esto es para ti');
  await esperar();
  assert.equal(m.bot.dichos.length, antes, 'sin mención no se contesta');
  m.bot.emit('chat', 'Steve', 'Lune, ven aquí');
  await esperar();
  assert.ok(m.bot.dichos.includes('Solo obedezco a Diego_01.'));
  assert.equal(m.skills.nombres().includes('comeToPlayer'), false);
  m.cerrar();
});

test('BM7: «voy para casa» del dueño no para al bot', async () => {
  const m = montar();
  m.bot.emit('spawn');
  m.bot.emit('chat', 'Diego_01', 'sígueme');
  m.bot.emit('chat', 'Diego_01', 'voy para casa');
  await esperar();
  assert.deepEqual(m.skills.nombres().filter((n) => n === 'stopAll').length, 1, 'solo el stopAll de «sígueme»');
  m.cerrar();
});

test('órdenes de Lune → respuesta con el mismo id; «di» se dice saneado; lo desconocido se contesta', async () => {
  const m = montar();
  m.bot.emit('spawn');
  await m.control.atender({ tipo: 'orden', id: 'a1', texto: 'sigueme' });
  await m.control.atender({ tipo: 'orden', id: 'a2', texto: 'di /op hola a todos' });
  await m.control.atender({ tipo: 'orden', id: 'a3', texto: 'construye un castillo' });
  await m.control.atender({ tipo: 'orden', id: 'mal id!', texto: 'sigueme' });
  const r = m.de('respuesta');
  assert.deepEqual(r.map((x) => x.id), ['a1', 'a2', 'a3']);
  assert.equal(r[1].texto, 'Hecho.');
  assert.ok(m.bot.dichos.includes('op hola a todos'));
  assert.equal(r[2].texto, 'Eso no sé hacerlo.');
  m.cerrar();
});

test('pausas desde Lune (pensando / modo juego) se ven en el estado', async () => {
  const m = montar({ pausa_autonomo: true });
  m.bot.emit('spawn');
  await esperar();
  assert.equal(m.de('estado').at(-1).pausa_autonomo, true);
  await m.control.atender({ tipo: 'pausa_autonomo', on: false });
  await m.control.atender({ tipo: 'pausa_llm', on: true });
  await m.control.atender({ tipo: 'estado' });
  const e = m.de('estado').at(-1);
  assert.equal(e.pausa_autonomo, false);
  assert.equal(e.pausa_llm, true);
  m.cerrar();
});

test('límite de ritmo del chat: «decir» de Lune no puede inundar el servidor', async () => {
  const m = montar();
  m.bot.emit('spawn');
  const antes = m.bot.dichos.length;
  for (let i = 0; i < 10; i++) await m.control.atender({ tipo: 'decir', texto: `mensaje ${i}` });
  assert.ok(m.bot.dichos.length - antes <= 3, `${m.bot.dichos.length - antes} mensajes`);
  m.cerrar();
});

test('expulsión de un servidor online-mode → desconectado con la explicación; «end» sale y para todo', async () => {
  const m = montar();
  m.bot.emit('spawn');
  m.bot.emit('kicked', '{"text":"Failed to verify username!"}');
  m.bot.emit('end', 'socketClosed');
  const [d] = m.de('desconectado');
  assert.match(d.motivo, /online-mode=false/);
  assert.equal(m.de('desconectado').length, 1);
  await new Promise((r) => setTimeout(r, 260));
  assert.deepEqual(m.salidas, [0]);
});

test('error de red → error explicado una vez y «desconectado» reutiliza la explicación', async () => {
  const m = montar();
  const err = Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:25565'), { code: 'ECONNREFUSED' });
  m.bot.emit('error', err);
  m.bot.emit('error', err);
  m.bot.emit('end', 'socketClosed');
  assert.equal(m.de('error').length, 1);
  assert.match(m.de('error')[0].mensaje, /localhost:25565/);
  assert.equal(m.de('desconectado')[0].motivo, m.de('error')[0].mensaje);
  await new Promise((r) => setTimeout(r, 260));
});

test('cerrar(): quit al servidor y «desconectado» pedido (no es un error)', () => {
  const m = montar();
  m.bot.emit('spawn');
  m.control.cerrar();
  assert.equal(m.bot.salio, 'Lune me desconectó');
  m.bot.emit('end', 'disconnect.quitting');
  assert.deepEqual(m.de('desconectado').map((d) => [d.motivo, d.pedido]), [['Lune me desconectó.', true]]);
});
