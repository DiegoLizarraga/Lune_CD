/*
 * Web principal de los cortes 9 y 10 en el sandbox de jsx_falso.mjs (sin navegador):
 *   · extra/bailes_mmd.jsx: BailesPanel (lista y buscador, reproductor, al terminar, en el sitio, volumen diferido,
 *     favoritos, ajustes por baile, quitar con confirmación, importar, aviso «sin esqueleto», títulos como texto) y
 *     BailesCard, con y sin backend (window.luneEscenario);
 *   · extra/minecraft.jsx: MinecraftPanel (órdenes, decir, eventos, chat del juego SOLO como texto, registro del bot) y
 *     MinecraftCard (reacciones, «Detectar», datos del bot validados, aviso de suplantación y de online-mode=false,
 *     instalar el bot solo con su botón y su progreso, conectar);
 *   · app.jsx: vistas «bailes» y «minecraft», vista_pedida → 'lune-vista' y entradas del menú; apariencia.jsx: icono.
 * Lo lanza tests/test_index_html_c910.py (y test_js_modulos.py con el resto).
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { crearSandbox, senal, KIT, EXTRA, buscar, porId, boton, botones, todoTexto, conClase, interruptor, texto } from './jsx_falso.mjs';

const BAILES = path.join(EXTRA, 'bailes_mmd.jsx');
const MC = path.join(EXTRA, 'minecraft.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
const ev = (v) => ({ target: { value: v, checked: v } });
const ID = '0123456789ab';
const ID2 = 'fedcba987654';

const RANURAS = ['bailes_lista', 'bailes_refrescar', 'mmd_estado_json', 'mmd_reproducir', 'mmd_pausa', 'mmd_parar', 'mmd_siguiente',
  'mmd_anterior', 'mmd_config_guardar', 'baile_meta_guardar', 'baile_favorito', 'baile_desactivar', 'bailes_importar', 'baile_quitar',
  'bailes_abrir_carpeta', 'mc_estado_json', 'mc_config', 'mc_config_guardar', 'mc_bot_instalar', 'mc_bot_conectar',
  'mc_bot_desconectar', 'mc_orden', 'mc_decir', 'mc_log_detectar', 'mc_eventos'];
const SENALES = ['bailes_cambio', 'mmd_estado', 'mmd_importado', 'vista_pedida', 'mc_estado', 'mc_evento', 'mc_chat', 'mc_log'];

/** window.luneEscenario falso: ranuras que apuntan y responden por callback, y señales. */
function puenteFalso(respuestas = {}) {
  const llamadas = [];
  const obj = {};
  for (const s of SENALES) obj[s] = senal();
  for (const n of RANURAS) {
    obj[n] = (...args) => {
      const cb = typeof args[args.length - 1] === 'function' ? args.pop() : null;
      llamadas.push([n, ...args]);
      const r = respuestas[n];
      const v = typeof r === 'function' ? r(...args) : r;
      if (cb) cb(v);
    };
  }
  return { obj, llamadas, respuestas, de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)), limpiar: () => { llamadas.length = 0; } };
}
const cargar = (archivos, esc = null, globales = {}) => crearSandbox({ archivos, globales: { ...(esc ? { luneEscenario: esc } : {}), ...globales } });

const LISTA = [
  { id: ID, titulo: '<b>Senbonzakura</b>', tipo: 'vmd', autor_cancion: 'Kurousa-P', autor_mmd: 'Yu', duracion: 245, audio: true, favorito: false,
    offset_ms: 0, brazo_a_grados: 35, en_el_sitio: null },
  { id: ID2, titulo: 'Saludo', tipo: 'vrma', duracion: 4, audio: false, desactivado: true, problema: '' },
  { id: '../../x', titulo: 'malo' },
];
const ESTADO = { fase: 'sonando', id: ID, titulo: 'Senbonzakura', autor: 'Kurousa-P', t: 61, total: 245, modo: 'vrm', al_terminar: 'parar',
  volumen: 0.25, en_el_sitio: true, pausado: false, modo_mascota: 'vrm', sin_esqueleto: false, servicio: true };

