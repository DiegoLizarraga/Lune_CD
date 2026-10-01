"""
Tests de los recursos del lado de Python (11.3):

  · Optimizador: el monitor del panel nativo solo mide a la vista y cpu_percent no
    duerme el hilo de Qt; LuneBridge.sistema_info no bloquea (los procesos, en un hilo).
  · Chat web: los trozos del stream agrupados (como mucho uno cada CHUNK_CADA_MS, el
    último acumulado SIEMPRE antes de `done`, nada de un envío ya cortado) y lo mismo
    para la burbuja de la asistente.
  · Música: sin público, sondeo lento y sin bucle rápido; ControlBaile.hay_publico.
  · Red: red.anunciar apagado de serie y el anuncio mDNS en un hilo.
  · Ventana nativa: el sondeo de proveedores solo a la vista y antes de enviar.
  · Whisper: soltar_modelo por inactividad, en el recorte de RAM y en modo juego, nunca
    con un dictado, una llamada o una transcripción en curso.
  · Modo juego: descarga el modelo de Ollama local (salvo que el bot de Minecraft piense).
  · La carpeta de modelos 3D con su ruta de verdad en los textos.

Offscreen, sin red, sin tarjeta de sonido y sin datos de verdad (conftest).
"""
import json
import sys
import threading
import time
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtWidgets")

# El puente de la web con sus dobles (AIFalso, VozFalsa…): el mismo de los tests del chat.
from test_web_chat_asistente import AsistenteFalsa, TimerFalso, WorkerFalso, puente  # noqa: E402,F401


def esperar(cond, tope=3.0):
    from PyQt6.QtWidgets import QApplication
    fin = time.monotonic() + tope
    while not cond() and time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.005)
    return cond()


class ConfigDict:
    def __init__(self, d=None):
        self.d = d or {}

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor


# ── 1. Optimizador ─────────────────────────────────────────────────────────────

def test_estadisticas_no_duermen_el_hilo(monkeypatch):
    psutil = pytest.importorskip("psutil")
    from servicios import optimizador as O
    intervalos = []
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None, **k: intervalos.append(interval) or 12.0)
    s = O.Optimizador().estadisticas_sistema()
    assert s["disponible"] and s["cpu"] == 12.0
    O.Optimizador.cebar_cpu()
    assert intervalos == [None, None]                    # nunca interval=0.2 (200 ms dormido)


def test_panel_optimizador_solo_mide_a_la_vista(qapp, tmp_path, monkeypatch):
    from nucleo.config import Config
    from servicios import optimizador as O
    import ui.optimizer_panel as op
    lecturas, cebados = [], []
    monkeypatch.setattr(op, "PRIMERA_LECTURA_MS", 5)
    monkeypatch.setattr(O.Optimizador, "estadisticas_sistema",
                        lambda self: lecturas.append(1) or {"disponible": False})
    monkeypatch.setattr(O.Optimizador, "cebar_cpu", staticmethod(lambda: cebados.append(1)))
    p = op.OptimizadorPanel(Config(str(tmp_path / "config.json")))
    time.sleep(0.25)
    qapp.processEvents()
    assert not p._stats_timer.isActive() and lecturas == [] and cebados == []   # oculto: nada
    p.show()
    assert p._stats_timer.isActive() and cebados == [1]
    assert esperar(lambda: lecturas)                     # la primera lectura, tras cebar
    p.hide()
    assert not p._stats_timer.isActive() and not p._primera.isActive()
    n = len(lecturas)
    p._refrescar_stats()                                 # un tic que llega ya oculto: nada
    assert len(lecturas) == n
    p.deleteLater()


