/*
 * ui_web/vrm/lune_grande.js — módulo 'grande' del bus VRM: pantalla grande
 * (AvatarBigScreenHandler de Mate-Engine) y el pelo que se aparta con el clic
 * (AvatarBigScreenTouchHandler).
 *
 * La ventana la mueve Python (ui/pantalla_grande_qt.ControlPantallaGrande → ui/companion.py):
 * aquí solo la cámara. Python llama window.luneGrande(fase, opts) en este orden:
 *
 *   glide  (400 ms, ventana aún pequeña)  la cámara sube `desplazamiento` m (el
 *          modelo se va por abajo); al empezar: setPixelRatio(1) y setFPS(30)
 *   entrar (500 ms, ventana ya del monitor) encuadre de la cabeza: baja desde
 *          baseY + 0.5 m hasta baseY con smoothstep (la cara sube desde abajo)
 *   (activa) cada frame: h = max(0.12, |head.y − neck.y|), d = (1.4·h/2)/tan(fov/2),
 *          camY = head.y + 0.08 suavizado, x = head.x suavizado, mirando en horizontal
 *   salir  (500 ms) de baseY a baseY + 0.5 m (se va por abajo)
 *   volver (400 ms, ventana ya restaurada)  encuadre normal: baja de y0 + desplazamiento a y0
 *   fin    ctx.encuadrar(null), FOV y pixelRatio originales, setFPS(PARAMS.fpsActivo)
 *
 * `desplazamiento` = max(0.5, alto visible del encuadre normal): con el retrato o el
 * cuerpo entero el modelo sale del todo de la ventana pequeña. El salto de cámara del
 * final de Mate-Engine no se copia (volver acaba donde empieza el encuadre normal).
 * Una fase nueva a mitad de otra arranca desde donde está la cámara (sin saltos);
 * 'fin' vale en cualquier momento (salida inmediata al entrar un juego).
 * Si la ventana cambia de tamaño en 'volver' (Chromium avisa del resize más tarde),
 * se vuelve a leer el encuadre normal. Cada fase empieza a contar en el siguiente frame
 * (el reloj es el del motor, que el módulo solo ve en los hooks).
 *
 * Sujetar (clic izquierdo mantenido en pantalla grande → window.luneHold(on, px, py)):
 * un VRMSpringBoneCollider esférico de radio 0.04 m en el punto del rayo del ratón a
 * max(0.4, profundidad de la cabeza) m de la cámara (ScreenToWorldPoint de Unity). Su
 * grupo se añade UNA vez a cada array DISTINTO de joint.colliderGroups (los joints de
 * un mismo spring comparten el array: crítica c.5) y se quita al soltar, al salir de
 * pantalla grande y en alDescargar. Las clases de three-vrm llegan por `deps` (la
 * página las importa); sin ellas, luneHold no hace nada.
 *
 * est.grande = true desde 'glide' hasta 'fin'. ocupado() en las transiciones.
 * Eventos: ctx.emitir('grande_fase', {fase}) (solo para el log de Python).
 * API: fase(fase, opts) → bool · hold(on, px, py) → bool · estado()
 * Sin imports de three: THREE llega por ctx (Node: tests/js/grande.test.mjs).
 */
import { clamp, lerp, suav, smoothstep } from './lune_modulos.js';

export const NOMBRE = 'grande';
export const ORDEN = 60;

export const PARAMS_GRANDE = Object.freeze({
  buffer: 1.4,          // alto visible = 1.4 · alto de la cabeza
  yOffset: 0.08,        // m sobre el hueso de la cabeza
  fadeY: 0.5,           // m que sube la cámara al entrar/salir (FadeYOffset)
  hMin: 0.12, hDefecto: 0.25,
  glideMs: 400, fadeMs: 500,
  suavY: 6, suavX: 4, suavZ: 6,
  radio: 0.04,          // m del colisionador del ratón
  profMin: 0.4,         // m mínimos del colisionador a la cámara
  fps: 30,
});

export const FASES = Object.freeze(['glide', 'entrar', 'salir', 'volver', 'fin']);

const G2R = Math.PI / 180;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/** Alto de la cabeza: max(hMin, |head.y − neck.y|), o hDefecto sin cuello. */
export function alturaCabeza(headY, neckY, p = PARAMS_GRANDE) {
  if (!finito(headY) || !finito(neckY)) return p.hDefecto;
  return Math.max(p.hMin, Math.abs(headY - neckY));
}

