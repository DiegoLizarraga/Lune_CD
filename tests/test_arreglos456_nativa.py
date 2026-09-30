"""
Arreglos de la revisión 4-5-6, parte nativa (y lo común que toca: acciones_ui,
montaje_escritorio, anfitriones, panel de escritorio, modo juego). Offscreen y con
dobles: sin Telegram, ni Win32 que cambie algo, ni config.json real.

  VS1  Web con la flotante guardada: Lune en la barra lateral cuenta como asistente
       para expresiones y baile (radial SVG y bandeja); la expresión la pone la barra.
  VS2  Panel de escritorio nativo: relee al enseñarse y cuando la bandeja/radial/atajo
       cambian el tema, siempre encima o la barra de tareas; escribe solo lo tocado.
  VS4  «Comentar» en la nativa durante una partida avisa sin sacar a la asistente.
  VS5  Salir de verdad y parar el bot avisan «Se detuvo…» a Telegram, una vez.
  VS6  El modo juego forzado viaja en el cambio de interfaz (y no se pierde).
  VS7  «Detener» + cambio de interfaz: un solo «Se detuvo…».
  RH4  «Liberar memoria» recolecta en el hilo de Qt antes de recortar en el suyo.
  Sospechas/riesgos: cerrar_para_cambio sigue si cortar la respuesta falla; el
       scroll diferido y las notas/red diferidas no tocan una ventana que se fue.
"""
import copy
import json
import os
import sys
import threading
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
pytest.importorskip("PyQt6.QtWidgets")

try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (main lo usa).
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, pyqtSignal  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QMainWindow, QScrollArea, QWidget  # noqa: E402

from nucleo import acciones_ui as au  # noqa: E402
from nucleo.config import Config  # noqa: E402
from servicios.telegram_worker import AVISO_TG_DETENIDA  # noqa: E402
from ui import montaje_escritorio as me  # noqa: E402
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from test_montaje_escritorio import (GestorFalso, JuegoFalso, AsistenteFalsa, TemaFalso,  # noqa: E402
                                     TrayFalso)


# ── Dobles comunes ─────────────────────────────────────────────────────────────

class CfgDoble:
    """Config de mentira con las dos formas: get/set (montaje, anfitriones) y
    `.config` + save() (paneles nativos, ControlTema)."""
    DEFAULT_CONFIG = Config.DEFAULT_CONFIG

    def __init__(self):
        self.config = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.guardados = 0

    def get(self, s, k, d=None):
        return self.config.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.config.setdefault(s, {})[k] = copy.deepcopy(v)

    def save(self):
        self.guardados += 1

    def feature(self, n, d=True):
        return self.config.get("features", {}).get(n, d)

    def recargar(self):
        return False


class AutoinicioFalso:
    def activo(self):
        return False

    def establecer(self, on):
        return bool(on)


def _fabricas(**extra):
    f = {"tema": lambda c, p: TemaFalso(c, p), "juego": JuegoFalso, "gestor_atajos": GestorFalso(),
         "tray": TrayFalso, "autoinicio": AutoinicioFalso(), "recortar": lambda: (10.0, 5.0),
         "modelos_vrm": lambda: [], "sonar": lambda n: None, "traer_al_frente": None, "ocio": False, "vida": False, "escenario": False}
    f.update(extra)
    return f


def _borrar_pendientes():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


# ═══ VS1: Lune en la barra lateral de la web ════════════════════════════════════

class PuenteWebFalso(QObject):
    """Lo que AnfitrionWeb usa de LuneBridge."""
    acto = pyqtSignal(str)
    aviso = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._overlay = None
        self._worker = None
        self._llamada = None
        self.voice = types.SimpleNamespace(_enabled=False)

    def asistente_toggle(self):
        return False

    def comentar_pantalla(self):
        return False

    def voz_toggle(self):
        return False


