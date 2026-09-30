"""
Integración final de los cortes 5 y 6 en las ventanas y en patata.

Web: `VentanaWeb.__init__` de verdad con Chromium sustituido (el arnés de
tests/test_anfitriones_corte4.py) → los objetos `alarmas` y `musica` del canal están
antes de setUrl, se enlazan con los controladores de verdad (tests/ocio_falso_c56.py)
al montar, «alarma» navega a la vista de alarmas y salir desmonta una vez.
Cambio de interfaz en caliente (GestorInterfaz web → nativa → web): nunca dos
detectores de música, dos programadores de alarmas ni dos dueños del mutex.
Nativa: el ocio va con el corte 4, el tile ALARMAS abre el editor y el baile pinta la
carita y «♪ BAILANDO». Ajustes nativos: el panel de ocio recibe los servicios y
«Guardar» escribe lo pendiente. Chat: «avísame en 5 minutos» (web, nativa y patata)
sale como Llamada por el Ejecutor sin pasar por la memoria; desde Telegram, con
origen remoto. Patata: alarmas, baile y salvapantallas sin Qt, comandos, /ayuda y
capas del título.
"""
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("PyQt6.QtWidgets")
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
except ImportError:
    pass

from PyQt6.QtWidgets import QLabel  # noqa: E402

import ocio_falso_c56 as of  # noqa: E402
import test_anfitriones_corte4 as c4  # noqa: E402
from test_anfitriones_corte4 import ajustes, entorno, sistema  # noqa: E402,F401  (fixtures)
from nucleo.config import Config  # noqa: E402

CANAL_C56 = ["alarmas", "escenario", "escritorio", "lune", "musica", "tareas", "vida"]   # «vida»: 7/8; «escenario»: 9/10; «tareas»: 10.9
HERRAMIENTAS = ("temporizador", "alarma", "cancelar_alarma", "listar_alarmas",
                "asistente_bailar", "parar_baile", "asistente_pantalla_grande")


@pytest.fixture
def ocio(entorno, monkeypatch, tmp_path):
    """El arnés del corte 4 con los controladores de ocio de verdad (dobles del sistema)."""
    reg = of.Registro(tmp_path / "ocio")
    reg.carpeta.mkdir()
    fab = dict(c4.fabricas(), ocio=of.fabricas_ocio(reg))
    monkeypatch.setattr(entorno.ws.VentanaWeb, "FABRICAS_C4", fab)
    monkeypatch.setattr(entorno.main.LuneCDWindow, "FABRICAS_C4", fab)
    contador = {"desmontar": 0}
    from ui.montaje_ocio import ServiciosOcio
    real = ServiciosOcio.desmontar

    def desmontar(self):
        if not self.desmontado:
            contador["desmontar"] += 1
        return real(self)
    monkeypatch.setattr(ServiciosOcio, "desmontar", desmontar)
    entorno.reg, entorno.cuenta = reg, contador
    return entorno


# ═══ Web ══════════════════════════════════════════════════════════════════════

def test_web_registra_los_puentes_de_ocio_antes_de_cargar_y_los_enlaza(ocio, sistema):
    v = ocio.web()
    assert v.web.objetos_al_cargar == CANAL_C56                        # window.luneAlarmas / luneMusica
    s = v._servicios_c4
    o = s.ocio
    assert o is not None and o.alarmas is ocio.reg.alarmas[-1] and o.grande.escritorio is v.bridge.escritorio
    po = v._puentes_ocio
    assert po.alarmas._alarmas is o.alarmas and po.alarmas._grande is o.grande
    assert po.musica._baile is o.baile
    for h in HERRAMIENTAS:
        assert v.bridge.tools.tiene_handler(h), h                      # el ToolManager del puente
    assert len(ocio.reg.detectores_vivos) == 1 and len(ocio.reg.alarmas_en_marcha) == 1
    # «alarma» (radial, bandeja, CommandMenu) en la web: la vista de alarmas de la página.
    vistas = []
    v._puente_esc.navegar.connect(vistas.append)
    assert s.despachador.ejecutar("alarma") and vistas == ["alarmas"]
    # Lo que pide la página llega a los controladores de verdad.
    r = json.loads(po.alarmas.temporizador_crear(json.dumps({"h": 0, "m": 2, "s": 0, "texto": "té"})))
    assert r["ok"], r
    assert [(t.duracion_s, t.texto) for t in o.alarmas.almacen.temporizadores()] == [(120, "té")]
    assert json.loads(po.musica.estado_json())["bailando"] is False


