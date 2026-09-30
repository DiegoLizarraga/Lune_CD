/*
 * Lista de tareas estilo Microsoft To Do (Lune CD 10.9) en el sandbox de jsx_falso.mjs (sin navegador):
 *   · extra/tareas.jsx: TareasPanel con un window.luneTareas falso (estado, agregar, completar, al_mi_dia, quitar y la
 *     señal cambio): «Mi día» con la fecha, filas con su lista, «Completadas (n)» plegable y tachada, marcar con una
 *     animación corta, Enter en «Agregar una tarea», papelera con «¿Quitar?», bombilla → «Sugerencias» (Ayer /
 *     Agregado recientemente / Más antiguas) con «+», estado vacío, refresco con `cambio` y sin puente (aviso);
 *   · LuneTareas (utilidades puras);
 *   · sidebar.jsx: la entrada «Tareas» con las pendientes de hoy (se actualiza con `cambio`, abre la vista);
 *   · app.jsx: la vista «tareas» por 'lune-vista', por la barra y por el CommandMenu.
 * Lo lanza también tests/test_puente_tareas.py.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  crearSandbox, senal, KIT, EXTRA, buscar, boton, botones, todoTexto, conClase, texto,
} from './jsx_falso.mjs';

const TAREAS = path.join(EXTRA, 'tareas.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
export const RANURAS = ['estado', 'agregar', 'completar', 'al_mi_dia', 'quitar'];
export const SENALES = ['cambio'];

/** Objeto del QWebChannel falso: ranuras que apuntan y responden por callback, y señales. */
function puenteFalso(respuestas = {}) {
  const llamadas = [];
  const obj = {};
  for (const s of SENALES) obj[s] = senal();
  for (const n of RANURAS) {
    obj[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push([n, ...args]);
      const r = respuestas[n];
      const v = typeof r === 'function' ? r(...args) : r;
      if (cb) cb(v);
    };
  }
  return { obj, llamadas, respuestas, de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)) };
}

/** Un backend con estado, como ui/puente_tareas.py: `sec` dice dónde sale en las sugerencias. */
function backend(inicial = []) {
  let n = 100;
  const tareas = inicial.map((t) => ({ lista: 'Tareas', creada: '2026-09-29T09:00:00', hecha: false, hecha_en: '', en_mi_dia: true, ...t }));
  const limpia = ({ sec, ...t }) => t;
  const estado = () => {
    const pend = tareas.filter((t) => !t.hecha && t.en_mi_dia);
    const fuera = tareas.filter((t) => !t.hecha && !t.en_mi_dia);
    return {
      disponible: true,
      mi_dia: { fecha: '2026-09-29', fecha_larga: 'martes, 29 de septiembre', pendientes: pend.map(limpia),
        hechas: tareas.filter((t) => t.hecha).map(limpia) },
      sugerencias: { ayer: fuera.filter((t) => t.sec === 'ayer').map(limpia), recientes: fuera.filter((t) => t.sec === 'recientes').map(limpia),
        antes: fuera.filter((t) => t.sec === 'antes').map(limpia) },
      contador: { hoy: pend.length, total: pend.length + fuera.length },
    };
  };
  const resp = (ok, error, tarea) => JSON.stringify({ ok, error, ...(tarea ? { tarea: limpia(tarea) } : {}), estado: estado() });
  const buscarT = (id) => tareas.find((t) => t.id === id);
  const P = puenteFalso({
    estado: () => JSON.stringify(estado()),
    agregar(txt) {
      const t = { id: `t${++n}`, texto: txt, lista: 'Tareas', creada: '2026-09-29T12:00:00', hecha: false, hecha_en: '', en_mi_dia: true };
      tareas.unshift(t);
      return resp(true, '', t);
    },
    completar(id, h) {
      const t = buscarT(id);
      if (!t) return resp(false, 'Esa tarea ya no está.');
      t.hecha = !!h; t.hecha_en = h ? '2026-09-29T12:30:00' : '';
      return resp(true, '', t);
    },
    al_mi_dia(id, si) {
      const t = buscarT(id);
      if (!t) return resp(false, 'Esa tarea ya no está.');
      t.en_mi_dia = !!si;
      return resp(true, '', t);
    },
    quitar(id) {
      const i = tareas.findIndex((t) => t.id === id);
      if (i < 0) return resp(false, 'Esa tarea ya no está.');
      tareas.splice(i, 1);
      return resp(true, '');
    },
  });
  return { P, tareas, estado };
}

