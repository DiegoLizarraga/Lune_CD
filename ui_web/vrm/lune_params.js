/*
 * ui_web/vrm/lune_params.js — Lista blanca y rangos de window.luneParams (P14, «Custom VRM»).
 *
 * Python manda a la mascota 3D la calibración del modelo (modelo_vrm/<modelo>.lune.json,
 * ver nucleo/vrm.py → params_modelo) y los pesos de seguimiento. Aquí se decide qué
 * claves de PARAMS se pueden tocar desde fuera y en qué rango: todo lo demás se ignora
 * (ni claves nuevas, ni __proto__, ni NaN/Infinity, ni textos raros).
 *
 * Tipos:
 *   'signo'  → 1 (tal cual) o -1 (invertir). true = -1, false = 1, un número = su signo.
 *   'opcion' → uno de `valores` (invertirEjes: 0 = automático, 1 = tal cual, -1 = invertir X/Z).
 *              'auto' = 0. Un número se redondea (Math.round) y se recorta a los valores.
 *   'real'   → número recortado a [min, max] (4 decimales).
 *   'entero' → número redondeado y recortado a [min, max].
 * Los números pueden venir como texto ("0,5" también vale), igual que en nucleo/vrm.py.
 *
 * Las 10 claves de CLAVES_MODELO tienen EXACTAMENTE los mismos rangos que
 * nucleo/vrm.py → AJUSTES (lo comprueba tests/test_vrm_ajustes.py con Node).
 *
 * API:
 *   validarValor(clave, v)          → número válido | null
 *   validarParams(json)             → {clave: valor} solo con lo válido (acepta objeto o texto JSON)
 *   aplicarParams(PARAMS, json)     → {aplicados, cambiadas: [claves cuyo valor cambió]}
 *   crearLuneParams(PARAMS, alCambiar?) → fn(json) para window.luneParams; devuelve el JSON
 *                                     de lo aplicado y llama alCambiar(cambiadas, PARAMS) si hubo cambios
 *   defectos(claves = CLAVES_MODELO) → {clave: defecto}
 *   ejesDe(invertirEjes, xAntebrazoIzq, metaVersion) → sXZ (±1): lo que hace lune_vrm.js al cargar,
 *                                     en puro, para recalcularlo cuando cambia invertirEjes
 *
 * Sin imports: se carga igual en el navegador (import desde companion_vrm.html) que en
 * Node (tests/js/params.test.mjs).
 */

export const RANGOS = Object.freeze({
  // ── Calibración por modelo (nucleo/vrm.py AJUSTES) ──────────────────────────
  invertirEjes:    { tipo: 'opcion', valores: [-1, 0, 1], defecto: 0 },
  invertirH:       { tipo: 'signo', defecto: 1 },          // balanceo horizontal al arrastrar
  invertirV:       { tipo: 'signo', defecto: 1 },          // balanceo vertical
  invertirBrazos:  { tipo: 'signo', defecto: 1 },          // brazos con retraso (módulo movimiento)
  invertirPiernas: { tipo: 'signo', defecto: 1 },          // piernas con retraso
  luz:             { tipo: 'real', min: 0.2, max: 3.0, defecto: 1.0 },   // × intensidad de las luces
  altura:          { tipo: 'real', min: -0.5, max: 0.5, defecto: 0.0 },  // m: sube/baja el modelo
  pesoCabeza:      { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },   // seguimiento del cursor
  pesoTorso:       { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },
  pesoOjos:        { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },
  // ── Solo en caliente (no se guardan por modelo) ─────────────────────────────
  fpsActivo:       { tipo: 'entero', min: 15, max: 144, defecto: 60 },
  // Balanceo al arrastrar (AvatarSwayController de Mate-Engine, valores de su escena;
  // lo aplica ui_web/vrm/lune_movimiento.js): ganancia °/(px/s), topes en °, muelle
  // (Hz, ζ), filtro de la velocidad y fundidos (1/s). Mismos defectos que PARAMS de
  // lune_vrm.js y PARAMS_SWAY de lune_movimiento.js (tests/js/integracion_vrm.test.mjs).
  swayGanH:        { tipo: 'real', min: 0.0, max: 0.05, defecto: 0.0167 },
  swayGanV:        { tipo: 'real', min: 0.0, max: 0.05, defecto: 0.0167 },
  swayMaxZ:        { tipo: 'real', min: 0.0, max: 60.0, defecto: 45 },
  swayMaxX:        { tipo: 'real', min: 0.0, max: 40.0, defecto: 20 },
  swayFrec:        { tipo: 'real', min: 0.1, max: 8.0, defecto: 0.75 },
  swayZeta:        { tipo: 'real', min: 0.05, max: 2.0, defecto: 0.5 },
  swayFiltro:      { tipo: 'real', min: 1.0, max: 60.0, defecto: 12 },
  swayEntrada:     { tipo: 'real', min: 0.5, max: 30.0, defecto: 8 },
  swaySalida:      { tipo: 'real', min: 0.5, max: 30.0, defecto: 3 },
});

