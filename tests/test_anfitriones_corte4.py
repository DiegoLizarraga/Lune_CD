"""
Integración final del corte 4: el montaje de verdad en las dos ventanas.

Web: `VentanaWeb.__init__` DE VERDAD con Chromium sustituido (vista y página falsas,
servidor http falso) y el QWebChannel real → el puente `escritorio` está registrado
antes de setUrl, la bandeja es UNA, los atajos no chocan en un cambio en caliente, salir
desmonta una vez, la mascota nace sin icono, la última conversación vuelve al arrancar.
Nativa: `LuneCDWindow` con sus métodos de verdad sobre un QMainWindow sin construir la
interfaz (y un __init__ de verdad con dobles para comprobar que el tema va antes de
_init_ui). Las piezas pesadas del montaje (tema, modo juego, bandeja del sistema,
RegisterHotKey) son dobles: un «sistema» falso que cuenta iconos visibles y combinaciones
registradas y rechaza una combinación ocupada como lo haría Windows (1409).
Además: Ajustes nativos aplican cada apartado, limpiar chat avisa a Telegram y los
comandos nuevos de patata (sin Qt).
"""
import copy
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
pytest.importorskip("PyQt6.QtWidgets")
try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (fixture qapp).
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401
except ImportError:
    pass

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWebChannel import QWebChannel  # noqa: E402
from PyQt6.QtWidgets import QMainWindow, QSystemTrayIcon, QWidget  # noqa: E402

from nucleo.config import Config  # noqa: E402
from servicios.atajos_globales import normalizar  # noqa: E402


# ═══ El «sistema» falso: iconos de la bandeja y combinaciones registradas ════════

class Sistema:
    iconos: list = []            # TrayGlobal visibles ahora
    max_iconos = 0               # el máximo que hubo a la vez
    combos: dict = {}            # combinación → gestor que la tiene
    choques: list = []           # lo que Windows habría rechazado (1409)
    eventos: list = []           # ("montar"|"desmontar", dueño)

    @classmethod
    def reset(cls):
        cls.iconos, cls.max_iconos, cls.combos, cls.choques, cls.eventos = [], 0, {}, [], []


class TrayGlobal(QObject):
    activated = pyqtSignal(object)
    MessageIcon = QSystemTrayIcon.MessageIcon              # main.py y web_shell los usan
    ActivationReason = QSystemTrayIcon.ActivationReason

    @staticmethod
    def isSystemTrayAvailable():
        return True

    def __init__(self, icono=None, parent=None):
        super().__init__(parent)
        self.visible, self.mensajes, self.menu, self.tooltip = False, [], None, ""

    def setContextMenu(self, m):
        self.menu = m

    def contextMenu(self):
        return self.menu

    def setToolTip(self, t):
        self.tooltip = t

    def setIcon(self, i):
        pass

    def show(self):
        self.visible = True
        if self not in Sistema.iconos:
            Sistema.iconos.append(self)
        Sistema.max_iconos = max(Sistema.max_iconos, len(Sistema.iconos))

    def hide(self):
        self.visible = False
        if self in Sistema.iconos:
            Sistema.iconos.remove(self)

    def showMessage(self, *a):
        self.mensajes.append(a)

    def deleteLater(self):
        self.hide()
        super().deleteLater()


class GestorGlobal:
    """GestorAtajos falso con el registro compartido de «Windows»."""

    def __init__(self):
        self._on_atajo = None
        self.activos = {}
        self.vivo = False

    def activo(self):
        return self.vivo

    def iniciar(self):
        self.vivo = True
        return True

    def detener(self):
        self.vivo = False

    def registrar(self, id_, combo):
        c = normalizar(combo)
        duenio = Sistema.combos.get(c)
        if duenio is not None and duenio is not self:
            Sistema.choques.append((id_, c))
            return "Otra aplicación ya usa esa combinación (1409)."
        Sistema.combos[c] = self
        self.activos[id_] = c
        return None

    def quitar(self, id_):
        c = self.activos.pop(id_, None)
        if c is not None and Sistema.combos.get(c) is self:
            del Sistema.combos[c]

    def quitar_todos(self):
        for i in list(self.activos):
            self.quitar(i)


class TemaFalso(QObject):
    cambio = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config, self.diario = config, []

    def _preset(self):
        return self.config.get("tema", "preset", "cian")

    def actual(self):
        return {"preset": self._preset(), "hue": 0.0, "saturacion": 1.0, "tenir_pop": False,
                "tenir_fondo": False}

    def css_json(self):
        return "null" if self._preset() == "cian" else '{"--cyan-500": "#FF00AA"}'

    def qss_menu(self):
        return "QMenu {}"

    def colores_radial(self):
        return {"acento": "#00E5FF"}

    def aplicar_preset(self, p):
        self.diario.append(("preset", p))

    def recargar(self):
        self.diario.append("recargar")
        return self.actual()

    def set_mascota(self, v):
        pass

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

    def recargar_config(self):
        self.diario.append("recargar_config")

    def set_mascota(self, v):
        pass


class AutoinicioFalso:
    def __init__(self):
        self.on = False

    def activo(self):
        return self.on

    def establecer(self, q):
        self.on = bool(q)
        return self.on


def fabricas():
    from ui.atajos_qt import GestorAtajosQt
    return {
        "tema": lambda config, parent: TemaFalso(config, parent),
        "juego": lambda escritorio, config, *, voice=None, parent=None: JuegoFalso(
            escritorio, config, voice=voice, parent=parent),
        "atajos": lambda config, *, disponible, parent=None: GestorAtajosQt(
            config, disponible=disponible, gestor=GestorGlobal(), parent=parent),
        "tray": TrayGlobal,
        "autoinicio": AutoinicioFalso(),
        "recortar": lambda: (100.0, 80.0),
        "modelos_vrm": lambda: [],
        "sonar": lambda nombre: None,
        "traer_al_frente": None,
        "ocio": False,               # cortes 5/6 aparte (tests/test_anfitriones_c56.py)
        "vida": False,               # cortes 7/8 aparte (tests/test_anfitriones_c78_int.py)
        "escenario": False,          # cortes 9/10 aparte (tests/test_anfitriones_c910_int.py)
    }


