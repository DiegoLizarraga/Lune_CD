/*
 * ui_web/ui_kits/lune-desktop/vrm_barra.js — avatar VRM en la barra lateral del modo normal.
 *
 * Para qué sirve: la piel web (index.html) carga todo con Babel (`text/babel`) y no
 * tiene three.js. Este módulo ES es el puente: crea la asistente 3D de
 * ui_web/vrm/lune_vrm.js (crearAsistente) sobre un <canvas> de la barra lateral y la
 * publica en `window.LuneVRMBarra` para que sidebar.jsx la use sin imports.
 *
 * Se carga con un <script type="module"> DESPUÉS de un importmap igual al de
 * ui_web/companion_vrm.html, con rutas relativas a ui_kits/lune-desktop/:
 *   "three": "../../vendor/three/three.module.min.js",
 *   "three/addons/": "../../vendor/three/",
 *   "@pixiv/three-vrm": "../../vendor/three/three-vrm.module.min.js"
 * No importa nada de forma estática: el motor (y three) se piden con import()
 * la primera vez que se crea un avatar, así la página no paga three.js si la
 * asistente no es VRM, y el archivo se prueba en Node (tests/js/vrm_barra.test.mjs).
 *
 * API (window.LuneVRMBarra y exports):
 *   const h = LuneVRMBarra.crear(canvas, '/vrm/actual.vrm', opts)   → handle
 *     opts: encuadre ('retrato'|'cuerpo'), fps (30), version (→ ?v=),
 *           onEvento(tipo, dato), alListo(meta), alError(motivo),
 *           liberarAlPausar (true), clicToca (true), alturaCara (0.35),
 *           alcance (1), params (json inicial para luneParams), validarParams(json)
 *   h.setEstado(e) · h.setHablando(on) · h.pausar(on) · h.cargar(url, v)
 *   h.luneParams(json) · h.encuadrar(modo) · h.cursor(clientX, clientY) · h.destruir()
 *   h.registrar(instalar) → módulo | null   módulo del bus de lune_vrm.js (lune_modulos.js);
 *                           antes de que haya motor se encola y se registra al crearlo
 *   h.mod(nombre, metodo, ...args)          API de un módulo (= window.luneMod en la asistente en escritorio);
 *                           sin motor se encola (las 32 últimas) y se llama tras los registros
 *   h.usarModulo(nombre, {opciones, importar}) → Promise<bool>   import() perezoso de
 *                           RUTAS_MODULOS[nombre] y registrar(ctx => mod.instalar(ctx, opciones)),
 *                           una vez por avatar; opciones por defecto: OPCIONES_MODULOS[nombre]
 *                           (baileProc: {encuadrar: false}, la barra se queda en 'retrato')
 *   LuneVRMBarra.destruir(h) · .params(json) (todos los vivos y los siguientes)
 *   LuneVRMBarra.recargar(url, v) (cambio de personaje) · .precargar() · .activos()
 *   LuneVRMBarra.cargarModulo(nombre) → Promise<módulo | null> (en caché; un fallo se reintenta)
 *
 * Cursor: la asistente mira al ratón de la PÁGINA (mousemove de window). clientX/Y se
 * mapean a nx/ny como hace companion.py con el cursor global: respecto a la cara
 * (proyección del hueso de la cabeza; si no, 35 % desde arriba del canvas) y a
 * media ventana, en −1.6..1.6. Fuera de la ventana no llegan eventos: se queda el
 * último nx/ny con `dentro = false`. `dentro` = el puntero está sobre el canvas
 * (caricia en la cabeza y hit-test por alfa, igual que en la asistente flotante).
 *
 * Recursos: pausar(true) pone FPS 0 y, con liberarAlPausar, suelta el contexto
 * WebGL (WEBGL_lose_context) para no tener dos avatares en la GPU cuando Lune sale
 * al escritorio; pausar(false) lo restaura (three.js re-sube texturas y shaders).
 * destruir() libera el modelo y el contexto (con m.destruir() del motor, que además
 * para su bucle y descarta una carga en vuelo); el <canvas> ya no se puede
 * reutilizar (en React, que se monte uno nuevo).
 */

/** Ruta del .vrm activo que publica el http local (ServidorEstatico.publicar). */
export const RUTA_MODELO = '/vrm/actual.vrm';
/** Motor de la asistente, relativo a este archivo (ui_web/vrm/lune_vrm.js). */
export const RUTA_MOTOR = '../../vrm/lune_vrm.js';

/** Opciones por defecto de crear(). */
export const DEFECTOS = Object.freeze({
  encuadre: 'retrato',
  fps: 30,               // la barra es pequeña y va junto al chat: 30 fps sobran
  alturaCara: 0.35,      // igual que companion.py (_enviar_cursor) si no hay cabeza proyectada
  alcance: 1,            // × media ventana: el cursor en el borde de la ventana ≈ ±1
  tope: 1.6,             // mismo clamp que companion.py
  liberarAlPausar: true,
  clicToca: true,
  refrescoCaraMs: 400,   // cada cuánto se vuelve a proyectar la cabeza como centro de la mirada
});

