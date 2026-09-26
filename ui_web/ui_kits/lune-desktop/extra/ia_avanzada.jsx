/* Lune CD desktop — IA avanzada: API compatible con OpenAI, parámetros del modelo y aprobaciones.
 *
 * CompatCard({cfg, set}):   proveedor «compat» (LM Studio, Groq, OpenAI, Together, Mistral…): URL base,
 *                           clave, modelo y «Probar conexión».
 * AvanzadoCard({cfg, set}): presets Preciso / Equilibrado / Creativo, temperatura, top_p, top_k, min_p,
 *                           repeat_penalty, máximo de tokens, semilla, contexto 2K–32K y «Liberar memoria».
 * AprobacionModal({pendiente, onResolver}): una acción del modelo que pide permiso. Muestra herramienta,
 *                           resumen y argumentos con cuenta atrás de 60 s; «Sí, hazlo» / «No» llaman a
 *                           window.lune.resolver_aprobacion(id, ok) y luego a onResolver(id, ok). Al llegar
 *                           a 0 NO se responde al backend: el modal se cierra (onResolver(id, false,
 *                           'caducada')) y el Ejecutor la marca CADUCADA por su cuenta (llega
 *                           aprobacion_resuelta). Esc = No; Enter NO aprueba (el foco empieza en «No» y
 *                           «Sí, hazlo» no responde los primeros 700 ms).
 * AprobacionHost():         cola global: escucha la señal window.lune.aprobacion_pedida(str json) (y el
 *                           evento de ventana 'lune-aprobacion' con detail = json u objeto) y muestra la
 *                           primera. Si el puente trae aprobacion_resuelta(str id) la quita al resolverse
 *                           fuera (diálogo Qt, Ejecutor que cancela), y si trae aprobaciones_pendientes(cb)
 *                           recoge las que ya esperaban al abrir la ventana.
 *
 * La petición es la que arma lune_core/acciones.Ejecutor._pedir:
 *   {id, herramienta, args, resumen, descripcion, riesgo, motivo, origen, timeout, pregunta}
 * (también se aceptan timeout_s y expira = epoch en ms). Todo lo que viene del modelo (herramienta,
 * resumen, argumentos) se pinta como TEXTO PLANO, sin caracteres de control ni de formato (bidi, ancho
 * cero, que podrían disfrazar una URL) y recortado: las mismas reglas que ui/aprobacion_qt.py.
 *
 * Claves planas (como get_config/guardar_config en ui/web_bridge.py; van a datos.json → modelos, ver
 * nucleo/datos.parametros_muestreo):
 *   compat_url, compat_key, compat_model,
 *   preset_muestreo (preciso · equilibrado · creativo · personalizado),
 *   temperatura, top_p, top_k, min_p, repeat_penalty  (null = «del modelo»: no se envía),
 *   num_predict (0 = automático: bot.max_tokens), seed (−1 = aleatoria), ollama_num_ctx (2048–32768).
 * Los presets son los de datos.PRESETS_MUESTREO: Preciso fija los cinco; Equilibrado y Creativo solo la
 * temperatura y dejan el resto «del modelo» (null), igual que datos.aplicar_preset_muestreo.
 * compat_key: get_config trae una máscara fija en vez de la clave; CampoClave la muestra como guardada y lo
 *   que se teclee la sustituye entera; sin tocar, se manda la máscara y el puente conserva la guardada.
 * Puente: compat_probar(cb) → JSON {ok, mensaje, modelos:[…], ms}; compat_borrador(json) (opcional: antes de
 *         probar se manda lo escrito, {compat_url, compat_key, compat_model}); ia_liberar_vram(cb) →
 *         JSON/bool/nada; resolver_aprobacion(id, ok); señales aprobacion_pedida y, opcional, aprobacion_resuelta.
 * Sin window.lune (demo en el navegador) todo funciona con estado local: LuneIA.demoAprobacion() abre una.
 *
 * Se registra solo con Object.assign(window, {...}) dentro de una IIFE (Babel convierte los const
 * de nivel superior en var globales y pisaría los de otros .jsx).
 */
