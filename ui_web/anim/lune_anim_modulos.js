/*
 * ui_web/anim/lune_anim_modulos.js — registro de módulos de la asistente animada (companion.html).
 *
 * Para qué sirve: la asistente de vídeo (WebM) va a recibir varias funciones en cortes
 * distintos (arrastre, baile, pantalla grande, comida, pausa en juegos…). En vez de
 * que todas editen el mismo script de la página y se pisen, cada una es un módulo
 * `ui_web/anim/lune_*.js` que se registra aquí, con el mismo patrón que el bus del
 * VRM (ui_web/vrm/lune_modulos.js, del que reutiliza el núcleo y las utilidades).
 *
 * Contrato de un módulo (lo devuelve `instalar(ctx)`):
 *   {
 *     nombre: 'baileAnim', orden: 40,
 *     alIniciar() {}, alDetener() {},
 *     alEmocion(nombre) {},                 // la página cambió de clip/emoción
 *     tick(dt, t, est) {},                  // cada frame mientras el bucle corre
 *     pose(out, dt, t, est) {},             // aporta transformaciones CSS (ver abajo)
 *     ocupado(est) { return false },        // true → el bucle va a fps completos
 *     inhibe(est) { return {} },            // {idle, seguimiento, caricia, parpadeo, gesto}
 *     api: {}
 *   }
 *
 * Composición de estilos (para que dos módulos no se sobrescriban `transform`):
 * cada frame se crea out = {transform: [], filtro: [], opacidad: 1}; cada módulo
 * AÑADE piezas en su orden y el registro escribe una sola vez en el elemento
 * objetivo (por defecto #stage) con transform-origin 0 0. Las piezas con pivote
 * propio se hacen con rotarEn()/escalarEn(), que usan % del propio elemento:
 *
 *   pose(out) { out.transform.push(rotarEn(angulo, '50%', '6%')); out.filtro.push('brightness(.75)'); }
 *
 * El registro es el DUEÑO de style.transform, style.filter y style.opacity del
 * objetivo: nadie más debe escribirlos a mano (usar un hook `pose`).
 *
 * Uso en la página:
 *   import { crearRegistroAnim } from './anim/lune_anim_modulos.js';
 *   const reg = crearRegistroAnim({ stage, video, burbuja });
 *   reg.registrar(instalarBaile);  reg.iniciar();
 *   reg.estado({ drag: true });    // la página actualiza `est` desde luneDrag, luneSleep…
 */
import { crearRegistro, clamp } from '../vrm/lune_modulos.js';

export {
  FACTORES, clamp, lerp, suav, smoothstep, Muelle, smoothDamp, Bolsa, crearAleatorio, emitirPorDefecto,
} from '../vrm/lune_modulos.js';

export const HOOKS_ANIM = Object.freeze(['alIniciar', 'alDetener', 'alEmocion', 'tick', 'pose']);

const num = (v, d = 0) => (Number.isFinite(v) ? v : d);
const redondeo = (v) => Math.round(num(v) * 1000) / 1000;
/** Unidad CSS: los números son px. */
const unidad = (v) => (typeof v === 'number' ? `${redondeo(v)}px` : String(v).trim());
/** La misma longitud con el signo cambiado ('50%' → '-50%', '-4px' → '4px'). */
const negar = (v) => { const s = unidad(v); return s.startsWith('-') ? s.slice(1) : `-${s}`; };
/** Envuelve una pieza para que pivote en (ox, oy) con transform-origin 0 0. */
const enPivote = (ox, oy, pieza) => `translate(${unidad(ox)}, ${unidad(oy)}) ${pieza} translate(${negar(ox)}, ${negar(oy)})`;

/** translate en px. */
export function mover(x = 0, y = 0) { return `translate(${redondeo(x)}px, ${redondeo(y)}px)`; }

/** Rotación en grados alrededor de (ox, oy), en unidades CSS del propio elemento ('50%', 12 = 12px). */
export function rotarEn(grados, ox = '50%', oy = '100%') {
  return enPivote(ox, oy, `rotate(${redondeo(grados)}deg)`);
}

