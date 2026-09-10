"""
voice.py — Motor de voz de Lune (edge-tts con fallback a gTTS).
Reproduce las respuestas en voz alta de forma asíncrona.

SALIDA DE AUDIO (v10)
---------------------
pygame/SDL manda el sonido al dispositivo que Windows tenga por defecto, que
no siempre es el que quieres (con Steam instalado aparece un «Speakers (Steam
Streaming Microphone)» virtual, y el headset Bluetooth no se vuelve el default
solo por estar conectado). Por eso el usuario puede elegir la salida en
Configuración → Audio; se guarda por NOMBRE en config (`voz.dispositivo_salida`,
vacío = la del sistema) y se aplica al abrir el mixer con `devicename=`.
"""
import io
import os
import re
import threading


def listar_salidas():
    """
    Nombres de las salidas de audio que ve SDL (pygame). Lista vacía si pygame
    no está o no hay tarjeta de sonido. SDL solo enumera con el subsistema de
    audio iniciado, así que si el mixer está cerrado se abre un momento.
    """
    try:
        import pygame
        from pygame._sdl2 import audio as sdl_audio
    except Exception:
        return []
    abierto_aqui = False
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(); abierto_aqui = True
        nombres = [str(n) for n in sdl_audio.get_audio_device_names(False)]
    except Exception:
        nombres = []
    finally:
        if abierto_aqui:
            try: pygame.mixer.quit()
            except Exception: pass
    return nombres


