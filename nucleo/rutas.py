"""
nucleo/rutas.py — Dónde vive cada cosa de Lune: el programa y lo tuyo.

Única fuente de verdad de las rutas. Hasta la 11.1 cada módulo se anclaba por su
cuenta a la raíz del repo (Path(__file__).parent.parent) y valía para todo: lo que
trae Lune y lo que escribe. Desde la 11.2 Lune también se instala como un programa
(el Setup.exe de GitHub Releases, empaquetado con PyInstaller) y ahí son dos sitios:

                    DESDE EL CÓDIGO (git)          INSTALADA (Setup.exe)
  RECURSOS          la raíz del repo               la carpeta del programa (_internal)
  (lo que trae      ui_web/, assets/, fonts/,      %LOCALAPPDATA%\\Programs\\Lune CD\\_internal
   Lune; se lee)    lune_face/, sonidos/…          (cada actualización la reemplaza)
  DATOS             la raíz del repo               %APPDATA%\\Lune CD
  (lo tuyo; se      config.json, datos.json,       (ni el instalador ni las actualizaciones
   escribe)         memoria.json, chats/, logs/…   lo tocan; al desinstalar se pregunta)

Desde el código RECURSOS y DATOS son la misma carpeta: nada cambia respecto a la 11.1.

LUNE_CD_DATOS (variable de entorno) fuerza la carpeta de DATOS en los dos casos: los
tests la ponen (tests/conftest.py) para no tocar nunca lo de verdad, y sirve para una
copia portátil o para probar una versión instalada sin mezclar tus datos.

Los ejecutables: instalada, «Lune.exe» (ventanas) y «LunePatata.exe» (la terminal)
comparten _internal/. Desde el código son python(w).exe con main.py / patata.py.
orden_app(), orden_patata() y orden_reinicio() dan la orden lista para subprocess.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

# ¿Corremos empaquetados (PyInstaller)? sys.frozen lo pone el cargador de PyInstaller.
INSTALADA: bool = bool(getattr(sys, "frozen", False))

# Raíz del código: el repo; instalada, _internal (sys._MEIPASS: PyInstaller deja ahí
# los datos con la misma estructura que el repo y __file__ de cada módulo cuelga de ahí).
CODIGO: Path = (Path(getattr(sys, "_MEIPASS", "")) if INSTALADA and getattr(sys, "_MEIPASS", None)
                else Path(__file__).resolve().parent.parent)

# Lo que trae Lune y solo se lee.
RECURSOS: Path = CODIGO

# La carpeta con los .exe (instalada) o la raíz del repo (desde el código).
PROGRAMA: Path = Path(sys.executable).resolve().parent if INSTALADA else CODIGO

NOMBRE_CARPETA_DATOS = "Lune CD"
VARIABLE_DATOS = "LUNE_CD_DATOS"

EXE_APP = "Lune.exe"
EXE_PATATA = "LunePatata.exe"

# Mutex de «Lune está abierta» (la app y patata lo crean al arrancar y lo sueltan al
# salir): el instalador (packaging/lune.iss, CheckForMutexes) espera a que no exista
# antes de reemplazar archivos y el desinstalador pide cerrar Lune si existe.
MUTEX_ABIERTA = "LuneCD_Abierta"

# AppUserModelID de Windows: fijo (el mismo que el acceso directo del menú Inicio que
# crea el instalador). Si cambiara con cada versión, el icono anclado a la barra de
# tareas y la búsqueda de Windows dejarían de reconocer a Lune tras cada actualización.
AUMID = "DiegoLizarraga.LuneCD"


def carpeta_datos(entorno=None, instalada: bool = None) -> Path:
    """Dónde van los datos del usuario (sin crearla). `entorno` e `instalada` son para los tests."""
    entorno = os.environ if entorno is None else entorno
    instalada = INSTALADA if instalada is None else instalada
    forzada = str(entorno.get(VARIABLE_DATOS) or "").strip()
    if forzada:
        return Path(forzada).expanduser().resolve()
    if instalada:
        base = str(entorno.get("APPDATA") or "").strip()
        raiz = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return raiz / NOMBRE_CARPETA_DATOS
    return Path(__file__).resolve().parent.parent


def carpeta_local(entorno=None, instalada: bool = None) -> Path:
    """Dónde va lo pesado o desechable (logs, cachés, bots). Sin crearla."""
    entorno = os.environ if entorno is None else entorno
    instalada = INSTALADA if instalada is None else instalada
    forzada = str(entorno.get(VARIABLE_DATOS) or "").strip()
    if forzada:
        return Path(forzada).expanduser().resolve()
    if instalada:
        base = str(entorno.get("LOCALAPPDATA") or "").strip()
        raiz = Path(base) if base else Path.home() / "AppData" / "Local"
        return raiz / NOMBRE_CARPETA_DATOS
    return Path(__file__).resolve().parent.parent


# Lo tuyo y lo local. Se calculan una vez al importar (como hacía cada módulo con su RAIZ).
DATOS: Path = carpeta_datos()
LOCAL: Path = carpeta_local()

for _carpeta in {DATOS, LOCAL} - {CODIGO}:
    try:
        _carpeta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def recurso(*partes: str) -> Path:
    """Ruta de algo que trae Lune (solo lectura)."""
    return RECURSOS.joinpath(*partes)


def dato(*partes: str) -> Path:
    """Ruta de algo del usuario (se puede escribir)."""
    return DATOS.joinpath(*partes)


def local(*partes: str) -> Path:
    """Ruta de algo pesado o desechable del usuario (logs, cachés, bots)."""
    return LOCAL.joinpath(*partes)


# ── Avisos de «falta instalar…» ─────────────────────────────────────────────────

AVISO_NO_INCLUIDO = ("No viene en la versión instalada de Lune: solo funciona usando Lune "
                     "desde el código (mira el README).")


def como_instalar(*paquetes: str) -> str:
    """Cómo conseguir lo que falta. Desde el código, la orden de pip; instalada no hay
    pip (todo lo que se puede ya viene dentro), así que se dice sin comandos. Único
    sitio que escribe «pip install» para el usuario."""
    lista = " ".join(p for p in paquetes if p)
    if INSTALADA:
        return AVISO_NO_INCLUIDO
    return f"pip install {lista}".strip()


# ── Órdenes para lanzar Lune ────────────────────────────────────────────────────

def _hermano(exe: str, nombre: str) -> str:
    """python.exe ↔ pythonw.exe en la misma carpeta, si existe; si no, el mismo."""
    candidato = Path(exe).with_name(nombre)
    return str(candidato) if candidato.exists() else exe


def orden_app(*args: str) -> List[str]:
    """Abrir la app de ventanas (sin consola)."""
    if INSTALADA:
        return [str(PROGRAMA / EXE_APP), *args]
    return [_hermano(sys.executable, "pythonw.exe"), str(CODIGO / "main.py"), *args]


def orden_patata(*args: str) -> List[str]:
    """Abrir Lune en la terminal (necesita una consola: python.exe, no pythonw)."""
    if INSTALADA:
        return [str(PROGRAMA / EXE_PATATA), *args]
    return [_hermano(sys.executable, "python.exe"), str(CODIGO / "patata.py"), *args]


def orden_reinicio() -> List[str]:
    """Volver a lanzar este mismo proceso con los mismos argumentos."""
    if INSTALADA:
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


__all__ = (
    "INSTALADA", "CODIGO", "RECURSOS", "PROGRAMA", "DATOS", "LOCAL", "NOMBRE_CARPETA_DATOS",
    "VARIABLE_DATOS", "EXE_APP", "EXE_PATATA", "MUTEX_ABIERTA", "AUMID", "AVISO_NO_INCLUIDO",
    "carpeta_datos", "carpeta_local", "recurso", "dato", "local", "como_instalar",
    "orden_app", "orden_patata", "orden_reinicio",
)
