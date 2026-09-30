"""
Tests de ui/asiento_qt.ControlAsiento (offscreen, corte 7): el delegado de
arrastre mueve en px físicos; al encajar pide la prioridad «sentada», sienta a la
asistente y la pone justo encima de la ventana; sin «sentarse en ventanas» no
enumera; con un juego delante ni enumera ni encaja; sentada va a 15 Hz y a 60 Hz
un rato cuando la ventana se mueve; minimizada se levanta; ceder por la pantalla
grande y reanudar; la barra reafirma «siempre encima» cada 2 s; los sprites
encajan al soltar; el punto de asiento se vuelve a medir; la herramienta desde
otro hilo; detener idempotente. Asistente, ventanas, pantalla, cursor y reloj
falsos; ServiciosEscritorio y BusEstado reales.
"""
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from servicios.win_pantalla import Rect  # noqa: E402
from ventanas_falsas_c78 import (ApiVentanasFalsa, Config, EntradaFalsa, PantallaFalsa,  # noqa: E402
                                 Reloj, V, VentanaPropiaFalsa)

PROPIA = 0x7000
BLOC = (300, 400, 1100, 900)
RECT_M = (100, 100, 400, 600)                   # la ventana de la asistente: 300×500


class AsistenteFalsa(QObject):
    """Cumple el contrato de la asistente de los cortes 7/8 (CompanionFlotante)."""
    arrastre_cambio = pyqtSignal(bool)

    def __init__(self, dpr=1.0, render="vrm", punto=None, sincrono=True):
        super().__init__()
        self.dpr, self.render = dpr, render
        self.punto = punto or {"asiento": [150, 400], "sonda": [150, 420]}
        self.sincrono = sincrono
        self.delegado = None
        self.asientos, self.cbs_asiento, self.pendientes = [], [], []
        self.restauraciones = 0
        self.visible = True
        self.hilos = []

    def hwnd(self):
        return PROPIA

    def devicePixelRatioF(self):
        return self.dpr

    def isVisible(self):
        return self.visible

    def set_arrastre_delegado(self, fn):
        self.delegado = fn

    def punto_asiento(self, cb):
        if self.sincrono:
            cb(dict(self.punto))
        else:
            self.pendientes.append(cb)

    def asiento(self, on, modo="", variante=0, cb=None):
        self.hilos.append(threading.get_ident())
        self.asientos.append((on, modo, variante))
        if cb is not None:
            self.cbs_asiento.append(cb)

    def restaurar_orden_z(self):
        self.restauraciones += 1

    def windowHandle(self):
        return None


class SpritesFalsos(AsistenteFalsa):
    """AvatarOverlay: arrastre nativo, sin delegado."""
    set_arrastre_delegado = None

    def __init__(self, **kw):
        super().__init__(render="sprites", **kw)


class Entorno:
    pass


def _montar(qapp, config=None, asistente=None, ventanas=None, pantalla=None, en_ui=None, activa=0):
    from ui.asiento_qt import ControlAsiento
    from ui.escritorio import ServiciosEscritorio
    import random
    e = Entorno()
    e.cfg = config or Config()
    e.esc = ServiciosEscritorio(e.cfg)
    e.api = ApiVentanasFalsa(ventanas if ventanas is not None else {2: V(BLOC)}, activa=activa)
    e.pantalla = pantalla or PantallaFalsa()
    e.win = VentanaPropiaFalsa({PROPIA: RECT_M})
    e.cursor = EntradaFalsa(500, 500)
    e.reloj = Reloj()
    e.ctl = ControlAsiento(e.esc, e.cfg, api=e.api, ventana=e.win, entrada=e.cursor, pantalla=e.pantalla,
                           hwnd_principal=lambda: 0, en_ui=en_ui, reloj=e.reloj, azar=random.Random(3))
    e.esc.registrar("asiento", e.ctl, ("sentada",))
    e.esc.iniciar()
    e.m = asistente or AsistenteFalsa()
    e.esc.set_asistente(e.m)
    e.estados, e.sentadas, e.levantadas = [], [], []
    e.ctl.cambio.connect(lambda s: e.estados.append(json.loads(s)))
    e.ctl.sentada.connect(lambda modo, v: e.sentadas.append((modo, v)))
    e.ctl.levantada.connect(e.levantadas.append)
    return e