function backendBailes(estado = ESTADO) {
  let e = { ...estado };
  const P = puenteFalso({
    bailes_lista: () => JSON.stringify({ bailes: LISTA, servicio: true }),
    bailes_refrescar: true,
    mmd_estado_json: () => JSON.stringify(e),
    mmd_reproducir: (id) => JSON.stringify({ ok: true, texto: '¡A bailar «Senbonzakura»!', estado: e = { ...e, fase: 'sonando', id: id || ID } }),
    mmd_pausa: () => JSON.stringify({ ok: true, estado: e = { ...e, fase: e.pausado ? 'sonando' : 'pausado', pausado: !e.pausado } }),
    mmd_parar: () => JSON.stringify({ ok: true, estado: e = { ...e, fase: 'parado', id: '', titulo: '' } }),
    mmd_siguiente: () => JSON.stringify({ ok: false, texto: 'No hay más bailes.', estado: e }),
    mmd_anterior: () => JSON.stringify({ ok: true, texto: '¡A bailar «Saludo»!', estado: e }),
    mmd_config_guardar: (j) => JSON.stringify({ ok: true, error: '', estado: e = { ...e, ...JSON.parse(j) } }),
    baile_meta_guardar: () => JSON.stringify({ ok: true, texto: 'Guardado.' }),
    baile_favorito: true, baile_desactivar: true, bailes_importar: true, bailes_abrir_carpeta: true,
    baile_quitar: () => JSON.stringify({ ok: true, texto: 'Lo moví a bailes/.quitados.' }),
  });
  return { P, estado: () => e };
}
const fila = (a, id) => buscar(a, (n) => n.props && n.props['data-id'] === id)[0];

// ── Registro y utilidades puras ──────────────────────────────────────────────
test('los dos archivos se registran solos sin pisar globales', () => {
  assert.deepEqual(plano(cargar([BAILES]).nuevas.sort()), ['BailesCard', 'BailesPanel', 'LuneBailesWeb']);
  assert.deepEqual(plano(cargar([MC]).nuevas.sort()), ['LuneMinecraftWeb', 'MinecraftCard', 'MinecraftPanel']);
});

test('LuneBailesWeb: normalización, tiempos y textos', () => {
  const B = cargar([BAILES]).sb.LuneBailesWeb;
  assert.equal(B.normalizarBaile({ id: '../x' }), null);
  assert.equal(B.normalizarBaile({ id: 'ABCDEF012345' }), null, 'solo hex en minúsculas, como los ids de la biblioteca');
  const b = B.normalizarBaile({ id: ID, titulo: '\u202eHola\u0000', tipo: 'exe', duracion: Infinity, offset_ms: 900, brazo_a_grados: 60, ruta: 'C:/x' });
  assert.deepEqual(plano(b), { id: ID, titulo: 'Hola', tipo: '', autor_cancion: '', autor_mmd: '', duracion: null, audio: false,
    favorito: false, desactivado: false, problema: '', aviso: '', offset_ms: 0, brazo_a_grados: 35, en_el_sitio: null, bpm: null });
  const l = B.normalizarLista({ bailes: [...LISTA, LISTA[0]], servicio: true });
  assert.deepEqual(plano(l.bailes.map((x) => x.id)), [ID, ID2]);
  assert.equal(B.normalizarLista(Array.from({ length: 600 }, (_, i) => ({ id: i.toString(16).padStart(12, '0') }))).bailes.length, 500);
  const e = B.normalizarEstado({ fase: 'bailoteo', modo_mascota: 'sprites', t: -1, total: 1e9, al_terminar: 'bucle' });
  assert.equal(e.fase, 'parado');
  assert.equal(e.sin_esqueleto, true);
  assert.equal(e.t, 0);
  assert.equal(e.total, 0);
  assert.equal(e.al_terminar, 'parar');
  assert.equal(B.mmss(245.9), '4:05');
  assert.equal(B.tiempoVisible({ fase: 'sonando', t: 10, total: 11, pausado: false }, 1000, 1500), 10.5);
  assert.equal(B.tiempoVisible({ fase: 'sonando', t: 10, total: 11, pausado: false }, 1000, 9000), 11, 'como mucho el total');
  assert.equal(B.tiempoVisible({ fase: 'pausado', t: 10, total: 100, pausado: true }, 1000, 9000), 10, 'en pausa no avanza');
  const s = (o) => B.textoEstado(B.normalizarEstado({ servicio: true, ...o }));
  assert.match(s({ fase: 'cargando', titulo: 'X', analizando: true }), /escuchando el ritmo/);
  assert.match(s({ fase: 'pausado', pausado: true, cedida: true, titulo: 'X' }), /juego, la alarma/);
  assert.match(s({ pendiente: true, fase: 'cargando', titulo: 'X' }), /Saco a la mascota/);
  assert.match(B.textoEstado(B.normalizarEstado({})), /necesita la app/);
});

