/*
 * ui_web/vrm/lune_modulos.js — bus de módulos del avatar VRM y utilidades de física.
 *
 * Para qué sirve: cada función nueva de la asistente 3D (idles, movimiento, sentarse,
 * baile, pantalla grande, comida…) vive en su propio archivo `ui_web/vrm/lune_*.js`
 * y se ENGANCHA a lune_vrm.js a través de este bus, en vez de editar todas el mismo
 * bucle de animación. lune_vrm.js crea el bus una vez (con 'idles' y 'movimiento'
 * ya registrados) y llama a los hooks en cada frame; los módulos no se conocen entre sí.
 *
 * No importa three: THREE (y todo lo del motor) llega por `ctx`. Así el archivo se
 * carga igual en el navegador que en Node (tests/js/modulos.test.mjs).
 *
 * Contrato de un módulo (lo devuelve `instalar(ctx)` de cada archivo):
 *   {
 *     nombre: 'baileProc', orden: 40,        // orden ascendente; empate = orden de registro
 *     alCargar(vrm) {}, alDescargar() {},
 *     pose(out, dt, t, est) {},              // suma rotaciones aditivas en `out` (ver sumar/mezclarPoses)
 *     trasPose(dt, t, est) {},               // tras rotation.set y antes de vrm.update
 *     expresiones(set, dt, t, est) {},       // set(nombre, peso, 'max'|'sobre') en cada frame
 *     trasUpdate(dt, t, est) {},             // tras vrm.update y antes de render
 *     ocupado(est) { return false },         // true → no bajar a fpsReposo
 *     inhibe(est) { return {} },             // {idle, seguimiento, caricia, parpadeo, gesto} 0..1
 *     api: {}                                // window.luneMod('baileProc', 'metodo', ...args)
 *   }
 *
 * Bus:
 *   const bus = crearBus(ctx);
 *   bus.registrar(mod | instalar | {instalar})  → el módulo registrado (o null si no vale)
 *   bus.llamar(hook, ...args)                   → valores devueltos (sin undefined), en orden
 *   bus.api(nombre, metodo, ...args)            → lo que devuelva mod.api[metodo]
 *   bus.ocupado(est)                            → OR de los ocupado()
 *   bus.inhibe(est)                             → producto por clave de los inhibe()
 *   bus.quitar(nombre) · bus.lista() · bus.obtener(nombre) · bus.reactivar(nombre)
 *   bus.exponer(win, 'luneMod')                 → win.luneMod(nombre, metodo, ...args)
 *
 * Errores: un módulo que lanza no tumba el frame; se avisa una vez por hook con
 * ctx.emitir('error', …) y, a los 30 fallos, el módulo se desactiva.
 *
 * Utilidades (también las usa ui_web/anim/lune_anim_modulos.js):
 *   clamp, lerp, suav(dt, k), smoothstep, Muelle, smoothDamp (fórmula de Unity),
 *   Bolsa (azar sin repetir), crearAleatorio(semilla), sumar, mezclarPoses,
 *   interpolarPoses, emitirPorDefecto.
 */

/** Claves que devuelve inhibe(); cada una es un factor 0..1 que multiplica esa capa. */
export const FACTORES = Object.freeze(['idle', 'seguimiento', 'caricia', 'parpadeo', 'gesto']);

/** Hooks que llama lune_vrm.js en cada frame o al cambiar de modelo. */
export const HOOKS_VRM = Object.freeze(['alCargar', 'alDescargar', 'pose', 'trasPose', 'expresiones', 'trasUpdate']);

const ORDEN_DEFECTO = 50;
const MAX_FALLOS = 30;          // fallos de un módulo antes de desactivarlo
const MAX_COLA_EVENTOS = 200;   // mismo tope que ui_web/lune_eventos.js

// ── Matemática básica ──────────────────────────────────────────────────────────

const finito = Number.isFinite;

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;

/** Factor de un lerp exponencial independiente del fps: x += (obj - x) * suav(dt, k). */
export function suav(dt, k) {
  if (!finito(dt) || !finito(k) || dt <= 0 || k <= 0) return 0;
  return 1 - Math.exp(-k * dt);
}

