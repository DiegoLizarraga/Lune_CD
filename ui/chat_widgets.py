"""
chat_widgets.py — Widgets de la conversación: pestañas de proveedor,
burbujas de mensaje con markdown, bloques de código e indicador de "escribiendo…".
"""
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from ui import markdown_qt

from ui.theme import COLORS, PROVIDER_META, FONT_DISPLAY, FONT_BODY, FONT_MONO
from ui.icons import icon, icon_pixmap
from ui.effects import apply_glow, clear_glow


class ProviderTab(QFrame):
    clicked = pyqtSignal(str)
    def __init__(self, provider_id, meta, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id; self.meta = meta; self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFixedHeight(64)
        layout = QHBoxLayout(self); layout.setContentsMargins(14, 8, 14, 8); layout.setSpacing(10)
        self.icon_lbl = QLabel(); self.icon_lbl.setFixedWidth(30); self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_col = QVBoxLayout(); text_col.setSpacing(2)
        self.name_lbl = QLabel(self.meta["label"]); self.name_lbl.setFont(QFont(FONT_DISPLAY, 10, QFont.Weight.Bold))
        self.desc_lbl = QLabel(self.meta["desc"]); self.desc_lbl.setFont(QFont(FONT_MONO, 8))
        text_col.addWidget(self.name_lbl); text_col.addWidget(self.desc_lbl)
        # Punto de estado: verde si el proveedor responde, gris si no se sabe.
        self.estado = QLabel("●"); self.estado.setFixedWidth(12)
        self.estado.setFont(QFont("Segoe UI", 9))
        self.estado.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;")
        self.estado.setToolTip("Estado desconocido")
        layout.addWidget(self.icon_lbl); layout.addLayout(text_col, 1); layout.addWidget(self.estado)
        self._apply_style(False)

    def set_estado(self, disponible: bool, detalle: str = ""):
        color = COLORS["success"] if disponible else COLORS["error"]
        self.estado.setStyleSheet(f"color:{color};background:transparent;")
        self.estado.setToolTip(detalle or ("Disponible" if disponible else "No responde"))

    def _apply_style(self, active):
        c, d = self.meta["color"], self.meta["dark"]
        svg = self.meta.get("svg")
        if active:
            self.setStyleSheet(f"ProviderTab {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {d}88,stop:1 {d}22);border:2px solid {c};border-radius:2px;}}")
            self.name_lbl.setStyleSheet(f"color:{c};background:transparent;letter-spacing:1px;"); self.desc_lbl.setStyleSheet(f"color:{c}aa;background:transparent;")
            if svg: self.icon_lbl.setPixmap(icon_pixmap(svg, c, 20))
            apply_glow(self, c, radius=16, alpha=110)
        else:
            clear_glow(self)
            self.setStyleSheet(f"ProviderTab {{background:transparent;border:2px solid transparent;border-left:2px solid {COLORS['border']};border-radius:2px;}}ProviderTab:hover{{background:{COLORS['surface2']};border-left:2px solid {c};}}")
            self.name_lbl.setStyleSheet(f"color:{COLORS['text']};background:transparent;letter-spacing:1px;"); self.desc_lbl.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;")
            if svg: self.icon_lbl.setPixmap(icon_pixmap(svg, COLORS["text_muted"], 20))
        self.icon_lbl.setStyleSheet("background:transparent;")

    def set_active(self, active):
        self._active = active; self._apply_style(active)
    def mousePressEvent(self, event):
        self.clicked.emit(self.provider_id)


# ── Bloque de código con botón de copiar ──────────────────────────────────────

class BloqueCodigo(QFrame):
    """Un ``` ``` ``` del modelo: cabecera con el lenguaje y botón de copiar."""

    def __init__(self, codigo: str, lenguaje: str = "", parent=None):
        super().__init__(parent)
        self.codigo = codigo
        self.setStyleSheet(
            f"BloqueCodigo{{background:{COLORS['bg']};border:1px solid {COLORS['border']};"
            f"border-left:3px solid {COLORS['accent']};border-radius:2px;}}"
        )
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        cabecera = QFrame()
        cabecera.setStyleSheet(f"QFrame{{background:{COLORS['surface2']};border:none;}}")
        cl = QHBoxLayout(cabecera); cl.setContentsMargins(10, 4, 6, 4); cl.setSpacing(6)
        etiqueta = QLabel((lenguaje or "código").upper())
        etiqueta.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        etiqueta.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;letter-spacing:1px;")

        self.btn_copiar = QPushButton("COPIAR")
        self.btn_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copiar.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self.btn_copiar.setFixedHeight(22)
        self.btn_copiar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{COLORS['text_dim']};"
            f"border:1px solid {COLORS['border']};border-radius:2px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{COLORS['accent']};border-color:{COLORS['accent']};}}"
        )
        self.btn_copiar.clicked.connect(self._copiar)
        cl.addWidget(etiqueta); cl.addStretch(); cl.addWidget(self.btn_copiar)
        layout.addWidget(cabecera)

        cuerpo = QLabel(codigo)
        cuerpo.setFont(QFont(FONT_MONO, 10))
        cuerpo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cuerpo.setWordWrap(True)
        cuerpo.setStyleSheet(
            f"color:{COLORS['text']};background:transparent;border:none;padding:10px 12px;"
        )
        cuerpo.setMaximumWidth(560)
        layout.addWidget(cuerpo)

    def _copiar(self):
        QApplication.clipboard().setText(self.codigo)
        self.btn_copiar.setText("COPIADO")
        QTimer.singleShot(1400, lambda: self.btn_copiar.setText("COPIAR"))


