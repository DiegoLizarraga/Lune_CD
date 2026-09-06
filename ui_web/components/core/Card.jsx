import React from 'react';

const CSS = `
.lune-card{
  position:relative; background:var(--surface); color:var(--text);
  border:var(--bw) solid var(--border-strong);
  clip-path:var(--clip-notch);
  padding:var(--space-6);
}
.lune-card.is-flat{ clip-path:none; }
.lune-card.tone-raised{ background:var(--surface-2); }
.lune-card.tone-cyan{ border-color:var(--cyan-700); box-shadow:var(--glow-cyan-sm); }
.lune-card.tone-blue{ border-color:var(--blue-600); }
.lune-card.tone-yellow{ border-color:var(--yellow-600); }
.lune-card.is-grid{ background-image:var(--tex-grid); background-size:var(--tex-grid-size); }
.lune-card.is-scan::after{
  content:""; position:absolute; inset:0; background:var(--tex-scanline);
  pointer-events:none;
}
/* corner accent tick on the cut corner */
.lune-card.is-tick::before{
  content:""; position:absolute; top:0; right:0; width:14px; height:14px;
  background:var(--accent);
  clip-path:polygon(100% 0, 0 0, 100% 100%);
}
.lune-card-eyebrow{
  font:var(--text-overline); letter-spacing:var(--ls-mega);
  text-transform:uppercase; color:var(--accent); margin:0 0 var(--space-3);
  display:flex; align-items:center; gap:8px;
}
.lune-card-title{
  font-family:var(--font-display); font-weight:700; font-size:var(--fs-h3);
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-strong);
  margin:0 0 var(--space-2);
}
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-card-css')) {
  const s = document.createElement('style'); s.id = 'lune-card-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Notched surface panel — the base container for Lune CD content. */
export function Card({
  children, eyebrow, title, tone = 'default', notch = true,
  grid = false, scan = false, tick = false, className = '', style, ...rest
}) {
  const cls = [
    'lune-card',
    !notch && 'is-flat',
    tone !== 'default' && `tone-${tone}`,
    grid && 'is-grid',
    scan && 'is-scan',
    tick && 'is-tick',
    className,
  ].filter(Boolean).join(' ');
  return (
    <div className={cls} style={style} {...rest}>
      {eyebrow && <p className="lune-card-eyebrow">{eyebrow}</p>}
      {title && <h3 className="lune-card-title">{title}</h3>}
      {children}
    </div>
  );
}
