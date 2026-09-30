/* Lune CD desktop — Baile con la música (cortes 5 y 6).
 *
 * BaileCard              Ajustes: bailar sola con la música (auto), sensibilidad (umbral), apps permitidas como
 *                        chips + «suenan ahora» (con «+» para permitirlas), cambiar de baile cada N s, notas ♪,
 *                        estado en vivo y Bailar/Parar.
 * window.LuneBaileWeb    para app.jsx y sidebar.jsx (la asistente de la barra baila):
 *   useBaile() → {estado, config, reloj, suscribir(fn)}   estado_json + señal baile_estado; config_baile (y el
 *                        evento de window 'lune-baile-config' cuando BaileCard guarda); reloj = crearReloj()
 *                        alimentado por la señal baile_pulso; suscribir(fn) → quitar: fn({bpm, fase, energia})
 *                        en cada pulso (≤ 2 por segundo) para mandarlo al módulo baileProc del avatar 3D.
 *   crearReloj(ahora?)   extrapola la fase entre pulsos (fase continua): LuneRitmo.crearReloj de ui_web/lune_ritmo.js
 *                        si está cargado (corrige con ±20 % de velocidad); si no, uno propio que corrige ≤ 0.2 por
 *                        pulso. → {pulso(bpm, fase, energia), beat(t), fase(t), bpm, energia, sincronizado, reiniciar()}
 *   transformVideo(beat, energia) → {dy, grados, escala, css}   baile del vídeo de la barra: bote de 0 a −6 px,
 *                        balanceo alterno de ±2° y un estirón en cada golpe (escala ≥ 1.06 para no ver bordes).
 *   rotulo(estado)       «♪ Spotify · 124 BPM»
 *   opcionesPagina(config, estado) → {estilo, cambiar, cambiarS, particulas}  (como nucleo/baile.opciones_pagina)
 * Puente: window.luneMusica (ui/puente_musica.py). BaileCard guarda al momento (config.set en Python).
 * Sin puente (navegador), demo local. Se registra solo: Object.assign(window, {BaileCard, LuneBaileWeb}).
 */
