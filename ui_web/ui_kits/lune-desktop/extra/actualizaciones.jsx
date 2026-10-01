/* Lune CD desktop — Actualizaciones (Ajustes → Sistema, 11.3).
 *
 * ActualizacionesCard  mi versión y si soy la «instalada» o «desde el código», «Buscar actualizaciones», el
 *                      resultado con las notas del release (texto plano, recortado), la barra de la descarga,
 *                      «Instalar y reiniciar» (con confirmación: te cierro, se instala solo y me vuelvo a abrir),
 *                      «Descargar ahora», «Cancelar», «Omitir esta versión» y el interruptor «Buscar al iniciar».
 *                      Desde el código (git): buscar = los commits nuevos y «Actualizar y reiniciar» = git pull +
 *                      pip y reinicio (con su aviso si tienes cambios sin guardar). Copia sin git: el enlace a la
 *                      página de Releases. Si el aviso al iniciar encontró una versión nueva, la tarjeta sale
 *                      resaltada al abrir Ajustes.
 * Habla con window.lune (ui/web_bridge.py → ui/actualizacion_qt.ControlActualizacion):
 *   actualizacion_info() · actualizacion_buscar() · actualizacion_descargar() · actualizacion_cancelar() ·
 *   actualizacion_instalar() · actualizacion_omitir(version) · actualizacion_al_iniciar(bool)
 *   señal: actualizacion(json {fase: buscando|hay|al_dia|descargando|lista|instalando|error, version, notas, bytes,
 *          total, pct, mensaje, …})
 * Sin puente (navegador), demo local. Se registra solo: Object.assign(window, {ActualizacionesCard, LuneActualizaciones}).
 */