def test_web_salir_desmonta_el_ocio_una_sola_vez(ocio, sistema):
    v = ocio.web()
    canal, o = v._canal, v._servicios_c4.ocio
    o.alarmas._tic()
    assert ocio.reg.dueno is o.alarmas._mutex
    v.salir_de_verdad()
    v.bridge.cerrar_escritorio()
    assert ocio.cuenta["desmontar"] == 1 and o.desmontado
    assert ocio.reg.detectores_vivos == [] and ocio.reg.alarmas_en_marcha == [] and ocio.reg.dueno is None
    assert "alarmas" not in canal.registrados and "musica" not in canal.registrados
    assert v._puentes_ocio is None
    v._liberar_todo()
    assert ocio.cuenta["desmontar"] == 1


def test_relevo_en_caliente_un_solo_detector_programador_y_dueno(ocio, sistema, qapp):
    from ui.cambio_interfaz import GestorInterfaz

    def fabrica(modo):
        return ocio.web(diferir=True) if modo == "web" else ocio.nativa()
    g = GestorInterfaz(fabrica, guardar_modo=lambda m: None, animar=lambda v, ms, fin: fin(),
                       fundido_ms=0, tope_carga_ms=10)
    reg = ocio.reg
    web = ocio.web()
    g.adoptar(web)

    def comprobar(ventana, ocio_de):
        o = ocio_de(ventana)
        assert o is not None and not o.desmontado
        assert reg.detectores_vivos == [o.baile.detector]
        assert reg.alarmas_en_marcha == [o.alarmas]
        o.alarmas._tic()
        assert reg.dueno is o.alarmas._mutex
        for otro in reg.alarmas:
            if otro is not o.alarmas:
                otro._tic()                                            # los viejos, parados: nada
        assert reg.dueno is o.alarmas._mutex
    comprobar(web, lambda w: w._servicios_c4.ocio)
    assert g.cambiar("nativo") is True
    nat = g.ventana
    comprobar(nat, lambda w: w._servicios_c4.ocio)
    assert web._servicios_c4 is None and "alarmas" not in web._canal.registrados
    assert g.cambiar("web") is True
    assert c4._esperar(qapp, lambda: g.modo == "web" and not g.cambiando)
    otra = g.ventana
    assert otra.web.objetos_al_cargar == CANAL_C56
    comprobar(otra, lambda w: w._servicios_c4.ocio)
    assert otra._puentes_ocio.alarmas._alarmas is otra._servicios_c4.ocio.alarmas
    assert ocio.cuenta["desmontar"] == 2                                # la web y la nativa, una vez cada una
    assert sistema.max_iconos == 1 and sistema.choques == []


def test_web_diferida_registra_los_puentes_pero_monta_al_final(ocio, sistema):
    vieja = ocio.web()
    nueva = ocio.web(diferir=True)
    assert nueva.web.objetos_al_cargar == CANAL_C56
    assert nueva._servicios_c4 is None and nueva._puentes_ocio.alarmas._alarmas is None
    assert len(ocio.reg.detectores_vivos) == 1                          # solo el de la vieja
    vieja.cerrar_para_cambio()
    assert ocio.reg.detectores_vivos == []
    nueva.iniciar_servicios({})
    assert nueva._puentes_ocio.alarmas._alarmas is nueva._servicios_c4.ocio.alarmas
    assert len(ocio.reg.detectores_vivos) == 1


