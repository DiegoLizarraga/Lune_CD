import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MEMORIA_DIR = join(__dirname, "data");

function memoriaPath(userId) {
  return join(MEMORIA_DIR, `memoria_${userId}.json`);
}

export function loadMemoria(userId) {
  try {
    if (!existsSync(memoriaPath(userId))) return {};
    const raw = readFileSync(memoriaPath(userId), "utf-8");
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export function saveMemoria(userId, datos) {
  if (!existsSync(MEMORIA_DIR)) mkdirSync(MEMORIA_DIR, { recursive: true });
  writeFileSync(memoriaPath(userId), JSON.stringify(datos, null, 2), "utf-8");
}

export function buildMemoryPrompt(userId) {
  const mem = loadMemoria(userId);
  if (!mem || Object.keys(mem).length === 0) return "";
  const datos = Object.entries(mem)
    .map(([k, v]) => `- ${k}: ${v}`)
    .join("\n");
  return `\n\n[Lo que recuerdas de este usuario]:\n${datos}`;
}
