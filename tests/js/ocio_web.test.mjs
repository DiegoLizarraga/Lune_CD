/*
 * Web principal de los cortes 5 y 6 en el sandbox de jsx_falso.mjs (sin navegador):
 *   · extra/alarmas.jsx: AlarmasPanel (demo y con window.luneAlarmas falso), AlarmaBanner (bloqueo de
 *     «Apagar» con cuenta atrás), AlarmasCard y PantallaGrandeCard (guardado al momento y diferido, atajo
 *     de luneEscritorio, «Abrir alarmas» → 'lune-vista');
 *   · extra/baile.jsx: BaileCard (estado en vivo, apps permitidas y «suenan ahora») y LuneBaileWeb
 *     (useBaile, reloj del pulso, transform del vídeo, rótulo);
 *   · app.jsx + sidebar.jsx: vista «alarmas», banner global, CommandMenu (accion_menu) y la asistente de la
 *     barra bailando en vídeo (transform ≤ 30 fps) y en VRM (baileProc por h.usarModulo/h.mod).
 * Lo lanza también tests/test_jsx_ocio.py.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  crearSandbox, escritorioFalso, senal, KIT, EXTRA, buscar, porId, boton, botones, todoTexto, conClase, interruptor, texto,
} from './jsx_falso.mjs';

const ALARMAS = path.join(EXTRA, 'alarmas.jsx');
const BAILE = path.join(EXTRA, 'baile.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
const ev = (v) => ({ target: { value: v, checked: v } });
const esperar = () => new Promise((r) => setImmediate(r));

const RANURAS_ALARMAS = ['alarmas_json', 'alarma_guardar', 'alarma_borrar', 'temporizador_crear', 'temporizador_accion',
  'alarma_apagar', 'alarma_posponer', 'alarma_probar', 'config_alarmas', 'config_alarmas_guardar', 'grande_estado_json',
  'grande_alternar', 'salvapantallas_probar', 'config_grande', 'config_grande_guardar'];
const SENALES_ALARMAS = ['alarmas_cambio', 'alarma_sonando', 'alarma_apagada', 'grande_estado'];
const RANURAS_MUSICA = ['estado_json', 'bailar', 'parar', 'config_baile', 'config_baile_guardar', 'apps_audio', 'app_permitir', 'app_quitar'];
const SENALES_MUSICA = ['baile_estado', 'baile_pulso', 'apps_cambio'];

/** Objeto del QWebChannel falso: ranuras que apuntan y responden por callback, y señales. */
function puenteFalso(ranuras, senales, respuestas = {}) {
  const llamadas = [];
  const obj = {};
  for (const s of senales) obj[s] = senal();
  for (const n of ranuras) {
    obj[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push([n, ...args]);
      const r = respuestas[n];
      const v = typeof r === 'function' ? r(...args) : r;
      if (cb) cb(v);
    };
  }
  return {
    obj, llamadas, respuestas,
    de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)),
    limpiar: () => { llamadas.length = 0; },
  };
}

function cargar({ alarmas = null, musica = null, escritorio = null, globales = {} } = {}) {
  return crearSandbox({ archivos: [ALARMAS, BAILE], escritorio, globales: {
    ...(alarmas ? { luneAlarmas: alarmas } : {}), ...(musica ? { luneMusica: musica } : {}), ...globales } });
}

// ── Registro y utilidades puras ──────────────────────────────────────────────
test('se registran solos sin pisar globales', () => {
  const S = cargar();
  assert.deepEqual(plano(S.nuevas.sort()), ['AlarmaBanner', 'AlarmasCard', 'AlarmasPanel', 'BaileCard', 'LuneAlarmas',
    'LuneBaileWeb', 'PantallaGrandeCard']);
});

test('LuneAlarmas: horas, días, duraciones, próxima alarma y textos', () => {
  const A = cargar().sb.LuneAlarmas;
  assert.deepEqual(plano(A.parsearHora('7:05')), { hora: 7, minuto: 5 });
  for (const malo of ['24:00', '7:5', 'x', '', null, '07:60']) assert.equal(A.parsearHora(malo), null, String(malo));
  assert.equal(A.mascara('lmxjv'), 31);
  assert.equal(A.mascara('sd'), 96);
  assert.equal(A.letrasDe(A.mascara('dl')), 'ld');
  assert.equal(A.textoDias(0, false), 'Todos los días');
  assert.equal(A.textoDias(31, false), 'De lunes a viernes');
  assert.equal(A.textoDias(96, false), 'Fines de semana');
  assert.equal(A.textoDias(1 << 5, false), 'Los sábados');
  assert.equal(A.textoDias(A.mascara('lxv'), false), 'L X V');
  assert.equal(A.textoDias(0, true), 'Una vez');
  assert.equal(A.formatoDuracion(65), '01:05');
  assert.equal(A.formatoDuracion(3725), '1:02:05');
  assert.equal(A.formatoDuracion(0.2), '00:01', 'redondea hacia arriba');
  assert.equal(A.restante({ activo: true, objetivo: 1000, restante_s: 5 }, 990), 10);
  assert.equal(A.restante({ activo: false, objetivo: 0, restante_s: 42 }, 990), 42);
  assert.equal(A.restante({ activo: true, objetivo: 1000, restante_s: 5 }, 2000), 0);
  // 2026-09-26 es sábado
  const sab10 = new Date(2026, 8, 26, 10, 0);
  const laborable = { activa: true, hora: 7, minuto: 30, dias: 31 };
  const f = A.proximaVez(laborable, sab10);
  assert.deepEqual([f.getDate(), f.getHours(), f.getMinutes()], [28, 7, 30], 'lunes 28 a las 07:30');
  assert.equal(A.proximaVez({ ...laborable, dias: 0 }, sab10).getDate(), 27, 'todos los días: mañana');
  assert.equal(A.proximaVez({ ...laborable, dias: 0 }, new Date(2026, 8, 26, 6, 0)).getDate(), 26, 'hoy, más tarde');
  assert.equal(A.proximaVez({ ...laborable, activa: false }, sab10), null);
  const p = A.proxima([laborable, { activa: true, hora: 12, minuto: 0, dias: 0 }], sab10);
  assert.equal(p.alarma.hora, 12);
  // Con `proxima` del backend (epoch de su reloj) manda esa, corregida con el desfase de relojes
  const epoch = new Date(2026, 8, 26, 11, 0).getTime() / 1000;
  const q = A.proxima([{ ...laborable, proxima: epoch + 100 }, { activa: true, hora: 12, minuto: 0, dias: 0 }], sab10, 100);
  assert.equal(q.alarma.hora, 7, 'la del backend (una vez con fecha, por ejemplo) gana aunque la hora diga otra cosa');
  assert.equal(q.cuando.getHours(), 11);
  assert.deepEqual(plano(A.normalizarProxima({ id: 't2', tipo: 'temporizador', texto: 'té', cuando: 5 })), { id: 't2', tipo: 'temporizador', texto: 'té', cuando: 5 });
  assert.equal(A.normalizarProxima({ id: 'x y', cuando: 5 }), null);
  assert.equal(A.textoFalta(3 * 60000 + 5000), 'en 3 min');
  assert.equal(A.textoFalta(5 * 3600000 + 20 * 60000), 'en 5 h 20 min');
  assert.equal(A.textoFalta(10000), 'en menos de 1 min');
  assert.equal(A.tituloSonando({ tipo: 'temporizador', atraso_s: 0 }), 'Temporizador');
  assert.equal(A.tituloSonando({ tipo: 'alarma', atraso_s: 420 }), 'Alarma · hace 7 min');
  const e = A.normalizarEstado({ alarmas: [{ id: 'a1', hora: 7, minuto: 0 }, { id: '<x>', hora: 7, minuto: 0 }, { id: 'a2', hora: 25, minuto: 0 }],
    temporizadores: [{ id: 't1', duracion_s: 60, objetivo: 5, activo: false }, { id: 't2', duracion_s: 0 }], sonando: 'x' });
  assert.deepEqual(e.alarmas.map((a) => a.id), ['a1']);
  assert.deepEqual(plano(e.temporizadores), [{ id: 't1', activo: false, duracion_s: 60, objetivo: 0, restante_s: 60, texto: '' }]);
  assert.equal(e.sonando, null);
  assert.equal(A.normalizarConfigGrande({ paso: 99 }).paso, 10);
  assert.equal(A.normalizarConfigGrande(null).pasos[7].etiqueta, '1 h 30 min');
  assert.equal(A.normalizarConfigAlarmas({ volumen: 3, sonido: 'bomba', bloqueo_s: -4 }).volumen, 1);
  assert.equal(A.normalizarConfigAlarmas({ sonido: 'bomba' }).sonido, 'azar');
});

