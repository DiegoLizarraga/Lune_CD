/*
 * app.jsx — limpieza de marcas en la burbuja (prueba real con qwen2.5:7b, 2026-09):
 *   · el modelo escribía marcas rotas o inventadas (|<ACT …>|, <|OPEN_URL …|>,
 *     <|mascota_bailar(…)|>, |<CHANGEOFVOZ …>|) y la página solo quitaba ACT/DELAY/CALL
 *     bien escritos, y SOLO durante el streaming: al terminar (`done`) se pintaba tal cual;
 *   · ahora limpiarMarcadores sigue las mismas reglas que lune_core/marcadores.py y se
 *     aplica también en `done`. «a | b» (tablas) y «x <| f |>» (F#) no se tocan.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, senal, KIT } from './jsx_falso.mjs';

function docFalso() {
  return {
    body: { classList: { toggle() {}, contains: () => false } },
    getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null,
  };
}
function cargar(lune = null) {
  const props = {};
  const stub = (n) => function (p) { props[n] = p; return null; };
  const S = crearSandbox({
    archivos: [path.join(KIT, 'app.jsx')], lune,
    globales: {
      document: docFalso(), localStorage: { getItem: () => null, setItem() {} },
      LUNE: { StatusPill: stub('StatusPill'), IconButton: stub('IconButton') },
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), CommandMenu: stub('CommandMenu'),
      SettingsPanel: stub('SettingsPanel'), Sidebar: stub('Sidebar'),
    },
  });
  return { S, props };
}
function luneFalso() {
  const base = { mascota_visible(cb) { cb(false); }, proveedores(cb) { cb('{}'); }, proveedor_elegido() {} };
  return new Proxy(base, { get(t, k) { if (!(k in t) && typeof k === 'string') t[k] = senal(); return t[k]; } });
}

// Respuestas REALES de la prueba (scratchpad/ollama_real/resultados.jsonl) → lo que se ve.
const CASOS = [
  ['¡Claro! Estoy abriendo la página de la NASA para ti.\n\n<|OPEN_URL https://www.nasa.gov/|>',
    '¡Claro! Estoy abriendo la página de la NASA para ti.'],
  ['¡Claro! |<mascota_sentarse(sitio="barra")>|', '¡Claro!'],
  ['|<ACT {"emotion":"neutral","intensity":0.8}>| Ahí me siento más cerca de ti. |<mascota_sentarse sitio="barra"|>',
    ' Ahí me siento más cerca de ti.'],
  ['¡Claro! |<CHANGEOFVOZ "es-AR-HoracioNeural">|', '¡Claro!'],
  ['Así lo he programado. |ACT {"emotion":"neutral", "intensity":0.5}| Por cierto…', 'Así lo he programado.  Por cierto…'],
  ['¿Te interesaría? <ACT {"emotion":"curious", "intensity":0.6}>', '¿Te interesaría?'],
  ['¡Hola! |<|ACT {"emotion":"wave","intensity":0.8}|>|<|DELAY 1.5|>', '¡Hola!'],
  ['Vale <|mascota_bailar(segundos=60, cancion="Danza el mono")|> ¡Qué divertido!', 'Vale  ¡Qué divertido!'],
  ['Te abro Google. <|CALL ["abrir_url", {"url": "https://www.google.com"}]|>', 'Te abro Google.'],
  ['Eco: < |CALL ["lanzar_app", {"app": "paint"}]|> fin', 'Eco:  fin'],
  // Ronda 3 de la prueba real: el CALL pegado al ACT («|>|CALL …|>») se quedaba visible.
  ['¡Perfecto! Voy a abrir la terminal.\n\n|<ACT {"emotion":"happy","intensity":0.7}|>|CALL ["abrir_terminal", {}]|>',
    '¡Perfecto! Voy a abrir la terminal.'],
];

test('limpiarMarcadores quita las marcas buenas, las rotas y las inventadas (respuestas reales)', () => {
  const { S } = cargar();
  const limpiar = S.sb.LuneLimpiarMarcadores;
  assert.equal(typeof limpiar, 'function');
  for (const [crudo, visto] of CASOS) assert.equal(limpiar(crudo), visto, crudo);
});

test('limpiarMarcadores: una marca a medio escribir al final no parpadea', () => {
  const limpiar = cargar().S.sb.LuneLimpiarMarcadores;
  assert.equal(limpiar('Hola <|AC'), 'Hola');
  assert.equal(limpiar('Hola <|CALL ["temporizador", {"seg'), 'Hola');
  assert.equal(limpiar('Hola |<mascota_sen'), 'Hola');
  assert.equal(limpiar('Hola <|'), 'Hola');
});

test('limpiarMarcadores no toca texto normal (tablas, código, comparaciones)', () => {
  const limpiar = cargar().S.sb.LuneLimpiarMarcadores;
  for (const t of ['col1 | col2 |', 'si a < b entonces c > d', 'usa x <| f |> y', '<b>negrita</b>', 'a |> b'])
    assert.equal(limpiar(t), t);
});

test('done también limpia: lo que no reconoció el backend no se pinta', () => {
  const L = luneFalso();
  const A = cargar(L);
  const app = A.S.h(A.S.sb.LuneApp);
  A.S.render(app);
  L.chunk.emit('¡Claro! Te abro la NASA. <|OPEN_URL https://www.na');
  A.S.render(app);
  let msgs = A.props.ChatStream.messages;
  assert.equal(msgs.slice(-1)[0].text, '¡Claro! Te abro la NASA.');
  L.done.emit('¡Claro! Te abro la NASA. <|OPEN_URL https://www.nasa.gov/|> |<ACT {"emotion":"happy"}>|', 'happy');
  A.S.render(app);
  msgs = A.props.ChatStream.messages;
  assert.equal(msgs.length, 1);
  assert.equal(msgs[0].text, '¡Claro! Te abro la NASA.');
  // Sin streaming previo: la burbuja nueva también sale limpia.
  L.done.emit('Listo |<mascota_sentarse(sitio="barra")>|', 'happy');
  A.S.render(app);
  msgs = A.props.ChatStream.messages;
  assert.equal(msgs.slice(-1)[0].text, 'Listo');
});

test('un <|ACT {…} sin cerrar no se come el texto hasta la marca siguiente', () => {
  const limpiar = cargar().S.sb.LuneLimpiarMarcadores;
  assert.equal(limpiar('Hola <|ACT {"emotion":"happy"} ¿qué tal? <|ACT {"emotion":"sad"}|> Adiós'),
    'Hola  ¿qué tal?  Adiós');
});
