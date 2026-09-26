"""
Tests de ui/panel_ocio_nativo.PanelOcioNativo (offscreen): carga la config, cada
apartado escribe UNA vez (config.config + save) tras el retardo y emite
`cambiado` aplicando en caliente (`recargar_config` del controlador), los
botones llegan a los controladores y el panel funciona sin ellos.
"""
import copy
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from nucleo.config import Config  # noqa: E402
from ui import panel_ocio_nativo as pon  # noqa: E402
from ui.panel_ocio_nativo import PanelOcioNativo  # noqa: E402


class ConfigDisco:
    """Como nucleo.config.Config: `.config` (dict) + `save()`."""

    def __init__(self):
        self.config = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.guardados = 0

    def get(self, s, k, d=None):
        return self.config.get(s, {}).get(k, d)

    def save(self):
        self.guardados += 1


class AlarmasFalsas(QObject):
    cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []

    def recargar_config(self):
        self.diario.append("recargar")

    def abrir_dialogo(self, parent=None):
        self.diario.append(("dialogo", parent is not None))

    def probar(self):
        self.diario.append("probar")
        return True

    def rapido(self, minutos=5):
        self.diario.append(("rapido", minutos))
        return {"ok": True}

    def listar(self):
        return {"alarmas": [{"id": "a1", "activa": True}, {"id": "a2", "activa": False}],
                "temporizadores": [{"id": "t1"}],
                "proxima": {"texto": "gimnasio", "cuando_texto": "mañana a las 07:30"}}


class GrandeFalsa(QObject):
    cambio = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.activo = False
        self.ultimo_error = ""

    def recargar_config(self):
        self.diario.append("recargar")

    def probar_salvapantallas(self):
        self.diario.append("probar")
        return not self.ultimo_error

    def alternar(self):
        self.activo = not self.activo
        self.diario.append("alternar")
        return self.activo

    def estado(self):
        return {"activo": self.activo}


class BaileFalso(QObject):
    estado_cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.diario = []
        self.bailando = False

    def recargar_config(self):
        self.diario.append("recargar")

    def bailar(self, segundos=None, *, origen="manual"):
        self.bailando = True
        self.diario.append("bailar")
        return True

    def parar(self, *, silenciar_auto=True):
        self.bailando = False
        self.diario.append("parar")
        return True

    def estado(self):
        return {"bailando": self.bailando, "app": "Spotify", "bpm": 124.0}

    def apps_sonando(self, refrescar=True):
        return ["Spotify", "chrome.exe", "C:\\Apps\\Tidal.exe"]


@pytest.fixture
def panel(qapp):
    creados = []

    def crear(**kw):
        cfg = kw.pop("config", None) or ConfigDisco()
        p = PanelOcioNativo(cfg, retardo_ms=kw.pop("retardo_ms", 30), **kw)
        cambios = []
        p.cambiado.connect(cambios.append)
        creados.append(p)
        return p, cfg, cambios
    yield crear
    for p in creados:
        p.deleteLater()


def test_carga_la_config(panel):
    cfg = ConfigDisco()
    cfg.config["salvapantallas"].update(activo=True, paso=3, fondo_oscuro=False)
    cfg.config["alarmas"].update(bloqueo_s=7, volumen=0.4, sonido="alarma_2")
    cfg.config["baile"].update(umbral=0.1, apps=["Spotify", "vlc.exe", "spotify", "???"])
    p, _, _ = panel(config=cfg)
    assert p.chk_salva.isChecked() and p.slider_paso.value() == 3
    assert p.valor_paso.text() == "15 min"
    assert not p.chk_fondo.isChecked()
    assert p.spin_bloqueo.value() == 7 and p.slider_volumen.value() == 40
    assert p.combo_sonido.currentData() == "alarma_2"
    assert p.slider_umbral.value() == 10 and p.valor_umbral.text() == "0.10"
    assert p.apps() == ["Spotify", "vlc"]                 # normalizadas y sin repetir
    assert not p.pendiente and cfg.guardados == 0          # cargar no guarda


