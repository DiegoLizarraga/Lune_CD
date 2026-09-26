/*
 * Menú radial SVG de la web (extra/apariencia.jsx): geometría igual que ui/menu_radial.py
 * (tabla de referencia; tests/test_jsx_apariencia.py la compara además con el Python real),
 * RadialMenu (resaltar, pulsar = escala 0.8, soltar = ejecutar, zona muerta, Esc, clic derecho,
 * perder el foco, teclado) y RadialHost (acciones_catalogo → accion_menu, «ajustes»/«chat» en la
 * página, segundo radial de expresiones, sonidos del menú, demo sin backend).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, escritorioFalso, EXTRA, buscar, conClase, texto } from './jsx_falso.mjs';

const APARIENCIA = path.join(EXTRA, 'apariencia.jsx');

// (dx, dy, n) → índice, con y hacia abajo y el botón 0 en [0°, 360/n) desde las 12 en sentido horario.
const TABLA = [
  [0, -100, 4, 0], [100, 0, 4, 1], [0, 100, 4, 2], [-100, 0, 4, 3],
  [1, -100, 4, 0], [-1, -100, 4, 3], [100, -1, 4, 0], [100, 1, 4, 1],
  [0, -85, 4, null], [0, -85.01, 4, 0], [60, 60, 4, null], [0, 0, 1, null],
  [0, -200, 1, 0], [0, 200, 1, 0], [-5, 300, 1, 0],
  [0, -500, 0, null], [0, -500, -3, null],
  [0, -120, 3, 0], [120, 70, 3, 1], [-120, 70, 3, 1], [-120, 40, 3, 2],
  [Math.sin(35.9 * Math.PI / 180) * 120, -Math.cos(35.9 * Math.PI / 180) * 120, 10, 0],
  [Math.sin(36.1 * Math.PI / 180) * 120, -Math.cos(36.1 * Math.PI / 180) * 120, 10, 1],
  [Math.sin(359.5 * Math.PI / 180) * 120, -Math.cos(359.5 * Math.PI / 180) * 120, 10, 9],
  [Math.sin(179.9 * Math.PI / 180) * 90, -Math.cos(179.9 * Math.PI / 180) * 90, 2, 0],
  [Math.sin(180.1 * Math.PI / 180) * 90, -Math.cos(180.1 * Math.PI / 180) * 90, 2, 1],
  [1e6, 1e6, 8, 3], [0, -100, 2.7, 0], [-0, -100, 4, 0],
];

function cargar(opciones = {}) {
  return crearSandbox({ archivos: [APARIENCIA], ...opciones });
}
const items3 = [
  { id: 'ajustes', etiqueta: 'Ajustes', icono: 'gear' },
  { id: 'voz', etiqueta: 'Voz', icono: 'volume' },
  { id: 'dormir', etiqueta: 'Dormir', icono: 'luna_rara', habilitado: false },
];

test('se registra solo, sin pisar globales', () => {
  const S = cargar();
  for (const n of ['AparienciaCard', 'AtajosCard', 'MenuRadialCard', 'BandejaCard', 'RadialMenu', 'RadialHost', 'LuneRadial', 'LuneApariencia']) {
    assert.ok(S.sb[n], `falta window.${n}`);
  }
  assert.deepEqual(S.nuevas.sort(), ['AparienciaCard', 'AtajosCard', 'BandejaCard', 'LuneApariencia', 'LuneRadial', 'MenuRadialCard', 'RadialHost', 'RadialMenu']);
});

test('indice: tabla de referencia (la de ui/menu_radial.py)', () => {
  const { indice } = cargar().sb.LuneRadial;
  for (const [dx, dy, n, esperado] of TABLA) {
    const r = indice(dx, dy, n);
    assert.equal(r === null ? null : r + 0, esperado, `indice(${dx}, ${dy}, ${n})`);
  }
  assert.equal(indice(NaN, 5, 4), null);
  assert.equal(indice(0, -100, 4, 150), null, 'zona muerta configurable');
});

test('geometría: constantes, posiciones a mitad de sector y factorLerp', () => {
  const R = cargar().sb.LuneRadial;
  assert.deepEqual([R.LIENZO, R.ZONA_MUERTA, R.RADIO_ICONOS, R.RADIO_EXTERIOR, R.MAX_BOTONES], [368, 85, 120, 165, 10]);
  const p4 = R.posiciones(4);
  const cerca = (a, b) => Math.abs(a - b) < 1e-9;
  assert.ok(cerca(p4[0][0], 120 * Math.sin(Math.PI / 4)) && cerca(p4[0][1], -120 * Math.cos(Math.PI / 4)), 'botón 0 a 45°');
  assert.ok(cerca(p4[2][0], -120 * Math.sin(Math.PI / 4)) && cerca(p4[2][1], 120 * Math.cos(Math.PI / 4)), 'botón 2 a 225°');
  const p1 = R.posiciones(1);
  assert.ok(cerca(p1[0][0], 0) && cerca(p1[0][1], 120), 'n = 1: abajo, como en Mate-Engine');
  for (let n = 1; n <= 10; n++) {
    R.posiciones(n).forEach(([x, y], i) => assert.equal(R.indice(x, y, n), i, `el icono ${i} de ${n} cae en su sector`));
  }
  assert.ok(cerca(R.factorLerp(0.2, 1 / 60), 0.2), 'un frame a 60 fps = base');
  assert.ok(cerca(R.factorLerp(0.2, 2 / 60), 1 - 0.8 * 0.8), 'dos frames');
  assert.equal(R.factorLerp(0.2, 0), 0);
  assert.equal(R.factorLerp(1, 0.001), 1);
  assert.match(R.sector(0, 4), /^M [\d. ]+ L [\d. ]+ A 165 165 0 0 1 [\d. ]+ L [\d. ]+ A 85 85 0 0 0 [\d. ]+ Z$/);
  assert.match(R.sector(0, 1), /A 165 165 0 1 1 .* A 85 85 0 1 0 /, 'n = 1: anillo entero');
});

test('normalizarItems: ids válidos, etiquetas recortadas, máximo 10', () => {
  const R = cargar().sb.LuneRadial;
  const muchos = Array.from({ length: 14 }, (_, i) => ({ id: `a${i}`, etiqueta: 'x'.repeat(60) }));
  const r = R.normalizarItems([{ id: '<img>' }, { id: 'Voz' }, null, 'voz', ...muchos]);
  assert.equal(r.length, 10);
  assert.equal(r[0].id, 'a0');
  assert.ok(r[0].etiqueta.length <= 40 && r[0].etiqueta.endsWith('…'));
  assert.equal(R.normalizarItems('basura').length, 0);
});

test('colocar: el lienzo cabe entero en la ventana', () => {
  const R = cargar().sb.LuneRadial;
  assert.deepEqual({ ...R.colocar(10, 10) }, { cx: 184, cy: 184, left: 0, top: 0 });
  assert.deepEqual({ ...R.colocar(1275, 815) }, { cx: 1280 - 184, cy: 820 - 184, left: 1280 - 368, top: 820 - 368 });
  assert.deepEqual({ ...R.colocar(640, 400) }, { cx: 640, cy: 400, left: 456, top: 216 });
});

function menu(S, props) {
  const el = S.h(S.sb.RadialMenu, { x: 640, y: 400, items: items3, ...props });
  const pintar = () => S.render(el);
  return { el, pintar };
}
const capa = (arbol) => conClase(arbol, 'ln-radial-capa')[0];
const svg = (arbol) => buscar(arbol, (n) => n.type === 'svg')[0];
const seleccionado = (arbol) => buscar(arbol, (n) => n.type === 'path' && /\bis-sel\b/.test(n.props.className || '') && n.props['data-i'] != null)
  .map((n) => n.props['data-i']);
const puntero = (x, y, button = 0) => ({ clientX: x, clientY: y, button, preventDefault() {} });

test('RadialMenu: abre con escala, resalta, pulsa (0.8) y ejecuta al soltar', () => {
  const S = cargar();
  const elegidos = [], cierres = [];
  const { pintar } = menu(S, { onElegir: (it, i) => elegidos.push([it.id, i]), onCerrar: () => cierres.push(1) });
  let a = pintar();
  assert.ok(!/is-abierto/.test(svg(a).props.className), 'empieza pequeño (escala .2)');
  S.avanzar(1);
  a = pintar();
  assert.ok(/is-abierto/.test(svg(a).props.className), 'y crece a 1');
  assert.deepEqual({ ...svg(a).props.style }, { left: 456, top: 216 });
  assert.equal(buscar(a, (n) => n.props && n.props.role === 'menuitem').length, 3);
  assert.equal(texto(conClase(a, 'ln-radial-txt')[0]), 'Lune');
  capa(a).props.onPointerMove(puntero(640 + 100, 400 - 60));      // arriba a la derecha → botón 0 (0°–120°)
  a = pintar();
  assert.deepEqual(seleccionado(a), [0]);
  assert.equal(texto(conClase(a, 'ln-radial-txt')[0]), 'Ajustes');
  assert.equal(conClase(a, 'ln-radial-arco').length, 1, 'arco amarillo del seleccionado');
  capa(a).props.onPointerDown(puntero(640 + 100, 400 + 60));      // abajo a la derecha → botón 1 (120°–240°)
  a = pintar();
  assert.ok(/is-pulsado/.test(svg(a).props.className), 'al pulsar: escala 0.8');
  capa(a).props.onPointerUp(puntero(640 + 100, 400 + 60, 2));     // el derecho no ejecuta
  assert.deepEqual(elegidos, []);
  capa(a).props.onPointerUp(puntero(640 + 100, 400 + 60));
  assert.deepEqual(elegidos, [['voz', 1]]);
  capa(a).props.onPointerUp(puntero(640 + 100, 400 + 60));
  capa(a).props.onContextMenu({ preventDefault() {} });
  assert.deepEqual(elegidos, [['voz', 1]], 'una sola vez');
  assert.deepEqual(cierres, [], 'ni cierra después de elegir');
});

test('RadialMenu: soltar en la zona muerta, Esc, clic derecho y perder el foco cierran sin elegir', () => {
  for (const cerrarCon of ['centro', 'esc', 'derecho', 'blur', 'deshabilitado']) {
    const S = cargar();
    const elegidos = [], cierres = [];
    const { pintar } = menu(S, { onElegir: (it) => elegidos.push(it.id), onCerrar: () => cierres.push(cerrarCon) });
    const a = pintar();
    if (cerrarCon === 'centro') capa(a).props.onPointerUp(puntero(640 + 40, 400 + 40));
    if (cerrarCon === 'esc') S.dispatch(S.evento('keydown', { key: 'Escape' }));
    if (cerrarCon === 'derecho') capa(a).props.onContextMenu({ preventDefault() {} });
    if (cerrarCon === 'blur') S.dispatch(S.evento('blur'));
    if (cerrarCon === 'deshabilitado') {
      capa(a).props.onPointerUp(puntero(640 - 100, 400 - 30));     // botón 2 (240°–360°), deshabilitado
      assert.deepEqual([elegidos, cierres], [[], []], 'un botón deshabilitado no hace nada');
      continue;
    }
    assert.deepEqual([elegidos, cierres], [[], [cerrarCon]], cerrarCon);
    S.desmontar();
    assert.equal(S.nOyentes('keydown') + S.nOyentes('blur'), 0, 'al desmontar suelta los oyentes');
  }
});

test('RadialMenu: teclado (flechas y Enter)', () => {
  const S = cargar();
  const elegidos = [];
  const { pintar } = menu(S, { items: items3.slice(0, 2), onElegir: (it) => elegidos.push(it.id) });
  pintar();
  S.dispatch(S.evento('keydown', { key: 'ArrowRight' }));
  let a = pintar();
  assert.deepEqual(seleccionado(a), [0]);
  S.dispatch(S.evento('keydown', { key: 'ArrowRight' }));
  S.dispatch(S.evento('keydown', { key: 'ArrowRight' }));
  S.dispatch(S.evento('keydown', { key: 'ArrowLeft' }));
  a = pintar();
  assert.deepEqual(seleccionado(a), [1]);
  const e = S.evento('keydown', { key: 'Enter' });
  S.dispatch(e);
  assert.ok(e.prevenido);
  assert.deepEqual(elegidos, ['voz']);
});

function host(S, props = {}) {
  const avisos = [], vistas = [], caras = [];
  const el = S.h(S.sb.RadialHost, { onAviso: (m) => avisos.push(m), onNavegar: (v) => vistas.push(v), onExpresion: (x) => caras.push(x), ...props });
  return { el, avisos, vistas, caras, pintar: () => S.render(el) };
}
const abrir = (S, detalle) => S.dispatch(new S.sb.CustomEvent('lune-radial', { detail: detalle }));
function sfxFalso() {
  const tocados = [];
  return { tocados, obj: { tocar: (n, o) => { tocados.push([n, o && o.vol]); return Promise.resolve(null); } } };
}

test('RadialHost: pide los botones al puente y ejecuta con accion_menu', () => {
  const E = escritorioFalso({
    radial_estado: JSON.stringify({ sonidos: true, volumen: 0.3 }),
    acciones_catalogo: (tipo) => JSON.stringify(tipo === 'radial'
      ? [{ id: 'ajustes', etiqueta: 'Ajustes', icono: 'gear' }, { id: 'voz', etiqueta: 'Voz', icono: 'volume', marcado: true },
        { id: 'expresiones', etiqueta: 'Expresiones', icono: 'smile' }, { id: 'chat', etiqueta: 'Escribirle', icono: 'message' }]
      : [{ id: 'expresion', etiqueta: 'Contenta', icono: 'smile', arg: 'happy' }, { id: 'expresion', etiqueta: 'Triste', icono: 'frown', arg: 'sad' }]),
    accion_menu: () => true,
  });
  const sfx = sfxFalso();
  const S = cargar({ escritorio: E.obj, globales: { luneSfx: sfx.obj } });
  const H = host(S, { mascotaFuera: true });
  assert.equal(H.pintar().length, 0, 'cerrado: nada');
  abrir(S, { x: 300, y: 300, tipo: 'principal' });
  let a = H.pintar();
  assert.deepEqual(E.de('acciones_catalogo'), [['radial']]);
  assert.equal(buscar(a, (n) => n.props && n.props.role === 'menuitem').length, 4);
  assert.deepEqual(sfx.tocados.map((t) => t[0]), ['menu_abrir']);
  assert.equal(sfx.tocados[0][1], 0.3, 'volumen de menu.volumen');
  // botón 1 de 4 (90°–180°): «voz» → accion_menu('voz', '')
  capa(a).props.onPointerUp(puntero(300 + 100, 300 + 20));
  a = H.pintar();
  assert.deepEqual(E.de('accion_menu'), [['voz', '']]);
  assert.equal(a.length, 0, 'se cierra al elegir');
  assert.deepEqual(sfx.tocados.map((t) => t[0]), ['menu_abrir', 'menu_boton']);
  // «ajustes» y «chat» navegan en la propia página (sin accion_menu)
  abrir(S, { x: 300, y: 300 });
  a = H.pintar();
  capa(a).props.onPointerUp(puntero(300 + 60, 300 - 100));        // botón 0
  abrir(S, { x: 300, y: 300 });
  a = H.pintar();
  capa(a).props.onPointerUp(puntero(300 - 100, 300 - 20));        // botón 3 (270°–360°): chat
  assert.deepEqual(H.vistas, ['settings', 'chat']);
  assert.deepEqual(E.de('accion_menu'), [['voz', '']]);
  // «expresiones» → segundo radial; con la mascota fuera, la expresión la pone el backend
  abrir(S, { x: 300, y: 300 });
  a = H.pintar();
  capa(a).props.onPointerUp(puntero(300 - 60, 300 + 100));        // botón 2: expresiones
  a = H.pintar();
  assert.deepEqual(E.de('acciones_catalogo').slice(-1), [['expresiones']]);
  assert.equal(texto(conClase(a, 'ln-radial-txt')[0]), 'Expresiones');
  capa(a).props.onPointerUp(puntero(300 + 100, 300 - 10));        // botón 0 de 2: happy
  assert.deepEqual(E.de('accion_menu').slice(-1), [['expresion', 'happy']]);
  assert.deepEqual(H.caras, []);
  // Esc: cierra con su sonido
  abrir(S, { x: 300, y: 300 });
  H.pintar();
  S.dispatch(S.evento('keydown', { key: 'Escape' }));
  a = H.pintar();
  assert.equal(a.length, 0);
  assert.equal(sfx.tocados[sfx.tocados.length - 1][0], 'menu_cerrar');
});

test('RadialHost: con Lune en la barra la expresión la pone la barra; sin sonidos no suena', () => {
  const E = escritorioFalso({
    radial_estado: JSON.stringify({ sonidos: false, volumen: 1 }),
    acciones_catalogo: (tipo) => JSON.stringify(tipo === 'expresiones'
      ? [{ id: 'expresion', etiqueta: 'Contenta', icono: 'smile', arg: 'happy' }] : [{ id: 'expresiones', etiqueta: 'Expresiones' }]),
    accion_menu: () => true,
  });
  const sfx = sfxFalso();
  const S = cargar({ escritorio: E.obj, globales: { luneSfx: sfx.obj } });
  const H = host(S, { mascotaFuera: false });
  H.pintar();
  abrir(S, { x: 500, y: 500 });
  let a = H.pintar();
  capa(a).props.onPointerUp(puntero(500, 500 - 150));
  a = H.pintar();
  capa(a).props.onPointerUp(puntero(500, 500 + 150));             // n = 1: todo el anillo
  assert.deepEqual(H.caras, ['happy']);
  assert.deepEqual(E.de('accion_menu'), []);
  assert.deepEqual(sfx.tocados, []);
});

test('RadialHost: menú vacío avisa; respuesta vieja ignorada; accion_menu false avisa', () => {
  let pendiente = null;
  const E = escritorioFalso({ accion_menu: () => false });
  E.obj.acciones_catalogo = (tipo, cb) => { pendiente = cb; };        // responde tarde (asíncrono)
  const S = cargar({ escritorio: E.obj });
  const H = host(S);
  H.pintar();
  abrir(S, { x: 200, y: 200 });
  const vieja = pendiente;
  abrir(S, { x: 210, y: 210 });
  const nueva = pendiente;
  vieja(JSON.stringify([{ id: 'voz', etiqueta: 'VIEJA' }]));
  assert.equal(H.pintar().length, 0, 'la respuesta del primer pedido no abre nada');
  nueva(JSON.stringify([]));
  H.pintar();
  assert.deepEqual(H.avisos, ['No hay acciones para este menú.']);
  abrir(S, { x: 200, y: 200 });
  pendiente(JSON.stringify([{ id: 'voz', etiqueta: 'Voz' }]));
  const a = H.pintar();
  capa(a).props.onPointerUp(puntero(200, 50));
  assert.deepEqual(H.avisos.slice(-1), ['No pude: Voz']);
});

test('RadialHost sin backend: demo local; LuneRadial.abrir sin coordenadas usa el centro', () => {
  const S = cargar();
  const H = host(S);
  H.pintar();
  const detalles = [];
  S.sb.addEventListener('lune-radial', (e) => detalles.push(e.detail));
  assert.equal(S.sb.LuneRadial.abrir(), true);
  assert.deepEqual({ ...detalles[0] }, { x: 640, y: 410, tipo: 'principal' });
  let a = H.pintar();
  const n = buscar(a, (x) => x.props && x.props.role === 'menuitem').length;
  assert.equal(n, S.sb.LuneRadial.DEMO.principal.length);
  // botón «voz» de la demo (índice 4 de 6: 240°–300°)
  capa(a).props.onPointerUp(puntero(640 - 150, 410 + 10));
  assert.match(H.avisos[0], /^Demo · Voz/);
  S.sb.LuneRadial.abrir(100, 100, 'secundario');
  a = H.pintar();
  assert.equal(buscar(a, (x) => x.props && x.props.role === 'menuitem').length, 3);
});
