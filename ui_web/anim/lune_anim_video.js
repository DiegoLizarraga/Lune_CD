/*
 * ui_web/anim/lune_anim_video.js — clips de la asistente animada con DOBLE BÚFER.
 *
 * Para qué sirve: antes, cambiar de emoción en companion.html cambiaba el `src` del
 * único <video> y la asistente daba un salto (pantallazo del primer frame o un negro
 * mientras cargaba). Este módulo del registro (ui_web/anim/lune_anim_modulos.js)
 * usa DOS vídeos apilados (#va y #vb):
 *
 *   1. carga el clip nuevo en el vídeo oculto;
 *   2. espera a 'canplay' (si en 800 ms no llega, o da error, cae al respaldo:
 *      `composed` para todas las emociones);
 *   3. cruza la opacidad: 250 ms por defecto, 500 ms hacia el idle (`composed`),
 *      450 ms hacia `sad`/`bored` (y 500 ms hacia el clip de dormir);
 *   4. al acabar libera el decodificador del saliente: pause + removeAttribute('src') + load().
 *
 * Una petición que llega a mitad de un fundido espera a que acabe (gana la última);
 * una que llega mientras se carga otra reutiliza el vídeo oculto (no se ve nada).
 *
 * Además:
 *   - Rotación de idles: si assets/asistente/anime-videos/idles.json lista dos o más
 *     clips idle, con la asistente en `normal` cambia de uno a otro cada 12–18 s
 *     (Bolsa sin repetir). Sin json, o con uno solo, no hace nada.
 *     Formato: ["composed", "composed-2"] o {"idles": [...]}; cada entrada es un
 *     nombre (→ lune-<nombre>.webm) o un archivo .webm de esa carpeta.
 *   - Dormir: el estado `sleeping` usa lune-sleeping.webm si existe; si no, `bored`
 *     a 0.6x con filter brightness(.75) (clase .lune-sueno-sustituto) y zzz.
 *   - Capas de emoción: otros módulos (lune_anim_fisica.js: arrastre, mareo, dormir)
 *     no pisan la emoción que pone Python: fijan una CAPA con prioridad en
 *     `est.capasEmocion` (fijarCapa/quitarCapa) y aquí se muestra la de más prioridad,
 *     o la emoción base si no hay ninguna. Al quitar la capa vuelve la base.
 *
 * Contrato con la página (lo aplica la integración en companion.html):
 *   <div id="stage"><video id="va" class="lune-vid" muted loop playsinline preload="auto"></video>
 *                   <video id="vb" class="lune-vid" muted loop playsinline preload="auto"></video></div>
 *   + <link rel="stylesheet" href="css/asistente_anim.css">
 *   reg.registrar(instalar);  window.setEmocion = (s) => reg.emocion(s);   (o publicar(window, reg))
 * Si solo existe el <video id="v"> de siempre, se usa como #va y se crea #vb a su lado.
 * Al instalarse pone .lune-doble en el stage (el CSS solo oculta el vídeo inactivo con
 * esa clase) y quita el `onerror` que el script clásico pusiera en los vídeos.
 *
 * Este módulo sustituye ctx.video() por el vídeo VISIBLE en cada momento, para que
 * otros módulos (captura de frame, pausa…) no tengan que saber del doble búfer.
 *
 * En la página: window.luneMod('video', 'estado') → {base, efectiva, clip, …};
 * luneMod('video', 'pausar', true|false); luneMod('video', 'idles', [...]).
 *
 * Sin DOM real en los tests: los vídeos, el temporizador y la carga del json se
 * inyectan (tests/js/anim_video.test.mjs).
 */
import { Bolsa, clamp } from './lune_anim_modulos.js';

export const NOMBRE = 'video';
export const ORDEN = 10;

/** Carpeta de los clips, relativa a ui_web/ (la sirve el http local de companion.py). */
export const CARPETA = 'assets/asistente/anime-videos/';

