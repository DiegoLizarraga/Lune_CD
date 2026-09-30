"""
Integración de los cortes 9 y 10 (reproductor de bailes MMD/VRMA y Minecraft): las clases
DE VERDAD cumplen lo que las otras les llaman.

- Asistentes (ui/companion.CompanionFlotante, ui/avatar_overlay.AvatarOverlay): lo que les
  piden ControlMMD (mmd, bailar, pulso, despertar) y ControlMinecraft (decir_reaccion). Los
  sprites NO tienen `mmd` (su camino es la canción por el Mezclador + bailar/pulso).
- ControlMMD y ControlMinecraft: lo que llaman ui/montaje_escenario, ui/puente_escenario (y a
  través de él extra/bailes_mmd.jsx y extra/minecraft.jsx), ui/panel_escenario_nativo,
  ui/montaje_ocio y las herramientas del modelo.
- BailesTerminal y MinecraftTerminal: lo que usa patata.py.
- El montaje de verdad (montar_escritorio → montar_escenario) con los controladores de verdad
  y dobles (tests/escenario_falso_c910.py): acciones con handler, herramientas en el
  ToolManager, «conecta el bot de Minecraft» → Llamada → Ejecutor (pide permiso) → el bot
  arranca; desmontar lo quita todo y para el bot.
- `pensando` con varias fuentes (BusEstado.pensar): el chat de la ventana pausa el modelo del
  bot y la asistente que acaba de comentar no se lo quita.
- Catálogo, config, .gitignore, la plantilla de datos, la CSP de las páginas y la detección
  de pedidos: imperativos claros sí; preguntas, negaciones, pasado y frases sobre el tema, no.
Offscreen; nada de node, red, registro de Windows ni audio.
"""
import copy
import inspect
import json
import os
import re
import sys
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

from PyQt6.QtCore import QMetaMethod  # noqa: E402

import escenario_falso_c910 as ef  # noqa: E402
from nucleo.config import Config  # noqa: E402
from ocio_falso_c56 import admite  # noqa: E402

JSX = RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "extra"
ACCIONES = ("bailes", "minecraft", "minecraft_bot")
HERRAMIENTAS = ("listar_bailes", "minecraft_estado", "minecraft_orden", "minecraft_bot")


def _metodo(cls, nombre):
    f = inspect.getattr_static(cls, nombre, None)
    assert callable(f), f"{cls.__name__}.{nombre} no existe"
    return f


def _propiedad(cls, nombre) -> bool:
    return isinstance(inspect.getattr_static(cls, nombre, None), property)


def _senales(cls, *nombres):
    for n in nombres:
        s = getattr(cls, n, None)
        assert s is not None and type(s).__name__ == "pyqtSignal", f"{cls.__name__}.{n}"


def _llamados(ruta: Path, patron: str) -> set:
    return set(re.findall(patron, ruta.read_text(encoding="utf-8")))


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)

    def feature(self, n, d=True):
        return d


# ═══ Asistentes ═══════════════════════════════════════════════════════════════════

def test_companion_cumple_lo_que_le_piden_el_reproductor_y_minecraft():
    C = pytest.importorskip("ui.companion").CompanionFlotante
    for orden, datos in (("cargar", {"id": "0" * 12}), ("pausa", {"on": True}), ("parar", None),
                         ("volumen", {"volumen": 0.5}), ("offset", {"offsetMs": 20}), ("en_sitio", {"enSitio": True}),
                         ("bucle", {"bucle": False})):
        assert admite(_metodo(C, "mmd"), None, orden, datos), orden
    assert admite(_metodo(C, "mmd"), None, "parar")
    assert _propiedad(C, "mmd_activo")
    assert admite(_metodo(C, "decir_reaccion"), None, "¡Logro!", "happy", 8000)
    assert admite(_metodo(C, "decir_reaccion"), None, "Hola")
    assert admite(_metodo(C, "bailar"), None, True, {"estilo": "pop"}) and admite(_metodo(C, "bailar"), None, False)
    assert admite(_metodo(C, "pulso"), None, 120.0, 0.5, 0.7)
    assert admite(_metodo(C, "despertar"), None)


