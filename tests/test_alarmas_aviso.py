"""
Tests de servicios/alarmas_aviso.py (sin Qt, mezclador y relojes falsos):

- sonido en bucle por el canal «alarma» (WAV al azar o el elegido), volumen acotado;
- cola FIFO; un disparo repetido no se encola dos veces;
- bloqueo de 5 s: ni apagar ni posponer antes (salvo `forzar`);
- apagar pasa a la siguiente, habla (menos la prueba) y la quita de `sonando`;
- posponer crea un temporizador «pospuesta» (en el almacén o en memoria);
- corte a los 900 s; detener() calla sin borrar `sonando` del archivo;
- el sonido que llega tarde (hilo) tras apagar se detiene;
- elegir_visual.
"""
import random
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.alarmas import Almacen, Disparo, Programador  # noqa: E402
from servicios.alarmas_aviso import CANAL, ControlAviso, elegir_visual  # noqa: E402


class Reloj:
    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


class MezcladorFalso:
    def __init__(self):
        self.sonando = {}
        self.diario = []
        self._n = 0

    def cargar_wav(self, ruta):
        return f"buf:{Path(ruta).name}"

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self._n += 1
        self.sonando[self._n] = (buf, vol, bucle, canal)
        self.diario.append(("reproducir", buf, vol, bucle, canal))
        return self._n

    def detener(self, sid):
        self.sonando.pop(sid, None)
        self.diario.append(("detener", sid))

    def detener_canal(self, canal):
        for k in [k for k, v in self.sonando.items() if v[3] == canal]:
            del self.sonando[k]
        self.diario.append(("detener_canal", canal))

    def set_dispositivo(self, nombre):
        self.diario.append(("dispositivo", nombre))


def D(origen, texto="", tipo="alarma", t=1000.0):
    return Disparo(origen, texto, tipo, 0.0, "07:30", t)


@pytest.fixture
def piezas(tmp_path):
    reloj = Reloj(0.0)
    mez = MezcladorFalso()
    diario = []
    alm = Almacen(tmp_path / "alarmas.json", reloj=Reloj(5000.0))
    av = ControlAviso(mezclador=mez, almacen=alm, reloj=reloj, lanzar=lambda f: f(),
                      on_mostrar=lambda d: diario.append(("mostrar", d.origen)),
                      on_ocultar=lambda d: diario.append(("ocultar", d.origen)),
                      on_voz=lambda d: diario.append(("voz", d.texto)),
                      azar=random.Random(3), epoch=Reloj(5000.0))
    return av, mez, reloj, diario, alm


def test_suena_en_bucle_por_el_canal_alarma(piezas):
    av, mez, reloj, diario, _ = piezas
    av.volumen = 3.0                                   # se acota a 1
    assert av.disparar(D("a1", "gimnasio")) is True
    assert av.sonando.origen == "a1"
    (buf, vol, bucle, canal), = mez.sonando.values()
    assert bucle is True and canal == CANAL == "alarma" and vol == 1.0
    assert buf in {"buf:alarma_1.wav", "buf:alarma_2.wav", "buf:alarma_3.wav"}
    assert diario == [("mostrar", "a1")]


def test_sonido_elegido(piezas):
    av, mez, *_ = piezas
    av.sonido = "alarma_2"
    av.disparar(D("a1"))
    assert list(mez.sonando.values())[0][0] == "buf:alarma_2.wav"
    assert av.ultimo_sonido == "alarma_2"


def test_cola_fifo(piezas):
    av, mez, reloj, diario, _ = piezas
    assert av.disparar(D("a1", "uno")) is True
    assert av.disparar(D("a2", "dos")) is False
    assert av.disparar(D("t1", "tres", "temporizador")) is False
    assert [d.origen for d in av.cola] == ["a2", "t1"]
    assert av.disparar(D("a2", "dos")) is False and len(av.cola) == 2     # repetido: no se duplica
    reloj.t = 6
    assert av.apagar()
    assert av.sonando.origen == "a2" and [d.origen for d in av.cola] == ["t1"]
    assert len(mez.sonando) == 1                                          # el sonido anterior se calló
    reloj.t = 12
    assert av.apagar()
    reloj.t = 18
    assert av.apagar()
    assert av.sonando is None and mez.sonando == {}
    assert diario == [("mostrar", "a1"), ("mostrar", "a2"), ("voz", "uno"), ("mostrar", "t1"),
                      ("voz", "dos"), ("ocultar", "t1"), ("voz", "tres")]


def test_bloqueo_de_5_s(piezas):
    av, mez, reloj, diario, _ = piezas
    av.disparar(D("a1"))
    reloj.t = 4.9
    assert not av.puede_apagar()
    assert av.restante_bloqueo() == pytest.approx(0.1)
    assert av.apagar() is False and av.posponer() is False
    assert av.sonando is not None
    reloj.t = 5.0
    assert av.puede_apagar() and av.apagar()
    assert av.sonando is None


def test_forzar_salta_el_bloqueo(piezas):
    av, *_ = piezas
    av.disparar(D("a1"))
    assert av.apagar(forzar=True)


