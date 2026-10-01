/* Lune CD desktop — Sentarse, comida, Discord y arranque con Windows (cortes 7 y 8).
 *
 * SentarseCard        Ajustes: sentarse en la barra de tareas (al soltarla encima), en ventanas (apagado por
 *                     defecto; al activarlo pide confirmar con el aviso anticheat, como Mate-Engine), ajuste de
 *                     altura −64..64 px (guardado diferido), el estado y «Sentarse en la barra» / «En una
 *                     ventana» / «Bajar».
 * ComidaCard          la comida con el clic central (activa), «Batido», «Pastel», «Guardar» y lo que hay en la mano.
 * DiscordCard         la presencia (activa), el Application ID (17–20 cifras; sin él no hace nada), enseñar el
 *                     modelo 3D, el enlace del botón (https), el estado de la conexión, la nota de privacidad y
 *                     la línea «Discord ve: …» (solo los textos fijos: nunca títulos de ventana ni el chat).
 *                     Sin conectar: «Reconectar» (luneVida.discord_reconectar) y el `motivo` con el siguiente
 *                     paso (Discord cerrado, sin Application ID, otra Lune ya publica…).
 * AutoinicioOpciones  ({activo}) bajo el interruptor «Arrancar con Windows» de settings.jsx: en la bandeja / con
 *                     la asistente en escritorio / con la ventana, esperar N s (0–120) y el estado de la entrada (desactivada
 *                     desde el Administrador de tareas, carpeta movida…).
 * ComidaWeb           global (app.jsx): con la flotante guardada, la comida sigue al ratón dentro de la ventana
 *                     (SVG procedural del color de la variante, pointer-events: none, balanceo al moverla). Un
 *                     tramo del ratón que ENTRA en la cabeza de Lune de la barra (window.__luneCabezaBarra(), de
 *                     sidebar.jsx) con 0.35 s de enfriamiento → luneVida.comida_evento(id) + evento de window
 *                     'lune-asistente-cara' {estado: 'happy', ms: 2500} (app.jsx pone la cara). Esc o 2 minutos sin
 *                     mover el ratón → luneVida.comida_guardar(). Los sonidos los pone Python (Mezclador).
 * window.LuneVida     utilidades puras (tests): normalizar*, segmentoTocaCirculo, crearDetector, idDiscordValido,
 *                     urlBotonValida, publicacionSegura, textoDiscordVe, textoAutoinicio, textoAsiento…
 * Puente: window.luneVida (ui/puente_vida.py). Guardan al momento (config.set en Python). Sin puente (navegador),
 * una demo local. Se registra solo: Object.assign(window, {SentarseCard, ComidaCard, DiscordCard,
 * AutoinicioOpciones, ComidaWeb, LuneVida}).
 */