def test_sprites_bailan_y_reaccionan_sin_mmd():
    from ui.avatar_overlay import AvatarOverlay as A
    assert admite(_metodo(A, "decir_reaccion"), None, "¡Logro!", "happy", 8000)
    assert admite(_metodo(A, "bailar"), None, True, {"estilo": "pop"})
    assert admite(_metodo(A, "pulso"), None, 120.0, 0.5, 0.7)
    assert admite(_metodo(A, "despertar"), None)
    assert getattr(A, "mmd", None) is None          # sprites: canción por el Mezclador + bailar/pulso


# ═══ Controladores ═══════════════════════════════════════════════════════════════

def test_control_mmd_cumple_lo_que_llaman_montaje_puente_panel_ocio_y_herramientas():
    from ui.mmd_qt import ControlMMD as M
    # Fábrica por defecto de ui/montaje_escenario y el contrato de ServiciosEscritorio.
    assert admite(M.__init__, None, None, None, anfitrion=None, en_ui=None, parent=None)
    for n, a in (("iniciar", ()), ("detener", ()), ("set_asistente", (None,)), ("ceder", (None,)),
                 ("reanudar", (None,)), ("evento_asistente", ("mmd", {})), ("recargar_config", ())):
        assert admite(_metodo(M, n), None, *a), f"ControlMMD.{n}"
    # Lo que llaman el puente y el panel (por nombre en su código) existe.
    nombres = (_llamados(RAIZ / "ui" / "puente_escenario.py", r'llamar\(self\._mmd, "([a-z_]+)"')
               | _llamados(RAIZ / "ui" / "panel_escenario_nativo.py", r'_llamar\(self\.mmd, "([a-z_]+)"'))
    assert {"reproducir", "pausa", "parar", "lista", "estado", "refrescar", "quitar"} <= nombres
    for n in nombres | {"siguiente", "anterior", "favorito", "desactivar", "volumen", "set_al_terminar",
                        "set_en_el_sitio", "importar_dialogo", "pedir_vista", "herramientas",
                        "reproducir_por_texto"}:
        _metodo(M, n)
    # Firmas exactas de lo que se les pasa.
    assert admite(M.reproducir, None, None, origen="usuario") and admite(M.reproducir, None, "a" * 12)
    assert admite(M.pausa, None) and admite(M.pausa, None, True) and admite(M.lista, None, "texto")
    assert admite(M.guardar_meta, None, "a" * 12, {"titulo": "x"}) and admite(M.favorito, None, "a" * 12, True)
    assert admite(M.desactivar, None, "a" * 12, False) and admite(M.importar_dialogo, None, None)
    assert admite(M.volumen, None, 0.5) and admite(M.set_al_terminar, None, "parar")
    assert admite(M.set_en_el_sitio, None, True) and admite(M.reproducir_por_texto, None, "Alfa")
    assert _propiedad(M, "activo")                     # montaje_ocio: «bailar» lo para si suena
    _senales(M, "estado_cambio", "biblioteca_cambio", "importado", "vista_pedida")


def test_control_minecraft_cumple_lo_que_llaman_montaje_puente_panel_y_herramientas():
    from ui.minecraft_qt import ControlMinecraft as C
    assert admite(C.__init__, None, None, None, anfitrion=None, voice=None, en_ui=None, parent=None)
    for n, a in (("iniciar", ()), ("detener", ()), ("set_asistente", (None,)), ("recargar_config", ())):
        assert admite(_metodo(C, n), None, *a), f"ControlMinecraft.{n}"
    nombres = (_llamados(RAIZ / "ui" / "puente_escenario.py", r'llamar\(self\._mc, "([a-z_]+)"')
               | _llamados(RAIZ / "ui" / "panel_escenario_nativo.py", r'_llamar\(self\.minecraft, "([a-z_]+)"'))
    assert {"conectar_bot", "desconectar_bot", "instalar_bot", "orden", "decir"} <= nombres
    for n in nombres | {"alternar_reacciones", "alternar_bot", "estado", "requisitos", "herramientas"}:
        _metodo(C, n)
    assert admite(C.orden, None, "sígueme", origen="modelo") and admite(C.decir, None, "hola")
    assert admite(C.eventos_recientes, None) and admite(C.eventos_recientes, None, 50)
    for p in ("reaccionando", "bot_conectado"):
        assert _propiedad(C, p), p
    _senales(C, "estado_cambio", "evento", "chat", "log_bot")


