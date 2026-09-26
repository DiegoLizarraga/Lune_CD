"""
ui/puente_musica.py (objeto `musica` del QWebChannel, window.luneMusica).

Con un doble de ControlBaile (QObject con estado_cambio/pulso/apps_cambio):
  · validación: segundos del baile, umbral 0.02–0.6, cambiar_s 5–120, apps sin rutas ni comodines
    (nombre sin «.exe», como Mate-Engine), tipos estrictos;
  · sin servicios: estado por defecto y la config se lee y se guarda igual (Config real en tmp);
  · servicios tardíos (enlazar) y señales reemitidas normalizadas (pulso acotado, fase mod 1, apps
    que llegan con ruta → solo el nombre).
"""
import json
import os
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from ui import puente_musica as pm  # noqa: E402
from ui.puentes_ocio import PuentesOcio  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PyQt6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class BaileFalso(QObject):
    """Como ControlBaile (ui/baile_qt.py)."""
    estado_cambio = pyqtSignal(str)
    pulso = pyqtSignal(str)
    apps_cambio = pyqtSignal(str)

    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.llamadas: List[tuple] = []
        self.bailando = False

    def estado(self):
        return {"bailando": self.bailando, "origen": "manual" if self.bailando else "", "musica": False, "app": "",
                "estilo": "palmas" if self.bailando else "", "bpm": 120.0 if self.bailando else None, "energia": 0.0,
                "auto": True, "pausado_hasta_silencio": False, "disponible": None}

    def bailar(self, segundos=None, *, origen="manual"):
        self.llamadas.append(("bailar", segundos))
        self.bailando = True
        return True

    def parar(self, *, silenciar_auto=True):
        self.llamadas.append(("parar",))
        ok, self.bailando = self.bailando, False
        return ok

    def apps_sonando(self, refrescar=True):
        self.llamadas.append(("apps_sonando", refrescar))
        return ["Spotify", "C:\\Program Files\\VLC\\vlc.exe", "", "*"]

    def permitir_app(self, n):
        self.llamadas.append(("permitir_app", n))
        apps = list(self.config.get("baile", "apps", []))
        if n.lower() not in {a.lower() for a in apps}:
            apps.append(n)
            self.config.set("baile", "apps", apps)
        return apps

    def quitar_app(self, n):
        self.llamadas.append(("quitar_app", n))
        apps = [a for a in self.config.get("baile", "apps", []) if a.lower() != n.lower()]
        self.config.set("baile", "apps", apps)
        return apps

    def recargar_config(self):
        self.llamadas.append(("recargar_config",))

    def de(self, n):
        return [c[1:] for c in self.llamadas if c[0] == n]


@pytest.fixture
def config_real(tmp_path):
    from nucleo.config import Config
    return Config(str(tmp_path / "config.json"))


def _j(s):
    return json.loads(s)


def _senal(senal):
    recibido = []
    senal.connect(lambda *a: recibido.append(a))
    return recibido


def test_normalizar_app():
    assert pm.normalizar_app("  Spotify.EXE ") == "Spotify"
    assert pm.normalizar_app("foobar2000") == "foobar2000"
    assert pm.normalizar_app("Apple Music (beta)") == "Apple Music (beta)"
    for malo in ("C:\\x\\spotify.exe", "a/b", "c:spotify", "", ".exe", "*", "x" * 61, None, 5, "...", "\x07"):
        assert pm.normalizar_app(malo) is None, repr(malo)
    assert pm.normalizar_app("C:\\Program Files\\VLC\\vlc.exe", desde_ruta=True) == "vlc"
    assert pm.lista_apps(["Spotify", "spotify.exe", "vlc", "../x", 3]) == ["Spotify", "vlc"]
    assert pm.normalizar_pulso('{"bpm": 999, "fase": 2.25, "energia": -1}') == {"bpm": 250.0, "fase": 0.25, "energia": 0.0}
    assert pm.normalizar_pulso({"bpm": "x", "fase": 0}) is None
    assert pm.normalizar_pulso("no json") is None


def test_sin_servicios_por_defecto_y_config(config_real):
    p = pm.PuenteMusica(config=config_real)
    e = _j(p.estado_json())
    assert e == {"bailando": False, "origen": "", "musica": False, "app": "", "estilo": "", "bpm": 0, "energia": 0,
                 "auto": True, "pausado_hasta_silencio": False, "disponible": False}
    assert p.bailar(0) is False and p.parar() is False
    assert _j(p.apps_audio()) == []
    c = _j(p.config_baile())
    assert c["apps"] == ["Spotify", "MusicBee", "foobar2000", "vlc", "AppleMusic"] and 0.02 <= c["umbral"] <= 0.6
    # Sin ControlBaile, las apps se guardan en la config igual
    r = _j(p.app_permitir("Deezer.exe"))
    assert r["ok"] is True and r["apps"][-1] == "Deezer"
    assert _j(p.app_permitir("deezer"))["apps"].count("Deezer") == 1, "sin repetir (sin mayúsculas)"
    assert _j(p.app_quitar("DEEZER"))["apps"] == ["Spotify", "MusicBee", "foobar2000", "vlc", "AppleMusic"]
    assert _j(p.app_permitir("C:\\x\\y.exe"))["ok"] is False
    from nucleo.config import Config
    assert Config(config_real.config_path).get("baile", "apps")[-1] == "AppleMusic"


