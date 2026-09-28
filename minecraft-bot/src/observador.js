// ── observador.js ────────────────────────────────────────────────────────────────
// Lo que el bot le cuenta a Lune de la partida (eventos para sus reacciones en el
// escritorio o en el chat del juego). Nuevo en Lune.
//
//   · del DUEÑO: `muerte` y `logro` (mensajes del sistema: `translate` si mineflayer
//     lo da; si no, los mismos patrones que el lector de latest.log), y `peligro`
//     {detalle: mob} cuando un hostil está a ≤8 bloques de él (como mucho cada 20 s);
//   · del mundo: `dia` / `noche` (al cambiar) y `lluvia` (al empezar);
//   · del bot: `bot_muerte`, `bot_mata`, `bot_mineral`, `bot_herida` y `bot_nivel`.
//
// Cada evento sale por emitir('evento', {evento, jugador, detalle}). Todo lo que
// viene del servidor pasa por nickSeguro / limpiarChat: Lune lo trata igualmente
// como texto no confiable y nunca lo manda a su modelo.
//
// Por inyección: crearObservador({bot, dueno, emitir, ahora, …}); en los tests
// `bot` es un EventEmitter de mentira.
'use strict'

const { nickSeguro, limpiarChat } = require('./sanear')
const { HOSTILES } = require('./vocab')

const NOCHE = 13000
const RADIO_PELIGRO = 8
const CADA_PELIGRO_MS = 20000
const INTERVALO_MS = 2000
const LOGROS_TRANSLATE = /^chat\.type\.advancement\.(task|goal|challenge)$/

// Patrones de respaldo (sin `translate`: servidores que mandan el texto ya traducido), los
// MISMOS que lune_core/minecraft_log.py, sacados de los textos reales del juego (es_es, es_mx
// y demás es_*, en_us; 1.20.1–1.21.x). Anclados al principio: «<nick> <frase>», nunca el chat
// de un jugador («<nick> texto» va con position 'chat'). En es_mx el juego escribe «/a» u
// «(a)» literal: «fue asesinado/a por».
const NICK_RE = '[A-Za-z0-9_]{3,16}'
const VOCALES = { a: '[aá]', e: '[eé]', i: '[ií]', o: '[oó]', u: '[uúü]', á: '[aá]', é: '[eé]', í: '[ií]', ó: '[oó]', ú: '[uúü]' }
/** Trozo de regex escrito como el juego → cada vocal con o sin tilde. Sin clases [..] dentro. */
const flex = (s) => Array.from(s, (c) => VOCALES[c] || c).join('')
const P = '(?:o|a)(?:/a|\\(a\\))?'
const FIN = '(?![\\p{L}\\p{N}_])'
const PARTICIPIOS = 'alcanzad|aniquilad|aplastad|arrasad|asesinad|atravesad|borrad|calcinad|condenad|congelad|detonad|' +
  'disparad|electrocutad|empalad|empujad|ensartad|espetad|explotad|golpead|impactad|matad|obliterad|' +
  'perforad|picad|pinchad|quemad|rematad|reducid|reventad|rostizad|volad'
