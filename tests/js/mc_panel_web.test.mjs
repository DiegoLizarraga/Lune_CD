// tests/js/mc_panel_web.test.mjs — la tarjeta de Minecraft de Ajustes (extra/minecraft.jsx) con un
// window.luneEscenario de mentira: «Reinstalar el bot» no se puede pulsar con el bot en marcha
// (npm ci borraría node_modules, que el bot está usando; revisión final BM11).
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, senal, EXTRA, boton } from './jsx_falso.mjs';

const MC = path.join(EXTRA, 'minecraft.jsx');
const RANURAS = ['mc_estado_json', 'mc_config', 'mc_config_guardar', 'mc_bot_instalar', 'mc_bot_conectar', 'mc_bot_desconectar',
  'mc_orden', 'mc_decir', 'mc_log_detectar', 'mc_eventos'];
const SENALES = ['mc_estado', 'mc_evento', 'mc_chat', 'mc_log', 'vista_pedida'];
const CONFIG = { config: { reaccionar: true, ruta_log: '', voz_reacciones: false, auto_con_juego: true, decir_en_juego: true,
  resumen_al_salir: true, pensar_en_juego: false, reaccionar_otros: false },
bot: { host: 'localhost', port: 25565, version: '', usuario: '', dueno: 'Alex_22', pensar_cada_s: 45, defender: true,
  solo_dueno: true, estilo_frases: 'personaje' }, error: '' };
const estado = (bot) => ({ reaccionar: true, servicio: true, log: { activo: false }, requisitos: { node: 'v24.19.0', node_ok: true, npm: true },
  bot: { instalado: true, instalando: false, conectado: false, conectando: false, ...bot } });

function montar(bot) {
  let e = estado(bot);
  const llamadas = [];
  const obj = {};
  for (const s of SENALES) obj[s] = senal();
  const respuestas = {
    mc_estado_json: () => JSON.stringify(e),
    mc_config: () => JSON.stringify(CONFIG),
    mc_bot_instalar: () => JSON.stringify({ ok: true, texto: 'Instalando…', estado: e }),
    mc_eventos: () => JSON.stringify({ eventos: [] }),
  };
  for (const n of RANURAS) {
    obj[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push(n);
      const r = respuestas[n];
      if (cb) cb(typeof r === 'function' ? r(...args) : r);
    };
  }
  const S = crearSandbox({ archivos: [MC], globales: { luneEscenario: obj } });
  const el = S.h(S.sb.MinecraftCard);
  const poner = (b) => { e = estado(b); obj.mc_estado.emit(JSON.stringify(e)); };
  return { S, el, llamadas, poner };
}

test('«Reinstalar el bot» desactivado con el bot conectado o conectándose; libre al desconectar', () => {
  const { S, el, llamadas, poner } = montar({ conectado: true });
  let b = boton(S.render(el), 'Reinstalar el bot');
  assert.equal(b.props.disabled, true);
  assert.match(String(b.props.title), /Desconecta el bot/);
  poner({ conectando: true });
  assert.equal(boton(S.render(el), 'Reinstalar el bot').props.disabled, true);
  poner({});
  b = boton(S.render(el), 'Reinstalar el bot');
  assert.equal(b.props.disabled, false);
  b.props.onClick();
  assert.ok(llamadas.includes('mc_bot_instalar'));
});