def _qt_de(obj):
    mo = obj.metaObject()
    ranuras, senales = set(), set()
    for i in range(mo.methodCount()):
        m = mo.method(i)
        nombre = bytes(m.name()).decode()
        if m.methodType() == QMetaMethod.MethodType.Slot:
            ranuras.add(nombre)
        elif m.methodType() == QMetaMethod.MethodType.Signal:
            senales.add(nombre)
    return ranuras, senales


def test_el_puente_escenario_tiene_las_ranuras_y_senales_que_usan_los_jsx(qapp):
    from ui.puente_escenario import PuenteEscenario, registrar_puente_escenario
    p = PuenteEscenario(None)
    ranuras, senales = _qt_de(p)
    pedidas, escuchadas = set(), set()
    for nombre in ("bailes_mmd.jsx", "minecraft.jsx"):
        texto = (JSX / nombre).read_text(encoding="utf-8")
        pedidas |= set(re.findall(r"\bpedir\('([a-z_]+)'", texto))
        escuchadas |= set(re.findall(r"\bconectar\('([a-z_]+)'", texto))
    assert {"bailes_lista", "mmd_reproducir", "mmd_pausa", "mc_estado_json", "mc_bot_instalar", "mc_orden"} <= pedidas
    assert {"mmd_estado", "bailes_cambio", "mc_estado", "mc_chat"} <= escuchadas
    assert pedidas <= ranuras, f"los jsx llaman a ranuras que PuenteEscenario no tiene: {pedidas - ranuras}"
    assert escuchadas <= senales, f"los jsx escuchan señales que no existen: {escuchadas - senales}"
    assert "vista_pedida" in senales                                   # app.jsx → lune-vista
    # Lo que llama web_shell (antes de setUrl, enlazar tarde, cerrar una vez).
    assert admite(registrar_puente_escenario, None, None, None, ventana=None)
    assert admite(PuenteEscenario.enlazar, None, None) and admite(PuenteEscenario.cerrar, None)
    p.cerrar()
    html = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "index.html").read_text(encoding="utf-8")
    assert "channel.objects.escenario" in html


def test_montaje_panel_y_escritorio_firmas():
    from ui.montaje_escenario import ServiciosEscenario, montar_escenario
    from ui.montaje_escritorio import ServiciosCorte4
    from ui.panel_escenario_nativo import PanelEscenarioNativo
    assert {"mmd", "minecraft", "en_ui"} <= set(ServiciosEscenario.__dataclass_fields__)
    assert "escenario" in ServiciosCorte4.__dataclass_fields__
    assert admite(montar_escenario, None, None, voice=None, fabricas=None)
    assert ServiciosEscenario.detener is ServiciosEscenario.desmontar
    assert admite(PanelEscenarioNativo.__init__, None, None, None, retardo_ms=300, datos=None, rutas_log=None)
    assert admite(PanelEscenarioNativo.enlazar, None, None) and admite(PanelEscenarioNativo.guardar_ya, None)
    _senales(PanelEscenarioNativo, "cambiado")
    # montar_escritorio llama a montar_escenario con su fábrica (y False = sin él).
    fuente = inspect.getsource(__import__("ui.montaje_escritorio", fromlist=["x"]).montar_escritorio)
    assert 'fab.get("escenario")' in fuente and "montar_escenario(s, config, voice=voice" in fuente


