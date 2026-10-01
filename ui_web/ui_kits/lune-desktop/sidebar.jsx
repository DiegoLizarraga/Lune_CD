/* Lune CD desktop — Sidebar (v10)
 *
 * Escenario de la asistente (AsistenteStage):
 *   · Por defecto, el vídeo del estado (assets/asistente/anime-videos/lune-<estado>.webm) o su PNG.
 *   · Con la asistente en VRM (Ajustes → Asistente en escritorio → VRM 3D) y un .vrm publicado por ui/web_shell.py
 *     en /vrm/actual.vrm, el avatar 3D de vrm_barra.js (window.LuneVRMBarra) sobre un <canvas>.
 *     Si el módulo carga tarde se espera su evento 'lune-vrm-barra'; si falla WebGL o el modelo,
 *     o deja de haber modelo, se vuelve al vídeo. El cambio de personaje o de modelo lo avisa
 *     web_shell con el evento 'lune-vrm-modelo' (y ya recarga los avatares vivos).
 *   · Lune fuera (asistente en escritorio): la barra no la dibuja dos veces. El vídeo se desmonta y el
 *     avatar 3D se pausa (FPS 0 y contexto WebGL liberado) y se oculta bajo el aviso.
 *   · Modo juego (corte 4): el avatar 3D y el vídeo se pausan mientras hay un juego delante.
 *   · Lune en reposo (11.2, ui_web/lune_reposo.js → `quieta`): el vídeo se pausa y el avatar 3D baja a 0 fps
 *     SIN soltar su contexto WebGL (h.reposar), así al volver sigue al momento donde estaba.
 *   · Clic derecho sobre la asistente → menú radial SVG (window.LuneRadial, extra/apariencia.jsx).
 *   · Baile (cortes 5/6): app.jsx pasa `baile` = window.LuneBaileWeb.useBaile() (extra/baile.jsx). En VRM, el
 *     módulo baileProc (ui_web/vrm/lune_baile_proc.js) se registra en el avatar de la barra (h.usarModulo) y
 *     recibe bailar(on, opts) y cada pulso; en vídeo, un transform por rAF a ≤ 30 fps, solo mientras baila y
 *     no está en pausa (Lune fuera o modo juego). Encima, el rótulo «♪ Spotify · 124 BPM».
 *   · Comida (cortes 7/8): clic central (soltado) sobre la asistente → menú radial «secundario» (Batido, Pastel,
 *     Guardar), como la flotante. `window.__luneCabezaBarra()` → {x, y, r} en px de la ventana (o null): la
 *     cabeza de Lune para el acierto de ComidaWeb (extra/vida.jsx). En VRM, el hueso de la cabeza (+0.1 m, como
 *     Mate-Engine) proyectado, r = 0.22·ancho; en vídeo, la misma fórmula que companion.html (luneCabeza) con el
 *     encuadre de la barra (object-fit: cover, abajo al centro). Solo la registra el escenario a la vista.
 *
 * Tareas (10.9): la entrada «Tareas» (TareasAcceso), siempre a la vista, con las pendientes de hoy (Mi día) y el
 * total, de window.luneTareas (ui/puente_tareas.py: estado() y la señal cambio, así se actualiza sola cuando Lune
 * anota algo desde el chat). Abre la vista «tareas» (extra/tareas.jsx) con `onTareas` o, sin él, con el evento de
 * window 'lune-vista'. Sin el objeto (navegador, backend viejo) queda como un acceso sin número.
 */

// PNG estático (respaldo si el video de un estado aún no existe).
const ASISTENTE = {
  normal:   '../../assets/asistente/anime/lune-composed.png',
  happy:    '../../assets/asistente/anime/lune-happy.png',
  reading:  '../../assets/asistente/anime/lune-thinking.png',
  thinking: '../../assets/asistente/anime/lune-thinking.png',
  typing:   '../../assets/asistente/anime/lune-composed.png',
  error:    '../../assets/asistente/anime/lune-nervous.png',
  angry:    '../../assets/asistente/anime/lune-angry.png',
  surprised:'../../assets/asistente/anime/lune-surprised.png',
  nervous:  '../../assets/asistente/anime/lune-nervous.png',
  wave:     '../../assets/asistente/anime/lune-happy.png',
};

