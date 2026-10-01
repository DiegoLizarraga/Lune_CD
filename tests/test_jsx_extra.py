"""
Comprueba los componentes JSX «extra» de Ajustes (ui_web/ui_kits/lune-desktop/extra/*.jsx).

La interfaz web los carga con <script type="text/babel">: Babel standalone los
transpila en el navegador con los presets `react` y `env`. Aquí se hace lo mismo
con el Babel vendorizado (ui_web/vendor/babel.min.js) desde Node:

1. Todos los extra/*.jsx transpilan igual que en la página, siguen siendo scripts
   clásicos (sin import/require) y se registran solos con Object.assign(window, …).
2. voz.jsx e ia_avanzada.jsx se ejecutan en un sandbox de `vm` con un React falso
   (hooks mínimos, sin DOM): registran sus componentes, no pisan globales de los
   otros .jsx, sus utilidades puras dan lo esperado y los componentes se dibujan y
   llaman al puente (window.lune) con el formato acordado, con y sin backend.

Sin Node, los tests que lo necesitan se saltan. Sin red ni pantalla.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_EXTRA = RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "extra"
BABEL = RAIZ / "ui_web" / "vendor" / "babel.min.js"

# Arnés de Node. Modo «transpilar»: solo Babel. Modo «probar»: Babel + sandbox.
# Imprime en la última línea un JSON {checks, fallos, archivos}.
ARNES_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [modo, rutaBabel, ...archivos] = process.argv.slice(2);

function cargarBabel(ruta) {
  const src = fs.readFileSync(ruta, 'utf8');
  const m = { exports: {} };
  new Function('module', 'exports', 'self', 'window', src)(m, m.exports, {}, {});
  if (!m.exports || typeof m.exports.transform !== 'function') throw new Error('no pude cargar Babel standalone');
  return m.exports;
}
const Babel = cargarBabel(rutaBabel);
// Lo mismo que usa Babel standalone con <script type="text/babel"> (sin data-presets).
const OPCIONES = {
  presets: ['react', 'env'],
  plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'],
};
const transpilar = (ruta) => Babel.transform(fs.readFileSync(ruta, 'utf8'),
  { ...OPCIONES, filename: path.basename(ruta) }).code;

const fallos = [];
let checks = 0;
function check(nombre, cond, detalle) {
  checks++;
  if (!cond) fallos.push(nombre + (detalle === undefined ? '' : ' -> ' + JSON.stringify(detalle)));
}
function fin(extra) {
  console.log(JSON.stringify({ checks, fallos, ...(extra || {}) }));
  process.exit(fallos.length ? 1 : 0);
}

// ── Modo transpilar ───────────────────────────────────────────────────────────
if (modo === 'transpilar') {
  const res = {};
  for (const ruta of archivos) {
    const nombre = path.basename(ruta);
    try {
      const code = transpilar(ruta);
      res[nombre] = code.length;
      check(`${nombre}: produce código`, code.length > 200);
      check(`${nombre}: script clásico (sin require/exports)`, !/\brequire\(|\bexports\./.test(code));
      check(`${nombre}: se registra en window`, /Object\.assign\(\s*window\s*,/.test(code));
    } catch (e) {
      check(`${nombre}: transpila`, false, String(e && e.message || e).slice(0, 400));
    }
  }
  fin({ archivos: res });
}

// ── Modo probar: React falso con hooks mínimos ────────────────────────────────
const Fragment = Symbol('Fragment');
let actual = null, sucio = false, efectos = [];
let estados = new Map();            // tipo de componente → [slots por instancia]
let contador = new Map();
const cambiaron = (a, b) => !a || !b || a.length !== b.length || a.some((x, i) => !Object.is(x, b[i]));
function slot() { if (!actual) throw new Error('hook fuera de un componente'); return [actual.slots, actual.i++]; }
const React = {
  Fragment,
  createElement(type, props, ...children) {
    const p = { ...(props || {}) };
    if (children.length) p.children = children.length === 1 ? children[0] : children;
    return { type, props: p };
  },
  useState(init) {
    const [s, i] = slot();
    if (!(i in s)) s[i] = typeof init === 'function' ? init() : init;
    return [s[i], (v) => {
      const nv = typeof v === 'function' ? v(s[i]) : v;
      if (!Object.is(nv, s[i])) { s[i] = nv; sucio = true; }
    }];
  },
  useRef(v) { const [s, i] = slot(); if (!(i in s)) s[i] = { current: v }; return s[i]; },
  useMemo(fn, deps) {
    const [s, i] = slot();
    if (!(i in s) || cambiaron(s[i].deps, deps)) s[i] = { deps, v: fn() };
    return s[i].v;
  },
  useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
  useEffect(fn, deps) {
    const [s, i] = slot();
    if (!(i in s) || cambiaron(s[i].deps, deps)) { s[i] = { deps }; efectos.push(fn); }
  },
};
const h = React.createElement;

function llamar(tipo, props) {
  const n = contador.get(tipo) || 0;
  contador.set(tipo, n + 1);
  if (!estados.has(tipo)) estados.set(tipo, []);
  const inst = estados.get(tipo);
  if (!inst[n]) inst[n] = [];
  const previo = actual;
  actual = { slots: inst[n], i: 0 };
  try { return tipo(props || {}); } finally { actual = previo; }
}
function expandir(el) {
  if (el == null || el === false || el === true) return [];
  if (typeof el === 'string' || typeof el === 'number') return [String(el)];
  if (Array.isArray(el)) return el.flatMap(expandir);
  if (typeof el.type === 'function') return expandir(llamar(el.type, el.props));
  if (el.type === Fragment) return expandir(el.props.children);
  return [{ type: el.type, props: el.props, hijos: expandir(el.props.children) }];
}
/** Dibuja, corre los efectos y repite mientras cambie el estado (como React). */
function renderizar(el, conservar) {
  if (!conservar) estados = new Map();
  let arbol = [];
  for (let pase = 0; pase < 10; pase++) {
    sucio = false; contador = new Map(); efectos = [];
    arbol = expandir(el);
    const ef = efectos; efectos = [];
    ef.forEach((f) => f());
    if (!sucio) break;
  }
  return arbol;
}
const texto = (n) => (typeof n === 'string' ? n : n.hijos.map(texto).join(''));
function buscar(nodos, pred, out = []) {
  for (const n of nodos) {
    if (typeof n === 'string') continue;
    if (pred(n)) out.push(n);
    buscar(n.hijos, pred, out);
  }
  return out;
}
const porId = (arbol, id) => buscar(arbol, (n) => n.props && n.props.id === id)[0];
const boton = (arbol, t) => buscar(arbol, (n) => n.type === 'button' && texto(n).includes(t))[0];
const todoTexto = (arbol) => arbol.map(texto).join(' ');

// Componentes del kit (window.LUNE) falsos pero con la misma firma.
const LUNE = {
  Card: ({ children, eyebrow, title, tone }) => h('section', { 'data-tone': tone },
    eyebrow ? h('p', null, eyebrow) : null, title ? h('h3', null, title) : null, children),
  Button: ({ children, variant, size, ...r }) => h('button', { ...r, 'data-variant': variant }, children),
  Input: ({ label, hint, textarea, error, ...r }) => h('div', { 'data-error': !!error },
    label ? h('label', null, label) : null, h(textarea ? 'textarea' : 'input', r), hint ? h('span', null, hint) : null),
  Switch: ({ label, ...r }) => h('label', null, h('input', { type: 'checkbox', ...r }), label),
  Badge: ({ children, variant }) => h('span', { 'data-badge': variant }, children),
};

const codigos = archivos.map((ruta) => [path.basename(ruta), transpilar(ruta)]);

function sandbox(lune) {
  let ahora = 1700000000000;
  const RealDate = Date;
  class FalsaFecha extends RealDate { static now() { return ahora; } }
  let intervalos = [], esperas = [];
  const oyentes = {};
  const sb = {
    React, URL, console, Date: FalsaFecha,
    setInterval: (f) => { intervalos.push(f); return intervalos.length; },
    clearInterval: () => {},
    setTimeout: (f) => { esperas.push(f); return esperas.length; },
    clearTimeout: () => {},
    addEventListener: (t, f) => { (oyentes[t] = oyentes[t] || []).push(f); },
    removeEventListener: (t, f) => { oyentes[t] = (oyentes[t] || []).filter((g) => g !== f); },
    dispatchEvent: (e) => { (oyentes[e.type] || []).slice().forEach((f) => f(e)); return true; },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    LUNE,
    CFG_DEMO: 'de settings.jsx', MOONS: 'de settings.jsx', PanelShell: 'de panels.jsx',
  };
  sb.window = sb;
  if (lune) sb.lune = lune;
  vm.createContext(sb);
  const antes = new Set(Object.keys(sb));
  for (const [nombre, code] of codigos) vm.runInContext(code, sb, { filename: nombre });
  // Babel (preset env) pone sus helpers (_objectSpread, ownKeys…) al nivel superior del archivo:
  // son idénticos en todos los .jsx, así que da igual que se repitan.
  const HELPERS_BABEL = new Set(['ownKeys']);
  const nuevas = Object.keys(sb).filter((k) => !antes.has(k) && !k.startsWith('_') && !HELPERS_BABEL.has(k));
  return {
    sb, nuevas, oyentes,
    avanzar(ms) {
      ahora += ms;
      const es = esperas; esperas = [];
      es.forEach((f) => f());
      intervalos.slice().forEach((f) => f());
    },
  };
}

const registro = [];
const rec = (k) => (e) => registro.push([k, (e && e.target) ? e.target.value : e]);
const hubo = (k, v) => registro.some(([a, b]) => a === k && (v === undefined || JSON.stringify(b) === JSON.stringify(v)));

// ── A. Carga y utilidades puras ───────────────────────────────────────────────
const A = sandbox(null);
const W = A.sb;
const ESPERADOS = ['VozCard', 'PackSonidosCard', 'LuneVoz', 'CompatCard', 'AvanzadoCard', 'AprobacionModal', 'AprobacionHost', 'LuneIA'];
for (const n of ESPERADOS) check(`registra window.${n}`, W[n] && (typeof W[n] === 'function' || typeof W[n] === 'object'));
check('solo registra sus nombres (más helpers de Babel)', A.nuevas.every((k) => ESPERADOS.includes(k)), A.nuevas);
check('no pisa CFG_DEMO/MOONS/PanelShell de otros .jsx',
  W.CFG_DEMO === 'de settings.jsx' && W.MOONS === 'de settings.jsx' && W.PanelShell === 'de panels.jsx');
check('Date falso activo en el sandbox', vm.runInContext('Date.now()', W) === 1700000000000);

const V = W.LuneVoz;
check('numeroDe +10% → 10', V.numeroDe('+10%') === 10);
check('numeroDe -5Hz → -5', V.numeroDe('-5Hz') === -5);
check('numeroDe recorta a ±50', V.numeroDe('+80%') === 50 && V.numeroDe('-99Hz') === -50);
check('numeroDe basura → 0', V.numeroDe('abc') === 0 && V.numeroDe(null) === 0);
check('aRate/aPitch con signo', V.aRate(-7) === '-7%' && V.aRate(0) === '+0%' && V.aPitch(12) === '+12Hz');
const resp0 = V.normalizarVoces(null);
check('respaldo: 45 es + 12 multilingües', resp0.edge.length === 57 && resp0.respaldo === true, resp0.edge.length);
check('respaldo: 45 en español', resp0.edge.filter((v) => v.id.startsWith('es-') && !v.multi).length === 45);
check('respaldo: 12 multilingües', resp0.edge.filter((v) => v.multi).length === 12);
check('respaldo: todas con F/M', resp0.edge.every((v) => v.genero === 'F' || v.genero === 'M'));
check('respaldo: Dalia de México es F', (() => {
  const d = resp0.edge.find((v) => v.id === 'es-MX-DaliaNeural'); return d && d.genero === 'F' && d.pais === 'México' && d.nombre === 'Dalia';
})());
const grupos0 = V.agruparVoces(resp0.edge);
check('grupos: 22 países + multilingües', grupos0.length === 23, grupos0.map((g) => g.grupo));
check('grupos: México primero', grupos0[0].grupo === 'México');
check('grupos: multilingües al final', /Multiling/.test(grupos0[grupos0.length - 1].grupo));
check('grupos: F antes que M', grupos0[0].voces.map((v) => v.genero).join('') === 'FM');
const crudo = V.normalizarVoces(JSON.stringify([
  { ShortName: 'es-ES-AlvaroNeural', Gender: 'Male', Locale: 'es-ES' },
  { ShortName: 'en-US-AvaMultilingualNeural', Gender: 'Female', Locale: 'en-US' },
  '<img src=x onerror=alert(1)>', 'es-MX-DaliaNeural', 'es-MX-DaliaNeural',
]));
check('formato de edge_tts.list_voices', crudo.edge.length === 3 && crudo.respaldo === false, crudo.edge.map((v) => v.id));
check('formato crudo: Alvaro M de España', crudo.edge[0].genero === 'M' && crudo.edge[0].pais === 'España');
check('formato crudo: Ava multilingüe', crudo.edge[1].multi === true && crudo.edge[1].nombre === 'Ava');
check('descarta ids inválidos y duplicados', !crudo.edge.some((v) => /[<>]/.test(v.id)));
check('gTTS por defecto: com.mx, es, us', resp0.gtts.map((p) => p[0]).join(',') === 'com.mx,es,us');
check('Kokoro por defecto: no disponible con instrucciones', resp0.kokoro.disponible === false && /kokoro-onnx/.test(resp0.kokoro.mensaje) && !/pip install/.test(resp0.kokoro.mensaje));
const packs0 = V.normalizarPacks(null);
check('packs: siempre «default»', packs0.length === 1 && packs0[0].id === 'default');
const packs1 = V.normalizarPacks('{"packs":[{"id":"gatos","nombre":"Gatos","autor":"D","eventos":["a","b"]},"default","gatos"]}');
check('packs: default primero si no viene, sin duplicados', packs1.map((p) => p.id).join(',') === 'gatos,default', packs1.map((p) => p.id));
check('packs: cuenta eventos', packs1[0].eventos === 2 && packs1[0].autor === 'D');
// Formato de nucleo.packs_sonido.PackSonido.a_dict(): eventos = {evento: nº de archivos}
const packs2 = V.normalizarPacks(JSON.stringify([{ id: 'default', nombre: 'Lune', descripcion: 'Los de siempre', eventos: { arrastre_inicio: 2, caricia: 1, beber: 3 }, valido: true }]));
check('packs: formato a_dict (eventos como dict)', packs2.length === 1 && packs2[0].eventos === 3 && packs2[0].descripcion === 'Los de siempre', packs2);

// Formato de servicios.voces.catalogo()
const cat = V.normalizarVoces(JSON.stringify({
  edge: [{ id: 'es-MX-DaliaNeural', locale: 'es-MX', genero: 'F', pais: 'México', nombre: 'Dalia', multilingue: false }],
  multilingues: [{ id: 'en-US-AvaMultilingualNeural', locale: 'en-US', genero: 'F', pais: 'Estados Unidos', nombre: 'Ava', multilingue: true }],
  gtts_tld: { 'com.mx': 'México', es: 'España', us: 'Estados Unidos', com: 'Genérico (google.com)' },
  kokoro: { disponible: false, voces: {}, mensaje: 'Instala kokoro-onnx' },
  motores: ['auto', 'edge', 'gtts', 'kokoro'],
  actual: { motor: 'edge', id: 'es-AR-TomasNeural', rate: '+10%', pitch: '+0Hz', volumen: '+0%', tld: 'com.mx' },
  personaje: 'Lune', personaje_voz: { id: 'es-AR-TomasNeural', rate: 10 },
}));
check('catalogo: voces y multilingües', cat.edge.length === 2 && cat.edge[1].multi === true && cat.respaldo === false);
check('catalogo: acentos de gtts_tld (dict)', cat.gtts.map((p) => p[0]).join(',') === 'com.mx,es,us,com');
check('catalogo: mensaje de Kokoro del backend', cat.kokoro.disponible === false && cat.kokoro.mensaje === 'Instala kokoro-onnx');
check('catalogo: voz actual y motor activo', cat.actual.id === 'es-AR-TomasNeural' && cat.motor_activo === 'edge', cat.actual);
check('catalogo: voz propia del personaje (rate numérico → "+10%")', cat.personaje === 'Lune' && cat.personaje_voz.id === 'es-AR-TomasNeural' && cat.personaje_voz.rate === '+10%', cat.personaje_voz);
check('describirParams', V.describirParams({ id: 'es-MX-DaliaNeural', rate: '+10%', pitch: '-5Hz' }, resp0.edge) === 'Dalia (México) · +10% · -5Hz'
  && V.describirParams({ motor: 'gtts', id: '', tld: 'es' }, resp0.edge) === 'gtts · acento es', V.describirParams({ id: 'es-MX-DaliaNeural', rate: '+10%', pitch: '-5Hz' }, resp0.edge));
const pp = V.paramsPrueba({ motor_salida: 'edge', edge_voz: 'es-AR-ElenaNeural', edge_rate: '+80%', edge_pitch: '-3Hz', gtts_tld: 'es' }, '  hola  ');
check('paramsPrueba: formato de voces.params_desde', JSON.stringify(pp) === JSON.stringify({ motor: 'edge', id: 'es-AR-ElenaNeural', rate: '+50%', pitch: '-3Hz', tld: 'es', texto: 'hola' }), pp);
check('paramsPrueba: gTTS sin id, Kokoro con su voz', V.paramsPrueba({ motor_salida: 'gtts' }).id === '' && V.paramsPrueba({ motor_salida: 'kokoro', kokoro_voz: 'em_alex' }).id === 'em_alex'
  && V.paramsPrueba({ motor_salida: 'raro' }).motor === 'auto');
const gk = V.agruparKokoro([['af_bella', 'Bella'], ['ef_dora', 'Dora'], ['bm_george', 'George'], ['em_alex', 'Alex'], ['zf_xiaobei', 'Xiaobei']]);
check('agruparKokoro: español primero, luego inglés y otros', gk.map((g) => g.grupo).join('|') === 'Español|Inglés (EE. UU.)|Inglés (Reino Unido)|Otros idiomas'
  && gk[0].voces.length === 2, gk.map((g) => g.grupo));

const I = W.LuneIA;
check('presetDe({}) = equilibrado', I.presetDe({}) === 'equilibrado');
check('presetDe(preciso)', I.presetDe({ ...I.PRESETS.preciso }) === 'preciso');
check('presetDe(creativo) con strings', I.presetDe({ temperatura: '1' }) === 'creativo');
check('presetDe: creativo con top_k fijo = personalizado', I.presetDe({ temperatura: 1, top_k: 40 }) === 'personalizado');
check('presetDe: top_k 0 = del modelo', I.presetDe({ temperatura: 0.7, top_k: 0 }) === 'equilibrado');
check('presetDe(otro) = personalizado', I.presetDe({ temperatura: 0.33 }) === 'personalizado');
check('presetDe: preset guardado sin valores explícitos', I.presetDe({ preset_muestreo: 'preciso' }) === 'preciso'
  && I.valoresMuestreo({ preset_muestreo: 'preciso' }).top_k === 40);
check('valoresMuestreo: lo explícito manda sobre el preset', I.valoresMuestreo({ preset_muestreo: 'preciso', temperatura: 0.5 }).temperatura === 0.5);
check('valoresMuestreo: equilibrado deja el resto del modelo (null)', (() => {
  const v = I.valoresMuestreo({}); return v.temperatura === 0.7 && v.top_p === null && v.top_k === null && v.min_p === null && v.repeat_penalty === null;
})());
check('preset Preciso = 0.2/0.9/40/0.05/1.1', JSON.stringify(I.PRESETS.preciso) === JSON.stringify({ temperatura: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1 }));
check('Equilibrado y Creativo solo fijan la temperatura (como datos.PRESETS_MUESTREO)',
  JSON.stringify(I.PRESETS.equilibrado) === '{"temperatura":0.7}' && JSON.stringify(I.PRESETS.creativo) === '{"temperatura":1}');
check('temperaturas 0.2 · 0.7 · 1.0', I.PRESETS.preciso.temperatura === 0.2 && I.PRESETS.equilibrado.temperatura === 0.7 && I.PRESETS.creativo.temperatura === 1);
check('valoresPreset(creativo) borra el resto', JSON.stringify(I.valoresPreset('creativo')) === JSON.stringify({ temperatura: 1, top_p: null, top_k: null, min_p: null, repeat_penalty: null }));
check('opcional: rangos de datos._PARAMS_MUESTREO', I.opcional(5, 'temperatura') === 2 && I.opcional('0', 'top_p') === 0.01 && I.opcional(-3, 'top_k') === null
  && I.opcional(40.6, 'top_k') === 41 && I.opcional('', 'min_p') === null && I.opcional(true, 'min_p') === null && I.opcional(9, 'repeat_penalty') === 2);
check('contextos 2K..32K', I.CONTEXTOS[0] === 2048 && I.CONTEXTOS[I.CONTEXTOS.length - 1] === 32768);
check('indiceContexto', I.indiceContexto(8192) === 2 && I.indiceContexto(30000) === 4 && I.indiceContexto(undefined) === 2 && I.indiceContexto(1000) === 0);
check('esLocal: localhost y red privada', I.esLocal('http://localhost:1234/v1') && I.esLocal('http://192.168.1.5:1234/v1') && I.esLocal('http://10.0.0.2/v1') && I.esLocal('http://172.16.4.1/v1') && I.esLocal('http://[::1]:1234/v1'));
check('esLocal: internet no', !I.esLocal('https://api.groq.com/openai/v1') && !I.esLocal('http://172.32.0.1/v1') && !I.esLocal('basura'));
check('urlValida', I.urlValida('https://api.openai.com/v1') && !I.urlValida('ftp://x/v1') && !I.urlValida('http://u:p@host/v1') && !I.urlValida('') && !I.urlValida('hola'));
check('avisoUrl: clave por http fuera de la red', /sin cifrar/.test(I.avisoUrl('http://api.ejemplo.com/v1', 'sk-1')));
check('avisoUrl: http local sin aviso', I.avisoUrl('http://localhost:1234/v1', '') === '');
check('avisoUrl: https bien', I.avisoUrl('https://api.openai.com/v1', 'k') === '');
check('avisoUrl: solo la base', /base/.test(I.avisoUrl('https://api.openai.com/v1/chat/completions', 'k')));
const pend = I.normalizarPendiente('{"id":7,"herramienta":"abrir_url","args":{"url":"https://x.y"},"riesgo":"escritura"}');
check('normalizarPendiente', pend && pend.id === '7' && pend.herramienta === 'abrir_url' && pend.timeout_s === 60 && pend.riesgo === 'ESCRITURA', pend);
check('normalizarPendiente sin id / no JSON → null', I.normalizarPendiente('{}') === null && I.normalizarPendiente('no json') === null && I.normalizarPendiente(null) === null
  && I.normalizarPendiente('[1]') === null);
check('normalizarPendiente recorta el timeout', I.normalizarPendiente({ id: 1, timeout_s: 9999 }).timeout_s === 600 && I.normalizarPendiente({ id: 1, timeout_s: 1 }).timeout_s === 5);
// Formato de lune_core/acciones.Ejecutor._pedir (timeout, motivo, origen, descripcion)
const pend2 = I.normalizarPendiente({ id: 'ab12', herramienta: 'minecraft_orden', args: { orden: 'ven' }, resumen: 'Mandar «ven» al bot',
  descripcion: 'Da una orden al bot', riesgo: 'ESCRITURA', motivo: 'Controla el bot', origen: 'usuario', timeout: 45, pregunta: '¿Lo hago?' });
check('normalizarPendiente: formato del Ejecutor', pend2.timeout_s === 45 && pend2.motivo === 'Controla el bot' && pend2.origen === 'usuario' && pend2.descripcion === 'Da una orden al bot', pend2);
check('normalizarPendiente: expira en segundos → ms', I.normalizarPendiente({ id: 1, expira: 1700000000 }).expira === 1700000000000);
// Texto del modelo: sin bidi, ancho cero ni control (se construyen con fromCharCode: el fuente no lleva invisibles)
const ch = (...cps) => String.fromCodePoint(...cps);
const trampa = 'https://banco.com' + ch(0x202E) + 'moc.live' + ch(0x200B) + ch(0x07) + ch(0xE0041) + '/x';
check('limpiar quita bidi, ancho cero, control y etiquetas', I.limpiar(trampa, 300) === 'https://banco.commoc.live/x', I.limpiar(trampa, 300));
check('limpiar: saltos visibles y recorte con «…»', I.limpiar('a\nb' + ch(0x2028) + 'c\td', 300) === 'a ⏎ b ⏎ c d' && I.limpiar('x'.repeat(50), 10) === 'x'.repeat(9) + '…');
check('limpiar no parte emojis', I.limpiar(ch(0x1F319).repeat(5), 3) === ch(0x1F319).repeat(2) + '…');
const pendT = I.normalizarPendiente({ id: 'z', herramienta: 'abrir' + ch(0x202E) + 'url', resumen: 'Abrir' + ch(0x200F) + ' x' });
check('normalizarPendiente limpia herramienta y resumen', pendT.herramienta === 'abrirurl' && pendT.resumen === 'Abrir x', pendT);
check('formatearArgs: clave: valor por línea', I.formatearArgs({ url: 'https://x.y', n: 3, o: { a: 1 } }) === 'url: https://x.y\nn: 3\no: {"a":1}', I.formatearArgs({ url: 'https://x.y', n: 3, o: { a: 1 } }));
check('formatearArgs: vacío y recortes', I.formatearArgs({}) === '' && I.formatearArgs(null) === '' && I.formatearArgs({ x: 'y'.repeat(5000) }).length <= 700
  && I.formatearArgs(Object.fromEntries(Array.from({ length: 20 }, (_, i) => ['k' + i, i]))).endsWith('… (8 más)'));
check('formatearArgs limpia los valores', I.formatearArgs({ ruta: 'C:/a' + ch(0x202E) + 'b' }) === 'ruta: C:/ab');
check('varianteRiesgo', I.varianteRiesgo('SISTEMA') === 'danger' && I.varianteRiesgo('escritura') === 'yellow' && I.varianteRiesgo('LECTURA') === 'cyan' && I.varianteRiesgo('') === 'ink');
const pr = I.normalizarPrueba('{"ok":true,"modelos":[{"id":"a"},"b",""],"ms":12.4}');
check('normalizarPrueba', pr.ok === true && pr.modelos.join(',') === 'a,b' && pr.ms === 12, pr);
check('normalizarPrueba tolera bool y texto', I.normalizarPrueba(false).ok === false && I.normalizarPrueba('Timeout').mensaje === 'Timeout');

// ── B. Dibujo sin backend (demo en el navegador) ──────────────────────────────
let arbol = renderizar(h(W.VozCard, { cfg: { edge_voz: 'es-MX-DaliaNeural' }, set: rec }));
const og = buscar(arbol, (n) => n.type === 'optgroup');
check('VozCard demo: optgroup por país', og.length === 23 && og[0].props.label === 'México', og.map((n) => n.props.label));
const selVoz = porId(arbol, 'f-edge-voz');
check('VozCard demo: 57 voces en el selector', selVoz && buscar(selVoz.hijos, (n) => n.type === 'option').length === 57);
check('VozCard demo: marca F/M', /Dalia · F/.test(todoTexto(arbol)) && /Jorge · M/.test(todoTexto(arbol)));
check('VozCard demo: Kokoro en gris', boton(arbol, 'Kokoro') && boton(arbol, 'Kokoro').props.disabled === true);
check('VozCard demo: explica Kokoro', /no está instalado/.test(todoTexto(arbol)));
check('VozCard demo: acento gTTS en automático', !!porId(arbol, 'f-gtts-tld'));
boton(arbol, 'Edge (en línea)').props.onClick();
check('VozCard: elegir motor', hubo('motor_salida', 'edge'));
porId(arbol, 'f-edge-rate').props.onChange({ target: { value: '-12' } });
porId(arbol, 'f-edge-pitch').props.onChange({ target: { value: '7' } });
check('VozCard: velocidad como "-12%"', hubo('edge_rate', '-12%'));
check('VozCard: tono como "+7Hz"', hubo('edge_pitch', '+7Hz'));
check('VozCard: rango −50..+50', porId(arbol, 'f-edge-rate').props.min === -50 && porId(arbol, 'f-edge-rate').props.max === 50);
selVoz.props.onChange({ target: { value: 'es-AR-TomasNeural' } });
check('VozCard: elegir voz', hubo('edge_voz', 'es-AR-TomasNeural'));
boton(arbol, 'Probar').props.onClick();                     // sin backend: no lanza
arbol = renderizar(h(W.VozCard, { cfg: { motor_salida: 'gtts', gtts_tld: 'es' }, set: rec }));
check('VozCard gTTS: sin voces de edge', !porId(arbol, 'f-edge-voz') && porId(arbol, 'f-gtts-tld').props.value === 'es');
arbol = renderizar(h(W.VozCard, { cfg: { edge_voz: 'xx-YY-RaraNeural' }, set: rec }));
check('VozCard: conserva una voz desconocida', /xx-YY-RaraNeural \(actual\)/.test(todoTexto(arbol)));
arbol = renderizar(h(W.VozCard, {}));                        // suelta, sin cfg ni set
check('VozCard suelta: se dibuja', !!porId(arbol, 'f-edge-voz'));

arbol = renderizar(h(W.PackSonidosCard, { cfg: {}, set: rec }));
check('PackSonidosCard demo: pack por defecto', porId(arbol, 'f-pack-sfx').props.value === 'default');
check('PackSonidosCard demo: volumen 70 %', porId(arbol, 'f-vol-sfx').props.value === 70);
porId(arbol, 'f-vol-sfx').props.onChange({ target: { value: '40' } });
check('PackSonidosCard: volumen_sfx 0–1', hubo('volumen_sfx', 0.4));

arbol = renderizar(h(W.CompatCard, { cfg: {}, set: rec }));
check('CompatCard demo: atajos de servicios', /LM Studio/.test(todoTexto(arbol)) && /Groq/.test(todoTexto(arbol)) && /Mistral/.test(todoTexto(arbol)));
check('CompatCard demo: sin URL no se prueba', boton(arbol, 'Probar conexión').props.disabled === true);
boton(arbol, 'Groq').props.onClick();
check('CompatCard: atajo rellena la URL', hubo('compat_url', 'https://api.groq.com/openai/v1'));
arbol = renderizar(h(W.CompatCard, { cfg: { compat_url: 'http://api.ejemplo.com/v1', compat_key: 'sk-x' }, set: rec }));
check('CompatCard: avisa de clave sin cifrar', /sin cifrar/.test(todoTexto(arbol)));
check('CompatCard: clave como password', buscar(arbol, (n) => n.type === 'input' && n.props.type === 'password').length === 1);
arbol = renderizar(h(W.CompatCard, { cfg: { compat_url: 'ftp://x' }, set: rec }));
check('CompatCard: URL inválida marcada', buscar(arbol, (n) => n.props && n.props['data-error'] === true).length === 1);

// Clave guardada: get_config trae una máscara fija; lo que se teclee la sustituye entera.
check('textoInsertado: al final, al principio, en medio, pegado y borrando',
  I.textoInsertado('••••••••', '••••••••sk-1') === 'sk-1' && I.textoInsertado('••••••••', 'k••••••••') === 'k'
  && I.textoInsertado('••••••••', '••••x••••') === 'x' && I.textoInsertado('••••••••', 'sk-pegada') === 'sk-pegada'
  && I.textoInsertado('••••••••', '•••••••') === '' && I.textoInsertado('', 'abc') === 'abc');
const MASCARA = '••••••••';
registro.length = 0;
arbol = renderizar(h(W.CompatCard, { cfg: { compat_url: 'https://api.groq.com/openai/v1', compat_key: MASCARA }, set: rec }));
let campoClave = porId(arbol, 'f-compat-key');
check('CompatCard: la máscara se ve como contraseña y avisa de que hay una guardada',
  campoClave && campoClave.props.type === 'password' && campoClave.props.value === MASCARA && /Clave guardada/.test(todoTexto(arbol)));
campoClave.props.onChange({ target: { value: MASCARA + 'g' } });
check('CompatCard: teclear sobre la máscara la sustituye (no se pega)', hubo('compat_key', 'g') && !hubo('compat_key', MASCARA + 'g'), registro);
registro.length = 0;
arbol = renderizar(h(W.CompatCard, { cfg: { compat_url: 'https://api.groq.com/openai/v1', compat_key: MASCARA }, set: rec }));
porId(arbol, 'f-compat-key').props.onChange({ target: { value: MASCARA.slice(1) } });
check('CompatCard: borrar sobre la máscara la deja vacía', hubo('compat_key', ''), registro);
// Lo que escribe el usuario ya no es «guardada»: se edita normal
const cfgClave = { compat_url: 'https://api.groq.com/openai/v1', compat_key: 'sk' };
const elClave = h(W.CompatCard, { cfg: cfgClave, set: (k) => (e) => { cfgClave[k] = (e && e.target) ? e.target.value : e; } });
renderizar(elClave);
porId(renderizar(elClave, true), 'f-compat-key').props.onChange({ target: { value: 'skX' } });   // sustituye: 'X'
check('CompatCard: primera tecla sobre una clave de fuera = sustituir', cfgClave.compat_key === 'X', cfgClave);
porId(renderizar(elClave, true), 'f-compat-key').props.onChange({ target: { value: 'XY' } });
check('CompatCard: después se escribe normal', cfgClave.compat_key === 'XY', cfgClave);

registro.length = 0;
arbol = renderizar(h(W.AvanzadoCard, { cfg: {}, set: rec }));
check('AvanzadoCard: Equilibrado por defecto', boton(arbol, 'Equilibrado').props['data-variant'] === 'primary');
boton(arbol, 'Preciso').props.onClick();
check('AvanzadoCard: preset Preciso', hubo('temperatura', 0.2) && hubo('top_k', 40) && hubo('min_p', 0.05) && hubo('repeat_penalty', 1.1) && hubo('preset_muestreo', 'preciso'));
registro.length = 0;
boton(arbol, 'Creativo').props.onClick();
check('AvanzadoCard: Creativo = temperatura 1 y el resto del modelo (null)', hubo('temperatura', 1) && hubo('top_p', null) && hubo('top_k', null)
  && hubo('min_p', null) && hubo('repeat_penalty', null) && hubo('preset_muestreo', 'creativo'), registro);
porId(arbol, 'f-temp').props.onChange({ target: { value: '1.3' } });
check('AvanzadoCard: mover un deslizador = personalizado', hubo('temperatura', 1.3) && hubo('preset_muestreo', 'personalizado'));
for (const id of ['f-temp', 'f-top-p', 'f-top-k', 'f-min-p', 'f-repeat', 'f-num-predict', 'f-ctx']) check(`AvanzadoCard: deslizador ${id}`, !!porId(arbol, id));
porId(arbol, 'f-ctx').props.onChange({ target: { value: '4' } });
check('AvanzadoCard: contexto 32K', hubo('ollama_num_ctx', 32768));
const valores = buscar(arbol, (n) => n.props && n.props.className === 'ln-x-range-val').map(texto);
check('AvanzadoCard: 8K por defecto', porId(arbol, 'f-ctx').props.value === 2 && valores.includes('8K'), valores);
check('AvanzadoCard: valores visibles', valores.includes('0.70') && valores.includes('automático'), valores);
check('AvanzadoCard: sin fijar = «del modelo» en la posición de Ollama', valores.filter((t) => t === 'del modelo').length === 4
  && porId(arbol, 'f-top-k').props.value === 40 && porId(arbol, 'f-top-p').props.value === 0.9, valores);
registro.length = 0;
porId(arbol, 'f-top-k').props.onChange({ target: { value: '60' } });
check('AvanzadoCard: fijar top_k', hubo('top_k', 60) && hubo('temperatura', 0.7) && hubo('top_p', null) && hubo('preset_muestreo', 'personalizado'), registro);
porId(arbol, 'f-num-predict').props.onChange({ target: { value: '512' } });
check('AvanzadoCard: máximo de tokens', hubo('num_predict', 512));
const semilla = buscar(arbol, (n) => n.type === 'input' && n.props.placeholder === 'aleatoria')[0];
check('AvanzadoCard: semilla con id propio', semilla && semilla.props.id === 'f-seed');
semilla.props.onChange({ target: { value: '42' } });
semilla.props.onChange({ target: { value: '' } });
check('AvanzadoCard: semilla fija y aleatoria (−1)', hubo('seed', 42) && hubo('seed', -1));
boton(arbol, 'Liberar memoria').props.onClick();            // sin backend: no lanza

// Preset guardado sin valores explícitos: al tocar uno se materializan los demás (no se pierden)
registro.length = 0;
arbol = renderizar(h(W.AvanzadoCard, { cfg: { preset_muestreo: 'preciso' }, set: rec }));
check('AvanzadoCard: reconoce el preset guardado', boton(arbol, 'Preciso').props['data-variant'] === 'primary');
porId(arbol, 'f-temp').props.onChange({ target: { value: '0.5' } });
check('AvanzadoCard: al personalizar conserva los del preset', hubo('temperatura', 0.5) && hubo('top_p', 0.9) && hubo('top_k', 40)
  && hubo('min_p', 0.05) && hubo('repeat_penalty', 1.1) && hubo('preset_muestreo', 'personalizado'), registro);
registro.length = 0;
arbol = renderizar(h(W.AvanzadoCard, { cfg: { temperatura: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1, preset_muestreo: 'preciso' }, set: rec }));
const vaciar = boton(arbol, '↺ del modelo');
check('AvanzadoCard: botón para volver a «del modelo»', !!vaciar && buscar(arbol, (n) => n.type === 'button' && texto(n).includes('↺ del modelo')).length === 4);
if (vaciar) { vaciar.props.onClick(); check('AvanzadoCard: ↺ deja el valor en null', hubo('top_p', null) && hubo('preset_muestreo', 'personalizado'), registro); }
registro.length = 0;
arbol = renderizar(h(W.AvanzadoCard, { cfg: { temperatura: 1.0, top_k: 40, preset_muestreo: 'personalizado' }, set: rec }));
buscar(arbol, (n) => n.type === 'button' && texto(n).includes('↺ del modelo'))[0].props.onClick();
check('AvanzadoCard: quitar lo que sobra vuelve al preset (Creativo)', hubo('top_k', null) && hubo('preset_muestreo', 'creativo'), registro);
arbol = renderizar(h(W.AvanzadoCard, { cfg: { num_ctx: 12000 }, set: rec }));
check('AvanzadoCard: contexto fuera de la lista (num_ctx)', /\(ahora 12K\)/.test(todoTexto(arbol)) && porId(arbol, 'f-ctx').props.value === 2, todoTexto(arbol).slice(0, 200));

let resueltos = [];
const onResolver = (id, ok) => resueltos.push([id, ok]);
arbol = renderizar(h(W.AprobacionModal, { onResolver, pendiente: JSON.stringify({
  id: 'a1', herramienta: 'lanzar_app', resumen: 'Abrir el Bloc de notas', args: { app: 'notepad' }, riesgo: 'sistema' }) }));
const txt = todoTexto(arbol);
check('AprobacionModal: herramienta, resumen y args', /lanzar_app/.test(txt) && /Abrir el Bloc de notas/.test(txt) && /app: notepad/.test(txt), txt.slice(0, 300));
check('AprobacionModal: riesgo con su color', buscar(arbol, (n) => n.props && n.props['data-badge'] === 'danger').length >= 1);
check('AprobacionModal: cuenta atrás de 60 s', /60 s/.test(txt));
check('AprobacionModal: «Sí, hazlo» empieza desarmado', boton(arbol, 'Sí, hazlo').props.disabled === true);
check('AprobacionModal: foco en «No»', boton(arbol, 'No').props.autoFocus === true);
check('AprobacionModal: es alertdialog', buscar(arbol, (n) => n.props && n.props.role === 'alertdialog').length === 1);
boton(arbol, 'No').props.onClick();
boton(arbol, 'No').props.onClick();                          // un segundo clic no resuelve dos veces
check('AprobacionModal demo: No → onResolver(id, false) una vez', JSON.stringify(resueltos) === JSON.stringify([['a1', false]]), resueltos);
check('AprobacionModal: sin id no dibuja nada', renderizar(h(W.AprobacionModal, { pendiente: '{}' })).length === 0);

// ── C. Con backend falso (window.lune) ────────────────────────────────────────
function luneFalso(llamadas, conexiones, extra) {
  return {
    voces_disponibles(cb) {
      llamadas.push(['voces']);
      cb(JSON.stringify({
        edge: [{ id: 'es-MX-DaliaNeural', genero: 'F' }, { ShortName: 'es-ES-AlvaroNeural', Gender: 'Male', Locale: 'es-ES' }],
        multilingues: ['en-US-AvaMultilingualNeural'],
        gtts: [{ tld: 'com.mx', nombre: 'México' }],
        kokoro: { disponible: true, voces: { ef_dora: 'Dora (femenina)', em_alex: 'Alex (masculina)', af_bella: 'Bella (femenina, EE. UU.)' } },
        motor_activo: 'edge-tts',
        actual: { motor: 'edge', id: 'es-ES-AlvaroNeural', rate: '-10%', pitch: '+0Hz', tld: 'com.mx' },
        personaje: 'Lune', personaje_voz: { id: 'es-ES-AlvaroNeural', rate: '-10%' },
      }));
    },
    probar_voz(j, cb) { llamadas.push(['probar_voz', JSON.parse(j)]); cb(true); },
    packs_sonido(cb) { cb(JSON.stringify([{ id: 'default', nombre: 'Lune' }, { id: 'gatos', nombre: 'Gatos', autor: 'D', eventos: ['a', 'b', 'c'] }])); },
    compat_probar(cb) { llamadas.push(['compat_probar']); cb(JSON.stringify({ ok: true, modelos: ['m1', { id: 'm2' }], ms: 88.6 })); },
    ia_liberar_vram(cb) { llamadas.push(['liberar']); cb(); },
    resolver_aprobacion(id, ok) { llamadas.push(['resolver', id, ok]); },
    aprobacion_pedida: { connect(f) { conexiones.pedida = f; }, disconnect() { conexiones.pedida = null; } },
    aprobacion_resuelta: { connect(f) { conexiones.resuelta = f; }, disconnect() {} },
    ...(extra || {}),
  };
}
let llamadas = [], conexiones = {};
const C = sandbox(luneFalso(llamadas, conexiones));
const WC = C.sb;
const hay = (pred) => llamadas.some(pred);

const elVoz = h(WC.VozCard, { cfg: { edge_voz: 'es-MX-DaliaNeural', edge_rate: '+10%', edge_pitch: '-5Hz', gtts_tld: 'com.mx' }, set: rec });
arbol = renderizar(elVoz);
check('VozCard: pide la lista al puente', hay((l) => l[0] === 'voces'));
const og2 = buscar(arbol, (n) => n.type === 'optgroup').map((n) => n.props.label);
check('VozCard: grupos de la lista del puente', og2.length === 3 && og2[0] === 'México' && og2[1] === 'España' && /Multiling/.test(og2[2]), og2);
check('VozCard: Kokoro instalado = activo', boton(arbol, 'Kokoro').props.disabled === false);
check('VozCard: muestra el motor activo', /ahora: edge-tts/.test(todoTexto(arbol)));
check('VozCard: velocidad y tono leídos', porId(arbol, 'f-edge-rate').props.value === 10 && porId(arbol, 'f-edge-pitch').props.value === -5);
boton(arbol, 'Probar').props.onClick();
const pv = (llamadas.find((l) => l[0] === 'probar_voz') || [])[1] || {};
check('VozCard: probar_voz con el formato de voces.params_desde', pv.motor === 'auto' && pv.id === 'es-MX-DaliaNeural'
  && pv.rate === '+10%' && pv.pitch === '-5Hz' && pv.tld === 'com.mx' && typeof pv.texto === 'string' && pv.texto.length > 0
  && Object.keys(pv).sort().join(',') === 'id,motor,pitch,rate,texto,tld', pv);
check('VozCard: enseña la voz que suena ahora', /Suena ahora \(guardado\): Alvaro \(España\) · -10%/.test(todoTexto(arbol)), todoTexto(arbol).slice(0, 600));
check('VozCard: avisa de la voz propia del personaje', /«Lune» tiene voz propia/.test(todoTexto(arbol)) && /manda sobre lo que elijas aquí/.test(todoTexto(arbol)));
const frase = porId(arbol, 'f-voz-prueba');
check('VozCard: frase de prueba con id propio', !!frase);
if (frase) {
  frase.props.onChange({ target: { value: '   ' } });
  arbol = renderizar(elVoz, true);
  llamadas.length = 0;
  boton(arbol, 'Probar').props.onClick();
  const pv2 = (llamadas.find((l) => l[0] === 'probar_voz') || [])[1] || {};
  check('VozCard: frase vacía → una por defecto', pv2.texto === 'Hola, soy Lune.', pv2);
}
arbol = renderizar(h(WC.VozCard, { cfg: { motor_salida: 'kokoro', kokoro_voz: 'em_alex' }, set: rec }));
check('VozCard Kokoro: elegir voz de Kokoro', porId(arbol, 'f-kokoro-voz') && porId(arbol, 'f-kokoro-voz').props.value === 'em_alex' && !porId(arbol, 'f-edge-voz'));
const ogK = buscar(porId(arbol, 'f-kokoro-voz').hijos, (n) => n.type === 'optgroup').map((n) => n.props.label);
check('VozCard Kokoro: voces agrupadas por idioma', ogK.join('|') === 'Español|Inglés (EE. UU.)', ogK);
boton(arbol, 'Probar').props.onClick();
const pvK = (llamadas.filter((l) => l[0] === 'probar_voz').pop() || [])[1] || {};
check('VozCard Kokoro: prueba con la voz de Kokoro', pvK.motor === 'kokoro' && pvK.id === 'em_alex', pvK);

arbol = renderizar(h(WC.PackSonidosCard, { cfg: { pack_sonidos: 'gatos', volumen_sfx: 0.25 }, set: rec }));
check('PackSonidosCard: packs del puente', buscar(porId(arbol, 'f-pack-sfx').hijos, (n) => n.type === 'option').length === 2);
check('PackSonidosCard: eventos del pack', /3 eventos/.test(todoTexto(arbol)));
check('PackSonidosCard: volumen leído', porId(arbol, 'f-vol-sfx').props.value === 25);

const elCompat = h(WC.CompatCard, { cfg: { compat_url: 'http://localhost:1234/v1', compat_model: 'm1' }, set: rec });
arbol = renderizar(elCompat);
check('CompatCard local: clave opcional', /no la necesitan/.test(todoTexto(arbol)));
boton(arbol, 'Probar conexión').props.onClick();
check('CompatCard: llama a compat_probar', hay((l) => l[0] === 'compat_probar'));
check('CompatCard: sin compat_borrador en el puente no lo llama y avisa de que prueba lo guardado',
  !hay((l) => l[0] === 'compat_borrador') && /Prueba lo guardado/.test(todoTexto(arbol)));
arbol = renderizar(elCompat, true);
check('CompatCard: muestra conectado y latencia', /Conectado · 89 ms/.test(todoTexto(arbol)), todoTexto(arbol).slice(0, 400));
const chipM2 = boton(arbol, 'm2');
check('CompatCard: modelos para elegir', !!chipM2);
if (chipM2) { chipM2.props.onClick(); check('CompatCard: chip rellena el modelo', hubo('compat_model', 'm2')); }
// Con compat_borrador: antes de probar manda lo escrito, con la máscara tal cual (el puente usa la guardada)
const llamB = [];
const B = sandbox(luneFalso(llamB, {}, { compat_borrador(j) { llamB.push(['compat_borrador', JSON.parse(j)]); } }));
arbol = renderizar(h(B.sb.CompatCard, { cfg: { compat_url: 'https://api.groq.com/openai/v1', compat_key: '••••••••', compat_model: 'm1' }, set: rec }));
check('CompatCard con borrador: avisa de que prueba lo escrito', /Prueba lo que está escrito/.test(todoTexto(arbol)));
boton(arbol, 'Probar conexión').props.onClick();
const iB = llamB.findIndex((l) => l[0] === 'compat_borrador'), iP = llamB.findIndex((l) => l[0] === 'compat_probar');
check('CompatCard: compat_borrador (con la máscara) antes de compat_probar', iB >= 0 && iP > iB
  && JSON.stringify(llamB[iB][1]) === JSON.stringify({ compat_url: 'https://api.groq.com/openai/v1', compat_key: '••••••••', compat_model: 'm1' }), llamB);

const elAv = h(WC.AvanzadoCard, { cfg: { temperatura: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1 }, set: rec });
arbol = renderizar(elAv);
check('AvanzadoCard: reconoce Preciso', boton(arbol, 'Preciso').props['data-variant'] === 'primary');
boton(arbol, 'Liberar memoria').props.onClick();
arbol = renderizar(elAv, true);
check('AvanzadoCard: ia_liberar_vram', hay((l) => l[0] === 'liberar') && /Listo/.test(todoTexto(arbol)));

// Host: señal → modal → aprobar → siguiente en cola
const elHost = h(WC.AprobacionHost, {});
arbol = renderizar(elHost);
check('AprobacionHost: vacío al principio', arbol.length === 0);
check('AprobacionHost: conectado a aprobacion_pedida', typeof conexiones.pedida === 'function');
conexiones.pedida(JSON.stringify({ id: 'x9', herramienta: 'abrir_url', resumen: 'Abrir https://ejemplo.com', args: { url: 'https://ejemplo.com' } }));
conexiones.pedida(JSON.stringify({ id: 'x9', herramienta: 'abrir_url' }));      // duplicada: se ignora
conexiones.pedida(JSON.stringify({ id: 'y1', herramienta: 'minecraft_orden', resumen: 'Ven aquí', args: { orden: 'ven' } }));
conexiones.pedida('basura');
arbol = renderizar(elHost, true);
check('AprobacionHost: muestra la primera', /abrir_url/.test(todoTexto(arbol)) && /\+1 en cola/.test(todoTexto(arbol)), todoTexto(arbol).slice(0, 300));
boton(arbol, 'Sí, hazlo').props.onClick();
check('AprobacionModal: Sí → resolver_aprobacion(id, true)', hay((l) => l[0] === 'resolver' && l[1] === 'x9' && l[2] === true));
arbol = renderizar(elHost, true);
check('AprobacionHost: pasa a la siguiente', /minecraft_orden/.test(todoTexto(arbol)) && !/abrir_url/.test(todoTexto(arbol)));
conexiones.resuelta('y1');                                                        // resuelta desde el diálogo Qt
arbol = renderizar(elHost, true);
check('AprobacionHost: aprobacion_resuelta la quita', arbol.length === 0);
WC.LuneIA.demoAprobacion();
arbol = renderizar(elHost, true);
check('AprobacionHost: evento lune-aprobacion (demo)', /lanzar_app/.test(todoTexto(arbol)));

// La cola no regala tiempo: una petición que esperó detrás de otra caduca cuando el backend
llamadas.length = 0;
const conexQ = {};
const Q = sandbox(luneFalso(llamadas, conexQ));
const elQ = h(Q.sb.AprobacionHost, {});
renderizar(elQ);
conexQ.pedida(JSON.stringify({ id: 'q1', herramienta: 'abrir_url', timeout: 60 }));
conexQ.pedida(JSON.stringify({ id: 'q2', herramienta: 'minecraft_orden', timeout: 60 }));
arbol = renderizar(elQ, true);
Q.avanzar(40000);
arbol = renderizar(elQ, true);
check('AprobacionHost: a los 40 s quedan 20', /20 s/.test(todoTexto(arbol)) && /abrir_url/.test(todoTexto(arbol)), todoTexto(arbol).slice(0, 200));
Q.avanzar(21000);
arbol = renderizar(elQ, true);
// Caducar no es rechazar: no se responde al puente (el Ejecutor la marca CADUCADA él solo)
check('AprobacionHost: la primera caduca y se cierra sin responder', !llamadas.some((l) => l[0] === 'resolver')
  && !/abrir_url/.test(todoTexto(arbol)), { llamadas, texto: todoTexto(arbol).slice(0, 200) });
Q.avanzar(250);
arbol = renderizar(elQ, true);
check('AprobacionHost: la de la cola ya había caducado también (sin responder)', !llamadas.some((l) => l[0] === 'resolver')
  && arbol.length === 0, { llamadas, texto: todoTexto(arbol).slice(0, 200) });
conexQ.resuelta('q1');                                   // llega la resolución del backend (CADUCADA): no pasa nada
check('AprobacionHost: aprobacion_resuelta de una ya cerrada no rompe', renderizar(elQ, true).length === 0);
const P = sandbox(luneFalso(llamadas, {}, {
  aprobaciones_pendientes(cb) { cb(JSON.stringify([{ id: 'p0', herramienta: 'comentar_pantalla', resumen: 'Captura a la nube', riesgo: 'LECTURA', origen: 'no_confiable' }])); },
}));
arbol = renderizar(h(P.sb.AprobacionHost, {}));
check('AprobacionHost: recoge las que ya esperaban (aprobaciones_pendientes)', /comentar_pantalla/.test(todoTexto(arbol)));
check('AprobacionModal: avisa del texto de terceros', /texto de terceros/.test(todoTexto(arbol)) && /Si no se lo pediste tú, di que no/.test(todoTexto(arbol)));
resueltos = [];
llamadas.length = 0;
const X = sandbox(luneFalso(llamadas, {}));
renderizar(h(X.sb.AprobacionModal, { onResolver, pendiente: { id: 'old', herramienta: 'x', expira: 1700000000000 - 5000 } }));
check('AprobacionModal: ya caducada al llegar = se cierra al momento, sin responder al puente',
  JSON.stringify(resueltos) === JSON.stringify([['old', false]]) && !llamadas.some((l) => l[0] === 'resolver'), { resueltos, llamadas });

// Cuenta atrás: sin respuesta = caducada (solo se cierra); Esc = No
llamadas.length = 0; resueltos = [];
const motivos = [];
const D = sandbox(luneFalso(llamadas, {}));
renderizar(h(D.sb.AprobacionModal, { onResolver: (id, ok, motivo) => { resueltos.push([id, ok]); motivos.push(motivo); }, pendiente: { id: 't1', herramienta: 'x', timeout_s: 5 } }));
D.avanzar(3000);
check('AprobacionModal: antes de tiempo no resuelve', !llamadas.some((l) => l[0] === 'resolver') && resueltos.length === 0);
D.avanzar(2500);
check('AprobacionModal: a 0 s = caducada: se cierra sin resolver_aprobacion', !llamadas.some((l) => l[0] === 'resolver')
  && JSON.stringify(resueltos) === JSON.stringify([['t1', false]]) && motivos[0] === 'caducada', { llamadas, resueltos, motivos });
D.avanzar(1000);
check('AprobacionModal: caducada una sola vez', resueltos.length === 1, resueltos);
const E = sandbox(luneFalso(llamadas, {}));
resueltos = [];
renderizar(h(E.sb.AprobacionModal, { onResolver, pendiente: { id: 'e1', herramienta: 'x' } }));
E.sb.dispatchEvent({ type: 'keydown', key: 'Enter', preventDefault() {} });
check('AprobacionModal: Enter no aprueba', resueltos.length === 0);
E.sb.dispatchEvent({ type: 'keydown', key: 'Escape', preventDefault() {} });
check('AprobacionModal: Esc = No', JSON.stringify(resueltos) === JSON.stringify([['e1', false]]), resueltos);

fin();
"""


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado: se saltan los tests de JSX")
    return node