test('LuneBaileWeb: apps, rótulo, opciones de página, reloj del pulso y transform del vídeo', () => {
  const B = cargar().sb.LuneBaileWeb;
  assert.equal(B.normalizarApp('  Spotify.EXE '), 'Spotify');
  for (const malo of ['C:\\x\\spotify.exe', 'a/b', '', '.exe', '***', 5]) assert.equal(B.normalizarApp(malo), null, String(malo));
  assert.deepEqual(plano(B.listaApps(['Spotify', 'spotify.exe', 'vlc', '../x'])), ['Spotify', 'vlc']);
  assert.equal(B.rotulo({ bailando: true, app: 'Spotify', bpm: 123.6 }), '♪ Spotify · 124 BPM');
  assert.equal(B.rotulo({ bailando: true, origen: 'manual' }), '♪ a su aire');
  assert.equal(B.rotulo({ bailando: false, app: 'Spotify' }), '');
  assert.deepEqual(plano(B.opcionesPagina({ cambiar: true, cambiar_s: 20, particulas: false }, { estilo: 'palmas' })),
    { cambiar: true, cambiarS: 20, particulas: false, estilo: 'palmas' });
  assert.deepEqual(plano(B.opcionesPagina(null, { estilo: '<x>' })), { cambiar: false, cambiarS: 15, particulas: true });
  // Reloj: extrapola entre pulsos y cada pulso corrige ≤ 0.2 de fase
  let t = 0;
  const r = B.crearReloj(() => t);
  r.pulso(120, 0, 0.8);
  t = 0.25;
  assert.ok(Math.abs(r.fase() - 0.5) < 1e-9, '120 BPM: medio pulso a los 0.25 s');
  t = 1.0;
  assert.ok(Math.abs(r.fase() - 0) < 1e-9);
  r.pulso(120, 0.5, 0.8);                          // Python dice 0.5 y nosotros íbamos por 0.0
  assert.ok(Math.abs(r.fase() - 0.8) < 1e-9, `corrige solo 0.2 (fase ${r.fase()})`);
  let antes = r.beat();
  for (let i = 1; i <= 10; i++) { t = 1 + i * 0.01; const b = r.beat(); assert.ok(b > antes && b - antes < 0.03, 'continua'); antes = b; }
  for (let i = 0; i < 6; i++) { t += 0.5; r.pulso(120, (0.5 + 1 * (i + 1)) % 1, 0.8); }
  assert.ok(Math.abs(r.fase() - 0.5) < 1e-9, 'converge a la fase de Python');
  assert.equal(r.bpm, 120);
  r.reiniciar();
  assert.equal(r.sincronizado, false);
  // Transform del vídeo: bote 0..−6 px, ±2°, escala ≥ 1.06 (sin bordes a la vista)
  for (let b = 0; b <= 4; b += 0.05) {
    for (const e of [0, 0.5, 1]) {
      const x = B.transformVideo(b, e);
      assert.ok(x.dy <= 1e-9 && x.dy >= -6, `dy ${x.dy}`);
      assert.ok(Math.abs(x.grados) <= 2, `grados ${x.grados}`);
      assert.ok(x.escala >= 1.06 && x.escala <= 1.08, `escala ${x.escala}`);
      assert.match(x.css, /^translateY\(-?[\d.]+px\) rotate\(-?[\d.]+deg\) scale\([\d.]+\)$/);
    }
  }
  assert.ok(Math.abs(B.transformVideo(2, 1).dy) < 1e-9, 'en el golpe, abajo');
  assert.ok(B.transformVideo(0.5, 1).grados > 0 && B.transformVideo(1.5, 1).grados < 0, 'un golpe a cada lado');
});

test('con ui_web/lune_ritmo.js cargado, el reloj del baile es LuneRitmo.crearReloj (sin saltos de fase)', () => {
  const S = crearSandbox({ archivos: [path.join(KIT, '..', '..', 'lune_ritmo.js'), ALARMAS, BAILE] });
  assert.equal(typeof S.sb.LuneRitmo.crearReloj, 'function');
  let t = 10;
  const r = S.sb.LuneBaileWeb.crearReloj(() => t);
  assert.equal(r.ritmo, true);
  assert.equal(r.sincronizado, false);
  r.pulso(120, 0.25, 0.8);
  assert.equal(r.sincronizado, true);
  assert.equal(r.bpm, 120);
  let antes = r.beat(t);
  assert.ok(Math.abs(r.fase(t) - 0.25) < 0.02, `se alinea con la primera medida (${r.fase(t)})`);
  for (let i = 1; i <= 60; i++) {
    t += 1 / 30;
    if (i === 15) r.pulso(120, 0.9, 0.8);                    // medida que discrepa: corrige sin saltar
    const b = r.beat(t);
    assert.ok(b > antes && b - antes < (2 / 30) * 1.25, `continuo y ≤ +20 % de velocidad (${b - antes})`);
    antes = b;
  }
  r.reiniciar();
  assert.equal(r.sincronizado, false);
});

