// telegram-bot-or/ia.js con bot.proveedor = "compat": usa la API compatible con OpenAI
// de la app (modelos.compat_url / compat_model / compat_key, URL normalizada como
// servicios/ai_manager.base_compat). Antes caía a OpenRouter. Sin red ni datos.json:
// cada llamada recibe su config y un fetch de mentira.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ia = await import(pathToFileURL(join(RAIZ, "telegram-bot-or", "ia.js")).href);
const { chatIA, baseCompat, esHostLocal, descripcionModelo } = ia;

function config(extra = {}) {
  return {
    proveedor: "compat", openrouterKey: "or-clave", modelo: "openrouter/auto",
    ollamaUrl: "http://localhost:11434", ollamaModel: "", ollamaTimeoutMs: 1000,
    temperatura: 0.7, maxTokens: 512,
    compatUrl: "localhost:1234", compatKey: "", compatModelo: "qwen2.5-7b", compatTimeoutMs: 5000,
    ...extra,
  };
}

function respuesta(status, cuerpo) {
  return { ok: status >= 200 && status < 300, status,
           json: async () => cuerpo, text: async () => JSON.stringify(cuerpo) };
}

function fetchFalso(rutas) {
  const llamadas = [];
  const fn = async (url, opciones = {}) => {
    llamadas.push({ url, opciones, cuerpo: opciones.body ? JSON.parse(opciones.body) : null });
    for (const [trozo, r] of rutas) if (url.includes(trozo)) return typeof r === "function" ? r(url, opciones) : r;
    throw new Error(`URL inesperada: ${url}`);
  };
  fn.llamadas = llamadas;
  return fn;
}

const ok = (texto) => respuesta(200, { choices: [{ message: { content: texto } }] });
const MENSAJES = [{ role: "user", content: "hola" }];

test("baseCompat normaliza igual que la app (ai_manager.base_compat)", () => {
  const casos = {
    "localhost:1234": "http://localhost:1234/v1",
    "api.openai.com": "https://api.openai.com/v1",
    "http://pc:3000/api": "http://pc:3000/api",
    "https://api.groq.com/openai/v1/chat/completions": "https://api.groq.com/openai/v1",
    "http://192.168.1.5:8080/": "http://192.168.1.5:8080/v1",
    "pc-potente:1234": "http://pc-potente:1234/v1",
    "100.100.1.2:1234": "http://100.100.1.2:1234/v1",
    "10.0.0.2:11434/v1/models": "http://10.0.0.2:11434/v1",
    "https://api.together.xyz": "https://api.together.xyz/v1",
    "lmstudio.local:1234": "http://lmstudio.local:1234/v1",
    "8.8.8.8:80": "https://8.8.8.8:80/v1",
    "": "",
  };
  for (const [entrada, esperado] of Object.entries(casos)) assert.equal(baseCompat(entrada), esperado, entrada);
  assert.equal(esHostLocal("api.groq.com"), false);
  assert.equal(esHostLocal("172.20.0.1:8000"), true);
});

test("compat va a la API compatible, NO a OpenRouter", async () => {
  const f = fetchFalso([["localhost:1234/v1/chat/completions", ok("¡hola desde LM Studio!")]]);
  const texto = await chatIA(MENSAJES, "Eres Lune.", { config: config({ compatKey: "sk-local" }), fetchFn: f });
  assert.equal(texto, "¡hola desde LM Studio!");
  assert.equal(f.llamadas.length, 1);
  const [{ url, opciones, cuerpo }] = f.llamadas;
  assert.equal(url, "http://localhost:1234/v1/chat/completions");
  assert.ok(!f.llamadas.some((l) => l.url.includes("openrouter")));
  assert.equal(opciones.method, "POST");
  assert.equal(opciones.headers.Authorization, "Bearer sk-local");
  assert.equal(cuerpo.model, "qwen2.5-7b");
  assert.deepEqual(cuerpo.messages, [{ role: "system", content: "Eres Lune." }, ...MENSAJES]);
  assert.equal(cuerpo.max_tokens, 512);
  assert.equal(cuerpo.temperature, 0.7);
  assert.equal(cuerpo.stream, false);
});

