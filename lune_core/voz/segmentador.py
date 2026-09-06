"""
lune_core/voz/segmentador.py — Cortar el texto en frases para TTS en streaming.

Portado de packages/pipelines-audio/src/processors/tts-chunker.ts de AIRI. El
objetivo: sintetizar y empezar a hablar SIN esperar a que el modelo termine el
párrafo. Se emite un segmento cuando:

  · se cierra una frase con puntuación fuerte (. ! ? … 。！？) — corte "duro";
  · o hay puntuación blanda (, ; : —) y ya se acumularon >= MIN_PALABRAS;
  · o se superan MAX_PALABRAS aunque no haya puntuación (evita segmentos enormes).

Las dos PRIMERAS frases se emiten antes (BOOST_PALABRAS menor) para bajar el
tiempo hasta el primer audio. Los números con punto (3.14) y los "..." no cuentan
como fin de frase.
"""
from __future__ import annotations

import re
from typing import List, Optional

DURA = ".!?…。！？"
BLANDA = ",;:—–"

MIN_PALABRAS = 4
MAX_PALABRAS = 30
BOOST_PALABRAS = 2       # para las 2 primeras frases del turno
BOOST_FRASES = 2

# "3.14", "1.000", "e.g." → el punto no cierra frase
_NO_CORTE = re.compile(r"\d[.,]\d|\b[a-zA-Z]\.[a-zA-Z]\.")
# "..." o "…": no cortar en cada punto
_PUNTOS_SUSPENSIVOS = re.compile(r"\.{2,}")


def _palabras(s: str) -> int:
    return len(s.split())


class SegmentadorStream:
    """Alimenta con `escribir(chunk)`; devuelve los segmentos ya listos."""

    def __init__(self, min_palabras: int = MIN_PALABRAS, max_palabras: int = MAX_PALABRAS):
        self.min_palabras = min_palabras
        self.max_palabras = max_palabras
        self._buffer = ""
        self._emitidos = 0

    def _umbral_min(self) -> int:
        # Las primeras frases salen antes para reducir la latencia inicial.
        return BOOST_PALABRAS if self._emitidos < BOOST_FRASES else self.min_palabras

    def escribir(self, chunk: str) -> List[str]:
        self._buffer += chunk
        segmentos: List[str] = []
        while True:
            corte = self._buscar_corte()
            if corte is None:
                break
            seg = self._buffer[:corte].strip()
            self._buffer = self._buffer[corte:]
            if seg:
                segmentos.append(seg)
                self._emitidos += 1
        return segmentos

    def vaciar(self) -> List[str]:
        """Al terminar el stream: emite lo que quede (aunque no cierre frase)."""
        resto = self._buffer.strip()
        self._buffer = ""
        if resto:
            self._emitidos += 1
            return [resto]
        return []

    def _buscar_corte(self) -> Optional[int]:
        buf = self._buffer
        # 1) corte duro en la primera puntuación fuerte "real"
        for m in re.finditer(f"[{re.escape(DURA)}]+", buf):
            fin = m.end()
            # ignorar 3.14 / e.g. / "..." a mitad
            ventana = buf[max(0, m.start() - 1):fin + 1]
            if _NO_CORTE.search(ventana):
                continue
            # "..." cuenta como un solo corte al final del grupo
            if _PUNTOS_SUSPENSIVOS.match(buf[m.start():]) and fin < len(buf) and buf[fin] in DURA:
                continue
            # incluir comillas/paréntesis de cierre pegados
            while fin < len(buf) and buf[fin] in '"\')]}»':
                fin += 1
            if _palabras(buf[:fin]) >= 1:
                return fin
        # 2) corte blando si ya hay suficientes palabras
        if _palabras(buf) >= self._umbral_min():
            for m in re.finditer(f"[{re.escape(BLANDA)}]", buf):
                if _palabras(buf[:m.end()]) >= self._umbral_min():
                    return m.end()
        # 3) corte por longitud
        if _palabras(buf) >= self.max_palabras:
            # corta en el último espacio antes del límite
            palabras = buf.split()
            trozo = " ".join(palabras[:self.max_palabras])
            return len(trozo)
        return None


def segmentar(texto: str, **kw) -> List[str]:
    """Segmenta un texto completo (no streaming)."""
    s = SegmentadorStream(**kw)
    return s.escribir(texto) + s.vaciar()
