"""
ui/menu_radial.py — Menú radial de la mascota (CircleSelector / MenuActions de Mate-Engine).

Se abre con el clic derecho sobre la mascota (se abre al SOLTAR), con el atajo
global «menu_radial» o desde la bandeja; en la web hay una versión SVG aparte
(extra/apariencia.jsx) que usa la MISMA geometría: `indice()` de aquí y
`window.LuneRadial.indice` de la web deben dar lo mismo (test de paridad).

Geometría (la de Mate-Engine, lienzo de 368 px):
    - zona muerta / anillo interior de 85 px: dentro no se elige nada;
    - iconos a 120 px del centro; anillo exterior de 165 px;
    - de 1 a 10 botones. El botón i ocupa el sector [i·360/n, (i+1)·360/n) en
      grados medidos EN SENTIDO HORARIO DESDE LAS 12 (y de pantalla hacia abajo),
      y su icono va en el centro del sector, (i+0.5)·360/n. Es la disposición
      de CircleSelector.BuildButtons (bRot = previa + relleno/2).
      Tabla (n=4): arriba-derecha 0, abajo-derecha 1, abajo-izquierda 2,
      arriba-izquierda 3; exactamente a las 12 → 0, a las 3 → 1.
Sensación (CircleSelector.Update): al abrir crece desde 0 con lerp 0.2 por
frame; el arco del cursor gira y los colores cambian con lerp 0.54; el botón
señalado se pinta con el color de fondo sobre el arco de acento; al pulsar se
encoge a 0.8 y al SOLTAR se ejecuta; soltar en la zona muerta cierra. Los lerps
van normalizados por dt (`factor_lerp`) para que no dependan de los fps. Con la
mascota a la vista el menú sigue a su cabeza (MenuActions.followBone).

Cierre: Esc, clic derecho o central, clic fuera (Qt.Popup) o perder el foco.
Mientras está abierto: BusEstado.menu_abierto=True y mascota.set_menu_abierto(True)
(sin arrastre, caricias ni sueño). Sonidos menu_abrir / menu_cerrar / menu_boton.
Orden de señales al elegir: primero `cerrado` (se sueltan los bloqueos) y luego
`elegido(id, arg)`: así «Dormir» no choca con el bloqueo de sueño del menú.
"""
from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from nucleo import acciones_ui
from nucleo.acciones_ui import ItemRadial

_log = logging.getLogger("lune.menu_radial")

# ── Geometría (pura) ─────────────────────────────────────────────────────────────
LIENZO = 368
ZONA_MUERTA = 85.0
RADIO_ICONOS = 120.0
RADIO_EXTERIOR = 165.0
MAX_BOTONES = acciones_ui.MAX_RADIAL

LERP_ESCALA = 0.2        # CircleSelector: localScale → Size
LERP_ARCO = 0.54         # arco del cursor y colores de los botones
LERP_CIERRE = 0.3        # al cerrar, algo más rápido (el popup aún captura el ratón)
LERP_SEGUIR = 0.85       # MenuActions: 1 - followSmoothness (0.15)
ESCALA_PULSADO = 0.8
TAM_ICONO = 30


def angulo(dx: float, dy: float) -> float:
    """Ángulo en grados, en sentido horario desde las 12, en [0, 360). `dy` crece
    hacia abajo (coordenadas de pantalla)."""
    a = math.degrees(math.atan2(dx, -dy)) % 360.0
    return 0.0 if a >= 360.0 else a