@pytest.fixture
def entorno(qapp):
    creados = []

    def crear(**kw):
        e = _montar(qapp, **kw)
        creados.append(e)
        return e
    yield crear
    for e in creados:
        e.esc.cerrar()
        e.ctl.deleteLater()


def bus(e):
    return e.esc.estado.actual()


def mover_cursor(e, x, y, dt=0.02):
    e.reloj.t += dt
    e.cursor.c = (x, y)
    return e.m.delegado() if e.m.delegado else None


def sentar_arrastrando(e):
    """Arrastra la asistente hasta que la sonda (150, 420) queda en (700, 410), el borde del
    Bloc, y la deja ahí quieta medio segundo (sin MouseMove: el tic del arrastre)."""
    e.m.arrastre_cambio.emit(True)
    assert e.m.delegado is not None
    mover_cursor(e, 520, 500)
    assert mover_cursor(e, 950, 390) is True          # llega al borde
    assert bus(e).sentada == ""
    quieta(e, 0.5)
    assert bus(e).sentada == "ventana"


def quieta(e, s, paso=1 / 15):
    """El ratón quieto `s` segundos durante el arrastre: solo corre el tic del arrastre."""
    fin = e.reloj.t + s
    while e.reloj.t < fin - 1e-9:
        e.reloj.t = min(fin, e.reloj.t + paso)
        e.ctl._tic_arrastre()


def tics_hasta_quieta(e, n=200):
    for _ in range(n):
        e.reloj.t += 1 / 60
        e.ctl._tic()
        if not e.ctl.maquina.suavizando:
            return
    raise AssertionError("no se quedó quieta")


# ── Arrastre manual ────────────────────────────────────────────────────────────

def test_el_delegado_mueve_en_px_fisicos(entorno):
    e = entorno(asistente=AsistenteFalsa(dpr=1.5))
    e.m.arrastre_cambio.emit(True)
    assert mover_cursor(e, 530, 520) is True
    assert e.win.de("mover")[-1] == ("mover", PROPIA, 130, 120)
    assert bus(e).sentada == ""


