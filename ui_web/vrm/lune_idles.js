/*
 * ui_web/vrm/lune_idles.js — módulo 'idles' del bus VRM ("Idle Animation" de
 * Mate-Engine, corte 3).
 *
 * Sustituye a aplicarIdle() de lune_vrm.js (4 variantes fijas en rueda cada 10 s)
 * por 10 variantes procedurales:
 *   manosEspalda · manosDelante (juega con los dedos) · mirarAlrededor ·
 *   mirarSuelo · pesoPierna · tararear · mirarseMano · ladeoCurioso · tocarsePelo
 *   y estirarse (one-shot de 3 s tras 2 min sin actividad; no entra en la rueda).
 * Se eligen con Bolsa (sin repetir hasta agotar la tanda) cada azar(8, 14) s y se
 * funden en 1 s con smoothstep. Si se cambia a mitad de un fundido, las variantes
 * salientes bajan desde el peso que tenían (sin saltos). Las asimétricas eligen
 * lado al entrar (se espejan izquierda↔derecha).
 *
 * Peso global = (1 − 0.7·gestoPeso)(1 − dragPeso)(1 − sleepBlend) × activo × est.inh.idle
 * (el factor de otros módulos, si el motor lo pasa).
 *
 * Además:
 *   - microexpresiones cada 7–13 s: entrecerrar los ojos +0.25 (0.4/1/0.4 s) o
 *     sonrisa happy 0.25 + ee 0.15 durante 0.9 s (no mientras habla, la arrastran o duerme);
 *   - bostezo (2.4 s, mano a la boca) al empezar a dormir, o con api.bostezar();
 *     no se multiplica por sleepBlend para que se vea mientras se duerme; si la
 *     despiertan a mitad, se funde fuera; con el modelo cargado ya dormida, no bosteza;
 *   - estiramiento tras `estirarTras` s sin actividad (est.inactivo; si el motor no
 *     lo pasa, se deduce de cambios en cursor, arrastre, habla y gesto): brazos
 *     abajo y atrás, nunca por encima de la horizontal;
 *   - con est.hablando no pone expresiones (ni de variantes ni de bostezo/estiramiento).
 *
 * Convención de las poses: la de lune_vrm.js (radianes, huesos normalizados,
 * convención VRM 1.0; el motor aplica sXZ a X y Z al final). X = cabecear (+ abajo;
 * en un brazo caído, + lo lleva hacia atrás), Y = girar (+ hacia la izquierda del
 * modelo = derecha del espectador), Z = ladear (brazo izquierdo: − baja, + sube;
 * derecho al revés). Espejo: (x, y, z) → (x, −y, −z) cambiando left↔right.
 * Las amplitudes son un punto de partida para ajustar en pantalla.
 *
 * API (window.luneMod('idles', …)):
 *   variante(n?)          n = índice 0..9 o nombre → la fuerza ahora; sin n → nombre actual
 *   set({activo, cambioMin, cambioMax, mezcla, microMin, microMax, estirarTras}) → config
 *   bostezar() · estirar() · estado() · historial()
 *
 * Sin imports de three (tests/js/idles.test.mjs en Node).
 */
import { clamp, smoothstep, smoothDamp, Bolsa, crearAleatorio, mezclarPoses, sumar } from './lune_modulos.js';

const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);
const SALIDA_UNICO = 0.8;         // s: un one-shot sustituido a medias se funde en esto

export const CONFIG_IDLES = Object.freeze({
  cambioMin: 8, cambioMax: 14,       // s entre variantes
  mezcla: 1.0,                       // s de fundido (smoothstep)
  microMin: 7, microMax: 13,         // s entre microexpresiones
  estirarTras: 120,                  // s sin actividad → estirarse
  estirarDur: 3.0, bostezoDur: 2.4,
});

// ── Utilidades de pose ─────────────────────────────────────────────────────────

function espejoHueso(h) {
  if (h.startsWith('left')) return 'right' + h.slice(4);
  if (h.startsWith('right')) return 'left' + h.slice(5);
  return h;
}

