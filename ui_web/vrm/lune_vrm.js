/*
 * ui_web/vrm/lune_vrm.js — motor de la mascota VRM de Lune (three.js + @pixiv/three-vrm).
 *
 * No hay clips de animación: TODO es procedural sobre los huesos normalizados del
 * humanoide (nacen en T-pose, identidad) y las expresiones del modelo. Cada frame
 * se compone, en este orden, y SIEMPRE antes de vrm.update(dt):
 *
 *   pose = A-pose de reposo
 *        + variante de idle (cambia cada 10 s con 1 s de mezcla)
 *        + gesto del estado (happy, wave, dismiss, thinking…) × su peso
 *        + pose "colgada" del arrastre × peso
 *        + pose de dormida × peso
 *        + caricia en la cabeza × peso
 *        + respiración, seguimiento del cursor (cabeza / torso / ojos),
 *          balanceo del arrastre (muelle amortiguado en las caderas), boca al hablar
 *
 * Los números vienen de Mate-Engine (proyecto Unity de mascota VRM) adaptados a
 * three.js: seguimiento 45°/30° cabeza, ±15° torso, ±12° ojos; muelle del
 * balanceo 2.6 Hz / ζ 0.35; dormir 1.0 s de entrada / 0.45 s de salida; caricia =
 * 540° de círculos o 180 px de zigzag; hit-test por alfa del píxel (umbral 0.1).
 *
 * API (la usa companion_vrm.html para exponerla en window.*):
 *   const m = crearMascota({ canvas, src, encuadre, onEvento });
 *   m.setEstado('happy')          estados: normal happy sad angry thinking surprised
 *                                  nervous curious wave dismiss listening talking
 *                                  typing laughing bored working
 *   m.setHablando(true|false)     boca (visemas) mientras suena la voz
 *   m.cursor(nx, ny, px, py, dentro) → bool (¿cursor sobre el avatar?)
 *   m.drag(on, vx, vy)            vx/vy en px/ms (px de pantalla, Y hacia abajo)
 *   m.dormir(on) · m.tocar() · m.encuadrar('retrato'|'cuerpo') · m.cargar(url)
 *   m.setFPS(n) · m.meta()
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const G2R = Math.PI / 180;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const suav = (dt, k) => 1 - Math.exp(-k * dt);     // lerp exponencial, independiente del fps
const azar = (a, b) => a + Math.random() * (b - a);

// ── Parámetros (de Mate-Engine, adaptados) ─────────────────────────────────────
export const PARAMS = {
  // Seguimiento del cursor (AvatarMouseTracking): límites en grados y suavizados (1/s)
  cabezaYaw: 45, cabezaPitch: 30, cabezaSuav: 10,
  torsoYaw: 15, torsoSuav: 6,
  ojosX: 0.6, ojosY: 0.4,                 // cuánto se desplaza el punto de mirada (m)
  // Balanceo al arrastrar (AvatarSwayController): ganancia en °/(px/s), clamps en °,
  // muelle semi-implícito (Hz, ζ), filtro de la velocidad (1/s), fundido del peso (1/s)
  swayGanH: 0.012, swayGanV: 0.007, swayMaxZ: 25, swayMaxX: 12,
  swayFrec: 2.6, swayZeta: 0.35, swayFiltro: 12, swayEntrada: 8, swaySalida: 3,
  invertirH: 1, invertirV: 1,             // ±1 si el balanceo sale al revés en un modelo
  // Ejes de los huesos: 0 = automático (se mide el brazo al cargar), 1 = tal cual,
  // -1 = invertir X y Z. Los VRM 0.x tienen el rig girado 180° y salen con los
  // brazos en V si no se invierte; los VRM 1.0 no.
  invertirEjes: 0,
  dragMinimo: 0.30,                       // s: el arrastre dura al menos esto (dragLockTimer)
  // Fuerza sobre el pelo/falda (spring bones) al mover la ventana
  peloFuerza: 0.3, peloVelRef: 2000,
  // Ciclo de idles
  idleCambio: 10, idleMezcla: 1.0,
  // Sueño
  dormirEntrada: 1.0, dormirSalida: 0.45, dormirSalidaDrag: 0.25,
  // Caricia en la cabeza (PetVoiceReactionHandler.ProcessPat)
  patRadio: 0.13, patGrados: 540, patMinRadio: 12, patMinMov: 4, patReset: 0.6,
  patCooldown: 0.5, patWiggleDist: 180, patWiggleCambios: 3,
  // Render
  fov: 24, fpsActivo: 60, fpsReposo: 30, reposoTras: 4, alfaHit: 26, hitCadaMs: 33,
  // Los gestos con tiempo (saludo, "no") vuelven solos al idle; el resto SE QUEDA
  // hasta el siguiente estado (si la haces reír, sigue riéndose). gestoWatchdog
  // (ms) los devolvería a neutral pasado ese tiempo; 0 = nunca.
  gestoWatchdog: 0,
};

// ── Poses (radianes, huesos normalizados). Ejes: X = cabecear (+ mira abajo),
//    Y = girar (+ hacia la derecha del espectador), Z = ladear. Brazo izquierdo
//    apunta a +X en T-pose: z negativo lo baja; el derecho apunta a -X: z positivo lo baja.
const POSE_REPOSO = {                     // A-pose: brazos caídos, codos un poco al frente
  leftUpperArm: [0, 0, -1.15], rightUpperArm: [0, 0, 1.15],
  leftLowerArm: [0, -0.28, 0], rightLowerArm: [0, 0.28, 0],
  leftHand: [0, 0, -0.08], rightHand: [0, 0, 0.08],
};
const POSE_ARRASTRE = {                   // colgada de las axilas: brazos arriba, piernas atrás
  leftUpperArm: [0, 0, 1.6], rightUpperArm: [0, 0, -1.6],
  leftLowerArm: [0, 0.1, 0.3], rightLowerArm: [0, -0.1, -0.3],
  leftUpperLeg: [0.22, 0, 0.05], rightUpperLeg: [0.22, 0, -0.05],
  leftLowerLeg: [0.2, 0, 0], rightLowerLeg: [0.2, 0, 0],
  spine: [0.06, 0, 0], head: [-0.12, 0, 0],
};
const POSE_DORMIDA = {                    // cabecea dormida de pie (el clip original va tumbada)
  head: [0.30, 0, 0], neck: [0.12, 0, 0], spine: [0.18, 0, 0], chest: [0.10, 0, 0],
  upperChest: [0.08, 0, 0], leftUpperArm: [0, 0, -0.05], rightUpperArm: [0, 0, 0.05],
};
const POSE_CARICIA = { head: [0.05, 0, 0], neck: [-0.08, 0, 0] };

// Gestos por estado: pose (offset) + término dinámico opcional fn(t, out) + duración (ms; 0 = hasta que cambie el estado)
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
  typing:    { pose: { head: [0.12, 0, 0], leftUpperArm: [0.9, 0, -0.85], rightUpperArm: [0.9, 0, 0.85], leftLowerArm: [0, -0.9, 0], rightLowerArm: [0, 0.9, 0] }, dur: 0,
               fn: (t, o) => { add(o, 'leftHand', 0.25 * Math.sin(t * 16), 0, 0); add(o, 'rightHand', 0.25 * Math.sin(t * 16 + 1.7), 0, 0); } },
  working:   { pose: { head: [0.12, 0, 0], leftUpperArm: [0.9, 0, -0.85], rightUpperArm: [0.9, 0, 0.85], leftLowerArm: [0, -0.9, 0], rightLowerArm: [0, 0.9, 0] }, dur: 0,
               fn: (t, o) => { add(o, 'leftHand', 0.25 * Math.sin(t * 16), 0, 0); add(o, 'rightHand', 0.25 * Math.sin(t * 16 + 1.7), 0, 0); } },
  laughing:  { pose: { head: [-0.15, 0, 0], spine: [-0.04, 0, 0] }, dur: 0, bob: 0.02,
               fn: (t, o) => { add(o, 'spine', 0.035 * Math.sin(t * 2 * Math.PI * 4), 0, 0); add(o, 'upperChest', 0, 0.02 * Math.sin(t * 2 * Math.PI * 2), 0); } },
  bored:     { pose: { head: [0.12, 0, 0.16], neck: [0.05, 0, 0], spine: [0.10, 0, 0], leftUpperArm: [0, 0, 0.1], rightUpperArm: [0, 0, -0.1] }, dur: 0,
               fn: (t, o) => { add(o, 'head', 0, 0.12 * Math.sin(t * 0.5), 0); } },
  reading:   { pose: { head: [0.15, 0, 0.05], spine: [0.04, 0, 0] }, dur: 0 },
  error:     { pose: { head: [0.06, 0, -0.08], leftUpperArm: [0, 0, 0.12], rightUpperArm: [0, 0, -0.12] }, dur: 0 },
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
  sleeping:  {},
};
// Alias por si un modelo trae nombres propios en vez de presets.
const ALIAS = {
  happy: ['happy', 'joy', 'smile', 'fun', 'にこり', '笑い'], angry: ['angry', 'anger', '怒り'],
  sad: ['sad', 'sorrow', '困る'], relaxed: ['relaxed', 'fun', 'calm'], surprised: ['surprised', 'surprise', 'shock'],
  neutral: ['neutral'], aa: ['aa', 'a', 'あ', 'mouth_a'], ih: ['ih', 'i', 'い'], ou: ['ou', 'u', 'う'],
  ee: ['ee', 'e', 'え'], oh: ['oh', 'o', 'お'], blink: ['blink', 'blink_both', 'まばたき', 'eyes_closed'],
  blinkLeft: ['blinkLeft', 'blink_l', 'wink', 'ウィンク'], blinkRight: ['blinkRight', 'blink_r', 'ウィンク右'],
};
const EMOCIONES = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'];
const VISEMAS = ['aa', 'ih', 'ou', 'ee', 'oh'];
const HUESOS = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand',
  'leftUpperLeg', 'leftLowerLeg', 'rightUpperLeg', 'rightLowerLeg'];

function add(out, hueso, x, y, z) {
  const r = out[hueso] || (out[hueso] = [0, 0, 0]);
  r[0] += x; r[1] += y; r[2] += z;
}
function mezclar(out, pose, w) {
  if (!pose || w <= 0) return;
  for (const h in pose) { const p = pose[h]; add(out, h, p[0] * w, p[1] * w, p[2] * w); }
}

// Muelle amortiguado semi-implícito (AvatarSwayController): f en Hz, ζ adimensional.
// Se integra en subpasos de ≤ 1/120 s: con dt grandes (pestaña frenada, 10 fps) el
// Euler diverge, se va a NaN y el modelo desaparecería para siempre.
class Muelle {
  constructor(f, zeta, tope = 90) { this.w = Math.max(0.01, f) * 2 * Math.PI; this.z = zeta; this.x = 0; this.v = 0; this.tope = tope; }
  paso(objetivo, dt) {
    const n = Math.max(1, Math.ceil(dt / (1 / 120))), h = dt / n;
    for (let i = 0; i < n; i++) {
      const a = this.w * this.w * (objetivo - this.x) - 2 * this.z * this.w * this.v;
      this.v += a * h; this.x += this.v * h;
    }
    if (!Number.isFinite(this.x) || !Number.isFinite(this.v)) { this.x = 0; this.v = 0; }
    this.x = clamp(this.x, -this.tope, this.tope);
    return this.x;
  }
}

export function crearMascota({ canvas, src, encuadre = 'retrato', onEvento = () => {} }) {
  // ── Escena ───────────────────────────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(PARAMS.fov, 1, 0.05, 30);
  camera.position.set(0, 1.3, 1.2);
  const luz = new THREE.DirectionalLight(0xffffff, Math.PI * 0.9); luz.position.set(0.8, 1.6, 1.4); scene.add(luz);
  scene.add(new THREE.HemisphereLight(0xdde8ff, 0x445066, 1.0));
  const gl = renderer.getContext();
  const pixel = new Uint8Array(4);

  let vrm = null, listo = false, huesos = {}, disponibles = new Set(), resueltas = {};
  let sXZ = 1;                            // signo de las rotaciones X/Z según el rig (ver PARAMS.invertirEjes)
  let ultimoHit = 0;
  let caja = new THREE.Box3(), alturaCabeza = 1.4, modoEncuadre = encuadre;
  const miraTarget = new THREE.Object3D(); scene.add(miraTarget);

  // ── Estado ───────────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  let ahora = 0;                          // s desde el arranque
  let estado = 'normal', tEstado = 0, gestoPeso = 0, gestoObj = 0, gestoActual = null;
  let idleVar = 0, idleSig = 0, idleMezclaT = 1, idleTimer = 0;
  const objetivoExpr = {}, actualExpr = {};
  let hablando = false, visemaActual = 'aa', visemaT = 0, bocaPeso = 0;
  let parpadeo = 0, tParpadeo = azar(2, 5), parpadeoFase = 0;
  let durmiendo = false, sleepBlend = 0, sleepLado = 1, cabeceoT = azar(6, 10), cabeceo = 0, despertarT = 0;
  let cursor = { nx: 0, ny: 0, px: -1, py: -1, dentro: false, t: 0 };
  let cabezaYaw = 0, cabezaPitch = 0, torsoYaw = 0, pesoMirada = 1;
  let drag = { on: false, lock: 0, vx: 0, vy: 0, fvx: 0, fvy: 0, peso: 0, t: 0, muelleZ: new Muelle(PARAMS.swayFrec, PARAMS.swayZeta), muelleX: new Muelle(PARAMS.swayFrec, PARAMS.swayZeta) };
  let sobreModelo = true, ultimaActividad = 0, fpsObj = PARAMS.fpsActivo, ultimoFrame = 0;
  let toque = { t: -10 };
  let pat = { hover: false, activo: false, t0: 0, ang: 0, acum: 0, wiggle: 0, cambios: 0, ultimo: null, ultimoMov: null, expira: 0, cooldown: 0, lado: 1, peso: 0 };
  let intro = { activo: false, t: 0 };
  const springBase = new Map();
  let cargaGen = 0;                       // dos cargas solapadas: solo cuenta la última

  function actividad() { ultimaActividad = ahora; }

  // ── Expresiones: resolver nombres del modelo ─────────────────────────────────
  function resolver(nombre) {
    if (nombre in resueltas) return resueltas[nombre];
    const em = vrm?.expressionManager;
    let r = null;
    if (em) {
      const cands = ALIAS[nombre] || [nombre];
      const todos = (em.expressions || []).map(e => e.expressionName);
      for (const c of cands) {
        if (em.getExpression(c)) { r = c; break; }
        const enc = todos.find(n => n.toLowerCase() === c.toLowerCase());
        if (enc) { r = enc; break; }
      }
    }
    resueltas[nombre] = r; return r;
  }
  function setExpr(nombre, v) {
    const em = vrm?.expressionManager; if (!em) return;
    const real = resolver(nombre); if (!real) return;
    em.setValue(real, clamp(v, 0, 1));
  }

  // ── Carga ────────────────────────────────────────────────────────────────────
  function descargar() {
    if (!vrm) return;
    scene.remove(vrm.scene);
    try { VRMUtils.deepDispose(vrm.scene); } catch (_) {}
    vrm = null; listo = false; huesos = {}; disponibles = new Set(); resueltas = {}; springBase.clear();
  }
  function cargar(url) {
    const gen = ++cargaGen;
    descargar();
    onEvento('cargando', url);
    const loader = new GLTFLoader();
    loader.register(parser => new VRMLoaderPlugin(parser));
    loader.crossOrigin = 'anonymous';
    loader.load(url, (gltf) => {
      if (gen !== cargaGen) { try { VRMUtils.deepDispose(gltf.scene); } catch (_) {} return; }   // ya se pidió otro
      const v = gltf.userData.vrm;
      if (!v) { onEvento('error', 'El archivo no es un modelo VRM.'); return; }
      descargar();                                  // por si otra carga terminó entre medias
      try { VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (_) {}
      // (removeUnnecessaryJoints se omite a propósito: en three-vrm 3.1 deforma
      //  algunos modelos con varias mallas; solo era una optimización.)
      VRMUtils.rotateVRM0(v);                       // los VRM 0.x miran a -Z: girarlos hacia la cámara
      v.scene.traverse(o => { o.frustumCulled = false; o.visible = true; });
      v.scene.position.set(0, 0, 0); v.scene.scale.setScalar(1);
      scene.add(v.scene);
      vrm = v;
      for (const h of HUESOS) { const n = v.humanoid?.getNormalizedBoneNode(h); if (n) huesos[h] = n; }
      // Ejes del rig: las poses están pensadas con el brazo izquierdo apuntando a +X
      // (VRM 1.0). En los VRM 0.x el rig normalizado nace girado 180° (brazo a -X),
      // así que las rotaciones en X y Z van al revés. Se mide en vez de fiarse de la versión.
      if (PARAMS.invertirEjes === 1 || PARAMS.invertirEjes === -1) sXZ = PARAMS.invertirEjes;
      else if (huesos.leftLowerArm && Math.abs(huesos.leftLowerArm.position.x) > 1e-4) sXZ = huesos.leftLowerArm.position.x < 0 ? -1 : 1;
      else sXZ = (v.meta?.metaVersion === '0') ? -1 : 1;
      v.scene.updateMatrixWorld(true);
      caja = new THREE.Box3().setFromObject(v.scene);
      const cab = huesos.head ? huesos.head.getWorldPosition(new THREE.Vector3()) : null;
      alturaCabeza = cab ? cab.y : lerp(caja.min.y, caja.max.y, 0.88);
      if (v.lookAt) { v.lookAt.target = miraTarget; }
      // Gravedad base de cada spring bone (para SUMAR la fuerza del arrastre, no sustituirla).
      try {
        for (const j of (v.springBoneManager?.joints || [])) {
          springBase.set(j, j.settings.gravityDir.clone().multiplyScalar(j.settings.gravityPower));
        }
      } catch (_) {}
      encuadrar(modoEncuadre);
      listo = true;
      intro = { activo: true, t: 0 };
      setEstado('wave');
      actividad();
      onEvento('listo', meta());
    }, undefined, (err) => { if (gen === cargaGen) onEvento('error', (err && err.message) || String(err)); });
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
  window.addEventListener('resize', () => { ajustar(); if (vrm) encuadrar(modoEncuadre); });

  // ── Estados / gestos ─────────────────────────────────────────────────────────
  function setEstado(nombre) {
    nombre = String(nombre || 'normal').toLowerCase();
    if (!(nombre in EXPRESIONES) && !(nombre in GESTOS)) nombre = 'normal';
    if (nombre === 'sleeping') { dormir(true); return; }
    if (durmiendo && nombre !== 'normal') dormir(false);
    estado = nombre; tEstado = ahora; actividad();
    const e = EXPRESIONES[nombre] || {};
    for (const k of EMOCIONES) objetivoExpr[k] = e[k] || 0;
    objetivoExpr.blinkRight = e.blinkRight || 0; objetivoExpr.blinkLeft = e.blinkLeft || 0;
    objetivoExpr.aaExtra = e.aa || 0;
    const g = GESTOS[nombre];
    if (g) { gestoActual = { ...g, nombre }; gestoObj = 1; }
    else gestoObj = 0;
    onEvento('estado', nombre);
  }
  function setHablando(on) { hablando = !!on; if (on) { actividad(); if (durmiendo) dormir(false); } }
  function tocar() { toque.t = ahora; actividad(); if (durmiendo) dormir(false); }

  function dormir(on) {
    on = !!on;
    if (on === durmiendo) return;
    durmiendo = on; actividad();
    if (on) { sleepLado = Math.random() < 0.5 ? -1 : 1; cabeceoT = azar(6, 10); onEvento('dormir', true); }
    else { despertarT = ahora; onEvento('dormir', false); }
  }

  // ── Cursor global (Python lo manda a ~30 Hz; también en modo fantasma) ───────
  function cursorGlobal(nx, ny, px, py, dentro) {
    // Nunca dejar escapar una excepción: Python la ignoraría y perdería el sondeo
    // del fantasma automático, y el handler global pintaría el aviso opaco.
    try {
      if (Math.abs(nx - cursor.nx) > 1e-3 || Math.abs(ny - cursor.ny) > 1e-3) actividad();
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
    if (!huesos.head || drag.on || durmiendo || hablando || estado === 'thinking') { pat.hover = false; pat.activo = false; return; }
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
      actividad(); onEvento('caricia', true);
    }
  }

  // ── Arrastre: Python manda velocidad (px/ms, Y hacia abajo) ──────────────────
  function setDrag(on, vx, vy) {
    actividad();
    if (on && !drag.on) { drag.t = ahora; onEvento('arrastre', true); if (durmiendo) dormir(false); }
    if (on) { drag.on = true; drag.suelto = false; drag.lock = PARAMS.dragMinimo; drag.vx = (vx || 0) * 1000; drag.vy = (vy || 0) * 1000; }
    else { drag.vx = 0; drag.vy = 0; drag.suelto = true; }   // se apaga cuando venza el bloqueo mínimo
  }

  // ── Bucle ────────────────────────────────────────────────────────────────────
  function ocupado() {
    if (drag.on || hablando || intro.activo || pat.activo) return true;
    if (Math.abs(sleepBlend - (durmiendo ? 1 : 0)) > 0.01) return true;
    if (Math.abs(gestoPeso - gestoObj) > 0.01 || gestoActual?.fn) return true;
    if (ahora - ultimaActividad < PARAMS.reposoTras) return true;
    if (parpadeo > 0.01 || bocaPeso > 0.01) return true;
    for (const k in objetivoExpr) if (Math.abs((actualExpr[k] || 0) - objetivoExpr[k]) > 0.01) return true;
    return false;
  }

  function tick(now) {
    requestAnimationFrame(tick);
    if (fpsObj <= 0) { clock.getDelta(); return; }
    const objetivo = ocupado() ? fpsObj : Math.min(fpsObj, PARAMS.fpsReposo);
    const intervalo = 1000 / objetivo;
    if (now - ultimoFrame < intervalo - 0.5) return;
    ultimoFrame = (now - ultimoFrame > 2 * intervalo) ? now : now - ((now - ultimoFrame) % intervalo);
    const dt = Math.min(clock.getDelta(), 0.1);
    ahora += dt;
    if (vrm) { animar(dt); vrm.update(dt); }
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
    const out = {};
    mezclar(out, POSE_REPOSO, 1);

    // ── Idle: variantes que rotan cada idleCambio s con idleMezcla s de crossfade
    idleTimer += dt;
    if (idleTimer > PARAMS.idleCambio) { idleTimer = 0; idleSig = (idleVar + 1) % 4; idleMezclaT = 0; }
    if (idleMezclaT < 1) { idleMezclaT = Math.min(1, idleMezclaT + dt / PARAMS.idleMezcla); if (idleMezclaT >= 1) idleVar = idleSig; }
    const wSig = idleMezclaT < 1 ? idleMezclaT : 0;
    aplicarIdle(out, idleVar, 1 - wSig); if (wSig > 0) aplicarIdle(out, idleSig, wSig);
    // Respiración (más lenta y profunda dormida)
    const resp = lerp(0.015 * Math.sin(ahora * 2 * Math.PI / 4), 0.03 * Math.sin(ahora * 2 * Math.PI * 0.22), sleepBlend);
    add(out, 'chest', resp, 0, 0); add(out, 'spine', resp * 0.5, 0, 0);

    // ── Gesto del estado (fade 0.25 s; los gestos con duración vuelven solos)
    if (gestoActual) {
      const t = ahora - tEstado;
      if (gestoActual.dur && t * 1000 > gestoActual.dur) { gestoObj = 0; if (estado === gestoActual.nombre) { estado = 'normal'; for (const k of EMOCIONES) objetivoExpr[k] = 0; objetivoExpr.aaExtra = 0; objetivoExpr.blinkLeft = objetivoExpr.blinkRight = 0; onEvento('estado', 'normal'); } }
      else if (!gestoActual.dur && PARAMS.gestoWatchdog > 0 && ahora - tEstado > PARAMS.gestoWatchdog / 1000 && !hablando) { setEstado('normal'); }
    }
    gestoPeso += (gestoObj - gestoPeso) * suav(dt, 4);
    if (gestoPeso <= 0.001 && gestoObj === 0) gestoActual = null;
    if (gestoActual && gestoPeso > 0.001) {
      const wG = gestoPeso * (1 - sleepBlend) * (1 - drag.peso);
      const tmp = {}; mezclar(tmp, gestoActual.pose, 1); if (gestoActual.fn) gestoActual.fn(ahora - tEstado, tmp);
      mezclar(out, tmp, wG);
      if (gestoActual.bob) vrm.scene.position.y = gestoActual.bob * Math.abs(Math.sin(ahora * 2 * Math.PI * 2)) * wG; else vrm.scene.position.y = 0;
    } else vrm.scene.position.y = 0;

    // ── Toque (clic): pequeño respingo feliz
    const tq = ahora - toque.t;
    if (tq < 1.2) { const k = Math.exp(-tq * 3) * Math.sin(tq * 12); add(out, 'head', -0.12 * k, 0, 0); add(out, 'spine', -0.04 * k, 0, 0); }

    // ── Arrastre: bloqueo mínimo, pose colgada y balanceo (muelle en las caderas)
    if (drag.lock > 0) drag.lock -= dt;
    if (drag.suelto && drag.lock <= 0) { drag.on = false; drag.suelto = false; onEvento('arrastre', false); }
    drag.peso += ((drag.on ? 1 : 0) - drag.peso) * suav(dt, drag.on ? PARAMS.swayEntrada : PARAMS.swaySalida);
    drag.fvx += (drag.vx - drag.fvx) * suav(dt, PARAMS.swayFiltro);
    drag.fvy += (drag.vy - drag.fvy) * suav(dt, PARAMS.swayFiltro);
    if (!drag.on) { drag.vx = 0; drag.vy = 0; }
    const objZ = clamp(PARAMS.invertirH * drag.fvx * PARAMS.swayGanH, -PARAMS.swayMaxZ, PARAMS.swayMaxZ) * (drag.on ? 1 : 0);
    const objX = clamp(PARAMS.invertirV * drag.fvy * PARAMS.swayGanV, -PARAMS.swayMaxX, PARAMS.swayMaxX) * (drag.on ? 1 : 0);
    const leanZ = drag.muelleZ.paso(objZ, dt), leanX = drag.muelleX.paso(objX, dt);
    const wLean = Math.max(drag.peso, Math.min(1, Math.abs(leanZ) / 2 + Math.abs(leanX) / 2));
    add(out, 'hips', leanX * G2R * wLean, 0, leanZ * G2R * wLean);
    // brazos a la zaga (contrapeso), como los additive de Mate-Engine
    add(out, 'leftUpperArm', 0, 0, -leanZ * G2R * 0.5 * wLean); add(out, 'rightUpperArm', 0, 0, -leanZ * G2R * 0.5 * wLean);
    mezclar(out, POSE_ARRASTRE, drag.peso);
    if (drag.on && ahora - drag.t < 0.4) { /* sorpresa breve al levantarla */ }
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
      mezclar(out, tmp, pat.peso);
    }

    // ── Seguimiento del cursor: cabeza (45°/30°), torso (±15°) y ojos
    const pesoObj = (durmiendo || sleepBlend > 0.5) ? 0 : 1;
    pesoMirada += (pesoObj - pesoMirada) * suav(dt, 3);
    const yawObj = clamp(Math.atan(cursor.nx * 1.4) / G2R, -PARAMS.cabezaYaw, PARAMS.cabezaYaw);
    const pitchObj = clamp(Math.atan(cursor.ny * 1.0) / G2R, -PARAMS.cabezaPitch, PARAMS.cabezaPitch);
    cabezaYaw += (yawObj - cabezaYaw) * suav(dt, PARAMS.cabezaSuav);
    cabezaPitch += (pitchObj - cabezaPitch) * suav(dt, PARAMS.cabezaSuav);
    torsoYaw += (clamp(cursor.nx, -1, 1) * PARAMS.torsoYaw - torsoYaw) * suav(dt, PARAMS.torsoSuav);
    const wT = pesoMirada * (1 - pat.peso * 0.6);
    add(out, 'head', -cabezaPitch * G2R * 0.7 * wT, cabezaYaw * G2R * 0.75 * wT, 0);
    add(out, 'neck', -cabezaPitch * G2R * 0.3 * wT, cabezaYaw * G2R * 0.25 * wT, 0);
    add(out, 'spine', 0, torsoYaw * G2R * 0.5 * wT, 0); add(out, 'chest', 0, torsoYaw * G2R * 0.3 * wT, 0); add(out, 'upperChest', 0, torsoYaw * G2R * 0.2 * wT, 0);
    miraTarget.position.set(cursor.nx * PARAMS.ojosX * wT, alturaCabeza + cursor.ny * PARAMS.ojosY * wT, camera.position.z);

    // ── Habla: cabeza con un poco de énfasis
    if (hablando) add(out, 'head', 0.03 * Math.sin(ahora * 2 * Math.PI * 1.3), 0, 0.015 * Math.sin(ahora * 2 * Math.PI * 0.7));

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
      // sorpresa al levantarla (0.4 s) y al despertar (0.6 s), sobre lo anterior
      const sDrag = drag.on ? 0.6 * clamp(1 - (ahora - drag.t) / 0.4, 0, 1) : 0;
      const sDesp = despertarT > 0 ? 0.5 * clamp(1 - (ahora - despertarT) / 0.6, 0, 1) : 0;
      if (sDrag > 0 || sDesp > 0) setExpr('surprised', Math.max(actualExpr.surprised || 0, sDrag, sDesp));
      // caricia: felicidad con los ojos entrecerrados
      if (pat.peso > 0.001) { setExpr('happy', Math.max(actualExpr.happy || 0, pat.peso)); }
      setExpr('relaxed', Math.max(actualExpr.relaxed || 0, 0.5 * sleepBlend));

      // parpadeo natural (cierre rápido, apertura más lenta); dormida: ojos cerrados
      tParpadeo -= dt;
      if (tParpadeo <= 0 && parpadeoFase === 0 && sleepBlend < 0.5) { parpadeoFase = 1; tParpadeo = azar(2.5, 6); }
      if (parpadeoFase === 1) { parpadeo = Math.min(1, parpadeo + dt / 0.06); if (parpadeo >= 1) parpadeoFase = 2; }
      else if (parpadeoFase === 2) { parpadeo = Math.max(0, parpadeo - dt / 0.12); if (parpadeo <= 0) parpadeoFase = 0; }
      const dobleParp = despertarT > 0 && ahora - despertarT < 0.5 ? (Math.sin((ahora - despertarT) * 2 * Math.PI * 4) > 0 ? 1 : 0) : 0;
      // Los pesos que no se reescriben se QUEDAN (three-vrm no los limpia): escribir
      // siempre los tres, y por encima el guiño (thinking) y los ojos entrecerrados (caricia).
      const blink = Math.max(parpadeo * (1 - sleepBlend), sleepBlend, dobleParp);
      const tieneBlink = !!resolver('blink');
      const base = tieneBlink ? 0 : blink;
      const guino = (objetivoExpr.blinkRight || 0) * (1 - sleepBlend) * gestoPeso;
      const entre = pat.peso * 0.5;
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
      if (pat.peso > 0.01 && !hablando) setExpr('aa', Math.max(aaExtra, 0.15 * pat.peso));
    }

    if (despertarT > 0 && ahora - despertarT > 1) despertarT = 0;
    if (intro.activo) { intro.t += dt; if (intro.t > 2.8) intro.activo = false; }
  }

  function aplicarIdle(out, variante, w) {
    if (w <= 0) return;
    if (variante === 1) { add(out, 'hips', 0, 0, 0.05 * w); add(out, 'spine', 0, 0, -0.035 * w); add(out, 'head', 0, 0, 0.03 * w); }
    else if (variante === 2) { add(out, 'hips', 0, 0, -0.05 * w); add(out, 'spine', 0, 0, 0.035 * w); add(out, 'head', 0, 0, -0.03 * w); }
    else if (variante === 3) { add(out, 'head', 0, 0.22 * Math.sin(ahora * 2 * Math.PI / 6) * w, 0); add(out, 'spine', 0, 0.05 * Math.sin(ahora * 2 * Math.PI / 6) * w, 0); }
  }

  ajustar();
  requestAnimationFrame(tick);
  if (src) cargar(src);

  return {
    setEstado, setHablando, tocar, dormir, encuadrar, cargar, meta,
    cursor: cursorGlobal, drag: setDrag,
    setFPS: (n) => { fpsObj = Math.max(0, Number(n) || 0); if (fpsObj > 0) clock.getDelta(); },
    get listo() { return listo; }, get estado() { return estado; }, get durmiendo() { return durmiendo; },
    PARAMS,
  };
}
