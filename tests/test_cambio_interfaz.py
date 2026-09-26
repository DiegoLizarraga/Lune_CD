"""
Cambio de modo de interfaz en caliente (ui/cambio_interfaz.py, ui/web_shell.py y
/interfaz de patata.py).

GestorInterfaz con ventanas falsas: la nueva se crea y se enseña ANTES de cerrar
la vieja, hereda su geometría, si la fábrica falla se queda la vieja, una segunda
petición durante un cambio se ignora, el servidor de instancia única trae al
frente la nueva y patata lanza la terminal y cierra la app. VentanaWeb suelta
bandeja, mascota, bot, IA en curso, aprobaciones y servicios de escritorio sin
llamar a QApplication.quit. Patata /interfaz con el lanzador inyectado: nunca se
abre nada de verdad.
"""
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (fixture qapp).
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from PyQt6.QtCore import QObject, QRect, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow

import ui.cambio_interfaz as ci
from ui.cambio_interfaz import GestorInterfaz

RAIZ = Path(__file__).resolve().parent.parent


def esperar(app, cond, t=2.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    app.processEvents()
    return cond()


# ── Ventanas falsas ───────────────────────────────────────────────────────────────
class VentanaFalsa:
    """Cumple el contrato de GestorInterfaz y apunta en `log` lo que le pasa."""

    def __init__(self, modo, log, *, en_marcha=None, lista=True):
        self.MODO_INTERFAZ = modo
        self.log = log
        self.en_marcha = dict(en_marcha or {})
        self.lista = lista                 # False: al_estar_lista guarda el callback y no llama
        self.cb_lista = None
        self.visible = False
        self.enabled = True
        self.estado_recibido = None
        self.servicios = None
        self.al_frente = 0
        self.geom = None
        self.opacidad = 1.0
        self.avisos = []

    def __repr__(self):
        return f"<{self.MODO_INTERFAZ}#{id(self) % 1000}>"

    # contrato
    def estado_para_cambio(self):
        self.log.append(("estado", self))
        return {"proveedor": "compat", "voz": True, "sesion": {"id": "s1", "mensajes": [{"rol": "user"}]}}

    def aplicar_estado(self, estado):
        self.log.append(("aplicar", self))
        self.estado_recibido = dict(estado)

    def al_estar_lista(self, cb, tope_ms):
        self.log.append(("esperar", self))
        if self.lista:
            cb()
        else:
            self.cb_lista = cb

    def cerrar_para_cambio(self):
        self.log.append(("cerrar", self))
        self.visible = False
        return dict(self.en_marcha)

    def iniciar_servicios(self, estado):
        self.log.append(("servicios", self))
        self.servicios = dict(estado)

    def salir_de_verdad(self):
        self.log.append(("salir_de_verdad", self))

    def aviso_cambio(self, texto):
        self.avisos.append(texto)

    # lo de Qt que usa el gestor
    def setGeometry(self, *r):
        self.geom = tuple(r[0].getRect()) if len(r) == 1 else tuple(r)

    def setWindowOpacity(self, v):
        self.opacidad = v

    def show(self):
        self.log.append(("mostrar", self))
        self.visible = True

    def raise_(self):
        self.al_frente += 1

    def activateWindow(self):
        pass

    def setEnabled(self, v):
        self.enabled = bool(v)

    def deleteLater(self):
        self.log.append(("borrar", self))


def _gestor(fabrica, log, **kw):
    modos = []
    kw.setdefault("guardar_modo", modos.append)
    kw.setdefault("avisar", lambda v, t: log.append(("avisar", t)))
    kw.setdefault("fundido_ms", 0)
    kw.setdefault("salir", lambda: log.append(("salir",)))
    g = GestorInterfaz(fabrica, **kw)
    g.modos_guardados = modos
    return g


def _fabrica(log, creadas, **kw_ventana):
    def fabrica(modo):
        v = VentanaFalsa(modo, log, **kw_ventana)
        log.append(("crear", modo))
        creadas.append(v)
        return v
    return fabrica


# ── GestorInterfaz ────────────────────────────────────────────────────────────────
def test_la_nueva_se_crea_y_se_ensena_antes_de_cerrar_la_vieja(qapp):
    log, creadas = [], []
    vieja = VentanaFalsa("web", log, en_marcha={"mascota_fuera": True, "telegram": True})
    g = _gestor(_fabrica(log, creadas), log)
    g.adoptar(vieja)
    assert g.modo == "web"
    hechos = []
    g.cambio_hecho.connect(hechos.append)
    assert g.cambiar("nativo") is True
    nueva = creadas[0]
    pasos = [(p, v) for p, *v in log if p in ("crear", "aplicar", "mostrar", "cerrar", "borrar", "servicios")]
    assert [p for p, _ in pasos] == ["crear", "aplicar", "mostrar", "cerrar", "borrar", "servicios"]
    assert ("mostrar", nueva) in log and ("cerrar", vieja) in log
    assert log.index(("mostrar", nueva)) < log.index(("cerrar", vieja)) < log.index(("servicios", nueva))
    # La nueva hereda el estado y relanza lo que estaba en marcha en la vieja.
    assert nueva.estado_recibido["proveedor"] == "compat" and nueva.estado_recibido["voz"] is True
    assert nueva.servicios["mascota_fuera"] is True and nueva.servicios["telegram"] is True
    assert g.ventana is nueva and g.modo == "nativo" and not g.cambiando
    assert g.modos_guardados == ["nativo"] and hechos == ["nativo"]
    assert nueva.visible and not vieja.visible


def test_el_modo_actual_no_se_vuelve_a_cambiar(qapp):
    log, creadas = [], []
    g = _gestor(_fabrica(log, creadas), log)
    g.adoptar(VentanaFalsa("web", log))
    assert g.cambiar("web") is False and g.cambiar("completa") is False
    assert g.pedir("web") is False and g.cambiar("inventado") is False
    assert creadas == [] and g.modos_guardados == []


def test_si_la_fabrica_falla_se_queda_la_vieja_y_se_avisa(qapp):
    log = []

    def fabrica(modo):
        raise RuntimeError("sin QtWebEngine")

    vieja = VentanaFalsa("nativo", log)
    g = _gestor(fabrica, log)
    g.adoptar(vieja)
    fallos = []
    g.cambio_fallido.connect(lambda m, t: fallos.append((m, t)))
    assert g.cambiar("web") is False
    assert g.ventana is vieja and g.modo == "nativo" and not g.cambiando
    assert vieja.enabled and ("cerrar", vieja) not in log
    avisos = [t for p, *t in log if p == "avisar"]
    assert avisos and "sin QtWebEngine" in avisos[0][0]
    # Se guardó el modo nuevo para construirla y, al fallar, vuelve el de antes.
    assert g.modos_guardados == ["web", "nativo"]
    assert fallos and fallos[0][0] == "web"
    # Y se puede volver a intentar.
    assert g.cambiar("web") is False and not g.cambiando


def test_si_falla_al_preparar_la_nueva_se_descarta(qapp):
    log, creadas = [], []

    class Rota(VentanaFalsa):
        def aplicar_estado(self, estado):
            raise ValueError("estado raro")

    def fabrica(modo):
        v = Rota(modo, log)
        creadas.append(v)
        return v

    vieja = VentanaFalsa("web", log)
    g = _gestor(fabrica, log)
    g.adoptar(vieja)
    assert g.cambiar("nativo") is False
    assert g.ventana is vieja and ("cerrar", creadas[0]) in log and ("cerrar", vieja) not in log


def test_una_segunda_peticion_durante_el_cambio_se_ignora(qapp):
    log, creadas = [], []
    vieja = VentanaFalsa("web", log)
    g = _gestor(_fabrica(log, creadas, lista=False), log)
    g.adoptar(vieja)
    assert g.cambiar("nativo") is True
    assert g.cambiando and not vieja.enabled            # la vieja no admite nada mientras carga
    assert g.cambiar("patata") is False and g.pedir("nativo") is False and g.pedir("web") is False
    assert len(creadas) == 1 and ("cerrar", vieja) not in log
    creadas[0].cb_lista()                                 # la página ya pintó
    creadas[0].cb_lista()                                 # un segundo aviso no repite el relevo
    assert log.count(("cerrar", vieja)) == 1 and g.ventana is creadas[0] and not g.cambiando


def test_pedir_difiere_el_cambio_y_no_admite_dos(qapp):
    log, creadas = [], []
    g = _gestor(_fabrica(log, creadas), log)
    g.adoptar(VentanaFalsa("web", log))
    assert g.pedir("nativo") is True
    assert g.pedir("nativo") is False                     # ya hay uno pendiente
    assert creadas == []                                  # aún no: la página que pidió termina antes
    assert esperar(qapp, lambda: g.modo == "nativo")
    assert len(creadas) == 1


def test_la_senal_de_la_ventana_pide_el_cambio(qapp):
    class Vqt(QObject):
        cambio_interfaz_pedido = pyqtSignal(str)
        MODO_INTERFAZ = "web"

    log, creadas = [], []
    g = _gestor(_fabrica(log, creadas), log)
    v = Vqt()
    g.adoptar(v)
    v.cambio_interfaz_pedido.emit("nativo")
    assert esperar(qapp, lambda: g.modo == "nativo") and len(creadas) == 1


def test_si_la_nueva_nunca_avisa_el_gestor_no_se_queda_colgado(qapp, monkeypatch):
    monkeypatch.setattr(ci, "_MARGEN_GUARDA_MS", 20)
    log, creadas = [], []
    vieja = VentanaFalsa("web", log)
    g = _gestor(_fabrica(log, creadas, lista=False), log, tope_carga_ms=10)
    g.adoptar(vieja)
    assert g.cambiar("nativo") is True
    assert esperar(qapp, lambda: not g.cambiando)
    assert g.ventana is creadas[0] and ("cerrar", vieja) in log


def test_el_servidor_de_instancia_trae_al_frente_la_nueva(qapp):
    class ServidorFalso(QObject):
        newConnection = pyqtSignal()

        def hasPendingConnections(self):
            return False

    log, creadas = [], []
    vieja = VentanaFalsa("web", log)
    g = _gestor(_fabrica(log, creadas), log)
    g.adoptar(vieja)
    srv = ServidorFalso()
    g.conectar_servidor(srv)
    g.conectar_servidor(srv)                              # conectar dos veces no duplica
    srv.newConnection.emit()
    assert vieja.al_frente == 1
    g.cambiar("nativo")
    nueva = creadas[0]
    antes_v, antes_n = vieja.al_frente, nueva.al_frente
    srv.newConnection.emit()
    assert nueva.al_frente == antes_n + 1 and vieja.al_frente == antes_v


def test_geometria_y_fundido_con_ventanas_qt(qapp):
    class VQt(QMainWindow):
        def __init__(self, modo, log):
            super().__init__()
            self.MODO_INTERFAZ, self.log = modo, log

        def cerrar_para_cambio(self):
            self.log.append(("cerrar", self))
            self.hide()
            return {}

        def iniciar_servicios(self, estado):
            self.log.append(("servicios", self))

    log, creadas = [], []

    def fabrica(modo):
        v = VQt(modo, log)
        creadas.append(v)
        return v

    vieja = VQt("web", log)
    vieja.setGeometry(QRect(140, 110, 720, 520))
    vieja.show()
    qapp.processEvents()
    g = GestorInterfaz(fabrica, guardar_modo=lambda m: None, avisar=lambda v, t: None,
                       fundido_ms=40)
    g.adoptar(vieja)
    assert g.cambiar("nativo") is True
    nueva = creadas[0]
    assert nueva.isVisible() and nueva.windowOpacity() < 1.0     # empezó transparente…
    assert ("cerrar", vieja) not in log                          # …y la vieja sigue debajo
    assert esperar(qapp, lambda: not g.cambiando)
    assert nueva.windowOpacity() == 1.0 and ("cerrar", vieja) in log
    assert nueva.geometry().getRect() == (140, 110, 720, 520)
    # Maximizada: la nueva sale maximizada y con la misma geometría normal.
    nueva.showMaximized()
    qapp.processEvents()
    g.fundido_ms = 0
    assert g.cambiar("web") is True
    otra = creadas[1]
    qapp.processEvents()
    assert otra.isMaximized() and otra.normalGeometry().getRect() == (140, 110, 720, 520)
    for v in creadas + [vieja]:
        try:
            v.close()
        except RuntimeError:                                  # ya la borró el gestor
            pass


def test_patata_lanza_la_terminal_y_cierra_la_app(qapp):
    log = []
    vieja = VentanaFalsa("web", log)
    lanzadas = []
    g = _gestor(lambda m: pytest.fail("patata no usa la fábrica"), log,
                lanzar_patata=lambda: lanzadas.append(1) or True)
    g.adoptar(vieja)
    assert g.cambiar("patata") is True
    assert lanzadas == [1] and ("salir_de_verdad", vieja) in log and ("salir",) in log
    assert log.index(("salir_de_verdad", vieja)) < log.index(("salir",))
    assert g.modos_guardados == ["patata"] and g.ventana is None and g.modo == "patata"


def test_patata_sin_terminal_se_queda_la_ventana(qapp):
    log = []
    vieja = VentanaFalsa("nativo", log)
    g = _gestor(lambda m: None, log, lanzar_patata=lambda: False)
    g.adoptar(vieja)
    assert g.cambiar("terminal") is False
    assert ("salir",) not in log and ("salir_de_verdad", vieja) not in log
    assert g.ventana is vieja and g.modo == "nativo" and not g.cambiando
    assert any(p == "avisar" for p, *_ in log)


# ── Ayudantes para soltar recursos ────────────────────────────────────────────────
class SenalFalsa:
    def __init__(self):
        self.slots = []
        self.desconectada = False

    def connect(self, fn):
        self.slots.append(fn)

    def disconnect(self, *a):
        self.desconectada = True
        self.slots = []

    def emit(self, *a):
        for fn in list(self.slots):
            fn(*a)


class HiloFalso:
    def __init__(self, corriendo=True):
        self.corriendo = corriendo
        self.llamadas = []
        for s in ("token_received", "response_ready", "error_occurred", "finished",
                  "log_signal", "stopped", "listo", "error"):
            setattr(self, s, SenalFalsa())

    def isRunning(self):
        return self.corriendo

    def stop(self):
        self.llamadas.append("stop")

    def requestInterruption(self):
        self.llamadas.append("interrumpir")

    def wait(self, ms):
        self.llamadas.append(("wait", ms))

    def terminar(self):
        self.corriendo = False
        self.finished.emit()


def test_detener_hilo_ia_corta_desconecta_y_retiene():
    w = HiloFalso()
    prov = types.SimpleNamespace(cancel_flag=False)
    assert ci.detener_hilo_ia(w, {"ollama": prov}) is True
    assert prov.cancel_flag is True
    assert w.response_ready.desconectada and w.token_received.desconectada
    assert w in ci._retenidos                            # no se destruye corriendo
    w.terminar()
    assert w not in ci._retenidos
    assert ci.detener_hilo_ia(None) is False


def test_detener_bot_cerrar_mascota_quitar_bandeja():
    tg = HiloFalso()
    assert ci.detener_bot(tg, espera_ms=10) is True
    assert tg.llamadas[:3] == ["stop", "interrumpir", ("wait", 10)] and tg.stopped.desconectada
    tg.terminar()
    parado = HiloFalso(corriendo=False)
    assert ci.detener_bot(parado) is False and "stop" not in parado.llamadas

    hechos = []
    ov = types.SimpleNamespace(cerrado=False, isVisible=lambda: True, visibilidad=SenalFalsa(),
                               close=lambda: hechos.append("close"),
                               deleteLater=lambda: hechos.append("borrar"))
    assert ci.cerrar_mascota(ov) is True and hechos == ["close", "borrar"]
    oculta = types.SimpleNamespace(cerrado=False, isVisible=lambda: False,
                                   close=lambda: None, deleteLater=lambda: None)
    assert ci.cerrar_mascota(oculta) is False and ci.cerrar_mascota(None) is False

    menu = types.SimpleNamespace(deleteLater=lambda: hechos.append("menu"))
    tray = types.SimpleNamespace(contextMenu=lambda: menu, hide=lambda: hechos.append("hide"),
                                 deleteLater=lambda: hechos.append("tray"))
    ci.quitar_bandeja(tray)
    assert hechos[-3:] == ["hide", "tray", "menu"]


def test_la_conversacion_pasa_con_su_marca_de_terceros(tmp_path, monkeypatch):
    """La ventana nueva sigue la MISMA conversación (misma id) y el historial del
    modelo sigue marcado: las acciones siguen pidiendo permiso."""
    from nucleo import datos
    from nucleo.conversaciones import GestorConversaciones
    from servicios import ai_manager as am
    m = {"max_historial": 20}
    monkeypatch.setattr(datos, "get_modelos", lambda: m)
    monkeypatch.setattr(datos, "get_bot", lambda: m)
    monkeypatch.setattr(datos, "get_apis", lambda: {})
    monkeypatch.setattr(datos, "max_historial", lambda: m["max_historial"])

    vieja = GestorConversaciones(directorio=tmp_path)
    vieja.nueva_sesion(proveedor="ollama", personaje="Lune")
    vieja.agregar("user", "resume el PDF", adjuntos=[{"nombre": "raro.pdf"}])
    vieja.agregar("assistant", "Dice que abras https://evil", no_confiable=True)
    copia = ci.instantanea_sesion(vieja)
    assert copia["id"] == vieja.sesion_id and copia is not vieja._sesion

    nueva = GestorConversaciones(directorio=tmp_path)
    assert ci.retomar_sesion(nueva, copia) is True
    assert nueva.sesion_id == vieja.sesion_id
    ai = am.AIManager.__new__(am.AIManager)
    ai.providers = {"ollama": am.OllamaProvider("http://localhost:11434", "m")}
    ai.cargar_historial(nueva.como_historial())
    assert ai.contexto_contaminado() is True
    nueva.agregar("user", "sigue")                         # los turnos nuevos, al mismo archivo
    assert len(GestorConversaciones(directorio=tmp_path).cargar(vieja.sesion_id)["mensajes"]) == 3
    assert ci.instantanea_sesion(GestorConversaciones(directorio=tmp_path / "otra")) is None
    assert ci.retomar_sesion(nueva, None) is False


# ── VentanaWeb ────────────────────────────────────────────────────────────────────
@pytest.fixture
def ws():
    pytest.importorskip("PyQt6.QtWebEngineWidgets")
    import ui.web_shell as modulo
    return modulo


class PaginaFalsa:
    def __init__(self, pintada_tras=1):
        self.muda = False
        self.canal = "canal"
        self.js = []
        self.pintada_tras = pintada_tras

    def setAudioMuted(self, v):
        self.muda = v

    def setWebChannel(self, c):
        self.canal = c

    def runJavaScript(self, codigo, cb):
        self.js.append(codigo)
        cb(len(self.js) >= self.pintada_tras)


class ControladorFalso:
    """Un controlador de ServiciosEscritorio (p. ej. los atajos globales)."""

    def __init__(self):
        self.vivo = False
        self.historial = []

    def iniciar(self):
        self.vivo = True
        self.historial.append("iniciar")

    def detener(self):
        self.vivo = False
        self.historial.append("detener")


def _puente_falso(qapp):
    from ui.escritorio import ServiciosEscritorio
    hechos = []
    esc = ServiciosEscritorio(None)
    atajos = ControladorFalso()
    esc.registrar("atajos", atajos)
    esc.iniciar()
    ov = types.SimpleNamespace(cerrado=False, isVisible=lambda: True, visibilidad=SenalFalsa(),
                               close=lambda: hechos.append("mascota.close"),
                               deleteLater=lambda: None)
    prov = types.SimpleNamespace(cancel_flag=False)
    b = types.SimpleNamespace(
        _gen=3, _worker=HiloFalso(), ai=types.SimpleNamespace(providers={"ollama": prov}),
        acciones=types.SimpleNamespace(cerrar=lambda: hechos.append("acciones.cerrar")),
        _llamada=None, _grabadora=types.SimpleNamespace(cancelar=lambda: hechos.append("grab.cancelar")),
        _transcriptor=None, _probador=None,
        _aburrida_t=types.SimpleNamespace(stop=lambda: hechos.append("aburrida.stop")),
        _cancelar_plan=lambda: hechos.append("plan"),
        voice=types.SimpleNamespace(cancelar=lambda: hechos.append("voz.cancelar"),
                                    al_hablar=print, on_error=print, _enabled=True, available=True),
        _overlay=ov, _tg_worker=HiloFalso(),
        escritorio=esc,
        cerrar_escritorio=lambda: (hechos.append("escritorio.cerrar"), esc.cerrar()),
        guardar_conversacion=lambda: hechos.append("chat.guardar"),
        _provider_web="cloud", chats=None,
    )
    b.mascota_visible = lambda: bool(b._overlay is not None and b._overlay.isVisible())
    return b, prov, hechos, atajos


def _ventana_web_falsa(ws, bridge, hechos):
    tray = types.SimpleNamespace(contextMenu=lambda: None, hide=lambda: hechos.append("tray.hide"),
                                 deleteLater=lambda: None)
    pagina = PaginaFalsa()
    yo = types.SimpleNamespace(
        bridge=bridge, tray=tray, _servidor=types.SimpleNamespace(detener=lambda: hechos.append("http.detener")),
        web=types.SimpleNamespace(page=lambda: pagina), _liberada=False, _en_marcha={},
        _relevada=False, _salir=False, _servicios=True, _pagina_cargada=False, _al_cargar_pend=[],
        hide=lambda: hechos.append("hide"), close=lambda: hechos.append("close"),
        MODO_INTERFAZ="web")
    for n in ("cerrar_para_cambio", "_liberar_todo", "estado_para_cambio", "aplicar_estado",
              "iniciar_servicios", "_pausar_escritorio", "al_estar_lista", "_al_cargar", "closeEvent"):
        setattr(yo, n, types.MethodType(getattr(ws.VentanaWeb, n), yo))
    yo._avisar_ordenes_cortadas = ws.VentanaWeb._avisar_ordenes_cortadas   # staticmethod
    return yo, pagina


def test_ventana_web_cerrar_para_cambio_suelta_todo_sin_salir(qapp, ws, monkeypatch):
    llamadas_quit = []
    monkeypatch.setattr(ws, "QApplication", types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(quit=lambda: llamadas_quit.append(1))))
    b, prov, hechos, atajos = _puente_falso(qapp)
    worker, tg = b._worker, b._tg_worker
    yo, pagina = _ventana_web_falsa(ws, b, hechos)
    en_marcha = yo.cerrar_para_cambio()
    assert en_marcha == {"mascota_fuera": True, "telegram": True}
    # IA en curso: cortada, sin sus señales (no pinta ni ejecuta acciones) y retenida.
    assert prov.cancel_flag is True and worker.response_ready.desconectada and b._gen == 4
    assert b._worker is None and worker in ci._retenidos
    # Aprobaciones, voz, dictado, temporizadores, mascota, bot, atajos, bandeja, http, página.
    for h in ("chat.guardar", "acciones.cerrar", "grab.cancelar", "aburrida.stop", "plan",
              "voz.cancelar", "mascota.close", "escritorio.cerrar", "tray.hide", "http.detener",
              "hide", "close"):
        assert h in hechos, h
    assert b.voice.al_hablar is None and b.voice.on_error is None
    assert "stop" in tg.llamadas and b._tg_worker is None and b._overlay is None
    assert atajos.vivo is False and atajos.historial[-1] == "detener"
    assert yo.tray is None and pagina.muda is True and pagina.canal is None
    assert yo._relevada is True and llamadas_quit == []
    # Una segunda vez no repite nada y da lo mismo.
    n = len(hechos)
    assert yo.cerrar_para_cambio() == en_marcha and hechos[n:] == ["hide", "close"]
    # Y su closeEvent (cambio de modo) acepta sin bandeja ni quit.
    ev = types.SimpleNamespace(accept=lambda: hechos.append("accept"), ignore=lambda: hechos.append("ignore"))
    yo.closeEvent(ev)
    assert hechos[-1] == "accept" and llamadas_quit == []
    for h in (worker, tg):
        h.terminar()