// ── AlarmasPanel ─────────────────────────────────────────────────────────────
test('AlarmasPanel sin backend: demo local de alarmas y temporizadores con cuenta atrás', () => {
  const S = cargar();
  const el = S.h(S.sb.AlarmasPanel);
  let a = S.render(el);
  assert.match(todoTexto(a), /Demo sin la app/);
  assert.match(todoTexto(a), /Sin alarmas/);
  porId(a, 'f-al-hora').props.onChange(ev('06:45'));
  for (const d of ['lunes', 'miércoles', 'viernes']) buscar(S.render(el), (n) => n.props && n.props['aria-label'] === d)[0].props.onClick();
  a = S.render(el);
  assert.equal(buscar(a, (n) => n.props && n.props['aria-label'] === 'lunes')[0].props['aria-pressed'], true);
  assert.match(todoTexto(a), /L X V/);
  porId(a, 'f-al-texto').props.onChange(ev('gimnasio'));
  boton(S.render(el), 'Añadir alarma').props.onClick();
  a = S.render(el);
  const filas = conClase(a, 'ln-al-fila');
  assert.equal(filas.length, 1);
  assert.match(texto(filas[0]), /06:45.*L X V.*gimnasio/);
  assert.equal(porId(a, 'f-al-hora').props.value, '07:30', 'el formulario se vacía');
  // Editar, apagar y borrar
  boton(a, 'Editar').props.onClick();
  a = S.render(el);
  assert.equal(porId(a, 'f-al-hora').props.value, '06:45');
  porId(a, 'f-al-hora').props.onChange(ev('06:50'));
  boton(S.render(el), 'Guardar cambios').props.onClick();
  a = S.render(el);
  assert.match(texto(conClase(a, 'ln-al-fila')[0]), /06:50/);
  interruptor(a, 'Activa').onChange({ target: { checked: false } });
  a = S.render(el);
  assert.equal(conClase(a, 'is-off').length, 1);
  buscar(a, (n) => n.props && n.props['aria-label'] === 'Borrar la alarma de las 06:50')[0].props.onClick();
  a = S.render(el);
  assert.equal(conClase(a, 'ln-al-fila').length, 0);
  // Temporizador de 1:05 que cuenta atrás en la página
  porId(a, 'f-tm-m').props.onChange(ev('1'));
  porId(S.render(el), 'f-tm-s').props.onChange(ev('5'));
  boton(S.render(el), 'Crear e iniciar').props.onClick();
  a = S.render(el);
  const id = conClase(a, 'ln-al-cuenta')[0].props.id;
  assert.equal(texto(porId(a, id)), '01:05');
  S.avanzar(2000);
  a = S.render(el);
  assert.equal(texto(porId(a, id)), '01:03');
  boton(a, 'Parar').props.onClick();
  a = S.render(el);
  S.avanzar(5000);
  a = S.render(el);
  assert.equal(texto(porId(a, id)), '01:03', 'parado no cuenta');
  boton(a, 'Iniciar').props.onClick();
  boton(S.render(el), '5 min').props.onClick();
  a = S.render(el);
  assert.equal(conClase(a, 'ln-al-cuenta').length, 2);
  S.desmontar();
  assert.equal(S.temporizadores(), 0, 'sin intervalos colgados');
});

function backendAlarmas(extra = {}) {
  const ahora = 1700000000 + 100;                 // el reloj del backend va 100 s por delante de la página
  let cfgA = { activo: true, pantalla_grande: true, decir_texto: true, bloqueo_s: 5, recuperar_min: 10, posponer_min: 7,
    volumen: 0.8, sonido: 'azar' };
  let estado = {
    disponible: true, activo: true, ahora,
    alarmas: [{ id: 'a1', activa: true, hora: 7, minuto: 30, dias: 31, una_vez: false, texto: 'gimnasio' }],
    temporizadores: [{ id: 't1', activo: true, duracion_s: 300, objetivo: ahora + 65, restante_s: 300, texto: 'té' }],
    sonando: null,
  };
  const P = puenteFalso(RANURAS_ALARMAS, SENALES_ALARMAS, {
    alarmas_json: () => JSON.stringify(estado),
    alarma_guardar: (j) => {
      const o = JSON.parse(j);
      if (o.hora === '03:00') return JSON.stringify({ ok: false, error: 'Hora rara.', estado });
      return JSON.stringify({ ok: true, error: '', id: 'a2', estado });
    },
    alarma_borrar: () => JSON.stringify({ ok: true, error: '', estado }),
    temporizador_crear: () => JSON.stringify({ ok: true, error: '', id: 't2', estado }),
    temporizador_accion: () => JSON.stringify({ ok: true, error: '', estado }),
    alarma_probar: true, alarma_apagar: true, alarma_posponer: true,
    config_alarmas: () => JSON.stringify(cfgA),
    config_alarmas_guardar: (j) => { cfgA = { ...cfgA, ...JSON.parse(j) }; return JSON.stringify({ ok: true, error: '', estado: cfgA }); },
    ...extra,
  });
  return { P, poner: (e) => { estado = { ...estado, ...e }; }, estado: () => estado };
}

