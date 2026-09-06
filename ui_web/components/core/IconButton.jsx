import React from 'react';

const CSS = `
.lune-iconbtn{
  display:inline-flex; align-items:center; justify-content:center;
  flex:none; cursor:pointer; color:var(--text-muted);
  background:transparent; border:var(--bw) solid transparent;
  transition:color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.lune-iconbtn svg{ display:block; }
.lune-iconbtn.sz-sm{ width:32px; height:32px; }
.lune-iconbtn.sz-md{ width:40px; height:40px; }
.lune-iconbtn.sz-lg{ width:48px; height:48px; }
.lune-iconbtn.clip{ clip-path:var(--clip-tr); }
.lune-iconbtn:hover{ color:var(--cyan-400); background:var(--ink-700); }
.lune-iconbtn:active{ transform:translateY(1px); }
.lune-iconbtn:focus-visible{ outline:2px solid var(--cyan-500); outline-offset:1px; }
.lune-iconbtn.v-solid{ background:var(--ink-700); border-color:var(--border-strong); color:var(--text); }
.lune-iconbtn.v-solid:hover{ border-color:var(--cyan-700); color:var(--cyan-400); box-shadow:var(--glow-cyan-sm); }
.lune-iconbtn.v-cyan{ background:var(--cyan-500); color:var(--ink-950); }
.lune-iconbtn.v-cyan:hover{ filter:brightness(1.08); color:var(--ink-950); }
.lune-iconbtn.v-danger{ background:var(--red-500); color:var(--white); }
.lune-iconbtn.is-active{ color:var(--cyan-400); background:var(--ink-700); border-color:var(--cyan-700); }
.lune-iconbtn:disabled{ opacity:.4; cursor:not-allowed; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-iconbtn-css')) {
  const s = document.createElement('style'); s.id = 'lune-iconbtn-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Square icon-only button. Pass an inline SVG / icon node as children. */
export function IconButton({
  children, label, variant = 'ghost', size = 'md', clip = false,
  active = false, className = '', ...rest
}) {
  return (
    <button
      type="button" aria-label={label} title={label}
      className={`lune-iconbtn v-${variant} sz-${size}${clip ? ' clip' : ''}${active ? ' is-active' : ''} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