def test_sistema_info_no_bloquea_y_los_procesos_van_en_un_hilo(puente, monkeypatch):
    psutil = pytest.importorskip("psutil")
    from servicios import optimizador as O
    intervalos, hilos = [], []
    soltar = threading.Event()
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None, **k: intervalos.append(interval) or 7.5)

    def pesados(self, top=8):
        hilos.append(threading.current_thread() is threading.main_thread())
        soltar.wait(3)
        return [{"pid": 1, "nombre": "juego.exe", "ram": 1, "ram_str": "1 B"}]
    monkeypatch.setattr(O.Optimizador, "procesos_pesados", pesados)
    t0 = time.monotonic()
    j = json.loads(puente.sistema_info())
    assert time.monotonic() - t0 < 0.5                   # ni 200 ms de CPU ni process_iter aquí
    assert j["cpu"] is None and j["procesos"] == [] and j["ram"] is not None   # la 1ª ceba la CPU
    soltar.set()
    puente._sis_hilo.join(3)
    assert hilos == [False] and intervalos == [None]
    j = json.loads(puente.sistema_info())
    assert j["cpu"] == 7.5 and j["procesos"][0]["nombre"] == "juego.exe"
    assert hilos == [False]                              # reciente: no se vuelve a contar


def test_optimizar_web_pide_dos_veces_al_abrir():
    src = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "panels.jsx").read_text("utf-8")
    trozo = src[src.index("function OptimizarPanel"):]
    assert "setTimeout(cargar, 600)" in trozo and "clearTimeout(t0)" in trozo


# ── 2. Chat web: trozos agrupados ──────────────────────────────────────────────

@pytest.fixture
def stream(puente, monkeypatch):
    """Puente con un worker falso en marcha, reloj y temporizador del agrupado a mano."""
    import ui.web_bridge as wb
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    monkeypatch.setattr(wb.datos, "openrouter_key", lambda: "sk-prueba")
    reloj = {"t": 1000.0}
    monkeypatch.setattr(wb, "time", types.SimpleNamespace(monotonic=lambda: reloj["t"]))
    b = puente
    timer = TimerFalso()
    timer.timeout.connect(b._soltar_chunk)
    b._chunk_timer = timer
    orden = []
    b.chunk.connect(lambda t: orden.append(("chunk", t)))
    b.done.connect(lambda t, e: orden.append(("done", t)))
    return types.SimpleNamespace(b=b, reloj=reloj, timer=timer, orden=orden)


def _pasa(s, ms):
    s.reloj["t"] += ms / 1000.0


def test_trozos_agrupados_y_el_ultimo_antes_de_done(stream):
    s = stream
    s.b.enviar("cuéntame de python", "cloud")
    w = WorkerFalso.creados[-1]
    w.token_received.emit("Ho")                          # el primero, al momento
    assert s.orden == [("chunk", "Ho")]
    _pasa(s, 10)
    w.token_received.emit("Hola")                        # dentro de la ventana: se guarda
    _pasa(s, 10)
    w.token_received.emit("Hola, qué")
    assert s.orden == [("chunk", "Ho")] and s.timer.activo
    s.timer.disparar()                                   # vence: sale el ÚLTIMO acumulado
    assert s.orden[-1] == ("chunk", "Hola, qué")
    _pasa(s, 10)
    w.token_received.emit("Hola, qué tal")               # pendiente al terminar
    w.response_ready.emit("Hola, qué tal.")
    trozos = [t for k, t in s.orden if k == "chunk"]
    assert trozos == ["Ho", "Hola, qué", "Hola, qué tal"]   # en orden, sin repetir
    assert s.orden[-2] == ("chunk", "Hola, qué tal") and s.orden[-1] == ("done", "Hola, qué tal.")
    s.timer.disparar()                                   # nada después de done
    assert s.orden[-1][0] == "done"


def test_trozos_espaciados_salen_todos(stream):
    s = stream
    s.b.enviar("cuéntame de python", "cloud")
    w = WorkerFalso.creados[-1]
    for texto in ("a", "ab", "abc"):
        w.token_received.emit(texto)
        _pasa(s, 60)                                     # más que CHUNK_CADA_MS entre trozos
    assert [t for k, t in s.orden if k == "chunk"] == ["a", "ab", "abc"]


