"""
Tests del hub, el cliente y la memoria compartida (lune_core), de extremo a extremo
sobre un servidor real en 127.0.0.1 con puerto efímero.
"""
import asyncio
import sys
from pathlib import Path

import pytest
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import protocolo as P  # noqa: E402
from lune_core.hub import Hub, HubEnHilo  # noqa: E402
from lune_core.cliente import Cliente, ClienteEnHilo  # noqa: E402
from lune_core.servicio_memoria import ServicioMemoria  # noqa: E402
from memoria import MemoriaManager  # noqa: E402

TOKEN = "secreto-de-prueba"


def correr(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=20))


async def hub_de_prueba(tmp_path=None, token=TOKEN):
    hub = Hub(token, host="127.0.0.1", puerto=0)
    if tmp_path is not None:
        ServicioMemoria(hub, MemoriaManager(path=tmp_path / "memoria.json"))
    await hub.iniciar()
    return hub


async def crudo(hub):
    """Conexión de bajo nivel para probar el protocolo sin el SDK."""
    return await websockets.connect(f"ws://127.0.0.1:{hub.puerto}/ws", open_timeout=5)


def evento(tipo, data, nombre="crudo", parent=None):
    return P.codificar(P.nuevo_evento(tipo, data, P.Fuente(nombre, "app"), parent_id=parent))


async def leer(ws, timeout=5):
    return P.decodificar(await asyncio.wait_for(ws.recv(), timeout))


# ── Handshake ──────────────────────────────────────────────────────────────────

def test_auth_y_announce():
    async def caso():
        hub = await hub_de_prueba()
        try:
            ws = await crudo(hub)
            await ws.send(evento(P.Tipo.AUTH, {"token": TOKEN}))
            r = await leer(ws)
            assert r.type == "authed" and r.data["peer_id"]
            await ws.send(evento(P.Tipo.ANNOUNCE, {"name": "crudo", "kind": "app", "events": []}))
            r = await leer(ws)
            assert r.type == "peers"
            assert any(p["name"] == "crudo" for p in r.data["peers"])
            await ws.close()
        finally:
            await hub.detener()
    correr(caso())


def test_token_malo_es_terminal_y_cierra_con_4001():
    async def caso():
        hub = await hub_de_prueba()
        try:
            ws = await crudo(hub)
            await ws.send(evento(P.Tipo.AUTH, {"token": "incorrecto"}))
            r = await leer(ws)
            assert r.type == "error" and r.data["code"] == "token_invalido" and r.data["terminal"] is True
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), 5)
            assert ws.close_code == P.CIERRE_TOKEN_INVALIDO
        finally:
            await hub.detener()
    correr(caso())


def test_eventos_antes_de_autenticar_se_rechazan():
    async def caso():
        hub = await hub_de_prueba()
        try:
            ws = await crudo(hub)
            await ws.send(evento(P.Tipo.INPUT_TEXT, {"text": "hola"}))
            r = await leer(ws)
            assert r.type == "error" and r.data["code"] == "no_autenticado" and r.data["terminal"] is False
            await ws.close()
        finally:
            await hub.detener()
    correr(caso())


def test_basura_no_tumba_el_hub():
    async def caso():
        hub = await hub_de_prueba()
        try:
            ws = await crudo(hub)
            await ws.send("esto no es json")
            r = await leer(ws)
            assert r.type == "error" and r.data["code"] == "evento_invalido"
            # y sigue vivo: ahora sí autenticamos
            await ws.send(evento(P.Tipo.AUTH, {"token": TOKEN}))
            assert (await leer(ws)).type == "authed"
            await ws.close()
        finally:
            await hub.detener()
    correr(caso())


def test_host_sin_token_acepta_a_todos():
    async def caso():
        hub = await hub_de_prueba(token="")
        try:
            ws = await crudo(hub)
            await ws.send(evento(P.Tipo.AUTH, {"token": "cualquier cosa"}))
            assert (await leer(ws)).type == "authed"
            await ws.close()
        finally:
            await hub.detener()
    correr(caso())


# ── Difusión ───────────────────────────────────────────────────────────────────

async def _peer_listo(hub, nombre):
    c = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, nombre, "app")
    assert await c.conectar(reintentar=False)
    return c


def test_un_evento_llega_a_los_demas_pero_no_al_emisor():
    async def caso():
        hub = await hub_de_prueba()
        recibidos_b, recibidos_a = [], []
        try:
            a = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "A", "app", on_evento=recibidos_a.append)
            b = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "B", "app", on_evento=recibidos_b.append)
            assert await a.conectar(reintentar=False) and await b.conectar(reintentar=False)
            await a.enviar(P.Tipo.INPUT_TEXT, {"text": "hola desde A"})
            await asyncio.sleep(0.3)
            assert any(e.type == "input:text" and e.data["text"] == "hola desde A" for e in recibidos_b)
            assert not any(e.type == "input:text" for e in recibidos_a)
            await a.cerrar(); await b.cerrar()
        finally:
            await hub.detener()
    correr(caso())


def test_route_to_restringe_destinatarios():
    async def caso():
        hub = await hub_de_prueba()
        rb, rc = [], []
        try:
            a = await _peer_listo(hub, "A")
            b = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "B", "app", on_evento=rb.append)
            c = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "C", "app", on_evento=rc.append)
            assert await b.conectar(reintentar=False) and await c.conectar(reintentar=False)
            await a.enviar(P.Tipo.INPUT_TEXT, {"text": "solo para B"}, to=["B"])
            await asyncio.sleep(0.3)
            assert any(e.type == "input:text" for e in rb)
            assert not any(e.type == "input:text" for e in rc)
            for x in (a, b, c):
                await x.cerrar()
        finally:
            await hub.detener()
    correr(caso())


