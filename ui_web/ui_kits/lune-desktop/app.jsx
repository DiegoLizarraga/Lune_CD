/* Lune CD desktop — App shell + state */
const { useState, useRef, useCallback } = React;

const PROVIDERS = {
  local: { name:'Lune AI · Local', desc:'Modelo offline · sin red', Icon: () => <window.IconCpu/>, accent:'cyan' },
  cloud: { name:'Lune AI · Nube',  desc:'Enrutamiento inteligente', Icon: () => <window.IconCloud/>, accent:'blue' },
  // Tercer proveedor (solo si está configurado en Ajustes): LM Studio, Groq, OpenAI…
  compat: { name:'Lune AI · API', desc:'API compatible con OpenAI', Icon: () => <window.IconBolt/>, accent:'yellow' },
};
const COMPAT_OFF = { on:false, model:'', url:'' };
let _mid = 0;
const uid = () => `m${++_mid}`;
const NOW = () => new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });

// Quita los marcadores de control (<|ACT …|>) del texto mientras se transmite,
// para que no se vean en la burbuja durante el streaming.
function limpiarMarcadores(t) {
  return (t || '')
    .replace(/<\|\s*(ACT|DELAY|CALL)\b[\s\S]*?\|>/gi, '')   // marcador completo
    .replace(/<\|\s*(ACT|DELAY|CALL)\b[\s\S]*$/i, '')        // marcador parcial al final
    .replace(/\s+$/,'');
}

function Topbar({ provider, status, view, onView, onMenu }) {
  const { StatusPill, IconButton } = window.LUNE;
  const p = PROVIDERS[provider] || PROVIDERS.local;
  return (
    <header className="ln-topbar">
      <span className={`ln-topbar-ic ${provider}`}><p.Icon/></span>
      <div className="ln-topbar-tx">
        <span className="ln-topbar-title">{p.name}</span>
        <span className="ln-topbar-desc">· {p.desc}</span>
      </div>
      <div className="ln-topbar-right">
        <button className="p3-menubtn" onClick={onMenu}><span>Menú</span></button>
        <IconButton label="Ajustes" variant="ghost" active={view==='settings'}
          onClick={()=>onView(view==='settings'?'chat':'settings')}><window.IconGear/></IconButton>
        <StatusPill status={status} />
      </div>
    </header>
  );
}

const SHARDS = [
  { l:'6%',  s:46, c:'var(--cyan-500)',  d:'26s', dl:'0s',   o:.10 },
  { l:'16%', s:22, c:'var(--blue-400)',  d:'19s', dl:'-6s',  o:.12 },
  { l:'28%', s:64, c:'var(--blue-500)',  d:'34s', dl:'-14s', o:.07 },
  { l:'40%', s:16, c:'var(--yellow-500)',d:'22s', dl:'-3s',  o:.14 },
  { l:'52%', s:38, c:'var(--cyan-400)',  d:'28s', dl:'-18s', o:.09 },
  { l:'63%', s:26, c:'var(--blue-300)',  d:'21s', dl:'-9s',  o:.11 },
  { l:'74%', s:54, c:'var(--cyan-500)',  d:'36s', dl:'-24s', o:.06 },
  { l:'84%', s:18, c:'var(--yellow-400)',d:'24s', dl:'-12s', o:.12 },
  { l:'92%', s:32, c:'var(--blue-400)',  d:'30s', dl:'-20s', o:.08 },
];

