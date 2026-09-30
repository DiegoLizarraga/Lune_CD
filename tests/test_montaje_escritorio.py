"""
Tests de ui/montaje_escritorio.py (montar_escritorio + ServiciosCorte4) y de los
anfitriones (ui/anfitrion_web.py, ui/anfitrion_nativo.py), con dobles: Tema y
Juego falsos (los de verdad son de los agentes C y A), bandeja con un
QSystemTrayIcon falso, GestorAtajos falso, asistente y anfitrión falsos. Offscreen.
"""
import copy
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, QPoint, QTimer, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu  # noqa: E402

from nucleo.config import Config  # noqa: E402
from servicios.atajos_globales import normalizar  # noqa: E402
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from ui.montaje_escritorio import ORDEN, ServiciosCorte4, montar_escritorio  # noqa: E402


# ── Dobles ────────────────────────────────────────────────────────────────────

class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)

    def feature(self, n, d=True):
        return d


class TemaFalso(QObject):
    cambio = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.diario = []

    def qss_menu(self):
        return f"QMenu {{ color: {self.config.get('tema', 'preset')}; }}"

    def colores_radial(self):
        return {"acento": "#FF00AA" if self.config.get("tema", "preset") == "magenta_mate" else "#00E5FF"}

    def aplicar_preset(self, p):
        self.diario.append(("preset", p))
        self.config.set("tema", "preset", p)
        self.cambio.emit("{}")
        return {}

    def iniciar(self):
        self.diario.append("iniciar")

    def detener(self):
        self.diario.append("detener")


class JuegoFalso(QObject):
    cambio = pyqtSignal(bool, str)

    def __init__(self, escritorio, config, *, voice=None, parent=None):
        super().__init__(parent)
        self.diario = []
        self.e = {"activo": False, "motivo": "", "forzado": None, "exe": ""}

    def iniciar(self):
        self.diario.append("iniciar")

    def detener(self):
        self.diario.append("detener")

    def estado(self):
        return dict(self.e)

    def activo(self):
        return self.e["activo"]

    def forzar(self, on):
        self.diario.append(("forzar", on))

    def set_asistente(self, v):
        self.diario.append(("asistente", v is not None))


class TrayFalso(QObject):
    activated = pyqtSignal(object)

    @staticmethod
    def isSystemTrayAvailable():
        return True

    def __init__(self, icono=None, parent=None):
        super().__init__(parent)
        self.menu, self.tooltip, self.visible, self.mensajes, self.borrado = None, "", False, [], False

    def setContextMenu(self, m):
        self.menu = m

    def setToolTip(self, t):
        self.tooltip = t

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def showMessage(self, *a):
        self.mensajes.append(a)

    def deleteLater(self):
        self.borrado = True
        super().deleteLater()


class GestorFalso:
    def __init__(self):
        self._on_atajo = None
        self.activos = {}
        self.vivo = False
        self.diario = []

    def activo(self):
        return self.vivo

    def iniciar(self):
        self.vivo = True
        return True

    def detener(self):
        self.vivo = False
        self.diario.append("detener")

    def registrar(self, id_, combo):
        self.activos[id_] = normalizar(combo)

    def quitar(self, id_):
        self.activos.pop(id_, None)

    def quitar_todos(self):
        self.activos.clear()
        self.diario.append("quitar_todos")


class AsistenteFalsa(QObject):
    menu_pedido = pyqtSignal(str, object)
    visibilidad = pyqtSignal(bool)
    cerrado = False

    def __init__(self):
        super().__init__()
        self.visible = True
        self.render = "vrm"
        self.diario = []
        self.click_through = False
        self.durmiendo = False

    def isVisible(self):
        return self.visible

    def __getattr__(self, nombre):
        # Cualquier método del contrato de la asistente: se apunta y ya.
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        return lambda *a: self.diario.append((nombre,) + a)

    def set_click_through(self, on):
        self.click_through = on
        self.diario.append(("set_click_through", on))

    def dormir(self):
        self.durmiendo = True
        self.diario.append(("dormir",))

    def despertar(self):
        self.durmiendo = False
        self.diario.append(("despertar",))

    def ancla_menu(self, cb):
        cb(QPoint(400, 300))


