// tests/js/ajustes_guardar.test.mjs — «Guardar configuración» de la piel web (settings.jsx) manda
// SOLO lo que cambiaste en Ajustes (revisión 4-5-6, VS3): lo cambiado fuera con Ajustes abierto
// (tamaño/encuadre de la asistente desde el radial o la bandeja, «Arrancar con Windows» desde la
// bandeja…) no se revierte con la foto que dio get_config al abrir. Igual al cambiar de modo.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, KIT, boton, interruptor, senal } from './jsx_falso.mjs';

const SETTINGS = path.join(KIT, 'settings.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
const ICONOS = ['IconCloud', 'IconCpu', 'IconTelegram', 'IconBrain', 'IconMic', 'IconVolume', 'IconBolt', 'IconMoon'];

const FOTO = {
  openrouter_key: '••••', openrouter_model: 'openrouter/auto', ollama_url: 'http://localhost:11434', ollama_model: 'm',
  telegram_token: '', telegram_admin_id: '', telegram_ordenes_pc: false, nombre: 'Lune', system_prompt: 'x',
  voz: false, memoria: true, acciones_ia: true, asistente_render: 'vrm', interfaz_modo: 'web',
  vrm_webengine: true, vrm_modelos: ['a.vrm'], vrm_archivo: '', vrm_tamano: 'normal', vrm_encuadre: 'retrato',
  vrm_fantasma_auto: true, seguir_cursor: true, dormir_min: 10, asistente_fuera: true, autoinicio: false,
  aburrimiento_min: 10, dispositivo_entrada: '', dispositivo_salida: '', modelo_whisper: 'base', voz_idioma: 'es',
};

function montar() {
  const guardados = [];
  const cambios = [];
  const lune = {
    get_config(cb) { cb(JSON.stringify(FOTO)); },
    guardar_config(json, cb) { guardados.push(JSON.parse(json)); cb(JSON.stringify({ ok: true })); },
    cambiar_interfaz(modo, cb) { cambios.push(modo); cb(JSON.stringify({ ok: true })); },
    dispositivos_audio(cb) { cb('{}'); },
    compat_borrador() {},
    mic_prueba: senal(),
  };
  const globales = {};
  for (const n of ICONOS) globales[n] = () => null;
  const S = crearSandbox({ archivos: [SETTINGS], lune, globales });
  const el = S.h(S.sb.SettingsPanel, { voiceOn: false, onVoice() {}, fx: { bg: false, sweep: true, micro: true },
    setFxKey: () => () => {} });
  const r = { S, guardados, cambios, arbol: S.render(el) };
  r.redibujar = () => { r.arbol = S.render(el); return r.arbol; };
  r.guardar = () => { boton(r.arbol, 'Guardar configuración').props.onClick(); r.redibujar(); return guardados[guardados.length - 1]; };
  return r;
}

test('cambiosAjustes: solo las claves que cambiaron, sin las de solo lectura', () => {
  const S = crearSandbox({ archivos: [SETTINGS] });
  const f = S.sb.cambiosAjustes;
  assert.deepEqual(plano(f({ a: 1, b: [1, 2], voz: true }, { a: 1, b: [1, 2], voz: false })), {});
  assert.deepEqual(plano(f({ a: 1, b: 'x' }, { a: 2, b: 'x', c: null })), { a: 2, c: null });
  assert.deepEqual(plano(f(null, { a: 1, asistente_fuera: true })), { a: 1 });   // sin foto: todo (menos lo de solo lectura)
  assert.deepEqual(plano(f({ m: 'web' }, { m: 'nativo' }, ['m'])), {});
});

test('guardar sin tocar nada no manda nada (tampoco el autoinicio ni el tamaño de la foto)', () => {
  const r = montar();
  assert.deepEqual(plano(r.guardar()), {});
});

test('guardar manda solo lo cambiado en Ajustes y después ya no lo repite', () => {
  const r = montar();
  boton(r.arbol, 'Grande').props.onClick();                 // Tamaño ▸ Grande en Ajustes
  r.redibujar();
  assert.deepEqual(plano(r.guardar()), { vrm_tamano: 'grande' });
  assert.deepEqual(plano(r.guardar()), {});                 // la foto ya lo tiene
  interruptor(r.arbol, 'Arrancar Lune junto con Windows').onChange({ target: { checked: true } });
  r.redibujar();
  assert.deepEqual(plano(r.guardar()), { autoinicio: true });
});

test('cambiar de modo guarda solo lo pendiente (sin interfaz_modo) y luego pide el cambio', () => {
  const r = montar();
  boton(r.arbol, 'Cuerpo entero').props.onClick();
  r.redibujar();
  boton(r.arbol, 'Bajos recursos').props.onClick();
  r.redibujar();
  assert.deepEqual(plano(r.guardados), [{ vrm_encuadre: 'cuerpo' }]);
  assert.deepEqual(r.cambios, ['nativo']);
});
