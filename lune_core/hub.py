"""
lune_core/hub.py — El bus de eventos del host.

Un servidor WebSocket al que se conectan los terminales (la app de escritorio,
la asistente en escritorio, el bot de Telegram, un navegador) como *peers*. El hub no piensa:
reparte eventos y mantiene la lista de quién está vivo. Los servicios del
núcleo (memoria, agente, voz) se registran como manejadores internos.

Reglas, portadas del "server channel" de AIRI y adaptadas:
  · Se acepta siempre el upgrade y se autentica DESPUÉS con un evento `auth`
    (código de cierre 4001 si el token es malo). Ventana de 15 s.
  · Latido: el peer hace `ping`; sin señales en TTL pasa a unhealthy y a 2×TTL
    se cierra. Cualquier mensaje cuenta como señal de vida.
  · Todo evento de un peer autenticado se (1) entrega a los manejadores internos
    del tipo y (2) reenvía a los demás peers, salvo que `route.to` lo restrinja.
  · El hub corre en su propio bucle asyncio, NUNCA en el hilo de Qt (`HubEnHilo`).
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from . import protocolo as P
from .protocolo import Evento, Fuente, Tipo, CodigoError

Manejador = Callable[[Evento, "Peer"], Awaitable[None]]


def _log(msg: str):
    try:
        from nucleo.utils import log_info
        log_info(f"[hub] {msg}")
    except Exception:
        print(f"[hub] {msg}")


@dataclass
class Peer:
    ws: Any
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    kind: str = ""
    events: List[str] = field(default_factory=list)
    authenticated: bool = False
    announced: bool = False
    healthy: bool = True
    last_seen: float = field(default_factory=time.monotonic)
    conectado_en: float = field(default_factory=time.monotonic)

    def resumen(self) -> dict:
        return {"id": self.id, "name": self.name or self.id, "kind": self.kind,
                "healthy": self.healthy}


class Hub:
    def __init__(self, token: Optional[str], host: str = "0.0.0.0",
                 puerto: int = P.PUERTO_POR_DEFECTO, fuente_id: str = "core"):
        self.token = token or ""
        self.host = host
        self.puerto = puerto
        self.fuente = Fuente(id=fuente_id, kind="core")
        self.peers: Dict[str, Peer] = {}
        self._manejadores: Dict[str, List[Manejador]] = {}
        self._servidor = None
        self._tarea_latido: Optional[asyncio.Task] = None
        self.estado_extra: Dict[str, Any] = {}   # lo que quiera anunciar host:status
        if not self.token:
            _log("AVISO: sin token; cualquier equipo de la red podrá conectarse")

    # ── Servicios internos ─────────────────────────────────────────────────────

    def registrar(self, tipo: Tipo | str, manejador: Manejador):
        """Un servicio del núcleo se suscribe a un tipo de evento."""
        clave = tipo.value if isinstance(tipo, Tipo) else str(tipo)
        self._manejadores.setdefault(clave, []).append(manejador)

    # ── Envío ──────────────────────────────────────────────────────────────────

    async def enviar_a(self, peer: Peer, evento: Evento):
        try:
            await peer.ws.send(P.codificar(evento))
        except ConnectionClosed:
            pass

    async def responder(self, peer: Peer, tipo: Tipo | str, data: dict, a: Evento) -> Evento:
        """Respuesta dirigida a un peer, correlacionada con el evento que la causó."""
        ev = P.nuevo_evento(tipo, data, self.fuente, parent_id=a.meta.id)
        await self.enviar_a(peer, ev)
        return ev

    async def emitir(self, evento: Evento, excepto: Optional[Peer] = None):
        """
        Reparte a los peers autenticados. Si `route.to` trae ids (o nombres),
        solo a esos. Nunca al emisor.
        """
        destinos = None
        if evento.route and isinstance(evento.route.get("to"), list):
            destinos = set(evento.route["to"])
        texto = P.codificar(evento)
        for peer in list(self.peers.values()):
            if not peer.authenticated or peer is excepto:
                continue
            if destinos is not None and peer.id not in destinos and peer.name not in destinos:
                continue
            try:
                await peer.ws.send(texto)
            except ConnectionClosed:
                continue

    async def publicar(self, tipo: Tipo | str, data: dict, to: Optional[list] = None):
        """El núcleo emite un evento propio (output:*, memory:changed, host:status…)."""
        await self.emitir(P.nuevo_evento(tipo, data, self.fuente, to=to))

    def estado(self) -> dict:
        return {
            "peers": [p.resumen() for p in self.peers.values() if p.authenticated],
            "version": P.VERSION,
            **self.estado_extra,
        }

    # ── Conexiones ─────────────────────────────────────────────────────────────

    async def _conexion(self, ws):
        peer = Peer(ws=ws)
        self.peers[peer.id] = peer
        _log(f"conexión {peer.id} desde {getattr(ws, 'remote_address', '?')}")
        try:
            # Ventana de autenticación: primer mensaje debe ser `auth` (o ping).
            try:
                await asyncio.wait_for(self._autenticar(peer), timeout=P.VENTANA_AUTH_S)
            except asyncio.TimeoutError:
                await ws.close(P.CIERRE_NO_AUTENTICADO, "sin autenticar a tiempo")
                return
            if not peer.authenticated:
                return
            async for mensaje in ws:
                peer.last_seen = time.monotonic()
                if not peer.healthy:
                    peer.healthy = True
                    await self._difundir_peers()
                await self._despachar(peer, mensaje)
        except ConnectionClosed:
            pass
        finally:
            self.peers.pop(peer.id, None)
            if peer.announced:
                _log(f"se fue {peer.name or peer.id}")
                await self._difundir_peers()

    async def _autenticar(self, peer: Peer):
        async for mensaje in peer.ws:
            peer.last_seen = time.monotonic()
            try:
                ev = P.decodificar(mensaje)
            except P.ErrorProtocolo as e:
                await self.enviar_a(peer, P.error_evento(CodigoError.EVENTO_INVALIDO, self.fuente,
                                                         detalle=str(e)))
                continue
            if ev.type == Tipo.PING.value:
                await self.responder(peer, Tipo.PONG, {}, ev)
                continue
            if ev.type != Tipo.AUTH.value:
                await self.enviar_a(peer, P.error_evento(CodigoError.NO_AUTENTICADO, self.fuente,
                                                         parent_id=ev.meta.id))
                continue
            if not P.comparar_token(ev.data.get("token"), self.token):
                await self.enviar_a(peer, P.error_evento(CodigoError.TOKEN_INVALIDO, self.fuente,
                                                         parent_id=ev.meta.id))
                await peer.ws.close(P.CIERRE_TOKEN_INVALIDO, "token inválido")
                return
            peer.authenticated = True
            peer.name = ev.meta.source.id
            peer.kind = ev.meta.source.kind
            await self.responder(peer, Tipo.AUTHED, {"peer_id": peer.id}, ev)
            return

    async def _despachar(self, peer: Peer, mensaje):
        try:
            ev = P.decodificar(mensaje)
        except P.ErrorProtocolo as e:
            await self.enviar_a(peer, P.error_evento(CodigoError.EVENTO_INVALIDO, self.fuente,
                                                     detalle=str(e)))
            return

        if ev.type == Tipo.PING.value:
            await self.responder(peer, Tipo.PONG, {}, ev)
            return
        if ev.type == Tipo.AUTH.value:
            await self.responder(peer, Tipo.AUTHED, {"peer_id": peer.id}, ev)
            return
        if ev.type == Tipo.ANNOUNCE.value:
            peer.name = str(ev.data.get("name") or peer.name or peer.id)
            peer.kind = str(ev.data.get("kind") or peer.kind or ev.meta.source.kind)
            peer.events = [str(x) for x in (ev.data.get("events") or [])]
            peer.announced = True
            _log(f"anunciado {peer.name} ({peer.kind})")
            await self.responder(peer, Tipo.PEERS, self.estado(), ev)
            await self._difundir_peers(excepto=peer)
            return
        if not P.es_tipo_conocido(ev.type):
            await self.enviar_a(peer, P.error_evento(CodigoError.TIPO_DESCONOCIDO, self.fuente,
                                                     parent_id=ev.meta.id, detalle=ev.type))
            return

        # 1) servicios internos
        for manejador in self._manejadores.get(ev.type, []):
            try:
                await manejador(ev, peer)
            except Exception as e:  # un servicio roto no tumba el hub
                _log(f"manejador de {ev.type} falló: {e}")
                await self.enviar_a(peer, P.error_evento(CodigoError.INTERNO, self.fuente,
                                                         parent_id=ev.meta.id, detalle=str(e)))
        # 2) los demás peers
        await self.emitir(ev, excepto=peer)

    async def _difundir_peers(self, excepto: Optional[Peer] = None):
        await self.emitir(P.nuevo_evento(Tipo.PEERS, self.estado(), self.fuente), excepto=excepto)

    # ── Latido ─────────────────────────────────────────────────────────────────

    async def _latido(self):
        intervalo = max(5, P.TTL_LATIDO_S // 5)
        while True:
            await asyncio.sleep(intervalo)
            ahora = time.monotonic()
            cambio = False
            for peer in list(self.peers.values()):
                silencio = ahora - peer.last_seen
                if silencio > 2 * P.TTL_LATIDO_S:
                    _log(f"cierro {peer.name or peer.id} por silencio ({int(silencio)} s)")
                    try:
                        await peer.ws.close(P.CIERRE_SIN_LATIDO, "sin latido")
                    except Exception:
                        pass
                elif silencio > P.TTL_LATIDO_S and peer.healthy:
                    peer.healthy = False
                    cambio = True
            if cambio:
                await self._difundir_peers()

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    async def iniciar(self):
        self._servidor = await websockets.serve(
            self._conexion, self.host, self.puerto,
            ping_interval=None,        # el latido es nuestro, a nivel de protocolo
            max_size=16 * 1024 * 1024,  # audio/imágenes en base64
        )
        # Si se pidió puerto 0 (tests), el sistema eligió uno: recupéralo.
        for sock in self._servidor.sockets:
            self.puerto = sock.getsockname()[1]
            break
        self._tarea_latido = asyncio.create_task(self._latido())
        _log(f"escuchando en ws://{self.host}:{self.puerto}{P.RUTA_WS}")

    async def detener(self):
        if self._tarea_latido:
            self._tarea_latido.cancel()
        for peer in list(self.peers.values()):
            try:
                await peer.ws.close(P.CIERRE_APAGADO, "host apagándose")
            except Exception:
                pass
        if self._servidor:
            self._servidor.close()
            await self._servidor.wait_closed()
        _log("detenido")

    async def servir_para_siempre(self):
        await self.iniciar()
        try:
            await asyncio.Future()
        finally:
            await self.detener()


class HubEnHilo:
    """
    Arranca un Hub en un hilo con su propio bucle asyncio, para usarlo desde
    una app Qt (modo local) sin tocar el hilo de la interfaz.
    """

    def __init__(self, hub: Hub, servicios: Optional[Callable[[Hub], None]] = None):
        self.hub = hub
        self._servicios = servicios
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._hilo: Optional[threading.Thread] = None
        self._listo = threading.Event()

    def iniciar(self, timeout: float = 5.0) -> bool:
        def _correr():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            if self._servicios:
                self._servicios(self.hub)
            self._loop.run_until_complete(self.hub.iniciar())
            self._listo.set()
            try:
                self._loop.run_forever()
            finally:
                self._loop.run_until_complete(self.hub.detener())
                self._loop.close()

        self._hilo = threading.Thread(target=_correr, name="lune-hub", daemon=True)
        self._hilo.start()
        return self._listo.wait(timeout)

    def llamar(self, coro, timeout: float = 10.0):
        """Ejecuta una corrutina en el bucle del hub y espera el resultado."""
        if not self._loop:
            raise RuntimeError("el hub no está iniciado")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def detener(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._hilo:
            self._hilo.join(timeout=5)
