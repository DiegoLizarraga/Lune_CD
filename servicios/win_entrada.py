"""
servicios/win_entrada.py — Saber si la persona está usando el PC, sin espiar el teclado.

PARA QUÉ SIRVE
--------------
Lo usan el salvapantallas (¿cuánto lleva el PC sin tocarse?), la salida del
salvapantallas y de la pantalla grande, y el apagado de alarmas (¿acaba de
pulsar algo?). Todo por SONDEO, sin ganchos globales de teclado ni de ratón:
eso es lo que hace que Lune sea segura con los anticheat.

QUÉ LEE Y QUÉ NO
----------------
- `segundos_inactivo()`: `GetLastInputInfo` contra `GetTickCount`. Es la marca
  de tiempo de la última entrada de la sesión; no dice qué se pulsó.
- `DetectorEntrada.poll()`: hay entrada nueva si
    · cambió esa marca de tiempo y el cursor NO se movió (una tecla, la rueda,
      un clic derecho...), o
    · hay flanco del botón izquierdo (`GetAsyncKeyState(VK_LBUTTON)`).
  NUNCA se recorren códigos de tecla: sondear cientos de teclas varias veces
  por segundo es lo que hace un keylogger, y así lo vería un antivirus o un
  anticheat. Mover el ratón no cuenta como entrada, a propósito.
  Límite conocido: un ratón que «tiembla» sin mover el cursor (o empujado
  contra el borde de la pantalla) cambia la marca y cuenta como entrada.
- `mando_activo()`: `XInputGetState` de `xinput1_4.dll` (opcional). Los mandos
  no actualizan `GetLastInputInfo`; sin esto el salvapantallas saltaría en
  mitad de una partida con mando. Si la DLL no está, devuelve False.

Todo recibe un objeto `api` inyectable (ver `ApiEntradaWin32`) para probarlo
en seco: los tests pasan una API falsa o DLLs falsas, sin pantalla ni hardware.
Fuera de Windows todo es inofensivo: 0 segundos, sin entrada, sin mando.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Callable, List, NamedTuple, Optional, Tuple

VK_LBUTTON = 0x01
ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167
MAX_MANDOS = 4

# Zonas muertas recomendadas por Microsoft para XInput.
ZONA_MUERTA_IZQ = 7849
ZONA_MUERTA_DER = 8689
UMBRAL_GATILLO = 30

# Un hueco sin mando se vuelve a consultar como mucho cada tantos segundos:
# XInputGetState sobre un mando desconectado es lento.
ESPERA_DESCONECTADO_S = 3.0

_MASCARA_32 = 0xFFFFFFFF


class EstadoMando(NamedTuple):
    """Lo que devuelve XInputGetState de un mando conectado."""
    paquete: int
    botones: int
    gatillo_izq: int
    gatillo_der: int
    lx: int
    ly: int
    rx: int
    ry: int


# ── Estructuras de Win32 ──────────────────────────────────────────────────────

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


# ── APIs: la real (ctypes) y la nula (otros sistemas) ─────────────────────────

class ApiEntradaNula:
    """Fuera de Windows: nadie toca nada, nunca hay entrada ni mando."""

    def tick(self) -> int:
        return 0

    def ultima_entrada(self) -> Optional[int]:
        return None

    def cursor(self) -> Optional[Tuple[int, int]]:
        return None

    def boton_izquierdo(self) -> bool:
        return False

    def hay_xinput(self) -> bool:
        return False

    def estado_mando(self, indice: int) -> Optional[EstadoMando]:
        return None


_SIN_CARGAR = object()


class ApiEntradaWin32:
    """
    Envoltorio mínimo de user32/kernel32/xinput. Las DLL se pueden inyectar
    (objetos con las mismas funciones) para probar el marshalling sin Windows.
    Solo expone el botón izquierdo: no hay forma de pedirle otra tecla.
    """

    def __init__(self, user32=None, kernel32=None, xinput=_SIN_CARGAR):
        self._u = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        self._k = kernel32 if kernel32 is not None else ctypes.WinDLL("kernel32", use_last_error=True)
        self._x = xinput if xinput is _SIN_CARGAR else self._firmar_xinput(xinput)
        self._firmar()

    def _firmar(self):
        u, k = self._u, self._k
        k.GetTickCount.argtypes = []
        k.GetTickCount.restype = wintypes.DWORD
        u.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        u.GetLastInputInfo.restype = wintypes.BOOL
        u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        u.GetCursorPos.restype = wintypes.BOOL
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short

    @staticmethod
    def _firmar_xinput(dll):
        if dll is None:
            return None
        try:
            dll.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
            dll.XInputGetState.restype = wintypes.DWORD
            return dll
        except AttributeError:
            return None

    def _xinput(self):
        """xinput1_4 (Windows 8+) con xinput9_1_0 de respaldo; None si no hay ninguna.
        Se carga la primera vez que hace falta, no al crear la API."""
        if self._x is _SIN_CARGAR:
            dll = None
            for nombre in ("xinput1_4", "xinput9_1_0"):
                try:
                    dll = ctypes.WinDLL(nombre)
                    break
                except (OSError, AttributeError):     # AttributeError: no es Windows
                    continue
            self._x = self._firmar_xinput(dll)
        return self._x

    def tick(self) -> int:
        return int(self._k.GetTickCount()) & _MASCARA_32

    def ultima_entrada(self) -> Optional[int]:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not self._u.GetLastInputInfo(ctypes.byref(lii)):
            return None
        return int(lii.dwTime) & _MASCARA_32

    def cursor(self) -> Optional[Tuple[int, int]]:
        p = wintypes.POINT()
        if not self._u.GetCursorPos(ctypes.byref(p)):
            return None
        return (int(p.x), int(p.y))

    def boton_izquierdo(self) -> bool:
        return bool(int(self._u.GetAsyncKeyState(VK_LBUTTON)) & 0x8000)

    def hay_xinput(self) -> bool:
        return self._xinput() is not None

    def estado_mando(self, indice: int) -> Optional[EstadoMando]:
        x = self._xinput()
        if x is None:
            return None
        st = XINPUT_STATE()
        try:
            r = int(x.XInputGetState(int(indice), ctypes.byref(st)))
        except Exception:
            return None
        if r != ERROR_SUCCESS:
            return None
        g = st.Gamepad
        return EstadoMando(int(st.dwPacketNumber), int(g.wButtons), int(g.bLeftTrigger),
                           int(g.bRightTrigger), int(g.sThumbLX), int(g.sThumbLY),
                           int(g.sThumbRX), int(g.sThumbRY))


_api_defecto = None


def api_defecto():
    """La API real en Windows (una por proceso) y la nula en el resto."""
    global _api_defecto
    if _api_defecto is None:
        if sys.platform == "win32":
            try:
                _api_defecto = ApiEntradaWin32()
            except Exception:
                _api_defecto = ApiEntradaNula()
        else:
            _api_defecto = ApiEntradaNula()
    return _api_defecto


# ── Inactividad ───────────────────────────────────────────────────────────────

def ms_desde(ahora: int, antes: int) -> int:
    """Milisegundos entre dos lecturas de GetTickCount, aunque el contador haya
    dado la vuelta (32 bits: cada 49,7 días)."""
    return (int(ahora) - int(antes)) & _MASCARA_32


def segundos_inactivo(api=None) -> float:
    """Segundos desde la última entrada (teclado, ratón, táctil) de la sesión.
    0.0 si no se puede saber: mejor creer que hay alguien que dormirse a destiempo."""
    api = api or api_defecto()
    try:
        ultima = api.ultima_entrada()
        if ultima is None:
            return 0.0
        return ms_desde(api.tick(), ultima) / 1000.0
    except Exception:
        return 0.0


# ── Mando (XInput) ────────────────────────────────────────────────────────────

def mando_en_reposo(est: EstadoMando) -> bool:
    """Sin botones, gatillos sueltos y sticks dentro de la zona muerta. El
    número de paquete no se usa: un stick con deriva lo cambia sin parar."""
    if est.botones:
        return False
    if est.gatillo_izq > UMBRAL_GATILLO or est.gatillo_der > UMBRAL_GATILLO:
        return False
    if abs(est.lx) > ZONA_MUERTA_IZQ or abs(est.ly) > ZONA_MUERTA_IZQ:
        return False
    if abs(est.rx) > ZONA_MUERTA_DER or abs(est.ry) > ZONA_MUERTA_DER:
        return False
    return True


class LectorMando:
    """¿Alguien está usando un mando AHORA? Recorre los 4 huecos de XInput y
    espera `ESPERA_DESCONECTADO_S` antes de volver a preguntar por uno vacío."""

    def __init__(self, api=None, reloj: Callable[[], float] = time.monotonic):
        self.api = api or api_defecto()
        self._reloj = reloj
        self._espera: List[float] = [0.0] * MAX_MANDOS

    def activo(self) -> bool:
        try:
            if not self.api.hay_xinput():
                return False
        except Exception:
            return False
        ahora = self._reloj()
        hay = False
        for i in range(MAX_MANDOS):
            if self._espera[i] > ahora:
                continue
            try:
                est = self.api.estado_mando(i)
            except Exception:
                est = None
            if est is None:
                self._espera[i] = ahora + ESPERA_DESCONECTADO_S
                continue
            if not mando_en_reposo(est):
                hay = True
        return hay


_lector_defecto: Optional[LectorMando] = None


def mando_activo(api=None) -> bool:
    """True si algún mando XInput tiene un botón, gatillo o stick en uso.
    False si no hay mandos, no hay XInput o no es Windows."""
    global _lector_defecto
    api = api or api_defecto()
    if _lector_defecto is None or _lector_defecto.api is not api:
        _lector_defecto = LectorMando(api)
    return _lector_defecto.activo()


# ── Detector de entrada nueva (salir del salvapantallas, apagar alarmas) ─────

class DetectorEntrada:
    """
    Llama a `poll()` a 20-30 Hz mientras esperas «que la persona haga algo».
    La primera llamada (y la siguiente a `reiniciar()`) solo toma la línea
    base y devuelve False, así la entrada que abrió el salvapantallas o la
    alarma no la cierra al instante.

    `ultimo_motivo` dice por qué fue la última detección: 'clic', 'entrada'
    (cambió la marca sin mover el cursor) o 'mando'.
    """

    def __init__(self, api=None, con_mando: bool = False, lector_mando: Optional[LectorMando] = None):
        self.api = api or api_defecto()
        self.con_mando = con_mando
        self._lector = lector_mando
        self.ultimo_motivo = ""
        self.reiniciar()

    def reiniciar(self):
        self._base = False
        self._t = None
        self._pos = None
        self._clic = False
        self._mando = False

    def _mando_ahora(self) -> bool:
        if not self.con_mando:
            return False
        if self._lector is None:
            self._lector = LectorMando(self.api)
        return self._lector.activo()

    def poll(self) -> bool:
        try:
            t = self.api.ultima_entrada()
            pos = self.api.cursor()
            clic = self.api.boton_izquierdo()
        except Exception:
            return False
        mando = self._mando_ahora()

        if not self._base:
            self._base = True
            self._t, self._pos, self._clic, self._mando = t, pos, clic, mando
            return False

        motivo = ""
        if clic and not self._clic:
            motivo = "clic"
        elif t is not None and self._t is not None and t != self._t and pos == self._pos:
            motivo = "entrada"
        elif mando and not self._mando:
            motivo = "mando"

        self._t, self._pos, self._clic, self._mando = t, pos, clic, mando
        if motivo:
            self.ultimo_motivo = motivo
            return True
        return False