def test_contexto_con_lune_en_la_barra_cuenta_para_expresiones_y_baile():
    est = types.SimpleNamespace(grande=False, sentada="", bailando="manual", durmiendo=False)
    barra = au.Contexto(modo="normal", render="animado", asistente_visible=False, asistente_barra=True)
    nadie = au.Contexto(modo="normal", render="animado", asistente_visible=False)
    for i in ("expresiones", "expresion", "bailar", "baile_pausa"):
        assert au.visible(i, est, barra), i
        assert not au.visible(i, est, nadie), i
    # Lo que es de la flotante (dormir, llevarla, cerrarla, sentarla) no.
    for i in ("dormir", "esquina", "cerrar_asistente", "sentarse", "tamano"):
        assert not au.visible(i, est, barra), i
    # Corte 8: la comida sí (ComidaWeb la dibuja dentro de la ventana y se come sobre la de la barra).
    assert au.visible("comer_pastel", est, barra) and not au.visible("comer_pastel", est, nadie)


@pytest.fixture
def web(qapp):
    from ui.anfitrion_web import AnfitrionWeb
    cfg = CfgDoble()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    puente = PuenteWebFalso(cfg)
    ventana = QWidget()
    ventana.show()
    s = me.montar_escritorio(esc, AnfitrionWeb(puente, ventana), cfg, fabricas=_fabricas())
    bailes = []
    s.despachador.registrar("bailar", lambda: bailes.append(1))     # lo registra montar_ocio
    yield types.SimpleNamespace(s=s, esc=esc, cfg=cfg, puente=puente, ventana=ventana, bailes=bailes)
    s.desmontar()
    esc.cerrar()
    ventana.close()
    ventana.deleteLater()
    _borrar_pendientes()


def test_web_radial_y_bandeja_con_lune_en_la_barra(web, monkeypatch):
    from ui.puente_escritorio import PuenteEscritorio
    monkeypatch.setattr(me, "MS_EXPRESION", 30)
    s, puente = web.s, web.puente
    ctx = s.contexto()
    assert ctx.asistente_barra is True and ctx.asistente_visible is False
    # El radial SVG (el mismo puente que usa la página): Expresiones y Bailar.
    pe = PuenteEscritorio(s, web.esc, web.cfg, anfitrion=s.anfitrion, contexto=s.contexto)
    ids = [i["id"] for i in json.loads(pe.acciones_catalogo("radial"))]
    assert "expresiones" in ids and "bailar" in ids and "dormir" not in ids
    assert [e["arg"] for e in json.loads(pe.acciones_catalogo("expresiones"))][:2] == ["happy", "sad"]
    # La expresión la pone la barra (señal `acto` del puente web) y vuelve sola.
    caras = []
    puente.acto.connect(caras.append)
    assert pe.accion_menu("expresion", "happy") is True
    assert caras == ["happy"]
    QTest.qWait(150)
    assert caras == ["happy", "normal"]
    assert pe.accion_menu("bailar", "") is True and web.bailes == [1]
    # La bandeja: Bailar vuelve a sus rápidas (Dormir no: el sueño es de la flotante).
    menu = au.menu_bandeja(s.despachador, web.esc.estado.actual(), s.contexto(),
                           web.cfg.get("bandeja", "acciones"), [])
    [lune] = [it for it in menu if it.etiqueta == "Lune"]
    rapidas = [h.id for h in lune.hijos]
    assert "bailar" in rapidas and "dormir" not in rapidas
    # Con la ventana escondida no hay barra a la vista.
    web.ventana.hide()
    assert s.contexto().asistente_barra is False
    assert "expresiones" not in [i["id"] for i in json.loads(pe.acciones_catalogo("radial"))]
    # Con la flotante fuera, la expresión es suya (la barra no la dibuja).
    web.ventana.show()
    flot = AsistenteFalsa()
    flot.render = "animado"
    puente._overlay = flot
    ctx = s.contexto()
    assert ctx.asistente_visible is True and ctx.asistente_barra is False
    caras.clear()
    assert pe.accion_menu("expresion", "sad") is True
    assert ("set_estado", "sad", 30) in flot.diario and caras == []
    pe.cerrar()


# ═══ VS2: el panel de escritorio nativo no pisa lo que cambió la bandeja ══════════

