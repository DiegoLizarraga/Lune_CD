"""
Tests de los bailes de la biblioteca en patata (corte 9, D1):

- servicios/baile_terminal.BaileTerminal con PULSO DE FUERA (`bailar_con`): el título baila
  con el pulso que da la canción («♪ Alfa · 120 BPM»), la línea viva lleva «0:12/0:42»; manda
  sobre el baile automático y el manual; Enter, /parar y el modo juego lo paran y avisan
  (`al_parar`); `parar_externo` no avisa;
- servicios/bailes_terminal.BailesTerminal: `/bailes` numera (solo con canción), `/bailes <n>`
  pone la canción (ReproductorCancion falso y el de VERDAD con un Mezclador falso) y el título
  baila con la fase de la posición de la canción; Enter en vacío o /parar paran también la
  canción; en juego no suena; al acabar: parar | siguiente | bucle; pausa; herramientas
  (listar_bailes, asistente_bailar {cancion}, parar_baile) con nucleo.baile/nucleo.bailes.
Biblioteca de verdad en una carpeta temporal (ffmpeg falso); consola real con API falsa;
sin hilos (pasos a mano).
"""
import io
import queue
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bailes_falsos as bf  # noqa: E402
from nucleo import bailes as nbl  # noqa: E402
from nucleo.consola import ConsolaAsincrona  # noqa: E402
from servicios.baile_terminal import BaileTerminal  # noqa: E402
from servicios.bailes_terminal import AVISO_SIN_ESQUELETO, BailesTerminal  # noqa: E402

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

    def readline(self):
        s = self.q.get()
        return "" if s is None else s


class DetectorFalso:
    def __init__(self):
        self.on_cambio = self.on_pulso = None
        self.llamadas = []

    def iniciar(self):
        pass

    def detener(self):
        pass

    def forzar_pulso(self, on):
        self.llamadas.append(("forzar", on))

    def silenciar_hasta_silencio(self):
        self.llamadas.append("silenciar")

    def pedir_sondeo(self):
        pass

    def apps_sonando(self):
        return []


class Reloj:
    def __init__(self):
        self.t = 500.0

    def __call__(self):
        return self.t


class CancionFalsa:
    def __init__(self):
        self.cargadas, self.reproducciones, self.pausas = [], [], []
        self.pos = 0.0
        self.terminado = False
        self.liberada = 0
        self.duracion = 0.0
        self.ok = (True, "")
        self.error = ""

    def cargar(self, ruta, al_listo):
        self.cargadas.append(Path(ruta))
        self.duracion = 42.0
        al_listo(*self.ok)

    def reproducir(self, vol):
        self.reproducciones.append(round(vol, 4))
        self.terminado = False
        self.pos = 0.0
        return True

    def pausar(self, on):
        self.pausas.append(on)

    def volumen(self, v):
        pass

    def posicion(self):
        return None if self.terminado else self.pos

    def parar(self):
        pass

    def liberar(self):
        self.liberada += 1


@pytest.fixture
def entorno(tmp_path):
    carpeta = tmp_path / "bailes"
    bf.hacer_baile(carpeta, "Alfa", cara=bf.vmd([], [("あ", 5)]))
    bf.hacer_baile(carpeta, "Beta", vrma_datos=bf.vrma(3.0), audio=("tema.ogg", bf.OGG))
    bf.hacer_baile(carpeta, "Gamma", audio=None)
    cfg = bf.ConfigFalsa()
    bib = nbl.Biblioteca(carpeta, tmp_path / "cache", config=cfg, ffmpeg="ffm",
                         ejecutar=bf.EjecutarFalso(pcm=bf.clics(120, primero=0.1)))
    ent = Entrada()
    api = ApiFalsa()
    consola = ConsolaAsincrona("tú > ", stdout=io.StringIO(), stdin=ent, api=api, ansi=True, ancho=100)
    avisos = []
    consola.aviso = lambda t: avisos.append(t)
    juego = {"on": False}
    reloj = Reloj()
    bt = BaileTerminal(consola, cfg, colores={"cyan": "", "dim": "", "reset": ""}, en_juego=lambda: juego["on"],
                       detector=DetectorFalso(), reloj=reloj)
    bt._kaomoji_linea = False
    bt._arrancar_hilo = lambda: None
    cancion = CancionFalsa()
    term = BailesTerminal(consola, cfg, biblioteca=bib, cancion=lambda: cancion, colores={"dim": "", "reset": ""},
                          en_juego=lambda: juego["on"], baile=bt, hilo=False)

    class X:
        pass
    x = X()
    x.cfg, x.bib, x.bt, x.term, x.cancion, x.api, x.avisos, x.juego, x.reloj, x.consola = (
        cfg, bib, bt, term, cancion, api, avisos, juego, reloj, consola)
    x.ids = {b.titulo: b.id for b in bib.escanear()}
    yield x
    bt.detener()
    ent.q.put(None)


