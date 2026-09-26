// tests/js/params.test.mjs — lista blanca y rangos de window.luneParams
// (ui_web/vrm/lune_params.js). Sin DOM ni three: `node --test tests/js/params.test.mjs`.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  RANGOS, CLAVES_MODELO, CLAVES_SEGUIMIENTO, validarValor, validarParams, aplicarParams,
  crearLuneParams, defectos, ejesDe,
} from '../../ui_web/vrm/lune_params.js';

test('descarta claves desconocidas, prototipos y funciones', () => {
  const r = validarParams({
    luz: 1.5, fov: 90, cabezaYaw: 180, patGrados: 0, hola: 'x',
    ['__proto__']: { luz: 3 }, constructor: 1, toString: 2,
  });
  assert.deepEqual(r, { luz: 1.5 });
  const malicioso = JSON.parse('{"__proto__": {"contaminado": true}, "altura": 0.1}');
  const r2 = validarParams(malicioso);
  assert.deepEqual(r2, { altura: 0.1 });
  assert.equal({}.contaminado, undefined);
  assert.equal(Object.getPrototypeOf(r2), Object.prototype);
});

test('limita los rangos', () => {
  const r = validarParams({
    luz: 99, altura: -3, pesoCabeza: 1.5, pesoTorso: -1, pesoOjos: 0.25,
    fpsActivo: 1000, swayGanH: 1, swayMaxZ: -5, swayFrec: 0,
  });
  assert.equal(r.luz, 3);
  assert.equal(r.altura, -0.5);
  assert.equal(r.pesoCabeza, 1);
  assert.equal(r.pesoTorso, 0);
  assert.equal(r.pesoOjos, 0.25);
  assert.equal(r.fpsActivo, 144);
  assert.equal(r.swayGanH, 0.05);
  assert.equal(r.swayMaxZ, 0);
  assert.equal(r.swayFrec, 0.1);
  assert.equal(validarValor('fpsActivo', 5), 15);
  assert.equal(validarValor('fpsActivo', 59.6), 60);
  assert.equal(validarValor('altura', 0.123456), 0.1235);
  assert.equal(validarValor('luz', 0.1), 0.2);
});

test('signos y opción de ejes', () => {
  assert.equal(validarValor('invertirH', -1), -1);
  assert.equal(validarValor('invertirH', -0.2), -1);
  assert.equal(validarValor('invertirH', 0), 1);
  assert.equal(validarValor('invertirH', 7), 1);
  assert.equal(validarValor('invertirV', true), -1);
  assert.equal(validarValor('invertirV', false), 1);
  assert.equal(validarValor('invertirBrazos', '-1'), -1);
  assert.equal(validarValor('invertirPiernas', 'abc'), null);
  assert.equal(validarValor('invertirEjes', 'auto'), 0);
  assert.equal(validarValor('invertirEjes', ' Automático '), 0);
  assert.equal(validarValor('invertirEjes', -5), -1);
  assert.equal(validarValor('invertirEjes', 0.4), 0);
  assert.equal(validarValor('invertirEjes', 0.6), 1);
  assert.ok(Object.is(validarValor('invertirEjes', -0.2), 0), 'nunca -0');
  assert.equal(validarValor('invertirEjes', true), null);
});

test('valores que no son números se descartan (NaN, Infinity, null, objetos, bool en reales)', () => {
  const r = validarParams({
    luz: NaN, altura: Infinity, pesoCabeza: null, pesoTorso: {}, pesoOjos: [0.5],
    swayGanV: true, fpsActivo: '', swayZeta: '1e400',
  });
  assert.deepEqual(r, {});
  assert.equal(validarValor('luz', '0,5'), 0.5);          // coma decimal, como en Python
  assert.equal(validarValor('luz', ' 2 '), 2);
  assert.equal(validarValor('luz', '2abc'), null);
  assert.equal(validarValor('nada', 1), null);
  assert.equal(validarValor(undefined, 1), null);
});

