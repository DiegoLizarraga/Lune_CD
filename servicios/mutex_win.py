"""
servicios/mutex_win.py — Un mutex con nombre para que solo UN proceso de Lune haga cierta tarea.

PARA QUÉ SIRVE
--------------
La app, patata y el bot pueden estar abiertos a la vez. Algunas tareas no se
deben duplicar: que suene la misma alarma dos veces, o que haya dos presencias
de Discord peleándose. Cada una usa un mutex con nombre de Windows
(`Local\\Lune_CD_Alarmas`, `Local\\LuneDiscordRPC`...): quien lo posee hace la
tarea; los demás lo reintentan de vez en cuando por si el dueño se cierra.

CÓMO SE SABE QUIÉN ES EL DUEÑO
------------------------------
`CreateMutexW` + `WaitForSingleObject(h, 0)`:
- WAIT_OBJECT_0 → nadie lo tenía: somos dueños.
- WAIT_ABANDONED → el dueño anterior murió sin soltarlo: también somos dueños
  (`abandonado` queda en True, para el log).
- WAIT_TIMEOUT → es de otro. Se CIERRA el handle en el acto.

No se usa «¿ya existía?» (ERROR_ALREADY_EXISTS): así el perdedor se quedaría
con un handle abierto que mantiene vivo el mutex y nunca llegaría a ser dueño
aunque el primero se cerrara. Con la espera de 0 ms, un reintento posterior
(`adquirir()` otra vez) sí lo consigue en cuanto el dueño lo suelta o muere.

DETALLES DE WINDOWS
-------------------
- La propiedad de un mutex es del HILO que lo adquirió, no del proceso. Si ese
  hilo termina, el mutex queda abandonado y OTRO PROCESO lo obtiene (con
  WAIT_ABANDONED) aunque este siga vivo y crea que es el dueño. Por eso cada
  `MutexNombrado` hace todas sus llamadas a kernel32 desde un hilo PROPIO de
  larga vida (`_HiloDueno`, daemon): se puede llamar a `adquirir()`,
  `es_dueno` y `liberar()` desde cualquier hilo (un worker que acaba, el de
  Qt…) y la propiedad dura hasta `liberar()` o hasta que el proceso muere.
- Si aun así el hilo propio ya no vive, `es_dueno` es False y `adquirir()`
  suelta el estado local y lo vuelve a intentar desde un hilo nuevo.
- El hilo se crea en el primer `adquirir()` y se va con `liberar()` (o cuando
  la instancia se recoge). Un perdedor que reintenta conserva el suyo, parado
  en una cola: no cuesta nada.
- Dos instancias con el mismo nombre en el mismo proceso tienen hilos
  distintos, así que solo una es dueña.
- Si el nombre no lleva espacio de nombres, se le pone `Local\\` (la sesión
  del usuario). Otras barras invertidas del nombre se cambian por `_`.

Fuera de Windows es un no-op que siempre adquiere. La API (`ApiMutexWin32`) es
inyectable para probarlo sin kernel32.
"""
from __future__ import annotations

import ctypes
import queue
import sys
import threading
from ctypes import wintypes
from typing import Any, Callable, Optional, Tuple

WAIT_OBJECT_0 = 0x00000000
WAIT_ABANDONED = 0x00000080
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF

_ESPACIOS = ("Local\\", "Global\\", "Session\\")

# Lo más que se espera al hilo propio (las llamadas son de 0 ms: responde al instante).
_ESPERA_HILO_S = 5.0


def normalizar_nombre(nombre: str) -> str:
    """`Lune_CD_Alarmas` → `Local\\Lune_CD_Alarmas`; respeta `Local\\` y `Global\\`."""
    nombre = str(nombre or "").strip() or "Lune_CD"
    for prefijo in _ESPACIOS:
        if nombre.startswith(prefijo):
            resto = nombre[len(prefijo):]
            if prefijo == "Session\\":        # Session\<n>\<nombre>
                n, _, resto2 = resto.partition("\\")
                return prefijo + n + "\\" + (resto2.replace("\\", "_") or "Lune_CD")
            return prefijo + (resto.replace("\\", "_") or "Lune_CD")
    return "Local\\" + nombre.replace("\\", "_")