/** Pose espejada izquierda↔derecha: (x, y, z) → (x, −y, −z). */
export function espejar(pose) {
  const out = {};
  for (const h in pose) {
    const p = pose[h];
    if (p) out[espejoHueso(h)] = [p[0] || 0, -(p[1] || 0), -(p[2] || 0)];
  }
  return out;
}

/** Envolvente ataque/mantener/soltar con smoothstep en los bordes (0..1). */
export function envolvente(tl, ataque, mantener, soltar) {
  if (!finito(tl) || tl <= 0) return 0;
  if (tl < ataque) return smoothstep(tl / ataque);
  if (tl < ataque + mantener) return 1;
  const r = (tl - ataque - mantener) / Math.max(1e-6, soltar);
  return r >= 1 ? 0 : 1 - smoothstep(r);
}

// ── Variantes ──────────────────────────────────────────────────────────────────
// pose: offset fijo sobre la A-pose · fn(t, tl, o): término dinámico (t global, tl
// local) · expr: expresiones suaves mientras dura · espejo: elige lado al entrar.

export const VARIANTES = Object.freeze([
  {
    nombre: 'manosEspalda',
    pose: {
      spine: [-0.03, 0, 0], head: [-0.03, 0, 0],
      leftUpperArm: [0.30, 0, -0.14], rightUpperArm: [0.30, 0, 0.14],
      leftLowerArm: [0, -0.20, -0.75], rightLowerArm: [0, 0.20, 0.75],
      leftHand: [0, 0, -0.10], rightHand: [0, 0, 0.10],
    },
    fn: (t, tl, o) => {                                   // se balancea sobre los talones
      sumar(o, 'spine', 0.015 * Math.sin(TAU * t / 5), 0, 0);
      sumar(o, 'head', 0, 0.08 * Math.sin(TAU * t / 9), 0);
    },
  },
  {
    nombre: 'manosDelante',
    pose: {
      head: [0.08, 0, 0],
      leftUpperArm: [-0.30, 0, -0.12], rightUpperArm: [-0.30, 0, 0.12],
      leftLowerArm: [0, -0.85, -0.25], rightLowerArm: [0, 0.85, 0.25],
    },
    fn: (t, tl, o) => {                                   // juega con los dedos
      sumar(o, 'leftHand', 0.20 * Math.sin(TAU * 0.7 * t), 0, 0.10 * Math.sin(TAU * 1.1 * t));
      sumar(o, 'rightHand', 0.20 * Math.sin(TAU * 0.7 * t + 1.3), 0, -0.10 * Math.sin(TAU * 1.1 * t + 0.7));
      const b = 0.06 * Math.sin(TAU * 0.35 * t);
      sumar(o, 'leftLowerArm', 0, -b, 0); sumar(o, 'rightLowerArm', 0, b, 0);
    },
  },
  {
    nombre: 'mirarAlrededor',
    pose: {},
    fn: (t, tl, o) => {
      const g = Math.sin(TAU * t / 7);
      sumar(o, 'head', -0.04 + 0.05 * Math.sin(TAU * t / 3.5), 0.38 * g, 0.03 * g);
      sumar(o, 'neck', 0, 0.12 * g, 0);
      sumar(o, 'spine', 0, 0.05 * Math.sin(TAU * t / 7 - 0.4), 0);
      sumar(o, 'upperChest', 0, 0.03 * Math.sin(TAU * t / 7 - 0.2), 0);
    },
    expr: { surprised: 0.08 },
  },
  {
    nombre: 'mirarSuelo',
    pose: { head: [0.28, 0, 0.04], neck: [0.08, 0, 0], spine: [0.05, 0, 0] },
    fn: (t, tl, o) => {                                   // arrastra la punta del pie
      sumar(o, 'head', 0, 0.10 * Math.sin(TAU * t / 8), 0);
      const p = 0.5 + 0.5 * Math.sin(TAU * t / 3);
      sumar(o, 'rightUpperLeg', -0.04 * p, 0, 0);
      sumar(o, 'rightLowerLeg', 0.08 * p, 0, 0);
    },
    expr: { relaxed: 0.15, sad: 0.08 },
    espejo: true,
  },
  {
    nombre: 'pesoPierna',                                 // peso en la izquierda, rodilla derecha suelta
    pose: {
      hips: [0, 0, 0.06], spine: [0, 0, -0.045], chest: [0, 0, -0.02], head: [0, 0, 0.035],
      rightUpperLeg: [-0.06, 0, -0.02], rightLowerLeg: [0.16, 0, 0],
      leftUpperArm: [0, 0, -0.03], rightUpperArm: [0, 0, 0.02],
    },
    fn: (t, tl, o) => { sumar(o, 'hips', 0, 0, 0.008 * Math.sin(TAU * t / 4.5)); },
    espejo: true,
  },
  {
    nombre: 'tararear',
    pose: {},
    fn: (t, tl, o) => {
      const r = Math.sin(TAU * 0.5 * t);
      sumar(o, 'head', 0.03 * Math.sin(TAU * t), 0, 0.07 * r);
      sumar(o, 'neck', 0, 0, 0.03 * r);
      sumar(o, 'hips', 0, 0, -0.025 * r);
      sumar(o, 'spine', 0, 0, 0.02 * r);
    },
    expr: { relaxed: 0.35, happy: 0.2, ou: 0.1 },
  },
  {
    // One-shot (no entra en la rueda). Los brazos NO suben (lo pidió el usuario): se
    // estira hacia abajo y atrás, brazos rectos (antebrazos sin el codo de la A-pose)
    // y un poco más caídos, hombros atrás, pecho fuera, espalda arqueada y cabeza
    // atrás. Con la A-pose (brazo z ∓1.15) el brazo queda a ~83° bajo la horizontal y
    // x > 0 lleva la mano DETRÁS (ver la nota de signos de lune_vrm.js).
    nombre: 'estirarse',
    unico: true,
    pose: {
      leftUpperArm: [0.55, 0, -0.30], rightUpperArm: [0.55, 0, 0.30],
      leftLowerArm: [0, 0.28, 0], rightLowerArm: [0, -0.28, 0],
      leftHand: [0.25, 0, -0.15], rightHand: [0.25, 0, 0.15],
      spine: [-0.10, 0, 0], chest: [-0.08, 0, 0], upperChest: [-0.05, 0, 0],
      neck: [-0.06, 0, 0], head: [-0.20, 0, 0],
    },
    fn: (t, tl, o) => {
      // tirón hacia atrás en el centro del estiramiento y un leve vaivén lateral
      const k = Math.sin(Math.PI * clamp(tl / 3, 0, 1));
      sumar(o, 'leftUpperArm', 0.12 * k, 0, 0); sumar(o, 'rightUpperArm', 0.12 * k, 0, 0);
      sumar(o, 'chest', -0.03 * k, 0, 0); sumar(o, 'head', -0.05 * k, 0, 0);
      sumar(o, 'spine', 0, 0, 0.05 * Math.sin(TAU * tl / 3));
    },
    expr: { blink: 0.7, aa: 0.35, happy: 0.2 },
  },
  {
    nombre: 'mirarseMano',                                // la derecha; espejo = la izquierda
    pose: {
      rightUpperArm: [-0.85, 0, -0.55], rightLowerArm: [0, 1.2, 0],
      head: [0.18, -0.22, -0.06], spine: [0.03, -0.05, 0],
    },
    fn: (t, tl, o) => { sumar(o, 'rightHand', 0, 0.35 * Math.sin(TAU * t / 2.6), 0.15 * Math.sin(TAU * t / 1.7)); },
    expr: { surprised: 0.1, relaxed: 0.15 },
    espejo: true,
  },
  {
    nombre: 'ladeoCurioso',
    pose: { head: [-0.04, 0.10, 0.22], neck: [0, 0.03, 0.06], spine: [0, 0, 0.03] },
    fn: (t, tl, o) => { sumar(o, 'head', 0, 0, 0.03 * Math.sin(TAU * t / 3)); },
    expr: { surprised: 0.12, happy: 0.1 },
    espejo: true,
  },
  {
    nombre: 'tocarsePelo',                                // mano derecha al pelo; espejo = izquierda
    pose: {
      rightUpperArm: [0.45, 0, -1.4], rightLowerArm: [0, 0, -1.9], rightHand: [0, 0, -0.2],
      head: [0.02, -0.05, 0.12],
    },
    fn: (t, tl, o) => {
      sumar(o, 'rightHand', 0, 0.25 * Math.sin(TAU * 1.1 * t), 0.10 * Math.sin(TAU * 1.1 * t));
      sumar(o, 'rightLowerArm', 0, 0, 0.08 * Math.sin(TAU * 0.55 * t));
    },
    expr: { happy: 0.12, relaxed: 0.2 },
    espejo: true,
  },
]);

