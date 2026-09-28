/*
 * Web principal de los cortes 7 y 8 en el sandbox de jsx_falso.mjs (sin navegador):
 *   · extra/vida.jsx: SentarseCard (aviso anticheat antes de guardar «ventanas», altura diferida, sentar/bajar),
 *     ComidaCard, DiscordCard (Application ID, enlace https, «Discord ve:» solo con los textos fijos) y
 *     AutoinicioOpciones (cómo, espera diferida, Administrador de tareas), con y sin backend (window.luneVida);
 *   · ComidaWeb: sigue al ratón, acierto por segmento-círculo contra window.__luneCabezaBarra() con flanco y
 *     enfriamiento de 0.35 s → comida_evento + 'lune-mascota-cara'; Esc y 2 minutos quieta la guardan;
 *   · app.jsx + sidebar.jsx: la cara al comer, clic central → radial «secundario», la cabeza de la barra en
 *     vídeo y en VRM (y nada con Lune fuera).
 * Lo lanza tests/test_index_html_c78.py.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  crearSandbox, escritorioFalso, senal, KIT, EXTRA, buscar, porId, boton, botones, todoTexto, conClase, interruptor, texto,
} from './jsx_falso.mjs';

const VIDA = path.join(EXTRA, 'vida.jsx');
const plano = (x) => JSON.parse(JSON.stringify(x));
const ev = (v) => ({ target: { value: v, checked: v } });
const ID = '123456789012345678';

const RANURAS = ['asiento_estado', 'asiento_config_guardar', 'asiento_sentar', 'asiento_bajar', 'comida_estado',
  'comida_alternar', 'comida_guardar', 'comida_evento', 'comida_config_guardar', 'discord_estado', 'discord_alternar',
  'discord_config_guardar', 'autoinicio_estado', 'autoinicio_opciones'];
const SENALES = ['asiento_cambio', 'comida_cambio', 'comida_web', 'discord_cambio', 'autoinicio_cambio'];

/** window.luneVida falso: ranuras que apuntan y responden por callback, y señales. */
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
  return {
    obj, llamadas, respuestas,
    de: (n) => llamadas.filter((l) => l[0] === n).map((l) => l.slice(1)),
    limpiar: () => { llamadas.length = 0; },
  };
}
const cargar = (vida = null, globales = {}) => crearSandbox({ archivos: [VIDA], globales: { ...(vida ? { luneVida: vida } : {}), ...globales } });
const mover = (S, x, y) => S.dispatch({ type: 'pointermove', clientX: x, clientY: y });
const WEB_BATIDO = JSON.stringify({ accion: 'aparece', id: 'batido', variante: 'fresa', color: '#FF6FA8', tipo: 'beber', nombre: 'Batido' });

// ── Registro y utilidades puras ──────────────────────────────────────────────
test('se registra solo sin pisar globales', () => {
  const S = cargar();
  assert.deepEqual(plano(S.nuevas.sort()), ['AutoinicioOpciones', 'ComidaCard', 'ComidaWeb', 'DiscordCard', 'LuneVida',
    'SentarseCard']);
});

