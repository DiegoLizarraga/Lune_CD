/*
 * ui_web/anim/lune_anim_mmd.js — módulo 'mmdAnim' de la mascota ANIMADA: los bailes de la
 * biblioteca en una mascota sin esqueleto (corte 9; decisión D1 de Diego, «equivalente
 * mínimo»).
 *
 * La animada no puede seguir un .vmd ni un .vrma: suena la canción del baile en esta página
 * (ui_web/lune_mmd_audio.js, el mismo reproductor que la VRM) y Lune hace el baile
 * procedural de los cortes 5 y 6 (window.luneBailar / window.lunePulso, del módulo
 * anim/lune_anim_baile.js) al pulso ANALIZADO de esa canción: Python (nucleo/bailes.
 * Biblioteca.analizar_pulso) manda {bpm, fase0} y aquí la fase sale del reloj del audio
 * con LuneMMDAudio.pulsoEn(t, {bpm, fase0}), como mucho a 2 Hz (lunePulso extrapola entre
 * medias). El panel avisa «esta mascota no tiene esqueleto: baila a su manera».
 *
 * Python (ui/mmd_qt.ControlMMD → ui/companion.py mmd → window.luneMMD) pide:
 *   api.cargar({id, tipo:'audio', audio, bpm, fase0, offsetMs, volumen, bucle, autoplay, titulo})
 *   api.reproducir() · api.pausa(on?) · api.parar() · api.volumen(v) · api.offset(ms)
 *   api.bucle(on) · api.enSitio(on) (sin efecto: no hay cadera) · api.estado()
 * y la página traduce window.luneMMD(orden, datos) con `orden(api, orden, datos)`.
 * Fases (las del VRM): parado | cargando | listo | sonando | pausado | error.
 * Eventos ctx.emitir('mmd', {fase, id, t, total, mensaje}): cargando, listo, sonando,
 * pausado, t (cada segundo de canción), fin, parado, error.
 *
 *   · Suena al acabar de cargar si nadie pidió pausa entretanto (autoplay y pausa se
 *     guardan en `quiereSonar`: una pausa pedida mientras carga —ventana oculta, juego—
 *     no se pierde).
 *   · Pausa (D5): deja de bailar (luneBailar(false): vuelve al reposo) con la canción en
 *     pausa; al seguir, desde el mismo punto y otra vez a bailar.
 *   · Fin de la canción: 'fin' y sigue bailando 1.5 s esperando otro cargar (siguiente o
 *     aleatorio: sin cortes); si no llega, deja de bailar y 'parado'. Con bucle, vuelve a
 *     empezar sin 'fin'.
 *   · Arrastrarla o dormida: lo lleva el baile (su peso baja) y la canción sigue.
 *   · Hablando Lune (est.hablando): la canción al 35 % (duck de LuneMMDAudio).
 * Solo acepta audio de /bailes/ o /bailes_cache/ del MISMO origen (el servidor local).
 * Este módulo no escribe estilos: el movimiento es del de baile. Sin DOM en los tests:
 * tests/js/anim_mmd.test.mjs.
 */
import { clamp } from './lune_anim_modulos.js';

export const NOMBRE = 'mmdAnim';
export const ORDEN = 60;
export const FASES = Object.freeze(['parado', 'cargando', 'listo', 'sonando', 'pausado', 'error']);
export const PREFIJOS = Object.freeze(['/bailes/', '/bailes_cache/']);

export const PARAMS_MMD_ANIM = Object.freeze({
  pulsoS: 0.5,          // lunePulso como mucho a 2 Hz
  energia: 0.7,         // la del baile de los sprites con una canción (ui/mmd_qt ENERGIA_D1)
  retencionS: 1.5,      // tras 'fin' sigue bailando esperando otro cargar
  bpm: 120,
  urlMax: 1024,
});

const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);
const redondear = (v) => Math.round(num(v) * 1000) / 1000;