# ── Memoria compartida ─────────────────────────────────────────────────────────

def test_dos_terminales_ven_la_misma_memoria(tmp_path):
    """Lo que motiva 9.0: recordar en un equipo y verlo desde otro."""
    async def caso():
        hub = await hub_de_prueba(tmp_path)
        avisos_b = []
        try:
            a = await _peer_listo(hub, "laptop")
            b = Cliente(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "telegram", "bot", on_evento=avisos_b.append)
            assert await b.conectar(reintentar=False)

            r = await a.pedir(P.Tipo.MEMORY_REMEMBER, {"mensaje": "recuerda que me gusta el té verde"})
            assert r.type == "memory:result" and "Anotado" in (r.data["resultado"] or "")

            r = await b.pedir(P.Tipo.MEMORY_QUERY, {"que": "listar"})
            assert "té verde" in r.data["resultado"]

            r = await b.pedir(P.Tipo.MEMORY_QUERY, {"que": "contexto"})
            assert "té verde" in r.data["resultado"]

            await asyncio.sleep(0.2)
            assert any(e.type == "memory:changed" for e in avisos_b)

            r = await a.pedir(P.Tipo.MEMORY_FORGET, {"id": "todo"})
            assert "borrada" in r.data["resultado"].lower()
            r = await b.pedir(P.Tipo.MEMORY_QUERY, {"que": "listar"})
            assert "té verde" not in r.data["resultado"]

            await a.cerrar(); await b.cerrar()
        finally:
            await hub.detener()
    correr(caso())


def test_un_mensaje_normal_no_se_guarda(tmp_path):
    async def caso():
        hub = await hub_de_prueba(tmp_path)
        try:
            a = await _peer_listo(hub, "A")
            r = await a.pedir(P.Tipo.MEMORY_REMEMBER, {"mensaje": "me gustaría saber cómo funciona python"})
            assert r.data["resultado"] is None
            r = await a.pedir(P.Tipo.MEMORY_QUERY, {"que": "todo"})
            assert r.data["resultado"]["recuerdos"] == []
            await a.cerrar()
        finally:
            await hub.detener()
    correr(caso())


def test_consulta_desconocida_devuelve_error_controlado(tmp_path):
    async def caso():
        hub = await hub_de_prueba(tmp_path)
        try:
            a = await _peer_listo(hub, "A")
            r = await a.pedir(P.Tipo.MEMORY_QUERY, {"que": "inventada"})
            assert r.type == "memory:result" and r.data["resultado"] is None and r.data.get("error")
            await a.cerrar()
        finally:
            await hub.detener()
    correr(caso())


# ── SDK síncrono (lo que usa la app Qt) ────────────────────────────────────────

def test_cliente_en_hilo_contra_hub_en_hilo(tmp_path):
    hub = Hub(TOKEN, host="127.0.0.1", puerto=0)
    en_hilo = HubEnHilo(hub, servicios=lambda h: ServicioMemoria(h, MemoriaManager(path=tmp_path / "m.json")))
    assert en_hilo.iniciar(timeout=5)
    try:
        cli = ClienteEnHilo(f"ws://127.0.0.1:{hub.puerto}", TOKEN, "app-qt", "app")
        assert cli.iniciar(timeout=8)
        assert cli.estado == "ready"
        r = cli.pedir_sync(P.Tipo.MEMORY_REMEMBER, {"mensaje": "me llamo Diego"})
        assert r.type == "memory:result"
        r = cli.pedir_sync(P.Tipo.MEMORY_QUERY, {"que": "nombre"})
        assert r.data["resultado"] == "Diego"
        cli.detener()
    finally:
        en_hilo.detener()


def test_cliente_con_token_malo_queda_en_failed():
    async def caso():
        hub = await hub_de_prueba()
        try:
            c = Cliente(f"ws://127.0.0.1:{hub.puerto}", "malo", "A", "app")
            assert await c.conectar(reintentar=True) is False
            assert c.estado == "failed"
        finally:
            await hub.detener()
    correr(caso())


def test_memory_set_guarda_pares_y_reemplaza(tmp_path):
    """El bot guarda pares clave/valor que extrae el LLM; /olvidar los vacía."""
    async def caso():
        hub = await hub_de_prueba(tmp_path)
        try:
            bot = await _peer_listo(hub, "bot")
            app = await _peer_listo(hub, "app")
            r = await bot.pedir(P.Tipo.MEMORY_SET, {"datos": {"nombre": "Diego", "ciudad": "Culiacán", "gustos": "café"}})
            assert r.data["resultado"] is True
            r = await app.pedir(P.Tipo.MEMORY_QUERY, {"que": "todo"})
            assert r.data["resultado"]["nombre"] == "Diego"
            assert r.data["resultado"]["stats"]  # sigue siendo la misma memoria
            r = await app.pedir(P.Tipo.MEMORY_QUERY, {"que": "listar"})
            assert "Culiacán" in r.data["resultado"] and "café" in r.data["resultado"]
            # reemplazar = vaciar datos_clave, sin tocar el nombre
            await bot.pedir(P.Tipo.MEMORY_SET, {"datos": {}, "reemplazar": True})
            r = await app.pedir(P.Tipo.MEMORY_QUERY, {"que": "listar"})
            assert "Culiacán" not in r.data["resultado"]
            r = await app.pedir(P.Tipo.MEMORY_QUERY, {"que": "nombre"})
            assert r.data["resultado"] == "Diego"
            await bot.cerrar(); await app.cerrar()
        finally:
            await hub.detener()
    correr(caso())

