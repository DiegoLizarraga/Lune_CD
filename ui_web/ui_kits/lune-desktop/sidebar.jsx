/* Lune CD desktop — Sidebar (v9.0) */
const MASCOT = {
  normal:   '../../assets/mascot/anime/lune-composed.png',
  happy:    '../../assets/mascot/anime/lune-happy.png',
  reading:  '../../assets/mascot/anime/lune-thinking.png',
  thinking: '../../assets/mascot/anime/lune-thinking.png',
  typing:   '../../assets/mascot/anime/lune-composed.png',
  error:    '../../assets/mascot/anime/lune-nervous.png',
  angry:    '../../assets/mascot/anime/lune-angry.png',
  surprised:'../../assets/mascot/anime/lune-surprised.png',
  nervous:  '../../assets/mascot/anime/lune-nervous.png',
  wave:     '../../assets/mascot/anime/lune-wave.png',
};

function Sidebar({ provider, onProvider, mascotState }) {
  const { ProviderTab } = window.LUNE;
  return (
    <aside className="ln-sidebar">
      <div className="ln-brand">
        <div className="ln-brand-mark lune-jp">月</div>
        <div className="ln-brand-tx">
          <div className="ln-brand-name">LUNE <span>CD</span></div>
          <div className="ln-brand-sub"><span className="lune-jp">ルネ</span> · HÍBRIDO v9.0</div>
        </div>
      </div>

      <div className="ln-sec-label">// Red Neuronal</div>
      <div className="ln-providers">
        <ProviderTab icon={<window.IconCloud/>} name="Lune AI · Nube" desc="Enrutamiento inteligente" accent="blue"
          active={provider==='cloud'} onClick={()=>onProvider('cloud')} />
        <ProviderTab icon={<window.IconCpu/>} name="Lune AI · Local" desc="Offline · sin red" accent="cyan"
          active={provider==='local'} onClick={()=>onProvider('local')} />
      </div>

      <div className="ln-mascot">
        <div className="ln-mascot-stage">
          <img src={MASCOT[mascotState] || MASCOT.normal} alt="Lune" />
        </div>
      </div>
    </aside>
  );
}
window.Sidebar = Sidebar;