test("sin clave no manda Authorization; sin modelo usa el primero de /models (una vez)", async () => {
  const f = fetchFalso([
    ["/v1/models", respuesta(200, { data: [{ id: "el-cargado" }, { id: "otro" }] })],
    ["/v1/chat/completions", ok("vale")],
  ]);
  const cfg = config({ compatUrl: "http://pc-modelos:1234", compatModelo: "" });
  assert.equal(await chatIA(MENSAJES, "s", { config: cfg, fetchFn: f }), "vale");
  assert.equal(await chatIA(MENSAJES, "s", { config: cfg, fetchFn: f }), "vale");
  const urls = f.llamadas.map((l) => l.url);
  assert.deepEqual(urls, ["http://pc-modelos:1234/v1/models", "http://pc-modelos:1234/v1/chat/completions",
                          "http://pc-modelos:1234/v1/chat/completions"]);
  assert.ok(f.llamadas.every((l) => !("Authorization" in l.opciones.headers)));
  assert.equal(f.llamadas[1].cuerpo.model, "el-cargado");
});

test("OpenAI: max_completion_tokens y, en modelos de razonamiento, sin temperature", async () => {
  const f = fetchFalso([["api.openai.com/v1/chat/completions", ok("ok")]]);
  await chatIA(MENSAJES, "s", { config: config({ compatUrl: "api.openai.com", compatModelo: "gpt-5-mini", compatKey: "k" }), fetchFn: f });
  const { cuerpo, url } = f.llamadas[0];
  assert.equal(url, "https://api.openai.com/v1/chat/completions");
  assert.equal(cuerpo.max_completion_tokens, 512);
  assert.ok(!("max_tokens" in cuerpo) && !("temperature" in cuerpo));
});

test("errores claros: sin URL, clave rechazada, servidor apagado", async () => {
  const nada = fetchFalso([]);
  await assert.rejects(chatIA(MENSAJES, "s", { config: config({ compatUrl: "" }), fetchFn: nada }), /compat_url/);
  assert.equal(nada.llamadas.length, 0);                       // tampoco a OpenRouter
  const f401 = fetchFalso([["/chat/completions", respuesta(401, { error: "bad key" })]]);
  await assert.rejects(chatIA(MENSAJES, "s", { config: config(), fetchFn: f401 }), /rechazo la clave/);
  const apagado = async () => { const e = new TypeError("fetch failed"); e.cause = { code: "ECONNREFUSED" }; throw e; };
  await assert.rejects(chatIA(MENSAJES, "s", { config: config(), fetchFn: apagado }), /No pude conectar con localhost/);
});

test("openrouter y ollama siguen igual", async () => {
  const f = fetchFalso([["openrouter.ai/api/v1/chat/completions", ok("nube")]]);
  assert.equal(await chatIA(MENSAJES, "s", { config: config({ proveedor: "openrouter" }), fetchFn: f }), "nube");
  assert.equal(f.llamadas[0].opciones.headers.Authorization, "Bearer or-clave");
  const o = fetchFalso([["localhost:11434/api/chat", respuesta(200, { message: { content: "local" } })]]);
  assert.equal(await chatIA(MENSAJES, "s", { config: config({ proveedor: "ollama", ollamaModel: "m" }), fetchFn: o }), "local");
});

test("descripcionModelo dice la API compatible", () => {
  assert.equal(descripcionModelo(config()), "qwen2.5-7b · API compatible en localhost");
  assert.equal(descripcionModelo(config({ compatModelo: "" })), "el primero de /models · API compatible en localhost");
  assert.equal(descripcionModelo(config({ proveedor: "openrouter" })), "openrouter/auto · OpenRouter");
});
