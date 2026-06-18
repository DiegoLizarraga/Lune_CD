"""
voice.py — Motor de voz de Lune (edge-tts con fallback a gTTS).
Reproduce las respuestas en voz alta de forma asíncrona.
"""
import io
import os
import re
import threading


class VoiceEngine:
    def __init__(self):
        self._enabled = False; self._lock = threading.Lock(); self._engine = None; self._init_engine()

    def _init_engine(self):
        try: import edge_tts; import pygame; pygame.mixer.init(); self._engine = "edge"; return
        except ImportError: pass
        try: from gtts import gTTS; import pygame; pygame.mixer.init(); self._engine = "gtts"; return
        except ImportError: pass
        self._engine = None

    def speak(self, text: str):
        if not self._enabled or not self._engine: return
        clean = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', text, flags=re.UNICODE).strip()[:400]
        if clean: threading.Thread(target=self._speak_blocking, args=(clean,), daemon=True).start()

    def _speak_blocking(self, text: str):
        with self._lock:
            if self._engine == "edge": self._speak_edge(text)
            elif self._engine == "gtts": self._speak_gtts(text)

    def _speak_edge(self, text: str):
        try:
            import asyncio, edge_tts, pygame, tempfile
            async def _synth():
                c = edge_tts.Communicate(text, voice="es-MX-DaliaNeural")
                t = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                t.close(); await c.save(t.name); return t.name
            path = asyncio.run(_synth())
            pygame.mixer.music.load(path); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): threading.Event().wait(0.1)
            os.unlink(path)
        except Exception: pass

    def _speak_gtts(self, text: str):
        try:
            from gtts import gTTS; import pygame
            tts = gTTS(text, lang="es"); fp = io.BytesIO()
            tts.write_to_fp(fp); fp.seek(0)
            pygame.mixer.music.load(fp); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): threading.Event().wait(0.1)
        except Exception: pass

    def toggle(self) -> bool: self._enabled = not self._enabled; return self._enabled
    @property
    def available(self): return self._engine is not None
    @property
    def engine_name(self): return self._engine or "sin voz"
