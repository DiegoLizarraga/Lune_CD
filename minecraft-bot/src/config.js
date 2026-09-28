// ── config.js ────────────────────────────────────────────────────────────────────
// La configuración del bot llega de Lune en la PRIMERA línea de stdin
// ({"tipo":"config", …}; ver canal.js). Aquí se valida entera: nada de .env ni
// de dotenv. Si algo no cuadra, el bot no se conecta y dice por qué.
//
// validarConfig(obj) → {ok: true, config} | {ok: false, error: 'texto'}
//
// Solo servidores sin autenticación (online-mode=false): el bot entra con
// auth 'offline' y el nick que se le da. No hay cuentas de Microsoft.
//
// Puro: sin dependencias ni efectos.
'use strict'

const NICK = /^[A-Za-z0-9_]{3,16}$/
const VERSION = /^\d+\.\d+(\.\d+)?$/
const ETIQUETA_HOST = /^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/
const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/
const IPV6 = /^[0-9A-Fa-f:]{2,39}$/
const PROVEEDORES = new Set(['ollama', 'openrouter', 'compat'])
const ESTILOS = new Set(['personaje', 'sobrio'])
const MAX_PERSONA = 2000          // unidades UTF-16 (.length): un emoji cuenta 2

function hostValido (h) {
  const s = String(h ?? '').trim()
  if (!s || s.length > 253) return ''
  if (IPV4.test(s)) return s
  if (s.includes(':')) return (IPV6.test(s) && (s.match(/:/g) || []).length >= 2) ? s : ''
  const etiquetas = s.split('.')
  if (etiquetas.some((e) => !ETIQUETA_HOST.test(e))) return ''
  return s
}

function entero (v, min, max) {
  if (typeof v === 'boolean' || v === null || v === undefined || v === '') return null
  const n = Number(v)
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < min || n > max) return null
  return n
}