class _Acciones:
    def __init__(self):
        self.ejecutadas, self.ejecutor = [], None

    def ejecutar(self, llamadas, origen, ctx):
        self.ejecutadas.append((llamadas, origen, ctx))

    def pendientes(self):
        return []

    def cerrar(self):
        pass


class _Memoria:
    def __init__(self):
        self.vistos = []

    def procesar_mensaje_usuario(self, t):
        self.vistos.append(t)
        return "✎ Anotado" if t.lower().startswith(("recuerda", "recuérdame")) else None

    def obtener_contexto_para_prompt(self):
        return ""


def test_web_chat_avisame_sale_como_llamada_sin_memoria(ocio, sistema):
    from lune_core.acciones import USUARIO
    v = ocio.web()
    b = v.bridge
    b.memoria, b.acciones = _Memoria(), _Acciones()
    assert b._enviar("recuérdame que a las 5 de la tarde tengo cita", b._provider_web) is True
    llamadas, origen, _ctx = b.acciones.ejecutadas[-1]
    assert origen == USUARIO and [(x.herramienta, x.args["hora"], x.directa) for x in llamadas] == [
        ("alarma", "17:00", True)]
    assert b.memoria.vistos == []                                      # antes que la memoria
    # Sin hora ni duración: sigue siendo un recuerdo.
    b._enviar("recuerda que mi cumple es el 5", b._provider_web)
    assert b.memoria.vistos == ["recuerda que mi cumple es el 5"] and len(b.acciones.ejecutadas) == 1


def test_web_orden_de_telegram_avisame_va_con_origen_remoto(ocio, sistema, monkeypatch):
    import ui.web_bridge as wb
    from lune_core.acciones import REMOTO
    v = ocio.web()
    b = v.bridge
    b.acciones = _Acciones()
    remotas = []
    monkeypatch.setattr(wb, "ordenes_activas", lambda cfg: True)
    b._ejecutar_remoto = lambda llamadas, ctx, oid: remotas.append((llamadas, dict(ctx), oid))
    b._responder_telegram = lambda oid, texto: True
    b._orden_remota("7", "avísame en 5 minutos")
    assert len(remotas) == 1
    llamadas, ctx, oid = remotas[0]
    assert oid == "7" and ctx["origen"] == REMOTO and [x.herramienta for x in llamadas] == ["temporizador"]
    assert v._servicios_c4.ocio.alarmas.almacen.temporizadores() == []   # nada sin aprobación


# ═══ Nativa ═══════════════════════════════════════════════════════════════════

def test_nativa_monta_ocio_tile_alarmas_y_baile_en_la_carita(ocio, sistema):
    panel = c4.PanelFalso()
    yo = ocio.nativa(panel=panel)
    yo.iniciar_servicios({})
    s = yo._servicios_c4
    o = s.ocio
    assert panel.recibidos == [s] and o is not None
    assert {"grande", "alarmas", "baile"} <= set(yo.escritorio.controladores())
    # Tile ALARMAS → despachador «alarma» → el editor (nativa: sin navegar).
    abiertos = []
    o.alarmas.abrir_dialogo = lambda parent=None: abiertos.append(1)
    yo._abrir_alarmas()
    assert abiertos == [1]
    # Baile → carita contenta y «♪ BAILANDO»; al parar, LISTO.
    caras = []
    yo.status_label, yo.status_dot = QLabel("LISTO"), QLabel("●")
    yo.lune_face = types.SimpleNamespace(set_state=lambda e, **k: caras.append(e), _player=None,
                                         setVisible=lambda v: None)
    assert o.baile.bailar(20) is True
    assert yo.status_label.text().startswith("♪ BAILANDO") and caras[-1] == "happy"
    o.baile.parar()
    assert yo.status_label.text() == "LISTO" and caras[-1] == "normal"
    # Salir: una vez, y el baile ya no pinta nada.
    yo._quit_real = True
    yo.closeEvent(c4.Evento())
    assert ocio.cuenta["desmontar"] == 1 and ocio.reg.detectores_vivos == []