def test_cada_apartado_escribe_una_vez_y_emite_cambiado(panel):
    a, g, b = AlarmasFalsas(), GrandeFalsa(), BaileFalso()
    p, cfg, cambios = panel(alarmas=a, grande=g, baile=b)
    p.chk_salva.setChecked(True)
    p.slider_paso.setValue(2)
    p.chk_clic_todo.setChecked(False)
    p.spin_bloqueo.setValue(9)
    p.slider_umbral.setValue(30)
    assert p.pendiente and cfg.guardados == 0
    QTest.qWait(120)
    assert cfg.guardados == 1                              # una sola escritura
    assert cfg.config["salvapantallas"]["activo"] is True
    assert cfg.config["salvapantallas"]["paso"] == 2
    assert cfg.config["salvapantallas"]["clic_sale_de_todo"] is False
    assert cfg.config["alarmas"]["bloqueo_s"] == 9
    assert cfg.config["baile"]["umbral"] == 0.3
    assert cambios == ["alarmas", "grande", "baile"]
    assert "recargar" in a.diario and "recargar" in g.diario and "recargar" in b.diario
    assert p.ultimo_guardado["grande"][("salvapantallas", "paso")] == 2


def test_guardar_ya_y_solo_lo_tocado(panel):
    g = GrandeFalsa()
    p, cfg, cambios = panel(grande=g, retardo_ms=10_000)
    p.chk_reloj.setChecked(False)
    assert p.guardar_ya() == ["grande"]
    assert cfg.guardados == 1 and cambios == ["grande"]
    assert cfg.config["salvapantallas"]["reloj"] is False
    assert p.guardar_ya() == [] and cfg.guardados == 1


def test_volumen_y_sonido_de_la_alarma(panel):
    p, cfg, _ = panel(retardo_ms=10_000)
    p.slider_volumen.setValue(55)
    p.combo_sonido.setCurrentIndex(p.combo_sonido.findData("alarma_3"))
    p.guardar_ya()
    assert cfg.config["alarmas"]["volumen"] == 0.55
    assert cfg.config["alarmas"]["sonido"] == "alarma_3"
    assert p.valor_volumen.text() == "55 %"


def test_apps_del_baile(panel):
    b = BaileFalso()
    p, cfg, _ = panel(baile=b, retardo_ms=10_000)
    base = p.apps()
    assert p.anadir_app("C:\\Program Files\\Deezer\\Deezer.exe") is True
    assert p.apps()[-1] == "Deezer"
    assert p.anadir_app("deezer") is False                 # ya está
    assert p.anadir_app("") is False
    assert "Spotify" not in p.apps_suenan()                # ya permitida
    assert p.apps_suenan() == ["chrome", "Tidal"]
    p.lista_apps.setCurrentRow(0)
    assert p.quitar_app() is True
    p.guardar_ya()
    assert cfg.config["baile"]["apps"] == base[1:] + ["Deezer"]


def test_botones_llegan_a_los_controladores(panel):
    a, g, b = AlarmasFalsas(), GrandeFalsa(), BaileFalso()
    p, _, _ = panel(alarmas=a, grande=g, baile=b)
    p.btn_editar_alarmas.click()
    p.btn_probar_alarma.click()
    p.btn_temporizador.click()
    assert a.diario[:3] == [("dialogo", True), "probar", ("rapido", 5)]
    p.btn_grande.click()
    assert g.activo and p.btn_grande.text() == "SALIR DE PANTALLA GRANDE"
    p.btn_probar_salva.click()
    assert "probar" in g.diario
    p.btn_bailar.click()
    assert b.bailando and p.btn_bailar.text() == "PARAR"
    assert "Spotify" in p.estado_baile.text() and "124 BPM" in p.estado_baile.text()
    p.btn_bailar.click()
    assert not b.bailando