(function () {
  const { useState, useEffect, useRef, useMemo } = React;

  // ── Puente: window.luneMusica ──
  const puente = () => window.luneMusica || null;
  function conectar(senal, fn) {
    const p = puente();
    const s = p && p[senal];
    if (!s || typeof s.connect !== 'function') return () => {};
    try { s.connect(fn); } catch (err) { return () => {}; }
    return () => { try { s.disconnect(fn); } catch (err) { /* ya no está */ } };
  }
  function leer(j, def) {
    if (j == null) return def;
    if (typeof j === 'object') return j;
    try { const o = JSON.parse(j); return o == null ? def : o; } catch (e) { return def; }
  }
  function pedir(nombre, args, cb) {
    const p = puente();
    if (p && typeof p[nombre] === 'function') {
      try { p[nombre](...(args || []), (r) => { if (cb) cb(r); }); return 'puente'; } catch (e) { return ''; }
    }
    if (p) return '';
    const f = DEMO[nombre];
    if (typeof f !== 'function') return '';
    const r = f(...(args || []));
    if (cb) cb(r);
    return 'demo';
  }
  function alListo(fn) {
    if (puente()) { fn(); return () => {}; }
    window.addEventListener('lune-ready', fn, { once: true });
    return () => window.removeEventListener('lune-ready', fn);
  }
  function crearRetardo(fn, ms) {
    let timer = null, pendiente = {};
    return (parcial) => {
      pendiente = { ...pendiente, ...(parcial || {}) };
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = null; const p = pendiente; pendiente = {}; fn(p); }, ms);
    };
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const fin = Number.isFinite;
  const acotar = (v, a, b) => Math.min(b, Math.max(a, v));
  const APPS_DEFECTO = ['Spotify', 'MusicBee', 'foobar2000', 'vlc', 'AppleMusic'];
  const BAILE_DEFECTO = { auto: true, umbral: 0.05, apps: APPS_DEFECTO, cambiar: false, cambiar_s: 15, particulas: true };
  const ESTADO_DEFECTO = { bailando: false, origen: '', musica: false, app: '', estilo: '', bpm: 0, energia: 0, auto: true,
    pausado_hasta_silencio: false, disponible: false };
  const ESTILOS = { rebote: 'Rebote', vaiven: 'Vaivén', brazos_arriba: 'Brazos arriba', palmas: 'Palmas', cadera: 'Cadera',
    cabeceo: 'Cabeceo', puno_alterno: 'Puño alterno', paso_lateral: 'Paso lateral' };
  const MAX_APPS = 30;
  const APP_OK = /^[\w .\-()]{1,60}$/;

  /** «  Spotify.EXE » → «Spotify»; null si trae ruta, comodines o está vacío (como ui/puente_musica.py). */
  function normalizarApp(nombre) {
    if (typeof nombre !== 'string') return null;
    let s = nombre.trim();
    if (!s || /[\\/:]/.test(s)) return null;
    if (/\.exe$/i.test(s)) s = s.slice(0, -4).trim();
    if (!s || !APP_OK.test(s) || !/[A-Za-z0-9]/.test(s)) return null;
    return s;
  }
  function listaApps(v, max = MAX_APPS) {
    const out = [], vistos = new Set();
    for (const a of Array.isArray(v) ? v : []) {
      const n = normalizarApp(a);
      if (n && !vistos.has(n.toLowerCase())) { vistos.add(n.toLowerCase()); out.push(n); }
      if (out.length >= max) break;
    }
    return out;
  }
  const incluye = (lista, app) => lista.some((a) => a.toLowerCase() === String(app).toLowerCase());
  function normalizarEstado(o) {
    const r = o && typeof o === 'object' ? o : {};
    const bpm = Number(r.bpm), en = Number(r.energia);
    const bailando = r.bailando === true;
    return {
      bailando, origen: bailando && (r.origen === 'auto' || r.origen === 'manual') ? r.origen : '', musica: r.musica === true,
      app: normalizarApp(r.app || '') || '', estilo: ESTILOS[r.estilo] ? r.estilo : '',
      bpm: fin(bpm) && bpm > 0 ? acotar(bpm, 40, 250) : 0, energia: fin(en) ? acotar(en, 0, 1) : 0,
      auto: r.auto !== false, pausado_hasta_silencio: r.pausado_hasta_silencio === true, disponible: r.disponible === true,
    };
  }
  function normalizarPulso(o) {
    const r = o && typeof o === 'object' ? o : null;
    if (!r) return null;
    const bpm = Number(r.bpm), fase = Number(r.fase), en = Number(r.energia);
    if (!fin(bpm) || !fin(fase)) return null;
    return { bpm: acotar(bpm, 40, 250), fase: ((fase % 1) + 1) % 1, energia: fin(en) ? acotar(en, 0, 1) : 0.5 };
  }
  function normalizarConfig(o) {
    const r = o && typeof o === 'object' ? o : {};
    const out = { ...BAILE_DEFECTO, apps: Array.isArray(r.apps) ? listaApps(r.apps) : APPS_DEFECTO.slice() };
    ['auto', 'cambiar', 'particulas'].forEach((k) => { if (typeof r[k] === 'boolean') out[k] = r[k]; });
    const u = Number(r.umbral); if (fin(u)) out.umbral = acotar(u, 0.02, 0.6);
    const c = Number(r.cambiar_s); if (fin(c)) out.cambiar_s = Math.round(acotar(c, 5, 120));
    return out;
  }
  /** Opciones para luneBailar / baileProc.bailar (las mismas claves que nucleo/baile.opciones_pagina). */
  function opcionesPagina(config, estado) {
    const c = normalizarConfig(config);
    const o = { cambiar: c.cambiar, cambiarS: c.cambiar_s, particulas: c.particulas };
    if (estado && ESTILOS[estado.estilo]) o.estilo = estado.estilo;
    return o;
  }
  function rotulo(estado) {
    const e = normalizarEstado(estado);
    if (!e.bailando) return '';
    const partes = [e.app || (e.musica ? 'música' : 'a su aire')];
    if (e.bpm) partes.push(`${Math.round(e.bpm)} BPM`);
    return `♪ ${partes.join(' · ')}`;
  }

  /** Reloj del pulso: la página no recibe más de 2 pulsos por segundo; entre uno y otro extrapola con el
   *  BPM. `beat(t)` = pulsos transcurridos (continuo). Con ui_web/lune_ritmo.js cargado (index.html) usa
   *  LuneRitmo.crearReloj (corrige la fase cambiando la velocidad ±20 %, sin saltos, el mismo reloj que las
   *  páginas de la asistente); sin él, uno propio que corrige la fase como mucho 0.2 por pulso. */
  function crearReloj(ahora) {
    const reloj = typeof ahora === 'function' ? ahora : () => Date.now() / 1000;
    const R = window.LuneRitmo;
    if (R && typeof R.crearReloj === 'function') {
      try {
        const r = R.crearReloj({ bpm: 120, ahora: reloj });
        if (r && typeof r.pulso === 'function' && typeof r.avanzar === 'function') return adaptarRitmo(r, reloj);
      } catch (e) { /* lune_ritmo.js viejo o roto: el reloj propio */ }
    }
    return relojPropio(reloj);
  }
  function adaptarRitmo(r, reloj) {
    let tiene = false;
    let ultimo = { pulsos: 0, fase: 0, bpm: 120, energia: 0.5 };
    const en = (t) => { const e = r.avanzar(fin(t) ? t : reloj()); if (e && fin(e.pulsos)) ultimo = e; return ultimo; };
    const actual = () => { try { const e = typeof r.estado === 'function' ? r.estado() : null; return e && fin(e.bpm) ? e : ultimo; } catch (err) { return ultimo; } };
    return {
      ritmo: true,
      pulso(b, f, e) { tiene = true; r.pulso(Number(b), Number(f), Number(e), reloj()); },
      beat: (t) => en(t).pulsos,
      fase: (t) => { const p = en(t).pulsos; return p - Math.floor(p); },
      get bpm() { return actual().bpm; },
      get energia() { return actual().energia; },
      get sincronizado() { return tiene; },
      reiniciar() { tiene = false; try { if (typeof r.reiniciar === 'function') r.reiniciar(); } catch (err) { /* sigue */ } },
    };
  }
  function relojPropio(reloj) {
    let bpm = 120, energia = 0.5, beat0 = 0, t0 = reloj(), tiene = false;
    const beatEn = (t) => beat0 + ((t - t0) * bpm) / 60;
    return {
      pulso(b, f, e) {
        const t = reloj();
        const nb = fin(Number(b)) && Number(b) > 0 ? acotar(Number(b), 40, 250) : 120;
        const nf = fin(Number(f)) ? ((Number(f) % 1) + 1) % 1 : 0;
        const ne = fin(Number(e)) ? acotar(Number(e), 0, 1) : energia;
        if (!tiene) { tiene = true; beat0 = nf; }
        else {
          const actual = beatEn(t);
          let dif = nf - (actual - Math.floor(actual));
          dif -= Math.round(dif);                              // camino corto: −0.5..0.5
          beat0 = actual + acotar(dif, -0.2, 0.2);
        }
        t0 = t; bpm = nb; energia = ne;
      },
      beat: (t) => beatEn(fin(t) ? t : reloj()),
      fase(t) { const b = beatEn(fin(t) ? t : reloj()); return b - Math.floor(b); },
      get bpm() { return bpm; },
      get energia() { return energia; },
      get sincronizado() { return tiene; },
      reiniciar() { tiene = false; bpm = 120; energia = 0.5; beat0 = 0; t0 = reloj(); },
    };
  }
  /** Baile del vídeo de la barra en el pulso `beat` (continuo): el golpe cae en los enteros. */
  function transformVideo(beat, energia) {
    const b = fin(Number(beat)) ? Number(beat) : 0;
    const e = 0.4 + 0.6 * (fin(Number(energia)) ? acotar(Number(energia), 0, 1) : 0.5);
    const f = b - Math.floor(b);
    const dy = -6 * e * Math.sin(Math.PI * f);                // arriba entre golpes, abajo en el golpe
    const grados = 2 * e * Math.sin(Math.PI * b);             // un golpe a cada lado
    const estiron = Math.pow(1 - f, 3);                       // justo en el golpe
    const escala = 1.06 + 0.02 * e * estiron;
    const r = (x, n = 3) => Math.round(x * 10 ** n) / 10 ** n;
    return { dy: r(dy, 2), grados: r(grados), escala: r(escala, 4),
      css: `translateY(${r(dy, 2)}px) rotate(${r(grados)}deg) scale(${r(escala, 4)})` };
  }

  // ── Demo sin backend ───────────────────────────────────────────────────────
  const DEMO = (function () {
    let cfg = normalizarConfig(null);
    const sonando = ['Spotify', 'chrome'];
    const resp = () => JSON.stringify({ ok: true, error: '', apps: cfg.apps.slice() });
    return {
      estado_json: () => JSON.stringify({ ...ESTADO_DEFECTO, auto: cfg.auto }),
      config_baile: () => JSON.stringify(cfg),
      config_baile_guardar(j) { cfg = normalizarConfig({ ...cfg, ...leer(j, {}) }); return JSON.stringify({ ok: true, error: '', estado: cfg }); },
      apps_audio: () => JSON.stringify(sonando),
      app_permitir(n) {
        const a = normalizarApp(n);
        if (!a) return JSON.stringify({ ok: false, error: 'Solo el nombre del programa (por ejemplo Spotify), sin rutas.', apps: cfg.apps });
        if (!incluye(cfg.apps, a)) cfg = { ...cfg, apps: [...cfg.apps, a] };
        return resp();
      },
      app_quitar(n) { cfg = { ...cfg, apps: cfg.apps.filter((a) => a.toLowerCase() !== String(n).toLowerCase()) }; return resp(); },
      bailar: () => false,
      parar: () => false,
    };
  })();

  // ── Estilos propios ────────────────────────────────────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-ocio-baile-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-ocio-baile-css';
      st.textContent = `
        .ln-bl-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-bl-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-bl-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-bl-estado.is-on{ border-left-color:var(--yellow-500); box-shadow:inset 0 0 18px rgb(var(--yellow-500-rgb, 255 224 0) / .08); }
        .ln-bl-estado-tx{ flex:1; min-width:180px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-bl-apps{ display:flex; flex-wrap:wrap; gap:6px; }
        .ln-bl-app{ display:inline-flex; align-items:center; gap:6px; font-family:var(--font-mono); font-size:11.5px; color:var(--cyan-300);
          background:var(--ink-800); border:var(--bw) solid var(--cyan-700); padding:3px 4px 3px 10px; clip-path:var(--clip-tr); }
        .ln-bl-app.is-suena{ color:var(--yellow-400); border-color:var(--yellow-600); background:rgb(var(--yellow-500-rgb, 255 224 0) / .06); }
        .ln-bl-app.is-permitida{ color:var(--text-muted); border-color:var(--ink-500); padding-right:10px; }
        .ln-bl-app button{ appearance:none; -webkit-appearance:none; border:none; background:none; color:var(--text-dim); cursor:pointer; font:inherit; padding:0 6px; }
        .ln-bl-app button:hover{ color:var(--yellow-500); }
        .ln-bl-add{ display:flex; gap:8px; align-items:flex-end; margin-top:10px; flex-wrap:wrap; }
        .ln-bl-add .lune-field{ flex:1; min-width:180px; }
        .ln-bl-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-bl-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-bl-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-bl-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-bl-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-bl-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-bl-msg.is-error{ color:var(--yellow-500); }
        .ln-bl-msg.is-ok{ color:var(--cyan-300); }
        .ln-baile-rotulo{ position:absolute; left:8px; right:8px; top:8px; z-index:2; pointer-events:none; text-align:center;
          font-family:var(--font-mono); font-weight:700; font-size:10.5px; letter-spacing:.06em; color:var(--ink-950); background:var(--yellow-500);
          padding:3px 8px; clip-path:var(--clip-tr); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
          box-shadow:3px 3px 0 rgb(var(--ink-950-rgb, 5 7 15) / .7); animation:ln-baile-in .3s var(--ease-snap); }
        @keyframes ln-baile-in{ from{ opacity:0; transform:translateY(-8px) skewX(-8deg); } to{ opacity:1; transform:none; } }
        .ln-asistente-stage video.is-bailando{ transform-origin:50% 100%; will-change:transform; }
        @media (prefers-reduced-motion: reduce){ .ln-baile-rotulo{ animation:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // ── Hook para app.jsx / sidebar.jsx ────────────────────────────────────────
  function useBaile() {
    const vivo = useRef(true);
    const [estado, setEstado] = useState(ESTADO_DEFECTO);
    const [config, setConfig] = useState(BAILE_DEFECTO);
    const reloj = useRef(null);
    if (!reloj.current) reloj.current = crearReloj();
    const oyentes = useRef(null);
    if (!oyentes.current) oyentes.current = new Set();
    const api = useRef(null);
    if (!api.current) {
      api.current = {
        suscribir(fn) {
          if (typeof fn !== 'function') return () => {};
          oyentes.current.add(fn);
          return () => { oyentes.current.delete(fn); };
        },
      };
    }
    useEffect(() => {
      vivo.current = true;
      inyectarEstilos();
      const quitar = [];
      const alEstado = (j) => {
        const e = normalizarEstado(leer(j, {}));
        if (!vivo.current) return;
        if (!e.bailando) reloj.current.reiniciar();
        setEstado(e);
      };
      const alPulso = (j) => {
        const p = normalizarPulso(leer(j, null));
        if (!p || !vivo.current) return;
        reloj.current.pulso(p.bpm, p.fase, p.energia);
        for (const fn of [...oyentes.current]) { try { fn(p); } catch (e) { /* un oyente roto no para a los demás */ } }
      };
      const alConfig = (ev) => {
        if (!vivo.current) return;
        if (ev && ev.detail) setConfig(normalizarConfig(ev.detail));
        else pedir('config_baile', [], (j) => { if (vivo.current) setConfig(normalizarConfig(leer(j, {}))); });
      };
      const cablear = () => {
        quitar.push(conectar('baile_estado', alEstado), conectar('baile_pulso', alPulso));
        pedir('estado_json', [], alEstado);
        pedir('config_baile', [], (j) => { if (vivo.current) setConfig(normalizarConfig(leer(j, {}))); });
      };
      window.addEventListener('lune-baile-config', alConfig);
      const q = alListo(cablear);
      return () => {
        vivo.current = false;
        q();
        quitar.splice(0).forEach((f) => f());
        window.removeEventListener('lune-baile-config', alConfig);
      };
    }, []);
    return { estado, config, reloj: reloj.current, suscribir: api.current.suscribir };
  }

  // ── BaileCard ──────────────────────────────────────────────────────────────
  function Deslizador({ id, label, min, max, step = 1, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-bl-range">
        <div className="ln-bl-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-bl-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }
  const Msg = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-bl-msg${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);
  const avisarConfig = (c) => { try { window.dispatchEvent(new window.CustomEvent('lune-baile-config', { detail: c })); } catch (e) { /* sin eventos */ } };
  function textoEstado(e) {
    if (!e.disponible) return 'El baile no está en marcha (arranca con los servicios de escritorio).';
    if (e.bailando) {
      const quien = e.origen === 'manual' ? 'Bailando porque se lo pediste' : 'Bailando con la música';
      const det = [e.app, e.bpm ? `${Math.round(e.bpm)} BPM` : '', ESTILOS[e.estilo] || ''].filter(Boolean).join(' · ');
      return det ? `${quien}: ${det}.` : `${quien}.`;
    }
    if (e.pausado_hasta_silencio) return 'En pausa hasta que se calle la música.';
    if (e.musica) return `Suena música${e.app ? ` (${e.app})` : ''}, pero ahora no puede bailar.`;
    return e.auto ? 'Quieta: esperando música de una app permitida.' : 'Quieta (no baila sola: está apagado).';
  }

  function BaileCard() {
    const { Card, Button, Switch, Badge, Input } = window.LUNE;
    const { estado } = useBaile();
    const vivo = useRef(true);
    const [cfg, setCfg] = useState(BAILE_DEFECTO);
    const [suenan, setSuenan] = useState([]);
    const [manual, setManual] = useState('');
    const [msg, setMsg] = useState(null);
    useEffect(() => {
      vivo.current = true;
      const quitar = [];
      const alApps = (j) => { const l = leer(j, []); if (vivo.current) setSuenan(listaApps(Array.isArray(l) ? l : [], 50)); };
      const cablear = () => {
        pedir('config_baile', [], (j) => { if (vivo.current) setCfg(normalizarConfig(leer(j, {}))); });
        pedir('apps_audio', [], alApps);
        quitar.push(conectar('apps_cambio', alApps));
      };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { vivo.current = false; q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    const guardar = (parcial) => {
      setCfg((c) => normalizarConfig({ ...c, ...parcial }));
      const via = pedir('config_baile_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.estado) { const c = normalizarConfig(r.estado); setCfg(c); avisarConfig(c); }
        setMsg(r && r.ok ? { texto: 'Guardado.', ok: true } : { texto: (r && r.error) || 'No pude guardar.', error: true });
      });
      if (!via) setMsg({ texto: 'El baile no está disponible.', error: true });
    };
    const diferido = useMemo(() => crearRetardo((p) => guardar(p), 350), []);
    const cambiarApp = (ranura, nombre) => {
      const n = normalizarApp(nombre);
      if (!n) { setMsg({ texto: 'Escribe solo el nombre del programa (por ejemplo Spotify), sin rutas.', error: true }); return false; }
      if (ranura === 'app_permitir' && incluye(cfg.apps, n)) { setMsg({ texto: `${n} ya está en la lista.`, ok: true }); return false; }
      if (ranura === 'app_permitir' && cfg.apps.length >= MAX_APPS) { setMsg({ texto: `Como mucho ${MAX_APPS} apps.`, error: true }); return false; }
      pedir(ranura, [n], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && Array.isArray(r.apps)) { const c = { ...cfg, apps: listaApps(r.apps) }; setCfg(c); avisarConfig(c); }
        setMsg(r && r.ok ? { texto: ranura === 'app_permitir' ? `${n} cuenta como música.` : `${n} ya no cuenta.`, ok: true }
          : { texto: (r && r.error) || 'No pude guardar.', error: true });
      });
      return true;
    };
    const bailar = () => {
      const demo = !puente();
      pedir('bailar', [0], (ok) => {
        if (!vivo.current) return;
        setMsg(demo ? { texto: 'Demo: el baile es de la app.', error: true }
          : ok ? null : { texto: 'Ahora no puede bailar (¿dormida, un juego, la pantalla grande o una alarma?).', error: true });
      });
    };
    const parar = () => pedir('parar', [], (ok) => { if (vivo.current && !ok) setMsg({ texto: 'No estaba bailando.', error: true }); });
    const nuevas = suenan.filter((a) => !incluye(cfg.apps, a));
    const Icono = window.IconVolume || (() => null);
    return (
      <Card id="aj-baile" eyebrow={<><Icono width={13} height={13}/> Ocio · Baile</>} title="Baile con la música" tone="yellow" tick={estado.bailando}>
        <p className="ln-bl-nota">
          Lune mira el volumen de cada app del mezclador de Windows (sin grabar el sonido) y, si suena una de tu lista, baila al ritmo.
          No se despierta por la música: si duerme, baila al despertar.
        </p>
        <div className={`ln-bl-estado${estado.bailando ? ' is-on' : ''}`}>
          <Badge variant={estado.bailando ? 'yellow' : 'ink'} outline={!estado.bailando}>{estado.bailando ? '♪ BAILANDO' : 'quieta'}</Badge>
          <span className="ln-bl-estado-tx">{textoEstado(estado)}</span>
          {estado.bailando
            ? <Button size="sm" variant="ghost" onClick={parar}>Parar</Button>
            : <Button size="sm" variant="secondary" onClick={bailar}>Bailar</Button>}
        </div>
        <div className="ln-bl-sub">Con la música</div>
        <div className="ln-toggle-row">
          <Switch label="Bailar sola cuando suena música" checked={cfg.auto} onChange={(e) => guardar({ auto: !!e.target.checked })} accent="yellow" />
          <Switch label="Notas ♪ mientras baila" checked={cfg.particulas} onChange={(e) => guardar({ particulas: !!e.target.checked })} />
          <Switch label="Cambiar de baile" checked={cfg.cambiar} onChange={(e) => guardar({ cambiar: !!e.target.checked })} accent="blue" />
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-settings-grid">
          <Deslizador id="f-baile-umbral" label="Sensibilidad" min={2} max={60} value={Math.round(cfg.umbral * 100)}
            fmt={(v) => `${v} %`} hint="Volumen mínimo de la app para contar como música (menos = baila con la música más baja)."
            disabled={!cfg.auto} onChange={(v) => { setCfg((c) => ({ ...c, umbral: v / 100 })); diferido({ umbral: v / 100 }); }} />
          <Deslizador id="f-baile-cambiar" label="Cambiar de baile cada" min={5} max={120} value={cfg.cambiar_s}
            fmt={(v) => `${v} s`} disabled={!cfg.cambiar}
            onChange={(v) => { setCfg((c) => ({ ...c, cambiar_s: v })); diferido({ cambiar_s: v }); }} />
        </div>
        <div className="ln-bl-sub">Apps que cuentan como música</div>
        <div className="ln-bl-apps">
          {cfg.apps.length === 0 && <span className="ln-bl-msg" style={{ margin: 0 }}>Ninguna: solo baila si se lo pides.</span>}
          {cfg.apps.map((a) => (
            <span className={`ln-bl-app${incluye(suenan, a) ? ' is-suena' : ''}`} key={a}>{incluye(suenan, a) ? `♪ ${a}` : a}
              <button type="button" aria-label={`Quitar ${a}`} title="Quitar" onClick={() => cambiarApp('app_quitar', a)}>✕</button>
            </span>
          ))}
        </div>
        <div className="ln-bl-sub">Suenan ahora</div>
        <div className="ln-bl-apps">
          {suenan.length === 0 && <span className="ln-bl-msg" style={{ margin: 0 }}>Nada suena ahora mismo.</span>}
          {suenan.map((a) => (incluye(cfg.apps, a)
            ? <span className="ln-bl-app is-permitida" key={a}>{a} ✓</span>
            : <span className="ln-bl-app" key={a}>{a}
                <button type="button" aria-label={`Permitir ${a}`} title="Que cuente como música" onClick={() => cambiarApp('app_permitir', a)}>＋</button>
              </span>))}
          <Button size="sm" variant="ghost" onClick={() => pedir('apps_audio', [], (j) => { const l = leer(j, []); if (vivo.current) setSuenan(listaApps(Array.isArray(l) ? l : [], 50)); })}>Refrescar</Button>
        </div>
        {nuevas.length > 0 && <p className="ln-bl-nota" style={{ marginTop: 8 }}>Pulsa ＋ en una app para que cuente como música.</p>}
        <div className="ln-bl-add">
          <Input id="f-baile-app" label="O escribe el programa" placeholder="Spotify" value={manual} maxLength={60}
            onChange={(e) => setManual(e.target.value)} />
          <Button size="sm" variant="ghost" disabled={!manual.trim()} onClick={() => { if (cambiarApp('app_permitir', manual)) setManual(''); }}>Añadir</Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  Object.assign(window, {
    BaileCard,
    LuneBaileWeb: {
      useBaile, crearReloj, transformVideo, rotulo, opcionesPagina, normalizarApp, listaApps, normalizarEstado,
      normalizarPulso, normalizarConfig, ESTILOS,
    },
  });
})();