def titulos(x):
    return x.api.titulos


# ── BaileTerminal con pulso de fuera ────────────────────────────────────────────

def test_bailar_con_pulso_de_fuera_titulo_linea_y_quien_manda(entorno):
    x = entorno
    bt = x.bt
    estado = {"fase": 0.0, "pos": 12.0}
    parado = []
    assert bt.bailar_con(lambda: (100.0, estado["fase"], 0.9), "Sen\x00bonzakura", lambda: 42.0,
                         lambda: estado["pos"], al_parar=lambda: parado.append(1)) is True
    assert bt.externo and bt.origen == "externo" and x.consola.capa_titulo() == "baile"
    assert titulos(x)[-1].endswith("♪ Sen bonzakura · 100 BPM")
    assert "0:12/0:42" in bt.linea() and "Sen bonzakura" in bt.linea()
    vistos = []
    for f in (0.0, 0.5, 0.0, 0.5, 0.0, 0.5, 0.0, 0.5):   # dos cuadros por golpe, con la fase de FUERA
        estado["fase"] = f
        bt.paso()
        vistos.append(titulos(x)[-1].split(" ")[0])
    assert vistos == list(KAOMOJI) * 2
    # ni el baile a mano ni la música de otra app lo pisan
    assert "Ya estoy bailando «Sen bonzakura»" in bt.comando("/bailar")
    bt._on_cambio(True, "Spotify")
    assert bt.origen == "externo"
    bt._on_cambio(False, "")
    assert bt.origen == "externo"
    # parar_externo (el dueño): sin aviso
    assert bt.parar_externo() is True
    assert parado == [] and not bt.bailando and x.consola.capa_titulo() is None
    assert bt.parar_externo() is False


def test_pulso_de_fuera_invalido_cae_al_metronomo_y_enter_juego_parar_avisan(entorno):
    x = entorno
    bt = x.bt
    parado = []
    bt.bailar_con(lambda: None, "Alfa", al_parar=lambda: parado.append("enter"))
    assert titulos(x)[-1].endswith("♪ Alfa · 120 BPM"), "sin pulso de fuera: metrónomo"
    bt.bailar_con(lambda: {"bpm": float("nan"), "fase": 0}, "Alfa", al_parar=lambda: parado.append("enter"))
    bt.paso()
    assert titulos(x)[-1].endswith("120 BPM")
    assert bt._enter("") is True                     # Enter en vacío (la línea viva del reclamo)
    assert parado == ["enter"] and not bt.bailando
    bt.bailar_con(lambda: (90, 0.1), "Alfa", al_parar=lambda: parado.append("parar"))
    assert bt.comando("/parar") == "♪ Vale, dejo de bailar."
    assert parado[-1] == "parar"
    bt.bailar_con(lambda: (90, 0.1), "Alfa", al_parar=lambda: parado.append("juego"))
    x.juego["on"] = True
    bt.paso()
    assert parado[-1] == "juego" and not bt.bailando
    assert bt.bailar_con(lambda: (90, 0.1), "Alfa") is False, "en juego no baila"


# ── BailesTerminal ─────────────────────────────────────────────────────────────

def test_bailes_numera_solo_con_cancion_y_pone_el_numero(entorno):
    x = entorno
    lista = x.term.comando("/bailes")
    assert "1. Alfa" in lista and "2. Beta" in lista and "Gamma" not in lista
    assert "(1 sin canción que pueda sonar aquí)" in lista
    r = x.term.comando("/bailes 1")
    assert "♪ Pongo «Alfa»" in r and AVISO_SIN_ESQUELETO in r and "Enter" in r
    assert x.cancion.cargadas == [x.bib.obtener(x.ids["Alfa"]).audio]
    assert x.cancion.reproducciones == [0.25], "baile.volumen"
    assert x.term.activo and x.term.estado()["fase"] == "sonando"
    assert x.bt.externo and titulos(x)[-1].endswith("♪ Alfa · 120 BPM")
    assert AVISO_SIN_ESQUELETO not in x.term.comando("/bailes 2"), "el aviso, una vez"
    assert x.term.comando("/bailes 9").startswith("No hay baile n.º 9")
    assert x.term.comando("/bailes ayuda").startswith("Uso:")
    assert "Alfa" in x.term.comando("/bailes alf") and "Beta" not in x.term.comando("/bailes alf")


