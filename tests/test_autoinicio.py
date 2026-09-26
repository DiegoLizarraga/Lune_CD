"""
Tests del arranque con Windows (servicios/autoinicio.py) con un winreg FALSO:
ninguno crea ni borra entradas reales de inicio de Windows.

- `comando` por modo y con comillas (rutas con espacios, OneDrive).
- `activar` escribe Run + StartupApproved 02; 03 del Administrador de tareas
  → `activo` False.
- `reparar` corrige ruta y modo de una entrada que ya existe; nunca la crea ni
  toca StartupApproved.
- Fuera de Windows no hace nada.
"""
import sys
from pathlib import Path

import pytest

from servicios import autoinicio as ai

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APROBADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


class RegFalso:
    """La API de winreg que usa autoinicio, sobre un dict."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1
    REG_BINARY = 3

    class _Clave:
        def __init__(self, ruta):
            self.ruta = ruta

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def __init__(self, run=None, aprobado=None):
        self.claves = {RUN: {}}
        self.escrituras = []
        if run is not None:
            self.claves[RUN][ai.NOMBRE] = (run, self.REG_SZ)
        if aprobado is not None:
            self.claves[APROBADO] = {ai.NOMBRE: (aprobado, self.REG_BINARY)}

    def OpenKey(self, raiz, sub, reserved=0, access=KEY_READ):
        assert raiz == self.HKEY_CURRENT_USER, "solo HKCU"
        if sub not in self.claves:
            raise FileNotFoundError(sub)
        return self._Clave(sub)

    def CreateKeyEx(self, raiz, sub, reserved=0, access=KEY_SET_VALUE):
        assert raiz == self.HKEY_CURRENT_USER, "solo HKCU"
        self.claves.setdefault(sub, {})
        return self._Clave(sub)

    def QueryValueEx(self, clave, nombre):
        valores = self.claves.get(clave.ruta, {})
        if nombre not in valores:
            raise FileNotFoundError(nombre)
        return valores[nombre]

    def SetValueEx(self, clave, nombre, reserved, tipo, valor):
        self.claves[clave.ruta][nombre] = (valor, tipo)
        self.escrituras.append((clave.ruta, nombre, valor))

    def DeleteValue(self, clave, nombre):
        valores = self.claves.get(clave.ruta, {})
        if nombre not in valores:
            raise FileNotFoundError(nombre)
        del valores[nombre]
        self.escrituras.append((clave.ruta, nombre, None))

    # Ayudas del test
    def run(self):
        return self.claves.get(RUN, {}).get(ai.NOMBRE, (None, None))[0]

    def aprobado(self):
        return self.claves.get(APROBADO, {}).get(ai.NOMBRE, (None, None))[0]


VBS = str(ai.RAIZ / "iniciar_lune.vbs")


# ── comando ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("modo, cola", [
    ("web", " /autoinicio"),
    ("nativo", " /autoinicio"),
    ("patata", " /autoinicio /patata"),
])
def test_comando_por_modo(modo, cola):
    assert ai.comando(modo) == f'wscript.exe "{VBS}"{cola}'


def test_comando_con_espacios_va_entre_comillas():
    raiz = Path("C:/Users/Diego B/OneDrive/Lune CD")
    orden = ai.comando("web", raiz=raiz)
    assert f'"{raiz / "iniciar_lune.vbs"}"' in orden
    assert orden.startswith("wscript.exe ") and orden.endswith(" /autoinicio")


def test_comando_sin_modo_usa_el_de_la_interfaz(monkeypatch):
    monkeypatch.setattr(ai, "_modo_de_config", lambda config=None: "patata")
    assert ai.comando().endswith("/autoinicio /patata")
    monkeypatch.setattr(ai, "_modo_de_config", lambda config=None: "web")
    assert ai.comando().endswith(".vbs\" /autoinicio")


# ── activar / desactivar / estado ──────────────────────────────────────────────

def test_activar_escribe_run_y_aprobado_02():
    reg = RegFalso()
    assert ai.activar("web", reg) is True
    assert reg.run() == ai.comando("web")
    assert reg.aprobado() == bytes([0x02]) + bytes(11)
    assert reg.claves[APROBADO][ai.NOMBRE][1] == reg.REG_BINARY
    assert ai.activo(reg) is True


def test_activar_en_patata_registra_la_variante_de_terminal():
    reg = RegFalso()
    ai.activar("patata", reg)
    assert reg.run().endswith("/autoinicio /patata")


def test_deshabilitada_en_el_administrador_de_tareas_no_esta_activa():
    reg = RegFalso(run=ai.comando("web"), aprobado=bytes([0x03]) + bytes(11))
    assert ai.activo(reg) is False
    e = ai.estado("web", reg)
    assert e["registrado"] is True and e["aprobado"] is False and e["activo"] is False


def test_sin_valor_en_startupapproved_cuenta_como_aprobada():
    reg = RegFalso(run=ai.comando("web"))
    assert ai.aprobado_por_windows(reg) is True
    assert ai.activo(reg) is True


def test_reactivar_a_mano_vuelve_a_aprobarla():
    reg = RegFalso(run=ai.comando("web"), aprobado=bytes([0x03]) + bytes(11))
    assert ai.establecer(True, "web", reg) is True
    assert reg.aprobado()[0] == 0x02


def test_desactivar_borra_run_y_no_toca_startupapproved():
    reg = RegFalso(run=ai.comando("web"), aprobado=bytes([0x02]) + bytes(11))
    assert ai.desactivar(reg) is True
    assert reg.run() is None
    assert reg.aprobado() == bytes([0x02]) + bytes(11)
    assert ai.desactivar(reg) is True             # ya no estaba: sigue siendo éxito
    assert ai.activo(reg) is False


def test_establecer_devuelve_el_estado_resultante():
    reg = RegFalso()
    assert ai.establecer(True, "web", reg) is True
    assert ai.establecer(False, "web", reg) is False


def test_estado_completo():
    reg = RegFalso(run=f'wscript.exe "{VBS}" /autoinicio')
    e = ai.estado("web", reg)
    assert e == {"activo": True, "registrado": True, "aprobado": True, "ruta_ok": True, "modo_ok": True,
                 "comando": ai.comando("web"), "esperado": ai.comando("web")}
    e = ai.estado("patata", reg)
    assert e["ruta_ok"] is True and e["modo_ok"] is False
    e = ai.estado("web", RegFalso(run='wscript.exe "D:\\viejo\\iniciar_lune.vbs" /autoinicio'))
    assert e["ruta_ok"] is False
    e = ai.estado("web", RegFalso())
    assert e["registrado"] is False and e["activo"] is False and e["comando"] == ""


# ── reparar ────────────────────────────────────────────────────────────────────

def test_reparar_corrige_la_ruta_de_una_carpeta_movida():
    reg = RegFalso(run='wscript.exe "D:\\Lune viejo\\iniciar_lune.vbs" /autoinicio')
    assert ai.reparar(modo="web", reg=reg) == "ruta"
    assert reg.run() == ai.comando("web")
    assert APROBADO not in reg.claves


def test_reparar_corrige_el_modo():
    reg = RegFalso(run=ai.comando("web"))
    assert ai.reparar(modo="patata", reg=reg) == "modo"
    assert reg.run() == ai.comando("patata")
    assert ai.reparar(modo="web", reg=reg) == "modo"
    assert reg.run() == ai.comando("web")


def test_reparar_migra_la_entrada_antigua_sin_autoinicio():
    reg = RegFalso(run=f'wscript.exe "{VBS}"')
    assert ai.reparar(modo="nativo", reg=reg) == "modo"
    assert reg.run() == ai.comando("nativo")


def test_reparar_lee_el_modo_de_la_config():
    reg = RegFalso(run=ai.comando("web"))
    assert ai.reparar({"interfaz": {"modo": "patata"}}, reg=reg) == "modo"
    assert reg.run() == ai.comando("patata")


def test_reparar_nunca_crea_la_entrada():
    reg = RegFalso()
    assert ai.reparar(modo="web", reg=reg) == ""
    assert reg.escrituras == [] and reg.run() is None


def test_reparar_no_toca_startupapproved_aunque_este_deshabilitada():
    tres = bytes([0x03]) + bytes(11)
    reg = RegFalso(run='wscript.exe "E:\\otra\\iniciar_lune.vbs" /autoinicio', aprobado=tres)
    assert ai.reparar(modo="web", reg=reg) == "ruta"
    assert reg.aprobado() == tres
    assert ai.activo(reg) is False
    assert all(ruta == RUN for ruta, _n, _v in reg.escrituras)


def test_reparar_sin_nada_que_hacer_no_escribe():
    reg = RegFalso(run=ai.comando("web"))
    assert ai.reparar(modo="web", reg=reg) == ""
    assert reg.escrituras == []


# ── Fuera de Windows ───────────────────────────────────────────────────────────

def test_fuera_de_windows_no_hace_nada(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert ai.activo() is False
    assert ai.activar("web") is False
    assert ai.desactivar() is False
    assert ai.establecer(True, "web") is False
    assert ai.reparar(modo="web") == ""
    assert ai.valor_registrado() is None
    assert ai.aprobado_por_windows() is False
    e = ai.estado("web")
    assert e["activo"] is False and e["registrado"] is False
