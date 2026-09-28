/* Lune CD desktop — Apariencia, atajos, menú radial y bandeja (Ajustes, corte 4) + menú radial SVG.
 *
 * Tarjetas (se montan en settings.jsx con `window.X && <window.X/>`; no usan cfg/set de SettingsPanel:
 * guardan al momento por el segundo objeto del QWebChannel, window.luneEscritorio):
 *   AparienciaCard   tema: presets (cian, magenta mate, violeta, rojo neón, ámbar, verde ácido) o
 *                    tono/saturación personalizados + teñir el amarillo (tenir_pop) y los fondos
 *                    (tenir_fondo). Vista previa ≤ 1 llamada cada 50 ms; guarda 400 ms tras el último cambio.
 *   AtajosCard       atajos globales con «Detectar» (KeyboardEvent.code + modificadores; mientras
 *                    captura, atajos_capturando(true) pausa los de Lune; Esc, perder el foco o 15 s cancelan).
 *   MenuRadialCard   botones del menú radial (hasta 10, en orden), sonidos y «Probar».
 *   BandejaCard      acciones rápidas del menú de la bandeja.
 * Menú radial SVG (versión web de ui/menu_radial.py, misma geometría: lienzo 368, zona muerta 85,
 * iconos a 120, anillo exterior 165, 1–10 botones, ángulo horario desde arriba):
 *   RadialMenu       el menú (se abre donde se pida; pulsar = escala 0.8, soltar = ejecutar; Esc, clic
 *                    derecho, soltar en la zona muerta o perder el foco lo cierran).
 *   RadialHost       lo monta app.jsx: escucha window 'lune-radial' ({x, y, tipo}), pide los botones a
 *                    acciones_catalogo(tipo) y ejecuta con accion_menu(id, arg). «ajustes»/«chat» navegan
 *                    en la propia página; «expresiones» abre un segundo radial (con la mascota en la barra,
 *                    la expresión la pone la barra; con la mascota fuera, el backend).
 *   window.LuneRadial = {indice, posiciones, factorLerp, sector, abrir(x?, y?, tipo?), …}
 * Enlace con app.jsx (window.LuneApariencia):
 *   conectarApp({setFx, setModoJuego, setView}) → limpiar   efectos desde la config (localStorage solo de
 *        respaldo), tema_estado → window.luneTema al arrancar y en tema_cambio, juego_estado → modo juego,
 *        navegar → vista (#sección = desplazarse a la tarjeta id="aj-<sección>").
 *   guardarEfecto('bg'|'sweep'|'micro', bool)              efectos_guardar({fondo|barrido|micro: bool})
 *
 * Puente (todo opcional; sin él, demo local en el navegador): ver ui/puente_escritorio.py.
 * Se registra solo (Object.assign(window, …)) dentro de una IIFE: Babel (preset env) convertiría los
 * const de nivel superior en var globales y pisaría los de otros .jsx.
 */