(function () {
  const { useState, useEffect, useRef, useCallback } = React;

  // ── Datos ──────────────────────────────────────────────────────────────────
  // Espejo de nucleo/datos.PRESETS_MUESTREO: lo que un preset no define queda «del modelo» (null).
  const PRESETS = {
    preciso:     { temperatura: 0.2, top_p: 0.9, top_k: 40, min_p: 0.05, repeat_penalty: 1.1 },
    equilibrado: { temperatura: 0.7 },
    creativo:    { temperatura: 1.0 },
  };
  const NOMBRES_PRESET = [['preciso', 'Preciso'], ['equilibrado', 'Equilibrado'], ['creativo', 'Creativo']];
  const PRESET_POR_DEFECTO = 'equilibrado';
  const CLAVES_MUESTREO = ['temperatura', 'top_p', 'top_k', 'min_p', 'repeat_penalty'];
  // Límites de datos._PARAMS_MUESTREO (el deslizador puede ser más estrecho).
  const RANGOS = { temperatura: [0, 2], top_p: [0.01, 1], top_k: [1, 1000], min_p: [0, 1], repeat_penalty: [0.5, 2] };
  // Dónde se dibuja un deslizador «del modelo» (los valores por defecto de Ollama).
  const NEUTROS = { top_p: 0.9, top_k: 40, min_p: 0, repeat_penalty: 1.1 };
  const DEFECTOS = { temperatura: 0.7, top_p: null, top_k: null, min_p: null, repeat_penalty: null,
    num_predict: 0, seed: -1, ollama_num_ctx: 8192 };
  const CONTEXTOS = [2048, 4096, 8192, 16384, 32768];
  const ATAJOS_COMPAT = [
    ['LM Studio', 'http://localhost:1234/v1'],
    ['Groq', 'https://api.groq.com/openai/v1'],
    ['OpenAI', 'https://api.openai.com/v1'],
    ['Together', 'https://api.together.xyz/v1'],
    ['Mistral', 'https://api.mistral.ai/v1'],
    ['DeepSeek', 'https://api.deepseek.com/v1'],
  ];
  const TIMEOUT_APROBACION_S = 60;
  const ARMADO_MS = 700;          // «Sí, hazlo» no responde hasta entonces: evita un doble clic de rebote
  // Recortes de ui/aprobacion_qt.py
  const MAX_HERRAMIENTA = 60, MAX_RESUMEN = 300, MAX_VALOR = 160, MAX_ARGS = 700, MAX_LINEAS_ARGS = 12;
  const SALTO_VISIBLE = ' ⏎ ';
  // Puntos de código que no se pintan (como las categorías Cc, Cf y Co que quita aprobacion_qt.limpiar):
  // control, guion blando, marcas bidi y de ancho cero, BOM, etiquetas invisibles y uso privado.
  // Van como números (no como escapes en el fuente) para que el archivo no lleve caracteres invisibles.
  const INVISIBLES = [
    [0x00, 0x08], [0x0B, 0x1F], [0x7F, 0x9F], [0xAD, 0xAD], [0x600, 0x605], [0x61C, 0x61C], [0x6DD, 0x6DD],
    [0x70F, 0x70F], [0x180E, 0x180E], [0x200B, 0x200F], [0x202A, 0x202E], [0x2060, 0x2064], [0x2066, 0x206F],
    [0xFEFF, 0xFEFF], [0xFFF9, 0xFFFB], [0xE000, 0xF8FF], [0xD800, 0xDFFF], [0x1D173, 0x1D17A],
    [0xE0000, 0xE007F], [0xF0000, 0x10FFFF],
  ];
  const SALTOS = [0x0A, 0x2028, 0x2029];      // salto de línea, separador de línea y de párrafo

  // ── Utilidades puras (window.LuneIA, las usa tests/test_jsx_extra.py) ──────
  function num(v, defecto) {
    if (v === '' || v == null || typeof v === 'boolean') return defecto;
    const n = Number(v);
    return Number.isFinite(n) ? n : defecto;
  }
  const casi = (a, b) => a != null && b != null && Math.abs(a - b) < 1e-6;

  /** Valor de muestreo validado como en datos._opcional; null = «del modelo». */
  function opcional(v, clave) {
    const n = num(v, null);
    if (n == null) return null;
    if (clave === 'top_k' && n <= 0) return null;          // top_k ≤ 0 = sin valor
    const [a, b] = RANGOS[clave] || [-Infinity, Infinity];
    const r = Math.min(b, Math.max(a, n));
    return clave === 'top_k' ? Math.round(r) : r;
  }

  function presetGuardado(cfg) {
    const c = cfg || {};
    const p = String(c.preset_muestreo || c.preset || '').trim().toLowerCase();
    return PRESETS[p] || p === 'personalizado' ? p : PRESET_POR_DEFECTO;
  }

  /** Valores efectivos (como datos.parametros_muestreo): lo explícito manda; si falta, el del preset guardado. */
  function valoresMuestreo(cfg) {
    const c = cfg || {};
    const base = PRESETS[presetGuardado(c)] || {};
    const out = {};
    CLAVES_MUESTREO.forEach((k) => {
      const v = opcional(c[k], k);
      out[k] = v != null ? v : (base[k] != null ? base[k] : null);
    });
    if (out.temperatura == null) out.temperatura = DEFECTOS.temperatura;
    return out;
  }

  /** ¿Qué preset coincide con estos valores? → 'preciso' | 'equilibrado' | 'creativo' | 'personalizado'. */
  function presetDe(cfg) {
    const v = valoresMuestreo(cfg);
    for (const [id] of NOMBRES_PRESET) {
      const p = PRESETS[id];
      if (CLAVES_MUESTREO.every((k) => (p[k] != null ? casi(v[k], p[k]) : v[k] == null))) return id;
    }
    return 'personalizado';
  }

  /** Lo que escribe un preset: sus valores y null en lo que no define (vuelve al valor del modelo). */
  function valoresPreset(id) {
    const p = PRESETS[id];
    if (!p) return null;
    const out = {};
    CLAVES_MUESTREO.forEach((k) => { out[k] = p[k] != null ? p[k] : null; });
    return out;
  }

  /** Contexto guardado (ollama_num_ctx; también acepta num_ctx de parametros_muestreo) o null. */
  function contexto(c) {
    const o = c || {};
    return num(o.ollama_num_ctx != null && o.ollama_num_ctx !== '' ? o.ollama_num_ctx : o.num_ctx, null);
  }

  /** Índice de CONTEXTOS más cercano (para el deslizador); tolera valores fuera de la lista. */
  function indiceContexto(n) {
    const v = num(n, DEFECTOS.ollama_num_ctx);
    let mejor = 0;
    CONTEXTOS.forEach((c, i) => { if (Math.abs(c - v) < Math.abs(CONTEXTOS[mejor] - v)) mejor = i; });
    return mejor;
  }
  const etiquetaContexto = (n) => `${Math.round(num(n, 8192) / 1024)}K`;

  function hostDe(url) {
    try { return new URL(String(url)).hostname.replace(/^\[|\]$/g, '').toLowerCase(); } catch (e) { return ''; }
  }

  /** ¿El host es este equipo o la red local? (ahí se tolera http y la clave vacía). */
  function esLocal(url) {
    const h = hostDe(url);
    if (!h) return false;
    if (h === 'localhost' || h === '::1' || h.endsWith('.local') || h.endsWith('.lan')) return true;
    const m = h.match(/^(\d+)\.(\d+)\.\d+\.\d+$/);
    if (!m) return false;
    const a = +m[1], b = +m[2];
    return a === 127 || a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31);
  }

  /** ¿La URL base es usable? (http/https, sin usuario:contraseña incrustados). Vacía = no configurada. */
  function urlValida(url) {
    const u = String(url || '').trim();
    if (!u) return false;
    try {
      const p = new URL(u);
      return (p.protocol === 'http:' || p.protocol === 'https:') && !p.username && !p.password && !!p.hostname;
    } catch (e) { return false; }
  }

  /** Aviso sobre la URL base: '' si está bien. */
  function avisoUrl(url, clave) {
    const u = String(url || '').trim();
    if (!u) return '';
    let p = null;
    try { p = new URL(u); } catch (e) { return 'No parece una URL: empieza por http:// o https://'; }
    if (p.protocol !== 'http:' && p.protocol !== 'https:') return 'Solo http:// o https://';
    if (p.username || p.password) return 'No pongas usuario ni contraseña en la URL: la clave va en su campo.';
    if (p.protocol === 'http:' && !esLocal(u) && String(clave || '').trim())
      return 'Ojo: con http:// fuera de tu red la clave viajaría sin cifrar. Usa https://.';
    if (/\/chat\/completions\/?$/.test(p.pathname)) return 'Pon solo la base (…/v1): Lune añade /chat/completions.';
    return '';
  }

  const esInvisible = (cp) => INVISIBLES.some(([a, b]) => cp >= a && cp <= b);

  /** Una línea visible, como aprobacion_qt.limpiar: sin control ni formato; saltos → ⏎; recortada con «…». */
  function limpiar(texto, maximo) {
    const t0 = (texto == null ? '' : String(texto)).replace(/\r\n?/g, '\n');
    let t = '';
    for (const ch of t0) {                     // por puntos de código (un emoji no se parte)
      const cp = ch.codePointAt(0);
      if (SALTOS.includes(cp)) t += SALTO_VISIBLE;
      else if (cp === 0x09) t += ' ';
      else if (!esInvisible(cp)) t += ch;
    }
    t = t.trim();
    const max = maximo == null ? MAX_RESUMEN : maximo;
    const letras = Array.from(t);
    if (letras.length > max) t = `${letras.slice(0, Math.max(0, max - 1)).join('').trimEnd()}…`;
    return t;
  }

  const aJson = (v) => { try { const s = JSON.stringify(v); return s === undefined ? String(v) : s; } catch (e) { return String(v); } };

  /** Argumentos como «clave: valor», una línea por clave (como aprobacion_qt.formatear_args). */
  function formatearArgs(args, maxValor = MAX_VALOR, maxTotal = MAX_ARGS) {
    if (args == null) return '';
    if (typeof args !== 'object') return limpiar(typeof args === 'string' ? args : aJson(args), maxTotal);
    if (Array.isArray(args)) return args.length ? limpiar(aJson(args), maxTotal) : '';
    const claves = Object.keys(args);
    if (!claves.length) return '';
    const lineas = claves.slice(0, MAX_LINEAS_ARGS).map((k) => {
      const v = args[k];
      return `${limpiar(k, 40)}: ${limpiar(typeof v === 'string' ? v : aJson(v), maxValor)}`;
    });
    if (claves.length > MAX_LINEAS_ARGS) lineas.push(`… (${claves.length - MAX_LINEAS_ARGS} más)`);
    let t = lineas.join('\n');
    if (t.length > maxTotal) t = `${t.slice(0, Math.max(0, maxTotal - 1)).trimEnd()}…`;
    return t;
  }

  /**
   * Lo que el usuario metió al editar `anterior` hasta dejarlo en `nuevo` (sin el prefijo ni el sufijo
   * que no cambiaron). Para la clave guardada: get_config no la manda, trae una máscara fija que el
   * puente entiende como «conservar la guardada»; al escribir sobre ella, lo tecleado SUSTITUYE a la
   * máscara entera (no se le pega), y borrar deja el campo vacío.
   */
  function textoInsertado(anterior, nuevo) {
    const a = String(anterior == null ? '' : anterior), n = String(nuevo == null ? '' : nuevo);
    let i = 0;
    while (i < a.length && i < n.length && a[i] === n[i]) i++;
    let j = 0;
    while (j < a.length - i && j < n.length - i && a[a.length - 1 - j] === n[n.length - 1 - j]) j++;
    return n.slice(i, n.length - j);
  }

  /** Respuesta de compat_probar → {ok, mensaje, modelos, ms}. */
  function normalizarPrueba(resp) {
    let r = resp;
    if (typeof r === 'string') { try { r = JSON.parse(r); } catch (e) { r = { ok: false, mensaje: r }; } }
    if (typeof r === 'boolean') r = { ok: r };
    const o = r && typeof r === 'object' ? r : {};
    const modelos = (Array.isArray(o.modelos) ? o.modelos : [])
      .map((m) => (typeof m === 'string' ? m : (m && (m.id || m.nombre)) || ''))
      .map((m) => limpiar(m, 120)).filter(Boolean).slice(0, 60);
    const ms = num(o.ms != null ? o.ms : o.latencia_ms, null);
    return {
      ok: !!o.ok,
      mensaje: limpiar(o.mensaje || o.error || (o.ok ? 'Conectado' : 'No respondió'), 300),
      modelos,
      ms: ms == null ? null : Math.round(ms),
    };
  }

  /** Petición de aprobación (JSON u objeto) → forma estable, o null si no trae id. */
  function normalizarPendiente(p) {
    let o = p;
    if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { return null; } }
    if (!o || typeof o !== 'object' || Array.isArray(o)) return null;
    const id = String(o.id == null ? '' : o.id).trim().slice(0, 64);
    if (!id) return null;
    let args = o.args != null ? o.args : o.argumentos;
    if (args == null) args = {};
    const timeout = Math.max(5, Math.min(600, num(o.timeout_s != null ? o.timeout_s : o.timeout, TIMEOUT_APROBACION_S)));
    let expira = num(o.expira, null);
    if (expira != null && expira < 1e12) expira *= 1000;          // vino en segundos
    return {
      id,
      herramienta: limpiar(o.herramienta || o.tool || 'acción', MAX_HERRAMIENTA) || 'acción',
      resumen: limpiar(o.resumen || '', MAX_RESUMEN),
      descripcion: limpiar(o.descripcion || '', MAX_RESUMEN),
      motivo: limpiar(o.motivo || '', MAX_RESUMEN),
      args,
      riesgo: limpiar(o.riesgo || '', 20).toUpperCase(),
      origen: limpiar(o.origen || '', 30),
      timeout_s: timeout,
      expira,                           // epoch en ms (opcional; si no, se cuenta desde que aparece)
    };
  }

  /** Variante de Badge para la etiqueta de riesgo (mismos colores que aprobacion_qt.color_riesgo). */
  function varianteRiesgo(riesgo) {
    const r = String(riesgo || '').toUpperCase();
    if (/PELIGR|ALTO|SISTEMA/.test(r)) return 'danger';
    if (/ESCRIT|RED|EJEC/.test(r)) return 'yellow';
    if (/LECTUR/.test(r)) return 'cyan';
    return 'ink';
  }

  // ── Estilos propios (index.html no se toca) ────────────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-x-ia-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-x-ia-css';
      st.textContent = `
        .ln-x-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-x-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-x-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-x-range.is-vacio .ln-x-range-val{ color:var(--text-faint); }
        .ln-x-range.is-vacio input[type=range]{ opacity:.45; }
        .ln-x-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-x-link{ appearance:none; -webkit-appearance:none; background:none; border:none; padding:0; cursor:pointer;
          font:inherit; color:var(--cyan-400); text-decoration:underline; text-underline-offset:2px; }
        .ln-x-link:hover{ color:var(--cyan-300); }
        .ln-x-estado{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-x-estado.is-error{ color:var(--yellow-500); }
        .ln-x-chips{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
        .ln-x-chip{ appearance:none; -webkit-appearance:none; cursor:pointer; font-family:var(--font-mono); font-size:11px;
          padding:3px 9px; color:var(--cyan-300); background:var(--ink-900); border:var(--bw) solid var(--cyan-700); }
        .ln-x-chip:hover, .ln-x-chip.is-on{ background:var(--cyan-500); color:var(--ink-950); border-color:var(--cyan-500); }
        .ln-x-aprob{ border-color:var(--yellow-600); width:min(560px, 100%); }
        .ln-x-aprob-tool{ font-family:var(--font-mono); font-size:14px; color:var(--yellow-500); overflow-wrap:anywhere; }
        .ln-x-aprob-args{ max-height:34vh; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; }
        .ln-x-aprob-bar i{ background:linear-gradient(90deg, var(--yellow-500), var(--cyan-500)); transition:width .25s linear; }
        @media (prefers-reduced-motion: reduce){ .ln-x-aprob-bar i{ transition:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  function useCfg(cfg, set) {
    const [local, setLocal] = useState(() => ({ ...(cfg || {}) }));
    if (typeof set === 'function') return [cfg || {}, set];
    return [local, (k) => (e) => setLocal((c) => ({ ...c, [k]: (e && e.target) ? e.target.value : e }))];
  }

  /** Deslizador con valor visible. `vacio` = «del modelo»: se dibuja en `neutro` y ofrece volver a vacío. */
  function Deslizador({ id, label, min, max, step, value, onChange, fmt, hint, vacio, neutro, onVaciar }) {
    const pos = vacio ? neutro : value;
    return (
      <div className={`lune-field ln-x-range${vacio ? ' is-vacio' : ''}`}>
        <div className="ln-x-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-x-range-val">
            {vacio ? 'del modelo' : (fmt ? fmt(value) : value)}
            {!vacio && onVaciar && (
              <>{' '}<button type="button" className="ln-x-link" title="Que lo decida el modelo (no se envía)"
                onClick={onVaciar}>↺ del modelo</button></>
            )}
          </span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={pos}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }

  /**
   * Contraseña de una clave de API. Si el valor vino de fuera (la máscara de get_config, o una clave ya
   * guardada) y no lo ha escrito el usuario en este campo, está «guardada»: se ve como puntos y lo
   * primero que se teclee la SUSTITUYE entera (textoInsertado). Mientras no se toque, al guardar o
   * probar se manda la máscara tal cual y el puente la cambia por la clave guardada.
   */
  function CampoClave({ id, label, value, onChange, hint, hintGuardada, placeholder }) {
    const { Input } = window.LUNE;
    const propia = useRef(null);                 // lo último que puso este campo
    const v = value == null ? '' : String(value);
    const guardada = v !== '' && v !== propia.current;
    const cambiar = (e) => {
      const n = (e && e.target) ? e.target.value : e;
      const nuevo = guardada ? textoInsertado(v, n) : String(n == null ? '' : n);
      propia.current = nuevo;
      if (typeof onChange === 'function') onChange(nuevo);
    };
    return (
      <Input id={id} label={label} type="password" autoComplete="off" spellCheck={false}
        value={v} onChange={cambiar} placeholder={placeholder || 'sin clave'}
        hint={guardada ? (hintGuardada || 'Clave guardada. Lo que escribas la sustituye; bórrala para quitarla.') : hint} />
    );
  }

  // ── CompatCard ─────────────────────────────────────────────────────────────
  function CompatCard({ cfg, set: setProp }) {
    const { Card, Button, Input, Badge } = window.LUNE;
    const [c, set] = useCfg(cfg, setProp);
    const [prueba, setPrueba] = useState(null);
    const [probando, setProbando] = useState(false);
    const vivo = useRef(true);
    useEffect(() => { inyectarEstilos(); vivo.current = true; return () => { vivo.current = false; }; }, []);

    const url = String(c.compat_url || '');
    const aviso = avisoUrl(url, c.compat_key);
    const conBorrador = !!(window.lune && typeof window.lune.compat_borrador === 'function');

    const probar = () => {
      if (!window.lune || typeof window.lune.compat_probar !== 'function') {
        setPrueba({ ok: false, mensaje: 'Demo · sin backend', modelos: [], ms: null }); return;
      }
      setProbando(true); setPrueba(null);
      // Se prueba lo escrito (aún sin guardar). La clave va como está: si es la máscara de la
      // guardada, el puente usa la guardada.
      if (conBorrador) {
        try {
          window.lune.compat_borrador(JSON.stringify({
            compat_url: url, compat_key: String(c.compat_key || ''), compat_model: String(c.compat_model || ''),
          }));
        } catch (e) { /* se prueba lo guardado */ }
      }
      try {
        window.lune.compat_probar((r) => {
          if (!vivo.current) return;
          setProbando(false); setPrueba(normalizarPrueba(r));
        });
      } catch (e) { setProbando(false); setPrueba({ ok: false, mensaje: 'No pude pedir la prueba al backend.', modelos: [], ms: null }); }
    };

    const Icono = window.IconCloud || (() => null);
    return (
      <Card eyebrow={<><Icono width={13} height={13}/> Red Neuronal · Compatible OpenAI</>} title="Otra API de IA" tone="blue" tick>
        <p className="ln-card-nota">
          Cualquier servicio que hable el formato de OpenAI (<code>/v1/chat/completions</code>): LM Studio en tu PC, Groq,
          OpenAI, Together, Mistral… Se usa como proveedor «compat», además de Ollama y OpenRouter, con reintentos si falla la red.
        </p>
        <div className="ln-x-chips" style={{ margin: '0 0 12px' }}>
          {ATAJOS_COMPAT.map(([n, u]) => (
            <button key={n} type="button" className={`ln-x-chip${url === u ? ' is-on' : ''}`} title={u}
              onClick={() => set('compat_url')(u)}>{n}</button>
          ))}
        </div>
        <div className="ln-settings-grid">
          <Input id="f-compat-url" label="URL base" value={url} onChange={set('compat_url')} error={!!url && !urlValida(url)}
            placeholder="http://localhost:1234/v1" hint={aviso || 'Termina en /v1. Los botones de arriba la rellenan.'} />
          <Input id="f-compat-modelo" label="Modelo" value={c.compat_model || ''} onChange={set('compat_model')}
            placeholder="p. ej. llama-3.1-8b-instant" hint="El nombre exacto que usa ese servicio." />
        </div>
        <div style={{ height: 12 }} />
        <CampoClave id="f-compat-key" label="Clave de la API" value={c.compat_key} onChange={set('compat_key')}
          placeholder={esLocal(url) ? 'no hace falta en local' : 'sin clave'}
          hint={esLocal(url) ? 'LM Studio y servidores locales no la necesitan: déjala vacía.' : 'Se guarda solo en datos.json, en este equipo.'} />
        <div className="ln-audio-row">
          <Button variant="ghost" size="sm" onClick={probar} disabled={probando || !urlValida(url)}>{probando ? 'Probando…' : 'Probar conexión'}</Button>
          {prueba && (
            <Badge variant={prueba.ok ? 'cyan' : 'danger'}>
              {prueba.ok ? 'Conectado' : 'Sin conexión'}{prueba.ms != null ? ` · ${prueba.ms} ms` : ''}
            </Badge>
          )}
          <span className="lune-field-hint">
            {conBorrador ? 'Prueba lo que está escrito, aunque no lo hayas guardado.' : 'Prueba lo guardado: si cambiaste algo, guarda antes.'}
          </span>
        </div>
        {prueba && prueba.mensaje && <p className={`ln-x-estado${prueba.ok ? '' : ' is-error'}`}>{prueba.mensaje}</p>}
        {prueba && prueba.modelos.length > 0 && (
          <>
            <p className="ln-x-estado">Modelos que ofrece ({prueba.modelos.length}). Pulsa uno para elegirlo:</p>
            <div className="ln-x-chips">
              {prueba.modelos.map((m) => (
                <button key={m} type="button" className={`ln-x-chip${m === c.compat_model ? ' is-on' : ''}`}
                  onClick={() => set('compat_model')(m)}>{m}</button>
              ))}
            </div>
          </>
        )}
      </Card>
    );
  }

  // ── AvanzadoCard ───────────────────────────────────────────────────────────
  function AvanzadoCard({ cfg, set: setProp }) {
    const { Card, Button, Input, Badge } = window.LUNE;
    const [c, set] = useCfg(cfg, setProp);
    const [msg, setMsg] = useState({ t: '', error: false });
    const [liberando, setLiberando] = useState(false);
    const vivo = useRef(true);
    useEffect(() => { inyectarEstilos(); vivo.current = true; return () => { vivo.current = false; }; }, []);

    const v = valoresMuestreo(c);
    const preset = presetDe(c);
    const numPredict = Math.max(0, Math.round(num(c.num_predict, DEFECTOS.num_predict)));
    const seed = Math.round(num(c.seed, DEFECTOS.seed));
    const ctx = contexto(c);
    const ctxIdx = indiceContexto(ctx);
    const ctxFuera = ctx != null && !CONTEXTOS.includes(ctx);

    const aplicarPreset = (id) => {
      const p = valoresPreset(id);
      if (!p) return;
      CLAVES_MUESTREO.forEach((k) => set(k)(p[k]));
      set('preset_muestreo')(id);
    };
    // Al tocar un valor se escriben TODOS los efectivos (también los que venían del preset), para que
    // al pasar a «personalizado» no se pierdan; y la etiqueta vuelve a un preset si coincide con uno.
    const cambiar = (k) => (n) => {
      const nuevos = { ...v, [k]: n == null ? null : opcional(n, k) };
      CLAVES_MUESTREO.forEach((k2) => set(k2)(nuevos[k2]));
      set('preset_muestreo')(presetDe({ ...nuevos, preset_muestreo: 'personalizado' }));
    };

    const liberar = () => {
      if (!window.lune || typeof window.lune.ia_liberar_vram !== 'function') {
        setMsg({ t: 'Demo · sin backend', error: false }); return;
      }
      setLiberando(true); setMsg({ t: 'Pidiendo a Ollama que suelte el modelo…', error: false });
      try {
        window.lune.ia_liberar_vram((r) => {
          if (!vivo.current) return;
          setLiberando(false);
          let o = r;
          if (typeof r === 'string') { try { o = JSON.parse(r); } catch (e) { o = { mensaje: r }; } }
          const texto = o && typeof o === 'object' && o.mensaje ? limpiar(o.mensaje, 300) : '';
          if (o === false || (o && typeof o === 'object' && o.ok === false)) {
            setMsg({ t: texto || 'No pude liberar el modelo (¿Ollama está encendido?).', error: true });
          } else {
            setMsg({ t: texto || 'Listo: el modelo sale de la memoria. El próximo mensaje tardará un poco más en cargarlo.', error: false });
          }
        });
      } catch (e) { setLiberando(false); setMsg({ t: 'No pude pedirlo al backend.', error: true }); }
    };

    const f2 = (n) => Number(n).toFixed(2);
    const opc = (k) => ({ vacio: v[k] == null, neutro: NEUTROS[k], onVaciar: () => cambiar(k)(null) });
    const Icono = window.IconCpu || (() => null);
    return (
      <Card eyebrow={<><Icono width={13} height={13}/> Red Neuronal · Ajuste fino</>} title="Parámetros del modelo" tone="yellow">
        <p className="ln-card-nota">
          Cómo elige las palabras. Ollama usa todos; OpenRouter y las APIs compatibles ignoran los que no soportan
          (top_k, min_p y el contexto suelen ser solo de Ollama y LM Studio). «Del modelo» = no se envía.
        </p>
        <div className="ln-seg-row">
          {NOMBRES_PRESET.map(([id, t]) => (
            <Button key={id} variant={preset === id ? 'primary' : 'ghost'} size="sm" onClick={() => aplicarPreset(id)}>{t}</Button>
          ))}
          {preset === 'personalizado' && <Badge variant="yellow" outline>personalizado</Badge>}
        </div>
        <div style={{ height: 14 }} />
        <div className="ln-settings-grid">
          <Deslizador id="f-temp" label="Temperatura" min={0} max={2} step={0.05} value={v.temperatura} fmt={f2}
            onChange={cambiar('temperatura')} hint="Baja = precisa y repetible; alta = creativa y dispersa." />
          <Deslizador id="f-top-p" label="top_p" min={0.05} max={1} step={0.01} value={v.top_p} fmt={f2} {...opc('top_p')}
            onChange={cambiar('top_p')} hint="Solo considera las palabras que suman esta probabilidad." />
          <Deslizador id="f-top-k" label="top_k" min={1} max={200} step={1} value={v.top_k} {...opc('top_k')}
            onChange={cambiar('top_k')} hint="Cuántas palabras candidatas mira en cada paso." />
          <Deslizador id="f-min-p" label="min_p" min={0} max={0.5} step={0.01} value={v.min_p} fmt={f2} {...opc('min_p')}
            onChange={cambiar('min_p')} hint="Descarta las palabras muy improbables frente a la mejor." />
          <Deslizador id="f-repeat" label="Penalización por repetir" min={0.8} max={2} step={0.01} value={v.repeat_penalty} fmt={f2}
            {...opc('repeat_penalty')} onChange={cambiar('repeat_penalty')} hint="1.00 = sin penalizar. Súbelo si se repite." />
          <Deslizador id="f-num-predict" label="Máximo de tokens por respuesta" min={0} max={8192} step={64} value={Math.min(8192, numPredict)}
            fmt={() => (numPredict <= 0 ? 'automático' : numPredict)} onChange={(n) => set('num_predict')(n)}
            hint="0 = automático (el tope de siempre, bot.max_tokens)." />
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-settings-grid">
          <Input id="f-seed" label="Semilla" type="number" min="0" step="1" value={seed < 0 ? '' : String(seed)} placeholder="aleatoria"
            onChange={(e) => {
              const t = String(e.target.value || '').trim();
              const n = parseInt(t, 10);
              set('seed')(t === '' || !Number.isFinite(n) || n < 0 ? -1 : Math.min(n, 2147483647));
            }}
            hint="Vacía = aleatoria. Con un número fijo, la misma pregunta da la misma respuesta." />
          <Deslizador id="f-ctx" label="Contexto (memoria de la conversación)" min={0} max={CONTEXTOS.length - 1} step={1} value={ctxIdx}
            fmt={(i) => `${etiquetaContexto(CONTEXTOS[i])}${ctxFuera ? ` (ahora ${etiquetaContexto(ctx)})` : ''}`}
            onChange={(i) => set('ollama_num_ctx')(CONTEXTOS[i])} hint="Solo Ollama. Más contexto recuerda más, pero gasta más VRAM." />
        </div>
        <div className="ln-audio-row">
          <Button variant="ghost" size="sm" onClick={liberar} disabled={liberando}>{liberando ? 'Liberando…' : 'Liberar memoria del modelo'}</Button>
          <span className="lune-field-hint">Descarga el modelo de Ollama de la VRAM ya (útil antes de jugar).</span>
        </div>
        {msg.t && <p className={`ln-x-estado${msg.error ? ' is-error' : ''}`}>{msg.t}</p>}
      </Card>
    );
  }

  // ── AprobacionModal ────────────────────────────────────────────────────────
  function AprobacionModal({ pendiente, onResolver, enCola = 0 }) {
    const { Button, Badge } = window.LUNE;
    const p = normalizarPendiente(pendiente);
    const id = p ? p.id : '';
    const total = p ? p.timeout_s : TIMEOUT_APROBACION_S;
    const [restante, setRestante] = useState(total);
    const [armado, setArmado] = useState(false);
    const hecho = useRef(false);
    const onResolverRef = useRef(onResolver);
    onResolverRef.current = onResolver;

    const resolver = useCallback((ok) => {
      if (hecho.current || !id) return;
      hecho.current = true;
      try {
        if (window.lune && typeof window.lune.resolver_aprobacion === 'function') window.lune.resolver_aprobacion(id, !!ok);
      } catch (e) { /* el backend la dará por rechazada al caducar */ }
      if (typeof onResolverRef.current === 'function') onResolverRef.current(id, !!ok);
    }, [id]);

    // Se acabó el tiempo: solo se cierra el modal. Responder aquí la dejaría «rechazada por el
    // usuario»; el backend la da por CADUCADA él solo (y avisa con aprobacion_resuelta).
    const caducar = useCallback(() => {
      if (hecho.current || !id) return;
      hecho.current = true;
      if (typeof onResolverRef.current === 'function') onResolverRef.current(id, false, 'caducada');
    }, [id]);

    // Cuenta atrás desde que aparece, o hasta `expira` si la trae (el host la pone al recibirla: una
    // petición que esperó en la cola no tiene más tiempo que el del backend). A 0 = caducada.
    useEffect(() => {
      if (!p) return undefined;
      inyectarEstilos();
      hecho.current = false;
      setArmado(false);
      const fin = p.expira != null ? p.expira : Date.now() + total * 1000;
      const tick = () => {
        const s = Math.max(0, Math.ceil((fin - Date.now()) / 1000));
        setRestante(s);
        if (s <= 0) caducar();
      };
      tick();
      const t = setInterval(tick, 250);
      const a = setTimeout(() => setArmado(true), ARMADO_MS);
      const tecla = (e) => { if (e.key === 'Escape') { e.preventDefault(); resolver(false); } };
      window.addEventListener('keydown', tecla);
      return () => { clearInterval(t); clearTimeout(a); window.removeEventListener('keydown', tecla); };
    }, [id]);   // eslint-disable-line react-hooks/exhaustive-deps

    if (!p) return null;
    const pct = Math.max(0, Math.min(100, (restante / total) * 100));
    const args = formatearArgs(p.args);
    // Orden que llegó desde Telegram (/pc): todo pide permiso y se dice de dónde vino.
    const remota = p.origen === 'remoto';
    const terceros = !!p.origen && p.origen !== 'usuario' && !remota;
    return (
      <div className="ln-modal-bg" role="presentation">
        <div className="ln-modal ln-x-aprob" role="alertdialog" aria-modal="true"
          aria-labelledby="ln-x-aprob-titulo" aria-describedby="ln-x-aprob-resumen">
          <div className="lune-overline">// Lune quiere hacer algo</div>
          <h3 className="ln-modal-title" id="ln-x-aprob-titulo">¿Lo hago?</h3>
          <div className="ln-badge-row" style={{ marginBottom: 10 }}>
            <span className="ln-x-aprob-tool">{p.herramienta}</span>
            {p.riesgo && <Badge variant={varianteRiesgo(p.riesgo)} outline>{p.riesgo.toLowerCase()}</Badge>}
            {terceros && <Badge variant="danger" outline>{p.origen === 'no_confiable' ? 'texto de terceros' : `origen: ${p.origen}`}</Badge>}
            {remota && <Badge variant="yellow" outline>Pedido desde Telegram</Badge>}
            {enCola > 0 && <Badge variant="ink" outline>+{enCola} en cola</Badge>}
          </div>
          <div className="ln-modal-body" id="ln-x-aprob-resumen">
            <p style={{ margin: '0 0 8px' }}>{p.resumen || p.descripcion || 'El modelo pidió usar esta herramienta.'}</p>
            {args && <pre className="ln-code ln-x-aprob-args">{args}</pre>}
            {p.motivo && <span className="ln-modal-nota">Por qué pregunto: {p.motivo}</span>}
            {terceros && (
              <span className="ln-modal-nota" style={{ color: 'var(--yellow-500)' }}>
                La pidió una respuesta que leyó texto de fuera (una ventana, la pantalla, un chat…). Si no se lo pediste tú, di que no.
              </span>
            )}
            {remota && (
              <span className="ln-modal-nota" style={{ color: 'var(--yellow-500)' }}>
                Pedido desde Telegram: llegó por tu bot, no se escribió en este PC. Si no fuiste tú, di que no.
              </span>
            )}
            <span className="ln-modal-nota">Solo tú puedes aprobarla. Si no respondes, se cancela sola.</span>
          </div>
          <div className="ln-vu ln-x-aprob-bar" style={{ marginTop: 14 }} aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>
          <div className="ln-modal-foot">
            <Badge variant="ink" outline>{restante} s</Badge>
            <div className="ln-seg-row">
              <Button variant="ghost" size="sm" autoFocus onClick={() => resolver(false)}>No</Button>
              <Button variant="pop" size="sm" disabled={!armado || restante <= 0} onClick={() => resolver(true)}>Sí, hazlo</Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── AprobacionHost: cola de peticiones del backend ─────────────────────────
  function AprobacionHost() {
    const [cola, setCola] = useState([]);
    useEffect(() => {
      const encolar = (j) => {
        const p = normalizarPendiente(j);
        if (!p) return;
        // El reloj del backend empieza al pedirla, no cuando le toque el turno en la cola.
        const conFin = p.expira != null ? p : { ...p, expira: Date.now() + p.timeout_s * 1000 };
        setCola((c) => (c.some((x) => x.id === conFin.id) ? c : [...c, conFin]));
      };
      const quitar = (id) => setCola((c) => c.filter((x) => x.id !== String(id)));
      const onEvento = (e) => encolar(e && e.detail);
      let puente = null;
      const conectar = () => {
        const l = window.lune;
        if (!l || puente === l) return;
        puente = l;
        try { l.aprobacion_pedida.connect(encolar); } catch (e) { /* puente sin aprobaciones */ }
        try { if (l.aprobacion_resuelta) l.aprobacion_resuelta.connect(quitar); } catch (e) {}
        try {
          if (typeof l.aprobaciones_pendientes === 'function') {
            l.aprobaciones_pendientes((j) => {
              let lista = j;
              if (typeof j === 'string') { try { lista = JSON.parse(j); } catch (e) { lista = []; } }
              (Array.isArray(lista) ? lista : []).forEach(encolar);
            });
          }
        } catch (e) {}
      };
      window.addEventListener('lune-aprobacion', onEvento);
      window.addEventListener('lune-ready', conectar);
      conectar();
      return () => {
        window.removeEventListener('lune-aprobacion', onEvento);
        window.removeEventListener('lune-ready', conectar);
        if (puente) {
          try { puente.aprobacion_pedida.disconnect(encolar); } catch (e) {}
          try { if (puente.aprobacion_resuelta) puente.aprobacion_resuelta.disconnect(quitar); } catch (e) {}
        }
      };
    }, []);
    const actual = cola[0];
    if (!actual) return null;
    return (
      <AprobacionModal key={actual.id} pendiente={actual} enCola={cola.length - 1}
        onResolver={(id) => setCola((c) => c.filter((x) => x.id !== id))} />
    );
  }

  function demoAprobacion() {
    try {
      window.dispatchEvent(new CustomEvent('lune-aprobacion', { detail: {
        id: `demo-${Date.now()}`, herramienta: 'lanzar_app', riesgo: 'SISTEMA', origen: 'usuario',
        resumen: 'Abrir el Bloc de notas', args: { app: 'notepad' }, motivo: 'Abre programas en tu PC',
      } }));
    } catch (e) {}
  }

  Object.assign(window, {
    CompatCard,
    AvanzadoCard,
    AprobacionModal,
    AprobacionHost,
    LuneIA: {
      PRESETS, CONTEXTOS, DEFECTOS, NEUTROS, ATAJOS_COMPAT, TIMEOUT_APROBACION_S,
      presetDe, valoresMuestreo, valoresPreset, opcional, indiceContexto, esLocal, urlValida, avisoUrl,
      normalizarPrueba, normalizarPendiente, limpiar, formatearArgs, varianteRiesgo, demoAprobacion,
      // Para otros campos de clave (settings.jsx: OpenRouter, Telegram) con la máscara de get_config.
      textoInsertado, CampoClave,
    },
  });
})();