class MascotaFalsa(QObject):
    """La mascota flotante (CompanionFlotante / AvatarOverlay) de mentira."""
    visibilidad = pyqtSignal(bool)
    recrear = pyqtSignal()
    menu_pedido = pyqtSignal(str, object)
    creadas: list = []

    def __init__(self, config=None, ai_manager=None, render="", bandeja=True, parent=None):
        super().__init__()
        self.bandeja, self.render = bandeja, render or "animado"
        self.cerrado, self.visible, self.diario = False, False, []
        MascotaFalsa.creadas.append(self)

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True
        self.visibilidad.emit(True)

    def hide(self):
        self.visible = False
        self.visibilidad.emit(False)

    def raise_(self):
        pass

    def close(self):
        self.cerrado, self.visible = True, False

    def quitar_bandeja(self):
        self.diario.append("quitar_bandeja")

    def set_bus_estado(self, bus):
        pass

    def comentar_pantalla(self):
        self.diario.append("comentar")


class SpritesFalsa(MascotaFalsa):
    def __init__(self, config=None, parent=None, bandeja=True):
        super().__init__(config, render="sprites", bandeja=bandeja)


# ═══ Web: VentanaWeb de verdad sin Chromium ═══════════════════════════════════

class PaginaFalsa:
    def __init__(self):
        self.canal, self.js, self.muda = None, [], False

    def setBackgroundColor(self, c):
        pass

    def setWebChannel(self, c):
        self.canal = c

    def runJavaScript(self, js, cb=None):
        self.js.append(js)

    def setAudioMuted(self, v):
        self.muda = v


class AjustesFalsos:
    def setAttribute(self, *a):
        pass


class VistaFalsa(QWidget):
    """QWebEngineView de mentira: anota qué objetos tenía el canal al cargar la página."""
    loadFinished = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._pagina = PaginaFalsa()
        self.urls, self.objetos_al_cargar = [], None

    def page(self):
        return self._pagina

    def settings(self):
        return AjustesFalsos()

    def setUrl(self, url):
        canal = self._pagina.canal
        self.objetos_al_cargar = sorted(canal.registrados) if canal is not None else None
        self.urls.append(url)


class CanalAnotado(QWebChannel):
    """QWebChannel de verdad que anota qué hay registrado (registeredObjects() de PyQt
    se queda con los objetos y los borra al soltar el dict: no se usa)."""

    def __init__(self, *a):
        super().__init__(*a)
        self.registrados = {}

    def registerObject(self, nombre, obj):
        self.registrados[nombre] = obj
        super().registerObject(nombre, obj)

    def deregisterObject(self, obj):
        for n, o in list(self.registrados.items()):
            if o is obj:
                del self.registrados[n]
        super().deregisterObject(obj)


class ServidorFalso:
    def __init__(self, raiz=None):
        self.rutas_extra, self.detenido = {}, False

    def iniciar(self):
        return True

    def url(self, p):
        return f"http://127.0.0.1:5/{p}"

    def publicar(self, ruta, archivo):
        self.rutas_extra[ruta] = archivo

    def detener(self):
        self.detenido = True


class VozFalsa:
    def __init__(self, config=None, **kw):
        self._enabled, self.available = False, False
        self.al_hablar = self.on_error = None
        self.silenciada = False

    def cancelar(self):
        pass

    def invalidar_params(self):
        pass

    def speak(self, t):
        pass

    def silenciar(self, on):
        self.silenciada = bool(on)


class AIFalso:
    def __init__(self):
        self.providers, self.historiales, self.limpiado = {}, [], 0

    def clear_history(self):
        self.limpiado += 1

    def cargar_historial(self, h):
        self.historiales.append(list(h))

    def reload_provider(self):
        pass


class MemFalsa:
    def obtener_contexto_para_prompt(self):
        return ""