const FRASES_EN = [
  'was slain by', 'was shot by', 'was killed', 'was blown up by', 'blew up', 'drowned',
  'fell from', 'fell off', 'fell out of the world', 'fell while climbing', 'fell too far',
  'hit the ground too hard', 'burned to death', 'was burned to a crisp', 'was burnt to a crisp',
  'went up in flames', 'walked into fire', 'walked into a cactus', 'walked into the danger zone',
  'tried to swim in lava', 'starved to death', 'suffocated in a wall', 'was struck by lightning',
  'froze to death', 'was frozen to death', 'was pricked to death', 'was poked to death', 'withered away',
  'was squashed', 'was squished', 'was impaled', 'was skewered', 'was fireballed by', 'was stung to death',
  'was pummeled by', 'was smashed by', 'was speared by', "was roasted in dragon's breath",
  'experienced kinetic energy', 'was obliterated', 'discovered the floor was lava', 'was doomed to fall',
  'went off with a bang', 'left the confines of this world', "didn't want to live in the same world as",
  'died',
]
const FRASES_ES = [
  'fue (?:' + PARTICIPIOS + '){P}', 'fue víctima de',
  'ha sido (?:' + PARTICIPIOS + '){P}', 'ha sido víctima de',
  'se ha muerto', 'ha muerto', 'se murió', 'murió',
  'se ha ahogado', 'se ahogó', 'se ha asfixiado', 'se asfixió', 'se sofocó',
  'se ha calcinado', 'se asó en', 'se ha quemado', 'se quemó', 'se prendió fuego',
  'ha ardido', 'ardió',
  'ha explotado', 'explotó', 'ha estallado', 'reventó', 'ha pegado un estallido',
  'voló con fuegos artificiales', 'se fue con un bang', 'se convirtió en un fuego artificial',
  'se ha convertido en fuegos artificiales',
  'se ha caído', 'se cayó', 'ha caído (?:de|desde)', 'cayó (?:a|de|del|desde|fuera|demasiado)',
  'se ha estampado contra', 'se golpeó', 'se dio con', 'se dio contra', 'se chocó contra', 'chocó contra el piso',
  'ha experimentado la energía cinética', 'experimentó la energía cinética',
  'ha intentado nadar en', 'intentó nadar en', 'trató de nadar en',
  'ha descubierto que el suelo era lava', 'descubrió que el (?:suelo|piso) era lava',
  'ha pisado (?:un cactus|una zona de peligro)',
  'caminó (?:cerca de un cactus|en fuego|hacia el fuego|hacia un cactus|por la zona peligrosa|sobre una zona peligrosa)',
  'ha recibido (?:una paliza|un empujón)',
  'recibió (?:la ira de|un proyectil|un tiro|una bola de fuego|una piña)',
  'ha sufrido una gran presión', 'sufrió (?:hambruna|la ira del wither|una caída)',
  '(?:ha abandonado|abandona|abandonó|dejó) los (?:bordes|confines)', 'salió de los límites del mundo',
  'no (?:quería|volverá a) vivir en el mismo mundo', 'metió la pata',
  'se congeló', 'se ha descompuesto', 'se descompuso', 'se ha reducido a cenizas', 'se redujo a cenizas',
  'se pinchó', 'se quedó pegado a un cactus',
].map((f) => flex(f).replace('{P}', P))
const MUERTE_TEXTO = new RegExp('^(' + NICK_RE + ') (?:' + FRASES_EN.concat(FRASES_ES).join('|') + ')' + FIN + '(?: (.*))?$', 'iu')
// es_es: «A <nick> le ha caído un yunque / un bloque / un rayo…».
const MUERTE_A = new RegExp('^' + flex('A') + ' (' + NICK_RE + ') ' + flex('le (?:ha caído|cayó) un (?:yunque|bloque|rayo)') +
  FIN + '(?: (.*))?$', 'iu')
// Quien mata delante: «<quien> ha tirado a <nick> desde muy alto», «… hizo explotar / mandó a volar a <nick>».
const MUERTE_POR = new RegExp('^(.{1,40}?) (?:' + flex('ha tirado a') + ' (' + NICK_RE + ') ' + flex('desde muy alto') + '|' +
  flex('(?:hizo explotar|mandó a volar) a') + ' (' + NICK_RE + '))' + FIN + '(?: (.*))?$', 'iu')
const ARMA = new RegExp(flex('\\s+(?:con su|y su|con|usando|utilizando|equipado con|empuñando|using|wielding|with)\\s+\\[.*$|' +
  '\\s+(?:con su|y su|usando|utilizando|equipado con|empuñando|using|wielding)\\s+.*$'), 'iu')
