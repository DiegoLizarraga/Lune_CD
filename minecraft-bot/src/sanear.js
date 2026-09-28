// ── sanear.js ────────────────────────────────────────────────────────────────────
// Todo lo que el bot escribe en el chat del juego y todo lo que llega del juego
// (chat de jugadores, nombres, motivos de expulsión) es texto que no controla
// Lune. Aquí se limpia antes de usarlo:
//
//   · limpiarChat(t): lo que el bot DICE. Sin códigos de color «§x», sin controles
//     ni saltos de línea, sin marcadores <|…|>, con TODOS los espacios Unicode (también
//     U+180E, U+2800, rellenos Hangul) hechos un espacio y SIN «/» al principio: el bot
//     nunca ejecuta comandos del servidor (/op, /give…), lo pida el modelo o un
//     jugador. ≤256 caracteres (el tope del chat de Minecraft).
//   · limpiarEntrada(t, tope): lo que llega del juego y puede acabar en el prompt
//     del modelo del bot (chat de terceros): lo anterior + marcadores de rol y
//     plantillas neutralizados; ≤200.
//   · nickSeguro(n): un nick de Minecraft válido ([A-Za-z0-9_]{1,16}) o ''.
//   · crearLimitador({rafaga, cada_ms, ahora}): cubo de fichas para no hacer spam
//     (un servidor expulsa por spam).
//
// Puro: sin dependencias ni efectos.
'use strict'

const MAX_CHAT = 256
const MAX_ENTRADA = 200
const NICK = /^[A-Za-z0-9_]{1,16}$/

// Controles C0/C1, bidi (pueden dar la vuelta al texto), anchos cero, marcas invisibles
// (U+00AD, U+034F, U+061C, U+180B-180D, U+206A-206F, U+FFF9-FFFB) y etiquetas (U+E0000-E007F).
const CONTROLES = /[\u0000-\u001f\u007f-\u009f\u00ad\u034f\u061c\u180b-\u180d\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb]|\udb40[\udc00-\udc7f]/g
// TODA la clase de espacios, también los que \s de JS no cubre pero un servidor puede
// recortar (Java 8: Character.isWhitespace(U+180E) es true y StringUtils.normalizeSpace quita
// los del principio) o que se ven en blanco: U+180E, U+2800 (braille vacío), los rellenos
// Hangul (U+115F, U+1160, U+3164, U+FFA0) y U+17B4/17B5. \s ya cubre U+00A0, U+1680,
// U+2000-200A, U+2028/2029, U+202F, U+205F, U+3000 y U+FEFF. Todos → un espacio ANTES de
// quitar la «/» del principio: «\u180E/op x» no llega nunca como comando.
const ESPACIOS = /[\s\u180e\u2800\u115f\u1160\u3164\uffa0\u17b4\u17b5]+/g
const COLORES = /§./g                     // §a, §l… (formato de Minecraft)
const MARCADORES = /<\|[^|>]{0,80}\|>/g         // <|ACT happy|>, <|CALL …|>

function _texto (t) {
  return typeof t === 'string' ? t : (t == null ? '' : String(t))
}

/** Lo que el bot va a decir en el chat del juego (ver cabecera). */
function limpiarChat (t, tope = MAX_CHAT) {
  let s = _texto(t)
    .replace(COLORES, '')
    .replace(/§/g, '')
    .replace(/[\r\n\t]+/g, ' ')
    .replace(CONTROLES, '')
    .replace(MARCADORES, '')
  s = s.replace(ESPACIOS, ' ').trim()
  s = s.replace(/^[ /\\]+/, '')                 // nunca un comando del servidor
  if (s.length > tope) s = s.slice(0, Math.max(0, tope - 1)).trimEnd() + '…'
  return s
}

/**
 * Texto de TERCEROS (chat del juego) camino del modelo: se limpia como el chat y
 * se rompen los marcadores de rol y de plantilla con los que un jugador podría
 * intentar colar instrucciones («system:», «<|im_start|>», «[INST]», «```»).
 */
function limpiarEntrada (t, tope = MAX_ENTRADA) {
  let s = limpiarChat(t, tope + 50)
  s = s
    .replace(/<\|/g, '< |')
    .replace(/\|>/g, '| >')
    .replace(/\[\/?(INST|SYS)\]/gi, '($1)')
    .replace(/```/g, "'''")
    .replace(/\b(system|assistant|developer)\s*:/gi, '$1 -')
    .replace(/["{}]/g, (c) => (c === '"' ? "'" : c === '{' ? '(' : ')'))
  s = s.replace(/\s+/g, ' ').trim()
  if (s.length > tope) s = s.slice(0, Math.max(0, tope - 1)).trimEnd() + '…'
  return s
}

/** Un nick de Minecraft válido o ''. */
function nickSeguro (n) {
  if (typeof n !== 'string') return ''
  const s = n.trim()
  return NICK.test(s) ? s : ''
}

/** Un nombre de bloque/objeto/mob de minecraft-data ([a-z0-9_], ≤48) o ''. */
function idSeguro (n) {
  const s = _texto(n).trim().toLowerCase()
  return /^[a-z0-9_]{1,48}$/.test(s) ? s : ''
}

/**
 * Cubo de fichas: `rafaga` mensajes seguidos como mucho y luego uno cada `cada_ms`.
 * permitir() → true si se puede decir algo ahora (y gasta una ficha).
 */
function crearLimitador ({ rafaga = 3, cada_ms: cadaMs = 1500, ahora = () => Date.now() } = {}) {
  const max = Math.max(1, Math.floor(rafaga))
  const cada = Math.max(1, Number(cadaMs) || 1500)
  let fichas = max
  let ultimo = ahora()

  function rellenar () {
    const t = ahora()
    const ganadas = (t - ultimo) / cada
    if (ganadas > 0) {
      fichas = Math.min(max, fichas + ganadas)
      ultimo = t
    }
  }

  return {
    permitir () {
      rellenar()
      if (fichas >= 1) {
        fichas -= 1
        return true
      }
      return false
    },
    get fichas () { rellenar(); return fichas },
  }
}

module.exports = { limpiarChat, limpiarEntrada, nickSeguro, idSeguro, crearLimitador, MAX_CHAT, MAX_ENTRADA }