def test_terminales_cumplen_lo_que_usa_patata():
    from servicios import bailes_terminal as bt
    from servicios import minecraft_terminal as mt
    B, M = bt.BailesTerminal, mt.MinecraftTerminal
    assert admite(B.__init__, None, None, None, colores={}, en_juego=lambda: False, baile=None)
    for n, a in (("iniciar", ()), ("detener", ()), ("comando", ("/bailes",)), ("registrar_herramientas", (None,)),
                 ("bailar_pedido", ({"cancion": "x"},)), ("parar_pedido", ())):
        assert admite(_metodo(B, n), None, *a), f"BailesTerminal.{n}"
    assert _propiedad(B, "activo")
    assert admite(M.__init__, None, None, None, voice=None, colores={}, en_juego=lambda: False,
                  pensando=lambda: False)
    for n, a in (("iniciar", ()), ("detener", ()), ("comando", ("/mc",)), ("registrar_herramientas", (None,)),
                 ("alternar_reacciones", ()), ("conectar_bot", ()), ("desconectar_bot", ())):
        assert admite(_metodo(M, n), None, *a), f"MinecraftTerminal.{n}"
    assert _propiedad(M, "reaccionando") and _propiedad(M, "bot_conectado")
    assert bt.AYUDA.startswith("/bailes") and mt.AYUDA.startswith("/mc")


# ═══ El montaje de verdad ═══════════════════════════════════════════════════════

@pytest.fixture
def montaje(qapp, tmp_path):
    import test_montaje_escritorio as tme
    from servicios.tools import ToolManager
    from ui.escritorio import ServiciosEscritorio
    from ui.montaje_escritorio import montar_escritorio
    reg = ef.Registro()
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tm = ToolManager()
    esc.conectar_herramientas(tm)
    esc.iniciar()
    fab_esc = dict(ef.fabricas_escenario(reg, tmp_path), en_ui=lambda: (lambda fn, espera_s=5.0: fn()))
    fab = {"tema": lambda c, p: tme.TemaFalso(c, p), "juego": tme.JuegoFalso, "gestor_atajos": tme.GestorFalso(),
           "tray": tme.TrayFalso, "autoinicio": tme.AutoinicioFalso(), "sonar": lambda n: None,
           "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": False,
           "escenario": fab_esc}
    anf = tme.AnfitrionFalso(modo="normal")
    s = montar_escritorio(esc, anf, cfg, fabricas=fab)
    s.reg, s.cfg, s.esc, s.tm, s.anf, s.dir = reg, cfg, esc, tm, anf, tmp_path
    yield s
    s.desmontar()
    esc.cerrar()


def test_montaje_real_registra_todo_y_desmontar_lo_quita_y_para_el_bot(montaje):
    from ui.minecraft_qt import ControlMinecraft
    from ui.mmd_qt import ControlMMD
    from ui.montaje_escenario import ServiciosEscenario
    s, reg = montaje, montaje.reg
    e = s.escenario
    assert isinstance(e, ServiciosEscenario)
    assert isinstance(e.mmd, ControlMMD) and isinstance(e.minecraft, ControlMinecraft)
    assert list(s.esc.controladores())[-2:] == ["mmd", "minecraft"]
    for id_ in ACCIONES:
        assert s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS:
        assert s.tm.tiene_handler(h), h
    assert reg.mmds_vivos() == [e.mmd] and reg.mcs_vivos() == [e.minecraft]
    assert (s.dir / "bailes" / "LEEME.txt").is_file()                   # la carpeta de bailes, en tmp
    # «Mis bailes» (web): la ventana y la vista «bailes».
    vistas = []
    e.mmd.vista_pedida.connect(vistas.append)
    assert s.despachador.ejecutar("bailes") and vistas == ["bailes"] and ("mostrar",) in s.anf.diario
    # «Bot de Minecraft» (bandeja/radial): conecta sin instalar nada; ✔ = conectado.
    assert s.despachador.ejecutar("minecraft_bot")
    p = reg.procesos[-1]
    assert p.vivo and len(p.arranques) == 1 and p.instalaciones == 0
    assert p.arranques[0]["dueno"] == ef.DUENO and p.arranques[0]["nick"] == "Lune"

    s.desmontar()
    for id_ in ACCIONES:
        assert not s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS:
        assert not s.tm.tiene_handler(h), h
    assert not {"mmd", "minecraft"} & set(s.esc.controladores())
    assert reg.mmds_vivos() == [] and reg.mcs_vivos() == [] and reg.nodes_vivos() == []
    assert e.desmontado
    s.desmontar()                                                              # idempotente


