/*
 * ui_web/vrm/lune_movimiento.js — módulo 'movimiento' del bus VRM ("Dragging
 * Animation" y "Expression based on Movement" de Mate-Engine, corte 3).
 *
 * Todo lo que pasa mientras arrastran la ventana de Lune:
 *   1. Balanceo (AvatarSwayController) con los valores de la ESCENA de Mate-Engine:
 *      muelle 0.75 Hz / ζ 0.5 en las caderas, topes 45° (ladeo) / 20° (cabeceo),
 *      ganancia 0.0167 °/(px/s) en los dos ejes (en ME es 1 °/(px/frame) a 60 fps).
 *   2. Brazos y piernas con retraso: limb = lerp(limb, −lean, suav(dt, 6)), cada
 *      extremidad recortada a ±35° (× aditivo × signo invertirBrazos/invertirPiernas).
 *   3. Pose colgada de las axilas con movimiento: la cabeza mira alrededor (periodos
 *      6.4 y 2.3 s), las manos se retuercen a 0.9 Hz, una rodilla doblada (lado al
 *      azar en cada arrastre). El seguimiento del cursor baja a ×0.4 (inhibe).
 *   4. Cara sostenida: tras 0.3 s de arrastre y rampa de 0.2 s, sad 0.7 + 'oh' en
 *      triángulo 0↔0.4 con periodo de 4 s.
 *   5. Caras por velocidad (filtrada): < 400 px/s relajada, 400–1500 preocupada,
 *      > 1500 asustada (bordes suavizados).
 *   6. Mareo: ≥ 4 inversiones de sentido con |v| > 800 px/s en 1.5 s (en un mismo
 *      eje) → gesto 'dizzy' de 2.5 s (cabeza en círculos, ojos entrecerrados),
 *      cooldown de 10 s y ctx.emitir('mareo', {inversiones, eje}).
 * Sustituye en lune_vrm.js al balanceo de las caderas, los brazos −0.5·leanZ y
 * POSE_ARRASTRE (ver notas de integración). No se balancea con est.sentada.
 *
 * Parámetros: PARAMS_SWAY y PARAMS_MOVIMIENTO son los valores por defecto. Cada clave
 * se lee, por orden: api.params() > ctx.PARAMS (lo que cambia window.luneParams) >
 * defecto. Las sway* usan los MISMOS nombres que PARAMS de lune_vrm.js.
 *
 * est que necesita: drag, dragPeso, dragVx, dragVy (px/s de pantalla, Y hacia abajo,
 * sin filtrar; 0 si no hay arrastre), sleepBlend, sentada. ctx: emitir, PARAMS,
 * tieneExpr(nombre) opcional (para entrecerrar con blinkLeft/Right si no hay 'blink').
 *
 * API (window.luneMod('movimiento', …)):
 *   set({activo}) · params(json?) → efectivos · mareo() fuerza el mareo · estado() · reiniciar()
 *
 * Convención de poses: la de lune_vrm.js (radianes, huesos normalizados VRM 1.0; el
 * motor aplica sXZ al final). Sin imports de three (tests/js/movimiento.test.mjs).
 */
import { clamp, lerp, suav, smoothstep, Muelle, mezclarPoses, sumar, crearAleatorio } from './lune_modulos.js';

const G2R = Math.PI / 180;
const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);
const signo = (v) => (num(v, 1) < 0 ? -1 : 1);

/** Balanceo al arrastrar: valores de la escena de Mate-Engine (Mate Engine Main.unity). */
export const PARAMS_SWAY = Object.freeze({
  swayGanH: 0.0167, swayGanV: 0.0167,       // °/(px/s)
  swayMaxZ: 45, swayMaxX: 20,               // ° (ladeo, cabeceo)
  swayFrec: 0.75, swayZeta: 0.5,            // muelle (Hz, ζ)
  swayFiltro: 12,                           // 1/s: filtro de la velocidad
  invertirH: 1, invertirV: 1,               // ±1
  invertirBrazos: 1, invertirPiernas: 1,    // ±1 (−1 si en un modelo salen al revés)
  brazosAditivo: 1, piernasAditivo: 1,      // 0..1 (armsAdditive/legsAdditive)
  extremidadesMax: 35,                      // ° por eje
  extremidadesRetraso: 6,                   // 1/s (limbLag)
});

