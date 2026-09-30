"""
ui/aprobacion_qt.py — «¿Lo hago?»: aprobación de una acción del modelo junto a
la asistente, cuando la ventana principal no está a la vista.

PARA QUÉ SIRVE
--------------
Las herramientas con riesgo (lanzar una app, una orden de Minecraft, mandar una
captura a la nube…) necesitan que un HUMANO diga que sí, y la pregunta tiene
que verse. Con la ventana principal delante la hace el modal web
(`AprobacionModal`); en la nativa, un QMessageBox; en patata, la consola
(`consola.reclamar`). Pero si solo está la asistente o Lune vive en la bandeja,
el modal web no se ve y todo caducaría. `DialogoAprobacion` es esa pregunta
en pequeño: sin bordes, siempre encima, junto a la asistente (o en la esquina de
la pantalla), con la herramienta, un resumen y los argumentos.

Reglas (crítica d, «aprobaciones sin interfaz visible»):
- «Sí, hazlo» / «No». Sin respuesta en `SEGUNDOS` (60 s) = rechazada: cuenta
  atrás visible y `resuelto(False)` al llegar a 0.
- `resuelto(bool)` se emite UNA sola vez. Esc, Alt+F4 o cerrar = No.
  `descartar()` la cierra sin emitir (se resolvió por otro lado, p. ej. en el
  modal web o porque el Ejecutor canceló el turno).
- Contra el «sí» por accidente: el foco empieza en «No» (un Espacio o Enter
  que ibas a mandar a otra ventana no aprueba nada) y «Sí, hazlo» está
  desactivado los primeros `ARMADO_MS` tras mostrarse (un clic que iba a otra
  cosa no cae en él).
- Todo lo que viene del modelo (herramienta, resumen, argumentos) se pinta como
  TEXTO PLANO, sin caracteres de control ni de formato (bidi, ancho cero, que
  podrían disfrazar una ruta o una URL) y recortado (`formatear_args`).
- Acepta el foco al mostrarse (activateWindow), pero NO fuerza el primer plano
  con SetForegroundWindow: la pregunta no nace de un clic tuyo y no debe
  quitarle el teclado a un juego. Si Windows no la activa, se ve encima igual.

Uso (integración):

    dlg = DialogoAprobacion("lanzar_app", "Abrir el Bloc de notas",
                            {"app": "notepad"}, riesgo="ESCRITURA")
    dlg.resuelto.connect(lambda ok: ejecutor.responder(id_, ok))
    dlg.mostrar_junto_a(asistente.frameGeometry() if asistente else None)
"""
from __future__ import annotations

import json
import math
import time
import unicodedata
from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from ui.entrada_chat import Rect, pantalla_disponible, posicion_junto_a, rgba
from ui.theme import COLORS, FONT_BODY, FONT_DISPLAY, FONT_MONO

SEGUNDOS = 60
ARMADO_MS = 700
ANCHO = 330
TICK_MS = 250

MAX_HERRAMIENTA = 60
MAX_RESUMEN = 300
MAX_VALOR = 160
MAX_ARGS = 700
MAX_LINEAS_ARGS = 12

TEXTO_SI = "Sí, hazlo"
TEXTO_NO = "No"
SALTO_VISIBLE = " ⏎ "

# Color de la etiqueta de riesgo según la palabra que traiga.
_COLOR_RIESGO = (
    (("PELIGR", "ALTO", "SISTEMA"), "error"),
    (("ESCRIT", "RED", "RED_", "EJEC"), "yellow"),
    (("LECTUR",), "accent"),
)


# ── Texto seguro ──────────────────────────────────────────────────────────────

def limpiar(texto: Any, maximo: int) -> str:
    """Una línea visible: sin control ni formato (bidi, ancho cero); saltos → ⏎; recortada con «…»."""
    t = "" if texto is None else str(texto)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    partes = []
    for ch in t:
        if ch == "\n" or unicodedata.category(ch) in ("Zl", "Zp"):
            partes.append(SALTO_VISIBLE)
        elif ch == "\t":
            partes.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co"):
            continue
        else:
            partes.append(ch)
    t = "".join(partes).strip()
    if len(t) > maximo:
        t = t[:max(0, maximo - 1)].rstrip() + "…"
    return t


