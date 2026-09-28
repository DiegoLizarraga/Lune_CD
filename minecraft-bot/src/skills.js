// ── skills.js ──────────────────────────────────────────────────────────────────
// "Las manos" del bot. Habilidades de bajo nivel reutilizables que NO dependen
// del LLM: moverse, seguir, minar, recoger, atacar, soltar, equipar, comer, huir.
// Cada skill es defensiva: nunca lanza, devuelve true/false o un texto de resultado.
// (Copia de Another-craft sin cambios de lógica. Los límites — a quién se ataca,
// a quién se le da algo, hasta dónde se camina — los ponen actions.js y
// commands.js antes de llamar aquí.)
'use strict'

const { Movements, goals } = require('mineflayer-pathfinder')
const { GoalNear, GoalFollow, GoalXZ, GoalGetToBlock } = goals
const Vec3 = require('vec3')

const TOOL_TIERS = ['netherite', 'diamond', 'iron', 'stone', 'golden', 'wooden']

function mcData(bot) {
  return require('minecraft-data')(bot.version)
}

// Movements cacheados: permitimos cavar y hacer torres 1x1 para que llegue a casi todo.
function ensureMovements(bot) {
  if (!bot._minaMovements) {
    const m = new Movements(bot, mcData(bot))
    m.canDig = true
    m.allow1by1towers = true
    bot._minaMovements = m
  }
  bot.pathfinder.setMovements(bot._minaMovements)
}

// ── Localización de entidades ──────────────────────────────────────────────────

function playerEntity(bot, username) {
  const p = bot.players[username]
  return p && p.entity ? p.entity : null
}

function nearestPlayer(bot, maxDist = 64) {
  let best = null
  let bestDist = maxDist
  for (const name in bot.players) {
    if (name === bot.username) continue
    const e = bot.players[name].entity
    if (!e) continue
    const d = e.position.distanceTo(bot.entity.position)
    if (d <= bestDist) { best = e; bestDist = d }
  }
  return best
}

function nearestEntityByName(bot, name, maxDist = 32) {
  let best = null
  let bestDist = maxDist
  for (const id in bot.entities) {
    const e = bot.entities[id]
    if (e === bot.entity || e.name !== name) continue
    const d = e.position.distanceTo(bot.entity.position)
    if (d <= bestDist) { best = e; bestDist = d }
  }
  return best
}

function nearestHostile(bot, maxDist = 16) {
  const hostiles = new Set([
    'creeper', 'zombie', 'skeleton', 'spider', 'cave_spider', 'witch',
    'enderman', 'zombified_piglin', 'husk', 'stray', 'drowned', 'pillager',
    'zombie_villager', 'phantom', 'slime', 'silverfish', 'vex',
  ])
  let best = null
  let bestDist = maxDist
  for (const id in bot.entities) {
    const e = bot.entities[id]
    if (e === bot.entity || !e.name || !hostiles.has(e.name)) continue
    const d = e.position.distanceTo(bot.entity.position)
    if (d <= bestDist) { best = e; bestDist = d }
  }
  return best
}

// ── Movimiento ──────────────────────────────────────────────────────────────────

function stopAll(bot) {
  try { bot.pathfinder.setGoal(null) } catch {}
  bot.clearControlStates()
  bot._minaFollowing = null
}

async function goNear(bot, position, range = 1) {
  ensureMovements(bot)
  await bot.pathfinder.goto(new GoalNear(position.x, position.y, position.z, range))
}

async function goToCoords(bot, x, z) {
  ensureMovements(bot)
  await bot.pathfinder.goto(new GoalXZ(Math.floor(x), Math.floor(z)))
}

// Seguir a un jugador de forma continua (goal dinámico que se re-evalúa solo).
function follow(bot, username, range = 2) {
  const e = playerEntity(bot, username)
  if (!e) return false
  ensureMovements(bot)
  bot._minaFollowing = username
  bot.pathfinder.setGoal(new GoalFollow(e, range), true)
  return true
}

async function comeToPlayer(bot, username) {
  const e = playerEntity(bot, username)
  if (!e) return false
  await goNear(bot, e.position, 2)
  return true
}

