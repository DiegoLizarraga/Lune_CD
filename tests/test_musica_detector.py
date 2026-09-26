"""
Tests de servicios/musica_detector: ¿suena música? (histéresis, apps
permitidas, exclusión de Lune, modo juego, bucle rápido y pulso ≤ 2 Hz,
baile a mano con `forzar_pulso` y `silenciar_hasta_silencio`).

Medidor de sesiones y reloj falsos: nada de COM ni de hilos reales salvo el
test del bucle, que corre con un `dormir` falso que adelanta el reloj.
"""
import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios.audio_sesiones import Sesion  # noqa: E402
from servicios.musica_detector import (  # noqa: E402
    DetectorMusica, Histeresis, coincide_app, elegir, leer_config, normalizar_nombre_app,
)

PROPIO = 4242


class Config:
    def __init__(self, **baile):
        self.d = {"baile": {"auto": True, "umbral": 0.2, "apps": ["Spotify", "vlc"], **baile}}

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor


class MedidorFalso:
    """{clave: [pid, exe, pico]} que el test cambia; cuenta las llamadas."""

    def __init__(self, **sesiones):
        self.s = {k: list(v) for k, v in sesiones.items()}
        self.enumeraciones = 0
        self.lecturas = []
        self.abierto = False
        self.cerrado = False

    def abrir(self):
        self.abierto = True

    def cerrar(self):
        self.cerrado = True

    def sesiones(self, umbral_nombre=None):
        self.enumeraciones += 1
        return [Sesion(pid, exe, pico, k) for k, (pid, exe, pico) in self.s.items()]

    def pico(self, clave):
        self.lecturas.append(clave)
        v = self.s.get(clave)
        return None if v is None else v[2]


class Reloj:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


def detector(medidor, config=None, **kw):
    reloj = kw.pop("reloj", Reloj())
    d = DetectorMusica(config or Config(), medidor=medidor, pids={PROPIO}, reloj=reloj, **kw)
    d.cambios, d.pulsos, d.apps = [], [], []
    d.on_cambio = lambda a, app: d.cambios.append((a, app))
    d.on_pulso = d.pulsos.append
    d.on_sesiones = d.apps.append
    d.reloj = reloj
    return d


# ── Funciones sueltas ────────────────────────────────────────────────────────────
def test_coincide_app_empieza_por_sin_mayusculas_ni_exe():
    apps = ["Spotify", "vlc", "foobar2000"]
    assert coincide_app("Spotify", apps) == "Spotify"
    assert coincide_app("spotify.exe", apps) == "Spotify"
    assert coincide_app("SpotifyWebHelper", apps) == "Spotify"       # «empieza por», como ME
    assert coincide_app("VLC.EXE", apps) == "vlc"
    assert coincide_app("firefox", apps) is None
    assert coincide_app("", apps) is None


def test_normalizar_nombre_app():
    assert normalizar_nombre_app(' "C:\\Program Files\\Spotify\\Spotify.exe" ') == "Spotify"
    assert normalizar_nombre_app("vlc.EXE") == "vlc"
    assert normalizar_nombre_app("") is None
    assert normalizar_nombre_app("a*b") is None
    assert normalizar_nombre_app(None) is None


def test_elegir_la_mas_fuerte_permitida_que_no_sea_de_lune():
    ss = [Sesion(PROPIO, "Spotify", 0.9, "a"),          # de Lune (su voz): fuera
          Sesion(0, "Spotify", 0.9, "b"),                # pid 0: fuera
          Sesion(10, "firefox", 0.8, "c"),               # no permitida
          Sesion(11, "Spotify", 0.3, "d"),
          Sesion(11, "Spotify", 0.5, "e"),               # Spotify con dos sesiones: la más fuerte
          Sesion(12, "vlc", 0.1, "f")]                   # por debajo del umbral
    assert elegir(ss, ["Spotify", "vlc"], {PROPIO}, 0.2).clave == "e"
    assert elegir(ss, ["vlc"], {PROPIO}, 0.2) is None


def test_leer_config_acota_y_limpia():
    c = leer_config(Config(umbral=5, apps=["Spotify.exe", "", 3, "a/b/vlc"], auto=0))
    assert c == {"auto": False, "umbral": 1.0, "apps": ["Spotify", "vlc"]}
    assert leer_config(None)["umbral"] == 0.05                 # D1
    assert leer_config(Config(umbral="x"))["umbral"] == 0.05