const TOPE_PARAM = 100000;     // límite superior de cualquier PARAM numérico en filtrarParams
const ALTURA_OJOS = 0.06;      // m por encima del hueso de la cabeza (línea de los ojos)

const finito = Number.isFinite;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const numero = (...vs) => { for (const v of vs) { const n = Number(v); if (v !== null && v !== '' && finito(n)) return n; } return 0; };

function aviso(...args) { try { console.warn('[vrm_barra]', ...args); } catch (e) { /* sin consola */ } }

// ── Lógica pura ─────────────────────────────────────────────────────────────────

/**
 * Mapea la posición del ratón en la página (clientX/Y) a lo que espera
 * asistente.cursor(nx, ny, px, py, dentro):
 *   nx, ny  −tope..tope; 0 = la cara; +nx a la derecha, +ny hacia ARRIBA.
 *           Escala: media ventana (vista.ancho/2, vista.alto/2) × alcance.
 *   px, py  las mismas coordenadas cliente (lune_vrm.js las compara con
 *           canvas.getBoundingClientRect() y con su proyección de la cabeza).
 *   dentro  el punto cae sobre el canvas (borde derecho e inferior excluidos).
 * `rect` es un DOMRect (left, top, width, height); `opciones.centro` = {x, y} en px
 * cliente sustituye al centro por defecto (centro horizontal, alturaCara vertical).
 * Devuelve null si x o y no son números finitos.
 */
export function mapearCursor(x, y, rect, vista, opciones = {}) {
  if (!finito(x) || !finito(y) || !rect) return null;
  const alturaCara = finito(opciones.alturaCara) ? clamp(opciones.alturaCara, 0, 1) : DEFECTOS.alturaCara;
  const alcance = finito(opciones.alcance) && opciones.alcance > 0 ? opciones.alcance : DEFECTOS.alcance;
  const tope = finito(opciones.tope) && opciones.tope > 0 ? opciones.tope : DEFECTOS.tope;
  const left = numero(rect.left, rect.x), top = numero(rect.top, rect.y);
  const w = Math.max(0, numero(rect.width)), h = Math.max(0, numero(rect.height));
  const c = opciones.centro;
  const cx = c && finito(c.x) ? c.x : left + w / 2;
  const cy = c && finito(c.y) ? c.y : top + h * alturaCara;
  const semiW = Math.max(1, numero(vista && vista.ancho) / 2) * alcance;
  const semiH = Math.max(1, numero(vista && vista.alto) / 2) * alcance;
  return {
    nx: clamp((x - cx) / semiW, -tope, tope),
    ny: clamp((cy - y) / semiH, -tope, tope),
    px: x,
    py: y,
    dentro: w > 0 && h > 0 && x >= left && x < left + w && y >= top && y < top + h,
  };
}

/**
 * Añade (o sustituye) `v=<version>` en la URL del modelo para saltarse la caché
 * cuando cambia el archivo (como companion_vrm.html con ?v=). Sin versión, igual.
 */
export function urlConVersion(url, v) {
  url = String(url || '');
  if (!url || v === undefined || v === null || v === '') return url;
  const val = encodeURIComponent(String(v));
  const i = url.indexOf('#');
  const base = i >= 0 ? url.slice(0, i) : url;
  const ancla = i >= 0 ? url.slice(i) : '';
  if (/[?&]v=[^&]*/.test(base)) return base.replace(/([?&])v=[^&]*/, `$1v=${val}`) + ancla;
  return base + (base.includes('?') ? '&' : '?') + 'v=' + val + ancla;
}

/**
 * Lista blanca para luneParams cuando el motor no trae la suya: solo claves que
 * YA existen en PARAMS con valor numérico, con un número finito (o texto numérico).
 * invertirEjes → −1/0/1; el resto de invertir* → ±1 (0 se ignora); los demás no
 * pueden ser negativos y se limitan a TOPE_PARAM.
 * `entrada` es un objeto o un JSON. → {aplicados, ignorados, error}
 */
export function filtrarParams(params, entrada) {
  const res = { aplicados: {}, ignorados: [], error: null };
  let datos = entrada;
  if (typeof datos === 'string') {
    try { datos = JSON.parse(datos); } catch (e) { res.error = 'JSON no válido'; return res; }
  }
  if (!datos || typeof datos !== 'object' || Array.isArray(datos)) { res.error = 'se esperaba un objeto'; return res; }
  for (const k of Object.keys(datos)) {
    const v = datos[k];
    const conocida = params && Object.prototype.hasOwnProperty.call(params, k) && typeof params[k] === 'number';
    const n = (typeof v === 'number' || (typeof v === 'string' && v.trim() !== '')) ? Number(v) : NaN;
    if (!conocida || !finito(n)) { res.ignorados.push(k); continue; }
    if (k === 'invertirEjes') res.aplicados[k] = Math.sign(n);
    else if (k.startsWith('invertir')) { if (n === 0) res.ignorados.push(k); else res.aplicados[k] = n < 0 ? -1 : 1; }
    else if (n < 0) res.ignorados.push(k);
    else res.aplicados[k] = Math.min(n, TOPE_PARAM);
  }
  return res;
}

