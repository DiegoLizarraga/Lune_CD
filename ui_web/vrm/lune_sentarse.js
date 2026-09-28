/*
 * ui_web/vrm/lune_sentarse.js — módulo 'sentarse' del bus VRM: Lune sentada en el borde
 * de una ventana o en la barra de tareas (corte 7; «Window Sitting» y «Taskbar Sitting»
 * de Mate-Engine, AvatarWindowHandler.cs / AvatarTaskbarController.cs, sin clips).
 *
 * La ventana la mueve Python (ui/asiento_qt.ControlAsiento sobre ui/companion.py): aquí
 * solo la pose, el encuadre y la MEDIDA del asiento en px de la página.
 *
 *   window.luneSentar('ventana'|'barra', variante)  → JSON {asiento:{x,y}, sonda:{x,y}}
 *   window.luneSentar(null)                         → se levanta ('null')
 *   window.luneSeatPx()                             → JSON igual, con la pose que tiene
 *
 * Poses (convención de lune_vrm.js: radianes, huesos normalizados VRM 1.0, el motor aplica
 * sXZ a X y Z, así que en los VRM 0.x sale igual). Base: caderas x +0.12 y columna −0.08
 * (se SUMAN), muslos x −1.45 (adelante), espinillas x +1.35 (rodilla doblada) y pies
 * x +0.2. Los pies no están en HUESOS del motor: se ponen en trasPose con
 * humanoid.getNormalizedBoneNode('leftFoot'|'rightFoot') y vuelven a identidad al
 * acabar y en alDescargar.
 * Brazos SIEMPRE abajo (Diego: nada de brazos arriba en reposo). Medidos con matrices
 * (tests/js/sentarse.test.mjs, VRM 1.0 y 0.x): codo y mano por debajo del hombro y la
 * mano por debajo del pecho en todas las variantes.
 *   ventana 0  manos en el regazo, juntas delante
 *   ventana 1  manos apoyadas en el borde, junto a la cadera
 *   ventana 2  tobillos cruzados, un poco adelantada y las manos hacia las rodillas
 *   ventana 3  manos en los muslos y balancea las piernas (espinilla ±0.18 a 0.5 Hz, alternas)
 *   barra      piernas colgando (0.35 Hz ±0.12, alternas), torso un poco adelantado
 *
 * Mezcla: w += (obj − w)·suav(dt, 6) (≈ 88 % en 0.35 s). En `pose` se SUSTITUYEN piernas
 * y brazos por la pose sentada × w (interpolación, como interpolarPoses): los idles que
 * tocan piernas o brazos (estirarse…) no suben nada. En los brazos el peso es
 * w·(1 − gestoPeso) solo si el gesto del estado mueve los brazos (GESTOS_CON_BRAZOS:
 * wave, dismiss, thinking…): un saludo se sigue viendo; con happy/sad… los brazos
 * siguen en su sitio. Caderas y columna se suman. Un cambio de variante sentada funde
 * de una a otra con el mismo suav(6).
 *   inhibe  {idle: 1 − 0.65·w}
 *   ocupado mientras 0 < w < 1 o fundiendo de variante
 *   est.sentada = modo mientras está sentada o le queda peso (lune_movimiento.js no se
 *           balancea con est.sentada)
 *   encuadre ctx.encuadrar('cuerpo', true) al sentarse (en la MISMA llamada, antes de
 *           medir); si otro lo cambia mientras sigue sentada (el baile que se funde llama
 *           encuadrar(null)), se vuelve a poner (salvo en pantalla grande). Cuando w vuelve
 *           a 0: ctx.encuadrar(null), salvo que el baile siga (él lleva su encuadre).
 *
 * Medida (sentar/puntos): se aplica la pose sentada al 100 % (caderas, columna, piernas y
 * pies; los brazos no cuentan), updateMatrixWorld, se proyecta y se DEJAN las rotaciones
 * como estaban (todo en la misma llamada JS: no se ve).
 *   asiento = media de los muslos − 0.12·(cabeza − pie)   (SeatWorldGuess de ME :653-669)
 *   sonda   = caderas − 0.23·altura                       (el −0.375 de la escena de ME)
 * altura = cabeza − caderas + largo de la pierna (independiente de la pose).
 * Sin imports de three: THREE llega por ctx (Node: tests/js/sentarse.test.mjs).
 */
