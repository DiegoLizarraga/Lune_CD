"""
Dobles de los tests del corte 7 (sentarse): ventanas ajenas, pantalla (monitores y
barra), win_ventana, entrada (cursor) y reloj. Sin Win32 real.
"""
from servicios.win_pantalla import Monitor, Rect

WS_CAPTION = 0x00C00000
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 1
LWA_ALPHA = 2

PID_LUNE = 1000
MON1 = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032), True, r"\\.\DISPLAY1")
MON2 = Monitor(202, Rect(1920, 0, 3840, 1080), Rect(1920, 0, 3840, 1040), False, r"\\.\DISPLAY2")


class V:
    """Una ventana falsa de primer nivel (todo configurable)."""

    def __init__(self, rect, *, pid=500, clase="Notepad", titulo=5, estilo=WS_OVERLAPPEDWINDOW, ex=0,
                 visible=True, padre=0, raiz=None, minimizada=False, maximizada=False, cloaked=False,
                 capas=None, existe=True, rect_visible=None, monitor=MON1):
        self.rect = Rect(*rect)
        self.pid, self.clase, self.titulo = pid, clase, titulo
        self.estilo, self.ex = estilo, ex
        self.es_visible, self.padre, self.raiz = visible, padre, raiz
        self.min, self.max, self.cloak = minimizada, maximizada, cloaked
        self.capas_ = capas
        self.vive = existe
        self.rv = Rect(*rect_visible) if rect_visible else None
        self.mon = monitor


class ApiVentanasFalsa:
    """`ventanas`: {hwnd: V}; `orden`: hwnds en orden Z de arriba abajo."""

    def __init__(self, ventanas=None, orden=None, activa=0):
        self.v = dict(ventanas or {})
        self.orden = list(orden) if orden is not None else list(self.v)
        self._activa = activa
        self.n_enumerar = 0
        self.llamadas = []

    def enumerar(self):
        self.n_enumerar += 1
        return list(self.orden)

    def activa(self):
        return self._activa

    def visible(self, h):
        return self.v[h].es_visible if h in self.v else False

    def rect(self, h):
        return self.v[h].rect if h in self.v and self.v[h].vive else None

    def rect_visible(self, h):
        if h not in self.v or not self.v[h].vive:
            return None
        return self.v[h].rv or self.v[h].rect

    def clase(self, h):
        return self.v[h].clase

    def largo_titulo(self, h):
        return self.v[h].titulo

    def estilo(self, h):
        return self.v[h].estilo

    def estilo_ex(self, h):
        return self.v[h].ex

    def padre(self, h):
        return self.v[h].padre

    def raiz(self, h):
        r = self.v[h].raiz
        return h if r is None else r

    def minimizada(self, h):
        return self.v[h].min

    def maximizada(self, h):
        return self.v[h].max

    def cloaked(self, h):
        return self.v[h].cloak

    def capas(self, h):
        return self.v[h].capas_

    def anterior(self, h):
        try:
            i = self.orden.index(h)
        except ValueError:
            return 0
        return self.orden[i - 1] if i > 0 else 0

    def existe(self, h):
        return h in self.v and self.v[h].vive

    def pid(self, h):
        self.llamadas.append(("pid", h))
        return self.v[h].pid if h in self.v else 0

    def monitor(self, h):
        if h not in self.v or self.v[h].mon is None:
            return None
        m = self.v[h].mon
        return m.rect, m.trabajo


class PantallaFalsa:
    """Lo que `win_pantalla.barra_tareas` y `monitores` preguntan."""

    def __init__(self, monitores=(MON1, MON2), bandejas=None, auto_oculta=False):
        self.mons = {m.hmon: m for m in monitores}
        self.orden = [m.hmon for m in monitores]
        self.bandejas = dict(bandejas if bandejas is not None else
                             {"Shell_TrayWnd": {0x100: Rect(0, 1032, 1920, 1080)},
                              "Shell_SecondaryTrayWnd": {0x200: Rect(1920, 1040, 3840, 1080)}})
        self.auto_oculta = auto_oculta
        self.n = 0

    def info_monitor(self, hmon):
        self.n += 1
        return self.mons.get(hmon)

    def lista_monitores(self):
        return list(self.orden)

    def buscar_ventanas(self, clase):
        return list(self.bandejas.get(clase, {}))

    def rect_ventana(self, h):
        for d in self.bandejas.values():
            if h in d:
                return d[h]
        return None

    def barra_auto_oculta(self):
        return self.auto_oculta


class VentanaPropiaFalsa:
    """Doble de servicios.win_ventana para la ventana de la mascota."""

    def __init__(self, rects=None):
        self.rects = {h: Rect(*r) for h, r in (rects or {}).items()}
        self.llamadas = []
        self.encima = False

    def rect_propia(self, h):
        return self.rects.get(h)

    def mover(self, h, x, y):
        self.llamadas.append(("mover", h, int(x), int(y)))
        r = self.rects.get(h)
        if r is None:
            return False
        self.rects[h] = Rect(int(x), int(y), int(x) + r.ancho, int(y) + r.alto)
        return True

    def colocar_sobre(self, h, obj):
        self.llamadas.append(("colocar_sobre", h, obj))
        self.encima = True
        return True

    def encima_de(self, h, obj):
        self.llamadas.append(("encima_de", h, obj))
        return self.encima

    def set_encima(self, h, on):
        self.llamadas.append(("set_encima", h, on))
        return True

    def de(self, tipo):
        return [c for c in self.llamadas if c[0] == tipo]


class EntradaFalsa:
    def __init__(self, x=0, y=0):
        self.c = (x, y)

    def cursor(self):
        return self.c


class Reloj:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Config:
    def __init__(self, **avatar):
        self.d = {"avatar": {"sentarse_ventanas": False, "sentarse_barra": True, "sentarse_offset_px": 0,
                             **avatar}}

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor
