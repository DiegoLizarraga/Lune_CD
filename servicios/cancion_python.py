"""
servicios/cancion_python.py — La canción de un baile sonando desde Python.

Para las mascotas que no tienen página que la reproduzca (sprites) o que no
saben reproducir bailes (D1: «equivalente mínimo»): la canción suena por el
Mezclador (servicios/mezclador.py, canal `musica`, que no se cachea) y Lune
hace el baile procedural al pulso analizado de esa canción
(nucleo.bailes.Biblioteca.analizar_pulso). La patata la usa igual.

Memoria: el Mezclador trabaja con float32 estéreo a 44.1 kHz, ~21 MB por
minuto. Por eso hay un tope (`MAX_DURACION_S`, 10 min) y la decodificación se
corta ahí con `-t` en ffmpeg: una mezcla de una hora nunca llega a ocupar 1 GB.
Al parar o liberar se suelta el buffer.

    r = ReproductorCancion()
    r.cargar(ruta, al_listo)          # en su hilo; al_listo(ok, texto) desde ese hilo
    r.reproducir(0.25)                # → Mezclador.reproducir(buf, vol, canal="musica")
    r.posicion(); r.pausar(True); r.volumen(0.5); r.terminado; r.parar(); r.liberar()

Sin Qt; el Mezclador, el cargador, el reloj y el hilo son inyectables.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

_log = logging.getLogger("lune.cancion")

MAX_DURACION_S = 600                    # decodificar a float32 estéreo son ~21 MB por minuto
FRECUENCIA = 44100
TIEMPO_FFMPEG_S = 120.0


class ErrorCancion(Exception):
    """Error al cargar la canción, con un texto apto para el usuario."""


def _sin_ventana() -> dict:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def _ejecutar_defecto() -> Callable:
    """ffmpeg que se puede matar (nucleo.bailes.ejecutar_proceso): al detener el reproductor y
    al salir de Lune no sigue decodificando solo (hasta 120 s)."""
    try:
        from nucleo.bailes import ejecutar_proceso
        return ejecutar_proceso
    except Exception:
        return subprocess.run


def cargar_cancion(ruta: Any, *, ffmpeg: Optional[str] = None, ejecutar: Optional[Callable] = None,
                   max_s: float = MAX_DURACION_S, timeout: float = TIEMPO_FFMPEG_S, **_kw) -> np.ndarray:
    """La canción como float32 (N, 2) a 44.1 kHz, decodificando COMO MUCHO `max_s` + 1 s
    (así se sabe si se pasa del tope sin gastar la memoria de toda la canción).

    Con ffmpeg (el de imageio-ffmpeg): cualquier formato. Sin ffmpeg: solo WAV, mirando
    antes la duración en su cabecera. ErrorCancion con texto si no se puede."""
    p = Path(ruta)
    if not p.is_file():
        raise ErrorCancion(f"No encuentro la canción: {p.name}")
    exe = ffmpeg
    if exe is None:
        try:
            from servicios.mezclador import ruta_ffmpeg
            exe = ruta_ffmpeg()
        except Exception:
            exe = None
    if exe:
        cmd = [exe, "-nostdin", "-v", "error", "-i", str(p), "-vn", "-map", "0:a:0", "-map_metadata", "-1",
               "-t", f"{float(max_s) + 1.0:g}", "-ac", "2", "-ar", str(FRECUENCIA),
               "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
        try:
            r = (ejecutar or _ejecutar_defecto())(cmd, capture_output=True, timeout=timeout, **_sin_ventana())
        except subprocess.TimeoutExpired as e:
            raise ErrorCancion(f"ffmpeg tardó demasiado en leer {p.name}.") from e
        except OSError as e:
            raise ErrorCancion(f"No pude ejecutar ffmpeg: {e}") from e
        if getattr(r, "returncode", 1) != 0:
            err = (getattr(r, "stderr", b"") or b"").decode("utf-8", "replace").strip().splitlines()
            raise ErrorCancion(f"ffmpeg no pudo leer {p.name}: {err[-1] if err else 'error'}"[:300])
        raw = getattr(r, "stdout", b"") or b""
        n = len(raw) // 8
        if n == 0:
            raise ErrorCancion(f"{p.name} no tiene audio.")
        return np.frombuffer(raw[: n * 8], dtype="<f4").reshape(-1, 2)
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                if w.getframerate() > 0 and w.getnframes() / w.getframerate() > max_s + 1.0:
                    raise ErrorCancion(f"La canción dura más de {int(max_s // 60)} minutos.")
        except (wave.Error, EOFError):
            pass                                        # WAV float o raro: lo mira cargar_wav
        from servicios.mezclador import ErrorAudio, cargar_wav
        try:
            return cargar_wav(p, cachear=False)
        except ErrorAudio as e:
            raise ErrorCancion(str(e)) from e
    raise ErrorCancion("Para esta canción hace falta ffmpeg (pip install imageio-ffmpeg).")


class ReproductorCancion:
    """Una canción cargada y sonando por el Mezclador (ver la cabecera del módulo)."""

    def __init__(self, mezclador: Any = None, *, cargar: Optional[Callable[..., Any]] = None,
                 reloj: Callable[[], float] = time.monotonic, hilo: bool = True):
        self._mezclador = mezclador
        self._cargar = cargar or cargar_cancion
        self._reloj = reloj
        self._hilo = bool(hilo)
        self._lock = threading.Lock()
        self._gen = 0
        self._buf: Optional[np.ndarray] = None
        self._id: Optional[int] = None
        self._pausado = False
        self._vol = 1.0
        self.duracion: float = 0.0
        self.ruta: Optional[Path] = None
        self.error = ""

    # ── Mezclador ────────────────────────────────────────────────────────────────
    def _mez(self) -> Any:
        if self._mezclador is None:
            from servicios.mezclador import Mezclador
            self._mezclador = Mezclador.instancia()
        return self._mezclador

    # ── Carga ────────────────────────────────────────────────────────────────────
    def cargar(self, ruta: Any, al_listo: Callable[[bool, str], None]) -> None:
        """Decodifica `ruta` en su hilo y llama a `al_listo(ok, texto)` (desde ese hilo).
        Más de MAX_DURACION_S → (False, «…»). Una carga nueva (o `liberar`) deja sin
        efecto la anterior: su `al_listo` ya no se llama."""
        self.parar()
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._buf = None
            self.duracion = 0.0
            self.ruta = Path(ruta)
            self.error = ""

        def trabajo() -> None:
            ok, texto, buf, dur = False, "", None, 0.0
            try:
                buf = self._cargar(Path(ruta), cachear=False)
                buf = np.asarray(buf)
                if buf.ndim != 2 or buf.shape[1] != 2 or buf.dtype != np.float32:
                    from servicios.mezclador import a_estereo
                    buf = a_estereo(buf)
                dur = len(buf) / float(FRECUENCIA)
                if dur > MAX_DURACION_S + 0.5:
                    buf = None
                    texto = f"La canción dura más de {MAX_DURACION_S // 60} minutos: aquí no la puedo poner."
                elif dur <= 0:
                    buf = None
                    texto = "La canción está vacía."
                else:
                    ok = True
            except Exception as e:                               # noqa: BLE001
                texto = str(e)[:300] or "No pude cargar la canción."
                buf = None
            with self._lock:
                if gen != self._gen:
                    return                                       # otra carga o liberar(): se descarta
                self._buf = buf
                self.duracion = dur if ok else 0.0
                self.error = "" if ok else texto
            try:
                al_listo(ok, texto)
            except Exception:
                _log.exception("cancion: al_listo falló")

        if self._hilo:
            threading.Thread(target=trabajo, name="lune-cancion", daemon=True).start()
        else:
            trabajo()

    @property
    def cargada(self) -> bool:
        return self._buf is not None

    # ── Reproducción ─────────────────────────────────────────────────────────────
    def reproducir(self, vol: float) -> bool:
        """Empieza desde el principio (también para repetir). False si no hay canción."""
        buf = self._buf
        if buf is None:
            return False
        self.parar()
        self._vol = _vol(vol)
        try:
            self._id = self._mez().reproducir(buf, vol=self._vol, canal="musica")
        except Exception as e:                                   # noqa: BLE001
            self.error = f"No pude ponerla: {e}"[:300]
            self._id = None
            return False
        self._pausado = False
        return True

    def pausar(self, on: bool) -> None:
        self._pausado = bool(on)
        if self._id is not None:
            try:
                self._mez().pausar(self._id, bool(on))
            except Exception:
                _log.debug("cancion: no pude pausar", exc_info=True)

    def parar(self) -> None:
        i, self._id = self._id, None
        self._pausado = False
        if i is not None:
            try:
                self._mez().detener(i)
            except Exception:
                _log.debug("cancion: no pude parar", exc_info=True)

    def volumen(self, v: float) -> None:
        self._vol = _vol(v)
        if self._id is not None:
            try:
                self._mez().set_volumen(self._id, self._vol)
            except Exception:
                pass

    def posicion(self) -> Optional[float]:
        """Segundos sonados (None si no suena o ya acabó)."""
        if self._id is None:
            return None
        try:
            return self._mez().posicion(self._id)
        except Exception:
            return None

    @property
    def sonando(self) -> bool:
        return self._id is not None and not self._pausado and not self.terminado

    @property
    def pausado(self) -> bool:
        return self._id is not None and self._pausado

    @property
    def terminado(self) -> bool:
        """True cuando la canción empezó y el Mezclador ya la dio por acabada."""
        if self._id is None:
            return False
        try:
            return not self._mez().activo(self._id)
        except Exception:
            return True

    def liberar(self) -> None:
        """Para y suelta el buffer (y deja sin efecto una carga en curso)."""
        self.parar()
        with self._lock:
            self._gen += 1
            self._buf = None
            self.duracion = 0.0


def _vol(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 1.0
    if f != f:                                                   # NaN
        return 1.0
    return max(0.0, min(1.0, f))


__all__ = ("ReproductorCancion", "cargar_cancion", "ErrorCancion", "MAX_DURACION_S")
