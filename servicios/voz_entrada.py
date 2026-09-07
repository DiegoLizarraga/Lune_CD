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

DISPOSITIVOS (v10)
------------------
Windows suele traer varios micrófonos (el de la laptop, el headset Bluetooth,
el "Steam Streaming Microphone"…) y el que PortAudio elige por defecto no es
necesariamente el que tienes puesto. Por eso el usuario puede elegir uno en
Configuración; se guarda por NOMBRE (los índices cambian al enchufar cosas) y
se resuelve a índice justo antes de abrir el stream. Si el nombre ya no existe
(headset apagado), se cae al micrófono por defecto y se avisa.

Cada dispositivo aparece repetido una vez por API (MME, DirectSound, WASAPI,
WDM-KS). Se listan solo los de la API preferida (MME en Windows: es la que usa
PortAudio por defecto y la que remuestrea sola a 16 kHz).
"""
import importlib.util
import queue
import tempfile
import threading
import wave
from array import array
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FRECUENCIA = 16000   # Whisper trabaja a 16 kHz
CANALES = 1

MODELOS = ["tiny", "base", "small", "medium", "large-v3"]

_modelo_cargado = None
_modelo_nombre = None
_modelo_dispositivo = None   # "cuda" | "cpu" con el que se cargó
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


# ── Dispositivos de entrada ────────────────────────────────────────────────────

def _api_preferida(sd) -> Optional[int]:
    """Índice de la host API cuyos dispositivos se listan (MME en Windows)."""
    try:
        apis = list(sd.query_hostapis())
    except Exception:
        return None
    for i, api in enumerate(apis):
        if "MME" in str(api.get("name", "")):
            return i
    return None          # Linux/macOS: una sola API útil, se listan todos


def listar_entradas() -> List[Dict]:
    """
    Micrófonos disponibles: [{id, nombre, canales, sr, defecto}], sin repetir
    el mismo nombre. Lista vacía si sounddevice no está o no hay ninguno.
    """
    try:
        import sounddevice as sd
        dispositivos = sd.query_devices()
    except Exception:
        return []
    api = _api_preferida(sd)
    try:
        defecto = sd.default.device[0]
    except Exception:
        defecto = -1
    vistos, salida = set(), []
    for i, d in enumerate(dispositivos):
        if d.get("max_input_channels", 0) <= 0:
            continue
        if api is not None and d.get("hostapi") != api:
            continue
        nombre = str(d.get("name", "")).strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)
        salida.append({
            "id": i, "nombre": nombre,
            "canales": int(d.get("max_input_channels", 1)),
            "sr": int(d.get("default_samplerate", 44100) or 44100),
            "defecto": i == defecto,
        })
    return salida


def resolver_entrada(nombre: Optional[str]) -> Optional[int]:
    """
    Nombre guardado en config → índice de sounddevice. None si está vacío (usa
    el micrófono por defecto) o si ese dispositivo ya no está conectado.
    Primero coincidencia exacta; si no, por prefijo (MME recorta los nombres
    largos a 31 caracteres, así que «Headset (WH-CH520)» y «Headset (WH-CH520) Hands-Free»
    pueden ser el mismo aparato).
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    entradas = listar_entradas()
    for e in entradas:
        if e["nombre"] == nombre:
            return e["id"]
    n = nombre.lower()
    for e in entradas:
        en = e["nombre"].lower()
        if en.startswith(n) or n.startswith(en):
            return e["id"]
    return None


def nombre_dispositivo(indice: Optional[int]) -> str:
    """Nombre legible del índice (o del micrófono por defecto si es None)."""
    try:
        import sounddevice as sd
        d = sd.query_devices(indice if indice is not None else None, "input")
        return str(d.get("name", "micrófono"))
    except Exception:
        return "micrófono"


def hay_microfono(dispositivo: Optional[int] = None) -> Tuple[bool, str]:
    """(hay, nombre_o_motivo). Con `dispositivo` comprueba ESE índice."""
    try:
        import sounddevice as sd
    except Exception:
        return False, "sounddevice no está instalado."
    try:
        if dispositivo is not None:
            d = sd.query_devices(dispositivo)
            if d.get("max_input_channels", 0) > 0:
                return True, str(d.get("name", "micrófono"))
            return False, f"«{d.get('name', dispositivo)}» no es un micrófono."
        dispositivos = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as e:
        return False, f"No pude consultar los dispositivos de audio: {e}"
    if not dispositivos:
        return False, "No encontré ningún micrófono conectado."
    return True, nombre_dispositivo(None)