/** Distancia de la cámara para que se vean buffer·h de alto con ese FOV vertical (°). */
export function distanciaEncuadre(h, fovGrados, buffer = PARAMS_GRANDE.buffer) {
  const fov = clamp(num(fovGrados, 24), 1, 170) * G2R;
  return (buffer * num(h, PARAMS_GRANDE.hDefecto) / 2) / Math.tan(fov / 2);
}

/** Avance 0..1 con smoothstep de una fase de `ms` que empezó en t0 (s). */
export function curva(t, t0, ms) {
  if (!(ms > 0)) return 1;
  return smoothstep(clamp((t - t0) / (ms / 1000), 0, 1));
}

/**
 * Punto del mundo bajo el ratón a `prof` m de una cámara que mira a −Z sin girar
 * (en pantalla grande siempre) — ScreenToWorldPoint(mouse, z = prof).
 * px/py en px de la página; rect = canvas.getBoundingClientRect().
 */
export function puntoRayo({ px, py, rect, cam, fov, aspect, prof }) {
  const w = Math.max(1, num(rect && rect.width, 1)), h = Math.max(1, num(rect && rect.height, 1));
  const nx = ((num(px) - num(rect && rect.left)) / w) * 2 - 1;
  const ny = 1 - ((num(py) - num(rect && rect.top)) / h) * 2;
  const tanV = Math.tan(clamp(num(fov, 24), 1, 170) * G2R / 2);
  const a = num(aspect, w / h);
  const d = num(prof, 1);
  return { x: num(cam.x) + nx * tanV * a * d, y: num(cam.y) + ny * tanV * d, z: num(cam.z) - d };
}

/**
 * instalar(ctx, deps) → módulo. deps: {VRMSpringBoneCollider, VRMSpringBoneColliderShapeSphere,
 * dpr (pixelRatio al acabar), params}.
 */