// Camina hacia una posición SIN bloquear (goal de un solo uso, no se espera). Lo usa el
// refugio nocturno para acercarse a un jugador sin tomar reflexBusy, de modo que un
// creeper u otra urgencia pueda interrumpir el camino (los reflejos llaman a stopAll).
function approach(bot, position, range = 3) {
  ensureMovements(bot)
  bot.pathfinder.setGoal(new GoalNear(position.x, position.y, position.z, range))
}

// Explorar: caminar ~24 bloques en una dirección al azar.
async function explore(bot) {
  const pos = bot.entity.position
  const angle = Math.random() * Math.PI * 2
  const x = pos.x + Math.cos(angle) * 24
  const z = pos.z + Math.sin(angle) * 24
  await goToCoords(bot, x, z)
}

// ── Minar (con herramienta correcta + recoger el drop) ───────────────────────────

function toolCategoryFor(blockName) {
  if (/_log$|_wood$|planks|crafting_table|chest|bookshelf|door|fence|ladder|sign/.test(blockName)) return 'axe'
  if (/dirt|grass_block|sand|gravel|clay|soul_sand|soul_soil|farmland|podzol|mycelium|snow/.test(blockName)) return 'shovel'
  if (/leaves|wool|cobweb/.test(blockName)) return null // no hace falta herramienta especial
  return 'pickaxe'
}

function tierRank(itemName) {
  for (let i = 0; i < TOOL_TIERS.length; i++) {
    if (itemName.startsWith(TOOL_TIERS[i])) return TOOL_TIERS.length - i
  }
  return 0
}

async function equipBestTool(bot, blockName) {
  const cat = toolCategoryFor(blockName)
  if (!cat) return
  const tools = bot.inventory.items().filter(i => i.name.endsWith('_' + cat))
  if (!tools.length) return
  tools.sort((a, b) => tierRank(b.name) - tierRank(a.name))
  if (bot.heldItem && bot.heldItem.name === tools[0].name) return
  try { await bot.equip(tools[0], 'hand') } catch {}
}

async function equipBestWeapon(bot) {
  const swords = bot.inventory.items().filter(i => i.name.endsWith('_sword'))
  const axes = bot.inventory.items().filter(i => i.name.endsWith('_axe'))
  const pool = swords.length ? swords : axes
  if (!pool.length) return
  pool.sort((a, b) => tierRank(b.name) - tierRank(a.name))
  if (bot.heldItem && bot.heldItem.name === pool[0].name) return
  try { await bot.equip(pool[0], 'hand') } catch {}
}

// Mina hasta `count` bloques del tipo dado y recoge lo que caiga.
// Devuelve cuántos minó.
async function mineNearest(bot, blockName, count = 1) {
  const data = mcData(bot)
  const type = data.blocksByName[blockName]
  if (!type) return 0

  let mined = 0
  for (let n = 0; n < count; n++) {
    const block = bot.findBlock({ matching: type.id, maxDistance: 48 })
    if (!block) break

    ensureMovements(bot)
    try {
      await bot.pathfinder.goto(new GoalGetToBlock(block.position.x, block.position.y, block.position.z))
    } catch { break }

    await equipBestTool(bot, block.name)
    if (!bot.canDigBlock(block)) continue
    try {
      await bot.dig(block)
      mined++
    } catch { /* el bloque cambió o no se pudo */ }
  }

  if (mined > 0) await collectNearbyItems(bot, 8)
  return mined
}

// ── Talar árbol completo ─────────────────────────────────────────────────────────

const LOG_NAMES = new Set([
  'oak_log', 'birch_log', 'spruce_log', 'jungle_log', 'acacia_log', 'dark_oak_log',
  'mangrove_log', 'cherry_log', 'pale_oak_log',
])

// Encuentra todos los troncos conectados a uno inicial (incluye ramas) con un
// "flood-fill" en 3x3x3. Atravesamos solo troncos, así que no salta a otro árbol
// salvo que sus troncos se toquen. Tope de seguridad para árboles enormes (jungla).
function collectTreeLogs(bot, start) {
  const key = p => `${p.x},${p.y},${p.z}`
  const visited = new Set([key(start.position)])
  const queue = [start.position]
  const logs = []
  const MAX = 96

  while (queue.length && logs.length < MAX) {
    const pos = queue.shift()
    const block = bot.blockAt(pos)
    if (!block || !LOG_NAMES.has(block.name)) continue // muro: no exploramos sus vecinos
    logs.push(block)
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dz = -1; dz <= 1; dz++) {
          if (!dx && !dy && !dz) continue
          const np = pos.offset(dx, dy, dz)
          const k = key(np)
          if (visited.has(k)) continue
          visited.add(k)
          queue.push(np)
        }
      }
    }
  }
  return logs
}

