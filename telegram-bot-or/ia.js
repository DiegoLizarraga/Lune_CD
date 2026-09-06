/**
 * ia.js — Puente del bot con los modelos de lenguaje.
 *
 * Dos proveedores con la misma firma, y un despachador (`chatIA`) que elige
 * segun `bot.proveedor` en datos.json:
 *   · openrouter → nube, con API key
 *   · ollama     → modelo local, en esta maquina o en otra de la red
 *                  (modelos.ollama_url / ollama_model, los mismos que la app)
 *
 * Vive aparte de bot.js para poder probarlo sin arrancar Telegram.
 */
import { loadConfig } from "./config.js";
import { hubDisponible, chatViaHost } from "./memoria.js";

const config = loadConfig();

// ── OpenRouter ────────────────────────────────────────────────────────────────
export async function chatOpenRouter(messages, systemPrompt) {
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

// ── Ollama (modelo local: en esta maquina o en otra de la red) ──────────────
// Sin streaming: Telegram entrega mensajes completos, y asi el codigo queda
// simetrico con chatOpenRouter. El keep_alive evita que el servidor descargue
// el modelo de memoria entre mensajes.
export async function chatOllama(messages, systemPrompt) {
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), config.ollamaTimeoutMs);
  let response;
  try {
    response = await fetch(`${config.ollamaUrl}/api/chat`, {
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

// Un solo punto de entrada: el proveedor lo decide datos.json (bot.proveedor).
export async function chatIA(messages, systemPrompt) {
  // Si hay un host conectado, el chat lo corre EL HOST (agente): mismo cerebro,
  // misma memoria y las herramientas de escritorio. El bot solo manda el texto.
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
    return chatOllama(messages, systemPrompt);
  }
  return chatOpenRouter(messages, systemPrompt);
}

export function chatViaHostDisponible() { return hubDisponible(); }

export function descripcionModelo() {
  return config.proveedor === "ollama"
    ? `${config.ollamaModel} · local en ${config.ollamaUrl}`
    : `${config.modelo} · OpenRouter`;
}
