/* Lune CD desktop — Alarmas, temporizadores, pantalla grande y salvapantallas (cortes 5 y 6).
 *
 * AlarmasPanel        vista «alarmas» (app.jsx): alarmas con <input type=time>, días L M X J V S D, «Solo una
 *                     vez», texto, interruptor, «Editar» y papelera; temporizadores h/m/s (y rápidos de 1, 5, 10
 *                     y 25 min) con la cuenta atrás en la página cada 250 ms desde `objetivo` (epoch del backend,
 *                     corregido con su `ahora`), Iniciar/Parar/Reiniciar/Borrar; «Probar».
 * AlarmaBanner        global (app.jsx): lo que está sonando, con «Apagar» bloqueado los primeros segundos (cuenta
 *                     atrás de apagar_en_ms, como el bloqueo de ControlAviso) y «Posponer».
 * AlarmasCard         Ajustes: alarmas activas, pantalla grande al sonar, decir el texto, sonido y volumen,
 *                     bloqueo, posponer, recuperar las perdidas, «Probar» y «Abrir alarmas».
 * PantallaGrandeCard  Ajustes: salvapantallas (interruptor, espera en 11 pasos, un clic sale también de la
 *                     pantalla grande, fondo oscuro, reloj), el atajo de la pantalla grande (lo lee de
 *                     luneEscritorio.atajos_estado), «Probar salvapantallas» y «Pantalla grande ahora».
 * Puente: window.luneAlarmas (ui/puente_alarmas.py). Guardan al momento (config.set en Python), sin pasar por
 * get_config/guardar_config. Sin puente (navegador), una demo local que no suena.
 * «Abrir alarmas» navega con el evento de window 'lune-vista' ({detail: 'alarmas'}), que escucha app.jsx.
 * Se registra solo: Object.assign(window, {AlarmasPanel, AlarmaBanner, AlarmasCard, PantallaGrandeCard, LuneAlarmas}).
 */
