"""
Tests de ui/pantalla_grande_qt.ControlPantallaGrande (offscreen), con el
ServiciosEscritorio de verdad (BusEstado y tabla de prioridades), una mascota
falsa que cumple el contrato (soporta_grande, geometria, set_geometria,
grande_fase, set_salvapantallas, mostrar_alarma…), VentanaReloj falsa, reloj
falso y una API de entrada falsa (GetLastInputInfo, cursor, clic, mando, estado
de energía): nada de Win32 de verdad.
"""
import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, QRect, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402

from nucleo.config import Config  # noqa: E402
from servicios import win_entrada as we  # noqa: E402
from servicios.win_entrada import EstadoMando  # noqa: E402
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from ui.pantalla_grande_qt import ControlPantallaGrande, indice_mayor_interseccion  # noqa: E402

GEOM = QRect(100, 120, 300, 420)


# ── Dobles ────────────────────────────────────────────────────────────────────

class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class MascotaFalsa(QObject):
    visibilidad = pyqtSignal(bool)

    def __init__(self, bus=None, render="vrm", lista=True, geom=GEOM):
        super().__init__()
        self.render = render
        self.lista = lista
        self.cerrado = False
        self.vis = True
        self.geom = QRect(geom)
        self.diario = []
        self.bus = bus
        self.bus_al_tocarla = None
        self.durmiendo = False

    @property
    def soporta_grande(self):
        return self.lista

    def _anotar(self, *x):
        if self.bus_al_tocarla is None and self.bus is not None:
            self.bus_al_tocarla = self.bus.actual()
        self.diario.append(x)

    def isVisible(self):
        return self.vis and not self.cerrado

    def geometria(self):
        self._anotar("geometria")
        return QRect(self.geom)

    def set_geometria(self, r):
        self._anotar("set_geometria", QRect(r))
        self.geom = QRect(r)

    def grande_fase(self, fase, opciones):
        self._anotar("fase", fase, dict(opciones))

    def set_salvapantallas(self, on, *, fondo_oscuro=True, reloj=True):
        self._anotar("salvapantallas", bool(on), fondo_oscuro, reloj)
        self.durmiendo = bool(on)

    def mostrar_alarma(self, texto, retraso_ms=3000):
        self._anotar("alarma", texto)

    def ocultar_alarma(self):
        self._anotar("alarma", None)

    def despertar(self):
        self._anotar("despertar")
        self.durmiendo = False
        return True

    def close(self):
        self._anotar("close")
        self.cerrado = True
        self.vis = False

    def fases(self):
        return [d[1] for d in self.diario if d[0] == "fase"]

    def geometrias(self):
        return [d[1] for d in self.diario if d[0] == "set_geometria"]


class VentanaFalsa(QObject):
    apagar = pyqtSignal()
    posponer = pyqtSignal()
    cerrar_pedido = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.modo = ""
        self.visible = False
        self.ocultandose = False
        self.diario = []

    def mostrar(self, modo, *, pantalla=None, fondo_oscuro=True, reloj=True, cara=None):
        self.modo, self.visible = modo, True
        self.diario.append(("mostrar", modo, fondo_oscuro, reloj))

    def set_alarma(self, texto, *, bloqueo_ms=0):
        self.diario.append(("alarma", texto, bloqueo_ms))

    def ocultar(self, ms=500):
        self.visible = False
        self.diario.append(("ocultar", ms))

    def isVisible(self):
        return self.visible


class ApiFalsa:
    """Sesión de Windows de mentira: inactividad, cursor, clic, mando y energía."""

    def __init__(self):
        self.ultima = 500_000
        self.t = 500_000
        self.pos = (10, 10)
        self.clic = False
        self.mando = None
        self.ejecucion = 0

    def inactivo(self, s):
        self.t = self.ultima + int(s * 1000)

    def tecla(self):
        self.ultima = self.t = self.t + 10

    def tick(self):
        return self.t

    def ultima_entrada(self):
        return self.ultima

    def cursor(self):
        return self.pos

    def boton_izquierdo(self):
        return self.clic

    def hay_xinput(self):
        return self.mando is not None

    def estado_mando(self, i):
        return self.mando if i == 0 else None

    def estado_ejecucion(self):
        return self.ejecucion


class AnfitrionFalso:
    modo = "normal"

    def __init__(self, esc, crea_lista=False):
        self.esc = esc
        self.crea_lista = crea_lista
        self.creadas = []

    def mascota(self):
        return self.creadas[-1] if self.creadas and not self.creadas[-1].cerrado else None

    def alternar_mascota(self):
        m = MascotaFalsa(self.esc.estado, lista=self.crea_lista)
        self.creadas.append(m)
        self.esc.set_mascota(m)
        return True