test('LuneMinecraftWeb: estado, chat como texto, validación del bot y textos', () => {
  const M = cargar([MC]).sb.LuneMinecraftWeb;
  const e = M.normalizarEstado({ servicio: true, bot: { instalado: true, conectado: true, nick: '<script>', vida: 99, lluvia: 'sí' },
    requisitos: { node: 'v24.1.0; rm -rf', node_ok: null } });
  assert.equal(e.bot.nick, '');
  assert.equal(e.bot.vida, null);
  assert.equal(e.bot.lluvia, null);
  assert.equal(e.requisitos.node, null);
  assert.equal(e.requisitos.node_ok, null, 'None = comprobando');
  assert.match(M.textoBot(M.normalizarEstado({ servicio: true, requisitos: { node_ok: null } })), /Comprobando Node/);
  assert.match(M.textoBot(M.normalizarEstado({ servicio: true, requisitos: { node_ok: false } })), /Node\.js 18/);
  assert.match(M.textoBot(M.normalizarEstado({ servicio: true, requisitos: { node_ok: true } })), /no está instalado/);
  assert.deepEqual(plano(M.normalizarChat({ de: 'Steve', texto: '<b>hola</b>\u0007', t: 5, extra: 1 })), { de: 'Steve', texto: '<b>hola</b>', t: 5 });
  assert.equal(M.normalizarChat({ de: '<img>', texto: 'x' }), null);
  assert.equal(M.normalizarChat({ de: 'Alex', texto: '\u0000' }), null);
  assert.equal(M.normalizarEvento({ tipo: '<b>', texto: 'x' }), null);
  assert.equal(M.normalizarEvento({ tipo: 'muerte', texto: 'uy', fuente: 'javascript' }).fuente, '');
  const ok = { host: 'localhost', port: 25565, version: '', usuario: '', dueno: 'Steve_1', pensar_cada_s: 45 };
  assert.equal(M.validarBot(ok).ok, true);
  const mal = M.validarBot({ host: 'http://x', port: 70000, version: 'última', usuario: 'yo', dueno: 'a b', pensar_cada_s: 5 });
  assert.deepEqual(Object.keys(mal.errores).sort(), ['dueno', 'host', 'pensar_cada_s', 'port', 'usuario', 'version']);
  assert.equal(M.validarBot({ ...ok, usuario: 'steve_1' }).errores.usuario, 'No puede llamarse igual que tú.');
});

// ── BailesPanel con backend ───────────────────────────────────────────────────
test('BailesPanel: pide la lista, refresca y pinta los bailes como texto', () => {
  const { P } = backendBailes();
  const S = cargar([BAILES], P.obj);
  const el = S.h(S.sb.BailesPanel);
  const a = S.render(el);
  assert.deepEqual(plano(P.de('bailes_lista')), [['']]);
  assert.equal(P.de('bailes_refrescar').length, 1);
  assert.equal(P.de('mmd_estado_json').length, 1);
  assert.ok(fila(a, ID) && fila(a, ID2) && !fila(a, '../../x'));
  assert.match(texto(fila(a, ID)), /<b>Senbonzakura<\/b>/, 'el título sale tal cual, como texto');
  assert.equal(buscar(a, (n) => n.type === 'b').length, 0, 'nunca se interpreta como HTML');
  assert.match(texto(fila(a, ID2)), /sin canción/);
  assert.ok(fila(a, ID).props.className.includes('is-actual'), 'el que suena');
  assert.ok(fila(a, ID2).props.className.includes('is-off'), 'no sale al azar');
  assert.match(todoTexto(a), /Bailando «Senbonzakura» · Kurousa-P/);
  assert.match(todoTexto(a), /1:01/);
  assert.equal(conClase(a, 'ln-bl-aviso').length, 0, 'VRM: sin aviso de esqueleto');
  // la lista nueva por la señal
  P.obj.bailes_cambio.emit(JSON.stringify({ bailes: [LISTA[1]], servicio: true }));
  const b = S.render(el);
  assert.ok(!fila(b, ID) && fila(b, ID2));
});

