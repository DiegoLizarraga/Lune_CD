"""
ui/chat_asistente.py — Hablarle a Lune desde la asistente flotante (el «AI Chat» de
Mate-Engine): doble clic → cajita de texto; la respuesta sale en su burbuja.

Lo comparten las dos asistentes, la web (ui/companion.py: animada o VRM) y la de
sprites (ui/avatar_overlay.py), para que se comporten igual:

`DesambiguadorClic`
    Un clic limpio sobre la asistente ya hace algo (la animada comenta la
    pantalla, con captura y llamada a la IA). Para que el doble clic abra la
    cajita SIN disparar antes ese comentario, el clic simple se retrasa
    `QApplication.doubleClickInterval()` ms y se cancela si llega el segundo clic
    (crítica c.10). El temporizador se puede inyectar (tests).

`ChatAsistente`
    La cajita (ui/entrada_chat.EntradaChat) anclada bajo la asistente. Lo que
    escribes va a `dueno.on_chat(texto) -> bool`, que ponen quien lleva la app
    (main.py `_chat_desde_asistente`, ui/web_bridge.py `enviar_desde_asistente`) para
    que entre por el flujo normal del chat: mismo historial, misma memoria,
    mismas acciones con aprobación. La respuesta la pinta la asistente con
    `burbuja_texto(texto)` / `burbuja_fin(ms)`. Si `dueno.proveedor_chat()` dice
    'ollama', al abrir precalienta el modelo («Despertando a Lune…»).

`BurbujaQt`
    Burbuja de texto flotante hecha con Qt para la asistente de sprites (sin
    Chromium): encima de la asistente, sin foco, deja pasar los clics y el texto
    va SIEMPRE como texto plano (nada del modelo se interpreta como HTML).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

log = logging.getLogger("lune.chat_asistente")

INTERVALO_DOBLE_CLIC_MS = 400          # respaldo si Qt no lo sabe
AVISO_SIN_CHAT = "Para charlar conmigo, abre Lune (la ventana principal)."
AVISO_OCUPADA = "Espera, aún estoy con lo anterior…"


def intervalo_doble_clic() -> int:
    """ms que separan un clic de un doble clic (el del sistema)."""
    try:
        ms = int(QApplication.doubleClickInterval())
        if ms > 0:
            return ms
    except Exception:  # noqa: BLE001 — sin QApplication o API distinta
        pass
    try:
        ms = int(QGuiApplication.styleHints().mouseDoubleClickInterval())
        if ms > 0:
            return ms
    except Exception:  # noqa: BLE001
        pass
    return INTERVALO_DOBLE_CLIC_MS


def ms_lectura(texto: str) -> int:
    """Cuánto dejar la burbuja a la vista: 1 s por cada 15 letras, al menos 8 s."""
    return max(8000, len(str(texto or "")) * 1000 // 15)


# ── Clic simple vs. doble clic ────────────────────────────────────────────────

class DesambiguadorClic(QObject):
    """
    clic()        un clic limpio (sin arrastre): espera el intervalo de doble clic
                  y, si no llega otro, llama a `al_simple()`.
    doble_clic()  cancela el clic simple pendiente y llama a `al_doble()`.
    """

    def __init__(self, al_simple: Callable[[], Any], al_doble: Callable[[], Any],
                 parent: Optional[QObject] = None, *,
                 intervalo: Optional[Callable[[], int]] = None, temporizador: Any = None):
        super().__init__(parent)
        self._al_simple = al_simple
        self._al_doble = al_doble
        self._intervalo = intervalo or intervalo_doble_clic
        self._timer = temporizador if temporizador is not None else QTimer(self)
        try:
            self._timer.setSingleShot(True)
        except Exception:  # noqa: BLE001 — temporizador de mentira sin el método
            pass
        self._timer.timeout.connect(self._vencio)

    def pendiente(self) -> bool:
        try:
            return bool(self._timer.isActive())
        except Exception:  # noqa: BLE001
            return False

    def clic(self) -> None:
        self._timer.start(max(1, int(self._intervalo())))

    def doble_clic(self) -> None:
        self.cancelar()
        self._llamar(self._al_doble)

    def cancelar(self) -> None:
        try:
            self._timer.stop()
        except Exception:  # noqa: BLE001
            pass

    def _vencio(self) -> None:
        self._llamar(self._al_simple)

    @staticmethod
    def _llamar(fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 — un fallo de la acción no rompe el ratón
            log.exception("chat_asistente: fallo en la acción del clic")


# ── La cajita de chat de la asistente ───────────────────────────────────────────

class ChatAsistente(QObject):
    """EntradaChat de una asistente (`dueno`). Se crea al abrirla por primera vez."""

    def __init__(self, dueno: QWidget, *, crear_entrada: Optional[Callable[[], Any]] = None):
        super().__init__(dueno)
        self.dueno = dueno
        self._crear_entrada = crear_entrada
        self.entrada = None

    def _entrada(self):
        if self.entrada is None:
            if self._crear_entrada is not None:
                self.entrada = self._crear_entrada()
            else:
                from ui.entrada_chat import EntradaChat
                self.entrada = EntradaChat()
            self.entrada.enviado.connect(self._enviado)
        return self.entrada

    def abierta(self) -> bool:
        try:
            return self.entrada is not None and bool(self.entrada.isVisible())
        except RuntimeError:
            return False

    def abrir(self) -> None:
        """Abre la cajita bajo la asistente y le da el foco (llamar tras el clic)."""
        entrada = self._entrada()
        rect = None
        try:
            rect = self.dueno.frameGeometry()
        except Exception:  # noqa: BLE001
            rect = None
        entrada.mostrar_junto_a(rect)
        self._precalentar(entrada)

    def _precalentar(self, entrada) -> None:
        proveedor = getattr(self.dueno, "proveedor_chat", None)
        if not callable(proveedor):
            return
        try:
            if str(proveedor() or "") != "ollama":
                return
            from nucleo import datos
            entrada.precalentar(datos.ollama_url(), datos.ollama_model())
        except Exception:  # noqa: BLE001 — precalentar es opcional
            log.info("chat_asistente: no pude precalentar el modelo", exc_info=True)

    def cerrar(self) -> None:
        if self.entrada is not None:
            try:
                self.entrada.cerrar()
            except RuntimeError:
                pass

    def destruir(self) -> None:
        """Al cerrar la asistente: la cajita se va con ella."""
        e, self.entrada = self.entrada, None
        if e is not None:
            try:
                e.close()
                e.deleteLater()
            except RuntimeError:
                pass

    def _enviado(self, texto: str) -> None:
        texto = str(texto or "").strip()
        if not texto:
            return
        cb = getattr(self.dueno, "on_chat", None)
        if not callable(cb):
            self._decir(AVISO_SIN_CHAT)
            return
        try:
            cb(texto)
        except Exception:  # noqa: BLE001
            log.exception("chat_asistente: on_chat falló")
            self._decir("Uf, no pude mandar eso.")

    def _decir(self, texto: str) -> None:
        for metodo, args in (("burbuja_texto", (texto,)), ("burbuja_fin", (6000,))):
            fn = getattr(self.dueno, metodo, None)
            if callable(fn):
                try:
                    fn(*args)
                except Exception:  # noqa: BLE001
                    pass


# ── Burbuja Qt (asistente de sprites) ───────────────────────────────────────────

class BurbujaQt(QLabel):
    """Burbuja de texto sobre la asistente de sprites. `texto(t)` y `fin(ms)`."""

    ANCHO_MAX = 320
    MAX_CARACTERES = 600

    def __init__(self, dueno: Optional[QWidget] = None):
        super().__init__(None)
        self._dueno = dueno
        self.setWindowFlags(Qt.WindowType.Tool
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMaximumWidth(self.ANCHO_MAX)
        try:
            from ui.theme import COLORS, FONT_BODY
            self.setStyleSheet(
                f"QLabel{{background:{COLORS['surface']};color:{COLORS['text']};"
                f"border:2px solid {COLORS['accent']};border-radius:10px;padding:8px 10px;"
                f"font-family:'{FONT_BODY}';font-size:12px;}}")
        except Exception:  # noqa: BLE001
            pass
        self._t_fin = QTimer(self)
        self._t_fin.setSingleShot(True)
        self._t_fin.timeout.connect(self.hide)

    def texto(self, texto: str) -> None:
        t = str(texto or "").strip()
        if not t:
            return
        if len(t) > self.MAX_CARACTERES:
            t = "…" + t[-self.MAX_CARACTERES:]
        self._t_fin.stop()
        self.setText(t)
        self.adjustSize()
        self._colocar()
        if not self.isVisible():
            self.show()
        self.raise_()

    def fin(self, ms: Optional[int] = None) -> None:
        ms = ms_lectura(self.text()) if ms is None else int(ms)
        if ms <= 0:
            self.hide()
        else:
            self._t_fin.start(ms)

    def _colocar(self) -> None:
        from ui.entrada_chat import pantalla_disponible, posicion_junto_a
        rect = None
        if self._dueno is not None:
            try:
                rect = self._dueno.frameGeometry()
            except RuntimeError:
                rect = None
        x, y = posicion_junto_a(rect, (self.width(), self.height()), pantalla_disponible(rect),
                                preferencias=("arriba", "izquierda", "derecha", "abajo"))
        self.move(x, y)