def test_panel_no_devuelve_el_tema_que_puso_la_bandeja(qapp):
    """El escenario de la revisión: bandeja Tema ▸ Magenta → Ajustes → mover la
    saturación. Antes el panel escribía las cinco claves de sus controles viejos."""
    from ui.escritorio_panel_nativo import PanelEscritorioNativo
    from ui.tema_qt import ControlTema
    cfg = CfgDoble()
    panel = PanelEscritorioNativo(cfg, None, retardo_ms=0)
    tema_ctl = ControlTema(cfg, retardo_ms=0)
    tema_ctl.aplicar_preset("magenta_mate")
    tema_ctl.guardar_ya()
    panel.slider_sat.setValue(90)
    panel.guardar_ya()
    assert cfg.config["tema"]["preset"] == "magenta_mate"
    assert cfg.config["tema"]["saturacion"] == 0.9
    assert tema_ctl.recargar()["preset"] == "magenta_mate"
    panel.deleteLater()
    tema_ctl.deleteLater()


class SenalesFalsas(QObject):
    config = pyqtSignal(str, str)


def test_panel_enlazado_sigue_a_la_bandeja_y_se_suelta(qapp):
    from ui.escritorio_panel_nativo import PanelEscritorioNativo
    from ui.tema_qt import ControlTema
    cfg = CfgDoble()
    tema_ctl = ControlTema(cfg, retardo_ms=60000)          # su guardado diferido no llega solo
    senales = SenalesFalsas()
    servicios = types.SimpleNamespace(tema=tema_ctl, config_cambio=senales.config, _deshacer=[])
    panel = PanelEscritorioNativo(cfg, None, retardo_ms=0)
    panel.enlazar_servicios(servicios)
    tema_ctl.aplicar_preset("violeta")                     # la bandeja, aún sin escribir
    assert panel.combo_preset.currentData() == "violeta" and not panel.pendiente
    assert cfg.config["tema"]["preset"] == "cian"
    panel.slider_sat.setValue(130)
    panel.guardar_ya()
    assert cfg.config["tema"]["preset"] == "violeta" and cfg.config["tema"]["saturacion"] == 1.3
    assert not tema_ctl.pendiente                          # lo suyo, antes que lo nuestro
    # Siempre encima cambiado desde el radial: la casilla, releída (sin guardar nada).
    cfg.set("avatar", "siempre_encima", False)
    senales.config.emit("avatar", "siempre_encima")
    assert not panel.chk_encima.isChecked() and not panel.pendiente
    # Al desmontar los servicios, el panel los suelta.
    for f in servicios._deshacer:
        f()
    tema_ctl.aplicar_preset("ambar")
    cfg.set("avatar", "siempre_encima", True)
    senales.config.emit("avatar", "siempre_encima")
    assert panel.combo_preset.currentData() == "violeta" and not panel.chk_encima.isChecked()
    panel.deleteLater()
    tema_ctl.deleteLater()


class AnfitrionNativoFalso:
    """Anfitrión «br»: set_en_barra guarda la clave como poner_en_barra (sin Win32)."""
    modo = "br"
    soporta_llamada = False

    def __init__(self, cfg):
        self.cfg = cfg

    def mostrar_ventana(self): pass
    def ventana_visible(self): return True
    def asistente(self): return None
    def alternar_asistente(self): return False
    def voz_on(self): return False
    def alternar_voz(self): return False
    def llamada_on(self): return False
    def alternar_llamada(self): return False
    def abrir_ajustes(self, seccion=""): pass
    def salir(self): pass
    def aviso(self, texto): pass
    def set_aburrimiento(self, activo): pass
    def en_barra_on(self): return bool(self.cfg.get("interfaz", "en_barra_tareas", True))
    def set_en_barra(self, on): self.cfg.set("interfaz", "en_barra_tareas", bool(on))


def test_panel_con_la_bandeja_de_verdad_y_al_enseñarse(qapp):
    from ui.escritorio_panel_nativo import PanelEscritorioNativo
    from ui.tema_qt import ControlTema
    cfg = CfgDoble()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    s = me.montar_escritorio(esc, AnfitrionNativoFalso(cfg), cfg, fabricas=_fabricas(
        tema=lambda c, p: ControlTema(c, retardo_ms=0, parent=p)))
    panel = PanelEscritorioNativo(cfg, None, retardo_ms=0)
    panel.enlazar_servicios(s)
    d = s.despachador
    assert d.ejecutar("tema", "rojo_neon") and d.ejecutar("siempre_encima") and d.ejecutar("en_barra_tareas")
    assert panel.combo_preset.currentData() == "rojo_neon"
    assert not panel.chk_encima.isChecked() and not panel.chk_barra.isChecked()
    # Lo siguiente que se toca en el panel no devuelve nada de eso.
    panel.spin_fps_max.setValue(45)
    panel.guardar_ya()
    assert cfg.config["avatar"]["fps_max"] == 45 and cfg.config["avatar"]["siempre_encima"] is False
    assert cfg.config["interfaz"]["en_barra_tareas"] is False
    assert s.tema.recargar()["preset"] == "rojo_neon"
    # Con Ajustes cerrado alguien cambia config.json (patata, otra ventana): al enseñarse, se relee.
    panel.hide()
    cfg.config["avatar"]["siempre_encima"] = True
    cfg.config["juego"]["fps"] = 7
    panel.show()
    assert panel.chk_encima.isChecked() and panel.spin_juego_fps.value() == 7 and not panel.pendiente
    panel.hide()
    s.desmontar()
    esc.cerrar()
    panel.deleteLater()
    _borrar_pendientes()