test('AlarmasPanel con backend: payloads exactos, errores, señal alarmas_cambio y reloj del backend', () => {
  const { P, poner } = backendAlarmas();
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmasPanel);
  let a = S.render(el);
  assert.equal(P.de('alarmas_json').length, 1);
  assert.doesNotMatch(todoTexto(a), /Demo/);
  assert.match(todoTexto(a), /Próxima: 07:30 · gimnasio/);
  assert.equal(texto(porId(a, 'tm-t1')), '01:05', 'objetivo − ahora del backend, no del reloj de la página');
  S.avanzar(1000);
  assert.equal(texto(porId(S.render(el), 'tm-t1')), '01:04');
  // Nueva alarma: JSON exacto
  porId(a, 'f-al-hora').props.onChange(ev('08:15'));
  buscar(S.render(el), (n) => n.props && n.props['aria-label'] === 'sábado')[0].props.onClick();
  interruptor(S.render(el), 'Solo una vez').onChange({ target: { checked: true } });
  porId(S.render(el), 'f-al-texto').props.onChange(ev('  pan  '));
  boton(S.render(el), 'Añadir alarma').props.onClick();
  assert.deepEqual(plano(P.de('alarma_guardar').map((l) => JSON.parse(l[0]))), [{ hora: '08:15', dias: 's', una_vez: true, texto: 'pan' }]);
  a = S.render(el);
  assert.match(todoTexto(a), /Alarma para las 08:15/);
  // Error del backend: se ve y el formulario se queda
  porId(a, 'f-al-hora').props.onChange(ev('03:00'));
  boton(S.render(el), 'Añadir alarma').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /Hora rara/);
  assert.equal(porId(a, 'f-al-hora').props.value, '03:00');
  // Editar manda el id; interruptor y papelera
  boton(a, 'Editar').props.onClick();
  boton(S.render(el), 'Guardar cambios').props.onClick();
  assert.equal(JSON.parse(P.de('alarma_guardar').slice(-1)[0][0]).id, 'a1');
  interruptor(S.render(el), 'Activa').onChange({ target: { checked: false } });
  assert.deepEqual(plano(JSON.parse(P.de('alarma_guardar').slice(-1)[0][0])), { id: 'a1', activa: false });
  buscar(S.render(el), (n) => n.props && n.props['aria-label'] === 'Borrar la alarma de las 07:30')[0].props.onClick();
  assert.deepEqual(plano(P.de('alarma_borrar')), [['a1']]);
  // Temporizadores
  boton(S.render(el), 'Parar').props.onClick();
  boton(S.render(el), 'Reiniciar').props.onClick();
  buscar(S.render(el), (n) => n.props && n.props['aria-label'] === 'Borrar el temporizador t1')[0].props.onClick();
  assert.deepEqual(plano(P.de('temporizador_accion')), [['t1', 'parar'], ['t1', 'reiniciar'], ['t1', 'borrar']]);
  boton(S.render(el), '10 min').props.onClick();
  porId(S.render(el), 'f-tm-h').props.onChange(ev('99'));
  a = S.render(el);
  assert.equal(porId(a, 'f-tm-h').props.value, 23, 'se acota');
  boton(a, 'Crear e iniciar').props.onClick();
  assert.deepEqual(plano(P.de('temporizador_crear').map((l) => JSON.parse(l[0]))),
    [{ segundos: 600, texto: '', iniciar: true }, { h: 23, m: 5, s: 0, texto: '', iniciar: true }]);
  // Señal de otro proceso: sin temporizadores en marcha no queda ningún intervalo
  poner({ temporizadores: [], alarmas: [] });
  P.obj.alarmas_cambio.emit(JSON.stringify({ disponible: true, activo: false, ahora: 1700000200, alarmas: [], temporizadores: [] }));
  a = S.render(el);
  assert.match(todoTexto(a), /EN PAUSA/);
  assert.equal(S.temporizadores(), 0);
  interruptor(a, 'Alarmas activas').onChange({ target: { checked: true } });
  assert.deepEqual(plano(P.de('config_alarmas_guardar')), [['{"activo":true}']]);
  boton(S.render(el), 'Probar').props.onClick();
  assert.equal(P.de('alarma_probar').length, 1);
  assert.match(todoTexto(S.render(el)), /Sonando una prueba/);
  S.desmontar();
  assert.equal(P.obj.alarmas_cambio.oyentes, 0, 'desconecta al desmontar');
});

test('AlarmasPanel: el puente llega tarde (lune-ready) y deja la demo', () => {
  const S = cargar();
  const el = S.h(S.sb.AlarmasPanel);
  assert.match(todoTexto(S.render(el)), /Demo/);
  const { P } = backendAlarmas();
  S.sb.luneAlarmas = P.obj;
  S.dispatch(new S.sb.Event('lune-ready'));
  const a = S.render(el);
  assert.doesNotMatch(todoTexto(a), /Demo/);
  assert.equal(conClase(a, 'ln-al-fila').length, 2);
  assert.equal(P.obj.alarmas_cambio.oyentes, 1);
});

// ── AlarmaBanner ─────────────────────────────────────────────────────────────
test('AlarmaBanner: «Apagar» bloqueado con cuenta atrás, posponer con los minutos de la config, apagada lo quita', () => {
  const { P } = backendAlarmas();
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmaBanner);
  assert.deepEqual(S.render(el), [], 'sin nada sonando no se dibuja');
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'gimnasio', tipo: 'alarma', atraso_s: 0, programado: '2026-09-26T07:30',
    apagar_en_ms: 5000, cola: 1 }));
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-alarma-banner').length, 1);
  assert.match(todoTexto(a), /gimnasio/);
  assert.match(todoTexto(a), /07:30/);
  assert.match(todoTexto(a), /\+1 aviso en cola/);
  assert.equal(boton(a, 'Apagar').props.disabled, true);
  assert.equal(texto(boton(a, 'Apagar')), 'Apagar (5)');
  assert.equal(texto(boton(a, 'Posponer')), 'Posponer 7 min');
  S.avanzar(2100);
  a = S.render(el);
  assert.equal(texto(boton(a, 'Apagar')), 'Apagar (3)');
  S.avanzar(3000);
  a = S.render(el);
  assert.equal(boton(a, 'Apagar').props.disabled, false);
  assert.equal(texto(boton(a, 'Apagar')), 'Apagar');
  assert.equal(S.temporizadores(), 0, 'la cuenta atrás se para al acabar el bloqueo');
  boton(a, 'Apagar').props.onClick();
  assert.equal(P.de('alarma_apagar').length, 1);
  assert.deepEqual(S.render(el), []);
  // Posponer y la señal de apagada
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: '', tipo: 'temporizador', apagar_en_ms: 0 }));
  a = S.render(el);
  assert.match(todoTexto(a), /Se acabó el tiempo/);
  boton(a, 'Posponer').props.onClick();
  assert.equal(P.de('alarma_posponer').length, 1);
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'y', tipo: 'alarma', apagar_en_ms: 0, posponer_min: 9 }));
  assert.equal(texto(boton(S.render(el), 'Posponer')), 'Posponer 9 min', 'los minutos que dice el controlador');
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'x', tipo: 'prueba', apagar_en_ms: 0 }));
  a = S.render(el);
  assert.equal(boton(a, 'Posponer'), undefined, 'una prueba no se pospone');
  P.obj.alarma_apagada.emit();
  assert.deepEqual(S.render(el), []);
  S.desmontar();
  assert.equal(P.obj.alarma_sonando.oyentes + P.obj.alarma_apagada.oyentes, 0);
});