def test_nativa_chat_avisame_va_al_ejecutor_antes_que_la_memoria(qapp, monkeypatch):
    import main
    from lune_core.acciones import REMOTO, USUARIO
    from servicios.tools import ToolManager
    monkeypatch.setattr(main, "MessageBubble", lambda *a, **k: object())
    ejecutadas, memoria = [], _Memoria()
    texto = {"t": "avísame en 5 minutos que saque la pizza"}
    yo = types.SimpleNamespace(
        _worker_vivo=lambda: False, _set_status=lambda *a: None, current_provider="ollama", _turno={},
        stack=types.SimpleNamespace(setCurrentIndex=lambda i: None), _cancelar_plan=lambda: None,
        voice=types.SimpleNamespace(cancelar=lambda: None),
        messages_layout=types.SimpleNamespace(insertWidget=lambda *a: None, count=lambda: 1),
        input_field=types.SimpleNamespace(text=lambda: texto["t"], clear=lambda: None),
        _adjuntos=[], _refrescar_adjuntos=lambda: None, _guardar_turno=lambda *a, **k: None,
        memoria=memoria, tools=ToolManager(), ai_manager=types.SimpleNamespace(providers={}),
        _modo_acciones=lambda: "normal", _scroll_bottom=lambda: None,
        _ejecutar_acciones=lambda ll, origen, ctx, **kw: ejecutadas.append((ll, origen, dict(ctx), kw)))
    main.LuneCDWindow._send_message(yo)
    ll, origen, ctx, kw = ejecutadas[-1]
    assert origen == USUARIO and kw["directo"] is True and memoria.vistos == []
    assert [(x.herramienta, x.args) for x in ll] == [("temporizador", {"segundos": 300, "texto": "saque la pizza"})]
    # Desde Telegram: origen remoto (pide permiso en el PC).
    main.LuneCDWindow._send_message(yo, texto="pon una alarma a las 7:30", remoto="9")
    ll, origen, ctx, kw = ejecutadas[-1]
    assert origen == REMOTO and ctx["origen"] == REMOTO and kw["remoto"] == "9"
    assert [x.herramienta for x in ll] == ["alarma"] and memoria.vistos == []


# ═══ Ajustes nativos ══════════════════════════════════════════════════════════

class _Ctl:
    def __init__(self, estado=None):
        self.llamadas, self._estado = [], estado or {}

    def recargar_config(self):
        self.llamadas.append("recargar_config")

    def estado(self):
        return dict(self._estado)

    def listar(self):
        return {"alarmas": [], "temporizadores": []}


def test_ajustes_nativos_enlazan_y_guardan_el_panel_de_ocio(ajustes):
    from ui.panel_ocio_nativo import PanelOcioNativo
    caja = {"s": None}
    p = ajustes.crear(lambda: caja["s"])
    panel = p.ocio_panel
    assert isinstance(panel, PanelOcioNativo) and panel.alarmas is None and panel.baile is None
    o = types.SimpleNamespace(alarmas=_Ctl(), grande=_Ctl({"activo": False}), baile=_Ctl({"bailando": False}))
    s = types.SimpleNamespace(ocio=o, atajos=None, _deshacer=[], desmontar=lambda: None)
    caja["s"] = s
    p.usar_servicios(s)
    assert panel.alarmas is o.alarmas and panel.grande is o.grande and panel.baile is o.baile
    # «Guardar configuración» escribe lo pendiente del panel y lo aplica en caliente.
    panel._poner("baile", "baile", "umbral", 0.1)
    panel._poner("alarmas", "alarmas", "volumen", 0.5)
    p._save()
    assert o.baile.llamadas == ["recargar_config"] and o.alarmas.llamadas == ["recargar_config"]
    guardada = Config(str(ajustes.cfg.config_path))
    assert guardada.get("baile", "umbral") == 0.1 and guardada.get("alarmas", "volumen") == 0.5
    # Al desmontar los servicios, el panel los suelta.
    for f in s._deshacer:
        f()
    assert panel.alarmas is None and panel.baile is None and panel.grande is None
    panel._timer.stop()


