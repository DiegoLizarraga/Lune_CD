/* Lune CD desktop — Chat surface + reply engine */

const NOW = () => new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });

/* Fake intent engine — mirrors tools.py (web shortcuts, app launch, system info). */
function buildReply(text, provider) {
  const t = text.toLowerCase();
  const open = t.match(/\b(abre|ve a|abrir)\s+(youtube|netflix|wikipedia|spotify|github|gmail)/);
  if (open) {
    const site = open[2];
    return { kind:'tool', tool:{ ok:true, icon:'ext', title:`Abriendo ${site}`, detail:`https://${site}.com — lanzado en tu navegador.` }, asistente:'happy' };
  }
  if (/\bbusca(r)?\b/.test(t)) {
    const q = text.replace(/.*busca(r)?\s*(en\s+\w+)?\s*/i, '').trim() || 'tu consulta';
    return { kind:'tool', tool:{ ok:true, icon:'search', title:'Búsqueda lanzada', detail:`Resultados para “${q}”.` }, asistente:'reading' };
  }
  if (/\b(lanza|abre el programa|abre la app)\b/.test(t)) {
    return { kind:'tool', tool:{ ok:true, icon:'bolt', title:'App lanzada', detail:'Proceso iniciado localmente (0.1s, sin tokens).' }, asistente:'happy' };
  }
  if (/\b(estado del pc|info del sistema|sistema)\b/.test(t)) {
    return { kind:'tool', tool:{ ok:true, icon:'cpu', title:'Estado del sistema', detail:'CPU 18% · RAM 42% · Disco 61% · Red OK' }, asistente:'reading' };
  }
  if (/\b(recuerda|anota)\b/.test(t)) {
    return { text:'Anotado. Lo guardé en memoria — no se me olvida.', asistente:'happy' };
  }
  const canned = [
    'Listo. Lo tengo. ¿Seguimos?',
    'Hecho a mi manera — directa, sin relleno. Dime el siguiente paso.',
    provider==='local'
      ? 'Corriendo en local, cero red, cero costo. Aquí mando yo.'
      : 'Tirando del modelo en la nube. Respuesta lista.',
    'Te dejo lo esencial. Si quieres más profundidad, pídemelo.',
  ];
  return { text: canned[Math.floor(Math.random()*canned.length)], asistente:'happy' };
}
window.buildReply = buildReply;

function ToolCard({ tool }) {
  const { Card } = window.LUNE;
  const Ic = { ext: window.IconExternal, search: window.IconSearch, bolt: window.IconBolt, cpu: window.IconCpu }[tool.icon] || window.IconBolt;
  return (
    <div className="ln-toolrow">
      <Card tone="cyan" tick notch={true} className="ln-toolcard">
        <div className="ln-tool-head">
          <span className="ln-tool-ic"><Ic width={18} height={18} /></span>
          <span className="ln-tool-title">{tool.title}</span>
          <span className="ln-tool-flag">OK · 0.1s</span>
        </div>
        <p className="ln-tool-detail">{tool.detail}</p>
      </Card>
    </div>
  );
}

function TypingIndicator({ provider }) {
  const { Avatar } = window.LUNE;
  return (
    <div className="ln-typing">
      <Avatar src="../../assets/asistente/anime/lune-thinking.png" size="md" ring={provider==='cloud'?'blue':'cyan'} />
      <div className="ln-typing-bubble">
        <span className="ln-dot" /><span className="ln-dot" /><span className="ln-dot" />
      </div>
    </div>
  );
}

function Welcome({ provider, onEjemplo }) {
  const ejemplos = ['abre youtube', 'busca lofi de shibuya', 'estado del pc', 'recuerda que entrego el viernes'];
  const chips = (cls) => (
    <div className={cls}>
      {ejemplos.map((t, i) => (
        <button key={i} type="button" className="ln-chip ln-chip-btn"
          onClick={() => onEjemplo && onEjemplo(t)}>"{t}"</button>
      ))}
    </div>
  );
  // Modo Nube: hero "LUNE ENTRE NUBES" (cielo nocturno, avatar flotando sobre una nube).
  if (provider === 'cloud') {
    const Nube = window.NubeSvg;
    return (
      <div className="nube-hero">
        <div className="nube-avatar-wrap">
          <img className="nube-avatar" src="../../assets/asistente/anime/lune_inicio_ui.png" alt="Lune" />
          {Nube && <Nube className="nube-avatar-cloud" width={150} fill="#f3f8ff" opacity="0.95" />}
        </div>
        <div className="nube-kanji">ルネ起動</div>
        <h1 className="nube-h1">LUNE ENTRE NUBES</h1>
        <p className="nube-p">Tu asistente personal. Memoria persistente, herramientas al instante, modelos en la nube.</p>
        {chips('nube-chips')}
      </div>
    );
  }
  return (
    <div className="ln-welcome">
      <div className="ln-welcome-giant" aria-hidden="true">LUNE</div>
      <div className="ln-welcome-mark">
        <img src="../../assets/asistente/anime/lune_inicio_ui.png" alt="Lune" />
      </div>
      <div className="ln-welcome-jp lune-jp">ルネ起動</div>
      <h1 className="ln-welcome-title">LUNE EN LÍNEA</h1>
      <p className="ln-welcome-sub">
        Tu asistente personal. Memoria persistente, herramientas al instante,
        {provider==='cloud' ? ' modelos en la nube.' : ' 100% local y privada.'}
      </p>
      {chips('ln-welcome-chips')}
    </div>
  );
}