test('AlarmaBanner: al recargar la página a media alarma, sale la que ya suena', () => {
  const { P, poner } = backendAlarmas();
  poner({ sonando: { texto: 'pastilla', tipo: 'alarma', apagar_en_ms: 1200, cola: 0 } });
  const S = cargar({ alarmas: P.obj });
  const a = S.render(S.h(S.sb.AlarmaBanner));
  assert.match(todoTexto(a), /pastilla/);
  assert.equal(texto(boton(a, 'Apagar')), 'Apagar (2)');
});

// ── Tarjetas de Ajustes ──────────────────────────────────────────────────────
test('AlarmasCard: carga, interruptores al momento, deslizadores juntos en un guardado, sonido, probar y «Abrir alarmas»', () => {
  const { P } = backendAlarmas();
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmasCard);
  let a = S.render(el);
  assert.equal(a[0].props.id, 'aj-alarmas');
  assert.match(todoTexto(a), /1 alarma · 1 temporizador en marcha · próxima 07:30/);
  assert.equal(porId(a, 'f-al-posponer').props.value, 7);
  interruptor(a, 'Decir el texto').onChange({ target: { checked: false } });
  boton(S.render(el), 'Alarma 2').props.onClick();
  porId(S.render(el), 'f-al-bloqueo').props.onChange(ev('10'));
  porId(S.render(el), 'f-al-volumen').props.onChange(ev('40'));
  assert.deepEqual(plano(P.de('config_alarmas_guardar').map((l) => JSON.parse(l[0]))), [{ decir_texto: false }, { sonido: 'alarma_2' }]);
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(P.de('config_alarmas_guardar').slice(-1)[0][0])), { bloqueo_s: 10, volumen: 0.4 });
  a = S.render(el);
  assert.equal(boton(a, 'Alarma 2').props['data-variant'], 'primary');
  const vistas = [];
  S.sb.addEventListener('lune-vista', (e) => vistas.push(e.detail));
  boton(a, 'Abrir alarmas').props.onClick();
  assert.deepEqual(vistas, ['alarmas']);
  boton(a, 'Probar').props.onClick();
  assert.equal(P.de('alarma_probar').length, 1);
});

test('PantallaGrandeCard: config, espera en 11 pasos, atajo del corte 4, estado en vivo y botones', () => {
  let cfg = { activo: false, paso: 2, clic_sale_de_todo: true, fondo_oscuro: true, reloj: true,
    pasos: [30, 60, 300, 900, 1800, 2700, 3600, 5400, 7200, 9000, 10800].map((s, i) => ({ paso: i, segundos: s, etiqueta: `E${i}` })) };
  const { P } = backendAlarmas({
    config_grande: () => JSON.stringify(cfg),
    config_grande_guardar: (j) => { cfg = { ...cfg, ...JSON.parse(j) }; return JSON.stringify({ ok: true, error: '', estado: cfg }); },
    grande_estado_json: JSON.stringify({ activa: false, motivo: '', disponible: true }),
    grande_alternar: true, salvapantallas_probar: false,
  });
  const lista = [{ id: 'pantalla_grande', texto: 'Ctrl+Alt+Shift+B', combo: 'ctrl+alt+shift+b', disponible: true }];
  const E = escritorioFalso({ atajos_estado: () => JSON.stringify({ lista }) });
  const S = cargar({ alarmas: P.obj, escritorio: E.obj });
  const el = S.h(S.sb.PantallaGrandeCard);
  let a = S.render(el);
  assert.equal(a[0].props.id, 'aj-grande');
  assert.equal(texto(conClase(a, 'ln-al-kbd')[0]), 'Ctrl+Alt+Shift+B');
  assert.match(todoTexto(a), /E2/);
  assert.equal(porId(a, 'f-grande-paso').props.disabled, true, 'sin salvapantallas no se elige la espera');
  interruptor(a, 'Salvapantallas').onChange({ target: { checked: true } });
  a = S.render(el);
  porId(a, 'f-grande-paso').props.onChange(ev('6'));
  porId(S.render(el), 'f-grande-paso').props.onChange(ev('7'));
  S.avanzar(350);
  interruptor(S.render(el), 'Un clic sale').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('config_grande_guardar').map((l) => JSON.parse(l[0]))),
    [{ activo: true }, { paso: 7 }, { clic_sale_de_todo: false }]);
  assert.match(todoTexto(S.render(el)), /E7/);
  // Atajo cambiado desde AtajosCard y estado de la pantalla grande en vivo
  E.obj.atajos_cambio.emit(JSON.stringify({ lista: [{ id: 'pantalla_grande', texto: '', combo: '' }] }));
  a = S.render(el);
  assert.equal(texto(conClase(a, 'ln-al-kbd')[0]), 'sin atajo');
  P.obj.grande_estado.emit(JSON.stringify({ activa: true, motivo: 'alarma', disponible: true }));
  a = S.render(el);
  assert.match(todoTexto(a), /PANTALLA GRANDE/);
  assert.match(todoTexto(a), /por una alarma/);
  boton(a, 'Salir de pantalla grande').props.onClick();
  assert.equal(P.de('grande_alternar').length, 1);
  boton(S.render(el), 'Probar salvapantallas').props.onClick();
  assert.match(todoTexto(S.render(el)), /Ahora no se puede/);
  S.desmontar();
  assert.equal(E.obj.atajos_cambio.oyentes + P.obj.grande_estado.oyentes, 0);
});

test('tarjetas sin backend: demo que responde en local y no suena', () => {
  const S = cargar();
  for (const n of ['AlarmasCard', 'PantallaGrandeCard', 'BaileCard']) {
    const a = S.render(S.h(S.sb[n]));
    assert.ok(a.length === 1 && a[0].type === 'section' && /^aj-/.test(a[0].props.id), n);
    S.desmontar();
  }
  const el = S.h(S.sb.PantallaGrandeCard);
  boton(S.render(el), 'Pantalla grande ahora').props.onClick();
  const a = S.render(el);
  assert.match(todoTexto(a), /Demo: la pantalla grande es de la app/);
  assert.match(todoTexto(a), /PANTALLA GRANDE/);
  S.desmontar();
  const b = S.h(S.sb.BaileCard);
  boton(S.render(b), 'Bailar').props.onClick();
  assert.match(todoTexto(S.render(b)), /Demo: el baile es de la app/);
  assert.match(todoTexto(S.render(b)), /chrome/, 'suenan ahora (demo)');
});