def _borrar_pendientes():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _esperar(qapp, cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    qapp.processEvents()
    return cond()


@pytest.fixture
def sistema():
    Sistema.reset()
    MascotaFalsa.creadas = []
    yield Sistema
    Sistema.reset()


@pytest.fixture
def entorno(qapp, monkeypatch, tmp_path, sistema):
    """Ventanas web y nativas de prueba con el montaje de verdad y piezas falsas."""
    import main
    import ui.montaje_escritorio as me
    import ui.web_bridge as wb
    import ui.web_shell as ws
    from nucleo.conversaciones import GestorConversaciones

    salidas = []
    app_falsa = types.SimpleNamespace(quit=lambda: salidas.append("quit"),
                                      setQuitOnLastWindowClosed=lambda v: None)
    monkeypatch.setattr(ws, "QApplication", types.SimpleNamespace(instance=lambda: app_falsa))
    monkeypatch.setattr(main, "QApplication", types.SimpleNamespace(quit=lambda: salidas.append("quit")))
    monkeypatch.setattr(ws, "_ServidorEstatico", ServidorFalso)
    monkeypatch.setattr(ws, "QWebEngineView", VistaFalsa)
    monkeypatch.setattr(ws, "QWebChannel", CanalAnotado)
    monkeypatch.setattr(ws, "asegurar_pagina", lambda web, origen, abrir_fuera=None: web.page())
    monkeypatch.setattr(ws, "publicar_vrm", lambda srv, cfg: {"url": "", "v": "", "archivo": "", "params": ""})
    monkeypatch.setattr(ws, "QSystemTrayIcon", TrayGlobal)            # la bandeja de respaldo
    monkeypatch.setattr(main, "QSystemTrayIcon", TrayGlobal)
    monkeypatch.setattr(wb, "VoiceEngine", VozFalsa)
    monkeypatch.setitem(sys.modules, "ui.companion", types.SimpleNamespace(CompanionFlotante=MascotaFalsa))
    import ui.avatar_overlay as ao
    monkeypatch.setattr(ao, "AvatarOverlay", SpritesFalsa)
    monkeypatch.setattr(main, "AvatarOverlay", SpritesFalsa)
    fab = fabricas()
    monkeypatch.setattr(ws.VentanaWeb, "FABRICAS_C4", fab)
    monkeypatch.setattr(main.LuneCDWindow, "FABRICAS_C4", fab)

    carpeta_chats = tmp_path / "chats"

    def gestor_chats(self):
        if self._chats is None:
            self._chats = GestorConversaciones(directorio=carpeta_chats)
        return self._chats
    monkeypatch.setattr(wb.LuneBridge, "_gestor_chats", gestor_chats)

    # Quién monta y desmonta, en qué orden.
    montar_real, desmontar_real = me.montar_escritorio, me.ServiciosCorte4.desmontar

    def montar(escritorio, *a, **kw):
        Sistema.eventos.append(("montar", escritorio))
        return montar_real(escritorio, *a, **kw)

    def desmontar(self):
        if not self.desmontado:
            Sistema.eventos.append(("desmontar", self.escritorio))
        return desmontar_real(self)
    monkeypatch.setattr(me, "montar_escritorio", montar)
    monkeypatch.setattr(me.ServiciosCorte4, "desmontar", desmontar)

    cfg = Config(str(tmp_path / "config.json"))
    creadas = []

    def web(diferir=False, config=None):
        from servicios.tools import ToolManager
        v = ws.VentanaWeb(config=config or cfg, ai_manager=AIFalso(), memoria=MemFalsa(),
                          tools=ToolManager(), diferir_servicios=diferir)
        creadas.append(v)
        return v

    def nativa(panel=None, config=None):
        v = _nativa(config or cfg, panel=panel)
        creadas.append(v)
        return v

    yield types.SimpleNamespace(web=web, nativa=nativa, cfg=cfg, salidas=salidas, chats=carpeta_chats,
                                ws=ws, main=main)
    for v in creadas:
        try:
            if isinstance(v, ws.VentanaWeb):
                v._liberar_todo()
            else:
                s = getattr(v, "_servicios_c4", None)
                if s is not None:
                    s.desmontar()
                v.escritorio.cerrar()
            v.deleteLater()
        except RuntimeError:
            pass
    _borrar_pendientes()


def _nativa(cfg, panel=None):
    """LuneCDWindow con sus métodos de verdad, sin construir la interfaz."""
    import main
    from ui.escritorio import ServiciosEscritorio
    W = main.LuneCDWindow
    yo = W.__new__(W)
    QMainWindow.__init__(yo)
    yo._relevada = yo._servicios_listos = yo._quit_real = False
    yo._servicios_c4 = None
    yo._ultima_orden_tg = ""
    yo.config = cfg
    yo.voice = VozFalsa()
    yo.escritorio = ServiciosEscritorio(cfg, voice=yo.voice, parent=yo)
    yo.tray = None
    yo._overlay = yo._tg_worker = yo.ai_worker = None
    yo._turno = {}
    yo.ai_manager = types.SimpleNamespace(providers={})
    yo.acciones = types.SimpleNamespace(pendientes=lambda: [], cerrar=lambda: None,
                                        nueva_conversacion=lambda: None)
    yo._grabadora = yo._transcriptor = yo._sondeo_prov = None
    yo._timers_plan = []
    yo.lune_face = types.SimpleNamespace(_player=None, setVisible=lambda v: None)
    yo.chats = types.SimpleNamespace(guardar=lambda: None, _sesion=None)
    yo.notas = types.SimpleNamespace(cerrar=lambda: None)
    yo.red = types.SimpleNamespace(detener=lambda: None)
    yo.memoria = types.SimpleNamespace(get_stats=lambda: {}, cerrar_sesion=lambda r: None)
    yo._hub_cliente = yo._hub_en_hilo = None
    yo.current_provider = "ollama"
    yo.provider_tabs = {}
    yo._cortar_respuesta = lambda: None
    if panel is not None:
        yo.settings_panel = panel
    return yo


class Evento:
    def __init__(self):
        self.hecho = []

    def accept(self):
        self.hecho.append("accept")

    def ignore(self):
        self.hecho.append("ignore")


# ═══ Web: arranque normal ═══════════════════════════════════════════════════════

def test_web_registra_el_puente_antes_de_cargar_y_monta_un_solo_icono(entorno, sistema):
    v = entorno.web()
    # La página ve window.lune Y window.luneEscritorio (y los de ocio de los cortes 5/6):
    # todos estaban antes de setUrl.
    assert v.web.objetos_al_cargar == ["alarmas", "escenario", "escritorio", "lune", "musica", "vida"]
    s = v._servicios_c4
    assert s is not None and v.bridge._servicios_c4 is s
    assert v._puente_esc.servicios is s and v._puente_esc.anfitrion is v._anfitrion
    assert v._anfitrion.navegar == v._puente_esc.pedir_vista          # Ajustes → navegar
    # UN icono: el de la bandeja única (sin la de respaldo); `tray` lo lee de ella.
    assert len(sistema.iconos) == 1 and v.tray is s.bandeja.icono_tray
    assert getattr(v, "_tray_respaldo", None) is None
    # Atajos registrados (los que tienen acción en la web) y sin choques.
    assert set(s.atajos.lista()) and len(sistema.combos) == 8 and sistema.choques == []
    # El puente ya contesta con los servicios montados.
    radial = json.loads(v._puente_esc.acciones_catalogo("radial"))
    assert {"ajustes", "voz"} <= {i["id"] for i in radial}
    # Los tray.showMessage de siempre llegan al icono de la bandeja única.
    v.tray.showMessage("Lune CD", "hola")
    assert sistema.iconos[0].mensajes[-1][:2] == ("Lune CD", "hola")


def test_web_mascota_sin_icono_propio(entorno, sistema):
    v = entorno.web()
    assert v.bridge.mascota_toggle() is True
    m = MascotaFalsa.creadas[-1]
    assert m.bandeja is False                                          # sin bandeja propia
    assert "quitar_bandeja" in m.diario                                # y la red de seguridad
    assert len(sistema.iconos) == 1
    # sprites: AvatarOverlay también sin bandeja
    entorno.cfg.set("avatar", "render", "sprites")
    v.bridge._mascota_recrear()
    assert isinstance(MascotaFalsa.creadas[-1], SpritesFalsa) and MascotaFalsa.creadas[-1].bandeja is False


def test_web_cerrar_oculta_segun_minimizar_a_bandeja(entorno, sistema):
    v = entorno.web()
    ev = Evento()
    v.show()
    v.closeEvent(ev)
    assert ev.hecho == ["ignore"] and not v.isVisible() and entorno.salidas == []
    assert sistema.iconos[0].mensajes[-1][0] == "Lune sigue aquí"
    # Sin minimizar a la bandeja: cerrar es salir (el icono estaba igual).
    entorno.cfg.config.setdefault("features", {})["minimizar_a_bandeja"] = False
    ev2 = Evento()
    v.closeEvent(ev2)
    assert ev2.hecho == ["accept"] and entorno.salidas == ["quit"]
    assert sistema.iconos == [] and sistema.combos == {}


def test_web_salir_desmonta_una_sola_vez(entorno, sistema):
    v = entorno.web()
    s = v._servicios_c4
    tema, juego, canal = s.tema, s.juego, v._canal
    v.salir_de_verdad()
    v.bridge.cerrar_escritorio()                                       # aboutToQuit
    assert entorno.salidas == ["quit"]
    assert tema.diario.count("detener") == 1 and juego.diario.count("detener") == 1
    assert [e for e, _ in sistema.eventos].count("desmontar") == 1
    assert sistema.iconos == [] and sistema.combos == {}
    assert "escritorio" not in canal.registrados                      # el puente, fuera del canal
    assert v._servicios_c4 is None and v.bridge._servicios_c4 is None
    v._liberar_todo()                                                  # otra vez: nada más
    assert [e for e, _ in sistema.eventos].count("desmontar") == 1


def test_web_respaldo_si_el_montaje_falla(entorno, sistema, monkeypatch):
    def revienta():
        raise RuntimeError("sin despachador")
    monkeypatch.setattr(entorno.ws.VentanaWeb, "FABRICAS_C4", dict(fabricas(), despachador=revienta))
    v = entorno.web()
    assert v._servicios_c4 is None
    assert len(sistema.iconos) == 1 and v.tray is v._tray_respaldo      # el icono de siempre
    # El puente sigue en la página (sin servicios: estado por defecto, sin lanzar).
    assert v.web.objetos_al_cargar == ["alarmas", "escenario", "escritorio", "lune", "musica", "vida"]
    assert json.loads(v._puente_esc.acciones_catalogo("radial")) == []
    assert json.loads(v._puente_esc.efectos()) == {"fondo": True, "barrido": True, "micro": True}


# ═══ Cambio de interfaz en caliente ═══════════════════════════════════════════

def test_web_diferida_no_toca_nada_hasta_que_la_vieja_suelta(entorno, sistema, qapp):
    vieja = entorno.web()
    combos_vieja = dict(sistema.combos)
    entorno.cfg.set("tema", "preset", "magenta_mate")
    nueva = entorno.web(diferir=True)
    # La nueva ya tiene su puente en la página, pero ni bandeja ni atajos: son de la vieja.
    assert nueva.web.objetos_al_cargar == ["alarmas", "escenario", "escritorio", "lune", "musica", "vida"]
    assert nueva._servicios_c4 is None and nueva._puente_esc.servicios is None
    assert len(sistema.iconos) == 1 and sistema.combos == combos_vieja and sistema.choques == []
    # Sin servicios, el tema de la página sale de la config (sin el cian de siempre).
    assert json.loads(nueva._puente_esc.tema_estado())["vars"]
    emitidos = []
    nueva._puente_esc.tema_cambio.connect(emitidos.append)
    # El relevo (GestorInterfaz._rematar): la vieja suelta, la nueva monta.
    vieja.cerrar_para_cambio()
    assert sistema.iconos == [] and sistema.combos == {}
    nueva.iniciar_servicios({})
    assert len(sistema.iconos) == 1 and nueva.tray is nueva._servicios_c4.bandeja.icono_tray
    assert len(sistema.combos) == 8 and sistema.choques == [] and sistema.max_iconos == 1
    assert nueva._puente_esc.servicios is nueva._servicios_c4
    assert emitidos and json.loads(emitidos[-1]) == {"--cyan-500": "#FF00AA"}   # la página se entera
    orden = [(e, d) for e, d in sistema.eventos]
    assert orden.index(("desmontar", vieja.bridge.escritorio)) < orden.index(("montar", nueva.bridge.escritorio))


def test_relevo_web_nativa_y_vuelta_con_gestor(entorno, sistema, qapp):
    from ui.cambio_interfaz import GestorInterfaz

    def fabrica(modo):
        return entorno.web(diferir=True) if modo == "web" else entorno.nativa()
    g = GestorInterfaz(fabrica, guardar_modo=lambda m: None, animar=lambda v, ms, fin: fin(),
                       fundido_ms=0, tope_carga_ms=10)
    web = entorno.web()
    g.adoptar(web)
    assert g.cambiar("nativo") is True and g.modo == "nativo"
    nat = g.ventana
    assert nat is not web and nat._servicios_c4 is not None and web._servicios_c4 is None
    assert len(sistema.iconos) == 1 and nat.tray is nat._servicios_c4.bandeja.icono_tray
    assert len(sistema.combos) == 7                                    # la nativa no tiene «llamada»
    # Y de vuelta a la web (espera a que la página «pinte»: aquí, el tope).
    assert g.cambiar("web") is True
    assert _esperar(qapp, lambda: g.modo == "web" and not g.cambiando)
    otra = g.ventana
    assert otra._servicios_c4 is not None and nat._servicios_c4 is None
    assert len(sistema.iconos) == 1 and len(sistema.combos) == 8
    # En ningún momento hubo dos iconos ni una combinación rechazada.
    assert sistema.max_iconos == 1 and sistema.choques == []
    eventos = [(e, d) for e, d in sistema.eventos]
    assert eventos.index(("desmontar", web.bridge.escritorio)) < eventos.index(("montar", nat.escritorio))
    assert eventos.index(("desmontar", nat.escritorio)) < eventos.index(("montar", otra.bridge.escritorio))


# ═══ Nativa ═══════════════════════════════════════════════════════════════════

class PanelFalso:
    def __init__(self):
        self.recibidos = []

    def usar_servicios(self, s):
        self.recibidos.append(s)


def test_nativa_monta_en_build_tray_un_icono_y_da_los_servicios_a_ajustes(entorno, sistema):
    panel = PanelFalso()
    yo = entorno.nativa(panel=panel)
    yo.iniciar_servicios({})
    s = yo._servicios_c4
    assert s is not None and panel.recibidos == [s]
    assert len(sistema.iconos) == 1 and yo.tray is s.bandeja.icono_tray
    assert getattr(yo, "_tray_respaldo", None) is None
    # Mostrar en la barra de tareas, radial, bandeja: el anfitrión es el nativo.
    assert s.anfitrion.modo == "br" and not s.despachador.tiene("llamada")
    # La mascota nace sin icono propio.
    yo._toggle_overlay()
    assert MascotaFalsa.creadas[-1].bandeja is False and len(sistema.iconos) == 1
    yo.iniciar_servicios({})                                           # una sola vez
    assert [e for e, _ in sistema.eventos].count("montar") == 1


def test_nativa_minimizar_y_salir_desmonta_una_vez(entorno, sistema):
    yo = entorno.nativa()
    yo.iniciar_servicios({})
    tema, juego = yo._servicios_c4.tema, yo._servicios_c4.juego
    ev = Evento()
    yo.show()
    yo.closeEvent(ev)                                                  # minimizar a la bandeja
    assert ev.hecho == ["ignore"] and entorno.salidas == [] and len(sistema.iconos) == 1
    assert sistema.iconos[0].mensajes
    yo._quit_real = True
    ev2 = Evento()
    yo.closeEvent(ev2)
    assert ev2.hecho == ["accept"] and entorno.salidas == ["quit"]
    assert tema.diario.count("detener") == 1 and juego.diario.count("detener") == 1
    assert sistema.iconos == [] and sistema.combos == {} and yo._servicios_c4 is None


def test_nativa_sin_minimizar_cerrar_sale(entorno, sistema):
    entorno.cfg.config.setdefault("features", {})["minimizar_a_bandeja"] = False
    yo = entorno.nativa()
    yo.iniciar_servicios({})
    assert len(sistema.iconos) == 1                                    # el icono está igual
    ev = Evento()
    yo.closeEvent(ev)
    assert ev.hecho == ["accept"] and entorno.salidas == ["quit"] and sistema.iconos == []


def test_nativa_respaldo_si_el_montaje_falla(entorno, sistema, monkeypatch):
    import main

    def revienta():
        raise RuntimeError("roto")
    monkeypatch.setattr(main.LuneCDWindow, "FABRICAS_C4", dict(fabricas(), despachador=revienta))
    yo = entorno.nativa()
    yo.iniciar_servicios({})
    assert yo._servicios_c4 is None and len(sistema.iconos) == 1 and yo.tray is yo._tray_respaldo


class _Parar(Exception):
    pass


def test_nativa_aplica_el_tema_antes_de_construir_la_interfaz(qapp, monkeypatch, tmp_path):
    """LuneCDWindow.__init__ de verdad (con dobles de lo pesado): cuando se construye
    la interfaz, COLORS ya tiene el color del tema."""
    import main
    from ui import theme
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("tema", "preset", "magenta_mate")
    visto = {}

    class Nada:
        def __init__(self, *a, **k):
            self.activo = False
            self.providers = {}
            self.available = False
            self._enabled = False
            self.resultado = types.SimpleNamespace(connect=lambda *a: None)

        def __getattr__(self, n):
            return lambda *a, **k: None

    for nombre in ("AIManager", "VoiceEngine", "MemoriaManager", "ToolManager", "AccionesQt",
                   "GestorConversaciones", "NotasService", "RedService", "BancoRespuestas"):
        monkeypatch.setattr(main, nombre, Nada)
    monkeypatch.setattr(main, "Config", lambda: cfg)
    monkeypatch.setattr(main, "datos", types.SimpleNamespace(
        hub_modo=lambda: "local", get_bot=lambda: {}, get_personaje=lambda n: {}))
    monkeypatch.setattr(main, "lune_face", types.SimpleNamespace(set_active_pack=lambda p: None,
                                                                 set_anim_video=lambda v: None))

    def init_ui(self):
        visto["accent"] = theme.COLORS["accent"]
        visto["meta"] = theme.PROVIDER_META["ollama"]["color"]
        raise _Parar()
    monkeypatch.setattr(main.LuneCDWindow, "_init_ui", init_ui)
    try:
        with pytest.raises(_Parar):
            main.LuneCDWindow()
        assert visto["accent"] != "#00E5FF" and visto["accent"] == visto["meta"]
    finally:
        theme.aplicar_tema({})                                          # COLORS de siempre
    assert theme.COLORS["accent"] == "#00E5FF"


# ═══ Web: aburrimiento, modo juego y comentar ═════════════════════════════════

def test_web_modo_juego_pausa_atajos_y_aburrimiento(entorno, sistema):
    v = entorno.web()
    b, s = v.bridge, v._servicios_c4
    assert b._aburrida_t.isActive()
    s.juego.e.update(activo=True, motivo="quns3")
    s.juego.cambio.emit(True, "quns3")
    assert not b._aburrida_t.isActive() and b._aburrimiento_pausado is True
    assert list(sistema.combos.values()) and len(sistema.combos) == 1   # solo mostrar_lune
    b._rearmar_aburrimiento()                                          # un mensaje tuyo no lo rearma
    assert not b._aburrida_t.isActive()
    s.juego.e.update(activo=False, motivo="")
    s.juego.cambio.emit(False, "")
    assert b._aburrida_t.isActive() and len(sistema.combos) == 8


def test_web_comentar_pantalla_avisa_en_modo_juego(entorno):
    v = entorno.web()
    b = v.bridge
    avisos = []
    b.aviso.connect(avisos.append)
    b.escritorio.estado.actualizar(juego=True)
    assert b.comentar_pantalla() is False
    assert avisos and "modo juego" in avisos[-1] and b._overlay is None   # ni saca la mascota
    b.escritorio.estado.actualizar(juego=False)
    assert b.comentar_pantalla() is True and "comentar" in MascotaFalsa.creadas[-1].diario


# ═══ La web restaura la última conversación al arrancar ═══════════════════════

def _guardar_conversacion(carpeta):
    from nucleo.conversaciones import GestorConversaciones
    g = GestorConversaciones(directorio=carpeta)
    g.nueva_sesion(proveedor="ollama", personaje="Lune")
    g.agregar("user", "¿qué tal?")
    g.agregar("assistant", "Bien, aquí sigo.")
    g.guardar()
    return g.sesion_id


def test_web_restaura_la_ultima_conversacion_al_arrancar(entorno):
    sid = _guardar_conversacion(entorno.chats)
    v = entorno.web()
    estado = json.loads(v.bridge.estado_inicial())
    assert [m["text"] for m in estado["mensajes"]] == ["¿qué tal?", "Bien, aquí sigo."]
    assert v.bridge.chats.sesion_id == sid                             # los turnos nuevos, ahí
    assert v.bridge.ai.historiales and len(v.bridge.ai.historiales[-1]) == 2


def test_web_no_restaura_en_un_cambio_de_modo_ni_si_esta_apagado(entorno):
    _guardar_conversacion(entorno.chats)
    diferida = entorno.web(diferir=True)                               # el relevo trae la suya
    assert json.loads(diferida.bridge.estado_inicial())["mensajes"] == []
    diferida.cerrar_para_cambio()
    entorno.cfg.set("chat", "restaurar_ultima", False)
    v = entorno.web()
    assert json.loads(v.bridge.estado_inicial())["mensajes"] == []


# ═══ Limpiar chat con una orden de Telegram esperando permiso ════════════════

def test_web_limpiar_chat_avisa_a_telegram(entorno):
    from servicios.telegram_worker import AVISO_TG_DETENIDA
    v = entorno.web()
    b = v.bridge
    respuestas, nuevas = [], []
    b._tg_worker = types.SimpleNamespace(responder_orden=lambda oid, t: respuestas.append((oid, t)) or True,
                                         isRunning=lambda: True)
    b.acciones = types.SimpleNamespace(pendientes=lambda: [{"id": "p1", "remoto": True}],
                                       nueva_conversacion=lambda: nuevas.append(1), cerrar=lambda: None)
    b._ultima_orden_tg = "o7"
    b.limpiar_chat()
    assert respuestas == [("o7", AVISO_TG_DETENIDA)] and nuevas == [1]
    # Sin nada pendiente, no se dice nada.
    b.acciones.pendientes = lambda: []
    b.limpiar_chat()
    assert len(respuestas) == 1
    b._tg_worker = None


def test_nativa_conversacion_nueva_avisa_a_telegram(qapp, monkeypatch):
    import main
    from servicios.telegram_worker import AVISO_TG_DETENIDA
    respuestas, orden = [], []
    yo = types.SimpleNamespace(
        _turno={}, ai_worker=None, _ultima_orden_tg="o9",
        _tg_worker=types.SimpleNamespace(responder_orden=lambda oid, t: respuestas.append((oid, t)) or True),
        acciones=types.SimpleNamespace(pendientes=lambda: [{"remoto": True}],
                                       nueva_conversacion=lambda: orden.append("nueva")),
        chats=types.SimpleNamespace(nueva_sesion=lambda **k: None), current_provider="ollama",
        ai_manager=types.SimpleNamespace(clear_history=lambda: None),
        messages_layout=types.SimpleNamespace(count=lambda: 1),
        _add_welcome=lambda: None, lune_face=types.SimpleNamespace(set_state=lambda s: None),
        stack=types.SimpleNamespace(setCurrentIndex=lambda i: None),
        _cortar_respuesta=lambda: orden.append("cortar"))
    for n in ("_nueva_conversacion", "_avisar_ordenes_pendientes", "_responder_telegram", "_worker_vivo"):
        setattr(yo, n, types.MethodType(getattr(main.LuneCDWindow, n), yo))
    monkeypatch.setattr(main.datos, "get_bot", lambda: {"personaje_default": "Lune"})
    yo._nueva_conversacion()
    assert respuestas == [("o9", AVISO_TG_DETENIDA)]
    assert orden == ["cortar", "nueva"]


# ═══ Ajustes nativos: cada apartado del panel de escritorio se aplica ════════

class Registro:
    def __init__(self):
        self.llamadas = []

    def __getattr__(self, nombre):
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        return lambda *a: self.llamadas.append((nombre,) + a)


def _servicios_falsos():
    atajos = Registro()
    atajos.cambio = types.SimpleNamespace(connect=lambda f: None, disconnect=lambda f: None)
    atajos.estado = lambda: []
    mascota = Registro()
    return types.SimpleNamespace(tema=Registro(), juego=Registro(), atajos=atajos, anfitrion=Registro(),
                                 escritorio=types.SimpleNamespace(mascota=mascota), desmontar=lambda: None)


def test_aplicar_seccion_escritorio_solo_lo_que_cambio():
    from ui.settings_panel import aplicar_seccion_escritorio as aplicar
    cfg = Config.__new__(Config)
    datos_cfg = copy.deepcopy(Config.DEFAULT_CONFIG)
    cfg.get = lambda s, k, d=None: datos_cfg.get(s, {}).get(k, d)
    datos_cfg["avatar"]["fps_max"] = 30
    s = _servicios_falsos()
    assert aplicar("rendimiento", None, cfg) == []
    assert aplicar("rendimiento", s, cfg, {("avatar", "fps_max")}) == ["set_fps_max"]
    assert s.escritorio.mascota.llamadas == [("set_fps_max", 30)] and s.anfitrion.llamadas == []
    assert aplicar("rendimiento", s, cfg, {("interfaz", "en_barra_tareas"), ("sistema", "recorte_ram_auto")}) \
        == ["recargar_config", "set_en_barra"]
    assert s.anfitrion.llamadas == [("set_en_barra", True)]
    assert aplicar("tema", s, cfg) == ["recargar"] and aplicar("juego", s, cfg) == ["recargar_config"]
    assert aplicar("atajos", s, cfg) == ["recargar"] and aplicar("radial", s, cfg) == []


@pytest.fixture
def ajustes(qapp, monkeypatch, tmp_path):
    from servicios import autoinicio, voces
    from ui import settings_panel as SP
    datos_panel = {"apis": {"openrouter_key": ""},
                   "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": ""},
                   "bot": {"personaje_default": "Lune"},
                   "personajes": [{"nombre": "Lune", "systemPrompt": "x", "fraseInicial": "hola"}]}
    monkeypatch.setattr(SP.datos, "cargar", lambda: copy.deepcopy(datos_panel))
    monkeypatch.setattr(SP.datos, "guardar", lambda d: None)
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(autoinicio, "establecer", lambda on: None)
    monkeypatch.setattr(voces, "_voz_personaje", lambda p: SP.voz_de(p))
    cfg = Config(str(tmp_path / "config.json"))
    creados = []

    def crear(servicios):
        p = SP.SettingsPanel(cfg, voice=None, servicios=servicios)
        creados.append(p)
        return p
    yield types.SimpleNamespace(crear=crear, cfg=cfg)
    for p in creados:
        p.vrm_panel._timer.stop()
        p.escritorio_panel._timer.stop()
        p.deleteLater()