def test_probar_salvapantallas_guarda_antes_y_explica_el_error(panel):
    g = GrandeFalsa()
    g.ultimo_error = "hay un juego delante"
    p, cfg, _ = panel(grande=g, retardo_ms=10_000)
    p.chk_salva.setChecked(True)
    assert p.probar_salvapantallas() is False
    assert cfg.guardados == 1                              # lo pendiente se guardó antes de probar
    assert "juego" in p.estado_grande.text()


def test_resumen_de_alarmas_y_atajo(panel):
    p, _, _ = panel(alarmas=AlarmasFalsas(), grande=GrandeFalsa())
    t = p.resumen_alarmas.text()
    assert "1 alarma activa" in t and "1 temporizador" in t and "07:30" in t
    assert "Ctrl+Alt+Shift+B" in p.estado_grande.text()


def test_sin_controladores_y_enlazar_despues(panel):
    p, cfg, _ = panel()
    assert not p.btn_grande.isVisibleTo(p) and not p.btn_bailar.isVisibleTo(p)
    assert not p.btn_editar_alarmas.isVisibleTo(p)
    assert p.alternar_baile() is False
    p.probar_alarma()                                      # sin alarmas: nada, sin error
    from types import SimpleNamespace
    g, b, a = GrandeFalsa(), BaileFalso(), AlarmasFalsas()
    p.enlazar(SimpleNamespace(alarmas=a, grande=g, baile=b))
    assert p.btn_grande.isVisibleTo(p) and p.btn_bailar.isVisibleTo(p) and p.btn_suenan.isVisibleTo(p)
    g.activo = True
    g.cambio.emit(True, "manual")                          # la señal repinta
    assert p.btn_grande.text() == "SALIR DE PANTALLA GRANDE"
    p.enlazar(None)
    g.cambio.emit(False, "")
    assert p.grande is None


def test_con_config_sin_disco_usa_set(panel):
    class CfgSet:
        def __init__(self):
            self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

        def get(self, s, k, d=None):
            return self.d.get(s, {}).get(k, d)

        def set(self, s, k, v):
            self.d.setdefault(s, {})[k] = v
    cfg = CfgSet()
    p, _, cambios = panel(config=cfg, retardo_ms=10_000)
    p.chk_particulas.setChecked(False)
    p.guardar_ya()
    assert cfg.d["baile"]["particulas"] is False and cambios == ["baile"]


def test_sonidos_y_normalizar():
    assert pon.sonidos()[0] == "azar" and "alarma_1" in pon.sonidos()
    assert pon.normalizar_app("  \"C:\\x\\Spotify.exe\" ") == "Spotify"
    assert pon.normalizar_app(123) is None
    assert pon.texto_atajo({"atajos": {"lista": [{"id": "pantalla_grande", "combo": "ctrl+alt+shift+b"}]}},
                           "pantalla_grande") == "Ctrl+Alt+Shift+B"
    assert pon.texto_atajo({}, "pantalla_grande") == ""


def test_resumen_de_alarmas_ensena_el_texto_literal_sin_html(panel):
    """Revisión 4-5-6 (SM1): el texto de la próxima alarma («<b>hola</b>», o un <img> por UNC)
    se interpretaba como HTML en el resumen."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    class AlarmasHtml(AlarmasFalsas):
        def listar(self):
            return {"alarmas": [{"id": "a1", "activa": True}], "temporizadores": [],
                    "proxima": {"texto": "<b>hola</b>", "cuando_texto": "hoy a las 07:30"}}

    p, _, _ = panel(alarmas=AlarmasHtml(), grande=GrandeFalsa())
    lbl = p.resumen_alarmas
    assert "«<b>hola</b>»" in lbl.text()
    html = QLabel()
    html.setFont(lbl.font())
    html.setWordWrap(lbl.wordWrap())
    html.setText(lbl.text())
    assert lbl.textFormat() == Qt.TextFormat.PlainText
    assert lbl.minimumSizeHint().width() > html.minimumSizeHint().width()