/** Estado de la asistente → clip (lune-<clip>.webm). Lo que no esté cae al idle. */
export const MAPA = Object.freeze({
  normal: 'composed', thinking: 'thinking', happy: 'happy', angry: 'angry', error: 'angry',
  surprised: 'surprised', nervous: 'nervous', wave: 'wave', dismiss: 'dismiss',
  sad: 'sad', curious: 'curious', reading: 'curious',
  typing: 'working', working: 'working', listening: 'listening', talking: 'talking',
  laughing: 'laughing', bored: 'bored', sleeping: 'sleeping',
  dizzy: 'nervous',                     // mareo (lune_anim_fisica.js): no hay clip propio
});

export const CLIP_IDLE = 'composed';
export const CLIP_DORMIR = 'sleeping';

/** Duraciones del fundido (ms) según el clip de destino. */
export const FUNDIDO = Object.freeze({ defecto: 250, idle: 500, triste: 450, dormir: 500 });

/** Si el clip no está listo en este tiempo, se pasa al respaldo. */
export const ESPERA_CARGA_MS = 800;

/** Cada cuánto rota el idle (s, al azar entre los dos). */
export const ROTACION_IDLE_S = Object.freeze([12, 18]);

/** Sustituto de dormir si no hay lune-sleeping.webm: `bored` lento y más oscuro. */
export const SUENO_SUSTITUTO = Object.freeze({ clip: 'bored', velocidad: 0.6 });

/** Prioridades de las capas conocidas (más alta = gana). */
export const PRIORIDAD_CAPA = Object.freeze({ dormir: 40, arrastre: 80, mareo: 90 });

const NOMBRE_OK = /^[A-Za-z0-9_-]{1,64}$/;
const ARCHIVO_OK = /^[A-Za-z0-9_.-]{1,96}\.webm$/i;
const tiene = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);

// ── Lógica pura ────────────────────────────────────────────────────────────────

/** Nombre del clip para un estado (siempre uno válido; lo desconocido → composed). */
export function clipDe(estado, mapa = MAPA) {
  const k = String(estado ?? '').trim().toLowerCase();
  const c = tiene(mapa, k) ? mapa[k] : null;
  return typeof c === 'string' && NOMBRE_OK.test(c) ? c : CLIP_IDLE;
}

/** Ruta del clip: <carpeta>lune-<clip>.webm */
export function srcDe(clip, carpeta = CARPETA) {
  return `${carpeta}lune-${clip}.webm`;
}

/**
 * Milisegundos del fundido hacia `hacia` (nombre del clip de destino):
 * 500 hacia el idle (composed o un idle de la rotación), 450 hacia sad/bored,
 * 500 hacia el clip de dormir y 250 para todo lo demás.
 */
export function duracionFundido(hacia, { idle = false } = {}) {
  const c = String(hacia ?? '');
  if (idle || c === CLIP_IDLE) return FUNDIDO.idle;
  if (c === 'sad' || c === 'bored') return FUNDIDO.triste;
  if (c === CLIP_DORMIR) return FUNDIDO.dormir;
  return FUNDIDO.defecto;
}

