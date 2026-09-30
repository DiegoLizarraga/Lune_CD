/*
 * app.jsx y sidebar.jsx con el corte 4 y el estado inicial del puente (sandbox con estado de verdad):
 *   · wire(): estado_inicial() pinta la conversación en curso y toma proveedor/voz/bot/asistente;
 *     sin estado_inicial (backend viejo) se sigue resincronizando el proveedor con proveedor_elegido;
 *     con «compat» no se cae a «local» (estado_inicial va después de proveedores()).
 *   · window.luneEscritorio: efectos desde la config (y guardar al cambiarlos), tema al arrancar y en
 *     tema_cambio, modo juego → clase en <body> y barra en pausa, navegar → vista, F1 y clic derecho
 *     sobre la asistente → menú radial SVG.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, escritorioFalso, senal, KIT, EXTRA, buscar, conClase, texto } from './jsx_falso.mjs';

const ARCHIVOS = [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx'), path.join(EXTRA, 'apariencia.jsx'),
  path.join(EXTRA, 'juego.jsx'), path.join(KIT, 'app.jsx')];

function docFalso() {
  const clases = new Set();
  return {
    clases,
    body: { classList: { toggle(c, on) { if (on) clases.add(c); else clases.delete(c); }, contains: (c) => clases.has(c) } },
    getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null,
  };
}
/** window.lune falso: lo que no se defina es una señal (connect/disconnect). */
function luneFalso(metodos = {}) {
  const llamadas = [];
  const base = {
    asistente_visible(cb) { cb(false); },
    proveedores(cb) { cb('{}'); },
    proveedor_elegido(p) { llamadas.push(['proveedor', p]); },
    ...metodos,
  };
  const obj = new Proxy(base, { get(t, k) { if (!(k in t) && typeof k === 'string') t[k] = senal(); return t[k]; } });
  return { obj, llamadas, proveedores: () => llamadas.filter((l) => l[0] === 'proveedor').map((l) => l[1]) };
}
function cargar({ lune = null, escritorio = null } = {}) {
  const doc = docFalso();
  const props = {};
  const stub = (n) => function (p) { props[n] = p; return null; };
  const temas = [];
  const S = crearSandbox({
    archivos: ARCHIVOS, lune, escritorio,
    globales: {
      document: doc, localStorage: { getItem: () => null, setItem() {} },
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), CommandMenu: stub('CommandMenu'),
      SettingsPanel: stub('SettingsPanel'), AprobacionHost: stub('AprobacionHost'),
      luneTema: (m) => { temas.push(m); return 1; },
    },
  });
  const app = S.h(S.sb.LuneApp);
  return { S, doc, props, temas, pintar: () => S.render(app) };
}
const titulo = (a) => texto(conClase(a, 'ln-topbar-title')[0]);
// Lo que sale del sandbox (otro «realm» de vm) se compara por valor.
const plano = (x) => JSON.parse(JSON.stringify(x));

test('estado_inicial: pinta la conversación en curso y toma proveedor, voz, bot y asistente', () => {
  const L = luneFalso({
    estado_inicial: (cb) => cb(JSON.stringify({
      proveedor: 'cloud', voz: true, telegram: true, asistente_fuera: true,
      mensajes: [{ role: 'user', text: 'hola' }, { role: 'assistant', text: '¡Hola! Aquí sigo.' }, { role: 'user', text: '' }],
    })),
  });
  const A = cargar({ lune: L.obj });
  const a = A.pintar();
  const msgs = A.props.ChatStream.messages;
  assert.deepEqual(plano(msgs.map((m) => [m.role, m.text, m.provider])), [['user', 'hola', 'cloud'], ['bot', '¡Hola! Aquí sigo.', 'cloud']]);
  assert.equal(new Set(msgs.map((m) => m.id)).size, 2, 'ids únicos');
  assert.equal(titulo(a), 'Lune AI · Nube');
  assert.equal(L.proveedores().slice(-1)[0], 'cloud', 'el puente se queda con el suyo');
  assert.equal(conClase(a, 'is-out').length, 1, 'asistente fuera');
  const menu = A.props.CommandMenu.items;
  assert.ok(menu.find((i) => /^Voz ON/.test(i.label)) && menu.find((i) => i.label === 'Telegram').on === true);
});

test('sin estado_inicial (backend viejo): se sigue avisando del proveedor elegido', () => {
  const L = luneFalso();
  const A = cargar({ lune: L.obj });
  A.pintar();
  assert.ok(L.proveedores().includes('local'));
  assert.deepEqual(plano(A.props.ChatStream.messages), []);
  // estado_inicial que falla o sin proveedor válido: también se resincroniza
  const L2 = luneFalso({ estado_inicial: (cb) => cb('no json') });
  const A2 = cargar({ lune: L2.obj });
  A2.pintar();
  assert.ok(L2.proveedores().filter((p) => p === 'local').length >= 2, L2.llamadas);
  const L3 = luneFalso({ estado_inicial: () => { throw new Error('puente roto'); } });
  const A3 = cargar({ lune: L3.obj });
  A3.pintar();
  assert.ok(L3.proveedores().filter((p) => p === 'local').length >= 2);
});