def test_settings_panel_propaga_cambiado_a_los_servicios(ajustes):
    caja = {"s": None}
    p = ajustes.crear(lambda: caja["s"])                               # como main: aún sin montar
    panel = p.escritorio_panel
    assert panel.atajos is None
    panel._poner("tema", "tema", "preset", "violeta")
    assert panel.guardar_ya() == ["tema"]                              # sin servicios: no pasa nada
    s = _servicios_falsos()
    caja["s"] = s
    p.usar_servicios(s)
    assert panel.atajos is s.atajos
    vistos = []
    p.escritorio_cambiado.connect(vistos.append)
    panel._poner("tema", "tema", "preset", "ambar")
    panel._poner("rendimiento", "avatar", "fps_max", 30)
    assert panel.guardar_ya() == ["tema", "rendimiento"]
    assert s.tema.llamadas == [("recargar",)]
    assert s.escritorio.mascota.llamadas == [("set_fps_max", 30)]
    assert s.anfitrion.llamadas == []                                  # en_barra no cambió: sin parpadeo
    assert vistos == ["tema", "rendimiento"]
    assert ajustes.cfg.get("tema", "preset") == "ambar"
    # «Guardar configuración» escribe lo pendiente del panel de escritorio y lo aplica.
    panel._poner("juego", "juego", "fps", 10)
    panel._poner("atajos", "atajos", "pausar_en_juegos", False)
    p._save()
    assert ("recargar_config",) in s.juego.llamadas and ("recargar",) in s.atajos.llamadas
    assert Config(str(ajustes.cfg.config_path)).get("juego", "fps") == 10


