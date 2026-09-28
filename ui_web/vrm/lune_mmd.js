/*
 * ui_web/vrm/lune_mmd.js — módulo 'mmd' del bus VRM: reproductor de bailes MMD (.vmd) y
 * VRM Animation (.vrma) con su canción (corte 9; AvatarDancePlayer de Mate-Engine).
 *
 * Python (ui/mmd_qt.ControlMMD → ui/companion.py → window.luneMMD) pide un baile de la
 * biblioteca (nucleo/bailes.py, servido por el servidor local en /bailes/ y /bailes_cache/):
 *   api.cargar({id, tipo:'vmd'|'vrma', motion:[url] | motion0..2, cara:[url] | cara0..1,
 *               audio:url|null, offsetMs, enSitio, bucle, brazoGrados, volumen, autoplay}) → Promise<bool>
 *   api.reproducir() · api.pausa(on?) · api.parar() · api.volumen(v) · api.offset(ms)
 *   api.enSitio(on) · api.bucle(on) · api.estado() → {fase, id, t, total, peso, error, …}
 *   api.orden(orden, datos): las órdenes de Python tal cual (cargar {…} · pausa {on} · parar ·
 *               volumen {volumen} · offset {offsetMs} · en_sitio {enSitio} · bucle {bucle}):
 *               la página solo hace window.luneMMD = (o, d) => luneMod('mmd', 'orden', o, d)
 * Fases: parado | cargando | listo | sonando | pausado | saliendo | error.
 * Eventos (ctx.emitir('mmd', {fase, id, t, total, mensaje})): cargando, listo, sonando,
 * pausado, t (cada segundo), fin, parado, error.
 *
 * Un solo camino de animación: el VMD se hornea (lune_vmd.js) en un VRMAnimation sintético
 * y el .vrma se lee con GLTFLoader + VRMAnimationLoaderPlugin; los dos pasan por
 * createVRMAnimationClip(anim, vrm) con la metaVersion que corresponde al signo sXZ que mide
 * el motor (así los VRM 0.x salen igual que con los demás módulos). Las pistas del clip se
 * evalúan con sus interpolantes (sin AnimationMixer: su PropertyMixer no reescribe un valor
 * que no cambia, y el motor lo pisa en cada frame: una pose sostenida se perdería).
 *
 * Por frame, en trasPose (tras rotation.set del motor y antes de vrm.update):
 *   procedural = lo que dejó el motor si el hueso está en ctx.huesos o la expresión en
 *                EXPR_MOTOR; si no, el reposo (identidad, cadera de reposo, peso 0)
 *   valor      = slerp/lerp(procedural → clip(t), w); enSitio: cadera x/z de reposo;
 *                hablando: visemas del clip × 0 (suavizado)
 *   t          = reloj del AUDIO (LuneMMDAudio.crearReloj: deriva > 80 ms salta, si no
 *                corrige un 10 %); sin canción, el del motor
 * Peso w: entra en 0.5 s y sale en 0.6 s (smoothstep); arrastrándola baja con suav(12) y
 * el audio sigue; en pausa (D5 de Diego) baja a 0 en 0.6 s con t congelado y al seguir
 * vuelve desde el mismo t. Al salir (w = 0): resetNormalizedPose() sin tocar los huesos del
 * motor (dedos, hombros, pies, ojos… vuelven a identidad: crítica c.2), expresiones ajenas a
 * 0, fuera el proxy de mirada, ctx.setLookAt(true), ctx.encuadrar(null) y 'parado'. Así los
 * brazos siempre acaban en la pose de reposo de lune_vrm.js (petición de Diego).
 * Al entrar: ctx.encuadrar('cuerpo', true), ctx.setLookAt(false) y springBoneManager.reset()
 * (también en cada vuelta del bucle y en cada salto de más de 0.5 s).
 * Fin de la canción (o del clip, sin canción ni bucle): 'fin' y aguanta la pose 1.5 s
 * esperando otro cargar (siguiente/aleatorio: transición suave de 0.5 s desde lo que se ve);
 * si no llega, sale al reposo. Con bucle, vuelve a empezar sin 'fin'.
 * Otro cargar mientras suena: el de antes aguanta su pose (t congelado) hasta que el nuevo
 * esté listo; si estaba en pausa o saliendo (parar), sigue al reposo mientras carga (D5).
 *   inhibe  {idle, seguimiento, caricia, gesto: 1 − w, parpadeo: 1 − w si el clip parpadea}
 *   ocupado cargando, sonando, saliendo, 0 < w < 1 o en transición
 *   est.mmd = w > 0; est.baile ||= w > 0 (solo durante el frame: trasUpdate lo devuelve a lo
 *           de los demás). Duck: con est.hablando, volumen × 0.35.
 *   encuadre si otro módulo lo quita mientras baila (el baile procedural que se funde llama
 *           encuadrar(null)), se vuelve a poner (salvo en pantalla grande); al acabar no se
 *           suelta si el baile procedural sigue (él lleva el suyo).
 *   alDescargar (cambio de modelo): para y emite error {mensaje: 'modelo'}.
 * Carga: fetch(url, {cache:'no-store'}) solo de /bailes/ o /bailes_cache/ del mismo origen,
 * con Content-Length y bytes leídos ≤ 32 MiB. El .vrma: GLB con VRMC_vrm_animation y
 * NINGÚN uri en buffers/images (se rechaza antes del GLTFLoader) y, por si acaso, un
 * LoadingManager cuyo setURLModifier convierte en 'data:,' lo que no sea blob: o /bailes/.
 *
 * Sin imports de three: THREE, los cargadores, lune_vmd.js y LuneMMDAudio llegan por
 * `opciones` (la página los importa; Node: tests/js/mmd.test.mjs).
 */
