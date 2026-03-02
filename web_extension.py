import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import webbrowser
import threading
import re
from datetime import datetime

API_KEY = "la api de ia"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-3.5-turbo"

SYSTEM_PROMPT = """Eres Lune Cd, un asistente lunar AI amigable y carismatica que habla español.

REGLAS PARA ABRIR EL NAVEGADOR:
Cuando el usuario pida abrir, buscar, investigar, ver, o navegar a algo en internet, DEBES incluir al final de tu respuesta uno de estos comandos:

- Para buscar en Google: ABRIR_BUSQUEDA:[términos de búsqueda optimizados para Google]
- Para abrir un sitio web específico: ABRIR_URL:[url completa con https://]

Ejemplos:
- Usuario: "abre en navegador una ventana investigando sobre la revolución francesa"
  → Tu respuesta termina con: ABRIR_BUSQUEDA:revolución francesa causas consecuencias historia

- Usuario: "busca los mejores restaurantes de sushi en sinaloa"
  → Tu respuesta termina con: ABRIR_BUSQUEDA:mejores restaurantes sushi sinaloa

- Usuario: "ábre youtube"
  → Tu respuesta termina con: ABRIR_URL:https://www.youtube.com

- Usuario: "ve a wikipedia a buscar sobre Albert Einstein"
  → Tu respuesta termina con: ABRIR_URL:https://es.wikipedia.org/wiki/Albert_Einstein

IMPORTANTE:
- Coloca el comando siempre al FINAL de tu respuesta, en una línea separada
- Solo incluye estos comandos cuando el usuario pida explícitamente abrir o buscar en internet
- NO generes páginas HTML, solo abre Google o el sitio pedido"""

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lune Cd</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg-dark:    #0d1b2e;
    --bg-mid:     #112240;
    --bg-header:  #0f2035;
    --bubble-bot: #1a3a5c;
    --bubble-user:#1565c0;
    --accent:     #4fc3f7;
    --accent2:    #29b6f6;
    --text:       #e8f4fd;
    --muted:      #7bacc4;
    --border:     #1e3a52;
    --online:     #4caf50;
    --input-bg:   #0f2035;
  }

  html, body {
    height: 100%;
    background: var(--bg-dark);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    overflow: hidden;
  }

  /* Background subtle gradient like in the screenshot */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse at 20% 50%, rgba(21,101,192,0.15) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 20%, rgba(13,71,161,0.12) 0%, transparent 50%),
      linear-gradient(180deg, #0d1b2e 0%, #0a1628 100%);
    pointer-events: none;
    z-index: 0;
  }

  .app {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  /* ── HEADER ── */
  header {
    background: var(--bg-header);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .avatar-header {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    background: linear-gradient(135deg, #1565c0, #42a5f5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    flex-shrink: 0;
    box-shadow: 0 0 16px rgba(66,165,245,0.35);
  }

  .header-info h1 {
    font-size: 22px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.3px;
  }

  .header-info p {
    font-size: 13px;
    color: var(--muted);
    font-weight: 400;
    margin-top: 1px;
  }

  .status-badge {
    display: flex;
    align-items: center;
    gap: 7px;
    background: rgba(76,175,80,0.12);
    border: 1px solid rgba(76,175,80,0.3);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    color: #81c784;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    background: var(--online);
    border-radius: 50%;
    box-shadow: 0 0 6px var(--online);
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(0.85); }
  }

  /* ── CHAT AREA ── */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 24px 16px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    scroll-behavior: smooth;
  }

  #chat::-webkit-scrollbar { width: 4px; }
  #chat::-webkit-scrollbar-track { background: transparent; }
  #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  /* Message row */
  .msg-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    animation: fadeUp 0.25s ease;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .msg-row.user-row {
    flex-direction: row-reverse;
  }

  /* Bot avatar in chat */
  .msg-avatar {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: linear-gradient(135deg, #1565c0, #42a5f5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 17px;
    flex-shrink: 0;
    margin-bottom: 2px;
    box-shadow: 0 0 10px rgba(66,165,245,0.25);
  }

  .msg-avatar.hidden { visibility: hidden; }

  /* Bubble */
  .bubble {
    max-width: 58%;
    padding: 11px 15px;
    border-radius: 18px;
    font-size: 15px;
    line-height: 1.55;
    position: relative;
  }

  .bubble.bot {
    background: var(--bubble-bot);
    border-bottom-left-radius: 4px;
    color: var(--text);
  }

  .bubble.user {
    background: var(--bubble-user);
    border-bottom-right-radius: 4px;
    color: #fff;
    align-self: flex-end;
  }

  .bubble .time {
    font-size: 11px;
    color: var(--muted);
    margin-top: 5px;
    text-align: right;
    opacity: 0.7;
  }

  /* Browser action tag inside bubble */
  .browser-tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 8px;
    padding: 5px 11px;
    background: rgba(79,195,247,0.12);
    border: 1px solid rgba(79,195,247,0.3);
    border-radius: 8px;
    font-size: 12px;
    color: var(--accent);
    font-weight: 500;
  }

  /* Typing indicator */
  .typing-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
  }

  .typing-bubble {
    background: var(--bubble-bot);
    border-radius: 18px;
    border-bottom-left-radius: 4px;
    padding: 13px 18px;
    display: flex;
    gap: 5px;
    align-items: center;
  }

  .typing-bubble span {
    width: 7px; height: 7px;
    background: var(--muted);
    border-radius: 50%;
    animation: typingBounce 1.2s infinite;
  }
  .typing-bubble span:nth-child(2) { animation-delay: 0.2s; }
  .typing-bubble span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes typingBounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
    40% { transform: translateY(-6px); opacity: 1; }
  }

  /* ── FOOTER INPUT ── */
  footer {
    padding: 12px 16px 16px;
    flex-shrink: 0;
  }

  .input-wrap {
    display: flex;
    align-items: center;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 30px;
    padding: 8px 8px 8px 20px;
    gap: 10px;
    transition: border-color 0.2s;
  }

  .input-wrap:focus-within {
    border-color: rgba(79,195,247,0.5);
    box-shadow: 0 0 0 3px rgba(79,195,247,0.07);
  }

  #input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 15px;
  }

  #input::placeholder { color: var(--muted); }

  #sendBtn {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: linear-gradient(135deg, #1565c0, #42a5f5);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition: transform 0.15s, opacity 0.2s;
    box-shadow: 0 2px 10px rgba(66,165,245,0.4);
  }

  #sendBtn:hover { transform: scale(1.08); }
  #sendBtn:active { transform: scale(0.95); }
  #sendBtn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

  #sendBtn svg {
    width: 18px; height: 18px;
    fill: white;
    transform: translateX(1px);
  }