class VoiceEngine:
    def __init__(self, config=None):
        self.config = config
        self._enabled = False; self._lock = threading.Lock(); self._engine = None
        self._salida = ""          # nombre de la salida con la que se abrió el mixer ("" = sistema)
        self._init_engine()

    def _cfg(self, clave, default):
        """Lee una clave de la sección 'voz' de config, con respaldo."""
        try:
            if self.config is not None:
                return self.config.get("voz", clave, default)
        except Exception:
            pass
        return default

    # ── Mixer y dispositivo de salida ───────────────────────────────────────────
    def _abrir_mixer(self, nombre=None):
        """
        Abre pygame.mixer en la salida pedida (o la de config). Si ese nombre ya
        no existe (headset apagado), cae a la del sistema sin quejarse: mejor
        oír a Lune por los altavoces que no oírla.
        """
        import pygame
        nombre = (self._cfg("dispositivo_salida", "") if nombre is None else nombre) or ""
        nombre = str(nombre).strip()
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        if nombre:
            try:
                pygame.mixer.init(devicename=nombre); self._salida = nombre; return True
            except Exception:
                pass
        pygame.mixer.init(); self._salida = ""
        return not nombre

    @property
    def salida_actual(self):
        return self._salida

    def aplicar_salida(self, nombre):
        """Cambia la salida en caliente. Devuelve True si se abrió la pedida."""
        if not self._engine:
            return False
        with self._lock:
            try:
                return self._abrir_mixer(nombre or "")
            except Exception:
                return False

    def probar_salida(self):
        """Suena un tono corto por la salida actual (para saber si es la buena)."""
        if not self._engine:
            return False
        def _beep():
            with self._lock:
                try:
                    import math, struct, pygame
                    sr = 22050
                    if not pygame.mixer.get_init():
                        self._abrir_mixer()
                    frec, ch = pygame.mixer.get_init()[0] or sr, pygame.mixer.get_init()[2] or 2
                    n = int(frec * 0.35)
                    muestras = bytearray()
                    for i in range(n):
                        env = min(1.0, i / (frec * 0.02), (n - i) / (frec * 0.06))
                        v = int(9000 * env * math.sin(2 * math.pi * 660 * i / frec))
                        muestras += struct.pack("<h", v) * ch
                    s = pygame.mixer.Sound(buffer=bytes(muestras)); s.play()
                    threading.Event().wait(0.45)
                except Exception:
                    pass
        threading.Thread(target=_beep, daemon=True).start()
        return True

    def _init_engine(self):
        pref = self._cfg("motor_salida", "auto")
        # Voz local Kokoro: solo si se pide explícitamente y está disponible.
        if pref == "kokoro":
            try:
                from lune_core.voz import kokoro_backend
                if kokoro_backend.disponible(self._cfg("kokoro_carpeta", "modelos_voz")):
                    self._abrir_mixer(); self._engine = "kokoro"; return
            except Exception:
                pass
            # se pidió kokoro pero no está: se cae a edge (degradación silenciosa)
        if pref in ("auto", "edge", "kokoro"):
            try: import edge_tts; self._abrir_mixer(); self._engine = "edge"; return
            except ImportError: pass
            except Exception: pass          # sin tarjeta de sonido: mudo, no muerto
        try: from gtts import gTTS; self._abrir_mixer(); self._engine = "gtts"; return
        except ImportError: pass
        except Exception: pass
        self._engine = None

    @staticmethod
    def _limpiar(text: str, tope: int = 400) -> str:
        limpio = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', text or '', flags=re.UNICODE).strip()
        if len(limpio) > tope:                      # cortar en un espacio, no a media palabra
            corte = limpio.rfind(" ", 0, tope)
            limpio = limpio[:corte if corte > tope // 2 else tope].rstrip()
        return limpio

    def speak(self, text: str):
        if not self._enabled or not self._engine: return
        clean = self._limpiar(text)
        if clean: threading.Thread(target=self._speak_blocking, args=(clean,), daemon=True).start()

    # ── Varios tramos seguidos, cada uno con su expresión ─────────────────────
    def speak_segmentos(self, segmentos, al_segmento=None, al_terminar=None, tope: int = 600) -> bool:
        """
        Habla `[(etiqueta, texto), …]` en orden. Los tramos se sintetizan en
        paralelo y se reproducen uno tras otro; justo antes de que suene cada uno
        se llama a `al_segmento(i, etiqueta)` (también para un tramo sin texto,
        p. ej. un marcador final) y al acabar a `al_terminar()`. Los avisos llegan
        desde el hilo de audio: quien los use debe marshalear al hilo de Qt.
        `cancelar()` corta la lectura y los tramos pendientes. Devuelve False si
        no hay voz o nada que decir (para que quien llama exprese de otra forma).
        """
        if not self._enabled or not self._engine:
            return False
        limpios = [(et, self._limpiar(t, tope)) for et, t in (segmentos or [])]
        if not any(t for _, t in limpios):
            return False
        gen = self._gen_voz
        threading.Thread(target=self._speak_segmentos_blocking,
                         args=(limpios, al_segmento, al_terminar, gen), daemon=True).start()
        return True

    def cancelar(self):
        """Corta lo que esté sonando y los tramos pendientes (mensaje nuevo, Detener)."""
        self._gen_voz += 1
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass

    def _speak_segmentos_blocking(self, segmentos, al_segmento, al_terminar, gen):
        from concurrent.futures import ThreadPoolExecutor
        with self._lock:
            if gen != self._gen_voz:                # lo cancelaron mientras esperaba su turno
                return
            with ThreadPoolExecutor(max_workers=3) as pool:
                futuros = [pool.submit(self._sintetizar_a_archivo, texto) if texto else None
                           for _, texto in segmentos]
                for i, ((etiqueta, _texto), fut) in enumerate(zip(segmentos, futuros)):
                    ruta = None
                    if fut is not None:
                        try:
                            ruta = fut.result()
                        except Exception:
                            ruta = None
                    if gen != self._gen_voz:        # cancelado: ni suena ni avisa, solo limpia
                        self._borrar(ruta)
                        continue
                    if al_segmento is not None:
                        try:
                            al_segmento(i, etiqueta)
                        except Exception:
                            pass
                    if ruta:
                        self._reproducir_archivo(ruta)
            if al_terminar is not None and gen == self._gen_voz:
                try:
                    al_terminar()
                except Exception:
                    pass

    def _speak_blocking(self, text: str):
        with self._lock:
            if self._engine == "edge": self._speak_edge(text)
            elif self._engine == "gtts": self._speak_gtts(text)
            elif self._engine == "kokoro":
                ruta = self._sintetizar_a_archivo(text)
                if ruta: self._reproducir_archivo(ruta)

    # ── Aviso «está sonando» (la mascota 3D mueve la boca mientras Lune habla) ──
    # `al_hablar(True/False)` se llama desde el hilo de audio: quien lo use debe
    # marshalear al hilo de Qt (el puente lo hace con una señal).
    al_hablar = None
    _gen_voz = 0          # sube con cancelar(): las lecturas de una generación vieja se callan

    def _sonando(self, activo: bool):
        cb = self.al_hablar
        if cb is None:
            return
        try:
            cb(bool(activo))
        except Exception:
            pass

    def _speak_edge(self, text: str):
        try:
            import asyncio, edge_tts, pygame, tempfile
            async def _synth():
                c = edge_tts.Communicate(text, voice="es-MX-DaliaNeural")
                t = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                t.close(); await c.save(t.name); return t.name
            path = asyncio.run(_synth())
            pygame.mixer.music.load(path); pygame.mixer.music.play()
            self._sonando(True)
            try:
                while pygame.mixer.music.get_busy(): threading.Event().wait(0.1)
            finally:
                self._sonando(False)
                self._soltar_audio()
            self._borrar(path)
        except Exception: pass

    def _speak_gtts(self, text: str):
        try:
            from gtts import gTTS; import pygame
            tts = gTTS(text, lang="es"); fp = io.BytesIO()
            tts.write_to_fp(fp); fp.seek(0)
            pygame.mixer.music.load(fp); pygame.mixer.music.play()
            self._sonando(True)
            try:
                while pygame.mixer.music.get_busy(): threading.Event().wait(0.1)
            finally:
                self._sonando(False)
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
        import tempfile
        t = None
        try:
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
            if t is not None:
                self._borrar(t.name)         # sin red: no dejar un .mp3 vacío por ahí
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
            self._sonando(True)
            try:
                while pygame.mixer.music.get_busy():
                    threading.Event().wait(0.05)
            finally:
                self._sonando(False)
                self._soltar_audio()
        except Exception:
            pass
        self._borrar(ruta)

    @staticmethod
    def _soltar_audio():
        # SDL mantiene el archivo abierto hasta unload(): sin esto, en Windows el
        # borrado falla (WinError 32) y los temporales se acumulan en %TEMP%.
        try:
            import pygame
            pygame.mixer.music.unload()
        except Exception:
            pass

    @staticmethod
    def _borrar(ruta):
        try:
            if ruta:
                os.unlink(ruta)
        except OSError:
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
