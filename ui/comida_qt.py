"""
ui/comida_qt.py — La comida en el escritorio: el dibujo, la ventanita que sigue
al cursor y el controlador (actividad `comida` de la tabla de prioridades).

- `pintar_comida(p, id, variante, rect, ladeo, cabeceo, escala)`: dibujo
  procedural con QPainter (sin PNG): un batido con nata y pajita o un pastel con
  cobertura que gotea y una cereza, en el color de la variante.
- `ComidaCursor`: ventana transparente, sin foco y que no recibe el ratón
  (Frameless | Tool | StaysOnTop | WindowTransparentForInput |
  WindowDoesNotAcceptFocus) centrada en el cursor, sin suavizado (ME :131-137).
  Aparece en 0.25 s, se guarda en 0.2 s y se balancea al moverla
  (nucleo.comida.BalanceoComida).
- `ControlComida`: el controlador de ServiciosEscritorio (ui/escritorio.py).

AL APARECER (`alternar(id)`, acciones comer_batido / comer_pastel / comida)
  1. exige `comida.activa`;
  2. `prioridad.iniciar("comida")`; si se deniega (juego, alarma, pantalla
     grande, salvapantallas, MMD) avisa «Ahora no puedo comer: …»;
  3. sonidos por el Mezclador: comida_aparece (+ una capa en el batido);
  4. la vista:
       · con la asistente a la vista → `ComidaCursor` (≈ 0.33 del ancho de la
         asistente, mínimo 64 px), un QTimer de 16 ms SOLO mientras hay comida,
         `QCursor.pos()` y `asistente.cabeza(cb)` a 10 Hz;
       · en la web sin asistente fuera → `comida_web` (la dibuja la página y avisa
         del acierto con `acierto_web`);
       · en la nativa sin asistente → primero la saca (`anfitrion.alternar_asistente`);
  5. `asistente.set_comida_activa(True)`.
ACIERTO (el tramo del cursor pasa por la cabeza, por flanco y con 0.35 s de
  enfriamiento): `asistente.comer(tipo, 2500)` (o `anfitrion.reaccion("happy",
  2500)` sin asistente), trago_N / mordisco_N con tono al azar y emoción `happy`.
CAMBIO: pedir otra con una en la mano la cambia (suena comida_aparece).
SE GUARDA: al pedir la misma, a los 2 min sin moverla (D4), con `ceder` (sin
  sonido), con la asistente oculta o `None` (vista de escritorio), al apagar
  `comida.activa` o al detener.
`comer_directo(id)` (herramienta dar_de_comer): la reacción sin comida en el
  cursor; si no había comida, sostiene la actividad durante la reacción.

Si con la comida en la web aparece la asistente flotante, la comida pasa al
escritorio. Señales (JSON en texto, para el puente web):
    cambio(str)       {activa, id, variante, color, tipo, vista: escritorio|web|"", disponible}
    comida_web(str)   {accion: aparece|guarda|cambia, id, variante, color, tipo, nombre}
"""
from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from nucleo import comida as nc

_log = logging.getLogger("lune.comida")

TIC_MS = 16
CABEZA_S = 0.1                   # asistente.cabeza(cb) a 10 Hz
TAM_FRACCION, TAM_MIN, TAM_MAX, TAM_SIN_ASISTENTE = 0.33, 64, 220, 96

_TINTA = QColor(43, 28, 51, 235)
_NATA = QColor("#FFF7EE")
_GUARNICION = {"fresa": "#E23B5A", "mango": "#FF9F1C", "matcha": "#5E8C31"}
# pastel: variante → (bizcocho, relleno)
_PASTEL = {
    "chocolate": ("#3E2316", "#F3E3D0"),
    "fresa": ("#F2CF96", "#FF4F7E"),
    "limon": ("#F2CF96", "#FFF6C8"),
    "vainilla": ("#E9C27A", "#FFFFFF"),
}


