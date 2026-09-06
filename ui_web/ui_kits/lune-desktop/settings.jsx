/* Lune CD desktop — Settings panel */
const MOONS = [
  { l:'3%',  s:34, m:1, d:'11s', dl:'0s',    o:.55 }, { l:'9%',  s:16, m:0, d:'9s',  dl:'-4s',  o:.7 },
  { l:'15%', s:52, m:1, d:'14s', dl:'-8s',   o:.35 }, { l:'22%', s:20, m:0, d:'10s', dl:'-2s',  o:.6 },
  { l:'28%', s:28, m:1, d:'12s', dl:'-6s',   o:.5 },  { l:'36%', s:14, m:0, d:'8s',  dl:'-5s',  o:.65 },
  { l:'44%', s:40, m:1, d:'15s', dl:'-11s',  o:.3 },  { l:'52%', s:18, m:0, d:'9.5s',dl:'-1s',  o:.7 },
  { l:'60%', s:24, m:1, d:'11s', dl:'-7s',   o:.55 }, { l:'68%', s:46, m:0, d:'16s', dl:'-13s', o:.28 },
  { l:'75%', s:16, m:1, d:'8.5s',dl:'-3s',   o:.7 },  { l:'82%', s:30, m:0, d:'12s', dl:'-9s',  o:.5 },
  { l:'89%', s:22, m:1, d:'10s', dl:'-5.5s', o:.6 },  { l:'95%', s:38, m:0, d:'14s', dl:'-10s', o:.35 },
];
const FIXED = [
  { t:'-3%', l:'-2%',  s:74, m:1, r:-14 }, { t:'2%',  l:'6%',  s:40, m:0, r:20 },
  { t:'9%',  l:'1%',   s:52, m:0, r:-30 }, { t:'15%', l:'-3%', s:88, m:1, r:38 },
  { t:'23%', l:'4%',   s:30, m:0, r:10 },  { t:'-4%', l:'88%', s:80, m:1, r:22 },
  { t:'4%',  l:'94%',  s:44, m:0, r:-18 }, { t:'12%', l:'89%', s:58, m:1, r:-40 },
  { t:'20%', l:'96%',  s:34, m:0, r:30 },  { t:'29%', l:'92%', s:48, m:1, r:12 },
];
function MoonField() {
  return (
    <div className="p5-moonfield" aria-hidden="true">
      <span className="p5-streak" style={{ top:'26%', left:'-10%', animationDelay:'0s' }} />
      <span className="p5-streak" style={{ top:'58%', left:'-20%', animationDelay:'-5s' }} />
      {FIXED.map((f, i) => (
        <span key={'f'+i} className={(f.m ? 'p5-moon' : 'p5-star') + ' p5-fix'} style={{
          top:f.t, left:f.l, width:f.s, height:f.s,
          '--r':`${f.r}deg`, animationDelay:`${-i * .7}s`,
        }} />
      ))}
      {MOONS.map((m, i) => (
        <span key={i} className={m.m ? 'p5-moon' : 'p5-star'} style={{
          left:m.l, width:m.s, height:m.s, '--o':m.o,
          animationDuration:m.d, animationDelay:m.dl,
        }} />
      ))}
      <div className="p5-horizon" />
      <div className="p5-lune-sil">
        <div className="p5-bubble">¿Qué ajustamos hoy?</div>
        <img src="../../assets/mascot/anime/lune-base-cut.png" alt="" />
      </div>
    </div>
  );
}

const CFG_DEMO = {
  openrouter_key:'', openrouter_model:'openrouter/auto',
  ollama_url:'http://localhost:11434', ollama_model:'',
  telegram_token:'', nombre:'Lune',
  system_prompt:'Eres Lune. Directa, con personalidad y filo. Sin relleno, sin emoji.',
  voz:false, memoria:true, acciones_ia:true,
};

