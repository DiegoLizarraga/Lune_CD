/* Lune CD desktop — Biblioteca de modelos 3D (VRM): «Custom VRM» y seguimiento de Mate-Engine.
 *
 * VrmBiblioteca({cfg, set}):
 *   · Rejilla de los .vrm de modelo_vrm/ con la miniatura que trae cada modelo, nombre, versión y
 *     quién lo usa (personaje activo, modelo por defecto).
 *   · Importar .vrm…, borrar (con confirmación en dos pasos) y usar/quitar con el personaje activo.
 *   · Ficha del modelo elegido (autor, licencia, triángulos, expresiones) y calibración EN VIVO:
 *     ejes (auto · tal cual · invertir X/Z), balanceo H/V, brazos y piernas invertidos, luz, altura.
 *   · Seguimiento del cursor por modelo: cabeza, torso y ojos (0–100 %). Si el modelo no trae
 *     lookAt, aviso «Este modelo no mueve los ojos» y el deslizador de ojos queda en gris.
 *   · Con `cfg`/`set` de SettingsPanel (opcionales) enseña además el interruptor global
 *     «Seguir el cursor» (clave plana seguir_cursor = avatar.seguir_cursor).
 *
 * Los rangos son los de nucleo/vrm.py AJUSTES y ui_web/vrm/lune_params.js (tests/test_vrm_biblioteca.py
 * comprueba que coinciden). Los cambios de calibración se mandan agrupados (150 ms) a
 * window.lune.vrm_ajustes; el backend los guarda en modelo_vrm/<modelo>.lune.json y, si la asistente
 * 3D enseña ese modelo, se los pasa con window.luneParams.
 *
 * Puente (QWebChannel, todo opcional; sin window.lune hay una demo local que no guarda nada):
 *   window.lune.vrm_biblioteca(cb)              → JSON de nucleo.vrm.biblioteca(config):
 *        {webengine, carpeta, activo, activo_vrm, por_defecto, modelos:[ficha sin efectivos]}
 *   window.lune.vrm_modelos(cb)                 → JSON {webengine, modelos:[archivo], carpeta}
 *                                                 (respaldo si no existe vrm_biblioteca)
 *   window.lune.personajes_lista(cb)            → JSON [{nombre, activo, vrm}] (respaldo)
 *   window.lune.vrm_meta(nombre, cb)            → JSON de nucleo.vrm.ficha(nombre, config):
 *        {ok, archivo, version, nombre, autor, mb, licencia, licencia_url, triangulos, tieneLookAt,
 *         lookAt, miniatura, expresiones, ajustes, efectivos, personajes, por_defecto}
 *   window.lune.vrm_miniatura(nombre, cb)       → "data:image/png;base64,…" (o jpeg) · "" si no trae
 *   window.lune.vrm_ajustes(nombre, json, cb)   → JSON {ok, archivo, ajustes, efectivos} | {ok:false, error}
 *                                                 json = {clave: valor | null}; null = volver al defecto
 *   window.lune.vrm_borrar(nombre, cb)          → JSON {ok, archivo, personajes, por_defecto, modelos} | {ok:false, error}
 *   window.lune.vrm_importar(cb)                → JSON {ok, archivo, modelos} | {ok:false, cancelado | error}
 *   window.lune.personaje_vrm(nombre, archivo, cb) → JSON {ok} | {ok:false, error}  (archivo "" = quitar)
 *
 * Se registra solo: Object.assign(window, {VrmBiblioteca, LuneVrm}). Va dentro de una IIFE para no
 * pisar los const de nivel superior de otros .jsx (Babel preset env los convierte en var globales).
 */