# ═══ Patata: comandos nuevos, sin Qt ══════════════════════════════════════════

class ApiFalsa:
    def __init__(self):
        self.titulos = []

    def habilitar_vt(self):
        return True

    def es_consola_entrada(self):
        return False

    def titulo(self, texto):
        self.titulos.append(texto)
        return True

    def parpadear(self, veces=3, hasta_foco=True):
        return True

    def leer_tecla(self):
        return ""


class EntradaBloqueante:
    def __init__(self):
        self.q = queue.Queue()

    def put(self, s):
        self.q.put(s)

    def readline(self):
        s = self.q.get()
        return "" if s is None else s


class DetectorFalso:
    INTERVALO_S = 0.02

    def __init__(self):
        self.forzado = None
        self.lecturas = []
        self._activo = False

    def forzar(self, on):
        self.forzado = on

    def detectando(self):
        return True

    def evaluar(self):
        antes = self._activo
        if self.forzado is not None:
            self._activo = self.forzado
        elif self.lecturas:
            self._activo = self.lecturas.pop(0)
        motivo = "forzado" if self.forzado else ("quns3" if self._activo else "")
        return (self._activo != antes, self._activo, motivo)


class AutoFalso:
    def __init__(self):
        self.on = False
        self.modos = []

    def activo(self):
        return self.on

    def establecer(self, q, modo=None):             # como servicios/autoinicio.establecer
        self.on = bool(q)
        self.modos.append(modo)
        return self.on