(function () {
  const { useState, useEffect, useRef, useMemo } = React;

  // ── Puente: window.luneVida (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneVida || null;
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

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const fin = Number.isFinite;
  const acotar = (v, a, b) => Math.min(b, Math.max(a, v));
  const entero = (v) => (typeof v === 'number' && fin(v) && Math.round(v) === v ? v : null);
  const txt = (v, max = 160) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, max) : '');
  const SITIOS = ['barra', 'ventana'];
  const OFFSET_MAX = 64;
  const RETRASO_MAX = 120;
  const COMOS = [['bandeja', 'En la bandeja'], ['asistente', 'Con la asistente en escritorio'], ['ventana', 'Con la ventana']];
  const ENFRIAMIENTO_MS = 350;                        // nucleo/comida.COOLDOWN_S
  const GUARDAR_SOLA_MS = 120000;                     // D4: 2 minutos sin moverla
  const MS_CARA = 2500;                               // nucleo/comida.MS_REACCION
  const CABEZA_MS = 100;                              // la cabeza de la barra a 10 Hz, como la flotante
  const TAM_COMIDA = 96;                              // ui/comida_qt.TAM_SIN_ASISTENTE
  const ID_OK = /^[a-z][a-z_]{0,23}$/;
  const COLOR_OK = /^#[0-9A-Fa-f]{6}$/;
  const ID_DISCORD = /^\d{17,20}$/;
  const ACCIONES_WEB = ['aparece', 'guarda', 'cambia'];
  const AVISO_ANTICHEAT = 'Para sentarse en ventanas, Lune lee la posición de las ventanas abiertas (sin tocarlas ni '
    + 'leer lo que hay dentro) y solo mueve la suya. Algunos anticheats de juegos online vigilan a los programas que '
    + 'miran ventanas: con un juego delante Lune no mira nada, pero si te preocupa, déjalo apagado.';
  const PRIVACIDAD = 'Discord solo recibe «Lune CD · <modo>» y un estado fijo (bailando, durmiendo, sentada…). Nunca '
    + 'títulos de ventanas, programas, el chat, el personaje ni tus alarmas; con un juego delante, nada.';
  // Lo único que puede salir en «Discord ve:» (los textos fijos de servicios/discord_presencia.py).
  const DETALLES_DISCORD = ['Escritorio · 3D', 'Escritorio · animación', 'Escritorio · sprites', 'Ventana', 'Terminal'];
  const ESTADOS_DISCORD = ['Con una alarma sonando', 'En pantalla grande', 'Durmiendo en el salvapantallas',
    'En una llamada', 'Paseando por la pantalla', 'Bailando ♪', 'Merendando', 'Echando una siesta sentada',
    'Durmiendo (-_-) zzZ', 'Sentada en la barra de tareas', 'Sentada en una ventana', 'Pensando…', 'Hablando',
    'En el escritorio', 'Charlando', 'En la terminal'];
  const CATALOGO_DEMO = [
    { id: 'batido', nombre: 'Batido', tipo: 'beber', variantes: [
      { id: 'fresa', nombre: 'fresa', color: '#FF6FA8' }, { id: 'mango', nombre: 'mango', color: '#FFB547' },
      { id: 'matcha', nombre: 'matcha', color: '#8BC34A' }] },
    { id: 'pastel', nombre: 'Pastel', tipo: 'comer', variantes: [
      { id: 'chocolate', nombre: 'chocolate', color: '#6B3E26' }, { id: 'fresa', nombre: 'fresa', color: '#FF8FB1' },
      { id: 'limon', nombre: 'limón', color: '#FFE45C' }, { id: 'vainilla', nombre: 'vainilla', color: '#FFF1C9' }] },
  ];
  const ASIENTO_DEFECTO = { sentada: '', variante: 0, ventanas: false, barra: true, offset: 0, servicio: false,
    asistente: false, juego: false, arrastrando: false, cedida: false };
  const COMIDA_DEFECTO = { activa: false, id: '', variante: '', color: '', tipo: '', nombre: '', vista: '',
    disponible: true, servicio: false };
  const DISCORD_DEFECTO = { activo: false, conectado: false, usuario: '', error: '', motivo: '', client_id_ok: false, sin_id: false,
    publicando: null, vista_previa: null, servicio: false, config: { client_id: '', mostrar_modelo: false, boton_url: '' } };
  const AUTO_DEFECTO = { activo: false, registrado: false, aprobado: false, ruta_ok: false, modo_ok: false,
    como: 'bandeja', retraso_s: 20, disponible: false };

  function normalizarAsiento(o) {
    const r = o && typeof o === 'object' ? o : {};
    const off = entero(r.offset);
    const sentada = SITIOS.includes(r.sentada) ? r.sentada : '';
    const v = entero(r.variante);
    return {
      sentada, variante: sentada && v !== null ? acotar(v, 0, 7) : 0,
      ventanas: r.ventanas === true, barra: r.barra !== false,
      offset: off === null ? 0 : acotar(off, -OFFSET_MAX, OFFSET_MAX),
      servicio: r.servicio === true, asistente: r.asistente === true, juego: r.juego === true,
      arrastrando: r.arrastrando === true, cedida: r.cedida === true,
    };
  }
  function normalizarCatalogo(lista) {
    const out = [];
    for (const c of Array.isArray(lista) ? lista : []) {
      if (!c || typeof c !== 'object' || !ID_OK.test(String(c.id || '')) || !['beber', 'comer'].includes(c.tipo)) continue;
      const variantes = (Array.isArray(c.variantes) ? c.variantes : [])
        .filter((v) => v && ID_OK.test(String(v.id || '')) && COLOR_OK.test(String(v.color || '')))
        .map((v) => ({ id: v.id, nombre: txt(v.nombre, 24) || v.id, color: v.color }));
      if (variantes.length) out.push({ id: c.id, nombre: txt(c.nombre, 24) || c.id, tipo: c.tipo, variantes });
      if (out.length >= 12) break;
    }
    return out.length ? out : CATALOGO_DEMO;
  }
  function normalizarComida(o) {
    const r = o && typeof o === 'object' ? o : {};
    const activa = r.activa === true && ID_OK.test(String(r.id || '')) && ID_OK.test(String(r.variante || ''));
    return {
      activa, id: activa ? r.id : '', variante: activa ? r.variante : '',
      color: activa && COLOR_OK.test(String(r.color || '')) ? r.color : '',
      tipo: activa && ['beber', 'comer'].includes(r.tipo) ? r.tipo : '', nombre: activa ? txt(r.nombre, 24) : '',
      vista: activa && ['escritorio', 'web'].includes(r.vista) ? r.vista : '',
      disponible: r.disponible !== false, servicio: r.servicio === true,
    };
  }
  /** comida_web → {accion, id, variante, color, tipo, nombre} | null */
  function normalizarComidaWeb(o) {
    const r = o && typeof o === 'object' ? o : null;
    if (!r || !ACCIONES_WEB.includes(r.accion) || !ID_OK.test(String(r.id || ''))) return null;
    return {
      accion: r.accion, id: r.id, variante: ID_OK.test(String(r.variante || '')) ? r.variante : '',
      color: COLOR_OK.test(String(r.color || '')) ? r.color : '#FFFFFF',
      tipo: r.tipo === 'comer' ? 'comer' : 'beber', nombre: txt(r.nombre, 24),
    };
  }
  function idDiscordValido(s) { return typeof s === 'string' && (s === '' || ID_DISCORD.test(s)); }
  function bytesUtf8(s) { try { return unescape(encodeURIComponent(s)).length; } catch (e) { return Infinity; } }
  /** https con host «x.y», ≤ 512 bytes y sin espacios ni caracteres raros (como servicios/discord_presencia). */
  function urlBotonValida(s) {
    if (typeof s !== 'string' || !s || s !== s.trim() || bytesUtf8(s) > 512) return false;
    if (/[\s<>"'`\\\u0000-\u001f]/.test(s)) return false;
    const m = /^https:\/\/([^/?#@:]+)(:\d{1,5})?([/?#].*)?$/i.exec(s);
    return !!(m && /^[A-Za-z0-9.-]+$/.test(m[1]) && m[1].includes('.') && !m[1].startsWith('.') && !m[1].endsWith('.'));
  }
  /** {details, state} si son textos de la lista fija; si no, null (no se enseña). */
  function publicacionSegura(p) {
    if (!p || typeof p !== 'object' || typeof p.details !== 'string' || typeof p.state !== 'string') return null;
    const pre = 'Lune CD · ';
    if (!p.details.startsWith(pre) || !DETALLES_DISCORD.includes(p.details.slice(pre.length))) return null;
    if (!ESTADOS_DISCORD.includes(p.state)) return null;
    return { details: p.details, state: p.state };
  }
  function normalizarDiscord(o) {
    const r = o && typeof o === 'object' ? o : {};
    const c = r.config && typeof r.config === 'object' ? r.config : {};
    const conectado = r.conectado === true;
    return {
      activo: r.activo === true, conectado, usuario: conectado ? txt(r.usuario, 40) : '', error: txt(r.error, 160),
      motivo: conectado ? '' : txt(r.motivo, 200),       // por qué no conecta, con el siguiente paso
      client_id_ok: r.client_id_ok === true, sin_id: r.sin_id === true,
      publicando: conectado ? publicacionSegura(r.publicando) : null, vista_previa: publicacionSegura(r.vista_previa),
      servicio: r.servicio === true,
      config: {
        client_id: typeof c.client_id === 'string' && ID_DISCORD.test(c.client_id) ? c.client_id : '',
        mostrar_modelo: c.mostrar_modelo === true,
        boton_url: urlBotonValida(c.boton_url) ? c.boton_url : '',
      },
    };
  }
  function textoDiscordVe(e) {
    const d = normalizarDiscord(e);
    if (!d.activo) return 'Discord ve: nada (apagado).';
    const p = d.publicando || d.vista_previa;
    if (p) return `Discord ve: ${p.details} — ${p.state}`;
    if (!d.servicio) return 'Discord ve: lo verás aquí con la app abierta.';
    return 'Discord ve: nada ahora mismo (con un juego delante no se publica).';
  }
  function textoEstadoDiscord(e) {
    const d = normalizarDiscord(e);
    if (!d.activo) return 'Apagado.';
    if (d.sin_id || !d.config.client_id) return 'Falta el Application ID: sin él no se publica nada.';
    if (!d.servicio) return 'Se conecta con la app abierta (y Discord abierto).';
    if (d.conectado) return d.usuario ? `Conectado como ${d.usuario}.` : 'Conectado.';
    if (d.motivo) return d.motivo;
    return d.error ? `Sin conectar: ${d.error}` : 'Sin conectar (esperando a Discord).';
  }
  function normalizarAutoinicio(o) {
    const r = o && typeof o === 'object' ? o : {};
    const ret = entero(r.retraso_s);
    return {
      activo: r.activo === true, registrado: r.registrado === true, aprobado: r.aprobado === true,
      ruta_ok: r.ruta_ok === true, modo_ok: r.modo_ok === true,
      como: COMOS.some(([k]) => k === r.como) ? r.como : 'bandeja',
      retraso_s: ret === null ? 20 : acotar(ret, 0, 300), disponible: r.disponible === true,
    };
  }
  function textoAutoinicio(e, activo) {
    const a = normalizarAutoinicio(e);
    if (!a.disponible) return 'El arranque con Windows solo funciona en la app, en Windows.';
    if (a.registrado && !a.aprobado) {
      return 'Desactivado desde el Administrador de tareas (pestaña Inicio). Vuelve a activar el interruptor para que arranque.';
    }
    if (a.registrado && !a.ruta_ok) return 'La entrada apunta a otra carpeta: se corrige sola la próxima vez que abras Lune.';
    if (a.activo) return 'Lune arranca con Windows sin pantalla de inicio (en patata, con la consola minimizada).';
    return activo ? 'Guardando…' : 'Estas opciones se usan cuando actives «Arrancar con Windows».';
  }
  function textoAsiento(e) {
    const a = normalizarAsiento(e);
    if (a.sentada === 'barra') return 'Sentada en la barra de tareas.';
    if (a.sentada === 'ventana') return 'Sentada en una ventana.';
    if (!a.servicio) return 'Se sienta la asistente en escritorio (necesita la app).';
    if (a.juego) return 'Con un juego delante ni se sienta ni mira las ventanas.';
    if (a.cedida) return 'De pie mientras dura la alarma o la pantalla grande; luego vuelve a sentarse.';
    if (!a.asistente) return 'De pie. Saca a la asistente al escritorio para sentarla.';
    return 'De pie: arrástrala hasta la barra de tareas (o al borde de una ventana) y suéltala.';
  }

  /** ¿El segmento p0→p1 entra en el círculo (c, r)? Estrictamente dentro: la tangente no cuenta. */
  function segmentoTocaCirculo(p0, p1, c, r) {
    const n = [p0 && p0.x, p0 && p0.y, p1 && p1.x, p1 && p1.y, c && c.x, c && c.y, r].map(Number);
    if (!n.every(fin) || n[6] <= 0) return false;
    const [x0, y0, x1, y1, cx, cy, rr] = n;
    const dx = x1 - x0, dy = y1 - y0, l2 = dx * dx + dy * dy;
    const t = l2 <= 0 ? 0 : acotar(((cx - x0) * dx + (cy - y0) * dy) / l2, 0, 1);
    const px = x0 + t * dx, py = y0 + t * dy;
    return (px - cx) ** 2 + (py - cy) ** 2 < rr * rr;
  }
  function cabezaValida(c) {
    if (!c || typeof c !== 'object') return null;
    const x = Number(c.x), y = Number(c.y), r = Number(c.r);
    return fin(x) && fin(y) && fin(r) && r > 0 ? { x, y, r } : null;
  }
  /** El acierto de la comida, como nucleo/comida.GestorComida.al_mover: cuenta al ENTRAR en la cabeza (seguir
   *  dentro no cuenta; una pasada rápida que la cruza entera, sí), como mucho uno cada `enfriamientoMs`. */
  function crearDetector(enfriamientoMs = ENFRIAMIENTO_MS) {
    let dentro = false, siguiente = -Infinity;
    return {
      mover(t, p0, p1, cabeza) {
        const c = cabezaValida(cabeza);
        const toca = !!c && segmentoTocaCirculo(p0, p1, c, c.r);
        const acierto = toca && !dentro && t >= siguiente;
        if (acierto) siguiente = t + enfriamientoMs;
        dentro = !!c && segmentoTocaCirculo(p1, p1, c, c.r);
        return acierto;
      },
      reiniciar() { dentro = false; },
    };
  }
  function leerCabeza() {
    const f = window.__luneCabezaBarra;
    if (typeof f !== 'function') return null;
    try { return cabezaValida(f()); } catch (e) { return null; }
  }
  function nombreEnMano(e, catalogo) {
    const c = (catalogo || CATALOGO_DEMO).find((x) => x.id === e.id);
    const v = c && c.variantes.find((x) => x.id === e.variante);
    return c ? `${c.nombre.toLowerCase()}${v ? ` de ${v.nombre}` : ''}` : (e.nombre || e.id).toLowerCase();
  }

  // ── Demo sin backend ───────────────────────────────────────────────────────
  const DEMO = (function () {
    const cfg = { avatar: { ventanas: false, barra: true, offset: 0 }, comida: true,
      discord: { activo: false, client_id: '', mostrar_modelo: false, boton_url: '' }, como: 'bandeja', retraso_s: 20 };
    let sentada = '';
    let mano = null;                                   // {id, variante}
    const asiento = () => ({ ...ASIENTO_DEFECTO, ...cfg.avatar, sentada, servicio: true, asistente: true });
    const comida = () => {
      const c = mano && CATALOGO_DEMO.find((x) => x.id === mano.id);
      const v = c && c.variantes.find((x) => x.id === mano.variante);
      return c && v ? { activa: true, id: c.id, variante: v.id, color: v.color, tipo: c.tipo, nombre: c.nombre,
        vista: 'web', disponible: cfg.comida, servicio: true } : { ...COMIDA_DEFECTO, disponible: cfg.comida, servicio: true };
    };
    const web = (accion) => {
      const e = comida();
      const c = CATALOGO_DEMO.find((x) => x.id === (mano || {}).id);
      emitirDemo('comida_web', JSON.stringify({ accion, id: e.id || (c && c.id), variante: e.variante, color: e.color,
        tipo: e.tipo, nombre: e.nombre }));
    };
    const discord = () => ({ ...DISCORD_DEFECTO, activo: cfg.discord.activo, sin_id: cfg.discord.activo && !cfg.discord.client_id,
      client_id_ok: ID_DISCORD.test(cfg.discord.client_id), config: { ...cfg.discord },
      vista_previa: cfg.discord.activo ? { details: 'Lune CD · Ventana', state: 'Charlando' } : null });
    const auto = () => ({ ...AUTO_DEFECTO, como: cfg.como, retraso_s: cfg.retraso_s });
    const ok = (estado) => JSON.stringify({ ok: true, error: '', estado });
    return {
      asiento_estado: () => JSON.stringify(asiento()),
      asiento_config_guardar(j) {
        const o = leer(j, {});
        if (typeof o.ventanas === 'boolean') cfg.avatar.ventanas = o.ventanas;
        if (typeof o.barra === 'boolean') cfg.avatar.barra = o.barra;
        if (entero(o.offset) !== null) cfg.avatar.offset = acotar(o.offset, -OFFSET_MAX, OFFSET_MAX);
        return ok(asiento());
      },
      asiento_sentar(sitio) {
        if (sitio === 'ventana' && !cfg.avatar.ventanas) {
          return JSON.stringify({ ok: false, texto: 'Sentarme en ventanas está desactivado (Ajustes → Sentarse).', estado: asiento() });
        }
        sentada = sitio;
        return JSON.stringify({ ok: true, texto: `Demo: me senté en ${sitio === 'barra' ? 'la barra de tareas' : 'una ventana'}.`, estado: asiento() });
      },
      asiento_bajar() { const b = !!sentada; sentada = ''; return b; },
      comida_estado: () => JSON.stringify({ ...comida(), catalogo: CATALOGO_DEMO }),
      comida_alternar(id) {
        const c = CATALOGO_DEMO.find((x) => x.id === id);
        if (!c) return JSON.stringify({ ok: false, accion: '', motivo: 'desconocida', texto: 'Esa comida no existe.', estado: comida() });
        if (!cfg.comida) return JSON.stringify({ ok: false, accion: '', motivo: 'desactivada', texto: 'La comida está desactivada.', estado: comida() });
        let accion;
        if (mano && mano.id === id) { web('guarda'); mano = null; accion = 'guarda'; }
        else { accion = mano ? 'cambia' : 'aparece'; mano = { id, variante: c.variantes[0].id }; web(accion); }
        return JSON.stringify({ ok: true, accion, motivo: '', texto: '', estado: comida() });
      },
      comida_guardar() { if (!mano) return false; web('guarda'); mano = null; return true; },
      comida_evento: () => !!mano,
      comida_config_guardar(j) { const o = leer(j, {}); if (typeof o.activa === 'boolean') cfg.comida = o.activa; return ok(comida()); },
      discord_estado: () => JSON.stringify(discord()),
      discord_alternar() { cfg.discord.activo = !cfg.discord.activo; return cfg.discord.activo; },
      discord_reconectar: () => JSON.stringify({ ok: false, texto: 'Demo: me conecto a Discord con la app abierta.',
        estado: discord() }),
      discord_config_guardar(j) {
        const o = leer(j, {});
        if (typeof o.client_id === 'string' && !idDiscordValido(o.client_id)) {
          return JSON.stringify({ ok: false, error: 'El Application ID son de 17 a 20 cifras.', estado: discord() });
        }
        if (typeof o.boton_url === 'string' && o.boton_url && !urlBotonValida(o.boton_url)) {
          return JSON.stringify({ ok: false, error: 'El enlace del botón tiene que ser https://.', estado: discord() });
        }
        ['activo', 'mostrar_modelo'].forEach((k) => { if (typeof o[k] === 'boolean') cfg.discord[k] = o[k]; });
        ['client_id', 'boton_url'].forEach((k) => { if (typeof o[k] === 'string') cfg.discord[k] = o[k]; });
        return ok(discord());
      },
      autoinicio_estado: () => JSON.stringify(auto()),
      autoinicio_opciones(j) {
        const o = leer(j, {});
        if (COMOS.some(([k]) => k === o.como)) cfg.como = o.como;
        if (entero(o.retraso_s) !== null) cfg.retraso_s = acotar(o.retraso_s, 0, RETRASO_MAX);
        return ok(auto());
      },
    };
  })();

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-vida-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-vida-css';
      st.textContent = `
        .ln-vd-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-vd-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-vd-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-vd-estado.is-on{ border-left-color:var(--yellow-500); box-shadow:inset 0 0 18px rgb(var(--yellow-500-rgb, 255 224 0) / .08); }
        .ln-vd-estado-tx{ flex:1; min-width:180px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-vd-botones{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
        .ln-vd-aviso{ margin:10px 0 0; padding:10px 12px; font-size:12px; line-height:1.5; color:var(--text);
          background:rgb(var(--yellow-500-rgb, 255 224 0) / .07); border:var(--bw) solid var(--yellow-600);
          border-left:var(--bw-bold) solid var(--yellow-500); clip-path:var(--clip-tr); }
        .ln-vd-aviso p{ margin:0 0 8px; }
        .ln-vd-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-vd-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-vd-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-vd-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-vd-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-vd-fila{ display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap; margin-top:10px; }
        .ln-vd-fila .lune-field{ flex:1; min-width:200px; }
        .ln-vd-mano{ display:inline-flex; align-items:center; gap:8px; }
        .ln-vd-muestra{ width:14px; height:14px; border:var(--bw) solid var(--ink-950); box-shadow:0 0 0 1px rgb(var(--cyan-500-rgb, 0 229 255) / .35); }
        .ln-vd-ve{ margin:10px 0 0; padding:8px 12px; font-family:var(--font-mono); font-size:12px; color:var(--cyan-300);
          background:var(--ink-950); border:var(--bw) dashed rgb(var(--cyan-500-rgb, 0 229 255) / .45); clip-path:var(--clip-tr); }
        .ln-vd-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-vd-msg.is-error{ color:var(--yellow-500); }
        .ln-vd-msg.is-ok{ color:var(--cyan-300); }
        .ln-vd-auto{ margin:10px 0 4px; padding:10px 12px; border-left:var(--bw-bold) solid rgb(var(--cyan-500-rgb, 0 229 255) / .5);
          background:rgb(var(--ink-950-rgb, 5 7 15) / .45); }
        .ln-vd-auto.is-off{ opacity:.7; }
        .ln-comida-web{ position:fixed; z-index:9000; pointer-events:none; will-change:left, top, transform;
          transition:transform .14s ease-out; filter:drop-shadow(3px 4px 0 rgb(var(--ink-950-rgb, 5 7 15) / .55));
          animation:ln-comida-in .25s var(--ease-snap, ease-out); }
        .ln-comida-web svg{ display:block; width:100%; height:100%; }
        .ln-comida-web.is-sale{ animation:ln-comida-out .2s ease-in forwards; }
        .ln-comida-web.is-bocado svg{ animation:ln-comida-bocado .3s ease-out; }
        @keyframes ln-comida-in{ from{ opacity:0; transform:scale(.2); } to{ opacity:1; } }
        @keyframes ln-comida-out{ to{ opacity:0; transform:scale(.2); } }
        @keyframes ln-comida-bocado{ 40%{ transform:scale(.86) rotate(-6deg); } }
        @media (prefers-reduced-motion: reduce){ .ln-comida-web, .ln-comida-web.is-sale, .ln-comida-web.is-bocado svg{ animation:none; transition:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // ── Piezas comunes ─────────────────────────────────────────────────────────
  function Deslizador({ id, label, min, max, step = 1, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-vd-range">
        <div className="ln-vd-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-vd-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }
  const Msg = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-vd-msg${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);
  /** Estado + señal del puente: pide `ranura` al conectar y escucha `senal`. → [valor, poner, vivo] */
  function useEstado(ranura, senal, normalizar, defecto, deps = []) {
    const vivo = useRef(true);
    const [v, setV] = useState(defecto);
    useEffect(() => {
      vivo.current = true;
      const quitar = [];
      const al = (j) => { if (vivo.current) setV(normalizar(leer(j, {}))); };
      const cablear = () => { quitar.push(conectar(senal, al)); pedir(ranura, [], al); };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { vivo.current = false; q(); quitar.splice(0).forEach((f) => f()); };
    }, deps);
    return [v, setV, vivo];
  }
  /** config_guardar de una tarjeta: guarda y pone el estado que devuelve Python (o el error). */
  function guardador(ranura, normalizar, setV, setMsg, vivo, textoOk = 'Guardado.') {
    return (parcial) => {
      const via = pedir(ranura, [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.estado) setV(normalizar(r.estado));
        setMsg(r && r.ok ? { texto: textoOk, ok: true } : { texto: (r && r.error) || 'No pude guardar.', error: true });
      });
      if (!via) setMsg({ texto: 'Esto no está disponible en esta versión de la app.', error: true });
    };
  }

  // ── SentarseCard ───────────────────────────────────────────────────────────
  function SentarseCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    useEffect(() => { inyectarEstilos(); }, []);
    const [e, setE, vivo] = useEstado('asiento_estado', 'asiento_cambio', normalizarAsiento, ASIENTO_DEFECTO);
    const [confirmar, setConfirmar] = useState(false);
    const [offset, setOffset] = useState(null);           // mientras se arrastra el deslizador
    const [msg, setMsg] = useState(null);
    const guardar = guardador('asiento_config_guardar', normalizarAsiento, setE, setMsg, vivo);
    const diferido = useMemo(() => crearRetardo((p) => { setOffset(null); guardar(p); }, 350), []);
    const alVentanas = (on) => {
      if (on) { setConfirmar(true); return; }           // encender pide leer el aviso antes
      setConfirmar(false);
      guardar({ ventanas: false });
    };
    const sentar = (sitio) => pedir('asiento_sentar', [sitio], (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      if (r && r.estado) setE(normalizarAsiento(r.estado));
      setMsg(r && r.texto ? { texto: txt(r.texto), ok: r.ok === true, error: r.ok !== true } : null);
    });
    const bajar = () => pedir('asiento_bajar', [], (ok) => {
      if (!vivo.current) return;
      setMsg(ok ? { texto: 'Se bajó.', ok: true } : { texto: 'No estaba sentada.', error: true });
      pedir('asiento_estado', [], (j) => { if (vivo.current) setE(normalizarAsiento(leer(j, {}))); });
    });
    const Icono = window.IconUser || (() => null);
    return (
      <Card id="aj-sentarse" eyebrow={<><Icono width={13} height={13}/> Asistente en escritorio · Sentarse</>} title="Sentarse en la barra y en ventanas"
        tone="cyan" tick={!!e.sentada}>
        <p className="ln-vd-nota">
          Arrastra a Lune hasta la barra de tareas y suéltala: se sienta con las piernas colgando. Con «ventanas», medio segundo
          sobre el borde de arriba de una ventana y se queda sentada en ella, siguiéndola. Tira hacia arriba para bajarla.
        </p>
        <div className={`ln-vd-estado${e.sentada ? ' is-on' : ''}`}>
          <Badge variant={e.sentada ? 'yellow' : 'ink'} outline={!e.sentada}>{e.sentada ? 'SENTADA' : 'de pie'}</Badge>
          <span className="ln-vd-estado-tx">{textoAsiento(e)}</span>
          {e.sentada
            ? <Button size="sm" variant="ghost" onClick={bajar}>Bajar</Button>
            : <>
                <Button size="sm" variant="secondary" onClick={() => sentar('barra')}>Sentarse en la barra</Button>
                <Button size="sm" variant="ghost" disabled={!e.ventanas} onClick={() => sentar('ventana')}>En una ventana</Button>
              </>}
        </div>
        <div className="ln-vd-sub">Dónde se sienta</div>
        <div className="ln-toggle-row">
          <Switch label="En la barra de tareas" checked={e.barra} onChange={(ev) => guardar({ barra: !!ev.target.checked })} />
          <Switch label="En ventanas" checked={e.ventanas || confirmar} accent="yellow"
            onChange={(ev) => alVentanas(!!ev.target.checked)} />
        </div>
        {confirmar && !e.ventanas && (
          <div className="ln-vd-aviso" role="alertdialog" aria-label="Aviso antes de activar sentarse en ventanas">
            <p>{AVISO_ANTICHEAT}</p>
            <div className="ln-vd-botones">
              <Button size="sm" variant="primary" onClick={() => { setConfirmar(false); guardar({ ventanas: true }); }}>Activar igualmente</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmar(false)}>Cancelar</Button>
            </div>
          </div>
        )}
        <div style={{ height: 12 }} />
        <Deslizador id="f-sentarse-offset" label="Altura del asiento" min={-OFFSET_MAX} max={OFFSET_MAX}
          value={offset === null ? e.offset : offset} fmt={(v) => `${v > 0 ? '+' : ''}${v} px`}
          hint="Si queda flotando o hundida: negativo la sube, positivo la baja."
          onChange={(v) => { setOffset(v); diferido({ offset: v }); }} />
        <Msg msg={msg} />
      </Card>
    );
  }

  // ── ComidaCard ─────────────────────────────────────────────────────────────
  function ComidaCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    useEffect(() => { inyectarEstilos(); }, []);
    const [catalogo, setCatalogo] = useState(CATALOGO_DEMO);
    const normalizar = (o) => { if (o && Array.isArray(o.catalogo)) setCatalogo(normalizarCatalogo(o.catalogo)); return normalizarComida(o); };
    const [e, setE, vivo] = useEstado('comida_estado', 'comida_cambio', normalizar, COMIDA_DEFECTO);
    const [msg, setMsg] = useState(null);
    const guardarCfg = guardador('comida_config_guardar', normalizarComida, setE, setMsg, vivo);
    const alternar = (id) => pedir('comida_alternar', [id], (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      if (r && r.estado) setE(normalizarComida(r.estado));
      setMsg(r && r.ok ? null : { texto: txt(r && r.texto) || 'Ahora no puedo comer.', error: true });
    });
    const guardarComida = () => pedir('comida_guardar', [], () => {
      if (vivo.current) pedir('comida_estado', [], (j) => { if (vivo.current) setE(normalizar(leer(j, {}))); });
    });
    const c = catalogo.find((x) => x.id === e.id);
    const v = c && c.variantes.find((x) => x.id === e.variante);
    return (
      <Card id="aj-comida" eyebrow={<>Lune · Comida</>} title="Batido y pastel" tone="yellow" tick={e.activa}>
        <p className="ln-vd-nota">
          Clic central sobre Lune → Batido o Pastel. La comida sigue al ratón: pásala rápido por su cabeza para dársela. Esc o
          dos minutos sin moverla la guardan.
        </p>
        <div className={`ln-vd-estado${e.activa ? ' is-on' : ''}`}>
          <Badge variant={e.activa ? 'yellow' : 'ink'} outline={!e.activa}>{e.activa ? 'EN LA MANO' : 'nada'}</Badge>
          <span className="ln-vd-estado-tx">
            {e.activa
              ? <span className="ln-vd-mano"><span className="ln-vd-muestra" style={{ background: (v && v.color) || e.color }} />{nombreEnMano(e, catalogo)}</span>
              : (e.disponible ? 'Nada en la mano.' : 'Desactivada.')}
          </span>
        </div>
        <div className="ln-toggle-row" style={{ marginTop: 12 }}>
          <Switch label="Comida con el clic central" checked={e.disponible} accent="yellow"
            onChange={(ev) => guardarCfg({ activa: !!ev.target.checked })} />
        </div>
        <div className="ln-vd-botones">
          {catalogo.map((x) => (
            <Button key={x.id} size="sm" variant={e.activa && e.id === x.id ? 'primary' : 'secondary'} disabled={!e.disponible}
              onClick={() => alternar(x.id)}>{x.nombre}</Button>
          ))}
          <Button size="sm" variant="ghost" disabled={!e.activa} onClick={guardarComida}>Guardar</Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  // ── DiscordCard ────────────────────────────────────────────────────────────
  function DiscordCard() {
    const { Card, Button, Switch, Badge, Input } = window.LUNE;
    useEffect(() => { inyectarEstilos(); }, []);
    const tocado = useRef({ id: false, url: false });
    const [id, setId] = useState('');
    const [url, setUrl] = useState('');
    const normalizar = (o) => {
      const d = normalizarDiscord(o);
      if (!tocado.current.id) setId(d.config.client_id);
      if (!tocado.current.url) setUrl(d.config.boton_url);
      return d;
    };
    const [e, setE, vivo] = useEstado('discord_estado', 'discord_cambio', normalizar, DISCORD_DEFECTO);
    const [msg, setMsg] = useState(null);
    const guardar = (parcial, textoOk = 'Guardado.') => {
      const via = pedir('discord_config_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.ok) { tocado.current = { id: false, url: false }; }
        if (r && r.estado) setE(normalizar(r.estado));
        setMsg(r && r.ok ? { texto: textoOk, ok: true } : { texto: txt(r && r.error) || 'No pude guardar.', error: true });
      });
      if (!via) setMsg({ texto: 'Esto no está disponible en esta versión de la app.', error: true });
    };
    // «Reconectar»: lo intenta ya; si ni se puede (apagada, sin ID…), el motivo. Lo que pase después
    // (conectada, o por qué no: Discord cerrado, otra Lune ya publica…) llega por discord_cambio.
    const reconectar = () => {
      const via = pedir('discord_reconectar', [], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.estado) setE(normalizar(r.estado));
        setMsg({ texto: txt(r && r.texto, 200) || (r && r.ok ? 'Lo intento ahora…' : 'No pude reconectar.'),
          ok: !!(r && r.ok), error: !(r && r.ok) });
      });
      if (!via) setMsg({ texto: 'Esto no está disponible en esta versión de la app.', error: true });
    };
    const idLimpio = id.trim();
    const idMal = !idDiscordValido(idLimpio);
    const urlLimpia = url.trim();
    const urlMal = !!urlLimpia && !urlBotonValida(urlLimpia);
    const Icono = window.IconMessage || window.IconChat || (() => null);
    return (
      <Card id="aj-discord" eyebrow={<><Icono width={13} height={13}/> Integraciones · Discord</>} title="Discord: lo que hace Lune"
        tone="blue" tick={e.conectado}>
        <p className="ln-vd-nota">
          Tu estado de Discord enseña lo que hace Lune (bailando, durmiendo, sentada en la barra…). Necesita el Application ID
          de una app de Discord: en discord.com/developers → New Application, sube en Rich Presence → Art Assets una imagen
          llamada «lune» y copia aquí su Application ID (no es un secreto).
        </p>
        <div className={`ln-vd-estado${e.conectado ? ' is-on' : ''}`}>
          <Badge variant={e.conectado ? 'yellow' : 'ink'} outline={!e.conectado}>{e.conectado ? 'CONECTADO' : (e.activo ? 'sin conectar' : 'apagado')}</Badge>
          <span className="ln-vd-estado-tx">{textoEstadoDiscord(e)}</span>
          {e.activo && !e.conectado && <Button size="sm" variant="secondary" onClick={reconectar}>Reconectar</Button>}
        </div>
        <div className="ln-toggle-row" style={{ marginTop: 12 }}>
          <Switch label="Enseñar en Discord lo que hace Lune" checked={e.activo} accent="blue"
            onChange={(ev) => guardar({ activo: !!ev.target.checked })} />
          <Switch label="Enseñar el nombre del modelo 3D" checked={e.config.mostrar_modelo}
            onChange={(ev) => guardar({ mostrar_modelo: !!ev.target.checked })} />
        </div>
        <div className="ln-vd-fila">
          <Input id="f-discord-id" label="Application ID" placeholder="123456789012345678" value={id} maxLength={20}
            error={idMal} hint={idMal ? 'Son de 17 a 20 cifras.' : 'discord.com/developers → tu app → Application ID.'}
            onChange={(ev) => { tocado.current.id = true; setId(String(ev.target.value || '')); }} />
          <Button size="sm" variant="secondary" disabled={idMal || idLimpio === e.config.client_id}
            onClick={() => guardar({ client_id: idLimpio }, idLimpio ? 'Application ID guardado.' : 'Application ID borrado.')}>
            {idLimpio || !e.config.client_id ? 'Guardar ID' : 'Borrar ID'}</Button>
        </div>
        <div className="ln-vd-fila">
          <Input id="f-discord-url" label="Enlace del botón «Conoce a Lune» (opcional)" placeholder="https://…" value={url} maxLength={512}
            error={urlMal} hint={urlMal ? 'Tiene que empezar por https:// (sin espacios).' : 'Solo lo ven los demás en tu perfil.'}
            onChange={(ev) => { tocado.current.url = true; setUrl(String(ev.target.value || '')); }} />
          <Button size="sm" variant="ghost" disabled={urlMal || urlLimpia === e.config.boton_url}
            onClick={() => guardar({ boton_url: urlLimpia })}>Guardar enlace</Button>
        </div>
        <p className="ln-vd-nota" style={{ marginTop: 12 }}>{PRIVACIDAD}</p>
        <p className="ln-vd-ve" aria-live="polite">{textoDiscordVe(e)}</p>
        <Msg msg={msg} />
      </Card>
    );
  }

  // ── AutoinicioOpciones (bajo el interruptor de settings.jsx) ───────────────
  function AutoinicioOpciones({ activo = false }) {
    const { Button } = window.LUNE;
    useEffect(() => { inyectarEstilos(); }, []);
    const [e, setE, vivo] = useEstado('autoinicio_estado', 'autoinicio_cambio', normalizarAutoinicio, AUTO_DEFECTO, [!!activo]);
    const [espera, setEspera] = useState(null);
    const [msg, setMsg] = useState(null);
    const guardar = guardador('autoinicio_opciones', normalizarAutoinicio, setE, setMsg, vivo);
    const diferido = useMemo(() => crearRetardo((p) => { setEspera(null); guardar(p); }, 350), []);
    const max = Math.max(RETRASO_MAX, e.retraso_s);
    return (
      <div className={`ln-vd-auto${activo ? '' : ' is-off'}`} id="aj-autoinicio-opciones">
        <div className="ln-vd-sub" style={{ marginTop: 0 }}>Al arrancar con Windows</div>
        <div className="ln-vd-botones" style={{ marginTop: 0 }}>
          {COMOS.map(([k, t]) => (
            <Button key={k} size="sm" variant={e.como === k ? 'primary' : 'ghost'} onClick={() => { if (e.como !== k) guardar({ como: k }); }}>{t}</Button>
          ))}
        </div>
        <div style={{ height: 10 }} />
        <Deslizador id="f-autoinicio-espera" label="Esperar antes de abrir" min={0} max={max} step={5}
          value={espera === null ? e.retraso_s : espera} fmt={(v) => `${v} s`}
          hint="El inicio de sesión va más ligero: la interfaz se carga después."
          onChange={(v) => { setEspera(v); diferido({ retraso_s: Math.min(RETRASO_MAX, v) }); }} />
        <p className="ln-vd-msg">{textoAutoinicio(e, activo)}</p>
        <Msg msg={msg} />
      </div>
    );
  }

  // ── ComidaWeb: la comida dentro de la ventana (sin la asistente flotante) ────
  function SvgComida({ tipo, color, variante }) {
    const tinta = 'var(--ink-950)';
    if (tipo === 'comer') {
      const bizcocho = variante === 'chocolate' ? '#3E2316' : '#F2CF96';
      return (
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <ellipse cx="50" cy="88" rx="40" ry="7" fill="rgb(255 255 255 / .85)" stroke={tinta} strokeWidth="3" />
          <rect x="18" y="50" width="64" height="34" rx="4" fill={bizcocho} stroke={tinta} strokeWidth="3.5" />
          <path d="M18 62 H82" stroke="rgb(255 255 255 / .55)" strokeWidth="4" />
          <path d="M16 52 Q16 40 30 40 H70 Q84 40 84 52 V58 Q78 64 74 58 Q70 68 64 58 Q58 64 52 58 Q46 70 40 58 Q34 64 28 58 Q22 66 16 58 Z"
            fill={color} stroke={tinta} strokeWidth="3.5" strokeLinejoin="round" />
          <path d="M50 30 Q54 20 62 16" fill="none" stroke={tinta} strokeWidth="3" strokeLinecap="round" />
          <circle cx="50" cy="33" r="7.5" fill="#E23B5A" stroke={tinta} strokeWidth="3" />
          <circle cx="47.5" cy="30.5" r="2" fill="rgb(255 255 255 / .8)" />
        </svg>
      );
    }
    return (
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <path d="M60 4 L52 36" stroke={tinta} strokeWidth="8" strokeLinecap="round" />
        <path d="M60 4 L52 36" stroke="var(--cyan-400)" strokeWidth="4" strokeLinecap="round" />
        <path d="M26 40 Q24 28 36 28 Q40 18 52 22 Q62 16 68 26 Q78 28 74 40 Z" fill="#FFF7EE" stroke={tinta} strokeWidth="3.5" strokeLinejoin="round" />
        <path d="M26 40 H74 L65 92 H35 Z" fill={color} stroke={tinta} strokeWidth="3.5" strokeLinejoin="round" />
        <path d="M33 48 L38 84" stroke="rgb(255 255 255 / .45)" strokeWidth="5" strokeLinecap="round" />
        <path d="M27 40 H73" stroke={tinta} strokeWidth="3.5" />
      </svg>
    );
  }

  let ultimoPuntero = null;                             // {x, y} en px de la ventana: dónde aparece la comida
  function ComidaWeb() {
    const [comida, setComida] = useState(null);         // {id, variante, color, tipo, nombre}
    const [pos, setPos] = useState(null);
    const [ladeo, setLadeo] = useState(0);
    const [sale, setSale] = useState(false);
    const [bocado, setBocado] = useState(false);
    const vivo = useRef(true);
    const actual = useRef(null);
    const detector = useRef(null);
    if (!detector.current) detector.current = crearDetector();
    const cabeza = useRef({ t: -Infinity, c: null });
    const timers = useRef({});
    const limpiarTimer = (k) => { if (timers.current[k]) { clearTimeout(timers.current[k]); timers.current[k] = null; } };
    const guardar = () => pedir('comida_guardar', [], () => {});

    // Señales del puente (y el estado al recargar la página a media comida).
    useEffect(() => {
      vivo.current = true;
      inyectarEstilos();
      const quitar = [];
      const mostrar = (o) => {
        limpiarTimer('sale');
        setSale(false);
        actual.current = o;
        detector.current.reiniciar();
        setComida(o);
        if (ultimoPuntero) setPos({ ...ultimoPuntero });
      };
      const ocultar = () => {
        if (!actual.current) return;
        actual.current = null;
        setSale(true);
        limpiarTimer('sale');
        timers.current.sale = setTimeout(() => { if (vivo.current) { setComida(null); setSale(false); } }, 200);
      };
      const alWeb = (j) => {
        const o = normalizarComidaWeb(leer(j, null));
        if (!o || !vivo.current) return;
        if (o.accion === 'guarda') ocultar(); else mostrar(o);
      };
      const cablear = () => {
        quitar.push(conectar('comida_web', alWeb));
        pedir('comida_estado', [], (j) => {
          const e = normalizarComida(leer(j, {}));
          if (vivo.current && e.activa && e.vista === 'web') {
            mostrar({ accion: 'aparece', id: e.id, variante: e.variante, color: e.color || '#FFFFFF', tipo: e.tipo || 'beber', nombre: e.nombre });
          }
        });
      };
      const alPunteroSiempre = (ev) => {
        const x = Number(ev && ev.clientX), y = Number(ev && ev.clientY);
        if (fin(x) && fin(y)) ultimoPuntero = { x, y };
      };
      window.addEventListener('pointermove', alPunteroSiempre);
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => {
        vivo.current = false;
        q();
        quitar.splice(0).forEach((f) => f());
        window.removeEventListener('pointermove', alPunteroSiempre);
        Object.keys(timers.current).forEach(limpiarTimer);
      };
    }, []);

    // Con comida en la mano: seguir al ratón, acertar en la cabeza de la barra, Esc y D4.
    const hay = !!comida && !sale;
    useEffect(() => {
      if (!hay) return undefined;
      let previo = ultimoPuntero ? { ...ultimoPuntero } : null;
      const d4 = () => { limpiarTimer('d4'); timers.current.d4 = setTimeout(() => { if (actual.current) guardar(); }, GUARDAR_SOLA_MS); };
      const alMover = (ev) => {
        const x = Number(ev && ev.clientX), y = Number(ev && ev.clientY);
        const o = actual.current;
        if (!fin(x) || !fin(y) || !o) return;
        const p1 = { x, y };
        const p0 = previo || p1;
        previo = p1;
        const t = Date.now();
        if (t - cabeza.current.t >= CABEZA_MS) cabeza.current = { t, c: leerCabeza() };
        setPos(p1);
        setLadeo(acotar((p1.x - p0.x) * 1.2, -25, 25));
        limpiarTimer('ladeo');
        timers.current.ladeo = setTimeout(() => { if (vivo.current) setLadeo(0); }, 140);
        d4();
        if (detector.current.mover(t, p0, p1, cabeza.current.c)) {
          pedir('comida_evento', [o.id], () => {});
          try { window.dispatchEvent(new window.CustomEvent('lune-asistente-cara', { detail: { estado: 'happy', ms: MS_CARA } })); } catch (e) { /* sin eventos */ }
          setBocado(true);
          limpiarTimer('bocado');
          timers.current.bocado = setTimeout(() => { if (vivo.current) setBocado(false); }, 300);
        }
      };
      const alTecla = (ev) => {
        if (!ev || (ev.key !== 'Escape' && ev.code !== 'Escape') || !actual.current) return;
        guardar();
      };
      window.addEventListener('pointermove', alMover);
      window.addEventListener('keydown', alTecla);
      d4();
      return () => {
        window.removeEventListener('pointermove', alMover);
        window.removeEventListener('keydown', alTecla);
        ['d4', 'ladeo', 'bocado'].forEach(limpiarTimer);
      };
    }, [hay, comida && comida.id]);

    if (!comida) return null;
    const p = pos || { x: (Number(window.innerWidth) || 1280) / 2, y: (Number(window.innerHeight) || 820) / 2 };
    const t = TAM_COMIDA;
    return (
      <div className={`ln-comida-web${sale ? ' is-sale' : ''}${bocado ? ' is-bocado' : ''}`} aria-hidden="true"
        data-comida={comida.id} data-variante={comida.variante}
        style={{ left: Math.round(p.x - t / 2), top: Math.round(p.y - t / 2), width: t, height: t,
          transform: ladeo ? `rotate(${Math.round(ladeo * 10) / 10}deg)` : undefined }}>
        <SvgComida tipo={comida.tipo} color={comida.color} variante={comida.variante} />
      </div>
    );
  }

  Object.assign(window, {
    SentarseCard, ComidaCard, DiscordCard, AutoinicioOpciones, ComidaWeb,
    LuneVida: {
      normalizarAsiento, normalizarCatalogo, normalizarComida, normalizarComidaWeb, normalizarDiscord, normalizarAutoinicio,
      segmentoTocaCirculo, crearDetector, idDiscordValido, urlBotonValida, publicacionSegura, textoDiscordVe,
      textoEstadoDiscord, textoAutoinicio, textoAsiento, nombreEnMano, CATALOGO_DEMO, ENFRIAMIENTO_MS, GUARDAR_SOLA_MS,
      AVISO_ANTICHEAT, PRIVACIDAD,
    },
  });
})();
