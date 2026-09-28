// ── commands.js ──────────────────────────────────────────────────────────────────
// Órdenes directas por el chat del juego (y las que manda Lune). Se resuelven al
// instante, SIN el modelo: rápidas y fiables. Si el mensaje no es una orden,
// handleCommand devuelve null y bot.js decide si lo piensa el modelo.
//
// SOLO cuenta lo DIRIGIDO al bot (el chat del servidor es de todos):
//   · la orden va AL PRINCIPIO del mensaje (tras «oye», «porfa»… y la mención):
//     «sígueme», «Lune, ven aquí», «mina 10 hierro porfa». Una palabra suelta en
//     medio de una conversación no es una orden («voy para casa», «esto es para ti»);
//   · «para» / «espera»… solo si es TODO el mensaje (con «ya», «ahí»… o la mención);
//   · el dueño puede dar la orden sin mencionar al bot; los demás jugadores solo
//     cuentan si lo mencionan (nick o nombre del personaje). A un desconocido que
//     no lo menciona no se le contesta nada (antes: «Solo obedezco a X» a
//     cualquier frase con «para», «ven» o «espera», cada 2,5 s).
//
// De Another-craft, con estos cambios de Lune:
//   · Por inyección: crearComandos({skills, mcData, charla, decir, dueno, soloDueno,
//     nombres}); los tests pasan dobles, sin mineflayer.
//   · El DUEÑO es FIJO (config.dueno): ya no pasa a ser «el último que habla».
//   · Con solo_dueno, los demás (si mencionan al bot) solo reciben respuestas
//     sociales (hola, gracias, chiste, ayuda…); una orden suya se contesta con
//     «Solo obedezco a X».
//     OJO: con online-mode=false un nick se puede suplantar; es un filtro, no una
//     garantía (la tarjeta de Ajustes lo avisa).
//   · Nunca ataca a jugadores ni a nada fuera de la lista blanca (vocab.atacable).
//   · «dame/suelta» solo al dueño.
//   · Las órdenes de Lune llegan como handleCommand(bot, dueño, texto, {origen:'lune'})
//     y solo ellas pueden usar «di <texto>» (el bot lo dice, saneado).
//   · La mención usa el nick del bot y el nombre del personaje (letras Unicode):
//     «mina hierro» es minar aunque el bot se llame Mina.
'use strict'

const vocab = require('./vocab')
const { nickSeguro, limpiarChat } = require('./sanear')

const SOCIALES = new Set(['greet', 'thanks', 'praise', 'love', 'joke', 'hora', 'ayuda'])
const AYUDA = 'Sé: sígueme, ven, para, mina <bloque>, tala árbol, ataca <mob>, defiéndeme, recoge, ' +
  'dame <objeto>, come, explora, inventario, dónde estás, vida, mírame, salta, baila, chiste.'