// Tala el árbol más cercano (o del tipo dado): pica todos sus troncos de abajo
// hacia arriba y recoge troncos/manzanas/retoños. Devuelve cuántos troncos taló.
async function chopTree(bot, blockName = null) {
  const data = mcData(bot)
  let start
  if (blockName && data.blocksByName[blockName]) {
    start = bot.findBlock({ matching: data.blocksByName[blockName].id, maxDistance: 48 })
  } else {
    const logIds = [...LOG_NAMES].map(n => data.blocksByName[n]).filter(Boolean).map(b => b.id)
    start = bot.findBlock({ matching: logIds, maxDistance: 48 })
  }
  if (!start) return 0

  const logs = collectTreeLogs(bot, start).sort((a, b) => a.position.y - b.position.y)
  ensureMovements(bot)
  await equipBestTool(bot, start.name)

  let chopped = 0
  const deadline = Date.now() + 30000
  for (const log of logs) {
    if (Date.now() > deadline) break
    const block = bot.blockAt(log.position) // re-leemos: pudo cambiar
    if (!block || !LOG_NAMES.has(block.name)) continue
    try {
      await bot.pathfinder.goto(new GoalGetToBlock(block.position.x, block.position.y, block.position.z))
    } catch { continue } // no alcanzable (tronco flotante alto): lo saltamos
    await equipBestTool(bot, block.name)
    if (!bot.canDigBlock(block)) continue
    try {
      await bot.dig(block)
      chopped++
    } catch { /* el bloque cambió */ }
  }

  if (chopped > 0) await collectNearbyItems(bot, 12)
  return chopped
}

// ── Combate ──────────────────────────────────────────────────────────────────────

// Ataca al mob más cercano con ese nombre hasta matarlo o perderlo (máx ~12s).
async function attackNearest(bot, mobName) {
  let target = nearestEntityByName(bot, mobName, 24)
  if (!target) return false

  await equipBestWeapon(bot)
  ensureMovements(bot)

  const deadline = Date.now() + 12000
  while (target && target.isValid && Date.now() < deadline) {
    const dist = target.position.distanceTo(bot.entity.position)
    if (dist > 3.2) {
      bot.pathfinder.setGoal(new GoalFollow(target, 2), true)
    } else {
      bot.pathfinder.setGoal(null)
      await bot.lookAt(target.position.offset(0, target.height * 0.9, 0))
      bot.attack(target)
    }
    await sleep(500)
    target = bot.entities[target.id] && bot.entities[target.id].isValid
      ? bot.entities[target.id]
      : nearestEntityByName(bot, mobName, 24)
  }
  bot.pathfinder.setGoal(null)
  return true
}

// ── Recoger / soltar items ───────────────────────────────────────────────────────

async function collectNearbyItems(bot, radius = 16) {
  let collected = 0
  for (let pass = 0; pass < 8; pass++) {
    const drops = Object.values(bot.entities)
      .filter(e => e.name === 'item' && e.position.distanceTo(bot.entity.position) <= radius)
      .sort((a, b) =>
        a.position.distanceTo(bot.entity.position) - b.position.distanceTo(bot.entity.position))
    if (!drops.length) break
    const item = drops[0]
    try {
      await goNear(bot, item.position, 0)
      collected++
    } catch { break }
  }
  return collected
}

async function dropItem(bot, itemName, towardUsername = null, count = null) {
  const items = bot.inventory.items()
  const match = itemName
    ? items.find(i => i.name === itemName || i.name.includes(itemName))
    : items[0]
  if (!match) return false

  if (towardUsername) {
    const e = playerEntity(bot, towardUsername)
    if (e) { try { await bot.lookAt(e.position.offset(0, 1.5, 0)) } catch {} }
  }
  try {
    await bot.toss(match.type, null, count || match.count)
    return true
  } catch { return false }
}

// ── Comer ──────────────────────────────────────────────────────────────────────

function isFood(bot, item) {
  const data = mcData(bot)
  return data.foods && data.foods[item.type] !== undefined
}

