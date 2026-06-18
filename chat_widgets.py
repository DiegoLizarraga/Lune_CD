"""
chat_widgets.py — Widgets de la conversación: pestañas de proveedor,
burbujas de mensaje e indicador de "escribiendo…".
"""
from datetime import datetime

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from theme import COLORS, PROVIDER_META, FONT_DISPLAY, FONT_BODY, FONT_MONO
from icons import icon_pixmap
from effects import apply_glow, clear_glow


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
        layout.addWidget(self.icon_lbl); layout.addLayout(text_col, 1)
        self._apply_style(False)

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


class MessageBubble(QFrame):
    def __init__(self, text, is_user, provider_id="openrouter", parent=None):
        super().__init__(parent); self.is_user = is_user; self.provider_id = provider_id; self._build(text)

    def _build(self, text):
        outer = QHBoxLayout(self); outer.setContentsMargins(12, 4, 12, 4); outer.setSpacing(10)
        meta = PROVIDER_META.get(self.provider_id, PROVIDER_META["openrouter"]); color = meta["color"]

        if self.is_user:
            outer.addStretch(); bubble = QFrame()
            bubble.setStyleSheet(f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {COLORS['blue_dark']},stop:1 {COLORS['user_bubble']});border-radius:3px;border:2px solid {COLORS['blue']};}}")
            bl = QVBoxLayout(bubble); bl.setContentsMargins(15,11,15,11); bl.setSpacing(4)
            self.text_lbl = QLabel(text); self.text_lbl.setWordWrap(True); self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont(FONT_BODY, 11)); self.text_lbl.setStyleSheet(f"color:#FFFFFF;background:transparent;"); self.text_lbl.setMaximumWidth(520); bl.addWidget(self.text_lbl)
            ts = QLabel(datetime.now().strftime("%H:%M")); ts.setFont(QFont(FONT_MONO, 8)); ts.setStyleSheet(f"color:#C4D0E6;background:transparent;"); ts.setAlignment(Qt.AlignmentFlag.AlignRight); bl.addWidget(ts)
            outer.addWidget(bubble)
        else:
            avatar = QLabel(meta["icon"]); avatar.setFixedSize(36, 36); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFont(QFont("Segoe UI Emoji", 15))
            avatar.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {meta['dark']},stop:1 {color}44);border-radius:2px;border:2px solid {color}88;")
            outer.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop); bubble = QFrame()
            bubble.setStyleSheet(f"QFrame{{background:{COLORS['bot_bubble']};border-radius:3px;border:1px solid {COLORS['border']};border-left:3px solid {color};}}")
            bl = QVBoxLayout(bubble); bl.setContentsMargins(15,11,15,11); bl.setSpacing(4)
            sender = QLabel(meta["label"]); sender.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold)); sender.setStyleSheet(f"color:{color};background:transparent;letter-spacing:1px;"); bl.addWidget(sender)
            self.text_lbl = QLabel(text); self.text_lbl.setWordWrap(True); self.text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.text_lbl.setFont(QFont(FONT_BODY, 11)); self.text_lbl.setStyleSheet(f"color:{COLORS['text']};background:transparent;"); self.text_lbl.setMaximumWidth(520); bl.addWidget(self.text_lbl)
            ts = QLabel(datetime.now().strftime("%H:%M")); ts.setFont(QFont(FONT_MONO, 8)); ts.setStyleSheet(f"color:{COLORS['text_dim']};background:transparent;"); bl.addWidget(ts)
            outer.addWidget(bubble); outer.addStretch()

    def update_text(self, text):
        self.text_lbl.setText(text)


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