def test_bailar_y_parar_validan_los_segundos():
    b = BaileFalso()
    p = pm.PuenteMusica(config={}, baile=b)
    for malo in (4, 301, -5, True):
        assert p.bailar(malo) is False, malo
    assert b.de("bailar") == []
    assert p.bailar(0) is True and p.bailar(30) is True
    assert b.de("bailar") == [(None,), (30,)], "0 = los segundos por defecto de ControlBaile"
    assert p.parar() is True and p.parar() is False
    e = _j(p.estado_json())
    assert e["disponible"] is True and e["bpm"] == 0 and e["bailando"] is False


def test_config_baile_rangos_y_guardado(config_real):
    b = BaileFalso(config_real)
    p = pm.PuenteMusica(config=config_real, baile=b)
    for malo in ('{"umbral": 0.01}', '{"umbral": 0.7}', '{"umbral": "0.1"}', '{"cambiar_s": 4}', '{"cambiar_s": 121}',
                 '{"cambiar_s": 10.5}', '{"auto": 1}', '{"apps": "Spotify"}', '{"apps": ["C:\\\\x.exe"]}',
                 json.dumps({"apps": [f"a{i}" for i in range(31)]}), '{"volumen": 1}', '{}', 'x'):
        r = _j(p.config_baile_guardar(malo))
        assert r["ok"] is False and r["error"], malo
    assert b.de("recargar_config") == []
    r = _j(p.config_baile_guardar(json.dumps({"auto": False, "umbral": 0.05, "cambiar": True, "cambiar_s": 30,
                                              "particulas": False, "apps": ["Spotify.exe", "spotify", "Tidal"]})))
    assert r["ok"] is True
    assert r["estado"] == {"auto": False, "umbral": 0.05, "apps": ["Spotify", "Tidal"], "cambiar": True, "cambiar_s": 30,
                           "particulas": False}
    assert config_real.get("baile", "umbral") == 0.05
    assert b.de("recargar_config") == [()]


def test_apps_con_controlador_y_senales_reemitidas(config_real):
    b = BaileFalso(config_real)
    p = pm.PuenteMusica(config=config_real)
    estados, pulsos, apps = _senal(p.baile_estado), _senal(p.baile_pulso), _senal(p.apps_cambio)
    PuentesOcio(None, p).enlazar(type("S", (), {"ocio": type("O", (), {"baile": b})()})())
    assert p.baile is b
    assert _j(estados[-1][0])["disponible"] is True, "al enlazar tarde, la página recibe el estado"
    assert _j(p.apps_audio()) == ["Spotify", "vlc"], "lo del backend con ruta se queda en el nombre"
    assert b.de("apps_sonando") == [()] or b.de("apps_sonando") == [(True,)]
    r = _j(p.app_permitir("Tidal.exe"))
    assert r["ok"] is True and "Tidal" in r["apps"] and b.de("permitir_app") == [("Tidal",)]
    r = _j(p.app_quitar("tidal"))
    assert "Tidal" not in r["apps"] and b.de("quitar_app") == [("tidal",)]
    b.estado_cambio.emit(json.dumps({"bailando": True, "origen": "auto", "musica": True, "app": "C:\\x\\Spotify.exe",
                                     "estilo": "<b>", "bpm": 1e6, "energia": 2, "auto": True, "disponible": None}))
    e = _j(estados[-1][0])
    assert e["bailando"] is True and e["app"] == "Spotify" and e["estilo"] == "" and e["bpm"] == 250.0 and e["energia"] == 1.0
    assert e["origen"] == "auto" and e["disponible"] is True
    b.pulso.emit(json.dumps({"bpm": 124.456, "fase": 1.3, "energia": 0.8, "confianza": 0.9, "t": 5}))
    assert _j(pulsos[-1][0]) == {"bpm": 124.46, "fase": 0.3, "energia": 0.8}
    b.pulso.emit("basura")
    assert len(pulsos) == 1, "un pulso roto no llega a la página"
    b.apps_cambio.emit(json.dumps(["Spotify", "D:\\m\\foobar2000.exe", "*"]))
    assert _j(apps[-1][0]) == ["Spotify", "foobar2000"]
    # Soltar y cerrar
    p.enlazar(baile=None)
    b.pulso.emit(json.dumps({"bpm": 120, "fase": 0}))
    assert len(pulsos) == 1
    assert _j(p.estado_json())["disponible"] is False
    p.cerrar()
    p.enlazar(baile=b)
    assert p.baile is None, "cerrado: no vuelve a enlazar"