// Estado → nombre base del video (assets/asistente/anime-videos/lune-<base>.webm).
// Si el clip no existe todavía, cae al idle "composed" y, si tampoco, al PNG.
// v10 — un estado por clip. Los que aún no tienen video caen al idle hasta que
// exista `lune-<estado>.webm` (ver scripts/convertir_asistente.py).
const VID = {
  normal:'composed', thinking:'thinking', happy:'happy', angry:'angry', error:'angry',
  surprised:'surprised', nervous:'nervous', wave:'wave', dismiss:'dismiss',
  sad:'sad', curious:'curious', reading:'curious',
  typing:'working', listening:'listening', talking:'talking',
  laughing:'laughing', bored:'bored',
};
const VID_DIR = '../../assets/asistente/anime-videos/';
const VID_IDLE = VID_DIR + 'lune-composed.webm';

const FPS_BAILE_VIDEO = 30;

// ── Cabeza de la asistente de la barra (comida de la web, cortes 7/8) ──────────
const ALTO_CABEZA_M = 0.1;       // el acierto de Mate-Engine: cabeza + (0, 0.1, 0)
const ALTOS_POR_METRO = 1.29;    // clips 720×1280 (companion.html, luneCabeza)
const RADIO_CABEZA_M = 0.1732;   // 0.1·|escala| de Mate-Engine
const numOk = (v) => typeof v === 'number' && isFinite(v);
/** {x, y, r} de la cabeza en un <video>/<img> de la barra (object-fit: cover, abajo al centro). */
function cabezaVideo(el) {
  try {
    if (!el || typeof el.getBoundingClientRect !== 'function') return null;
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return null;
    const vw = el.videoWidth > 0 ? el.videoWidth : (el.naturalWidth > 0 ? el.naturalWidth : 720);
    const vh = el.videoHeight > 0 ? el.videoHeight : (el.naturalHeight > 0 ? el.naturalHeight : 1280);
    const s = Math.max(r.width / vw, r.height / vh);
    const cw = vw * s, ch = vh * s;
    const izq = r.left + (r.width - cw) / 2, arriba = r.top + (r.height - ch);
    const M = ALTOS_POR_METRO;
    return { x: izq + 0.505 * cw, y: arriba + (0.36 - ALTO_CABEZA_M * M) * ch, r: RADIO_CABEZA_M * M * ch };
  } catch (e) { return null; }
}
/** {x, y, r} de la cabeza del avatar 3D de la barra: el hueso proyectado (sin él, el 35 % desde arriba). */
function cabezaVrm(h, canvas) {
  try {
    if (!canvas || typeof canvas.getBoundingClientRect !== 'function') return null;
    const r = canvas.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) return null;
    const radio = 0.22 * r.width;
    const m = h && h.asistente;
    const ctx = m && m.ctx;
    const cab = ctx && ctx.huesos && ctx.huesos.head;
    const T = ctx && ctx.THREE;
    if (cab && T && typeof T.Vector3 === 'function' && typeof ctx.proyectar === 'function' && typeof cab.getWorldPosition === 'function') {
      const v = cab.getWorldPosition(new T.Vector3());
      v.y += ALTO_CABEZA_M;
      const p = ctx.proyectar(v);
      if (p && numOk(p.x) && numOk(p.y)) return { x: p.x, y: p.y, r: radio };
    }
    return { x: r.left + r.width / 2, y: r.top + 0.35 * r.height, r: radio };
  } catch (e) { return null; }
}
/** Publica `fn` como window.__luneCabezaBarra mientras el escenario esté a la vista. → quitar */
function publicarCabeza(fn) {
  window.__luneCabezaBarra = fn;
  return () => { if (window.__luneCabezaBarra === fn) window.__luneCabezaBarra = null; };
}