test('LuneVida: segmento-círculo, detector con flanco y enfriamiento, validaciones y textos', () => {
  const V = cargar().sb.LuneVida;
  const c = { x: 100, y: 100 };
  assert.equal(V.segmentoTocaCirculo({ x: 0, y: 100 }, { x: 300, y: 100 }, c, 20), true, 'pasada rápida que cruza entera');
  assert.equal(V.segmentoTocaCirculo({ x: 0, y: 120 }, { x: 300, y: 120 }, c, 20), false, 'tangente no cuenta');
  assert.equal(V.segmentoTocaCirculo({ x: 0, y: 0 }, { x: 10, y: 0 }, c, 20), false);
  assert.equal(V.segmentoTocaCirculo({ x: 100, y: 100 }, { x: 100, y: 100 }, c, 20), true, 'un punto dentro');
  assert.equal(V.segmentoTocaCirculo({ x: NaN, y: 0 }, { x: 1, y: 1 }, c, 20), false);
  const d = V.crearDetector();
  const cab = { x: 100, y: 100, r: 20 };
  assert.equal(d.mover(0, { x: 0, y: 100 }, { x: 300, y: 100 }, cab), true);
  assert.equal(d.mover(100, { x: 300, y: 100 }, { x: 0, y: 100 }, cab), false, 'enfriamiento de 0.35 s');
  assert.equal(d.mover(400, { x: 0, y: 100 }, { x: 100, y: 100 }, cab), true, 'entra y se queda');
  assert.equal(d.mover(900, { x: 100, y: 100 }, { x: 101, y: 100 }, cab), false, 'seguir dentro no cuenta');
  assert.equal(d.mover(1400, { x: 101, y: 100 }, { x: 300, y: 100 }, cab), false, 'salir no cuenta');
  assert.equal(d.mover(1500, { x: 300, y: 100 }, { x: 0, y: 100 }, null), false, 'sin cabeza');
  assert.equal(V.ENFRIAMIENTO_MS, 350);
  assert.equal(V.GUARDAR_SOLA_MS, 120000);
  // Discord
  assert.equal(V.idDiscordValido(ID), true);
  assert.equal(V.idDiscordValido(''), true, 'vacío = sin ID');
  for (const malo of ['1234567890123456', '123456789012345678901', '12345678901234567a', ' ' + ID, 123456789012345678]) {
    assert.equal(V.idDiscordValido(malo), false, String(malo));
  }
  assert.equal(V.urlBotonValida('https://lune.example.com/a?b=c'), true);
  for (const malo of ['http://lune.example.com', 'https://sinpunto', 'javascript:alert(1)', 'https://a.b/ c', 'https://a.b/<x>',
    ' https://a.b', 'https://' + 'a'.repeat(600) + '.com', '']) {
    assert.equal(V.urlBotonValida(malo), false, malo);
  }
  assert.deepEqual(plano(V.publicacionSegura({ details: 'Lune CD · Ventana', state: 'Charlando', x: 1 })),
    { details: 'Lune CD · Ventana', state: 'Charlando' });
  for (const malo of [{ details: 'Lune CD · Ventana', state: 'YouTube - Google Chrome' }, { details: 'Spotify', state: 'Charlando' },
    { details: 'Lune CD · Ventana' }, 'Lune CD', null]) {
    assert.equal(V.publicacionSegura(malo), null);
  }
  assert.equal(V.textoDiscordVe({ activo: false }), 'Discord ve: nada (apagado).');
  assert.equal(V.textoDiscordVe({ activo: true, servicio: true, vista_previa: { details: 'Lune CD · Mascota 3D', state: 'Merendando' } }),
    'Discord ve: Lune CD · Mascota 3D — Merendando');
  assert.match(V.textoDiscordVe({ activo: true, servicio: true, vista_previa: { details: 'Lune CD · Ventana', state: 'Banco - Chrome' } }),
    /nada ahora mismo/);
  // Comida web: color y acción validados
  assert.equal(V.normalizarComidaWeb({ accion: 'borrar', id: 'batido' }), null);
  assert.equal(V.normalizarComidaWeb({ accion: 'aparece', id: '<b>' }), null);
  assert.equal(V.normalizarComidaWeb({ accion: 'aparece', id: 'batido', color: 'url(x)' }).color, '#FFFFFF');
  // Autoinicio
  assert.match(V.textoAutoinicio({ disponible: true, registrado: true, aprobado: false }), /Administrador de tareas/);
  assert.match(V.textoAutoinicio({ disponible: true, registrado: true, aprobado: true, ruta_ok: false }), /otra carpeta/);
  assert.match(V.textoAutoinicio({ disponible: false }), /solo funciona en la app/);
  assert.equal(V.normalizarAutoinicio({ como: 'escritorio', retraso_s: 999 }).como, 'bandeja');
  assert.equal(V.normalizarAutoinicio({ retraso_s: 999 }).retraso_s, 300);
  assert.equal(V.normalizarAsiento({ offset: 500, sentada: 'techo' }).offset, 64);
  assert.equal(V.normalizarAsiento({ sentada: 'techo' }).sentada, '');
});

