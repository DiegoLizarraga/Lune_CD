"""
ui/companion.py — Lune como companion flotante de escritorio (v10, estilo anime animado).

Ventana pequeña, sin bordes, siempre encima y arrastrable que muestra a Lune con
el nuevo estilo ANIMADO (los clips webm de la piel web dentro de un mini-stage con
marco neón) y una burbuja donde comenta lo que ve en tu pantalla.

- Comentarios de pantalla: captura la pantalla, se la manda al modelo (visión) y
  muestra un comentario breve en la burbuja. Manual (bandeja) o periódico opcional
  (config avatar.comentarios_cada_min; 0 = apagado). Usa el proveedor actual: con
  Ollama es 100% local; con OpenRouter la captura viaja a la nube.
"""
from __future__ import annotations

import base64
import io

from PyQt6.QtCore import Qt, QUrl, QPoint, QTimer, QEvent
from PyQt6.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

from ui.web_shell import _ServidorEstatico, DIR_WEB, RAIZ
from nucleo import datos
from lune_core import marcadores

PAGINA = "companion.html"

# Emoción canónica del modelo → estado de video de la mascota.
EMOCION_A_ESTADO = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
}

_PROMPT_PANTALLA = (
    "Esta es una captura de la pantalla del usuario. Haz UN comentario BREVE "
    "(una sola frase), con tu personalidad: directa, curiosa, con filo y sin relleno "
    "ni emoji. No describas literalmente lo que ves: coméntalo como lo haría una "
    "compañera ingeniosa. Si no hay nada interesante, suelta algo ligero."
)


def _escape_js(texto: str) -> str:
    import json
    return json.dumps(texto or "", ensure_ascii=False)


