"""Tests de servicios/voice.py con motores falsos: qué argumentos recibe
edge_tts.Communicate, el acento de gTTS, «Probar», on_error (voz inexistente →
NoAudioReceived), silenciar y la caché de parámetros. Sin red ni tarjeta de sonido."""
import os
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import voces  # noqa: E402
from servicios import voice as V  # noqa: E402
from nucleo import personajes  # noqa: E402


class Cfg:
    def __init__(self, **voz):
        self.d = {"voz": voz}

    def get(self, seccion, clave, default=None):
        return self.d.get(seccion, {}).get(clave, default)


class NoAudioReceived(Exception):
    """Mismo nombre que edge_tts.exceptions.NoAudioReceived."""


@pytest.fixture
def edge(monkeypatch):
    """edge_tts falso: Communicate guarda los argumentos y escribe un .mp3 de mentira.
    `edge.fallar[voz] = excepción` hace que esa voz falle al guardar."""
    mod = types.ModuleType("edge_tts")
    mod.llamadas = []
    mod.fallar = {}

    class Communicate:
        def __init__(self, text, voice="en-US-EmmaMultilingualNeural", *, rate="+0%",
                     volume="+0%", pitch="+0Hz", **_):
            mod.llamadas.append({"text": text, "voice": voice, "rate": rate,
                                 "pitch": pitch, "volume": volume})
            self.voice = voice

        async def save(self, ruta):
            exc = mod.fallar.get(self.voice)
            if exc is not None:
                raise exc
            Path(ruta).write_bytes(b"ID3falso")

    mod.Communicate = Communicate
    mod.exceptions = types.SimpleNamespace(NoAudioReceived=NoAudioReceived)
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    return mod


