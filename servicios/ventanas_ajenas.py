"""
servicios/ventanas_ajenas.py — Qué ventanas de OTROS programas hay y dónde están.

PARA QUÉ SIRVE
--------------
Sentarse en ventanas y en la barra de tareas (corte 7, P03; `ui/asiento_qt.py`
y `nucleo/asiento.py`): mientras arrastras a la asistente, Lune mira qué ventanas
tienen el borde superior cerca para sentarse encima, y cuando ya está sentada
vigila si esa ventana se movió, se minimizó o se cerró. Es el port de
`AvatarWindowHandler.cs` de Mate-Engine (enumeración y filtros) y de
`MonitorHelper.cs` (la barra de cada monitor).

SOLO LECTURA (anticheat)
------------------------
De las ventanas ajenas solo se LEEN datos, por sondeo, cuando hace falta (a 15 Hz
mientras arrastras; nada en reposo). No hay ganchos de eventos del sistema ni se
abre ningún proceso ajeno:
- EnumWindows, IsWindowVisible, GetWindowRect, GetClassNameW,
  GetWindowTextLengthW (el largo; el título no se lee), GetWindowLongW, GetParent,
  GetAncestor, IsIconic, IsZoomed, IsWindow, GetWindow(GW_HWNDPREV),
  GetLayeredWindowAttributes, GetForegroundWindow, MonitorFromWindow y
  GetMonitorInfoW;
- DwmGetWindowAttribute (EXTENDED_FRAME_BOUNDS y CLOAKED);
- el pid con GetWindowThreadProcessId, sin abrir el proceso.
Lo único que se mueve o se reordena es la ventana PROPIA de la asistente, y eso lo
hace `servicios/win_ventana.py` (que comprueba antes que es propia).

QUÉ OFRECE
----------
- `ApiVentanasWin32` / `ApiVentanasNula`: la API inyectable (los tests usan una
  falsa). `api_defecto()` da la real en Windows y la nula fuera.
- `listar_candidatas(api, excluir_pid=…, permitir=…)`: ventanas donde sentarse,
  en orden Z (de arriba abajo), con los filtros de ME: raíz y sin dueño, con
  título, ≥ 200×60, visibles y sin «cloak», ni el escritorio ni clases raras, ni
  transparentes ni otros avatares de escritorio, ni a pantalla completa en SU monitor, ni
  minimizadas ni maximizadas. Las barras de tareas salen marcadas `es_barra`.
  Tope de 128.
- `ocluida_en(api, hwnd, x, y)`: ¿otra ventana tapa ese punto de `hwnd`?
- `estado_ventana(api, hwnd)`: ok · cerrada · oculta · minimizada · maximizada ·
  pantalla_completa · cloaked (por qué hay que levantarse).
- `encima_de(api, a, b)`: ¿a está por encima de b en el orden Z?
- `barra_asiento(hmon_o_rect)`: la barra de tareas de ABAJO del monitor donde
  está la asistente, como `Candidata` (las barras laterales o arriba no valen).

COORDENADAS
-----------
Todo en px físicos (el proceso es consciente de DPI por monitor, como con Qt 6).
`rect_visible` usa DWMWA_EXTENDED_FRAME_BOUNDS: sin el borde invisible de 7 px
que Windows 10/11 pone a los lados y abajo de las ventanas con marco.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from servicios import win_pantalla as wp
from servicios.win_pantalla import CLASES_BARRA, Rect

# ── Constantes de Win32 ────────────────────────────────────────────────────────
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
GA_ROOT = 2
GW_HWNDPREV = 3
MONITOR_DEFAULTTONEAREST = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

_MASCARA_32 = 0xFFFFFFFF

# ── Reglas de Mate-Engine (AvatarWindowHandler.cs y la escena) ─────────────────
ALFA_TRANSPARENTE = 230          # layeredAlphaIgnoreBelow: con alfa ≤ 230 no cuenta
ALFA_OCLUSOR = 8                 # una ventana casi invisible (≤ 8) no tapa
ANCHO_MIN, ALTO_MIN = 200, 60    # IsSitEligibleWindow
TOL_PANTALLA_COMPLETA = 2        # ±2 px contra SU monitor (ME lo compara con el principal)
MAX_CANDIDATAS = 128
MAX_PASOS_Z = 2048               # tope al subir por el orden Z
CLASES_NO = frozenset({"Progman", "WorkerW", "DV2ControlHost", "MsgrIMEWindowClass"})
CLASES_UNITY = frozenset({"UnityWndClass", "UnityGUIView"})

ESTADOS = ("ok", "cerrada", "oculta", "minimizada", "maximizada", "pantalla_completa", "cloaked")


@dataclass(frozen=True)
class Candidata:
    """Una ventana donde la asistente se puede sentar (o una barra de tareas)."""
    hwnd: int
    rect: Rect            # px físicos; en ventanas, el borde visible (sin el invisible de Win11)
    es_barra: bool
    topmost: bool


def _rect(r) -> Rect:
    return r if isinstance(r, Rect) else Rect(*(int(v) for v in r))


def _rect_win(r) -> Rect:
    return Rect(int(r.left), int(r.top), int(r.right), int(r.bottom))


# ── APIs ───────────────────────────────────────────────────────────────────────

class ApiVentanasNula:
    """Fuera de Windows: no hay ventanas."""

    def enumerar(self) -> List[int]:
        return []

    def activa(self) -> int:
        return 0

    def visible(self, h) -> bool:
        return False

    def rect(self, h) -> Optional[Rect]:
        return None

    def rect_visible(self, h) -> Optional[Rect]:
        return None

    def clase(self, h) -> str:
        return ""

    def largo_titulo(self, h) -> int:
        return 0

    def estilo(self, h) -> int:
        return 0

    def estilo_ex(self, h) -> int:
        return 0

    def padre(self, h) -> int:
        return 0

    def raiz(self, h) -> int:
        return 0

    def minimizada(self, h) -> bool:
        return False

    def maximizada(self, h) -> bool:
        return False

    def cloaked(self, h) -> bool:
        return False

    def capas(self, h) -> Optional[Tuple[int, int]]:
        return None

    def anterior(self, h) -> int:
        return 0

    def existe(self, h) -> bool:
        return False

    def pid(self, h) -> int:
        return 0

    def monitor(self, h) -> Optional[Tuple[Rect, Rect]]:
        return None


def _tipo_enum_ventanas():
    fabrica = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return fabrica(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class ApiVentanasWin32:
    """user32 + dwmapi con ctypes, SOLO LECTURA. Las DLL se pueden inyectar."""

    def __init__(self, user32=None, dwmapi=None):
        self._u = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        self._d = dwmapi if dwmapi is not None else ctypes.WinDLL("dwmapi")
        self._enum_tipo = _tipo_enum_ventanas()
        self._firmar()

    def _firmar(self):
        u, d, H = self._u, self._d, wintypes.HWND
        firmas = {
            "EnumWindows": ([self._enum_tipo, wintypes.LPARAM], wintypes.BOOL),
            "GetForegroundWindow": ([], H),
            "IsWindowVisible": ([H], wintypes.BOOL),
            "IsWindow": ([H], wintypes.BOOL),
            "IsIconic": ([H], wintypes.BOOL),
            "IsZoomed": ([H], wintypes.BOOL),
            "GetWindowRect": ([H, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "GetClassNameW": ([H, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetWindowTextLengthW": ([H], ctypes.c_int),
            "GetWindowLongW": ([H, ctypes.c_int], wintypes.LONG),
            "GetParent": ([H], H),
            "GetAncestor": ([H, wintypes.UINT], H),
            "GetWindow": ([H, wintypes.UINT], H),
            "GetLayeredWindowAttributes": ([H, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_ubyte),
                                            ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "GetWindowThreadProcessId": ([H, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            "MonitorFromWindow": ([H, wintypes.DWORD], wintypes.HMONITOR),
            "GetMonitorInfoW": ([wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)], wintypes.BOOL),
        }
        for nombre, (args, res) in firmas.items():
            f = getattr(u, nombre)
            f.argtypes = args
            f.restype = res
        d.DwmGetWindowAttribute.argtypes = [H, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        d.DwmGetWindowAttribute.restype = ctypes.c_long                 # HRESULT sin excepción

    def enumerar(self) -> List[int]:
        """Las ventanas de primer nivel en orden Z, de arriba abajo."""
        salida: List[int] = []
        agregar = salida.append

        def _cada(hwnd, _lparam):
            if hwnd:
                agregar(hwnd)
            return True

        callback = self._enum_tipo(_cada)          # vivo hasta que vuelve la llamada
        self._u.EnumWindows(callback, 0)
        return salida

    def activa(self) -> int:
        return int(self._u.GetForegroundWindow() or 0)

    def visible(self, h) -> bool:
        return bool(self._u.IsWindowVisible(h))

    def rect(self, h) -> Optional[Rect]:
        r = wintypes.RECT()
        if not self._u.GetWindowRect(h, ctypes.byref(r)):
            return None
        return _rect_win(r)

    def rect_visible(self, h) -> Optional[Rect]:
        """El borde que se ve (DWMWA_EXTENDED_FRAME_BOUNDS) o, si DWM no lo da, GetWindowRect."""
        r = wintypes.RECT()
        try:
            hr = int(self._d.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                                   ctypes.sizeof(r)))
        except Exception:
            hr = -1
        if hr == 0:
            v = _rect_win(r)
            if not v.vacio:
                return v
        return self.rect(h)

    def clase(self, h) -> str:
        buf = ctypes.create_unicode_buffer(256)
        return buf.value if self._u.GetClassNameW(h, buf, 256) > 0 else ""

    def largo_titulo(self, h) -> int:
        return max(0, int(self._u.GetWindowTextLengthW(h)))

    def estilo(self, h) -> int:
        return int(self._u.GetWindowLongW(h, GWL_STYLE)) & _MASCARA_32

    def estilo_ex(self, h) -> int:
        return int(self._u.GetWindowLongW(h, GWL_EXSTYLE)) & _MASCARA_32

    def padre(self, h) -> int:
        return int(self._u.GetParent(h) or 0)

    def raiz(self, h) -> int:
        return int(self._u.GetAncestor(h, GA_ROOT) or 0)

    def minimizada(self, h) -> bool:
        return bool(self._u.IsIconic(h))

    def maximizada(self, h) -> bool:
        return bool(self._u.IsZoomed(h))

    def cloaked(self, h) -> bool:
        v = wintypes.DWORD(0)
        try:
            hr = int(self._d.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v)))
        except Exception:
            return False
        return hr == 0 and int(v.value) != 0

    def capas(self, h) -> Optional[Tuple[int, int]]:
        """(alfa, flags) de GetLayeredWindowAttributes, o None si no los tiene."""
        key, alfa, flags = wintypes.DWORD(0), ctypes.c_ubyte(0), wintypes.DWORD(0)
        if not self._u.GetLayeredWindowAttributes(h, ctypes.byref(key), ctypes.byref(alfa), ctypes.byref(flags)):
            return None
        return int(alfa.value), int(flags.value)

    def anterior(self, h) -> int:
        return int(self._u.GetWindow(h, GW_HWNDPREV) or 0)

    def existe(self, h) -> bool:
        return bool(self._u.IsWindow(h))

    def pid(self, h) -> int:
        pid = wintypes.DWORD(0)
        self._u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        return int(pid.value)

    def monitor(self, h) -> Optional[Tuple[Rect, Rect]]:
        """(rcMonitor, rcWork) del monitor donde está (o más cerca está) la ventana."""
        hmon = self._u.MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not self._u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        return _rect_win(mi.rcMonitor), _rect_win(mi.rcWork)


_api_defecto = None


def api_defecto():
    """La API real en Windows (una por proceso) y la nula en el resto."""
    global _api_defecto
    if _api_defecto is None:
        if sys.platform == "win32":
            try:
                _api_defecto = ApiVentanasWin32()
            except Exception:
                _api_defecto = ApiVentanasNula()
        else:
            _api_defecto = ApiVentanasNula()
    return _api_defecto


def _seguro(fn, *args, defecto=None):
    try:
        return fn(*args)
    except Exception:
        return defecto


# ── Filtros (IsEffectivelyTransparentWindow, IsLikelyUniWindow…, IsSitEligibleWindow de ME) ──

def _transparente(api, h, clase: str, ex: int) -> bool:
    if not ex & WS_EX_LAYERED:
        return False
    if ex & WS_EX_TRANSPARENT:
        return True                                    # deja pasar los clics
    if ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
        return True
    capas = _seguro(api.capas, h)
    if capas:
        alfa, flags = capas
        if flags & LWA_COLORKEY:
            return True
        if flags & LWA_ALPHA and alfa <= ALFA_TRANSPARENTE:
            return True
    st = int(_seguro(api.estilo, h, defecto=0) or 0)
    if not st & WS_CAPTION:
        if int(_seguro(api.largo_titulo, h, defecto=0) or 0) <= 1:
            return True
        if clase in CLASES_UNITY:
            return True
    return False


def es_transparente(api, h, clase) -> bool:
    """IsEffectivelyTransparentWindow de ME. Solo cuenta si es una ventana EN CAPAS
    (WS_EX_LAYERED) y además: deja pasar los clics, es de herramienta o no se
    activa, usa color clave, tiene alfa ≤ 230, o no tiene barra de título y su
    título tiene ≤ 1 carácter (o es una ventana de Unity sin título)."""
    api = api or api_defecto()
    ex = int(_seguro(api.estilo_ex, h, defecto=0) or 0)
    return _transparente(api, h, str(clase or ""), ex)


def _parece_asistente(api, h, clase: str, ex: int) -> bool:
    if not ex & WS_EX_LAYERED:
        return False
    rara = bool(ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT))
    if not rara:
        capas = _seguro(api.capas, h)
        if capas:
            alfa, flags = capas
            rara = bool((flags & LWA_ALPHA and alfa < 255) or flags & LWA_COLORKEY)
    if not rara:
        return False
    if clase == "UnityWndClass":
        return True                                    # Mate-Engine abierto, u otro avatar hecho en Unity
    st = int(_seguro(api.estilo, h, defecto=0) or 0)
    return not st & WS_CAPTION and int(_seguro(api.largo_titulo, h, defecto=0) or 0) <= 1


def parece_asistente(api, h, clase) -> bool:
    """¿Es otro avatar de escritorio? (IsLikelyUniWindow… de ME): en capas, «rara» (de
    herramienta, sin activar, sin clics o translúcida) y sin título, o de Unity
    (Mate-Engine abierto). Ahí no se sienta la asistente."""
    api = api or api_defecto()
    ex = int(_seguro(api.estilo_ex, h, defecto=0) or 0)
    return _parece_asistente(api, h, str(clase or ""), ex)


def _pantalla_completa(rect: Rect, mon: Optional[Tuple[Rect, Rect]], tol: int = TOL_PANTALLA_COMPLETA) -> bool:
    if not mon:
        return False
    m = _rect(mon[0])
    if m.vacio or rect.vacio:
        return False
    return all(abs(a - b) <= tol for a, b in zip(rect, m))


def es_elegible(api, h, rect, clase) -> bool:
    """IsSitEligibleWindow de ME + que no esté a pantalla completa en SU monitor
    (±2 px), ni maximizada, ni con el borde por encima de su monitor (se
    levantaría en el acto)."""
    api = api or api_defecto()
    if rect is None:
        return False
    r = _rect(rect)
    if r.ancho < ANCHO_MIN or r.alto < ALTO_MIN:
        return False
    clase = str(clase or "")
    if clase in CLASES_NO or clase.startswith("#") or "Desktop" in clase:
        return False
    try:
        if api.padre(h) or api.raiz(h) != h:
            return False                               # hija o con dueño (diálogos, popups)
        if api.minimizada(h) or api.largo_titulo(h) <= 0:
            return False
        if api.cloaked(h):
            return False                               # otro escritorio virtual, UWP suspendida…
        if api.maximizada(h):
            return False
        mon = api.monitor(h)
        if _pantalla_completa(r, mon):
            return False
        if mon and r.arriba < _rect(mon[0]).arriba:
            return False                               # el borde está por encima de su monitor: no se vería
    except Exception:
        return False
    return True


# ── Enumeración ────────────────────────────────────────────────────────────────

def listar_candidatas(api=None, *, excluir_pid: int, permitir: Iterable[int] = (), ventanas: bool = True,
                      barras: bool = True, maximo: int = MAX_CANDIDATAS) -> List[Candidata]:
    """Ventanas donde sentarse, en orden Z (de arriba abajo).

    - `excluir_pid`: las del propio proceso no cuentan (la asistente, la burbuja,
      el radial…), salvo las de `permitir` (la ventana principal de Lune), a las
      que además no se les pasan los filtros de transparencia y de otros avatares.
    - `ventanas` / `barras`: qué entra; las barras de tareas (Shell_TrayWnd y
      Shell_SecondaryTrayWnd) salen con `es_barra` y su GetWindowRect.
    - Como mucho `maximo` (128).
    """
    api = api or api_defecto()
    permitidas = {int(p) for p in (permitir or ()) if p}
    salida: List[Candidata] = []
    if not ventanas and not barras:
        return salida
    try:
        hwnds = api.enumerar()
    except Exception:
        return salida
    for h in hwnds:
        if len(salida) >= maximo:
            break
        try:
            if not api.visible(h):
                continue
            propia = h in permitidas
            if not propia and api.pid(h) == excluir_pid:
                continue
            clase = api.clase(h) or ""
            ex = int(api.estilo_ex(h) or 0)
            if not propia and _transparente(api, h, clase, ex):
                continue
            if clase in CLASES_BARRA:
                if barras:
                    r = api.rect(h)
                    if r is not None:
                        salida.append(Candidata(int(h), _rect(r), True, bool(ex & WS_EX_TOPMOST)))
                continue
            if not ventanas:
                continue
            r = api.rect(h)
            if r is None:
                continue
            r = _rect(r)
            if not propia and _parece_asistente(api, h, clase, ex):
                continue
            if not es_elegible(api, h, r, clase):
                continue
            visible = api.rect_visible(h)
            salida.append(Candidata(int(h), _rect(visible) if visible else r, False, bool(ex & WS_EX_TOPMOST)))
        except Exception:
            continue
    return salida


def ocluida_en(api, hwnd, x, y, *, excluir_pid: int, pasos: int = MAX_PASOS_Z) -> bool:
    """IsOccludedByHigherWindowsAtPoint de ME: ¿alguna ventana por encima de `hwnd`
    en el orden Z tapa el punto (x, y)? Se saltan las propias, las invisibles, las
    «cloaked», las minimizadas, las transparentes, otros avatares de escritorio, las que dejan
    pasar los clics y las casi invisibles (alfa ≤ 8). Como mucho `pasos` ventanas
    hacia arriba."""
    api = api or api_defecto()
    try:
        h = api.anterior(hwnd)
    except Exception:
        return False
    for _ in range(max(0, int(pasos))):
        if not h:
            return False
        try:
            if api.pid(h) == excluir_pid or not api.visible(h) or api.cloaked(h):
                h = api.anterior(h)
                continue
            r = api.rect_visible(h)
            if r is None or not (r.izq <= x <= r.der and r.arriba <= y <= r.abajo):
                h = api.anterior(h)
                continue
            clase = api.clase(h) or ""
            ex = int(api.estilo_ex(h) or 0)
            if _transparente(api, h, clase, ex) or _parece_asistente(api, h, clase, ex) or api.minimizada(h):
                h = api.anterior(h)
                continue
            if ex & WS_EX_TRANSPARENT:
                h = api.anterior(h)
                continue
            if ex & WS_EX_LAYERED:
                capas = api.capas(h)
                if capas and capas[1] & LWA_ALPHA and capas[0] <= ALFA_OCLUSOR:
                    h = api.anterior(h)
                    continue
            return True
        except Exception:
            return False
    return False


def estado_ventana(api, hwnd) -> str:
    """Por qué habría que levantarse de `hwnd`: "ok" si se puede seguir sentada;
    si no, cerrada · oculta · minimizada · cloaked · maximizada · pantalla_completa."""
    api = api or api_defecto()
    try:
        if not hwnd or not api.existe(hwnd):
            return "cerrada"
        if not api.visible(hwnd):
            return "oculta"
        if api.minimizada(hwnd):
            return "minimizada"
        if api.cloaked(hwnd):
            return "cloaked"
        if api.maximizada(hwnd):
            return "maximizada"
        r = api.rect(hwnd)
        if r is not None and _pantalla_completa(_rect(r), api.monitor(hwnd)):
            return "pantalla_completa"
    except Exception:
        return "cerrada"
    return "ok"


def encima_de(api, a, b, pasos: int = MAX_PASOS_Z) -> bool:
    """IsAboveInZOrder de ME: ¿`a` está por encima de `b`? (sube desde b)."""
    api = api or api_defecto()
    if not a or not b or a == b:
        return False
    h = b
    for _ in range(max(0, int(pasos))):
        try:
            h = api.anterior(h)
        except Exception:
            return False
        if not h:
            return False
        if h == a:
            return True
    return False


# ── Barra de tareas donde sentarse ─────────────────────────────────────────────

def _monitor_para(x, api) -> Optional[wp.Monitor]:
    """El Monitor de `x`: un hmon (int), un Monitor o el rect de la asistente (el
    monitor que contiene su centro o, si ninguno, el que más se solapa)."""
    if isinstance(x, wp.Monitor):
        return x
    if isinstance(x, int):
        try:
            return api.info_monitor(x) if x else None
        except Exception:
            return None
    try:
        r = _rect(x)
    except Exception:
        return None
    mons = wp.monitores(api)
    if not mons:
        return None
    cx, cy = r.centro
    for m in mons:
        if _rect(m.rect).contiene(cx, cy):
            return m
    mejor = max(mons, key=lambda m: _rect(m.rect).interseccion(r).area)
    return mejor if _rect(mejor.rect).interseccion(r).area > 0 else None


def _hwnd_barra(mon_rect: Rect, api) -> int:
    for clase in CLASES_BARRA:
        try:
            ventanas = api.buscar_ventanas(clase)
        except Exception:
            ventanas = []
        for h in ventanas:
            try:
                r = api.rect_ventana(h)
            except Exception:
                r = None
            if r and not _rect(r).interseccion(mon_rect).vacio:
                return int(h)
    return 0


def barra_asiento(hmon_o_rect_asistente, api_pantalla=None) -> Optional[Candidata]:
    """La barra de tareas de ABAJO del monitor de la asistente, como Candidata.

    Sale de `win_pantalla.barra_tareas` (rcMonitor − rcWork, como MonitorHelper de
    ME). Solo si está abajo: en una barra lateral o arriba no se sienta. Con la
    barra auto-oculta el borde es el de abajo del monitor y no sigue a la barra
    cuando se despliega (el rect va de rcMonitor.abajo a +1 px). None si no hay."""
    api = api_pantalla or wp.api_defecto()
    mon = _monitor_para(hmon_o_rect_asistente, api)
    if mon is None:
        return None
    m = _rect(mon.rect)
    barra = wp.barra_tareas(mon.hmon, api)
    if barra is None:
        return None
    barra = _rect(barra)
    if wp.lado_barra(barra, m) != "abajo":
        return None
    if barra not in wp.franjas_reservadas(m, _rect(mon.trabajo)):
        barra = Rect(barra.izq, m.abajo, barra.der, m.abajo + 1)        # auto-oculta: borde fijo
    return Candidata(_hwnd_barra(m, api), barra, True, True)


__all__ = (
    "Candidata", "ApiVentanasWin32", "ApiVentanasNula", "api_defecto", "es_transparente", "parece_asistente",
    "es_elegible", "listar_candidatas", "ocluida_en", "estado_ventana", "encima_de", "barra_asiento",
    "ESTADOS", "MAX_CANDIDATAS", "MAX_PASOS_Z",
)