export function instalar(ctx = {}, deps = {}) {
  const P = { ...PARAMS_GRANDE, ...(deps.params || {}) };
  const T = ctx.THREE || null;
  const Col = typeof deps.VRMSpringBoneCollider === 'function' ? deps.VRMSpringBoneCollider : null;
  const Esfera = typeof deps.VRMSpringBoneColliderShapeSphere === 'function' ? deps.VRMSpringBoneColliderShapeSphere : null;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };
  const cam = () => ctx.camera || null;

  let fase = null;               // null | glide | entrar | activa | salir | volver | hecho (tras volver)
  let t0 = null, ms = 0, ahora = 0;        // t0 null: la fase empieza en el próximo frame
  let normal = null;             // {y, z, fov, off, w, h}: encuadre normal de la ventana pequeña
  let desde = { x: 0, y: 0, z: 0 };
  let suave = null;              // {x, y, z} de la cámara en activa
  let fovOriginal = null;
  let hold = { on: false, px: 0, py: 0 };
  let colisionador = null, grupo = null;
  const enganchados = new Set();

  function head() {
    const hs = ctx.huesos || {};
    return hs.head || null;
  }

  function posHueso(h) {
    if (!h || typeof h.getWorldPosition !== 'function') return null;
    const v = T && T.Vector3 ? new T.Vector3() : { x: 0, y: 0, z: 0, set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; } };
    try { return h.getWorldPosition(v); } catch (e) { return null; }
  }

  /** Encuadre de la cabeza ahora: {x, y (baseY), z, d, h}. */
  function objetivo() {
    const c = cam();
    const hs = ctx.huesos || {};
    const ph = posHueso(hs.head), pn = posHueso(hs.neck);
    const h = ph ? alturaCabeza(ph.y, pn ? pn.y : NaN, P) : P.hDefecto;
    const d = distanciaEncuadre(h, c ? c.fov : 24, P.buffer);
    const x = ph ? ph.x : 0, y = (ph ? ph.y : 1.4) + P.yOffset, zc = (ph ? ph.z : 0) + d;
    return { x, y, z: zc, d, h };
  }

  function medidas() {
    const c = ctx.canvas;
    return { w: num(c && c.clientWidth, 0), h: num(c && c.clientHeight, 0) };
  }

  /** Lee el encuadre normal (el del usuario) de la ventana tal como está ahora. */
  function leerNormal(reencuadrar) {
    const c = cam();
    if (!c) return null;
    if (reencuadrar && typeof ctx.encuadrar === 'function') { try { ctx.encuadrar(null); } catch (e) { /* sin cámara */ } }
    const fov = num(c.fov, 24);
    const cabeza = posHueso(head());
    const prof = Math.max(0.05, num(c.position.z) - (cabeza ? cabeza.z : 0));
    const visible = 2 * prof * Math.tan(fov * G2R / 2);
    const m = medidas();
    return { y: num(c.position.y), z: num(c.position.z), fov, off: Math.max(P.fadeY, visible), w: m.w, h: m.h };
  }

  function ponerCamara(x, y, z) {
    const c = cam();
    if (!c) return;
    c.position.set(x, y, z);
    if (c.rotation && typeof c.rotation.set === 'function') c.rotation.set(0, 0, 0);   // en horizontal
    else if (typeof c.lookAt === 'function') c.lookAt(x, y, z - 1);
  }

  function actual() {
    const c = cam();
    return c ? { x: num(c.position.x), y: num(c.position.y), z: num(c.position.z) } : { x: 0, y: 0, z: 0 };
  }

  // ── Colisionador del ratón ───────────────────────────────────────────────────
  function engancharColisionador() {
    const vrm = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
    const sbm = vrm && vrm.springBoneManager;
    if (!sbm || !Col || !Esfera) return false;
    if (!colisionador) {
      const offset = T && T.Vector3 ? new T.Vector3(0, 0, 0) : undefined;
      colisionador = new Col(new Esfera({ offset, radius: P.radio, inside: false }));
      colisionador.name = 'luneSujetar';
      grupo = { colliders: [colisionador], name: 'luneSujetar' };
    }
    const arrays = new Set();
    for (const j of (sbm.joints || [])) if (j && Array.isArray(j.colliderGroups)) arrays.add(j.colliderGroups);
    for (const arr of arrays) {
      if (!arr.includes(grupo)) arr.push(grupo);
      enganchados.add(arr);
    }
    return enganchados.size > 0;
  }

  function soltarColisionador() {
    if (grupo) {
      for (const arr of enganchados) {
        let i;
        while ((i = arr.indexOf(grupo)) >= 0) arr.splice(i, 1);
      }
    }
    enganchados.clear();
  }

  function moverColisionador() {
    if (!colisionador || !enganchados.size) return;
    const c = cam();
    if (!c) return;
    const cabeza = posHueso(head());
    const prof = Math.max(P.profMin, num(c.position.z) - (cabeza ? cabeza.z : 0));
    const rect = ctx.canvas && typeof ctx.canvas.getBoundingClientRect === 'function'
      ? ctx.canvas.getBoundingClientRect() : { left: 0, top: 0, width: 1, height: 1 };
    const p = puntoRayo({ px: hold.px, py: hold.py, rect, cam: c.position, fov: c.fov, aspect: c.aspect, prof });
    colisionador.position.set(p.x, p.y, p.z);
    try { if (typeof colisionador.updateMatrixWorld === 'function') colisionador.updateMatrixWorld(true); } catch (e) { /* sigue */ }
  }

  function setHold(on, px, py) {
    const puede = fase === 'entrar' || fase === 'activa';
    if (!on || !puede) {
      const habia = hold.on;
      hold.on = false;
      soltarColisionador();
      return habia && !on;
    }
    hold.px = num(Number(px), hold.px); hold.py = num(Number(py), hold.py);
    if (!hold.on) hold.on = engancharColisionador();
    if (hold.on) moverColisionador();
    return hold.on;
  }

  // ── Fases ────────────────────────────────────────────────────────────────────
  function empezar(f, opts) {
    const o = opts && typeof opts === 'object' ? opts : {};
    const c = cam();
    const est = typeof ctx.estado === 'function' ? ctx.estado() : null;
    t0 = null;
    if (f === 'glide') {
      if (!fase || fase === 'hecho') {
        normal = leerNormal(false);
        fovOriginal = c ? c.fov : null;
        try { if (typeof ctx.setPixelRatio === 'function') ctx.setPixelRatio(1); } catch (e) { /* sigue */ }
        try { if (typeof ctx.setFPS === 'function') ctx.setFPS(P.fps); } catch (e) { /* sigue */ }
      }
      ms = num(Number(o.ms), P.glideMs);
    } else if (f === 'entrar') {
      if (!normal) normal = leerNormal(false);
      if (fovOriginal === null && c) fovOriginal = c.fov;
      ms = num(Number(o.ms), P.fadeMs);
      suave = null;
    } else if (f === 'salir') {
      ms = num(Number(o.ms), P.fadeMs);
    } else if (f === 'volver') {
      setHold(false);
      normal = leerNormal(true);
      ms = num(Number(o.ms), P.glideMs);
    }
    desde = actual();
    fase = f;
    if (est) est.grande = true;
  }

  function terminar() {
    setHold(false);
    const c = cam();
    const est = typeof ctx.estado === 'function' ? ctx.estado() : null;
    if (est) est.grande = false;
    if (c && fovOriginal !== null && finito(fovOriginal)) {
      c.fov = fovOriginal;
      if (typeof c.updateProjectionMatrix === 'function') c.updateProjectionMatrix();
    }
    try { if (typeof ctx.encuadrar === 'function') ctx.encuadrar(null); } catch (e) { /* sin cámara */ }
    const dpr = num(Number(deps.dpr), Math.min(num(globalThis.devicePixelRatio, 1) || 1, 2));
    try { if (typeof ctx.setPixelRatio === 'function') ctx.setPixelRatio(dpr); } catch (e) { /* sigue */ }
    const fps = num(ctx.PARAMS && ctx.PARAMS.fpsActivo, 60);
    try { if (typeof ctx.setFPS === 'function') ctx.setFPS(fps); } catch (e) { /* sigue */ }
    fase = null; normal = null; suave = null; fovOriginal = null;
  }

  function setFase(f, opts) {
    f = String(f ?? '').trim().toLowerCase();
    if (!FASES.includes(f)) return false;
    if (f === 'fin') { if (fase !== null) terminar(); }
    else empezar(f, opts);
    emitir('grande_fase', { fase: f });
    return true;
  }

  function trasUpdate(dt, t) {
    ahora = num(t, ahora);
    if (!fase) return;
    const d = num(dt);
    if (t0 === null) t0 = ahora;
    const u = curva(ahora, t0, ms);
    if (fase === 'glide' || fase === 'volver') {
      // Ventana pequeña: encuadre normal desplazado. En 'volver', si Chromium avisó
      // del resize después, se relee el encuadre normal.
      if (fase === 'volver' && normal) {
        const m = medidas();
        if (m.w !== normal.w || m.h !== normal.h) normal = leerNormal(true);
      }
      if (!normal) normal = leerNormal(false);
      if (!normal) return;
      if (fase === 'glide') ponerCamara(lerp(desde.x, 0, u), lerp(desde.y, normal.y + normal.off, u), lerp(desde.z, normal.z, u));
      else {
        ponerCamara(0, lerp(normal.y + normal.off, normal.y, u), normal.z);
        if (u >= 1) fase = 'hecho';
      }
      return;
    }
    if (fase === 'hecho') { if (normal) ponerCamara(0, normal.y, normal.z); return; }
    const o = objetivo();
    if (fase === 'entrar') {
      ponerCamara(o.x, lerp(o.y + P.fadeY, o.y, u), o.z);
      if (u >= 1) { fase = 'activa'; suave = { x: o.x, y: o.y, z: o.z }; }
    } else if (fase === 'activa') {
      if (!suave) suave = actual();
      suave.x += (o.x - suave.x) * suav(d, P.suavX);
      suave.y += (o.y - suave.y) * suav(d, P.suavY);
      suave.z += (o.z - suave.z) * suav(d, P.suavZ);
      ponerCamara(suave.x, suave.y, suave.z);
    } else if (fase === 'salir') {
      ponerCamara(lerp(desde.x, o.x, u), lerp(desde.y, o.y + P.fadeY, u), lerp(desde.z, o.z, u));
    }
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    alCargar() { if (hold.on) setHold(false); },
    alDescargar() {
      hold.on = false;
      soltarColisionador();
      colisionador = null; grupo = null;              // el modelo nuevo trae otros joints
    },
    trasPose(dt, t) {
      ahora = num(t, ahora);
      if (hold.on) moverColisionador();
    },
    trasUpdate,
    ocupado() { return fase === 'glide' || fase === 'entrar' || fase === 'salir' || fase === 'volver'; },
    api: {
      fase: (f, opts) => setFase(f, opts),
      hold: (on, px, py) => setHold(!!on, px, py),
      estado: () => ({
        fase, activa: fase !== null, hold: hold.on, enganchados: enganchados.size,
        normal: normal ? { ...normal } : null,
      }),
    },
  };
}
