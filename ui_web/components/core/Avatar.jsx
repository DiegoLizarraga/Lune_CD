import React from 'react';

const CSS = `
.lune-avatar{
  position:relative; display:inline-flex; align-items:center; justify-content:center;
  flex:none; overflow:hidden; background:var(--ink-700);
  border:var(--bw) solid var(--border-strong);
  font-family:var(--font-display); font-weight:700; color:var(--text);
  clip-path:var(--clip-tr);
}
.lune-avatar img{ width:100%; height:100%; object-fit:cover; object-position:top center; }
.lune-avatar.sz-sm{ width:30px; height:30px; font-size:12px; }
.lune-avatar.sz-md{ width:38px; height:38px; font-size:14px; }
.lune-avatar.sz-lg{ width:52px; height:52px; font-size:18px; }
.lune-avatar.sz-xl{ width:72px; height:72px; font-size:24px; }
.lune-avatar.ring-cyan{ border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm); }
.lune-avatar.ring-blue{ border-color:var(--blue-500); }
.lune-avatar.ring-yellow{ border-color:var(--yellow-500); }
.lune-avatar.is-bot{ background:linear-gradient(135deg,var(--blue-700),var(--cyan-700)); }
.lune-avatar-dot{
  position:absolute; right:-2px; bottom:-2px; width:11px; height:11px;
  border:2px solid var(--bg); background:var(--cyan-500);
}
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-avatar-css')) {
  const s = document.createElement('style'); s.id = 'lune-avatar-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Clipped avatar — Lune's portrait, initials, or bot mark. */
export function Avatar({
  src, alt = '', initials, bot = false, size = 'md', ring,
  online = false, className = '', ...rest
}) {
  const cls = [
    'lune-avatar', `sz-${size}`, ring && `ring-${ring}`, bot && 'is-bot', className,
  ].filter(Boolean).join(' ');
  return (
    <span className={cls} {...rest}>
      {src ? <img src={src} alt={alt} /> : (initials || (bot ? '☾' : '?'))}
      {online && <span className="lune-avatar-dot" />}
    </span>
  );
}