# ═══ VS4: «Comentar» en la nativa durante una partida ══════════════════════════

def test_nativa_comentar_en_partida_avisa_sin_sacar_la_asistente():
    from ui.anfitrion_nativo import AVISO_JUEGO_PANTALLA, AnfitrionNativo
    from ui.web_bridge import AVISO_JUEGO_PANTALLA as AVISO_WEB
    hechos, partida = [], {"on": True}
    masc = types.SimpleNamespace(cerrado=False, isVisible=lambda: False,
                                 comentar_pantalla=lambda: hechos.append("comentar"))
    estado = types.SimpleNamespace(actual=lambda: types.SimpleNamespace(juego=partida["on"]))
    win = types.SimpleNamespace(escritorio=types.SimpleNamespace(estado=estado), _asistente_viva=lambda: masc,
                                _toggle_overlay=lambda: hechos.append("sacar"),
                                _set_status=lambda texto, color: hechos.append(("aviso", texto)))
    anf = AnfitrionNativo(win)
    assert anf.comentar() is False
    assert hechos == [("aviso", AVISO_JUEGO_PANTALLA)] and AVISO_JUEGO_PANTALLA == AVISO_WEB
    partida["on"] = False
    assert anf.comentar() is True and hechos[-2:] == ["sacar", "comentar"]


# ═══ VS5 / VS7 / sospecha: órdenes de Telegram al cerrar, parar o cambiar ═══════

class HiloFalso(QObject):
    """AIWorker o TelegramBotWorker vistos desde la ventana (con sus señales)."""
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    log_signal = pyqtSignal(str)
    stopped = pyqtSignal()
    orden_recibida = pyqtSignal(str, str)

    def __init__(self, hechos=None, nombre=""):
        super().__init__()
        self.vivo = True
        self.hechos = hechos if hechos is not None else []
        self.nombre = nombre

    def isRunning(self):
        return self.vivo

    def stop(self):
        self.hechos.append(f"{self.nombre}.stop")

    def requestInterruption(self):
        pass

    def wait(self, ms=0):
        return True

    def responder_orden(self, oid, texto):
        self.hechos.append(("tg", oid, texto))
        return True

    def terminar(self):
        self.vivo = False
        self.finished.emit()


def _enlazar(yo, *nombres):
    import main
    for n in nombres:
        setattr(yo, n, types.MethodType(getattr(main.LuneCDWindow, n), yo))
    return yo