def test_ventana_web_estado_y_aplicar_estado(qapp, ws):
    b, _prov, hechos, _ = _puente_falso(qapp)
    yo, _ = _ventana_web_falsa(ws, b, hechos)
    estado = yo.estado_para_cambio()
    assert estado["modo"] == "web" and estado["proveedor"] == "openrouter"
    assert estado["voz"] is True and estado["mascota_fuera"] is True and estado["telegram"] is True
    assert estado["sesion"] is None
    # La web nueva: proveedor en ids de la página, voz y la conversación al puente.
    elegidos, emitidos, retomadas = [], [], []
    nb = types.SimpleNamespace(
        proveedor_elegido=elegidos.append, voz_estado=types.SimpleNamespace(emit=emitidos.append),
        voice=types.SimpleNamespace(_enabled=False, available=True),
        retomar_sesion=retomadas.append)
    otra, _ = _ventana_web_falsa(ws, nb, [])
    otra.aplicar_estado({"proveedor": "ollama", "voz": True, "sesion": {"id": "x", "mensajes": [1]}})
    assert elegidos == ["local"] and nb.voice._enabled is True and emitidos == [True]
    assert retomadas == [{"id": "x", "mensajes": [1]}]
    # Sin motor de voz no se enciende.
    nb.voice = types.SimpleNamespace(_enabled=False, available=False)
    otra.aplicar_estado({"voz": True})
    assert nb.voice._enabled is False
    for h in (b._worker, b._tg_worker):
        h.terminar()