def test_histeresis_entra_con_dos_y_sale_a_los_6_s():
    h = Histeresis()
    assert h.paso(0.3, 0.0, 0.2) == (False, False)
    assert h.paso(0.1, 2.0, 0.2) == (False, False)       # se corta la racha
    assert h.paso(0.3, 4.0, 0.2) == (False, False)
    assert h.paso(0.3, 6.0, 0.2) == (True, True)
    assert h.paso(0.04, 7.0, 0.2) == (False, True)       # por debajo de 0.25·umbral = 0.05
    assert h.paso(0.06, 10.0, 0.2) == (False, True)      # vuelve a subir: se reinicia la cuenta
    assert h.paso(0.0, 11.0, 0.2) == (False, True)
    assert h.paso(0.0, 16.9, 0.2) == (False, True)
    assert h.paso(0.0, 17.0, 0.2) == (True, False)


# ── Detector ─────────────────────────────────────────────────────────────────────
def test_entra_con_dos_lecturas_y_solo_apps_permitidas():
    m = MedidorFalso(ff=[10, "firefox", 0.9], sp=[11, "Spotify", 0.0], yo=[PROPIO, "Spotify", 0.9])
    d = detector(m)
    for _ in range(3):
        assert d.sondear() == (False, "")
        d.reloj.t += 2
    assert d.cambios == []                               # firefox no cuenta; la voz de Lune tampoco
    assert d.apps[-1] == ["firefox"]                     # «suenan ahora», sin la de Lune
    m.s["sp"][2] = 0.4
    assert d.sondear() == (False, "")
    d.reloj.t += 2
    assert d.sondear() == (True, "Spotify")
    assert d.cambios == [(True, "Spotify")]
    assert d.apps[-1] == ["firefox", "Spotify"]


def activo(m=None, **kw):
    m = m or MedidorFalso(sp=[11, "Spotify", 0.5])
    d = detector(m, **kw)
    d.sondear(); d.reloj.t += 2; d.sondear()
    assert d.activa
    return d, m


def test_bucle_rapido_una_lectura_por_paso_y_pulso_como_mucho_2_hz():
    d, m = activo()
    m.enumeraciones = 0
    for k in range(150):                                 # 3 s a 50 Hz
        d.reloj.t += 0.02
        m.s["sp"][2] = 0.8 if k % 25 == 0 else 0.3
        d.rapido()
    assert m.lecturas == ["sp"] * 150 and m.enumeraciones == 0
    assert 6 <= len(d.pulsos) <= 7
    ts = [p.t for p in d.pulsos]
    assert all(b - a >= 0.5 - 1e-6 for a, b in zip(ts, ts[1:]))


def test_sale_a_los_6_s_por_debajo_de_un_cuarto_del_umbral():
    d, m = activo()
    m.s["sp"][2] = 0.04
    for _ in range(int(5.9 / 0.02)):
        d.reloj.t += 0.02
        d.rapido()
    assert d.activa and d.cambios == [(True, "Spotify")]
    for _ in range(10):
        d.reloj.t += 0.02
        d.rapido()
    assert not d.activa and d.cambios[-1] == (False, "Spotify")


def test_sesion_que_muere_no_rompe_y_acaba_saliendo():
    d, m = activo()
    del m.s["sp"]
    for _ in range(int(6.5 / 0.02)):
        d.reloj.t += 0.02
        d.rapido()
    assert not d.activa and d.cambios[-1][0] is False


def test_en_juego_no_llama_a_com_y_deja_de_bailar():
    juego = {"on": False}
    d, m = activo(en_juego=lambda: juego["on"])
    juego["on"] = True
    m.enumeraciones, m.lecturas = 0, []
    d.reloj.t += 2
    assert d.sondear() == (False, "")
    d.rapido()
    assert m.enumeraciones == 0 and m.lecturas == []
    assert d.cambios[-1] == (False, "Spotify")
    juego["on"] = False                                  # tras el juego vuelve a detectar
    d.sondear(); d.reloj.t += 2; d.sondear()
    assert d.cambios[-1] == (True, "Spotify")