def _nativa_para_relevo(hechos):
    """Lo que usan cerrar_para_cambio, _stop_generation y _cortar_respuesta."""
    boton = types.SimpleNamespace(hide=lambda: None, show=lambda: None, setEnabled=lambda v: None,
                                  setFocus=lambda: None)
    yo = types.SimpleNamespace(
        _gen=1, ai_worker=HiloFalso(hechos, "ia"), current_provider="ollama",
        ai_manager=types.SimpleNamespace(providers={"ollama": types.SimpleNamespace(cancel_flag=False)}),
        _turno={"remoto": "o1", "proveedor": "ollama"}, _ultima_orden_tg="o1",
        _typing_indicator=None, _current_bubble=None, _seguidor=None, _voz_stream=None, _timers_plan=[],
        stop_btn=boton, send_btn=boton, input_field=boton, _set_status=lambda *a: None,
        acciones=types.SimpleNamespace(cerrar=lambda: hechos.append("acciones.cerrar"), pendientes=lambda: []),
        voice=types.SimpleNamespace(cancelar=lambda: None, al_hablar=None, on_error=None),
        lune_face=types.SimpleNamespace(_player=None, set_state=lambda *a, **k: None),
        _grabadora=None, _transcriptor=None, _sondeo_prov=None, _timer_estado=None,
        chats=types.SimpleNamespace(guardar=lambda: None),
        notas=types.SimpleNamespace(cerrar=lambda: None), red=types.SimpleNamespace(detener=lambda: None),
        _overlay=types.SimpleNamespace(cerrado=False, isVisible=lambda: True,
                                       close=lambda: hechos.append("asistente.close"), deleteLater=lambda: None),
        _tg_worker=HiloFalso(hechos, "tg"),
        escritorio=types.SimpleNamespace(cerrar=lambda: hechos.append("escritorio.cerrar")),
        _hub_cliente=None, _hub_en_hilo=types.SimpleNamespace(detener=lambda: hechos.append("hub.detener")),
        tray=None, _servicios_c4=types.SimpleNamespace(desmontar=lambda: hechos.append("c4.desmontar")),
        hide=lambda: hechos.append("hide"), close=lambda: hechos.append("close"), _relevada=False)
    return _enlazar(yo, "cerrar_para_cambio", "_cortar_respuesta", "_worker_vivo", "_cancelar_worker",
                    "_cancelar_plan", "_asistente_viva", "_responder_telegram", "_stop_generation")


def _soltar(*hilos):
    for h in hilos:
        if h is not None:
            h.terminar()


def test_detener_y_luego_cambiar_de_interfaz_avisa_una_vez(qapp):
    hechos = []
    yo = _nativa_para_relevo(hechos)
    ia, tg = yo.ai_worker, yo._tg_worker
    yo._stop_generation()                                  # «Detener»: el hilo aún corta
    assert hechos == [("tg", "o1", AVISO_TG_DETENIDA)] and ia.isRunning()
    assert "remoto" not in yo._turno
    en_marcha = yo.cerrar_para_cambio()                    # y se cambia de interfaz enseguida
    avisos = [h for h in hechos if isinstance(h, tuple)]
    assert avisos == [("tg", "o1", AVISO_TG_DETENIDA)]
    assert en_marcha == {"asistente_fuera": True, "telegram": True}
    _soltar(ia, tg)


def test_cambio_de_interfaz_avisa_antes_de_parar_el_bot_una_vez(qapp):
    hechos = []
    yo = _nativa_para_relevo(hechos)
    ia, tg = yo.ai_worker, yo._tg_worker
    yo.cerrar_para_cambio()
    avisos = [h for h in hechos if isinstance(h, tuple)]
    assert avisos == [("tg", "o1", AVISO_TG_DETENIDA)]
    assert hechos.index(avisos[0]) < hechos.index("tg.stop")
    _soltar(ia, tg)


def test_cerrar_para_cambio_suelta_todo_aunque_cortar_la_respuesta_falle(qapp):
    import ui.cambio_interfaz as ci
    hechos = []
    yo = _nativa_para_relevo(hechos)
    ia, tg = yo.ai_worker, yo._tg_worker

    def revienta():
        raise RuntimeError("burbuja ya borrada")
    yo._cortar_respuesta = revienta
    en_marcha = yo.cerrar_para_cambio()
    assert en_marcha == {"asistente_fuera": True, "telegram": True}
    for h in ("c4.desmontar", "acciones.cerrar", "asistente.close", "tg.stop", "escritorio.cerrar",
              "hub.detener", "hide", "close"):
        assert h in hechos, h
    assert ia in ci._retenidos and yo.ai_worker is None and yo._tg_worker is None
    _soltar(ia, tg)


