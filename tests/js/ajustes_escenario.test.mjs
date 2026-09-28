// tests/js/ajustes_escenario.test.mjs — integración de los cortes 9/10 en Ajustes de la piel web (settings.jsx):
// las tarjetas BailesCard (extra/bailes_mmd.jsx) y MinecraftCard (extra/minecraft.jsx) salen tras las de los
// cortes 7/8 (Discord), en ese orden. Sin esos .jsx cargados (backend viejo) Ajustes se dibuja igual.
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import { crearSandbox, KIT, buscar, senal } from './jsx_falso.mjs';

const SETTINGS = path.join(KIT, 'settings.jsx');
const ICONOS = ['IconCloud', 'IconCpu', 'IconTelegram', 'IconBrain', 'IconMic', 'IconVolume', 'IconBolt', 'IconMoon'];
const FOTO = {
  openrouter_key: '', openrouter_model: 'openrouter/auto', ollama_url: 'http://localhost:11434', ollama_model: 'm',
  telegram_token: '', telegram_admin_id: '', telegram_ordenes_pc: false, nombre: 'Lune', system_prompt: 'x',
  voz: false, memoria: true, acciones_ia: true, mascota_render: 'animado', interfaz_modo: 'web',
  vrm_webengine: false, vrm_modelos: [], autoinicio: false, aburrimiento_min: 10,
};

function montar({ conEscenario = true } = {}) {
  const lune = {
    get_config(cb) { cb(JSON.stringify({ ...FOTO })); },
    guardar_config(json, cb) { cb(JSON.stringify({ ok: true })); },
    cambiar_interfaz(modo, cb) { cb(JSON.stringify({ ok: true })); },
    dispositivos_audio(cb) { cb('{}'); },
    compat_borrador() {},
    mic_prueba: senal(),
  };
  const globales = {};
  for (const n of ICONOS) globales[n] = () => null;
  let h = null;
  const stub = (id) => () => h('div', { id });
  for (const n of ['AlarmasCard', 'PantallaGrandeCard', 'BaileCard', 'SentarseCard', 'ComidaCard', 'DiscordCard']) {
    globales[n] = stub(`stub-${n}`);
  }
  if (conEscenario) {
    globales.BailesCard = stub('stub-BailesCard');
    globales.MinecraftCard = stub('stub-MinecraftCard');
  }
  const S = crearSandbox({ archivos: [SETTINGS], lune, globales });
  h = S.h;
  const el = S.h(S.sb.SettingsPanel, { voiceOn: false, onVoice() {}, fx: { bg: false, sweep: true, micro: true },
    setFxKey: () => () => {} });
  return { S, el, arbol: S.render(el) };
}

const ids = (arbol) => buscar(arbol, (n) => n.props && typeof n.props.id === 'string' && n.props.id.startsWith('stub-'))
  .map((n) => n.props.id);

test('las tarjetas de bailes y Minecraft salen tras las de los cortes 7/8, en orden', () => {
  const { arbol } = montar();
  const orden = ids(arbol);
  const pos = (id) => orden.indexOf(id);
  for (const id of ['stub-BailesCard', 'stub-MinecraftCard', 'stub-DiscordCard']) assert.ok(pos(id) >= 0, id);
  assert.ok(pos('stub-DiscordCard') < pos('stub-BailesCard'));
  assert.ok(pos('stub-BailesCard') < pos('stub-MinecraftCard'));
});

test('sin extra/bailes_mmd.jsx ni extra/minecraft.jsx (backend viejo) Ajustes se dibuja igual', () => {
  const { arbol } = montar({ conEscenario: false });
  const orden = ids(arbol);
  assert.deepEqual(orden.filter((x) => /Bailes|Minecraft/.test(x)), []);
  assert.ok(orden.includes('stub-DiscordCard'));
});

test('index.html carga bailes_mmd.jsx y minecraft.jsx antes que app.jsx y después de settings.jsx', () => {
  const html = fs.readFileSync(path.join(KIT, 'index.html'), 'utf8');
  const i = (s) => html.indexOf(s);
  for (const s of ['src="settings.jsx"', 'src="extra/bailes_mmd.jsx"', 'src="extra/minecraft.jsx"', 'src="app.jsx"']) {
    assert.ok(i(s) >= 0, s);
  }
  assert.ok(i('src="settings.jsx"') < i('src="extra/bailes_mmd.jsx"'));
  assert.ok(i('src="extra/minecraft.jsx"') < i('src="app.jsx"'));
});