/** Bostezo (mano a la boca, cabeza atrás, boca abierta, ojos cerrados). */
export const BOSTEZO = Object.freeze({
  nombre: 'bostezo',
  pose: {
    rightUpperArm: [0.55, 0, -0.65], rightLowerArm: [0, 0, -1.95], rightHand: [0, 0, -0.3],
    leftUpperArm: [0, 0, 0.08], head: [-0.20, 0, 0.05], neck: [-0.06, 0, 0], spine: [-0.05, 0, 0],
  },
  fn: (t, tl, o) => { sumar(o, 'head', 0, 0, 0.04 * Math.sin(TAU * tl / 2.4)); },
  expr: { aa: 0.75, blink: 0.85, relaxed: 0.3 },
});

export const INDICE_ESTIRARSE = VARIANTES.findIndex((v) => v.nombre === 'estirarse');
const RUEDA = VARIANTES.map((v, i) => (v.unico ? -1 : i)).filter((i) => i >= 0);

/** Pose de una variante en t (espejada si lado < 0). */
export function poseVariante(v, t, tl, lado = 1) {
  const tmp = {};
  mezclarPoses(tmp, v.pose, 1);
  if (typeof v.fn === 'function') v.fn(t, tl, tmp);
  return lado < 0 ? espejar(tmp) : tmp;
}

