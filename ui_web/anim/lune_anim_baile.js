/*
 * ui_web/anim/lune_anim_baile.js — módulo 'baileAnim' de la asistente ANIMADA:
 * baile con la música sobre el #stage (cortes 5 y 6).
 *
 * Mismas funciones de página que el VRM (ui_web/vrm/lune_baile_proc.js):
 * window.luneBailar(on, opts) y window.lunePulso(bpm, fase, energia). El pulso se
 * extrapola con LuneRitmo.crearReloj (ui_web/lune_ritmo.js; sin él, un metrónomo).
 *
 * Por pulso (b = pulsos continuos, A = 0.4 + 0.6·energía):
 *   · translateY de −6..0 px: sube entre pulsos y cae en el pulso;
 *   · giro ±4° alterno (un pulso a cada lado) con pivote abajo al centro. ±4° y no
 *     más: el stage mide 210 px en una ventana de 240 (crítica c.6);
 *   · aplastado en cada golpe (escala ±3.5 %).
 * Todo con rotarEn/escalarEn/mover en el hook `pose`: el registro es el dueño de
 * style.transform (este módulo NO escribe estilos).
 * Clip: capa de emoción 'baile' = 'happy' (prioridad 30, por debajo de dormir,
 * arrastre y mareo) mientras baila; al acabar se quita y vuelve la emoción base.
 * Peso: entra con suav(5), sale con suav(8); arrastrarla (est.drag) lo corta con
 * suav(12) y dormida no baila. est.baile = baila o le queda peso.
 *
 * API: bailar(on, {estilo, cambiar, cambiarS, particulas}) · pulso(bpm, fase, energia) · estado()
 * Eventos: ctx.emitir('baile', {on, estilo}). opciones.alGolpe(energia): notas ♪.
 * La lógica pura (paso) se prueba sin DOM: tests/js/anim_baile.test.mjs.
 */
import { clamp, suav, rotarEn, escalarEn, mover } from './lune_anim_modulos.js';
import { fijarCapa, quitarCapa } from './lune_anim_video.js';

export const NOMBRE = 'baileAnim';
export const ORDEN = 40;

export const PARAMS_BAILE_ANIM = Object.freeze({
  maxGrados: 4,           // giro alterno (crítica c.6)
  maxY: 6,                // px que sube entre pulsos
  estiron: 0.035,         // aplastado en el golpe
  entrada: 5, salida: 8, corte: 12,
  capa: 'baile', clip: 'happy', prioridad: 30,
  pivoteX: '50%', pivoteY: '100%',
  bpm: 120,
});

const TAU = Math.PI * 2;
const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

/**
 * Transformación del baile en el pulso b (continuo) con energía e: {grados, dy, sx, sy}.
 * grados en CSS (± alterno, |g| ≤ maxGrados), dy ≤ 0 (px; − = arriba).
 */
export function paso(b, energia, p = PARAMS_BAILE_ANIM) {
  const x = num(b);
  const A = 0.4 + 0.6 * clamp(num(energia, 0.5), 0, 1);
  const grados = num(p.maxGrados, 4) * A * Math.cos(Math.PI * x);
  const salto = (1 - Math.cos(TAU * x)) / 2;              // 0 en el pulso, 1 a mitad
  const g = Math.pow((1 + Math.cos(TAU * x)) / 2, 4);     // golpe seco en el pulso
  const k = num(p.estiron, 0.035) * g * A;
  const dy = -num(p.maxY, 6) * A * salto;
  return { grados: grados === 0 ? 0 : grados, dy: dy === 0 ? 0 : dy, sx: 1 + 0.5 * k, sy: 1 - k };
}

function nuevoReloj(opciones) {
  if (opciones.reloj && typeof opciones.reloj.avanzar === 'function') return opciones.reloj;
  const R = globalThis.LuneRitmo;
  if (R && typeof R.crearReloj === 'function') return R.crearReloj({ bpm: PARAMS_BAILE_ANIM.bpm });
  let pulsos = 0, t = null, bpm = PARAMS_BAILE_ANIM.bpm, e = 0.6, golpe = false;
  const estado = () => ({ pulsos, bpm, energia: e, golpe });
  return {
    avanzar(tt) {
      golpe = false;
      if (finito(tt) && t !== null && tt > t) {
        const antes = pulsos;
        pulsos += (bpm / 60) * Math.min(tt - t, 0.5);
        golpe = Math.floor(pulsos) > Math.floor(antes);
      }
      if (finito(tt)) t = tt;
      return estado();
    },
    pulso(b, f, en) { if (finito(b) && b > 0) bpm = clamp(b, 40, 240); if (finito(en)) e = clamp(en, 0, 1); return true; },
    metronomo(b) { if (finito(b) && b > 0) bpm = clamp(b, 40, 240); return true; },
    reiniciar() { pulsos = 0; t = null; return this; },
    estado,
  };
}

