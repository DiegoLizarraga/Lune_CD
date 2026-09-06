/* Lune CD desktop — Paneles de datos: Personajes · Memoria · Historial · Optimizar */

function PanelShell({ overline, title, children }) {
  return (
    <div className="ln-settings">
      <div className="ln-settings-inner">
        <header className="ln-settings-head">
          <div className="lune-overline">// {overline}</div>
          <h2 className="ln-settings-title"><span>{title}</span></h2>
        </header>
        {children}
      </div>
    </div>
  );
}

function PersonajesPanel() {
  const { Card, Button, Badge } = window.LUNE;
  const [lista, setLista] = React.useState([]);
  const cargar = () => { if (window.lune) window.lune.personajes_lista((j) => { try { setLista(JSON.parse(j)); } catch (e) {} }); };
  React.useEffect(cargar, []);
  const activar = (nombre) => { if (window.lune) window.lune.personaje_activar(nombre, () => cargar()); };
  return (
    <PanelShell overline="Roleplay" title="PERSONAJES">
      {lista.length === 0 && <p className="ln-empty">Sin personajes (o backend inactivo).</p>}
      {lista.map((p) => (
        <Card key={p.nombre} tone={p.activo ? 'cyan' : 'default'} tick={p.activo} title={p.nombre}
          eyebrow={p.activo ? <Badge variant="cyan">Activo</Badge> : null}>
          <p className="ln-panel-desc">{p.descripcion || '—'}</p>
          {!p.activo && (
            <div style={{ marginTop: 12 }}>
              <Button variant="ghost" size="sm" onClick={() => activar(p.nombre)}>Activar</Button>
            </div>
          )}
        </Card>
      ))}
    </PanelShell>
  );
}

function MemoriaPanel() {
  const { Card, Badge, Button } = window.LUNE;
  const [info, setInfo] = React.useState(null);
  const cargar = () => { if (window.lune) window.lune.memoria_info((j) => { try { setInfo(JSON.parse(j)); } catch (e) { setInfo({}); } }); };
  React.useEffect(cargar, []);
  const olvidar = (id) => { if (window.lune) window.lune.memoria_olvidar(id, () => cargar()); };
  const olvidarTodo = () => { if (window.lune && window.confirm('¿Borrar TODA la memoria de Lune?')) window.lune.memoria_olvidar_todo(() => cargar()); };
  const i = info || {};
  const st = i.stats || {};
  const rec = i.recuerdos || [];
  return (
    <PanelShell overline="Nodos persistentes" title="MEMORIA">
      <Card tone="blue" tick title={i.nombre ? `Usuario · ${i.nombre}` : 'Memoria de Lune'}>
        <div className="ln-badge-row">
          <Badge variant="ink" outline>{st.total_mensajes || 0} mensajes</Badge>
          {st.ultima_sesion && <Badge variant="ink" outline>últ. {String(st.ultima_sesion).slice(0, 10)}</Badge>}
          <Badge variant="cyan">{rec.length} recuerdos</Badge>
        </div>
        {rec.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Button variant="danger" size="sm" onClick={olvidarTodo}>Olvidar todo</Button>
          </div>
        )}
      </Card>
      {rec.map((r) => (
        <Card key={r.id} title={r.tipo || 'nota'}>
          <p className="ln-panel-desc">{r.contenido}</p>
          <div className="ln-panel-foot">
            <span className="ln-panel-meta">{String(r.fecha || '').slice(0, 10)}{r.tags && r.tags.length ? ' · ' + r.tags.join(', ') : ''}</span>
            <Button variant="ghost" size="sm" onClick={() => olvidar(r.id)}>Olvidar</Button>
          </div>
        </Card>
      ))}
      {rec.length === 0 && <p className="ln-empty">Aún no hay recuerdos. Dile "recuerda que…".</p>}
    </PanelShell>
  );
}

