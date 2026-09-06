"""Tests del descubrimiento de dispositivos y la asignación de roles."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import descubrimiento as D  # noqa: E402


# ── Roles ↔ modos ───────────────────────────────────────────────────────────────

def test_rol_a_modo_y_vuelta():
    from servicios.red_service import rol_a_modo, modo_a_rol
    assert rol_a_modo(D.ROL_HOST) == "host"
    assert rol_a_modo(D.ROL_INTERACCION) == "terminal"
    assert rol_a_modo(D.ROL_HIBRIDO) == "local"
    assert modo_a_rol("host") == D.ROL_HOST
    assert modo_a_rol("terminal") == D.ROL_INTERACCION
    assert modo_a_rol("local") == D.ROL_HIBRIDO


# ── Dispositivo ─────────────────────────────────────────────────────────────────

def test_dispositivo_aloja_modelo_segun_rol_y_modelo():
    host = D.DispositivoLune("ally", D.ROL_HOST, "192.168.1.5", 7777, {"modelo": "qwen2.5:7b"})
    assert host.aloja_modelo and host.url_hub == "ws://192.168.1.5:7777"
    inter = D.DispositivoLune("laptop", D.ROL_INTERACCION, "192.168.1.6", 7777, {})
    assert not inter.aloja_modelo
    host_sin_modelo = D.DispositivoLune("x", D.ROL_HOST, "1.2.3.4", 7777, {})
    assert not host_sin_modelo.aloja_modelo   # host pero sin modelo declarado


# ── Anuncio + descubrimiento reales (mDNS en esta máquina) ─────────────────────

@pytest.mark.skipif(not D.zeroconf_disponible(), reason="zeroconf no instalado")
def test_anunciar_y_descubrir():
    a1 = D.AnuncioLune("host-test", D.ROL_HOST, 7801, {"modelo": "qwen2.5:7b"})
    a2 = D.AnuncioLune("inter-test", D.ROL_INTERACCION, 7802, {"vrm": "1"})
    assert a1.iniciar() and a2.iniciar()
    try:
        time.sleep(1.2)
        disp = D.buscar_dispositivos(timeout=2.0, excluir_puerto=7802)
        por_puerto = {d.hub_puerto: d for d in disp}
        assert 7801 in por_puerto and 7802 in por_puerto
        host = por_puerto[7801]
        assert host.rol == D.ROL_HOST and host.modelo == "qwen2.5:7b" and host.aloja_modelo
        assert por_puerto[7802].es_este is True     # excluir_puerto lo marcó
        # los que alojan modelo van primero
        assert disp[0].aloja_modelo
    finally:
        a1.detener(); a2.detener()


@pytest.mark.skipif(not D.zeroconf_disponible(), reason="zeroconf no instalado")
def test_actualizar_rol_se_refleja():
    a = D.AnuncioLune("cambia-test", D.ROL_HIBRIDO, 7803, {})
    assert a.iniciar()
    try:
        a.actualizar(rol=D.ROL_HOST, capacidades={"modelo": "llama3.1"})
        time.sleep(1.2)
        disp = {d.hub_puerto: d for d in D.buscar_dispositivos(timeout=2.0)}
        assert disp[7803].rol == D.ROL_HOST and disp[7803].modelo == "llama3.1"
    finally:
        a.detener()


def test_degradacion_sin_zeroconf(monkeypatch):
    """Si zeroconf no está, ni anunciar ni buscar revientan."""
    monkeypatch.setattr(D, "zeroconf_disponible", lambda: False)
    a = D.AnuncioLune("x", D.ROL_HOST, 7777)
    assert a.iniciar() is False
    assert D.buscar_dispositivos(timeout=0.1) == []
