import { Bot, session, InlineKeyboard } from "grammy";
import { loadConfig, getPersonaje } from "./config.js";
import { loadMemoria, saveMemoria, buildMemoryPrompt } from "./memoria.js";
import { textToVoice } from "./voz.js";
import { buscarWeb } from "./search.js";
import { unlinkSync, createWriteStream, existsSync, createReadStream } from "fs";
import { join } from "path";
import {
  resolverRuta, listarCarpeta, textoListado,
  soloFotos, tipoArchivo, prepararCarpetaRecibidos,
  formatearTamano, HOME
} from "./archivos.js";
import { estadoSistema } from "./sistema.js";

const config = loadConfig();
const bot = new Bot(config.telegramToken);

// ── SEGURIDAD: solo tu usuario puede usar el bot ─────────────────────────────
// Pon tu Telegram ID en config.json como "adminId": 123456789
// Para saber tu ID escribe /id al bot antes de activar el filtro
function esAdmin(ctx) {
  if (!config.adminId) return true; // si no esta configurado, permite todo
  return String(ctx.from?.id) === String(config.adminId);
}

function soloAdmin(ctx, next) {
  if (!esAdmin(ctx)) return ctx.reply("No tienes permiso para usar este bot.");
  return next();
}

// ── OpenRouter ────────────────────────────────────────────────────────────────
async function chatOpenRouter(messages, systemPrompt) {
  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${config.openrouterKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://telegram-bot.local",
      "X-Title": "Telegram Chatbot",
    },
    body: JSON.stringify({
      model: config.modelo,
      max_tokens: config.maxTokens ?? 1024,
      messages: [
        { role: "system", content: systemPrompt },
        ...messages,
      ],
    }),
  });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(`OpenRouter error ${response.status}: ${err}`);
  }
  const data = await response.json();
  return data.choices[0].message.content;
}

// ── Sesion ────────────────────────────────────────────────────────────────────
bot.use(session({
  initial: () => ({
    history: [],
    personajeActivo: config.personajeDefault,
    vozActiva: false,
    rutaActual: HOME,
  }),
}));

bot.use(soloAdmin);

// ── Menu inline ───────────────────────────────────────────────────────────────
function menuPrincipal() {
  return new InlineKeyboard()
    .text("Personajes", "cmd_personajes").text("Cambiar personaje", "cmd_cambiar").row()
    .text("Voz ON/OFF", "cmd_voz").text("Buscar en web", "cmd_buscar").row()
    .text("Mi memoria", "cmd_memoria").text("Olvidar todo", "cmd_olvidar").row()
    .text("Archivos", "cmd_archivos").text("Sistema", "cmd_sistema").row()
    .text("Limpiar chat", "cmd_limpiar").text("Modelo activo", "cmd_modelo");
}

// ── /start ────────────────────────────────────────────────────────────────────
bot.command("start", async (ctx) => {
  const p = getPersonaje(ctx.session.personajeActivo);
  await ctx.reply(
    `Hola! Soy *${p.nombre}*.\n${p.descripcion}\n\nUsa el menu de abajo o escribe "/" para ver los comandos.`,
    { parse_mode: "Markdown", reply_markup: menuPrincipal() }
  );
});

// ── /id (para saber tu Telegram ID) ──────────────────────────────────────────
bot.command("id", async (ctx) => {
  await ctx.reply(`Tu Telegram ID es: \`${ctx.from.id}\`\nPonlo en config.json como "adminId" para activar la proteccion.`, { parse_mode: "Markdown" });
});

// ── Callbacks del menu ────────────────────────────────────────────────────────
bot.callbackQuery("cmd_personajes", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const lista = config.personajes.map((p, i) => `${i + 1}. *${p.nombre}* - ${p.descripcion}`).join("\n");
  const kb = new InlineKeyboard();
  config.personajes.forEach(p => kb.text(p.nombre, `usar_${p.nombre}`).row());
  await ctx.reply(`*Personajes disponibles:*\n\n${lista}\n\nSelecciona uno:`, { parse_mode: "Markdown", reply_markup: kb });
});

bot.callbackQuery("cmd_cambiar", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const kb = new InlineKeyboard();
  config.personajes.forEach(p => kb.text(p.nombre, `usar_${p.nombre}`).row());
  await ctx.reply("Elige un personaje:", { reply_markup: kb });
});

