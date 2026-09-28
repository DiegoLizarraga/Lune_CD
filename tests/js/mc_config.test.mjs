// tests/js/mc_config.test.mjs — validación de la configuración que Lune manda al bot
// (primera línea de stdin; minecraft-bot/src/config.js).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requerirBot } from './mc_falsos.mjs';

const { validarConfig, hostValido } = requerirBot('./config');

const BASE = { host: 'localhost', port: 25565, nick: 'Lune', dueno: 'Diego_01' };
const con = (extra) => validarConfig({ ...BASE, ...extra });
const error = (extra) => {
  const r = con(extra);
  assert.equal(r.ok, false, JSON.stringify(extra));
  return r.error;
};

test('una configuración mínima vale y lleva los valores por defecto', () => {
  const r = validarConfig(BASE);
  assert.equal(r.ok, true);
  assert.deepEqual(r.config, {
    host: 'localhost', port: 25565, version: '', nick: 'Lune', dueno: 'Diego_01', solo_dueno: true, defender: true,
    pensar_cada_s: 45, estilo: 'personaje', persona: { nombre: 'Lune', prompt: '', frases: {} }, llm: null,
    pausa_autonomo: false, pausa_llm: false,
  });
});

test('servidor: nombres, IPv4 e IPv6 sí; esquemas, rutas, espacios y cosas raras no', () => {
  for (const h of ['localhost', 'mc.example.com', 'pc-potente', '192.168.1.9', '::1', 'fe80::1']) assert.equal(hostValido(h), h, h);
  for (const h of ['', 'http://x.com', 'x.com/ruta', 'a b', 'x..com', '-x.com', 'user@host', '1.2.3.4:25565', 'a'.repeat(254), null]) {
    assert.equal(hostValido(h), '', String(h));
  }
  assert.match(error({ host: 'http://evil' }), /servidor/);
});

test('puerto, versión y pensar_cada_s fuera de rango se rechazan', () => {
  for (const port of [0, 70000, 'abc', 1.5, true, null]) assert.match(error({ port }), /puerto/);
  assert.equal(con({ version: '1.21.1' }).ok, true);
  assert.equal(con({ version: '1.20' }).ok, true);
  for (const version of ['latest', '1', '1.21.1-pre', 'v1.21']) assert.match(error({ version }), /versión/);
  assert.match(error({ pensar_cada_s: 29 }), /pensar_cada_s/);
  assert.match(error({ pensar_cada_s: 3601 }), /pensar_cada_s/);
  assert.equal(con({ pensar_cada_s: 30 }).config.pensar_cada_s, 30);
});

test('nick y dueño: 3–16 [A-Za-z0-9_]; el dueño es obligatorio y distinto del bot', () => {
  for (const nick of ['ab', 'con espacio', 'x'.repeat(17), 'Lúne', '']) assert.match(error({ nick }), /nick/);
  assert.match(error({ dueno: '' }), /dueño/);
  assert.match(error({ dueno: 'lune' }), /dueño/);
});

test('persona con emojis: se mide en unidades UTF-16, como la recorta Lune (largo_utf16)', () => {
  // 1000 emojis = 2000 unidades (.length): cabe justo; uno más, no. Lune (minecraft_proceso.py)
  // recorta a 2000 unidades UTF-16, así que lo que manda siempre pasa (antes recortaba a 2000
  // puntos de código = hasta 4000 unidades y el bot rechazaba la configuración).
  assert.equal(con({ persona: { prompt: '💎'.repeat(1000) } }).config.persona.prompt.length, 2000);
  assert.match(error({ persona: { prompt: '💎'.repeat(1001) } }), /2000/);
  // Los recortes (nombre ≤40, frases ≤120) nunca dejan medio emoji.
  const r = con({ persona: { nombre: 'a' + '💎'.repeat(30), prompt: '', frases: { join: ['b' + '🎉'.repeat(80)] } } });
  assert.equal(r.config.persona.nombre, 'a' + '💎'.repeat(19));
  assert.equal(r.config.persona.frases.join[0], 'b' + '🎉'.repeat(59));
  assert.ok(!/[\ud800-\udbff]$/.test(r.config.persona.nombre));
});

test('persona: ≤2000 caracteres; frases filtradas; estilo personaje o sobrio', () => {
  assert.match(error({ persona: { prompt: 'x'.repeat(2001) } }), /2000/);
  const r = con({ persona: { nombre: 'Lune\u0007', prompt: 'Eres Lune.', frases: { join: ['Hola {name}', 5, ''], 'mal-cat': ['x'], death: 'no-lista' } } });
  assert.equal(r.config.persona.nombre, 'Lune');
  assert.deepEqual(r.config.persona.frases, { join: ['Hola {name}'] });
  assert.equal(con({ estilo: 'SOBRIO' }).config.estilo, 'sobrio');
  assert.match(error({ estilo: 'kawaii' }), /estilo/);
});

test('booleans: solo_dueno y defender solo se apagan con false explícito', () => {
  assert.equal(con({ solo_dueno: 0 }).config.solo_dueno, true);
  assert.equal(con({ solo_dueno: false, defender: false }).config.solo_dueno, false);
  assert.equal(con({ pausa_autonomo: true }).config.pausa_autonomo, true);
});

test('llm: ollama, openrouter y compat con URL http(s); lo demás se rechaza', () => {
  const ollama = con({ llm: { proveedor: 'ollama', url: 'http://localhost:11434/', modelo: 'qwen', num_ctx: 8192 } });
  assert.equal(ollama.ok, true);
  assert.deepEqual(ollama.config.llm, { proveedor: 'ollama', url: 'http://localhost:11434', modelo: 'qwen', clave: '', keep_alive: '30m', num_ctx: 8192, timeout_ms: 20000 });
  assert.match(error({ llm: { proveedor: 'gpt', url: 'http://x', modelo: 'm' } }), /proveedor/);
  for (const url of ['file:///C:/x', 'javascript:alert(1)', 'http://user:pass@x.com', 'no es url', '']) {
    assert.match(error({ llm: { proveedor: 'ollama', url, modelo: 'm' } }), /URL/, url);
  }
  assert.match(error({ llm: { proveedor: 'openrouter', url: 'https://openrouter.ai/api/v1', modelo: 'm' } }), /clave/);
  assert.match(error({ llm: { proveedor: 'ollama', url: 'http://x', modelo: 'm', num_ctx: 10 } }), /num_ctx/);
  assert.match(error({ llm: { proveedor: 'ollama', url: 'http://x', modelo: 'm', timeout_ms: 5 } }), /timeout/);
  assert.match(error({ llm: 'ollama' }), /objeto/);
});

test('no es un objeto → error', () => {
  for (const x of [null, 'config', [BASE], 5]) assert.equal(validarConfig(x).ok, false);
});
