"""
probar_red.py — Comprueba en un comando que la red de Lune funciona.

    python probar_red.py

Según el modo en datos.json:
  · local / host → levanta un hub aquí y hace un viaje de ida y vuelta a la
    memoria (escribe un recuerdo y lo lee), demostrando el mecanismo.
  · terminal     → se conecta al host configurado (url_host + token) y hace el
    mismo viaje contra la memoria del host de verdad.

No modifica tu memoria de forma permanente: escribe un recuerdo de prueba y lo
borra al final (en modo host/local usa una memoria temporal aparte).
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import datos
from lune_core import protocolo as P


def _ok(msg): print(f"  \033[92m✓\033[0m {msg}")
def _fail(msg): print(f"  \033[91m✗\033[0m {msg}")
def _info(msg): print(f"    {msg}")


def probar_terminal(url: str, token: str) -> bool:
    from lune_core.cliente import ClienteEnHilo
    print(f"\nModo TERMINAL → conectando al host en {url}")
    cli = ClienteEnHilo(url, token, nombre="prueba", kind="app")
    if not cli.iniciar(timeout=8):
        _fail(f"no pude conectar ({cli.estado}). ¿El host tiene 'python -m lune_core serve' y el token coincide?")
        cli.detener()
        return False
    _ok(f"conectado al host (estado: {cli.estado})")
    try:
        marca = f"prueba de red {int(time.time())}"
        r = cli.pedir_sync(P.Tipo.MEMORY_REMEMBER, {"mensaje": f"recuerda que {marca}"}, timeout=8)
        if "Anotado" not in (r.data.get("resultado") or ""):
            _fail(f"el host no anotó el recuerdo: {r.data}")
            return False
        _ok("escribí un recuerdo en el host")
        r = cli.pedir_sync(P.Tipo.MEMORY_QUERY, {"que": "listar"}, timeout=8)
        if marca in (r.data.get("resultado") or ""):
            _ok("lo leí de vuelta desde el host: la memoria es compartida")
        else:
            _fail("no encontré el recuerdo al releer")
            return False
        # limpieza: borro solo ese recuerdo de prueba
        cli.pedir_sync(P.Tipo.MEMORY_FORGET, {"id": marca}, timeout=8)
        _info("(recuerdo de prueba borrado)")
        return True
    except Exception as e:
        _fail(f"error hablando con el host: {e}")
        return False
    finally:
        cli.detener()


def probar_local() -> bool:
    from lune_core.hub import Hub, HubEnHilo
    from lune_core.cliente import ClienteEnHilo
    from lune_core.servicio_memoria import ServicioMemoria
    from memoria import MemoriaManager

    print("\nModo LOCAL/HOST → levanto un hub aquí y pruebo el viaje de ida y vuelta")
    tmp = Path(tempfile.mkdtemp()) / "memoria_prueba.json"
    token = "prueba-local"
    hub = Hub(token, host="127.0.0.1", puerto=0)
    en_hilo = HubEnHilo(hub, servicios=lambda h: ServicioMemoria(h, MemoriaManager(path=tmp)))
    if not en_hilo.iniciar(timeout=5):
        _fail("el hub no arrancó")
        return False
    _ok(f"hub levantado en el puerto {hub.puerto}")

    cli_a = ClienteEnHilo(f"ws://127.0.0.1:{hub.puerto}", token, "equipo-A", "app")
    cli_b = ClienteEnHilo(f"ws://127.0.0.1:{hub.puerto}", token, "equipo-B", "bot")
    try:
        if not (cli_a.iniciar(timeout=6) and cli_b.iniciar(timeout=6)):
            _fail("los clientes no conectaron")
            return False
        _ok("dos 'equipos' conectados al mismo hub")
        cli_a.pedir_sync(P.Tipo.MEMORY_REMEMBER, {"mensaje": "recuerda que estoy probando la red"})
        _ok("el equipo A escribió un recuerdo")
        r = cli_b.pedir_sync(P.Tipo.MEMORY_QUERY, {"que": "listar"})
        if "probando la red" in (r.data.get("resultado") or ""):
            _ok("el equipo B lo ve: la memoria es la MISMA para ambos")
            return True
        _fail("el equipo B no vio el recuerdo")
        return False
    finally:
        cli_a.detener(); cli_b.detener(); en_hilo.detener()


def main() -> int:
    modo = datos.hub_modo()
    print(f"Red de Lune · modo de este equipo: {modo}")
    if modo == "terminal":
        url = datos.hub_url_host()
        if not url:
            _fail("modo terminal sin URL de host en datos.json (Ajustes → Red de Lune)")
            return 1
        ok = probar_terminal(url, datos.hub_token())
    else:
        ok = probar_local()
    print("\n" + ("🌙  Todo funciona." if ok else "⚠️  Algo falló; revisa los mensajes de arriba."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