# ═══ Patata ═══════════════════════════════════════════════════════════════════

class _Pieza:
    """AlarmasTerminal / BaileTerminal / SalvapantallasTerminal de mentira."""

    def __init__(self, nombre, diario, comandos=()):
        self.nombre, self.diario, self.comandos = nombre, diario, set(comandos)

    def iniciar(self):
        self.diario.append((self.nombre, "iniciar"))

    def detener(self):
        self.diario.append((self.nombre, "detener"))

    def comando(self, linea):
        cmd = linea.split()[0].lower()
        if cmd in self.comandos:
            self.diario.append((self.nombre, linea))
            return f"{self.nombre}: {linea}"
        return None

    def registrar_herramientas(self, tools):
        self.diario.append((self.nombre, "herramientas"))


@pytest.fixture
def patata_c56(tmp_path, monkeypatch):
    import patata
    import test_patata as tp
    from nucleo import datos
    from nucleo.consola import ConsolaAsincrona
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    creadas = []

    def crear(**kw):
        entrada, out, api = tp.EntradaBloqueante(), io.StringIO(), tp.ApiFalsa()
        consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=api, ansi=False)
        cfg = Config(str(tmp_path / "config.json"))
        kw.setdefault("memoria", _Memoria())
        p = patata.Patata(color=False, consola=consola, config=cfg, ai=tp.AIFalsa("no debería hablar"),
                          voice=None, audit_path=None, **kw)
        p.entrada, p.out, p.api, p.cfg = entrada, out, api, cfg
        creadas.append(p)
        return p
    yield crear
    for p in creadas:
        p.entrada.put(None)
        p.cerrar()
    datos.invalidar()


def test_patata_comandos_ayuda_arranque_y_cierre_del_ocio(patata_c56):
    from servicios.tools import ToolManager
    diario = []
    p = patata_c56(tools=ToolManager(),
                   alarmas=_Pieza("alarmas", diario, ("/alarma", "/alarmas", "/timer", "/timers", "/apagar")),
                   baile=_Pieza("baile", diario, ("/bailar", "/parar")),
                   salvapantallas=_Pieza("salva", diario))
    assert ("alarmas", "herramientas") in diario                          # registrar_herramientas(tools)
    assert p.comando("/alarma 07:30 lmxjv gimnasio") is False and ("alarmas", "/alarma 07:30 lmxjv gimnasio") in diario
    assert "alarmas: /timer 10m" in (p.comando("/timer 10m") or p.out.getvalue())
    p.comando("/bailar 20")
    assert ("baile", "/bailar 20") in diario
    antes = len(p.out.getvalue())
    p.comando("/ayuda")
    ayuda = p.out.getvalue()[antes:]
    for c in ("/alarma HH:MM", "/timer 10m", "/borrar_alarma", "/apagar", "/bailar", "/parar", "salvapantallas"):
        assert c in ayuda, c
    # «baila» en el chat → el baile del título (no el Ejecutor, no la IA).
    p.responder("¡baila!")
    assert ("baile", "/bailar") in diario and p.ai.system == ""
    p.responder("para de bailar")
    assert ("baile", "/parar") in diario
    # correr() arranca las tres piezas; cerrar() las para antes que la consola.
    hilo = threading.Thread(target=p.correr, daemon=True)
    hilo.start()
    assert c4._esperar(types.SimpleNamespace(processEvents=lambda: None),
                       lambda: ("salva", "iniciar") in diario, 3.0)
    assert {("alarmas", "iniciar"), ("baile", "iniciar"), ("salva", "iniciar")} <= set(diario)
    p.entrada.put("/salir\n")
    hilo.join(5)
    assert {("alarmas", "detener"), ("baile", "detener"), ("salva", "detener")} <= set(diario)


