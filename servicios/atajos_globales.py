"""
servicios/atajos_globales.py — Atajos de teclado globales sin hooks.

Lune escucha combinaciones como Ctrl+Alt+Shift+L aunque no tenga el foco
(mostrar la asistente, pantalla grande, temporizador rápido…). Se hace con
`RegisterHotKey` de user32, que es lo que Windows ofrece para esto: el sistema
avisa con un WM_HOTKEY cuando se pulsa ESA combinación y nada más. No se lee
el resto del teclado, no se inyecta nada en otros procesos y no hay hooks de
bajo nivel, así que los anticheat no lo ven como un keylogger (es lo que hace
que Mate-Engine sea «Anti Cheat Safe»).

Detalles que mandan en el diseño:

* `RegisterHotKey(NULL, …)` va ligado al HILO que lo llama: el WM_HOTKEY llega
  a la cola de mensajes de ese hilo y solo ese hilo puede hacer
  `UnregisterHotKey`. Por eso `GestorAtajos` tiene un hilo propio con un bucle
  `GetMessageW`, y las altas y bajas se le piden por una cola + un mensaje
  propio (`PostThreadMessageW`). Se para con `PostThreadMessageW(WM_QUIT)`.
* `MOD_NOREPEAT` siempre: mantener la tecla pulsada no dispara el atajo en
  ráfaga.
* En teclados en español AltGr = Ctrl+Alt. Un atajo Ctrl+Alt+E se comería el
  «€» y Ctrl+Alt+Q / Ctrl+Alt+2 la «@». `validar()` avisa y propone añadir
  Shift (los atajos por defecto de Lune son Ctrl+Alt+Shift+…).

El callback `on_atajo(id)` se ejecuta en el hilo de atajos, no en el de Qt: el
adaptador Qt (`ui/atajos_qt.py`) lo reenvía con una señal en cola.

Sin Qt y con user32/kernel32 inyectables, así se prueba sin Windows real.
"""
from __future__ import annotations

import ctypes
import itertools
import logging
import queue
import re
import sys
import threading
from typing import Callable, Dict, Hashable, Optional, Tuple

log = logging.getLogger("lune.atajos")

# ── Constantes de Win32 ────────────────────────────────────────────────────────
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
_MODS_TODOS = MOD_ALT | MOD_CONTROL | MOD_SHIFT | MOD_WIN

WM_QUIT = 0x0012
WM_USER = 0x0400
WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_LUNE_ATAJOS = WM_APP + 0x4C          # «hay órdenes en la cola del gestor»
PM_NOREMOVE = 0x0000

ERROR_HOTKEY_ALREADY_REGISTERED = 1409

VK_F1 = 0x70
VK_F12 = 0x7B
VK_F24 = 0x87

PREFIJO_AVISO = "Aviso:"


# ── Tabla de teclas ────────────────────────────────────────────────────────────
_MODIFICADORES: Dict[str, int] = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "ctl": MOD_CONTROL,
    "alt": MOD_ALT, "option": MOD_ALT,
    "shift": MOD_SHIFT, "mayus": MOD_SHIFT, "mayús": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
    "cmd": MOD_WIN, "os": MOD_WIN,
}
# Nombres de modificadores tal como los da KeyboardEvent.code en JS.
for _lado in ("left", "right"):
    _MODIFICADORES["control" + _lado] = MOD_CONTROL
    _MODIFICADORES["alt" + _lado] = MOD_ALT
    _MODIFICADORES["shift" + _lado] = MOD_SHIFT
    _MODIFICADORES["meta" + _lado] = MOD_WIN
    _MODIFICADORES["os" + _lado] = MOD_WIN

# Nombre canónico → código de tecla virtual.
_TECLAS: Dict[str, int] = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _TECLAS[_c] = ord(_c.upper())
for _d in range(10):
    _TECLAS[str(_d)] = 0x30 + _d
    _TECLAS[f"numpad{_d}"] = 0x60 + _d
for _f in range(1, 25):
    _TECLAS[f"f{_f}"] = VK_F1 + _f - 1
_TECLAS.update({
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pause": 0x13, "printscreen": 0x2C,
    "period": 0xBE, "comma": 0xBC, "minus": 0xBD, "plus": 0xBB,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
})

