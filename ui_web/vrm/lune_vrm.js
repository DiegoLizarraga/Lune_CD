/*
 * ui_web/vrm/lune_vrm.js — motor de la asistente VRM de Lune (three.js + @pixiv/three-vrm).
 *
 * No hay clips de animación: TODO es procedural sobre los huesos normalizados del
 * humanoide (nacen en T-pose, identidad) y las expresiones del modelo. Cada frame
 * se compone, en este orden, y SIEMPRE antes de vrm.update(dt):
 *
 *   pose = A-pose de reposo
 *        + respiración (más lenta y profunda dormida)
 *        + gestos del estado (happy, wave, dismiss, thinking…): mezclador de
 *          lune_gestos.js con fundido por destino (0.25 s; 0.5 hacia normal; 1 s al
 *          salir de laughing), las capas salientes se apagan sin congelarse
 *        + toque, pose de dormida × peso, caricia en la cabeza × peso
 *        + seguimiento del cursor (cabeza / torso / ojos × pesoCabeza/Torso/Ojos)
 *        + boca y cabeceo al hablar
 *        + módulos del bus: 'idles' (lune_idles.js: 10 variantes con fundido,
 *          microexpresiones, bostezo, estiramiento) y 'movimiento'
 *          (lune_movimiento.js: balanceo al arrastrar, brazos y piernas con retraso,
 *          pose colgada, caras por velocidad, mareo) y los que se registren luego
 *
 * Los números vienen de Mate-Engine (proyecto Unity de asistente en escritorio con VRM) adaptados a
 * three.js: seguimiento 45°/30° cabeza, ±15° torso, ±12° ojos; balanceo con los
 * valores de su escena (muelle 0.75 Hz / ζ 0.5, topes 45°/20°); dormir 1.0 s de
 * entrada / 0.45 s de salida; caricia = 540° de círculos o 180 px de zigzag;
 * hit-test por alfa del píxel (umbral 0.1).
 *
 * API (la usa companion_vrm.html para exponerla en window.*):
 *   const m = crearAsistente({ canvas, src, encuadre, onEvento });
 *   m.setEstado('happy')          estados: normal happy sad angry thinking surprised
 *                                  nervous curious wave dismiss listening talking
 *                                  typing laughing bored working reading error dizzy
 *   m.setHablando(true|false)     boca (visemas) mientras suena la voz
 *   m.cursor(nx, ny, px, py, dentro) → bool (¿cursor sobre el avatar?)
 *   m.drag(on, vx, vy)            vx/vy en px/ms (px de pantalla, Y hacia abajo)
 *   m.dormir(on) · m.tocar() · m.encuadrar('retrato'|'cuerpo') · m.cargar(url)
 *   m.setFPS(n) · m.meta() · m.destruir() → bool (true la primera vez)
 *                                  Ritmo (11.2): fpsActivo con algo en marcha, fpsReposo (24) sin nada
 *                                  (mover el cursor no cuenta) y fpsDormida (12) dormida del todo; en
 *                                  reposo el frame siguiente lo da un temporizador y no un rAF en cada
 *                                  refresco (PARAMS.esperaTemporizador); setFPS(0) para el bucle.
 *                                  crearAsistente acepta además {temporizador, ahoraMs} (tests).
 *   m.luneParams(json) → JSON     calibración del modelo con la lista blanca de
 *                                  lune_params.js (luz, altura, pesos, invertir*, sway*)
 *   m.mod(nombre, metodo, ...args)  API de un módulo del bus (window.luneMod en la página)
 *   m.registrar(modulo) · m.bus     bus de módulos (ui_web/vrm/lune_modulos.js)
 *
 * Bus de módulos (v10.3): las funciones nuevas (idles, movimiento, sentarse, baile,
 * pantalla grande, comida…) son módulos `ui_web/vrm/lune_*.js` que se registran en
 * el bus y se enganchan al bucle sin editar este archivo. Por frame, en este orden:
 *   pose(out, dt, t, est)        tras gesto, caricia y seguimiento, antes de
 *                                huesos[h].rotation.set (suma rotaciones en `out`)
 *   expresiones(set, dt, t, est) al final del bloque de expresiones
 *   trasPose(dt, t, est)         antes de vrm.update
 *   trasUpdate(dt, t, est)       después de vrm.update y antes de render
 * alCargar(vrm) al cargar un modelo y alDescargar() antes de soltarlo. ocupado() =
 * lo de aquí OR bus.ocupado(est); bus.inhibe(est) da factores 0..1 que multiplican
 * idle, seguimiento, caricia, parpadeo y gesto (sin módulos valen 1).
 * ctx de los módulos: {THREE, vrm(), camera, scene, renderer, canvas, huesos, PARAMS,
 * sXZ, proyectar(v3), emitir(tipo, datos), encuadrar(modo, temporal), setFPS(n),
 * setPixelRatio(r), setLookAt(on), estado(), tieneExpr(nombre)}.
 *
 * Eventos hacia Python: además de onEvento (para la página), se encolan en
 * window.luneEventos (ui_web/lune_eventos.js) como {t, d}: caricia {lado},
 * arrastre {on}, dormir {}, despertar {}, estado {nombre}, error {origen, mensaje}
 * y, desde el módulo 'movimiento', mareo {inversiones, eje}.
 *
 * Módulos: three, three-vrm y el bus (lune_modulos.js) son el núcleo (import
 * estático). Los demás se piden con import() dinámico: si uno da 404 o tiene un
 * error de sintaxis, el avatar arranca sin él (aviso en consola, MODULOS_OPCIONALES):
 *   lune_idles.js / lune_movimiento.js → sin variantes de reposo / sin balanceo
 *   lune_params.js → window.luneParams no aplica nada (calibración por defecto)
 *   lune_gestos.js → mezclador mínimo (el gesto nuevo sustituye al anterior)
 *
 * m.destruir() suelta todo (bucle, listener de resize, modelo, módulos, contexto
 * WebGL); una carga en vuelo que termine después se libera sin tocar la escena.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { crearBus, emitirPorDefecto } from './lune_modulos.js';

const G2R = Math.PI / 180;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const suav = (dt, k) => 1 - Math.exp(-k * dt);     // lerp exponencial, independiente del fps
const azar = (a, b) => a + Math.random() * (b - a);
const tiene = (o, k) => Object.prototype.hasOwnProperty.call(o, k);   // nada de 'constructor'/'__proto__'

// ── Módulos opcionales ─────────────────────────────────────────────────────────
async function opcional(promesa, nombre) {
  try { return await promesa; } catch (e) {
    try { console.warn(`[lune_vrm] sigo sin ${nombre}:`, (e && e.message) || e); } catch (_) { /* sin consola */ }
    return null;
  }
}
// (Los import() llevan la ruta literal: los tests la reescriben igual que los estáticos.)
const [modGestos, modIdles, modMovimiento, modParams] = await Promise.all([
  opcional(import('./lune_gestos.js'), 'lune_gestos.js'),
  opcional(import('./lune_idles.js'), 'lune_idles.js'),
  opcional(import('./lune_movimiento.js'), 'lune_movimiento.js'),
  opcional(import('./lune_params.js'), 'lune_params.js'),
]);
/** Qué módulos opcionales cargaron (false = el avatar sigue sin ese). */
export const MODULOS_OPCIONALES = Object.freeze({
  gestos: !!modGestos, idles: !!modIdles, movimiento: !!modMovimiento, params: !!modParams,
});

/**
 * Respaldo de lune_gestos.js: misma API que crearMezcladorGestos pero sin capas
 * salientes. El gesto nuevo sustituye al anterior y solo su peso se suaviza (lo que
 * hacía el motor antes del corte 3); al volver a 'normal' el último se apaga suave.
 */
function crearMezcladorMinimo(gestos) {
  const gestoDe = (n) => (tiene(gestos, n) && gestos[n] && gestos[n].pose ? gestos[n] : null);
  let actual = { nombre: 'normal', g: null, t0: 0 };
  let visto = null;                       // {g, t0}: el que se ve (el actual o el que se apaga)
  let w = 0, tW = 0;
  function avanzar(t) {
    const dt = Math.max(0, t - tW); tW = t;
    w += ((actual.g ? 1 : 0) - w) * suav(dt, 4);
    if (!actual.g && w < 1e-3) { w = 0; visto = null; }
  }
  return {
    cambiar(nombre, t) {
      nombre = String(nombre == null || nombre === '' ? 'normal' : nombre);
      const g = gestoDe(nombre);
      if (nombre === actual.nombre && !(g && g.dur > 0)) return 0;
      avanzar(t);
      actual = { nombre, g, t0: t };
      if (g) visto = { g, t0: t };
      return 0.25;
    },
    pose(out, t, wExt = 1) {
      avanzar(t);
      if (!visto || w <= 1e-3 || !(wExt > 0)) return out;
      const tmp = {};
      mezclar(tmp, visto.g.pose, 1);
      if (typeof visto.g.fn === 'function') { try { visto.g.fn(Math.max(0, t - visto.t0), tmp); } catch (_) { /* sigue */ } }
      mezclar(out, tmp, w * wExt);
      return out;
    },
    peso(t) { avanzar(t); return clamp(w, 0, 1); },
    bob(y, dt, t, wExt = 1) {
      const amp = visto && Number.isFinite(visto.g.bob) ? visto.g.bob * w : 0;
      const obj = amp * Math.abs(Math.sin(t * 2 * Math.PI * 2)) * (Number.isFinite(wExt) ? Math.max(0, wExt) : 0);
      const y0 = Number.isFinite(y) ? y : 0;
      return y0 + (obj - y0) * suav(dt, 10);
    },
    vencido(t) { const g = actual.g; return !!(g && g.dur > 0 && (t - actual.t0) * 1000 > g.dur); },
    fundiendo(t) { avanzar(t); return Math.abs(w - (actual.g ? 1 : 0)) > 0.01; },
    dinamico() { return !!(visto && typeof visto.g.fn === 'function'); },
    reiniciar(nombre = 'normal', t = 0) {
      const g = gestoDe(String(nombre || 'normal'));
      actual = { nombre: String(nombre || 'normal'), g, t0: t };
      visto = g ? { g, t0: t } : null; w = g ? 1 : 0; tW = t;
    },
    tLocal: (t) => t - actual.t0,
    get actual() { return actual.nombre; },
    get gesto() { return actual.g; },
  };
}