def test_listar_bailes_por_el_ejecutor_con_la_biblioteca_de_verdad(montaje):
    from lune_core.acciones import Llamada, USUARIO
    from servicios.tools import ctx_acciones
    ej = montaje.tm.crear_ejecutor(audit_path=None)
    resultados = []
    for modo in ("normal", "patata", "vrm"):
        ej.ejecutar_llamadas([Llamada("listar_bailes", {}, origen=USUARIO)], USUARIO,
                             ctx_acciones(None, "", modo), resultados.append)
        assert resultados[-1].ok and "«Alfa»" in resultados[-1].mensaje and "«Beta»" in resultados[-1].mensaje


def test_conecta_el_bot_de_minecraft_llamada_por_el_ejecutor_con_permiso(montaje):
    from lune_core.acciones import USUARIO
    from servicios.tools import ctx_acciones
    s, reg = montaje, montaje.reg
    llamadas = s.tm.detectar_llamadas("Lune, conecta el bot de Minecraft")
    assert [(ll.herramienta, ll.args, ll.origen, ll.directa) for ll in llamadas] == [
        ("minecraft_bot", {"accion": "conectar"}, USUARIO, True)]
    assert s.tm.detectar_llamadas("¿cómo conecto el bot?") == []
    preguntas = []
    ej = s.tm.crear_ejecutor(lambda pend, responder: preguntas.append((pend, responder)), audit_path=None)
    resultados = []
    ej.ejecutar_llamadas(llamadas, USUARIO, ctx_acciones(None, "", "normal"), resultados.append)
    p = reg.procesos[-1]
    assert len(preguntas) == 1 and preguntas[0][0]["herramienta"] == "minecraft_bot" and not p.vivo
    preguntas[0][1](True)                                                  # «Sí»
    assert p.vivo and len(p.arranques) == 1 and p.instalaciones == 0
    assert resultados and resultados[-1].ok and "Conectando el bot" in resultados[-1].mensaje
    # «desconecta el bot de Minecraft»: sin permiso.
    ej.ejecutar_llamadas(s.tm.detectar_llamadas("desconecta el bot de minecraft"), USUARIO,
                         ctx_acciones(None, "", "normal"), resultados.append)
    assert len(preguntas) == 1 and resultados[-1].ok
    assert _esperar(lambda: not p.vivo)


def _esperar(cond, t=3.0):
    import time
    from PyQt6.QtWidgets import QApplication
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


class AsistenteVRM:
    render = "vrm"

    def __init__(self):
        self.ordenes = []

    def mmd(self, orden, datos=None):
        self.ordenes.append((orden, datos))
        return True

    def despertar(self):
        return True

    def isVisible(self):
        return True


def test_ponme_el_baile_de_alfa_llega_al_reproductor_de_verdad(montaje):
    from nucleo import baile as nb
    s = montaje
    ll = s.tm.detectar_llamadas("ponme el baile de Alfa")
    assert [(x.herramienta, x.args) for x in ll] == [("asistente_bailar", {"segundos": 30, "cancion": "Alfa"})]
    m = AsistenteVRM()
    s.esc.set_asistente(m)
    r = nb.herramienta_bailar(ll[0].args, {"mmd": s.escenario.mmd, "baile": None})
    assert isinstance(r, str) and "Alfa" in r
    cargas = [d for o, d in m.ordenes if o == "cargar"]
    assert len(cargas) == 1 and cargas[0]["titulo"] == "Alfa" and cargas[0]["tipo"] == "vmd"
    assert s.esc.estado.actual().bailando == "mmd"
    s.escenario.mmd.parar()
    s.esc.set_asistente(None)