(function () {
  const { useState, useEffect, useMemo, useRef } = React;

  // ── Rangos (idénticos a nucleo/vrm.py AJUSTES y a lune_params.js) ──────────
  const RANGOS = {
    invertirEjes:    { tipo: 'opcion', valores: [-1, 0, 1], defecto: 0 },
    invertirH:       { tipo: 'signo', defecto: 1 },
    invertirV:       { tipo: 'signo', defecto: 1 },
    invertirBrazos:  { tipo: 'signo', defecto: 1 },
    invertirPiernas: { tipo: 'signo', defecto: 1 },
    luz:             { tipo: 'real', min: 0.2, max: 3.0, defecto: 1.0 },
    altura:          { tipo: 'real', min: -0.5, max: 0.5, defecto: 0.0 },
    pesoCabeza:      { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },
    pesoTorso:       { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },
    pesoOjos:        { tipo: 'real', min: 0.0, max: 1.0, defecto: 1.0 },
  };
  const CLAVES = Object.keys(RANGOS);
  const DEFECTOS = CLAVES.reduce((o, k) => { o[k] = RANGOS[k].defecto; return o; }, {});
  const EJES = [[0, 'Automático', 'Lune mide el brazo al cargar y decide'], [1, 'Tal cual', 'Ejes del modelo sin tocar'],
    [-1, 'Invertir X/Z', 'Para rigs girados: brazos en V o cabeza al revés']];
  const SIGNOS = [
    ['invertirH', 'Balanceo horizontal al revés', 'Si al arrastrarla de lado se inclina hacia donde no toca.'],
    ['invertirV', 'Balanceo vertical al revés', 'Si al subirla o bajarla cabecea al revés.'],
    ['invertirBrazos', 'Brazos al revés al arrastrar', 'Los brazos se quedan atrás con retraso; esto invierte el sentido.'],
    ['invertirPiernas', 'Piernas al revés al arrastrar', 'Igual que los brazos, para las piernas.'],
  ];
  const ESPERA_ENVIO = 150;          // ms: agrupa los cambios de un deslizador antes de mandarlos
  const tiene = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

  // ── Utilidades puras (window.LuneVrm, las usa tests/test_vrm_biblioteca.py) ──
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

  /** Valor de un ajuste dentro de su rango, o null (misma regla que lune_params.validarValor). */
  function validarValor(clave, v) {
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
      return Math.max(-1, Math.min(1, Math.round(x))) || 0;
    }
    const x = numero(v);
    if (x === null) return null;
    return (Math.round(Math.min(r.max, Math.max(r.min, x)) * 1e4) / 1e4) || 0;
  }

  function parsear(r) {
    if (typeof r !== 'string') return r;
    try { return JSON.parse(r); } catch (e) { return null; }
  }
  const esObj = (o) => !!o && typeof o === 'object' && !Array.isArray(o);
  const texto = (v, max) => (v == null || typeof v === 'object' ? '' : String(v)).slice(0, max || 120);
  // Mismo criterio que nucleo/vrm._nombre_seguro: nombre de archivo .vrm sin carpetas.
  const archivoValido = (a) => typeof a === 'string' && /\.vrm$/i.test(a) && a.length > 4 && a.length <= 200
    && !/[\\/:*?"<>|\u0000-\u001f]/.test(a) && a !== '..';

  /** Solo data URL de PNG/JPEG en base64: nada de http, javascript: ni SVG en <img src>. */
  function urlMiniatura(s) {
    const u = typeof s === 'string' ? s.trim() : '';
    return /^data:image\/(png|jpeg);base64,[A-Za-z0-9+/]+={0,2}$/.test(u) ? u : '';
  }

  /** Respuesta de vrm_meta (o una ficha de vrm_biblioteca) → ficha con tipos seguros. */
  function normalizarFicha(resp) {
    const o = parsear(resp);
    if (!esObj(o)) return null;
    const archivo = texto(o.archivo, 200);
    const ajustes = {};
    if (esObj(o.ajustes)) CLAVES.forEach((k) => { const v = validarValor(k, o.ajustes[k]); if (v !== null && tiene(o.ajustes, k)) ajustes[k] = v; });
    let efectivos = null;
    if (esObj(o.efectivos)) {
      efectivos = { ...DEFECTOS };
      CLAVES.forEach((k) => { if (tiene(o.efectivos, k)) { const v = validarValor(k, o.efectivos[k]); if (v !== null) efectivos[k] = v; } });
    }
    const mb = Number(o.mb);
    const tris = Number(o.triangulos);
    return {
      ok: o.ok !== false, motivo: texto(o.motivo, 300), archivo,
      version: o.version === '0' || o.version === '1' ? o.version : '',
      nombre: texto(o.nombre), autor: texto(o.autor), mb: Number.isFinite(mb) && mb >= 0 ? mb : 0,
      licencia: texto(o.licencia, 200), licencia_url: texto(o.licencia_url, 300),
      triangulos: Number.isFinite(tris) && tris > 0 ? Math.round(tris) : 0,
      // Sin dato no se asume nada: solo false explícito enciende el aviso de los ojos.
      tieneLookAt: o.tieneLookAt === false ? false : (o.tieneLookAt === true ? true : null),
      lookAt: o.lookAt === 'hueso' || o.lookAt === 'expresion' ? o.lookAt : '',
      miniatura: o.miniatura !== false,
      expresiones: Array.isArray(o.expresiones) ? o.expresiones.map((e) => texto(e, 40)).filter(Boolean).slice(0, 64) : [],
      ajustes, efectivos,
      personajes: Array.isArray(o.personajes) ? o.personajes.map((p) => texto(p, 60)).filter(Boolean) : [],
      por_defecto: o.por_defecto === true,
    };
  }

  /** Valores de los deslizadores: efectivos si vienen; si no, defectos + lo guardado del modelo. */
  function efectivosDe(ficha) {
    if (!ficha) return { ...DEFECTOS };
    if (ficha.efectivos) return { ...DEFECTOS, ...ficha.efectivos };
    return { ...DEFECTOS, ...(ficha.ajustes || {}) };
  }

  /** Respuesta de vrm_biblioteca, o de vrm_modelos + personajes_lista → biblioteca normalizada. */
  function normalizarBiblioteca(resp, personajes) {
    const o = parsear(resp);
    const out = { webengine: true, carpeta: '', activo: '', activo_vrm: '', por_defecto: '', modelos: [] };
    if (Array.isArray(o)) o.forEach((a) => { if (archivoValido(a)) out.modelos.push({ ...normalizarFicha({ archivo: a }), soloNombre: true }); });
    else if (esObj(o)) {
      out.webengine = o.webengine !== false;
      out.carpeta = texto(o.carpeta, 400);
      out.activo = texto(o.activo);
      out.activo_vrm = texto(o.activo_vrm, 400);
      out.por_defecto = texto(o.por_defecto, 400);
      (Array.isArray(o.modelos) ? o.modelos : []).forEach((m) => {
        if (typeof m === 'string') { if (archivoValido(m)) out.modelos.push({ ...normalizarFicha({ archivo: m }), soloNombre: true }); return; }
        const f = normalizarFicha(m);
        if (f && archivoValido(f.archivo)) out.modelos.push(f);
      });
    }
    // Respaldo: personajes_lista → personaje activo y su modelo
    const pl = parsear(personajes);
    if (Array.isArray(pl) && !out.activo) {
      const act = pl.find((p) => esObj(p) && p.activo);
      if (act) { out.activo = texto(act.nombre); out.activo_vrm = texto(act.vrm, 400); }
    }
    const vistos = new Set();
    out.modelos = out.modelos.filter((m) => { const k = m.archivo.toLowerCase(); if (vistos.has(k)) return false; vistos.add(k); return true; });
    // activo_vrm puede ser una ruta absoluta: para la rejilla cuenta el nombre de archivo
    out.activo_vrm = nombreDe(out.activo_vrm);
    out.por_defecto = nombreDe(out.por_defecto);
    return out;
  }
  const nombreDe = (ruta) => String(ruta || '').split(/[\\/]/).pop();

  /** Qué modelo enseñar: el actual si sigue, el del personaje activo, el por defecto o el primero. */
  function elegirModelo(bib, actual) {
    const hay = (a) => a && bib.modelos.some((m) => m.archivo.toLowerCase() === String(a).toLowerCase());
    const buscar = (a) => bib.modelos.find((m) => m.archivo.toLowerCase() === String(a).toLowerCase()).archivo;
    if (hay(actual)) return buscar(actual);
    if (hay(bib.activo_vrm)) return buscar(bib.activo_vrm);
    if (hay(bib.por_defecto)) return buscar(bib.por_defecto);
    return bib.modelos.length ? bib.modelos[0].archivo : '';
  }

  function iniciales(f) {
    const base = (f.nombre || f.archivo.replace(/\.vrm$/i, '')).replace(/[_\-.]+/g, ' ').trim();
    const partes = base.split(/\s+/).filter(Boolean);
    return ((partes[0] || '?')[0] + (partes[1] ? partes[1][0] : '')).toUpperCase();
  }
  const etiqueta = (f) => f.nombre || f.archivo.replace(/\.vrm$/i, '');
  const fmtPct = (v) => `${Math.round(v * 100)} %`;
  const fmtLuz = (v) => `×${Number(v).toFixed(2)}`;
  const fmtAltura = (v) => `${v > 0 ? '+' : ''}${Number(v).toFixed(2)} m`;
  function fmtMiles(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }

  /** Línea técnica: «VRM 1.0 · 12.3 MB · 35 000 triángulos · 18 expresiones». */
  function describir(f) {
    if (!f) return '';
    const p = [];
    if (f.version) p.push(f.version === '1' ? 'VRM 1.0' : 'VRM 0.x');
    if (f.mb) p.push(`${f.mb} MB`);
    if (f.triangulos) p.push(`${fmtMiles(f.triangulos)} triángulos`);
    if (f.expresiones.length) p.push(`${f.expresiones.length} expresiones`);
    return p.join(' · ');
  }

  /** Respuesta de vrm_ajustes/vrm_borrar/vrm_importar/personaje_vrm → {ok, error, cancelado, ...}. */
  function resultado(r) {
    const o = parsear(r);
    if (o === true) return { ok: true };
    if (!esObj(o)) return { ok: false, error: 'El backend no respondió.' };
    return { ...o, ok: o.ok === true, error: texto(o.error, 300) };
  }

  // Demo sin backend (navegador suelto): dos modelos sin miniatura.
  const DEMO = {
    webengine: true, carpeta: 'modelo_vrm/', activo: 'Lune', activo_vrm: 'lune_demo.vrm', por_defecto: '',
    modelos: [
      normalizarFicha({ archivo: 'lune_demo.vrm', nombre: 'Lune (demo)', autor: 'Lune CD', version: '1', mb: 14.2,
        triangulos: 42000, tieneLookAt: true, lookAt: 'hueso', miniatura: false, personajes: ['Lune'],
        expresiones: ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'aa', 'blink'] }),
      normalizarFicha({ archivo: 'vieja_demo.vrm', nombre: 'Vieja (demo)', autor: 'Alguien', version: '0', mb: 9.8,
        triangulos: 28000, tieneLookAt: false, miniatura: false, licencia: 'CC BY-NC · sin uso comercial' }),
    ],
  };

  // ── Estilos propios (index.html no se toca) ────────────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-x-vrm-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-x-vrm-css';
      st.textContent = `
        .ln-vrm-grid{ display:grid; grid-template-columns:repeat(auto-fill, minmax(128px, 1fr)); gap:10px; margin:4px 0 2px; }
        .ln-vrm-tile{ appearance:none; -webkit-appearance:none; display:flex; flex-direction:column; gap:6px; min-width:0;
          padding:8px; background:var(--surface-2); border:var(--bw, 2px) solid var(--border); color:var(--text);
          text-align:left; cursor:pointer; clip-path:var(--clip-notch, none); font:inherit;
          transition:border-color var(--dur-fast, .12s), background var(--dur-fast, .12s); }
        .ln-vrm-tile:hover{ border-color:var(--border-bright); background:var(--surface-3); }
        .ln-vrm-tile:focus-visible{ outline:2px solid var(--cyan-400); outline-offset:2px; }
        .ln-vrm-tile.is-sel{ border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm, none); }
        .ln-vrm-thumb{ position:relative; aspect-ratio:1/1; width:100%; overflow:hidden; display:flex; align-items:center;
          justify-content:center; background:var(--ink-950);
          background-image:linear-gradient(135deg, rgb(var(--cyan-500-rgb) / .10), rgb(var(--blue-500-rgb) / .14)); }
        .ln-vrm-thumb img{ width:100%; height:100%; object-fit:cover; display:block; }
        .ln-vrm-ini{ font-family:var(--font-display); font-size:30px; font-weight:700; letter-spacing:2px; color:var(--cyan-300); opacity:.8; }
        .ln-vrm-ver{ position:absolute; top:4px; left:4px; font-family:var(--font-mono); font-size:10px; padding:1px 5px;
          background:rgb(var(--ink-950-rgb) / .8); color:var(--text-muted); }
        .ln-vrm-name{ font-weight:600; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .ln-vrm-sub{ font-family:var(--font-mono); font-size:10.5px; color:var(--text-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .ln-vrm-tags{ display:flex; flex-wrap:wrap; gap:4px; min-height:0; }
        .ln-vrm-tags .lune-badge{ font-size:9.5px; }
        .ln-vrm-ficha{ display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:0 0 12px; font-size:12.5px; }
        .ln-vrm-ficha dt{ font-family:var(--font-mono); color:var(--text-dim); font-size:11px; padding-top:1px; }
        .ln-vrm-ficha dd{ margin:0; color:var(--text-muted); min-width:0; overflow-wrap:anywhere; }
        .ln-vrm-sec{ margin:16px 0 8px; }
        .ln-vrm-checks{ display:grid; grid-template-columns:1fr 1fr; gap:8px 14px; margin:10px 0 4px; }
        .ln-vrm-aviso{ margin:8px 0 0; padding:8px 10px; font-size:12px; color:var(--yellow-400);
          border-left:3px solid var(--yellow-500); background:rgb(var(--yellow-500-rgb) / .07); }
        .ln-vrm-peligro{ margin-top:12px; padding:10px 12px; border:1px solid var(--danger); background:rgb(255 59 92 / .07); }
        .ln-vrm-peligro p{ margin:0 0 10px; font-size:12.5px; color:var(--text); }
        .ln-x-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-x-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-x-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-x-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-x-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-x-estado{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-x-estado.is-error{ color:var(--yellow-500); }
        @media (max-width: 560px){ .ln-vrm-checks{ grid-template-columns:1fr; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  function Deslizador({ id, label, min, max, step, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-x-range">
        <div className="ln-x-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-x-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }

  const puede = (m) => !!(window.lune && typeof window.lune[m] === 'function');

  // ── VrmBiblioteca ──────────────────────────────────────────────────────────
  function VrmBiblioteca({ cfg, set }) {
    const { Card, Button, Badge, Switch } = window.LUNE;
    const conPuente = !!window.lune;
    const [bib, setBib] = useState(() => (conPuente ? normalizarBiblioteca(null) : DEMO));
    const [cargando, setCargando] = useState(conPuente);
    const [sel, setSel] = useState('');
    const [fichas, setFichas] = useState({});       // archivo → ficha completa (vrm_meta)
    const [minis, setMinis] = useState({});         // archivo → data URL ('' = no trae)
    const [valores, setValores] = useState(() => ({ ...DEFECTOS }));
    const [msg, setMsg] = useState({ texto: '', error: false });
    const [confirmar, setConfirmar] = useState('');
    const [ocupado, setOcupado] = useState(false);
    const vivo = useRef(true);
    const cola = useRef({ nombre: '', cambios: {}, t: null });
    const pedidas = useRef(new Set());              // miniaturas ya pedidas
    const selActual = useRef('');                   // para callbacks que llegan tarde
    selActual.current = sel;

    const aviso = (t, error) => { if (vivo.current) setMsg({ texto: t || '', error: !!error }); };

    // ── Envío agrupado de la calibración ────────────────────────────────────
    function vaciarCola() {
      const c = cola.current;
      if (c.t) { clearTimeout(c.t); c.t = null; }
      const nombre = c.nombre, cambios = c.cambios;
      c.cambios = {};
      if (!nombre || !Object.keys(cambios).length || !puede('vrm_ajustes')) return;
      try {
        window.lune.vrm_ajustes(nombre, JSON.stringify(cambios), (r) => {
          const res = resultado(r);
          if (!vivo.current) return;
          if (!res.ok) { aviso(`No pude guardar la calibración: ${res.error || 'error desconocido'}`, true); return; }
          const aj = normalizarFicha({ archivo: nombre, ajustes: res.ajustes }).ajustes;
          setFichas((fs) => (fs[nombre] ? { ...fs, [nombre]: { ...fs[nombre], ajustes: aj } } : fs));
        });
      } catch (e) { aviso('No pude mandar la calibración al backend.', true); }
    }

    function cambiar(clave, v) {
      const val = validarValor(clave, v);
      if (val === null || !sel) return;
      setValores((vs) => ({ ...vs, [clave]: val }));
      if (!conPuente) { aviso('Demo · sin backend: la calibración no se guarda.'); return; }
      const c = cola.current;
      if (c.nombre && c.nombre !== sel) vaciarCola();
      c.nombre = sel;
      c.cambios[clave] = val;
      if (!c.t) c.t = setTimeout(() => { c.t = null; vaciarCola(); }, ESPERA_ENVIO);
    }

    function restablecer() {
      if (!sel) return;
      vaciarCola();
      if (!conPuente) { setValores({ ...DEFECTOS }); return; }
      if (!puede('vrm_ajustes')) return;
      const nulos = CLAVES.reduce((o, k) => { o[k] = null; return o; }, {});
      const nombre = sel;
      try {
        window.lune.vrm_ajustes(nombre, JSON.stringify(nulos), (r) => {
          const res = resultado(r);
          if (!vivo.current) return;
          if (!res.ok) { aviso(`No pude restablecer: ${res.error}`, true); return; }
          const f = normalizarFicha({ archivo: nombre, ajustes: res.ajustes, efectivos: res.efectivos });
          setFichas((fs) => (fs[nombre] ? { ...fs, [nombre]: { ...fs[nombre], ajustes: f.ajustes, efectivos: f.efectivos } } : fs));
          setValores(efectivosDe(f));
          aviso('Calibración restablecida: vuelve a los valores por defecto (y a los pesos globales de seguimiento).');
        });
      } catch (e) { aviso('No pude restablecer la calibración.', true); }
    }

    // ── Carga ───────────────────────────────────────────────────────────────
    function aplicarBiblioteca(b) {
      if (!vivo.current) return;
      setBib(b);
      setCargando(false);
      setSel((s) => elegirModelo(b, s));
    }

    function cargar() {
      if (!conPuente) return;
      setCargando(true);
      try {
        if (puede('vrm_biblioteca')) {
          window.lune.vrm_biblioteca((j) => aplicarBiblioteca(normalizarBiblioteca(j)));
        } else if (puede('vrm_modelos')) {
          window.lune.vrm_modelos((j) => {
            const o = parsear(j);
            const lista = esObj(o) ? { webengine: o.webengine, carpeta: o.carpeta, modelos: o.modelos || [] } : { modelos: [] };
            if (puede('personajes_lista')) window.lune.personajes_lista((pl) => aplicarBiblioteca(normalizarBiblioteca(lista, pl)));
            else aplicarBiblioteca(normalizarBiblioteca(lista));
          });
        } else setCargando(false);
      } catch (e) { setCargando(false); aviso('No pude leer la biblioteca de modelos.', true); }
    }

    useEffect(() => {
      inyectarEstilos();
      vivo.current = true;
      if (conPuente) cargar(); else setSel(elegirModelo(DEMO, ''));
      return () => { vaciarCola(); vivo.current = false; };
    }, []);

    // Miniaturas: una petición por modelo (el backend las cachea por mtime)
    useEffect(() => {
      if (!puede('vrm_miniatura')) return;
      bib.modelos.forEach((m) => {
        if (m.miniatura === false || pedidas.current.has(m.archivo)) return;
        pedidas.current.add(m.archivo);
        try {
          window.lune.vrm_miniatura(m.archivo, (u) => {
            if (vivo.current) setMinis((ms) => ({ ...ms, [m.archivo]: urlMiniatura(u) }));
          });
        } catch (e) { /* sin miniatura */ }
      });
    }, [bib]);

    // Ficha completa del elegido (con efectivos) y sus valores en los deslizadores
    useEffect(() => {
      setConfirmar('');
      if (!sel) return;
      const deBib = bib.modelos.find((m) => m.archivo === sel) || null;
      if (!conPuente) { setValores(efectivosDe(deBib)); return; }
      setValores(efectivosDe(fichas[sel] || deBib));
      if (!puede('vrm_meta')) return;
      const nombre = sel;
      try {
        window.lune.vrm_meta(nombre, (j) => {
          const f = normalizarFicha(j);
          if (!vivo.current || !f) return;
          setFichas((fs) => ({ ...fs, [nombre]: f }));
          // Solo si sigue elegido y no hay cambios a medio mandar de este modelo
          if (cola.current.nombre === nombre && Object.keys(cola.current.cambios).length) return;
          if (selActual.current === nombre) setValores(efectivosDe(f));
        });
      } catch (e) { /* se queda con lo de la rejilla */ }
    }, [sel]);

    // ── Acciones ────────────────────────────────────────────────────────────
    const importar = () => {
      if (!puede('vrm_importar')) { aviso(`Demo · sin backend: copia el .vrm a la carpeta ${carpeta}.`); return; }
      setOcupado(true);
      try {
        window.lune.vrm_importar((j) => {
          const r = resultado(j);
          if (!vivo.current) return;
          setOcupado(false);
          if (r.ok) {
            aviso(`Modelo «${texto(r.archivo, 200)}» importado.`);
            if (archivoValido(r.archivo)) setSel(r.archivo);
            cargar();
          } else if (!r.cancelado) aviso(`No pude importar: ${r.error || 'error desconocido'}`, true);
        });
      } catch (e) { setOcupado(false); aviso('No pude abrir el diálogo de importar.', true); }
    };

    const asignar = (archivo) => {
      if (!bib.activo) return;
      if (!puede('personaje_vrm')) {
        setBib((b) => ({ ...b, activo_vrm: archivo }));
        aviso('Demo · sin backend: la asignación no se guarda.');
        return;
      }
      setOcupado(true);
      try {
        window.lune.personaje_vrm(bib.activo, archivo, (j) => {
          const r = resultado(j);
          if (!vivo.current) return;
          setOcupado(false);
          if (!r.ok) { aviso(`No pude asignar el modelo: ${r.error || 'error desconocido'}`, true); return; }
          aviso(archivo ? `«${bib.activo}» ahora usa ${archivo}.` : `«${bib.activo}» vuelve al modelo por defecto.`);
          cargar();
        });
      } catch (e) { setOcupado(false); aviso('No pude asignar el modelo.', true); }
    };

    const borrar = (archivo) => {
      setConfirmar('');
      if (cola.current.nombre === archivo) { cola.current.cambios = {}; vaciarCola(); }
      if (!puede('vrm_borrar')) {
        const nb = { ...bib, modelos: bib.modelos.filter((m) => m.archivo !== archivo) };
        setBib(nb);
        setSel(elegirModelo(nb, ''));
        aviso('Demo · sin backend: no se ha borrado ningún archivo.');
        return;
      }
      setOcupado(true);
      try {
        window.lune.vrm_borrar(archivo, (j) => {
          const r = resultado(j);
          if (!vivo.current) return;
          setOcupado(false);
          if (!r.ok) { aviso(`No pude borrar: ${r.error || 'error desconocido'}`, true); return; }
          const quitados = Array.isArray(r.personajes) ? r.personajes.map((p) => texto(p, 60)).filter(Boolean) : [];
          aviso(`«${archivo}» borrado${quitados.length ? `; ${quitados.join(', ')} ${quitados.length > 1 ? 'vuelven' : 'vuelve'} al modelo por defecto` : ''}.`);
          setFichas((fs) => { const n = { ...fs }; delete n[archivo]; return n; });
          setMinis((ms) => { const n = { ...ms }; delete n[archivo]; return n; });
          pedidas.current.delete(archivo);
          setSel('');
          cargar();
        });
      } catch (e) { setOcupado(false); aviso('No pude borrar el modelo.', true); }
    };

    // ── Derivados ───────────────────────────────────────────────────────────
    const ficha = useMemo(() => {
      const deBib = bib.modelos.find((m) => m.archivo === sel) || null;
      const f = fichas[sel];
      return f ? { ...(deBib || {}), ...f } : deBib;
    }, [bib, fichas, sel]);
    const esDelActivo = !!(sel && bib.activo_vrm && bib.activo_vrm.toLowerCase() === sel.toLowerCase());
    // La carpeta de verdad (vrm_biblioteca la manda: en la instalada vive en %APPDATA%).
    const carpeta = bib.carpeta || 'modelo_vrm/';
    const sinOjos = !!(ficha && ficha.tieneLookAt === false);
    const hayCfg = !!(cfg && typeof set === 'function');
    const siguiendo = !hayCfg || cfg.seguir_cursor !== false;
    const Icono = window.IconUser || window.IconMoon || (() => null);

    return (
      <>
        <Card eyebrow={<><Icono width={13} height={13}/> Asistente en escritorio · VRM</>} title="Biblioteca de modelos 3D" tone="blue">
          <p className="ln-card-nota">
            Los .vrm de <b>{carpeta}</b>. Elige uno para ver su ficha y calibrarlo: los cambios se ven en la asistente 3D
            al momento y se guardan con el modelo.
          </p>
          {!bib.webengine && (
            <p className="ln-vrm-aviso">
              {cfg && cfg.instalada
                ? 'No pude cargar QtWebEngine y la asistente 3D lo necesita: reinstala Lune. Puedes preparar los modelos igual.'
                : 'La asistente 3D necesita PyQt6-WebEngine (Sistema → Instalar componentes…). Puedes preparar los modelos igual.'}
            </p>
          )}
          {cargando && bib.modelos.length === 0 && <p className="ln-x-estado">Cargando modelos…</p>}
          {!cargando && bib.modelos.length === 0 && (
            <p className="ln-empty">Aún no hay ningún .vrm. Impórtalo con el botón o cópialo a la carpeta {carpeta}.</p>
          )}
          {bib.modelos.length > 0 && (
            <div className="ln-vrm-grid" role="listbox" aria-label="Modelos VRM">
              {bib.modelos.map((m) => {
                const url = minis[m.archivo] || '';
                const esSel = m.archivo === sel;
                const delActivo = bib.activo_vrm && bib.activo_vrm.toLowerCase() === m.archivo.toLowerCase();
                const porDefecto = bib.por_defecto && bib.por_defecto.toLowerCase() === m.archivo.toLowerCase();
                return (
                  <button key={m.archivo} type="button" role="option" aria-selected={esSel}
                    className={`ln-vrm-tile${esSel ? ' is-sel' : ''}`} title={m.archivo} onClick={() => setSel(m.archivo)}>
                    <div className="ln-vrm-thumb">
                      {url ? <img src={url} alt={`Miniatura de ${etiqueta(m)}`} draggable={false} />
                        : <span className="ln-vrm-ini" aria-hidden="true">{iniciales(m)}</span>}
                      {m.version && <span className="ln-vrm-ver">{m.version === '1' ? '1.0' : '0.x'}</span>}
                    </div>
                    <div className="ln-vrm-name">{etiqueta(m)}</div>
                    <div className="ln-vrm-sub">{m.autor || m.archivo}</div>
                    {(delActivo || porDefecto) && (
                      <div className="ln-vrm-tags">
                        {delActivo && <Badge variant="cyan">{bib.activo || 'activo'}</Badge>}
                        {porDefecto && <Badge variant="ink" outline>por defecto</Badge>}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
          <div className="ln-audio-row">
            <Button variant="primary" size="sm" disabled={ocupado} onClick={importar}>Importar .vrm…</Button>
            {conPuente && <Button variant="ghost" size="sm" disabled={ocupado} onClick={cargar}>Recargar</Button>}
            {bib.modelos.length > 0 && <Badge variant="ink" outline>{bib.modelos.length} {bib.modelos.length === 1 ? 'modelo' : 'modelos'}</Badge>}
          </div>
          <p className="lune-field-hint" style={{ marginTop: 8 }}>
            Hay modelos gratuitos en VRoid Hub y Booth: respeta la licencia de cada uno.
          </p>
          {msg.texto && <p className={`ln-x-estado${msg.error ? ' is-error' : ''}`}>{msg.texto}</p>}
        </Card>

        {ficha && (
          <Card eyebrow={`Modelo · ${ficha.archivo}`} title={etiqueta(ficha)} tone="cyan" tick={esDelActivo}>
            {!ficha.ok && <p className="ln-vrm-aviso">{ficha.motivo || 'Este archivo no se puede leer como VRM.'}</p>}
            <dl className="ln-vrm-ficha">
              {describir(ficha) && <><dt>Modelo</dt><dd>{describir(ficha)}</dd></>}
              {ficha.autor && <><dt>Autor</dt><dd>{ficha.autor}</dd></>}
              {(ficha.licencia || ficha.licencia_url) && (
                <><dt>Licencia</dt><dd>{ficha.licencia || '—'}{ficha.licencia_url ? ` · ${ficha.licencia_url}` : ''}</dd></>
              )}
              <dt>Lo usan</dt>
              <dd>
                {ficha.personajes && ficha.personajes.length ? ficha.personajes.join(', ') : 'ningún personaje'}
                {ficha.por_defecto || (bib.por_defecto && bib.por_defecto.toLowerCase() === ficha.archivo.toLowerCase()) ? ' · modelo por defecto' : ''}
              </dd>
            </dl>

            <div className="ln-seg-row">
              {bib.activo && !esDelActivo && (
                <Button variant="primary" size="sm" disabled={ocupado} onClick={() => asignar(ficha.archivo)}>
                  Usar con {bib.activo}
                </Button>
              )}
              {bib.activo && esDelActivo && (
                <Button variant="ghost" size="sm" disabled={ocupado} onClick={() => asignar('')}>Quitar de {bib.activo}</Button>
              )}
              <Button variant="ghost" size="sm" disabled={ocupado} onClick={() => setConfirmar(ficha.archivo)}>Borrar…</Button>
            </div>
            {confirmar === ficha.archivo && (
              <div className="ln-vrm-peligro" role="alertdialog" aria-label="Confirmar borrado">
                <p>
                  ¿Borrar <b>{ficha.archivo}</b>? Se elimina el archivo de modelo_vrm/ y su calibración
                  {ficha.personajes && ficha.personajes.length ? `, y ${ficha.personajes.join(', ')} ${ficha.personajes.length > 1 ? 'vuelven' : 'vuelve'} al modelo por defecto` : ''}.
                  No se puede deshacer.
                </p>
                <div className="ln-seg-row">
                  <Button variant="danger" size="sm" onClick={() => borrar(ficha.archivo)}>Sí, borrar</Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmar('')}>Cancelar</Button>
                </div>
              </div>
            )}

            <div className="lune-overline ln-vrm-sec">Calibración</div>
            <div className="ln-seg-row">
              {EJES.map(([v, t, desc]) => (
                <Button key={v} variant={valores.invertirEjes === v ? 'primary' : 'ghost'} size="sm" title={desc}
                  onClick={() => cambiar('invertirEjes', v)}>{t}</Button>
              ))}
            </div>
            <span className="lune-field-hint">Ejes del esqueleto. Si los brazos salen en V o la cabeza gira al revés, prueba «Invertir X/Z».</span>
            <div className="ln-vrm-checks">
              {SIGNOS.map(([k, t, desc]) => (
                <Switch key={k} label={t} title={desc} checked={valores[k] === -1}
                  onChange={(e) => cambiar(k, !!(e && e.target ? e.target.checked : e))} />
              ))}
            </div>
            <div className="ln-settings-grid" style={{ marginTop: 10 }}>
              <Deslizador id="f-vrm-luz" label="Luz" min={0.2} max={3} step={0.05} value={valores.luz}
                onChange={(n) => cambiar('luz', n)} fmt={fmtLuz} hint="Multiplica las luces de la escena (modelos muy oscuros o quemados)." />
              <Deslizador id="f-vrm-altura" label="Altura" min={-0.5} max={0.5} step={0.01} value={valores.altura}
                onChange={(n) => cambiar('altura', n)} fmt={fmtAltura} hint="Sube o baja el modelo en su ventana." />
            </div>

            <div className="lune-overline ln-vrm-sec">Seguimiento del cursor</div>
            {hayCfg && (
              <Switch label="Seguir el cursor (en todos los modelos)" checked={siguiendo}
                onChange={(e) => set('seguir_cursor')(!!(e && e.target ? e.target.checked : e))} />
            )}
            {!siguiendo && (
              <p className="ln-x-estado">El seguimiento está apagado: estos pesos se guardan, pero no se aplican hasta que lo enciendas.</p>
            )}
            <div className="ln-settings-grid" style={{ marginTop: 10 }}>
              <Deslizador id="f-vrm-cabeza" label="Cabeza" min={0} max={100} step={5} value={Math.round(valores.pesoCabeza * 100)}
                onChange={(n) => cambiar('pesoCabeza', n / 100)} fmt={(n) => fmtPct(n / 100)} hint="Cuánto gira la cabeza hacia el ratón." />
              <Deslizador id="f-vrm-torso" label="Torso" min={0} max={100} step={5} value={Math.round(valores.pesoTorso * 100)}
                onChange={(n) => cambiar('pesoTorso', n / 100)} fmt={(n) => fmtPct(n / 100)} hint="Cuánto acompaña la columna." />
              <Deslizador id="f-vrm-ojos" label="Ojos" min={0} max={100} step={5} value={Math.round(valores.pesoOjos * 100)}
                disabled={sinOjos} onChange={(n) => cambiar('pesoOjos', n / 100)} fmt={(n) => fmtPct(n / 100)}
                hint={sinOjos ? 'Sin efecto en este modelo.' : 'Cuánto siguen los ojos al cursor.'} />
            </div>
            {sinOjos && (
              <p className="ln-vrm-aviso">
                Este modelo no mueve los ojos: no trae «lookAt» (ni huesos de ojos ni expresiones de mirada).
                La cabeza y el torso sí siguen al cursor.
              </p>
            )}
            <div className="ln-audio-row">
              <Button variant="ghost" size="sm" onClick={restablecer}>Restablecer calibración</Button>
            </div>
          </Card>
        )}
      </>
    );
  }

  Object.assign(window, {
    VrmBiblioteca,
    LuneVrm: {
      RANGOS, CLAVES, DEFECTOS, validarValor, urlMiniatura, normalizarFicha, normalizarBiblioteca, efectivosDe,
      elegirModelo, iniciales, describir, resultado, archivoValido, fmtPct, fmtLuz, fmtAltura, ESPERA_ENVIO,
    },
  });
})();
