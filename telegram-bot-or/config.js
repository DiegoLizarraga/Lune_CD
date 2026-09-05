import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// datos.json está en la carpeta padre (raíz del proyecto)
// Si no existe ahí, busca en la carpeta actual como fallback
function findDatosJson() {
  const enPadre  = join(__dirname, "..", "datos.json");
  const enActual = join(__dirname, "datos.json");
  try {
    readFileSync(enPadre);
    return enPadre;
  } catch {
    return enActual;
  }
}

function loadDatos() {
  const path = findDatosJson();
  const raw  = readFileSync(path, "utf-8");
  return JSON.parse(raw);
}

// Construye el objeto config en el formato que espera bot.js
//
// El bot lee las MISMAS claves de `modelos` que la app de escritorio
// (ollama_url, ollama_model, ollama_keep_alive…): una sola fuente de verdad.
// Lo único propio del bot es `bot.proveedor`, que decide a quién pregunta.
export function loadConfig() {
  const datos = loadDatos();
  const m = datos.modelos ?? {};
  return {
    telegramToken:    datos.apis?.telegram_token     ?? "",
    openrouterKey:    datos.apis?.openrouter_key     ?? "",
    adminId:          datos.apis?.telegram_admin_id  ?? "",

    // "ollama" (modelo local, en esta máquina o en otra de la red) u "openrouter" (nube)
    proveedor:        (datos.bot?.proveedor ?? "openrouter").toLowerCase(),

    // La app escribe `openrouter_model`; `openrouter` es el nombre viejo de la
    // clave y se mantiene solo para no romper datos.json de versiones previas.
    modelo:           m.openrouter_model ?? m.openrouter ?? "openrouter/auto",

    ollamaUrl:        (m.ollama_url ?? "http://localhost:11434").replace(/\/+$/, ""),
    ollamaModel:      m.ollama_model ?? "",
    ollamaKeepAlive:  m.ollama_keep_alive ?? "30m",
    ollamaNumCtx:     Number(m.ollama_num_ctx) || 8192,
    ollamaTimeoutMs:  (Number(m.ollama_timeout) || 300) * 1000,
    temperatura:      Number(m.temperatura ?? 0.7),

    // Hub de Lune: en modo 'host' el bot corre junto al núcleo (127.0.0.1);
    // en 'terminal' se conecta a la URL del host; en 'local' no hay hub.
    hubModo:          (datos.hub?.modo ?? "local").toLowerCase(),
    hubUrl:           (datos.hub?.modo ?? "local").toLowerCase() === "host"
                        ? `ws://127.0.0.1:${Number(datos.hub?.puerto) || 7777}`
                        : ((datos.hub?.modo ?? "local").toLowerCase() === "terminal" ? (datos.hub?.url_host ?? "") : ""),
    hubToken:         datos.hub?.token ?? "",

    personajeDefault: datos.bot?.personaje_default    ?? "",
    maxHistorial:     datos.bot?.max_historial        ?? 20,
    maxTokens:        datos.bot?.max_tokens           ?? 1024,
    personajes:       datos.personajes                ?? [],
  };
}

export function getPersonaje(nombre) {
  const { personajes } = loadConfig();
  return (
    personajes.find(
      (p) => p.nombre.toLowerCase() === nombre?.toLowerCase()
    ) ?? personajes[0]
  );
}
