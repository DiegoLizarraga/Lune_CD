"""
lune_core/chat_remota.py — El chat del host visto desde un terminal (la app).

Expone la MISMA superficie que usa AIWorker de AIManager (`chat(...)` y `uso()`),
pero cada mensaje viaja por el hub al host, que corre el modelo, la memoria y las
herramientas. Así, en modo terminal, la app no carga ningún modelo: solo pinta lo
que el host va enviando. Si el host se cae, main.py vuelve al AIManager local.
"""
from __future__ import annotations

import asyncio
from typing import Callable, List, Optional


class ChatRemoto:
    """Adaptador con forma de AIManager que enruta el chat al host por el hub."""

    # main.py hace `if provider in self.ai_manager.providers`: vacío = no aplica.
    providers: dict = {}

    def __init__(self, cliente_en_hilo):
        self.cliente = cliente_en_hilo
        self._ultimo_uso: dict = {}

    @property
    def conectado(self) -> bool:
        return bool(self.cliente and self.cliente.conectado)

    async def chat(self, message: str, system_prompt: str = "",
                   provider: Optional[str] = None, on_token: Callable = None,
                   imagenes: Optional[List[str]] = None, *,
                   origen: Optional[str] = None, efimero: bool = False) -> str:
        """
        El `system_prompt` se ignora a propósito: lo arma el host con SU memoria,
        emociones y herramientas. Aquí solo mandamos el texto y las imágenes, y
        el origen (un turno con texto de terceros también lo es en el host) y si
        es efímero (el host no lo guarda en la conversación).
        """
        loop = asyncio.get_running_loop()
        extra = {}
        if origen is not None:
            extra["origen"] = origen
        if efimero:
            extra["efimero"] = True

        def trabajo():
            return self.cliente.chat_remoto_sync(
                message, imagenes=imagenes, on_delta=on_token,
                provider=provider, timeout=180.0, **extra)

        try:
            res = await loop.run_in_executor(None, trabajo)
        except Exception as e:
            from servicios.ai_manager import redactar_secretos
            return f"Error: no pude hablar con el host ({redactar_secretos(e)})."
        self._ultimo_uso = res.get("usage", {}) or {}
        return res.get("text", "") or "Sin respuesta"

    def uso(self, provider: Optional[str] = None) -> dict:
        return self._ultimo_uso

    # Compatibilidad con llamadas que AIManager sí tiene (no-ops aquí).
    def reload_provider(self, provider_id: str = None):
        pass

    def clear_history(self, provider: Optional[str] = None):
        pass

    def cargar_historial(self, mensajes):
        pass
