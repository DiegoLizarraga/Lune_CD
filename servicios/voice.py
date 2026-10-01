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

VOZ ELEGIBLE (v10.4)
--------------------
Qué voz suena lo decide servicios/voces.resolver_voz (personaje > config > por
defecto), releído cada 2 s o al llamar a `invalidar_params()`. El motor se
elige por frase: el pedido si está disponible; si no, edge; si no, gTTS.

    probar_voz(params, texto)   corta lo que suene y prueba una voz, aunque la
                                voz esté apagada (botón «Probar»)
    reiniciar_motor()           vuelve a mirar qué motores hay (cambio de motor)
    silenciar(on)               modo juego: calla y no habla hasta silenciar(False)
    on_error(msg)               aviso legible de lo que antes se tragaba (voz
                                inexistente → NoAudioReceived, sin red…). Llega
                                desde el hilo de audio: marshalear a Qt
    al_hablar(bool)             ya existía: la boca de la asistente

MIXER PEREZOSO (11.3)
---------------------
El constructor ya no importa pygame ni abre la tarjeta (eran ~400 ms en el hilo
de Qt antes de enseñar la ventana, y la salida quedaba abierta toda la sesión:
Lune siempre en el mezclador de volumen de Windows y los auriculares Bluetooth
sin entrar nunca en reposo). Se abre justo antes de sonar (`_asegurar_mixer`) y
un vigilante lo cierra tras `MIXER_CIERRE_S` sin sonar. `available` solo dice
si hay motor y pygame instalado; si no hay tarjeta, se avisa al primer uso.
"""
import json
import os
import re
import sys
import threading
import time

# Sin el anuncio «Hello from the pygame community» en patata ni en la consola.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from servicios import voces  # noqa: E402  (ligero: no importa edge_tts)

CACHE_PARAMS_S = 2.0            # cada cuánto se relee la voz del personaje activo
SILENCIO_AVISOS_S = 20.0        # el mismo aviso no se repite antes de esto
MIXER_CIERRE_S = 15.0           # sin sonar este rato, se suelta la tarjeta (pygame.mixer.quit)
VIGILANTE_PASO_S = 1.0          # cada cuánto mira el vigilante si toca cerrarla


def _pygame_si_cargado():
    """El módulo pygame si alguien ya lo importó (None si no): para no pagar su import
    (~350 ms) solo por cortar o mirar un mixer que nunca se abrió."""
    return sys.modules.get("pygame")


def _pygame_instalado() -> bool:
    if _pygame_si_cargado() is not None:
        return True
    try:
        import importlib.util
        return importlib.util.find_spec("pygame") is not None
    except (ImportError, ValueError):
        return False


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


def _es_sin_audio(exc) -> bool:
    """edge-tts lanza NoAudioReceived si la voz no existe (o el texto no se puede leer)."""
    return any(c.__name__ == "NoAudioReceived" for c in type(exc).__mro__)


def _es_de_red(exc) -> bool:
    nombres = {c.__name__ for c in type(exc).__mro__}
    return bool(isinstance(exc, (OSError, TimeoutError, ConnectionError))
                or nombres & {"ClientError", "WebSocketError", "gTTSError", "ServerTimeoutError"})


class VoiceEngine:
    # `al_hablar(True/False)` y `on_error(msg)` se llaman desde el hilo de audio:
    # quien los use debe marshalear al hilo de Qt (el puente lo hace con señales).
    al_hablar = None
    on_error = None
    _gen_voz = 0          # sube con cancelar(): las lecturas de una generación vieja se callan
    # Valores de clase para lo nuevo: los tests crean motores con __new__ y solo
    # rellenan lo que usan, así que nada de esto puede depender de __init__.
    config = None
    _engine = None
    _enabled = False
    _silenciada = False
    _disponibles = frozenset()
    _kokoro_ok = None
    _params_cache = None
    _avisos = None
    ultimo_error = ""
    _salida = ""
    _salida_pedida = None
    _lock_mixer = None
    _hilo_vig = None
    _ultimo_sonido = 0.0
    cierre_mixer_s = MIXER_CIERRE_S

    def __init__(self, config=None, on_error=None):
        self.config = config
        self._enabled = False; self._lock = threading.Lock(); self._engine = None
        self._salida = ""          # nombre de la salida con la que se abrió el mixer ("" = sistema)
        self._salida_pedida = None # la elegida en caliente (aplicar_salida); None = la de config
        self._lock_mixer = threading.RLock()   # abrir/cerrar/cargar el mixer (y el vigilante)
        self._hilo_vig = None
        self._ultimo_sonido = 0.0  # time.monotonic() de la última vez que sonó algo
        self._silenciada = False   # modo juego
        self._disponibles = set()  # motores importables: edge, gtts (kokoro se mira aparte)
        self._kokoro_ok = None     # None = sin comprobar
        self._params_cache = None  # (instante, ParamsVoz)
        self._avisos = {}          # mensaje → último instante (para no repetir)
        self.ultimo_error = ""
        if on_error is not None:
            self.on_error = on_error
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

    def _candado_mixer(self):
        if self._lock_mixer is None:          # motores de tests creados con __new__
            self._lock_mixer = threading.RLock()
        return self._lock_mixer

    def mixer_abierto(self) -> bool:
        """¿Tiene la tarjeta abierta ahora mismo? Sin importar pygame si nadie lo hizo."""
        pg = _pygame_si_cargado()
        try:
            return bool(pg is not None and pg.mixer.get_init())
        except Exception:
            return False

    def _asegurar_mixer(self):
        """
        Abre el mixer si está cerrado, en la salida elegida en caliente o la de config
        (cae a la del sistema si ya no existe), y arranca el vigilante que lo cierra
        tras MIXER_CIERRE_S sin sonar. Devuelve True si quedó abierto; si no hay
        tarjeta, avisa (una vez cada rato) y devuelve False.
        """
        with self._candado_mixer():
            self._ultimo_sonido = time.monotonic()
            if self.mixer_abierto():
                return True
            try:
                self._abrir_mixer(self._salida_pedida)
            except Exception as e:
                self._avisar(f"No pude abrir la salida de audio: {e}")
                return False
            self._arrancar_vigilante()
            return True

    def cerrar_mixer(self) -> bool:
        """Suelta la tarjeta si no está sonando nada. Devuelve True si la cerró."""
        with self._candado_mixer():
            pg = _pygame_si_cargado()
            if pg is None or not self.mixer_abierto():
                return False
            try:
                if pg.mixer.music.get_busy() or pg.mixer.get_busy():
                    return False
                pg.mixer.quit()
                return True
            except Exception:
                return False

    def revisar_cierre(self, ahora=None) -> bool:
        """Un paso del vigilante: cierra el mixer si lleva MIXER_CIERRE_S sin sonar.
        Devuelve True cuando ya no hay nada que vigilar (mixer cerrado)."""
        with self._candado_mixer():
            if not self.mixer_abierto():
                return True
            ahora = time.monotonic() if ahora is None else ahora
            pg = _pygame_si_cargado()
            try:
                sonando = bool(pg.mixer.music.get_busy() or pg.mixer.get_busy())
            except Exception:
                sonando = False
            if sonando:
                self._ultimo_sonido = ahora
                return False
            if ahora - self._ultimo_sonido < self.cierre_mixer_s:
                return False
            return self.cerrar_mixer()

    def _arrancar_vigilante(self):
        """Con el candado del mixer: un hilo que lo cierra tras el silencio y se acaba."""
        if self._hilo_vig is not None and self._hilo_vig.is_alive():
            return

        def vigilar():
            while True:
                threading.Event().wait(VIGILANTE_PASO_S)
                if self.revisar_cierre():
                    return

        self._hilo_vig = threading.Thread(target=vigilar, name="LuneVozVigilante", daemon=True)
        self._hilo_vig.start()

    def aplicar_salida(self, nombre):
        """Cambia la salida en caliente. Devuelve True si se abrió la pedida. Con el
        mixer cerrado solo guarda el nombre: se usa al abrirlo para la próxima frase."""
        if not self._engine:
            return False
        nombre = str(nombre or "").strip()
        with self._lock:
            with self._candado_mixer():
                self._salida_pedida = nombre
                if not self.mixer_abierto():
                    self._salida = nombre
                    return True
                try:
                    return self._abrir_mixer(nombre)
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
                    with self._candado_mixer():
                        estaba = self.mixer_abierto()
                        if not self._asegurar_mixer():
                            return
                        pedida = self._salida_pedida
                        if not estaba and pedida and self._salida != pedida:
                            # Con el mixer cerrado, aplicar_salida no pudo comprobarla.
                            self._avisar(f"No encontré la salida «{pedida}»; suena por la del sistema.")
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

    # ── Motores ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _detectar_motores():
        """edge/gTTS instalados (sin importarlos: edge_tts tarda ~1 s en cargar)."""
        import importlib.util
        disp = set()
        for motor, modulo in (("edge", "edge_tts"), ("gtts", "gtts")):
            if sys.modules.get(modulo) is not None:     # ya importado (o sustituido en tests)
                disp.add(motor)
                continue
            try:
                if importlib.util.find_spec(modulo) is not None:
                    disp.add(motor)
            except (ImportError, ValueError):
                pass
        return disp

    def _kokoro_disponible(self):
        if self._kokoro_ok is None:
            try:
                from lune_core.voz import kokoro_backend
                self._kokoro_ok = bool(kokoro_backend.disponible(self._cfg("kokoro_carpeta", "modelos_voz")))
            except Exception:
                self._kokoro_ok = False
        return self._kokoro_ok

    def _motor_para(self, params):
        """Motor que va a sonar para `params`: el pedido si está; si no, edge; si no, gTTS."""
        if params.motor == "kokoro" and self._kokoro_disponible():
            return "kokoro"
        if params.motor == "gtts" and "gtts" in self._disponibles:
            return "gtts"
        if "edge" in self._disponibles:
            return "edge"
        if "gtts" in self._disponibles:
            return "gtts"
        return None

    def _init_engine(self):
        # Voz local Kokoro: solo si se pide explícitamente (personaje o config) y
        # está disponible; si no, se cae a edge y luego a gTTS (degradación silenciosa).
        self._disponibles = self._detectar_motores()
        self._kokoro_ok = None
        params = self._params(refrescar=True)
        motor = self._motor_para(params)
        # Sin pygame no hay con qué sonar. La tarjeta NO se abre aquí (mixer perezoso):
        # si no hay, se avisa al primer uso (_asegurar_mixer) y Lune sigue muda, no muerta.
        if motor is None or not _pygame_instalado():
            self._engine = None
            return
        self._engine = motor

    def reiniciar_motor(self):
        """Vuelve a mirar qué motores hay y cuál toca (tras cambiar el motor o
        instalar Kokoro). Corta lo que suene. Devuelve el nombre del motor."""
        self.cancelar()
        self._params_cache = None
        self._kokoro_ok = None
        if self._engine is None:
            self._init_engine()          # quizá ahora sí hay librería o tarjeta
        else:
            self._disponibles = self._detectar_motores()
            self._engine = self._motor_para(self._params(refrescar=True))
        return self.engine_name

    # ── Parámetros de la voz ────────────────────────────────────────────────────
    def _params(self, refrescar=False):
        """ParamsVoz efectivos (personaje activo > config > defecto), con caché de 2 s."""
        ahora = time.monotonic()
        c = self._params_cache
        if not refrescar and c is not None and ahora - c[0] < CACHE_PARAMS_S:
            return c[1]
        try:
            p = voces.voz_activa(self.config)
        except Exception:
            p = voces.ParamsVoz()
        self._params_cache = (ahora, p)
        return p

    def invalidar_params(self):
        """La próxima frase relee la voz (tras cambiar personaje o voz)."""
        self._params_cache = None

    @property
    def params(self):
        return self._params()

    def _params_edge(self, params=None):
        """Argumentos de edge_tts.Communicate: voice, rate, pitch y volume."""
        p = params or self._params()
        voz = p.id
        if not voces.es_id_edge(voz):     # el personaje pidió Kokoro/gTTS y no está: su voz de edge
            try:
                voz = voces.resolver_voz(self.config, None, motor="edge").id
            except Exception:
                voz = voces.VOZ_POR_DEFECTO
        return {"voice": voz, "rate": p.rate, "pitch": p.pitch, "volume": p.volumen}

    def _velocidad_kokoro(self, params):
        try:
            base = float(self._cfg("kokoro_velocidad", 1.0) or 1.0)
        except (TypeError, ValueError):
            base = 1.0
        return max(0.5, min(2.0, base * (1 + voces.porcentaje(params.rate) / 100)))

    # ── Errores: avisar en vez de tragarse ──────────────────────────────────────
    def _mensaje_error(self, exc, params=None, motor=""):
        p = params or self._params()
        if _es_sin_audio(exc):
            voz = self._params_edge(p)["voice"]
            if voces.es_voz_edge_conocida(voz):
                return f"edge-tts no devolvió audio con la voz «{voz}». Vuelve a intentarlo en un momento."
            return (f"La voz «{voz}» no devolvió audio: puede que no exista. "
                    f"Elige otra en Configuración → Voz (o /voces en la terminal).")
        if isinstance(exc, ImportError):
            return f"Falta el motor de voz {motor or '?'}: {exc}"
        if isinstance(exc, ValueError):
            return f"Ajuste de voz no válido ({exc}). Revisa velocidad, tono y volumen."
        if _es_de_red(exc):
            return f"No pude conectar con el servicio de voz ({motor or 'edge-tts'}). ¿Hay internet?"
        return f"Error de voz ({motor or '?'}): {type(exc).__name__}: {exc}"

    def _avisar(self, mensaje):
        """Llama a on_error(mensaje) sin repetir el mismo aviso en ráfaga."""
        self.ultimo_error = mensaje
        if self._avisos is None:
            self._avisos = {}
        ahora = time.monotonic()
        ultimo = self._avisos.get(mensaje)
        if ultimo is not None and ahora - ultimo < SILENCIO_AVISOS_S:
            return
        self._avisos[mensaje] = ahora
        cb = self.on_error
        if cb is None:
            return
        try:
            cb(mensaje)
        except Exception:
            pass

    def _avisar_error(self, exc, params=None, motor=""):
        try:
            self._avisar(self._mensaje_error(exc, params, motor))
        except Exception:
            pass

    # ── Hablar ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _limpiar(text: str, tope: int = 400) -> str:
        # Red de seguridad (prueba real): ninguna marca de control se lee en voz, ni
        # las buenas ni las rotas (<|OPEN_URL …|>, |<ACT …>|) ni las neutralizadas
        # (< |CALL …|>). Sin esto la voz decía «OPEN_URL httpswww.nasa.gov».
        text = text or ''
        try:
            from lune_core.marcadores import limpiar_para_mostrar
            text = limpiar_para_mostrar(text)
        except Exception:
            pass
        text = re.sub(r'<\s+\|.*?\|>', ' ', text, flags=re.DOTALL)
        limpio = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', text, flags=re.UNICODE).strip()
        limpio = re.sub(r'[ \t]{2,}', ' ', limpio)
        if len(limpio) > tope:                      # cortar en un espacio, no a media palabra
            corte = limpio.rfind(" ", 0, tope)
            limpio = limpio[:corte if corte > tope // 2 else tope].rstrip()
        return limpio

    @property
    def silenciada(self):
        return self._silenciada

    def silenciar(self, on=True):
        """Modo juego: corta lo que suene y no habla hasta silenciar(False)."""
        self._silenciada = bool(on)
        if self._silenciada:
            self.cancelar()

    def speak(self, text: str):
        if not self._enabled or not self._engine or self._silenciada: return
        clean = self._limpiar(text)
        if clean:
            threading.Thread(target=self._speak_blocking, args=(clean, self._gen_voz), daemon=True).start()

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
        if not self._enabled or not self._engine or self._silenciada:
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
        if not self.mixer_abierto():       # nada suena (y sin pagar el import de pygame)
            return
        try:
            _pygame_si_cargado().mixer.music.stop()
        except Exception:
            pass

    def _speak_segmentos_blocking(self, segmentos, al_segmento, al_terminar, gen):
        from concurrent.futures import ThreadPoolExecutor
        with self._lock:
            if gen != self._gen_voz:                # lo cancelaron mientras esperaba su turno
                return
            # Todos los tramos salen con la misma voz: _params() la guarda 2 s.
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

    def _speak_blocking(self, text: str, gen=None):
        with self._lock:
            if gen is not None and gen != self._gen_voz:
                return
            params = self._params()
            motor = self._motor_para(params)
            if motor == "edge": self._speak_edge(text, params)
            elif motor == "gtts": self._speak_gtts(text, params)
            elif motor == "kokoro":
                ruta = self._sintetizar_a_archivo(text, params)
                if ruta: self._reproducir_archivo(ruta)

    # ── Probar una voz (botón «Probar», /voz prueba) ─────────────────────────────
    def probar_voz(self, params=None, texto=None) -> bool:
        """
        Corta lo que suene y dice `texto` (o una frase de prueba) con `params`
        (ParamsVoz, dict o JSON de la interfaz; lo que falte sale de la voz
        actual; un "texto" dentro del JSON vale como `texto`). Suena aunque la
        voz esté apagada o en modo juego: es una orden explícita. En su propio
        hilo. False si no hay motor ni salida de audio.
        """
        if isinstance(params, str):
            try:
                params = json.loads(params) if params.strip() else None
            except ValueError:
                params = None
        if isinstance(params, dict) and not texto:
            texto = str(params.get("texto") or "").strip() or None
        if not self._engine:
            from nucleo import rutas
            self._avisar(f"No hay motor de voz: instala edge-tts ({rutas.como_instalar('edge-tts')}) "
                         "o revisa la salida de audio.")
            return False
        self.cancelar()
        try:
            p = voces.params_desde(params, self._params())
        except Exception:
            p = self._params()
        clean = self._limpiar(texto or voces.TEXTO_PRUEBA)
        if not clean:
            return False
        if p.motor == "kokoro" and not self._kokoro_disponible():
            self._avisar("Kokoro no está instalado; la prueba suena con edge-tts.")
        gen = self._gen_voz

        def _probar():
            with self._lock:
                if gen != self._gen_voz:
                    return
                ruta = self._sintetizar_a_archivo(clean, p)
                if ruta is None:
                    return
                if gen != self._gen_voz:
                    self._borrar(ruta)
                    return
                self._reproducir(ruta)

        threading.Thread(target=_probar, name="voz-prueba", daemon=True).start()
        return True

    # ── Aviso «está sonando» (la asistente 3D mueve la boca mientras Lune habla) ──
    def _sonando(self, activo: bool):
        cb = self.al_hablar
        if cb is None:
            return
        try:
            cb(bool(activo))
        except Exception:
            pass

    def _speak_edge(self, text: str, params=None):
        ruta = self._sintetizar_a_archivo(text, params, motor="edge")
        if ruta:
            self._reproducir_archivo(ruta)

    def _speak_gtts(self, text: str, params=None):
        ruta = self._sintetizar_a_archivo(text, params, motor="gtts")
        if ruta:
            self._reproducir_archivo(ruta)

    def toggle(self) -> bool: self._enabled = not self._enabled; return self._enabled
    @property
    def available(self): return self._engine is not None
    @property
    def engine_name(self):
        return {"edge": "edge-tts", "gtts": "gTTS",
                "kokoro": "Kokoro (local)"}.get(self._engine, "sin voz")

    # ── Síntesis de una frase a archivo (para el pipeline en streaming) ─────────
    def _edge_guardar(self, texto: str, ruta: str, params):
        """edge-tts a `ruta` con la voz de `params`. Si la voz no existe (NoAudioReceived
        con una voz que no está en la lista), avisa y repite con la de por defecto."""
        import asyncio
        import edge_tts
        kw = self._params_edge(params)

        async def _s(k):
            await edge_tts.Communicate(texto, k["voice"], rate=k["rate"], pitch=k["pitch"],
                                       volume=k["volume"]).save(ruta)
        try:
            asyncio.run(_s(kw))
        except Exception as e:
            if (not _es_sin_audio(e) or kw["voice"] == voces.VOZ_POR_DEFECTO
                    or voces.es_voz_edge_conocida(kw["voice"])):
                raise
            self._avisar(self._mensaje_error(e, params, "edge-tts")
                         + f" Mientras tanto hablo con {voces.VOZ_POR_DEFECTO}.")
            asyncio.run(_s(dict(kw, voice=voces.VOZ_POR_DEFECTO)))

    def _sintetizar_a_archivo(self, texto: str, params=None, motor=None):
        """Devuelve la ruta de un audio con `texto`, o None. Sin reproducir."""
        clean = re.sub(r'[^\w\s,.!?áéíóúüñ¿¡]', '', texto or '', flags=re.UNICODE).strip()
        if not clean or not self._engine:
            return None
        if not re.search(r"[^\W_]", clean):     # solo signos: nada que decir (edge daría NoAudioReceived)
            return None
        p = params or self._params()
        motor = motor or self._motor_para(p)
        # Kokoro local → WAV, con posible conversión de voz (RVC) encima.
        if motor == "kokoro":
            try:
                from lune_core.voz import kokoro_backend
                ruta = kokoro_backend.sintetizar(
                    clean,
                    voz=p.id if p.motor == "kokoro" else self._cfg("kokoro_voz", kokoro_backend.VOZ_POR_DEFECTO),
                    velocidad=self._velocidad_kokoro(p),
                    carpeta=self._cfg("kokoro_carpeta", "modelos_voz"),
                    idioma=self._cfg("idioma", "es"),
                )
                if ruta:
                    return self._quizas_rvc(ruta)
            except Exception:
                pass
            # Kokoro falló (pesos, espeak-ng…): se avisa y se sigue con edge/gTTS.
            self._avisar("Kokoro no pudo generar la voz; sigo con edge-tts.")
            motor = "edge" if "edge" in self._disponibles else ("gtts" if "gtts" in self._disponibles else None)
            if motor is None:
                return None
        import tempfile
        t = None
        try:
            t = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False); t.close()
            if motor == "edge":
                self._edge_guardar(clean, t.name, p)
            else:
                from gtts import gTTS
                gTTS(clean, lang="es", tld=p.tld or voces.TLD_POR_DEFECTO).save(t.name)
            return t.name
        except Exception as e:
            if t is not None:
                self._borrar(t.name)         # sin red: no dejar un .mp3 vacío por ahí
            self._avisar_error(e, p, {"edge": "edge-tts", "gtts": "gTTS"}.get(motor, motor))
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
        """Reproduce y borra `ruta`. En modo juego no suena (solo se borra)."""
        if self._silenciada:
            self._borrar(ruta)
            return
        self._reproducir(ruta)

    def _reproducir(self, ruta: str):
        try:
            import pygame
            # Abrir (si hace falta) y empezar a sonar con el candado: el vigilante no
            # puede cerrar la tarjeta entre medias. Sin tarjeta, ya avisó y no suena.
            with self._candado_mixer():
                if not self._asegurar_mixer():
                    self._borrar(ruta)
                    return
                pygame.mixer.music.load(ruta); pygame.mixer.music.play()
            self._sonando(True)
            try:
                while pygame.mixer.music.get_busy():
                    threading.Event().wait(0.05)
            finally:
                self._ultimo_sonido = time.monotonic()
                self._sonando(False)
                self._soltar_audio()
        except Exception as e:
            self._avisar(f"No pude reproducir la voz por la salida de audio: {e}")
        self._borrar(ruta)

    @staticmethod
    def _soltar_audio():
        # SDL mantiene el archivo abierto hasta unload(): sin esto, en Windows el
        # borrado falla (WinError 32) y los temporales se acumulan en %TEMP%.
        pg = _pygame_si_cargado()
        if pg is None:
            return
        try:
            pg.mixer.music.unload()
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
        if not self.voz.available or not self.voz._enabled or getattr(self.voz, "silenciada", False):
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
