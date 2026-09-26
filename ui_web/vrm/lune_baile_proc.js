/*
 * ui_web/vrm/lune_baile_proc.js — módulo 'baileProc' del bus VRM: bailes procedurales
 * al pulso de la música (cortes 5 y 6; «Dance» de Mate-Engine sin clips).
 *
 * Python (ui/baile_qt.ControlBaile → ui/companion.py) enciende el baile con
 * window.luneBailar(on, opts) y le pasa el pulso (nucleo/pulso.py) como mucho 2 veces
 * por segundo con window.lunePulso(bpm, fase, energia). Entre medias el pulso se
 * extrapola con LuneRitmo.crearReloj (ui_web/lune_ritmo.js, script clásico que la
 * página carga antes; sin él, un metrónomo interno).
 *
 * 8 estilos (ESTILOS), todos ADITIVOS sobre la A-pose y en la convención de
 * lune_vrm.js (radianes, huesos normalizados, VRM 1.0: el motor aplica sXZ a X y Z,
 * así que en los VRM 0.x sale igual sin tocar nada aquí). Amplitud × (0.4 + 0.6·energía).
 *   rebote        rodillas y cabeza al pulso, bote hacia abajo
 *   vaiven        balanceo lateral de torso y caderas (2 pulsos por lado a lado)
 *   brazos_arriba bombeo de brazos a media altura; SOLO un pulso y medio de cada
 *                 8 (1 compás de 2) suben por encima de la horizontal
 *   palmas        palmas delante del pecho en cada pulso
 *   cadera        caderas a un lado y a otro con contrapeso del torso
 *   cabeceo       cabeceo marcado al pulso y hombros
 *   puno_alterno  puñetazos alternos hacia DELANTE, a la altura del pecho
 *   paso_lateral  paso a un lado y a otro (±2.5 cm) con la pierna que abre
 * Los brazos NUNCA pasan de la horizontal salvo en el golpe breve de brazos_arriba
 * (tests/js/baile_proc.test.mjs lo comprueba con matrices, VRM 1.0 y 0.x).
 *
 * Mezcla: el peso entra con suav(5) y sale con suav(8); el arrastre (est.drag), la
 * pantalla grande (est.grande) o estar dormida (sleepBlend > 0.5) lo llevan a 0 (el
 * arrastre, con suav(12): lo corta). Con `cambiar`, cada `cambiarS` s pasa al siguiente
 * estilo (Bolsa sin repetir) con 2 s de fundido (smoothstep).
 *   inhibe  {idle: 1 − peso, seguimiento: 1 − 0.3·peso}
 *   ocupado mientras baile o quede peso (el motor no baja a fpsReposo)
 *   bote    en trasPose, sumado a vrm.scene.position.y (animar lo reescribe cada frame);
 *           el paso lateral mueve vrm.scene.position.x y lo deshace al acabar
 *   encuadre ctx.encuadrar('cuerpo', true) al empezar y ctx.encuadrar(null) cuando el
 *           peso llega a 0 (opciones.encuadrar = false lo desactiva: barra lateral)
 *   cara    happy × 0.3 × peso ('max': no baja lo que ponga Lune)
 *   est.baile = baila o le queda peso
 *
 * API (window.luneMod('baileProc', …) y las funciones de la página):
 *   bailar(on, {estilo, cambiar, cambiarS|cambiar_s, particulas}) → bool
 *   pulso(bpm, fase, energia) → bool       · estilo(nombre?) → nombre actual
 *   estado() → {activo, peso, estilo, previo, mezcla, bpm, pulsos, energia, particulas}
 * Eventos: ctx.emitir('baile', {on, estilo}) (solo para el log de Python).
 * opciones.alGolpe(energia): en cada pulso con peso > 0.5 y partículas (notas ♪).
 *
 * Los tiempos (cambio de estilo, fundido) y el pulso que llega por la API se aplican
 * en el siguiente frame: el reloj es el del motor, que el módulo solo ve en los hooks.
 *
 * poseEstilo(nombre, pulsos, energia, out) es PURA (sin estado): `pulsos` es la cuenta
 * continua de pulsos (13.4 = 40 % del pulso 13). desplazamiento(…) → {x, y} en metros.
 * Sin imports de three (Node: tests/js/baile_proc.test.mjs).
 */