test('BailesPanel: buscar (diferido), bailar, pausa, parar, siguiente y anterior', () => {
  const { P } = backendBailes({ ...ESTADO, fase: 'parado', id: '', titulo: '' });
  const S = cargar([BAILES], P.obj);
  const el = S.h(S.sb.BailesPanel);
  let a = S.render(el);
  porId(a, 'f-bl-buscar').props.onChange(ev('senbon'));
  S.avanzar(299);
  assert.equal(P.de('bailes_lista').length, 1);
  S.avanzar(1);
  assert.deepEqual(plano(P.de('bailes_lista').slice(-1)), [['senbon']]);
  a = S.render(el);
  buscar(fila(a, ID).hijos, (n) => n.type === 'button' && texto(n) === 'Bailar')[0].props.onClick();
  assert.deepEqual(plano(P.de('mmd_reproducir')), [[ID]]);
  a = S.render(el);
  assert.match(todoTexto(a), /¡A bailar «Senbonzakura»!/);
  boton(a, '⏸ Pausa').props.onClick();
  a = S.render(el);
  assert.ok(boton(a, '▶ Seguir'), 'en pausa: «Seguir» (D5: mismo punto)');
  boton(a, '▶ Seguir').props.onClick();
  assert.equal(P.de('mmd_pausa').length, 2, 'seguir es otra pausa (alterna), no reproducir de nuevo');
  a = S.render(el);
  boton(a, '⏹ Parar').props.onClick();
  a = S.render(el);
  assert.equal(boton(a, '⏹ Parar').props.disabled, true);
  buscar(a, (n) => n.type === 'button' && n.props['aria-label'] === 'Siguiente')[0].props.onClick();
  assert.match(todoTexto(S.render(el)), /No hay más bailes/);
  buscar(a, (n) => n.type === 'button' && n.props['aria-label'] === 'Anterior')[0].props.onClick();
  assert.equal(P.de('mmd_anterior').length, 1);
  boton(S.render(el), '▶ Bailar').props.onClick();
  assert.deepEqual(plano(P.de('mmd_reproducir').slice(-1)), [['']], 'sin baile elegido: el último o el primero');
});

test('BailesPanel: al terminar, en el sitio, volumen diferido y el aviso sin esqueleto', () => {
  const { P } = backendBailes({ ...ESTADO, modo_mascota: 'animado', modo: 'animado' });
  const S = cargar([BAILES], P.obj);
  const el = S.h(S.sb.BailesPanel);
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-bl-aviso').length, 1);
  assert.match(todoTexto(a), /no tiene esqueleto: baila a su manera/);
  boton(a, 'Al azar').props.onClick();
  interruptor(S.render(el), 'Bailar en el sitio').onChange({ target: { checked: false } });
  porId(S.render(el), 'f-bl-volumen').props.onChange(ev('60'));
  porId(S.render(el), 'f-bl-volumen').props.onChange(ev('65'));
  assert.deepEqual(plano(P.de('mmd_config_guardar').map((l) => JSON.parse(l[0]))), [{ al_terminar: 'aleatorio' }, { en_el_sitio: false }]);
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(P.de('mmd_config_guardar').slice(-1)[0][0])), { volumen: 0.65 });
  a = S.render(el);
  assert.equal(boton(a, 'Al azar').props['data-variant'], 'primary');
  assert.equal(porId(a, 'f-bl-volumen').props.value, 65);
});

test('BailesPanel: favorito, ajustes del baile, quitar con confirmación, importar y carpeta', () => {
  const { P } = backendBailes();
  const S = cargar([BAILES], P.obj);
  const el = S.h(S.sb.BailesPanel);
  let a = S.render(el);
  buscar(fila(a, ID).hijos, (n) => n.type === 'button' && n.props['aria-pressed'] === false)[0].props.onClick();
  assert.deepEqual(plano(P.de('baile_favorito')), [[ID, true]]);
  buscar(fila(a, ID).hijos, (n) => n.type === 'button' && texto(n) === 'Ajustes')[0].props.onClick();
  a = S.render(el);
  porId(a, `f-bl-off-${ID}`).props.onChange(ev('-120'));
  porId(S.render(el), `f-bl-brazo-${ID}`).props.onChange(ev('30'));
  a = S.render(el);
  buscar(fila(a, ID).hijos, (n) => n.type === 'button' && texto(n) === 'No')[0].props.onClick();
  a = S.render(el);
  boton(a, 'Guardar ajustes').props.onClick();
  assert.deepEqual(plano(P.de('baile_meta_guardar').map(([id, j]) => [id, JSON.parse(j)])),
    [[ID, { offset_ms: -120, brazo_a_grados: 30, en_el_sitio: false }]]);
  assert.match(todoTexto(S.render(el)), /Ajustes del baile guardados/);
  a = S.render(el);
  interruptor(a, 'Sale en «siguiente»').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('baile_desactivar')), [[ID, true]]);
  boton(a, 'Quitar').props.onClick();
  assert.equal(P.de('baile_quitar').length, 0, 'el primer clic solo pide confirmar');
  a = S.render(el);
  boton(a, '¿Seguro? Quitar').props.onClick();
  assert.deepEqual(plano(P.de('baile_quitar')), [[ID]]);
  a = S.render(el);
  boton(a, 'Quitar').props.onClick();
  S.avanzar(4000);
  assert.ok(boton(S.render(el), 'Quitar') && !boton(S.render(el), '¿Seguro?'), 'la confirmación caduca');
  boton(S.render(el), 'Importar…').props.onClick();
  assert.equal(P.de('bailes_importar').length, 1);
  assert.match(todoTexto(S.render(el)), /Elige el movimiento/);
  P.obj.mmd_importado.emit(JSON.stringify({ ok: false, texto: 'Ese archivo no es un VMD.', id: null }));
  assert.match(todoTexto(S.render(el)), /Ese archivo no es un VMD/);
  boton(S.render(el), 'Abrir carpeta').props.onClick();
  assert.equal(P.de('bailes_abrir_carpeta').length, 1);
  // ninguna ranura recibe rutas: solo ids de 12 hex
  for (const [n, ...args] of P.llamadas) {
    for (const x of args) assert.ok(typeof x !== 'string' || !/[\\/:]/.test(x) || x.startsWith('{'), `${n}: ${x}`);
  }
});

