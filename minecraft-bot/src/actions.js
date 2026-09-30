// ── actions.js ───────────────────────────────────────────────────────────────────
// Traduce la decisión del modelo ({chat, action, target}) a habilidades reales.
// Respeta el pánico (huir de un creeper manda) y usa un candado para no lanzar dos
// rutas de pathfinder a la vez.
//
// De Another-craft, con los límites de Lune (lista blanca):
//   · el chat va por `decir` (saneado, sin «/» inicial, con límite de ritmo);
//   · `goto` solo a ≤200 bloques de donde está;
//   · `drop` solo al DUEÑO y si está cerca (≤8 bloques);
//   · `attack` solo contra mobs atacables (vocab.MOBS_ATACABLES: nunca `player`,
//     aldeanos, animales domesticados (lobos, gatos…) ni soportes de armadura);
//   · `follow`/`come` con solo_dueno: solo al dueño.
//
// Por inyección: crearAcciones({skills, mcData, decir, dueno, soloDueno}).
'use strict'

const vocab = require('./vocab')
const { nickSeguro } = require('./sanear')

const MAX_GOTO = 200    // bloques (horizontal) que puede andar de una vez por orden del modelo
const MAX_DROP = 8      // distancia máxima al dueño para soltarle algo
const MAX_DEPTH = 5     // log->tablas->palo/mesa sobra; corta recursiones patológicas
const MAX_NODES = 2000  // tope de exploración del planificador de crafteo

function crearAcciones ({ skills = null, mcData = null, decir = null, dueno = '', soloDueno = true,
  maxGoto = MAX_GOTO, log = null } = {}) {
  const sk = () => skills || require('./skills')
  const datos = mcData || ((bot) => require('minecraft-data')(bot.version))
  const di = decir || (() => false)
  const registrar = log || ((m) => console.log(m))
  const owner = nickSeguro(dueno)

  function jugadorPermitido (bot, nombre) {
    const quien = nickSeguro(nombre) || owner
    if (!quien) return null
    if (soloDueno && quien.toLowerCase() !== owner.toLowerCase()) return owner || null
    return quien
  }

  const HANDLERS = {
    idle: async () => {},

    follow: (bot, target) => {
      const who = jugadorPermitido(bot, target)
      return who ? Promise.resolve(sk().follow(bot, who)).then(() => {}) : null
    },

    come: (bot, target) => {
      const who = jugadorPermitido(bot, target)
      return who ? sk().comeToPlayer(bot, who) : null
    },

    goto: async (bot, target) => {
      if (!target) return
      const parts = String(target).split(',').map(Number)
      if (parts.length < 2 || !parts.every(n => Number.isFinite(n))) return
      const x = parts[0]
      const z = parts[parts.length - 1]
      const p = bot.entity && bot.entity.position
      if (!p) return
      const dist = Math.hypot(x - p.x, z - p.z)
      if (dist > maxGoto) {
        registrar(`[acción] goto a ${Math.round(dist)} bloques: demasiado lejos (máx ${maxGoto})`)
        return
      }
      await sk().goToCoords(bot, x, z)
    },

    mine: (bot, target) => {
      const block = vocab.toBlockName(target)
      return block ? sk().mineNearest(bot, block, 1) : null
    },

    chop: (bot, target) => {
      const block = vocab.toBlockName(target)
      return sk().chopTree(bot, block && /_log$/.test(block) ? block : null)
    },

    attack: (bot, target) => {
      const mob = vocab.toMobName(target)
      if (!mob || !vocab.atacable(mob)) return null
      return sk().attackNearest(bot, mob)
    },

    collect: (bot) => sk().collectNearbyItems(bot, 16),

    craft: (bot, target) => craftItem(bot, target, { datos, decir: di, skills: sk() }),

    eat: (bot, target) => sk().eatFood(bot, target),

    drop: (bot, target) => {
      if (!owner || !target) return null
      const e = sk().playerEntity(bot, owner)
      if (!e || !bot.entity || e.position.distanceTo(bot.entity.position) > MAX_DROP) return null
      return sk().dropItem(bot, vocab.toBlockName(target) || target, owner)
    },

    flee: (bot) => {
      const threat = sk().nearestHostile(bot, 16)
      return threat ? sk().fleeFrom(bot, threat, 16) : null
    },

    explore: (bot) => sk().explore(bot),
  }

  async function executeDecision (bot, decision) {
    const { chat, action, target, reason } = decision || {}
    registrar(`[lune] ${reason || ''} → ${action}(${target || '-'})`)

    if (chat) di(String(chat))

    // El pánico (huir de un creeper) tiene prioridad absoluta sobre lo que pida el modelo.
    const st = bot.lune || {}
    if (st.panic || st.reflexBusy) return false

    const handler = HANDLERS[action]
    if (!handler || action === 'idle') return false

    st.busy = true
    try {
      await handler(bot, target)
      return true
    } catch (err) {
      registrar(`[acción] error en ${action}: ${err && err.message}`)
      return false
    } finally {
      st.busy = false
    }
  }

  return { executeDecision, HANDLERS, MAX_GOTO: maxGoto }
}

