"""
servicios/llamada.py — Modo llamada: conversación continua solo por voz.

Como una llamada tipo ChatGPT: Lune escucha, transcribe lo que dices, lo manda
al chat, y cuando la respuesta está lista LA HABLA; al terminar vuelve a
escuchar. Todo en bucle hasta que apagues la llamada.

Piezas que reutiliza (ya existían): Whisper local (voz_entrada) para oír,
VoiceEngine (voice) para hablar, y el chat normal de la app para responder.

Detección de voz sencilla por energía (RMS): espera a que hables, graba hasta
~1.2 s de silencio y transcribe. Mientras Lune habla NO escucha (así no se oye
a sí misma).

Ciclo por turno:
    escuchar → transcribir → emitir `transcrito` → esperar la respuesta
    (decir_y_seguir) → hablarla → escuchar…
"""
from __future__ import annotations

import tempfile
import threading
import wave

from PyQt6.QtCore import QThread, pyqtSignal

FS = 16000                 # Whisper trabaja a 16 kHz
BLOQUE_S = 0.1             # tamaño de bloque de audio (segundos)
SILENCIO_FIN_S = 1.2       # silencio tras hablar que cierra la frase
ESPERA_VOZ_S = 60          # sin voz en este tiempo → reintenta (no bloquea)
ESPERA_RESPUESTA_S = 120   # si la respuesta no llega, vuelve a escuchar


class LlamadaWorker(QThread):
    estado = pyqtSignal(str)        # escuchando · transcribiendo · esperando · hablando · off
    transcrito = pyqtSignal(str)    # lo que dijo el usuario
    aviso = pyqtSignal(str)
    terminado = pyqtSignal()

    def __init__(self, voice, modelo_whisper="base", idioma="es", umbral=0.015,
                 dispositivo=None):
        super().__init__()
        self.voice = voice
        self.modelo = modelo_whisper
        self.idioma = idioma
        self.umbral = float(umbral)
        self.dispositivo = dispositivo      # índice de sounddevice; None = por defecto
        self._parar = threading.Event()
        self._respuesta_lista = threading.Event()
        self._respuesta = ""

    # ── Control desde fuera ──────────────────────────────────────────────────────
    def decir_y_seguir(self, texto: str):
        """La app entrega la respuesta: el worker la habla y vuelve a escuchar."""
        self._respuesta = (texto or "").strip()
        self._respuesta_lista.set()

    def parar(self):
        self._parar.set()
        self._respuesta_lista.set()   # despierta si estaba esperando

    # ── Bucle ────────────────────────────────────────────────────────────────────
    def run(self):
        from servicios import voz_entrada
        try:
            while not self._parar.is_set():
                self.estado.emit("escuchando")
                wav = self._escuchar()
                if self._parar.is_set():
                    break
                if not wav:
                    continue          # nadie habló: seguir escuchando
                self.estado.emit("transcribiendo")
                try:
                    texto = voz_entrada.transcribir(wav, self.modelo, self.idioma)
                except Exception as e:
                    self.aviso.emit(f"No pude transcribir: {e}")
                    continue
                if not (texto or "").strip():
                    continue
                self._respuesta_lista.clear()
                self._respuesta = ""
                self.transcrito.emit(texto.strip())
                self.estado.emit("esperando")
                self._respuesta_lista.wait(ESPERA_RESPUESTA_S)
                if self._parar.is_set():
                    break
                if self._respuesta:
                    self.estado.emit("hablando")
                    self._hablar(self._respuesta)
        finally:
            self.estado.emit("off")
            self.terminado.emit()

    def _escuchar(self):
        """Graba hasta que hables y luego calles ~1.2 s. Devuelve ruta WAV o None."""
        try:
            import numpy as np
            import sounddevice as sd
            from servicios.voz_entrada import _abrir_stream
        except Exception as e:
            self.aviso.emit(f"Modo llamada: falta sounddevice/numpy ({e})")
            self._parar.set()
            return None
        frames, hablando, silencio, bloques = [], False, 0, 0
        max_bloques = int(ESPERA_VOZ_S / BLOQUE_S)
        fin_silencio = int(SILENCIO_FIN_S / BLOQUE_S)
        # 16 kHz si el micrófono lo acepta; si no, su frecuencia nativa (el WAV
        # se escribe a la real y Whisper remuestrea).
        try:
            stream, fs = _abrir_stream(sd, self.dispositivo, lambda sr: sd.InputStream(
                samplerate=sr, channels=1, dtype="int16", blocksize=int(sr * BLOQUE_S),
                device=self.dispositivo))
        except Exception as e:
            self.aviso.emit(f"Llamada: {e}")
            self._parar.set()
            return None
        bloque = int(fs * BLOQUE_S)
        try:
            with stream as s:
                while not self._parar.is_set():
                    data, _ = s.read(bloque)
                    rms = float(np.sqrt(np.mean((data.astype(np.float32) / 32768.0) ** 2)))
                    bloques += 1
                    if rms > self.umbral:
                        hablando, silencio = True, 0
                        frames.append(data.copy())
                    elif hablando:
                        silencio += 1
                        frames.append(data.copy())
                        if silencio >= fin_silencio:
                            break
                    elif bloques >= max_bloques:
                        return None
        except Exception as e:
            self.aviso.emit(f"Llamada: se perdió el micrófono ({e})")
            self._parar.set()
            return None
        if not hablando or len(frames) < 4:
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); tmp.close()
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs)
            w.writeframes(b"".join(f.tobytes() for f in frames))
        return tmp.name

    def _hablar(self, texto: str):
        """Habla BLOQUEANDO (para no escuchar mientras Lune habla)."""
        try:
            ruta = self.voice._sintetizar_a_archivo(texto)
            if ruta:
                self.voice._reproducir_archivo(ruta)
        except Exception as e:
            self.aviso.emit(f"No pude hablar: {e}")