// ── Sin backend (demo en el navegador) ────────────────────────────────────────
test('demo sin backend: las tarjetas se dibujan y responden en local; la comida sigue al ratón', () => {
  const S = cargar();
  const h = S.h;
  for (const n of ['SentarseCard', 'ComidaCard', 'DiscordCard']) {
    const a = S.render(h(S.sb[n]));
    assert.ok(a.length === 1 && a[0].type === 'section' && /^aj-/.test(a[0].props.id), n);
    S.desmontar();
  }
  const au = S.render(h(S.sb.AutoinicioOpciones, { activo: false }));
  assert.match(todoTexto(au), /solo funciona en la app/);
  S.desmontar();
  // Sentarse
  const se = h(S.sb.SentarseCard);
  let a = S.render(se);
  boton(a, 'Sentarse en la barra').props.onClick();
  a = S.render(se);
  assert.match(todoTexto(a), /Demo: me senté en la barra/);
  assert.ok(boton(a, 'Bajar'));
  S.desmontar();
  // Comida + ComidaWeb juntas
  const Juntas = () => h(S.React.Fragment, null, h(S.sb.ComidaCard), h(S.sb.ComidaWeb));
  const el = h(Juntas);
  a = S.render(el);
  mover(S, 400, 300);
  boton(a, 'Batido').props.onClick();
  a = S.render(el);
  const w = conClase(a, 'ln-comida-web')[0];
  assert.ok(w, 'la comida aparece en la página');
  assert.equal(w.props['data-comida'], 'batido');
  assert.deepEqual([w.props.style.left, w.props.style.top], [352, 252], 'centrada en el ratón');
  assert.match(todoTexto(a), /batido de fresa/);
  boton(a, 'Guardar').props.onClick();
  a = S.render(el);
  assert.ok(conClase(a, 'is-sale').length === 1, 'se guarda con animación');
  S.avanzar(250);
  a = S.render(el);
  assert.equal(conClase(a, 'ln-comida-web').length, 0);
  S.desmontar();
  assert.equal(S.nOyentes('pointermove') + S.nOyentes('keydown'), 0, 'sin oyentes colgados');
});

// ── Con backend ────────────────────────────────────────────────────────────────
test('SentarseCard: aviso anticheat antes de encender «ventanas», barra, altura diferida, sentar y bajar', () => {
  let estado = { sentada: '', ventanas: false, barra: true, offset: 0, servicio: true, mascota: true };
  const P = puenteFalso({
    asiento_estado: () => JSON.stringify(estado),
    asiento_config_guardar: (j) => { estado = { ...estado, ...JSON.parse(j) }; return JSON.stringify({ ok: true, error: '', estado }); },
    asiento_sentar: (sitio) => { estado = { ...estado, sentada: sitio, variante: 1 }; return JSON.stringify({ ok: true, texto: 'Me senté en la barra de tareas.', estado }); },
    asiento_bajar: () => { const b = !!estado.sentada; estado = { ...estado, sentada: '' }; return b; },
  });
  const S = cargar(P.obj);
  const el = S.h(S.sb.SentarseCard);
  let a = S.render(el);
  assert.equal(P.de('asiento_estado').length, 1);
  assert.match(todoTexto(a), /arrástrala hasta la barra de tareas/);
  assert.equal(boton(a, 'En una ventana').props.disabled, true, 'sin «ventanas» no se ofrece');
  // Encender «ventanas»: primero el aviso, sin guardar
  interruptor(a, 'En ventanas').onChange({ target: { checked: true } });
  a = S.render(el);
  assert.equal(P.de('asiento_config_guardar').length, 0);
  assert.match(todoTexto(a), /anticheats/);
  boton(a, 'Cancelar').props.onClick();
  a = S.render(el);
  assert.doesNotMatch(todoTexto(a), /anticheats/);
  assert.equal(P.de('asiento_config_guardar').length, 0, 'cancelar no guarda');
  interruptor(a, 'En ventanas').onChange({ target: { checked: true } });
  boton(S.render(el), 'Activar igualmente').props.onClick();
  assert.deepEqual(plano(P.de('asiento_config_guardar').map((l) => JSON.parse(l[0]))), [{ ventanas: true }]);
  a = S.render(el);
  assert.equal(boton(a, 'En una ventana').props.disabled, false);
  // Apagar no pide nada; la barra, al momento
  interruptor(a, 'En ventanas').onChange({ target: { checked: false } });
  interruptor(S.render(el), 'En la barra de tareas').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('asiento_config_guardar').slice(1).map((l) => JSON.parse(l[0]))), [{ ventanas: false }, { barra: false }]);
  // Altura: un solo guardado 350 ms después del último movimiento
  for (const v of ['-5', '-10', '-12']) porId(S.render(el), 'f-sentarse-offset').props.onChange(ev(v));
  assert.equal(porId(S.render(el), 'f-sentarse-offset').props.value, -12);
  assert.equal(P.de('asiento_config_guardar').length, 3);
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(P.de('asiento_config_guardar').slice(-1)[0][0])), { offset: -12 });
  // Sentar y bajar
  boton(S.render(el), 'Sentarse en la barra').props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(P.de('asiento_sentar')), [['barra']]);
  assert.match(todoTexto(a), /SENTADA/);
  assert.match(todoTexto(a), /Me senté en la barra de tareas\./);
  boton(a, 'Bajar').props.onClick();
  a = S.render(el);
  assert.equal(P.de('asiento_bajar').length, 1);
  assert.match(todoTexto(a), /de pie/);
  // Señal de fuera (se sentó arrastrándola)
  estado = { ...estado, sentada: 'ventana' };
  P.obj.asiento_cambio.emit(JSON.stringify(estado));
  assert.match(todoTexto(S.render(el)), /Sentada en una ventana/);
  S.desmontar();
  assert.equal(P.obj.asiento_cambio.oyentes, 0, 'desconecta la señal al desmontar');
});

