/* Lune CD — Command Menu (Persona 3 Reload style) */
const CMD_COLORS = ['var(--cyan-300)','var(--cyan-400)','var(--cyan-500)','var(--blue-300)','var(--blue-400)','var(--paper)','var(--cyan-400)','var(--blue-300)','var(--cyan-500)','var(--blue-400)','var(--gray-300)'];

function CommandMenu({ open, items, onClose }) {
  const [idx, setIdx] = React.useState(0);
  React.useEffect(() => { if (open) setIdx(0); }, [open]);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowDown') setIdx((i) => (i + 1) % items.length);
      else if (e.key === 'ArrowUp') setIdx((i) => (i - 1 + items.length) % items.length);
      else if (e.key === 'Enter') { items[idx].onClick && items[idx].onClick(); onClose(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, idx, items]);
  if (!open) return null;
  const active = items[idx];
  return (
    <div className="p3-overlay" onClick={onClose}>
      <div className="p3-bigword" aria-hidden="true">コマンド</div>
      <div className="p3-slash-bg" aria-hidden="true"></div>
      <img className="p3-mascot" src="../../assets/mascot/anime/lune-base-cut.png" alt="" />
      <div className="p3-word-vert" aria-hidden="true">LUNE</div>
      <nav className="p3-list" onClick={(e)=>e.stopPropagation()}>
        {items.map((it, i) => (
          <button key={it.label}
            className={`p3-item${i === idx ? ' is-active' : ''}${it.danger ? ' is-danger' : ''}`}
            style={{ '--i': i, '--c': CMD_COLORS[i % CMD_COLORS.length], marginLeft: `${(i % 6) * 26}px` }}
            onMouseEnter={() => setIdx(i)}
            onClick={() => { it.onClick && it.onClick(); onClose(); }}>
            <span className="p3-item-tx">{it.label}</span>
            {it.on != null && <span className={`p3-item-led${it.on ? ' on' : ''}`} />}
          </button>
        ))}
      </nav>
      <div className="p3-cmdinfo" onClick={(e)=>e.stopPropagation()}>
        <div className="p3-cmdinfo-name">{active.label}</div>
        <div className="p3-cmdinfo-line">Command ───</div>
        <div className="p3-cmdinfo-desc">{active.desc}</div>
        <div className="p3-cmdinfo-keys"><b>↵</b> Confirmar&nbsp;&nbsp;<b>Esc</b> Cerrar</div>
      </div>
    </div>
  );
}
window.CommandMenu = CommandMenu;