/* Un mensaje del chat. Con React.memo solo se vuelve a pintar el que cambia: cada trozo de la
   respuesta cambia el texto de la última burbuja y el resto del chat no se toca (antes se repintaba
   entero con cada trozo, y el coste crecía con la conversación). app.jsx conserva el mismo objeto
   para los mensajes que no cambian. */
function burbujaIgual(antes, ahora) {
  const a = antes.m, b = ahora.m;
  if (a === b) return true;
  if (!a || !b) return false;
  return a.id === b.id && a.text === b.text && a.streaming === b.streaming && a.role === b.role
    && a.provider === b.provider && a.time === b.time && a.kind === b.kind && a.tool === b.tool;
}
function MensajeChat({ m }) {
  const { ChatBubble, Avatar } = window.LUNE;
  if (m.kind === 'tool') return <ToolCard tool={m.tool} />;
  if (m.role === 'user') return <ChatBubble role="user" time={m.time}>{m.text}</ChatBubble>;
  return (
    <ChatBubble role="bot" provider={m.provider} time={m.time} streaming={m.streaming}
      avatar={<Avatar src={`../../assets/asistente/anime/lune-${m.provider==='cloud'?'happy':'composed'}.png`} size="md" ring={m.provider==='cloud'?'blue':'cyan'} />}>
      {m.text}
    </ChatBubble>
  );
}
const Mensaje = typeof React.memo === 'function' ? React.memo(MensajeChat, burbujaIgual) : MensajeChat;

function ChatStream({ messages, typing, provider, onEjemplo }) {
  const endRef = React.useRef(null);
  React.useEffect(() => { if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight; }, [messages, typing]);
  if (messages.length === 0) {
    return <div className="ln-stream" ref={endRef}><Welcome provider={provider} onEjemplo={onEjemplo} /></div>;
  }
  return (
    <div className="ln-stream" ref={endRef}>
      <div className="ln-stream-inner">
        {messages.map((m) => <Mensaje key={m.id} m={m} />)}
        {typing && <TypingIndicator provider={provider} />}
      </div>
    </div>
  );
}

function InputBar({ value, onChange, onSend, onStop, busy, onAttach, onMic, adjuntos = [], grabando = false }) {
  const { IconButton } = window.LUNE;
  return (
    <div className="ln-inputbar-wrap">
      {adjuntos.length > 0 && (
        <div className="ln-attach-row">
          {adjuntos.map((n, i) => <span key={i} className="ln-chip ln-attach-chip">{n}</span>)}
        </div>
      )}
      <div className="ln-inputbar">
        <IconButton label="Adjuntar" variant="solid" onClick={onAttach}><window.IconClip/></IconButton>
        <IconButton label={grabando ? 'Grabando…' : 'Dictar'} variant={grabando ? 'danger' : 'solid'} onClick={onMic}><window.IconMic/></IconButton>
        <div className="ln-input-wrap">
          <span className="ln-input-glyph">&gt;</span>
          <input
            className="ln-input" value={value} placeholder="Dime qué necesitas… (Enter para enviar)"
            onChange={(e)=>onChange(e.target.value)}
            onKeyDown={(e)=>{ if(e.key==='Enter' && !busy) onSend(); }}
            disabled={busy}
          />
        </div>
        {busy
          ? <IconButton label="Detener" variant="danger" clip onClick={onStop}><window.IconStop/></IconButton>
          : <IconButton label="Enviar" variant="cyan" clip onClick={onSend}><window.IconSend/></IconButton>}
      </div>
    </div>
  );
}

Object.assign(window, { ChatStream, InputBar });
window.LuneChat = { Mensaje, burbujaIgual };   // para los tests (tests/js/chat_web.test.mjs)
