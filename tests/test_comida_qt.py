"""
Tests de ui/comida_qt.py (offscreen): el dibujo procedural, la ventanita que
sigue al cursor (banderas, aparecer/guardar animados, balanceo) y ControlComida
con ServiciosEscritorio real (BusEstado y tabla de prioridades de verdad), una
asistente falsa que cumple el contrato del corte 8, un mezclador falso, un cursor
falso y un reloj falso.
"""
import json
import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import comida as nc  # noqa: E402


# ── Dobles ───────────────────────────────────────────────────────────────────────

class Config:
    def __init__(self, **secciones):
        self.d = {"avatar": {"volumen_sfx": 0.7, "pack_sonidos": "default"},
                  "juego": {"silenciar": True}, "comida": {"activa": True}}
        for sec, vals in secciones.items():
            self.d.setdefault(sec, {}).update(vals)

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class MezcladorFalso:
    def __init__(self):
        self.sonados = []

    def cargar_audio(self, ruta):
        return Path(ruta)

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self.sonados.append((Path(buf).stem, round(float(velocidad), 3), canal))
        return len(self.sonados)

    def nombres(self):
        return [s[0] for s in self.sonados]


class AsistenteFalsa:
    """Cumple lo que usa la comida del contrato de la asistente (corte 8)."""

    def __init__(self, cabeza=(500, 300, 40), ancho=300):
        self.visible = True
        self.cerrado = False
        self.cabeza_resp = cabeza
        self.ancho = ancho
        self.comidas, self.activas = [], []
        self.pedidas_cabeza = 0
        self.asincrona = False
        self.pendientes = []

    def isVisible(self):
        return self.visible

    def width(self):
        return self.ancho

    def cabeza(self, cb):
        self.pedidas_cabeza += 1
        if self.asincrona:
            self.pendientes.append(cb)
        else:
            cb(self.cabeza_resp)

    def comer(self, tipo, ms=2500):
        self.comidas.append((tipo, ms))

    def set_comida_activa(self, on):
        self.activas.append(bool(on))


class CursorFalso:
    """Lo que ControlComida usa de ComidaCursor."""
    creados = []

    def __init__(self):
        self.llamadas = []
        self.visible = False
        CursorFalso.creados.append(self)

    def mostrar(self, id_, variante, tam_px, centro=None):
        self.llamadas.append(("mostrar", id_, variante, tam_px))
        self.visible = True

    def ocultar(self, animado=True):
        self.llamadas.append(("ocultar", animado))
        self.visible = False

    def paso(self, dt, cursor):
        self.llamadas.append(("paso", round(dt, 4), cursor.x(), cursor.y()))

    def close(self):
        self.llamadas.append(("close",))

    def deleteLater(self):
        self.llamadas.append(("deleteLater",))

    def de(self, tipo):
        return [c for c in self.llamadas if c[0] == tipo]


class AnfitrionFalso:
    def __init__(self, modo="normal", asistente_al_sacar=None, esc=None):
        self.modo = modo
        self.avisos, self.reacciones = [], []
        self.sacadas = 0
        self._m = asistente_al_sacar
        self._esc = esc

    def aviso(self, texto):
        self.avisos.append(texto)

    def reaccion(self, estado, ms):
        self.reacciones.append((estado, ms))

    def alternar_asistente(self):
        self.sacadas += 1
        if self._m is not None and self._esc is not None:
            self._esc.set_asistente(self._m)