function AsistenteVideo({ state, pausado = false, baile = null }) {
  const wanted = VID_DIR + 'lune-' + (VID[state] || 'composed') + '.webm';
  const [src, setSrc] = React.useState(wanted);
  const [png, setPng] = React.useState(false);
  const video = React.useRef(null);
  const imagen = React.useRef(null);
  React.useEffect(() => { setSrc(wanted); setPng(false); }, [wanted]);
  React.useEffect(() => {
    const v = video.current;
    if (!v) return;
    try { if (pausado) v.pause(); else { const p = v.play(); if (p && p.catch) p.catch(() => {}); } } catch (e) { /* sin vídeo */ }
  }, [pausado, src]);
  // En pausa manda la pausa: Chromium reanuda solo el vídeo que paró al minimizar la ventana cuando
  // vuelve a verse, aunque entretanto Lune se haya quedado quieta o haya empezado un juego.
  React.useEffect(() => {
    const v = video.current;
    if (!v || !pausado || typeof v.addEventListener !== 'function') return undefined;
    const alReproducir = () => { try { v.pause(); } catch (e) { /* sin vídeo */ } };
    v.addEventListener('play', alReproducir);
    return () => { try { v.removeEventListener('play', alReproducir); } catch (e) { /* ya no está */ } };
  }, [pausado, src]);
  // Baile: transform del <video> al pulso (reloj de extra/baile.jsx), ≤ 30 fps y solo mientras baila.
  const bailando = !!(baile && baile.estado && baile.estado.bailando) && !pausado;
  React.useEffect(() => {
    const v = video.current;
    const B = window.LuneBaileWeb;
    const reloj = baile && baile.reloj;
    if (!v || !bailando || !B || !reloj) return undefined;
    let vivo = true, raf = 0, timer = 0, ultimo = -Infinity;
    const programar = () => {
      if (typeof window.requestAnimationFrame === 'function') raf = window.requestAnimationFrame(pintar);
      else timer = setTimeout(pintar, 1000 / FPS_BAILE_VIDEO);
    };
    function pintar() {
      if (!vivo) return;
      const t = Date.now();
      if (t - ultimo >= 1000 / FPS_BAILE_VIDEO - 1) {
        ultimo = t;
        try { v.style.transform = B.transformVideo(reloj.beat(), reloj.energia).css; } catch (e) { /* sin estilos */ }
      }
      programar();
    }
    try { v.classList.add('is-bailando'); } catch (e) { /* sin clases */ }
    programar();
    return () => {
      vivo = false;
      if (raf && typeof window.cancelAnimationFrame === 'function') window.cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
      try { v.style.transform = ''; v.classList.remove('is-bailando'); } catch (e) { /* sin estilos */ }
    };
  }, [bailando, src, png]);

  // Cortes 7/8: la cabeza para la comida de la web (solo mientras se ve).
  React.useEffect(() => (pausado ? undefined : publicarCabeza(() => cabezaVideo(png ? imagen.current : video.current))),
    [pausado, png]);

  if (png) return <img ref={imagen} src={ASISTENTE[state] || ASISTENTE.normal} alt="Lune" />;
  return (
    <video ref={video} key={src} src={src} autoPlay={!pausado} loop muted playsInline
      onError={() => { if (src !== VID_IDLE) setSrc(VID_IDLE); else setPng(true); }} />
  );
}

// ── VRM en la barra ──────────────────────────────────────────────────────────
/** {render, url, v, archivo, params} normalizado (null si no vale). */
function normalizarVrmBarra(o) {
  if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { return null; } }
  if (!o || typeof o !== 'object') return null;
  const txt = (v) => (v == null || typeof v === 'object' ? '' : String(v));
  const url = txt(o.url);
  return {
    render: txt(o.render) || 'animado',
    url: /^\/(?![\/\\])/.test(url) ? url : '',       // solo rutas del http local (ni //host ni http:)
    v: txt(o.v),
    archivo: txt(o.archivo),
    params: typeof o.params === 'string' ? o.params : '',
  };
}
const claveVrm = (i) => (i ? `${i.url}|${i.v}` : '');