/** Las que se guardan por modelo en modelo_vrm/<modelo>.lune.json (mismo orden que AJUSTES). */
export const CLAVES_MODELO = Object.freeze([
  'invertirEjes', 'invertirH', 'invertirV', 'invertirBrazos', 'invertirPiernas',
  'luz', 'altura', 'pesoCabeza', 'pesoTorso', 'pesoOjos',
]);

/** Las de seguimiento del cursor (cabeza, torso, ojos). */
export const CLAVES_SEGUIMIENTO = Object.freeze(['pesoCabeza', 'pesoTorso', 'pesoOjos']);

const MAX_TEXTO_JSON = 64 * 1024;          // un luneParams no necesita más
const tiene = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

function numero(v) {
  if (typeof v === 'boolean' || v === null || v === undefined) return null;
  let x;
  if (typeof v === 'number') x = v;
  else if (typeof v === 'string') {
    const s = v.trim().replace(',', '.');
    if (!s || !/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(s)) return null;
    x = Number(s);
  } else return null;
  return Number.isFinite(x) ? x : null;
}

const redondear4 = (x) => Math.round(x * 1e4) / 1e4;

/** El valor de `clave` dentro de su rango, o null si la clave no existe o el valor no vale. */
export function validarValor(clave, v) {
  if (typeof clave !== 'string' || !tiene(RANGOS, clave)) return null;
  const r = RANGOS[clave];
  if (r.tipo === 'signo') {
    if (typeof v === 'boolean') return v ? -1 : 1;
    const x = numero(v);
    return x === null ? null : (x < 0 ? -1 : 1);
  }
  if (r.tipo === 'opcion') {
    if (typeof v === 'string' && ['auto', 'automatico', 'automático'].includes(v.trim().toLowerCase())) return 0;
    const x = numero(v);
    if (x === null) return null;
    const n = Math.round(x);
    const lo = Math.min(...r.valores), hi = Math.max(...r.valores);
    return Math.max(lo, Math.min(hi, n)) || 0;              // || 0: nunca -0
  }
  const x = numero(v);
  if (x === null) return null;
  const c = Math.min(r.max, Math.max(r.min, x));
  return r.tipo === 'entero' ? Math.round(c) : (redondear4(c) || 0);
}

/** Objeto (o texto JSON) → solo las claves de RANGOS con valor válido, en el orden de RANGOS. */
export function validarParams(json) {
  let o = json;
  if (typeof o === 'string') {
    if (o.length > MAX_TEXTO_JSON) return {};
    try { o = JSON.parse(o); } catch (_) { return {}; }
  }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return {};
  const out = {};
  for (const k of Object.keys(RANGOS)) {
    if (!tiene(o, k)) continue;
    const v = validarValor(k, o[k]);
    if (v !== null) out[k] = v;
  }
  return out;
}

/** Aplica lo válido sobre PARAMS (Object.assign con lista blanca). */
export function aplicarParams(PARAMS, json) {
  const aplicados = validarParams(json);
  const cambiadas = [];
  if (!PARAMS || typeof PARAMS !== 'object') return { aplicados, cambiadas };
  for (const k of Object.keys(aplicados)) {
    if (PARAMS[k] !== aplicados[k]) cambiadas.push(k);
    PARAMS[k] = aplicados[k];
  }
  return { aplicados, cambiadas };
}

/**
 * La función de window.luneParams: `window.luneParams = crearLuneParams(mascota.PARAMS,
 * (cambiadas) => …)`. Devuelve JSON de lo aplicado (lo que Python puede leer en el callback
 * de runJavaScript). Un alCambiar que lanza no rompe la llamada.
 */
export function crearLuneParams(PARAMS, alCambiar) {
  return function luneParams(json) {
    const { aplicados, cambiadas } = aplicarParams(PARAMS, json);
    if (cambiadas.length && typeof alCambiar === 'function') {
      try { alCambiar(cambiadas, PARAMS); } catch (e) { try { console.warn('luneParams', e); } catch (_) {} }
    }
    return JSON.stringify(aplicados);
  };
}

/** {clave: defecto} de las claves pedidas (por defecto, las del modelo). */
export function defectos(claves = CLAVES_MODELO) {
  const out = {};
  for (const k of claves) if (tiene(RANGOS, k)) out[k] = RANGOS[k].defecto;
  return out;
}

/**
 * Signo de las rotaciones X/Z según el rig, como lune_vrm.js al cargar:
 *   invertirEjes ±1 → ese valor; 0 (auto) → se mide el antebrazo izquierdo (x < 0 → -1)
 *   y, si no se puede medir, los VRM 0.x van invertidos (-1) y los 1.0 no (1).
 */
export function ejesDe(invertirEjes, xAntebrazoIzq, metaVersion) {
  const inv = validarValor('invertirEjes', invertirEjes) ?? 0;
  if (inv === 1 || inv === -1) return inv;
  if (Number.isFinite(xAntebrazoIzq) && Math.abs(xAntebrazoIzq) > 1e-4) return xAntebrazoIzq < 0 ? -1 : 1;
  return String(metaVersion) === '0' ? -1 : 1;
}
