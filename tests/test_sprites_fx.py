"""
Tests de ui/sprites_fx.py: balanceo, caras por velocidad, mareo, respiración y
mirada de la asistente de sprites, y sus adaptadores Qt.

La lógica pura se prueba con reloj falso; FisicaSpriteQt / RespiracionSpriteQt y
SpriteRotado con QT_QPA_PLATFORM=offscreen (fixture `qapp` de conftest.py). Los
temporizadores no se esperan: se llama a `_tick()` con el reloj falso avanzado.
"""
import math
import os
import random
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import sprites_fx as fx  # noqa: E402


class Reloj:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avanzar(self, s: float) -> None:
        self.t += s


def arrastrar(f, t, x, vx, segundos, hz_mov=60, hz_paso=30):
    """Mueve la ventana a vx px/s durante `segundos` (Move a hz_mov, paso a hz_paso).
    Devuelve (t, x, ángulos)."""
    angulos = []
    n = int(round(segundos * hz_mov))
    cada = max(1, hz_mov // hz_paso)
    for i in range(n):
        t += 1 / hz_mov
        x += vx / hz_mov
        f.mover(x, 0, t)
        if i % cada == cada - 1:
            angulos.append(f.paso(t))
    return t, x, angulos


# ── FisicaSprite ─────────────────────────────────────────────────────────────────

def test_constantes_de_mate_engine():
    assert fx.GANANCIA == 0.0167 and fx.F_HZ == 0.9 and fx.ZETA == 0.5 and fx.TOPE_GRADOS == 6.0
    assert fx.PIVOTE == (0.5, 0.06)


def test_objetivo_con_saturacion_suave_a_6_grados():
    f = fx.FisicaSprite()
    f.vx = 100
    assert f.objetivo() == pytest.approx(1.67, rel=0.03)             # casi lineal con poca velocidad
    assert f.objetivo() < 1.67                                        # tanh: nunca más que la lineal
    for v in (1000, 5000, 10 ** 6):
        f.vx = v
        assert 5 < f.objetivo() <= 6.0
        f.vx = -v
        assert -6.0 <= f.objetivo() < -5
    f.vx = 1000
    assert fx.FisicaSprite(invertir=True).objetivo() == 0.0          # vx propio = 0
    g = fx.FisicaSprite(invertir=True)
    g.vx = 1000
    assert g.objetivo() == pytest.approx(-f.objetivo())


def test_angulo_sigue_al_arrastre_converge_a_0_y_rebota():
    f = fx.FisicaSprite()
    assert f.mover(0, 0, 0.0) is False                               # primera: solo referencia
    assert f.reposo and f.paso(0.0) == 0.0
    t, x, angulos = arrastrar(f, 0.0, 0.0, 600, 0.6)
    assert not f.reposo
    assert f.vx == pytest.approx(600, rel=0.02)
    assert angulos[-1] > 4                                            # a la derecha: positivo (horario)
    assert max(abs(a) for a in angulos) <= fx.TOPE_GRADOS * 1.5      # tope duro del muelle
    # La ventana se para: el ángulo pasa al otro lado (rebote) y se asienta en 0 exacto
    minimo, t_reposo = 0.0, None
    for _ in range(150):
        t += 1 / 30
        a = f.paso(t)
        minimo = min(minimo, a)
        if f.reposo and t_reposo is None:
            t_reposo = t
    assert minimo < -0.3, f"sin rebote ({minimo})"
    assert t_reposo is not None and f.angulo == 0.0 and f.paso(t + 1) == 0.0
    assert f.vx == 0.0 and f.vy == 0.0


def test_a_la_izquierda_el_angulo_es_negativo():
    f = fx.FisicaSprite()
    f.mover(500, 0, 0.0)
    _, _, angulos = arrastrar(f, 0.0, 500, -800, 0.5)
    assert angulos[-1] < -4


def test_saltos_huecos_y_valores_raros_no_balancean():
    f = fx.FisicaSprite()
    f.mover(0, 0, 0.0)
    assert f.mover(1000, 0, 0.02) is False                           # salto > 400 px: por código
    assert f.vx == 0.0
    assert f.mover(1010, 0, 0.5) is False                            # hueco > 0.25 s: tramo nuevo
    assert f.mover(1012, 0, 0.501) is False                          # < 4 ms: se acumula
    assert f.mover(float("nan"), 0, 0.6) is False
    assert f.mover("x", 0, 0.6) is False
    assert f.mover(1020, 0, 0.51) is True                            # ahora sí (10 px en 10 ms)
    f.saltar(0, 0, 0.52)
    assert f.vx == 0.0 and f.vx_inst == 0.0
    assert math.isfinite(f.paso(float("inf")))
    f.reiniciar()
    assert f.reposo and f.angulo == 0.0


# ── Caras por velocidad y mareo ──────────────────────────────────────────────────

def test_clasificador_velocidad_con_histeresis():
    c = fx.ClasificadorVelocidad()
    assert c.actualizar(100, 0.0) == "tranquila"
    assert c.actualizar(450, 0.1) == "preocupada"
    assert c.actualizar(1600, 0.2) == "asustada"
    assert c.actualizar(1300, 0.3) == "asustada"                      # 1300 ≥ 1500·0.8
    assert c.actualizar(1100, 0.4) == "asustada"                      # < 1200 pero solo 0.2 s
    assert c.actualizar(1100, 0.7) == "preocupada"
    assert c.actualizar(float("nan"), 1.5) == "tranquila"
    assert fx.CARA_SPRITE["tranquila"] == "sad"


def test_detector_mareo():
    def agitar(d, n, v=1500.0, paso=0.3, t0=0.0):
        dis = False
        for i in range(n + 1):
            dis = d.actualizar(v if i % 2 == 0 else -v, 0.0, t0 + i * paso) or dis
        return dis

    assert agitar(fx.DetectorMareo(), 3) is False
    assert agitar(fx.DetectorMareo(), 4) is True
    assert agitar(fx.DetectorMareo(), 8, v=700) is False              # lentas
    assert agitar(fx.DetectorMareo(), 4, paso=0.55) is False          # fuera de la ventana de 1.5 s
    d = fx.DetectorMareo()
    assert agitar(d, 4) is True
    assert agitar(d, 10, t0=2.0) is False                             # enfriamiento de 10 s
    assert agitar(d, 5, t0=12.0) is True


# ── Respiración y mirada ─────────────────────────────────────────────────────────

def test_respiracion_periodo_4_s_y_amplitud_1_a_2_px():
    r = fx.RespiracionSprite(desfase=0.3)
    assert r.periodo == 4.0 and 1.0 <= r.amplitud <= 2.0
    for t in (0.0, 0.7, 1.3, 2.9):
        assert r.dy(t + 4.0) == pytest.approx(r.dy(t), abs=1e-9)
        assert r.dy(t + 2.0) == pytest.approx(-r.dy(t), abs=1e-9)
    muestras = [r.dy(i / 100) for i in range(400)]
    assert max(muestras) == pytest.approx(r.amplitud, abs=0.01)
    assert min(muestras) == pytest.approx(-r.amplitud, abs=0.01)
    assert {r.dy_px(i / 10) for i in range(40)} <= {-2, -1, 0, 1, 2}
    assert fx.RespiracionSprite(amplitud=9).amplitud == 2.0 and fx.RespiracionSprite(amplitud=0).amplitud == 1.0


def test_respiracion_desfase_sembrado_y_dormida_sin_saltos():
    a = fx.RespiracionSprite(rng=random.Random(1))
    b = fx.RespiracionSprite(rng=random.Random(1))
    c = fx.RespiracionSprite(rng=random.Random(2))
    assert a.dy(0.0) == b.dy(0.0) and a.dy(0.0) != c.dy(0.0)
    r = fx.RespiracionSprite(desfase=1.0)
    antes = r.dy(3.21)
    r.set_dormida(True, 3.21)
    assert r.periodo == 6.0 and r.amplitud == 2.0
    # Misma fase en el cambio: solo cambia la amplitud (1.5 → 2), sin salto de fase
    assert r.dy(3.21) == pytest.approx(antes * 2.0 / 1.5, abs=1e-9)
    assert r.dy(3.21 + 6.0) == pytest.approx(r.dy(3.21), abs=1e-9)
    r.set_dormida(True, 5.0)                                          # sin cambio
    r.set_dormida(False, 4.0)
    assert r.periodo == 4.0


def test_lado_mirada(qapp):
    from PyQt6.QtCore import QPoint, QPointF, QRect
    rect = (100, 100, 200, 300)                                       # centro x = 200
    assert fx.lado_mirada((150, 0), rect) == "izq"
    assert fx.lado_mirada((250, 900), rect) == "der"
    assert fx.lado_mirada((200, 0), rect) == "der"                    # en el centro exacto: der
    assert fx.lado_mirada(QPoint(10, 10), QRect(100, 100, 200, 300)) == "izq"
    assert fx.lado_mirada(QPointF(299.5, 10), QRect(100, 100, 200, 300)) == "der"
    # Histéresis: cerca del centro se queda como estaba
    assert fx.lado_mirada((205, 0), rect, actual="izq", histeresis=10) == "izq"
    assert fx.lado_mirada((195, 0), rect, actual="der", histeresis=10) == "der"
    assert fx.lado_mirada((215, 0), rect, actual="izq", histeresis=10) == "der"
    assert fx.lado_mirada((205, 0), rect, actual="raro", histeresis=10) == "der"


def test_margen_lienzo_cabe_el_giro():
    w, h = 120, 240
    assert fx.margen_lienzo(w, h, 0) == (0, 0)
    mx, my = fx.margen_lienzo(w, h, 6)
    assert mx > 0 and my >= 0
    px, py = 0.5 * w, 0.06 * h
    for g in (-6, 6):
        r = math.radians(g)
        for ex, ey in ((0, 0), (w, 0), (0, h), (w, h)):
            x = (ex - px) * math.cos(r) - (ey - py) * math.sin(r) + px
            y = (ex - px) * math.sin(r) + (ey - py) * math.cos(r) + py
            assert -mx - 1e-6 <= x <= w + mx + 1e-6 and -my - 1e-6 <= y <= h + my + 1e-6


# ── Imagen: recorte, región y sprite girado ──────────────────────────────────────

def _sprite(w=60, h=100):
    """Fondo casi negro con una figura clara (rectángulo 20..40 × 10..90)."""
    from PyQt6.QtGui import QColor, QImage
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(8, 11, 22))
    for y in range(10, 90):
        for x in range(20, 40):
            img.setPixelColor(x, y, QColor(0, 229, 255))
    return img