def _json(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(v)


def formatear_args(args: Any, max_valor: int = MAX_VALOR, max_total: int = MAX_ARGS) -> str:
    """Argumentos de la herramienta como «clave: valor», una línea por clave.

    Los textos van tal cual (sin comillas), el resto en JSON. Cada valor se
    limpia y recorta a `max_valor`; como mucho MAX_LINEAS_ARGS claves y
    `max_total` caracteres en total.
    """
    if args is None or args == {} or args == []:
        return ""
    if not isinstance(args, dict):
        return limpiar(_json(args), max_total)
    lineas = []
    claves = list(args.items())
    for k, v in claves[:MAX_LINEAS_ARGS]:
        valor = v if isinstance(v, str) else _json(v)
        lineas.append(f"{limpiar(k, 40)}: {limpiar(valor, max_valor)}")
    if len(claves) > MAX_LINEAS_ARGS:
        lineas.append(f"… ({len(claves) - MAX_LINEAS_ARGS} más)")
    texto = "\n".join(lineas)
    if len(texto) > max_total:
        texto = texto[:max(0, max_total - 1)].rstrip() + "…"
    return texto


def color_riesgo(riesgo: str) -> str:
    r = (riesgo or "").upper()
    for claves, color in _COLOR_RIESGO:
        if any(c in r for c in claves):
            return COLORS[color]
    return COLORS["text_muted"]


def texto_cuenta(segundos: int) -> str:
    return f"Si no contestas, en {max(0, int(segundos))} s será que no"


# ── Ventana ───────────────────────────────────────────────────────────────────

class DialogoAprobacion(QWidget):
    """Pregunta «¿Lo hago?» flotante. `resuelto(bool)` una sola vez."""

    resuelto = pyqtSignal(bool)

    def __init__(self, herramienta: str, resumen: str = "", args: Any = None, *,
                 riesgo: str = "", segundos: int = SEGUNDOS, armado_ms: int = ARMADO_MS,
                 id_aprobacion: str = "", autodestruir: bool = True,
                 reloj: Callable[[], float] = time.monotonic,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.id_aprobacion = id_aprobacion
        self.herramienta = limpiar(herramienta, MAX_HERRAMIENTA) or "herramienta"
        self._reloj = reloj
        self._limite = reloj() + max(1, int(segundos))
        self._armado_ms = max(0, int(armado_ms))
        self._autodestruir = autodestruir
        self._resultado: Optional[bool] = None
        self._cerrada = False
        self._ultimo_mostrado = -1

        # Acepta foco (sin WindowDoesNotAcceptFocus); Tool: sin botón en la barra.
        self.setWindowFlags(Qt.WindowType.Tool
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle("Lune · ¿lo hago?")
        self.setFixedWidth(ANCHO)

        marco = QFrame(self)
        marco.setObjectName("marco")

        def etiqueta(texto: str, nombre: str) -> QLabel:
            e = QLabel(texto, marco)
            e.setObjectName(nombre)
            e.setTextFormat(Qt.TextFormat.PlainText)   # nada de HTML del modelo
            e.setWordWrap(True)
            e.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            return e

        self.titulo = etiqueta("¿LO HAGO?", "titulo")
        self.etiqueta_riesgo = etiqueta(limpiar(riesgo, 20).upper(), "riesgo")
        self.etiqueta_riesgo.setWordWrap(False)
        self.etiqueta_riesgo.setVisible(bool(self.etiqueta_riesgo.text()))
        self.etiqueta_herramienta = etiqueta(self.herramienta, "herramienta")
        self.etiqueta_resumen = etiqueta(limpiar(resumen, MAX_RESUMEN), "resumen")
        self.etiqueta_resumen.setVisible(bool(self.etiqueta_resumen.text()))
        self.etiqueta_args = etiqueta(formatear_args(args), "args")
        self.etiqueta_args.setVisible(bool(self.etiqueta_args.text()))
        self.etiqueta_cuenta = etiqueta("", "cuenta")

        self.boton_no = QPushButton(TEXTO_NO, marco)
        self.boton_no.setObjectName("no")
        self.boton_si = QPushButton(TEXTO_SI, marco)
        self.boton_si.setObjectName("si")
        for b in (self.boton_no, self.boton_si):
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_si.setEnabled(self._armado_ms == 0)
        self.boton_no.clicked.connect(lambda: self.resolver(False))
        self.boton_si.clicked.connect(lambda: self.resolver(True))

        cabecera = QHBoxLayout()
        cabecera.setSpacing(6)
        cabecera.addWidget(self.titulo, 1)
        cabecera.addWidget(self.etiqueta_riesgo, 0, Qt.AlignmentFlag.AlignRight)
        botones = QHBoxLayout()
        botones.setSpacing(8)
        botones.addStretch(1)
        botones.addWidget(self.boton_no)
        botones.addWidget(self.boton_si)

        interior = QVBoxLayout(marco)
        interior.setContentsMargins(14, 12, 14, 12)
        interior.setSpacing(6)
        interior.addLayout(cabecera)
        interior.addWidget(self.etiqueta_herramienta)
        interior.addWidget(self.etiqueta_resumen)
        interior.addWidget(self.etiqueta_args)
        interior.addWidget(self.etiqueta_cuenta)
        interior.addLayout(botones)
        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(0, 0, 0, 0)
        fuera.addWidget(marco)

        self._aplicar_estilo(color_riesgo(riesgo))
        self.setTabOrder(self.boton_no, self.boton_si)

        self._t_cuenta = QTimer(self)
        self._t_cuenta.setInterval(TICK_MS)
        self._t_cuenta.timeout.connect(self._tick)
        self._t_cuenta.start()
        self._t_armado = QTimer(self)
        self._t_armado.setSingleShot(True)
        self._t_armado.timeout.connect(self._armar)
        self._tick()

    def _aplicar_estilo(self, color_tag: str):
        self.setStyleSheet(f"""
            QFrame#marco {{
                background: {rgba(COLORS['surface'], 0.98)};
                border: 2px solid {COLORS['yellow']};
                border-radius: 10px;
            }}
            QLabel {{ color: {COLORS['text']}; font-family: '{FONT_BODY}'; font-size: 12px; }}
            QLabel#titulo {{ color: {COLORS['yellow']}; font-family: '{FONT_DISPLAY}';
                             font-size: 13px; font-weight: 700; letter-spacing: 1px; }}
            QLabel#riesgo {{ color: {color_tag}; border: 1px solid {color_tag}; border-radius: 3px;
                             padding: 0 5px; font-family: '{FONT_MONO}'; font-size: 9px; }}
            QLabel#herramienta {{ color: {COLORS['accent']}; font-family: '{FONT_MONO}'; font-size: 12px; }}
            QLabel#args {{ color: {COLORS['text_muted']}; font-family: '{FONT_MONO}'; font-size: 11px;
                           background: {rgba(COLORS['bg'], 0.7)}; border: 1px solid {COLORS['border']};
                           border-radius: 4px; padding: 4px 6px; }}
            QLabel#cuenta {{ color: {COLORS['text_dim']}; font-family: '{FONT_MONO}'; font-size: 10px; }}
            QPushButton {{ font-family: '{FONT_BODY}'; font-size: 12px; font-weight: 600;
                           border-radius: 4px; padding: 5px 14px; }}
            QPushButton#no {{ color: {COLORS['text']}; background: {COLORS['surface3']};
                              border: 1px solid {COLORS['border2']}; }}
            QPushButton#no:focus {{ border: 1px solid {COLORS['accent']}; }}
            QPushButton#si {{ color: {COLORS['bg']}; background: {COLORS['accent']};
                              border: 1px solid {COLORS['accent']}; }}
            QPushButton#si:disabled {{ color: {COLORS['text_dim']}; background: {COLORS['surface2']};
                                       border: 1px solid {COLORS['border']}; }}
        """)

    # ── Estado ───────────────────────────────────────────────────────────────
    @property
    def resultado(self) -> Optional[bool]:
        """None mientras no se ha contestado."""
        return self._resultado

    def restante(self) -> int:
        """Segundos que quedan (redondeando hacia arriba)."""
        return max(0, math.ceil(self._limite - self._reloj()))

    def armada(self) -> bool:
        return self.boton_si.isEnabled()

    def _armar(self):
        if self._resultado is None and not self._cerrada:
            self.boton_si.setEnabled(True)

    def _tick(self):
        if self._resultado is not None or self._cerrada:
            return
        quedan = self.restante()
        if quedan <= 0:
            self.resolver(False)
            return
        if quedan != self._ultimo_mostrado:
            self._ultimo_mostrado = quedan
            self.etiqueta_cuenta.setText(texto_cuenta(quedan))

    # ── Mostrar ──────────────────────────────────────────────────────────────
    def mostrar_junto_a(self, rect: Optional[Rect] = None):
        """Al lado de la asistente (`rect` global de Qt) o, sin ella, en la esquina
        inferior derecha de la pantalla del cursor. Pide el foco para «No»."""
        if self._resultado is not None or self._cerrada:
            return
        self.adjustSize()
        tam = (self.width(), self.sizeHint().height())
        x, y = posicion_junto_a(rect, tam, pantalla_disponible(rect),
                                ("derecha", "izquierda", "arriba", "abajo"))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.boton_no.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def showEvent(self, e):
        super().showEvent(e)
        if not self.boton_si.isEnabled() and not self._t_armado.isActive() and self._resultado is None:
            self._t_armado.start(self._armado_ms)

    # ── Resolver ─────────────────────────────────────────────────────────────
    def resolver(self, ok: bool) -> bool:
        """Contesta. True si esta llamada fue la que resolvió (la señal sale una vez)."""
        if self._resultado is not None or self._cerrada:
            return False
        if ok and not self.boton_si.isEnabled():
            return False                      # «sí» antes de armarse: no cuenta
        self._resultado = bool(ok)
        self._parar()
        self.resuelto.emit(self._resultado)
        self._cerrar()
        return True

    def descartar(self):
        """Cierra sin emitir: la aprobación se resolvió por otro lado."""
        if self._cerrada:
            return
        self._parar()
        self._cerrar()

    def _parar(self):
        self._t_cuenta.stop()
        self._t_armado.stop()
        self.boton_si.setEnabled(False)
        self.boton_no.setEnabled(False)

    def _cerrar(self):
        self._cerrada = True
        self.hide()
        if self._autodestruir:
            self.deleteLater()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.resolver(False)
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if self._resultado is None and not self._cerrada:
            self._resultado = False
            self._parar()
            self._cerrada = True
            self.resuelto.emit(False)
            if self._autodestruir:
                self.deleteLater()
        e.accept()
