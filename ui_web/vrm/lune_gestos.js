/*
 * ui_web/vrm/lune_gestos.js — mezclador de gestos con fundidos por destino
 * ("Smooth Anim Transitions" de Mate-Engine, corte 3).
 *
 * Hasta ahora lune_vrm.js cambiaba de gesto de golpe: setEstado sustituía
 * gestoActual y solo suavizaba el PESO (0→1). Pasar de 'happy' a 'angry' a mitad
 * de un fundido saltaba de una pose a otra en un frame. Este mezclador guarda los
 * gestos salientes como capas con el peso que tenían en el instante del cambio y
 * los funde a la vez que entra el nuevo: la pose es continua aunque se cambie a
 * mitad, y los gestos salientes siguen moviéndose (la risa se apaga, no se congela).
 *
 * Tiempos de fundido (s), como las transiciones del Animator de Mate-Engine:
 *   0.25 por defecto · 0.5 hacia 'normal' · 0.45 hacia 'sad' o 'bored' ·
 *   1.0 al salir de 'laughing' (si se cumplen dos reglas, manda la más lenta).
 * La entrada es un smoothstep; las capas salientes bajan con (1 − smoothstep)
 * desde el peso que tenían, así que la suma de pesos nunca pasa de 1.
 *
 * Uso (lune_vrm.js):
 *   const mg = crearMezcladorGestos(GESTOS, () => ahora);
 *   mg.cambiar('happy')                     en setEstado; devuelve la duración del fundido
 *   mg.pose(out, ahora, w)                  suma la mezcla × w en `out` (aditivo)
 *   bobY = mg.bob(bobY, dt, ahora, w)       saltito vertical suavizado con suav(dt, 10)
 *   mg.peso(ahora)                          el "gestoPeso" del motor (0..1)
 *   mg.vencido(ahora)                       gesto con `dur` que ya terminó → volver a 'normal'
 *   mg.fundiendo(ahora) · mg.dinamico()     para ocupado()
 *   mg.actual · mg.tLocal(ahora) · mg.capas(ahora) · mg.reiniciar(nombre, t)
 *
 * GESTOS es el mismo objeto de lune_vrm.js: {nombre: {pose, fn?(tLocal, out), bob?, dur? (ms)}}.
 * Un nombre que no está en GESTOS ('normal', 'sleeping'…) es "sin gesto": solo funde
 * lo anterior hacia cero. Sin imports de three (tests/js/gestos.test.mjs en Node).
 */
import { clamp, suav, smoothstep, mezclarPoses } from './lune_modulos.js';

const finito = Number.isFinite;
const PESO_MIN = 1e-4;          // capas por debajo de esto se descartan
const MAX_CAPAS = 6;            // salientes simultáneas (cambios muy seguidos)

/** Duraciones de fundido (s). `hacia` = por destino, `desde` = por origen. */
export const TIEMPOS_FUNDIDO = Object.freeze({
  defecto: 0.25,
  hacia: Object.freeze({ normal: 0.5, sad: 0.45, bored: 0.45 }),
  desde: Object.freeze({ laughing: 1.0 }),
});

/** Segundos que tarda el fundido de `desde` a `hacia` (manda la regla más lenta). */
export function duracionFundido(desde, hacia, tiempos = TIEMPOS_FUNDIDO) {
  const t = tiempos || TIEMPOS_FUNDIDO;
  const def = finito(t.defecto) ? t.defecto : TIEMPOS_FUNDIDO.defecto;
  const h = t.hacia && Object.prototype.hasOwnProperty.call(t.hacia, hacia) ? t.hacia[hacia] : undefined;
  const d = t.desde && Object.prototype.hasOwnProperty.call(t.desde, desde) ? t.desde[desde] : undefined;
  let r = finito(h) ? h : def;
  if (finito(d)) r = Math.max(r, d);
  return Math.max(0, r);
}

function unirTiempos(extra) {
  if (!extra || typeof extra !== 'object') return TIEMPOS_FUNDIDO;
  return {
    defecto: finito(extra.defecto) ? extra.defecto : TIEMPOS_FUNDIDO.defecto,
    hacia: { ...TIEMPOS_FUNDIDO.hacia, ...(extra.hacia || {}) },
    desde: { ...TIEMPOS_FUNDIDO.desde, ...(extra.desde || {}) },
  };
}

/**
 * @param GESTOS   {nombre: {pose, fn?, bob?, dur?}}
 * @param reloj    () => segundos; se usa cuando no se pasa `t` (por defecto 0)
 * @param opciones {tiempos?: {defecto, hacia, desde}, maxCapas?: n}
 */