import { clamp, lerp, suav, sumar, interpolarPoses } from './lune_modulos.js';

export const NOMBRE = 'sentarse';
export const ORDEN = 85;                 // tras idles 20, movimiento 30, baile 40, grande 60, comida 70

export const MODOS = Object.freeze(['ventana', 'barra']);
export const VARIANTES_VENTANA = 4;

export const PARAMS_SENTARSE = Object.freeze({
  suav: 6,                 // 1/s de la mezcla (≈ 0.35 s)
  idle: 0.65,              // inhibe {idle: 1 − 0.65·w}
  asientoBaja: 0.12,       // × (cabeza − pie)
  sonda: 0.23,             // × altura bajo las caderas
  balanceoHz: 0.5, balanceoRad: 0.18,     // variante 3
  barraHz: 0.35, barraRad: 0.12,          // barra
});

export const PIERNAS = Object.freeze(['leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg']);
export const BRAZOS = Object.freeze(['leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand']);
export const TRONCO = Object.freeze(['hips', 'spine']);          // se suman
export const PIES = Object.freeze(['leftFoot', 'rightFoot']);     // en trasPose (no están en HUESOS)
/** Gestos del motor que mueven los brazos: sentada, esos se siguen viendo. */
export const GESTOS_CON_BRAZOS = Object.freeze(['wave', 'dismiss', 'thinking', 'typing', 'working', 'surprised', 'angry', 'nervous']);

const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/** 'ventana' | 'barra' o null. */
export function modoValido(modo) {
  const m = String(modo ?? '').trim().toLowerCase();
  return MODOS.includes(m) ? m : null;
}

/** Variante 0..3 en ventana; 0 en la barra. */
export function varianteValida(modo, variante) {
  if (modoValido(modo) === 'barra') return 0;
  const v = Math.floor(Number(variante));
  return finito(v) ? clamp(v, 0, VARIANTES_VENTANA - 1) : 0;
}

/** Brazo/pierna izquierda en su convención y el derecho espejado (x, −y, −z). */
function par(out, sufijo, x, y, z) {
  out['left' + sufijo] = [x, y, z];
  out['right' + sufijo] = [x, -y || 0, -z || 0];          // sin −0
}

/**
 * Pose sentada ABSOLUTA de piernas, brazos y pies (y el delta de caderas y columna) para
 * `modo`/`variante`. `t` (s) mueve las piernas de las variantes que se balancean; con
 * t = null, la pose quieta (la que se mide). Pura: siempre las mismas claves.
 */
export function poseSentada(modo, variante = 0, t = null, out = {}) {
  const m = modoValido(modo) || 'ventana';
  const v = varianteValida(m, variante);
  out.hips = [0.12, 0, 0];
  out.spine = [-0.08, 0, 0];
  par(out, 'UpperLeg', -1.45, 0, 0);
  par(out, 'LowerLeg', 1.35, 0, 0);
  par(out, 'Foot', 0.2, 0, 0);
  // Manos en los muslos (codo junto al costado, antebrazo hacia delante y abajo)
  par(out, 'UpperArm', 0.05, -0.50, -1.35);
  par(out, 'LowerArm', 0, -1.05, 0);
  par(out, 'Hand', 0, -0.15, -0.10);
  const P = PARAMS_SENTARSE;
  if (m === 'barra') {
    out.spine = [0.06, 0, 0];                              // torso un poco adelantado
    par(out, 'LowerLeg', 1.42, 0, 0);                      // piernas colgando
    if (t !== null && finito(t)) {
      const s = P.barraRad * Math.sin(TAU * P.barraHz * t);
      out.leftLowerLeg[0] += s; out.rightLowerLeg[0] -= s;
    }
    return out;
  }
  if (v === 0) {                                           // manos juntas en el regazo
    par(out, 'UpperArm', -0.10, -1.00, -1.45);
    par(out, 'LowerArm', 0, -1.10, 0);
    par(out, 'Hand', 0, -0.25, -0.05);
  } else if (v === 1) {                                    // manos en el borde, junto a la cadera
    par(out, 'UpperArm', 0, 0.05, -1.40);
    par(out, 'LowerArm', 0, -0.05, 0);
    par(out, 'Hand', 0, 0, 0.30);
    out.spine = [-0.12, 0, 0];                             // se apoya un poco hacia atrás
  } else if (v === 2) {                                    // tobillos cruzados, manos hacia las rodillas
    out.spine = [0.02, 0, 0];
    out.leftUpperLeg = [-1.40, 0, 0.06]; out.rightUpperLeg = [-1.40, 0, -0.06];
    out.leftLowerLeg = [1.30, 0, -0.42]; out.rightLowerLeg = [1.40, 0, 0.42];
    par(out, 'UpperArm', -0.20, -1.00, -1.30);
    par(out, 'LowerArm', 0, -0.95, 0);
    par(out, 'Hand', 0, -0.20, -0.05);
  } else if (t !== null && finito(t)) {                    // 3: balancea las piernas
    const s = P.balanceoRad * Math.sin(TAU * P.balanceoHz * t);
    out.leftLowerLeg[0] += s; out.rightLowerLeg[0] -= s;
  }
  return out;
}

