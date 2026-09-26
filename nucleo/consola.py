"""
nucleo/consola.py — La terminal del modo patata, compartida entre hilos.

PARA QUÉ SIRVE
--------------
En patata varias cosas quieren la consola a la vez: el chat (leer lo que
escribes y pintar la respuesta en streaming), una alarma que suena desde otro
hilo («Enter para apagarla»), una aprobación del modelo («¿Lo hago? s/N»)...
Si cada una llamara a `input()` habría dos consumidores de stdin peleándose por
la misma línea, y un aviso impreso a mitad del prompt dejaría la pantalla
revuelta. `ConsolaAsincrona` lo resuelve con:

- UN solo despachador de entrada (un hilo lector). Cada línea escrita va:
    · al primer RECLAMO pendiente, si hay (`reclamar(fn)` / `preguntar()`), o
    · al chat, que la recoge con `leer_linea()` (bloqueante).
  Así «la siguiente línea apaga la alarma» y el chat nunca se roban líneas.
- UN solo lock de salida, `consola.lock` (reentrante). Lo toman `escribir()`,
  `imprimir()` y `aviso()`; el streaming de la respuesta debe escribir con
  `consola.escribir(token)` para no mezclarse con los avisos.
- `aviso(texto)`: borra la línea en curso (`\\r\\033[2K`, y las de encima si
  la línea da la vuelta), imprime el aviso y vuelve a pintar lo que había: el
  prompt con lo que llevabas escrito, o la frase a medias del streaming.
- `titulo(txt)` (`SetConsoleTitleW`) y `parpadear()` (`FlashWindowEx`) para
  avisar aunque la consola esté minimizada. Activa las secuencias VT al crearse.
- Título por CAPAS (`titulo_capa(capa, texto, prioridad)`): varias piezas
  quieren el título a la vez (alarma 60, modo juego 50, baile 20, salvapantallas
  10). Se enseña la capa de mayor prioridad (a igualdad, la última puesta); al
  quitarla (`texto=None`) se repinta la siguiente y, sin capas, el título normal
  de `titulo()` (o `titulo_defecto` si nadie lo puso: nunca se queda puesta una
  capa ya quitada).
- `reclamar()` devuelve `cancelar()` con `cancelar.cambiar_prompt(texto)`: el
  prompt del reclamo cambia en vivo (la línea del baile, la cuenta atrás de la
  alarma). `prioridad` ordena los reclamos (el baile usa una baja: una alarma
  o una aprobación se quedan antes su Enter).

LECTURA
-------
En una consola de Windows de verdad se lee tecla a tecla con
`ReadConsoleInputW` (modo «teclas»): así se sabe lo que llevas escrito y el
aviso lo repinta. Además lo que tecleas mientras Lune está respondiendo no se
cruza con su texto: se guarda y aparece al volver el prompt. Hay retroceso,
Esc (borra la línea) y flechas ↑/↓ para el historial.
Si la entrada no es una consola (tubería, tests, otro sistema) se leen líneas
de `stdin` (modo «lineas»): el aviso solo puede repintar el prompt.

Nada de ganchos globales: solo se lee la entrada de ESTA consola.

Uso típico (patata):

    consola = ConsolaAsincrona("tú > ")
    linea = consola.leer_linea()                 # bloquea hasta Enter
    consola.escribir(token)                      # streaming, con el mismo lock
    consola.aviso("⏰ Alarma: sacar la ropa")    # desde cualquier hilo
    cancelar = consola.reclamar(apagar, prompt="Enter apaga la alarma > ")
    respuesta = consola.preguntar("¿Lo hago? (s/N) ", timeout=60)

Todo lo externo es inyectable (stdout, stdin, lector de teclas, API de
Windows, ancho) para probarlo en seco.
"""
from __future__ import annotations

import ctypes
import io
import logging
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, List, Optional, Tuple, Union

_log = logging.getLogger("lune.consola")