const DEMO = [
  { id: 'a1', texto: 'Comprar pan' },
  { id: 'a2', texto: 'Llamar al dentista', lista: 'Recordatorios' },
  { id: 'h1', texto: 'Regar las plantas', hecha: true, hecha_en: '2026-09-29T08:00:00' },
  { id: 's1', texto: 'Pagar la luz', en_mi_dia: false, sec: 'ayer', creada: '2026-09-28T10:00:00' },
  { id: 's2', texto: 'Terminar el informe', en_mi_dia: false, sec: 'recientes', creada: '2026-09-25T10:00:00' },
  { id: 's3', texto: 'Ordenar el garaje', en_mi_dia: false, sec: 'antes', creada: '2026-08-01T10:00:00' },
];

function cargar({ tareas = null, globales = {} } = {}) {
  return crearSandbox({ archivos: [TAREAS], globales: { ...(tareas ? { luneTareas: tareas } : {}), ...globales } });
}
const filas = (a) => conClase(a, 'ln-td-fila');
const fila = (a, id) => filas(a).find((f) => f.props['data-id'] === id);
const enFila = (f, pred) => buscar(f.hijos, pred)[0];
const circulo = (f) => enFila(f, (n) => n.props && n.props.role === 'checkbox');
const porEtiqueta = (nodos, l) => buscar(nodos, (n) => n.type === 'button' && n.props['aria-label'] === l);
const entrada = (a) => buscar(a, (n) => n.type === 'input' && n.props['aria-label'] === 'Agregar una tarea')[0];

// ── Registro y utilidades puras ──────────────────────────────────────────────
test('se registra solo sin pisar globales', () => {
  assert.deepEqual(plano(cargar().nuevas.sort()), ['LuneTareas', 'TareasPanel']);
});

test('LuneTareas: normalizar, fecha larga en español y el texto del contador', () => {
  const T = cargar().sb.LuneTareas;
  assert.equal(T.fechaLarga(new Date(2026, 8, 29)), 'martes, 29 de septiembre');
  assert.equal(T.fechaLarga(new Date(2026, 0, 4)), 'domingo, 4 de enero');
  assert.deepEqual(plano(T.normalizarTarea({ id: 'x1', texto: '  hola\u0007  mundo ', lista: 'Otra', hecha: 'sí', en_mi_dia: true })),
    { id: 'x1', texto: 'hola mundo', lista: 'Tareas', creada: '', hecha: false, hecha_en: '', en_mi_dia: true });
  for (const malo of [null, 5, { id: '<x>' }, { id: '' }, { id: 'a b' }]) assert.equal(T.normalizarTarea(malo), null, JSON.stringify(malo));
  assert.equal(T.normalizarTarea({ id: 'r', lista: 'Recordatorios', texto: 'x'.repeat(500) }).texto.length, 200);
  const e = T.normalizarEstado({ disponible: true, mi_dia: { pendientes: [{ id: 'a' }, { id: '!!' }], hechas: 'no' }, contador: { hoy: -3, total: 2.7 } },
    new Date(2026, 8, 29));
  assert.equal(e.mi_dia.fecha_larga, 'martes, 29 de septiembre', 'sin fecha del backend: la de la página');
  assert.deepEqual(e.mi_dia.pendientes.map((t) => t.id), ['a']);
  assert.deepEqual(plano(e.mi_dia.hechas), []);
  assert.deepEqual(plano(e.contador), { hoy: 0, total: 2 });
  assert.deepEqual(plano(T.normalizarEstado(null).sugerencias), { ayer: [], recientes: [], antes: [] });
  assert.equal(T.normalizarEstado(null).disponible, false);
  assert.equal(T.textoContador({ hoy: 3, total: 5 }), '3 para hoy · 5 en total');
  assert.equal(T.textoContador({ hoy: 2, total: 2 }), '2 para hoy');
  assert.equal(T.textoContador({ hoy: 0, total: 1 }), '1 pendiente');
  assert.equal(T.textoContador({ hoy: 0, total: 4 }), '4 pendientes');
  assert.equal(T.textoContador({ hoy: 0, total: 0 }), 'Nada pendiente');
  assert.equal(T.textoContador({ hoy: 3, total: 5 }, false), 'Mi día');
});

