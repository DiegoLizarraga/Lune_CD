"""
lune_core/protocolo.py — El contrato del hub: sobres, tipos de evento y errores.

Es la única fuente de verdad de cómo se hablan el host y los terminales. Todo
lo demás (hub, cliente Python, cliente del bot en Node) se ajusta a esto. Sin
dependencias fuera de la biblioteca estándar, a propósito: cualquier proceso
que hable JSON puede ser un terminal.

Forma de un evento en el cable (JSON plano, una línea por mensaje):

    {
      "type": "input:text",
      "data": {"text": "hola", "session_id": "abc"},
      "meta": {
        "source": {"id": "laptop-app", "kind": "app"},
        "id": "e1f3…",
        "parent_id": null,          # id del evento al que responde, si aplica
        "ts": "2026-09-05T10:00:00"
      },
      "route": {"to": ["bot-telegram"]}   # opcional; sin route = a todos
    }

Los nombres de tipo son `dominio:accion`. Empezamos con pocos y claros; añadir
uno nuevo es añadirlo a `Tipo` y documentar su `data` aquí.
"""
from __future__ import annotations

import hmac
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

VERSION = 1
PUERTO_POR_DEFECTO = 7777
RUTA_WS = "/ws"

# Latido: el cliente hace ping cada INTERVALO_PING_S; el servidor da por muerto
# a un peer que no ha dado señales en TTL_LATIDO_S y lo cierra a 2×TTL.
INTERVALO_PING_S = 20
TTL_LATIDO_S = 60

# Ventana para autenticarse tras abrir el socket. Se acepta siempre el upgrade
# y se autentica DESPUÉS con un mensaje: un navegador oculta el 401 del upgrade
# y así el cliente sí distingue «token malo» de «red caída».
VENTANA_AUTH_S = 15

# Códigos de cierre WebSocket propios (rango 4000-4999 es de aplicación).
CIERRE_TOKEN_INVALIDO = 4001
CIERRE_NO_AUTENTICADO = 4002
CIERRE_SIN_LATIDO = 4003
CIERRE_APAGADO = 4004


class Tipo(str, Enum):
    """Catálogo de eventos. El valor es lo que viaja en `type`."""

    # ── Transporte y sesión ──
    AUTH = "auth"                         # C→S {token}
    AUTHED = "authed"                     # S→C {peer_id}
    ANNOUNCE = "announce"                 # C→S {name, kind, events: [tipos que emite]}
    PEERS = "peers"                       # S→C {peers: [{id, name, kind, healthy}]}
    PING = "ping"                         # C→S {}
    PONG = "pong"                         # S→C {}
    ERROR = "error"                       # S→C {code, message, terminal}

    # ── Entrada del usuario (desde un terminal) ──
    # {text, session_id?, attachments?, images?, provider?, origen?, efimero?}
    # origen 'no_confiable' solo baja la confianza del turno; efimero: no se guarda.
    INPUT_TEXT = "input:text"
    INPUT_VOICE = "input:voice"           # {audio_b64, format, session_id?}

    # ── Salida del personaje (desde el host) ──
    OUTPUT_DELTA = "output:chat:delta"    # {text}  (streaming)
    OUTPUT_ACT = "output:chat:act"        # {emotion, intensity, motion?}
    OUTPUT_DONE = "output:chat:done"      # {text, usage, acts, tools}
    OUTPUT_VOICE = "output:voice"         # {audio_b64, format, seq, text}

    # ── Memoria compartida ──
    MEMORY_QUERY = "memory:query"         # {que: "contexto"|"listar"|"nombre"|"stats"}
    MEMORY_RESULT = "memory:result"       # {que, resultado}
    MEMORY_REMEMBER = "memory:remember"   # {mensaje} → se procesa como en la app
    MEMORY_FORGET = "memory:forget"       # {id | "todo"}
    MEMORY_SET = "memory:set"             # {datos: {clave: valor}, reemplazar?: bool}
    MEMORY_CHANGED = "memory:changed"     # {motivo}  (broadcast tras cualquier cambio)

    # ── Estado del host ──
    HOST_STATUS = "host:status"           # {busy, model, tokens_s, peers}

    # ── Herramientas (9.5; corte 2 de Mate-Engine) ──
    # El host pide permiso SOLO al terminal que hizo la petición, y solo si ese
    # terminal anunció que emite TOOL_APPROVAL_RESPONSE (ANNOUNCE.events). Solo
    # cuenta la respuesta de ese mismo terminal; sin respuesta en 60 s, rechazada.
    TOOL_APPROVAL_REQUEST = "tool:approval:request"    # S→C {id, tool, args, why, risk, …pendiente}
    TOOL_APPROVAL_RESPONSE = "tool:approval:response"  # C→S {id, approved: bool, reason?}
    TOOL_APPROVAL_CLOSE = "tool:approval:close"        # S→C {id, motivo}  (caducó o se canceló)
    TOOL_RESULT = "tool:result"                        # S→C {ok, mensaje, herramienta, estado, args, pendiente_id}

    # ── Mascota y alarmas ──
    MASCOTA_ACCION = "mascota:accion"     # {accion, args}  (bailar, dormir, sentarse…)
    ALARMA = "alarm:fire"                 # {id, texto, tipo: "alarma"|"temporizador"}


class CodigoError(str, Enum):
    TOKEN_INVALIDO = "token_invalido"
    NO_AUTENTICADO = "no_autenticado"
    EVENTO_INVALIDO = "evento_invalido"
    TIPO_DESCONOCIDO = "tipo_desconocido"
    NO_DISPONIBLE = "no_disponible"
    INTERNO = "interno"


