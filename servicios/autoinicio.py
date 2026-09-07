"""
servicios/autoinicio.py — Arrancar Lune junto con Windows.

Escribe/borra una entrada en la clave Run del usuario actual
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run), que lanza
`iniciar_lune.vbs` con wscript (sin consola). Único sitio que sabe de esto: lo
usan el puente de la piel web y el panel de ajustes nativo.
En sistemas que no son Windows no hace nada y siempre devuelve False.
"""
from __future__ import annotations

import sys
from pathlib import Path

NOMBRE = "LuneCD"
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RAIZ = Path(__file__).resolve().parent.parent
VBS = RAIZ / "iniciar_lune.vbs"


def comando() -> str:
    return f'wscript.exe "{VBS}"'


def activo() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
            valor, _ = winreg.QueryValueEx(k, NOMBRE)
            return bool(valor)
    except OSError:
        return False


def activar() -> bool:
    if sys.platform != "win32" or not VBS.exists():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NOMBRE, 0, winreg.REG_SZ, comando())
        return True
    except OSError:
        return False


def desactivar() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOMBRE)
        return True
    except FileNotFoundError:
        return True          # ya no estaba
    except OSError:
        return False


def establecer(quiere: bool) -> bool:
    """Deja el autoinicio como `quiere` y devuelve el estado resultante."""
    if quiere:
        activar()
    else:
        desactivar()
    return activo()