export const PARAMS_MOVIMIENTO = Object.freeze({
  seguimientoArrastre: 0.4,                 // × seguimiento del cursor colgada
  caraRetraso: 0.3, caraRampa: 0.2,         // s
  caraSad: 0.7, caraOh: 0.4, caraOhPeriodo: 4,
  velRelajada: 400, velAsustada: 1500,      // px/s
  mareoUmbral: 800, mareoInversiones: 4, mareoVentana: 1.5, mareoDuracion: 2.5, mareoCooldown: 10,
});

const DEFECTOS = Object.freeze({ ...PARAMS_SWAY, ...PARAMS_MOVIMIENTO });

/** Colgada de las axilas (POSE_ARRASTRE de lune_vrm.js) con la rodilla derecha doblada. */
export const POSE_COLGADA = Object.freeze({
  leftUpperArm: [0, 0, 1.6], rightUpperArm: [0, 0, -1.6],
  leftLowerArm: [0, 0.1, 0.3], rightLowerArm: [0, -0.1, -0.3],
  leftUpperLeg: [0.22, 0, 0.05], rightUpperLeg: [-0.08, 0, -0.05],
  leftLowerLeg: [0.2, 0, 0], rightLowerLeg: [0.65, 0, 0],
  spine: [0.06, 0, 0], head: [-0.12, 0, 0],
});

/** Gesto de mareo (por si se quiere añadir a GESTOS de lune_vrm.js como 'dizzy'). */
export const GESTO_MAREO = Object.freeze({
  pose: { spine: [0.04, 0, 0] },
  fn: (t, o) => {
    const a = TAU * 0.9 * t;
    sumar(o, 'head', 0.09 * Math.sin(a), 0, 0.09 * Math.cos(a));       // círculo: el peso entra desde 0
    sumar(o, 'neck', 0.035 * Math.sin(a), 0, 0.035 * Math.cos(a));
    sumar(o, 'upperChest', 0, 0, 0.03 * Math.sin(a * 0.5));
  },
  dur: 2500,
});

function espejoHueso(h) {
  if (h.startsWith('left')) return 'right' + h.slice(4);
  if (h.startsWith('right')) return 'left' + h.slice(5);
  return h;
}
function espejar(pose) {
  const out = {};
  for (const h in pose) { const p = pose[h]; if (p) out[espejoHueso(h)] = [p[0] || 0, -(p[1] || 0), -(p[2] || 0)]; }
  return out;
}

/** Pose colgada con movimiento en el tiempo local del arrastre (lado −1 = espejada). */
export function poseColgada(tl, lado = 1) {
  const o = {};
  mezclarPoses(o, POSE_COLGADA, 1);
  const yaw = 0.22 * Math.sin(TAU * tl / 6.4) + 0.07 * Math.sin(TAU * tl / 2.3);
  sumar(o, 'head', 0.05 * Math.sin(TAU * tl / 2.3 + 1.1), yaw, 0.04 * Math.sin(TAU * tl / 6.4 + 0.5));
  sumar(o, 'neck', 0, 0.3 * yaw, 0);
  const m = Math.sin(TAU * 0.9 * tl), m2 = Math.sin(TAU * 0.9 * tl + 1.2);
  sumar(o, 'leftHand', 0.25 * m, 0, 0.15 * m2);
  sumar(o, 'rightHand', -0.25 * m, 0, 0.15 * m2);
  sumar(o, 'leftLowerArm', 0, 0.06 * m, 0); sumar(o, 'rightLowerArm', 0, 0.06 * m, 0);
  sumar(o, 'leftLowerLeg', 0.06 * Math.sin(TAU * 0.45 * tl), 0, 0);
  sumar(o, 'rightLowerLeg', 0.06 * Math.sin(TAU * 0.45 * tl + 2), 0, 0);
  return lado < 0 ? espejar(o) : o;
}

/** Onda triangular 0 → amp → 0 con periodo `periodo` (empieza en 0). */
export function triangulo(t, amp, periodo) {
  if (!finito(t) || !(periodo > 0)) return 0;
  let p = (t / periodo) % 1; if (p < 0) p += 1;
  return amp * (p < 0.5 ? 2 * p : 2 - 2 * p);
}

// ── Física del balanceo (pura) ─────────────────────────────────────────────────

/**
 * Balanceo + extremidades con retraso, en grados. `leer(clave)` da los parámetros
 * (PARAMS_SWAY por defecto). paso(dt, activo, vx, vy) con vx/vy en px/s.
 */