def test_detener_y_un_envio_viejo_no_pintan_nada_despues(stream):
    s = stream
    s.b.enviar("cuéntame de python", "cloud")
    w = WorkerFalso.creados[-1]
    w.token_received.emit("Uno")
    w.token_received.emit("Uno dos")                     # pendiente
    s.b.detener()
    assert s.orden[-2:] == [("chunk", "Uno dos"), ("done", "")]   # lo que llegó, antes del done
    w.token_received.emit("Uno dos tres")                # el worker viejo aún emite: se ignora
    s.timer.disparar()
    assert s.orden[-1] == ("done", "")
    # Un pendiente de otra generación se tira aunque alguien vacíe.
    s.b._chunk_pend = (s.b._gen - 1, "viejo")
    s.b._soltar_chunk()
    assert ("chunk", "viejo") not in s.orden


def test_error_saca_lo_pendiente_antes(stream):
    s = stream
    s.b.enviar("cuéntame de python", "cloud")
    w = WorkerFalso.creados[-1]
    w.token_received.emit("Medio")
    w.token_received.emit("Medio texto")
    w.error_occurred.emit("se cortó")
    assert s.orden[-2:] == [("chunk", "Medio texto"), ("done", "Error: se cortó")]


def test_burbuja_de_la_asistente_tambien_agrupada(stream):
    s = stream
    ov = AsistenteFalsa()
    s.b._overlay = ov
    assert s.b.enviar_desde_asistente("¿y tú?") is True
    w = WorkerFalso.creados[-1]
    for texto in ("Bien", "Bien,", "Bien, gra", "Bien, gracias"):
        w.token_received.emit(texto)
        _pasa(s, 5)
    assert ov.textos == ["Bien"]                         # un runJavaScript, no cuatro
    w.response_ready.emit("Bien, gracias.")
    assert ov.textos == ["Bien", "Bien, gracias", "Bien, gracias."]
    assert ov.fines and s.orden[-1] == ("done", "Bien, gracias.")


# ── 3. Música: sin público no hay bucle rápido ─────────────────────────────────

def test_detector_sin_publico_sondeo_lento_y_sin_bucle_rapido():
    from test_musica_detector import MedidorFalso, Reloj, detector
    reloj = Reloj(0.0)
    m = MedidorFalso(sp=[11, "Spotify", 0.5])
    esperas = []

    def dormir(seg):
        esperas.append(seg)
        reloj.t += seg
        if reloj.t > 60.0:
            d._parar.set()
    d = detector(m, reloj=reloj, dormir=dormir, hay_publico=lambda: False)
    d._bucle()
    assert m.lecturas == []                              # ni una lectura a 50 Hz
    assert esperas and all(x == pytest.approx(d.INTERVALO_SIN_PUBLICO_S) for x in esperas)
    assert m.enumeraciones == pytest.approx(7, abs=1)    # cada 10 s, no cada 2 s
    assert d.cambios == [(True, "Spotify")]              # la música se sigue detectando


def test_detector_vuelve_al_bucle_rapido_con_publico_y_despertar():
    from test_musica_detector import activo
    publico = {"si": False}
    d, m = activo(hay_publico=lambda: publico["si"])
    m.lecturas = []
    d.reloj.t += 0.02
    d.rapido()
    assert m.lecturas == []
    publico["si"] = True
    d.reloj.t += 0.02
    d.rapido()
    assert m.lecturas == ["sp"]
    d._pedido.clear()
    d._despertar.clear()
    d.despertar()                                        # vuelve el público: sondea ya
    assert d._pedido.is_set() and d._despertar.is_set()


class _Visible:
    def __init__(self, v=False):
        self.v = v

    def isVisible(self):
        return self.v