# Sinónimos (español, símbolos y nombres de KeyboardEvent.code/key de JS).
_SINONIMOS: Dict[str, str] = {
    "espacio": "space", "spacebar": "space",
    "return": "enter", "intro": "enter", "numpadenter": "enter",
    "esc": "escape", "retroceso": "backspace",
    "del": "delete", "supr": "delete", "suprimir": "delete",
    "ins": "insert", "inicio": "home", "fin": "end",
    "pgup": "pageup", "repag": "pageup", "prior": "pageup",
    "pgdn": "pagedown", "avpag": "pagedown", "next": "pagedown",
    "izquierda": "left", "arriba": "up", "derecha": "right", "abajo": "down",
    "arrowleft": "left", "arrowup": "up", "arrowright": "right", "arrowdown": "down",
    "pausa": "pause", "prtsc": "printscreen", "impr": "printscreen", "imppnt": "printscreen",
    ".": "period", "punto": "period",
    ",": "comma", "coma": "comma",
    "-": "minus", "menos": "minus",
    "+": "plus", "mas": "plus", "más": "plus",
    "numpadmultiply": "multiply", "numpadadd": "add", "numpadsubtract": "subtract",
    "numpaddecimal": "decimal", "numpaddivide": "divide",
}

# Código de tecla → nombre para mostrar.
_NOMBRE_VK: Dict[int, str] = {}
for _n, _vk in _TECLAS.items():
    _NOMBRE_VK.setdefault(_vk, _n)
_BONITO = {
    "space": "Espacio", "enter": "Enter", "tab": "Tab", "escape": "Esc",
    "backspace": "Retroceso", "delete": "Supr", "insert": "Insert",
    "home": "Inicio", "end": "Fin", "pageup": "RePág", "pagedown": "AvPág",
    "left": "←", "up": "↑", "right": "→", "down": "↓",
    "pause": "Pausa", "printscreen": "ImprPant",
    "period": ".", "comma": ",", "minus": "-", "plus": "+",
    "multiply": "Num *", "add": "Num +", "subtract": "Num -", "decimal": "Num .",
    "divide": "Num /",
}


def _nombre_tecla(parte: str) -> Optional[str]:
    """Nombre canónico de una tecla escrita por el usuario, o None si no se conoce."""
    p = _SINONIMOS.get(parte, parte)
    if p in _TECLAS:
        return p
    m = re.fullmatch(r"key([a-z])", p)          # KeyboardEvent.code: KeyL
    if m:
        return m.group(1)
    m = re.fullmatch(r"digit(\d)", p)           # KeyboardEvent.code: Digit3
    if m:
        return m.group(1)
    return None


def _escribe(vk: int) -> bool:
    """True si la tecla escribe un carácter (letras, números, signos, espacio)."""
    return (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A or vk == 0x20
            or 0xBA <= vk <= 0xC0 or 0xDB <= vk <= 0xDF or vk == 0xE2)


def _es_f(vk: int) -> bool:
    return VK_F1 <= vk <= VK_F24


# ── Parseo y validación ────────────────────────────────────────────────────────

def parsear_combo(combo: str) -> Tuple[int, int]:
    """
    «ctrl+alt+shift+l» → (MOD_CONTROL|MOD_ALT|MOD_SHIFT, 0x4C).

    Sin distinguir mayúsculas y tolerando espacios alrededor de los «+». Acepta
    letras, dígitos, f1–f24, space, enter, tab, escape, flechas, period, comma,
    minus, plus («ctrl++»), el teclado numérico y los nombres de
    KeyboardEvent.code de JS (KeyL, Digit3, ArrowUp, ControlLeft…), para que el
    botón «Detectar» de la interfaz pueda mandar lo que capture.
    Los mods devueltos NO llevan MOD_NOREPEAT (lo añade el gestor).
    Lanza ValueError con un mensaje para el usuario si no se entiende.
    """
    s = (combo or "").strip().lower()
    if not s:
        raise ValueError("El atajo está vacío.")
    s = re.sub(r"\s*\+\s*", "+", s)
    s = re.sub(r"\s+", "", s)                   # «page up» → «pageup»
    if s == "+":
        s = "plus"
    elif s.endswith("++"):                      # «ctrl++» → la tecla «+»
        s = s[:-2] + "+plus"
    partes = s.split("+")
    if any(not p for p in partes):
        raise ValueError(f"No entiendo el atajo «{combo}»: sobra o falta un «+».")

    mods, vk = 0, None
    for p in partes:
        if p in ("altgr", "altgraph"):
            raise ValueError("AltGr no sirve para atajos globales: usa Ctrl+Alt+Shift.")
        if p in _MODIFICADORES:
            mods |= _MODIFICADORES[p]
            continue
        nombre = _nombre_tecla(p)
        if nombre is None:
            raise ValueError(f"No conozco la tecla «{p}».")
        if vk is not None:
            raise ValueError("Un atajo solo puede tener una tecla además de los modificadores.")
        vk = _TECLAS[nombre]
    if vk is None:
        raise ValueError("Falta la tecla principal (por ejemplo Ctrl+Alt+Shift+L).")
    return mods, vk


