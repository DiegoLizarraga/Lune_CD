"""
Tests de ui/panel_vida_nativo.PanelVidaNativo (offscreen): carga la config, cada
apartado escribe UNA vez (config.config + save) tras el retardo y emite `cambiado`
aplicando en caliente (`recargar_config` del controlador), el aviso anticheat al
encender «sentarse en ventanas», la validación del Application ID y del enlace, el
estado del arranque con Windows (StartupApproved) y la línea «Discord ve» con solo
los textos fijos. Funciona sin controladores y con los que llegan tarde.
"""
import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from nucleo.config import Config  # noqa: E402
from ui import panel_vida_nativo as pvn  # noqa: E402
from ui.panel_vida_nativo import PanelVidaNativo  # noqa: E402

ID = "123456789012345678"


class ConfigDisco:
    """Como nucleo.config.Config: `.config` (dict) + `save()`."""

    def __init__(self):
        self.config = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.guardados = 0

    def get(self, s, k, d=None):
        return self.config.get(s, {}).get(k, d)

    def save(self):
        self.guardados += 1


class AsientoFalso(QObject):
    cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.sentada = ""

    def estado(self):
        return {"sentada": self.sentada, "disponible": True, "juego": False}

    def sentar(self, sitio):
        self.diario.append(("sentar", sitio))
        self.sentada = sitio
        return True, "Me senté en la barra de tareas."

    def bajar(self, motivo="usuario"):
        self.diario.append("bajar")
        estaba, self.sentada = bool(self.sentada), ""
        return estaba

    def recargar_config(self):
        self.diario.append("recargar")


class ComidaFalsa(QObject):
    cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.act = None
        self.ultimo_motivo = ""

    def estado(self):
        a = self.act
        return {"activa": a is not None, "id": a[0] if a else "", "variante": a[1] if a else "", "disponible": True}

    def alternar(self, id_):
        self.diario.append(("alternar", id_))
        self.act = (id_, "mango") if id_ == "batido" else (id_, "limon")
        return "aparece"

    def guardar(self, sonido=True):
        self.diario.append("guardar")
        self.act = None
        return True

    def recargar_config(self):
        self.diario.append("recargar")


class DiscordFalso(QObject):
    estado_cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.e = {"activo": True, "conectado": True, "usuario": "diego", "error": "",
                  "publicando": {"details": "Lune CD · Escritorio · 3D", "state": "Bailando ♪"}, "vista_previa": None}

    def estado(self):
        return dict(self.e)

    def recargar_config(self):
        self.diario.append("recargar")


class AutoinicioFalso:
    def __init__(self, **e):
        self.e = {"activo": False, "registrado": False, "aprobado": True, "ruta_ok": False, **e}
        self.modos = []

    def estado(self, modo=None, reg=None):
        self.modos.append(modo)
        return dict(self.e)


def panel(qapp, cfg=None, **kw):
    kw.setdefault("autoinicio", AutoinicioFalso())
    kw.setdefault("retardo_ms", 30)
    return PanelVidaNativo(cfg if cfg is not None else ConfigDisco(), **kw)


def esperar_guardado(p):
    QTest.qWait(80)
    assert not p.pendiente


def test_carga_la_config(qapp):
    cfg = ConfigDisco()
    cfg.config["avatar"].update(sentarse_ventanas=True, sentarse_barra=False, sentarse_offset_px=99)
    cfg.config["discord"].update(activo=True, client_id=ID, mostrar_modelo=True, boton_url="javascript:x")
    cfg.config["sistema"].update(autoinicio_como="asistente", autoinicio_retraso_s=45)
    cfg.config["comida"]["activa"] = False
    p = panel(qapp, cfg)
    assert p.chk_ventanas.isChecked() and not p.chk_barra.isChecked()
    assert p.spin_offset.value() == 64                              # acotado
    assert not p.aviso_anticheat.isVisibleTo(p), "cargar la config no avisa"
    assert not p.chk_comida.isChecked()
    assert p.chk_discord.isChecked() and p.linea_id.text() == ID and p.chk_modelo.isChecked()
    assert p.linea_url.text() == "", "un enlace que no es https no se enseña"
    assert p.combo_como.currentData() == "asistente" and p.spin_espera.value() == 45
    assert not p.pendiente and cfg.guardados == 0