def _pixeles_opacos(img):
    return sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 0)


def test_recortar_fondo_y_region(qapp):
    from PyQt6.QtGui import QImage
    base = fx.recortar_fondo(_sprite())
    assert base.format() == QImage.Format.Format_ARGB32_Premultiplied
    assert base.pixelColor(0, 0).alpha() == 0                         # fondo oscuro → transparente
    assert base.pixelColor(30, 50).alpha() == 255
    assert _pixeles_opacos(base) == 20 * 80
    reg = fx.region_silueta(base)
    assert reg.boundingRect().getRect() == (20, 10, 20, 80)
    vacia = QImage(10, 10, QImage.Format.Format_ARGB32_Premultiplied)
    from PyQt6.QtCore import Qt
    vacia.fill(Qt.GlobalColor.transparent)
    assert fx.region_silueta(vacia).isEmpty()


def test_sprite_rotado_no_recorta_la_silueta(qapp):
    """Crítica c.8: girar dentro de un lienzo con margen y recalcular la región."""
    sr = fx.SpriteRotado(_sprite())
    w, h = sr.tamano_sprite
    assert (w, h) == (60, 100)
    lw, lh = sr.lienzo
    assert lw == w + 2 * sr.margen[0] and lh == h + 2 * sr.margen[1]
    recto, reg0 = sr.componer(0.0)
    assert (recto.width(), recto.height()) == (lw, lh)
    mx, my = sr.margen
    assert reg0.boundingRect().getRect() == (mx + 20, my + 10, 20, 80)      # sin giro: mismo sitio
    area = _pixeles_opacos(recto)
    for g in (-sr.tope_grados, sr.tope_grados, 20.0):                       # 20° se recorta al tope
        img, reg = sr.componer(g, dy=2)
        assert abs(_pixeles_opacos(img) - area) / area < 0.08, g          # la figura entera, sin cortes
        br = reg.boundingRect()
        assert br.left() >= 0 and br.top() >= 0 and br.right() < lw and br.bottom() < lh
        assert br != reg0.boundingRect()                                    # la región se recalcula
    # Caché: la misma petición devuelve el mismo fotograma
    a = sr.componer(3.0, dy=1)
    assert sr.componer(3.05, dy=1) is a                                      # mismo ángulo cuantizado
    # Espejo y atenuado
    esp, _ = sr.componer(0.0, espejo=True)
    assert esp.pixelColor(mx + 30, my + 50).alpha() == 255
    osc, _ = sr.componer(0.0, atenuar=1.0)
    assert osc.pixelColor(mx + 30, my + 50).blue() < 30
    assert osc.pixelColor(0, 0).alpha() == 0