TITULO_DEFECTO = "Lune"             # sin capas y sin titulo(): lo que se repinta

# Secuencias ANSI/VT
BORRAR_LINEA = "\r\033[2K"          # al principio de la línea y la borra entera
SUBIR_Y_BORRAR = "\033[1A\033[2K"   # sube una fila (misma columna) y la borra

# Teclas especiales que devuelve el lector (cadenas de 2 caracteres: no chocan
# con un carácter tecleado, que siempre es 1 o un par sustituto ya combinado).
TECLA_ARRIBA = "\x00H"
TECLA_ABAJO = "\x00P"

_RE_ANSI = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"              # CSI: colores, cursor…
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"   # OSC: título…
    r"|\x1b[@-Z\\-_]"                       # escapes de 2 caracteres
)

# ── WinAPI ───────────────────────────────────────────────────────────────────────
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
KEY_EVENT = 0x0001
VK_UP = 0x26
VK_DOWN = 0x28
VK_MENU = 0x12
FLASHW_ALL = 0x00000003          # título + botón de la barra de tareas
FLASHW_TIMERNOFG = 0x0000000C    # hasta que la ventana pase a primer plano

if sys.platform == "win32":
    from ctypes import wintypes

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class _EVENTO(ctypes.Union):
        # El mayor de la unión (MOUSE_EVENT_RECORD) mide 16 bytes, como KEY_EVENT_RECORD.
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_relleno", ctypes.c_byte * 16)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENTO)]

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]


def _handle_valido(h: Any) -> bool:
    return bool(h) and h != -1 and h != ctypes.c_void_p(-1).value


def _combinar_sustitutos(alta: str, baja: str) -> str:
    """Une un par sustituto UTF-16 (emoji…) en un carácter; lo roto se reemplaza."""
    return (alta + baja).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


