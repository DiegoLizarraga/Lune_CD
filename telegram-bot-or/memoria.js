/**
 * memoria.js — La memoria del bot.
 *
 * Dos caminos:
 *  · Con hub (datos.json → hub.modo 'host' o 'terminal'): el usuario administrador
 *    lee y escribe LA MISMA memoria.json que la app, la del host, por eventos.
 *  · Sin hub: se comporta como antes (memoria.json de la raiz para el admin,
 *    archivos por usuario en data/ para los demas).
 *
 * Todas las funciones publicas son async: el llamante hace `await`.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { loadConfig } from "./config.js";
import { HubCliente } from "./hub.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MEMORIA_DIR = join(__dirname, "data");
const ROOT_MEM = join(__dirname, "..", "memoria.json");

let hub = null;          // HubCliente conectado, o null
let hubIntentado = false;

// ── Hub ───────────────────────────────────────────────────────────────────────

/** Conecta con el hub si esta configurado. Idempotente; no lanza. */
export async function iniciarHub() {
  if (hubIntentado) return hub?.listo ?? false;
  hubIntentado = true;
  const { hubUrl, hubToken } = loadConfig();
  if (!hubUrl) return false;
  const cliente = new HubCliente({ url: hubUrl, token: hubToken, nombre: "bot-telegram", kind: "bot", eventos: ["input:text"] });
  cliente.on("memory:changed", (ev) => console.log(`[hub] memoria cambiada (${ev.data?.motivo ?? "?"}) por ${ev.data?.por ?? "?"}`));
  // No bloqueamos el arranque del bot: reconecta solo en segundo plano.
  cliente.conectar().then(ok => {
    if (ok) { hub = cliente; console.log(`[hub] conectado a ${hubUrl} como bot-telegram`); }
    else console.log(`[hub] no pude conectar a ${hubUrl}${cliente.estado === "failed" ? " (token invalido)" : ""}; uso memoria local`);
  }).catch(() => {});
  // Damos un momento por si el host esta en la misma maquina y responde al instante
  await new Promise(r => setTimeout(r, 800));
  hub = cliente.listo ? cliente : hub;
  return !!hub;
}

export function estadoHub() {
  if (!hub) return "sin hub (memoria local)";
  return hub.listo ? `hub conectado (${hub.url})` : `hub ${hub.estado}`;
}

function hubListo() { return !!(hub && hub.listo); }

/** ¿Hay un host al que delegar el chat (agente)? */
export function hubDisponible() { return hubListo(); }

/**
 * El chat lo corre el HOST (mismo cerebro, memoria y herramientas). Devuelve el
 * texto final; onDelta recibe el streaming si se quiere. Lanza si no hay hub.
 */
export async function chatViaHost(text, { onDelta = null, imagenes = [], timeoutMs = 180000 } = {}) {
  if (!hubListo()) throw new Error("sin hub para el chat");
  return hub.pedirChat(text, { onDelta, imagenes, timeoutMs });
}

// ── Local (como antes) ────────────────────────────────────────────────────────

function memoriaPath(userId) { return join(MEMORIA_DIR, `memoria_${userId}.json`); }

function esAdmin(userId) {
  try { const { adminId } = loadConfig(); return adminId && String(userId) === String(adminId); }
  catch { return false; }
}

function estructuraVacia() {
  const ahora = new Date().toISOString();
  return { usuario: { nombre: null, preferencias: [], contexto: "" }, recuerdos: [], datos_clave: {},
           resumen_sesion_anterior: "", estadisticas: { total_mensajes: 0, primera_sesion: ahora, ultima_sesion: ahora } };
}
function loadRoot() { try { return JSON.parse(readFileSync(ROOT_MEM, "utf-8")); } catch { return null; } }
function saveRoot(data) { writeFileSync(ROOT_MEM, JSON.stringify(data, null, 2), "utf-8"); }
function rootToFlat(root) {
  const flat = {};
  if (root?.usuario?.nombre) flat.nombre = root.usuario.nombre;
  Object.assign(flat, root?.datos_clave || {});
  return flat;
}

// ── API publica ───────────────────────────────────────────────────────────────

/** Vista plana {nombre, ...datos_clave} del usuario. */
export async function loadMemoria(userId) {
  if (esAdmin(userId)) {
    if (hubListo()) {
      try {
        const r = await hub.pedir("memory:query", { que: "todo" });
        const t = r.data?.resultado;
        if (t) { const flat = { ...(t.datos_clave ?? {}) }; if (t.nombre) flat.nombre = t.nombre; return flat; }
      } catch (e) { console.error("[hub] loadMemoria:", e.message); }
    }
    const root = loadRoot();
    return root ? rootToFlat(root) : {};
  }
  try { return existsSync(memoriaPath(userId)) ? JSON.parse(readFileSync(memoriaPath(userId), "utf-8")) : {}; }
  catch { return {}; }
}

/**
 * Guarda pares clave/valor (los que el LLM extrae con [MEMORIA: {...}]).
 * Con `{}` se vacian los datos del bot (el /olvidar de siempre).
 */
export async function saveMemoria(userId, datos) {
  if (esAdmin(userId)) {
    const { nombre, ...resto } = datos || {};
    if (hubListo()) {
      try {
        const vaciar = Object.keys(datos || {}).length === 0;
        await hub.pedir("memory:set", { datos: { ...(nombre ? { nombre } : {}), ...resto }, reemplazar: vaciar });
        return;
      } catch (e) { console.error("[hub] saveMemoria:", e.message); }
    }
    const root = loadRoot() || estructuraVacia();
    if (!root.usuario) root.usuario = { nombre: null, preferencias: [], contexto: "" };
    if (nombre) root.usuario.nombre = nombre;
    root.datos_clave = resto;
    saveRoot(root);
    return;
  }
  if (!existsSync(MEMORIA_DIR)) mkdirSync(MEMORIA_DIR, { recursive: true });
  writeFileSync(memoriaPath(userId), JSON.stringify(datos, null, 2), "utf-8");
}

/** Bloque de texto para el system prompt. */
export async function buildMemoryPrompt(userId) {
  if (esAdmin(userId)) {
    if (hubListo()) {
      try {
        const r = await hub.pedir("memory:query", { que: "contexto" });
        const ctx = r.data?.resultado;
        if (typeof ctx === "string") return ctx;      // ya viene con sus delimitadores (o vacio)
      } catch (e) { console.error("[hub] buildMemoryPrompt:", e.message); }
    }
    const root = loadRoot();
    if (!root) return "";
    const lineas = [];
    if (root.usuario?.nombre) lineas.push(`- nombre: ${root.usuario.nombre}`);
    for (const [k, v] of Object.entries(root.datos_clave || {})) lineas.push(`- ${k}: ${v}`);
    for (const r of root.recuerdos || []) if (r?.contenido) lineas.push(`- ${r.contenido}`);
    if (root.resumen_sesion_anterior) lineas.push(`- (sesion anterior) ${root.resumen_sesion_anterior}`);
    return lineas.length ? `\n\n[Lo que recuerdas de este usuario]:\n${lineas.join("\n")}` : "";
  }
  const mem = await loadMemoria(userId);
  if (!mem || Object.keys(mem).length === 0) return "";
  return `\n\n[Lo que recuerdas de este usuario]:\n${Object.entries(mem).map(([k, v]) => `- ${k}: ${v}`).join("\n")}`;
}