def test_control_baile_hay_publico_y_despierta_al_detector(qapp, monkeypatch):
    import ui.baile_qt as bq
    from test_baile_qt import Config
    from ui.escritorio import ServiciosEscritorio
    creados = []

    class Detector:
        def __init__(self, config, **kw):
            self.kw = kw
            self.on_cambio = self.on_pulso = self.on_sesiones = None
            self.llamadas = []
            creados.append(self)

        def iniciar(self):
            pass

        def detener(self):
            pass

        def despertar(self):
            self.llamadas.append("despertar")

        def forzar_pulso(self, on):
            pass

    monkeypatch.setattr(bq, "DetectorMusica", Detector)
    esc = ServiciosEscritorio(Config())
    ctl = bq.ControlBaile(esc, esc.config)
    vista = {"ventana": False}
    ctl.set_anfitrion(types.SimpleNamespace(ventana_visible=lambda: vista["ventana"]))
    ctl.iniciar()
    hay = creados[0].kw["hay_publico"]
    assert ctl._t_publico.isActive()
    assert ctl.hay_publico() is False and hay() is False  # en la bandeja y sin asistente
    m = _Visible(False)
    ctl.set_asistente(m)
    assert hay() is False
    m.v = True                                           # la asistente sale al escritorio
    ctl._revisar_publico()
    assert hay() is True and creados[0].llamadas == ["despertar"]
    m.v = False
    vista["ventana"] = True                              # o la ventana a la vista
    ctl._revisar_publico()
    assert hay() is True and creados[0].llamadas == ["despertar"]
    vista["ventana"] = False
    ctl._revisar_publico()
    assert hay() is False
    ctl.detener()
    assert not ctl._t_publico.isActive()
    esc.cerrar()
    ctl.deleteLater()


def test_baile_sin_anfitrion_siempre_tiene_publico(qapp):
    from test_baile_qt import Config, DetectorFalso
    from ui.baile_qt import ControlBaile
    from ui.escritorio import ServiciosEscritorio
    esc = ServiciosEscritorio(Config())
    ctl = ControlBaile(esc, esc.config, detector=DetectorFalso())
    assert ctl.hay_publico() is True                     # como antes (y en los dobles de test)
    esc.cerrar()
    ctl.deleteLater()


def test_montar_ocio_le_pasa_el_anfitrion_al_baile():
    from ui.montaje_ocio import montar_ocio

    class Baile:
        anfitrion = None

        def set_anfitrion(self, a):
            self.anfitrion = a

    b = Baile()
    anf = types.SimpleNamespace(modo="normal", ventana_visible=lambda: True)
    s4 = types.SimpleNamespace(escritorio=None, anfitrion=anf, despachador=None, avisar=None, _deshacer=[])
    montar_ocio(s4, ConfigDict(), fabricas={"en_ui": lambda: None, "grande": lambda *a, **k: None,
                                            "alarmas": lambda *a, **k: None, "baile": lambda *a, **k: b})
    assert b.anfitrion is anf


# ── 4. Red ─────────────────────────────────────────────────────────────────────

def test_anunciar_apagado_de_serie_y_el_config_viejo_conserva_el_suyo(tmp_path):
    from nucleo.config import Config
    assert Config.DEFAULT_CONFIG["red"]["anunciar"] is False
    assert Config(str(tmp_path / "nuevo.json")).get("red", "anunciar") is False
    viejo = tmp_path / "viejo.json"
    viejo.write_text(json.dumps({"red": {"anunciar": True}}), "utf-8")
    assert Config(str(viejo)).get("red", "anunciar") is True


def test_anuncio_mdns_en_un_hilo(qapp, monkeypatch):
    from lune_core import descubrimiento as D
    from servicios import red_service as R
    arrancar = threading.Event()
    eventos = []

    class Anuncio:
        def __init__(self, nombre, rol, puerto, caps):
            self.nombre = nombre

        def iniciar(self):
            eventos.append(("iniciar", threading.current_thread() is threading.main_thread()))
            arrancar.wait(3)
            return True

        def detener(self):
            eventos.append(("detener", self.nombre))

        def actualizar(self, rol, caps):
            eventos.append(("actualizar", threading.current_thread() is threading.main_thread()))

    monkeypatch.setattr(D, "AnuncioLune", Anuncio)
    monkeypatch.setattr(D, "zeroconf_disponible", lambda: True)
    monkeypatch.setattr(R.datos, "hub_puerto", lambda: 7777)
    monkeypatch.setattr(R.datos, "ollama_model", lambda: "")
    red = R.RedService(ConfigDict({"red": {"anunciar": True, "nombre": "pc", "rol": "hibrido"}}))
    t0 = time.monotonic()
    assert red.anunciar() is True
    assert time.monotonic() - t0 < 0.5                   # register_service no espera aquí
    assert esperar(lambda: eventos) and eventos[0] == ("iniciar", False)
    red.detener()                                        # salir mientras arranca
    arrancar.set()
    red._hilo.join(3)
    assert ("detener", "pc") in eventos and red._anuncio is None   # se retira al terminar
    # Un anuncio normal se queda y reanunciar actualiza en otro hilo.
    eventos.clear()
    red.anunciar()
    red._hilo.join(3)
    assert red._anuncio is not None
    red.reanunciar()
    red._hilo.join(3)
    assert eventos[-1] == ("actualizar", False)
    red.detener()