// ── Crafteo recursivo (planificar → ejecutar), de Another-craft ─────────────────────
// 1) PLANIFICAR (puro) sobre un inventario SIMULADO; si una rama no se completa se
//    revierte y se prueba otra receta. Una receta que necesita mesa planifica una.
// 2) EJECUTAR: colocar la mesa cuando toque y fabricar.
async function craftItem (bot, name, { datos, decir, skills }) {
  const itemName = vocab.toBlockName(name) || name
  if (!itemName) return
  const data = datos(bot)
  const item = data.itemsByName[itemName]
  if (!item) { decir(`No sé qué es «${itemName}».`); return }

  if (bot.inventory.count(item.id, null) >= 1) {
    decir(`Ya tengo ${itemName}.`)
    return
  }

  const res = await planAndCraft(bot, data, item.id, 1, skills)
  if (res.ok) decir(`Hecho: ${itemName}.`)
  else decir(`No pude fabricar ${itemName}: ${res.reason}`)
}

async function planAndCraft (bot, data, itemId, need, skills) {
  const tableBlock = data.blocksByName.crafting_table
  const worldTable = !!(tableBlock && bot.findBlock({ matching: tableBlock.id, maxDistance: 16 }))
  const ctx = { bot, data, sim: simInventory(bot), inProgress: new Set(), failed: new Map(), nodes: 0, steps: [], worldTable }
  let res
  try {
    res = plan(ctx, itemId, need, 0)
  } catch (err) {
    return { ok: false, reason: cleanErr(err) }
  }
  if (!res.ok) return res
  return executePlan(bot, data, ctx.steps, skills)
}

function simInventory (bot) {
  const sim = {}
  for (const it of bot.inventory.items()) sim[it.type] = (sim[it.type] || 0) + it.count
  return sim
}
function simCount (ctx, id) { return ctx.sim[id] || 0 }

function plan (ctx, itemId, need, depth) {
  const { bot, data } = ctx
  const nm = (data.items[itemId] && data.items[itemId].name) || itemId

  if (simCount(ctx, itemId) >= need) return { ok: true }
  if (depth > MAX_DEPTH) return { ok: false, reason: `receta demasiado profunda (${nm})` }
  if (ctx.inProgress.has(itemId)) return { ok: false, reason: `ciclo de recetas en ${nm}` }
  if (ctx.failed.has(itemId)) return { ok: false, reason: ctx.failed.get(itemId) }
  if (++ctx.nodes > MAX_NODES) return { ok: false, reason: 'plan demasiado complejo' }

  ctx.inProgress.add(itemId)
  try {
    const recipes = sortRecipes(ctx, bot.recipesAll(itemId, null, true))
    if (!recipes.length) {
      const reason = `no hay receta para ${nm} (hay que minarlo o talarlo)`
      ctx.failed.set(itemId, reason)
      return { ok: false, reason }
    }

    let lastReason = `no pude conseguir ${nm}`
    for (const recipe of recipes) {
      const snap = { sim: { ...ctx.sim }, stepsLen: ctx.steps.length, worldTable: ctx.worldTable }
      const attempt = planRecipe(ctx, itemId, need, depth, recipe)
      if (attempt.ok && simCount(ctx, itemId) >= need) return { ok: true }
      ctx.sim = snap.sim
      ctx.steps.length = snap.stepsLen
      ctx.worldTable = snap.worldTable
      lastReason = attempt.reason || lastReason
    }
    return { ok: false, reason: lastReason }
  } finally {
    ctx.inProgress.delete(itemId)
  }
}

