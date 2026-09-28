// ── canal.js ─────────────────────────────────────────────────────────────────────
// El canal entre Lune (lune_core/minecraft_proceso.py) y este bot: su propio
// stdin/stdout, sin red ni puertos.
//
//   · Bot → Lune: una línea en stdout que EMPIEZA por
//         @@LUNE <token> <json en ASCII>
//     El token llega en LUNE_MC_TOKEN (uno nuevo en cada lanzamiento). Lune solo
//     acepta la marca al principio de la línea, así que un jugador que escriba
//     «@@LUNE …» en el chat del juego no puede colarla (y no sabe el token).
//     El JSON va en ASCII (\uXXXX): no depende de la página de códigos.
//   · Lune → bot: líneas JSON en stdin. La primera es {"tipo":"config", …}; luego
//     orden, decir, pausa_llm, pausa_autonomo, estado y salir.
//   · Al cerrarse stdin (Lune paró el bot o se cerró), el bot sale: nunca queda
//     un node huérfano.
//
// Puro: sin efectos al importarse. bot.js crea el canal y llama a escuchar().
'use strict'

const MARCA = '@@LUNE'
const MAX_LINEA = 8192          // bot → Lune (Lune ignora lo que pase de aquí)
const MAX_ENTRADA = 32768       // Lune → bot (la configuración lleva la persona en ASCII escapado)
const TIPOS_ENTRADA = new Set(['config', 'orden', 'decir', 'pausa_llm', 'pausa_autonomo', 'estado', 'salir'])
const TIPOS_SALIDA = new Set(['listo', 'conectado', 'desconectado', 'estado', 'evento', 'chat', 'respuesta', 'error'])

/** JSON solo en ASCII (\uXXXX): la línea no depende de la página de códigos. */
function jsonAscii (valor) {
  return JSON.stringify(valor).replace(/[\u007f-\uffff]/g,
    (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'))
}

/**
 * crearCanal({token, escribir, entrada, salir, ahora, alRecibir})
 *   token      LUNE_MC_TOKEN (obligatorio: sin token no se emite nada).
 *   escribir   (linea) => …   por defecto process.stdout.
 *   entrada    stream de entrada (por defecto process.stdin).
 *   salir      (codigo) => …  al cerrarse la entrada (por defecto process.exit).
 *   ahora      reloj en ms (inyectable).
 *   alRecibir  (mensaje) => …  cada mensaje válido de Lune.
 */
function crearCanal ({ token = '', escribir = null, entrada = null, salir = null, ahora = () => Date.now(),
  alRecibir = null } = {}) {
  const tok = String(token || '')
  const esc = escribir || ((linea) => process.stdout.write(linea + '\n'))
  const fin = salir || ((codigo) => process.exit(codigo))
  let cerrado = false
  let emitidas = 0

  /** Escribe un mensaje para Lune. false si no se pudo (sin token, tipo raro o demasiado largo). */
  function emitir (tipo, datos = {}) {
    if (!tok || cerrado || !TIPOS_SALIDA.has(tipo)) return false
    const cuerpo = Object.assign({}, datos && typeof datos === 'object' ? datos : {}, { tipo, t: ahora() })
    let linea = `${MARCA} ${tok} ${jsonAscii(cuerpo)}`
    if (linea.length > MAX_LINEA) {
      // Algo se fue de tamaño (un motivo de expulsión enorme…): se avisa corto.
      if (tipo === 'error') return false
      linea = `${MARCA} ${tok} ${jsonAscii({ tipo: 'error', mensaje: `mensaje «${tipo}» demasiado largo`, t: ahora() })}`
    }
    try {
      esc(linea)
      emitidas++
      return true
    } catch {
      return false
    }
  }

  /** Una línea de stdin → el mensaje validado ({tipo, …}) o null. */
  function recibir (linea) {
    const texto = String(linea ?? '')
    if (!texto || texto.length > MAX_ENTRADA) return null
    let m
    try { m = JSON.parse(texto) } catch { return null }
    if (!m || typeof m !== 'object' || Array.isArray(m)) return null
    if (typeof m.tipo !== 'string' || !TIPOS_ENTRADA.has(m.tipo)) return null
    return m
  }

  /** Lee la entrada línea a línea; al cerrarse, salir(0). Devuelve el readline. */
  function escuchar () {
    const { createInterface } = require('node:readline')
    const rl = createInterface({ input: entrada || process.stdin, crlfDelay: Infinity })
    rl.on('line', (l) => {
      const m = recibir(l)
      if (m && typeof alRecibir === 'function') {
        try { alRecibir(m) } catch (e) { console.error('canal: error atendiendo a Lune:', e && e.message) }
      }
    })
    rl.on('close', () => {
      cerrado = true
      fin(0)
    })
    return rl
  }

  return {
    emitir,
    recibir,
    escuchar,
    get cerrado () { return cerrado },
    get emitidas () { return emitidas },
  }
}

module.exports = { crearCanal, jsonAscii, MARCA, MAX_LINEA, MAX_ENTRADA, TIPOS_ENTRADA, TIPOS_SALIDA }
