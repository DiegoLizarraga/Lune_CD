"""
ui/entrada_chat.py — Cajita para escribirle a Lune desde la asistente flotante
(el «AI Chat» de Mate-Engine, versión Lune).

PARA QUÉ SIRVE
--------------
La asistente (VRM, animada o sprites) es una ventana `WindowDoesNotAcceptFocus`:
nunca roba el foco a lo que estás usando, así que no puede recibir texto. Para
hablarle sin abrir la ventana principal, un doble clic (o la bandeja, o un
atajo) abre esta cajita anclada bajo la asistente. Lo que escribes sale por la
señal `enviado(str)`; la respuesta la pinta la burbuja de la asistente
(`burbujaTexto`/`burbujaFin`), no esta ventana.

`EntradaChat` es la ÚNICA ventana de Lune que acepta foco, y solo porque la abre
un clic tuyo: `Tool | Frameless | StaysOnTop` SIN `WindowDoesNotAcceptFocus`.
Al abrirse llama a `activateWindow()` (y en Windows a `SetForegroundWindow`, que
el sistema permite porque el proceso acaba de recibir ese clic) para que puedas
escribir enseguida.

Teclas (`manejar_tecla`, función pura para probarla sin ventana):
    Enter / Ctrl+Enter    envía (si hay texto; en vacío no hace nada)
    Shift+Enter           salto de línea
    Esc                   cierra (el borrador se conserva hasta la próxima vez)

Si pierde el foco (clic en otra ventana) se cierra sola, también conservando
el borrador. Tras enviar se cierra (`cerrar_al_enviar=True`).

Precalentar (opcional): con Ollama, el primer mensaje tras un rato tarda
porque el modelo se carga en la VRAM. `precalentar(url, modelo)` hace en un
hilo `POST {url}/api/generate {"model", "keep_alive": "30m"}` (sin prompt:
Ollama solo carga el modelo) mientras la cajita muestra «Despertando a Lune…».
No repite si ya lo hizo hace menos de `PRECALENTAR_VALIDO_S`.

Uso (integración en la asistente):

    self.entrada = EntradaChat()
    self.entrada.enviado.connect(self._chat_enviado)
    ...
    self.entrada.mostrar_junto_a(self.frameGeometry())
    self.entrada.precalentar(datos.ollama_url(), modelo)

Coordenadas: `mostrar_junto_a` recibe el rectángulo GLOBAL de Qt (lógico) de
la asistente; se coloca debajo, o encima si no cabe, siempre dentro de la
pantalla disponible de ese punto. Al menos `ANCHO_MIN` (280 px) de ancho.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.request
from typing import Callable, Optional, Sequence, Tuple, Union

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCursor, QGuiApplication, QTextCursor
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                             QVBoxLayout, QWidget)

from ui.theme import COLORS, FONT_BODY, FONT_MONO

log = logging.getLogger("lune.entrada_chat")

ANCHO_MIN = 280
ANCHO_MAX = 460
LINEAS_MAX = 6
MAX_CARACTERES = 4000
MARGEN = 8

TEXTO_AYUDA = "Enter envía · Shift+Enter, otra línea · Esc cierra"
TEXTO_DESPERTANDO = "Despertando a Lune…"
TEXTO_NO_DESPIERTA = "Lune no responde (¿está encendido Ollama?)"
KEEP_ALIVE = "30m"
TIMEOUT_PRECALENTAR_S = 120
PRECALENTAR_VALIDO_S = 300

ENVIAR, SALTO, CERRAR = "enviar", "salto", "cerrar"

Rect = Union[QRect, Sequence[int]]


# ── Lógica pura ───────────────────────────────────────────────────────────────

def _valor(x) -> int:
    """Entero de una tecla o de unos modificadores (enum de PyQt6 o int)."""
    v = getattr(x, "value", x)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


_ESC = _valor(Qt.Key.Key_Escape)
_ENTER = frozenset({_valor(Qt.Key.Key_Return), _valor(Qt.Key.Key_Enter)})
_SHIFT = _valor(Qt.KeyboardModifier.ShiftModifier)
_ALT = _valor(Qt.KeyboardModifier.AltModifier)
_META = _valor(Qt.KeyboardModifier.MetaModifier)


def manejar_tecla(tecla, mods, texto: str) -> Optional[str]:
    """Qué hacer con una tecla de la cajita.

    'enviar' (Enter o Ctrl+Enter con texto), 'salto' (Shift+Enter), 'cerrar' (Esc)
    o None: la tecla no es nuestra. Enter en vacío o con Alt/Win da None (quien
    llama se la traga para que no meta un salto de línea). El Enter del teclado
    numérico (KeypadModifier) cuenta igual que el normal.
    """
    k = _valor(tecla)
    m = _valor(mods)
    if k == _ESC:
        return CERRAR
    if k in _ENTER:
        if m & _SHIFT:
            return SALTO
        if m & (_ALT | _META):
            return None
        return ENVIAR if (texto or "").strip() else None
    return None


def _como_tupla(r: Rect) -> Tuple[int, int, int, int]:
    if isinstance(r, QRect):
        return r.x(), r.y(), r.width(), r.height()
    x, y, w, h = r
    return int(x), int(y), int(w), int(h)


def posicion_junto_a(ancla: Optional[Rect], tam: Sequence[int], pantalla: Rect,
                     preferencias: Sequence[str] = ("abajo", "arriba"),
                     margen: int = MARGEN) -> Tuple[int, int]:
    """Esquina superior izquierda para una ventana de `tam` (ancho, alto) junto a `ancla`.

    Prueba los lados de `preferencias` ('abajo', 'arriba', 'derecha', 'izquierda')
    en orden y usa el primero que cabe en `pantalla`; si no cabe ninguno, el
    primero. Siempre acaba dentro de la pantalla. Sin ancla: esquina inferior
    derecha (como una notificación).
    """
    w, h = int(tam[0]), int(tam[1])
    px, py, pw, ph = _como_tupla(pantalla)
    if ancla is None:
        x, y = px + pw - w - 2 * margen, py + ph - h - 2 * margen
    else:
        ax, ay, aw, ah = _como_tupla(ancla)
        candidatos = {
            "abajo": (ax + (aw - w) // 2, ay + ah + margen),
            "arriba": (ax + (aw - w) // 2, ay - margen - h),
            "derecha": (ax + aw + margen, ay + (ah - h) // 2),
            "izquierda": (ax - margen - w, ay + (ah - h) // 2),
        }
        cabe = {
            "abajo": lambda x, y: y + h <= py + ph,
            "arriba": lambda x, y: y >= py,
            "derecha": lambda x, y: x + w <= px + pw,
            "izquierda": lambda x, y: x >= px,
        }
        prefs = [p for p in preferencias if p in candidatos] or ["abajo"]
        x, y = candidatos[prefs[0]]
        for lado in prefs:
            cx, cy = candidatos[lado]
            if cabe[lado](cx, cy):
                x, y = cx, cy
                break
    x = max(px, min(x, px + pw - w))
    y = max(py, min(y, py + ph - h))
    return int(x), int(y)


def pantalla_disponible(ancla: Optional[Rect] = None) -> QRect:
    """Área disponible (sin barra de tareas) de la pantalla del ancla o del cursor."""
    if ancla is not None:
        x, y, w, h = _como_tupla(ancla)
        punto = QRect(x, y, w, h).center()
    else:
        punto = QCursor.pos()
    pantalla = QGuiApplication.screenAt(punto) or QGuiApplication.primaryScreen()
    return pantalla.availableGeometry() if pantalla else QRect(0, 0, 1280, 720)


def rgba(hex_color: str, alfa: float) -> str:
    """'#0F1424' + 0.96 → 'rgba(15, 20, 36, 245)' para QSS."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {max(0, min(255, round(alfa * 255)))})"