class AnfitrionFalso:
    def __init__(self, modo="normal", asistente=None):
        self.modo = modo
        self.soporta_llamada = modo == "normal"
        self.diario = []
        self.voz = False
        self.barra = True
        self.visible = True
        self._asistente = asistente

    def _apunta(self, *a):
        self.diario.append(a)

    def mostrar_ventana(self): self._apunta("mostrar")
    def ventana_visible(self): return self.visible
    def asistente(self): return self._asistente
    def alternar_asistente(self):
        self._apunta("alternar_asistente")
        if self._asistente is not None:
            self._asistente.visible = not self._asistente.visible
        return bool(self._asistente and self._asistente.visible)
    def voz_on(self): return self.voz
    def alternar_voz(self):
        self.voz = not self.voz
        self._apunta("voz", self.voz)
        return self.voz
    def llamada_on(self): return False
    def alternar_llamada(self): self._apunta("llamada")
    def comentar(self): self._apunta("comentar")
    def abrir_ajustes(self, seccion=""): self._apunta("ajustes", seccion)
    def salir(self): self._apunta("salir")
    def aviso(self, texto): self._apunta("aviso", texto)
    def set_aburrimiento(self, activo): self._apunta("aburrimiento", activo)
    def en_barra_on(self): return self.barra
    def set_en_barra(self, on):
        self.barra = on
        self._apunta("en_barra", on)


class AutoinicioFalso:
    def __init__(self):
        self.on = False

    def activo(self):
        return self.on

    def establecer(self, q):
        self.on = bool(q)
        return self.on


@pytest.fixture
def montaje(qapp):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    masc = AsistenteFalsa()
    anf = AnfitrionFalso(asistente=masc)
    gestor = GestorFalso()
    sonidos = []
    auto = AutoinicioFalso()
    fab = {
        "tema": lambda c, p: TemaFalso(c, p),
        "juego": JuegoFalso,
        "gestor_atajos": gestor,
        "tray": TrayFalso,
        "autoinicio": auto,
        "recortar": lambda: (512.0, 300.0),
        "modelos_vrm": lambda: ["a.vrm", "b.vrm"],
        "sonar": sonidos.append,
        "traer_al_frente": None,
        "ocio": False,               # cortes 5/6 aparte (tests/test_anfitriones_c56.py)
        "vida": False,               # cortes 7/8 aparte (tests/test_anfitriones_c78_int.py)
        "escenario": False,          # cortes 9/10 aparte (tests/test_anfitriones_c910_int.py)
    }
    s = montar_escritorio(esc, anf, cfg, fabricas=fab)
    esc.set_asistente(masc, render="vrm")
    s.cfg, s.esc, s.masc, s.anf, s.gestor, s.sonidos, s.auto = cfg, esc, masc, anf, gestor, sonidos, auto
    yield s
    s.desmontar()
    esc.cerrar()


# ── Montaje ───────────────────────────────────────────────────────────────────

def test_monta_en_orden_y_arranca(montaje):
    s = montaje
    assert isinstance(s, ServiciosCorte4)
    assert list(s.esc.controladores()) == list(ORDEN)
    assert "iniciar" in s.tema.diario and "iniciar" in s.juego.diario
    assert s.bandeja.icono_tray.visible
    assert s.gestor.vivo and "mostrar_lune" in s.gestor.activos
    assert "pantalla_grande" not in s.gestor.activos and "baile_pausa" not in s.gestor.activos
    assert "llamada" in s.gestor.activos                               # web: sí
    # la asistente llegó a los controladores y a la bandeja (red de seguridad)
    assert ("asistente", True) in s.juego.diario
    assert ("quitar_bandeja",) in s.masc.diario
    assert s.bandeja._qss == "QMenu { color: cian; }"