/**
 * Suelta la memoria de un grafo de three.js sin importar three: geometrías (y sus
 * arrays, también los morph targets), materiales, texturas (las de los uniforms de
 * MToon incluidas; cierra los ImageBitmap) y esqueletos. Cada recurso una vez.
 * → {geometrias, materiales, texturas}
 */
export function vaciarEscena(raiz) {
  const cuenta = { geometrias: 0, materiales: 0, texturas: 0 };
  if (!raiz || typeof raiz.traverse !== 'function') return cuenta;
  const geoms = new Set(), mats = new Set(), texs = new Set(), esqueletos = new Set();
  raiz.traverse((o) => {
    if (!o) return;
    if (o.geometry) geoms.add(o.geometry);
    const ms = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
    for (const mt of ms) if (mt) mats.add(mt);
    if (o.skeleton) esqueletos.add(o.skeleton);
  });
  for (const mt of mats) {
    for (const k of Object.keys(mt)) { const v = mt[k]; if (v && v.isTexture) texs.add(v); }
    const u = mt.uniforms;
    if (u && typeof u === 'object') {
      for (const k of Object.keys(u)) { const v = u[k] && u[k].value; if (v && v.isTexture) texs.add(v); }
    }
    try { mt.dispose && mt.dispose(); } catch (e) { /* sigue */ }
    cuenta.materiales++;
  }
  for (const t of texs) {
    try { t.dispose && t.dispose(); } catch (e) { /* sigue */ }
    const img = t.image;
    if (img && typeof img.close === 'function') { try { img.close(); } catch (e) { /* ya cerrado */ } }
    try { if (t.source && typeof t.source === 'object') t.source.data = null; } catch (e) { /* solo lectura */ }
    cuenta.texturas++;
  }
  for (const g of geoms) {
    try { g.dispose && g.dispose(); } catch (e) { /* sigue */ }
    try {
      if (g.attributes && typeof g.deleteAttribute === 'function') for (const k of Object.keys(g.attributes)) g.deleteAttribute(k);
      if (typeof g.setIndex === 'function') g.setIndex(null);
      if (g.morphAttributes) g.morphAttributes = {};
    } catch (e) { /* sigue */ }
    cuenta.geometrias++;
  }
  for (const s of esqueletos) { try { s.dispose && s.dispose(); } catch (e) { /* sigue */ } }
  try { raiz.removeFromParent && raiz.removeFromParent(); } catch (e) { /* sin padre */ }
  return cuenta;
}

/**
 * Libera la asistente que creó lune_vrm.js. Si trae destruir() (lune_vrm.js v10.3+: bucle,
 * resize, modelo, módulos, contexto y cargas en vuelo) se usa SOLO eso, una vez.
 * Si no lo trae, o lanza, el respaldo: FPS 0, alDescargar a los módulos del bus,
 * fuera de la escena, vaciarEscena, renderer.dispose() y pérdida forzada del
 * contexto (el bucle rAF de un motor viejo sigue vivo, pero a FPS 0 no hace nada).
 * Nunca lanza.
 */
export function liberarAsistente(m) {
  if (!m) return false;
  if (typeof m.destruir === 'function') {
    try { m.destruir(); return true; } catch (e) { aviso('destruir', e && e.message); }   // → respaldo
  }
  try { m.setFPS && m.setFPS(0); } catch (e) { /* sigue */ }
  const ctx = m.ctx || {};
  let vrm = null;
  try { vrm = typeof ctx.vrm === 'function' ? ctx.vrm() : null; } catch (e) { vrm = null; }
  if (vrm) {
    try { m.bus && m.bus.llamar && m.bus.llamar('alDescargar'); } catch (e) { /* sigue */ }
    try { ctx.scene && ctx.scene.remove && ctx.scene.remove(vrm.scene); } catch (e) { /* sigue */ }
    try { vaciarEscena(vrm.scene); } catch (e) { /* sigue */ }
  }
  const r = ctx.renderer;
  try { r && r.dispose && r.dispose(); } catch (e) { /* sigue */ }
  try { r && r.forceContextLoss && r.forceContextLoss(); } catch (e) { /* ya perdido */ }
  return true;
}

/**
 * Centro de la mirada en px cliente: el hueso de la cabeza (+ALTURA_OJOS m)
 * proyectado con ctx.proyectar. null si el motor aún no tiene cabeza.
 */