test('ComidaCard: activa, Batido/Pastel, error de Python a la vista y Guardar', () => {
  let estado = { activa: false, disponible: true, servicio: true };
  const catalogo = [{ id: 'batido', nombre: 'Batido', tipo: 'beber', variantes: [{ id: 'mango', nombre: 'mango', color: '#FFB547' }] },
    { id: 'pastel', nombre: 'Pastel', tipo: 'comer', variantes: [{ id: 'limon', nombre: 'limón', color: '#FFE45C' }] },
    { id: '<script>', nombre: 'x', tipo: 'beber', variantes: [{ id: 'x', nombre: 'x', color: '#000000' }] }];
  const P = puenteFalso({
    comida_estado: () => JSON.stringify({ ...estado, catalogo }),
    comida_alternar: (id) => {
      if (id === 'pastel') return JSON.stringify({ ok: false, accion: '', motivo: 'juego', texto: 'Ahora no puedo comer: hay un juego delante.', estado });
      estado = { activa: true, id, variante: 'mango', color: '#FFB547', tipo: 'beber', vista: 'web', disponible: true, servicio: true };
      return JSON.stringify({ ok: true, accion: 'aparece', estado });
    },
    comida_guardar: () => { estado = { activa: false, disponible: true, servicio: true }; return true; },
    comida_config_guardar: (j) => { estado = { ...estado, disponible: JSON.parse(j).activa }; return JSON.stringify({ ok: true, estado }); },
  });
  const S = cargar(P.obj);
  const el = S.h(S.sb.ComidaCard);
  let a = S.render(el);
  assert.equal(botones(a, '').filter((b) => /^(Batido|Pastel|x)$/.test(texto(b))).length, 2, 'ids raros fuera del catálogo');
  assert.equal(boton(a, 'Guardar').props.disabled, true);
  boton(a, 'Batido').props.onClick();
  a = S.render(el);
  assert.deepEqual(plano(P.de('comida_alternar')), [['batido']]);
  assert.match(todoTexto(a), /EN LA MANO/);
  assert.match(todoTexto(a), /batido de mango/);
  boton(a, 'Pastel').props.onClick();
  a = S.render(el);
  assert.match(todoTexto(a), /hay un juego delante/);
  boton(a, 'Guardar').props.onClick();
  a = S.render(el);
  assert.equal(P.de('comida_guardar').length, 1);
  assert.match(todoTexto(a), /Nada en la mano/);
  interruptor(a, 'Comida con el clic central').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('comida_config_guardar').map((l) => JSON.parse(l[0]))), [{ activa: false }]);
  a = S.render(el);
  assert.equal(boton(a, 'Batido').props.disabled, true, 'desactivada: sin botones');
  estado = { activa: true, id: 'pastel', variante: 'limon', color: '#FFE45C', tipo: 'comer', vista: 'escritorio', disponible: true, servicio: true };
  P.obj.comida_cambio.emit(JSON.stringify(estado));
  assert.match(todoTexto(S.render(el)), /pastel de limón/);
  S.desmontar();
  assert.equal(P.obj.comida_cambio.oyentes, 0);
});

