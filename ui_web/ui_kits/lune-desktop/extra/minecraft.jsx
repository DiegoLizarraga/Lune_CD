/* Lune CD desktop — Minecraft: reacciones a tu partida y el bot de Lune (corte 10).
 *
 * MinecraftPanel  vista «minecraft» (app.jsx): el bot (conectado o no, vida, hambre, día, lluvia), conectar y
 *                 desconectar, órdenes rápidas (sígueme, ven, para, recoge, explora), otra orden, «Decir» en el chat
 *                 del juego, qué hace Lune (eventos: lo que dijo o apuntó; en modo juego lo dice el bot en el chat y
 *                 al salir hay un resumen), el chat del juego (SOLO TEXTO: es de terceros, nunca se interpreta) y el
 *                 registro del bot.
 * MinecraftCard   Ajustes: reacciones (reaccionar, latest.log automático o uno de los que encuentra «Detectar», voz,
 *                 decir en el juego, resumen al salir, pensar en juego, otros jugadores) y el bot (servidor, puerto,
 *                 versión, nick, dueño, solo el dueño con el aviso de suplantación, defenderte, pensar cada N s, estilo),
 *                 «Instalar el bot (~400 MB)» con su progreso (D3: solo este botón instala), conectar y el aviso de
 *                 online-mode=false («Abrir en LAN» de vanilla no sirve).
 * window.LuneMinecraftWeb  utilidades puras (tests): normalizarEstado, normalizarConfig, normalizarEvento,
 *                 normalizarChat, textoBot, validarBot, ORDENES_RAPIDAS, AVISO_SUPLANTACION, AVISO_ONLINE_MODE.
 * Puente: window.luneEscenario (ui/puente_escenario.py). La página nunca manda rutas: el latest.log es «automático» o
 * uno de los detectados. Sin puente (navegador), una demo local. Se registra solo: Object.assign(window,
 * {MinecraftPanel, MinecraftCard, LuneMinecraftWeb}).
 */