export function proyectarCabeza(m) {
  try {
    const ctx = m && m.ctx;
    const cabeza = ctx && ctx.huesos && ctx.huesos.head;
    const T = ctx && ctx.THREE;
    if (!cabeza || !T || typeof T.Vector3 !== 'function' || typeof ctx.proyectar !== 'function'
        || typeof cabeza.getWorldPosition !== 'function') return null;
    const v = cabeza.getWorldPosition(new T.Vector3());
    v.y += ALTURA_OJOS;
    const p = ctx.proyectar(v);
    return p && finito(p.x) && finito(p.y) ? { x: p.x, y: p.y } : null;
  } catch (e) {
    return null;
  }
}

// ── Motor (import perezoso) ─────────────────────────────────────────────────────

let motorPromesa = null;
function cargarMotorPorDefecto() {
  if (!motorPromesa) {
    motorPromesa = import(RUTA_MOTOR).catch((e) => { motorPromesa = null; throw e; });   // reintentable
  }
  return motorPromesa;
}

/** Empieza a descargar three.js y el motor sin crear nada. → Promise<bool> */
export function precargar() {
  return cargarMotorPorDefecto().then(() => true, (e) => { aviso('precarga', e && e.message); return false; });
}

/** Módulos del bus de lune_vrm.js que la barra carga bajo demanda (rutas relativas a este archivo). */
export const RUTAS_MODULOS = Object.freeze({
  baileProc: '../../vrm/lune_baile_proc.js',     // baile procedural (cortes 5/6): api {bailar, pulso, estado}
});
/** Opciones con que la barra instala cada módulo (instalar(ctx, opciones)). */
export const OPCIONES_MODULOS = Object.freeze({
  baileProc: Object.freeze({ encuadrar: false }),   // sin encuadre 'cuerpo' temporal: la barra es pequeña
});
const MAX_COLA_MOD = 32;
const modulosPromesa = new Map();
const importarPorDefecto = (ruta) => import(ruta);

/**
 * import() perezoso de un módulo del bus por su nombre en RUTAS_MODULOS. → Promise<módulo | null>
 * (null si el nombre no existe o el archivo no carga: 404, sintaxis). Se guarda en caché; un
 * fallo no se guarda (se puede reintentar). `importar` es inyectable (tests).
 */
export function cargarModulo(nombre, importar = importarPorDefecto) {
  const ruta = Object.prototype.hasOwnProperty.call(RUTAS_MODULOS, nombre) ? RUTAS_MODULOS[nombre] : null;
  if (!ruta) return Promise.resolve(null);
  if (!modulosPromesa.has(nombre)) {
    const p = Promise.resolve()
      .then(() => importar(ruta))
      .then((mod) => mod || null, (e) => { modulosPromesa.delete(nombre); aviso('módulo', nombre, e && e.message); return null; });
    modulosPromesa.set(nombre, p);
  }
  return modulosPromesa.get(nombre);
}

// ── Avatares vivos ──────────────────────────────────────────────────────────────

const vivos = new Set();
const lienzosUsados = new WeakSet();   // canvas con un renderer ya destruido: su contexto no vuelve
let paramsGlobales = null;             // último params(json): también para los que se creen luego

/**
 * Crea el avatar sobre `canvas` con el modelo `urlModelo` y devuelve el handle.
 * El motor se crea en una microtarea (tras el import): si se llama a destruir()
 * antes, no llega a tocar el canvas (StrictMode de React incluido).
 */