// ── La vista ─────────────────────────────────────────────────────────────────
test('Mi día: fecha, pendientes con su lista, «Completadas (n)» plegable y tachada', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  const t = todoTexto(a);
  assert.match(t, /MI DÍA/);
  assert.match(t, /martes, 29 de septiembre/);
  assert.deepEqual(filas(a).map((f) => f.props['data-id']), ['a1', 'a2', 'h1'], 'pendientes de Mi día y luego las hechas');
  assert.match(texto(fila(a, 'a2')), /Llamar al dentista.*Recordatorios/);
  assert.match(texto(fila(a, 'a1')), /Comprar pan.*Tareas/);
  assert.ok(fila(a, 'h1').props.className.includes('is-hecha'), 'la hecha va tachada');
  assert.equal(circulo(fila(a, 'h1')).props['aria-checked'], true);
  assert.equal(circulo(fila(a, 'a1')).props['aria-checked'], false);
  const plegar = boton(a, 'Completadas (1)');
  assert.ok(plegar && plegar.props['aria-expanded'] === true);
  plegar.props.onClick();
  a = S.render(el);
  assert.deepEqual(filas(a).map((f) => f.props['data-id']), ['a1', 'a2'], 'plegada: sin las hechas');
  assert.equal(boton(a, 'Completadas (1)').props['aria-expanded'], false);
  assert.equal(conClase(a, 'ln-td-sug').length, 0, 'las sugerencias empiezan cerradas');
  assert.ok(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(todoTexto(a)), 'sin emojis');
});

test('marcar: el círculo se anima y luego se completa; desmarcar va al momento', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  circulo(fila(a, 'a1')).props.onClick();
  a = S.render(el);
  assert.ok(fila(a, 'a1').props.className.includes('is-marcando'), 'la animación corta');
  assert.equal(circulo(fila(a, 'a1')).props['aria-checked'], true);
  assert.deepEqual(plano(B.P.de('completar')), [], 'todavía no');
  circulo(fila(a, 'a1')).props.onClick();            // doble clic durante la animación: una sola vez
  S.avanzar(320);
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('completar')), [['a1', true]]);
  assert.deepEqual(filas(a).map((f) => f.props['data-id']), ['a2', 'a1', 'h1'], 'pasó a «Completadas»');
  assert.match(texto(boton(a, 'Completadas')), /Completadas \(2\)/);
  circulo(fila(a, 'h1')).props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('completar')), [['a1', true], ['h1', false]]);
  assert.ok(fila(a, 'h1') && !fila(a, 'h1').props.className.includes('is-hecha'));
});

test('agregar: Enter la añade a Mi día y limpia la barra; vacía no', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  const tecla = (k) => ({ key: k, preventDefault() {} });
  assert.equal(entrada(a).props.placeholder, 'Agregar una tarea');
  entrada(a).props.onKeyDown(tecla('Enter'));
  assert.deepEqual(plano(B.P.de('agregar')), [], 'vacía: nada');
  entrada(a).props.onChange({ target: { value: '   ' } });
  a = S.render(el);
  entrada(a).props.onKeyDown(tecla('Enter'));
  assert.deepEqual(plano(B.P.de('agregar')), [], 'solo espacios: nada');
  entrada(a).props.onChange({ target: { value: '  Sacar  la basura\u0007 ' } });
  a = S.render(el);
  assert.ok(boton(a, 'Agregar'), 'con texto sale el botón');
  entrada(a).props.onKeyDown(tecla('a'));
  assert.deepEqual(plano(B.P.de('agregar')), []);
  entrada(a).props.onKeyDown(tecla('Enter'));
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('agregar')), [['Sacar la basura']]);
  assert.equal(entrada(a).props.value, '', 'la barra queda limpia');
  assert.equal(filas(a)[0].props['data-id'], 't101', 'la nueva arriba, en Mi día');
  entrada(a).props.onChange({ target: { value: 'x'.repeat(400) } });
  a = S.render(el);
  assert.equal(entrada(a).props.value.length, 200, 'como mucho 200 caracteres');
});