</style>
</head>
<body>
<div class="app">

  <!-- HEADER -->
  <header>
    <div class="header-left">
      <div class="avatar-header">🌙</div>
      <div class="header-info">
        <h1>Lune Cd web extension</h1>
        <p>Asistente AI del dia a dia</p>
      </div>
    </div>
    <div class="status-badge">
      <div class="status-dot"></div>
      En línea
    </div>
  </header>

  <!-- CHAT -->
  <div id="chat">
    <!-- Welcome message -->
    <div class="msg-row" id="welcome-row">
      <div class="msg-avatar">🌙</div>
      <div class="bubble bot">
        ¡Hola! Soy Lune Cd, tu asistente en su version de la web :D ¿En qué puedo ayudarte hoy?
        <div class="time" id="welcome-time"></div>
      </div>
    </div>
  </div>

  <!-- FOOTER -->
  <footer>
    <div class="input-wrap">
      <input id="input" type="text" placeholder="Escribe tu mensaje..." autocomplete="off" />
      <button id="sendBtn" onclick="sendMessage()">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  </footer>

</div>

<script>
  const chat = document.getElementById('chat');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const history = [];

  // Set welcome time
  document.getElementById('welcome-time').textContent = getTime();

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) sendMessage();
  });

  function getTime() {
    const now = new Date();
    return now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
  }

  function addBotMessage(text, browserAction = null, showAvatar = true) {
    const row = document.createElement('div');
    row.className = 'msg-row';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar' + (showAvatar ? '' : ' hidden');
    avatar.textContent = '🌙';

    const bubble = document.createElement('div');
    bubble.className = 'bubble bot';
    bubble.innerHTML = text.replace(/\\n/g, '<br>');

    if (browserAction) {
      const tag = document.createElement('div');
      tag.className = 'browser-tag';
      tag.innerHTML = browserAction.type === 'search'
        ? '🔍 Buscando: <em>"' + browserAction.query + '"</em>'
        : '🌐 Abriendo: <em>' + browserAction.url + '</em>';
      bubble.appendChild(document.createElement('br'));
      bubble.appendChild(tag);
    }

    const timeEl = document.createElement('div');
    timeEl.className = 'time';
    timeEl.textContent = getTime();
    bubble.appendChild(timeEl);

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return row;
  }

  function addUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'msg-row user-row';

    const bubble = document.createElement('div');
    bubble.className = 'bubble user';
    bubble.textContent = text;

    const timeEl = document.createElement('div');
    timeEl.className = 'time';
    timeEl.textContent = getTime();
    bubble.appendChild(timeEl);

    row.appendChild(bubble);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
  }

  function addTyping() {
    const row = document.createElement('div');
    row.className = 'typing-row';
    row.id = 'typing-row';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = '🌙';

    const bubble = document.createElement('div');
    bubble.className = 'typing-bubble';
    bubble.innerHTML = '<span></span><span></span><span></span>';

    row.appendChild(avatar);
    row.appendChild(bubble);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
    return row;
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addUserMessage(text);
    history.push({ role: 'user', content: text });
    input.value = '';
    sendBtn.disabled = true;

    const typing = addTyping();

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history })
      });
      const data = await res.json();
      typing.remove();

      const reply = data.reply || 'Sin respuesta.';
      const browserAction = data.browser_action || null;

      addBotMessage(reply, browserAction);
      history.push({ role: 'assistant', content: reply });

    } catch (err) {
      typing.remove();
      addBotMessage('Error al conectar con el servidor.');
    }

    sendBtn.disabled = false;
    input.focus();
  }