const COLA = new RegExp(flex('\\s+(?:de un lugar muy alto|desde muy alto|con una bola de fuego|mientras|while|whilst)') + FIN + '.*$', 'iu')
// Lo que va justo antes de quien mata; gana el ÚLTIMO del texto (las frases largas, antes que «por»/«by»).
const ANTES_DEL_ASESINO = new RegExp('(?<![\\p{L}\\p{N}_])(?:' + flex(
  'víctima de|flechazo de|disparo de|tiro de|mazazo de|picadura de|paliza de|calavera de|cráneo de|' +
  'bola de fuego de|aliento de dragón de|aliento del dragón de|proyectil del wither de|piña de|la magia de|' +
  'huir de|escapar de|escapaba de|por culpa de|debido a|a causa de|luchaba contra|luchaba con|' +
  'peleaba contra|peleaba con|luchando contra|golpear a|atacar a|pegarle a|mismo mundo que|por un\\(a\\)') +
  '|escape|fighting|hurt|due to|because of|same world as|skull from|by|' + flex('por') + ')\\s+', 'giu')
const LOGRO_TEXTO = new RegExp('^(' + NICK_RE + ') (?:has made the advancement|has completed the challenge|has reached the goal|' +
  flex('(?:ha conseguido|consiguió|acaba de conseguir|ha obtenido) el (?:progreso|logro)|' +
    '(?:ha completado|completó|acaba de completar) el desafío|' +
    '(?:ha alcanzado|alcanzó|acaba de alcanzar) (?:el objetivo|la meta)') + ') \\[(.{1,80})\\]\\s*$', 'iu')

/** Quién mató según el texto de la muerte (sin el arma), o ''. */
function asesino (resto) {
  const r = String(resto || '').replace(ARMA, '')
  let fin = -1
  for (const m of r.matchAll(ANTES_DEL_ASESINO)) fin = m.index + m[0].length
  return fin < 0 ? '' : r.slice(fin).replace(COLA, '').trim().slice(0, 40)
}

/** Una muerte en texto plano → {jugador, detalle} o null. */
function muerteTexto (texto) {
  let m = texto.match(MUERTE_TEXTO)
  if (m) return { jugador: m[1], detalle: asesino(texto.slice(m[1].length + 1)) }
  m = texto.match(MUERTE_A)
  if (m) return { jugador: m[1], detalle: asesino(m[2] || '') }
  m = texto.match(MUERTE_POR)
  if (m) return { jugador: m[2] || m[3], detalle: m[1].trim().slice(0, 40) }
  return null
}

function textoDe (x) {
  if (x == null) return ''
  if (typeof x === 'string') return x
  try {
    if (typeof x.toString === 'function' && x.toString !== Object.prototype.toString) return String(x.toString())
    if (typeof x.text === 'string') return x.text
  } catch {}
  return ''
}

/** Lee un mensaje del sistema → {tipo:'muerte'|'logro', jugador, detalle} o null. */
function leerMensaje (msg) {
  if (!msg) return null
  const translate = typeof msg.translate === 'string' ? msg.translate : ''
  const args = Array.isArray(msg.with) ? msg.with : []
  if (translate.startsWith('death.')) {
    const jugador = nickSeguro(textoDe(args[0]))
    if (!jugador) return null
    return { tipo: 'muerte', jugador, detalle: limpiarChat(textoDe(args[1]), 64) }
  }
  if (LOGROS_TRANSLATE.test(translate)) {
    const jugador = nickSeguro(textoDe(args[0]))
    if (!jugador) return null
    const logro = limpiarChat(textoDe(args[1]).replace(/^\[|\]$/g, ''), 64)
    return { tipo: 'logro', jugador, detalle: logro }
  }
  const texto = limpiarChat(textoDe(msg), 300)
  let m = texto.match(LOGRO_TEXTO)
  if (m) return { tipo: 'logro', jugador: m[1], detalle: limpiarChat(m[2], 64) }
  const x = muerteTexto(texto)
  if (x) return { tipo: 'muerte', jugador: x.jugador, detalle: limpiarChat(x.detalle, 64) }
  return null
}

/**
 * crearObservador({bot, dueno, emitir, ahora, radioPeligro, cadaPeligroMs, intervaloMs,
 *                  setInterval, clearInterval}) → {start, stop, procesarMensaje, revisar}
 */