# ── Dibujo ──────────────────────────────────────────────────────────────────────
def _pluma(ancho: float = 0.03) -> QPen:
    pen = QPen(_TINTA)
    pen.setWidthF(ancho)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _elipse(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def _media_anchura(y: float, y0: float, y1: float, w0: float, w1: float) -> float:
    k = (y - y0) / (y1 - y0) if y1 != y0 else 0.0
    return w0 + (w1 - w0) * k


def _pintar_batido(p: QPainter, color: QColor, variante: str) -> None:
    """Vaso de batido en una caja unidad (−0.5…0.5): vaso, líquido, nata y pajita."""
    y_top, y_bot, w_top, w_bot = -0.18, 0.44, 0.25, 0.18
    # Pajita (detrás de la nata): inclinada y a rayas.
    p.save()
    p.translate(0.06, -0.24)
    p.rotate(14)
    paja = QRectF(-0.03, -0.30, 0.06, 0.34)
    p.setPen(_pluma(0.025))
    p.setBrush(QBrush(QColor("#FFFFFF")))
    p.drawRoundedRect(paja, 0.02, 0.02)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color.darker(115)))
    for y in (-0.26, -0.16, -0.06):
        franja = QPolygonF([QPointF(-0.03, y), QPointF(0.03, y - 0.03), QPointF(0.03, y), QPointF(-0.03, y + 0.03)])
        p.drawPolygon(franja)
    p.restore()
    # Vaso.
    vaso = QPolygonF([QPointF(-w_top, y_top), QPointF(w_top, y_top), QPointF(w_bot, y_bot), QPointF(-w_bot, y_bot)])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 80)))
    p.drawPolygon(vaso)
    # Líquido.
    y_liq, margen = -0.10, 0.025
    wl = _media_anchura(y_liq, y_top, y_bot, w_top, w_bot) - margen
    wb = w_bot - margen
    liquido = QPolygonF([QPointF(-wl, y_liq), QPointF(wl, y_liq), QPointF(wb, y_bot - margen),
                         QPointF(-wb, y_bot - margen)])
    grad = QLinearGradient(QPointF(0, y_liq), QPointF(0, y_bot))
    grad.setColorAt(0.0, color.lighter(108))
    grad.setColorAt(1.0, color.darker(108))
    p.setBrush(QBrush(grad))
    p.drawPolygon(liquido)
    p.setBrush(QBrush(color.lighter(125)))
    p.drawEllipse(QPointF(0, y_liq), wl, 0.03)
    # Brillo del vaso.
    p.setBrush(QBrush(QColor(255, 255, 255, 120)))
    p.drawRoundedRect(QRectF(-0.185, -0.08, 0.035, 0.40), 0.017, 0.017)
    # Contorno del vaso.
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pluma())
    p.drawPolygon(vaso)
    # Nata (tres bolas unidas sobre el borde) y la guarnición.
    nata = _elipse(-0.13, -0.22, 0.10, 0.08).united(_elipse(0.13, -0.22, 0.10, 0.08))
    nata = nata.united(_elipse(0.0, -0.28, 0.12, 0.10))
    base = QPainterPath()
    base.addRoundedRect(QRectF(-0.27, -0.23, 0.54, 0.07), 0.03, 0.03)
    nata = nata.united(base)
    p.setBrush(QBrush(_NATA))
    p.drawPath(nata)
    p.setBrush(QBrush(QColor(_GUARNICION.get(variante, color.darker(125).name()))))
    p.drawEllipse(QPointF(0.12, -0.32), 0.05, 0.05)