// ── Módulo ─────────────────────────────────────────────────────────────────────

/**
 * instalar(ctx, opciones?) → módulo 'idles'. opciones: {aleatorio, semilla, config}.
 * Si no se pasan, usa ctx.aleatorio o Math.random. ctx.tieneExpr(nombre) (opcional)
 * decide si se entrecierran los ojos con 'blink' o con blinkLeft/blinkRight.
 */
export function instalar(ctx = {}, opciones = {}) {
  const azarBase = typeof opciones.aleatorio === 'function' ? opciones.aleatorio
    : opciones.semilla !== undefined ? crearAleatorio(opciones.semilla)
      : typeof ctx.aleatorio === 'function' ? ctx.aleatorio : Math.random;
  const azar = (a, b) => a + num(Number(azarBase()), 0.5) * (b - a);
  const cfg = { ...CONFIG_IDLES, ...(opciones.config || {}) };
  const bolsa = new Bolsa(RUEDA, { aleatorio: azarBase });
  const bolsaMicro = new Bolsa(['entrecerrar', 'sonrisa'], { aleatorio: azarBase });

  let actual = null;            // {v, i, lado, t0}
  let salientes = [];           // [{v, i, lado, t0, w0}]
  let tCambio = 0, proximo = null;
  let unico = null;             // {v, t0, dur, tipo: 'estirarse'|'bostezo'}
  let unicoPrev = null;         // one-shot sustituido a medias: {u, e0, t1}, se funde en SALIDA_UNICO s
  let micro = null, proxMicro = null;
  let activo = true, pesoActivo = 1, pesoInh = 1;
  const velInh = { v: 0 };      // smoothDamp del factor de otros módulos
  let armadoEstirar = true, dormidaAntes = false, ultimoBostezo = -Infinity;
  let ultimaAct = null, cursorPrev = null, gestoPrev;
  let tUlt = 0, W = 0, A = 1, dpUlt = 0, ocupacion = 0;
  const historial = [];

  const entrada = (t) => smoothstep(clamp((t - tCambio) / Math.max(1e-3, cfg.mezcla), 0, 1));

  function capasEn(t) {
    const s = entrada(t);
    const res = [];
    if (s < 1) for (const c of salientes) { const w = c.w0 * (1 - s); if (w > 1e-4) res.push({ ...c, w }); }
    if (actual) res.push({ ...actual, w: s });
    return res;
  }

  function cambiar(i, t) {
    const v = VARIANTES[i];
    if (!v) return null;
    const nuevas = capasEn(t).map((c) => ({ v: c.v, i: c.i, lado: c.lado, t0: c.t0, w0: c.w })).filter((c) => c.w0 > 1e-4);
    while (nuevas.length > 4) {                           // cambios muy seguidos: fuera la más débil
      let k = 0;
      for (let j = 1; j < nuevas.length; j++) if (nuevas[j].w0 < nuevas[k].w0) k = j;
      nuevas.splice(k, 1);
    }
    salientes = nuevas;
    actual = { v, i, lado: v.espejo && azar(0, 1) < 0.5 ? -1 : 1, t0: t };
    tCambio = t;
    proximo = t + azar(cfg.cambioMin, cfg.cambioMax);
    historial.push({ nombre: v.nombre, t });
    if (historial.length > 60) historial.shift();
    return v.nombre;
  }

  function siguienteDeLaRueda() {
    let i = bolsa.siguiente();
    if (actual && i === actual.i && RUEDA.length > 1) i = bolsa.siguiente();   // tras un variante() forzado
    return i;
  }

  function lanzarUnico(tipo, t) {
    if (unico) {                                          // el que estaba se funde, no se corta
      const e = envUnico(unico, t - unico.t0);
      unicoPrev = e > 1e-4 ? { u: unico, e0: e, t1: t } : null;
    }
    if (tipo === 'bostezo') { unico = { v: BOSTEZO, t0: t, dur: cfg.bostezoDur, tipo }; ultimoBostezo = t; }
    else unico = { v: VARIANTES[INDICE_ESTIRARSE], t0: t, dur: cfg.estirarDur, tipo };
    historial.push({ nombre: unico.v.nombre, t });
    if (historial.length > 60) historial.shift();
    return unico.v.nombre;
  }

  /** El one-shot en curso se funde fuera en SALIDA_UNICO s (sin salto). */
  function soltarUnico(t) {
    if (!unico) return;
    const e = envUnico(unico, t - unico.t0);
    unicoPrev = e > 1e-4 ? { u: unico, e0: e, t1: t } : null;
    unico = null;
  }

  function envUnico(u, tl) {
    const k = Math.max(1e-3, u.dur) / (u.tipo === 'bostezo' ? 2.4 : 3.0);   // termina justo en u.dur
    return u.tipo === 'bostezo' ? envolvente(tl, 0.7 * k, 1.0 * k, 0.7 * k) : envolvente(tl, 0.8 * k, 1.4 * k, 0.8 * k);
  }

  // El bostezo se ve aunque se esté durmiendo; el estiramiento se apaga como el idle.
  const factorDe = (u) => (u.tipo === 'bostezo' ? A * (1 - dpUlt) : W);

  /** One-shots en t: [{u, e (envolvente), f (factor)}]. Sin efectos. */
  function unicosEn(t) {
    const res = [];
    if (unicoPrev) {
      const k = clamp((t - unicoPrev.t1) / SALIDA_UNICO, 0, 1);
      const e = unicoPrev.e0 * (1 - smoothstep(k));
      if (e > 1e-4) res.push({ u: unicoPrev.u, e, f: factorDe(unicoPrev.u) });
    }
    if (unico) {
      const e = envUnico(unico, t - unico.t0);
      res.push({ u: unico, e, f: factorDe(unico) });
    }
    return res;
  }

  function inactivo(t, est) {
    if (finito(est.inactivo)) return Math.max(0, est.inactivo);
    // Sin est.inactivo: actividad = cursor que se mueve, arrastre, habla o gesto nuevo.
    const c = est.cursor || {};
    const nx = num(c.nx), ny = num(c.ny);
    if (ultimaAct === null) ultimaAct = t;
    if (est.drag || est.hablando || (gestoPrev !== undefined && est.gesto !== gestoPrev)
      || (cursorPrev && (Math.abs(nx - cursorPrev[0]) > 1e-3 || Math.abs(ny - cursorPrev[1]) > 1e-3))) ultimaAct = t;
    cursorPrev = [nx, ny]; gestoPrev = est.gesto;
    return t - ultimaAct;
  }

  function ojos(set, v) {
    if (!(v > 0.001)) return;
    if (typeof ctx.tieneExpr !== 'function' || ctx.tieneExpr('blink')) set('blink', v);
    else { set('blinkLeft', v); set('blinkRight', v); }
  }

  const mod = {
    nombre: 'idles',
    orden: 20,

    alCargar() {
      actual = null; salientes = []; proximo = null; unico = null; unicoPrev = null; micro = null; proxMicro = null;
      // Un modelo que se carga con ella ya dormida no bosteza: no "se está durmiendo".
      let e = null;
      try { e = typeof ctx.estado === 'function' ? ctx.estado() : null; } catch (_) { e = null; }
      dormidaAntes = !!(e && e.dormida);
    },
    alDescargar() { unico = null; unicoPrev = null; micro = null; },

    pose(out, dt, t, est = {}) {
      tUlt = t;
      const gp = clamp(num(est.gestoPeso), 0, 1), dp = clamp(num(est.dragPeso), 0, 1), sb = clamp(num(est.sleepBlend), 0, 1);
      if (!actual) cambiar(siguienteDeLaRueda(), t);

      // Estiramiento tras mucho rato quieta (una vez por periodo de inactividad)
      const inact = inactivo(t, est);
      if (inact < cfg.estirarTras) armadoEstirar = true;
      else if (armadoEstirar && !unico && activo && !est.dormida && !est.drag && !est.hablando) { armadoEstirar = false; lanzarUnico('estirarse', t); }
      // Bostezo al empezar a dormir; si la despiertan a mitad (voz, toque), se funde fuera
      if (est.dormida && !dormidaAntes && activo && t - ultimoBostezo > 5 && !(unico && unico.tipo === 'bostezo')) lanzarUnico('bostezo', t);
      else if (!est.dormida && dormidaAntes && unico && unico.tipo === 'bostezo') soltarUnico(t);
      dormidaAntes = !!est.dormida;

      // Rueda de variantes (espera a que acabe el one-shot)
      if (proximo !== null && t >= proximo && !unico && activo) cambiar(siguienteDeLaRueda(), t);

      // Pesos
      pesoActivo = clamp(pesoActivo + (activo ? 1 : -1) * num(dt) / Math.max(1e-3, cfg.mezcla), 0, 1);
      const inhObj = est.inh && finito(est.inh.idle) ? clamp(est.inh.idle, 0, 1) : 1;
      pesoInh = clamp(smoothDamp(pesoInh, inhObj, velInh, 0.5, dt), 0, 1);
      A = smoothstep(pesoActivo) * pesoInh;
      dpUlt = dp;
      W = A * (1 - 0.7 * gp) * (1 - dp) * (1 - sb);

      // One-shots (estiramiento, bostezo): ocupan su peso y el resto del idle cede
      if (unico && t - unico.t0 >= unico.dur) unico = null;
      if (unicoPrev && t - unicoPrev.t1 >= SALIDA_UNICO) unicoPrev = null;
      ocupacion = 0;
      for (const x of unicosEn(t)) {
        mezclarPoses(out, poseVariante(x.u.v, t, t - x.u.t0, 1), x.e * x.f);
        ocupacion += x.e;
      }
      ocupacion = clamp(ocupacion, 0, 1);
      const wBase = W * (1 - ocupacion);
      if (wBase > 1e-5) for (const c of capasEn(t)) mezclarPoses(out, poseVariante(c.v, t, t - c.t0, c.lado), c.w * wBase);
      return out;
    },

    expresiones(set, dt, t, est = {}) {
      const acc = {};
      const poner = (expr, w) => { if (!expr || !(w > 1e-4)) return; for (const k in expr) acc[k] = Math.max(acc[k] || 0, expr[k] * w); };
      const wBase = W * (1 - ocupacion);
      // Hablando, la boca y los ojos son de la voz: ni las variantes ni el bostezo o el
      // estiramiento (aa, blink) ponen expresión (despertada por la voz, abre los ojos).
      if (!est.hablando) for (const c of capasEn(t)) poner(c.v.expr, c.w * wBase);
      if (!est.hablando) for (const x of unicosEn(t)) poner(x.u.v.expr, x.e * x.f);

      // Microexpresiones
      if (proxMicro === null) proxMicro = t + azar(cfg.microMin, cfg.microMax);
      if (!micro && t >= proxMicro) {
        if (!est.hablando && !est.drag && !est.dormida && W > 0.3 && activo) micro = { tipo: bolsaMicro.siguiente(), t0: t };
        proxMicro = t + azar(cfg.microMin, cfg.microMax);
      }
      if (micro) {
        const tl = t - micro.t0;
        const e = micro.tipo === 'entrecerrar' ? envolvente(tl, 0.4, 1.0, 0.4) : envolvente(tl, 0.2, 0.5, 0.2);
        if ((micro.tipo === 'entrecerrar' && tl >= 1.8) || (micro.tipo === 'sonrisa' && tl >= 0.9)) micro = null;
        else if (micro.tipo === 'entrecerrar') poner({ blink: 0.25 }, e * W);
        else poner({ happy: 0.25, ee: 0.15 }, e * W * (est.hablando ? 0 : 1));
      }

      for (const k in acc) {
        if (k === 'blink') ojos(set, acc[k]);
        else if (acc[k] > 1e-3) set(k, acc[k], 'max');
      }
    },

    ocupado() { return !!unico || !!unicoPrev; },

    api: {
      /** Fuerza una variante (índice 0..9 o nombre); sin argumento devuelve la actual. */
      variante(n) {
        if (n === undefined || n === null) return unico ? unico.v.nombre : (actual ? actual.v.nombre : null);
        const i = typeof n === 'number' ? (n | 0) : VARIANTES.findIndex((v) => v.nombre === String(n));
        if (i < 0 || i >= VARIANTES.length) return null;
        if (i === INDICE_ESTIRARSE) return lanzarUnico('estirarse', tUlt);
        return cambiar(i, tUlt);
      },
      /** set({activo, cambioMin, cambioMax, mezcla, microMin, microMax, estirarTras}) */
      set(opts = {}) {
        if (opts && typeof opts === 'object') {
          if ('activo' in opts) activo = !!opts.activo;
          for (const k of ['cambioMin', 'cambioMax', 'mezcla', 'microMin', 'microMax', 'estirarTras']) {
            const v = Number(opts[k]);
            if (k in opts && finito(v) && v >= 0) cfg[k] = v;
          }
          if (cfg.cambioMax < cfg.cambioMin) cfg.cambioMax = cfg.cambioMin;
          if (cfg.microMax < cfg.microMin) cfg.microMax = cfg.microMin;
        }
        return { activo, ...cfg };
      },
      bostezar() { return lanzarUnico('bostezo', tUlt); },
      estirar() { return lanzarUnico('estirarse', tUlt); },
      estado() {
        return {
          activo, peso: W, variante: actual ? actual.v.nombre : null, lado: actual ? actual.lado : 1,
          unico: unico ? unico.v.nombre : null, micro: micro ? micro.tipo : null,
          capas: capasEn(tUlt).map((c) => ({ nombre: c.v.nombre, peso: c.w })),
          proximo,
        };
      },
      historial() { return historial.map((h) => ({ ...h })); },
    },
  };
  return mod;
}

export default instalar;
