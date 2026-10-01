/* Lune CD desktop — Probar cada apartado y «Comprobar que todo funciona» (Ajustes, 11.3).
 *
 * DiagnosticoCard     Ajustes → Sistema: «Comprobar que todo funciona». La lista por secciones (lo que traigo, tus
 *                     carpetas, librerías, tu equipo y red y servicios) con BIEN / MAL / NO APLICA y el detalle, que se
 *                     va pintando según llega cada comprobación; al final, el resumen. «Parar» la corta.
 * ProbarOpenRouter    ({cfg}) en la tarjeta de OpenRouter: «Probar clave» con lo ESCRITO (la máscara = la guardada):
 *                     la clave (no gasta tokens) y que el modelo exista.
 * ProbarOllama        ({cfg, set}) en la de Ollama: «Probar / Buscar modelos» con la URL escrita; los modelos salen
 *                     como chips y al pulsar uno se elige (set('ollama_model')).
 * ProbarTelegram      ({cfg}) en la de Telegram: «Probar bot»: el token, tu ID, Node.js 18+ y la carpeta del bot.
 * ProbarDictado       ({cfg, descargados}) en Audio: «Probar dictado»: graba 3 s con el micrófono elegido y lo
 *                     transcribe con el modelo de Whisper elegido. Si ese modelo no está bajado avisa antes: la
 *                     primera vez lo descargo (~145 MB el «base») y tarda.
 * window.LuneDiagnostico  utilidades puras (tests): normalizarEvento, normalizarPrueba, agrupar, marca, pesoWhisper…
 *
 * Habla con window.lune (ui/web_bridge.py; la lógica, sin Qt, en servicios/pruebas.py y servicios/diagnostico.py):
 *   diagnostico_iniciar() → bool · diagnostico_parar() → bool · señal diagnostico(json):
 *     {tipo: 'inicio', version, modo, secciones: [{id, nombre}], total} · {tipo: 'item', id, seccion, seccion_nombre,
 *     nombre, ok: true|false|null, detalle} · {tipo: 'fin', ok, resumen, fallan, cuentan, no_aplica, parado}
 *   openrouter_probar(json {openrouter_key, openrouter_model}) → json {ok, mensaje, modelo_ok, gratis, ms}
 *   ollama_probar(url) → json {ok, mensaje, modelos, url}
 *   telegram_probar(json {telegram_token, telegram_admin_id}) → json {ok, mensaje, bot, items: [{id, nombre, ok, detalle}]}
 *   dictado_probar(json {dispositivo_entrada, modelo_whisper, voz_idioma}) → bool · señal dictado_prueba(json
 *     {fase: grabando|descargando|transcribiendo|listo|error, ok, texto, mensaje})
 * Todo lo que llega se pinta como TEXTO PLANO (sin controles) y recortado. La clave y el token nunca vuelven.
 * Sin puente (navegador), una demo local. Se registra solo: Object.assign(window, {DiagnosticoCard, ProbarOpenRouter,
 * ProbarOllama, ProbarTelegram, ProbarDictado, LuneDiagnostico}).
 */