@pytest.fixture
def gtts(monkeypatch):
    mod = types.ModuleType("gtts")
    mod.llamadas = []

    class gTTS:
        def __init__(self, text, lang="en", tld="com", **_):
            mod.llamadas.append({"text": text, "lang": lang, "tld": tld})

        def save(self, ruta):
            Path(ruta).write_bytes(b"ID3falso")

    mod.gTTS = gTTS
    monkeypatch.setitem(sys.modules, "gtts", mod)
    return mod


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Sin mixer real, sin caché de voces del usuario y con un personaje controlable."""
    monkeypatch.setattr(voces, "RUTA_CACHE", tmp_path / "voces_edge.json")
    monkeypatch.setattr(V.VoiceEngine, "_abrir_mixer", lambda self, nombre=None: True)
    estado = {"personaje": {"nombre": "Lune"}}
    monkeypatch.setattr(personajes, "get_activo", lambda: estado["personaje"])
    return estado


def _motor(cfg=None, **kw):
    errores = []
    eng = V.VoiceEngine(cfg if cfg is not None else Cfg(), on_error=errores.append, **kw)
    return eng, errores


def _limpiar(ruta):
    if ruta and os.path.exists(ruta):
        os.unlink(ruta)


# ── Parámetros que llegan a edge_tts.Communicate ─────────────────────────────────

def test_pygame_sin_anuncio():
    assert os.environ.get("PYGAME_HIDE_SUPPORT_PROMPT") == "1"


def test_communicate_recibe_voz_rate_pitch_y_volumen_de_config(edge, entorno):
    eng, errores = _motor(Cfg(edge_voz="es-AR-TomasNeural", edge_rate="-10%",
                              edge_pitch="+5Hz", edge_volumen="+20%"))
    assert eng.available and eng.engine_name == "edge-tts"
    ruta = eng._sintetizar_a_archivo("Hola, ¿qué tal? 🙂")
    try:
        assert ruta and Path(ruta).read_bytes() == b"ID3falso"
        assert edge.llamadas == [{"text": "Hola, ¿qué tal?", "voice": "es-AR-TomasNeural",
                                  "rate": "-10%", "pitch": "+5Hz", "volume": "+20%"}]
        assert errores == []
    finally:
        _limpiar(ruta)


def test_la_voz_del_personaje_manda(edge, entorno):
    entorno["personaje"] = {"nombre": "Aria", "voz": {"id": "es-CU-BelkysNeural", "pitch": -4}}
    eng, _ = _motor(Cfg(edge_voz="es-AR-TomasNeural", edge_rate="+7%"))
    _limpiar(eng._sintetizar_a_archivo("Hola"))
    assert edge.llamadas[-1] == {"text": "Hola", "voice": "es-CU-BelkysNeural",
                                 "rate": "+7%", "pitch": "-4Hz", "volume": "+0%"}


def test_speak_tambien_usa_los_parametros(edge, entorno, monkeypatch):
    """El otro sitio donde antes iba fija es-MX-DaliaNeural: la lectura directa."""
    sonados = []
    monkeypatch.setattr(V.VoiceEngine, "_reproducir", lambda self, ruta: (sonados.append(ruta), _limpiar(ruta)))
    eng, _ = _motor(Cfg(edge_voz="es-VE-PaolaNeural", edge_rate="+12%"))
    eng._speak_blocking("Buenos días")
    assert len(sonados) == 1
    assert edge.llamadas[-1]["voice"] == "es-VE-PaolaNeural" and edge.llamadas[-1]["rate"] == "+12%"


def test_la_cache_de_2s_y_invalidar(edge, entorno):
    eng, _ = _motor()
    assert eng.params.id == voces.VOZ_POR_DEFECTO
    entorno["personaje"] = {"nombre": "Aria", "voz": "es-PR-KarinaNeural"}
    assert eng.params.id == voces.VOZ_POR_DEFECTO      # dentro de los 2 s: la de antes
    eng.invalidar_params()
    assert eng.params.id == "es-PR-KarinaNeural"


def test_texto_solo_con_signos_no_llama_a_edge(edge, entorno):
    eng, errores = _motor()
    assert eng._sintetizar_a_archivo("¿¡...!?") is None
    assert edge.llamadas == [] and errores == []


# ── on_error: avisar en vez de tragarse ──────────────────────────────────────────

def test_voz_inexistente_avisa_y_habla_con_la_de_siempre(edge, entorno):
    edge.fallar["es-XX-InventadaNeural"] = NoAudioReceived("No audio was received.")
    eng, errores = _motor(Cfg(edge_voz="es-XX-InventadaNeural"))
    ruta = eng._sintetizar_a_archivo("Hola")
    try:
        assert ruta is not None                                  # no se queda muda
        assert [c["voice"] for c in edge.llamadas] == ["es-XX-InventadaNeural", voces.VOZ_POR_DEFECTO]
        assert len(errores) == 1
        assert "es-XX-InventadaNeural" in errores[0] and "no devolvió audio" in errores[0]
        assert eng.ultimo_error == errores[0]
    finally:
        _limpiar(ruta)


def test_voz_conocida_sin_audio_avisa_sin_culpar_a_la_voz(edge, entorno):
    edge.fallar["es-ES-ElviraNeural"] = NoAudioReceived("No audio was received.")
    eng, errores = _motor(Cfg(edge_voz="es-ES-ElviraNeural"))
    assert eng._sintetizar_a_archivo("Hola") is None
    assert len(edge.llamadas) == 1                               # sin reintento con otra voz
    assert errores and "Vuelve a intentarlo" in errores[0]


def test_sin_red_avisa_y_no_deja_temporales(edge, entorno, monkeypatch, tmp_path):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    edge.fallar[voces.VOZ_POR_DEFECTO] = OSError("getaddrinfo failed")
    eng, errores = _motor()
    assert eng._sintetizar_a_archivo("Hola") is None
    assert errores and "internet" in errores[0]
    assert not list(tmp_path.glob("*.mp3"))


def test_el_mismo_aviso_no_se_repite_en_rafaga(edge, entorno):
    edge.fallar[voces.VOZ_POR_DEFECTO] = OSError("sin red")
    eng, errores = _motor()
    for _ in range(3):
        eng._sintetizar_a_archivo("Hola")
    assert len(errores) == 1


def test_on_error_que_revienta_no_rompe_la_voz(edge, entorno):
    edge.fallar[voces.VOZ_POR_DEFECTO] = OSError("sin red")

    def malo(_msg):
        raise RuntimeError("bug del que escucha")

    eng = V.VoiceEngine(Cfg(), on_error=malo)
    assert eng._sintetizar_a_archivo("Hola") is None


# ── gTTS con acento ──────────────────────────────────────────────────────────────

def test_gtts_usa_el_tld(gtts, entorno, monkeypatch):
    monkeypatch.delitem(sys.modules, "edge_tts", raising=False)
    monkeypatch.setattr(V.VoiceEngine, "_detectar_motores", staticmethod(lambda: {"gtts"}))
    eng, _ = _motor(Cfg(gtts_tld="es"))
    assert eng.engine_name == "gTTS"
    _limpiar(eng._sintetizar_a_archivo("Hola"))
    assert gtts.llamadas == [{"text": "Hola", "lang": "es", "tld": "es"}]


def test_personaje_con_gtts_aunque_haya_edge(edge, gtts, entorno):
    entorno["personaje"] = {"nombre": "Aria", "voz": {"motor": "gtts", "tld": "us"}}
    eng, _ = _motor()
    _limpiar(eng._sintetizar_a_archivo("Hola"))
    assert edge.llamadas == [] and gtts.llamadas[-1]["tld"] == "us"


# ── Kokoro: voz y velocidad, y respaldo a edge si falla ──────────────────────────

def test_kokoro_voz_velocidad_y_respaldo(edge, entorno, monkeypatch):
    from lune_core.voz import kokoro_backend
    pedidas = []
    salida = {"ruta": None}

    def sintetizar(texto, voz, velocidad, carpeta, idioma):
        pedidas.append((voz, round(velocidad, 3), idioma))
        return salida["ruta"]

    monkeypatch.setattr(kokoro_backend, "sintetizar", sintetizar)
    monkeypatch.setattr(V.VoiceEngine, "_kokoro_disponible", lambda self: True)
    entorno["personaje"] = {"nombre": "Aria", "voz": {"motor": "kokoro", "id": "af_heart", "rate": "+20%"}}
    eng, errores = _motor(Cfg(kokoro_velocidad=1.0, edge_voz="es-GT-MartaNeural"))
    assert eng.engine_name == "Kokoro (local)"
    # Kokoro devuelve None (pesos rotos…): se avisa y habla edge con su voz de config.
    ruta = eng._sintetizar_a_archivo("Hola")
    try:
        assert pedidas == [("af_heart", 1.2, "es")]
        assert ruta and edge.llamadas[-1]["voice"] == "es-GT-MartaNeural"
        assert errores and "Kokoro" in errores[0]
    finally:
        _limpiar(ruta)


# ── Probar, silenciar, reiniciar ─────────────────────────────────────────────────

def test_probar_voz_suena_con_la_voz_apagada_y_corta_lo_anterior(edge, entorno, monkeypatch):
    sonado = threading.Event()
    rutas = []

    def reproducir(self, ruta):
        rutas.append(ruta)
        _limpiar(ruta)
        sonado.set()

    monkeypatch.setattr(V.VoiceEngine, "_reproducir", reproducir)
    eng, errores = _motor()
    assert not eng._enabled
    gen_antes = eng._gen_voz
    assert eng.probar_voz('{"id": "es-CL-CatalinaNeural", "rate": 15}', "Probando")
    assert eng._gen_voz == gen_antes + 1                          # canceló lo que sonaba
    assert sonado.wait(5)
    assert edge.llamadas[-1] == {"text": "Probando", "voice": "es-CL-CatalinaNeural",
                                 "rate": "+15%", "pitch": "+0Hz", "volume": "+0%"}
    assert errores == []


def test_probar_voz_con_texto_dentro_del_json(edge, entorno, monkeypatch):
    sonado = threading.Event()
    monkeypatch.setattr(V.VoiceEngine, "_reproducir", lambda self, r: (_limpiar(r), sonado.set()))
    eng, _ = _motor()
    assert eng.probar_voz('{"motor_salida": "edge", "edge_voz": "es-NI-YolandaNeural", "texto": "Qué tal"}')
    assert sonado.wait(5)
    assert (edge.llamadas[-1]["voice"], edge.llamadas[-1]["text"]) == ("es-NI-YolandaNeural", "Qué tal")


def test_probar_voz_sin_parametros_usa_la_actual_y_frase_de_prueba(edge, entorno, monkeypatch):
    sonado = threading.Event()
    monkeypatch.setattr(V.VoiceEngine, "_reproducir", lambda self, r: (_limpiar(r), sonado.set()))
    eng, _ = _motor(Cfg(edge_voz="es-HN-KarlaNeural"))
    eng.silenciar(True)                                          # «Probar» es explícito: suena igual
    assert eng.probar_voz()
    assert sonado.wait(5)
    assert edge.llamadas[-1]["voice"] == "es-HN-KarlaNeural"
    assert edge.llamadas[-1]["text"].startswith("Hola, soy Lune")


def test_probar_voz_sin_motor_avisa(entorno, monkeypatch):
    monkeypatch.setattr(V.VoiceEngine, "_detectar_motores", staticmethod(lambda: set()))
    eng, errores = _motor()
    assert not eng.available
    assert eng.probar_voz() is False
    assert errores and "No hay motor de voz" in errores[0]


def test_silenciar_modo_juego(edge, entorno, monkeypatch):
    sonados = []
    monkeypatch.setattr(V.VoiceEngine, "_reproducir", lambda self, r: (sonados.append(r), _limpiar(r)))
    eng, _ = _motor()
    eng._enabled = True
    eng.silenciar(True)
    assert eng.silenciada
    assert eng.speak_segmentos([("happy", "Hola")]) is False
    eng.speak("Hola")                                            # no lanza hilo
    ruta = eng._sintetizar_a_archivo("Hola")
    eng._reproducir_archivo(ruta)                                # una frase del streaming en vuelo
    assert sonados == [] and not os.path.exists(ruta)            # no sonó y se borró
    assert V.VozStreaming(eng).iniciar() is False
    eng.silenciar(False)
    eng._speak_blocking("Hola")
    assert len(sonados) == 1


def test_reiniciar_motor_relee_motores_y_voz(edge, gtts, entorno, monkeypatch):
    eng, _ = _motor()
    assert eng.engine_name == "edge-tts"
    monkeypatch.setattr(V.VoiceEngine, "_detectar_motores", staticmethod(lambda: {"gtts"}))
    assert eng.reiniciar_motor() == "gTTS"
    entorno["personaje"] = {"nombre": "Aria", "voz": "es-CO-SalomeNeural"}
    monkeypatch.setattr(V.VoiceEngine, "_detectar_motores", staticmethod(lambda: {"edge", "gtts"}))
    assert eng.reiniciar_motor() == "edge-tts"
    assert eng.params.id == "es-CO-SalomeNeural"


def test_lo_que_ya_existia_sigue_ahi(entorno):
    eng, _ = _motor()
    for nombre in ("speak", "speak_segmentos", "cancelar", "toggle", "aplicar_salida", "probar_salida",
                   "_sintetizar_a_archivo", "_reproducir_archivo", "_quizas_rvc", "_speak_edge",
                   "_speak_gtts", "probar_voz", "reiniciar_motor", "silenciar", "invalidar_params"):
        assert callable(getattr(eng, nombre)), nombre
    assert V.VoiceEngine.al_hablar is None and hasattr(eng, "on_error")
    assert callable(V.listar_salidas)
