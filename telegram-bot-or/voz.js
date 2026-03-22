import { execFile } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { existsSync } from "fs";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Voces en español disponibles en edge-tts:
// es-MX-DaliaNeural     (mujer, México)
// es-MX-JorgeNeural     (hombre, México)
// es-ES-ElviraNeural    (mujer, España)
// es-ES-AlvaroNeural    (hombre, España)
const VOZ = "es-MX-DaliaNeural";

export async function textToVoice(texto, userId) {
  // Limpiar markdown para que no se lea raro en voz
  const textoLimpio = texto
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`(.*?)`/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .replace(/\[MEMORIA:.*?\]/gs, "")
    .trim();

  // Limitar a 500 chars para no generar audios muy largos
  const textoCorto = textoLimpio.length > 500
    ? textoLimpio.substring(0, 500) + "..."
    : textoLimpio;

  const outputPath = join(__dirname, "data", `voz_${userId}_${Date.now()}.mp3`);

  return new Promise((resolve) => {
    execFile(
      "edge-tts",
      ["--voice", VOZ, "--text", textoCorto, "--write-media", outputPath],
      (error) => {
        if (error) {
          console.error("edge-tts error:", error.message);
          resolve(null);
          return;
        }
        resolve(outputPath);
      }
    );
  });
}
