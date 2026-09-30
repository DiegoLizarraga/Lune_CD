"""
Contratos del corte 4 (integración final): las clases DE VERDAD tienen lo que las
otras piezas les llaman, con firmas compatibles (inspect.signature(...).bind con los
argumentos exactos que usan quien las llama). Si alguien renombra un método o cambia
una firma, esto falla aquí y no en pantalla.

  · asistentes (CompanionFlotante, AvatarOverlay) → contrato §1.3 del plan;
  · ControlModoJuego, ControlTema, GestorAtajosQt, BandejaLune, ControlMenuRadial y
    PuenteEscritorio → lo que usan montar_escritorio, el puente web y Ajustes;
  · AnfitrionWeb / AnfitrionNativo → contra VentanaWeb, LuneBridge y LuneCDWindow
    reales (lo que traducen tiene que existir allí);
  · ventanas ↔ cambio de interfaz y montaje; SettingsPanel ↔ panel de escritorio.
Offscreen, sin crear ventanas pesadas (solo BandejaLune, que es inerte hasta iniciar).
"""
import copy
import inspect
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")
try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (fixture qapp).
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
except ImportError:
    pass

from PyQt6.QtCore import QPoint  # noqa: E402


def _firma(fn):
    return inspect.signature(fn)


def _admite(fn, *args, **kw) -> bool:
    """¿Se puede llamar `fn` (función o método sin enlazar) con estos argumentos?"""
    try:
        _firma(fn).bind(*args, **kw)
        return True
    except TypeError:
        return False


def _es_senal(cls, nombre) -> bool:
    """Atributo de clase que es una pyqtSignal (sin instanciar la clase)."""
    s = getattr(cls, nombre, None)
    return s is not None and type(s).__name__ in ("pyqtSignal", "pyqtBoundSignal")


YO = object()          # el «self» para bind() sobre métodos sin enlazar


# ── Asistentes: contrato §1.3 del plan ──────────────────────────────────────────────

def _asistentes():
    from ui.avatar_overlay import AvatarOverlay
    clases = [AvatarOverlay]
    try:
        from ui.companion import CompanionFlotante
        clases.append(CompanionFlotante)
    except Exception:                                     # sin QtWebEngine: solo sprites
        pass
    return clases


@pytest.mark.parametrize("cls", _asistentes(), ids=lambda c: c.__name__)
def test_asistentes_cumplen_el_contrato_del_corte4(cls):
    init = cls.__init__
    assert "bandeja" in _firma(init).parameters and _firma(init).parameters["bandeja"].default is True
    assert _admite(init, YO, None, bandeja=False)          # web_bridge/main: crear_asistente(..., bandeja=False)
    assert _es_senal(cls, "menu_pedido")                   # ('principal'|'secundario', QPoint)
    for nombre, args in (("quitar_bandeja", ()), ("ancla_menu", (lambda p: None,)),
                         ("set_menu_abierto", (True,)), ("aplicar_plan_juego", (None,)),
                         ("aplicar_tema", ("null",)), ("set_encima", (True,)), ("set_fps_max", (30,)),
                         ("set_comentarios_auto", (True,)), ("llevar_a_esquina", ())):
        f = getattr(cls, nombre, None)
        assert callable(f), f"{cls.__name__}.{nombre}"
        assert _admite(f, YO, *args), f"{cls.__name__}.{nombre}{args}"
    for prop in ("comentarios_auto", "click_through"):
        assert isinstance(inspect.getattr_static(cls, prop), property), f"{cls.__name__}.{prop}"
    # Lo que además llaman el montaje, la bandeja y el radial (con getattr defensivo, pero
    # estas las tienen las dos): abrir el chat, modo fantasma, expresión y cerrar.
    for nombre in ("abrir_chat", "set_click_through", "set_estado", "close", "isVisible"):
        assert callable(getattr(cls, nombre, None)), f"{cls.__name__}.{nombre}"
    assert _admite(cls.set_estado, YO, "happy", 4000)


