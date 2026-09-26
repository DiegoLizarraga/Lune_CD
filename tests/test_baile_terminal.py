"""
Tests de servicios/baile_terminal (patata): cuadros al pulso en la capa del
título, la línea viva en el prompt de un reclamo (`cambiar_prompt`), Enter en
vacío para, `/bailar auto on|off`, `permitir`/`quitar` guardan en la config,
modo juego y baile automático con la música. Consola real con salida y API
falsas, detector y reloj falsos; sin el hilo de la animación (pasos a mano)
salvo en su propio test.
"""
import io
import queue
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.consola import ConsolaAsincrona, ancho_visible  # noqa: E402
from nucleo.pulso import Pulso  # noqa: E402
from servicios.baile_terminal import BaileTerminal  # noqa: E402

KAOMOJI = ("ヽ(^o^)ﾉ", "┏(^o^)┛", "ヾ(^o^)ノ", "┗(^o^)┓")


class ApiFalsa:
    def __init__(self):
        self.titulos = []

    def habilitar_vt(self):
        return True

    def es_consola_entrada(self):
        return False

    def titulo(self, texto):
        self.titulos.append(texto)
        return True

    def parpadear(self, veces=3, hasta_foco=True):
        return True


class Entrada:
    def __init__(self):
        self.q = queue.Queue()

    def put(self, s):
        self.q.put(s)

    def readline(self):
        s = self.q.get()
        return "" if s is None else s


class Config:
    def __init__(self, **baile):
        self.d = {"baile": {"auto": True, "umbral": 0.2, "apps": ["Spotify", "vlc"], **baile}}
        self.sets = []

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.sets.append((sec, clave, valor))
        self.d.setdefault(sec, {})[clave] = valor


class DetectorFalso:
    def __init__(self):
        self.on_cambio = self.on_pulso = None
        self.llamadas = []
        self.disponible = True
        self.sonando = ["firefox", "Spotify"]

    def iniciar(self):
        self.llamadas.append("iniciar")

    def detener(self):
        self.llamadas.append("detener")

    def forzar_pulso(self, on):
        self.llamadas.append(("forzar", on))

    def silenciar_hasta_silencio(self):
        self.llamadas.append("silenciar")

    def pedir_sondeo(self):
        self.llamadas.append("sondeo")

    def apps_sonando(self):
        return list(self.sonando)


class Reloj:
    def __init__(self):
        self.t = 500.0

    def __call__(self):
        return self.t