test('DiscordCard: «Discord ve» solo con textos fijos, Application ID, enlace https y estado', () => {
  let estado = { activo: true, conectado: true, usuario: 'diego', error: '', servicio: true, client_id_ok: false, sin_id: true,
    publicando: { details: 'Lune CD · Ventana', state: 'Banco Santander - Google Chrome' },
    vista_previa: { details: 'Lune CD · Mascota 3D', state: 'Bailando ♪' },
    config: { client_id: '', mostrar_modelo: false, boton_url: '' } };
  const P = puenteFalso({
    discord_estado: () => JSON.stringify(estado),
    discord_config_guardar: (j) => {
      const o = JSON.parse(j);
      estado = { ...estado, activo: o.activo ?? estado.activo, config: { ...estado.config, ...Object.fromEntries(Object.entries(o).filter(([k]) => k !== 'activo')) } };
      estado.sin_id = estado.activo && !estado.config.client_id;
      return JSON.stringify({ ok: true, error: '', estado });
    },
  });
  const S = cargar(P.obj);
  const el = S.h(S.sb.DiscordCard);
  let a = S.render(el);
  const ve = () => texto(conClase(S.render(el), 'ln-vd-ve')[0]);
  assert.equal(ve(), 'Discord ve: Lune CD · Mascota 3D — Bailando ♪', 'el título de ventana nunca sale');
  assert.doesNotMatch(todoTexto(a), /Chrome|Santander/);
  assert.match(todoTexto(a), /Falta el Application ID/);
  assert.match(todoTexto(a), /Nunca títulos de ventanas/);
  // Application ID: mal → no se puede guardar; bien → guarda
  porId(a, 'f-discord-id').props.onChange(ev('12345'));
  a = S.render(el);
  assert.equal(boton(a, 'Guardar ID').props.disabled, true);
  assert.match(todoTexto(a), /17 a 20 cifras/);
  porId(a, 'f-discord-id').props.onChange(ev(ID));
  a = S.render(el);
  boton(a, 'Guardar ID').props.onClick();
  assert.deepEqual(plano(P.de('discord_config_guardar').map((l) => JSON.parse(l[0]))), [{ client_id: ID }]);
  a = S.render(el);
  assert.match(todoTexto(a), /Application ID guardado/);
  assert.match(todoTexto(a), /Conectado como diego/);
  // Enlace: http no; https sí
  porId(a, 'f-discord-url').props.onChange(ev('http://lune.example.com'));
  a = S.render(el);
  assert.equal(boton(a, 'Guardar enlace').props.disabled, true);
  porId(a, 'f-discord-url').props.onChange(ev('https://lune.example.com/lune'));
  boton(S.render(el), 'Guardar enlace').props.onClick();
  assert.deepEqual(plano(JSON.parse(P.de('discord_config_guardar').slice(-1)[0][0])), { boton_url: 'https://lune.example.com/lune' });
  // Interruptores
  interruptor(S.render(el), 'nombre del modelo').onChange({ target: { checked: true } });
  interruptor(S.render(el), 'Enseñar en Discord').onChange({ target: { checked: false } });
  assert.deepEqual(plano(P.de('discord_config_guardar').slice(-2).map((l) => JSON.parse(l[0]))), [{ mostrar_modelo: true }, { activo: false }]);
  assert.equal(ve(), 'Discord ve: nada (apagado).');
  // Señal de fuera: con un juego delante no hay vista previa
  estado = { ...estado, activo: true, publicando: null, vista_previa: null };
  P.obj.discord_cambio.emit(JSON.stringify(estado));
  assert.match(ve(), /nada ahora mismo/);
  S.desmontar();
  assert.equal(P.obj.discord_cambio.oyentes, 0);
});

test('AutoinicioOpciones: estado del Administrador de tareas, cómo, espera diferida y refresco con el interruptor', () => {
  let estado = { activo: false, registrado: true, aprobado: false, ruta_ok: true, como: 'bandeja', retraso_s: 20, disponible: true };
  const P = puenteFalso({
    autoinicio_estado: () => JSON.stringify(estado),
    autoinicio_opciones: (j) => { estado = { ...estado, ...JSON.parse(j) }; return JSON.stringify({ ok: true, error: '', estado }); },
  });
  const S = cargar(P.obj);
  let a = S.render(S.h(S.sb.AutoinicioOpciones, { activo: false }));
  assert.match(todoTexto(a), /Administrador de tareas/);
  assert.equal(boton(a, 'En la bandeja').props['data-variant'], 'primary');
  boton(a, 'En la bandeja').props.onClick();
  assert.equal(P.de('autoinicio_opciones').length, 0, 'la que ya está no se guarda');
  boton(a, 'Con la mascota').props.onClick();
  a = S.render(S.h(S.sb.AutoinicioOpciones, { activo: false }));
  assert.deepEqual(plano(P.de('autoinicio_opciones').map((l) => JSON.parse(l[0]))), [{ como: 'mascota' }]);
  assert.equal(boton(a, 'Con la mascota').props['data-variant'], 'primary');
  for (const v of ['30', '45']) porId(S.render(S.h(S.sb.AutoinicioOpciones, { activo: false })), 'f-autoinicio-espera').props.onChange(ev(v));
  assert.equal(P.de('autoinicio_opciones').length, 1);
  S.avanzar(350);
  assert.deepEqual(plano(JSON.parse(P.de('autoinicio_opciones').slice(-1)[0][0])), { retraso_s: 45 });
  // El interruptor de settings.jsx cambió: se vuelve a leer el estado
  const n = P.de('autoinicio_estado').length;
  estado = { ...estado, activo: true, aprobado: true };
  a = S.render(S.h(S.sb.AutoinicioOpciones, { activo: true }));
  assert.equal(P.de('autoinicio_estado').length, n + 1);
  assert.match(todoTexto(a), /arranca con Windows/);
  S.desmontar();
  assert.equal(P.obj.autoinicio_cambio.oyentes, 0);
});

