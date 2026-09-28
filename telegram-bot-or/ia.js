/**
 * ia.js — Puente del bot con los modelos de lenguaje.
 *
 * Tres proveedores con la misma firma, y un despachador (`chatIA`) que elige
 * segun `bot.proveedor` en datos.json:
 *   · openrouter → nube, con API key
 *   · ollama     → modelo local, en esta maquina o en otra de la red
 *                  (modelos.ollama_url / ollama_model, los mismos que la app)
 *   · compat     → cualquier API compatible con OpenAI (LM Studio, llama.cpp,
 *                  Groq, OpenAI…) con la MISMA configuracion que la app:
 *                  modelos.compat_url / compat_model / compat_key (o apis.compat_key)
 *                  / compat_timeout. Sin modelo, el primero que devuelva /models.
 *                  Antes, con «compat» el bot caia a OpenRouter.
 *
 * Vive aparte de bot.js para poder probarlo sin arrancar Telegram. La configuracion
 * se lee al primer uso (no al importar) y cada funcion acepta la suya y su `fetch`
 * (tests/js/telegram_ia.test.mjs, sin datos.json ni red).
 */
import { loadConfig } from "./config.js";
import { hubDisponible, chatViaHost } from "./memoria.js";

let _config = null;
function configActual() { return (_config ??= loadConfig()); }

// ── OpenRouter ────────────────────────────────────────────────────────────────
export async function chatOpenRouter(messages, systemPrompt, config = configActual(), fetchFn = globalThis.fetch) {
  const response = await fetchFn("https://openrouter.ai/api/v1/chat/completions", {
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

// ── Ollama (modelo local: en esta maquina o en otra de la red) ──────────────
// Sin streaming: Telegram entrega mensajes completos, y asi el codigo queda
// simetrico con chatOpenRouter. El keep_alive evita que el servidor descargue
// el modelo de memoria entre mensajes.
export async function chatOllama(messages, systemPrompt, config = configActual(), fetchFn = globalThis.fetch) {
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), config.ollamaTimeoutMs);
  let response;
  try {
    response = await fetchFn(`${config.ollamaUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        model: config.ollamaModel,
        stream: false,
        keep_alive: config.ollamaKeepAlive,
        options: {
          num_ctx: config.ollamaNumCtx,
          temperature: config.temperatura,
          num_predict: config.maxTokens ?? 1024,
        },
        messages: [
          { role: "system", content: systemPrompt },
          ...messages,
        ],
      }),
    });
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error(`El modelo local no respondio en ${config.ollamaTimeoutMs / 1000}s.`);
    }
    const code = e.cause?.code;
    if (code === "ECONNREFUSED" || code === "ENOTFOUND" || code === "EHOSTUNREACH" || code === "ETIMEDOUT") {
      throw new Error(`No hay servidor Ollama en ${config.ollamaUrl}. ¿Esta encendido?`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Ollama error ${response.status}: ${err}`);
  }
  const data = await response.json();
  if (data.error) throw new Error(`Ollama: ${data.error}`);
  return data.message?.content ?? "";
}

// ── Compatible con OpenAI (lo mismo que servicios/ai_manager.CompatProvider) ──
const DOMINIOS_LOCALES = [".local", ".lan", ".home", ".internal", ".localhost", ".ts.net"];

function hostDe(url) {
  let t = String(url ?? "").trim();
  if (!t.includes("://")) t = "http://" + t;
  try { return new URL(t).hostname.toLowerCase().replace(/^\[|\]$/g, ""); } catch { return ""; }
}

/** ¿La URL apunta a este equipo o a la red local (LAN, Tailscale, *.local)? */
export function esHostLocal(url) {
  const h = hostDe(url);
  if (!h) return false;
  if (h === "localhost" || DOMINIOS_LOCALES.some((s) => h.endsWith(s))) return true;
  const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
      || (a === 169 && b === 254) || (a === 100 && b >= 64 && b <= 127);      // 100.64/10: Tailscale
  }
  if (h.includes(":")) return h === "::1" || /^f[cd]/.test(h) || /^fe[89ab]/.test(h);
  return !h.includes(".");                   // nombre de equipo de la red ("pc-potente")
}

/**
 * URL base como la de la app (ai_manager.base_compat): «localhost:1234» →
 * «http://localhost:1234/v1»; «api.openai.com» → «https://api.openai.com/v1»; si
 * pegaron el endpoint completo («…/v1/chat/completions») se le quita la cola; una
 * ruta propia («https://api.groq.com/openai/v1») se respeta.
 */