import { clamp, lerp, suav, smoothstep, Bolsa, sumar, mezclarPoses, interpolarPoses } from './lune_modulos.js';

export const NOMBRE = 'baileProc';
export const ORDEN = 40;

export const ESTILOS = Object.freeze([
  'rebote', 'vaiven', 'brazos_arriba', 'palmas', 'cadera', 'cabeceo', 'puno_alterno', 'paso_lateral',
]);

export const PARAMS_BAILE = Object.freeze({
  entrada: 5,           // suav del peso al empezar
  salida: 8,            // suav del peso al acabar
  corte: 12,            // suav hacia 0 al arrastrarla
  fundido: 2,           // s de fundido entre estilos
  cambiarS: 15, cambiarMin: 5, cambiarMax: 300,
  bpm: 120,             // metrónomo sin pulso de Python
  felicidad: 0.3,       // happy × peso
  seguimiento: 0.3,     // cuánto baja el seguimiento del cursor
});

const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

// ── Curvas del pulso (b = pulsos continuos) ────────────────────────────────────

/** 1 justo en el pulso, 0 a mitad; `k` lo afila. */
export const golpe = (b, k = 2) => Math.pow((1 + Math.cos(TAU * b)) / 2, k);
/** 0 en el pulso, 1 a mitad (el contrario de golpe con k = 1). */
const entre = (b) => (1 - Math.cos(TAU * b)) / 2;
/** ±1 en pulsos alternos (periodo de 2 pulsos). */
const lado = (b) => Math.cos(Math.PI * b);
/** Campana suave de 0 a 1 centrada en c con radio r (cos²). */
const campana = (x, c, r) => (Math.abs(x - c) >= r ? 0 : Math.cos((Math.PI / 2) * (x - c) / r) ** 2);
const amplitud = (e) => 0.4 + 0.6 * clamp(num(e, 0.5), 0, 1);

/**
 * Suma una rotación al brazo izquierdo en su convención y su espejo al derecho
 * (x, −y, −z): así z > 0 SUBE los dos brazos y y < 0 los lleva hacia delante.
 * `sufijo` = 'UpperArm' | 'LowerArm' | 'UpperLeg' | 'LowerLeg'.
 */
function par(out, sufijo, x, y, z) {
  sumar(out, 'left' + sufijo, x, y, z);
  sumar(out, 'right' + sufijo, x, -y, -z);
}
/** Solo un lado, en la convención del izquierdo (el derecho se espeja). */
function uno(out, izq, sufijo, x, y, z) {
  if (izq) sumar(out, 'left' + sufijo, x, y, z);
  else sumar(out, 'right' + sufijo, x, -y, -z);
}
/** Rodillas: muslo adelante y espinilla atrás (el pie queda bajo la cadera). */
function rodillas(out, d) {
  par(out, 'UpperLeg', -0.24 * d, 0, 0);
  par(out, 'LowerLeg', 0.46 * d, 0, 0);
}

// ── Estilos ────────────────────────────────────────────────────────────────────
// Cada uno: (out, b, A) con A = amplitud por energía. Los ángulos de los brazos son
// DELTAS sobre la A-pose (brazo a −1.15 en z, antebrazo a −0.28 en y).

