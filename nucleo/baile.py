"""
nucleo/baile.py — Lo común del baile procedural (con la música del PC o a mano).

- `ESTILOS`: los 8 bailes procedurales (las páginas VRM y animada los tienen
  con el mismo nombre; los sprites y la terminal los aproximan).
- `opciones_pagina(config, estilo)`: lo que se manda con `luneBailar(true, opts)`
  (`{estilo, cambiar, cambiarS, particulas}`).
- Handlers de las herramientas del modelo `mascota_bailar` y `parar_baile`
  (lune_core/catalogo_herramientas.py): `ctx["baile"]` es el controlador
  (ui/baile_qt.ControlBaile) y `ctx["en_ui"]` lo ejecuta en el hilo de Qt.
- `frames_ascii(kaomoji)`: los cuadros del baile en la terminal (patata).

Sin Qt.
"""
from __future__ import annotations

import os
import random
from typing import Any, Callable, Mapping, Optional, Tuple, Union

ESTILOS: Tuple[str, ...] = ("rebote", "vaiven", "brazos_arriba", "palmas", "cadera", "cabeceo",
                            "puno_alterno", "paso_lateral")
MIN_S, MAX_S, DEFECTO_S = 5, 300, 30
CAMBIAR_MIN_S, CAMBIAR_MAX_S, CAMBIAR_DEFECTO_S = 5, 120, 15

FRAMES_ASCII: Tuple[str, ...] = ("\\o/", "|o|", "/o\\", "_o_")
FRAMES_KAOMOJI: Tuple[str, ...] = ("ヽ(^o^)ﾉ", "┏(^o^)┛", "ヾ(^o^)ノ", "┗(^o^)┓")

# Motivos de la tabla de prioridades (nucleo/estado_mascota) en palabras.
MOTIVOS = {
    "juego": "hay un juego delante",
    "alarma": "hay una alarma sonando",
    "grande": "estoy en pantalla grande",
    "salvapantallas": "estoy de salvapantallas",
    "mmd": "ya estoy con otro baile",
    "sentada": "estoy sentada",
    "comida": "estoy comiendo",
    "durmiendo": "estoy dormida",
}


def _cfg(config: Any, clave: str, defecto: Any) -> Any:
    try:
        return config.get("baile", clave, defecto) if config is not None else defecto
    except Exception:
        return defecto


def _entero(v: Any, lo: int, hi: int, defecto: int) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return defecto
    return max(lo, min(hi, n))


def segundos_validos(v: Any) -> int:
    """Duración de un baile a mano, entre MIN_S y MAX_S (DEFECTO_S si no vale)."""
    if v is None or v == "":
        return DEFECTO_S
    return _entero(v, MIN_S, MAX_S, DEFECTO_S)


def estilo_valido(estilo: Any) -> Optional[str]:
    e = str(estilo or "").strip().lower()
    return e if e in ESTILOS else None


def opciones_pagina(config: Any, estilo: Optional[str] = None, *,
                    rng: Optional[random.Random] = None) -> dict:
    """{estilo, cambiar, cambiarS, particulas} para `luneBailar(true, opts)`.

    Sin `estilo` (o con uno que no existe), uno al azar."""
    e = estilo_valido(estilo) or (rng or random).choice(ESTILOS)
    return {
        "estilo": e,
        "cambiar": bool(_cfg(config, "cambiar", False)),
        "cambiarS": _entero(_cfg(config, "cambiar_s", CAMBIAR_DEFECTO_S), CAMBIAR_MIN_S, CAMBIAR_MAX_S,
                            CAMBIAR_DEFECTO_S),
        "particulas": bool(_cfg(config, "particulas", True)),
    }


def motivo_legible(motivo: str) -> str:
    return MOTIVOS.get(str(motivo or ""), str(motivo or ""))


def es_windows_terminal(env: Optional[Mapping[str, str]] = None) -> bool:
    """¿La terminal es Windows Terminal? (pinta bien los kaomoji; conhost no siempre)."""
    e = os.environ if env is None else env
    return bool(e.get("WT_SESSION"))


def frames_ascii(kaomoji: bool) -> Tuple[str, ...]:
    """Cuadros del baile en la terminal: \\o/ |o| /o\\ _o_ (o kaomoji)."""
    return FRAMES_KAOMOJI if kaomoji else FRAMES_ASCII


# ── Herramientas del modelo ──────────────────────────────────────────────────────
def _de_ctx(ctx: Any, clave: str) -> Any:
    """ctx[clave] (dict) o ctx.clave (objeto), también dentro de ctx['contexto']
    (el Ejecutor envuelve así los ctx que no son dict; como nucleo/sueno)."""
    if ctx is None:
        return None
    v = ctx.get(clave) if isinstance(ctx, Mapping) else getattr(ctx, clave, None)
    if v is None and isinstance(ctx, Mapping) and ctx.get("contexto") is not None:
        c = ctx.get("contexto")
        v = c.get(clave) if isinstance(c, Mapping) else getattr(c, clave, None)
    return v


def _en_ui(ctx: Any, fn: Callable[[], Any]) -> Any:
    en_ui = _de_ctx(ctx, "en_ui")
    return en_ui(fn) if callable(en_ui) else fn()


def herramienta_bailar(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `mascota_bailar` ({segundos?, cancion?})."""
    baile = _de_ctx(ctx, "baile")
    if baile is None or not callable(getattr(baile, "bailar", None)):
        return False, "Ahora mismo no puedo bailar aquí."
    args = args if isinstance(args, Mapping) else {}
    seg = segundos_validos(args.get("segundos"))
    cancion = str(args.get("cancion") or "").strip()
    try:
        ok = _en_ui(ctx, lambda: baile.bailar(seg, origen="manual"))
    except Exception as e:
        return False, f"No pude ponerme a bailar: {e}"[:300]
    if ok is False:
        motivo = motivo_legible(getattr(baile, "ultimo_motivo", "") or "")
        return False, "Ahora no puedo bailar" + (f": {motivo}." if motivo else ".")
    nota = " Aún no tengo reproductor de canciones: bailo con lo que suene." if cancion else ""
    return f"¡A bailar! {seg} s.{nota}"


def herramienta_parar(args: Any = None, ctx: Any = None) -> Union[str, Tuple[bool, str]]:
    """Handler de `parar_baile` ({})."""
    baile = _de_ctx(ctx, "baile")
    if baile is None or not callable(getattr(baile, "parar", None)):
        return False, "Ahora mismo no estoy bailando aquí."
    try:
        ok = _en_ui(ctx, lambda: baile.parar())
    except Exception as e:
        return False, f"No pude parar: {e}"[:300]
    return "Vale, dejo de bailar." if ok else "No estaba bailando."


__all__ = (
    "ESTILOS", "MIN_S", "MAX_S", "DEFECTO_S", "segundos_validos", "estilo_valido", "opciones_pagina",
    "motivo_legible", "es_windows_terminal", "frames_ascii", "herramienta_bailar", "herramienta_parar",
)
