"""Tests del servicio de voz: segmentador y pipeline de reproducción ordenada."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core.voz import segmentador as S  # noqa: E402
from lune_core.voz.pipeline import PipelineVoz  # noqa: E402


# ── Segmentador ─────────────────────────────────────────────────────────────────

def test_corte_por_frase():
    segs = S.segmentar("Hola mundo. ¿Cómo estás? Muy bien gracias.")
    assert len(segs) == 3
    assert segs[0].startswith("Hola mundo")


def test_numeros_con_punto_no_cortan():
    segs = S.segmentar("El valor de pi es 3.14 y sigue siendo importante para todos hoy.")
    assert len(segs) == 1


def test_puntos_suspensivos_no_cortan_multiple():
    segs = S.segmentar("Espera un momento... ya casi está listo todo el asunto.")
    # "..." no genera 3 segmentos; a lo sumo 2 frases
    assert len(segs) <= 2


def test_max_palabras_corta_lo_largo():
    texto = " ".join(["palabra"] * 80)   # sin puntuación
    segs = S.segmentar(texto, max_palabras=30)
    assert len(segs) >= 2
    assert all(len(s.split()) <= 30 for s in segs)


def test_las_primeras_frases_salen_antes():
    """Boost: las 2 primeras salen con umbral bajo (2 palabras) para latencia inicial."""
    s = S.SegmentadorStream()
    # 2 palabras + coma: con boost (umbral 2) sale ya; sin boost (umbral 4) esperaría
    assert s.escribir("Hola amigo, ") == ["Hola amigo,"]
    # una frase corta más también sale (segunda del boost)
    assert s.escribir("qué tal, ") == ["qué tal,"]
    # tras 2 frases, el umbral sube: 2 palabras con coma ya NO cortan
    assert s.escribir("muy bien, ") == []


def test_streaming_por_trozos():
    s = S.SegmentadorStream()
    segs = []
    for chunk in ["Me alegro ", "mucho de verte hoy. ", "¿Qué ", "necesitas de mi parte?"]:
        segs += s.escribir(chunk)
    segs += s.vaciar()
    assert len(segs) == 2
    assert "Me alegro" in segs[0]


def test_vaciar_emite_lo_que_queda():
    s = S.SegmentadorStream()
    s.escribir("frase sin cerrar todavia")
    assert s.vaciar() == ["frase sin cerrar todavia"]


# ── Pipeline ────────────────────────────────────────────────────────────────────

def correr(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=15))


def test_reproduce_en_orden_aunque_sintetice_desordenado():
    """La clave: síntesis concurrente, reproducción en orden estricto."""
    reproducidos = []

    async def sintetizar(texto):
        # la segunda frase tarda MENOS que la primera → termina antes
        await asyncio.sleep(0.05 if "primera" in texto else 0.01)
        return f"audio:{texto}"

    async def reproducir(audio, texto):
        reproducidos.append(texto)

    async def caso():
        pipe = PipelineVoz(sintetizar, reproducir, concurrencia=4)
        await pipe.encolar("la primera")
        await pipe.encolar("la segunda")
        await pipe.encolar("la tercera")
        await pipe.fin()

    correr(caso())
    assert reproducidos == ["la primera", "la segunda", "la tercera"]


def test_concurrencia_limita_sintesis_simultanea():
    activos = {"n": 0, "max": 0}

    async def sintetizar(texto):
        activos["n"] += 1
        activos["max"] = max(activos["max"], activos["n"])
        await asyncio.sleep(0.02)
        activos["n"] -= 1
        return texto

    async def reproducir(audio, texto):
        pass

    async def caso():
        pipe = PipelineVoz(sintetizar, reproducir, concurrencia=2)
        for i in range(6):
            await pipe.encolar(f"frase {i}")
        await pipe.fin()

    correr(caso())
    assert activos["max"] <= 2


def test_una_sintesis_que_falla_no_rompe_el_resto():
    reproducidos = []

    async def sintetizar(texto):
        if "mala" in texto:
            raise RuntimeError("boom")
        return texto

    async def reproducir(audio, texto):
        reproducidos.append(texto)

    async def caso():
        pipe = PipelineVoz(sintetizar, reproducir)
        await pipe.encolar("buena 1")
        await pipe.encolar("mala")
        await pipe.encolar("buena 2")
        await pipe.fin()

    correr(caso())
    # la mala se salta (audio None), las buenas suenan en orden
    assert reproducidos == ["buena 1", "buena 2"]


def test_cancelar_detiene_la_reproduccion():
    reproducidos = []

    async def sintetizar(texto):
        await asyncio.sleep(0.03)
        return texto

    async def reproducir(audio, texto):
        reproducidos.append(texto)

    async def caso():
        pipe = PipelineVoz(sintetizar, reproducir)
        await pipe.encolar("uno")
        await pipe.encolar("dos")
        await pipe.cancelar()
        await pipe.fin()

    correr(caso())
    assert reproducidos == []


# ── VozStreaming (flujo completo con síntesis y reproducción simuladas) ─────────

def test_voz_streaming_habla_por_frases_en_orden(monkeypatch):
    """
    Sin audio real: se simula el motor. Verifica que al alimentar el buffer
    acumulado del stream, las frases se sintetizan y 'reproducen' en orden.
    """
    from servicios import voice

    reproducidos = []

    class MotorFalso:
        available = True
        _enabled = True
        def _sintetizar_a_archivo(self, texto):
            return f"audio::{texto}"        # 'ruta' simulada
        def _reproducir_archivo(self, ruta):
            reproducidos.append(ruta.replace("audio::", ""))

    vs = voice.VozStreaming(MotorFalso())
    assert vs.iniciar()
    # el modelo va escupiendo el buffer ACUMULADO
    for buf in ["Hola mundo. ", "Hola mundo. ¿Cómo estás? ", "Hola mundo. ¿Cómo estás? Muy bien."]:
        vs.escribir(buf)
    vs.terminar()

    assert reproducidos == ["Hola mundo.", "¿Cómo estás?", "Muy bien."]


def test_voz_streaming_no_arranca_si_esta_muda():
    from servicios import voice

    class Muda:
        available = False
        _enabled = False
    vs = voice.VozStreaming(Muda())
    assert vs.iniciar() is False


# ── Voz local: Kokoro y RVC (degradación) ───────────────────────────────────────

def test_kokoro_degrada_sin_dependencias():
    """Sin kokoro-onnx ni pesos, ni disponible() ni sintetizar() revientan."""
    from lune_core.voz import kokoro_backend as k
    # En el entorno de test no hay pesos ni el paquete: debe reportar no-disponible.
    assert k.disponible("carpeta_que_no_existe") is False
    assert k.sintetizar("hola", carpeta="carpeta_que_no_existe") is None
    assert "kokoro" in k.mensaje_instalacion().lower()
    assert k.VOZ_POR_DEFECTO in k.VOCES_ES


def test_rvc_degrada_devolviendo_el_audio_original():
    """Sin rvc-python ni modelo, convertir() devuelve la ruta de entrada intacta."""
    from lune_core.voz import rvc_backend as r
    assert r.disponible("") is False
    assert r.disponible("modelo_inexistente.pth") is False
    assert r.convertir("/tmp/entrada.wav", "modelo_inexistente.pth") == "/tmp/entrada.wav"


def test_voiceengine_pide_kokoro_pero_cae_a_edge_si_no_esta():
    """Elegir 'kokoro' sin pesos no deja a Lune muda: cae a edge/gtts."""
    from servicios import voice

    class ConfigFalsa:
        def get(self, seccion, clave, default=None):
            return {"motor_salida": "kokoro"}.get(clave, default)
    ve = voice.VoiceEngine(ConfigFalsa())
    # No hay pesos de Kokoro en el entorno de test → motor real distinto de kokoro.
    assert ve._engine in ("edge", "gtts", None)
    assert ve._engine != "kokoro"


# ── Hablar por tramos con expresión (speak_segmentos) ───────────────────────────

def _motor_falso(monkeypatch, enabled=True):
    import threading
    from servicios import voice
    v = voice.VoiceEngine.__new__(voice.VoiceEngine)
    v._enabled, v._engine, v._lock, v.al_hablar = enabled, "edge", threading.Lock(), None
    eventos = []
    monkeypatch.setattr(v, "_sintetizar_a_archivo", lambda t: (eventos.append(("sint", t)), f"audio::{t}")[1])
    monkeypatch.setattr(v, "_reproducir_archivo", lambda r: eventos.append(("play", r.replace("audio::", ""))))
    return v, eventos


def test_speak_segmentos_reproduce_en_orden_y_avisa_antes_de_cada_tramo(monkeypatch):
    v, eventos = _motor_falso(monkeypatch)
    avisos = []
    fin = []
    v._speak_segmentos_blocking([("happy", "Hola."), ("laughing", "jaja."), ("sad", "adiós.")],
                                lambda i, e: avisos.append((i, e)), lambda: fin.append(1), v._gen_voz)
    plays = [t for k, t in eventos if k == "play"]
    assert plays == ["Hola.", "jaja.", "adiós."]
    assert avisos == [(0, "happy"), (1, "laughing"), (2, "sad")]
    assert fin == [1]                                   # al acabar avisa (la cara final se queda)
    # un tramo sin texto (marcador final) también avisa, aunque no suene
    avisos.clear(); eventos.clear()
    v._speak_segmentos_blocking([("happy", "Hola."), ("laughing", "")], lambda i, e: avisos.append(e), None, v._gen_voz)
    assert avisos == ["happy", "laughing"] and [t for k, t in eventos if k == "play"] == ["Hola."]


def test_speak_segmentos_limpia_y_devuelve_false_si_no_hay_voz(monkeypatch):
    v, _ = _motor_falso(monkeypatch, enabled=False)
    assert v.speak_segmentos([("happy", "Hola")]) is False
    v2, _ = _motor_falso(monkeypatch)
    assert v2.speak_segmentos([("happy", "   "), ("sad", "***")]) is False    # nada hablable
    assert v2._limpiar("¡Hola! <b>*x*</b>") == "¡Hola! bxb"
    # el tope corta en un espacio, no a media palabra
    largo = " ".join(["palabra"] * 100)
    corto = v2._limpiar(largo, tope=50)
    assert len(corto) <= 50 and not corto.endswith("pala") and corto.endswith("palabra")


def test_cancelar_calla_los_tramos_pendientes(monkeypatch):
    v, eventos = _motor_falso(monkeypatch)
    avisos = []
    def aviso(i, e):
        avisos.append(e)
        if i == 0:
            v.cancelar()                                  # llega otro mensaje a mitad
    fin = []
    v._speak_segmentos_blocking([("happy", "uno."), ("sad", "dos."), ("angry", "tres.")], aviso, lambda: fin.append(1), v._gen_voz)
    assert avisos == ["happy"]                            # los siguientes ya no avisan
    assert [t for k, t in eventos if k == "play"] == ["uno."]
    assert fin == []                                      # ni se da por terminada
    # una lectura de una generación vieja que aún esperaba el lock no arranca
    eventos.clear()
    v._speak_segmentos_blocking([("happy", "tarde.")], lambda i, e: avisos.append(e), None, v._gen_voz - 1)
    assert [t for k, t in eventos if k == "play"] == []


def test_speak_segmentos_sigue_si_un_tramo_falla(monkeypatch):
    v, eventos = _motor_falso(monkeypatch)
    def sint(t):
        if "mal" in t:
            raise RuntimeError("tts caído")
        return f"audio::{t}"
    monkeypatch.setattr(v, "_sintetizar_a_archivo", sint)
    avisos = []
    v._speak_segmentos_blocking([("happy", "bien."), ("angry", "mal."), ("sad", "fin.")], lambda i, e: avisos.append(e), None, v._gen_voz)
    assert [t for k, t in eventos if k == "play"] == ["bien.", "fin."]
    assert avisos == ["happy", "angry", "sad"]        # la cara cambia aunque no suene
