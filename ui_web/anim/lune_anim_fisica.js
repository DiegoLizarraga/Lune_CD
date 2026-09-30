/*
 * ui_web/anim/lune_anim_fisica.js — arrastre, toque y sueño de la asistente ANIMADA.
 *
 * Para qué sirve: en el modo VRM, lune_vrm.js ya reacciona a luneDrag/luneTouch/
 * luneSleep; en el modo animado (clips WebM de companion.html) esas funciones no
 * existían y Python las llamaba en vano. Este módulo del registro
 * (ui_web/anim/lune_anim_modulos.js) las implementa con CSS sobre el #stage:
 *
 *   drag(on, vx, vy)   vx/vy en px/ms (lo que manda companion.py, igual que al VRM).
 *                      Balanceo con un muelle 2D (0.9 Hz, ζ 0.5, de Mate-Engine):
 *                        · ángulo = clamp(−vx·0.0167, ±6°), vx en px/s, pivote
 *                          arriba-centro (50 % / 6 %). ±6° y no ±20°: el stage mide
 *                          210 px en una ventana de 240 y más giro lo recorta.
 *                          Convención matemática (positivo = antihorario): en CSS se
 *                          aplica rotate(−ángulo), así el cuerpo cuelga DETRÁS del
 *                          movimiento, como un péndulo sujeto por arriba.
 *                        · estirón vertical ±2.5 % según vy (sube → se estira).
 *                      Cara (capa 'arrastre' de lune_anim_video.js): 'surprised'
 *                      0.4 s al levantarla y luego 'nervous' mientras dure; si se la
 *                      mueve muy deprisa (> 1500 px/s) vuelve a 'surprised'
 *                      (histéresis a 1100 px/s y 0.8 s mínimo por cara).
 *                      Mareo: 4 o más inversiones de sentido a > 800 px/s en 1.5 s
 *                      → capa 'dizzy' (clip nervous) 2.5 s + bamboleo, evento 'mareo',
 *                      enfriamiento de 10 s.
 *                      El arrastre dura al menos 0.3 s desde la última muestra (como
 *                      dragMinimo del VRM) y la velocidad caduca si Python deja de
 *                      mandarla (ratón quieto con el botón pulsado).
 *   tocar()            minirrebote (salta ~5 px y aplasta un poco) y despierta.
 *   dormir(on)         clase .lune-dormida en el stage + zzz + capa 'dormir'
 *                      ('sleeping': lune_anim_video.js pone el clip o el sustituto)
 *                      + respiración lenta. Eventos 'dormir' / 'despertar'.
 *
 * Mismas reglas que el VRM: arrastrar o tocar despierta; setEmocion('sleeping')
 * duerme y cualquier emoción que no sea 'normal' despierta (hook alEmocion).
 *
 * Eventos hacia Python (ctx.emitir → window.luneEventos): arrastre {on},
 * dormir {}, despertar {}, mareo {}.
 *
 * El registro es el dueño de style.transform del stage: aquí solo se añaden piezas
 * en `pose(out)` (rotarEn / escalarEn / mover). Las clases CSS (.lune-dormida) están
 * en ui_web/css/asistente_anim.css.
 *
 * En la página: publicar(window, reg) crea window.luneDrag, luneTouch y luneSleep
 * (misma firma que en companion_vrm.html) sobre reg.api('fisica', …).
 * La lógica pura (anguloObjetivo, CaraArrastre, DetectorMareo, reboteToque…) se
 * prueba sin DOM en tests/js/anim_fisica.test.mjs.
 */
import { Muelle, clamp, suav, rotarEn, escalarEn, mover } from './lune_anim_modulos.js';
import { fijarCapa, quitarCapa, asegurarZzz } from './lune_anim_video.js';

export const NOMBRE = 'fisica';
export const ORDEN = 20;

/** Parámetros (ajustables en caliente con luneMod('fisica', 'params', {...})). */
export const PARAMS_FISICA = Object.freeze({
  // Muelle 2D del balanceo (AvatarSwayController de Mate-Engine)
  frec: 0.9, zeta: 0.5,
  ganancia: 0.0167,            // °/(px/s)
  maxAngulo: 6,                // ° (crítica c.6)
  invertir: 1,                 // -1 si en pantalla sale al revés
  pivoteX: '50%', pivoteY: '6%',
  ganEstiron: 0.00003,         // escala Y por px/s de vy
  maxEstiron: 0.025,
  filtro: 12,                  // 1/s: suavizado de la velocidad que llega de Python
  filtroMareo: 30,             // 1/s: suavizado (más rápido) para contar inversiones
  caducidad: 0.12,             // s sin muestras → velocidad 0
  dragMinimo: 0.3,             // s tras la última muestra antes de soltar de verdad
  // Caras por movimiento
  sorpresa: 0.4,               // s de 'surprised' al levantarla
  velRapida: 1500, velRapidaSalida: 1100, sostenCara: 0.8,
  // Mareo al agitarla
  mareoVel: 800, mareoInversiones: 4, mareoVentana: 1.5, mareoDuracion: 2.5, mareoEnfriamiento: 10,
  mareoAmplitud: 3, mareoFrec: 1.4,
  // Toque y sueño
  toqueDuracion: 0.7, toqueAltura: 5,
  dormirEntrada: 1.0, dormirSalida: 0.45,
  respiracion: 0.006, respiracionPeriodo: 4,
});