export function crear(canvas, urlModelo, opts = {}) {
  opts = opts || {};
  const cfg = { ...DEFECTOS };
  for (const k of Object.keys(DEFECTOS)) if (opts[k] !== undefined) cfg[k] = opts[k];
  cfg.encuadre = cfg.encuadre === 'cuerpo' ? 'cuerpo' : 'retrato';
  cfg.fps = finito(Number(cfg.fps)) && Number(cfg.fps) > 0 ? Number(cfg.fps) : DEFECTOS.fps;
  const ventana = opts.ventana || (typeof window !== 'undefined' ? window : null);
  const diferir = typeof opts.diferir === 'function' ? opts.diferir : (fn) => setTimeout(fn, 0);
  const reloj = typeof opts.reloj === 'function' ? opts.reloj
    : () => (globalThis.performance && performance.now ? performance.now() : Date.now());

  let m = null;                     // la asistente de lune_vrm.js
  let url = String(urlModelo || '');
  let version = opts.version !== undefined ? opts.version : null;
  let estado = 'normal', hablando = false, pausado = !!opts.pausado;
  let destruido = false, listo = false, arrancando = false;
  const paramsPend = [];
  if (opts.params) paramsPend.push(opts.params);
  const instaladores = [];          // registrar() antes de que haya motor
  const colaMod = [];               // mod() antes de que haya motor: [nombre, metodo, args]
  const modulosUsados = new Map();  // usarModulo(): nombre → Promise<bool>, una vez por avatar
  let raton = null, fuera = false, ultimoMapa = null, sobreModelo = false;
  let rafCursor = 0, rafEncuadre = 0;
  let cara = null, caraT = -Infinity;
  let ctxEstado = 'vivo', ext = null;   // vivo · perdiendo · perdido · restaurando
  let ro = null;

  const avisar = (tipo, dato) => {
    if (typeof opts.onEvento !== 'function') return;
    try { opts.onEvento(tipo, dato); } catch (e) { aviso('onEvento', tipo, e && e.message); }
  };
  const fallar = (motivo) => {
    const txt = String(motivo || 'error');
    if (typeof opts.alError === 'function') { try { opts.alError(txt); } catch (e) { aviso('alError', e && e.message); } }
    else aviso(txt);
  };

  // El renderer ajusta canvas.width/height; sin tamaño CSS el canvas crecería con
  // él (y con devicePixelRatio 2 el ResizeObserver entraría en bucle).
  try {
    const st = canvas && canvas.style;
    if (st) {
      if (!st.width) st.width = '100%';
      if (!st.height) st.height = '100%';
      if (!st.display) st.display = 'block';
    }
  } catch (e) { /* sin estilos */ }

  // ── Motor ──
  function arrancar() {
    if (destruido || m || arrancando || pausado || !url) return;
    if (!canvas || typeof canvas.getContext !== 'function') { fallar('No hay un <canvas> válido para el avatar.'); return; }
    if (lienzosUsados.has(canvas)) { fallar('Este <canvas> ya tuvo un avatar destruido: monta uno nuevo.'); return; }
    arrancando = true;
    let motor;
    try {
      motor = typeof opts.crearAsistente === 'function' ? { crearAsistente: opts.crearAsistente }
        : (typeof opts.cargarMotor === 'function' ? opts.cargarMotor() : cargarMotorPorDefecto());
    } catch (e) { motor = Promise.reject(e); }
    Promise.resolve(motor).then((mod) => {
      arrancando = false;
      if (destruido || m || pausado) return;          // pausado: arranca en pausar(false)
      const crearAsistente = mod && mod.crearAsistente;
      if (typeof crearAsistente !== 'function') throw new Error('el motor no exporta crearAsistente');
      lienzosUsados.add(canvas);
      listo = false;
      const nueva = crearAsistente({ canvas, src: urlConVersion(url, version), encuadre: cfg.encuadre, onEvento: alEventoMotor });
      if (destruido) { liberarAsistente(nueva); return; }
      m = nueva;
      try { m.setFPS(cfg.fps); } catch (e) { /* sigue */ }
      if (paramsGlobales) aplicarParams(paramsGlobales);
      while (paramsPend.length) aplicarParams(paramsPend.shift());
      // Módulos del bus y llamadas a su API que llegaron antes que el motor, en ese orden.
      while (instaladores.length) registrarEnMotor(instaladores.shift());
      while (colaMod.length) { const [n, met, args] = colaMod.shift(); llamarMod(n, met, args); }
      if (hablando) { try { m.setHablando(true); } catch (e) { /* sigue */ } }
      avisar('motor', true);
      enviarCursor();
    }).catch((e) => {
      arrancando = false;
      const msg = (e && e.message) || String(e);
      avisar('error', msg);
      fallar('No se pudo abrir el visor 3D: ' + msg);
    });
  }

  // Eventos del motor (cargando, listo, error, estado, caricia, arrastre, dormir…).
  function alEventoMotor(tipo, dato) {
    if (destruido) return;
    if (tipo === 'cargando') listo = false;
    else if (tipo === 'listo') {
      listo = true; cara = null;
      // Al cargar, el motor saluda (wave); si la app ya tenía otra cara, se respeta.
      if (m && estado !== 'normal') { try { m.setEstado(estado); } catch (e) { /* sigue */ } }
      if (m && hablando) { try { m.setHablando(true); } catch (e) { /* sigue */ } }
      if (typeof opts.alListo === 'function') { try { opts.alListo(dato); } catch (e) { aviso('alListo', e && e.message); } }
      enviarCursor();
    } else if (tipo === 'error') {
      listo = false;   // cargar() suelta el modelo anterior antes de pedir el nuevo
      fallar(dato);
    }
    avisar(tipo, dato);
  }

  // ── Cursor ──
  function centroCara() {
    if (!m || !listo) return null;
    const t = reloj();
    if (!cara || t - caraT >= cfg.refrescoCaraMs) { cara = proyectarCabeza(m); caraT = t; }
    return cara;
  }

  function enviarCursor() {
    if (destruido || pausado || !m || !raton) return;
    let mapa;
    if (fuera && ultimoMapa) mapa = { nx: ultimoMapa.nx, ny: ultimoMapa.ny, px: -1, py: -1, dentro: false };
    else {
      let rect = null;
      try { rect = canvas.getBoundingClientRect(); } catch (e) { rect = null; }
      const vista = { ancho: ventana ? ventana.innerWidth : 0, alto: ventana ? ventana.innerHeight : 0 };
      mapa = mapearCursor(raton.x, raton.y, rect, vista,
        { alturaCara: cfg.alturaCara, alcance: cfg.alcance, tope: cfg.tope, centro: centroCara() });
    }
    if (!mapa) return;
    ultimoMapa = mapa;
    let r = false;
    try { r = m.cursor(mapa.nx, mapa.ny, mapa.px, mapa.py, mapa.dentro); } catch (e) { r = false; }
    sobreModelo = !!mapa.dentro && r === true;
  }

  function programarCursor() {
    if (destruido || pausado || !m) return;
    if (ventana && typeof ventana.requestAnimationFrame === 'function') {
      if (!rafCursor) rafCursor = ventana.requestAnimationFrame(() => { rafCursor = 0; enviarCursor(); });
    } else enviarCursor();
  }

  function alMover(e) {
    if (destruido || !e) return;
    const x = Number(e.clientX), y = Number(e.clientY);
    if (!finito(x) || !finito(y)) return;
    raton = { x, y }; fuera = false;
    programarCursor();
  }
  function alSalir(e) {
    // mouseout sube desde cada elemento; solo cuenta al salir de la ventana (sin destino).
    if (destruido || !e || e.relatedTarget || e.toElement) return;
    fuera = true;
    programarCursor();
  }
  function alClic() {
    if (destruido || pausado || !m || !listo || !cfg.clicToca) return;
    enviarCursor();                                 // hit-test con la última lectura del motor
    if (sobreModelo) { try { m.tocar(); } catch (e) { /* sigue */ } }
  }

  // ── Tamaño ──
  function reencuadrar() {
    if (destruido || !m) return;
    try { m.encuadrar(cfg.encuadre); } catch (e) { /* sigue */ }
    cara = null;
    enviarCursor();
  }
  function programarEncuadre() {
    if (destruido || pausado || !m) return;
    if (ventana && typeof ventana.requestAnimationFrame === 'function') {
      if (!rafEncuadre) rafEncuadre = ventana.requestAnimationFrame(() => { rafEncuadre = 0; reencuadrar(); });
    } else reencuadrar();
  }

  // ── Contexto WebGL ──
  function extensionPerdida() {
    try {
      const r = m && m.ctx && m.ctx.renderer;
      const gl = r && typeof r.getContext === 'function' ? r.getContext() : null;
      if (!gl || (typeof gl.isContextLost === 'function' && gl.isContextLost())) return null;
      return gl.getExtension('WEBGL_lose_context') || null;
    } catch (e) { return null; }
  }
  // Lleva el contexto al estado deseado. restoreContext solo vale DESPUÉS de que se
  // despache 'webglcontextlost' (three hace preventDefault ahí); por eso las
  // transiciones esperan a sus eventos y se reintenta con diferir().
  function sincronizarContexto() {
    if (destruido || !m) return;
    const quiero = pausado && cfg.liberarAlPausar ? 'perdido' : 'vivo';
    if (quiero === 'perdido' && ctxEstado === 'vivo') {
      ext = ext || extensionPerdida();
      if (!ext) return;                             // sin la extensión: solo FPS 0
      ctxEstado = 'perdiendo';
      try { ext.loseContext(); } catch (e) { ctxEstado = 'vivo'; }
    } else if (quiero === 'vivo' && ctxEstado === 'perdido' && ext) {
      ctxEstado = 'restaurando';
      try { ext.restoreContext(); } catch (e) { ctxEstado = 'perdido'; fallar('No se pudo restaurar el contexto WebGL.'); }
    }
  }
  function alPerderContexto() {
    if (destruido) return;
    ctxEstado = 'perdido';
    avisar('contexto', 'perdido');
    diferir(sincronizarContexto);
  }
  function alRestaurarContexto() {
    if (destruido) return;
    ctxEstado = 'vivo'; cara = null;
    avisar('contexto', 'vivo');
    diferir(sincronizarContexto);
  }

  // ── Parámetros ──
  function aplicarParams(entrada) {
    if (!m) { paramsPend.push(entrada); return { pendiente: true }; }
    if (typeof m.luneParams === 'function') {                  // el motor trae su lista blanca
      try { return m.luneParams(entrada); } catch (e) { aviso('luneParams', e && e.message); return null; }
    }
    const P = m.PARAMS;
    if (!P) return null;
    let aplicados;
    if (typeof opts.validarParams === 'function') {
      try { aplicados = opts.validarParams(entrada) || {}; } catch (e) { aviso('validarParams', e && e.message); return null; }
    } else {
      const r = filtrarParams(P, entrada);
      if (r.error) aviso('luneParams', r.error);
      aplicados = r.aplicados;
    }
    const antes = { fov: P.fov, invertirEjes: P.invertirEjes };
    Object.assign(P, aplicados);
    const cam = m.ctx && m.ctx.camera;
    if ('fov' in aplicados && P.fov !== antes.fov && cam) {
      try { cam.fov = P.fov; cam.updateProjectionMatrix && cam.updateProjectionMatrix(); m.encuadrar(cfg.encuadre); } catch (e) { /* sigue */ }
      cara = null;
    }
    // Los ejes del rig se miden al cargar: hay que recargar el modelo para aplicarlos.
    if ('invertirEjes' in aplicados && P.invertirEjes !== antes.invertirEjes && url) {
      try { m.cargar(urlConVersion(url, version)); } catch (e) { /* sigue */ }
    }
    return aplicados;
  }

  // ── Bus de módulos del motor ──
  function registrarEnMotor(instalar) {
    if (!m || typeof m.registrar !== 'function') return null;
    try { return m.registrar(instalar) || null; } catch (e) { aviso('registrar', e && e.message); return null; }
  }
  function llamarMod(nombre, metodo, args) {
    if (!m || typeof m.mod !== 'function') return undefined;
    try { return m.mod(nombre, metodo, ...args); } catch (e) { aviso('mod', nombre, metodo, e && e.message); return undefined; }
  }

  // ── Listeners ──
  const opcPasivo = { passive: true };
  if (ventana && typeof ventana.addEventListener === 'function') {
    ventana.addEventListener('mousemove', alMover, opcPasivo);
    ventana.addEventListener('mouseout', alSalir, opcPasivo);
  }
  if (canvas && typeof canvas.addEventListener === 'function') {
    canvas.addEventListener('click', alClic);
    canvas.addEventListener('webglcontextlost', alPerderContexto);
    canvas.addEventListener('webglcontextrestored', alRestaurarContexto);
  }
  const RO = ventana && ventana.ResizeObserver;
  if (typeof RO === 'function' && canvas) {
    try { ro = new RO(() => programarEncuadre()); ro.observe(canvas); } catch (e) { ro = null; }
  }

  function quitarListeners() {
    if (ventana && typeof ventana.removeEventListener === 'function') {
      ventana.removeEventListener('mousemove', alMover, opcPasivo);
      ventana.removeEventListener('mouseout', alSalir, opcPasivo);
      if (typeof ventana.cancelAnimationFrame === 'function') {
        if (rafCursor) ventana.cancelAnimationFrame(rafCursor);
        if (rafEncuadre) ventana.cancelAnimationFrame(rafEncuadre);
      }
    }
    rafCursor = 0; rafEncuadre = 0;
    if (canvas && typeof canvas.removeEventListener === 'function') {
      canvas.removeEventListener('click', alClic);
      canvas.removeEventListener('webglcontextlost', alPerderContexto);
      canvas.removeEventListener('webglcontextrestored', alRestaurarContexto);
    }
    if (ro) { try { ro.disconnect(); } catch (e) { /* sigue */ } ro = null; }
  }

  // ── Handle ──
  const handle = {
    /** Cara/gesto de lune_vrm.js (normal, happy, thinking, sleeping…). Antes de 'listo' se guarda. */
    setEstado(e) {
      estado = String(e || 'normal').toLowerCase();
      if (m && listo && !destruido) { try { m.setEstado(estado); } catch (err) { /* sigue */ } }
    },
    /** Boca (visemas) mientras suena la voz. */
    setHablando(on) {
      hablando = !!on;
      if (m && !destruido) { try { m.setHablando(hablando); } catch (err) { /* sigue */ } }
    },
    /** FPS 0 y (con liberarAlPausar) suelta el contexto WebGL; pausar(false) lo recupera. → bool */
    pausar(on = true) {
      on = !!on;
      if (destruido || on === pausado) return pausado;
      pausado = on;
      if (on) {
        if (ventana && typeof ventana.cancelAnimationFrame === 'function') {
          if (rafCursor) ventana.cancelAnimationFrame(rafCursor);
          if (rafEncuadre) ventana.cancelAnimationFrame(rafEncuadre);
        }
        rafCursor = 0; rafEncuadre = 0;
        if (m) { try { m.setFPS(0); } catch (err) { /* sigue */ } }
      } else if (!m) {
        arrancar();
      } else {
        try { m.setFPS(cfg.fps); } catch (err) { /* sigue */ }
        programarEncuadre();
        enviarCursor();
      }
      sincronizarContexto();
      return pausado;
    },
    /** Otro modelo en el mismo contexto (cambio de personaje). `v` = versión (?v=). → bool */
    cargar(nuevaUrl, v) {
      if (destruido) return false;
      const u = String(nuevaUrl || '');
      if (!u) return false;
      url = u;
      if (v !== undefined) version = v;
      listo = false;
      if (m) { try { m.cargar(urlConVersion(url, version)); } catch (err) { fallar(err && err.message); return false; } }
      else arrancar();
      return true;
    },
    /** Calibración del modelo: lista blanca sobre PARAMS (o la del motor, si la trae). */
    luneParams(json) {
      if (destruido) return null;
      return aplicarParams(json);
    },
    /** 'retrato' | 'cuerpo' */
    encuadrar(modo) {
      cfg.encuadre = modo === 'cuerpo' ? 'cuerpo' : 'retrato';
      if (m && !destruido) reencuadrar();
      return cfg.encuadre;
    },
    /** Alimenta el cursor a mano (px cliente), p. ej. desde un pointermove propio. */
    cursor(x, y) {
      if (destruido || !finito(x) || !finito(y)) return false;
      raton = { x, y }; fuera = false;
      enviarCursor();
      return sobreModelo;
    },
    /** Registra un módulo en el bus del motor (instalar(ctx) | módulo). Sin motor todavía,
     *  se encola (sin repetir) y se registra al crearlo. → el módulo registrado o null. */
    registrar(instalar) {
      if (destruido || !instalar) return null;
      if (m) return registrarEnMotor(instalar);
      if (!instaladores.includes(instalar)) instaladores.push(instalar);
      return null;
    },
    /** API de un módulo del bus: h.mod('baileProc', 'bailar', true, opts). Sin motor, se
     *  encola (las MAX_COLA_MOD últimas) y se llama después de los registros pendientes. */
    mod(nombre, metodo, ...args) {
      if (destruido) return undefined;
      if (m) return llamarMod(nombre, metodo, args);
      colaMod.push([nombre, metodo, args]);
      if (colaMod.length > MAX_COLA_MOD) colaMod.shift();
      return undefined;
    },
    /** Carga (import perezoso) y registra el módulo RUTAS_MODULOS[nombre] una vez, instalado con
     *  `opciones` (por defecto OPCIONES_MODULOS[nombre]). → Promise<bool> */
    usarModulo(nombre, { importar, opciones } = {}) {
      if (destruido) return Promise.resolve(false);
      if (modulosUsados.has(nombre)) return modulosUsados.get(nombre);
      const opc = opciones !== undefined ? opciones : (OPCIONES_MODULOS[nombre] || null);
      const p = cargarModulo(nombre, importar).then((mod) => {
        const inst = mod && (typeof mod.instalar === 'function' ? mod.instalar
          : (mod.default && typeof mod.default.instalar === 'function' ? mod.default.instalar : null));
        if (!inst || destruido) { modulosUsados.delete(nombre); return false; }
        handle.registrar(opc ? (ctx) => inst(ctx, opc) : inst);
        return true;
      });
      modulosUsados.set(nombre, p);
      return p;
    },
    /** Libera modelo, listeners y contexto WebGL. Idempotente. → bool (true la primera vez) */
    destruir() {
      if (destruido) return false;
      destruido = true;
      quitarListeners();
      vivos.delete(handle);
      instaladores.length = 0; colaMod.length = 0;
      const mm = m;
      m = null; listo = false;
      liberarAsistente(mm);             // m.destruir() si lo trae (una sola vez); si no, el respaldo
      return true;
    },
    get listo() { return listo; },
    get pausado() { return pausado; },
    get destruido() { return destruido; },
    get estado() { return estado; },
    get url() { return url; },
    get contexto() { return ctxEstado; },
    get asistente() { return m; },
  };

  vivos.add(handle);
  arrancar();
  return handle;
}