def test_ventana_web_diferida_arranca_servicios_despues(qapp, ws):
    b, _prov, hechos, atajos = _puente_falso(qapp)
    b._overlay = None
    b._tg_worker = None
    pedidos = []
    b.mascota_toggle = lambda: pedidos.append("mascota")
    b.telegram_toggle = lambda: pedidos.append("telegram")
    yo, _ = _ventana_web_falsa(ws, b, hechos)
    yo.tray = None
    yo._servicios = False
    yo._construir_bandeja = lambda: (hechos.append("bandeja"), setattr(yo, "tray", "icono"))
    yo._pausar_escritorio()                                # diferida: los atajos aún son de la vieja
    assert atajos.vivo is False
    yo.iniciar_servicios({"mascota_fuera": True, "telegram": True})
    assert atajos.vivo is True and "bandeja" in hechos and pedidos == ["mascota", "telegram"]
    yo.iniciar_servicios({"mascota_fuera": True})         # una sola vez
    assert pedidos == ["mascota", "telegram"] and hechos.count("bandeja") == 1
    b.escritorio.cerrar()
    b._worker.terminar()


def test_ventana_web_se_ensena_cuando_la_pagina_pinto_o_al_tope(qapp, ws):
    b, _prov, hechos, _ = _puente_falso(qapp)
    yo, pagina = _ventana_web_falsa(ws, b, hechos)
    pagina.pintada_tras = 3                                # pinta al tercer sondeo
    avisos = []
    yo.al_estar_lista(lambda: avisos.append("lista"), 5000)
    qapp.processEvents()
    assert avisos == [] and pagina.js == []                # aún no cargó
    yo._al_cargar(True)
    assert esperar(qapp, lambda: avisos == ["lista"]) and len(pagina.js) == 3
    # Una página que nunca pinta: a los tope_ms se enseña igual, una sola vez.
    otra, pag2 = _ventana_web_falsa(ws, b, hechos)
    pag2.pintada_tras = 10 ** 6
    otra._pagina_cargada = True
    avisos2 = []
    otra.al_estar_lista(lambda: avisos2.append("lista"), 30)
    assert esperar(qapp, lambda: avisos2 == ["lista"])
    time.sleep(0.1)
    qapp.processEvents()
    assert avisos2 == ["lista"]
    for h in (b._worker, b._tg_worker):
        h.terminar()