def texto_combo(mods: int, vk: int) -> str:
    """(mods, vk) → «Ctrl+Alt+Shift+L», para mostrar en menús y ajustes."""
    trozos = []
    if mods & MOD_CONTROL:
        trozos.append("Ctrl")
    if mods & MOD_ALT:
        trozos.append("Alt")
    if mods & MOD_SHIFT:
        trozos.append("Shift")
    if mods & MOD_WIN:
        trozos.append("Win")
    nombre = _NOMBRE_VK.get(vk, f"0x{vk:02X}")
    trozos.append(_BONITO.get(nombre, nombre.upper()))
    return "+".join(trozos)


def normalizar(combo: str) -> str:
    """Forma canónica para guardar en config: «Shift+CTRL+L» → «ctrl+shift+l»."""
    mods, vk = parsear_combo(combo)
    trozos = [n for m, n in ((MOD_CONTROL, "ctrl"), (MOD_ALT, "alt"),
                             (MOD_SHIFT, "shift"), (MOD_WIN, "win")) if mods & m]
    trozos.append(_NOMBRE_VK.get(vk, f"0x{vk:02X}"))
    return "+".join(trozos)


def comprobar(combo: str) -> Tuple[Optional[str], Optional[str]]:
    """
    (error, aviso) de un atajo. El error impide usarlo; el aviso no (el
    usuario puede quedárselo), pero conviene enseñarlo en la interfaz.
    """
    try:
        mods, vk = parsear_combo(combo)
    except ValueError as e:
        return str(e), None
    texto = texto_combo(mods, vk)
    if vk == VK_F12:
        return ("F12 está reservada por Windows para el depurador y no puede ser "
                "un atajo global."), None
    if not (mods & _MODS_TODOS) and not _es_f(vk):
        return (f"«{texto}» sola no puede ser un atajo global: taparía esa tecla en "
                "todas las aplicaciones. Añade Ctrl, Alt, Shift o Win "
                "(solo F1–F24 pueden ir sin modificador)."), None
    if (mods & _MODS_TODOS) == MOD_SHIFT and _escribe(vk):
        return (f"{texto} escribe un carácter en cualquier programa. "
                "Añade Ctrl o Alt."), None
    if mods & MOD_WIN and mods & MOD_ALT:
        return ("Win+Alt está reservado por Windows (la Xbox Game Bar usa Win+Alt+R, "
                "Win+Alt+G…). Elige otra combinación."), None
    if mods & MOD_CONTROL and mods & MOD_ALT and not mods & MOD_SHIFT and _escribe(vk):
        return None, (f"{PREFIJO_AVISO} en teclados en español Ctrl+Alt es AltGr, así que "
                      f"{texto} puede comerse un carácter (AltGr+E es «€», AltGr+Q o "
                      f"AltGr+2 es «@»). Mejor Ctrl+Alt+Shift+{texto.rsplit('+', 1)[-1]}.")
    return None, None


def validar(combo: str) -> Optional[str]:
    """
    None si el atajo vale tal cual; si no, el texto para el usuario. Los avisos
    (Ctrl+Alt sin Shift) empiezan por «Aviso:» y no impiden registrarlo: usa
    `comprobar()` o `es_aviso()` para distinguirlos de los errores.
    """
    error, aviso = comprobar(combo)
    return error or aviso


