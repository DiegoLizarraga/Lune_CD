import React from 'react';

const CSS = `
.lune-badge{
  display:inline-flex; align-items:center; gap:5px;
  font-family:var(--font-mono); font-weight:700; font-size:10px;
  text-transform:uppercase; letter-spacing:.1em; line-height:1;
  padding:4px 9px; white-space:nowrap;
  clip-path:var(--clip-tr);
  border:var(--bw) solid transparent;
}
.lune-badge.v-cyan{ background:var(--cyan-500); color:var(--ink-950); }
.lune-badge.v-blue{ background:var(--blue-500); color:var(--white); }
.lune-badge.v-yellow{ background:var(--yellow-500); color:var(--ink-950); }
.lune-badge.v-danger{ background:var(--red-500); color:var(--white); }
.lune-badge.v-ink{ background:var(--ink-700); color:var(--text-muted); border-color:var(--border-strong); }
/* outline variants */
.lune-badge.is-outline{ background:transparent; }
.lune-badge.is-outline.v-cyan{ color:var(--cyan-400); border-color:var(--cyan-700); }
.lune-badge.is-outline.v-blue{ color:var(--blue-300); border-color:var(--blue-600); }
.lune-badge.is-outline.v-yellow{ color:var(--yellow-500); border-color:var(--yellow-600); }
.lune-badge.is-outline.v-danger{ color:var(--red-500); border-color:var(--red-600); }
.lune-badge .jp{ font-family:var(--font-jp); font-weight:900; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-badge-css')) {
  const s = document.createElement('style'); s.id = 'lune-badge-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Compact tag/label chip. */
export function Badge({ children, variant = 'cyan', outline = false, className = '', ...rest }) {
  return (
    <span className={`lune-badge v-${variant}${outline ? ' is-outline' : ''} ${className}`} {...rest}>
      {children}
    </span>
  );
}
