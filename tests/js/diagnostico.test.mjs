// tests/js/diagnostico.test.mjs — los «Probar» de Ajustes y «Comprobar que todo funciona» de la piel web (11.3):
// extra/diagnostico.jsx (DiagnosticoCard, ProbarOpenRouter, ProbarOllama, ProbarTelegram, ProbarDictado) con un
// window.lune falso; en settings.jsx, «Probar micrófono» con el micro ocupado y «Probar salida» con respuesta; y el
// «Reconectar» de DiscordCard (extra/vida.jsx). Todo lo que llega se pinta como texto plano.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, EXTRA, KIT, boton, buscar, conClase, todoTexto, senal } from './jsx_falso.mjs';

const DIAG = path.join(EXTRA, 'diagnostico.jsx');
const SETTINGS = path.join(KIT, 'settings.jsx');
const VIDA = path.join(EXTRA, 'vida.jsx');
const ICONOS = ['IconCloud', 'IconCpu', 'IconTelegram', 'IconBrain', 'IconMic', 'IconVolume', 'IconBolt', 'IconMoon'];

/** window.lune falso: respuestas[ranura] = valor o fn(args) → valor; apunta las llamadas. */
function luneFalso(respuestas = {}) {
  const llamadas = [];
  const lune = { diagnostico: senal(), dictado_prueba: senal(), mic_prueba: senal(), llamadas };
  for (const n of ['diagnostico_iniciar', 'diagnostico_parar', 'openrouter_probar', 'ollama_probar', 'telegram_probar',
    'dictado_probar', 'probar_microfono', 'probar_salida', 'get_config', 'dispositivos_audio', 'guardar_config',
    'compat_borrador']) {
    lune[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push([n, ...args]);
      const r = respuestas[n];
      const v = typeof r === 'function' ? r(...args) : r;
      if (cb) cb(v);
    };
  }
  return lune;
}

function montar(componente, props = {}, lune = luneFalso(), archivos = [DIAG]) {
  const globales = {};
  for (const n of ICONOS) globales[n] = () => null;
  const S = crearSandbox({ archivos, lune, globales });
  const el = S.h(S.sb[componente], props);
  const r = { S, el, lune, arbol: S.render(el) };
  r.redibujar = () => { r.arbol = S.render(el); return r.arbol; };
  r.texto = () => todoTexto(r.redibujar());
  return r;
}

test('se registra solo, sin pisar nada', () => {
  const S = crearSandbox({ archivos: [DIAG] });
  assert.deepEqual([...S.nuevas].sort(), ['DiagnosticoCard', 'LuneDiagnostico', 'ProbarDictado', 'ProbarOllama',
    'ProbarOpenRouter', 'ProbarTelegram']);
});

test('LuneDiagnostico: eventos y respuestas normalizados (texto plano, recortado)', () => {
  const S = crearSandbox({ archivos: [DIAG] });
  const L = S.sb.LuneDiagnostico;
  assert.equal(L.normalizarEvento('basura'), null);
  assert.equal(L.normalizarEvento({ tipo: 'item' }), null);                       // sin id
  const it = L.normalizarEvento(JSON.stringify({ tipo: 'item', id: 'x', seccion: 'red', nombre: 'Internet',
    ok: 'si', detalle: 'a\u0000b\u202e' + 'z'.repeat(500) }));
  assert.equal(it.ok, null);                                                        // solo true/false cuentan
  assert.ok(!/[\u0000\u202e]/.test(it.detalle) && it.detalle.length <= 300);
  const p = L.normalizarPrueba('{"ok":false,"mensaje":"No.","modelos":["a",3,null],"items":[{"id":"t","ok":true}]}');
  assert.deepEqual(JSON.parse(JSON.stringify(p.modelos)), ['a', '3']);
  assert.equal(p.items[0].ok, true);
  assert.equal(L.marca(null), 'NO APLICA');
  assert.equal(L.pesoWhisper('base'), '~145 MB');
  const g = L.agrupar([{ id: 'b', seccion: 'red' }, { id: 'a', seccion: 'datos', seccion_nombre: 'Tus carpetas' }],
    [{ id: 'datos', nombre: 'Tus carpetas' }, { id: 'red', nombre: 'Red' }]);
  assert.deepEqual([...g.map((x) => x.id)], ['datos', 'red']);
});

