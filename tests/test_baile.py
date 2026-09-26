"""
Tests de nucleo/baile: opciones para las páginas, duración, cuadros de la
terminal y los handlers de las herramientas `mascota_bailar` y `parar_baile`
(con un controlador falso y un `en_ui` que apunta en qué hilo se llamó).
"""
import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import baile as nb  # noqa: E402


class Config:
    def __init__(self, **baile):
        self.d = {"baile": baile}

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)


class BaileFalso:
    def __init__(self, puede=True, motivo=""):
        self.puede, self.ultimo_motivo = puede, motivo
        self.llamadas = []
        self.bailando = False

    def bailar(self, segundos=None, *, origen="manual"):
        self.llamadas.append(("bailar", segundos, origen, threading.get_ident()))
        self.bailando = self.puede
        return self.puede

    def parar(self):
        self.llamadas.append(("parar",))
        estaba, self.bailando = self.bailando, False
        return estaba


def test_ocho_estilos_y_opciones_pagina():
    assert len(nb.ESTILOS) == 8 and len(set(nb.ESTILOS)) == 8
    op = nb.opciones_pagina(Config(cambiar=True, cambiar_s=500, particulas=False), "palmas")
    assert op == {"estilo": "palmas", "cambiar": True, "cambiarS": 120, "particulas": False}
    op = nb.opciones_pagina(None, "no_existe", rng=random.Random(1))
    assert op["estilo"] in nb.ESTILOS and op["cambiar"] is False and op["cambiarS"] == 15
    assert op["particulas"] is True
    assert nb.opciones_pagina(Config(cambiar_s="x"))["cambiarS"] == 15
    assert nb.opciones_pagina(Config(cambiar_s=1))["cambiarS"] == 5


def test_segundos_validos():
    assert nb.segundos_validos(None) == 30
    assert nb.segundos_validos("45") == 45
    assert nb.segundos_validos(1) == 5 and nb.segundos_validos(9999) == 300
    assert nb.segundos_validos("abc") == 30


def test_frames_y_windows_terminal():
    assert nb.frames_ascii(False) == ("\\o/", "|o|", "/o\\", "_o_")
    assert len(nb.frames_ascii(True)) == 4 and nb.frames_ascii(True) != nb.frames_ascii(False)
    assert nb.es_windows_terminal({"WT_SESSION": "abc"}) is True
    assert nb.es_windows_terminal({}) is False


def test_herramienta_bailar_por_en_ui():
    b = BaileFalso()
    hilos = []

    def en_ui(fn):
        hilos.append("ui")
        return fn()
    r = nb.herramienta_bailar({"segundos": 45}, {"baile": b, "en_ui": en_ui})
    assert r == "¡A bailar! 45 s."
    assert hilos == ["ui"] and b.llamadas[0][:3] == ("bailar", 45, "manual")


def test_herramienta_bailar_con_cancion_dice_que_no_hay_reproductor():
    r = nb.herramienta_bailar({"cancion": "macarena"}, {"baile": BaileFalso()})
    assert "reproductor" in r and r.startswith("¡A bailar! 30 s.")


def test_herramienta_bailar_no_puede_con_motivo_legible():
    r = nb.herramienta_bailar({}, {"baile": BaileFalso(puede=False, motivo="grande")})
    assert r == (False, "Ahora no puedo bailar: estoy en pantalla grande.")
    assert nb.herramienta_bailar({}, {}) [0] is False
    assert nb.herramienta_bailar({}, None)[0] is False


def test_ctx_envuelto_por_el_ejecutor():
    b = BaileFalso()
    assert nb.herramienta_bailar({}, {"contexto": {"baile": b}}).startswith("¡A bailar!")


def test_herramienta_parar():
    b = BaileFalso()
    assert nb.herramienta_parar({}, {"baile": b}) == "No estaba bailando."
    b.bailando = True
    assert nb.herramienta_parar({}, {"baile": b}) == "Vale, dejo de bailar."
    assert nb.herramienta_parar({}, {})[0] is False


def test_herramienta_que_revienta_no_propaga():
    class Roto(BaileFalso):
        def bailar(self, *a, **k):
            raise RuntimeError("uy")
    ok, msg = nb.herramienta_bailar({}, {"baile": Roto()})
    assert ok is False and "uy" in msg
