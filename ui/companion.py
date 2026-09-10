"""
ui/companion.py — Lune como companion flotante de escritorio (v10.1).

Ventana pequeña, sin bordes, siempre encima y arrastrable con una burbuja donde
Lune comenta lo que ve en tu pantalla. Dos formas de dibujarla (config avatar.render):

    "animado"  los clips webm de la piel web en un mini-stage con marco neón
               (ui_web/companion.html).
    "vrm"      un avatar 3D VRM (ui_web/companion_vrm.html + ui_web/vrm/lune_vrm.js,
               three.js + @pixiv/three-vrm empaquetados en ui_web/vendor). El .vrm
               se elige por personaje (nucleo/vrm.py) y se sirve por el http local.

Comportamientos de mascota (modo VRM), portados de Mate-Engine a procedural:
  - sigue el cursor con cabeza, ojos y torso aunque esté fuera de la ventana
    (Python le manda la posición global a ~30 Hz);
  - al arrastrarla se balancea según la velocidad y rebota al soltarla;
  - se duerme tras N minutos sin tocarla ni hablarle (avatar.dormir_min);
  - mueve la boca mientras suena la voz (VoiceEngine.al_hablar);
  - "fantasma automático": los clics pasan al escritorio donde NO hay avatar
    (la página dice si el cursor está sobre el modelo y aquí se conmuta
    WS_EX_TRANSPARENT), además del modo fantasma total de la bandeja.

Comentarios de pantalla: captura la pantalla, se la manda al modelo (visión) y
muestra un comentario breve en la burbuja. Manual (clic sobre ella / bandeja) o
periódico opcional (avatar.comentarios_cada_min; 0 = apagado). Usa el proveedor
actual: con Ollama es 100% local; con OpenRouter la captura viaja a la nube.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QPoint, QTimer, QEvent, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QActionGroup, QColor, QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

from ui.servidor_web import ServidorEstatico, DIR_WEB, RAIZ
from nucleo import datos
from lune_core import marcadores

PAGINAS = {"animado": "companion.html", "vrm": "companion_vrm.html"}
RUTA_MODELO = "/vrm/actual.vrm"          # el .vrm activo, publicado por el http local

# Tamaño de la ventana (px) por modo de render y tamaño elegido.
TAMANOS_VRM = {"pequeno": (210, 330), "normal": (290, 460), "grande": (390, 620)}
TAMANO_ANIMADO = (240, 430)
ENCUADRES = ("retrato", "cuerpo")

# Emoción canónica del modelo → estado de la mascota (mismo vocabulario en las
# dos páginas: companion.html lo mapea a clips y companion_vrm.html a expresiones).
EMOCION_A_ESTADO = {
    "happy": "happy", "sad": "sad", "angry": "angry", "think": "thinking",
    "surprised": "surprised", "awkward": "nervous", "question": "thinking",
    "curious": "curious", "neutral": "normal",
    # v10 — un estado por clip; si el clip aún no existe, el visor cae al idle.
    "nervous": "nervous", "wave": "wave", "dismiss": "dismiss",
    # v10.1
    "laughing": "laughing", "bored": "bored",
}

_PROMPT_PANTALLA = (
    "Esta es una captura de la pantalla del usuario. Haz UN comentario BREVE "
    "(una sola frase), con tu personalidad: directa, curiosa, con filo y sin relleno "
    "ni emoji. No describas literalmente lo que ves: coméntalo como lo haría una "
    "compañera ingeniosa. Si no hay nada interesante, suelta algo ligero."
)
# Sin visión (modelo local de solo texto): se le cuenta qué ventana tiene delante.
_PROMPT_VENTANA = (
    "No puedes ver la pantalla, pero sabes qué tiene delante el usuario ahora mismo: "
    "{contexto}. Haz UN comentario BREVE (una sola frase), con tu personalidad: directa, "
    "curiosa, con filo y sin relleno ni emoji. No lo describas literalmente: coméntalo "
    "como lo haría una compañera ingeniosa. Si no da para mucho, suelta algo ligero."
)
_PREFIJOS_ERROR = ("Error Ollama:", "Error OpenRouter:", "Error:")
_AVISO_SIN_VISION_NUBE = "Tu modelo local no ve imágenes; para la pantalla uso la nube."
_AVISO_SIN_VISION_TEXTO = ("Tu modelo local no ve imágenes: comento por la ventana activa. "
                           "Con «ollama pull llava» (u otro con visión) vería la pantalla.")


def _es_error(texto: str) -> bool:
    """Los proveedores devuelven sus fallos como texto; no son un comentario."""
    return str(texto or "").lstrip().startswith(_PREFIJOS_ERROR)


def _parece_sin_vision(msg: str) -> bool:
    m = str(msg or "").lower()
    return "400" in m or "image" in m or "imagen" in m or "vision" in m or "does not support" in m


def _contexto_ventana() -> str:
    """Qué tiene el usuario delante, sin captura: título de la ventana activa y programa."""
    titulo, proceso = "", ""
    if sys.platform == "win32":
        try:
            import win32gui, win32process
            h = win32gui.GetForegroundWindow()
            titulo = (win32gui.GetWindowText(h) or "").strip()
            try:
                import psutil
                _, pid = win32process.GetWindowThreadProcessId(h)
                proceso = psutil.Process(pid).name()
            except Exception:
                proceso = ""
        except Exception:
            pass
    partes = []
    if titulo:
        partes.append(f"la ventana «{titulo[:120]}»")
    if proceso:
        partes.append(f"del programa {proceso}")
    return " ".join(partes)


def _js_str(texto: str) -> str:
    return json.dumps(texto or "", ensure_ascii=False)


def _log(msg: str):
    try:
        from nucleo.utils import log_info
        log_info(msg)
    except Exception:
        pass


class CompanionFlotante(QMainWindow):
    """Mascota flotante (video anime o avatar VRM) + burbuja de comentarios."""

    visibilidad = pyqtSignal(bool)       # se muestra / se oculta o cierra
    recrear = pyqtSignal()               # "ya puedo ser VRM": quien me creó debe recrearme

    UMBRAL_ARRASTRE = 6                  # px: menos que esto es un CLIC, no arrastre
    CURSOR_HZ = 30                       # frecuencia con la que se le manda el cursor

    def __init__(self, config=None, ai_manager=None, render: str | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._ai = ai_manager
        self._worker = None
        self._pensando = False
        self._click_through = False      # modo fantasma TOTAL (bandeja)
        self._fantasma_auto = False      # ahora mismo dejando pasar clics (auto)
        self._sobre_modelo = True        # última respuesta de la página
        self._arrastre = None
        self._durmiendo = False
        self._revert_token = 0
        self.cerrado = False
        self.modelo: Path | None = None

        self.render_pedido = render or (str(self.config.get("avatar", "render", "animado")) if self.config else "animado")
        self.render = self._elegir_render(render)

        self.setWindowTitle("Lune")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus   # nunca roba el foco a lo que usas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._escala = self._escala_obj = self._cfg_float("vrm_escala", 1.0)
        self.resize(*self._tamano_ventana())

        self._icono = QIcon()
        for ext in ("ico", "png"):
            ruta = RAIZ / "assets" / f"lune_icon.{ext}"
            if ruta.exists():
                self._icono = QIcon(str(ruta)); self.setWindowIcon(self._icono); break

        rutas_extra = {RUTA_MODELO: self.modelo} if self.modelo else {}
        self._servidor = ServidorEstatico(DIR_WEB, rutas_extra=rutas_extra)
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
        self.web.setUrl(QUrl(self._url_pagina()))
        self.setCentralWidget(self.web)

        self._restaurar_posicion()
        self._construir_bandeja()

        # Comentarios automáticos de pantalla (opcional, apagado por defecto).
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.comentar_pantalla)
        self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))

        # Solo VRM: cursor global → la página; sueño por inactividad.
        self._timer_cursor = QTimer(self)
        self._timer_cursor.setInterval(int(1000 / self.CURSOR_HZ))
        self._timer_cursor.timeout.connect(self._enviar_cursor)
        self._timer_sueno = QTimer(self)
        self._timer_sueno.setSingleShot(True)
        self._timer_sueno.timeout.connect(self._dormir)
        self._ultimo_cursor = (None, None)
        # Escala con la rueda del ratón (se materializa como tamaño de ventana).
        self._timer_escala = QTimer(self)
        self._timer_escala.setInterval(16)
        self._timer_escala.timeout.connect(self._paso_escala)
        self._t_escala = 0.0

        # Modo fantasma total guardado (como la mascota de sprites): se aplica ya mostrada.
        if self._cfg_bool("click_through", False):
            QTimer.singleShot(300, lambda: self.set_click_through(True))

    # ── Render, modelo y página ──────────────────────────────────────────────────
    def _elegir_render(self, render: str | None) -> str:
        r = render or (str(self.config.get("avatar", "render", "animado")) if self.config else "animado")
        if r != "vrm":
            return "animado"
        from nucleo import vrm
        self.modelo = vrm.ruta_modelo(self.config)
        if self.modelo is None:
            _log("[companion] modo VRM pedido pero no hay ningún .vrm (modelo_vrm/): uso el animado")
            return "animado"
        return "vrm"

    def _tamano_ventana(self):
        if self.render != "vrm":
            return TAMANO_ANIMADO
        w, h = TAMANOS_VRM.get(self._cfg_str("vrm_tamano", "normal"), TAMANOS_VRM["normal"])
        return max(120, round(w * self._escala)), max(180, round(h * self._escala))

    def _url_pagina(self) -> str:
        pagina = PAGINAS[self.render]
        if self.render != "vrm":
            return self._servidor.url(pagina)
        try:
            v = int(self.modelo.stat().st_mtime)
        except OSError:
            v = 0
        enc = self._cfg_str("vrm_encuadre", "retrato")
        return (self._servidor.url(pagina)
                + f"?src={RUTA_MODELO}&v={v}&enc={enc if enc in ENCUADRES else 'retrato'}")

    def recargar_modelo(self):
        """El personaje activo cambió: si tiene otro .vrm, se carga sin cerrar la ventana.
        Si esta ventana arrancó degradada a vídeo por falta de modelo y ahora ya hay
        uno, pide que la recreen (la página de vídeo no puede volverse 3D)."""
        from nucleo import vrm
        if self.render != "vrm":
            if self.render_pedido == "vrm" and vrm.ruta_modelo(self.config) is not None:
                self.recrear.emit()
            return
        nuevo = vrm.ruta_modelo(self.config)
        if nuevo is None or nuevo == self.modelo:
            return
        self.modelo = nuevo
        self._servidor.publicar(RUTA_MODELO, nuevo)
        try:
            v = int(nuevo.stat().st_mtime)
        except OSError:
            v = 0
        self._js(f"window.luneCargarModelo && window.luneCargarModelo({_js_str(f'{RUTA_MODELO}?v={v}')})")

    # ── Puente Python → JS ───────────────────────────────────────────────────────
    def _js(self, codigo: str, callback=None):
        try:
            if callback is None:
                self.web.page().runJavaScript(codigo)
            else:
                self.web.page().runJavaScript(codigo, callback)
        except Exception:
            pass

    def _on_cargado(self, ok):
        try:
            fp = self.web.focusProxy()
            if fp is not None:
                fp.installEventFilter(self)   # arrastrar pinchando sobre la mascota
        except Exception:
            pass
        if self.render == "vrm" and ok:
            self._timer_cursor.start()
            self._rearmar_sueno()

    # ── Estado / emoción ─────────────────────────────────────────────────────────
    def set_estado(self, estado: str, ms: int = 0):
        """Estado visual ('happy', 'thinking', …). Con ms > 0 vuelve solo al idle."""
        self._despertar()
        self._js(f"window.setEmocion && window.setEmocion({_js_str(estado)})")
        self._revert_token += 1
        if ms and ms > 0 and estado != "normal":
            token = self._revert_token
            QTimer.singleShot(int(ms), lambda: self._revertir(token))

    def _revertir(self, token: int):
        if token == self._revert_token and not self._pensando:
            self._js("window.setEmocion && window.setEmocion('normal')")

    def set_emocion(self, emocion: str, ms: int = 0):
        self.set_estado(EMOCION_A_ESTADO.get((emocion or "").lower(), "normal"), ms)

    def set_act(self, act: dict, ms: int = 0):
        if isinstance(act, dict):
            self.set_emocion(str(act.get("emotion", "neutral")), ms)

    def set_hablando(self, hablando: bool):
        """La voz está sonando: el avatar VRM mueve la boca (no-op en animado)."""
        if hablando:
            self._despertar()
        self._js(f"window.luneSpeak && window.luneSpeak({'true' if hablando else 'false'})")

    # ── Cursor global → cabeza/ojos/torso, y fantasma automático ─────────────────
    def _enviar_cursor(self):
        if not self.isVisible() or self.web is None:
            return
        c = QCursor.pos()
        g = self.geometry()
        pantalla = self.screen() or QApplication.primaryScreen()
        sg = pantalla.geometry() if pantalla else g
        # Normalizado respecto al centro de la cara (≈ 35 % desde arriba en retrato)
        # y a media pantalla: -1..1 dentro del monitor, más allá si se sale.
        cx = g.left() + g.width() / 2
        cy = g.top() + g.height() * 0.35
        nx = (c.x() - cx) / max(1.0, sg.width() / 2)
        ny = (cy - c.y()) / max(1.0, sg.height() / 2)
        nx = max(-1.6, min(1.6, nx)); ny = max(-1.6, min(1.6, ny))
        dentro = g.contains(c)
        px = c.x() - g.left(); py = c.y() - g.top()
        ux, uy = self._ultimo_cursor
        if ux is not None and abs(nx - ux) < 0.002 and abs(ny - uy) < 0.002 and not dentro:
            return
        self._ultimo_cursor = (nx, ny)
        self._js(f"window.luneCursor ? window.luneCursor({nx:.4f}, {ny:.4f}, {int(px)}, {int(py)}, {'true' if dentro else 'false'}) : null",
                 self._on_cursor_respuesta if dentro else None)
        if not dentro and self._fantasma_auto and not self._click_through:
            # Fuera de la ventana no hace falta dejar pasar clics: volver a normal
            # para que al entrar sobre el avatar responda al primer clic.
            self._aplicar_transparente(False)

    def _on_cursor_respuesta(self, sobre_modelo):
        """La página dice si el cursor está sobre el avatar (píxel con alfa)."""
        if sobre_modelo is None or self._click_through or self._arrastre:
            return
        sobre = bool(sobre_modelo)
        if sobre == self._sobre_modelo:
            return
        self._sobre_modelo = sobre
        if self._cfg_bool("vrm_fantasma_auto", True):
            self._aplicar_transparente(not sobre)

    def _aplicar_transparente(self, activo: bool):
        """WS_EX_TRANSPARENT (Windows) o WA_TransparentForMouseEvents: deja pasar los clics."""
        activo = bool(activo)
        if self._fantasma_auto == activo and not self._click_through:
            return
        self._fantasma_auto = activo
        if sys.platform == "win32":
            try:
                import win32gui, win32con
                hwnd = int(self.winId())
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                ex = (ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT) if activo \
                    else (ex & ~win32con.WS_EX_TRANSPARENT)
                # WS_EX_TRANSPARENT solo afecta al hit-test: no hace falta SWP_FRAMECHANGED
                # (forzaría un repintado de la ventana translúcida = parpadeo al cruzar el borde).
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
                return
            except Exception:
                pass
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, activo)

    def event(self, ev):
        # Si la ventana llega a activarse (Alt-Tab, bandeja) no puede quedarse
        # "fantasma": vuelve a recibir clics hasta el siguiente sondeo del cursor.
        if ev.type() == QEvent.Type.WindowActivate and not self._click_through and self._fantasma_auto:
            self._sobre_modelo = True
            self._aplicar_transparente(False)
        return super().event(ev)

    # ── Escala con la rueda (Mate-Engine: ±0.1 por muesca, con suavizado) ────────
    ESCALA_MIN, ESCALA_MAX, ESCALA_PASO = 0.6, 1.5, 0.1

    def _rueda(self, ev) -> bool:
        if self.render != "vrm" or self._arrastre or self._click_through:
            return False
        muescas = ev.angleDelta().y() / 120.0
        if not muescas:
            return False
        self._despertar()
        self._escala_obj = max(self.ESCALA_MIN, min(self.ESCALA_MAX, self._escala_obj + muescas * self.ESCALA_PASO))
        if not self._timer_escala.isActive():
            self._t_escala = time.monotonic()
            self._timer_escala.start()
        return True

    def _paso_escala(self):
        ahora = time.monotonic()
        dt = max(1e-3, min(0.05, ahora - self._t_escala)); self._t_escala = ahora
        f = 1 - (1 - 0.3) ** (dt * 60)              # lerp exponencial normalizado a 60 fps
        self._escala += (self._escala_obj - self._escala) * f
        llegado = abs(self._escala_obj - self._escala) < 0.003
        if llegado:
            self._escala = self._escala_obj
            self._timer_escala.stop()
        w, h = self._tamano_ventana()
        if (w, h) != (self.width(), self.height()):
            g = self.geometry()                     # crece desde los pies, centrada
            self.setGeometry(g.center().x() - w // 2, g.bottom() - h, w, h)
        if llegado:                                 # config.json se escribe UNA vez, al final
            self._asegurar_en_pantalla()
            if self.config:
                self.config.set("avatar", "vrm_escala", round(self._escala, 3))
            self._guardar_posicion()

    def wheelEvent(self, ev):
        if not self._rueda(ev):
            super().wheelEvent(ev)

    # ── Sueño por inactividad (solo VRM) ─────────────────────────────────────────
    def _rearmar_sueno(self):
        if self.render != "vrm":
            return
        minutos = self._cfg_int("dormir_min", 10)
        self._timer_sueno.stop()
        if minutos > 0:
            self._timer_sueno.start(minutos * 60_000)

    def _dormir(self):
        if self.render != "vrm" or self._durmiendo or self._pensando:
            return
        self._durmiendo = True
        self._js("window.luneSleep && window.luneSleep(true)")

    def _despertar(self):
        if self.render != "vrm":
            return
        if self._durmiendo:
            self._durmiendo = False
            self._js("window.luneSleep && window.luneSleep(false)")
        self._rearmar_sueno()

    # ── Comentario de pantalla ───────────────────────────────────────────────────
    def comentar_pantalla(self):
        if self._pensando or self._ai is None:
            return
        self._despertar()
        proveedor, con_imagen = self._elegir_proveedor()
        self._b64 = None
        if con_imagen:
            b64 = self._capturar()
            if not b64:
                self._decir("No pude ver la pantalla.", "nervous")
                return
            self._b64 = b64
        self._pensando = True
        self._reintentado = False
        self._js("window.pensando && window.pensando()")
        self.set_estado("thinking")
        self._lanzar(proveedor, con_imagen)

    # ── Proveedor con fallback ───────────────────────────────────────────────────
    def _elegir_proveedor(self):
        """
        Devuelve (proveedor, con_imagen):
          · Ollama responde y su modelo VE imágenes → Ollama con captura (100 % local).
          · Ollama responde pero el modelo es de solo texto → la nube con captura si hay
            clave; si no, Ollama en modo texto (le contamos qué ventana hay delante).
          · Ollama no responde → la nube si hay clave; si no, se intenta igual.
          · Sin modelo local → la nube.
        """
        hay_nube = bool(datos.openrouter_key())
        if datos.ollama_model():
            try:
                from servicios import ollama_client
                ok, _, _ = ollama_client.listar_modelos(datos.ollama_url(), timeout=3)
            except Exception:
                ok = False
            if ok:
                if self._vision_local() is False:
                    if hay_nube:
                        self._avisar_una_vez(_AVISO_SIN_VISION_NUBE)
                        return "openrouter", True
                    self._avisar_una_vez(_AVISO_SIN_VISION_TEXTO)
                    return "ollama", False
                return "ollama", True
            if hay_nube:
                self._js("window.comentar && window.comentar("
                         + _js_str("Ollama no responde; uso la nube un momento.") + ")")
                return "openrouter", True
            return "ollama", True    # sin nube: se intenta igual y se avisa si falla
        return "openrouter", True

    def _vision_local(self):
        """True/False si se sabe si el modelo local ve imágenes; None si no se pudo saber."""
        try:
            from servicios import ollama_client
            return ollama_client.soporta_vision(datos.ollama_url(), datos.ollama_model(), timeout=3)
        except Exception:
            return None

    def _avisar_una_vez(self, texto: str):
        dados = getattr(self, "_avisos_dados", None)
        if dados is None:
            dados = self._avisos_dados = set()
        if texto in dados:
            return
        dados.add(texto)
        self._js(f"window.comentar && window.comentar({_js_str(texto)}, 9000)")

    def _lanzar(self, provider: str, con_imagen: bool = True):
        from servicios.ai_worker import AIWorker
        self._provider_actual = provider
        self._con_imagen = bool(con_imagen and self._b64)
        if self._con_imagen:
            prompt, imagenes = _PROMPT_PANTALLA, [self._b64]
        else:
            prompt = _PROMPT_VENTANA.format(contexto=_contexto_ventana() or "algo sin título")
            imagenes = []
        self._worker = AIWorker(self._ai, prompt, provider,
                                imagenes=imagenes, permitir_acciones=False, emociones=True)
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
        # Los proveedores devuelven sus fallos como texto: no van a la burbuja tal cual.
        if _es_error(respuesta):
            self._fallo(respuesta)
            return
        self._pensando = False
        self._reintentado = False      # el próximo fallo puede volver a intentar la nube
        try:
            hablable, control = marcadores.separar(respuesta)
            acts = [v for c, v in control if c == "act"]
        except Exception:
            hablable, acts = respuesta, []
        estado = EMOCION_A_ESTADO.get(acts[-1].get("emotion"), "happy") if acts else "happy"
        self._decir((hablable or "").strip() or "…", estado)

    def _on_error(self, msg):
        self._fallo(str(msg or ""))

    def _fallo(self, msg: str):
        """Un comentario falló. Se reintenta UNA vez con la mejor alternativa:
        Ollama rechazó la captura (modelo sin visión) → nube con captura, o Ollama en
        modo texto; Ollama caído → nube. Si no hay más, Lune lo dice con gracia."""
        _log(f"[companion] comentario de pantalla falló ({getattr(self, '_provider_actual', '?')}): {msg[:200]}")
        proveedor = getattr(self, "_provider_actual", "")
        reintentado = getattr(self, "_reintentado", False)
        if proveedor == "ollama" and not reintentado:
            self._reintentado = True
            if getattr(self, "_con_imagen", False) and _parece_sin_vision(msg):
                try:
                    from servicios import ollama_client
                    ollama_client.marcar_sin_vision(datos.ollama_url(), datos.ollama_model())
                except Exception:
                    pass
                if datos.openrouter_key():
                    self._avisar_una_vez(_AVISO_SIN_VISION_NUBE)
                    self._lanzar("openrouter", True)
                else:
                    self._avisar_una_vez(_AVISO_SIN_VISION_TEXTO)
                    self._lanzar("ollama", False)
                return
            if datos.openrouter_key():
                self._lanzar("openrouter", bool(self._b64))
                return
        self._reintentado = False
        self._pensando = False
        self._decir("Uf, algo falló al mirar la pantalla.", "nervous")

    def _decir(self, texto: str, estado: str = "happy"):
        self.set_estado(estado, 9000)
        self._js(f"window.comentar && window.comentar({_js_str(texto)})")

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

    # ── Modo fantasma total (click-through) ──────────────────────────────────────
    def set_click_through(self, activo: bool):
        self._click_through = bool(activo)
        self._fantasma_auto = None            # fuerza a reaplicar
        self._aplicar_transparente(self._click_through)
        if not self._click_through:
            self._sobre_modelo = True         # que el siguiente sondeo decida
        if self.config and self.config.get("avatar", "click_through", False) != self._click_through:
            self.config.set("avatar", "click_through", self._click_through)
        act = getattr(self, "act_fantasma", None)
        if act is not None and act.isChecked() != self._click_through:
            act.setChecked(self._click_through)

    def aplicar_opciones(self):
        """Ajustes cambiaron (dormir_min, vrm_fantasma_auto, comentarios): aplicar en caliente."""
        self._aplicar_intervalo(self._cfg_int("comentarios_cada_min", 0))
        if getattr(self, "act_auto", None) is not None:
            self.act_auto.setChecked(self._cfg_int("comentarios_cada_min", 0) > 0)
        if self.render != "vrm":
            return
        self._rearmar_sueno()
        if not self._cfg_bool("vrm_fantasma_auto", True) and not self._click_through:
            self._sobre_modelo = True
            self._aplicar_transparente(False)

    # ── Tamaño y encuadre (VRM) ──────────────────────────────────────────────────
    def aplicar_tamano(self, nombre: str):
        if self.render != "vrm" or nombre not in TAMANOS_VRM:
            return
        if self.config:
            self.config.set("avatar", "vrm_tamano", nombre)
        # Crece hacia arriba/izquierda para que los pies se queden donde estaban.
        w, h = self._tamano_ventana()
        g = self.geometry()
        self.setGeometry(g.right() - w, g.bottom() - h, w, h)
        self._asegurar_en_pantalla()
        self._guardar_posicion()

    def aplicar_encuadre(self, nombre: str):
        if self.render != "vrm" or nombre not in ENCUADRES:
            return
        if self.config:
            self.config.set("avatar", "vrm_encuadre", nombre)
        self._js(f"window.luneEncuadre && window.luneEncuadre({_js_str(nombre)})")

    # ── Arrastre y clic ──────────────────────────────────────────────────────────
    # Arrastre manual (no startSystemMove) para poder distinguir un CLIC de un
    # arrastre: si sueltas sin moverte, Lune comenta la pantalla. Mientras se
    # arrastra, el avatar VRM recibe la velocidad para balancearse.
    def _raton_press(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self._click_through:
            return
        self._despertar()
        self._arrastre = {
            "origen": ev.globalPosition().toPoint(),
            "ventana": self.pos(),
            "movido": False,
            "t": time.monotonic(),
            "ultimo": ev.globalPosition().toPoint(),
            "envio": 0.0,
        }

    def _raton_move(self, ev):
        a = self._arrastre
        if not a or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        p = ev.globalPosition().toPoint()
        delta = p - a["origen"]
        if not a["movido"] and (abs(delta.x()) > self.UMBRAL_ARRASTRE or abs(delta.y()) > self.UMBRAL_ARRASTRE):
            a["movido"] = True
            self._js("window.luneDrag && window.luneDrag(true, 0, 0)")
        if a["movido"]:
            self.move(a["ventana"] + delta)
            ahora = time.monotonic()
            dt = max(1e-3, ahora - a["t"])
            v = p - a["ultimo"]
            a["t"], a["ultimo"] = ahora, p
            if ahora - a["envio"] >= 1 / 60:          # px/ms, para la página
                a["envio"] = ahora
                self._js(f"window.luneDrag && window.luneDrag(true, {v.x() / dt / 1000:.3f}, {v.y() / dt / 1000:.3f})")

    def _raton_release(self, ev):
        a = self._arrastre
        self._arrastre = None
        if not a or ev.button() != Qt.MouseButton.LeftButton:
            return
        if a["movido"]:
            self._js("window.luneDrag && window.luneDrag(false, 0, 0)")
            self._asegurar_en_pantalla()
            self._guardar_posicion()
        else:
            self._js("window.luneTouch && window.luneTouch()")
            self.comentar_pantalla()     # clic limpio sobre Lune → comenta la pantalla

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self._raton_press(ev)
        elif t == QEvent.Type.MouseMove:
            self._raton_move(ev)
        elif t == QEvent.Type.MouseButtonRelease:
            self._raton_release(ev)
        elif t == QEvent.Type.Wheel:
            if self._rueda(ev):
                return True                          # la página no debe hacer scroll
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

    def _cfg_str(self, clave, default):
        try:
            return str(self.config.get("avatar", clave, default) or default) if self.config else default
        except Exception:
            return default

    def _cfg_float(self, clave, default):
        try:
            return float(self.config.get("avatar", clave, default)) if self.config else default
        except (TypeError, ValueError):
            return default

    def _cfg_bool(self, clave, default):
        try:
            return bool(self.config.get("avatar", clave, default)) if self.config else default
        except Exception:
            return default

    def _restaurar_posicion(self):
        x = self.config.get("avatar", "companion_x", None) if self.config else None
        y = self.config.get("avatar", "companion_y", None) if self.config else None
        if isinstance(x, int) and isinstance(y, int) and self._dentro_de_pantalla(x, y):
            self.move(x, y)
        else:
            self._esquina_inferior_derecha()

    def _dentro_de_pantalla(self, x, y) -> bool:
        for s in QApplication.screens():
            if s.availableGeometry().contains(QPoint(x + 20, y + 20)):
                return True
        return False

    def _esquina_inferior_derecha(self):
        p = self.screen() or QApplication.primaryScreen()
        if p:
            g = p.availableGeometry()
            self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)

    def _asegurar_en_pantalla(self):
        """Que al soltarla o crecer no quede fuera del monitor (Mate-Engine la devuelve)."""
        p = self.screen() or QApplication.primaryScreen()
        if not p:
            return
        g = p.availableGeometry()
        x = min(max(self.x(), g.left() - self.width() // 3), g.right() - self.width() * 2 // 3)
        y = min(max(self.y(), g.top()), g.bottom() - self.height() // 2)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

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
        self.tray.setToolTip("Lune · mascota 3D" if self.render == "vrm" else "Lune · companion")
        menu = QMenu()
        act_com = QAction("Comentar la pantalla ahora", self)
        act_com.triggered.connect(self.comentar_pantalla)
        self.act_auto = QAction("Comentarios automáticos", self)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(self._cfg_int("comentarios_cada_min", 0) > 0)
        self.act_auto.toggled.connect(self._alternar_auto)
        self.act_fantasma = QAction("Modo fantasma (dejar pasar todos los clics)", self)
        self.act_fantasma.setCheckable(True)
        self.act_fantasma.setChecked(self._cfg_bool("click_through", False))
        self.act_fantasma.toggled.connect(self.set_click_through)
        menu.addAction(act_com)
        menu.addAction(self.act_auto)
        menu.addAction(self.act_fantasma)
        if self.render == "vrm":
            menu.addSeparator()
            self._submenu_opciones(menu, "Tamaño", (("pequeno", "Pequeña"), ("normal", "Normal"), ("grande", "Grande")),
                                   self._cfg_str("vrm_tamano", "normal"), self.aplicar_tamano)
            self._submenu_opciones(menu, "Encuadre", (("retrato", "Retrato (cara y torso)"), ("cuerpo", "Cuerpo entero")),
                                   self._cfg_str("vrm_encuadre", "retrato"), self.aplicar_encuadre)
            act_esq = QAction("Llevar a la esquina", self)
            act_esq.triggered.connect(lambda: (self._esquina_inferior_derecha(), self._guardar_posicion()))
            menu.addAction(act_esq)
        menu.addSeparator()
        act_cerrar = QAction("Cerrar mascota", self)
        act_cerrar.triggered.connect(self.close)
        menu.addAction(act_cerrar)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _submenu_opciones(self, menu, titulo, opciones, actual, aplicar):
        sub = menu.addMenu(titulo)
        grupo = QActionGroup(self); grupo.setExclusive(True)
        for clave, etiqueta in opciones:
            a = QAction(etiqueta, self); a.setCheckable(True); a.setChecked(clave == actual)
            a.triggered.connect(lambda _=False, k=clave: aplicar(k))
            grupo.addAction(a); sub.addAction(a)

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def showEvent(self, ev):
        super().showEvent(ev)
        self.visibilidad.emit(True)
        self._js("window.luneSetFPS && window.luneSetFPS(60)")   # oculta no renderiza
        self._despertar()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.visibilidad.emit(False)
        self._js("window.luneSetFPS && window.luneSetFPS(0)")

    def closeEvent(self, ev):
        self.cerrado = True
        self._guardar_posicion()
        self._timer.stop(); self._timer_cursor.stop(); self._timer_sueno.stop(); self._timer_escala.stop()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        if self._servidor is not None:
            self._servidor.detener()
        ev.accept()