// Tema "Nube": cielo nocturno con estrellas, luna y nubecitas a la deriva.
// Va dentro de .ln-main (solo con Lune AI · Nube); las barras y la vista quedan encima.
const NUBES = [
  { w:180, top:'10%', o:.85, d:'70s',  dl:'-10s', c:'#e6efff' },
  { w:110, top:'26%', o:.5,  d:'95s',  dl:'-48s', c:'#c9dbff' },
  { w:240, top:'56%', o:.35, d:'120s', dl:'-70s', c:'#b7cdf7' },
  { w:90,  top:'70%', o:.45, d:'60s',  dl:'-22s', c:'#dbe7ff' },
  { w:150, top:'42%', o:.6,  d:'85s',  dl:'-60s', c:'#e6efff' },
  { w:70,  top:'84%', o:.3,  d:'55s',  dl:'-35s', c:'#c9dbff' },
];
const NubeSvg = ({ fill, ...p }) => (
  <svg viewBox="0 0 120 60" fill={fill} {...p}>
    <ellipse cx="35" cy="42" rx="24" ry="15"/><ellipse cx="62" cy="30" rx="26" ry="19"/><ellipse cx="90" cy="43" rx="21" ry="13"/>
  </svg>
);
function BgNube() {
  return (
    <div className="nube-sky" aria-hidden="true">
      <div className="nube-stars" />
      <div className="nube-moon" />
      {NUBES.map((n, i) => (
        <NubeSvg key={i} className="nube-cloud" width={n.w} fill={n.c}
          style={{ top:n.top, opacity:n.o, animation:`nube-drift ${n.d} linear ${n.dl} infinite` }} />
      ))}
    </div>
  );
}
window.NubeSvg = NubeSvg;

// Vistas a las que se puede ir con el evento de window 'lune-vista' (extra/alarmas.jsx: «Abrir alarmas»).
const VISTAS_APP = ['chat', 'settings', 'personajes', 'memoria', 'historial', 'optimizar', 'tools', 'alarmas'];

/** Baile (extra/baile.jsx): estado y pulso para la barra lateral y el CommandMenu. null si ese archivo
 *  no cargó. window.LuneBaileWeb no aparece ni desaparece en la vida de la página: el orden de los
 *  hooks es estable. */
function useBaileApp() {
  const B = window.LuneBaileWeb;
  return B && typeof B.useBaile === 'function' ? B.useBaile() : null;
}

function BgShards() {
  return (
    <div className="p3-bg" aria-hidden="true">
      {SHARDS.map((s, i) => (
        <span key={i} className="p3-shard" style={{
          left:s.l, width:s.s, height:s.s*1.4, background:s.c,
          '--o':s.o, animationDuration:s.d, animationDelay:s.dl,
        }} />
      ))}
    </div>
  );
}