export class Balanceo {
  constructor(leer = (k) => PARAMS_SWAY[k]) {
    this.leer = leer;
    this.muelleZ = new Muelle(leer('swayFrec'), leer('swayZeta'), 90);
    this.muelleX = new Muelle(leer('swayFrec'), leer('swayZeta'), 90);
    this.reiniciar();
  }

  reiniciar() {
    this.fvx = 0; this.fvy = 0; this.leanZ = 0; this.leanX = 0; this.limbZ = 0; this.limbX = 0;
    this.muelleZ.reiniciar(); this.muelleX.reiniciar();
    return this;
  }

  paso(dt, activo, vx, vy) {
    const L = this.leer;
    if (!finito(dt) || dt <= 0) return this;
    const f = L('swayFrec'), z = L('swayZeta');
    this.muelleZ.configurar(f, z); this.muelleX.configurar(f, z);
    const k = suav(dt, L('swayFiltro'));
    this.fvx += ((activo ? num(vx) : 0) - this.fvx) * k;
    this.fvy += ((activo ? num(vy) : 0) - this.fvy) * k;
    const maxZ = Math.abs(num(L('swayMaxZ'), 45)), maxX = Math.abs(num(L('swayMaxX'), 20));
    const objZ = activo ? clamp(signo(L('invertirH')) * this.fvx * num(L('swayGanH')), -maxZ, maxZ) : 0;
    const objX = activo ? clamp(signo(L('invertirV')) * this.fvy * num(L('swayGanV')), -maxX, maxX) : 0;
    this.leanZ = this.muelleZ.paso(objZ, dt);
    this.leanX = this.muelleX.paso(objX, dt);
    const kl = suav(dt, L('extremidadesRetraso'));
    this.limbZ = lerp(this.limbZ, -this.leanZ, kl);
    this.limbX = lerp(this.limbX, -this.leanX, kl);
    return this;
  }

  /** [x°, z°] para una extremidad: clamp(limb·aditivo, ±max)·signo (sin peso). */
  extremidad(aditivo, sgn, max = this.leer('extremidadesMax')) {
    const m = Math.abs(num(max, 35)), a = num(aditivo, 1), s = signo(sgn);
    return [clamp(this.limbX * a, -m, m) * s || 0, clamp(this.limbZ * a, -m, m) * s || 0];
  }

  get velocidad() { return Math.hypot(this.fvx, this.fvy); }
}

// ── Detector de mareo (puro) ───────────────────────────────────────────────────

/**
 * Cuenta inversiones de sentido por eje con |v| > umbral. Una inversión es un
 * cambio de signo entre dos muestras fuertes separadas ≤ ventana s. Se dispara con
 * ≥ `inversiones` en un mismo eje dentro de la ventana y fuera del cooldown.
 */
export class DetectorMareo {
  constructor({ umbral = 800, inversiones = 4, ventana = 1.5, cooldown = 10 } = {}) {
    this.umbral = umbral; this.inversiones = inversiones; this.ventana = ventana; this.cooldown = cooldown;
    this.hasta = -Infinity;
    this.ultimas = 0; this.eje = null;
    this.disparo = null;          // último disparo: {inversiones, eje, t}
    this.reiniciarEjes();
  }

  reiniciarEjes() {
    this.ejes = [{ s: 0, t: -Infinity, inv: [] }, { s: 0, t: -Infinity, inv: [] }];
    this.ultimas = 0;
  }

  /** Muestra de velocidad (px/s) en t (s). Devuelve true si toca marearse ahora. */
  muestra(vx, vy, t) {
    if (!finito(t)) return false;
    let n = 0, eje = null;
    const vs = [vx, vy];
    for (let i = 0; i < 2; i++) {
      const e = this.ejes[i], v = vs[i];
      while (e.inv.length && t - e.inv[0] > this.ventana) e.inv.shift();
      if (finito(v) && Math.abs(v) > this.umbral) {
        const s = v > 0 ? 1 : -1;
        if (e.s !== 0 && s !== e.s && t - e.t <= this.ventana) e.inv.push(t);
        e.s = s; e.t = t;
      }
      if (e.inv.length > n) { n = e.inv.length; eje = i ? 'y' : 'x'; }
    }
    this.ultimas = n; this.eje = eje;
    if (n >= this.inversiones && t >= this.hasta) {
      this.hasta = t + this.cooldown;
      this.disparo = { inversiones: n, eje, t };
      this.reiniciarEjes();
      return true;
    }
    return false;
  }
}

// ── Módulo ─────────────────────────────────────────────────────────────────────

