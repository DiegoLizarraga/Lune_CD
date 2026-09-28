// ── reflexes.js ──────────────────────────────────────────────────────────────────
// Instintos de supervivencia que corren en TIEMPO REAL (cada ~600ms), sin pasar por
// el LLM: huye de creepers al instante, come cuando tiene hambre, se defiende y se
// pone la armadura. Tienen prioridad sobre el bucle autónomo: con pánico, todo lo
// demás cede. Siguen funcionando con el cerebro en pausa (modo juego de Lune).
//
// De Another-craft; Lune solo cambia el tono de las frases y habla con `decir`
// (saneado + límite de ritmo) en vez de bot.chat. El estado compartido es bot.lune.
'use strict'

const TICK_MS = 600

function startReflexes (bot, { skills = null, decir = null, ahora = () => Date.now() } = {}) {
  const sk = skills || require('./skills')
  const di = decir || (() => false)
  const timer = setInterval(() => {
    tick(bot, sk, di, ahora).catch(err => console.error('[reflejo]', err.message))
  }, TICK_MS)
  bot.once('end', () => clearInterval(timer))
  return timer
}

async function tick (bot, skills, decir, ahora) {
  const st = bot.lune
  if (!bot.entity || !st || st.reflexBusy) return

  // 1) CREEPER cerca → huir es lo primero, siempre.
  const creeper = skills.nearestEntityByName(bot, 'creeper', 7)
  if (creeper) {
    if (!st.panic) {
      st.panic = true
      sayThrottled(bot, decir, ahora, '¡Creeper! ¡Me largo!', 4000)
    }
    st.reflexBusy = true
    try {
      await skills.fleeFrom(bot, creeper, 18)
    } finally {
      st.reflexBusy = false
      st.panic = false
      // si estaba siguiendo a alguien, retomamos al terminar de huir
      if (st.following) skills.follow(bot, st.following)
    }
    return
  }
  st.panic = false

  // 2) Salud crítica → huir de la amenaza más cercana.
  if (bot.health <= 6) {
    const threat = skills.nearestHostile(bot, 12)
    if (threat) {
      st.reflexBusy = true
      sayThrottled(bot, decir, ahora, 'Me están machacando. Me retiro.', 5000)
      try { await skills.fleeFrom(bot, threat, 16) } finally { st.reflexBusy = false }
      return
    }
  }

  // 3) Defensa propia: un hostil pegado y con vida suficiente → contraatacar.
  if (st.defendSelf && bot.health > 8) {
    const threat = skills.nearestHostile(bot, 3)
    if (threat && threat.name !== 'creeper') {
      st.reflexBusy = true
      try { await skills.attackNearest(bot, threat.name) } finally { st.reflexBusy = false }
      return
    }
  }

  // 4) Hambre → comer (sin nada más urgente).
  if (bot.food <= 16 && !st.busy) {
    st.reflexBusy = true
    try {
      const ate = await skills.eatFood(bot)
      if (ate && bot.food < 6) sayThrottled(bot, decir, ahora, 'Tenía mucha hambre.', 8000)
    } finally { st.reflexBusy = false }
    return
  }

  // 5) Armadura disponible sin equipar → ponérsela (revisión espaciada).
  const now = ahora()
  if (now - (st.lastArmorCheck || 0) > 15000) {
    st.lastArmorCheck = now
    await skills.equipArmor(bot)
  }

  // 6) NOCHE → refugio básico (BAJA prioridad): arrimarse a un jugador o, sola y a
  //    oscuras, poner UNA antorcha. Sin pisar órdenes ni seguimiento.
  const esNoche = bot.time && bot.time.timeOfDay >= 13000
  if (esNoche && !st.busy && !st.panic && !st.following && !st.thinking &&
      now - (st.nightShelterAt || 0) > 10000) {
    const jugador = skills.nearestPlayer(bot, 24)
    if (jugador) {
      st.nightShelterAt = now
      sayThrottled(bot, decir, ahora, 'De noche me quedo cerca. Por si acaso.', 30000)
      skills.approach(bot, jugador.position, 3)
      return
    }
    if (skills.isDarkHere(bot)) {
      st.nightShelterAt = now
      st.reflexBusy = true
      try {
        const puesta = await skills.placeTorchNearby(bot)
        sayThrottled(bot, decir, ahora, puesta
          ? 'Pongo una antorcha. Nada de sorpresas.'
          : 'Está muy oscuro y no tengo antorchas.', 30000)
      } finally { st.reflexBusy = false }
    }
  }
}

function sayThrottled (bot, decir, ahora, text, ms) {
  const now = ahora()
  if (now - (bot.lune.lastReflexChat || 0) < ms) return
  bot.lune.lastReflexChat = now
  decir(text)
}

module.exports = { startReflexes, TICK_MS }
