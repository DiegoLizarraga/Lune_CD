import {
  readdirSync, statSync, existsSync, mkdirSync, renameSync
} from "fs";
import { join, extname, basename, dirname } from "path";
import { homedir } from "os";

export const HOME = homedir();

const EXTENSIONES_FOTO  = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"];
const EXTENSIONES_VIDEO = [".mp4", ".mov", ".avi", ".mkv", ".webm"];
const EXTENSIONES_AUDIO = [".mp3", ".ogg", ".wav", ".flac", ".m4a"];
const EXTENSIONES_DOC   = [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv", ".zip", ".rar"];

// Resolver ruta relativa al home
export function resolverRuta(ruta) {
  if (!ruta || ruta === "~" || ruta === "") return HOME;
  if (ruta.startsWith("/")) {
    // Rutas absolutas solo permitidas dentro del home
    if (!ruta.startsWith(HOME)) return HOME;
    return ruta;
  }
  if (ruta.startsWith("~/")) return join(HOME, ruta.slice(2));
  return join(HOME, ruta);
}

// Listar contenido de una carpeta
export function listarCarpeta(ruta) {
  const rutaReal = resolverRuta(ruta);

  if (!existsSync(rutaReal)) {
    return { error: `No existe la carpeta: ${rutaReal}` };
  }

  const stat = statSync(rutaReal);
  if (!stat.isDirectory()) {
    return { error: `Eso no es una carpeta: ${rutaReal}` };
  }

  const items = readdirSync(rutaReal, { withFileTypes: true });

  const carpetas = [];
  const archivos = [];

  for (const item of items) {
    if (item.name.startsWith(".")) continue; // ocultar archivos ocultos
    const rutaItem = join(rutaReal, item.name);
    if (item.isDirectory()) {
      carpetas.push({ nombre: item.name, ruta: rutaItem });
    } else if (item.isFile()) {
      const info = statSync(rutaItem);
      archivos.push({
        nombre: item.name,
        ruta: rutaItem,
        ext: extname(item.name).toLowerCase(),
        tamano: info.size,
      });
    }
  }

  return { ruta: rutaReal, carpetas, archivos };
}

// Formatear tamano en KB/MB
export function formatearTamano(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Clasificar archivo por extension
export function tipoArchivo(ext) {
  if (EXTENSIONES_FOTO.includes(ext))  return "foto";
  if (EXTENSIONES_VIDEO.includes(ext)) return "video";
  if (EXTENSIONES_AUDIO.includes(ext)) return "audio";
  if (EXTENSIONES_DOC.includes(ext))   return "documento";
  return "otro";
}

// Filtrar solo fotos de una lista de archivos
export function soloFotos(archivos) {
  return archivos.filter(a => EXTENSIONES_FOTO.includes(a.ext));
}

// Guardar archivo recibido en carpeta destino
export function prepararCarpetaRecibidos() {
  const ruta = join(HOME, "BotRecibidos");
  if (!existsSync(ruta)) mkdirSync(ruta, { recursive: true });
  return ruta;
}

// Construir texto de listado para Telegram
export function textoListado(resultado, rutaMostrada) {
  if (resultado.error) return resultado.error;

  const { carpetas, archivos } = resultado;
  const lineas = [`📂 ${rutaMostrada || resultado.ruta}\n`];

  if (carpetas.length === 0 && archivos.length === 0) {
    lineas.push("(carpeta vacía)");
    return lineas.join("\n");
  }

  if (carpetas.length > 0) {
    lineas.push(`Carpetas (${carpetas.length}):`);
    carpetas.slice(0, 20).forEach(c => lineas.push(`📁 ${c.nombre}`));
    if (carpetas.length > 20) lineas.push(`...y ${carpetas.length - 20} más`);
  }

  if (archivos.length > 0) {
    lineas.push(`\nArchivos (${archivos.length}):`);
    archivos.slice(0, 30).forEach(a => {
      const tipo = tipoArchivo(a.ext);
      const icono = tipo === "foto" ? "🖼" : tipo === "video" ? "🎬" : tipo === "audio" ? "🎵" : tipo === "documento" ? "📄" : "📎";
      lineas.push(`${icono} ${a.nombre} (${formatearTamano(a.tamano)})`);
    });
    if (archivos.length > 30) lineas.push(`...y ${archivos.length - 30} más`);
  }

  return lineas.join("\n");
}
