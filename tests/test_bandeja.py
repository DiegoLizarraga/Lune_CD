"""
Tests de ui/bandeja.py (BandejaLune): un solo icono con el menú reconstruido en
aboutToShow, acciones por el Despachador (solo `triggered`), clic izquierdo →
Abrir Lune, clic central → asistente, tooltip ≤ 127 caracteres como mucho una vez
por segundo, avisos, QSS del tema, red de seguridad con la asistente y detener.
Con una fábrica de QSystemTrayIcon falsa (offscreen).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon  # noqa: E402

from nucleo.acciones_ui import ACCIONES, Contexto, Despachador  # noqa: E402
from nucleo.estado_asistente import BusEstado  # noqa: E402
from ui.bandeja import TOOLTIP_MAX, BandejaLune, texto_tooltip  # noqa: E402

R = QSystemTrayIcon.ActivationReason


class TrayFalso(QObject):
    activated = pyqtSignal(object)
    hay = True
    creados = []

    @staticmethod
    def isSystemTrayAvailable():
        return TrayFalso.hay

    def __init__(self, icono=None, parent=None):
        super().__init__(parent)
        self.menu = None
        self.tooltip = ""
        self.tooltips = []
        self.visible = False
        self.mensajes = []
        self.borrado = False
        TrayFalso.creados.append(self)

    def setContextMenu(self, m):
        self.menu = m

    def contextMenu(self):
        return self.menu

    def setToolTip(self, t):
        self.tooltip = t
        self.tooltips.append(t)

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def showMessage(self, *a):
        self.mensajes.append(a)

    def deleteLater(self):
        self.borrado = True
        super().deleteLater()


class ConfigFalsa:
    def __init__(self, acciones):
        self.d = {"bandeja": {"acciones": acciones}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)


@pytest.fixture
def bandeja(qapp):
    TrayFalso.hay = True
    TrayFalso.creados.clear()
    bus = BusEstado()
    desp = Despachador()
    hechos = []
    for i in ACCIONES:
        desp.registrar(i, lambda arg="", i=i: hechos.append((i, arg)))
    ctx = {"v": Contexto(modo="normal", render="vrm", asistente_visible=True, voz_on=True,
                         tema_preset="ambar")}
    b = BandejaLune(desp, bus, lambda: ctx["v"], ConfigFalsa(["voz", "comentar", "bailar"]),
                    icono=None, fabrica_tray=TrayFalso,
                    presets=lambda: ["cian", "ambar"])
    b.bus, b.hechos, b.ctx = bus, hechos, ctx
    yield b
    b.detener()


def acciones_de(menu: QMenu):
    """[(texto, submenú|None, acción)] sin separadores."""
    out = []
    for a in menu.actions():
        if a.isSeparator():
            continue
        out.append((a.text(), a.menu(), a))
    return out


def buscar(menu: QMenu, *ruta):
    actual = menu
    for i, texto in enumerate(ruta):
        for t, sub, a in acciones_de(actual):
            if t == texto:
                if i == len(ruta) - 1:
                    return a
                actual = sub
                break
        else:
            raise AssertionError(f"no está «{texto}» en {[t for t, _, _ in acciones_de(actual)]}")


def test_iniciar_pone_un_icono_con_menu(bandeja):
    bandeja.iniciar()
    bandeja.iniciar()                                  # idempotente: un solo icono
    assert len(TrayFalso.creados) == 1
    tray = bandeja.icono_tray
    assert tray.visible and tray.menu is not None
    textos = [t for t, _, _ in acciones_de(tray.menu)]
    assert textos[0] == "Abrir Lune" and textos[-1] == "Salir"
    abrir = acciones_de(tray.menu)[0][2]
    assert abrir.font().bold()
    assert tray.tooltip.startswith("Lune CD") and len(tray.tooltip) <= TOOLTIP_MAX


def test_sin_bandeja_del_sistema(bandeja):
    TrayFalso.hay = False
    bandeja.iniciar()
    assert bandeja.icono_tray is None
    assert bandeja.mostrar_aviso("t", "x") is False
    bandeja.refrescar_tooltip()                         # no revienta


def test_about_to_show_reconstruye_con_el_estado_actual(bandeja):
    bandeja.iniciar()
    menu = bandeja.icono_tray.menu
    voz = buscar(menu, "Lune", "Voz")
    assert voz.isCheckable() and voz.isChecked()
    assert buscar(menu, "Tema", "Ámbar").isChecked()
    assert buscar(menu, "Asistente en escritorio", "Dormir")
    # cambia el estado → al abrir otra vez el menú refleja lo nuevo
    bandeja.ctx["v"] = bandeja.ctx["v"]._replace(voz_on=False, asistente_visible=False)
    bandeja.bus.actualizar(durmiendo=True)
    menu.aboutToShow.emit()
    assert not buscar(menu, "Lune", "Voz").isChecked()
    with pytest.raises(AssertionError):
        buscar(menu, "Asistente en escritorio", "Dormir")               # sin asistente a la vista no se ofrece
    assert buscar(menu, "Asistente en escritorio", "Sacar a la asistente al escritorio")
    # «bailar» está en bandeja.acciones pero no se ve sin asistente: no sale
    assert "Bailar" not in [t for t, _, _ in acciones_de(buscar(menu, "Lune", "Voz").parent())]


def test_reconstruir_no_acumula_submenus(bandeja, qapp):
    bandeja.iniciar()
    menu = bandeja.icono_tray.menu
    for _ in range(5):
        menu.aboutToShow.emit()
    qapp.sendPostedEvents(None, 0)                      # procesa los deleteLater
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    vivos = [c for c in menu.findChildren(QMenu)]
    assert len(vivos) == len(bandeja._submenus)


def test_triggered_ejecuta_por_el_despachador_tras_cerrar_el_menu(bandeja, qapp):
    bandeja.iniciar()
    menu = bandeja.icono_tray.menu
    buscar(menu, "Tema", "Cian").trigger()
    buscar(menu, "Lune", "Voz").trigger()
    assert bandeja.hechos == []                         # todavía no: el menú se está cerrando
    qapp.processEvents()
    assert bandeja.hechos == [("tema", "cian"), ("voz", "")]
    # Trigger sobre un checkable NO se ejecuta dos veces ni por toggled
    bandeja.hechos.clear()
    menu.aboutToShow.emit()
    qapp.processEvents()
    assert bandeja.hechos == []


def test_clics_en_el_icono(bandeja, qapp):
    bandeja.iniciar()
    tray = bandeja.icono_tray
    tray.activated.emit(R.Trigger)
    tray.activated.emit(R.DoubleClick)
    tray.activated.emit(R.MiddleClick)
    tray.activated.emit(R.Context)
    assert bandeja.hechos == [("mostrar_lune", ""), ("mostrar_lune", ""), ("asistente", "")]


def test_tooltip_corto_y_como_mucho_una_vez_por_segundo(bandeja, qapp):
    from PyQt6.QtTest import QTest
    bandeja.iniciar()
    tray = bandeja.icono_tray
    bandeja.INTERVALO_TOOLTIP_MS = 150
    bandeja.bus.actualizar(juego=True, alarma=True, visible=True, durmiendo=True, llamada=True,
                           hablando=True, bailando="musica", grande=True)
    bandeja.refrescar_tooltip()
    n = len(tray.tooltips)
    bandeja.bus.actualizar(hablando=False)
    bandeja.refrescar_tooltip()
    bandeja.refrescar_tooltip()
    assert len(tray.tooltips) == n                       # agrupado: aún no
    QTest.qWait(250)
    assert len(tray.tooltips) == n + 1
    assert all(len(t) <= TOOLTIP_MAX for t in tray.tooltips)
    assert "modo juego" in tray.tooltip and "dormida en el escritorio" in tray.tooltip


def test_texto_tooltip_se_recorta():
    class E:
        juego = alarma = visible = llamada = hablando = grande = True
        durmiendo = pensando = False
        bailando = "x" * 300
    assert len(texto_tooltip(E())) <= TOOLTIP_MAX
    assert texto_tooltip(object()) == "Lune CD"


def test_avisos_y_qss(bandeja):
    bandeja.iniciar()
    assert bandeja.mostrar_aviso("Lune sigue aquí", "Ábreme desde la bandeja", 3000, "aviso")
    titulo, texto, icono, ms = bandeja.icono_tray.mensajes[-1]
    assert (titulo, ms, icono) == ("Lune sigue aquí", 3000, QSystemTrayIcon.MessageIcon.Warning)
    bandeja.aplicar_qss("QMenu { color: red; }")
    assert bandeja.icono_tray.menu.styleSheet() == "QMenu { color: red; }"
    assert all(s.styleSheet() == "QMenu { color: red; }" for s in bandeja._submenus)
    bandeja.icono_tray.menu.aboutToShow.emit()
    assert all(s.styleSheet() == "QMenu { color: red; }" for s in bandeja._submenus)


def test_set_asistente_quita_su_bandeja(bandeja):
    class Asistente:
        quitadas = 0

        def quitar_bandeja(self):
            Asistente.quitadas += 1
    bandeja.iniciar()
    bandeja.set_asistente(Asistente())
    bandeja.set_asistente(None)
    bandeja.set_asistente(object())                        # sin quitar_bandeja: se tolera
    assert Asistente.quitadas == 1


def test_detener_quita_el_icono_ya(bandeja):
    bandeja.iniciar()
    tray = bandeja.icono_tray
    bandeja.detener()
    assert bandeja.icono_tray is None and not tray.visible and tray.borrado
    bandeja.detener()                                    # idempotente
    bandeja.iniciar()                                    # y se puede volver a poner
    assert bandeja.icono_tray is not None and bandeja.icono_tray is not tray