test('quitar: papelera con «¿Quitar?» (No / Quitar) que se cancela sola', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  porEtiqueta(fila(a, 'a1').hijos, 'Quitar tarea')[0].props.onClick();
  a = S.render(el);
  assert.match(texto(fila(a, 'a1')), /¿Quitar\?/);
  enFila(fila(a, 'a1'), (n) => n.type === 'button' && texto(n) === 'No').props.onClick();
  a = S.render(el);
  assert.doesNotMatch(texto(fila(a, 'a1')), /¿Quitar\?/);
  porEtiqueta(fila(a, 'a1').hijos, 'Quitar tarea')[0].props.onClick();
  S.avanzar(4100);
  a = S.render(el);
  assert.doesNotMatch(texto(fila(a, 'a1')), /¿Quitar\?/, 'se cancela sola');
  assert.deepEqual(plano(B.P.de('quitar')), []);
  porEtiqueta(fila(a, 'a2').hijos, 'Quitar tarea')[0].props.onClick();
  a = S.render(el);
  enFila(fila(a, 'a2'), (n) => n.type === 'button' && texto(n) === 'Quitar').props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('quitar')), [['a2']]);
  assert.equal(fila(a, 'a2'), undefined);
  // «Quitar de Mi día» (el sol tachado): a las sugerencias
  porEtiqueta(fila(a, 'a1').hijos, 'Quitar de Mi día')[0].props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('al_mi_dia')), [['a1', false]]);
  assert.equal(fila(a, 'a1'), undefined);
});

test('sugerencias: la bombilla abre «Ayer», «Agregado recientemente» y «Más antiguas» con «+» a Mi día', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  const bombilla = boton(a, 'Sugerencias');
  assert.match(texto(bombilla), /Sugerencias3/, 'con cuántas hay');
  bombilla.props.onClick();
  a = S.render(el);
  const panel = conClase(a, 'ln-td-sug')[0];
  assert.ok(panel, 'el panel de la derecha');
  assert.deepEqual(conClase(panel.hijos, 'ln-td-sec').map(texto), ['Ayer', 'Agregado recientemente', 'Más antiguas']);
  assert.deepEqual(filas(panel.hijos).map((f) => f.props['data-id']), ['s1', 's2', 's3']);
  assert.equal(porEtiqueta(panel.hijos, 'Quitar tarea').length, 0, 'en las sugerencias no hay papelera');
  porEtiqueta(fila(panel.hijos, 's2').hijos, 'Agregar a Mi día')[0].props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(B.P.de('al_mi_dia')), [['s2', true]]);
  assert.ok(fila(conClase(a, 'ln-td-main')[0].hijos, 's2'), 'ya está en Mi día');
  assert.deepEqual(filas(conClase(a, 'ln-td-sug')[0].hijos).map((f) => f.props['data-id']), ['s1', 's3']);
  // Marcar desde las sugerencias también la completa
  circulo(fila(conClase(a, 'ln-td-sug')[0].hijos, 's1')).props.onClick();
  S.avanzar(320);
  assert.deepEqual(plano(B.P.de('completar')), [['s1', true]]);
  a = S.render(el);
  porEtiqueta(a, 'Cerrar sugerencias')[0].props.onClick();
  a = S.render(el);
  assert.equal(conClase(a, 'ln-td-sug').length, 0);
});

test('estado vacío como el de To Do (dibujo de línea, sin emojis) y botón a las sugerencias', () => {
  const B = backend([{ id: 's1', texto: 'Pagar la luz', en_mi_dia: false, sec: 'ayer' }]);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  const vacio = conClase(a, 'ln-td-vacio')[0];
  assert.ok(vacio);
  assert.match(texto(vacio), /Concéntrate en tu día/);
  assert.match(texto(vacio), /Termina tus tareas con Mi día, una lista que se actualiza todos los días/);
  assert.ok(buscar(vacio.hijos, (n) => n.type === 'svg').length === 1, 'un dibujo SVG');
  boton(a, 'Ver sugerencias (1)').props.onClick();
  a = S.render(el);
  assert.ok(conClase(a, 'ln-td-sug')[0]);
  // Sin nada de nada: «Anotar una tarea» y el panel de sugerencias lo dice
  const B2 = backend([]);
  const S2 = cargar({ tareas: B2.P.obj });
  const el2 = S2.h(S2.sb.TareasPanel);
  a = S2.render(el2);
  assert.ok(boton(a, 'Anotar una tarea'));
  boton(a, 'Sugerencias').props.onClick();
  assert.match(todoTexto(S2.render(el2)), /Nada que sugerir/);
});

test('se refresca con luneTareas.cambio (Lune anotó algo desde el chat) y suelta la señal al desmontar', () => {
  const B = backend(DEMO);
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  S.render(el);
  assert.equal(B.P.obj.cambio.oyentes, 1);
  B.tareas.unshift({ id: 'c1', texto: 'Llevar el coche al taller', lista: 'Tareas', creada: '2026-09-29T13:00:00', hecha: false, hecha_en: '', en_mi_dia: true });
  B.P.obj.cambio.emit(JSON.stringify(B.estado()));
  const a = S.render(el);
  assert.equal(filas(a)[0].props['data-id'], 'c1');
  B.P.obj.cambio.emit('no es json');
  assert.equal(filas(S.render(el))[0].props['data-id'], 'c1', 'lo raro se ignora');
  S.desmontar();
  assert.equal(B.P.obj.cambio.oyentes, 0);
});