# ── Burbuja de mensaje ────────────────────────────────────────────────────────

class MessageBubble(QFrame):
    """
    Burbuja de chat con markdown.

    Durante el streaming se pinta texto plano en una sola etiqueta (rehacer los
    widgets 16 veces por segundo iría fatal). Al terminar, `update_text()` sin
    `streaming` reconstruye el contenido ya formateado.
    """

    def __init__(self, text, is_user, provider_id="openrouter", parent=None,
                 markdown: bool = True, adjuntos=None):
        super().__init__(parent)
        self.is_user = is_user
        self.provider_id = provider_id
        self.markdown = markdown
        self.texto = text
        self.adjuntos = adjuntos or []
        self._build(text)

    def _build(self, text):
        outer = QHBoxLayout(self); outer.setContentsMargins(12, 4, 12, 4); outer.setSpacing(10)
        meta = PROVIDER_META.get(self.provider_id, PROVIDER_META["openrouter"]); color = meta["color"]

        if self.is_user:
            outer.addStretch()
            bubble = QFrame()
            bubble.setStyleSheet(f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {COLORS['blue_dark']},stop:1 {COLORS['user_bubble']});border-radius:3px;border:2px solid {COLORS['blue']};}}")
            bl = QVBoxLayout(bubble); bl.setContentsMargins(15, 11, 15, 11); bl.setSpacing(4)
            self.contenido = QVBoxLayout(); self.contenido.setSpacing(6)
            bl.addLayout(self.contenido)
            self._pintar(text, color_texto="#FFFFFF")
            if self.adjuntos:
                bl.addWidget(self._fila_adjuntos("#C4D0E6"))
            ts = QLabel(datetime.now().strftime("%H:%M")); ts.setFont(QFont(FONT_MONO, 8))
            ts.setStyleSheet("color:#C4D0E6;background:transparent;"); ts.setAlignment(Qt.AlignmentFlag.AlignRight)
            bl.addWidget(ts)
            outer.addWidget(bubble)
        else:
            avatar = QLabel(meta["icon"]); avatar.setFixedSize(36, 36); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFont(QFont("Segoe UI Emoji", 15))
            avatar.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {meta['dark']},stop:1 {color}44);border-radius:2px;border:2px solid {color}88;")
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

            bubble = QFrame()
            bubble.setStyleSheet(f"QFrame{{background:{COLORS['bot_bubble']};border-radius:3px;border:1px solid {COLORS['border']};border-left:3px solid {color};}}")
            bl = QVBoxLayout(bubble); bl.setContentsMargins(15, 11, 15, 11); bl.setSpacing(4)

            fila = QHBoxLayout(); fila.setSpacing(8)
            sender = QLabel(meta["label"]); sender.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
            sender.setStyleSheet(f"color:{color};background:transparent;letter-spacing:1px;")
            self.btn_copiar_todo = QPushButton()
            self.btn_copiar_todo.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_copiar_todo.setIcon(icon("copy", COLORS["text_dim"], 13))
            self.btn_copiar_todo.setIconSize(QSize(13, 13)); self.btn_copiar_todo.setFixedSize(22, 20)
            self.btn_copiar_todo.setToolTip("Copiar el mensaje")
            self.btn_copiar_todo.setStyleSheet(
                f"QPushButton{{background:transparent;border:none;}}"
                f"QPushButton:hover{{background:{COLORS['surface2']};border-radius:2px;}}"
            )
            self.btn_copiar_todo.clicked.connect(self._copiar_todo)
            fila.addWidget(sender); fila.addStretch(); fila.addWidget(self.btn_copiar_todo)
            bl.addLayout(fila)

            self.contenido = QVBoxLayout(); self.contenido.setSpacing(6)
            bl.addLayout(self.contenido)
            self._pintar(text)

            self.pie = QLabel(datetime.now().strftime("%H:%M")); self.pie.setFont(QFont(FONT_MONO, 8))
            self.pie.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;")
            bl.addWidget(self.pie)
            outer.addWidget(bubble); outer.addStretch()

    def _fila_adjuntos(self, color) -> QLabel:
        nombres = ", ".join(a.get("nombre", "archivo") for a in self.adjuntos)
        lbl = QLabel(f"📎 {nombres}")
        lbl.setFont(QFont(FONT_MONO, 8)); lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{color};background:transparent;border:none;")
        return lbl

    # ── Pintado del contenido ──────────────────────────────────────────────────
    def _limpiar(self):
        while self.contenido.count():
            item = self.contenido.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _etiqueta(self, texto, color_texto, rico: bool) -> QLabel:
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        lbl.setOpenExternalLinks(True)
        lbl.setTextFormat(Qt.TextFormat.RichText if rico else Qt.TextFormat.PlainText)
        lbl.setFont(QFont(FONT_BODY, 11))
        lbl.setStyleSheet(f"color:{color_texto};background:transparent;border:none;")
        lbl.setMaximumWidth(560)
        return lbl

    def _pintar(self, texto, color_texto=None, streaming=False):
        color_texto = color_texto or COLORS["text"]
        self._limpiar()

        if streaming or not self.markdown or not markdown_qt.tiene_formato(texto):
            self.contenido.addWidget(self._etiqueta(texto, color_texto, rico=False))
            return

        for tipo, contenido, lenguaje in markdown_qt.dividir_bloques(texto):
            if tipo == "codigo":
                self.contenido.addWidget(BloqueCodigo(contenido, lenguaje))
            else:
                html = markdown_qt.a_html(
                    contenido, color_texto=color_texto,
                    color_codigo=COLORS["surface3"], color_enlace=COLORS["accent"],
                    color_tenue=COLORS["text_muted"],
                )
                if html:
                    self.contenido.addWidget(self._etiqueta(html, color_texto, rico=True))

    def update_text(self, text, streaming: bool = False):
        self.texto = text
        color = "#FFFFFF" if self.is_user else COLORS["text"]
        self._pintar(text, color_texto=color, streaming=streaming)

    def set_pie(self, texto: str):
        """Añade info al pie de la burbuja (hora + tokens/costo)."""
        if hasattr(self, "pie"):
            self.pie.setText(texto)

    def _copiar_todo(self):
        QApplication.clipboard().setText(self.texto)
        self.btn_copiar_todo.setIcon(icon("check", COLORS["success"], 13))
        QTimer.singleShot(
            1400,
            lambda: self.btn_copiar_todo.setIcon(icon("copy", COLORS["text_dim"], 13)),
        )