import { clamp, suav, smoothstep } from './lune_modulos.js';

export const NOMBRE = 'mmd';
export const ORDEN = 60;
export const FASES = Object.freeze(['parado', 'cargando', 'listo', 'sonando', 'pausado', 'saliendo', 'error']);
/** Expresiones que escribe lune_vrm.js en cada frame (EMOCIONES + VISEMAS + parpadeos). */
export const EXPR_MOTOR = Object.freeze(['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral',
  'aa', 'ih', 'ou', 'ee', 'oh', 'blink', 'blinkLeft', 'blinkRight']);
const VISEMAS = new Set(['aa', 'ih', 'ou', 'ee', 'oh']);
const PARPADEOS = new Set(['blink', 'blinkLeft', 'blinkRight']);
export const PREFIJOS = Object.freeze(['/bailes/', '/bailes_cache/']);

export const PARAMS_MMD = Object.freeze({
  entradaS: 0.5,        // s de entrada del peso
  salidaS: 0.6,         // s de salida (parar, pausa, fin, error)
  corte: 12,            // suav hacia 0 al arrastrarla
  retencionS: 1.5,      // s que aguanta la pose tras 'fin' esperando otro cargar
  transicionS: 0.5,     // s de la transición de un baile al siguiente
  salto: 0.5,           // s: un salto mayor del reloj reinicia los muelles
  habla: 10,            // suav del apagado de los visemas del clip al hablar
  esperaModeloS: 20,    // s que cargar() espera a que haya modelo
  bytes: 32 << 20,      // tope de un .vmd/.vrma
  jsonMax: 4 << 20,     // tope del JSON de un .vrma
  urlMax: 1024,
});

const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);
const redondear = (v) => Math.round(num(v) * 1000) / 1000;

/**
 * URL absoluta si `url` es de /bailes/ o /bailes_cache/ del MISMO origen (ya codificada con %,
 * sin '..', '\\', '//', controles, query ni hash); si no, null.
 */
export function urlPermitida(url, origen) {
  if (typeof url !== 'string' || !url || url.length > PARAMS_MMD.urlMax) return null;
  if (/[\u0000- \u007f\\]/.test(url)) return null;
  let base;
  try { base = new URL(String(origen || '')); } catch (e) { return null; }
  if (base.protocol !== 'http:' && base.protocol !== 'https:') return null;
  let u;
  try { u = new URL(url, base.origin + '/'); } catch (e) { return null; }
  if (u.origin !== base.origin || u.username || u.password || u.search || u.hash) return null;
  const crudo = url.startsWith('/') ? url : url.startsWith(base.origin + '/') ? url.slice(base.origin.length) : null;
  if (crudo === null || crudo.includes('..') || crudo.includes('//') || /%2e%2e|%2f|%5c|%00/i.test(crudo)) return null;
  if (!PREFIJOS.some((p) => u.pathname.startsWith(p) && u.pathname.length > p.length)) return null;
  return u.href;
}

/** Datos de cargar() validados → {datos} o {error}. Acepta objeto o JSON; motion/cara en lista o planos. */
export function opcionesCarga(entrada, origen) {
  let o = entrada;
  if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { return { error: 'datos no válidos' }; } }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return { error: 'datos no válidos' };
  const tipo = o.tipo === 'vrma' ? 'vrma' : o.tipo === 'vmd' ? 'vmd' : null;
  if (!tipo) return { error: 'tipo no válido' };
  const juntar = (lista, planos) => (Array.isArray(lista) ? lista : planos.map((k) => o[k]))
    .filter((x) => x !== undefined && x !== null && x !== '');
  const motion = juntar(o.motion, ['motion0', 'motion1', 'motion2']);
  const cara = juntar(o.cara, ['cara0', 'cara1']);
  if (!motion.length || motion.length > (tipo === 'vrma' ? 1 : 3) || cara.length > 2) return { error: 'archivos no válidos' };
  const m = motion.map((u) => urlPermitida(u, origen)), c = cara.map((u) => urlPermitida(u, origen));
  if (m.some((x) => !x) || c.some((x) => !x)) return { error: 'ruta no permitida' };
  let audio = null;
  if (o.audio !== undefined && o.audio !== null && o.audio !== '') {
    audio = urlPermitida(o.audio, origen);
    if (!audio) return { error: 'ruta no permitida' };
  }
  const n = (v, d, a, b) => { const x = Number(v); return finito(x) && v !== null && v !== '' ? clamp(x, a, b) : d; };
  return {
    datos: {
      id: String(o.id ?? '').replace(/[^0-9A-Za-z_-]/g, '').slice(0, 64), tipo, motion: m, cara: c, audio,
      offsetMs: n(o.offsetMs, 0, -500, 500), enSitio: !!o.enSitio, bucle: !!o.bucle,
      brazoGrados: n(o.brazoGrados, 35, 25, 45), volumen: n(o.volumen, 1, 0, 1), autoplay: o.autoplay !== false,
    },
  };
}

