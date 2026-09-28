// ── vocab.js ───────────────────────────────────────────────────────────────────
// Traduce palabras en español (o nombres ya válidos) a IDs de minecraft-data.
// Lo usan tanto los comandos de chat como el ejecutor del LLM.
// (De Another-craft; Lune añade la lista blanca de mobs que se pueden atacar.)
'use strict'

const BLOCK_WORDS = {
  madera: 'oak_log', tronco: 'oak_log', arbol: 'oak_log', árbol: 'oak_log',
  roble: 'oak_log', abedul: 'birch_log', pino: 'spruce_log', abeto: 'spruce_log',
  jungla: 'jungle_log', acacia: 'acacia_log', cerezo: 'cherry_log',
  tablas: 'oak_planks', tabla: 'oak_planks', palo: 'stick', palos: 'stick',
  piedra: 'stone', cobblestone: 'cobblestone', roca: 'stone', adoquin: 'cobblestone',
  carbon: 'coal_ore', carbón: 'coal_ore',
  hierro: 'iron_ore', fierro: 'iron_ore',
  oro: 'gold_ore',
  diamante: 'diamond_ore', diamantes: 'diamond_ore',
  cobre: 'copper_ore', redstone: 'redstone_ore', esmeralda: 'emerald_ore',
  lapis: 'lapis_ore', lapislazuli: 'lapis_ore', lapislázuli: 'lapis_ore',
  cuarzo: 'nether_quartz_ore', obsidiana: 'obsidian',
  arena: 'sand', tierra: 'dirt', grava: 'gravel', arcilla: 'clay',
  nieve: 'snow', hielo: 'ice', cesped: 'grass_block', césped: 'grass_block',
  trigo: 'wheat', zanahoria: 'carrots', papa: 'potatoes', patata: 'potatoes',
  remolacha: 'beetroots', calabaza: 'pumpkin', melon: 'melon', melón: 'melon',
  caña: 'sugar_cane', cana: 'sugar_cane', bambu: 'bamboo', bambú: 'bamboo',
  mesa: 'crafting_table', horno: 'furnace', cofre: 'chest', antorcha: 'torch',
}

const MOB_WORDS = {
  zombi: 'zombie', zombie: 'zombie', muerto: 'zombie',
  creeper: 'creeper', creepers: 'creeper',
  esqueleto: 'skeleton', esqueletos: 'skeleton',
  arana: 'spider', araña: 'spider', aranas: 'spider', arañas: 'spider',
  bruja: 'witch', enderman: 'enderman', slime: 'slime', limo: 'slime',
  ahogado: 'drowned', husk: 'husk', momia: 'husk', phantom: 'phantom', fantasma: 'phantom',
  saqueador: 'pillager', pillager: 'pillager', blaze: 'blaze',
  vaca: 'cow', vacas: 'cow', cerdo: 'pig', puerco: 'pig', cerdos: 'pig',
  oveja: 'sheep', ovejas: 'sheep', pollo: 'chicken', gallina: 'chicken', pollos: 'chicken',
  caballo: 'horse', aldeano: 'villager', aldeanos: 'villager',
  lobo: 'wolf', perro: 'wolf', conejo: 'rabbit', conejos: 'rabbit',
  gato: 'cat', zorro: 'fox', oso: 'panda', panda: 'panda', abeja: 'bee', abejas: 'bee',
  tortuga: 'turtle', delfin: 'dolphin', delfín: 'dolphin', axolote: 'axolotl', axolotl: 'axolotl',
}

// Hostiles (también los usan los reflejos y el observador).
const HOSTILES = new Set([
  'creeper', 'zombie', 'skeleton', 'spider', 'cave_spider', 'witch', 'enderman',
  'zombified_piglin', 'husk', 'stray', 'drowned', 'pillager', 'zombie_villager',
  'phantom', 'slime', 'silverfish', 'vex', 'blaze', 'magma_cube', 'vindicator',
  'evoker', 'ravager', 'guardian', 'hoglin', 'piglin_brute', 'bogged', 'breeze',
])

// Lo ÚNICO que el bot ataca (lo pida el chat, Lune o su modelo): hostiles y animales
// de granja. Nunca `player`, aldeanos, mascotas, golems, soportes de armadura…
const MOBS_ATACABLES = new Set([...HOSTILES, 'cow', 'pig', 'sheep', 'chicken', 'rabbit'])

function normalize (str) {
  return (str || '').toLowerCase().trim()
}

// Devuelve un nombre de bloque válido o null.
function toBlockName (word) {
  const w = normalize(word)
  return BLOCK_WORDS[w] || (/^[a-z_]+$/.test(w) ? w : null)
}

// Devuelve un nombre de mob válido o null.
function toMobName (word) {
  const w = normalize(word)
  return MOB_WORDS[w] || (/^[a-z_]+$/.test(w) ? w : null)
}

/** ¿Se puede atacar a este mob? (lista blanca) */
function atacable (nombre) {
  return MOBS_ATACABLES.has(normalize(nombre))
}

module.exports = { toBlockName, toMobName, normalize, atacable, BLOCK_WORDS, MOB_WORDS, HOSTILES, MOBS_ATACABLES }
