/* Lune CD desktop — Reproductor de bailes MMD/VRMA (corte 9).
 *
 * BailesPanel   vista «bailes» (app.jsx): el reproductor (⏮ ▶/⏸ ⏹ ⏭, progreso de solo lectura, «al terminar»:
 *               parar / siguiente / repetir / aleatorio, en el sitio y volumen), la biblioteca (buscador, favoritos,
 *               «al azar», bailar, ajustes por baile: sincronía ±500 ms, ángulo de los brazos 25–45° y en el sitio;
 *               quitar con confirmación: se mueve a bailes/.quitados), importar (diálogo de archivos de la app),
 *               abrir la carpeta y el aviso «En 2D mi figura no tiene esqueleto: bailo a mi manera» con la animada o
 *               los sprites.
 * BailesCard    Ajustes: volumen, al terminar, en el sitio, abrir la carpeta y «Abrir mis bailes» (evento de window
 *               'lune-vista' {detail: 'bailes'}).
 * window.LuneBailesWeb   utilidades puras (tests): normalizarBaile, normalizarLista, normalizarEstado, textoEstado,
 *               mmss, tiempoVisible, AL_TERMINAR, AVISO_SIN_ESQUELETO.
 * Puente: window.luneEscenario (ui/puente_escenario.py). La página NUNCA manda rutas: los bailes van por su id
 * (12 hex) e importar abre el diálogo de la app. Los títulos vienen de nombres de archivo: siempre como texto.
 * Sin puente (navegador), una demo local que no suena. Se registra solo: Object.assign(window, {BailesPanel,
 * BailesCard, LuneBailesWeb}).
 */