test('acepta texto JSON y rechaza JSON roto, listas y textos enormes', () => {
  assert.deepEqual(validarParams('{"luz": 2, "x": 1}'), { luz: 2 });
  assert.deepEqual(validarParams('{roto'), {});
  assert.deepEqual(validarParams('[1,2]'), {});
  assert.deepEqual(validarParams(null), {});
  assert.deepEqual(validarParams(42), {});
  assert.deepEqual(validarParams(JSON.stringify({ luz: 2, relleno: 'x'.repeat(70000) })), {});
});

test('aplicarParams asigna solo lo válido y dice qué cambió', () => {
  const PARAMS = { luz: 1, altura: 0, fov: 24, invertirEjes: 0, pesoOjos: 1 };
  const { aplicados, cambiadas } = aplicarParams(PARAMS, { luz: 1, altura: 0.2, fov: 90, invertirEjes: -1, basura: 3 });
  assert.deepEqual(aplicados, { invertirEjes: -1, luz: 1, altura: 0.2 });
  assert.deepEqual(cambiadas.sort(), ['altura', 'invertirEjes']);
  assert.equal(PARAMS.fov, 24, 'fov no está en la lista blanca');
  assert.equal(PARAMS.basura, undefined);
  assert.equal(PARAMS.altura, 0.2);
});

test('crearLuneParams: devuelve JSON, avisa de los cambios y aguanta un alCambiar que lanza', () => {
  const PARAMS = { luz: 1, pesoCabeza: 1 };
  const avisos = [];
  const lp = crearLuneParams(PARAMS, (c, P) => { avisos.push([...c]); assert.equal(P, PARAMS); });
  assert.equal(lp('{"luz": 2.5, "fov": 1}'), '{"luz":2.5}');
  assert.deepEqual(avisos, [['luz']]);
  lp({ luz: 2.5 });
  assert.equal(avisos.length, 1, 'sin cambios no avisa');
  const roto = crearLuneParams(PARAMS, () => { throw new Error('x'); });
  const aviso = console.warn; console.warn = () => {};
  try { assert.equal(roto({ pesoCabeza: 0 }), '{"pesoCabeza":0}'); } finally { console.warn = aviso; }
  assert.equal(PARAMS.pesoCabeza, 0);
});

test('claves del modelo, seguimiento y defectos', () => {
  assert.equal(CLAVES_MODELO.length, 10);
  for (const k of CLAVES_MODELO) assert.ok(RANGOS[k], k);
  for (const k of CLAVES_SEGUIMIENTO) assert.ok(CLAVES_MODELO.includes(k), k);
  for (const k of ['fpsActivo', 'swayGanH', 'swayGanV', 'swayMaxZ', 'swayMaxX', 'swayFrec', 'swayZeta',
    'swayFiltro', 'swayEntrada', 'swaySalida']) assert.ok(RANGOS[k] && !CLAVES_MODELO.includes(k), k);
  const d = defectos();
  assert.deepEqual(Object.keys(d), [...CLAVES_MODELO]);
  assert.equal(d.luz, 1); assert.equal(d.invertirEjes, 0); assert.equal(d.pesoOjos, 1);
  // Cada defecto es válido en su propio rango
  for (const [k, r] of Object.entries(RANGOS)) assert.equal(validarValor(k, r.defecto), r.defecto, k);
  assert.deepEqual(defectos(['fpsActivo', 'nada']), { fpsActivo: 60 });
  assert.ok(Object.isFrozen(RANGOS));
});

test('ejesDe: forzado, medido y por versión', () => {
  assert.equal(ejesDe(1, -0.3, '0'), 1);
  assert.equal(ejesDe(-1, 0.3, '1'), -1);
  assert.equal(ejesDe(0, -0.25, '1'), -1);
  assert.equal(ejesDe('auto', 0.25, '0'), 1);
  assert.equal(ejesDe(0, 0, '0'), -1);
  assert.equal(ejesDe(0, undefined, '1'), 1);
  assert.equal(ejesDe('basura', NaN, '0'), -1);
});