// ── ComidaWeb ─────────────────────────────────────────────────────────────────
test('ComidaWeb: sigue al ratón, acierta por flanco con enfriamiento, Esc y 2 minutos quieta la guardan', () => {
  const P = puenteFalso({ comida_estado: JSON.stringify({ activa: false }), comida_evento: true, comida_guardar: true });
  const caras = [];
  const S = cargar(P.obj, { __luneCabezaBarra: () => ({ x: 100, y: 100, r: 20 }) });
  S.sb.addEventListener('lune-mascota-cara', (e) => caras.push(plano(e.detail)));
  const el = S.h(S.sb.ComidaWeb);
  assert.deepEqual(S.render(el), [], 'sin comida no dibuja nada');
  P.obj.comida_web.emit(WEB_BATIDO);
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-comida-web').length, 1);
  const svg = buscar(a, (n) => n.type === 'path' && n.props.fill === '#FF6FA8');
  assert.ok(svg.length === 1, 'el batido con el color de la variante');
  assert.equal(conClase(a, 'ln-comida-web')[0].props['aria-hidden'], 'true');
  // Pasada rápida por la cabeza
  mover(S, 0, 100);
  mover(S, 300, 100);
  assert.deepEqual(plano(P.de('comida_evento')), [['batido']]);
  assert.deepEqual(caras, [{ estado: 'happy', ms: 2500 }]);
  a = S.render(el);
  const w = conClase(a, 'ln-comida-web')[0];
  assert.deepEqual([w.props.style.left, w.props.style.top], [252, 52]);
  assert.match(w.props.style.transform, /rotate\(25deg\)/, 'se ladea hacia donde va (tope 25°)');
  assert.ok(w.props.className.includes('is-bocado'));
  mover(S, 0, 100);                                       // vuelve a cruzar dentro del enfriamiento
  assert.equal(P.de('comida_evento').length, 1);
  S.avanzar(400);
  mover(S, 300, 100);
  assert.equal(P.de('comida_evento').length, 2, 'pasado el enfriamiento, otra');
  S.avanzar(400);
  mover(S, 100, 100);                                     // entra y se queda
  mover(S, 101, 101);
  assert.equal(P.de('comida_evento').length, 3, 'quedarse dentro no cuenta más');
  S.avanzar(200);
  a = S.render(el);
  assert.equal(conClase(a, 'ln-comida-web')[0].props.style.transform, undefined, 'quieta vuelve a derecho');
  // Esc la guarda (Python manda 'guarda' por la señal)
  S.dispatch(S.evento('keydown', { key: 'Escape' }));
  assert.equal(P.de('comida_guardar').length, 1);
  S.dispatch(S.evento('keydown', { key: 'a' }));
  assert.equal(P.de('comida_guardar').length, 1);
  // D4: dos minutos sin moverla (moverla reinicia la cuenta)
  S.avanzar(100000);
  mover(S, 500, 500);
  S.avanzar(100000);
  assert.equal(P.de('comida_guardar').length, 1);
  S.avanzar(20001);
  assert.equal(P.de('comida_guardar').length, 2);
  P.obj.comida_web.emit(JSON.stringify({ accion: 'guarda', id: 'batido', variante: 'fresa' }));
  a = S.render(el);
  assert.ok(conClase(a, 'is-sale').length === 1);
  S.avanzar(250);
  assert.deepEqual(S.render(el), []);
  mover(S, 0, 100);
  mover(S, 300, 100);
  assert.equal(P.de('comida_evento').length, 3, 'guardada ya no acierta');
  S.desmontar();
  assert.equal(S.nOyentes('pointermove') + S.nOyentes('keydown'), 0);
  assert.equal(P.obj.comida_web.oyentes, 0);
});

