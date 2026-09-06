"""
lune_core/descubrimiento.py — Encontrar el host y emparejar terminales.

Dos mecanismos, portados del pairing por QR de AIRI (stage-shared/server-channel-qr):

  · QR de emparejamiento: el host muestra un código con sus URLs y el token; un
    terminal lo escanea y queda configurado. `construir_payload` / `leer_payload`.
  · Descubrimiento por mDNS (zeroconf, opcional): el host se anuncia en la LAN y
    los terminales lo encuentran sin escribir la IP. Si zeroconf no está
    instalado, se degrada a "usa el QR o escribe la IP".

El payload del QR es JSON:
    {"type":"lune:server-channel","version":1,
     "urls":["ws://192.168.1.50:7777","ws://10.0.0.5:7777"], "token":"…"}
Varias URLs porque el host puede tener varias IPs (Wi-Fi + Ethernet).
"""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import protocolo as P

TIPO_PAYLOAD = "lune:server-channel"
SERVICIO_MDNS = "_lunecd._tcp.local."

# Roles que puede tener un dispositivo en la red de Lune.
ROL_HOST = "host"              # sirve el modelo, la memoria y la voz a los demás
ROL_INTERACCION = "interaccion"  # solo interactúa: chat, avatar; usa el host
ROL_HIBRIDO = "hibrido"        # hace todo aquí mismo (equipo único)
ROLES = (ROL_HOST, ROL_INTERACCION, ROL_HIBRIDO)

ETIQUETA_ROL = {
    ROL_HOST: "Host (aloja el modelo)",
    ROL_INTERACCION: "Interacción (chat y avatar)",
    ROL_HIBRIDO: "Híbrido (todo aquí)",
}


# ── IPs del host ────────────────────────────────────────────────────────────────

