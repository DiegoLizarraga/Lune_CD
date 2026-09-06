"""
lune_core/servicio_chat.py — El chat de Lune, servido por el host (el "agente").

Hasta ahora cada terminal (la app, el bot, el navegador) llamaba a Ollama por su
cuenta. Con esto, el HOST corre el modelo una sola vez y sirve la conversación a
todos por el hub: reciben el mismo cerebro, la misma memoria y —si el host las
tiene activadas— las mismas herramientas de escritorio (9.5).

Atiende:
    input:text {text, images?, provider?}
      → output:chat:delta {text}     (varias veces, streaming)
      → output:chat:act   {emotion, intensity, motion?}   (por cada <|ACT|>)
      → output:chat:done  {text, usage, acts, tools}

Reutiliza el AIManager de la app (mismos proveedores y ajustes), la memoria del
host (para el contexto y para persistir) y, opcionalmente, el ToolManager y el
servicio de notas (RAG). Es el equivalente de ServicioMemoria para el chat.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from .hub import Hub, Peer
from .protocolo import Evento, Tipo
from . import marcadores
from .prompt import GRAMATICA_EMOCIONES

# Mismas reglas que inyecta la app (ai_worker.py), aquí sin depender de Qt.
REGLAS_HERRAMIENTAS = (
    "\n\n=========================================\n"
    "REGLAS DE HERRAMIENTAS DE ESCRITORIO:\n"
    "Puedes ejecutar acciones en el PC del usuario si lo consideras necesario. "
    "Para hacerlo, DEBES incluir uno de los siguientes comandos exactamente al FINAL de tu respuesta:\n\n"
    "1. Para buscar en Google o Youtube:\n   ABRIR_BUSQUEDA:[términos]\n"
    "2. Para abrir una URL:\n   ABRIR_URL:[url completa con https://]\n"
    "3. Para lanzar una app:\n   TOOL:lanzar_app:[nombre_del_programa]\n"
    "4. Para verificar info del PC:\n   TOOL:sistema_info:\n"
)


class ServicioChat:
    def __init__(self, hub: Hub, ai_manager, memoria=None, tools=None, notas=None,
                 provider_por_defecto: str = "ollama", persona=None):
        self.hub = hub
        self.ai = ai_manager
        self.memoria = memoria
        self.tools = tools
        self.notas = notas
        self.provider_por_defecto = provider_por_defecto
        self._persona = persona          # str o callable → persona base del system prompt
        hub.registrar(Tipo.INPUT_TEXT, self._on_input)

    # ── System prompt (persona + memoria + herramientas + emociones + RAG) ──────
    def _system(self, texto_usuario: str) -> str:
        base = self._persona() if callable(self._persona) else (self._persona or "")
        partes = [base] if base else []
        try:
            ctx = self.memoria.obtener_contexto_para_prompt() if self.memoria else ""
        except Exception:
            ctx = ""
        if ctx:
            partes.append("CONTEXTO DE MEMORIA DEL USUARIO:\n" + ctx)
        if self.tools is not None:
            partes.append(REGLAS_HERRAMIENTAS)
        partes.append(GRAMATICA_EMOCIONES)
        if self.notas is not None and getattr(self.notas, "activo", False):
            try:
                frags = self.notas.contexto_para(texto_usuario)
                if frags:
                    from .prompt import bloque_contexto
                    partes.append(bloque_contexto(frags))
            except Exception:
                pass
        return "\n\n".join(p for p in partes if p)

    def _provider(self, pedido: Optional[str]) -> str:
        """Usa el proveedor pedido si el host lo tiene disponible; si no, el suyo."""
        try:
            provs = getattr(self.ai, "providers", {})
            if pedido and pedido in provs and provs[pedido].is_available():
                return pedido
        except Exception:
            pass
        return self.provider_por_defecto

    # ── Manejo del chat ─────────────────────────────────────────────────────────
    async def _on_input(self, ev: Evento, peer: Peer):
        text = str(ev.data.get("text") or "")
        if not text.strip():
            await self.hub.responder(peer, Tipo.OUTPUT_DONE, {"text": "", "usage": {}}, ev)
            return
        imagenes = ev.data.get("images") or []
        provider = self._provider(ev.data.get("provider"))
        system = self._system(text)
        loop = asyncio.get_running_loop()

        self.hub.estado_extra["busy"] = True
        await self.hub.publicar(Tipo.HOST_STATUS, self.hub.estado())

        # Streaming con batching: agrupa tokens para no saturar la red con
        # un mensaje por carácter. El modelo escupe desde un hilo del executor,
        # así que se agenda el envío en el bucle del hub de forma segura.
        pend = {"buf": "", "last": time.monotonic()}

        def on_token(tok: str):
            pend["buf"] += tok
            ahora = time.monotonic()
            if len(pend["buf"]) >= 24 or (ahora - pend["last"]) > 0.12:
                chunk, pend["buf"], pend["last"] = pend["buf"], "", ahora
                asyncio.run_coroutine_threadsafe(
                    self.hub.responder(peer, Tipo.OUTPUT_DELTA, {"text": chunk}, ev), loop)

        try:
            texto = await self.ai.chat(text, system, provider=provider,
                                       on_token=on_token, imagenes=imagenes)
        except Exception as e:
            texto = f"Error del host al generar la respuesta: {e}"

        if pend["buf"]:      # lo que quedó sin enviar
            await self.hub.responder(peer, Tipo.OUTPUT_DELTA, {"text": pend["buf"]}, ev)

        # Emociones: separa marcadores y emite un ACT por cada uno.
        hablable, control = marcadores.separar(texto)
        acts = [v for c, v in control if c == "act"]
        for a in acts:
            await self.hub.responder(peer, Tipo.OUTPUT_ACT, a, ev)

        # Herramientas de escritorio, ejecutadas EN EL HOST. Se parte del texto
        # YA sin marcadores de emoción (hablable), para no reintroducirlos.
        texto_final = hablable
        resultados_tools = []
        if self.tools is not None:
            try:
                limpio, comandos = self.tools.parsear_respuesta_ia(hablable)
                texto_final = limpio if limpio is not None else hablable
                for cmd in comandos:
                    herr = cmd.pop("herramienta", None)
                    if herr:
                        r = self.tools.ejecutar(herr, **cmd)
                        resultados_tools.append({"ok": bool(r.ok), "mensaje": r.mensaje})
            except Exception:
                pass

        # Persistir en la memoria del host (sesión, resumen…).
        try:
            if self.memoria:
                self.memoria.procesar_respuesta_lune(texto)
        except Exception:
            pass

        try:
            usage = self.ai.uso(provider)
        except Exception:
            usage = {}

        self.hub.estado_extra["busy"] = False
        await self.hub.publicar(Tipo.HOST_STATUS, self.hub.estado())
        await self.hub.responder(peer, Tipo.OUTPUT_DONE,
                                 {"text": texto_final, "usage": usage,
                                  "acts": acts, "tools": resultados_tools}, ev)