(function () {
  const { useState, useEffect, useRef, useMemo } = React;

  // ── Puente: window.luneEscenario (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneEscenario || null;
  const DEMO_SENALES = {};
  function conectar(senal, fn) {
    const p = puente();
    if (!p) {                                          // demo: señales locales
      const s = (DEMO_SENALES[senal] = DEMO_SENALES[senal] || new Set());
      s.add(fn);
      return () => s.delete(fn);
    }
    const s = p[senal];
    if (!s || typeof s.connect !== 'function') return () => {};
    try { s.connect(fn); } catch (err) { return () => {}; }
    return () => { try { s.disconnect(fn); } catch (err) { /* ya no está */ } };
  }
  function emitirDemo(senal, valor) {
    const s = DEMO_SENALES[senal];
    if (s) [...s].forEach((f) => { try { f(valor); } catch (e) { /* sigue */ } });
  }
  function leer(j, def) {
    if (j == null) return def;
    if (typeof j === 'object') return j;
    try { const o = JSON.parse(j); return o == null ? def : o; } catch (e) { return def; }
  }
  /** Llama a la ranura `nombre` del puente o, sin él, a la de la demo. → 'puente' | 'demo' | '' */
  function pedir(nombre, args, cb) {
    const p = puente();
    if (p && typeof p[nombre] === 'function') {
      try { p[nombre](...(args || []), (r) => { if (cb) cb(r); }); return 'puente'; } catch (e) { return ''; }
    }
    if (p) return '';                                  // backend viejo sin esa ranura
    const f = DEMO[nombre];
    if (typeof f !== 'function') return '';
    const r = f(...(args || []));
    if (cb) cb(r);
    return 'demo';
  }
  /** fn ahora si ya hay puente; si no, cuando llegue 'lune-ready'. → quitar */
  function alListo(fn) {
    if (puente()) { fn(); return () => {}; }
    window.addEventListener('lune-ready', fn, { once: true });
    return () => window.removeEventListener('lune-ready', fn);
  }
  /** Llama `ms` después del último cambio, con todos los cambios juntos ({a} + {b} = {a, b}). */
  function crearRetardo(fn, ms) {
    let timer = null, pendiente = {};
    return (parcial) => {
      pendiente = { ...pendiente, ...(parcial || {}) };
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = null; const p = pendiente; pendiente = {}; fn(p); }, ms);
    };
  }
  function irAVista(v) {
    try { window.dispatchEvent(new window.CustomEvent('lune-vista', { detail: v })); } catch (e) { /* sin eventos */ }
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const fin = Number.isFinite;
  const acotar = (v, a, b) => Math.min(b, Math.max(a, v));
  const entero = (v) => (typeof v === 'number' && fin(v) && Math.round(v) === v ? v : null);
  const numEn = (v, a, b) => (typeof v === 'number' && fin(v) && v >= a && v <= b ? v : null);
  const txt = (v, max = 80) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f​-‏‪-‮⁦-⁩]/g, '').trim().slice(0, max) : '');
  const ID_OK = /^[0-9a-f]{12}$/;
  const FASES = ['parado', 'cargando', 'listo', 'sonando', 'pausado', 'saliendo', 'error'];
  const MODOS = ['vrm', 'animado', 'sprites'];
  const AL_TERMINAR = [['parar', 'Parar'], ['siguiente', 'Siguiente'], ['repetir', 'Repetir'], ['aleatorio', 'Al azar']];
  const T_MAX = 7200;
  const MAX_BAILES = 500;
  const MAX_BUSQUEDA = 60;
  const AVISO_SIN_ESQUELETO = 'En 2D mi figura no tiene esqueleto: bailo a mi manera (suena la canción y bailo al ritmo).';
  const ESTADO_DEFECTO = { fase: 'parado', id: '', titulo: '', autor: '', autor_mmd: '', t: 0, total: 0, modo: '',
    al_terminar: 'parar', volumen: 0.25, en_el_sitio: true, error: '', analizando: false, pausado: false, cedida: false,
    pendiente: false, modo_asistente: '', sin_esqueleto: false, importando: false, servicio: false };

  function normalizarBaile(o) {
    const r = o && typeof o === 'object' ? o : null;
    if (!r || !ID_OK.test(String(r.id || ''))) return null;
    const dur = numEn(r.duracion, 0, T_MAX);
    const off = entero(r.offset_ms);
    const brazo = numEn(r.brazo_a_grados, 25, 45);
    const bpm = numEn(r.bpm, 40, 240);
    return {
      id: r.id, titulo: txt(r.titulo) || r.id, tipo: ['vmd', 'vrma'].includes(r.tipo) ? r.tipo : '',
      autor_cancion: txt(r.autor_cancion), autor_mmd: txt(r.autor_mmd), duracion: dur === null ? null : dur,
      audio: r.audio === true, favorito: r.favorito === true, desactivado: r.desactivado === true,
      problema: txt(r.problema, 200), aviso: txt(r.aviso, 200),
      offset_ms: off !== null && off >= -500 && off <= 500 ? off : 0, brazo_a_grados: brazo === null ? 35 : brazo,
      en_el_sitio: typeof r.en_el_sitio === 'boolean' ? r.en_el_sitio : null, bpm: bpm === null ? null : bpm,
    };
  }
  /** {bailes, servicio} o una lista → {bailes: [...válidos, sin repetir, ≤ 500], servicio} */
  function normalizarLista(o) {
    const r = Array.isArray(o) ? { bailes: o, servicio: true } : (o && typeof o === 'object' ? o : {});
    const out = [], vistos = new Set();
    for (const x of Array.isArray(r.bailes) ? r.bailes : []) {
      const b = normalizarBaile(x);
      if (!b || vistos.has(b.id)) continue;
      vistos.add(b.id);
      out.push(b);
      if (out.length >= MAX_BAILES) break;
    }
    return { bailes: out, servicio: r.servicio === true };
  }
  function normalizarEstado(o) {
    const r = o && typeof o === 'object' ? o : {};
    const modoM = MODOS.includes(r.modo_asistente) ? r.modo_asistente : '';
    const t = numEn(r.t, 0, T_MAX), total = numEn(r.total, 0, T_MAX), vol = numEn(r.volumen, 0, 1);
    return {
      fase: FASES.includes(r.fase) ? r.fase : 'parado', id: ID_OK.test(String(r.id || '')) ? r.id : '',
      titulo: txt(r.titulo), autor: txt(r.autor), autor_mmd: txt(r.autor_mmd),
      t: t === null ? 0 : t, total: total === null ? 0 : total, modo: MODOS.includes(r.modo) ? r.modo : '',
      al_terminar: AL_TERMINAR.some(([k]) => k === r.al_terminar) ? r.al_terminar : 'parar',
      volumen: vol === null ? 0.25 : vol, en_el_sitio: r.en_el_sitio !== false, error: txt(r.error, 300),
      analizando: r.analizando === true, pausado: r.pausado === true, cedida: r.cedida === true,
      pendiente: r.pendiente === true, modo_asistente: modoM,
      sin_esqueleto: r.sin_esqueleto === true || modoM === 'animado' || modoM === 'sprites',
      importando: r.importando === true, servicio: r.servicio === true,
    };
  }
  function mmss(s) {
    const t = Math.max(0, Math.floor(Number(s) || 0));
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
  }
  /** El tiempo a la vista: el último que dio Python y, sonando, lo que pasó desde entonces (≤ total). */
  function tiempoVisible(e, recibidoMs, ahoraMs) {
    const extra = e.fase === 'sonando' && !e.pausado ? Math.max(0, (ahoraMs - recibidoMs) / 1000) : 0;
    const t = e.t + Math.min(extra, 2);                // Python la corrige cada segundo: sin saltos grandes
    return e.total > 0 ? Math.min(e.total, t) : t;
  }
  function textoEstado(e) {
    const titulo = e.titulo ? `«${e.titulo}»` : 'un baile';
    if (!e.servicio) return 'El reproductor necesita la app abierta.';
    if (e.fase === 'error') return e.error ? `No pude bailar: ${e.error}` : 'No pude bailar.';
    if (e.pendiente) return `Salgo al escritorio para bailar ${titulo}…`;
    if (e.fase === 'cargando') return `Preparando ${titulo}…${e.analizando ? ' (escuchando el ritmo)' : ''}`;
    if (e.cedida) return `En pausa mientras dura el juego, la alarma o la pantalla grande: ${titulo}.`;
    if (e.fase === 'pausado' || e.pausado) return `En pausa: ${titulo}.`;
    if (['sonando', 'listo', 'saliendo'].includes(e.fase)) return `Bailando ${titulo}${e.autor ? ` · ${e.autor}` : ''}.`;
    return 'Parada. Elige un baile de la lista.';
  }
  const puesto = (e) => e.pendiente || !['parado', 'error'].includes(e.fase);

  // ── Demo sin backend ───────────────────────────────────────────────────────
  const DEMO = (function () {
    const cfg = { volumen: 0.25, al_terminar: 'parar', en_el_sitio: true };
    let lista = [
      { id: '5e1b0a7a2c01', titulo: 'Senbonzakura', tipo: 'vmd', autor_cancion: 'Kurousa-P', autor_mmd: 'demo', duracion: 245,
        audio: true, favorito: true },
      { id: '9a3c11f00b22', titulo: 'Ievan Polkka', tipo: 'vmd', autor_cancion: 'Otomania', duracion: 150, audio: true },
      { id: 'c0ffee000033', titulo: 'Saludo (VRoid)', tipo: 'vrma', duracion: 4, audio: false },
    ];
    let actual = null, pausado = false;
    const estado = () => {
      const b = lista.find((x) => x.id === actual);
      return { ...ESTADO_DEFECTO, ...cfg, servicio: true, modo_asistente: 'vrm', fase: b ? (pausado ? 'pausado' : 'sonando') : 'parado',
        id: b ? b.id : '', titulo: b ? b.titulo : '', autor: b ? (b.autor_cancion || '') : '', total: b ? b.duracion : 0,
        pausado: !!b && pausado };
    };
    const emitir = () => emitirDemo('mmd_estado', JSON.stringify(estado()));
    const bailes = () => ({ bailes: lista, servicio: true });
    const paso = (d) => {
      const i = lista.findIndex((x) => x.id === actual);
      const n = lista[(i + d + lista.length) % lista.length];
      actual = n.id; pausado = false; emitir();
      return JSON.stringify({ ok: true, texto: `Demo: «${n.titulo}».`, estado: estado() });
    };
    return {
      bailes_lista(t) {
        const q = String(t || '').toLowerCase();
        return JSON.stringify({ bailes: lista.filter((b) => !q || `${b.titulo} ${b.autor_cancion || ''}`.toLowerCase().includes(q)), servicio: true });
      },
      bailes_refrescar() { emitirDemo('bailes_cambio', JSON.stringify(bailes())); return true; },
      mmd_estado_json: () => JSON.stringify(estado()),
      mmd_reproducir(id) {
        const b = lista.find((x) => x.id === id) || (!id && lista[0]);
        if (!b) return JSON.stringify({ ok: false, texto: 'Ese baile no existe.', estado: estado() });
        actual = b.id; pausado = false; emitir();
        return JSON.stringify({ ok: true, texto: `Demo: bailaría «${b.titulo}» en la app.`, estado: estado() });
      },
      mmd_pausa() { if (actual) pausado = !pausado; emitir(); return JSON.stringify({ ok: !!actual, estado: estado() }); },
      mmd_parar() { const ok = !!actual; actual = null; pausado = false; emitir(); return JSON.stringify({ ok, estado: estado() }); },
      mmd_siguiente: () => paso(1),
      mmd_anterior: () => paso(-1),
      mmd_config_guardar(j) {
        const o = leer(j, {});
        if (numEn(o.volumen, 0, 1) !== null) cfg.volumen = o.volumen;
        if (AL_TERMINAR.some(([k]) => k === o.al_terminar)) cfg.al_terminar = o.al_terminar;
        if (typeof o.en_el_sitio === 'boolean') cfg.en_el_sitio = o.en_el_sitio;
        return JSON.stringify({ ok: true, error: '', estado: estado() });
      },
      baile_meta_guardar(id, j) {
        const o = leer(j, {});
        lista = lista.map((b) => (b.id === id ? { ...b, ...o } : b));
        emitirDemo('bailes_cambio', JSON.stringify(bailes()));
        return JSON.stringify({ ok: true, texto: 'Guardado (demo).' });
      },
      baile_favorito(id, on) { lista = lista.map((b) => (b.id === id ? { ...b, favorito: !!on } : b)); emitirDemo('bailes_cambio', JSON.stringify(bailes())); return true; },
      baile_desactivar(id, on) { lista = lista.map((b) => (b.id === id ? { ...b, desactivado: !!on } : b)); emitirDemo('bailes_cambio', JSON.stringify(bailes())); return true; },
      bailes_importar: () => false,
      baile_quitar(id) {
        lista = lista.filter((b) => b.id !== id);
        if (actual === id) actual = null;
        emitirDemo('bailes_cambio', JSON.stringify(bailes()));
        return JSON.stringify({ ok: true, texto: 'Demo: lo quitaría (a bailes/.quitados).' });
      },
      bailes_abrir_carpeta: () => false,
    };
  })();

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-bailes-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-bailes-css';
      st.textContent = `
        .ln-bl-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-bl-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-bl-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-bl-estado.is-on{ border-left-color:var(--yellow-500); box-shadow:inset 0 0 18px rgb(var(--yellow-500-rgb, 255 224 0) / .08); }
        .ln-bl-estado-tx{ flex:1; min-width:200px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-bl-prog{ margin:12px 0 4px; }
        .ln-bl-prog-barra{ position:relative; height:8px; background:var(--ink-950); border:var(--bw) solid var(--ink-500); overflow:hidden; }
        .ln-bl-prog-lleno{ position:absolute; inset:0 auto 0 0; background:linear-gradient(90deg, var(--cyan-600), var(--cyan-400));
          box-shadow:0 0 12px rgb(var(--cyan-500-rgb, 0 229 255) / .45); }
        .ln-bl-prog-tx{ display:flex; justify-content:space-between; font-family:var(--font-mono); font-size:11px; color:var(--text-muted); margin-top:4px; }
        .ln-bl-mando{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:12px; }
        .ln-bl-mando .ln-bl-grande{ min-width:120px; }
        .ln-bl-botones{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
        .ln-bl-aviso{ margin:10px 0 0; padding:10px 12px; font-size:12px; line-height:1.5; color:var(--text);
          background:rgb(var(--yellow-500-rgb, 255 224 0) / .07); border:var(--bw) solid var(--yellow-600);
          border-left:var(--bw-bold) solid var(--yellow-500); clip-path:var(--clip-tr); }
        .ln-bl-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-bl-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-bl-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-bl-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-bl-buscar{ display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap; }
        .ln-bl-buscar .lune-field{ flex:1; min-width:200px; }
        .ln-bl-lista{ display:flex; flex-direction:column; gap:6px; margin-top:12px; }
        .ln-bl-fila{ display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center; padding:8px 10px;
          background:rgb(var(--ink-950-rgb, 5 7 15) / .55); border:var(--bw) solid var(--ink-500); clip-path:var(--clip-tr); }
        .ln-bl-fila.is-actual{ border-color:var(--cyan-500); box-shadow:inset 0 0 14px rgb(var(--cyan-500-rgb, 0 229 255) / .12); }
        .ln-bl-fila.is-off{ opacity:.62; }
        .ln-bl-estrella{ background:none; border:0; cursor:pointer; font-size:18px; line-height:1; color:var(--text-faint); padding:2px 4px; }
        .ln-bl-estrella.is-on{ color:var(--yellow-500); text-shadow:0 0 8px rgb(var(--yellow-500-rgb, 255 224 0) / .5); }
        .ln-bl-info{ min-width:0; }
        .ln-bl-titulo{ display:block; font-weight:700; color:var(--text-strong); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .ln-bl-meta{ display:flex; gap:8px; flex-wrap:wrap; font-family:var(--font-mono); font-size:11px; color:var(--text-muted); }
        .ln-bl-meta .is-mal{ color:var(--yellow-500); }
        .ln-bl-acc{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
        .ln-bl-ajustes{ grid-column:1 / -1; padding:10px 12px; margin-top:4px; border-left:var(--bw-bold) solid rgb(var(--cyan-500-rgb, 0 229 255) / .5);
          background:rgb(var(--ink-950-rgb, 5 7 15) / .45); display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; }
        .ln-bl-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-bl-msg.is-error{ color:var(--yellow-500); }
        .ln-bl-msg.is-ok{ color:var(--cyan-300); }
        .ln-bl-vacio{ font-size:12.5px; color:var(--text-dim); padding:10px 0; }
        @media (prefers-reduced-motion: reduce){ .ln-bl-prog-lleno{ transition:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // ── Piezas comunes ─────────────────────────────────────────────────────────
  const IconoBaile = (p) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
      <rect x="2" y="2" width="20" height="20" rx="2.18" /><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5" />
    </svg>
  );
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

  /** Estado del reproductor (mmd_estado) y config del reproductor con guardado diferido. */
  function useReproductor() {
    const vivo = useRef(true);
    const [e, setE] = useState(ESTADO_DEFECTO);
    const recibido = useRef(Date.now());
    const poner = (o) => { if (!vivo.current) return; recibido.current = Date.now(); setE(normalizarEstado(o)); };
    useEffect(() => {
      vivo.current = true;
      inyectarEstilos();
      const quitar = [];
      const al = (j) => poner(leer(j, {}));
      const cablear = () => { quitar.push(conectar('mmd_estado', al)); pedir('mmd_estado_json', [], al); };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { vivo.current = false; q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    return { e, poner, vivo, recibido };
  }
  function useConfigReproductor(poner, setMsg) {
    const [vol, setVol] = useState(null);                    // mientras se arrastra el deslizador
    const guardar = (parcial) => {
      const via = pedir('mmd_config_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (r && r.estado) poner(r.estado);
        if (setMsg && r && !r.ok) setMsg({ texto: txt(r.error, 200) || 'No pude guardar.', error: true });
      });
      if (!via && setMsg) setMsg({ texto: 'Esto no está disponible en esta versión de la app.', error: true });
    };
    const diferido = useMemo(() => crearRetardo((p) => { setVol(null); guardar(p); }, 350), []);
    const volumen = (v) => { setVol(v); diferido({ volumen: acotar(v, 0, 100) / 100 }); };
    return { vol, volumen, guardar };
  }
  function ControlesConfig({ e, cfg }) {
    const { Button, Switch } = window.LUNE;
    return (
      <>
        <div className="ln-bl-sub">Al terminar</div>
        <div className="ln-bl-botones" style={{ marginTop: 0 }} role="group" aria-label="Al terminar">
          {AL_TERMINAR.map(([k, t]) => (
            <Button key={k} size="sm" variant={e.al_terminar === k ? 'primary' : 'ghost'} aria-pressed={e.al_terminar === k}
              onClick={() => { if (e.al_terminar !== k) cfg.guardar({ al_terminar: k }); }}>{t}</Button>
          ))}
        </div>
        <div className="ln-toggle-row" style={{ marginTop: 12 }}>
          <Switch label="Bailar en el sitio (sin desplazarse)" checked={e.en_el_sitio}
            onChange={(ev) => cfg.guardar({ en_el_sitio: !!ev.target.checked })} />
        </div>
        <div style={{ height: 10 }} />
        <Deslizador id="f-bl-volumen" label="Volumen de la canción" min={0} max={100}
          value={cfg.vol === null ? Math.round(e.volumen * 100) : cfg.vol} fmt={(v) => `${v} %`}
          hint="Mientras Lune habla, la canción baja sola." onChange={cfg.volumen} />
      </>
    );
  }

  // ── BailesPanel (vista «bailes») ───────────────────────────────────────────
  function FilaBaile({ b, actual, abierto, onAbrir, onBailar, onMsg, alCambio }) {
    const { Button, Switch, Badge } = window.LUNE;
    const [off, setOff] = useState(b.offset_ms);
    const [brazo, setBrazo] = useState(b.brazo_a_grados);
    const [sitio, setSitio] = useState(b.en_el_sitio);
    const [confirmar, setConfirmar] = useState(false);
    const tConfirmar = useRef(null);
    useEffect(() => { setOff(b.offset_ms); setBrazo(b.brazo_a_grados); setSitio(b.en_el_sitio); }, [b.offset_ms, b.brazo_a_grados, b.en_el_sitio]);
    useEffect(() => () => { if (tConfirmar.current) clearTimeout(tConfirmar.current); }, []);
    const favorito = () => pedir('baile_favorito', [b.id, !b.favorito], (ok) => { if (ok) alCambio(); });
    const azar = (on) => pedir('baile_desactivar', [b.id, !on], (ok) => { if (ok) alCambio(); });
    const guardarAjustes = () => pedir('baile_meta_guardar', [b.id, JSON.stringify({ offset_ms: Math.round(off), brazo_a_grados: brazo, en_el_sitio: sitio })],
      (j) => { const r = leer(j, {}); onMsg(r && r.ok ? { texto: 'Ajustes del baile guardados.', ok: true } : { texto: txt(r && r.texto, 200) || 'No pude guardarlo.', error: true }); if (r && r.ok) alCambio(); });
    const quitar = () => {
      if (!confirmar) {
        setConfirmar(true);
        if (tConfirmar.current) clearTimeout(tConfirmar.current);
        tConfirmar.current = setTimeout(() => setConfirmar(false), 4000);
        return;
      }
      setConfirmar(false);
      pedir('baile_quitar', [b.id], (j) => { const r = leer(j, {}); onMsg({ texto: txt(r && r.texto, 200) || 'Hecho.', ok: !!(r && r.ok), error: !(r && r.ok) }); alCambio(); });
    };
    const autores = [b.autor_cancion, b.autor_mmd].filter(Boolean).join(' · ');
    return (
      <div className={`ln-bl-fila${actual ? ' is-actual' : ''}${b.desactivado ? ' is-off' : ''}`} data-id={b.id}>
        <button type="button" className={`ln-bl-estrella${b.favorito ? ' is-on' : ''}`} aria-pressed={b.favorito}
          aria-label={b.favorito ? `Quitar «${b.titulo}» de favoritos` : `Marcar «${b.titulo}» como favorito`} onClick={favorito}>★</button>
        <div className="ln-bl-info">
          <span className="ln-bl-titulo" title={b.titulo}>{b.titulo}</span>
          <span className="ln-bl-meta">
            {b.tipo && <span>{b.tipo.toUpperCase()}</span>}
            {autores && <span>{autores}</span>}
            {b.duracion !== null && <span>{mmss(b.duracion)}</span>}
            {!b.audio && <span>sin canción</span>}
            {b.problema && <span className="is-mal">⚠ {b.problema}</span>}
            {!b.problema && b.aviso && <span className="is-mal">{b.aviso}</span>}
          </span>
        </div>
        <div className="ln-bl-acc">
          {actual && <Badge variant="yellow">SUENA</Badge>}
          <Button size="sm" variant="primary" disabled={!!b.problema} onClick={() => onBailar(b.id)}>Bailar</Button>
          <Button size="sm" variant="ghost" aria-expanded={abierto} onClick={onAbrir}>Ajustes</Button>
        </div>
        {abierto && (
          <div className="ln-bl-ajustes">
            <Deslizador id={`f-bl-off-${b.id}`} label="Sincronía con la canción" min={-500} max={500} step={10} value={off}
              fmt={(v) => `${v > 0 ? '+' : ''}${v} ms`} hint="Si el baile va adelantado, súbelo; si va atrasado, bájalo." onChange={setOff} />
            <Deslizador id={`f-bl-brazo-${b.id}`} label="Ángulo de los brazos" min={25} max={45} step={1} value={brazo}
              fmt={(v) => `${v}°`} hint="Si los brazos atraviesan el cuerpo, súbelo." onChange={setBrazo} />
            <div>
              <div className="ln-bl-sub" style={{ marginTop: 0 }}>En el sitio</div>
              <div className="ln-bl-botones" style={{ marginTop: 0 }}>
                {[[null, 'Como en Ajustes'], [true, 'Sí'], [false, 'No']].map(([v, t]) => (
                  <Button key={String(v)} size="sm" variant={sitio === v ? 'primary' : 'ghost'} onClick={() => setSitio(v)}>{t}</Button>
                ))}
              </div>
              <div className="ln-toggle-row" style={{ marginTop: 10 }}>
                <Switch label="Sale en «siguiente» y al azar" checked={!b.desactivado} onChange={(ev) => azar(!!ev.target.checked)} />
              </div>
            </div>
            <div className="ln-bl-botones">
              <Button size="sm" variant="secondary" onClick={guardarAjustes}>Guardar ajustes</Button>
              <Button size="sm" variant="ghost" onClick={quitar}>{confirmar ? '¿Seguro? Quitar' : 'Quitar'}</Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  function BailesPanel() {
    const { Card, Button, Badge, Input } = window.LUNE;
    const { e, poner, vivo, recibido } = useReproductor();
    const [msg, setMsg] = useState(null);
    const cfg = useConfigReproductor(poner, setMsg);
    const [lista, setLista] = useState({ bailes: [], servicio: false });
    const [busca, setBusca] = useState('');
    const [abierto, setAbierto] = useState('');
    const [, setTic] = useState(0);
    const buscaRef = useRef('');
    buscaRef.current = busca;
    const pedirLista = (q) => pedir('bailes_lista', [String(q || '').slice(0, MAX_BUSQUEDA)], (j) => {
      if (vivo.current) setLista(normalizarLista(leer(j, {})));
    });
    const buscarDiferido = useMemo(() => crearRetardo((p) => pedirLista(p.q), 300), []);
    useEffect(() => {
      const quitar = [];
      const alBailes = (j) => {
        if (!vivo.current) return;
        if (buscaRef.current.trim()) pedirLista(buscaRef.current.trim());   // con búsqueda: se vuelve a pedir filtrada
        else setLista(normalizarLista(leer(j, {})));
      };
      const alImportado = (j) => {
        const r = leer(j, {});
        if (!vivo.current || !r) return;
        setMsg({ texto: txt(r.texto, 300) || (r.ok ? 'Importado.' : 'No pude importarlo.'), ok: r.ok === true, error: r.ok !== true });
      };
      const cablear = () => {
        quitar.push(conectar('bailes_cambio', alBailes));
        quitar.push(conectar('mmd_importado', alImportado));
        pedirLista('');
        pedir('bailes_refrescar', [], () => {});                 // la carpeta puede haber cambiado
      };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    // Progreso suave entre los avisos de Python (cada ~1 s).
    const sonando = e.fase === 'sonando' && !e.pausado;
    useEffect(() => {
      if (!sonando) return undefined;
      const id = setInterval(() => setTic((n) => n + 1), 500);
      return () => clearInterval(id);
    }, [sonando]);

    const responder = (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      if (r && r.estado) poner(r.estado);
      if (r && r.texto) setMsg({ texto: txt(r.texto, 300), ok: r.ok === true, error: r.ok !== true });
    };
    const bailar = (id) => { const via = pedir('mmd_reproducir', [id || ''], responder); if (!via) setMsg({ texto: 'El reproductor no está disponible.', error: true }); };
    const pausa = () => pedir('mmd_pausa', [], responder);
    const parar = () => pedir('mmd_parar', [], responder);
    const siguiente = () => pedir('mmd_siguiente', [], responder);
    const anterior = () => pedir('mmd_anterior', [], responder);
    const importar = () => {
      const demo = !puente();
      const via = pedir('bailes_importar', [], (ok) => {
        if (!vivo.current) return;
        setMsg(demo ? { texto: 'Demo: importar abre el diálogo de archivos en la app.', error: true }
          : ok ? { texto: 'Elige el movimiento (.vmd o .vrma) y su canción…', ok: true } : { texto: 'Ya hay un diálogo abierto (o la app no está lista).', error: true });
      });
      if (!via) setMsg({ texto: 'Importar no está disponible en esta versión de la app.', error: true });
    };
    const carpeta = () => pedir('bailes_abrir_carpeta', [], (ok) => { if (vivo.current && !ok) setMsg({ texto: puente() ? 'No pude abrir la carpeta.' : 'Demo: abre la carpeta «bailes» en la app.', error: true }); });
    const alCambio = () => { if (!puente()) pedirLista(buscaRef.current.trim()); };

    const tVis = tiempoVisible(e, recibido.current, Date.now());
    const pct = e.total > 0 ? acotar((tVis / e.total) * 100, 0, 100) : 0;
    const enMarcha = puesto(e);
    const bailando = ['sonando', 'listo', 'saliendo'].includes(e.fase) && !e.pausado;
    const badge = e.fase === 'error' ? ['ERROR', 'yellow'] : e.pendiente || e.fase === 'cargando' ? ['CARGANDO', 'ink']
      : e.pausado || e.fase === 'pausado' ? ['EN PAUSA', 'ink'] : bailando ? ['BAILANDO', 'yellow'] : ['PARADA', 'ink'];
    const demo = !puente();
    return (
      <div className="ln-settings ln-bailes">
        <div className="ln-settings-inner">
          <header className="ln-settings-head">
            <div className="lune-overline">// Reproductor · MMD y VRMA</div>
            <h2 className="ln-settings-title"><span>BAILES</span></h2>
          </header>

          <Card id="bl-reproductor" eyebrow={<><IconoBaile width={13} height={13}/> Reproductor</>} title="Lo que baila Lune" tone="cyan" tick={bailando}>
            {demo && <p className="ln-bl-nota">Demo sin la app: la lista es de ejemplo y no suena nada.</p>}
            <div className={`ln-bl-estado${bailando ? ' is-on' : ''}`}>
              <Badge variant={badge[1]} outline={badge[1] === 'ink'}>{badge[0]}</Badge>
              <span className="ln-bl-estado-tx">{textoEstado(e)}</span>
            </div>
            {e.sin_esqueleto && <p className="ln-bl-aviso" role="note">{AVISO_SIN_ESQUELETO}</p>}
            <div className="ln-bl-prog" aria-label="Progreso de la canción">
              <div className="ln-bl-prog-barra" role="progressbar" aria-valuemin={0} aria-valuemax={Math.round(e.total)} aria-valuenow={Math.round(tVis)}>
                <div className="ln-bl-prog-lleno" style={{ width: `${pct.toFixed(1)}%` }} />
              </div>
              <div className="ln-bl-prog-tx"><span>{mmss(tVis)}</span><span>{e.total > 0 ? mmss(e.total) : '—'}</span></div>
            </div>
            <div className="ln-bl-mando">
              <Button size="sm" variant="ghost" aria-label="Anterior" onClick={anterior}>⏮</Button>
              {bailando
                ? <Button size="sm" variant="secondary" className="ln-bl-grande" onClick={pausa}>⏸ Pausa</Button>
                : <Button size="sm" variant="primary" className="ln-bl-grande" onClick={() => (enMarcha && e.pausado && !e.cedida ? pausa() : bailar(e.id))}>
                    {enMarcha && e.pausado && !e.cedida ? '▶ Seguir' : '▶ Bailar'}</Button>}
              <Button size="sm" variant="ghost" disabled={!enMarcha} onClick={parar}>⏹ Parar</Button>
              <Button size="sm" variant="ghost" aria-label="Siguiente" onClick={siguiente}>⏭</Button>
            </div>
            <ControlesConfig e={e} cfg={cfg} />
            <Msg msg={msg} />
          </Card>

          <Card id="bl-biblioteca" eyebrow="Biblioteca" title="Tus bailes" tone="blue">
            <p className="ln-bl-nota">
              Un .vmd (o un .vrma) y su canción. Si trae un VMD de labios o de cara, también lo usa. La carpeta «bailes» trae un
              LEEME con los formatos; respeta la licencia de cada baile y de cada canción.
            </p>
            <div className="ln-bl-buscar">
              <Input id="f-bl-buscar" label="Buscar" placeholder="título o autor…" value={busca} maxLength={MAX_BUSQUEDA}
                onChange={(ev) => { const v = String(ev.target.value || ''); setBusca(v); buscarDiferido({ q: v.trim() }); }} />
              <Button size="sm" variant="primary" disabled={e.importando} onClick={importar}>{e.importando ? 'Importando…' : 'Importar…'}</Button>
              <Button size="sm" variant="ghost" onClick={carpeta}>Abrir carpeta</Button>
            </div>
            <div className="ln-bl-lista">
              {lista.bailes.length === 0 && (
                <p className="ln-bl-vacio">{busca.trim() ? 'Ningún baile coincide.' : 'Aún no hay bailes: impórtalos o mételos en la carpeta «bailes».'}</p>
              )}
              {lista.bailes.map((b) => (
                <FilaBaile key={b.id} b={b} actual={b.id === e.id && enMarcha} abierto={abierto === b.id}
                  onAbrir={() => setAbierto((a) => (a === b.id ? '' : b.id))} onBailar={bailar} onMsg={setMsg} alCambio={alCambio} />
              ))}
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // ── BailesCard (Ajustes) ───────────────────────────────────────────────────
  function BailesCard() {
    const { Card, Button } = window.LUNE;
    const { e, poner } = useReproductor();
    const [msg, setMsg] = useState(null);
    const cfg = useConfigReproductor(poner, setMsg);
    const carpeta = () => pedir('bailes_abrir_carpeta', [], (ok) => { if (!ok) setMsg({ texto: puente() ? 'No pude abrir la carpeta.' : 'Demo: abre la carpeta en la app.', error: true }); });
    return (
      <Card id="aj-bailes" eyebrow={<><IconoBaile width={13} height={13}/> Baile · MMD y VRMA</>} title="Mis bailes" tone="cyan" tick={puesto(e)}>
        <p className="ln-bl-nota">
          Bailo tus .vmd (MikuMikuDance) y .vrma con su canción. Si me pausas o me paras, me quedo en reposo con los brazos
          abajo; al reanudar sigo desde el mismo punto. Con las imágenes animadas o los sprites no hay esqueleto: suena la
          canción y bailo a mi manera.
        </p>
        <ControlesConfig e={e} cfg={cfg} />
        <div className="ln-bl-botones">
          <Button size="sm" variant="secondary" onClick={() => irAVista('bailes')}>Abrir mis bailes</Button>
          <Button size="sm" variant="ghost" onClick={carpeta}>Abrir la carpeta</Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  Object.assign(window, {
    BailesPanel, BailesCard,
    LuneBailesWeb: {
      normalizarBaile, normalizarLista, normalizarEstado, textoEstado, mmss, tiempoVisible, AL_TERMINAR,
      AVISO_SIN_ESQUELETO, ESTADO_DEFECTO,
    },
  });
})();
