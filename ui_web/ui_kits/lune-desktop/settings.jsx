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
        <img src="../../assets/asistente/anime/lune-base-cut.png" alt="" />
      </div>
    </div>
  );
}

const CFG_DEMO = {
  openrouter_key:'', openrouter_model:'openrouter/auto',
  ollama_url:'http://localhost:11434', ollama_model:'',
  telegram_token:'', telegram_admin_id:'', telegram_ordenes_pc:false, nombre:'Lune',
  system_prompt:'Eres Lune. Directa, con personalidad y filo. Sin relleno, sin emoji.',
  voz:false, memoria:true, acciones_ia:true,
  asistente_render:'animado', interfaz_modo:'web',
  vrm_webengine:false, vrm_modelos:[], vrm_archivo:'', vrm_tamano:'normal', vrm_encuadre:'retrato', vrm_fantasma_auto:true, dormir_min:10,
  seguir_cursor:true,
  autoinicio:false, aburrimiento_min:10,
  dispositivo_entrada:'', dispositivo_salida:'', modelo_whisper:'base', voz_idioma:'es',
  // Voz de salida (VozCard) y sonidos de la asistente (PackSonidosCard)
  motor_salida:'auto', edge_voz:'es-MX-DaliaNeural', edge_rate:'+0%', edge_pitch:'+0Hz', gtts_tld:'com.mx', kokoro_voz:'ef_dora',
  pack_sonidos:'default', volumen_sfx:0.7,
  // API compatible con OpenAI (CompatCard) y parámetros del modelo (AvanzadoCard)
  compat_url:'', compat_key:'', compat_model:'',
  preset_muestreo:'equilibrado', temperatura:0.7, top_p:null, top_k:null, min_p:null, repeat_penalty:null,
  num_predict:0, seed:-1, ollama_num_ctx:8192,
};
/* Campo de clave (OpenRouter, Telegram). get_config trae una máscara, no la clave: con
   LuneIA.CampoClave (extra/ia_avanzada.jsx) lo que se teclea SUSTITUYE la máscara entera en vez de
   añadirse detrás; sin tocarlo se manda la máscara y el puente conserva la guardada. Sin ese
   módulo, un Input de contraseña normal (el puente también ignora «máscara + lo tecleado»). */
function CampoClaveAjustes(props) {
  const L = window.LuneIA;
  if (L && typeof L.CampoClave === 'function') return <L.CampoClave {...props} />;
  const { Input } = window.LUNE;
  return <Input id={props.id} label={props.label} type="password" autoComplete="off" spellCheck={false}
    value={props.value} onChange={props.onChange} hint={props.hint} />;
}

const AUDIO_DEMO = { entradas:[], salidas:[], faltan:[], modelos_whisper:['tiny','base','small','medium','large-v3'], modelos_descargados:[] };

/* «Guardar configuración» manda SOLO lo que cambiaste en Ajustes: cada clave de `cfg` cuyo
   valor no es el de la foto que dio get_config al abrir (o al último guardado). Así no se
   revierte lo cambiado fuera con Ajustes abierto (tamaño o encuadre de la asistente desde el
   radial o la bandeja, «Arrancar con Windows» desde la bandeja…). `fuera`: claves que no
   se mandan nunca (solo lectura o con su propio interruptor). */
const AJUSTES_SOLO_LECTURA = ['voz', 'vrm_modelos', 'vrm_webengine', 'asistente_fuera'];
function cambiosAjustes(foto, cfg, fuera = AJUSTES_SOLO_LECTURA) {
  const out = {};
  const base = foto || {};
  for (const k of Object.keys(cfg || {})) {
    if (fuera.includes(k)) continue;
    const tenia = Object.prototype.hasOwnProperty.call(base, k);
    if (!tenia || JSON.stringify(base[k]) !== JSON.stringify(cfg[k])) out[k] = cfg[k];
  }
  return out;
}
window.cambiosAjustes = cambiosAjustes;

