// tests/js/vrm_fps.test.mjs — ritmo del bucle de ui_web/vrm/lune_vrm.js (11.2), con el motor DE
// VERDAD en Node (motor_vrm_falso.mjs): mover el cursor no lo sube a fpsActivo, dormida del todo
// baja a fpsDormida, y con FPS 0 el bucle se para (ni un requestAnimationFrame más) hasta que
// setFPS(n > 0) lo vuelve a arrancar.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { reloj } from './three_falso.mjs';
import { frames, correr, montar, quietaSinIdles, motor } from './motor_vrm_falso.mjs';

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
