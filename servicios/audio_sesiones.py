"""
servicios/audio_sesiones.py — Cuánto suena cada app del PC (medidor de pico por
sesión de audio de Windows), para que Lune baile con la música.

QUÉ HACE
--------
Windows lleva, por cada app que reproduce sonido, una «sesión de audio» con su
medidor de pico (lo que enseña el mezclador de volumen). Aquí se leen con WASAPI
por comtypes, a mano y sin pycaw ni bibliotecas de tipos:

    IMMDeviceEnumerator → EnumAudioEndpoints(render, activos)     (TODOS los
      IMMDevice → Activate(IAudioSessionManager2)                   endpoints:
        GetSessionEnumerator → IAudioSessionControl                 crítica c.21)
          → IAudioSessionControl2: pid, identificador, ¿sonidos del sistema?
          → IAudioMeterInformation: GetPeakValue (0..1)

Solo se lee el MEDIDOR: no se captura ni se graba audio (decisión D4), no se
abre ningún proceso para saber su nombre (sale del identificador de la sesión:
«…|\\Device\\…\\Spotify.exe%b{…}» → «Spotify») y no se engancha nada. Si el
identificador no lo trae, como último recurso psutil (consulta limitada), y
solo para sesiones que suenan por encima del umbral.

HILOS
-----
COM se inicializa (CoInitializeEx) en el hilo que llama a `abrir()` y todo lo
demás (sesiones, pico, cerrar) debe ir en ese mismo hilo: el del detector de
música (servicios/musica_detector.py). Nunca en el hilo de Qt.

Pero `import comtypes` la PRIMERA vez hace CoInitialize en el hilo que importa y
apunta en atexit un CoUninitialize que corre en el hilo principal: por eso
`preparar_comtypes()` lo importa antes en el hilo principal (el de Qt, o el de
patata), al construir el detector; así ese par queda equilibrado en su hilo y el
del detector solo lleva su CoInitializeEx/CoUninitialize propio.

Y nada de gc.collect() aquí: el hilo del detector podría destruir objetos de Qt
que estén en ciclos (fuera del hilo de Qt). Los punteros COM se sueltan por
recuento (el medidor vacía su caché antes de `finalizar`).

Sin comtypes (o fuera de Windows) `abrir()` lanza y quien lo usa se queda sin
baile automático: nada más se rompe.

El backend COM es inyectable (`MedidorSesiones(com=...)`): los tests usan uno
falso con la misma forma (`inicializar`, `finalizar`, `endpoints`, `sesiones`,
`info`, `medidor`, `pico`).
"""
from __future__ import annotations

import ctypes
import logging
import re
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

_log = logging.getLogger("lune.audio")

CLSID_MMDEVICE_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
E_RENDER = 0                       # EDataFlow.eRender
DEVICE_STATE_ACTIVE = 0x1
CLSCTX_ALL = 23
COINIT_APARTMENTTHREADED = 0x2     # el mismo modelo con el que comtypes se inicializa al importarse
S_OK, S_FALSE = 0, 1

_RE_NOMBRE = re.compile(r"[^\x00-\x1f<>:\"/\\|?*]{1,120}")


@dataclass(frozen=True)
class Sesion:
    """Una sesión de audio: `pid` del proceso, `exe` sin «.exe» («Spotify»),
    `pico` 0..1 en el momento de leerla y `clave` para volver a medirla (`pico`)."""
    pid: int
    exe: str
    pico: float
    clave: str


def exe_de_identificador(ident: str) -> str:
    """Nombre del ejecutable (sin «.exe») a partir del identificador de sesión.

    «{0.0.0.00000000}.{guid}|\\Device\\HarddiskVolume3\\…\\Spotify.exe%b{…}» → «Spotify».
    Los sonidos del sistema («…|#%b{…}») o lo que no acabe en .exe → «».
    """
    if not ident:
        return ""
    s = str(ident)
    if "|" in s:
        s = s.split("|", 1)[1]
    s = s.split("%b", 1)[0].strip()
    if not s or s.startswith("#"):
        return ""
    base = re.split(r"[\\/]", s)[-1].strip()
    if len(base) <= 4 or not base.lower().endswith(".exe"):
        return ""
    base = base[:-4].strip()
    return base if _RE_NOMBRE.fullmatch(base) else ""