function SettingsPanel({ voiceOn, onVoice, fx = { bg:true, sweep:true, micro:true }, setFxKey = () => () => {} }) {
  const { Card, Input, Switch, Button, Badge } = window.LUNE;
  const [cfg, setCfg] = React.useState(null);
  const [msg, setMsg] = React.useState('');

  React.useEffect(() => {
    if (window.lune) window.lune.get_config((j) => { try { setCfg(JSON.parse(j)); } catch(e){ setCfg({ ...CFG_DEMO }); } });
    else setCfg({ ...CFG_DEMO });
  }, []);

  const set   = (k) => (e) => setCfg((c) => ({ ...c, [k]: (e && e.target) ? e.target.value : e }));
  const setBl = (k) => (e) => setCfg((c) => ({ ...c, [k]: !!(e && e.target ? e.target.checked : e) }));
  const guardar = () => {
    if (!cfg) return;
    if (!window.lune) { setMsg('Demo · sin backend'); setTimeout(()=>setMsg(''),2500); return; }
    window.lune.guardar_config(JSON.stringify(cfg), (r) => {
      let ok = true; try { ok = JSON.parse(r).ok; } catch(e){}
      setMsg(ok ? 'Guardado en datos.json' : 'Error al guardar'); setTimeout(()=>setMsg(''), 2800);
    });
  };

  const c = cfg || CFG_DEMO;
  return (
    <div className="ln-settings">
      {fx.bg && <MoonField />}
      <div className="ln-settings-inner">
        <header className="ln-settings-head">
          <div className="lune-overline">// Panel de Control</div>
          <h2 className="ln-settings-title"><span>CONFIGURACIÓN GENERAL</span></h2>
        </header>

        <Card eyebrow={<><window.IconCloud width={13} height={13}/> Red Neuronal · Nube</>} title="OpenRouter" tone="blue" tick>
          <div className="ln-settings-grid">
            <Input label="API Key de OpenRouter" type="password" value={c.openrouter_key||''} onChange={set('openrouter_key')} hint="Se guarda localmente en datos.json" />
            <Input label="Modelo" value={c.openrouter_model||''} onChange={set('openrouter_model')} hint="openrouter/auto enruta solo" />
          </div>
        </Card>

        <Card eyebrow={<><window.IconCpu width={13} height={13}/> Red Neuronal · Local</>} title="Ollama" tone="cyan" tick>
          <div className="ln-settings-grid">
            <Input label="Servidor" value={c.ollama_url||''} onChange={set('ollama_url')} hint="http://localhost:11434 o una IP de tu red" />
            <Input label="Modelo local" value={c.ollama_model||''} onChange={set('ollama_model')} hint="p. ej. qwen2.5:7b" />
          </div>
        </Card>

        <Card eyebrow={<><window.IconTelegram width={13} height={13}/> Integración</>} title="Telegram" tone="blue">
          <Input label="Token del Bot" type="password" value={c.telegram_token||''} onChange={set('telegram_token')} hint="@BotFather → /newbot" />
        </Card>

        <Card eyebrow={<><window.IconBrain width={13} height={13}/> Comportamiento</>} title="Personalidad">
          <Input label="Nombre del asistente" value={c.nombre||''} onChange={set('nombre')} />
          <div style={{height:14}} />
          <Input label="System Prompt" textarea rows={3} value={c.system_prompt||''} onChange={set('system_prompt')} />
          <div style={{height:18}} />
          <div className="ln-toggle-row">
            <Switch label="Voz (edge-tts · es-MX)" checked={voiceOn} onChange={onVoice} />
            <Switch label="Memoria persistente" checked={!!c.memoria} onChange={setBl('memoria')} accent="blue" />
            <Switch label="Herramientas de escritorio" checked={!!c.acciones_ia} onChange={setBl('acciones_ia')} />
          </div>
        </Card>

        <Card eyebrow={<><window.IconBolt width={13} height={13}/> Rendimiento</>} title="Efectos visuales" tone="yellow">
          <p style={{margin:'0 0 14px', font:'var(--text-data)', fontSize:12, color:'var(--text-dim)'}}>Desactiva efectos para consumir menos recursos en equipos modestos.</p>
          <div className="ln-toggle-row">
            <Switch label="Fondo animado (fragmentos y grid)" checked={fx.bg} onChange={setFxKey('bg')} />
            <Switch label="Barrido al cambiar de vista" checked={fx.sweep} onChange={setFxKey('sweep')} accent="blue" />
            <Switch label="Micro-animaciones (burbujas, hover)" checked={fx.micro} onChange={setFxKey('micro')} />
          </div>
        </Card>

        <div className="ln-settings-foot">
          <Badge variant="ink" outline>{msg || 'datos.json'}</Badge>
          <Button variant="primary" size="lg" onClick={guardar}>Guardar configuración</Button>
        </div>
      </div>
    </div>
  );
}
window.SettingsPanel = SettingsPanel;
