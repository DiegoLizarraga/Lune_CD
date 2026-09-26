"""
servicios/discord_ipc.py — Hablar con el Discord abierto en este PC (Rich Presence), sin librerías.

QUÉ ES
------
El cliente de escritorio de Discord escucha en una tubería con nombre local,
`\\\\.\\pipe\\discord-ipc-N` (N = 0..9: la 0 es la del Discord normal; PTB y
Canary cogen la siguiente libre). Por ahí una app le dice «pon esta actividad
en mi perfil». Es la vía oficial del cliente: sin memoria de otros procesos,
sin inyección y sin red (todo es local; Discord publica por su cuenta).

Mate-Engine usa la librería DiscordRPC (C#); aquí se hace a mano, porque el
protocolo es corto:

- Cada trama es `struct.pack('<II', op, largo)` + JSON UTF-8 de `largo` bytes.
- op 0 HANDSHAKE: `{"v": 1, "client_id": "<Application ID>"}`. Discord responde
  con una trama op 1 `{"cmd": "DISPATCH", "evt": "READY", "data": {"user": …}}`
  o cierra (op 2) con `{"code": 4000, …}` si el Application ID no vale.
- op 1 FRAME: órdenes y respuestas. `SET_ACTIVITY` con `args.pid` (Discord la
  borra sola si ese proceso muere) y `nonce` (la respuesta trae el mismo);
  `evt: "ERROR"` si algo no le gustó.
- op 2 CLOSE: se acabó (con `code` y `message`).
- op 3 PING → hay que contestar op 4 PONG con los mismos datos.

HILOS
-----
Nada de esto se llama desde el hilo de Qt: lo usa el hilo «LuneDiscordRPC» de
servicios/discord_presencia.py. `TuberiaWin32.disponibles()` (PeekNamedPipe) no
bloquea, y solo se lee lo que ya ha llegado, así que `atender()` vuelve al
momento; `conectar()` y `set_activity()` esperan su respuesta como mucho
`timeout_s` (con `dormir` a trocitos).

Fuera de Windows `TuberiaWin32.abrir` devuelve None (no hay Discord que abrir).
La DLL (`kernel32`), la apertura de la tubería (`abrir`), el reloj y el `dormir`
son inyectables: los tests usan un Discord falso en memoria.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import struct
import sys
import time
import uuid
from ctypes import wintypes
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger("lune.discord")

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
MAX_TRAMA = 64 * 1024
ID_OK = re.compile(r"^\d{17,20}$")
TUBERIAS = 10                      # discord-ipc-0 … discord-ipc-9
CODIGO_ID_NO_VALIDO = 4000         # cierre de Discord: «Invalid Client ID»

_CABECERA = struct.Struct("<II")
_MAX_BUFFER = 4 * MAX_TRAMA        # lo que se acepta sin cerrar trama: más es basura
_PASO_ESPERA_S = 0.02

# Textos que ve el usuario (en la tarjeta o en /discord estado).
TXT_ID_NO_VALIDO = "El Application ID de Discord no es válido."
TXT_SIN_DISCORD = "Discord no está abierto."
TXT_NO_RESPONDE = "Discord no responde."
TXT_CORTADA = "Discord cerró la conexión."
TXT_CANCELADO = "Conexión cancelada."


class ErrorTrama(ValueError):
    """Una trama imposible (más larga que MAX_TRAMA): la conexión está rota."""


# ── Tramas ──────────────────────────────────────────────────────────────────────
def empaquetar(op: int, datos: Any) -> bytes:
    """Cabecera `<II` (op, largo) + JSON UTF-8 compacto."""
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(cuerpo) > MAX_TRAMA:
        raise ErrorTrama(f"trama de {len(cuerpo)} bytes (máximo {MAX_TRAMA})")
    return _CABECERA.pack(int(op), len(cuerpo)) + cuerpo


def desempaquetar(buf: bytes) -> Tuple[List[Tuple[int, dict]], bytes]:
    """Saca las tramas COMPLETAS de `buf` → (lista de (op, datos), resto sin completar).

    Un JSON roto dentro de una trama completa se entrega como `{}` (la trama se
    consume igual, para no atascar las siguientes). Un largo imposible lanza
    ErrorTrama: ya no se puede saber dónde empieza la trama siguiente.
    """
    buf = bytes(buf or b"")
    tramas: List[Tuple[int, dict]] = []
    pos, total = 0, len(buf)
    while total - pos >= _CABECERA.size:
        op, largo = _CABECERA.unpack_from(buf, pos)
        if largo > MAX_TRAMA:
            raise ErrorTrama(f"trama de {largo} bytes (máximo {MAX_TRAMA})")
        inicio = pos + _CABECERA.size
        if total - inicio < largo:
            break
        cuerpo = buf[inicio:inicio + largo]
        pos = inicio + largo
        try:
            datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
        except (UnicodeDecodeError, ValueError):
            datos = {}
        if not isinstance(datos, dict):
            datos = {"valor": datos}
        tramas.append((int(op), datos))
    return tramas, buf[pos:]


def nombre_tuberia(n: int) -> str:
    return "\\\\.\\pipe\\discord-ipc-" + str(int(n))


# ── La tubería de Windows ──────────────────────────────────────────────────────
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_INVALIDO = ctypes.c_void_p(-1).value
_K32: Any = None


def _preparar_kernel32(k: Any) -> Any:
    """Firmas completas (sin ellas un HANDLE de 64 bits se trunca)."""
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k.CreateFileW.restype = wintypes.HANDLE
    k.PeekNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                ctypes.POINTER(wintypes.DWORD)]
    k.PeekNamedPipe.restype = wintypes.BOOL
    k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.ReadFile.restype = wintypes.BOOL
    k.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.WriteFile.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


def _kernel32_defecto() -> Any:
    global _K32
    if _K32 is None:
        _K32 = _preparar_kernel32(ctypes.WinDLL("kernel32", use_last_error=True))
    return _K32


def _ultimo_error() -> int:
    try:
        return int(ctypes.get_last_error())
    except Exception:
        return 0


class TuberiaWin32:
    """Un extremo cliente de `\\\\.\\pipe\\discord-ipc-N` (kernel32 con ctypes).

    `disponibles()` usa PeekNamedPipe: dice cuántos bytes esperan SIN bloquear.
    `leer(n)` solo se llama con n ≤ disponibles, así que tampoco bloquea. Un
    fallo (Discord se cerró: ERROR_BROKEN_PIPE) lanza OSError.
    """

    def __init__(self, handle: int, kernel32: Any):
        self._h = handle
        self._k = kernel32

    @classmethod
    def abrir(cls, n: int, kernel32: Any = None) -> "Optional[TuberiaWin32]":
        """La tubería N abierta, o None si no existe, está ocupada o no es Windows."""
        if kernel32 is None:
            if sys.platform != "win32":
                return None
            try:
                kernel32 = _kernel32_defecto()
            except Exception:
                return None
        try:
            h = kernel32.CreateFileW(nombre_tuberia(n), _GENERIC_READ | _GENERIC_WRITE, 0, None,
                                     _OPEN_EXISTING, 0, None)
        except Exception:
            return None
        if not h or h == _INVALIDO or h == -1:
            return None
        return cls(h, kernel32)

    def _handle(self) -> int:
        if not self._h:
            raise OSError("la tubería de Discord está cerrada")
        return self._h

    def disponibles(self) -> int:
        total = wintypes.DWORD(0)
        if not self._k.PeekNamedPipe(self._handle(), None, 0, None, ctypes.byref(total), None):
            raise OSError(_ultimo_error(), "PeekNamedPipe falló (¿Discord se cerró?)")
        return int(total.value)

    def leer(self, n: int) -> bytes:
        n = max(1, int(n))
        buf = ctypes.create_string_buffer(n)
        leidos = wintypes.DWORD(0)
        if not self._k.ReadFile(self._handle(), buf, n, ctypes.byref(leidos), None):
            raise OSError(_ultimo_error(), "ReadFile falló (¿Discord se cerró?)")
        return buf.raw[:int(leidos.value)]

    def escribir(self, datos: bytes) -> None:
        pendiente = bytes(datos)
        while pendiente:
            escritos = wintypes.DWORD(0)
            if not self._k.WriteFile(self._handle(), pendiente, len(pendiente), ctypes.byref(escritos), None):
                raise OSError(_ultimo_error(), "WriteFile falló (¿Discord se cerró?)")
            if int(escritos.value) <= 0:
                raise OSError("WriteFile no escribió nada")
            pendiente = pendiente[int(escritos.value):]

    def cerrar(self) -> None:
        h, self._h = self._h, None
        if h:
            try:
                self._k.CloseHandle(h)
            except Exception:
                pass

    def __del__(self):
        try:
            self.cerrar()
        except Exception:
            pass


# ── El cliente ─────────────────────────────────────────────────────────────────
def _nombre_usuario(datos: dict) -> str:
    """El nombre que enseña Discord (solo para la tarjeta de Lune; no se publica)."""
    usuario = ((datos.get("data") or {}).get("user") or {}) if isinstance(datos, dict) else {}
    if not isinstance(usuario, dict):
        return ""
    return str(usuario.get("global_name") or usuario.get("username") or "")[:64]


def _resultado(ok: bool, *, usuario: str = "", error: str = "", codigo: int = 0) -> Dict[str, Any]:
    return {"ok": bool(ok), "usuario": usuario, "error": error, "codigo": int(codigo or 0)}


class ClienteIPC:
    """Una conexión con el Discord local.

        c = ClienteIPC("123456789012345678")
        r = c.conectar()                 # {ok, usuario, error, codigo}
        c.set_activity({...}, os.getpid())
        c.atender()                      # cada ~100 ms: PING → PONG, CLOSE
        c.cerrar()                       # actividad null + OP_CLOSE

    Tras un CLOSE de Discord, `conectado` es False y `codigo_cierre` dice por qué
    (4000 = el Application ID no vale: no tiene sentido reintentar con el mismo).
    """

    def __init__(self, client_id: str, *, abrir: Callable[[int], Any] = TuberiaWin32.abrir,
                 reloj: Callable[[], float] = time.monotonic, dormir: Callable[[float], Any] = time.sleep):
        self.client_id = str(client_id or "").strip()
        self._abrir = abrir
        self._reloj = reloj
        self._dormir = dormir
        self._tuberia: Any = None
        self._buf = b""
        self._pid = os.getpid()
        self.numero: Optional[int] = None       # qué discord-ipc-N se abrió
        self.conectado = False
        self.usuario = ""
        self.error = ""
        self.codigo_cierre = 0

    # ── Conexión ──────────────────────────────────────────────────────────────
    def conectar(self, timeout_s: float = 5.0, *,
                 cancelar: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """Prueba discord-ipc-0..9, manda el handshake y espera READY.

        → {ok, usuario, error, codigo}. `cancelar()` True corta la espera (quien
        cierra la app no espera los 5 s)."""
        if self.conectado:
            return _resultado(True, usuario=self.usuario)
        self.codigo_cierre = 0
        if not ID_OK.match(self.client_id):
            self.error = TXT_ID_NO_VALIDO
            return _resultado(False, error=self.error, codigo=CODIGO_ID_NO_VALIDO)
        tuberia = None
        for n in range(TUBERIAS):
            try:
                tuberia = self._abrir(n)
            except Exception:
                tuberia = None
            if tuberia is not None:
                self.numero = n
                break
        if tuberia is None:
            self.error = TXT_SIN_DISCORD
            return _resultado(False, error=self.error)
        self._tuberia = tuberia
        self._buf = b""
        try:
            tuberia.escribir(empaquetar(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id}))
        except (OSError, ErrorTrama) as e:
            self._soltar_tuberia()
            self.error = TXT_CORTADA
            _log.debug("discord: el handshake no salió: %s", e)
            return _resultado(False, error=self.error)
        t0 = self._reloj()
        while True:
            try:
                tramas = self._leer()
            except (OSError, ErrorTrama):
                self._soltar_tuberia()
                self.error = TXT_CORTADA
                return _resultado(False, error=self.error)
            for op, datos in tramas:
                if op == OP_PING:
                    self._pong(datos)
                elif op == OP_CLOSE:
                    codigo = _int(datos.get("code"))
                    self._soltar_tuberia()
                    self.codigo_cierre = codigo
                    self.error = (TXT_ID_NO_VALIDO if codigo == CODIGO_ID_NO_VALIDO
                                  else _texto_error(datos, TXT_CORTADA))
                    return _resultado(False, error=self.error, codigo=codigo)
                elif op == OP_FRAME and datos.get("evt") == "READY":
                    self.conectado = True
                    self.usuario = _nombre_usuario(datos)
                    self.error = ""
                    return _resultado(True, usuario=self.usuario)
                elif op == OP_FRAME and datos.get("evt") == "ERROR":
                    datos_error = datos.get("data") if isinstance(datos.get("data"), dict) else {}
                    codigo = _int(datos_error.get("code"))
                    self._soltar_tuberia()
                    self.error = (TXT_ID_NO_VALIDO if codigo == CODIGO_ID_NO_VALIDO
                                  else _texto_error(datos_error, TXT_CORTADA))
                    return _resultado(False, error=self.error, codigo=codigo)
            if self._reloj() - t0 >= float(timeout_s):
                self._soltar_tuberia()
                self.error = TXT_NO_RESPONDE
                return _resultado(False, error=self.error)
            if cancelar is not None and _seguro(cancelar):
                self._soltar_tuberia()
                self.error = TXT_CANCELADO
                return _resultado(False, error=self.error)
            self._dormir(_PASO_ESPERA_S)

    # ── Actividad ─────────────────────────────────────────────────────────────
    def set_activity(self, actividad: Optional[dict], pid: int, *, timeout_s: float = 2.0) -> Dict[str, Any]:
        """SET_ACTIVITY (None = borrarla) con `pid` y un nonce; espera la respuesta.

        → {ok, error, codigo}. Un `evt: ERROR` de Discord → ok False con su mensaje."""
        if not self.conectado or self._tuberia is None:
            return {"ok": False, "error": self.error or TXT_SIN_DISCORD, "codigo": 0}
        self._pid = int(pid)
        nonce = uuid.uuid4().hex
        orden = {"cmd": "SET_ACTIVITY", "args": {"pid": int(pid), "activity": actividad}, "nonce": nonce}
        try:
            self._tuberia.escribir(empaquetar(OP_FRAME, orden))
        except ErrorTrama as e:
            return {"ok": False, "error": str(e), "codigo": 0}
        except OSError:
            self._caida(TXT_CORTADA)
            return {"ok": False, "error": self.error, "codigo": 0}
        t0 = self._reloj()
        while True:
            try:
                tramas = self._leer()
            except (OSError, ErrorTrama):
                self._caida(TXT_CORTADA)
                return {"ok": False, "error": self.error, "codigo": 0}
            for op, datos in tramas:
                if self._control(op, datos):
                    continue
                if op == OP_FRAME and datos.get("nonce") == nonce:
                    if datos.get("evt") == "ERROR":
                        d = datos.get("data") if isinstance(datos.get("data"), dict) else {}
                        return {"ok": False, "error": _texto_error(d, "Discord rechazó la actividad."),
                                "codigo": _int(d.get("code"))}
                    return {"ok": True, "error": "", "codigo": 0}
            if not self.conectado:
                return {"ok": False, "error": self.error, "codigo": self.codigo_cierre}
            if self._reloj() - t0 >= float(timeout_s):
                return {"ok": False, "error": TXT_NO_RESPONDE, "codigo": 0, "sin_respuesta": True}
            self._dormir(_PASO_ESPERA_S)

    def atender(self) -> None:
        """Lo que haya llegado, sin bloquear: PING → PONG; CLOSE → desconectado."""
        if not self.conectado or self._tuberia is None:
            return
        try:
            tramas = self._leer()
        except (OSError, ErrorTrama):
            self._caida(TXT_CORTADA)
            return
        for op, datos in tramas:
            self._control(op, datos)

    def cerrar(self, limpiar: bool = True) -> None:
        """Borra la actividad (menos de 1 s esperando la respuesta, para que quepa en
        el `cerrar(timeout=1.0)` de la presencia), manda OP_CLOSE y suelta la
        tubería. Idempotente."""
        if self._tuberia is None:
            self.conectado = False
            return
        if limpiar and self.conectado:
            try:
                self.set_activity(None, self._pid, timeout_s=0.8)
            except Exception:
                pass
        if self._tuberia is not None:
            try:
                self._tuberia.escribir(empaquetar(OP_CLOSE, {"v": 1, "client_id": self.client_id}))
            except Exception:
                pass
        self._soltar_tuberia()

    # ── Internos ──────────────────────────────────────────────────────────────
    def _leer(self) -> List[Tuple[int, dict]]:
        t = self._tuberia
        if t is None:
            raise OSError("sin tubería")
        n = t.disponibles()
        while n > 0:
            trozo = t.leer(min(n, MAX_TRAMA + _CABECERA.size))
            if not trozo:
                break
            self._buf += trozo
            if len(self._buf) > _MAX_BUFFER:
                raise ErrorTrama("demasiados datos sin una trama completa")
            n = t.disponibles()
        tramas, self._buf = desempaquetar(self._buf)
        return tramas

    def _control(self, op: int, datos: dict) -> bool:
        """PING y CLOSE (vale en cualquier momento). True si la trama era de control."""
        if op == OP_PING:
            self._pong(datos)
            return True
        if op == OP_CLOSE:
            codigo = _int(datos.get("code"))
            self._caida(TXT_ID_NO_VALIDO if codigo == CODIGO_ID_NO_VALIDO else _texto_error(datos, TXT_CORTADA),
                        codigo)
            return True
        return False

    def _pong(self, datos: dict) -> None:
        try:
            if self._tuberia is not None:
                self._tuberia.escribir(empaquetar(OP_PONG, datos))
        except (OSError, ErrorTrama):
            self._caida(TXT_CORTADA)

    def _caida(self, error: str, codigo: int = 0) -> None:
        self.error = error
        self.codigo_cierre = int(codigo or 0)
        self._soltar_tuberia()

    def _soltar_tuberia(self) -> None:
        t, self._tuberia = self._tuberia, None
        self.conectado = False
        self._buf = b""
        if t is not None:
            try:
                t.cerrar()
            except Exception:
                pass


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _texto_error(datos: Any, defecto: str) -> str:
    if isinstance(datos, dict):
        msg = str(datos.get("message") or "").strip()
        if msg:
            return f"Discord: {msg[:160]}"
    return defecto


def _seguro(fn: Callable[[], bool]) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


__all__ = ("OP_HANDSHAKE", "OP_FRAME", "OP_CLOSE", "OP_PING", "OP_PONG", "MAX_TRAMA", "ID_OK",
           "TUBERIAS", "CODIGO_ID_NO_VALIDO", "ErrorTrama", "empaquetar", "desempaquetar",
           "nombre_tuberia", "TuberiaWin32", "ClienteIPC")