def indice(dx: float, dy: float, n: int, zona_muerta: float = ZONA_MUERTA) -> Optional[int]:
    """Botón señalado por el punto (dx, dy) relativo al centro, o None en la zona
    muerta (distancia <= zona_muerta) o si no hay botones. Sin límite exterior:
    como en ME, lejos del menú sigue valiendo la dirección."""
    try:
        n = int(n)
        dx, dy, zona_muerta = float(dx), float(dy), float(zona_muerta)
    except (TypeError, ValueError, OverflowError):
        return None
    if n < 1 or not (math.isfinite(dx) and math.isfinite(dy)) or math.hypot(dx, dy) <= zona_muerta:
        return None
    sector = 360.0 / n
    return min(int(angulo(dx, dy) // sector), n - 1)


def centro_sector(i: int, n: int) -> float:
    """Ángulo (horario desde las 12) del centro del botón i de n."""
    return (i + 0.5) * 360.0 / max(1, n)


def posiciones(n: int, radio: float = RADIO_ICONOS) -> List[Tuple[float, float]]:
    """Centro de cada icono relativo al centro del menú (x a la derecha, y abajo)."""
    n = max(0, int(n))
    out = []
    for i in range(n):
        a = math.radians(centro_sector(i, n))
        out.append((radio * math.sin(a), -radio * math.cos(a)))
    return out


def factor_lerp(base: float, dt: float, fps_ref: float = 60.0) -> float:
    """Lerp «por frame» de Unity normalizado por tiempo: con dt = 1/fps_ref da
    `base`; con el doble de dt, lo que harían dos frames. Siempre en [0, 1]."""
    base = min(max(float(base), 0.0), 1.0)
    dt = max(0.0, float(dt))
    if base >= 1.0:
        return 1.0
    return 1.0 - (1.0 - base) ** (dt * float(fps_ref))


# ── Colores ──────────────────────────────────────────────────────────────────────
COLORES_DEFECTO: Dict[str, str] = {
    "fondo": "#0B0F1EEB",          # ink-850 casi opaco (CSS #RRGGBBAA)
    "borde": "#2E3D66",            # ink-400
    "acento": "#00E5FF",           # cyan-500 (el tema lo rota)
    "acento_2": "#1E55FF",         # blue-500
    "texto": "#EAF1FF",            # paper
    "deshabilitado": "#4B5878",    # gray-500
    "separador": "#1B2440",        # ink-600
}
# Nombres que se aceptan en set_colores: los de ui/tema_qss.colores_radial (acento,
# acento_oscuro = borde del anillo, secundario, fondo, fondo_borde, texto,
# deshabilitado…) y alias. El primero que venga en `c` gana.
_ALIAS_COLOR = {
    "fondo": ("fondo", "background", "bg", "fondo_menu", "superficie"),
    "borde": ("borde", "border", "anillo", "acento_oscuro", "fondo_borde"),
    "acento": ("acento", "accent", "cyan", "cursor", "primario"),
    "acento_2": ("acento_2", "accent_2", "azul", "blue", "secundario"),
    "texto": ("texto", "text", "etiqueta"),
    "deshabilitado": ("deshabilitado", "disabled", "apagado"),
    "separador": ("separador", "separator", "divisor", "fondo_borde"),
}
ALFA_FONDO = 0xEB          # el anillo deja entrever el escritorio si el tema lo da opaco


def color_de(valor: Any, respaldo: str = "#FFFFFF") -> QColor:
    """QColor de "#RGB", "#RRGGBB", "#RRGGBBAA" (orden CSS), "rgb(r g b / a)",
    "rgba(r, g, b, a)", un QColor o una tupla. Si no se entiende, `respaldo`."""
    if isinstance(valor, QColor):
        return QColor(valor)
    if isinstance(valor, (tuple, list)) and 3 <= len(valor) <= 4:
        try:
            c = [int(v) for v in valor[:3]]
            a = valor[3] if len(valor) == 4 else 255
            a = int(round(float(a) * 255)) if isinstance(a, float) and a <= 1 else int(a)
            return QColor(*c, max(0, min(255, a)))
        except (TypeError, ValueError):
            return QColor(respaldo)
    s = str(valor or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{8})", s)
    if m:
        h = m.group(1)
        return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)", s)
    if m:
        r, g, b = (max(0, min(255, int(float(x)))) for x in m.groups()[:3])
        a = m.group(4)
        if a is None:
            alfa = 255
        elif a.endswith("%"):
            alfa = int(round(float(a[:-1]) * 2.55))
        else:
            f = float(a)
            alfa = int(round(f * 255)) if f <= 1 else int(f)
        return QColor(r, g, b, max(0, min(255, alfa)))
    c = QColor(s)
    return c if c.isValid() else QColor(respaldo)


def normalizar_colores(c: Optional[dict]) -> Dict[str, QColor]:
    """Mezcla `c` (con alias) sobre COLORES_DEFECTO → {clave: QColor}."""
    out = {k: color_de(v) for k, v in COLORES_DEFECTO.items()}
    if isinstance(c, dict):
        for clave, alias in _ALIAS_COLOR.items():
            for a in alias:
                if a in c and c[a]:
                    out[clave] = color_de(c[a], COLORES_DEFECTO[clave])
                    if clave == "fondo" and out[clave].alpha() == 255:
                        out[clave].setAlpha(ALFA_FONDO)
                    break
    return out


def _mezcla(a: QColor, b: QColor, t: float) -> QColor:
    t = min(max(t, 0.0), 1.0)
    return QColor(int(round(a.red() + (b.red() - a.red()) * t)),
                  int(round(a.green() + (b.green() - a.green()) * t)),
                  int(round(a.blue() + (b.blue() - a.blue()) * t)),
                  int(round(a.alpha() + (b.alpha() - a.alpha()) * t)))


def _dist_color(a: QColor, b: QColor) -> int:
    return max(abs(a.red() - b.red()), abs(a.green() - b.green()),
               abs(a.blue() - b.blue()), abs(a.alpha() - b.alpha()))


# ── Widget ───────────────────────────────────────────────────────────────────────

class MenuRadial(QWidget):
    """El menú radial (Qt.Popup translúcido de 368 px). Ver el docstring del módulo."""

    elegido = pyqtSignal(str, str)      # (id, arg)
    cerrado = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *, colores: Optional[dict] = None,
                 traer_al_frente: Optional[Callable[[int], Any]] = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(LIENZO, LIENZO)
        self.setWindowTitle("Lune · menú")
        self._traer = traer_al_frente
        self._col = normalizar_colores(colores)
        self._items: List[ItemRadial] = []
        self._abierto = False
        self._cerrando = False
        self._fue_activo = False
        self._sel: Optional[int] = None
        self._pulsado = False
        self._escala = 0.0
        self._arco: Optional[float] = None          # ángulo actual del arco (grados)
        self._arco_alfa = 0.0
        self._cols: List[QColor] = []                # color actual de cada icono
        self._esc_btn: List[float] = []              # escala actual de cada icono
        self._pos_f: Optional[Tuple[float, float]] = None   # esquina sup-izq (float) al seguir
        self._objetivo: Optional[QPoint] = None      # centro global al que seguir
        self._mascaras: Dict[str, QPixmap] = {}
        self.ultimo_por_eleccion = False             # el último cierre fue por elegir un botón
        self._t = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._paso)

    # ── API ────────────────────────────────────────────────────────────────
    @property
    def abierto(self) -> bool:
        return self._abierto

    @property
    def items(self) -> List[ItemRadial]:
        return list(self._items)

    @property
    def seleccion(self) -> Optional[int]:
        return self._sel

    def centro_global(self) -> QPoint:
        return self.mapToGlobal(QPoint(LIENZO // 2, LIENZO // 2))

    def abrir(self, centro: QPoint, items: Sequence[ItemRadial]) -> bool:
        """Abre el menú centrado en `centro` (coordenadas globales). False sin botones."""
        lista = [i for i in (items or ()) if isinstance(i, ItemRadial)][:MAX_BOTONES]
        if not lista:
            return False
        self._items = lista
        self._abierto, self._cerrando, self._pulsado = True, False, False
        self._fue_activo = False
        self.ultimo_por_eleccion = False
        self._sel, self._arco, self._arco_alfa = None, None, 0.0
        self._escala = 0.0
        self._cols = [QColor(self._color_reposo(it)) for it in lista]
        self._esc_btn = [1.0] * len(lista)
        self._objetivo = None
        self._pos_f = None
        self._colocar(QPoint(centro))
        self.show()
        self.raise_()
        self.activateWindow()
        if self._traer is not None:
            try:
                self._traer(int(self.winId()))
            except Exception:
                _log.debug("traer_al_frente falló", exc_info=True)
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self._actualizar_sel(self.mapFromGlobal(QCursor.pos()))
        self._despertar()
        return True

    def cerrar(self) -> None:
        """Cierra (animación de salida). Emite `cerrado` en el acto."""
        if not self._abierto:
            return
        self._abierto = False
        self._cerrando = True
        self._pulsado = False
        self.cerrado.emit()
        if self.isVisible():
            self._despertar()
        else:
            self._cerrando = False

    def set_colores(self, c: Optional[dict]) -> None:
        self._col = normalizar_colores(c)
        self._despertar()
        self.update()

    def seguir(self, centro: QPoint) -> None:
        """Nuevo centro global al que deslizarse (la cabeza de la mascota)."""
        if not self._abierto or centro is None:
            return
        self._objetivo = QPoint(centro)
        self._despertar()

    # ── Internos: posición y selección ─────────────────────────────────────
    def _limites(self, centro: QPoint):
        pantalla = QGuiApplication.screenAt(centro) or QGuiApplication.primaryScreen()
        return pantalla.availableGeometry() if pantalla is not None else None

    def _esquina_para(self, centro: QPoint) -> Tuple[float, float]:
        x, y = centro.x() - LIENZO / 2, centro.y() - LIENZO / 2
        g = self._limites(centro)
        if g is not None and g.width() >= LIENZO and g.height() >= LIENZO:
            x = min(max(x, g.left()), g.right() + 1 - LIENZO)
            y = min(max(y, g.top()), g.bottom() + 1 - LIENZO)
        return float(x), float(y)

    def _colocar(self, centro: QPoint) -> None:
        x, y = self._esquina_para(centro)
        self._pos_f = (x, y)
        self.move(int(round(x)), int(round(y)))

    def _actualizar_sel(self, p) -> None:
        if not self._abierto or not self._items:
            return
        dx = float(p.x()) - LIENZO / 2
        dy = float(p.y()) - LIENZO / 2
        i = indice(dx, dy, len(self._items))
        self._poner_sel(i)

    def _poner_sel(self, i: Optional[int]) -> None:
        if i == self._sel:
            return
        self._sel = i
        if i is not None and self._arco is None:
            self._arco = centro_sector(i, len(self._items))
        self._despertar()

    def _elegir(self) -> None:
        if not self._abierto or self._sel is None or self._sel >= len(self._items):
            return
        it = self._items[self._sel]
        if not it.habilitado:
            self.cerrar()                       # ME: bloqueado → no ejecuta, pero cierra
            return
        self.ultimo_por_eleccion = True
        self.cerrar()
        self.elegido.emit(it.id, it.arg)

    def _color_reposo(self, it: ItemRadial) -> QColor:
        return self._col["acento"] if it.habilitado else self._col["deshabilitado"]

    # ── Eventos ────────────────────────────────────────────────────────────
    def mouseMoveEvent(self, ev):
        if self._abierto:
            self._actualizar_sel(ev.position())
        ev.accept()

    def mousePressEvent(self, ev):
        if not self._abierto:
            ev.accept()
            return
        b = ev.button()
        if b == Qt.MouseButton.LeftButton:
            self._actualizar_sel(ev.position())
            self._pulsado = True
            self._despertar()
        elif b in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self.cerrar()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._abierto and ev.button() == Qt.MouseButton.LeftButton and self._pulsado:
            self._pulsado = False
            self._actualizar_sel(ev.position())
            if self._sel is None:
                self.cerrar()                   # soltar en la zona muerta cierra
            else:
                self._elegir()
        ev.accept()

    def keyPressEvent(self, ev):
        if not self._abierto:
            ev.accept()
            return
        k = ev.key()
        n = len(self._items)
        if k == Qt.Key.Key_Escape:
            self.cerrar()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab) and n:
            self._poner_sel(0 if self._sel is None else (self._sel + 1) % n)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backtab) and n:
            self._poner_sel(n - 1 if self._sel is None else (self._sel - 1) % n)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._elegir()
        ev.accept()

    def event(self, ev):
        t = ev.type()
        if t == QEvent.Type.WindowActivate:
            self._fue_activo = True
        elif t == QEvent.Type.WindowDeactivate:
            if self._abierto and self._fue_activo:
                self.cerrar()
        return super().event(ev)

    def hideEvent(self, ev):
        # Qt cierra el popup solo (clic fuera): cuenta como cerrar sin elegir.
        self._timer.stop()
        self._cerrando = False
        if self._abierto:
            self._abierto = False
            self._pulsado = False
            self.cerrado.emit()
        super().hideEvent(ev)

    # ── Animación ──────────────────────────────────────────────────────────
    def _despertar(self) -> None:
        if not self._timer.isActive():
            self._t = time.monotonic()
            self._timer.start()

    def _paso(self, dt: Optional[float] = None) -> None:
        ahora = time.monotonic()
        if dt is None:
            dt = min(max(ahora - self._t, 1 / 240), 0.1)
        self._t = ahora
        quieto = True
        n = len(self._items)
        # Escala del conjunto
        if self._abierto:
            objetivo, f = 1.0, factor_lerp(LERP_ESCALA, dt)
        else:
            objetivo, f = 0.0, factor_lerp(LERP_CIERRE, dt)
        self._escala += (objetivo - self._escala) * f
        if abs(objetivo - self._escala) < 0.002:
            self._escala = objetivo
        else:
            quieto = False
        if self._cerrando and self._escala <= 0.03:
            self._cerrando = False
            self._timer.stop()
            self.hide()
            return
        fa = factor_lerp(LERP_ARCO, dt)
        # Arco del cursor (por el camino corto)
        if self._sel is not None and n:
            meta = centro_sector(self._sel, n)
            actual = meta if self._arco is None else self._arco
            dif = ((meta - actual + 180.0) % 360.0) - 180.0
            if abs(dif) < 0.05:
                self._arco = meta
            else:
                self._arco = (actual + dif * fa) % 360.0
                quieto = False
        alfa_meta = 1.0 if self._sel is not None else 0.0
        self._arco_alfa += (alfa_meta - self._arco_alfa) * fa
        if abs(alfa_meta - self._arco_alfa) < 0.01:
            self._arco_alfa = alfa_meta
        else:
            quieto = False
        # Colores y escala de cada botón
        for i, it in enumerate(self._items):
            if i == self._sel and it.habilitado:
                meta_c = self._col["fondo"]
            else:
                meta_c = self._color_reposo(it)
            meta_c = QColor(meta_c.red(), meta_c.green(), meta_c.blue(), 255)
            c = self._cols[i] if i < len(self._cols) else QColor(meta_c)
            nuevo = _mezcla(c, meta_c, fa)
            if _dist_color(nuevo, meta_c) <= 2:
                nuevo = meta_c
            else:
                quieto = False
            if i < len(self._cols):
                self._cols[i] = nuevo
            meta_e = ESCALA_PULSADO if (self._pulsado and i == self._sel and it.habilitado) else 1.0
            e = self._esc_btn[i] if i < len(self._esc_btn) else 1.0
            e += (meta_e - e) * fa
            if abs(meta_e - e) < 0.003:
                e = meta_e
            else:
                quieto = False
            if i < len(self._esc_btn):
                self._esc_btn[i] = e
        # Seguir a la cabeza
        if self._abierto and self._objetivo is not None and self._pos_f is not None:
            mx, my = self._esquina_para(self._objetivo)
            x, y = self._pos_f
            fs = factor_lerp(LERP_SEGUIR, dt)
            x += (mx - x) * fs
            y += (my - y) * fs
            if abs(mx - x) < 0.5 and abs(my - y) < 0.5:
                x, y = mx, my
            else:
                quieto = False
            self._pos_f = (x, y)
            if (int(round(x)), int(round(y))) != (self.x(), self.y()):
                self.move(int(round(x)), int(round(y)))
        self.update()
        if quieto and self._abierto:
            self._timer.stop()              # nada que animar: 0 % de CPU hasta el siguiente evento

    # ── Pintado ────────────────────────────────────────────────────────────
    def _mascara(self, nombre: str, px: int) -> QPixmap:
        clave = f"{nombre}@{px}"
        pm = self._mascaras.get(clave)
        if pm is None:
            try:
                from ui.icons import icon_pixmap
                pm = icon_pixmap(nombre, "#FFFFFF", px)
            except Exception:
                pm = QPixmap()
            self._mascaras[clave] = pm
        return pm

    @staticmethod
    def _tintar(mascara: QPixmap, color: QColor) -> QPixmap:
        pm = QPixmap(mascara.size())
        pm.setDevicePixelRatio(mascara.devicePixelRatio())
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.drawPixmap(0, 0, mascara)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(QRectF(0, 0, pm.width(), pm.height()), color)
        q.end()
        return pm

    @staticmethod
    def _sector(r_int: float, r_ext: float, desde: float, ancho: float) -> QPainterPath:
        """Trozo de anillo entre `desde` y `desde+ancho` (grados horarios desde las 12)."""
        ext = QRectF(-r_ext, -r_ext, 2 * r_ext, 2 * r_ext)
        inn = QRectF(-r_int, -r_int, 2 * r_int, 2 * r_int)
        inicio = 90.0 - desde                     # Qt: antihorario desde las 3
        camino = QPainterPath()
        camino.arcMoveTo(ext, inicio)
        camino.arcTo(ext, inicio, -ancho)
        camino.arcTo(inn, inicio - ancho, ancho)
        camino.closeSubpath()
        return camino

    def paintEvent(self, _ev):
        if self._escala <= 0.001 or not self._items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.translate(LIENZO / 2, LIENZO / 2)
        p.scale(self._escala, self._escala)
        p.setOpacity(min(1.0, self._escala * 1.25))
        n = len(self._items)
        sector = 360.0 / n
        col = self._col
        # Anillo de fondo
        anillo = QPainterPath()
        anillo.addEllipse(QPointF(0, 0), RADIO_EXTERIOR, RADIO_EXTERIOR)
        hueco = QPainterPath()
        hueco.addEllipse(QPointF(0, 0), ZONA_MUERTA, ZONA_MUERTA)
        anillo = anillo.subtracted(hueco)
        p.fillPath(anillo, col["fondo"])
        # Arco del cursor
        if self._arco is not None and self._arco_alfa > 0.01:
            it = self._items[self._sel] if self._sel is not None and self._sel < n else None
            c = QColor(col["acento"] if (it is None or it.habilitado) else col["deshabilitado"])
            c.setAlphaF(max(0.0, min(1.0, c.alphaF() * self._arco_alfa)))
            if n == 1:
                p.fillPath(anillo, c)
            else:
                p.fillPath(self._sector(ZONA_MUERTA, RADIO_EXTERIOR, self._arco - sector / 2, sector), c)
        # Separadores y bordes
        if n > 1:
            p.setPen(QPen(col["separador"], 1.5))
            for i in range(n):
                a = math.radians(i * sector)
                s, cs = math.sin(a), -math.cos(a)
                p.drawLine(QPointF(ZONA_MUERTA * s, ZONA_MUERTA * cs),
                           QPointF(RADIO_EXTERIOR * s, RADIO_EXTERIOR * cs))
        borde = QColor(col["borde"])
        p.setPen(QPen(borde, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), RADIO_EXTERIOR, RADIO_EXTERIOR)
        p.drawEllipse(QPointF(0, 0), ZONA_MUERTA, ZONA_MUERTA)
        # Iconos
        for i, ((x, y), it) in enumerate(zip(posiciones(n), self._items)):
            c = self._cols[i] if i < len(self._cols) else self._color_reposo(it)
            e = self._esc_btn[i] if i < len(self._esc_btn) else 1.0
            tam = TAM_ICONO * e
            masc = self._mascara(it.icono, TAM_ICONO)
            if not masc.isNull():
                p.drawPixmap(QRectF(x - tam / 2, y - tam / 2, tam, tam), self._tintar(masc, c),
                             QRectF(0, 0, masc.width(), masc.height()))
            else:                                  # sin icono: la inicial
                f = QFont(self.font())
                f.setPointSizeF(max(6.0, 13.0 * e))
                f.setBold(True)
                p.setFont(f)
                p.setPen(c)
                p.drawText(QRectF(x - tam / 2, y - tam / 2, tam, tam), int(Qt.AlignmentFlag.AlignCenter),
                           (it.etiqueta or it.id or "?")[:1].upper())
            if it.marcado:                         # interruptor encendido: punto
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(x, y + tam / 2 + 6), 2.5, 2.5)
                p.setBrush(Qt.BrushStyle.NoBrush)
        # Etiqueta del botón señalado en el centro
        if self._sel is not None and self._sel < n:
            it = self._items[self._sel]
            f = QFont(self.font())
            f.setPointSizeF(10.5)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(col["texto"] if it.habilitado else col["deshabilitado"])
            r = ZONA_MUERTA * 0.78
            p.drawText(QRectF(-r, -r, 2 * r, 2 * r),
                       int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), it.etiqueta)
        p.end()