// ── BaileCard y useBaile ─────────────────────────────────────────────────────
function backendMusica() {
  let cfg = { auto: true, umbral: 0.2, apps: ['Spotify', 'vlc'], cambiar: false, cambiar_s: 15, particulas: true };
  const P = puenteFalso(RANURAS_MUSICA, SENALES_MUSICA, {
    estado_json: JSON.stringify({ bailando: false, auto: true, disponible: true }),
    config_baile: () => JSON.stringify(cfg),
    config_baile_guardar: (j) => { cfg = { ...cfg, ...JSON.parse(j) }; return JSON.stringify({ ok: true, error: '', estado: cfg }); },
    apps_audio: JSON.stringify(['Spotify', 'chrome', 'C:\\ruta\\mala.exe']),
    app_permitir: (n) => { cfg = { ...cfg, apps: [...cfg.apps, n] }; return JSON.stringify({ ok: true, error: '', apps: cfg.apps }); },
    app_quitar: (n) => { cfg = { ...cfg, apps: cfg.apps.filter((a) => a !== n) }; return JSON.stringify({ ok: true, error: '', apps: cfg.apps }); },
    bailar: true, parar: true,
  });
  return { P, cfg: () => cfg };
}

test('BaileCard: estado en vivo, Bailar/Parar, ajustes, sensibilidad diferida y apps', () => {
  const { P, cfg } = backendMusica();
  const S = cargar({ musica: P.obj });
  const el = S.h(S.sb.BaileCard);
  let a = S.render(el);
  assert.equal(a[0].props.id, 'aj-baile');
  assert.match(todoTexto(a), /esperando música/);
  boton(a, 'Bailar').props.onClick();
  assert.deepEqual(plano(P.de('bailar')), [[0]]);
  P.obj.baile_estado.emit(JSON.stringify({ bailando: true, origen: 'auto', musica: true, app: 'Spotify', estilo: 'palmas', bpm: 124, energia: 0.7,
    disponible: true }));
  a = S.render(el);
  assert.match(todoTexto(a), /♪ BAILANDO/);
  assert.match(todoTexto(a), /Bailando con la música: Spotify · 124 BPM · Palmas/);
  boton(a, 'Parar').props.onClick();
  assert.equal(P.de('parar').length, 1);
  // Ajustes: interruptores al momento; la sensibilidad, 350 ms después (en 0.02–0.6)
  const configs = [];
  S.sb.addEventListener('lune-baile-config', (e) => configs.push(e.detail));
  interruptor(a, 'Cambiar de baile').onChange({ target: { checked: true } });
  porId(S.render(el), 'f-baile-umbral').props.onChange(ev('10'));
  porId(S.render(el), 'f-baile-umbral').props.onChange(ev('5'));
  porId(S.render(el), 'f-baile-cambiar').props.onChange(ev('30'));
  S.avanzar(350);
  assert.deepEqual(plano(P.de('config_baile_guardar').map((l) => JSON.parse(l[0]))), [{ cambiar: true }, { umbral: 0.05, cambiar_s: 30 }]);
  assert.equal(configs.length, 2, 'avisa a useBaile (barra) de la config nueva');
  assert.equal(cfg().umbral, 0.05);
  // Apps: «suenan ahora» sin rutas, ＋ permite, ✕ quita, a mano sin rutas
  a = S.render(el);
  assert.match(todoTexto(a), /♪ Spotify/, 'la permitida que suena se marca');
  assert.equal(buscar(a, (n) => n.props && /mala/.test(n.props['aria-label'] || '')).length, 0);
  buscar(a, (n) => n.props && n.props['aria-label'] === 'Permitir chrome')[0].props.onClick();
  buscar(S.render(el), (n) => n.props && n.props['aria-label'] === 'Quitar vlc')[0].props.onClick();
  assert.deepEqual(plano(P.de('app_permitir')), [['chrome']]);
  assert.deepEqual(plano(P.de('app_quitar')), [['vlc']]);
  a = S.render(el);
  porId(a, 'f-baile-app').props.onChange(ev('D:\\music\\x.exe'));
  botones(S.render(el), 'Añadir').slice(-1)[0].props.onClick();
  assert.equal(P.de('app_permitir').length, 1, 'con ruta no se manda');
  assert.match(todoTexto(S.render(el)), /sin rutas/);
  porId(S.render(el), 'f-baile-app').props.onChange(ev('MusicBee.exe'));
  botones(S.render(el), 'Añadir').slice(-1)[0].props.onClick();
  assert.deepEqual(plano(P.de('app_permitir').slice(-1)), [['MusicBee']]);
  P.obj.apps_cambio.emit(JSON.stringify(['foobar2000']));
  assert.match(todoTexto(S.render(el)), /foobar2000/);
  S.desmontar();
  assert.equal(P.obj.baile_estado.oyentes + P.obj.apps_cambio.oyentes + P.obj.baile_pulso.oyentes, 0);
});

// ── app.jsx + sidebar.jsx ────────────────────────────────────────────────────
const ARCHIVOS_APP = [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx'), path.join(EXTRA, 'apariencia.jsx'),
  path.join(EXTRA, 'juego.jsx'), ALARMAS, BAILE, path.join(KIT, 'app.jsx')];

function docFalso() {
  const clases = new Set();
  return {
    clases,
    body: { classList: { toggle(c, on) { if (on) clases.add(c); else clases.delete(c); } } },
    getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null,
  };
}
function luneFalso() {
  const base = { asistente_visible(cb) { cb(false); }, proveedores(cb) { cb('{}'); }, proveedor_elegido() {} };
  return new Proxy(base, { get(t, k) { if (!(k in t) && typeof k === 'string') t[k] = senal(); return t[k]; } });
}
/** Elementos del DOM falsos para los ref (el React falso no los pone): <video> y <canvas>. */
function conRefs(S) {
  const nodos = {};
  const crear = S.React.createElement;
  S.React.createElement = (type, props, ...hijos) => {
    if (props && props.ref && typeof type === 'string' && !props.ref.current) {
      const clases = new Set();
      const n = { tipo: type, style: {}, clases, classList: { add: (c) => clases.add(c), remove: (c) => clases.delete(c) },
        play: () => Promise.resolve(), pause() {} };
      props.ref.current = n;
      (nodos[type] = nodos[type] || []).push(n);
    }
    return crear(type, props, ...hijos);
  };
  return nodos;
}
function cargarApp({ alarmas = null, musica = null, escritorio = null, vrm = null } = {}) {
  const props = {};
  const stub = (n) => function (p) { props[n] = p; return null; };
  const S = crearSandbox({
    archivos: ARCHIVOS_APP, lune: luneFalso(), escritorio,
    globales: {
      document: docFalso(), localStorage: { getItem: () => null, setItem() {} },
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), CommandMenu: stub('CommandMenu'), SettingsPanel: stub('SettingsPanel'),
      AprobacionHost: stub('AprobacionHost'), luneTema: () => 1,
      ...(alarmas ? { luneAlarmas: alarmas } : {}), ...(musica ? { luneMusica: musica } : {}),
      ...(vrm ? { LuneVRMBarra: vrm.api, __luneVrmBarra: { render: 'vrm', url: '/vrm/actual.vrm', v: '1' } } : {}),
    },
  });
  const nodos = conRefs(S);
  const app = S.h(S.sb.LuneApp);
  return { S, props, nodos, pintar: () => S.render(app) };
}