test('errores del backend: el mensaje sale en la vista', () => {
  const B = backend(DEMO);
  B.P.respuestas.agregar = () => JSON.stringify({ ok: false, error: 'No pude anotarla: disco lleno', estado: B.estado() });
  const S = cargar({ tareas: B.P.obj });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  entrada(a).props.onChange({ target: { value: 'algo' } });
  a = S.render(el);
  entrada(a).props.onKeyDown({ key: 'Enter', preventDefault() {} });
  a = S.render(el);
  assert.match(texto(conClase(a, 'ln-td-msg')[0]), /disco lleno/);
  assert.equal(entrada(a).props.value, 'algo', 'no se pierde lo escrito');
  // Backend sin tareas disponibles (memoria que no sirve): aviso
  const P2 = puenteFalso({ estado: JSON.stringify({ disponible: false, mi_dia: {}, sugerencias: {}, contador: {} }) });
  const S2 = cargar({ tareas: P2.obj });
  a = S2.render(S2.h(S2.sb.TareasPanel));
  assert.match(texto(conClase(a, 'ln-td-aviso')[0]), /no puedo leer tus tareas/);
  assert.equal(entrada(a).props.disabled, true);
});

test('sin puente (navegador suelto): aviso, vista vacía y no revienta', () => {
  const S = cargar();
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  assert.match(texto(conClase(a, 'ln-td-aviso')[0]), /Tus tareas viven en la app de Lune/);
  assert.ok(conClase(a, 'ln-td-vacio')[0]);
  assert.equal(entrada(a).props.disabled, true);
  entrada(a).props.onChange({ target: { value: 'algo' } });
  a = S.render(el);
  entrada(a).props.onKeyDown({ key: 'Enter', preventDefault() {} });
  a = S.render(el);
  assert.match(texto(conClase(a, 'ln-td-msg')[0]), /necesitan la app/);
  boton(a, 'Sugerencias').props.onClick();
  assert.ok(conClase(S.render(el), 'ln-td-sug')[0]);
});

test('en la app el canal llega después: espera sin aviso y carga con lune-ready', () => {
  const B = backend(DEMO);
  const S = cargar({ globales: { qt: { webChannelTransport: {} } } });
  const el = S.h(S.sb.TareasPanel);
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-td-aviso').length, 0, 'todavía no se sabe: sin aviso');
  assert.equal(S.nOyentes('lune-ready'), 1);
  S.sb.luneTareas = B.P.obj;
  S.dispatch(new S.sb.Event('lune-ready'));
  a = S.render(el);
  assert.deepEqual(filas(a).map((f) => f.props['data-id']), ['a1', 'a2', 'h1']);
  // Backend viejo sin el objeto: el aviso
  const S2 = cargar({ globales: { qt: { webChannelTransport: {} } } });
  const el2 = S2.h(S2.sb.TareasPanel);
  S2.render(el2);
  S2.dispatch(new S2.sb.Event('lune-ready'));
  assert.match(texto(conClase(S2.render(el2), 'ln-td-aviso')[0]), /app de Lune/);
});