def _abrir_stream(sd, dispositivo, crear):
    """
    Abre un stream probando 16 kHz (lo que Whisper quiere) y, si el dispositivo
    no lo acepta (pasa con WASAPI/WDM-KS o hardware raro), su frecuencia nativa.
    `crear(samplerate)` construye el stream. Devuelve (stream, samplerate).
    """
    candidatos = [FRECUENCIA]
    try:
        info = sd.query_devices(dispositivo if dispositivo is not None else None, "input")
        nativa = int(info.get("default_samplerate", 0) or 0)
        if nativa and nativa != FRECUENCIA:
            candidatos.append(nativa)
    except Exception:
        pass
    if 44100 not in candidatos and 48000 not in candidatos:
        candidatos += [48000, 44100]
    ultimo = None
    for sr in candidatos:
        try:
            return crear(sr), sr
        except Exception as e:       # PortAudioError u otros: probar la siguiente
            ultimo = e
    raise RuntimeError(f"no pude abrir el micrófono ({ultimo})")


def _rms_int16(datos: bytes) -> float:
    """Energía 0..1 de un bloque int16 (sin numpy: basta para medir nivel)."""
    a = array("h"); a.frombytes(datos[: len(datos) - len(datos) % 2])
    if not a:
        return 0.0
    return (sum(x * x for x in a) / len(a)) ** 0.5 / 32768.0


def probar_microfono(dispositivo: Optional[int] = None, segundos: float = 1.5) -> Dict:
    """
    Graba `segundos` y devuelve cuánto se oyó: {ok, nivel, pico, nombre, sr, error}.
    `nivel`/`pico` van 0..1 (RMS medio y máximo por bloque). ok = se oyó algo
    por encima del ruido de fondo (≈ hablaste o hay ruido cerca).
    """
    faltan = dependencias_faltantes()
    if "sounddevice" in faltan:
        return {"ok": False, "nivel": 0, "pico": 0, "nombre": "", "sr": 0,
                "error": "sounddevice no está instalado (pip install sounddevice)."}
    import sounddevice as sd
    nombre = nombre_dispositivo(dispositivo)
    bloques: List[bytes] = []

    def cb(indata, _frames, _time, _estado):
        bloques.append(bytes(indata))

    try:
        stream, sr = _abrir_stream(sd, dispositivo, lambda s: sd.RawInputStream(
            samplerate=s, blocksize=int(s * 0.1), dtype="int16", channels=CANALES,
            device=dispositivo, callback=cb))
    except Exception as e:
        return {"ok": False, "nivel": 0, "pico": 0, "nombre": nombre, "sr": 0, "error": str(e)}
    try:
        with stream:
            threading.Event().wait(segundos)
    except Exception as e:
        return {"ok": False, "nivel": 0, "pico": 0, "nombre": nombre, "sr": sr, "error": str(e)}
    niveles = [_rms_int16(b) for b in bloques] or [0.0]
    nivel, pico = sum(niveles) / len(niveles), max(niveles)
    return {"ok": pico > 0.01, "nivel": round(nivel, 4), "pico": round(pico, 4),
            "nombre": nombre, "sr": sr, "error": ""}


# ── Grabación ──────────────────────────────────────────────────────────────────

class Grabadora:
    """
    Graba del micrófono hasta que le digas que pare.

    El callback de sounddevice corre en un hilo suyo de tiempo real, así que se
    limita a meter los bloques en una cola: si haces trabajo pesado ahí, el audio
    sale con cortes.

    `dispositivo` es el índice de sounddevice (None = el de por defecto). El
    WAV sale a la frecuencia REAL con la que se abrió el stream: faster-whisper
    remuestrea solo, así que no importa que no sea 16 kHz.
    """

    def __init__(self, dispositivo: Optional[int] = None):
        self._cola: queue.Queue = queue.Queue()
        self._stream = None
        self.grabando = False
        self.dispositivo = dispositivo
        self.samplerate = FRECUENCIA

    def iniciar(self):
        import sounddevice as sd

        self._cola = queue.Queue()

        def callback(indata, _frames, _time, estado):
            if estado:
                pass  # xruns puntuales: no vale la pena abortar por eso
            self._cola.put(bytes(indata))

        self._stream, self.samplerate = _abrir_stream(
            sd, self.dispositivo,
            lambda sr: sd.RawInputStream(
                samplerate=sr, blocksize=int(sr * 0.25), dtype="int16",
                channels=CANALES, device=self.dispositivo, callback=callback))
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
        if len(audio) < self.samplerate * 2 * 0.4:
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(CANALES)
            w.setsampwidth(2)          # int16
            w.setframerate(self.samplerate)
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

