// ── bot.js ───────────────────────────────────────────────────────────────────────
// Punto de entrada del bot de Minecraft de Lune (adaptado de Another-craft «mina»).
// NO se arranca a mano: lo lanza Lune (lune_core/minecraft_proceso.py) como
// proceso hijo, `node [--permission …] src/bot.js`, sin shell ni npm start.
//
// Arranque:
//   1. Exige LUNE_MC_TOKEN (uno nuevo en cada lanzamiento) y lo borra del entorno.
//   2. Espera 10 s la PRIMERA línea de stdin, {"tipo":"config", …} (config.js la
//      valida; la clave del modelo viaja aquí, nunca en el entorno ni en el log).
//      Sin ella, sale.
//   3. Con --probar: comprueba que las dependencias cargan (también bajo
//      `node --permission`), emite `listo {probar:true}` y sale sin conectarse.
//   4. Si no, createBot({…, auth:'offline'}): SOLO servidores con online-mode=false.
//
// Tres capas de mente (como en Another-craft):
//   1) Reflejos  (reflexes.js) → supervivencia en tiempo real, sin modelo;
//   2) Órdenes   (commands.js) → respuestas instantáneas del chat y de Lune;
//   3) Cerebro   (brain.js)    → personalidad y decisiones con su modelo; en pausa
//      mientras Lune piensa (pausa_llm) y el bucle autónomo en pausa durante el
//      modo juego de Lune (pausa_autonomo). Órdenes, reflejos y menciones siguen.
//
// Hacia Lune (canal.js): listo, conectado, desconectado {motivo}, estado (cada 5 s),
// evento (observador.js), chat {de, texto} (texto de terceros, saneado),
// respuesta {id, texto} y error. Desde Lune: orden, decir, pausa_llm,
// pausa_autonomo, estado y salir. Al cerrarse stdin, el bot sale.
//
// Toda salida de consola va con el prefijo «[bot] » y en una sola línea: nada
// que escriba el juego puede empezar una línea por «@@LUNE».
'use strict'

const { crearCanal } = require('./canal')
const { validarConfig } = require('./config')
const { limpiarChat, nickSeguro, crearLimitador } = require('./sanear')

const ESPERA_CONFIG_MS = 10000
const ESTADO_CADA_MS = 5000
const ID_ORDEN = /^[A-Za-z0-9_-]{1,40}$/
const MAX_ORDEN = 200

/** console.* → una línea «[bot] …» sin controles (ni saltos) en stdout. */
function instalarConsola (escribir = (l) => process.stdout.write(l + '\n')) {
  const linea = (...args) => {
    const t = args.map((a) => (a instanceof Error ? a.message : typeof a === 'string' ? a : (() => {
      try { return JSON.stringify(a) } catch { return String(a) }
    })())).join(' ')
    const limpio = t.replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]+/g, ' ').slice(0, 500)
    try { escribir('[bot] ' + limpio) } catch {}
  }
  for (const k of ['log', 'info', 'warn', 'error', 'debug']) console[k] = linea
  return linea
}

/** Texto legible de un motivo de expulsión (string, JSON de chat o ChatMessage). */
function textoMotivo (reason) {
  const plano = (x, prof = 0) => {
    if (x == null || prof > 6) return ''
    if (typeof x === 'string') {
      const s = x.trim()
      if ((s.startsWith('{') || s.startsWith('[')) && prof === 0) {
        try { return plano(JSON.parse(s), prof + 1) } catch { return s }
      }
      return s
    }
    if (Array.isArray(x)) return x.map((y) => plano(y, prof + 1)).join('')
    if (typeof x === 'object') {
      if (typeof x.toString === 'function' && x.toString !== Object.prototype.toString) return String(x.toString())
      let t = typeof x.text === 'string' ? x.text : (typeof x.translate === 'string' ? x.translate : '')
      if (Array.isArray(x.extra)) t += x.extra.map((y) => plano(y, prof + 1)).join('')
      return t
    }
    return String(x)
  }
  return limpiarChat(plano(reason), 200)
}