/** Respaldo de ejesDe (lune_params.js): signo X/Z del rig. */
function ejesRespaldo(invertirEjes, xAntebrazoIzq, metaVersion) {
  if (invertirEjes === 1 || invertirEjes === -1) return invertirEjes;
  if (Number.isFinite(xAntebrazoIzq) && Math.abs(xAntebrazoIzq) > 1e-4) return xAntebrazoIzq < 0 ? -1 : 1;
  return String(metaVersion) === '0' ? -1 : 1;
}

const crearMezcladorGestos = (modGestos && modGestos.crearMezcladorGestos) || crearMezcladorMinimo;
const ejesDe = (modParams && modParams.ejesDe) || ejesRespaldo;
// Sin lune_params.js no hay lista blanca: luneParams no aplica nada.
const crearLuneParams = (modParams && modParams.crearLuneParams) || (() => () => '{}');
// Mareo de lune_movimiento.js; sin él, una cabeza ladeada de 2.5 s.
const GESTO_MAREO = (modMovimiento && modMovimiento.GESTO_MAREO)
  || { pose: { head: [0.06, 0, 0.08], neck: [0.03, 0, 0], spine: [0.04, 0, 0] }, dur: 2500 };

// ── Parámetros (de Mate-Engine, adaptados) ─────────────────────────────────────
// Las claves que se pueden tocar desde fuera (window.luneParams) y sus rangos están
// en lune_params.js (RANGOS): sus defectos son los mismos que aquí.
export const PARAMS = {
  // Seguimiento del cursor (AvatarMouseTracking): límites en grados y suavizados (1/s)
  cabezaYaw: 45, cabezaPitch: 30, cabezaSuav: 10,
  torsoYaw: 15, torsoSuav: 6,
  ojosX: 0.6, ojosY: 0.4,                 // cuánto se desplaza el punto de mirada (m)
  // Pesos del seguimiento por modelo (0..1; modelo_vrm/<modelo>.lune.json o config)
  pesoCabeza: 1, pesoTorso: 1, pesoOjos: 1,
  // Balanceo al arrastrar (AvatarSwayController, valores de la ESCENA de Mate-Engine;
  // lo aplica el módulo 'movimiento'): ganancia en °/(px/s), topes en °, muelle
  // semi-implícito (Hz, ζ), filtro de la velocidad (1/s), fundido del peso (1/s)
  swayGanH: 0.0167, swayGanV: 0.0167, swayMaxZ: 45, swayMaxX: 20,
  swayFrec: 0.75, swayZeta: 0.5, swayFiltro: 12, swayEntrada: 8, swaySalida: 3,
  // ±1 si en un modelo sale al revés: balanceo horizontal y vertical, y brazos y
  // piernas con retraso (lune_movimiento.js)
  invertirH: 1, invertirV: 1, invertirBrazos: 1, invertirPiernas: 1,
  // Ejes de los huesos: 0 = automático (se mide el brazo al cargar), 1 = tal cual,
  // -1 = invertir X y Z. Los VRM 0.x tienen el rig girado 180° y salen con los
  // brazos en V si no se invierte; los VRM 1.0 no.
  invertirEjes: 0,
  dragMinimo: 0.30,                       // s: el arrastre dura al menos esto (dragLockTimer)
  dragCaducidad: 0.12,                    // s sin muestras de Python (ratón quieto) → velocidad 0
  // Fuerza sobre el pelo/falda (spring bones) al mover la ventana
  peloFuerza: 0.3, peloVelRef: 2000,
  // Calibración del modelo: × intensidad de las luces, y m que sube/baja el modelo
  luz: 1, altura: 0,
  // Sueño
  dormirEntrada: 1.0, dormirSalida: 0.45, dormirSalidaDrag: 0.25,
  // Caricia en la cabeza (PetVoiceReactionHandler.ProcessPat)
  patRadio: 0.13, patGrados: 540, patMinRadio: 12, patMinMov: 4, patReset: 0.6,
  patCooldown: 0.5, patWiggleDist: 180, patWiggleCambios: 3,
  // Render. En reposo (nada en marcha: mover el cursor no cuenta, el seguimiento suavizado se
  // ve igual a 24 fps) baja a fpsReposo, y dormida del todo a fpsDormida: la ventana es
  // translúcida y Qt copia cada frame de la GPU a la CPU.
  fov: 24, fpsActivo: 60, fpsReposo: 24, fpsDormida: 12, reposoTras: 4, alfaHit: 26, hitCadaMs: 33,
  // En reposo y dormida el frame siguiente se espera con un temporizador y no con un
  // requestAnimationFrame en cada refresco del monitor: medido en la asistente (11.2), ese bucle
  // a 60/s sin pintar nada costaba él solo un 7-10 % de CPU. Con algo en marcha (o esperas más
  // cortas que esperaMinMs), rAF como siempre. false = siempre rAF (los tests que simulan frames).
  esperaTemporizador: true, esperaMinMs: 20,
  // Los gestos con tiempo (saludo, "no", mareo) vuelven solos al idle; el resto SE
  // QUEDA hasta el siguiente estado (si la haces reír, sigue riéndose). gestoWatchdog
  // (ms) los devolvería a neutral pasado ese tiempo; 0 = nunca.
  gestoWatchdog: 0,
};

// ── Poses (radianes, huesos normalizados, convención VRM 1.0: el modelo mira a +Z,
//    hacia la cámara; sXZ lo traduce al rig girado de los VRM 0.x). Ejes: X =
//    cabecear (+ mira abajo), Y = girar (+ hacia la derecha del espectador), Z = ladear.
//    Brazo izquierdo apunta a +X en T-pose: z negativo lo baja; el derecho apunta a -X:
//    z positivo lo baja.
//    Signo de X en los brazos: three.js compone rotation (orden 'XYZ') como Rx·Ry·Rz,
//    así que Z baja el brazo y DESPUÉS X lo gira sobre el eje lateral del padre. Con el
//    brazo caído (≈ −Y), Rx(a)·(0, −1, 0) = (0, −cos a, −sin a): a > 0 lleva la mano
//    a −Z (DETRÁS del cuerpo) y a < 0 a +Z (DELANTE). Por eso typing/working van con
//    x −0.9 (con +0.9 las manos acababan a la espalda) y en lune_idles.js manosDelante
//    usa x −0.30 y manosEspalda x +0.30. Si el antebrazo va doblado hacia ARRIBA (Z del
//    antebrazo: thinking, dismiss, bostezo), x > 0 inclina ese antebrazo hacia delante
//    (Rx(a)·(0, 1, 0) = (0, cos a, sin a)): la mano queda delante de la cara.
const POSE_REPOSO = {                     // A-pose: brazos caídos, codos un poco al frente
  leftUpperArm: [0, 0, -1.15], rightUpperArm: [0, 0, 1.15],
  leftLowerArm: [0, -0.28, 0], rightLowerArm: [0, 0.28, 0],
  leftHand: [0, 0, -0.08], rightHand: [0, 0, 0.08],
};
const POSE_DORMIDA = {                    // cabecea dormida de pie (el clip original va tumbada)
  head: [0.30, 0, 0], neck: [0.12, 0, 0], spine: [0.18, 0, 0], chest: [0.10, 0, 0],
  upperChest: [0.08, 0, 0], leftUpperArm: [0, 0, -0.05], rightUpperArm: [0, 0, 0.05],
};
const POSE_CARICIA = { head: [0.05, 0, 0], neck: [-0.08, 0, 0] };

