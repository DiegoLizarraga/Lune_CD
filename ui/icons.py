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
    # ── Corte 4: acciones de la bandeja, el menú radial y los atajos ──
    "window":     ("stroke", '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 9h20"/>'
                             '<path d="M6 6.5h.01M9 6.5h.01"/>'),
    "radial":     ("stroke", '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3.5"/>'
                             '<path d="M12 2v6.5M12 15.5V22M2 12h6.5M15.5 12H22"/>'),
    "log_out":    ("stroke", '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/>'
                             '<path d="M21 12H9"/>'),
    "message":    ("stroke", '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>'),
    "message_dots": ("stroke", '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>'),
    "eye":        ("stroke", '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>'),
    "smile":      ("stroke", '<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/>'
                             '<path d="M9 9h.01M15 9h.01"/>'),
    "frown":      ("stroke", '<circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/>'
                             '<path d="M9 9h.01M15 9h.01"/>'),
    "angry":      ("stroke", '<circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/>'
                             '<path d="M7.5 8 10 9M14 9l2.5-1"/><path d="M9 10.5h.01M15 10.5h.01"/>'),
    "surprised":  ("stroke", '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="15.5" r="2"/>'
                             '<path d="M9 9h.01M15 9h.01"/>'),
    "thinking":   ("stroke", '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>'
                             '<path d="M12 17h.01"/>'),
    "hand":       ("stroke", '<path d="M18 11V6a2 2 0 0 0-4 0v5"/><path d="M14 10V4a2 2 0 0 0-4 0v6"/>'
                             '<path d="M10 10.5V6a2 2 0 0 0-4 0v8"/>'
                             '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-6-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>'),
    "sun":        ("stroke", '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41'
                             'M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>'),
    "ghost":      ("stroke", '<path d="M9 10h.01M15 10h.01"/>'
                             '<path d="M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8z"/>'),
    "pin":        ("stroke", '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16'
                             'a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7'
                             'a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>'),
    "maximize":   ("stroke", '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3'
                             'M16 21h3a2 2 0 0 0 2-2v-3"/>'),
    "frame":      ("stroke", '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2'
                             'M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="10" r="3"/><path d="M7 18a5 5 0 0 1 10 0"/>'),
    "corner":     ("stroke", '<rect x="3" y="3" width="10" height="10" rx="1.5"/><path d="M21 14v7h-7"/>'
                             '<path d="m21 21-6.5-6.5"/>'),
    "arrow_down": ("stroke", '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>'),
    "monitor":    ("stroke", '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    "phone":      ("stroke", '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6'
                             ' 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81'
                             'a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45'
                             'c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>'),
    "music":      ("stroke", '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'),
    "pause":      ("stroke", '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>'),
    "alarm":      ("stroke", '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2"/><path d="M5 3 2 6M22 6l-3-3"/>'),
    "timer":      ("stroke", '<path d="M10 2h4"/><path d="M12 14l3-3"/><circle cx="12" cy="14" r="8"/>'),
    "cake":       ("stroke", '<path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8"/>'
                             '<path d="M4 16s.5-1 2-1 2.5 2 4 2 2.5-2 4-2 2.5 2 4 2 2-1 2-1"/><path d="M2 21h20"/>'
                             '<path d="M7 8v3M12 8v3M17 8v3"/><path d="M7 4h.01M12 4h.01M17 4h.01"/>'),
    "cup":        ("stroke", '<path d="M6 8h12l-1.5 13h-9z"/><path d="m12 8 2-6h3"/><path d="M6.5 12.5h11"/>'),
    "package":    ("stroke", '<path d="M16.5 9.4 7.55 4.24"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0'
                             'l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
                             '<path d="M3.3 7 12 12l8.7-5M12 22V12"/>'),
    "gamepad":    ("stroke", '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4M8 10v4"/>'
                             '<path d="M15 13h.01M18 11h.01"/>'),
    "palette":    ("stroke", '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/>'
                             '<circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/>'
                             '<path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.13'
                             '-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.56-2.5 5.56-5.55'
                             'C21.97 6.01 17.46 2 12 2z"/>'),
    "power":      ("stroke", '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>'),
    "taskbar":    ("stroke", '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 16h20"/><path d="M6 18h3"/>'),
    "box":        ("stroke", '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73'
                             'l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
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