def modelo_descargado(nombre: str = "base") -> bool:
    """¿Está el modelo en la caché de Hugging Face? (si no, la 1ª vez descarga)."""
    try:
        from huggingface_hub import constants
        base = Path(constants.HF_HUB_CACHE)
    except Exception:
        base = Path.home() / ".cache" / "huggingface" / "hub"
    return any(p.is_dir() for p in base.glob(f"models--*faster-whisper-{nombre}*"))


def _hay_cuda() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def cargar_modelo(nombre: str = "base", forzar_cpu: bool = False):
    """
    Carga (y cachea) el modelo de Whisper. La primera vez puede tardar: si no
    está descargado, faster-whisper lo baja de Hugging Face.
    """
    global _modelo_cargado, _modelo_nombre, _modelo_dispositivo
    with _lock_modelo:
        destino = "cpu" if (forzar_cpu or not _hay_cuda()) else "cuda"
        if (_modelo_cargado is not None and _modelo_nombre == nombre
                and _modelo_dispositivo == destino):
            return _modelo_cargado

        from faster_whisper import WhisperModel

        # GPU si ctranslate2 la ve; si no (o si falla al cargar), CPU con int8,
        # que es lo razonable en equipos sin CUDA. En el PC potente esto coge la
        # GPU solo.
        modelo = None
        if destino == "cuda":
            try:
                modelo = WhisperModel(nombre, device="cuda", compute_type="float16")
            except Exception:
                destino = "cpu"
        if modelo is None:
            modelo = WhisperModel(nombre, device="cpu", compute_type="int8")

        _modelo_cargado, _modelo_nombre, _modelo_dispositivo = modelo, nombre, destino
        return modelo


def _mensaje_error_modelo(e: Exception, modelo: str) -> str:
    """Traduce los fallos típicos de faster-whisper a algo que se entienda."""
    texto = str(e)
    bajo = texto.lower()
    if any(k in bajo for k in ("connection", "resolve", "huggingface", "timed out",
                               "max retries", "name or service", "getaddrinfo")):
        return (f"No pude descargar el modelo Whisper «{modelo}» (necesita internet la "
                "primera vez). Prueba con «tiny» en Configuración → Audio, o conéctate y reintenta.")
    if "cudnn" in bajo or "cublas" in bajo or "cuda" in bajo:
        return "La GPU no tiene las librerías de CUDA; reintenta y usaré la CPU."
    return f"No pude transcribir el audio: {texto}"


def transcribir(ruta_wav: Path, modelo: str = "base", idioma: str = "es") -> str:
    """Devuelve el texto dictado. Lanza RuntimeError con un mensaje presentable."""
    faltan = dependencias_faltantes()
    if faltan:
        raise RuntimeError(mensaje_instalacion())
    if not ruta_wav or not Path(ruta_wav).exists():
        raise RuntimeError("No se grabó nada.")

    def _correr(w):
        segmentos, _info = w.transcribe(
            str(ruta_wav),
            language=idioma or None,
            vad_filter=True,            # recorta los silencios
            beam_size=5,
        )
        return " ".join(s.text.strip() for s in segmentos).strip()

    try:
        try:
            return _correr(cargar_modelo(modelo))
        except Exception as e:
            # Las librerías de CUDA fallan al TRANSCRIBIR, no al cargar (cuDNN,
            # cuBLAS ausentes): se reintenta una vez en CPU antes de rendirse.
            if _modelo_dispositivo == "cuda" and ("cu" in str(e).lower()):
                return _correr(cargar_modelo(modelo, forzar_cpu=True))
            raise
    except RuntimeError as e:
        raise RuntimeError(_mensaje_error_modelo(e, modelo))
    except Exception as e:
        raise RuntimeError(_mensaje_error_modelo(e, modelo))
    finally:
        try:
            Path(ruta_wav).unlink(missing_ok=True)
        except OSError:
            pass