test('app: vista «alarmas» por lune-vista, banner global y CommandMenu con alarmas, temporizador, pantalla grande y bailar', () => {
  const { P } = backendAlarmas();
  const M = backendMusica();
  const E = escritorioFalso({ accion_menu: (id) => id !== 'pantalla_grande', juego_estado_json: JSON.stringify({ activo: false }) });
  const A = cargarApp({ alarmas: P.obj, musica: M.P.obj, escritorio: E.obj });
  let a = A.pintar();
  A.S.dispatch(new A.S.sb.CustomEvent('lune-vista', { detail: 'alarmas' }));
  a = A.pintar();
  assert.ok(porId(a, 'al-alarmas') && porId(a, 'al-temporizadores'), 'la vista de alarmas');
  A.S.dispatch(new A.S.sb.CustomEvent('lune-vista', { detail: '<script>' }));
  assert.ok(porId(A.pintar(), 'al-alarmas'), 'lo raro se ignora');
  const items = A.props.CommandMenu.items;
  const item = (l) => items.find((i) => i.label === l);
  for (const l of ['Alarmas', 'Temporizador rápido', 'Pantalla grande', 'Bailar']) assert.ok(item(l), l);
  assert.equal(new Set(items.map((i) => i.label)).size, items.length, 'etiquetas únicas (son la key)');
  assert.equal(item('Bailar').on, false);
  item('Temporizador rápido').onClick();
  item('Pantalla grande').onClick();
  item('Bailar').onClick();
  assert.deepEqual(plano(E.de('accion_menu')), [['temporizador_rapido', '5'], ['pantalla_grande', ''], ['bailar', '']]);
  a = A.pintar();
  assert.match(texto(conClase(a, 'ln-toast')[0]), /no está disponible/, 'sin handler: aviso');
  item('Chat').onClick();
  A.pintar();
  item('Alarmas').onClick();
  assert.ok(porId(A.pintar(), 'al-alarmas'));
  // Banner global
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'gimnasio', apagar_en_ms: 0 }));
  a = A.pintar();
  assert.equal(conClase(a, 'ln-alarma-banner').length, 1);
  // Bailando: rótulo en la barra y «Parar el baile» en el menú
  M.P.obj.baile_estado.emit(JSON.stringify({ bailando: true, app: 'Spotify', bpm: 124, disponible: true }));
  a = A.pintar();
  assert.equal(texto(conClase(a, 'ln-baile-rotulo')[0]), '♪ Spotify · 124 BPM');
  assert.equal(A.props.CommandMenu.items.find((i) => i.label === 'Parar el baile').on, true);
});

test('app sin luneEscritorio: el CommandMenu avisa de que necesita la app', () => {
  const A = cargarApp();
  A.pintar();
  A.props.CommandMenu.items.find((i) => i.label === 'Pantalla grande').onClick();
  assert.match(texto(conClase(A.pintar(), 'ln-toast')[0]), /necesita la app/);
});

test('barra en vídeo: transform al pulso (≤ 30 fps) solo mientras baila y no en modo juego', () => {
  const M = backendMusica();
  const E = escritorioFalso({ juego_estado_json: JSON.stringify({ activo: false }) });
  const A = cargarApp({ musica: M.P.obj, escritorio: E.obj });
  A.pintar();
  const v = A.nodos.video[0];
  assert.ok(v, 'el <video> de la barra');
  A.S.avanzar(200);
  assert.equal(v.style.transform, undefined, 'quieta: nada');
  M.P.obj.baile_estado.emit(JSON.stringify({ bailando: true, app: 'Spotify', bpm: 120, disponible: true }));
  M.P.obj.baile_pulso.emit(JSON.stringify({ bpm: 120, fase: 0.25, energia: 1 }));
  A.pintar();
  assert.ok(v.clases.has('is-bailando'));
  const vistos = new Set();
  let cuadros = 0;
  let previo = v.style.transform;
  for (let i = 0; i < 30; i++) {
    A.S.avanzar(1000 / 30);
    if (v.style.transform !== previo) { cuadros++; previo = v.style.transform; }
    vistos.add(v.style.transform);
  }
  assert.ok(cuadros >= 20 && cuadros <= 31, `~30 cuadros en 1 s (${cuadros})`);
  assert.ok(vistos.size > 10);
  assert.match(v.style.transform, /translateY\(.*\) rotate\(.*\) scale\(.*\)/);
  // Modo juego: se para y deja el vídeo como estaba
  E.obj.juego_estado.emit(JSON.stringify({ activo: true, motivo: 'quns3' }));
  A.pintar();
  assert.equal(v.style.transform, '');
  assert.ok(!v.clases.has('is-bailando'));
  const t = A.S.temporizadores();
  A.S.avanzar(500);
  assert.equal(v.style.transform, '', 'en juego no se repinta');
  E.obj.juego_estado.emit(JSON.stringify({ activo: false }));
  A.pintar();
  A.S.avanzar(100);
  assert.notEqual(v.style.transform, '');
  M.P.obj.baile_estado.emit(JSON.stringify({ bailando: false, disponible: true }));
  A.pintar();
  assert.equal(v.style.transform, '');
  assert.ok(A.S.temporizadores() <= t, 'sin bucle colgado');
});

