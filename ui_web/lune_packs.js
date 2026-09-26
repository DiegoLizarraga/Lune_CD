/*
 * ui_web/lune_packs.js — packs de sonidos de reacción de la mascota (window.luneSonidos).
 *
 * Para qué sirve: la mascota (VRM y animada) suena por EVENTOS («arrastre_inicio»,
 * «caricia», «beber», «tecleo»…) y no por archivos. Un pack de sonidos (carpeta de
 * sonidos/ con pack.json, ver nucleo/packs_sonido.py) dice qué clips tiene cada
 * evento; este script elige uno al azar y lo toca con window.luneSfx (lune_sfx.js,
 * que tiene que cargarse antes).
 *
 * Reglas (las de los voice packs de Mate-Engine):
 *   - arrastre_inicio / arrastre_fin: tono al azar entre 0.9 y 1.1;
 *   - eventos de REACCIÓN (caricia, pudor, mareo, despertar, dormir, saludo): su clip
 *     es la «voz» de la mascota y solo suena si no está sonando otra voz de reacción
 *     ni la voz TTS (hablando(true)); las CAPAS del evento suenan siempre;
 *   - tecleo: mientras la burbuja escribe, un blip cada 2 letras, tono 0.95–1.05,
 *     como mucho uno cada 35 ms y nunca con la voz TTS sonando. La envolvente del
 *     blip (blip.wav, ~30 ms) ya hace el fundido: no se corta en seco.
 *
 * Sin pack cargado se usa DEFECTO, espejo de sonidos/default/pack.json (los WAV de
 * assets/sfx/ que genera scripts/generar_sfx.py; tests/js/packs.test.mjs comprueba
 * que coinciden). Un pack que no trae un evento sigue con el de DEFECTO; si lo trae,
 * mapeo «reemplazar» usa solo los suyos y «ciclo» los repite hasta el tamaño del
 * de DEFECTO: out[i] = nuevos[i % n].
 *
 * API:
 *   luneSonidos.cargar(fuente, {base}) → Promise<bool>
 *        fuente = URL de un pack.json (sus archivos se buscan junto a él) u objeto
 *        ya resuelto por Python (packs_sonido.pack_para_web). false (y se queda el
 *        pack anterior) si no se puede leer, no trae nada válido o su "base" no está
 *        permitida. Solo .ogg/.wav, sin esquemas (http:, data:…), «..» ni «\».
 *   luneSonidos.tocar(evento, {vol}) → Promise<{voz, capa} | null>
 *   luneSonidos.setVolumen(v 0..1) · getVolumen()   volumen propio (× el del pack)
 *   luneSonidos.hablando(on)        la voz TTS suena: calla la voz de reacción y el tecleo
 *   luneSonidos.tecleo(on)          blips siguiendo el texto de #btxt (MutationObserver;
 *                                   sin él, sondeo cada 40 ms)
 *   luneSonidos.letras(n)           avisar a mano de n letras escritas (→ blips sonados)
 *   luneSonidos.clips(evento, capas) → [urls]   (p. ej. la alarma en bucle con luneSfx)
 *   luneSonidos.pack() · eventos() · defecto() · reiniciar()
 *   luneSonidos.aleatorio / luneSonidos.ahora   inyectables (tests)
 *
 * Script clásico: <script src="lune_sfx.js"></script><script src="lune_packs.js"></script>.
 * Nunca lanza: sin luneSfx o sin WebAudio, tocar() devuelve null.
 */
