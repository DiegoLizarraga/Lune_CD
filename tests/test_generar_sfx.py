"""
Tests de scripts/generar_sfx.py: formato de los WAV (44.1 kHz, 16 bits, mono),
bordes a cero (sin clicks), volumen moderado, patrón 880/660 Hz de las alarmas
(0.2 s sonando / 0.15 s en silencio) y generación determinista. Comprueba también
que los WAV del repo (ui_web/assets/sfx/) están generados y con ese formato.
"""
import importlib.util
import wave
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "generar_sfx.py"

ESPERADOS = {
    "alarma_1", "alarma_2", "alarma_3", "drag_start", "drag_stop", "comida_aparece",
    "comida_capa_1", "comida_capa_2", "trago_1", "trago_2", "trago_3",
    "mordisco_1", "mordisco_2", "mordisco_3", "blip", "menu_abrir", "menu_cerrar", "menu_boton",
}


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generar_sfx", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _leer(ruta):
    with wave.open(str(ruta), "rb") as w:
        params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32767.0
    return params, x


def test_estan_todos_los_sonidos(gen):
    assert set(gen.SONIDOS) == ESPERADOS
    assert gen.DIR_SFX == RAIZ / "ui_web" / "assets" / "sfx"


def test_formato_bordes_y_volumen(gen, tmp_path):
    rutas = gen.generar(tmp_path)
    assert {r.stem for r in rutas} == ESPERADOS
    for ruta in rutas:
        params, x = _leer(ruta)
        assert params == (1, 2, 44100), ruta.name
        assert x[0] == 0 and x[-1] == 0, f"{ruta.name}: el borde no está a cero (clic)"
        pico_db = 20 * np.log10(np.max(np.abs(x)))
        assert -20.0 <= pico_db <= -6.0, f"{ruta.name}: pico {pico_db:.1f} dBFS"
        seg = len(x) / 44100
        if ruta.stem.startswith("alarma"):
            assert 1.2 <= seg <= 1.8, ruta.name
        else:
            assert 0.03 <= seg <= 0.8, f"{ruta.name}: {seg:.2f} s no es un efecto corto"
        # la cola (últimos 5 ms) ya está prácticamente apagada
        assert np.max(np.abs(x[-220:])) < 0.05, ruta.name


def _frecuencia_dominante(x):
    esp = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.fft.rfftfreq(len(x), 1 / 44100)[np.argmax(esp)]


def test_alarmas_pitan_y_callan_a_su_ritmo(gen):
    patrones = []
    for nombre in ("alarma_1", "alarma_2", "alarma_3"):
        x = gen.sintetizar(nombre)
        casilla = int(round(0.35 * 44100))
        assert len(x) % casilla == 0, "la duración debe ser un número entero de casillas (bucle)"
        patron = []
        for i in range(len(x) // casilla):
            c = x[i * casilla:(i + 1) * casilla]
            sonando, silencio = c[int(0.02 * 44100):int(0.18 * 44100)], c[int(0.21 * 44100):]
            assert np.max(np.abs(silencio)) < 1e-9, f"{nombre}: suena en el silencio de la casilla {i}"
            if np.sqrt(np.mean(sonando ** 2)) < 1e-6:
                patron.append(0)
                continue
            f = _frecuencia_dominante(sonando)
            patron.append(880 if abs(f - 880) < 15 else 660 if abs(f - 660) < 15 else f)
        assert set(patron) <= {0, 660, 880}, (nombre, patron)
        assert sum(1 for p in patron if p) >= 2, (nombre, patron)
        patrones.append(tuple(patron))
    assert len(set(patrones)) == 3, f"los tres patrones deben ser distintos: {patrones}"


def test_determinista(gen, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generar(a, nombres=["mordisco_2", "trago_1", "alarma_3"])
    gen.generar(b, nombres=["mordisco_2", "trago_1", "alarma_3"])
    for nombre in ("mordisco_2", "trago_1", "alarma_3"):
        assert (a / f"{nombre}.wav").read_bytes() == (b / f"{nombre}.wav").read_bytes()


def test_variantes_distintas(gen):
    for grupo in (("trago_1", "trago_2", "trago_3"), ("mordisco_1", "mordisco_2", "mordisco_3"),
                  ("comida_capa_1", "comida_capa_2"), ("menu_abrir", "menu_cerrar")):
        sonidos = [gen.sintetizar(n) for n in grupo]
        for i in range(len(sonidos)):
            for j in range(i + 1, len(sonidos)):
                a, b = sonidos[i], sonidos[j]
                assert len(a) != len(b) or not np.allclose(a, b), (grupo[i], grupo[j])


def test_leeme(gen, tmp_path):
    gen.generar(tmp_path, nombres=["blip"])
    assert "scripts/generar_sfx.py" in (tmp_path / "LEEME.txt").read_text("utf-8")


def test_los_wav_del_repo_estan_generados():
    carpeta = RAIZ / "ui_web" / "assets" / "sfx"
    assert "scripts/generar_sfx.py" in (carpeta / "LEEME.txt").read_text("utf-8")
    for nombre in ESPERADOS:
        params, x = _leer(carpeta / f"{nombre}.wav")
        assert params == (1, 2, 44100) and len(x) > 0 and x[0] == 0 and x[-1] == 0, nombre
