"""
servicios/autoinicio.py — Arrancar Lune junto con Windows.

La entrada vive en la clave Run del usuario actual
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, valor «LuneCD») y
lanza `iniciar_lune.vbs` con wscript (sin consola):

- web y nativa: `wscript.exe "<raíz>\\iniciar_lune.vbs" /autoinicio`
  → pythonw main.py --autoinicio (sin pantalla de inicio; nucleo/arranque.py
  decide si abre en la bandeja, con la mascota o con la ventana, tras la espera).
- patata:      `wscript.exe "<raíz>\\iniciar_lune.vbs" /autoinicio /patata`
  → python.exe patata.py --autoinicio en una consola MINIMIZADA, sin exigir PyQt6.

WINDOWS PUEDE DESACTIVARLA SIN BORRARLA
---------------------------------------
El Administrador de tareas (pestaña Inicio) no toca Run: escribe en
`...\\Explorer\\StartupApproved\\Run` un binario de 12 bytes cuyo primer byte es
02 (habilitada) o 03 (deshabilitada; el bit 0 encendido). Sin valor ahí, cuenta
como habilitada. `activo()` = registrada Y aprobada, así que el interruptor de
Lune refleja lo que dijo el Administrador de tareas. `activar()` (el usuario lo
pidió a mano en Lune) escribe 02 + 11 ceros; nadie más toca StartupApproved.

REPARAR
-------
`reparar()` se llama al arrancar: si la entrada EXISTE pero apunta a otra
carpeta (la movieron) o al modo equivocado (cambiaron a patata o al revés, o es
una entrada de antes sin /autoinicio), la reescribe. Nunca la crea (la config
`sistema.autoinicio` no siempre está al día) y nunca toca StartupApproved.

Único sitio que sabe de esto: lo usan el puente web, el panel nativo, patata y
main.py. Fuera de Windows no hace nada (False / ""). `reg` es el módulo winreg
o un doble con la misma API (OpenKey, CreateKeyEx, QueryValueEx, SetValueEx,
DeleteValue, HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ, REG_BINARY): los tests
nunca tocan el registro de verdad.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

NOMBRE = "LuneCD"
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APROBADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RAIZ = Path(__file__).resolve().parent.parent
VBS = RAIZ / "iniciar_lune.vbs"
APROBADO_SI = bytes([0x02]) + bytes(11)          # lo que escribe el Administrador de tareas al habilitar

_RE_VBS = re.compile(r'"([^"]*?\.vbs)"', re.IGNORECASE)


# ── Utilidades ──────────────────────────────────────────────────────────────────
def _reg(reg: Any = None) -> Any:
    """El módulo winreg (o el doble inyectado). None fuera de Windows."""
    if reg is not None:
        return reg
    if sys.platform != "win32":
        return None
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def _es_patata(modo: Any) -> bool:
    return str(modo or "").strip().lower() == "patata"


def _modo_de_config(config: Any = None) -> str:
    """interfaz.modo: de `config` si se da; si no, del config.json (solo lectura)."""
    if config is not None:
        try:
            if isinstance(config, dict):
                return str((config.get("interfaz") or {}).get("modo") or "web")
            return str(config.get("interfaz", "modo", "web") or "web")
        except Exception:
            return "web"
    try:
        from nucleo.config import RUTA_CONFIG
        ruta = Path(RUTA_CONFIG)
    except Exception:
        ruta = RAIZ / "config.json"
    try:
        datos = json.loads(ruta.read_text("utf-8"))
        return str((datos.get("interfaz") or {}).get("modo") or "web")
    except Exception:
        return "web"


def _normal(ruta: str) -> str:
    return os.path.normcase(os.path.normpath(str(ruta)))


def _vbs_de(valor: str) -> Optional[str]:
    m = _RE_VBS.search(str(valor or ""))
    return m.group(1) if m else None


def _misma_ruta(valor: str, raiz: Path = RAIZ) -> bool:
    vbs = _vbs_de(valor)
    return vbs is not None and _normal(vbs) == _normal(Path(raiz) / "iniciar_lune.vbs")


def _misma_orden(a: str, b: str) -> bool:
    """Iguales salvo mayúsculas en la ruta y espacios repetidos."""
    return " ".join(str(a or "").split()).lower() == " ".join(str(b or "").split()).lower()


# ── API ─────────────────────────────────────────────────────────────────────────
def comando(modo: Optional[str] = None, *, raiz: Path = RAIZ) -> str:
    """La orden de la entrada Run. `modo` None → interfaz.modo del config.json."""
    if modo is None:
        modo = _modo_de_config()
    vbs = Path(raiz) / "iniciar_lune.vbs"
    orden = f'wscript.exe "{vbs}" /autoinicio'
    if _es_patata(modo):
        orden += " /patata"
    return orden


def valor_registrado(reg: Any = None) -> Optional[str]:
    """Lo que hay en Run\\LuneCD, o None si no hay entrada (o no es Windows)."""
    r = _reg(reg)
    if r is None:
        return None
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, _RUN) as k:
            valor, _tipo = r.QueryValueEx(k, NOMBRE)
    except OSError:
        return None
    return str(valor) if valor else None


def aprobado_por_windows(reg: Any = None) -> bool:
    """¿La deja arrancar Windows? Sin valor en StartupApproved = sí; primer byte
    con el bit 0 encendido (03) = deshabilitada en el Administrador de tareas."""
    r = _reg(reg)
    if r is None:
        return False
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, _APROBADO) as k:
            valor, _tipo = r.QueryValueEx(k, NOMBRE)
    except OSError:
        return True
    if isinstance(valor, (bytes, bytearray)) and len(valor) >= 1:
        return not (valor[0] & 1)
    return True


def activo(reg: Any = None) -> bool:
    """Registrada Y aprobada por Windows."""
    if _reg(reg) is None:
        return False
    return bool(valor_registrado(reg)) and aprobado_por_windows(reg)


def estado(modo: Optional[str] = None, reg: Any = None) -> Dict[str, Any]:
    """{activo, registrado, aprobado, ruta_ok, modo_ok, comando, esperado}.

    `comando`: lo registrado ("" si no hay); `esperado`: lo que debería haber."""
    esperado = comando(modo)
    if _reg(reg) is None:
        return {"activo": False, "registrado": False, "aprobado": False, "ruta_ok": False,
                "modo_ok": False, "comando": "", "esperado": esperado}
    valor = valor_registrado(reg) or ""
    registrado = bool(valor)
    aprobado = aprobado_por_windows(reg)
    return {
        "activo": registrado and aprobado,
        "registrado": registrado,
        "aprobado": aprobado,
        "ruta_ok": registrado and _misma_ruta(valor),
        "modo_ok": registrado and _misma_orden(valor, esperado),
        "comando": valor,
        "esperado": esperado,
    }


def activar(modo: Optional[str] = None, reg: Any = None) -> bool:
    """El usuario lo pidió: escribe Run y marca la entrada como aprobada (02)."""
    r = _reg(reg)
    if r is None or not VBS.exists():
        return False
    try:
        with r.CreateKeyEx(r.HKEY_CURRENT_USER, _RUN, 0, r.KEY_SET_VALUE) as k:
            r.SetValueEx(k, NOMBRE, 0, r.REG_SZ, comando(modo))
    except OSError:
        return False
    try:
        with r.CreateKeyEx(r.HKEY_CURRENT_USER, _APROBADO, 0, r.KEY_SET_VALUE) as k:
            r.SetValueEx(k, NOMBRE, 0, r.REG_BINARY, APROBADO_SI)
    except OSError:
        pass                       # sin StartupApproved (versiones viejas): con Run basta
    return True


def desactivar(reg: Any = None) -> bool:
    """Borra la entrada Run (StartupApproved no se toca)."""
    r = _reg(reg)
    if r is None:
        return False
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, _RUN, 0, r.KEY_SET_VALUE) as k:
            r.DeleteValue(k, NOMBRE)
        return True
    except FileNotFoundError:
        return True          # ya no estaba
    except OSError:
        return False


def establecer(quiere: bool, modo: Optional[str] = None, reg: Any = None) -> bool:
    """Deja el autoinicio como `quiere` y devuelve el estado resultante."""
    if quiere:
        activar(modo, reg)
    else:
        desactivar(reg)
    return activo(reg)


def reparar(config: Any = None, modo: Optional[str] = None, reg: Any = None) -> str:
    """Corrige una entrada que YA existe: "ruta" (otra carpeta), "modo" (otra
    variante) o "" (nada que hacer, no hay entrada o no es Windows). Nunca crea
    la entrada y nunca toca StartupApproved."""
    r = _reg(reg)
    if r is None:
        return ""
    valor = valor_registrado(reg)
    if not valor:
        return ""
    if modo is None:
        modo = _modo_de_config(config)
    esperado = comando(modo)
    if _misma_orden(valor, esperado) or not VBS.exists():
        return ""
    motivo = "modo" if _misma_ruta(valor) else "ruta"
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, _RUN, 0, r.KEY_SET_VALUE) as k:
            r.SetValueEx(k, NOMBRE, 0, r.REG_SZ, esperado)
    except OSError:
        return ""
    return motivo


__all__ = ("NOMBRE", "RAIZ", "VBS", "APROBADO_SI", "comando", "valor_registrado",
           "aprobado_por_windows", "activo", "estado", "activar", "desactivar",
           "establecer", "reparar")