def test_crear_asistente_quita_la_bandeja_solo_si_la_clase_sabe():
    from ui.escritorio import crear_asistente

    class ConBandeja:
        def __init__(self, config=None, bandeja=True):
            self.bandeja = bandeja

    class ConKw:
        def __init__(self, config=None, **kw):
            self.kw = kw

    class Vieja:                                           # antes del corte 4 (o un doble)
        def __init__(self, config=None):
            self.config = config

    class SinInit:
        pass

    assert crear_asistente(ConBandeja, "cfg").bandeja is False
    assert crear_asistente(ConKw, "cfg").kw == {"bandeja": False}
    assert crear_asistente(Vieja, "cfg").config == "cfg"
    assert isinstance(crear_asistente(SinInit), SinInit)


# ── Controladores del escritorio ──────────────────────────────────────────────────

def test_control_modo_juego():
    from ui.modo_juego_qt import ControlModoJuego
    assert _es_senal(ControlModoJuego, "cambio")
    # montaje._juego_defecto y los tests: (escritorio, config, voice=, parent=)
    assert _admite(ControlModoJuego.__init__, YO, None, None, voice=None, parent=None)
    for nombre, args in (("iniciar", ()), ("detener", ()), ("set_asistente", (None,)), ("forzar", (None,)),
                         ("forzar", (True,)), ("activo", ()), ("estado", ()), ("recargar_config", ())):
        assert _admite(getattr(ControlModoJuego, nombre), YO, *args), nombre


def test_control_tema():
    from ui.tema_qt import ControlTema
    assert _es_senal(ControlTema, "cambio")
    assert _admite(ControlTema.__init__, YO, None, parent=None)      # montaje._tema_defecto
    for nombre, args in (("actual", ()), ("css_json", ()), ("qss_menu", ()), ("colores_radial", ()),
                         ("previsualizar", ({},)), ("guardar", ({},)), ("guardar", ()),
                         ("restablecer", ()), ("aplicar_preset", ("violeta",)), ("recargar", ()),
                         ("set_asistente", (None,)), ("iniciar", ()), ("detener", ()), ("guardar_ya", ())):
        assert _admite(getattr(ControlTema, nombre), YO, *args), nombre


def test_gestor_atajos_qt():
    from ui.atajos_qt import GestorAtajosQt
    assert _es_senal(GestorAtajosQt, "accion") and _es_senal(GestorAtajosQt, "cambio")
    assert _admite(GestorAtajosQt.__init__, YO, None, disponible=lambda i: True, gestor=None, parent=None)
    assert "mostrar_lune" in GestorAtajosQt.SIEMPRE_ACTIVOS
    for nombre, args in (("iniciar", ()), ("detener", ()), ("recargar", ()), ("set_pausa", (True,)),
                         ("capturando", (True,)), ("capturando", (True, 15000)), ("estado", ()),
                         ("validar", ("ctrl+alt+x",)), ("validar", ("ctrl+alt+x", "voz")),
                         ("cambiar", ("voz", "")), ("activar", (True,)), ("restablecer", ()),
                         ("lista", ()), ("activo", ()), ("resumen", ()), ("pulsado", ("voz",))):
        assert _admite(getattr(GestorAtajosQt, nombre), YO, *args), nombre


def test_bandeja_lune(qapp):
    from nucleo.acciones_ui import Contexto, Despachador
    from nucleo.estado_asistente import BusEstado
    from ui.bandeja import BandejaLune
    # montaje: BandejaLune(desp, bus, contexto, config, icono=, parent=[, fabrica_tray=])
    assert _admite(BandejaLune.__init__, YO, None, None, None, None, icono=None, parent=None,
                   fabrica_tray=object)
    b = BandejaLune(Despachador(), BusEstado(), lambda: Contexto(), {}, icono=None)
    try:
        assert b.icono_tray is None                        # inerte hasta iniciar(): sin icono
        for nombre, args in (("iniciar", ()), ("detener", ()), ("set_asistente", (None,)),
                             ("mostrar_aviso", ("t", "x")), ("mostrar_aviso", ("t", "x", 4000, "info")),
                             ("aplicar_qss", ("",)), ("refrescar_tooltip", ()), ("items", ()),
                             ("ejecutar", ("mostrar_lune", ""))):
            assert _admite(getattr(BandejaLune, nombre), YO, *args), nombre
        assert b.mostrar_aviso("Lune", "sin icono") is False     # quien avisa usa otro medio
    finally:
        b.deleteLater()


