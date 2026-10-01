/*
 * Tarjetas de Ajustes del corte 4 (extra/apariencia.jsx y extra/juego.jsx) en el sandbox de
 * jsx_falso.mjs, con y sin backend (window.luneEscritorio falso).
 *
 * No acaba en .test.mjs: lo lanza tests/test_jsx_apariencia.py con `node --test` (y le pasa,
 * si existe, la tabla de ui/menu_radial.indice en LUNE_TABLA_RADIAL para comprobar la paridad).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  crearSandbox, escritorioFalso, EXTRA, buscar, porId, boton, botones, todoTexto, conClase, interruptor, texto,
} from './jsx_falso.mjs';

const APARIENCIA = path.join(EXTRA, 'apariencia.jsx');
const JUEGO = path.join(EXTRA, 'juego.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
const cargar = (escritorio = null, globales = {}) => crearSandbox({ archivos: [APARIENCIA, JUEGO], escritorio, globales });
const ev = (v) => ({ target: { value: v, checked: v } });

test('paridad de LuneRadial.indice con ui/menu_radial.indice (tabla de Python)', (t) => {
  const ruta = process.env.LUNE_TABLA_RADIAL;
  if (!ruta || !fs.existsSync(ruta)) { t.skip('sin tabla de Python'); return; }
  const tabla = JSON.parse(fs.readFileSync(ruta, 'utf8'));
  assert.ok(tabla.length > 200);
  const { indice } = cargar().sb.LuneRadial;
  const malos = tabla.filter(([dx, dy, n, esp]) => { const r = indice(dx, dy, n); return (r === null ? null : r + 0) !== esp; });
  assert.deepEqual(malos.slice(0, 5), [], `${malos.length} diferencias`);
});

test('registra sus tarjetas y utilidades sin pisar globales', () => {
  const S = cargar();
  assert.deepEqual(plano(S.nuevas.sort()), ['AparienciaCard', 'AtajosCard', 'BandejaCard', 'JuegoCard', 'LuneApariencia',
    'LuneJuego', 'LuneRadial', 'MenuRadialCard', 'RadialHost', 'RadialMenu', 'RendimientoCard']);
});

test('utilidades: limitador ≤ 1 cada 50 ms (la última llega), retardo, combos de «Detectar»', () => {
  const S = cargar();
  const A = S.sb.LuneApariencia;
  const hechas = [];
  const lim = A.crearLimitador((x) => hechas.push([x, S.ahora()]), 50);
  const t0 = S.ahora();
  for (let i = 0; i < 10; i++) { lim(i); S.avanzar(5); }            // 10 llamadas en 50 ms
  S.avanzar(100);
  assert.deepEqual(hechas.map((h) => h[0]), [0, 9]);
  assert.ok(hechas[1][1] - hechas[0][1] >= 50 && hechas[0][1] === t0);
  const ret = [];
  const r = A.crearRetardo((x) => ret.push(x), 400);
  r(1); S.avanzar(300); r(2); S.avanzar(399);
  assert.deepEqual(ret, []);
  S.avanzar(1);
  assert.deepEqual(ret, [2]);
  const c = A.comboDesdeEvento;
  assert.deepEqual(plano(c({ code: 'Escape' })), { cancelar: true });
  assert.equal(c({ code: 'Escape', ctrlKey: true }).completo, true, 'Ctrl+Esc no cancela');
  assert.deepEqual(plano(c({ code: 'ControlLeft', ctrlKey: true, altKey: true })), { completo: false, texto: 'Ctrl+Alt+…' });
  assert.deepEqual(plano(c({ code: 'KeyL', ctrlKey: true, altKey: true, shiftKey: true })),
    { completo: true, combo: 'ctrl+alt+shift+KeyL', texto: 'Ctrl+Alt+Shift+L' });
  assert.equal(c({ code: 'Digit3', metaKey: true, shiftKey: true }).combo, 'shift+win+Digit3');
  assert.equal(c({ code: 'AltRight', ctrlKey: true, altKey: true }).completo, false, 'AltGr solo no es un atajo');
  assert.equal(c({ code: 'F9' }).combo, 'F9');
  assert.deepEqual(plano(A.fxDesdeCfg({ fondo: false, micro: 'x' }, { bg: true, sweep: false, micro: true })), { bg: false, sweep: false, micro: true, quieta: true });
  assert.deepEqual(plano(A.fxDesdeCfg({ pausar_sin_foco: false }, null)), { bg: true, sweep: true, micro: true, quieta: false });
  assert.deepEqual(plano(A.vistaDe('settings#atajos')), { vista: 'settings', seccion: 'atajos' });
  assert.equal(A.vistaDe('javascript:x'), null);
  assert.deepEqual(plano(A.vistaDe('alarmas')), { vista: 'alarmas', seccion: '' });
  assert.equal(A.vistaDe('chat#<b>').seccion, '');
  assert.deepEqual(plano(A.normalizarTema({ preset: 'violeta', hue: 725, saturacion: 9, tenir_pop: 'si' })),
    { preset: 'violeta', hue: 5, saturacion: 2, tenir_pop: false, tenir_fondo: false });
  assert.equal(A.tonoDe({ preset: 'violeta', hue: 0 }, A.PRESETS_DEMO), 0.233);
  assert.equal(A.tonoDe({ preset: 'personalizado', hue: 90 }, A.PRESETS_DEMO), 0.25);
  assert.equal(A.colorTono(0), 'hsl(186 100% 50%)');
  assert.deepEqual(plano(A.mover(['a', 'b', 'c'], 1, -1)), ['b', 'a', 'c']);
  assert.deepEqual(plano(A.mover(['a', 'b'], 0, -1)), ['a', 'b']);
  const J = S.sb.LuneJuego;
  assert.equal(J.normalizarApp('  Juego.EXE '), 'juego.exe');
  for (const malo of ['C:\\Games\\x.exe', '../x.exe', 'a/b.exe', '', 'x'.repeat(81), '*.exe', 5]) assert.equal(J.normalizarApp(malo), null, String(malo));
  assert.deepEqual([J.valorForzado(true), J.valorForzado(false), J.valorForzado(null)], [1, -1, 0]);
  assert.match(J.textoEstado({ activo: true, motivo: 'sin_bordes', exe: 'x.exe', disponible: true }), /sin bordes.*x\.exe/);
});

// ── Sin backend (demo en el navegador) ─────────────────────────────────────────
test('demo sin backend: las seis tarjetas se dibujan y responden en local', () => {
  const S = cargar();
  const h = S.h;
  for (const n of ['AparienciaCard', 'AtajosCard', 'MenuRadialCard', 'BandejaCard', 'JuegoCard', 'RendimientoCard']) {
    const a = S.render(h(S.sb[n]));
    assert.ok(a.length === 1 && a[0].type === 'section' && /^aj-/.test(a[0].props.id), n);
    S.desmontar();
  }
  // Apariencia: preset y tono cambian en la tarjeta y avisa de que la vista previa es de la app
  const ap = h(S.sb.AparienciaCard);
  let a = S.render(ap);
  assert.equal(botones(a, '').filter((b) => /Cian|Magenta|Violeta|Rojo|Ámbar|Verde|Personalizado/.test(texto(b))).length, 7);
  boton(a, 'Magenta mate').props.onClick();
  a = S.render(ap);
  assert.equal(boton(a, 'Magenta mate').props['data-variant'], 'primary');
  assert.match(todoTexto(a), /necesita la app/);
  porId(a, 'f-tema-hue').props.onChange(ev('200'));
  a = S.render(ap);
  assert.equal(boton(a, 'Personalizado').props['data-variant'], 'primary');
  assert.equal(porId(a, 'f-tema-hue').props.value, 200);
  S.desmontar();
  // Atajos: «Detectar» + teclas → la fila cambia en local
  const at = h(S.sb.AtajosCard);
  a = S.render(at);
  const filas = conClase(a, 'ln-c4-fila');
  assert.ok(filas.length >= 5);
  botones(a, 'Detectar')[0].props.onClick();
  a = S.render(at);
  assert.match(texto(conClase(a, 'is-vivo')[0]), /Pulsa la combinación/);
  S.dispatch(S.evento('keydown', { code: 'ShiftLeft', shiftKey: true, ctrlKey: true }));
  a = S.render(at);
  assert.equal(texto(conClase(a, 'is-vivo')[0]), 'Ctrl+Shift+…');
  S.dispatch(S.evento('keydown', { code: 'KeyK', ctrlKey: true, altKey: true, shiftKey: true }));
  a = S.render(at);
  assert.equal(conClase(a, 'is-vivo').length, 0);
  assert.equal(texto(conClase(a, 'ln-c4-kbd')[0]), 'Ctrl+Alt+Shift+K');
  S.desmontar();
  // Juego: forzar y «Añadir app» en demo
  const jg = h(S.sb.JuegoCard);
  a = S.render(jg);
  boton(a, 'Forzar modo juego').props.onClick();
  a = S.render(jg);
  assert.match(todoTexto(a), /EN JUEGO/);
  boton(a, 'Añadir app').props.onClick();
  a = S.render(jg);
  assert.ok(porId(a, 'f-juego-visibles'));
  S.desmontar();
  assert.equal(S.nOyentes('keydown'), 0, 'sin oyentes colgados');
});

// ── Con backend ────────────────────────────────────────────────────────────────
test('AparienciaCard: carga el tema, vista previa limitada, guarda diferido y restablece', () => {
  const tema = { preset: 'violeta', hue: 83.88, saturacion: 1, tenir_pop: false, tenir_fondo: false };
  const E = escritorioFalso({
    tema_estado: () => JSON.stringify({ cfg: tema, vars: null, presets: { cian: 0, violeta: 0.233, ambar: 0.594 } }),
    tema_guardar: (j) => JSON.stringify({ ok: true, error: '', estado: { cfg: JSON.parse(j) } }),
    tema_restablecer: JSON.stringify({ ok: true, estado: { cfg: { preset: 'cian', hue: 0, saturacion: 1 } } }),
  });
  const S = cargar(E.obj);
  const el = S.h(S.sb.AparienciaCard);
  let a = S.render(el);
  assert.equal(E.de('tema_estado').length, 1);
  assert.equal(boton(a, 'Violeta').props['data-variant'], 'primary');
  assert.equal(botones(a, '').filter((b) => /Cian|Violeta|Ámbar|Personalizado/.test(texto(b))).length, 4, 'presets del puente');
  assert.equal(porId(a, 'f-tema-hue').props.value, 84);
  // 5 movimientos del tono en 20 ms: 1 vista previa ya y la última a los 50 ms; guarda UNA vez a los 400 ms
  for (const v of [100, 110, 120, 130, 140]) { porId(S.render(el), 'f-tema-hue').props.onChange(ev(String(v))); S.avanzar(4); }
  assert.equal(E.de('tema_previsualizar').length, 1);
  S.avanzar(50);
  const vistas = E.de('tema_previsualizar').map((l) => JSON.parse(l[0]));
  assert.equal(vistas.length, 2);
  assert.deepEqual([vistas[0].hue, vistas[1].hue, vistas[1].preset], [100, 140, 'personalizado']);
  assert.equal(E.de('tema_guardar').length, 0, 'aún no guarda');
  S.avanzar(400);
  assert.deepEqual(E.de('tema_guardar').map((l) => JSON.parse(l[0]).hue), [140]);
  a = S.render(el);
  assert.match(todoTexto(a), /Tema guardado/);
  // Presets e interruptores guardan al momento
  boton(a, 'Ámbar').props.onClick();
  assert.equal(JSON.parse(E.de('tema_guardar').slice(-1)[0][0]).preset, 'ambar');
  interruptor(S.render(el), 'amarillo').onChange({ target: { checked: true } });
  assert.equal(JSON.parse(E.de('tema_guardar').slice(-1)[0][0]).tenir_pop, true);
  porId(S.render(el), 'f-tema-sat').props.onChange(ev('150'));
  S.avanzar(500);
  assert.equal(JSON.parse(E.de('tema_guardar').slice(-1)[0][0]).saturacion, 1.5);
  // Un cambio de fuera (bandeja) recarga la tarjeta; justo después de tocarla, no
  E.obj.tema_cambio.emit('null');
  assert.equal(E.de('tema_estado').length, 1, 'recién tocada: no pisa lo que mueves');
  S.avanzar(2000);
  E.obj.tema_cambio.emit('null');
  assert.equal(E.de('tema_estado').length, 2);
  boton(S.render(el), 'Restablecer').props.onClick();
  a = S.render(el);
  assert.equal(E.de('tema_restablecer').length, 1);
  assert.equal(boton(a, 'Cian').props['data-variant'], 'primary');
  S.desmontar();
  assert.equal(E.obj.tema_cambio.oyentes, 0, 'desconecta la señal al desmontar');
});

test('AtajosCard: estado, «Detectar» pausa los atajos, valida y guarda; Esc/foco/15 s cancelan', () => {
  const lista = [
    { id: 'mostrar_lune', etiqueta: 'Abrir Lune', combo: 'ctrl+alt+shift+l', texto: 'Ctrl+Alt+Shift+L', disponible: true },
    { id: 'voz', etiqueta: 'Voz', combo: 'ctrl+alt+shift+v', texto: 'Ctrl+Alt+Shift+V', disponible: true, aviso: null },
    { id: 'pantalla_grande', etiqueta: 'Pantalla grande', combo: 'ctrl+alt+shift+b', texto: '', disponible: false },
  ];
  const estado = () => ({ lista, activo: true, pausar_en_juegos: true });
  const E = escritorioFalso({
    atajos_estado: () => JSON.stringify(estado()),
    atajo_validar: (c) => JSON.stringify(/KeyQ/.test(c)
      ? { ok: false, error: 'Ctrl+Alt+Q ya lo usa «Abrir Lune».' }
      : { ok: true, combo: c.toLowerCase().replace('key', ''), texto: 'Ctrl+Alt+Shift+J', aviso: null }),
    atajo_guardar: (id, combo) => { lista[1] = { ...lista[1], combo, texto: combo ? 'Ctrl+Alt+Shift+J' : '' }; return JSON.stringify({ ok: true, error: '', estado: estado() }); },
    atajos_restablecer: () => JSON.stringify({ ok: true, estado: estado() }),
  });
  const S = cargar(E.obj);
  const el = S.h(S.sb.AtajosCard);
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-c4-fila').length, 2, 'lo que no tiene handler no sale');
  assert.match(todoTexto(a), /Abrir Lune/);
  botones(a, 'Detectar')[1].props.onClick();
  S.render(el);
  assert.deepEqual(plano(E.de('atajos_capturando')), [[true]]);
  const k = S.evento('keydown', { code: 'KeyJ', ctrlKey: true, altKey: true, shiftKey: true });
  S.dispatch(k);
  assert.ok(k.prevenido && k.parado, 'la tecla no llega a la página (ni al F1 del radial)');
  assert.deepEqual(plano(E.de('atajos_capturando')), [[true], [false]]);
  assert.deepEqual(plano(E.de('atajo_validar')), [['ctrl+alt+shift+KeyJ']]);
  assert.deepEqual(plano(E.de('atajo_guardar')), [['voz', 'ctrl+alt+shift+j']]);
  a = S.render(el);
  assert.match(todoTexto(a), /Guardado: Ctrl\+Alt\+Shift\+J/);
  // Error de validación: no guarda
  botones(a, 'Detectar')[1].props.onClick();
  S.render(el);
  S.dispatch(S.evento('keydown', { code: 'KeyQ', ctrlKey: true, altKey: true }));
  a = S.render(el);
  assert.equal(E.de('atajo_guardar').length, 1);
  assert.match(todoTexto(a), /ya lo usa «Abrir Lune»/);
  // Esc, perder el foco y 15 s: cancelan y reanudan
  for (const cancelar of ['esc', 'blur', 'tiempo']) {
    botones(S.render(el), 'Detectar')[0].props.onClick();
    S.render(el);
    if (cancelar === 'esc') S.dispatch(S.evento('keydown', { code: 'Escape' }));
    if (cancelar === 'blur') S.dispatch(S.evento('blur'));
    if (cancelar === 'tiempo') S.avanzar(15000);
    a = S.render(el);
    assert.equal(conClase(a, 'is-vivo').length, 0, cancelar);
    assert.deepEqual(plano(E.de('atajos_capturando').slice(-1)), [[false]], cancelar);
  }
  assert.match(todoTexto(a), /Se acabó el tiempo/);
  assert.equal(E.de('atajo_guardar').length, 1);
  // Quitar (✕) = sin atajo; señal atajos_cambio refresca; interruptor y restablecer
  buscar(a, (n) => n.type === 'button' && n.props['aria-label'] === 'Quitar el atajo de Voz')[0].props.onClick();
  assert.deepEqual(plano(E.de('atajo_guardar').slice(-1)), [['voz', '']]);
  lista[0] = { ...lista[0], texto: 'Ctrl+Alt+Shift+X' };
  E.obj.atajos_cambio.emit(JSON.stringify(estado()));
  a = S.render(el);
  assert.match(todoTexto(a), /Ctrl\+Alt\+Shift\+X/);
  interruptor(a, 'Atajos globales activos').onChange({ target: { checked: false } });
  assert.deepEqual(plano(E.de('atajos_activar')), [[false]]);
  boton(S.render(el), 'Restablecer').props.onClick();
  assert.equal(E.de('atajos_restablecer').length, 1);
  // Desmontar a media captura: se reanudan los atajos
  botones(S.render(el), 'Detectar')[0].props.onClick();
  S.render(el);
  S.desmontar();
  assert.deepEqual(plano(E.de('atajos_capturando').slice(-1)), [[false]]);
  assert.equal(S.nOyentes('keydown') + S.nOyentes('blur'), 0);
});

test('MenuRadialCard y BandejaCard: ordenar, quitar, añadir hasta el máximo, sonidos y «Probar»', () => {
  const cat = ['ajustes', 'chat', 'voz', 'dormir', 'fantasma', 'bailar'].map((id) => ({ id, etiqueta: id.toUpperCase(), icono: '' }));
  let principal = ['ajustes', 'chat', 'voz'];
  let acciones = ['voz', 'dormir'];
  const E = escritorioFalso({
    radial_estado: () => JSON.stringify({ principal, secundario: [], defecto: ['ajustes', 'voz'], catalogo: cat, max: 4, sonidos: true, volumen: 0.6 }),
    radial_guardar: (j) => { const o = JSON.parse(j); if (o.principal) principal = o.principal;
      return JSON.stringify({ ok: true, descartados: [], estado: { principal, catalogo: cat, max: 4, defecto: ['ajustes', 'voz'], sonidos: o.sonidos !== false, volumen: o.volumen ?? 0.6 } }); },
    bandeja_estado: () => JSON.stringify({ acciones, defecto: ['voz'], catalogo: cat, max: 20 }),
    bandeja_guardar: (j) => { acciones = JSON.parse(j).acciones; return JSON.stringify({ ok: true, estado: { acciones, defecto: ['voz'], catalogo: cat, max: 20 } }); },
  });
  const S = cargar(E.obj);
  const el = S.h(S.sb.MenuRadialCard);
  let a = S.render(el);
  assert.deepEqual(conClase(a, 'ln-c4-fila').map((f) => texto(conClase([f], 'ln-c4-fila-nombre')[0])), ['AJUSTES', 'CHAT', 'VOZ']);
  assert.equal(buscar(a, (n) => n.type === 'path' && n.props.role === 'menuitem').length, 3, 'vista previa del radial');
  buscar(a, (n) => n.props && n.props['aria-label'] === 'Subir CHAT')[0].props.onClick();
  assert.deepEqual(plano(JSON.parse(E.de('radial_guardar')[0][0])), { principal: ['chat', 'ajustes', 'voz'] });
  a = S.render(el);
  buscar(a, (n) => n.props && n.props['aria-label'] === 'Quitar VOZ')[0].props.onClick();
  a = S.render(el);
  assert.deepEqual(principal, ['chat', 'ajustes']);
  porId(a, 'f-radial-nuevo').props.onChange(ev('bailar'));
  a = S.render(el);
  boton(a, 'Añadir').props.onClick();
  a = S.render(el);
  assert.deepEqual(principal, ['chat', 'ajustes', 'bailar']);
  boton(a, 'Añadir').props.onClick();                               // el primero libre: voz → 4 = máximo
  a = S.render(el);
  assert.equal(principal.length, 4);
  assert.equal(boton(a, 'Máximo 4').props.disabled, true);
  interruptor(a, 'Sonidos del menú').onChange({ target: { checked: false } });
  assert.deepEqual(plano(JSON.parse(E.de('radial_guardar').slice(-1)[0][0])), { sonidos: false });
  a = S.render(el);
  assert.equal(porId(a, 'f-radial-vol').props.disabled, true);
  const abiertos = [];
  S.sb.addEventListener('lune-radial', (e) => abiertos.push(e.detail.tipo));
  boton(a, 'Probar').props.onClick();
  assert.deepEqual(abiertos, ['principal']);
  boton(a, 'Restablecer').props.onClick();
  assert.deepEqual(principal, ['ajustes', 'voz']);
  S.desmontar();
  const eb = S.h(S.sb.BandejaCard);
  a = S.render(eb);
  buscar(a, (n) => n.props && n.props['aria-label'] === 'Quitar VOZ')[0].props.onClick();
  a = S.render(eb);
  assert.deepEqual(plano(JSON.parse(E.de('bandeja_guardar')[0][0])), { acciones: ['dormir'] });
  assert.match(todoTexto(a), /se rehace al abrirlo/);
});

test('JuegoCard: estado en vivo, forzar 1/0/-1, ajustes, apps (sin rutas) y FPS con retardo', () => {
  let cfg = { activo: true, accion: 'ocultar', fps: 0, apps: ['viejo.exe'], rutas_juego: true, incluir_videos: true,
    prioridad_baja: true, recortar_ram: true, silenciar: true, pausar_atajos: true };
  const E = escritorioFalso({
    juego_config: () => JSON.stringify(cfg),
    juego_estado_json: JSON.stringify({ activo: false, motivo: '', forzado: null, exe: '', disponible: true }),
    juego_guardar: (j) => { cfg = { ...cfg, ...JSON.parse(j) }; return JSON.stringify({ ok: true, estado: cfg }); },
    juego_apps_visibles: JSON.stringify(['juego.exe', 'viejo.exe', 'C:\\ruta\\mala.exe', 'otro.exe']),
  });
  const S = cargar(E.obj);
  const el = S.h(S.sb.JuegoCard);
  let a = S.render(el);
  assert.match(todoTexto(a), /no hay ningún juego/);
  E.obj.juego_estado.emit(JSON.stringify({ activo: true, motivo: 'quns3', forzado: null, exe: 'elden.exe' }));
  a = S.render(el);
  assert.match(todoTexto(a), /EN JUEGO/);
  assert.match(todoTexto(a), /pantalla completa exclusiva · elden\.exe/);
  boton(a, 'Forzar modo juego').props.onClick();
  boton(a, 'Forzar «sin juego»').props.onClick();
  boton(a, 'Automático').props.onClick();
  assert.deepEqual(plano(E.de('juego_forzar')), [[1], [-1], [0]]);
  interruptor(a, 'Silenciar la voz').onChange({ target: { checked: false } });
  boton(a, 'Al fondo').props.onClick();
  interruptor(a, 'Pausar los atajos').onChange({ target: { checked: false } });
  assert.deepEqual(plano(E.de('juego_guardar').map((l) => JSON.parse(l[0]))),
    [{ silenciar: false }, { accion: 'fondo' }, { pausar_atajos: false }]);
  a = S.render(el);
  assert.equal(boton(a, 'Al fondo').props['data-variant'], 'primary');
  // FPS: un solo guardado 350 ms después del último movimiento
  for (const v of [10, 20, 30]) porId(S.render(el), 'f-juego-fps').props.onChange(ev(String(v)));
  assert.equal(E.de('juego_guardar').length, 3);
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(E.de('juego_guardar').slice(-1)[0][0])), { fps: 30 });
  // Apps: «Añadir app…» → visibles (sin las que ya están ni rutas) → Añadir
  a = S.render(el);
  boton(a, 'Añadir app').props.onClick();
  a = S.render(el);
  const opciones = buscar(porId(a, 'f-juego-visibles').hijos, (n) => n.type === 'option').map((o) => o.props.value);
  assert.deepEqual(opciones, ['juego.exe', 'otro.exe']);
  porId(a, 'f-juego-visibles').props.onChange(ev('otro.exe'));
  a = S.render(el);
  botones(a, 'Añadir').find((b) => texto(b) === 'Añadir').props.onClick();
  assert.deepEqual(plano(JSON.parse(E.de('juego_guardar').slice(-1)[0][0])), { apps: ['viejo.exe', 'otro.exe'] });
  // Escrito a mano: con ruta, no se manda
  a = S.render(el);
  porId(a, 'f-juego-manual').props.onChange(ev('C:\\Games\\x.exe'));
  a = S.render(el);
  const n = E.de('juego_guardar').length;
  botones(a, 'Añadir').slice(-1)[0].props.onClick();
  a = S.render(el);
  assert.equal(E.de('juego_guardar').length, n);
  assert.match(todoTexto(a), /sin rutas/);
  buscar(a, (x) => x.props && x.props['aria-label'] === 'Quitar viejo.exe')[0].props.onClick();
  assert.deepEqual(plano(JSON.parse(E.de('juego_guardar').slice(-1)[0][0])), { apps: ['otro.exe'] });
  S.desmontar();
  assert.equal(E.obj.juego_estado.oyentes, 0);
});

test('RendimientoCard: carga, guarda al momento (FPS con retardo) y libera memoria', () => {
  const E = escritorioFalso({
    rendimiento: JSON.stringify({ fps_max: 90, siempre_encima: true, recorte_ram_auto: false, en_barra_tareas: true }),
    rendimiento_guardar: (j) => JSON.stringify({ ok: true, estado: { fps_max: 90, siempre_encima: true, recorte_ram_auto: false, en_barra_tareas: true, ...JSON.parse(j) } }),
    liberar_memoria: JSON.stringify({ ok: true, antes: 612.4, despues: 380.1, liberado: 232.3 }),
  });
  const S = cargar(E.obj);
  const el = S.h(S.sb.RendimientoCard);
  let a = S.render(el);
  assert.equal(porId(a, 'f-fps-max').props.value, 90);
  interruptor(a, 'barra de tareas').onChange({ target: { checked: false } });
  interruptor(a, 'Recortar la memoria').onChange({ target: { checked: true } });
  assert.deepEqual(plano(E.de('rendimiento_guardar').map((l) => JSON.parse(l[0]))), [{ en_barra_tareas: false }, { recorte_ram_auto: true }]);
  porId(S.render(el), 'f-fps-max').props.onChange(ev('30'));
  porId(S.render(el), 'f-fps-max').props.onChange(ev('45'));
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(E.de('rendimiento_guardar').slice(-1)[0][0])), { fps_max: 45 });
  boton(S.render(el), 'Liberar memoria').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /Liberados 232\.3 MB \(612\.4 → 380\.1 MB\)/);
});
