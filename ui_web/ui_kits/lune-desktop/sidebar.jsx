/* Lune CD desktop — Sidebar (v10)
 *
 * Escenario de la mascota (MascotStage):
 *   · Por defecto, el vídeo del estado (assets/mascot/anime-videos/lune-<estado>.webm) o su PNG.
 *   · Con la mascota en VRM (Ajustes → Mascota → VRM 3D) y un .vrm publicado por ui/web_shell.py
 *     en /vrm/actual.vrm, el avatar 3D de vrm_barra.js (window.LuneVRMBarra) sobre un <canvas>.
 *     Si el módulo carga tarde se espera su evento 'lune-vrm-barra'; si falla WebGL o el modelo,
 *     o deja de haber modelo, se vuelve al vídeo. El cambio de personaje o de modelo lo avisa
 *     web_shell con el evento 'lune-vrm-modelo' (y ya recarga los avatares vivos).
 *   · Lune fuera (mascota de escritorio): la barra no la dibuja dos veces. El vídeo se desmonta y el
 *     avatar 3D se pausa (FPS 0 y contexto WebGL liberado) y se oculta bajo el aviso.
 */

// PNG estático (respaldo si el video de un estado aún no existe).
const MASCOT = {
  normal:   '../../assets/mascot/anime/lune-composed.png',
  happy:    '../../assets/mascot/anime/lune-happy.png',
  reading:  '../../assets/mascot/anime/lune-thinking.png',
  thinking: '../../assets/mascot/anime/lune-thinking.png',
  typing:   '../../assets/mascot/anime/lune-composed.png',
  error:    '../../assets/mascot/anime/lune-nervous.png',
  angry:    '../../assets/mascot/anime/lune-angry.png',
  surprised:'../../assets/mascot/anime/lune-surprised.png',
  nervous:  '../../assets/mascot/anime/lune-nervous.png',
  wave:     '../../assets/mascot/anime/lune-wave.png',
};

// Estado → nombre base del video (assets/mascot/anime-videos/lune-<base>.mp4).
// Si el clip no existe todavía, cae al idle "composed" y, si tampoco, al PNG.
// v10 — un estado por clip. Los que aún no tienen video caen al idle hasta que
// exista `lune-<estado>.webm` (ver scripts/convertir_mascota.py).
const VID = {
  normal:'composed', thinking:'thinking', happy:'happy', angry:'angry', error:'angry',
  surprised:'surprised', nervous:'nervous', wave:'wave', dismiss:'dismiss',
  sad:'sad', curious:'curious', reading:'curious',
  typing:'working', listening:'listening', talking:'talking',
  laughing:'laughing', bored:'bored',
};
const VID_DIR = '../../assets/mascot/anime-videos/';
const VID_IDLE = VID_DIR + 'lune-composed.webm';

function MascotVideo({ state }) {
  const wanted = VID_DIR + 'lune-' + (VID[state] || 'composed') + '.webm';
  const [src, setSrc] = React.useState(wanted);
  const [png, setPng] = React.useState(false);
  React.useEffect(() => { setSrc(wanted); setPng(false); }, [wanted]);

  if (png) return <img src={MASCOT[state] || MASCOT.normal} alt="Lune" />;
  return (
    <video key={src} src={src} autoPlay loop muted playsInline
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
function MascotVrm({ info, state, pausado, onFallo }) {
  const lienzo = React.useRef(null);
  const handle = React.useRef(null);
  const fallo = React.useRef(onFallo);
  fallo.current = onFallo;
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
  return <canvas ref={lienzo} className="ln-mascot-vrm" aria-label="Lune (avatar 3D)" />;
}

function MascotStage({ state, mascotaFuera = false }) {
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
  if (usarVrm) return <MascotVrm info={info} state={state} pausado={mascotaFuera} onFallo={onFallo} />;
  if (mascotaFuera) return null;
  return <MascotVideo state={state} />;
}

// Lune está fuera (mascota de escritorio): el escenario no la dibuja dos veces.
// Queda un aviso y un botón para traerla de vuelta a la ventana.
function MascotFuera({ onTraer }) {
  return (
    <div className="ln-mascot-out">
      <div className="ln-mascot-out-jp lune-jp">月</div>
      <div className="ln-mascot-out-t">Lune está en tu escritorio</div>
      <div className="ln-mascot-out-d">Anda por ahí como mascota flotante. Aquí no la verás doble.</div>
      {onTraer && <button className="ln-mascot-out-btn" onClick={onTraer}>Traerla de vuelta</button>}
    </div>
  );
}

function Sidebar({ provider, onProvider, mascotState, mascotaFuera = false, onTraer, compat = null }) {
  const { ProviderTab } = window.LUNE;
  // Tercera pestaña: API compatible con OpenAI (LM Studio, Groq…), solo si está configurada.
  const conCompat = !!(compat && compat.on);
  const descCompat = (compat && compat.model) || 'API compatible con OpenAI';
  return (
    <aside className="ln-sidebar">
      <div className="ln-brand">
        <div className="ln-brand-mark lune-jp">月</div>
        <div className="ln-brand-tx">
          <div className="ln-brand-name">LUNE <span>CD</span></div>
          <div className="ln-brand-sub"><span className="lune-jp">ルネ</span> · HÍBRIDO v9.0</div>
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

      <div className="ln-mascot">
        <div className={`ln-mascot-stage${mascotaFuera ? ' is-out' : ''}`}>
          {/* El avatar 3D sigue montado (en pausa y oculto) mientras Lune está fuera. */}
          {mascotaFuera ? <MascotFuera onTraer={onTraer} /> : null}
          <MascotStage state={mascotState} mascotaFuera={mascotaFuera} />
        </div>
      </div>
    </aside>
  );
}
window.Sidebar = Sidebar;
window.LuneBarra = { normalizarVrmBarra, claveVrm };
