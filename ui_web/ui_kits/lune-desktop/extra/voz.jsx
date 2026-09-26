/* Lune CD desktop — Voz de Lune y pack de sonidos de la mascota (Ajustes).
 *
 * VozCard({cfg, set}):    motor de salida (automático · edge-tts · gTTS · Kokoro), voz de edge-tts
 *                         agrupada por país con marca F/M, velocidad y tono de −50 a +50, acento de
 *                         gTTS, Kokoro en gris con las instrucciones si no está instalado, y «Probar».
 * PackSonidosCard({cfg, set}): pack de sonidos de reacción y volumen de los efectos.
 *
 * `cfg` y `set` son los de SettingsPanel (settings.jsx): `set(clave)(valor | evento)`. Claves planas,
 * como las aplanan get_config/guardar_config en ui/web_bridge.py:
 *   motor_salida (voz.motor_salida)   edge_voz  (voz.edge_voz)    edge_rate (voz.edge_rate, "+10%")
 *   edge_pitch   (voz.edge_pitch, "-5Hz")      gtts_tld  (voz.gtts_tld)    kokoro_voz (voz.kokoro_voz, opcional)
 *   pack_sonidos (avatar.pack_sonidos)         volumen_sfx (avatar.volumen_sfx, 0–1)
 *
 * Puente (QWebChannel, todo opcional):
 *   window.lune.voces_disponibles(cb)  → JSON de servicios.voces.catalogo():
 *        {edge:[{id, locale, genero, pais, nombre, multilingue}], multilingues:[…], gtts_tld:{tld: nombre},
 *         kokoro:{disponible, voces:{id: nombre}, mensaje}, actual:{motor, id, rate, pitch, tld},
 *         personaje, personaje_voz:{id?, motor?, rate?, pitch?, tld?}}
 *        (también vale una lista suelta de voces o el formato crudo de edge_tts.list_voices)
 *   window.lune.probar_voz(json, cb)   → bool. json = {motor, id, rate, pitch, tld, texto}: el formato de
 *                                        servicios.voces.params_desde (id = voz de edge o de Kokoro; "" con gTTS)
 *   window.lune.packs_sonido(cb)       → JSON [PackSonido.a_dict()] = [{id, nombre, autor, descripcion, eventos:{ev: n}}]
 *                                        o {packs:[…]}
 * Sin window.lune (demo en el navegador) usa la lista embebida y no suena nada.
 *
 * La voz propia del personaje activo (datos.json → personajes[i].voz) manda sobre la de aquí
 * (resolver_voz: personaje > config > por defecto): si la trae, la tarjeta lo avisa.
 *
 * Se registra solo: Object.assign(window, {VozCard, PackSonidosCard, LuneVoz}). Va dentro de una IIFE
 * porque Babel (preset env) convierte los const de nivel superior en var globales y pisaría los de
 * otros .jsx (CFG_DEMO, MOONS…).
 */
