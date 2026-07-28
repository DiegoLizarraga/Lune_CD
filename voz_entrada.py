"""
voz_entrada.py — Dictado: graba del micrófono y transcribe con Whisper local.

Complementa a voice.py (que solo habla). Todo corre en tu máquina: el audio no
sale de aquí.

Dependencias, ambas de carga diferida — si faltan, la app arranca igual y el
botón del micrófono explica qué instalar:
    pip install faster-whisper sounddevice

`faster-whisper` es bastante más rápido que el whisper original y va bien en CPU
con el modelo «base». En el PC potente, con GPU, sube a «small» o «medium» desde
Configuración y notarás la diferencia.

El modelo se carga UNA vez y se queda en memoria: la primera transcripción tarda
unos segundos (descarga y carga) y las siguientes son casi instantáneas.
"""
import importlib.util
import queue
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Optional, Tuple

FRECUENCIA = 16000   # Whisper trabaja a 16 kHz
CANALES = 1

MODELOS = ["tiny", "base", "small", "medium", "large-v3"]

_modelo_cargado = None
_modelo_nombre = None
_lock_modelo = threading.Lock()


# ── Disponibilidad ─────────────────────────────────────────────────────────────

def dependencias_faltantes() -> List[str]:
    """Paquetes pip que faltan para poder dictar."""
    faltan = []
    if importlib.util.find_spec("faster_whisper") is None:
        faltan.append("faster-whisper")
    if importlib.util.find_spec("sounddevice") is None:
        faltan.append("sounddevice")
    return faltan


def disponible() -> bool:
    return not dependencias_faltantes()


def mensaje_instalacion() -> str:
    faltan = dependencias_faltantes()
    if not faltan:
        return ""
    return ("Para dictar por voz necesito:\n\n"
            f"    pip install {' '.join(faltan)}\n\n"
            "Es transcripción 100% local: el audio no sale de tu equipo.")


def hay_microfono() -> Tuple[bool, str]:
    try:
        import sounddevice as sd
    except Exception:
        return False, "sounddevice no está instalado."
    try:
        dispositivos = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as e:
        return False, f"No pude consultar los dispositivos de audio: {e}"
    if not dispositivos:
        return False, "No encontré ningún micrófono conectado."
    return True, dispositivos[0].get("name", "micrófono")


# ── Grabación ──────────────────────────────────────────────────────────────────

class Grabadora:
    """
    Graba del micrófono hasta que le digas que pare.

    El callback de sounddevice corre en un hilo suyo de tiempo real, así que se
    limita a meter los bloques en una cola: si haces trabajo pesado ahí, el audio
    sale con cortes.
    """

    def __init__(self):
        self._cola: queue.Queue = queue.Queue()
        self._stream = None
        self.grabando = False

    def iniciar(self):
        import sounddevice as sd

        self._cola = queue.Queue()

        def callback(indata, _frames, _time, estado):
            if estado:
                pass  # xruns puntuales: no vale la pena abortar por eso
            self._cola.put(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=FRECUENCIA, blocksize=4000, dtype="int16",
            channels=CANALES, callback=callback,
        )
        self._stream.start()
        self.grabando = True

    def detener(self) -> Optional[Path]:
        """Cierra el stream y vuelca lo grabado a un WAV temporal."""
        if not self.grabando:
            return None
        self.grabando = False
        try:
            self._stream.stop(); self._stream.close()
        except Exception:
            pass
        self._stream = None

        bloques = []
        while not self._cola.empty():
            bloques.append(self._cola.get())
        if not bloques:
            return None

        audio = b"".join(bloques)
        # Menos de ~0.4 s es un clic sin querer, no una frase
        if len(audio) < FRECUENCIA * 2 * 0.4:
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(CANALES)
            w.setsampwidth(2)          # int16
            w.setframerate(FRECUENCIA)
            w.writeframes(audio)
        return Path(tmp.name)

    def cancelar(self):
        if self._stream is not None:
            try:
                self._stream.stop(); self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.grabando = False


# ── Transcripción ──────────────────────────────────────────────────────────────

def cargar_modelo(nombre: str = "base"):
    """
    Carga (y cachea) el modelo de Whisper. La primera vez puede tardar: si no
    está descargado, faster-whisper lo baja de Hugging Face.
    """
    global _modelo_cargado, _modelo_nombre
    with _lock_modelo:
        if _modelo_cargado is not None and _modelo_nombre == nombre:
            return _modelo_cargado

        from faster_whisper import WhisperModel

        # Se intenta GPU y se cae a CPU con int8, que es lo razonable en equipos
        # sin CUDA. En el PC potente esto coge la GPU solo.
        try:
            modelo = WhisperModel(nombre, device="cuda", compute_type="float16")
        except Exception:
            modelo = WhisperModel(nombre, device="cpu", compute_type="int8")

        _modelo_cargado, _modelo_nombre = modelo, nombre
        return modelo


def transcribir(ruta_wav: Path, modelo: str = "base", idioma: str = "es") -> str:
    """Devuelve el texto dictado. Lanza RuntimeError con un mensaje presentable."""
    faltan = dependencias_faltantes()
    if faltan:
        raise RuntimeError(mensaje_instalacion())
    if not ruta_wav or not Path(ruta_wav).exists():
        raise RuntimeError("No se grabó nada.")

    try:
        w = cargar_modelo(modelo)
        segmentos, _info = w.transcribe(
            str(ruta_wav),
            language=idioma or None,
            vad_filter=True,            # recorta los silencios
            beam_size=5,
        )
        return " ".join(s.text.strip() for s in segmentos).strip()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"No pude transcribir el audio: {e}")
    finally:
        try:
            Path(ruta_wav).unlink(missing_ok=True)
        except OSError:
            pass


def descargar_modelo():
    """Suelta el modelo de memoria (útil para liberar VRAM)."""
    global _modelo_cargado, _modelo_nombre
    with _lock_modelo:
        _modelo_cargado = None
        _modelo_nombre = None