/* Guía de Ollama: en este equipo o en otro de la red (el "?" junto a Ollama). */
function AyudaOllama({ onClose }) {
  const { Button, Badge } = window.LUNE;
  const [tab, setTab] = React.useState('local');
  const Code = ({ children }) => <pre className="ln-code">{children}</pre>;
  const copiar = (t) => { try { navigator.clipboard.writeText(t); } catch (e) {} };
  return (
    <div className="ln-modal-bg" onClick={onClose}>
      <div className="ln-modal" onClick={(e)=>e.stopPropagation()} role="dialog" aria-label="Cómo configurar Ollama">
        <div className="lune-overline">// Modelo local</div>
        <h3 className="ln-modal-title">¿Dónde va a correr Ollama?</h3>
        <div className="ln-modal-tabs">
          <Button variant={tab==='local'?'primary':'ghost'} size="sm" onClick={()=>setTab('local')}>En este equipo</Button>
          <Button variant={tab==='red'?'primary':'ghost'} size="sm" onClick={()=>setTab('red')}>En otro equipo de la red</Button>
        </div>

        {tab==='local' ? (
          <div className="ln-modal-body">
            <p>Lo más simple: Ollama y Lune en la misma PC.</p>
            <ol>
              <li>Instala Ollama desde <b>ollama.com/download</b> (Windows, macOS o Linux).</li>
              <li>Baja un modelo (una vez, necesita internet). Ejemplos: <Code>ollama pull qwen2.5:7b</Code> <Code>ollama pull llama3.1</Code>
                Para que Lune <b>vea imágenes</b>: <Code>ollama pull llava</Code></li>
              <li>Deja <b>Servidor</b> en <code>http://localhost:11434</code>, pulsa <b>Guardar</b> y luego elige el modelo en <b>Modelo local</b>.</li>
            </ol>
            <p className="ln-modal-nota">Si el modelo tarda en arrancar en frío, sube el <i>Timeout</i>. <i>keep_alive</i> decide cuánto se queda cargado en VRAM.</p>
          </div>
        ) : (
          <div className="ln-modal-body">
            <p>Tienes una PC potente y quieres que esta use su modelo. Ollama corre allá; Lune se conecta por Wi-Fi.</p>
            <ol>
              <li><b>En la PC potente</b>: instala Ollama y haz que escuche en la red (no solo en localhost):
                <Code>setx OLLAMA_HOST 0.0.0.0:11434</Code>
                <span className="ln-modal-nota">Cierra y vuelve a abrir Ollama para que lo tome. En Linux/macOS: <code>export OLLAMA_HOST=0.0.0.0:11434</code> y <code>ollama serve</code>.</span></li>
              <li><b>Firewall</b> de esa PC: permite el puerto <b>11434</b> (TCP) en la red privada.</li>
              <li>Averigua su <b>IP local</b> (en esa PC: <code>ipconfig</code> → "Dirección IPv4", algo como <code>192.168.1.50</code>).</li>
              <li><b>Aquí en Lune</b>: en <b>Servidor</b> pon <code>http://192.168.1.50:11434</code> (con su IP), Guardar, y elige el modelo.</li>
              <li>Que no se duerma: en la PC potente, PowerShell como administrador:
                <Code>powercfg /change standby-timeout-ac 0{'\n'}powercfg /change hibernate-timeout-ac 0</Code>
                <span className="ln-modal-nota">Solo afecta enchufada; la pantalla puede apagarse igual.</span></li>
            </ol>
            <p className="ln-modal-nota">⚠️ No expongas Ollama a internet: no trae autenticación. Solo en tu red local.
              Si el modelo remoto falla, Lune se pasa sola a la nube (OpenRouter) para no dejarte colgado.</p>
          </div>
        )}
        <div className="ln-modal-foot">
          <Badge variant="ink" outline>Guía de Lune</Badge>
          <Button variant="primary" size="sm" onClick={onClose}>Entendido</Button>
        </div>
      </div>
    </div>
  );
}