test('BailesCard: config y «Abrir mis bailes»', () => {
  const { P } = backendBailes({ ...ESTADO, al_terminar: 'repetir', volumen: 0.4 });
  const S = cargar([BAILES], P.obj);
  const el = S.h(S.sb.BailesCard);
  let a = S.render(el);
  assert.equal(a[0].props.id, 'aj-bailes');
  assert.equal(boton(a, 'Repetir').props['data-variant'], 'primary');
  assert.equal(porId(a, 'f-bl-volumen').props.value, 40);
  boton(a, 'Siguiente').props.onClick();
  assert.deepEqual(plano(JSON.parse(P.de('mmd_config_guardar')[0][0])), { al_terminar: 'siguiente' });
  const vistas = [];
  S.sb.addEventListener('lune-vista', (e) => vistas.push(e.detail));
  boton(S.render(el), 'Abrir mis bailes').props.onClick();
  assert.deepEqual(vistas, ['bailes']);
  boton(S.render(el), 'Abrir la carpeta').props.onClick();
  assert.equal(P.de('bailes_abrir_carpeta').length, 1);
});

test('demo sin backend: la biblioteca de ejemplo y bailar sin sonar', () => {
  const S = cargar([BAILES]);
  const el = S.h(S.sb.BailesPanel);
  let a = S.render(el);
  assert.match(todoTexto(a), /Demo sin la app/);
  assert.ok(botones(a, 'Bailar').length >= 3);
  boton(a, '▶ Bailar').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /Demo: bailaría/);
  boton(a, 'Importar…').props.onClick();
  assert.match(todoTexto(S.render(el)), /Demo: importar abre el diálogo/);
  const c = S.render(S.h(S.sb.BailesCard));
  assert.equal(c[0].props.id, 'aj-bailes');
});

// ── Minecraft ─────────────────────────────────────────────────────────────────
const MC_ESTADO = { reaccionar: true, servicio: true, log: { activo: true, yo: 'Diego_01', ruta: 'C:/mc/logs/latest.log' },
  bot: { instalado: true, conectado: true, servidor: 'localhost:25565', nick: 'Lune', vida: 18, hambre: 20, dia: false, lluvia: true },
  requisitos: { node: 'v24.19.0', node_ok: true, npm: true } };
const MC_CONFIG = { config: { reaccionar: true, ruta_log: '', voz_reacciones: false, auto_con_juego: true, decir_en_juego: true,
  resumen_al_salir: true, pensar_en_juego: false, reaccionar_otros: false },
  bot: { host: 'localhost', port: 25565, version: '', usuario: '', dueno: 'Diego_01', pensar_cada_s: 45, defender: true,
    solo_dueno: true, estilo_frases: 'personaje' }, error: '' };

