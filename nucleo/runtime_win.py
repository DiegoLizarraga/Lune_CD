"""
nucleo/runtime_win.py — Evita el APPCRASH de Whisper (y otras librerías C++) en Windows.

EL PROBLEMA
-----------
PyQt6 trae SU PROPIA copia del runtime de C++ (MSVCP140.dll 14.26, de 2020) en
`PyQt6/Qt6/bin`. Al importar PyQt6 esa copia entra al proceso y, como Windows
solo carga UNA DLL por nombre, cualquier módulo que se importe después y pida
`msvcp140.dll` se queda con la vieja. `ctranslate2` (el motor de faster-whisper),
`onnxruntime` (Kokoro) y otros están compilados con Visual Studio 2022 reciente
y necesitan ≥ 14.40: en cuanto tocan un `std::mutex` de la DLL vieja, el
proceso muere con 0xC0000005 dentro de MSVCP140.dll. En el visor de eventos
sale como "Faulting module: ...PyQt6\\Qt6\\bin\\MSVCP140.dll". En la práctica:
"pulso el micrófono y Lune se cierra".

LA SOLUCIÓN
-----------
Cargar ANTES de PyQt6 el runtime que ya tiene Windows en System32 (mucho más
nuevo, y el runtime de Microsoft es compatible hacia atrás: Qt corre igual con
él). Al llegar PyQt6, `msvcp140.dll` ya está en el proceso y se reutiliza.

Solo se hace si el de System32 es igual o más nuevo que el de PyQt6: si fuera
más viejo, Qt no arrancaría, y eso es peor que no poder dictar.

Uso: llamar a `precargar_msvc()` como PRIMERA cosa en main.py, antes de
cualquier `import PyQt6`. Es inofensivo fuera de Windows.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll")

# Se rellena en precargar_msvc(): qué se precargó y por qué (para el log).
ultimo_informe = ""


def version_dll(ruta: str) -> Tuple[int, int, int, int]:
    """Versión de archivo (a.b.c.d) de una DLL; (0,0,0,0) si no se pudo leer."""
    if sys.platform != "win32":
        return (0, 0, 0, 0)
    try:
        import ctypes
        from ctypes import wintypes

        ver = ctypes.WinDLL("version.dll")
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL

        tam = ver.GetFileVersionInfoSizeW(ruta, None)
        if not tam:
            return (0, 0, 0, 0)
        buf = ctypes.create_string_buffer(tam)
        if not ver.GetFileVersionInfoW(ruta, 0, tam, buf):
            return (0, 0, 0, 0)
        ptr, ln = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(ln)) or not ptr.value:
            return (0, 0, 0, 0)

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [("dwSignature", wintypes.DWORD), ("dwStrucVersion", wintypes.DWORD),
                        ("dwFileVersionMS", wintypes.DWORD), ("dwFileVersionLS", wintypes.DWORD),
                        ("dwProductVersionMS", wintypes.DWORD), ("dwProductVersionLS", wintypes.DWORD),
                        ("dwFileFlagsMask", wintypes.DWORD), ("dwFileFlags", wintypes.DWORD),
                        ("dwFileOS", wintypes.DWORD), ("dwFileType", wintypes.DWORD),
                        ("dwFileSubtype", wintypes.DWORD), ("dwFileDateMS", wintypes.DWORD),
                        ("dwFileDateLS", wintypes.DWORD)]

        info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        return (info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF)
    except Exception:
        return (0, 0, 0, 0)


def carpeta_qt_bin() -> Optional[Path]:
    """`PyQt6/Qt6/bin` sin importar PyQt6 (importarlo cargaría justo lo que evitamos)."""
    try:
        spec = importlib.util.find_spec("PyQt6")
        if spec and spec.submodule_search_locations:
            for loc in spec.submodule_search_locations:
                p = Path(loc) / "Qt6" / "bin"
                if p.is_dir():
                    return p
    except Exception:
        pass
    return None


def precargar_msvc() -> List[str]:
    """
    Carga el runtime de C++ de System32 antes que el de PyQt6. Devuelve los
    nombres precargados (vacío si no aplica). Nunca lanza.
    """
    global ultimo_informe
    if sys.platform != "win32":
        ultimo_informe = "no es Windows"
        return []
    if "PyQt6.QtCore" in sys.modules:
        ultimo_informe = "PyQt6 ya estaba cargado: tarde para precargar"
        return []
    try:
        import ctypes
    except Exception:
        return []
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    qt_bin = carpeta_qt_bin()
    cargados, motivos = [], []
    for nombre in DLLS:
        sistema = sysdir / nombre
        if not sistema.exists():
            continue
        de_qt = qt_bin / nombre if qt_bin else None
        if de_qt is not None and de_qt.exists():
            v_sis, v_qt = version_dll(str(sistema)), version_dll(str(de_qt))
            if v_sis < v_qt:
                motivos.append(f"{nombre}: el del sistema ({'.'.join(map(str, v_sis))}) es más viejo que el de Qt")
                continue
        try:
            ctypes.WinDLL(str(sistema))
            cargados.append(nombre)
        except OSError as e:
            motivos.append(f"{nombre}: {e}")
    ultimo_informe = ("precargados de System32: " + ", ".join(cargados)) if cargados else "nada precargado"
    if motivos:
        ultimo_informe += " · " + "; ".join(motivos)
    return cargados