def test_apagar_la_quita_de_sonando_en_el_archivo(piezas):
    av, mez, reloj, diario, alm = piezas
    d = D("a1", "gimnasio", t=4800.0)
    alm.anotar_sonando(d)
    av.disparar(d)
    reloj.t = 10
    av.apagar()
    assert alm.sonando() == []


def test_detener_no_borra_sonando(piezas):
    av, mez, reloj, diario, alm = piezas
    d = D("a1", "gimnasio", t=4800.0)
    alm.anotar_sonando(d)
    av.disparar(d)
    av.disparar(D("a2"))
    av.detener()
    assert av.sonando is None and av.cola == () and mez.sonando == {}
    assert [x.origen for x in alm.sonando()] == ["a1"]
    assert ("ocultar", "a1") not in diario and not any(e[0] == "voz" for e in diario)


def test_posponer_crea_pospuesta_en_el_almacen(piezas):
    av, mez, reloj, diario, alm = piezas
    av.posponer_min = 5
    av.disparar(D("a1", "gimnasio"))
    reloj.t = 6
    assert av.posponer()
    assert av.sonando is None and av.motivo_fin == "pospuesta"
    t, = alm.temporizadores()
    assert (t.duracion_s, t.texto, t.pospuesta, t.una_vez) == (300, "gimnasio", True, True)
    assert t.objetivo == 5000.0 + 300
    assert not any(e[0] == "voz" for e in diario)       # posponer no habla
    # Cuando vence, suena como «pospuesta».
    d, _ = Programador(alm).tick(datetime(2026, 9, 26, 7, 35), 5301.0)
    assert d[0].tipo == "pospuesta" and d[0].texto == "gimnasio"


def test_posponer_sin_almacen_va_en_memoria():
    reloj = Reloj(0.0)
    mostrados = []
    av = ControlAviso(mezclador=MezcladorFalso(), reloj=reloj, lanzar=lambda f: f(), posponer_min=1,
                      on_mostrar=lambda d: mostrados.append((d.origen, d.tipo)))
    av.disparar(D("a1", "x"))
    reloj.t = 5
    assert av.posponer()
    reloj.t = 64
    av.tick()
    assert mostrados == [("a1", "alarma")]
    reloj.t = 65
    av.tick()
    assert mostrados == [("a1", "alarma"), ("a1", "pospuesta")]


def test_la_prueba_no_se_pospone_ni_habla(piezas):
    av, mez, reloj, diario, alm = piezas
    av.disparar(Disparo("prueba", "Prueba", "prueba", 0.0, "", 1.0))
    reloj.t = 6
    assert av.posponer()
    assert alm.temporizadores() == []
    av.disparar(Disparo("prueba", "Prueba", "prueba", 0.0, "", 2.0))
    reloj.t = 12
    av.apagar()
    assert not any(e[0] == "voz" for e in diario)


def test_corte_a_los_900_s(piezas):
    av, mez, reloj, diario, alm = piezas
    d = D("a1", "gimnasio", t=4800.0)
    alm.anotar_sonando(d)
    av.disparar(d)
    reloj.t = 899
    av.tick()
    assert av.sonando is not None
    reloj.t = 900
    av.tick()
    assert av.sonando is None and av.motivo_fin == "cortada" and mez.sonando == {}
    assert ("ocultar", "a1") in diario and alm.sonando() == []
    assert not any(e[0] == "voz" for e in diario)


def test_sonido_que_llega_tarde_se_detiene():
    """El sonido va en un hilo: si al llegar ya la apagaron, se para."""
    reloj = Reloj(0.0)
    mez = MezcladorFalso()
    pendientes = []
    av = ControlAviso(mezclador=mez, reloj=reloj, lanzar=pendientes.append)
    av.disparar(D("a1"))
    av.apagar(forzar=True)
    for f in pendientes:
        f()
    assert mez.sonando == {}


def test_dispositivo_una_vez(piezas):
    av, mez, *_ = piezas
    av.dispositivo = "Altavoces"
    av.disparar(D("a1"))
    av.apagar(forzar=True)
    av.disparar(D("a2"))
    assert [e for e in mez.diario if e[0] == "dispositivo"] == [("dispositivo", "Altavoces")]


def test_fallo_de_audio_no_rompe_el_aviso():
    class Roto(MezcladorFalso):
        def reproducir(self, *a, **k):
            raise RuntimeError("sin tarjeta")
    mostrados = []
    av = ControlAviso(mezclador=Roto(), lanzar=lambda f: f(), on_mostrar=lambda d: mostrados.append(d.origen))
    assert av.disparar(D("a1")) and mostrados == ["a1"]


@pytest.mark.parametrize("kw,esperado", [
    (dict(juego=True, pantalla_grande=True, render="vrm", mascota_visible=True), "discreto"),
    (dict(juego=False, pantalla_grande=True, render="vrm", mascota_visible=True), "grande"),
    (dict(juego=False, pantalla_grande=True, render="", mascota_visible=False), "grande"),
    (dict(juego=False, pantalla_grande=False, render="sprites", mascota_visible=True), "burbuja"),
    (dict(juego=False, pantalla_grande=True, render="patata", mascota_visible=False), "discreto"),
])
def test_elegir_visual(kw, esperado):
    assert elegir_visual(**kw) == esperado
