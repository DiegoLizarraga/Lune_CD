"""
ui/ventana_reloj.py — Ventana de pantalla completa con reloj y carita (Qt puro, sin GPU).

La usan la pantalla grande, el salvapantallas y la alarma cuando no hay una
asistente 3D o animada a la vista (decisión D2 del plan de los cortes 5 y 6):
con sprites, con la asistente guardada, en la nativa sin VRM o sin QtWebEngine.
Es barata: un QWidget que se pinta con QPainter, una carita PNG de lune_face/
(nada de QVideoWidget) y un QTimer de 1 s para la hora solo mientras se ve.

    v = VentanaReloj()
    v.mostrar("salvapantallas", pantalla=screen, fondo_oscuro=True, reloj=True)
    v.set_alarma("sacar la pizza")        # burbuja #FF4826 a los 3 s, 35 c/s, Apagar/Posponer
    v.ocultar(500)                         # fundido con windowOpacity

Modos: "salvapantallas" (reloj grande y la carita dormida), "grande" (carita
grande y reloj pequeño) y "alarma" (carita, reloj y la burbuja de la alarma).
Ventana sin marco, siempre encima, de herramienta y que no roba el foco
(WindowDoesNotAcceptFocus + WA_ShowWithoutActivating): no quita el teclado al
juego ni a la app que estaba delante.

Señales: `apagar` y `posponer` (botones de la alarma) y `cerrar_pedido` (un clic
izquierdo fuera de los botones). Quien la usa decide qué hacer con el clic
(ui/pantalla_grande_qt.ControlPantallaGrande).
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtCore import QPropertyAnimation, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

MODOS = ("salvapantallas", "grande", "alarma")
RETRASO_ALARMA_MS = 3000            # Mate-Engine: la burbuja sale a los 3 s
LETRAS_POR_S = 35                   # y se escribe a 35 caracteres por segundo
FADE_MS = 500
COLOR_ALARMA = "#FF4826"
ANCHO_BURBUJA = 600

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")

# Carita por modo (estados de ui/lune_face.FACE_FILES).
CARA_POR_MODO = {"salvapantallas": "sleeping", "grande": "happy", "alarma": "normal"}
_ALIAS_CARA = {"dormida": "sleeping", "normal": "normal", "feliz": "happy"}


def _colores() -> dict:
    try:
        from ui.theme import COLORS
        return COLORS
    except Exception:
        return {"accent": "#00E5FF", "text": "#EAF1FF", "text_muted": "#97A6C4"}


def cargar_cara(estado: str) -> Optional[QPixmap]:
    """PNG de la carita para `estado` (el pack activo de lune_face o lune_face/).
    Un estado de vídeo usa su imagen fija. None si no hay imagen."""
    try:
        from ui import lune_face as lf
    except Exception:
        return None
    try:
        ruta, tipo = lf.get_face_info(estado)
        if tipo != "image":
            alt = lf.FACE_FALLBACK_IMAGE.get(estado)
            ruta = str(lf._pack_path(alt) or (lf.FACE_DIR / alt)) if alt else None
        if not ruta or not Path(ruta).is_file():
            return None
        pm = QPixmap(str(ruta))
        return None if pm.isNull() else pm
    except Exception:
        return None


def texto_fecha(ahora: datetime) -> str:
    """«viernes, 26 de septiembre»."""
    return f"{DIAS[ahora.weekday()]}, {ahora.day} de {MESES[ahora.month - 1]}"


class VentanaReloj(QWidget):
    """Fondo oscuro, reloj y carita a pantalla completa (ver el docstring del módulo)."""

    apagar = pyqtSignal()
    posponer = pyqtSignal()
    cerrar_pedido = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *,
                 hora: Callable[[], datetime] = datetime.now,
                 cargar: Callable[[str], Optional[QPixmap]] = cargar_cara,
                 reloj: Callable[[], float] = time.monotonic):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("Lune")
        self._hora = hora
        self._cargar = cargar
        self._reloj = reloj
        self.modo = ""
        self.fondo_oscuro = True
        self.con_reloj = True
        self.cara = ""
        self._pix: Optional[QPixmap] = None
        self._cache_cara = {}
        self._c = _colores()

        # Alarma
        self.alarma_texto: Optional[str] = None
        self.alarma_visible = ""                 # lo ya «escrito» de la burbuja
        self._apagar_desde = 0.0

        self._timer_hora = QTimer(self)
        self._timer_hora.setInterval(1000)
        self._timer_hora.timeout.connect(self._tic_hora)
        self._timer_retraso = QTimer(self)
        self._timer_retraso.setSingleShot(True)
        self._timer_retraso.timeout.connect(self._empezar_a_escribir)
        self._timer_letras = QTimer(self)
        self._timer_letras.setInterval(max(1, round(1000 / LETRAS_POR_S)))
        self._timer_letras.timeout.connect(self._siguiente_letra)
        self._timer_bloqueo = QTimer(self)
        self._timer_bloqueo.setInterval(250)
        self._timer_bloqueo.timeout.connect(self._pintar_boton_apagar)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(self._fin_fundido)
        self._ocultando = False

        self._botones = QWidget(self)
        fila = QHBoxLayout(self._botones)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(14)
        self.btn_apagar = self._boton("APAGAR", principal=True)
        self.btn_apagar.clicked.connect(self._pulsar_apagar)
        self.btn_posponer = self._boton("POSPONER")
        self.btn_posponer.clicked.connect(self._pulsar_posponer)
        fila.addWidget(self.btn_apagar)
        fila.addWidget(self.btn_posponer)
        self._botones.hide()

    # ── API ──────────────────────────────────────────────────────────────────────
    def mostrar(self, modo: str, *, pantalla: Any = None, fondo_oscuro: bool = True,
                reloj: bool = True, cara: Optional[str] = None) -> None:
        """Enseña la ventana en `modo` sobre la pantalla `pantalla` (QScreen; la
        principal si no se da). Si ya se veía, cambia de modo sin parpadear."""
        self.modo = modo if modo in MODOS else "grande"
        self.fondo_oscuro = bool(fondo_oscuro)
        self.con_reloj = bool(reloj)
        estado = _ALIAS_CARA.get(str(cara or ""), str(cara or "")) or CARA_POR_MODO[self.modo]
        self.cara = estado
        if estado not in self._cache_cara:
            try:
                self._cache_cara[estado] = self._cargar(estado)
            except Exception:
                self._cache_cara[estado] = None
        self._pix = self._cache_cara[estado]
        if self.modo != "alarma" and self.alarma_texto is not None:
            self.set_alarma(None)
        scr = pantalla or QGuiApplication.primaryScreen()
        if scr is not None:
            try:
                self.setGeometry(scr.geometry())
            except Exception:
                pass
        self._timer_hora.start()
        visible = self.isVisible() and not self._ocultando
        self._ocultando = False
        self._anim.stop()
        if not visible:
            self.setWindowOpacity(0.0)
            self.show()
            self._fundido(1.0, FADE_MS)
        else:
            self.setWindowOpacity(1.0)
        self._colocar_botones()
        self.update()

    def set_alarma(self, texto: Optional[str], *, bloqueo_ms: int = 0,
                   retraso_ms: int = RETRASO_ALARMA_MS) -> None:
        """Burbuja de la alarma: aparece a los `retraso_ms` y se escribe a 35 c/s,
        con Apagar y Posponer (los dos desactivados durante `bloqueo_ms` desde ahora,
        como la tarjeta nativa: durante el bloqueo la alarma no se puede posponer).
        None la quita."""
        self._timer_retraso.stop()
        self._timer_letras.stop()
        self._timer_bloqueo.stop()
        if texto is None:
            self.alarma_texto = None
            self.alarma_visible = ""
            self._botones.hide()
            self.update()
            return
        self.alarma_texto = str(texto) or "⏰"
        self.alarma_visible = ""
        self._apagar_desde = self._reloj() + max(0, int(bloqueo_ms)) / 1000.0
        self._botones.hide()
        if retraso_ms > 0:
            self._timer_retraso.start(int(retraso_ms))
        else:
            self._empezar_a_escribir()
        self.update()

    def ocultar(self, ms: int = FADE_MS) -> None:
        """Fundido de `ms` y se esconde (0 = ya)."""
        self._timer_hora.stop()
        self.set_alarma(None)
        if ms <= 0 or not self.isVisible():
            self._anim.stop()
            self._ocultando = False
            self.hide()
            self.setWindowOpacity(1.0)
            return
        self._ocultando = True
        self._fundido(0.0, ms)

    @property
    def ocultandose(self) -> bool:
        return self._ocultando

    # ── Fundido ──────────────────────────────────────────────────────────────────
    def _fundido(self, hasta: float, ms: int) -> None:
        self._anim.stop()
        self._anim.setDuration(max(1, int(ms)))
        self._anim.setStartValue(float(self.windowOpacity()))
        self._anim.setEndValue(float(hasta))
        self._anim.start()

    def _fin_fundido(self) -> None:
        if self._ocultando:
            self._ocultando = False
            self.hide()
            self.setWindowOpacity(1.0)

    # ── Alarma ───────────────────────────────────────────────────────────────────
    def _empezar_a_escribir(self) -> None:
        if self.alarma_texto is None:
            return
        self.alarma_visible = ""
        self._botones.show()
        self._colocar_botones()
        self._pintar_boton_apagar()
        if self._reloj() < self._apagar_desde:
            self._timer_bloqueo.start()
        self._timer_letras.start()
        self._siguiente_letra()

    def _siguiente_letra(self) -> None:
        t = self.alarma_texto
        if t is None or len(self.alarma_visible) >= len(t):
            self._timer_letras.stop()
            return
        self.alarma_visible = t[:len(self.alarma_visible) + 1]
        if len(self.alarma_visible) >= len(t):
            self._timer_letras.stop()
        self.update()

    def _pintar_boton_apagar(self) -> None:
        falta = self._apagar_desde - self._reloj()
        if falta > 0:
            self.btn_apagar.setEnabled(False)
            self.btn_posponer.setEnabled(False)
            self.btn_apagar.setText(f"APAGAR ({math.ceil(falta)})")
        else:
            self._timer_bloqueo.stop()
            self.btn_apagar.setEnabled(True)
            self.btn_posponer.setEnabled(True)
            self.btn_apagar.setText("APAGAR")

    def _pulsar_apagar(self) -> None:
        if self._reloj() >= self._apagar_desde:
            self.apagar.emit()

    def _pulsar_posponer(self) -> None:
        if self._reloj() >= self._apagar_desde:
            self.posponer.emit()

    # ── Eventos ──────────────────────────────────────────────────────────────────
    def _tic_hora(self) -> None:
        self.update()

    def mousePressEvent(self, ev) -> None:                              # noqa: N802 (Qt)
        if ev.button() == Qt.MouseButton.LeftButton:
            self.cerrar_pedido.emit()
        ev.accept()

    def resizeEvent(self, ev) -> None:                                  # noqa: N802 (Qt)
        super().resizeEvent(ev)
        self._colocar_botones()

    def hideEvent(self, ev) -> None:                                    # noqa: N802 (Qt)
        self._timer_hora.stop()
        super().hideEvent(ev)

    # ── Dibujo ───────────────────────────────────────────────────────────────────
    def _boton(self, texto: str, principal: bool = False) -> QPushButton:
        b = QPushButton(texto)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        b.setFixedHeight(40)
        b.setMinimumWidth(150)
        fondo = COLOR_ALARMA if principal else "rgba(255,255,255,0.08)"
        b.setStyleSheet(
            f"QPushButton{{background:{fondo};color:#FFFFFF;border:2px solid {COLOR_ALARMA};"
            f"border-radius:8px;padding:0 18px;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:#FF6A4D;}}"
            f"QPushButton:disabled{{background:rgba(255,72,38,0.35);color:rgba(255,255,255,0.6);}}")
        return b

    def _geometria_burbuja(self) -> QRect:
        w, h = self.width(), self.height()
        ancho = int(min(ANCHO_BURBUJA, w * 0.92))
        alto = max(64, int(h * 0.12))
        y = int(h * 0.64)
        return QRect((w - ancho) // 2, y, ancho, alto)

    def _colocar_botones(self) -> None:
        b = self._geometria_burbuja()
        self._botones.adjustSize()
        bw, bh = self._botones.sizeHint().width(), self._botones.sizeHint().height()
        self._botones.setGeometry((self.width() - bw) // 2, b.bottom() + 18, bw, bh)

    def paintEvent(self, ev) -> None:                                   # noqa: N802 (Qt)
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            w, h = self.width(), self.height()
            # Fondo: casi negro, o casi transparente (alfa 1: que el clic no la atraviese).
            p.fillRect(self.rect(), QColor(4, 6, 12, 232) if self.fondo_oscuro else QColor(0, 0, 0, 1))
            modo = self.modo or "grande"
            tam_cara = {"grande": 0.46, "salvapantallas": 0.20, "alarma": 0.26}[modo]
            y_cara = {"grande": 0.12, "salvapantallas": 0.12, "alarma": 0.08}[modo]
            lado = int(h * tam_cara)
            caja = QRect((w - lado) // 2, int(h * y_cara), lado, lado)
            if self._pix is not None and not self._pix.isNull():
                pm = self._pix.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                p.setOpacity(0.55 if modo == "salvapantallas" else 1.0)
                p.drawPixmap(caja.x() + (lado - pm.width()) // 2, caja.y() + (lado - pm.height()) // 2, pm)
                p.setOpacity(1.0)
            else:
                self._pintar_carita(p, caja, dormida=(modo == "salvapantallas"))
            if modo == "salvapantallas":
                p.setPen(QColor(self._c.get("text_muted", "#97A6C4")))
                p.setFont(QFont("Segoe UI", max(10, int(h * 0.03)), QFont.Weight.Bold))
                p.drawText(QRect(caja.right() - lado // 6, caja.y() - lado // 8, lado, lado // 3),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, "z z Z")
            y = caja.bottom() + int(h * 0.04)
            if self.con_reloj:
                ahora = self._hora()
                grande = modo == "salvapantallas"
                tam = max(18, int(h * (0.15 if grande else 0.075)))
                p.setPen(QColor(self._c.get("accent", "#00E5FF")))
                p.setFont(QFont("Segoe UI", tam, QFont.Weight.Light))
                alto_hora = int(tam * 1.5)
                p.drawText(QRect(0, y, w, alto_hora), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                           ahora.strftime("%H:%M"))
                y += alto_hora
                p.setPen(QColor(self._c.get("text_muted", "#97A6C4")))
                p.setFont(QFont("Segoe UI", max(10, int(h * 0.022))))
                p.drawText(QRect(0, y, w, int(h * 0.05)), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                           texto_fecha(ahora))
            if modo == "grande":
                p.setPen(QColor(255, 255, 255, 90))
                p.setFont(QFont("Segoe UI", max(9, int(h * 0.016))))
                p.drawText(QRect(0, h - int(h * 0.07), w, int(h * 0.05)), Qt.AlignmentFlag.AlignHCenter,
                           "Un clic para salir")
            if self.alarma_texto is not None and (self.alarma_visible or self._botones.isVisible()):
                self._pintar_burbuja(p)
        finally:
            p.end()

    def _pintar_burbuja(self, p: QPainter) -> None:
        r = self._geometria_burbuja()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COLOR_ALARMA))
        p.drawRoundedRect(QRectF(r), 14, 14)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        p.drawText(r.adjusted(18, 10, -18, -10),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.alarma_visible)

    def _pintar_carita(self, p: QPainter, caja: QRect, dormida: bool) -> None:
        """Sin PNG: una carita dibujada (círculo, ojos y boca)."""
        acento = QColor(self._c.get("accent", "#00E5FF"))
        p.setPen(Qt.PenStyle.NoPen)
        fondo = QColor(acento)
        fondo.setAlpha(60 if dormida else 110)
        p.setBrush(fondo)
        p.drawEllipse(caja)
        pen = QPen(QColor(255, 255, 255, 200 if not dormida else 120), max(2, caja.width() // 30))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy, r = caja.center().x(), caja.center().y(), caja.width() // 2
        ojo = r // 3
        for dx in (-ojo, ojo):
            if dormida:
                p.drawLine(cx + dx - r // 8, cy - r // 6, cx + dx + r // 8, cy - r // 6)
            else:
                p.drawEllipse(cx + dx - r // 16, cy - r // 5, r // 8, r // 8)
        p.drawArc(QRect(cx - r // 4, cy, r // 2, r // 4), 200 * 16, 140 * 16)


__all__ = ("VentanaReloj", "MODOS", "cargar_cara", "texto_fecha", "RETRASO_ALARMA_MS",
           "LETRAS_POR_S", "COLOR_ALARMA")