const finito = Number.isFinite;
const num = (v, d = 0) => (finito(v) ? v : d);

// ── Lógica pura ────────────────────────────────────────────────────────────────

/**
 * Ángulo objetivo del balanceo en grados (convención matemática, + = antihorario):
 * clamp(−vx·ganancia, ±maxAngulo), con vx en px/s (+ = hacia la derecha).
 */
export function anguloObjetivo(vx, p = PARAMS_FISICA) {
  const inv = p.invertir === -1 ? -1 : 1;
  const m = Math.abs(num(p.maxAngulo, 6));
  const a = clamp(-num(vx) * num(p.ganancia, 0.0167) * inv, -m, m);
  return a === 0 ? 0 : a;                              // sin -0
}

/** Grados para CSS rotate() (positivo = horario en pantalla). */
export function anguloCSS(angulo) {
  const a = -num(angulo);
  return a === 0 ? 0 : a;
}

/** Estirón vertical (fracción de escala Y) por la velocidad vertical en px/s. */
export function estironObjetivo(vy, p = PARAMS_FISICA) {
  const m = Math.abs(num(p.maxEstiron, 0.025));
  const e = clamp(-num(vy) * num(p.ganEstiron, 0.00003), -m, m);
  return e === 0 ? 0 : e;
}

/**
 * Cara durante el arrastre: 'surprised' los primeros `sorpresa` s, luego 'nervous';
 * por encima de velRapida vuelve a 'surprised' (sale por debajo de velRapidaSalida)
 * y cada cara dura al menos sostenCara s para que los clips no parpadeen.
 */
export class CaraArrastre {
  constructor(p = PARAMS_FISICA) { this.p = p; this.terminar(); }

  iniciar(t) {
    this.t0 = num(t); this.tCambio = this.t0; this.fase = 'inicio'; this.rapida = false;
    this.cara = 'surprised';
    return this.cara;
  }

  actualizar(t, velocidad) {
    if (!this.fase) return null;
    const p = this.p;
    const v = Math.abs(num(velocidad));
    if (!this.rapida && v > p.velRapida) this.rapida = true;
    else if (this.rapida && v < p.velRapidaSalida) this.rapida = false;
    if (this.fase === 'inicio') {
      if (num(t) - this.t0 < p.sorpresa) return (this.cara = 'surprised');
      this.fase = 'arrastre';
      this.cara = this.rapida ? 'surprised' : 'nervous';
      this.tCambio = num(t);
      return this.cara;
    }
    const deseada = this.rapida ? 'surprised' : 'nervous';
    if (deseada !== this.cara && num(t) - this.tCambio >= p.sostenCara) {
      this.cara = deseada;
      this.tCambio = num(t);
    }
    return this.cara;
  }

  terminar() { this.fase = null; this.cara = null; this.t0 = 0; this.tCambio = 0; this.rapida = false; }
}

/**
 * Detecta que la están agitando: cuenta inversiones de sentido por eje entre muestras
 * con |v| > mareoVel (las lentas no cuentan ni rompen la racha). Con mareoInversiones
 * o más dentro de mareoVentana s → true (una vez; luego enfriamiento).
 */
export class DetectorMareo {
  constructor(p = PARAMS_FISICA) { this.p = p; this.enfriadoHasta = -Infinity; this.reiniciar(); }

  reiniciar() { this.signo = { x: 0, y: 0 }; this.inv = { x: [], y: [] }; }

  muestra(t, vx, vy) {
    const p = this.p;
    const ahora = num(t);
    let n = 0;
    for (const [eje, v] of [['x', vx], ['y', vy]]) {
      const lista = this.inv[eje];
      if (finito(v) && Math.abs(v) > p.mareoVel) {
        const s = Math.sign(v);
        if (this.signo[eje] !== 0 && s !== this.signo[eje]) lista.push(ahora);
        this.signo[eje] = s;
      }
      while (lista.length && ahora - lista[0] > p.mareoVentana) lista.shift();
      n = Math.max(n, lista.length);
    }
    if (n >= p.mareoInversiones && ahora >= this.enfriadoHasta) {
      this.enfriadoHasta = ahora + p.mareoEnfriamiento;
      this.reiniciar();
      return true;
    }
    return false;
  }
}