def test_cada_apartado_escribe_una_vez_y_aplica(qapp):
    cfg = ConfigDisco()
    a, c, d = AsientoFalso(), ComidaFalsa(), DiscordFalso()
    p = panel(qapp, cfg, asiento=a, comida=c, discord=d)
    cambiados = []
    p.cambiado.connect(cambiados.append)
    p.chk_barra.setChecked(False)
    p.spin_offset.setValue(-10)
    p.spin_offset.setValue(-12)
    p.chk_comida.setChecked(False)
    p.chk_modelo.setChecked(True)
    p.combo_como.setCurrentIndex(p.combo_como.findData("ventana"))
    p.spin_espera.setValue(60)
    assert cfg.guardados == 0, "espera a que se quede quieto"
    esperar_guardado(p)
    assert cfg.guardados == 1
    assert cfg.config["avatar"]["sentarse_barra"] is False and cfg.config["avatar"]["sentarse_offset_px"] == -12
    assert cfg.config["comida"]["activa"] is False and cfg.config["discord"]["mostrar_modelo"] is True
    assert cfg.config["sistema"]["autoinicio_como"] == "ventana" and cfg.config["sistema"]["autoinicio_retraso_s"] == 60
    assert cambiados == ["asiento", "comida", "discord", "arranque"]
    assert a.diario.count("recargar") == 1 and c.diario.count("recargar") == 1 and d.diario.count("recargar") == 1
    assert p.guardar_ya() == []                                      # nada pendiente


def test_aviso_anticheat_al_encender_ventanas(qapp):
    cfg = ConfigDisco()
    p = panel(qapp, cfg)
    p.chk_ventanas.setChecked(True)
    assert p.aviso_anticheat.isVisibleTo(p)
    assert "anticheat" in p.aviso_anticheat.text() and "no mira nada" in p.aviso_anticheat.text()
    p.guardar_ya()
    assert cfg.config["avatar"]["sentarse_ventanas"] is True
    p.chk_ventanas.setChecked(False)
    assert not p.aviso_anticheat.isVisibleTo(p)


def test_application_id_y_enlace_validados(qapp):
    cfg = ConfigDisco()
    p = panel(qapp, cfg)
    p.linea_id.setText("12345")
    assert "17 a 20 cifras" in p.error_discord.text()
    p.guardar_ya()
    assert cfg.config["discord"]["client_id"] == "" and cfg.guardados == 0
    p.linea_id.setText(ID)
    assert p.error_discord.text() == ""
    p.linea_url.setText("http://lune.example.com")
    assert "https://" in p.error_discord.text()
    p.guardar_ya()
    assert cfg.config["discord"]["client_id"] == ID and cfg.config["discord"]["boton_url"] == ""
    p.linea_url.setText("https://lune.example.com/lune")
    p.linea_id.setText("")                                           # borrar el ID vale
    p.guardar_ya()
    assert cfg.config["discord"]["boton_url"] == "https://lune.example.com/lune"
    assert cfg.config["discord"]["client_id"] == ""


def test_discord_ve_solo_textos_fijos(qapp):
    d = DiscordFalso()
    cfg = ConfigDisco()
    p = panel(qapp, cfg, discord=d)
    assert p.discord_ve.text() == "Discord ve: Lune CD · Escritorio · 3D — Bailando ♪"
    assert "Falta el Application ID" in p.estado_discord.text(), "D1: sin ID no publica"
    cfg.config["discord"]["client_id"] = ID
    d.estado_cambio.emit("{}")
    assert "Conectado como diego" in p.estado_discord.text()
    d.e["publicando"] = {"details": "Lune CD · Ventana", "state": "Banco Santander - Google Chrome"}
    d.estado_cambio.emit("{}")
    assert "Chrome" not in p.discord_ve.text() and p.discord_ve.text().startswith("Discord ve: nada")
    d.e["activo"] = False
    d.estado_cambio.emit("{}")
    assert p.discord_ve.text() == "Discord ve: nada (apagado)."
    assert pvn.texto_discord_ve({"activo": True, "vista_previa": {"details": "Lune CD · Ventana", "state": "Charlando"}}) \
        == "Discord ve: Lune CD · Ventana — Charlando"