/**
 * URL absoluta si `url` es de /bailes/ o /bailes_cache/ del MISMO origen (ya codificada con
 * %, sin '..', '\\', '//', controles, query ni hash); si no, null. (La misma regla que
 * ui_web/vrm/lune_mmd.js y ui/companion.py url_mmd_segura.)
 */
export function urlPermitida(url, origen) {
  if (typeof url !== 'string' || !url || url.length > PARAMS_MMD_ANIM.urlMax) return null;
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

/** Datos de cargar() validados → {datos} o {error}. Acepta objeto o JSON. */
export function opcionesAudio(entrada, origen) {
  let o = entrada;
  if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { return { error: 'datos no válidos' }; } }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return { error: 'datos no válidos' };
  if (o.tipo !== 'audio') return { error: 'esta mascota solo baila con la canción (tipo «audio»)' };
  const audio = urlPermitida(o.audio, origen);
  if (!audio) return { error: 'ruta no permitida' };
  const n = (v, d, a, b) => {
    const x = Number(v);
    return v !== null && v !== undefined && v !== '' && typeof v !== 'boolean' && finito(x) ? clamp(x, a, b) : d;
  };
  let fase0 = n(o.fase0, 0, 0, 1);
  if (fase0 >= 1) fase0 = 0;
  return {
    datos: {
      id: String(o.id ?? '').replace(/[^0-9A-Za-z_-]/g, '').slice(0, 64), audio,
      bpm: n(o.bpm, PARAMS_MMD_ANIM.bpm, 40, 240), fase0,
      offsetMs: n(o.offsetMs, 0, -500, 500), volumen: n(o.volumen, 1, 0, 1),
      bucle: o.bucle === true, autoplay: o.autoplay !== false,
    },
  };
}

/** Fase del pulso sin lune_mmd_audio.js (misma cuenta que LuneMMDAudio.pulsoEn). */
function pulsoEnLocal(t, datos) {
  const b = clamp(num(Number(datos.bpm), PARAMS_MMD_ANIM.bpm), 40, 240);
  let f = num(Number(datos.fase0)) + num(Number(t)) * b / 60;
  f -= Math.floor(f);
  return { bpm: b, fase: f };
}

/**
 * window.luneMMD(orden, datos) de la página → el api de este módulo. `datos` objeto o JSON:
 *   cargar {…} · pausa {on} · parar · volumen {volumen} · offset {offsetMs} · en_sitio {enSitio}
 *   · bucle {bucle} → bool; estado → JSON.
 */
export function orden(api, ord, datos) {
  if (!api) return false;
  let d = datos;
  if (typeof d === 'string') { try { d = JSON.parse(d); } catch (e) { d = null; } }
  const v = (clave) => (d && typeof d === 'object' && !Array.isArray(d) ? d[clave] : d);
  try {
    switch (String(ord || '')) {
      case 'cargar':
        if (!d || typeof d !== 'object' || Array.isArray(d)) return false;
        Promise.resolve(api.cargar(d)).catch(() => { /* el módulo ya avisó con 'error' */ });
        return true;
      case 'pausa': {
        const on = v('on');
        api.pausa(on === true || on === false ? on : undefined);
        return true;
      }
      case 'parar': return !!api.parar();
      case 'volumen': api.volumen(Number(v('volumen'))); return true;
      case 'offset': api.offset(Number(v('offsetMs'))); return true;
      case 'en_sitio': api.enSitio(v('enSitio') === true); return true;
      case 'bucle': api.bucle(v('bucle') === true); return true;
      case 'estado': return JSON.stringify(api.estado());
      default: return false;
    }
  } catch (e) {
    return false;
  }
}

/**
 * instalar(ctx, opciones) para crearRegistroAnim().registrar(). opciones: {audio
 * (LuneMMDAudio), bailar(on, opts), pulso(bpm, fase, energia), origen, params}.
 */