export function crearMezcladorGestos(GESTOS = {}, reloj = null, opciones = {}) {
  const gestos = GESTOS || {};
  const ahora = typeof reloj === 'function' ? reloj : () => 0;
  const tiempos = unirTiempos(opciones.tiempos);
  const maxCapas = Math.max(1, (opciones.maxCapas | 0) || MAX_CAPAS);

  let actual = { nombre: 'normal', g: null, t0: 0 };
  let salientes = [];           // [{nombre, g, t0, w0}]: w0 = peso en el instante del último cambio
  let tCambio = 0, durF = 0;

  const tiempo = (t) => { if (finito(t)) return t; const r = Number(ahora()); return finito(r) ? r : 0; };
  const gestoDe = (n) => (Object.prototype.hasOwnProperty.call(gestos, n) && gestos[n] && gestos[n].pose ? gestos[n] : null);

  /** Progreso del fundido en curso con entrada smoothstep (1 = terminado). */
  function entrada(t) {
    if (durF <= 0) return 1;
    return smoothstep(clamp((t - tCambio) / durF, 0, 1));
  }

  /** Capas con su peso efectivo en t: [{nombre, g, t0, w}] (sin tocar el estado). */
  function capasEn(t) {
    const s = entrada(t);
    const res = [];
    if (s < 1) for (const c of salientes) { const w = c.w0 * (1 - s); if (w > PESO_MIN) res.push({ nombre: c.nombre, g: c.g, t0: c.t0, w }); }
    if (actual.g && s > 0) res.push({ nombre: actual.nombre, g: actual.g, t0: actual.t0, w: s });
    return res;
  }

  /** Pose de un gesto en su tiempo local (pose fija + término dinámico). */
  function evaluar(g, tLocal) {
    const tmp = {};
    mezclarPoses(tmp, g.pose, 1);
    if (typeof g.fn === 'function') {
      try { g.fn(Math.max(0, tLocal), tmp); } catch (e) { /* un fn roto no tumba el frame */ }
    }
    return tmp;
  }

  function cambiar(nombre, t) {
    nombre = String(nombre == null || nombre === '' ? 'normal' : nombre);
    const tt = tiempo(t);
    const g = gestoDe(nombre);
    // El mismo gesto persistente otra vez no hace nada; uno con duración (wave) se repite.
    if (nombre === actual.nombre && !(g && g.dur > 0)) return 0;
    const nuevas = capasEn(tt).map((c) => ({ nombre: c.nombre, g: c.g, t0: c.t0, w0: c.w }));
    // Con cambios muy seguidos se descarta la capa más débil (su salto es ≤ su peso).
    while (nuevas.length > maxCapas) {
      let k = 0;
      for (let i = 1; i < nuevas.length; i++) if (nuevas[i].w0 < nuevas[k].w0) k = i;
      nuevas.splice(k, 1);
    }
    durF = duracionFundido(actual.nombre, nombre, tiempos);
    salientes = nuevas;
    tCambio = tt;
    actual = { nombre, g, t0: tt };
    return durF;
  }

  /** Suma en `out` la mezcla de gestos × w. */
  function pose(out, t, w = 1) {
    const tt = tiempo(t);
    if (entrada(tt) >= 1 && salientes.length) salientes = [];     // fundido terminado
    if (!out || !finito(w) || w <= 0) return out;
    for (const c of capasEn(tt)) mezclarPoses(out, evaluar(c.g, tt - c.t0), c.w * w);
    return out;
  }

  /** Peso total de gesto (0..1): lo que el motor llama gestoPeso. */
  function peso(t) {
    let s = 0;
    for (const c of capasEn(tiempo(t))) s += c.w;
    return clamp(s, 0, 1);
  }

  /**
   * Saltito vertical (happy, wave, laughing): objetivo = Σ bob·peso × |sin(2π·2·t)| × w,
   * seguido con un lerp exponencial suav(dt, 10). Devuelve el nuevo desplazamiento.
   */
  function bob(y, dt, t, w = 1) {
    const tt = tiempo(t);
    let amp = 0;
    for (const c of capasEn(tt)) if (finito(c.g.bob)) amp += c.g.bob * c.w;
    const obj = amp * Math.abs(Math.sin(tt * 2 * Math.PI * 2)) * (finito(w) ? Math.max(0, w) : 0);
    const y0 = finito(y) ? y : 0;
    return y0 + (obj - y0) * suav(dt, 10);
  }

  function vencido(t) {
    const g = actual.g;
    return !!(g && finito(g.dur) && g.dur > 0 && (tiempo(t) - actual.t0) * 1000 > g.dur);
  }

  function fundiendo(t) {
    return (salientes.length > 0 || !!actual.g) && entrada(tiempo(t)) < 1;
  }

  function dinamico() {
    if (actual.g && typeof actual.g.fn === 'function') return true;
    return salientes.some((c) => typeof c.g.fn === 'function');
  }

  /** Corta sin fundido (al cargar un modelo nuevo). */
  function reiniciar(nombre = 'normal', t) {
    const tt = tiempo(t);
    nombre = String(nombre || 'normal');
    actual = { nombre, g: gestoDe(nombre), t0: tt };
    salientes = []; tCambio = tt; durF = 0;
  }

  return {
    cambiar, pose, peso, bob, vencido, fundiendo, dinamico, reiniciar,
    tLocal: (t) => tiempo(t) - actual.t0,
    duracion: (desde, hacia) => duracionFundido(desde, hacia, tiempos),
    capas: (t) => capasEn(tiempo(t)).map((c) => ({ nombre: c.nombre, peso: c.w })),
    get actual() { return actual.nombre; },
    get gesto() { return actual.g; },
  };
}
