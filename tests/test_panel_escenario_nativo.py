"""
Tests de ui/panel_escenario_nativo.PanelEscenarioNativo (offscreen): carga config.json y los
datos del bot (datos.json falso), cada apartado escribe UNA vez tras 300 ms quieto (config.json
en una escritura; datos.json con guardar_minecraft) y emite `cambiado` aplicando en caliente
(`recargar_config`), la validación (latest.log, nicks, versión, servidor; el error de
guardar_minecraft a la vista), el aviso de suplantación con «solo el dueño», el aviso «sin
esqueleto», la biblioteca como texto plano, los botones hacia los controladores (el bot solo se
instala con su botón) y `enlazar` tardío que se suelta solo al desmontar.
"""
import copy
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, Qt, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from nucleo.config import Config  # noqa: E402
from ui import panel_escenario_nativo as pen  # noqa: E402
from ui.panel_escenario_nativo import PanelEscenarioNativo  # noqa: E402

ID = "0123456789ab"
ID2 = "fedcba987654"


class ConfigDisco:
    """Como nucleo.config.Config: `.config` (dict) + `save()`."""

    def __init__(self):
        self.config = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.guardados = 0

    def get(self, s, k, d=None):
        return self.config.get(s, {}).get(k, d)

    def save(self):
        self.guardados += 1


class DatosFalsos:
    def __init__(self):
        self.mc = {"host": "mi.server.net", "port": 25570, "version": "1.21.1", "usuario": "Lune_bot",
                   "dueno": "Diego_01", "pensar_cada_s": 90, "defender": False, "solo_dueno": True,
                   "estilo_frases": "sobrio", "visor": False}
        self.guardados = []
        self.error = None

    def minecraft(self):
        return dict(self.mc)

    def guardar_minecraft(self, cambios):
        self.guardados.append(dict(cambios))
        if self.error:
            raise ValueError(self.error)
        self.mc.update(cambios)
        return dict(self.mc)


class MMDFalso(QObject):
    estado_cambio = pyqtSignal(str)
    biblioteca_cambio = pyqtSignal(str)
    importado = pyqtSignal(str)
    vista_pedida = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.e = {"fase": "parado"}

    def estado(self):
        return dict(self.e)

    def refrescar(self):
        self.diario.append("refrescar")

    def reproducir(self, id_=None, *, origen="usuario"):
        self.diario.append(("reproducir", id_, origen))
        return True, "¡A bailar!"

    def pausa(self, on=None):
        self.diario.append("pausa")
        return True

    def parar(self):
        self.diario.append("parar")
        return True

    def siguiente(self):
        self.diario.append("siguiente")
        return False, "No hay más bailes."

    def anterior(self):
        self.diario.append("anterior")
        return True, "¡A bailar!"

    def favorito(self, id_, on):
        self.diario.append(("favorito", id_, on))
        return True

    def desactivar(self, id_, on):
        self.diario.append(("desactivar", id_, on))
        return True

    def quitar(self, id_):
        self.diario.append(("quitar", id_))
        return True, "Lo moví a bailes/.quitados."

    def importar_dialogo(self, parent=None):
        self.diario.append(("importar", parent is not None))

    def abrir_carpeta(self):
        self.diario.append("carpeta")
        return True

    def recargar_config(self):
        self.diario.append("recargar")


class MCFalso(QObject):
    estado_cambio = pyqtSignal(str)
    evento = pyqtSignal(str)
    chat = pyqtSignal(str)
    log_bot = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.bot = {"instalado": False, "instalando": False, "conectado": False, "conectando": False,
                    "servidor": "", "nick": "", "error": ""}

    def estado(self):
        return {"reaccionar": True, "log": {"activo": True, "yo": "Diego_01", "ruta": "x"}, "bot": dict(self.bot),
                "requisitos": {"node": "v24.19.0", "node_ok": True, "npm": True}}

    def instalar_bot(self):
        self.diario.append("instalar")
        self.bot["instalando"] = True

    def conectar_bot(self):
        self.diario.append("conectar")
        return False, "Pon tu nick de Minecraft (dueño) en Ajustes → Minecraft."

    def desconectar_bot(self):
        self.diario.append("desconectar")
        return False

    def recargar_config(self):
        self.diario.append("recargar")