/** Nombre del clip a partir de su ruta ('…/lune-happy.webm' → 'happy'). */
export function clipDeSrc(src) {
  const m = /(?:^|\/)(?:lune-)?([^/]+?)\.webm(?:[?#].*)?$/i.exec(String(src ?? ''));
  return m ? m[1] : '';
}

/**
 * Lista de idles de idles.json → rutas únicas y seguras dentro de `carpeta`.
 * Acepta un array o {idles: [...]}; cada entrada es un nombre ('composed-2') o un
 * archivo ('lune-composed-2.webm'). Nada de rutas, '..' ni URLs.
 */
export function normalizarIdles(json, carpeta = CARPETA) {
  const lista = Array.isArray(json) ? json : (json && Array.isArray(json.idles) ? json.idles : []);
  const out = [];
  for (const x of lista) {
    const s = String(x ?? '').trim();
    let src = null;
    if (ARCHIVO_OK.test(s) && !s.includes('..')) src = carpeta + s;
    else if (NOMBRE_OK.test(s)) src = srcDe(s, carpeta);
    if (src && !out.includes(src)) out.push(src);
  }
  return out;
}

/**
 * Candidatos en orden para mostrar `estado`: el principal y sus respaldos.
 * Cada uno: {estado, clip, src, velocidad, sustituto, idle, fundido}.
 *   sleeping → [lune-sleeping, bored a 0.6x (sustituto), composed]
 *   normal   → [idle de la rotación (si hay), composed]
 *   otro     → [su clip, composed]
 * Se saltan los que ya se sabe que faltan (dieron error) y los repetidos.
 */
export function candidatos(estado, { mapa = MAPA, carpeta = CARPETA, idle = null, faltan = null } = {}) {
  const e = String(estado ?? 'normal') || 'normal';
  const clip = clipDe(e, mapa);
  const lista = [];
  const poner = (c, extra = {}) => {
    const src = extra.src || srcDe(c, carpeta);
    const esIdle = !!extra.idle || c === CLIP_IDLE;
    lista.push({
      estado: e, clip: c, src, velocidad: extra.velocidad || 1, sustituto: !!extra.sustituto,
      idle: esIdle, fundido: duracionFundido(c, { idle: esIdle }),
    });
  };
  if (clip === CLIP_DORMIR) {
    poner(CLIP_DORMIR);
    poner(SUENO_SUSTITUTO.clip, { velocidad: SUENO_SUSTITUTO.velocidad, sustituto: true });
  } else if (clip === CLIP_IDLE && idle) {
    poner(clipDeSrc(idle) || CLIP_IDLE, { src: idle, idle: true });
  } else {
    poner(clip);
  }
  poner(CLIP_IDLE);
  const vistos = new Set();
  return lista.filter((c) => {
    const k = `${c.src}@${c.velocidad}`;
    if (vistos.has(k) || (faltan && faltan.has(c.src))) return false;
    vistos.add(k);
    return true;
  });
}

// ── Capas de emoción (las usan otros módulos) ─────────────────────────────────

/**
 * Fija una capa de emoción en `est.capasEmocion` (la de más prioridad manda sobre la
 * emoción base). estado null/'' la quita. Prioridad por defecto: PRIORIDAD_CAPA[capa] o 50.
 */
export function fijarCapa(est, capa, estado, prioridad) {
  if (!est || !capa) return;
  if (estado === null || estado === undefined || estado === '') { quitarCapa(est, capa); return; }
  const capas = est.capasEmocion && typeof est.capasEmocion === 'object' ? est.capasEmocion : (est.capasEmocion = {});
  const p = Number.isFinite(prioridad) ? prioridad : (tiene(PRIORIDAD_CAPA, capa) ? PRIORIDAD_CAPA[capa] : 50);
  const prev = capas[capa];
  if (prev && prev.estado === String(estado) && prev.prioridad === p) return;
  capas[capa] = { estado: String(estado), prioridad: p };
}

export function quitarCapa(est, capa) {
  if (est && est.capasEmocion && tiene(est.capasEmocion, capa)) delete est.capasEmocion[capa];
}

/** La emoción que se ve: la capa de más prioridad (empate: la primera fijada) o la base. */
export function emocionEfectiva(base, capas) {
  let mejor = null;
  if (capas && typeof capas === 'object') {
    for (const k of Object.keys(capas)) {
      const c = capas[k];
      if (!c || !c.estado) continue;
      const p = Number.isFinite(c.prioridad) ? c.prioridad : 50;
      if (!mejor || p > mejor.p) mejor = { p, estado: c.estado };
    }
  }
  return mejor ? mejor.estado : (String(base || '') || 'normal');
}

// ── Utilidades DOM (toleran elementos falsos) ─────────────────────────────────

function clase(el, nombre, on) {
  if (!el || !el.classList) return;
  if (on) el.classList.add(nombre); else el.classList.remove(nombre);
}

function varCSS(el, nombre, valor) {
  if (!el || !el.style) return;
  if (typeof el.style.setProperty === 'function') el.style.setProperty(nombre, valor);
  else el.style[nombre] = valor;
}

function atributo(el, nombre, valor) {
  if (!el) return;
  if (valor === null || valor === undefined) { if (typeof el.removeAttribute === 'function') el.removeAttribute(nombre); }
  else if (typeof el.setAttribute === 'function') el.setAttribute(nombre, String(valor));
}

function reproducir(el) {
  if (!el || typeof el.play !== 'function') return;
  try { const p = el.play(); if (p && typeof p.catch === 'function') p.catch(() => {}); } catch (e) { /* autoplay bloqueado */ }
}

function velocidad(el, v) {
  if (!el) return;
  try { el.defaultPlaybackRate = v; el.playbackRate = v; } catch (e) { /* sin soporte */ }
}

/** Crea (una vez) el contenedor de los zzz dentro del stage. Devuelve el elemento o null. */
export function asegurarZzz(stage, doc = null) {
  if (!stage) return null;
  const d = doc || stage.ownerDocument || globalThis.document;
  const hay = typeof stage.querySelector === 'function' ? stage.querySelector('.lune-zzz') : null;
  if (hay) return hay;
  if (!d || typeof d.createElement !== 'function' || typeof stage.appendChild !== 'function') return null;
  const zzz = d.createElement('div');
  zzz.className = 'lune-zzz';
  atributo(zzz, 'aria-hidden', 'true');
  for (const letra of ['z', 'z', 'Z']) {
    const s = d.createElement('span');
    s.textContent = letra;
    zzz.appendChild(s);
  }
  stage.appendChild(zzz);
  return zzz;
}

/**
 * Los dos vídeos: #va y #vb; si solo está el #v de siempre (o el primer <video> del
 * stage), se usa como A y se crea B a su lado con los mismos atributos.
 */
export function buscarVideos(stage, doc) {
  const porId = (id) => (doc && typeof doc.getElementById === 'function' ? doc.getElementById(id) : null);
  let a = porId('va'), b = porId('vb');
  if (!a) a = porId('v') || (stage && typeof stage.querySelector === 'function' ? stage.querySelector('video') : null);
  if (a && !b && doc && typeof doc.createElement === 'function' && a.parentNode) {
    b = doc.createElement('video');
    b.id = 'vb';
    for (const k of ['muted', 'loop', 'playsinline']) atributo(b, k, '');
    atributo(b, 'preload', 'auto');
    a.parentNode.insertBefore(b, a.nextSibling || null);
  }
  for (const v of [a, b]) {
    if (!v) continue;
    clase(v, 'lune-vid', true);
    try { v.muted = true; v.loop = true; v.playsInline = true; } catch (e) { /* elemento falso */ }
  }
  return [a, b];
}

// ── Doble búfer ───────────────────────────────────────────────────────────────

/**
 * Controlador de los dos <video>. No sabe de emociones: recibe listas de candidatos
 * (ver candidatos()) y enseña el primero que cargue.
 *   mostrar(lista)  pide mostrar lista[0] (con respaldo lista[1..]); → bool
 *   activo()        vídeo visible (o null) · actual() candidato visible
 *   cargando() · fundiendo() · faltan (Set de src que dieron error)
 *   pausar(on)      pausa/reanuda el visible (el que entra no se reproduce en pausa)
 * `alMostrar(candidato)` se llama al empezar cada fundido.
 */
export function crearDobleBufer({ a = null, b = null, temporizador = null, esperaMs = ESPERA_CARGA_MS, alMostrar = null } = {}) {
  const g = globalThis;
  const tm = temporizador || {
    setTimeout: (f, ms) => g.setTimeout(f, ms),
    clearTimeout: (id) => g.clearTimeout(id),
  };
  const faltan = new Set();
  let activo = null, actual = null;
  let carga = null;       // {tk, lista, i, el, obj, quitar()}
  let fundido = null;     // {timer, saliente}
  let siguiente = null;   // lista pedida durante un fundido (gana la última)
  let token = 0;
  let pausado = false;

  // Si la página ya puso un clip en A (el setEmocion clásico), se adopta como visible.
  for (const el of [a, b]) {
    const src = el && typeof el.getAttribute === 'function' ? el.getAttribute('src') : null;
    if (src && !activo) {
      activo = el;
      const clip = clipDeSrc(src);
      actual = { estado: '', clip, src, velocidad: 1, sustituto: false, idle: clip === CLIP_IDLE, fundido: 0 };
      clase(el, 'activo', true);
    }
  }

  const libre = () => (activo === a ? b : a);

  function aplicarModo(el, obj) {
    velocidad(el, obj.velocidad || 1);
    clase(el, 'lune-sueno-sustituto', !!obj.sustituto);
  }

  function liberar(el) {
    if (!el) return;
    try { if (typeof el.pause === 'function') el.pause(); } catch (e) { /* ya parado */ }
    atributo(el, 'src', null);
    try { if (typeof el.load === 'function') el.load(); } catch (e) { /* suelta el decodificador */ }
    clase(el, 'activo', false);
    clase(el, 'saliendo', false);
    clase(el, 'lune-sueno-sustituto', false);
    velocidad(el, 1);
  }

  function cancelarCarga() {
    if (!carga) return;
    const c = carga;
    carga = null;
    c.quitar();
    liberar(c.el);
  }

  function terminarFundido() {
    const f = fundido;
    fundido = null;
    if (f && f.saliente && f.saliente !== activo) liberar(f.saliente);
    if (siguiente) { const l = siguiente; siguiente = null; mostrar(l); }
  }

  function iniciarFundido(el, obj) {
    const saliente = activo;
    const ms = Math.max(0, Number(obj.fundido) || 0);
    aplicarModo(el, obj);
    varCSS(el, '--lune-fundido', `${ms}ms`);
    if (saliente) varCSS(saliente, '--lune-fundido', `${ms}ms`);
    clase(el, 'saliendo', false);
    clase(el, 'activo', true);
    if (saliente) { clase(saliente, 'activo', false); clase(saliente, 'saliendo', true); }
    if (!pausado) reproducir(el);
    activo = el; actual = obj;
    if (typeof alMostrar === 'function') { try { alMostrar(obj); } catch (e) { /* la página sigue */ } }
    // Margen de 40 ms para que la transición CSS termine antes de soltar el saliente.
    fundido = { saliente, timer: tm.setTimeout(terminarFundido, ms + 40) };
  }

  function cargar(lista, i) {
    const obj = lista[i];
    if (!obj) return false;                              // sin más respaldos: se queda lo que había
    if (actual && obj.src === actual.src) {              // el respaldo ya se está viendo
      aplicarModo(activo, obj);
      const cambio = actual.sustituto !== obj.sustituto || actual.estado !== obj.estado;
      actual = obj;
      if (cambio && typeof alMostrar === 'function') { try { alMostrar(obj); } catch (e) { /* nada */ } }
      return true;
    }
    const el = libre();
    if (!el) return false;
    const tk = ++token;
    liberar(el);
    aplicarModo(el, obj);
    atributo(el, 'src', obj.src);
    try { if (typeof el.load === 'function') el.load(); } catch (e) { /* lo cubre el tiempo de espera */ }
    const ok = () => listo(tk);
    const mal = () => falla(tk, true);
    if (typeof el.addEventListener === 'function') {
      el.addEventListener('canplay', ok);
      el.addEventListener('error', mal);
    }
    const timer = tm.setTimeout(() => falla(tk, false), esperaMs);
    carga = {
      tk, lista, i, el, obj,
      quitar() {
        if (typeof el.removeEventListener === 'function') {
          el.removeEventListener('canplay', ok);
          el.removeEventListener('error', mal);
        }
        tm.clearTimeout(timer);
      },
    };
    return true;
  }

  function listo(tk) {
    if (!carga || carga.tk !== tk) return;
    const c = carga;
    carga = null;
    c.quitar();
    iniciarFundido(c.el, c.obj);
  }

  // Error (el archivo no existe o no se decodifica) → se recuerda y se prueba el
  // siguiente; tiempo agotado → también el siguiente, pero sin marcarlo (quizá el
  // disco iba lento y la próxima vez sí carga).
  function falla(tk, esError) {
    if (!carga || carga.tk !== tk) return;
    const c = carga;
    carga = null;
    c.quitar();
    if (esError) faltan.add(c.obj.src);
    liberar(c.el);
    cargar(c.lista, c.i + 1);
  }

  function mostrar(lista) {
    if (!Array.isArray(lista) || !lista.length) return false;
    if (fundido) { siguiente = lista; return true; }
    const obj = lista[0];
    if (actual && obj.src === actual.src) { cancelarCarga(); return cargar(lista, 0); }
    if (carga && carga.obj.src === obj.src && carga.i === 0) {
      carga.lista = lista; carga.obj = obj;              // misma carga en curso: solo el modo
      aplicarModo(carga.el, obj);
      return true;
    }
    cancelarCarga();
    return cargar(lista, 0);
  }

  function pausar(on) {
    pausado = !!on;
    if (!activo) return;
    if (pausado) { try { activo.pause(); } catch (e) { /* nada */ } } else reproducir(activo);
  }

  return {
    mostrar, pausar, faltan,
    activo: () => activo,
    actual: () => actual,
    cargando: () => !!carga,
    fundiendo: () => !!fundido,
    pausado: () => pausado,
    /** Suelta todo (al descargar la página). */
    liberarTodo() {
      cancelarCarga();
      if (fundido) { tm.clearTimeout(fundido.timer); fundido = null; }
      siguiente = null;
      for (const el of [a, b]) liberar(el);
      activo = null; actual = null;
    },
  };
}

// ── Módulo del registro ───────────────────────────────────────────────────────

/** Lee un JSON (fetch sin caché); null si no existe o no se puede leer. */
async function cargarJSONPorDefecto(url) {
  const g = globalThis;
  if (typeof g.fetch !== 'function') return null;
  try {
    const r = await g.fetch(url, { cache: 'no-store' });
    if (!r || !r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

/**
 * instalar(ctx) para crearRegistroAnim().registrar(). `opciones` solo para tests o
 * páginas especiales: {videos:[a,b], carpeta, mapa, temporizador, cargarJSON,
 * aleatorio, rotacion:[min,max], esperaMs, documento}.
 */
export function instalar(ctx = {}, opciones = {}) {
  const {
    carpeta = CARPETA, mapa = MAPA, videos = null, temporizador = null,
    cargarJSON = cargarJSONPorDefecto, aleatorio = Math.random,
    rotacion = ROTACION_IDLE_S, esperaMs = ESPERA_CARGA_MS, documento = null,
  } = opciones;
  const stage = ctx.stage || null;
  const doc = documento || (stage && stage.ownerDocument) || globalThis.document || null;
  const [va, vb] = Array.isArray(videos) ? videos : buscarVideos(stage, doc);
  // El módulo es el dueño de los dos vídeos: fuera el onerror del script clásico de
  // companion.html (ponía el idle a mano en #v y competía con el respaldo de aquí).
  for (const v of [va, vb]) { if (v) { try { v.onerror = null; } catch (e) { /* elemento falso */ } } }
  // asistente_anim.css solo oculta los vídeos inactivos con .lune-doble en el stage: sin
  // esta clase los dos se veían a la vez y no había fundido.
  clase(stage, 'lune-doble', true);

  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;

  function alMostrar(obj) {
    atributo(stage, 'data-clip', obj.clip);
    if (obj.clip === CLIP_DORMIR || obj.sustituto) {
      asegurarZzz(stage, doc);
      atributo(stage, 'data-sueno', obj.sustituto ? 'sustituto' : 'clip');
    } else {
      atributo(stage, 'data-sueno', null);
    }
  }

  const buf = crearDobleBufer({ a: va, b: vb, temporizador, esperaMs, alMostrar });

  // Los demás módulos ven siempre el vídeo visible.
  const videoPrevio = typeof ctx.video === 'function' ? ctx.video : null;
  ctx.video = () => buf.activo() || (videoPrevio ? videoPrevio() : va);

  const azar = () => {
    const [mn, mx] = Array.isArray(rotacion) && rotacion.length === 2 ? rotacion : ROTACION_IDLE_S;
    const r = Number(aleatorio());
    return mn + (Number.isFinite(r) ? clamp(r, 0, 1) : 0.5) * (mx - mn);
  };

  let base = 'normal';
  let pedido = null;            // clave de lo último pedido (efectiva + idle)
  let efectiva = 'normal';
  let idles = [];
  let idleSrc = null;
  const bolsa = new Bolsa([], { aleatorio });
  let tIdle = azar();
  let idlesCargados = false;
  let pausaManual = false;

  function resolver(forzar = false) {
    efectiva = emocionEfectiva(base, est().capasEmocion);
    const conIdle = clipDe(efectiva, mapa) === CLIP_IDLE && idles.length >= 2 ? idleSrc : null;
    const clave = `${efectiva}|${conIdle || ''}`;
    if (!forzar && clave === pedido) return false;
    pedido = clave;
    return buf.mostrar(candidatos(efectiva, { mapa, carpeta, idle: conIdle, faltan: buf.faltan }));
  }

  // Igual que setEstado del VRM: 'sleeping' duerme sin tocar la emoción base y
  // cualquier otra que no sea 'normal' despierta.
  function setEmocion(nombre) {
    const n = String(nombre ?? '').trim() || 'normal';
    if (n === 'sleeping') fijarCapa(est(), 'dormir', 'sleeping');
    else {
      base = n;
      if (n !== 'normal') quitarCapa(est(), 'dormir');
    }
    return resolver();
  }

  function fijarIdles(lista) {
    idles = normalizarIdles(lista, carpeta);
    bolsa.cambiar(idles);
    idleSrc = idles.length >= 2 ? idles[0] : null;
    if (idleSrc) bolsa.ultimo = idleSrc;              // el primero ya se ve: la bolsa no lo repite
    tIdle = azar();
    resolver();
    return idles.length;
  }

  async function cargarIdles() {
    if (idlesCargados) return idles.length;
    idlesCargados = true;
    let json = null;
    try { json = await cargarJSON(`${carpeta}idles.json`); } catch (e) { json = null; }
    if (json) fijarIdles(json);
    return idles.length;
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,

    alIniciar() {
      if (!pausaManual) buf.pausar(false);
      return cargarIdles();
    },

    alDetener() { buf.pausar(true); },            // ventana oculta: no decodificar

    alEmocion(nombre) { setEmocion(nombre); },

    tick(dt, t, e) {
      resolver();                                  // capas nuevas (arrastre, dormir, mareo)
      if (idles.length < 2 || clipDe(efectiva, mapa) !== CLIP_IDLE) { tIdle = azar(); return; }
      if (buf.cargando() || buf.fundiendo()) return;
      tIdle -= Number.isFinite(dt) ? dt : 0;
      if (tIdle > 0) return;
      tIdle = azar();
      const sig = bolsa.siguiente();
      if (sig && sig !== idleSrc) { idleSrc = sig; resolver(); }
    },

    api: {
      setEmocion,
      activo: () => buf.activo(),
      estado: () => {
        const a = buf.actual();
        return {
          base, efectiva, clip: a ? a.clip : null, src: a ? a.src : null,
          velocidad: a ? a.velocidad : 1, sustituto: !!(a && a.sustituto),
          cargando: buf.cargando(), fundiendo: buf.fundiendo(),
          idles: idles.length, faltan: [...buf.faltan], pausado: buf.pausado(),
        };
      },
      idles: (lista) => fijarIdles(lista),
      pausar(on) { pausaManual = !!on; buf.pausar(pausaManual); return pausaManual; },
      /** Vuelve a pedir la emoción efectiva (p. ej. tras borrar la lista de faltan). */
      refrescar() { buf.faltan.clear(); return resolver(true); },
      liberar() { buf.liberarTodo(); pedido = null; clase(stage, 'lune-doble', false); },
    },
  };
}

/**
 * Publica en window lo que usa Python: setEmocion(s) pasa por el registro para que
 * todos los módulos se enteren (alEmocion). Aplica la emoción que el script clásico
 * haya guardado en window.__luneEmocionPendiente antes de que cargara el módulo.
 */
export function publicar(win = globalThis, reg) {
  if (!win || !reg) return;
  const pendiente = win.__luneEmocionPendiente;
  win.setEmocion = (s) => reg.emocion(s);
  if (pendiente) { win.__luneEmocionPendiente = null; reg.emocion(pendiente); }
}