def test_pensando_del_chat_pausa_el_modelo_del_bot_y_no_lo_pisa_la_asistente(montaje):
    from nucleo.estado_asistente import PENSANDO_CHAT
    s, reg = montaje, montaje.reg
    ok, _ = s.escenario.minecraft.conectar_bot()
    p = reg.procesos[-1]
    assert ok and p.vivo
    bus = s.esc.estado
    bus.pensar(PENSANDO_CHAT, True)                                            # la ventana espera al modelo
    assert _esperar(lambda: ("llm", True) in p.pausas)
    bus.actualizar(pensando=True)                                              # la asistente comenta la pantalla
    bus.actualizar(pensando=False)                                             # …y acaba
    assert bus.actual().pensando is True and p.pausas.count(("llm", False)) == 0
    bus.pensar(PENSANDO_CHAT, False)
    assert bus.actual().pensando is False
    assert _esperar(lambda: p.pausas[-1] == ("llm", False))


# ═══ Bus, cambio de interfaz y el bot ════════════════════════════════════════════

def test_bus_pensar_con_varias_fuentes():
    from nucleo.estado_asistente import PENSANDO_CHAT, BusEstado, EstadoAsistente
    bus = BusEstado()
    vistos = []
    bus.suscribir(lambda est, cambios: vistos.append(cambios.get("pensando")))
    assert bus.pensar(PENSANDO_CHAT, True) is True and bus.actual().pensando
    assert bus.actualizar(pensando=True) is False                              # ya pensaba: sin aviso
    assert bus.pensar(PENSANDO_CHAT, False) is False and bus.actual().pensando  # la asistente sigue
    assert bus.actualizar(pensando=False) is True and not bus.actual().pensando
    assert vistos == [(False, True), (True, False)]
    assert BusEstado(EstadoAsistente(pensando=True)).actualizar(pensando=False) is True


def test_quitar_la_asistente_apaga_solo_su_pensando(qapp):
    from nucleo.estado_asistente import PENSANDO_CHAT
    from ui.escritorio import ServiciosEscritorio
    esc = ServiciosEscritorio(ConfigFalsa())
    m = AsistenteVRM()
    esc.set_asistente(m)
    esc.estado.actualizar(pensando=True)                                       # comentando la pantalla
    esc.set_asistente(None)                                                      # se cierra a medias
    assert esc.estado.actual().pensando is False
    esc.estado.pensar(PENSANDO_CHAT, True)
    esc.set_asistente(m)
    esc.set_asistente(None)
    assert esc.estado.actual().pensando is True                                # el chat sigue
    esc.cerrar()


def test_bot_minecraft_de_y_reconectar_sin_instalar():
    from ui.cambio_interfaz import bot_minecraft_de, reconectar_bot_minecraft

    class Mc:
        def __init__(self, instalado=True):
            self.proceso = ef.ProcesoFalso(instalado=instalado)
            self.bot_conectado = False
            self.conectados = 0

        def conectar_bot(self):
            self.conectados += 1
            if not self.proceso.instalado():
                return False, "Instala el bot en Ajustes → Minecraft (descarga ~400 MB)."
            self.proceso.vivo = True
            return True, "Conectando…"
    s = types.SimpleNamespace(escenario=types.SimpleNamespace(minecraft=Mc()))
    assert bot_minecraft_de(None) is False and bot_minecraft_de(types.SimpleNamespace()) is False
    assert bot_minecraft_de(s) is False
    s.escenario.minecraft.proceso.vivo = True                                  # conectándose
    assert bot_minecraft_de(s) is True
    s.escenario.minecraft.proceso.vivo = False
    s.escenario.minecraft.bot_conectado = True
    assert bot_minecraft_de(s) is True
    assert reconectar_bot_minecraft(s) == (True, "") and s.escenario.minecraft.conectados == 0
    nuevo = types.SimpleNamespace(escenario=types.SimpleNamespace(minecraft=Mc(instalado=False)))
    ok, texto = reconectar_bot_minecraft(nuevo)
    assert ok is False and "Instala" in texto and nuevo.escenario.minecraft.proceso.instalaciones == 0
    assert reconectar_bot_minecraft(types.SimpleNamespace(escenario=None))[0] is False


