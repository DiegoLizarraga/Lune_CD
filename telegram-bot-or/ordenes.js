// ordenes.js — Órdenes desde Telegram hacia Lune (la app de escritorio).
//
// El bot lo lanza Lune (servicios/telegram_worker.py) y el canal es su propio
// stdin/stdout, sin red:
//   · Pedir una orden: una línea en stdout
//       @@LUNE_ORDEN <token> {"id": "...", "texto": "...", "chat_id": ...}
//     El token llega en la variable de entorno LUNE_ORDENES_TOKEN SOLO si en
//     Lune está activado «Órdenes desde Telegram» y hay apis.telegram_admin_id.
//   · Respuestas: Lune escribe en stdin líneas JSON
//       {"tipo": "orden:mensaje", "id": "...", "texto": "..."}
//     y se mandan al chat de esa orden (mapa id → chat con caducidad). Un id
//     desconocido o caducado se ignora.
// La aprobación de lo que se ejecute es SIEMPRE en el PC, nunca desde aquí.
//
// Sin efectos al importarse: bot.js crea el canal y llama a escuchar().
import { createInterface } from "node:readline";
import { randomBytes } from "node:crypto";

export const MARCA = "@@LUNE_ORDEN";
export const TIPO_MENSAJE = "orden:mensaje";
export const CADUCIDAD_MS = 5 * 60 * 1000;   // sin noticias de Lune en 5 min: se olvida
export const MAX_ORDEN = 1000;               // caracteres de la orden que se mandan
export const MAX_MENSAJE = 4000;             // Telegram admite 4096 por mensaje
// Al cerrarse stdin (Lune paró el bot, p. ej. al cambiar de interfaz), lo que se
// esté mandando a Telegram (p. ej. «Se detuvo…») termina antes de salir, con tope:
// Lune espera 3 s a que el proceso acabe.
export const ESPERA_SALIDA_MS = 2500;
const ID_VALIDO = /^[A-Za-z0-9_-]{1,40}$/;

/** JSON solo en ASCII (\uXXXX): la línea no depende de la página de códigos. */
export function jsonAscii(valor) {
  return JSON.stringify(valor).replace(/[\u007f-￿]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

/** La línea que pide una orden a Lune. */
export function lineaOrden(token, orden) {
  return `${MARCA} ${token} ${jsonAscii(orden)}`;
}

export class CanalOrdenes {
  /**
   * token        LUNE_ORDENES_TOKEN ("" = función apagada: pedirOrden devuelve null).
   * responder    async (chatId, texto) => …  manda un mensaje a Telegram.
   * escribir     (linea) => …  por defecto, process.stdout.
   * ahora        reloj en ms (inyectable en tests).
   * caducidadMs  cuánto se recuerda una orden desde su último mensaje.
   * nuevoId      () => id (inyectable en tests).
   */
  constructor({ token = "", responder = async () => {}, escribir = null, ahora = () => Date.now(),
                caducidadMs = CADUCIDAD_MS, nuevoId = null } = {}) {
    this.token = String(token || "");
    this.responder = responder;
    this.escribir = escribir || ((linea) => process.stdout.write(linea + "\n"));
    this.ahora = ahora;
    this.caducidadMs = caducidadMs;
    this.nuevoId = nuevoId || (() => randomBytes(6).toString("hex"));
    this.pendientes = new Map();             // id → { chatId, visto }
    this.enVuelo = new Set();                // respuestas que se están mandando a Telegram
  }

  /** Espera (como mucho `topeMs`) a que terminen las respuestas en vuelo. */
  terminarEnvios(topeMs = ESPERA_SALIDA_MS) {
    if (this.enVuelo.size === 0) return Promise.resolve();
    let t;
    const tope = new Promise((r) => { t = setTimeout(r, Math.max(0, topeMs)); });
    return Promise.race([Promise.allSettled([...this.enVuelo]), tope]).finally(() => clearTimeout(t));
  }

  /** ¿Lune abrió el canal (función activada e iniciado desde Lune)? */
  activo() {
    return this.token.length > 0;
  }

  /** Quita las órdenes que llevan `caducidadMs` sin noticias. */
  limpiar() {
    const t = this.ahora();
    for (const [id, p] of this.pendientes) {
      if (t - p.visto >= this.caducidadMs) this.pendientes.delete(id);
    }
  }

  /** Manda la orden a Lune y devuelve su id (null si el canal está cerrado o no hay texto). */
  pedirOrden(texto, chatId) {
    if (!this.activo()) return null;
    const limpio = String(texto ?? "").trim().slice(0, MAX_ORDEN);
    if (!limpio || chatId === undefined || chatId === null) return null;
    this.limpiar();
    const id = String(this.nuevoId());
    this.pendientes.set(id, { chatId, visto: this.ahora() });
    this.escribir(lineaOrden(this.token, { id, texto: limpio, chat_id: chatId }));
    return id;
  }

  /**
   * Una línea que llegó por stdin. true si era un orden:mensaje de una orden
   * conocida (y se mandó a su chat); false si se ignoró.
   */
  recibirLinea(linea) {
    let m;
    try { m = JSON.parse(String(linea ?? "")); } catch { return false; }
    if (!m || typeof m !== "object" || m.tipo !== TIPO_MENSAJE) return false;
    if (typeof m.id !== "string" || !ID_VALIDO.test(m.id) || typeof m.texto !== "string") return false;
    this.limpiar();
    const p = this.pendientes.get(m.id);
    if (!p) return false;                    // desconocida o caducada
    const texto = m.texto.trim();
    if (!texto) return false;
    p.visto = this.ahora();                  // cada mensaje renueva la caducidad
    const corto = texto.length > MAX_MENSAJE ? texto.slice(0, MAX_MENSAJE - 1) + "…" : texto;
    const envio = Promise.resolve()
      .then(() => this.responder(p.chatId, corto))
      .catch((e) => console.error("Órdenes: no pude responder en Telegram:", e?.message ?? e));
    this.enVuelo.add(envio);
    envio.finally(() => this.enVuelo.delete(envio));
    return true;
  }

  /**
   * Lee stdin línea a línea. Si `salirAlCerrar` (el bot lo lanzó Lune), al
   * cerrarse stdin (Lune paró el bot o se cerró) el proceso termina: así no se
   * queda un bot huérfano con el token. Antes termina de mandar lo que estaba en
   * vuelo (como mucho ESPERA_SALIDA_MS). `salir` es inyectable en tests.
   */
  escuchar({ entrada = process.stdin, salirAlCerrar = false, alCerrar = null,
             salir = (codigo) => process.exit(codigo) } = {}) {
    const rl = createInterface({ input: entrada, crlfDelay: Infinity });
    rl.on("line", (l) => { this.recibirLinea(l); });
    rl.on("close", () => {
      if (typeof alCerrar === "function") alCerrar();
      if (salirAlCerrar) {
        this.terminarEnvios().then(() => {
          console.log("Lune cerró el canal: bot detenido.");
          salir(0);
        });
      }
    });
    return rl;
  }
}
