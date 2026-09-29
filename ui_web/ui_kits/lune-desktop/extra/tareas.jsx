/* Lune CD desktop — Tareas, estilo Microsoft To Do (Lune CD 10.9).
 *
 * TareasPanel   vista «tareas» (app.jsx): «Mi día» con la fecha debajo; las pendientes de hoy (un círculo para
 *               marcarlas, el texto y debajo su lista: «Tareas» o «Recordatorios»); «Completadas (n)» plegable con
 *               el texto tachado; la papelera al pasar el ratón (con confirmación ligera: «¿Quitar?»); el sol
 *               tachado la saca de Mi día; la bombilla abre a la derecha «Sugerencias» (Ayer / Agregado
 *               recientemente / Más antiguas) con «+» para traerla a Mi día; estado vacío con un dibujo de línea;
 *               abajo, «Agregar una tarea» (Enter la añade a Mi día).
 * Las tareas son los recuerdos de tipo tarea/recordatorio de memoria.json (nucleo/tareas.py): lo que le dices a
 * Lune con «recuerda que tengo que…» sale aquí solo (señal `cambio`), sin preguntarle.
 * Puente: window.luneTareas (ui/puente_tareas.py). Sin puente (navegador suelto, o un backend sin el objeto),
 * un aviso y la vista vacía: no revienta.
 * LuneTareas    utilidades puras (normalizar lo que llega del puente, fecha larga en español, textos) para los
 *               tests y para la entrada «Tareas» de la barra lateral (sidebar.jsx).
 * Se registra solo: Object.assign(window, {TareasPanel, LuneTareas}).
 */