class TypingIndicator(QFrame):
    def __init__(self, provider_id="openrouter", parent=None):
        super().__init__(parent); meta = PROVIDER_META.get(provider_id, PROVIDER_META["openrouter"])
        layout = QHBoxLayout(self); layout.setContentsMargins(12, 4, 12, 4); layout.setSpacing(10)
        avatar = QLabel(meta["icon"]); avatar.setFixedSize(36,36); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFont(QFont("Segoe UI Emoji", 15))
        avatar.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {meta['dark']},stop:1 {meta['color']}44);border-radius:2px;border:2px solid {meta['color']}88;")
        layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop); dots_frame = QFrame()
        dots_frame.setStyleSheet(f"QFrame{{background:{COLORS['bot_bubble']};border-radius:3px;border:1px solid {COLORS['border']};border-left:3px solid {meta['color']};}}")
        dl = QHBoxLayout(dots_frame); dl.setContentsMargins(16,12,16,12); dl.setSpacing(6); self.dots = []
        for _ in range(3):
            dot = QLabel("●"); dot.setFont(QFont("Segoe UI", 9)); dot.setStyleSheet(f"color:{COLORS['text_muted']};background:transparent;")
            dl.addWidget(dot); self.dots.append(dot)
        layout.addWidget(dots_frame); layout.addStretch()
        self._dot_idx = 0; self._timer = QTimer(self); self._timer.timeout.connect(self._animate); self._timer.start(300)

    def _animate(self):
        c = COLORS["accent"]
        for i, dot in enumerate(self.dots): dot.setStyleSheet(f"color:{''+c if i==self._dot_idx else COLORS['text_dim']};background:transparent;")
        self._dot_idx = (self._dot_idx + 1) % 3

    def stop(self): self._timer.stop()