test('ComidaWeb: al recargar la página con comida en la web sale ya; cambia de comida; lo raro se ignora', () => {
  const P = puenteFalso({
    comida_estado: JSON.stringify({ activa: true, id: 'pastel', variante: 'limon', color: '#FFE45C', tipo: 'comer', vista: 'web' }),
  });
  const S = cargar(P.obj);
  const el = S.h(S.sb.ComidaWeb);
  let a = S.render(el);
  assert.equal(conClase(a, 'ln-comida-web')[0].props['data-comida'], 'pastel');
  assert.ok(buscar(a, (n) => n.type === 'path' && n.props.fill === '#FFE45C').length === 1, 'el pastel con su cobertura');
  P.obj.comida_web.emit(WEB_BATIDO);
  a = S.render(el);
  assert.equal(conClase(a, 'ln-comida-web')[0].props['data-comida'], 'batido');
  P.obj.comida_web.emit(JSON.stringify({ accion: 'explota', id: 'batido' }));
  P.obj.comida_web.emit('no es json');
  assert.equal(conClase(S.render(el), 'ln-comida-web')[0].props['data-comida'], 'batido');
  S.desmontar();
  // En el escritorio (mascota flotante) la página no la dibuja
  const P2 = puenteFalso({ comida_estado: JSON.stringify({ activa: true, id: 'batido', variante: 'fresa', vista: 'escritorio' }) });
  const S2 = cargar(P2.obj);
  assert.deepEqual(S2.render(S2.h(S2.sb.ComidaWeb)), []);
});

// ── app.jsx + sidebar.jsx ─────────────────────────────────────────────────────
const ARCHIVOS_APP = [path.join(KIT, 'icons.jsx'), path.join(KIT, 'sidebar.jsx'), path.join(EXTRA, 'apariencia.jsx'),
  path.join(EXTRA, 'juego.jsx'), path.join(EXTRA, 'alarmas.jsx'), path.join(EXTRA, 'baile.jsx'), VIDA, path.join(KIT, 'app.jsx')];

function docFalso() {
  return {
    body: { classList: { toggle() {} } },
    getElementById: () => null, createElement: () => ({}), head: { appendChild() {} }, querySelector: () => null,
  };
}
function luneFalso() {
  const base = { mascota_visible(cb) { cb(false); }, proveedores(cb) { cb('{}'); }, proveedor_elegido() {} };
  return new Proxy(base, { get(t, k) { if (!(k in t) && typeof k === 'string') t[k] = senal(); return t[k]; } });
}
/** Elementos del DOM falsos para los ref: <video> 180×320 en (10, 20) y <canvas> 200×360 en (0, 0). */
function conRefs(S) {
  const nodos = {};
  const crear = S.React.createElement;
  const RECT = { video: { left: 10, top: 20, width: 180, height: 320 }, canvas: { left: 0, top: 0, width: 200, height: 360 } };
  S.React.createElement = (type, props, ...hijos) => {
    if (props && props.ref && typeof type === 'string' && !props.ref.current) {
      const clases = new Set();
      const n = { tipo: type, style: {}, clases, classList: { add: (c) => clases.add(c), remove: (c) => clases.delete(c) },
        play: () => Promise.resolve(), pause() {}, videoWidth: 720, videoHeight: 1280,
        getBoundingClientRect: () => ({ ...(RECT[type] || { left: 0, top: 0, width: 100, height: 100 }) }) };
      props.ref.current = n;
      (nodos[type] = nodos[type] || []).push(n);
    }
    return crear(type, props, ...hijos);
  };
  return nodos;
}
function cargarApp({ vida = null, vrm = null, lune = null } = {}) {
  const props = {};
  const stub = (n) => function (p) { props[n] = p; return null; };
  const S = crearSandbox({
    archivos: ARCHIVOS_APP, lune: lune || luneFalso(), escritorio: escritorioFalso({ juego_estado_json: JSON.stringify({ activo: false }) }).obj,
    globales: {
      document: docFalso(), localStorage: { getItem: () => null, setItem() {} },
      ChatStream: stub('ChatStream'), InputBar: stub('InputBar'), CommandMenu: stub('CommandMenu'), SettingsPanel: stub('SettingsPanel'),
      AprobacionHost: stub('AprobacionHost'), luneTema: () => 1,
      ...(vida ? { luneVida: vida } : {}),
      ...(vrm ? { LuneVRMBarra: vrm, __luneVrmBarra: { render: 'vrm', url: '/vrm/actual.vrm', v: '1' } } : {}),
    },
  });
  const nodos = conRefs(S);
  const app = S.h(S.sb.LuneApp);
  return { S, props, nodos, pintar: () => S.render(app) };
}
const srcVideo = (a) => buscar(a, (n) => n.type === 'video')[0].props.src;