# ── FisicaSpriteQt ───────────────────────────────────────────────────────────────

class Espia:
    def __init__(self, obj):
        self.angulos, self.movimientos, self.caras, self.mareos = [], [], [], 0
        obj.angulo.connect(self.angulos.append)
        obj.movimiento.connect(self.movimientos.append)
        obj.cara.connect(self.caras.append)
        obj.mareo.connect(self._mareo)

    def _mareo(self):
        self.mareos += 1


def test_fisica_qt_timer_solo_mientras_se_mueve(qapp):
    reloj = Reloj()
    q = fx.FisicaSpriteQt(reloj=reloj)
    e = Espia(q)
    assert not q.activo
    x = 0.0
    q.mover(x, 0)                                                     # referencia
    assert not q.activo and e.movimientos == []
    for i in range(36):                                               # 0.6 s a 600 px/s
        reloj.avanzar(1 / 60)
        x += 10
        q.mover(x, 0)
        if i % 2:
            q._tick()
    assert q.activo and q.arrastrando
    assert e.movimientos == [True]
    assert e.caras[0] == "tranquila" and "preocupada" in e.caras
    assert e.angulos and max(e.angulos) > 4
    # Se para: fin del arrastre a los 0.3 s, rebote, 0.0 y el temporizador se apaga
    for _ in range(150):
        reloj.avanzar(1 / 30)
        q._tick()
        if not q.activo:
            break
    assert not q.activo and not q.arrastrando
    assert e.movimientos == [True, False]
    assert e.caras[-1] == ""
    assert e.angulos[-1] == 0.0 and min(e.angulos) < 0
    n = len(e.angulos)
    q._tick()
    assert len(e.angulos) == n                                        # sin cambios, no emite


