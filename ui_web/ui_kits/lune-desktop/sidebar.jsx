/* Lune CD desktop — Sidebar (v10) */

// PNG estático (respaldo si el video de un estado aún no existe).
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

// Estado → nombre base del video (assets/mascot/anime-videos/lune-<base>.mp4).
// Si el clip no existe todavía, cae al idle "composed" y, si tampoco, al PNG.
// v10 — un estado por clip. Los que aún no tienen video caen al idle hasta que
// exista `lune-<estado>.webm` (ver scripts/convertir_mascota.py).
const VID = {
  normal:'composed', thinking:'thinking', happy:'happy', angry:'angry', error:'angry',
  surprised:'surprised', nervous:'nervous', wave:'wave', dismiss:'dismiss',
  sad:'sad', curious:'curious', reading:'curious',
  typing:'working', listening:'listening', talking:'talking',
  laughing:'laughing', bored:'bored',
};
const VID_DIR = '../../assets/mascot/anime-videos/';
const VID_IDLE = VID_DIR + 'lune-composed.webm';

function MascotStage({ state }) {
  const wanted = VID_DIR + 'lune-' + (VID[state] || 'composed') + '.webm';
  const [src, setSrc] = React.useState(wanted);
  const [png, setPng] = React.useState(false);
  React.useEffect(() => { setSrc(wanted); setPng(false); }, [wanted]);

  if (png) return <img src={MASCOT[state] || MASCOT.normal} alt="Lune" />;
  return (
    <video key={src} src={src} autoPlay loop muted playsInline
      onError={() => { if (src !== VID_IDLE) setSrc(VID_IDLE); else setPng(true); }} />
  );
}

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
          <MascotStage state={mascotState} />
        </div>
      </div>
    </aside>
  );
}
window.Sidebar = Sidebar;
