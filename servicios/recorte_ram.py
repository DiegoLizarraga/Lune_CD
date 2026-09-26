"""
servicios/recorte_ram.py — Liberar memoria de Lune (el MemoryTrim de Mate-Engine).

`recortar()` hace lo mismo que MemoryTrim.TrimRoutine: recolecta basura y le
pide a Windows que vacíe el working set (EmptyWorkingSet) — pero SOLO de los
procesos de Lune: el propio y sus QtWebEngineProcess (`win_pantalla.pids_propios`),
abiertos con PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION (nada de leer ni
escribir memoria). Las páginas vuelven solas cuando hacen falta: el efecto es
que Lune ocupa menos RAM física mientras juegas, a cambio de un pequeño tirón
al volver. Por eso se usa al entrar en modo juego, a mano («Liberar memoria») y,
si se activa `sistema.recorte_ram_auto`, con `ProgramadorRecorte`.

`gc.collect()` solo se hace en el hilo principal (el de Qt): recolectar en otro
hilo podría destruir objetos de Qt fuera de su hilo. Quien lo llame desde un
hilo aparte debe recolectar antes en el suyo (ui/modo_juego_qt lo hace).

Fuera de Windows solo recolecta y mide.
"""
from __future__ import annotations

import ctypes
import gc
import sys
import threading
import time
from typing import Callable, Optional, Tuple

from servicios import win_pantalla as wp

PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400
ACCESO_RECORTE = PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION
MB = 1024 * 1024


def _dlls(psapi, kernel32):
    """Las DLL reales (con firmas) si no se inyectan; (None, None) fuera de Windows."""
    if psapi is not None and kernel32 is not None:
        return psapi, kernel32
    if sys.platform != "win32":
        return None, None
    from ctypes import wintypes
    try:
        k = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
        p = psapi or ctypes.WinDLL("psapi", use_last_error=True)
        if kernel32 is None:
            k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k.OpenProcess.restype = wintypes.HANDLE
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            k.CloseHandle.restype = wintypes.BOOL
        if psapi is None:
            p.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            p.EmptyWorkingSet.restype = wintypes.BOOL
        return p, k
    except Exception:
        return None, None


def _rss_total(pids, ps) -> float:
    total = 0
    for pid in pids:
        try:
            total += int(ps.Process(pid).memory_info().rss)
        except Exception:
            continue
    return total / MB


def recortar(*, pids=None, psapi=None, kernel32=None, psutil_mod=None,
             recolectar: Optional[bool] = None) -> Tuple[float, float]:
    """
    Recolecta basura y vacía el working set de los procesos de Lune. Devuelve la
    RAM física (MB, suma de RSS) antes y después. Nunca lanza: un proceso que no
    se deja abrir o que ya no existe se salta. `recolectar=None`: gc.collect solo
    si se llama desde el hilo principal.
    """
    ps = psutil_mod
    if ps is None:
        try:
            import psutil as ps
        except Exception:
            ps = None
    try:
        objetivos = wp.pids_propios(pids, ps)
    except Exception:
        objetivos = []
    antes = _rss_total(objetivos, ps) if ps is not None else 0.0
    if recolectar is None:
        recolectar = threading.current_thread() is threading.main_thread()
    if recolectar:
        try:
            gc.collect()
        except Exception:
            pass
    p, k = _dlls(psapi, kernel32)
    if p is not None and k is not None:
        for pid in objetivos:
            h = None
            try:
                h = k.OpenProcess(ACCESO_RECORTE, False, int(pid))
                if h:
                    p.EmptyWorkingSet(h)
            except Exception:
                pass
            finally:
                if h:
                    try:
                        k.CloseHandle(h)
                    except Exception:
                        pass
    despues = _rss_total(objetivos, ps) if ps is not None else 0.0
    return (round(antes, 1), round(despues, 1))


class ProgramadorRecorte:
    """
    Cuándo toca recortar con `sistema.recorte_ram_auto` (como MemoryTrim de ME):
    a los 0, 10 y 15 s de activarlo y luego cada 600 s. Quien lo usa llama a
    `toca(animando)` de vez en cuando (cada 2 s) y recorta si devuelve True.
    Mientras la mascota anima (arrastre, baile, pantalla grande…) no toca: el
    recorte provoca tirones; lo pendiente se hace en cuanto deje de animar.
    """

    PASOS_S = (0, 10, 15)
    PERIODO_S = 600

    def __init__(self, reloj: Callable[[], float] = time.monotonic):
        self._reloj = reloj
        self._activo = False
        self._t0 = 0.0
        self._pasos: list = []
        self._siguiente = 0.0

    @property
    def activo(self) -> bool:
        return self._activo

    def activar(self, on: bool) -> None:
        on = bool(on)
        if on == self._activo:
            return
        self._activo = on
        if on:
            self._t0 = self._reloj()
            self._pasos = list(self.PASOS_S)
            self._siguiente = self._t0 + self.PERIODO_S
        else:
            self._pasos = []

    def toca(self, animando: bool = False) -> bool:
        """¿Toca recortar ahora? (consume el paso o el periodo que tocaba)."""
        if not self._activo or animando:
            return False
        ahora = self._reloj()
        transcurrido = ahora - self._t0
        vencidos = [p for p in self._pasos if transcurrido >= p]
        if vencidos:
            self._pasos = [p for p in self._pasos if transcurrido < p]
            return True
        if ahora >= self._siguiente:
            # Tras una suspensión larga no se encadenan recortes: el siguiente, en un periodo.
            self._siguiente = ahora + self.PERIODO_S
            return True
        return False