(function () {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;

  // ── Puente: window.luneEscritorio (QWebChannel; los resultados llegan por callback) ──
  const puente = () => window.luneEscritorio || null;
  function llamar(nombre, args, cb) {
    const e = puente();
    if (!e || typeof e[nombre] !== 'function') return false;
    try { e[nombre](...(args || []), (r) => { if (cb) cb(r); }); return true; } catch (err) { return false; }
  }
  function conectar(senal, fn) {
    const e = puente();
    const s = e && e[senal];
    if (!s || typeof s.connect !== 'function') return () => {};
    try { s.connect(fn); } catch (err) { return () => {}; }
    return () => { try { s.disconnect(fn); } catch (err) { /* ya no está */ } };
  }
  function leer(j, def) {
    if (j == null) return def;
    if (typeof j === 'object') return j;
    try { const o = JSON.parse(j); return o == null ? def : o; } catch (e) { return def; }
  }
  const ID_OK = /^[a-z][a-z0-9_]{0,39}$/;
  const recortar = (s, n) => { const t = String(s == null ? '' : s); return t.length > n ? t.slice(0, n - 1) + '…' : t; };

  // ── Geometría del radial (la misma que ui/menu_radial.py) ──────────────────
  const LIENZO = 368, CENTRO = LIENZO / 2, ZONA_MUERTA = 85, RADIO_ICONOS = 120, RADIO_EXTERIOR = 165, MAX_BOTONES = 10;

  /** Botón bajo (dx, dy) respecto al centro (y hacia abajo), en sentido horario desde arriba.
   *  El botón 0 ocupa [0°, 360/n); null en la zona muerta (distancia ≤ zonaMuerta) o sin botones. */
  function indice(dx, dy, n, zonaMuerta = ZONA_MUERTA) {
    n = Math.floor(Number(n));
    dx = Number(dx); dy = Number(dy);
    if (!(n >= 1) || !isFinite(dx) || !isFinite(dy)) return null;
    if (Math.hypot(dx, dy) <= zonaMuerta) return null;
    // Igual que angulo() de ui/menu_radial.py: math.degrees(x) = x * (180 / pi) y el % de Python
    // (fmod y, si sale negativo, + 360), para que las fronteras caigan en el mismo botón.
    let a = (Math.atan2(dx, -dy) * (180 / Math.PI)) % 360;
    if (a < 0) a += 360;
    if (a >= 360 || a === 0) a = 0;
    return Math.min(n - 1, Math.floor(a / (360 / n)));
  }
  /** Centro de cada botón: [x, y] respecto al centro, a mitad de su sector. */
  function posiciones(n, radio = RADIO_ICONOS) {
    n = Math.max(0, Math.floor(Number(n) || 0));
    const out = [];
    for (let i = 0; i < n; i++) {
      const a = (i + 0.5) * (2 * Math.PI / n);
      out.push([radio * Math.sin(a), -radio * Math.cos(a)]);
    }
    return out;
  }
  /** Lerp «por frame» de Unity normalizado por tiempo (dt en segundos), como factor_lerp de Python:
   *  con dt = 1/fpsRef da `base`; el mismo resultado a 30 o a 144 fps. */
  function factorLerp(base, dt, fpsRef = 60) {
    const b = Math.min(1, Math.max(0, Number(base) || 0));
    if (b >= 1) return 1;
    return 1 - Math.pow(1 - b, Math.max(0, Number(dt) || 0) * fpsRef);
  }
  const pt = (r, a, c) => [c + r * Math.sin(a), c - r * Math.cos(a)].map((v) => Math.round(v * 100) / 100).join(' ');
  /** Path SVG del sector anular i de n (entre r0 y r1). Con n = 1, el anillo entero (evenodd). */
  function sector(i, n, r0 = ZONA_MUERTA, r1 = RADIO_EXTERIOR, c = CENTRO) {
    if (n <= 1) {
      return `M ${c} ${c - r1} A ${r1} ${r1} 0 1 1 ${c} ${c + r1} A ${r1} ${r1} 0 1 1 ${c} ${c - r1} Z `
        + `M ${c} ${c - r0} A ${r0} ${r0} 0 1 0 ${c} ${c + r0} A ${r0} ${r0} 0 1 0 ${c} ${c - r0} Z`;
    }
    const paso = 2 * Math.PI / n, a0 = i * paso, a1 = (i + 1) * paso;
    const grande = paso > Math.PI ? 1 : 0;
    return `M ${pt(r0, a0, c)} L ${pt(r1, a0, c)} A ${r1} ${r1} 0 ${grande} 1 ${pt(r1, a1, c)} `
      + `L ${pt(r0, a1, c)} A ${r0} ${r0} 0 ${grande} 0 ${pt(r0, a0, c)} Z`;
  }

  // ── Iconos (trazos 24×24; nombres de ui/icons.py y alias) ──────────────────
  const ICONOS = {
    gear: ['M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'],
    chat: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
    eye: ['M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
    smile: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M8 14s1.5 2 4 2 4-2 4-2', 'M9 9h.01', 'M15 9h.01'],
    frown: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M16 16s-1.5-2-4-2-4 2-4 2', 'M9 9h.01', 'M15 9h.01'],
    angry: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M16 16s-1.5-2-4-2-4 2-4 2', 'M7.5 8 10 9', 'M16.5 8 14 9'],
    surprised: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 17a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', 'M9 9h.01', 'M15 9h.01'],
    thinking: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M9 15h6', 'M9 9h.01', 'M15 9h.01'],
    hand: ['M18 11V6a2 2 0 0 0-4 0v5', 'M14 10V4a2 2 0 0 0-4 0v6', 'M10 10.5V6a2 2 0 0 0-4 0v8', 'M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15'],
    music: ['M9 18V5l12-2v13', 'M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'M18 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
    clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 6v6l4 2'],
    volume: ['M11 5 6 9H2v6h4l5 4z', 'M19 12a7 7 0 0 0-3-5.7', 'M15.5 8.5a3.5 3.5 0 0 1 0 5'],
    volume_off: ['M11 5 6 9H2v6h4l5 4z', 'M22 9l-6 6', 'M16 9l6 6'],
    moon: ['M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z'],
    maximize: ['M15 3h6v6', 'M9 21H3v-6', 'M21 3l-7 7', 'M3 21l7-7'],
    down: ['M12 5v14', 'M19 12l-7 7-7-7'],
    cake: ['M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8', 'M4 16s.5-1 2-1 2.5 2 4 2 2.5-2 4-2 2.5 2 4 2 2-1 2-1', 'M2 21h20', 'M7 8v3', 'M12 8v3', 'M17 8v3'],
    cup: ['M17 8h1a4 4 0 1 1 0 8h-1', 'M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z', 'M6 2v2', 'M10 2v2', 'M14 2v2'],
    bookmark: ['M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'],
    ghost: ['M9 10h.01', 'M15 10h.01', 'M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8z'],
    phone: ['M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z'],
    mic: ['M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z', 'M19 10v2a7 7 0 0 1-14 0v-2', 'M12 19v3'],
    gamepad: ['M6 12h4', 'M8 10v4', 'M15 13h.01', 'M18 11h.01', 'M17.32 5H6.68a4 4 0 0 0-3.98 3.59l-.9 7.18A3 3 0 0 0 4.78 19c.93 0 1.8-.45 2.34-1.21L8.5 16h7l1.38 1.79A2.87 2.87 0 0 0 19.22 19a3 3 0 0 0 2.98-3.23l-.9-7.18A4 4 0 0 0 17.32 5z'],
    user: ['M20 21a8 8 0 1 0-16 0', 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z'],
    corner: ['M4 10V4h6', 'M20 14v6h-6'],
    close: ['M18 6 6 18', 'M6 6l12 12'],
    bolt: ['M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z'],
    search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'M21 21l-4.3-4.3'],
    brain: ['M12 5a3 3 0 1 0-5.99.14 4 4 0 0 0-1.5 7.06A3.5 3.5 0 0 0 8 18.5 3 3 0 0 0 12 19m0-14a3 3 0 1 1 5.99.14 4 4 0 0 1 1.5 7.06A3.5 3.5 0 0 1 16 18.5 3 3 0 0 1 12 19m0-14v14'],
    telegram: ['M22 3l-9.5 9.5', 'M22 3 15 21l-4-8-8-4 19-6z'],
    power: ['M12 2v10', 'M18.36 6.64a9 9 0 1 1-12.73 0'],
    window: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M3 9h18'],
    radial: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M12 2v6', 'M12 16v6', 'M2 12h6', 'M16 12h6'],
    log_out: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'M16 17l5-5-5-5', 'M21 12H9'],
    sun: ['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z', 'M12 1v2', 'M12 21v2', 'M4.22 4.22l1.42 1.42', 'M18.36 18.36l1.42 1.42',
      'M1 12h2', 'M21 12h2', 'M4.22 19.78l1.42-1.42', 'M18.36 5.64l1.42-1.42'],
    message_dots: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', 'M8 10h.01', 'M12 10h.01', 'M16 10h.01'],
    pin: ['M12 17v5', 'M9 3h6l-1 7 4 4H6l4-4z'],
    frame: ['M22 6H2', 'M22 18H2', 'M6 2v20', 'M18 2v20'],
    monitor: ['M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M8 21h8', 'M12 17v4'],
    pause: ['M6 4h4v16H6z', 'M14 4h4v16h-4z'],
    alarm: ['M12 21a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'M12 9v4l2 2', 'M5 3 2 6', 'M22 6l-3-3'],
    timer: ['M10 2h4', 'M12 14l3-3', 'M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16z'],
    package: ['M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z',
      'M3.27 6.96 12 12.01l8.73-5.05', 'M12 22.08V12'],
    palette: ['M12 22a10 10 0 1 1 10-10c0 2.5-2 3-3.5 3H16a2 2 0 0 0-1.5 3.3A1.7 1.7 0 0 1 12 22z', 'M7.5 10.5h.01', 'M10.5 7.5h.01', 'M15.5 7.5h.01'],
    cpu: ['M6 6h12v12H6z', 'M9 1v3', 'M15 1v3', 'M9 20v3', 'M15 20v3', 'M20 9h3', 'M20 14h3', 'M1 9h3', 'M1 14h3'],
    taskbar: ['M3 17h18v4H3z', 'M6 19h2', 'M10 19h2'],
    // Cortes 9/10: «Mis bailes» (la biblioteca del reproductor MMD/VRMA).
    film: ['M4.18 2h15.64A2.18 2.18 0 0 1 22 4.18v15.64A2.18 2.18 0 0 1 19.82 22H4.18A2.18 2.18 0 0 1 2 19.82V4.18A2.18 2.18 0 0 1 4.18 2z',
      'M7 2v20', 'M17 2v20', 'M2 12h20', 'M2 7h5', 'M2 17h5', 'M17 17h5', 'M17 7h5'],
  };
  const ALIAS_ICONO = {
    engranaje: 'gear', ajustes: 'gear', settings: 'gear', mensaje: 'chat', chat: 'chat', ojo: 'eye', comentar: 'eye',
    cara: 'smile', sonrisa: 'smile', expresiones: 'smile', happy: 'smile', triste: 'frown', sad: 'frown', enfado: 'angry',
    sorpresa: 'surprised', pensar: 'thinking', saludo: 'hand', wave: 'hand', musica: 'music', nota: 'music', bailar: 'music',
    baile: 'music', reloj: 'clock', alarma: 'clock', temporizador: 'clock', temporizador_rapido: 'clock', voz: 'volume',
    altavoz: 'volume', luna: 'moon', dormir: 'moon', despertar: 'moon', tamano: 'maximize', pantalla_grande: 'maximize',
    grande: 'maximize', bajar: 'down', flecha_abajo: 'down', pastel: 'cake', comer_pastel: 'cake', comida: 'cake',
    batido: 'cup', comer_batido: 'cup', vaso: 'cup', guardar_comida: 'bookmark', guardar: 'bookmark', fantasma: 'ghost',
    llamada: 'phone', telefono: 'phone', microfono: 'mic', juego: 'gamepad', modo_juego: 'gamepad',
    modo_juego_forzar: 'gamepad', minecraft: 'gamepad', mascota: 'user', usuario: 'user', esquina: 'corner',
    llevar_a_esquina: 'corner', cerrar: 'close', salir: 'log_out', discord: 'chat', rayo: 'bolt', buscar: 'search',
    message: 'chat', arrow_down: 'down', box: 'package', expresion: 'smile', cerrar_mascota: 'close',
    mostrar_lune: 'window', menu_radial: 'radial', comentarios_auto: 'message_dots', siempre_encima: 'pin',
    encuadre: 'frame', baile_pausa: 'pause', tema: 'palette', autoinicio: 'power', liberar_memoria: 'cpu',
    en_barra_tareas: 'taskbar', sentarse: 'taskbar', barra_tareas: 'taskbar',
    bailes: 'film', mis_bailes: 'film', pelicula: 'film', minecraft_bot: 'package', bot: 'package',
  };
  function trazosIcono(icono, id) {
    const k = String(icono || '').toLowerCase();
    return ICONOS[k] || ICONOS[ALIAS_ICONO[k]] || ICONOS[ALIAS_ICONO[String(id || '')]] || null;
  }

  // ── Botones del radial ──────────────────────────────────────────────────────
  function normalizarItems(lista) {
    const out = [];
    (Array.isArray(lista) ? lista : []).forEach((it) => {
      if (!it || typeof it !== 'object' || !ID_OK.test(String(it.id || ''))) return;
      out.push({
        id: String(it.id),
        etiqueta: recortar(it.etiqueta || it.id, 40),
        icono: String(it.icono || ''),
        arg: typeof it.arg === 'string' ? it.arg.slice(0, 40) : '',
        habilitado: it.habilitado !== false,
      });
    });
    return out.slice(0, MAX_BOTONES);
  }
  const it_ = (id, etiqueta, arg) => ({ id, etiqueta, icono: '', arg: arg || '', habilitado: true });
  // Demo sin backend (navegador): lo mínimo para ver y probar el menú.
  const DEMO = {
    principal: [it_('ajustes', 'Ajustes'), it_('chat', 'Chat'), it_('comentar', 'Comentar pantalla'),
      it_('expresiones', 'Expresiones'), it_('voz', 'Voz'), it_('dormir', 'Dormir')],
    secundario: [it_('comer_batido', 'Batido'), it_('comer_pastel', 'Pastel'), it_('guardar_comida', 'Guardar comida')],
    // Segundo radial: una expresión por botón (acción «expresion» con arg, como nucleo/acciones_ui.py).
    expresiones: [it_('expresion', 'Contenta', 'happy'), it_('expresion', 'Triste', 'sad'), it_('expresion', 'Enfadada', 'angry'),
      it_('expresion', 'Sorprendida', 'surprised'), it_('expresion', 'Pensativa', 'thinking'), it_('expresion', 'Saludar', 'wave')],
  };
  const TIPO_PUENTE = { principal: 'radial', secundario: 'secundario', expresiones: 'expresiones' };
  const ICONO_ARG = { happy: 'smile', sad: 'frown', angry: 'angry', surprised: 'surprised', thinking: 'thinking', wave: 'hand' };

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-c4-apariencia-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-c4-apariencia-css';
      st.textContent = `
        .ln-c4-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-c4-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-c4-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-c4-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-c4-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-c4-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-c4-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-c4-range input.ln-c4-hue{ -webkit-appearance:none; appearance:none; height:10px; border:var(--bw) solid var(--ink-500);
          background:linear-gradient(90deg, hsl(0 100% 50%), hsl(60 100% 50%), hsl(120 100% 50%), hsl(180 100% 50%), hsl(240 100% 50%), hsl(300 100% 50%), hsl(360 100% 50%)); }
        .ln-c4-estado{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-c4-estado.is-error{ color:var(--yellow-500); }
        .ln-c4-estado.is-ok{ color:var(--cyan-300); }
        .ln-c4-presets{ display:flex; flex-wrap:wrap; gap:8px; }
        .ln-c4-muestra{ display:inline-block; width:12px; height:12px; margin-right:6px; vertical-align:-1px; border:1px solid var(--ink-950); }
        .ln-c4-paleta{ display:flex; gap:6px; margin-top:14px; }
        .ln-c4-paleta i{ flex:1; height:14px; border:var(--bw) solid var(--ink-950); }
        .ln-c4-fila{ display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:var(--bw) solid var(--border); flex-wrap:wrap; }
        .ln-c4-fila:last-child{ border-bottom:none; }
        .ln-c4-fila-nombre{ flex:1; min-width:140px; font-family:var(--font-display); font-weight:600; font-size:13px; color:var(--text-strong); }
        .ln-c4-kbd{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); background:var(--ink-950); border:var(--bw) solid var(--cyan-700);
          padding:3px 9px; clip-path:var(--clip-tr); white-space:nowrap; }
        .ln-c4-kbd.is-vivo{ color:var(--ink-950); background:var(--yellow-500); border-color:var(--yellow-600); }
        .ln-c4-kbd.is-vacio{ color:var(--text-faint); border-color:var(--ink-500); }
        .ln-c4-num{ font-family:var(--font-mono); font-size:11px; color:var(--text-faint); width:18px; text-align:right; }
        .ln-c4-add{ display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap; }
        .ln-c4-add select{ flex:1; min-width:180px; }
        .ln-c4-grid{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:start; }
        .ln-c4-preview{ display:block; width:184px; height:184px; }
        @media (max-width: 760px){ .ln-c4-grid{ grid-template-columns:1fr; } }
        .ln-radial-capa{ position:fixed; inset:0; z-index:1100; cursor:default; }
        .ln-radial{ position:absolute; overflow:visible; transform:scale(.2); opacity:0; transform-origin:50% 50%;
          transition:transform .16s var(--ease-snap), opacity .12s ease; filter:drop-shadow(6px 6px 0 rgb(var(--ink-950-rgb, 5 7 15) / .75)); }
        .ln-radial.is-abierto{ transform:scale(1); opacity:1; }
        .ln-radial.is-abierto.is-pulsado{ transform:scale(.8); transition-duration:.09s; }
        .ln-radial-seg{ fill:var(--ink-850); stroke:var(--ink-500); stroke-width:2; cursor:pointer; transition:fill .09s ease; }
        .ln-radial-seg.is-sel{ fill:var(--cyan-500); stroke:var(--cyan-300); }
        .ln-radial-seg.is-off{ fill:var(--ink-900); cursor:not-allowed; }
        .ln-radial-arco{ fill:var(--yellow-500); pointer-events:none; }
        .ln-radial-ic{ color:var(--cyan-300); pointer-events:none; }
        .ln-radial-ic.is-sel{ color:var(--ink-950); }
        .ln-radial-ic.is-off{ color:var(--gray-600); }
        .ln-radial-ic text{ font-family:var(--font-display); font-weight:700; font-size:15px; fill:currentColor; }
        .ln-radial-centro{ fill:var(--ink-950); stroke:var(--cyan-700); stroke-width:2.5; pointer-events:none; }
        .ln-radial-txt{ font-family:var(--font-display); font-weight:700; font-style:italic; font-size:13px; letter-spacing:.04em;
          text-transform:uppercase; fill:var(--yellow-500); pointer-events:none; }
        .modo-juego .ln-radial{ transition:none; }
        @media (prefers-reduced-motion: reduce){ .ln-radial, .ln-radial.is-abierto.is-pulsado{ transform:none; transition:opacity .08s linear; } }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  function sonar(cfg, nombre) {
    if (!cfg || !cfg.sonidos) return;
    const s = window.luneSfx;
    if (!s || typeof s.tocar !== 'function') return;
    try { const r = s.tocar(nombre, { vol: cfg.volumen, pitch: [0.97, 1.03] }); if (r && r.catch) r.catch(() => {}); } catch (e) { /* sin audio */ }
  }

  // ── SVG del radial (menú y vista previa) ───────────────────────────────────
  function IconoRadial({ item, x, y, clase }) {
    const trazos = (item.id === 'expresion' && !item.icono && ICONOS[ICONO_ARG[item.arg]]) || trazosIcono(item.icono, item.id) || null;
    if (!trazos) {
      return (
        <g className={clase} transform={`translate(${x} ${y})`}>
          <text x="0" y="0" textAnchor="middle" dominantBaseline="central">{String(item.etiqueta || item.id).slice(0, 1).toUpperCase()}</text>
        </g>
      );
    }
    return (
      <g className={clase} transform={`translate(${x - 12} ${y - 12})`}>
        {trazos.map((d, k) => <path key={k} d={d} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />)}
      </g>
    );
  }

  function RadialSvg({ items, sel = null, titulo = '', clase = '', estilo, tamano = LIENZO, onPulsarItem }) {
    const n = items.length;
    const P = posiciones(n);
    const actual = sel != null ? items[sel] : null;
    return (
      <svg className={clase} width={tamano} height={tamano} viewBox={`0 0 ${LIENZO} ${LIENZO}`} style={estilo}
        role="menu" aria-label={titulo || 'Menú radial'}>
        {items.map((it, i) => (
          <path key={'s' + i} d={sector(i, n)} fillRule="evenodd" role="menuitem" aria-label={it.etiqueta}
            aria-disabled={it.habilitado === false ? 'true' : undefined} data-i={i}
            className={`ln-radial-seg${i === sel ? ' is-sel' : ''}${it.habilitado === false ? ' is-off' : ''}`}
            onClick={onPulsarItem ? () => onPulsarItem(i) : undefined} />
        ))}
        {sel != null && n > 0 && <path className="ln-radial-arco" d={sector(sel, n, RADIO_EXTERIOR, RADIO_EXTERIOR + 7)} fillRule="evenodd" />}
        {items.map((it, i) => (
          <IconoRadial key={'i' + i} item={it} x={CENTRO + P[i][0]} y={CENTRO + P[i][1]}
            clase={`ln-radial-ic${i === sel ? ' is-sel' : ''}${it.habilitado === false ? ' is-off' : ''}`} />
        ))}
        <circle className="ln-radial-centro" cx={CENTRO} cy={CENTRO} r={ZONA_MUERTA - 8} />
        <text className="ln-radial-txt" x={CENTRO} y={CENTRO} textAnchor="middle" dominantBaseline="central">
          {recortar(actual ? actual.etiqueta : (titulo || 'Lune'), 18)}
        </text>
      </svg>
    );
  }

  /** Dónde va el lienzo para que quepa entero en la ventana: {cx, cy, left, top}. */
  function colocar(x, y) {
    const W = Number(window.innerWidth) || 1280, H = Number(window.innerHeight) || 820;
    const fija = (v, max) => (max >= LIENZO ? Math.min(max - CENTRO, Math.max(CENTRO, v)) : max / 2);
    const cx = fija(isFinite(Number(x)) ? Number(x) : W / 2, W);
    const cy = fija(isFinite(Number(y)) ? Number(y) : H / 2, H);
    return { cx, cy, left: cx - CENTRO, top: cy - CENTRO };
  }

  // ── RadialMenu ──────────────────────────────────────────────────────────────
  function RadialMenu({ x, y, items, titulo = '', onElegir, onCerrar }) {
    const lista = useMemo(() => normalizarItems(items), [items]);
    const n = lista.length;
    const { cx, cy, left, top } = colocar(x, y);
    const [sel, setSel] = useState(null);
    const [pulsado, setPulsado] = useState(false);
    const [abierto, setAbierto] = useState(false);
    const hecho = useRef(false);
    const selRef = useRef(null);
    selRef.current = sel;
    const cb = useRef({ onElegir, onCerrar });
    cb.current = { onElegir, onCerrar };

    const cerrar = () => {
      if (hecho.current) return;
      hecho.current = true;
      if (cb.current.onCerrar) cb.current.onCerrar();
    };
    const elegir = (i) => {
      if (hecho.current || i == null) return;
      const it = lista[i];
      if (!it || it.habilitado === false) return;
      hecho.current = true;
      if (cb.current.onElegir) cb.current.onElegir(it, i);
    };
    const bajo = (e) => indice(Number(e.clientX) - cx, Number(e.clientY) - cy, n);

    useEffect(() => {
      inyectarEstilos();
      const t = setTimeout(() => setAbierto(true), 0);      // de escala .2 a 1 (transición CSS)
      const onKey = (e) => {
        const k = e.key;
        if (k === 'Escape') { e.preventDefault(); cerrar(); return; }
        if (!n) return;
        const s = selRef.current;
        if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'Tab') { e.preventDefault(); setSel(s == null ? 0 : (s + 1) % n); }
        else if (k === 'ArrowLeft' || k === 'ArrowUp') { e.preventDefault(); setSel(s == null ? n - 1 : (s - 1 + n) % n); }
        else if (k === 'Enter' || k === ' ') { e.preventDefault(); if (s != null) elegir(s); }
      };
      const onBlur = () => cerrar();
      window.addEventListener('keydown', onKey, true);
      window.addEventListener('blur', onBlur);
      return () => { clearTimeout(t); window.removeEventListener('keydown', onKey, true); window.removeEventListener('blur', onBlur); };
    }, []);

    return (
      <div className="ln-radial-capa" role="presentation"
        onPointerMove={(e) => setSel(bajo(e))}
        onPointerDown={(e) => { if (e.button === 0) { setPulsado(true); setSel(bajo(e)); } }}
        onPointerUp={(e) => {
          if (e.button !== 0) return;
          setPulsado(false);
          const i = bajo(e);
          if (i == null) cerrar(); else elegir(i);
        }}
        onContextMenu={(e) => { if (e.preventDefault) e.preventDefault(); cerrar(); }}>
        <RadialSvg items={lista} sel={sel} titulo={titulo}
          clase={`ln-radial${abierto ? ' is-abierto' : ''}${pulsado ? ' is-pulsado' : ''}`}
          estilo={{ left, top }} />
      </div>
    );
  }

  // ── RadialHost: lo monta app.jsx ────────────────────────────────────────────
  function centroMascota() {
    try {
      const el = document.querySelector('.ln-mascot-stage');
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) return { x: r.left + r.width / 2, y: r.top + r.height * 0.4 };
      }
    } catch (e) { /* sin DOM */ }
    return { x: (Number(window.innerWidth) || 1280) / 2, y: (Number(window.innerHeight) || 820) / 2 };
  }
  function abrirRadial(x, y, tipo) {
    let px = Number(x), py = Number(y);
    if (x == null || y == null || !isFinite(px) || !isFinite(py)) { const c = centroMascota(); px = c.x; py = c.y; }
    try {
      window.dispatchEvent(new window.CustomEvent('lune-radial', { detail: { x: px, y: py, tipo: tipo || 'principal' } }));
      return true;
    } catch (e) { return false; }
  }

  function RadialHost({ onNavegar, onExpresion, onAviso, mascotaFuera = false }) {
    const [menu, setMenu] = useState(null);                 // {x, y, tipo, items}
    const sonidos = useRef({ sonidos: true, volumen: 0.6 });
    const pedido = useRef(0);
    const props = useRef({});
    props.current = { onNavegar, onExpresion, onAviso, mascotaFuera };
    const aviso = (m) => { if (props.current.onAviso) props.current.onAviso(m); };

    const abrir = useCallback((d) => {
      const tipo = TIPO_PUENTE[d && d.tipo] ? d.tipo : 'principal';
      const x = Number(d && d.x), y = Number(d && d.y);
      const token = ++pedido.current;
      const mostrar = (items) => {
        if (token !== pedido.current) return;              // llegó otro pedido después
        if (!items.length) { aviso('No hay acciones para este menú.'); return; }
        setMenu({ x, y, tipo, items });
        sonar(sonidos.current, 'menu_abrir');
      };
      const ok = llamar('acciones_catalogo', [TIPO_PUENTE[tipo]], (j) => mostrar(normalizarItems(leer(j, []))));
      if (!ok) mostrar(DEMO[tipo]);
    }, []);

    useEffect(() => {
      inyectarEstilos();
      const alAbrir = (e) => abrir((e && e.detail) || {});
      const cargar = () => llamar('radial_estado', [], (j) => {
        const r = leer(j, {});
        const v = Number(r.volumen);
        sonidos.current = { sonidos: r.sonidos !== false, volumen: isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.6 };
      });
      window.addEventListener('lune-radial', alAbrir);
      if (puente()) cargar(); else window.addEventListener('lune-ready', cargar, { once: true });
      return () => { window.removeEventListener('lune-radial', alAbrir); window.removeEventListener('lune-ready', cargar); };
    }, []);

    if (!menu) return null;
    const cerrar = () => { sonar(sonidos.current, 'menu_cerrar'); setMenu(null); };
    const elegir = (it) => {
      const { x, y, tipo } = menu;
      const P = props.current;
      sonar(sonidos.current, 'menu_boton');
      setMenu(null);
      if (it.id === 'expresiones' && tipo !== 'expresiones') { abrir({ x, y, tipo: 'expresiones' }); return; }
      if (it.id === 'expresion' && it.arg && !P.mascotaFuera && P.onExpresion) { P.onExpresion(it.arg); return; }
      if ((it.id === 'ajustes' || it.id === 'chat') && P.onNavegar) { P.onNavegar(it.id === 'ajustes' ? 'settings' : 'chat'); return; }
      const ok = llamar('accion_menu', [it.id, it.arg || ''], (r) => { if (r === false) aviso(`No pude: ${it.etiqueta}`); });
      if (!ok) aviso(`Demo · ${it.etiqueta} (necesita la app)`);
    };
    return <RadialMenu key={pedido.current} x={menu.x} y={menu.y} items={menu.items}
      titulo={menu.tipo === 'expresiones' ? 'Expresiones' : 'Lune'} onElegir={elegir} onCerrar={cerrar} />;
  }

  // ── Enlace con app.jsx ─────────────────────────────────────────────────────
  const FX_A_CFG = { bg: 'fondo', sweep: 'barrido', micro: 'micro' };
  /** {fondo, barrido, micro} de la config → {bg, sweep, micro} de app.jsx (lo que falte, como estaba). */
  function fxDesdeCfg(o, previo) {
    const base = { bg: true, sweep: true, micro: true, ...(previo || {}) };
    if (!o || typeof o !== 'object') return base;
    Object.keys(FX_A_CFG).forEach((k) => { if (typeof o[FX_A_CFG[k]] === 'boolean') base[k] = o[FX_A_CFG[k]]; });
    return base;
  }
  function guardarEfecto(k, v) {
    const clave = FX_A_CFG[k];
    if (!clave) return false;
    return llamar('efectos_guardar', [JSON.stringify({ [clave]: !!v })]);
  }
  function aplicarTema(v) {
    const f = window.luneTema;
    if (typeof f !== 'function') return false;
    const m = leer(v, null);
    try { f(m && typeof m === 'object' && !Array.isArray(m) && Object.keys(m).length ? m : null); return true; } catch (e) { return false; }
  }
  const VISTAS = ['chat', 'settings', 'personajes', 'memoria', 'historial', 'optimizar', 'tools', 'alarmas', 'bailes', 'minecraft'];
  function vistaDe(v) {
    const [vista, seccion] = String(v || '').split('#');
    if (!VISTAS.includes(vista)) return null;
    return { vista, seccion: /^[a-z][a-z0-9_-]{0,23}$/.test(seccion || '') ? seccion : '' };
  }
  function desplazarA(seccion) {
    setTimeout(() => {
      try { const el = document.getElementById('aj-' + seccion); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) { /* sin DOM */ }
    }, 450);
  }
  function conectarApp({ setFx, setModoJuego, setView } = {}) {
    let vivo = true;
    const quitar = [];
    const cablear = () => {
      if (!vivo || !puente()) return;
      llamar('efectos', [], (j) => { const o = leer(j, null); if (vivo && o && setFx) setFx((f) => fxDesdeCfg(o, f)); });
      llamar('tema_estado', [], (j) => { const o = leer(j, null); if (vivo && o) aplicarTema(o.vars); });
      quitar.push(conectar('tema_cambio', (css) => { if (vivo) aplicarTema(css); }));
      const alJuego = (j) => { const o = leer(j, null); if (vivo && o && setModoJuego) setModoJuego(!!o.activo); };
      llamar('juego_estado_json', [], alJuego);
      quitar.push(conectar('juego_estado', alJuego));
      quitar.push(conectar('navegar', (v) => {
        const r = vistaDe(v);
        if (!vivo || !r || !setView) return;
        setView(r.vista);
        if (r.seccion) desplazarA(r.seccion);
      }));
    };
    if (puente()) cablear(); else window.addEventListener('lune-ready', cablear, { once: true });
    return () => { vivo = false; window.removeEventListener('lune-ready', cablear); quitar.splice(0).forEach((f) => f()); };
  }

  // ── Utilidades de las tarjetas ─────────────────────────────────────────────
  /** Llama a fn como mucho una vez cada `ms` (la última petición siempre llega). */
  function crearLimitador(fn, ms) {
    let ultimo = -Infinity, timer = null, pendiente;
    return (arg) => {
      const ahora = Date.now();
      const espera = ms - (ahora - ultimo);
      if (espera <= 0 && !timer) { ultimo = ahora; fn(arg); return; }
      pendiente = arg;
      if (!timer) timer = setTimeout(() => { timer = null; ultimo = Date.now(); fn(pendiente); }, Math.max(0, espera));
    };
  }
  /** Llama a fn `ms` después de la última petición. */
  function crearRetardo(fn, ms) {
    let timer = null;
    return (arg) => { if (timer) clearTimeout(timer); timer = setTimeout(() => { timer = null; fn(arg); }, ms); };
  }
  function useVivo() {
    const vivo = useRef(true);
    useEffect(() => { vivo.current = true; inyectarEstilos(); return () => { vivo.current = false; }; }, []);
    return vivo;
  }
  function Deslizador({ id, label, min, max, step = 1, value, onChange, fmt, hint, clase = '', disabled }) {
    return (
      <div className="lune-field ln-c4-range">
        <div className="ln-c4-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-c4-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} className={clase} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }
  const Estado = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-c4-estado${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);

  // ── Tema ───────────────────────────────────────────────────────────────────
  const PRESETS_DEMO = { cian: 0, magenta_mate: 0.316, violeta: 0.233, rojo_neon: 0.455, ambar: 0.594, verde_acido: 0.816 };
  const NOMBRE_PRESET = { cian: 'Cian', magenta_mate: 'Magenta mate', violeta: 'Violeta', rojo_neon: 'Rojo neón', ambar: 'Ámbar',
    verde_acido: 'Verde ácido', personalizado: 'Personalizado' };
  const HUE_CIAN = 186.1;                                   // tono HSV de --cyan-500 (#00E5FF)
  const TEMA_DEFECTO = { preset: 'cian', hue: 0, saturacion: 1, tenir_pop: false, tenir_fondo: false };
  function normalizarTema(o) {
    const t = { ...TEMA_DEFECTO };
    if (!o || typeof o !== 'object') return t;
    if (typeof o.preset === 'string' && /^[a-z][a-z0-9_]{0,23}$/.test(o.preset)) t.preset = o.preset;
    const h = Number(o.hue); if (isFinite(h)) t.hue = ((h % 360) + 360) % 360;
    const s = Number(o.saturacion); if (isFinite(s)) t.saturacion = Math.min(2, Math.max(0, s));
    t.tenir_pop = o.tenir_pop === true; t.tenir_fondo = o.tenir_fondo === true;
    return t;
  }
  /** Fracción de vuelta (0–1) del tema: la del preset o hue/360 si es personalizado. */
  function tonoDe(t, presets) {
    if (t.preset !== 'personalizado' && presets && presets[t.preset] != null) return Number(presets[t.preset]) || 0;
    return (Number(t.hue) || 0) / 360;
  }
  function colorTono(tono, sat = 1) {
    const h = Math.round(((HUE_CIAN + tono * 360) % 360 + 360) % 360);
    return `hsl(${h} ${Math.round(100 * Math.min(1, Math.max(0, sat)))}% 50%)`;
  }

  function AparienciaCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    const vivo = useVivo();
    const [t, setT] = useState(TEMA_DEFECTO);
    const [presets, setPresets] = useState(PRESETS_DEMO);
    const [msg, setMsg] = useState(null);
    const tocado = useRef(0);                                // último cambio local (ms)
    const conBackend = !!puente();

    const cargar = useCallback(() => llamar('tema_estado', [], (j) => {
      const o = leer(j, null);
      if (!vivo.current || !o) return;
      setT(normalizarTema(o.cfg));
      if (o.presets && typeof o.presets === 'object') setPresets(o.presets);
    }), []);
    const vista = useMemo(() => crearLimitador((cfg) => llamar('tema_previsualizar', [JSON.stringify(cfg)]), 50), []);
    const guardarAhora = useCallback((cfg) => {
      const ok = llamar('tema_guardar', [JSON.stringify(cfg)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        setMsg(r.ok ? { texto: 'Tema guardado.', ok: true } : { texto: r.error || 'No pude guardar el tema.', error: true });
      });
      if (!ok) setMsg({ texto: 'Demo: la vista previa del tema necesita la app.', error: true });
    }, []);
    const guardarPronto = useMemo(() => crearRetardo(guardarAhora, 400), []);

    useEffect(() => {
      cargar();
      // Cambios de fuera (bandeja, panel nativo): se recargan si no estás moviendo nada aquí.
      return conectar('tema_cambio', () => { if (Date.now() - tocado.current > 1500) cargar(); });
    }, []);

    const cambiar = (parcial, inmediato) => {
      const n = normalizarTema({ ...t, ...parcial });
      tocado.current = Date.now();
      setT(n);
      setMsg(null);
      vista(n);
      if (inmediato) guardarAhora(n); else guardarPronto(n);
    };
    const restablecer = () => {
      tocado.current = 0;
      const ok = llamar('tema_restablecer', [], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado && r.estado.cfg) setT(normalizarTema(r.estado.cfg));
        setMsg(r.ok ? { texto: 'Tema de siempre (cian).', ok: true } : { texto: r.error || 'No pude restablecer.', error: true });
      });
      if (!ok) setT(TEMA_DEFECTO);
    };

    const tono = tonoDe(t, presets);
    const nombres = Object.keys(presets);
    const Icono = window.IconMoon || (() => null);
    return (
      <Card id="aj-apariencia" eyebrow={<><Icono width={13} height={13}/> Apariencia · Tema</>} title="Colores de Lune" tone="cyan" tick>
        <p className="ln-c4-nota">
          Gira el tono de los acentos cian y azul en toda la app: esta ventana, la mascota, la burbuja, la bandeja y el menú radial.
          Se aplica al momento{conBackend ? '' : ' (en la app)'}.
        </p>
        <div className="ln-c4-sub">Presets</div>
        <div className="ln-c4-presets">
          {nombres.map((p) => (
            <Button key={p} size="sm" variant={t.preset === p ? 'primary' : 'ghost'}
              onClick={() => cambiar({ preset: p, hue: Math.round(Number(presets[p]) * 3600) / 10 % 360 }, true)}>
              <span className="ln-c4-muestra" style={{ background: colorTono(Number(presets[p]) || 0, t.saturacion) }} />
              {NOMBRE_PRESET[p] || p}
            </Button>
          ))}
          <Button size="sm" variant={t.preset === 'personalizado' ? 'primary' : 'ghost'}
            onClick={() => cambiar({ preset: 'personalizado', hue: Math.round(tono * 3600) / 10 % 360 }, true)}>
            <span className="ln-c4-muestra" style={{ background: colorTono(tono, t.saturacion) }} />Personalizado
          </Button>
        </div>
        <div style={{ height: 14 }} />
        <div className="ln-settings-grid">
          <Deslizador id="f-tema-hue" clase="ln-c4-hue" label="Tono" min={0} max={359} step={1}
            value={Math.round(tono * 360) % 360} fmt={(v) => `${v}°`}
            onChange={(v) => cambiar({ preset: 'personalizado', hue: v })} hint="Mover el tono pasa a «Personalizado»." />
          <Deslizador id="f-tema-sat" label="Saturación" min={0} max={200} step={5}
            value={Math.round(t.saturacion * 100)} fmt={(v) => `${v} %`}
            onChange={(v) => cambiar({ saturacion: v / 100 })} hint="100 % = la de siempre; 0 = gris." />
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-toggle-row">
          <Switch label="Teñir también el amarillo (acentos pop)" checked={t.tenir_pop}
            onChange={(e) => cambiar({ tenir_pop: !!e.target.checked }, true)} accent="yellow" />
          <Switch label="Teñir también los fondos" checked={t.tenir_fondo}
            onChange={(e) => cambiar({ tenir_fondo: !!e.target.checked }, true)} accent="blue" />
        </div>
        <div className="ln-c4-paleta" aria-hidden="true">
          <i style={{ background: 'var(--cyan-500)' }} /><i style={{ background: 'var(--cyan-300)' }} />
          <i style={{ background: 'var(--blue-500)' }} /><i style={{ background: 'var(--blue-300)' }} />
          <i style={{ background: 'var(--yellow-500)' }} /><i style={{ background: 'var(--ink-800)' }} />
        </div>
        <div className="ln-c4-add">
          <Button size="sm" variant="ghost" onClick={restablecer}>Restablecer</Button>
          <Badge variant="ink" outline>{NOMBRE_PRESET[t.preset] || t.preset}</Badge>
        </div>
        <Estado msg={msg} />
      </Card>
    );
  }

  // ── Atajos ─────────────────────────────────────────────────────────────────
  const NOMBRE_ATAJO = {
    mostrar_lune: 'Mostrar Lune', mascota: 'Sacar / guardar la mascota', menu_radial: 'Menú radial',
    comentar: 'Comentar la pantalla', voz: 'Voz sí / no', llamada: 'Modo llamada', fantasma: 'Modo fantasma',
    dormir: 'Dormir / despertar', pantalla_grande: 'Pantalla grande', baile_pausa: 'Pausar el baile',
  };
  const ATAJOS_DEMO = [
    ['mostrar_lune', 'ctrl+alt+shift+l', 'Ctrl+Alt+Shift+L'], ['mascota', 'ctrl+alt+shift+m', 'Ctrl+Alt+Shift+M'],
    ['menu_radial', 'ctrl+alt+shift+space', 'Ctrl+Alt+Shift+Space'], ['comentar', 'ctrl+alt+shift+c', 'Ctrl+Alt+Shift+C'],
    ['voz', 'ctrl+alt+shift+v', 'Ctrl+Alt+Shift+V'],
  ].map(([id, combo, texto]) => ({ id, combo, texto, error: null, aviso: null, disponible: true }));
  const MOD_CODE = /^(Control|Shift|Alt|Meta|OS)(Left|Right)?$|^AltGraph$/;
  const BONITO_MOD = { ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', win: 'Win' };
  function teclaBonita(code) {
    const c = String(code || '');
    let m = /^Key([A-Z])$/.exec(c); if (m) return m[1];
    m = /^Digit(\d)$/.exec(c); if (m) return m[1];
    m = /^Arrow(Up|Down|Left|Right)$/.exec(c); if (m) return m[1];
    m = /^Numpad(.+)$/.exec(c); if (m) return 'Num ' + m[1];
    return c;
  }
  /** keydown → {cancelar} | {completo:false, texto} | {completo:true, combo, texto}.
   *  combo = modificadores + KeyboardEvent.code (lo entiende atajos_globales.parsear_combo). */
  function comboDesdeEvento(e) {
    const code = String((e && e.code) || '');
    const mods = [];
    if (e.ctrlKey) mods.push('ctrl');
    if (e.altKey) mods.push('alt');
    if (e.shiftKey) mods.push('shift');
    if (e.metaKey) mods.push('win');
    const texto = mods.map((m) => BONITO_MOD[m]).join('+');
    if (code === 'Escape' && !mods.length) return { cancelar: true };
    if (!code || MOD_CODE.test(code) || code === 'Unidentified') return { completo: false, texto: texto ? texto + '+…' : '…' };
    return { completo: true, combo: [...mods, code].join('+'), texto: [...mods.map((m) => BONITO_MOD[m]), teclaBonita(code)].join('+') };
  }
  function normalizarAtajos(o) {
    const r = o && typeof o === 'object' ? o : {};
    const lista = (Array.isArray(r.lista) ? r.lista : []).filter((f) => f && ID_OK.test(String(f.id || ''))).map((f) => ({
      id: String(f.id), etiqueta: f.etiqueta ? recortar(f.etiqueta, 60) : (NOMBRE_ATAJO[f.id] || String(f.id)),
      combo: String(f.combo || ''), texto: String(f.texto || f.combo || ''),
      error: f.error ? String(f.error) : null, aviso: f.aviso ? String(f.aviso) : null, disponible: f.disponible !== false,
    }));
    return { lista, activo: r.activo !== false, pausar_en_juegos: r.pausar_en_juegos !== false };
  }

  function AtajosCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    const vivo = useVivo();
    const [est, setEst] = useState(() => normalizarAtajos({ lista: puente() ? [] : ATAJOS_DEMO }));
    const [captura, setCaptura] = useState(null);           // {id, vivo}
    const [msgs, setMsgs] = useState({});                   // id → {texto, error|ok}
    const [msg, setMsg] = useState(null);
    const capturaRef = useRef(null);
    capturaRef.current = captura;

    useEffect(() => {
      llamar('atajos_estado', [], (j) => { if (vivo.current) setEst(normalizarAtajos(leer(j, {}))); });
      return conectar('atajos_cambio', (j) => { if (vivo.current) setEst(normalizarAtajos(leer(j, {}))); });
    }, []);

    const ponerMsg = (id, m) => setMsgs((x) => ({ ...x, [id]: m }));
    const guardar = (id, combo) => {
      const ok = llamar('atajo_validar', [combo], (j) => {
        const v = leer(j, {});
        if (!vivo.current) return;
        if (!v.ok) { ponerMsg(id, { texto: v.error || 'Ese atajo no sirve.', error: true }); return; }
        llamar('atajo_guardar', [id, v.combo || combo], (j2) => {
          const r = leer(j2, {});
          if (!vivo.current) return;
          if (r.estado) setEst(normalizarAtajos(r.estado));
          const aviso = r.aviso || v.aviso;
          ponerMsg(id, r.ok ? { texto: aviso || `Guardado: ${v.texto || combo}`, ok: !aviso, error: !!aviso }
            : { texto: r.error || 'No pude guardar el atajo.', error: true });
        });
      });
      if (!ok) {                                            // demo: solo en la tarjeta
        const c = comboDesdeTexto(combo);
        setEst((e) => ({ ...e, lista: e.lista.map((f) => (f.id === id ? { ...f, combo, texto: c } : f)) }));
        ponerMsg(id, { texto: 'Demo: se guarda en la app.', error: true });
      }
    };
    const quitar = (id) => {                                // "" = sin atajo
      const ok = llamar('atajo_guardar', [id, ''], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado) setEst(normalizarAtajos(r.estado));
        ponerMsg(id, r.ok ? { texto: 'Sin atajo.', ok: true } : { texto: r.error || 'No pude quitarlo.', error: true });
      });
      if (!ok) setEst((e) => ({ ...e, lista: e.lista.map((f) => (f.id === id ? { ...f, combo: '', texto: '' } : f)) }));
    };
    const terminar = (combo, motivo) => {
      const c = capturaRef.current;
      if (!c) return;
      capturaRef.current = null;
      setCaptura(null);
      llamar('atajos_capturando', [false]);
      if (combo) guardar(c.id, combo);
      else if (motivo) ponerMsg(c.id, { texto: motivo, error: true });
    };
    const detectar = (id) => {
      if (capturaRef.current) terminar(null);
      const c = { id, vivo: '' };
      capturaRef.current = c;
      setCaptura(c);
      ponerMsg(id, null);
      llamar('atajos_capturando', [true]);                  // los atajos de Lune se pausan mientras
    };

    useEffect(() => {
      if (!captura) return undefined;
      const onKey = (e) => {
        if (e.preventDefault) e.preventDefault();
        if (e.stopPropagation) e.stopPropagation();
        if (e.repeat) return;
        const r = comboDesdeEvento(e);
        if (r.cancelar) { terminar(null); return; }
        if (!r.completo) { setCaptura((c) => (c ? { ...c, vivo: r.texto } : c)); return; }
        terminar(r.combo);
      };
      const onBlur = () => terminar(null, 'Cancelado: la ventana perdió el foco.');
      const t = setTimeout(() => terminar(null, 'Se acabó el tiempo (15 s).'), 15000);
      window.addEventListener('keydown', onKey, true);
      window.addEventListener('blur', onBlur);
      return () => { clearTimeout(t); window.removeEventListener('keydown', onKey, true); window.removeEventListener('blur', onBlur); };
    }, [captura && captura.id]);
    // Al salir de Ajustes con una captura a medias, los atajos se reanudan.
    useEffect(() => () => { if (capturaRef.current) llamar('atajos_capturando', [false]); }, []);

    const activar = (on) => {
      setEst((e) => ({ ...e, activo: on }));
      llamar('atajos_activar', [on], () => llamar('atajos_estado', [], (j) => { if (vivo.current) setEst(normalizarAtajos(leer(j, {}))); }));
    };
    const restablecer = () => {
      const ok = llamar('atajos_restablecer', [], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado) setEst(normalizarAtajos(r.estado));
        setMsgs({});
        setMsg({ texto: 'Atajos de fábrica (Ctrl+Alt+Shift+…).', ok: true });
      });
      if (!ok) setEst(normalizarAtajos({ lista: ATAJOS_DEMO }));
    };

    const filas = est.lista.filter((f) => f.disponible);
    const Icono = window.IconBolt || (() => null);
    return (
      <Card id="aj-atajos" eyebrow={<><Icono width={13} height={13}/> Escritorio · Teclado</>} title="Atajos globales" tone="blue">
        <p className="ln-c4-nota">
          Funcionan aunque Lune no tenga el foco (RegisterHotKey de Windows, sin leer el teclado). «Detectar» y pulsa la combinación;
          Esc cancela. Mejor con Ctrl+Alt+Shift: en teclados en español Ctrl+Alt es AltGr.
        </p>
        <div className="ln-toggle-row">
          <Switch label="Atajos globales activos" checked={est.activo} onChange={(e) => activar(!!e.target.checked)} accent="blue" />
        </div>
        <div style={{ height: 8 }} />
        {filas.length === 0 && <p className="ln-c4-estado">Cargando atajos…</p>}
        {filas.map((f) => {
          const capt = captura && captura.id === f.id;
          const m = msgs[f.id];
          return (
            <div key={f.id}>
              <div className="ln-c4-fila">
                <span className="ln-c4-fila-nombre">{f.etiqueta}</span>
                <span className={`ln-c4-kbd${capt ? ' is-vivo' : !f.texto ? ' is-vacio' : ''}`} data-atajo={f.id}>
                  {capt ? (captura.vivo || 'Pulsa la combinación…') : (f.texto || 'sin atajo')}
                </span>
                {f.error && !capt && <Badge variant="danger">error</Badge>}
                <Button size="sm" variant={capt ? 'pop' : 'ghost'} onClick={() => (capt ? terminar(null) : detectar(f.id))}>
                  {capt ? 'Cancelar' : 'Detectar'}
                </Button>
                {!capt && f.combo && (
                  <Button size="sm" variant="ghost" title="Dejar sin atajo" aria-label={`Quitar el atajo de ${f.etiqueta}`}
                    onClick={() => quitar(f.id)}>✕</Button>
                )}
              </div>
              {f.error && !m && <p className="ln-c4-estado is-error">{f.error}</p>}
              {f.aviso && !f.error && !m && <p className="ln-c4-estado is-error">{f.aviso}</p>}
              <Estado msg={m} />
            </div>
          );
        })}
        <div className="ln-c4-add">
          <Button size="sm" variant="ghost" onClick={restablecer}>Restablecer</Button>
        </div>
        <Estado msg={msg} />
      </Card>
    );
  }
  function comboDesdeTexto(combo) {
    return String(combo || '').split('+').map((p) => BONITO_MOD[p] || teclaBonita(p)).join('+');
  }

  // ── Listas de acciones (radial y bandeja) ──────────────────────────────────
  const NOMBRE_ACCION_DEMO = {
    ajustes: 'Ajustes', chat: 'Chat', comentar: 'Comentar pantalla', expresiones: 'Expresiones', bailar: 'Bailar',
    alarma: 'Alarma', voz: 'Voz', dormir: 'Dormir', tamano: 'Tamaño', bajar: 'Bajar', mascota: 'Mascota', llamada: 'Llamada',
    pantalla_grande: 'Pantalla grande', temporizador_rapido: 'Temporizador', comida: 'Comida', modo_juego_forzar: 'Modo juego',
    discord: 'Discord', minecraft: 'Reacciones a Minecraft', fantasma: 'Modo fantasma', comer_batido: 'Batido', comer_pastel: 'Pastel',
    guardar_comida: 'Guardar comida', bailes: 'Mis bailes', minecraft_bot: 'Bot de Minecraft',
  };
  function normalizarCatalogo(lista) {
    const out = [], vistos = new Set();
    (Array.isArray(lista) ? lista : []).forEach((a) => {
      const id = a && String(a.id || '');
      if (!ID_OK.test(id) || vistos.has(id)) return;
      vistos.add(id);
      out.push({ id, etiqueta: recortar(a.etiqueta || id, 40), icono: String(a.icono || '') });
    });
    return out;
  }
  const catalogoDemo = (ids) => ids.map((id) => ({ id, etiqueta: NOMBRE_ACCION_DEMO[id] || id, icono: '' }));
  const soloIds = (l) => (Array.isArray(l) ? l.filter((i) => ID_OK.test(String(i))).map(String) : []);
  /** Mueve el elemento i en `d` posiciones (−1 arriba, +1 abajo); sin salirse. */
  function mover(lista, i, d) {
    const j = i + d;
    if (i < 0 || j < 0 || i >= lista.length || j >= lista.length) return lista.slice();
    const out = lista.slice();
    [out[i], out[j]] = [out[j], out[i]];
    return out;
  }

  function ListaAcciones({ ids, catalogo, max, prefijo, onCambio }) {
    const { Button } = window.LUNE;
    const [nuevo, setNuevo] = useState('');
    const nombre = (id) => { const a = catalogo.find((x) => x.id === id); return a ? a.etiqueta : (NOMBRE_ACCION_DEMO[id] || id); };
    const libres = catalogo.filter((a) => !ids.includes(a.id));
    const lleno = ids.length >= max;
    const elegido = libres.some((a) => a.id === nuevo) ? nuevo : (libres[0] ? libres[0].id : '');
    return (
      <div>
        {ids.length === 0 && <p className="ln-c4-estado">Sin acciones.</p>}
        {ids.map((id, i) => (
          <div className="ln-c4-fila" key={id}>
            <span className="ln-c4-num">{i + 1}</span>
            <span className="ln-c4-fila-nombre">{nombre(id)}</span>
            <Button size="sm" variant="ghost" title="Subir" aria-label={`Subir ${nombre(id)}`} disabled={i === 0}
              onClick={() => onCambio(mover(ids, i, -1))}>↑</Button>
            <Button size="sm" variant="ghost" title="Bajar" aria-label={`Bajar ${nombre(id)}`} disabled={i === ids.length - 1}
              onClick={() => onCambio(mover(ids, i, 1))}>↓</Button>
            <Button size="sm" variant="ghost" title="Quitar" aria-label={`Quitar ${nombre(id)}`}
              onClick={() => onCambio(ids.filter((x) => x !== id))}>✕</Button>
          </div>
        ))}
        <div className="ln-c4-add">
          <select id={`${prefijo}-nuevo`} className="lune-input ln-select" value={elegido} disabled={lleno || !libres.length}
            onChange={(e) => setNuevo(e.target.value)} aria-label="Acción para añadir">
            {!libres.length && <option value="">(no quedan acciones)</option>}
            {libres.map((a) => <option key={a.id} value={a.id}>{a.etiqueta}</option>)}
          </select>
          <Button size="sm" variant="secondary" disabled={lleno || !elegido} onClick={() => { if (elegido) onCambio([...ids, elegido]); }}>
            {lleno ? `Máximo ${max}` : 'Añadir'}
          </Button>
        </div>
      </div>
    );
  }

  // ── Menú radial ────────────────────────────────────────────────────────────
  function normalizarRadial(o) {
    const r = o && typeof o === 'object' ? o : {};
    const max = Math.min(MAX_BOTONES, Math.max(1, Math.floor(Number(r.max) || MAX_BOTONES)));
    const v = Number(r.volumen);
    return {
      principal: soloIds(r.principal).slice(0, max), secundario: soloIds(r.secundario).slice(0, max),
      defecto: soloIds(r.defecto), catalogo: normalizarCatalogo(r.catalogo), max,
      sonidos: r.sonidos !== false, volumen: isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.6,
    };
  }
  const RADIAL_DEMO = {
    principal: ['ajustes', 'chat', 'comentar', 'expresiones', 'voz', 'dormir'],
    defecto: ['ajustes', 'chat', 'comentar', 'expresiones', 'voz', 'dormir'],
    catalogo: catalogoDemo(['ajustes', 'chat', 'comentar', 'expresiones', 'bailar', 'alarma', 'voz', 'dormir', 'tamano', 'bajar', 'fantasma', 'llamada']),
  };

  function MenuRadialCard() {
    const { Card, Button, Switch } = window.LUNE;
    const vivo = useVivo();
    const [est, setEst] = useState(() => normalizarRadial(puente() ? {} : RADIAL_DEMO));
    const [msg, setMsg] = useState(null);
    const guardarVol = useMemo(() => crearRetardo((v) => guardar({ volumen: v }), 350), []);

    useEffect(() => { llamar('radial_estado', [], (j) => { if (vivo.current) setEst(normalizarRadial(leer(j, {}))); }); }, []);

    function guardar(parcial) {
      setEst((e) => ({ ...e, ...parcial }));
      const ok = llamar('radial_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado) setEst(normalizarRadial(r.estado));
        const desc = Array.isArray(r.descartados) && r.descartados.length ? ` (descartados: ${r.descartados.join(', ')})` : '';
        setMsg(r.ok ? { texto: 'Guardado.' + desc, ok: !desc, error: !!desc } : { texto: r.error || 'No pude guardar.', error: true });
      });
      if (!ok) setMsg({ texto: 'Demo: se guarda en la app.', error: true });
    }

    const nombres = new Map(est.catalogo.map((a) => [a.id, a]));
    const itemsVista = est.principal.map((id) => ({ id, etiqueta: (nombres.get(id) || {}).etiqueta || NOMBRE_ACCION_DEMO[id] || id,
      icono: (nombres.get(id) || {}).icono || '', arg: '', habilitado: true }));
    const catalogo = est.catalogo.length ? est.catalogo : catalogoDemo(est.principal);
    const Icono = window.IconGear || (() => null);
    return (
      <Card id="aj-radial" eyebrow={<><Icono width={13} height={13}/> Escritorio · Mascota</>} title="Menú radial" tone="cyan">
        <p className="ln-c4-nota">
          Clic derecho sobre la mascota (o F1 aquí, o su atajo) abre este menú. Mueve el ratón hacia un botón y haz clic; en el
          centro, Esc o clic derecho se cierra. Hasta {est.max} botones, en orden horario desde arriba.
        </p>
        <div className="ln-c4-grid">
          <ListaAcciones ids={est.principal} catalogo={catalogo} max={est.max} prefijo="f-radial"
            onCambio={(ids) => guardar({ principal: ids.slice(0, est.max) })} />
          <RadialSvg items={itemsVista} clase="ln-c4-preview" tamano={184} titulo="Vista previa" />
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-settings-grid">
          <div className="ln-toggle-row">
            <Switch label="Sonidos del menú" checked={est.sonidos} onChange={(e) => guardar({ sonidos: !!e.target.checked })} />
          </div>
          <Deslizador id="f-radial-vol" label="Volumen" min={0} max={100} step={5} value={Math.round(est.volumen * 100)}
            fmt={(v) => `${v} %`} disabled={!est.sonidos}
            onChange={(v) => { setEst((e) => ({ ...e, volumen: v / 100 })); guardarVol(v / 100); }} />
        </div>
        <div className="ln-c4-add">
          <Button size="sm" variant="secondary" onClick={() => abrirRadial()}>Probar</Button>
          <Button size="sm" variant="ghost" disabled={!est.defecto.length} onClick={() => guardar({ principal: est.defecto.slice(0, est.max) })}>Restablecer</Button>
        </div>
        <Estado msg={msg} />
      </Card>
    );
  }

  // ── Bandeja ────────────────────────────────────────────────────────────────
  function normalizarBandeja(o) {
    const r = o && typeof o === 'object' ? o : {};
    const max = Math.min(30, Math.max(1, Math.floor(Number(r.max) || 20)));
    return { acciones: soloIds(r.acciones).slice(0, max), defecto: soloIds(r.defecto), catalogo: normalizarCatalogo(r.catalogo), max };
  }
  const BANDEJA_DEMO = {
    acciones: ['mascota', 'comentar', 'voz', 'llamada', 'dormir'],
    defecto: ['mascota', 'comentar', 'voz', 'llamada', 'dormir'],
    catalogo: catalogoDemo(['mascota', 'comentar', 'voz', 'llamada', 'dormir', 'fantasma', 'modo_juego_forzar', 'bailar']),
  };

  function BandejaCard() {
    const { Card, Button } = window.LUNE;
    const vivo = useVivo();
    const [est, setEst] = useState(() => normalizarBandeja(puente() ? {} : BANDEJA_DEMO));
    const [msg, setMsg] = useState(null);
    useEffect(() => { llamar('bandeja_estado', [], (j) => { if (vivo.current) setEst(normalizarBandeja(leer(j, {}))); }); }, []);
    const guardar = (ids) => {
      setEst((e) => ({ ...e, acciones: ids }));
      const ok = llamar('bandeja_guardar', [JSON.stringify({ acciones: ids })], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado) setEst(normalizarBandeja(r.estado));
        setMsg(r.ok ? { texto: 'Guardado: el menú de la bandeja se rehace al abrirlo.', ok: true } : { texto: r.error || 'No pude guardar.', error: true });
      });
      if (!ok) setMsg({ texto: 'Demo: se guarda en la app.', error: true });
    };
    const catalogo = est.catalogo.length ? est.catalogo : catalogoDemo(est.acciones);
    const Icono = window.IconBolt || (() => null);
    return (
      <Card id="aj-bandeja" eyebrow={<><Icono width={13} height={13}/> Escritorio · Bandeja</>} title="Menú de la bandeja" tone="blue">
        <p className="ln-c4-nota">
          Acciones rápidas del submenú «Lune» del icono de la bandeja (junto al reloj). Las que aún no tienen función no salen.
        </p>
        <ListaAcciones ids={est.acciones} catalogo={catalogo} max={est.max} prefijo="f-bandeja" onCambio={guardar} />
        <div className="ln-c4-add">
          <Button size="sm" variant="ghost" disabled={!est.defecto.length} onClick={() => guardar(est.defecto.slice(0, est.max))}>Restablecer</Button>
        </div>
        <Estado msg={msg} />
      </Card>
    );
  }

  Object.assign(window, {
    AparienciaCard,
    AtajosCard,
    MenuRadialCard,
    BandejaCard,
    RadialMenu,
    RadialHost,
    LuneRadial: {
      LIENZO, CENTRO, ZONA_MUERTA, RADIO_ICONOS, RADIO_EXTERIOR, MAX_BOTONES,
      indice, posiciones, factorLerp, sector, colocar, normalizarItems, trazosIcono, abrir: abrirRadial, DEMO,
    },
    LuneApariencia: {
      conectarApp, guardarEfecto, aplicarTema, fxDesdeCfg, vistaDe, crearLimitador, crearRetardo, normalizarTema,
      tonoDe, colorTono, comboDesdeEvento, teclaBonita, normalizarAtajos, normalizarRadial, normalizarBandeja, mover,
      PRESETS_DEMO, HUE_CIAN,
    },
  });
})();
