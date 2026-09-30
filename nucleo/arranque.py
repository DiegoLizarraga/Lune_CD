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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from nucleo import nombres_antiguos

COMOS = ("bandeja", "asistente", "ventana")
COMO_DEFECTO = "bandeja"
RETRASO_DEFECTO_S = 20
RETRASO_MAX_S = 300
_BANDERAS_AUTOINICIO = frozenset({"--autoinicio", "/autoinicio", "-autoinicio"})


@dataclass(frozen=True)
class Opciones:
    autoinicio: bool = False


@dataclass(frozen=True)
class Plan:
    splash: bool
    mostrar_ventana: bool
    abrir_asistente: bool
    retraso_s: int
    silencioso: bool


PLAN_NORMAL = Plan(splash=True, mostrar_ventana=True, abrir_asistente=False, retraso_s=0, silencioso=False)


def parsear_args(argv: Iterable[Any]) -> Opciones:
    """`--autoinicio` o `/autoinicio` (sin distinguir mayúsculas). Lo demás se ignora."""
    try:
        banderas = {str(a).strip().lower() for a in (argv or ())}
    except TypeError:
        banderas = set()
    return Opciones(autoinicio=bool(banderas & _BANDERAS_AUTOINICIO))


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


__all__ = ("COMOS", "COMO_DEFECTO", "RETRASO_DEFECTO_S", "RETRASO_MAX_S", "Opciones", "Plan",
           "PLAN_NORMAL", "parsear_args", "plan_arranque", "como", "retraso_s")