const POSES = {
  rebote(out, b, A) {
    const d = golpe(b, 2) * A, h = entre(b) * A;
    sumar(out, 'head', 0.08 * d, 0, 0); sumar(out, 'neck', 0.03 * d, 0, 0);
    sumar(out, 'spine', 0.05 * d, 0, 0);
    rodillas(out, d);
    par(out, 'UpperArm', -0.10 * d, 0, 0.06 + 0.10 * h);       // se abren un poco entre pulsos
    par(out, 'LowerArm', 0, -0.20 * A, 0);
  },

  vaiven(out, b, A) {
    const s = lado(b) * A, d = golpe(b, 2) * A;
    sumar(out, 'spine', 0, 0, 0.09 * s); sumar(out, 'chest', 0, 0, 0.03 * s);
    sumar(out, 'hips', 0, 0, -0.05 * s);
    sumar(out, 'head', 0, 0.05 * s, -0.06 * s); sumar(out, 'neck', 0, 0, -0.02 * s);
    // Brazos un poco separados que se mecen con el cuerpo (uno sube cuando el otro baja).
    uno(out, true, 'UpperArm', 0, 0, 0.14 * A + 0.08 * s);
    uno(out, false, 'UpperArm', 0, 0, 0.14 * A - 0.08 * s);
    par(out, 'LowerArm', 0, -0.25 * A, 0);
    sumar(out, 'leftUpperLeg', 0, 0, 0.03 * s); sumar(out, 'rightUpperLeg', 0, 0, 0.03 * s);
    rodillas(out, 0.4 * d);
  },

  brazos_arriba(out, b, A) {
    const p = golpe(b, 1.5);
    const frase = b - 8 * Math.floor(b / 8);                  // 0..8: frase de 2 compases
    const w = campana(frase, 6.5, 0.75);                      // golpe arriba: ~1.5 pulsos de 8
    // Bombeo a media altura (por debajo de la horizontal) y, en el golpe, arriba.
    const zBase = A * (0.45 + 0.40 * p);                      // total ≥ −0.30 rad: bajo la horizontal
    par(out, 'UpperArm', lerp(-0.35, -0.10, w), 0, lerp(zBase, 1.75, w));
    par(out, 'LowerArm', 0, lerp(-0.35, 0.12, w), 0);
    sumar(out, 'spine', -0.04 * w, 0, 0); sumar(out, 'head', -0.08 * w + 0.04 * p * A, 0, 0);
    rodillas(out, 0.5 * p * A);
  },

  palmas(out, b, A) {
    const c = golpe(b, 3);                                    // palmada seca en el pulso
    // Brazos delante y hacia dentro; el antebrazo cierra en cada pulso.
    par(out, 'UpperArm', -0.15, lerp(-0.9, -1.2, c), 0.55);   // total z ≈ −0.6: bajo la horizontal
    par(out, 'LowerArm', 0, lerp(-0.45, -1.32, c), 0);
    sumar(out, 'head', 0.05 * c * A, 0, 0); sumar(out, 'spine', 0.03 * c * A, 0, 0);
    rodillas(out, 0.45 * c * A);
  },

  cadera(out, b, A) {
    const s = lado(b) * A, d = golpe(b, 2) * A;
    sumar(out, 'hips', 0, 0.07 * s, 0.12 * s);
    sumar(out, 'spine', 0, -0.03 * s, -0.10 * s); sumar(out, 'chest', 0, 0, -0.03 * s);
    sumar(out, 'head', 0, 0, 0.04 * s);
    sumar(out, 'leftUpperLeg', 0, 0, -0.12 * s); sumar(out, 'rightUpperLeg', 0, 0, -0.12 * s);
    // Brazos algo abiertos, con los codos doblados, que van y vienen al revés que la cadera.
    uno(out, true, 'UpperArm', 0.12 * s, 0, 0.20 * A);
    uno(out, false, 'UpperArm', -0.12 * s, 0, 0.20 * A);
    par(out, 'LowerArm', 0, -0.45 * A, 0);
    rodillas(out, 0.3 * d);
  },

  cabeceo(out, b, A) {
    const d = golpe(b, 2.5) * A;
    sumar(out, 'head', 0.16 * d, 0, 0.05 * lado(b) * A); sumar(out, 'neck', 0.06 * d, 0, 0);
    sumar(out, 'spine', 0.04 * d, 0, 0); sumar(out, 'upperChest', 0.02 * d, 0, 0);
    par(out, 'UpperArm', 0, 0, 0.06 * d);                     // hombros arriba en el golpe
    par(out, 'LowerArm', 0, -0.15 * A, 0);
    rodillas(out, 0.5 * d);
  },

  puno_alterno(out, b, A) {
    const k = Math.floor(b), f = b - k;
    const empuje = Math.sin(Math.PI * f) ** 2 * A;             // 0 en el pulso, máximo a mitad
    const izq = k % 2 === 0;
    // Guardia: antebrazos doblados delante; el brazo que golpea se estira hacia delante.
    for (const esIzq of [true, false]) {
      const p = esIzq === izq ? empuje : 0;
      uno(out, esIzq, 'UpperArm', -0.30 - 0.70 * p, 0, 0.15 + 0.35 * p);
      uno(out, esIzq, 'LowerArm', 0, -0.72 + 0.80 * p, 0);
    }
    const giro = (izq ? 1 : -1) * empuje;
    sumar(out, 'spine', 0, -0.10 * giro, 0); sumar(out, 'chest', 0, -0.05 * giro, 0);
    sumar(out, 'head', 0.03 * empuje, 0.06 * giro, 0);
    rodillas(out, 0.3 * golpe(b, 2) * A);
  },

  paso_lateral(out, b, A) {
    const s = Math.sin((Math.PI / 2) * b) * A;                // ciclo de 4 pulsos: izquierda, centro, derecha
    const d = golpe(b, 2) * A;
    sumar(out, 'leftUpperLeg', 0, 0, 0.12 * Math.max(0, s));  // abre la pierna del lado al que va
    sumar(out, 'rightUpperLeg', 0, 0, 0.12 * Math.min(0, s));
    sumar(out, 'hips', 0, 0, 0.05 * s); sumar(out, 'spine', 0, 0, -0.04 * s);
    sumar(out, 'head', 0, 0.04 * s, -0.02 * s);
    uno(out, true, 'UpperArm', 0, 0, 0.12 * A + 0.06 * s);
    uno(out, false, 'UpperArm', 0, 0, 0.12 * A - 0.06 * s);
    par(out, 'LowerArm', 0, -0.30 * A, 0);
    rodillas(out, 0.4 * d);
  },
};