def _correr(tmp_path: Path, modo: str, archivos) -> dict:
    node = _node()
    arnes = tmp_path / "arnes_jsx.cjs"
    arnes.write_text(ARNES_JS, encoding="utf-8")
    r = subprocess.run(
        [node, str(arnes), modo, str(BABEL), *(str(a) for a in archivos)],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    lineas = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    salida = (r.stdout or "")[-4000:] + "\n" + (r.stderr or "")[-3000:]
    assert lineas, f"el arnés de Node no dio resultado:\n{salida}"
    res = json.loads(lineas[-1])
    assert r.returncode == 0 and not res["fallos"], "fallos:\n  " + "\n  ".join(res["fallos"]) + f"\n{salida}"
    return res


def test_existen_los_jsx_de_voz_e_ia():
    for nombre in ("voz.jsx", "ia_avanzada.jsx"):
        ruta = CARPETA_EXTRA / nombre
        assert ruta.is_file(), f"falta {ruta}"
        src = ruta.read_text(encoding="utf-8")
        # Se registran solos y no dependen de que window.lune exista (demo en navegador).
        assert "Object.assign(window" in src
        assert "window.lune" in src


def test_jsx_extra_transpilan(tmp_path):
    archivos = sorted(CARPETA_EXTRA.glob("*.jsx"))
    assert archivos, "no hay .jsx en extra/"
    res = _correr(tmp_path, "transpilar", archivos)
    assert set(res["archivos"]) == {a.name for a in archivos}


def test_voz_e_ia_en_sandbox(tmp_path):
    res = _correr(tmp_path, "probar", [CARPETA_EXTRA / "voz.jsx", CARPETA_EXTRA / "ia_avanzada.jsx"])
    assert res["checks"] > 100
