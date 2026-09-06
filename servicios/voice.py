"""
voice.py — Motor de voz de Lune (edge-tts con fallback a gTTS).
Reproduce las respuestas en voz alta de forma asíncrona.
"""
import io
import os
import re
import threading


class VoiceEngine:
    def __init__(self, config=None):
        self.config = config
        self._enabled = False; self._lock = threading.Lock(); self._engine = None; self._init_engine()

    def _cfg(self, clave, default):
        """Lee una clave de la sección 'voz' de config, con respaldo."""
        try:
            if self.config is not None:
                return self.config.get("voz", clave, default)
        except Exception:
            pass
        return default

    def _init_engine(self):
        pref = self._cfg("motor_salida", "auto")
        # Voz local Kokoro: solo si se pide explícitamente y está disponible.
        if pref == "kokoro":
            try:
                from lune_core.voz import kokoro_backend
                if kokoro_backend.disponible(self._cfg("kokoro_carpeta", "modelos_voz")):
                    import pygame; pygame.mixer.init(); self._engine = "kokoro"; return
            except Exception:
                pass
            # se pidió kokoro pero no está: se cae a edge (degradación silenciosa)
        if pref in ("auto", "edge", "kokoro"):
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
            elif self._engine == "kokoro":
                ruta = self._sintetizar_a_archivo(text)
                if ruta: self._reproducir_archivo(ruta)

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
    def engine_name(self):
        return {"edge": "edge-tts", "gtts": "gTTS",
                "kokoro": "Kokoro (local)"}.get(self._engine, "sin voz")

    # ── Síntesis de una frase a archivo (para el pipeline en streaming) ─────────
    def _sintetizar_a_archivo(self, texto: str):
        """Devuelve la ruta de un audio con `texto`, o None. Sin reproducir."""
        clean = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', texto, flags=re.UNICODE).strip()
        if not clean or not self._engine:
            return None
        # Kokoro local → WAV, con posible conversión de voz (RVC) encima.
        if self._engine == "kokoro":
            try:
                from lune_core.voz import kokoro_backend
                ruta = kokoro_backend.sintetizar(
                    clean,
                    voz=self._cfg("kokoro_voz", kokoro_backend.VOZ_POR_DEFECTO),
                    velocidad=self._cfg("kokoro_velocidad", 1.0),
                    carpeta=self._cfg("kokoro_carpeta", "modelos_voz"),
                    idioma=self._cfg("idioma", "es"),
                )
                return self._quizas_rvc(ruta) if ruta else None
            except Exception:
                return None
        try:
            import tempfile
            t = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False); t.close()
            if self._engine == "edge":
                import asyncio, edge_tts
                async def _s():
                    await edge_tts.Communicate(clean, voice="es-MX-DaliaNeural").save(t.name)
                asyncio.run(_s())
            else:
                from gtts import gTTS
                gTTS(clean, lang="es").save(t.name)
            return t.name
        except Exception:
            return None

    def _quizas_rvc(self, ruta_wav):
        """Si RVC está activado y disponible, convierte el audio; si no, lo deja igual."""
        if not ruta_wav or not self._cfg("rvc_activo", False):
            return ruta_wav
        modelo = self._cfg("rvc_modelo", "")
        try:
            from lune_core.voz import rvc_backend
            if not rvc_backend.disponible(modelo):
                return ruta_wav
            salida = rvc_backend.convertir(
                ruta_wav, modelo,
                transpose=self._cfg("rvc_transpose", 0),
                index_rate=self._cfg("rvc_index_rate", 0.5),
            )
            if salida != ruta_wav:                 # limpiar el WAV intermedio de Kokoro
                try: os.unlink(ruta_wav)
                except OSError: pass
            return salida
        except Exception:
            return ruta_wav

    def _reproducir_archivo(self, ruta: str):
        try:
            import pygame
            pygame.mixer.music.load(ruta); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                threading.Event().wait(0.05)
            os.unlink(ruta)
        except Exception:
            pass


class VozStreaming:
    """
    Habla por frases MIENTRAS el modelo escribe: segmenta el stream, sintetiza
    varias frases en paralelo y las reproduce en orden. Corre en su propio hilo
    con un bucle asyncio para no tocar el hilo de Qt.

        vs = VozStreaming(voice_engine)
        vs.iniciar()
        vs.escribir(chunk)   # varias veces, con el texto acumulado que llega
        vs.terminar()        # emite lo que quede y cierra
        vs.cancelar()        # el usuario interrumpió
    """
    def __init__(self, voz: "VoiceEngine", concurrencia: int = 3):
        self.voz = voz
        self.concurrencia = concurrencia
        self._loop = None
        self._hilo = None
        self._pipe = None
        self._seg = None
        self._ultimo = ""      # texto ya procesado (para deltas del buffer acumulado)

    def iniciar(self) -> bool:
        if not self.voz.available or not self.voz._enabled:
            return False
        import asyncio
        from lune_core.voz import SegmentadorStream, PipelineVoz

        self._seg = SegmentadorStream()
        self._ultimo = ""

        def _correr():
            self._loop = asyncio.new_event_loop(); asyncio.set_event_loop(self._loop)

            async def _sint(texto):
                return await self._loop.run_in_executor(None, self.voz._sintetizar_a_archivo, texto)
            async def _rep(ruta, _texto):
                await self._loop.run_in_executor(None, self.voz._reproducir_archivo, ruta)

            self._pipe = PipelineVoz(_sint, _rep, concurrencia=self.concurrencia)
            self._loop.run_forever()

        self._hilo = threading.Thread(target=_correr, name="voz-streaming", daemon=True)
        self._hilo.start()
        # esperar a que el pipe exista
        for _ in range(50):
            if self._pipe is not None:
                return True
            threading.Event().wait(0.02)
        return self._pipe is not None

    def escribir(self, buffer_acumulado: str):
        """Recibe el buffer ACUMULADO del stream; procesa solo lo nuevo."""
        if self._pipe is None:
            return
        delta = buffer_acumulado[len(self._ultimo):] if buffer_acumulado.startswith(self._ultimo) else buffer_acumulado
        self._ultimo = buffer_acumulado
        for frase in self._seg.escribir(delta):
            self._encolar(frase)

    def terminar(self):
        if self._pipe is None:
            return
        for frase in self._seg.vaciar():
            self._encolar(frase)
        self._detener()

    def cancelar(self):
        if self._pipe is None:
            return
        import asyncio
        try:
            asyncio.run_coroutine_threadsafe(self._pipe.cancelar(), self._loop).result(timeout=2)
        except Exception:
            pass
        self._parar_loop()

    def _encolar(self, frase: str):
        import asyncio
        try:
            asyncio.run_coroutine_threadsafe(self._pipe.encolar(frase), self._loop)
        except Exception:
            pass

    def _detener(self):
        import asyncio
        try:
            asyncio.run_coroutine_threadsafe(self._pipe.fin(), self._loop).result(timeout=60)
        except Exception:
            pass
        self._parar_loop()

    def _parar_loop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