/* Opciones de la asistente 3D (VRM): modelo por defecto, tamaño, encuadre, sueño y clics. */
function VrmOpciones({ c, set, setBl, setCfg }) {
  const { Button, Switch, Input } = window.LUNE;
  const modelos = c.vrm_modelos || [];
  const importar = () => {
    if (!window.lune) return;
    window.lune.vrm_importar((j) => {
      let r = {}; try { r = JSON.parse(j); } catch (e) {}
      if (r.ok) setCfg((k) => ({ ...k, vrm_modelos: r.modelos || modelos, vrm_archivo: r.archivo || k.vrm_archivo }));
    });
  };
  const nota = { margin:'6px 0 0', font:'var(--text-data)', fontSize:11, color:'var(--text-faint)' };
  return (
    <div style={{ marginTop: 14 }}>
      {modelos.length === 0 && !c.vrm_archivo && (
        <p style={{ ...nota, color:'var(--yellow-500)', margin:'0 0 10px' }}>
          No hay ningún modelo: impórtame un archivo .vrm aquí (o suéltalo en mi carpeta de modelos 3D: la ves en la Biblioteca de modelos 3D).
        </p>
      )}
      <div className="ln-settings-grid">
        <div className="lune-field">
          <label className="lune-field-label" htmlFor="f-vrm-archivo">Modelo por defecto</label>
          <select id="f-vrm-archivo" className="lune-input" value={c.vrm_archivo || ''} onChange={set('vrm_archivo')}>
            <option value="">El primero de mi carpeta de modelos</option>
            {modelos.map((m) => <option key={m} value={m}>{m}</option>)}
            {c.vrm_archivo && !modelos.includes(c.vrm_archivo) && <option value={c.vrm_archivo}>{c.vrm_archivo}</option>}
          </select>
          <span className="lune-field-hint">Cada personaje puede traer el suyo (Personajes → Modelo 3D).</span>
        </div>
        <div>
          <div className="lune-overline" style={{ marginBottom: 6 }}>Añadir modelo</div>
          <Button variant="ghost" size="sm" onClick={importar}>Importar .vrm…</Button>
          <p style={nota}>Se copia a mi carpeta de modelos 3D. Hay modelos gratuitos en VRoid Hub y Booth (respeta su licencia).</p>
        </div>
      </div>
      <div style={{ height: 12 }} />
      <div className="ln-settings-grid">
        <div>
          <div className="lune-overline" style={{ marginBottom: 6 }}>Tamaño</div>
          <div className="ln-seg-row">
            {[['pequeno','Pequeña'],['normal','Normal'],['grande','Grande']].map(([k, t]) => (
              <Button key={k} variant={(c.vrm_tamano||'normal')===k?'primary':'ghost'} size="sm" onClick={()=>set('vrm_tamano')(k)}>{t}</Button>
            ))}
          </div>
        </div>
        <div>
          <div className="lune-overline" style={{ marginBottom: 6 }}>Encuadre</div>
          <div className="ln-seg-row">
            {[['retrato','Retrato'],['cuerpo','Cuerpo entero']].map(([k, t]) => (
              <Button key={k} variant={(c.vrm_encuadre||'retrato')===k?'primary':'ghost'} size="sm" onClick={()=>set('vrm_encuadre')(k)}>{t}</Button>
            ))}
          </div>
        </div>
      </div>
      <div style={{ height: 12 }} />
      <div className="ln-settings-grid">
        <Input label="Se duerme tras (minutos sin tocarla ni hablarle)" type="number" min="0" value={c.dormir_min ?? 10}
          onChange={set('dormir_min')} hint="0 = nunca. Se despierta al hacerle clic, arrastrarla o cuando Lune responde." />
        <div className="ln-toggle-row" style={{ alignItems:'flex-end', paddingBottom: 22 }}>
          <Switch label="Los clics pasan al escritorio donde no hay avatar" checked={c.vrm_fantasma_auto !== false} onChange={setBl('vrm_fantasma_auto')} />
        </div>
      </div>
    </div>
  );
}