@pytest.fixture
def montaje(qapp):
    from PyQt6.QtCore import QPoint
    from ui.comida_qt import ControlComida
    from ui.escritorio import ServiciosEscritorio

    creados = []

    def crear(modo="normal", config=None, asistente="si", asistente_al_sacar=None):
        esc = ServiciosEscritorio(config or Config())
        reloj = Reloj()
        mez = MezcladorFalso()
        pos = {"p": QPoint(100, 100)}
        anf = AnfitrionFalso(modo, asistente_al_sacar, esc)
        en_ui = []

        def correr(fn):
            en_ui.append(fn)
            return fn()
        ctl = ControlComida(esc, esc.config, anfitrion=anf, mezclador=mez, fabrica_cursor=CursorFalso,
                            azar=random.Random(4), reloj=reloj, en_ui=correr,
                            cursor_pos=lambda: pos["p"], lanzar_sonido=lambda f: f())
        esc.registrar("comida", ctl, ("comida",))
        esc.iniciar()
        m = AsistenteFalsa() if asistente == "si" else None
        if m is not None:
            esc.set_asistente(m)
        ctl.cambios, ctl.webs = [], []
        ctl.cambio.connect(lambda s: ctl.cambios.append(json.loads(s)))
        ctl.comida_web.connect(lambda s: ctl.webs.append(json.loads(s)))

        class X:
            pass
        x = X()
        x.esc, x.ctl, x.m, x.mez, x.pos, x.reloj, x.anf, x.en_ui = esc, ctl, m, mez, pos, reloj, anf, en_ui
        creados.append(x)
        return x

    CursorFalso.creados.clear()
    yield crear
    for x in creados:
        x.esc.cerrar()
        x.ctl.deleteLater()


def comiendo(x):
    return x.esc.estado.actual().comiendo


def cursor(x):
    return x.ctl._cursor


def mover(x, px, py, dt=0.016):
    from PyQt6.QtCore import QPoint
    x.reloj.t += dt
    x.pos["p"] = QPoint(px, py)
    x.ctl.paso()


# ── Dibujo ───────────────────────────────────────────────────────────────────────

def _imagen(fn, lado=128):
    from PyQt6.QtGui import QColor, QImage, QPainter
    img = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    try:
        r = fn(p)
    finally:
        p.end()
    return img, r


def _opacos(img, y0=0, y1=None):
    y1 = img.height() if y1 is None else y1
    return [(x, y) for y in range(y0, y1) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 128]


def _cerca(c, hex_, tol=40):
    from PyQt6.QtGui import QColor
    o = QColor(hex_)
    return abs(c.red() - o.red()) + abs(c.green() - o.green()) + abs(c.blue() - o.blue()) <= tol


def test_pintar_batido_con_el_color_de_la_variante(qapp):
    from PyQt6.QtCore import QRectF
    from ui.comida_qt import pintar_comida
    for var in nc.CATALOGO["batido"].variantes:
        img, ok = _imagen(lambda p: pintar_comida(p, "batido", var.id, QRectF(0, 0, 128, 128)))
        assert ok
        # el líquido ocupa el centro del vaso
        assert _cerca(img.pixelColor(64, 86), var.color), (var.id, img.pixelColor(64, 86).name())


def test_pintar_pastel_con_la_cobertura_de_la_variante(qapp):
    from PyQt6.QtCore import QRectF
    from ui.comida_qt import pintar_comida
    imagenes = []
    for var in nc.CATALOGO["pastel"].variantes:
        img, ok = _imagen(lambda p: pintar_comida(p, "pastel", var.id, QRectF(0, 0, 128, 128)))
        assert ok and _cerca(img.pixelColor(70, 57), var.color), (var.id, img.pixelColor(70, 57).name())
        imagenes.append(img)
    assert imagenes[0] != imagenes[1]


def test_pintar_nada_con_escala_cero_o_comida_desconocida(qapp):
    from PyQt6.QtCore import QRectF
    from ui.comida_qt import pintar_comida
    for args in (("batido", "fresa", QRectF(0, 0, 128, 128), 0, 0, 0.0),
                 ("pizza", "", QRectF(0, 0, 128, 128), 0, 0, 1.0),
                 ("pastel", "fresa", QRectF(), 0, 0, 1.0)):
        img, ok = _imagen(lambda p: pintar_comida(p, *args))
        assert ok is False and not _opacos(img)


def test_ladeo_positivo_inclina_la_parte_de_arriba_a_la_derecha(qapp):
    from PyQt6.QtCore import QRectF
    from ui.comida_qt import pintar_comida

    def centro_x_arriba(ladeo):
        img, _ = _imagen(lambda p: pintar_comida(p, "batido", "mango", QRectF(0, 0, 128, 128), ladeo, 0, 1.0))
        pts = _opacos(img, 0, 45)
        return sum(x for x, _ in pts) / len(pts)
    recto, derecha, izquierda = centro_x_arriba(0), centro_x_arriba(25), centro_x_arriba(-25)
    assert derecha > recto + 5 and izquierda < recto - 5
    # cabeceo: se acorta en vertical
    alto = lambda cab: len({y for _, y in _opacos(_imagen(  # noqa: E731
        lambda p: pintar_comida(p, "pastel", "limon", QRectF(0, 0, 128, 128), 0, cab, 1.0))[0])})
    assert alto(40) < alto(0)