/** Lo que publicó web_shell: window.__luneVrmBarra, el slot vrm_barra() y el evento 'lune-vrm-modelo'.
 *  Devuelve [info, personaje]: `personaje` cuenta los cambios de personaje (señal del puente
 *  personaje_cambio), para reintentar el avatar aunque el modelo sea el mismo. */
function useVrmBarra() {
  const [info, setInfo] = React.useState(() => normalizarVrmBarra(window.__luneVrmBarra));
  const [personaje, setPersonaje] = React.useState(0);
  React.useEffect(() => {
    let vivo = true;
    let puente = null;
    const poner = (o) => { const n = normalizarVrmBarra(o); if (vivo && n) setInfo(n); };
    const alModelo = (e) => poner(e && e.detail);
    const alPersonaje = () => { if (vivo) setPersonaje((n) => n + 1); };
    const pedir = () => {
      const b = window.lune;
      if (b && typeof b.vrm_barra === 'function') { try { b.vrm_barra((j) => poner(j)); } catch (e) { /* sin puente */ } }
      if (b && b.personaje_cambio && typeof b.personaje_cambio.connect === 'function') {
        try { b.personaje_cambio.connect(alPersonaje); puente = b; } catch (e) { /* puente viejo */ }
      }
    };
    window.addEventListener('lune-vrm-modelo', alModelo);
    if (window.lune) pedir(); else window.addEventListener('lune-ready', pedir, { once: true });
    return () => {
      vivo = false;
      window.removeEventListener('lune-vrm-modelo', alModelo);
      window.removeEventListener('lune-ready', pedir);
      if (puente) { try { puente.personaje_cambio.disconnect(alPersonaje); } catch (e) { /* ya no está */ } }
    };
  }, []);
  return [info, personaje];
}

/** ¿Ya está window.LuneVRMBarra? (el módulo puede cargar después que este .jsx) */
function useLibVrm() {
  const [lib, setLib] = React.useState(() => !!window.LuneVRMBarra);
  React.useEffect(() => {
    if (lib) return undefined;
    const listo = () => setLib(!!window.LuneVRMBarra);
    if (window.LuneVRMBarra) { listo(); return undefined; }
    window.addEventListener('lune-vrm-barra', listo);
    return () => window.removeEventListener('lune-vrm-barra', listo);
  }, [lib]);
  return lib;
}

/** El <canvas> con el avatar. Se crea al montar y se destruye al desmontar (un canvas
 *  con el contexto destruido no se reutiliza: para reintentar, React monta otro). */
