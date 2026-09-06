"""
lune_core/voz — Servicio de voz: convertir el stream del modelo en habla.

    segmentador   corta el texto en frases aptas para TTS mientras llega
    pipeline      sintetiza varias frases en paralelo y las reproduce EN ORDEN

Portado de packages/pipelines-audio de AIRI (tts-chunker.ts, speech-pipeline.ts),
como lógica pura sin dependencia de audio: los motores TTS/STT concretos
(edge-tts, Kokoro, faster-whisper) se conectan por encima.
"""
from .segmentador import segmentar, SegmentadorStream  # noqa: F401
from .pipeline import PipelineVoz  # noqa: F401