def traer_al_frente(ventana: QWidget) -> None:
    """activateWindow() y, en Windows, SetForegroundWindow (permitido tras un clic del usuario)."""
    ventana.raise_()
    ventana.activateWindow()
    if sys.platform == "win32" and QGuiApplication.platformName() == "windows":
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(ventana.winId()))
        except Exception:  # noqa: BLE001 — si Windows lo niega, parpadea y ya
            pass


def _post_json(url: str, cuerpo: dict, timeout: float) -> int:
    """POST JSON sin proxies (Ollama es local o de la LAN). Devuelve el código HTTP."""
    datos = json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"Content-Type": "application/json"})
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with abridor.open(req, timeout=timeout) as r:
        r.read(64 * 1024)
        return int(getattr(r, "status", 200))


# ── Ventana ───────────────────────────────────────────────────────────────────

class EntradaChat(QWidget):
    """Cajita de texto flotante bajo la asistente. Señal `enviado(str)` con el texto."""

    enviado = pyqtSignal(str)
    cerrado = pyqtSignal()
    precalentado = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None, *,
                 cerrar_al_enviar: bool = True,
                 cerrar_al_perder_foco: bool = True,
                 placeholder: str = "Escríbele a Lune…",
                 poster: Optional[Callable[[str, dict, float], int]] = None,
                 reloj: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.cerrar_al_enviar = cerrar_al_enviar
        self.cerrar_al_perder_foco = cerrar_al_perder_foco
        self._poster = poster or _post_json
        self._reloj = reloj
        self._hilo_pre: Optional[threading.Thread] = None
        self._pre_ok: Tuple[Optional[tuple], float] = (None, 0.0)
        self._pre_clave: Optional[tuple] = None

        # Sin WindowDoesNotAcceptFocus: es la única ventana de Lune que recibe teclado.
        self.setWindowFlags(Qt.WindowType.Tool
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle("Lune · chat")
        self.setMinimumWidth(ANCHO_MIN)

        self.marco = QFrame(self)
        self.marco.setObjectName("marco")
        self.caja = QPlainTextEdit(self.marco)
        self.caja.setObjectName("caja")
        self.caja.setPlaceholderText(placeholder)
        self.caja.setTabChangesFocus(True)
        self.caja.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.caja.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.caja.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.caja.installEventFilter(self)
        self.caja.textChanged.connect(self._ajustar_alto)

        self.estado = QLabel("", self.marco)
        self.estado.setObjectName("estado")
        self.estado.setTextFormat(Qt.TextFormat.PlainText)
        self.estado.hide()
        self.ayuda = QLabel(TEXTO_AYUDA, self.marco)
        self.ayuda.setObjectName("ayuda")
        self.ayuda.setTextFormat(Qt.TextFormat.PlainText)

        pie = QHBoxLayout()
        pie.setContentsMargins(2, 0, 2, 0)
        pie.addWidget(self.estado)
        pie.addStretch(1)
        pie.addWidget(self.ayuda)

        interior = QVBoxLayout(self.marco)
        interior.setContentsMargins(10, 8, 10, 6)
        interior.setSpacing(4)
        interior.addWidget(self.caja)
        interior.addLayout(pie)

        fuera = QVBoxLayout(self)
        fuera.setContentsMargins(0, 0, 0, 0)
        fuera.addWidget(self.marco)

        self._t_estado = QTimer(self)
        self._t_estado.setSingleShot(True)
        self._t_estado.timeout.connect(self._ocultar_estado)
        self.precalentado.connect(self._on_precalentado)

        self._aplicar_estilo()
        self._ajustar_alto()

    # ── Estilo y tamaño ──────────────────────────────────────────────────────
    def _aplicar_estilo(self):
        self.setStyleSheet(f"""
            QFrame#marco {{
                background: {rgba(COLORS['surface'], 0.97)};
                border: 2px solid {COLORS['accent']};
                border-radius: 10px;
            }}
            QPlainTextEdit#caja {{
                background: transparent;
                color: {COLORS['text']};
                border: none;
                font-family: '{FONT_BODY}';
                font-size: 13px;
                selection-background-color: {COLORS['blue']};
            }}
            QLabel#ayuda {{ color: {COLORS['text_dim']}; font-family: '{FONT_MONO}'; font-size: 10px; }}
            QLabel#estado {{ color: {COLORS['yellow']}; font-family: '{FONT_MONO}'; font-size: 10px; }}
        """)

    def _lineas(self) -> int:
        doc = self.caja.document()
        try:
            visuales = int(doc.documentLayout().documentSize().height())
        except Exception:  # noqa: BLE001
            visuales = 0
        return max(1, min(LINEAS_MAX, max(doc.blockCount(), visuales)))

    def _ajustar_alto(self):
        fm = self.caja.fontMetrics()
        margen_doc = int(self.caja.document().documentMargin()) * 2
        alto = fm.lineSpacing() * self._lineas() + margen_doc + 2 * self.caja.frameWidth() + 2
        if self.caja.height() != alto:
            self.caja.setFixedHeight(alto)
            if self.isVisible():
                self.adjustSize()

    # ── Mostrar, activar, cerrar ─────────────────────────────────────────────
    def mostrar_junto_a(self, rect_global: Optional[Rect] = None, *, texto: Optional[str] = None):
        """Abre (o recoloca) la cajita junto a la asistente y le da el foco.

        `rect_global`: rectángulo global de Qt de la asistente (frameGeometry()) o
        (x, y, ancho, alto). Sin él, en la esquina inferior derecha de la pantalla
        del cursor. `texto` sustituye el borrador (p. ej. «/» desde un atajo).
        """
        if texto is not None:
            self.caja.setPlainText(texto[:MAX_CARACTERES])
            self.caja.moveCursor(QTextCursor.MoveOperation.End)
        ancho_ancla = _como_tupla(rect_global)[2] if rect_global is not None else ANCHO_MIN
        self.setFixedWidth(max(ANCHO_MIN, min(ANCHO_MAX, ancho_ancla)))
        self._ajustar_alto()
        self.adjustSize()
        tam = (self.width(), self.sizeHint().height())
        x, y = posicion_junto_a(rect_global, tam, pantalla_disponible(rect_global))
        self.move(x, y)
        self.show()
        self.activar()

    def activar(self):
        """Foco a la caja (llamar justo después del clic que la abre)."""
        traer_al_frente(self)
        self.caja.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def cerrar(self):
        """Oculta la cajita. El borrador se queda para la próxima vez."""
        if self.isVisible():
            self.hide()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.cerrado.emit()

    def changeEvent(self, e):
        super().changeEvent(e)
        if (e.type() == QEvent.Type.ActivationChange and self.cerrar_al_perder_foco
                and self.isVisible() and not self.isActiveWindow()):
            # Un instante de margen: al abrir un menú propio o recolocarla se
            # pierde y recupera la activación en el mismo ciclo.
            QTimer.singleShot(150, self._cerrar_si_inactiva)

    def _cerrar_si_inactiva(self):
        if self.isVisible() and not self.isActiveWindow():
            self.cerrar()

    # ── Teclas y envío ───────────────────────────────────────────────────────
    def eventFilter(self, obj, ev):
        if obj is self.caja and ev.type() == QEvent.Type.KeyPress:
            if self._tecla(ev.key(), ev.modifiers()):
                return True
        return super().eventFilter(obj, ev)

    def _tecla(self, tecla, mods) -> bool:
        """Aplica manejar_tecla. True si la tecla se consumió."""
        accion = manejar_tecla(tecla, mods, self.caja.toPlainText())
        if accion == ENVIAR:
            self.enviar()
            return True
        if accion == SALTO:
            self.caja.insertPlainText("\n")
            return True
        if accion == CERRAR:
            self.cerrar()
            return True
        return _valor(tecla) in _ENTER          # Enter en vacío o con Alt: nada

    def enviar(self) -> bool:
        """Emite `enviado` con el texto (sin espacios de los bordes) y vacía la caja."""
        texto = self.caja.toPlainText().strip()
        if not texto:
            return False
        texto = texto[:MAX_CARACTERES]
        self.caja.clear()
        self.enviado.emit(texto)
        if self.cerrar_al_enviar:
            self.cerrar()
        return True

    def texto(self) -> str:
        return self.caja.toPlainText()

    # ── Estado («Despertando a Lune…») ───────────────────────────────────────
    def mostrar_estado(self, texto: str, ms: int = 0):
        """Texto pequeño en el pie (sustituye a la ayuda). ms > 0: se quita solo."""
        self._t_estado.stop()
        self.estado.setText(texto)
        self.estado.show()
        self.ayuda.hide()
        if ms > 0:
            self._t_estado.start(int(ms))

    def _ocultar_estado(self):
        self._t_estado.stop()
        self.estado.hide()
        self.estado.setText("")
        self.ayuda.show()

    # ── Precalentar el modelo de Ollama ──────────────────────────────────────
    def precalentar(self, url: str, modelo: str, keep_alive: str = KEEP_ALIVE) -> bool:
        """Carga `modelo` en Ollama en un hilo. False si no hace falta o no se puede."""
        base = (url or "").strip().rstrip("/")
        modelo = (modelo or "").strip()
        if not modelo or not base.lower().startswith(("http://", "https://")):
            return False
        if self._hilo_pre is not None and self._hilo_pre.is_alive():
            return False
        clave = (base, modelo)
        ultima_clave, cuando = self._pre_ok
        if ultima_clave == clave and self._reloj() - cuando < PRECALENTAR_VALIDO_S:
            return False
        self._pre_clave = clave
        self.mostrar_estado(TEXTO_DESPERTANDO)
        cuerpo = {"model": modelo, "keep_alive": keep_alive, "stream": False}
        self._hilo_pre = threading.Thread(
            target=self._precalentar_hilo, args=(base + "/api/generate", cuerpo),
            name="lune-precalentar", daemon=True)
        self._hilo_pre.start()
        return True

    def _precalentar_hilo(self, url: str, cuerpo: dict):
        ok = False
        try:
            codigo = self._poster(url, cuerpo, TIMEOUT_PRECALENTAR_S)
            ok = codigo is None or 200 <= int(codigo) < 300
        except Exception as e:  # noqa: BLE001 — sin red, Ollama apagado, modelo que no existe…
            log.info("no se pudo precalentar %s: %s", cuerpo.get("model"), e)
        try:
            self.precalentado.emit(ok)          # llega en cola al hilo de Qt
        except RuntimeError:
            pass                                # la ventana ya no existe

    @pyqtSlot(bool)
    def _on_precalentado(self, ok: bool):
        if ok:
            self._pre_ok = (self._pre_clave, self._reloj())
            if self.estado.text() == TEXTO_DESPERTANDO:
                self._ocultar_estado()
        elif self.estado.text() == TEXTO_DESPERTANDO:
            self.mostrar_estado(TEXTO_NO_DESPIERTA, ms=5000)