test('barra en VRM: baileProc por usarModulo, bailar con las opciones, pulsos al módulo y parar', async () => {
  const llamadas = [];
  const handle = {
    setEstado() {}, pausar(on) { llamadas.push(['pausar', on]); },
    usarModulo: (n) => { llamadas.push(['usarModulo', n]); return Promise.resolve(true); },
    mod: (...a) => { llamadas.push(['mod', ...a]); },
  };
  const vrm = { api: { crear: () => handle, destruir: () => true } };
  const M = backendMusica();
  const E = escritorioFalso({ juego_estado_json: JSON.stringify({ activo: false }) });
  const A = cargarApp({ musica: M.P.obj, escritorio: E.obj, vrm });
  let a = A.pintar();
  assert.equal(buscar(a, (n) => n.type === 'canvas').length, 1, 'avatar 3D en la barra');
  assert.equal(llamadas.filter((l) => l[0] === 'usarModulo').length, 0, 'sin baile no se carga el módulo');
  M.P.obj.baile_estado.emit(JSON.stringify({ bailando: true, app: 'Spotify', estilo: 'cadera', bpm: 124, disponible: true }));
  M.P.obj.baile_pulso.emit(JSON.stringify({ bpm: 124, fase: 0.1, energia: 0.9 }));
  A.pintar();
  await esperar();
  const mods = () => llamadas.filter((l) => l[0] === 'mod').map((l) => l.slice(1));
  assert.deepEqual(plano(llamadas.find((l) => l[0] === 'usarModulo')), ['usarModulo', 'baileProc']);
  assert.deepEqual(plano(mods()[0]), ['baileProc', 'bailar', true, { cambiar: false, cambiarS: 15, particulas: true, estilo: 'cadera' }]);
  assert.equal(mods()[1][1], 'pulso', 'la fase actual del reloj nada más empezar');
  M.P.obj.baile_pulso.emit(JSON.stringify({ bpm: 126, fase: 0.5, energia: 0.8 }));
  assert.deepEqual(plano(mods().slice(-1)[0]), ['baileProc', 'pulso', 126, 0.5, 0.8]);
  // Modo juego: el avatar se pausa y deja de bailar; al volver, vuelve a bailar
  E.obj.juego_estado.emit(JSON.stringify({ activo: true }));
  A.pintar();
  assert.deepEqual(plano(mods().slice(-1)[0]), ['baileProc', 'bailar', false]);
  const n = mods().length;
  M.P.obj.baile_pulso.emit(JSON.stringify({ bpm: 126, fase: 0.7, energia: 0.8 }));
  assert.equal(mods().length, n, 'en pausa no se mandan pulsos');
  E.obj.juego_estado.emit(JSON.stringify({ activo: false }));
  A.pintar();
  await esperar();
  assert.deepEqual(plano(mods().slice(-2)[0].slice(0, 3)), ['baileProc', 'bailar', true]);
  M.P.obj.baile_estado.emit(JSON.stringify({ bailando: false, disponible: true }));
  A.pintar();
  assert.deepEqual(plano(mods().slice(-1)[0]), ['baileProc', 'bailar', false]);
  assert.equal(llamadas.filter((l) => l[0] === 'usarModulo').length, 2, 'usarModulo es idempotente en vrm_barra');
});

// ── Revisión 4-5-6 (MO3, MO4, MO13) ──────────────────────────────────────────
test('AlarmaBanner: «Posponer» también bloqueado durante el bloqueo (como la tarjeta nativa)', () => {
  const { P } = backendAlarmas();
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmaBanner);
  S.render(el);                                                   // monta y conecta las señales
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'gimnasio', tipo: 'alarma', apagar_en_ms: 5000 }));
  let a = S.render(el);
  assert.equal(boton(a, 'Posponer').props.disabled, true, 'durante el bloqueo no hace nada: que no lo parezca');
  S.avanzar(5100);
  a = S.render(el);
  assert.equal(boton(a, 'Posponer').props.disabled, false);
});

test('AlarmaBanner: con dos en cola, apagar la primera no oculta el banner de la segunda', () => {
  // Python: alarma_apagar → ControlAviso pasa a la siguiente → alarma_sonando(segunda) LLEGA ANTES que la
  // respuesta (true) de alarma_apagar. Antes el callback hacía setSon(null) y ocultaba la segunda.
  let P;
  ({ P } = backendAlarmas({
    alarma_apagar: () => { P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'segunda', tipo: 'alarma', apagar_en_ms: 0 })); return true; },
    alarma_posponer: () => { P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'tercera', tipo: 'alarma', apagar_en_ms: 0 })); return true; },
  }));
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmaBanner);
  S.render(el);
  P.obj.alarma_sonando.emit(JSON.stringify({ texto: 'primera', tipo: 'alarma', apagar_en_ms: 0, cola: 2 }));
  boton(S.render(el), 'Apagar').props.onClick();
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-alarma-banner').length, 1, 'sigue el banner');
  assert.match(todoTexto(a), /segunda/);
  boton(a, 'Posponer').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /tercera/);
  // La última: la respuesta llega sin otra alarma_sonando → se quita.
  P.respuestas.alarma_apagar = true;
  boton(S.render(el), 'Apagar').props.onClick();
  assert.deepEqual(S.render(el), []);
});

test('alarmas con fecha: «Una vez · 27/09», próxima solo ese día y aviso al editarla con días', () => {
  const A = cargar().sb.LuneAlarmas;
  assert.equal(A.textoDias(0, true, '2026-09-27'), 'Una vez · 27/09');
  assert.equal(A.textoDias(0, true, '<img>'), 'Una vez');
  assert.equal(A.normalizarAlarma({ id: 'a1', hora: 7, minuto: 0, fecha: '2026-09-27' }).fecha, '2026-09-27');
  assert.equal(A.normalizarAlarma({ id: 'a1', hora: 7, minuto: 0, fecha: 'mañana' }).fecha, '');
  const sab10 = new Date(2026, 8, 26, 10, 0);
  const f = A.proximaVez({ activa: true, hora: 7, minuto: 0, dias: 0, fecha: '2026-09-28' }, sab10);
  assert.deepEqual([f.getDate(), f.getHours()], [28, 7], 'el lunes 28, no mañana domingo');
  assert.equal(A.proximaVez({ activa: true, hora: 7, minuto: 0, dias: 0, fecha: '2026-09-26' }, sab10), null, 'ya pasó');

  const { P, poner } = backendAlarmas();
  poner({ alarmas: [{ id: 'a1', activa: true, hora: 7, minuto: 0, dias: 0, una_vez: true, texto: '', fecha: '2026-09-27' }] });
  const S = cargar({ alarmas: P.obj });
  const el = S.h(S.sb.AlarmasPanel);
  let a = S.render(el);
  assert.match(todoTexto(a), /Una vez · 27\/09 · a1/);
  boton(a, 'Editar').props.onClick();
  a = S.render(el);
  assert.match(texto(porId(a, 'al-nota-fecha')), /Solo el 27\/09/);
  buscar(a, (n) => n.props && n.props['aria-label'] === 'lunes')[0].props.onClick();
  a = S.render(el);
  assert.match(texto(porId(a, 'al-nota-fecha')), /deja de ser solo el 27\/09/);
  boton(a, 'Guardar cambios').props.onClick();
  assert.deepEqual(plano(JSON.parse(P.de('alarma_guardar').slice(-1)[0][0])),
    { hora: '07:00', dias: 'l', una_vez: true, texto: '', id: 'a1' }, 'el contrato no cambia: la fecha la quita Python');
});