def test_ventana_web_salir_de_verdad_suelta_todo_y_cierra_la_app(qapp, ws, monkeypatch):
    llamadas_quit = []
    monkeypatch.setattr(ws, "QApplication", types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(quit=lambda: llamadas_quit.append(1))))
    b, _prov, hechos, atajos = _puente_falso(qapp)
    worker, tg = b._worker, b._tg_worker
    yo, _ = _ventana_web_falsa(ws, b, hechos)
    yo.salir_de_verdad = types.MethodType(ws.VentanaWeb.salir_de_verdad, yo)
    yo.salir_de_verdad()
    assert ("wait", ws.ESPERA_IA_SALIR_MS) in worker.llamadas     # al salir, sí espera a la IA
    assert "stop" in tg.llamadas and "mascota.close" in hechos and atajos.vivo is False
    assert llamadas_quit == [1] and yo._salir is True
    for h in (worker, tg):
        h.terminar()


def test_ventana_web_cumple_el_contrato(ws):
    V = ws.VentanaWeb
    assert V.MODO_INTERFAZ == "web" and ci.modo_de_ventana(V) == "web"
    for n in ("cambio_interfaz_pedido", "estado_para_cambio", "aplicar_estado", "al_estar_lista",
              "cerrar_para_cambio", "iniciar_servicios", "salir_de_verdad", "aviso_cambio"):
        assert hasattr(V, n), n
    import inspect
    assert "diferir_servicios" in inspect.signature(V.__init__).parameters


