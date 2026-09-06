import React from 'react';

const CSS = `
.lune-switch{ display:inline-flex; align-items:center; gap:11px; cursor:pointer; user-select:none; }
.lune-switch.is-disabled{ opacity:.45; cursor:not-allowed; }
.lune-switch-track{
  position:relative; width:46px; height:24px; flex:none;
  background:var(--ink-700); border:var(--bw) solid var(--border-strong);
  clip-path:polygon(5px 0,100% 0,100% 100%,0 100%,0 5px);
  transition:background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.lune-switch-thumb{
  position:absolute; top:2px; left:2px; width:17px; height:17px;
  background:var(--gray-300);
  transition:transform var(--dur) var(--ease-snap), background var(--dur-fast);
}
.lune-switch input{ position:absolute; opacity:0; width:0; height:0; }
.lune-switch input:checked + .lune-switch-track{
  background:var(--cyan-700); border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm);
}
.lune-switch input:checked + .lune-switch-track .lune-switch-thumb{
  transform:translateX(22px); background:var(--cyan-400);
}
.lune-switch input:focus-visible + .lune-switch-track{ outline:2px solid var(--white); outline-offset:2px; }
.lune-switch-label{ font-family:var(--font-sans); font-size:14px; color:var(--text); }
.lune-switch.accent-blue input:checked + .lune-switch-track{ background:var(--blue-700); border-color:var(--blue-500); box-shadow:none; }
.lune-switch.accent-blue input:checked + .lune-switch-track .lune-switch-thumb{ background:var(--blue-400); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-switch-css')) {
  const s = document.createElement('style'); s.id = 'lune-switch-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Angular toggle switch. */
export function Switch({
  checked, defaultChecked, onChange, label, disabled = false,
  accent = 'cyan', className = '', ...rest
}) {
  return (
    <label className={`lune-switch accent-${accent}${disabled ? ' is-disabled' : ''} ${className}`}>
      <input
        type="checkbox" checked={checked} defaultChecked={defaultChecked}
        onChange={onChange} disabled={disabled} {...rest}
      />
      <span className="lune-switch-track"><span className="lune-switch-thumb" /></span>
      {label && <span className="lune-switch-label">{label}</span>}
    </label>
  );
}