# ── ComidaCursor ─────────────────────────────────────────────────────────────────

def test_cursor_ventana_sin_foco_y_transparente_al_raton(qapp):
    from PyQt6.QtCore import Qt
    from ui.comida_qt import ComidaCursor
    w = ComidaCursor()
    try:
        f = w.windowFlags()
        for bandera in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.Tool, Qt.WindowType.WindowStaysOnTopHint,
                        Qt.WindowType.WindowTransparentForInput, Qt.WindowType.WindowDoesNotAcceptFocus):
            assert f & bandera, bandera
        for attr in (Qt.WidgetAttribute.WA_TranslucentBackground, Qt.WidgetAttribute.WA_ShowWithoutActivating):
            assert w.testAttribute(attr), attr
    finally:
        w.deleteLater()


def test_cursor_aparece_sigue_centrado_se_balancea_y_se_guarda(qapp):
    from PyQt6.QtCore import QPoint
    from ui.comida_qt import ComidaCursor
    reloj = Reloj()
    w = ComidaCursor(reloj=reloj)
    try:
        w.mostrar("batido", "fresa", 100, QPoint(400, 300))
        assert w.isVisible() and w.escala == 0.0 and w.fase == "aparece"
        assert w.width() == w.height() == 160
        assert w.geometry().center().x() in (399, 400) and w.geometry().center().y() in (299, 300)
        reloj.t += 0.1
        w.paso(0.1, QPoint(420, 300))
        assert 0.0 < w.escala < 1.0
        assert abs(w.geometry().center().x() - 420) <= 1                 # sin suavizado
        for _ in range(20):
            reloj.t += 1 / 60
            w.paso(1 / 60, QPoint(w.geometry().center().x() + 6, 300))
        assert w.escala == 1.0 and w.fase == "quieta"
        assert w.ladeo > 1                                              # a la derecha: horario
        w.grab()                                                        # pinta sin errores
        w.ocultar(animado=True)
        assert w.fase == "guarda" and w.isVisible()
        reloj.t += 0.1
        w._tic_anim()
        assert 0.0 < w.escala < 1.0
        reloj.t += 0.11
        w._tic_anim()
        assert not w.isVisible() and w.fase == "" and w.escala == 0.0
        # de golpe
        w.mostrar("pastel", "limon", 64, QPoint(10, 10))
        w.ocultar(animado=False)
        assert not w.isVisible()
    finally:
        w.deleteLater()


# ── ControlComida ────────────────────────────────────────────────────────────────

def test_aparece_pide_la_prioridad_suena_y_sigue_al_cursor(montaje):
    x = montaje()
    assert not x.ctl._timer.isActive()                                  # sin comida, sin timer
    assert x.ctl.alternar("batido") == "aparece"
    assert comiendo(x) and x.ctl.activa[0] == "batido"
    assert x.mez.nombres()[0] == "comida_aparece" and re.fullmatch(r"comida_capa_[12]", x.mez.nombres()[1])
    assert all(canal == "sfx" and 0.65 <= vel <= 1.25 for _, vel, canal in x.mez.sonados)
    cur = cursor(x)
    assert cur.de("mostrar") == [("mostrar", "batido", x.ctl.activa[1], 99)]      # 0.33 × 300
    assert x.m.activas == [True]
    assert x.ctl._timer.isActive() and x.ctl._timer.interval() == 16
    assert x.ctl.cambios[-1] == {"activa": True, "id": "batido", "variante": x.ctl.activa[1],
                                 "color": nc.variante_de("batido", x.ctl.activa[1]).color,
                                 "tipo": "beber", "vista": "escritorio", "disponible": True}
    mover(x, 150, 120)
    assert cur.de("paso")[-1][2:] == (150, 120)


def test_pastel_sin_capa_y_tamano_minimo(montaje):
    x = montaje()
    x.m.ancho = 100
    x.ctl.alternar("pastel")
    assert x.mez.nombres() == ["comida_aparece"]
    assert cursor(x).de("mostrar")[0][3] == 64