test('DiagnosticoCard: pide la comprobación y pinta item a item, por secciones', () => {
  const lune = luneFalso({ diagnostico_iniciar: true, diagnostico_parar: true });
  const m = montar('DiagnosticoCard', {}, lune);
  boton(m.arbol, 'Comprobar que todo funciona').props.onClick();
  assert.deepEqual(lune.llamadas.map((l) => l[0]), ['diagnostico_iniciar']);
  assert.ok(m.texto().includes('Comprobando…'));
  lune.diagnostico.emit(JSON.stringify({ tipo: 'inicio', version: '11.3', modo: 'codigo', total: 3,
    secciones: [{ id: 'datos', nombre: 'Tus carpetas' }, { id: 'red', nombre: 'Red y servicios' }] }));
  lune.diagnostico.emit(JSON.stringify({ tipo: 'item', id: 'carpeta_datos', seccion: 'datos', seccion_nombre: 'Tus carpetas',
    nombre: 'Carpeta de tus datos', ok: true, detalle: 'C:/x' }));
  let t = m.texto();
  assert.ok(t.includes('Tus carpetas') && t.includes('BIEN') && t.includes('Carpeta de tus datos') && t.includes('1 de 3'));
  assert.ok(!t.includes('Red y servicios'), 'una sección sin items todavía no sale');
  lune.diagnostico.emit(JSON.stringify({ tipo: 'item', id: 'openrouter', seccion: 'red', seccion_nombre: 'Red y servicios',
    nombre: 'Clave de OpenRouter (nube)', ok: false, detalle: 'OpenRouter no reconoce esa clave.' }));
  lune.diagnostico.emit(JSON.stringify({ tipo: 'item', id: 'ollama', seccion: 'red', nombre: 'Ollama', ok: null, detalle: 'No uso Ollama.' }));
  t = m.texto();
  assert.ok(t.includes('MAL') && t.includes('NO APLICA') && t.includes('no reconoce'));
  boton(m.arbol, 'Parar').props.onClick();
  assert.equal(lune.llamadas[lune.llamadas.length - 1][0], 'diagnostico_parar');
  lune.diagnostico.emit(JSON.stringify({ tipo: 'fin', ok: false, resumen: 'Me falla 1 de 2: Clave de OpenRouter (nube).',
    fallan: 1, cuentan: 2, no_aplica: 1 }));
  t = m.texto();
  assert.ok(t.includes('Me falla 1 de 2') && t.includes('FALLA 1') && !t.includes('Comprobando…'));
  assert.ok(!boton(m.arbol, 'Parar'));
  // Desmontar suelta la señal.
  m.S.desmontar();
  assert.equal(lune.diagnostico.oyentes, 0);
});

test('DiagnosticoCard: si ya había una en marcha, lo dice', () => {
  const m = montar('DiagnosticoCard', {}, luneFalso({ diagnostico_iniciar: false }));
  boton(m.arbol, 'Comprobar que todo funciona').props.onClick();
  assert.ok(m.texto().includes('Ya estoy comprobando'));
});

test('DiagnosticoCard sin puente: demo', () => {
  const S = crearSandbox({ archivos: [DIAG], globales: { IconBolt: () => null } });
  const el = S.h(S.sb.DiagnosticoCard, {});
  const a = S.render(el);
  boton(a, 'Comprobar que todo funciona').props.onClick();
  assert.ok(todoTexto(S.render(el)).includes('Demo'));
});

test('ProbarOpenRouter manda lo escrito (también la máscara) y pinta la respuesta', () => {
  const lune = luneFalso({ openrouter_probar: () => JSON.stringify({ ok: true, mensaje: 'Tu clave de OpenRouter funciona.', ms: 120 }) });
  const m = montar('ProbarOpenRouter', { cfg: { openrouter_key: '••••••••', openrouter_model: 'openrouter/auto' } }, lune);
  boton(m.arbol, 'Probar clave').props.onClick();
  const [nombre, json] = lune.llamadas[0];
  assert.equal(nombre, 'openrouter_probar');
  assert.deepEqual(JSON.parse(json), { openrouter_key: '••••••••', openrouter_model: 'openrouter/auto' });
  const t = m.texto();
  assert.ok(t.includes('BIEN · 120 ms') && t.includes('funciona'));
});

