"""
servicios/mezclador.py — Mezclador de audio de Lune para todo lo que no es la voz.

La voz de Lune tiene `pygame.mixer.music` para ella sola (voice.py). Alarmas,
efectos (comida, menús, arrastre) y la música de los bailes en sprites y
patata pasan por aquí, porque las alternativas no mezclan:

* `winsound` solo suena un sonido asíncrono a la vez por proceso (un trago
  cortaría la alarma).
* `sd.play()` de sounddevice corta lo que sonaba antes.
* `pygame.mixer` es de la voz, y `voice.aplicar_salida()` hace `mixer.quit()`.

Cómo funciona: un único `sounddevice.OutputStream` (44.1 kHz, estéreo,
float32) cuyo callback suma con numpy todas las fuentes activas, aplica su
volumen y el de su canal (`alarma`, `sfx`, `musica`) y recorta a [-1, 1].
Cada fuente tiene su velocidad (remuestreo lineal: cambia el tono, como
`playbackRate`), su bucle y su posición.

El stream NO se queda abierto: se abre al reproducir y se cierra tras
`SILENCIO_CIERRE_S` (5 s) sin nada sonando. Un stream siempre abierto impide
que un juego abra la tarjeta en modo exclusivo (AUDCLNT_E_DEVICE_IN_USE) y
mantiene despierto el audio del equipo.

Dispositivo: se elige por NOMBRE (`voz.dispositivo_salida`, el mismo que usa
la voz). Ese nombre viene de pygame/SDL y no coincide letra a letra con los
de PortAudio: MME los recorta a 31 caracteres y Windows añade «2- » cuando un
aparato reaparece. Por eso se busca por coincidencia aproximada y en WASAPI
primero (nombres completos, modo compartido). WDM-KS se descarta: abre la
tarjeta en exclusiva.

Si sounddevice no está o no abre ningún dispositivo, cae a `winsound`: suena
como WAV (se escribe uno temporal), sin mezcla (el último corta al anterior).

Stream muerto: si el dispositivo desaparece (auriculares desenchufados,
AUDCLNT_E_DEVICE_INVALIDATED), PortAudio deja de llamar al callback y las
fuentes ya no avanzan. Se detecta de tres formas: `stream.active` en False, el
`finished_callback` del stream, o (en el vigilante) que algo debería sonar y el
callback lleva `CALLBACK_MUDO_S` sin correr. Entonces se cierra y se reabre (la
salida del sistema, device=None, es el «Sound Mapper» de MME, que sigue al
dispositivo por defecto actual); si no abre nada, o si tras
`MAX_REAPERTURAS_MUDAS` reaperturas ningún stream llega a pedir audio, lo que
sonaba pasa a winsound.
No se reinicia PortAudio (`Pa_Terminate`) para refrescar la lista: cerraría
también los streams del micrófono (dictado, modo llamada), que son de otro
módulo del mismo proceso.

Decodificación: `cargar_wav()` lee WAV PCM de 8/16/24/32 bits y float sin
dependencias; `cargar_audio()` usa el ffmpeg de imageio-ffmpeg para mp3, ogg,
flac… (subproceso a PCM f32le 44.1 kHz estéreo). La caché solo guarda audios
cortos (efectos): hasta `_CACHE_BUFFER_MAX_BYTES` cada uno y
`_CACHE_MAX_BYTES` en total; una canción en WAV no se queda en RAM.

Sin Qt; sounddevice, winsound, el reloj y ffmpeg son inyectables para probarlo
sin tarjeta de sonido.
"""
from __future__ import annotations

import difflib
import itertools
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger("lune.mezclador")

FRECUENCIA = 44100
CANALES_SALIDA = 2
SILENCIO_CIERRE_S = 5.0
CANALES = ("alarma", "sfx", "musica")