def _pintar_pastel(p: QPainter, color: QColor, variante: str) -> None:
    """Pastel redondo en una caja unidad: bizcocho, relleno, cobertura que gotea y cereza."""
    rx, ry, y_top, y_bot = 0.38, 0.11, -0.08, 0.34
    bizcocho_hex, relleno_hex = _PASTEL.get(variante, ("#F2CF96", "#FFFFFF"))
    cuerpo = QPainterPath()
    cuerpo.addRect(QRectF(-rx, y_top, 2 * rx, y_bot - y_top))
    cuerpo = cuerpo.united(_elipse(0, y_bot, rx, ry)).united(_elipse(0, y_top, rx, ry))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(bizcocho_hex)))
    p.drawPath(cuerpo)
    # Relleno: una franja curva a media altura (la mitad delantera de una elipse).
    p.save()
    p.setClipPath(cuerpo)
    pen = QPen(QColor(relleno_hex))
    pen.setWidthF(0.05)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(-rx, 0.13 - ry, 2 * rx, 2 * ry), 180 * 16, 180 * 16)
    p.restore()
    p.setPen(_pluma())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(cuerpo)
    # Cobertura: la tapa y unas gotas por delante.
    cobertura = _elipse(0, y_top, rx + 0.01, ry + 0.01)
    for x, largo in ((-0.30, 0.07), (-0.16, 0.13), (0.0, 0.08), (0.15, 0.15), (0.29, 0.06)):
        y_arco = y_top + ry * math.sqrt(max(0.0, 1.0 - (x / rx) ** 2))
        gota = QPainterPath()
        gota.addRoundedRect(QRectF(x - 0.05, y_top, 0.10, (y_arco - y_top) + largo), 0.05, 0.05)
        cobertura = cobertura.united(gota)
    p.setBrush(QBrush(color))
    p.drawPath(cobertura)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 90)))
    p.drawEllipse(QPointF(-0.16, y_top - 0.02), 0.09, 0.03)
    # Cereza con rabito.
    rabito = QPainterPath(QPointF(0.0, -0.25))
    rabito.quadTo(QPointF(0.02, -0.34), QPointF(0.08, -0.38))
    p.setPen(QPen(QColor("#3F6B2A"), 0.025, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(rabito)
    p.setPen(_pluma(0.025))
    p.setBrush(QBrush(QColor("#E0344C")))
    p.drawEllipse(QPointF(0.0, -0.19), 0.075, 0.075)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 170)))
    p.drawEllipse(QPointF(-0.025, -0.215), 0.02, 0.02)


def pintar_comida(p: QPainter, id_: str, variante: str, rect, ladeo: float = 0.0, cabeceo: float = 0.0,
                  escala: float = 1.0) -> bool:
    """Dibuja la comida centrada en `rect` (lado = el menor de `rect` × `escala`).

    `ladeo` en grados, positivo = horario (arriba hacia la derecha); `cabeceo` en
    grados, positivo = la parte de arriba se aleja (se acorta en vertical).
    False si no hay nada que dibujar (comida desconocida, escala 0 o rect vacío)."""
    c = nc.comida(id_)
    r = QRectF(rect)
    try:
        escala = float(escala)
        ladeo = float(ladeo) if math.isfinite(float(ladeo)) else 0.0
        cabeceo = float(cabeceo) if math.isfinite(float(cabeceo)) else 0.0
    except (TypeError, ValueError):
        return False
    if c is None or r.isEmpty() or not math.isfinite(escala) or escala <= 0.0:
        return False
    v = nc.variante_de(c.id, variante)
    lado = min(r.width(), r.height()) * min(escala, 1.5)
    p.save()
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.translate(r.center())
        # Sombra (sin girar).
        p.save()
        p.scale(lado, lado)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 45)))
        p.drawEllipse(QPointF(0.0, 0.47), 0.22, 0.03)
        p.restore()
        p.rotate(ladeo)
        p.scale(lado, lado * max(0.5, math.cos(math.radians(max(-60.0, min(60.0, cabeceo))))))
        color = QColor(v.color)
        if c.tipo == "beber":
            _pintar_batido(p, color, v.id)
        else:
            _pintar_pastel(p, color, v.id)
    finally:
        p.restore()
    return True


