"""
Tests de ui/escritorio.py (ServiciosEscritorio): el esqueleto donde los cortes
siguientes enchufan alarmas, pantalla grande, modo juego, etc.

Sin pantalla (offscreen). Se prueba el registro y ciclo de vida de los
controladores, la tabla de prioridades con sus avisos de ceder/reanudar, la
mascota (bus inyectado, visibilidad y eventos de la página) y que los cambios
de estado lleguen por señal al hilo de Qt aunque vengan de otro hilo.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")


class Controlador:
    def __init__(self, nombre, diario):
        self.nombre, self.diario = nombre, diario

    def iniciar(self): self.diario.append(("iniciar", self.nombre))
    def detener(self): self.diario.append(("detener", self.nombre))
    def set_mascota(self, m): self.diario.append(("mascota", self.nombre, m))
    def ceder(self, c): self.diario.append(("ceder", self.nombre, c.actividad, c.valor, c.por))
    def reanudar(self, c): self.diario.append(("reanudar", self.nombre, c.actividad, c.valor))
    def evento_mascota(self, tipo, datos): self.diario.append(("evento", self.nombre, tipo, datos))


def test_registro_y_ciclo_de_vida(qapp):
    from ui.escritorio import ServiciosEscritorio
    from nucleo.estado_mascota import BusEstado
    s = ServiciosEscritorio()
    assert isinstance(s.estado, BusEstado) and s.controladores() == {}
    diario = []
    a = s.registrar("alarmas", Controlador("alarmas", diario), actividades=("alarma",))
    s.registrar("roto", object())                      # sin métodos: se tolera
    assert s.obtener("alarmas") is a and list(s.controladores()) == ["alarmas", "roto"]
    s.iniciar(); s.iniciar()                             # idempotente
    b = s.registrar("grande", Controlador("grande", diario), actividades=("grande",))
    assert diario == [("iniciar", "alarmas"), ("iniciar", "grande")]   # tarde: se inicia al registrar
    diario.clear()
    s.detener()
    assert diario == [("detener", "grande"), ("detener", "alarmas")]    # orden inverso
    assert s.quitar("grande") is True and s.obtener("grande") is None and s.quitar("grande") is False
    with pytest.raises(ValueError):
        s.registrar("x", b, actividades=("bailoteo",))
    s.cerrar()


def test_un_controlador_que_falla_no_tumba_a_los_demas(qapp):
    from ui.escritorio import ServiciosEscritorio

    class Roto:
        def iniciar(self): raise RuntimeError("boom")

    s = ServiciosEscritorio()
    diario = []
    s.registrar("roto", Roto())
    s.registrar("bien", Controlador("bien", diario))
    s.iniciar()
    assert ("iniciar", "bien") in diario
    s.cerrar()


def test_tabla_de_prioridades_avisa_de_ceder_y_reanudar(qapp):
    from ui.escritorio import ServiciosEscritorio
    s = ServiciosEscritorio()
    diario = []
    s.registrar("asiento", Controlador("asiento", diario), actividades=("sentada",))
    s.registrar("grande", Controlador("grande", diario), actividades=("grande",))

    assert s.prioridad.iniciar("sentada", "barra")
    assert s.estado.actual().sentada == "barra" and diario == []
    r = s.prioridad.iniciar("grande")
    assert r and s.estado.actual().grande is True and s.estado.actual().sentada == ""
    assert diario == [("ceder", "asiento", "sentada", "barra", "grande")]      # levántala
    # un juego manda sobre todo; mientras, la comida no puede empezar
    assert not s.prioridad.puede("comida") and s.prioridad.activas() == ["grande"]
    diario.clear()
    hechas = s.prioridad.terminar("grande")
    assert [c.actividad for c in hechas] == ["sentada"]
    assert diario == [("reanudar", "asiento", "sentada", "barra")]             # vuelve a sentarla
    assert s.estado.actual().sentada == "barra"
    # «bájate» durante la pantalla grande: ya no se vuelve a sentar
    s.prioridad.iniciar("grande"); diario.clear()
    s.prioridad.olvidar("sentada")
    assert s.prioridad.terminar("grande") == [] and diario == []
    assert s.prioridad.TABLA["juego"] > s.prioridad.TABLA["alarma"]
    s.cerrar()


def test_mascota_recibe_el_bus_y_se_siguen_su_visibilidad_y_sus_eventos(qapp):
    from PyQt6.QtCore import QObject, pyqtSignal
    from ui.escritorio import ServiciosEscritorio

    class MascotaFalsa(QObject):
        visibilidad = pyqtSignal(bool)
        evento_js = pyqtSignal(str, dict)
        render = "vrm"

        def __init__(self):
            super().__init__(); self.bus = "sin"
        def isVisible(self): return True
        def set_bus_estado(self, bus): self.bus = bus

    s = ServiciosEscritorio()
    diario, eventos, cambios = [], [], []
    s.registrar("frases", Controlador("frases", diario))
    s.evento_mascota.connect(lambda t, d: eventos.append((t, d)))
    s.mascota_cambio.connect(lambda m: cambios.append(m))
    m = MascotaFalsa()
    s.set_mascota(m)
    assert m.bus is s.estado and s.mascota is m and cambios == [m]
    assert s.estado.actual().render == "vrm" and s.estado.actual().visible is True
    assert ("mascota", "frases", m) in diario
    m.visibilidad.emit(False)
    assert s.estado.actual().visible is False
    m.evento_js.emit("caricia", {"lado": 1})
    assert eventos == [("caricia", {"lado": 1})]
    assert ("evento", "frases", "caricia", {"lado": 1}) in diario
    # soltarla: se desconecta y el bus se le retira
    s.set_mascota(None)
    assert m.bus is None and s.estado.actual().render == "" and cambios[-1] is None
    m.evento_js.emit("caricia", {})
    m.visibilidad.emit(True)
    assert len(eventos) == 1 and s.estado.actual().visible is False
    s.cerrar()


def test_los_cambios_de_estado_llegan_por_senal_en_el_hilo_de_qt(qapp):
    from ui.escritorio import ServiciosEscritorio
    s = ServiciosEscritorio()
    recibidos = []
    s.estado_cambio.connect(lambda e, c: recibidos.append((threading.get_ident(), e, c)))
    s.estado.actualizar(durmiendo=True)
    assert recibidos and recibidos[-1][2] == {"durmiendo": (False, True)}   # mismo hilo: directo
    principal = threading.get_ident()
    recibidos.clear()
    h = threading.Thread(target=lambda: s.estado.actualizar(hablando=True))
    h.start(); h.join()
    for _ in range(50):
        qapp.processEvents()
        if recibidos:
            break
    assert recibidos and recibidos[0][0] == principal and recibidos[0][1].hablando is True
    s.cerrar()
    recibidos.clear()
    s.estado.actualizar(llamada=True)                  # tras cerrar ya no avisa
    qapp.processEvents()
    assert recibidos == []


def _procesar(qapp, hasta, veces=100):
    for _ in range(veces):
        qapp.processEvents()
        if hasta():
            return


def test_estado_cambio_llega_en_orden_aunque_se_mezclen_hilos(qapp):
    """El caso de la revisión: un cambio de otro hilo aún en la cola de eventos
    y otro posterior en el hilo de Qt. Antes el de Qt salía directo y el viejo
    llegaba después, así que lo último que veían los receptores era falso."""
    from ui.escritorio import ServiciosEscritorio
    s = ServiciosEscritorio()
    recibidos = []
    s.estado_cambio.connect(lambda e, c: recibidos.append((e, dict(c))))
    h = threading.Thread(target=lambda: s.estado.actualizar(hablando=True))
    h.start(); h.join()
    s.estado.actualizar(arrastrando=True)              # hilo de Qt, con uno pendiente en cola
    assert recibidos == []                             # no se adelanta al pendiente
    _procesar(qapp, lambda: len(recibidos) >= 2)
    assert [c for _, c in recibidos] == [{"hablando": (False, True)}, {"arrastrando": (False, True)}]
    ultimo = recibidos[-1][0]
    assert ultimo.hablando is True and ultimo.arrastrando is True and ultimo is s.estado.actual()
    # Vaciada la cola, los cambios del hilo de Qt vuelven a salir directos.
    s.estado.actualizar(durmiendo=True)
    assert recibidos[-1][1] == {"durmiendo": (False, True)}
    s.cerrar()


def test_un_cambio_hecho_por_un_receptor_durante_una_entrega_en_cola_va_detras(qapp):
    from ui.escritorio import ServiciosEscritorio
    s = ServiciosEscritorio()
    orden = []

    def receptor(e, c):
        orden.append(tuple(c))
        if "hablando" in c:
            s.estado.actualizar(emocion="happy")       # reacciona desde el hilo de Qt
    s.estado_cambio.connect(receptor)
    h = threading.Thread(target=lambda: (s.estado.actualizar(hablando=True),
                                         s.estado.actualizar(pensando=True)))
    h.start(); h.join()
    _procesar(qapp, lambda: len(orden) >= 3)
    assert orden == [("hablando",), ("pensando",), ("emocion",)]
    s.cerrar()


def test_la_tabla_no_sienta_para_levantar_en_el_acto(qapp):
    """Sentada → MMD → pantalla grande. Al acabar la grande: solo se reanuda el
    MMD (antes: reanudar sentada, ceder sentada, reanudar mmd)."""
    from ui.escritorio import ServiciosEscritorio
    s = ServiciosEscritorio()
    diario = []
    s.registrar("asiento", Controlador("asiento", diario), actividades=("sentada",))
    s.registrar("mmd", Controlador("mmd", diario), actividades=("mmd",))
    s.registrar("grande", Controlador("grande", diario), actividades=("grande",))
    assert s.prioridad.iniciar("sentada", "barra")
    assert s.prioridad.iniciar("mmd")
    assert s.prioridad.iniciar("grande")
    diario.clear()
    hechas = s.prioridad.terminar("grande")
    assert [c.actividad for c in hechas] == ["mmd"]
    assert diario == [("reanudar", "mmd", "mmd", "mmd")]
    assert s.estado.actual().bailando == "mmd" and s.estado.actual().sentada == ""
    diario.clear()
    assert [c.actividad for c in s.prioridad.terminar("mmd")] == ["sentada"]
    assert diario == [("reanudar", "asiento", "sentada", "barra")]
    s.cerrar()


def test_si_un_reanudar_no_puede_empezar_sigue_pendiente(qapp):
    """Entre terminar_actividad e iniciar_actividad otro hilo empieza un juego:
    la sentada no se pierde, espera a que acabe el juego."""
    from ui.escritorio import ServiciosEscritorio
    from nucleo.estado_mascota import BusEstado

    class BusCarrera(BusEstado):
        def terminar_actividad(self, actividad):
            r = super().terminar_actividad(actividad)
            if actividad == "grande":
                self.actualizar(juego=True)            # «otro hilo», justo entre medias
            return r

    s = ServiciosEscritorio(bus=BusCarrera())
    diario = []
    s.registrar("asiento", Controlador("asiento", diario), actividades=("sentada",))
    s.prioridad.iniciar("sentada", "ventana")
    s.prioridad.iniciar("grande")
    diario.clear()
    assert s.prioridad.terminar("grande") == [] and diario == []
    assert [(c.actividad, c.valor) for c in s.estado.pendientes()["juego"]] == [("sentada", "ventana")]
    assert [c.actividad for c in s.prioridad.terminar("juego")] == ["sentada"]
    assert diario == [("reanudar", "asiento", "sentada", "ventana")]
    s.cerrar()


# ── Cableado: LuneBridge (web) y LuneCDWindow (nativa) crean los servicios ──────

def _mascota_falsa_cls():
    from PyQt6.QtCore import QObject, pyqtSignal

    class MascotaFalsa(QObject):
        visibilidad = pyqtSignal(bool)
        evento_js = pyqtSignal(str, dict)
        recrear = pyqtSignal()

        def __init__(self, config=None, ai_manager=None, render=None, **kw):
            super().__init__()
            self.render, self.bus, self.cerrado, self._vis = render, "sin", False, False

        def isVisible(self): return self._vis
        def show(self): self._vis = True; self.visibilidad.emit(True)
        def hide(self): self._vis = False; self.visibilidad.emit(False)
        def raise_(self): pass
        def close(self): self.cerrado = True; self.hide()
        def set_bus_estado(self, bus): self.bus = bus

    return MascotaFalsa


def test_el_puente_web_crea_los_servicios_y_les_pasa_la_mascota(qapp, tmp_path, monkeypatch):
    import types
    from nucleo.config import Config
    from ui.escritorio import ServiciosEscritorio
    from ui.web_bridge import LuneBridge

    # ui.companion de mentira: no hace falta QtWebEngine para probar el cableado.
    Falsa = _mascota_falsa_cls()
    monkeypatch.setitem(sys.modules, "ui.companion",
                        types.SimpleNamespace(CompanionFlotante=Falsa))
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "vrm")
    b = LuneBridge(config=cfg, ai_manager=object(), memoria=object(), tools=object(),
                   voice=type("Voz", (), {})())
    try:
        assert isinstance(b.escritorio, ServiciosEscritorio) and b.escritorio.iniciado
        eventos = []
        b.escritorio.evento_mascota.connect(lambda t, d: eventos.append((t, d)))
        assert b.mascota_toggle() is True
        ov = b._overlay
        assert b.escritorio.mascota is ov and ov.bus is b.escritorio.estado
        est = b.escritorio.estado.actual()
        assert est.render == "vrm" and est.visible is True
        ov.evento_js.emit("caricia", {"lado": 1})          # la cola de eventos ya tiene receptor
        assert eventos == [("caricia", {"lado": 1})]
        b._mascota_recrear()                                # cambia de render: otra ventana
        assert b._overlay is not ov and b.escritorio.mascota is b._overlay
        assert ov.bus is None and b._overlay.bus is b.escritorio.estado
        b.cerrar_escritorio()                               # al salir (aboutToQuit)
        assert b.escritorio.mascota is None and not b.escritorio.iniciado
        assert b._overlay.bus is None                       # soltó el bus de la mascota
    finally:
        b.cerrar_escritorio()
        b.deleteLater()


def test_la_ventana_nativa_engancha_la_mascota(qapp, tmp_path, monkeypatch):
    import inspect
    import types
    import main
    from nucleo.config import Config
    from ui.escritorio import ServiciosEscritorio

    Falsa = _mascota_falsa_cls()
    monkeypatch.setattr(main, "AvatarOverlay", Falsa)
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("avatar", "render", "sprites")
    esc = ServiciosEscritorio()
    yo = types.SimpleNamespace(config=cfg, ai_manager=None, escritorio=esc, _overlay=None,
                               _on_mascota_visible=lambda v: None, _mascota_recrear=lambda: None)
    yo._escritorio_mascota = types.MethodType(main.LuneCDWindow._escritorio_mascota, yo)
    yo._crear_mascota = types.MethodType(main.LuneCDWindow._crear_mascota, yo)
    ov = yo._crear_mascota()
    assert esc.mascota is ov and ov.bus is esc.estado
    assert esc.estado.actual().render == "sprites"
    yo._overlay = ov
    main.LuneCDWindow._mascota_recrear(yo)                  # estaba oculta: no se recrea
    assert esc.mascota is None and ov.bus is None and yo._overlay is None
    # Se crea en __init__ y se cierra al salir de verdad.
    assert "ServiciosEscritorio(" in inspect.getsource(main.LuneCDWindow.__init__)
    assert "self.escritorio.cerrar()" in inspect.getsource(main.LuneCDWindow.closeEvent)
    esc.cerrar()
