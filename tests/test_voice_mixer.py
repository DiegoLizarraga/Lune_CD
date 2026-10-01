"""
Tests del mixer perezoso de la voz (servicios/voice.py, 11.3).

- El constructor no importa pygame ni abre la tarjeta; `available` no depende de eso.
- Se abre justo antes de sonar (frase, prueba de salida) en la salida elegida.
- Un vigilante lo cierra tras MIXER_CIERRE_S sin sonar (nunca mientras suena).
- aplicar_salida con el mixer cerrado solo guarda el nombre.
- Cortar (cancelar) sin mixer abierto no importa pygame.
Con un pygame falso en sys.modules: ni tarjeta de verdad ni ruido.
"""
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from servicios import voice as V  # noqa: E402
from servicios import voces  # noqa: E402
from nucleo import personajes  # noqa: E402


class _Music:
    def __init__(self, pg):
        self.pg = pg
        self._sonando = 0

    def load(self, ruta):
        self.pg.eventos.append(("load", ruta))

    def play(self):
        self.pg.eventos.append("play")
        self._sonando = 2                       # «suena» las dos próximas preguntas

    def get_busy(self):
        if self._sonando > 0:
            self._sonando -= 1
            return True
        return False

    def stop(self):
        self.pg.eventos.append("stop")
        self._sonando = 0

    def unload(self):
        self.pg.eventos.append("unload")


class _Mixer:
    def __init__(self, pg):
        self.pg = pg
        self.estado = None
        self.inits = []
        self.music = _Music(pg)
        self.ocupado = False                   # un Sound (el pitido de prueba) sonando

    def init(self, devicename=None, **_):
        self.inits.append(devicename)
        if devicename and devicename in self.pg.no_existen:
            raise RuntimeError("No such device")
        if self.pg.sin_tarjeta:
            raise RuntimeError("No available audio device")
        self.estado = (44100, -16, 2)

    def get_init(self):
        return self.estado

    def quit(self):
        self.pg.eventos.append("quit")
        self.estado = None

    def get_busy(self):
        return self.ocupado

    class Sound:
        def __init__(self, buffer=b""):
            self.buffer = buffer

        def play(self):
            pass


@pytest.fixture
def pg(monkeypatch):
    mod = types.ModuleType("pygame")
    mod.eventos = []
    mod.no_existen = set()
    mod.sin_tarjeta = False
    mod.mixer = _Mixer(mod)
    monkeypatch.setitem(sys.modules, "pygame", mod)
    return mod


@pytest.fixture
def edge(monkeypatch):
    mod = types.ModuleType("edge_tts")
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    return mod


@pytest.fixture
def entorno(monkeypatch, tmp_path, pg, edge):
    monkeypatch.setattr(voces, "RUTA_CACHE", tmp_path / "voces_edge.json")
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    return pg


class Cfg:
    def __init__(self, **voz):
        self.voz = voz

    def get(self, seccion, clave, default=None):
        return self.voz.get(clave, default) if seccion == "voz" else default


def _motor(cfg=None):
    avisos = []
    eng = V.VoiceEngine(cfg if cfg is not None else Cfg(), on_error=avisos.append)
    return eng, avisos


def _audio(tmp_path, nombre="frase.mp3"):
    ruta = tmp_path / nombre
    ruta.write_bytes(b"ID3falso")
    return str(ruta)


# ── Constructor ────────────────────────────────────────────────────────────────
def test_el_constructor_no_abre_la_tarjeta(entorno):
    eng, avisos = _motor(Cfg(dispositivo_salida="Auriculares"))
    assert eng.available and eng.engine_name == "edge-tts"
    assert entorno.mixer.inits == [] and not eng.mixer_abierto()
    assert eng._hilo_vig is None and avisos == []


def test_available_sin_pygame_instalado_es_falso(entorno, monkeypatch):
    monkeypatch.setattr(V, "_pygame_instalado", lambda: False)
    eng, _ = _motor()
    assert not eng.available


def test_el_constructor_no_importa_pygame():
    """En un proceso limpio: construir el motor no carga pygame (~350 ms en el hilo de Qt)."""
    codigo = ("import sys; from servicios import voice; v = voice.VoiceEngine(None); "
              "print('pygame' in sys.modules)")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True,
                       text=True, timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "False"


# ── Abrir al sonar ─────────────────────────────────────────────────────────────
def test_reproducir_abre_la_salida_de_config_y_suena(entorno, tmp_path):
    eng, avisos = _motor(Cfg(dispositivo_salida="Auriculares"))
    hablando = []
    eng.al_hablar = hablando.append
    ruta = _audio(tmp_path)
    eng._reproducir(ruta)
    assert entorno.mixer.inits == ["Auriculares"] and eng.salida_actual == "Auriculares"
    assert ("load", ruta) in entorno.eventos and "play" in entorno.eventos
    assert hablando == [True, False] and avisos == []
    assert not os.path.exists(ruta)                    # el temporal se borra igual
    assert eng.mixer_abierto()                         # se queda abierto hasta el silencio


