"""
lune_core/servicio_memoria.py — La memoria de Lune, servida por el hub.

Envuelve `memoria.MemoriaManager` (que no cambia) y lo expone por eventos, de
modo que la app en modo terminal y el bot de Telegram lean y escriban LA MISMA
memoria.json: la del host. Hasta ahora cada equipo tenía su copia y divergían.

Eventos que atiende:
    memory:query    {que: "contexto"|"listar"|"nombre"|"stats"|"todo"}
                    → memory:result {que, resultado}
    memory:remember {mensaje}   ← el texto del usuario, tal cual; se procesa igual
                    → memory:result {que:"remember", resultado: str|None}
    memory:forget   {id} | {id:"todo"}
                    → memory:result {que:"forget", resultado: str}
Tras cualquier cambio difunde memory:changed {motivo} a todos los peers.
"""
from __future__ import annotations

from typing import Any

from .hub import Hub, Peer
from .protocolo import Evento, Tipo


class ServicioMemoria:
    def __init__(self, hub: Hub, memoria):
        self.hub = hub
        self.memoria = memoria
        hub.registrar(Tipo.MEMORY_QUERY, self._on_query)
        hub.registrar(Tipo.MEMORY_REMEMBER, self._on_remember)
        hub.registrar(Tipo.MEMORY_FORGET, self._on_forget)
        hub.registrar(Tipo.MEMORY_SET, self._on_set)

    # ── Consultas ──────────────────────────────────────────────────────────────

    def consultar(self, que: str) -> Any:
        m = self.memoria
        if que == "contexto":
            return m.obtener_contexto_para_prompt()
        if que == "listar":
            return m._cmd_listar()
        if que == "nombre":
            return m.get_nombre_usuario()
        if que == "stats":
            return m.get_stats()
        if que == "todo":
            return {"nombre": m.get_nombre_usuario(), "stats": m.get_stats(),
                    "recuerdos": m.get_todos_recuerdos()}
        raise ValueError(f"consulta desconocida: {que}")

    async def _on_query(self, ev: Evento, peer: Peer):
        que = str(ev.data.get("que") or "contexto")
        try:
            resultado = self.consultar(que)
        except ValueError as e:
            await self.hub.responder(peer, Tipo.MEMORY_RESULT,
                                     {"que": que, "resultado": None, "error": str(e)}, ev)
            return
        await self.hub.responder(peer, Tipo.MEMORY_RESULT, {"que": que, "resultado": resultado}, ev)

    # ── Escrituras ─────────────────────────────────────────────────────────────

    async def _on_remember(self, ev: Evento, peer: Peer):
        mensaje = str(ev.data.get("mensaje") or "")
        antes = self._huella()
        respuesta = self.memoria.procesar_mensaje_usuario(mensaje) if mensaje else None
        await self.hub.responder(peer, Tipo.MEMORY_RESULT,
                                 {"que": "remember", "resultado": respuesta}, ev)
        if self._huella() != antes:
            await self.hub.publicar(Tipo.MEMORY_CHANGED, {"motivo": "remember", "por": peer.name})

    async def _on_forget(self, ev: Evento, peer: Peer):
        objetivo = str(ev.data.get("id") or "").strip()
        if not objetivo:
            resultado = "Dime qué olvidar: un id o «todo»."
        elif objetivo.lower() == "todo":
            resultado = self.memoria._cmd_olvida_todo()
        else:
            resultado = self.memoria._cmd_olvida(objetivo)
        await self.hub.responder(peer, Tipo.MEMORY_RESULT, {"que": "forget", "resultado": resultado}, ev)
        await self.hub.publicar(Tipo.MEMORY_CHANGED, {"motivo": "forget", "por": peer.name})

    async def _on_set(self, ev: Evento, peer: Peer):
        """
        Pares clave/valor (lo que el bot extrae con [MEMORIA: {...}]). `nombre`
        va al usuario; el resto a datos_clave. Con `reemplazar`, se vacía
        datos_clave antes (es el /olvidar del bot, que no toca los recuerdos).
        """
        datos = ev.data.get("datos") or {}
        if not isinstance(datos, dict):
            datos = {}
        d = self.memoria._data
        if ev.data.get("reemplazar"):
            d["datos_clave"] = {}
        for clave, valor in datos.items():
            clave = str(clave).strip()
            if not clave:
                continue
            if clave.lower() == "nombre":
                d.setdefault("usuario", {})["nombre"] = str(valor) if valor else None
            else:
                d.setdefault("datos_clave", {})[clave] = str(valor)
        self.memoria._guardar()
        await self.hub.responder(peer, Tipo.MEMORY_RESULT, {"que": "set", "resultado": True}, ev)
        await self.hub.publicar(Tipo.MEMORY_CHANGED, {"motivo": "set", "por": peer.name})

    def _huella(self) -> tuple:
        """Algo barato que cambia si la memoria cambió (para no difundir en vano)."""
        d = self.memoria._data
        return (d.get("usuario", {}).get("nombre"), len(d.get("recuerdos", [])),
                tuple(sorted(d.get("datos_clave", {}).items())))