/** Pose del estilo (aditiva, radianes) en `out`. Estilo desconocido → 'rebote'. */
export function poseEstilo(nombre, pulsos, energia, out = {}) {
  const f = POSES[nombre] || POSES.rebote;
  f(out, num(pulsos), amplitud(energia));
  return out;
}

/** Desplazamiento de la raíz del modelo (m): bote vertical y paso lateral. */
export function desplazamiento(nombre, pulsos, energia) {
  const b = num(pulsos), A = amplitud(energia);
  const d = golpe(b, 2) * A;
  switch (nombre) {
    case 'rebote': return { x: 0, y: -0.022 * d };
    case 'vaiven': return { x: 0, y: -0.008 * d };
    case 'brazos_arriba': return { x: 0, y: -0.012 * golpe(b, 1.5) * A + 0.01 * campana(b - 8 * Math.floor(b / 8), 6.5, 0.75) };
    case 'palmas': return { x: 0, y: -0.010 * golpe(b, 3) * A };
    case 'cadera': return { x: 0, y: -0.008 * d };
    case 'cabeceo': return { x: 0, y: -0.012 * d };
    case 'puno_alterno': return { x: 0, y: -0.008 * d };
    case 'paso_lateral': return { x: 0.025 * Math.sin((Math.PI / 2) * b) * A, y: -0.012 * d };
    default: return { x: 0, y: -0.022 * d };
  }
}

/** Metrónomo mínimo si ui_web/lune_ritmo.js no está cargado (misma API que LuneRitmo.crearReloj). */
function relojMinimo(bpm = PARAMS_BAILE.bpm) {
  let pulsos = 0, t = null, b = bpm, e = 0.6, golpeAhora = false;
  const estado = () => ({ pulsos, fase: pulsos - Math.floor(pulsos), bpm: b, energia: e, golpe: golpeAhora, velocidad: b / 60 });
  return {
    avanzar(tt) {
      golpeAhora = false;
      if (!finito(tt)) return estado();
      if (t !== null && tt > t) {
        const antes = pulsos;
        pulsos += (b / 60) * Math.min(tt - t, 0.5);
        golpeAhora = Math.floor(pulsos) > Math.floor(antes);
      }
      t = tt;
      return estado();
    },
    pulso(bb, fase, en) {
      if (finito(Number(bb)) && bb > 0) b = clamp(Number(bb), 40, 240);
      if (finito(Number(en))) e = clamp(Number(en), 0, 1);
      return true;
    },
    metronomo(bb) { if (finito(Number(bb)) && bb > 0) b = clamp(Number(bb), 40, 240); return true; },
    reiniciar() { pulsos = 0; t = null; return this; },
    estado,
  };
}