/** Escala alrededor de (ox, oy). `s` puede ser un número o [sx, sy]. */
export function escalarEn(s, ox = '50%', oy = '100%') {
  const [sx, sy] = Array.isArray(s) ? s : [s, s];
  return enPivote(ox, oy, `scale(${redondeo(num(sx, 1))}, ${redondeo(num(sy, 1))})`);
}

/** Estado compartido por defecto de la asistente animada (la página lo va actualizando). */
export function estadoInicial() {
  return {
    emocion: 'normal', drag: false, dormida: false, hablando: false, baile: false,
    grande: false, comiendo: false, menu: false, pausa: false,
    cursor: { px: 0, py: 0, nx: 0, ny: 0 },
  };
}

/**
 * Crea el registro. Opciones además de {stage, video, burbuja}:
 *   objetivo   elemento al que se aplican los estilos compuestos (por defecto stage)
 *   emitir     (tipo, datos) → cola hacia Python (por defecto window.luneEmitir)
 *   raf/caf    requestAnimationFrame/cancelAnimationFrame (inyectables en tests)
 *   ahora      () → ms (por defecto performance.now)
 *   fpsReposo  fps del bucle cuando ningún módulo está ocupado (por defecto 15)
 *   temporizador {poner(fn, ms) → id, quitar(id)}: la espera entre pasos en reposo (11.2). En
 *              reposo el paso siguiente lo da un temporizador y no un requestAnimationFrame en
 *              cada refresco del monitor (ese bucle a 60/s sin pintar nada costaba un 7-10 % de
 *              CPU en la asistente); con algo ocupado, o con la página oculta, rAF. Por defecto
 *              setTimeout; con `raf` inyectado y sin `temporizador` (los tests de siempre), nunca.
 *   esperaMinMs  esperas más cortas que esto van con rAF (por defecto 20)
 */
