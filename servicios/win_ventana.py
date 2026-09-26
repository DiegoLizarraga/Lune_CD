"""
servicios/win_ventana.py — Orden Z y barra de tareas de las ventanas PROPIAS de Lune.

- `set_encima(hwnd, on)`: siempre encima (HWND_TOPMOST) o no (HWND_NOTOPMOST).
- `al_fondo(hwnd)`: fuera de «siempre encima» y detrás de todo (modo juego
  «fondo»: la mascota no pelea con el juego sin bordes).
- `traer_al_frente(hwnd)`: arriba del orden Z y en primer plano (el menú radial
  lo pide justo tras un clic o un WM_HOTKEY, cuando Windows lo permite).
- `set_en_barra(hwnd, on)`: sale o no en la barra de tareas (WS_EX_APPWINDOW /
  WS_EX_TOOLWINDOW). OJO: Windows solo lo nota al ocultar y volver a mostrar la
  ventana; eso lo hace quien llama (con QtWebEngine, ocultar/mostrar la principal).

Para sentarse en ventanas y en la barra (corte 7, ui/asiento_qt.py):

- `rect_propia(hwnd)`: GetWindowRect de la ventana propia (px físicos).
- `mover(hwnd, x, y)`: la mueve a (x, y) en px físicos, sin cambiar su tamaño ni
  su orden Z y sin activarla.
- `colocar_sobre(propia, objetivo)`: deja la ventana propia JUSTO encima de otra
  en el orden Z (la mascota sentada en el Bloc de notas queda tapada por lo que
  tape al Bloc). Solo se mueve la propia: de la otra solo se LEE quién tiene
  encima (GetWindow GW_HWNDPREV) y si es «siempre encima».
- `encima_de(propia, objetivo)`: ¿la propia ya está justo encima? (saltando las
  ventanas invisibles que haya entre medias, que no tapan nada).

SEGURIDAD: cada función que cambia algo comprueba primero que la ventana es de
ESTE proceso (GetWindowThreadProcessId == pid propio) y si no, no hace nada:
nunca se mueve ni se cambia el orden Z ni el estilo de la ventana de otro
programa (un juego). SetWindowPos va siempre con SWP_NOACTIVATE; las del orden Z
con SWP_NOMOVE | SWP_NOSIZE y la de mover con SWP_NOSIZE | SWP_NOZORDER.

Fuera de Windows no hace nada (devuelve False). `user32` se puede inyectar.
"""
from __future__ import annotations

import ctypes
import os
import sys

HWND_TOP = 0
HWND_BOTTOM = 1
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOOWNERZORDER = 0x0200

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

GW_HWNDPREV = 3

_FLAGS_Z = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
_FLAGS_MOVER = SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
_MASCARA_32 = 0xFFFFFFFF
# Ventanas invisibles que se saltan al mirar quién hay justo encima del objetivo.
PASOS_INVISIBLES = 64

_user32_real = None


def _user32(user32=None):
    """La user32 inyectada, la real con sus firmas (una vez) o None fuera de Windows."""
    global _user32_real
    if user32 is not None:
        return user32
    if sys.platform != "win32":
        return None
    if _user32_real is None:
        from ctypes import wintypes
        try:
            u = ctypes.WinDLL("user32", use_last_error=True)
            H = wintypes.HWND
            u.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.UINT]
            u.SetWindowPos.restype = wintypes.BOOL
            u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
            u.GetWindowThreadProcessId.restype = wintypes.DWORD
            u.GetWindowLongW.argtypes = [H, ctypes.c_int]
            u.GetWindowLongW.restype = wintypes.LONG
            u.SetWindowLongW.argtypes = [H, ctypes.c_int, wintypes.LONG]
            u.SetWindowLongW.restype = wintypes.LONG
            u.SetForegroundWindow.argtypes = [H]
            u.SetForegroundWindow.restype = wintypes.BOOL
            u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
            u.GetWindowRect.restype = wintypes.BOOL
            u.GetWindow.argtypes = [H, wintypes.UINT]
            u.GetWindow.restype = H
            u.IsWindowVisible.argtypes = [H]
            u.IsWindowVisible.restype = wintypes.BOOL
            _user32_real = u
        except Exception:
            return None
    return _user32_real


def _pid_de(hwnd: int, u) -> int:
    from ctypes import wintypes
    pid = wintypes.DWORD(0)
    try:
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except Exception:
        return 0
    return int(pid.value)


def es_propia(hwnd, user32=None) -> bool:
    """¿La ventana `hwnd` es de este proceso? (sin eso no se toca)."""
    u = _user32(user32)
    if u is None or not hwnd:
        return False
    return _pid_de(int(hwnd), u) == os.getpid()


def _set_pos(u, hwnd: int, despues: int, flags: int = _FLAGS_Z) -> bool:
    try:
        return bool(u.SetWindowPos(hwnd, despues, 0, 0, 0, 0, flags | SWP_NOACTIVATE))
    except Exception:
        return False


def set_encima(hwnd, on: bool, user32=None) -> bool:
    """Siempre encima (on) o no. Solo ventanas propias."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return False
    return _set_pos(u, int(hwnd), HWND_TOPMOST if on else HWND_NOTOPMOST)


def al_fondo(hwnd, user32=None) -> bool:
    """Quita «siempre encima» y la manda detrás de todo. Solo ventanas propias."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return False
    a = _set_pos(u, int(hwnd), HWND_NOTOPMOST)
    b = _set_pos(u, int(hwnd), HWND_BOTTOM)
    return a and b


