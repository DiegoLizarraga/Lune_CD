"""
lune_core/voz/pipeline.py — Sintetizar en paralelo, reproducir en orden.

Portado de packages/pipelines-audio/src/speech-pipeline.ts + playback-manager.ts
de AIRI. El modelo escupe frases; se sintetizan hasta N a la vez (rápido) pero se
reproducen SIEMPRE en el orden en que llegaron (coherente). Soporta cancelación
(el usuario interrumpe) y una función de síntesis inyectable, para poder probar
el pipeline sin audio real.

    async def sintetizar(texto) -> algo reproducible (bytes, ruta, lo que sea)
    async def reproducir(audio, texto) -> None

    pipe = PipelineVoz(sintetizar, reproducir, concurrencia=4)
    for frase in segmentos:
        await pipe.encolar(frase)
    await pipe.fin()
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

Sintetizar = Callable[[str], Awaitable[object]]
Reproducir = Callable[[object, str], Awaitable[None]]


class PipelineVoz:
    def __init__(self, sintetizar: Sintetizar, reproducir: Reproducir,
                 *, concurrencia: int = 4):
        self._sintetizar = sintetizar
        self._reproducir = reproducir
        self._sem = asyncio.Semaphore(max(1, concurrencia))
        self._sig_seq = 0                 # nº que se asigna al encolar
        self._sig_reproducir = 0          # nº que toca reproducir ahora
        self._listos: dict = {}           # seq -> (audio|None, texto)
        self._cond = asyncio.Condition()
        self._play_lock = asyncio.Lock()  # solo un audio suena a la vez, en orden
        self._tareas: list = []
        self._cancelado = False

    async def encolar(self, texto: str):
        """Registra una frase; su síntesis arranca ya (limitada por la concurrencia)."""
        if self._cancelado or not texto.strip():
            return
        seq = self._sig_seq
        self._sig_seq += 1
        self._tareas.append(asyncio.create_task(self._sintetizar_una(seq, texto)))

    async def _sintetizar_una(self, seq: int, texto: str):
        audio = None
        if not self._cancelado:
            async with self._sem:
                if not self._cancelado:
                    try:
                        audio = await self._sintetizar(texto)
                    except Exception:
                        audio = None       # una frase que falla no rompe el resto
        async with self._cond:
            self._listos[seq] = (audio, texto)
            self._cond.notify_all()
        await self._drenar()

    async def _drenar(self):
        """
        Reproduce en orden estricto lo que ya esté listo. El lock de reproducción
        garantiza que solo un audio suene a la vez: sin él, dos drenadores
        concurrentes reproducían frases en paralelo y se perdía el orden.
        """
        async with self._play_lock:
            while True:
                async with self._cond:
                    if self._sig_reproducir not in self._listos:
                        return
                    audio, texto = self._listos.pop(self._sig_reproducir)
                    self._sig_reproducir += 1
                if audio is not None and not self._cancelado:
                    try:
                        await self._reproducir(audio, texto)
                    except Exception:
                        pass

    async def fin(self):
        """Espera a que todo se sintetice y se reproduzca, en orden."""
        if self._tareas:
            await asyncio.gather(*self._tareas, return_exceptions=True)
        await self._drenar()

    async def cancelar(self):
        """Interrumpe: no se sintetiza ni reproduce nada más."""
        self._cancelado = True
        for t in self._tareas:
            t.cancel()
        async with self._cond:
            self._listos.clear()
            self._cond.notify_all()