# ── Ventana que sigue al cursor ─────────────────────────────────────────────────
class ComidaCursor(QWidget):
    """La comida flotando en el cursor (ver la cabecera del módulo)."""

    MARGEN = 1.6                 # lado de la ventana / lado del dibujo (sitio para girar)

    def __init__(self, parent: Optional[QWidget] = None, *, reloj: Callable[[], float] = time.monotonic):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reloj = reloj
        self.id = ""
        self.variante = ""
        self.tam = TAM_SIN_ASISTENTE
        self.escala = 0.0
        self.fase = ""                           # aparece | quieta | guarda | ""
        self._t0 = 0.0
        self._escala0 = 1.0
        self.balanceo = nc.BalanceoComida()
        self.ladeo = self.cabeceo = 0.0
        self._ultimo: Optional[QPoint] = None
        self._t_anim = QTimer(self)
        self._t_anim.setInterval(TIC_MS)
        self._t_anim.timeout.connect(self._tic_anim)

    @property
    def animando(self) -> bool:
        return self.fase in ("aparece", "guarda")

    def mostrar(self, id_: str, variante: str, tam_px: int, centro: Optional[QPoint] = None) -> None:
        """Aparece (0.25 s) con `id_`/`variante` y `tam_px` px de lado, en `centro`
        (por defecto, el cursor). Si ya estaba, vuelve a aparecer con la nueva."""
        self.id, self.variante = str(id_), str(variante)
        self.tam = max(16, int(tam_px))
        lado = int(math.ceil(self.tam * self.MARGEN))
        self.resize(lado, lado)
        self.balanceo.reiniciar()
        self.ladeo = self.cabeceo = 0.0
        self._t_anim.stop()
        self.fase = "aparece"
        self._t0 = self._reloj()
        self.escala = 0.0
        c = centro if centro is not None else QCursor.pos()
        self._ultimo = QPoint(c)
        self._centrar(c)
        self.show()
        self.raise_()
        self.update()

    def ocultar(self, animado: bool = True) -> None:
        """Se guarda: encoge en 0.2 s (con su propio timer) o de golpe."""
        if not animado or not self.isVisible():
            self._t_anim.stop()
            self.fase = ""
            self.escala = 0.0
            self.hide()
            return
        self.fase = "guarda"
        self._t0 = self._reloj()
        self._escala0 = self.escala if self.escala > 0 else 1.0
        self._t_anim.start()

    def paso(self, dt: float, cursor: QPoint) -> None:
        """Un paso del bucle de 16 ms: sigue al cursor (centrada, sin suavizado),
        balanceo con lo que se movió y la escala de aparecer."""
        if self.fase == "guarda" or not self.isVisible():
            return
        c = QPoint(cursor)
        antes = self._ultimo if self._ultimo is not None else c
        self.ladeo, self.cabeceo = self.balanceo.paso(dt, c.x() - antes.x(), c.y() - antes.y())
        self._ultimo = c
        self._avanzar_escala()
        self._centrar(c)
        self.update()

    def _centrar(self, c: QPoint) -> None:
        self.move(int(c.x() - self.width() / 2), int(c.y() - self.height() / 2))

    def _avanzar_escala(self) -> None:
        t = self._reloj()
        if self.fase == "aparece":
            k = (t - self._t0) / nc.APARECER_S
            if k >= 1.0:
                self.fase, self.escala = "quieta", 1.0
            else:
                k = max(0.0, k)
                self.escala = 1.0 - (1.0 - k) ** 2           # sale rápido y frena
        elif self.fase == "guarda":
            k = (t - self._t0) / nc.GUARDAR_S
            if k >= 1.0:
                self._t_anim.stop()
                self.fase, self.escala = "", 0.0
                self.hide()
            else:
                self.escala = self._escala0 * (1.0 - max(0.0, k))

    def _tic_anim(self) -> None:
        self._avanzar_escala()
        self.update()

    def paintEvent(self, _ev) -> None:                          # noqa: N802 (Qt)
        if not self.id or self.escala <= 0.0:
            return
        p = QPainter(self)
        try:
            lado = float(self.tam)
            r = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
            pintar_comida(p, self.id, self.variante, r, self.ladeo, self.cabeceo, self.escala)
        finally:
            p.end()


# ── Controlador ─────────────────────────────────────────────────────────────────
def _llamar(obj: Any, metodo: str, *args) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("comida: %s.%s falló", type(obj).__name__, metodo)
        return None


def _visible(m: Any) -> bool:
    if m is None or getattr(m, "cerrado", False):
        return False
    try:
        return bool(m.isVisible())
    except Exception:
        return False


