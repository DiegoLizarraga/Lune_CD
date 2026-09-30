"""
Tests del pulso de la canción de un baile (nucleo/bailes: analizar_pcm y
Biblioteca.analizar_pulso), el «equivalente mínimo» de las asistentes sin esqueleto
(D1): pista de clics sintética → BPM ± 2 y la fase del primer golpe; los
argumentos exactos de ffmpeg; la caché (no se repite; se rehace si cambia la
canción o el bpm del lune.json); ffmpeg que falla → 120 BPM sin caché.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bailes_falsos as bf  # noqa: E402
from nucleo import bailes as nbl  # noqa: E402


def err_fase(obtenida: float, esperada: float) -> float:
    return abs((obtenida - esperada + 0.5) % 1.0 - 0.5)


@pytest.mark.parametrize("bpm,primero", [(120, 0.1), (128, 0.23), (97, 0.4), (150, 0.05)])
def test_click_track_bpm_y_fase(bpm, primero):
    r = nbl.analizar_pcm(bf.clics(bpm, primero=primero), 11025)
    assert abs(r["bpm"] - bpm) <= 2.0
    periodo = 60.0 / bpm
    assert err_fase(r["fase0"], (-primero / periodo) % 1.0) <= 0.06          # ≤ 6 % de un golpe
    assert r["confianza"] >= 0.5
    # La fase sigue bien al final de la pista (el tempo es el de toda la canción).
    t = 39.0
    ultimo = primero + np.floor((t - primero) / periodo) * periodo
    assert err_fase(nbl.fase_en(t, r["bpm"], r["fase0"]), (t - ultimo) / periodo) <= 0.08


def test_silencio_ruido_y_bpm_fijo():
    silencio = np.zeros(11025 * 10, np.int16)
    assert nbl.analizar_pcm(silencio) == {"bpm": 120.0, "fase0": 0.0, "confianza": 0.0}
    assert nbl.analizar_pcm(silencio, bpm_fijo=90)["bpm"] == 90.0
    corto = bf.clics(120, dur=1.0)
    assert nbl.analizar_pcm(corto)["confianza"] == 0.0
    r = nbl.analizar_pcm(bf.clics(120, primero=0.1), bpm_fijo=120)
    assert r["bpm"] == 120.0 and err_fase(r["fase0"], 0.8) <= 0.06
    rng = np.random.default_rng(5)
    ruido = (rng.uniform(-0.5, 0.5, 11025 * 20) * 32767).astype(np.int16)
    assert nbl.analizar_pcm(ruido)["confianza"] < 0.5


def test_envolvente_a_50_hz():
    pcm = np.zeros(11025, np.int16)
    pcm[2205] = -32768                                   # 0.2 s → trozo 10
    t, picos = nbl.envolvente_pico(pcm, 11025)
    assert len(t) == 50 and t[0] == pytest.approx(0.01) and picos[10] == pytest.approx(1.0)
    assert picos.sum() == pytest.approx(1.0)


@pytest.fixture
def bib(tmp_path):
    carpeta = tmp_path / "bailes"
    bf.hacer_baile(carpeta, "Clics", audio=("clics.ogg", bf.OGG))
    ej = bf.EjecutarFalso(pcm=bf.clics(120, primero=0.1))
    b = nbl.Biblioteca(carpeta, tmp_path / "cache", config=bf.ConfigFalsa(), ffmpeg="ffm", ejecutar=ej)
    b.ej = ej
    return b


def test_analizar_pulso_con_ffmpeg_falso_y_argumentos_exactos(bib):
    b = bib.escanear()[0]
    r = bib.analizar_pulso(b)
    assert abs(r["bpm"] - 120) <= 2 and err_fase(r["fase0"], 0.8) <= 0.06
    assert bib.ej.cmds == [["ffm", "-nostdin", "-v", "error", "-i", str(b.audio), "-vn", "-map", "0:a:0",
                            "-ac", "1", "-ar", "11025", "-t", "1200", "-f", "s16le", "pipe:1"]]
    assert bib.ej.kw[0]["capture_output"] is True and bib.ej.kw[0]["timeout"] == 120
    cache = json.loads((bib.cache / f"{b.id}.pulso.json").read_text(encoding="utf-8"))
    assert cache["bpm"] == r["bpm"] and cache["audio"] == "clics.ogg"


def test_cache_no_repite_y_se_rehace_si_cambia(bib):
    b = bib.escanear()[0]
    r1 = bib.analizar_pulso(b)
    assert bib.analizar_pulso(b) == r1 and len(bib.ej.cmds) == 1              # con caché no se repite
    b.audio.write_bytes(bf.OGG + b"otra")                                     # la canción cambió
    bib.analizar_pulso(bib.escanear()[0])
    assert len(bib.ej.cmds) == 2
    bib.guardar_meta(b.id, {"bpm": 60})                                        # bpm a mano en lune.json
    r3 = bib.analizar_pulso(bib.obtener(b.id))
    assert len(bib.ej.cmds) == 3 and r3["bpm"] == 60.0


def test_ffmpeg_que_falla_da_120_y_no_se_cachea(bib):
    bib.ej.rc = 1
    b = bib.escanear()[0]
    r = bib.analizar_pulso(b)
    assert (r["bpm"], r["fase0"], r["confianza"]) == (120.0, 0.0, 0.0) and "error" in r
    assert not (bib.cache / f"{b.id}.pulso.json").exists()
    bib.ej.rc = 0
    assert abs(bib.analizar_pulso(b)["bpm"] - 120) <= 2 and len(bib.ej.cmds) == 2


def test_sin_cancion_ni_ffmpeg(tmp_path, monkeypatch):
    carpeta = tmp_path / "bailes"
    bf.hacer_baile(carpeta, "Mudo", audio=None, meta={"bpm": 100})
    bib = nbl.Biblioteca(carpeta, tmp_path / "c", ejecutar=bf.EjecutarFalso())
    b = bib.escanear()[0]
    assert bib.analizar_pulso(b) == {"bpm": 100.0, "fase0": 0.0, "confianza": 0.0}
    bf.hacer_baile(carpeta, "ConCancion")
    monkeypatch.setattr(nbl, "_ffmpeg_defecto", lambda: None)
    b2 = [x for x in bib.escanear() if x.titulo == "ConCancion"][0]
    r = bib.analizar_pulso(b2)
    assert r["bpm"] == 120.0 and "ffmpeg" in r["error"]
