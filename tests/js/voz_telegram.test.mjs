// tests/js/voz_telegram.test.mjs — voz del bot de Telegram (telegram-bot-or/voz.js).
// Solo las funciones puras: no lanza edge-tts ni lee datos.json.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizar, vozDePersonaje, argsEdgeTts, VOZ_DEFECTO } from '../../telegram-bot-or/voz.js';

test('normalizar acepta números y cadenas y acota', () => {
  assert.equal(normalizar(10, '%', -90, 200), '+10%');
  assert.equal(normalizar('-15', '%', -90, 200), '-15%');
  assert.equal(normalizar(' +20 % ', '%', -90, 200), '+20%');
  assert.equal(normalizar(999, '%', -90, 200), '+200%');
  assert.equal(normalizar('-5Hz', 'Hz', -100, 100), '-5Hz');
  assert.equal(normalizar('rápido', '%', -90, 200), null);
  assert.equal(normalizar(true, '%', -90, 200), null);
  assert.equal(normalizar(undefined, '%', -90, 200), null);
});

test('prioridad: personaje > config.json voz.* > por defecto', () => {
  assert.deepEqual(vozDePersonaje(null, {}),
    { voz: VOZ_DEFECTO, rate: '+0%', pitch: '+0Hz', volumen: '+0%' });
  const cfg = { edge_voz: 'es-ES-ElviraNeural', edge_rate: '-10%', edge_pitch: '+5Hz' };
  assert.deepEqual(vozDePersonaje({ nombre: 'Lune' }, cfg),
    { voz: 'es-ES-ElviraNeural', rate: '-10%', pitch: '+5Hz', volumen: '+0%' });
  assert.deepEqual(vozDePersonaje({ voz: { id: 'es-AR-ElenaNeural', rate: 15 } }, cfg),
    { voz: 'es-AR-ElenaNeural', rate: '+15%', pitch: '+5Hz', volumen: '+0%' });
  // Forma corta y voces que no son de edge (Kokoro) → la de config.
  assert.equal(vozDePersonaje({ voz: 'es-CL-CatalinaNeural' }).voz, 'es-CL-CatalinaNeural');
  assert.equal(vozDePersonaje({ voz: { motor: 'kokoro', id: 'af_heart' } }, cfg).voz, 'es-ES-ElviraNeural');
  assert.equal(vozDePersonaje({ voz: { id: 'inventada', rate: 'mucho' } }, {}).rate, '+0%');
});

test('la CLI recibe las opciones con "=" (un -10% suelto sería otra opción)', () => {
  const args = argsEdgeTts('-hola', 'out.mp3', { voz: 'es-MX-JorgeNeural', rate: '-10%', pitch: '-2Hz', volumen: '+0%' });
  assert.deepEqual(args, [
    '--voice=es-MX-JorgeNeural', '--rate=-10%', '--pitch=-2Hz', '--volume=+0%',
    '--text=-hola', '--write-media=out.mp3',
  ]);
});