def test_control_menu_radial():
    from ui.menu_radial import ControlMenuRadial, MenuRadial
    assert _admite(ControlMenuRadial.__init__, YO, None, None, None, lambda: None, colores=None,
                   sonar=None, parent=None, traer_al_frente=None)
    for nombre, args in (("iniciar", ()), ("detener", ()), ("set_asistente", (None,)), ("set_colores", ({},)),
                         ("abierto", ()), ("cerrar", ()), ("items", ("principal",)),
                         ("abrir", ("principal",)), ("abrir", ("expresiones", QPoint(1, 1)))):
        assert _admite(getattr(ControlMenuRadial, nombre), YO, *args), nombre
    assert _es_senal(MenuRadial, "elegido") and _es_senal(MenuRadial, "cerrado")


def test_puente_escritorio():
    from ui import puente_escritorio as pe
    P = pe.PuenteEscritorio
    for s in ("tema_cambio", "juego_estado", "atajos_cambio", "navegar"):
        assert _es_senal(P, s), s
    # web_shell registra el puente SIN servicios y se los da después.
    assert _admite(pe.registrar_en_canal, None, None, None, None, anfitrion=None)
    assert _admite(P.usar_servicios, YO, None, anfitrion=None, contexto=None)
    for nombre in ("cerrar", "pedir_vista", "enganchar_anfitrion", "acciones_catalogo", "accion_menu",
                   "tema_estado", "tema_previsualizar", "tema_guardar", "tema_restablecer", "efectos",
                   "efectos_guardar", "atajos_estado", "atajo_validar", "atajo_guardar", "atajos_activar",
                   "atajos_capturando", "atajos_restablecer", "radial_estado", "radial_guardar",
                   "bandeja_estado", "bandeja_guardar", "juego_estado_json", "juego_forzar", "juego_config",
                   "juego_guardar", "juego_apps_visibles", "rendimiento", "rendimiento_guardar",
                   "liberar_memoria"):
        assert callable(getattr(P, nombre, None)), nombre


def test_montaje_y_servicios_corte4():
    from ui.escritorio import ServiciosEscritorio
    from ui.montaje_escritorio import ACTIVIDADES, ORDEN, ServiciosCorte4, montar_escritorio
    assert _admite(montar_escritorio, None, None, None, voice=None, icono=None, fabricas=None)
    assert ORDEN == ("despachador", "tema", "atajos", "juego", "radial", "bandeja")
    assert ACTIVIDADES["juego"] == ("juego",)
    assert _admite(ServiciosEscritorio.registrar, YO, "juego", None, actividades=("juego",))
    for campo in ("despachador", "tema", "atajos", "juego", "radial", "bandeja", "escritorio",
                  "anfitrion", "contexto", "sonar", "avisar"):
        assert campo in ServiciosCorte4.__dataclass_fields__, campo
    assert ServiciosCorte4.detener is ServiciosCorte4.desmontar


# ── Anfitriones contra las ventanas y el puente DE VERDAD ────────────────────────

PROTOCOLO = ("mostrar_ventana", "asistente", "alternar_asistente", "voz_on", "alternar_voz", "llamada_on",
             "alternar_llamada", "abrir_ajustes", "salir", "aviso", "set_aburrimiento", "en_barra_on",
             "set_en_barra")


@pytest.mark.parametrize("modulo,clase,modo", [("ui.anfitrion_web", "AnfitrionWeb", "normal"),
                                              ("ui.anfitrion_nativo", "AnfitrionNativo", "br")])
def test_anfitriones_cumplen_el_protocolo(modulo, clase, modo):
    import importlib
    cls = getattr(importlib.import_module(modulo), clase)
    assert cls.modo == modo
    for nombre in PROTOCOLO + ("comentar", "ventana_visible"):
        assert callable(getattr(cls, nombre, None)), f"{clase}.{nombre}"