export function instalar(ctx = {}, opciones = {}) {
  const op = opciones && typeof opciones === 'object' ? opciones : {};
  const P = { ...PARAMS_MMD_ANIM, ...(op.params || {}) };
  const AUDIO = op.audio || globalThis.LuneMMDAudio || null;
  const origen = op.origen || (globalThis.location && globalThis.location.origin) || '';
  const bailarFn = typeof op.bailar === 'function' ? op.bailar : null;
  const pulsoFn = typeof op.pulso === 'function' ? op.pulso : null;
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  const llamar = (fn, ...a) => { try { if (typeof fn === 'function') return fn(...a); } catch (e) { /* sigue */ } return undefined; };
  const emitir = (tipo, datos) => llamar(ctx.emitir, tipo, datos);

  let fase = 'parado', id = '', error = '';
  let gen = 0;                        // cada cargar/parar invalida lo que esté en vuelo
  let player = null;
  let total = 0, tAudio = 0, bpm = P.bpm, fase0 = 0;
  let bucle = false, volumen = 1, offsetMs = 0;
  let quiereSonar = false;            // autoplay o la última pausa pedida
  let bailando = false;               // este módulo pidió luneBailar(true)
  let retencion = null;               // s que quedan bailando tras 'fin'
  let ahora = 0, ultimoPulso = -Infinity, ultimoSegundo = -1, duckVisto = null;

  function reproductor() {
    if (!player && AUDIO && typeof AUDIO.crear === 'function') {
      player = AUDIO.crear({ ahora: () => ahora * 1000 });
    }
    return player;
  }
  function emitirMMD(f, extra = {}) {
    emitir('mmd', { fase: f, id, t: redondear(tAudio), total: redondear(total), ...extra });
  }
  function bailarOn() {
    if (bailando) return;
    bailando = true;
    llamar(bailarFn, true, { particulas: true });
  }
  function bailarOff() {
    if (!bailando) return;
    bailando = false;
    llamar(bailarFn, false);
  }
  function mandarPulso() {
    ultimoPulso = ahora;
    if (!pulsoFn) return;
    const p = AUDIO && typeof AUDIO.pulsoEn === 'function' ? AUDIO.pulsoEn(tAudio, { bpm, fase0 }) : pulsoEnLocal(tAudio, { bpm, fase0 });
    llamar(pulsoFn, p.bpm, p.fase, P.energia);
  }
  function leerT() {
    const t = player ? player.t() : null;
    if (t !== null && t !== undefined && finito(Number(t))) tAudio = Math.max(0, Number(t));
    return tAudio;
  }
  /** play(); si el navegador lo rechaza, no se baila en silencio: error. */
  function sonar() {
    const a = player;
    if (!a) return;
    const g = gen;
    Promise.resolve(a.reproducir()).then((ok) => {
      if (!ok && g === gen && fase === 'sonando') fallar('la canción no se puede reproducir: ' + String(a.error || '?'));
    }, () => { /* reproducir() no rechaza */ });
  }

  function fallar(mensaje) {
    error = String(mensaje || 'error').slice(0, 200);
    fase = 'error';
    retencion = null;
    quiereSonar = false;
    if (player) player.parar();
    bailarOff();
    emitir('mmd', { fase: 'error', id, mensaje: error });
  }

  async function cargar(entrada) {
    const { datos: d, error: err } = opcionesAudio(entrada, origen);
    const g = ++gen;
    if (!d) { id = ''; fallar(err); return false; }
    // Lo que sonaba calla mientras carga el nuevo; el baile sigue (transición sin cortes)
    if (player && fase === 'sonando') player.pausar();
    fase = 'cargando'; id = d.id; error = ''; retencion = null;
    quiereSonar = d.autoplay;
    bucle = d.bucle; volumen = d.volumen; offsetMs = d.offsetMs; bpm = d.bpm; fase0 = d.fase0;
    total = 0; tAudio = 0; ultimoSegundo = -1;
    emitirMMD('cargando');
    const a = reproductor();
    if (!a) { fallar('falta lune_mmd_audio.js'); return false; }
    a.volumen(volumen);
    a.offset(offsetMs);
    let r;
    try { r = await a.cargar(d.audio); } catch (e) { r = { ok: false, error: String((e && e.message) || e) }; }
    if (g !== gen) return false;
    if (!r || !r.ok) { fallar('la canción no se puede reproducir: ' + String((r && r.error) || '?')); return false; }
    total = num(Number(r.total));
    fase = 'listo';
    emitirMMD('listo');
    if (quiereSonar) reproducir();
    else bailarOff();                  // en pausa desde antes de sonar: quieta
    return true;
  }

  function reproducir() {
    if (fase === 'pausado') return pausa(false);
    if (fase !== 'listo') return fase === 'sonando';
    fase = 'sonando'; quiereSonar = true; retencion = null;
    sonar();
    leerT();
    ultimoSegundo = Math.floor(tAudio);
    bailarOn();
    mandarPulso();
    emitirMMD('sonando');
    return true;
  }

  function pausa(on) {
    const quiere = on === true || on === false ? on : fase === 'sonando';
    quiereSonar = !quiere;
    if (quiere) {
      if (fase === 'sonando' && retencion === null) {
        fase = 'pausado';
        if (player) player.pausar();
        bailarOff();                   // D5: al reposo, sin congelarse a mitad de un paso
        emitirMMD('pausado');
        return true;
      }
      return fase === 'pausado';
    }
    if (fase === 'pausado') {
      fase = 'sonando';
      sonar();
      bailarOn();
      mandarPulso();
      emitirMMD('sonando');
      return true;
    }
    if (fase === 'listo') return reproducir();
    return fase === 'sonando';
  }

  function salir() {
    retencion = null;
    quiereSonar = false;
    if (player) player.liberar();
    bailarOff();
    fase = 'parado';
    emitirMMD('parado');
  }

  function parar() {
    gen++;
    quiereSonar = false;
    retencion = null;
    const antes = fase;
    if (player) player.liberar();
    bailarOff();
    fase = 'parado';
    if (antes === 'parado' || antes === 'error') return false;
    emitirMMD('parado');
    return true;
  }

  function tick(dt, t, estado) {
    const d = Math.max(0, num(dt));
    ahora = finito(t) ? t : ahora + d;
    const e = estado || est();
    if (player) {
      const habla = !!e.hablando;
      if (habla !== duckVisto) { duckVisto = habla; player.duck(habla); }
      player.paso();
    }
    e.mmd = fase === 'sonando' && retencion === null;
    if (fase !== 'sonando') return;
    if (retencion !== null) {
      retencion -= d;
      if (retencion <= 0) salir();
      return;
    }
    leerT();
    if (player && player.terminado()) {
      if (bucle) {
        player.parar();                // a 0 y otra vez, sin 'fin'
        sonar();
        tAudio = 0;
        ultimoSegundo = 0;
        mandarPulso();
        return;
      }
      retencion = P.retencionS;
      e.mmd = false;
      emitirMMD('fin');
      return;
    }
    if (ahora - ultimoPulso >= P.pulsoS - 1e-9) mandarPulso();
    const s = Math.floor(tAudio);
    if (s !== ultimoSegundo) { ultimoSegundo = s; emitirMMD('t'); }
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    tick,
    ocupado() { return fase === 'cargando' || fase === 'sonando'; },
    alDetener() { /* oculta: el bucle se pausa (companion.py ya la ha puesto en pausa) */ },
    api: {
      cargar: (datos) => cargar(datos),
      reproducir: () => reproducir(),
      pausa: (on) => pausa(on),
      parar: () => parar(),
      volumen(v) {
        const n = Number(v);
        if (finito(n)) volumen = clamp(n, 0, 1);
        if (player) player.volumen(volumen);
        return volumen;
      },
      offset(ms) {
        const n = Number(ms);
        if (finito(n)) offsetMs = clamp(n, -500, 500);
        if (player) player.offset(offsetMs);
        return offsetMs;
      },
      enSitio() { return false; },       // sin esqueleto no hay cadera que dejar en el sitio
      bucle(on) { bucle = !!on; return bucle; },
      estado: () => ({
        fase, id, t: redondear(tAudio), total: redondear(total), bpm, fase0, bucle, volumen, offsetMs,
        bailando, quiereSonar, retencion: retencion !== null, error,
      }),
    },
  };
}