def test_atajo_pulsado_ejecuta_la_accion(montaje, qapp):
    s = montaje
    s.gestor._on_atajo("voz")
    qapp.processEvents()
    assert ("voz", True) in s.anf.diario and s.sonidos == []
    s.cfg.d["atajos"]["sonido"] = True
    s.gestor._on_atajo("mostrar_lune")
    qapp.processEvents()
    assert ("mostrar",) in s.anf.diario and s.sonidos == ["menu_boton"]


def test_atajo_menu_radial_abre_el_radial_en_la_cabeza(montaje, qapp):
    s = montaje
    s.gestor._on_atajo("menu_radial")
    qapp.processEvents()
    assert s.radial.abierto() and s.radial.menu.centro_global() == QPoint(400, 300)
    assert s.esc.estado.actual().menu_abierto is True
    assert ("set_menu_abierto", True) in s.masc.diario
    assert "menu_abrir" in s.sonidos


def test_modo_juego_pausa_atajos_aburrimiento_y_radial(montaje, qapp):
    s = montaje
    s.radial.abrir("principal", QPoint(400, 300))
    s.juego.cambio.emit(True, "quns3")
    assert set(s.gestor.activos) == {"mostrar_lune"}
    assert ("aburrimiento", False) in s.anf.diario
    assert not s.radial.abierto() and s.esc.estado.actual().menu_abierto is False
    s.juego.cambio.emit(False, "")
    assert "voz" in s.gestor.activos
    assert s.anf.diario[-1] == ("aburrimiento", True)


def test_tema_llega_a_la_bandeja_y_al_radial(montaje, qapp):
    s = montaje
    s.radial.abrir("principal", QPoint(400, 300))
    assert s.despachador.ejecutar("tema", "magenta_mate")
    assert ("preset", "magenta_mate") in s.tema.diario
    assert s.bandeja._qss == "QMenu { color: magenta_mate; }"
    assert s.radial.menu._col["acento"].name() == "#ff00aa"


def test_contexto(montaje):
    s = montaje
    s.anf.voz = True
    s.anf.barra = False
    s.cfg.d["tema"]["preset"] = "violeta"
    s.cfg.d["avatar"]["vrm_tamano"] = "grande"
    s.juego.e.update(activo=True, motivo="lista", forzado=None)
    s.auto.on = True
    c = s.contexto()
    assert (c.modo, c.render, c.asistente_visible, c.voz_on, c.en_barra_on) == ("normal", "vrm", True, True, False)
    assert (c.tema_preset, c.tamano, c.varios_vrm, c.autoinicio_on) == ("violeta", "grande", True, True)
    assert (c.juego_activo, c.juego_motivo, c.juego_forzado) == (True, "lista", None)


def test_acciones_de_la_asistente(montaje):
    s = montaje
    d, m = s.despachador, s.masc
    d.ejecutar("fantasma")
    assert m.click_through is True
    d.ejecutar("dormir")
    d.ejecutar("dormir")
    assert ("dormir",) in m.diario and ("despertar",) in m.diario
    s.cfg.d["avatar"]["vrm_tamano"] = "grande"
    d.ejecutar("tamano")                                 # sin arg: la siguiente (vuelve a pequeña)
    d.ejecutar("tamano", "normal")
    assert ("aplicar_tamano", "pequeno") in m.diario and ("aplicar_tamano", "normal") in m.diario
    d.ejecutar("encuadre")
    assert ("aplicar_encuadre", "cuerpo") in m.diario
    d.ejecutar("expresion", "wave")
    d.ejecutar("expresion", "<script>")
    assert [x for x in m.diario if x[0] == "set_estado"] == [("set_estado", "wave", 4000)]
    d.ejecutar("esquina")
    d.ejecutar("chat")
    d.ejecutar("comentar")
    assert ("llevar_a_esquina",) in m.diario and ("abrir_chat",) in m.diario
    assert ("comentar",) in s.anf.diario
    d.ejecutar("siempre_encima")
    assert s.cfg.d["avatar"]["siempre_encima"] is False and ("set_encima", False) in m.diario
    d.ejecutar("comentarios_auto")                       # la asistente falsa no tiene la propiedad
    assert ("set_comentarios_auto", True) in m.diario
    d.ejecutar("cerrar_asistente")
    assert ("close",) in m.diario