# code → (mensaje, terminal). Terminal = no tiene sentido reintentar.
ERRORES: Dict[CodigoError, tuple] = {
    CodigoError.TOKEN_INVALIDO: ("El token no coincide con el del host.", True),
    CodigoError.NO_AUTENTICADO: ("Autentícate antes de enviar eventos.", False),
    CodigoError.EVENTO_INVALIDO: ("El evento no tiene la forma esperada.", False),
    CodigoError.TIPO_DESCONOCIDO: ("Tipo de evento desconocido para este host.", False),
    CodigoError.NO_DISPONIBLE: ("El host no tiene ese servicio activo.", False),
    CodigoError.INTERNO: ("Fallo interno del host.", False),
}


class ErrorProtocolo(ValueError):
    """Un mensaje que no cumple el contrato."""


# ── Sobres ─────────────────────────────────────────────────────────────────────

@dataclass
class Fuente:
    id: str
    kind: str    # "app" | "bot" | "overlay" | "web" | "core"


@dataclass
class Meta:
    source: Fuente
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_id: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class Evento:
    type: str
    data: Dict[str, Any]
    meta: Meta
    route: Optional[Dict[str, Any]] = None

    def responde_a(self) -> Optional[str]:
        return self.meta.parent_id


def nuevo_evento(tipo: Tipo | str, data: Optional[dict], fuente: Fuente,
                 parent_id: Optional[str] = None, to: Optional[list] = None) -> Evento:
    """Construye un evento bien formado. `to` restringe destinatarios."""
    return Evento(
        type=tipo.value if isinstance(tipo, Tipo) else str(tipo),
        data=dict(data or {}),
        meta=Meta(source=fuente, parent_id=parent_id),
        route={"to": list(to)} if to else None,
    )


def error_evento(codigo: CodigoError, fuente: Fuente, parent_id: Optional[str] = None,
                 detalle: str = "") -> Evento:
    mensaje, terminal = ERRORES[codigo]
    if detalle:
        mensaje = f"{mensaje} {detalle}".strip()
    return nuevo_evento(Tipo.ERROR, {"code": codigo.value, "message": mensaje,
                                     "terminal": terminal}, fuente, parent_id)


# ── Codec ──────────────────────────────────────────────────────────────────────

def codificar(evento: Evento) -> str:
    d = asdict(evento)
    if d.get("route") is None:
        d.pop("route", None)
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def decodificar(texto: str | bytes) -> Evento:
    """
    Valida lo mínimo para no propagar basura: `type` str no vacío, `data` dict,
    `meta.source.{id,kind}` str y `meta.id` str. Todo lo demás es opcional.
    """
    try:
        if isinstance(texto, (bytes, bytearray)):
            texto = texto.decode("utf-8")
        crudo = json.loads(texto)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErrorProtocolo(f"JSON inválido: {e}") from e
    if not isinstance(crudo, dict):
        raise ErrorProtocolo("el evento debe ser un objeto")

    tipo = crudo.get("type")
    if not isinstance(tipo, str) or not tipo:
        raise ErrorProtocolo("falta 'type'")
    data = crudo.get("data", {})
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ErrorProtocolo("'data' debe ser un objeto")

    meta = crudo.get("meta") or {}
    if not isinstance(meta, dict):
        raise ErrorProtocolo("'meta' debe ser un objeto")
    fuente = meta.get("source") or {}
    if not isinstance(fuente, dict) or not isinstance(fuente.get("id"), str) \
            or not isinstance(fuente.get("kind"), str):
        raise ErrorProtocolo("falta 'meta.source.{id,kind}'")
    ident = meta.get("id")
    if not isinstance(ident, str) or not ident:
        raise ErrorProtocolo("falta 'meta.id'")
    parent = meta.get("parent_id")
    if parent is not None and not isinstance(parent, str):
        raise ErrorProtocolo("'meta.parent_id' debe ser texto o null")

    route = crudo.get("route")
    if route is not None:
        if not isinstance(route, dict):
            raise ErrorProtocolo("'route' debe ser un objeto")
        to = route.get("to")
        if to is not None and not (isinstance(to, list) and all(isinstance(x, str) for x in to)):
            raise ErrorProtocolo("'route.to' debe ser una lista de ids")

    return Evento(
        type=tipo,
        data=data,
        meta=Meta(source=Fuente(id=fuente["id"], kind=fuente["kind"]),
                  id=ident, parent_id=parent,
                  ts=str(meta.get("ts") or datetime.now().isoformat(timespec="seconds"))),
        route=route,
    )


def es_tipo_conocido(tipo: str) -> bool:
    return tipo in {t.value for t in Tipo}


# ── Seguridad ──────────────────────────────────────────────────────────────────

def comparar_token(recibido: Optional[str], esperado: Optional[str]) -> bool:
    """
    Comparación en tiempo constante. Se rellena a longitud fija para que la
    longitud del token tampoco se filtre por el tiempo de respuesta.
    """
    if not esperado:
        # Un host sin token configurado acepta a cualquiera de la LAN. Se permite
        # explícitamente (equipo único / pruebas), pero el hub lo avisa en el log.
        return True
    a = (recibido or "").encode("utf-8").ljust(256, b"\0")[:256]
    b = esperado.encode("utf-8").ljust(256, b"\0")[:256]
    return hmac.compare_digest(a, b) and len(recibido or "") == len(esperado)


def generar_token() -> str:
    import secrets
    return secrets.token_urlsafe(24)