export function crearRegistroAnim({
  stage = null, video = null, burbuja = null, objetivo = null, emitir = null,
  raf = null, caf = null, ahora = null, fpsReposo = 15, temporizador = null, esperaMinMs = 20,
} = {}) {
  const g = globalThis;
  const est = estadoInicial();
  let videoActual = video;
  const ctx = {
    stage, burbuja,
    /** <video> visible ahora (con doble búfer cambia en cada emoción). */
    video: () => (typeof videoActual === 'function' ? videoActual() : videoActual),
    estado: () => est,
  };
  if (typeof emitir === 'function') ctx.emitir = emitir;
  const reg = crearRegistro(ctx, { etiqueta: 'luneAnim' });

  const pedirFrame = raf || (typeof g.requestAnimationFrame === 'function' ? g.requestAnimationFrame.bind(g) : (f) => setTimeout(() => f(reloj()), 16));
  const cancelarFrame = caf || (typeof g.cancelAnimationFrame === 'function' ? g.cancelAnimationFrame.bind(g) : clearTimeout);
  const reloj = ahora || (() => (g.performance && g.performance.now ? g.performance.now() : Date.now()));

  const tm = temporizador && typeof temporizador.poner === 'function' ? temporizador
    : (raf ? null : { poner: (f, ms) => setTimeout(f, ms), quitar: (id) => clearTimeout(id) });

  let destino = objetivo || stage;
  let corriendo = false, idFrame = null, ultimoTick = null, t = 0;
  let espera = null;                     // temporizador del paso siguiente en reposo (o null)
  let aplicado = { transform: null, filtro: null, opacidad: null };

  /** Compone las piezas de `pose` y las escribe solo si cambiaron (evita recalcular estilos). */
  function componer(dt) {
    const out = { transform: [], filtro: [], opacidad: 1 };
    reg.llamar('pose', out, dt, t, est);
    if (!destino || !destino.style) return out;
    const tr = out.transform.join(' ');
    const fi = out.filtro.join(' ');
    const op = clamp(num(out.opacidad, 1), 0, 1);
    if (tr !== aplicado.transform) {
      destino.style.transformOrigin = tr ? '0 0' : '';
      destino.style.transform = tr;
      aplicado.transform = tr;
    }
    if (fi !== aplicado.filtro) { destino.style.filter = fi; aplicado.filtro = fi; }
    if (op !== aplicado.opacidad) { destino.style.opacity = op === 1 ? '' : String(op); aplicado.opacidad = op; }
    return out;
  }

  /** Un paso del bucle; exportado para tests y para páginas que ya tienen su propio bucle. */
  function paso(ms) {
    const ahoraMs = num(ms, reloj());
    if (ultimoTick !== null) {
      // En reposo (ningún módulo ocupado) se salta frames hasta llegar a fpsReposo.
      const intervalo = reg.ocupado(est) ? 0 : 1000 / Math.max(1, num(fpsReposo, 15));
      if (ahoraMs - ultimoTick + 0.5 < intervalo) return false;
    }
    // Pestaña frenada o vuelta de suspensión: como mucho 0.1 s por paso, sin saltos.
    const dt = ultimoTick === null ? 0 : clamp((ahoraMs - ultimoTick) / 1000, 0, 0.1);
    ultimoTick = ahoraMs;
    t += dt;
    reg.llamar('tick', dt, t, est);
    componer(dt);
    return true;
  }

  function quitarEspera() {
    if (espera === null) return;
    try { tm.quitar(espera); } catch (e) { /* ya salió */ }
    espera = null;
  }

  /** El paso siguiente: rAF si algo está ocupado; en reposo, el temporizador hasta que toque. */
  function siguiente() {
    if (!corriendo || idFrame !== null || espera !== null) return;
    const intervalo = 1000 / Math.max(1, num(fpsReposo, 15));
    const falta = ultimoTick === null || reg.ocupado(est) ? 0 : intervalo - (reloj() - ultimoTick);
    const oculta = g.document && g.document.hidden === true;
    if (tm && !oculta && falta > esperaMinMs) {
      espera = tm.poner(() => { espera = null; bucle(reloj()); }, falta);
    } else {
      idFrame = pedirFrame(bucle);
    }
  }

  function bucle(ms) {
    idFrame = null;
    if (!corriendo) return;
    try { paso(ms); } finally { siguiente(); }
  }

  /** Algo pasó (una llamada a un módulo, una emoción…): el paso, ya, sin esperar al temporizador. */
  function despertar() {
    if (espera === null) return;
    quitarEspera();
    if (corriendo && idFrame === null) idFrame = pedirFrame(bucle);
  }

  function iniciar() {
    if (corriendo) return false;
    corriendo = true; ultimoTick = null;
    reg.llamar('alIniciar');
    idFrame = pedirFrame(bucle);
    return true;
  }

  function detener() {
    if (!corriendo) return false;
    corriendo = false;
    if (idFrame !== null) { try { cancelarFrame(idFrame); } catch (e) { /* ya no existe */ } }
    idFrame = null;
    quitarEspera();
    reg.llamar('alDetener');
    return true;
  }

  // Lo que llega de Python o de la página (luneDrag, luneTouch… van por api) puede ocupar a un
  // módulo: el paso, ya. El cursor no (llega 30 veces por segundo y no pone nada en marcha).
  const apiBase = reg.api, registrarBase = reg.registrar;
  reg.api = (...args) => { const r = apiBase(...args); despertar(); return r; };
  reg.registrar = (mod) => { const r = registrarBase(mod); despertar(); return r; };

  return Object.assign(reg, {
    est, paso, iniciar, detener, componer,
    corriendo: () => corriendo,
    /** Mezcla `parcial` en el estado compartido y lo devuelve. */
    estado(parcial) {
      if (parcial && typeof parcial === 'object') {
        let otro = false;
        for (const k of Object.keys(parcial)) {
          if (k === 'cursor' && parcial.cursor && typeof parcial.cursor === 'object') Object.assign(est.cursor, parcial.cursor);
          else { est[k] = parcial[k]; otro = true; }
        }
        if (otro) despertar();
      }
      return est;
    },
    /** La página cambió de clip: avisa a los módulos. */
    emocion(nombre) { est.emocion = String(nombre || 'normal'); reg.llamar('alEmocion', est.emocion); despertar(); },
    setVideo(v) { videoActual = v; },
    setObjetivo(el) { destino = el; aplicado = { transform: null, filtro: null, opacidad: null }; },
  });
}