(function (w) {
  'use strict';

  if (w.luneSonidos && w.luneSonidos.__lune) return;   // ya cargado: conservar estado

  var RE_EVENTO = /^[a-z0-9_]{1,40}$/;
  var RE_EXT = /\.(ogg|wav)$/i;
  var MAX_ARCHIVOS = 32;
  var MAX_REF = 300;
  var PITCH = { arrastre_inicio: [0.9, 1.1], arrastre_fin: [0.9, 1.1] };
  var PITCH_TECLEO = [0.95, 1.05];
  var REACCIONES = { caricia: 1, pudor: 1, mareo: 1, despertar: 1, dormir: 1, saludo: 1 };
  var BASES = { 'ui_web/assets/sfx': null };   // null = la base de luneSfx (assets/sfx/)
  var VOZ_DURACION_DEFECTO_S = 1;
  var LETRAS_POR_BLIP = 2;
  var MIN_BLIP_MS = 35;
  var VOL_TECLEO = 0.6;
  var SONDEO_TECLEO_MS = 40;

  // Espejo de sonidos/default/pack.json (nombres relativos a assets/sfx/).
  var DEFECTO = {
    id: 'default',
    nombre: 'Lune (por defecto)',
    autor: 'Lune CD',
    mapeo: 'ciclo',
    volumen: 1,
    eventos: {
      arrastre_inicio: ['drag_start.wav'],
      arrastre_fin: ['drag_stop.wav'],
      caricia: [],
      pudor: [],
      mareo: [],
      despertar: [],
      dormir: [],
      saludo: [],
      burbuja_abrir: [],
      burbuja_cerrar: [],
      tecleo: ['blip.wav'],
      alarma: ['alarma_1.wav', 'alarma_2.wav', 'alarma_3.wav'],
      comida_aparece: ['comida_aparece.wav'],
      comida_capa: ['comida_capa_1.wav', 'comida_capa_2.wav'],
      beber: ['trago_1.wav', 'trago_2.wav', 'trago_3.wav'],
      comer: ['mordisco_1.wav', 'mordisco_2.wav', 'mordisco_3.wav'],
      menu_abrir: ['menu_abrir.wav'],
      menu_cerrar: ['menu_cerrar.wav'],
      menu_boton: ['menu_boton.wav'],
      menu_interruptor: ['menu_boton.wav'],
    },
    capas: {},
  };

  var volumen = 1;
  var pack = null;                 // {id, nombre, autor, mapeo, volumen, eventos, capas}
  var hablandoTTS = false;
  var vozHasta = 0, vozPendiente = false;
  var tecleoOn = false, acumulado = 0, ultimoBlip = -1e12, largoBtxt = 0;
  var observador = null, sondeo = null;

  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function num(v, defecto) { var n = Number(v); return Number.isFinite(n) ? n : defecto; }

  function ahora() {
    var f = api.ahora;
    if (typeof f === 'function') { try { return Number(f()) || 0; } catch (e) { /* reloj roto */ } }
    return Date.now();
  }

  function elegir(lista) {
    var azar = typeof api.aleatorio === 'function' ? api.aleatorio : Math.random;
    var i = Math.floor(num(azar(), 0) * lista.length);
    return lista[clamp(i, 0, lista.length - 1)];
  }

  function sfx() {
    var s = w.luneSfx;
    return s && typeof s.tocar === 'function' ? s : null;
  }

  function avisar(msg, extra) {
    try { if (w.console && w.console.warn) w.console.warn('[luneSonidos] ' + msg, extra || ''); } catch (e) { /* sin consola */ }
  }

  function copiaTabla(t) {
    var out = {};
    Object.keys(t || {}).forEach(function (k) { out[k] = t[k].slice(); });
    return out;
  }

  // ── Validación de rutas ─────────────────────────────────────────────────────
  function segmentoMalo(s) {
    var d;
    try { d = decodeURIComponent(s); } catch (e) { return true; }
    return d === '' || d === '.' || d === '..' || /[\\/:]/.test(d) || /[\u0000-\u001f]/.test(d);
  }

  // Devuelve la URL (o el nombre relativo a luneSfx) o null si no es segura.
  function refSegura(ref, base) {
    if (typeof ref !== 'string') return null;
    var r = ref.trim();
    if (!r || r.length > MAX_REF || !RE_EXT.test(r)) return null;      // sin ?query ni #hash
    if (/[\\\u0000-\u001f]/.test(r)) return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(r) || r.indexOf('//') === 0) return null;   // esquema o //host
    var raiz = r.charAt(0) === '/';
    var segs = (raiz ? r.slice(1) : r).split('/');
    if (segs.some(segmentoMalo)) return null;
    if (raiz || base === null) return r;          // raíz del mismo origen o relativo a assets/sfx/
    var u;
    try { u = new URL(r, base).href; } catch (e) { return null; }
    return u.indexOf(base) === 0 ? u : null;       // nunca fuera de la carpeta del pack
  }

  function normalizarTabla(t, base) {
    var out = {};
    if (!t || typeof t !== 'object' || Array.isArray(t)) return out;
    Object.keys(t).forEach(function (ev) {
      if (!RE_EVENTO.test(ev)) return;
      var lista = typeof t[ev] === 'string' ? [t[ev]] : t[ev];
      if (!Array.isArray(lista)) return;
      var ok = [];
      lista.slice(0, MAX_ARCHIVOS).forEach(function (ref) {
        var u = refSegura(ref, base);
        if (u) ok.push(u);
      });
      out[ev] = ok;
    });
    return out;
  }

  function mapear(defecto, nuevo, mapeo) {
    var out = {};
    var claves = {};
    Object.keys(defecto).forEach(function (k) { claves[k] = 1; });
    Object.keys(nuevo).forEach(function (k) { claves[k] = 1; });
    Object.keys(claves).forEach(function (ev) {
      var n = nuevo[ev] || [], d = defecto[ev] || [];
      if (!n.length) { out[ev] = d.slice(); return; }
      if (mapeo === 'reemplazar') { out[ev] = n.slice(); return; }
      var total = Math.max(d.length, n.length), l = [];
      for (var i = 0; i < total; i++) l.push(n[i % n.length]);
      out[ev] = l;
    });
    return out;
  }

  function contar(t) {
    return Object.keys(t).reduce(function (s, k) { return s + t[k].length; }, 0);
  }

  function baseDocumento() {
    try {
      if (w.document && w.document.baseURI) return String(w.document.baseURI);
      if (w.location && w.location.href) return String(w.location.href);
    } catch (e) { /* sin documento */ }
    return null;
  }

  // Carpeta de los archivos de un pack: la de su pack.json, o la base permitida.
  // undefined = base no permitida (el pack se rechaza).
  function baseArchivos(j, urlPack, baseOpcion) {
    if (typeof j.base === 'string' && j.base) {
      return Object.prototype.hasOwnProperty.call(BASES, j.base) ? BASES[j.base] : undefined;
    }
    if (j.base != null && j.base !== '') return undefined;
    var ref = baseOpcion || urlPack;
    if (!ref) return null;
    try { return new URL('./', ref).href; } catch (e) { return null; }
  }

  function aplicar(j, urlPack, baseOpcion) {
    if (!j || typeof j !== 'object' || Array.isArray(j)) return false;
    var base = baseArchivos(j, urlPack, baseOpcion);
    if (base === undefined) { avisar('base no permitida', j.base); return false; }
    var ev = normalizarTabla(j.eventos, base);
    var cp = normalizarTabla(j.capas, base);
    if (!contar(ev) && !contar(cp)) { avisar('el pack no trae ningún .ogg/.wav válido', j.nombre || urlPack || ''); return false; }
    var mapeo = j.mapeo === 'reemplazar' ? 'reemplazar' : 'ciclo';
    pack = {
      id: typeof j.id === 'string' ? j.id : '',
      nombre: typeof j.nombre === 'string' ? j.nombre.slice(0, 60) : '',
      autor: typeof j.autor === 'string' ? j.autor.slice(0, 60) : '',
      mapeo: mapeo,
      volumen: clamp(num(j.volumen, 1), 0, 1),
      eventos: mapear(DEFECTO.eventos, ev, mapeo),
      capas: mapear(DEFECTO.capas, cp, mapeo),
    };
    return true;
  }

  function cargar(fuente, opciones) {
    var o = opciones || {};
    if (fuente && typeof fuente === 'object') {
      try { return Promise.resolve(aplicar(fuente, null, o.base || null)); } catch (e) { return Promise.resolve(false); }
    }
    if (typeof fuente !== 'string' || !fuente.trim() || typeof w.fetch !== 'function') return Promise.resolve(false);
    var urlPack = fuente.trim();
    try { urlPack = new URL(urlPack, baseDocumento() || undefined).href; } catch (e) { /* se queda relativa */ }
    return w.fetch(urlPack)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) { return aplicar(j, urlPack, o.base || null); })
      .catch(function (e) {
        avisar('no se pudo cargar el pack', urlPack + ' ' + String((e && e.message) || e));
        return false;
      });
  }

  function tabla() { return pack || DEFECTO; }
  function volumenEfectivo() { return volumen * tabla().volumen; }

  // ── Reproducción ────────────────────────────────────────────────────────────
  function vozOcupada() { return vozPendiente || ahora() < vozHasta; }

  function tocarVoz(s, clip, vol) {
    vozPendiente = true;
    var carga;
    try { carga = typeof s.cargar === 'function' ? s.cargar(clip) : null; } catch (e) { carga = null; }
    return Promise.resolve(carga)
      .then(function (buf) {
        var dur = buf && num(buf.duration, 0) > 0 ? num(buf.duration, 0) : VOZ_DURACION_DEFECTO_S;
        return Promise.resolve(s.tocar(clip, { vol: vol, canal: 'pack_voz' })).then(function (h) {
          vozPendiente = false;
          if (h && !hablandoTTS) vozHasta = ahora() + dur * 1000;
          else if (h && hablandoTTS && typeof h.detener === 'function') { h.detener(); h = null; }
          return h || null;
        });
      })
      .catch(function () { vozPendiente = false; return null; });
  }

  function tocar(evento, opciones) {
    var s = sfx();
    if (!s) return Promise.resolve(null);
    var ev = String(evento == null ? '' : evento);
    var t = tabla();
    var clips = t.eventos[ev] || [], capas = t.capas[ev] || [];
    if (!clips.length && !capas.length) return Promise.resolve(null);
    var o = opciones || {};
    var vol = volumenEfectivo() * (o.vol == null ? 1 : clamp(num(o.vol, 1), 0, 2));
    if (!(vol > 0)) return Promise.resolve(null);
    var pitch = PITCH[ev] || 1;
    var pVoz = null, pCapa = null;
    try {
      if (clips.length) {
        if (REACCIONES[ev]) {
          if (!hablandoTTS && !vozOcupada()) pVoz = tocarVoz(s, elegir(clips), vol);
        } else {
          pVoz = s.tocar(elegir(clips), { vol: vol, pitch: pitch, canal: 'pack' });
        }
      }
      if (capas.length) pCapa = s.tocar(elegir(capas), { vol: vol, pitch: pitch, canal: 'pack_capa' });
    } catch (e) {
      return Promise.resolve(null);
    }
    return Promise.all([pVoz, pCapa])
      .then(function (r) { return { voz: r[0] || null, capa: r[1] || null }; })
      .catch(function () { return null; });
  }

  function setVolumen(v) {
    var n = Number(v);
    if (Number.isFinite(n)) volumen = clamp(n, 0, 1);
    return volumen;
  }

  function hablando(on) {
    hablandoTTS = !!on;
    if (hablandoTTS) {
      vozHasta = 0;
      var s = sfx();
      if (s && typeof s.detenerCanal === 'function') {
        try { s.detenerCanal('pack_voz'); s.detenerCanal('tecleo'); } catch (e) { /* sin audio */ }
      }
    }
    return hablandoTTS;
  }

  // ── Tecleo ──────────────────────────────────────────────────────────────────
  function blip() {
    var t = ahora();
    if (hablandoTTS || t - ultimoBlip < MIN_BLIP_MS) return false;
    var s = sfx();
    var clips = tabla().eventos.tecleo || [];
    var vol = volumenEfectivo() * VOL_TECLEO;
    if (!s || !clips.length || !(vol > 0)) return false;
    ultimoBlip = t;
    try { s.tocar(elegir(clips), { vol: vol, pitch: PITCH_TECLEO, canal: 'tecleo' }); } catch (e) { return false; }
    return true;
  }

  // Un trozo grande de golpe (streaming) da UN blip, no una ráfaga.
  function letras(n) {
    var k = Math.floor(Number(n));
    if (!(k > 0)) return 0;
    acumulado += k;
    if (acumulado < LETRAS_POR_BLIP) return 0;
    acumulado = acumulado % LETRAS_POR_BLIP;
    return blip() ? 1 : 0;
  }

  function btxt() {
    try {
      var d = w.document;
      return d && typeof d.getElementById === 'function' ? d.getElementById('btxt') : null;
    } catch (e) { return null; }
  }

  function largo(el) { return el ? Array.from(String(el.textContent || '')).length : 0; }

  function revisar() {
    var n = largo(btxt());
    if (n > largoBtxt) letras(n - largoBtxt);
    else if (n < largoBtxt) acumulado = 0;           // texto nuevo: se empieza a contar de cero
    largoBtxt = n;
  }

  function dejarDeObservar() {
    if (observador) { try { observador.disconnect(); } catch (e) { /* ya suelto */ } observador = null; }
    if (sondeo !== null) { try { w.clearInterval(sondeo); } catch (e) { /* sin timers */ } sondeo = null; }
  }

  function observar() {
    dejarDeObservar();
    var el = btxt();
    largoBtxt = largo(el);
    acumulado = 0;
    if (el && typeof w.MutationObserver === 'function') {
      try {
        observador = new w.MutationObserver(revisar);
        observador.observe(el, { childList: true, characterData: true, subtree: true });
        return;
      } catch (e) { observador = null; }
    }
    // Sin #btxt todavía o sin MutationObserver: sondeo barato mientras dure el tecleo.
    if (typeof w.setInterval === 'function') sondeo = w.setInterval(revisar, SONDEO_TECLEO_MS);
  }

  function tecleo(on) {
    on = !!on;
    if (on === tecleoOn) return tecleoOn;
    tecleoOn = on;
    if (on) observar(); else dejarDeObservar();
    return tecleoOn;
  }

  // ── Consultas ───────────────────────────────────────────────────────────────
  function clips(evento, deCapas) {
    var t = tabla();
    return ((deCapas ? t.capas : t.eventos)[String(evento)] || []).slice();
  }

  var api = {
    __lune: true,
    cargar: cargar,
    tocar: tocar,
    setVolumen: setVolumen,
    getVolumen: function () { return volumen; },
    hablando: hablando,
    tecleo: tecleo,
    letras: letras,
    clips: clips,
    pack: function () {
      var t = tabla();
      return { id: t.id, nombre: t.nombre, autor: t.autor, mapeo: t.mapeo, volumen: t.volumen };
    },
    eventos: function () { return Object.keys(tabla().eventos).sort(); },
    defecto: function () { return { eventos: copiaTabla(DEFECTO.eventos), capas: copiaTabla(DEFECTO.capas) }; },
    reiniciar: function () { pack = null; vozHasta = 0; return true; },
    aleatorio: Math.random,
    ahora: null,
  };

  w.luneSonidos = api;
})(typeof window !== 'undefined' ? window : globalThis);
