"""
personajes_panel.py — Panel de Roleplay / Personajes para Lune CD.
Lista los personajes, permite elegir el activo, importar character cards
(TavernAI / SillyTavern, JSON o PNG) y borrar los importados.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from theme import COLORS, FONT_DISPLAY, FONT_MONO, FONT_BODY
from icons import icon
import personajes


class PersonajesPanel(QFrame):
    elegido = pyqtSignal(str)   # emite el nombre del personaje elegido

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame{background:transparent;}")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"QScrollArea{{border:none;background:transparent;}}QScrollBar:vertical{{background:{COLORS['surface']};width:8px;border-radius:4px;}}QScrollBar::handle:vertical{{background:{COLORS['border2']};border-radius:4px;}}")
        outer.addWidget(self.scroll)
        self._render()

    def refrescar(self):
        self._render()

    # ── Construcción ───────────────────────────────────────────────────────────
    def _render(self):
        content = QFrame(); layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 22, 36, 36); layout.setSpacing(14)

        over = QLabel("// ROL · PERSONAJES"); over.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        over.setStyleSheet(f"color:{COLORS['text_dim']};letter-spacing:2px;")
        layout.addWidget(over)
        title = QLabel("PERSONAJES"); title.setFont(QFont(FONT_DISPLAY, 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{COLORS['text']};letter-spacing:2px;")
        layout.addWidget(title)
        sub = QLabel("Elige quién habla contigo. Importa character cards (TavernAI / SillyTavern) en .json o .png.")
        sub.setWordWrap(True); sub.setFont(QFont(FONT_MONO, 9)); sub.setStyleSheet(f"color:{COLORS['text_muted']};")
        layout.addWidget(sub)

        activo = personajes.activo_nombre().lower()
        for p in personajes.listar():
            layout.addWidget(self._tarjeta(p, es_activo=p.get("nombre", "").lower() == activo))

        # Botón importar
        btn = QPushButton("  IMPORTAR CHARACTER CARD"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(icon("import", COLORS["bg"], 16))
        btn.setFont(QFont(FONT_DISPLAY, 11, QFont.Weight.Bold)); btn.setFixedHeight(46)
        btn.setStyleSheet(f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['cyan_dark']},stop:1 {COLORS['accent']});color:{COLORS['bg']};border:none;border-radius:3px;letter-spacing:1px;padding:0 16px;}}QPushButton:hover{{background:{COLORS['accent']};}}")
        btn.clicked.connect(self._importar)
        fila = QHBoxLayout(); fila.addWidget(btn); fila.addStretch()
        layout.addSpacing(6); layout.addLayout(fila)

        layout.addStretch()
        self.scroll.setWidget(content)

    def _tarjeta(self, p, es_activo):
        nombre = p.get("nombre", "?")
        desc = (p.get("descripcion") or p.get("personalidad") or "Sin descripción.").strip()
        if len(desc) > 160: desc = desc[:160] + "…"

        card = QFrame()
        borde = COLORS["accent"] if es_activo else COLORS["border"]
        card.setStyleSheet(f"QFrame{{background:{COLORS['surface']};border:2px solid {borde};border-radius:3px;}}")
        cl = QHBoxLayout(card); cl.setContentsMargins(16, 12, 16, 12); cl.setSpacing(12)

        col = QVBoxLayout(); col.setSpacing(3)
        n = QLabel(nombre.upper()); n.setFont(QFont(FONT_DISPLAY, 13, QFont.Weight.Bold))
        n.setStyleSheet(f"color:{COLORS['accent'] if es_activo else COLORS['text']};letter-spacing:1px;border:none;background:transparent;")
        d = QLabel(desc); d.setWordWrap(True); d.setFont(QFont(FONT_BODY, 10))
        d.setStyleSheet(f"color:{COLORS['text_muted']};border:none;background:transparent;")
        col.addWidget(n); col.addWidget(d)
        cl.addLayout(col, 1)

        if es_activo:
            tag = QLabel("ACTIVO"); tag.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
            tag.setStyleSheet(f"color:{COLORS['bg']};background:{COLORS['accent']};padding:4px 8px;border:none;")
            cl.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            usar = QPushButton("USAR"); usar.setCursor(Qt.CursorShape.PointingHandCursor)
            usar.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold)); usar.setFixedHeight(30)
            usar.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};border:2px solid {COLORS['cyan_dark']};border-radius:2px;padding:0 12px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}")
            usar.clicked.connect(lambda _=False, nm=nombre: self.elegido.emit(nm))
            cl.addWidget(usar, 0, Qt.AlignmentFlag.AlignVCenter)

            # No permitir borrar el primero (Lune por defecto)
            if personajes.listar() and personajes.listar()[0].get("nombre", "").lower() != nombre.lower():
                borrar = QPushButton("✕"); borrar.setCursor(Qt.CursorShape.PointingHandCursor)
                borrar.setFixedSize(30, 30); borrar.setFont(QFont(FONT_BODY, 11, QFont.Weight.Bold))
                borrar.setStyleSheet(f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['error']};border:2px solid {COLORS['error']}55;border-radius:2px;}}QPushButton:hover{{background:{COLORS['error']}33;border-color:{COLORS['error']};}}")
                borrar.clicked.connect(lambda _=False, nm=nombre: self._borrar(nm))
                cl.addWidget(borrar, 0, Qt.AlignmentFlag.AlignVCenter)

        return card

    # ── Acciones ─────────────────────────────────────────────────────────────--
    def _importar(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Importar character card", "",
            "Character cards (*.json *.png);;Todos (*.*)",
        )
        if not ruta:
            return
        try:
            p = personajes.importar(ruta)
            QMessageBox.information(self, "Importado",
                                    f"Personaje «{p['nombre']}» importado. Pulsa USAR para activarlo.")
            self._render()
        except Exception as e:
            QMessageBox.warning(self, "No se pudo importar", str(e))

    def _borrar(self, nombre):
        r = QMessageBox.question(self, "Borrar personaje",
                                 f"¿Eliminar a «{nombre}»?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        personajes.eliminar(nombre)
        self._render()