def panel(qapp, cfg=None, **kw):
    kw.setdefault("retardo_ms", 30)
    kw.setdefault("datos", DatosFalsos())
    return PanelEscenarioNativo(cfg if cfg is not None else ConfigDisco(), **kw)


def esperar(ms=80):
    QTest.qWait(ms)


def test_carga_config_y_datos(qapp):
    cfg = ConfigDisco()
    cfg.config["baile"].update(volumen=0.4, en_el_sitio=False)
    cfg.config["baile"]["al_terminar"] = "aleatorio"
    cfg.config["minecraft"].update(reaccionar=True, ruta_log="C:/mc/logs/latest.log")
    p = panel(qapp, cfg)
    assert p.slider_vol.value() == 40 and p.lbl_vol.text() == "40 %"
    assert p.combo_al_terminar.currentData() == "aleatorio" and not p.chk_en_sitio.isChecked()
    assert p.checks_mc["reaccionar"].isChecked() and p.checks_mc["decir_en_juego"].isChecked()
    assert p.linea_log.text() == "C:/mc/logs/latest.log"
    assert (p.linea_host.text(), p.spin_puerto.value(), p.linea_version.text()) == ("mi.server.net", 25570, "1.21.1")
    assert (p.linea_usuario.text(), p.linea_dueno.text(), p.spin_pensar.value()) == ("Lune_bot", "Diego_01", 90)
    assert not p.chk_defender.isChecked() and p.combo_estilo.currentData() == "sobrio"
    assert not p.pendiente and cfg.guardados == 0 and p._datos.guardados == []


def test_bailes_escribe_una_vez_a_los_300_ms_y_aplica(qapp):
    cfg = ConfigDisco()
    m = MMDFalso()
    p = PanelEscenarioNativo(cfg, datos=DatosFalsos())            # el retardo de verdad: 300 ms
    p.enlazar(mmd=m)
    cambios = []
    p.cambiado.connect(cambios.append)
    p.slider_vol.setValue(70)
    p.combo_al_terminar.setCurrentIndex(p.combo_al_terminar.findData("repetir"))
    p.chk_en_sitio.setChecked(False)
    QTest.qWait(150)
    assert cfg.guardados == 0 and p.pendiente
    QTest.qWait(300)
    assert cfg.guardados == 1 and not p.pendiente
    assert (cfg.get("baile", "volumen"), cfg.get("baile", "al_terminar"), cfg.get("baile", "en_el_sitio")) == (0.7, "repetir", False)
    assert cambios == ["bailes"] and m.diario.count("recargar") == 1
    assert p.ultimo_guardado["bailes"] == {("baile", "volumen"): 0.7, ("baile", "al_terminar"): "repetir",
                                           ("baile", "en_el_sitio"): False}


def test_minecraft_config_y_bot_en_una_escritura_cada_uno(qapp, tmp_path):
    cfg = ConfigDisco()
    mc = MCFalso()
    datos = DatosFalsos()
    p = panel(qapp, cfg, datos=datos)
    p.enlazar(minecraft=mc)
    cambios = []
    p.cambiado.connect(cambios.append)
    p.checks_mc["reaccionar"].setChecked(True)
    p.checks_mc["pensar_en_juego"].setChecked(True)
    p.linea_log.setText(str(tmp_path / "logs" / "latest.log"))
    p.linea_host.setText("localhost")
    p.spin_puerto.setValue(25565)
    p.linea_dueno.setText("Steve_99")
    p.chk_defender.setChecked(True)
    p.spin_pensar.setValue(120)
    p.combo_estilo.setCurrentIndex(p.combo_estilo.findData("personaje"))
    esperar()
    assert cfg.guardados == 1 and cfg.get("minecraft", "reaccionar") is True
    assert cfg.get("minecraft", "pensar_en_juego") is True
    assert cfg.get("minecraft", "ruta_log") == str(tmp_path / "logs" / "latest.log")
    assert datos.guardados == [{"host": "localhost", "port": 25565, "dueno": "Steve_99", "defender": True,
                                "pensar_cada_s": 120, "estilo_frases": "personaje"}]
    assert cambios == ["minecraft"] and mc.diario.count("recargar") == 1