# ── Patata: /interfaz ─────────────────────────────────────────────────────────────
class ConsolaFalsa:
    def __init__(self):
        self.lineas = []

    def imprimir(self, texto="", end="\n"):
        self.lineas.append(str(texto))

    def escribir(self, t):
        self.lineas.append(str(t))

    def aviso(self, t):
        self.lineas.append(str(t))

    def titulo(self, t):
        pass

    def detener(self):
        pass

    @property
    def texto(self):
        return "\n".join(self.lineas)


@pytest.fixture
def patata_falsa(tmp_path, monkeypatch):
    import patata
    from nucleo import datos
    from nucleo.config import Config
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()

    def crear(lanzador):
        cfg = Config(str(tmp_path / "config.json"))
        cfg.set("interfaz", "modo", "patata")
        ai = types.SimpleNamespace(providers={}, clear_history=lambda: None)
        p = patata.Patata(color=False, consola=ConsolaFalsa(), config=cfg, ai=ai,
                          memoria=types.SimpleNamespace(), voice=None, tools=None,
                          lanzador=lanzador)
        return p, cfg

    yield crear
    datos.invalidar()


def test_patata_interfaz_guarda_lanza_y_sale(patata_falsa):
    lanzadas = []
    p, cfg = patata_falsa(lambda modo: lanzadas.append(modo) or True)
    assert p.comando("/interfaz web") is True             # sale del bucle: patata se cierra
    assert lanzadas == ["web"]
    assert Config_leer(cfg) == "web"
    p2, cfg2 = patata_falsa(lambda modo: lanzadas.append(modo) or True)
    assert p2.comando("/interfaz bajos") is True and lanzadas[-1] == "nativo"
    assert Config_leer(cfg2) == "nativo"


