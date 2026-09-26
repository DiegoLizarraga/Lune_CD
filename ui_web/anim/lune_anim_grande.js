/*
 * ui_web/anim/lune_anim_grande.js — módulo 'grandeAnim' de la mascota ANIMADA:
 * pantalla grande (cortes 5 y 6).
 *
 * La ventana la pone Python del tamaño del monitor (ui/companion.py → grande_fase) y
 * el #stage crece por CSS (body.lune-grande en ui_web/css/grande.css, clase que pone
 * LunePantalla): el WebM de 720×1280 se REDUCE a la altura de la pantalla (hasta
 * 1280 px), no se estira. Aquí solo el movimiento, con las mismas fases que el VRM
 * (window.luneGrande(fase, opts)):
 *
 *   glide  (400 ms, ventana pequeña)  el stage baja y sale por abajo (translateY 0 → 110 %)
 *   entrar (500 ms, ventana grande)   sube desde abajo y aparece (opacidad 0 → 1)
 *   salir  (500 ms)                   baja y se desvanece
 *   volver (400 ms, ventana pequeña)  sube desde abajo a su sitio
 *   fin                                todo como estaba
 * Curvas con smoothstep. Entre 'glide' y 'entrar' se queda fuera (la ventana está
 * cambiando de tamaño). est.grande = true de 'glide' a 'fin'. Cada fase empieza a
 * contar en el siguiente tick (el reloj es el del registro).
 *
 * El registro es el dueño de style.transform/opacity: solo piezas en `pose`.
 * Eventos: ctx.emitir('grande_fase', {fase}). API: fase(fase, opts) · estado().
 * Sin DOM en los tests: tests/js/anim_grande.test.mjs.
 */
import { clamp, smoothstep } from './lune_anim_modulos.js';

export const NOMBRE = 'grandeAnim';
export const ORDEN = 60;

export const TIEMPOS_MS = Object.freeze({ glide: 400, entrar: 500, salir: 500, volver: 400 });
export const FASES = Object.freeze(['glide', 'entrar', 'salir', 'volver', 'fin']);
/** % del alto del stage que baja para salir de la vista. */
export const FUERA = 110;

const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/** Desplazamiento (% del alto, + = abajo) y opacidad de la fase con avance u (0..1). */
export function desplazamiento(fase, u) {
  const s = smoothstep(clamp(num(u), 0, 1));
  switch (fase) {
    case 'glide': return { y: FUERA * s, opacidad: 1 };
    case 'espera': return { y: FUERA, opacidad: 0 };
    case 'entrar': return { y: FUERA * (1 - s), opacidad: s };
    case 'salir': return { y: FUERA * s, opacidad: 1 - s };
    case 'volver': return { y: FUERA * (1 - s), opacidad: 1 };
    default: return { y: 0, opacidad: 1 };
  }
}

export function instalar(ctx = {}, opciones = {}) {
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };
  const tiempos = { ...TIEMPOS_MS, ...(opciones.tiempos || {}) };

  let fase = null, t0 = null, ms = 0, ahora = 0;

  function setFase(f, opts) {
    f = String(f ?? '').trim().toLowerCase();
    if (!FASES.includes(f)) return false;
    const e = est();
    if (f === 'fin') {
      fase = null;
      e.grande = false;
    } else {
      const o = opts && typeof opts === 'object' ? opts : {};
      fase = f; t0 = null;
      ms = Math.max(0, num(Number(o.ms), tiempos[f]));
      e.grande = true;
    }
    emitir('grande_fase', { fase: f });
    return true;
  }

  function avance() {
    if (t0 === null) return 0;
    return ms > 0 ? clamp((ahora - t0) / (ms / 1000), 0, 1) : 1;
  }

  /** La fase que se ve: el glide acabado espera fuera; entrar/volver acabados, en su sitio. */
  function visible() {
    if (!fase) return null;
    const u = avance();
    if (fase === 'glide' && u >= 1) return { f: 'espera', u: 1 };
    if ((fase === 'entrar' || fase === 'volver') && u >= 1) return { f: 'activa', u: 1 };
    if (fase === 'salir' && u >= 1) return { f: 'espera', u: 1 };
    return { f: fase, u };
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    tick(dt, t) {
      ahora = finito(t) ? t : ahora + num(dt);
      if (fase && t0 === null) t0 = ahora;
    },
    pose(out) {
      const v = visible();
      if (!v || v.f === 'activa') return;
      const d = desplazamiento(v.f, v.u);
      if (Math.abs(d.y) > 0.01) out.transform.push(`translate(0px, ${Math.round(d.y * 100) / 100}%)`);
      if (d.opacidad < 1) out.opacidad = num(out.opacidad, 1) * clamp(d.opacidad, 0, 1);
    },
    ocupado() { return !!fase && avance() < 1; },
    api: {
      fase: (f, opts) => setFase(f, opts),
      estado: () => { const v = visible(); return { fase, visible: v ? v.f : null, activa: fase !== null }; },
    },
  };
}