def test_auto_apagado_no_detecta():
    cfg = Config(auto=False)
    d = detector(MedidorFalso(sp=[11, "Spotify", 0.9]), cfg)
    d.sondear(); d.reloj.t += 2; d.sondear()
    assert not d.activa and d.cambios == []
    assert not d._toca_sondear()                         # el hilo no sondea solo


def test_apagar_auto_con_musica_la_da_por_acabada():
    cfg = Config()
    d, m = activo(config=cfg)
    cfg.set("baile", "auto", False)
    d.sondear()
    assert not d.activa and d.cambios[-1] == (False, "Spotify")


def test_forzar_pulso_sigue_la_sesion_mas_fuerte_aunque_no_este_permitida():
    m = MedidorFalso(ff=[10, "firefox", 0.7], yt=[12, "chrome", 0.3], yo=[PROPIO, "python", 0.9])
    d = detector(m)
    d.sondear()
    d.rapido()
    assert m.lecturas == []                              # sin música ni baile a mano: nada rápido
    d.forzar_pulso(True)
    d.sondear()
    d.reloj.t += 0.02
    d.rapido()
    assert m.lecturas == ["ff"] and len(d.pulsos) == 1
    assert d.cambios == []                               # forzar no es «hay música»
    d.forzar_pulso(False)
    d.rapido()
    assert m.lecturas == ["ff"]


def test_silenciar_hasta_silencio():
    d, m = activo()
    d.silenciar_hasta_silencio()
    assert not d._rapido_activo()                        # silenciado: sin bucle rápido
    m.s["sp2"] = [13, "vlc", 0.9]                       # cambia de app: no avisa
    del m.s["sp"]
    d.reloj.t += 2
    d.sondear()
    assert d.cambios == [(True, "Spotify")]
    m.s["sp2"][2] = 0.0                                  # se calla: sale y se acaba el silencio
    for _ in range(5):
        d.reloj.t += 2
        d.sondear()
    assert d.cambios[-1][0] is False and not d.estado()["silenciado"]
    m.s["sp2"][2] = 0.5                                  # nueva música: vuelve a avisar
    d.sondear(); d.reloj.t += 2; d.sondear()
    assert d.cambios[-1] == (True, "vlc")


def test_reanudar_auto_deshace_el_silencio():
    d, m = activo()
    d.silenciar_hasta_silencio()
    d.reanudar_auto()
    assert d.cambios[-1] == (True, "Spotify") and d._rapido_activo()


def test_sin_medidor_disponible_no_hay_baile():
    class Roto(MedidorFalso):
        def abrir(self):
            raise ImportError("comtypes")
    m = Roto(sp=[11, "Spotify", 0.9])
    d = detector(m)
    assert d.sondear() == (False, "") and d.sondear() == (False, "")
    assert d.disponible is False and m.enumeraciones == 0
    assert d.estado()["disponible"] is False


def test_bucle_del_hilo_sondeo_lento_y_rapido_a_50_hz():
    reloj = Reloj(0.0)
    m = MedidorFalso(sp=[11, "Spotify", 0.5])
    esperas = []

    def dormir(s):
        esperas.append(s)
        reloj.t += s
        if reloj.t > 8.0:
            d._parar.set()
    d = detector(m, reloj=reloj, dormir=dormir)
    d._bucle()                                           # en este hilo, con el reloj falso
    assert m.cerrado                                     # cierra COM al salir
    assert d.cambios == [(True, "Spotify")]
    lentas = [s for s in esperas if s > 0.5]
    rapidas = [s for s in esperas if s <= 0.021]
    assert lentas and lentas[0] == pytest.approx(2.0)    # antes de la música: cada 2 s
    assert len(rapidas) > 100 and all(s == pytest.approx(0.02) for s in rapidas)
    assert m.enumeraciones == pytest.approx(5, abs=1)    # el sondeo lento sigue cada 2 s


def test_iniciar_y_detener_el_hilo_real():
    m = MedidorFalso(sp=[11, "Spotify", 0.0])
    d = DetectorMusica(Config(), medidor=m, pids={PROPIO})
    d.iniciar()
    d.pedir_sondeo()
    fin = time.monotonic() + 3.0
    while m.enumeraciones < 1 and time.monotonic() < fin:
        time.sleep(0.01)
    d.detener()
    assert m.abierto and m.cerrado and m.enumeraciones >= 1
    assert d._hilo is None and not d.activa