def test_patata_avisame_llamada_por_el_ejecutor_con_alarmas_de_verdad(patata_c56, tmp_path):
    import test_patata as tp
    from nucleo.alarmas import Almacen
    from servicios.alarmas_patata import AlarmasTerminal
    from servicios.tools import ToolManager
    almacen = Almacen(tmp_path / "alarmas.json")
    reg = of.Registro(tmp_path)
    memoria = _Memoria()
    tm = ToolManager()
    p = patata_c56(tools=tm, memoria=memoria, baile=None, salvapantallas=None, alarmas=None)
    p.alarmas = AlarmasTerminal(p.consola, p.cfg, almacen=almacen, mutex=of.MutexFalso(reg),
                                mezclador=reg.mez, lanzar_sonido=lambda f: f())
    p.alarmas.registrar_herramientas(tm)
    p.responder("avísame en 5 minutos que saque la pizza")
    assert tp.esperar(lambda: [(t.duracion_s, t.texto) for t in almacen.temporizadores()] == [(300, "saque la pizza")])
    assert memoria.vistos == [] and p.ai.system == ""
    assert tp.esperar(lambda: "✓" in p.out.getvalue())
    # /alarma de verdad, y la lista con ids.
    p.comando("/alarma 07:30 lmxjv gimnasio")
    assert [(a.hhmm, a.texto) for a in almacen.alarmas()] == [("07:30", "gimnasio")]
    antes = len(p.out.getvalue())
    p.comando("/alarmas")
    assert "gimnasio" in p.out.getvalue()[antes:]


def test_patata_capas_del_titulo_alarma_juego_baile_salvapantallas(patata_c56):
    from servicios import alarmas_patata, baile_terminal, salvapantallas_terminal
    assert (alarmas_patata.PRIORIDAD_TITULO, baile_terminal.PRIORIDAD_TITULO, salvapantallas_terminal.PRIORIDAD) \
        == (60, 20, 10)
    p = patata_c56(alarmas=None, baile=None, salvapantallas=None)
    con = p.consola
    con.titulo_capa("salvapantallas", "(-_-) zzZ 23:41", 10)
    assert p.api.titulos[-1] == "(-_-) zzZ 23:41"
    con.titulo_capa("baile", "ヽ(^o^)ﾉ ♪ Spotify", 20)
    assert p.api.titulos[-1] == "ヽ(^o^)ﾉ ♪ Spotify"
    p._juego_activo = True
    p._poner_titulo(":D")
    assert p.api.titulos[-1].endswith("· modo juego")                  # el juego (50) tapa baile y salvapantallas
    con.titulo_capa("alarma", "⏰ Pizza", 60)
    assert p.api.titulos[-1] == "⏰ Pizza"                              # la alarma (60), encima de todo
    con.titulo_capa("alarma", None, 60)
    assert p.api.titulos[-1].endswith("· modo juego")
    p._juego_activo = False
    p._poner_titulo()
    assert p.api.titulos[-1] == "ヽ(^o^)ﾉ ♪ Spotify"
    con.titulo_capa("baile", None, 20)
    con.titulo_capa("salvapantallas", None, 10)
    assert p.api.titulos[-1] == "Lune :D · patata"


def test_patata_por_defecto_trae_alarmas_baile_y_salvapantallas(patata_c56, monkeypatch, tmp_path):
    from nucleo import alarmas as al
    from servicios.alarmas_patata import AlarmasTerminal
    from servicios.baile_terminal import BaileTerminal
    from servicios.salvapantallas_terminal import SalvapantallasTerminal
    from servicios.tools import ToolManager
    monkeypatch.setattr(al, "RUTA", tmp_path / "alarmas.json")          # nunca el de verdad
    tm = ToolManager()
    p = patata_c56(tools=tm)
    assert isinstance(p.alarmas, AlarmasTerminal) and isinstance(p.baile, BaileTerminal)
    assert isinstance(p.salvapantallas, SalvapantallasTerminal)
    assert p.alarmas.almacen.ruta == tmp_path / "alarmas.json"
    for h in ("temporizador", "alarma", "cancelar_alarma", "listar_alarmas"):
        assert tm.tiene_handler(h), h