function AsistenteVrm({ info, state, pausado, onFallo, baile = null, reposo = false }) {
  const lienzo = React.useRef(null);
  const handle = React.useRef(null);
  const fallo = React.useRef(onFallo);
  fallo.current = onFallo;
  const bailaba = React.useRef(false);
  React.useEffect(() => {
    const B = window.LuneVRMBarra;
    const c = lienzo.current;
    if (!B || !c || typeof B.crear !== 'function') { fallo.current('sin visor 3D'); return undefined; }
    let h = null;
    try {
      h = B.crear(c, info.url, {
        version: info.v || undefined,
        params: info.params || undefined,
        pausado: !!pausado,
        alError: (m) => fallo.current(m || 'error del visor 3D'),
      });
    } catch (e) { fallo.current(String((e && e.message) || e)); return undefined; }
    handle.current = h;
    try { h.setEstado(state || 'normal'); } catch (e) { /* sigue */ }
    return () => { handle.current = null; try { B.destruir(h); } catch (e) { /* ya estaba */ } };
  }, []);
  React.useEffect(() => { const h = handle.current; if (h) { try { h.setEstado(state || 'normal'); } catch (e) { /* sigue */ } } }, [state]);
  React.useEffect(() => { const h = handle.current; if (h) { try { h.pausar(!!pausado); } catch (e) { /* sigue */ } } }, [pausado]);
  // Lune en reposo: 0 fps sin soltar el contexto (pausar() manda sobre esto).
  React.useEffect(() => {
    const h = handle.current;
    if (h && typeof h.reposar === 'function') { try { h.reposar(!!reposo); } catch (e) { /* sigue */ } }
  }, [reposo]);
  // Cortes 7/8: la cabeza para la comida de la web (en pausa, Lune está fuera o hay un juego: nada).
  React.useEffect(() => (pausado ? undefined : publicarCabeza(() => cabezaVrm(handle.current, lienzo.current))), [pausado]);
  // Baile: módulo baileProc en el bus del avatar de la barra (se carga la primera vez que baila).
  const B = window.LuneBaileWeb;
  const bailando = !!(baile && baile.estado && baile.estado.bailando) && !pausado;
  const opciones = bailando && B && typeof B.opcionesPagina === 'function' ? B.opcionesPagina(baile.config, baile.estado) : null;
  const claveBaile = bailando ? JSON.stringify(opciones || {}) : '';
  React.useEffect(() => {
    const h = handle.current;
    if (!h || typeof h.mod !== 'function') return undefined;
    if (!bailando) {
      if (bailaba.current) { bailaba.current = false; try { h.mod('baileProc', 'bailar', false); } catch (e) { /* sigue */ } }
      return undefined;
    }
    let vivo = true, quitar = null;
    const usar = typeof h.usarModulo === 'function' ? h.usarModulo('baileProc') : Promise.resolve(false);
    Promise.resolve(usar).then((ok) => {
      if (!vivo || !ok) return;
      bailaba.current = true;
      try { h.mod('baileProc', 'bailar', true, opciones || {}); } catch (e) { /* sigue */ }
      const r = baile.reloj;
      if (r && r.sincronizado) { try { h.mod('baileProc', 'pulso', r.bpm, r.fase(), r.energia); } catch (e) { /* sigue */ } }
      if (typeof baile.suscribir === 'function') {
        quitar = baile.suscribir((p) => { try { h.mod('baileProc', 'pulso', p.bpm, p.fase, p.energia); } catch (e) { /* sigue */ } });
      }
    }, () => {});
    return () => { vivo = false; if (quitar) quitar(); };
  }, [bailando, claveBaile]);
  return <canvas ref={lienzo} className="ln-asistente-vrm" aria-label="Lune (avatar 3D)" />;
}

/** «♪ Spotify · 124 BPM» sobre la asistente de la barra mientras baila (y está a la vista). */
function RotuloBaile({ baile, visible }) {
  const B = window.LuneBaileWeb;
  const t = visible && baile && baile.estado && baile.estado.bailando && B && typeof B.rotulo === 'function' ? B.rotulo(baile.estado) : '';
  return t ? <div className="ln-baile-rotulo" aria-live="polite">{t}</div> : null;
}

function AsistenteStage({ state, asistenteFuera = false, modoJuego = false, baile = null, quieta = false }) {
  const [info, personaje] = useVrmBarra();
  const lib = useLibVrm();
  const [fallida, setFallida] = React.useState('');    // clave (url|v) del modelo que falló
  const render = info ? info.render : '';
  // Un fallo pasajero (WebGL, descarga) no deja la barra en vídeo para siempre: al
  // dejar el render VRM y volver a él, o al cambiar de personaje, se reintenta
  // aunque el modelo sea el mismo.
  React.useEffect(() => { if (render !== 'vrm') setFallida(''); }, [render]);
  React.useEffect(() => { if (personaje) setFallida(''); }, [personaje]);
  const onFallo = React.useCallback((motivo) => {
    try { console.warn('[barra] avatar 3D:', motivo); } catch (e) { /* sin consola */ }
    setFallida(claveVrm(info));
  }, [info && info.url, info && info.v]);
  // Un modelo nuevo (otra versión) se vuelve a intentar aunque el anterior fallara.
  const usarVrm = !!(info && info.render === 'vrm' && info.url && lib && fallida !== claveVrm(info));
  const rotulo = <RotuloBaile baile={baile} visible={!asistenteFuera && !modoJuego} />;
  if (usarVrm) return <>{rotulo}<AsistenteVrm info={info} state={state} pausado={asistenteFuera || modoJuego} onFallo={onFallo} baile={baile}
    reposo={quieta} /></>;
  if (asistenteFuera) return null;
  return <>{rotulo}<AsistenteVideo state={state} pausado={modoJuego || quieta} baile={baile} /></>;
}

