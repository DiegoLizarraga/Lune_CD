/*
 * Tarjeta «Actualizaciones» (extra/actualizaciones.jsx, 11.3) en el sandbox de jsx_falso.mjs (sin navegador), con
 * un window.lune falso (las ranuras actualizacion_* y la señal actualizacion de ui/web_bridge.py):
 *   · instalada: versión y modo, «Buscar actualizaciones», las notas, «Instalar y reiniciar» con confirmación,
 *     «Descargar ahora», la barra con «Cancelar», «Omitir esta versión», «Buscar al iniciar» y «Volver a avisarme»;
 *   · resaltada al abrir si el aviso al iniciar encontró una versión nueva;
 *   · desde el código (git): los commits y «Actualizar y reiniciar», que no sale con cambios sin guardar;
 *   · copia sin git: solo el enlace a Releases; sin puente, una demo que no revienta;
 *   · LuneActualizaciones (utilidades puras) y la señal se suelta al desmontar.
 * Lo lanza también tests/test_actualizacion_jsx.py.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, senal, EXTRA, buscar, boton, todoTexto, interruptor } from './jsx_falso.mjs';

const CARD = path.join(EXTRA, 'actualizaciones.jsx');
const RANURAS = ['actualizacion_info', 'actualizacion_buscar', 'actualizacion_descargar', 'actualizacion_cancelar',
  'actualizacion_instalar', 'actualizacion_omitir', 'actualizacion_al_iniciar'];

function puenteFalso(respuestas = {}) {
  const llamadas = [];
  const obj = { actualizacion: senal() };
  for (const n of RANURAS) {
    obj[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push([n, ...args]);
      const r = respuestas[n];
      const v = typeof r === 'function' ? r(...args) : (r === undefined ? true : r);
      if (cb) cb(v);
    };
  }
  return { obj, llamadas, de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)) };
}

const INFO = (extra = {}) => JSON.stringify({
  version: '11.3', modo: 'instalada', al_iniciar: true, ultima_comprobacion: '2026-10-01T07:00:00Z',
  omitir_version: '', pagina: 'https://github.com/DiegoLizarraga/Lune_CD/releases', ocupado: false, descargado: false,
  estado: {}, ...extra,
});
const HAY = (extra = {}) => JSON.stringify({
  fase: 'hay', modo: 'instalada', version: '11.4', notas: 'Me actualizo sola.\n· y gasto menos', bytes: 0, total: 1000,
  pct: 0, mensaje: 'Hay una versión nueva de mí: la 11.4 (tengo la 11.3).', nueva: true, instalable: true, ...extra,
});

function montar(respuestas, opciones = {}) {
  const P = puenteFalso(respuestas);
  const S = crearSandbox({ archivos: [CARD], lune: opciones.sinPuente ? null : P.obj });
  const el = S.h(S.sb.ActualizacionesCard, {});
  return { P, S, el, pintar: () => S.render(el) };
}

test('se registra sola con su tarjeta y sus utilidades', () => {
  const { S } = montar({});
  assert.deepEqual(S.nuevas.sort(), ['ActualizacionesCard', 'LuneActualizaciones']);
  const L = S.sb.LuneActualizaciones;
  assert.equal(L.fmtFecha('2026-10-01T07:05:00Z'), '2026-10-01 07:05 UTC');
  assert.equal(L.fmtFecha('basura'), '');
  assert.equal(L.recortarNotas('x'.repeat(2000)).length, 901);
  const e = L.normalizarEstado({ fase: 'descargando', bytes: 500, total: 1000 });
  assert.equal(e.pct, 50);
  assert.equal(L.normalizarEstado({ fase: 'rara' }).fase, '');
  assert.equal(L.normalizarInfo({ modo: 'raro' }).modo, 'carpeta');
  const b = L.botones('instalada', L.normalizarEstado(JSON.parse(HAY())));
  assert.ok(b.instalar && b.descargar && b.omitir && !b.cancelar && b.conConfirmar);
  const sinSha = L.botones('instalada', L.normalizarEstado(JSON.parse(HAY({ instalable: false }))));
  assert.ok(!sinSha.instalar && sinSha.enlace);
  const git = L.botones('git', L.normalizarEstado({ fase: 'hay', limpio: false }));
  assert.ok(!git.instalar && !git.descargar && !git.omitir);
  assert.ok(!L.botones('carpeta', L.normalizarEstado({ fase: 'hay', nueva: true })).instalar);
});

test('instalada: buscar, ver las notas, confirmar e instalar', () => {
  const { P, S, pintar } = montar({ actualizacion_info: INFO() });
  let a = pintar();
  const t0 = todoTexto(a);
  assert.match(t0, /Soy la versión 11\.3 · instalada/);
  assert.match(t0, /La última vez que miré: 2026-10-01 07:00 UTC/);
  assert.equal(boton(a, 'Instalar y reiniciar'), undefined);
  boton(a, 'Buscar actualizaciones').props.onClick();
  assert.equal(P.de('actualizacion_buscar').length, 1);
  P.obj.actualizacion.emit(JSON.stringify({ fase: 'buscando', mensaje: 'Buscando en GitHub…' }));
  a = pintar();
  assert.ok(boton(a, 'Buscando…').props.disabled);
  P.obj.actualizacion.emit(HAY());
  a = pintar();
  const t = todoTexto(a);
  assert.match(t, /¡Versión nueva!/);
  assert.match(t, /Me actualizo sola\.\n· y gasto menos/);
  assert.equal(buscar(a, (n) => n.type === 'section')[0].props['data-tone'], 'yellow');      // resaltada
  // «Instalar y reiniciar» pide confirmación antes de hacer nada.
  boton(a, 'Instalar y reiniciar').props.onClick();
  a = pintar();
  assert.equal(P.de('actualizacion_instalar').length, 0);
  assert.match(todoTexto(a), /te cierro, se instala sola y me vuelvo a abrir/);
  boton(a, 'Ahora no').props.onClick();
  a = pintar();
  assert.doesNotMatch(todoTexto(a), /te cierro/);
  boton(a, 'Instalar y reiniciar').props.onClick();
  a = pintar();
  boton(a, 'Sí, instalar').props.onClick();
  assert.equal(P.de('actualizacion_instalar').length, 1);
  S.desmontar();
});

test('instalada: descarga con barra, cancelar, omitir y buscar al iniciar', () => {
  const { P, S, pintar } = montar({ actualizacion_info: INFO() });
  pintar();
  P.obj.actualizacion.emit(HAY());
  let a = pintar();
  boton(a, 'Descargar ahora').props.onClick();
  assert.equal(P.de('actualizacion_descargar').length, 1);
  P.obj.actualizacion.emit(HAY({ fase: 'descargando', bytes: 400 * 1048576, total: 1000 * 1048576, pct: 40,
    mensaje: 'Descargando 400 MB de 1000 MB (40 %)…' }));
  a = pintar();
  const barra = buscar(a, (n) => n.type === 'i' && n.props.style && n.props.style.width)[0];
  assert.equal(barra.props.style.width, '40%');
  assert.match(todoTexto(a), /400 MB de 1000 MB/);
  assert.ok(boton(a, 'Buscar actualizaciones').props.disabled);
  boton(a, 'Cancelar').props.onClick();
  assert.equal(P.de('actualizacion_cancelar').length, 1);
  P.obj.actualizacion.emit(HAY());
  a = pintar();
  boton(a, 'Omitir esta versión').props.onClick();
  assert.deepEqual(P.de('actualizacion_omitir'), [['11.4']]);
  interruptor(a, 'Buscar al iniciar').onChange({ target: { checked: false } });
  assert.deepEqual(P.de('actualizacion_al_iniciar'), [[false]]);
  a = pintar();
  assert.equal(interruptor(a, 'Buscar al iniciar').checked, false);
  S.desmontar();
});

test('resaltada al abrir si el aviso al iniciar la encontró, y «Volver a avisarme»', () => {
  const { P, pintar } = montar({ actualizacion_info: INFO({ estado: JSON.parse(HAY()), omitir_version: '11.2' }) });
  const a = pintar();
  assert.match(todoTexto(a), /¡Versión nueva!/);
  assert.match(todoTexto(a), /Me pediste saltarte la 11\.2/);
  const enlace = buscar(a, (n) => n.type === 'a' && /Volver a avisarme/.test(n.hijos.join('')))[0];
  enlace.props.onClick({ preventDefault() {} });
  assert.deepEqual(P.de('actualizacion_omitir'), [['']]);
});

test('desde el código: commits y «Actualizar y reiniciar» solo con el árbol limpio', () => {
  const { P, S, pintar } = montar({ actualizacion_info: INFO({ modo: 'git' }) });
  let a = pintar();
  assert.match(todoTexto(a), /desde el código \(git\)/);
  P.obj.actualizacion.emit(JSON.stringify({ fase: 'hay', modo: 'git', commits: ['abc uno', 'def dos'], limpio: false,
    modificados: ['main.py'], mensaje: 'Hay 2 cambio(s) nuevo(s) esperando.' }));
  a = pintar();
  assert.match(todoTexto(a), /· abc uno/);
  assert.match(todoTexto(a), /sin guardar/);
  assert.equal(boton(a, 'Actualizar y reiniciar'), undefined);
  P.obj.actualizacion.emit(JSON.stringify({ fase: 'hay', modo: 'git', commits: ['abc uno'], limpio: true,
    mensaje: 'Hay 1 cambio(s) nuevo(s) esperando.' }));
  a = pintar();
  boton(a, 'Actualizar y reiniciar').props.onClick();
  a = pintar();
  assert.match(todoTexto(a), /git/);
  boton(a, 'Sí, actualizar').props.onClick();
  assert.equal(P.de('actualizacion_instalar').length, 1);
  assert.equal(boton(a, 'Omitir esta versión'), undefined);
  S.desmontar();
});

test('copia sin git: el enlace a Releases y nada que instalar', () => {
  const { P, pintar } = montar({ actualizacion_info: INFO({ modo: 'carpeta' }) });
  pintar();
  P.obj.actualizacion.emit(HAY({ instalable: false, modo: 'carpeta' }));
  const a = pintar();
  const enlace = buscar(a, (n) => n.type === 'a' && /Releases/.test(n.hijos.join('')))[0];
  assert.equal(enlace.props.href, 'https://github.com/DiegoLizarraga/Lune_CD/releases');
  assert.equal(enlace.props.target, '_blank');
  assert.equal(boton(a, 'Instalar y reiniciar'), undefined);
  assert.equal(boton(a, 'Descargar ahora'), undefined);
});

test('sin puente: demo sin reventar', () => {
  const { pintar } = montar({}, { sinPuente: true });
  let a = pintar();
  assert.match(todoTexto(a), /Demo/);
  boton(a, 'Buscar actualizaciones').props.onClick();
  a = pintar();
  assert.match(todoTexto(a), /necesitan la app/);
});

test('la señal se suelta al desmontar y lo de un botón ocupado se avisa', () => {
  const { P, S, pintar } = montar({ actualizacion_info: INFO(), actualizacion_buscar: false });
  let a = pintar();
  assert.equal(P.obj.actualizacion.oyentes, 1);
  boton(a, 'Buscar actualizaciones').props.onClick();
  a = pintar();
  assert.match(todoTexto(a), /Ya estoy en ello/);
  S.desmontar();
  assert.equal(P.obj.actualizacion.oyentes, 0);
});