/** Explica un motivo de desconexión o error de red en castellano. */
function explicar (motivo, cfg = {}) {
  const m = String(motivo || '')
  if (/ECONNREFUSED/i.test(m)) return `No hay ningún servidor en ${cfg.host}:${cfg.port} (¿está abierto?).`
  if (/ENOTFOUND|EAI_AGAIN/i.test(m)) return `No encuentro el servidor «${cfg.host}».`
  if (/ETIMEDOUT|timed out/i.test(m)) return 'El servidor no contesta (tiempo agotado).'
  if (/logged in|authenticat|verify|premium|online.?mode|invalid session/i.test(m)) {
    return 'El servidor pide cuentas de Microsoft (online-mode=true): el bot solo entra en servidores con online-mode=false. ' +
      '«Abrir en LAN» del juego normal tampoco sirve.'
  }
  if (/outdated|version/i.test(m)) return `Versión incompatible: ${m}`
  if (/^socketClosed$/i.test(m)) return 'Se cerró la conexión con el servidor.'
  return m || 'Desconectado.'
}

/**
 * Crea el bot de mineflayer y engancha las capas. Solo aquí se cargan mineflayer
 * y compañía (los tests de los demás módulos no los necesitan).
 * → {atender(mensaje), cerrar(), bot}
 */