// Lune está fuera (asistente en escritorio): el escenario no la dibuja dos veces.
// Queda un aviso y un botón para traerla de vuelta a la ventana.
function AsistenteFuera({ onTraer }) {
  return (
    <div className="ln-asistente-out">
      <div className="ln-asistente-out-jp lune-jp">月</div>
      <div className="ln-asistente-out-t">Lune está en tu escritorio</div>
      <div className="ln-asistente-out-d">Anda suelta por ahí, fuera de esta ventana. Aquí no la verás doble.</div>
      {onTraer && <button className="ln-asistente-out-btn" onClick={onTraer}>Traerla de vuelta</button>}
    </div>
  );
}

// ── Tareas (10.9): acceso siempre a la vista con las pendientes de hoy ───────
/** {hoy, total, ok} de lo que manda window.luneTareas (estado() o la señal cambio); null si no vale. */
function contadorTareas(j) {
  let o = j;
  if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { return null; } }
  if (!o || typeof o !== 'object') return null;
  const c = o.contador && typeof o.contador === 'object' ? o.contador : {};
  const n = (v) => (typeof v === 'number' && isFinite(v) && v >= 0 ? Math.floor(v) : 0);
  const hoy = n(c.hoy);
  return { hoy, total: Math.max(hoy, n(c.total)), ok: o.disponible === true };
}
/** «3 para hoy · 5 en total» (lo mismo que LuneTareas.textoContador de extra/tareas.jsx). */
function textoTareas(c) {
  if (!c || !c.ok) return 'Mi día';
  if (!c.total) return 'Nada pendiente';
  if (!c.hoy) return c.total === 1 ? '1 pendiente' : `${c.total} pendientes`;
  return `${c.hoy} para hoy` + (c.total > c.hoy ? ` · ${c.total} en total` : '');
}
const IconoTareas = (p) => React.createElement('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true', ...p },
  React.createElement('circle', { key: 0, cx: 12, cy: 12, r: 9 }),
  React.createElement('path', { key: 1, d: 'M8 12.2l2.8 2.8L16.4 9.3' }));

function TareasAcceso({ activo = false, onAbrir }) {
  const [c, setC] = React.useState(null);
  React.useEffect(() => {
    let vivo = true, senal = null;
    const poner = (j) => { const n = contadorTareas(j); if (vivo && n) setC(n); };
    const cablear = () => {
      const t = window.luneTareas;
      if (!t) return;
      if (typeof t.estado === 'function') { try { t.estado(poner); } catch (e) { /* sin puente */ } }
      if (t.cambio && typeof t.cambio.connect === 'function') {
        try { t.cambio.connect(poner); senal = t.cambio; } catch (e) { /* puente viejo */ }
      }
    };
    if (window.luneTareas) cablear(); else window.addEventListener('lune-ready', cablear, { once: true });
    return () => {
      vivo = false;
      window.removeEventListener('lune-ready', cablear);
      if (senal) { try { senal.disconnect(poner); } catch (e) { /* ya no está */ } }
    };
  }, []);
  const abrir = () => {
    if (typeof onAbrir === 'function') { onAbrir(); return; }
    try { window.dispatchEvent(new window.CustomEvent('lune-vista', { detail: 'tareas' })); } catch (e) { /* sin eventos */ }
  };
  const hoy = c && c.ok ? c.hoy : 0;
  return (
    <button type="button" className={`ln-tareas-acc${activo ? ' is-active' : ''}${hoy ? ' has-pend' : ''}`} onClick={abrir}
      aria-pressed={activo} title="Tus tareas: Mi día y lo que me pediste que te recordara">
      <span className="ln-tareas-acc-ic"><IconoTareas /></span>
      <span className="ln-tareas-acc-tx">
        <span className="ln-tareas-acc-nom">Tareas</span>
        <span className="ln-tareas-acc-desc">{textoTareas(c)}</span>
      </span>
      {c && c.ok ? <span className="ln-tareas-acc-num" aria-label={`${hoy} pendientes hoy`}>{hoy}</span> : null}
    </button>
  );
}