(function () {
  const { useState, useEffect, useRef } = React;

  const FASES = ['buscando', 'hay', 'al_dia', 'descargando', 'lista', 'instalando', 'error'];
  const OCUPADAS = ['buscando', 'descargando', 'instalando'];
  const MAX_NOTAS = 900;
  const URL_RELEASES = 'https://github.com/DiegoLizarraga/Lune_CD/releases';
  const MODOS = { instalada: 'instalada', git: 'desde el código (git)', carpeta: 'copia sin git' };

  const puente = () => window.lune || null;
  function llamar(nombre, args, cb) {
    const l = puente();
    if (!l || typeof l[nombre] !== 'function') return false;
    try { l[nombre](...(args || []), (r) => { if (cb) cb(r); }); return true; } catch (err) { return false; }
  }
  function conectar(senal, fn) {
    const l = puente();
    const s = l && l[senal];
    if (!s || typeof s.connect !== 'function') return () => {};
    try { s.connect(fn); } catch (err) { return () => {}; }
    return () => { try { s.disconnect(fn); } catch (err) { /* ya no está */ } };
  }
  function leer(j, def) {
    if (j == null) return def;
    if (typeof j === 'object') return j;
    try { const o = JSON.parse(j); return o == null ? def : o; } catch (e) { return def; }
  }
  const num = (v) => { const n = Number(v); return isFinite(n) && n > 0 ? n : 0; };

  // ── Utilidades puras (window.LuneActualizaciones; las prueban los tests) ──────
  function normalizarEstado(e) {
    const r = e && typeof e === 'object' ? e : {};
    const fase = FASES.includes(r.fase) ? r.fase : '';
    const total = num(r.total), bytes = Math.min(num(r.bytes), total || num(r.bytes));
    const pct = Math.max(0, Math.min(100, Math.round(num(r.pct) || (total ? (bytes * 100) / total : 0))));
    return {
      fase, version: String(r.version || ''), notas: String(r.notas || ''), mensaje: String(r.mensaje || ''),
      bytes, total, pct, nueva: !!r.nueva, instalable: !!r.instalable, omitida: !!r.omitida,
      pagina: String(r.pagina || ''), commits: Array.isArray(r.commits) ? r.commits.map(String) : [],
      limpio: r.limpio !== false, modificados: Array.isArray(r.modificados) ? r.modificados.map(String) : [],
    };
  }
  function normalizarInfo(i) {
    const r = i && typeof i === 'object' ? i : {};
    return {
      version: String(r.version || ''), modo: MODOS[r.modo] ? r.modo : 'carpeta',
      al_iniciar: r.al_iniciar !== false, ultima: String(r.ultima_comprobacion || ''),
      omitida: String(r.omitir_version || ''), pagina: String(r.pagina || URL_RELEASES),
      estado: normalizarEstado(r.estado),
    };
  }
  /** «2026-10-01T07:00:00Z» → «2026-10-01 07:00 UTC» (sin depender del idioma del sistema). */
  function fmtFecha(iso) {
    const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(String(iso || ''));
    return m ? `${m[1]} ${m[2]} UTC` : '';
  }
  const fmtMB = (b) => `${Math.round(num(b) / (1024 * 1024))} MB`;
  /** Las notas en texto plano y recortadas (el backend ya quita el Markdown). */
  function recortarNotas(t, max = MAX_NOTAS) {
    const s = String(t || '').replace(/\r\n/g, '\n').trim();
    return s.length > max ? s.slice(0, max).trimEnd() + '…' : s;
  }
  /** Qué botones van según el modo y el estado. */
  function botones(modo, e) {
    const f = e.fase;
    const ocupada = OCUPADAS.includes(f);
    if (modo === 'git') {
      const hayGit = f === 'hay' || f === 'lista';
      return { buscar: !ocupada, instalar: hayGit && e.limpio, descargar: false, cancelar: false,
        omitir: false, enlace: false, conConfirmar: f !== 'lista' };
    }
    if (modo !== 'instalada') {
      return { buscar: !ocupada, instalar: false, descargar: false, cancelar: false, omitir: false, enlace: true, conConfirmar: false };
    }
    const nueva = e.nueva && e.instalable && ['hay', 'al_dia', 'lista', 'error'].includes(f);
    return {
      buscar: !ocupada, instalar: nueva, descargar: nueva && f !== 'lista', cancelar: f === 'descargando',
      omitir: f === 'hay' && !!e.version && !e.omitida, enlace: f === 'hay' && e.nueva && !e.instalable,
      conConfirmar: true,
    };
  }
  const textoModo = (modo) => MODOS[modo] || modo;

  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-act-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-act-css';
      st.textContent = `
        .ln-act-nota{ margin:0 0 12px; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim); }
        .ln-act-version{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:0 0 12px; font-family:var(--font-mono); font-size:13px; color:var(--text); }
        .ln-act-version b{ color:var(--cyan-300); }
        .ln-act.is-nueva .ln-act-estado{ border-left-color:var(--yellow-500); }
        .ln-act-estado{ padding:10px 12px; background:var(--ink-950); border:var(--bw) solid var(--ink-500);
          border-left:var(--bw-bold) solid var(--cyan-700); clip-path:var(--clip-tr); margin:0 0 12px; }
        .ln-act-msg{ font-family:var(--font-mono); font-size:12px; color:var(--text); margin:0; }
        .ln-act-msg.is-error{ color:var(--yellow-500); }
        .ln-act-notas{ white-space:pre-wrap; font:var(--text-data); font-size:12px; line-height:1.5; color:var(--text-dim);
          margin:8px 0 0; max-height:180px; overflow:auto; }
        .ln-act-commits{ margin:8px 0 0; padding:0; list-style:none; font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); }
        .ln-act-barra{ display:flex; align-items:center; gap:10px; margin:0 0 12px; }
        .ln-act-barra span{ font-family:var(--font-mono); font-size:11.5px; color:var(--cyan-300); min-width:42px; text-align:right; }
        .ln-act-fila{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:0 0 12px; }
        .ln-act-confirma{ padding:10px 12px; border:var(--bw) solid var(--yellow-500); background:var(--ink-900); margin:0 0 12px; }
        .ln-act-confirma p{ margin:0 0 10px; font:var(--text-data); font-size:12px; color:var(--text); }
        .ln-act a{ color:var(--cyan-300); }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // ── ActualizacionesCard ────────────────────────────────────────────────────
  function ActualizacionesCard() {
    const { Card, Button, Switch, Badge } = window.LUNE;
    const vivo = useRef(true);
    const [info, setInfo] = useState(() => normalizarInfo({ modo: puente() ? '' : 'carpeta' }));
    const [est, setEst] = useState(() => normalizarEstado({}));
    const [confirmar, setConfirmar] = useState(false);
    const [aviso, setAviso] = useState('');
    const sinPuente = !puente() || typeof puente().actualizacion_info !== 'function';

    const pedirInfo = () => llamar('actualizacion_info', [], (j) => {
      if (!vivo.current) return;
      const i = normalizarInfo(leer(j, {}));
      setInfo(i);
      if (i.estado.fase) setEst(i.estado);
    });
    useEffect(() => {
      vivo.current = true;
      inyectarEstilos();
      pedirInfo();
      const soltar = conectar('actualizacion', (j) => {
        if (!vivo.current) return;
        const e = normalizarEstado(leer(j, {}));
        setEst(e);
        if (e.fase === 'al_dia' || e.fase === 'hay' || e.fase === 'error') pedirInfo();   // omitida y última vez
      });
      return () => { vivo.current = false; soltar(); };
    }, []);

    const modo = info.modo;
    const b = botones(modo, est);
    const resaltada = est.fase === 'hay' || est.fase === 'lista';
    const demo = (t) => setAviso(t || 'Demo: las actualizaciones necesitan la app.');
    const buscar = () => { setAviso(''); setConfirmar(false); if (!llamar('actualizacion_buscar', [], (ok) => { if (!ok && vivo.current) setAviso('Ya estoy en ello; un momento.'); })) demo(); };
    const descargar = () => { setAviso(''); if (!llamar('actualizacion_descargar', [], (ok) => { if (!ok && vivo.current) setAviso('Ahora no puedo descargarla.'); })) demo(); };
    const cancelar = () => { if (!llamar('actualizacion_cancelar', [])) demo(); };
    const instalar = () => {
      setConfirmar(false); setAviso('');
      if (!llamar('actualizacion_instalar', [], (ok) => { if (!ok && vivo.current) setAviso('No pude empezar; vuelve a buscar.'); })) demo();
    };
    const pulsarInstalar = () => { if (b.conConfirmar) setConfirmar(true); else instalar(); };
    const omitir = (v) => { if (!llamar('actualizacion_omitir', [v], () => pedirInfo())) demo(); };
    const alIniciar = (e) => {
      const on = !!(e && e.target ? e.target.checked : e);
      setInfo((i) => ({ ...i, al_iniciar: on }));
      if (!llamar('actualizacion_al_iniciar', [on])) demo('Demo: se guarda en la app.');
    };

    const Icono = window.IconBolt || (() => null);
    const notas = recortarNotas(est.notas);
    const ultima = fmtFecha(info.ultima);
    const textoInstalar = modo === 'git' ? (est.fase === 'lista' ? 'Reiniciar ahora' : 'Actualizar y reiniciar') : 'Instalar y reiniciar';
    const confirmaTexto = modo === 'git'
      ? 'Traigo los cambios de git, instalo lo que falte y me reinicio. Si tienes trabajo sin commitear no toco nada.'
      : `Descargo la ${est.version || 'versión nueva'} si no la tengo (comprobada con su SHA-256), te cierro, se instala sola y me vuelvo a abrir. Tus datos se quedan como están.`;
    return (
      <Card id="aj-actualizaciones" eyebrow={<><Icono width={13} height={13}/> Sistema</>} title="Actualizaciones" tone={resaltada ? 'yellow' : 'blue'}>
        <div className={'ln-act' + (resaltada ? ' is-nueva' : '')}>
          <div className="ln-act-version">
            <span>Soy la versión <b>{info.version || '?'}</b> · {textoModo(modo)}</span>
            {resaltada && <Badge variant="yellow">¡Versión nueva!</Badge>}
          </div>
          {modo === 'carpeta' && (
            <p className="ln-act-nota">
              Esta copia no es la instalada ni un repositorio git, así que no me actualizo sola. Mis versiones nuevas están
              en <a href={info.pagina || URL_RELEASES} target="_blank" rel="noopener noreferrer">la página de Releases de GitHub</a>.
            </p>
          )}
          {modo === 'git' && (
            <p className="ln-act-nota">Me usas desde el código: busco los commits nuevos de git y «Actualizar y reiniciar» hace git pull e instala lo que falte.</p>
          )}
          {(est.mensaje || est.commits.length > 0) && (
            <div className="ln-act-estado" role="status">
              {est.mensaje && <p className={'ln-act-msg' + (est.fase === 'error' ? ' is-error' : '')}>{est.mensaje}</p>}
              {modo === 'git' && est.commits.length > 0 && (
                <ul className="ln-act-commits">{est.commits.slice(0, 10).map((c, i) => <li key={i}>· {c}</li>)}</ul>
              )}
              {modo === 'git' && est.fase === 'hay' && !est.limpio && (
                <p className="ln-act-msg is-error">Tienes {est.modificados.length || 'algunos'} archivo(s) sin guardar: no toco nada hasta que hagas commit (o lo descartes).</p>
              )}
              {notas && modo !== 'git' && ['hay', 'descargando', 'lista', 'al_dia'].includes(est.fase) && est.nueva && (
                <p className="ln-act-notas">{notas}</p>
              )}
              {b.enlace && est.pagina && modo !== 'carpeta' && (
                <p className="ln-act-msg">Puedes descargarla a mano en <a href={est.pagina} target="_blank" rel="noopener noreferrer">GitHub</a>.</p>
              )}
            </div>
          )}
          {(est.fase === 'descargando' && modo === 'instalada') || (est.fase === 'lista' && modo === 'instalada') ? (
            <div className="ln-act-barra">
              <div className="ln-vu" aria-hidden="true"><i style={{ width: `${est.pct}%` }} /></div>
              <span>{est.pct} %</span>
            </div>
          ) : null}
          {est.fase === 'descargando' && est.total > 0 && (
            <p className="ln-act-nota">{fmtMB(est.bytes)} de {fmtMB(est.total)}</p>
          )}
          {confirmar && (
            <div className="ln-act-confirma" role="alertdialog" aria-label="Confirmar la actualización">
              <p>{confirmaTexto}</p>
              <div className="ln-act-fila" style={{ margin: 0 }}>
                <Button size="sm" variant="primary" onClick={instalar}>Sí, {modo === 'git' ? 'actualizar' : 'instalar'}</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmar(false)}>Ahora no</Button>
              </div>
            </div>
          )}
          <div className="ln-act-fila">
            <Button size="sm" variant="secondary" disabled={!b.buscar} onClick={buscar}>
              {est.fase === 'buscando' ? 'Buscando…' : 'Buscar actualizaciones'}
            </Button>
            {b.instalar && !confirmar && <Button size="sm" variant="primary" onClick={pulsarInstalar}>{textoInstalar}</Button>}
            {b.descargar && !confirmar && <Button size="sm" variant="ghost" onClick={descargar}>Descargar ahora</Button>}
            {b.cancelar && <Button size="sm" variant="ghost" onClick={cancelar}>Cancelar</Button>}
            {b.omitir && !confirmar && <Button size="sm" variant="ghost" onClick={() => omitir(est.version)}>Omitir esta versión</Button>}
          </div>
          <div className="ln-toggle-row">
            <Switch label="Buscar al iniciar (una vez al día, nunca con un juego delante)" checked={info.al_iniciar} onChange={alIniciar} accent="blue" />
          </div>
          {(ultima || info.omitida) && (
            <p className="ln-act-nota" style={{ margin: '10px 0 0' }}>
              {ultima && <>La última vez que miré: {ultima}. </>}
              {info.omitida && <>Me pediste saltarte la {info.omitida}. </>}
              {info.omitida && <a href="#" onClick={(e) => { if (e && e.preventDefault) e.preventDefault(); omitir(''); }}>Volver a avisarme</a>}
            </p>
          )}
          {aviso && <p className="ln-act-msg is-error" role="status">{aviso}</p>}
          {sinPuente && !aviso && <p className="ln-act-nota" style={{ margin: '10px 0 0' }}>Demo: busco versiones nuevas desde la app.</p>}
        </div>
      </Card>
    );
  }

  Object.assign(window, {
    ActualizacionesCard,
    LuneActualizaciones: { normalizarEstado, normalizarInfo, fmtFecha, fmtMB, recortarNotas, botones, textoModo, FASES, URL_RELEASES },
  });
})();