/** Comprueba un .vrma (GLB) antes de dárselo al GLTFLoader → JSON; Error si no vale. */
export function validarGLB(buf, jsonMax = PARAMS_MMD.jsonMax) {
  const b = buf instanceof Uint8Array ? buf : ArrayBuffer.isView(buf) ? new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength) : new Uint8Array(buf || new ArrayBuffer(0));
  if (b.byteLength < 20) throw new Error('el .vrma está vacío o cortado');
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (dv.getUint32(0, true) !== 0x46546C67) throw new Error('el .vrma no es un GLB');
  if (dv.getUint32(4, true) !== 2) throw new Error('el .vrma no es glTF 2');
  if (dv.getUint32(8, true) > b.byteLength) throw new Error('el .vrma está cortado');
  const largo = dv.getUint32(12, true);
  if (dv.getUint32(16, true) !== 0x4E4F534A) throw new Error('el .vrma no empieza por JSON');
  if (largo > jsonMax) throw new Error('el JSON del .vrma es demasiado grande');
  if (20 + largo > b.byteLength) throw new Error('el .vrma está cortado');
  let json;
  try { json = JSON.parse(new TextDecoder().decode(b.subarray(20, 20 + largo))); } catch (e) { throw new Error('el JSON del .vrma no es válido'); }
  if (!json || typeof json !== 'object') throw new Error('el JSON del .vrma no es válido');
  if (!Array.isArray(json.extensionsUsed) || !json.extensionsUsed.includes('VRMC_vrm_animation')) {
    throw new Error('el archivo no es una VRM Animation (falta VRMC_vrm_animation)');
  }
  for (const lista of [json.buffers, json.images]) {
    for (const x of Array.isArray(lista) ? lista : []) {
      if (x && typeof x === 'object' && x.uri !== undefined) throw new Error('el .vrma pide archivos de fuera (uri): no se abre');
    }
  }
  return json;
}

/** Reloj mínimo si ui_web/lune_mmd_audio.js no está (misma API que LuneMMDAudio.crearReloj). */
function relojMinimo() {
  let t = 0, salto = 0;
  return {
    avanzar(dt, tA) {
      salto = 0;
      if (finito(dt) && dt > 0) t += dt;
      if (tA !== null && tA !== undefined && finito(Number(tA))) {
        const e = Number(tA) - t;
        if (Math.abs(e) > 0.08) { salto = e; t = Number(tA); } else t += 0.1 * e;
      }
      return t;
    },
    reiniciar(t0) { t = finito(Number(t0)) ? Number(t0) : 0; salto = 0; return t; },
    get t() { return t; },
    get salto() { return salto; },
  };
}

/**
 * instalar(ctx, opciones) → módulo del bus. opciones: {THREE = ctx.THREE, GLTFLoader,
 * VRMAnimationLoaderPlugin, createVRMAnimationClip, VRMAnimation, VRMLookAtQuaternionProxy,
 * vmd (módulo lune_vmd.js), audio (LuneMMDAudio), fetch, origen, params, ceder (horneado)}.
 */