def test_estado_del_arranque(qapp):
    casos = [
        ({"registrado": True, "aprobado": False, "ruta_ok": True}, "Administrador de tareas"),
        ({"registrado": True, "aprobado": True, "ruta_ok": False}, "otra carpeta"),
        ({"registrado": True, "aprobado": True, "ruta_ok": True, "activo": True}, "Activado"),
        ({}, "Desactivado"),
    ]
    for e, texto in casos:
        auto = AutoinicioFalso(**e)
        cfg = ConfigDisco()
        cfg.config["interfaz"]["modo"] = "br"
        p = panel(qapp, cfg, autoinicio=auto)
        assert texto in p.estado_arranque.text(), (e, p.estado_arranque.text())
        assert auto.modos and auto.modos[-1] == "br"


def test_botones_llegan_a_los_controladores(qapp):
    a, c = AsientoFalso(), ComidaFalsa()
    p = panel(qapp, asiento=a, comida=c)
    assert p.btn_sentarse.isVisibleTo(p) and not p.btn_bajar.isVisibleTo(p)
    assert p.sentarse() is True and a.diario == [("sentar", "barra")]
    assert p.estado_asiento.text() == "Me senté en la barra de tareas."
    a.cambio.emit("{}")
    assert "Sentada en la barra" in p.estado_asiento.text()
    assert p.btn_bajar.isVisibleTo(p) and not p.btn_sentarse.isVisibleTo(p)
    assert p.bajar() is True
    assert p.comer("batido") == "aparece" and ("alternar", "batido") in c.diario
    assert "batido de mango" in p.estado_comida.text()
    assert p.guardar_comida() is True and "guardar" in c.diario
    assert not p.btn_guardar_comida.isEnabled()


def test_sin_controladores_y_enlazar_tarde(qapp):
    cfg = ConfigDisco()
    p = panel(qapp, cfg)
    assert not p.btn_sentarse.isVisibleTo(p) and not p.btn_batido.isVisibleTo(p)
    assert p.sentarse() is False and p.comer("batido") == "" and p.guardar_comida() is False
    assert p.discord_ve.text() == "Discord ve: nada (apagado)."
    a, c, d = AsientoFalso(), ComidaFalsa(), DiscordFalso()
    p.enlazar(SimpleNamespace(vida=SimpleNamespace(asiento=a, comida=c, discord=d)))
    assert p.asiento is a and p.comida is c and p.discord is d
    assert p.btn_sentarse.isVisibleTo(p) and p.btn_batido.isVisibleTo(p)
    assert p.discord_ve.text().startswith("Discord ve: Lune CD")
    a.sentada = "ventana"
    a.cambio.emit("{}")
    assert "Sentada en una ventana" in p.estado_asiento.text()
    p.enlazar(None)                                                   # soltar
    a.sentada = "barra"
    a.cambio.emit("{}")
    assert "Sentada" not in p.estado_asiento.text()


def test_se_suelta_solo_al_desmontar_los_servicios(qapp):
    a, c, d = AsientoFalso(), ComidaFalsa(), DiscordFalso()
    s4 = SimpleNamespace(vida=SimpleNamespace(asiento=a, comida=c, discord=d), _deshacer=[])
    p = panel(qapp, discord=None)
    p.enlazar(s4)
    p.enlazar(s4)                                                     # un solo enganche
    assert len(s4._deshacer) == 1 and p.asiento is a
    for f in reversed(s4._deshacer):                                  # ServiciosCorte4.desmontar
        f()
    assert p.asiento is None and p.comida is None and p.discord is None
    # si ya tiene otros, no los suelta
    otros = SimpleNamespace(asiento=AsientoFalso(), comida=None, discord=None, _deshacer=[])
    p.enlazar(otros)
    s4._deshacer[0]()
    assert p.asiento is otros.asiento


def test_ocultar_guarda_lo_pendiente(qapp):
    cfg = ConfigDisco()
    p = panel(qapp, cfg, retardo_ms=10000)
    p.show()
    p.chk_barra.setChecked(False)
    assert p.pendiente
    p.hide()
    assert not p.pendiente and cfg.config["avatar"]["sentarse_barra"] is False