function crearBot (cfg, canal, { requerir = require, ahora = () => Date.now(), salir = () => {} } = {}) {
  const mineflayer = requerir('mineflayer')
  const { pathfinder } = requerir('mineflayer-pathfinder')
  const skills = requerir('./skills')
  const { getWorldContext } = requerir('./world')
  const { crearCerebro } = requerir('./brain')
  const { crearAcciones } = requerir('./actions')
  const { crearComandos } = requerir('./commands')
  const { crearCharla } = requerir('./chatter')
  const { startReflexes } = requerir('./reflexes')
  const { crearObservador } = requerir('./observador')

  const bot = mineflayer.createBot({
    host: cfg.host,
    port: cfg.port,
    username: cfg.nick,
    version: cfg.version || false,
    auth: 'offline',
    hideErrors: true,
  })
  bot.loadPlugin(pathfinder)

  // Estado compartido: coordina las tres capas para que no se pisen.
  const st = {
    owner: cfg.dueno,          // FIJO: el dueño no cambia por hablar
    busy: false,               // hay una acción de movimiento en curso
    panic: false,              // huyendo de un creeper (máxima prioridad)
    reflexBusy: false,         // un reflejo está ejecutándose
    thinking: false,           // hay una llamada al modelo en curso
    defendSelf: cfg.defender,
    pausaAutonomo: cfg.pausa_autonomo,
    lastReflexChat: 0,
    lastArmorCheck: 0,
    nightShelterAt: 0,
  }
  // skills.follow guarda el nombre en bot._minaFollowing; lo reflejamos en st.following
  Object.defineProperty(st, 'following', {
    get () { return bot._minaFollowing || null },
    set (v) { bot._minaFollowing = v },
  })
  bot.lune = st

  const limitador = crearLimitador({ rafaga: 3, cada_ms: 1500, ahora })
  function decir (texto) {
    const t = limpiarChat(texto)
    if (!t || !limitador.permitir()) return false
    try { bot.chat(t); return true } catch { return false }
  }

  const charla = crearCharla({ decir, ahora, frases: cfg.persona.frases, estilo: cfg.estilo, nombre: cfg.persona.nombre, nick: cfg.nick })
  const cerebro = crearCerebro({ persona: cfg.persona, estilo: cfg.estilo, dueno: cfg.dueno, llm: cfg.llm, ahora, avisoCaida: charla.line('sinModelo') })
  cerebro.pausado = cfg.pausa_llm
  const acciones = crearAcciones({ skills, decir, dueno: cfg.dueno, soloDueno: cfg.solo_dueno })
  const comandos = crearComandos({ skills, charla, decir, dueno: cfg.dueno, soloDueno: cfg.solo_dueno, nombres: [cfg.nick, cfg.persona.nombre], ahora })
  const observador = crearObservador({ bot, dueno: cfg.dueno, emitir: canal.emitir, ahora })

  let dentro = false
  let desconectado = false
  let pedido = false            // Lune pidió salir: no es un error
  let tAutonomo = null
  let tEstado = null

  function estado () {
    const e = { dentro, pausa_autonomo: !!st.pausaAutonomo, pausa_llm: !!cerebro.pausado }
    try {
      if (bot.entity) {
        const p = bot.entity.position
        e.vida = Math.round(bot.health ?? 0)
        e.hambre = Math.round(bot.food ?? 0)
        e.pos = { x: Math.floor(p.x), y: Math.floor(p.y), z: Math.floor(p.z) }
        e.dia = !(bot.time && bot.time.timeOfDay >= 13000)
        e.lluvia = !!bot.isRaining
        e.siguiendo = nickSeguro(st.following || '')
        e.ocupado = !!(st.busy || st.reflexBusy || st.thinking)
        try {
          const b = bot.blockAt(p)
          const bioma = b && b.biome && b.biome.name
          if (bioma) e.bioma = String(bioma).replace(/[^a-z0-9_]/gi, '').slice(0, 40)
        } catch {}
      }
    } catch {}
    return e
  }

  let ultimoEstado = -Infinity
  function emitirEstado () {
    ultimoEstado = ahora()
    canal.emitir('estado', estado())
  }

  let ultimoError = ''
  let ultimoErrorT = -Infinity

  function desconexion (motivo) {
    if (desconectado) return
    desconectado = true
    dentro = false
    const m = String(motivo || '')
    if (pedido) {
      canal.emitir('desconectado', { motivo: 'Lune me desconectó.', pedido: true })
      return
    }
    // «socketClosed»/«Desconectado.» tras un error de red: el error explicado dice más.
    const generico = !m || /^(socketClosed|Desconectado\.?)$/i.test(m)
    canal.emitir('desconectado', { motivo: generico && ultimoError ? ultimoError : explicar(m, cfg) })
  }

  // ── Ciclo de vida ────────────────────────────────────────────────────────────
  // `spawn` se dispara también en cada respawn: los timers se arrancan UNA vez.
  bot.on('spawn', () => {
    skills.equipArmor(bot).catch(() => {})
    if (dentro) {
      decir(charla.line('respawn'))
      return
    }
    dentro = true
    console.log(`conectada como ${bot.username} (Minecraft ${bot.version})`)
    canal.emitir('conectado', { nick: nickSeguro(bot.username), version: String(bot.version || '').slice(0, 16) })
    decir(charla.line('saludo'))
    startReflexes(bot, { skills, decir, ahora })
    charla.start(bot)
    observador.start()
    iniciarAutonomo()
    tEstado = setInterval(emitirEstado, ESTADO_CADA_MS)
    setImmediate(emitirEstado)      // mineflayer pone la vida justo DESPUÉS de emitir 'spawn'
  })

  // Vida y hambre al cambiar (como mucho una vez por segundo), además de cada 5 s.
  bot.on('health', () => { if (dentro && ahora() - ultimoEstado >= 1000) emitirEstado() })

  bot.on('death', () => {
    decir(charla.line('death'))
    skills.stopAll(bot)
    st.busy = false
  })

  bot.on('kicked', (reason) => desconexion(textoMotivo(reason)))
  bot.on('error', (err) => {
    const m = explicar(String((err && (err.code || err.message)) || err), cfg)
    const t = ahora()
    if (m === ultimoError && t - ultimoErrorT < 5000) return      // el mismo error dos veces seguidas
    ultimoError = m
    ultimoErrorT = t
    canal.emitir('error', { mensaje: m })
  })
  bot.on('end', (reason) => {
    clearInterval(tAutonomo)
    clearInterval(tEstado)
    observador.stop()
    desconexion(textoMotivo(reason) || 'Desconectado.')
    setTimeout(() => salir(0), 200)
  })

  // ── Chat del juego: órdenes primero, modelo después ──────────────────────────
  bot.on('chat', async (username, message) => {
    if (username === bot.username) return
    const de = nickSeguro(username)
    const texto = limpiarChat(message)
    if (!de || !texto) return
    canal.emitir('chat', { de, texto })        // texto de terceros: Lune solo lo pinta
    try {
      const cmd = await comandos.handleCommand(bot, de, texto)       // ya sin «§», controles ni saltos
      if (cmd && cmd.handled) {
        if (cmd.reply) decir(cmd.reply)
        return
      }
      const esDueno = comandos.esDueno(de)
      if (cfg.solo_dueno && !esDueno) return        // los demás no llegan al modelo
      const mencion = comandos.mencionado(texto) || (esDueno && /\?\s*$/.test(texto))
      if (!mencion || st.thinking || cerebro.pausado) return
      st.thinking = true
      try {
        const decision = await cerebro.think(getWorldContext(bot), texto, de)
        await acciones.executeDecision(bot, decision)
      } finally {
        st.thinking = false
      }
    } catch (err) {
      console.error('error al responder:', err && err.message)   // sin frases de error en bucle
    }
  })

  // ── Bucle autónomo (decisiones del modelo cuando no hay nada urgente) ─────────
  function iniciarAutonomo () {
    tAutonomo = setInterval(async () => {
      if (st.pausaAutonomo || cerebro.pausado || st.panic || st.reflexBusy || st.busy || st.following || st.thinking) return
      st.thinking = true
      try {
        const decision = await cerebro.think(getWorldContext(bot))
        await acciones.executeDecision(bot, decision)
      } catch (err) {
        console.error('error en el bucle autónomo:', err && err.message)
      } finally {
        st.thinking = false
      }
    }, cfg.pensar_cada_s * 1000)
  }

  // ── Lo que manda Lune ─────────────────────────────────────────────────────────
  async function atender (m) {
    switch (m.tipo) {
      case 'orden': {
        const id = typeof m.id === 'string' && ID_ORDEN.test(m.id) ? m.id : null
        const texto = typeof m.texto === 'string' ? m.texto.slice(0, MAX_ORDEN) : ''
        if (!id || !texto.trim()) return
        if (!dentro) {
          canal.emitir('respuesta', { id, texto: 'Todavía no estoy dentro del mundo.' })
          return
        }
        let r = null
        try {
          r = await comandos.handleCommand(bot, cfg.dueno, texto, { origen: 'lune' })
        } catch (err) {
          canal.emitir('respuesta', { id, texto: `No pude: ${limpiarChat(err && err.message, 120)}` })
          return
        }
        if (!r) {
          canal.emitir('respuesta', { id, texto: charla.line('noEntiendo') || 'Eso no sé hacerlo.' })
          return
        }
        if (r.reply) decir(r.reply)
        canal.emitir('respuesta', { id, texto: r.reply || (r.dicho === false ? 'No pude decirlo (demasiado seguido).' : 'Hecho.') })
        return
      }
      case 'decir':
        if (typeof m.texto === 'string' && dentro) decir(m.texto)
        return
      case 'pausa_llm':
        cerebro.pausado = !!m.on
        return
      case 'pausa_autonomo':
        st.pausaAutonomo = !!m.on
        return
      case 'estado':
        emitirEstado()
        return
      default:
    }
  }

  function cerrar () {
    pedido = true
    clearInterval(tAutonomo)
    clearInterval(tEstado)
    try { observador.stop() } catch {}
    try { bot.quit('Lune me desconectó') } catch {}
  }

  return { atender, cerrar, bot, estado }
}

