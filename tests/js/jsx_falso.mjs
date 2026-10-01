/*
 * tests/js/jsx_falso.mjs — sandbox para probar los .jsx de la interfaz web sin navegador.
 *
 * Transpila con el Babel vendorizado (ui_web/vendor/babel.min.js, las mismas opciones que usa
 * <script type="text/babel">) y ejecuta en un contexto de `vm` con:
 *   · React falso con hooks mínimos (useState, useRef, useMemo, useCallback y useEffect CON
 *     limpieza), `key` y desmontaje de lo que deja de dibujarse (como React);
 *   · reloj y temporizadores falsos (avanzar(ms) dispara en orden; clearTimeout de verdad);
 *   · eventos de window (addEventListener con {once}, dispatchEvent, CustomEvent);
 *   · el kit window.LUNE falso (Card, Button, Input, Switch, Badge) con la misma firma.
 * Además, escritorioFalso(): un window.luneEscritorio que apunta las llamadas y responde por
 * callback, con señales (connect/disconnect/emit).
 *
 * No es un test (no acaba en .test.mjs): lo usan radial_web.test.mjs y tarjetas_c4.mjs.
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

export const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const KIT = path.join(RAIZ, 'ui_web', 'ui_kits', 'lune-desktop');
export const EXTRA = path.join(KIT, 'extra');

let babel = null;
export function cargarBabel() {
  if (babel) return babel;
  const src = fs.readFileSync(path.join(RAIZ, 'ui_web', 'vendor', 'babel.min.js'), 'utf8');
  const m = { exports: {} };
  new Function('module', 'exports', 'self', 'window', src)(m, m.exports, {}, {});
  if (!m.exports || typeof m.exports.transform !== 'function') throw new Error('no pude cargar Babel standalone');
  babel = m.exports;
  return babel;
}
export const OPCIONES = {
  presets: ['react', 'env'],
  plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'],
};
const cacheCodigo = new Map();
export function transpilar(ruta) {
  if (!cacheCodigo.has(ruta)) {
    cacheCodigo.set(ruta, cargarBabel().transform(fs.readFileSync(ruta, 'utf8'), { ...OPCIONES, filename: path.basename(ruta) }).code);
  }
  return cacheCodigo.get(ruta);
}

// ── React falso ────────────────────────────────────────────────────────────────
export function crearReact() {
  const Fragment = Symbol('Fragment');
  let actual = null, sucio = false, efectos = [];
  let instancias = new Map();             // tipo → Map(clave → {slots})
  let contador = new Map(), vistos = new Set();
  const cambiaron = (a, b) => !a || !b || a.length !== b.length || a.some((x, i) => !Object.is(x, b[i]));
  function slot() {
    if (!actual) throw new Error('hook fuera de un componente');
    return [actual.slots, actual.i++];
  }
  function limpiar(inst) {
    for (const s of inst.slots) if (s && s.__efecto && typeof s.limpiar === 'function') { const f = s.limpiar; s.limpiar = null; f(); }
  }
  const React = {
    Fragment,
    createElement(type, props, ...children) {
      const { key, ...p } = props || {};
      if (children.length) p.children = children.length === 1 ? children[0] : children;
      return { type, props: p, key: key == null ? null : String(key) };
    },
    useState(init) {
      const [s, i] = slot();
      if (!(i in s)) s[i] = { v: typeof init === 'function' ? init() : init };
      const celda = s[i];
      return [celda.v, (v) => {
        const nv = typeof v === 'function' ? v(celda.v) : v;
        if (!Object.is(nv, celda.v)) { celda.v = nv; sucio = true; }
      }];
    },
    useRef(v) { const [s, i] = slot(); if (!(i in s)) s[i] = { current: v }; return s[i]; },
    useMemo(fn, deps) {
      const [s, i] = slot();
      if (!(i in s) || cambiaron(s[i].deps, deps)) s[i] = { deps, v: fn() };
      return s[i].v;
    },
    useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
    // React.memo: aquí no memoriza (cada pase vuelve a dibujar todo); guarda el componente y el
    // comparador para que los tests los prueben (chat_web.test.mjs).
    memo(tipo, igual) { const Memo = (props) => tipo(props); Memo.tipo = tipo; Memo.igual = igual; return Memo; },
    useEffect(fn, deps) {
      const [s, i] = slot();
      const previo = s[i];
      if (previo && !cambiaron(previo.deps, deps)) return;
      const reg = { __efecto: true, deps, limpiar: null };
      s[i] = reg;
      efectos.push(() => {
        if (previo && typeof previo.limpiar === 'function') { const f = previo.limpiar; previo.limpiar = null; f(); }
        const r = fn();
        reg.limpiar = typeof r === 'function' ? r : null;
      });
    },
  };
  function llamar(tipo, props, key) {
    const n = contador.get(tipo) || 0;
    contador.set(tipo, n + 1);
    const clave = key != null ? 'k:' + key : 'n:' + n;
    if (!instancias.has(tipo)) instancias.set(tipo, new Map());
    const mapa = instancias.get(tipo);
    if (!mapa.has(clave)) mapa.set(clave, { slots: [] });
    vistos.add(mapa.get(clave));
    const previo = actual;
    actual = { slots: mapa.get(clave).slots, i: 0 };
    try { return tipo(props || {}); } finally { actual = previo; }
  }
  function expandir(el) {
    if (el == null || el === false || el === true) return [];
    if (typeof el === 'string' || typeof el === 'number') return [String(el)];
    if (Array.isArray(el)) return el.flatMap(expandir);
    if (typeof el.type === 'function') return expandir(llamar(el.type, el.props, el.key));
    if (el.type === Fragment) return expandir(el.props.children);
    return [{ type: el.type, props: el.props, hijos: expandir(el.props.children) }];
  }
  function barrer() {
    for (const [tipo, mapa] of instancias) {
      for (const [clave, inst] of mapa) if (!vistos.has(inst)) { limpiar(inst); mapa.delete(clave); }
      if (!mapa.size) instancias.delete(tipo);
    }
  }
  /** Dibuja, desmonta lo que ya no sale, corre los efectos y repite mientras cambie el estado. */
  function renderizar(el) {
    let arbol = [];
    for (let pase = 0; pase < 25; pase++) {
      sucio = false; contador = new Map(); vistos = new Set(); efectos = [];
      arbol = expandir(el);
      barrer();
      const ef = efectos; efectos = [];
      ef.forEach((f) => f());
      if (!sucio) break;
    }
    return arbol;
  }
  function desmontar() {
    for (const mapa of instancias.values()) for (const inst of mapa.values()) limpiar(inst);
    instancias = new Map();
  }
  React.renderizar = renderizar;
  React.desmontar = desmontar;
  return React;
}