function SettingsPanel({ voiceOn, onVoice, fx = { bg:true, sweep:true, micro:true, quieta:true }, setFxKey = () => () => {} }) {
  const { Card, Input, Switch, Button, Badge } = window.LUNE;
  const [cfg, setCfg] = React.useState(null);
  const [msg, setMsg] = React.useState('');
  const [ayudaOllama, setAyudaOllama] = React.useState(false);
  // La foto de get_config (y de lo ya guardado): lo que no cambiaste no se manda.
  const foto = React.useRef(null);

  React.useEffect(() => {
    if (window.lune) window.lune.get_config((j) => {
      try { const r = JSON.parse(j); foto.current = { ...r }; setCfg(r); } catch(e){ setCfg({ ...CFG_DEMO }); }
    });
    else setCfg({ ...CFG_DEMO });
  }, []);

  const set   = (k) => (e) => setCfg((c) => ({ ...c, [k]: (e && e.target) ? e.target.value : e }));
  const setBl = (k) => (e) => setCfg((c) => ({ ...c, [k]: !!(e && e.target ? e.target.checked : e) }));
  // Guarda lo cambiado (cambiosAjustes) y, si salió bien, la foto pasa a tenerlo.
  const guardarCambios = (payload, alTerminar) => {
    window.lune.guardar_config(JSON.stringify(payload), (r) => {
      let ok = true; try { ok = JSON.parse(r).ok; } catch(e){}
      if (ok) foto.current = { ...(foto.current || {}), ...payload };
      alTerminar(ok);
    });
  };
  const guardar = () => {
    if (!cfg) return;
    if (!window.lune) { setMsg('Demo · sin backend'); setTimeout(()=>setMsg(''),2500); return; }
    guardarCambios(cambiosAjustes(foto.current, cfg), (ok) => {
      setMsg(ok ? 'Guardado en datos.json' : 'Error al guardar'); setTimeout(()=>setMsg(''), 2800);
    });
  };
  // Modo de interfaz: se aplica al instante. Primero se guarda lo pendiente de Ajustes
  // (la ventana nueva lo lee de disco) y luego se pide el cambio; el modo lo escribe el
  // gestor (si falla, se queda el de antes y sale un aviso). El actual no se «cambia».
  const [cambiandoModo, setCambiandoModo] = React.useState(false);
  const cambiarModo = (modo) => {
    const actual = (cfg && cfg.interfaz_modo) || 'web';
    if (!cfg || modo === actual || cambiandoModo) return;
    if (!window.lune || typeof window.lune.cambiar_interfaz !== 'function') {
      set('interfaz_modo')(modo); return;                    // demo: solo se marca
    }
    // Lo pendiente (solo lo cambiado; el modo lo escribe el gestor, no guardar_config).
    const payload = cambiosAjustes(foto.current, cfg, [...AJUSTES_SOLO_LECTURA, 'interfaz_modo']);
    setCambiandoModo(true); setMsg('Cambiando de interfaz…');
    guardarCambios(payload, () => {
      window.lune.cambiar_interfaz(modo, (r) => {
        let x = {}; try { x = JSON.parse(r) || {}; } catch (e) {}
        if (x.ok && x.reinicio) { setCfg((c0) => ({ ...c0, interfaz_modo: modo })); setMsg('Se aplicará al reiniciar Lune'); }
        else if (!x.ok) setMsg(x.error || 'No pude cambiar de interfaz');
        setCambiandoModo(false);
        setTimeout(() => setMsg(''), 4000);
      });
    });
  };

  const c = cfg || CFG_DEMO;

  // «Probar conexión» de la API compatible prueba lo que está escrito, aún sin guardar.
  React.useEffect(() => {
    if (!cfg || !window.lune || typeof window.lune.compat_borrador !== 'function') return;
    try {
      window.lune.compat_borrador(JSON.stringify({
        compat_url: cfg.compat_url || '', compat_key: cfg.compat_key || '', compat_model: cfg.compat_model || '',
      }));
    } catch (e) {}
  }, [cfg && cfg.compat_url, cfg && cfg.compat_key, cfg && cfg.compat_model]);

  // ── Audio: dispositivos reales del equipo y pruebas de micrófono/salida ──
  const [audio, setAudio] = React.useState(AUDIO_DEMO);
  const [micMsg, setMicMsg] = React.useState('');
  const [micNivel, setMicNivel] = React.useState(0);
  const [probando, setProbando] = React.useState(false);
  React.useEffect(() => {
    if (!window.lune) return undefined;
    window.lune.dispositivos_audio((j) => { try { setAudio((a) => ({ ...a, ...JSON.parse(j) })); } catch (e) {} });
    const onPrueba = (j) => {
      setProbando(false);
      try { const r = JSON.parse(j); setMicMsg(r.mensaje || ''); setMicNivel(Number(r.pico) || 0); } catch (e) {}
    };
    try { window.lune.mic_prueba.connect(onPrueba); } catch (e) {}
    return () => { try { window.lune.mic_prueba.disconnect(onPrueba); } catch (e) {} };
  }, []);
  const HABLA_AHORA = 'Habla ahora… (1.5 s)';
  const probarMic = () => {
    if (!window.lune) { setMicMsg('Demo · sin backend'); return; }
    setProbando(true); setMicMsg(HABLA_AHORA); setMicNivel(0);
    // False: el micrófono está ocupado (dictado, llamada o «Probar dictado») o no se encontró; si la
    // señal ya trajo el motivo se queda, si no, este (antes se quedaba en «Habla ahora…»).
    window.lune.probar_microfono(c.dispositivo_entrada || '', (ok) => {
      if (ok) return;
      setProbando(false);
      setMicMsg((m) => (m === HABLA_AHORA
        ? 'Ahora no puedo probarlo: el micrófono está en uso (dictado, llamada o «Probar dictado»). Termina y vuelve a probar.'
        : m));
    });
  };
  // «Probar salida» con respuesta a la vista: «Sonando…» o por qué no.
  const [salidaMsg, setSalidaMsg] = React.useState('');
  const probarSalida = () => {
    if (!window.lune) { setSalidaMsg('Demo · sin backend'); return; }
    setSalidaMsg('Probando la salida…');
    window.lune.probar_salida(c.dispositivo_salida || '', (ok) => {
      setSalidaMsg(ok ? `Sonando un tono por «${c.dispositivo_salida || 'la salida del sistema'}»… ¿me oyes?`
        : 'No pude sonar: no tengo motor de voz o esa salida no está.');
    });
  };
  const micDef = (audio.entradas.find((e) => e.defecto) || {}).nombre;

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
            <CampoClaveAjustes id="f-or-key" label="API Key de OpenRouter" value={c.openrouter_key||''} onChange={set('openrouter_key')} hint="Se guarda localmente en datos.json" />
            <Input label="Modelo" value={c.openrouter_model||''} onChange={set('openrouter_model')} hint="openrouter/auto enruta solo" />
          </div>
          {/* 11.3 (extra/diagnostico.jsx): «Probar clave» con lo escrito. */}
          {window.ProbarOpenRouter && <window.ProbarOpenRouter cfg={c} />}
        </Card>

        <Card eyebrow={<><window.IconCpu width={13} height={13}/> Red Neuronal · Local
            <button type="button" className="ln-help-btn" title="¿Cómo configuro Ollama? (aquí o en otro equipo)"
              onClick={()=>setAyudaOllama(true)} aria-label="Ayuda de Ollama">?</button></>}
          title="Ollama" tone="cyan" tick>
          <div className="ln-settings-grid">
            <Input label="Servidor" value={c.ollama_url||''} onChange={set('ollama_url')} hint="http://localhost:11434 o la IP de otro equipo de tu red" />
            <Input label="Modelo local" value={c.ollama_model||''} onChange={set('ollama_model')} hint="p. ej. qwen2.5:7b" />
          </div>
          {/* 11.3 (extra/diagnostico.jsx): «Probar / Buscar modelos»; los modelos salen como chips para elegir. */}
          {window.ProbarOllama && <window.ProbarOllama cfg={c} set={set} />}
          <p className="ln-modal-nota" style={{margin:'10px 0 0'}}>¿Ollama en otra computadora? Pulsa el <b>?</b> de arriba: Lune te explica paso a paso.</p>
        </Card>
        {ayudaOllama && <AyudaOllama onClose={()=>setAyudaOllama(false)} />}

        {/* Tercer proveedor (LM Studio, Groq, OpenAI…) y parámetros del modelo (extra/ia_avanzada.jsx) */}
        {window.CompatCard && <window.CompatCard cfg={c} set={set} />}
        {window.AvanzadoCard && <window.AvanzadoCard cfg={c} set={set} />}

        <Card eyebrow={<><window.IconTelegram width={13} height={13}/> Integración</>} title="Telegram" tone="blue">
          <div className="ln-settings-grid">
            <CampoClaveAjustes id="f-tg-token" label="Token del Bot" value={c.telegram_token||''} onChange={set('telegram_token')} hint="@BotFather → /newbot" />
            <Input label="Tu ID de Telegram" value={c.telegram_admin_id||''} onChange={set('telegram_admin_id')}
              inputMode="numeric" hint="Escríbele /id al bot. Solo números; con él, solo tú puedes usarlo." />
          </div>
          <div style={{height:14}} />
          <div className="ln-toggle-row">
            <Switch label="Órdenes desde Telegram (con aprobación en el PC)" checked={!!c.telegram_ordenes_pc}
              onChange={setBl('telegram_ordenes_pc')} accent="blue" />
          </div>
          <p className="ln-modal-nota" style={{margin:'8px 0 0'}}>
            Escribe <code>/pc abre youtube</code> en tu Telegram y Lune lo hace aquí solo si lo apruebas en el PC.
            Requiere tu ID de Telegram y reiniciar el bot para aplicarse.
          </p>
          {/* 11.3 (extra/diagnostico.jsx): «Probar bot»: token, tu ID, Node.js y la carpeta del bot. */}
          {window.ProbarTelegram && <window.ProbarTelegram cfg={c} />}
        </Card>

        <Card eyebrow={<><window.IconBrain width={13} height={13}/> Comportamiento</>} title="Personalidad">
          <Input label="Nombre del asistente" value={c.nombre||''} onChange={set('nombre')} />
          <div style={{height:14}} />
          <Input label="System Prompt" textarea rows={3} value={c.system_prompt||''} onChange={set('system_prompt')} />
          <div style={{height:18}} />
          <div className="ln-toggle-row">
            <Switch label="Voz (Lune lee sus respuestas)" checked={voiceOn} onChange={onVoice} />
            <Switch label="Memoria persistente" checked={!!c.memoria} onChange={setBl('memoria')} accent="blue" />
            <Switch label="Herramientas de escritorio" checked={!!c.acciones_ia} onChange={setBl('acciones_ia')} />
            <Switch label="Respuestas instantáneas (saludos, hora, tus tareas: sin gastar IA)"
                    checked={c.respuestas_rapidas !== false} onChange={setBl('respuestas_rapidas')} />
          </div>
        </Card>

        {/* Qué voz, velocidad, tono y motor (extra/voz.jsx); el interruptor de arriba la enciende. */}
        {window.VozCard && <window.VozCard cfg={c} set={set} />}

        <Card eyebrow={<><window.IconMic width={13} height={13}/> Audio</>} title="Micrófono y salida" tone="cyan">
          <p className="ln-card-nota">
            Para dictar (🎙 en el chat) y para el modo llamada. Windows suele traer varios micrófonos (el de la laptop, el headset,
            «Steam Streaming»…): elige el que tienes puesto y pruébalo antes de llamar.
          </p>
          {/* audio.instalar lo escribe el backend (nucleo/rutas.como_instalar): la orden de pip desde el
              código; instalada, que eso no viene (ahí no hay pip ni «Instalar componentes…»). */}
          {audio.faltan && audio.faltan.length > 0 && (
            <p className="ln-modal-nota" style={{ margin:'0 0 12px', color:'var(--yellow-500)' }}>
              {c.instalada
                ? <>Falta {audio.faltan.join(', ')}. {audio.instalar}</>
                : <>Falta instalar: <code>{audio.instalar || audio.faltan.join(' ')}</code> — o usa «Instalar componentes…» más abajo.</>}
            </p>
          )}
          <div className="ln-settings-grid">
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-mic">Micrófono de entrada</label>
              <select id="f-mic" className="lune-input ln-select" value={c.dispositivo_entrada || ''} onChange={set('dispositivo_entrada')}>
                <option value="">Por defecto del sistema{micDef ? ` · ${micDef}` : ''}</option>
                {audio.entradas.map((e) => <option key={e.id} value={e.nombre}>{e.nombre}{e.defecto ? ' (defecto)' : ''}</option>)}
              </select>
              <span className="lune-field-hint">{audio.entradas.length ? `${audio.entradas.length} detectados · si el tuyo no sale, conéctalo y vuelve a abrir Configuración` : 'No detecté micrófonos'}</span>
            </div>
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-out">Salida de audio (por dónde habla Lune)</label>
              <select id="f-out" className="lune-input ln-select" value={c.dispositivo_salida || ''} onChange={set('dispositivo_salida')}>
                <option value="">Por defecto del sistema</option>
                {audio.salidas.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <span className="lune-field-hint">«Speakers (Steam Streaming …)» es virtual: si lo eliges no oirás nada.</span>
            </div>
          </div>
          <div className="ln-audio-row">
            <Button variant="ghost" size="sm" onClick={probarMic} disabled={probando}>{probando ? 'Escuchando…' : 'Probar micrófono'}</Button>
            <div className="ln-vu" aria-hidden="true"><i style={{ width: `${Math.min(100, Math.round(micNivel * 400))}%` }} /></div>
            <Button variant="ghost" size="sm" onClick={probarSalida}><window.IconVolume width={13} height={13}/> Probar salida</Button>
          </div>
          {micMsg && <p className="ln-modal-nota" style={{ margin:'8px 0 0' }}>{micMsg}</p>}
          {salidaMsg && <p className="ln-modal-nota" style={{ margin:'8px 0 0' }} role="status">{salidaMsg}</p>}
          <div style={{height:14}} />
          <div className="ln-settings-grid">
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-whisper">Modelo de Whisper (transcripción local)</label>
              <select id="f-whisper" className="lune-input ln-select" value={c.modelo_whisper || 'base'} onChange={set('modelo_whisper')}>
                {(audio.modelos_whisper || []).map((m) => (
                  <option key={m} value={m}>{m}{(audio.modelos_descargados || []).includes(m) ? ' · descargado' : ' · se descarga la 1ª vez'}</option>
                ))}
              </select>
              <span className="lune-field-hint">tiny/base van bien en CPU; small o más grande con GPU. La descarga es una sola vez y necesita internet.</span>
            </div>
            <Input label="Idioma del dictado" value={c.voz_idioma ?? 'es'} onChange={set('voz_idioma')} hint="es, en, fr… vacío = detectar solo" />
          </div>
          {/* 11.3 (extra/diagnostico.jsx): «Probar dictado», 3 s con el micrófono y el modelo elegidos. */}
          {window.ProbarDictado && <window.ProbarDictado cfg={c} descargados={audio.modelos_descargados} />}
        </Card>

        <Card eyebrow={<><window.IconBolt width={13} height={13}/> Sistema</>} title="Calidad de vida" tone="blue">
          <div className="ln-toggle-row">
            <Switch label="Arrancar Lune junto con Windows" checked={!!c.autoinicio} onChange={setBl('autoinicio')} accent="blue" />
          </div>
          {/* Cortes 7/8 (extra/vida.jsx): cómo aparece al arrancar con Windows y cuánto espera. */}
          {window.AutoinicioOpciones && <window.AutoinicioOpciones activo={!!c.autoinicio} />}
          <div style={{height:14}} />
          <div className="ln-settings-grid">
            <Input label="Lune se aburre tras (minutos sin escribirle)" type="number" min="0" value={c.aburrimiento_min ?? 10}
              onChange={set('aburrimiento_min')} hint="0 = nunca. Te dice algo una vez por racha; tu siguiente mensaje la rearma." />
            {/* Solo desde el código: la Lune instalada ya trae todo y no tiene pip. */}
            {!c.instalada && (
              <div>
                <div className="lune-overline" style={{marginBottom:6}}>Componentes</div>
                <Button variant="ghost" size="sm" onClick={()=>{ if (window.lune) window.lune.abrir_instalador(()=>{}); else setMsg('Demo · sin backend'); }}>
                  Instalar componentes…
                </Button>
                <p className="ln-modal-nota" style={{margin:'6px 0 0'}}>Abre el instalador: explica para qué sirve cada cosa (voz, dictado, interfaz animada…) y lo instala.</p>
              </div>
            )}
          </div>
        </Card>

        {/* 11.3 (extra/actualizaciones.jsx): mi versión, buscar e instalar las nuevas; guarda al momento por window.lune. */}
        {window.ActualizacionesCard && <window.ActualizacionesCard />}

        {/* 11.3 (extra/diagnostico.jsx): «Comprobar que todo funciona», item a item por window.lune. */}
        {window.DiagnosticoCard && <window.DiagnosticoCard />}

        <Card eyebrow={<><window.IconMoon width={13} height={13}/> Escritorio</>} title="Asistente en escritorio" tone="cyan">
          <p style={{margin:'0 0 12px', font:'var(--text-data)', fontSize:12, color:'var(--text-dim)'}}>
            Cómo se dibuja Lune cuando la sacas al escritorio (menú → Asistente en escritorio). Mientras está fuera, la barra lateral no la dibuja. Haz clic sobre ella para que comente tu pantalla, o doble clic para escribirle.
          </p>
          <div className="ln-seg-row">
            <Button variant={c.asistente_render==='animado'?'primary':'ghost'} size="sm" onClick={()=>set('asistente_render')('animado')}>Imágenes animadas</Button>
            <Button variant={c.asistente_render==='vrm'?'primary':'ghost'} size="sm" disabled={!c.vrm_webengine}
              title={c.vrm_webengine ? 'Avatar 3D con un modelo VRM'
                : (c.instalada ? 'No pude cargar QtWebEngine: reinstala Lune' : 'Necesita PyQt6-WebEngine (Sistema → Instalar componentes…)')}
              onClick={()=>set('asistente_render')('vrm')}>VRM 3D</Button>
            <Button variant={c.asistente_render==='sprites'?'primary':'ghost'} size="sm" onClick={()=>set('asistente_render')('sprites')}>Sprites ligeros</Button>
          </div>
          {c.asistente_render==='vrm' && <VrmOpciones c={c} set={set} setBl={setBl} setCfg={setCfg} />}
        </Card>

        {/* Biblioteca de modelos 3D (extra/vrm_biblioteca.jsx): rejilla, ficha, calibración en vivo,
            seguimiento del cursor y borrar. Solo con la asistente en VRM. */}
        {c.asistente_render==='vrm' && window.VrmBiblioteca && <window.VrmBiblioteca cfg={c} set={set} />}

        {/* Sonidos de reacción de la asistente y su volumen (extra/voz.jsx) */}
        {window.PackSonidosCard && <window.PackSonidosCard cfg={c} set={set} />}

        {/* Corte 4 (extra/apariencia.jsx y extra/juego.jsx): guardan al momento por window.luneEscritorio. */}
        {window.AparienciaCard && <window.AparienciaCard />}
        {window.MenuRadialCard && <window.MenuRadialCard />}
        {window.AtajosCard && <window.AtajosCard />}
        {window.BandejaCard && <window.BandejaCard />}
        {window.JuegoCard && <window.JuegoCard />}
        {window.RendimientoCard && <window.RendimientoCard />}

        {/* Cortes 5/6 (extra/alarmas.jsx y extra/baile.jsx): guardan al momento por window.luneAlarmas y
            window.luneMusica. */}
        {window.AlarmasCard && <window.AlarmasCard />}
        {window.PantallaGrandeCard && <window.PantallaGrandeCard />}
        {window.BaileCard && <window.BaileCard />}

        {/* Cortes 7/8 (extra/vida.jsx): sentarse, comida y Discord; guardan al momento por window.luneVida. */}
        {window.SentarseCard && <window.SentarseCard />}
        {window.ComidaCard && <window.ComidaCard />}
        {window.DiscordCard && <window.DiscordCard />}

        {/* Cortes 9/10 (extra/bailes_mmd.jsx y extra/minecraft.jsx): bailes MMD/VRMA y Minecraft; guardan
            al momento por window.luneEscenario. */}
        {window.BailesCard && <window.BailesCard />}
        {window.MinecraftCard && <window.MinecraftCard />}

        <Card eyebrow={<><window.IconCpu width={13} height={13}/> Rendimiento</>} title="Modo de interfaz" tone="yellow">
          <p style={{margin:'0 0 12px', font:'var(--text-data)', fontSize:12, color:'var(--text-dim)'}}>
            <b>Bajos recursos</b> usa la interfaz nativa ligera (sin Chromium ni videos) para no consumir tanto en equipos modestos. Se aplica al instante: guarda lo pendiente y la conversación sigue en la nueva.
          </p>
          <div className="ln-seg-row">
            <Button variant={(c.interfaz_modo||'web')==='web'?'primary':'ghost'} size="sm" disabled={cambiandoModo} onClick={()=>cambiarModo('web')}>Completa</Button>
            <Button variant={c.interfaz_modo==='nativo'?'primary':'ghost'} size="sm" disabled={cambiandoModo} onClick={()=>cambiarModo('nativo')}>Bajos recursos</Button>
            <Button variant={c.interfaz_modo==='patata'?'primary':'ghost'} size="sm" disabled={cambiandoModo} onClick={()=>cambiarModo('patata')} title="Solo terminal: texto y caritas :D — sin Qt, sin imágenes">Patata (terminal)</Button>
          </div>
        </Card>

        <Card eyebrow={<><window.IconBolt width={13} height={13}/> Rendimiento</>} title="Efectos visuales" tone="yellow">
          <p style={{margin:'0 0 14px', font:'var(--text-data)', fontSize:12, color:'var(--text-dim)'}}>Desactiva efectos para consumir menos recursos en equipos modestos.</p>
          <div className="ln-toggle-row">
            <Switch label="Fondo animado (fragmentos y grid)" checked={fx.bg} onChange={setFxKey('bg')} />
            <Switch label="Barrido al cambiar de vista" checked={fx.sweep} onChange={setFxKey('sweep')} accent="blue" />
            <Switch label="Micro-animaciones (burbujas, hover)" checked={fx.micro} onChange={setFxKey('micro')} />
            {/* Lune en reposo (11.2, ui_web/lune_reposo.js): efectos.pausar_sin_foco */}
            <Switch label="Quedarme quieta cuando no me usas" checked={fx.quieta !== false} onChange={setFxKey('quieta')} accent="blue" />
          </div>
          <p className="ln-modal-nota" style={{margin:'10px 0 0'}}>
            Sin el foco 20 s, o 90 s sin tocar nada, el fondo, las animaciones y mi vídeo se detienen donde estaban y vuelven al moverte.
          </p>
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