function App() {
  const [provider, setProvider] = useState('local');
  const [view, setView] = useState('chat');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [telegramOn, setTelegramOn] = useState(false);
  const [mascot, setMascot] = useState('normal');
  const [mascotaFuera, setMascotaFuera] = useState(false); // Lune está en el escritorio (mascota flotante)
  const [menuOpen, setMenuOpen] = useState(false);
  const [adjuntos, setAdjuntos] = useState([]);   // nombres de archivos adjuntos
  const [grabando, setGrabando] = useState(false); // micrófono grabando
  const [llamadaOn, setLlamadaOn] = useState(false); // modo llamada por voz
  const [toast, setToast] = useState('');          // aviso breve del backend
  const [compat, setCompat] = useState(COMPAT_OFF); // API compatible configurada (tercer proveedor)
  const [modoJuego, setModoJuego] = useState(false); // hay un juego delante (señal juego_estado, corte 4)
  const baile = useBaileApp();                       // cortes 5/6: la mascota de la barra baila
  const toastT = useRef(null);
  const sendRef = useRef(null);                    // send() actual, para las señales
  // Efectos: manda la config (efectos.*, por window.luneEscritorio); localStorage es solo el respaldo
  // sin backend (su origen cambia en cada arranque: el puerto del servidor local es otro).
  const [fx, setFx] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lune-fx')) || { bg:true, sweep:true, micro:true }; }
    catch(e){ return { bg:true, sweep:true, micro:true }; }
  });
  React.useEffect(() => { try { localStorage.setItem('lune-fx', JSON.stringify(fx)); } catch (e) {} }, [fx]);
  const setFxKey = (k) => (e) => {
    const v = !!e.target.checked;
    setFx((f) => ({ ...f, [k]: v }));
    if (window.LuneApariencia) window.LuneApariencia.guardarEfecto(k, v);
  };
  const timers = useRef([]);
  const providerRef = useRef(provider); providerRef.current = provider;
  const streamId = useRef(null);   // id del mensaje del bot que se está llenando
  const holdRef = useRef(4000);    // cuánto dura la última expresión (según intensidad)

  const mostrarToast = useCallback((msg) => {
    if (!msg) return;
    setToast(String(msg));
    if (toastT.current) clearTimeout(toastT.current);
    toastT.current = setTimeout(() => setToast(''), 3200);
  }, []);

  // Puente con el backend real (QWebChannel). Si no existe (navegador), la UI
  // usa el motor de demostración de chat.jsx y todo sigue funcionando.
  React.useEffect(() => {
    function wire() {
      const b = window.lune;
      if (!b) return;
      // El efecto de `provider` pudo correr antes de que existiera window.lune (al
      // recargar la página): el puente se quedaría con el proveedor de antes. Se le
      // dice (o se toma el suyo con estado_inicial) al final de wire(), tras proveedores().
      const resincronizar = () => {
        try { if (typeof b.proveedor_elegido === 'function') b.proveedor_elegido(providerRef.current); } catch (e) {}
      };
      b.chunk.connect((acumulado) => {
        setTyping(false);   // la cara la lleva `acto` (typing y los <|ACT|> según llegan)
        // El id se fija AQUÍ (síncrono), no dentro del updater: si no, 'done'
        // podría leer streamId aún vacío y crear una segunda burbuja.
        if (!streamId.current) streamId.current = uid();
        const id = streamId.current;
        const limpio = limpiarMarcadores(acumulado);
        setMessages((m) => {
          if (m.some((x) => x.id === id)) return m.map((x) => x.id === id ? { ...x, text: limpio } : x);
          return [...m, { id, role:'bot', provider: providerRef.current, text: limpio, time: NOW(), streaming:true }];
        });
      });
      b.acto.connect((estado) => setMascot(estado));
      // La expresión final llega por `done` (o, con voz, tramo a tramo por `acto`)
      // y SE QUEDA: si la haces reír, sigue riéndose hasta el siguiente mensaje.
      b.emocion.connect(() => {});
      b.voz_estado.connect((on) => setVoiceOn(!!on));
      b.telegram_estado.connect((run, detail) => { setTelegramOn(!!run); if (detail) mostrarToast(detail); });
      b.adjuntos_cambio.connect((j) => { try { setAdjuntos(JSON.parse(j) || []); } catch (e) { setAdjuntos([]); } });
      b.grabando.connect((on) => setGrabando(!!on));
      b.dictado.connect((texto) => { if (texto) setInput((v) => (v ? v + ' ' : '') + texto); });
      b.aviso.connect((msg) => mostrarToast(msg));
      // Mascota de escritorio: mientras está fuera, la barra lateral no la dibuja.
      b.mascota_estado.connect((v) => setMascotaFuera(!!v));
      try { b.mascota_visible((v) => setMascotaFuera(!!v)); } catch (e) {}
      // Modo llamada: lo que dice el usuario entra como mensaje y se envía solo.
      b.usuario_dijo.connect((texto) => { if (texto && sendRef.current) sendRef.current(texto); });
      b.llamada_estado.connect((on, estado) => {
        setLlamadaOn(!!on);
        // La mascota "actúa" la llamada: escucha, piensa, habla.
        const M = { escuchando:'listening', transcribiendo:'thinking', esperando:'thinking', hablando:'talking', off:'normal' };
        if (on && M[estado]) setMascot(M[estado]);
        if (!on) setMascot('normal');
        if (estado && (!on || estado === 'escuchando')) mostrarToast(on ? 'Llamada: te escucho' : estado);
      });
      b.herramienta.connect((ok, icon, title, detail) => {
        setTyping(false);
        setMessages((m) => [...m, { id: uid(), kind:'tool', tool:{ ok, icon, title, detail } }]);
      });
      b.done.connect((texto, mascota) => {
        setTyping(false); setBusy(false);
        const id = streamId.current;
        streamId.current = null;
        setMessages((m) => {
          if (id && m.some((x) => x.id === id)) return m.map((x) => x.id === id ? { ...x, text: texto || x.text, streaming:false } : x);
          if (texto) return [...m, { id: uid(), role:'bot', provider: providerRef.current, text: texto, time: NOW() }];
          return m;
        });
        if (mascota) setMascot(mascota);   // vacío = la cara la va llevando la voz
      });
      // Chat de la mascota (doble clic sobre ella): mismo historial que esta ventana.
      // Lo que escribiste allí entra aquí como mensaje tuyo y la respuesta llega por chunk/done.
      try {
        b.usuario_mascota.connect((texto) => {
          if (!texto) return;
          streamId.current = null;
          setMessages((m) => [...m, { id: uid(), role:'user', text: texto, time: NOW() }]);
          setBusy(true); setTyping(true); setMascot('thinking');
        });
      } catch (e) {}
      // Tercer proveedor: la pestaña «API» solo sale si la API compatible está configurada.
      const leerCompat = (j) => {
        let r = {}; try { r = typeof j === 'string' ? JSON.parse(j) : (j || {}); } catch (e) {}
        setCompat(r && r.compat ? { on:true, model: String(r.compat_model || ''), url: String(r.compat_url || '') } : COMPAT_OFF);
      };
      try { b.proveedores(leerCompat); } catch (e) {}
      try { b.proveedores_cambio.connect(leerCompat); } catch (e) {}
      // Estado inicial del puente (p. ej. tras cambiar de interfaz en caliente): proveedor, voz,
      // bot, mascota y la conversación en curso {proveedor, voz, telegram, mascota_fuera,
      // mensajes:[{role, text}]}. Va DESPUÉS de proveedores(): con «compat» la pestaña ya existe
      // y no se cae a «local». Sin estado_inicial (backend viejo): se resincroniza como antes.
      if (typeof b.estado_inicial === 'function') {
        try {
          b.estado_inicial((j) => {
            let r = {};
            try { r = (typeof j === 'string' ? JSON.parse(j) : j) || {}; } catch (e) {}
            const prov = PROVIDERS[r.proveedor] ? r.proveedor : '';
            if (prov) setProvider(prov); else resincronizar();
            setVoiceOn(!!r.voz); setTelegramOn(!!r.telegram); setMascotaFuera(!!r.mascota_fuera);
            if (Array.isArray(r.mensajes) && r.mensajes.length) {
              setMessages(r.mensajes.filter((m) => m && m.text).map((m) => ({ id: uid(), role: m.role === 'user' ? 'user' : 'bot',
                provider: prov || providerRef.current, text: String(m.text), time: '' })));
            }
          });
        } catch (e) { resincronizar(); }
      } else resincronizar();
    }
    if (window.lune) wire();
    else window.addEventListener('lune-ready', wire, { once:true });
  }, []);

  // Corte 4 (window.luneEscritorio): efectos desde la config, tema (window.luneTema) al arrancar y en
  // tema_cambio, modo juego y navegar → vista. La lógica vive en extra/apariencia.jsx.
  React.useEffect(() => {
    const A = window.LuneApariencia;
    return A && typeof A.conectarApp === 'function' ? A.conectarApp({ setFx, setModoJuego, setView }) : undefined;
  }, []);
  React.useEffect(() => { try { document.body.classList.toggle('modo-juego', modoJuego); } catch (e) {} }, [modoJuego]);
  // Cortes 5/6: 'lune-vista' ({detail: vista}) desde las tarjetas («Abrir alarmas»). Solo vistas conocidas.
  React.useEffect(() => {
    const alVista = (e) => { const v = String((e && e.detail) || ''); if (VISTAS_APP.includes(v)) setView(v); };
    window.addEventListener('lune-vista', alVista);
    return () => window.removeEventListener('lune-vista', alVista);
  }, []);
  // F1 → menú radial (SVG) sobre la mascota de la barra.
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'F1' || e.repeat) return;
      e.preventDefault();
      if (window.LuneRadial) window.LuneRadial.abrir();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  // Expresión elegida en el radial con Lune en la barra: la pone la barra 4 s.
  const expresionRadial = useCallback((x) => {
    setMascot(x);
    const t = setTimeout(() => setMascot((m) => (m === x ? 'normal' : m)), 4000);
    timers.current.push(t);
  }, []);

  // Si la API compatible deja de estar configurada, se vuelve al modelo local.
  React.useEffect(() => { if (!compat.on && provider === 'compat') setProvider('local'); }, [compat.on, provider]);
  // El chat de la mascota usa el mismo proveedor que esta ventana.
  React.useEffect(() => {
    if (window.lune && typeof window.lune.proveedor_elegido === 'function') {
      try { window.lune.proveedor_elegido(provider); } catch (e) {}
    }
  }, [provider]);

  const status = busy ? 'busy' : (mascot === 'error' ? 'error' : 'live');

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  const send = useCallback((textoArg) => {
    // Puede recibir un texto explícito (chip de bienvenida) o usar el input.
    const text = (typeof textoArg === 'string' ? textoArg : input).trim();
    if (!text || busy) return;
    setView('chat');
    setInput('');
    const userMsg = { id: uid(), role:'user', text, time: NOW() };
    setMessages((m) => [...m, userMsg]);
    setBusy(true); setTyping(true); setMascot('thinking');

    // Backend real: el modelo, la memoria y las herramientas de Lune.
    if (window.lune) {
      streamId.current = null;
      try { window.lune.enviar(text, provider); }
      catch (e) { setBusy(false); setTyping(false); setMascot('error'); }
      return;
    }

    // ── Demo (navegador, sin backend): motor simulado de chat.jsx ──
    const reply = window.buildReply(text, provider);
    const t1 = setTimeout(() => {
      setTyping(false);
      if (reply.kind === 'tool') {
        setMessages((m) => [...m, { id: uid(), kind:'tool', tool: reply.tool }]);
        setMascot(reply.mascot || 'happy');
        setBusy(false);
        return;
      }
      // typewriter stream
      const full = reply.text;
      const botId = uid();
      setMessages((m) => [...m, { id: botId, role:'bot', provider, text:'', time: NOW(), streaming:true }]);
      setMascot('typing');
      let i = 0;
      const step = () => {
        i += Math.max(2, Math.round(full.length / 22));
        const slice = full.slice(0, i);
        setMessages((m) => m.map((x) => x.id === botId ? { ...x, text: slice } : x));
        if (i < full.length) {
          const t = setTimeout(step, 32); timers.current.push(t);
        } else {
          setMessages((m) => m.map((x) => x.id === botId ? { ...x, streaming:false } : x));
          setMascot(reply.mascot || 'happy');
          setBusy(false);
          const tr = setTimeout(() => setMascot('normal'), 4000); timers.current.push(tr);
        }
      };
      step();
    }, 850);
    timers.current.push(t1);
  }, [input, busy, provider]);

  const stop = useCallback(() => {
    if (window.lune) { try { window.lune.detener(); } catch (e) {} }
    clearTimers();
    setTyping(false); setBusy(false); setMascot('normal');
    streamId.current = null;
    setMessages((m) => m.map((x) => x.streaming ? { ...x, streaming:false } : x));
  }, []);

  // Limpiar chat: también el historial del modelo y la conversación de las acciones
  // (presupuesto repuesto; las preguntas «¿Lo hago?» abiertas se cierran sin hacer nada).
  const clear = useCallback(() => {
    if (window.lune && typeof window.lune.limpiar_chat === 'function') { try { window.lune.limpiar_chat(); } catch (e) {} }
    clearTimers(); streamId.current = null;
    setMessages([]); setTyping(false); setBusy(false); setMascot('normal'); setView('chat');
  }, []);

  // ── Toggles cableados al backend real (con fallback local para la demo) ──
  const toggleVoz = useCallback(() => {
    if (window.lune) window.lune.voz_toggle((v) => setVoiceOn(!!v));
    else setVoiceOn((v) => !v);
  }, []);
  const toggleTelegram = useCallback(() => {
    if (window.lune) window.lune.telegram_toggle((r) => {
      try { r = JSON.parse(r); } catch (e) { r = {}; }
      setTelegramOn(!!(r && r.running));
    });
    else setTelegramOn((v) => !v);
  }, []);
  const toggleMascota = useCallback(() => {
    if (window.lune) window.lune.mascota_toggle(() => {});
  }, []);
  const onAttach = useCallback(() => {
    if (window.lune) window.lune.adjuntar((j) => { try { setAdjuntos(JSON.parse(j) || []); } catch (e) {} });
  }, []);
  const onMic = useCallback(() => {
    if (window.lune) window.lune.dictar(() => {});
    else mostrarToast('El dictado necesita la app (Whisper local).');
  }, [mostrarToast]);
  // Modo llamada (toggle, como Telegram): conversación continua solo por voz.
  const toggleLlamada = useCallback(() => {
    if (window.lune) window.lune.llamada_toggle(() => {});
    else mostrarToast('El modo llamada necesita la app (Whisper + voz).');
  }, [mostrarToast]);
  sendRef.current = send;   // las señales del puente usan siempre el send() vigente
  // Acciones del despachador del corte 4 (luneEscritorio.accion_menu): pantalla grande, bailar,
  // temporizador rápido… Sin backend o sin handler en este modo, un aviso.
  const accionEscritorio = useCallback((id, arg = '', okTexto = '') => {
    const e = window.luneEscritorio;
    if (!e || typeof e.accion_menu !== 'function') { mostrarToast('Esto necesita la app.'); return; }
    try {
      e.accion_menu(id, arg, (ok) => { if (!ok) mostrarToast('Ahora no está disponible.'); else if (okTexto) mostrarToast(okTexto); });
    } catch (err) { mostrarToast('No pude hacerlo.'); }
  }, [mostrarToast]);
  const bailando = !!(baile && baile.estado && baile.estado.bailando);
  const cargarHistorial = useCallback((msgs) => {
    clearTimers();
    setMessages((msgs || []).map((m) => ({ id: uid(), role: m.role, provider: providerRef.current, text: m.text, time: '' })));
    setView('chat');
  }, []);

  return (
    <div className={`ln-app lune-backdrop${fx.bg?'':' fx-no-bg'}${fx.sweep?'':' fx-no-sweep'}${fx.micro?'':' fx-no-micro'}${provider==='cloud'?' tema-nube':''}`}>
      {fx.bg && <BgShards />}
      <window.Sidebar provider={provider} onProvider={setProvider} mascotState={mascot}
        mascotaFuera={mascotaFuera} onTraer={toggleMascota} compat={compat} modoJuego={modoJuego} baile={baile} />
      <main className="ln-main">
        {provider==='cloud' && <BgNube />}
        <Topbar provider={provider} status={status} view={view} onView={setView} onMenu={() => setMenuOpen(true)} />
        <div className="ln-view" key={view}>
          {view === 'chat' ? <window.ChatStream messages={messages} typing={typing} provider={provider} onEjemplo={send} />
           : view === 'personajes' ? <window.PersonajesPanel />
           : view === 'memoria' ? <window.MemoriaPanel />
           : view === 'historial' ? <window.HistorialPanel onCargar={cargarHistorial} />
           : view === 'optimizar' ? <window.OptimizarPanel />
           : view === 'tools' ? <window.ToolsPanel />
           : view === 'alarmas' && window.AlarmasPanel ? <window.AlarmasPanel />
           : <window.SettingsPanel voiceOn={voiceOn} onVoice={toggleVoz} fx={fx} setFxKey={setFxKey} />}
        </div>
        {view === 'chat' && (
          <window.InputBar value={input} onChange={setInput} onSend={send} onStop={stop} busy={busy}
            onAttach={onAttach} onMic={onMic} adjuntos={adjuntos} grabando={grabando} />
        )}
      </main>
      <window.CommandMenu open={menuOpen} onClose={() => setMenuOpen(false)} items={[
        { label:'Chat', desc:'Volver a la conversación', onClick:()=>setView('chat') },
        { label:'Ajustes', desc:'Configuración general', onClick:()=>setView('settings') },
        { label:'Personajes', desc:'Cambia el personaje activo', onClick:()=>setView('personajes') },
        { label:'Memoria', desc:'Nodos de memoria persistente', onClick:()=>setView('memoria') },
        { label:'Tools', desc:'Herramientas de escritorio', onClick:()=>setView('tools') },
        { label:'Historial', desc:'Conversaciones previas', onClick:()=>setView('historial') },
        { label:'Optimizar', desc:'Rendimiento del modelo', onClick:()=>setView('optimizar') },
        ...(window.AlarmasPanel ? [{ label:'Alarmas', desc:'Alarmas y temporizadores', onClick:()=>setView('alarmas') }] : []),
        { label:'Temporizador rápido', desc:'Un temporizador de 5 minutos', onClick:()=>accionEscritorio('temporizador_rapido', '5') },
        { label:'Pantalla grande', desc:'Lune llena la pantalla (otra vez para salir)', onClick:()=>accionEscritorio('pantalla_grande') },
        { label: bailando ? 'Parar el baile' : 'Bailar', desc:'Lune baila (con música, al ritmo)', on: baile ? bailando : undefined,
          onClick:()=>accionEscritorio('bailar') },
        { label:`Mascota ${mascotaFuera?'ON':'OFF'}`, desc: mascotaFuera ? 'Traer a Lune de vuelta a la ventana' : 'Sacar a Lune al escritorio', on:mascotaFuera, onClick:toggleMascota },
        { label:`Voz ${voiceOn?'ON':'OFF'}`, desc:'Lune lee sus respuestas (la voz se elige en Ajustes)', on:voiceOn, onClick:toggleVoz },
        { label:'Telegram', desc:'Bot sincronizado', on:telegramOn, onClick:toggleTelegram },
        { label:`Llamada ${llamadaOn?'ON':'OFF'}`, desc:'Conversación solo por voz', on:llamadaOn, onClick:toggleLlamada },
        { label:'Limpiar chat', desc:'Borra la conversación actual', danger:true, onClick:clear },
      ]} />
      {toast && <div className="ln-toast" role="status">{toast}</div>}
      {/* Cortes 5/6: la alarma que está sonando, con «Apagar» (bloqueado los primeros segundos) y «Posponer». */}
      {window.AlarmaBanner && <window.AlarmaBanner />}
      {/* Acciones del modelo que piden permiso (señal aprobacion_pedida): modal global
          con cuenta atrás de 60 s; «Sí, hazlo» / «No» → window.lune.resolver_aprobacion. */}
      {window.AprobacionHost && <window.AprobacionHost />}
      {/* Menú radial SVG (extra/apariencia.jsx): F1 o clic derecho sobre la mascota de la barra. */}
      {window.RadialHost && <window.RadialHost onNavegar={setView} onExpresion={expresionRadial}
        onAviso={mostrarToast} mascotaFuera={mascotaFuera} />}
    </div>
  );
}
window.LuneApp = App;