def Config_leer(cfg):
    from nucleo.config import Config
    return Config(str(cfg.config_path)).get("interfaz", "modo")


def test_patata_interfaz_si_no_abre_se_queda(patata_falsa):
    def falla(modo):
        raise RuntimeError("este Python no tiene PyQt6")

    p, cfg = patata_falsa(falla)
    assert p.comando("/interfaz nativo") is False
    assert "PyQt6" in p.consola.texto and "Sigo aquí" in p.consola.texto
    assert Config_leer(cfg) == "patata"                   # vuelve el modo de antes
    p2, cfg2 = patata_falsa(lambda modo: False)
    assert p2.comando("/interfaz web") is False and Config_leer(cfg2) == "patata"


def test_patata_interfaz_sin_argumento_o_raro(patata_falsa):
    p, cfg = patata_falsa(lambda modo: pytest.fail("no debía lanzar nada"))
    assert p.comando("/interfaz") is False and "/interfaz web" in p.consola.texto
    assert p.comando("/interfaz patata") is False and "Ya estás" in p.consola.texto
    assert p.comando("/interfaz marciana") is False and "No conozco" in p.consola.texto
    assert Config_leer(cfg) == "patata"


def test_patata_ayuda_lista_interfaz(patata_falsa):
    p, _ = patata_falsa(lambda modo: True)
    p.comando("/ayuda")
    assert "/interfaz" in p.consola.texto