function planRecipe (ctx, itemId, need, depth, recipe) {
  const { data } = ctx
  const haveNow = simCount(ctx, itemId)
  const perCraft = recipe.result.count || 1
  const crafts = Math.max(1, Math.ceil((need - haveNow) / perCraft))

  for (const d of recipe.delta) {
    if (d.count >= 0) continue
    const required = -d.count * crafts
    if (simCount(ctx, d.id) < required) {
      const sub = plan(ctx, d.id, required, depth + 1)
      if (!sub.ok) return sub
    }
    ctx.sim[d.id] = simCount(ctx, d.id) - required
  }

  let placeTable = false
  if (recipe.requiresTable && !ctx.worldTable) {
    const tableItem = data.itemsByName.crafting_table
    if (!tableItem) return { ok: false, reason: 'no conozco la mesa de crafteo' }
    if (simCount(ctx, tableItem.id) < 1) {
      const sub = plan(ctx, tableItem.id, 1, depth + 1)
      if (!sub.ok) return { ok: false, reason: `necesito una mesa: ${sub.reason}` }
    }
    ctx.sim[tableItem.id] = simCount(ctx, tableItem.id) - 1
    ctx.worldTable = true
    placeTable = true
  }

  for (const d of recipe.delta) {
    if (d.count <= 0) continue
    ctx.sim[d.id] = simCount(ctx, d.id) + d.count * crafts
  }
  ctx.steps.push({ recipe, crafts, requiresTable: recipe.requiresTable, placeTable })
  return { ok: true }
}

function sortRecipes (ctx, recipes) {
  return recipes
    .map(r => {
      let missing = 0
      let total = 0
      for (const d of r.delta) {
        if (d.count >= 0) continue
        total++
        if (simCount(ctx, d.id) < -d.count) missing++
      }
      return { r, table: r.requiresTable ? 1 : 0, missing, total }
    })
    .sort((a, b) => a.table - b.table || a.missing - b.missing || a.total - b.total)
    .map(x => x.r)
}

async function executePlan (bot, data, steps, skills) {
  const tableBlock = data.blocksByName.crafting_table
  let worldTable = tableBlock ? bot.findBlock({ matching: tableBlock.id, maxDistance: 16 }) : null
  if (worldTable) { try { await skills.goNear(bot, worldTable.position, 2) } catch {} }

  for (const step of steps) {
    if (step.placeTable && !worldTable) {
      const inv = bot.inventory.items().find(i => i.name === 'crafting_table')
      if (!inv) return { ok: false, reason: 'no tengo mesa para colocar' }
      try {
        await bot.equip(inv, 'hand')
        worldTable = await placeCraftingTable(bot, tableBlock)
        if (worldTable) { try { await skills.goNear(bot, worldTable.position, 2) } catch {} }
      } catch {}
      if (!worldTable) return { ok: false, reason: 'no pude colocar la mesa de crafteo' }
    }
    const useTable = step.requiresTable ? worldTable : null
    if (step.requiresTable && !useTable) return { ok: false, reason: 'falta la mesa de crafteo' }
    try {
      await bot.craft(step.recipe, step.crafts, useTable)
    } catch (err) {
      return { ok: false, reason: cleanErr(err) }
    }
  }
  return { ok: true }
}

async function placeCraftingTable (bot, tableType) {
  const Vec3 = require('vec3')
  const base = bot.entity.position.floored()
  const offsets = [
    new Vec3(1, -1, 0), new Vec3(-1, -1, 0), new Vec3(0, -1, 1), new Vec3(0, -1, -1),
    new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1),
    new Vec3(0, -1, 0),
  ]
  for (const off of offsets) {
    const ref = bot.blockAt(base.plus(off))
    if (!ref || ref.boundingBox !== 'block') continue
    const dest = ref.position.offset(0, 1, 0)
    const destBlock = bot.blockAt(dest)
    if (!destBlock || destBlock.boundingBox !== 'empty') continue
    if (dest.equals(base) || dest.equals(base.offset(0, 1, 0))) continue
    try {
      await bot.placeBlock(ref, new Vec3(0, 1, 0))
      const placed = bot.findBlock({ matching: tableType.id, maxDistance: 4 })
      if (placed) return placed
    } catch { /* probamos el siguiente candidato */ }
  }
  return null
}

// Limpia el doble prefijo "Error: ..." que produce bot.craft (throw new Error(err)).
function cleanErr (err) {
  return String((err && err.message) || err).replace(/^Error:\s*/, '')
}

module.exports = { crearAcciones, MAX_GOTO, MAX_DROP }