/**
 * smoothstep(x) con x en 0..1, o smoothstep(borde0, borde1, x) como en GLSL.
 * Devuelve 0..1 con derivada nula en los extremos (para fundidos).
 */
export function smoothstep(a, b, x) {
  let t;
  if (b === undefined && x === undefined) t = a;
  else t = b === a ? (x < a ? 0 : 1) : (x - a) / (b - a);
  if (!finito(t)) return 0;
  t = clamp(t, 0, 1);
  return t * t * (3 - 2 * t);
}

// ── Muelle amortiguado ─────────────────────────────────────────────────────────

/**
 * Muelle amortiguado semi-implícito (AvatarSwayController de Mate-Engine).
 * f en Hz, zeta adimensional; `tope` limita la salida. Se integra en subpasos de
 * ≤ 1/120 s porque con dt grandes (pestaña frenada, 10 fps) el Euler diverge y
 * el modelo acabaría en NaN. Con dt, objetivo o estado no finitos no se rompe:
 * ignora el paso o se reinicia a 0.
 */
export class Muelle {
  constructor(f = 1, zeta = 0.5, tope = 90) {
    this.x = 0; this.v = 0; this.tope = tope;
    this.configurar(f, zeta);
  }

  configurar(f, zeta) {
    this.f = finito(f) ? Math.max(0.01, f) : 1;
    this.w = this.f * 2 * Math.PI;
    this.z = finito(zeta) ? Math.max(0, zeta) : 0.5;
    return this;
  }

  reiniciar(x = 0, v = 0) { this.x = finito(x) ? x : 0; this.v = finito(v) ? v : 0; return this; }

  paso(objetivo, dt) {
    if (!finito(dt) || dt <= 0) return this.x;
    if (!finito(objetivo)) objetivo = this.x;
    // Más de 2 s de golpe (suspensión, pestaña dormida): el muelle ya estaría en
    // reposo; se simulan 2 s como mucho para no hacer 100 000 subpasos.
    const tiempo = Math.min(dt, 2);
    const n = Math.max(1, Math.ceil(tiempo * 120 - 1e-9)), h = tiempo / n;
    const w2 = this.w * this.w, amort = 2 * this.z * this.w;
    for (let i = 0; i < n; i++) {
      const a = w2 * (objetivo - this.x) - amort * this.v;
      this.v += a * h;
      this.x += this.v * h;
    }
    if (!finito(this.x) || !finito(this.v)) { this.x = 0; this.v = 0; }
    this.x = clamp(this.x, -this.tope, this.tope);
    return this.x;
  }
}

// ── SmoothDamp (Unity) ─────────────────────────────────────────────────────────

/**
 * Mathf.SmoothDamp de Unity, literal. `ref` es un objeto {v} con la velocidad
 * (el `ref float currentVelocity` de C#); se modifica en sitio.
 *
 *   const sd = { v: 0 };
 *   x = smoothDamp(x, objetivo, sd, 0.3, dt);             // tiempoSuave en s
 *   x = smoothDamp(x, objetivo, sd, 0.3, dt, 2000);       // con velocidad máxima
 *
 * NaN-safe: si `actual` no es finito salta al objetivo; si dt <= 0 no se mueve.
 */
export function smoothDamp(actual, objetivo, ref, tiempoSuave, dt, velMax = Infinity) {
  if (!ref || typeof ref !== 'object') ref = { v: 0 };
  if (!finito(ref.v)) ref.v = 0;
  if (!finito(objetivo)) return finito(actual) ? actual : 0;
  if (!finito(actual)) { ref.v = 0; return objetivo; }
  if (!finito(dt) || dt <= 0) return actual;

  const suave = Math.max(0.0001, finito(tiempoSuave) ? tiempoSuave : 0.0001);
  const omega = 2 / suave;
  const x = omega * dt;
  const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  let cambio = actual - objetivo;
  const destinoOriginal = objetivo;
  const maxCambio = (velMax > 0 ? velMax : Infinity) * suave;
  cambio = clamp(cambio, -maxCambio, maxCambio);
  const destino = actual - cambio;
  const temp = (ref.v + omega * cambio) * dt;
  ref.v = (ref.v - omega * temp) * exp;
  let salida = destino + (cambio + temp) * exp;
  // Sin sobrepaso
  if ((destinoOriginal - actual > 0) === (salida > destinoOriginal)) {
    salida = destinoOriginal;
    ref.v = (salida - destinoOriginal) / dt;
  }
  return salida;
}