EXTENSIONES_FFMPEG = (".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".wma", ".webm")

_CACHE_MAX = 48                            # WAV cortos (efectos) que se quedan en memoria
_CACHE_MAX_BYTES = 32 * 1024 * 1024        # tope total de la caché
_CACHE_BUFFER_MAX_BYTES = 2 * 1024 * 1024  # lo más grande que se guarda (~6 s estéreo float32)

# Si algo debería sonar y el callback de audio lleva este tiempo sin correr, el
# stream está muerto (un stream vivo lo llama cada ~10 ms, suene algo o no).
CALLBACK_MUDO_S = 2.0
# Reaperturas seguidas sin que ningún stream llegue a llamar al callback: a la
# siguiente se deja de insistir y lo que suena pasa a winsound.
MAX_REAPERTURAS_MUDAS = 3


class ErrorAudio(Exception):
    """Error al leer o reproducir audio, con un mensaje apto para el usuario."""


Buffer = Union[np.ndarray, str, Path]


# ── Conversión de formatos ─────────────────────────────────────────────────────

def a_estereo(datos) -> np.ndarray:
    """
    Cualquier array de audio (N,) o (N, canales), entero o float → float32
    (N, 2) contiguo en [-1, 1]. Mono se duplica; más de 2 canales se quedan
    con los dos primeros.
    """
    a = np.asarray(datos)
    if a.dtype.kind == "u":
        bits = a.dtype.itemsize * 8
        a = (a.astype(np.float32) - 2 ** (bits - 1)) / 2 ** (bits - 1)
    elif a.dtype.kind == "i":
        a = a.astype(np.float32) / float(2 ** (a.dtype.itemsize * 8 - 1))
    elif a.dtype.kind != "f":
        raise ErrorAudio(f"Tipo de audio no soportado: {a.dtype}")
    a = a.astype(np.float32, copy=False)
    if a.ndim == 1:
        a = np.repeat(a[:, None], 2, axis=1)
    elif a.ndim == 2:
        if a.shape[1] == 1:
            a = np.repeat(a, 2, axis=1)
        elif a.shape[1] == 0:
            raise ErrorAudio("El audio no tiene canales.")
        else:
            a = a[:, :2]
    else:
        raise ErrorAudio(f"Forma de audio no soportada: {a.shape}")
    return np.ascontiguousarray(a, dtype=np.float32)


def remuestrear(datos: np.ndarray, sr_origen: int, sr_destino: int) -> np.ndarray:
    """Cambio de frecuencia con interpolación lineal (suficiente para efectos)."""
    if sr_origen == sr_destino or len(datos) == 0:
        return datos
    n = len(datos)
    n_out = max(1, int(round(n * sr_destino / sr_origen)))
    t = np.arange(n_out, dtype=np.float64) * (sr_origen / sr_destino)
    x = np.arange(n, dtype=np.float64)
    salida = np.empty((n_out, datos.shape[1]), dtype=np.float32)
    for c in range(datos.shape[1]):
        salida[:, c] = np.interp(t, x, datos[:, c])
    return salida


def duracion(buf: np.ndarray) -> float:
    """Segundos que dura un buffer del mezclador (a 44.1 kHz)."""
    return len(buf) / FRECUENCIA


# ── WAV sin dependencias ───────────────────────────────────────────────────────

def _leer_riff(ruta: Path) -> Tuple[np.ndarray, int]:
    """WAV en disco → (datos (N, canales) float32, frecuencia)."""
    try:
        raw = ruta.read_bytes()
    except OSError as e:
        raise ErrorAudio(f"No pude leer {ruta.name}: {e}") from e
    return _parsear_riff(raw, ruta.name)


def _parsear_riff(raw: bytes, nombre: str) -> Tuple[np.ndarray, int]:
    """
    Bytes de un WAV → (datos (N, canales) float32, frecuencia). PCM 8/16/24/32
    bits y float 32/64, también WAVE_FORMAT_EXTENSIBLE. Tolera el tamaño
    0xFFFFFFFF que escribe ffmpeg cuando saca el WAV por una tubería.
    """
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ErrorAudio(f"{nombre} no es un WAV válido.")
    pos, fmt, datos = 12, None, None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        tam = struct.unpack_from("<I", raw, pos + 4)[0]
        cuerpo = raw[pos + 8:pos + 8 + tam]     # si el tamaño miente, llega hasta el final
        if cid == b"fmt ":
            fmt = cuerpo
        elif cid == b"data":
            datos = cuerpo
            break
        pos += 8 + tam + (tam & 1)
    if fmt is None or len(fmt) < 16 or datos is None:
        raise ErrorAudio(f"{nombre}: WAV incompleto (falta fmt o data).")
    formato, canales, sr, _bps, alineacion, bits = struct.unpack_from("<HHIIHH", fmt)
    if formato == 0xFFFE and len(fmt) >= 26:        # WAVE_FORMAT_EXTENSIBLE
        formato = struct.unpack_from("<H", fmt, 24)[0]
    if canales < 1 or sr < 1:
        raise ErrorAudio(f"{nombre}: cabecera WAV rota.")
    ancho = bits // 8
    if alineacion != ancho * canales or ancho < 1:
        raise ErrorAudio(f"{nombre}: WAV de {bits} bits no soportado.")
    datos = datos[:len(datos) - len(datos) % alineacion]
    if formato == 1:                                 # PCM entero
        if ancho == 1:
            a = (np.frombuffer(datos, np.uint8).astype(np.float32) - 128.0) / 128.0
        elif ancho == 2:
            a = np.frombuffer(datos, "<i2").astype(np.float32) / 32768.0
        elif ancho == 3:
            b = np.frombuffer(datos, np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            v = np.where(v & 0x800000, v - 0x1000000, v)
            a = v.astype(np.float32) / 8388608.0
        elif ancho == 4:
            a = np.frombuffer(datos, "<i4").astype(np.float32) / 2147483648.0
        else:
            raise ErrorAudio(f"{nombre}: WAV de {bits} bits no soportado.")
    elif formato == 3:                               # IEEE float
        if ancho == 4:
            a = np.frombuffer(datos, "<f4").astype(np.float32)
        elif ancho == 8:
            a = np.frombuffer(datos, "<f8").astype(np.float32)
        else:
            raise ErrorAudio(f"{nombre}: WAV float de {bits} bits no soportado.")
    else:
        raise ErrorAudio(f"{nombre}: formato WAV {formato} no soportado (¿ADPCM, µ-law?).")
    return a.reshape(-1, canales), int(sr)


_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_lock_cache = threading.Lock()


def _bytes_cache() -> int:
    """Con `_lock_cache`: bytes que ocupan los buffers guardados."""
    return sum(b.nbytes for b in _cache.values())


def cargar_wav(ruta: Union[str, Path], cachear: bool = True) -> np.ndarray:
    """
    Lee un WAV y lo deja listo para el mezclador: float32 (N, 2) a 44.1 kHz.
    Guarda en caché los últimos leídos (por ruta, tamaño y fecha), así que los
    efectos que suenan a menudo no tocan el disco. Solo los cortos: un buffer
    de más de `_CACHE_BUFFER_MAX_BYTES` (música en WAV, ~21 MB por minuto) se
    devuelve sin guardar, y el total no pasa de `_CACHE_MAX_BYTES` (se expulsa
    el que lleva más tiempo sin usarse). Con `cachear=False` (el canal
    'musica') ni se guarda. El array devuelto es de solo lectura porque puede
    estar compartido.
    """
    p = Path(ruta)
    try:
        st = p.stat()
    except OSError as e:
        raise ErrorAudio(f"No encuentro el sonido {p}") from e
    clave = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    with _lock_cache:
        if clave in _cache:
            _cache.move_to_end(clave)
            return _cache[clave]
    datos, sr = _leer_riff(p)
    buf = remuestrear(a_estereo(datos), sr, FRECUENCIA)
    buf = np.ascontiguousarray(buf, dtype=np.float32)
    buf.setflags(write=False)
    if cachear and buf.nbytes <= min(_CACHE_BUFFER_MAX_BYTES, _CACHE_MAX_BYTES):
        with _lock_cache:
            _cache[clave] = buf
            while _cache and (len(_cache) > _CACHE_MAX or _bytes_cache() > _CACHE_MAX_BYTES):
                _cache.popitem(last=False)
    return buf


def ruta_ffmpeg() -> Optional[str]:
    """ffmpeg de imageio-ffmpeg (viene en su wheel) o, si no, el del PATH."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return str(exe)
    except Exception:
        pass
    return shutil.which("ffmpeg")


def cargar_audio(ruta: Union[str, Path], *, ffmpeg: Optional[str] = None,
                 ejecutar: Optional[Callable] = None, timeout: float = 180.0,
                 cachear: bool = True) -> np.ndarray:
    """
    Lee cualquier audio (wav, mp3, ogg, opus, flac, m4a…) → float32 (N, 2) a
    44.1 kHz. Los WAV normales se leen en Python (con la caché de efectos de
    `cargar_wav`; `cachear=False` para la música); el resto (y los WAV raros)
    los decodifica ffmpeg por subproceso a PCM f32le 44.1 kHz y nunca se
    guardan. Sin ffmpeg lanza ErrorAudio explicando qué instalar.

    ffmpeg saca un WAV con los canales originales: el mono se duplica aquí
    (con `-ac 2` ffmpeg lo bajaría 3 dB y sonaría más flojo que el mismo
    sonido en WAV). Solo lo que trae más de 2 canales se vuelve a pedir con
    `-ac 2`, para que ffmpeg haga la mezcla 5.1 → estéreo como es debido.
    """
    p = Path(ruta)
    if not p.is_file():
        raise ErrorAudio(f"No encuentro el archivo de audio: {p}")
    if p.suffix.lower() == ".wav":
        try:
            return cargar_wav(p, cachear=cachear)
        except ErrorAudio:
            pass                       # WAV comprimido: que lo intente ffmpeg
    exe = ffmpeg or ruta_ffmpeg()
    if not exe:
        from nucleo import rutas
        raise ErrorAudio(
            f"Para reproducir {p.suffix or 'este audio'} hace falta ffmpeg. "
            f"Instálalo con:  {rutas.como_instalar('imageio-ffmpeg')}")
    datos, sr = _decodificar_ffmpeg(exe, p, ejecutar or subprocess.run, timeout, estereo=False)
    if datos.shape[1] > CANALES_SALIDA:
        datos, sr = _decodificar_ffmpeg(exe, p, ejecutar or subprocess.run, timeout, estereo=True)
    if len(datos) == 0:
        raise ErrorAudio(f"{p.name} no tiene audio.")
    return np.ascontiguousarray(remuestrear(a_estereo(datos), sr, FRECUENCIA), dtype=np.float32)


def _decodificar_ffmpeg(exe: str, p: Path, ejecutar: Callable, timeout: float,
                        estereo: bool) -> Tuple[np.ndarray, int]:
    """Una pasada de ffmpeg → WAV f32le 44.1 kHz por la tubería → (datos, sr)."""
    cmd = [exe, "-nostdin", "-v", "error", "-i", str(p), "-vn", "-map", "0:a:0",
           "-map_metadata", "-1", "-fflags", "+bitexact",
           "-f", "wav", "-acodec", "pcm_f32le", "-ar", str(FRECUENCIA)]
    if estereo:
        cmd += ["-ac", str(CANALES_SALIDA)]
    cmd.append("pipe:1")
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        r = ejecutar(cmd, capture_output=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired as e:
        raise ErrorAudio(f"ffmpeg tardó demasiado en leer {p.name}.") from e
    except OSError as e:
        raise ErrorAudio(f"No pude ejecutar ffmpeg: {e}") from e
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        detalle = err[-1] if err else f"código {r.returncode}"
        raise ErrorAudio(f"ffmpeg no pudo leer {p.name}: {detalle}")
    return _parsear_riff(r.stdout or b"", p.name)


# ── Elección de dispositivo ────────────────────────────────────────────────────

_PRIORIDAD_API = (("wasapi", 0), ("directsound", 1), ("mme", 2))
_ALIAS_POR_DEFECTO = ("microsoft sound mapper", "primary sound driver",
                      "controlador primario de sonido", "asignador de sonido")


def _normalizar_nombre(nombre: str) -> str:
    n = str(nombre or "").lower().strip()
    n = re.sub(r"(?<![\w])\d+-\s*", "", n)       # «Speakers (2- Realtek)» → «speakers (realtek)»
    return re.sub(r"\s+", " ", n)


def _tokens(nombre: str) -> set:
    return set(t for t in re.split(r"[^\w]+", nombre) if t)


def similitud_nombres(pedido: str, candidato: str) -> float:
    """
    0..1: cuánto se parece el nombre guardado (de SDL/pygame) a uno de
    PortAudio. 1 = igual (sin el «2- » de Windows) o recortado por MME a 31
    caracteres; 0.95 = otro prefijo; si no, la media entre palabras
    compartidas y difflib.
    """
    a, b = _normalizar_nombre(pedido), _normalizar_nombre(candidato)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Recorte de MME (31 caracteres, a veces con el espacio final quitado):
    # es el MISMO aparato, así que cuenta como igual y decide la prioridad de API.
    ra, rb = sorted((str(pedido).lower(), str(candidato).lower()), key=len)
    if len(ra) in (30, 31) and len(rb) > len(ra) and rb.startswith(ra.rstrip()):
        return 1.0
    corto, largo = sorted((a, b), key=len)
    if len(corto) >= 8 and largo.startswith(corto):
        return 0.95
    # Media de palabras compartidas y parecido de letras: solo con difflib,
    # «Speakers (Steam Streaming Speakers)» y «… Microphone)» pasan del 0.8.
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return 0.5 * jaccard + 0.5 * difflib.SequenceMatcher(None, a, b).ratio()


def buscar_dispositivo(sd, nombre: str, umbral: float = 0.8) -> Optional[Tuple[int, dict, str]]:
    """
    Busca la salida que mejor coincide con `nombre` → (índice, info, api) o
    None. A igual parecido gana WASAPI, luego DirectSound y luego MME. Nunca
    WDM-KS (exclusivo) ni los alias «Sound Mapper»/«Primary Sound Driver».
    """
    if not str(nombre or "").strip():
        return None
    try:
        dispositivos = list(sd.query_devices())
        apis = [str(a.get("name", "")) for a in sd.query_hostapis()]
    except Exception:
        return None
    mejor, clave_mejor = None, None
    for i, d in enumerate(dispositivos):
        if int(d.get("max_output_channels", 0) or 0) <= 0:
            continue
        nd = str(d.get("name", ""))
        if any(nd.lower().startswith(alias) for alias in _ALIAS_POR_DEFECTO):
            continue
        h = d.get("hostapi", -1)
        api = apis[h] if isinstance(h, int) and 0 <= h < len(apis) else ""
        api_l = api.lower().replace(" ", "")
        if "wdm-ks" in api_l or "wdmks" in api_l:
            continue
        prioridad = next((p for clave, p in _PRIORIDAD_API if clave in api_l), 3)
        s = similitud_nombres(nombre, nd)
        if s < umbral:
            continue
        clave = (round(s, 3), -prioridad)
        if clave_mejor is None or clave > clave_mejor:
            mejor, clave_mejor = (i, d, api), clave
    return mejor


# ── Mezclador ──────────────────────────────────────────────────────────────────

class _Fuente:
    """Un sonido en reproducción."""
    __slots__ = ("id", "datos", "vol", "velocidad", "bucle", "canal", "pos",
                 "pausada", "terminada")

    def __init__(self, id_: int, datos: np.ndarray, vol: float, velocidad: float,
                 bucle: bool, canal: Optional[str]):
        self.id, self.datos, self.vol = id_, datos, vol
        self.velocidad, self.bucle, self.canal = velocidad, bucle, canal
        self.pos = 0.0               # en muestras del buffer (44.1 kHz)
        self.pausada = False
        self.terminada = len(datos) == 0


def _leer_fuente(f: _Fuente, frames: int, paso: float) -> Optional[np.ndarray]:
    """
    Siguientes `frames` muestras de salida de la fuente (float32 (frames, 2)),
    avanzando `paso` muestras del buffer por cada una. Marca la fuente como
    terminada si se acaba (sin bucle).
    """
    datos = f.datos
    n = len(datos)
    if n == 0 or frames <= 0:
        f.terminada = f.terminada or n == 0
        return None
    if paso == 1.0 and f.pos == int(f.pos):          # camino rápido: sin interpolar
        p = int(f.pos)
        if f.bucle:
            if p + frames <= n:
                bloque = datos[p:p + frames]
            else:
                bloque = datos[(p + np.arange(frames)) % n]
            f.pos = float((p + frames) % n)
            return bloque
        trozo = datos[p:p + frames]
        f.pos = float(p + frames)
        if f.pos >= n:
            f.terminada = True
        if len(trozo) == frames:
            return trozo
        bloque = np.zeros((frames, datos.shape[1]), np.float32)
        bloque[:len(trozo)] = trozo
        return bloque

    idx = f.pos + np.arange(frames, dtype=np.float64) * paso
    if f.bucle:
        idx = np.mod(idx, n)
        i0 = idx.astype(np.int64)
        i1 = i0 + 1
        i1[i1 >= n] = 0
        frac = (idx - i0).astype(np.float32)[:, None]
        bloque = datos[i0] * (1.0 - frac) + datos[i1] * frac
        f.pos = float((f.pos + frames * paso) % n)
        return bloque
    validos = int(np.count_nonzero(idx < n))           # idx crece: son los primeros
    bloque = np.zeros((frames, datos.shape[1]), np.float32)
    if validos:
        iv = idx[:validos]
        i0 = iv.astype(np.int64)
        i1 = np.minimum(i0 + 1, n - 1)
        frac = (iv - i0).astype(np.float32)[:, None]
        bloque[:validos] = datos[i0] * (1.0 - frac) + datos[i1] * frac
    f.pos = f.pos + frames * paso
    if f.pos >= n:
        f.terminada = True
    return bloque


class Mezclador:
    """
    Mezclador único del proceso (usa `Mezclador.instancia()`).

        m = Mezclador.instancia()
        m.set_dispositivo(cfg.get("voz", "dispositivo_salida", ""))
        buf = cargar_wav(rutas.recurso("ui_web", "assets", "sfx", "trago_1.wav"))
        sid = m.reproducir(buf, vol=0.8, canal="sfx")
        alarma = m.reproducir(cargar_wav(...), bucle=True, canal="alarma")
        m.detener(alarma)

    Todo es seguro entre hilos. Los ids son enteros crecientes.
    """

    _instancia: Optional["Mezclador"] = None
    _lock_instancia = threading.Lock()

    @classmethod
    def instancia(cls) -> "Mezclador":
        """El mezclador compartido (se crea la primera vez)."""
        with cls._lock_instancia:
            if cls._instancia is None:
                cls._instancia = cls()
            return cls._instancia

    def __init__(self, *, sd=None, winsound=None, reloj: Callable[[], float] = time.monotonic,
                 cierre_s: float = SILENCIO_CIERRE_S, vigilante: bool = True):
        self._sd_inyectado = sd
        self._sd = sd
        self._sd_fallo = False
        self._winsound = winsound
        self._reloj = reloj
        self._cierre_s = float(cierre_s)
        self._usar_vigilante = vigilante
        # Dos candados: `_lock` protege los datos y lo usa el callback de audio
        # (siempre breve); `_lock_stream` ordena abrir/cerrar el stream y nunca
        # lo toma el callback. Orden: _lock_stream → _lock, jamás al revés.
        self._lock = threading.Lock()
        self._lock_stream = threading.RLock()
        self._fuentes: "OrderedDict[int, _Fuente]" = OrderedDict()
        self._ids = itertools.count(1)
        self._vol_canal: Dict[Optional[str], float] = {}
        self._stream = None
        self._gen = 0                  # sube al cerrar: el callback de un stream viejo calla
        self._caido = False            # el finished_callback avisó: el stream actual ya no suena
        self._ultimo_callback = 0.0    # reloj de la última vez que PortAudio pidió audio
        self._reaperturas_mudas = 0    # reaperturas seguidas sin ningún callback (0 al llegar uno)
        self._sr_salida = FRECUENCIA
        self._canales_stream = CANALES_SALIDA
        self._silencio_desde: Optional[float] = None
        self._nombre_dispositivo = ""
        self._dispositivo_resuelto: Optional[str] = None
        self._hilo_vig: Optional[threading.Thread] = None
        self._fin_vig = threading.Event()
        self._ws: Optional[dict] = None           # sonido actual en modo winsound
        self._temporales: List[str] = []
        self.ultimo_error: Optional[str] = None

    # ── API pública ────────────────────────────────────────────────────────
    cargar_wav = staticmethod(cargar_wav)
    cargar_audio = staticmethod(cargar_audio)

    @property
    def modo(self) -> str:
        """'sounddevice', 'winsound' (sin mezcla) o 'ninguno'."""
        if self._modulo_sd() is not None:
            return "sounddevice"
        return "winsound" if self._modulo_winsound() is not None else "ninguno"

    @property
    def abierto(self) -> bool:
        """True mientras el stream de salida está abierto."""
        return self._stream is not None

    def reproducir(self, buf: Buffer, vol: float = 1.0, velocidad: float = 1.0,
                   bucle: bool = False, canal: Optional[str] = None) -> int:
        """
        Empieza a sonar `buf` (array de `cargar_wav`/`cargar_audio`, cualquier
        array de audio a 44.1 kHz, o una ruta) y devuelve su id. `vol` 0..4,
        `velocidad` >0 (2 = el doble de rápido y una octava más agudo). Con
        `canal`, se puede detener o bajar de volumen junto a los demás de ese
        canal.
        """
        if isinstance(buf, (str, Path)):
            buf = cargar_audio(buf, cachear=canal != "musica")
        datos = buf if (isinstance(buf, np.ndarray) and buf.dtype == np.float32
                        and buf.ndim == 2 and buf.shape[1] == 2) else a_estereo(buf)
        fuente = _Fuente(next(self._ids), datos,
                         vol=min(max(float(vol), 0.0), 4.0),
                         velocidad=min(max(float(velocidad), 0.05), 8.0),
                         bucle=bool(bucle), canal=canal)
        if fuente.terminada:
            return fuente.id                        # buffer vacío: no hay nada que sonar
        with self._lock_stream:
            if self._modulo_sd() is not None:
                with self._lock:
                    self._fuentes[fuente.id] = fuente
                    self._silencio_desde = None
                if self._asegurar_stream():
                    return fuente.id
                # Sin salida por sounddevice: lo nuevo y lo que se quedó en un
                # stream muerto pasan a winsound (la alarma antes que nada).
                self._pasar_a_winsound()
                return fuente.id
            self._reproducir_winsound(fuente)
        return fuente.id

    def detener(self, id_: int) -> None:
        """Para un sonido (si ya terminó, no pasa nada)."""
        with self._lock:
            if self._fuentes.pop(id_, None) is not None:
                self._marcar_silencio()
                return
        if self._ws and self._ws["id"] == id_:
            self._parar_winsound()

    def detener_canal(self, canal: str) -> None:
        """Para todos los sonidos de un canal ('alarma', 'sfx', 'musica')."""
        with self._lock:
            for i in [i for i, f in self._fuentes.items() if f.canal == canal]:
                del self._fuentes[i]
            self._marcar_silencio()
        if self._ws and self._ws["canal"] == canal:
            self._parar_winsound()

    def detener_todo(self) -> None:
        """Silencio total."""
        with self._lock:
            self._fuentes.clear()
            self._marcar_silencio()
        if self._ws:
            self._parar_winsound()

    def activo(self, id_: int) -> bool:
        """True mientras el sonido `id_` sigue sonando (o está en pausa)."""
        with self._lock:
            f = self._fuentes.get(id_)
            if f is not None:
                return not f.terminada
        ws = self._ws
        if ws and ws["id"] == id_:
            return ws["bucle"] or self._reloj() - ws["t0"] < ws["dur"]
        return False

    def posicion(self, id_: int) -> Optional[float]:
        """Segundos reproducidos del sonido `id_` (en bucle, dentro de la vuelta). None si no suena."""
        with self._lock:
            f = self._fuentes.get(id_)
            if f is not None:
                return f.pos / FRECUENCIA
        ws = self._ws
        if ws and ws["id"] == id_:
            t = (self._reloj() - ws["t0"]) * ws["velocidad"]
            total = ws["dur"] * ws["velocidad"]
            if ws["bucle"] and total > 0:
                return t % total
            return t if t < total else None
        return None

    def pausar(self, id_: int, pausado: bool = True) -> None:
        """Pausa o reanuda un sonido sin perder su posición."""
        with self._lock:
            f = self._fuentes.get(id_)
            if f is None:
                return
            f.pausada = bool(pausado)
            if f.pausada:
                self._marcar_silencio()
            else:
                self._silencio_desde = None
            reabrir = not f.pausada
        if reabrir:
            with self._lock_stream:
                if self._modulo_sd() is not None and not self._asegurar_stream():
                    self.ultimo_error = self.ultimo_error or "No se pudo reabrir el audio."
                    self._pasar_a_winsound()

    def set_volumen(self, id_: int, vol: float) -> None:
        """Cambia el volumen de un sonido que ya suena."""
        with self._lock:
            f = self._fuentes.get(id_)
            if f is not None:
                f.vol = min(max(float(vol), 0.0), 4.0)

    def set_volumen_canal(self, canal: Optional[str], vol: float) -> None:
        """Volumen de todo un canal (se multiplica por el de cada sonido)."""
        with self._lock:
            self._vol_canal[canal] = min(max(float(vol), 0.0), 4.0)

    def set_dispositivo(self, nombre: Optional[str]) -> Optional[str]:
        """
        Elige la salida por nombre (el de `voz.dispositivo_salida`; vacío = la
        del sistema). Devuelve el nombre de PortAudio que se usará, o None si
        no se encontró (se usa la salida del sistema). Si algo suena, se pasa
        al nuevo dispositivo sin cortarse.
        """
        with self._lock_stream:
            self._nombre_dispositivo = str(nombre or "").strip()
            sd = self._modulo_sd()
            encontrado = buscar_dispositivo(sd, self._nombre_dispositivo) if sd else None
            self._dispositivo_resuelto = str(encontrado[1].get("name")) if encontrado else None
            if self._stream is not None:
                self._cerrar_stream()
                with self._lock:
                    hay = self._sonando()
                if hay and not self._asegurar_stream():
                    self._pasar_a_winsound()
            return self._dispositivo_resuelto

    def revisar_cierre(self) -> bool:
        """
        Cierra el stream si lleva `cierre_s` segundos sin nada sonando. Lo
        llama el vigilante cada medio segundo. True si queda cerrado.

        También vigila que el stream siga vivo: si murió (dispositivo perdido:
        `active` en False, el finished_callback avisó, o hay algo sonando y el
        callback lleva `CALLBACK_MUDO_S` sin correr), lo cierra y lo reabre; si
        no se puede, lo que sonaba pasa a winsound.
        """
        with self._lock_stream:
            if self._stream is not None and not self._stream_sano():
                self._cerrar_stream()
                with self._lock:
                    hay = self._sonando()
                    self._reaperturas_mudas += 1
                    insistir = self._reaperturas_mudas <= MAX_REAPERTURAS_MUDAS
                if hay and insistir:
                    log.warning("Mezclador: la salida de audio dejó de responder "
                                "(¿dispositivo desconectado?); la reabro.")
                if hay and not (insistir and self._asegurar_stream()):
                    if not insistir:
                        self.ultimo_error = ("La salida de audio no responde; "
                                             "sigo con winsound (sin mezcla).")
                        log.warning("Mezclador: %s", self.ultimo_error)
                    self._pasar_a_winsound()
                return self._stream is None
            with self._lock:
                if self._stream is None:
                    return True
                if self._sonando() or self._silencio_desde is None:
                    return False
                if self._reloj() - self._silencio_desde < self._cierre_s:
                    return False
            self._cerrar_stream()
            return True

    def cerrar(self) -> None:
        """Para todo, cierra el stream y borra los WAV temporales."""
        self.detener_todo()
        with self._lock_stream:
            self._cerrar_stream()
            self._fin_vig.set()
        self._limpiar_temporales(todos=True)

    # ── sounddevice ────────────────────────────────────────────────────────
    def _modulo_sd(self):
        if self._sd is None and not self._sd_fallo:
            try:
                import sounddevice
                self._sd = sounddevice
            except Exception as e:           # falta el paquete o PortAudio
                self._sd_fallo = True
                self.ultimo_error = f"sounddevice no disponible: {e}"
                log.info("Mezclador: %s; uso winsound", self.ultimo_error)
        return self._sd

    def _sonando(self) -> bool:
        return any(not f.pausada and not f.terminada for f in self._fuentes.values())

    def _marcar_silencio(self) -> None:
        """Con `_lock`: si ya no suena nada, apunta desde cuándo."""
        if self._silencio_desde is None and not self._sonando():
            self._silencio_desde = self._reloj()

    def _intentos(self, sd) -> List[Tuple[Optional[int], int, Optional[object]]]:
        """(dispositivo, frecuencia, extra_settings) a probar, en orden."""
        intentos: List[Tuple[Optional[int], int, Optional[object]]] = []
        encontrado = buscar_dispositivo(sd, self._nombre_dispositivo) if self._nombre_dispositivo else None
        if encontrado:
            idx, info, api = encontrado
            extra = None
            if "wasapi" in api.lower():
                try:                          # WASAPI compartido remuestrea a 44.1k él mismo
                    extra = sd.WasapiSettings(auto_convert=True)
                except Exception:
                    extra = None
            intentos.append((idx, FRECUENCIA, extra))
            sr_nativa = int(float(info.get("default_samplerate", 0) or 0))
            if sr_nativa and sr_nativa != FRECUENCIA:
                intentos.append((idx, sr_nativa, None))
        intentos.append((None, FRECUENCIA, None))       # la salida del sistema
        return intentos

    def _stream_vivo(self) -> bool:
        """¿El stream abierto sigue sonando? No si el finished_callback avisó o
        si PortAudio lo da por inactivo (`active` en False: dispositivo perdido)."""
        stream = self._stream
        if stream is None or self._caido:
            return False
        try:
            return getattr(stream, "active", True) is not False
        except Exception:                  # PortAudioError: el stream ya no es válido
            return False

    def _stream_sano(self) -> bool:
        """`_stream_vivo` y, además, si hay algo sonando, que el callback haya
        corrido en los últimos `CALLBACK_MUDO_S` (algunos backends dejan de
        llamarlo sin marcarlo inactivo)."""
        if not self._stream_vivo():
            return False
        with self._lock:
            mudo = self._sonando() and self._reloj() - self._ultimo_callback > CALLBACK_MUDO_S
        return not mudo

    def _asegurar_stream(self) -> bool:
        """Con `_lock_stream`: abre el stream si no lo está, o lo reabre si el
        que hay murió (dispositivo perdido). False si no se pudo."""
        if self._stream is not None:
            if self._stream_vivo():
                return True
            log.warning("Mezclador: el stream de salida murió (¿dispositivo desconectado?); lo reabro.")
            self._cerrar_stream()
        sd = self._modulo_sd()
        if sd is None:
            return False
        errores = []
        for dispositivo, sr, extra in self._intentos(sd):
            with self._lock:
                self._gen += 1
                gen = self._gen
                self._sr_salida = sr
                self._caido = False
            kw = dict(samplerate=sr, channels=CANALES_SALIDA, dtype="float32",
                      device=dispositivo, callback=self._crear_callback(gen),
                      finished_callback=self._crear_fin(gen))
            if extra is not None:
                kw["extra_settings"] = extra
            stream = None
            try:
                stream = sd.OutputStream(**kw)
                stream.start()
            except Exception as e:
                errores.append(f"{dispositivo}@{sr}: {e}")
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                continue
            with self._lock:
                if gen != self._gen or self._caido:
                    # Murió al arrancar (el finished_callback ya avisó): el siguiente.
                    errores.append(f"{dispositivo}@{sr}: se paró al arrancar")
                    self._caido = False
                    muerto = True
                else:
                    muerto = False
                    self._stream = stream
                    self._ultimo_callback = self._reloj()
                    if self._sonando():
                        self._silencio_desde = None
                    else:
                        self._marcar_silencio()
            if muerto:
                for metodo in ("stop", "close"):
                    try:
                        getattr(stream, metodo)()
                    except Exception:
                        pass
                continue
            self._arrancar_vigilante()
            return True
        self.ultimo_error = "No se pudo abrir la salida de audio: " + " | ".join(errores)
        log.warning("Mezclador: %s", self.ultimo_error)
        return False

    def _cerrar_stream(self) -> None:
        """Con `_lock_stream`: suelta el dispositivo (fuera de `_lock`, porque
        stop() espera a que termine el callback y el callback usa `_lock`)."""
        with self._lock:
            stream, self._stream = self._stream, None
            self._gen += 1
            self._caido = False
        if stream is None:
            return
        for metodo in ("stop", "close"):
            try:
                getattr(stream, metodo)()
            except Exception:
                pass

    def _pasar_a_winsound(self) -> None:
        """Con `_lock_stream`: no hay salida por sounddevice. Lo que estaba
        sonando (también lo que se quedó en un stream muerto) sale de la mezcla
        y UNO sigue por winsound, que no mezcla: la alarma si la hay; si no, el
        último que empezó. Lo pausado se queda, por si vuelve a haber salida."""
        with self._lock:
            vivas = [f for f in self._fuentes.values() if not f.terminada and not f.pausada]
            for f in vivas:
                del self._fuentes[f.id]
            self._marcar_silencio()
        if not vivas:
            return
        f = next((x for x in reversed(vivas) if x.canal == "alarma"), vivas[-1])
        if not f.bucle and f.pos > 0:                      # sigue por donde iba
            f = _Fuente(f.id, f.datos[int(f.pos):], f.vol, f.velocidad, f.bucle, f.canal)
            if f.terminada:
                return
        self._reproducir_winsound(f)

    def _crear_fin(self, gen: int):
        """finished_callback de PortAudio: el stream `gen` dejó de sonar. Si no
        lo paramos nosotros (al cerrar sube `_gen`), es que murió."""
        def fin():
            if gen == self._gen:
                self._caido = True
        return fin

    def _crear_callback(self, gen: int):
        def callback(outdata, frames, _tiempo, _estado):
            try:
                with self._lock:
                    if gen != self._gen:
                        outdata.fill(0)
                        return
                    self._ultimo_callback = self._reloj()
                    self._reaperturas_mudas = 0
                    mezcla = self._mezclar(frames)
                if outdata.shape[1] == mezcla.shape[1]:
                    outdata[:] = mezcla
                else:
                    outdata[:] = mezcla.mean(axis=1, keepdims=True)
            except Exception:              # nunca tumbar el stream por un sonido raro
                outdata.fill(0)
        return callback

    def _mezclar(self, frames: int) -> np.ndarray:
        """Con `_lock`: suma las fuentes activas → float32 (frames, 2) recortado."""
        mezcla = np.zeros((frames, CANALES_SALIDA), np.float32)
        paso_base = FRECUENCIA / float(self._sr_salida)
        terminadas = []
        for f in self._fuentes.values():
            if f.pausada:
                continue
            bloque = _leer_fuente(f, frames, f.velocidad * paso_base)
            g = f.vol * self._vol_canal.get(f.canal, 1.0)
            if bloque is not None and g > 0.0:
                if g == 1.0:
                    mezcla += bloque
                else:
                    mezcla += bloque * np.float32(g)
            if f.terminada:
                terminadas.append(f.id)
        for i in terminadas:
            del self._fuentes[i]
        if terminadas:
            self._marcar_silencio()
        np.clip(mezcla, -1.0, 1.0, out=mezcla)
        return mezcla

    def _arrancar_vigilante(self) -> None:
        """Con `_lock_stream`: hilo que cierra el stream tras el silencio."""
        if not self._usar_vigilante:
            return
        if self._hilo_vig is not None and self._hilo_vig.is_alive():
            return
        self._fin_vig = threading.Event()
        fin = self._fin_vig

        def vigilar():
            while not fin.wait(0.5):
                with self._lock_stream:
                    if self.revisar_cierre():
                        self._hilo_vig = None
                        return

        self._hilo_vig = threading.Thread(target=vigilar, name="LuneMezcladorVigilante", daemon=True)
        self._hilo_vig.start()

    # ── winsound (sin mezcla) ──────────────────────────────────────────────
    def _modulo_winsound(self):
        if self._winsound is None and sys.platform == "win32":
            try:
                import winsound
                self._winsound = winsound
            except Exception:
                self._winsound = None
        return self._winsound

    def _reproducir_winsound(self, f: _Fuente) -> bool:
        """Plan B: WAV temporal por PlaySound. Corta lo que sonara antes."""
        ws = self._modulo_winsound()
        if ws is None:
            self.ultimo_error = self.ultimo_error or "No hay ninguna salida de audio disponible."
            return False
        datos = f.datos
        if f.velocidad != 1.0:
            datos = remuestrear(datos, FRECUENCIA, max(1, int(round(FRECUENCIA / f.velocidad))))
        g = f.vol * self._vol_canal.get(f.canal, 1.0)
        pcm = (np.clip(datos * g, -1.0, 1.0) * 32767.0).astype("<i2")
        try:
            fd, ruta = tempfile.mkstemp(prefix="lune_mezclador_", suffix=".wav")
            os.close(fd)
            with wave.open(ruta, "wb") as w:
                w.setnchannels(CANALES_SALIDA)
                w.setsampwidth(2)
                w.setframerate(FRECUENCIA)
                w.writeframes(pcm.tobytes())
        except OSError as e:
            self.ultimo_error = f"No pude preparar el sonido: {e}"
            return False
        flags = ws.SND_FILENAME | ws.SND_ASYNC | getattr(ws, "SND_NODEFAULT", 0)
        if f.bucle:
            flags |= ws.SND_LOOP
        try:
            ws.PlaySound(ruta, flags)
        except Exception as e:
            self.ultimo_error = f"winsound no pudo sonar: {e}"
            self._temporales.append(ruta)
            self._limpiar_temporales()
            return False
        anterior = self._ws
        self._ws = {"id": f.id, "t0": self._reloj(), "dur": len(datos) / FRECUENCIA,
                    "bucle": f.bucle, "canal": f.canal, "velocidad": f.velocidad, "ruta": ruta}
        if anterior:
            self._temporales.append(anterior["ruta"])
        self._limpiar_temporales()
        return True

    def _parar_winsound(self) -> None:
        ws = self._modulo_winsound()
        if ws is not None:
            try:
                ws.PlaySound(None, 0)
            except Exception:
                pass
        if self._ws:
            self._temporales.append(self._ws["ruta"])
        self._ws = None
        self._limpiar_temporales()

    def _limpiar_temporales(self, todos: bool = False) -> None:
        if todos and self._ws:
            self._temporales.append(self._ws["ruta"])
            self._ws = None
        quedan = []
        for ruta in self._temporales:
            try:
                os.remove(ruta)
            except FileNotFoundError:
                pass
            except OSError:
                quedan.append(ruta)      # Windows aún lo tiene abierto: otra vez será
        self._temporales = quedan