export function instalar(ctx = {}, opciones = {}) {
  const op = opciones && typeof opciones === 'object' ? opciones : {};
  const THREE = op.THREE || ctx.THREE;
  const P = { ...PARAMS_MMD, ...(op.params || {}) };
  const vmd = op.vmd || null;
  const AUDIO = op.audio || globalThis.LuneMMDAudio || null;
  const fetchFn = typeof op.fetch === 'function' ? op.fetch : (typeof globalThis.fetch === 'function' ? globalThis.fetch.bind(globalThis) : null);
  const origen = op.origen || (globalThis.location && globalThis.location.origin) || '';
  const emitirCtx = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };
  const llamar = (fn, ...a) => { try { if (typeof fn === 'function') return fn(...a); } catch (e) { /* sigue */ } return undefined; };

  let fase = 'parado', id = '', error = '';
  let gen = 0;                        // cada cargar/parar/cambio de modelo invalida lo que esté en vuelo
  let actual = null;                  // {vrm, objetivos, duracion, conParpadeo, proxy, conIK}
  let transicion = null;              // {desde: Map(clave → valor), residuos: [objetivo], u}
  let wLin = 0, w = 0, escritoCero = true;
  let tClip = 0, ultimoSegundo = -1;
  let retencion = null;               // s que quedan aguantando la pose tras 'fin'
  let saliendo = false, entrado = false;
  let sostener = false;               // cargando otro: el que SONABA aguanta su pose (el pausado o el que sale, no)
  let bucle = false, enSitio = false, volumenBase = 1, offsetMs = 0;
  let conAudio = false, totalAudio = 0;
  let hablaK = 1, duckVisto = null;
  let ahoraS = 0;
  let camRef = null;                  // cámara tras poner el encuadre 'cuerpo' (para volver a ponerlo si otro lo quita)
  let baileOtro = false;              // est.baile de OTRO módulo (el baile procedural) en este frame
  let player = null;
  const reloj = AUDIO && typeof AUDIO.crearReloj === 'function' ? AUDIO.crearReloj({ tolerancia: 0.08, correccion: 0.1 }) : relojMinimo();
  const esperas = new Set();

  const _q = THREE ? new THREE.Quaternion() : null, _q2 = THREE ? new THREE.Quaternion() : null;
  const _v = THREE ? new THREE.Vector3() : null, _v2 = THREE ? new THREE.Vector3() : null;

  function reproductor() {
    if (!player && AUDIO && typeof AUDIO.crear === 'function') {
      player = AUDIO.crear({ ahora: () => ahoraS * 1000 });
      player.volumen(volumenBase);
      player.offset(offsetMs);
    }
    return player;
  }
  const totalActual = () => (conAudio && totalAudio > 0 ? totalAudio : actual ? actual.duracion : 0);
  function emitirMMD(f, extra = {}) {
    emitirCtx('mmd', { fase: f, id, t: redondear(tClip), total: redondear(totalActual()), ...extra });
  }
  /** play() de la canción; si el navegador lo rechaza, el baile no sigue en silencio: error. */
  function sonar() {
    const a = conAudio ? reproductor() : null;
    if (!a) return;
    const g = gen;
    Promise.resolve(a.reproducir()).then((ok) => {
      if (!ok && g === gen && conAudio && fase === 'sonando') fallar('la canción no se puede reproducir: ' + String(a.error || '?'));
    }, () => { /* reproducir() no rechaza */ });
  }
  function reiniciarMuelles() {
    const v = actual ? actual.vrm : (typeof ctx.vrm === 'function' ? ctx.vrm() : null);
    llamar(v && v.springBoneManager && v.springBoneManager.reset && v.springBoneManager.reset.bind(v.springBoneManager));
  }

  // ── Carga ─────────────────────────────────────────────────────────────────────
  function esperarModelo() {
    const v = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
    if (v) return Promise.resolve(v);
    return new Promise((res, rej) => {
      const e = { res, rej, t: null };
      e.t = setTimeout(() => { esperas.delete(e); rej(new Error('no hay modelo cargado')); }, P.esperaModeloS * 1000);
      esperas.add(e);
    });
  }
  function soltarEsperas(motivo) {
    for (const e of esperas) { clearTimeout(e.t); e.rej(new Error(motivo)); }
    esperas.clear();
  }

  async function leerLimitado(r, max) {
    if (r.body && typeof r.body.getReader === 'function') {
      const lector = r.body.getReader();
      const trozos = [];
      let total = 0;
      for (;;) {
        const { done, value } = await lector.read();
        if (done) break;
        total += value.byteLength;
        if (total > max) { try { await lector.cancel(); } catch (e) { /* ya */ } throw new Error('el archivo es demasiado grande'); }
        trozos.push(value);
      }
      const out = new Uint8Array(total);
      let p = 0;
      for (const t of trozos) { out.set(t, p); p += t.byteLength; }
      return out.buffer;
    }
    const ab = await r.arrayBuffer();
    if (!ab || ab.byteLength > max) throw new Error('el archivo es demasiado grande');
    return ab;
  }
  async function descargar(url) {
    const abs = urlPermitida(url, origen);
    if (!abs) throw new Error('ruta no permitida');
    if (!fetchFn) throw new Error('sin fetch');
    const r = await fetchFn(abs, { cache: 'no-store' });
    if (!r || !r.ok) throw new Error(`no se pudo leer el archivo (${r ? r.status : '?'})`);
    const cl = Number(r.headers && typeof r.headers.get === 'function' ? r.headers.get('content-length') : NaN);
    if (finito(cl) && cl > P.bytes) throw new Error('el archivo es demasiado grande');
    return leerLimitado(r, P.bytes);
  }

  async function animDeVRMA(ab) {
    validarGLB(ab, P.jsonMax);
    if (!op.GLTFLoader || !op.VRMAnimationLoaderPlugin) throw new Error('falta el cargador de .vrma');
    const manager = new THREE.LoadingManager();
    manager.setURLModifier((u) => (/^blob:/i.test(String(u)) || urlPermitida(String(u), origen) ? u : 'data:,'));
    const loader = new op.GLTFLoader(manager);
    loader.register((p) => new op.VRMAnimationLoaderPlugin(p));
    const gltf = await new Promise((res, rej) => {
      try { loader.parse(ab, '', res, rej); } catch (e) { rej(e); }
    });
    const anim = gltf && gltf.userData && Array.isArray(gltf.userData.vrmAnimations) ? gltf.userData.vrmAnimations[0] : null;
    if (!anim) throw new Error('el .vrma no trae ninguna animación');
    return anim;
  }

  /** Posiciones de reposo del rig en convención VRM 1.0 (los 0.x con x/z negadas). */
  function reposoVRM1(vrm, sXZ) {
    const hum = vrm.humanoid || {};
    let rp = null;
    try { rp = hum.normalizedRestPose; } catch (e) { rp = null; }
    const out = {};
    const poner = (k, p) => { out[k] = { position: sXZ < 0 ? [-p[0], p[1], -p[2]] : [p[0], p[1], p[2]] }; };
    if (rp && typeof rp === 'object') {
      for (const k of Object.keys(rp)) {
        const p = rp[k] && rp[k].position;
        if (Array.isArray(p) && p.length >= 3 && p.every((x) => finito(Number(x)))) poner(k, p.map(Number));
      }
    }
    if (!out.hips) {
      const h = ctx.huesos || {};
      for (const k of Object.keys(h)) { const n = h[k]; if (n && n.position) poner(k, [n.position.x, n.position.y, n.position.z]); }
    }
    return out;
  }

  async function animDeVMD(bufs, caras, d, vrm, g) {
    if (!vmd || typeof vmd.parsearVMD !== 'function') throw new Error('falta lune_vmd.js');
    if (!op.VRMAnimation) throw new Error('falta three-vrm-animation');
    const lista = [...bufs, ...caras].map((b) => vmd.parsearVMD(b));
    const sXZ = ctx.sXZ === -1 ? -1 : 1;
    const restPose = reposoVRM1(vrm, sXZ);
    const hum = vrm.humanoid;
    const hor = await vmd.hornear(THREE, lista, {
      brazoGrados: d.brazoGrados, restPose,
      huesosModelo: (h) => !!(hum && typeof hum.getNormalizedBoneNode === 'function' && hum.getNormalizedBoneNode(h)),
      cancelado: () => g !== gen, ceder: op.ceder,
    });
    const anim = vmd.aVRMAnimation(op.VRMAnimation, THREE, hor, restPose.hips ? restPose.hips.position : null);
    anim.conIK = !!hor.conIK;
    return anim;
  }

  /** La cara de un VMD de labios sobre un .vrma (opcional: si no vale, el baile sigue sin ella). */
  async function caraSobreVRMA(anim, caras, g) {
    if (!caras.length || !vmd) return;
    let hor;
    try { hor = await vmd.hornear(THREE, caras.map((b) => vmd.parsearVMD(b)), { soloCara: true, cancelado: () => g !== gen, ceder: op.ceder }); }
    catch (e) { return; }
    for (const [p, v] of hor.expr) {
      if (!anim.expressionTracks.preset.has(p)) anim.expressionTracks.preset.set(p, new THREE.NumberKeyframeTrack(p, hor.tiempos, v));
    }
    anim.duration = Math.max(num(anim.duration), num(hor.duracion));
  }

  /** Clip del VRM + objetivos (qué nodo o expresión mueve cada pista y con qué interpolante). */
  function crearActual(anim, vrm) {
    const sXZ = ctx.sXZ === -1 ? -1 : 1;
    const Proxy = op.VRMLookAtQuaternionProxy;
    const conMirada = !!(anim.lookAtTrack && vrm.lookAt && Proxy && vrm.scene);
    let proxy = null, proxyNuevo = false;
    if (conMirada) {
      proxy = (vrm.scene.children || []).find((o) => o instanceof Proxy) || null;
      if (!proxy) { proxy = new Proxy(vrm.lookAt); proxyNuevo = true; vrm.scene.add(proxy); }
      proxy.name = 'VRMLookAtQuaternionProxy';
    }
    const vista = {
      scene: vrm.scene, humanoid: vrm.humanoid, expressionManager: vrm.expressionManager || null,
      lookAt: conMirada ? vrm.lookAt : null, meta: { metaVersion: sXZ < 0 ? '0' : '1' },
    };
    let clip;
    try { clip = op.createVRMAnimationClip(anim, vista); } catch (e) {
      if (proxyNuevo && proxy.parent) proxy.parent.remove(proxy);
      throw e;
    }
    const pistas = new Map((clip.tracks || []).map((tr) => [tr.name, tr]));
    const motor = new Set(Object.values(ctx.huesos || {}));
    const objetivos = [];
    const hum = vrm.humanoid;
    for (const hueso of anim.humanoidTracks.rotation.keys()) {
      const node = hum.getNormalizedBoneNode(hueso);
      const tr = node && pistas.get(`${node.name}.quaternion`);
      if (!tr) continue;
      objetivos.push({ tipo: 'rot', clave: node, node, hueso, motor: motor.has(node), interp: tr.createInterpolant(),
        proc: new THREE.Quaternion(), salida: new THREE.Quaternion() });
    }
    if (anim.humanoidTracks.translation.has('hips')) {
      const node = hum.getNormalizedBoneNode('hips');
      const tr = node && pistas.get(`${node.name}.position`);
      if (tr) {
        let r = null;
        try { r = hum.normalizedRestPose && hum.normalizedRestPose.hips && hum.normalizedRestPose.hips.position; } catch (e) { r = null; }
        const reposo = Array.isArray(r) ? new THREE.Vector3(r[0], r[1], r[2]) : node.position.clone();
        objetivos.push({ tipo: 'pos', clave: 'pos:hips', node, reposo, interp: tr.createInterpolant(),
          proc: new THREE.Vector3(), salida: new THREE.Vector3() });
      }
    }
    const em = vrm.expressionManager;
    if (em) {
      for (const mapa of [anim.expressionTracks.preset, anim.expressionTracks.custom]) {
        for (const nombre of mapa.keys()) {
          const expr = em.getExpression(nombre);
          const tr = expr && pistas.get(em.getExpressionTrackName(nombre));
          if (!tr) continue;
          objetivos.push({ tipo: 'expr', clave: expr, expr, nombre, motor: EXPR_MOTOR.includes(nombre), visema: VISEMAS.has(nombre),
            interp: tr.createInterpolant(), proc: 0, salida: 0 });
        }
      }
    }
    if (conMirada) {
      const tr = pistas.get(`${proxy.name}.quaternion`);
      if (tr) objetivos.push({ tipo: 'mirada', clave: 'mirada', proxy, interp: tr.createInterpolant() });
    }
    return {
      vrm, objetivos, proxy, proxyNuevo,
      duracion: Math.max(0, num(Number(clip.duration), num(anim.duration))),
      conParpadeo: objetivos.some((o) => o.tipo === 'expr' && PARPADEOS.has(o.nombre)),
      conIK: !!anim.conIK,
    };
  }

  /** Suelta el clip: fuera el proxy de mirada (salvo si lo hereda `sigue`). */
  function liberarClip(a, sigue = null) {
    if (!a) return;
    if (a.proxy && (!sigue || sigue.proxy !== a.proxy)) {
      if (a.proxy.parent) a.proxy.parent.remove(a.proxy);
      const la = a.vrm && a.vrm.lookAt;
      if (la) { if (typeof la.reset === 'function') llamar(la.reset.bind(la)); else { la.yaw = 0; la.pitch = 0; } }
    }
    for (const o of a.objetivos) o.interp = null;
  }

  /** Reposo de lo que movió el clip SIN tocar los huesos del motor (que ya tienen su pose de este frame). */
  function restaurarReposo(a) {
    if (!a || !a.vrm) return;
    const hum = a.vrm.humanoid;
    const guardados = [];
    for (const n of Object.values(ctx.huesos || {})) if (n && n.quaternion) guardados.push([n, n.quaternion.clone()]);
    if (hum && typeof hum.resetNormalizedPose === 'function') llamar(hum.resetNormalizedPose.bind(hum));
    else for (const o of a.objetivos) { if (o.tipo === 'rot' && !o.motor) o.node.quaternion.identity(); if (o.tipo === 'pos') o.node.position.copy(o.reposo); }
    for (const [n, q] of guardados) n.quaternion.copy(q);
    for (const o of a.objetivos) if (o.tipo === 'expr' && !o.motor) o.expr.weight = 0;
  }

  function activar(nuevo) {
    if (actual && (w > 1e-3 || transicion)) {
      // Transición desde lo que se ve (el baile que acaba de terminar o el que se sostenía)
      const viejos = [...actual.objetivos, ...(transicion ? transicion.residuos : [])].filter((o) => o.tipo !== 'mirada');
      const desde = new Map();
      for (const o of viejos) desde.set(o.clave, o.tipo === 'expr' ? o.salida : o.salida.clone());
      const claves = new Set(nuevo.objetivos.map((o) => o.clave));
      const residuos = viejos.filter((o) => !claves.has(o.clave));
      liberarClip(actual, nuevo);
      transicion = { desde, residuos, u: 0 };
      actual = nuevo;
    } else {
      if (actual) { liberarClip(actual, nuevo); restaurarReposo(actual); }
      transicion = null;
      actual = nuevo;
      wLin = 0; w = 0;
    }
    escritoCero = false;
  }

  function fallar(mensaje) {
    error = String(mensaje || 'error').slice(0, 200);
    fase = 'error';
    retencion = null;
    if (player) player.parar();
    if (actual && (w > 1e-3 || transicion)) saliendo = true;      // sale al reposo sin 'parado'
    else if (actual || entrado) finalizar(false);
    emitirCtx('mmd', { fase: 'error', id, mensaje: error });
  }

  async function cargar(entrada) {
    const { datos: d, error: err } = opcionesCarga(entrada, origen);
    const g = ++gen;
    soltarEsperas('reemplazado');
    if (!d) { id = ''; fallar(err); return false; }
    // Lo que SONABA se sostiene (t congelado, canción en pausa) hasta que el nuevo esté listo
    // (transición suave). Lo que estaba en pausa (D5) o saliendo al reposo se queda en reposo:
    // «cargando» no le devuelve el peso (nada de brazos arriba mientras carga el siguiente).
    sostener = !saliendo && (fase === 'sonando' || (fase === 'cargando' && sostener));
    if (player && fase === 'sonando') player.pausar();
    fase = 'cargando'; id = d.id; error = ''; retencion = null; saliendo = false;
    bucle = d.bucle; enSitio = d.enSitio; volumenBase = d.volumen; offsetMs = d.offsetMs;
    emitirMMD('cargando');
    try {
      if (!THREE) throw new Error('falta three.js');
      const vrm = await esperarModelo();
      if (g !== gen) return false;
      const pMov = Promise.all(d.motion.map(descargar));
      const pCara = Promise.all(d.cara.map(descargar));
      let pAudio = Promise.resolve({ ok: true, total: 0 });
      if (d.audio) {
        const a = reproductor();
        if (!a) throw new Error('falta lune_mmd_audio.js');
        a.volumen(volumenBase); a.offset(offsetMs);
        pAudio = a.cargar(d.audio);
      } else if (player) player.liberar();
      const [movs, caras] = await Promise.all([pMov, pCara]);
      if (g !== gen) return false;
      let anim;
      if (d.tipo === 'vrma') { anim = await animDeVRMA(movs[0]); await caraSobreVRMA(anim, caras, g); }
      else anim = await animDeVMD(movs, caras, d, vrm, g);
      const ra = await pAudio;
      if (g !== gen) return false;
      if (!ra || !ra.ok) throw new Error('la canción no se puede reproducir: ' + String((ra && ra.error) || '?'));
      if (vrm !== (typeof ctx.vrm === 'function' ? ctx.vrm() : null)) throw new Error('modelo');
      const nuevo = crearActual(anim, vrm);
      conAudio = !!d.audio; totalAudio = conAudio ? num(ra.total) : 0;
      activar(nuevo);
      fase = 'listo';
      tClip = 0;
      emitirMMD('listo');
      if (d.autoplay) reproducir();
      return true;
    } catch (e) {
      if (g !== gen) return false;
      fallar((e && e.message) || String(e));
      return false;
    }
  }

  // ── Reproducción ──────────────────────────────────────────────────────────────
  function camara() {
    const c = ctx.camera && ctx.camera.position;
    return c ? { x: num(c.x), y: num(c.y), z: num(c.z) } : null;
  }
  function encuadrarCuerpo() { llamar(ctx.encuadrar, 'cuerpo', true); camRef = camara(); }
  /** Si otro módulo quita el encuadre de cuerpo entero (el baile procedural que se funde llama
   *  encuadrar(null)), se vuelve a poner; en pantalla grande la cámara es suya. */
  function vigilarEncuadre(e) {
    if (!entrado || (e && e.grande)) return;
    const c = camara();
    if (!c) return;
    if (!camRef || Math.abs(c.x - camRef.x) > 1e-6 || Math.abs(c.y - camRef.y) > 1e-6 || Math.abs(c.z - camRef.z) > 1e-6) encuadrarCuerpo();
  }
  function entrar() {
    if (!entrado) {
      entrado = true;
      encuadrarCuerpo();
      llamar(ctx.setLookAt, false);
    }
    reiniciarMuelles();
  }

  function reproducir() {
    if (!actual) return false;
    if (fase === 'pausado') return pausa(false);
    if (fase !== 'listo') return fase === 'sonando';
    fase = 'sonando'; saliendo = false; retencion = null;
    const a = conAudio ? reproductor() : null;
    tClip = reloj.reiniciar(a ? num(a.t(), 0) : 0);
    ultimoSegundo = Math.floor(tClip);
    entrar();
    sonar();
    emitirMMD('sonando');
    return true;
  }

  function pausa(on) {
    const quiere = on === undefined || on === null ? fase !== 'pausado' : !!on;
    if (quiere && fase === 'cargando') sostener = false;   // en pausa mientras carga: el de antes, al reposo
    if (quiere && fase === 'sonando' && retencion === null) {
      fase = 'pausado';
      if (conAudio && player) player.pausar();
      emitirMMD('pausado');
      return true;
    }
    if (!quiere && fase === 'pausado') {
      fase = 'sonando';
      sonar();
      emitirMMD('sonando');
      return true;
    }
    return quiere ? fase === 'pausado' : fase === 'sonando';
  }

  function salir() {
    fase = 'saliendo'; saliendo = true; retencion = null;
    if (player) player.parar();
  }

  function parar() {
    gen++;
    soltarEsperas('parado');
    if (!actual) {
      if (fase === 'parado' || fase === 'error') { fase = 'parado'; return false; }
      finalizar(true);
      return true;
    }
    if (w > 1e-3 || transicion) { salir(); return true; }
    finalizar(true);
    return true;
  }

  function finalizar(emitirParado) {
    if (actual) { liberarClip(actual); restaurarReposo(actual); }
    if (transicion) {
      for (const o of transicion.residuos) {
        if (o.tipo === 'expr' && !o.motor) o.expr.weight = 0;
      }
      transicion = null;
    }
    actual = null;
    if (entrado) {
      entrado = false; camRef = null;
      llamar(ctx.setLookAt, true);
      if (!baileOtro) llamar(ctx.encuadrar, null);     // si el baile procedural sigue, él lleva su encuadre
    }
    wLin = 0; w = 0; saliendo = false; retencion = null; escritoCero = true;
    conAudio = false; totalAudio = 0;
    if (player) player.liberar();
    if (emitirParado) { fase = 'parado'; emitirMMD('parado'); }
  }

  function vuelta() {
    if (conAudio && player) {
      player.parar();
      sonar();
      tClip = reloj.reiniciar(num(player.t(), 0));
    } else {
      const d = actual.duracion;
      tClip = reloj.reiniciar(d > 0 ? tClip - d * Math.floor(tClip / d) : 0);
    }
    ultimoSegundo = Math.floor(tClip);
    reiniciarMuelles();
  }

  function avanzarTiempo(d) {
    if (fase !== 'sonando') return;
    if (retencion !== null) {
      retencion -= d;
      if (retencion <= 0) salir();
      return;
    }
    const a = conAudio ? player : null;
    const tA = a && a.sonando() ? a.t() : null;
    const antes = tClip;
    tClip = reloj.avanzar(d, tA);
    if (Math.abs(tClip - antes - d) > P.salto) reiniciarMuelles();
    const acabo = a ? a.terminado() : tClip >= actual.duracion;
    if (acabo) {
      if (bucle && (a || actual.duracion > 0)) vuelta();
      else {
        if (!a) tClip = actual.duracion;
        retencion = P.retencionS;
        emitirMMD('fin');
        return;
      }
    }
    const s = Math.floor(tClip);
    if (s !== ultimoSegundo) { ultimoSegundo = s; emitirMMD('t'); }
  }

  // ── Mezcla ────────────────────────────────────────────────────────────────────
  function capturarProc(o) {
    if (o.tipo === 'rot') { if (o.motor) o.proc.copy(o.node.quaternion); else o.proc.identity(); }
    else if (o.tipo === 'pos') o.proc.copy(o.reposo);
    else if (o.tipo === 'expr') o.proc = o.motor ? num(Number(o.expr.weight)) : 0;
  }

  function aplicar(peso) {
    const a = actual;
    const k = transicion ? smoothstep(clamp(transicion.u, 0, 1)) : 1;
    const desde = transicion ? transicion.desde : null;
    const tc = clamp(num(tClip), 0, a.duracion);
    for (const o of a.objetivos) {
      if (!o.interp) continue;
      const v = o.interp.evaluate(tc);
      if (o.tipo === 'mirada') {
        o.proxy.quaternion.set(v[0], v[1], v[2], v[3]);      // el proxy pone yaw/pitch en vrm.lookAt
        const la = a.vrm.lookAt;
        if (la) { la.yaw = num(la.yaw) * peso; la.pitch = num(la.pitch) * peso; }
        continue;
      }
      capturarProc(o);
      const ini = desde && k < 1 ? desde.get(o.clave) : undefined;
      if (o.tipo === 'rot') {
        _q.set(v[0], v[1], v[2], v[3]);
        _q2.copy(o.proc).slerp(_q, peso);
        if (ini) { _q.copy(_q2); _q2.copy(ini).slerp(_q, k); }
        o.node.quaternion.copy(_q2);
        o.salida.copy(_q2);
      } else if (o.tipo === 'pos') {
        _v.set(v[0], v[1], v[2]);
        _v2.copy(o.proc).lerp(_v, peso);
        if (enSitio) { _v2.x = o.proc.x; _v2.z = o.proc.z; }
        if (ini) { _v.copy(_v2); _v2.copy(ini).lerp(_v, k); }
        o.node.position.copy(_v2);
        o.salida.copy(_v2);
      } else {
        const wE = peso * (o.visema ? hablaK : 1);
        let x = o.proc + (num(v[0]) - o.proc) * wE;
        if (ini !== undefined) x = ini + (x - ini) * k;
        x = clamp(x, 0, 1);
        o.expr.weight = x;
        o.salida = x;
      }
    }
    if (transicion) {
      for (const o of transicion.residuos) {
        capturarProc(o);
        const ini = desde.get(o.clave);
        if (o.tipo === 'rot') { _q2.copy(ini || o.proc).slerp(o.proc, k); o.node.quaternion.copy(_q2); o.salida.copy(_q2); }
        else if (o.tipo === 'pos') { _v2.copy(ini || o.proc).lerp(o.proc, k); o.node.position.copy(_v2); o.salida.copy(_v2); }
        else if (o.tipo === 'expr') { const x = clamp((ini ?? o.proc) + (o.proc - (ini ?? o.proc)) * k, 0, 1); o.expr.weight = x; o.salida = x; }
      }
    }
  }

  function trasPose(dt, t, est) {
    const d = Math.max(0, num(dt));
    ahoraS = num(t, ahoraS + d);
    const e = est || (typeof ctx.estado === 'function' ? ctx.estado() : null) || {};
    const habla = !!e.hablando;
    if (player && conAudio) {
      if (habla !== duckVisto) { duckVisto = habla; player.duck(habla); }
      player.paso();
    }
    hablaK += ((habla ? 0 : 1) - hablaK) * suav(d, P.habla);
    if (!actual) return;
    avanzarTiempo(d);
    if (!actual) return;
    const quiere = !saliendo && (fase === 'sonando' || (fase === 'cargando' && sostener));
    if (e.drag) wLin += (0 - wLin) * suav(d, P.corte);
    else if (quiere) wLin = Math.min(1, wLin + d / P.entradaS);
    else wLin = Math.max(0, wLin - d / P.salidaS);
    if (wLin < 1e-4 && !quiere) wLin = 0;
    w = smoothstep(wLin);
    if (w > 0 || transicion || !escritoCero) {
      // La transición avanza antes de aplicar: el último frame ya escribe el reposo de los residuos
      if (transicion) transicion.u = Math.min(1, transicion.u + d / P.transicionS);
      aplicar(w);
      if (transicion && transicion.u >= 1) transicion = null;
      escritoCero = w <= 0 && !transicion;
    }
    if (saliendo && w <= 0 && !transicion) finalizar(fase === 'saliendo');
  }

  /**
   * Las órdenes tal como las manda Python (ui/companion.py mmd → window.luneMMD(orden, datos)):
   * cargar {…} · pausa {on} · parar · volumen {volumen} · offset {offsetMs} · en_sitio {enSitio}
   * · bucle {bucle} (y reproducir). Orden desconocida → false.
   */
  function ordenPython(orden, datos) {
    const d = datos && typeof datos === 'object' ? datos : {};
    const valor = (k) => (datos !== null && typeof datos === 'object' ? d[k] : datos);
    switch (String(orden || '')) {
      case 'cargar': return cargar(datos);
      case 'reproducir': return reproducir();
      case 'pausa': { const on = valor('on'); return pausa(typeof on === 'boolean' ? on : undefined); }
      case 'parar': return parar();
      case 'volumen': return api.volumen(valor('volumen'));
      case 'offset': return api.offset(valor('offsetMs'));
      case 'en_sitio': return api.enSitio(!!valor('enSitio'));
      case 'bucle': return api.bucle(!!valor('bucle'));
      default: return false;
    }
  }

  const api = {
    cargar: (datos) => cargar(datos),
    reproducir: () => reproducir(),
    pausa: (on) => pausa(on),
    parar: () => parar(),
    volumen(v) {
      const n = Number(v);
      if (finito(n)) volumenBase = clamp(n, 0, 1);
      if (player) player.volumen(volumenBase);
      return volumenBase;
    },
    offset(ms) {
      const n = Number(ms);
      if (finito(n)) {
        const nuevo = clamp(n, -500, 500);
        if (!conAudio && actual) tClip = reloj.reiniciar(tClip + (nuevo - offsetMs) / 1000);
        offsetMs = nuevo;
        if (player) player.offset(offsetMs);
      }
      return offsetMs;
    },
    enSitio(on) { enSitio = !!on; return enSitio; },
    bucle(on) { bucle = !!on; return bucle; },
    orden: (orden, datos) => ordenPython(orden, datos),
    estado: () => ({
      fase, id, t: redondear(tClip), total: redondear(totalActual()), peso: w, error,
      bucle, enSitio, volumen: volumenBase, offsetMs, conAudio, retencion: retencion !== null,
      transicion: !!transicion, ik: !!(actual && actual.conIK),
    }),
  };

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    alCargar() {
      const v = typeof ctx.vrm === 'function' ? ctx.vrm() : null;
      for (const e of esperas) { clearTimeout(e.t); e.res(v); }
      esperas.clear();
    },
    alDescargar() {
      const habia = !!actual || ['cargando', 'listo', 'sonando', 'pausado', 'saliendo'].includes(fase);
      gen++;
      if (actual) liberarClip(actual);
      actual = null; transicion = null;
      if (entrado) { entrado = false; camRef = null; llamar(ctx.setLookAt, true); llamar(ctx.encuadrar, null); }
      wLin = 0; w = 0; saliendo = false; retencion = null; escritoCero = true;
      conAudio = false; totalAudio = 0;
      if (player) player.liberar();
      if (habia) { fase = 'error'; error = 'modelo'; emitirCtx('mmd', { fase: 'error', id, mensaje: 'modelo' }); }
    },
    pose(out, dt, t, est) {
      ahoraS = num(t, ahoraS);
      const e = est || {};
      baileOtro = !!e.baile;                 // lo puso el baile procedural (orden 40) en este frame
      e.mmd = w > 0;
      if (w > 0) e.baile = true;             // sentarse (orden 85) no suelta el encuadre mientras bailamos
      vigilarEncuadre(e);
    },
    trasPose,
    trasUpdate(dt, t, est) {
      // est.baile es de quien baila EN ESTE frame: lo nuestro se quita al acabar el frame para
      // que el siguiente vea solo lo de los demás (sin baile procedural nadie lo reescribe).
      const e = est || {};
      if (e.baile && !baileOtro) e.baile = false;
    },
    ocupado() { return fase === 'cargando' || fase === 'sonando' || fase === 'saliendo' || (w > 0 && w < 1) || !!transicion; },
    inhibe() {
      const r = 1 - w;
      return { idle: r, seguimiento: r, caricia: r, gesto: r, parpadeo: actual && actual.conParpadeo ? r : 1 };
    },
    api,
  };
}
