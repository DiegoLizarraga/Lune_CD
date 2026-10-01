"""
servicios/win_pantalla.py — Qué hay en la pantalla: ventana activa, monitores y barra de tareas.

PARA QUÉ SIRVE
--------------
Es la base común del modo juego (¿hay algo a pantalla completa?), de sentarse
en la barra de tareas (¿dónde está la barra de ESTE monitor?), de la pantalla
grande y del detector de música (¿este proceso es la propia Lune?). Cada
paquete pregunta aquí en vez de repetir su propio ctypes.

QUÉ OFRECE
----------
- `estado_notificaciones()`: `SHQueryUserNotificationState` (QUNS). 2 = ocupado
  (también salta con un vídeo del navegador a pantalla completa), 3 = juego
  Direct3D a pantalla completa, 4 = presentación. `quns_indica_juego()` aplica
  las reglas de cuándo fiarse del 2.
- `ventana_primer_plano()` → `InfoVentana` con hwnd, pid, clase, título, rect,
  rect de SU monitor, estilo y nombre del exe. El título es texto NO fiable
  (lo pone cualquier programa): si acaba en un prompt, hay que neutralizarlo.
- `es_pantalla_completa(info, tol=2)`: los cuatro bordes a ±2 px de su monitor,
  como Mate-Engine. Una ventana maximizada con marco sobresale unos 8 px y no
  cuenta; `tiene_titulo()` y `es_escritorio()` completan la regla del modo juego.
- `es_de_lune(pid)`: el proceso propio y sus hijos QtWebEngineProcess (con
  caché de unos segundos). Solo esos hijos: si Lune lanza un juego con una
  herramienta, ese juego es hijo suyo y NO debe contar como Lune.
- `barra_tareas(hmon)` → `Rect` o None: la franja que el monitor reserva
  (rcMonitor − rcWork); si la barra está auto-oculta, la ventana
  Shell_TrayWnd / Shell_SecondaryTrayWnd que cae en ese monitor.
- `monitores()`, `monitor_de_ventana(hwnd)`, `lado_barra()`.
- `ventanas_visibles()` → `VentanaVisible(hwnd, pid, titulo)` de las ventanas
  de primer nivel visibles, con título y sin WS_EX_TOOLWINDOW (lo que sale en
  Alt-Tab, más o menos): para el «Añadir app» del modo juego.
- `pids_propios()`: los pids sobre los que Lune puede ACTUAR (prioridad,
  recorte de RAM): el propio y sus hijos QtWebEngineProcess, comprobados dos
  veces. Ningún otro, aunque sea hijo suyo (un juego lanzado por una herramienta).

PROCESOS AJENOS
---------------
Del proceso de otra ventana solo se pide el nombre (`psutil.Process(pid).name()`)
y, para la regla de rutas del modo juego, `ruta_proceso()` (la ruta del exe).
Las dos abren como mucho un handle de consulta limitada, sin permiso de leer
memoria. La línea de comandos de procesos ajenos no se lee nunca.

COORDENADAS
-----------
Todo sale en las coordenadas del hilo que llama (px físicos si el proceso es
consciente de DPI por monitor, como con Qt 6; virtualizadas si no). Compara
solo rects obtenidos desde el mismo hilo.

Todas las funciones aceptan un objeto `api` inyectable (ver `ApiPantallaWin32`)
para probarlas sin pantalla. Fuera de Windows responden vacío sin fallar.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from typing import Callable, List, NamedTuple, Optional, Set, Tuple

# Valores de QUERY_USER_NOTIFICATION_STATE.
QUNS_NOT_PRESENT = 1
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_ACCEPTS_NOTIFICATIONS = 5
QUNS_QUIET_TIME = 6
QUNS_APP = 7

WS_CAPTION = 0x00C00000          # WS_BORDER | WS_DLGFRAME
WS_EX_TOOLWINDOW = 0x00000080
GWL_STYLE = -16
GWL_EXSTYLE = -20
MAX_VENTANAS = 512               # tope de ventanas_visibles()
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
ABM_GETSTATE = 4
ABS_AUTOHIDE = 1

CLASES_BARRA = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")
CLASES_ESCRITORIO = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})
HIJOS_DE_LUNE = ("qtwebengineprocess",)       # prefijo del nombre, en minúsculas
# Los QtWebEngineProcess casi no cambian: cada 30 s basta (antes 5 s: una instantánea de
# todos los procesos cada ~6 s entre el modo juego y el detector de música). Al crear,
# cerrar, enseñar u ocultar la asistente, invalidar_pids() fuerza el recálculo.
TTL_PIDS_S = 30.0

_MASCARA_32 = 0xFFFFFFFF


# ── Tipos ─────────────────────────────────────────────────────────────────────

class Rect(NamedTuple):
    """Rectángulo de Win32: `der` y `abajo` quedan fuera, como en RECT."""
    izq: int
    arriba: int
    der: int
    abajo: int

    @property
    def ancho(self) -> int:
        return self.der - self.izq

    @property
    def alto(self) -> int:
        return self.abajo - self.arriba

    @property
    def vacio(self) -> bool:
        return self.ancho <= 0 or self.alto <= 0

    @property
    def area(self) -> int:
        return 0 if self.vacio else self.ancho * self.alto

    @property
    def centro(self) -> Tuple[float, float]:
        return ((self.izq + self.der) / 2.0, (self.arriba + self.abajo) / 2.0)

    def interseccion(self, otro: "Rect") -> "Rect":
        """La parte común (puede salir vacía: mira `.vacio`)."""
        o = _como_rect(otro)
        return Rect(max(self.izq, o.izq), max(self.arriba, o.arriba),
                    min(self.der, o.der), min(self.abajo, o.abajo))

    def contiene(self, x: float, y: float) -> bool:
        return self.izq <= x < self.der and self.arriba <= y < self.abajo


RECT_VACIO = Rect(0, 0, 0, 0)


class Monitor(NamedTuple):
    hmon: int
    rect: Rect            # rcMonitor: el monitor entero, barra incluida
    trabajo: Rect         # rcWork: sin la barra de tareas ni otras appbars
    principal: bool
    nombre: str           # \\.\DISPLAY1 ...


class InfoVentana(NamedTuple):
    hwnd: int
    pid: int
    clase: str
    titulo: str           # texto NO fiable: lo escribe el otro programa
    rect: Rect
    rect_monitor: Rect    # rcMonitor del monitor donde está la ventana
    estilo: int           # GWL_STYLE (32 bits sin signo)
    exe: str              # nombre del ejecutable (p. ej. "javaw.exe"), "" si no se pudo
    hmon: int = 0


class VentanaVisible(NamedTuple):
    hwnd: int
    pid: int
    titulo: str           # texto NO fiable: lo escribe el otro programa


def _como_rect(r) -> Rect:
    return r if isinstance(r, Rect) else Rect(*(int(v) for v in r))


# ── Estructuras de Win32 ──────────────────────────────────────────────────────

class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT), ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


_FIRMA_ENUM_MONITORES = (wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                         ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


def _tipo_enum_monitores():
    # WINFUNCTYPE solo existe en Windows; fuera se usa CFUNCTYPE (da igual: no se llama).
    fabrica = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return fabrica(*_FIRMA_ENUM_MONITORES)


def _tipo_enum_ventanas():
    fabrica = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return fabrica(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _rect_win(r) -> Rect:
    return Rect(int(r.left), int(r.top), int(r.right), int(r.bottom))


# ── APIs ──────────────────────────────────────────────────────────────────────

class _ProcesosPsutil:
    """Lo que se pregunta a psutil: igual en Windows y fuera."""

    def pid_propio(self) -> int:
        return os.getpid()

    def nombre_proceso(self, pid: int) -> str:
        try:
            import psutil
            return psutil.Process(int(pid)).name() or ""
        except Exception:
            return ""

    def ruta_proceso(self, pid: int) -> str:
        try:
            import psutil
            return psutil.Process(int(pid)).exe() or ""
        except Exception:
            return ""

    def hijos(self, pid: int) -> List[Tuple[int, str]]:
        """(pid, nombre) de los descendientes de `pid`. Son procesos propios."""
        try:
            import psutil
            procesos = psutil.Process(int(pid)).children(recursive=True)
        except Exception:
            return []
        salida = []
        for p in procesos:
            try:
                salida.append((int(p.pid), p.name() or ""))
            except Exception:
                continue
        return salida


class ApiPantallaNula(_ProcesosPsutil):
    """Fuera de Windows: sin ventanas, sin monitores, sin barra."""

    def estado_notificaciones(self) -> Optional[int]:
        return None

    def ventana_activa(self) -> int:
        return 0

    def pid_ventana(self, hwnd: int) -> int:
        return 0

    def clase_ventana(self, hwnd: int) -> str:
        return ""

    def titulo_ventana(self, hwnd: int) -> str:
        return ""

    def rect_ventana(self, hwnd: int) -> Optional[Rect]:
        return None

    def estilo_ventana(self, hwnd: int) -> int:
        return 0

    def monitor_de_ventana(self, hwnd: int) -> int:
        return 0

    def info_monitor(self, hmon: int) -> Optional[Monitor]:
        return None

    def lista_monitores(self) -> List[int]:
        return []

    def buscar_ventanas(self, clase: str) -> List[int]:
        return []

    def barra_auto_oculta(self) -> bool:
        return False

    def ventanas_visibles(self) -> List[Tuple[int, int, str]]:
        return []


class ApiPantallaWin32(_ProcesosPsutil):
    """user32 + shell32 con ctypes. Las DLL se pueden inyectar en los tests."""

    def __init__(self, user32=None, shell32=None):
        self._u = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        self._s = shell32 if shell32 is not None else ctypes.WinDLL("shell32", use_last_error=True)
        self._enum_tipo = _tipo_enum_monitores()
        self._firmar()

    def _firmar(self):
        u, s, H = self._u, self._s, wintypes.HWND
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = H
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetClassNameW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowTextLengthW.argtypes = [H]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.GetWindowLongW.argtypes = [H, ctypes.c_int]
        u.GetWindowLongW.restype = wintypes.LONG
        u.MonitorFromWindow.argtypes = [H, wintypes.DWORD]
        u.MonitorFromWindow.restype = wintypes.HMONITOR
        u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
        u.GetMonitorInfoW.restype = wintypes.BOOL
        u.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                          self._enum_tipo, wintypes.LPARAM]
        u.EnumDisplayMonitors.restype = wintypes.BOOL
        u.FindWindowExW.argtypes = [H, H, wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.FindWindowExW.restype = H
        s.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
        s.SHQueryUserNotificationState.restype = ctypes.c_long       # HRESULT sin excepción
        s.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
        s.SHAppBarMessage.restype = ctypes.c_size_t

    def estado_notificaciones(self) -> Optional[int]:
        v = ctypes.c_int(0)
        if int(self._s.SHQueryUserNotificationState(ctypes.byref(v))) != 0:
            return None
        return int(v.value)

    def ventana_activa(self) -> int:
        return int(self._u.GetForegroundWindow() or 0)

    def pid_ventana(self, hwnd: int) -> int:
        pid = wintypes.DWORD(0)
        self._u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def clase_ventana(self, hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        return buf.value if self._u.GetClassNameW(hwnd, buf, 256) > 0 else ""

    def titulo_ventana(self, hwnd: int) -> str:
        n = int(self._u.GetWindowTextLengthW(hwnd))
        if n <= 0:
            return ""
        n = min(n, 1024)
        buf = ctypes.create_unicode_buffer(n + 1)
        self._u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def rect_ventana(self, hwnd: int) -> Optional[Rect]:
        r = wintypes.RECT()
        if not self._u.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        return _rect_win(r)

    def estilo_ventana(self, hwnd: int) -> int:
        return int(self._u.GetWindowLongW(hwnd, GWL_STYLE)) & _MASCARA_32

    def monitor_de_ventana(self, hwnd: int) -> int:
        return int(self._u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0)

    def info_monitor(self, hmon: int) -> Optional[Monitor]:
        if not hmon:
            return None
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not self._u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        return Monitor(int(hmon), _rect_win(mi.rcMonitor), _rect_win(mi.rcWork),
                       bool(mi.dwFlags & MONITORINFOF_PRIMARY), str(mi.szDevice))

    def lista_monitores(self) -> List[int]:
        encontrados: List[int] = []

        def _cada(hmon, _hdc, _prect, _lparam):
            if hmon:
                encontrados.append(int(hmon))
            return True

        callback = self._enum_tipo(_cada)          # vivo hasta que vuelve la llamada
        self._u.EnumDisplayMonitors(None, None, callback, 0)
        return encontrados

    def buscar_ventanas(self, clase: str) -> List[int]:
        """Todas las ventanas de primer nivel de esa clase (hay una barra secundaria por monitor)."""
        salida: List[int] = []
        h = None
        for _ in range(16):
            h = self._u.FindWindowExW(None, h, clase, None)
            if not h:
                break
            salida.append(int(h))
        return salida

    def barra_auto_oculta(self) -> bool:
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        return bool(int(self._s.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd))) & ABS_AUTOHIDE)

    def _firmar_enum_ventanas(self):
        """Firmas de EnumWindows e IsWindowVisible, al primer uso (las DLL falsas de
        los tests más viejos no las traen)."""
        if getattr(self, "_enum_ventanas_tipo", None) is not None:
            return
        u, H = self._u, wintypes.HWND
        tipo = _tipo_enum_ventanas()
        u.EnumWindows.argtypes = [tipo, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [H]
        u.IsWindowVisible.restype = wintypes.BOOL
        self._enum_ventanas_tipo = tipo

    def ventanas_visibles(self) -> List[Tuple[int, int, str]]:
        """(hwnd, pid, título) de las ventanas de primer nivel visibles, con título
        y sin WS_EX_TOOLWINDOW. Solo lee: estilo, título y pid de cada una."""
        self._firmar_enum_ventanas()
        salida: List[Tuple[int, int, str]] = []

        def _cada(hwnd, _lparam):
            try:
                if not hwnd or not self._u.IsWindowVisible(hwnd):
                    return True
                ex = int(self._u.GetWindowLongW(hwnd, GWL_EXSTYLE)) & _MASCARA_32
                if ex & WS_EX_TOOLWINDOW:
                    return True
                titulo = self.titulo_ventana(hwnd)
                if titulo:
                    salida.append((int(hwnd), self.pid_ventana(hwnd), titulo))
            except Exception:
                pass
            return len(salida) < MAX_VENTANAS

        callback = self._enum_ventanas_tipo(_cada)     # vivo hasta que vuelve la llamada
        self._u.EnumWindows(callback, 0)
        return salida


_api_defecto = None


def api_defecto():
    """La API real en Windows (una por proceso) y la nula en el resto."""
    global _api_defecto
    if _api_defecto is None:
        if sys.platform == "win32":
            try:
                _api_defecto = ApiPantallaWin32()
            except Exception:
                _api_defecto = ApiPantallaNula()
        else:
            _api_defecto = ApiPantallaNula()
    return _api_defecto


# ── Notificaciones (QUNS) ─────────────────────────────────────────────────────

def estado_notificaciones(api=None) -> int:
    """Valor QUNS (1..7), o 0 si no se pudo leer."""
    api = api or api_defecto()
    try:
        v = api.estado_notificaciones()
    except Exception:
        return 0
    return int(v) if v else 0


def quns_indica_juego(estado: int, incluir_videos: bool = True,
                      lune_a_pantalla_completa: bool = False) -> bool:
    """
    ¿El estado QUNS basta para decir «hay un juego o una presentación»?
    3 (Direct3D a pantalla completa) y 4 (presentación) siempre. 2 (ocupado)
    también salta con un vídeo del navegador a pantalla completa, así que solo
    cuenta con `incluir_videos`; y como no se puede excluir por pid, se ignora
    mientras la propia Lune esté a pantalla completa (pantalla grande o
    salvapantallas), para no entrar en un bucle de ocultarse.
    """
    if estado in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE):
        return True
    if estado == QUNS_BUSY:
        return bool(incluir_videos) and not lune_a_pantalla_completa
    return False


# ── Ventana en primer plano ───────────────────────────────────────────────────

def ventana_primer_plano(api=None) -> Optional[InfoVentana]:
    """La ventana activa con los datos del modo juego, o None si no hay."""
    api = api or api_defecto()
    try:
        hwnd = int(api.ventana_activa() or 0)
        if not hwnd:
            return None
        pid = int(api.pid_ventana(hwnd) or 0)
        hmon = int(api.monitor_de_ventana(hwnd) or 0)
        mon = api.info_monitor(hmon) if hmon else None
        rect = api.rect_ventana(hwnd)
        return InfoVentana(
            hwnd=hwnd,
            pid=pid,
            clase=api.clase_ventana(hwnd) or "",
            titulo=api.titulo_ventana(hwnd) or "",
            rect=_como_rect(rect) if rect else RECT_VACIO,
            rect_monitor=_como_rect(mon.rect) if mon else RECT_VACIO,
            estilo=int(api.estilo_ventana(hwnd) or 0) & _MASCARA_32,
            exe=(api.nombre_proceso(pid) or "") if pid else "",
            hmon=hmon,
        )
    except Exception:
        return None


def es_pantalla_completa(info: Optional[InfoVentana], tol: int = 2) -> bool:
    """Los cuatro bordes de la ventana a ±`tol` px de los de SU monitor."""
    if info is None:
        return False
    r, m = _como_rect(info.rect), _como_rect(info.rect_monitor)
    if m.vacio or r.vacio:
        return False
    return all(abs(a - b) <= tol for a, b in zip(r, m))


def tiene_titulo(info: Optional[InfoVentana]) -> bool:
    """Tiene barra de título (WS_CAPTION completo). Los juegos sin bordes no."""
    return info is not None and (int(info.estilo) & WS_CAPTION) == WS_CAPTION


def es_escritorio(info: Optional[InfoVentana]) -> bool:
    """El fondo de escritorio o la barra de tareas: cubren el monitor y no son juegos."""
    return info is not None and info.clase in CLASES_ESCRITORIO


def ruta_proceso(pid: int, api=None) -> str:
    """Ruta completa del exe (regla `steamapps\\common`…). Handle de consulta
    limitada, sin leer memoria. "" si no se pudo."""
    api = api or api_defecto()
    try:
        return api.ruta_proceso(int(pid)) or ""
    except Exception:
        return ""


# ── ¿Es Lune? ─────────────────────────────────────────────────────────────────

def _es_hijo_de_lune(nombre: str) -> bool:
    n = (nombre or "").lower()
    return any(n.startswith(p) for p in HIJOS_DE_LUNE)


_gen_pids = 0       # sube con invalidar_pids(): todos los PidsLune recalculan sus hijos


def invalidar_pids() -> None:
    """La asistente se creó, se cerró o cambió de visibilidad (una página nueva o
    descartada es un QtWebEngineProcess que aparece o se va): la próxima consulta de
    cualquier PidsLune (modo juego, música, recorte de RAM) vuelve a listar los hijos."""
    global _gen_pids
    _gen_pids += 1


class PidsLune:
    """El pid propio más los hijos QtWebEngineProcess, recalculados cada `ttl` s
    o tras invalidar_pids()."""

    def __init__(self, api=None, ttl: float = TTL_PIDS_S, reloj: Callable[[], float] = time.monotonic):
        self.api = api or api_defecto()
        self.ttl = ttl
        self._reloj = reloj
        self._hijos: Set[int] = set()
        self._t: Optional[float] = None
        self._gen = _gen_pids

    def pids(self) -> Set[int]:
        ahora = self._reloj()
        gen = _gen_pids
        if self._t is None or ahora - self._t >= self.ttl or gen != self._gen:
            try:
                hijos = self.api.hijos(self.api.pid_propio())
            except Exception:
                hijos = []
            self._hijos = {int(pid) for pid, nombre in hijos if _es_hijo_de_lune(nombre)}
            self._t = ahora
            self._gen = gen
        return {int(self.api.pid_propio())} | self._hijos

    def contiene(self, pid: int) -> bool:
        if not pid:
            return False
        if int(pid) == int(self.api.pid_propio()):
            return True
        return int(pid) in self.pids()


_pids_defecto: Optional[PidsLune] = None


def es_de_lune(pid: int, api=None) -> bool:
    """True si `pid` es este proceso o uno de sus QtWebEngineProcess."""
    global _pids_defecto
    api = api or api_defecto()
    if _pids_defecto is None or _pids_defecto.api is not api:
        _pids_defecto = PidsLune(api)
    return _pids_defecto.contiene(pid)


def pids_propios(pids=None, psutil_mod=None) -> List[int]:
    """
    Los pids sobre los que Lune puede ACTUAR (bajar la prioridad, recortar la RAM):
    el propio y sus hijos QtWebEngineProcess, comprobados dos veces. Un pid vale
    solo si está en `pids` (un `PidsLune`, o un conjunto de pids) Y es el propio o
    un descendiente suyo que psutil ve con nombre de QtWebEngineProcess. Así un
    juego lanzado por una herramienta (hijo de Lune, pero no WebEngine) o un pid
    ajeno colado en la lista no se tocan nunca. El propio va siempre el primero.
    """
    if pids is None:
        pids = PidsLune()
    if hasattr(pids, "pids"):
        try:
            propio = int(pids.api.pid_propio())
        except Exception:
            propio = os.getpid()
        try:
            candidatos = {int(p) for p in pids.pids()}
        except Exception:
            candidatos = {propio}
    else:
        propio = os.getpid()
        try:
            candidatos = {int(p) for p in pids}
        except Exception:
            candidatos = set()
    salida = [propio] if propio in candidatos else []
    resto = sorted(candidatos - {propio})
    if not resto:
        return salida
    ps = psutil_mod
    if ps is None:
        try:
            import psutil as ps
        except Exception:
            return salida
    try:
        hijos = {}
        for p in ps.Process(propio).children(recursive=True):
            try:
                hijos[int(p.pid)] = p.name() or ""
            except Exception:
                continue
    except Exception:
        return salida
    salida.extend(pid for pid in resto if pid in hijos and _es_hijo_de_lune(hijos[pid]))
    return salida


# ── Ventanas visibles (para «Añadir app» del modo juego) ──────────────────────

def ventanas_visibles(api=None) -> List[VentanaVisible]:
    """Ventanas de primer nivel visibles, con título y sin WS_EX_TOOLWINDOW. Solo
    lectura (estilo, título, pid); el título es texto NO fiable."""
    api = api or api_defecto()
    try:
        crudas = api.ventanas_visibles() or []
    except Exception:
        return []
    salida = []
    for v in crudas[:MAX_VENTANAS]:
        try:
            hwnd, pid, titulo = v
            salida.append(VentanaVisible(int(hwnd), int(pid or 0), str(titulo or "")))
        except Exception:
            continue
    return salida


# ── Monitores ─────────────────────────────────────────────────────────────────

def monitores(api=None) -> List[Monitor]:
    """Todos los monitores, en el orden de EnumDisplayMonitors."""
    api = api or api_defecto()
    try:
        hmons = api.lista_monitores()
    except Exception:
        return []
    salida = []
    for h in hmons:
        try:
            m = api.info_monitor(h)
        except Exception:
            m = None
        if m is not None:
            salida.append(m)
    return salida


def monitor_de_ventana(hwnd: int, api=None) -> Optional[Monitor]:
    """El monitor donde está (o más cerca está) la ventana."""
    api = api or api_defecto()
    try:
        hmon = int(api.monitor_de_ventana(int(hwnd)) or 0)
        return api.info_monitor(hmon) if hmon else None
    except Exception:
        return None


# ── Barra de tareas ───────────────────────────────────────────────────────────

def franjas_reservadas(monitor: Rect, trabajo: Rect) -> List[Rect]:
    """Lo que el área de trabajo le quita al monitor, lado por lado."""
    m, t = _como_rect(monitor), _como_rect(trabajo)
    franjas = []
    if t.arriba > m.arriba:
        franjas.append(Rect(m.izq, m.arriba, m.der, t.arriba))
    if t.abajo < m.abajo:
        franjas.append(Rect(m.izq, t.abajo, m.der, m.abajo))
    if t.izq > m.izq:
        franjas.append(Rect(m.izq, m.arriba, t.izq, m.abajo))
    if t.der < m.der:
        franjas.append(Rect(t.der, m.arriba, m.der, m.abajo))
    return [f for f in franjas if not f.vacio]


def _bandejas_en(monitor: Rect, api) -> List[Rect]:
    """Rects (recortados al monitor) de las ventanas de barra que caen en él."""
    salida = []
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
            if not r:
                continue
            dentro = _como_rect(r).interseccion(monitor)
            if not dentro.vacio:
                salida.append(dentro)
    return salida


def barra_tareas(hmon, api=None) -> Optional[Rect]:
    """
    Rect de la barra de tareas del monitor `hmon` (entero o `Monitor`), o None
    si ese monitor no tiene barra.

    1. Si el monitor reserva franjas (rcMonitor − rcWork) y alguna coincide con
       una ventana de barra, esa franja.
    2. Si la barra está auto-oculta, la ventana de barra de ese monitor
       recortada a él (oculta queda un hilo de 1-2 px en el borde).
    3. Si hay franjas pero no se encontró la ventana, la franja más grande.
    """
    api = api or api_defecto()
    hmon = int(getattr(hmon, "hmon", hmon) or 0)
    if not hmon:
        return None
    try:
        mon = api.info_monitor(hmon)
    except Exception:
        mon = None
    if mon is None:
        return None
    m = _como_rect(mon.rect)
    franjas = franjas_reservadas(m, _como_rect(mon.trabajo))
    bandejas = _bandejas_en(m, api)

    if franjas and bandejas:
        def solape(f: Rect) -> int:
            return max(f.interseccion(b).area for b in bandejas)
        mejor = max(franjas, key=lambda f: (solape(f), f.area))
        if solape(mejor) > 0:
            return mejor
    try:
        oculta = bool(api.barra_auto_oculta())
    except Exception:
        oculta = False
    if oculta and bandejas:
        return max(bandejas, key=lambda b: b.area)
    if franjas:
        return max(franjas, key=lambda f: f.area)
    return None


def lado_barra(barra: Rect, monitor: Rect) -> str:
    """'abajo', 'arriba', 'izq' o 'der': el borde del monitor donde está la barra."""
    b, m = _como_rect(barra), _como_rect(monitor)
    if b.ancho >= b.alto:
        return "arriba" if abs(b.arriba - m.arriba) < abs(m.abajo - b.abajo) else "abajo"
    return "izq" if abs(b.izq - m.izq) < abs(m.der - b.der) else "der"
