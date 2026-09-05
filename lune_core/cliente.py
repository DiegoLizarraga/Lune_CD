"""
lune_core/cliente.py — SDK de terminal: cómo un peer habla con el hub.

Máquina de estados (portada del server-sdk de AIRI):
    idle → connecting → authenticating → announcing → ready
                                   ↘ failed (token inválido: no reintentar)
    ready → reconnecting → connecting …  (backoff exponencial con jitter, tope 30 s)

`Cliente` es asyncio puro. `ClienteEnHilo` lo envuelve para código síncrono
(la app Qt): corre el cliente en su hilo y expone `pedir_sync()` etc.
"""
from __future__ import annotations

import asyncio
import random
import threading
from typing import Any, Callable, Dict, Iterable, Optional

import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI, InvalidHandshake

from . import protocolo as P
from .protocolo import Evento, Fuente, Tipo

OnEvento = Callable[[Evento], None]


def _log(msg: str):
    try:
        from utils import log_info
        log_info(f"[cliente] {msg}")
    except Exception:
        print(f"[cliente] {msg}")


class Cliente:
    def __init__(self, url: str, token: Optional[str], nombre: str, kind: str = "app",
                 eventos_emitidos: Iterable[str] = (), on_evento: Optional[OnEvento] = None,
                 on_estado: Optional[Callable[[str], None]] = None):
        self.url = url.rstrip("/")
        if not self.url.endswith(P.RUTA_WS):
            self.url += P.RUTA_WS
        self.token = token or ""
        self.fuente = Fuente(id=nombre, kind=kind)
        self.eventos_emitidos = list(eventos_emitidos)
        self.on_evento = on_evento
        self.on_estado = on_estado
        self.estado = "idle"
        self.peer_id: Optional[str] = None
        self.peers: list = []
        self._ws = None
        self._pendientes: Dict[str, asyncio.Future] = {}
        self._tarea_ping: Optional[asyncio.Task] = None
        self._tarea_recv: Optional[asyncio.Task] = None
        self._cerrar = False
        self._listo = asyncio.Event()

    # ── Estado ─────────────────────────────────────────────────────────────────

    def _set_estado(self, e: str):
        if e != self.estado:
            self.estado = e
            if self.on_estado:
                try:
                    self.on_estado(e)
                except Exception:
                    pass

    @property
    def conectado(self) -> bool:
        return self.estado == "ready"

    # ── Conexión ───────────────────────────────────────────────────────────────

    async def conectar(self, reintentar: bool = True) -> bool:
        """Conecta y hace el handshake. Con `reintentar`, insiste con backoff."""
        intento = 0
        while not self._cerrar:
            self._set_estado("connecting" if intento == 0 else "reconnecting")
            try:
                ok = await self._conectar_una_vez()
            except _TokenInvalido:
                self._set_estado("failed")
                _log("token inválido: no reintento")
                return False
            if ok:
                return True
            if not reintentar:
                self._set_estado("failed")
                return False
            intento += 1
            espera = min(1.0 * (2 ** (intento - 1)), 30.0)
            espera *= 0.5 + random.random() * 0.5   # jitter con suelo del 50 %
            _log(f"sin conexión con el host; reintento en {espera:.1f} s")
            await asyncio.sleep(espera)
        return False

    async def _conectar_una_vez(self) -> bool:
        try:
            self._ws = await websockets.connect(self.url, ping_interval=None,
                                                max_size=16 * 1024 * 1024, open_timeout=8)
        except (OSError, InvalidURI, InvalidHandshake, asyncio.TimeoutError) as e:
            _log(f"no pude abrir {self.url}: {e}")
            return False

        try:
            self._set_estado("authenticating")
            ev_auth = await self._enviar_crudo(Tipo.AUTH, {"token": self.token})
            resp = await self._esperar_respuesta(ev_auth, timeout=8)
            if resp is None:
                return False
            if resp.type == Tipo.ERROR.value:
                if resp.data.get("code") == P.CodigoError.TOKEN_INVALIDO.value:
                    raise _TokenInvalido()
                return False
            self.peer_id = resp.data.get("peer_id")

            self._set_estado("announcing")
            ev_ann = await self._enviar_crudo(Tipo.ANNOUNCE, {
                "name": self.fuente.id, "kind": self.fuente.kind,
                "events": self.eventos_emitidos,
            })
            resp = await self._esperar_respuesta(ev_ann, timeout=8)
            if resp is None or resp.type != Tipo.PEERS.value:
                return False
            self.peers = resp.data.get("peers", [])
        except _TokenInvalido:
            await self._cerrar_ws()
            raise
        except ConnectionClosed:
            return False

        self._set_estado("ready")
        self._listo.set()
        self._tarea_ping = asyncio.create_task(self._pinger())
        self._tarea_recv = asyncio.create_task(self._bucle_recv())
        _log(f"listo como {self.fuente.id} ({self.peer_id})")
        return True

    async def _esperar_respuesta(self, a: Evento, timeout: float) -> Optional[Evento]:
        """Durante el handshake leemos directamente del socket."""
        try:
            while True:
                mensaje = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
                ev = P.decodificar(mensaje)
                if ev.meta.parent_id == a.meta.id:
                    return ev
                # Algo que no es para nosotros aún (p. ej. peers de otro): ignorar
        except (asyncio.TimeoutError, ConnectionClosed, P.ErrorProtocolo):
            return None

    async def _bucle_recv(self):
        try:
            async for mensaje in self._ws:
                try:
                    ev = P.decodificar(mensaje)
                except P.ErrorProtocolo:
                    continue
                if ev.type == Tipo.PEERS.value:
                    self.peers = ev.data.get("peers", [])
                fut = self._pendientes.pop(ev.meta.parent_id, None) if ev.meta.parent_id else None
                if fut is not None and not fut.done():
                    fut.set_result(ev)
                    continue
                if ev.type == Tipo.PONG.value:
                    continue
                if self.on_evento:
                    try:
                        self.on_evento(ev)
                    except Exception as e:
                        _log(f"on_evento falló: {e}")
        except ConnectionClosed as e:
            _log(f"conexión cerrada ({e.code})")
        finally:
            self._listo.clear()
            for fut in self._pendientes.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("conexión perdida"))
            self._pendientes.clear()
            if self._tarea_ping:
                self._tarea_ping.cancel()
            if not self._cerrar:
                if getattr(self._ws, "close_code", None) == P.CIERRE_TOKEN_INVALIDO:
                    self._set_estado("failed")
                else:
                    asyncio.create_task(self.conectar())

    async def _pinger(self):
        try:
            while True:
                await asyncio.sleep(P.INTERVALO_PING_S)
                await self._enviar_crudo(Tipo.PING, {})
        except (asyncio.CancelledError, ConnectionClosed):
            pass

    # ── Envío ──────────────────────────────────────────────────────────────────

    async def _enviar_crudo(self, tipo, data, to=None, parent_id=None) -> Evento:
        ev = P.nuevo_evento(tipo, data, self.fuente, parent_id=parent_id, to=to)
        await self._ws.send(P.codificar(ev))
        return ev

    async def enviar(self, tipo: Tipo | str, data: dict, to: Optional[list] = None,
                     parent_id: Optional[str] = None) -> Evento:
        if not self.conectado:
            raise ConnectionError("el cliente no está listo")
        return await self._enviar_crudo(tipo, data, to=to, parent_id=parent_id)

    async def pedir(self, tipo: Tipo | str, data: dict, timeout: float = 10.0) -> Evento:
        """Envía y espera el evento cuyo parent_id sea el nuestro."""
        if not self.conectado:
            raise ConnectionError("el cliente no está listo")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        ev = P.nuevo_evento(tipo, data, self.fuente)
        self._pendientes[ev.meta.id] = fut
        await self._ws.send(P.codificar(ev))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pendientes.pop(ev.meta.id, None)

    async def esperar_listo(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._listo.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def cerrar(self):
        self._cerrar = True
        for t in (self._tarea_ping, self._tarea_recv):
            if t:
                t.cancel()
        await self._cerrar_ws()
        self._set_estado("idle")

    async def _cerrar_ws(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


class _TokenInvalido(Exception):
    pass


class ClienteEnHilo:
    """
    Cliente para código síncrono (la app Qt): corre `Cliente` en un hilo con su
    bucle y ofrece métodos bloqueantes con timeout. `on_evento` se llama desde
    el hilo del cliente: en Qt, reemitir por una señal.
    """

    def __init__(self, url: str, token: Optional[str], nombre: str, kind: str = "app",
                 eventos_emitidos: Iterable[str] = (), on_evento: Optional[OnEvento] = None,
                 on_estado: Optional[Callable[[str], None]] = None):
        self._args = dict(url=url, token=token, nombre=nombre, kind=kind,
                          eventos_emitidos=eventos_emitidos, on_evento=on_evento,
                          on_estado=on_estado)
        self.cliente: Optional[Cliente] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._hilo: Optional[threading.Thread] = None
        self._arrancado = threading.Event()

    def iniciar(self, timeout: float = 10.0) -> bool:
        """Arranca el hilo y espera a estar `ready` (o agota el timeout)."""
        def _correr():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self.cliente = Cliente(**self._args)
            self._arrancado.set()
            self._loop.create_task(self.cliente.conectar())
            try:
                self._loop.run_forever()
            finally:
                self._loop.run_until_complete(self.cliente.cerrar())
                self._loop.close()

        self._hilo = threading.Thread(target=_correr, name="lune-cliente", daemon=True)
        self._hilo.start()
        self._arrancado.wait(5)
        return self.esperar_listo(timeout)

    def esperar_listo(self, timeout: float) -> bool:
        try:
            return asyncio.run_coroutine_threadsafe(
                self.cliente.esperar_listo(timeout), self._loop).result(timeout + 1)
        except Exception:
            return False

    @property
    def estado(self) -> str:
        return self.cliente.estado if self.cliente else "idle"

    @property
    def conectado(self) -> bool:
        return bool(self.cliente and self.cliente.conectado)

    def pedir_sync(self, tipo, data: dict, timeout: float = 10.0) -> Evento:
        return asyncio.run_coroutine_threadsafe(
            self.cliente.pedir(tipo, data, timeout), self._loop).result(timeout + 1)

    def enviar_sync(self, tipo, data: dict, to: Optional[list] = None, timeout: float = 5.0) -> Evento:
        return asyncio.run_coroutine_threadsafe(
            self.cliente.enviar(tipo, data, to=to), self._loop).result(timeout)

    def detener(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._hilo:
            self._hilo.join(timeout=5)