def test_la_salida_que_ya_no_existe_cae_a_la_del_sistema_sin_quejarse(entorno, tmp_path):
    entorno.no_existen.add("Headset apagado")
    eng, avisos = _motor(Cfg(dispositivo_salida="Headset apagado"))
    eng._reproducir(_audio(tmp_path))
    assert entorno.mixer.inits == ["Headset apagado", None]
    assert eng.salida_actual == "" and avisos == []


def test_sin_tarjeta_avisa_al_primer_uso_y_no_revienta(entorno, tmp_path):
    entorno.sin_tarjeta = True
    eng, avisos = _motor()
    assert eng.available                               # se sabe al usarla, como antes
    ruta = _audio(tmp_path)
    eng._reproducir(ruta)
    assert avisos and "salida de audio" in avisos[0]
    assert "play" not in entorno.eventos and not os.path.exists(ruta)


# ── Vigilante: se cierra tras el silencio ──────────────────────────────────────
def test_revisar_cierre_suelta_la_tarjeta_tras_el_silencio(entorno, tmp_path):
    eng, _ = _motor()
    eng._reproducir(_audio(tmp_path))
    t = eng._ultimo_sonido
    assert eng.revisar_cierre(t + V.MIXER_CIERRE_S - 1) is False and eng.mixer_abierto()
    assert eng.revisar_cierre(t + V.MIXER_CIERRE_S + 0.1) is True
    assert not eng.mixer_abierto() and "quit" in entorno.eventos
    # la siguiente frase la vuelve a abrir
    eng._reproducir(_audio(tmp_path, "otra.mp3"))
    assert eng.mixer_abierto() and len(entorno.mixer.inits) == 2


def test_revisar_cierre_no_cierra_mientras_suena(entorno):
    eng, _ = _motor()
    assert eng._asegurar_mixer()
    t = eng._ultimo_sonido
    entorno.mixer.ocupado = True                       # el pitido de prueba (un Sound)
    assert eng.revisar_cierre(t + V.MIXER_CIERRE_S * 3) is False and eng.mixer_abierto()
    entorno.mixer.ocupado = False
    ahora = t + V.MIXER_CIERRE_S * 3
    assert eng.revisar_cierre(ahora + 1) is False      # el silencio cuenta desde que dejó de sonar
    assert eng.revisar_cierre(ahora + V.MIXER_CIERRE_S + 0.1) is True


def test_el_vigilante_cierra_solo(entorno, monkeypatch):
    monkeypatch.setattr(V, "VIGILANTE_PASO_S", 0.02)
    eng, _ = _motor()
    eng.cierre_mixer_s = 0.05
    assert eng._asegurar_mixer()
    hilo = eng._hilo_vig
    assert hilo is not None and hilo.name == "LuneVozVigilante"
    hilo.join(timeout=5)
    assert not hilo.is_alive() and not eng.mixer_abierto()


# ── Salida en caliente ─────────────────────────────────────────────────────────
def test_aplicar_salida_con_el_mixer_cerrado_solo_guarda_el_nombre(entorno, tmp_path):
    eng, _ = _motor(Cfg(dispositivo_salida="Altavoces"))
    assert eng.aplicar_salida("Auriculares") is True
    assert entorno.mixer.inits == [] and eng.salida_actual == "Auriculares"
    eng._reproducir(_audio(tmp_path))
    assert entorno.mixer.inits == ["Auriculares"]      # la elegida en caliente, no la de config


def test_aplicar_salida_con_el_mixer_abierto_lo_reabre(entorno):
    eng, _ = _motor()
    assert eng._asegurar_mixer()
    entorno.no_existen.add("Fantasma")
    assert eng.aplicar_salida("Fantasma") is False     # no está: cae al sistema y lo dice
    assert eng.salida_actual == "" and entorno.mixer.inits[-2:] == ["Fantasma", None]


def test_probar_salida_avisa_si_la_guardada_ya_no_existe(entorno):
    import time
    entorno.no_existen.add("Fantasma")
    eng, avisos = _motor()
    assert eng.aplicar_salida("Fantasma") is True      # cerrado: aún no se puede saber
    assert eng.probar_salida() is True                 # el pitido va en su hilo
    limite = time.monotonic() + 5
    while not avisos and time.monotonic() < limite:
        time.sleep(0.02)
    assert any("Fantasma" in a for a in avisos)
    assert eng.mixer_abierto() and eng.salida_actual == ""
    with eng._lock:                                    # que el pitido acabe antes de soltar el pygame falso
        pass


# ── Cortar sin mixer ───────────────────────────────────────────────────────────
def test_cancelar_sin_mixer_abierto_no_toca_pygame(entorno):
    eng, _ = _motor()
    gen = eng._gen_voz
    eng.cancelar()
    assert eng._gen_voz == gen + 1 and "stop" not in entorno.eventos
    assert eng._asegurar_mixer()
    eng.cancelar()
    assert "stop" in entorno.eventos


def test_cancelar_sin_pygame_cargado_no_lo_importa(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "pygame", raising=False)
    eng = V.VoiceEngine.__new__(V.VoiceEngine)
    eng.cancelar()
    eng._soltar_audio()
    assert "pygame" not in sys.modules