(function () {
  const { useState, useEffect, useMemo, useRef } = React;

  // ── Datos ──────────────────────────────────────────────────────────────────
  const PAISES = {
    'es-MX': 'México', 'es-AR': 'Argentina', 'es-BO': 'Bolivia', 'es-CL': 'Chile', 'es-CO': 'Colombia',
    'es-CR': 'Costa Rica', 'es-CU': 'Cuba', 'es-DO': 'República Dominicana', 'es-EC': 'Ecuador',
    'es-ES': 'España', 'es-GQ': 'Guinea Ecuatorial', 'es-GT': 'Guatemala', 'es-HN': 'Honduras',
    'es-NI': 'Nicaragua', 'es-PA': 'Panamá', 'es-PE': 'Perú', 'es-PR': 'Puerto Rico', 'es-PY': 'Paraguay',
    'es-SV': 'El Salvador', 'es-US': 'Estados Unidos', 'es-UY': 'Uruguay', 'es-VE': 'Venezuela',
  };
  const GRUPO_MULTI = 'Multilingües (hablan español con su acento)';

  // Respaldo si el puente no responde: las 45 voces es-* de edge-tts y las 12 multilingües.
  const ES_COMPACTO = 'AR:Elena F,Tomas M;BO:Sofia F,Marcelo M;CL:Catalina F,Lorenzo M;CO:Salome F,Gonzalo M;' +
    'CR:Maria F,Juan M;CU:Belkys F,Manuel M;DO:Ramona F,Emilio M;EC:Andrea F,Luis M;ES:Elvira F,Ximena F,Alvaro M;' +
    'GQ:Teresa F,Javier M;GT:Marta F,Andres M;HN:Karla F,Carlos M;MX:Dalia F,Jorge M;NI:Yolanda F,Federico M;' +
    'PA:Margarita F,Roberto M;PE:Camila F,Alex M;PR:Karina F,Victor M;PY:Tania F,Mario M;SV:Lorena F,Rodrigo M;' +
    'US:Paloma F,Alonso M;UY:Valentina F,Mateo M;VE:Paola F,Sebastian M';
  const MULTI_COMPACTO = 'en-US:Ava F,Emma F,Andrew M,Brian M;en-AU:William M;fr-FR:Vivienne F,Remy M;' +
    'de-DE:Seraphina F,Florian M;it-IT:Giuseppe M;ko-KR:Hyunsu M;pt-BR:Thalita F';

  function expandir(compacto, prefijo, sufijo) {
    const out = [];
    compacto.split(';').forEach((bloque) => {
      const [loc, lista] = bloque.split(':');
      lista.split(',').forEach((par) => {
        const [nombre, g] = par.trim().split(' ');
        out.push({ id: `${prefijo}${loc}-${nombre}${sufijo}`, genero: g });
      });
    });
    return out;
  }
  const VOCES_RESPALDO = [
    ...expandir(ES_COMPACTO, 'es-', 'Neural'),
    ...expandir(MULTI_COMPACTO, '', 'MultilingualNeural'),
  ];
  const GTTS_RESPALDO = [['com.mx', 'México'], ['es', 'España'], ['us', 'Estados Unidos']];
  const KOKORO_RESPALDO = [['ef_dora', 'Dora (femenina)'], ['em_alex', 'Alex (masculina)'], ['em_santa', 'Santa (masculina)']];
  // Kokoro v1.0: la primera letra del id es el idioma (e = español, a = EE. UU., b = Reino Unido…).
  const IDIOMAS_KOKORO = { e: 'Español', a: 'Inglés (EE. UU.)', b: 'Inglés (Reino Unido)' };
  const KOKORO_INSTALAR = 'Para la voz 100 % local (Kokoro) hace falta:\n    pip install kokoro-onnx\n' +
    '    (y espeak-ng del sistema, para el español)\ny los pesos en «modelos_voz/»:\n' +
    '    kokoro-v1.0.onnx y voices-v1.0.bin\n    https://github.com/thewh1teagle/kokoro-onnx/releases';
  const MOTORES = [
    ['auto', 'Automático', 'edge-tts y, si falla, gTTS'],
    ['edge', 'Edge (en línea)', 'Voces neuronales de Microsoft; necesita internet'],
    ['gtts', 'gTTS', 'Google Translate; voz simple, necesita internet'],
    ['kokoro', 'Kokoro (local)', 'Sin internet; corre en tu PC'],
  ];
  // Igual que servicios/voces.py (_RE_ID_EDGE): «es-MX-DaliaNeural», «en-US-AvaMultilingualNeural».
  const ID_VOZ = /^[a-z]{2,3}-[A-Z]{2,4}-[A-Za-z0-9-]*Neural$/;

  // ── Utilidades puras (window.LuneVoz, las usa tests/test_jsx_extra.py) ─────
  function generoDe(g) {
    const s = String(g || '').trim().toLowerCase();
    if (!s) return '';
    if (s.startsWith('f') || s.startsWith('muj')) return 'F';
    if (s.startsWith('m') || s.startsWith('h')) return 'M';   // male · masculino · hombre
    return '';
  }

  function normalizarVoz(v, multi) {
    if (!v) return null;
    const o = typeof v === 'string' ? { id: v } : v;
    const id = String(o.id || o.ShortName || o.short_name || o.voz || '').trim();
    if (!ID_VOZ.test(id)) return null;
    const partes = id.split('-');
    const locale = String(o.locale || o.Locale || partes.slice(0, 2).join('-'));
    const esMulti = !!(multi || o.multilingue || o.multi || /Multilingual/i.test(id));
    const base = partes[partes.length - 1].replace(/Multilingual/i, '').replace(/Neural$/i, '');
    return {
      id, locale, multi: esMulti,
      nombre: String(o.nombre || base || id),
      genero: generoDe(o.genero || o.Gender || o.sexo),
      pais: String(o.pais || PAISES[locale] || locale),
    };
  }

  function aPares(lista, claveId, claveNombre) {
    if (!lista) return [];
    if (Array.isArray(lista)) {
      return lista.map((x) => {
        if (Array.isArray(x)) return [String(x[0]), String(x[1] || x[0])];
        if (x && typeof x === 'object') return [String(x[claveId] || x.id || ''), String(x[claveNombre] || x.nombre || x[claveId] || x.id || '')];
        return [String(x), String(x)];
      }).filter((p) => p[0]);
    }
    if (typeof lista === 'object') return Object.keys(lista).map((k) => [k, String(lista[k] || k)]);
    return [];
  }

  const recortar = (v, max) => String(v == null ? '' : v).slice(0, max || 80);

  /** {motor, id, rate, pitch, tld} de un objeto del puente; {} si no trae nada útil. */
  function paramsDe(o) {
    if (!o || typeof o !== 'object' || Array.isArray(o)) return {};
    const out = {};
    ['motor', 'id', 'tld'].forEach((k) => { if (o[k] != null && String(o[k]).trim()) out[k] = recortar(o[k]).trim(); });
    // rate/pitch pueden venir como "+10%" / "-5Hz" o como número (forma corta del personaje)
    if (o.rate != null && String(o.rate).trim()) out.rate = typeof o.rate === 'number' ? aRate(o.rate) : recortar(o.rate, 12);
    if (o.pitch != null && String(o.pitch).trim()) out.pitch = typeof o.pitch === 'number' ? aPitch(o.pitch) : recortar(o.pitch, 12);
    return out;
  }

  /** Respuesta de voces_disponibles (JSON o ya parseada) → {edge, gtts, kokoro, motor_activo, actual, personaje…}. */
  function normalizarVoces(resp) {
    let r = resp;
    if (typeof r === 'string') { try { r = JSON.parse(r); } catch (e) { r = null; } }
    let edge = [], multis = [], gtts = [], kokoro = null, activo = '';
    let actual = {}, personaje = '', personajeVoz = {};
    if (Array.isArray(r)) edge = r;
    else if (r && typeof r === 'object') {
      edge = r.edge || r.voces || r.edge_voces || [];
      multis = r.multilingues || r.multi || [];
      gtts = aPares(r.gtts || r.gtts_tld || r.acentos, 'tld', 'nombre');
      kokoro = r.kokoro || null;
      actual = paramsDe(r.actual);
      personaje = recortar(r.personaje, 60).trim();
      personajeVoz = paramsDe(typeof r.personaje_voz === 'string' ? { id: r.personaje_voz } : r.personaje_voz);
      activo = String(r.motor_activo || r.motor || actual.motor || '');
    }
    const vistos = new Set();
    const voces = [];
    [[edge, false], [multis, true]].forEach(([lista, m]) => {
      (Array.isArray(lista) ? lista : []).forEach((x) => {
        const v = normalizarVoz(x, m);
        if (v && !vistos.has(v.id)) { vistos.add(v.id); voces.push(v); }
      });
    });
    const k = kokoro && typeof kokoro === 'object' ? kokoro : {};
    return {
      edge: voces.length ? voces : VOCES_RESPALDO.map((x) => normalizarVoz(x)),
      gtts: gtts.length ? gtts : GTTS_RESPALDO,
      kokoro: {
        disponible: !!k.disponible,
        voces: aPares(k.voces, 'id', 'nombre').length ? aPares(k.voces, 'id', 'nombre') : KOKORO_RESPALDO,
        mensaje: String(k.mensaje || k.instalar || KOKORO_INSTALAR),
      },
      motor_activo: activo,
      actual,
      personaje,
      personaje_voz: personajeVoz,
      respaldo: !voces.length,
    };
  }

  /** Voces de Kokoro ([id, nombre]) → [{grupo, voces}] por idioma (español primero). */
  function agruparKokoro(pares) {
    const grupos = new Map();
    (pares || []).forEach((p) => {
      const g = IDIOMAS_KOKORO[String(p[0]).charAt(0)] || 'Otros idiomas';
      if (!grupos.has(g)) grupos.set(g, []);
      grupos.get(g).push(p);
    });
    const orden = Object.values(IDIOMAS_KOKORO);
    const peso = (g) => (orden.includes(g) ? orden.indexOf(g) : orden.length);
    return [...grupos.keys()].sort((a, b) => (peso(a) - peso(b)) || a.localeCompare(b, 'es'))
      .map((g) => ({ grupo: g, voces: grupos.get(g) }));
  }

  /** Lo que se manda a probar_voz: el formato de servicios.voces.params_desde (+ texto). */
  function paramsPrueba(c, textoPrueba) {
    const cfg = c || {};
    const motor = MOTORES.some((m) => m[0] === cfg.motor_salida) ? cfg.motor_salida : 'auto';
    const id = motor === 'gtts' ? '' : motor === 'kokoro' ? String(cfg.kokoro_voz || 'ef_dora')
      : String(cfg.edge_voz || 'es-MX-DaliaNeural');
    return {
      motor, id,
      rate: aRate(cfg.edge_rate), pitch: aPitch(cfg.edge_pitch),
      tld: String(cfg.gtts_tld || 'com.mx'),
      texto: String(textoPrueba == null ? '' : textoPrueba).trim().slice(0, 200),
    };
  }

  /** «Dalia (México) · +10% · -5Hz» para enseñar una voz resuelta. */
  function describirParams(p, voces) {
    if (!p || typeof p !== 'object') return '';
    const partes = [];
    if (p.id) {
      const v = (voces || []).find((x) => x.id === p.id);
      partes.push(v ? `${v.nombre} (${v.multi ? v.locale : v.pais})` : p.id);
    } else if (p.motor) partes.push(p.motor);
    if (p.rate && numeroDe(p.rate) !== 0) partes.push(aRate(p.rate));
    if (p.pitch && numeroDe(p.pitch) !== 0) partes.push(aPitch(p.pitch));
    if (p.tld && !p.id) partes.push(`acento ${p.tld}`);
    return partes.join(' · ');
  }

  /** Voces → [{grupo, voces}] : México primero, países hispanos por nombre, otras, multilingües al final. */
  function agruparVoces(voces) {
    const grupos = new Map();
    (voces || []).forEach((v) => {
      const g = v.multi ? GRUPO_MULTI : v.pais;
      if (!grupos.has(g)) grupos.set(g, []);
      grupos.get(g).push(v);
    });
    const peso = (g) => (g === 'México' ? 0 : g === GRUPO_MULTI ? 3 : Object.values(PAISES).includes(g) ? 1 : 2);
    const orden = [...grupos.keys()].sort((a, b) => (peso(a) - peso(b)) || a.localeCompare(b, 'es'));
    return orden.map((g) => ({
      grupo: g,
      voces: grupos.get(g).slice().sort((a, b) =>
        ((a.genero || 'Z').localeCompare(b.genero || 'Z')) || a.nombre.localeCompare(b.nombre, 'es')),
    }));
  }

  function etiquetaVoz(v) {
    const extra = v.multi ? ` · ${v.locale}` : '';
    return `${v.nombre}${v.genero ? ` · ${v.genero}` : ''}${extra}`;
  }

  /** "+10%" → 10, "-5Hz" → -5; recorta a ±50 y tolera basura (→ 0). */
  function numeroDe(s) {
    const n = parseInt(String(s == null ? '' : s).replace(/[^\d+-]/g, ''), 10);
    if (!Number.isFinite(n)) return 0;
    return Math.max(-50, Math.min(50, n));
  }
  const conSigno = (n) => `${n >= 0 ? '+' : ''}${Math.round(n)}`;
  const aRate = (n) => `${conSigno(numeroDe(n))}%`;
  const aPitch = (n) => `${conSigno(numeroDe(n))}Hz`;

  /** Respuesta de packs_sonido → [{id, nombre, autor, eventos, muestra}], siempre con «default». */
  function normalizarPacks(resp) {
    let r = resp;
    if (typeof r === 'string') { try { r = JSON.parse(r); } catch (e) { r = null; } }
    const lista = Array.isArray(r) ? r : (r && Array.isArray(r.packs) ? r.packs : []);
    const out = [];
    const vistos = new Set();
    lista.forEach((p) => {
      const o = typeof p === 'string' ? { id: p } : (p || {});
      const id = String(o.id || o.carpeta || o.nombre || '').trim();
      if (!id || vistos.has(id)) return;
      vistos.add(id);
      const ev = Array.isArray(o.eventos) ? o.eventos.length : (o.eventos && typeof o.eventos === 'object' ? Object.keys(o.eventos).length : Number(o.eventos) || 0);
      out.push({
        id, nombre: String(o.nombre || id).slice(0, 60), autor: String(o.autor || '').slice(0, 60),
        descripcion: String(o.descripcion || '').slice(0, 300), eventos: ev, muestra: String(o.muestra || ''),
      });
    });
    if (!vistos.has('default')) out.unshift({ id: 'default', nombre: 'Lune (por defecto)', autor: 'Lune CD', descripcion: '', eventos: 0, muestra: '' });
    return out;
  }

  // ── Estilos propios (index.html no se toca) ────────────────────────────────
  function inyectarEstilos() {
    try {
      if (!window.document || document.getElementById('ln-x-voz-css')) return;
      const st = document.createElement('style');
      st.id = 'ln-x-voz-css';
      st.textContent = `
        .ln-x-range{ display:flex; flex-direction:column; gap:6px; min-width:0; }
        .ln-x-range-top{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
        .ln-x-range-val{ font-family:var(--font-mono); font-size:12px; color:var(--cyan-300); }
        .ln-x-range input[type=range]{ width:100%; accent-color:var(--cyan-500); cursor:pointer; }
        .ln-x-range input[type=range]:disabled{ cursor:not-allowed; opacity:.45; }
        .ln-x-link{ appearance:none; -webkit-appearance:none; background:none; border:none; padding:0; cursor:pointer;
          font:inherit; color:var(--cyan-400); text-decoration:underline; text-underline-offset:2px; }
        .ln-x-link:hover{ color:var(--cyan-300); }
        .ln-x-row{ display:flex; align-items:flex-end; gap:12px; flex-wrap:wrap; margin-top:14px; }
        .ln-x-row > .lune-field{ flex:1; min-width:200px; }
        .ln-x-estado{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted); margin:8px 0 0; }
        .ln-x-estado.is-error{ color:var(--yellow-500); }
      `;
      document.head.appendChild(st);
    } catch (e) { /* sin DOM (tests) */ }
  }

  // `set` de SettingsPanel si viene; si no (demo suelta), un estado local con la misma firma.
  function useCfg(cfg, set) {
    const [local, setLocal] = useState(() => ({ ...(cfg || {}) }));
    if (typeof set === 'function') return [cfg || {}, set];
    return [local, (k) => (e) => setLocal((c) => ({ ...c, [k]: (e && e.target) ? e.target.value : e }))];
  }

  function Deslizador({ id, label, min, max, step, value, onChange, fmt, hint, disabled }) {
    return (
      <div className="lune-field ln-x-range">
        <div className="ln-x-range-top">
          <label className="lune-field-label" htmlFor={id}>{label}</label>
          <span className="ln-x-range-val">{fmt ? fmt(value) : value}</span>
        </div>
        <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))} />
        {hint && <span className="lune-field-hint">{hint}</span>}
      </div>
    );
  }

  // ── VozCard ────────────────────────────────────────────────────────────────
  function VozCard({ cfg, set: setProp }) {
    const { Card, Button, Input, Badge } = window.LUNE;
    const [c, set] = useCfg(cfg, setProp);
    const [datos, setDatos] = useState(() => normalizarVoces(null));
    const [cargando, setCargando] = useState(!!window.lune);
    const [texto, setTexto] = useState('Hola, soy Lune. Así sueno ahora.');
    const [estado, setEstado] = useState({ msg: '', error: false });
    const [probando, setProbando] = useState(false);
    const [verKokoro, setVerKokoro] = useState(false);
    const vivo = useRef(true);

    useEffect(() => {
      inyectarEstilos();
      vivo.current = true;
      if (window.lune && typeof window.lune.voces_disponibles === 'function') {
        try {
          window.lune.voces_disponibles((j) => {
            if (!vivo.current) return;
            setDatos(normalizarVoces(j)); setCargando(false);
          });
        } catch (e) { setCargando(false); }
      } else setCargando(false);
      return () => { vivo.current = false; };
    }, []);

    const motor = MOTORES.some((m) => m[0] === c.motor_salida) ? c.motor_salida : 'auto';
    const kokoroOk = datos.kokoro.disponible;
    const edgeVoz = String(c.edge_voz || 'es-MX-DaliaNeural');
    const rate = numeroDe(c.edge_rate);
    const pitch = numeroDe(c.edge_pitch);
    const tld = String(c.gtts_tld || 'com.mx');
    const kokoroVoz = String(c.kokoro_voz || 'ef_dora');

    const grupos = useMemo(() => agruparVoces(datos.edge), [datos]);
    const gruposKokoro = useMemo(() => agruparKokoro(datos.kokoro.voces), [datos]);
    const pv = datos.personaje_voz || {};
    const propia = Object.keys(pv).length > 0;
    const ahora = describirParams(datos.actual, datos.edge);
    const conocida = datos.edge.some((v) => v.id === edgeVoz);
    const usaEdge = motor === 'auto' || motor === 'edge' || (motor === 'kokoro' && !kokoroOk);
    const usaGtts = motor === 'auto' || motor === 'gtts';

    const probar = () => {
      if (!window.lune || typeof window.lune.probar_voz !== 'function') {
        setEstado({ msg: 'Demo · sin backend: aquí no suena nada.', error: false }); return;
      }
      // Formato de servicios.voces.params_desde: lo que hay AHORA en la tarjeta, aunque no esté guardado.
      const payload = paramsPrueba({ ...c, motor_salida: motor, edge_voz: edgeVoz, gtts_tld: tld, kokoro_voz: kokoroVoz }, texto);
      if (!payload.texto) payload.texto = 'Hola, soy Lune.';
      setProbando(true); setEstado({ msg: 'Probando…', error: false });
      try {
        window.lune.probar_voz(JSON.stringify(payload), (r) => {
          if (!vivo.current) return;
          let ok = r;
          if (typeof r === 'string') { try { const o = JSON.parse(r); ok = typeof o === 'object' && o ? o.ok : o; } catch (e) { ok = r === 'true'; } }
          setProbando(false);
          setEstado(ok
            ? { msg: 'Sonando. Si no la oyes, revisa la salida de audio (Audio → Probar salida).', error: false }
            : { msg: 'No pude probar la voz: ¿falta edge-tts o no hay internet? Mira el aviso de Lune.', error: true });
        });
      } catch (e) { setProbando(false); setEstado({ msg: 'No pude pedir la prueba al backend.', error: true }); }
    };

    const Icono = window.IconVolume || (() => null);
    return (
      <Card eyebrow={<><Icono width={13} height={13}/> Voz · Salida</>} title="Cómo habla Lune" tone="cyan" tick>
        <p className="ln-card-nota">
          Elige motor, voz, velocidad y tono. «Probar» suena aunque la voz esté apagada y corta lo que esté diciendo.
          Los cambios se aplican al pulsar <b>Guardar configuración</b>.
        </p>

        <div className="lune-overline" style={{ marginBottom: 6 }}>Motor</div>
        <div className="ln-seg-row">
          {MOTORES.map(([k, t, desc]) => {
            const bloqueado = k === 'kokoro' && !kokoroOk;
            return (
              <Button key={k} variant={motor === k ? 'primary' : 'ghost'} size="sm" disabled={bloqueado}
                title={bloqueado ? 'Kokoro no está instalado (mira «Cómo instalarlo»)' : desc}
                onClick={() => set('motor_salida')(k)}>{t}</Button>
            );
          })}
          {datos.motor_activo && <Badge variant="ink" outline>ahora: {datos.motor_activo}</Badge>}
        </div>
        {ahora && <p className="ln-x-estado">Suena ahora (guardado): {ahora}</p>}
        {propia && (
          <p className="ln-x-estado is-error">
            {datos.personaje ? `«${datos.personaje}»` : 'El personaje activo'} tiene voz propia
            ({describirParams(pv, datos.edge) || pv.motor}) y manda sobre lo que elijas aquí: lo de esta tarjeta vale
            para los personajes sin voz. Se cambia en su ficha de datos.json (personajes → voz) o pidiéndoselo a Lune.
          </p>
        )}
        {!kokoroOk && (
          <p className={`ln-x-estado${motor === 'kokoro' ? ' is-error' : ''}`}>
            {motor === 'kokoro'
              ? 'Kokoro está elegido pero no instalado: mientras tanto Lune habla con edge-tts. '
              : 'Kokoro (voz sin internet) está en gris porque no está instalado. '}
            <button type="button" className="ln-x-link" onClick={() => setVerKokoro((v) => !v)}>
              {verKokoro ? 'Ocultar' : 'Cómo instalarlo'}
            </button>
          </p>
        )}
        {!kokoroOk && verKokoro && <pre className="ln-code">{datos.kokoro.mensaje}</pre>}

        {usaEdge && (
          <>
            <div style={{ height: 14 }} />
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-edge-voz">Voz de edge-tts</label>
              <select id="f-edge-voz" className="lune-input ln-select" value={edgeVoz} onChange={set('edge_voz')}>
                {!conocida && <option value={edgeVoz}>{edgeVoz} (actual)</option>}
                {grupos.map((g) => (
                  <optgroup key={g.grupo} label={g.grupo}>
                    {g.voces.map((v) => <option key={v.id} value={v.id}>{etiquetaVoz(v)}</option>)}
                  </optgroup>
                ))}
              </select>
              <span className="lune-field-hint">
                {cargando ? 'Cargando la lista de voces…'
                  : `${datos.edge.length} voces · F = femenina, M = masculina${datos.respaldo ? ' · lista sin conexión' : ''}. Las multilingües hablan español con su acento.`}
              </span>
            </div>
            <div style={{ height: 12 }} />
            <div className="ln-settings-grid">
              <Deslizador id="f-edge-rate" label="Velocidad" min={-50} max={50} step={1} value={rate}
                onChange={(n) => set('edge_rate')(aRate(n))} fmt={(n) => aRate(n)} hint="0 = normal; negativo, más despacio." />
              <Deslizador id="f-edge-pitch" label="Tono" min={-50} max={50} step={1} value={pitch}
                onChange={(n) => set('edge_pitch')(aPitch(n))} fmt={(n) => aPitch(n)} hint="En hercios: + más aguda, − más grave." />
            </div>
          </>
        )}

        {usaGtts && (
          <>
            <div style={{ height: 14 }} />
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-gtts-tld">Acento de gTTS{motor === 'auto' ? ' (si edge-tts falla)' : ''}</label>
              <select id="f-gtts-tld" className="lune-input ln-select" value={tld} onChange={set('gtts_tld')}>
                {!datos.gtts.some((p) => p[0] === tld) && <option value={tld}>{tld} (actual)</option>}
                {datos.gtts.map(([k, n]) => <option key={k} value={k}>{n} · {k}</option>)}
              </select>
              <span className="lune-field-hint">gTTS no tiene voces ni tono: solo cambia el acento.</span>
            </div>
          </>
        )}

        {motor === 'kokoro' && kokoroOk && (
          <>
            <div style={{ height: 14 }} />
            <div className="lune-field">
              <label className="lune-field-label" htmlFor="f-kokoro-voz">Voz de Kokoro</label>
              <select id="f-kokoro-voz" className="lune-input ln-select" value={kokoroVoz} onChange={set('kokoro_voz')}>
                {!datos.kokoro.voces.some((p) => p[0] === kokoroVoz) && <option value={kokoroVoz}>{kokoroVoz} (actual)</option>}
                {gruposKokoro.map((g) => (
                  <optgroup key={g.grupo} label={g.grupo}>
                    {g.voces.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
                  </optgroup>
                ))}
              </select>
              <span className="lune-field-hint">La primera frase tarda unos segundos: el modelo se carga una vez.</span>
            </div>
          </>
        )}

        <div className="ln-x-row">
          <Input id="f-voz-prueba" label="Frase de prueba" value={texto} maxLength={200} onChange={(e) => setTexto(e.target.value)} />
          <Button variant="ghost" size="sm" onClick={probar} disabled={probando}>
            <Icono width={13} height={13}/> {probando ? 'Probando…' : 'Probar'}
          </Button>
        </div>
        {estado.msg && <p className={`ln-x-estado${estado.error ? ' is-error' : ''}`}>{estado.msg}</p>}
      </Card>
    );
  }

  // ── PackSonidosCard ────────────────────────────────────────────────────────
  let promesaSfx = null;
  function asegurarSfx() {
    if (window.luneSfx) return Promise.resolve(window.luneSfx);
    if (promesaSfx) return promesaSfx;
    promesaSfx = new Promise((ok) => {
      try {
        const s = document.createElement('script');
        s.src = '../../lune_sfx.js';           // ui_web/lune_sfx.js desde ui_kits/lune-desktop/
        s.onload = () => ok(window.luneSfx || null);
        s.onerror = () => { promesaSfx = null; ok(null); };
        document.head.appendChild(s);
      } catch (e) { promesaSfx = null; ok(null); }
    });
    return promesaSfx;
  }

  function PackSonidosCard({ cfg, set: setProp }) {
    const { Card, Button, Badge } = window.LUNE;
    const [c, set] = useCfg(cfg, setProp);
    const [packs, setPacks] = useState(() => normalizarPacks(null));
    const [msg, setMsg] = useState('');
    const vivo = useRef(true);

    useEffect(() => {
      inyectarEstilos();
      vivo.current = true;
      if (window.lune && typeof window.lune.packs_sonido === 'function') {
        try { window.lune.packs_sonido((j) => { if (vivo.current) setPacks(normalizarPacks(j)); }); } catch (e) {}
      }
      return () => { vivo.current = false; };
    }, []);

    const actual = String(c.pack_sonidos || 'default');
    const pack = packs.find((p) => p.id === actual);
    const vol = Math.max(0, Math.min(1, Number(c.volumen_sfx == null || c.volumen_sfx === '' ? 0.7 : c.volumen_sfx) || 0));

    const escuchar = () => {
      if (vol <= 0) { setMsg('Volumen a 0: los efectos están apagados.'); return; }
      asegurarSfx().then((sfx) => {
        if (!vivo.current) return;
        if (!sfx) { setMsg('No pude cargar los efectos en esta página.'); return; }
        const muestra = pack && pack.muestra ? pack.muestra : 'drag_stop';
        Promise.resolve(sfx.tocar(muestra, { vol, pitch: [0.95, 1.05] }))
          .then((r) => { if (vivo.current) setMsg(r ? '' : 'Ese sonido no está disponible.'); })
          .catch(() => {});
      });
    };

    const Icono = window.IconMoon || (() => null);
    const IconoVol = window.IconVolume || (() => null);
    return (
      <Card eyebrow={<><Icono width={13} height={13}/> Mascota · Sonidos</>} title="Pack de sonidos" tone="blue">
        <p className="ln-card-nota">Los ruiditos de la mascota: arrastrarla, soltarla, comer, menús. Cada pack es una carpeta en <b>sonidos/</b>.</p>
        <div className="ln-settings-grid">
          <div className="lune-field">
            <label className="lune-field-label" htmlFor="f-pack-sfx">Pack</label>
            <select id="f-pack-sfx" className="lune-input ln-select" value={actual} onChange={set('pack_sonidos')}>
              {!pack && <option value={actual}>{actual} (no encontrado)</option>}
              {packs.map((p) => <option key={p.id} value={p.id}>{p.nombre}{p.autor ? ` · ${p.autor}` : ''}</option>)}
            </select>
            <span className="lune-field-hint">
              {pack && pack.descripcion ? `${pack.descripcion} · ` : ''}
              {pack && pack.eventos ? `${pack.eventos} eventos con sonido` : 'Si falta un sonido en el pack, suena el de Lune.'}
            </span>
          </div>
          <Deslizador id="f-vol-sfx" label="Volumen de los efectos" min={0} max={100} step={5} value={Math.round(vol * 100)}
            onChange={(n) => set('volumen_sfx')(Math.round(n) / 100)} fmt={(n) => (n <= 0 ? 'apagados' : `${n} %`)}
            hint="0 = sin efectos. No cambia el volumen de la voz." />
        </div>
        <div className="ln-audio-row">
          <Button variant="ghost" size="sm" onClick={escuchar}><IconoVol width={13} height={13}/> Escuchar</Button>
          {!pack && <Badge variant="yellow" outline>pack no encontrado: se usará el de Lune</Badge>}
        </div>
        {msg && <p className="ln-x-estado">{msg}</p>}
      </Card>
    );
  }

  Object.assign(window, {
    VozCard,
    PackSonidosCard,
    LuneVoz: {
      PAISES, VOCES_RESPALDO, GTTS_RESPALDO, generoDe, normalizarVoz, normalizarVoces, agruparVoces,
      agruparKokoro, etiquetaVoz, numeroDe, aRate, aPitch, paramsDe, paramsPrueba, describirParams, normalizarPacks,
    },
  });
})();