// ── Azar ───────────────────────────────────────────────────────────────────────

/** Generador determinista (mulberry32) → función () => [0, 1). Para tests y repeticiones. */
export function crearAleatorio(semilla = 1) {
  let a = (Number(semilla) >>> 0) || 0x9E3779B9;
  return function aleatorio() {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Bolsa de azar sin repetir: saca todos los elementos en orden barajado antes de
 * volver a empezar, y nunca repite el último de una tanda como primero de la
 * siguiente (si hay más de uno). `elementos` puede ser un número n (→ 0..n-1).
 *
 *   const b = new Bolsa(['a', 'b', 'c'], { semilla: 7 });   // o { aleatorio: fn }
 *   b.siguiente();
 */
export class Bolsa {
  constructor(elementos = [], { aleatorio = null, semilla } = {}) {
    this.aleatorio = typeof aleatorio === 'function' ? aleatorio
      : semilla !== undefined ? crearAleatorio(semilla) : Math.random;
    this.ultimo = undefined;
    this.cambiar(elementos);
  }

  /** Sustituye los elementos y vacía la tanda en curso. */
  cambiar(elementos) {
    if (typeof elementos === 'number') elementos = Array.from({ length: Math.max(0, elementos | 0) }, (_, i) => i);
    this.elementos = Array.isArray(elementos) ? elementos.slice() : [];
    this.pila = [];
    return this;
  }

  get quedan() { return this.pila.length; }

  _indice(n) {
    const r = Number(this.aleatorio());
    const i = Math.floor((finito(r) ? r : 0) * n);
    return clamp(i, 0, n - 1);
  }

  _rellenar() {
    const p = this.elementos.slice();
    for (let i = p.length - 1; i > 0; i--) {             // Fisher-Yates
      const j = this._indice(i + 1);
      const tmp = p[i]; p[i] = p[j]; p[j] = tmp;
    }
    // Se saca con pop(): el primero de la tanda es el último del array.
    if (p.length > 1 && p[p.length - 1] === this.ultimo) {
      const tmp = p[0]; p[0] = p[p.length - 1]; p[p.length - 1] = tmp;
    }
    this.pila = p;
  }

  siguiente() {
    if (!this.elementos.length) return undefined;
    if (!this.pila.length) this._rellenar();
    this.ultimo = this.pila.pop();
    return this.ultimo;
  }
}

// ── Poses (objetos {hueso: [x, y, z]} en radianes) ────────────────────────────

/** Suma una rotación a un hueso de la pose `out` (crea la entrada si falta). */
export function sumar(out, hueso, x = 0, y = 0, z = 0) {
  const r = out[hueso] || (out[hueso] = [0, 0, 0]);
  if (finito(x)) r[0] += x;
  if (finito(y)) r[1] += y;
  if (finito(z)) r[2] += z;
  return out;
}

/** out += pose · w (aditivo, como `mezclar` de lune_vrm.js). Ignora valores no finitos. */
export function mezclarPoses(out, pose, w = 1) {
  if (!out || !pose || !finito(w) || w <= 0) return out;
  for (const h in pose) {
    const p = pose[h];
    if (!p) continue;
    sumar(out, h, (p[0] || 0) * w, (p[1] || 0) * w, (p[2] || 0) * w);
  }
  return out;
}

/** Pose intermedia entre a y b (t 0..1) sobre la unión de huesos. Para fundidos entre gestos. */
export function interpolarPoses(a, b, t, out = {}) {
  a = a || {}; b = b || {};
  const k = finito(t) ? clamp(t, 0, 1) : 0;
  const huesos = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const h of huesos) {
    const pa = a[h] || [0, 0, 0], pb = b[h] || [0, 0, 0];
    out[h] = [lerp(pa[0] || 0, pb[0] || 0, k), lerp(pa[1] || 0, pb[1] || 0, k), lerp(pa[2] || 0, pb[2] || 0, k)];
  }
  return out;
}

// ── Eventos hacia Python ───────────────────────────────────────────────────────

/**
 * Emisor por defecto si ctx no trae `emitir`: usa window.luneEmitir (ui_web/lune_eventos.js)
 * o, si ese script no está, encola directamente en window.__luneEventos con el mismo formato.
 */
export function emitirPorDefecto(tipo, datos) {
  const g = globalThis;
  if (typeof g.luneEmitir === 'function') return g.luneEmitir(tipo, datos);
  if (!tipo) return false;
  if (!Array.isArray(g.__luneEventos)) g.__luneEventos = [];
  let d = null;
  try { const s = JSON.stringify(datos); d = s === undefined ? null : JSON.parse(s); } catch (e) { d = String(datos); }
  g.__luneEventos.push({ t: String(tipo), d, ts: Date.now() });
  const sobra = g.__luneEventos.length - MAX_COLA_EVENTOS;
  if (sobra > 0) g.__luneEventos.splice(0, sobra);
  return true;
}

// ── Registro genérico (lo comparten el bus VRM y el de la asistente animada) ────

/**
 * Registro de módulos ordenados. `ctx` se pasa a instalar() y a los avisos de error.
 * Si ctx no trae `emitir`, se le pone emitirPorDefecto (el mismo ctx llega a los módulos).
 */
export function crearRegistro(ctx = {}, { etiqueta = 'modulos' } = {}) {
  if (typeof ctx.emitir !== 'function') ctx.emitir = emitirPorDefecto;
  let entradas = [];            // copia al escribir: iterar es seguro aunque se registre en un hook
  let secuencia = 0;
  let cargado = { hay: false, args: [] };

  function avisar(entrada, hook, err, desactivado) {
    const mensaje = String((err && err.message) || err || 'error');
    try { console.warn(`[${etiqueta}] ${entrada.mod.nombre}.${hook}:`, mensaje); } catch (e) { /* sin consola */ }
    try { ctx.emitir('error', { modulo: entrada.mod.nombre, hook, mensaje: mensaje.slice(0, 300), desactivado: !!desactivado }); } catch (e) { /* sin canal */ }
  }

  function fallo(entrada, hook, err) {
    entrada.fallos += 1;
    if (!entrada.avisados.has(hook)) { entrada.avisados.add(hook); avisar(entrada, hook, err, false); }
    if (entrada.fallos >= MAX_FALLOS && entrada.activo) { entrada.activo = false; avisar(entrada, hook, err, true); }
  }

  function invocar(entrada, hook, args) {
    const f = entrada.mod[hook];
    if (typeof f !== 'function') return undefined;
    try { return f.apply(entrada.mod, args); } catch (err) { fallo(entrada, hook, err); return undefined; }
  }

  function buscar(nombre) { return entradas.find((e) => e.mod.nombre === nombre) || null; }

  function quitar(nombre) {
    const e = buscar(nombre);
    if (!e) return false;
    entradas = entradas.filter((x) => x !== e);
    if (cargado.hay) invocar(e, 'alDescargar', []);
    return true;
  }

  function registrar(mod) {
    if (typeof mod === 'function') {
      try { mod = mod(ctx); } catch (err) { avisar({ mod: { nombre: mod.name || '?' } }, 'instalar', err, true); return null; }
    } else if (mod && typeof mod.instalar === 'function' && typeof mod.nombre !== 'string') {
      try { mod = mod.instalar(ctx); } catch (err) { avisar({ mod: { nombre: '?' } }, 'instalar', err, true); return null; }
    }
    if (!mod || typeof mod !== 'object' || typeof mod.nombre !== 'string' || !mod.nombre) {
      avisar({ mod: { nombre: '?' } }, 'registrar', new Error('módulo sin nombre'), true);
      return null;
    }
    quitar(mod.nombre);          // mismo nombre = sustituir (recarga en caliente)
    const entrada = { mod, orden: finito(mod.orden) ? mod.orden : ORDEN_DEFECTO, seq: secuencia++, fallos: 0, avisados: new Set(), activo: true };
    entradas = [...entradas, entrada].sort((a, b) => (a.orden - b.orden) || (a.seq - b.seq));
    if (cargado.hay) invocar(entrada, 'alCargar', cargado.args);   // llega con el modelo ya cargado
    return mod;
  }

  function llamar(hook, ...args) {
    if (hook === 'alCargar') cargado = { hay: true, args };
    else if (hook === 'alDescargar') cargado = { hay: false, args: [] };
    const res = [];
    for (const e of entradas) {
      if (!e.activo) continue;
      const v = invocar(e, hook, args);
      if (v !== undefined) res.push(v);
    }
    return res;
  }

  function ocupado(est) {
    for (const e of entradas) {
      if (e.activo && typeof e.mod.ocupado === 'function' && invocar(e, 'ocupado', [est])) return true;
    }
    return false;
  }

  function inhibe(est, out = {}) {
    for (const k of FACTORES) out[k] = 1;
    for (const e of entradas) {
      if (!e.activo || typeof e.mod.inhibe !== 'function') continue;
      const r = invocar(e, 'inhibe', [est]);
      if (!r || typeof r !== 'object') continue;
      for (const k of FACTORES) {
        if (r[k] === undefined || r[k] === null) continue;
        const v = Number(r[k]);
        if (finito(v)) out[k] *= clamp(v, 0, 1);
      }
    }
    return out;
  }

  function api(nombre, metodo, ...args) {
    const e = buscar(nombre);
    const f = e && e.mod.api && e.mod.api[metodo];
    if (typeof f !== 'function') {
      try { console.warn(`[${etiqueta}] no existe ${nombre}.${metodo}`); } catch (err) { /* sin consola */ }
      return undefined;
    }
    try { return f.apply(e.mod.api, args); } catch (err) { fallo(e, 'api.' + metodo, err); return undefined; }
  }

  function reactivar(nombre) {
    const e = buscar(nombre);
    if (!e) return false;
    e.activo = true; e.fallos = 0; e.avisados.clear();
    return true;
  }

  function exponer(win = globalThis, global = 'luneMod') {
    win[global] = (nombre, metodo, ...args) => api(nombre, metodo, ...args);
    return win[global];
  }

  return {
    ctx, registrar, quitar, llamar, ocupado, inhibe, api, reactivar, exponer,
    lista: () => entradas.map((e) => e.mod.nombre),
    obtener: (nombre) => { const e = buscar(nombre); return e ? e.mod : null; },
    activo: (nombre) => { const e = buscar(nombre); return !!(e && e.activo); },
  };
}

/**
 * Bus de módulos del avatar VRM. ctx = {THREE, vrm(), camera, scene, renderer, canvas,
 * huesos, PARAMS, sXZ, proyectar(v3)→{x,y}, emitir(evento, datos), encuadrar(modo, temporal),
 * setFPS(n), setPixelRatio(r), setLookAt(on), estado(), tieneExpr(nombre)→bool}.
 * est = {drag, dragPeso, dragVx, dragVy (px/s de pantalla, Y hacia abajo, sin filtrar;
 * 0 sin arrastre), dormida, sleepBlend, gesto, gestoPeso, hablando, inactivo (s desde la
 * última actividad), inh (factores del frame de inhibe()), baile, sentada, grande,
 * comiendo, menu, cursor:{px,py,nx,ny}}.
 * lune_vrm.js registra de serie 'idles' (lune_idles.js) y 'movimiento' (lune_movimiento.js).
 */
export function crearBus(ctx = {}) {
  return crearRegistro(ctx, { etiqueta: 'luneMod' });
}