def montar(qapp, *, mascota=True, lista=True, render="vrm", cfg=None, anfitrion=None, activo=False):
    cfg = cfg or ConfigFalsa()
    cfg.set("avatar", "render", render)
    if activo:
        cfg.set("salvapantallas", "activo", True)
    esc = ServiciosEscritorio(cfg)
    reloj = Reloj()
    api = ApiFalsa()
    ventanas = []

    def fabrica():
        v = VentanaFalsa()
        ventanas.append(v)
        return v
    anf = anfitrion(esc) if callable(anfitrion) else anfitrion
    ctl = ControlPantallaGrande(esc, cfg, anfitrion=anf, api_entrada=api, fabrica_reloj=fabrica,
                                reloj=reloj, hay_webengine=lambda: True)
    cambios = []
    ctl.cambio.connect(lambda a, m: cambios.append((a, m)))
    esc.registrar("grande", ctl, ("grande", "salvapantallas"))
    m = None
    if mascota:
        m = MascotaFalsa(esc.estado, render=render, lista=lista)
        esc.set_mascota(m)
    return SimpleNamespace(esc=esc, ctl=ctl, m=m, reloj=reloj, api=api, ventanas=ventanas, cfg=cfg,
                           cambios=cambios, anf=anf, bus=esc.estado)


def pasar(h, s):
    h.reloj.t += s
    h.ctl._tic_maquina()


def activa(h):
    pasar(h, 0.4)
    pasar(h, 0.5)
    assert h.ctl._maquina.estado == "activa"


# ── Pantalla grande con la mascota ────────────────────────────────────────────

def test_entrada_planeo_monitor_fundido_activa(qapp):
    h = montar(qapp)
    assert h.ctl.entrar("manual") is True
    # La actividad se pidió ANTES de tocar la ventana (el detector de juegos la ve).
    assert h.m.bus_al_tocarla.grande is True
    assert h.m.diario[0] == ("geometria",)
    assert h.m.fases() == ["glide"]
    assert h.m.diario[1][2]["ms"] == 400
    assert h.ctl._t_maquina.isActive()
    pasar(h, 0.4)
    pantalla = QGuiApplication.primaryScreen().geometry()
    assert h.m.geometrias() == [pantalla]
    assert h.m.fases() == ["glide", "entrar"]
    pasar(h, 0.5)
    assert h.ctl._maquina.estado == "activa" and h.ctl.activo
    assert not h.ctl._t_maquina.isActive()
    assert h.cambios == [(True, "manual")]
    assert h.ctl.estado()["vista"] == "mascota"