@pytest.fixture
def patata_(tmp_path, monkeypatch):
    import patata
    from nucleo import datos
    from nucleo.consola import ConsolaAsincrona
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    creadas = []

    def crear(**kw):
        api, entrada, out = ApiFalsa(), EntradaBloqueante(), io.StringIO()
        consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=api, ansi=False)
        cfg = Config(str(tmp_path / "config.json"))
        prioridades, recortes = [], []
        kw.setdefault("juego", DetectorFalso())
        kw.setdefault("prioridad", lambda baja: prioridades.append(baja))
        kw.setdefault("recortar", lambda: recortes.append(1) or (250.0, 180.0))
        kw.setdefault("autoinicio", AutoFalso())
        p = patata.Patata(color=kw.pop("color", False), consola=consola, config=cfg,
                          ai=types.SimpleNamespace(providers={}), memoria=MemFalsa(), voice=None,
                          tools=None, **kw)
        p.api, p.entrada, p.out, p.cfg = api, entrada, out, cfg
        p.prioridades, p.recortes = prioridades, recortes
        creadas.append(p)
        return p
    yield crear
    for p in creadas:
        p.entrada.put(None)
        p.cerrar()
    datos.invalidar()


def _cmd(p, linea):
    antes = len(p.out.getvalue())
    salir = p.comando(linea)
    return p.out.getvalue()[antes:], salir