class ApiConsolaWin32:
    """Lo poco de la API de consola de Windows que se usa. Fuera de Windows no hace nada.

    Se puede inyectar `kernel32`/`user32` falsos (tests); si no, se cargan con
    ctypes la primera vez que hacen falta.
    """

    def __init__(self, kernel32: Any = None, user32: Any = None):
        self._k = kernel32
        self._u = user32

    def _k32(self) -> Any:
        if self._k is None and sys.platform == "win32":
            try:
                k = ctypes.WinDLL("kernel32", use_last_error=True)
                k.GetStdHandle.argtypes = [wintypes.DWORD]
                k.GetStdHandle.restype = wintypes.HANDLE
                k.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                k.GetConsoleMode.restype = wintypes.BOOL
                k.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                k.SetConsoleMode.restype = wintypes.BOOL
                k.SetConsoleTitleW.argtypes = [wintypes.LPCWSTR]
                k.SetConsoleTitleW.restype = wintypes.BOOL
                k.GetConsoleWindow.argtypes = []
                k.GetConsoleWindow.restype = wintypes.HWND
                k.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(INPUT_RECORD),
                                                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
                k.ReadConsoleInputW.restype = wintypes.BOOL
                self._k = k
            except (OSError, AttributeError):
                self._k = False
        return self._k or None

    def _u32(self) -> Any:
        if self._u is None and sys.platform == "win32":
            try:
                u = ctypes.WinDLL("user32", use_last_error=True)
                u.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
                u.FlashWindowEx.restype = wintypes.BOOL
                self._u = u
            except (OSError, AttributeError):
                self._u = False
        return self._u or None

    def _modo(self, std: int) -> Optional[int]:
        k = self._k32()
        if k is None:
            return None
        h = k.GetStdHandle(std)
        if not _handle_valido(h):
            return None
        modo = wintypes.DWORD()
        if not k.GetConsoleMode(h, ctypes.byref(modo)):
            return None                 # redirigida: no es una consola
        return int(modo.value)

    def habilitar_vt(self) -> bool:
        """Activa las secuencias VT (colores, borrar línea…) en la salida. True si quedan activas."""
        modo = self._modo(STD_OUTPUT_HANDLE)
        if modo is None:
            return False
        if modo & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        k = self._k32()
        return bool(k.SetConsoleMode(k.GetStdHandle(STD_OUTPUT_HANDLE),
                                     modo | ENABLE_VIRTUAL_TERMINAL_PROCESSING))

    def es_consola_entrada(self) -> bool:
        """¿La entrada estándar es una consola de Windows (y no una tubería)?"""
        return self._modo(STD_INPUT_HANDLE) is not None

    def titulo(self, texto: str) -> bool:
        k = self._k32()
        return bool(k is not None and k.SetConsoleTitleW(texto))

    def parpadear(self, veces: int = 3, hasta_foco: bool = True) -> bool:
        """Hace parpadear la ventana de la consola en la barra de tareas."""
        k, u = self._k32(), self._u32()
        if k is None or u is None:
            return False
        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return False
        flags = FLASHW_ALL | (FLASHW_TIMERNOFG if hasta_foco else 0)
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, flags, max(1, int(veces)), 0)
        u.FlashWindowEx(ctypes.byref(info))   # devuelve el estado anterior, no éxito
        return True

    def leer_tecla(self) -> str:
        """Bloquea hasta la próxima tecla. Devuelve el carácter (Enter = "\\r",
        retroceso = "\\x08"…), TECLA_ARRIBA/TECLA_ABAJO, o "" si no se puede leer.

        Ctrl+C no llega aquí: con la entrada procesada (lo normal) Windows lo
        convierte en KeyboardInterrupt en el hilo principal.
        """
        k = self._k32()
        if k is None:
            return ""
        h = k.GetStdHandle(STD_INPUT_HANDLE)
        rec = INPUT_RECORD()
        n = wintypes.DWORD()
        alta = ""
        while True:
            if not k.ReadConsoleInputW(h, ctypes.byref(rec), 1, ctypes.byref(n)):
                return ""
            if rec.EventType != KEY_EVENT:
                continue
            ev = rec.Event.KeyEvent
            ch = ev.uChar or "\x00"
            if not ev.bKeyDown:
                # Alt + números del teclado numérico: el carácter llega al SOLTAR Alt.
                if not (ev.wVirtualKeyCode == VK_MENU and ch != "\x00"):
                    continue
            if ch == "\x00":
                if ev.wVirtualKeyCode == VK_UP:
                    return TECLA_ARRIBA
                if ev.wVirtualKeyCode == VK_DOWN:
                    return TECLA_ABAJO
                continue                 # Mayús, Ctrl, F1… no escriben nada
            if "\ud800" <= ch <= "\udbff":
                alta = ch                # emoji: llega en dos mitades
                continue
            if alta:
                ch, alta = _combinar_sustitutos(alta, ch), ""
            return ch * max(1, int(ev.wRepeatCount))


def habilitar_vt(api: Optional[ApiConsolaWin32] = None) -> bool:
    """Activa las secuencias VT en la consola de Windows. Fuera de Windows, True."""
    if sys.platform != "win32":
        return True
    return (api or ApiConsolaWin32()).habilitar_vt()


def ancho_visible(texto: str) -> int:
    """Columnas que ocupa `texto` en la terminal: sin secuencias ANSI, con los
    caracteres anchos (CJK, muchos emoji) a 2 y los combinantes a 0."""
    col = 0
    for ch in _RE_ANSI.sub("", texto):
        if ch == "\t":
            col += 8 - col % 8
        elif unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf", "Cc"):
            continue
        else:
            col += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return col


