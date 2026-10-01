"""
servicios/autoinicio.py — Arrancar Lune junto con Windows.

La entrada vive en la clave Run del usuario actual
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, valor «LuneCD»).

Desde el código lanza `iniciar_lune.vbs` con wscript (sin consola):

- web y nativa: `wscript.exe "<raíz>\\iniciar_lune.vbs" /autoinicio`
  → pythonw main.py --autoinicio (sin pantalla de inicio; nucleo/arranque.py
  decide si abre en la bandeja, con la asistente o con la ventana, tras la espera).
- patata:      `wscript.exe "<raíz>\\iniciar_lune.vbs" /autoinicio /patata`
  → python.exe patata.py --autoinicio en una consola MINIMIZADA, sin exigir PyQt6.

Instalada (nucleo/rutas.INSTALADA), la misma orden en todos los modos:
`"<carpeta del programa>\\Lune.exe" --autoinicio`. Con la interfaz en patata,
main.py abre LunePatata.exe --autoinicio minimizada y se retira (_lanzar_patata).

UNA INSTALACIÓN Y UNA COPIA DEL CÓDIGO EN EL MISMO PC
-----------------------------------------------------
Las dos usan el valor «LuneCD». Cada una solo se da por activa con una entrada de
SU tipo (Lune.exe la instalada, iniciar_lune.vbs la del código) y de SU carpeta, y
`reparar()` nunca se apropia de una entrada del otro tipo: si no, cada una la
reescribiría a su ruta en cada arranque. Encenderlo a mano (`activar`) sí la cambia
(lo pidió el usuario); apagarlo (`desactivar`) no borra la del otro tipo (esa no
arranca a esta Lune).

WINDOWS PUEDE DESACTIVARLA SIN BORRARLA
---------------------------------------
El Administrador de tareas (pestaña Inicio) no toca Run: escribe en
`...\\Explorer\\StartupApproved\\Run` un binario de 12 bytes cuyo primer byte es
02 (habilitada) o 03 (deshabilitada; el bit 0 encendido). Sin valor ahí, cuenta
como habilitada. `activo()` = registrada (de este tipo y de esta carpeta) Y
aprobada, así que el interruptor de Lune refleja lo que dijo el Administrador de
tareas. `activar()` (el usuario lo pidió a mano en Lune) escribe 02 + 11 ceros;
nadie más toca StartupApproved.

REPARAR
-------
`reparar()` se llama al arrancar: si la entrada EXISTE, es de este tipo y apunta a
otra carpeta (la movieron) o al modo equivocado (cambiaron a patata o al revés, o es
una entrada de antes sin /autoinicio), la reescribe. Nunca la crea (la config
`sistema.autoinicio` no siempre está al día), nunca toca StartupApproved y nunca
toca una entrada del otro tipo.

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

from nucleo import rutas

NOMBRE = "LuneCD"
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APROBADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
# Donde está el lanzador: la raíz del repo (código) o la carpeta de Lune.exe (instalada).
RAIZ = rutas.PROGRAMA
VBS = RAIZ / "iniciar_lune.vbs"
APROBADO_SI = bytes([0x02]) + bytes(11)          # lo que escribe el Administrador de tareas al habilitar

# Los dos tipos de entrada: la de la copia del código (.vbs) y la de la instalada (.exe).
TIPO_CODIGO = "codigo"
TIPO_INSTALADA = "instalada"

_RE_LANZADOR = re.compile(r'"([^"]*?\.(?:vbs|exe))"', re.IGNORECASE)


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
        ruta = rutas.dato("config.json")
    try:
        datos = json.loads(ruta.read_text("utf-8"))
        return str((datos.get("interfaz") or {}).get("modo") or "web")
    except Exception:
        return "web"


def _normal(ruta: str) -> str:
    return os.path.normcase(os.path.normpath(str(ruta)))


def tipo_propio() -> str:
    """El tipo de entrada de esta Lune: TIPO_INSTALADA (Lune.exe) o TIPO_CODIGO (.vbs)."""
    return TIPO_INSTALADA if rutas.INSTALADA else TIPO_CODIGO


def lanzador(raiz: Optional[Path] = None) -> Path:
    """Lo que lanza la entrada de esta Lune: Lune.exe (instalada) o iniciar_lune.vbs."""
    base = Path(RAIZ if raiz is None else raiz)
    return base / (rutas.EXE_APP if rutas.INSTALADA else "iniciar_lune.vbs")


def _lanzador_de(valor: str) -> Optional[str]:
    """La ruta entre comillas que lanza la entrada: el .vbs si lo hay (wscript.exe puede
    ir entre comillas delante); si no, el .exe. None si no reconozco ninguno."""
    rutas_entre_comillas = _RE_LANZADOR.findall(str(valor or ""))
    for ruta in rutas_entre_comillas:
        if ruta.lower().endswith(".vbs"):
            return ruta
    return rutas_entre_comillas[0] if rutas_entre_comillas else None


def tipo_de(valor: str) -> Optional[str]:
    """TIPO_CODIGO (lanza un .vbs), TIPO_INSTALADA (lanza un .exe) o None (no la reconozco)."""
    ruta = _lanzador_de(valor)
    if ruta is None:
        return None
    return TIPO_CODIGO if ruta.lower().endswith(".vbs") else TIPO_INSTALADA


def _de_la_otra(valor: str) -> bool:
    """¿Es la entrada de la otra Lune (la instalada si esta es la del código, o al revés)?"""
    tipo = tipo_de(valor)
    return tipo is not None and tipo != tipo_propio()


def _misma_ruta(valor: str, raiz: Optional[Path] = None) -> bool:
    ruta = _lanzador_de(valor)
    return ruta is not None and _normal(ruta) == _normal(lanzador(raiz))


def _es_de_esta(valor: str) -> bool:
    """¿La entrada es de esta Lune: de su tipo y de su carpeta?"""
    return tipo_de(valor) == tipo_propio() and _misma_ruta(valor)


def _misma_orden(a: str, b: str) -> bool:
    """Iguales salvo mayúsculas en la ruta y espacios repetidos."""
    return " ".join(str(a or "").split()).lower() == " ".join(str(b or "").split()).lower()


# ── API ─────────────────────────────────────────────────────────────────────────
def comando(modo: Optional[str] = None, *, raiz: Optional[Path] = None) -> str:
    """La orden de la entrada Run. Instalada, la misma en todos los modos (main.py
    abre la terminal minimizada si la interfaz es patata). `modo` None → interfaz.modo
    del config.json."""
    if rutas.INSTALADA:
        return f'"{lanzador(raiz)}" --autoinicio'
    if modo is None:
        modo = _modo_de_config()
    orden = f'wscript.exe "{lanzador(raiz)}" /autoinicio'
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
    """Registrada (de este tipo y de esta carpeta) Y aprobada por Windows."""
    if _reg(reg) is None:
        return False
    valor = valor_registrado(reg)
    return bool(valor) and _es_de_esta(valor) and aprobado_por_windows(reg)


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
        "activo": registrado and _es_de_esta(valor) and aprobado,
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
    if r is None or not lanzador().exists():
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
    """Borra la entrada Run (StartupApproved no se toca). La de la otra Lune (instalada
    o desde el código) se deja: esa no arranca a esta, que ya queda sin arrancar."""
    r = _reg(reg)
    if r is None:
        return False
    valor = valor_registrado(reg)
    if valor and _de_la_otra(valor):
        return True
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
    """Corrige una entrada de ESTE tipo que YA existe: "ruta" (otra carpeta), "modo"
    (otra variante) o "" (nada que hacer, no hay entrada, es de la otra Lune o no es
    Windows). Nunca crea la entrada y nunca toca StartupApproved."""
    r = _reg(reg)
    if r is None:
        return ""
    valor = valor_registrado(reg)
    if not valor or _de_la_otra(valor):
        return ""
    if modo is None:
        modo = _modo_de_config(config)
    esperado = comando(modo)
    if _misma_orden(valor, esperado) or not lanzador().exists():
        return ""
    motivo = "modo" if _misma_ruta(valor) else "ruta"
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, _RUN, 0, r.KEY_SET_VALUE) as k:
            r.SetValueEx(k, NOMBRE, 0, r.REG_SZ, esperado)
    except OSError:
        return ""
    return motivo


__all__ = ("NOMBRE", "RAIZ", "VBS", "APROBADO_SI", "TIPO_CODIGO", "TIPO_INSTALADA", "comando",
           "lanzador", "tipo_propio", "tipo_de", "valor_registrado", "aprobado_por_windows",
           "activo", "estado", "activar", "desactivar", "establecer", "reparar")
