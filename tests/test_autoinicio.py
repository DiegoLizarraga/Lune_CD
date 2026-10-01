"""
Tests del arranque con Windows (servicios/autoinicio.py) con un winreg FALSO:
ninguno crea ni borra entradas reales de inicio de Windows.

- `comando` por modo y con comillas (rutas con espacios, OneDrive).
- `activar` escribe Run + StartupApproved 02; 03 del Administrador de tareas
  → `activo` False.
- `reparar` corrige ruta y modo de una entrada que ya existe; nunca la crea ni
  toca StartupApproved.
- Instalada (nucleo/rutas.INSTALADA, con rutas parcheadas): «Lune.exe» --autoinicio en
  todos los modos; una instalación y una copia del código no se quitan la entrada.
- Fuera de Windows no hace nada.
"""
import sys
from pathlib import Path

import pytest

from nucleo import rutas
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


# ── Tipos de entrada: la del código (.vbs) y la instalada (.exe) ───────────────

def test_tipo_de_cada_entrada():
    assert ai.tipo_de('wscript.exe "C:\\x\\iniciar_lune.vbs" /autoinicio') == ai.TIPO_CODIGO
    assert ai.tipo_de('"C:\\Windows\\System32\\wscript.exe" "C:\\x\\iniciar_lune.vbs"') == ai.TIPO_CODIGO
    assert ai.tipo_de('"C:\\Programas\\Lune CD\\Lune.exe" --autoinicio') == ai.TIPO_INSTALADA
    assert ai.tipo_de("algo que no reconozco") is None
    assert ai.tipo_propio() == ai.TIPO_CODIGO                   # los tests corren desde el código
    assert ai.lanzador() == ai.RAIZ / "iniciar_lune.vbs"


def test_desde_el_codigo_no_se_apropia_de_la_instalada():
    instalada = '"C:\\Users\\Diego\\AppData\\Local\\Programs\\Lune CD\\Lune.exe" --autoinicio'
    reg = RegFalso(run=instalada)
    assert ai.reparar(modo="patata", reg=reg) == ""
    assert reg.escrituras == [] and reg.run() == instalada
    assert ai.activo(reg) is False and ai.estado("web", reg)["activo"] is False
    assert ai.desactivar(reg) is True and reg.run() == instalada     # apagarla aquí no borra la otra
    assert ai.establecer(True, "web", reg) is True                   # encenderla a mano sí la cambia
    assert reg.run() == ai.comando("web")


def test_activo_exige_que_sea_de_esta_carpeta():
    reg = RegFalso(run='wscript.exe "D:\\otra copia\\iniciar_lune.vbs" /autoinicio')
    assert ai.activo(reg) is False
    assert ai.reparar(modo="web", reg=reg) == "ruta"
    assert ai.activo(reg) is True


def test_una_entrada_que_no_reconozco_se_repara_como_siempre():
    reg = RegFalso(run="C:\\viejo\\iniciar_lune.vbs /autoinicio")            # sin comillas
    assert ai.reparar(modo="web", reg=reg) == "ruta"
    assert reg.run() == ai.comando("web")


def test_el_respaldo_del_modo_lee_el_config_de_los_datos(monkeypatch, tmp_path):
    import nucleo.config as nc
    monkeypatch.delattr(nc, "RUTA_CONFIG")                            # sin nucleo.config utilizable
    monkeypatch.setattr(rutas, "DATOS", tmp_path)
    (tmp_path / "config.json").write_text('{"interfaz": {"modo": "patata"}}', "utf-8")
    assert ai.comando().endswith("/autoinicio /patata")


# ── Instalada (Lune.exe) ───────────────────────────────────────────────────────

@pytest.fixture
def instalada(monkeypatch, tmp_path):
    """Lune instalada en una carpeta temporal, con un Lune.exe de mentira."""
    carpeta = tmp_path / "Programs" / "Lune CD"
    carpeta.mkdir(parents=True)
    (carpeta / "Lune.exe").write_bytes(b"")
    monkeypatch.setattr(rutas, "INSTALADA", True)
    monkeypatch.setattr(ai, "RAIZ", carpeta)
    return carpeta


def test_instalada_la_orden_es_lune_exe_en_todos_los_modos(instalada):
    exe = instalada / "Lune.exe"
    for modo in ("web", "nativo", "patata", None):
        assert ai.comando(modo) == f'"{exe}" --autoinicio'
    assert ai.tipo_propio() == ai.TIPO_INSTALADA and ai.lanzador() == exe


def test_instalada_activar_escribe_lune_exe_tambien_en_patata(instalada):
    reg = RegFalso()
    assert ai.activar("patata", reg) is True
    assert reg.run() == f'"{instalada / "Lune.exe"}" --autoinicio'
    assert reg.aprobado() == ai.APROBADO_SI and ai.activo(reg) is True
    e = ai.estado("patata", reg)
    assert e["activo"] and e["ruta_ok"] and e["modo_ok"]


def test_instalada_sin_lune_exe_no_activa_ni_repara(instalada):
    (instalada / "Lune.exe").unlink()
    reg = RegFalso()
    assert ai.activar("web", reg) is False and reg.run() is None
    reg = RegFalso(run='"C:\\Viejo\\Lune CD\\Lune.exe" --autoinicio')
    assert ai.reparar(modo="web", reg=reg) == "" and reg.escrituras == []


def test_instalada_repara_una_instalacion_movida_o_sin_autoinicio(instalada):
    reg = RegFalso(run='"C:\\Viejo\\Lune CD\\Lune.exe" --autoinicio')
    assert ai.reparar(modo="web", reg=reg) == "ruta"
    assert reg.run() == ai.comando("web") and APROBADO not in reg.claves
    reg = RegFalso(run=f'"{instalada / "Lune.exe"}"')
    assert ai.reparar(modo="patata", reg=reg) == "modo"
    assert reg.run() == ai.comando("patata")
    assert ai.reparar(modo="patata", reg=reg) == ""                   # ya está bien: no reescribe


def test_instalada_no_se_apropia_de_la_del_codigo(instalada):
    del_codigo = f'wscript.exe "{VBS}" /autoinicio /patata'
    reg = RegFalso(run=del_codigo)
    assert ai.reparar(modo="web", reg=reg) == ""
    assert reg.escrituras == [] and reg.run() == del_codigo
    assert ai.activo(reg) is False
    assert ai.desactivar(reg) is True and reg.run() == del_codigo
    assert ai.establecer(True, "web", reg) is True
    assert reg.run() == f'"{instalada / "Lune.exe"}" --autoinicio'


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
