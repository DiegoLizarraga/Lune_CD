"""
Tests de servicios/salvapantallas_terminal.SalvapantallasTerminal: la capa de
título «(-_-) zzZ HH:MM» tras el paso configurado, la hora que se refresca, la
vuelta con cualquier entrada, el mando, el juego y la pantalla pedida, y la
consola sin capas. Sin hilos de verdad salvo en la prueba de iniciar/detener.
"""
import copy
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config import Config  # noqa: E402
from servicios import win_entrada as we  # noqa: E402
from servicios.salvapantallas_terminal import CAPA, PRIORIDAD, SalvapantallasTerminal  # noqa: E402
from servicios.win_entrada import EstadoMando  # noqa: E402


class ConfigFalsa:
    def __init__(self, **salva):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.d["salvapantallas"].update(salva)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)


class ConsolaCapas:
    def __init__(self):
        self.capas = []

    def titulo_capa(self, capa, texto, prioridad=0):
        self.capas.append((capa, texto, prioridad))


class ConsolaVieja:
    def __init__(self):
        self.titulos = []

    def titulo(self, texto):
        self.titulos.append(texto)
        return True


class Api:
    def __init__(self):
        self.ultima = 1_000_000
        self.t = 1_000_000
        self.mando = None
        self.ejecucion = 0

    def inactivo(self, s):
        self.t = self.ultima + int(s * 1000)

    def tick(self):
        return self.t

    def ultima_entrada(self):
        return self.ultima

    def cursor(self):
        return (0, 0)

    def boton_izquierdo(self):
        return False

    def hay_xinput(self):
        return self.mando is not None

    def estado_mando(self, i):
        return self.mando if i == 0 else None

    def estado_ejecucion(self):
        return self.ejecucion


class Reloj:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


def crear(consola=None, **cfg):
    cfg.setdefault("activo", True)
    api, reloj = Api(), Reloj()
    hora = {"v": datetime(2026, 9, 26, 23, 41)}
    s = SalvapantallasTerminal(consola or ConsolaCapas(), ConfigFalsa(**cfg), api=api, reloj=reloj,
                               hora=lambda: hora["v"])
    return s, api, reloj, hora


def esperar(s, api, reloj, seg):
    api.inactivo(seg)
    reloj.t += seg
    return s.tic()


def test_capa_de_titulo_con_reloj_tras_el_paso():
    s, api, reloj, _ = crear(paso=0)
    assert esperar(s, api, reloj, 20) is False
    assert s.consola.capas == []
    assert esperar(s, api, reloj, 31) is True
    assert s.consola.capas == [(CAPA, "(-_-) zzZ 23:41", PRIORIDAD)]
    assert s.activo


def test_la_hora_se_refresca_solo_al_cambiar_el_minuto():
    s, api, reloj, hora = crear()
    esperar(s, api, reloj, 31)
    esperar(s, api, reloj, 32)
    assert len(s.consola.capas) == 1
    hora["v"] = datetime(2026, 9, 26, 23, 42)
    esperar(s, api, reloj, 33)
    assert s.consola.capas[-1] == (CAPA, "(-_-) zzZ 23:42", PRIORIDAD)


def test_sin_reloj_solo_la_carita():
    s, api, reloj, _ = crear(reloj=False)
    esperar(s, api, reloj, 31)
    assert s.consola.capas[-1][1] == "(-_-) zzZ"


def test_cualquier_entrada_lo_quita():
    s, api, reloj, _ = crear()
    esperar(s, api, reloj, 31)
    api.ultima = api.t                                  # alguien tocó el PC
    reloj.t += 1
    assert s.tic() is False
    assert s.consola.capas[-1] == (CAPA, None, PRIORIDAD)
    assert not s.activo
    reloj.t += 1
    assert s.tic() is False                              # no vuelve enseguida


def test_paso_largo():
    s, api, reloj, _ = crear(paso=2)                    # 5 min
    assert esperar(s, api, reloj, 299) is False
    assert esperar(s, api, reloj, 301) is True


def test_mando_juego_y_pantalla_pedida_no_arman():
    s, api, reloj, _ = crear()
    api.mando = EstadoMando(3, 0, 255, 0, 0, 0, 0, 0)  # gatillo apretado
    assert esperar(s, api, reloj, 40) is False
    api.mando = None
    api.ejecucion = we.ES_DISPLAY_REQUIRED
    assert esperar(s, api, reloj, 40) is False
    api.ejecucion = 0
    s._en_juego = lambda: True
    assert esperar(s, api, reloj, 40) is False
    s._en_juego = lambda: False
    assert esperar(s, api, reloj, 41) is True


def test_juego_o_apagado_con_el_salvapantallas_puesto_lo_quita():
    s, api, reloj, _ = crear()
    esperar(s, api, reloj, 31)
    s._en_juego = lambda: True
    assert s.tic() is False
    assert s.consola.capas[-1] == (CAPA, None, PRIORIDAD)
    s2, api2, reloj2, _ = crear()
    esperar(s2, api2, reloj2, 31)
    s2.config.d["salvapantallas"]["activo"] = False
    assert s2.tic() is False and not s2.activo


def test_apagado_no_hace_nada():
    s, api, reloj, _ = crear(activo=False)
    assert esperar(s, api, reloj, 10_000) is False
    assert s.consola.capas == []


def test_consola_sin_capas_usa_titulo_y_restaura():
    consola = ConsolaVieja()
    restaurados = []
    s, api, reloj, _ = crear(consola=consola)
    s._restaurar = lambda: restaurados.append(1)
    esperar(s, api, reloj, 31)
    assert consola.titulos == ["(-_-) zzZ 23:41"]
    api.ultima = api.t
    reloj.t += 1
    s.tic()
    assert restaurados == [1]


def test_iniciar_y_detener_con_hilo():
    consola = ConsolaCapas()
    api = Api()
    api.inactivo(40)
    r = {"t": 0.0}
    s = SalvapantallasTerminal(consola, ConfigFalsa(activo=True), api=api, intervalo_s=0.05,
                               reloj=lambda: r["t"])
    s.iniciar()                                          # la actividad cuenta desde aquí
    s.iniciar()                                          # idempotente
    r["t"] = 1000.0                                      # pasa el tiempo
    fin = time.monotonic() + 3
    while not consola.capas and time.monotonic() < fin:
        time.sleep(0.02)
    s.detener()
    assert consola.capas and consola.capas[0][1].startswith("(-_-) zzZ")
    assert consola.capas[-1] == (CAPA, None, PRIORIDAD)  # al detener, fuera la capa
    assert s._hilo is None