def es_aviso(mensaje: Optional[str]) -> bool:
    """True si un mensaje de `validar()` es solo un aviso (el atajo sirve)."""
    return bool(mensaje) and mensaje.startswith(PREFIJO_AVISO)


# ── Gestor con hilo propio ─────────────────────────────────────────────────────

class _MSG(ctypes.Structure):
    """MSG de Win32 (definido a mano para no depender de ctypes.wintypes)."""
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_ulong),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
        ("lPrivate", ctypes.c_ulong),
    ]


def _cargar_win32():
    """user32/kernel32 propios (no los compartidos de ctypes.windll) con argtypes."""
    from ctypes import wintypes as w
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    pmsg = ctypes.POINTER(_MSG)
    u32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
    u32.RegisterHotKey.restype = w.BOOL
    u32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
    u32.UnregisterHotKey.restype = w.BOOL
    u32.GetMessageW.argtypes = [pmsg, w.HWND, w.UINT, w.UINT]
    u32.GetMessageW.restype = w.BOOL
    u32.PeekMessageW.argtypes = [pmsg, w.HWND, w.UINT, w.UINT, w.UINT]
    u32.PeekMessageW.restype = w.BOOL
    u32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
    u32.PostThreadMessageW.restype = w.BOOL
    k32.GetCurrentThreadId.argtypes = []
    k32.GetCurrentThreadId.restype = w.DWORD
    return u32, k32


class _Orden:
    """Petición al hilo de atajos; quien la manda espera a `listo`."""
    __slots__ = ("tipo", "id", "mods", "vk", "listo", "resultado", "cancelada")

    def __init__(self, tipo: str, id_=None, mods: int = 0, vk: int = 0):
        self.tipo, self.id, self.mods, self.vk = tipo, id_, mods, vk
        self.listo = threading.Event()
        self.resultado: Optional[str] = None
        self.cancelada = False


