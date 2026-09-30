/*
 * ui_web/anim/lune_anim_sentarse.js — módulo 'sentarseAnim' de la asistente ANIMADA:
 * «sentada» en el borde de una ventana o en la barra de tareas (corte 7, decisión D2).
 *
 * Los clips WebM no tienen pose sentada: la animada se APOYA de pie sobre el borde (la
 * ventana la pega y la mueve Python, ui/asiento_qt.ControlAsiento). Aquí solo:
 *   · la clase .lune-sentada en el #stage (ui_web/css/sentarse.css: sin borde inferior
 *     y una sombra fina, como si pisara el borde) y data-sentada = modo;
 *   · el punto de asiento: asiento = sonda = centro-abajo del #stage, en px de la página.
 * Mismas funciones de página que el VRM (ui_web/vrm/lune_sentarse.js):
 *   window.luneSentar('ventana'|'barra', variante) → JSON {asiento:{x,y}, sonda:{x,y}} ·
 *   window.luneSentar(null) → 'null' · window.luneSeatPx() → JSON.
 * El registro es el dueño de style.transform/filter/opacity del #stage: este módulo NO
 * escribe estilos (solo la clase y el atributo). est.sentada = modo | false.
 * Sin DOM real en los tests: tests/js/anim_sentarse.test.mjs (dom_falso.mjs).
 */
export const NOMBRE = 'sentarseAnim';
export const ORDEN = 85;
export const CLASE = 'lune-sentada';
export const MODOS = Object.freeze(['ventana', 'barra']);

const finito = Number.isFinite;
const redondeo = (v) => Math.round(v * 10) / 10;

/** 'ventana' | 'barra' o null. */
export function modoValido(modo) {
  const m = String(modo ?? '').trim().toLowerCase();
  return MODOS.includes(m) ? m : null;
}

/** {asiento:{x,y}, sonda:{x,y}}: el centro de abajo del #stage (px de la página), o null. */
export function puntos(stage) {
  try {
    if (!stage || typeof stage.getBoundingClientRect !== 'function') return null;
    const r = stage.getBoundingClientRect();
    const x = Number(r.left) + Number(r.width) / 2, y = Number(r.top) + Number(r.height);
    if (!finito(x) || !finito(y) || !(Number(r.width) > 0) || !(Number(r.height) > 0)) return null;
    const p = { x: redondeo(x), y: redondeo(y) };
    return { asiento: { ...p }, sonda: { ...p } };
  } catch (e) {
    return null;
  }
}

function clase(el, nombre, on) {
  try { if (el && el.classList) { if (on) el.classList.add(nombre); else el.classList.remove(nombre); } } catch (e) { /* elemento falso */ }
}

function atributo(el, nombre, valor) {
  try {
    if (!el) return;
    if (valor === null || valor === undefined) { if (typeof el.removeAttribute === 'function') el.removeAttribute(nombre); }
    else if (typeof el.setAttribute === 'function') el.setAttribute(nombre, String(valor));
  } catch (e) { /* elemento falso */ }
}

/** instalar(ctx) para crearRegistroAnim().registrar(). */
export function instalar(ctx = {}) {
  const stage = ctx.stage || null;
  const local = {};
  const est = () => (typeof ctx.estado === 'function' && ctx.estado()) || local;
  const emitir = (tipo, datos) => { try { if (typeof ctx.emitir === 'function') ctx.emitir(tipo, datos); } catch (e) { /* sin canal */ } };
  let modo = '', variante = 0;

  function sentar(m, v) {
    const mm = modoValido(m);
    if (!mm) { levantar(); return null; }
    const vv = mm === 'barra' ? 0 : Math.max(0, Math.min(3, Math.floor(Number(v)) || 0));
    const cambio = mm !== modo || vv !== variante;
    modo = mm; variante = vv;
    clase(stage, CLASE, true);
    atributo(stage, 'data-sentada', mm);
    est().sentada = mm;
    if (cambio) emitir('sentada', { modo: mm, variante: vv });
    return puntos(stage);
  }

  function levantar() {
    const habia = !!modo;
    modo = ''; variante = 0;
    clase(stage, CLASE, false);
    atributo(stage, 'data-sentada', null);
    est().sentada = false;
    if (habia) emitir('sentada', { modo: '', variante: 0 });
    return habia;
  }

  return {
    nombre: NOMBRE,
    orden: ORDEN,
    api: {
      sentar: (m, v) => sentar(m, v),
      levantar: () => levantar(),
      puntos: () => puntos(stage),
      estado: () => ({ sentada: modo, variante }),
    },
  };
}