def test_patata_tema_y_caritas(patata_):
    from nucleo import tema
    p = patata_(color=True)
    base = p.c["cyan"]
    texto, _ = _cmd(p, "/tema")
    assert "*cian" in texto and "magenta_mate" in texto
    texto, _ = _cmd(p, "/tema Magenta Mate")
    assert "Tema Magenta Mate" in texto and p.cfg.get("patata", "tema") == "magenta_mate"
    assert p.c["cyan"] == tema.ansi(tema.paleta("magenta_mate")["cyan-500"]) != base
    _cmd(p, "/tema rojo")                                              # inicio único → rojo_neon
    assert p.cfg.get("patata", "tema") == "rojo_neon"
    assert "No conozco" in _cmd(p, "/tema marte")[0]
    _cmd(p, "/tema cian")
    assert p.c["cyan"] == base                                         # el de siempre
    # Caritas
    assert "clasico" in _cmd(p, "/caritas")[0]
    _cmd(p, "/caritas kaomoji")
    assert p.cfg.get("patata", "caritas") == "kaomoji"
    assert p._cara("happy") == "(^▽^)" and "(^▽^)" in p._lune(":D", "x")
    assert "Elige" in _cmd(p, "/caritas raras")[0]
    _cmd(p, "/caritas clasico")
    assert p._lune(":D", "x").count(":D") == 1


