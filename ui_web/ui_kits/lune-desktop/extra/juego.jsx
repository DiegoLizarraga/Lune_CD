/* Lune CD desktop — Modo juego y rendimiento de la mascota (Ajustes, corte 4).
 *
 * JuegoCard        estado en vivo (señal juego_estado) y forzar (automático · forzar · forzar «sin juego»),
 *                  detectar juegos, qué hace la mascota (ocultar · al fondo · nada), FPS durante el juego,
 *                  silenciar la voz, bajar la prioridad, recortar la memoria, pausar los atajos, contar vídeos
 *                  a pantalla completa, contar lo que corre desde carpetas de juegos y la lista de apps que
 *                  siempre cuentan como juego (con «Añadir app» desde las ventanas abiertas).
 * RendimientoCard  FPS máximos de la mascota, siempre encima, recorte automático de memoria, mostrar Lune en la
 *                  barra de tareas y «Liberar memoria».
 * No usan cfg/set de SettingsPanel: guardan al momento por window.luneEscritorio (ui/puente_escritorio.py):
 *   juego_config() · juego_guardar(json) · juego_estado_json() · juego_forzar(1 | 0 | -1) · juego_apps_visibles()
 *   rendimiento() · rendimiento_guardar(json) · liberar_memoria()      señal: juego_estado(json)
 * juego_forzar: 1 = forzar modo juego · 0 = automático · -1 = forzar «sin juego».
 * Sin puente (navegador), demo local. Se registra solo: Object.assign(window, {JuegoCard, RendimientoCard, LuneJuego}).
 */