function nuevoReloj(opciones) {
  if (opciones.reloj && typeof opciones.reloj.avanzar === 'function') return opciones.reloj;
  const R = globalThis.LuneRitmo;
  if (R && typeof R.crearReloj === 'function') return R.crearReloj({ bpm: PARAMS_BAILE.bpm });
  return relojMinimo();
}

/** Estilo válido o null. */
export function estiloValido(n) {
  const s = String(n ?? '').trim().toLowerCase();
  return ESTILOS.includes(s) ? s : null;
}

/**
 * instalar(ctx, opciones) → módulo del bus. opciones (sobre todo para tests y la
 * barra lateral): {reloj, aleatorio, alGolpe(energia), encuadrar: bool, params}.
 */
export function instalar(ctx = {}, opciones = {}) {
  const P = { ...PARAMS_BAILE, ...(opciones.params || {}) };
  const reloj = nuevoReloj(opciones);
  const aleatorio = typeof opciones.aleatorio === 'function' ? opciones.aleatorio
    : typeof ctx.aleatorio === 'function' ? ctx.aleatorio : Math.random;
  const bolsa = new Bolsa(ESTILOS, { aleatorio });
  const conEncuadre = opciones.encuadrar !== false;
  const alGolpe = typeof opciones.alGolpe === 'function' ? opciones.alGolpe : null;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };

  let activo = false, peso = 0;
  let estilo = ESTILOS[0], previo = null, tFundido = null, tCambio = null;   // null = el próximo frame
  let pulsoPendiente = null;
  let cambiar = false, cambiarS = P.cambiarS, particulas = true;
  let ahora = 0, encuadrado = false;
  let ultimo = reloj.estado ? reloj.estado() : { pulsos: 0, energia: 0.6, bpm: P.bpm };
  let offX = 0, sceneX = null;           // lo que el paso lateral sumó a vrm.scene.position.x
  let mezcla = 1;

  function elegir(nombre) {
    const v = estiloValido(nombre);
    if (v) return v;
    let s = bolsa.siguiente();
    if (s === estilo && ESTILOS.length > 1) s = bolsa.siguiente();
    return s || ESTILOS[0];
  }

  function cambiarA(nuevo) {
    if (!nuevo || nuevo === estilo) return;
    previo = estilo; estilo = nuevo; tFundido = null; mezcla = 0;
  }

  function bailar(on, opts = {}) {
    on = !!on;
    const o = opts && typeof opts === 'object' ? opts : {};
    if ('cambiar' in o) cambiar = !!o.cambiar;
    const cs = Number(o.cambiarS ?? o.cambiar_s);
    if (finito(cs)) cambiarS = clamp(cs, P.cambiarMin, P.cambiarMax);
    if ('particulas' in o) particulas = !!o.particulas;
    if (on) {
      const pedido = estiloValido(o.estilo);
      if (!activo) {
        if (peso <= 0.001) {
          // Empieza de cero: estilo directo, reloj nuevo (el primer pulso alinea).
          estilo = pedido || elegir(null); previo = null; mezcla = 1;
          if (typeof reloj.reiniciar === 'function') reloj.reiniciar();
          if (typeof reloj.metronomo === 'function') reloj.metronomo(P.bpm);
        } else if (pedido) cambiarA(pedido);
        tCambio = null;
        if (conEncuadre && !encuadrado && typeof ctx.encuadrar === 'function') {
          try { ctx.encuadrar('cuerpo', true); encuadrado = true; } catch (e) { /* sin cámara */ }
        }
        activo = true;
        emitir('baile', { on: true, estilo });
      } else if (pedido && pedido !== estilo) {
        cambiarA(pedido); tCambio = null;
        emitir('baile', { on: true, estilo });
      }
      return true;
    }
    if (activo) {
      activo = false;
      emitir('baile', { on: false, estilo });
    }
    return true;
  }

  function soltarEncuadre() {
    if (!encuadrado) return;
    encuadrado = false;
    try { if (typeof ctx.encuadrar === 'function') ctx.encuadrar(null); } catch (e) { /* sin cámara */ }
  }

  function pose(out, dt, t, est) {
    ahora = num(t, ahora);
    const e = est || {};
    const d = num(dt);
    const para = !activo || e.drag || e.grande || num(e.sleepBlend) > 0.5;
    const objetivo = para ? 0 : 1;
    const k = objetivo > peso ? suav(d, P.entrada) : suav(d, e.drag ? P.corte : P.salida);
    peso += (objetivo - peso) * k;
    if (objetivo === 0 && peso < 1e-3) peso = 0;
    if (objetivo === 1 && peso > 1 - 1e-4) peso = 1;
    e.baile = activo || peso > 0;

    if (tCambio === null) tCambio = ahora;
    if (previo && tFundido === null) tFundido = ahora;
    if (pulsoPendiente) {
      const [b0, f0, e0] = pulsoPendiente;
      pulsoPendiente = null;
      reloj.pulso(b0, f0, e0, ahora);
    }
    ultimo = reloj.avanzar(ahora);
    if (ultimo.golpe && peso > 0.5 && particulas && alGolpe) {
      try { alGolpe(num(ultimo.energia, 0.5)); } catch (err) { /* sin notas */ }
    }

    if (activo && cambiar && ahora - tCambio >= cambiarS) {
      cambiarA(elegir(null));
      tFundido = ahora;
      tCambio = ahora;
    }
    if (previo) {
      mezcla = smoothstep(clamp((ahora - tFundido) / Math.max(0.01, P.fundido), 0, 1));
      if (mezcla >= 1) { previo = null; mezcla = 1; }
    }

    if (peso <= 0) {
      if (!activo) soltarEncuadre();
      return;
    }
    const b = num(ultimo.pulsos), en = num(ultimo.energia, 0.5);
    let p = poseEstilo(estilo, b, en, {});
    if (previo) p = interpolarPoses(poseEstilo(previo, b, en, {}), p, mezcla);
    mezclarPoses(out, p, peso);
  }

  function desplazamientoActual() {
    if (peso <= 0) return { x: 0, y: 0 };
    const b = num(ultimo.pulsos), en = num(ultimo.energia, 0.5);
    let dz = desplazamiento(estilo, b, en);
    if (previo) {
      const a = desplazamiento(previo, b, en);
      dz = { x: lerp(a.x, dz.x, mezcla), y: lerp(a.y, dz.y, mezcla) };
    }
    return { x: dz.x * peso, y: dz.y * peso };
  }

  function trasPose() {
    const vrm = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
    const pos = vrm && vrm.scene && vrm.scene.position;
    if (!pos) return;
    const dz = desplazamientoActual();
    pos.y += dz.y;                                  // animar() lo reescribe en cada frame
    // x no lo toca nadie más: se suma la diferencia y se recuerda lo puesto.
    if (sceneX !== vrm.scene) { sceneX = vrm.scene; offX = 0; }
    pos.x += dz.x - offX;
    offX = dz.x;
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    alCargar() { offX = 0; sceneX = null; },
    alDescargar() { offX = 0; sceneX = null; },
    pose,
    trasPose,
    expresiones(set) {
      if (peso > 0.01 && typeof set === 'function') set('happy', P.felicidad * peso, 'max');
    },
    ocupado() { return activo || peso > 0; },
    inhibe() { return { idle: 1 - peso, seguimiento: 1 - P.seguimiento * peso }; },
    api: {
      bailar: (on, opts) => bailar(on, opts),
      pulso(bpm, fase, energia) {
        const b = Number(bpm);
        if (!finito(b) || b <= 0) return false;
        pulsoPendiente = [b, Number(fase), Number(energia)];
        return true;
      },
      estilo(nombre) {
        const v = estiloValido(nombre);
        if (v && v !== estilo) {
          if (peso > 0) cambiarA(v); else estilo = v;
          tCambio = null;
        }
        return estilo;
      },
      estado: () => ({
        activo, peso, estilo, previo, mezcla, particulas, cambiar, cambiarS,
        bpm: num(ultimo.bpm, P.bpm), pulsos: num(ultimo.pulsos), energia: num(ultimo.energia),
      }),
    },
  };
}