test('recarga de la página: wire() al llegar lune-ready; «compat» no se cae a «local»', () => {
  const A = cargar();
  A.pintar();
  const L = luneFalso({
    proveedores: (cb) => cb(JSON.stringify({ compat: true, compat_model: 'qwen', compat_url: 'http://localhost:1234/v1' })),
    estado_inicial: (cb) => cb(JSON.stringify({ proveedor: 'compat', mensajes: [] })),
  });
  A.S.sb.lune = L.obj;
  A.S.dispatch(new A.S.sb.Event('lune-ready'));
  const a = A.pintar();
  assert.equal(titulo(a), 'Lune AI · API');
  assert.equal(L.proveedores().slice(-1)[0], 'compat');
  assert.ok(!L.proveedores().includes('local'), L.llamadas);
});

function escritorio() {
  return escritorioFalso({
    efectos: JSON.stringify({ fondo: false, barrido: true, micro: false }),
    efectos_guardar: (j) => JSON.stringify({ ok: true, estado: JSON.parse(j) }),
    tema_estado: JSON.stringify({ cfg: { preset: 'violeta' }, vars: { '--cyan-500': '#8A00FF', '--cyan-500-rgb': '138 0 255' }, presets: {} }),
    juego_estado_json: JSON.stringify({ activo: false, motivo: '', forzado: null, exe: '' }),
    radial_estado: JSON.stringify({ sonidos: false }),
    acciones_catalogo: JSON.stringify([{ id: 'voz', etiqueta: 'Voz' }, { id: 'ajustes', etiqueta: 'Ajustes' }]),
    accion_menu: true,
  });
}

test('corte 4: efectos de la config, tema, modo juego, navegar, F1 y clic derecho → radial', () => {
  const E = escritorio();
  const L = luneFalso();
  const A = cargar({ lune: L.obj, escritorio: E.obj });
  let a = A.pintar();
  const app = conClase(a, 'ln-app')[0];
  assert.match(app.props.className, /fx-no-bg/);
  assert.match(app.props.className, /fx-no-micro/);
  assert.doesNotMatch(app.props.className, /fx-no-sweep/);
  assert.equal(conClase(a, 'p3-bg').length, 0, 'sin fondo animado');
  assert.deepEqual(plano(A.temas), [{ '--cyan-500': '#8A00FF', '--cyan-500-rgb': '138 0 255' }], 'tema al arrancar');
  E.obj.tema_cambio.emit('null');
  E.obj.tema_cambio.emit('{"--blue-500":"#FF0000"}');
  assert.deepEqual(plano(A.temas.slice(1)), [null, { '--blue-500': '#FF0000' }]);
  // Ajustes → Efectos: el interruptor guarda en la config
  E.obj.navegar.emit('settings');
  a = A.pintar();
  assert.ok(A.props.SettingsPanel, 'navegar → Ajustes');
  A.props.SettingsPanel.setFxKey('sweep')({ target: { checked: false } });
  a = A.pintar();
  assert.deepEqual(plano(E.de('efectos_guardar')), [['{"barrido":false}']]);
  assert.match(conClase(a, 'ln-app')[0].props.className, /fx-no-sweep/);
  E.obj.navegar.emit('<script>');
  E.obj.navegar.emit('chat#x');
  a = A.pintar();
  assert.ok(A.props.ChatStream && A.props.InputBar, 'vuelve al chat; lo raro se ignora');
  // Modo juego: clase en <body> y la barra en pausa
  E.obj.juego_estado.emit(JSON.stringify({ activo: true, motivo: 'quns3' }));
  a = A.pintar();
  assert.ok(A.doc.clases.has('modo-juego'));
  const video = buscar(a, (n) => n.type === 'video')[0];
  assert.equal(video.props.autoPlay, false, 'vídeo de la barra en pausa');
  E.obj.juego_estado.emit(JSON.stringify({ activo: false }));
  a = A.pintar();
  assert.ok(!A.doc.clases.has('modo-juego'));
  assert.equal(buscar(a, (n) => n.type === 'video')[0].props.autoPlay, true);
  // F1 → radial
  const f1 = A.S.evento('keydown', { key: 'F1' });
  A.S.dispatch(f1);
  a = A.pintar();
  assert.ok(f1.prevenido);
  assert.deepEqual(plano(E.de('acciones_catalogo')), [['radial']]);
  assert.equal(conClase(a, 'ln-radial-capa').length, 1);
  A.S.dispatch(A.S.evento('keydown', { key: 'Escape' }));
  a = A.pintar();
  assert.equal(conClase(a, 'ln-radial-capa').length, 0);
  // Clic derecho sobre la asistente de la barra → radial donde se hizo clic (sin menú de Chromium)
  const escenario = conClase(a, 'ln-asistente-stage')[0];
  const ctx = A.S.evento('contextmenu', { clientX: 150, clientY: 600 });
  escenario.props.onContextMenu(ctx);
  a = A.pintar();
  assert.ok(ctx.prevenido);
  assert.equal(E.de('acciones_catalogo').length, 2);
  const svg = buscar(a, (n) => n.type === 'svg' && /ln-radial/.test(n.props.className || ''))[0];
  assert.deepEqual(plano(svg.props.style), { left: 0, top: 600 - 184 });
});

test('sin luneEscritorio: localStorage de respaldo y nada se rompe', () => {
  const L = luneFalso();
  const A = cargar({ lune: L.obj });
  const a = A.pintar();
  const app = conClase(a, 'ln-app')[0];
  assert.doesNotMatch(app.props.className, /fx-no-/);
  A.props.CommandMenu.items.find((i) => i.label === 'Ajustes').onClick();
  A.pintar();
  A.props.SettingsPanel.setFxKey('bg')({ target: { checked: false } });
  assert.match(conClase(A.pintar(), 'ln-app')[0].props.className, /fx-no-bg/);
  assert.deepEqual(plano(A.temas), []);
});