class GestorAtajos:
    """
    Registra atajos globales y llama a `on_atajo(id)` cuando se pulsan.

        g = GestorAtajos(lambda id: print("pulsado", id))
        g.iniciar()
        err = g.registrar("mostrar_lune", "ctrl+alt+shift+l")   # None si fue bien
        ...
        g.detener()

    `id` puede ser cualquier valor hashable (en Lune, el nombre de la acción).
    Se puede registrar antes de `iniciar()`: se guarda y se da de alta al
    arrancar (los fallos quedan en `errores`). `detener()` suelta todos los
    atajos pero recuerda cuáles había, y otro `iniciar()` los vuelve a poner.
    """

    TIEMPO_ESPERA = 2.0

    def __init__(self, on_atajo: Callable[[Hashable], None], *,
                 user32=None, kernel32=None,
                 obtener_error: Optional[Callable[[], int]] = None):
        self._on_atajo = on_atajo
        self._u32, self._k32 = user32, kernel32
        self._obtener_error = obtener_error or getattr(ctypes, "get_last_error", lambda: 0)
        self._lock = threading.Lock()
        self._deseados: Dict[Hashable, Tuple[int, int]] = {}   # id → (mods, vk) que deben estar
        self._nums: Dict[Hashable, int] = {}                    # id → id numérico para Windows
        self._contador = itertools.count(1)
        # Solo los toca el hilo de atajos:
        self._activos: Dict[Hashable, Tuple[int, int]] = {}
        self._por_num: Dict[int, Hashable] = {}
        self._cola: "queue.Queue[_Orden]" = queue.Queue()
        self._hilo: Optional[threading.Thread] = None
        self._tid: Optional[int] = None
        self.errores: Dict[Hashable, str] = {}

    # ── Ciclo de vida ──────────────────────────────────────────────────────
    def activo(self) -> bool:
        """True si el hilo de atajos está vivo y escuchando."""
        h = self._hilo
        return bool(h and h.is_alive() and self._tid is not None)

    def iniciar(self) -> bool:
        """Arranca el hilo y registra lo pendiente. False si no se pudo."""
        if self.activo():
            return True
        if self._u32 is None or self._k32 is None:
            if sys.platform != "win32":
                log.info("Atajos globales: solo existen en Windows")
                return False
            try:
                u32, k32 = _cargar_win32()
            except Exception as e:           # pragma: no cover - Windows raro
                log.warning("Atajos globales: no pude cargar user32: %s", e)
                return False
            self._u32 = self._u32 or u32
            self._k32 = self._k32 or k32
        self._cola = queue.Queue()
        listo = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, args=(listo,),
                                      name="LuneAtajos", daemon=True)
        self._hilo.start()
        listo.wait(self.TIEMPO_ESPERA)
        return self.activo()

    def detener(self) -> None:
        """Suelta todos los atajos (desde su hilo) y para el bucle."""
        hilo, tid = self._hilo, self._tid
        if hilo is None:
            return
        if tid is not None:
            try:
                self._u32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception as e:           # pragma: no cover
                log.warning("Atajos globales: no pude parar el hilo: %s", e)
        if threading.current_thread() is hilo:
            return                            # se llama desde on_atajo: el bucle sale solo
        hilo.join(self.TIEMPO_ESPERA)
        self._hilo = None

    # ── Altas y bajas ──────────────────────────────────────────────────────
    def registrar(self, id_: Hashable, combo: str) -> Optional[str]:
        """
        Da de alta (o cambia) el atajo `id_`. None si fue bien; si no, el
        motivo para enseñárselo al usuario (combinación inválida, ya usada por
        otro atajo de Lune o por otra aplicación…). Los avisos de AltGr no
        impiden registrar.
        """
        error, _aviso = comprobar(combo)
        if error:
            return error
        mods, vk = parsear_combo(combo)
        with self._lock:
            for otro, par in self._deseados.items():
                if otro != id_ and par == (mods, vk):
                    return f"{texto_combo(mods, vk)} ya lo usa «{otro}»."
            if not self.activo():
                self._deseados[id_] = (mods, vk)
                self._nums.setdefault(id_, next(self._contador))
                self.errores.pop(id_, None)
                return None
        return self._pedir(_Orden("registrar", id_, mods, vk))

    def quitar(self, id_: Hashable) -> None:
        """Da de baja el atajo `id_` (si no existe, no pasa nada)."""
        if not self.activo():
            with self._lock:
                self._deseados.pop(id_, None)
                self.errores.pop(id_, None)
            return
        self._pedir(_Orden("quitar", id_))

    def quitar_todos(self) -> None:
        """Da de baja todos los atajos."""
        if not self.activo():
            with self._lock:
                self._deseados.clear()
                self.errores.clear()
            return
        self._pedir(_Orden("quitar_todos"))

    def registrados(self) -> Dict[Hashable, str]:
        """{id: «Ctrl+Alt+Shift+L»} de los atajos que Lune quiere tener."""
        with self._lock:
            return {k: texto_combo(m, v) for k, (m, v) in self._deseados.items()}

    # ── Comunicación con el hilo ───────────────────────────────────────────
    def _pedir(self, orden: _Orden) -> Optional[str]:
        """Manda la orden al hilo de atajos y espera su resultado."""
        if threading.current_thread() is self._hilo:
            self._aplicar(orden)              # desde on_atajo: ya estamos en el hilo
            return orden.resultado
        tid = self._tid
        self._cola.put(orden)
        ok = False
        if tid is not None:
            try:
                ok = bool(self._u32.PostThreadMessageW(tid, WM_LUNE_ATAJOS, 0, 0))
            except Exception:
                ok = False
        if not ok or not orden.listo.wait(self.TIEMPO_ESPERA):
            orden.cancelada = True
            return "El hilo de atajos no responde; reinicia Lune si sigue pasando."
        return orden.resultado

    def _vaciar_cola(self, cancelar: bool = False) -> None:
        while True:
            try:
                orden = self._cola.get_nowait()
            except queue.Empty:
                return
            if orden.cancelada:
                continue
            if cancelar:
                orden.resultado = "Los atajos globales se están deteniendo."
            else:
                try:
                    self._aplicar(orden)
                except Exception as e:        # pragma: no cover - defensivo
                    orden.resultado = f"Error interno de atajos: {e}"
            orden.listo.set()

    # ── Lo que corre en el hilo de atajos ──────────────────────────────────
    def _bucle(self, listo: threading.Event) -> None:
        u32 = self._u32
        msg = _MSG()
        pmsg = ctypes.pointer(msg)
        try:
            tid = int(self._k32.GetCurrentThreadId())
            # Crea la cola de mensajes del hilo antes de que nadie le escriba:
            # PostThreadMessageW falla si el hilo todavía no tiene cola.
            u32.PeekMessageW(pmsg, None, WM_USER, WM_USER, PM_NOREMOVE)
            # Foto de lo pendiente y alta del tid en el mismo candado que usa
            # registrar(): o su atajo entra en la foto, o ya ve el hilo activo
            # y lo pide por la cola. Nunca se pierde uno entre medias.
            with self._lock:
                pendientes = list(self._deseados.items())
                self._tid = tid
            for id_, (mods, vk) in pendientes:
                self._aplicar(_Orden("registrar", id_, mods, vk))
        except Exception as e:
            log.warning("Atajos globales: no arrancó el hilo: %s", e)
            self._tid = None
            listo.set()
            return
        listo.set()
        try:
            while True:
                r = u32.GetMessageW(pmsg, None, 0, 0)
                if r == 0 or r == -1:
                    break
                if msg.message == WM_HOTKEY:
                    self._disparar(int(msg.wParam))
                elif msg.message == WM_LUNE_ATAJOS:
                    self._vaciar_cola()
        finally:
            for num in [n for n, _ in self._activos.values()]:
                try:
                    u32.UnregisterHotKey(None, num)
                except Exception:
                    pass
            self._activos.clear()
            self._por_num.clear()
            with self._lock:
                self._tid = None
            self._vaciar_cola(cancelar=True)

    def _disparar(self, num: int) -> None:
        id_ = self._por_num.get(num)
        if id_ is None:
            return
        try:
            self._on_atajo(id_)
        except Exception:
            log.exception("Atajos globales: falló la acción de «%s»", id_)

    def _aplicar(self, orden: _Orden) -> None:
        if orden.tipo == "registrar":
            orden.resultado = self._alta(orden.id, orden.mods, orden.vk)
        elif orden.tipo == "quitar":
            self._baja(orden.id)
            with self._lock:
                self._deseados.pop(orden.id, None)
                self.errores.pop(orden.id, None)
        elif orden.tipo == "quitar_todos":
            for id_ in list(self._activos):
                self._baja(id_)
            with self._lock:
                self._deseados.clear()
                self.errores.clear()

    def _alta(self, id_: Hashable, mods: int, vk: int) -> Optional[str]:
        with self._lock:
            num = self._nums.setdefault(id_, next(self._contador))
        anterior = self._activos.get(id_)
        if anterior and anterior[1] == (mods, vk):
            return None                        # ya estaba así
        if anterior:
            self._baja(id_)
        if self._u32.RegisterHotKey(None, num, mods | MOD_NOREPEAT, vk):
            self._activos[id_] = (num, (mods, vk))
            self._por_num[num] = id_
            with self._lock:
                self._deseados[id_] = (mods, vk)
                self.errores.pop(id_, None)
            return None
        codigo = int(self._obtener_error() or 0)
        texto = texto_combo(mods, vk)
        if codigo == ERROR_HOTKEY_ALREADY_REGISTERED:
            error = f"{texto} ya lo usa otra aplicación (o Windows). Elige otro atajo."
        else:
            error = f"Windows no dejó registrar {texto} (error {codigo})."
        if anterior:                           # deja el atajo que había
            m0, v0 = anterior[1]
            if self._u32.RegisterHotKey(None, num, m0 | MOD_NOREPEAT, v0):
                self._activos[id_] = (num, (m0, v0))
                self._por_num[num] = id_
        else:
            with self._lock:
                self._deseados.pop(id_, None)
        with self._lock:
            self.errores[id_] = error
        log.info("Atajos globales: %s", error)
        return error

    def _baja(self, id_: Hashable) -> None:
        actual = self._activos.pop(id_, None)
        if not actual:
            return
        num = actual[0]
        self._por_num.pop(num, None)
        try:
            self._u32.UnregisterHotKey(None, num)
        except Exception:
            pass