test('ProbarOllama: los modelos salen como chips y al pulsar uno se elige', () => {
  const elegidos = [];
  const set = (k) => (v) => elegidos.push([k, v]);
  const lune = luneFalso({ ollama_probar: () => JSON.stringify({ ok: true, mensaje: 'Ollama responde.', modelos: ['llava', 'qwen2.5:7b'] }) });
  const m = montar('ProbarOllama', { cfg: { ollama_url: 'http://10.0.0.2:11434', ollama_model: 'llava' }, set }, lune);
  boton(m.arbol, 'Probar / Buscar modelos').props.onClick();
  assert.deepEqual(lune.llamadas[0], ['ollama_probar', 'http://10.0.0.2:11434']);
  m.redibujar();
  const chips = conClase(m.arbol, 'ln-dg-chip');
  assert.equal(chips.length, 2);
  assert.ok(conClase(m.arbol, 'is-on').length === 1, 'el elegido, marcado');
  boton(m.arbol, 'qwen2.5:7b').props.onClick();
  assert.deepEqual(elegidos, [['ollama_model', 'qwen2.5:7b']]);
});

test('ProbarTelegram: cada parte con su marca', () => {
  const lune = luneFalso({ telegram_probar: () => JSON.stringify({ ok: false, mensaje: 'Falta Node.js 18 o más nuevo.',
    items: [{ id: 'token', nombre: 'Token del bot', ok: true, detalle: 'Tu bot @LuneBot responde.' },
      { id: 'node', nombre: 'Node.js 18+', ok: false, detalle: 'Falta Node.js 18 o más nuevo.' }] }) });
  const m = montar('ProbarTelegram', { cfg: { telegram_token: '••••••••', telegram_admin_id: '42' } }, lune);
  boton(m.arbol, 'Probar bot').props.onClick();
  assert.deepEqual(JSON.parse(lune.llamadas[0][1]), { telegram_token: '••••••••', telegram_admin_id: '42' });
  const t = m.texto();
  assert.ok(t.includes('@LuneBot') && t.includes('Node.js 18+') && t.includes('MAL'));
});

test('un backend viejo sin la ranura: lo dice en vez de quedarse probando', () => {
  const lune = luneFalso();
  delete lune.openrouter_probar;
  const m = montar('ProbarOpenRouter', { cfg: {} }, lune);
  boton(m.arbol, 'Probar clave').props.onClick();
  const t = m.texto();
  assert.ok(t.includes('no está disponible') && t.includes('Probar clave'));
});

test('ProbarDictado: avisa de la descarga, manda lo elegido y sigue las fases', () => {
  const lune = luneFalso({ dictado_probar: true });
  const cfg = { dispositivo_entrada: 'Headset', modelo_whisper: 'base', voz_idioma: 'es' };
  const m = montar('ProbarDictado', { cfg, descargados: [] }, lune);
  assert.ok(m.texto().includes('La primera vez descargo el modelo «base» (~145 MB)'));
  boton(m.arbol, 'Probar dictado').props.onClick();
  assert.deepEqual(JSON.parse(lune.llamadas[0][1]), { dispositivo_entrada: 'Headset', modelo_whisper: 'base', voz_idioma: 'es' });
  lune.dictado_prueba.emit(JSON.stringify({ fase: 'grabando', ok: null, mensaje: 'Grabando 3 s: dime una frase.' }));
  assert.ok(m.texto().includes('Grabando…'));
  lune.dictado_prueba.emit(JSON.stringify({ fase: 'descargando', ok: null, mensaje: 'Descargando el modelo…' }));
  assert.ok(m.texto().includes('Descargando…'));
  lune.dictado_prueba.emit(JSON.stringify({ fase: 'listo', ok: true, texto: 'hola', mensaje: 'Te entendí: «hola».' }));
  const t = m.texto();
  assert.ok(t.includes('Te entendí') && t.includes('Probar dictado'));
  const ya = montar('ProbarDictado', { cfg, descargados: ['base'] }, luneFalso());
  assert.ok(!ya.texto().includes('descargo'));
});

