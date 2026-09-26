"""
Tests del menú radial en Qt (offscreen): el widget MenuRadial (elegir al soltar
fuera de la zona muerta; Esc, clic derecho, perder el foco o soltar en el centro
cierran sin elegir; teclado) y ControlMenuRadial (BusEstado.menu_abierto,
mascota.set_menu_abierto, sonidos, menu_pedido, ancla de la cabeza, segundo
radial de expresiones, detener).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from nucleo.acciones_ui import Contexto, Despachador, ItemRadial  # noqa: E402
from nucleo.estado_mascota import BusEstado  # noqa: E402
from ui.menu_radial import LIENZO, ControlMenuRadial, MenuRadial, centro_sector  # noqa: E402

C = LIENZO / 2


def items(n=4, deshabilitado=None):
    return [ItemRadial(f"id{i}", f"Botón {i}", "gear", arg=f"a{i}", habilitado=(i != deshabilitado))
            for i in range(n)]


def punto_boton(i, n, radio=130):
    import math
    a = math.radians(centro_sector(i, n))
    return QPointF(C + radio * math.sin(a), C - radio * math.cos(a))


def raton(w, tipo, p, boton=Qt.MouseButton.NoButton):
    botones = boton if tipo == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
    ev = QMouseEvent(tipo, QPointF(p), QPointF(w.mapToGlobal(QPointF(p))), boton, botones,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def mover(w, p):
    raton(w, QEvent.Type.MouseMove, p)


def clic(w, p, boton=Qt.MouseButton.LeftButton):
    raton(w, QEvent.Type.MouseMove, p)
    raton(w, QEvent.Type.MouseButtonPress, p, boton)
    raton(w, QEvent.Type.MouseButtonRelease, p, boton)


def tecla(w, k):
    QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))


def terminar_animacion(w, pasos=80):
    for _ in range(pasos):
        if not w.isVisible():
            return
        w._paso(1 / 60)


@pytest.fixture
def menu(qapp):
    m = MenuRadial()
    diario = []
    m.elegido.connect(lambda i, a: diario.append(("elegido", i, a)))
    m.cerrado.connect(lambda: diario.append(("cerrado",)))
    m.diario = diario
    yield m
    m.hide()
    m.deleteLater()


# ── Widget ────────────────────────────────────────────────────────────────────

def test_abrir_sin_botones_no_abre(menu):
    assert menu.abrir(QPoint(500, 500), []) is False
    assert not menu.isVisible() and not menu.abierto


def test_soltar_fuera_de_la_zona_muerta_elige(menu):
    assert menu.abrir(QPoint(600, 500), items(4)) is True
    assert menu.isVisible() and menu.abierto
    mover(menu, punto_boton(2, 4))
    assert menu.seleccion == 2
    clic(menu, punto_boton(2, 4))
    # primero se sueltan los bloqueos (cerrado) y luego se ejecuta (elegido)
    assert menu.diario == [("cerrado",), ("elegido", "id2", "a2")]
    assert menu.ultimo_por_eleccion and not menu.abierto
    terminar_animacion(menu)
    assert not menu.isVisible()


def test_soltar_en_la_zona_muerta_cierra_sin_elegir(menu):
    menu.abrir(QPoint(600, 500), items(3))
    clic(menu, QPointF(C + 20, C - 10))
    assert menu.diario == [("cerrado",)]
    assert not menu.ultimo_por_eleccion


def test_boton_deshabilitado_cierra_sin_elegir(menu):
    menu.abrir(QPoint(600, 500), items(4, deshabilitado=1))
    clic(menu, punto_boton(1, 4))
    assert menu.diario == [("cerrado",)]


@pytest.mark.parametrize("como", ["esc", "derecho", "central", "foco", "ocultar"])
def test_cerrar_sin_emitir_elegido(menu, como):
    menu.abrir(QPoint(600, 500), items(5))
    mover(menu, punto_boton(3, 5))
    if como == "esc":
        tecla(menu, Qt.Key.Key_Escape)
    elif como == "derecho":
        raton(menu, QEvent.Type.MouseButtonPress, punto_boton(3, 5), Qt.MouseButton.RightButton)
    elif como == "central":
        raton(menu, QEvent.Type.MouseButtonPress, punto_boton(3, 5), Qt.MouseButton.MiddleButton)
    elif como == "foco":
        QApplication.sendEvent(menu, QEvent(QEvent.Type.WindowActivate))
        QApplication.sendEvent(menu, QEvent(QEvent.Type.WindowDeactivate))
    else:
        menu.hide()                                 # Qt cierra el popup (clic fuera)
    assert menu.diario == [("cerrado",)]
    assert not menu.abierto
    # un segundo cierre no vuelve a emitir
    menu.cerrar()
    menu.hide()
    assert menu.diario == [("cerrado",)]


def test_desactivar_sin_haber_estado_activo_no_cierra(menu):
    # Si Windows no le dio el foco nunca, un Deactivate suelto no lo cierra.
    menu.abrir(QPoint(600, 500), items(2))
    QApplication.sendEvent(menu, QEvent(QEvent.Type.WindowDeactivate))
    assert menu.abierto


def test_teclado(menu):
    menu.abrir(QPoint(600, 500), items(3))
    mover(menu, QPointF(C, C))                      # centro: nada señalado
    assert menu.seleccion is None
    tecla(menu, Qt.Key.Key_Right)
    tecla(menu, Qt.Key.Key_Right)
    tecla(menu, Qt.Key.Key_Left)
    assert menu.seleccion == 0
    tecla(menu, Qt.Key.Key_Left)
    assert menu.seleccion == 2
    tecla(menu, Qt.Key.Key_Return)
    assert menu.diario == [("cerrado",), ("elegido", "id2", "a2")]


def test_pulsar_encoge_el_boton_y_la_animacion_converge(menu):
    menu.abrir(QPoint(600, 500), items(4))
    mover(menu, punto_boton(1, 4))
    raton(menu, QEvent.Type.MouseButtonPress, punto_boton(1, 4), Qt.MouseButton.LeftButton)
    for _ in range(120):
        menu._paso(1 / 60)
    assert menu._escala == pytest.approx(1.0)
    assert menu._esc_btn[1] == pytest.approx(0.8)
    assert menu._arco == pytest.approx(centro_sector(1, 4))
    assert not menu._timer.isActive()               # quieto: sin gastar CPU
    img = menu.grab()                                # pinta sin errores
    assert img.width() == LIENZO


def test_reabrir_mientras_se_cierra(menu):
    menu.abrir(QPoint(600, 500), items(2))
    for _ in range(30):
        menu._paso(1 / 60)                          # ya abierto del todo
    tecla(menu, Qt.Key.Key_Escape)
    menu._paso(1 / 60)
    assert menu.isVisible() and not menu.abierto     # animando la salida
    assert menu.abrir(QPoint(600, 500), items(3)) is True
    assert menu.abierto and len(menu.items) == 3


def test_set_colores_acepta_alias_y_css(menu):
    from ui.menu_radial import color_de, normalizar_colores
    c = normalizar_colores({"accent": "#FF00AA", "fondo": "#11223380", "texto": "rgb(1 2 3 / .5)"})
    assert c["acento"].name() == "#ff00aa"
    assert c["fondo"].alpha() == 0x80 and c["fondo"].name() == "#112233"
    assert c["texto"].alpha() == 128 and c["texto"].red() == 1
    assert color_de("no es un color", "#010203").name() == "#010203"
    menu.set_colores({"acento": "#123456"})
    assert menu._col["acento"].name() == "#123456"
    # Las claves de ui/tema_qss.colores_radial
    try:
        from ui.tema_qss import colores_radial
    except ImportError:
        return
    c = normalizar_colores(colores_radial())
    crudo = colores_radial()
    assert c["acento"].name() == crudo["acento"].lower()
    assert c["borde"].name() == crudo["acento_oscuro"].lower()
    assert c["fondo"].name() == crudo["fondo"].lower() and c["fondo"].alpha() < 255


# ── Controlador ───────────────────────────────────────────────────────────────

class MascotaFalsa(QObject):
    menu_pedido = pyqtSignal(str, object)

    def __init__(self, ancla_async=False):
        super().__init__()
        self.visible = True
        self.diario = []
        self.ancla_async = ancla_async
        self.callbacks = []

    def isVisible(self):
        return self.visible

    def set_menu_abierto(self, on):
        self.diario.append(("menu_abierto", on))

    def ancla_menu(self, cb):
        if self.ancla_async:
            self.callbacks.append(cb)
        else:
            cb(QPoint(390, 310))


class Config:
    def __init__(self, principal):
        self.d = {"menu_radial": {"principal": principal, "secundario": []}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)


@pytest.fixture
def control(qapp):
    bus = BusEstado()
    desp = Despachador()
    hechos = []
    for i in ("voz", "dormir", "ajustes", "chat"):
        desp.registrar(i, lambda arg="", i=i: hechos.append((i, arg)))
    sonidos = []
    ctx = {"v": Contexto(modo="normal", render="vrm", mascota_visible=True)}
    ctl = ControlMenuRadial(desp, bus, Config(["voz", "dormir", "ajustes", "bailar", "chat"]),
                            lambda: ctx["v"], sonar=sonidos.append)
    ctl.bus, ctl.desp, ctl.hechos, ctl.sonidos, ctl.ctx = bus, desp, hechos, sonidos, ctx
    yield ctl
    ctl.detener()


def test_control_abrir_pone_menu_abierto_y_elegir_ejecuta(control):
    assert control.abrir("principal", QPoint(600, 500)) is True
    m = control.menu
    assert [i.id for i in m.items] == ["voz", "dormir", "ajustes", "chat"]     # «bailar» sin handler
    assert control.bus.actual().menu_abierto is True
    assert control.sonidos == ["menu_abrir"]
    clic(m, punto_boton(1, 4))
    assert control.bus.actual().menu_abierto is False
    assert control.hechos == [("dormir", "")]
    assert control.sonidos == ["menu_abrir", "menu_boton"]                     # sin «menu_cerrar»


def test_control_esc_suena_cerrar_y_no_ejecuta(control):
    control.abrir("principal", QPoint(600, 500))
    tecla(control.menu, Qt.Key.Key_Escape)
    assert control.hechos == [] and control.sonidos == ["menu_abrir", "menu_cerrar"]
    assert control.bus.actual().menu_abierto is False


def test_control_arrastrando_no_abre_y_otra_vez_cierra(control):
    control.bus.actualizar(arrastrando=True)
    assert control.abrir("principal", QPoint(600, 500)) is False
    control.bus.actualizar(arrastrando=False)
    assert control.abrir("principal", QPoint(600, 500)) is True
    assert control.abrir("principal") is False                 # como F1 en ME: segunda vez cierra
    assert not control.abierto() and control.bus.actual().menu_abierto is False


def test_control_sin_botones_no_abre(control):
    assert control.abrir("secundario", QPoint(600, 500)) is False
    assert control.abrir("otro", QPoint(600, 500)) is False
    assert control.bus.actual().menu_abierto is False


def test_control_mascota_menu_pedido_y_bloqueos(control):
    masc = MascotaFalsa()
    control.set_mascota(masc)
    masc.menu_pedido.emit("principal", QPoint(410, 290))
    assert control.abierto()
    assert masc.diario == [("menu_abierto", True)]
    assert control.menu.centro_global() == QPoint(390, 310)     # en la cabeza, como en ME
    tecla(control.menu, Qt.Key.Key_Escape)
    assert masc.diario == [("menu_abierto", True), ("menu_abierto", False)]
    control.set_mascota(None)
    masc.menu_pedido.emit("principal", QPoint(650, 420))       # ya desconectada
    assert not control.abierto()


def test_control_ancla_de_la_cabeza_asincrona_y_seguir(control):
    masc = MascotaFalsa(ancla_async=True)
    control.set_mascota(masc)
    assert control.abrir("principal") is True                  # pendiente de la cabeza
    assert control.abierto() and (control.menu is None or not control.menu.abierto)
    masc.callbacks.pop(0)(QPoint(380, 300))
    assert control.menu.abierto and control.menu.centro_global() == QPoint(380, 300)
    assert control._seguir_t.isActive()
    # la cabeza se mueve: el menú se desliza hacia ella
    control._pedir_seguir()
    masc.callbacks.pop(0)(QPoint(420, 280))
    for _ in range(60):
        control.menu._paso(1 / 60)
    assert control.menu.centro_global() == QPoint(420, 280)


def test_control_clic_derecho_sin_ancla_abre_en_el_punto(control):
    class SinAncla(QObject):
        menu_pedido = pyqtSignal(str, object)

        def isVisible(self):
            return True
    m = SinAncla()
    control.set_mascota(m)
    m.menu_pedido.emit("principal", QPoint(410, 290))
    assert control.menu.centro_global() == QPoint(410, 290)


def test_control_clic_derecho_con_ancla_que_no_contesta_usa_el_punto(control, qapp):
    from PyQt6.QtTest import QTest
    masc = MascotaFalsa(ancla_async=True)
    control.set_mascota(masc)
    control.ESPERA_ANCLA_MS = 20
    masc.menu_pedido.emit("principal", QPoint(405, 295))
    QTest.qWait(80)
    assert control.menu.abierto and control.menu.centro_global() == QPoint(405, 295)


def test_control_ancla_que_no_contesta_abre_en_el_cursor(control, qapp):
    from PyQt6.QtTest import QTest
    masc = MascotaFalsa(ancla_async=True)
    control.set_mascota(masc)
    control.ESPERA_ANCLA_MS = 20
    assert control.abrir("principal") is True
    QTest.qWait(80)
    assert control.menu is not None and control.menu.abierto
    masc.callbacks[0](QPoint(1, 1))                            # respuesta tardía: se ignora
    assert control.menu.abierto


def test_control_expresiones_abre_segundo_radial(control):
    masc = MascotaFalsa()
    estados = []
    masc.set_estado = lambda e, ms: estados.append((e, ms))
    control.set_mascota(masc)
    control.desp.registrar("expresiones", lambda: control.abrir("expresiones"))
    control.desp.registrar("expresion", lambda arg="": masc.set_estado(arg, 4000))
    control._config.d["menu_radial"]["principal"] = ["expresiones", "voz"]
    control.abrir("principal", QPoint(600, 500))
    clic(control.menu, punto_boton(0, 2))
    assert control.menu.abierto and len(control.menu.items) == 6
    assert control.bus.actual().menu_abierto is True
    clic(control.menu, punto_boton(5, 6))
    assert estados == [("wave", 4000)]
    assert control.bus.actual().menu_abierto is False


def test_control_detener_cierra_sin_sonido_y_suelta(control):
    masc = MascotaFalsa()
    control.set_mascota(masc)
    control.abrir("principal", QPoint(600, 500))
    control.sonidos.clear()
    control.detener()
    assert control.menu is None and control.sonidos == []
    assert control.bus.actual().menu_abierto is False
    assert ("menu_abierto", False) in masc.diario
    masc.menu_pedido.emit("principal", QPoint(1, 1))
    assert not control.abierto()
    # El escritorio se reanuda: la mascota sigue enlazada y el clic derecho vuelve a abrir
    control.iniciar()
    masc.menu_pedido.emit("principal", QPoint(400, 300))
    assert control.abierto() and control.menu is not None


def test_control_set_colores_llega_al_menu(control):
    control.abrir("principal", QPoint(600, 500))
    control.set_colores({"acento": "#FF0080"})
    assert control.menu._col["acento"].name() == "#ff0080"