def test_patata_ram_y_juego(patata_):
    p = patata_()
    texto, _ = _cmd(p, "/ram")
    assert "250 MB → 180 MB" in texto and p.recortes == [1]
    assert "automático" in _cmd(p, "/juego")[0]
    texto, _ = _cmd(p, "/juego on")
    assert "activo" in texto and "forzado" in texto and p.prioridades == [True]
    assert p.api.titulos[-1].endswith("modo juego")
    _cmd(p, "/juego off")
    assert p.prioridades == [True, False] and not p.api.titulos[-1].endswith("modo juego")
    _cmd(p, "/juego auto")
    assert p._det_juego.forzado is None
    assert "Uso:" in _cmd(p, "/juego quizás")[0]


def test_patata_hilo_del_modo_juego(patata_):
    p = patata_()
    p._det_juego.lecturas = [True] * 5 + [False] * 200
    assert p.iniciar_juego() is True and p.iniciar_juego() is False
    fin = time.monotonic() + 3
    while time.monotonic() < fin and p.prioridades != [True, False]:
        time.sleep(0.01)
    assert p.prioridades == [True, False]                              # entró y salió solo
    p._det_juego.lecturas = [True] * 1000
    fin = time.monotonic() + 3
    while time.monotonic() < fin and not p._juego_activo:
        time.sleep(0.01)
    p.detener_juego()                                                  # al salir: prioridad de antes
    assert p.prioridades[-1] is False and p._hilo_juego is None and not p._juego_activo


def test_patata_menu(patata_):
    p = patata_()
    texto, salir = _cmd(p, "/menu")
    lineas = [x.strip() for x in texto.splitlines()]
    assert salir is False and "bandeja" in texto
    etiquetas = [x.split(". ", 1)[1] for x in lineas if x[:1].isdigit()]
    assert etiquetas[0].startswith("Voz") and etiquetas[-1] == "Salir"
    assert any(e.startswith("Modo juego") for e in etiquetas) and "Liberar memoria" in etiquetas
    n = {e.split("  ")[0]: i + 1 for i, e in enumerate(etiquetas)}
    texto, _ = _cmd(p, f"/menu {n['Voz']}")
    assert "No hay motor de voz" in texto
    _cmd(p, f"/menu {n['Liberar memoria']}")
    assert p.recortes == [1]
    _cmd(p, f"/menu {n['Tema']} violeta")
    assert p.cfg.get("patata", "tema") == "violeta"
    _cmd(p, f"/menu {n['Tema']}")                                     # sin opción: el siguiente
    assert p.cfg.get("patata", "tema") == "rojo_neon"
    _cmd(p, f"/menu {n['Arrancar con Windows']}")
    assert p._autoinicio.on is True and p.cfg.get("sistema", "autoinicio") is True
    assert p._autoinicio.modos[-1] == "patata"              # cortes 7/8: la variante de patata
    _cmd(p, "/menu modo_juego_forzar")                                 # también por id
    assert p._juego_activo is True and p.prioridades == [True]
    assert "No hay la opción" in _cmd(p, "/menu 99")[0]
    texto, salir = _cmd(p, f"/menu {len(etiquetas)}")                  # Salir
    assert salir is True


def test_patata_ayuda_cuenta_lo_nuevo(patata_):
    p = patata_()
    texto, _ = _cmd(p, "/ayuda")
    for c in ("/menu", "/tema", "/caritas", "/juego", "/ram"):
        assert c in texto, c
    assert "bandeja" in texto and "atajos" in texto


def test_patata_comandos_nuevos_sin_qt(tmp_path):
    guion = tmp_path / "guion.py"
    guion.write_text(f"""
import io, shutil, sys, types
sys.path.insert(0, {str(RAIZ)!r})
from pathlib import Path
from nucleo import datos
ruta = Path({str(tmp_path)!r}) / "datos.json"
shutil.copyfile(Path({str(RAIZ)!r}) / "datos.example.json", ruta)
datos._PATH = ruta
datos.invalidar()
import patata
from nucleo.config import Config
from nucleo.consola import ConsolaAsincrona

class Api:
    def habilitar_vt(self): return True
    def es_consola_entrada(self): return False
    def titulo(self, t): return True
    def parpadear(self, *a, **k): return True
    def leer_tecla(self): return ""

class Det:
    INTERVALO_S = 0.02
    forzado = None
    def forzar(self, on): self.forzado = on
    def detectando(self): return True
    def evaluar(self): return (True, bool(self.forzado), "forzado" if self.forzado else "")

out = io.StringIO()
consola = ConsolaAsincrona("> ", stdout=out, stdin=io.StringIO(""), api=Api(), ansi=False)
p = patata.Patata(color=False, consola=consola, config=Config(str(Path({str(tmp_path)!r}) / "config.json")),
                  ai=types.SimpleNamespace(providers={{}}), memoria=types.SimpleNamespace(), voice=None,
                  tools=None, juego=Det(), prioridad=lambda b: None, recortar=lambda: (10.0, 5.0))
for linea in ("/tema violeta", "/caritas kaomoji", "/menu", "/menu 1", "/juego on", "/juego auto", "/ram",
              "/ayuda"):
    p.comando(linea)
p.cerrar()
print("QT" if any(m.startswith("PyQt") for m in sys.modules) else "SIN_QT")
""", encoding="utf-8")
    r = subprocess.run([sys.executable, str(guion)], cwd=str(RAIZ), capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("SIN_QT"), r.stdout[-500:]