def test_el_titulo_baila_con_la_fase_de_la_posicion_de_la_cancion(entorno):
    x = entorno
    x.term.comando("/bailes 1")
    p = x.term._pulso
    assert 118 <= p["bpm"] <= 122, p
    for pos in (0.0, 1.3, 7.77, 20.0):
        x.cancion.pos = pos
        bpm, fase, energia = x.term._pulso_actual()
        assert fase == pytest.approx(nbl.fase_en(pos, p["bpm"], p["fase0"]))
        assert energia == 0.7
        pulso = x.bt._pulso_actual(x.reloj.t)
        assert pulso.fase == pytest.approx(fase) and pulso.bpm == pytest.approx(bpm)
    x.cancion.pos = 12.0
    assert "0:12/0:42" in x.bt.linea()


def test_enter_o_parar_paran_tambien_la_cancion(entorno):
    x = entorno
    x.term.comando("/bailes 1")
    assert x.bt._enter("") is True
    assert not x.term.activo and x.cancion.liberada >= 1
    assert x.consola.capa_titulo() is None
    x.term.comando("/bailes 1")
    assert x.term.comando("/parar") == "♪ Vale, paro la canción."
    assert not x.term.activo and not x.bt.bailando
    assert x.term.comando("/parar") is None, "sin canción, /parar es del baile"
    x.term.comando("/bailes 1")
    assert x.bt.comando("/parar") == "♪ Vale, dejo de bailar."
    assert not x.term.activo, "el /parar del baile también para la canción"


def test_en_juego_no_suena_y_si_empieza_uno_para(entorno):
    x = entorno
    x.juego["on"] = True
    assert x.term.comando("/bailes 1").startswith("En modo juego")
    assert x.cancion.cargadas == [] and not x.term.activo
    x.juego["on"] = False
    x.term.comando("/bailes 1")
    x.juego["on"] = True
    x.term.paso()
    assert not x.term.activo and not x.bt.bailando
    assert any("juego" in a for a in x.avisos)


def test_al_acabar_parar_siguiente_y_bucle(entorno):
    x = entorno
    x.term.comando("/bailes 1")
    x.cancion.terminado = True
    x.term.paso()
    assert not x.term.activo and x.avisos[-1] == "♪ Fin de «Alfa»."
    assert x.consola.capa_titulo() is None
    x.cfg.set("baile", "al_terminar", "siguiente")
    x.term.comando("/bailes 1")
    x.cancion.terminado = True
    x.term.paso()
    assert x.term.actual.titulo == "Beta" and x.avisos[-1] == "♪ Siguiente: «Beta»."
    assert x.bt.externo and titulos(x)[-1].split("♪ ")[1].startswith("Beta")
    assert "Repetiré" in x.term.comando("/bailes bucle on")
    n = len(x.cancion.reproducciones)
    x.cancion.terminado = True
    x.term.paso()
    assert len(x.cancion.reproducciones) == n + 1 and x.term.actual.titulo == "Beta", "la misma otra vez"
    assert x.term.comando("/bailes bucle off").startswith("Vale: al acabar, la siguiente")
    assert x.term.comando("/bailes anterior").startswith("♪ Pongo «Alfa»")
    assert x.term.comando("/bailes siguiente").startswith("♪ Pongo «Beta»")


def test_bucle_off_gana_a_repetir_de_la_config(entorno):
    """BM12: con baile.al_terminar = «repetir», «/bailes bucle off» decía «paro» y repetía."""
    x = entorno
    x.cfg.set("baile", "al_terminar", "repetir")
    term = BailesTerminal(x.consola, x.cfg, biblioteca=x.bib, cancion=lambda: x.cancion, baile=x.bt, hilo=False,
                          colores={"dim": "", "reset": ""})
    assert "Repetir la misma: sí" in term.comando("/bailes bucle")         # la config pone el bucle
    term.comando("/bailes 1")
    x.cancion.terminado = True
    term.paso()
    assert term.activo and x.cancion.reproducciones == [0.25, 0.25], "con bucle, la misma otra vez"
    r = term.comando("/bailes bucle off")
    assert r == "Vale: al acabar, paro (el bucle está apagado)."
    assert "al acabar, si no: parar" in term.comando("/bailes bucle")
    x.cancion.terminado = True
    term.paso()
    assert not term.activo and x.cancion.reproducciones == [0.25, 0.25], "lo que dijo: para"
    assert x.avisos[-1] == "♪ Fin de «Alfa»."