(function () {
  const { useState, useEffect, useRef } = React;

  const MARCAS = { bien: 'BIEN', mal: 'MAL', na: 'NO APLICA' };
  const FASES_DICTADO = ['grabando', 'descargando', 'transcribiendo', 'listo', 'error'];
  // Lo que pesa cada modelo de Whisper la primera vez (servicios/pruebas.WHISPER_MB).
  const WHISPER_MB = { tiny: 75, base: 145, small: 465, medium: 1500, 'large-v3': 3000 };
  const MAX_ITEMS = 120;

  const puente = () => window.lune || null;
  function hay(nombre) { const l = puente(); return !!(l && typeof l[nombre] === 'function'); }
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
  /** Texto plano: sin caracteres de control y recortado. */
  const txt = (v, max = 300) => (typeof v === 'string' || typeof v === 'number'
    ? String(v).replace(/[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max)
    : '');
  const ok3 = (v) => (v === true ? true : v === false ? false : null);

  // ── Utilidades puras ───────────────────────────────────────────────────────
  function marca(ok) { return ok === true ? MARCAS.bien : ok === false ? MARCAS.mal : MARCAS.na; }
  function varianteMarca(ok) { return ok === true ? 'cyan' : ok === false ? 'danger' : 'ink'; }

  /** Un evento de la señal diagnostico → forma estable (null si no vale). */
  function normalizarEvento(e) {
    const r = leer(e, null);
    if (!r || typeof r !== 'object' || Array.isArray(r)) return null;
    if (r.tipo === 'inicio') {
      const secciones = (Array.isArray(r.secciones) ? r.secciones : [])
        .filter((s) => s && typeof s.id === 'string')
        .map((s) => ({ id: txt(s.id, 30), nombre: txt(s.nombre, 60) || txt(s.id, 30) }));
      return { tipo: 'inicio', version: txt(r.version, 20), modo: txt(r.modo, 20), secciones,
        total: Math.max(0, Math.round(Number(r.total) || 0)) };
    }
    if (r.tipo === 'item') {
      const id = txt(r.id, 40);
      if (!id) return null;
      return { tipo: 'item', id, seccion: txt(r.seccion, 30), seccion_nombre: txt(r.seccion_nombre, 60) || txt(r.seccion, 30),
        nombre: txt(r.nombre, 80) || id, ok: ok3(r.ok), detalle: txt(r.detalle, 300) };
    }
    if (r.tipo === 'fin') {
      const n = (v) => Math.max(0, Math.round(Number(v) || 0));
      return { tipo: 'fin', ok: r.ok === true, resumen: txt(r.resumen, 300), fallan: n(r.fallan), cuentan: n(r.cuentan),
        no_aplica: n(r.no_aplica), parado: r.parado === true };
    }
    return null;
  }

  /** Respuesta de un «Probar» → {ok (true|false|null), mensaje, modelos, items, bot, ms}. */
  function normalizarPrueba(resp) {
    let r = leer(resp, null);
    if (typeof r === 'string') r = { ok: false, mensaje: r };
    if (typeof r === 'boolean') r = { ok: r };
    const o = r && typeof r === 'object' ? r : {};
    const modelos = (Array.isArray(o.modelos) ? o.modelos : []).map((m) => txt(m, 120)).filter(Boolean).slice(0, 80);
    const items = (Array.isArray(o.items) ? o.items : []).filter((i) => i && typeof i === 'object').slice(0, 10)
      .map((i) => ({ id: txt(i.id, 30), nombre: txt(i.nombre, 60), ok: ok3(i.ok), detalle: txt(i.detalle, 300) }));
    const ms = Number(o.ms);
    return { ok: ok3(o.ok), mensaje: txt(o.mensaje || o.error, 300) || (o.ok ? 'Funciona.' : 'No respondió.'),
      modelos, items, bot: txt(o.bot, 40), ms: Number.isFinite(ms) && ms >= 0 ? Math.round(ms) : null };
  }

  /** Los items por sección, en el orden de `secciones` (y las que no estaban, al final). */
  function agrupar(items, secciones) {
    const grupos = [];
    const porId = {};
    (secciones || []).forEach((s) => { porId[s.id] = { id: s.id, nombre: s.nombre, items: [] }; grupos.push(porId[s.id]); });
    (items || []).forEach((i) => {
      if (!porId[i.seccion]) { porId[i.seccion] = { id: i.seccion, nombre: i.seccion_nombre || i.seccion, items: [] }; grupos.push(porId[i.seccion]); }
      porId[i.seccion].items.push(i);
    });
    return grupos.filter((g) => g.items.length);
  }

  function pesoWhisper(modelo) { const mb = WHISPER_MB[modelo]; return mb ? `~${mb} MB` : ''; }

  function normalizarDictado(e) {
    const r = leer(e, {}) || {};
    const fase = FASES_DICTADO.includes(r.fase) ? r.fase : '';
    return { fase, ok: ok3(r.ok), texto: txt(r.texto, 300), mensaje: txt(r.mensaje, 300) };
  }

  // ── Demo sin backend ───────────────────────────────────────────────────────
  const DEMO_ITEMS = [
    { tipo: 'item', id: 'piel_web', seccion: 'recursos', seccion_nombre: 'Lo que traigo', nombre: 'Piel web (interfaz completa)', ok: true, detalle: 'ui_web/ui_kits/lune-desktop/index.html' },
    { tipo: 'item', id: 'carpeta_datos', seccion: 'datos', seccion_nombre: 'Tus carpetas', nombre: 'Carpeta de tus datos', ok: true, detalle: 'Demo' },
    { tipo: 'item', id: 'audio', seccion: 'equipo', seccion_nombre: 'Tu equipo', nombre: 'Micrófono y altavoces', ok: true, detalle: 'Veo 1 micrófono y 2 salidas.' },
    { tipo: 'item', id: 'openrouter', seccion: 'red', seccion_nombre: 'Red y servicios', nombre: 'Clave de OpenRouter (nube)', ok: null, detalle: 'Sin clave de OpenRouter (demo).' },
  ];

  // ── Estilos propios (index.html solo carga el .jsx) ────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-dg-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-dg-css';
      st.textContent = `
        .ln-dg-fila{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:12px; }
        .ln-dg-msg{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; overflow-wrap:anywhere; }
        .ln-dg-msg.is-error{ color:var(--yellow-500); }
        .ln-dg-msg.is-ok{ color:var(--cyan-300); }
        .ln-dg-sec{ font-family:var(--font-mono); font-size:11px; letter-spacing:.08em; text-transform:uppercase;
          color:var(--cyan-400); margin:14px 0 6px; }
        .ln-dg-item{ display:grid; grid-template-columns:auto 1fr; gap:4px 10px; align-items:baseline; padding:5px 0;
          border-bottom:1px solid var(--ink-800, rgba(255,255,255,.06)); }
        .ln-dg-nombre{ color:var(--text); font-size:13px; }
        .ln-dg-detalle{ grid-column:2; font-family:var(--font-mono); font-size:11px; color:var(--text-faint); overflow-wrap:anywhere; }
        .ln-dg-chips{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
        .ln-dg-chip{ appearance:none; -webkit-appearance:none; cursor:pointer; font-family:var(--font-mono); font-size:11px;
          padding:3px 9px; color:var(--cyan-300); background:var(--ink-900); border:var(--bw, 2px) solid var(--cyan-700); }
        .ln-dg-chip:hover, .ln-dg-chip.is-on{ background:var(--cyan-500); color:var(--ink-950); border-color:var(--cyan-500); }
        .ln-dg-barra{ height:4px; background:var(--ink-800, rgba(255,255,255,.08)); margin-top:10px; }
        .ln-dg-barra > i{ display:block; height:100%; background:var(--cyan-500); transition:width .2s; }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  /** {ok, mensaje} de un «Probar», con su insignia. */
  function Resultado({ r }) {
    const { Badge } = window.LUNE;
    if (!r) return null;
    return (
      <>
        <div className="ln-dg-fila">
          <Badge variant={varianteMarca(r.ok)}>{marca(r.ok)}{r.ms != null ? ` · ${r.ms} ms` : ''}</Badge>
        </div>
        <p className={`ln-dg-msg${r.ok === false ? ' is-error' : r.ok === true ? ' is-ok' : ''}`} role="status">{r.mensaje}</p>
      </>
    );
  }

  /** Estado de un botón «Probar» (pedir al puente, vivo al desmontar). → [r, probando, probar] */
  function usePrueba(ranura) {
    const [r, setR] = useState(null);
    const [probando, setProbando] = useState(false);
    const vivo = useRef(true);
    useEffect(() => { inyectarEstilos(); vivo.current = true; return () => { vivo.current = false; }; }, []);
    const probar = (args, demo) => {
      if (!puente()) { setR(normalizarPrueba(demo || { ok: null, mensaje: 'Demo · sin backend' })); return; }
      setProbando(true); setR(null);
      const via = llamar(ranura, args, (j) => {
        if (!vivo.current) return;
        setProbando(false); setR(normalizarPrueba(j));
      });
      if (!via) { setProbando(false); setR({ ok: false, mensaje: 'Esto no está disponible en esta versión de la app.', modelos: [], items: [], ms: null }); }
    };
    return [r, probando, probar];
  }

  // ── Probar por apartado ────────────────────────────────────────────────────
  function ProbarOpenRouter({ cfg }) {
    const { Button } = window.LUNE;
    const c = cfg || {};
    const [r, probando, probar] = usePrueba('openrouter_probar');
    const pedir = () => probar([JSON.stringify({ openrouter_key: String(c.openrouter_key || ''),
      openrouter_model: String(c.openrouter_model || '') })]);
    return (
      <div>
        <div className="ln-dg-fila">
          <Button variant="ghost" size="sm" onClick={pedir} disabled={probando}>{probando ? 'Probando…' : 'Probar clave'}</Button>
          <span className="lune-field-hint">Pruebo lo escrito (aunque no lo hayas guardado) sin gastar nada.</span>
        </div>
        <Resultado r={r} />
      </div>
    );
  }

  function ProbarOllama({ cfg, set }) {
    const { Button } = window.LUNE;
    const c = cfg || {};
    const [r, probando, probar] = usePrueba('ollama_probar');
    const pedir = () => probar([String(c.ollama_url || '')]);
    const elegir = (m) => { if (typeof set === 'function') set('ollama_model')(m); };
    return (
      <div>
        <div className="ln-dg-fila">
          <Button variant="ghost" size="sm" onClick={pedir} disabled={probando}>{probando ? 'Buscando…' : 'Probar / Buscar modelos'}</Button>
          <span className="lune-field-hint">Miro si Ollama responde en esa dirección y qué modelos tiene.</span>
        </div>
        <Resultado r={r} />
        {r && r.modelos.length > 0 && (
          <>
            <p className="ln-dg-msg">Pulsa uno para elegirlo (luego, Guardar):</p>
            <div className="ln-dg-chips">
              {r.modelos.map((m) => (
                <button key={m} type="button" className={`ln-dg-chip${m === c.ollama_model ? ' is-on' : ''}`}
                  onClick={() => elegir(m)}>{m}</button>
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  function ProbarTelegram({ cfg }) {
    const { Button, Badge } = window.LUNE;
    const c = cfg || {};
    const [r, probando, probar] = usePrueba('telegram_probar');
    const pedir = () => probar([JSON.stringify({ telegram_token: String(c.telegram_token || ''),
      telegram_admin_id: String(c.telegram_admin_id || '') })]);
    return (
      <div>
        <div className="ln-dg-fila">
          <Button variant="ghost" size="sm" onClick={pedir} disabled={probando}>{probando ? 'Probando…' : 'Probar bot'}</Button>
          <span className="lune-field-hint">El token, tu ID, Node.js 18+ y la carpeta del bot. No manda ningún mensaje.</span>
        </div>
        <Resultado r={r} />
        {r && r.items.length > 0 && r.items.map((i) => (
          <div key={i.id || i.nombre} className="ln-dg-item">
            <Badge variant={varianteMarca(i.ok)} outline={i.ok !== true}>{marca(i.ok)}</Badge>
            <span className="ln-dg-nombre">{i.nombre}</span>
            {i.detalle && <span className="ln-dg-detalle">{i.detalle}</span>}
          </div>
        ))}
      </div>
    );
  }

  function ProbarDictado({ cfg, descargados }) {
    const { Button } = window.LUNE;
    const c = cfg || {};
    const modelo = String(c.modelo_whisper || 'base');
    const bajado = Array.isArray(descargados) ? descargados.includes(modelo) : null;
    const [e, setE] = useState(null);
    const vivo = useRef(true);
    useEffect(() => {
      inyectarEstilos();
      vivo.current = true;
      const quitar = conectar('dictado_prueba', (j) => { if (vivo.current) setE(normalizarDictado(j)); });
      return () => { vivo.current = false; quitar(); };
    }, []);
    const enMarcha = !!(e && ['grabando', 'descargando', 'transcribiendo'].includes(e.fase));
    const probar = () => {
      if (!puente()) { setE({ fase: 'error', ok: null, texto: '', mensaje: 'Demo · sin backend' }); return; }
      setE({ fase: 'grabando', ok: null, texto: '', mensaje: 'Abriendo el micrófono…' });
      const via = llamar('dictado_probar', [JSON.stringify({ dispositivo_entrada: String(c.dispositivo_entrada || ''),
        modelo_whisper: modelo, voz_idioma: String(c.voz_idioma ?? 'es') })], (ok) => {
        // False: el motivo ya llegó por la señal; si no llegó nada, uno genérico.
        if (vivo.current && !ok) setE((x) => (x && x.fase === 'error' ? x
          : { fase: 'error', ok: false, texto: '', mensaje: 'Ahora no puedo probar el dictado: el micrófono está ocupado.' }));
      });
      if (!via) setE({ fase: 'error', ok: false, texto: '', mensaje: 'Esto no está disponible en esta versión de la app.' });
    };
    const aviso = bajado === false
      ? `La primera vez descargo el modelo «${modelo}» (${pesoWhisper(modelo) || 'unos MB'}): necesita internet y tarda un poco.`
      : 'Grabo 3 s con el micrófono y el modelo elegidos y te digo lo que entendí.';
    const clase = !e ? '' : e.ok === false || e.fase === 'error' ? ' is-error' : e.ok === true ? ' is-ok' : '';
    return (
      <div>
        <div className="ln-dg-fila">
          <Button variant="ghost" size="sm" onClick={probar} disabled={enMarcha}>
            {enMarcha ? (e.fase === 'grabando' ? 'Grabando…' : e.fase === 'descargando' ? 'Descargando…' : 'Transcribiendo…') : 'Probar dictado'}
          </Button>
          <span className="lune-field-hint">{aviso}</span>
        </div>
        {e && e.mensaje && <p className={`ln-dg-msg${clase}`} role="status">{e.mensaje}</p>}
      </div>
    );
  }

  // ── DiagnosticoCard ────────────────────────────────────────────────────────
  function DiagnosticoCard() {
    const { Card, Button, Badge } = window.LUNE;
    const [secciones, setSecciones] = useState([]);
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [fin, setFin] = useState(null);
    const [corriendo, setCorriendo] = useState(false);
    const [msg, setMsg] = useState('');
    const vivo = useRef(true);
    useEffect(() => {
      inyectarEstilos();
      vivo.current = true;
      const quitar = conectar('diagnostico', (j) => {
        if (!vivo.current) return;
        const ev = normalizarEvento(j);
        if (!ev) return;
        if (ev.tipo === 'inicio') { setSecciones(ev.secciones); setTotal(ev.total); setItems([]); setFin(null); setCorriendo(true); }
        else if (ev.tipo === 'item') setItems((xs) => [...xs.filter((x) => x.id !== ev.id), ev].slice(0, MAX_ITEMS));
        else { setFin(ev); setCorriendo(false); }
      });
      return () => { vivo.current = false; quitar(); };
    }, []);
    const comprobar = () => {
      setMsg('');
      if (!puente()) {
        setSecciones([]); setItems(DEMO_ITEMS.map(normalizarEvento)); setTotal(DEMO_ITEMS.length);
        setFin({ tipo: 'fin', ok: true, resumen: 'Demo · sin backend', fallan: 0, cuentan: 3, no_aplica: 1, parado: false });
        return;
      }
      setItems([]); setFin(null); setCorriendo(true);
      const via = llamar('diagnostico_iniciar', [], (ok) => {
        if (!vivo.current) return;
        if (!ok) setMsg('Ya estoy comprobando: espera a que acabe.');
      });
      if (!via) { setCorriendo(false); setMsg('Esto no está disponible en esta versión de la app.'); }
    };
    const parar = () => { llamar('diagnostico_parar', [], () => {}); };
    const grupos = agrupar(items, secciones);
    const pct = total ? Math.min(100, Math.round((items.length * 100) / total)) : 0;
    const Icono = window.IconBolt || (() => null);
    return (
      <Card id="aj-diagnostico" eyebrow={<><Icono width={13} height={13}/> Sistema · Diagnóstico</>} title="Comprobar que todo funciona"
        tone="cyan" tick={!!(fin && fin.ok)}>
        <p className="ln-card-nota">
          Miro lo que traigo, que pueda escribir en tus carpetas, tu micrófono y tus altavoces, y los servicios que usas
          (internet, OpenRouter, Ollama, Telegram y Node.js). Lo que no tienes configurado sale como «no aplica». Tus claves no
          salen de aquí.
        </p>
        <div className="ln-dg-fila">
          <Button variant="primary" size="sm" onClick={comprobar} disabled={corriendo}>{corriendo ? 'Comprobando…' : 'Comprobar que todo funciona'}</Button>
          {corriendo && <Button variant="ghost" size="sm" onClick={parar}>Parar</Button>}
          {corriendo && total > 0 && <span className="lune-field-hint">{items.length} de {total}</span>}
          {fin && <Badge variant={fin.ok ? 'cyan' : 'danger'}>{fin.ok ? 'TODO BIEN' : `FALLA${fin.fallan === 1 ? '' : 'N'} ${fin.fallan}`}</Badge>}
        </div>
        {corriendo && <div className="ln-dg-barra" aria-hidden="true"><i style={{ width: `${pct}%` }} /></div>}
        {msg && <p className="ln-dg-msg is-error" role="status">{msg}</p>}
        {fin && fin.resumen && <p className={`ln-dg-msg${fin.ok ? ' is-ok' : ' is-error'}`} role="status">{fin.resumen}</p>}
        {grupos.map((g) => (
          <div key={g.id}>
            <div className="ln-dg-sec">{g.nombre}</div>
            {g.items.map((i) => (
              <div key={i.id} className="ln-dg-item">
                <Badge variant={varianteMarca(i.ok)} outline={i.ok !== true}>{marca(i.ok)}</Badge>
                <span className="ln-dg-nombre">{i.nombre}</span>
                {i.detalle && <span className="ln-dg-detalle">{i.detalle}</span>}
              </div>
            ))}
          </div>
        ))}
      </Card>
    );
  }

  Object.assign(window, {
    DiagnosticoCard, ProbarOpenRouter, ProbarOllama, ProbarTelegram, ProbarDictado,
    LuneDiagnostico: { MARCAS, WHISPER_MB, marca, varianteMarca, normalizarEvento, normalizarPrueba, normalizarDictado,
      agrupar, pesoWhisper, hay },
  });
})();