def test_salida_restaura_la_geometria_exacta(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    assert h.ctl.salir() is True
    assert h.m.fases()[-1] == "salir"
    assert h.bus.actual().grande is True               # aún saliendo
    pasar(h, 0.5)
    assert h.m.geometrias()[-1] == GEOM
    assert h.m.fases()[-1] == "volver"
    pasar(h, 0.4)
    assert h.m.fases()[-1] == "fin"
    assert h.bus.actual().grande is False
    assert not h.ctl.activo
    assert h.cambios == [(True, "manual"), (False, "manual")]


def test_entrar_despierta_a_la_mascota_dormida(qapp):
    h = montar(qapp)
    h.m.durmiendo = True
    h.ctl.entrar("manual")
    assert ("despertar",) in h.m.diario


def test_alternar_ignorado_durante_la_transicion(qapp):
    h = montar(qapp)
    assert h.ctl.alternar() is True
    assert h.ctl.alternar() is True                     # entrando: se ignora
    assert h.m.fases() == ["glide"]
    activa(h)
    assert h.ctl.alternar() is False                    # sale
    assert h.ctl.alternar() is False                    # saliendo: se ignora
    pasar(h, 1.0)
    pasar(h, 1.0)
    assert h.bus.actual().grande is False


def test_entrar_durante_la_salida_se_encola(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.ctl.salir()
    assert h.ctl.entrar("alarma") is True
    assert h.ctl.activo and h.ctl.motivo == "alarma"
    pasar(h, 0.5)
    pasar(h, 0.4)                                        # fin de la salida → entra la encolada
    assert h.m.fases()[-2:] == ["fin", "glide"]
    assert h.bus.actual().grande is True
    activa(h)
    assert h.ctl.motivo == "alarma"
    assert h.cambios[-1] == (True, "alarma")


def test_juego_bloquea_la_entrada(qapp):
    h = montar(qapp)
    h.esc.prioridad.iniciar("juego")
    assert h.ctl.entrar("manual") is False
    assert "juego" in h.ctl.ultimo_error
    assert h.m.diario == []


def test_ceder_por_juego_sale_ya_sin_animacion(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.esc.prioridad.iniciar("juego")
    assert not h.ctl.activo
    assert h.m.fases()[-1] == "fin" and "salir" not in h.m.fases()
    assert h.m.geometrias()[-1] == GEOM
    est = h.bus.actual()
    assert est.juego is True and est.grande is False
    assert h.cambios[-1] == (False, "manual")


def test_minutos_sale_sola(qapp):
    h = montar(qapp)
    assert h.ctl.entrar("herramienta", minutos=2) is True
    assert h.ctl._t_minutos.isActive() and h.ctl._t_minutos.interval() == 120_000
    activa(h)
    assert h.ctl.estado()["restante_s"] == 120 - 1       # pasó ~0.9 s
    h.ctl._t_minutos.timeout.emit()
    assert h.m.fases()[-1] == "salir"


def test_la_mascota_se_va_en_mitad(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.esc.set_mascota(None)
    assert not h.ctl.activo
    assert h.bus.actual().grande is False
    assert h.cambios[-1] == (False, "manual")


def test_detener_sale_ya(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    h.ctl.detener()
    assert not h.ctl.activo and h.bus.actual().grande is False
    assert h.m.geometrias()[-1] == GEOM


# ── Sin mascota: VentanaReloj y mascota temporal ─────────────────────────────

def test_sin_mascota_y_sin_poder_sacarla_usa_ventana_reloj(qapp):
    h = montar(qapp, mascota=False, render="sprites")
    assert h.ctl.entrar("manual") is True
    assert len(h.ventanas) == 1
    v = h.ventanas[0]
    assert v.modo == "grande" and v.visible
    assert h.bus.actual().grande is True
    v.cerrar_pedido.emit()                              # un clic sale
    assert not v.visible and not h.ctl.activo
    assert h.bus.actual().grande is False


def test_con_sprites_a_la_vista_usa_ventana_reloj(qapp):
    h = montar(qapp, render="sprites", lista=False)
    h.m.render = "sprites"
    h.ctl.entrar("manual")
    assert h.ventanas and h.ventanas[0].modo == "grande"
    assert h.m.fases() == [] and h.m.geometrias() == []     # solo se mira en qué pantalla está


def test_mascota_temporal_se_saca_y_se_cierra_al_salir(qapp):
    h = montar(qapp, mascota=False, render="vrm", anfitrion=lambda esc: AnfitrionFalso(esc, crea_lista=False))
    assert h.ctl.entrar("manual") is True
    assert len(h.anf.creadas) == 1
    m = h.anf.creadas[0]
    assert h.ctl.activo and h.ctl.estado()["fase"] == "esperando"
    assert h.bus.actual().grande is True
    h.reloj.t += 2.0
    m.lista = True                                      # la página ya cargó
    h.ctl._comprobar_espera()
    assert m.fases() == ["glide"]
    activa(h)
    h.ctl.salir()
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert ("close",) in m.diario and m.cerrado
    assert h.bus.actual().grande is False


def test_mascota_temporal_que_no_carga_cae_al_reloj(qapp):
    h = montar(qapp, mascota=False, render="animado", anfitrion=lambda esc: AnfitrionFalso(esc, crea_lista=False))
    h.ctl.entrar("manual")
    m = h.anf.creadas[0]
    h.reloj.t += 6.5
    h.ctl._comprobar_espera()
    assert m.cerrado                                     # la temporal se cierra
    assert h.ventanas and h.ventanas[0].modo == "grande"
    assert h.bus.actual().grande is True and h.ctl.activo


def test_nativa_con_animado_no_saca_mascota(qapp):
    class Nativo(AnfitrionFalso):
        modo = "br"
    h = montar(qapp, mascota=False, render="animado", anfitrion=lambda esc: Nativo(esc))
    h.ctl.entrar("manual")
    assert h.anf.creadas == []
    assert h.ventanas[0].modo == "grande"


def test_sin_webengine_no_saca_mascota(qapp):
    h = montar(qapp, mascota=False, render="vrm", anfitrion=lambda esc: AnfitrionFalso(esc))
    h.ctl._hay_webengine = lambda: False
    h.ctl.entrar("manual")
    assert h.anf.creadas == [] and h.ventanas[0].modo == "grande"


def test_mascota_de_pagina_aun_cargando_se_espera_sin_ser_temporal(qapp):
    h = montar(qapp, lista=False)
    h.ctl.entrar("manual")
    assert h.ctl.estado()["fase"] == "esperando" and not h.ventanas
    h.m.lista = True
    h.ctl._comprobar_espera()
    activa(h)
    h.ctl.salir(inmediato=True)
    assert not h.m.cerrado                               # no era temporal


# ── Alarma ────────────────────────────────────────────────────────────────────

def test_alarma_sin_mascota_en_ventana_reloj(qapp):
    h = montar(qapp, mascota=False)
    apagar, posponer = [], []
    h.ctl.pedir_apagar_alarma.connect(lambda: apagar.append(1))
    h.ctl.pedir_posponer_alarma.connect(lambda: posponer.append(1))
    h.esc.prioridad.iniciar("alarma")
    assert h.ctl.entrar("alarma") is True
    v = h.ventanas[0]
    assert v.modo == "alarma"
    assert h.ctl.mostrar_alarma("sacar la pizza") is True
    assert ("alarma", "sacar la pizza", 5000) in v.diario
    v.cerrar_pedido.emit()                               # el clic lo lleva ControlAlarmasQt
    assert h.ctl.activo
    v.apagar.emit()
    v.posponer.emit()
    assert apagar == [1] and posponer == [1]
    assert h.ctl.salir("alarma") is True
    assert not v.visible and h.bus.actual().grande is False


def test_alarma_sobre_la_grande_manual_no_la_quita(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.esc.prioridad.iniciar("alarma")                    # coexisten
    assert h.ctl.entrar("alarma") is True
    assert h.ctl.mostrar_alarma("gimnasio") is True
    assert ("alarma", "gimnasio") in h.m.diario
    assert h.ctl.salir("alarma") is False
    assert h.m.diario[-1] == ("alarma", None)            # la burbuja sí se va
    assert h.ctl.activo and h.ctl.motivo == "manual"


def test_alarma_sobre_la_grande_de_reloj_cambia_de_modo_y_vuelve(qapp):
    h = montar(qapp, mascota=False, render="sprites")
    h.ctl.entrar("manual")
    v = h.ventanas[0]
    h.ctl.mostrar_alarma("x")
    assert v.modo == "alarma"
    h.ctl.salir("alarma")
    assert v.modo == "grande" and h.ctl.activo


def test_alarma_con_mascota_se_ve_en_la_mascota(qapp):
    h = montar(qapp)
    h.esc.prioridad.iniciar("alarma")
    h.ctl.entrar("alarma")
    h.ctl.mostrar_alarma("hola")
    assert ("alarma", "hola") in h.m.diario
    activa(h)
    h.ctl.salir("alarma")
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert not h.ctl.activo


# ── Salvapantallas ────────────────────────────────────────────────────────────

def armar(h, s=31):
    h.api.inactivo(s)
    h.reloj.t += s
    h.ctl._tic_inactividad()


def test_inactividad_falsa_arma_el_salvapantallas_con_la_mascota(qapp):
    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    assert h.ctl._t_inactividad.isActive()
    armar(h, 10)
    assert not h.ctl.activo                              # paso 0 = 30 s
    armar(h, 31)
    assert h.ctl.activo and h.ctl.motivo == "salvapantallas"
    assert h.bus.actual().salvapantallas is True
    assert ("salvapantallas", True, True, True) in h.m.diario
    assert h.ctl._t_entrada.isActive()


def test_sin_mascota_el_salvapantallas_es_la_ventana_reloj(qapp):
    h = montar(qapp, mascota=False, activo=True)
    h.cfg.set("salvapantallas", "fondo_oscuro", False)
    h.cfg.set("salvapantallas", "reloj", False)
    h.ctl.iniciar()
    armar(h)
    assert h.ventanas[0].diario[0] == ("mostrar", "salvapantallas", False, False)


def test_apagado_juego_mando_y_pantalla_pedida_no_arman(qapp):
    h = montar(qapp)
    h.ctl.iniciar()
    assert not h.ctl._t_inactividad.isActive()           # salvapantallas.activo = False
    h.ctl._tic_inactividad()
    assert not h.ctl.activo

    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    h.api.ejecucion = we.ES_DISPLAY_REQUIRED             # un vídeo pide la pantalla
    armar(h)
    assert not h.ctl.activo
    h.api.ejecucion = 0
    h.api.mando = EstadoMando(1, 0x1000, 0, 0, 0, 0, 0, 0)   # botón A pulsado
    armar(h)
    assert not h.ctl.activo
    h.api.mando = None
    h.esc.prioridad.iniciar("juego")
    armar(h)
    assert not h.ctl.activo


def test_dormida_cuenta_como_reposo(qapp):
    h = montar(qapp, activo=True)
    h.bus.actualizar(durmiendo=True)
    h.ctl.iniciar()
    armar(h)
    assert h.ctl.activo


def test_mover_el_raton_no_sale_y_el_clic_si(qapp):
    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    armar(h)
    activa(h)
    h.reloj.t += 2.0                                     # pasada la gracia
    h.api.pos = (400, 300)                               # mueve el ratón (y la marca cambia)
    h.api.ultima += 5
    h.ctl._tic_entrada()
    h.api.pos = (420, 310)
    h.api.ultima += 5
    h.ctl._tic_entrada()
    assert h.ctl.activo and h.m.fases()[-1] == "entrar"
    h.api.clic = True                                    # clic izquierdo
    h.ctl._tic_entrada()
    assert h.m.fases()[-1] == "salir"
    assert ("salvapantallas", False, True, True) in h.m.diario
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert h.bus.actual().salvapantallas is False and not h.ctl.activo


def test_la_entrada_de_la_gracia_no_lo_cierra(qapp):
    h = montar(qapp)
    assert h.ctl.probar_salvapantallas() is True
    h.api.tecla()                                        # soltar el clic de «Probar»
    h.ctl._tic_entrada()
    assert h.ctl.activo and h.ctl.motivo == "salvapantallas"


def test_tecla_sale_y_rearma_despues(qapp):
    h = montar(qapp, mascota=False, activo=True)
    h.ctl.iniciar()
    armar(h)
    h.reloj.t += 2.0
    h.api.tecla()
    h.ctl._tic_entrada()
    assert not h.ctl.activo and h.bus.actual().salvapantallas is False
    h.ctl._tic_inactividad()                             # acaba de haber actividad: no vuelve
    assert not h.ctl.activo


def test_clic_sale_de_todo_apagado_queda_en_grande_manual(qapp):
    h = montar(qapp, activo=True)
    h.cfg.set("salvapantallas", "clic_sale_de_todo", False)
    h.bus.actualizar(durmiendo=True)
    h.ctl.iniciar()
    armar(h)
    activa(h)
    h.reloj.t += 2.0
    h.api.clic = True
    h.ctl._tic_entrada()
    est = h.bus.actual()
    assert est.salvapantallas is False and est.grande is True
    assert h.ctl.activo and h.ctl.motivo == "manual"
    assert ("salvapantallas", False, True, True) in h.m.diario   # la despierta
    assert h.cambios[-1] == (True, "manual")
    h.ctl.salir()
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert h.bus.actual().grande is False


def test_clic_sale_de_todo_apagado_con_reloj_ignora_el_mismo_clic(qapp):
    h = montar(qapp, mascota=False, activo=True)
    h.cfg.set("salvapantallas", "clic_sale_de_todo", False)
    h.ctl.iniciar()
    armar(h)
    h.reloj.t += 2.0
    h.api.clic = True
    h.ctl._tic_entrada()
    v = h.ventanas[0]
    assert v.modo == "grande"
    v.cerrar_pedido.emit()                               # el mismo clic llega a la ventana
    assert h.ctl.activo
    h.reloj.t += 1.0
    v.cerrar_pedido.emit()                               # otro clic después: sale
    assert not h.ctl.activo


def test_ceder_salvapantallas_con_alarma_sigue_en_grande_con_motivo_alarma(qapp):
    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    armar(h)
    activa(h)
    r = h.esc.prioridad.iniciar("alarma")
    assert r
    est = h.bus.actual()
    assert est.alarma and est.grande and not est.salvapantallas
    assert h.ctl.activo and h.ctl.motivo == "alarma"
    assert ("salvapantallas", False, True, True) in h.m.diario
    assert not h.ctl._t_entrada.isActive()               # la entrada ya es cosa de la alarma
    assert h.ctl.entrar("alarma") is True
    assert h.ctl.salir("alarma") is True
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert h.bus.actual().grande is False
    h.esc.prioridad.terminar("alarma")


def test_ceder_salvapantallas_de_reloj_con_alarma_cambia_la_ventana(qapp):
    h = montar(qapp, mascota=False, activo=True)
    h.ctl.iniciar()
    armar(h)
    h.esc.prioridad.iniciar("alarma")
    assert h.ventanas[0].modo == "alarma"
    assert h.bus.actual().grande is True


def test_juego_cede_el_salvapantallas(qapp):
    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    armar(h)
    activa(h)
    h.esc.prioridad.iniciar("juego")
    assert not h.ctl.activo
    assert h.m.geometrias()[-1] == GEOM
    assert ("salvapantallas", False, True, True) in h.m.diario


def test_detector_de_verdad_por_defecto(qapp):
    h = montar(qapp)
    assert isinstance(h.ctl._detector(), we.DetectorEntrada)
    assert h.ctl._detector().con_mando is True


# ── Herramienta ───────────────────────────────────────────────────────────────

def test_herramienta_con_en_ui(qapp):
    h = montar(qapp)
    llamadas = []

    def en_ui(fn):
        llamadas.append(fn)
        return fn()
    h.ctl._en_ui = en_ui
    fn = h.ctl.herramientas()["mascota_pantalla_grande"]
    r = fn({"activar": True, "minutos": 3}, {"origen": "chat"})
    assert isinstance(r, str) and "3 min" in r
    assert llamadas and h.ctl.activo and h.ctl.motivo == "herramienta"
    activa(h)
    r = fn({"activar": False}, None)
    assert "vuelvo" in r
    assert h.m.fases()[-1] == "salir"


def test_herramienta_con_juego_devuelve_el_motivo(qapp):
    h = montar(qapp)
    h.esc.prioridad.iniciar("juego")
    ok, motivo = h.ctl.herramientas()["mascota_pantalla_grande"]({"activar": True}, {})
    assert ok is False and "juego" in motivo


# ── Varios ────────────────────────────────────────────────────────────────────

def test_indice_mayor_interseccion():
    a, b = QRect(0, 0, 1920, 1080), QRect(1920, 0, 2560, 1440)
    assert indice_mayor_interseccion(QRect(1800, 100, 300, 300), [a, b]) == 1
    assert indice_mayor_interseccion(QRect(100, 100, 300, 300), [a, b]) == 0
    assert indice_mayor_interseccion(QRect(-5000, -5000, 10, 10), [a, b]) == 0


def test_estado_y_recargar_config(qapp):
    h = montar(qapp)
    e = h.ctl.estado()
    assert e["activo"] is False and e["salvapantallas"]["etiqueta"] == "30 s"
    h.cfg.set("salvapantallas", "activo", True)
    h.cfg.set("salvapantallas", "paso", 2)
    h.ctl.iniciar()
    assert h.ctl.estado()["salvapantallas"]["segundos"] == 300
    assert h.ctl._t_inactividad.isActive()
    h.cfg.set("salvapantallas", "activo", False)
    h.ctl.recargar_config()
    assert not h.ctl._t_inactividad.isActive()


def test_ventana_reloj_de_verdad_por_defecto(qapp):
    cfg = ConfigFalsa()
    cfg.set("avatar", "render", "sprites")
    esc = ServiciosEscritorio(cfg)
    ctl = ControlPantallaGrande(esc, cfg, api_entrada=ApiFalsa(), hay_webengine=lambda: False)
    try:
        assert ctl.entrar("manual") is True
        from ui.ventana_reloj import VentanaReloj
        assert isinstance(ctl._ventana, VentanaReloj) and ctl._ventana.isVisible()
        ctl.salir(inmediato=True)
        assert not ctl._ventana.isVisible()
    finally:
        if ctl._ventana is not None:
            ctl._ventana.deleteLater()


# ── Revisión 4-5-6: alarma con el salvapantallas, mascota escondida, salida ───────

class _MezAlarma:
    def cargar_wav(self, ruta):
        return Path(ruta).name

    def reproducir(self, *a, **k):
        return 1

    def detener(self, sid):
        pass

    def detener_canal(self, canal):
        pass


class _MutexAlarma:
    es_dueno = True

    def adquirir(self):
        return True

    def liberar(self):
        pass


class _EntradaAlarma:
    def reiniciar(self):
        pass

    def poll(self):
        return False


def _con_alarmas(h, tmp_path):
    """El ControlAlarmasQt DE VERDAD junto a la grande (como montar_ocio), con
    sonido, mutex, entrada y tarjeta falsos. → (alarmas, diario de la tarjeta)."""
    from datetime import datetime
    from nucleo.alarmas import Almacen
    from servicios.alarmas_aviso import ControlAviso
    from ui.alarmas_qt import ControlAlarmasQt

    diario = []

    class Tarjeta(QObject):
        apagar = pyqtSignal()
        posponer = pyqtSignal()

        def set_disparo(self, texto, **kw):
            diario.append(("texto", texto))

        def mostrar(self):
            diario.append(("mostrar",))

        def cerrar(self):
            diario.append(("cerrar",))

    def epoch():
        return 1_790_000_000.0 + h.reloj.t

    alm = Almacen(tmp_path / "alarmas.json", reloj=epoch)
    aviso = ControlAviso(mezclador=_MezAlarma(), almacen=alm, reloj=h.reloj, epoch=epoch, lanzar=lambda f: f())
    a = ControlAlarmasQt(h.esc, h.cfg, voice=None, grande=h.ctl, avisar=lambda t: None, almacen=alm,
                         aviso=aviso, mutex=_MutexAlarma(), entrada=_EntradaAlarma(),
                         ahora=lambda: datetime(2026, 9, 26, 7, 30), epoch=epoch, reloj=h.reloj,
                         dialogo=Tarjeta, intervalo_ms=10 ** 6)
    h.esc.registrar("alarmas", a, ("alarma",))
    return a, diario


def _sonar(a):
    from nucleo.alarmas import Disparo
    a._disparar(Disparo("a1", "cita", "alarma", 0.0, "07:30", 0.0))


@pytest.mark.parametrize("mascota", [True, False])
def test_salvapantallas_y_alarma_en_burbuja_sale_del_salvapantallas(qapp, tmp_path, mascota):
    # MO2: con alarmas.pantalla_grande apagado la alarma no usa la grande: el
    # salvapantallas no puede quedarse en «alarma» (nadie la sacaría al apagarla).
    h = montar(qapp, mascota=mascota, activo=True)
    h.cfg.set("alarmas", "pantalla_grande", False)
    a, tarjeta = _con_alarmas(h, tmp_path)
    h.ctl.iniciar()
    assert h.ctl.probar_salvapantallas() is True
    if mascota:
        activa(h)
    assert h.bus.actual().salvapantallas is True
    _sonar(a)
    est = h.bus.actual()
    assert est.alarma is True and est.grande is False and est.salvapantallas is False
    assert not h.ctl.activo and h.ctl.motivo == ""
    assert ("mostrar",) in tarjeta                             # la tarjeta de la alarma
    if mascota:
        assert h.m.geometrias()[-1] == GEOM                    # la mascota vuelve a su sitio…
        assert ("salvapantallas", False, True, True) in h.m.diario    # …despierta…
        assert h.m.diario[-1] == ("alarma", "cita")            # …con la burbuja de la alarma
    else:
        assert not h.ventanas[0].visible                       # fuera la VentanaReloj
    h.reloj.t += 6                                             # pasado el bloqueo
    assert a.apagar() is True
    est = h.bus.actual()
    assert not h.ctl.activo and est.grande is False and est.alarma is False
    assert h.esc.prioridad.puede("salvapantallas") and h.esc.prioridad.puede("baile")
    h.ctl.detener()
    a.detener()


@pytest.mark.parametrize("mascota", [True, False])
def test_salvapantallas_y_alarma_en_grande_sale_al_apagarla(qapp, tmp_path, mascota):
    # Con alarmas.pantalla_grande (por defecto) la grande sigue con la alarma y se va al apagarla.
    h = montar(qapp, mascota=mascota, activo=True)
    a, _ = _con_alarmas(h, tmp_path)
    h.ctl.iniciar()
    h.ctl.probar_salvapantallas()
    if mascota:
        activa(h)
    _sonar(a)
    assert h.ctl.activo and h.ctl.motivo == "alarma" and h.bus.actual().grande is True
    if mascota:
        assert h.m.diario[-1] == ("alarma", "cita")
    else:
        assert h.ventanas[0].modo == "alarma"
    h.reloj.t += 6
    assert a.apagar() is True
    if mascota:
        pasar(h, 0.5)
        pasar(h, 0.4)
    assert not h.ctl.activo and h.bus.actual().grande is False
    h.ctl.detener()
    a.detener()


def test_grande_de_la_alarma_sale_sola_si_la_alarma_acaba_sin_sacarla(qapp):
    # Red de seguridad de MO2: el bus apaga `alarma` y nadie llamó a salir("alarma").
    h = montar(qapp, activo=True)
    h.ctl.iniciar()
    armar(h)
    activa(h)
    h.esc.prioridad.iniciar("alarma")
    assert h.ctl.motivo == "alarma"
    h.esc.prioridad.terminar("alarma")
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert not h.ctl.activo and h.bus.actual().grande is False
    # Con un juego se va sin animación (ceder), no con la salida animada.
    h.ctl.entrar("manual")
    activa(h)
    h.esc.prioridad.iniciar("alarma")
    h.ctl.entrar("alarma")
    n = len(h.m.fases())
    h.esc.prioridad.iniciar("juego")
    assert not h.ctl.activo and "salir" not in h.m.fases()[n:]
    h.ctl.detener()


def test_esconder_la_mascota_en_grande_sale_ya(qapp):
    # MO7: guardarla en la bandeja con la grande puesta → fuera (no activa e invisible).
    h = montar(qapp)
    h.ctl.iniciar()
    h.ctl.entrar("manual")
    activa(h)
    h.m.vis = False
    h.m.visibilidad.emit(False)
    est = h.bus.actual()
    assert not h.ctl.activo and est.grande is False and not est.visible
    assert h.m.geometrias()[-1] == GEOM                        # vuelve a su sitio para cuando se vea
    assert h.esc.prioridad.puede("salvapantallas") and h.esc.prioridad.puede("baile")
    assert h.cambios[-1] == (False, "manual")
    h.ctl.detener()


def test_esconder_la_mascota_temporal_la_cierra(qapp):
    h = montar(qapp, mascota=False, render="vrm", anfitrion=lambda esc: AnfitrionFalso(esc, crea_lista=True))
    h.ctl.iniciar()
    h.ctl.entrar("manual")
    m = h.anf.creadas[0]
    activa(h)
    m.vis = False
    m.visibilidad.emit(False)
    assert not h.ctl.activo and m.cerrado and h.bus.actual().grande is False
    h.ctl.detener()


def test_un_aviso_de_oculta_con_la_mascota_a_la_vista_no_sale(qapp):
    # Minimizar (Win+D) manda un hideEvent espontáneo pero la ventana sigue «visible».
    h = montar(qapp)
    h.ctl.iniciar()
    h.ctl.entrar("manual")
    activa(h)
    h.bus.actualizar(visible=False)
    assert h.ctl.activo and h.bus.actual().grande is True
    h.ctl.detener()


def test_tras_detener_no_escucha_el_bus(qapp):
    h = montar(qapp)
    h.ctl.iniciar()
    h.ctl.detener()
    h.ctl.entrar("manual")
    activa(h)
    h.m.vis = False
    h.m.visibilidad.emit(False)
    assert h.ctl.activo                                        # detenido: ya no mira el bus
    h.ctl.salir(inmediato=True)


def test_alarma_durante_la_salida_conserva_la_burbuja(qapp):
    # MO11: la alarma que entra durante la salida animada re-entra con su burbuja.
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.ctl.salir()
    assert h.ctl._maquina.estado == "saliendo"
    assert h.ctl.entrar("alarma") is True
    assert h.ctl.mostrar_alarma("cita") is True
    pasar(h, 0.5)
    pasar(h, 0.4)                                              # fin de la salida → entra la encolada
    activa(h)
    alarmas = [d for d in h.m.diario if d[0] == "alarma"]
    assert h.ctl.motivo == "alarma" and alarmas == [("alarma", "cita")]
    assert h.ctl._alarma_texto == "cita"
    assert h.ctl.salir("alarma") is True                       # al apagarla: fuera y sin burbuja
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert [d for d in h.m.diario if d[0] == "alarma"][-1] == ("alarma", None)
    assert not h.ctl.activo and h.ctl._alarma_texto is None


def test_alarma_durante_la_salida_en_otra_mascota_mueve_la_burbuja(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.ctl.salir()
    h.ctl.entrar("alarma")
    h.ctl.mostrar_alarma("cita")
    vieja = h.m
    nueva = MascotaFalsa(h.bus)
    h.ctl._mascota = nueva                                      # la de la entrada nueva es otra
    pasar(h, 0.5)
    pasar(h, 0.4)
    assert vieja.diario[-1] == ("alarma", None) or ("alarma", None) in vieja.diario
    assert ("alarma", "cita") in nueva.diario


def test_alarma_durante_la_salida_sin_mascota_lista_va_a_la_ventana_con_burbuja(qapp):
    h = montar(qapp)
    h.ctl.entrar("manual")
    activa(h)
    h.ctl.salir()
    h.ctl.entrar("alarma")
    h.ctl.mostrar_alarma("cita")
    h.m.lista = False                                          # la página dejó de estar lista
    pasar(h, 0.5)
    pasar(h, 0.4)
    v = h.ventanas[0]
    assert v.modo == "alarma" and ("alarma", "cita", 5000) in v.diario
    assert h.ctl.activo and h.ctl.motivo == "alarma"


def test_detener_borra_la_ventana_reloj(qapp):
    # VS8: la VentanaReloj (sin padre) no queda huérfana tras un cambio de interfaz.
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    cfg = ConfigFalsa()
    cfg.set("avatar", "render", "sprites")
    esc = ServiciosEscritorio(cfg)
    ctl = ControlPantallaGrande(esc, cfg, api_entrada=ApiFalsa(), hay_webengine=lambda: False)
    ctl.iniciar()
    assert ctl.entrar("manual") is True
    v = ctl._ventana
    ctl.detener()
    assert ctl._ventana is None and not v.isVisible()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert sip.isdeleted(v)
    assert ctl.entrar("manual") is True and ctl._ventana is not v      # si vuelve a hacer falta, otra
    ctl.detener()
    ctl.deleteLater()