(function () {
  const { useState, useEffect, useRef, useMemo } = React;

  const puente = () => window.luneEscritorio || null;
  function llamar(nombre, args, cb) {
    const e = puente();
    if (!e || typeof e[nombre] !== 'function') return false;
    try { e[nombre](...(args || []), (r) => { if (cb) cb(r); }); return true; } catch (err) { return false; }
  }
  function conectar(senal, fn) {
    const e = puente();
    const s = e && e[senal];
    if (!s || typeof s.connect !== 'function') return () => {};
    try { s.connect(fn); } catch (err) { return () => {}; }
    return () => { try { s.disconnect(fn); } catch (err) { /* ya no está */ } };
  }
  function leer(j, def) {
    if (j == null) return def;
    if (typeof j === 'object') return j;
    try { const o = JSON.parse(j); return o == null ? def : o; } catch (e) { return def; }
  }
  function crearRetardo(fn, ms) {
    let timer = null;
    return (arg) => { if (timer) clearTimeout(timer); timer = setTimeout(() => { timer = null; fn(arg); }, ms); };
  }

  // ── Datos y utilidades puras ───────────────────────────────────────────────
  const ACCIONES = [
    ['ocultar', 'Ocultarla', 'La mascota desaparece hasta que acabes.'],
    ['fondo', 'Al fondo', 'Se queda detrás de las ventanas, sin molestar.'],
    ['nada', 'Nada', 'Sigue igual (solo baja FPS, voz y prioridad).'],
  ];
  const MOTIVOS = {
    quns3: 'pantalla completa exclusiva', quns4: 'presentación a pantalla completa', quns2: 'vídeo o app a pantalla completa',
    sin_bordes: 'ventana sin bordes a pantalla completa', lista: 'está en tu lista de juegos', ruta: 'corre desde una carpeta de juegos',
    forzado: 'forzado a mano',
  };
  const JUEGO_DEFECTO = {
    activo: true, accion: 'ocultar', fps: 0, apps: [], rutas_juego: true, incluir_videos: true,
    prioridad_baja: true, recortar_ram: true, silenciar: true, pausar_atajos: true,
  };
  const RENDIMIENTO_DEFECTO = { fps_max: 60, siempre_encima: true, recorte_ram_auto: false, en_barra_tareas: true };
  const APP_OK = /^[\w .\-()]{1,80}$/;

  /** «  Juego.EXE » → «juego.exe»; null si no es un nombre de programa (nada de rutas). */
  function normalizarApp(nombre) {
    if (typeof nombre !== 'string') return null;
    const s = nombre.trim().toLowerCase();
    if (!s || /[\\/:]/.test(s) || !APP_OK.test(s)) return null;
    return s;
  }
  const bool = (v, d) => (typeof v === 'boolean' ? v : d);
  function normalizarJuego(o) {
    const r = o && typeof o === 'object' ? o : {};
    const fps = Number(r.fps);
    const apps = [];
    (Array.isArray(r.apps) ? r.apps : []).forEach((a) => { const n = normalizarApp(a); if (n && !apps.includes(n)) apps.push(n); });
    const out = { ...JUEGO_DEFECTO, apps };
    ['activo', 'rutas_juego', 'incluir_videos', 'prioridad_baja', 'recortar_ram', 'silenciar', 'pausar_atajos']
      .forEach((k) => { out[k] = bool(r[k], JUEGO_DEFECTO[k]); });
    out.accion = ACCIONES.some(([k]) => k === r.accion) ? r.accion : 'ocultar';
    out.fps = isFinite(fps) ? Math.min(60, Math.max(0, Math.round(fps))) : 0;
    return out;
  }
  function normalizarEstado(o) {
    const r = o && typeof o === 'object' ? o : {};
    return {
      activo: r.activo === true,
      motivo: typeof r.motivo === 'string' ? r.motivo.slice(0, 24) : '',
      forzado: typeof r.forzado === 'boolean' ? r.forzado : null,
      exe: normalizarApp(r.exe || '') || '',
      disponible: r.disponible !== false,
    };
  }
  /** forzado (true | false | null) → valor de juego_forzar (1 | -1 | 0). */
  const valorForzado = (f) => (f === true ? 1 : f === false ? -1 : 0);
  function textoEstado(e) {
    if (!e.disponible) return 'El detector de juegos no está en marcha.';
    if (!e.activo) return e.forzado === false ? 'Sin modo juego (forzado a mano).' : 'Ahora mismo no hay ningún juego delante.';
    const por = MOTIVOS[e.motivo] || e.motivo || 'detectado';
    return `En modo juego: ${por}${e.exe ? ` · ${e.exe}` : ''}.`;
  }
  function normalizarRendimiento(o) {
    const r = o && typeof o === 'object' ? o : {};
    const f = Number(r.fps_max);
    return {
      fps_max: isFinite(f) ? Math.min(144, Math.max(15, Math.round(f))) : 60,
      siempre_encima: bool(r.siempre_encima, true), recorte_ram_auto: bool(r.recorte_ram_auto, false),
      en_barra_tareas: bool(r.en_barra_tareas, true),
    };
  }

  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-c4-juego-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-c4-juego-css';
      st.textContent = `
        .ln-c4j-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-c4j-sub{ font:var(--text-overline); letter-spacing:var(--ls-mega); text-transform:uppercase; color:var(--text-faint); margin:16px 0 8px; }
        .ln-c4j-estado{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 12px; background:var(--ink-950);
          border:var(--bw) solid var(--ink-500); border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); }
        .ln-c4j-estado.is-on{ border-left-color:var(--yellow-500); }
        .ln-c4j-estado-tx{ flex:1; min-width:180px; font-family:var(--font-mono); font-size:12px; color:var(--text); }
        .ln-c4j-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-c4j-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-c4j-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-c4j-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-c4j-apps{ display:flex; flex-wrap:wrap; gap:6px; }
        .ln-c4j-app{ display:inline-flex; align-items:center; gap:6px; font-family:var(--font-mono); font-size:11.5px; color:var(--cyan-300);
          background:var(--ink-800); border:var(--bw) solid var(--cyan-700); padding:3px 4px 3px 10px; clip-path:var(--clip-tr); }
        .ln-c4j-app button{ appearance:none; -webkit-appearance:none; border:none; background:none; color:var(--text-dim); cursor:pointer; font:inherit; padding:0 6px; }
        .ln-c4j-app button:hover{ color:var(--yellow-500); }
        .ln-c4j-add{ display:flex; gap:8px; align-items:flex-end; margin-top:10px; flex-wrap:wrap; }
        .ln-c4j-add select, .ln-c4j-add .lune-field{ flex:1; min-width:180px; }
        .ln-c4j-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-c4j-msg.is-error{ color:var(--yellow-500); }
        .ln-c4j-msg.is-ok{ color:var(--cyan-300); }
        .modo-juego .ln-c4j-estado{ animation:none; }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }
  function useVivo() {
    const vivo = useRef(true);
    useEffect(() => { vivo.current = true; inyectarEstilos(); return () => { vivo.current = false; }; }, []);
    return vivo;
  }
  function Deslizador({ id, label, min, max, step = 1, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-c4j-range">
        <div className="ln-c4j-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-c4j-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }
  const Msg = ({ msg }) => (msg && msg.texto
    ? <p className={`ln-c4j-msg${msg.error ? ' is-error' : msg.ok ? ' is-ok' : ''}`} role="status">{msg.texto}</p> : null);

  // ── JuegoCard ──────────────────────────────────────────────────────────────
  function JuegoCard() {
    const { Card, Button, Switch, Badge, Input } = window.LUNE;
    const vivo = useVivo();
    const [cfg, setCfg] = useState(JUEGO_DEFECTO);
    const [est, setEst] = useState(() => normalizarEstado({ disponible: !!puente() }));
    const [visibles, setVisibles] = useState(null);          // null = sin pedir
    const [elegida, setElegida] = useState('');
    const [manual, setManual] = useState('');
    const [msg, setMsg] = useState(null);

    const guardar = (parcial) => {
      setCfg((c) => normalizarJuego({ ...c, ...parcial }));
      const ok = llamar('juego_guardar', [JSON.stringify(parcial)], (j) => {
        const r = leer(j, {});
        if (!vivo.current) return;
        if (r.estado) setCfg(normalizarJuego(r.estado));
        setMsg(r.ok ? { texto: 'Guardado.', ok: true } : { texto: r.error || 'No pude guardar.', error: true });
      });
      if (!ok) setMsg({ texto: 'Demo: se guarda en la app.', error: true });
    };
    const guardarFps = useMemo(() => crearRetardo((v) => guardar({ fps: v }), 350), []);

    useEffect(() => {
      llamar('juego_config', [], (j) => { if (vivo.current) setCfg(normalizarJuego(leer(j, {}))); });
      const alEstado = (j) => { if (vivo.current) setEst(normalizarEstado(leer(j, {}))); };
      llamar('juego_estado_json', [], alEstado);
      return conectar('juego_estado', alEstado);
    }, []);

    const forzar = (v) => {
      const ok = llamar('juego_forzar', [v], () => llamar('juego_estado_json', [], (j) => { if (vivo.current) setEst(normalizarEstado(leer(j, {}))); }));
      if (!ok) setEst((e) => ({ ...e, forzado: v === 1 ? true : v === -1 ? false : null, activo: v === 1, motivo: v === 1 ? 'forzado' : '' }));
    };
    const pedirVisibles = () => {
      const ok = llamar('juego_apps_visibles', [], (j) => {
        if (!vivo.current) return;
        const lista = [];
        (Array.isArray(leer(j, [])) ? leer(j, []) : []).forEach((a) => { const n = normalizarApp(a); if (n && !lista.includes(n)) lista.push(n); });
        setVisibles(lista);
        setElegida('');
        if (!lista.length) setMsg({ texto: 'No encontré ventanas abiertas de otros programas.', error: true });
      });
      if (!ok) setVisibles(['juego_demo.exe', 'otro_juego.exe']);
    };
    const anadir = (nombre) => {
      const n = normalizarApp(nombre);
      if (!n) { setMsg({ texto: 'Escribe solo el nombre del programa (por ejemplo juego.exe), sin rutas.', error: true }); return false; }
      if (cfg.apps.includes(n)) { setMsg({ texto: `${n} ya está en la lista.`, ok: true }); return false; }
      if (cfg.apps.length >= 50) { setMsg({ texto: 'Como mucho 50 apps.', error: true }); return false; }
      guardar({ apps: [...cfg.apps, n] });
      return true;
    };

    const libres = (visibles || []).filter((a) => !cfg.apps.includes(a));
    const sel = libres.includes(elegida) ? elegida : (libres[0] || '');
    const fz = valorForzado(est.forzado);
    const Icono = window.IconCpu || (() => null);
    return (
      <Card id="aj-juego" eyebrow={<><Icono width={13} height={13}/> Escritorio · Modo juego</>} title="Modo juego" tone="yellow" tick>
        <p className="ln-c4j-nota">
          Cuando hay un juego (o un vídeo) a pantalla completa delante, Lune se aparta: sin hooks ni tocar el juego, solo mira qué
          ventana tienes al frente. Entra a los ~4 s y sale a los ~6 s de dejarlo.
        </p>
        <div className={`ln-c4j-estado${est.activo ? ' is-on' : ''}`}>
          <Badge variant={est.activo ? 'yellow' : 'ink'} outline={!est.activo}>{est.activo ? 'EN JUEGO' : 'sin juego'}</Badge>
          <span className="ln-c4j-estado-tx">{textoEstado(est)}</span>
        </div>
        <div className="ln-c4j-sub">Forzar</div>
        <div className="ln-seg-row">
          <Button size="sm" variant={fz === 0 ? 'primary' : 'ghost'} onClick={() => forzar(0)}>Automático</Button>
          <Button size="sm" variant={fz === 1 ? 'primary' : 'ghost'} onClick={() => forzar(1)}>Forzar modo juego</Button>
          <Button size="sm" variant={fz === -1 ? 'primary' : 'ghost'} onClick={() => forzar(-1)}>Forzar «sin juego»</Button>
        </div>

        <div className="ln-c4j-sub">Detección</div>
        <div className="ln-toggle-row">
          <Switch label="Detectar juegos" checked={cfg.activo} onChange={(e) => guardar({ activo: !!e.target.checked })} accent="yellow" />
          <Switch label="Un vídeo a pantalla completa también cuenta" checked={cfg.incluir_videos}
            onChange={(e) => guardar({ incluir_videos: !!e.target.checked })} />
          <Switch label="Contar lo que corre desde carpetas de juegos (Steam, Epic…)" checked={cfg.rutas_juego}
            onChange={(e) => guardar({ rutas_juego: !!e.target.checked })} accent="blue" />
        </div>

        <div className="ln-c4j-sub">Durante el juego</div>
        <div className="ln-seg-row">
          {ACCIONES.map(([k, t, d]) => (
            <Button key={k} size="sm" variant={cfg.accion === k ? 'primary' : 'ghost'} title={d} onClick={() => guardar({ accion: k })}>{t}</Button>
          ))}
        </div>
        <div style={{ height: 12 }} />
        <div className="ln-settings-grid">
          <Deslizador id="f-juego-fps" label="FPS de la mascota en juego" min={0} max={60} step={5} value={cfg.fps}
            fmt={(v) => (v === 0 ? 'en pausa' : `${v} fps`)} hint="0 = en pausa (no gasta GPU)."
            onChange={(v) => { setCfg((c) => ({ ...c, fps: v })); guardarFps(v); }} />
          <div className="ln-toggle-row">
            <Switch label="Silenciar la voz" checked={cfg.silenciar} onChange={(e) => guardar({ silenciar: !!e.target.checked })} />
            <Switch label="Bajar la prioridad de Lune" checked={cfg.prioridad_baja} onChange={(e) => guardar({ prioridad_baja: !!e.target.checked })} accent="blue" />
            <Switch label="Recortar su memoria al entrar" checked={cfg.recortar_ram} onChange={(e) => guardar({ recortar_ram: !!e.target.checked })} />
            <Switch label="Pausar los atajos (menos «Mostrar Lune»)" checked={cfg.pausar_atajos} onChange={(e) => guardar({ pausar_atajos: !!e.target.checked })} accent="blue" />
          </div>
        </div>

        <div className="ln-c4j-sub">Siempre cuentan como juego</div>
        <div className="ln-c4j-apps">
          {cfg.apps.length === 0 && <span className="ln-c4j-msg" style={{ margin: 0 }}>Ninguna: se detectan solos.</span>}
          {cfg.apps.map((a) => (
            <span className="ln-c4j-app" key={a}>{a}
              <button type="button" aria-label={`Quitar ${a}`} title="Quitar" onClick={() => guardar({ apps: cfg.apps.filter((x) => x !== a) })}>✕</button>
            </span>
          ))}
        </div>
        <div className="ln-c4j-add">
          {visibles === null ? (
            <Button size="sm" variant="secondary" onClick={pedirVisibles}>Añadir app…</Button>
          ) : (
            <>
              <select id="f-juego-visibles" className="lune-input ln-select" value={sel} disabled={!libres.length}
                onChange={(e) => setElegida(e.target.value)} aria-label="Programas con ventana abierta">
                {!libres.length && <option value="">(nada nuevo abierto)</option>}
                {libres.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
              <Button size="sm" variant="secondary" disabled={!sel} onClick={() => { if (anadir(sel)) setElegida(''); }}>Añadir</Button>
              <Button size="sm" variant="ghost" onClick={pedirVisibles}>Refrescar</Button>
            </>
          )}
        </div>
        <div className="ln-c4j-add">
          <Input id="f-juego-manual" label="O escribe el programa" placeholder="juego.exe" value={manual} maxLength={80}
            onChange={(e) => setManual(e.target.value)} />
          <Button size="sm" variant="ghost" disabled={!manual.trim()} onClick={() => { if (anadir(manual)) setManual(''); }}>Añadir</Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  // ── RendimientoCard ────────────────────────────────────────────────────────
  function RendimientoCard() {
    const { Card, Button, Switch } = window.LUNE;
    const vivo = useVivo();
    const [r, setR] = useState(RENDIMIENTO_DEFECTO);
    const [msg, setMsg] = useState(null);
    const [liberando, setLiberando] = useState(false);

    const guardar = (parcial) => {
      setR((x) => normalizarRendimiento({ ...x, ...parcial }));
      const ok = llamar('rendimiento_guardar', [JSON.stringify(parcial)], (j) => {
        const o = leer(j, {});
        if (!vivo.current) return;
        if (o.estado) setR(normalizarRendimiento(o.estado));
        setMsg(o.ok ? { texto: 'Guardado y aplicado.', ok: true } : { texto: o.error || 'No pude guardar.', error: true });
      });
      if (!ok) setMsg({ texto: 'Demo: se guarda en la app.', error: true });
    };
    const guardarFps = useMemo(() => crearRetardo((v) => guardar({ fps_max: v }), 350), []);
    useEffect(() => { llamar('rendimiento', [], (j) => { if (vivo.current) setR(normalizarRendimiento(leer(j, {}))); }); }, []);

    const liberar = () => {
      setLiberando(true);
      const ok = llamar('liberar_memoria', [], (j) => {
        const o = leer(j, {});
        if (!vivo.current) return;
        setLiberando(false);
        setMsg(o.ok
          ? { texto: `Liberados ${Number(o.liberado || 0).toFixed(1)} MB (${Number(o.antes || 0).toFixed(1)} → ${Number(o.despues || 0).toFixed(1)} MB).`, ok: true }
          : { texto: o.error || 'No pude liberar memoria.', error: true });
      });
      if (!ok) { setLiberando(false); setMsg({ texto: 'Demo: liberar memoria necesita la app.', error: true }); }
    };

    const Icono = window.IconBolt || (() => null);
    return (
      <Card id="aj-rendimiento" eyebrow={<><Icono width={13} height={13}/> Rendimiento · Mascota</>} title="Rendimiento" tone="yellow">
        <p className="ln-c4j-nota">
          Cuánto gasta la mascota de escritorio. En reposo se dibuja a la mitad (máx. 30 fps). Se aplica al momento.
        </p>
        <Deslizador id="f-fps-max" label="FPS máximos de la mascota" min={15} max={144} step={1} value={r.fps_max}
          fmt={(v) => `${v} fps`} hint="Menos FPS = menos GPU; 60 va sobrado."
          onChange={(v) => { setR((x) => ({ ...x, fps_max: v })); guardarFps(v); }} />
        <div style={{ height: 12 }} />
        <div className="ln-toggle-row">
          <Switch label="Mascota siempre encima" checked={r.siempre_encima} onChange={(e) => guardar({ siempre_encima: !!e.target.checked })} />
          <Switch label="Recortar la memoria de vez en cuando" checked={r.recorte_ram_auto}
            onChange={(e) => guardar({ recorte_ram_auto: !!e.target.checked })} accent="blue" />
          <Switch label="Mostrar Lune en la barra de tareas" checked={r.en_barra_tareas}
            onChange={(e) => guardar({ en_barra_tareas: !!e.target.checked })} accent="yellow" />
        </div>
        <div className="ln-c4j-add">
          <Button size="sm" variant="secondary" disabled={liberando} onClick={liberar}>{liberando ? 'Liberando…' : 'Liberar memoria'}</Button>
        </div>
        <Msg msg={msg} />
      </Card>
    );
  }

  Object.assign(window, {
    JuegoCard,
    RendimientoCard,
    LuneJuego: { normalizarApp, normalizarJuego, normalizarEstado, normalizarRendimiento, valorForzado, textoEstado, MOTIVOS, ACCIONES },
  });
})();
