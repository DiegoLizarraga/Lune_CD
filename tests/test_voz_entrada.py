"""
Tests de voz_entrada: elección de micrófono por nombre y grabación robusta.

Sin hardware: se inyecta un `sounddevice` falso en sys.modules con la lista de
dispositivos típica de Windows (cada micrófono repetido por API, nombres MME
recortados a 31 caracteres) para comprobar que se listan sin duplicar, que el
nombre guardado se resuelve a índice y que si el micrófono no acepta 16 kHz se
abre a su frecuencia nativa.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import voz_entrada as V  # noqa: E402


DISPOSITIVOS = [
    {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100},
    {"name": "Microphone Array (2- Realtek(R)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100},
    {"name": "Headset (WH-CH520)", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 16000},
    {"name": "Speakers (2- Realtek(R) Audio)", "max_input_channels": 0, "hostapi": 0, "default_samplerate": 44100},
    {"name": "Headset (WH-CH520)", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 16000},   # DirectSound
    {"name": "Microphone Array (2- Realtek(R) Audio)", "max_input_channels": 2, "hostapi": 2, "default_samplerate": 48000},  # WASAPI
]
HOSTAPIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}]


class _Default:
    device = [1, 3]


def _sd_falso(monkeypatch, streams_que_fallan=()):
    """Módulo sounddevice de mentira con query_devices/query_hostapis/RawInputStream."""
    sd = types.ModuleType("sounddevice")
    sd.default = _Default()

    def query_devices(device=None, kind=None):
        if device is None and kind is None:
            return list(DISPOSITIVOS)
        if device is None:
            return DISPOSITIVOS[_Default.device[0]]
        return DISPOSITIVOS[device]

    sd.query_devices = query_devices
    sd.query_hostapis = lambda: list(HOSTAPIS)
    abiertos = []

    class RawInputStream:
        def __init__(self, samplerate, **kw):
            if samplerate in streams_que_fallan:
                raise RuntimeError(f"Invalid sample rate {samplerate}")
            self.samplerate = samplerate
            self.kw = kw
            abiertos.append(self)
        def start(self): pass
        def stop(self): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    sd.RawInputStream = RawInputStream
    sd.abiertos = abiertos
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    return sd


# ── Listado ────────────────────────────────────────────────────────────────────

def test_listar_entradas_solo_mme_y_sin_repetir(monkeypatch):
    _sd_falso(monkeypatch)
    nombres = [e["nombre"] for e in V.listar_entradas()]
    # Solo la API MME (índice 0) y sin salidas
    assert nombres == ["Microsoft Sound Mapper - Input", "Microphone Array (2- Realtek(R)", "Headset (WH-CH520)"]
    assert [e["defecto"] for e in V.listar_entradas()] == [False, True, False]


def test_listar_entradas_sin_sounddevice(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    assert V.listar_entradas() == []


# ── Resolución nombre → índice ─────────────────────────────────────────────────

def test_resolver_entrada_exacta_y_por_prefijo(monkeypatch):
    _sd_falso(monkeypatch)
    assert V.resolver_entrada("Headset (WH-CH520)") == 2
    # Nombre completo guardado desde otra API → coincide por prefijo con el MME recortado
    assert V.resolver_entrada("Microphone Array (2- Realtek(R) Audio)") == 1
    assert V.resolver_entrada("") is None
    assert V.resolver_entrada(None) is None
    assert V.resolver_entrada("Micrófono que no existe") is None


def test_hay_microfono_con_indice(monkeypatch):
    _sd_falso(monkeypatch)
    assert V.hay_microfono(2) == (True, "Headset (WH-CH520)")
    ok, motivo = V.hay_microfono(3)
    assert ok is False and "no es un micrófono" in motivo


# ── Grabadora: frecuencia de respaldo y WAV a la frecuencia real ───────────────

def test_grabadora_cae_a_la_frecuencia_nativa(monkeypatch):
    sd = _sd_falso(monkeypatch, streams_que_fallan=(16000,))
    g = V.Grabadora(dispositivo=1)
    g.iniciar()
    assert g.grabando
    assert g.samplerate == 44100            # la nativa del dispositivo 1
    assert sd.abiertos[-1].kw["device"] == 1
    # 1 s de silencio a 44.1 kHz → WAV con esa frecuencia
    g._cola.put(b"\x00\x00" * 44100)
    ruta = g.detener()
    assert ruta is not None
    import wave
    with wave.open(str(ruta)) as w:
        assert w.getframerate() == 44100
    ruta.unlink()


def test_grabadora_descarta_clics_cortos(monkeypatch):
    _sd_falso(monkeypatch)
    g = V.Grabadora()
    g.iniciar()
    assert g.samplerate == 16000
    g._cola.put(b"\x00\x00" * 1000)         # 0.06 s: un clic sin querer
    assert g.detener() is None


def test_grabadora_sin_frecuencia_valida_avisa(monkeypatch):
    _sd_falso(monkeypatch, streams_que_fallan=(16000, 44100, 48000))
    g = V.Grabadora(dispositivo=1)
    with pytest.raises(RuntimeError, match="no pude abrir"):
        g.iniciar()


# ── Prueba de micrófono ────────────────────────────────────────────────────────

def test_probar_microfono_reporta_nivel(monkeypatch):
    sd = _sd_falso(monkeypatch)
    # El stream falso no llama al callback: se simula "voz" alimentándolo a mano.
    original = sd.RawInputStream

    class ConVoz(original):
        def __enter__(self):
            cb = self.kw["callback"]
            cb(b"\x00\x40" * 1600, 1600, None, None)     # bloque con señal (~0.5 de amplitud)
            cb(b"\x00\x00" * 1600, 1600, None, None)     # bloque de silencio
            return self
    sd.RawInputStream = ConVoz
    monkeypatch.setattr(V, "dependencias_faltantes", lambda: [])
    r = V.probar_microfono(2, segundos=0.01)
    assert r["ok"] is True and r["pico"] > 0.4 and r["nombre"] == "Headset (WH-CH520)"
    assert r["error"] == ""


def test_probar_microfono_sin_sounddevice(monkeypatch):
    monkeypatch.setattr(V, "dependencias_faltantes", lambda: ["sounddevice"])
    r = V.probar_microfono()
    assert r["ok"] is False and "sounddevice" in r["error"]


def test_mensaje_prueba_es_legible():
    from ui.audio_prueba import mensaje_prueba
    assert "Te oigo" in mensaje_prueba({"ok": True, "pico": 0.1, "nombre": "Headset"})
    assert "No oí nada" in mensaje_prueba({"ok": False, "pico": 0.0, "nombre": "Headset"})
    assert "No pude abrir" in mensaje_prueba({"ok": False, "error": "boom"})


# ── Salida de audio ────────────────────────────────────────────────────────────

def test_voiceengine_cae_a_la_salida_del_sistema_si_no_existe(monkeypatch):
    """Elegir una salida que ya no está (headset apagado) no deja a Lune muda."""
    pygame = pytest.importorskip("pygame")
    from servicios import voice

    llamadas = []
    estado = {"init": None}

    def init_falso(devicename=None, **kw):
        llamadas.append(devicename)
        if devicename:
            raise pygame.error("No such device")
        estado["init"] = (44100, -16, 2)

    monkeypatch.setattr(pygame.mixer, "init", init_falso)
    monkeypatch.setattr(pygame.mixer, "quit", lambda: estado.update(init=None))
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: estado["init"])

    class ConfigFalsa:
        def get(self, seccion, clave, default=None):
            return {"motor_salida": "auto", "dispositivo_salida": "Headset apagado"}.get(clave, default)

    ve = voice.VoiceEngine(ConfigFalsa())
    if ve._engine is None:
        pytest.skip("sin edge-tts/gtts en este entorno")
    assert llamadas == []                              # mixer perezoso: el constructor no abre nada
    assert ve._asegurar_mixer() is True                # antes de sonar
    assert llamadas[:2] == ["Headset apagado", None]   # probó la pedida y cayó al sistema
    assert ve.salida_actual == ""
    # y en caliente, una salida válida (None → sistema) se aplica sin quejas
    assert ve.aplicar_salida("") is True