def traer_al_frente(hwnd, user32=None) -> bool:
    """Arriba del orden Z (sin activar con SetWindowPos) y luego SetForegroundWindow,
    que Windows solo concede tras una entrada del usuario (clic, WM_HOTKEY). Solo
    ventanas propias. True si quedó en primer plano."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return False
    _set_pos(u, int(hwnd), HWND_TOP)
    try:
        return bool(u.SetForegroundWindow(int(hwnd)))
    except Exception:
        return False


def set_en_barra(hwnd, on: bool, user32=None) -> bool:
    """Sale en la barra de tareas (WS_EX_APPWINDOW) o no (WS_EX_TOOLWINDOW). Solo
    ventanas propias; hay que ocultar y volver a mostrar la ventana para que la
    barra lo note (eso lo hace quien llama)."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return False
    h = int(hwnd)
    try:
        ex = int(u.GetWindowLongW(h, GWL_EXSTYLE)) & _MASCARA_32
    except Exception:
        return False
    nuevo = (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW if on else (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    if nuevo != ex:
        try:
            # LONG con signo: el bit alto (si lo hubiera) va como negativo.
            u.SetWindowLongW(h, GWL_EXSTYLE, ctypes.c_long(nuevo & _MASCARA_32).value)
        except Exception:
            return False
    return _set_pos(u, h, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)


# ── Sentarse en ventanas y en la barra (corte 7) ──────────────────────────────

def rect_propia(hwnd, user32=None):
    """GetWindowRect de una ventana PROPIA en px físicos (`win_pantalla.Rect`), o
    None si no es propia, no existe o fuera de Windows."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return None
    from ctypes import wintypes
    from servicios.win_pantalla import Rect
    r = wintypes.RECT()
    try:
        if not u.GetWindowRect(int(hwnd), ctypes.byref(r)):
            return None
    except Exception:
        return None
    return Rect(int(r.left), int(r.top), int(r.right), int(r.bottom))


def mover(hwnd, x, y, user32=None) -> bool:
    """Mueve una ventana PROPIA a (x, y) en px físicos: sin cambiar su tamaño ni
    su orden Z y sin activarla. False si no es propia."""
    u = _user32(user32)
    if u is None or not es_propia(hwnd, u):
        return False
    try:
        return bool(u.SetWindowPos(int(hwnd), 0, int(round(x)), int(round(y)), 0, 0, _FLAGS_MOVER))
    except Exception:
        return False


def _anterior(u, h: int) -> int:
    """GetWindow(h, GW_HWNDPREV): la ventana que tiene justo encima (lectura)."""
    try:
        return int(u.GetWindow(int(h), GW_HWNDPREV) or 0)
    except Exception:
        return 0


def _es_topmost(u, h: int) -> bool:
    """¿Tiene WS_EX_TOPMOST? (lectura del estilo)."""
    if not h:
        return False
    try:
        return bool(int(u.GetWindowLongW(int(h), GWL_EXSTYLE)) & _MASCARA_32 & WS_EX_TOPMOST)
    except Exception:
        return False


def _visible(u, h: int) -> bool:
    try:
        return bool(u.IsWindowVisible(int(h)))
    except Exception:
        return True                                   # en la duda, cuenta como que tapa


def encima_de(hwnd_propio, hwnd_objetivo, user32=None) -> bool:
    """¿La ventana propia está JUSTO encima de `hwnd_objetivo` en el orden Z?

    Sube desde el objetivo con GetWindow(GW_HWNDPREV) saltando las ventanas
    invisibles (no tapan nada y Windows las intercala a menudo), como mucho
    PASOS_INVISIBLES. Solo lee."""
    u = _user32(user32)
    if u is None or not hwnd_objetivo or not es_propia(hwnd_propio, u):
        return False
    propia, h = int(hwnd_propio), int(hwnd_objetivo)
    for _ in range(PASOS_INVISIBLES):
        h = _anterior(u, h)
        if not h:
            return False
        if h == propia:
            return True
        if _visible(u, h):
            return False
    return False


def colocar_sobre(hwnd_propio, hwnd_objetivo, user32=None) -> bool:
    """Pone la ventana PROPIA justo encima de `hwnd_objetivo` en el orden Z.

    Del objetivo solo se lee quién tiene encima (GW_HWNDPREV) y si es «siempre
    encima»; la única ventana que cambia es la propia:
    - si ya está justo encima (`encima_de`), no llama a nada y devuelve True;
    - objetivo normal: la propia deja de ser «siempre encima» (si lo era) y va
      detrás de la que el objetivo tiene encima (si esa no es «siempre encima»)
      o arriba del todo de las normales (HWND_TOP);
    - objetivo «siempre encima» (otra mascota, un reproductor en miniatura): la
      propia pasa a «siempre encima» y va detrás de la que tenga encima.
    Siempre con SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER."""
    u = _user32(user32)
    if u is None or not hwnd_objetivo or not es_propia(hwnd_propio, u):
        return False
    propia, objetivo = int(hwnd_propio), int(hwnd_objetivo)
    if propia == objetivo:
        return False
    if encima_de(propia, objetivo, u):
        return True
    prev = _anterior(u, objetivo)
    if prev == propia:
        return True
    if _es_topmost(u, objetivo):
        if not _es_topmost(u, propia) and not _set_pos(u, propia, HWND_TOPMOST):
            return False
        return _set_pos(u, propia, prev if prev else HWND_TOPMOST)
    if _es_topmost(u, propia) and not _set_pos(u, propia, HWND_NOTOPMOST):
        return False
    despues = prev if (prev and not _es_topmost(u, prev)) else HWND_TOP
    return _set_pos(u, propia, despues)