def test_salir_de_verdad_avisa_las_ordenes_sin_respuesta_una_vez(qapp, monkeypatch):
    import main
    salidas = []
    monkeypatch.setattr(main, "QApplication", types.SimpleNamespace(quit=lambda: salidas.append("quit")))
    hechos = []
    yo = types.SimpleNamespace(
        tray=None, _quit_real=True, _relevada=False, config=CfgDoble(),
        memoria=types.SimpleNamespace(get_stats=lambda: {}, cerrar_sesion=lambda r: None),
        _grabadora=None, chats=types.SimpleNamespace(guardar=lambda: None),
        notas=types.SimpleNamespace(cerrar=lambda: None), red=types.SimpleNamespace(detener=lambda: None),
        acciones=types.SimpleNamespace(cerrar=lambda: hechos.append("acciones.cerrar"),
                                       pendientes=lambda: [{"id": "p1", "remoto": True}]),
        _servicios_c4=None, escritorio=types.SimpleNamespace(cerrar=lambda: None), _overlay=None,
        _timer_estado=types.SimpleNamespace(stop=lambda: None), _hub_cliente=None, _hub_en_hilo=None,
        lune_face=types.SimpleNamespace(_player=None),
        ai_worker=HiloFalso(hechos, "ia"), _tg_worker=HiloFalso(hechos, "tg"),
        _turno={"remoto": "o1"}, _ultima_orden_tg="o2")
    _enlazar(yo, "closeEvent", "_worker_vivo", "_responder_telegram")
    ev = types.SimpleNamespace(accept=lambda: hechos.append("accept"), ignore=lambda: hechos.append("ignore"))
    yo.closeEvent(ev)
    avisos = [h for h in hechos if isinstance(h, tuple)]
    assert avisos == [("tg", "o1", AVISO_TG_DETENIDA), ("tg", "o2", AVISO_TG_DETENIDA)]
    assert hechos.index(avisos[-1]) < hechos.index("acciones.cerrar") < hechos.index("tg.stop")
    assert salidas == ["quit"] and "remoto" not in yo._turno and yo._ultima_orden_tg == ""
    yo.closeEvent(ev)                                      # otra vez (aboutToQuit…): nada más
    assert [h for h in hechos if isinstance(h, tuple)] == avisos
    _soltar(yo.ai_worker, yo._tg_worker)


def test_parar_el_bot_con_una_orden_en_curso_avisa_antes(qapp):
    hechos = []
    tg = HiloFalso(hechos, "tg")
    ia = HiloFalso(hechos, "ia")
    yo = types.SimpleNamespace(_tg_worker=tg, ai_worker=ia, _turno={"remoto": "o3"}, _ultima_orden_tg="o3",
                               acciones=types.SimpleNamespace(pendientes=lambda: []),
                               _set_telegram_btn_style=lambda *a: hechos.append("boton"))
    _enlazar(yo, "_toggle_telegram", "_worker_vivo", "_responder_telegram")
    yo._toggle_telegram()
    assert hechos[:2] == [("tg", "o3", AVISO_TG_DETENIDA), "tg.stop"]
    assert yo._tg_worker is None and "remoto" not in yo._turno
    _soltar(ia, tg)


# ═══ VS6: el modo juego forzado en el cambio de interfaz ══════════════════════════

def _juego_real(cfg, esc):
    from servicios import modo_juego as mj
    from ui.modo_juego_qt import ControlModoJuego
    return ControlModoJuego(esc, cfg, detector=mj.DetectorJuego(cfg, pids=[os.getpid()]),
                            recortar=lambda: (1.0, 1.0), prioridad=lambda baja: None, intervalo_ms=40)


def test_control_modo_juego_expone_el_forzado(qapp):
    cfg = CfgDoble()
    cfg.set("juego", "activo", False)
    esc = ServiciosEscritorio(cfg)
    j = _juego_real(cfg, esc)
    assert j.forzado is None
    j.forzar(True)
    assert j.forzado is True and j.activo()
    j.forzar(False)
    assert j.forzado is False and not j.activo()
    j.forzar(None)
    assert j.forzado is None
    j.detener()
    j.deleteLater()