bot.callbackQuery(/^usar_(.+)$/, async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const nombre = ctx.match[1];
  const p = config.personajes.find(p => p.nombre.toLowerCase() === nombre.toLowerCase());
  if (!p) { await ctx.reply("No encontre ese personaje."); return; }
  ctx.session.personajeActivo = p.nombre;
  ctx.session.history = [];
  await ctx.reply(`Listo! Ahora hablas con *${p.nombre}*. Conversacion reiniciada.`, { parse_mode: "Markdown", reply_markup: menuPrincipal() });
});

bot.callbackQuery("cmd_voz", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  ctx.session.vozActiva = !ctx.session.vozActiva;
  const estado = ctx.session.vozActiva ? "Voz *activada*" : "Voz *desactivada*";
  await ctx.reply(estado, { parse_mode: "Markdown", reply_markup: menuPrincipal() });
});

bot.callbackQuery("cmd_buscar", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  await ctx.reply("Escribe: /buscar <consulta>\nEjemplo: /buscar clima en Guadalajara");
});

bot.callbackQuery("cmd_memoria", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const mem = loadMemoria(String(ctx.from.id));
  if (!mem || Object.keys(mem).length === 0) { await ctx.reply("No tengo nada guardado todavia."); return; }
  const texto = Object.entries(mem).map(([k, v]) => `- *${k}*: ${v}`).join("\n");
  await ctx.reply(`*Lo que recuerdo de ti:*\n\n${texto}`, { parse_mode: "Markdown" });
});

bot.callbackQuery("cmd_olvidar", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  saveMemoria(String(ctx.from.id), {});
  await ctx.reply("Memoria borrada.", { reply_markup: menuPrincipal() });
});

bot.callbackQuery("cmd_limpiar", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  ctx.session.history = [];
  await ctx.reply("Conversacion limpiada.", { reply_markup: menuPrincipal() });
});

bot.callbackQuery("cmd_modelo", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  await ctx.reply(`Modelo actual: \`${config.modelo}\``, { parse_mode: "Markdown" });
});

bot.callbackQuery("cmd_sistema", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const info = estadoSistema();
  await ctx.reply(`*Estado del sistema*\n\n${info}`, { parse_mode: "Markdown" });
});

bot.callbackQuery("cmd_archivos", async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  ctx.session.rutaActual = HOME;
  const resultado = listarCarpeta(HOME);
  const texto = textoListado(resultado, "~");
  const kb = teclado_navegacion(resultado, HOME);
  await ctx.reply(texto, { reply_markup: kb });
});

// Navegar carpetas con botones
bot.callbackQuery(/^nav_(.+)$/, async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const ruta = ctx.match[1];
  ctx.session.rutaActual = ruta;
  const resultado = listarCarpeta(ruta);
  const rutaMostrada = ruta.replace(HOME, "~");
  const texto = textoListado(resultado, rutaMostrada);
  const kb = teclado_navegacion(resultado, ruta);
  await ctx.reply(texto, { reply_markup: kb });
});