function backendMC(estado = MC_ESTADO) {
  let e = JSON.parse(JSON.stringify(estado));
  let cfg = JSON.parse(JSON.stringify(MC_CONFIG));
  const P = puenteFalso({
    mc_estado_json: () => JSON.stringify(e),
    mc_config: () => JSON.stringify(cfg),
    mc_config_guardar: (j) => {
      const o = JSON.parse(j);
      Object.keys(o).forEach((k) => { if (k in cfg.config) cfg.config[k] = o[k]; else cfg.bot[k] = o[k]; });
      return JSON.stringify({ ok: true, error: '', config: cfg });
    },
    mc_bot_instalar: () => { e.bot.instalando = true; return JSON.stringify({ ok: true, texto: 'Instalando el bot (~400 MB). Tarda unos minutos.', estado: e }); },
    mc_bot_conectar: () => JSON.stringify({ ok: true, texto: 'Conectando el bot a localhost:25565 como Lune…', estado: e }),
    mc_bot_desconectar: true,
    mc_orden: (t) => JSON.stringify({ ok: true, texto: 'Se lo he mandado al bot.' }),
    mc_decir: () => JSON.stringify({ ok: true, texto: 'Dicho.' }),
    mc_log_detectar: () => JSON.stringify({ ok: true, rutas: ['C:/a/logs/latest.log', 'C:/b/logs/latest.log'], sugerida: 'C:/b/logs/latest.log', actual: '' }),
    mc_eventos: () => JSON.stringify([{ tipo: 'muerte', texto: '¡Otra vez el creeper!', estado: 'sad', fuente: 'log', t: 1700000000, entregado: true },
      { tipo: '<img>', texto: 'x' }]),
  });
  return { P, poner: (o) => { e = o; P.obj.mc_estado.emit(JSON.stringify(e)); } };
}

test('MinecraftPanel: estado, órdenes, decir, eventos, chat solo texto y registro del bot', () => {
  const { P } = backendMC();
  const S = cargar([MC], P.obj);
  const el = S.h(S.sb.MinecraftPanel);
  let a = S.render(el);
  assert.match(todoTexto(a), /Dentro de localhost:25565 como Lune/);
  assert.match(todoTexto(a), /♥ 18\/20/);
  assert.match(todoTexto(a), /☾ noche/);
  assert.match(todoTexto(a), /¡Otra vez el creeper!/);
  assert.match(todoTexto(a), /Leyendo tu partida como Diego_01/);
  boton(a, 'Sígueme').props.onClick();
  boton(a, 'Explora').props.onClick();
  porId(a, 'f-mc-orden').props.onChange(ev('mina 10 hierro'));
  a = S.render(el);
  porId(a, 'f-mc-orden').props.onKeyDown({ key: 'Enter' });
  assert.deepEqual(plano(P.de('mc_orden')), [['sígueme'], ['explora'], ['mina 10 hierro']]);
  porId(S.render(el), 'f-mc-decir').props.onChange(ev('¡hola!'));
  boton(S.render(el), 'Decir').props.onClick();
  assert.deepEqual(plano(P.de('mc_decir')), [['¡hola!']]);
  assert.equal(porId(S.render(el), 'f-mc-decir').props.value, '', 'se vacía al decirlo');
  // señales: el chat del juego es de terceros → solo texto
  P.obj.mc_chat.emit(JSON.stringify({ de: 'Steve', texto: '<b>hola</b> <img src=x onerror=alert(1)>', t: 1700000100 }));
  P.obj.mc_chat.emit(JSON.stringify({ de: '<script>', texto: 'no' }));
  P.obj.mc_evento.emit(JSON.stringify({ tipo: 'logro', texto: '¡Cazamonstruos!', estado: 'happy', fuente: 'log', t: 1700000200, entregado: true }));
  P.obj.mc_log.emit('conectado a localhost');
  a = S.render(el);
  assert.match(todoTexto(a), /<b>hola<\/b> <img src=x onerror=alert\(1\)>/);
  assert.equal(buscar(a, (n) => ['b', 'img', 'script'].includes(n.type)).length, 0);
  assert.doesNotMatch(todoTexto(a), /<script>/);
  assert.match(todoTexto(a), /¡Cazamonstruos!/);
  assert.match(todoTexto(a), /conectado a localhost/);
  interruptor(a, 'Reaccionar a lo que pasa').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('mc_config_guardar').map((l) => JSON.parse(l[0]))), [{ reaccionar: false }]);
  boton(S.render(el), 'Desconectar').props.onClick();
  assert.equal(P.de('mc_bot_desconectar').length, 1);
});

test('MinecraftPanel: sin el bot conectado las órdenes no se pueden mandar; sin instalar, a Ajustes', () => {
  const { P } = backendMC({ ...MC_ESTADO, bot: { instalado: false } });
  const S = cargar([MC], P.obj);
  const a = S.render(S.h(S.sb.MinecraftPanel));
  assert.equal(boton(a, 'Sígueme').props.disabled, true);
  assert.equal(boton(a, 'Conectar').props.disabled, true);
  assert.ok(boton(a, 'Ir a Ajustes → Minecraft'));
  assert.equal(boton(a, 'Instalar el bot'), undefined, 'D3: el panel no instala; solo el botón de Ajustes');
});