/**
 * Minirrebote del toque, s desde el toque → {y (px, − = arriba), sx, sy} o null al
 * acabar. Oscilación amortiguada: primero sube estirándose, luego aterriza aplastándose.
 */
export function reboteToque(t, p = PARAMS_FISICA) {
  const d = num(p.toqueDuracion, 0.7);
  if (!finito(t) || t < 0 || t >= d) return null;
  const a = Math.exp(-t * 7) * Math.sin(2 * Math.PI * t / 0.32) * (1 - t / d);
  return { y: -num(p.toqueAltura, 5) * a, sx: 1 - 0.015 * a, sy: 1 + 0.025 * a };
}

/** Bamboleo del mareo en grados (CSS), s desde que empezó; 0 al acabar. */
export function bamboleoMareo(t, p = PARAMS_FISICA) {
  const d = num(p.mareoDuracion, 2.5);
  if (!finito(t) || t < 0 || t >= d) return 0;
  return num(p.mareoAmplitud, 3) * Math.sin(2 * Math.PI * num(p.mareoFrec, 1.4) * t) * (1 - t / d);
}

// ── Módulo del registro ───────────────────────────────────────────────────────

function clase(el, nombre, on) {
  if (!el || !el.classList) return;
  if (on) el.classList.add(nombre); else el.classList.remove(nombre);
}

/** Claves de PARAMS_FISICA que se pueden cambiar en caliente (números y signo). */
const AJUSTABLES = new Set(Object.keys(PARAMS_FISICA).filter((k) => typeof PARAMS_FISICA[k] === 'number'));

/**
 * instalar(ctx) para crearRegistroAnim().registrar(). `opciones` solo para tests:
 * {params, documento}.
 */
