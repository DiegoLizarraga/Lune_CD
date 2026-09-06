"""
icons.py — Iconos SVG de línea (estilo Lucide, trazo 2px) para Lune CD.
Adaptados del Design System "Shibuya Punk". Se renderizan a QPixmap/QIcon
tintados con el color que se pida, para que combinen con el contexto
(cyan / azul / amarillo / texto).

Uso:
    from ui.icons import icon, icon_pixmap
    boton.setIcon(icon("gear", COLORS["accent"], 18))
    label.setPixmap(icon_pixmap("cpu", COLORS["cyan"], 20))
"""
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QPixmap, QPainter, QIcon

# kind: "stroke" (contorno) o "fill" (relleno). inner = elementos SVG internos.
ICONS = {
    "cloud":      ("stroke", '<path d="M17.5 19a4.5 4.5 0 0 0 0-9h-1.26A8 8 0 1 0 4 15.25"/>'),
    "cpu":        ("stroke", '<rect x="6" y="6" width="12" height="12" rx="1"/>'
                             '<path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>'),
    "gear":       ("stroke", '<circle cx="12" cy="12" r="3"/>'
                             '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    "trash":      ("stroke", '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6"/>'),
    "brain":      ("stroke", '<path d="M12 5a3 3 0 1 0-5.99.14 4 4 0 0 0-1.5 7.06A3.5 3.5 0 0 0 8 18.5 3 3 0 0 0 12 19m0-14a3 3 0 1 1 5.99.14 4 4 0 0 1 1.5 7.06A3.5 3.5 0 0 1 16 18.5 3 3 0 0 1 12 19m0-14v14"/>'),
    "tool":       ("stroke", '<path d="M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2-2 2.6-2.6z"/>'),
    "volume":     ("stroke", '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M19 12a7 7 0 0 0-3-5.7"/><path d="M15.5 8.5a3.5 3.5 0 0 1 0 5"/>'),
    "volume_off": ("stroke", '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M22 9l-6 6"/><path d="M16 9l6 6"/>'),
    "send":       ("stroke", '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'),
    "stop":       ("fill",   '<rect x="6" y="6" width="12" height="12" rx="1"/>'),
    "telegram":   ("stroke", '<path d="m22 3-9.5 9.5"/><path d="M22 3 15 21l-4-8-8-4 19-6z"/>'),
    "moon":       ("stroke", '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>'),
    "search":     ("stroke", '<path d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z"/><path d="m21 21-4.3-4.3"/>'),
    "bolt":       ("fill",   '<path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z"/>'),
    "user":       ("stroke", '<path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="7" r="4"/>'),
    "import":     ("stroke", '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>'),
    "copy":       ("stroke", '<rect x="9" y="9" width="12" height="12" rx="2"/>'
                             '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
    "check":      ("stroke", '<path d="M20 6 9 17l-5-5"/>'),
    "clip":       ("stroke", '<path d="M21.4 11.05 12.25 20.2a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'),
    "mic":        ("stroke", '<rect x="9" y="2" width="6" height="12" rx="3"/>'
                             '<path d="M19 10a7 7 0 0 1-14 0"/><path d="M12 19v3"/>'),
    "image":      ("stroke", '<rect x="3" y="3" width="18" height="18" rx="2"/>'
                             '<circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>'),
    "history":    ("stroke", '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'
                             '<path d="M12 7v5l3 2"/>'),
    "refresh":    ("stroke", '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>'),
    "close":      ("stroke", '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
    "plus":       ("stroke", '<path d="M12 5v14"/><path d="M5 12h14"/>'),
}


def _svg(name: str, color: str) -> str:
    kind, inner = ICONS[name]
    if kind == "stroke":
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                f'fill="none" stroke="{color}" stroke-width="2" '
                f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="{color}">{inner}</svg>')


def icon_pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    """Devuelve un QPixmap del icono tintado (nítido en pantallas HiDPI)."""
    if name not in ICONS:
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(_svg(name, color).encode("utf-8")))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str, size: int = 20) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))
