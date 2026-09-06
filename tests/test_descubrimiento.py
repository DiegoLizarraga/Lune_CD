"""Tests del emparejamiento por QR, el servidor web y el descubrimiento."""
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import descubrimiento as D  # noqa: E402
from lune_core.web_server import ServidorWeb  # noqa: E402


# ── Payload del QR ──────────────────────────────────────────────────────────────

def test_ida_y_vuelta_del_qr():
    p = D.construir_payload("tok-123", 7777, urls=["ws://192.168.1.50:7777", "ws://10.0.0.5:7777"])
    d = D.leer_payload(p)
    assert d["url"] == "ws://192.168.1.50:7777"
    assert d["urls"] == ["ws://192.168.1.50:7777", "ws://10.0.0.5:7777"]
    assert d["token"] == "tok-123"


def test_qr_de_otra_cosa_se_rechaza():
    import json
    with pytest.raises(ValueError, match="no es de Lune"):
        D.leer_payload(json.dumps({"type": "otra:cosa", "urls": ["ws://x"]}))


def test_qr_ilegible():
    with pytest.raises(ValueError):
        D.leer_payload("no es json")


def test_qr_sin_urls():
    import json
    with pytest.raises(ValueError, match="URL"):
        D.leer_payload(json.dumps({"type": D.TIPO_PAYLOAD, "urls": []}))


def test_urls_host_incluye_puerto():
    urls = D.urls_host(7777)
    assert all(u.startswith("ws://") and u.endswith(":7777") for u in urls)


# ── Servidor web ────────────────────────────────────────────────────────────────

def test_sirve_el_terminal_e_inyecta_el_puerto_del_hub():
    web = ServidorWeb(puerto_ws=7777, host="127.0.0.1", puerto=0)
    assert web.iniciar()
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{web.puerto}/", timeout=5).read().decode("utf-8")
        assert "LUNE CD" in html and "terminal web" in html
        assert "window.LUNE_WS_PORT=7777" in html    # apunta al hub correcto
    finally:
        web.detener()


def test_dos_servidores_no_chocan_de_puerto():
    a = ServidorWeb(7777, host="127.0.0.1", puerto=0); assert a.iniciar()
    b = ServidorWeb(7777, host="127.0.0.1", puerto=0); assert b.iniciar()
    assert a.puerto != b.puerto
    a.detener(); b.detener()


# ── mDNS (solo si zeroconf está) ───────────────────────────────────────────────

def test_descubrimiento_degrada_sin_zeroconf():
    """Sin zeroconf, buscar no revienta: devuelve lista vacía."""
    if D.zeroconf_disponible():
        pytest.skip("zeroconf instalado; este test cubre el modo degradado")
    assert D.buscar_hosts(timeout=0.1) == []