// ── Árbol dibujado ─────────────────────────────────────────────────────────────
export const texto = (n) => (typeof n === 'string' ? n : n.hijos.map(texto).join(''));
export function buscar(nodos, pred, out = []) {
  for (const n of nodos) {
    if (typeof n === 'string') continue;
    if (pred(n)) out.push(n);
    buscar(n.hijos, pred, out);
  }
  return out;
}
export const porId = (arbol, id) => buscar(arbol, (n) => n.props && n.props.id === id)[0];
export const boton = (arbol, t) => buscar(arbol, (n) => n.type === 'button' && texto(n).includes(t))[0];
export const botones = (arbol, t) => buscar(arbol, (n) => n.type === 'button' && texto(n).includes(t));
export const todoTexto = (arbol) => arbol.map(texto).join(' ');
export const conClase = (arbol, c) => buscar(arbol, (n) => n.props && typeof n.props.className === 'string'
  && n.props.className.split(/\s+/).includes(c));
/** Props del <input type="checkbox"> del Switch cuya etiqueta contiene `t` (checked, onChange…). */
export const interruptor = (arbol, t) => {
  const l = buscar(arbol, (n) => n.type === 'label' && texto(n).includes(t) && buscar(n.hijos, (x) => x.type === 'input').length)[0];
  const i = l && buscar(l.hijos, (x) => x.type === 'input')[0];
  return i ? i.props : undefined;
};

// ── Kit LUNE falso (misma firma que ui_web/components) ────────────────────────
function kitFalso(h) {
  return {
    Card: ({ children, eyebrow, title, tone, id }) => h('section', { id, 'data-tone': tone },
      eyebrow ? h('p', null, eyebrow) : null, title ? h('h3', null, title) : null, children),
    Button: ({ children, variant, size, ...r }) => h('button', { ...r, 'data-variant': variant }, children),
    Input: ({ label, hint, textarea, error, ...r }) => h('div', { 'data-error': !!error },
      label ? h('label', null, label) : null, h(textarea ? 'textarea' : 'input', r), hint ? h('span', null, hint) : null),
    Switch: ({ label, accent, ...r }) => h('label', null, h('input', { type: 'checkbox', ...r }), label),
    Badge: ({ children, variant, outline }) => h('span', { 'data-badge': variant }, children),
    StatusPill: ({ status }) => h('span', { 'data-status': status }),
    IconButton: ({ children, label, variant, active, ...r }) => h('button', { ...r, 'aria-label': label, 'data-active': !!active }, children),
    ProviderTab: ({ name, desc, active, accent, icon, ...r }) => h('button', { ...r, 'data-accent': accent, 'data-active': !!active }, name),
  };
}