function ToolsPanel() {
  const { Card, Badge } = window.LUNE;
  const [data, setData] = React.useState({ activas: true, tools: [] });
  React.useEffect(() => {
    if (window.lune) window.lune.tools_lista((j) => { try { setData(JSON.parse(j)); } catch (e) {} });
  }, []);
  return (
    <PanelShell overline="Acciones de escritorio" title="TOOLS">
      <div className="ln-badge-row" style={{ marginBottom: 14 }}>
        <Badge variant={data.activas ? 'cyan' : 'ink'} outline={!data.activas}>
          {data.activas ? 'Activas' : 'Desactivadas en Ajustes'}
        </Badge>
      </div>
      {(data.tools || []).map((t) => (
        <Card key={t.clave} tone="cyan" tick title={t.nombre}>
          <p className="ln-panel-desc">{t.descripcion}</p>
          <div className="ln-panel-meta">Prueba: "{t.ejemplo}"</div>
        </Card>
      ))}
    </PanelShell>
  );
}

function HistorialPanel({ onCargar }) {
  const { Card, Button, Badge } = window.LUNE;
  const [lista, setLista] = React.useState([]);
  React.useEffect(() => {
    if (window.lune) window.lune.historial_lista((j) => { try { setLista(JSON.parse(j)); } catch (e) {} });
  }, []);
  const abrir = (id) => {
    if (window.lune) window.lune.historial_cargar(id, (j) => { let m = []; try { m = JSON.parse(j); } catch (e) {} onCargar && onCargar(m); });
  };
  return (
    <PanelShell overline="Conversaciones previas" title="HISTORIAL">
      {lista.length === 0 && <p className="ln-empty">Sin conversaciones guardadas.</p>}
      {lista.map((s) => (
        <Card key={s.id} title={s.titulo || 'Conversación'}
          eyebrow={s.proveedor ? <Badge variant="ink" outline>{s.proveedor}</Badge> : null}>
          <div className="ln-panel-meta">
            {String(s.actualizado || s.creado || '').slice(0, 16).replace('T', ' ')} · {s.mensajes || 0} mensajes{s.personaje ? ' · ' + s.personaje : ''}
          </div>
          <div style={{ marginTop: 12 }}>
            <Button variant="ghost" size="sm" onClick={() => abrir(s.id)}>Abrir</Button>
          </div>
        </Card>
      ))}
    </PanelShell>
  );
}

function OptimizarPanel() {
  const { Card, Badge } = window.LUNE;
  const [info, setInfo] = React.useState(null);
  React.useEffect(() => {
    const cargar = () => { if (window.lune) window.lune.sistema_info((j) => { try { setInfo(JSON.parse(j)); } catch (e) {} }); };
    cargar();
    const t = setInterval(cargar, 3000);
    return () => clearInterval(t);
  }, []);
  const i = info || {};
  const Stat = ({ label, val }) => (
    <Card tone="cyan" tick title={val == null ? '—' : `${val}%`}>
      <div className="ln-panel-meta">{label}</div>
    </Card>
  );
  return (
    <PanelShell overline="Rendimiento" title="OPTIMIZAR">
      <div className="ln-stat-grid">
        <Stat label="CPU" val={i.cpu} />
        <Stat label="RAM" val={i.ram} />
        <Stat label="Disco" val={i.disco} />
      </div>
      <Card title="Procesos más pesados">
        {(i.procesos || []).map((p) => (
          <div className="ln-proc-row" key={p.pid}>
            <span className="ln-proc-name">{p.nombre}</span>
            <Badge variant="ink" outline>{p.ram_str || ''}</Badge>
          </div>
        ))}
        {(!i.procesos || i.procesos.length === 0) && <p className="ln-empty">—</p>}
      </Card>
    </PanelShell>
  );
}

Object.assign(window, { PersonajesPanel, MemoriaPanel, HistorialPanel, OptimizarPanel, ToolsPanel });