(function () {
  const { useState, useEffect, useRef } = React;

  // ── Puente: window.luneTareas (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneTareas || null;
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
  /** Llama a la ranura `nombre` del puente. → true si se pudo pedir. */
  function pedir(nombre, args, cb) {
    const p = puente();
    if (!p || typeof p[nombre] !== 'function') return false;
    try { p[nombre](...(args || []), (r) => { if (cb) cb(r); }); return true; } catch (e) { return false; }
  }
  /** fn ahora si ya hay puente; si no, cuando llegue 'lune-ready'. → quitar */
  function alListo(fn) {
    if (puente()) { fn(); return () => {}; }
    window.addEventListener('lune-ready', fn, { once: true });
    return () => window.removeEventListener('lune-ready', fn);
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const ID_OK = /^[A-Za-z0-9_-]{1,40}$/;
  const TEXTO_MAX = 200;
  const LISTAS = ['Tareas', 'Recordatorios'];
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];   // getDay()
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
    'noviembre', 'diciembre'];
  const MARCAR_MS = 320;                              // la animación del círculo antes de moverla a «Completadas»
  const CONFIRMAR_MS = 4000;                          // «¿Quitar?» se cancela solo

  /** «martes, 29 de septiembre» sin depender del idioma del navegador. */
  function fechaLarga(d) {
    const f = d && typeof d.getDay === 'function' && isFinite(d.getTime()) ? d : new Date();
    return `${DIAS[f.getDay()]}, ${f.getDate()} de ${MESES[f.getMonth()]}`;
  }
  const texto = (v, max = TEXTO_MAX) => (v == null || typeof v === 'object' ? '' : String(v))
    .replace(/[\u0000-\u001f\u007f-\u009f‎‏‪-‮⁦-⁩]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max);
  const entero = (v) => (typeof v === 'number' && isFinite(v) && v >= 0 ? Math.floor(v) : 0);

  /** Tarea del puente → {id, texto, lista, creada, hecha, hecha_en, en_mi_dia}; null si no vale. */
  function normalizarTarea(t) {
    if (!t || typeof t !== 'object' || !ID_OK.test(String(t.id || ''))) return null;
    return {
      id: String(t.id),
      texto: texto(t.texto) || '(sin texto)',
      lista: LISTAS.includes(t.lista) ? t.lista : 'Tareas',
      creada: typeof t.creada === 'string' ? t.creada.slice(0, 40) : '',
      hecha: t.hecha === true,
      hecha_en: typeof t.hecha_en === 'string' ? t.hecha_en.slice(0, 40) : '',
      en_mi_dia: t.en_mi_dia === true,
    };
  }
  const listaDe = (xs) => (Array.isArray(xs) ? xs.map(normalizarTarea).filter(Boolean) : []);
  /** Estado del puente (estado() o la señal cambio) → siempre con la misma forma. */
  function normalizarEstado(o, hoy) {
    const e = o && typeof o === 'object' ? o : {};
    const md = e.mi_dia && typeof e.mi_dia === 'object' ? e.mi_dia : {};
    const sg = e.sugerencias && typeof e.sugerencias === 'object' ? e.sugerencias : {};
    const c = e.contador && typeof e.contador === 'object' ? e.contador : {};
    const pendientes = listaDe(md.pendientes);
    return {
      disponible: e.disponible === true,
      error: typeof e.error === 'string' ? texto(e.error, 300) : '',
      mi_dia: {
        fecha: typeof md.fecha === 'string' ? md.fecha.slice(0, 10) : '',
        fecha_larga: texto(md.fecha_larga, 60) || fechaLarga(hoy),
        pendientes,
        hechas: listaDe(md.hechas),
      },
      sugerencias: { ayer: listaDe(sg.ayer), recientes: listaDe(sg.recientes), antes: listaDe(sg.antes) },
      contador: { hoy: c.hoy === undefined ? pendientes.length : entero(c.hoy), total: entero(c.total) },
    };
  }
  const nSugerencias = (e) => e.sugerencias.ayer.length + e.sugerencias.recientes.length + e.sugerencias.antes.length;
  /** Lo que dice la entrada de la barra lateral: «3 para hoy · 5 en total». */
  function textoContador(c, disponible = true) {
    if (!disponible) return 'Mi día';
    const hoy = entero(c && c.hoy), total = Math.max(entero(c && c.total), hoy);
    if (!total) return 'Nada pendiente';
    if (!hoy) return total === 1 ? '1 pendiente' : `${total} pendientes`;
    return `${hoy} para hoy` + (total > hoy ? ` · ${total} en total` : '');
  }

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  // Colores del tema por tokens (var(--x) y rgb(var(--x-rgb, R G B) / a)): el tema del corte 4 los tiñe.
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-tareas-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-tareas-css';
      st.textContent = `
        .ln-td{ flex:1; min-height:0; display:flex; position:relative; background:
          radial-gradient(640px 360px at 12% -8%, rgb(var(--yellow-500-rgb, 255 224 0) / .07), transparent 62%),
          radial-gradient(820px 520px at 90% 110%, rgb(var(--blue-500-rgb, 30 85 255) / .14), transparent 60%),
          linear-gradient(180deg, var(--ink-950) 0%, var(--ink-850) 70%); }
        .ln-td-main{ flex:1; min-width:0; display:flex; flex-direction:column; }
        .ln-td-head{ display:flex; align-items:flex-start; justify-content:space-between; gap:14px; padding:24px 28px 12px; }
        .ln-td-titulo{ position:relative; display:inline-block; margin:6px 0 0; padding:3px 22px 3px 12px; font-family:var(--font-display);
          font-weight:700; font-style:italic; font-size:26px; letter-spacing:.04em; color:var(--ink-950); transform:rotate(-1.5deg); }
        .ln-td-titulo::before{ content:""; position:absolute; inset:0; z-index:-1; background:var(--yellow-500); border:3px solid var(--ink-950);
          box-shadow:5px 5px 0 rgb(var(--ink-950-rgb, 5 7 15) / .75); clip-path:polygon(1% 8%, 100% 0, 98% 92%, 0 100%); }
        .ln-td-fecha{ margin-top:10px; font-family:var(--font-mono); font-size:12px; letter-spacing:.06em; color:var(--cyan-300); }
        .ln-td-herr{ display:flex; gap:8px; align-items:center; }
        .ln-td-btnic{ position:relative; appearance:none; -webkit-appearance:none; display:inline-flex; align-items:center; gap:7px; cursor:pointer;
          border:var(--bw) solid var(--ink-500); background:var(--ink-800); color:var(--text-muted); padding:8px 11px; clip-path:var(--clip-tr);
          font-family:var(--font-display); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.06em;
          transition:background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast); }
        .ln-td-btnic:hover{ color:var(--text); border-color:var(--cyan-700); }
        .ln-td-btnic.is-on{ background:rgb(var(--yellow-500-rgb, 255 224 0) / .12); border-color:var(--yellow-600); color:var(--yellow-300); }
        .ln-td-btnic svg{ display:block; flex:none; }
        .ln-td-badge{ min-width:18px; height:18px; padding:0 5px; display:inline-flex; align-items:center; justify-content:center;
          background:var(--yellow-500); color:var(--ink-950); font-family:var(--font-mono); font-weight:700; font-size:10px; }
        .ln-td-lista{ flex:1; min-height:0; overflow-y:auto; padding:6px 28px 18px; display:flex; flex-direction:column; gap:6px; }
        .ln-td-lista::-webkit-scrollbar, .ln-td-sug-lista::-webkit-scrollbar{ width:9px; }
        .ln-td-lista::-webkit-scrollbar-thumb, .ln-td-sug-lista::-webkit-scrollbar-thumb{ background:var(--ink-500); }
        .ln-td-aviso{ margin:4px 0 8px; padding:10px 12px; font-family:var(--font-mono); font-size:12px; line-height:1.5; color:var(--text);
          background:var(--ink-950); border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--yellow-500); clip-path:var(--clip-tr); }
        .ln-td-fila{ display:flex; align-items:center; gap:12px; padding:11px 12px; background:rgb(var(--ink-950-rgb, 5 7 15) / .72);
          border:var(--bw) solid var(--ink-500); clip-path:var(--clip-tr); animation:ln-td-in .24s var(--ease-snap) backwards;
          transition:border-color var(--dur-fast), background var(--dur-fast), opacity var(--dur), transform var(--dur) var(--ease-snap); }
        @keyframes ln-td-in{ from{ opacity:0; transform:translateY(8px) skewX(-3deg); } to{ opacity:1; transform:none; } }
        .ln-td-fila:hover, .ln-td-fila:focus-within{ border-color:var(--cyan-700); background:var(--ink-800); }
        .ln-td-fila.is-hecha .ln-td-texto{ text-decoration:line-through; color:var(--text-dim); }
        .ln-td-fila.is-marcando{ opacity:.55; transform:translateX(10px) skewX(-4deg); }
        .ln-td-fila.is-marcando .ln-td-texto{ text-decoration:line-through; color:var(--text-dim); }
        .ln-td-circulo{ appearance:none; -webkit-appearance:none; flex:none; width:22px; height:22px; padding:0; border-radius:50%; cursor:pointer;
          border:2px solid var(--cyan-500); background:transparent; color:transparent; display:inline-flex; align-items:center; justify-content:center;
          transition:background var(--dur-fast), color var(--dur-fast), box-shadow var(--dur-fast), transform var(--dur-fast) var(--ease-snap); }
        .ln-td-circulo:hover{ color:var(--cyan-400); box-shadow:0 0 10px rgb(var(--cyan-500-rgb, 0 229 255) / .35); }
        .ln-td-circulo.is-on{ background:var(--cyan-500); color:var(--ink-950); animation:ln-td-pop .32s var(--ease-snap); }
        .ln-td-circulo.is-rec{ border-color:var(--blue-400); }
        .ln-td-circulo.is-rec.is-on{ background:var(--blue-400); }
        @keyframes ln-td-pop{ 0%{ transform:scale(.7); } 60%{ transform:scale(1.18); } 100%{ transform:scale(1); } }
        .ln-td-tx{ flex:1; min-width:0; display:flex; flex-direction:column; gap:2px; }
        .ln-td-texto{ font-family:var(--font-sans); font-size:14px; color:var(--text-strong); overflow-wrap:anywhere; }
        .ln-td-meta{ font-family:var(--font-mono); font-size:10.5px; letter-spacing:.05em; text-transform:uppercase; color:var(--text-faint); }
        .ln-td-meta .is-dia{ color:var(--yellow-400); }
        .ln-td-acc{ display:flex; gap:2px; align-items:center; opacity:0; transition:opacity var(--dur-fast); }
        .ln-td-fila:hover .ln-td-acc, .ln-td-fila:focus-within .ln-td-acc, .ln-td-acc.is-fijo{ opacity:1; }
        .ln-td-ic{ appearance:none; -webkit-appearance:none; border:none; background:none; color:var(--text-dim); cursor:pointer; padding:6px; line-height:0; }
        .ln-td-ic:hover{ color:var(--cyan-300); }
        .ln-td-ic.is-peligro:hover{ color:var(--red-500); }
        .ln-td-ic.is-mas{ color:var(--cyan-400); border:var(--bw) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-td-ic.is-mas:hover{ background:var(--cyan-500); color:var(--ink-950); }
        .ln-td-conf{ display:flex; align-items:center; gap:6px; font-family:var(--font-mono); font-size:11px; color:var(--text-muted); }
        .ln-td-mini{ appearance:none; -webkit-appearance:none; cursor:pointer; padding:4px 9px; border:var(--bw) solid var(--ink-500); background:var(--ink-900);
          color:var(--text); font-family:var(--font-display); font-weight:600; font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; clip-path:var(--clip-tr); }
        .ln-td-mini.is-peligro{ border-color:var(--red-600); color:var(--red-500); }
        .ln-td-mini.is-peligro:hover{ background:var(--red-500); color:var(--ink-950); }
        .ln-td-plegar{ appearance:none; -webkit-appearance:none; align-self:flex-start; display:inline-flex; align-items:center; gap:7px; margin-top:12px;
          cursor:pointer; border:var(--bw) solid var(--ink-500); background:var(--ink-900); color:var(--text-muted); padding:6px 11px; clip-path:var(--clip-tr);
          font-family:var(--font-display); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:.06em; }
        .ln-td-plegar:hover{ color:var(--text); border-color:var(--cyan-700); }
        .ln-td-plegar svg{ transition:transform var(--dur-fast) var(--ease-snap); }
        .ln-td-plegar.is-abierto svg{ transform:rotate(90deg); }
        .ln-td-vacio{ margin:auto; padding:30px 16px; max-width:380px; display:flex; flex-direction:column; align-items:center; gap:10px; text-align:center; }
        .ln-td-vacio svg{ color:var(--cyan-500); filter:drop-shadow(0 0 10px rgb(var(--cyan-500-rgb, 0 229 255) / .25)); }
        .ln-td-vacio .is-luna{ color:var(--yellow-500); }
        .ln-td-vacio-t{ font-family:var(--font-display); font-weight:700; font-size:17px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-strong); }
        .ln-td-vacio-d{ font-family:var(--font-sans); font-size:13.5px; line-height:1.5; color:var(--text-muted); }
        .ln-td-vacio-btn{ appearance:none; -webkit-appearance:none; margin-top:6px; cursor:pointer; border:var(--bw) solid var(--cyan-700); background:var(--ink-800);
          color:var(--cyan-300); font-family:var(--font-display); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:.06em;
          padding:9px 14px; clip-path:var(--clip-tr); transition:background var(--dur-fast), color var(--dur-fast); }
        .ln-td-vacio-btn:hover{ background:var(--cyan-500); color:var(--ink-950); }
        .ln-td-nueva{ flex:none; display:flex; align-items:center; gap:10px; margin:0 28px 20px; padding:0 8px 0 14px; height:50px;
          background:var(--ink-900); border:var(--bw) solid var(--border); clip-path:var(--clip-tr); transition:border-color var(--dur-fast), box-shadow var(--dur-fast); }
        .ln-td-nueva:focus-within{ border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm); }
        .ln-td-nueva > svg{ color:var(--cyan-500); flex:none; }
        .ln-td-nueva input{ flex:1; min-width:0; height:100%; border:none; outline:none; background:transparent; color:var(--text);
          font-family:var(--font-sans); font-size:14px; }
        .ln-td-nueva input::placeholder{ color:var(--text-faint); }
        .ln-td-nueva input:disabled{ cursor:not-allowed; }
        .ln-td-msg{ margin:0 28px 8px; font-family:var(--font-mono); font-size:11.5px; color:var(--yellow-500); }
        .ln-td-sug{ flex:none; width:310px; display:flex; flex-direction:column; min-height:0; background:var(--ink-850);
          border-left:var(--bw) solid var(--border-strong); animation:ln-td-sug-in .26s var(--ease-snap); }
        @keyframes ln-td-sug-in{ from{ opacity:0; transform:translateX(30px); } to{ opacity:1; transform:none; } }
        .ln-td-sug-head{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:20px 16px 10px; }
        .ln-td-sug-t{ font-family:var(--font-display); font-weight:700; font-size:15px; text-transform:uppercase; letter-spacing:.06em; color:var(--yellow-300); }
        .ln-td-sug-lista{ flex:1; min-height:0; overflow-y:auto; padding:0 12px 18px; display:flex; flex-direction:column; gap:6px; }
        .ln-td-sec{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:12px 2px 2px; }
        .ln-td-sug .ln-td-fila{ padding:9px 10px; }
        .ln-td-sug .ln-td-acc{ opacity:1; }
        .ln-td-nada{ font-family:var(--font-mono); font-size:12px; line-height:1.5; color:var(--text-dim); padding:14px 4px; }
        @media (max-width: 900px){ .ln-td-sug{ position:absolute; right:0; top:0; bottom:0; z-index:5; box-shadow:var(--shadow-pop); } }
        @media (prefers-reduced-motion: reduce){ .ln-td-fila, .ln-td-sug, .ln-td-circulo.is-on{ animation:none; } .ln-td-fila.is-marcando{ transform:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }
  function useVivo() {
    const vivo = useRef(true);
    useEffect(() => { vivo.current = true; inyectarEstilos(); return () => { vivo.current = false; }; }, []);
    return vivo;
  }

  // ── Iconos de línea (como icons.jsx: 2px, sin relleno) ─────────────────────
  const svg = (trazos, extra) => (p) => React.createElement('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true', ...(p || {}) },
    ...trazos.map((d, i) => React.createElement('path', { key: i, d })), ...(extra ? extra() : []));
  const IconoCheck = svg(['M5 12.5l4.2 4.2L19 7']);
  const IconoMas = svg(['M12 5v14', 'M5 12h14']);
  const IconoPapelera = svg(['M3 6h18', 'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2']);
  const IconoBombilla = svg(['M9 18h6', 'M10 21h4', 'M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V17h5.2v-1.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z']);
  const IconoSolFuera = svg(['M12 2v2', 'M12 20v2', 'M4.9 4.9l1.4 1.4', 'M17.7 17.7l1.4 1.4', 'M2 12h2', 'M20 12h2', 'M4.9 19.1l1.4-1.4',
    'M17.7 6.3l1.4-1.4', 'M3 3l18 18'], () => [React.createElement('circle', { key: 'c', cx: 12, cy: 12, r: 4 })]);
  const IconoFlecha = svg(['M9 6l6 6-6 6']);
  const IconoCerrar = svg(['M18 6 6 18', 'M6 6l12 12']);

  /** El dibujo del estado vacío: una lista con su primera tarea hecha y la luna de Lune. */
  function DibujoVacio() {
    const h = React.createElement;
    return h('svg', { width: 150, height: 112, viewBox: '0 0 150 112', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
      strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true' },
      h('path', { d: 'M28 22h66l12 12v66H28z' }),
      h('path', { d: 'M94 22v12h12' }),
      h('circle', { cx: 44, cy: 48, r: 6 }), h('path', { d: 'M41.2 48.2l2 2 4-4.2' }),
      h('path', { d: 'M58 48h32' }),
      h('circle', { cx: 44, cy: 66, r: 6 }), h('path', { d: 'M58 66h26' }),
      h('circle', { cx: 44, cy: 84, r: 6 }), h('path', { d: 'M58 84h30' }),
      h('path', { className: 'is-luna', d: 'M131 14a15 15 0 1 0 9 26 12 12 0 1 1-9-26z' }),
      h('path', { className: 'is-luna', d: 'M117 60l3 3M124 58v4M113 66h4' }));
  }

  /** Estado de las tareas (estado() + señal cambio). modo: 'puente' | 'espera' (app, el canal aún no llegó) | 'sin'. */
  function useTareas(vivo) {
    const [estado, setEstado] = useState(() => normalizarEstado(null, new Date()));
    const [modo, setModo] = useState(() => (puente() ? 'puente' : (window.qt && window.qt.webChannelTransport ? 'espera' : 'sin')));
    const poner = (o) => { if (vivo.current && o && typeof o === 'object') setEstado(normalizarEstado(o, new Date())); };
    const cargar = () => pedir('estado', [], (j) => poner(leer(j, null)));
    useEffect(() => {
      const quitar = [];
      const cablear = () => {
        if (!puente()) { if (vivo.current) setModo('sin'); return; }
        if (vivo.current) setModo('puente');
        quitar.push(conectar('cambio', (j) => poner(leer(j, null))));
        cargar();
      };
      const q = alListo(cablear);
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    return { estado, poner, cargar, modo };
  }

  function sonarHecha() {
    const s = window.luneSfx;
    if (!s || typeof s.tocar !== 'function') return;
    try { const r = s.tocar('blip', { vol: 0.45, pitch: [1.08, 1.16] }); if (r && r.catch) r.catch(() => {}); } catch (e) { /* sin audio */ }
  }

  // ── Una tarea ──────────────────────────────────────────────────────────────
  function Fila({ t, marcando, onMarcar, onQuitar, onMiDia, sugerencia = false, confirmando, onConfirmar, onCancelar }) {
    const on = t.hecha || marcando;
    const clase = `ln-td-fila${t.hecha ? ' is-hecha' : ''}${marcando ? ' is-marcando' : ''}`;
    return (
      <div className={clase} data-id={t.id}>
        <button type="button" className={`ln-td-circulo${on ? ' is-on' : ''}${t.lista === 'Recordatorios' ? ' is-rec' : ''}`}
          role="checkbox" aria-checked={on} aria-label={t.hecha ? 'Marcar como pendiente' : 'Marcar como hecha'}
          title={t.hecha ? 'Marcar como pendiente' : 'Marcar como hecha'} onClick={() => onMarcar(t)}>
          <IconoCheck width={13} height={13} strokeWidth={3} />
        </button>
        <div className="ln-td-tx">
          <span className="ln-td-texto">{t.texto}</span>
          <span className="ln-td-meta">{t.lista}{!sugerencia && !t.hecha && t.en_mi_dia ? <span className="is-dia"> · Mi día</span> : null}</span>
        </div>
        {confirmando ? (
          <div className="ln-td-conf" role="group" aria-label="Confirmar">
            <span>¿Quitar?</span>
            <button type="button" className="ln-td-mini is-peligro" onClick={() => onConfirmar(t)}>Quitar</button>
            <button type="button" className="ln-td-mini" onClick={onCancelar}>No</button>
          </div>
        ) : (
          <div className={`ln-td-acc${sugerencia ? ' is-fijo' : ''}`}>
            {sugerencia
              ? <button type="button" className="ln-td-ic is-mas" aria-label="Agregar a Mi día" title="Agregar a Mi día"
                  onClick={() => onMiDia(t, true)}><IconoMas width={16} height={16} /></button>
              : (!t.hecha && t.en_mi_dia && onMiDia
                ? <button type="button" className="ln-td-ic" aria-label="Quitar de Mi día" title="Quitar de Mi día"
                    onClick={() => onMiDia(t, false)}><IconoSolFuera width={16} height={16} /></button> : null)}
            {!sugerencia && (
              <button type="button" className="ln-td-ic is-peligro" aria-label="Quitar tarea" title="Quitar tarea"
                onClick={() => onQuitar(t)}><IconoPapelera width={16} height={16} /></button>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── Vista «tareas» ─────────────────────────────────────────────────────────
  function TareasPanel() {
    const vivo = useVivo();
    const { estado, poner, cargar, modo } = useTareas(vivo);
    const [nueva, setNueva] = useState('');
    const [verHechas, setVerHechas] = useState(true);
    const [verSug, setVerSug] = useState(false);
    const [marcando, setMarcando] = useState({});        // id → true mientras se anima el círculo
    const [confirmar, setConfirmar] = useState('');      // id con «¿Quitar?» a la vista
    const [msg, setMsg] = useState('');
    const entrada = useRef(null);
    const timers = useRef([]);
    useEffect(() => () => { timers.current.forEach(clearTimeout); timers.current = []; }, []);
    const luego = (fn, ms) => { const id = setTimeout(() => { if (vivo.current) fn(); }, ms); timers.current.push(id); };
    const conPuente = modo === 'puente';
    const disponible = conPuente && estado.disponible;

    const responder = (alOk) => (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      if (r && r.estado) poner(r.estado); else cargar();
      if (r && r.ok) { setMsg(''); if (alOk) alOk(r); } else setMsg((r && r.error) || 'No pude hacerlo.');
    };
    const accion = (nombre, args, alOk) => {
      if (!pedir(nombre, args, responder(alOk))) setMsg('Las tareas necesitan la app de Lune.');
    };

    const agregar = () => {
      const t = texto(nueva);
      if (!t) return;
      if (!disponible) { setMsg('Las tareas necesitan la app de Lune.'); return; }
      accion('agregar', [t], () => setNueva(''));
    };
    const marcar = (t) => {
      if (!t.hecha) {
        if (marcando[t.id]) return;
        setMarcando((m) => ({ ...m, [t.id]: true }));
        sonarHecha();
        luego(() => {
          accion('completar', [t.id, true]);
          setMarcando((m) => { const n = { ...m }; delete n[t.id]; return n; });
        }, MARCAR_MS);
      } else accion('completar', [t.id, false]);
    };
    const alMiDia = (t, si) => accion('al_mi_dia', [t.id, !!si]);
    const pedirQuitar = (t) => {
      setConfirmar(t.id);
      luego(() => setConfirmar((c) => (c === t.id ? '' : c)), CONFIRMAR_MS);
    };
    const quitar = (t) => { setConfirmar(''); accion('quitar', [t.id]); };
    const cancelar = () => setConfirmar('');

    const md = estado.mi_dia;
    const nSug = nSugerencias(estado);
    const vacio = !md.pendientes.length && !md.hechas.length;
    const fila = (t, extra) => (
      <Fila key={t.id} t={t} marcando={!!marcando[t.id]} onMarcar={marcar} onQuitar={pedirQuitar} onMiDia={alMiDia}
        confirmando={confirmar === t.id} onConfirmar={quitar} onCancelar={cancelar} {...(extra || {})} />
    );
    const seccion = (titulo, xs) => (xs.length ? [
      <div key={`s-${titulo}`} className="ln-td-sec">{titulo}</div>,
      ...xs.map((t) => fila(t, { sugerencia: true })),
    ] : []);

    return (
      <div className="ln-td">
        <section className="ln-td-main" aria-label="Mi día">
          <header className="ln-td-head">
            <div>
              <div className="lune-overline">// Tareas</div>
              <h2 className="ln-td-titulo"><span>MI DÍA</span></h2>
              <div className="ln-td-fecha">{md.fecha_larga}</div>
            </div>
            <div className="ln-td-herr">
              <button type="button" className={`ln-td-btnic${verSug ? ' is-on' : ''}`} aria-pressed={verSug}
                title="Sugerencias: lo pendiente que no está en tu día" onClick={() => setVerSug((v) => !v)}>
                <IconoBombilla /><span>Sugerencias</span>{nSug ? <span className="ln-td-badge">{nSug}</span> : null}
              </button>
            </div>
          </header>

          <div className="ln-td-lista">
            {modo === 'sin' && (
              <div className="ln-td-aviso" role="status">
                Tus tareas viven en la app de Lune: ábrela y aquí verás todo lo que me pediste que te recordara.
              </div>
            )}
            {conPuente && !estado.disponible && (
              <div className="ln-td-aviso" role="status">{estado.error || 'Ahora mismo no puedo leer tus tareas.'}</div>
            )}
            {md.pendientes.map((t) => fila(t))}
            {vacio && (
              <div className="ln-td-vacio">
                <DibujoVacio />
                <div className="ln-td-vacio-t">Concéntrate en tu día</div>
                <div className="ln-td-vacio-d">
                  Termina tus tareas con Mi día, una lista que se actualiza todos los días. Lo que me pidas que te recuerde aparece aquí solo.
                </div>
                {nSug
                  ? <button type="button" className="ln-td-vacio-btn" onClick={() => setVerSug(true)}>Ver sugerencias ({nSug})</button>
                  : <button type="button" className="ln-td-vacio-btn" disabled={!disponible}
                      onClick={() => { const e = entrada.current; if (e && typeof e.focus === 'function') { try { e.focus(); } catch (x) { /* sin foco */ } } }}>
                      Anotar una tarea</button>}
              </div>
            )}
            {md.hechas.length > 0 && (
              <button type="button" className={`ln-td-plegar${verHechas ? ' is-abierto' : ''}`} aria-expanded={verHechas}
                onClick={() => setVerHechas((v) => !v)}>
                <IconoFlecha width={14} height={14} /><span>Completadas ({md.hechas.length})</span>
              </button>
            )}
            {verHechas && md.hechas.map((t) => fila(t))}
          </div>

          {msg && <p className="ln-td-msg" role="status">{msg}</p>}
          <div className="ln-td-nueva">
            <IconoMas />
            <input ref={entrada} type="text" value={nueva} maxLength={TEXTO_MAX} disabled={!disponible}
              aria-label="Agregar una tarea" placeholder={disponible ? 'Agregar una tarea' : 'Abre Lune para anotar tareas'}
              onChange={(e) => setNueva(String((e && e.target && e.target.value) || '').slice(0, TEXTO_MAX))}
              onKeyDown={(e) => { if (e && e.key === 'Enter' && !e.isComposing) { if (typeof e.preventDefault === 'function') e.preventDefault(); agregar(); } }} />
            {texto(nueva) && disponible
              ? <button type="button" className="ln-td-mini" onClick={agregar}>Agregar</button> : null}
          </div>
        </section>

        {verSug && (
          <aside className="ln-td-sug" aria-label="Sugerencias">
            <div className="ln-td-sug-head">
              <span className="ln-td-sug-t">Sugerencias</span>
              <button type="button" className="ln-td-ic" aria-label="Cerrar sugerencias" title="Cerrar" onClick={() => setVerSug(false)}>
                <IconoCerrar width={16} height={16} /></button>
            </div>
            <div className="ln-td-sug-lista">
              {nSug ? [
                ...seccion('Ayer', estado.sugerencias.ayer),
                ...seccion('Agregado recientemente', estado.sugerencias.recientes),
                ...seccion('Más antiguas', estado.sugerencias.antes),
              ] : <div className="ln-td-nada">Nada que sugerir: todo lo pendiente ya está en tu día.</div>}
            </div>
          </aside>
        )}
      </div>
    );
  }

  const LuneTareas = { normalizarTarea, normalizarEstado, fechaLarga, textoContador, texto, nSugerencias };
  Object.assign(window, { TareasPanel, LuneTareas });
})();
