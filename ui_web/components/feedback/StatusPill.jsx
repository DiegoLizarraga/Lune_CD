import React from 'react';

const CSS = `
.lune-status{
  display:inline-flex; align-items:center; gap:7px;
  font-family:var(--font-mono); font-weight:700; font-size:11px;
  text-transform:uppercase; letter-spacing:.08em; color:var(--text-muted);
  padding:5px 11px 5px 9px; background:var(--ink-800);
  border:var(--bw) solid var(--border-strong); border-radius:var(--radius-pill);
}
.lune-status .led{
  width:9px; height:9px; flex:none; border-radius:50%;
  background:var(--gray-400); position:relative;
}
.lune-status.s-live .led{ background:var(--cyan-500); }
/* El pulso es un ::after que crece y se apaga (transform + opacity: lo compone la GPU sin
   repintar); con box-shadow el hilo principal repintaba en cada frame. */
.lune-status.s-live .led::after{ content:""; position:absolute; inset:0; border-radius:50%;
  background:rgb(var(--cyan-500-rgb, 0 229 255) / .55); pointer-events:none;
  animation:lune-pulse 1.8s var(--ease-out) infinite; }
.lune-status.s-busy .led{ background:var(--yellow-500); }
.lune-status.s-error .led{ background:var(--red-500); }
.lune-status.s-off .led{ background:var(--gray-500); }
.lune-status.s-live{ color:var(--cyan-300); border-color:var(--cyan-700); }
.lune-status.s-busy{ color:var(--yellow-500); border-color:var(--yellow-600); }
.lune-status.s-error{ color:var(--red-500); border-color:var(--red-600); }
@keyframes lune-pulse{
  0%{ transform:scale(1); opacity:1; }
  70%{ transform:scale(2.6); opacity:0; }
  100%{ transform:scale(2.6); opacity:0; }
}
@media (prefers-reduced-motion: reduce){ .lune-status .led, .lune-status .led::after{ animation:none !important; } .lune-status .led::after{ display:none; } }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-status-css')) {
  const s = document.createElement('style'); s.id = 'lune-status-css'; s.textContent = CSS;
  document.head.appendChild(s);
}

/** Pill with pulsing LED indicating a live/busy/error/off state. */
export function StatusPill({ status = 'live', children, className = '', ...rest }) {
  const label = children ?? { live: 'Listo', busy: 'Procesando', error: 'Error', off: 'Offline' }[status];
  return (
    <span className={`lune-status s-${status} ${className}`} {...rest}>
      <span className="led" />{label}
    </span>
  );
}