function crearObservador ({ bot, dueno = '', emitir = () => false, ahora = () => Date.now(),
  radioPeligro = RADIO_PELIGRO, cadaPeligroMs = CADA_PELIGRO_MS, intervaloMs = INTERVALO_MS,
  setInterval: si = setInterval, clearInterval: ci = clearInterval } = {}) {
  const owner = nickSeguro(dueno)
  let timer = null
  let eraNoche = null
  let ultimoPeligro = -Infinity
  let ultimaVida = null
  let ultimoNivel = null
  const oyentes = []

  function evento (tipo, jugador = '', detalle = '') {
    // `tipo` del mensaje es 'evento' (lo pone el canal): el del evento va en `evento`.
    return emitir('evento', { evento: tipo, jugador: nickSeguro(jugador), detalle: limpiarChat(String(detalle ?? ''), 64) })
  }

  function esDueno (n) {
    return !!owner && String(n || '').toLowerCase() === owner.toLowerCase()
  }

  function procesarMensaje (msg, position) {
    if (position === 'chat') return null                    // chat de jugadores: nunca eventos
    const e = leerMensaje(msg)
    if (!e) return null
    if (bot && e.jugador && e.jugador === bot.username) return null   // lo del bot va por sus propios eventos
    if (!esDueno(e.jugador)) return null
    evento(e.tipo, e.jugador, e.detalle)
    return e
  }

  function revisarHora () {
    if (!bot || !bot.time) return
    const noche = bot.time.timeOfDay >= NOCHE
    if (eraNoche !== null && noche !== eraNoche) evento(noche ? 'noche' : 'dia')
    eraNoche = noche
  }

  function revisarPeligro () {
    if (!bot || !owner || !bot.players) return
    const p = bot.players[owner]
    const e = p && p.entity
    if (!e || !e.position) return
    let mejor = null
    let dist = radioPeligro
    for (const id in bot.entities || {}) {
      const x = bot.entities[id]
      if (!x || x === bot.entity || !x.name || !HOSTILES.has(x.name) || !x.position) continue
      const d = x.position.distanceTo(e.position)
      if (d <= dist) { mejor = x; dist = d }
    }
    if (!mejor) return
    const t = ahora()
    if (t - ultimoPeligro < cadaPeligroMs) return
    ultimoPeligro = t
    evento('peligro', owner, mejor.name)
  }

  function revisar () {
    revisarHora()
    revisarPeligro()
  }

  function on (nombre, fn) {
    bot.on(nombre, fn)
    oyentes.push([nombre, fn])
  }

  function start () {
    if (!bot || timer) return
    ultimaVida = bot.health
    ultimoNivel = bot.experience ? bot.experience.level : 0
    eraNoche = bot.time ? bot.time.timeOfDay >= NOCHE : null
    on('message', (msg, position) => { try { procesarMensaje(msg, position) } catch {} })
    on('death', () => evento('bot_muerte', bot.username))
    on('entityDead', (ent) => {
      if (!ent || !ent.name || !HOSTILES.has(ent.name) || !bot.entity || !ent.position) return
      if (ent.position.distanceTo(bot.entity.position) <= 6) evento('bot_mata', bot.username, ent.name)
    })
    on('diggingCompleted', (block) => {
      if (!block || !/_ore$/.test(String(block.name || ''))) return
      evento('bot_mineral', bot.username, block.name.replace(/^deepslate_/, '').replace(/_ore$/, ''))
    })
    on('health', () => {
      const prev = ultimaVida ?? bot.health
      ultimaVida = bot.health
      if (bot.health > 0 && prev - bot.health >= 5) evento('bot_herida', bot.username, String(Math.round(bot.health)))
    })
    on('experience', () => {
      const lvl = bot.experience ? bot.experience.level : 0
      if (lvl > (ultimoNivel || 0)) evento('bot_nivel', bot.username, String(lvl))
      ultimoNivel = lvl
    })
    on('rain', () => { if (bot.isRaining) evento('lluvia') })
    timer = si(revisar, intervaloMs)
  }

  function stop () {
    if (timer) ci(timer)
    timer = null
    for (const [nombre, fn] of oyentes.splice(0)) {
      try { bot.removeListener(nombre, fn) } catch {}
    }
  }

  return { start, stop, procesarMensaje, revisar, revisarHora, revisarPeligro }
}

module.exports = { crearObservador, leerMensaje, muerteTexto, MUERTE_TEXTO, LOGRO_TEXTO }