def test_sin_anunciar_no_hay_hilo(qapp, monkeypatch):
    from lune_core import descubrimiento as D
    from servicios import red_service as R
    monkeypatch.setattr(D, "zeroconf_disponible", lambda: True)
    red = R.RedService(ConfigDict())                     # sin red.anunciar: el de serie (False)
    assert red.anunciar() is False and red._hilo is None


# ── 5. Ventana nativa: sondeo de proveedores ───────────────────────────────────

def test_nativa_sondea_proveedores_solo_a_la_vista():
    import main

    class Timer:
        activo = False

        def isActive(self):
            return self.activo

        def start(self):
            self.activo = True

        def stop(self):
            self.activo = False

    sondeos = []
    vista = {"si": False}
    yo = types.SimpleNamespace(_timer_estado=Timer(), _sondeo_prov_t=None, _relevada=False, _quit_real=False)

    def sondear():
        sondeos.append(1)
        yo._sondeo_prov_t = time.monotonic()
    yo._sondear_proveedores = sondear
    yo._ventana_se_ve = lambda: vista["si"]
    for n in ("_cerrandose", "_sondear_si_viejo", "_al_cambiar_visibilidad"):
        setattr(yo, n, types.MethodType(getattr(main.LuneCDWindow, n), yo))
    yo._al_cambiar_visibilidad()
    assert not yo._timer_estado.activo and sondeos == []     # en la bandeja: ni timer ni red
    vista["si"] = True
    yo._al_cambiar_visibilidad()
    assert yo._timer_estado.activo and sondeos == [1]        # al enseñarse, sondea
    yo._al_cambiar_visibilidad()
    assert sondeos == [1]
    vista["si"] = False                                      # minimizada u oculta
    yo._al_cambiar_visibilidad()
    assert not yo._timer_estado.activo
    yo._sondear_si_viejo()
    assert sondeos == [1]                                    # reciente: no repite al enviar
    yo._sondeo_prov_t -= main.SONDEO_PROVEEDORES_MS / 1000 + 1
    yo._sondear_si_viejo()
    assert sondeos == [1, 1]                                 # viejo: sondea antes de enviar
    yo._relevada = True                                      # cerrándose: nada
    vista["si"] = True
    yo._al_cambiar_visibilidad()
    assert not yo._timer_estado.activo


def test_nativa_ya_no_sondea_al_construir_y_si_antes_de_enviar():
    import inspect
    import main
    src = (RAIZ / "main.py").read_text("utf-8")
    assert "QTimer.singleShot(800, self._sondear_proveedores)" not in src
    assert "self._timer_estado.start(60000)" not in src
    assert "_sondear_si_viejo" in inspect.getsource(main.LuneCDWindow._send_message)


# ── 6. Whisper: soltar el modelo ───────────────────────────────────────────────

@pytest.fixture
def whisper(monkeypatch):
    from servicios import voz_entrada as V
    for nombre, valor in (("_modelo_cargado", None), ("_modelo_nombre", None), ("_modelo_dispositivo", None),
                          ("_usos", 0), ("_ultimo_uso", 0.0), ("_temporizador", None)):
        monkeypatch.setattr(V, nombre, valor)
    yield V
    t = V._temporizador
    if t is not None:
        t.cancel()


def _cargar(V):
    V._modelo_cargado, V._modelo_nombre, V._modelo_dispositivo = object(), "base", "cpu"