def test_fisica_qt_con_boton_pulsado_sigue_arrastrando(qapp):
    reloj = Reloj()
    pulsado = [True]
    q = fx.FisicaSpriteQt(reloj=reloj, boton=lambda: pulsado[0])
    e = Espia(q)
    q.mover(0, 0)
    for i in range(20):
        reloj.avanzar(1 / 60)
        q.mover((i + 1) * 10, 0)
    for _ in range(60):                                               # 2 s quieta con el botón
        reloj.avanzar(1 / 30)
        q._tick()
    assert q.arrastrando and q.activo and e.movimientos == [True]
    assert e.caras[-1] == "tranquila"                                 # quieta → tranquila
    pulsado[0] = False
    reloj.avanzar(1 / 30)
    q._tick()
    assert not q.arrastrando and e.movimientos == [True, False]


def test_fisica_qt_mareo(qapp):
    reloj = Reloj()
    q = fx.FisicaSpriteQt(reloj=reloj)
    e = Espia(q)
    x = 500.0
    q.mover(x, 0)
    for i in range(90):                                               # ±1500 px/s cambiando cada 0.2 s
        reloj.avanzar(1 / 60)
        x += (25 if (i // 12) % 2 == 0 else -25)
        q.mover(x, 0)
        if i % 2:
            q._tick()
    assert e.mareos == 1


def test_fisica_qt_vigilar_ventana_y_deshabilitar(qapp):
    from PyQt6.QtCore import QCoreApplication, QPoint
    from PyQt6.QtGui import QMoveEvent
    from PyQt6.QtWidgets import QWidget
    reloj = Reloj()
    w = QWidget()
    q = fx.FisicaSpriteQt(reloj=reloj)
    e = Espia(q)
    q.vigilar(w)
    x = 0
    for i in range(20):
        reloj.avanzar(1 / 60)
        x += 12
        QCoreApplication.sendEvent(w, QMoveEvent(QPoint(x, 0), QPoint(x - 12, 0)))
    assert q.activo and e.movimientos == [True]
    for _ in range(5):
        reloj.avanzar(1 / 30)
        q._tick()
    assert e.angulos and e.angulos[-1] != 0.0
    q.set_habilitado(False)
    assert not q.habilitado and not q.activo
    assert e.angulos[-1] == 0.0 and e.movimientos == [True, False]
    reloj.avanzar(1 / 60)
    QCoreApplication.sendEvent(w, QMoveEvent(QPoint(x + 12, 0), QPoint(x, 0)))
    assert not q.activo                                               # deshabilitada no escucha
    q.set_habilitado(True)
    q.dejar()
    reloj.avanzar(1 / 60)
    QCoreApplication.sendEvent(w, QMoveEvent(QPoint(x + 24, 0), QPoint(x + 12, 0)))
    reloj.avanzar(1 / 60)
    QCoreApplication.sendEvent(w, QMoveEvent(QPoint(x + 36, 0), QPoint(x + 24, 0)))
    assert not q.activo                                               # ya no vigila
    w.deleteLater()


def test_respiracion_qt(qapp):
    reloj = Reloj(0.0)
    r = fx.RespiracionSpriteQt(reloj=reloj, respiracion=fx.RespiracionSprite(desfase=0.0, t0=0.0))
    valores = []
    r.dy.connect(valores.append)
    r.iniciar()
    assert r.activo and valores == [0]                                # emite al empezar
    reloj.avanzar(0.05)
    r._tick()
    assert valores == [0]                                             # mismo píxel: no emite
    reloj.avanzar(0.85)                                               # t = 0.9 s: −1.5·sin(0.45π) ≈ −1.48
    r._tick()
    assert valores == [0, -1]
    r.set_dormida(True)
    assert r.respiracion.dormida and r.respiracion.periodo == 6.0
    reloj.avanzar(0.1)
    r._tick()
    assert valores[-1] == -2                                          # dormida: 2 px
    r.detener()
    assert not r.activo and valores[-1] == 0                          # la deja en su sitio
    n = len(valores)
    r.detener()
    assert len(valores) == n