test('ProbarDictado: el micrófono ocupado no lo deja colgado', () => {
  const lune = luneFalso({ dictado_probar: false });
  const m = montar('ProbarDictado', { cfg: {} }, lune);
  boton(m.arbol, 'Probar dictado').props.onClick();
  const t = m.texto();
  assert.ok(t.includes('ocupado') && t.includes('Probar dictado'));
});

// ── settings.jsx: Audio ─────────────────────────────────────────────────────

function ajustes(respuestas) {
  const lune = luneFalso({ get_config: JSON.stringify({ dispositivo_salida: 'Auriculares', modelo_whisper: 'base' }),
    dispositivos_audio: '{}', ...respuestas });
  return montar('SettingsPanel', { voiceOn: false, onVoice() {}, fx: { bg: false } }, lune, [SETTINGS, DIAG]);
}

test('«Probar micrófono» con el micro ocupado ya no se queda en «Habla ahora…»', () => {
  const m = ajustes({ probar_microfono: false });
  boton(m.arbol, 'Probar micrófono').props.onClick();
  const t = m.texto();
  assert.ok(!t.includes('Habla ahora') && t.includes('en uso') && t.includes('Probar micrófono'));
  // Si la señal ya trajo el motivo (micrófono que no está), se queda ese.
  const m2 = ajustes({ probar_microfono: () => false });
  boton(m2.arbol, 'Probar micrófono').props.onClick();
  m2.lune.mic_prueba.emit(JSON.stringify({ ok: false, mensaje: 'No encuentro «X». ¿Está conectado?' }));
  assert.ok(m2.texto().includes('No encuentro «X»'));
});

test('«Probar salida» responde: sonando o por qué no', () => {
  const m = ajustes({ probar_salida: true });
  boton(m.arbol, 'Probar salida').props.onClick();
  assert.ok(m.texto().includes('Sonando un tono por «Auriculares»'));
  assert.deepEqual(m.lune.llamadas.find((l) => l[0] === 'probar_salida'), ['probar_salida', 'Auriculares']);
  const m2 = ajustes({ probar_salida: false });
  boton(m2.arbol, 'Probar salida').props.onClick();
  assert.ok(m2.texto().includes('No pude sonar'));
});

test('Ajustes pinta los Probar y la tarjeta del diagnóstico', () => {
  const t = ajustes({}).texto();
  for (const s of ['Probar clave', 'Probar / Buscar modelos', 'Probar bot', 'Probar dictado', 'Comprobar que todo funciona']) {
    assert.ok(t.includes(s), s);
  }
});

// ── vida.jsx: «Reconectar» de Discord ──────────────────────────────────────

function discord(estado, reconectar) {
  const llamadas = [];
  const luneVida = { discord_cambio: senal(), llamadas };
  luneVida.discord_estado = (cb) => cb(JSON.stringify(estado));
  luneVida.discord_reconectar = (cb) => { llamadas.push('reconectar'); cb(JSON.stringify(reconectar)); };
  const S = crearSandbox({ archivos: [VIDA], globales: { luneVida } });
  const el = S.h(S.sb.DiscordCard, {});
  const r = { S, el, luneVida, arbol: S.render(el) };
  r.texto = () => todoTexto(r.arbol = S.render(el));
  return r;
}

test('DiscordCard: sin conectar enseña el motivo y «Reconectar»', () => {
  const estado = { activo: true, conectado: false, error: 'Discord no está abierto.', servicio: true,
    motivo: 'Discord no está abierto: abre la app de escritorio de Discord (la web no vale) y pulsa Reconectar.',
    config: { client_id: '123456789012345678' } };
  const m = discord(estado, { ok: true, texto: 'Lo intento ahora: si Discord está abierto, en unos segundos sale «Conectado».',
    estado });
  assert.ok(m.texto().includes('la web no vale'));
  boton(m.arbol, 'Reconectar').props.onClick();
  assert.deepEqual(m.luneVida.llamadas, ['reconectar']);
  assert.ok(m.texto().includes('Lo intento ahora'));
  const conectado = discord({ ...estado, conectado: true, usuario: 'diego', motivo: '' }, {});
  assert.ok(!boton(conectado.arbol, 'Reconectar'));
  const apagado = discord({ ...estado, activo: false }, {});
  assert.ok(!boton(apagado.arbol, 'Reconectar'));
});