// ── Barra lateral ────────────────────────────────────────────────────────────
function cargarBarra(globales = {}) {
  return crearSandbox({ archivos: [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx')],
    globales: { document: { getElementById: () => null, createElement: () => ({}), head: { appendChild() {} } }, ...globales } });
}
const acceso = (a) => conClase(a, 'ln-tareas-acc')[0];

test('barra lateral: «Tareas» siempre a la vista con las pendientes de hoy; se actualiza sola y abre la vista', () => {
  const B = backend(DEMO);
  const S = cargarBarra({ luneTareas: B.P.obj });
  const abiertas = [];
  const props = { provider: 'local', onProvider() {}, asistenteState: 'normal', asistenteFuera: true, onTraer() {}, vista: 'chat',
    onTareas: () => abiertas.push(1) };
  let a = S.render(S.h(S.sb.Sidebar, props));
  let b = acceso(a);
  assert.ok(b, 'la entrada');
  assert.match(texto(b), /Tareas/);
  assert.match(texto(b), /2 para hoy · 5 en total/);
  assert.equal(texto(conClase(b.hijos, 'ln-tareas-acc-num')[0]), '2');
  assert.ok(b.props.className.includes('has-pend'));
  assert.equal(buscar(a, (n) => n.type === 'button' && n.props['data-accent']).length, 2, 'las pestañas de proveedor no cambian');
  assert.match(todoTexto(a), /ASISTENTE PERSONAL/);
  b.props.onClick();
  assert.equal(abiertas.length, 1);
  // Lune anota algo desde el chat → cambio
  B.tareas.unshift({ id: 'c1', texto: 'Nueva', lista: 'Tareas', creada: '', hecha: false, hecha_en: '', en_mi_dia: true });
  B.P.obj.cambio.emit(JSON.stringify(B.estado()));
  a = S.render(S.h(S.sb.Sidebar, { ...props, vista: 'tareas' }));
  b = acceso(a);
  assert.match(texto(b), /3 para hoy · 6 en total/);
  assert.ok(b.props.className.includes('is-active'), 'resaltada con la vista abierta');
  S.desmontar();
  assert.equal(B.P.obj.cambio.oyentes, 0, 'suelta la señal');
  assert.deepEqual(plano(S.sb.LuneBarra.contadorTareas('{"disponible":true,"contador":{"hoy":1,"total":0}}')), { hoy: 1, total: 1, ok: true });
  assert.equal(S.sb.LuneBarra.textoTareas({ hoy: 0, total: 0, ok: true }), 'Nada pendiente');
});

test('barra lateral sin puente: acceso sin número; sin onTareas pide la vista con lune-vista', () => {
  const S = cargarBarra();
  const vistas = [];
  S.sb.addEventListener('lune-vista', (e) => vistas.push(e.detail));
  const a = S.render(S.h(S.sb.Sidebar, { provider: 'local', onProvider() {}, asistenteState: 'normal', asistenteFuera: true }));
  const b = acceso(a);
  assert.match(texto(b), /TareasMi día/);
  assert.equal(conClase(b.hijos, 'ln-tareas-acc-num').length, 0);
  b.props.onClick();
  assert.deepEqual(vistas, ['tareas']);
});

// ── app.jsx ──────────────────────────────────────────────────────────────────
function cargarApp(tareas) {
  const props = {};
  const stub = (n) => function (p) { props[n] = p; return null; };
  const base = { asistente_visible(cb) { cb(false); }, proveedores(cb) { cb('{}'); }, proveedor_elegido() {} };
  const lune = new Proxy(base, { get(t, k) { if (!(k in t) && typeof k === 'string') t[k] = senal(); return t[k]; } });
  const S = crearSandbox({
    archivos: [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx'), TAREAS, path.join(KIT, 'app.jsx')],
    lune,
    globales: {
      document: { body: { classList: { toggle() {} } }, getElementById: () => null, createElement: () => ({}), head: { appendChild() {} } },
      localStorage: { getItem: () => null, setItem() {} },
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), CommandMenu: stub('CommandMenu'), SettingsPanel: stub('SettingsPanel'),
      luneTareas: tareas,
    },
  });
  const app = S.h(S.sb.LuneApp);
  return { S, props, pintar: () => S.render(app) };
}

test('app: la vista «tareas» por lune-vista, por la barra lateral y por el CommandMenu', () => {
  const B = backend(DEMO);
  const A = cargarApp(B.P.obj);
  let a = A.pintar();
  assert.equal(conClase(a, 'ln-td').length, 0, 'empieza en el chat');
  A.S.dispatch(new A.S.sb.CustomEvent('lune-vista', { detail: 'tareas' }));
  a = A.pintar();
  assert.ok(conClase(a, 'ln-td')[0], 'la vista de tareas');
  assert.match(todoTexto(a), /Comprar pan/);
  const item = A.props.CommandMenu.items.find((i) => i.label === 'Tareas');
  assert.ok(item, 'en el menú');
  A.props.CommandMenu.items.find((i) => i.label === 'Chat').onClick();
  a = A.pintar();
  assert.equal(conClase(a, 'ln-td').length, 0);
  acceso(a).props.onClick();
  a = A.pintar();
  assert.ok(conClase(a, 'ln-td')[0], 'desde la barra lateral');
  assert.ok(acceso(a).props.className.includes('is-active'));
  A.props.CommandMenu.items.find((i) => i.label === 'Chat').onClick();
  A.pintar();
  item.onClick();
  assert.ok(conClase(A.pintar(), 'ln-td')[0], 'desde el menú');
});