def test_el_modo_juego_forzado_pasa_a_la_ventana_nueva_y_no_se_pierde(qapp):
    cfg = CfgDoble()
    cfg.set("juego", "activo", False)                      # sin detección: solo el forzado
    esc_vieja, esc_nueva = ServiciosEscritorio(cfg), ServiciosEscritorio(cfg)
    vieja_j, nueva_j = _juego_real(cfg, esc_vieja), _juego_real(cfg, esc_nueva)
    vieja_j.forzar(True)                                   # bandeja ▸ Modo juego
    vieja = types.SimpleNamespace(MODO_INTERFAZ="nativo", current_provider="ollama",
                                  voice=types.SimpleNamespace(_enabled=False), _overlay=None, _tg_worker=None,
                                  _servicios_c4=types.SimpleNamespace(juego=vieja_j))
    _enlazar(vieja, "estado_para_cambio", "_asistente_a_la_vista", "_asistente_viva")
    estado = vieja.estado_para_cambio()
    assert estado["juego_forzado"] is True
    vieja_j.detener()                                      # la vieja desmonta (devuelve lo suyo)

    orden = []
    esc_nueva.registrar("juego", nueva_j)
    nueva = types.SimpleNamespace(_servicios_listos=False, tray=object(), escritorio=esc_nueva,
                                  _overlay=None, _tg_worker=None,
                                  _servicios_c4=types.SimpleNamespace(juego=nueva_j),
                                  _toggle_overlay=lambda: orden.append(("asistente", nueva_j.activo())),
                                  _toggle_telegram=lambda: orden.append("telegram"))
    _enlazar(nueva, "iniciar_servicios", "_asistente_a_la_vista", "_asistente_viva")
    nueva.iniciar_servicios(dict(estado, asistente_fuera=True))
    # La asistente sale antes (sin partida) y luego el forzado la esconde con el plan.
    assert orden == [("asistente", False)]
    assert nueva_j.forzado is True and nueva_j.activo()
    QTest.qWait(150)                                       # unos cuantos tics del detector
    assert nueva_j.forzado is True and nueva_j.activo()
    esc_nueva.cerrar()
    for j in (vieja_j, nueva_j):
        j.deleteLater()


# ═══ RH4: «Liberar memoria» ════════════════════════════════════════════════════

def test_liberar_memoria_recolecta_en_el_hilo_de_qt_y_recorta_en_otro(qapp, monkeypatch):
    llamadas, hecho = [], threading.Event()
    monkeypatch.setattr(me.gc, "collect", lambda *a: llamadas.append(("gc", threading.get_ident())) or 0)

    def recortar():
        llamadas.append(("recortar", threading.get_ident()))
        hecho.set()
        return (10.0, 5.0)
    cfg = CfgDoble()
    esc = ServiciosEscritorio(cfg)
    s = me.montar_escritorio(esc, AnfitrionNativoFalso(cfg), cfg, fabricas=_fabricas(recortar=recortar))
    principal = threading.get_ident()
    assert s.despachador.ejecutar("liberar_memoria")
    assert hecho.wait(3)
    i = llamadas.index(next(x for x in llamadas if x[0] == "recortar"))
    assert ("gc", principal) in llamadas[:i]                 # antes, en el hilo de Qt
    assert llamadas[i][1] != principal                       # EmptyWorkingSet en su hilo
    assert all(t == principal for n, t in llamadas if n == "gc")
    s.desmontar()
    esc.cerrar()


# ═══ Riesgos bajos: avisos diferidos con la ventana ya ida ═════════════════════

def test_scroll_diferido_con_la_ventana_ya_borrada(qapp, monkeypatch):
    import main
    from PyQt6 import sip
    errores = []
    monkeypatch.setattr(sys, "excepthook", lambda t, v, tb: errores.append(v))
    W = main.LuneCDWindow
    yo = W.__new__(W)
    QMainWindow.__init__(yo)
    yo.scroll = QScrollArea(yo)
    yo._scroll_bottom()
    yo.deleteLater()                                       # el cambio de interfaz la borra
    _borrar_pendientes()
    assert sip.isdeleted(yo)
    QTest.qWait(150)
    assert errores == []


def test_notas_y_red_diferidas_no_arrancan_en_una_ventana_que_se_va():
    hechos = []
    yo = types.SimpleNamespace(_relevada=False, _quit_real=False,
                               notas=types.SimpleNamespace(reindexar=lambda: hechos.append("notas")),
                               red=types.SimpleNamespace(anunciar=lambda: hechos.append("red")))
    _enlazar(yo, "_cerrandose", "_reindexar_notas", "_anunciar_red")
    yo._reindexar_notas()
    yo._anunciar_red()
    assert hechos == ["notas", "red"]
    yo._relevada = True                                    # cerrar_para_cambio ya cerró notas y red
    yo._reindexar_notas()
    yo._anunciar_red()
    yo._relevada, yo._quit_real = False, True              # saliendo
    yo._reindexar_notas()
    assert hechos == ["notas", "red"]