def esperar(cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


@pytest.fixture
def crear(monkeypatch):
    creadas = []

    def _crear(ansi=True, ancho=80, juego=None, hilo=False, **cfg):
        ent = Entrada()
        api = ApiFalsa()
        c = ConsolaAsincrona("tú > ", stdout=io.StringIO(), stdin=ent, api=api, ansi=ansi, ancho=ancho)
        c.entrada, c.api_falsa = ent, api
        det = DetectorFalso()
        reloj = Reloj()
        estado = {"juego": False} if juego is None else juego
        b = BaileTerminal(c, Config(**cfg), colores={"cyan": "", "dim": "", "reset": ""},
                          en_juego=lambda: estado["juego"], detector=det, reloj=reloj)
        b._kaomoji_linea = False
        if not hilo:
            b._arrancar_hilo = lambda: None
        b.det, b.reloj, b.juego, b.c_ = det, reloj, estado, c
        creadas.append((b, ent))
        return b
    yield _crear
    for b, ent in creadas:
        b.detener()
        ent.put(None)


def titulos(b):
    return b.c_.api_falsa.titulos


def test_bailar_a_mano_titulo_con_cuadros_al_pulso(crear):
    b = crear()
    r = b.comando("/bailar")
    assert "30 s" in r and "Enter" in r
    assert b.bailando and b.origen == "manual" and ("forzar", True) in b.det.llamadas
    assert b.c_.capa_titulo() == "baile"
    vistos = []
    for _ in range(8):                                   # 2 s a 120 BPM, cada 0.25 s: 2 cuadros por golpe
        vistos.append(titulos(b)[-1].split(" ")[0])
        b.reloj.t += 0.25
        b.paso()
    assert vistos == list(KAOMOJI) * 2
    assert titulos(b)[-1].endswith("♪ 120 BPM")


def test_linea_viva_en_el_prompt_del_reclamo(crear):
    b = crear()
    b.comando("/bailar 45")
    p = b.c_._texto_prompt()
    assert p.startswith("♪ \\o/") and "120 BPM" in p and "0:45" in p and "(Enter para)" in p
    b.reloj.t += 1.25
    b.paso()
    p2 = b.c_._texto_prompt()
    assert "0:43" in p2 and p2 != p                      # se repinta sola (cambiar_prompt)
    assert b.c_._reclamos[0].prioridad < 0               # la alarma y las preguntas van antes


def test_enter_en_vacio_para_y_lo_escrito_va_al_chat(crear):
    b = crear()
    b.comando("/bailar")
    h_caja = {}
    import threading

    def leer():
        h_caja["r"] = b.c_.leer_linea()
    h = threading.Thread(target=leer, daemon=True)
    h.start()
    b.c_.entrada.put("hola\n")                          # con texto: al chat, sigue bailando
    h.join(3)
    assert h_caja["r"] == "hola" and b.bailando
    b.c_.entrada.put("\n")
    assert esperar(lambda: not b.bailando)
    assert b.c_.capa_titulo() is None and not b.c_.reclamada


def test_parar(crear):
    b = crear()
    assert b.comando("/parar") == "No estaba bailando."
    b.comando("/bailar")
    assert b.comando("/parar") == "♪ Vale, dejo de bailar."
    assert not b.bailando and b.c_.capa_titulo() is None and not b.c_.reclamada
    assert b.det.llamadas[-1] == ("forzar", False)


def test_fin_del_baile_a_mano(crear):
    b = crear()
    b.comando("/bailar 5")
    b.reloj.t += 5.0
    b.paso()
    assert not b.bailando and b.c_.capa_titulo() is None


def test_fin_del_baile_a_mano_con_musica_sigue_sola(crear):
    b = crear()
    b._iniciado = True
    b.comando("/bailar 5")
    b._on_cambio(True, "Spotify")
    b.reloj.t += 5.0
    b.paso()
    assert b.bailando and b.origen == "auto" and not b.c_.reclamada
    assert "Spotify" in titulos(b)[-1]


def test_sin_ansi_solo_el_titulo(crear):
    b = crear(ansi=False)
    r = b.comando("/bailar 10")
    assert "título" in r and b.bailando and not b.c_.reclamada
    assert b.c_.capa_titulo() == "baile"


def test_musica_baila_sola_en_el_titulo_y_para_al_callarse(crear):
    b = crear()
    b.iniciar()
    assert "iniciar" in b.det.llamadas and b.det.on_cambio is not None
    b.det.on_cambio(True, "Spotify")
    assert b.bailando and b.origen == "auto" and not b.c_.reclamada
    b.det.on_pulso(Pulso(124.0, 0.0, 0.8, 0.9, b.reloj.t))
    b.reloj.t += 0.1
    b.paso()
    assert titulos(b)[-1].endswith("♪ Spotify · 124 BPM")
    b.det.on_cambio(False, "")
    assert not b.bailando and b.c_.capa_titulo() is None


def test_parar_con_musica_no_vuelve_sola_hasta_el_silencio(crear):
    b = crear()
    b.iniciar()
    b.det.on_cambio(True, "Spotify")
    b.comando("/parar")
    assert "silenciar" in b.det.llamadas
    b.det.on_cambio(True, "vlc")                         # (el detector no avisaría, pero por si acaso)
    assert not b.bailando
    b.det.on_cambio(False, "")
    b.det.on_cambio(True, "Spotify")
    assert b.bailando


def test_modo_juego(crear):
    b = crear()
    b.iniciar()
    b.juego["juego"] = True
    assert "juego" in b.comando("/bailar") and not b.bailando
    b.det.on_cambio(True, "Spotify")
    assert not b.bailando
    b.juego["juego"] = False
    b.comando("/bailar")
    b.juego["juego"] = True                              # empieza un juego bailando
    b.paso()
    assert not b.bailando and b.c_.capa_titulo() is None


def test_auto_on_off_guarda_en_la_config(crear):
    b = crear()
    b.iniciar()
    assert "sí" in b.comando("/bailar auto")
    b.det.on_cambio(True, "Spotify")
    assert b.bailando
    assert "ya no bailo sola" in b.comando("/bailar auto off")
    assert b.config.get("baile", "auto") is False and not b.bailando
    b.det.on_cambio(False, "")
    b.det.on_cambio(True, "Spotify")
    assert not b.bailando
    assert "bailaré sola" in b.comando("/bailar auto on")
    assert b.config.get("baile", "auto") is True and "sondeo" in b.det.llamadas
    assert "Usa" in b.comando("/bailar auto quizá")


def test_apps_permitir_y_quitar(crear):
    b = crear()
    r = b.comando("/bailar apps")
    assert "Spotify, vlc" in r and "firefox, Spotify" in r
    assert "Deezer" in b.comando('/bailar permitir "C:\\Apps\\Deezer.exe"')
    assert b.config.get("baile", "apps") == ["Spotify", "vlc", "Deezer"]
    assert "ya cuenta" in b.comando("/bailar permitir spotify")
    assert "ya no cuenta" in b.comando("/bailar quitar VLC")
    assert b.config.get("baile", "apps") == ["Spotify", "Deezer"]
    assert "no estaba" in b.comando("/bailar quitar winamp")
    assert "nombre" in b.comando("/bailar permitir")
    assert len(b.config.sets) == 2


def test_linea_ajustada_al_ancho(crear):
    b = crear(ancho=34)
    b._iniciado = True
    b._on_cambio(True, "UnaAppConNombreMuyLargoDeVerdad")
    b.comando("/bailar")
    linea = b.linea()
    assert ancho_visible(linea) <= 33 and "BPM" in linea
    b2 = crear(ancho=12)
    b2.comando("/bailar")
    assert ancho_visible(b2.linea()) <= 11


def test_comandos_que_no_son_suyos(crear):
    b = crear()
    assert b.comando("/alarmas") is None and b.comando("hola") is None and b.comando("/bailarina") is None
    assert "Uso" in b.comando("/bailar lalala")


def test_detener_quita_el_titulo_y_para_el_detector(crear):
    b = crear()
    b.iniciar()
    b.comando("/bailar")
    b.detener()
    assert not b.bailando and "detener" in b.det.llamadas and b.c_.capa_titulo() is None


def test_hilo_de_la_animacion_arranca_y_acaba(crear):
    b = crear(hilo=True)
    b.comando("/bailar")
    assert esperar(lambda: b._hilo is not None and b._hilo.is_alive())
    h = b._hilo
    b.comando("/parar")
    h.join(2)
    assert not h.is_alive()
