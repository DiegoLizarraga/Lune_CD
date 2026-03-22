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
export function loadConfig() {
  const datos = loadDatos();
  return {
    telegramToken:    datos.apis?.telegram_token     ?? "",
    openrouterKey:    datos.apis?.openrouter_key     ?? "",
    adminId:          datos.apis?.telegram_admin_id  ?? "",
    modelo:           datos.modelos?.openrouter       ?? "stepfun/step-3.5-flash:free",
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