/** Destruye un handle de crear(). → bool */
export function destruir(handle) {
  return !!(handle && typeof handle.destruir === 'function' && handle.destruir());
}

/** luneParams para todos los avatares vivos y los que se creen después. → resultados */
export function params(json) {
  paramsGlobales = json;
  return [...vivos].map((h) => h.luneParams(json));
}

/** Cambia el modelo de todos los avatares vivos (cambio de personaje). → cuántos */
export function recargar(url, v) {
  let n = 0;
  for (const h of vivos) if (h.cargar(url, v)) n++;
  return n;
}

/** Número de avatares vivos (no destruidos). */
export function activos() { return vivos.size; }

export const LuneVRMBarra = Object.freeze({
  crear, destruir, params, recargar, precargar, activos, cargarModulo,
  mapearCursor, urlConVersion, RUTA_MODELO, RUTAS_MODULOS, OPCIONES_MODULOS,
});

if (typeof window !== 'undefined' && window) {
  window.LuneVRMBarra = LuneVRMBarra;
  // sidebar.jsx (Babel) puede ejecutarse antes o después que este módulo: si aún
  // no ve window.LuneVRMBarra, que espere este evento.
  try { window.dispatchEvent(new Event('lune-vrm-barra')); } catch (e) { /* sin eventos */ }
}
