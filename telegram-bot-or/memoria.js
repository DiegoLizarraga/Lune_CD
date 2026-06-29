import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { loadConfig } from "./config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MEMORIA_DIR = join(__dirname, "data");

// memoria.json compartida con la app de escritorio (raíz del proyecto)
const ROOT_MEM = join(__dirname, "..", "memoria.json");

function memoriaPath(userId) {
  return join(MEMORIA_DIR, `memoria_${userId}.json`);
}

// ── ¿Es el usuario administrador? (comparte memoria con la app de PC) ──────────
function esAdmin(userId) {
  try {
    const { adminId } = loadConfig();
    return adminId && String(userId) === String(adminId);
  } catch {
    return false;
  }
}

// ── memoria.json de la app (formato estructurado) ─────────────────────────────
function estructuraVacia() {
  const ahora = new Date().toISOString();
  return {
    usuario: { nombre: null, preferencias: [], contexto: "" },
    recuerdos: [],
    datos_clave: {},
    resumen_sesion_anterior: "",
    estadisticas: { total_mensajes: 0, primera_sesion: ahora, ultima_sesion: ahora },
  };
}

function loadRoot() {
  try {
    return JSON.parse(readFileSync(ROOT_MEM, "utf-8"));
  } catch {
    return null;
  }
}

function saveRoot(data) {
  writeFileSync(ROOT_MEM, JSON.stringify(data, null, 2), "utf-8");
}

// Vista plana (clave:valor) de lo que el bot administra: nombre + datos_clave
function rootToFlat(root) {
  const flat = {};
  if (root?.usuario?.nombre) flat.nombre = root.usuario.nombre;
  Object.assign(flat, root?.datos_clave || {});
  return flat;
}

// ── API pública ───────────────────────────────────────────────────────────────

export function loadMemoria(userId) {
  if (esAdmin(userId)) {
    const root = loadRoot();
    return root ? rootToFlat(root) : {};
  }
  // Usuarios normales: archivo plano por usuario (como antes)
  try {
    if (!existsSync(memoriaPath(userId))) return {};
    return JSON.parse(readFileSync(memoriaPath(userId), "utf-8"));
  } catch {
    return {};
  }
}

export function saveMemoria(userId, datos) {
  if (esAdmin(userId)) {
    // Vuelca a la memoria.json compartida sin pisar los recuerdos de la app
    const root = loadRoot() || estructuraVacia();
    if (!root.usuario) root.usuario = { nombre: null, preferencias: [], contexto: "" };
    const { nombre, ...resto } = datos || {};
    if (nombre) root.usuario.nombre = nombre;
    root.datos_clave = resto;           // conjunto de hechos que gestiona el bot
    saveRoot(root);
    return;
  }
  // Usuarios normales: archivo plano por usuario (como antes)
  if (!existsSync(MEMORIA_DIR)) mkdirSync(MEMORIA_DIR, { recursive: true });
  writeFileSync(memoriaPath(userId), JSON.stringify(datos, null, 2), "utf-8");
}

export function buildMemoryPrompt(userId) {
  if (esAdmin(userId)) {
    const root = loadRoot();
    if (!root) return "";
    const lineas = [];
    if (root.usuario?.nombre) lineas.push(`- nombre: ${root.usuario.nombre}`);
    for (const [k, v] of Object.entries(root.datos_clave || {})) lineas.push(`- ${k}: ${v}`);
    // También incluye los recuerdos de texto libre guardados desde la app de PC
    for (const r of root.recuerdos || []) if (r?.contenido) lineas.push(`- ${r.contenido}`);
    if (root.resumen_sesion_anterior) lineas.push(`- (sesión anterior) ${root.resumen_sesion_anterior}`);
    if (!lineas.length) return "";
    return `\n\n[Lo que recuerdas de este usuario]:\n${lineas.join("\n")}`;
  }
  // Usuarios normales
  const mem = loadMemoria(userId);
  if (!mem || Object.keys(mem).length === 0) return "";
  const datos = Object.entries(mem).map(([k, v]) => `- ${k}: ${v}`).join("\n");
  return `\n\n[Lo que recuerdas de este usuario]:\n${datos}`;
}
