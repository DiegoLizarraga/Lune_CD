import React from 'react';

const CSS = `
.lune-provtab{
  position:relative; display:flex; align-items:center; gap:11px; width:100%;
  padding:10px 12px; cursor:pointer; text-align:left;
  background:transparent; border:var(--bw) solid transparent;
  color:var(--text-muted);
  clip-path:var(--clip-tr);
  transition:background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}
.lune-provtab:hover{ background:var(--ink-700); color:var(--text); }
.lune-provtab-ic{
  width:34px; height:34px; flex:none; display:flex; align-items:center; justify-content:center;
  background:var(--ink-700); border:var(--bw) solid var(--border-strong);
  clip-path:var(--clip-tr); color:var(--text-muted);
}
.lune-provtab-ic svg{ display:block; }
.lune-provtab-tx{ display:flex; flex-direction:column; gap:1px; min-width:0; }
.lune-provtab-name{ font-family:var(--font-display); font-weight:700; font-size:13px; text-transform:uppercase; letter-spacing:.03em; }
.lune-provtab-desc{ font-family:var(--font-mono); font-size:10px; color:var(--text-faint); text-transform:uppercase; letter-spacing:.05em; }
.lune-provtab-led{ margin-left:auto; width:8px; height:8px; flex:none; border-radius:50%; background:var(--gray-600); }

/* active — cyan (local) */
.lune-provtab.is-active.accent-cyan{ background:rgba(0,229,255,.10); border-color:var(--cyan-700); color:var(--cyan-300); }
.lune-provtab.is-active.accent-cyan .lune-provtab-ic{ background:var(--cyan-500); color:var(--ink-950); border-color:var(--cyan-400); }
.lune-provtab.is-active.accent-cyan .lune-provtab-name{ color:var(--cyan-300); }
.lune-provtab.is-active.accent-cyan .lune-provtab-led{ background:var(--cyan-500); box-shadow:var(--glow-cyan-sm); }
/* active — blue (cloud) */
.lune-provtab.is-active.accent-blue{ background:rgba(30,85,255,.12); border-color:var(--blue-600); color:var(--blue-300); }
.lune-provtab.is-active.accent-blue .lune-provtab-ic{ background:var(--blue-500); color:var(--white); border-color:var(--blue-400); }
.lune-provtab.is-active.accent-blue .lune-provtab-name{ color:var(--blue-300); }
.lune-provtab.is-active.accent-blue .lune-provtab-led{ background:var(--blue-400); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-provtab-css')) {
  const s = document.createElement('style'); s.id = 'lune-provtab-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Sidebar provider selector row (Nube / Local). */
export function ProviderTab({
  icon, name, desc, accent = 'cyan', active = false, onClick, className = '', ...rest
}) {
  return (
    <button
      type="button"
      className={`lune-provtab accent-${accent}${active ? ' is-active' : ''} ${className}`}
      onClick={onClick} aria-pressed={active} {...rest}
    >
      <span className="lune-provtab-ic">{icon}</span>
      <span className="lune-provtab-tx">
        <span className="lune-provtab-name">{name}</span>
        <span className="lune-provtab-desc">{desc}</span>
      </span>
      <span className="lune-provtab-led" />
    </button>
  );
}