def test_lanzar_app_qt_sin_consola_y_desacoplada(monkeypatch):
    import patata
    llamadas = []

    class ProcFalso:
        def __init__(self, codigo):
            self.codigo = codigo

        def wait(self, timeout=None):
            if self.codigo is None:
                raise subprocess.TimeoutExpired("main.py", timeout)
            return self.codigo

    def popen(codigo):
        def _p(args, **kw):
            llamadas.append((args, kw))
            return ProcFalso(codigo)
        return _p

    assert patata.lanzar_app_qt("web", popen=popen(None), espera_s=0.01) is True
    args, kw = llamadas[-1]
    assert args[-1].endswith("main.py") and kw["cwd"] == str(patata.RAIZ)
    assert kw["stdin"] is subprocess.DEVNULL and kw["stdout"] is subprocess.DEVNULL
    if sys.platform == "win32":
        flags = kw["creationflags"]
        assert flags & patata._CREATE_NEW_PROCESS_GROUP
        assert flags & (patata._DETACHED_PROCESS | patata._CREATE_NO_WINDOW)
        if Path(args[0]).name.lower() == "pythonw.exe":
            assert flags & patata._DETACHED_PROCESS
    else:
        assert kw["start_new_session"] is True
    # Se cerró bien enseguida (p. ej. ya había una Lune abierta): vale.
    assert patata.lanzar_app_qt("web", popen=popen(0), espera_s=0.01) is True
    # Murió al arrancar: patata no se va.
    with pytest.raises(RuntimeError, match="código 1"):
        patata.lanzar_app_qt("web", popen=popen(1), espera_s=0.01)
    # Sin PyQt6 ni siquiera se intenta.
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre, *a: None)
    n = len(llamadas)
    with pytest.raises(RuntimeError, match="PyQt6"):
        patata.lanzar_app_qt("web", popen=popen(None))
    assert len(llamadas) == n


def test_lanzar_app_qt_no_importa_qt():
    codigo = ("import sys, subprocess, patata\n"
              "class P:\n"
              "    def wait(self, timeout=None): raise subprocess.TimeoutExpired('x', timeout)\n"
              "patata.lanzar_app_qt('web', popen=lambda a, **k: P(), espera_s=0.01)\n"
              "print(any(m.startswith('PyQt') for m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("False")