/**
 * main({argv, env, stdin, escribir, exit, requerir, ahora, setTimeout})
 * Todo inyectable: los tests lo arrancan con un stdin de mentira.
 */
function main ({ argv = process.argv.slice(2), env = process.env, stdin = process.stdin,
  escribir = null, exit = null, requerir = require, ahora = () => Date.now(),
  setTimeout: st = setTimeout, clearTimeout: ct = clearTimeout, esperaConfigMs = ESPERA_CONFIG_MS } = {}) {
  const esc = escribir || ((l) => process.stdout.write(l + '\n'))
  const salir = exit || ((codigo) => {
    // Vaciar stdout antes de salir (en Windows la tubería puede ir con retraso).
    const t = setTimeout(() => process.exit(codigo), 1500)
    process.stdout.write('', () => { clearTimeout(t); process.exit(codigo) })
  })
  const probar = argv.includes('--probar')
  const token = String(env.LUNE_MC_TOKEN || '')
  if (!/^[0-9a-f]{16,64}$/.test(token)) {
    console.error('Falta LUNE_MC_TOKEN: a este bot lo lanza Lune (Ajustes → Minecraft).')
    salir(2)
    return null
  }
  try { delete env.LUNE_MC_TOKEN } catch {}

  let control = null
  let configurado = false
  let saliendo = false

  function terminar (codigo) {
    if (saliendo) return
    saliendo = true
    ct(tConfig)
    if (control) {
      try { control.cerrar() } catch {}
      st(() => salir(codigo), 300)
    } else {
      salir(codigo)
    }
  }

  function alRecibir (m) {
    if (!configurado) {
      if (m.tipo === 'salir') { terminar(0); return }
      if (m.tipo !== 'config') return
      configurado = true
      ct(tConfig)
      const v = validarConfig(m)
      if (!v.ok) {
        canal.emitir('error', { mensaje: v.error, fatal: true })
        terminar(1)
        return
      }
      if (probar) {
        try {
          for (const dep of ['mineflayer', 'mineflayer-pathfinder', 'minecraft-data', 'vec3']) requerir(dep)
        } catch (err) {
          canal.emitir('error', { mensaje: 'Faltan las dependencias del bot: instálalo en Ajustes → Minecraft.', fatal: true })
          console.error('no cargan las dependencias:', err && (err.code || err.message))
          terminar(1)
          return
        }
        canal.emitir('listo', { probar: true, node: process.version })
        terminar(0)
        return
      }
      try {
        control = crearBot(v.config, canal, { requerir, ahora, salir: terminar })
      } catch (err) {
        const falta = err && err.code === 'MODULE_NOT_FOUND'
        canal.emitir('error', {
          mensaje: falta ? 'Faltan las dependencias del bot: instálalo en Ajustes → Minecraft.' : `No pude arrancar el bot: ${limpiarChat(err && err.message, 160)}`,
          fatal: true,
        })
        terminar(1)
        return
      }
      canal.emitir('listo', { nick: v.config.nick })
      return
    }
    if (m.tipo === 'salir') { terminar(0); return }
    if (control) Promise.resolve(control.atender(m)).catch((e) => console.error('orden de Lune:', e && e.message))
  }

  const canal = crearCanal({ token, escribir: esc, entrada: stdin, salir: terminar, ahora, alRecibir })
  const tConfig = st(() => {
    if (!configurado) {
      canal.emitir('error', { mensaje: 'No llegó la configuración de Lune.', fatal: true })
      terminar(1)
    }
  }, esperaConfigMs)
  canal.escuchar()
  return { canal, get control () { return control }, terminar }
}

module.exports = { main, crearBot, instalarConsola, textoMotivo, explicar, ESPERA_CONFIG_MS }

if (require.main === module) {
  instalarConsola()
  main()
}