# ── Controlador ──────────────────────────────────────────────────────────────────

def _llamar(obj: Any, metodo: str, *args) -> Any:
    f = getattr(obj, metodo, None) if obj is not None else None
    if not callable(f):
        return None
    try:
        return f(*args)
    except Exception:
        _log.exception("menu_radial: %s.%s falló", type(obj).__name__, metodo)
        return None


def _cfg(config: Any, seccion: str, clave: str, defecto: Any = None) -> Any:
    try:
        if hasattr(config, "get") and not isinstance(config, dict):
            return config.get(seccion, clave, defecto)
        return (config or {}).get(seccion, {}).get(clave, defecto)
    except Exception:
        return defecto


class ControlMenuRadial(QObject):
    """Abre el radial desde la mascota (`menu_pedido`), el atajo o la bandeja y
    lleva sus efectos: BusEstado.menu_abierto, mascota.set_menu_abierto, sonidos,
    seguir a la cabeza y ejecutar lo elegido por el Despachador."""

    ESPERA_ANCLA_MS = 350          # si la mascota no contesta dónde está su cabeza, al cursor
    SEGUIR_MS = 120                # cada cuánto se pregunta por la cabeza con el menú abierto

    def __init__(self, despachador, estado, config, contexto: Callable[[], Any], *,
                 colores: Optional[dict] = None, sonar: Optional[Callable[[str], Any]] = None,
                 parent: Optional[QObject] = None,
                 fabrica_menu: Optional[Callable[..., MenuRadial]] = None,
                 traer_al_frente: Optional[Callable[[int], Any]] = None):
        super().__init__(parent)
        self._desp = despachador
        self._estado = estado
        self._config = config
        self._contexto = contexto
        self._colores = dict(colores or {})
        self._sonar = sonar
        self._fabrica = fabrica_menu or MenuRadial
        self._traer = traer_al_frente
        self._menu: Optional[MenuRadial] = None
        self._mascota = None
        self._tipo = ""
        self._pendiente = 0               # ficha de la última petición de ancla
        self._esperando = False
        self._callado = False
        self._detenido = False
        self._seguir_t = QTimer(self)
        self._seguir_t.setInterval(self.SEGUIR_MS)
        self._seguir_t.timeout.connect(self._pedir_seguir)

    # ── Ciclo de vida (contrato de controlador de ServiciosEscritorio) ─────
    def iniciar(self) -> None:
        """El widget se crea al abrir por primera vez; aquí solo se vuelve a permitir abrir."""
        self._detenido = False

    def detener(self) -> None:
        """Cierra el radial (sin sonido) y borra el widget. La mascota sigue
        enlazada: si el escritorio se reanuda (iniciar), el clic derecho vuelve a
        funcionar sin esperar a otro set_mascota."""
        self._detenido = True
        self._esperando = False
        self._pendiente += 1
        self._seguir_t.stop()
        menu, self._menu = self._menu, None
        if menu is not None:
            self._callado = True               # al apagar no suena «menu_cerrar»
            try:
                if menu.abierto:
                    menu.cerrar()          # emite cerrado → suelta menu_abierto
                menu.hide()
                menu.deleteLater()
            except RuntimeError:
                pass
            finally:
                self._callado = False

    def set_mascota(self, v) -> None:
        if v is self._mascota:
            return
        abierto = self.abierto()
        self._soltar_mascota()
        self._mascota = v
        if v is not None:
            s = getattr(v, "menu_pedido", None)
            if s is not None and hasattr(s, "connect"):
                try:
                    s.connect(self._on_menu_pedido)
                except (TypeError, RuntimeError):
                    pass
        if abierto:
            self.cerrar()

    def _soltar_mascota(self) -> None:
        vieja, self._mascota = self._mascota, None
        if vieja is None:
            return
        s = getattr(vieja, "menu_pedido", None)
        if s is not None:
            try:
                s.disconnect(self._on_menu_pedido)
            except (TypeError, RuntimeError, AttributeError):
                pass

    def set_colores(self, c: Optional[dict]) -> None:
        self._colores = dict(c or {})
        if self._menu is not None:
            self._menu.set_colores(self._colores)

    # ── Abrir y cerrar ─────────────────────────────────────────────────────
    def abierto(self) -> bool:
        return bool(self._esperando or (self._menu is not None and self._menu.abierto))

    @property
    def menu(self) -> Optional[MenuRadial]:
        return self._menu

    def cerrar(self) -> None:
        if self._esperando:
            self._esperando = False
            self._pendiente += 1
        if self._menu is not None and self._menu.abierto:
            self._menu.cerrar()

    def _on_menu_pedido(self, tipo, punto=None) -> None:
        """Clic derecho soltado sobre la mascota. Como en Mate-Engine, el radial se
        centra en su CABEZA (ancla_menu); el punto del clic es solo el respaldo."""
        punto = QPoint(punto) if isinstance(punto, QPoint) else None
        m = self._mascota_a_la_vista()
        if m is not None and callable(getattr(m, "ancla_menu", None)):
            self.abrir(str(tipo or "principal"), None, respaldo=punto)
        else:
            self.abrir(str(tipo or "principal"), punto)

    def items(self, tipo: str = "principal") -> List[ItemRadial]:
        """Botones que tendría ahora el radial `tipo`."""
        est = self._estado.actual()
        try:
            ctx = self._contexto()
        except Exception:
            _log.exception("menu_radial: el contexto falló")
            return []
        if tipo == "expresiones":
            return acciones_ui.items_expresiones(self._desp) if ctx.mascota_visible else []
        if tipo not in ("principal", "secundario"):
            return []
        return acciones_ui.items_radial(self._desp, est, ctx, _cfg(self._config, "menu_radial", tipo, []))

    def abrir(self, tipo: str = "principal", centro: Optional[QPoint] = None, *,
              respaldo: Optional[QPoint] = None) -> bool:
        """Abre el radial `tipo` ("principal", "secundario", "expresiones"). Si ya
        estaba abierto, lo cierra (como F1 en Mate-Engine) y devuelve False. Sin
        `centro`: en la cabeza de la mascota si está a la vista (su ancla_menu,
        que puede contestar más tarde) o en `respaldo` / el cursor. False si no se abre."""
        if self._detenido:
            return False
        if self.abierto():
            self.cerrar()
            return False
        est = self._estado.actual()
        if getattr(est, "arrastrando", False):
            return False
        items = self.items(tipo)
        if not items:
            return False
        self._tipo = tipo
        if centro is None:
            m = self._mascota_a_la_vista()
            if m is not None and callable(getattr(m, "ancla_menu", None)):
                self._pendiente += 1
                ficha = self._pendiente
                self._esperando = True
                QTimer.singleShot(self.ESPERA_ANCLA_MS, lambda: self._ancla_tarde(ficha, items, respaldo))
                try:
                    m.ancla_menu(lambda p, f=ficha: self._ancla_lista(f, p, items, respaldo))
                except Exception:
                    _log.exception("menu_radial: ancla_menu falló")
                    self._esperando = False
                    return self._abrir_en(respaldo or QCursor.pos(), items)
                return True
            centro = respaldo or QCursor.pos()
        return self._abrir_en(QPoint(centro), items)

    def _ancla_lista(self, ficha: int, punto, items, respaldo=None) -> None:
        if ficha != self._pendiente or not self._esperando:
            return
        self._esperando = False
        self._abrir_en(punto if isinstance(punto, QPoint) else (respaldo or QCursor.pos()), items)

    def _ancla_tarde(self, ficha: int, items, respaldo=None) -> None:
        if ficha != self._pendiente or not self._esperando:
            return
        self._esperando = False
        self._abrir_en(respaldo or QCursor.pos(), items)

    def _asegurar_menu(self) -> MenuRadial:
        if self._menu is None:
            try:
                menu = self._fabrica(colores=self._colores, traer_al_frente=self._traer)
            except TypeError:
                menu = self._fabrica()
                _llamar(menu, "set_colores", self._colores)
            menu.elegido.connect(self._on_elegido)
            menu.cerrado.connect(lambda m=menu: self._al_cerrar(m))
            self._menu = menu
        return self._menu

    def _abrir_en(self, centro: QPoint, items) -> bool:
        menu = self._asegurar_menu()
        if not menu.abrir(QPoint(centro), items):
            return False
        self._estado.actualizar(menu_abierto=True)
        _llamar(self._mascota, "set_menu_abierto", True)
        self._tocar("menu_abrir")
        if self._mascota_a_la_vista() is not None and callable(getattr(self._mascota, "ancla_menu", None)):
            self._seguir_t.start()
        return True

    def _al_cerrar(self, menu: MenuRadial) -> None:
        if menu is not self._menu and self._menu is not None:
            return
        self._seguir_t.stop()
        try:
            self._estado.actualizar(menu_abierto=False)
        except Exception:
            _log.exception("menu_radial: no pude soltar menu_abierto")
        _llamar(self._mascota, "set_menu_abierto", False)
        if not getattr(menu, "ultimo_por_eleccion", False):
            self._tocar("menu_cerrar")

    def _on_elegido(self, id_: str, arg: str) -> None:
        self._tocar("menu_boton")
        self._desp.ejecutar(str(id_), str(arg or ""), origen="radial")

    # ── Seguir a la cabeza ─────────────────────────────────────────────────
    def _mascota_a_la_vista(self):
        m = self._mascota
        if m is None or getattr(m, "cerrado", False):
            return None
        try:
            return m if m.isVisible() else None
        except Exception:
            return None

    def _pedir_seguir(self) -> None:
        m = self._mascota_a_la_vista()
        if m is None or self._menu is None or not self._menu.abierto:
            self._seguir_t.stop()
            return
        try:
            m.ancla_menu(self._seguir_a)
        except Exception:
            self._seguir_t.stop()

    def _seguir_a(self, punto) -> None:
        if isinstance(punto, QPoint) and self._menu is not None and self._menu.abierto:
            self._menu.seguir(punto)

    def _tocar(self, nombre: str) -> None:
        if self._sonar is None or self._callado:
            return
        try:
            self._sonar(nombre)
        except Exception:
            _log.debug("menu_radial: sonido %s falló", nombre, exc_info=True)