# ═══ Catálogo, config, plantilla, .gitignore y CSP ══════════════════════════════

def test_catalogo_de_los_cortes_9_y_10():
    import importlib
    from lune_core import catalogo_herramientas as C
    lb = C.CATALOGO["listar_bailes"]
    assert lb.modos == C.TODOS and lb.riesgo.name == "LECTURA" and not lb.requiere_aprobacion
    assert set(lb.args) == {"texto"} and lb.args["texto"].maxlen == 60 and lb.args["texto"].recortar
    for n in ("asistente_bailar", "parar_baile"):
        assert C.CATALOGO[n].disponible_en("patata"), n
        assert C.CATALOGO[n].disponible_en("normal") and C.CATALOGO[n].disponible_en("vrm"), n
    assert "cancion" in C.CATALOGO["asistente_bailar"].args
    for nombre in ("listar_bailes", "asistente_bailar", "parar_baile", "minecraft_estado", "minecraft_orden",
                   "minecraft_bot"):
        mod, fn = C.CATALOGO[nombre].handler.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(mod), fn)), nombre
    assert C.aprobacion_dinamica("minecraft_bot", {}, {"accion": "conectar"}) is True
    assert C.aprobacion_dinamica("minecraft_bot", {}, {"accion": "desconectar"}) is False
    assert C.CATALOGO["minecraft_orden"].requiere_aprobacion


def test_config_por_defecto_de_los_cortes_9_y_10():
    D = Config.DEFAULT_CONFIG
    assert D["baile"]["al_terminar"] == "parar"
    mc = D["minecraft"]
    assert (mc["decir_en_juego"], mc["resumen_al_salir"], mc["pensar_en_juego"], mc["reaccionar_otros"]) == (
        True, True, False, False)
    assert mc["reaccionar"] is False and mc["udp_mate_engine"] is False and mc["comentar_con_ia"] is False
    fuente = (RAIZ / "nucleo" / "config.py").read_text(encoding="utf-8")
    for clave in ("udp_mate_engine", "comentar_con_ia"):
        linea = next(l for l in fuente.splitlines() if f'"{clave}"' in l)
        assert "reservada" in linea, clave
    # Lo que leen el puente y el panel por defecto es lo mismo.
    from ui.puente_escenario import CONFIG_MC_DEFECTO
    for k, v in CONFIG_MC_DEFECTO.items():
        assert mc[k] == v, k


def test_gitignore_y_plantilla_de_datos():
    gi = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "bailes/" in gi and "cache/" in gi and "node_modules/" in gi
    d = json.loads((RAIZ / "datos.example.json").read_text(encoding="utf-8"))
    nota = d["minecraft"]["_nota"]
    assert "online-mode=false" in nota and "Abrir en LAN" in nota and "visor" in nota
    assert "frases_minecraft" in d["_nota"]
    assert "frases_minecraft" in (RAIZ / "nucleo" / "personajes.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("pagina", ["companion_vrm.html", "companion.html"])
def test_la_csp_de_las_paginas_solo_limita_las_conexiones(pagina):
    """connect-src 'self' blob: data: (fetch/XHR al servidor local y texturas blob:/data: de
    GLTFLoader). Nada de script-src/default-src/img-src/media-src/style-src/worker-src: los
    módulos del importmap, el import() perezoso, el <audio> de /bailes/, los estilos en línea y
    los workers siguen como sin CSP."""
    html = (RAIZ / "ui_web" / pagina).read_text(encoding="utf-8")
    metas = re.findall(r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]*)"', html)
    assert metas == ["connect-src 'self' blob: data:"]
    assert html.index("Content-Security-Policy") < html.index("<script")


# ═══ Detección de pedidos ═══════════════════════════════════════════════════════