// Quita acentos y signos para emparejar órdenes sin pelearnos con la ortografía.
function clean (text) {
  return String(text ?? '')
    .toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[¿?¡!.,;:"«»]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function escaparRegex (s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Interpreta un texto ya limpio (clean, y sin la mención ni las muletillas del principio)
 * → {tipo, …} o null. La orden tiene que ir AL PRINCIPIO; «para» y compañía, ser todo el
 * mensaje. Puro salvo `real*`, que comprueban contra minecraft-data (para que «mina hola»
 * no intente minar «hola»).
 */
function interpretar (text, { realBlock, realMob, origen = 'usuario' } = {}) {
  const words = text.split(/\s+/).filter(Boolean)
  let m

  if (origen === 'lune') {
    m = text.match(/^di\s+(.+)$/)
    if (m) return { tipo: 'di' }
  }
  if (/^(sigueme|sigue ?me|ven conmigo|acompaname|follow me|follow)\b/.test(text)) return { tipo: 'seguir' }
  if (/^(ven aqui|ven aca|ven|acercate|come here)\b/.test(text) && !/^ven a (minar|por|el|la)\b/.test(text)) return { tipo: 'ven' }
  if (/^(para|parate|detente|quieta|quieto|quedate(?: quiet[ao]| ahi| aqui)?|alto|stop|espera)(?: (?:ya|ahi|aqui|ahora))?$/.test(text)) return { tipo: 'para' }
  if (/^(tala|talar|corta|cortar|tumba|tumbar)\b/.test(text)) {
    let wood = null
    for (const w of words) {
      if (/^(madera|tronco|arbol|el|un|de|tala|talar|corta|cortar|tumba|tumbar)$/.test(w)) continue
      const b = realBlock(w)
      if (b && /_log$/.test(b)) { wood = b; break }
    }
    return { tipo: 'tala', madera: wood }
  }
  m = text.match(/^(mina|minar|pica|picar|consigue|consigueme)\s+(\d+\s+)?(.+)/)
  if (m && !/\bme sigues?\b/.test(text)) {
    const bloque = realBlock(m[3].split(/\s+/)[0])
    if (bloque) return { tipo: 'mina', bloque, cantidad: Math.min(m[2] ? parseInt(m[2]) : 1, 64) }
  }
  m = text.match(/^(ataca|atacar|mata|matar|pega|golpea)\s+(?:el |la |al |a )?(.+)/)
  if (m) {
    const palabra = m[2].split(/\s+/)[0]
    const mob = realMob(palabra)
    if (mob) return { tipo: 'ataca', mob, permitido: vocab.atacable(mob) }
    if (nickSeguro(palabra)) return { tipo: 'ataca', mob: palabra, permitido: false }
  }
  if (/^(defiendeme|protegeme|defiende)\b/.test(text)) return { tipo: 'defiende' }
  if (/^(recoge|recoger|junta los items|levanta)\b/.test(text)) return { tipo: 'recoge' }
  m = text.match(/^(suelta|tira|dame|dropea|pasame)\s+(?:el |la |un |una |unos |unas )?(.+)/)
  if (m) {
    const palabra = m[2].split(/\s+/)[0]
    return { tipo: 'suelta', item: vocab.toBlockName(palabra) || palabra }
  }
  if (/^(come|comer|come algo|alimentate)\b/.test(text)) return { tipo: 'come' }
  if (/^(explora|explorar|camina|pasea|ve a explorar)\b/.test(text)) return { tipo: 'explora' }
  if (/^(inventario|que tienes|que llevas|mochila)\b/.test(text)) return { tipo: 'inventario' }
  if (/^(donde estas|coordenadas|posicion|ubicacion)\b/.test(text)) return { tipo: 'donde' }
  if (/^(tu vida|tu salud|cuanta vida|tu hambre|como estas de vida)\b/.test(text) || /^(vida|salud|hambre)$/.test(text)) return { tipo: 'vida' }
  if (/^(mirame|voltea|mira aca|mira aqui|look)\b/.test(text)) return { tipo: 'mirame' }
  if (/^(salta|brinca|jump)\b/.test(text)) return { tipo: 'salta' }
  if (/^(baila|bailar|dance)\b/.test(text)) return { tipo: 'baila' }
  if (/^(chiste|cuentame un chiste|hazme reir|un chiste|joke)\b/.test(text)) return { tipo: 'joke' }
  if (/^(que hora es|es de noche|es de dia|hora del juego)\b/.test(text)) return { tipo: 'hora' }
  if (/^(ayuda|help|que sabes hacer|comandos)\b/.test(text)) return { tipo: 'ayuda' }
  if (/^(hola|holi|holaa+|buenas|buenos dias|buenas tardes|buenas noches|hey|hi|hello)\b/.test(text)) return { tipo: 'greet' }
  if (/^(gracias|grax|thx|thanks|te lo agradezco)\b/.test(text)) return { tipo: 'thanks' }
  if (/^(bien hecho|buen trabajo|eres genial|eres la mejor|que linda|bien hecha|crack)\b/.test(text)) return { tipo: 'praise' }
  if (/^(te quiero|te amo|me caes bien|eres adorable|te adoro)\b/.test(text)) return { tipo: 'love' }
  return null
}

// Muletillas delante (y detrás) de una orden: «oye Lune, sígueme porfa».
const MULETILLAS_INICIO = /^(?:(?:oye|ey|eh|venga|porfa|por favor)\s+)+/
const MULETILLAS_FIN = /\s+(?:porfa|por favor|ya)$/

/**
 * crearComandos({skills, mcData, charla, decir, dueno, soloDueno, nombres, ahora})
 * → {handleCommand(bot, username, message, {origen}) → Promise<{handled, reply}|null>, mencionado(texto)}
 */
function crearComandos ({ skills = null, mcData = null, charla = null, decir = null, dueno = '', soloDueno = true,
  nombres = [], ahora = () => Date.now() } = {}) {
  const sk = () => skills || require('./skills')
  const datos = mcData || ((bot) => require('minecraft-data')(bot.version))
  const di = decir || (() => false)
  const owner = nickSeguro(dueno)
  const linea = (cat, vars) => (charla && typeof charla.line === 'function' ? charla.line(cat, vars) : '')
  const elegir = (arr) => (charla && typeof charla.pick === 'function' ? charla.pick(arr) : arr[0])
  let ultimoSocial = -Infinity

  const alias = [...new Set(nombres.map((n) => String(n || '').trim()).filter((n) => n.length >= 2))]
  const reMencion = alias.length
    ? new RegExp(`(?<![\\p{L}\\p{N}_])(${alias.map(escaparRegex).join('|')})(?![\\p{L}\\p{N}_])`, 'iu')
    : null
  // La mención al principio o al final del texto YA limpio (clean: sin tildes ni signos).
  const limpios = [...new Set(alias.map(clean).filter((n) => n.length >= 2))].map(escaparRegex).join('|')
  const reMencionInicio = limpios ? new RegExp(`^(?:${limpios})(?![\\p{L}\\p{N}_])\\s*`, 'u') : null
  const reMencionFin = limpios ? new RegExp(`(?<![\\p{L}\\p{N}_])\\s*(?:${limpios})$`, 'u') : null

  /** Texto limpio → {texto sin muletillas ni mención, conMencion}. */
  function sinMencion (text) {
    let t = text.replace(MULETILLAS_INICIO, '')
    let conMencion = false
    const a = reMencionInicio && t.match(reMencionInicio)
    if (a && a[0].length < t.length) { t = t.slice(a[0].length).replace(MULETILLAS_INICIO, ''); conMencion = true }
    const b = reMencionFin && t.match(reMencionFin)
    if (b && b[0].length < t.length) { t = t.slice(0, t.length - b[0].length); conMencion = true }
    return { texto: t.replace(MULETILLAS_FIN, '').trim(), conMencion }
  }

  /** ¿Mencionan al bot (su nick o el nombre del personaje)? */
  function mencionado (texto) {
    return !!(reMencion && reMencion.test(String(texto ?? '')))
  }

  function esDueno (username) {
    return !!owner && String(username || '').toLowerCase() === owner.toLowerCase()
  }

  function run (bot, label, promise) {
    const st = bot.lune || (bot.lune = {})
    st.busy = true
    Promise.resolve(promise)
      .catch(err => console.error(`[orden:${label}]`, err && err.message))
      .finally(() => { st.busy = false })
  }

  function reply (text) { return { handled: true, reply: text || null } }

  function socialReply (text) {
    const now = ahora()
    if (now - ultimoSocial < 2500) return { handled: true, reply: null }
    ultimoSocial = now
    return reply(text)
  }

  async function handleCommand (bot, username, message, { origen = 'usuario' } = {}) {
    const text = clean(message)
    if (!text) return null
    const deLune = origen === 'lune'
    const mando = deLune || esDueno(username)
    const quien = deLune ? owner : (nickSeguro(username) || '')
    const data = () => datos(bot)
    const realBlock = (w) => {
      const n = vocab.toBlockName(w)
      try { return n && data().blocksByName[n] ? n : null } catch { return null }
    }
    const realMob = (w) => {
      const n = vocab.toMobName(w)
      try { return n && data().entitiesByName[n] ? n : null } catch { return null }
    }

    // Solo lo dirigido al bot: la orden al principio (tras la mención y las muletillas).
    // «mina hierro» con un bot llamado Mina es minar: primero se prueba sin quitar la mención.
    const { texto: resto, conMencion } = sinMencion(text)
    const mencion = conMencion || mencionado(message)
    let orden = interpretar(text.replace(MULETILLAS_INICIO, '').replace(MULETILLAS_FIN, ''), { realBlock, realMob, origen })
    if (!orden && resto !== text) orden = interpretar(resto, { realBlock, realMob, origen })
    if (!orden) return null

    if (!mando) {
      if (!mencion) return null                    // conversación entre jugadores: no es para el bot
      if (soloDueno && !SOCIALES.has(orden.tipo)) {
        return socialReply(owner ? `Solo obedezco a ${owner}.` : 'No obedezco a cualquiera.')
      }
    }

    const s = sk()
    switch (orden.tipo) {
      case 'di': {
        const dicho = limpiarChat(String(message).replace(/^\s*di\s+/i, ''), 100)
        if (!dicho) return reply('No hay nada que decir.')
        return { handled: true, reply: null, dicho: di(dicho) !== false }
      }
      case 'seguir': {
        s.stopAll(bot)
        const ok = s.follow(bot, quien)
        return reply(ok ? elegir([`Voy contigo, ${quien}.`, 'Detrás de ti.', 'Te sigo.']) : 'No te veo. ¿Dónde estás?')
      }
      case 'ven':
        s.stopAll(bot)
        run(bot, 'ven', s.comeToPlayer(bot, quien))
        return reply(elegir(['Voy.', 'Ya voy, espera.', 'En camino.']))
      case 'para':
        s.stopAll(bot)
        if (bot.lune) bot.lune.busy = false
        return reply(elegir(['Me quedo aquí.', 'Quieta.', 'Vale, paro.']))
      case 'tala':
        s.stopAll(bot)
        run(bot, 'tala', Promise.resolve(s.chopTree(bot, orden.madera))
          .then(n => di(n ? `Árbol talado: ${n} troncos.` : 'No veo ningún árbol cerca.')))
        return reply('A talar.')
      case 'mina':
        s.stopAll(bot)
        run(bot, 'mina', Promise.resolve(s.mineNearest(bot, orden.bloque, orden.cantidad))
          .then(n => di(n ? `Listo: ${n} de ${orden.bloque}.` : `No encontré ${orden.bloque} cerca.`)))
        return reply(`A picar ${orden.bloque}.`)
      case 'ataca':
        if (!orden.permitido) return reply(orden.mob === 'player' || !realMob(orden.mob) ? 'A jugadores no los ataco.' : 'Eso no lo ataco.')
        s.stopAll(bot)
        run(bot, 'ataca', Promise.resolve(s.attackNearest(bot, orden.mob))
          .then(ok => di(ok ? 'Hecho.' : `No veo ningún ${orden.mob}.`)))
        return reply(`A por el ${orden.mob}.`)
      case 'defiende': {
        const threat = s.nearestHostile(bot, 16)
        if (threat && vocab.atacable(threat.name)) {
          s.stopAll(bot)
          run(bot, 'defiende', s.attackNearest(bot, threat.name))
          return reply(`Yo me encargo de ese ${threat.name}.`)
        }
        return reply('No hay peligro cerca.')
      }
      case 'recoge':
        s.stopAll(bot)
        run(bot, 'recoge', Promise.resolve(s.collectNearbyItems(bot, 16))
          .then(n => di(n ? `Recogí ${n} cosas.` : 'No hay nada que recoger.')))
        return reply('Recogiendo.')
      case 'suelta': {
        if (!owner) return reply('No sé quién es mi dueño.')
        if (!mando) return reply(`Solo le doy cosas a ${owner}.`)
        const item = String(orden.item || '').slice(0, 48)
        run(bot, 'suelta', Promise.resolve(s.dropItem(bot, item, owner))
          .then(ok => di(ok ? `Toma, ${owner}: ${item}.` : `No tengo ${item}.`)))
        return reply('A ver qué llevo...')
      }
      case 'come':
        run(bot, 'come', Promise.resolve(s.eatFood(bot)).then(ok => di(ok ? 'Ñam.' : 'No tengo comida.')))
        return reply('Voy a comer algo.')
      case 'explora':
        s.stopAll(bot)
        run(bot, 'explora', s.explore(bot))
        return reply('Voy a dar una vuelta.')
      case 'inventario': {
        const items = bot.inventory.items()
        return reply(items.length
          ? `Llevo: ${items.map(i => `${i.count} ${i.name}`).slice(0, 8).join(', ')}.`
          : 'No llevo nada.')
      }
      case 'donde': {
        const p = bot.entity.position
        return reply(`Estoy en x=${Math.floor(p.x)} y=${Math.floor(p.y)} z=${Math.floor(p.z)}.`)
      }
      case 'vida':
        return reply(`Vida ${bot.health}/20 y hambre ${bot.food}/20.`)
      case 'mirame': {
        const e = s.playerEntity(bot, quien)
        if (e) {
          Promise.resolve(bot.lookAt(e.position.offset(0, 1.6, 0))).catch(() => {})
          return reply(elegir(['Te veo.', 'Aquí estoy.', '¿Qué?']))
        }
        return reply('No te encuentro.')
      }
      case 'salta':
        bot.setControlState('jump', true)
        setTimeout(() => bot.setControlState('jump', false), 350)
        return reply(elegir(['Hop.', 'Salto.', 'Mira.']))
      case 'baila':
        s.stopAll(bot)
        run(bot, 'baila', dance(bot, s))
        return reply(elegir(['A bailar.', 'Mira estos pasos.', 'Música, por favor.']))
      case 'joke':
        return socialReply(linea('joke'))
      case 'hora': {
        const noche = bot.time && bot.time.timeOfDay >= 13000
        return reply(noche ? 'Es de noche. Cuidado con los monstruos.' : 'Es de día.')
      }
      case 'ayuda':
        return socialReply(AYUDA)
      case 'greet':
      case 'thanks':
      case 'praise':
      case 'love':
        return socialReply(linea(orden.tipo))
      default:
        return null
    }
  }

  return { handleCommand, mencionado, esDueno }
}

// Baile: salta y gira sobre sí misma unas cuantas veces.
async function dance (bot, skills) {
  for (let i = 0; i < 6; i++) {
    bot.setControlState('jump', true)
    await skills.sleep(180)
    bot.setControlState('jump', false)
    try { await bot.look(bot.entity.yaw + Math.PI / 2, 0, true) } catch {}
    await skills.sleep(180)
  }
}

module.exports = { crearComandos, interpretar, clean, SOCIALES, AYUDA }
