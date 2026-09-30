/*
 * ui_web/anim/lune_anim_comida.js — módulo 'comidaAnim' de la asistente ANIMADA: la
 * reacción al comer o beber (corte 8).
 *
 * Mismas funciones de página que el VRM (ui_web/vrm/lune_comida.js):
 *   window.luneComer('beber'|'comer', ms) → bool · window.luneComidaActiva(on) → bool.
 * La comida la dibuja y la mueve Python (ui/comida_qt.ComidaCursor sobre el escritorio).
 *   · comer: capa de emoción 'comida' = 'happy' con prioridad 60 (lune_anim_video.js:
 *     por encima de dormir 40, por debajo de arrastre 80 y mareo 90) durante `ms`, y un
 *     rebote de escala hasta ×1.04 (0.35 s, pivote abajo al centro) al empezar.
 *   · activa(on): est.comiendo (con la comida en la mano).
 * El registro es el dueño de style.transform: el rebote va como pieza en `pose`
 * (escalarEn); este módulo NO escribe estilos. Cada reacción empieza a contar en el
 * siguiente tick (el reloj es el del registro).
 * Sin DOM en los tests: tests/js/anim_comida.test.mjs.
 */
import { clamp, escalarEn } from './lune_anim_modulos.js';
import { fijarCapa, quitarCapa } from './lune_anim_video.js';

export const NOMBRE = 'comidaAnim';
export const ORDEN = 70;

export const PARAMS_COMIDA_ANIM = Object.freeze({
  capa: 'comida', clip: 'happy', prioridad: 60,
  rebote: 1.04, reboteS: 0.35,
  pivoteX: '50%', pivoteY: '100%',
  msDefecto: 2500, msMax: 10000,
});

const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/** Escala del rebote en el instante tl (s desde que empezó): 1 → rebote → 1. */
export function escalaRebote(tl, p = PARAMS_COMIDA_ANIM) {
  if (!(tl >= 0) || !(p.reboteS > 0) || tl >= p.reboteS) return 1;
  return 1 + (p.rebote - 1) * Math.sin(Math.PI * (tl / p.reboteS));
}

/** instalar(ctx, opciones) para crearRegistroAnim().registrar(). opciones: {params}. */
export function instalar(ctx = {}, opciones = {}) {
  const p = { ...PARAMS_COMIDA_ANIM, ...(opciones.params || {}) };
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  let activa = false;
  let reaccion = null;                     // {tipo, dur, t0 (null: el próximo tick)}
  let ahora = 0, escala = 1, comidas = 0;

  function marcar() { est().comiendo = activa || !!reaccion; }

  function acabar() {
    reaccion = null; escala = 1;
    quitarCapa(est(), p.capa);
    marcar();
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    tick(dt, t) {
      ahora = finito(t) ? t : ahora + num(dt);
      if (!reaccion) return;
      if (reaccion.t0 === null) reaccion.t0 = ahora;
      const tl = ahora - reaccion.t0;
      if (tl >= reaccion.dur) { acabar(); return; }
      escala = escalaRebote(tl, p);
    },
    pose(out) {
      if (reaccion && Math.abs(escala - 1) > 0.0002) out.transform.push(escalarEn(escala, p.pivoteX, p.pivoteY));
    },
    ocupado() { return !!reaccion; },
    alDetener() { if (reaccion) acabar(); },     // oculta: la reacción ya no se ve
    api: {
      comer(tipo, ms) {
        const m = Number(ms);
        const dur = clamp(finito(m) && m > 0 ? m : p.msDefecto, 100, p.msMax) / 1000;
        reaccion = { tipo: String(tipo ?? '') === 'beber' ? 'beber' : 'comer', dur, t0: null };
        escala = 1;
        comidas += 1;
        fijarCapa(est(), p.capa, p.clip, p.prioridad);
        marcar();
        return true;
      },
      activa(on) { activa = !!on; marcar(); return true; },
      estado: () => ({ activa, reaccion: reaccion ? reaccion.tipo : null, escala, comidas }),
    },
  };
}
