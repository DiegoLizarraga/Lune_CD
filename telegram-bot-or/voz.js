/**
 * voz.js — Notas de voz del bot con edge-tts, con la MISMA voz que Lune en el escritorio.
 *
 * La voz se resuelve igual que en servicios/voces.py (resolver_voz con motor edge):
 *   personaje["voz"] (datos.json)  >  config.json voz.edge_voz / edge_rate / edge_pitch / edge_volumen
 *   >  es-MX-DaliaNeural, +0%, +0Hz
 * Un personaje con voz de Kokoro o gTTS usa aquí la de edge de config: el bot solo tiene edge-tts.
 *
 * A la CLI de edge-tts se le pasan las opciones con "=" (--rate=-10%): separado por un
 * espacio, argparse toma "-10%" por otra opción y falla. El texto va igual (--text=…) por
 * si empieza por un guion.
 */
import { execFile } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { readFileSync } from "fs";
import { loadConfig, getPersonaje } from "./config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const VOZ_DEFECTO = "es-MX-DaliaNeural";

// Las mismas expresiones con las que edge-tts valida (edge_tts/data_classes.py).
const RE_VOZ = /^[a-z]{2,}-[A-Z]{2,}-.+Neural$/;

/** 10, "10", "10%", "+10%" → "+10%" (acotado); null si no se entiende. */
export function normalizar(valor, sufijo, min, max) {
  if (valor === null || valor === undefined || typeof valor === "boolean") return null;
  let s = String(valor).trim().replace(/\s+/g, "");
  if (s.toLowerCase().endsWith(sufijo.toLowerCase())) s = s.slice(0, -sufijo.length);
  if (s === "" || !/^[+-]?\d+(\.\d+)?$/.test(s)) return null;
  const n = Math.max(min, Math.min(max, Math.round(Number(s))));
  return `${n >= 0 ? "+" : "-"}${Math.abs(n)}${sufijo}`;
}

function primero(candidatos, fn) {
  for (const c of candidatos) {
    const v = fn(c);
    if (v) return v;
  }
  return null;
}

/** {voz, rate, pitch, volumen} para edge-tts a partir del personaje y de config.json voz.*. */
export function vozDePersonaje(personaje, cfgVoz = {}) {
  let pv = personaje?.voz;
  if (typeof pv === "string") pv = { id: pv };
  if (!pv || typeof pv !== "object") pv = {};
  const cfg = cfgVoz && typeof cfgVoz === "object" ? cfgVoz : {};
  const idOk = (v) => (typeof v === "string" && RE_VOZ.test(v.trim()) ? v.trim() : null);
  return {
    voz: primero([pv.id, cfg.edge_voz], idOk) ?? VOZ_DEFECTO,
    rate: primero([pv.rate, cfg.edge_rate], (v) => normalizar(v, "%", -90, 200)) ?? "+0%",
    pitch: primero([pv.pitch, cfg.edge_pitch], (v) => normalizar(v, "Hz", -100, 100)) ?? "+0Hz",
    volumen: primero([pv.volumen, cfg.edge_volumen], (v) => normalizar(v, "%", -100, 100)) ?? "+0%",
  };
}

/** Argumentos de la CLI de edge-tts, todos con "=". */
export function argsEdgeTts(texto, salida, v) {
  return [
    `--voice=${v.voz}`,
    `--rate=${v.rate}`,
    `--pitch=${v.pitch}`,
    `--volume=${v.volumen}`,
    `--text=${texto}`,
    `--write-media=${salida}`,
  ];
}

function leerConfigVoz() {
  try {
    const c = JSON.parse(readFileSync(join(__dirname, "..", "config.json"), "utf-8"));
    return c?.voz ?? {};
  } catch {
    return {};
  }
}

/**
 * Voz del personaje activo. `personaje` puede ser el objeto, su nombre o nada
 * (entonces se usa bot.personaje_default de datos.json).
 */
export function vozActiva(personaje = null) {
  let p = personaje && typeof personaje === "object" ? personaje : null;
  if (!p) {
    try {
      const nombre = typeof personaje === "string" && personaje ? personaje : loadConfig().personajeDefault;
      p = getPersonaje(nombre) ?? null;
    } catch {
      p = null;
    }
  }
  return vozDePersonaje(p, leerConfigVoz());
}

function ejecutar(cmd, args) {
  return new Promise((resolve) => {
    execFile(cmd, args, (error) => resolve(error || null));
  });
}

// pip instala edge-tts.exe en una carpeta Scripts que no siempre está en el PATH:
// si el ejecutable no aparece, se usa el mismo módulo con `python -m edge_tts`.
async function edgeTts(args) {
  let error = await ejecutar("edge-tts", args);
  if (error && error.code === "ENOENT") {
    error = await ejecutar(process.env.PYTHON || "python", ["-m", "edge_tts", ...args]);
  }
  if (error) {
    console.error("edge-tts error:", error.message);
    return false;
  }
  return true;
}

export async function textToVoice(texto, userId, personaje = null) {
  // Limpiar markdown y marcadores <|…|> para que no se lean en voz
  const textoLimpio = texto
    .replace(/<\|[\s\S]*?\|>/g, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`(.*?)`/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .replace(/\[MEMORIA:.*?\]/gs, "")
    .trim();
  if (!textoLimpio) return null;

  // Limitar a 500 chars para no generar audios muy largos
  const textoCorto = textoLimpio.length > 500
    ? textoLimpio.substring(0, 500) + "..."
    : textoLimpio;

  const outputPath = join(__dirname, "data", `voz_${userId}_${Date.now()}.mp3`);
  const v = vozActiva(personaje);

  if (await edgeTts(argsEdgeTts(textoCorto, outputPath, v))) return outputPath;
  // Una voz que no existe da NoAudioReceived: se avisa en consola y se usa la de siempre.
  if (v.voz !== VOZ_DEFECTO) {
    console.error(`edge-tts: la voz ${v.voz} no respondió; uso ${VOZ_DEFECTO}.`);
    if (await edgeTts(argsEdgeTts(textoCorto, outputPath, { ...v, voz: VOZ_DEFECTO }))) return outputPath;
  }
  return null;
}