// Gestos por estado: pose (offset) + término dinámico opcional fn(tLocal, out) + duración
// (ms; 0 = hasta que cambie el estado). Los mezcla crearMezcladorGestos (lune_gestos.js).
const GESTOS = {
  happy:     { pose: { head: [-0.04, 0, 0.06], spine: [-0.03, 0, 0] }, bob: 0.012, dur: 0 },
  sad:       { pose: { head: [0.22, 0, 0], neck: [0.06, 0, 0], spine: [0.10, 0, 0], leftUpperArm: [0, 0, 0.08], rightUpperArm: [0, 0, -0.08] }, dur: 0 },
  angry:     { pose: { head: [0.08, 0, 0], spine: [0.08, 0, 0], leftUpperArm: [0, 0, 0.25], rightUpperArm: [0, 0, -0.25], leftLowerArm: [0, -0.5, 0], rightLowerArm: [0, 0.5, 0] }, dur: 0 },
  thinking:  { pose: { head: [-0.08, 0.18, 0.14], rightUpperArm: [0.6, 0, -0.55], rightLowerArm: [0, 0, -1.9], rightHand: [0, 0, -0.3] }, dur: 0,
               fn: (t, o) => { add(o, 'head', 0, 0.05 * Math.sin(t * 0.8), 0); } },
  surprised: { pose: { head: [-0.12, 0, 0], spine: [-0.08, 0, 0], leftUpperArm: [0, 0, 0.5], rightUpperArm: [0, 0, -0.5], leftLowerArm: [0, -0.4, 0.4], rightLowerArm: [0, 0.4, -0.4] }, dur: 0,
               fn: (t, o) => { const k = Math.exp(-t * 3); add(o, 'spine', -0.05 * k, 0, 0); } },
  nervous:   { pose: { head: [0.06, 0, -0.08], leftUpperArm: [0, 0, 0.12], rightUpperArm: [0, 0, -0.12], leftLowerArm: [0, -0.5, 0.2], rightLowerArm: [0, 0.5, -0.2] }, dur: 0,
               fn: (t, o) => { add(o, 'head', 0, 0, 0.025 * Math.sin(t * 22)); } },
  curious:   { pose: { head: [-0.05, 0.1, 0.22], spine: [0.06, 0.05, 0], neck: [-0.04, 0, 0.05] }, dur: 0 },
  wave:      { pose: { rightUpperArm: [0, 0, -2.2], rightLowerArm: [0, 0, -1.1], head: [-0.03, -0.08, 0.10] }, dur: 2600, bob: 0.008,
               fn: (t, o) => { add(o, 'rightHand', 0, 0, -0.45 * Math.sin(t * 2 * Math.PI * 3)); add(o, 'rightLowerArm', 0, 0, -0.18 * Math.sin(t * 2 * Math.PI * 3)); } },
  dismiss:   { pose: { spine: [0.02, 0, 0], leftUpperArm: [0, 0, 0.1], rightUpperArm: [0.3, 0, -0.35], rightLowerArm: [0, 0, -1.4] }, dur: 1600,
               fn: (t, o) => { const k = Math.exp(-t * 1.2); add(o, 'head', 0, 0.28 * Math.sin(t * 2 * Math.PI * 2.2) * k, 0); add(o, 'rightHand', 0, 0.5 * Math.sin(t * 2 * Math.PI * 2.2) * k, 0); } },
  listening: { pose: { head: [-0.02, 0.05, 0.12], spine: [0.05, 0.05, 0] }, dur: 0 },
  talking:   { pose: { head: [-0.02, 0, 0.03] }, dur: 0 },
  // Brazos hacia DELANTE (x −0.9, ver la nota de los signos arriba) y antebrazos doblados al frente.
  typing:    { pose: { head: [0.12, 0, 0], leftUpperArm: [-0.9, 0, -0.85], rightUpperArm: [-0.9, 0, 0.85], leftLowerArm: [0, -0.9, 0], rightLowerArm: [0, 0.9, 0] }, dur: 0,
               fn: (t, o) => { add(o, 'leftHand', 0.25 * Math.sin(t * 16), 0, 0); add(o, 'rightHand', 0.25 * Math.sin(t * 16 + 1.7), 0, 0); } },
  working:   { pose: { head: [0.12, 0, 0], leftUpperArm: [-0.9, 0, -0.85], rightUpperArm: [-0.9, 0, 0.85], leftLowerArm: [0, -0.9, 0], rightLowerArm: [0, 0.9, 0] }, dur: 0,
               fn: (t, o) => { add(o, 'leftHand', 0.25 * Math.sin(t * 16), 0, 0); add(o, 'rightHand', 0.25 * Math.sin(t * 16 + 1.7), 0, 0); } },
  laughing:  { pose: { head: [-0.15, 0, 0], spine: [-0.04, 0, 0] }, dur: 0, bob: 0.02,
               fn: (t, o) => { add(o, 'spine', 0.035 * Math.sin(t * 2 * Math.PI * 4), 0, 0); add(o, 'upperChest', 0, 0.02 * Math.sin(t * 2 * Math.PI * 2), 0); } },
  bored:     { pose: { head: [0.12, 0, 0.16], neck: [0.05, 0, 0], spine: [0.10, 0, 0], leftUpperArm: [0, 0, 0.1], rightUpperArm: [0, 0, -0.1] }, dur: 0,
               fn: (t, o) => { add(o, 'head', 0, 0.12 * Math.sin(t * 0.5), 0); } },
  reading:   { pose: { head: [0.15, 0, 0.05], spine: [0.04, 0, 0] }, dur: 0 },
  error:     { pose: { head: [0.06, 0, -0.08], leftUpperArm: [0, 0, 0.12], rightUpperArm: [0, 0, -0.12] }, dur: 0 },
  // Mareo (cabeza en círculos, 2.5 s): el mismo del módulo 'movimiento' al agitarla,
  // aquí como estado para ponerlo desde fuera (setEmocion('dizzy')).
  dizzy:     GESTO_MAREO,
};

// Expresiones VRM (nombres 1.0; three-vrm renombra los presets 0.x al importar) por estado.
const EXPRESIONES = {
  normal:    {},
  happy:     { happy: 1.0 },
  sad:       { sad: 1.0 },
  angry:     { angry: 1.0 },
  thinking:  { relaxed: 0.45, blinkRight: 0.35 },
  surprised: { surprised: 1.0 },
  nervous:   { relaxed: 0.35, sad: 0.25, surprised: 0.15 },
  curious:   { happy: 0.2, surprised: 0.35 },
  wave:      { happy: 0.9 },
  dismiss:   { angry: 0.4, relaxed: 0.3 },
  listening: { surprised: 0.2, relaxed: 0.15 },
  talking:   { happy: 0.25 },
  typing:    { relaxed: 0.3 },
  working:   { relaxed: 0.3 },
  laughing:  { happy: 1.0, aa: 0.25 },
  bored:     { relaxed: 0.4, sad: 0.2 },
  reading:   { relaxed: 0.3 },
  error:     { sad: 0.4, surprised: 0.3 },
  dizzy:     { sad: 0.35, surprised: 0.3, relaxed: 0.25 },   // respaldo si el modelo no trae 'dizzy'
  sleeping:  {},
};
// Estados que, si el modelo trae una expresión con ese nombre (ojos en espiral…),
// la usan en lugar de la mezcla de respaldo de EXPRESIONES.
const EXPR_PROPIAS = ['dizzy'];
// Alias por si un modelo trae nombres propios en vez de presets.
const ALIAS = {
  happy: ['happy', 'joy', 'smile', 'fun', 'にこり', '笑い'], angry: ['angry', 'anger', '怒り'],
  sad: ['sad', 'sorrow', '困る'], relaxed: ['relaxed', 'fun', 'calm'], surprised: ['surprised', 'surprise', 'shock'],
  neutral: ['neutral'], aa: ['aa', 'a', 'あ', 'mouth_a'], ih: ['ih', 'i', 'い'], ou: ['ou', 'u', 'う'],
  ee: ['ee', 'e', 'え'], oh: ['oh', 'o', 'お'], blink: ['blink', 'blink_both', 'まばたき', 'eyes_closed'],
  blinkLeft: ['blinkLeft', 'blink_l', 'wink', 'ウィンク'], blinkRight: ['blinkRight', 'blink_r', 'ウィンク右'],
  dizzy: ['dizzy', 'mareo', 'mareada', 'guruguru', 'ぐるぐる'],
};
const EMOCIONES = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'];
const VISEMAS = ['aa', 'ih', 'ou', 'ee', 'oh'];
const HUESOS = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg'];
const LUZ_DIRECCIONAL = Math.PI * 0.9, LUZ_AMBIENTE = 1.0;   // intensidades base (× PARAMS.luz)

function add(out, hueso, x, y, z) {
  const r = out[hueso] || (out[hueso] = [0, 0, 0]);
  r[0] += x; r[1] += y; r[2] += z;
}
function mezclar(out, pose, w) {
  if (!pose || w <= 0) return;
  for (const h in pose) { const p = pose[h]; add(out, h, p[0] * w, p[1] * w, p[2] * w); }
}
/** PARAMS[clave] recortado a 0..1 (1 si no es un número). */
function peso01(clave) {
  const v = PARAMS[clave];
  return Number.isFinite(v) ? clamp(v, 0, 1) : 1;
}