/** instalar(ctx, opciones?) → módulo 'movimiento'. opciones: {aleatorio, semilla, params}. */
export function instalar(ctx = {}, opciones = {}) {
  const azar = typeof opciones.aleatorio === 'function' ? opciones.aleatorio
    : opciones.semilla !== undefined ? crearAleatorio(opciones.semilla)
      : typeof ctx.aleatorio === 'function' ? ctx.aleatorio : Math.random;
  const propios = {};
  const leer = (k) => {
    if (Object.prototype.hasOwnProperty.call(propios, k)) return propios[k];
    const P = ctx.PARAMS;
    if (P && finito(P[k])) return P[k];
    return DEFECTOS[k];
  };
  function fijar(json) {
    let o = json;
    if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { o = null; } }
    if (!o || typeof o !== 'object') return;
    for (const k of Object.keys(DEFECTOS)) {
      if (!Object.prototype.hasOwnProperty.call(o, k)) continue;
      if (o[k] === null) { delete propios[k]; continue; }             // null = volver a ctx.PARAMS / defecto
      const v = Number(o[k]);
      if (finito(v)) propios[k] = v;
    }
  }
  if (opciones.params) fijar(opciones.params);

  const bal = new Balanceo(leer);
  const det = new DetectorMareo();
  let activo = true, pesoActivo = 1, A = 1;
  let dragAntes = false, tDrag0 = -Infinity, lado = 1;
  let cara = 0, wRelax = 1, wPreoc = 0, wAsust = 0;
  let mareoT0 = -Infinity, wMareo = 0, dp = 0, sb = 0;
  let tUlt = 0, brazos = [0, 0], piernas = [0, 0], wLean = 0;

  function lanzarMareo(t, datos = {}) {
    mareoT0 = t;
    try { ctx.emitir && ctx.emitir('mareo', datos); } catch (e) { /* sin canal */ }
  }

  function ojos(set, v) {
    if (!(v > 0.001)) return;
    if (typeof ctx.tieneExpr !== 'function' || ctx.tieneExpr('blink')) set('blink', v);
    else { set('blinkLeft', v); set('blinkRight', v); }
  }

  const mod = {
    nombre: 'movimiento',
    orden: 30,

    alCargar() { bal.reiniciar(); cara = 0; wMareo = 0; mareoT0 = -Infinity; },
    alDescargar() { bal.reiniciar(); det.reiniciarEjes(); },

    pose(out, dt, t, est = {}) {
      tUlt = t;
      const drag = !!est.drag;
      dp = clamp(num(est.dragPeso), 0, 1);
      sb = clamp(num(est.sleepBlend), 0, 1);
      if (drag && !dragAntes) { tDrag0 = t; lado = azar() < 0.5 ? -1 : 1; det.reiniciarEjes(); }
      if (!drag && dragAntes) det.reiniciarEjes();
      dragAntes = drag;
      pesoActivo = clamp(pesoActivo + (activo ? 1 : -1) * num(dt) / 0.5, 0, 1);
      A = smoothstep(pesoActivo);

      const vx = drag ? num(est.dragVx) : 0, vy = drag ? num(est.dragVy) : 0;
      bal.paso(dt, drag && activo && !est.sentada, vx, vy);

      // Mareo al agitarla
      det.umbral = leer('mareoUmbral'); det.inversiones = leer('mareoInversiones');
      det.ventana = leer('mareoVentana'); det.cooldown = leer('mareoCooldown');
      if (drag && activo && det.muestra(vx, vy, t)) lanzarMareo(t, { inversiones: det.disparo.inversiones, eje: det.disparo.eje });
      const tm = t - mareoT0, dur = leer('mareoDuracion');
      wMareo = tm >= 0 && tm < dur ? smoothstep(clamp(tm / 0.25, 0, 1)) * (1 - smoothstep(clamp((tm - (dur - 0.5)) / 0.5, 0, 1))) : 0;

      // Cara sostenida (sube con rampa; al soltar baja suave)
      const caraObj = drag && activo ? smoothstep(clamp((t - tDrag0 - leer('caraRetraso')) / Math.max(1e-3, leer('caraRampa')), 0, 1)) : 0;
      cara = caraObj >= cara ? caraObj : cara + (caraObj - cara) * suav(dt, 6);

      // Caras por velocidad (filtrada), bordes de ±50 / ±100 px/s
      const v = bal.velocidad, vr = leer('velRelajada'), va = leer('velAsustada');
      const a = smoothstep(vr - 50, vr + 50, v), b = smoothstep(va - 100, va + 100, v);
      const kc = suav(dt, 5);
      wRelax += ((1 - a) - wRelax) * kc; wPreoc += ((a - b) - wPreoc) * kc; wAsust += (b - wAsust) * kc;

      // Caderas + extremidades con retraso
      wLean = Math.max(dp, Math.min(1, (Math.abs(bal.leanZ) + Math.abs(bal.leanX)) / 2)) * A;
      brazos = bal.extremidad(leer('brazosAditivo'), leer('invertirBrazos'));
      piernas = bal.extremidad(leer('piernasAditivo'), leer('invertirPiernas'));
      if (wLean > 1e-5) {
        const g = G2R * wLean;
        sumar(out, 'hips', bal.leanX * g, 0, bal.leanZ * g);
        sumar(out, 'leftUpperArm', brazos[0] * g, 0, brazos[1] * g);
        sumar(out, 'rightUpperArm', brazos[0] * g, 0, brazos[1] * g);
        sumar(out, 'leftUpperLeg', piernas[0] * g, 0, piernas[1] * g);
        sumar(out, 'rightUpperLeg', piernas[0] * g, 0, piernas[1] * g);
      }
      // Pose colgada con movimiento
      if (dp * A > 1e-4) mezclarPoses(out, poseColgada(t - tDrag0, lado), dp * A);
      // Mareo: cabeza en círculos
      const wm = wMareo * A * (1 - sb);
      if (wm > 1e-4) {
        const tmp = {}; mezclarPoses(tmp, GESTO_MAREO.pose, 1); GESTO_MAREO.fn(tm, tmp);
        mezclarPoses(out, tmp, wm);
      }
      return out;
    },

    expresiones(set, dt, t, est = {}) {
      const k = cara * (1 - sb) * A;
      if (k > 1e-3) {
        const tri = triangulo(t - tDrag0, leer('caraOh'), leer('caraOhPeriodo'));
        set('sad', leer('caraSad') * (1 - 0.6 * wAsust) * k, 'max');
        set('oh', Math.max(tri, 0.5 * wAsust) * k, 'max');
        if (wRelax > 1e-3) set('relaxed', 0.3 * wRelax * k, 'max');
        const sor = 0.25 * wPreoc + 0.8 * wAsust;
        if (sor > 1e-3) set('surprised', sor * k, 'max');
      }
      const wm = wMareo * (1 - sb) * A;
      if (wm > 1e-3) {
        ojos(set, 0.45 * wm);
        set('sad', 0.3 * wm, 'max');
        set('oh', 0.2 * wm, 'max');
      }
    },

    inhibe(est = {}) {
      const d = clamp(num(est.dragPeso), 0, 1) * A;
      return {
        seguimiento: lerp(1, clamp(leer('seguimientoArrastre'), 0, 1), d) * (1 - 0.7 * wMareo),
        caricia: 1 - wMareo,
      };
    },

    ocupado() {
      if (A <= 0 && !activo) return false;
      return cara > 0.01 || wMareo > 0.001
        || Math.abs(bal.leanZ) + Math.abs(bal.leanX) > 0.05 || Math.abs(bal.limbZ) + Math.abs(bal.limbX) > 0.05;
    },

    api: {
      set(opts = {}) {
        if (opts && typeof opts === 'object' && 'activo' in opts) activo = !!opts.activo;
        return { activo };
      },
      /** params({clave: valor|null}) sobrescribe (null = quitar); sin args → valores efectivos. */
      params(json) {
        if (json !== undefined) fijar(json);
        const r = {};
        for (const k of Object.keys(DEFECTOS)) r[k] = leer(k);
        return r;
      },
      mareo() { lanzarMareo(tUlt, { inversiones: 0, eje: null, forzado: true }); return true; },
      reiniciar() { bal.reiniciar(); det.reiniciarEjes(); det.hasta = -Infinity; cara = 0; mareoT0 = -Infinity; wMareo = 0; },
      estado() {
        return {
          activo, leanZ: bal.leanZ, leanX: bal.leanX, limbZ: bal.limbZ, limbX: bal.limbX,
          brazos: brazos.slice(), piernas: piernas.slice(), pesoBalanceo: wLean,
          velocidad: bal.velocidad, cara,
          caras: { relajada: wRelax, preocupada: wPreoc, asustada: wAsust },
          mareo: wMareo > 0, pesoMareo: wMareo, inversiones: det.ultimas, lado,
        };
      },
    },
  };
  return mod;
}

export default instalar;
