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
from typing import List, Optional

from . import protocolo as P

TIPO_PAYLOAD = "lune:server-channel"
SERVICIO_MDNS = "_lunecd._tcp.local."


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


class AnuncioHost:
    """Publica el host en la LAN por mDNS. No-op si zeroconf no está."""
    def __init__(self, puerto: int, nombre: str = "Lune"):
        self.puerto = puerto
        self.nombre = nombre
        self._zc = None
        self._info = None

    def iniciar(self) -> bool:
        if not zeroconf_disponible():
            return False
        try:
            from zeroconf import Zeroconf, ServiceInfo
            ips = ips_locales()
            if not ips:
                return False
            self._zc = Zeroconf()
            self._info = ServiceInfo(
                SERVICIO_MDNS,
                f"{self.nombre}.{SERVICIO_MDNS}",
                addresses=[socket.inet_aton(ip) for ip in ips],
                port=self.puerto,
                properties={"version": str(P.VERSION)},
            )
            self._zc.register_service(self._info)
            return True
        except Exception:
            return False

    def detener(self):
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass


def buscar_hosts(timeout: float = 3.0) -> List[dict]:
    """Busca hosts de Lune en la LAN. [] si zeroconf no está o no hay ninguno."""
    if not zeroconf_disponible():
        return []
    try:
        import time
        from zeroconf import Zeroconf, ServiceBrowser
        encontrados = {}

        class _L:
            def add_service(self, zc, tipo, nombre):
                info = zc.get_service_info(tipo, nombre, timeout=int(timeout * 1000))
                if not info:
                    return
                for addr in info.parsed_addresses():
                    encontrados[nombre] = {"nombre": nombre.split(".")[0],
                                           "url": f"ws://{addr}:{info.port}"}
                    break
            def update_service(self, *a): pass
            def remove_service(self, *a): pass

        zc = Zeroconf()
        ServiceBrowser(zc, SERVICIO_MDNS, _L())
        time.sleep(timeout)
        zc.close()
        return list(encontrados.values())
    except Exception:
        return []