def test_validacion_de_minecraft(qapp):
    cfg = ConfigDisco()
    datos = DatosFalsos()
    p = panel(qapp, cfg, datos=datos)
    p.linea_log.setText("C:/Windows/win.ini")
    assert "latest.log" in p.error_log.text()
    p.linea_log.setText("\\\\servidor\\mc\\logs\\latest.log")
    assert "red" in p.error_log.text()
    p.linea_usuario.setText("yo")
    assert "3 a 16" in p.error_bot.text()
    p.linea_version.setText("última")
    assert "1.21.1" in p.error_bot.text()
    p.linea_host.setText("http://mi.server")
    assert "http" in p.error_bot.text()
    esperar()
    assert cfg.guardados == 0 and datos.guardados == [], "nada inválido se guarda"
    # lo que rechaza guardar_minecraft sale a la vista
    datos.error = "El bot no puede llamarse igual que tú (su dueño)."
    p.linea_usuario.setText("Diego_01")
    esperar()
    assert datos.guardados and p.error_bot.text().startswith("El bot no puede llamarse")


def test_aviso_de_suplantacion_y_de_online_mode(qapp):
    p = panel(qapp)
    p.show()
    try:
        assert p.chk_solo_dueno.isChecked() and p.aviso_suplantacion.isVisible()
        assert "online-mode=false" in p.aviso_suplantacion.text()
        assert "cualquiera puede ponerse tu nick" in p.aviso_suplantacion.text()
        p.chk_solo_dueno.setChecked(False)
        assert not p.aviso_suplantacion.isVisible()
        p.chk_solo_dueno.setChecked(True)
        assert p.aviso_suplantacion.isVisible()
        textos = " ".join(w.text() for w in p.findChildren(type(p.estado_bot)))
        assert "online-mode=false" in textos and "Abrir en LAN" in textos
    finally:
        p.hide()


def test_bailes_con_su_controlador(qapp):
    m = MMDFalso()
    p = panel(qapp)
    p.enlazar(SimpleNamespace(escenario=SimpleNamespace(mmd=m, minecraft=None), _deshacer=[]))
    assert m.diario == ["refrescar"]
    assert p.estado_mmd.text() == "Parada." and not p.btn_parar.isEnabled()
    lista = [{"id": ID, "titulo": "<b>Senbonzakura</b>", "autor_cancion": "Kurousa-P", "duracion": 245.2,
              "audio": True, "favorito": True},
             {"id": ID2, "titulo": "Sin canción", "audio": False, "desactivado": True},
             {"id": "../x", "titulo": "malo"}]
    m.biblioteca_cambio.emit(json.dumps(lista))
    textos = [p.lista.item(i).text() for i in range(p.lista.count())]
    assert textos == ["★ <b>Senbonzakura</b> — Kurousa-P  (4:05)", "Sin canción  [no al azar]  (sin canción)"]
    p.lista.itemDoubleClicked.emit(p.lista.item(0))
    assert m.diario[-1] == ("reproducir", ID, "usuario") and "¡A bailar!" in p.msg_bailes.text()
    p.lista.setCurrentRow(1)
    p.alternar_favorito()
    p.alternar_desactivado()
    assert m.diario[-2:] == [("favorito", ID2, True), ("desactivar", ID2, False)]
    p.quitar()
    assert m.diario[-1] == ("quitar", ID2) and "quitados" in p.msg_bailes.text()
    p.siguiente()
    assert "No hay más" in p.msg_bailes.text()
    p.importar()
    assert m.diario[-1] == ("importar", True)
    p.abrir_carpeta()
    assert m.diario[-1] == "carpeta"
    # estado en vivo y el aviso sin esqueleto
    m.e = {"fase": "sonando", "id": ID, "titulo": "Senbonzakura", "t": 61, "total": 245, "modo": "animado",
           "modo_mascota": "animado", "sin_esqueleto": True}
    m.estado_cambio.emit("{}")
    assert p.estado_mmd.text() == "Bailando «Senbonzakura» · 1:01 / 4:05"
    assert not p.aviso_esqueleto.isHidden() and p.btn_parar.isEnabled()
    m.e.update(fase="pausado", pausado=True)
    m.estado_cambio.emit("{}")
    assert p.estado_mmd.text().startswith("En pausa") and p.btn_pausa.text() == "▶ SEGUIR"
    p.pausa()
    p.parar()
    assert m.diario[-2:] == ["pausa", "parar"]
    m.importado.emit(json.dumps({"ok": False, "texto": "Ese archivo no es un VMD."}))
    assert p.msg_bailes.text() == "Ese archivo no es un VMD."