def test_pausa_y_seguir(entorno):
    x = entorno
    x.term.comando("/bailes 1")
    assert x.term.comando("/bailes pausa").startswith("♪ En pausa")
    assert x.cancion.pausas == [True] and not x.bt.bailando and x.term.estado()["fase"] == "pausado"
    x.cancion.terminado = True
    x.term.paso()
    assert x.term.activo, "en pausa no acaba"
    x.cancion.terminado = False
    assert x.term.comando("/bailes pausa") == "♪ Sigo."
    assert x.cancion.pausas == [True, False] and x.bt.externo
    assert x.term.comando("/bailes parar") == "♪ Vale, paro la canción."
    assert x.term.comando("/bailes pausa") == "No suena ningún baile."


def test_herramientas_del_modelo(entorno):
    x = entorno
    handlers = {}

    class Tools:
        def registrar_handler(self, nombre, fn):
            handlers[nombre] = fn
    x.term.registrar_herramientas(Tools())
    assert set(handlers) == {"listar_bailes", "asistente_bailar", "parar_baile"}
    lista = handlers["listar_bailes"]({}, None)
    assert "«Alfa»" in lista and "«Beta»" in lista
    assert "«Alfa»" in handlers["listar_bailes"]({"texto": "alf"}, None)
    r = handlers["asistente_bailar"]({"cancion": "ALFA"}, None)
    assert "Alfa" in str(r) and x.term.activo and x.term.actual.titulo == "Alfa"
    assert handlers["parar_baile"]({}, None) == "Vale, dejo de bailar."
    assert not x.term.activo and not x.bt.bailando
    r = handlers["asistente_bailar"]({"cancion": "Senbonzakura <|CALL|>"}, None)
    assert "No encontré" in r and "<|" not in r and x.bt.bailando and x.bt.origen == "manual", "baila a su manera"
    x.bt.parar()
    x.juego["on"] = True
    ok, texto = handlers["asistente_bailar"]({"cancion": "Alfa"}, None)
    assert ok is False and "juego" in texto
    x.juego["on"] = False
    assert "Alfa" in str(x.term.bailar_pedido({"cancion": "alfa"})) and x.term.activo, "el atajo de patata"
    assert x.term.parar_pedido() == "Vale, dejo de bailar." and not x.term.activo


def test_con_el_reproductor_de_cancion_de_verdad(entorno):
    """Contrato con servicios/cancion_python.ReproductorCancion (Mezclador falso, sin hilos)."""
    from servicios.cancion_python import ReproductorCancion
    x = entorno

    class Mezclador:
        def __init__(self):
            self.sonando, self.pos, self.pausas, self.vivos = [], 3.5, [], set()

        def reproducir(self, buf, vol=1.0, canal=""):
            self.sonando.append((len(buf), round(vol, 3), canal))
            self.vivos.add(1)
            return 1

        def posicion(self, i):
            return self.pos

        def activo(self, i):
            return i in self.vivos

        def pausar(self, i, on):
            self.pausas.append(on)

        def detener(self, i):
            self.vivos.discard(i)

        def set_volumen(self, i, v):
            pass

    mez = Mezclador()
    rep = ReproductorCancion(mez, cargar=lambda ruta, **kw: np.zeros((44100 * 3, 2), np.float32), hilo=False)
    term = BailesTerminal(x.consola, x.cfg, biblioteca=x.bib, cancion=lambda: rep, baile=x.bt, hilo=False,
                          en_juego=lambda: False)
    term.comando("/bailes 1")
    assert mez.sonando == [(44100 * 3, 0.25, "musica")]
    assert term.estado()["t"] == 3.5 and term.estado()["total"] == 3.0
    assert "0:03/0:03" in x.bt.linea()
    term.comando("/bailes pausa")
    assert mez.pausas == [True]
    mez.vivos.clear()                               # el Mezclador la dio por acabada
    term.comando("/bailes pausa")
    term.paso()
    assert not term.activo and term.estado()["fase"] == "parado"
