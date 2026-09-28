"""
servicios/instancia_patata.py — Una sola patata (Lune en la terminal) a la vez.

POR QUÉ
-------
La app de ventanas no se abre dos veces (main._ya_hay_una_instancia, con un
QLocalServer), pero patata no carga Qt. Sin esto, la patata que arrancó con Windows
y un doble clic en iniciar_lune.vbs (o en lune_patata.bat) daban DOS terminales con
Lune, las dos escribiendo en memoria.json.

CÓMO
----
- Mutex con nombre `Local\\Lune_CD_Patata` (servicios/mutex_win.MutexNombrado): lo
  tiene la patata viva mientras corre. Una segunda patata no lo consigue y se va.
- Evento con nombre `Local\\Lune_CD_Patata_Mostrar`: lo crea la patata viva y un
  hilo suyo lo espera. Quien la encuentra (otra patata, o main.py en modo patata)
  lo señala con `pedir_mostrar()`: la viva trae su consola al frente (si Windows lo
  deja; si no, parpadea) y dice que sigue ahí. Si el evento existe es que hay una
  patata viva: `pedir_mostrar()` sirve también para saberlo sin tocar el mutex.
- `AllowSetForegroundWindow(ASFW_ANY)` antes de señalar: quien acaba de abrir Lune
  (con el foco) le cede el permiso de ponerse delante.

    inst = InstanciaPatata()
    if not inst.adquirir():               # ya hay una
        inst.pedir_mostrar()
        return
    inst.escuchar(lambda: traer_consola_al_frente())
    ...
    inst.liberar()

Sin Qt. Fuera de Windows no hay nada que mirar: siempre se adquiere y nadie avisa.
La API (`ApiEventoWin32`) y el mutex son inyectables; los nombres también (los tests
usan unos propios para no tocar una patata de verdad).
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable, Optional

from servicios.mutex_win import WAIT_OBJECT_0, MutexNombrado

_log = logging.getLogger("lune.patata")

NOMBRE_MUTEX = "Local\\Lune_CD_Patata"
NOMBRE_EVENTO = "Local\\Lune_CD_Patata_Mostrar"

_EVENT_MODIFY_STATE = 0x0002
_SYNCHRONIZE = 0x00100000
_ASFW_ANY = -1
_SW_RESTORE = 9
ESPERA_MS = 500                    # el hilo que escucha mira si debe parar cada medio segundo


class ApiEventoWin32:
    """kernel32/user32 con ctypes (las DLL se pueden inyectar)."""

    def __init__(self, kernel32: Any = None, user32: Any = None):
        k = kernel32 if kernel32 is not None else ctypes.WinDLL("kernel32", use_last_error=True)
        u = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.restype = wintypes.HANDLE
        k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.OpenEventW.restype = wintypes.HANDLE
        k.SetEvent.argtypes = [wintypes.HANDLE]
        k.SetEvent.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.GetConsoleWindow.argtypes = []
        k.GetConsoleWindow.restype = wintypes.HWND
        u.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        u.AllowSetForegroundWindow.restype = wintypes.BOOL
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsIconic.restype = wintypes.BOOL
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        self._k, self._u = k, u

    def crear(self, nombre: str) -> int:
        """El evento (de reinicio automático, sin señalar). 0 si falla."""
        return int(self._k.CreateEventW(None, False, False, nombre) or 0)

    def abrir(self, nombre: str) -> int:
        """El evento de otro, para señalarlo. 0 si no existe (no hay patata viva)."""
        return int(self._k.OpenEventW(_EVENT_MODIFY_STATE | _SYNCHRONIZE, False, nombre) or 0)

    def senalar(self, h: int) -> bool:
        return bool(self._k.SetEvent(h))

    def esperar(self, h: int, ms: int) -> int:
        return int(self._k.WaitForSingleObject(h, int(ms))) & 0xFFFFFFFF

    def cerrar(self, h: int) -> None:
        self._k.CloseHandle(h)

    def permitir_primer_plano(self) -> None:
        self._u.AllowSetForegroundWindow(wintypes.DWORD(_ASFW_ANY & 0xFFFFFFFF))

    def traer_consola(self) -> bool:
        """La consola de ESTE proceso al frente (restaurada si estaba minimizada)."""
        hwnd = self._k.GetConsoleWindow()
        if not hwnd:
            return False
        if self._u.IsIconic(hwnd):
            self._u.ShowWindow(hwnd, _SW_RESTORE)
        return bool(self._u.SetForegroundWindow(hwnd))


class ApiEventoNula:
    """Fuera de Windows: no hay eventos con nombre ni consola que traer."""

    def crear(self, nombre: str) -> int:
        return 0

    def abrir(self, nombre: str) -> int:
        return 0

    def senalar(self, h: int) -> bool:
        return False

    def esperar(self, h: int, ms: int) -> int:
        return 0xFFFFFFFF

    def cerrar(self, h: int) -> None:
        pass

    def permitir_primer_plano(self) -> None:
        pass

    def traer_consola(self) -> bool:
        return False


def api_defecto() -> Any:
    if sys.platform != "win32":
        return ApiEventoNula()
    try:
        return ApiEventoWin32()
    except (OSError, AttributeError):
        return ApiEventoNula()


def pedir_mostrar(api: Any = None, nombre_evento: str = NOMBRE_EVENTO) -> bool:
    """Si hay una patata viva, le pide que traiga su consola al frente. True si la había
    (el evento existe solo mientras vive una)."""
    api = api if api is not None else api_defecto()
    try:
        h = api.abrir(nombre_evento)
    except Exception:
        return False
    if not h:
        return False
    try:
        try:
            api.permitir_primer_plano()
        except Exception:
            pass
        api.senalar(h)
    except Exception:
        _log.debug("patata: no pude avisar a la patata viva", exc_info=True)
    finally:
        try:
            api.cerrar(h)
        except Exception:
            pass
    return True


def patata_viva(api: Any = None, nombre_evento: str = NOMBRE_EVENTO) -> bool:
    """¿Hay una patata corriendo? Sin avisarla ni tocar su mutex."""
    api = api if api is not None else api_defecto()
    try:
        h = api.abrir(nombre_evento)
    except Exception:
        return False
    if not h:
        return False
    try:
        api.cerrar(h)
    except Exception:
        pass
    return True


def traer_consola_al_frente(api: Any = None) -> bool:
    """La consola de este proceso delante. False si no se pudo (Windows no deja robar
    el foco, o no hay consola): quien llama la hace parpadear."""
    api = api if api is not None else api_defecto()
    try:
        return bool(api.traer_consola())
    except Exception:
        return False


class InstanciaPatata:
    """El mutex de instancia única de patata y su aviso «muéstrate» (ver el módulo)."""

    def __init__(self, *, mutex: Any = None, api: Any = None, nombre_mutex: str = NOMBRE_MUTEX,
                 nombre_evento: str = NOMBRE_EVENTO):
        self._mutex = mutex if mutex is not None else MutexNombrado(nombre_mutex)
        self._api = api
        self.nombre_evento = nombre_evento
        self._evento = 0
        self._hilo: Optional[threading.Thread] = None
        self._parar = threading.Event()
        self.duena = False

    def _api_real(self) -> Any:
        if self._api is None:
            self._api = api_defecto()
        return self._api

    def adquirir(self) -> bool:
        """True si esta es LA patata (y deja creado el evento del aviso)."""
        try:
            self.duena = bool(self._mutex.adquirir())
        except Exception:
            _log.debug("patata: el mutex de instancia falló", exc_info=True)
            self.duena = True                  # sin mutex no se bloquea a nadie
        if self.duena and not self._evento:
            try:
                self._evento = self._api_real().crear(self.nombre_evento)
            except Exception:
                self._evento = 0
        return self.duena

    def pedir_mostrar(self) -> bool:
        """Esta NO es la dueña: pide a la viva que se enseñe. True si la había."""
        return pedir_mostrar(self._api_real(), self.nombre_evento)

    def escuchar(self, al_pedir: Callable[[], Any]) -> bool:
        """Hilo que espera el aviso y llama a `al_pedir()` (en ese hilo). False si no hay
        evento (fuera de Windows, o no se pudo crear)."""
        if not self._evento or self._hilo is not None:
            return bool(self._hilo)
        api, h, parar = self._api_real(), self._evento, self._parar

        def bucle() -> None:
            while not parar.is_set():
                try:
                    r = api.esperar(h, ESPERA_MS)
                except Exception:
                    return
                if parar.is_set():
                    return
                if r == WAIT_OBJECT_0:
                    try:
                        al_pedir()
                    except Exception:
                        _log.exception("patata: traer la consola al frente falló")

        self._hilo = threading.Thread(target=bucle, name="lune-patata-instancia", daemon=True)
        self._hilo.start()
        return True

    def liberar(self) -> None:
        """Para el hilo, cierra el evento y suelta el mutex. Idempotente."""
        self._parar.set()
        hilo, self._hilo = self._hilo, None
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(ESPERA_MS / 1000.0 + 1.0)
        h, self._evento = self._evento, 0
        if h:
            try:
                self._api_real().cerrar(h)
            except Exception:
                pass
        if self.duena:
            try:
                self._mutex.liberar()
            except Exception:
                pass
            self.duena = False


__all__ = ("NOMBRE_MUTEX", "NOMBRE_EVENTO", "ApiEventoWin32", "ApiEventoNula", "InstanciaPatata",
           "pedir_mostrar", "patata_viva", "traer_consola_al_frente", "api_defecto")