def ips_locales() -> List[str]:
    """IPs IPv4 de este equipo en la LAN (sin loopback ni link-local)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")):
                ips.add(ip)
    except socket.gaierror:
        pass
    # Truco robusto: abrir un socket UDP "hacia fuera" revela la IP de salida.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def urls_host(puerto: int) -> List[str]:
    return [f"ws://{ip}:{puerto}" for ip in ips_locales()] or [f"ws://127.0.0.1:{puerto}"]


# ── Payload del QR ──────────────────────────────────────────────────────────────

def construir_payload(token: str, puerto: int, urls: Optional[List[str]] = None) -> str:
    return json.dumps({
        "type": TIPO_PAYLOAD, "version": P.VERSION,
        "urls": urls or urls_host(puerto), "token": token,
    }, ensure_ascii=False, separators=(",", ":"))


def leer_payload(texto: str) -> dict:
    """
    Valida y devuelve {"url", "token"} del QR (la primera URL utilizable).
    Lanza ValueError si el código no es de Lune.
    """
    try:
        d = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"código ilegible: {e}") from e
    if not isinstance(d, dict) or d.get("type") != TIPO_PAYLOAD:
        raise ValueError("este código no es de Lune")
    urls = d.get("urls") or []
    if not (isinstance(urls, list) and urls):
        raise ValueError("el código no trae ninguna URL de host")
    return {"urls": [str(u) for u in urls], "url": str(urls[0]),
            "token": str(d.get("token") or "")}


# ── mDNS (opcional) ─────────────────────────────────────────────────────────────

def zeroconf_disponible() -> bool:
    import importlib.util
    return importlib.util.find_spec("zeroconf") is not None


@dataclass
class DispositivoLune:
    """Un Lune visto en la red (o este mismo)."""
    nombre: str
    rol: str
    host: str                       # IP en la LAN
    hub_puerto: int
    capacidades: Dict[str, str] = field(default_factory=dict)
    es_este: bool = False

    @property
    def url_hub(self) -> str:
        return f"ws://{self.host}:{self.hub_puerto}"

    @property
    def modelo(self) -> str:
        return self.capacidades.get("modelo", "")

    @property
    def aloja_modelo(self) -> bool:
        return self.rol in (ROL_HOST, ROL_HIBRIDO) and bool(self.modelo)

    def descripcion(self) -> str:
        etq = ETIQUETA_ROL.get(self.rol, self.rol)
        extra = f" · {self.modelo}" if self.modelo else ""
        return f"{self.nombre} — {etq}{extra}  [{self.host}]"


def nombre_por_defecto() -> str:
    try:
        return socket.gethostname() or "lune"
    except OSError:
        return "lune"


class AnuncioLune:
    """
    Publica ESTE Lune en la LAN por mDNS, con su rol y capacidades, para que
    otros dispositivos lo descubran. No-op si zeroconf no está instalado.
    Cualquier instancia de Lune se anuncia, no solo un host.
    """
    def __init__(self, nombre: str, rol: str, hub_puerto: int,
                 capacidades: Optional[dict] = None):
        self.nombre = nombre or nombre_por_defecto()
        self.rol = rol if rol in ROLES else ROL_HIBRIDO
        self.hub_puerto = hub_puerto
        self.capacidades = dict(capacidades or {})
        self._zc = None
        self._info = None

    def _service_info(self):
        from zeroconf import ServiceInfo
        props = {"version": str(P.VERSION), "rol": self.rol,
                 "hub_puerto": str(self.hub_puerto)}
        props.update({k: str(v) for k, v in self.capacidades.items()})
        ips = ips_locales()
        # Nombre único de instancia para no colisionar con otro Lune homónimo.
        instancia = f"{self.nombre}-{self.hub_puerto}".replace(".", "-")
        return ServiceInfo(
            SERVICIO_MDNS,
            f"{instancia}.{SERVICIO_MDNS}",
            addresses=[socket.inet_aton(ip) for ip in ips] or [socket.inet_aton("127.0.0.1")],
            port=self.hub_puerto,
            properties={k.encode(): str(v).encode() for k, v in props.items()},
            server=f"{instancia}.local.",
        )

    def iniciar(self) -> bool:
        if not zeroconf_disponible():
            return False
        try:
            from zeroconf import Zeroconf
            self._zc = Zeroconf()
            self._info = self._service_info()
            self._zc.register_service(self._info)
            return True
        except Exception:
            return False

    def actualizar(self, rol: Optional[str] = None, capacidades: Optional[dict] = None):
        """Re-anuncia con rol/capacidades nuevos (p. ej. tras cambiar de modelo)."""
        if rol is not None:
            self.rol = rol if rol in ROLES else self.rol
        if capacidades is not None:
            self.capacidades = dict(capacidades)
        if self._zc is None:
            return
        try:
            nuevo = self._service_info()
            self._zc.update_service(nuevo)
            self._info = nuevo
        except Exception:
            pass

    def detener(self):
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass


def buscar_dispositivos(timeout: float = 3.0,
                        excluir_puerto: Optional[int] = None) -> List[DispositivoLune]:
    """
    Descubre los Lune en la LAN. `excluir_puerto` marca este equipo como
    `es_este=True` (por el puerto del hub) en vez de esconderlo. [] sin zeroconf.
    """
    if not zeroconf_disponible():
        return []
    try:
        import time
        from zeroconf import Zeroconf, ServiceBrowser

        encontrados: Dict[str, DispositivoLune] = {}

        class _L:
            def add_service(self, zc, tipo, nombre):
                info = zc.get_service_info(tipo, nombre, timeout=int(timeout * 1000))
                if not info:
                    return
                props = {k.decode(): (v.decode() if v else "")
                         for k, v in (info.properties or {}).items()}
                direcciones = info.parsed_addresses() or ["127.0.0.1"]
                puerto = info.port or 7777
                caps = {k: v for k, v in props.items()
                        if k not in ("version", "rol", "hub_puerto")}
                encontrados[nombre] = DispositivoLune(
                    nombre=nombre.split(".")[0].rsplit("-", 1)[0],
                    rol=props.get("rol", ROL_HIBRIDO),
                    host=direcciones[0],
                    hub_puerto=puerto,
                    capacidades=caps,
                    es_este=(excluir_puerto is not None and puerto == excluir_puerto),
                )
            def update_service(self, *a): pass
            def remove_service(self, *a): pass

        zc = Zeroconf()
        ServiceBrowser(zc, SERVICIO_MDNS, _L())
        time.sleep(timeout)
        zc.close()
        return sorted(encontrados.values(), key=lambda d: (not d.aloja_modelo, d.nombre))
    except Exception:
        return []