// Enviar fotos de la carpeta actual
bot.callbackQuery(/^fotos_(.+)$/, async (ctx) => {
  try { await ctx.answerCallbackQuery(); } catch (_) {}
  const ruta = ctx.match[1];
  const resultado = listarCarpeta(ruta);
  if (resultado.error) { await ctx.reply(resultado.error); return; }
  const fotos = soloFotos(resultado.archivos);
  if (fotos.length === 0) { await ctx.reply("No hay fotos en esta carpeta."); return; }
  await ctx.reply(`Enviando ${Math.min(fotos.length, 10)} foto(s)...`);
  for (const foto of fotos.slice(0, 10)) {
    try {
      await ctx.replyWithPhoto({ source: foto.ruta }, { caption: foto.nombre.replace(/[_*[\]()~`>#+=|{}.!-]/g, "\\$&"), parse_mode: "MarkdownV2" });
    } catch (e) {
      await ctx.reply(`No pude enviar: ${foto.nombre} (${e.message})`);
    }
  }
  if (fotos.length > 10) await ctx.reply(`_(Se mostraron 10 de ${fotos.length} fotos. Usa /fotos <subcarpeta> para ver mas)_`, { parse_mode: "Markdown" });
});

// Construir teclado de navegacion para una carpeta
function teclado_navegacion(resultado, rutaActual) {
  const kb = new InlineKeyboard();

  if (!resultado.error) {
    // Subcarpetas (max 6)
    resultado.carpetas.slice(0, 6).forEach(c => {
      kb.text(`📁 ${c.nombre}`, `nav_${c.ruta}`).row();
    });

    // Si hay fotos, boton para enviarlas
    const fotos = soloFotos(resultado.archivos);
    if (fotos.length > 0) {
      kb.text(`🖼 Enviar ${fotos.length} foto(s)`, `fotos_${rutaActual}`).row();
    }
  }

  // Subir un nivel (si no estamos en home)
  if (rutaActual !== HOME) {
    const parent = join(rutaActual, "..");
    if (parent.startsWith(HOME)) {
      kb.text("⬆️ Subir nivel", `nav_${parent}`).row();
    }
  }

  kb.text("🏠 Inicio", "cmd_archivos");
  return kb;
}

// ── Comandos de texto ─────────────────────────────────────────────────────────
bot.command("personajes", async (ctx) => {
  const lista = config.personajes.map((p, i) => `${i + 1}. *${p.nombre}* - ${p.descripcion}`).join("\n");
  const kb = new InlineKeyboard();
  config.personajes.forEach(p => kb.text(p.nombre, `usar_${p.nombre}`).row());
  await ctx.reply(`*Personajes disponibles:*\n\n${lista}`, { parse_mode: "Markdown", reply_markup: kb });
});

bot.command("usar", async (ctx) => {
  const nombre = ctx.match?.trim();
  const p = config.personajes.find(p => p.nombre.toLowerCase() === nombre?.toLowerCase());
  if (!p) { await ctx.reply("No encontre ese personaje."); return; }
  ctx.session.personajeActivo = p.nombre;
  ctx.session.history = [];
  await ctx.reply(`Listo! Ahora hablas con *${p.nombre}*.`, { parse_mode: "Markdown" });
});

bot.command("limpiar", async (ctx) => { ctx.session.history = []; await ctx.reply("Conversacion limpiada."); });
bot.command("modelo",  async (ctx) => { await ctx.reply(`Modelo: \`${config.modelo}\``, { parse_mode: "Markdown" }); });

bot.command("voz", async (ctx) => {
  ctx.session.vozActiva = !ctx.session.vozActiva;
  await ctx.reply(ctx.session.vozActiva ? "Voz *activada*" : "Voz *desactivada*", { parse_mode: "Markdown" });
});

bot.command("memoria", async (ctx) => {
  const mem = loadMemoria(String(ctx.from.id));
  if (!mem || Object.keys(mem).length === 0) { await ctx.reply("No tengo nada guardado todavia."); return; }
  const texto = Object.entries(mem).map(([k, v]) => `- *${k}*: ${v}`).join("\n");
  await ctx.reply(`*Lo que recuerdo:*\n\n${texto}`, { parse_mode: "Markdown" });
});

bot.command("olvidar", async (ctx) => {
  saveMemoria(String(ctx.from.id), {});
  await ctx.reply("Memoria borrada.");
});

bot.command("sistema", async (ctx) => {
  await ctx.reply(`*Estado del sistema*\n\n${estadoSistema()}`, { parse_mode: "Markdown" });
});

// /ls [ruta] — listar carpeta
bot.command("ls", async (ctx) => {
  const ruta = ctx.match?.trim() || ctx.session.rutaActual || HOME;
  ctx.session.rutaActual = resolverRuta(ruta);
  const resultado = listarCarpeta(ruta);
  const rutaMostrada = resolverRuta(ruta).replace(HOME, "~");
  const texto = textoListado(resultado, rutaMostrada);
  const kb = teclado_navegacion(resultado, resolverRuta(ruta));
  await ctx.reply(texto, { reply_markup: kb });
});

// /fotos [ruta] — enviar fotos de una carpeta
bot.command("fotos", async (ctx) => {
  const ruta = ctx.match?.trim() || ctx.session.rutaActual || HOME;
  const rutaReal = resolverRuta(ruta);
  const resultado = listarCarpeta(rutaReal);
  if (resultado.error) { await ctx.reply(resultado.error); return; }
  const fotos = soloFotos(resultado.archivos);
  if (fotos.length === 0) { await ctx.reply("No hay fotos en esa carpeta."); return; }
  await ctx.reply(`Enviando ${Math.min(fotos.length, 10)} foto(s) de ${ruta}...`);
  for (const foto of fotos.slice(0, 10)) {
    try {
      await ctx.replyWithPhoto({ source: foto.ruta }, { caption: foto.nombre.replace(/[_*[\]()~`>#+=|{}.!-]/g, "\\$&"), parse_mode: "MarkdownV2" });
    } catch (e) {
      await ctx.reply(`No pude enviar: ${foto.nombre}`);
    }
  }
});

// /archivo [ruta/nombre] — enviar un archivo especifico
bot.command("archivo", async (ctx) => {
  const nombre = ctx.match?.trim();
  if (!nombre) { await ctx.reply("Uso: /archivo nombre.pdf\no con ruta: /archivo Documentos/nota.txt"); return; }
  const rutaReal = resolverRuta(nombre);
  if (!existsSync(rutaReal)) { await ctx.reply(`No encontre el archivo: ${nombre}`); return; }
  await ctx.reply(`Enviando ${nombre}...`);
  try {
    await ctx.replyWithDocument({ source: rutaReal });
  } catch (e) {
    await ctx.reply(`Error al enviar: ${e.message}\n(Recuerda: limite de 50MB por archivo)`);
  }
});

// /buscar
bot.command("buscar", async (ctx) => {
  const query = ctx.match?.trim();
  if (!query) { await ctx.reply("Uso: /buscar <consulta>"); return; }
  await ctx.replyWithChatAction("typing");
  try {
    const resultados = await buscarWeb(query);
    const personaje = getPersonaje(ctx.session.personajeActivo);
    const prompt = `El usuario quiere informacion sobre: "${query}"\n\nResultados:\n${resultados}\n\nResponde util y natural, mantén tu personalidad.`;
    ctx.session.history.push({ role: "user", content: prompt });
    const max = (config.maxHistorial ?? 20) * 2;
    if (ctx.session.history.length > max) ctx.session.history = ctx.session.history.slice(-max);
    const respuesta = await chatOpenRouter(ctx.session.history, personaje.systemPrompt);
    ctx.session.history.push({ role: "assistant", content: respuesta });
    await enviarRespuesta(ctx, respuesta);
  } catch (error) {
    await ctx.reply(`Error al buscar: ${error.message}`);
  }
});

// ── Recibir archivos/fotos enviados por el usuario ────────────────────────────
bot.on(["message:photo", "message:document", "message:video", "message:audio"], async (ctx) => {
  const carpeta = prepararCarpetaRecibidos();
  let fileId, nombre;

  if (ctx.message.photo) {
    // Tomar la foto en mejor calidad (ultimo elemento)
    const foto = ctx.message.photo.at(-1);
    fileId = foto.file_id;
    nombre = `foto_${Date.now()}.jpg`;
  } else if (ctx.message.document) {
    fileId = ctx.message.document.file_id;
    nombre = ctx.message.document.file_name ?? `archivo_${Date.now()}`;
  } else if (ctx.message.video) {
    fileId = ctx.message.video.file_id;
    nombre = ctx.message.video.file_name ?? `video_${Date.now()}.mp4`;
  } else if (ctx.message.audio) {
    fileId = ctx.message.audio.file_id;
    nombre = ctx.message.audio.file_name ?? `audio_${Date.now()}.mp3`;
  }

  try {
    const file = await ctx.getFile();
    const url  = `https://api.telegram.org/file/bot${config.telegramToken}/${file.file_path}`;
    const res  = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const destino = join(carpeta, nombre);
    const writer  = createWriteStream(destino);

    await new Promise((resolve, reject) => {
      res.body.pipeTo(new WritableStream({
        write(chunk) { writer.write(chunk); },
        close() { writer.end(); resolve(); },
        abort(err) { writer.destroy(); reject(err); },
      }));
    });

    await ctx.reply(
      `Guardado en:\n\`~/BotRecibidos/${nombre}\``,
      { parse_mode: "Markdown" }
    );
  } catch (e) {
    await ctx.reply(`Error al guardar: ${e.message}`);
  }
});

// ── Mensajes de texto normales ────────────────────────────────────────────────
bot.on("message:text", async (ctx) => {
  const userMsg = ctx.message.text;
  const userId  = String(ctx.from.id);
  const personaje = getPersonaje(ctx.session.personajeActivo);

  const necesitaBusqueda = detectarBusqueda(userMsg);
  let contextoBusqueda = "";
  if (necesitaBusqueda) {
    try {
      const resultados = await buscarWeb(userMsg);
      contextoBusqueda = `\n\n[Informacion actualizada de internet]:\n${resultados}`;
    } catch (e) { console.error("Busqueda auto:", e.message); }
  }

  const memoria = buildMemoryPrompt(userId);
  const systemPrompt = personaje.systemPrompt + memoria +
    `\n\nSi el usuario menciono datos personales (nombre, edad, gustos, trabajo, ciudad), extráelos al final:\n[MEMORIA: {"clave": "valor"}]`;

  ctx.session.history.push({ role: "user", content: userMsg + contextoBusqueda });
  const max = (config.maxHistorial ?? 20) * 2;
  if (ctx.session.history.length > max) ctx.session.history = ctx.session.history.slice(-max);

  await ctx.replyWithChatAction("typing");

  try {
    let respuesta = await chatOpenRouter(ctx.session.history, systemPrompt);
    const memoriaMatch = respuesta.match(/\[MEMORIA:\s*(\{.*?\})\]/s);
    if (memoriaMatch) {
      try {
        const nuevaMemoria = JSON.parse(memoriaMatch[1]);
        const memoriaActual = loadMemoria(userId) || {};
        saveMemoria(userId, { ...memoriaActual, ...nuevaMemoria });
      } catch (e) {}
      respuesta = respuesta.replace(/\[MEMORIA:.*?\]/s, "").trim();
    }
    ctx.session.history.push({ role: "assistant", content: respuesta });
    await enviarRespuesta(ctx, respuesta);
  } catch (error) {
    await ctx.reply(`Error: ${error.message}`);
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
async function enviarRespuesta(ctx, texto) {
  if (ctx.session.vozActiva) {
    await ctx.replyWithChatAction("record_voice");
    const audioPath = await textToVoice(texto, ctx.from.id);
    if (audioPath) {
      const { InputFile } = await import("grammy");
      await ctx.replyWithVoice(new InputFile(createReadStream(audioPath), "voz.ogg"));
      try { unlinkSync(audioPath); } catch (e) {}
      return;
    }
  }
  await ctx.reply(texto);
}

function detectarBusqueda(texto) {
  const keywords = ["que es", "quien es", "cuando", "donde esta", "como esta",
    "precio de", "noticias", "hoy", "actualmente", "busca", "buscar",
    "informacion sobre", "que paso", "clima", "temperatura", "cotizacion"];
  const lower = texto.toLowerCase();
  return keywords.some(k => lower.includes(k));
}

// ── Registrar comandos en menu "/" de Telegram ────────────────────────────────
await bot.api.setMyCommands([
  { command: "start",    description: "Inicio y bienvenida" },
  { command: "personajes", description: "Ver personajes disponibles" },
  { command: "usar",     description: "Cambiar personaje — /usar Nombre" },
  { command: "voz",      description: "Activar/desactivar respuestas de voz" },
  { command: "buscar",   description: "Buscar en internet — /buscar tema" },
  { command: "ls",       description: "Ver archivos — /ls o /ls Carpeta" },
  { command: "fotos",    description: "Ver fotos — /fotos o /fotos Carpeta" },
  { command: "archivo",  description: "Enviar un archivo — /archivo nombre.pdf" },
  { command: "sistema",  description: "Ver CPU, RAM y disco" },
  { command: "memoria",  description: "Ver lo que recuerdo de ti" },
  { command: "olvidar",  description: "Borrar mi memoria" },
  { command: "limpiar",  description: "Reiniciar conversacion" },
  { command: "modelo",   description: "Ver modelo de IA activo" },
  { command: "id",       description: "Ver tu Telegram ID" },
]);

// Manejador global de errores
bot.catch((err) => {
  const e = err.error;
  if (e?.description?.includes("query is too old")) return;
  console.error("Error:", e?.message ?? e);
});

bot.start();
console.log(`Bot iniciado | Modelo: ${config.modelo}`);