const lerp3 = (a, b, k) => {
  if (k >= 1) return [b[0], b[1], b[2]];                  // del todo: la pose sentada exacta
  const x = a || [0, 0, 0];
  return [lerp(x[0] || 0, b[0], k), lerp(x[1] || 0, b[1], k), lerp(x[2] || 0, b[2], k)];
};

/**
 * Mezcla la pose sentada en `out` (la del motor, con A-pose, gestos e idles): piernas y
 * brazos se SUSTITUYEN (× w y × wBrazos), caderas y columna se suman × w.
 */
export function aplicarSentada(out, pose, w, wBrazos = w) {
  const k = clamp(num(w), 0, 1);
  if (!out || !pose || k <= 0) return out;
  const kb = clamp(num(wBrazos, k), 0, 1);
  for (const h of PIERNAS) if (pose[h]) out[h] = lerp3(out[h], pose[h], k);
  if (kb > 0) for (const h of BRAZOS) if (pose[h]) out[h] = lerp3(out[h], pose[h], kb);
  for (const h of TRONCO) if (pose[h]) sumar(out, h, pose[h][0] * k, pose[h][1] * k, pose[h][2] * k);
  return out;
}

// ── Medida ──────────────────────────────────────────────────────────────────────

function nodoPie(ctx, nombre) {
  try {
    const vrm = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
    const hum = vrm && vrm.humanoid;
    const n = hum && typeof hum.getNormalizedBoneNode === 'function' ? hum.getNormalizedBoneNode(nombre) : null;
    return n && n.rotation && typeof n.rotation.set === 'function' ? n : null;
  } catch (e) {
    return null;
  }
}

const redondeo = (v) => Math.round(v * 10) / 10;

/**
 * {asiento:{x,y}, sonda:{x,y}} en px de la página (o null sin modelo). Con `pose`,
 * mide con esa pose aplicada al 100 % (caderas, columna, piernas y pies) y deja las
 * rotaciones como estaban; sin ella, con la pose que tenga ahora.
 */