export function instalar(ctx = {}, opciones = {}) {
  const p = { ...PARAMS_FISICA, ...(opciones.params || {}) };
  const stage = ctx.stage || null;
  const doc = opciones.documento || (stage && stage.ownerDocument) || globalThis.document || null;
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  const emitir = (tipo, datos) => {
    try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ }
  };

  let ahora = 0;                         // reloj del registro (s); lo avanza tick()
  const drag = { on: false, suelto: false, t0: 0, hasta: 0, tMuestra: 0, vx: 0, vy: 0, fvx: 0, fvy: 0, mvx: 0, mvy: 0 };
  const muelleA = new Muelle(p.frec, p.zeta, 45);
  const muelleE = new Muelle(p.frec, p.zeta, 0.2);
  const cara = new CaraArrastre(p);
  const detector = new DetectorMareo(p);
  let mareo = { t0: -Infinity, hasta: -Infinity };
  let toqueT = -Infinity;
  let dormida = false, sueno = 0;

  function dormir(on) {
    on = !!on;
    if (on === dormida) return false;
    dormida = on;
    const e = est();
    e.dormida = on;
    clase(stage, 'lune-dormida', on);
    if (on) {
      asegurarZzz(stage, doc);
      fijarCapa(e, 'dormir', 'sleeping');
      emitir('dormir', {});
    } else {
      quitarCapa(e, 'dormir');
      emitir('despertar', {});
    }
    return true;
  }

  function terminarArrastre() {
    drag.on = false; drag.suelto = false;
    drag.vx = 0; drag.vy = 0;
    cara.terminar();
    const e = est();
    e.drag = false;
    quitarCapa(e, 'arrastre');
    emitir('arrastre', { on: false });
  }

  function setDrag(on, vx, vy) {
    const e = est();
    if (on) {
      if (!drag.on) {
        drag.on = true; drag.t0 = ahora;
        e.drag = true;
        fijarCapa(e, 'arrastre', cara.iniciar(ahora));
        emitir('arrastre', { on: true });
        if (dormida) dormir(false);
      }
      drag.suelto = false;
      drag.hasta = ahora + p.dragMinimo;
      drag.vx = num(Number(vx)) * 1000;              // px/ms → px/s
      drag.vy = num(Number(vy)) * 1000;
      drag.tMuestra = ahora;
    } else if (drag.on) {
      drag.vx = 0; drag.vy = 0; drag.suelto = true;
      if (ahora >= drag.hasta) terminarArrastre();
    }
    return drag.on;
  }

  function tocar() {
    toqueT = ahora;
    if (dormida) dormir(false);
    return true;
  }

  function tick(dt, t) {
    const d = num(dt);
    ahora = finito(t) ? t : ahora + d;
    const e = est();

    if (drag.on) {
      if (ahora - drag.tMuestra > p.caducidad) { drag.vx = 0; drag.vy = 0; }   // ratón quieto
      if (drag.suelto && ahora >= drag.hasta) terminarArrastre();
    }
    const k = suav(d, p.filtro), km = suav(d, p.filtroMareo);
    drag.fvx += (drag.vx - drag.fvx) * k;
    drag.fvy += (drag.vy - drag.fvy) * k;
    drag.mvx += (drag.vx - drag.mvx) * km;
    drag.mvy += (drag.vy - drag.mvy) * km;
    if (!drag.on) { drag.vx = 0; drag.vy = 0; }

    muelleA.paso(drag.on ? anguloObjetivo(drag.fvx, p) : 0, d);
    muelleE.paso(drag.on ? estironObjetivo(drag.fvy, p) : 0, d);

    if (drag.on) {
      fijarCapa(e, 'arrastre', cara.actualizar(ahora, Math.hypot(drag.fvx, drag.fvy)));
      if (detector.muestra(ahora, drag.mvx, drag.mvy)) {
        mareo = { t0: ahora, hasta: ahora + p.mareoDuracion };
        emitir('mareo', {});
      }
    }
    if (ahora < mareo.hasta) fijarCapa(e, 'mareo', 'dizzy');
    else quitarCapa(e, 'mareo');

    sueno = clamp(sueno + (dormida ? 1 / p.dormirEntrada : -1 / p.dormirSalida) * d, 0, 1);
    e.drag = drag.on;
    e.dormida = dormida;
  }

  function pose(out) {
    const rot = clamp(anguloCSS(muelleA.x) + bamboleoMareo(ahora - mareo.t0, p), -p.maxAngulo, p.maxAngulo);
    if (Math.abs(rot) > 0.005) out.transform.push(rotarEn(rot, p.pivoteX, p.pivoteY));
    const s = muelleE.x;
    if (Math.abs(s) > 0.0002) out.transform.push(escalarEn([1 - s * 0.5, 1 + s], p.pivoteX, p.pivoteY));
    const r = reboteToque(ahora - toqueT, p);
    if (r) {
      out.transform.push(mover(0, r.y));
      out.transform.push(escalarEn([r.sx, r.sy], '50%', '100%'));
    }
    if (sueno > 0.001) {
      const resp = 1 + p.respiracion * sueno * Math.sin(2 * Math.PI * ahora / p.respiracionPeriodo);
      out.transform.push(escalarEn([1, resp], '50%', '100%'));
    }
  }

  function ocupado() {
    if (drag.on || reboteToque(ahora - toqueT, p) || ahora < mareo.hasta) return true;
    if (Math.abs(muelleA.x) > 0.02 || Math.abs(muelleA.v) > 0.05) return true;
    if (Math.abs(muelleE.x) > 0.0005 || Math.abs(muelleE.v) > 0.002) return true;
    return Math.abs(sueno - (dormida ? 1 : 0)) > 0.001;
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,

    alIniciar() { if (dormida) asegurarZzz(stage, doc); },

    // Igual que setEstado del VRM.
    alEmocion(nombre) {
      const n = String(nombre ?? '').trim() || 'normal';
      if (n === 'sleeping') dormir(true);
      else if (dormida && n !== 'normal') dormir(false);
    },

    tick, pose, ocupado,

    api: {
      drag: (on, vx, vy) => setDrag(!!on, vx, vy),
      tocar,
      dormir: (on) => dormir(!!on),
      estado: () => ({
        drag: drag.on, angulo: anguloCSS(muelleA.x), estiron: muelleE.x,
        cara: cara.cara, dormida, mareo: ahora < mareo.hasta,
      }),
      /** Object.assign con lista blanca (solo números de PARAMS_FISICA). */
      params(obj) {
        if (!obj || typeof obj !== 'object') return { ...p };
        for (const k of Object.keys(obj)) {
          const v = Number(obj[k]);
          if (AJUSTABLES.has(k) && finito(v)) p[k] = v;
        }
        muelleA.configurar(p.frec, p.zeta);
        muelleE.configurar(p.frec, p.zeta);
        return { ...p };
      },
    },
  };
}

/**
 * Publica en window las APIs que llama companion.py (mismas firmas que en
 * companion_vrm.html): luneDrag(on, vx, vy), luneTouch(), luneSleep(on).
 */
export function publicar(win = globalThis, reg) {
  if (!win || !reg) return;
  win.luneDrag = (on, vx, vy) => reg.api(NOMBRE, 'drag', !!on, vx, vy);
  win.luneTouch = () => reg.api(NOMBRE, 'tocar');
  win.luneSleep = (on) => reg.api(NOMBRE, 'dormir', !!on);
}