export function crearAsistente({ canvas, src, encuadre = 'retrato', onEvento = () => {}, temporizador = null, ahoraMs = null }) {
  // Temporizador y reloj (ms, la base de tiempo de requestAnimationFrame) de la espera entre frames
  // en reposo: inyectables para los tests (tests/js/vrm_fps.test.mjs).
  const tm = temporizador && typeof temporizador.poner === 'function' ? temporizador
    : { poner: (fn, ms) => setTimeout(fn, ms), quitar: (id) => clearTimeout(id) };
  const relojMs = typeof ahoraMs === 'function' ? ahoraMs : () => performance.now();
  // ── Escena ───────────────────────────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(PARAMS.fov, 1, 0.05, 30);
  camera.position.set(0, 1.3, 1.2);
  const luz = new THREE.DirectionalLight(0xffffff, LUZ_DIRECCIONAL); luz.position.set(0.8, 1.6, 1.4); scene.add(luz);
  const ambiente = new THREE.HemisphereLight(0xdde8ff, 0x445066, LUZ_AMBIENTE); scene.add(ambiente);
  const gl = renderer.getContext();
  const pixel = new Uint8Array(4);

  let vrm = null, listo = false, huesos = {}, resueltas = {};
  let sXZ = 1;                            // signo de las rotaciones X/Z según el rig (ver PARAMS.invertirEjes)
  let ultimoHit = 0;
  let caja = new THREE.Box3(), alturaCabeza = 1.4, modoEncuadre = encuadre;
  const miraTarget = new THREE.Object3D(); scene.add(miraTarget);

  // ── Estado ───────────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  let ahora = 0;                          // s desde el arranque
  let estado = 'normal', gestoPeso = 0, bobY = 0;
  const mezGestos = crearMezcladorGestos(GESTOS, () => ahora);
  const objetivoExpr = {}, actualExpr = {};
  let exprPropia = null;                  // expresión del modelo que se está usando/apagando (EXPR_PROPIAS)
  let hablando = false, visemaActual = 'aa', visemaT = 0, bocaPeso = 0;
  let parpadeo = 0, tParpadeo = azar(2, 5), parpadeoFase = 0;
  let durmiendo = false, sleepBlend = 0, sleepLado = 1, cabeceoT = azar(6, 10), cabeceo = 0, despertarT = 0;
  let cursor = { nx: 0, ny: 0, px: -1, py: -1, dentro: false, t: 0 };
  let cabezaYaw = 0, cabezaPitch = 0, torsoYaw = 0, pesoMirada = 1;
  let drag = { on: false, suelto: false, lock: 0, vx: 0, vy: 0, fvx: 0, fvy: 0, peso: 0, t: 0, tMuestra: 0 };
  let sobreModelo = true, ultimaActividad = 0, fpsObj = PARAMS.fpsActivo, ultimoFrame = 0;
  let toque = { t: -10 };
  let pat = { hover: false, activo: false, t0: 0, ang: 0, acum: 0, wiggle: 0, cambios: 0, ultimo: null, ultimoMov: null, expira: 0, cooldown: 0, lado: 1, peso: 0 };
  let intro = { activo: false, t: 0 };
  const springBase = new Map();
  let cargaGen = 0;                       // dos cargas solapadas: solo cuenta la última
  let lookAtOn = true, encuadreFijo = modoEncuadre;   // encuadreFijo: el del usuario (no el temporal)
  let destruido = false, rafId = 0;       // destruir(): sin bucle ni cargas que lleguen tarde
  let esperaId = null;                    // temporizador del frame siguiente en reposo (o null)

  // ── Bus de módulos ───────────────────────────────────────────────────────────
  // `est` es UN objeto que se actualiza cada frame (sin basura). Los campos baile,
  // sentada, grande, comiendo y menu los ponen los módulos que los llevan.
  // dragVx/dragVy: px/s de pantalla (Y hacia abajo) sin filtrar, 0 sin arrastre;
  // inactivo: s desde la última actividad; inh: factores del frame (el módulo de
  // idles, por ejemplo, se apaga con est.inh.idle).
  const est = {
    drag: false, dragPeso: 0, dragVx: 0, dragVy: 0, dormida: false, sleepBlend: 0,
    gesto: 'normal', gestoPeso: 0, hablando: false, inactivo: 0,
    baile: false, sentada: false, grande: false, comiendo: false, menu: false,
    cursor: { px: -1, py: -1, nx: 0, ny: 0 },
  };
  const inh = { idle: 1, seguimiento: 1, caricia: 1, parpadeo: 1, gesto: 1 };   // factores de bus.inhibe
  est.inh = inh;
  const emitir = (tipo, datos) => emitirPorDefecto(tipo, datos);
  const ctx = {
    THREE, scene, camera, renderer, canvas, PARAMS, emitir,
    vrm: () => vrm,
    get huesos() { return huesos; },
    get sXZ() { return sXZ; },
    proyectar: (v3) => proyectar(v3),
    encuadrar: (modo, temporal = false) => encuadrarCtx(modo, temporal),
    setFPS: (n) => setFPS(n),
    setPixelRatio: (r) => { const v = Number(r); renderer.setPixelRatio(clamp(Number.isFinite(v) && v > 0 ? v : 1, 0.25, 3)); },
    setLookAt: (on) => { lookAtOn = !!on; if (vrm?.lookAt) vrm.lookAt.target = lookAtOn ? miraTarget : null; },
    estado: () => est,
    tieneExpr: (nombre) => !!resolver(nombre),
  };
  const bus = crearBus(ctx);
  // 'idles' (orden 20): variantes, microexpresiones, bostezo; 'movimiento' (orden 30):
  // balanceo, pose colgada, mareo. Si su archivo no cargó, el avatar sigue sin ellos.
  if (modIdles && typeof modIdles.instalar === 'function') bus.registrar(modIdles.instalar);
  if (modMovimiento && typeof modMovimiento.instalar === 'function') bus.registrar(modMovimiento.instalar);

  function actualizarEst() {
    est.drag = drag.on; est.dragPeso = drag.peso; est.dragVx = drag.vx; est.dragVy = drag.vy;
    est.dormida = durmiendo; est.sleepBlend = sleepBlend;
    est.gesto = estado; est.gestoPeso = gestoPeso; est.hablando = hablando;
    est.inactivo = ahora - ultimaActividad;
    const c = est.cursor; c.px = cursor.px; c.py = cursor.py; c.nx = cursor.nx; c.ny = cursor.ny;
    return est;
  }

  // Eventos: a la página (onEvento, como siempre) y a la cola hacia Python con datos-objeto.
  function evento(tipo, dato) {
    try { onEvento(tipo, dato); } catch (e) { console.warn('onEvento', tipo, e); }
    try {
      if (tipo === 'caricia') emitir('caricia', { lado: pat.lado });
      else if (tipo === 'arrastre') emitir('arrastre', { on: !!dato });
      else if (tipo === 'dormir') emitir(dato ? 'dormir' : 'despertar', {});
      else if (tipo === 'estado') emitir('estado', { nombre: String(dato) });
      else if (tipo === 'error') emitir('error', { origen: 'modelo', mensaje: String(dato).slice(0, 300) });
    } catch (e) { /* sin cola: la página sigue igual */ }
  }

  function actividad() { ultimaActividad = ahora; cortarEspera(); }

  // ── Parámetros por modelo (window.luneParams) ────────────────────────────────
  function aplicarLuz() {
    const k = Number.isFinite(PARAMS.luz) ? Math.max(0, PARAMS.luz) : 1;
    luz.intensity = LUZ_DIRECCIONAL * k;
    ambiente.intensity = LUZ_AMBIENTE * k;
  }
  // Ejes del rig: las poses están pensadas con el brazo izquierdo apuntando a +X
  // (VRM 1.0). En los VRM 0.x el rig normalizado nace girado 180° (brazo a -X), así
  // que las rotaciones en X y Z van al revés. Se mide en vez de fiarse de la versión
  // (invertirEjes ±1 lo fuerza; ver ejesDe en lune_params.js).
  function medirEjes() {
    const x = huesos.leftLowerArm ? huesos.leftLowerArm.position.x : NaN;
    sXZ = ejesDe(PARAMS.invertirEjes, x, vrm && vrm.meta ? vrm.meta.metaVersion : undefined);
  }
  // pesoCabeza/Torso/Ojos, altura y sway* se leen en cada frame; aquí solo lo que
  // hay que recalcular al cambiar.
  function alCambiarParams(cambiadas) {
    if (cambiadas.includes('luz')) aplicarLuz();
    if (cambiadas.includes('invertirEjes') && vrm) medirEjes();
    if (cambiadas.includes('fpsActivo') && fpsObj > 0) setFPS(PARAMS.fpsActivo);
    actividad();                          // que el cambio se vea aunque estuviera en reposo
  }
  const luneParams = crearLuneParams(PARAMS, alCambiarParams);
  aplicarLuz();

  // ── Expresiones: resolver nombres del modelo ─────────────────────────────────
  function resolver(nombre) {
    const em = vrm?.expressionManager;
    if (!em) return null;                 // sin modelo no se cachea (al cargar se resolvería mal)
    nombre = String(nombre);
    if (tiene(resueltas, nombre)) return resueltas[nombre];
    let r = null;
    const cands = tiene(ALIAS, nombre) ? ALIAS[nombre] : [nombre];
    const todos = (em.expressions || []).map(e => e.expressionName);
    for (const c of cands) {
      if (em.getExpression(c)) { r = c; break; }
      const enc = todos.find(n => n.toLowerCase() === c.toLowerCase());
      if (enc) { r = enc; break; }
    }
    resueltas[nombre] = r; return r;
  }
  function setExpr(nombre, v) {
    const em = vrm?.expressionManager; if (!em) return;
    const real = resolver(nombre); if (!real) return;
    em.setValue(real, clamp(v, 0, 1));
  }
  // La que reciben los módulos en el hook `expresiones`: 'max' (por defecto) no baja
  // lo que ya puso Lune este frame; 'sobre' lo sustituye.
  function setExprMod(nombre, peso, modo = 'max') {
    const em = vrm?.expressionManager; if (!em) return;
    const real = resolver(nombre); if (!real) return;
    const v = clamp(Number.isFinite(peso) ? peso : 0, 0, 1);
    em.setValue(real, modo === 'sobre' ? v : Math.max(em.getValue(real) || 0, v));
  }

  // ── Carga ────────────────────────────────────────────────────────────────────
  function descargar() {
    if (!vrm) return;
    bus.llamar('alDescargar');                    // con el modelo aún vivo (colliders, mixers…)
    scene.remove(vrm.scene);
    try { VRMUtils.deepDispose(vrm.scene); } catch (_) {}
    vrm = null; listo = false; huesos = {}; resueltas = {}; springBase.clear();
    exprPropia = null; actualExpr.propia = 0; objetivoExpr.propia = 0;
  }
  function cargar(url) {
    if (destruido) return;
    const gen = ++cargaGen;
    descargar();
    evento('cargando', url);
    const loader = new GLTFLoader();
    loader.register(parser => new VRMLoaderPlugin(parser));
    loader.crossOrigin = 'anonymous';
    loader.load(url, (gltf) => {
      // Ya se pidió otro, o el motor se destruyó: se libera sin tocar la escena.
      if (gen !== cargaGen || destruido) { try { VRMUtils.deepDispose(gltf.scene); } catch (_) {} return; }
      const v = gltf.userData.vrm;
      if (!v) { try { VRMUtils.deepDispose(gltf.scene); } catch (_) {} evento('error', 'El archivo no es un modelo VRM.'); return; }
      descargar();                                  // por si otra carga terminó entre medias
      try { VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (_) {}
      // (removeUnnecessaryJoints se omite a propósito: en three-vrm 3.1 deforma
      //  algunos modelos con varias mallas; solo era una optimización.)
      VRMUtils.rotateVRM0(v);                       // los VRM 0.x miran a -Z: girarlos hacia la cámara
      v.scene.traverse(o => { o.frustumCulled = false; o.visible = true; });
      v.scene.position.set(0, 0, 0); v.scene.scale.setScalar(1);
      scene.add(v.scene);
      vrm = v; resueltas = {};
      for (const h of HUESOS) { const n = v.humanoid?.getNormalizedBoneNode(h); if (n) huesos[h] = n; }
      medirEjes();
      v.scene.updateMatrixWorld(true);
      caja = new THREE.Box3().setFromObject(v.scene);
      const cab = huesos.head ? huesos.head.getWorldPosition(new THREE.Vector3()) : null;
      alturaCabeza = cab ? cab.y : lerp(caja.min.y, caja.max.y, 0.88);
      if (v.lookAt) { v.lookAt.target = lookAtOn ? miraTarget : null; }
      // Gravedad base de cada spring bone (para SUMAR la fuerza del arrastre, no sustituirla).
      try {
        for (const j of (v.springBoneManager?.joints || [])) {
          springBase.set(j, j.settings.gravityDir.clone().multiplyScalar(j.settings.gravityPower));
        }
      } catch (_) {}
      encuadrar(modoEncuadre);
      listo = true;
      bobY = 0;
      if (durmiendo) {
        // Dormida (luneSleep antes de que acabe la carga, o recarga con ella dormida):
        // sigue dormida con el modelo nuevo, sin saludo ni 'despertar'.
        sleepBlend = 1;
        mezGestos.reiniciar(estado, ahora);
        fijarExpresiones(estado);
      } else {
        mezGestos.reiniciar('normal', ahora);       // modelo nuevo: sin fundido desde el gesto del anterior
      }
      actualizarEst();                              // los módulos ven est (dormida…) al día en alCargar
      bus.llamar('alCargar', v);                    // los módulos que se registren luego lo reciben solos
      intro = { activo: true, t: 0 };
      if (!durmiendo) setEstado('wave');
      actividad();
      evento('listo', meta());
    }, undefined, (err) => { if (gen === cargaGen && !destruido) evento('error', (err && err.message) || String(err)); });
  }

  function meta() {
    const m = vrm?.meta || {};
    let tris = 0;
    vrm?.scene.traverse(o => { if (o.isMesh && o.geometry) { const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position?.count || 0) / 3; } });
    return {
      version: m.metaVersion || '?', nombre: m.name || m.title || '',
      autor: (m.authors && m.authors[0]) || m.author || '', triangulos: Math.round(tris), ejes: sXZ,
      expresiones: (vrm?.expressionManager?.expressions || []).map(e => e.expressionName),
    };
  }

  // ── Encuadre: retrato (cara y torso) o cuerpo entero ─────────────────────────
  function encuadrar(modo) {
    modoEncuadre = modo === 'cuerpo' ? 'cuerpo' : 'retrato';
    ajustar();
    if (!vrm) return;
    const alto = Math.max(0.3, caja.max.y - caja.min.y);
    const ancho = Math.max(0.2, caja.max.x - caja.min.x);
    const tanF = Math.tan(camera.fov * G2R / 2);
    let visibleH, centroY;
    if (modoEncuadre === 'cuerpo') { visibleH = alto * 1.10; centroY = (caja.min.y + caja.max.y) / 2; }
    else { visibleH = clamp(alto * 0.46, 0.45, 1.2); centroY = alturaCabeza - visibleH * 0.28; }
    let d = (visibleH / 2) / tanF;
    const visibleW = visibleH * camera.aspect;
    if (visibleW < ancho * 1.05) d *= (ancho * 1.05) / visibleW;   // que quepa a lo ancho
    camera.position.set(0, centroY, d);
    camera.lookAt(0, centroY, 0);
    camera.updateProjectionMatrix();
  }
  function ajustar() {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  // Encuadre desde un módulo: `temporal` no cambia el del usuario (p. ej. cuerpo
  // entero mientras está sentada); encuadrarCtx(null) vuelve al del usuario.
  function encuadrarCtx(modo, temporal) {
    if (modo == null) { encuadrar(encuadreFijo); return modoEncuadre; }
    if (!temporal) encuadreFijo = modo === 'cuerpo' ? 'cuerpo' : 'retrato';
    encuadrar(modo);
    return modoEncuadre;
  }
  const alRedimensionar = () => { ajustar(); if (vrm) encuadrar(modoEncuadre); };
  window.addEventListener('resize', alRedimensionar);

  // ── Estados / gestos ─────────────────────────────────────────────────────────
  // Objetivos de las expresiones del estado. Un estado de EXPR_PROPIAS cuya expresión
  // trae el modelo la usa sola; si no, la mezcla de respaldo de EXPRESIONES.
  function fijarExpresiones(nombre) {
    const propia = EXPR_PROPIAS.includes(nombre) && resolver(nombre) ? nombre : null;
    const e = propia ? {} : ((tiene(EXPRESIONES, nombre) && EXPRESIONES[nombre]) || {});
    for (const k of EMOCIONES) objetivoExpr[k] = e[k] || 0;
    objetivoExpr.blinkRight = e.blinkRight || 0; objetivoExpr.blinkLeft = e.blinkLeft || 0;
    objetivoExpr.aaExtra = e.aa || 0;
    if (propia && propia !== exprPropia) { if (exprPropia) setExpr(exprPropia, 0); exprPropia = propia; actualExpr.propia = 0; }
    objetivoExpr.propia = propia ? 1 : 0;
  }
  function setEstado(nombre) {
    nombre = String(nombre || 'normal').toLowerCase();
    if (!tiene(EXPRESIONES, nombre) && !tiene(GESTOS, nombre)) nombre = 'normal';
    if (nombre === 'sleeping') { dormir(true); return; }
    if (durmiendo && nombre !== 'normal') dormir(false);
    estado = nombre; actividad();
    fijarExpresiones(nombre);
    mezGestos.cambiar(nombre, ahora);             // funde desde lo que se estuviera viendo
    evento('estado', nombre);
  }
  function setHablando(on) { hablando = !!on; if (on) { actividad(); if (durmiendo) dormir(false); } }
  function tocar() { toque.t = ahora; actividad(); if (durmiendo) dormir(false); }

  function dormir(on) {
    on = !!on;
    if (on === durmiendo) return;
    durmiendo = on; actividad();
    if (on) { sleepLado = Math.random() < 0.5 ? -1 : 1; cabeceoT = azar(6, 10); evento('dormir', true); }
    else { despertarT = ahora; evento('dormir', false); }
  }

  // ── Cursor global (Python lo manda a ~30 Hz; también en modo fantasma) ───────
  // Mover el cursor NO cuenta como actividad (11.2): el seguimiento ya va suavizado (suav)
  // y se ve igual a fpsReposo; si contara, con el ratón en marcha (casi siempre que
  // trabajas) el bucle iría a fpsActivo todo el rato. La caricia sí cuenta (procesarCaricia).
  function cursorGlobal(nx, ny, px, py, dentro) {
    // Nunca dejar escapar una excepción: Python la ignoraría y perdería el sondeo
    // del fantasma automático, y el handler global pintaría el aviso opaco.
    try {
      cursor = { nx: clamp(nx, -1.6, 1.6), ny: clamp(ny, -1.6, 1.6), px, py, dentro: !!dentro, t: ahora };
      if (dentro && listo) procesarCaricia(px, py);
      else if (pat.hover) { pat.hover = false; pat.activo = false; reiniciarPat(); }
    } catch (e) { console.warn('luneCursor', e); }
    return listo ? sobreModelo : true;     // sin modelo, toda la ventana es "hit"
  }

  // Proyección de un punto del mundo a px CSS relativos a la ventana.
  const _v = new THREE.Vector3(), _e = new THREE.Vector3();
  function proyectar(p) {
    const r = canvas.getBoundingClientRect();
    _v.copy(p).project(camera);
    return { x: r.left + (_v.x + 1) / 2 * r.width, y: r.top + (1 - _v.y) / 2 * r.height };
  }
  function reiniciarPat() { pat.acum = 0; pat.wiggle = 0; pat.cambios = 0; pat.ultimo = null; pat.ultimoMov = null; pat.expira = 0; }

  // Caricia en la cabeza: hover en un radio proyectado + gesto (círculos o zigzag).
  function procesarCaricia(px, py) {
    if (!huesos.head || drag.on || durmiendo || hablando || estado === 'thinking' || inh.caricia <= 0.001) { pat.hover = false; pat.activo = false; return; }
    const cab = huesos.head.getWorldPosition(new THREE.Vector3()); cab.y += 0.08;
    const s = proyectar(cab);
    _e.copy(cab).addScaledVector(new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0), PARAMS.patRadio);
    const b = proyectar(_e);
    const r2 = (b.x - s.x) ** 2 + (b.y - s.y) ** 2;
    const d2 = (px - s.x) ** 2 + (py - s.y) ** 2;
    const dentro = d2 <= r2;
    if (!dentro) { if (pat.hover) { pat.hover = false; pat.activo = false; reiniciarPat(); } return; }
    pat.hover = true; pat.lado = px >= s.x ? 1 : -1;
    if (pat.activo) return;
    // ProcessPat (Mate-Engine): acumula ángulo alrededor del centro y zigzags.
    const p = { x: px, y: py };
    if (pat.ultimo && ahora > pat.expira) reiniciarPat();     // gesto caducado: se vuelve a sembrar
    if (!pat.ultimo) { pat.ultimo = p; pat.ang = Math.atan2(py - s.y, px - s.x); pat.expira = ahora + PARAMS.patReset; return; }
    const dx = px - pat.ultimo.x, dy = py - pat.ultimo.y, mov = Math.hypot(dx, dy);
    if (mov < PARAMS.patMinMov) return;
    const ang = Math.atan2(py - s.y, px - s.x);
    let dAng = ang - pat.ang; while (dAng > Math.PI) dAng -= 2 * Math.PI; while (dAng < -Math.PI) dAng += 2 * Math.PI;
    const radio = Math.sqrt(d2), radioPrev = Math.hypot(pat.ultimo.x - s.x, pat.ultimo.y - s.y);
    if (radio >= PARAMS.patMinRadio || radioPrev >= PARAMS.patMinRadio) pat.acum += Math.abs(dAng) / G2R;
    if (pat.ultimoMov) {
      const dot = (dx * pat.ultimoMov.x + dy * pat.ultimoMov.y) / (mov * Math.hypot(pat.ultimoMov.x, pat.ultimoMov.y) || 1);
      if (dot < -0.2) pat.cambios++;
    }
    pat.wiggle += mov; pat.ultimoMov = { x: dx, y: dy }; pat.ultimo = p; pat.ang = ang; pat.expira = ahora + PARAMS.patReset;
    const exito = pat.acum >= PARAMS.patGrados || (pat.wiggle >= PARAMS.patWiggleDist && pat.cambios >= PARAMS.patWiggleCambios);
    if (exito && ahora >= pat.cooldown) {
      pat.activo = true; pat.cooldown = ahora + PARAMS.patCooldown; pat.t0 = ahora; reiniciarPat();
      actividad(); evento('caricia', true);
    }
  }

  // ── Arrastre: Python manda velocidad (px/ms, Y hacia abajo) ──────────────────
  function setDrag(on, vx, vy) {
    actividad();
    if (on && !drag.on) { drag.t = ahora; evento('arrastre', true); if (durmiendo) dormir(false); }
    if (on) {
      drag.on = true; drag.suelto = false; drag.lock = PARAMS.dragMinimo; drag.tMuestra = ahora;
      drag.vx = (Number(vx) || 0) * 1000; drag.vy = (Number(vy) || 0) * 1000;
    } else { drag.vx = 0; drag.vy = 0; drag.suelto = true; }   // se apaga cuando venza el bloqueo mínimo
  }
  // Bloqueo mínimo, peso y velocidad filtrada del arrastre; cada frame, haya modelo o no.
  function avanzarArrastre(dt) {
    if (drag.lock > 0) drag.lock -= dt;
    if (drag.on && !drag.suelto && ahora - drag.tMuestra > PARAMS.dragCaducidad) { drag.vx = 0; drag.vy = 0; }   // ratón quieto con el botón pulsado
    if (drag.suelto && drag.lock <= 0) { drag.on = false; drag.suelto = false; evento('arrastre', false); }
    drag.peso += ((drag.on ? 1 : 0) - drag.peso) * suav(dt, drag.on ? PARAMS.swayEntrada : PARAMS.swaySalida);
    drag.fvx += (drag.vx - drag.fvx) * suav(dt, PARAMS.swayFiltro);
    drag.fvy += (drag.vy - drag.fvy) * suav(dt, PARAMS.swayFiltro);
    if (!drag.on) { drag.vx = 0; drag.vy = 0; }
  }

  // ── Bucle ────────────────────────────────────────────────────────────────────
  function ocupado() {
    if (!vrm) return false;                   // sin modelo (o con uno roto) no hay nada que animar a 60 fps
    if (drag.on || hablando || intro.activo || pat.activo) return true;
    if (Math.abs(sleepBlend - (durmiendo ? 1 : 0)) > 0.01) return true;
    if (mezGestos.fundiendo(ahora) || mezGestos.dinamico()) return true;
    if (ahora - ultimaActividad < PARAMS.reposoTras) return true;
    if (parpadeo > 0.01 || bocaPeso > 0.01) return true;
    for (const k in objetivoExpr) if (Math.abs((actualExpr[k] || 0) - objetivoExpr[k]) > 0.01) return true;
    return bus.ocupado(actualizarEst());      // un módulo en marcha (baile, grande…) tampoco baja a reposo
  }

  // FPS 0 (oculta, modo juego, Lune en reposo) PARA el bucle: ni un requestAnimationFrame más
  // (antes despertaba al renderer 60-144 veces por segundo para nada). setFPS(n > 0) lo
  // vuelve a arrancar, sin salto: el primer dt cuenta desde aquí.
  function setFPS(n) {
    fpsObj = Math.max(0, Number(n) || 0);
    if (fpsObj <= 0 || destruido) { quitarEspera(); return; }
    clock.getDelta();
    if (!rafId && esperaId === null) rafId = requestAnimationFrame(tick);
  }

  // fps de este frame: fpsObj con algo en marcha (`activa`); si no, fpsReposo; dormida del todo, fpsDormida.
  function fpsObjetivo(activa = ocupado()) {
    if (activa) return fpsObj;
    const reposo = Math.min(fpsObj, PARAMS.fpsReposo);
    return durmiendo && sleepBlend > 0.99 ? Math.min(reposo, PARAMS.fpsDormida) : reposo;
  }

  // ── Frame siguiente: rAF con algo en marcha; en reposo, un temporizador que pinta él mismo ──────
  // (sin requestAnimationFrame entre medias). Con la página oculta, rAF: Chromium no lo llama y el
  // bucle se queda quieto hasta que se vuelva a ver, como siempre.
  function quitarEspera() {
    if (esperaId === null) return;
    try { tm.quitar(esperaId); } catch (_) { /* ya salió */ }
    esperaId = null;
  }
  function siguiente(esperaMs) {
    if (destruido || fpsObj <= 0 || rafId || esperaId !== null) return;
    const oculta = typeof document !== 'undefined' && document && document.hidden === true;
    if (PARAMS.esperaTemporizador !== false && !oculta && esperaMs > PARAMS.esperaMinMs) {
      esperaId = tm.poner(() => { esperaId = null; if (!rafId) tick(relojMs()); }, esperaMs);
    } else {
      rafId = requestAnimationFrame(tick);
    }
  }
  // Algo la despierta (actividad(), una llamada a un módulo): no espera al temporizador, frame ya.
  function cortarEspera() {
    if (esperaId === null) return;
    quitarEspera();
    if (!destruido && fpsObj > 0 && !rafId) rafId = requestAnimationFrame(tick);
  }

  function tick(now) {
    rafId = 0;
    if (destruido || fpsObj <= 0) return;         // parado hasta el próximo setFPS(n > 0)
    const activa = ocupado();
    const objetivo = fpsObjetivo(activa);
    const intervalo = 1000 / objetivo;
    const pasado = now - ultimoFrame;
    if (pasado < intervalo - 0.5) { siguiente(activa ? 0 : intervalo - pasado); return; }
    // Lo que sobra del intervalo se descuenta (sin deriva). Si el frame llegó un pelín antes, dentro
    // de la tolerancia, no sobra nada: con `pasado % intervalo` quedaba entero y el frame siguiente
    // se pintaba también (el doble de fps de lo pedido, justo cuando el monitor es múltiplo).
    ultimoFrame = pasado > 2 * intervalo ? now : now - (pasado >= intervalo ? pasado - intervalo : 0);
    // El siguiente se pide ANTES de pintar: si este frame lanza, el bucle sigue.
    siguiente(activa ? 0 : intervalo - (now - ultimoFrame));
    const dt = Math.min(clock.getDelta(), 0.1);
    ahora += dt;
    avanzarArrastre(dt);                          // también sin modelo: luneDrag(false) siempre suelta
    if (vrm) {
      animar(dt);
      bus.llamar('trasPose', dt, ahora, est);     // mixers, slerps, colliders (tras rotation.set)
      vrm.update(dt);
      bus.llamar('trasUpdate', dt, ahora, est);   // cámara de pantalla grande, anclas…
    }
    renderer.render(scene, camera);
    if (now - ultimoHit >= PARAMS.hitCadaMs) { ultimoHit = now; leerHit(); }   // readPixels sincroniza la GPU: no cada frame
  }

  // Hit-test por alfa del píxel bajo el cursor (mismo frame que el render).
  function leerHit() {
    if (!cursor.dentro || cursor.px < 0) { sobreModelo = false; return; }
    const r = canvas.getBoundingClientRect();
    const x = (cursor.px - r.left) * (canvas.width / Math.max(1, r.width));
    const y = (cursor.py - r.top) * (canvas.height / Math.max(1, r.height));
    if (x < 0 || y < 0 || x >= canvas.width || y >= canvas.height) { sobreModelo = false; return; }
    try {
      gl.readPixels(Math.floor(x), Math.floor(canvas.height - 1 - y), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      sobreModelo = pixel[3] >= PARAMS.alfaHit;
    } catch (_) { sobreModelo = true; }
  }

  function animar(dt) {
    gestoPeso = mezGestos.peso(ahora);        // peso total de las capas de gesto (0..1)
    const out = {};
    mezclar(out, POSE_REPOSO, 1);
    actualizarEst();
    bus.inhibe(est, inh);                     // factores 0..1 de los módulos (1 si no hay)

    // ── Respiración (más lenta y profunda dormida). Las variantes de idle son el
    //    módulo 'idles' (lune_idles.js), que suma su pose en el hook `pose`.
    const resp = lerp(0.015 * Math.sin(ahora * 2 * Math.PI / 4), 0.03 * Math.sin(ahora * 2 * Math.PI * 0.22), sleepBlend);
    add(out, 'chest', resp, 0, 0); add(out, 'spine', resp * 0.5, 0, 0);

    // ── Gesto del estado: mezclador con fundido por destino (lune_gestos.js). Los
    //    gestos con duración (wave, dismiss, dizzy) vuelven solos al idle.
    if (mezGestos.vencido(ahora)) {
      const n = mezGestos.actual;
      mezGestos.cambiar('normal', ahora);
      if (estado === n) { estado = 'normal'; fijarExpresiones('normal'); evento('estado', 'normal'); }
    } else if (mezGestos.gesto && !mezGestos.gesto.dur && PARAMS.gestoWatchdog > 0
      && mezGestos.tLocal(ahora) > PARAMS.gestoWatchdog / 1000 && !hablando) {
      setEstado('normal');
    }
    const wG = (1 - sleepBlend) * (1 - drag.peso) * inh.gesto;
    mezGestos.pose(out, ahora, wG);
    bobY = mezGestos.bob(bobY, dt, ahora, wG);
    const altura = Number.isFinite(PARAMS.altura) ? PARAMS.altura : 0;   // calibración del modelo (m)
    vrm.scene.position.y = altura + bobY;

    // ── Toque (clic): pequeño respingo feliz
    const tq = ahora - toque.t;
    if (tq < 1.2) { const k = Math.exp(-tq * 3) * Math.sin(tq * 12); add(out, 'head', -0.12 * k, 0, 0); add(out, 'spine', -0.04 * k, 0, 0); }

    // ── Arrastre: el bloqueo mínimo, el peso y la velocidad los lleva avanzarArrastre
    //    (en tick, antes de animar). El balanceo de las caderas, los brazos y piernas
    //    con retraso y la pose colgada son del módulo 'movimiento' (lune_movimiento.js),
    //    que lee est.dragPeso y est.dragVx/dragVy.
    // fuerza sobre pelo/falda: dirección contraria al movimiento, magnitud por velocidad
    if (springBase.size) {
      const v = Math.hypot(drag.fvx, drag.fvy);
      const mag = PARAMS.peloFuerza * clamp(v / PARAMS.peloVelRef, 0, 1);
      const fx = v > 1 ? -drag.fvx / v * mag : 0, fy = v > 1 ? drag.fvy / v * mag : 0;
      for (const [j, base] of springBase) {
        const g = _v.copy(base); g.x += fx; g.y += fy;
        const l = g.length();
        j.settings.gravityPower = l;
        if (l > 1e-6) j.settings.gravityDir.copy(g).normalize();
      }
    }

    // ── Sueño: entra en 1.0 s, sale en 0.45 s (0.25 si la arrastran)
    const vel = durmiendo ? 1 / PARAMS.dormirEntrada : 1 / (drag.on ? PARAMS.dormirSalidaDrag : PARAMS.dormirSalida);
    sleepBlend = clamp(sleepBlend + (durmiendo ? 1 : -1) * vel * dt, 0, 1);
    if (sleepBlend > 0) {
      const tmp = {}; mezclar(tmp, POSE_DORMIDA, 1);
      add(tmp, 'head', 0.04 * Math.sin(ahora * 2 * Math.PI * 0.25), 0, 0.12 * sleepLado);
      cabeceoT -= dt;
      if (cabeceoT <= 0) { cabeceo = 1.3; cabeceoT = azar(6, 10); }
      if (cabeceo > 0) { cabeceo -= dt; const f = cabeceo > 0.4 ? (1.3 - cabeceo) / 0.9 : cabeceo / 0.4; add(tmp, 'head', 0.15 * clamp(f, 0, 1), 0, 0); }
      mezclar(out, tmp, sleepBlend);
    }

    // ── Caricia: risita y cabeza hacia la mano
    pat.peso += ((pat.activo ? 1 : 0) - pat.peso) * suav(dt, pat.activo ? 10 : 1.5);
    if (pat.peso > 0.001) {
      const tmp = {}; mezclar(tmp, POSE_CARICIA, 1);
      const t = ahora - pat.t0;
      add(tmp, 'head', 0, 0, pat.lado * 0.14 + 0.05 * Math.sin(t * 2.5));
      add(tmp, 'spine', 0.03 * Math.sin(t * 6), 0, 0); add(tmp, 'upperChest', 0, 0.02 * Math.sin(t * 3), 0);
      mezclar(out, tmp, pat.peso * inh.caricia);
    }

    // ── Seguimiento del cursor: cabeza (45°/30°), torso (±15°) y ojos, cada uno × su
    //    peso por modelo (pesoCabeza/pesoTorso/pesoOjos)
    const pesoObj = (durmiendo || sleepBlend > 0.5) ? 0 : 1;
    pesoMirada += (pesoObj - pesoMirada) * suav(dt, 3);
    const yawObj = clamp(Math.atan(cursor.nx * 1.4) / G2R, -PARAMS.cabezaYaw, PARAMS.cabezaYaw);
    const pitchObj = clamp(Math.atan(cursor.ny * 1.0) / G2R, -PARAMS.cabezaPitch, PARAMS.cabezaPitch);
    cabezaYaw += (yawObj - cabezaYaw) * suav(dt, PARAMS.cabezaSuav);
    cabezaPitch += (pitchObj - cabezaPitch) * suav(dt, PARAMS.cabezaSuav);
    torsoYaw += (clamp(cursor.nx, -1, 1) * PARAMS.torsoYaw - torsoYaw) * suav(dt, PARAMS.torsoSuav);
    const wT = pesoMirada * (1 - pat.peso * 0.6) * inh.seguimiento;
    const wCab = wT * peso01('pesoCabeza'), wTor = wT * peso01('pesoTorso'), wOjos = wT * peso01('pesoOjos');
    add(out, 'head', -cabezaPitch * G2R * 0.7 * wCab, cabezaYaw * G2R * 0.75 * wCab, 0);
    add(out, 'neck', -cabezaPitch * G2R * 0.3 * wCab, cabezaYaw * G2R * 0.25 * wCab, 0);
    add(out, 'spine', 0, torsoYaw * G2R * 0.5 * wTor, 0); add(out, 'chest', 0, torsoYaw * G2R * 0.3 * wTor, 0); add(out, 'upperChest', 0, torsoYaw * G2R * 0.2 * wTor, 0);
    miraTarget.position.set(cursor.nx * PARAMS.ojosX * wOjos, alturaCabeza + altura + cursor.ny * PARAMS.ojosY * wOjos, camera.position.z);

    // ── Habla: cabeza con un poco de énfasis
    if (hablando) add(out, 'head', 0.03 * Math.sin(ahora * 2 * Math.PI * 1.3), 0, 0.015 * Math.sin(ahora * 2 * Math.PI * 0.7));

    // ── Módulos del bus: suman su pose sobre todo lo anterior
    bus.llamar('pose', out, dt, ahora, est);

    // ── Aplicar la pose (asignar, nunca acumular; X y Z con el signo del rig)
    for (const h in huesos) { const r = out[h] || [0, 0, 0]; huesos[h].rotation.set(r[0] * sXZ, r[1], r[2] * sXZ); }

    // ── Expresiones ──────────────────────────────────────────────────────────────
    const em = vrm.expressionManager;
    if (em) {
      const k = suav(dt, 8);
      for (const e of EMOCIONES) {
        const dest = (objetivoExpr[e] || 0) * (1 - sleepBlend) * (1 - drag.peso * 0.6);
        actualExpr[e] = lerp(actualExpr[e] || 0, dest, k);
        setExpr(e, actualExpr[e]);
      }
      // expresión propia del modelo para el estado (p. ej. 'dizzy'); al salir se
      // apaga con el mismo suavizado y se escribe a 0 (three-vrm no la limpia)
      if (exprPropia) {
        actualExpr.propia = lerp(actualExpr.propia || 0, (objetivoExpr.propia || 0) * (1 - sleepBlend), k);
        setExpr(exprPropia, actualExpr.propia);
        if (!objetivoExpr.propia && actualExpr.propia < 0.005) { setExpr(exprPropia, 0); exprPropia = null; actualExpr.propia = 0; }
      }
      // sorpresa al levantarla (0.4 s) y al despertar (0.6 s), sobre lo anterior
      const sDrag = drag.on ? 0.6 * clamp(1 - (ahora - drag.t) / 0.4, 0, 1) : 0;
      const sDesp = despertarT > 0 ? 0.5 * clamp(1 - (ahora - despertarT) / 0.6, 0, 1) : 0;
      if (sDrag > 0 || sDesp > 0) setExpr('surprised', Math.max(actualExpr.surprised || 0, sDrag, sDesp));
      // caricia: felicidad con los ojos entrecerrados
      const wPat = pat.peso * inh.caricia;
      if (wPat > 0.001) { setExpr('happy', Math.max(actualExpr.happy || 0, wPat)); }
      setExpr('relaxed', Math.max(actualExpr.relaxed || 0, 0.5 * sleepBlend));

      // parpadeo natural (cierre rápido, apertura más lenta); dormida: ojos cerrados
      tParpadeo -= dt;
      if (tParpadeo <= 0 && parpadeoFase === 0 && sleepBlend < 0.5) { parpadeoFase = 1; tParpadeo = azar(2.5, 6); }
      if (parpadeoFase === 1) { parpadeo = Math.min(1, parpadeo + dt / 0.06); if (parpadeo >= 1) parpadeoFase = 2; }
      else if (parpadeoFase === 2) { parpadeo = Math.max(0, parpadeo - dt / 0.12); if (parpadeo <= 0) parpadeoFase = 0; }
      const dobleParp = despertarT > 0 && ahora - despertarT < 0.5 ? (Math.sin((ahora - despertarT) * 2 * Math.PI * 4) > 0 ? 1 : 0) : 0;
      // Los pesos que no se reescriben se QUEDAN (three-vrm no los limpia): escribir
      // siempre los tres, y por encima el guiño (thinking) y los ojos entrecerrados (caricia).
      const blink = Math.max(parpadeo * (1 - sleepBlend) * inh.parpadeo, sleepBlend, dobleParp);
      const tieneBlink = !!resolver('blink');
      const base = tieneBlink ? 0 : blink;
      const guino = (objetivoExpr.blinkRight || 0) * (1 - sleepBlend) * gestoPeso;
      const entre = wPat * 0.5;
      setExpr('blink', tieneBlink ? blink : 0);
      setExpr('blinkLeft', Math.max(base, entre));
      setExpr('blinkRight', Math.max(base, guino, entre));

      // boca: visemas rotando cada ~120 ms mientras habla
      if (hablando) {
        visemaT -= dt;
        if (visemaT <= 0) { visemaT = azar(0.09, 0.15); visemaActual = VISEMAS[Math.floor(Math.random() * VISEMAS.length)]; bocaPeso = azar(0.4, 0.75); }
      }
      bocaPeso = lerp(bocaPeso, hablando ? bocaPeso : 0, hablando ? 0 : suav(dt, 15));
      for (const vname of VISEMAS) {
        const real = resolver(vname) || (vname !== 'aa' ? null : resolver('aa'));
        if (!real) continue;
        setExpr(vname, vname === visemaActual ? bocaPeso : 0);
      }
      if (!resolver(visemaActual) && resolver('aa')) setExpr('aa', bocaPeso);
      const aaExtra = (objetivoExpr.aaExtra || 0) * gestoPeso * (1 - sleepBlend);
      if (aaExtra > 0.01 && !hablando) setExpr('aa', aaExtra);
      if (wPat > 0.01 && !hablando) setExpr('aa', Math.max(aaExtra, 0.15 * wPat));

      // ── Módulos del bus: set(nombre, peso, 'max'|'sobre') encima de todo lo anterior
      bus.llamar('expresiones', setExprMod, dt, ahora, est);
    }

    if (despertarT > 0 && ahora - despertarT > 1) despertarT = 0;
    if (intro.activo) { intro.t += dt; if (intro.t > 2.8) intro.activo = false; }
  }

  // ── Destruir: suelta el bucle, el listener de resize, el modelo, los módulos del
  //    bus y el contexto WebGL. Una carga en vuelo que termine después se libera sin
  //    tocar la escena (cargaGen). Idempotente → true la primera vez.
  function destruir() {
    if (destruido) return false;
    destruido = true;
    cargaGen++;
    fpsObj = 0;
    try { if (rafId && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(rafId); } catch (_) { /* sigue */ }
    rafId = 0;
    quitarEspera();
    try { window.removeEventListener('resize', alRedimensionar); } catch (_) { /* sin ventana */ }
    try { descargar(); } catch (e) { console.warn('destruir: descargar', e); }   // alDescargar de los módulos con el modelo vivo
    for (const n of bus.lista()) { try { bus.quitar(n); } catch (_) { /* sigue */ } }
    listo = false; hablando = false; drag.on = false; drag.suelto = false;
    try { renderer.dispose(); } catch (_) { /* sigue */ }
    try { renderer.forceContextLoss(); } catch (_) { /* ya perdido */ }
    return true;
  }

  ajustar();
  rafId = requestAnimationFrame(tick);
  if (src) cargar(src);

  return {
    setEstado, setHablando, tocar, dormir, cargar, meta, setFPS, destruir,
    encuadrar: (modo) => encuadrarCtx(modo === 'cuerpo' ? 'cuerpo' : 'retrato', false),
    cursor: cursorGlobal, drag: setDrag,
    // Calibración del modelo (window.luneParams en la página; vrm_barra.js la usa si existe)
    luneParams,
    // Bus de módulos: m.mod('baileProc', 'play', …) = window.luneMod(…) en la página
    // (una llamada a un módulo puede ponerlo en marcha: el frame, ya, sin esperar al temporizador)
    mod: (nombre, metodo, ...args) => { const r = bus.api(nombre, metodo, ...args); cortarEspera(); return r; },
    registrar: (modulo) => { const r = bus.registrar(modulo); cortarEspera(); return r; },
    bus, ctx,
    get listo() { return listo; }, get estado() { return estado; }, get durmiendo() { return durmiendo; },
    get destruido() { return destruido; },
    PARAMS,
  };
}