export function medirAsiento(ctx = {}, pose = null, p = PARAMS_SENTARSE) {
  const T = ctx.THREE;
  const vrm = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
  const hs = ctx.huesos || {};
  if (!T || !T.Vector3 || !vrm || !vrm.scene || !hs.hips || typeof ctx.proyectar !== 'function') return null;
  const sXZ = ctx.sXZ === -1 ? -1 : 1;
  const nodos = {};
  for (const h of [...TRONCO, ...PIERNAS]) if (hs[h]) nodos[h] = hs[h];
  for (const h of PIES) { const n = nodoPie(ctx, h); if (n) nodos[h] = n; }
  const guardadas = [];
  if (pose) {
    for (const h of Object.keys(nodos)) {
      const r = pose[h], n = nodos[h];
      if (!r || !n.rotation) continue;
      guardadas.push([n, n.rotation.x, n.rotation.y, n.rotation.z]);
      n.rotation.set(num(r[0]) * sXZ, num(r[1]), num(r[2]) * sXZ);
    }
  }
  const actualizar = () => { try { if (typeof vrm.scene.updateMatrixWorld === 'function') vrm.scene.updateMatrixWorld(true); } catch (e) { /* sigue */ } };
  try {
    actualizar();
    const pos = (n) => (n && typeof n.getWorldPosition === 'function' ? n.getWorldPosition(new T.Vector3()) : null);
    const cad = pos(hs.hips);
    if (!cad) return null;
    const mI = pos(hs.leftUpperLeg) || cad, mD = pos(hs.rightUpperLeg) || cad;
    const rI = pos(hs.leftLowerLeg), rD = pos(hs.rightLowerLeg);
    const pI = pos(nodos.leftFoot), pD = pos(nodos.rightFoot);
    const cab = pos(hs.head);
    const cabezaY = cab ? cab.y : cad.y + 0.5;
    let pieY = cad.y;
    if (pI) pieY = pI.y;
    if (pD) pieY = pI ? Math.min(pieY, pD.y) : pD.y;
    const h = Math.max(0.1, cabezaY - pieY);
    const baja = clamp(h * p.asientoBaja, 0.01, h * 0.5);
    const asiento = new T.Vector3((mI.x + mD.x) / 2, (mI.y + mD.y) / 2 - baja, (mI.z + mD.z) / 2);
    // Altura de pie (no cambia con la pose): cabeza − caderas + la pierna entera.
    const d = (a, b) => (a && b ? Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z) : NaN);
    let pierna = (cad.y - mI.y) + d(mI, rI) + d(rI, pI);
    if (!finito(pierna) || pierna <= 0) pierna = Math.max(0, cad.y - pieY);
    const altura = Math.max(0.3, (cabezaY - cad.y) + pierna);
    const sonda = new T.Vector3(cad.x, cad.y - p.sonda * altura, cad.z);
    try { if (ctx.camera && typeof ctx.camera.updateMatrixWorld === 'function') ctx.camera.updateMatrixWorld(); } catch (e) { /* sigue */ }
    const a = ctx.proyectar(asiento), s = ctx.proyectar(sonda);
    if (!a || !s || ![a.x, a.y, s.x, s.y].every(finito)) return null;
    return { asiento: { x: redondeo(a.x), y: redondeo(a.y) }, sonda: { x: redondeo(s.x), y: redondeo(s.y) } };
  } catch (e) {
    return null;
  } finally {
    for (let i = guardadas.length - 1; i >= 0; i--) {
      const [n, x, y, z] = guardadas[i];
      n.rotation.set(x, y, z);
    }
    if (guardadas.length) actualizar();
  }
}

// ── Módulo ──────────────────────────────────────────────────────────────────────

