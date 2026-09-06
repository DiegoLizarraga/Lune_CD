"""
python -m lune_core serve — arranca el núcleo en el host.

Sirve el hub y la memoria compartida. El token se genera la primera vez y se
guarda en datos.json (`hub.token`); es lo que hay que poner en los terminales.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Los módulos de la raíz (datos, memoria, utils) no son un paquete: se añade la
# raíz al path para poder ejecutarse como `python -m lune_core` desde cualquier cwd.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import datos  # noqa: E402
from memoria import MemoriaManager  # noqa: E402
from utils import log_info  # noqa: E402

from .hub import Hub  # noqa: E402
from .protocolo import Tipo, PUERTO_POR_DEFECTO  # noqa: E402
from .servicio_memoria import ServicioMemoria  # noqa: E402


async def _estado_periodico(hub: Hub, cada_s: int = 30):
    while True:
        await asyncio.sleep(cada_s)
        await hub.publicar(Tipo.HOST_STATUS, hub.estado())


async def _servir(hub: Hub):
    await hub.iniciar()
    tarea = asyncio.create_task(_estado_periodico(hub))

    # Terminal web (página estática) en el puerto del hub + 1.
    from .web_server import ServidorWeb
    web = ServidorWeb(hub.puerto, host="0.0.0.0")
    if web.iniciar():
        log_info(f"[core] terminal web en http://<este-equipo>:{web.puerto}/")
        print(f"Terminal web: http://<ip-de-este-equipo>:{web.puerto}/")

    # Anuncio por mDNS (si zeroconf está instalado).
    from .descubrimiento import AnuncioHost
    anuncio = AnuncioHost(hub.puerto)
    if anuncio.iniciar():
        log_info("[core] anunciado por mDNS (los terminales pueden descubrirlo)")

    try:
        await asyncio.Future()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        tarea.cancel()
        anuncio.detener()
        web.detener()
        await hub.detener()


def construir_hub(host: str, puerto: int, token: str) -> Hub:
    hub = Hub(token, host=host, puerto=puerto)
    hub.estado_extra = {"busy": False, "model": datos.ollama_model()}
    ServicioMemoria(hub, MemoriaManager())
    return hub


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lune_core",
                                     description="Núcleo de Lune CD para el equipo host")
    sub = parser.add_subparsers(dest="orden")
    s = sub.add_parser("serve", help="servir el hub y la memoria compartida")
    s.add_argument("--host", default="0.0.0.0", help="interfaz de escucha (0.0.0.0 = toda la red)")
    s.add_argument("--puerto", type=int, default=None, help=f"puerto (por defecto hub.puerto o {PUERTO_POR_DEFECTO})")
    sub.add_parser("token", help="mostrar el token del hub (se genera si no existe)")
    args = parser.parse_args(argv)

    if args.orden == "token":
        print(datos.asegurar_token_hub())
        return 0

    if args.orden != "serve":
        parser.print_help()
        return 1

    token = datos.asegurar_token_hub()
    puerto = args.puerto or datos.hub_puerto()
    hub = construir_hub(args.host, puerto, token)
    log_info(f"[core] sirviendo en {args.host}:{puerto}")
    print(f"Lune core sirviendo en ws://{args.host}:{puerto}/ws")
    print(f"Token para los terminales: {token}")
    print("Ctrl+C para detener.")
    try:
        asyncio.run(_servir(hub))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