def test_encaja_pide_la_prioridad_sienta_y_coloca_sobre_la_ventana(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    assert e.api.n_enumerar >= 1
    on, modo, variante = e.m.asientos[-1]
    assert (on, modo) == (True, "ventana") and 0 <= variante <= 3
    assert ("colocar_sobre", PROPIA, 2) in e.win.llamadas
    assert e.sentadas == [("ventana", variante)]
    assert e.estados[-1]["sentada"] == "ventana"
    # clavado provisional con la sonda: la ventana va hacia (700 − 150, 400 − 420)
    x, y = e.win.rects[PROPIA][:2]
    assert x > 100 and y < 100


def test_sentada_arrastrando_desliza_por_el_borde_y_al_soltar_queda_clavada(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    for _ in range(40):                                # que el SmoothDamp llegue
        mover_cursor(e, 950, 390, dt=1 / 60)
    assert e.win.rects[PROPIA][:2] == (550, -20)
    mover_cursor(e, 1050, 392)                         # desliza a la derecha, sin salir de la banda
    assert e.win.rects[PROPIA][:2] == (650, -20)
    assert e.ctl.maquina.sentada.frac == pytest.approx(0.625)
    e.m.arrastre_cambio.emit(False)
    assert e.m.delegado is None and e.ctl._t_tic.isActive()
    assert bus(e).sentada == "ventana"


def test_arrastrarla_lejos_la_levanta(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    e.reloj.t += 1.0                                   # pasado el bloqueo
    mover_cursor(e, 950, 200)
    assert bus(e).sentada == "" and e.levantadas == ["arrastre"]
    assert e.m.asientos[-1][0] is False and e.m.restauraciones == 1
    assert e.win.rects[PROPIA][:2] == (100 + 450, 100 - 300)        # libre, con el cursor


def test_sin_sentarse_en_ventanas_no_enumera(entorno):
    e = entorno(config=Config(sentarse_ventanas=False, sentarse_barra=True))
    sentar = e.m.arrastre_cambio.emit
    sentar(True)
    mover_cursor(e, 950, 390)
    quieta(e, 0.6)
    assert e.api.n_enumerar == 0 and bus(e).sentada == ""
    assert e.pantalla.n > 0                            # la barra sí se mira…
    assert e.ctl._t_enum.interval() == e.ctl.BARRA_MS  # …a 4 Hz


def test_sin_nada_activo_no_instala_el_delegado(entorno):
    e = entorno(config=Config(sentarse_ventanas=False, sentarse_barra=False))
    e.m.arrastre_cambio.emit(True)
    assert e.m.delegado is None and not e.ctl._t_enum.isActive()


def test_con_un_juego_delante_ni_enumera_ni_encaja(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    e.esc.prioridad.iniciar("juego")
    e.m.arrastre_cambio.emit(True)
    assert e.m.delegado is None
    e.ctl._refrescar()
    assert e.api.n_enumerar == 0 and e.pantalla.n == 0
    assert e.ctl.sentar("barra") == (False, "Ahora no puedo: hay un juego delante.")


def test_si_la_tabla_no_deja_no_se_sienta(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    e.esc.prioridad.iniciar("alarma")
    assert e.ctl.sentar("barra") == (False, "Ahora no puedo sentarme: está sonando una alarma.")
    e.m.arrastre_cambio.emit(True)
    mover_cursor(e, 950, 390)
    quieta(e, 0.6)
    assert bus(e).sentada == "" and e.m.asientos == []


# ── Sentada y quieta ───────────────────────────────────────────────────────────

def test_15_hz_sentada_y_60_hz_medio_segundo_si_la_ventana_se_mueve(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    assert e.ctl.sentar("ventana") == (True, "Me senté en una ventana.")
    assert e.ctl._t_tic.isActive() and e.ctl._t_tic.interval() == e.ctl.RAPIDO_MS      # deslizándose
    tics_hasta_quieta(e)
    e.ctl._tic()
    assert e.ctl._t_tic.interval() == e.ctl.TIC_MS == 66
    pos = e.win.rects[PROPIA][:2]
    e.api.v[2].rect = Rect(340, 380, 1140, 880)        # el Bloc se mueve
    e.reloj.t += 1 / 15
    e.ctl._tic()
    assert e.ctl._t_tic.interval() == 16
    assert e.win.rects[PROPIA][:2] == (pos[0] + 40, pos[1] - 20)   # rígida, sin retraso
    e.reloj.t += 0.6
    e.ctl._tic()
    assert e.ctl._t_tic.interval() == 66


def test_cada_tic_la_vuelve_a_poner_encima_si_otra_se_colo(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    tics_hasta_quieta(e)
    antes = len(e.win.de("colocar_sobre"))
    e.ctl._tic()
    assert len(e.win.de("colocar_sobre")) == antes     # ya estaba encima
    e.win.encima = False                               # el usuario hizo clic en el Bloc
    e.reloj.t += 1 / 15
    e.ctl._tic()
    assert len(e.win.de("colocar_sobre")) == antes + 1


@pytest.mark.parametrize("cambio,motivo", [
    (lambda v: setattr(v, "min", True), "minimizada"),
    (lambda v: setattr(v, "max", True), "maximizada"),
    (lambda v: setattr(v, "vive", False), "cerrada"),
    (lambda v: setattr(v, "cloak", True), "cloaked"),
    (lambda v: setattr(v, "es_visible", False), "oculta"),
    (lambda v: setattr(v, "rect", Rect(0, 0, 1920, 1080)), "pantalla_completa"),
    (lambda v: setattr(v, "rect", Rect(300, -10, 1100, 500)), "fuera"),
])
def test_la_ventana_objetivo_la_levanta(entorno, cambio, motivo):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    tics_hasta_quieta(e)
    cambio(e.api.v[2])
    e.reloj.t += 1 / 15
    e.ctl._tic()
    assert e.levantadas == [motivo]
    assert e.m.asientos[-1] == (False, "", 0) and e.m.restauraciones == 1
    assert bus(e).sentada == "" and not e.ctl._t_tic.isActive() and not e.ctl._t_remedir.isActive()


def test_la_barra_reafirma_siempre_encima_cada_2_s(entorno):
    e = entorno()
    assert e.ctl.sentar("barra") == (True, "Me senté en la barra de tareas.")
    assert e.m.asientos[-1] == (True, "barra", 0) and bus(e).sentada == "barra"
    assert e.win.de("set_encima") == [("set_encima", PROPIA, True)]
    tics_hasta_quieta(e)
    n = len(e.win.de("set_encima"))
    e.reloj.t += 1.0
    e.ctl._tic()
    assert len(e.win.de("set_encima")) == n
    e.reloj.t += 1.1
    e.ctl._tic()
    assert len(e.win.de("set_encima")) == n + 1
    assert not e.win.de("colocar_sobre")


def test_sentada_en_la_barra_el_asiento_queda_en_su_borde(entorno):
    e = entorno()
    e.ctl.sentar("barra")
    e.m.cbs_asiento[-1]({"asiento": [150, 400], "sonda": [150, 420]})
    tics_hasta_quieta(e)
    x, y = e.win.rects[PROPIA][:2]
    assert y + 400 == 1032                            # el asiento en el borde de la barra


def test_el_asiento_medido_vuelve_a_clavar_con_suavizado(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    tics_hasta_quieta(e)
    e.m.cbs_asiento[-1]({"asiento": {"x": 140, "y": 380}, "sonda": {"x": 140, "y": 400}})
    assert e.ctl._asiento_rel == (140, 380) and e.ctl.maquina.suavizando
    tics_hasta_quieta(e)
    x, y = e.win.rects[PROPIA][:2]
    assert y + 380 == 400


def test_el_punto_de_asiento_se_remide_cada_segundo(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    e.m.cbs_asiento[-1](dict(e.m.punto))
    tics_hasta_quieta(e)
    assert e.ctl._t_remedir.isActive() and e.ctl._t_remedir.interval() == 1000
    n = len(e.win.de("mover"))
    e.ctl._remedir()                                   # igual: no se mueve
    assert len(e.win.de("mover")) == n
    e.m.punto = {"asiento": [150, 430], "sonda": [150, 450]}           # rueda: ahora es más grande
    e.ctl._remedir()
    assert len(e.win.de("mover")) == n + 1
    assert e.win.rects[PROPIA][1] + 430 == 400


def test_el_punto_de_un_pedido_viejo_no_pisa_el_asiento(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), asistente=AsistenteFalsa(sincrono=False))
    e.m.arrastre_cambio.emit(True)
    viejo = e.m.pendientes[-1]                          # pedido antes de sentarse
    e.m.pendientes.clear()
    mover_cursor(e, 520, 500)
    mover_cursor(e, 950, 390)
    quieta(e, 0.5)
    assert bus(e).sentada == "ventana"
    rel = e.ctl._asiento_rel
    viejo({"asiento": [1, 1], "sonda": [1, 1]})
    assert e.ctl._asiento_rel == rel


# ── Ceder y reanudar ───────────────────────────────────────────────────────────

def test_ceder_por_la_pantalla_grande_y_reanudar_en_la_misma_ventana(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    variante = e.m.asientos[-1][2]
    assert e.esc.prioridad.iniciar("grande")
    assert bus(e).sentada == "" and e.m.asientos[-1] == (False, "", 0)
    assert e.levantadas == ["cede"] and e.ctl.estado()["cedida"]
    e.esc.prioridad.terminar("grande")
    assert bus(e).sentada == "ventana"
    assert e.m.asientos[-1] == (True, "ventana", variante)
    assert e.ctl.maquina.sentada.objetivo.hwnd == 2 and e.ctl._t_tic.isActive()


def test_si_la_ventana_ya_no_esta_al_reanudar_suelta_la_actividad(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    e.esc.prioridad.iniciar("grande")
    e.api.v[2].min = True
    e.esc.prioridad.terminar("grande")
    assert bus(e).sentada == "" and e.m.asientos[-1][0] is False and e.ctl.maquina.sentada is None


def test_bajate_durante_la_pantalla_grande_ya_no_la_vuelve_a_sentar(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    e.esc.prioridad.iniciar("grande")
    assert e.ctl.bajar() is True
    e.esc.prioridad.terminar("grande")
    assert bus(e).sentada == "" and e.ctl.maquina.sentada is None


def test_el_juego_la_levanta_y_al_acabar_vuelve(entorno):
    e = entorno()
    e.ctl.sentar("barra")
    e.esc.prioridad.iniciar("juego")
    assert bus(e).sentada == "" and e.m.restauraciones == 1
    e.esc.prioridad.terminar("juego")
    assert bus(e).sentada == "barra" and e.m.asientos[-1] == (True, "barra", 0)


# ── Sprites (arrastre nativo) ──────────────────────────────────────────────────

def test_los_sprites_encajan_al_soltar(entorno):
    m = SpritesFalsos(punto={"asiento": [150, 480], "sonda": [150, 480]})
    e = entorno(asistente=m)
    e.m.arrastre_cambio.emit(True)
    assert e.m.delegado is None                        # el SO mueve la ventana
    e.win.rects[PROPIA] = Rect(100, 550, 400, 1050)    # el SO la dejó con la figura sobre la barra
    e.cursor.c = (560, 950)
    e.reloj.t += 0.3
    e.m.arrastre_cambio.emit(False)
    assert bus(e).sentada == "barra" and e.m.asientos[-1] == (True, "barra", 0)
    assert e.win.de("set_encima")


def test_los_sprites_sentados_se_levantan_al_empezar_a_arrastrar(entorno):
    e = entorno(asistente=SpritesFalsos(punto={"asiento": [150, 480], "sonda": [150, 480]}))
    e.ctl.sentar("barra")
    e.m.arrastre_cambio.emit(True)
    assert bus(e).sentada == "" and e.levantadas == ["arrastre"]


# ── Asistente, órdenes y ciclo de vida ───────────────────────────────────────────

def test_asistente_oculta_se_levanta(entorno):
    e = entorno()
    e.ctl.sentar("barra")
    e.esc.estado.actualizar(visible=False)
    assert bus(e).sentada == "" and e.levantadas == ["oculta"]


def test_sin_asistente_o_cambiada_se_levanta(entorno):
    e = entorno()
    e.ctl.sentar("barra")
    e.esc.set_asistente(None)
    assert bus(e).sentada == "" and e.m.asientos[-1][0] is False
    assert e.ctl.sentar("barra") == (False, "Necesito estar a la vista para sentarme: sácame primero.")


def test_ordenes_y_textos(entorno):
    e = entorno(config=Config(sentarse_ventanas=False))
    assert e.ctl.sentar("ventana") == (False, "Sentarme en ventanas está desactivado (Ajustes → Sentarse).")
    assert e.ctl.bajar() is False
    assert e.ctl.sentar("barra")[0] is True and e.ctl.sentada_en == "barra"
    assert e.ctl.sentar("barra") == (True, "Me senté en la barra de tareas.")      # ya lo estaba
    assert e.ctl.sentar("bajar") == (True, "Vale, ya me bajé.")
    assert e.ctl.sentada_en == "" and e.levantadas == ["usuario"]
    e.cfg.set("avatar", "sentarse_ventanas", True)
    e.api.v.clear()
    e.api.orden.clear()
    assert e.ctl.sentar("ventana") == (False, "No encuentro una ventana donde sentarme.")


def test_sentarse_en_ventana_prefiere_la_activa_y_si_no_la_mas_alta_visible(entorno):
    vs = {5: V((1000, 300, 1800, 800)), 2: V(BLOC), 3: V((1000, 850, 1800, 1000))}
    e = entorno(config=Config(sentarse_ventanas=True), ventanas=vs, activa=2)
    e.api.orden = [5, 2, 3]
    e.ctl.sentar("ventana")
    assert e.ctl.maquina.sentada.objetivo.hwnd == 2                  # la activa
    e.ctl.bajar()
    e.api._activa = 0
    e.ctl.sentar("ventana")
    assert e.ctl.maquina.sentada.objetivo.hwnd == 5                  # sin activa: la más alta
    e.ctl.bajar()
    e.api.v[3] = V((200, 350, 700, 450))                             # otra tapa el borde de la activa
    e.api.orden = [3, 5, 2]
    e.api._activa = 2
    e.ctl.sentar("ventana")
    assert e.ctl.maquina.sentada.objetivo.hwnd == 3
    e.ctl.bajar()
    e.api.v[3].min = True
    e.api.v[5].min = True
    e.ctl.sentar("ventana")
    assert e.ctl.maquina.sentada.objetivo.hwnd == 2                  # ya nadie la tapa


def test_desactivar_ventanas_la_baja_de_la_ventana(entorno):
    e = entorno(config=Config(sentarse_ventanas=True), activa=2)
    e.ctl.sentar("ventana")
    e.cfg.set("avatar", "sentarse_ventanas", False)
    e.ctl.recargar_config()
    assert bus(e).sentada == ""


def test_herramienta_desde_otro_hilo(entorno, qapp):
    from ui.montaje_ocio import EnHiloQt
    e = entorno(en_ui=EnHiloQt())
    fn = e.ctl.herramientas()["asistente_sentarse"]
    caja = {}
    hilo = threading.Thread(target=lambda: caja.update(r=fn({"sitio": "barra"}, None)))
    hilo.start()
    while hilo.is_alive():
        qapp.processEvents()
    hilo.join()
    assert caja["r"] == "Me senté en la barra de tareas."
    assert e.m.hilos and set(e.m.hilos) == {threading.get_ident()}      # en el hilo de Qt
    hilo = threading.Thread(target=lambda: caja.update(r=fn({"sitio": "bajar"}, None)))
    hilo.start()
    while hilo.is_alive():
        qapp.processEvents()
    assert caja["r"] == "Vale, ya me bajé." and bus(e).sentada == ""


def test_detener_idempotente_sin_timers_vivos(entorno):
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    e.ctl.detener()
    e.ctl.detener()
    assert not any(t.isActive() for t in (e.ctl._t_tic, e.ctl._t_enum, e.ctl._t_remedir, e.ctl._t_arrastre))
    assert e.m.delegado is None and bus(e).sentada == "" and e.ctl.maquina.sentada is None


def test_estado_json(entorno):
    e = entorno(config=Config(sentarse_ventanas=True, sentarse_offset_px=99))
    st = e.ctl.estado()
    assert st == {"sentada": "", "variante": 0, "ventanas": True, "barra": True, "offset": 64,
                  "disponible": True, "juego": False, "arrastrando": False, "cedida": False}
    e.ctl.sentar("barra")
    assert e.estados[-1]["sentada"] == "barra"


# ── Revisión 7-10 ──────────────────────────────────────────────────────────────

def test_quieta_medio_segundo_sobre_el_borde_se_sienta_sin_mover_el_raton(entorno):
    """SV1: VRM/animada llegan al borde (antes del medio segundo) y se quedan QUIETAS: sin
    MouseMove no había muestra y no se sentaba nunca (README: «mantenme medio segundo»)."""
    e = entorno(config=Config(sentarse_ventanas=True))
    e.m.arrastre_cambio.emit(True)
    assert e.ctl._t_arrastre.isActive()              # el tic del arrastre manual
    mover_cursor(e, 950, 390, dt=0.2)                # en el borde a los 0.2 s
    assert bus(e).sentada == ""
    quieta(e, 0.4)
    assert bus(e).sentada == ""                      # 0.4 s sobre el borde: aún no
    quieta(e, 0.15)
    assert bus(e).sentada == "ventana"
    e.m.arrastre_cambio.emit(False)
    assert not e.ctl._t_arrastre.isActive() and bus(e).sentada == "ventana"


def test_soltarla_tras_medio_segundo_en_el_borde_la_sienta(entorno):
    """SV1: al soltar se intenta con la sonda (antes el manual soltaba sin mirar)."""
    e = entorno(config=Config(sentarse_ventanas=True))
    e.m.arrastre_cambio.emit(True)
    mover_cursor(e, 950, 390, dt=0.2)                # llega al borde
    e.reloj.t += 0.6                                 # sin tics (el timer no llegó a correr)
    e.m.arrastre_cambio.emit(False)
    assert bus(e).sentada == "ventana" and e.m.asientos[-1][:2] == (True, "ventana")
    e2 = entorno(config=Config(sentarse_ventanas=True))
    e2.m.arrastre_cambio.emit(True)
    mover_cursor(e2, 950, 390, dt=0.2)
    e2.reloj.t += 0.2                                # soltarla de pasada: no
    e2.m.arrastre_cambio.emit(False)
    assert bus(e2).sentada == ""


def test_el_smoothdamp_acaba_con_el_raton_quieto(entorno):
    """SV1: sentada arrastrando, llega el asiento medido con la pose sentada y se desliza
    hasta él con SmoothDamp; con el ratón quieto se quedaba a medias (sin MouseMove)."""
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    quieta(e, 0.3, paso=1 / 60)
    e.m.cbs_asiento[-1]({"asiento": [150, 250], "sonda": [150, 230]})     # 170 px más arriba
    assert e.ctl.maquina.suavizando
    quieta(e, 1 / 60, paso=1 / 60)
    assert e.ctl._t_arrastre.interval() == e.ctl.RAPIDO_MS                # 60 Hz mientras desliza
    quieta(e, 1.0, paso=1 / 60)
    assert not e.ctl.maquina.suavizando
    assert e.win.rects[PROPIA][:2] == (550, 150)     # el asiento (150, 250) clavado en (700, 400)
    assert e.ctl._t_arrastre.interval() == e.ctl.ARRASTRE_MS


def test_moverla_durante_la_cesion_ya_no_la_devuelve_a_la_ventana(entorno):
    """SV2: sentada, empieza un MMD (cede), la arrastras lejos y al acabar el MMD cruzaba la
    pantalla de vuelta a la ventana de antes."""
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    e.m.arrastre_cambio.emit(False)
    tics_hasta_quieta(e)
    e.esc.prioridad.iniciar("mmd")
    assert e.ctl.cedida and bus(e).sentada == ""
    e.cursor.c = (500, 500)
    e.m.arrastre_cambio.emit(True)                   # la coges durante el baile
    assert not e.ctl.cedida
    mover_cursor(e, 100, 100)
    e.m.arrastre_cambio.emit(False)
    dejada = e.win.rects[PROPIA][:2]
    e.esc.prioridad.terminar("mmd")
    assert bus(e).sentada == "" and e.ctl.maquina.sentada is None
    assert e.win.rects[PROPIA][:2] == dejada and e.m.asientos[-1][0] is False


def test_levantarse_en_la_misma_pasada_vuelve_a_la_sonda_de_pie(entorno):
    """SV3: sentada, la página da el asiento de la pose sentada; al soltarse arrastrando
    seguía con esa sonda (encajaba con el pecho). Vuelve la de pie."""
    e = entorno(config=Config(sentarse_ventanas=True))
    sentar_arrastrando(e)
    e.m.cbs_asiento[-1]({"asiento": [150, 250], "sonda": [150, 230]})     # pose sentada
    assert e.ctl._sonda_rel == (150, 230)
    e.reloj.t += 1.0
    mover_cursor(e, 950, 150)                        # tira hacia arriba: se suelta
    assert e.levantadas == ["arrastre"]
    assert e.ctl._asiento_rel == (150, 400) and e.ctl._sonda_rel == (150, 420)   # la de pie
    quieta(e, 0.3)                                   # un momento lejos (fin del bloqueo vertical)
    mover_cursor(e, 950, 390)                        # de vuelta: la sonda DE PIE en el borde
    quieta(e, 0.5)
    assert bus(e).sentada == "ventana"
    quieta(e, 1.0, paso=1 / 60)
    assert e.win.rects[PROPIA][1] == 400 - 420       # clavada por la sonda de pie, sin salto


def test_con_monitores_apilados_sigue_en_la_barra_de_su_monitor(entorno):
    """Sospecha: con un monitor debajo de otro y el asiento por encima del centro de la
    ventana (pose sentada, altura del asiento), el centro caía en el monitor de abajo y la
    clavaba en SU barra. Manda el monitor del asiento."""
    from servicios.win_pantalla import Monitor
    arriba = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032), True, "A")
    abajo = Monitor(202, Rect(0, 1080, 1920, 2160), Rect(0, 1080, 1920, 2112), False, "B")
    pant = PantallaFalsa(monitores=(arriba, abajo),
                         bandejas={"Shell_TrayWnd": {0x100: Rect(0, 1032, 1920, 1080)},
                                   "Shell_SecondaryTrayWnd": {0x200: Rect(0, 2112, 1920, 2160)}})
    e = entorno(pantalla=pant)
    assert e.ctl.sentar("barra")[0] is True
    e.m.cbs_asiento[-1]({"asiento": [150, 150], "sonda": [150, 170]})     # asiento muy arriba
    tics_hasta_quieta(e)
    for _ in range(5):
        e.reloj.t += 1 / 15
        e.ctl._tic()
    y = e.win.rects[PROPIA][1]
    assert y + 150 == 1032 and bus(e).sentada == "barra"                    # en la barra de A
    assert e.win.rects[PROPIA][1] + e.win.rects[PROPIA].alto // 2 > 1080    # (el centro está en B)


class PantallaAutoOculta(PantallaFalsa):
    def __init__(self):
        from servicios.win_pantalla import Monitor
        mon = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080), True, "A")
        super().__init__(monitores=(mon,), bandejas={"Shell_TrayWnd": {0x100: Rect(0, 1078, 1920, 1080)}},
                         auto_oculta=True)
        self.preguntas = 0

    def barra_auto_oculta(self):
        self.preguntas += 1                          # SHAppBarMessage: un mensaje a Explorer
        return True


def test_barra_auto_oculta_no_pregunta_a_explorer_en_cada_tic(entorno):
    e = entorno(pantalla=PantallaAutoOculta())
    assert e.ctl.sentar("barra")[0] is True
    tics_hasta_quieta(e)
    antes = e.pantalla.preguntas
    for _ in range(30):                              # 2 s sentada a 15 Hz
        e.reloj.t += 1 / 15
        e.ctl._tic()
    assert bus(e).sentada == "barra"
    assert e.pantalla.preguntas - antes <= 2         # antes: 30 (una por tic)