export function baseCompat(url) {
  let b = String(url ?? "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (!b.includes("://")) b = (esHostLocal(b) ? "http://" : "https://") + b;
  for (const sufijo of ["/chat/completions", "/completions", "/models"]) {
    if (b.toLowerCase().endsWith(sufijo)) { b = b.slice(0, -sufijo.length).replace(/\/+$/, ""); break; }
  }
  let ruta = "";
  try { ruta = new URL(b).pathname; } catch { ruta = ""; }
  if (ruta === "" || ruta === "/") b = b.replace(/\/+$/, "") + "/v1";
  return b;
}

/** o1/o3/o4 y gpt-5 (no los «-chat») de OpenAI: sin temperature (daría 400). */
function esRazonamientoOpenAI(modelo) {
  const m = String(modelo ?? "").trim().toLowerCase();
  return /^o\d/.test(m) || (m.startsWith("gpt-5") && !m.includes("-chat"));
}

let _modeloAuto = { base: "", modelo: "" };   // el de /models, por URL

async function conTope(fetchFn, url, opciones, ms, host) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetchFn(url, { ...opciones, signal: ctrl.signal });
  } catch (e) {
    if (e.name === "AbortError") throw new Error(`La API compatible no respondio en ${Math.round(ms / 1000)}s.`);
    const code = e.cause?.code;
    if (code === "ECONNREFUSED" || code === "ENOTFOUND" || code === "EHOSTUNREACH" || code === "ETIMEDOUT") {
      throw new Error(`No pude conectar con ${host}. ¿Esta encendido el servidor?`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function errorHttp(status, detalle) {
  const cola = detalle ? `: ${String(detalle).slice(0, 200)}` : "";
  if (status === 401 || status === 403) return `API compatible: el servidor rechazo la clave (HTTP ${status})${cola}.`;
  if (status === 404) return `API compatible: no encontrado (HTTP 404)${cola}. Revisa la URL (suele terminar en /v1) y el modelo.`;
  if (status === 429) return `API compatible: demasiadas peticiones, espera un momento${cola}.`;
  return `API compatible: HTTP ${status}${cola}.`;
}

export async function chatCompat(messages, systemPrompt, config = configActual(), fetchFn = globalThis.fetch) {
  const base = baseCompat(config.compatUrl);
  if (!base) {
    throw new Error("No hay URL de la API compatible (modelos.compat_url en datos.json, o Ajustes de Lune → IA avanzada).");
  }
  const host = hostDe(base);
  const ms = config.compatTimeoutMs || 120000;
  const cabeceras = { "Content-Type": "application/json" };
  if (config.compatKey) cabeceras.Authorization = `Bearer ${config.compatKey}`;
  let modelo = config.compatModelo || (_modeloAuto.base === base ? _modeloAuto.modelo : "");
  if (!modelo) {
    const r = await conTope(fetchFn, `${base}/models`, { method: "GET", headers: cabeceras }, Math.min(ms, 10000), host);
    if (!r.ok) throw new Error(errorHttp(r.status, await r.text().catch(() => "")));
    const cuerpo = await r.json();
    const lista = Array.isArray(cuerpo) ? cuerpo : cuerpo?.data;
    const ids = (Array.isArray(lista) ? lista : [])
      .map((m) => (typeof m === "string" ? m : m?.id))
      .filter((id) => typeof id === "string" && id.trim());
    if (!ids.length) {
      throw new Error("API compatible: no hay modelo configurado y el servidor no devolvio ninguno en /models.");
    }
    modelo = ids[0].trim();
    _modeloAuto = { base, modelo };
  }
  const esOpenAI = host === "api.openai.com";
  const cuerpo = {
    model: modelo,
    messages: [{ role: "system", content: systemPrompt }, ...messages],
    stream: false,
  };
  // OpenAI ya prefiere max_completion_tokens; el resto del mundo sigue con max_tokens.
  cuerpo[esOpenAI ? "max_completion_tokens" : "max_tokens"] = config.maxTokens ?? 1024;
  if (!(esOpenAI && esRazonamientoOpenAI(modelo)) && Number.isFinite(config.temperatura)) {
    cuerpo.temperature = config.temperatura;
  }
  const response = await conTope(fetchFn, `${base}/chat/completions`, {
    method: "POST", headers: cabeceras, body: JSON.stringify(cuerpo),
  }, ms, host);
  if (!response.ok) throw new Error(errorHttp(response.status, await response.text().catch(() => "")));
  const data = await response.json();
  return data?.choices?.[0]?.message?.content ?? "";
}

// Un solo punto de entrada: el proveedor lo decide datos.json (bot.proveedor).
export async function chatIA(messages, systemPrompt, { config = configActual(), fetchFn = globalThis.fetch } = {}) {
  // Si hay un host conectado, el chat lo corre EL HOST (agente): mismo cerebro y
  // las herramientas de LECTURA. El bot solo manda el texto; el host no pone la
  // memoria del usuario en ese prompt (no puede saber quien escribe por Telegram).
  if (hubDisponible()) {
    const ultimo = [...messages].reverse().find(m => m.role === "user")?.content ?? "";
    if (ultimo) {
      try { return await chatViaHost(ultimo); }
      catch (e) { console.error("[hub] chat via host fallo, uso local:", e.message); }
    }
  }
  if (config.proveedor === "ollama") {
    if (!config.ollamaModel) {
      throw new Error("No hay modelo local configurado (modelos.ollama_model en datos.json).");
    }
    return chatOllama(messages, systemPrompt, config, fetchFn);
  }
  if (config.proveedor === "compat") return chatCompat(messages, systemPrompt, config, fetchFn);
  return chatOpenRouter(messages, systemPrompt, config, fetchFn);
}

export function chatViaHostDisponible() { return hubDisponible(); }

export function descripcionModelo(config = configActual()) {
  if (config.proveedor === "ollama") return `${config.ollamaModel} · local en ${config.ollamaUrl}`;
  if (config.proveedor === "compat") {
    const base = baseCompat(config.compatUrl);
    return `${config.compatModelo || "el primero de /models"} · API compatible en ${hostDe(base) || "(sin URL)"}`;
  }
  return `${config.modelo} · OpenRouter`;
}
