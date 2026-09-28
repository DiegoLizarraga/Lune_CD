// ── world.js ───────────────────────────────────────────────────────────────────
// Construye la "percepción" que el bot le pasa a su modelo: dónde está, cómo está,
// qué hay alrededor (jugadores, mobs, bloques) y si es de noche o de día.
// (De Another-craft. Lune: los nombres que manda el servidor pasan por nickSeguro
// e idSeguro, que un servidor sin autenticación puede mandar cualquier cosa.)
'use strict'

const { nickSeguro, idSeguro } = require('./sanear')

function getWorldContext (bot) {
  const pos = bot.entity.position
  const inventory = bot.inventory.items().map(i => `${idSeguro(i.name)}x${i.count}`).join(', ') || 'vacío'
  const held = bot.heldItem ? idSeguro(bot.heldItem.name) : 'nada (mano vacía)'
  const time = bot.time.timeOfDay

  let timeLabel
  if (time < 1000) timeLabel = 'amanecer'
  else if (time < 6000) timeLabel = 'mañana'
  else if (time < 12000) timeLabel = 'tarde'
  else if (time < 13000) timeLabel = 'atardecer'
  else timeLabel = 'NOCHE (salen monstruos)'

  const players = getNearbyPlayers(bot, 48)
  const mobs = getNearbyMobs(bot, 24)
  const blocks = getNearbyBlocks(bot, 6)

  return `Posición: x=${Math.floor(pos.x)}, y=${Math.floor(pos.y)}, z=${Math.floor(pos.z)}
Salud: ${bot.health}/20 | Hambre: ${bot.food}/20
En la mano: ${held}
Inventario: ${inventory}
Hora: ${timeLabel} (${time})
Jugadores cerca: ${players.length ? players.join(', ') : 'ninguno'}
Mobs cercanos: ${mobs.length ? mobs.join(', ') : 'ninguno'}
Bloques interesantes: ${blocks.length ? blocks.join(', ') : 'nada relevante'}`
}

function getNearbyPlayers (bot, radius) {
  const out = []
  for (const name in bot.players) {
    if (name === bot.username) continue
    const nick = nickSeguro(name)
    const e = bot.players[name].entity
    if (!nick || !e) continue
    const dist = Math.floor(e.position.distanceTo(bot.entity.position))
    if (dist <= radius) out.push(`${nick}@${dist}m`)
  }
  return out.sort((a, b) => parseInt(a.split('@')[1]) - parseInt(b.split('@')[1])).slice(0, 12)
}

function getNearbyMobs (bot, radius) {
  return Object.values(bot.entities)
    .filter(e => e !== bot.entity && (e.type === 'mob' || e.type === 'hostile' || e.type === 'animal'))
    .map(e => {
      const dist = Math.floor(e.position.distanceTo(bot.entity.position))
      const nombre = idSeguro(e.name)
      return dist <= radius && nombre ? `${nombre}@${dist}m` : null
    })
    .filter(Boolean)
    .sort((a, b) => parseInt(a.split('@')[1]) - parseInt(b.split('@')[1]))
    .slice(0, 8)
}

function getNearbyBlocks (bot, radius) {
  const interesting = new Set([
    'oak_log', 'birch_log', 'spruce_log', 'jungle_log', 'acacia_log', 'dark_oak_log',
    'coal_ore', 'iron_ore', 'gold_ore', 'diamond_ore', 'copper_ore', 'redstone_ore', 'emerald_ore',
    'crafting_table', 'furnace', 'chest', 'bed',
    'wheat', 'carrots', 'potatoes',
    'water', 'lava',
  ])
  const pos = bot.entity.position
  const found = new Map()

  for (let x = -radius; x <= radius; x++) {
    for (let y = -radius; y <= radius; y++) {
      for (let z = -radius; z <= radius; z++) {
        const block = bot.blockAt(pos.offset(x, y, z))
        if (block && interesting.has(block.name)) {
          found.set(block.name, (found.get(block.name) || 0) + 1)
        }
      }
    }
  }

  return Array.from(found.entries()).map(([name, n]) => `${name}x${n}`)
}

module.exports = { getWorldContext }