(function () {
  const { useState, useEffect, useRef, useMemo } = React;

  // ── Puente: window.luneAlarmas (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneAlarmas || null;
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
  /** Guarda `ms` después del último cambio, con todos los cambios juntos ({a} + {b} = {a, b}). */
  function crearRetardo(fn, ms) {
    let timer = null, pendiente = {};
    return (parcial) => {
      pendiente = { ...pendiente, ...(parcial || {}) };
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = null; const p = pendiente; pendiente = {}; fn(p); }, ms);
    };
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const DIAS = 'lmxjvsd';                               // bit0 = lunes … bit6 = domingo (como Python)
  const LETRAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  const NOMBRES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const PLURALES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábados', 'domingos'];
  const ID_OK = /^[A-Za-z0-9_-]{1,40}$/;
  const TIPOS = { alarma: 'Alarma', temporizador: 'Temporizador', pospuesta: 'Pospuesta', prueba: 'Prueba' };
  const SONIDOS = [['azar', 'Al azar'], ['alarma_1', 'Alarma 1'], ['alarma_2', 'Alarma 2'], ['alarma_3', 'Alarma 3']];
  const MOTIVOS = { manual: 'pedida a mano', herramienta: 'la pidió Lune', alarma: 'por una alarma', salvapantallas: 'salvapantallas' };
  const TIEMPOS = [30, 60, 300, 900, 1800, 2700, 3600, 5400, 7200, 9000, 10800];
  const RAPIDOS = [1, 5, 10, 25];
  const MAX_S = 24 * 3600;
  const TEXTO_MAX = 160;
  const fin = Number.isFinite;
  const pad2 = (n) => String(n).padStart(2, '0');
  const hhmm = (h, m) => `${pad2(h)}:${pad2(m)}`;
  const acotar = (v, a, b) => Math.min(b, Math.max(a, v));
  const txt = (v, n = TEXTO_MAX) => (typeof v === 'string' ? v.slice(0, n) : '');

  function parsearHora(v) {
    const m = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(String(v == null ? '' : v).trim());
    return m ? { hora: Number(m[1]), minuto: Number(m[2]) } : null;
  }
  /** «lmx» → máscara (bit0 = lunes). Lo que no es un día se ignora. */
  function mascara(letras) {
    let m = 0;
    for (const ch of String(letras || '').toLowerCase()) { const i = DIAS.indexOf(ch); if (i >= 0) m |= 1 << i; }
    return m;
  }
  const letrasDe = (mask) => DIAS.split('').filter((_, i) => mask & (1 << i)).join('');
  /** Días de una alarma en palabras: «Todos los días», «De lunes a viernes», «L X V», «Una vez». */
  function textoDias(mask, unaVez) {
    const m = (Number(mask) || 0) & 127;
    if (unaVez && !m) return 'Una vez';
    let t;
    if (!m || m === 127) t = 'Todos los días';
    else if (m === 31) t = 'De lunes a viernes';
    else if (m === 96) t = 'Fines de semana';
    else if ((m & (m - 1)) === 0) t = `Los ${PLURALES[Math.log2(m)]}`;
    else t = LETRAS.filter((_, i) => m & (1 << i)).join(' ');
    return unaVez ? `Una vez · ${t}` : t;
  }
  function normalizarAlarma(a) {
    if (!a || typeof a !== 'object' || !ID_OK.test(String(a.id == null ? '' : a.id))) return null;
    const h = Number(a.hora), mi = Number(a.minuto), d = Number(a.dias), px = Number(a.proxima);
    if (!Number.isInteger(h) || !Number.isInteger(mi) || h < 0 || h > 23 || mi < 0 || mi > 59) return null;
    return {
      id: String(a.id), activa: a.activa !== false, hora: h, minuto: mi,
      dias: Number.isInteger(d) && d >= 0 && d <= 127 ? d : 0, una_vez: a.una_vez === true, texto: txt(a.texto),
      proxima: fin(px) && px > 0 ? px : 0,                // epoch del backend (0 = que lo calcule la página)
    };
  }
  function normalizarTemporizador(t) {
    if (!t || typeof t !== 'object' || !ID_OK.test(String(t.id == null ? '' : t.id))) return null;
    const dur = Number(t.duracion_s), obj = Number(t.objetivo), rest = Number(t.restante_s);
    if (!fin(dur) || dur <= 0) return null;
    const activo = t.activo !== false;
    return {
      id: String(t.id), activo, duracion_s: Math.round(dur),
      objetivo: activo && fin(obj) && obj > 0 ? obj : 0,
      restante_s: fin(rest) && rest >= 0 ? rest : dur, texto: txt(t.texto),
    };
  }
  function normalizarSonando(s) {
    if (!s || typeof s !== 'object') return null;
    const n = (v) => (fin(Number(v)) ? Number(v) : 0);
    const pos = Number(s.posponer_min);
    return {
      texto: txt(s.texto), tipo: TIPOS[s.tipo] ? s.tipo : 'alarma', atraso_s: Math.max(0, n(s.atraso_s)),
      programado: txt(s.programado, 25), apagar_en_ms: acotar(n(s.apagar_en_ms), 0, 60000),
      cola: Math.round(acotar(n(s.cola), 0, 99)), posponer_min: Number.isInteger(pos) && pos >= 1 && pos <= 60 ? pos : 0,
    };
  }
  function normalizarProxima(p) {
    if (!p || typeof p !== 'object' || !ID_OK.test(String(p.id == null ? '' : p.id))) return null;
    const c = Number(p.cuando);
    return fin(c) && c > 0 ? { id: String(p.id), tipo: p.tipo === 'temporizador' ? 'temporizador' : 'alarma', texto: txt(p.texto), cuando: c } : null;
  }
  function normalizarEstado(o) {
    const r = o && typeof o === 'object' ? o : {};
    const lista = (v, f) => (Array.isArray(v) ? v.map(f).filter(Boolean) : []);
    return {
      disponible: r.disponible === true,
      activo: r.activo !== false,
      ahora: fin(Number(r.ahora)) ? Number(r.ahora) : 0,
      alarmas: lista(r.alarmas, normalizarAlarma),
      temporizadores: lista(r.temporizadores, normalizarTemporizador),
      sonando: normalizarSonando(r.sonando),
      proxima: normalizarProxima(r.proxima),
    };
  }
  /** Segundos que le quedan a un temporizador (en marcha: desde `objetivo`; parado: restante_s). */
  function restante(t, ahoraS) {
    if (t.activo && t.objetivo > 0) return Math.max(0, t.objetivo - ahoraS);
    return Math.max(0, t.restante_s);
  }
  /** 65 → «01:05»; 3725 → «1:02:05» (redondea hacia arriba: 0.2 s son «00:01»). */
  function formatoDuracion(s) {
    const x = Math.max(0, Math.ceil(Number(s) || 0));
    const h = Math.floor(x / 3600), m = Math.floor((x % 3600) / 60), sg = x % 60;
    return h ? `${h}:${pad2(m)}:${pad2(sg)}` : `${pad2(m)}:${pad2(sg)}`;
  }
  /** Próxima vez que sonará `a` después de `desde` (Date local), o null (apagada). */
  function proximaVez(a, desde) {
    if (!a || !a.activa) return null;
    for (let d = 0; d <= 7; d++) {
      const f = new Date(desde.getFullYear(), desde.getMonth(), desde.getDate() + d, a.hora, a.minuto, 0, 0);
      if (f.getTime() <= desde.getTime()) continue;
      const dia = (f.getDay() + 6) % 7;                  // lunes = 0
      if (!a.dias || (a.dias & (1 << dia))) return f;
    }
    return null;
  }
  /** La alarma que antes suena después de `desde`. Si el backend dio `proxima` (epoch) se usa esa,
   *  pasada al reloj de la página con `desfaseS` (ahora del backend − reloj de la página). */
  function proxima(alarmas, desde, desfaseS = 0) {
    let mejor = null;
    for (const a of alarmas || []) {
      const f = !a || !a.activa ? null : a.proxima > 0 ? new Date((a.proxima - desfaseS) * 1000) : proximaVez(a, desde);
      if (f && (!mejor || f.getTime() < mejor.cuando.getTime())) mejor = { alarma: a, cuando: f };
    }
    return mejor;
  }
  /** ms → «en 5 h 20 min», «en 3 min», «en menos de 1 min». */
  function textoFalta(ms) {
    const min = Math.floor(Math.max(0, ms) / 60000);
    if (min < 1) return 'en menos de 1 min';
    const h = Math.floor(min / 60), m = min % 60;
    if (h >= 24) { const d = Math.floor(h / 24); return `en ${d} d${h % 24 ? ` ${h % 24} h` : ''}`; }
    return h ? `en ${h} h${m ? ` ${m} min` : ''}` : `en ${m} min`;
  }
  function etiquetaTiempo(seg) {
    const s = Math.round(Number(seg) || 0);
    if (s < 60) return `${s} s`;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`;
  }
  function tituloSonando(s) {
    const base = TIPOS[s && s.tipo] || 'Alarma';
    const min = Math.round(((s && s.atraso_s) || 0) / 60);
    return min >= 1 ? `${base} · hace ${min} min` : base;
  }
  const segundosDe = (h, m, s) => (Number(h) || 0) * 3600 + (Number(m) || 0) * 60 + (Number(s) || 0);

  const ALARMAS_DEFECTO = { activo: true, pantalla_grande: true, decir_texto: true, bloqueo_s: 5, recuperar_min: 10,
    posponer_min: 5, volumen: 0.8, sonido: 'azar' };
  function normalizarConfigAlarmas(o) {
    const r = o && typeof o === 'object' ? o : {};
    const out = { ...ALARMAS_DEFECTO };
    ['activo', 'pantalla_grande', 'decir_texto'].forEach((k) => { if (typeof r[k] === 'boolean') out[k] = r[k]; });
    const rango = (k, a, b, ent) => { const v = Number(r[k]); if (fin(v)) out[k] = ent ? Math.round(acotar(v, a, b)) : acotar(v, a, b); };
    rango('bloqueo_s', 0, 30, true); rango('recuperar_min', 0, 120, true); rango('posponer_min', 1, 60, true);
    rango('volumen', 0, 1, false);
    if (SONIDOS.some(([k]) => k === r.sonido)) out.sonido = r.sonido;
    return out;
  }
  const PASOS_DEFECTO = TIEMPOS.map((s, i) => ({ paso: i, segundos: s, etiqueta: etiquetaTiempo(s) }));
  const GRANDE_DEFECTO = { activo: false, paso: 0, clic_sale_de_todo: true, fondo_oscuro: true, reloj: true };
  function normalizarConfigGrande(o) {
    const r = o && typeof o === 'object' ? o : {};
    const out = { ...GRANDE_DEFECTO };
    ['activo', 'clic_sale_de_todo', 'fondo_oscuro', 'reloj'].forEach((k) => { if (typeof r[k] === 'boolean') out[k] = r[k]; });
    const pasos = Array.isArray(r.pasos) && r.pasos.length
      ? r.pasos.map((p, i) => ({ paso: i, segundos: Number(p && p.segundos) || 0, etiqueta: txt(p && p.etiqueta, 24) || etiquetaTiempo(p && p.segundos) }))
      : PASOS_DEFECTO;
    const p = Number(r.paso);
    out.paso = Number.isInteger(p) ? acotar(p, 0, pasos.length - 1) : 0;
    out.pasos = pasos;
    return out;
  }
  function normalizarGrande(o) {
    const r = o && typeof o === 'object' ? o : {};
    const activa = r.activa === true;
    return { activa, motivo: activa && MOTIVOS[r.motivo] ? r.motivo : '', disponible: r.disponible === true };
  }
  /** Navega a la vista de alarmas (app.jsx escucha 'lune-vista'). */
  function abrirVista(vista = 'alarmas') {
    try { window.dispatchEvent(new window.CustomEvent('lune-vista', { detail: vista })); return true; } catch (e) { return false; }
  }

  // ── Demo sin backend (navegador): mismas respuestas que el puente, nada suena ──
  const DEMO = (function crearDemo() {
    let n = 0;
    const est = { alarmas: [], temporizadores: [] };
    let cfgA = { ...ALARMAS_DEFECTO };
    let cfgG = { ...GRANDE_DEFECTO };
    let grande = { activa: false, motivo: '' };
    const ahora = () => Date.now() / 1000;
    const estado = () => ({ disponible: false, activo: cfgA.activo, ahora: ahora(), alarmas: est.alarmas.slice(),
      temporizadores: est.temporizadores.slice(), sonando: null });
    const resp = (ok, error, extra) => JSON.stringify({ ok, error: ok ? '' : error, ...(extra || {}), estado: estado() });
    return {
      alarmas_json: () => JSON.stringify(estado()),
      alarma_guardar(j) {
        const o = leer(j, {});
        if (o.id) {
          const a = est.alarmas.find((x) => x.id === o.id);
          if (!a) return resp(false, 'Esa alarma no existe.');
          const hm = o.hora !== undefined ? parsearHora(o.hora) : { hora: a.hora, minuto: a.minuto };
          if (!hm) return resp(false, 'Hora no válida (HH:MM).');
          Object.assign(a, hm, o.dias !== undefined ? { dias: mascara(o.dias) } : {},
            typeof o.una_vez === 'boolean' ? { una_vez: o.una_vez } : {}, typeof o.activa === 'boolean' ? { activa: o.activa } : {},
            typeof o.texto === 'string' ? { texto: o.texto.trim().slice(0, TEXTO_MAX) } : {});
          return resp(true, '', { id: a.id });
        }
        const hm = parsearHora(o.hora);
        if (!hm) return resp(false, 'Hora no válida (HH:MM).');
        const a = { id: `a${++n}`, activa: true, ...hm, dias: mascara(o.dias), una_vez: o.una_vez === true,
          texto: String(o.texto || '').trim().slice(0, TEXTO_MAX) };
        est.alarmas.push(a);
        est.alarmas.sort((x, y) => (x.hora - y.hora) || (x.minuto - y.minuto));
        return resp(true, '', { id: a.id });
      },
      alarma_borrar(id) {
        const antes = est.alarmas.length + est.temporizadores.length;
        est.alarmas = est.alarmas.filter((a) => a.id !== id);
        est.temporizadores = est.temporizadores.filter((t) => t.id !== id);
        return resp(est.alarmas.length + est.temporizadores.length < antes, 'No encontré esa alarma.');
      },
      temporizador_crear(j) {
        const o = leer(j, {});
        const s = o.segundos !== undefined ? Number(o.segundos) : segundosDe(o.h, o.m, o.s);
        if (!Number.isInteger(s) || s < 1 || s > MAX_S) return resp(false, 'Entre 1 segundo y 24 horas.');
        const t = { id: `t${++n}`, activo: o.iniciar !== false, duracion_s: s, restante_s: s, texto: String(o.texto || '').trim().slice(0, TEXTO_MAX),
          objetivo: o.iniciar !== false ? ahora() + s : 0 };
        est.temporizadores.push(t);
        return resp(true, '', { id: t.id });
      },
      temporizador_accion(id, accion) {
        if (accion === 'borrar') return DEMO.alarma_borrar(id);
        const t = est.temporizadores.find((x) => x.id === id);
        if (!t) return resp(false, 'No encontré ese temporizador.');
        if (accion === 'parar' && t.activo) { t.restante_s = restante(t, ahora()); t.activo = false; t.objetivo = 0; }
        else if (accion === 'iniciar' && !t.activo) { t.activo = true; t.objetivo = ahora() + t.restante_s; }
        else if (accion === 'reiniciar') { t.restante_s = t.duracion_s; t.objetivo = t.activo ? ahora() + t.duracion_s : 0; }
        return resp(true, '');
      },
      alarma_apagar: () => false, alarma_posponer: () => false, alarma_probar: () => false, salvapantallas_probar: () => false,
      config_alarmas: () => JSON.stringify({ ...cfgA, sonidos: SONIDOS.map(([k]) => k) }),
      config_alarmas_guardar(j) { cfgA = normalizarConfigAlarmas({ ...cfgA, ...leer(j, {}) }); return JSON.stringify({ ok: true, error: '', estado: cfgA }); },
      config_grande: () => JSON.stringify({ ...cfgG, pasos: PASOS_DEFECTO }),
      config_grande_guardar(j) {
        cfgG = normalizarConfigGrande({ ...cfgG, ...leer(j, {}) });
        return JSON.stringify({ ok: true, error: '', estado: { ...cfgG, pasos: PASOS_DEFECTO } });
      },
      grande_estado_json: () => JSON.stringify({ ...grande, disponible: false }),
      grande_alternar() { grande = grande.activa ? { activa: false, motivo: '' } : { activa: true, motivo: 'manual' }; return true; },
    };
  })();

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  // Colores del tema por tokens (var(--x) y rgb(var(--x-rgb, R G B) / a)): el tema del corte 4 los tiñe.
  // El rojo de la alarma (#FF4826, el de Mate-Engine) es fijo: --lune-alarma.
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-ocio-alarmas-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-ocio-alarmas-css';
      st.textContent = `
        .ln-al-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-al-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-al-form{ display:flex; flex-wrap:wrap; gap:12px 16px; align-items:flex-end; }
        .ln-al-form .lune-field{ min-width:0; }
        .ln-al-hora-in{ font-family:var(--font-mono); font-size:20px; width:8.5ch; color-scheme:dark; }
        .ln-al-texto-in{ flex:1; min-width:200px; }
        .ln-al-dias{ display:flex; gap:6px; flex-wrap:wrap; }
        .ln-al-dia{ appearance:none; -webkit-appearance:none; width:34px; height:34px; cursor:pointer; border:var(--bw) solid var(--ink-500);
          background:var(--ink-900); color:var(--text-muted); font-family:var(--font-display); font-weight:700; font-size:13px; clip-path:var(--clip-tr);
          transition:background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast), transform var(--dur-fast) var(--ease-snap); }
        .ln-al-dia:hover{ border-color:var(--cyan-500); transform:skewX(-6deg); }
        .ln-al-dia.is-on{ background:var(--cyan-500); color:var(--ink-950); border-color:var(--cyan-300); box-shadow:0 0 10px rgb(var(--cyan-500-rgb, 0 229 255) / .35); }
        .ln-al-acciones{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
        .ln-al-lista{ margin-top:14px; display:flex; flex-direction:column; }
        .ln-al-fila{ display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:var(--bw) solid var(--border); flex-wrap:wrap; }
        .ln-al-fila:last-child{ border-bottom:none; }
        .ln-al-fila.is-off .ln-al-hora, .ln-al-fila.is-off .ln-al-meta{ opacity:.5; }
        .ln-al-fila.is-editando{ background:rgb(var(--cyan-500-rgb, 0 229 255) / .06); }
        .ln-al-hora{ font-family:var(--font-mono); font-weight:700; font-size:22px; color:var(--text-strong); min-width:5.2ch; }
        .ln-al-cuenta{ font-family:var(--font-mono); font-weight:700; font-size:22px; color:var(--cyan-300); min-width:7ch; font-variant-numeric:tabular-nums; }
        .ln-al-cuenta.is-parado{ color:var(--text-muted); }
        .ln-al-cuenta.is-cero{ color:var(--lune-alarma, #FF4826); }
        .ln-al-meta{ flex:1; min-width:140px; display:flex; flex-direction:column; gap:2px; }
        .ln-al-dias-tx{ font-family:var(--font-mono); font-size:11px; letter-spacing:.06em; color:var(--cyan-400); text-transform:uppercase; }
        .ln-al-texto{ font-family:var(--font-sans); font-size:13px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .ln-al-texto.is-vacio{ color:var(--text-faint); font-style:italic; }
        .ln-al-icono{ appearance:none; -webkit-appearance:none; border:none; background:none; color:var(--text-dim); cursor:pointer; padding:6px; line-height:0; }
        .ln-al-icono:hover{ color:var(--lune-alarma, #FF4826); }
        .ln-al-dur{ display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap; }
        .ln-al-dur .ln-al-num{ width:72px; }
        .ln-al-rapidos{ display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }
        .ln-al-prox{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; margin-bottom:14px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--yellow-500); clip-path:var(--clip-tr); }
        .ln-al-prox-tx{ flex:1; min-width:180px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-al-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-al-msg.is-error{ color:var(--yellow-500); }
        .ln-al-msg.is-ok{ color:var(--cyan-300); }
        .ln-al-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-al-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-al-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-al-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-al-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-al-kbd{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); background:var(--ink-950); border:var(--bw) solid var(--cyan-700);
          padding:3px 9px; clip-path:var(--clip-tr); white-space:nowrap; }
        .ln-al-kbd.is-vacio{ color:var(--text-faint); border-color:var(--ink-500); }
        .ln-al-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
        .ln-alarma-banner{ position:fixed; top:calc(var(--app-topbar, 56px) + 12px); left:50%; transform:translateX(-50%); z-index:1150;
          width:min(640px, calc(100vw - 32px)); display:flex; align-items:center; gap:14px; flex-wrap:wrap; padding:14px 16px;
          background:var(--ink-950); color:var(--paper); border:var(--bw-bold) solid var(--lune-alarma, #FF4826); clip-path:var(--clip-notch);
          box-shadow:6px 6px 0 rgb(var(--lune-alarma-rgb, 255 72 38) / .45), 0 0 26px rgb(var(--lune-alarma-rgb, 255 72 38) / .35);
          animation:ln-alarma-in .28s var(--ease-snap); }
        @keyframes ln-alarma-in{ from{ opacity:0; transform:translate(-50%, -16px) skewX(-6deg); } to{ opacity:1; transform:translate(-50%, 0); } }
        .ln-alarma-ic{ flex:none; width:42px; height:42px; display:flex; align-items:center; justify-content:center;
          background:var(--lune-alarma, #FF4826); color:var(--ink-950); clip-path:var(--clip-tr); animation:ln-alarma-pulso 1s ease-in-out infinite; }
        @keyframes ln-alarma-pulso{ 50%{ transform:scale(1.1) rotate(-8deg); } }
        .ln-alarma-tx{ flex:1; min-width:180px; }
        .ln-alarma-tit{ font-family:var(--font-display); font-weight:700; font-style:italic; font-size:12px; letter-spacing:.08em;
          text-transform:uppercase; color:var(--lune-alarma, #FF4826); }
        .ln-alarma-texto{ font-family:var(--font-sans); font-size:16px; font-weight:600; color:var(--text-strong); overflow-wrap:anywhere; }
        .ln-alarma-cola{ font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-top:2px; }
        .ln-alarma-acc{ display:flex; gap:8px; flex-wrap:wrap; }
        @media (prefers-reduced-motion: reduce){ .ln-alarma-banner, .ln-alarma-ic{ animation:none; } .ln-al-dia:hover{ transform:none; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }
  function useVivo() {
    const vivo = useRef(true);
    useEffect(() => { vivo.current = true; inyectarEstilos(); return () => { vivo.current = false; }; }, []);
    return vivo;
  }

  // ── Piezas ─────────────────────────────────────────────────────────────────
  const IconoAlarma = (p) => React.createElement('svg', { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round', ...p },
    React.createElement('circle', { cx: 12, cy: 13, r: 8 }), React.createElement('path', { d: 'M12 9v4l2 2M5 3 2 6M22 6l-3-3' }));
  function Deslizador({ id, label, min, max, step = 1, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-al-range">
        <div className="ln-al-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-al-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }
  const Msg = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-al-msg${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);
  /** Respuesta {ok, error, estado} de una ranura → mensaje para la tarjeta. */
  const msgDe = (r, okTexto) => (r && r.ok ? { texto: okTexto, ok: true } : { texto: (r && r.error) || 'No pude hacerlo.', error: true });

  /** Estado de alarmas y temporizadores (alarmas_json + señal alarmas_cambio) y el reloj del backend. */
  function useEstadoAlarmas(vivo) {
    const [estado, setEstado] = useState(() => normalizarEstado(null));
    const [modo, setModo] = useState(() => (puente() ? 'puente' : 'demo'));
    const desfase = useRef(0);                         // ahora del backend − reloj de la página (s)
    const poner = (o) => {
      if (!vivo.current || !o) return;
      const e = normalizarEstado(o);
      if (e.ahora) desfase.current = e.ahora - Date.now() / 1000;
      setEstado(e);
    };
    const cargar = () => pedir('alarmas_json', [], (j) => poner(leer(j, null)));
    useEffect(() => {
      const quitar = [];
      const cablear = () => { setModo('puente'); quitar.push(conectar('alarmas_cambio', (j) => poner(leer(j, null)))); cargar(); };
      const q = alListo(cablear);
      if (!puente()) cargar();                           // demo hasta que (si acaso) llegue el puente
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    const ahoraS = () => Date.now() / 1000 + desfase.current;
    return { estado, poner, cargar, ahoraS, modo };
  }

  // ── Vista «alarmas» ────────────────────────────────────────────────────────
  const FORM_VACIO = { id: '', hora: '07:30', dias: '', una_vez: false, texto: '' };

  function AlarmasPanel() {
    const { Card, Button, Switch, Input, Badge } = window.LUNE;
    const vivo = useVivo();
    const { estado, poner, cargar, ahoraS, modo } = useEstadoAlarmas(vivo);
    const [form, setForm] = useState(FORM_VACIO);
    const [dur, setDur] = useState({ h: 0, m: 5, s: 0, texto: '' });
    const [msgA, setMsgA] = useState(null);
    const [msgT, setMsgT] = useState(null);
    const [, setTic] = useState(0);
    const hayCuenta = estado.temporizadores.some((t) => t.activo && t.objetivo > 0);
    useEffect(() => {
      if (!hayCuenta) return undefined;
      const id = setInterval(() => setTic((n) => n + 1), 250);
      return () => clearInterval(id);
    }, [hayCuenta]);

    const responder = (setMsg, okTexto, alOk) => (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      if (r && r.estado) poner(r.estado); else cargar();
      setMsg(msgDe(r, okTexto));
      if (r && r.ok && alOk) alOk(r);
    };
    const guardarAlarma = () => {
      if (!parsearHora(form.hora)) { setMsgA({ texto: 'Pon una hora (HH:MM).', error: true }); return; }
      const d = { hora: form.hora, dias: form.dias, una_vez: form.una_vez, texto: form.texto.trim().slice(0, TEXTO_MAX) };
      if (form.id) d.id = form.id;
      const ok = pedir('alarma_guardar', [JSON.stringify(d)],
        responder(setMsgA, form.id ? 'Alarma cambiada.' : `Alarma para las ${form.hora}.`, () => setForm(FORM_VACIO)));
      if (!ok) setMsgA({ texto: 'Las alarmas no están disponibles.', error: true });
    };
    const cambiarActiva = (a, v) => pedir('alarma_guardar', [JSON.stringify({ id: a.id, activa: !!v })],
      responder(setMsgA, v ? `Alarma de las ${hhmm(a.hora, a.minuto)} activada.` : `Alarma de las ${hhmm(a.hora, a.minuto)} apagada.`));
    const borrar = (a, setMsg, okTexto) => pedir('alarma_borrar', [a.id], responder(setMsg, okTexto, () => {
      if (form.id === a.id) setForm(FORM_VACIO);
    }));
    const editar = (a) => { setForm({ id: a.id, hora: hhmm(a.hora, a.minuto), dias: letrasDe(a.dias), una_vez: a.una_vez, texto: a.texto }); setMsgA(null); };
    const alternarDia = (ch) => setForm((f) => {
      const m = mascara(f.dias) ^ (1 << DIAS.indexOf(ch));
      return { ...f, dias: letrasDe(m) };
    });
    const crearTemporizador = (payload, okTexto) => {
      const ok = pedir('temporizador_crear', [JSON.stringify(payload)], responder(setMsgT, okTexto));
      if (!ok) setMsgT({ texto: 'Los temporizadores no están disponibles.', error: true });
    };
    const crearDesdeForm = () => {
      const seg = segundosDe(dur.h, dur.m, dur.s);
      if (seg < 1 || seg > MAX_S) { setMsgT({ texto: 'Pon una duración entre 1 segundo y 24 horas.', error: true }); return; }
      crearTemporizador({ h: dur.h, m: dur.m, s: dur.s, texto: dur.texto.trim().slice(0, TEXTO_MAX), iniciar: true },
        `Temporizador de ${etiquetaTiempo(seg)} en marcha.`);
    };
    const accion = (t, a) => pedir('temporizador_accion', [t.id, a],
      responder(setMsgT, { iniciar: 'En marcha.', parar: 'Parado.', reiniciar: 'Reiniciado.', borrar: 'Temporizador borrado.' }[a]));
    const probar = () => {
      const demo = !puente();
      pedir('alarma_probar', [], (r) => {
        if (!vivo.current) return;
        setMsgA(demo ? { texto: 'Demo: la prueba suena en la app.', error: true }
          : r ? { texto: 'Sonando una prueba…', ok: true } : { texto: 'No pude probarla (¿están en marcha las alarmas?).', error: true });
      });
    };
    const activar = (v) => pedir('config_alarmas_guardar', [JSON.stringify({ activo: !!v })], (j) => {
      const r = leer(j, {});
      if (!vivo.current) return;
      cargar();
      setMsgA(r && r.ok ? { texto: v ? 'Alarmas activadas.' : 'Alarmas en pausa: no sonará ninguna.', ok: true } : msgDe(r));
    });
    const numero = (k, max) => (e) => {
      const v = Math.round(acotar(Number(e.target.value) || 0, 0, max));
      setDur((d) => ({ ...d, [k]: v }));
    };

    const ahora = new Date();
    const desfaseS = ahoraS() - Date.now() / 1000;
    const prox = estado.activo ? proxima(estado.alarmas, ahora, desfaseS) : null;
    const mask = mascara(form.dias);
    const aviso = modo === 'demo' ? 'Demo sin la app: se guardan en esta página y no suenan.'
      : !estado.disponible ? 'Las alarmas aún no están en marcha (arrancan con los servicios de escritorio).' : '';
    const Papelera = window.IconTrash || (() => '✕');
    return (
      <div className="ln-settings ln-alarmas">
        <div className="ln-settings-inner">
          <header className="ln-settings-head">
            <div className="lune-overline">// Despertador · temporizadores</div>
            <h2 className="ln-settings-title"><span>ALARMAS</span></h2>
          </header>

          <Card id="al-alarmas" eyebrow={<><IconoAlarma width={13} height={13}/> Alarmas</>} title="Alarmas" tone="yellow" tick>
            {aviso && <p className="ln-al-nota">{aviso}</p>}
            <div className="ln-al-prox">
              <Badge variant={estado.activo ? 'yellow' : 'ink'} outline={!estado.activo}>{estado.activo ? 'ACTIVAS' : 'EN PAUSA'}</Badge>
              <span className="ln-al-prox-tx">
                {!estado.activo ? 'Ninguna alarma sonará hasta que las actives.'
                  : prox ? `Próxima: ${hhmm(prox.alarma.hora, prox.alarma.minuto)}${prox.alarma.texto ? ` · ${prox.alarma.texto}` : ''} (${textoFalta(prox.cuando.getTime() - ahora.getTime())})`
                  : 'No hay ninguna alarma activa.'}
              </span>
              <Switch label="Alarmas activas" checked={estado.activo} onChange={(e) => activar(!!e.target.checked)} accent="yellow" />
            </div>

            <div className="ln-al-sub">{form.id ? 'Editar alarma' : 'Nueva alarma'}</div>
            <div className="ln-al-form">
              <div className="lune-field">
                <label className="lune-field-label" htmlFor="f-al-hora">Hora</label>
                <input id="f-al-hora" className="lune-input ln-al-hora-in" type="time" step={60} value={form.hora}
                  onChange={(e) => setForm((f) => ({ ...f, hora: e.target.value }))} />
              </div>
              <div className="lune-field">
                <span className="lune-field-label">Días</span>
                <div className="ln-al-dias" role="group" aria-label="Días de la semana">
                  {DIAS.split('').map((ch, i) => (
                    <button key={ch} type="button" className={`ln-al-dia${mask & (1 << i) ? ' is-on' : ''}`}
                      aria-pressed={!!(mask & (1 << i))} aria-label={NOMBRES[i]} title={NOMBRES[i]} onClick={() => alternarDia(ch)}>{LETRAS[i]}</button>
                  ))}
                </div>
              </div>
              <div className="ln-al-texto-in">
                <Input id="f-al-texto" label="Texto (opcional)" placeholder="gimnasio, sacar la ropa…" value={form.texto} maxLength={TEXTO_MAX}
                  onChange={(e) => setForm((f) => ({ ...f, texto: e.target.value }))}
                  onKeyDown={(e) => { if (e.key === 'Enter') guardarAlarma(); }} />
              </div>
            </div>
            <div className="ln-al-acciones">
              <Switch label="Solo una vez" checked={form.una_vez} onChange={(e) => setForm((f) => ({ ...f, una_vez: !!e.target.checked }))} />
              <span className="ln-al-nota" style={{ margin: 0, alignSelf: 'center' }}>{textoDias(mask, form.una_vez)}</span>
            </div>
            <div className="ln-al-acciones">
              <Button size="sm" variant="primary" onClick={guardarAlarma}>{form.id ? 'Guardar cambios' : 'Añadir alarma'}</Button>
              {form.id && <Button size="sm" variant="ghost" onClick={() => { setForm(FORM_VACIO); setMsgA(null); }}>Cancelar</Button>}
              <Button size="sm" variant="ghost" onClick={probar}>Probar</Button>
            </div>
            <Msg msg={msgA} />
            <div className="ln-al-lista">
              {estado.alarmas.length === 0 && <p className="ln-empty">Sin alarmas. También puedes pedírsela a Lune: «pon una alarma a las 7».</p>}
              {estado.alarmas.map((a) => (
                <div key={a.id} className={`ln-al-fila${a.activa ? '' : ' is-off'}${form.id === a.id ? ' is-editando' : ''}`}>
                  <span className="ln-al-hora">{hhmm(a.hora, a.minuto)}</span>
                  <div className="ln-al-meta">
                    <span className="ln-al-dias-tx">{textoDias(a.dias, a.una_vez)} · {a.id}</span>
                    <span className={`ln-al-texto${a.texto ? '' : ' is-vacio'}`}>{a.texto || 'sin texto'}</span>
                  </div>
                  <Switch label={a.activa ? 'Activa' : 'Apagada'} checked={a.activa} onChange={(e) => cambiarActiva(a, !!e.target.checked)} />
                  <Button size="sm" variant="ghost" onClick={() => editar(a)}>Editar</Button>
                  <button type="button" className="ln-al-icono" aria-label={`Borrar la alarma de las ${hhmm(a.hora, a.minuto)}`} title="Borrar"
                    onClick={() => borrar(a, setMsgA, `Alarma de las ${hhmm(a.hora, a.minuto)} borrada.`)}><Papelera width={16} height={16}/></button>
                </div>
              ))}
            </div>
          </Card>

          <Card id="al-temporizadores" eyebrow="⏲ Temporizadores" title="Temporizadores" tone="cyan">
            <div className="ln-al-dur">
              {[['h', 'Horas', 23], ['m', 'Min', 59], ['s', 'Seg', 59]].map(([k, et, max]) => (
                <div className="lune-field" key={k}>
                  <label className="lune-field-label" htmlFor={`f-tm-${k}`}>{et}</label>
                  <input id={`f-tm-${k}`} className="lune-input ln-al-num" type="number" min={0} max={max} step={1} value={dur[k]}
                    onChange={numero(k, max)} />
                </div>
              ))}
              <div className="ln-al-texto-in">
                <Input id="f-tm-texto" label="Texto (opcional)" placeholder="la pasta, el té…" value={dur.texto} maxLength={TEXTO_MAX}
                  onChange={(e) => { const v = e.target.value; setDur((d) => ({ ...d, texto: v })); }} />
              </div>
              <Button size="sm" variant="primary" onClick={crearDesdeForm}>Crear e iniciar</Button>
            </div>
            <div className="ln-al-rapidos">
              {RAPIDOS.map((min) => (
                <Button key={min} size="sm" variant="ghost" onClick={() => crearTemporizador({ segundos: min * 60, texto: '', iniciar: true },
                  `Temporizador de ${min} min en marcha.`)}>{min} min</Button>
              ))}
            </div>
            <Msg msg={msgT} />
            <div className="ln-al-lista">
              {estado.temporizadores.length === 0 && <p className="ln-empty">Sin temporizadores. «Avísame en 10 minutos» también vale.</p>}
              {estado.temporizadores.map((t) => {
                const r = restante(t, ahoraS());
                const enMarcha = t.activo && t.objetivo > 0;
                return (
                  <div key={t.id} className="ln-al-fila">
                    <span className={`ln-al-cuenta${!enMarcha ? ' is-parado' : ''}${enMarcha && r <= 0 ? ' is-cero' : ''}`} id={`tm-${t.id}`}>{formatoDuracion(r)}</span>
                    <div className="ln-al-meta">
                      <span className="ln-al-dias-tx">{etiquetaTiempo(t.duracion_s)} · {enMarcha ? (r > 0 ? 'en marcha' : '¡suena!') : 'parado'} · {t.id}</span>
                      <span className={`ln-al-texto${t.texto ? '' : ' is-vacio'}`}>{t.texto || 'sin texto'}</span>
                    </div>
                    {enMarcha
                      ? <Button size="sm" variant="ghost" onClick={() => accion(t, 'parar')}>Parar</Button>
                      : <Button size="sm" variant="secondary" onClick={() => accion(t, 'iniciar')}>Iniciar</Button>}
                    <Button size="sm" variant="ghost" onClick={() => accion(t, 'reiniciar')}>Reiniciar</Button>
                    <button type="button" className="ln-al-icono" aria-label={`Borrar el temporizador ${t.id}`} title="Borrar"
                      onClick={() => accion(t, 'borrar')}><Papelera width={16} height={16}/></button>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // ── Banner global: lo que está sonando ─────────────────────────────────────
  function AlarmaBanner() {
    const { Button } = window.LUNE;
    const vivo = useVivo();
    const [son, setSon] = useState(null);                 // sonando + puedeEn (ms del reloj de la página)
    const [posponerMin, setPosponerMin] = useState(5);
    const [, setTic] = useState(0);
    useEffect(() => {
      const quitar = [];
      const alSonar = (o) => {
        const s = normalizarSonando(leer(o, null));
        if (!s || !vivo.current) return;
        setSon({ ...s, puedeEn: Date.now() + s.apagar_en_ms });
        pedir('config_alarmas', [], (j) => { const c = normalizarConfigAlarmas(leer(j, {})); if (vivo.current) setPosponerMin(c.posponer_min); });
      };
      const cablear = () => {
        quitar.push(conectar('alarma_sonando', alSonar));
        quitar.push(conectar('alarma_apagada', () => { if (vivo.current) setSon(null); }));
        // Recarga de la página a media alarma: la que ya suena
        pedir('alarmas_json', [], (j) => { const e = leer(j, null); if (e && e.sonando) alSonar(e.sonando); });
      };
      const q = alListo(cablear);
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    const bloqueada = !!son && Date.now() < son.puedeEn;
    useEffect(() => {
      if (!bloqueada) return undefined;
      const id = setInterval(() => setTic((n) => n + 1), 250);
      return () => clearInterval(id);
    }, [bloqueada, son]);
    if (!son) return null;
    const falta = Math.max(0, Math.ceil((son.puedeEn - Date.now()) / 1000));
    const apagar = () => pedir('alarma_apagar', [], (ok) => { if (ok && vivo.current) setSon(null); });
    const posponer = () => pedir('alarma_posponer', [], (ok) => { if (ok && vivo.current) setSon(null); });
    return (
      <div className="ln-alarma-banner" role="alertdialog" aria-live="assertive" aria-label={tituloSonando(son)}>
        <span className="ln-alarma-ic" aria-hidden="true"><IconoAlarma /></span>
        <div className="ln-alarma-tx">
          <div className="ln-alarma-tit">{tituloSonando(son)}{son.programado ? ` · ${son.programado.slice(-5)}` : ''}</div>
          <div className="ln-alarma-texto">{son.texto || (son.tipo === 'temporizador' ? '¡Se acabó el tiempo!' : '¡Es la hora!')}</div>
          {son.cola > 0 && <div className="ln-alarma-cola">+{son.cola} {son.cola === 1 ? 'aviso' : 'avisos'} en cola</div>}
        </div>
        <div className="ln-alarma-acc">
          <Button size="sm" variant="danger" disabled={bloqueada} onClick={apagar}>{bloqueada ? `Apagar (${falta})` : 'Apagar'}</Button>
          {son.tipo !== 'prueba' && <Button size="sm" variant="ghost" onClick={posponer}>Posponer {son.posponer_min || posponerMin} min</Button>}
        </div>
      </div>
    );
  }

  // ── Ajustes: alarmas ───────────────────────────────────────────────────────
  function AlarmasCard() {
    const { Card, Button, Switch } = window.LUNE;
    const vivo = useVivo();
    const { estado } = useEstadoAlarmas(vivo);
    const [cfg, setCfg] = useState(ALARMAS_DEFECTO);
    const [msg, setMsg] = useState(null);
    useEffect(() => {
      const cargar = () => pedir('config_alarmas', [], (j) => { if (vivo.current) setCfg(normalizarConfigAlarmas(leer(j, {}))); });
      const q = alListo(cargar);
      if (!puente()) cargar();
      return q;
    }, []);
    const guardar = (parcial) => {
      setCfg((c) => normalizarConfigAlarmas({ ...c, ...parcial }));
      pedir('config_alarmas_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.estado) setCfg(normalizarConfigAlarmas(r.estado));
        setMsg(msgDe(r, 'Guardado.'));
      });
    };
    const diferido = useMemo(() => crearRetardo((p) => guardar(p), 350), []);
    const deslizar = (k) => (v) => { setCfg((c) => ({ ...c, [k]: v })); diferido({ [k]: v }); };
    const probar = () => {
      const demo = !puente();
      pedir('alarma_probar', [], (r) => {
        if (!vivo.current) return;
        setMsg(demo ? { texto: 'Demo: la prueba suena en la app.', error: true }
          : r ? { texto: 'Sonando una prueba…', ok: true } : { texto: 'No pude probarla.', error: true });
      });
    };
    const prox = cfg.activo ? proxima(estado.alarmas, new Date(), estado.ahora ? estado.ahora - Date.now() / 1000 : 0) : null;
    const enMarcha = estado.temporizadores.filter((t) => t.activo && t.objetivo > 0).length;
    const n = estado.alarmas.length;
    return (
      <Card id="aj-alarmas" eyebrow={<><IconoAlarma width={13} height={13}/> Ocio · Alarmas</>} title="Alarmas y temporizadores" tone="yellow">
        <div className="ln-al-prox">
          <span className="ln-al-prox-tx">
            {n} {n === 1 ? 'alarma' : 'alarmas'} · {enMarcha} {enMarcha === 1 ? 'temporizador en marcha' : 'temporizadores en marcha'}
            {prox ? ` · próxima ${hhmm(prox.alarma.hora, prox.alarma.minuto)}` : ''}
          </span>
          <Button size="sm" variant="secondary" onClick={() => abrirVista('alarmas')}>Abrir alarmas</Button>
        </div>
        <div className="ln-toggle-row">
          <Switch label="Alarmas activas" checked={cfg.activo} onChange={(e) => guardar({ activo: !!e.target.checked })} accent="yellow" />
          <Switch label="Pantalla grande al sonar" checked={cfg.pantalla_grande} onChange={(e) => guardar({ pantalla_grande: !!e.target.checked })} />
          <Switch label="Decir el texto en voz alta" checked={cfg.decir_texto} onChange={(e) => guardar({ decir_texto: !!e.target.checked })} accent="blue" />
        </div>
        <div className="ln-al-sub">Sonido</div>
        <div className="ln-seg-row">
          {SONIDOS.map(([k, et]) => (
            <Button key={k} size="sm" variant={cfg.sonido === k ? 'primary' : 'ghost'} onClick={() => guardar({ sonido: k })}>{et}</Button>
          ))}
          <Button size="sm" variant="ghost" onClick={probar}>Probar</Button>
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-settings-grid">
          <Deslizador id="f-al-volumen" label="Volumen" min={0} max={100} step={5} value={Math.round(cfg.volumen * 100)}
            fmt={(v) => `${v} %`} onChange={(v) => deslizar('volumen')(v / 100)} />
          <Deslizador id="f-al-bloqueo" label="Bloqueo antes de poder apagar" min={0} max={30} value={cfg.bloqueo_s}
            fmt={(v) => (v ? `${v} s` : 'sin bloqueo')} hint="Para no apagarla sin querer al tocar el ratón." onChange={deslizar('bloqueo_s')} />
          <Deslizador id="f-al-posponer" label="Posponer" min={1} max={60} value={cfg.posponer_min} fmt={(v) => `${v} min`} onChange={deslizar('posponer_min')} />
          <Deslizador id="f-al-recuperar" label="Recuperar las que se pasaron" min={0} max={120} step={5} value={cfg.recuperar_min}
            fmt={(v) => (v ? `≤ ${v} min` : 'no')} hint="Si el PC estaba suspendido o Lune cerrada." onChange={deslizar('recuperar_min')} />
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  // ── Ajustes: pantalla grande y salvapantallas ──────────────────────────────
  function atajoDe(lista) {
    const e = (Array.isArray(lista) ? lista : []).find((x) => x && x.id === 'pantalla_grande');
    if (!e) return null;
    return { texto: txt(e.texto || e.combo, 40), disponible: e.disponible !== false };
  }
  function PantallaGrandeCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    const vivo = useVivo();
    const [cfg, setCfg] = useState(() => normalizarConfigGrande(null));
    const [grande, setGrande] = useState(() => normalizarGrande(null));
    const [atajo, setAtajo] = useState(null);
    const [msg, setMsg] = useState(null);
    useEffect(() => {
      const quitar = [];
      const alGrande = (j) => { if (vivo.current) setGrande(normalizarGrande(leer(j, {}))); };
      const cablear = () => {
        pedir('config_grande', [], (j) => { if (vivo.current) setCfg(normalizarConfigGrande(leer(j, {}))); });
        pedir('grande_estado_json', [], alGrande);
        quitar.push(conectar('grande_estado', alGrande));
        // El atajo es del corte 4 (window.luneEscritorio)
        const esc = window.luneEscritorio;
        const alAtajos = (j) => { const o = leer(j, {}); if (vivo.current) setAtajo(atajoDe(o && o.lista)); };
        if (esc && typeof esc.atajos_estado === 'function') { try { esc.atajos_estado(alAtajos); } catch (e) { /* sin ranura */ } }
        const s = esc && esc.atajos_cambio;
        if (s && typeof s.connect === 'function') {
          try { s.connect(alAtajos); quitar.push(() => { try { s.disconnect(alAtajos); } catch (e) { /* ya no está */ } }); } catch (e) { /* sin señal */ }
        }
      };
      const q = alListo(cablear);
      if (!puente()) cablear();
      return () => { q(); quitar.splice(0).forEach((f) => f()); };
    }, []);
    const guardar = (parcial) => {
      setCfg((c) => normalizarConfigGrande({ ...c, ...parcial }));
      pedir('config_grande_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r && r.estado) setCfg(normalizarConfigGrande(r.estado));
        setMsg(msgDe(r, 'Guardado.'));
      });
    };
    const diferido = useMemo(() => crearRetardo((p) => guardar(p), 350), []);
    const alternar = () => {
      const demo = !puente();
      pedir('grande_alternar', [], (ok) => {
        if (!vivo.current) return;
        if (demo) { pedir('grande_estado_json', [], (j) => setGrande(normalizarGrande(leer(j, {})))); setMsg({ texto: 'Demo: la pantalla grande es de la app.', error: true }); return; }
        setMsg(ok ? null : { texto: 'No pude (necesita la mascota en VRM o animada, o se sustituye por el reloj).', error: true });
      });
    };
    const probar = () => {
      const demo = !puente();
      pedir('salvapantallas_probar', [], (ok) => {
        if (!vivo.current) return;
        setMsg(demo ? { texto: 'Demo: el salvapantallas es de la app.', error: true }
          : ok ? { texto: 'Salvapantallas en marcha: mover el ratón no lo quita; un clic o una tecla, sí.', ok: true }
          : { texto: 'Ahora no se puede (¿un juego, una alarma o la pantalla grande?).', error: true });
      });
    };
    const paso = cfg.pasos[cfg.paso] || cfg.pasos[0];
    return (
      <Card id="aj-grande" eyebrow="▣ Ocio · Pantalla grande" title="Pantalla grande y salvapantallas" tone="cyan">
        <p className="ln-al-nota">
          Lune llena el monitor con la cara encuadrada (mascota VRM o animada; con sprites o sin mascota, un reloj con su carita).
          El salvapantallas la pone así, dormida, cuando llevas un rato sin tocar nada.
        </p>
        <div className="ln-al-estado">
          <Badge variant={grande.activa ? 'cyan' : 'ink'} outline={!grande.activa}>{grande.activa ? 'PANTALLA GRANDE' : 'normal'}</Badge>
          {grande.activa && grande.motivo && <span className="ln-al-nota" style={{ margin: 0 }}>{MOTIVOS[grande.motivo]}</span>}
          <span style={{ flex: 1 }} />
          <span className="ln-al-nota" style={{ margin: 0 }}>Atajo</span>
          <span className={`ln-al-kbd${atajo && atajo.texto ? '' : ' is-vacio'}`}>{atajo ? (atajo.texto || 'sin atajo') : 'Ctrl+Alt+Shift+B'}</span>
        </div>
        <div className="ln-toggle-row">
          <Switch label="Salvapantallas" checked={cfg.activo} onChange={(e) => guardar({ activo: !!e.target.checked })} />
        </div>
        <div style={{ height: 12 }} />
        <Deslizador id="f-grande-paso" label="Esperar sin tocar nada" min={0} max={cfg.pasos.length - 1} value={cfg.paso}
          fmt={() => (paso ? paso.etiqueta : '')} disabled={!cfg.activo} hint="Con un juego, una alarma o Lune hablando no salta."
          onChange={(v) => { setCfg((c) => ({ ...c, paso: v })); diferido({ paso: v }); }} />
        <div style={{ height: 12 }} />
        <div className="ln-toggle-row">
          <Switch label="Un clic sale también de la pantalla grande" checked={cfg.clic_sale_de_todo}
            onChange={(e) => guardar({ clic_sale_de_todo: !!e.target.checked })} accent="blue" />
          <Switch label="Oscurecer el fondo" checked={cfg.fondo_oscuro} onChange={(e) => guardar({ fondo_oscuro: !!e.target.checked })} />
          <Switch label="Mostrar la hora" checked={cfg.reloj} onChange={(e) => guardar({ reloj: !!e.target.checked })} accent="yellow" />
        </div>
        <div className="ln-al-acciones">
          <Button size="sm" variant="secondary" onClick={probar}>Probar salvapantallas</Button>
          <Button size="sm" variant={grande.activa ? 'primary' : 'ghost'} onClick={alternar}>
            {grande.activa ? 'Salir de pantalla grande' : 'Pantalla grande ahora'}
          </Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  Object.assign(window, {
    AlarmasPanel,
    AlarmaBanner,
    AlarmasCard,
    PantallaGrandeCard,
    LuneAlarmas: {
      parsearHora, mascara, letrasDe, textoDias, normalizarAlarma, normalizarTemporizador, normalizarSonando,
      normalizarEstado, normalizarProxima, restante, formatoDuracion, proximaVez, proxima, textoFalta, etiquetaTiempo, tituloSonando,
      normalizarConfigAlarmas, normalizarConfigGrande, normalizarGrande, abrirVista, TIEMPOS, DIAS,
    },
  });
})();