</script>
</body>
</html>
"""


class ChatHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/chat':
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length))
            messages = body.get('messages', [])

            reply, browser_action = call_api(messages)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps(
                {'reply': reply, 'browser_action': browser_action},
                ensure_ascii=False
            )
            self.wfile.write(response.encode('utf-8'))


def call_api(messages):
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "max_tokens": 800,
        "temperature": 0.7
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
            "HTTP-Referer": "http://localhost:8080",
            "X-Title": "Lune Cd"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode('utf-8'))
            raw_reply = data['choices'][0]['message']['content']

            browser_action = None

            # Detectar ABRIR_BUSQUEDA
            match_search = re.search(r'ABRIR_BUSQUEDA:(.+?)(?:\n|$)', raw_reply)
            if match_search:
                query = match_search.group(1).strip()
                raw_reply = raw_reply.replace(match_search.group(0), '').strip()
                search_url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
                webbrowser.open(search_url)
                browser_action = {"type": "search", "query": query}

            # Detectar ABRIR_URL
            match_url = re.search(r'ABRIR_URL:(https?://\S+)', raw_reply)
            if match_url:
                url = match_url.group(1).strip()
                raw_reply = raw_reply.replace(match_url.group(0), '').strip()
                webbrowser.open(url)
                browser_action = {"type": "url", "url": url}

            return raw_reply.strip(), browser_action

    except Exception as e:
        return "Error al conectar con la API: " + str(e), None


def main():
    PORT = 8080
    print("\n🌙 Lune Cd iniciado")
    print("📌 Abriendo en: http://localhost:" + str(PORT))
    print("⏹  Presiona Ctrl+C para detener\n")

    threading.Timer(1.0, lambda: webbrowser.open("http://localhost:" + str(PORT))).start()

    with socketserver.TCPServer(("", PORT), ChatHandler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✅ Lune Cd detenido.")


if __name__ == "__main__":
    main()