async function eatFood(bot, foodName = null) {
  if (bot.food >= 20) return false
  const item = bot.inventory.items().find(i =>
    foodName ? i.name === foodName || i.name.includes(foodName) : isFood(bot, i))
  if (!item) return false
  try {
    await bot.equip(item, 'hand')
    await bot.consume()
    return true
  } catch { return false }
}

// ── Armadura ──────────────────────────────────────────────────────────────────

const ARMOR_SLOTS = [
  { suffix: '_helmet', dest: 'head' },
  { suffix: '_chestplate', dest: 'torso' },
  { suffix: '_leggings', dest: 'legs' },
  { suffix: '_boots', dest: 'feet' },
]

async function equipArmor(bot) {
  for (const slot of ARMOR_SLOTS) {
    const piece = bot.inventory.items()
      .filter(i => i.name.endsWith(slot.suffix))
      .sort((a, b) => tierRank(b.name) - tierRank(a.name))[0]
    if (piece) { try { await bot.equip(piece, slot.dest) } catch {} }
  }
}

// ── Huir de una amenaza ──────────────────────────────────────────────────────────

async function fleeFrom(bot, entity, distance = 16) {
  if (!entity) return
  const dir = bot.entity.position.minus(entity.position)
  if (dir.norm() === 0) dir.x = 1
  const away = bot.entity.position.plus(dir.normalize().scale(distance))
  stopAll(bot)
  try { await goToCoords(bot, away.x, away.z) } catch {}
}

// ── Refugio nocturno (iluminar la zona) ──────────────────────────────────────────

// True si donde está parada mina está oscuro (luz artificial baja → riesgo de mobs).
// Solo miramos block.light (antorchas/lava), no skyLight: de noche el cielo ya no
// ilumina, así que lo relevante para decidir si poner una antorcha es la luz puesta.
function isDarkHere(bot) {
  const at = bot.blockAt(bot.entity.position.floored())
  if (!at) return false // chunk no cargado: no arriesgamos
  return (at.light || 0) <= 5
}

// Intenta colocar UNA antorcha cerca de los pies de mina para iluminar. Devuelve
// true si la colocó. Defensiva: si no tiene antorcha, no hay sitio o placeBlock
// lanza, devuelve false. Busca 'torch' exacto (no soul_torch/redstone_torch).
async function placeTorchNearby(bot) {
  const torch = bot.inventory.items().find(i => i.name === 'torch')
  if (!torch) return false

  const feet = bot.entity.position.floored()
  // Colocamos antorchas DE PIE sobre el suelo de las celdas vecinas (lados y diagonales),
  // que es lo fiable: la antorcha va en una celda de aire libre AL LADO de mina.
  const around = [
    new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1),
    new Vec3(1, 0, 1), new Vec3(1, 0, -1), new Vec3(-1, 0, 1), new Vec3(-1, 0, -1),
  ]
  const candidates = around.map(f => ({ ref: feet.offset(f.x, -1, f.z), face: new Vec3(0, 1, 0) }))
  candidates.push({ ref: feet.offset(0, -1, 0), face: new Vec3(0, 1, 0) }) // último recurso: bajo los pies

  let equipped = false
  for (const c of candidates) {
    const ref = bot.blockAt(c.ref)
    if (!ref || ref.boundingBox !== 'block') continue // la referencia debe ser sólida
    const dest = ref.position.plus(c.face)
    const destBlock = bot.blockAt(dest)
    if (!destBlock || destBlock.boundingBox !== 'empty') continue // el hueco debe estar libre
    try {
      if (!equipped) { await bot.equip(torch, 'hand'); equipped = true }
      await bot.placeBlock(ref, c.face) // async; lanza si no se colocó
      return true
    } catch { /* ese sitio no sirvió: probamos el siguiente */ }
  }
  return false
}

// ── util ──────────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms))
}

module.exports = {
  ensureMovements,
  playerEntity,
  nearestPlayer,
  nearestEntityByName,
  nearestHostile,
  stopAll,
  goNear,
  goToCoords,
  follow,
  comeToPlayer,
  approach,
  explore,
  equipBestTool,
  equipBestWeapon,
  mineNearest,
  chopTree,
  attackNearest,
  collectNearbyItems,
  dropItem,
  eatFood,
  equipArmor,
  fleeFrom,
  isDarkHere,
  placeTorchNearby,
  sleep,
}