/** instalar(ctx, opciones) → módulo del bus. opciones: {params, encuadrar: bool}. */
export function instalar(ctx = {}, opciones = {}) {
  const P = { ...PARAMS_SENTARSE, ...(opciones.params || {}) };
  const conEncuadre = opciones.encuadrar !== false;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };
  const estado = () => (typeof ctx.estado === 'function' ? ctx.estado() : null);

  let objetivo = '';                        // '' | 'ventana' | 'barra'
  let variante = 0;
  let visto = { modo: 'ventana', variante: 0 };   // lo que se ve (y se funde al levantarse)
  let previo = null, mezcla = 1;            // cambio de variante sentada
  let w = 0, ahora = 0;
  let encuadrado = false, camRef = null;
  let piesPuestos = false;
  let poseVista = null;

  function camara() {
    const c = ctx.camera && ctx.camera.position;
    return c ? { x: num(c.x), y: num(c.y), z: num(c.z) } : null;
  }

  function encuadrar() {
    if (!conEncuadre || typeof ctx.encuadrar !== 'function') return;
    try { ctx.encuadrar('cuerpo', true); encuadrado = true; camRef = camara(); } catch (e) { /* sin cámara */ }
  }

  function soltarEncuadre(e) {
    if (!encuadrado) return;
    encuadrado = false; camRef = null;
    if (e && e.baile) return;               // el baile lleva su propio encuadre de cuerpo entero
    try { if (typeof ctx.encuadrar === 'function') ctx.encuadrar(null); } catch (err) { /* sin cámara */ }
  }

  function vigilarEncuadre(e) {
    if (!objetivo || !encuadrado || (e && e.grande)) return;
    const c = camara();
    if (!c) return;
    if (!camRef || Math.abs(c.x - camRef.x) > 1e-6 || Math.abs(c.y - camRef.y) > 1e-6 || Math.abs(c.z - camRef.z) > 1e-6) encuadrar();
  }

  function marcar() {
    const e = estado();
    if (e) e.sentada = objetivo || (w > 0 ? visto.modo : false);
  }

  function sentar(modo, v) {
    const m = modoValido(modo);
    if (!m) { levantar(); return null; }
    const vv = varianteValida(m, v);
    const cambio = objetivo && (objetivo !== m || variante !== vv);
    if (w > 0 && (cambio || !objetivo) && (visto.modo !== m || visto.variante !== vv)) {
      previo = { ...visto }; mezcla = 0;
    }
    const nuevo = !objetivo;
    objetivo = m; variante = vv; visto = { modo: m, variante: vv };
    marcar();
    encuadrar();                           // antes de medir: el asiento con el encuadre 'cuerpo'
    if (nuevo || cambio) emitir('sentada', { modo: m, variante: vv });
    return medirAsiento(ctx, poseSentada(m, vv, null), P);
  }

  function levantar() {
    if (!objetivo) return false;
    objetivo = '';
    previo = null; mezcla = 1;
    marcar();
    emitir('sentada', { modo: '', variante: 0 });
    return true;
  }

  function ponerPies(k) {
    const sXZ = ctx.sXZ === -1 ? -1 : 1;
    if (k <= 0) {
      if (!piesPuestos) return;
      for (const h of PIES) { const n = nodoPie(ctx, h); if (n) n.rotation.set(0, 0, 0); }
      piesPuestos = false;
      return;
    }
    const pose = poseVista || poseSentada(visto.modo, visto.variante, null);
    for (const h of PIES) {
      const n = nodoPie(ctx, h);
      const r = pose[h];
      if (n && r) n.rotation.set(r[0] * k * sXZ, r[1] * k, r[2] * k * sXZ);
    }
    piesPuestos = true;
  }

  function pose(out, dt, t, est) {
    ahora = num(t, ahora);
    const e = est || estado() || {};
    const d = num(dt);
    const obj = objetivo ? 1 : 0;
    w += (obj - w) * suav(d, P.suav);
    if (obj === 0 && w < 1e-3) w = 0;
    if (obj === 1 && w > 1 - 1e-4) w = 1;
    if (previo) {
      mezcla += (1 - mezcla) * suav(d, P.suav);
      if (mezcla > 1 - 1e-3) { mezcla = 1; previo = null; }
    }
    e.sentada = objetivo || (w > 0 ? visto.modo : false);
    if (w <= 0) {
      poseVista = null;
      if (!objetivo) soltarEncuadre(e);
      return;
    }
    vigilarEncuadre(e);
    let p = poseSentada(visto.modo, visto.variante, ahora);
    if (previo) p = interpolarPoses(poseSentada(previo.modo, previo.variante, ahora), p, mezcla);
    poseVista = p;
    const brazosGesto = GESTOS_CON_BRAZOS.includes(e.gesto) ? clamp(num(e.gestoPeso), 0, 1) : 0;
    aplicarSentada(out, p, w, w * (1 - brazosGesto));
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    alCargar() { piesPuestos = false; camRef = null; },
    alDescargar() { ponerPies(0); piesPuestos = false; camRef = null; },
    pose,
    trasPose() { ponerPies(w); },
    ocupado() { return (w > 0 && w < 1) || !!previo; },
    inhibe() { return { idle: 1 - P.idle * w }; },
    api: {
      sentar: (modo, v) => sentar(modo, v),
      levantar: () => levantar(),
      /** Asiento y sonda con la pose que tiene (sentada: la pose sentada quieta). */
      puntos: () => medirAsiento(ctx, objetivo ? poseSentada(visto.modo, visto.variante, null) : null, P),
      estado: () => ({ sentada: objetivo, variante: objetivo ? variante : 0, peso: w, mezcla, encuadrado, visto: { ...visto } }),
    },
  };
}