test('MinecraftCard: reacciones, «Detectar» y datos del bot validados', () => {
  const { P } = backendMC();
  const S = cargar([MC], P.obj);
  const el = S.h(S.sb.MinecraftCard);
  let a = S.render(el);
  assert.equal(a[0].props.id, 'aj-minecraft');
  assert.match(todoTexto(a), /online-mode=false/);
  assert.match(todoTexto(a), /«Abrir en LAN» de Minecraft normal no sirve/);
  interruptor(a, 'En modo juego, que lo diga el bot').onChange({ target: { checked: false } });
  assert.deepEqual(plano(JSON.parse(P.de('mc_config_guardar')[0][0])), { decir_en_juego: false });
  boton(S.render(el), 'Detectar').props.onClick();
  assert.deepEqual(plano(JSON.parse(P.de('mc_config_guardar').slice(-1)[0][0])), { ruta_log: 'C:/b/logs/latest.log' });
  a = S.render(el);
  const sel = porId(a, 'f-mc-log');
  assert.deepEqual(plano(buscar([sel], (n) => n.type === 'option').map((o) => o.props.value)), ['', 'C:/b/logs/latest.log', 'C:/a/logs/latest.log']);
  sel.props.onChange(ev(''));
  assert.deepEqual(plano(JSON.parse(P.de('mc_config_guardar').slice(-1)[0][0])), { ruta_log: '' });
  // datos del bot: inválido → no se puede guardar
  porId(S.render(el), 'f-mc-usuario').props.onChange(ev('yo'));
  a = S.render(el);
  assert.equal(boton(a, 'Guardar datos del bot').props.disabled, true);
  assert.match(todoTexto(a), /De 3 a 16 letras/);
  porId(a, 'f-mc-usuario').props.onChange(ev('Lune_bot'));
  porId(S.render(el), 'f-mc-port').props.onChange(ev('25566'));
  porId(S.render(el), 'f-mc-host').props.onChange(ev(' mi.servidor.net '));
  boton(S.render(el), 'Sobrio').props.onClick();
  interruptor(S.render(el), 'Te defiende').onChange({ target: { checked: false } });
  a = S.render(el);
  assert.equal(boton(a, 'Guardar datos del bot').props.disabled, false);
  boton(a, 'Guardar datos del bot').props.onClick();
  assert.deepEqual(plano(JSON.parse(P.de('mc_config_guardar').slice(-1)[0][0])), { host: 'mi.servidor.net', port: 25566, version: '',
    usuario: 'Lune_bot', dueno: 'Diego_01', pensar_cada_s: 45, defender: false, solo_dueno: true, estilo_frases: 'sobrio' });
  assert.match(todoTexto(S.render(el)), /Datos del bot guardados/);
});

test('MinecraftCard: aviso de suplantación con «solo el dueño»', () => {
  const { P } = backendMC();
  const S = cargar([MC], P.obj);
  const el = S.h(S.sb.MinecraftCard);
  let a = S.render(el);
  const aviso = /cualquiera puede ponerse tu nick/;
  assert.match(todoTexto(a), aviso);
  interruptor(a, 'Solo obedece al dueño').onChange({ target: { checked: false } });
  assert.doesNotMatch(todoTexto(S.render(el)), aviso);
  interruptor(S.render(el), 'Solo obedece al dueño').onChange({ target: { checked: true } });
  assert.match(todoTexto(S.render(el)), aviso);
});