function urlHttp (u) {
  const s = String(u ?? '').trim()
  if (!s || s.length > 500) return ''
  try {
    const url = new URL(s)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
    if (url.username || url.password) return ''
    return s.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

/** ≤ `tope` unidades UTF-16 (lo que mide .length; Lune recorta igual: largo_utf16 de
 *  minecraft_proceso.py) sin dejar medio emoji al final. */
function texto (v, tope) {
  if (typeof v !== 'string') return ''
  let s = v.slice(0, tope)
  if (s.length && /[\ud800-\udbff]$/.test(s)) s = s.slice(0, -1)
  return s
}

/** Valida la configuración del LLM propio del bot. → {ok, llm} | {ok:false, error} */
function validarLLM (llm) {
  if (llm === undefined || llm === null) return { ok: true, llm: null }   // sin cerebro: solo órdenes y reflejos
  if (typeof llm !== 'object' || Array.isArray(llm)) return { ok: false, error: 'llm tiene que ser un objeto' }
  const proveedor = String(llm.proveedor || '').toLowerCase()
  if (!PROVEEDORES.has(proveedor)) return { ok: false, error: `proveedor de LLM desconocido: «${texto(proveedor, 20)}»` }
  const url = urlHttp(llm.url)
  if (!url) return { ok: false, error: 'la URL del modelo no es http(s) válida' }
  const modelo = texto(llm.modelo, 200).trim()
  const clave = texto(llm.clave, 500).trim()
  if (proveedor === 'openrouter' && modelo && !clave) return { ok: false, error: 'falta la clave de OpenRouter' }
  const numCtx = llm.num_ctx === undefined ? 8192 : entero(llm.num_ctx, 512, 262144)
  if (numCtx === null) return { ok: false, error: 'num_ctx fuera de rango (512–262144)' }
  const timeoutMs = llm.timeout_ms === undefined ? 20000 : entero(llm.timeout_ms, 1000, 300000)
  if (timeoutMs === null) return { ok: false, error: 'timeout_ms fuera de rango (1000–300000)' }
  const keepAlive = texto(llm.keep_alive ?? '30m', 20).trim()
  if (keepAlive && !/^-?\d+(\.\d+)?[smh]?$/.test(keepAlive)) return { ok: false, error: 'keep_alive raro' }
  return { ok: true, llm: { proveedor, url, modelo, clave, keep_alive: keepAlive || '30m', num_ctx: numCtx, timeout_ms: timeoutMs } }
}

/**
 * validarConfig(obj) → {ok: true, config} | {ok: false, error}
 * config = {host, port, version, nick, dueno, solo_dueno, defender, pensar_cada_s, estilo,
 *           persona: {nombre, prompt, frases}, llm: {...}|null, pausa_autonomo, pausa_llm}
 */
function validarConfig (obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return { ok: false, error: 'la configuración no es un objeto' }
  const host = hostValido(obj.host)
  if (!host) return { ok: false, error: 'el servidor (host) no es un nombre ni una IP válidos' }
  const port = entero(obj.port, 1, 65535)
  if (port === null) return { ok: false, error: 'el puerto tiene que estar entre 1 y 65535' }
  const version = String(obj.version ?? '').trim()
  if (version && !VERSION.test(version)) return { ok: false, error: 'la versión tiene que ser como 1.21.1 (o vacía: autodetectar)' }
  const nick = String(obj.nick ?? '').trim()
  if (!NICK.test(nick)) return { ok: false, error: 'el nick del bot tiene que tener 3–16 letras, números o _' }
  const dueno = String(obj.dueno ?? '').trim()
  if (!NICK.test(dueno)) return { ok: false, error: 'falta tu nick de Minecraft (dueño): 3–16 letras, números o _' }
  if (dueno.toLowerCase() === nick.toLowerCase()) return { ok: false, error: 'el bot no puede llamarse como su dueño' }
  const pensar = obj.pensar_cada_s === undefined ? 45 : entero(obj.pensar_cada_s, 30, 3600)
  if (pensar === null) return { ok: false, error: 'pensar_cada_s tiene que estar entre 30 y 3600' }
  const estilo = String(obj.estilo ?? 'personaje').toLowerCase()
  if (!ESTILOS.has(estilo)) return { ok: false, error: 'estilo de frases desconocido (personaje o sobrio)' }

  const p = obj.persona && typeof obj.persona === 'object' ? obj.persona : {}
  const nombre = texto(p.nombre, 40).replace(/[\u0000-\u001f\u007f]/g, '').trim() || 'Lune'
  const prompt = typeof p.prompt === 'string' ? p.prompt : ''       // la línea entera ya va con tope (canal.js)
  if (prompt.length > MAX_PERSONA) return { ok: false, error: `la persona pasa de ${MAX_PERSONA} caracteres` }
  const frases = {}
  if (p.frases && typeof p.frases === 'object' && !Array.isArray(p.frases)) {
    for (const [cat, lista] of Object.entries(p.frases).slice(0, 40)) {
      if (!/^[A-Za-z_]{1,24}$/.test(cat) || !Array.isArray(lista)) continue
      const ok = lista.filter((f) => typeof f === 'string' && f.trim()).slice(0, 12).map((f) => texto(f, 120))
      if (ok.length) frases[cat] = ok
    }
  }

  const llm = validarLLM(obj.llm)
  if (!llm.ok) return { ok: false, error: llm.error }

  return {
    ok: true,
    config: {
      host,
      port,
      version,
      nick,
      dueno,
      solo_dueno: obj.solo_dueno !== false,
      defender: obj.defender !== false,
      pensar_cada_s: pensar,
      estilo,
      persona: { nombre, prompt, frases },
      llm: llm.llm,
      pausa_autonomo: obj.pausa_autonomo === true,
      pausa_llm: obj.pausa_llm === true,
    },
  }
}

module.exports = { validarConfig, validarLLM, hostValido, NICK, VERSION, MAX_PERSONA }
