// Búsqueda con DuckDuckGo — sin API key, sin registro, 100% gratis

export async function buscarWeb(query) {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}&kl=es-es`;

  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
      "Accept-Language": "es-ES,es;q=0.9",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
  });

  if (!response.ok) {
    throw new Error(`DuckDuckGo error ${response.status}`);
  }

  const html = await response.text();

  const resultados = [];
  const tituloRegex = /<a[^>]+class="result__a"[^>]*>(.*?)<\/a>/gs;
  const snippetRegex = /<a[^>]+class="result__snippet"[^>]*>(.*?)<\/a>/gs;
  const urlRegex = /<a[^>]+class="result__url"[^>]*>(.*?)<\/a>/gs;

  const titulos = [...html.matchAll(tituloRegex)].map(m => limpiarHtml(m[1]));
  const snippets = [...html.matchAll(snippetRegex)].map(m => limpiarHtml(m[1]));
  const urls = [...html.matchAll(urlRegex)].map(m => limpiarHtml(m[1]).trim());

  const total = Math.min(titulos.length, snippets.length, 4);

  for (let i = 0; i < total; i++) {
    if (titulos[i] && snippets[i]) {
      resultados.push(
        `${i + 1}. ${titulos[i]}\n${snippets[i]}${urls[i] ? `\nFuente: ${urls[i]}` : ""}`
      );
    }
  }

  if (resultados.length === 0) {
    return "No se encontraron resultados para esa búsqueda.";
  }

  return resultados.join("\n\n");
}

function limpiarHtml(str) {
  return str
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&nbsp;/g, " ")
    .trim();
}
