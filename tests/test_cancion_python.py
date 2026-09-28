"""
Tests de servicios/cancion_python (sin Qt): la canción de un baile por el Mezclador
(canal `musica`) para sprites y patata. Carga en su hilo, posición, pausa, volumen,
fin, tope de duración (no se decodifica más de lo permitido), una carga nueva deja
sin efecto la anterior, liberar suelta el buffer y los argumentos de ffmpeg.
"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bailes_falsos as bf  # noqa: E402
from servicios import cancion_python as cp  # noqa: E402


class MezcladorFalso:
    def __init__(self):
        self.fuentes = {}
        self.llamadas = []
        self._n = 0

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self._n += 1
        self.fuentes[self._n] = {"buf": buf, "vol": vol, "canal": canal, "pos": 0.0, "pausada": False}
        self.llamadas.append(("reproducir", self._n, vol, canal))
        return self._n

    def posicion(self, i):
        f = self.fuentes.get(i)
        return None if f is None else f["pos"]

    def activo(self, i):
        return i in self.fuentes

    def pausar(self, i, on=True):
        self.llamadas.append(("pausar", i, on))
        if i in self.fuentes:
            self.fuentes[i]["pausada"] = on

    def set_volumen(self, i, v):
        self.llamadas.append(("volumen", i, v))
        if i in self.fuentes:
            self.fuentes[i]["vol"] = v

    def detener(self, i):
        self.llamadas.append(("detener", i))
        self.fuentes.pop(i, None)

    # lo que haría el callback de audio
    def avanzar(self, i, s):
        self.fuentes[i]["pos"] += s

    def acabar(self, i):
        self.fuentes.pop(i, None)


def buffer(segundos):
    return np.zeros((int(segundos * cp.FRECUENCIA), 2), np.float32)


def test_carga_en_su_hilo_y_suena_por_el_canal_musica(tmp_path):
    mez = MezcladorFalso()
    hilos = []

    def cargar(ruta, **kw):
        hilos.append((threading.current_thread().name, kw.get("cachear")))
        return buffer(3.0)
    r = cp.ReproductorCancion(mez, cargar=cargar)
    listo = threading.Event()
    res = []

    def al_listo(ok, texto):
        res.append((ok, texto, threading.current_thread().name))
        listo.set()
    r.cargar(tmp_path / "c.mp3", al_listo)
    assert listo.wait(5)
    assert res[0][:2] == (True, "") and res[0][2] == "lune-cancion" and hilos == [("lune-cancion", False)]
    assert r.cargada and r.duracion == pytest.approx(3.0)
    assert r.reproducir(0.4) is True
    i = mez.llamadas[-1][1]
    assert mez.llamadas[-1] == ("reproducir", i, 0.4, "musica") and r.sonando
    mez.avanzar(i, 1.25)
    assert r.posicion() == pytest.approx(1.25)
    r.pausar(True)
    assert mez.fuentes[i]["pausada"] and r.pausado and not r.sonando
    r.pausar(False)
    r.volumen(1.7)
    assert mez.fuentes[i]["vol"] == 1.0                    # recortado a 0..1
    assert not r.terminado
    mez.acabar(i)                                          # el Mezclador la dio por acabada
    assert r.terminado and r.posicion() is None
    assert r.reproducir(0.4) and mez.llamadas[-1][0] == "reproducir"      # repetir: sin recargar
    r.parar()
    assert not r.terminado and r.posicion() is None
    r.liberar()
    assert not r.cargada and r.reproducir(0.5) is False


def test_tope_de_duracion(monkeypatch):
    monkeypatch.setattr(cp, "MAX_DURACION_S", 2)
    r = cp.ReproductorCancion(MezcladorFalso(), cargar=lambda ruta, **kw: buffer(3.0), hilo=False)
    res = []
    r.cargar("larga.mp3", lambda ok, t: res.append((ok, t)))
    assert res[0][0] is False and "más de" in res[0][1] and not r.cargada and r.reproducir(1) is False
    r.cargar("corta.mp3", lambda ok, t: res.append((ok, t)))
    assert res[-1] == (False, res[-1][1])
    r2 = cp.ReproductorCancion(MezcladorFalso(), cargar=lambda ruta, **kw: buffer(1.5), hilo=False)
    r2.cargar("ok.mp3", lambda ok, t: res.append((ok, t)))
    assert res[-1] == (True, "")


def test_error_al_cargar_y_carga_nueva_anula_la_vieja():
    def falla(ruta, **kw):
        raise cp.ErrorCancion("ffmpeg no pudo leer x.mp3")
    r = cp.ReproductorCancion(MezcladorFalso(), cargar=falla, hilo=False)
    res = []
    r.cargar("x.mp3", lambda ok, t: res.append((ok, t)))
    assert res == [(False, "ffmpeg no pudo leer x.mp3")] and r.error

    soltar = threading.Event()

    def lenta(ruta, **kw):
        if "vieja" in str(ruta):
            soltar.wait(5)
        return buffer(1.0)
    r = cp.ReproductorCancion(MezcladorFalso(), cargar=lenta)
    llamadas = []
    hecho = threading.Event()
    r.cargar("vieja.mp3", lambda ok, t: llamadas.append("vieja"))
    r.cargar("nueva.mp3", lambda ok, t: (llamadas.append("nueva"), hecho.set()))
    assert hecho.wait(5)
    soltar.set()
    for _ in range(50):
        if threading.active_count() <= 2:
            break
        threading.Event().wait(0.02)
    assert llamadas == ["nueva"]


def test_cargar_cancion_con_ffmpeg_falso(tmp_path):
    p = bf.escribir(tmp_path / "c.ogg", bf.OGG)
    visto = []
    datos = np.arange(8, dtype="<f4").tobytes()

    def ej(cmd, **kw):
        visto.append((cmd, kw))
        return SimpleNamespace(returncode=0, stdout=datos, stderr=b"")
    buf = cp.cargar_cancion(p, ffmpeg="ffm", ejecutar=ej)
    assert buf.dtype == np.float32 and buf.shape == (4, 2) and buf[1, 0] == 2.0
    cmd, kw = visto[0]
    assert cmd == ["ffm", "-nostdin", "-v", "error", "-i", str(p), "-vn", "-map", "0:a:0", "-map_metadata", "-1",
                   "-t", "601", "-ac", "2", "-ar", "44100", "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
    assert kw["capture_output"] is True and kw["timeout"] == cp.TIEMPO_FFMPEG_S
    with pytest.raises(cp.ErrorCancion, match="no pudo leer"):
        cp.cargar_cancion(p, ffmpeg="ffm", ejecutar=lambda c, **k: SimpleNamespace(returncode=1, stdout=b"",
                                                                                     stderr=b"roto"))
    with pytest.raises(cp.ErrorCancion, match="no tiene audio"):
        cp.cargar_cancion(p, ffmpeg="ffm", ejecutar=lambda c, **k: SimpleNamespace(returncode=0, stdout=b"",
                                                                                     stderr=b""))
    with pytest.raises(cp.ErrorCancion, match="No encuentro"):
        cp.cargar_cancion(tmp_path / "no.mp3", ffmpeg="ffm", ejecutar=ej)


def test_wav_sin_ffmpeg_mira_la_duracion_antes(tmp_path, monkeypatch):
    import servicios.mezclador as mz
    monkeypatch.setattr(mz, "ruta_ffmpeg", lambda: None)
    corto = bf.escribir(tmp_path / "corto.wav", bf.wav(0.5, 8000))
    buf = cp.cargar_cancion(corto)
    assert buf.shape[1] == 2 and len(buf) == pytest.approx(0.5 * 44100, abs=2)
    largo = bf.escribir(tmp_path / "largo.wav", bf.wav(2.0, 8000))
    with pytest.raises(cp.ErrorCancion, match="más de"):
        cp.cargar_cancion(largo, max_s=0.5)                # 2 s > 0.5 + 1 s de margen: ni se lee
    with pytest.raises(cp.ErrorCancion, match="ffmpeg"):
        cp.cargar_cancion(bf.escribir(tmp_path / "x.mp3", bf.MP3))
