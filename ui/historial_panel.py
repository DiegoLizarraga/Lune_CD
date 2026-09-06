"""
historial_panel.py — Lista las conversaciones guardadas y permite reabrirlas.
"""
from datetime import datetime

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QMessageBox,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme import COLORS, FONT_DISPLAY, FONT_MONO, FONT_BODY
from ui.icons import icon


def _fecha_legible(iso: str) -> str:
    """«hace 5 min», «ayer», «12/03» — lo que sea más útil de un vistazo."""
    if not iso:
        return ""
    try:
        cuando = datetime.fromisoformat(iso)
    except ValueError:
        return iso[:10]
    delta = datetime.now() - cuando
    seg = delta.total_seconds()
    if seg < 60:
        return "ahora mismo"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    if seg < 86400:
        return f"hace {int(seg // 3600)} h"
    if seg < 172800:
        return "ayer"
    if delta.days < 7:
        return f"hace {delta.days} días"
    return cuando.strftime("%d/%m/%Y")


class HistorialPanel(QFrame):
    abrir = pyqtSignal(str)     # id de la sesión a cargar
    nueva = pyqtSignal()

    def __init__(self, gestor, parent=None):
        super().__init__(parent)
        self.gestor = gestor
        self.setStyleSheet("QFrame{background:transparent;}")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:transparent;}}"
            f"QScrollBar:vertical{{background:{COLORS['surface']};width:8px;border-radius:4px;}}"
            f"QScrollBar::handle:vertical{{background:{COLORS['border2']};border-radius:4px;}}"
        )
        outer.addWidget(self.scroll)
        self.refrescar()

    def refrescar(self):
        content = QFrame(); layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 22, 36, 36); layout.setSpacing(12)

        over = QLabel("// CONVERSACIONES"); over.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        over.setStyleSheet(f"color:{COLORS['text_dim']};letter-spacing:2px;")
        layout.addWidget(over)
        title = QLabel("HISTORIAL"); title.setFont(QFont(FONT_DISPLAY, 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{COLORS['text']};letter-spacing:2px;")
        layout.addWidget(title)

        sesiones = self.gestor.listar()
        sub = QLabel(f"{len(sesiones)} conversación(es) guardadas. Se conservan las más recientes."
                     if sesiones else
                     "Todavía no hay nada guardado. Habla conmigo y esto se irá llenando.")
        sub.setWordWrap(True); sub.setFont(QFont(FONT_MONO, 9))
        sub.setStyleSheet(f"color:{COLORS['text_muted']};")
        layout.addWidget(sub)

        fila_acciones = QHBoxLayout(); fila_acciones.setSpacing(8)
        btn_nueva = QPushButton("  NUEVA CONVERSACIÓN")
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.setIcon(icon("plus", COLORS["bg"], 15)); btn_nueva.setIconSize(QSize(15, 15))
        btn_nueva.setFont(QFont(FONT_DISPLAY, 10, QFont.Weight.Bold)); btn_nueva.setFixedHeight(42)
        btn_nueva.setStyleSheet(
            f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['cyan_dark']},"
            f"stop:1 {COLORS['accent']});color:{COLORS['bg']};border:none;border-radius:3px;"
            f"padding:0 16px;letter-spacing:1px;}}QPushButton:hover{{background:{COLORS['accent']};}}"
        )
        btn_nueva.clicked.connect(self.nueva.emit)
        fila_acciones.addWidget(btn_nueva)

        if sesiones:
            btn_borrar = QPushButton("BORRAR TODO")
            btn_borrar.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_borrar.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold)); btn_borrar.setFixedHeight(42)
            btn_borrar.setStyleSheet(
                f"QPushButton{{background:transparent;color:{COLORS['text_dim']};"
                f"border:2px solid {COLORS['border']};border-radius:3px;padding:0 14px;}}"
                f"QPushButton:hover{{background:{COLORS['error']}22;color:{COLORS['error']};"
                f"border-color:{COLORS['error']};}}"
            )
            btn_borrar.clicked.connect(self._borrar_todo)
            fila_acciones.addWidget(btn_borrar)
        fila_acciones.addStretch()
        layout.addLayout(fila_acciones)

        for s in sesiones:
            layout.addWidget(self._tarjeta(s))

        layout.addStretch()
        self.scroll.setWidget(content)

    def _tarjeta(self, s) -> QFrame:
        card = QFrame()
        activa = s["id"] == self.gestor.sesion_id
        borde = COLORS["accent"] if activa else COLORS["border"]
        card.setStyleSheet(
            f"QFrame{{background:{COLORS['surface']};border:2px solid {borde};border-radius:3px;}}"
        )
        cl = QHBoxLayout(card); cl.setContentsMargins(16, 12, 16, 12); cl.setSpacing(12)

        col = QVBoxLayout(); col.setSpacing(3)
        t = QLabel(s["titulo"]); t.setWordWrap(True)
        t.setFont(QFont(FONT_BODY, 11, QFont.Weight.Bold))
        t.setStyleSheet(
            f"color:{COLORS['accent'] if activa else COLORS['text']};"
            "border:none;background:transparent;"
        )
        detalles = [_fecha_legible(s["actualizado"]), f"{s['mensajes']} mensajes"]
        if s.get("personaje"):
            detalles.append(s["personaje"])
        d = QLabel("  ·  ".join(detalles)); d.setFont(QFont(FONT_MONO, 8))
        d.setStyleSheet(f"color:{COLORS['text_muted']};border:none;background:transparent;")
        col.addWidget(t); col.addWidget(d)
        cl.addLayout(col, 1)

        if activa:
            tag = QLabel("ACTIVA"); tag.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
            tag.setStyleSheet(f"color:{COLORS['bg']};background:{COLORS['accent']};padding:4px 8px;border:none;")
            cl.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            abrir = QPushButton("ABRIR"); abrir.setCursor(Qt.CursorShape.PointingHandCursor)
            abrir.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold)); abrir.setFixedHeight(30)
            abrir.setStyleSheet(
                f"QPushButton{{background:{COLORS['surface2']};color:{COLORS['accent']};"
                f"border:2px solid {COLORS['cyan_dark']};border-radius:2px;padding:0 12px;letter-spacing:1px;}}"
                f"QPushButton:hover{{background:{COLORS['surface3']};border-color:{COLORS['accent']};}}"
            )
            abrir.clicked.connect(lambda _=False, sid=s["id"]: self.abrir.emit(sid))
            cl.addWidget(abrir, 0, Qt.AlignmentFlag.AlignVCenter)

        borrar = QPushButton(); borrar.setCursor(Qt.CursorShape.PointingHandCursor)
        borrar.setIcon(icon("trash", COLORS["error"], 14)); borrar.setIconSize(QSize(14, 14))
        borrar.setFixedSize(30, 30); borrar.setToolTip("Borrar esta conversación")
        borrar.setStyleSheet(
            f"QPushButton{{background:{COLORS['surface2']};border:2px solid {COLORS['error']}55;border-radius:2px;}}"
            f"QPushButton:hover{{background:{COLORS['error']}33;border-color:{COLORS['error']};}}"
        )
        borrar.clicked.connect(lambda _=False, sid=s["id"], ti=s["titulo"]: self._borrar(sid, ti))
        cl.addWidget(borrar, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    def _borrar(self, sesion_id, titulo):
        r = QMessageBox.question(self, "Borrar conversación",
                                 f"¿Eliminar «{titulo}»?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        self.gestor.borrar(sesion_id)
        self.refrescar()

    def _borrar_todo(self):
        r = QMessageBox.question(
            self, "Borrar todo el historial",
            "¿Eliminar TODAS las conversaciones guardadas?\n\n"
            "Tus recuerdos personales (/memoria) no se tocan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        n = self.gestor.borrar_todo()
        QMessageBox.information(self, "Historial borrado", f"Eliminé {n} conversación(es).")
        self.nueva.emit()
        self.refrescar()