def test_pasar_por_la_cabeza_es_comer(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    mover(x, 300, 300)                                   # pide la cabeza (10 Hz)
    assert x.m.pedidas_cabeza == 1
    antes = len(x.mez.sonados)
    mover(x, 700, 300)                                   # cruza la cabeza (500, 300, r 40) de un salto
    assert x.m.comidas == [("beber", 2500)]
    son, vel, canal = x.mez.sonados[antes]
    assert re.fullmatch(r"trago_[123]", son) and 0.65 <= vel <= 1.25 and canal == "sfx"
    assert x.esc.estado.actual().emocion == "happy"
    mover(x, 710, 300)
    mover(x, 520, 300)                                   # vuelve a entrar a los 0.032 s: enfriándose
    assert len(x.m.comidas) == 1
    mover(x, 800, 300, dt=0.4)
    mover(x, 500, 300)                                   # pasado el enfriamiento
    assert len(x.m.comidas) == 2


def test_cabeza_a_10_hz_y_respuesta_asincrona(montaje):
    x = montaje()
    x.m.asincrona = True
    x.ctl.alternar("pastel")
    for _ in range(12):
        mover(x, 100, 100)                               # 12 × 16 ms ≈ 0.19 s
    assert x.m.pedidas_cabeza == 2
    assert x.ctl._cabeza is None
    x.m.pendientes[-1]((100, 100, 30))                   # llega la respuesta de la página
    mover(x, 120, 100)
    mover(x, 400, 400)
    mover(x, 101, 100)
    assert x.m.comidas == [("comer", 2500)]


def test_pedir_otra_la_cambia_y_la_misma_la_guarda(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    x.mez.sonados.clear()
    assert x.ctl.alternar("pastel") == "cambia"
    assert x.ctl.activa[0] == "pastel" and comiendo(x)
    assert x.mez.nombres() == ["comida_aparece"]
    assert [c[1] for c in cursor(x).de("mostrar")] == ["batido", "pastel"]
    assert x.ctl.alternar("pastel") == "guarda"
    assert x.ctl.activa is None and not comiendo(x)
    assert cursor(x).de("ocultar") == [("ocultar", True)]
    assert x.m.activas == [True, False]
    assert not x.ctl._timer.isActive()
    assert x.ctl.cambios[-1]["activa"] is False and x.ctl.cambios[-1]["vista"] == ""


def test_la_comida_cede_el_baile_y_lo_reanuda_al_guardarse(montaje):
    x = montaje()

    class Baile:
        def __init__(self):
            self.cedido = self.reanudado = 0

        def ceder(self, c):
            self.cedido += 1

        def reanudar(self, c):
            self.reanudado += 1
    b = Baile()
    x.esc.registrar("baile", b, ("baile",))
    assert x.esc.prioridad.iniciar("baile", "musica")
    x.ctl.alternar("batido")
    assert b.cedido == 1 and x.esc.estado.actual().bailando == ""
    x.ctl.guardar()
    assert b.reanudado == 1 and x.esc.estado.actual().bailando == "musica"


def test_juego_la_guarda_sin_sonido_y_no_deja_sacarla(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    n = len(x.mez.sonados)
    assert x.esc.prioridad.iniciar("juego")
    assert x.ctl.activa is None and not comiendo(x)
    assert cursor(x).de("ocultar") and x.m.activas[-1] is False
    assert len(x.mez.sonados) == n                                   # sin sonido
    assert x.ctl.alternar("pastel") == "" and x.ctl.ultimo_motivo == "juego"
    assert x.anf.avisos == ["Ahora no puedo comer: hay un juego delante."]
    assert x.ctl.comer_directo("pastel") == ""
    assert len(x.mez.sonados) == n and x.m.comidas == []
    x.esc.prioridad.terminar("juego")
    assert x.ctl.alternar("pastel") == "aparece"


def test_asistente_none_u_oculta_la_guarda(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    x.esc.set_asistente(None)
    assert x.ctl.activa is None and not comiendo(x)
    assert x.m.activas == [True, False]                              # la que se fue también la suelta
    y = montaje()
    y.ctl.alternar("pastel")
    y.m.visible = False
    y.esc.estado.actualizar(visible=False)                           # la asistente se oculta
    assert y.ctl.activa is None and not comiendo(y) and y.m.activas == [True, False]


def test_otra_asistente_con_la_comida_fuera(montaje):
    """La asistente se recrea (cambio de render) con la comida en el cursor: la
    nueva la recibe y la vieja la suelta."""
    x = montaje()
    x.ctl.alternar("batido")
    nueva = AsistenteFalsa(cabeza=(50, 50, 20))
    x.esc.set_asistente(nueva)
    assert x.ctl.activa is not None and nueva.activas == [True] and x.m.activas == [True, False]
    mover(x, 10, 50)
    mover(x, 60, 50)
    assert nueva.comidas == [("beber", 2500)] and x.m.comidas == []


def test_web_sin_asistente_la_pinta_la_pagina(montaje):
    x = montaje(modo="normal", asistente="no")
    assert x.ctl.alternar("batido") == "aparece"
    assert CursorFalso.creados == [] and not x.ctl._timer.isActive()
    web = x.ctl.webs[-1]
    assert web["accion"] == "aparece" and web["id"] == "batido" and web["tipo"] == "beber"
    assert web["color"] == nc.variante_de("batido", web["variante"]).color
    assert x.ctl.estado()["vista"] == "web"
    x.ctl.alternar("pastel")
    assert x.ctl.webs[-1]["accion"] == "cambia" and x.ctl.webs[-1]["id"] == "pastel"
    # la página detecta el acierto
    n = len(x.mez.sonados)
    assert x.ctl.acierto_web("pastel") is True
    assert re.fullmatch(r"mordisco_[123]", x.mez.sonados[n][0])
    assert x.esc.estado.actual().emocion == "happy"
    assert x.anf.reacciones == []                                   # la cara la pone la página
    assert x.ctl.acierto_web("pastel") is False                     # enfriamiento de 0.35 s
    x.reloj.t += 0.4
    assert x.ctl.acierto_web("batido") is False                     # no es la de la mano
    assert x.ctl.acierto_web("pastel") is True
    x.ctl.guardar()
    assert x.ctl.webs[-1]["accion"] == "guarda" and not comiendo(x)
    assert x.ctl.acierto_web("pastel") is False


def test_web_con_la_comida_fuera_aparece_la_asistente_y_pasa_al_escritorio(montaje):
    x = montaje(modo="normal", asistente="no")
    x.ctl.alternar("batido")
    m = AsistenteFalsa()
    x.esc.set_asistente(m)
    assert x.ctl.webs[-1]["accion"] == "guarda"
    assert x.ctl.estado()["vista"] == "escritorio" and comiendo(x)
    assert CursorFalso.creados and CursorFalso.creados[-1].de("mostrar")
    assert m.activas == [True] and x.ctl._timer.isActive()


def test_nativa_sin_asistente_la_saca_primero(montaje):
    m = AsistenteFalsa()
    x = montaje(modo="br", asistente="no", asistente_al_sacar=m)
    assert x.ctl.alternar("pastel") == "aparece"
    assert x.anf.sacadas == 1 and x.ctl.estado()["vista"] == "escritorio"
    assert m.activas == [True] and cursor(x).de("mostrar")


def test_nativa_la_asistente_que_tarda_en_verse_recibe_la_comida(montaje):
    m = AsistenteFalsa()
    m.visible = False
    x = montaje(modo="br", asistente="no", asistente_al_sacar=m)
    assert x.ctl.alternar("batido") == "aparece"
    assert x.anf.sacadas == 1 and m.activas == [] and x.ctl.activa is not None
    assert cursor(x).de("mostrar")[0][3] == 96                       # sin asistente a la vista aún
    m.visible = True
    x.esc.estado.actualizar(visible=True)
    assert m.activas == [True] and x.ctl.activa is not None


def test_se_guarda_sola_a_los_dos_minutos_sin_moverla(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    mover(x, 100, 100)
    mover(x, 100, 100, dt=60)
    assert x.ctl.activa is not None
    mover(x, 101, 100, dt=60)                                        # se movió: vuelve a contar
    mover(x, 101, 100, dt=119)
    assert x.ctl.activa is not None
    mover(x, 101, 100, dt=1.5)
    assert x.ctl.activa is None and not comiendo(x) and not x.ctl._timer.isActive()


def test_comer_directo_sostiene_la_actividad_durante_la_reaccion(montaje):
    x = montaje()
    texto = x.ctl.comer_directo("pastel")
    assert texto.startswith("*ñam ñam* (pastel de ")
    assert x.m.comidas == [("comer", 2500)] and comiendo(x)
    assert re.fullmatch(r"mordisco_[123]", x.mez.nombres()[-1])
    assert x.ctl._t_directo.isActive() and x.ctl._t_directo.interval() == 2500
    x.ctl._fin_directo()
    assert not comiendo(x)
    # con la comida en la mano: la reacción de esa variante, sin tocar la prioridad
    x.ctl.alternar("batido")
    var = x.ctl.activa[1]
    assert x.ctl.comer_directo("batido") == f"*glup glup* (batido de {nc.variante_de('batido', var).nombre})"
    assert not x.ctl._t_directo.isActive() and comiendo(x)


def test_comer_directo_sin_asistente_usa_el_anfitrion(montaje):
    x = montaje(modo="normal", asistente="no")
    assert x.ctl.comer_directo("batido")
    assert x.anf.reacciones == [("happy", 2500)]


def test_herramienta_dar_de_comer_por_en_ui(montaje):
    x = montaje()
    h = x.ctl.herramientas()
    assert list(h) == ["dar_de_comer"]
    r = h["dar_de_comer"]({"comida": "batido"}, None)
    assert r.startswith("*glup glup* (batido de ") and len(x.en_ui) == 1
    x.esc.prioridad.iniciar("juego")
    x.ctl._fin_directo()
    ok, texto = h["dar_de_comer"]({"comida": "pastel"}, {"origen": "modelo"})
    assert ok is False and "juego" in texto


def test_herramienta_desde_otro_hilo(montaje, qapp):
    import threading
    from ui.montaje_ocio import EnHiloQt
    x = montaje()
    x.ctl._en_ui = EnHiloQt()
    caja = {}

    def trabajador():
        caja["r"] = x.ctl.herramientas()["dar_de_comer"]({"comida": "pastel"}, None)
        caja["hilo"] = threading.get_ident()
    h = threading.Thread(target=trabajador)
    h.start()
    while h.is_alive():
        qapp.processEvents()
        h.join(0.01)
    assert caja["r"].startswith("*ñam ñam*") and x.m.comidas == [("comer", 2500)]


def test_comida_desactivada(montaje):
    x = montaje(config=Config(comida={"activa": False}))
    assert x.ctl.alternar("batido") == "" and x.ctl.ultimo_motivo == "desactivada"
    assert x.anf.avisos == ["La comida está desactivada (Ajustes → Comida)."]
    assert not comiendo(x) and x.mez.sonados == []
    assert x.ctl.comer_directo("batido") == ""
    x.esc.config.set("comida", "activa", True)
    x.ctl.alternar("batido")
    x.esc.config.set("comida", "activa", False)
    x.ctl.recargar_config()
    assert x.ctl.activa is None and not comiendo(x)
    assert x.ctl.estado()["disponible"] is False


def test_silencio_en_juego_para_la_reaccion(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    x.esc.estado.actualizar(juego=True)             # un juego sin pasar por la tabla (p. ej. al arrancar)
    n = len(x.mez.sonados)
    x.ctl._reaccionar(x.ctl.gestor.reaccion())
    assert len(x.mez.sonados) == n and x.m.comidas


def test_detener_idempotente_sin_timers(montaje):
    x = montaje()
    x.ctl.alternar("batido")
    cur = cursor(x)
    x.ctl.detener()
    x.ctl.detener()
    assert x.ctl.activa is None and not comiendo(x)
    assert not x.ctl._timer.isActive() and not x.ctl._t_directo.isActive()
    assert ("ocultar", False) in cur.llamadas and ("deleteLater",) in cur.llamadas
    assert x.ctl._cursor is None
    x.ctl.paso()                                                    # sin comida no hace nada
    assert not x.ctl._timer.isActive()


def test_estado_por_defecto(montaje):
    x = montaje(asistente="no")
    assert x.ctl.estado() == {"activa": False, "id": "", "variante": "", "color": "", "tipo": "",
                              "vista": "", "disponible": True}
    assert x.ctl.ultima == "" and x.ctl.alternar("pizza") == ""
