"""
nucleo/arranque.py — Cómo arranca la app: a mano o junto con Windows (puro, sin Qt).

A mano (doble clic en el .vbs, el acceso directo…): pantalla de inicio y
ventana principal, como siempre.

Con Windows (`iniciar_lune.vbs /autoinicio` → `main.py --autoinicio`, ver
servicios/autoinicio.py) el inicio de sesión ya va cargado, así que:
- sin pantalla de inicio;
- se espera `sistema.autoinicio_retraso_s` (20 s por defecto, 0–300) antes de
  crear la ventana, para no sumar QtWebEngine (150–250 MB) al arranque de Windows;
- `sistema.autoinicio_como` decide cómo aparece:
    bandeja → ventana oculta, solo el icono de la bandeja (por defecto, D3);
    asistente → ventana oculta y la asistente en el escritorio;
    ventana → la ventana principal visible;
- `silencioso`: si ya había otra Lune abierta, esta se va sin traerla al frente
  (a quien arrancó el PC no le salta una ventana).

    opc = parsear_args(sys.argv[1:])
    plan = plan_arranque(config, opc)   # → Plan(splash, mostrar_ventana, abrir_asistente, retraso_s, silencioso)

Tras un reinicio (servicios/actualizador.reiniciar) la Lune nueva llega con
`--esperar-pid N`: main() espera (hasta ESPERA_PID_S) a que la vieja muera ANTES de
mirar la instancia única; si no, se conectaba al servidor de la vieja y se iba.

Instalada (Lune.exe / LunePatata.exe), `preparar_instalada()` al principio de main()
deja el proceso como lo espera el resto (desde el código no hace nada).
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from nucleo import nombres_antiguos

COMOS = ("bandeja", "asistente", "ventana")
COMO_DEFECTO = "bandeja"
RETRASO_DEFECTO_S = 20
RETRASO_MAX_S = 300
_BANDERAS_AUTOINICIO = frozenset({"--autoinicio", "/autoinicio", "-autoinicio"})
BANDERA_ESPERAR_PID = "--esperar-pid"
ESPERA_PID_S = 10.0


@dataclass(frozen=True)
class Opciones:
    autoinicio: bool = False
    esperar_pid: int = 0          # tras un reinicio: el PID de la Lune que se está cerrando


@dataclass(frozen=True)
class Plan:
    splash: bool
    mostrar_ventana: bool
    abrir_asistente: bool
    retraso_s: int
    silencioso: bool


PLAN_NORMAL = Plan(splash=True, mostrar_ventana=True, abrir_asistente=False, retraso_s=0, silencioso=False)


def parsear_args(argv: Iterable[Any]) -> Opciones:
    """`--autoinicio` o `/autoinicio` (sin distinguir mayúsculas) y `--esperar-pid N`
    (o `--esperar-pid=N`). Lo demás se ignora."""
    try:
        args = [str(a).strip() for a in (argv or ())]
    except TypeError:
        args = []
    banderas = {a.lower() for a in args}
    return Opciones(autoinicio=bool(banderas & _BANDERAS_AUTOINICIO), esperar_pid=_pid_de(args))


def _pid_de(args) -> int:
    """El N de `--esperar-pid N` / `--esperar-pid=N` (el último que haya); 0 si no hay o es basura."""
    pid = 0
    for i, a in enumerate(args):
        bajo = a.lower()
        if bajo == BANDERA_ESPERAR_PID:
            valor = args[i + 1] if i + 1 < len(args) else ""
        elif bajo.startswith(BANDERA_ESPERAR_PID + "="):
            valor = a.split("=", 1)[1]
        else:
            continue
        try:
            n = int(str(valor).strip())
        except ValueError:
            continue
        pid = n if n > 0 else 0
    return pid


def sin_esperar_pid(args: Iterable[Any]) -> list:
    """`args` sin ningún `--esperar-pid N` (para no arrastrarlos de un reinicio a otro)."""
    salida, saltar = [], False
    for a in list(args or ()):
        if saltar:
            saltar = False
            continue
        bajo = str(a).strip().lower()
        if bajo == BANDERA_ESPERAR_PID:
            saltar = True
            continue
        if bajo.startswith(BANDERA_ESPERAR_PID + "="):
            continue
        salida.append(a)
    return salida


def _pid_vivo(pid: int) -> bool:
    """¿Sigue vivo el proceso `pid`? Con psutil; sin él no se sabe y se da por muerto."""
    try:
        import psutil
    except ImportError:
        return False
    try:
        if not psutil.pid_exists(int(pid)):
            return False
        return psutil.Process(int(pid)).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def esperar_a_que_muera(pid: Any, limite_s: float = ESPERA_PID_S, *,
                        vivo: Optional[Callable[[int], bool]] = None,
                        dormir: Callable[[float], Any] = time.sleep,
                        reloj: Callable[[], float] = time.monotonic) -> bool:
    """Espera (como mucho `limite_s`) a que el proceso `pid` termine. True si ya no
    está (o nunca estuvo); False si se acabó el tiempo. Nunca se espera a sí mismo."""
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return True
    if pid <= 0 or pid == os.getpid():
        return True
    vivo = vivo or _pid_vivo
    fin = reloj() + max(0.0, float(limite_s or 0))
    while vivo(pid):
        if reloj() >= fin:
            return False
        dormir(0.1)
    return True


def preparar_instalada(*, instalada: Optional[bool] = None, entorno: Any = None,
                       modulo_sys: Any = None, cambiar_dir: Optional[Callable[[str], Any]] = None,
                       congelar: Optional[Callable[[], Any]] = None) -> bool:
    """Instalada (Lune.exe / LunePatata.exe), antes que nada:
    - multiprocessing.freeze_support() (Lune no usa multiprocessing: es un seguro);
    - HF_HOME en la carpeta local (cache/huggingface) si no lo tienes puesto: ahí van
      los modelos de Whisper (antes de que nada importe faster_whisper);
    - el directorio de trabajo a la carpeta de tus datos (desde la clave Run es
      System32): red de seguridad por si queda alguna ruta relativa;
    - stdout/stderr a os.devnull si no hay (Lune.exe no tiene consola).
    Desde el código no hace nada y devuelve False. Los argumentos son para los tests."""
    from nucleo import rutas
    instalada = rutas.INSTALADA if instalada is None else instalada
    if not instalada:
        return False
    entorno = os.environ if entorno is None else entorno
    s = sys if modulo_sys is None else modulo_sys
    try:
        if congelar is None:
            import multiprocessing
            congelar = multiprocessing.freeze_support
        congelar()
    except Exception:
        pass
    if not str(entorno.get("HF_HOME") or "").strip():
        entorno["HF_HOME"] = str(rutas.local("cache", "huggingface"))
    try:
        (cambiar_dir or os.chdir)(str(rutas.DATOS))
    except OSError:
        pass
    for nombre in ("stdout", "stderr"):
        if getattr(s, nombre, None) is None:
            try:
                setattr(s, nombre, open(os.devnull, "w", encoding="utf-8"))
            except OSError:
                pass
    return True


def _sistema(config: Any, clave: str, defecto: Any) -> Any:
    try:
        if config is None:
            return defecto
        if isinstance(config, dict):
            return (config.get("sistema") or {}).get(clave, defecto)
        return config.get("sistema", clave, defecto)
    except Exception:
        return defecto


def como(config: Any) -> str:
    """sistema.autoinicio_como validado (lo desconocido → bandeja)."""
    c = str(_sistema(config, "autoinicio_como", COMO_DEFECTO) or "").strip().lower()
    c = nombres_antiguos.como_autoinicio(c)           # el nombre de antes de la 11
    return c if c in COMOS else COMO_DEFECTO


def retraso_s(config: Any) -> int:
    """sistema.autoinicio_retraso_s en [0, 300] (basura → 20)."""
    v = _sistema(config, "autoinicio_retraso_s", RETRASO_DEFECTO_S)
    try:
        if isinstance(v, bool):
            raise TypeError
        n = int(float(v))
    except (TypeError, ValueError, OverflowError):
        n = RETRASO_DEFECTO_S
    return max(0, min(RETRASO_MAX_S, n))


def plan_arranque(config: Any, opciones: Opciones) -> Plan:
    """Qué hace main() al arrancar (ver el docstring del módulo)."""
    if not getattr(opciones, "autoinicio", False):
        return PLAN_NORMAL
    c = como(config)
    return Plan(
        splash=False,
        mostrar_ventana=(c == "ventana"),
        abrir_asistente=(c == "asistente"),
        retraso_s=retraso_s(config),
        silencioso=True,
    )


__all__ = ("COMOS", "COMO_DEFECTO", "RETRASO_DEFECTO_S", "RETRASO_MAX_S", "BANDERA_ESPERAR_PID",
           "ESPERA_PID_S", "Opciones", "Plan", "PLAN_NORMAL", "parsear_args", "sin_esperar_pid",
           "esperar_a_que_muera", "preparar_instalada", "plan_arranque", "como", "retraso_s")