def test_cerrar_asistente_apaga_lo_que_estaba_pensando(montaje):
    """Revisión 7-10 (RR5): cerrar la asistente con un «Comentar pantalla» a medias dejaba
    `pensando` pegado en el bus (Discord «Pensando…», bot de Minecraft en pausa, sin sueño)."""
    s = montaje
    s.esc.estado.actualizar(pensando=True)               # la asistente comentando la pantalla
    s.esc.estado.pensar("chat", True)                    # y el chat de la ventana
    s.despachador.ejecutar("cerrar_asistente")
    assert ("close",) in s.masc.diario
    assert s.esc.estado.actual().pensando is True        # el chat sigue: no es suya
    s.esc.estado.pensar("chat", False)
    assert s.esc.estado.actual().pensando is False


def test_chat_saca_la_asistente_si_estaba_guardada(montaje):
    s = montaje
    s.masc.visible = False
    s.despachador.ejecutar("chat")
    assert ("alternar_asistente",) in s.anf.diario and ("abrir_chat",) in s.masc.diario


def test_modo_juego_forzar(montaje):
    s = montaje
    d, j = s.despachador, s.juego
    d.ejecutar("modo_juego_forzar")                      # auto y sin juego → encender
    j.e.update(forzado=True, activo=True)
    d.ejecutar("modo_juego_forzar")                      # forzado → automático
    j.e.update(forzado=None, activo=True)
    d.ejecutar("modo_juego_forzar")                      # detectado → apagar a mano
    d.ejecutar("modo_juego_forzar", "on")
    d.ejecutar("modo_juego_forzar", "auto")
    d.ejecutar("modo_juego_forzar", "off")
    assert [x[1] for x in j.diario if x[0] == "forzar"] == [True, None, False, True, None, False]


def test_sistema_autoinicio_barra_y_memoria(montaje, qapp):
    s = montaje
    s.despachador.ejecutar("autoinicio")
    assert s.auto.on and s.cfg.d["sistema"]["autoinicio"] is True
    assert s.anf.diario[-1][0] == "aviso"                # con la ventana a la vista: aviso normal
    s.despachador.ejecutar("en_barra_tareas")
    assert s.anf.diario[-1] == ("en_barra", False)
    s.anf.visible = False                                # ventana oculta → globo de la bandeja
    s.despachador.ejecutar("liberar_memoria")
    fin = time.monotonic() + 3
    while not s.bandeja.icono_tray.mensajes and time.monotonic() < fin:
        qapp.processEvents()
        time.sleep(0.01)
    titulo, texto, _icono, _ms = s.bandeja.icono_tray.mensajes[-1]
    assert "512 MB" in texto and "300 MB" in texto


def test_menu_de_la_bandeja_por_el_despachador(montaje, qapp):
    s = montaje
    menu = s.bandeja.icono_tray.menu
    menu.aboutToShow.emit()
    textos = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert textos[0] == "Abrir Lune" and textos[-1] == "Salir"
    assert "Modo juego" in textos and "Arrancar con Windows" in textos
    salir = [a for a in menu.actions() if a.text() == "Salir"][0]
    salir.trigger()
    qapp.processEvents()
    assert ("salir",) in s.anf.diario


def test_estado_cambio_refresca_el_tooltip(montaje, qapp):
    s = montaje
    s.bandeja._ultimo_tooltip = 0
    s.esc.estado.actualizar(juego=True)
    qapp.processEvents()
    assert "modo juego" in s.bandeja.icono_tray.tooltip


# ── Desmontar ─────────────────────────────────────────────────────────────────