def _es_tty(f: Any) -> bool:
    try:
        return bool(f is not None and f.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _ultima_linea(texto: str) -> str:
    """Lo que queda en la línea en curso tras escribir `texto`."""
    linea = texto.rsplit("\n", 1)[-1]
    return linea.rsplit("\r", 1)[-1]


@dataclass(eq=False)
class _Reclamo:
    fn: Callable[[str], Any]
    prompt: Optional[str]
    bloqueante: bool = False               # alguien espera (preguntar): se enseña el prompt
    evento: Optional[threading.Event] = None
    cancelado: bool = False
    prioridad: int = 0                     # los de más prioridad reciben antes la línea


class ConsolaAsincrona:
    """Consola compartida entre hilos con un único lector (ver la cabecera del módulo)."""

    def __init__(self, prompt: str = "tú > ", *, stdout: Any = None, stdin: Any = None,
                 leer_tecla: Optional[Callable[[], str]] = None, api: Optional[ApiConsolaWin32] = None,
                 ansi: Optional[bool] = None, ancho: Union[int, Callable[[], int], None] = None,
                 titulo_defecto: str = TITULO_DEFECTO):
        self.prompt = prompt
        self.lock = threading.RLock()        # EL lock de salida (streaming + avisos)
        self._cond = threading.Condition(self.lock)
        self._api = api if api is not None else ApiConsolaWin32()
        propia = stdout is None
        self._stdout = stdout if stdout is not None else (sys.stdout or io.StringIO())
        self._stdin = stdin if stdin is not None else sys.stdin

        # VT: solo tiene sentido sobre la consola real.
        self.vt = self._api.habilitar_vt() if (propia and sys.platform == "win32") else False
        if ansi is None:
            ansi = _es_tty(self._stdout) and (sys.platform != "win32" or self.vt)
        self._ansi = bool(ansi)
        self._ancho = ancho

        # Modo de lectura
        if leer_tecla is not None:
            self.modo, self._leer_tecla = "teclas", leer_tecla
        elif stdin is None and sys.platform == "win32" and self._api.es_consola_entrada():
            self.modo, self._leer_tecla = "teclas", self._api.leer_tecla
        else:
            self.modo, self._leer_tecla = "lineas", None

        # Estado (todo protegido por self.lock)
        self._buffer = ""                     # lo tecleado y aún sin Enter (modo teclas)
        self._historial: List[str] = []
        self._pos_hist = 0
        self._ultimo_cr = False
        self._parcial = ""                    # salida escrita tras el último salto de línea
        self._dibujado = False                # ¿el prompt está en pantalla?
        self._prompt_dibujado = ""
        self._filas_prompt = 1
        self._lectores = 0                    # hilos esperando en leer_linea()
        self._cola_chat: Deque[Tuple[str, bool]] = deque()   # (línea, falta_eco)
        self._reclamos: Deque[_Reclamo] = deque()
        self._eof = False
        self._hilo: Optional[threading.Thread] = None
        # Título: el normal (titulo()) y las capas {capa: (prioridad, orden, texto)}.
        self._titulo_base: Optional[str] = None
        self._titulo_defecto = str(titulo_defecto or TITULO_DEFECTO)
        self._capas: dict = {}
        self._orden_capa = 0
        self._titulo_pintado: Optional[str] = None

    @property
    def ansi(self) -> bool:
        """¿La salida entiende secuencias ANSI (borrar línea, colores)?"""
        return self._ansi

    def columnas(self) -> int:
        """Ancho de la terminal en columnas."""
        return self._columnas()

    # ── Salida ───────────────────────────────────────────────────────────────────
    def escribir(self, texto: str) -> None:
        """Escribe `texto` tal cual (sin salto final). Para el streaming y los print.

        Si el prompt está en pantalla (alguien espera respuesta en otro hilo), el
        texto sale ENCIMA del prompt y este se vuelve a pintar debajo.
        """
        if not texto:
            return
        with self.lock:
            if self._dibujado:
                self._limpiar_vivo()
                self._out(self._parcial + texto)
                self._parcial = _ultima_linea(self._parcial + texto)
                self._dibujar_prompt()
            else:
                self._out(texto)
                self._parcial = _ultima_linea(self._parcial + texto)

    def imprimir(self, *partes: Any, sep: str = " ", end: str = "\n") -> None:
        """Como `print`, pero por la consola compartida."""
        self.escribir(sep.join(str(p) for p in partes) + end)

    def aviso(self, texto: str) -> None:
        """Imprime `texto` en su propia línea sin romper lo que hay en pantalla.

        Borra la línea en curso, escribe el aviso y repinta lo que había (el
        prompt con lo que llevabas escrito, o la frase a medias del streaming).
        Se puede llamar desde cualquier hilo.
        """
        with self.lock:
            con_prompt = self._dibujado
            self._limpiar_vivo()
            self._out(texto if texto.endswith("\n") else texto + "\n")
            self._repintar_vivo(con_prompt)

    def titulo(self, texto: str) -> bool:
        """Cambia el título normal de la ventana de la consola (estado, carita…).

        Si hay alguna capa (`titulo_capa`) se guarda y se enseñará al quitarlas."""
        with self.lock:
            self._titulo_base = str(texto)
            if self._capas:
                return True
            self._titulo_pintado = self._titulo_base
            return self._poner_titulo(self._titulo_base)

    def titulo_capa(self, capa: str, texto: Optional[str], prioridad: int = 0) -> bool:
        """Pone (o quita, con `texto=None`) la capa `capa` del título.

        Se enseña la de mayor `prioridad` (a igualdad, la puesta más tarde); sin
        capas, el título de `titulo()`. Solo se repinta si cambia lo que se ve.
        """
        with self.lock:
            capa = str(capa)
            if texto is None:
                if self._capas.pop(capa, None) is None:
                    return False
            else:
                viejo = self._capas.get(capa)
                if viejo is not None and viejo[0] == int(prioridad):
                    orden = viejo[1]               # cambiar el texto no la sube por encima de sus iguales
                else:
                    self._orden_capa += 1
                    orden = self._orden_capa
                self._capas[capa] = (int(prioridad), orden, str(texto))
            return self._repintar_titulo()

    def capa_titulo(self) -> Optional[str]:
        """La capa que se ve ahora en el título (None: el título normal)."""
        with self.lock:
            if not self._capas:
                return None
            return max(self._capas.items(), key=lambda kv: (kv[1][0], kv[1][1]))[0]

    def _repintar_titulo(self) -> bool:
        if self._capas:
            texto = max(self._capas.values(), key=lambda v: (v[0], v[1]))[2]
        else:
            # Sin titulo() todavía: el de por defecto, no la capa que se acaba de quitar.
            texto = self._titulo_base if self._titulo_base is not None else self._titulo_defecto
        if texto == self._titulo_pintado:
            return True
        self._titulo_pintado = texto
        return self._poner_titulo(texto)

    def _poner_titulo(self, texto: str) -> bool:
        limpio = "".join(ch for ch in str(texto) if ch.isprintable() or ch == " ")
        if self._api.titulo(limpio):
            return True
        if self._ansi and sys.platform != "win32":
            with self.lock:
                self._out(f"\033]0;{limpio}\a")
            return True
        return False

    def parpadear(self, veces: int = 3, hasta_foco: bool = True, campana: bool = False) -> bool:
        """Hace parpadear la consola en la barra de tareas (p. ej. al sonar una alarma).

        `campana` añade un BEL (Windows Terminal lo convierte en parpadeo o sonido
        según su configuración).
        """
        ok = self._api.parpadear(veces, hasta_foco)
        if campana:
            with self.lock:
                self._out("\a")
        return ok

    # ── Entrada ──────────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        """Arranca el hilo lector (lo hacen solos leer_linea, reclamar y preguntar)."""
        with self.lock:
            if self._hilo is not None or self._eof:
                return
            self._hilo = threading.Thread(target=self._bucle, name="consola-entrada", daemon=True)
            self._hilo.start()

    def detener(self) -> None:
        """Da la entrada por terminada: leer_linea lanza EOFError y los reclamos se sueltan."""
        self._fin()

    def leer_linea(self, prompt: Optional[str] = None) -> str:
        """Enseña el prompt y bloquea hasta la próxima línea para el chat.

        Lanza EOFError si se acaba la entrada. Ctrl+C sale como KeyboardInterrupt
        (se espera a trozos para que el hilo principal lo reciba).
        """
        self.iniciar()
        with self._cond:
            if prompt is not None:
                self.prompt = prompt
            self._lectores += 1
            try:
                self._sincronizar()
                while not self._cola_chat:
                    if self._eof:
                        raise EOFError("fin de la entrada de la consola")
                    self._cond.wait(0.25)
                linea, falta_eco = self._cola_chat.popleft()
            finally:
                self._lectores -= 1
                self._sincronizar()
            if falta_eco:                     # se tecleó mientras no había prompt
                self.aviso(self.prompt + linea)
            return linea

    def reclamar(self, fn: Callable[[str], Any], prompt: Optional[str] = None, *,
                 prioridad: int = 0) -> Callable[[], None]:
        """La próxima línea escrita irá a `fn(linea)` en vez de al chat.

        `fn` se llama desde el hilo lector: que sea rápida (apagar un sonido,
        guardar una respuesta). Si devuelve False, la línea NO se consume: sigue
        al siguiente reclamo o al chat, y este reclamo sigue esperando (p. ej. la
        alarma solo se apaga con Enter en vacío). `prompt` sustituye al prompt
        normal mientras este reclamo es el primero de la cola. Los reclamos van
        por `prioridad` (mayor antes) y, a igualdad, por orden de llegada.
        Devuelve `cancelar()`; `cancelar.cambiar_prompt(texto)` cambia su prompt
        (y lo repinta si es el que se ve).
        """
        r = _Reclamo(fn, prompt, prioridad=int(prioridad))
        self._encolar(r)

        def cancelar() -> None:
            self._quitar(r)

        def cambiar_prompt(texto: Optional[str]) -> bool:
            return self._cambiar_prompt(r, texto)
        cancelar.cambiar_prompt = cambiar_prompt          # type: ignore[attr-defined]
        return cancelar

    def preguntar(self, prompt: str, timeout: Optional[float] = None) -> Optional[str]:
        """Enseña `prompt` y espera la próxima línea. None si caduca o se acaba la entrada.

        Sirve desde cualquier hilo menos el lector (se bloquearía a sí mismo).
        """
        if threading.current_thread() is self._hilo:
            raise RuntimeError("preguntar() desde el hilo lector de la consola se bloquearía")
        caja: List[str] = []
        ev = threading.Event()

        def fn(linea: str) -> None:
            caja.append(linea)
            ev.set()

        r = _Reclamo(fn, prompt, bloqueante=True, evento=ev)
        if not self._encolar(r):
            return None
        limite = None if timeout is None else time.monotonic() + max(0.0, timeout)
        try:
            while not ev.wait(0.25 if limite is None else max(0.0, min(0.25, limite - time.monotonic()))):
                if self._eof or (limite is not None and time.monotonic() >= limite):
                    break
        finally:
            if not caja:
                self._quitar(r)
        return caja[0] if caja else None

    @property
    def reclamada(self) -> bool:
        """¿Hay algún reclamo esperando la próxima línea?"""
        with self.lock:
            return any(not r.cancelado for r in self._reclamos)

    # ── Internos: zona viva (línea parcial + prompt) ─────────────────────────────
    def _out(self, s: str) -> None:
        try:
            self._stdout.write(s)
        except UnicodeEncodeError:
            cod = getattr(self._stdout, "encoding", None) or "ascii"
            try:
                self._stdout.write(s.encode(cod, "replace").decode(cod))
            except (OSError, ValueError):
                return
        except (OSError, ValueError):
            return                            # consola cerrada
        try:
            self._stdout.flush()
        except (OSError, ValueError, AttributeError):
            pass

    def _columnas(self) -> int:
        a = self._ancho() if callable(self._ancho) else self._ancho
        if a is None:
            a = shutil.get_terminal_size((80, 24)).columns
        return max(1, int(a))

    def _filas(self, texto: str) -> int:
        return max(1, -(-ancho_visible(texto) // self._columnas()))

    def _texto_prompt(self) -> str:
        for r in self._reclamos:
            if not r.cancelado:
                return r.prompt if r.prompt is not None else self.prompt
        return self.prompt

    def _quiere_prompt(self) -> bool:
        if self._eof:
            return False
        if any(r.bloqueante and not r.cancelado for r in self._reclamos):
            return True
        return self._lectores > len(self._cola_chat)

    def _dibujar_prompt(self) -> None:
        texto = self._texto_prompt()
        linea = texto + (self._buffer if self.modo == "teclas" else "")
        self._out(("\n" if self._parcial else "") + linea)
        self._dibujado = True
        self._prompt_dibujado = texto
        self._filas_prompt = self._filas(linea)

    def _limpiar_vivo(self) -> None:
        """Borra la zona viva y deja el cursor al principio de una línea vacía.

        `_parcial` se conserva para repintarlo (sin ANSI no se puede borrar: se
        baja de línea y lo parcial queda escrito tal cual).
        """
        if self._ansi:
            filas = (self._filas_prompt if self._dibujado else 0) + \
                    (self._filas(self._parcial) if self._parcial else 0)
            self._out(BORRAR_LINEA + SUBIR_Y_BORRAR * max(0, filas - 1))
        else:
            if self._dibujado or self._parcial:
                self._out("\n")
            self._parcial = ""
        self._dibujado = False

    def _repintar_vivo(self, con_prompt: bool) -> None:
        if self._parcial:
            self._out(self._parcial)
        if con_prompt:
            self._dibujar_prompt()

    def _sincronizar(self) -> None:
        """Pone o quita el prompt según haya alguien esperando una línea."""
        quiere = self._quiere_prompt()
        if quiere and self._dibujado and self._texto_prompt() == self._prompt_dibujado:
            return
        if not quiere and not self._dibujado:
            return
        if self._dibujado:
            self._limpiar_vivo()
            self._repintar_vivo(quiere)
        else:
            self._dibujar_prompt()

    def _repintar_prompt(self) -> None:
        if self._dibujado:
            self._limpiar_vivo()
            self._repintar_vivo(True)

    # ── Internos: reclamos ───────────────────────────────────────────────────────
    def _encolar(self, r: _Reclamo) -> bool:
        self.iniciar()
        with self.lock:
            if self._eof:
                return False
            # Detrás de los de prioridad mayor o igual, delante de los de menos.
            pos = len(self._reclamos)
            for i, x in enumerate(self._reclamos):
                if x.prioridad < r.prioridad:
                    pos = i
                    break
            self._reclamos.insert(pos, r)
            self._sincronizar()
            return True

    def _cambiar_prompt(self, r: _Reclamo, texto: Optional[str]) -> bool:
        with self.lock:
            if r.cancelado or self._eof:
                return False
            r.prompt = texto
            self._sincronizar()
            return True

    def _quitar(self, r: _Reclamo) -> None:
        with self.lock:
            r.cancelado = True
            try:
                self._reclamos.remove(r)
            except ValueError:
                pass
            self._sincronizar()

    def _siguiente_reclamo(self) -> Optional[_Reclamo]:
        while self._reclamos:
            r = self._reclamos.popleft()
            if not r.cancelado:
                return r
        return None

    def _confirmar_linea(self) -> bool:
        """Deja en pantalla la línea recién enviada. True si hay que enseñarla luego
        (se tecleó a ciegas, sin prompt)."""
        if self.modo == "teclas":
            if self._dibujado:
                self._out("\n")
                self._dibujado = False
                self._parcial = ""
                return False
            return True
        # Modo líneas: el Enter lo ha pintado la propia terminal.
        self._dibujado = False
        self._parcial = ""
        return False

    def _despachar(self, linea: Optional[str]) -> None:
        """Entrega una línea (None = la del búfer de teclas) al primer reclamo o al chat."""
        rechazados: List[_Reclamo] = []
        falta_eco = False
        primera = True
        while True:
            with self.lock:
                if primera:
                    primera = False
                    if linea is None:
                        linea, self._buffer = self._buffer, ""
                        if linea and (not self._historial or self._historial[-1] != linea):
                            self._historial.append(linea)
                        self._pos_hist = len(self._historial)
                    falta_eco = self._confirmar_linea()
                r = self._siguiente_reclamo()
                if r is None:
                    for x in reversed(rechazados):
                        if not x.cancelado:
                            self._reclamos.appendleft(x)
                    self._cola_chat.append((linea, falta_eco))
                    self._cond.notify_all()
                    self._sincronizar()
                    return
                if falta_eco:
                    self.aviso((r.prompt if r.prompt is not None else self.prompt) + linea)
                    falta_eco = False
            try:
                res = r.fn(linea)
            except Exception:
                _log.exception("Error atendiendo una línea reclamada de la consola")
                res = None
            if res is False and not r.bloqueante:
                rechazados.append(r)
                continue
            with self.lock:
                for x in reversed(rechazados):
                    if not x.cancelado:
                        self._reclamos.appendleft(x)
                self._sincronizar()
            return

    def _fin(self) -> None:
        with self.lock:
            self._eof = True
            for r in self._reclamos:
                r.cancelado = True
                if r.evento is not None:
                    r.evento.set()
            self._reclamos.clear()
            self._cond.notify_all()
            self._sincronizar()

    # ── Internos: hilo lector ────────────────────────────────────────────────────
    def _bucle(self) -> None:
        try:
            if self.modo == "teclas":
                self._bucle_teclas()
            else:
                self._bucle_lineas()
        except Exception:
            _log.exception("El lector de la consola se ha parado")
        finally:
            self._fin()

    def _bucle_lineas(self) -> None:
        while not self._eof:
            try:
                linea = self._stdin.readline()
            except (OSError, ValueError):
                return
            if not linea:
                return
            self._despachar(linea.rstrip("\r\n"))

    def _bucle_teclas(self) -> None:
        while not self._eof:
            t = self._leer_tecla()
            if not t:
                return
            if t in (TECLA_ARRIBA, TECLA_ABAJO):
                self._historia(t == TECLA_ARRIBA)
                continue
            for c in t:
                accion = self._tecla(c)
                if accion == "enter":
                    self._despachar(None)
                elif accion == "eof":
                    return

    def _tecla(self, c: str) -> Optional[str]:
        """Aplica una tecla al búfer. Devuelve "enter", "eof" o None."""
        with self.lock:
            era_cr, self._ultimo_cr = self._ultimo_cr, (c == "\r")
            if c == "\r" or (c == "\n" and not era_cr):
                return "enter"
            if c == "\n":
                return None                   # el \n de un \r\n pegado
            if c == "\x08":                   # retroceso
                if self._buffer:
                    self._buffer = self._buffer[:-1]
                    self._repintar_prompt()
                return None
            if c == "\x1b":                   # Esc: vacía la línea, como la consola de Windows
                if self._buffer:
                    self._buffer = ""
                    self._repintar_prompt()
                return None
            if c == "\x1a":                   # Ctrl+Z en vacío: fin de la entrada
                return "eof" if not self._buffer else None
            if not c.isprintable():
                return None
            self._buffer += c
            if self._dibujado:
                self._out(c)
                self._filas_prompt = self._filas(self._prompt_dibujado + self._buffer)
            return None

    def _historia(self, arriba: bool) -> None:
        with self.lock:
            if not self._historial:
                return
            n = len(self._historial)
            self._pos_hist = max(0, self._pos_hist - 1) if arriba else min(n, self._pos_hist + 1)
            self._buffer = self._historial[self._pos_hist] if self._pos_hist < n else ""
            self._repintar_prompt()