def _acotar(p: Any) -> float:
    try:
        v = float(p)
    except (TypeError, ValueError):
        return 0.0
    if v != v:                     # NaN
        return 0.0
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _nombre_psutil(pid: int) -> str:
    """Último recurso: el nombre del proceso con psutil (consulta limitada)."""
    try:
        import psutil
        n = psutil.Process(int(pid)).name() or ""
    except Exception:
        return ""
    return n[:-4] if n.lower().endswith(".exe") else n


# ── Interfaces COM (orden de la vtable obligatorio) ──────────────────────────────
_IFACES: Optional[Dict[str, Any]] = None


def _interfaces() -> Dict[str, Any]:
    """Define (una vez) las interfaces con comtypes. Lanza ImportError sin comtypes."""
    global _IFACES
    if _IFACES is not None:
        return _IFACES
    from ctypes import HRESULT, POINTER, c_float, c_int, c_uint32, c_void_p
    from ctypes.wintypes import BOOL, DWORD, LPCWSTR
    from comtypes import COMMETHOD, GUID, IUnknown

    # Las cadenas que devuelve COM (CoTaskMemAlloc) se piden como puntero crudo
    # para liberarlas con CoTaskMemFree (con LPWSTR comtypes las perdería).
    class IAudioMeterInformation(IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "pfPeak")),
            COMMETHOD([], HRESULT, "GetMeteringChannelCount", (["out"], POINTER(c_uint32), "pnChannelCount")),
            COMMETHOD([], HRESULT, "GetChannelsPeakValues",
                      (["in"], c_uint32, "u32ChannelCount"), (["in"], POINTER(c_float), "afPeakValues")),
            COMMETHOD([], HRESULT, "QueryHardwareSupport", (["out"], POINTER(DWORD), "pdwHardwareSupportMask")),
        ]

    class IAudioSessionControl(IUnknown):
        _iid_ = GUID("{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_int), "pRetVal")),
            COMMETHOD([], HRESULT, "GetDisplayName", (["out"], POINTER(c_void_p), "pRetVal")),
            COMMETHOD([], HRESULT, "SetDisplayName", (["in"], LPCWSTR, "Value"), (["in"], POINTER(GUID), "EventContext")),
            COMMETHOD([], HRESULT, "GetIconPath", (["out"], POINTER(c_void_p), "pRetVal")),
            COMMETHOD([], HRESULT, "SetIconPath", (["in"], LPCWSTR, "Value"), (["in"], POINTER(GUID), "EventContext")),
            COMMETHOD([], HRESULT, "GetGroupingParam", (["out"], POINTER(GUID), "pRetVal")),
            COMMETHOD([], HRESULT, "SetGroupingParam", (["in"], POINTER(GUID), "Override"),
                      (["in"], POINTER(GUID), "EventContext")),
            COMMETHOD([], HRESULT, "RegisterAudioSessionNotification", (["in"], c_void_p, "NewNotifications")),
            COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification", (["in"], c_void_p, "NewNotifications")),
        ]

    class IAudioSessionControl2(IAudioSessionControl):
        _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetSessionIdentifier", (["out"], POINTER(c_void_p), "pRetVal")),
            COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier", (["out"], POINTER(c_void_p), "pRetVal")),
            COMMETHOD([], HRESULT, "GetProcessId", (["out"], POINTER(DWORD), "pRetVal")),
            COMMETHOD([], HRESULT, "IsSystemSoundsSession"),
            COMMETHOD([], HRESULT, "SetDuckingPreference", (["in"], BOOL, "optOut")),
        ]

    class IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_int), "SessionCount")),
            COMMETHOD([], HRESULT, "GetSession", (["in"], c_int, "SessionCount"),
                      (["out"], POINTER(POINTER(IAudioSessionControl)), "Session")),
        ]

    class IAudioSessionManager(IUnknown):
        _iid_ = GUID("{BFA971F1-4D5E-40BB-935E-967039BFBEE4}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetAudioSessionControl", (["in"], POINTER(GUID), "AudioSessionGuid"),
                      (["in"], DWORD, "StreamFlags"), (["out"], POINTER(c_void_p), "SessionControl")),
            COMMETHOD([], HRESULT, "GetSimpleAudioVolume", (["in"], POINTER(GUID), "AudioSessionGuid"),
                      (["in"], DWORD, "StreamFlags"), (["out"], POINTER(c_void_p), "AudioVolume")),
        ]

    class IAudioSessionManager2(IAudioSessionManager):
        _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetSessionEnumerator",
                      (["out"], POINTER(POINTER(IAudioSessionEnumerator)), "SessionEnum")),
            COMMETHOD([], HRESULT, "RegisterSessionNotification", (["in"], c_void_p, "SessionNotification")),
            COMMETHOD([], HRESULT, "UnregisterSessionNotification", (["in"], c_void_p, "SessionNotification")),
            COMMETHOD([], HRESULT, "RegisterDuckNotification", (["in"], LPCWSTR, "sessionID"),
                      (["in"], c_void_p, "duckNotification")),
            COMMETHOD([], HRESULT, "UnregisterDuckNotification", (["in"], c_void_p, "duckNotification")),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], DWORD, "dwClsCtx"),
                      (["in"], c_void_p, "pActivationParams"), (["out"], POINTER(POINTER(IUnknown)), "ppInterface")),
            COMMETHOD([], HRESULT, "OpenPropertyStore", (["in"], DWORD, "stgmAccess"),
                      (["out"], POINTER(c_void_p), "ppProperties")),
            COMMETHOD([], HRESULT, "GetId", (["out"], POINTER(c_void_p), "ppstrId")),
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(DWORD), "pdwState")),
        ]

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint32), "pcDevices")),
            COMMETHOD([], HRESULT, "Item", (["in"], c_uint32, "nDevice"), (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "dataFlow"), (["in"], DWORD, "dwStateMask"),
                      (["out"], POINTER(POINTER(IMMDeviceCollection)), "ppDevices")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], c_int, "dataFlow"), (["in"], c_int, "role"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
            COMMETHOD([], HRESULT, "GetDevice", (["in"], LPCWSTR, "pwstrId"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
            COMMETHOD([], HRESULT, "RegisterEndpointNotificationCallback", (["in"], c_void_p, "pClient")),
            COMMETHOD([], HRESULT, "UnregisterEndpointNotificationCallback", (["in"], c_void_p, "pClient")),
        ]

    _IFACES = {
        "GUID": GUID,
        "IAudioMeterInformation": IAudioMeterInformation,
        "IAudioSessionControl": IAudioSessionControl,
        "IAudioSessionControl2": IAudioSessionControl2,
        "IAudioSessionEnumerator": IAudioSessionEnumerator,
        "IAudioSessionManager": IAudioSessionManager,
        "IAudioSessionManager2": IAudioSessionManager2,
        "IMMDevice": IMMDevice,
        "IMMDeviceCollection": IMMDeviceCollection,
        "IMMDeviceEnumerator": IMMDeviceEnumerator,
    }
    return _IFACES


class ComAudio:
    """Backend real: WASAPI con comtypes. Todo en el hilo que llamó a `inicializar`."""

    def __init__(self):
        self._i: Optional[Dict[str, Any]] = None
        self._enum = None
        self._ole32 = None
        self._co = False

    def inicializar(self) -> None:
        if sys.platform != "win32":
            raise OSError("el medidor de sesiones de audio solo existe en Windows")
        import comtypes                              # sin comtypes: ImportError → no hay baile
        self._i = _interfaces()
        ole = ctypes.WinDLL("ole32")
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        ole.CoInitializeEx.restype = ctypes.c_long
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree.restype = None
        self._ole32 = ole
        # S_OK / S_FALSE: hay que equilibrarlo con CoUninitialize. RPC_E_CHANGED_MODE
        # (el hilo ya tenía otro modelo) también vale para usar COM, sin equilibrar.
        hr = int(ole.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
        self._co = hr in (S_OK, S_FALSE)
        try:
            self._enum = comtypes.CoCreateInstance(self._i["GUID"](CLSID_MMDEVICE_ENUMERATOR),
                                                   self._i["IMMDeviceEnumerator"], CLSCTX_ALL)
        except Exception:
            self.finalizar()
            raise

    def finalizar(self) -> None:
        self._enum = None                            # por recuento, ANTES de CoUninitialize (sin gc aquí)
        if self._co and self._ole32 is not None:
            self._co = False
            try:
                self._ole32.CoUninitialize()
            except Exception:
                pass

    def _cadena(self, p: Any) -> str:
        """Cadena devuelta por COM (CoTaskMemAlloc) → str, liberándola."""
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            try:
                self._ole32.CoTaskMemFree(p)
            except Exception:
                pass

    def endpoints(self) -> List[Tuple[str, Any]]:
        """(id, IMMDevice) de cada salida de audio activa."""
        col = self._enum.EnumAudioEndpoints(E_RENDER, DEVICE_STATE_ACTIVE)
        out = []
        for i in range(int(col.GetCount())):
            try:
                dev = col.Item(i)
                out.append((self._cadena(dev.GetId()) or f"#{i}", dev))
            except Exception:
                continue
        return out

    def sesiones(self, dispositivo: Any) -> List[Any]:
        """Los IAudioSessionControl de un dispositivo."""
        i = self._i
        unk = dispositivo.Activate(i["IAudioSessionManager2"]._iid_, CLSCTX_ALL, None)
        mgr = unk.QueryInterface(i["IAudioSessionManager2"])
        en = mgr.GetSessionEnumerator()
        out = []
        for k in range(int(en.GetCount())):
            try:
                out.append(en.GetSession(k))
            except Exception:
                continue
        return out

    def info(self, control: Any) -> Tuple[int, bool, str, str]:
        """(pid, ¿sonidos del sistema?, identificador, identificador de instancia)."""
        c2 = control.QueryInterface(self._i["IAudioSessionControl2"])
        pid = int(c2.GetProcessId() or 0)
        sistema = c2.IsSystemSoundsSession() == S_OK
        return pid, bool(sistema), self._cadena(c2.GetSessionIdentifier()), \
            self._cadena(c2.GetSessionInstanceIdentifier())

    def medidor(self, control: Any) -> Any:
        return control.QueryInterface(self._i["IAudioMeterInformation"])

    def pico(self, medidor: Any) -> float:
        return float(medidor.GetPeakValue())


class MedidorSesiones:
    """Picos de las sesiones de audio de TODAS las salidas activas.

        m = MedidorSesiones()
        m.abrir()                        # en el hilo que lo va a usar (CoInitializeEx)
        for s in m.sesiones(): ...       # Sesion(pid, exe, pico, clave); sin pid 0 ni sonidos del sistema
        m.pico(s.clave)                  # una sola llamada COM, con el medidor en caché
        m.cerrar()
    """

    def __init__(self, *, com: Any = None, nombre_pid: Optional[Callable[[int], str]] = None):
        self._com = com
        self._nombre_pid = nombre_pid or _nombre_psutil
        self._medidores: Dict[str, Any] = {}
        self._nombres: Dict[int, str] = {}           # pid → nombre de psutil (último recurso)
        self._abierto = False
        self._hilo: Optional[int] = None

    @property
    def abierto(self) -> bool:
        return self._abierto

    def abrir(self) -> None:
        """Inicializa COM en ESTE hilo. Lanza si no hay comtypes o no es Windows."""
        if self._abierto:
            return
        com = self._com if self._com is not None else ComAudio()
        com.inicializar()
        self._com = com
        self._abierto = True
        self._hilo = threading.get_ident()

    def cerrar(self) -> None:
        self._medidores = {}
        if not self._abierto:
            return
        self._abierto = False
        try:
            self._com.finalizar()
        except Exception:
            _log.debug("audio: no pude cerrar COM", exc_info=True)

    def _otro_hilo(self) -> bool:
        if self._hilo is not None and threading.get_ident() != self._hilo:
            _log.warning("audio: MedidorSesiones usado fuera del hilo que lo abrió")
            return True
        return False

    def sesiones(self, umbral_nombre: Optional[float] = None) -> List[Sesion]:
        """Las sesiones que hay ahora (se vuelven a enumerar todas las salidas).

        Salta el pid 0, los sonidos del sistema y las sesiones que mueren a mitad.
        Si el identificador no trae el exe, `umbral_nombre` (None = nunca) dice a
        partir de qué pico se pregunta el nombre a psutil.
        """
        if not self._abierto or self._otro_hilo():
            return []
        try:
            eps = list(self._com.endpoints())
        except Exception:
            _log.debug("audio: no pude enumerar las salidas", exc_info=True)
            return []
        out: List[Sesion] = []
        nuevos: Dict[str, Any] = {}
        for ep_id, dispositivo in eps:
            try:
                controles = list(self._com.sesiones(dispositivo))
            except Exception:
                continue
            for k, control in enumerate(controles):
                try:
                    pid, sistema, ident, inst = self._com.info(control)
                    pid = int(pid or 0)
                    if pid <= 0 or sistema:
                        continue
                    med = self._com.medidor(control)
                    pico = _acotar(self._com.pico(med))
                except Exception:
                    continue                          # el proceso murió entre medias
                clave = str(inst or f"{ep_id}|{pid}|{k}")
                if clave in nuevos:
                    clave = f"{clave}|{ep_id}|{k}"
                exe = exe_de_identificador(ident) or exe_de_identificador(inst)
                if not exe and umbral_nombre is not None and pico >= umbral_nombre:
                    exe = self._nombre(pid)
                nuevos[clave] = med
                out.append(Sesion(pid, exe, pico, clave))
        self._medidores = nuevos
        return out

    def pico(self, clave: str) -> Optional[float]:
        """Pico actual de la sesión `clave` (de la última enumeración) o None si ya no está."""
        med = self._medidores.get(clave)
        if med is None or not self._abierto or self._otro_hilo():
            return None
        try:
            return _acotar(self._com.pico(med))
        except Exception:
            self._medidores.pop(clave, None)
            return None

    def _nombre(self, pid: int) -> str:
        if pid not in self._nombres:
            if len(self._nombres) > 256:
                self._nombres.clear()
            try:
                self._nombres[pid] = str(self._nombre_pid(pid) or "")
            except Exception:
                self._nombres[pid] = ""
        return self._nombres[pid]


def preparar_comtypes(importar: Optional[Callable[[str], Any]] = None) -> bool:
    """Importa comtypes (si está) en ESTE hilo, que debe ser el principal: su
    CoInitialize de la primera importación y el CoUninitialize que apunta en atexit
    quedan así en el mismo hilo. Lo llama DetectorMusica al construirse. Sin
    comtypes o fuera de Windows no hace nada. → ¿importado?"""
    if sys.platform != "win32":
        return False
    if importar is None:
        import importlib
        importar = importlib.import_module
    try:
        importar("comtypes")
        return True
    except Exception:
        return False


def disponible() -> bool:
    """¿Se puede medir? (Windows y comtypes importable; no abre nada)."""
    if sys.platform != "win32":
        return False
    try:
        import importlib.util
        return importlib.util.find_spec("comtypes") is not None
    except Exception:
        return False


__all__ = ("Sesion", "exe_de_identificador", "MedidorSesiones", "ComAudio", "disponible", "preparar_comtypes")