def test_desmontar_para_y_suelta_todo(montaje, qapp):
    s = montaje
    tray = s.bandeja.icono_tray
    s.radial.abrir("principal", QPoint(400, 300))
    s.juego.e["activo"] = True
    s.desmontar()
    assert s.desmontado
    assert not tray.visible and tray.borrado and s.bandeja.icono_tray is None
    assert s.gestor.activos == {} and "quitar_todos" in s.gestor.diario and not s.gestor.vivo
    assert "detener" in s.juego.diario and "detener" in s.tema.diario
    assert s.esc.controladores() == {}
    assert s.esc.estado.actual().menu_abierto is False and not s.radial.abierto()
    assert s.anf.diario[-1] == ("aburrimiento", True)    # el juego lo había parado
    # nada queda conectado
    n = len(s.anf.diario)
    s.juego.cambio.emit(True, "quns3")
    s.gestor._on_atajo("voz")
    qapp.processEvents()
    assert len(s.anf.diario) == n
    s.desmontar()                                        # idempotente
    s.detener()


def test_desmontar_con_el_escritorio_ya_cerrado(qapp):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    g = GestorFalso()
    s = montar_escritorio(esc, AnfitrionFalso(), cfg, fabricas={
        "tema": lambda c, p: TemaFalso(c, p), "juego": JuegoFalso, "gestor_atajos": g,
        "tray": TrayFalso, "autoinicio": AutoinicioFalso(), "sonar": lambda n: None,
        "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    tray = s.bandeja.icono_tray
    esc.cerrar()                                         # la app se cierra antes
    s.desmontar()
    assert not tray.visible and not g.vivo


# ── Piezas que faltan o fallan ────────────────────────────────────────────────

def test_sin_tema_ni_juego_el_resto_funciona(qapp, monkeypatch):
    # Los módulos de los agentes A y C aún no existen (o fallan al importar).
    monkeypatch.setitem(sys.modules, "ui.tema_qt", None)
    monkeypatch.setitem(sys.modules, "ui.modo_juego_qt", None)
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    g = GestorFalso()
    s = montar_escritorio(esc, AnfitrionFalso(modo="br"), cfg, fabricas={
        "gestor_atajos": g, "tray": TrayFalso, "autoinicio": AutoinicioFalso(),
        "sonar": lambda n: None, "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    try:
        assert s.tema is None and s.juego is None
        assert list(esc.controladores()) == ["despachador", "atajos", "radial", "bandeja"]
        assert not s.despachador.tiene("tema") and not s.despachador.tiene("modo_juego_forzar")
        # nativa: sin llamada, ni handler ni atajo
        assert not s.despachador.tiene("llamada") and "llamada" not in g.activos
        assert s.contexto().modo == "br" and s.contexto().juego_activo is False
        s.bandeja.icono_tray.menu.aboutToShow.emit()
    finally:
        s.desmontar()
        esc.cerrar()


def test_fabrica_que_revienta_no_tumba_el_montaje(qapp):
    def mal(*a, **k):
        raise RuntimeError("boom")
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    s = montar_escritorio(esc, AnfitrionFalso(), cfg, fabricas={
        "tema": mal, "juego": mal, "gestor_atajos": GestorFalso(), "tray": TrayFalso,
        "autoinicio": AutoinicioFalso(), "sonar": lambda n: None, "modelos_vrm": lambda: [],
        "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    try:
        assert s.tema is None and s.juego is None and s.bandeja is not None and s.radial is not None
    finally:
        s.desmontar()
        esc.cerrar()


def test_fuera_de_la_barra_al_montar(qapp):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    anf = AnfitrionFalso()
    anf.barra = False
    s = montar_escritorio(esc, anf, cfg, fabricas={
        "tema": lambda c, p: TemaFalso(c, p), "juego": JuegoFalso, "gestor_atajos": GestorFalso(),
        "tray": TrayFalso, "autoinicio": AutoinicioFalso(), "sonar": lambda n: None,
        "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    try:
        assert ("en_barra", False) in anf.diario
        # el escritorio aún no se había iniciado: nada arrancó todavía
        assert s.bandeja.icono_tray is None
        esc.iniciar()
        assert s.bandeja.icono_tray is not None
    finally:
        s.desmontar()
        esc.cerrar()


def test_sonidos_de_menu_por_el_mezclador(qapp, tmp_path):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tocados = []

    class Mez:
        def cargar_wav(self, ruta):
            return str(ruta)

        def reproducir(self, buf, vol=1.0, canal=None):
            tocados.append((Path(buf).name, vol, canal))
    s = montar_escritorio(esc, AnfitrionFalso(), cfg, fabricas={
        "tema": lambda c, p: TemaFalso(c, p), "juego": JuegoFalso, "gestor_atajos": GestorFalso(),
        "tray": TrayFalso, "autoinicio": AutoinicioFalso(), "mezclador": Mez,
        "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    try:
        s.sonar("menu_abrir")
        fin = time.monotonic() + 3
        while not tocados and time.monotonic() < fin:
            time.sleep(0.01)
        assert tocados == [("menu_abrir.wav", 0.6, "menu")]
        cfg.d["menu"]["sonidos"] = False
        s.sonar("menu_cerrar")
        cfg.d["menu"]["sonidos"] = True
        esc.estado.actualizar(juego=True)                  # en juego con juego.silenciar: calla
        s.sonar("menu_cerrar")
        s.sonar("no_existe")
        time.sleep(0.1)
        assert len(tocados) == 1
    finally:
        s.desmontar()
        esc.cerrar()


# ── Anfitriones ───────────────────────────────────────────────────────────────

class _Senal:
    def __init__(self):
        self.emitidos = []

    def emit(self, *a):
        self.emitidos.append(a)


class BridgeFalso:
    def __init__(self, con_pausa=False):
        self.config = ConfigFalsa()
        self.voice = type("V", (), {"_enabled": True})()
        self._llamada = None
        self._overlay = None
        self.aviso = _Senal()
        self.diario = []
        self._aburrida_t = QTimer()
        self._aburrida_t.start(100000)
        if con_pausa:
            self.pausar_aburrimiento = lambda on: self.diario.append(("pausar", on))

    def _asistente_viva(self):
        return "ASISTENTE"

    def asistente_toggle(self):
        self.diario.append("asistente_toggle")
        return True

    def voz_toggle(self):
        self.diario.append("voz_toggle")
        return False

    def llamada_toggle(self):
        self.diario.append("llamada_toggle")
        return True

    def comentar_pantalla(self):
        self.diario.append("comentar_pantalla")
        return True

    def _rearmar_aburrimiento(self):
        self.diario.append("rearmar")


class VentanaFalsa:
    def __init__(self):
        self.diario = []
        self.vis = True

    def _mostrar(self): self.diario.append("mostrar")
    def _salir_de_verdad(self): self.diario.append("salir")
    def isVisible(self): return self.vis
    def isMinimized(self): return False
    def hide(self): self.diario.append("hide")
    def show(self): self.diario.append("show")
    def winId(self): return 1234


def test_anfitrion_web(qapp):
    from ui.anfitrion_web import AnfitrionWeb, poner_en_barra
    b, v = BridgeFalso(), VentanaFalsa()
    navegado = []
    a = AnfitrionWeb(b, v, navegar=navegado.append)
    assert a.modo == "normal" and a.soporta_llamada
    a.mostrar_ventana()
    a.abrir_ajustes("juego")
    a.salir()
    a.abrir_ajustes("Mal/Ruta")
    assert v.diario == ["mostrar", "mostrar", "salir", "mostrar"]
    assert navegado == ["settings#juego", "settings"]
    assert a.asistente() == "ASISTENTE" and a.alternar_asistente() is True
    assert a.voz_on() is True and a.alternar_voz() is False
    assert a.llamada_on() is False and a.alternar_llamada() is True
    assert a.comentar() is True
    assert b.diario == ["asistente_toggle", "voz_toggle", "llamada_toggle", "comentar_pantalla"]
    a.aviso("hola")
    assert b.aviso.emitidos == [("hola",)]
    # aburrimiento sin pausar_aburrimiento público: para/rearma el temporizador
    a.set_aburrimiento(False)
    assert not b._aburrida_t.isActive()
    a.set_aburrimiento(True)
    assert b.diario[-1] == "rearmar"
    b2 = BridgeFalso(con_pausa=True)
    AnfitrionWeb(b2, v).set_aburrimiento(False)
    assert b2.diario == [("pausar", True)]
    # barra de tareas: guarda y oculta/muestra alrededor del cambio de estilo
    llamadas = []
    v.diario.clear()
    poner_en_barra(v, False, b.config, set_en_barra=lambda h, on: llamadas.append((h, on)))
    assert b.config.d["interfaz"]["en_barra_tareas"] is False and llamadas == [(1234, False)]
    assert v.diario == ["hide", "show"]
    assert a.en_barra_on() is False and a.ventana_visible() is True


class StackFalso:
    def __init__(self):
        self.i = 0

    def currentIndex(self):
        return self.i

    def setCurrentIndex(self, i):
        self.i = i


class WinFalsa(VentanaFalsa):
    def __init__(self):
        super().__init__()
        self.config = ConfigFalsa()
        self.voice = type("V", (), {"_enabled": False})()
        self.stack = StackFalso()
        self.masc = None
        self.estados = []

    def _restore_from_tray(self): self.diario.append("restaurar")
    def _toggle_keys_panel(self): self.stack.i = 1 if self.stack.i != 1 else 0
    def _toggle_voice(self): self.voice._enabled = not self.voice._enabled
    def _quit_app(self): self.diario.append("quit")
    def _toggle_overlay(self):
        if self.masc is None:
            self.masc = AsistenteFalsa()
            self.masc.visible = True
        else:
            self.masc.visible = not self.masc.visible
    def _asistente_viva(self): return self.masc
    def _set_status(self, texto, color): self.estados.append(texto)


def test_anfitrion_nativo(qapp):
    from ui.anfitrion_nativo import AnfitrionNativo
    w = WinFalsa()
    a = AnfitrionNativo(w)
    assert a.modo == "br" and not a.soporta_llamada
    a.abrir_ajustes()
    a.abrir_ajustes()                                    # ya estaba: no vuelve al chat
    assert w.stack.i == 1 and w.diario == ["restaurar", "restaurar"]
    assert a.alternar_voz() is True and a.voz_on() is True
    assert a.alternar_asistente() is True and a.asistente() is w.masc
    assert a.comentar() is True and ("comentar_pantalla",) in w.masc.diario
    assert a.llamada_on() is False and a.alternar_llamada() is False
    a.set_aburrimiento(False)
    a.aviso("hecho")
    assert w.estados == ["hecho"]
    a.salir()
    assert w.diario[-1] == "quit"


def test_con_el_control_tema_real(qapp):
    """Integración con ui/tema_qt.ControlTema (agente C): el preset elegido en la
    bandeja cambia el QSS del menú y los colores del radial."""
    pytest.importorskip("ui.tema_qt")
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    s = montar_escritorio(esc, AnfitrionFalso(), cfg, fabricas={
        "juego": JuegoFalso, "gestor_atajos": GestorFalso(), "tray": TrayFalso,
        "autoinicio": AutoinicioFalso(), "sonar": lambda n: None, "modelos_vrm": lambda: [],
        "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False})
    try:
        assert s.tema is not None and s.despachador.tiene("tema")
        qss_cian = s.bandeja._qss
        assert qss_cian and "QMenu" in qss_cian
        s.radial.abrir("principal", QPoint(400, 300))
        acento_cian = s.radial.menu._col["acento"].name()
        assert s.despachador.ejecutar("tema", "magenta_mate")
        assert s.bandeja._qss != qss_cian
        assert s.radial.menu._col["acento"].name() != acento_cian
        assert s.contexto().tema_preset == "magenta_mate"             # aunque el guardado vaya diferido
    finally:
        s.desmontar()
        esc.cerrar()