class ApiMutexWin32:
    """kernel32 con ctypes. La DLL se puede inyectar en los tests."""

    def __init__(self, kernel32=None):
        k = kernel32 if kernel32 is not None else ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateMutexW.restype = wintypes.HANDLE
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.ReleaseMutex.argtypes = [wintypes.HANDLE]
        k.ReleaseMutex.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        self._k = k

    def crear(self, nombre: str) -> int:
        """Handle al mutex (creado o ya existente), sin pedir la propiedad. 0 si falla."""
        return int(self._k.CreateMutexW(None, False, nombre) or 0)

    def esperar(self, handle: int, ms: int) -> int:
        return int(self._k.WaitForSingleObject(handle, int(ms))) & 0xFFFFFFFF

    def soltar(self, handle: int) -> bool:
        return bool(self._k.ReleaseMutex(handle))

    def cerrar(self, handle: int) -> bool:
        return bool(self._k.CloseHandle(handle))

    def ultimo_error(self) -> int:
        try:
            return int(ctypes.get_last_error())
        except Exception:
            return 0


class _HiloDueno:
    """Hilo propio y de larga vida donde se hacen TODAS las llamadas a kernel32
    de un MutexNombrado, para que la propiedad del mutex (que es del hilo) no
    dependa de quién llame a `adquirir()`.

    El bucle no guarda referencias a la instancia (solo la cola), así que un
    MutexNombrado olvidado se puede recoger y su `__del__` para el hilo.
    """

    def __init__(self, nombre: str):
        self._cola: "queue.SimpleQueue" = queue.SimpleQueue()
        self._hilo = threading.Thread(target=_bucle_hilo_dueno, args=(self._cola,),
                                      name=f"LuneMutex[{nombre}]", daemon=True)
        self._hilo.start()

    def vivo(self) -> bool:
        return self._hilo.is_alive()

    def ejecutar(self, fn: Callable[[], Any], timeout: float = _ESPERA_HILO_S) -> Any:
        """Ejecuta `fn()` en el hilo propio y devuelve su resultado (o relanza su error)."""
        if not self.vivo():
            raise RuntimeError("el hilo del mutex ya no vive")
        caja: list = []
        hecho = threading.Event()
        self._cola.put((fn, caja, hecho))
        if not hecho.wait(timeout):
            raise TimeoutError("el hilo del mutex no responde")
        ok, valor = caja[0]
        if not ok:
            raise valor
        return valor

    def encargar(self, fn: Callable[[], Any]) -> None:
        """Como `ejecutar`, sin esperar (para `__del__`: nunca bloquear al recolector)."""
        if self.vivo():
            self._cola.put((fn, [], threading.Event()))

    def parar(self, esperar: bool = True) -> None:
        """El hilo termina cuando acaba lo que tenga en cola."""
        self._cola.put(None)
        if esperar and self._hilo is not threading.current_thread():
            self._hilo.join(_ESPERA_HILO_S)


def _bucle_hilo_dueno(cola: "queue.SimpleQueue") -> None:
    while True:
        tarea = cola.get()
        if tarea is None:
            return
        fn, caja, hecho = tarea
        try:
            caja.append((True, fn()))
        except BaseException as e:            # se relanza en quien pidió la tarea
            caja.append((False, e))
        hecho.set()
        # Sin referencias colgando hasta la tarea siguiente (el traceback de un
        # error relanzado llega hasta el MutexNombrado y no dejaría recogerlo).
        del tarea, fn, caja, hecho


def _intentar(api, nombre: str) -> Tuple[int, int, int]:
    """(En el hilo propio) CreateMutexW + WaitForSingleObject(h, 0).

    → (handle si somos dueños o 0, resultado de la espera, último error de
    CreateMutexW). Si no somos dueños el handle se cierra aquí mismo, para no
    mantener vivo el mutex de otro. GetLastError es por hilo: se lee aquí.
    """
    h = api.crear(nombre)
    if not h:
        try:
            err = api.ultimo_error()
        except Exception:
            err = 0
        return 0, WAIT_FAILED, err
    try:
        r = api.esperar(h, 0)
    except Exception:
        r = WAIT_FAILED
    if r in (WAIT_OBJECT_0, WAIT_ABANDONED):
        return h, r, 0
    # De otro (o fallo): cerrar YA, para no mantener vivo su mutex.
    try:
        api.cerrar(h)
    except Exception:
        pass
    return 0, r, 0


