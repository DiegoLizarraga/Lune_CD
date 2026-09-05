"""
lune_core — El núcleo de Lune sin interfaz: lo que corre en el host.

    protocolo        contrato de eventos (JSON, tipos, errores)
    hub              servidor WebSocket: peers, autenticación, latido, difusión
    cliente          SDK para terminales (asyncio y envoltorio para hilos/Qt)
    servicio_memoria memoria.json servida por eventos

Arranque en el host:  python -m lune_core serve
La app de escritorio lo importa en proceso (modo local) o se conecta a otro
host (modo terminal). Nada de aquí depende de Qt.
"""
from .protocolo import Tipo, Evento, Fuente, nuevo_evento, codificar, decodificar  # noqa: F401
from .hub import Hub, HubEnHilo  # noqa: F401
from .cliente import Cliente, ClienteEnHilo  # noqa: F401
from .servicio_memoria import ServicioMemoria  # noqa: F401