// ── Sandbox ────────────────────────────────────────────────────────────────────
export function crearSandbox({ archivos = [], escritorio = null, lune = null, globales = {} } = {}) {
  let ahora = 1700000000000;
  const RealDate = Date;
  class FalsaFecha extends RealDate {
    constructor(...a) { super(...(a.length ? a : [ahora])); }
    static now() { return ahora; }
  }
  let sigId = 1;
  const timers = new Map();
  const setTimeout_ = (fn, ms) => { const id = sigId++; timers.set(id, { t: ahora + Math.max(0, Number(ms) || 0), fn, cada: 0 }); return id; };
  const setInterval_ = (fn, ms) => { const id = sigId++; const c = Math.max(1, Number(ms) || 1); timers.set(id, { t: ahora + c, fn, cada: c }); return id; };
  const clear = (id) => { timers.delete(id); };
  function avanzar(ms = 0) {
    const fin = ahora + Math.max(0, ms);
    for (let vueltas = 0; vueltas < 10000; vueltas++) {
      let prox = null;
      for (const [id, x] of timers) if (x.t <= fin && (!prox || x.t < prox[1].t || (x.t === prox[1].t && id < prox[0]))) prox = [id, x];
      if (!prox) break;
      const [id, x] = prox;
      ahora = Math.max(ahora, x.t);
      if (x.cada) x.t += x.cada; else timers.delete(id);
      x.fn();
    }
    ahora = fin;
  }
  const oyentes = {};
  const add = (t, f, o) => { (oyentes[t] = oyentes[t] || []).push({ f, once: !!(o && typeof o === 'object' && o.once) }); };
  const remove = (t, f) => { oyentes[t] = (oyentes[t] || []).filter((x) => x.f !== f); };
  const dispatch = (e) => {
    (oyentes[e.type] || []).slice().forEach((x) => { if (x.once) remove(e.type, x.f); x.f(e); });
    return true;
  };
  class CustomEvent { constructor(type, init) { this.type = type; this.detail = init && init.detail; } }
  class Event { constructor(type) { this.type = type; } }
  const React = crearReact();
  const sb = {
    React, console, Date: FalsaFecha,
    setTimeout: setTimeout_, clearTimeout: clear, setInterval: setInterval_, clearInterval: clear,
    addEventListener: add, removeEventListener: remove, dispatchEvent: dispatch, CustomEvent, Event,
    innerWidth: 1280, innerHeight: 820,
    ...globales,
  };
  sb.LUNE = kitFalso(React.createElement);
  sb.window = sb;
  if (escritorio) sb.luneEscritorio = escritorio;
  if (lune) sb.lune = lune;
  vm.createContext(sb);
  const antes = new Set(Object.keys(sb));
  for (const ruta of archivos) vm.runInContext(transpilar(ruta), sb, { filename: path.basename(ruta) });
  // Babel (preset env) deja helpers al nivel superior (_objectSpread, ownKeys…): no cuentan.
  const nuevas = Object.keys(sb).filter((k) => !antes.has(k) && !k.startsWith('_') && k !== 'ownKeys');
  /** Evento de teclado (o lo que sea) para window, con preventDefault/stopPropagation apuntados. */
  const evento = (type, extra) => {
    const e = { type, prevenido: false, parado: false, ...(extra || {}) };
    e.preventDefault = () => { e.prevenido = true; };
    e.stopPropagation = () => { e.parado = true; };
    return e;
  };
  return {
    sb, React, h: React.createElement, nuevas, avanzar, oyentes, dispatch, evento,
    render: (el) => React.renderizar(el),
    desmontar: () => React.desmontar(),
    temporizadores: () => timers.size,
    ahora: () => ahora,
    nOyentes: (t) => (oyentes[t] || []).length,
  };
}

// ── window.luneEscritorio falso ────────────────────────────────────────────────
export function senal() {
  const fs_ = [];
  return {
    connect(f) { fs_.push(f); },
    disconnect(f) { const i = fs_.indexOf(f); if (i >= 0) fs_.splice(i, 1); },
    emit(...a) { fs_.slice().forEach((f) => f(...a)); },
    get oyentes() { return fs_.length; },
  };
}
export const RANURAS = [
  'acciones_catalogo', 'accion_menu', 'tema_estado', 'tema_previsualizar', 'tema_guardar', 'tema_restablecer',
  'efectos', 'efectos_guardar', 'atajos_estado', 'atajo_validar', 'atajo_guardar', 'atajos_activar',
  'atajos_capturando', 'atajos_restablecer', 'radial_estado', 'radial_guardar', 'bandeja_estado', 'bandeja_guardar',
  'juego_estado_json', 'juego_forzar', 'juego_config', 'juego_guardar', 'juego_apps_visibles', 'rendimiento',
  'rendimiento_guardar', 'liberar_memoria',
];
export const SENALES = ['tema_cambio', 'juego_estado', 'atajos_cambio', 'navegar'];
/** respuestas[ranura] = valor o función(args…) → valor (lo que devolvería el slot: casi siempre JSON). */
export function escritorioFalso(respuestas = {}) {
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
  return {
    obj, llamadas, respuestas,
    de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)),
    hubo: (n, pred) => llamadas.some((l) => l[0] === n && (!pred || pred(...l.slice(1)))),
    limpiar: () => { llamadas.length = 0; },
  };
}