def _soltar(api, h: int, soltar: bool = True) -> None:
    """(En el hilo dueño) ReleaseMutex + CloseHandle, sin propagar errores."""
    if soltar:
        try:
            api.soltar(h)
        except Exception:
            pass
    try:
        api.cerrar(h)
    except Exception:
        pass


class MutexNombrado:
    """
    Uso típico (el tick de las alarmas):

        self._mutex = MutexNombrado("Local\\\\Lune_CD_Alarmas")
        ...
        if self._mutex.adquirir():      # barato: reintenta si no somos dueños
            programar()

    O como context manager: `with MutexNombrado("X") as m: if m.es_dueno: ...`

    Se puede usar desde cualquier hilo: las llamadas al kernel las hace el hilo
    propio de la instancia (ver el docstring del módulo).
    """

    def __init__(self, nombre: str, api=None):
        self.nombre = normalizar_nombre(nombre)
        self._nulo = api is None and sys.platform != "win32"
        self._api = api
        self._h = 0
        self._dueno = False
        self._hilo: Optional[_HiloDueno] = None
        self.abandonado = False
        self.ultimo_error = 0
        self._lock = threading.Lock()

    def _api_real(self):
        if self._api is None:
            self._api = ApiMutexWin32()
        return self._api

    def _hilo_vivo(self) -> bool:
        return self._hilo is not None and self._hilo.vivo()

    @property
    def es_dueno(self) -> bool:
        """True mientras este proceso posee el mutex. Si el hilo que lo poseía
        ya no vive, el mutex está abandonado (otro proceso puede tomarlo): False."""
        return self._dueno and (self._nulo or self._hilo_vivo())

    def adquirir(self) -> bool:
        """True si este proceso es (o pasa a ser) el dueño. Nunca bloquea
        (espera como mucho a su propio hilo, que responde al momento)."""
        with self._lock:
            if self._dueno:
                if self._nulo or self._hilo_vivo():
                    return True
                self._olvidar_propiedad_locked()     # su hilo murió: el mutex quedó abandonado
            if self._nulo:
                self._dueno = True
                return True
            try:
                api = self._api_real()
                if not self._hilo_vivo():
                    self._hilo = _HiloDueno(self.nombre)
                nombre = self.nombre
                h, r, err = self._hilo.ejecutar(lambda: _intentar(api, nombre))
            except Exception:
                return False
            if not h:
                if err:
                    self.ultimo_error = err
                return False
            self._h = h
            self._dueno = True
            self.abandonado = r == WAIT_ABANDONED
            return True

    def liberar(self) -> None:
        """Suelta la propiedad, cierra el handle y para el hilo propio. Idempotente."""
        self._liberar(esperar=True)

    def _liberar(self, esperar: bool) -> None:
        with self._lock:
            hilo, self._hilo = self._hilo, None
            if self._dueno and not self._nulo:
                h, self._h = self._h, 0
                api = self._api
                if h and hilo is not None and hilo.vivo():
                    try:
                        if esperar:
                            hilo.ejecutar(lambda: _soltar(api, h))
                        else:
                            hilo.encargar(lambda: _soltar(api, h))
                    except Exception:
                        pass
                elif h and api is not None:
                    _soltar(api, h, soltar=False)    # sin su hilo, ReleaseMutex fallaría
            self._dueno = False
            if hilo is not None:
                hilo.parar(esperar=esperar)

    def _olvidar_propiedad_locked(self) -> None:
        """El hilo dueño murió: cierra nuestro handle (CloseHandle vale desde
        cualquier hilo) y deja el estado como «no dueño»."""
        h, self._h = self._h, 0
        self._dueno = False
        self._hilo = None
        if h and self._api is not None:
            _soltar(self._api, h, soltar=False)

    def __enter__(self) -> "MutexNombrado":
        self.adquirir()
        return self

    def __exit__(self, *exc) -> bool:
        self.liberar()
        return False

    def __del__(self):
        try:
            self._liberar(esperar=False)
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"MutexNombrado({self.nombre!r}, dueno={self.es_dueno})"
