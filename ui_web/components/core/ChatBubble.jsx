import React from 'react';

const CSS = `
.lune-msg{ display:flex; gap:11px; padding:6px 4px; max-width:100%; }
.lune-msg.is-user{ flex-direction:row-reverse; }
.lune-msg-body{ max-width:560px; min-width:0; display:flex; flex-direction:column; gap:4px; }
.lune-msg.is-user .lune-msg-body{ align-items:flex-end; }

.lune-bubble{
  position:relative; padding:11px 15px; font-family:var(--font-sans);
  font-size:14px; line-height:1.55; color:var(--text);
  border:var(--bw) solid var(--border-strong); background:var(--ink-800);
  white-space:pre-wrap; word-break:break-word;
}
/* bot bubble: cut top-left, cyan edge */
.lune-msg.is-bot .lune-bubble{
  clip-path:polygon(0 0, 100% 0, 100% 100%, 11px 100%, 0 calc(100% - 11px));
  border-left:var(--bw-bold) solid var(--cyan-700);
  background:var(--ink-750, var(--ink-800));
}
/* user bubble: cut bottom-right, blue fill */
.lune-msg.is-user .lune-bubble{
  clip-path:polygon(0 0, 100% 0, 100% calc(100% - 11px), calc(100% - 11px) 100%, 0 100%);
  background:linear-gradient(135deg, var(--blue-700), var(--blue-600));
  border-color:var(--blue-500); color:var(--white);
}
.lune-msg.prov-local.is-bot .lune-bubble{ border-left-color:var(--cyan-500); }
.lune-msg.prov-cloud.is-bot .lune-bubble{ border-left-color:var(--blue-500); }

.lune-msg-sender{
  font-family:var(--font-mono); font-weight:700; font-size:10px;
  text-transform:uppercase; letter-spacing:.1em; color:var(--cyan-400);
  display:flex; align-items:center; gap:6px; margin-bottom:1px;
}
.lune-msg.prov-cloud .lune-msg-sender{ color:var(--blue-300); }
.lune-msg-time{ font-family:var(--font-mono); font-size:10px; color:var(--text-faint); padding:0 2px; }
.lune-bubble .caret{ color:var(--cyan-400); font-weight:700; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-chatbubble-css')) {
  const s = document.createElement('style'); s.id = 'lune-chatbubble-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** A single chat row — Lune/user avatar + speech bubble. */
export function ChatBubble({
  children, role = 'bot', provider = 'local', sender, avatar,
  time, streaming = false, className = '', ...rest
}) {
  const isUser = role === 'user';
  const senderLabel = sender ?? (provider === 'cloud' ? 'Lune · Nube' : 'Lune · Local');
  return (
    <div className={`lune-msg is-${isUser ? 'user' : 'bot'} prov-${provider} ${className}`} {...rest}>
      {avatar}
      <div className="lune-msg-body">
        {!isUser && <span className="lune-msg-sender">{senderLabel}</span>}
        <div className="lune-bubble">
          {children}{streaming && <span className="caret">▋</span>}
        </div>
        {time && <span className="lune-msg-time">{time}</span>}
      </div>
    </div>
  );
}