GUION_SIN_QT = r'''
import io, shutil, sys, types
from pathlib import Path
RAIZ = Path({raiz!r}); TMP = Path({tmp!r})
sys.path.insert(0, str(RAIZ))
from nucleo import datos
shutil.copyfile(RAIZ / "datos.example.json", TMP / "datos.json")
datos._PATH = TMP / "datos.json"; datos.invalidar()
import patata
from nucleo.alarmas import Almacen
from nucleo.config import Config
from nucleo.consola import ConsolaAsincrona
from servicios.alarmas_patata import AlarmasTerminal
from servicios.baile_terminal import BaileTerminal
from servicios.salvapantallas_terminal import SalvapantallasTerminal
from servicios.tools import ToolManager

class Api:
    def habilitar_vt(self): return True
    def es_consola_entrada(self): return False
    def titulo(self, t): return True
    def parpadear(self, *a, **k): return True
    def leer_tecla(self): return ""
class Mutex:
    def adquirir(self): return True
    def liberar(self): pass
    es_dueno = True
class Mez:
    def cargar_wav(self, r): return b""
    def reproducir(self, *a, **k): return 1
    def detener(self, s): pass
    def detener_canal(self, c): pass
class Det:
    on_cambio = on_pulso = on_sesiones = None
    def iniciar(self): pass
    def detener(self): pass
    def forzar_pulso(self, on): pass
    def pedir_sondeo(self): pass
    def reanudar_auto(self): pass
    def silenciar_hasta_silencio(self): pass

out = io.StringIO()
consola = ConsolaAsincrona("> ", stdout=out, stdin=io.StringIO(""), api=Api(), ansi=False)
cfg = Config(str(TMP / "config.json"))
almacen = Almacen(TMP / "alarmas.json")
alarmas = AlarmasTerminal(consola, cfg, almacen=almacen, mutex=Mutex(), mezclador=Mez(), lanzar_sonido=lambda f: f())
baile = BaileTerminal(consola, cfg, detector=Det())
salva = SalvapantallasTerminal(consola, cfg)
p = patata.Patata(color=False, consola=consola, config=cfg, ai=types.SimpleNamespace(providers={{}}),
                  memoria=types.SimpleNamespace(procesar_mensaje_usuario=lambda t: None), voice=None,
                  tools=ToolManager(), audit_path=None, juego=None, alarmas=alarmas, baile=baile,
                  salvapantallas=salva)
for linea in ("/alarma 07:30 lmxjv gimnasio", "/timer 10m pizza", "/alarmas", "/timers", "/bailar 5", "/parar",
              "/ayuda"):
    p.comando(linea)
p.responder("avísame en 5 minutos que saque la ropa")
import time
fin = time.monotonic() + 5
while time.monotonic() < fin and len(almacen.temporizadores()) < 2:
    time.sleep(0.02)
p.cerrar()
print("ALARMAS", len(almacen.alarmas()), "TIMERS", len(almacen.temporizadores()))
print("QT" if any(m.startswith("PyQt") for m in sys.modules) else "SIN_QT")
'''


def test_patata_con_alarmas_baile_y_salvapantallas_sin_qt(tmp_path):
    guion = tmp_path / "guion_c56.py"
    guion.write_text(textwrap.dedent(GUION_SIN_QT.format(raiz=str(RAIZ), tmp=str(tmp_path))), encoding="utf-8")
    r = subprocess.run([sys.executable, str(guion)], cwd=str(RAIZ), capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr[-2000:]
    lineas = r.stdout.strip().splitlines()
    assert lineas[-1] == "SIN_QT", r.stdout[-800:]
    assert lineas[-2] == "ALARMAS 1 TIMERS 2", r.stdout[-800:]
