"""
effects.py — Glows neón para Lune CD (estilo Shibuya Punk).
Qt no soporta box-shadow en stylesheet, así que el halo se logra con
QGraphicsDropShadowEffect (offset 0 + color = brillo alrededor del widget).
"""
from PyQt6.QtWidgets import QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor


def apply_glow(widget, hex_color: str, radius: int = 20, alpha: int = 170):
    """Aplica un halo de color alrededor del widget."""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(radius)
    eff.setOffset(0, 0)
    c = QColor(hex_color)
    c.setAlpha(alpha)
    eff.setColor(c)
    widget.setGraphicsEffect(eff)


def clear_glow(widget):
    widget.setGraphicsEffect(None)
