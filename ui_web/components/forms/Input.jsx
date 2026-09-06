import React from 'react';

const CSS = `
.lune-field{ display:flex; flex-direction:column; gap:7px; width:100%; }
.lune-field-label{
  font:var(--text-overline); letter-spacing:var(--ls-mega);
  text-transform:uppercase; color:var(--text-dim);
  display:flex; align-items:center; gap:6px;
}
.lune-field-label .req{ color:var(--cyan-500); }
.lune-input-wrap{ position:relative; display:flex; align-items:center; }
.lune-input-wrap .lead{
  position:absolute; left:12px; display:flex; color:var(--text-dim);
  font-family:var(--font-mono); font-size:13px; pointer-events:none;
}
.lune-input, .lune-textarea{
  width:100%; font-family:var(--font-sans); font-size:14px; color:var(--text);
  background:var(--ink-900); border:var(--bw) solid var(--border);
  padding:11px 13px; outline:none;
  clip-path:var(--clip-tr);
  transition:border-color var(--dur-fast), box-shadow var(--dur-fast), background var(--dur-fast);
}
.lune-input{ height:44px; }
.lune-input.has-lead{ padding-left:34px; }
.lune-textarea{ resize:vertical; min-height:88px; line-height:1.5; }
.lune-input::placeholder, .lune-textarea::placeholder{ color:var(--text-faint); }
.lune-input:hover, .lune-textarea:hover{ border-color:var(--border-bright); }
.lune-input:focus, .lune-textarea:focus{
  border-color:var(--cyan-500); background:var(--ink-850);
  box-shadow:var(--glow-cyan-sm);
}
.lune-field.is-error .lune-input,
.lune-field.is-error .lune-textarea{ border-color:var(--red-500); }
.lune-input:disabled, .lune-textarea:disabled{ opacity:.45; cursor:not-allowed; }
.lune-field-hint{ font:var(--text-data); font-size:11px; color:var(--text-faint); }
.lune-field.is-error .lune-field-hint{ color:var(--red-500); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-input-css')) {
  const s = document.createElement('style'); s.id = 'lune-input-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Text input with optional label, leading glyph, hint and error state. */
export function Input({
  label, required = false, leading = null, hint, error = false,
  textarea = false, className = '', id, ...rest
}) {
  const fid = id || (label ? `f-${String(label).replace(/\s+/g, '-').toLowerCase()}` : undefined);
  return (
    <div className={`lune-field${error ? ' is-error' : ''} ${className}`}>
      {label && (
        <label className="lune-field-label" htmlFor={fid}>
          {label}{required && <span className="req">*</span>}
        </label>
      )}
      {textarea ? (
        <textarea id={fid} className="lune-textarea" {...rest} />
      ) : (
        <div className="lune-input-wrap">
          {leading && <span className="lead">{leading}</span>}
          <input id={fid} className={`lune-input${leading ? ' has-lead' : ''}`} {...rest} />
        </div>
      )}
      {hint && <span className="lune-field-hint">{hint}</span>}
    </div>
  );
}
