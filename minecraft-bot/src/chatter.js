// ── chatter.js ───────────────────────────────────────────────────────────────────
// La voz del bot en el chat del juego: frases ante lo que pasa (alguien entra,
// mata un mob, le pegan, encuentra mineral, llueve, anochece, sube de nivel…).
// NO usa el LLM: es instantáneo y gratis. Todo pasa por una cadencia (global y por
// categoría) para dar vida sin hacer spam.
//
// De Another-craft, con el tono de Lune: directa, con filo, sin «kyaa». El
// personaje puede traer sus frases (persona.frases[categoría]); las que falten
// salen de aquí. Con estilo 'sobrio', sin emojis.
//
// Por inyección: crearCharla({decir, ahora, azar, frases, estilo, nombre}).
// `decir` es el de bot.js (saneado + límite de ritmo): nunca bot.chat directo.
'use strict'

const { HOSTILES } = require('./vocab')

const GLOBAL_COOLDOWN_MS = 3500 // tiempo mínimo entre dos frases ambientales

// Mineral (en inglés base) → nombre en español, para las frases.
const ORE_ES = {
  coal: 'carbón', copper: 'cobre', iron: 'hierro', gold: 'oro',
  redstone: 'redstone', lapis: 'lapislázuli', diamond: 'diamante',
  emerald: 'esmeralda', quartz: 'cuarzo',
}

// ── Frases por categoría (huecos: {name}, {mob}, {ore}, {level}, {nombre}, {nick}) ──
const LINES = {
  join: [
    'Mira quién aparece: {name}.',
    'Hola, {name}. Llegas justo a tiempo.',
    '{name} ha llegado. Ya somos más.',
    'Bienvenido, {name}. No toques mis cofres.',
  ],
  leave: [
    '{name} se fue. Ya volverá.',
    'Adiós, {name}.',
    '{name} nos abandona. Anotado.',
  ],
  hurt: [
    '¡Au!',
    'Eso dolió.',
    'Oye, cuidado.',
    'Vale, eso no me gustó.',
  ],
  bigHurt: [
    'Esto me está haciendo mucho daño.',
    'Necesito ayuda, y en serio.',
    'No, no, no. Esto va mal.',
  ],
  kill: [
    'Un {mob} menos.',
    '{mob} fuera de juego.',
    'Ese {mob} no lo vio venir. ⚔️',
    'Hecho. El {mob} ya no molesta.',
  ],
  ore: [
    'Mira: {ore}.',
    '{ore}. Me lo quedo.',
    'Ooh, {ore}. ⛏️',
  ],
  oreRare: [
    '¡{ore}! Esto sí que es suerte. 💎',
    '¡Hay {ore}! Que nadie lo toque.',
    '{ore}. Hoy es un buen día.',
  ],
  rainStart: [
    'Empieza a llover.',
    'Lluvia. Genial...',
    'Se nubló. A ver si no caen rayos.',
  ],
  rainStop: [
    'Ya paró de llover.',
    'Sale el sol otra vez.',
  ],
  night: [
    'Se hizo de noche. Ojo con lo que sale.',
    'Noche. Los monstruos ya están despiertos. 🌙',
    'Está oscuro. Quédate cerca.',
  ],
  day: [
    'Amaneció. Sobrevivimos.',
    'Buenos días. A trabajar.',
    'De día otra vez. Mejor.',
  ],
  levelUp: [
    'Nivel {level}.',
    'Subí a nivel {level}. De nada.',
  ],
  death: [
    'Me morí. Ya vuelvo.',
    'Vale, eso no salió bien. Vuelvo enseguida.',
    'Caí. Que no se repita.',
  ],
  respawn: [
    'De vuelta.',
    'Otra vez aquí. Con más cuidado.',
  ],
  // ── Sociales (las reutiliza commands.js para contestar en el chat) ────────────
  greet: [
    'Hola.',
    'Hola. ¿Qué hacemos?',
    'Aquí {nombre}. ¿Qué pasa?',
  ],
  thanks: [
    'De nada.',
    'Cuando quieras.',
    'Para eso estoy.',
  ],
  praise: [
    'Lo sé.',
    'Gracias. Me esfuerzo.',
    'Ya era hora de que lo notaras.',
  ],
  love: [
    'Qué cursi. Gracias.',
    'Yo también. No se lo digas a nadie.',
  ],
  joke: [
    '¿Qué hace un creeper en una fiesta? Reventarla.',
    '¿Por qué los esqueletos no pelean entre ellos? No tienen agallas.',
    'Un aldeano me dijo «hrmm». Creo que me insultó.',
    '¿Cuál es el bloque más educado? El de-cente.',
  ],
  // ── Propias de Lune ──────────────────────────────────────────────────────────
  saludo: [
    'Hola, soy {nombre}. Escribe «ayuda» para ver qué sé hacer.',
  ],
  sinModelo: [
    'No me llega el modelo; sigo con órdenes simples.',
  ],
  noEntiendo: [
    'Eso no sé hacerlo.',
  ],
}

// Emojis (y selectores de variación) fuera para el estilo 'sobrio'.
const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu

/**
 * crearCharla({decir, ahora, azar, frases, estilo, nombre, nick})
 * → {line, pick, say, start, LINES}
 */
function crearCharla ({ decir = () => false, ahora = () => Date.now(), azar = Math.random, frases = null,
  estilo = 'personaje', nombre = 'Lune', nick = '' } = {}) {
  const propias = frases && typeof frases === 'object' ? frases : {}
  const sobrio = estilo === 'sobrio'
  const estado = { ultimo: 0, porCategoria: {} }

  function pick (arr) {
    if (!arr || !arr.length) return ''
    const i = Math.min(arr.length - 1, Math.floor(azar() * arr.length))
    return arr[Math.max(0, i)]
  }

  function fill (tpl, vars) {
    const todas = Object.assign({ nombre, nick }, vars)
    return tpl.replace(/\{(\w+)\}/g, (_, k) => (todas[k] != null ? String(todas[k]) : ''))
  }

  /** Una frase de la categoría ('' si no existe). */
  function line (categoria, vars = {}) {
    const pool = (Array.isArray(propias[categoria]) && propias[categoria].length) ? propias[categoria] : LINES[categoria]
    if (!pool) return ''
    let t = fill(pick(pool), vars)
    if (sobrio) t = t.replace(EMOJI, '').replace(/\s+/g, ' ').trim()
    return t
  }

  /** Dice una frase respetando la cadencia (global y por categoría). force=true se la salta. */
  function say (_bot, categoria, vars = {}, { force = false, cooldown = 12000 } = {}) {
    const text = line(categoria, vars)
    if (!text) return false
    const now = ahora()
    if (!force) {
      if (now - estado.ultimo < GLOBAL_COOLDOWN_MS) return false
      if (now - (estado.porCategoria[categoria] || 0) < cooldown) return false
    }
    estado.ultimo = now
    estado.porCategoria[categoria] = now
    return decir(text) !== false
  }

  function prettyOre (name) {
    const base = name.replace(/^deepslate_/, '').replace(/_ore$/, '')
    return ORE_ES[base] || base
  }

  // ── Cableado de eventos del bot ───────────────────────────────────────────────
  function start (bot) {
    bot.on('playerJoined', player => {
      if (!player || player.username === bot.username) return
      say(bot, 'join', { name: player.username }, { cooldown: 8000 })
    })
    bot.on('playerLeft', player => {
      if (!player || player.username === bot.username) return
      say(bot, 'leave', { name: player.username }, { cooldown: 8000 })
    })

    // Le pegan: reacciona según cuánto daño recibió (sin pisar el pánico de los reflejos).
    let ultimaVida = bot.health
    bot.on('health', () => {
      const prev = ultimaVida ?? bot.health
      const dropped = prev - bot.health
      ultimaVida = bot.health
      if (dropped <= 0 || bot.health <= 0 || (bot.lune && bot.lune.panic)) return
      if (dropped >= 5) say(bot, 'bigHurt', {}, { cooldown: 6000 })
      else say(bot, 'hurt', {}, { cooldown: 5000 })
    })

    // Murió un hostil cerca: se lo apunta.
    bot.on('entityDead', entity => {
      if (!entity || !entity.name || !HOSTILES.has(entity.name) || !bot.entity) return
      const dist = entity.position.distanceTo(bot.entity.position)
      if (dist <= 6) say(bot, 'kill', { mob: entity.name }, { cooldown: 5000 })
    })

    // Terminó de picar un bloque: si era mineral, lo comenta (más si es raro).
    bot.on('diggingCompleted', block => {
      if (!block || !/_ore$/.test(block.name)) return
      const base = block.name.replace(/^deepslate_/, '').replace(/_ore$/, '')
      const ore = prettyOre(block.name)
      if (base === 'diamond' || base === 'emerald') say(bot, 'oreRare', { ore }, { cooldown: 3000 })
      else say(bot, 'ore', { ore }, { cooldown: 6000 })
    })

    bot.on('rain', () => {
      say(bot, bot.isRaining ? 'rainStart' : 'rainStop', {}, { cooldown: 20000 })
    })

    let ultimoNivel = bot.experience ? bot.experience.level : 0
    bot.on('experience', () => {
      const lvl = bot.experience ? bot.experience.level : 0
      if (lvl > (ultimoNivel || 0)) say(bot, 'levelUp', { level: lvl }, { cooldown: 8000 })
      ultimoNivel = lvl
    })

    // Día/noche (sondeo ligero; no hay evento limpio para esto).
    let eraNoche = bot.time && bot.time.timeOfDay >= 13000
    const timeTimer = setInterval(() => {
      if (!bot.time) return
      const isNight = bot.time.timeOfDay >= 13000
      if (isNight && !eraNoche) say(bot, 'night', {}, { cooldown: 30000 })
      else if (!isNight && eraNoche) say(bot, 'day', {}, { cooldown: 30000 })
      eraNoche = isNight
    }, 5000)
    bot.once('end', () => clearInterval(timeTimer))
  }

  return { line, pick, say, start, LINES }
}

module.exports = { crearCharla, LINES, ORE_ES, GLOBAL_COOLDOWN_MS }
