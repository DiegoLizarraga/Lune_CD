"""
lune_core/memoria_remota.py — La memoria del host vista desde un terminal.

Expone la misma superficie que usa main.py de `MemoriaManager`, pero cada
llamada va al hub. Si el host no está (aún) conectado, cae al respaldo local
SIN esperar: un timeout de red por cada mensaje congelaría la interfaz.
"""
from __future__ import annotations

from typing import Any, Optional

from .cliente import ClienteEnHilo
from .protocolo import Tipo


class MemoriaRemota:
    def __init__(self, cliente: ClienteEnHilo, respaldo, timeout: float = 8.0):
        self.cliente = cliente
        self.respaldo = respaldo        # MemoriaManager local
        self.timeout = timeout
        self.ultimo_error: Optional[str] = None

    @property
    def conectado(self) -> bool:
        return self.cliente.conectado

    # ── Transporte ─────────────────────────────────────────────────────────────

    def _pedir(self, tipo, data: dict) -> Any:
        """Devuelve `resultado` de memory:result, o None si no se pudo."""
        if not self.cliente.conectado:
            self.ultimo_error = "sin conexión con el host"
            return None
        try:
            ev = self.cliente.pedir_sync(tipo, data, timeout=self.timeout)
        except Exception as e:  # timeout, conexión perdida
            self.ultimo_error = str(e)
            return None
        self.ultimo_error = ev.data.get("error")
        return ev.data.get("resultado")

    def _consultar(self, que: str) -> Any:
        return self._pedir(Tipo.MEMORY_QUERY, {"que": que})

    # ── Superficie compatible con MemoriaManager ───────────────────────────────

    def procesar_mensaje_usuario(self, mensaje: str) -> Optional[str]:
        if not self.cliente.conectado:
            return self.respaldo.procesar_mensaje_usuario(mensaje)
        return self._pedir(Tipo.MEMORY_REMEMBER, {"mensaje": mensaje})

    def obtener_contexto_para_prompt(self) -> str:
        r = self._consultar("contexto")
        return r if isinstance(r, str) else self.respaldo.obtener_contexto_para_prompt()

    def get_nombre_usuario(self) -> Optional[str]:
        if not self.cliente.conectado:
            return self.respaldo.get_nombre_usuario()
        return self._consultar("nombre")

    def get_stats(self) -> dict:
        r = self._consultar("stats")
        return r if isinstance(r, dict) else self.respaldo.get_stats()

    def get_todos_recuerdos(self) -> list:
        r = self._consultar("todo")
        if isinstance(r, dict) and isinstance(r.get("recuerdos"), list):
            return r["recuerdos"]
        return self.respaldo.get_todos_recuerdos()

    def _cmd_listar(self) -> str:
        r = self._consultar("listar")
        if isinstance(r, str):
            return r
        return "No pude leer la memoria del host. " + self.respaldo._cmd_listar()

    def agregar_recuerdo(self, contenido: str, tipo: str = "general", tags=None) -> Optional[str]:
        r = self._pedir(Tipo.MEMORY_REMEMBER, {"mensaje": f"recuerda que {contenido}"})
        return r if r is not None else self.respaldo.agregar_recuerdo(contenido, tipo, tags)

    def procesar_respuesta_lune(self, respuesta: str):
        # El host persiste por su cuenta; aquí no hay nada que volcar.
        pass

    def cerrar_sesion(self, resumen: str = ""):
        # La sesión (estadísticas, resumen) vive en el host.
        pass