def test_anfitrion_web_contra_luneBridge_y_ventanaweb_reales():
    from ui.web_bridge import LuneBridge
    from ui.web_shell import VentanaWeb
    # Lo que AnfitrionWeb llama del puente…
    for nombre in ("asistente_toggle", "comentar_pantalla", "voz_toggle", "llamada_toggle", "_asistente_viva",
                   "pausar_aburrimiento", "_rearmar_aburrimiento"):
        assert callable(getattr(LuneBridge, nombre, None)), nombre
    assert _es_senal(LuneBridge, "aviso")
    assert _admite(LuneBridge.pausar_aburrimiento, YO, True)
    # …y de la ventana (salir, enseñarse; winId/isVisible/hide/show son de QWidget).
    for nombre in ("_mostrar", "salir_de_verdad", "_salir_de_verdad", "isVisible", "isMinimized",
                   "winId", "hide", "show"):
        assert callable(getattr(VentanaWeb, nombre, None)), nombre


def test_anfitrion_nativo_contra_lunecdwindow_real():
    import main
    W = main.LuneCDWindow
    for nombre in ("_restore_from_tray", "_toggle_overlay", "_toggle_voice", "_toggle_keys_panel",
                   "salir_de_verdad", "_quit_app", "_asistente_viva", "_set_status", "isVisible",
                   "winId", "hide", "show"):
        assert callable(getattr(W, nombre, None)), nombre
    assert _admite(W._set_status, YO, "texto", "#00E5FF")


# ── Ventanas ↔ cambio de interfaz, montaje y bandeja única ───────────────────────

def test_ventanas_cumplen_el_contrato_del_relevo_y_del_corte4():
    import main
    from ui.web_shell import VentanaWeb
    for W in (VentanaWeb, main.LuneCDWindow):
        for nombre in ("estado_para_cambio", "aplicar_estado", "cerrar_para_cambio", "iniciar_servicios",
                       "salir_de_verdad", "aviso_cambio", "_montar_servicios_c4", "closeEvent"):
            assert callable(getattr(W, nombre, None)), f"{W.__name__}.{nombre}"
        assert _es_senal(W, "cambio_interfaz_pedido")
        assert isinstance(inspect.getattr_static(W, "tray"), property)       # lee la bandeja única
        assert inspect.getattr_static(W, "tray").fset is not None
        assert "FABRICAS_C4" in vars(W) and W.FABRICAS_C4 is None
        assert "diferir_servicios" in _firma(W.__init__).parameters
    assert callable(VentanaWeb._registrar_puente_escritorio)
    assert callable(main.LuneCDWindow._build_tray) and callable(main.LuneCDWindow._build_tray_respaldo)


def test_settings_panel_y_panel_de_escritorio():
    from ui import escritorio_panel_nativo as epn
    from ui import settings_panel as sp
    assert "servicios" in _firma(sp.SettingsPanel.__init__).parameters
    for nombre in ("usar_servicios", "servicios_c4", "_escritorio_cambiado"):
        assert callable(getattr(sp.SettingsPanel, nombre, None)), nombre
    assert _es_senal(sp.SettingsPanel, "escritorio_cambiado")
    assert _admite(sp.aplicar_seccion_escritorio, "tema", None, None, None)
    P = epn.PanelEscritorioNativo
    assert _es_senal(P, "cambiado") and epn.SECCIONES == ("tema", "juego", "rendimiento", "atajos", "radial")
    assert _admite(P.__init__, YO, None, None, atajos=None, apps_visibles=None, liberar_memoria=None)
    for nombre, args in (("set_atajos", (None,)), ("guardar_ya", ()), ("recargar", ())):
        assert _admite(getattr(P, nombre), YO, *args), nombre


def test_web_bridge_expone_lo_del_corte4():
    from ui.web_bridge import LuneBridge
    for nombre in ("pausar_aburrimiento", "restaurar_ultima", "retomar_sesion", "estado_inicial",
                   "_avisar_ordenes_pendientes", "limpiar_chat"):
        assert callable(getattr(LuneBridge, nombre, None)), nombre


def test_config_trae_fundido_ms():
    from nucleo.config import Config
    assert Config.DEFAULT_CONFIG["interfaz"]["fundido_ms"] == 180
    # y la vuelta de las claves del corte 4 que se leen desde varias piezas
    d = copy.deepcopy(Config.DEFAULT_CONFIG)
    assert d["patata"]["tema"] == "cian" and d["patata"]["caritas"] == "clasico"
    assert d["features"]["minimizar_a_bandeja"] is True