(function () {
  const { useState, useEffect, useRef } = React;

  // ── Puente: window.luneEscenario (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneEscenario || null;
  const DEMO_SENALES = {};
  function conectar(senal, fn) {
    const p = puente();
    if (!p) {
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
  function irAVista(v, seccion) {
    try { window.dispatchEvent(new window.CustomEvent('lune-vista', { detail: v })); } catch (e) { /* sin eventos */ }
    if (seccion) {
      setTimeout(() => {
        try { const el = document.getElementById(seccion); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) { /* sin DOM */ }
      }, 450);
    }
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const fin = Number.isFinite;
  const entero = (v) => (typeof v === 'number' && fin(v) && Math.round(v) === v ? v : null);
  const txt = (v, max = 160) => (typeof v === 'string' || typeof v === 'number'
    ? String(v).replace(/[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]/g, '').trim().slice(0, max) : '');
  const NICK = /^[A-Za-z0-9_]{3,16}$/;
  const VERSION = /^\d+\.\d+(\.\d+)?$/;
  const HOST = /^[A-Za-z0-9.\-:[\]]{1,253}$/;
  const PALABRA = /^[a-z_]{1,24}$/;
  const NODE = /^v?\d{1,3}\.\d{1,4}\.\d{1,5}$/;
  const FUENTES = ['log', 'bot', 'lune', 'usuario', 'modelo'];
  const ESTILOS = [['personaje', 'Como Lune'], ['sobrio', 'Sobrio']];
  const MAX_EVENTOS = 50, MAX_CHAT = 50, MAX_LOG = 30, MAX_ORDEN = 200, MAX_DECIR = 100;
  const ORDENES_RAPIDAS = [['sígueme', 'Sígueme'], ['ven', 'Ven'], ['para', 'Para'], ['recoge', 'Recoge'], ['explora', 'Explora']];
  const CONFIG_BOOL = [
    ['reaccionar', 'Reaccionar a lo que pasa en tu partida', 'Lee el latest.log (solo el archivo; nada del juego en sí).'],
    ['auto_con_juego', 'Solo mientras Minecraft está abierto', ''],
    ['voz_reacciones', 'Decir las reacciones en voz alta', ''],
    ['decir_en_juego', 'En modo juego, que lo diga el bot en el chat del juego', 'La mascota se oculta mientras juegas.'],
    ['resumen_al_salir', 'Al salir del modo juego, un resumen', ''],
    ['pensar_en_juego', 'Que el bot piense solo mientras juegas', 'Apagado: no le quita GPU a Minecraft (órdenes y reflejos siguen).'],
    ['reaccionar_otros', 'Reaccionar también a otros jugadores', ''],
  ];
  const CONFIG_DEFECTO = { reaccionar: false, ruta_log: '', voz_reacciones: false, auto_con_juego: true, decir_en_juego: true,
    resumen_al_salir: true, pensar_en_juego: false, reaccionar_otros: false };
  const BOT_DEFECTO = { host: 'localhost', port: 25565, version: '', usuario: '', dueno: '', pensar_cada_s: 45, defender: true,
    solo_dueno: true, estilo_frases: 'personaje' };
  const ESTADO_DEFECTO = { reaccionar: false, log: { ruta: '', activo: false, yo: '' },
    bot: { instalado: false, instalando: false, conectando: false, conectado: false, servidor: '', nick: '', vida: null,
      hambre: null, dia: null, lluvia: null, error: '' },
    requisitos: { node: null, node_ok: null, npm: null }, juego: false, pensando: false, servicio: false };
  const AVISO_SUPLANTACION = 'Ojo: en un servidor sin autenticación (online-mode=false) cualquiera puede ponerse tu nick. '
    + '«Solo el dueño» filtra por nombre, no es una garantía de seguridad.';
  const AVISO_ONLINE_MODE = 'El bot solo entra en servidores sin autenticación (online-mode=false): uno local o uno tuyo con esa '
    + 'opción. «Abrir en LAN» de Minecraft normal no sirve (pide cuenta). Sin visor ni puertos abiertos.';
  const PRIVACIDAD = 'El chat del juego nunca le llega al modelo de Lune. El bot usa su personaje pero no su memoria (el chat '
    + 'es público). Si su modelo está en la nube, lo que ve del mundo va a ese proveedor.';
  const NOMBRES_EVENTO = { muerte: 'Muerte', logro: 'Logro', conexion: 'Entró', desconexion: 'Salió', peligro: 'Peligro',
    dia: 'Día', noche: 'Noche', lluvia: 'Lluvia', sesion_inicio: 'Partida', sesion_fin: 'Fin', bot_conectado: 'Bot dentro',
    bot_desconectado: 'Bot fuera', bot_muerte: 'Bot murió', bot_mata: 'Bot cazó', bot_mineral: 'Mineral', bot_herida: 'Bot herido',
    bot_nivel: 'Nivel', orden: 'Orden', respuesta: 'Bot', resumen: 'Resumen', instalacion: 'Instalación' };

  const boolONull = (v) => (typeof v === 'boolean' ? v : null);
  const de0a40 = (v) => { const n = entero(v); return n !== null && n >= 0 && n <= 40 ? n : null; };
  const nick = (v) => (typeof v === 'string' && NICK.test(v) ? v : '');
  function normalizarEstado(o) {
    const r = o && typeof o === 'object' ? o : {};
    const log = r.log && typeof r.log === 'object' ? r.log : {};
    const b = r.bot && typeof r.bot === 'object' ? r.bot : {};
    const q = r.requisitos && typeof r.requisitos === 'object' ? r.requisitos : {};
    const activo = log.activo === true;
    return {
      reaccionar: r.reaccionar === true,
      log: { ruta: activo ? txt(log.ruta, 300) : '', activo, yo: activo ? nick(log.yo) : '' },
      bot: {
        instalado: b.instalado === true, instalando: b.instalando === true, conectando: b.conectando === true,
        conectado: b.conectado === true, servidor: txt(b.servidor, 260), nick: nick(b.nick), vida: de0a40(b.vida),
        hambre: de0a40(b.hambre), dia: boolONull(b.dia), lluvia: boolONull(b.lluvia), error: txt(b.error, 300),
      },
      requisitos: { node: typeof q.node === 'string' && NODE.test(q.node) ? q.node : null, node_ok: boolONull(q.node_ok), npm: boolONull(q.npm) },
      juego: r.juego === true, pensando: r.pensando === true, servicio: r.servicio === true,
    };
  }
  function normalizarConfig(o) {
    const r = o && typeof o === 'object' ? o : {};
    const c = r.config && typeof r.config === 'object' ? r.config : {};
    const b = r.bot && typeof r.bot === 'object' ? r.bot : {};
    const config = {};
    CONFIG_BOOL.forEach(([k]) => { config[k] = typeof c[k] === 'boolean' ? c[k] : CONFIG_DEFECTO[k]; });
    config.ruta_log = typeof c.ruta_log === 'string' ? c.ruta_log.slice(0, 1024) : '';
    const port = entero(b.port), pensar = entero(b.pensar_cada_s);
    return {
      config,
      bot: {
        host: txt(b.host, 253) || BOT_DEFECTO.host, port: port !== null && port >= 1 && port <= 65535 ? port : BOT_DEFECTO.port,
        version: txt(b.version, 16), usuario: txt(b.usuario, 16), dueno: txt(b.dueno, 16),
        pensar_cada_s: pensar !== null && pensar >= 10 && pensar <= 3600 ? pensar : BOT_DEFECTO.pensar_cada_s,
        defender: typeof b.defender === 'boolean' ? b.defender : true, solo_dueno: typeof b.solo_dueno === 'boolean' ? b.solo_dueno : true,
        estilo_frases: ESTILOS.some(([k]) => k === b.estilo_frases) ? b.estilo_frases : 'personaje',
      },
      error: txt(r.error, 300),
    };
  }
  function normalizarEvento(o) {
    const r = o && typeof o === 'object' ? o : null;
    if (!r || typeof r.tipo !== 'string' || !PALABRA.test(r.tipo)) return null;
    const t = typeof r.t === 'number' && fin(r.t) && r.t >= 0 ? r.t : 0;
    return { tipo: r.tipo, texto: txt(r.texto, 400), estado: typeof r.estado === 'string' && PALABRA.test(r.estado) ? r.estado : '',
      fuente: FUENTES.includes(r.fuente) ? r.fuente : '', t, entregado: r.entregado === true };
  }
  /** Chat del juego: de terceros, NO confiable. Solo {de (nick válido), texto (sin controles), t}. */
  function normalizarChat(o) {
    const r = o && typeof o === 'object' ? o : null;
    if (!r) return null;
    const de = nick(r.de), texto = txt(r.texto, 256);
    if (!de || !texto) return null;
    const t = typeof r.t === 'number' && fin(r.t) && r.t >= 0 ? r.t : 0;
    return { de, texto, t };
  }
  function textoBot(e) {
    const b = e.bot, q = e.requisitos;
    if (!e.servicio) return 'El bot va con la app abierta.';
    if (q.node_ok === false) return 'Hace falta Node.js 18 o más nuevo (nodejs.org) para el bot.';
    if (q.node_ok === null && !b.instalado) return 'Comprobando Node.js…';
    if (b.instalando) return 'Instalando el bot (~400 MB)… puede tardar unos minutos.';
    if (!b.instalado) return 'El bot no está instalado: Ajustes → Minecraft → «Instalar el bot».';
    if (b.conectado) return `Dentro de ${b.servidor || 'el servidor'} como ${b.nick || 'Lune'}.`;
    if (b.conectando) return `Conectando a ${b.servidor || 'el servidor'}…`;
    return b.error ? `Desconectado: ${b.error}` : 'Desconectado.';
  }
  function textoReacciones(e) {
    if (!e.reaccionar) return 'Reacciones apagadas.';
    if (!e.servicio) return 'Las reacciones van con la app abierta.';
    if (e.log.activo) return `Leyendo tu partida${e.log.yo ? ` como ${e.log.yo}` : ''}${e.juego ? ' (modo juego: lo guarda para el resumen o lo dice el bot)' : ''}.`;
    return 'Esperando a que abras Minecraft.';
  }
  /** Los datos del bot antes de mandarlos: {ok, errores: {campo: texto}} (Python lo vuelve a validar). */
  function validarBot(f) {
    const errores = {};
    const host = String(f.host || '').trim();
    if (!host || !HOST.test(host) || host.includes('://')) errores.host = 'Un nombre o una IP (sin http:// ni rutas).';
    const port = Number(f.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) errores.port = 'De 1 a 65535.';
    const version = String(f.version || '').trim();
    if (version && !VERSION.test(version)) errores.version = 'Como 1.21.1 (o vacía: la detecta).';
    for (const k of ['usuario', 'dueno']) {
      const v = String(f[k] || '').trim();
      if (v && !NICK.test(v)) errores[k] = 'De 3 a 16 letras, números o _.';
    }
    const u = String(f.usuario || '').trim(), d = String(f.dueno || '').trim();
    if (u && d && u.toLowerCase() === d.toLowerCase()) errores.usuario = 'No puede llamarse igual que tú.';
    const pensar = Number(f.pensar_cada_s);
    if (!Number.isInteger(pensar) || pensar < 30 || pensar > 3600) errores.pensar_cada_s = 'De 30 a 3600 s.';
    return { ok: !Object.keys(errores).length, errores };
  }
  function hora(t) {
    if (!t) return '';
    try { const d = new Date(t * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; } catch (e) { return ''; }
  }

  // ── Demo sin backend ───────────────────────────────────────────────────────
  const DEMO = (function () {
    const cfg = { ...CONFIG_DEFECTO };
    let bot = { ...BOT_DEFECTO, dueno: 'Steve' };
    const est = { instalado: false, instalando: false, conectado: false };
    const estado = () => ({ ...ESTADO_DEFECTO, reaccionar: cfg.reaccionar, servicio: true,
      bot: { ...ESTADO_DEFECTO.bot, ...est, servidor: est.conectado ? `${bot.host}:${bot.port}` : '', nick: est.conectado ? 'Lune' : '',
        vida: est.conectado ? 20 : null, hambre: est.conectado ? 18 : null, dia: est.conectado ? true : null },
      requisitos: { node: 'v24.0.0', node_ok: true, npm: true } });
    const emitir = () => emitirDemo('mc_estado', JSON.stringify(estado()));
    const config = () => ({ config: { ...cfg }, bot: { ...bot }, error: '' });
    return {
      mc_estado_json: () => JSON.stringify(estado()),
      mc_config: () => JSON.stringify(config()),
      mc_config_guardar(j) {
        const o = leer(j, {});
        const v = validarBot({ ...bot, ...o });
        if (!v.ok) return JSON.stringify({ ok: false, error: Object.values(v.errores)[0], config: config() });
        Object.keys(o).forEach((k) => { if (k in cfg) cfg[k] = o[k]; else if (k in bot) bot[k] = o[k]; });
        emitir();
        return JSON.stringify({ ok: true, error: '', config: config() });
      },
      mc_bot_instalar() { est.instalado = true; emitir(); return JSON.stringify({ ok: true, texto: 'Demo: en la app descargaría ~400 MB.', estado: estado() }); },
      mc_bot_conectar() {
        if (!est.instalado) return JSON.stringify({ ok: false, texto: 'Instala el bot en Ajustes → Minecraft (descarga ~400 MB).', estado: estado() });
        est.conectado = true; emitir();
        emitirDemo('mc_evento', JSON.stringify({ tipo: 'bot_conectado', texto: 'Ya estoy dentro.', estado: 'happy', fuente: 'bot', t: Date.now() / 1000, entregado: true }));
        return JSON.stringify({ ok: true, texto: 'Demo: conectado.', estado: estado() });
      },
      mc_bot_desconectar() { const b = est.conectado; est.conectado = false; emitir(); return b; },
      mc_orden(t) { return JSON.stringify(est.conectado ? { ok: true, texto: `Demo: «${txt(t, 40)}» mandado.` } : { ok: false, texto: 'El bot no está conectado.' }); },
      mc_decir(t) { return JSON.stringify(est.conectado ? { ok: true, texto: 'Dicho.' } : { ok: false, texto: 'El bot no está conectado.' }); },
      mc_log_detectar: () => JSON.stringify({ ok: false, rutas: [], sugerida: '', actual: cfg.ruta_log }),
      mc_eventos: () => '[]',
    };
  })();

  // ── Estilos propios ────────────────────────────────────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-mc-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-mc-css';
      st.textContent = `
        .ln-mc-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-mc-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-mc-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-mc-estado.is-on{ border-left-color:var(--yellow-500); box-shadow:inset 0 0 18px rgb(var(--yellow-500-rgb, 255 224 0) / .08); }
        .ln-mc-estado-tx{ flex:1; min-width:200px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-mc-stats{ display:flex; gap:14px; flex-wrap:wrap; margin-top:10px; font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-mc-botones{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; align-items:flex-end; }
        .ln-mc-fila{ display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap; margin-top:10px; }
        .ln-mc-fila .lune-field{ flex:1; min-width:180px; }
        .ln-mc-rejilla{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:10px; margin-top:8px; }
        .ln-mc-aviso{ margin:10px 0 0; padding:10px 12px; font-size:12px; line-height:1.5; color:var(--text);
          background:rgb(var(--yellow-500-rgb, 255 224 0) / .07); border:var(--bw) solid var(--yellow-600);
          border-left:var(--bw-bold) solid var(--yellow-500); clip-path:var(--clip-tr); }
        .ln-mc-lista{ display:flex; flex-direction:column; gap:4px; max-height:260px; overflow:auto; margin-top:8px; padding-right:4px; }
        .ln-mc-ev{ display:grid; grid-template-columns:44px 96px 1fr; gap:8px; align-items:baseline; font-size:12.5px; padding:5px 8px;
          background:rgb(var(--ink-950-rgb, 5 7 15) / .5); border-left:var(--bw-bold) solid rgb(var(--cyan-500-rgb, 0 229 255) / .45); }
        .ln-mc-ev.is-no{ opacity:.65; border-left-color:rgb(var(--cyan-500-rgb, 0 229 255) / .15); }
        .ln-mc-hora{ font-family:var(--font-mono); font-size:11px; color:var(--text-faint); }
        .ln-mc-tipo{ font-family:var(--font-mono); font-size:11px; color:var(--cyan-300); text-transform:uppercase; }
        .ln-mc-chat{ display:grid; grid-template-columns:44px auto 1fr; gap:8px; font-size:12.5px; padding:4px 8px; background:rgb(var(--ink-950-rgb, 5 7 15) / .4); }
        .ln-mc-de{ font-family:var(--font-mono); font-weight:700; color:var(--yellow-500); }
        .ln-mc-txt{ color:var(--text); overflow-wrap:anywhere; white-space:pre-wrap; }
        .ln-mc-log{ margin-top:8px; max-height:180px; overflow:auto; padding:8px 10px; font-family:var(--font-mono); font-size:11px; line-height:1.5;
          color:var(--text-muted); background:var(--ink-950); border:var(--bw) dashed rgb(var(--cyan-500-rgb, 0 229 255) / .35); white-space:pre-wrap; }
        .ln-mc-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-mc-msg.is-error{ color:var(--yellow-500); }
        .ln-mc-msg.is-ok{ color:var(--cyan-300); }
        .ln-mc-vacio{ font-size:12.5px; color:var(--text-dim); padding:6px 0; }
        .ln-mc-select{ width:100%; }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // ── Piezas comunes ─────────────────────────────────────────────────────────
  const IconoCubo = (p) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
      <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <path d="m3.3 7 8.7 5 8.7-5M12 22V12" />
    </svg>
  );
  const Msg = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-mc-msg${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);
  function useVivo() {
    const vivo = useRef(true);
    useEffect(() => { vivo.current = true; inyectarEstilos(); return () => { vivo.current = false; }; }, []);
    return vivo;
  }
  /** Estado del bot y las reacciones (mc_estado). */
  function useEstadoMC(vivo) {
    const [e, setE] = useState(ESTADO_DEFECTO);
    const poner = (o) => { if (vivo.current) setE(normalizarEstado(o)); };
    useEffect(() => {
      const quitar = [];
      const al = (j) => poner(leer(j, {}));
      const cablear = () => { quitar.push(conectar('mc_estado', al)); pedir('mc_estado_json', [], al); };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    return [e, poner];
  }
  const respuesta = (vivo, setMsg, poner) => (j) => {
    const r = leer(j, {});
    if (!vivo.current || !r) return;
    if (r.estado && poner) poner(r.estado);
    if (r.texto) setMsg({ texto: txt(r.texto, 300), ok: r.ok === true, error: r.ok !== true });
  };
  function BotonesBot({ e, poner, vivo, setMsg, instalar }) {
    const { Button } = window.LUNE;
    const b = e.bot;
    const conectarBot = () => {
      const via = pedir('mc_bot_conectar', [], respuesta(vivo, setMsg, poner));
      if (!via) setMsg({ texto: 'El bot no está disponible en esta versión de la app.', error: true });
    };
    const desconectarBot = () => pedir('mc_bot_desconectar', [], (ok) => { if (vivo.current) setMsg(ok ? { texto: 'Desconecto el bot.', ok: true } : { texto: 'El bot no estaba conectado.', error: true }); });
    return (
      <div className="ln-mc-botones">
        {instalar && (
          // Con el bot en marcha no se reinstala: npm ci borra node_modules, que está usando.
          <Button size="sm" variant={b.instalado ? 'ghost' : 'primary'}
            disabled={b.instalando || b.conectado || b.conectando || e.requisitos.node_ok === false || !e.servicio}
            title={b.conectado || b.conectando ? 'Desconecta el bot para reinstalarlo' : undefined}
            onClick={instalar}>{b.instalando ? 'Instalando…' : b.instalado ? 'Reinstalar el bot' : 'Instalar el bot (~400 MB)'}</Button>
        )}
        {b.conectado || b.conectando
          ? <Button size="sm" variant="secondary" onClick={desconectarBot}>Desconectar</Button>
          : <Button size="sm" variant="primary" disabled={!b.instalado || b.instalando} onClick={conectarBot}>Conectar</Button>}
      </div>
    );
  }

  // ── MinecraftPanel (vista «minecraft») ─────────────────────────────────────
  function MinecraftPanel() {
    const { Card, Button, Badge, Input, Switch } = window.LUNE;
    const vivo = useVivo();
    const [e, poner] = useEstadoMC(vivo);
    const [eventos, setEventos] = useState([]);
    const [chat, setChat] = useState([]);
    const [log, setLog] = useState([]);
    const [orden, setOrden] = useState('');
    const [dicho, setDicho] = useState('');
    const [msg, setMsg] = useState(null);
    useEffect(() => {
      const quitar = [];
      const alEvento = (j) => { const o = normalizarEvento(leer(j, null)); if (o && vivo.current) setEventos((l) => [...l, o].slice(-MAX_EVENTOS)); };
      const alChat = (j) => { const o = normalizarChat(leer(j, null)); if (o && vivo.current) setChat((l) => [...l, o].slice(-MAX_CHAT)); };
      const alLog = (s) => { const t = txt(s, 300); if (t && vivo.current) setLog((l) => [...l, t].slice(-MAX_LOG)); };
      const cablear = () => {
        quitar.push(conectar('mc_evento', alEvento));
        quitar.push(conectar('mc_chat', alChat));
        quitar.push(conectar('mc_log', alLog));
        pedir('mc_eventos', [], (j) => {
          const l = leer(j, []);
          if (vivo.current && Array.isArray(l)) setEventos(l.map(normalizarEvento).filter(Boolean).slice(-MAX_EVENTOS));
        });
      };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    const mandar = (t) => {
      const s = String(t || '').trim();
      if (!s) return;
      if (s.length > MAX_ORDEN) { setMsg({ texto: 'Esa orden es demasiado larga.', error: true }); return; }
      pedir('mc_orden', [s], respuesta(vivo, setMsg));
    };
    const decir = () => {
      const s = dicho.trim();
      if (!s) return;
      if (s.length > MAX_DECIR) { setMsg({ texto: `Como mucho ${MAX_DECIR} letras.`, error: true }); return; }
      pedir('mc_decir', [s], (j) => { respuesta(vivo, setMsg)(j); const r = leer(j, {}); if (r && r.ok && vivo.current) setDicho(''); });
    };
    const reaccionar = (on) => pedir('mc_config_guardar', [JSON.stringify({ reaccionar: !!on })], (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      setMsg(r && r.ok ? { texto: on ? 'Reacciono a tu partida.' : 'Ya no reacciono a Minecraft.', ok: true } : { texto: txt(r && r.error, 200) || 'No pude guardar.', error: true });
      pedir('mc_estado_json', [], (x) => poner(leer(x, {})));
    });
    const b = e.bot;
    const conectado = b.conectado;
    const badge = conectado ? ['DENTRO', 'yellow'] : b.conectando ? ['CONECTANDO', 'ink'] : b.instalando ? ['INSTALANDO', 'ink']
      : !b.instalado ? ['SIN INSTALAR', 'ink'] : ['FUERA', 'ink'];
    return (
      <div className="ln-settings ln-minecraft">
        <div className="ln-settings-inner">
          <header className="ln-settings-head">
            <div className="lune-overline">// Integración · Minecraft</div>
            <h2 className="ln-settings-title"><span>MINECRAFT</span></h2>
          </header>

          <Card id="mc-bot" eyebrow={<><IconoCubo width={13} height={13}/> Bot de Lune</>} title="Lune en tu mundo" tone="cyan" tick={conectado}>
            {!puente() && <p className="ln-mc-nota">Demo sin la app: el bot no se conecta a nada.</p>}
            <div className={`ln-mc-estado${conectado ? ' is-on' : ''}`}>
              <Badge variant={badge[1]} outline={badge[1] === 'ink'}>{badge[0]}</Badge>
              <span className="ln-mc-estado-tx">{textoBot(e)}</span>
            </div>
            {conectado && (
              <div className="ln-mc-stats" aria-label="Estado del bot">
                {b.vida !== null && <span>♥ {b.vida}/20</span>}
                {b.hambre !== null && <span>🍗 {b.hambre}/20</span>}
                {b.dia !== null && <span>{b.dia ? '☀ día' : '☾ noche'}</span>}
                {b.lluvia === true && <span>☂ lluvia</span>}
                {e.juego && <span>modo juego: piensa solo si se lo pides</span>}
              </div>
            )}
            <BotonesBot e={e} poner={poner} vivo={vivo} setMsg={setMsg} />
            {!b.instalado && e.servicio && (
              <div className="ln-mc-botones">
                <Button size="sm" variant="ghost" onClick={() => irAVista('settings', 'aj-minecraft')}>Ir a Ajustes → Minecraft</Button>
              </div>
            )}
            <div className="ln-mc-sub">Órdenes</div>
            <div className="ln-mc-botones" style={{ marginTop: 0 }}>
              {ORDENES_RAPIDAS.map(([t, et]) => (
                <Button key={t} size="sm" variant="secondary" disabled={!conectado} onClick={() => mandar(t)}>{et}</Button>
              ))}
            </div>
            <div className="ln-mc-fila">
              <Input id="f-mc-orden" label="Otra orden" placeholder="mina 10 hierro, tala, ataca zombie, dame pan…" value={orden} maxLength={MAX_ORDEN}
                onChange={(ev) => setOrden(String(ev.target.value || ''))} onKeyDown={(ev) => { if (ev.key === 'Enter') { mandar(orden); setOrden(''); } }} />
              <Button size="sm" variant="primary" disabled={!conectado || !orden.trim()} onClick={() => { mandar(orden); setOrden(''); }}>Mandar</Button>
            </div>
            <div className="ln-mc-fila">
              <Input id="f-mc-decir" label="Decir en el chat del juego" placeholder="¡hola a todos!" value={dicho} maxLength={MAX_DECIR}
                onChange={(ev) => setDicho(String(ev.target.value || ''))} onKeyDown={(ev) => { if (ev.key === 'Enter') decir(); }} />
              <Button size="sm" variant="secondary" disabled={!conectado || !dicho.trim()} onClick={decir}>Decir</Button>
            </div>
            <Msg msg={msg} />
          </Card>

          <Card id="mc-actividad" eyebrow="Tu partida" title="Qué hace Lune" tone="blue">
            <div className="ln-toggle-row">
              <Switch label="Reaccionar a lo que pasa en tu partida" checked={e.reaccionar} onChange={(ev) => reaccionar(!!ev.target.checked)} />
            </div>
            <p className="ln-mc-nota" style={{ marginTop: 8 }}>{textoReacciones(e)}</p>
            <div className="ln-mc-sub">Lo que dijo o apuntó</div>
            <div className="ln-mc-lista" aria-live="polite">
              {eventos.length === 0 && <p className="ln-mc-vacio">Nada todavía. Muertes, logros y conexiones salen aquí.</p>}
              {eventos.slice().reverse().map((ev, i) => (
                <div key={`${ev.t}-${i}`} className={`ln-mc-ev${ev.entregado ? '' : ' is-no'}`}>
                  <span className="ln-mc-hora">{hora(ev.t)}</span>
                  <span className="ln-mc-tipo">{NOMBRES_EVENTO[ev.tipo] || ev.tipo}</span>
                  <span className="ln-mc-txt">{ev.texto}</span>
                </div>
              ))}
            </div>
            <div className="ln-mc-sub">Chat del juego</div>
            <div className="ln-mc-lista">
              {chat.length === 0 && <p className="ln-mc-vacio">Con el bot dentro, aquí sale el chat (solo como texto).</p>}
              {chat.map((c, i) => (
                <div key={`${c.t}-${i}`} className="ln-mc-chat">
                  <span className="ln-mc-hora">{hora(c.t)}</span>
                  <span className="ln-mc-de">{c.de}</span>
                  <span className="ln-mc-txt">{c.texto}</span>
                </div>
              ))}
            </div>
            {log.length > 0 && (
              <>
                <div className="ln-mc-sub">Registro del bot</div>
                <div className="ln-mc-log">{log.join('\n')}</div>
              </>
            )}
            <p className="ln-mc-nota" style={{ marginTop: 12 }}>{PRIVACIDAD}</p>
          </Card>
        </div>
      </div>
    );
  }

  // ── MinecraftCard (Ajustes) ────────────────────────────────────────────────
  function MinecraftCard() {
    const { Card, Button, Switch, Input } = window.LUNE;
    const vivo = useVivo();
    const [e, poner] = useEstadoMC(vivo);
    const [cfg, setCfg] = useState(normalizarConfig({}));
    const [form, setForm] = useState(BOT_DEFECTO);
    const [tocado, setTocado] = useState(false);
    const [rutas, setRutas] = useState([]);
    const [msg, setMsg] = useState(null);
    const [msgBot, setMsgBot] = useState(null);
    const tocadoRef = useRef(false);
    tocadoRef.current = tocado;
    const aplicar = (o) => {
      const c = normalizarConfig(o);
      setCfg(c);
      if (!tocadoRef.current) setForm(c.bot);
      if (c.error) setMsg({ texto: c.error, error: true });
    };
    useEffect(() => {
      const cablear = () => pedir('mc_config', [], (j) => { if (vivo.current) aplicar(leer(j, {})); });
      const q = alListo(cablear);
      if (!puente()) cablear();
      return q;
    }, []);
    const guardar = (parcial, setM, okTexto, alOk) => {
      const via = pedir('mc_config_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.ok && alOk) alOk();
        if (r && r.config) aplicar(r.config);
        setM(r && r.ok ? { texto: okTexto, ok: true } : { texto: txt(r && r.error, 300) || 'No pude guardar.', error: true });
      });
      if (!via) setM({ texto: 'Esto no está disponible en esta versión de la app.', error: true });
    };
    const detectar = () => pedir('mc_log_detectar', [], (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      const l = (Array.isArray(r.rutas) ? r.rutas : []).filter((x) => typeof x === 'string' && x.length <= 1024).slice(0, 64);
      setRutas(l);
      if (!l.length) { setMsg({ texto: 'No encontré ningún latest.log. Abre Minecraft una vez y vuelve a probar.', error: true }); return; }
      const sug = l.includes(r.sugerida) ? r.sugerida : l[0];
      if (sug !== cfg.config.ruta_log) guardar({ ruta_log: sug }, setMsg, `Usaré ${sug}.`);
      else setMsg({ texto: `Ya uso ${sug}.`, ok: true });
    });
    const instalar = () => {
      const via = pedir('mc_bot_instalar', [], respuesta(vivo, setMsgBot, poner));
      if (!via) setMsgBot({ texto: 'Instalar no está disponible en esta versión de la app.', error: true });
    };
    const val = validarBot(form);
    const campo = (k) => (ev) => { setTocado(true); const v = ev.target.value; setForm((f) => ({ ...f, [k]: v })); };
    const numero = (k) => (ev) => { setTocado(true); const v = Math.round(Number(ev.target.value)); setForm((f) => ({ ...f, [k]: Number.isFinite(v) ? v : 0 })); };
    const guardarBot = () => {
      if (!val.ok) { setMsgBot({ texto: Object.values(val.errores)[0], error: true }); return; }
      const d = { host: String(form.host).trim(), port: Number(form.port), version: String(form.version || '').trim(),
        usuario: String(form.usuario || '').trim(), dueno: String(form.dueno || '').trim(), pensar_cada_s: Number(form.pensar_cada_s),
        defender: !!form.defender, solo_dueno: !!form.solo_dueno, estilo_frases: form.estilo_frases };
      guardar(d, setMsgBot, 'Datos del bot guardados.', () => setTocado(false));
    };
    const opciones = [...new Set([...(cfg.config.ruta_log ? [cfg.config.ruta_log] : []), ...rutas])];
    const Err = ({ k }) => (val.errores[k] ? <span className="ln-mc-msg is-error" style={{ margin: 0 }}>{val.errores[k]}</span> : null);
    return (
      <Card id="aj-minecraft" eyebrow={<><IconoCubo width={13} height={13}/> Integraciones · Minecraft</>} title="Minecraft" tone="blue"
        tick={e.bot.conectado || (e.reaccionar && e.log.activo)}>
        <p className="ln-mc-nota">
          Lune comenta tu partida (muertes, logros, quién entra) leyendo el latest.log, sin tocar el juego. Y puede entrar ella
          misma con un bot que te sigue, mina o te defiende, con su personaje.
        </p>
        <div className="ln-mc-sub">Reacciones</div>
        <div className="ln-toggle-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
          {CONFIG_BOOL.map(([k, et]) => (
            <Switch key={k} label={et} checked={cfg.config[k]} onChange={(ev) => guardar({ [k]: !!ev.target.checked }, setMsg, 'Guardado.')} />
          ))}
        </div>
        <div className="ln-mc-fila">
          <div className="lune-field">
            <label className="lune-field-label" htmlFor="f-mc-log">Registro de la partida</label>
            <select id="f-mc-log" className="lune-input ln-mc-select" value={cfg.config.ruta_log}
              onChange={(ev) => guardar({ ruta_log: String(ev.target.value || '') }, setMsg, 'Guardado.')}>
              <option value="">Automático (el más reciente)</option>
              {opciones.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <Button size="sm" variant="secondary" onClick={detectar}>Detectar</Button>
        </div>
        <Msg msg={msg} />

        <div className="ln-mc-sub">Bot de Minecraft</div>
        <p className="ln-mc-aviso" role="note">{AVISO_ONLINE_MODE}</p>
        <div className={`ln-mc-estado${e.bot.conectado ? ' is-on' : ''}`} style={{ marginTop: 10 }}>
          <span className="ln-mc-estado-tx">{textoBot(e)}</span>
        </div>
        <div className="ln-mc-rejilla">
          <div><Input id="f-mc-host" label="Servidor" placeholder="localhost" value={form.host} maxLength={253} error={!!val.errores.host} onChange={campo('host')} /><Err k="host" /></div>
          <div className="lune-field">
            <label className="lune-field-label" htmlFor="f-mc-port">Puerto</label>
            <input id="f-mc-port" className="lune-input" type="number" min={1} max={65535} step={1} value={form.port} onChange={numero('port')} />
            <Err k="port" />
          </div>
          <div><Input id="f-mc-version" label="Versión" placeholder="vacía = la detecta" value={form.version} maxLength={12} error={!!val.errores.version} onChange={campo('version')} /><Err k="version" /></div>
          <div><Input id="f-mc-usuario" label="Nick del bot" placeholder="el nombre de Lune" value={form.usuario} maxLength={16} error={!!val.errores.usuario} onChange={campo('usuario')} /><Err k="usuario" /></div>
          <div><Input id="f-mc-dueno" label="Tu nick (dueño)" placeholder="tu nick de Minecraft" value={form.dueno} maxLength={16} error={!!val.errores.dueno} onChange={campo('dueno')} /><Err k="dueno" /></div>
          <div className="lune-field">
            <label className="lune-field-label" htmlFor="f-mc-pensar">Pensar cada (s)</label>
            <input id="f-mc-pensar" className="lune-input" type="number" min={30} max={3600} step={5} value={form.pensar_cada_s} onChange={numero('pensar_cada_s')} />
            <Err k="pensar_cada_s" />
          </div>
        </div>
        <div className="ln-toggle-row" style={{ marginTop: 10 }}>
          <Switch label="Solo obedece al dueño" checked={!!form.solo_dueno} onChange={(ev) => { setTocado(true); const v = !!ev.target.checked; setForm((f) => ({ ...f, solo_dueno: v })); }} />
          <Switch label="Te defiende de los monstruos" checked={!!form.defender} onChange={(ev) => { setTocado(true); const v = !!ev.target.checked; setForm((f) => ({ ...f, defender: v })); }} />
        </div>
        {form.solo_dueno && <p className="ln-mc-aviso" role="note">{AVISO_SUPLANTACION}</p>}
        <div className="ln-mc-botones">
          {ESTILOS.map(([k, t]) => (
            <Button key={k} size="sm" variant={form.estilo_frases === k ? 'primary' : 'ghost'} aria-pressed={form.estilo_frases === k}
              onClick={() => { setTocado(true); setForm((f) => ({ ...f, estilo_frases: k })); }}>{t}</Button>
          ))}
          <Button size="sm" variant="secondary" disabled={!tocado || !val.ok} onClick={guardarBot}>Guardar datos del bot</Button>
        </div>
        <BotonesBot e={e} poner={poner} vivo={vivo} setMsg={setMsgBot} instalar={instalar} />
        <Msg msg={msgBot} />
        <p className="ln-mc-nota" style={{ marginTop: 12 }}>{PRIVACIDAD}</p>
        <div className="ln-mc-botones">
          <Button size="sm" variant="ghost" onClick={() => irAVista('minecraft')}>Abrir el panel de Minecraft</Button>
        </div>
      </Card>
    );
  }

  Object.assign(window, {
    MinecraftPanel, MinecraftCard,
    LuneMinecraftWeb: {
      normalizarEstado, normalizarConfig, normalizarEvento, normalizarChat, textoBot, textoReacciones, validarBot,
      ORDENES_RAPIDAS, AVISO_SUPLANTACION, AVISO_ONLINE_MODE, PRIVACIDAD, ESTADO_DEFECTO,
    },
  });
})();