class ControlComida(QObject):
    """Controlador de la comida (ver la cabecera del módulo)."""

    cambio = pyqtSignal(str)
    comida_web = pyqtSignal(str)

    TIC_MS = TIC_MS

    def __init__(self, escritorio: Any, config: Any, *, anfitrion: Any = None, mezclador: Any = None,
                 fabrica_cursor: Callable[[], Any] = ComidaCursor, azar: Any = None,
                 reloj: Callable[[], float] = time.monotonic, en_ui: Optional[Callable] = None,
                 parent: Optional[QObject] = None, cursor_pos: Optional[Callable[[], QPoint]] = None,
                 lanzar_sonido: Optional[Callable[[Callable[[], None]], Any]] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.anfitrion = anfitrion
        self._fabrica_cursor = fabrica_cursor
        self._reloj = reloj
        self._en_ui = en_ui
        self._cursor_pos = cursor_pos or QCursor.pos
        self.gestor = nc.GestorComida(azar=azar, reloj=reloj)
        self.sonidos = nc.SonidosComida(config, mezclador=mezclador, lanzar=lanzar_sonido,
                                        en_juego=self._en_juego, azar=azar)
        self._cursor: Any = None
        self._asistente: Any = None
        self._con_comida: Any = None          # la asistente a la que se dijo set_comida_activa(True)
        self._vista = ""
        self._iniciado = False
        self._bus_conectado = False
        self._prioridad_mia = False          # la comida en la mano sostiene la actividad
        self._directo = False                # comer_directo la sostiene durante la reacción
        self._ult_pos: Optional[QPoint] = None
        self._t_ult: Optional[float] = None
        self._cabeza: Optional[Tuple[float, float, float]] = None
        self._t_cabeza = -math.inf
        self._gen_cabeza = 0
        self._ultimo_estado = ""
        self.ultimo_motivo = ""
        self._timer = QTimer(self)
        self._timer.setInterval(TIC_MS)
        self._timer.timeout.connect(self.paso)
        self._t_directo = QTimer(self)
        self._t_directo.setSingleShot(True)
        self._t_directo.timeout.connect(self._fin_directo)

    # ── Lo compartido ────────────────────────────────────────────────────────────
    def _bus(self) -> Any:
        return getattr(self.escritorio, "estado", None)

    def _estado_bus(self) -> Any:
        bus = self._bus()
        try:
            return bus.actual() if bus is not None else None
        except Exception:
            return None

    def _en_juego(self) -> bool:
        est = self._estado_bus()
        return bool(est is not None and getattr(est, "juego", False))

    def _prioridad(self) -> Any:
        return getattr(self.escritorio, "prioridad", None)

    def _habilitada(self) -> bool:
        return nc.comida_habilitada(self.config)

    def _modo(self) -> str:
        return str(getattr(self.anfitrion, "modo", "") or "")

    def _asistente_vista(self) -> Any:
        m = self._asistente if self._asistente is not None else getattr(self.escritorio, "asistente", None)
        return m if _visible(m) else None

    @property
    def activa(self) -> Optional[Tuple[str, str]]:
        """(id, variante) de la comida en la mano, o None."""
        return self.gestor.activa

    @property
    def ultima(self) -> str:
        """La última comida que salió ("" si ninguna)."""
        return self.gestor.ultima

    @property
    def vista(self) -> str:
        return self._vista

    # ── Ciclo de vida (contrato de ServiciosEscritorio) ─────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and not self._bus_conectado:
            try:
                senal.connect(self._on_bus)
                self._bus_conectado = True
            except (TypeError, RuntimeError):
                pass

    def detener(self) -> None:
        self._guardar(sonido=False, animado=False)
        self._fin_directo()
        self._timer.stop()
        self._t_directo.stop()
        if self._bus_conectado:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._bus_conectado = False
        cur, self._cursor = self._cursor, None
        if cur is not None:
            _llamar(cur, "ocultar", False)
            _llamar(cur, "close")
            _llamar(cur, "deleteLater")
        self._iniciado = False
        self._emitir_estado()

    def set_asistente(self, v: Any) -> None:
        anterior, self._asistente = self._asistente, v
        if v is not anterior:
            self._cabeza = None
            self._t_cabeza = -math.inf
            self._gen_cabeza += 1
        if self.gestor.activa is None:
            return
        if self._vista == "escritorio":
            if not _visible(v):
                self._guardar(sonido=False)
                self._emitir_estado()
            else:
                self._comida_en_asistente(True)
        elif self._vista == "web" and _visible(v):
            self._pasar_a_escritorio()

    def ceder(self, c: Any = None) -> None:
        """La tabla le quita la comida (juego, alarma, grande…): se guarda sin
        sonido. La actividad ya está apagada: no se termina otra vez."""
        self._t_directo.stop()
        self._directo = False
        self._guardar(sonido=False, terminar=False)
        self._emitir_estado()

    def reanudar(self, c: Any = None) -> None:
        """La comida no es reanudable (un batido a medias se cancela)."""
        if self.gestor.activa is None and not self._directo:
            pr = self._prioridad()
            if pr is not None:
                _llamar(pr, "terminar", "comida")

    def recargar_config(self) -> None:
        if not self._habilitada() and self.gestor.activa is not None:
            self._guardar(sonido=False)
        self._emitir_estado()

    # ── Órdenes ──────────────────────────────────────────────────────────────────
    def alternar(self, id_: Any) -> str:
        """aparece | guarda | cambia; "" si no se pudo (motivo en `ultimo_motivo`)."""
        n = nc.normalizar_id(id_)
        if n is None:
            self.ultimo_motivo = "desconocida"
            return ""
        act = self.gestor.activa
        if act is None:
            return self._aparecer(n)
        if act[0] == n:
            self.guardar()
            return nc.GUARDA
        self.gestor.mostrar(n)
        self.sonidos.aparecer(n)
        self._mostrar_vista(nc.CAMBIA)
        self._emitir_estado()
        return nc.CAMBIA

    def guardar(self, sonido: bool = True) -> bool:
        """Guarda la comida de la mano. True si había."""
        hecho = self._guardar(sonido=sonido)
        self._emitir_estado()
        return hecho

    def acierto_web(self, id_: Any) -> bool:
        """La página detectó el acierto sobre la asistente de la barra: la reacción común."""
        act = self.gestor.activa
        if act is None or self._vista != "web" or nc.normalizar_id(id_) != act[0]:
            return False
        if not self.gestor.acierto(self._reloj()):
            return False
        self._reaccionar(self.gestor.reaccion())
        return True

    def comer_directo(self, id_: Any) -> str:
        """dar_de_comer: la reacción sin comida en el cursor. Devuelve el texto
        («*glup glup* (batido de fresa)») o "" si no se pudo (`ultimo_motivo`)."""
        n = nc.normalizar_id(id_)
        if n is None:
            self.ultimo_motivo = "desconocida"
            return ""
        if not self._habilitada():
            self.ultimo_motivo = "desactivada"
            return ""
        act = self.gestor.activa
        if act is None:
            pr = self._prioridad()
            if pr is not None:
                r = pr.iniciar("comida")
                if not r:
                    self.ultimo_motivo = str(getattr(r, "motivo", "") or "")
                    return ""
            self._directo = True
            self._t_directo.start(nc.MS_REACCION)
        self.ultimo_motivo = ""
        reac = self.gestor.reaccion(n, act[1] if act is not None and act[0] == n else None)
        self._reaccionar(reac)
        self._emitir_estado()
        return reac.texto

    # ── Consultas ────────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        act = self.gestor.activa
        c = nc.CATALOGO.get(act[0]) if act else None
        v = nc.variante_de(act[0], act[1]) if act else None
        return {
            "activa": act is not None,
            "id": act[0] if act else "",
            "variante": act[1] if act else "",
            "color": v.color if v else "",
            "tipo": c.tipo if c else "",
            "vista": self._vista if act else "",
            "disponible": self._habilitada(),
        }

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["comida"] = self
        if self._en_ui is not None:
            base["en_ui"] = self._en_ui
        return base

    def herramientas(self) -> dict:
        """{"dar_de_comer": handler(args, ctx)}."""
        return {"dar_de_comer": lambda args=None, ctx=None: nc.herramienta(args, self._ctx(ctx))}

    # ── Bucle de 16 ms (solo con comida en el escritorio) ────────────────────────
    def paso(self) -> None:
        """Un paso: mover y balancear, la cabeza a 10 Hz, el acierto y D4."""
        if self.gestor.activa is None or self._vista != "escritorio":
            self._timer.stop()
            return
        t = self._reloj()
        try:
            pos = QPoint(self._cursor_pos())
        except Exception:
            return
        dt = (t - self._t_ult) if self._t_ult is not None else TIC_MS / 1000.0
        antes = self._ult_pos if self._ult_pos is not None else pos
        if self._cursor is not None:
            _llamar(self._cursor, "paso", max(0.0, dt), pos)
        if t - self._t_cabeza >= CABEZA_S:
            self._pedir_cabeza(t)
        self._ult_pos, self._t_ult = pos, t
        if self.gestor.al_mover(t, (antes.x(), antes.y()), (pos.x(), pos.y()), self._cabeza):
            self._reaccionar(self.gestor.reaccion())
        if self.gestor.caducada(t):
            self.guardar()

    def _pedir_cabeza(self, t: float) -> None:
        self._t_cabeza = t
        m = self._asistente_vista()
        f = getattr(m, "cabeza", None) if m is not None else None
        if not callable(f):
            self._cabeza = None
            return
        gen = self._gen_cabeza

        def cb(res: Any = None) -> None:
            if gen == self._gen_cabeza:
                self._cabeza = nc.cabeza_valida(res) if res is not None else None
        try:
            f(cb)
        except Exception:
            _log.debug("comida: la asistente no dio la cabeza", exc_info=True)

    # ── Internos ─────────────────────────────────────────────────────────────────
    def _aparecer(self, n: str) -> str:
        if not self._habilitada():
            self.ultimo_motivo = "desactivada"
            _llamar(self.anfitrion, "aviso", "La comida está desactivada (Ajustes → Comida).")
            return ""
        pr = self._prioridad()
        if pr is not None:
            r = pr.iniciar("comida")
            if not r:
                self.ultimo_motivo = str(getattr(r, "motivo", "") or "")
                motivo = nc.motivo_legible(self.ultimo_motivo)
                _llamar(self.anfitrion, "aviso", "Ahora no puedo comer" + (f": {motivo}." if motivo else "."))
                return ""
        self.ultimo_motivo = ""
        self._prioridad_mia = True
        if self._directo:                         # la reacción directa pasa a ser de la comida
            self._t_directo.stop()
            self._directo = False
        self.gestor.mostrar(n)
        self._vista = self._elegir_vista()
        self.sonidos.aparecer(n)
        self._mostrar_vista(nc.APARECE)
        self._comida_en_asistente(True)
        self._emitir_estado()
        return nc.APARECE

    def _elegir_vista(self) -> str:
        if self._asistente_vista() is not None:
            return "escritorio"
        if self._modo() == "normal":
            return "web"
        f = getattr(self.anfitrion, "alternar_asistente", None)
        if callable(f):
            try:
                f()                               # la nativa saca a la asistente primero
            except Exception:
                _log.exception("comida: no pude sacar a la asistente")
        return "escritorio"

    def _tam_px(self) -> int:
        m = self._asistente_vista()
        try:
            ancho = float(m.width()) if m is not None else 0.0
        except Exception:
            ancho = 0.0
        if ancho <= 0.0:
            return TAM_SIN_ASISTENTE
        return int(max(TAM_MIN, min(TAM_MAX, round(TAM_FRACCION * ancho))))

    def _mostrar_vista(self, accion: str) -> None:
        act = self.gestor.activa
        if act is None:
            return
        if self._vista == "web":
            self._emitir_web(accion, act)
            return
        if self._cursor is None:
            try:
                self._cursor = self._fabrica_cursor()
            except Exception:
                _log.exception("comida: no pude crear la ventana de la comida")
                self._cursor = None
        pos = None
        try:
            pos = QPoint(self._cursor_pos())
        except Exception:
            pass
        if self._cursor is not None:
            _llamar(self._cursor, "mostrar", act[0], act[1], self._tam_px(), pos)
        self._ult_pos, self._t_ult = pos, None
        self._timer.start()

    def _pasar_a_escritorio(self) -> None:
        """Con la comida en la web aparece la asistente flotante: la comida sale al escritorio."""
        act = self.gestor.activa
        if act is None:
            return
        self._emitir_web(nc.GUARDA, act)
        self._vista = "escritorio"
        self._mostrar_vista(nc.APARECE)
        self._comida_en_asistente(True)
        self._emitir_estado()

    def _guardar(self, *, sonido: bool, terminar: bool = True, animado: bool = True) -> bool:
        act = self.gestor.activa
        if act is None:
            return False
        vista = self._vista
        self.gestor.guardar()
        self._timer.stop()
        self._vista = ""
        self._cabeza = None
        self._ult_pos = self._t_ult = None
        if vista == "escritorio" and self._cursor is not None:
            _llamar(self._cursor, "ocultar", animado)
        elif vista == "web":
            self._emitir_web(nc.GUARDA, act)
        if sonido:
            self.sonidos.guardar()
        self._comida_en_asistente(False)
        if self._prioridad_mia and terminar:
            pr = self._prioridad()
            if pr is not None:
                _llamar(pr, "terminar", "comida")
        self._prioridad_mia = False
        return True

    def _comida_en_asistente(self, on: bool) -> None:
        """`asistente.set_comida_activa(on)` una sola vez por asistente. Si la asistente
        cambió, la vieja la suelta (en silencio si ya se destruyó)."""
        if on:
            m = self._asistente_vista()
            if m is None or m is self._con_comida:
                return
            if self._con_comida is not None:
                self._soltar_en(self._con_comida)
            _llamar(m, "set_comida_activa", True)
            self._con_comida = m
            return
        m, self._con_comida = self._con_comida, None
        m = m if m is not None else self._asistente_vista()
        if m is not None:
            self._soltar_en(m)

    @staticmethod
    def _soltar_en(m: Any) -> None:
        try:
            m.set_comida_activa(False)
        except (AttributeError, RuntimeError):
            pass                                  # sin el método o ya destruida
        except Exception:
            _log.exception("comida: la asistente no soltó la comida")

    def _fin_directo(self) -> None:
        """Acabó la reacción de `comer_directo`: suelta la actividad si no hay comida en la mano."""
        self._t_directo.stop()
        if not self._directo:
            return
        self._directo = False
        if self.gestor.activa is None:
            pr = self._prioridad()
            if pr is not None:
                _llamar(pr, "terminar", "comida")
        self._emitir_estado()

    def _reaccionar(self, r: nc.Reaccion) -> None:
        m = self._asistente_vista()
        if m is not None and callable(getattr(m, "comer", None)):
            _llamar(m, "comer", r.tipo, r.ms)
        elif self._vista != "web":                 # en la web la página ya pone la cara
            _llamar(self.anfitrion, "reaccion", r.estado, r.ms)
        self.sonidos.reaccion(r)
        bus = self._bus()
        if bus is not None:
            try:
                bus.actualizar(emocion=r.estado)
            except Exception:
                pass

    def _on_bus(self, estado: Any = None, cambios: Any = None) -> None:
        if self.gestor.activa is None or not isinstance(cambios, dict) or "visible" not in cambios:
            return
        visible = bool(getattr(estado, "visible", False))
        if self._vista == "escritorio":
            if not visible:
                self._guardar(sonido=False)
                self._emitir_estado()
            else:
                self._comida_en_asistente(True)       # la nativa la sacó y ya se ve
        elif self._vista == "web" and visible and self._asistente_vista() is not None:
            self._pasar_a_escritorio()

    def _emitir_web(self, accion: str, act: Tuple[str, str]) -> None:
        c = nc.CATALOGO.get(act[0])
        v = nc.variante_de(act[0], act[1])
        datos: Dict[str, Any] = {"accion": accion, "id": act[0], "variante": act[1],
                                 "color": v.color if v else "", "tipo": c.tipo if c else "",
                                 "nombre": c.nombre if c else ""}
        self.comida_web.emit(json.dumps(datos, ensure_ascii=False))

    def _emitir_estado(self) -> None:
        txt = json.dumps(self.estado(), ensure_ascii=False, sort_keys=True)
        if txt != self._ultimo_estado:
            self._ultimo_estado = txt
            self.cambio.emit(txt)


__all__ = ("pintar_comida", "ComidaCursor", "ControlComida", "TIC_MS", "CABEZA_S")