test('app: la comida de la web sobre Lune de la barra (vídeo) pone la cara contenta y vuelve', () => {
  const P = puenteFalso({ comida_estado: JSON.stringify({ activa: false }), comida_evento: true });
  const A = cargarApp({ vida: P.obj });
  let a = A.pintar();
  assert.match(srcVideo(a), /lune-composed\.webm$/);
  const cab = A.S.sb.__luneCabezaBarra();
  assert.ok(cab && Math.abs(cab.x - 100.9) < 0.01 && Math.abs(cab.y - 93.92) < 0.01 && Math.abs(cab.r - 71.49) < 0.01,
    `la cabeza del vídeo con la fórmula de companion.html (${JSON.stringify(cab)})`);
  P.obj.comida_web.emit(WEB_BATIDO);
  a = A.pintar();
  assert.equal(conClase(a, 'ln-comida-web').length, 1, 'ComidaWeb global en app.jsx');
  mover(A.S, 0, 94);
  mover(A.S, 300, 94);
  assert.deepEqual(plano(P.de('comida_evento')), [['batido']]);
  a = A.pintar();
  assert.match(srcVideo(a), /lune-happy\.webm$/, 'la cara contenta en la barra');
  A.S.avanzar(2600);
  a = A.pintar();
  assert.match(srcVideo(a), /lune-composed\.webm$/, 'y vuelve a la de siempre');
  // Caras que no están en la lista, ignoradas
  A.S.dispatch(new A.S.sb.CustomEvent('lune-mascota-cara', { detail: { estado: '<img>', ms: 100 } }));
  assert.match(srcVideo(A.pintar()), /lune-composed\.webm$/);
});

test('sidebar: clic central (soltado) sobre la mascota → radial «secundario»; con Lune fuera, nada', () => {
  const lune = luneFalso();
  const A = cargarApp({ lune });
  const radiales = [];
  A.S.sb.addEventListener('lune-radial', (e) => radiales.push(plano(e.detail)));
  let a = A.pintar();
  const esc = () => conClase(A.pintar(), 'ln-mascot-stage')[0];
  let prevenido = false;
  esc().props.onMouseDown({ button: 1, preventDefault() { prevenido = true; } });
  assert.ok(prevenido, 'sin el autodesplazamiento del botón central');
  esc().props.onMouseUp({ button: 0, clientX: 5, clientY: 5, preventDefault() {} });
  assert.deepEqual(radiales, [], 'el izquierdo no abre nada');
  esc().props.onMouseUp({ button: 1, clientX: 50, clientY: 60, preventDefault() {} });
  assert.deepEqual(radiales, [{ x: 50, y: 60, tipo: 'secundario' }]);
  lune.mascota_estado.emit(true);                          // Lune sale al escritorio
  a = A.pintar();
  esc().props.onMouseUp({ button: 1, clientX: 50, clientY: 60, preventDefault() {} });
  assert.equal(radiales.length, 1);
  assert.equal(A.S.sb.__luneCabezaBarra, null, 'sin Lune en la barra no hay cabeza');
});

test('sidebar en VRM: la cabeza proyectada (+0.1 m, r = 0.22·ancho) y nada en pausa', () => {
  const handle = {
    setEstado() {}, pausar() {}, mod() {}, usarModulo: () => Promise.resolve(true),
    mascota: { ctx: {
      huesos: { head: { getWorldPosition(v) { v.x = 0; v.y = 1.5; v.z = 0; return v; } } },
      THREE: { Vector3: function () { this.x = 0; this.y = 0; this.z = 0; } },
      proyectar: (v) => ({ x: 120, y: 80 - v.y * 10 }),
    } },
  };
  const lune = luneFalso();
  const A = cargarApp({ lune, vrm: { crear: () => handle, destruir: () => true } });
  const a = A.pintar();
  assert.equal(buscar(a, (n) => n.type === 'canvas').length, 1);
  const cab = A.S.sb.__luneCabezaBarra();
  assert.equal(cab.x, 120);
  assert.ok(Math.abs(cab.y - 64) < 1e-9, `cabeza + 0.1 m (${cab.y})`);
  assert.equal(cab.r, 44);
  handle.mascota = null;                                   // el modelo aún no está: el 35 % desde arriba
  const sin = A.S.sb.__luneCabezaBarra();
  assert.ok(sin.x === 100 && Math.abs(sin.y - 126) < 1e-9 && sin.r === 44, JSON.stringify(sin));
  lune.mascota_estado.emit(true);                          // fuera: el avatar se pausa
  A.pintar();
  assert.equal(A.S.sb.__luneCabezaBarra, null);
  lune.mascota_estado.emit(false);
  A.pintar();
  assert.equal(typeof A.S.sb.__luneCabezaBarra, 'function');
});

test('apariencia: el icono de «sentarse» es el de la barra de tareas', () => {
  const S = crearSandbox({ archivos: [path.join(EXTRA, 'apariencia.jsx')] });
  const R = S.sb.LuneRadial;
  assert.ok(R.trazosIcono('', 'sentarse'));
  assert.deepEqual(plano(R.trazosIcono('', 'sentarse')), plano(R.trazosIcono('taskbar', '')));
});