@pytest.mark.parametrize("texto, esperado", [
    ("conecta el bot de Minecraft", ("minecraft_bot", {"accion": "conectar"})),
    ("Lune, desconecta el bot de minecraft porfa", ("minecraft_bot", {"accion": "desconectar"})),
    ("¡Conecta tu bot de Minecraft!", ("minecraft_bot", {"accion": "conectar"})),
    ("oye, desconecta el bot del minecraft", ("minecraft_bot", {"accion": "desconectar"})),
    ("ponme el baile de Senbonzakura", ("asistente_bailar", {"segundos": 30, "cancion": "Senbonzakura"})),
    ("Lune, pon el baile de Caramelldansen porfa", ("asistente_bailar", {"segundos": 30, "cancion": "Caramelldansen"})),
    ("baila «Senbonzakura»", ("asistente_bailar", {"segundos": 30, "cancion": "Senbonzakura"})),
    ('baila "Mr. Taxi"', ("asistente_bailar", {"segundos": 30, "cancion": "Mr. Taxi"})),
    ("pon la canción «Gangnam Style»", ("asistente_bailar", {"segundos": 30, "cancion": "Gangnam Style"})),
    # sin comillas, «pon la canción X» solo si X es un baile de la biblioteca (BM5; tests/test_tools.py)
    ("oye, ponme la canción «Senbonzakura»!", ("asistente_bailar", {"segundos": 30, "cancion": "Senbonzakura"})),
    ("Ponme el baile de Canción Rosa.", ("asistente_bailar", {"segundos": 30, "cancion": "Canción Rosa"})),
    ("para el baile", ("parar_baile", {})),
    ("ya quita el baile, Lune", ("parar_baile", {})),
    ("baila", ("asistente_bailar", {"segundos": 30})),                     # lo de antes sigue igual
])
def test_detectar_ordenes_de_bailes_y_minecraft(texto, esperado):
    from lune_core.acciones import USUARIO
    from servicios.tools import ToolManager
    ll = ToolManager().detectar_llamadas(texto)
    assert [(x.herramienta, x.args, x.origen, x.directa, x.error) for x in ll] == [
        (esperado[0], esperado[1], USUARIO, True, None)]


@pytest.mark.parametrize("texto", [
    # preguntas
    "¿cómo conecto el bot?", "¿conectas el bot de minecraft?", "conecta el bot de minecraft?",
    "¿conecta el bot de minecraft?", "¿puedes conectar el bot de minecraft?", "¿me pones el baile de Senbonzakura?",
    "ponme el baile de Senbonzakura?", "pon la canción?", "¿paras el baile?", "¿baila?",
    # negaciones
    "no conectes el bot de minecraft", "no, desconecta el bot de minecraft", "no me pongas el baile de Senbonzakura",
    # pasado
    "conecté el bot de minecraft", "ayer conecté el bot de minecraft", "me pusiste el baile de Senbonzakura",
    # frases sobre el tema, otra cosa o en la duda (lo decide el modelo)
    "el bot de minecraft se desconecta solo", "conecta el bot de minecraft a mi servidor", "conecta el bot",
    "desconecta el wifi", "conecta el bot de telegram", "quiero conectar el bot de minecraft",
    "el baile de Senbonzakura es genial", "pon el volumen", "ponme música",
    "para el baile de mañana necesito un vestido", "baila Senbonzakura", "baila muy bien", "baila conmigo",
    "pon la canción de nuevo", "pon la canción de Gangnam Style", "ponme el baile de Senbonzakura y dime algo",
    "oye, ponme la canción Senbonzakura!", "pon la canción más alta",      # sin biblioteca: el modelo
    "ponme el baile de otra vez", "pon el baile de Senbonzakura para mañana", "baila «»", "pon el baile de x",
    "instala el bot de minecraft",
])
def test_lo_que_no_es_una_orden_lo_decide_el_modelo(texto, monkeypatch):
    from nucleo import bailes as nbl
    from servicios.tools import ToolManager
    monkeypatch.setattr(nbl, "_COMPARTIDA", None)          # sin biblioteca (no la de bailes/ real)
    assert ToolManager().detectar_llamadas(texto) == [], texto