def test_soltar_modelo_y_nunca_en_uso(whisper):
    V = whisper
    assert V.soltar_modelo(recolectar=False) is False        # no había
    _cargar(V)
    V.ocupar()                                               # un dictado o una llamada
    assert V.soltar_modelo(recolectar=False) is False and V.modelo_en_memoria()
    V.desocupar()
    assert V.soltar_modelo(recolectar=False) is True and not V.modelo_en_memoria()
    _cargar(V)
    assert V._lock_modelo.acquire(timeout=1)                 # cargándose: tampoco
    try:
        assert V.soltar_modelo(recolectar=False) is False
    finally:
        V._lock_modelo.release()


def test_inactividad_suelta_el_modelo(whisper, monkeypatch):
    V = whisper
    monkeypatch.setattr(V, "INACTIVIDAD_SOLTAR_S", 0.05)
    _cargar(V)
    V.ocupar()
    time.sleep(0.12)
    assert V.modelo_en_memoria()                             # en uso no cuenta el tiempo
    V.desocupar()                                            # desde aquí, la inactividad
    assert esperar(lambda: not V.modelo_en_memoria(), 2.0)


def test_transcribir_marca_el_uso(whisper, monkeypatch, tmp_path):
    V = whisper
    vistos = []

    class Modelo:
        def transcribe(self, ruta, **kw):
            vistos.append(V.en_uso())
            return [types.SimpleNamespace(text=" hola ")], None

    monkeypatch.setattr(V, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(V, "cargar_modelo", lambda nombre="base", forzar_cpu=False: Modelo())
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    assert V.transcribir(wav) == "hola"
    assert vistos == [True] and not V.en_uso()


def test_grabadora_ocupa_mientras_dicta(whisper, monkeypatch):
    V = whisper

    class Stream:
        def start(self): pass
        def stop(self): pass
        def close(self): pass

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=lambda **k: Stream()))
    monkeypatch.setattr(V, "_abrir_stream", lambda sd, disp, crear: (Stream(), 16000))
    g = V.Grabadora()
    g.iniciar()
    assert V.en_uso()
    g.cancelar()
    assert not V.en_uso()
    g.iniciar()
    assert g.detener() is None and not V.en_uso()            # sin audio: None, y libre
    g.cancelar()
    assert not V.en_uso()                                    # sin desocupar dos veces


def test_recorte_de_ram_suelta_whisper(whisper, monkeypatch):
    from servicios import recorte_ram as rr
    V = whisper
    _cargar(V)
    V.ocupar()
    rr.recortar(pids=[], recolectar=False)
    assert V.modelo_en_memoria()                             # dictando: se queda
    V.desocupar()
    rr.recortar(pids=[], recolectar=False)
    assert not V.modelo_en_memoria()


def test_soltar_whisper_no_importa_voz_entrada(monkeypatch):
    from servicios import recorte_ram as rr
    monkeypatch.delitem(sys.modules, "servicios.voz_entrada", raising=False)
    assert rr.soltar_whisper() is False
    assert "servicios.voz_entrada" not in sys.modules


def test_la_llamada_ocupa_whisper():
    src = (RAIZ / "servicios" / "llamada.py").read_text("utf-8")
    assert "voz_entrada.ocupar()" in src and "voz_entrada.desocupar()" in src


# ── 7. Modo juego: Ollama y Whisper fuera ──────────────────────────────────────

@pytest.fixture
def juego(qapp, tmp_path, monkeypatch, whisper):
    from nucleo import datos
    from nucleo.config import Config
    from test_modo_juego_qt import DetectorFalso
    from ui.escritorio import ServiciosEscritorio
    from ui.modo_juego_qt import ControlModoJuego
    descargas = []

    class AI:
        def descargar_modelo(self):
            descargas.append(threading.current_thread() is threading.main_thread())
            return True

    url = {"v": "http://localhost:11434"}
    monkeypatch.setattr(datos, "ollama_url", lambda: url["v"])
    hechos = []

    def montar(proveedor="local", mc=None, pensar=False):
        cfg = Config(str(tmp_path / f"config{len(hechos)}.json"))
        cfg.set("minecraft", "pensar_en_juego", pensar)
        esc = ServiciosEscritorio(cfg, ai=AI(), bridge=types.SimpleNamespace(_provider_web=proveedor))
        esc.obtener = lambda n: mc if n == "minecraft" else None
        det = DetectorFalso()
        ctl = ControlModoJuego(esc, cfg, detector=det, recortar=lambda: (0.0, 0.0),
                               prioridad=lambda baja: None, intervalo_ms=10_000)
        hechos.append((esc, ctl))
        det.juego = True
        ctl._tic()
        assert ctl.activo()
        return ctl

    yield types.SimpleNamespace(montar=montar, descargas=descargas, url=url, V=whisper)
    for esc, ctl in hechos:
        ctl.detener()
        esc.cerrar()


