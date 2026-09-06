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
    import voice
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
    import voice
    class Muda:
        available = False
        _enabled = False
    vs = voice.VozStreaming(Muda())
    assert vs.iniciar() is False