class CompanionFlotante(QMainWindow):
    """Mascota flotante animada + burbuja de comentarios de pantalla."""

    def __init__(self, config=None, ai_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._ai = ai_manager
        self._worker = None
        self._pensando = False
        self._click_through = False
        self._arrastre = None

        self.setWindowTitle("Lune")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(240, 430)

        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = RAIZ / "assets" / f"lune_icon.{ext}"
            if ruta.exists():
                self._icono = QIcon(str(ruta)); self.setWindowIcon(self._icono); break

        self._servidor = _ServidorEstatico(DIR_WEB)
        self._servidor.iniciar()

        self.web = QWebEngineView()
        self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        try:
            self.web.page().setBackgroundColor(QColor(0, 0, 0, 0))
            s = self.web.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        except Exception:
            pass
        self.web.loadFinished.connect(self._on_cargado)
        self.web.setUrl(QUrl(f"http://127.0.0.1:{self._servidor.puerto}/{PAGINA}"))
        self.setCentralWidget(self.web)

        self._restaurar_posicion()
        self._construir_bandeja()

        # Comentarios automáticos de pantalla (opcional, apagado por defecto).
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.comentar_pantalla)
        self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))

    # ── Puente Python → JS ───────────────────────────────────────────────────────
    def _js(self, codigo: str):
        try:
            self.web.page().runJavaScript(codigo)
        except Exception:
            pass

    def _on_cargado(self, ok):
        try:
            fp = self.web.focusProxy()
            if fp is not None:
                fp.installEventFilter(self)   # arrastrar pinchando sobre la mascota
        except Exception:
            pass

    # ── Emoción ──────────────────────────────────────────────────────────────────
    def set_estado(self, estado: str, ms: int = 0):
        self._js(f"window.setEmocion && window.setEmocion({_escape_js(estado)})")

    def set_emocion(self, emocion: str, ms: int = 0):
        self.set_estado(EMOCION_A_ESTADO.get((emocion or "").lower(), "normal"))

    def set_act(self, act: dict, ms: int = 0):
        if isinstance(act, dict):
            self.set_emocion(str(act.get("emotion", "neutral")))

    # ── Comentario de pantalla ───────────────────────────────────────────────────
    def comentar_pantalla(self):
        if self._pensando or self._ai is None:
            return
        b64 = self._capturar()
        if not b64:
            self._decir("No pude ver la pantalla.", "nervous")
            return
        self._pensando = True
        self._js("window.pensando && window.pensando()")
        self.set_estado("thinking")
        self._b64 = b64
        self._lanzar(self._elegir_proveedor())

    # ── Proveedor con fallback: Ollama si responde; si no, la nube (OpenRouter) ──
    def _elegir_proveedor(self) -> str:
        """Ollama si hay modelo y el servidor contesta a un sondeo rápido; si no,
        OpenRouter (si hay clave). Así la mascota responde aunque Ollama esté caído."""
        hay_nube = bool(datos.openrouter_key())
        if datos.ollama_model():
            try:
                from servicios import ollama_client
                ok, _, _ = ollama_client.listar_modelos(datos.ollama_url(), timeout=3)
            except Exception:
                ok = False
            if ok:
                return "ollama"
            if hay_nube:
                self._js("window.comentar && window.comentar("
                         + _escape_js("Ollama no responde; uso la nube un momento.") + ")")
                return "openrouter"
            return "ollama"          # sin nube: se intenta igual y se avisa si falla
        return "openrouter"

    def _lanzar(self, provider: str):
        from servicios.ai_worker import AIWorker
        self._provider_actual = provider
        self._worker = AIWorker(self._ai, _PROMPT_PANTALLA, provider,
                                imagenes=[self._b64], permitir_acciones=False, emociones=True)
        self._worker.response_ready.connect(self._on_comentario)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _capturar(self):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            w, h = img.size
            if w > 1280:
                img = img.resize((1280, max(1, int(h * 1280 / w))))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return None

    def _on_comentario(self, respuesta: str):
        self._pensando = False
        self._reintentado = False      # el próximo fallo puede volver a intentar la nube
        try:
            hablable, control = marcadores.separar(respuesta)
            acts = [v for c, v in control if c == "act"]
        except Exception:
            hablable, acts = respuesta, []
        estado = EMOCION_A_ESTADO.get(acts[-1].get("emotion"), "happy") if acts else "happy"
        self._decir((hablable or "").strip() or "…", estado)

    def _on_error(self, _msg):
        # Si falló Ollama y hay clave de nube, reintenta UNA vez con OpenRouter.
        if (getattr(self, "_provider_actual", "") == "ollama"
                and datos.openrouter_key() and not getattr(self, "_reintentado", False)):
            self._reintentado = True
            self._lanzar("openrouter")
            return
        self._reintentado = False
        self._pensando = False
        self._decir("Uf, algo falló al mirar la pantalla.", "nervous")

    def _decir(self, texto: str, estado: str = "happy"):
        self.set_estado(estado)
        self._js(f"window.comentar && window.comentar({_escape_js(texto)})")

    # ── Comentarios automáticos ──────────────────────────────────────────────────
    def _aplicar_intervalo(self, minutos: int):
        try:
            minutos = int(minutos)
        except (TypeError, ValueError):
            minutos = 0
        if minutos > 0:
            self._timer.start(minutos * 60_000)
        else:
            self._timer.stop()

    def _alternar_auto(self, activo: bool):
        minutos = 3 if activo else 0
        if self.config:
            self.config.set("avatar", "comentarios_cada_min", minutos)
        self._aplicar_intervalo(minutos)

    # ── Modo fantasma (click-through) ────────────────────────────────────────────
    def set_click_through(self, activo: bool):
        import sys
        self._click_through = bool(activo)
        if sys.platform == "win32":
            try:
                import win32gui, win32con
                hwnd = int(self.winId())
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                ex = (ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT) if activo \
                    else (ex & ~win32con.WS_EX_TRANSPARENT)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
                return
            except Exception:
                pass
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)

    # ── Arrastre y click ─────────────────────────────────────────────────────────
    # Arrastre manual (no startSystemMove) para poder distinguir un CLICK de un
    # arrastre: si sueltas sin moverte, Lune comenta la pantalla.
    UMBRAL_ARRASTRE = 6   # px

    def _raton_press(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self._click_through:
            return
        self._arrastre = {
            "origen": ev.globalPosition().toPoint(),
            "ventana": self.pos(),
            "movido": False,
        }

    def _raton_move(self, ev):
        a = self._arrastre
        if not a or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = ev.globalPosition().toPoint() - a["origen"]
        if not a["movido"] and (abs(delta.x()) > self.UMBRAL_ARRASTRE or abs(delta.y()) > self.UMBRAL_ARRASTRE):
            a["movido"] = True
        if a["movido"]:
            self.move(a["ventana"] + delta)

    def _raton_release(self, ev):
        a = self._arrastre
        self._arrastre = None
        if not a or ev.button() != Qt.MouseButton.LeftButton:
            return
        if a["movido"]:
            self._guardar_posicion()
        else:
            self.comentar_pantalla()     # click limpio sobre Lune → comenta la pantalla

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self._raton_press(ev)
        elif t == QEvent.Type.MouseMove:
            self._raton_move(ev)
        elif t == QEvent.Type.MouseButtonRelease:
            self._raton_release(ev)
        return super().eventFilter(obj, ev)

    def mousePressEvent(self, ev):
        self._raton_press(ev); super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        self._raton_move(ev); super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._raton_release(ev); super().mouseReleaseEvent(ev)

    # ── Posición ─────────────────────────────────────────────────────────────────
    def _cfg_int(self, clave, default):
        try:
            return int(self.config.get("avatar", clave, default)) if self.config else default
        except (TypeError, ValueError):
            return default

    def _restaurar_posicion(self):
        x = self.config.get("avatar", "companion_x", None) if self.config else None
        y = self.config.get("avatar", "companion_y", None) if self.config else None
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
        else:
            p = self.screen() or QApplication.primaryScreen()
            if p:
                g = p.availableGeometry()
                self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)

    def _guardar_posicion(self):
        if self.config:
            self.config.set("avatar", "companion_x", self.x())
            self.config.set("avatar", "companion_y", self.y())

    # ── Bandeja ──────────────────────────────────────────────────────────────────
    def _construir_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self._icono, self)
        self.tray.setToolTip("Lune · companion")
        menu = QMenu()
        act_com = QAction("Comentar la pantalla ahora", self)
        act_com.triggered.connect(self.comentar_pantalla)
        self.act_auto = QAction("Comentarios automáticos", self)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(self._cfg_int("comentarios_cada_min", 0) > 0)
        self.act_auto.toggled.connect(self._alternar_auto)
        self.act_fantasma = QAction("Modo fantasma (dejar pasar clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.toggled.connect(self.set_click_through)
        act_cerrar = QAction("Cerrar companion", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_com)
        menu.addAction(self.act_auto)
        menu.addAction(self.act_fantasma)
        menu.addSeparator(); menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, ev):
        self._guardar_posicion()
        self._timer.stop()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        if self._servidor is not None:
            self._servidor.detener()
        ev.accept()