/** instalar(ctx, opciones) para crearRegistroAnim().registrar(). opciones: {reloj, alGolpe, params}. */
export function instalar(ctx = {}, opciones = {}) {
  const p = { ...PARAMS_BAILE_ANIM, ...(opciones.params || {}) };
  const reloj = nuevoReloj(opciones);
  const alGolpe = typeof opciones.alGolpe === 'function' ? opciones.alGolpe : null;
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };

  let activo = false, peso = 0, ahora = 0, particulas = true, estilo = null;
  let ultimo = reloj.estado ? reloj.estado() : { pulsos: 0, energia: 0.6, bpm: p.bpm };
  let pulsoPendiente = null;             // lo de la API se aplica en el próximo tick (reloj del registro)

  function bailar(on, opts = {}) {
    on = !!on;
    const o = opts && typeof opts === 'object' ? opts : {};
    if ('particulas' in o) particulas = !!o.particulas;
    if (typeof o.estilo === 'string') estilo = o.estilo;
    const e = est();
    if (on && !activo) {
      if (peso <= 0.001) {
        if (typeof reloj.reiniciar === 'function') reloj.reiniciar();
        if (typeof reloj.metronomo === 'function') reloj.metronomo(p.bpm);
      }
      activo = true;
      fijarCapa(e, p.capa, p.clip, p.prioridad);
      e.baile = true;
      emitir('baile', { on: true, estilo });
    } else if (!on && activo) {
      activo = false;
      quitarCapa(e, p.capa);
      emitir('baile', { on: false, estilo });
    }
    return true;
  }

  function tick(dt, t, estado) {
    const d = num(dt);
    ahora = finito(t) ? t : ahora + d;
    const e = estado || est();
    const para = !activo || e.drag || e.dormida || e.grande;
    const objetivo = para ? 0 : 1;
    const k = objetivo > peso ? suav(d, p.entrada) : suav(d, e.drag ? p.corte : p.salida);
    peso += (objetivo - peso) * k;
    if (objetivo === 0 && peso < 1e-3) peso = 0;
    if (objetivo === 1 && peso > 1 - 1e-4) peso = 1;
    e.baile = activo || peso > 0;
    if (pulsoPendiente) {
      const [b0, f0, e0] = pulsoPendiente;
      pulsoPendiente = null;
      reloj.pulso(b0, f0, e0, ahora);
    }
    ultimo = reloj.avanzar(ahora);
    if (ultimo.golpe && peso > 0.5 && particulas && alGolpe) {
      try { alGolpe(num(ultimo.energia, 0.5)); } catch (err) { /* sin notas */ }
    }
  }

  function pose(out) {
    if (peso <= 0) return;
    const s = paso(num(ultimo.pulsos), num(ultimo.energia, 0.5), p);
    const g = s.grados * peso, dy = s.dy * peso;
    if (Math.abs(g) > 0.005) out.transform.push(rotarEn(g, p.pivoteX, p.pivoteY));
    if (Math.abs(dy) > 0.01) out.transform.push(mover(0, dy));
    const sx = 1 + (s.sx - 1) * peso, sy = 1 + (s.sy - 1) * peso;
    if (Math.abs(sy - 1) > 0.0002) out.transform.push(escalarEn([sx, sy], p.pivoteX, p.pivoteY));
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    tick, pose,
    ocupado() { return activo || peso > 0; },
    alDetener() { /* el bucle se pausa (ventana oculta): al volver sigue donde iba */ },
    api: {
      bailar: (on, opts) => bailar(on, opts),
      pulso(bpm, fase, energia) {
        const b = Number(bpm);
        if (!finito(b) || b <= 0) return false;
        pulsoPendiente = [b, Number(fase), Number(energia)];
        return true;
      },
      estado: () => ({ activo, peso, particulas, estilo, bpm: num(ultimo.bpm, p.bpm), pulsos: num(ultimo.pulsos), energia: num(ultimo.energia) }),
    },
  };
}