function Sidebar({ provider, onProvider, asistenteState, asistenteFuera = false, onTraer, compat = null, modoJuego = false, baile = null,
  vista = '', onTareas, quieta = false }) {
  const { ProviderTab } = window.LUNE;
  // Tercera pestaña: API compatible con OpenAI (LM Studio, Groq…), solo si está configurada.
  const conCompat = !!(compat && compat.on);
  const descCompat = (compat && compat.model) || 'API compatible con OpenAI';
  // Clic derecho sobre la asistente de la barra → menú radial SVG (sin el menú de Chromium).
  const abrirRadial = (e) => {
    if (!window.LuneRadial) return;
    e.preventDefault();
    window.LuneRadial.abrir(e.clientX, e.clientY);
  };
  // Clic central (soltado) sobre la asistente → radial «secundario» (comida), como la flotante (cortes 7/8).
  const centralAbajo = (e) => { if (e && e.button === 1 && typeof e.preventDefault === 'function') e.preventDefault(); };
  const centralArriba = (e) => {
    if (!e || e.button !== 1 || asistenteFuera || !window.LuneRadial) return;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    window.LuneRadial.abrir(e.clientX, e.clientY, 'secundario');
  };
  return (
    <aside className="ln-sidebar">
      <div className="ln-brand">
        <div className="ln-brand-mark lune-jp">月</div>
        <div className="ln-brand-tx">
          <div className="ln-brand-name">LUNE <span>CD</span></div>
          <div className="ln-brand-sub"><span className="lune-jp">ルネ</span> · ASISTENTE PERSONAL</div>
        </div>
      </div>

      <div className="ln-sec-label">// Red Neuronal</div>
      <div className="ln-providers">
        <ProviderTab icon={<window.IconCloud/>} name="Lune AI · Nube" desc="Enrutamiento inteligente" accent="blue"
          active={provider==='cloud'} onClick={()=>onProvider('cloud')} />
        <ProviderTab icon={<window.IconCpu/>} name="Lune AI · Local" desc="Offline · sin red" accent="cyan"
          active={provider==='local'} onClick={()=>onProvider('local')} />
        {conCompat && (
          <ProviderTab icon={<window.IconBolt/>} name="Lune AI · API" desc={descCompat} accent="yellow"
            title={compat.url ? `API compatible con OpenAI · ${compat.url}` : 'API compatible con OpenAI'}
            active={provider==='compat'} onClick={()=>onProvider('compat')} />
        )}
      </div>

      <div className="ln-sec-label">// Mi día</div>
      <TareasAcceso activo={vista === 'tareas'} onAbrir={onTareas} />

      <div className="ln-asistente">
        <div className={`ln-asistente-stage${asistenteFuera ? ' is-out' : ''}`} onContextMenu={abrirRadial}
          onMouseDown={centralAbajo} onMouseUp={centralArriba}>
          {/* El avatar 3D sigue montado (en pausa y oculto) mientras Lune está fuera. */}
          {asistenteFuera ? <AsistenteFuera onTraer={onTraer} /> : null}
          <AsistenteStage state={asistenteState} asistenteFuera={asistenteFuera} modoJuego={modoJuego} baile={baile} quieta={quieta} />
        </div>
      </div>
    </aside>
  );
}
window.Sidebar = Sidebar;
window.LuneBarra = { normalizarVrmBarra, claveVrm, cabezaVideo, cabezaVrm, contadorTareas, textoTareas };