test('MinecraftCard: instalar solo con su botón, progreso y conectar', () => {
  const { P, poner } = backendMC({ ...MC_ESTADO, bot: { instalado: false }, requisitos: { node: 'v24.19.0', node_ok: true, npm: true } });
  const S = cargar([MC], P.obj);
  const el = S.h(S.sb.MinecraftCard);
  let a = S.render(el);
  assert.equal(P.de('mc_bot_instalar').length, 0);
  assert.equal(boton(a, 'Conectar').props.disabled, true);
  boton(a, 'Instalar el bot (~400 MB)').props.onClick();
  assert.equal(P.de('mc_bot_instalar').length, 1);
  a = S.render(el);
  assert.equal(boton(a, 'Instalando…').props.disabled, true);
  assert.match(todoTexto(a), /Instalando el bot \(~400 MB\)/);
  poner({ ...MC_ESTADO, bot: { instalado: true, conectado: false } });
  a = S.render(el);
  assert.ok(boton(a, 'Reinstalar el bot'));
  assert.equal(boton(a, 'Conectar').props.disabled, false);
  boton(a, 'Conectar').props.onClick();
  assert.equal(P.de('mc_bot_conectar').length, 1);
  assert.match(todoTexto(S.render(el)), /Conectando el bot a localhost:25565/);
  // sin Node no se puede instalar
  poner({ ...MC_ESTADO, bot: { instalado: false }, requisitos: { node: null, node_ok: false, npm: false } });
  a = S.render(el);
  assert.equal(boton(a, 'Instalar el bot (~400 MB)').props.disabled, true);
  assert.match(todoTexto(a), /Node\.js 18/);
});

test('Minecraft sin backend: demo local', () => {
  const S = cargar([MC]);
  const el = S.h(S.sb.MinecraftCard);
  let a = S.render(el);
  boton(a, 'Instalar el bot (~400 MB)').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /Demo: en la app descargaría/);
  const p = S.render(S.h(S.sb.MinecraftPanel));
  assert.match(todoTexto(p), /Demo sin la app/);
});

// ── app.jsx y apariencia.jsx ──────────────────────────────────────────────────
function docFalso() {
  const clases = new Set();
  return {
    body: { classList: { toggle(c, on) { if (on) clases.add(c); else clases.delete(c); }, contains: (c) => clases.has(c) } },
    getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null,
  };
}

test('app.jsx: vistas «bailes» y «minecraft», vista_pedida y entradas del menú', () => {
  const P = puenteFalso({});
  const props = {};
  const stub = (n) => function (p) { props[n] = (props[n] || 0) + 1; return null; };
  const S = crearSandbox({
    archivos: [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx'), path.join(EXTRA, 'apariencia.jsx'), path.join(EXTRA, 'juego.jsx'),
      BAILES, MC, path.join(KIT, 'app.jsx')],
    globales: {
      document: docFalso(), localStorage: { getItem: () => null, setItem() {} }, luneEscenario: P.obj,
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), SettingsPanel: stub('SettingsPanel'), AprobacionHost: stub('AprobacionHost'),
      CommandMenu: function (p) { props.menu = p.items; return null; },
    },
  });
  S.sb.BailesPanel = stub('BailesPanel');
  S.sb.MinecraftPanel = stub('MinecraftPanel');
  const app = S.h(S.sb.LuneApp);
  S.render(app);
  assert.ok(!props.BailesPanel && props.ChatStream);
  assert.equal(P.obj.vista_pedida.oyentes, 1, 'escucha vista_pedida');
  P.obj.vista_pedida.emit('javascript:alert(1)');
  S.render(app);
  assert.ok(!props.BailesPanel);
  P.obj.vista_pedida.emit('bailes');
  S.render(app);
  assert.ok(props.BailesPanel >= 1, 'la acción «Mis bailes» lleva a la vista');
  S.dispatch(new S.sb.CustomEvent('lune-vista', { detail: 'minecraft' }));
  S.render(app);
  assert.ok(props.MinecraftPanel >= 1);
  const etiquetas = props.menu.map((i) => i.label);
  assert.ok(etiquetas.includes('Mis bailes') && etiquetas.includes('Minecraft'));
  props.menu.find((i) => i.label === 'Mis bailes').onClick();
  S.desmontar();
  assert.equal(P.obj.vista_pedida.oyentes, 0, 'se desconecta al desmontar');
});

test('apariencia: icono de «Mis bailes» y vistas navegables', () => {
  const S = crearSandbox({ archivos: [path.join(EXTRA, 'apariencia.jsx')] });
  const R = S.sb.LuneRadial;
  assert.ok(R.trazosIcono('', 'bailes'));
  assert.deepEqual(plano(R.trazosIcono('film', '')), plano(R.trazosIcono('', 'bailes')));
  assert.deepEqual(plano(R.trazosIcono('box', '')), plano(R.trazosIcono('', 'minecraft_bot')));
  const A = S.sb.LuneApariencia;
  assert.deepEqual(plano(A.vistaDe('bailes')), { vista: 'bailes', seccion: '' });
  assert.deepEqual(plano(A.vistaDe('minecraft')), { vista: 'minecraft', seccion: '' });
  assert.deepEqual(plano(A.vistaDe('settings#minecraft')), { vista: 'settings', seccion: 'minecraft' });
});
