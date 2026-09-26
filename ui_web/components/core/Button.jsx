import React from 'react';

/* Inject component styles once per document. */
const CSS = `
.lune-btn{
  --_fill: var(--cyan-500);
  --_ink: var(--ink-950);
  position:relative; display:inline-flex; align-items:center; justify-content:center;
  gap:8px; border:none; cursor:pointer; user-select:none; white-space:nowrap;
  font-family:var(--font-display); font-weight:700; text-transform:uppercase;
  letter-spacing:.08em; color:var(--_ink); background:var(--_fill);
  clip-path:polygon(0 0, calc(100% - 11px) 0, 100% 11px, 100% 100%, 0 100%);
  transition:transform var(--dur-fast) var(--ease-snap), filter var(--dur-fast), background var(--dur-fast);
}
.lune-btn::after{ /* hard offset shadow drawn as a sibling layer via box-shadow won't follow clip; use translate trick */ }
.lune-btn:hover{ filter:brightness(1.08) saturate(1.05); }
.lune-btn:active{ transform:translate(3px,3px); }
.lune-btn:focus-visible{ outline:2px solid var(--white); outline-offset:3px; }
.lune-btn:disabled{ cursor:not-allowed; opacity:.4; filter:grayscale(.4); transform:none; }

/* size */
.lune-btn.sz-sm{ height:34px; padding:0 14px; font-size:12px; }
.lune-btn.sz-md{ height:42px; padding:0 20px; font-size:13px; }
.lune-btn.sz-lg{ height:52px; padding:0 28px; font-size:15px; letter-spacing:.1em; }
.lune-btn.is-block{ width:100%; }

/* shadow wrapper keeps the hard print-shadow aligned to clip */
.lune-btn-wrap{ display:inline-flex; position:relative; }
.lune-btn-wrap.is-block{ display:flex; width:100%; }
.lune-btn-wrap::before{
  content:""; position:absolute; inset:0; transform:translate(4px,4px); z-index:0;
  background:var(--ink-950);
  clip-path:polygon(0 0, calc(100% - 11px) 0, 100% 11px, 100% 100%, 0 100%);
}
.lune-btn-wrap .lune-btn{ position:relative; z-index:1; }
.lune-btn-wrap.no-shadow::before{ display:none; }

/* variants */
.lune-btn.is-primary{ --_fill:var(--cyan-500); --_ink:var(--ink-950); }
.lune-btn.is-secondary{ --_fill:var(--blue-500); --_ink:var(--white); }
.lune-btn.is-pop{ --_fill:var(--yellow-500); --_ink:var(--ink-950); }
.lune-btn.is-danger{ --_fill:var(--red-500); --_ink:var(--white); }
.lune-btn.is-ghost{
  background:transparent; color:var(--cyan-500);
  box-shadow:inset 0 0 0 1.5px var(--cyan-500);
}
.lune-btn.is-ghost:hover{ background:rgb(var(--cyan-500-rgb, 0 229 255) / .10); color:var(--cyan-300); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-button-css')) {
  const s = document.createElement('style'); s.id = 'lune-button-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/**
 * Lune CD primary action control. Angular, clipped corner, hard print-shadow.
 */
export function Button({
  children,
  variant = 'primary',   // primary | secondary | pop | ghost | danger
  size = 'md',           // sm | md | lg
  block = false,
  shadow = true,
  leading = null,
  trailing = null,
  disabled = false,
  className = '',
  ...rest
}) {
  const noShadow = !shadow || variant === 'ghost';
  return (
    <span className={`lune-btn-wrap${block ? ' is-block' : ''}${noShadow ? ' no-shadow' : ''}`}>
      <button
        className={`lune-btn is-${variant} sz-${size}${block ? ' is-block' : ''} ${className}`}
        disabled={disabled}
        {...rest}
      >
        {leading}
        {children}
        {trailing}
      </button>
    </span>
  );
}
