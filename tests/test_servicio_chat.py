"""
Tests del agente de chat servido por el host (lune_core/servicio_chat.py).

Loopback real: un Hub con ServicioChat (modelo/memoria/herramientas simulados) y
un Cliente que envía input:text y recibe el streaming, la emoción y el done. Así
se valida que "el terminal chatea vía el host" sin necesitar dos equipos.
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core.hub import Hub  # noqa: E402
from lune_core.cliente import Cliente  # noqa: E402
from lune_core.servicio_chat import ServicioChat  # noqa: E402
from lune_core import protocolo as P  # noqa: E402

TOKEN = "secreto-de-prueba"


def correr(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=20))


class FakeAI:
    """Modelo simulado: escupe por tokens un texto con emoción y una tool."""
    providers = {}

    def __init__(self):
        self.system = ""

    async def chat(self, message, system_prompt="", provider=None, on_token=None, imagenes=None):
        self.system = system_prompt
        texto = ('Hola <|ACT {"emotion":"happy","intensity":0.9}|>, ¿todo bien?\n'
                 'ABRIR_URL:https://example.com')
        for i in range(0, len(texto), 6):
            if on_token:
                on_token(texto[i:i + 6])
            await asyncio.sleep(0)
        return texto

    def uso(self, provider):
        return {"total": 7, "local": True}


class FakeMem:
    def __init__(self):
        self.persistido = []

    def obtener_contexto_para_prompt(self):
        return "El usuario se llama Diego."

    def procesar_respuesta_lune(self, t):
        self.persistido.append(t)


class FakeTools:
    def __init__(self):
        self.ejecutadas = []

    def parsear_respuesta_ia(self, resp):
        m = re.search(r'ABRIR_URL:(https?://\S+)', resp)
        limpio = re.sub(r'ABRIR_URL:https?://\S+', '', resp).strip()
        return limpio, ([{"herramienta": "abrir_url", "args": m.group(1)}] if m else [])

    def ejecutar(self, herramienta, **kw):
        self.ejecutadas.append((herramienta, kw))

        class R:
            ok = True
            mensaje = f"abrí {kw.get('args')}"
        return R()


def test_el_host_sirve_chat_con_streaming_emocion_y_tool():
    async def caso():
        hub = Hub(TOKEN, host="127.0.0.1", puerto=0)
        mem, tools, ai = FakeMem(), FakeTools(), FakeAI()
        ServicioChat(hub, ai, memoria=mem, tools=tools,
                     provider_por_defecto="ollama", persona="Eres Lune.")
        await hub.iniciar()

        eventos = []
        cli = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "term", "web",
                      on_evento=eventos.append)
        try:
            assert await cli.conectar(reintentar=False)
            ev = await cli.enviar(P.Tipo.INPUT_TEXT, {"text": "hola"})

            done = None
            for _ in range(300):
                done = next((e for e in eventos if e.type == "output:chat:done"
                             and e.meta.parent_id == ev.meta.id), None)
                if done:
                    break
                await asyncio.sleep(0.02)
            assert done is not None, "el host no cerró el chat (output:chat:done)"

            deltas = [e for e in eventos if e.type == "output:chat:delta"
                      and e.meta.parent_id == ev.meta.id]
            assert deltas, "no llegó streaming (output:chat:delta)"
            assert "Hola" in "".join(e.data["text"] for e in deltas)

            acts = [e for e in eventos if e.type == "output:chat:act"]
            assert acts and acts[0].data.get("emotion") == "happy"

            # el done trae el texto limpio (sin marcador ni el comando de tool)
            assert "ACT" not in done.data["text"] and "ABRIR_URL" not in done.data["text"]
            assert done.data["usage"].get("total") == 7

            # la herramienta se ejecutó EN EL HOST
            assert tools.ejecutadas and tools.ejecutadas[0][0] == "abrir_url"
            # el host persistió la respuesta en SU memoria
            assert mem.persistido
            # el system prompt del host llevó memoria del host + gramática de emociones
            assert "Diego" in ai.system and "emotion" in ai.system.lower()
        finally:
            await cli.cerrar()
            await hub.detener()

    correr(caso())


def test_texto_vacio_devuelve_done_sin_reventar():
    async def caso():
        hub = Hub(TOKEN, host="127.0.0.1", puerto=0)
        ServicioChat(hub, FakeAI(), memoria=FakeMem(), persona="Eres Lune.")
        await hub.iniciar()
        eventos = []
        cli = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "t", "web", on_evento=eventos.append)
        try:
            assert await cli.conectar(reintentar=False)
            ev = await cli.enviar(P.Tipo.INPUT_TEXT, {"text": "   "})
            done = None
            for _ in range(100):
                done = next((e for e in eventos if e.type == "output:chat:done"
                             and e.meta.parent_id == ev.meta.id), None)
                if done:
                    break
                await asyncio.sleep(0.02)
            assert done is not None and done.data["text"] == ""
        finally:
            await cli.cerrar()
            await hub.detener()

    correr(caso())


# ── Puente síncrono: la app (ClienteEnHilo + ChatRemoto) habla con el host ──────

def test_chat_remoto_desde_la_app_por_hilos(tmp_path):
    """
    Como la app real: hub en un hilo con ServicioChat, y un ClienteEnHilo que usa
    ChatRemoto.chat() (la misma superficie que AIManager). Verifica streaming y texto.
    """
    from lune_core.hub import Hub, HubEnHilo
    from lune_core.cliente import ClienteEnHilo
    from lune_core.chat_remota import ChatRemoto

    ai = FakeAI()
    hub = Hub(TOKEN, host="127.0.0.1", puerto=0)
    hub_hilo = HubEnHilo(hub, servicios=lambda h: ServicioChat(
        h, ai, memoria=FakeMem(), tools=FakeTools(), persona="Eres Lune."))
    assert hub_hilo.iniciar(timeout=5)
    try:
        cli = ClienteEnHilo(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "app-test", "app",
                            eventos_emitidos=["input:text"])
        assert cli.iniciar(timeout=6)
        try:
            remoto = ChatRemoto(cli)
            trozos = []
            texto = asyncio.run(remoto.chat("hola", on_token=trozos.append))
            assert "todo bien" in texto            # texto final (limpio) del host
            assert "".join(trozos)                 # llegó streaming por on_token
            assert remoto.uso().get("total") == 7  # el uso lo reporta el host
        finally:
            cli.detener()
    finally:
        hub_hilo.detener()
