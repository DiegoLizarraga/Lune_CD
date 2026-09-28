/*
 * ui_web/vrm/lune_comida.js — módulo 'comida' del bus VRM: la reacción de Lune al comer
 * o beber (corte 8; AvatarFoodController de Mate-Engine sin clips).
 *
 * La comida la dibuja y la mueve Python (ui/comida_qt.ControlComida → ui/comida_qt.ComidaCursor,
 * sobre el escritorio): aquí solo la cara y la cabeza cuando le pasas la comida por la
 * cabeza, y el modo «con comida en la mano».
 *
 *   window.luneComer('beber'|'comer', ms)  → bool     reacción de `ms` (2500 por defecto)
 *   window.luneComidaActiva(on)            → bool     hay comida en el cursor
 *
 *   beber  'ou' 0.5 y 3 cabeceos de 0.08 rad a 1.4 Hz (sorbitos)
 *   comer  'aa' = 0.45·(0.5 + 0.5·sin 2π·3t) durante 1.5 s (masticar)
 *   las dos: 'happy' 0.6 como máximo ('max': no baja lo que ya ponga Lune)
 * Fundido de entrada de 0.15 s y de salida de 0.3 s al final de `ms`. NO toca los brazos
 * (Diego: nada de brazos arriba; la comida la «acerca» el cursor).
 * activa(on) → inhibe {caricia: 0} (con la comida en la mano no hay caricia) y est.comiendo.
 * ocupado() mientras dura la reacción. La reacción empieza a contar en el siguiente frame
 * (el reloj es el del motor, que el módulo solo ve en los hooks).
 * Sin imports de three (Node: tests/js/comida_vrm.test.mjs).
 */
import { clamp, sumar } from './lune_modulos.js';

export const NOMBRE = 'comida';
export const ORDEN = 70;

export const TIPOS = Object.freeze(['beber', 'comer']);

export const PARAMS_COMIDA = Object.freeze({
  ou: 0.5,                 // boca de sorbo al beber
  cabeceos: 3, cabeceoRad: 0.08, cabeceoHz: 1.4,
  aa: 0.45, aaHz: 3, masticarS: 1.5,
  feliz: 0.6,
  entradaS: 0.15, salidaS: 0.3,
  msDefecto: 2500, msMax: 10000,
});

const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/** 'beber' | 'comer' (lo desconocido → 'comer'). */
export function tipoValido(tipo) {
  const t = String(tipo ?? '').trim().toLowerCase();
  return TIPOS.includes(t) ? t : 'comer';
}

/** Envolvente 0..1 de una reacción de `dur` s en el instante tl (fundidos de entrada y salida). */
export function envolvente(tl, dur, p = PARAMS_COMIDA) {
  if (!(tl >= 0) || !(tl < dur)) return 0;
  const a = p.entradaS > 0 ? clamp(tl / p.entradaS, 0, 1) : 1;
  const b = p.salidaS > 0 ? clamp((dur - tl) / p.salidaS, 0, 1) : 1;
  return Math.min(a, b);
}

/**
 * Lo que la reacción pone en el instante tl (s desde que empezó): {cabeza (rad x),
 * ou, aa, happy}. Pura.
 */
export function reaccionEn(tipo, tl, dur, p = PARAMS_COMIDA) {
  const env = envolvente(tl, dur, p);
  const r = { cabeza: 0, ou: 0, aa: 0, happy: p.feliz * env };
  if (env <= 0) return r;
  if (tipoValido(tipo) === 'beber') {
    r.ou = p.ou * env;
    const fin = p.cabeceos / p.cabeceoHz;
    if (tl < fin) r.cabeza = p.cabeceoRad * (1 - Math.cos(TAU * p.cabeceoHz * tl)) / 2 * env;
  } else if (tl < p.masticarS) {
    r.aa = p.aa * (0.5 + 0.5 * Math.sin(TAU * p.aaHz * tl)) * env;
  }
  return r;
}

/** instalar(ctx, opciones) → módulo del bus. opciones: {params}. */
export function instalar(ctx = {}, opciones = {}) {
  const P = { ...PARAMS_COMIDA, ...(opciones.params || {}) };
  const estado = () => (typeof ctx.estado === 'function' ? ctx.estado() : null);
  let activa = false;
  let reaccion = null;                     // {tipo, dur, t0 (null: el próximo frame)}
  let ahora = 0, actual = { cabeza: 0, ou: 0, aa: 0, happy: 0 };
  let comidas = 0;

  function marcar() {
    const e = estado();
    if (e) e.comiendo = activa || !!reaccion;
  }

  function avanzar(t) {
    ahora = num(t, ahora);
    if (!reaccion) { actual = { cabeza: 0, ou: 0, aa: 0, happy: 0 }; return; }
    if (reaccion.t0 === null) reaccion.t0 = ahora;
    const tl = ahora - reaccion.t0;
    if (tl >= reaccion.dur) { reaccion = null; actual = { cabeza: 0, ou: 0, aa: 0, happy: 0 }; marcar(); return; }
    actual = reaccionEn(reaccion.tipo, tl, reaccion.dur, P);
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    alDescargar() { reaccion = null; actual = { cabeza: 0, ou: 0, aa: 0, happy: 0 }; },
    pose(out, dt, t, est) {
      avanzar(t);
      const e = est || estado();
      if (e) e.comiendo = activa || !!reaccion;
      if (actual.cabeza > 1e-5) sumar(out, 'head', actual.cabeza, 0, 0);
    },
    expresiones(set) {
      if (typeof set !== 'function' || !reaccion) return;
      if (actual.happy > 0.001) set('happy', actual.happy, 'max');
      if (actual.ou > 0.001) set('ou', actual.ou, 'max');
      if (actual.aa > 0.001) set('aa', actual.aa, 'max');
    },
    ocupado() { return !!reaccion; },
    inhibe() { return activa ? { caricia: 0 } : {}; },
    api: {
      comer(tipo, ms) {
        const m = Number(ms);
        const dur = clamp(finito(m) && m > 0 ? m : P.msDefecto, 100, P.msMax) / 1000;
        reaccion = { tipo: tipoValido(tipo), dur, t0: null };
        comidas += 1;
        marcar();
        return true;
      },
      activa(on) { activa = !!on; marcar(); return true; },
      estado: () => ({ activa, reaccion: reaccion ? reaccion.tipo : null, comidas, ...actual }),
    },
  };
}
