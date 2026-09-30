// tests/js/ajustes_vida.test.mjs — integración de los cortes 7/8 en Ajustes de la piel web (settings.jsx):
// las tarjetas SentarseCard, ComidaCard y DiscordCard (extra/vida.jsx) salen tras las de los cortes 5/6 y
// AutoinicioOpciones justo bajo el interruptor «Arrancar Lune junto con Windows», con `activo` = ese
// interruptor. Sin vida.jsx cargado (backend viejo) Ajustes se dibuja igual.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, KIT, buscar, interruptor, senal } from './jsx_falso.mjs';

const SETTINGS = path.join(KIT, 'settings.jsx');
const ICONOS = ['IconCloud', 'IconCpu', 'IconTelegram', 'IconBrain', 'IconMic', 'IconVolume', 'IconBolt', 'IconMoon'];
const FOTO = {
  openrouter_key: '', openrouter_model: 'openrouter/auto', ollama_url: 'http://localhost:11434', ollama_model: 'm',
  telegram_token: '', telegram_admin_id: '', telegram_ordenes_pc: false, nombre: 'Lune', system_prompt: 'x',
  voz: false, memoria: true, acciones_ia: true, asistente_render: 'animado', interfaz_modo: 'web',
  vrm_webengine: false, vrm_modelos: [], autoinicio: false, aburrimiento_min: 10,
};

function montar({ conVida = true, autoinicio = false } = {}) {
  const lune = {
    get_config(cb) { cb(JSON.stringify({ ...FOTO, autoinicio })); },
    guardar_config(json, cb) { cb(JSON.stringify({ ok: true })); },
    cambiar_interfaz(modo, cb) { cb(JSON.stringify({ ok: true })); },
    dispositivos_audio(cb) { cb('{}'); },
    compat_borrador() {},
    mic_prueba: senal(),
  };
  const globales = {};
  for (const n of ICONOS) globales[n] = () => null;
  let h = null;
  const stub = (id) => (props) => h('div', { id, 'data-activo': props && 'activo' in props ? String(props.activo) : '' });
  if (conVida) {
    globales.SentarseCard = stub('stub-sentarse');
    globales.ComidaCard = stub('stub-comida');
    globales.DiscordCard = stub('stub-discord');
    globales.AutoinicioOpciones = stub('stub-autoinicio');
  }
  for (const n of ['AlarmasCard', 'PantallaGrandeCard', 'BaileCard']) globales[n] = stub(`stub-${n}`);
  const S = crearSandbox({ archivos: [SETTINGS], lune, globales });
  h = S.h;
  const el = S.h(S.sb.SettingsPanel, { voiceOn: false, onVoice() {}, fx: { bg: false, sweep: true, micro: true },
    setFxKey: () => () => {} });
  return { S, el, arbol: S.render(el) };
}

const ids = (arbol) => buscar(arbol, (n) => n.props && typeof n.props.id === 'string' && n.props.id.startsWith('stub-'))
  .map((n) => n.props.id);
const stubDe = (arbol, id) => buscar(arbol, (n) => n.props && n.props.id === id)[0];

test('las tarjetas de sentarse, comida y Discord salen tras las de los cortes 5/6, en orden', () => {
  const { arbol } = montar();
  const orden = ids(arbol);
  const pos = (id) => orden.indexOf(id);
  for (const id of ['stub-sentarse', 'stub-comida', 'stub-discord', 'stub-autoinicio']) assert.ok(pos(id) >= 0, id);
  assert.ok(pos('stub-BaileCard') < pos('stub-sentarse'));
  assert.ok(pos('stub-sentarse') < pos('stub-comida') && pos('stub-comida') < pos('stub-discord'));
  assert.ok(pos('stub-autoinicio') < pos('stub-BaileCard'), 'las opciones del arranque, en Sistema (antes)');
});

test('AutoinicioOpciones sigue al interruptor «Arrancar Lune junto con Windows»', () => {
  const r = montar({ autoinicio: false });
  assert.equal(stubDe(r.arbol, 'stub-autoinicio').props['data-activo'], 'false');
  interruptor(r.arbol, 'Arrancar Lune junto con Windows').onChange({ target: { checked: true } });
  r.arbol = r.S.render(r.el);
  assert.equal(stubDe(r.arbol, 'stub-autoinicio').props['data-activo'], 'true');
  const r2 = montar({ autoinicio: true });
  assert.equal(stubDe(r2.arbol, 'stub-autoinicio').props['data-activo'], 'true');
});

test('sin extra/vida.jsx (backend viejo) Ajustes se dibuja igual', () => {
  const { arbol } = montar({ conVida: false });
  assert.deepEqual(ids(arbol).filter((x) => /sentarse|comida|discord|autoinicio/.test(x)), []);
  assert.ok(interruptor(arbol, 'Arrancar Lune junto con Windows'));
});