def test_juego_descarga_ollama_local_en_un_hilo(juego):
    juego.montar("local")
    assert esperar(lambda: juego.descargas) and juego.descargas == [False]


@pytest.mark.parametrize("caso", ["nube", "remoto", "minecraft_piensa"])
def test_juego_no_descarga_ollama(juego, caso):
    bot = types.SimpleNamespace(_bot_vivo=lambda: True)
    if caso == "nube":
        juego.montar("cloud")
    elif caso == "remoto":
        juego.url["v"] = "http://192.168.1.50:11434"
        juego.montar("local")
    else:
        juego.montar("local", mc=bot, pensar=True)
    time.sleep(0.15)
    assert juego.descargas == []


def test_juego_descarga_si_el_bot_no_piensa(juego):
    juego.montar("local", mc=types.SimpleNamespace(_bot_vivo=lambda: False), pensar=True)
    assert esperar(lambda: juego.descargas)


def test_juego_suelta_whisper_salvo_dictando(juego):
    V = juego.V
    _cargar(V)
    V.ocupar()
    juego.montar("cloud")
    assert V.modelo_en_memoria()
    V.desocupar()
    juego.montar("cloud")
    assert not V.modelo_en_memoria()


def test_proveedor_activo_y_ollama_local(qapp):
    from PyQt6.QtCore import QObject
    from ui.escritorio import ServiciosEscritorio
    from ui.modo_juego_qt import ollama_es_local, proveedor_activo
    assert proveedor_activo(ServiciosEscritorio(bridge=types.SimpleNamespace(_provider_web="local"))) == "ollama"
    assert proveedor_activo(ServiciosEscritorio(bridge=types.SimpleNamespace(_provider_web="compat"))) == "compat"
    dueno = QObject()
    dueno.current_provider = "ollama"                    # la ventana nativa
    assert proveedor_activo(ServiciosEscritorio(parent=dueno)) == "ollama"
    for url, local in (("http://localhost:11434", True), ("http://127.0.0.1:11434/", True),
                       ("http://[::1]:11434", True), ("http://192.168.1.200:11434", False),
                       ("https://ollama.ejemplo.com", False), ("", False)):
        assert ollama_es_local(url) is local, url


# ── 8. La carpeta de modelos 3D, con su ruta de verdad ─────────────────────────

def test_textos_de_la_carpeta_vrm_con_la_ruta_real(puente):
    from nucleo import vrm
    r = json.loads(puente.personaje_vrm("Lune", "no_existe.vrm"))
    assert r["ok"] is False and str(vrm.CARPETA) in r["error"] and "modelo_vrm/" not in r["error"]
    assert json.loads(puente.vrm_modelos())["carpeta"] == str(vrm.CARPETA)
    src = (RAIZ / "ui" / "web_bridge.py").read_text("utf-8")
    for linea in src.splitlines():                       # lo que ve el usuario (avisos, errores)
        if "aviso.emit(" in linea or '"error"' in linea or "error = " in linea:
            assert "modelo_vrm/" not in linea, linea


def test_jsx_usa_la_carpeta_que_manda_el_backend():
    kit = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
    panels = (kit / "panels.jsx").read_text("utf-8")
    assert "vrm.carpeta" in panels and "en modelo_vrm/:" not in panels
    bib = (kit / "extra" / "vrm_biblioteca.jsx").read_text("utf-8")
    assert "bib.carpeta" in bib
    for viejo in ("<b>modelo_vrm/</b>", "a la carpeta modelo_vrm/."):
        assert viejo not in bib, viejo