def test_minecraft_botones_y_el_bot_solo_se_instala_con_su_boton(qapp):
    mc = MCFalso()
    datos = DatosFalsos()
    p = panel(qapp, datos=datos)
    p.enlazar(minecraft=mc)
    assert p.estado_bot.text() == "El bot no está instalado: pulsa «Instalar el bot»."
    assert p.btn_instalar.text() == pen.TEXTO_INSTALAR and not p.btn_conectar.isEnabled()
    assert p.estado_reacciones.text() == "Leyendo tu partida como Diego_01."
    assert "instalar" not in mc.diario
    p.btn_instalar.click()
    assert mc.diario == ["instalar"] and p.btn_instalar.text() == "INSTALANDO…" and not p.btn_instalar.isEnabled()
    mc.bot.update(instalando=False, instalado=True)
    mc.estado_cambio.emit("{}")
    assert p.btn_conectar.isEnabled()
    p.linea_dueno.setText("Alex_2")                          # pendiente: conectar guarda antes
    p.conectar_bot()
    assert datos.guardados[-1] == {"dueno": "Alex_2"} and mc.diario[-1] == "conectar"
    assert p.estado_bot.text().startswith("Pon tu nick")
    mc.bot.update(conectado=True, servidor="localhost:25565", nick="Lune", vida=17)
    mc.estado_cambio.emit("{}")
    assert p.estado_bot.text() == "Conectado a localhost:25565 como Lune · vida 17/20."
    assert p.btn_desconectar.isEnabled()
    p.desconectar_bot()
    assert mc.diario[-1] == "desconectar"


def test_detectar_el_log(qapp, tmp_path):
    viejo = tmp_path / "a" / "logs" / "latest.log"
    nuevo = tmp_path / "b" / "logs" / "latest.log"
    for i, f in enumerate((viejo, nuevo)):
        f.parent.mkdir(parents=True)
        f.write_text("x", encoding="utf-8")
        os.utime(f, (time.time() - 1000 + i * 500,) * 2)
    p = panel(qapp, rutas_log=lambda: [viejo, nuevo])
    assert p.detectar_log() == str(nuevo) and p.linea_log.text() == str(nuevo)
    p2 = panel(qapp, rutas_log=lambda: [])
    assert p2.detectar_log() == "" and "No encontré" in p2.error_log.text()


def test_sin_controladores_y_se_suelta_solo_al_desmontar(qapp):
    p = panel(qapp)
    assert not p.btn_reproducir.isEnabled() and not p.btn_instalar.isEnabled()
    assert "app abierta" in p.estado_mmd.text() and "app abierta" in p.estado_bot.text()
    assert p.reproducir(ID) is False
    m, mc = MMDFalso(), MCFalso()
    s4 = SimpleNamespace(escenario=SimpleNamespace(mmd=m, minecraft=mc), _deshacer=[])
    p.enlazar(s4)
    assert p.mmd is m and p.minecraft is mc and p.btn_reproducir.isEnabled()
    for f in reversed(s4._deshacer):
        f()
    assert p.mmd is None and p.minecraft is None and not p.btn_reproducir.isEnabled()
    m.estado_cambio.emit("{}")                                  # ya no escucha
    assert "app abierta" in p.estado_mmd.text()


def test_ocultar_y_guardar_ya_escriben_lo_pendiente(qapp):
    cfg = ConfigDisco()
    datos = DatosFalsos()
    p = panel(qapp, cfg, retardo_ms=10000, datos=datos)
    p.show()
    p.slider_vol.setValue(10)
    p.spin_pensar.setValue(300)
    assert cfg.guardados == 0 and p.pendiente
    p.hide()
    assert cfg.guardados == 1 and cfg.get("baile", "volumen") == 0.1 and datos.guardados == [{"pensar_cada_s": 300}]
    assert p.guardar_ya() == [] and cfg.guardados == 1
