"""
ui/tema_qss.py — El tema de color (nucleo/tema.py) en los menús Qt.

- `qss_menu(paleta)`: hoja de estilo de QMenu con el look Shibuya Punk (tinta,
  borde neón, selección con el acento translúcido) para el menú de la bandeja y
  los menús contextuales. `BandejaLune.aplicar_qss(qss)` la pone en su QMenu.
- `colores_radial(paleta)`: colores del menú radial de la asistente
  (`MenuRadial.set_colores(c)`), con los nombres de `CircleSelector` de
  Mate-Engine en español (acento, deshabilitado, fondo…).

`paleta` es la de `nucleo.tema.paleta(cfg)` (token → hex); le puede faltar
cualquier token (se usa el de BASE). Sin la paleta (None) sale el cian de siempre.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional

from nucleo import tema
from ui.theme import FONT_BODY

# Neutros que el tema no tiñe (tokens/colors.css): texto y grises.
TEXTO = "#EAF1FF"        # --paper
TEXTO_TENUE = "#97A6C4"  # --gray-300
APAGADO = "#4B5878"      # --gray-500


def _color(pal: Optional[Mapping[str, str]], tok: str) -> str:
    v = (pal or {}).get(tok) or tema.BASE[tok]
    try:
        return "#" + "".join(f"{c:02X}" for c in tema.canales(v)[:3])
    except ValueError:
        return tema.BASE[tok]


def _rgba(hex_: str, alfa: float) -> str:
    r, g, b = tema.canales(hex_)[:3]
    return f"rgba({r}, {g}, {b}, {int(round(max(0.0, min(1.0, alfa)) * 255))})"


def colores_radial(pal: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Colores del menú radial, todos «#RRGGBB» (QColor los acepta tal cual):

    acento (segmento elegido, cian-500) · acento_claro (iconos/texto elegido,
    cian-300) · acento_oscuro (borde del anillo, cian-700) · secundario
    (azul-500) · fondo (anillo, tinta-850) · fondo_borde (tinta-400) · texto ·
    texto_tenue · deshabilitado · pop (amarillo-500).
    """
    return {
        "acento": _color(pal, "cyan-500"),
        "acento_claro": _color(pal, "cyan-300"),
        "acento_oscuro": _color(pal, "cyan-700"),
        "secundario": _color(pal, "blue-500"),
        "fondo": _color(pal, "ink-850"),
        "fondo_borde": _color(pal, "ink-400"),
        "texto": TEXTO,
        "texto_tenue": TEXTO_TENUE,
        "deshabilitado": APAGADO,
        "pop": _color(pal, "yellow-500"),
    }


def qss_menu(pal: Optional[Mapping[str, str]] = None) -> str:
    """Hoja de estilo para QMenu (bandeja y menús contextuales) con la paleta."""
    fondo = _color(pal, "ink-800")
    borde = _color(pal, "cyan-700")
    sep = _color(pal, "ink-400")
    acento = _color(pal, "cyan-500")
    claro = _color(pal, "cyan-300")
    marca_borde = _color(pal, "ink-300")
    return (
        f"QMenu {{ background: {fondo}; color: {TEXTO}; border: 1px solid {borde};"
        f" padding: 4px 0; font-family: '{FONT_BODY}'; }}"
        f" QMenu::item {{ background: transparent; padding: 6px 24px 6px 26px; }}"
        f" QMenu::item:selected {{ background: {_rgba(acento, 0.16)}; color: {claro}; }}"
        f" QMenu::item:disabled {{ color: {APAGADO}; }}"
        f" QMenu::separator {{ height: 1px; background: {sep}; margin: 4px 10px; }}"
        f" QMenu::indicator {{ width: 10px; height: 10px; left: 8px; }}"
        f" QMenu::indicator:checked {{ background: {acento}; border: 1px solid {borde}; }}"
        f" QMenu::indicator:unchecked {{ background: transparent; border: 1px solid {marca_borde}; }}"
        f" QMenu::right-arrow {{ width: 8px; height: 8px; }}"
    )


__all__ = ("qss_menu", "colores_radial", "TEXTO", "TEXTO_TENUE", "APAGADO")
