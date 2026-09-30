"""
Tests de ui/montaje_escenario.py (montar_escenario, ServiciosEscenario) con el
ServiciosEscritorio y el Despachador de verdad y fábricas falsas del reproductor de bailes
(agente C, ui/mmd_qt.ControlMMD) y de Minecraft (agente D, ui/minecraft_qt.ControlMinecraft);
al final, con las clases de verdad (biblioteca en una carpeta temporal y un proceso del bot
falso: nada de node ni de red). También el enrutado de «bailar» y «baile_pausa» de
ui/montaje_ocio al reproductor MMD cuando suena. Offscreen.
"""
import copy
import inspect
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from nucleo.acciones_ui import Contexto, Despachador, items_radial  # noqa: E402
from nucleo.config import Config  # noqa: E402
from nucleo.estado_asistente import EstadoAsistente  # noqa: E402
from ui import montaje_escenario as me  # noqa: E402
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from ui.montaje_escenario import ServiciosEscenario, montar_escenario  # noqa: E402
from ui.montaje_ocio import EnHiloQt, montar_ocio  # noqa: E402


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)


class Controlador(QObject):
    """Base de los dobles: anota el ciclo de vida."""

    def __init__(self, nombre, diario, kw):
        super().__init__(kw.get("parent"))
        self.nombre, self.diario, self.kw = nombre, diario, kw
        self.borrado = False

    def iniciar(self):
        self.diario.append((self.nombre, "iniciar"))

    def detener(self):
        self.diario.append((self.nombre, "detener"))

    def set_asistente(self, v):
        self.diario.append((self.nombre, "asistente", v is not None))

    def deleteLater(self):
        self.borrado = True
        super().deleteLater()


class MMDFalso(Controlador):
    """Con las firmas del §1.1 del plan (ControlMMD)."""
    estado_cambio = pyqtSignal(str)
    biblioteca_cambio = pyqtSignal(str)
    importado = pyqtSignal(str)
    vista_pedida = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__("mmd", diario, kw)
        self.activo = False
        self.pausado = False
        self.cedida = False

    def pedir_vista(self):
        self.diario.append(("mmd", "vista"))
        self.vista_pedida.emit("bailes")

    def parar(self):
        self.diario.append(("mmd", "parar"))
        estaba, self.activo = self.activo, False
        return estaba

    def pausa(self, on=None):
        self.diario.append(("mmd", "pausa", on))
        if not self.activo:
            return False
        self.pausado = (not self.pausado) if on is None else bool(on)
        return True

    def estado(self):
        return {"fase": "pausado" if self.pausado else ("sonando" if self.activo else "parado"),
                "pausado": self.activo and (self.pausado or self.cedida), "cedida": self.cedida}

    def herramientas(self):
        return {"listar_bailes": lambda args=None, ctx=None: "Tus bailes: …"}


class MinecraftFalso(Controlador):
    """Con las firmas del §1.2 del plan (ControlMinecraft)."""
    estado_cambio = pyqtSignal(str)
    evento = pyqtSignal(str)
    chat = pyqtSignal(str)
    log_bot = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__("minecraft", diario, kw)
        self.reaccionando = False
        self.bot_conectado = False
        self.instalado = True

    def alternar_reacciones(self):
        self.reaccionando = not self.reaccionando
        self.diario.append(("minecraft", "reacciones", self.reaccionando))
        return self.reaccionando

    def conectar_bot(self):
        self.diario.append(("minecraft", "conectar"))
        if not self.instalado:
            return False, "Instala el bot en Ajustes → Minecraft (descarga ~400 MB)."
        self.bot_conectado = True
        return True, "Conectando el bot a localhost:25565 como Lune…"

    def desconectar_bot(self):
        self.diario.append(("minecraft", "desconectar"))
        estaba, self.bot_conectado = self.bot_conectado, False
        return estaba

    def instalar_bot(self):                              # nunca lo llama el montaje (D3)
        self.diario.append(("minecraft", "INSTALAR"))

    def herramientas(self):
        return {n: (lambda args=None, ctx=None: "ok") for n in ("minecraft_estado", "minecraft_orden", "minecraft_bot")}


class AtajosFalsos:
    def __init__(self):
        self.recargas = 0

    def recargar(self):
        self.recargas += 1


class ToolsFalsas:
    def __init__(self):
        self.h = {}

    def registrar_handler(self, n, fn):
        self.h[n] = fn

    def quitar_handler(self, n):
        self.h.pop(n, None)


class AnfitrionFalso:
    def __init__(self, modo="normal"):
        self.modo = modo
        self.diario = []

    def mostrar_ventana(self):
        self.diario.append("mostrar")

    def abrir_ajustes(self, seccion=""):
        self.diario.append(("ajustes", seccion))

    def aviso(self, texto):
        self.diario.append(("aviso", texto))


def fabricas(diario, **extra):
    f = {
        "mmd": lambda esc, cfg, **kw: MMDFalso(diario, **kw),
        "minecraft": lambda esc, cfg, **kw: MinecraftFalso(diario, **kw),
    }
    f.update(extra)
    return f


def montar(qapp, *, anfitrion=None, iniciado=True, fab=None, diario=None, desp=None, esc=None, cfg=None):
    cfg = cfg or ConfigFalsa()
    esc = esc or ServiciosEscritorio(cfg)
    tools = ToolsFalsas()
    esc.conectar_herramientas(tools)
    if iniciado:
        esc.iniciar()
    avisos = []
    s4 = SimpleNamespace(escritorio=esc, despachador=desp or Despachador(), atajos=AtajosFalsos(),
                         anfitrion=anfitrion or AnfitrionFalso(), avisar=avisos.append, _deshacer=[])
    diario = diario if diario is not None else []
    e = montar_escenario(s4, cfg, voice="voz", fabricas=fab or fabricas(diario))
    return SimpleNamespace(cfg=cfg, esc=esc, s4=s4, e=e, diario=diario, tools=tools, avisos=avisos)


IDS = ("bailes", "minecraft", "minecraft_bot")
HERRAMIENTAS = ("listar_bailes", "minecraft_estado", "minecraft_orden", "minecraft_bot")


def test_controladores_y_actividades_registrados(qapp):
    h = montar(qapp)
    esc, e = h.esc, h.e
    assert isinstance(e, ServiciosEscenario)
    assert esc.obtener("mmd") is e.mmd and esc.obtener("minecraft") is e.minecraft
    assert esc._controlador_de_actividad("mmd") is e.mmd
    # Minecraft no hace ninguna actividad de la tabla: nunca recibe ceder/reanudar
    assert e.minecraft not in [esc._controlador_de_actividad(a) for a in ("juego", "alarma", "grande", "mmd", "baile")]
    assert [x[0] for x in h.diario if x[1] == "iniciar"] == ["mmd", "minecraft"]


def test_inyeccion_de_dependencias(qapp):
    anf = AnfitrionFalso(modo="br")
    h = montar(qapp, anfitrion=anf)
    e = h.e
    assert isinstance(e.en_ui, EnHiloQt)
    for ctl in (e.mmd, e.minecraft):
        assert ctl.kw["en_ui"] is e.en_ui and ctl.kw["parent"] is h.esc and ctl.kw["anfitrion"] is anf
    assert e.minecraft.kw["voice"] == "voz"
    assert "voice" not in e.mmd.kw                           # la firma de C no lo lleva


def test_bailes_en_la_web_ensena_la_ventana_y_pide_la_vista(qapp):
    h = montar(qapp, anfitrion=AnfitrionFalso("normal"))
    vistas = []
    h.e.mmd.vista_pedida.connect(vistas.append)
    assert h.s4.despachador.ejecutar("bailes", origen="bandeja")
    assert h.s4.anfitrion.diario == ["mostrar"] and vistas == ["bailes"]
    assert ("mmd", "vista") in h.diario


def test_bailes_en_la_nativa_abre_ajustes(qapp):
    h = montar(qapp, anfitrion=AnfitrionFalso("br"))
    assert h.s4.despachador.ejecutar("bailes")
    assert h.s4.anfitrion.diario == [("ajustes", "escenario")]
    assert ("mmd", "vista") not in h.diario


def test_minecraft_alterna_las_reacciones_con_su_marcado(qapp):
    h = montar(qapp)
    d, mc = h.s4.despachador, h.e.minecraft
    assert d.marcado("minecraft") is False
    d.ejecutar("minecraft")
    assert mc.reaccionando and d.marcado("minecraft") is True
    assert h.avisos[-1] == "Reacciono a tu partida de Minecraft."
    d.ejecutar("minecraft")
    assert not mc.reaccionando and h.avisos[-1] == "Ya no reacciono a Minecraft."


def test_bot_de_minecraft_conecta_desconecta_y_nunca_instala(qapp):
    h = montar(qapp)
    d, mc = h.s4.despachador, h.e.minecraft
    mc.instalado = False
    d.ejecutar("minecraft_bot")
    assert h.avisos[-1].startswith("Instala el bot en Ajustes") and d.marcado("minecraft_bot") is False
    mc.instalado = True
    d.ejecutar("minecraft_bot")
    assert mc.bot_conectado and d.marcado("minecraft_bot") is True and h.avisos[-1].startswith("Conectando el bot")
    d.ejecutar("minecraft_bot")
    assert not mc.bot_conectado and h.avisos[-1] == "Desconecto el bot de Minecraft."
    assert ("minecraft", "INSTALAR") not in h.diario, "D3: el bot solo se instala con el botón de Ajustes"
    # con alternar_bot (el de D) manda él
    mc.alternar_bot = lambda: (h.diario.append(("minecraft", "alternar")) or (True, "Conectando…"))
    d.ejecutar("minecraft_bot")
    assert h.diario[-1] == ("minecraft", "alternar") and h.avisos[-1] == "Conectando…"


def test_etiquetas_en_el_radial_con_los_handlers(qapp):
    h = montar(qapp)
    d = h.s4.despachador
    est = EstadoAsistente(render="vrm", visible=True)
    ctx = Contexto(modo="normal", render="vrm", asistente_visible=True)
    items = items_radial(d, est, ctx, ["bailes", "minecraft", "minecraft_bot"])
    assert [(i.id, i.etiqueta, i.marcado) for i in items] == [
        ("bailes", "Mis bailes", None), ("minecraft", "Reacciones a Minecraft", False), ("minecraft_bot", "Bot de Minecraft", False)]
    # en pantalla grande no se abre la biblioteca
    grande = EstadoAsistente(render="vrm", visible=True, grande=True)
    assert "bailes" not in [i.id for i in items_radial(d, grande, ctx, ["bailes"])]


def test_herramientas_en_el_escritorio_y_en_el_toolmanager(qapp):
    h = montar(qapp)
    for n in HERRAMIENTAS:
        assert n in h.esc._herramientas and n in h.tools.h, n


def test_atajos_recargados(qapp):
    assert montar(qapp).s4.atajos.recargas == 1


def test_desmontar_idempotente_lo_quita_todo(qapp):
    h = montar(qapp)
    e, esc, d = h.e, h.esc, h.s4.despachador
    assert e.desmontar in h.s4._deshacer
    e.desmontar()
    assert e.desmontado
    for id_ in IDS:
        assert not d.tiene(id_), id_
    for n in HERRAMIENTAS:
        assert n not in esc._herramientas and n not in h.tools.h
    assert esc.obtener("mmd") is None and esc.obtener("minecraft") is None
    assert esc._controlador_de_actividad("mmd") is None
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["minecraft", "mmd"]
    assert h.s4.atajos.recargas == 2
    assert e.mmd.borrado and e.minecraft.borrado
    e.desmontar()
    assert h.s4.atajos.recargas == 2 and [x[0] for x in h.diario if x[1] == "detener"] == ["minecraft", "mmd"]


def test_desmontar_con_el_cambio_de_interfaz(qapp):
    h = montar(qapp)
    for f in reversed(h.s4._deshacer):                    # lo que hace ServiciosCorte4.desmontar
        f()
    assert h.e.desmontado and not h.s4.despachador.tiene("bailes")


def test_desmontar_sin_escritorio_iniciado_detiene_igual(qapp):
    h = montar(qapp, iniciado=False)
    h.e.desmontar()
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["minecraft", "mmd"]


def test_no_quita_un_handler_que_ya_no_es_suyo(qapp):
    h = montar(qapp)
    otro = lambda: None  # noqa: E731
    h.s4.despachador.registrar("minecraft", otro)
    h.e.desmontar()
    assert h.s4.despachador.tiene("minecraft") and not h.s4.despachador.tiene("bailes")


def test_fabricas_false_y_una_pieza_que_falla(qapp):
    diario = []

    def rompe(*a, **k):
        raise RuntimeError("sin node")
    h = montar(qapp, fab=fabricas(diario, minecraft=rompe), diario=diario)
    assert h.e.minecraft is None and h.e.mmd is not None
    d = h.s4.despachador
    assert d.tiene("bailes") and not d.tiene("minecraft") and not d.tiene("minecraft_bot")
    assert "listar_bailes" in h.esc._herramientas and "minecraft_estado" not in h.esc._herramientas
    h.e.desmontar()
    h2 = montar(qapp, fab=fabricas([], mmd=False))
    assert h2.e.mmd is None and h2.e.minecraft is not None
    assert not h2.s4.despachador.tiene("bailes") and h2.s4.despachador.tiene("minecraft_bot")
    h2.e.desmontar()


def test_sin_despachador_ni_escritorio(qapp):
    s4 = SimpleNamespace(escritorio=None, despachador=None, atajos=None, anfitrion=None, _deshacer=[])
    diario = []
    e = montar_escenario(s4, ConfigFalsa(), fabricas=fabricas(diario))
    assert e.mmd is not None and e.desmontar in s4._deshacer
    e.desmontar()
    assert [x[0] for x in diario if x[1] == "detener"] == ["minecraft", "mmd"]


# ── montaje_ocio: «bailar» y «baile_pausa» con el reproductor MMD ─────────────

class BaileFalso(QObject):
    estado_cambio = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__(kw.get("parent"))
        self.diario = diario
        self.bailando = False

    def bailar(self, *a, **k):
        self.diario.append(("baile", "bailar"))
        self.bailando = True
        return True

    def parar(self, **k):
        self.diario.append(("baile", "parar"))
        self.bailando = False
        return True

    def pausa(self):
        self.diario.append(("baile", "pausa"))
        return True


def test_bailar_y_pausar_van_al_reproductor_mmd_si_suena(qapp):
    diario = []
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    desp = Despachador()
    s4 = SimpleNamespace(escritorio=esc, despachador=desp, atajos=AtajosFalsos(), anfitrion=AnfitrionFalso(),
                         avisar=lambda t: None, _deshacer=[])
    ocio = montar_ocio(s4, cfg, fabricas={"grande": lambda *a, **k: None,
                                          "alarmas": lambda *a, **k: None,
                                          "baile": lambda esc_, cfg_, **kw: BaileFalso(diario, **kw)})
    e = montar_escenario(s4, cfg, fabricas=fabricas(diario))
    m, b = e.mmd, ocio.baile
    # sin baile MMD: el procedural de siempre
    assert desp.marcado("bailar") is False and desp.marcado("baile_pausa") is False
    desp.ejecutar("bailar")
    assert diario[-1] == ("baile", "bailar") and desp.marcado("bailar") is True
    desp.ejecutar("baile_pausa")
    assert diario[-1] == ("baile", "pausa")
    desp.ejecutar("bailar")
    assert diario[-1] == ("baile", "parar")
    # con un baile MMD puesto: pausa (alterna) y «bailar» lo para
    m.activo = True
    assert desp.marcado("bailar") is True
    desp.ejecutar("baile_pausa")
    assert diario[-1] == ("mmd", "pausa", None) and m.pausado and desp.marcado("baile_pausa") is True
    est = EstadoAsistente(render="vrm", visible=True, bailando="mmd")
    ctx = Contexto(modo="normal", render="vrm", asistente_visible=True)
    [it] = items_radial(desp, est, ctx, ["baile_pausa"])
    assert it.etiqueta == "Seguir el baile"
    desp.ejecutar("baile_pausa")
    assert not m.pausado and desp.marcado("baile_pausa") is False
    m.cedida = True                                       # pausado por un juego: no es «Seguir»
    assert desp.marcado("baile_pausa") is False
    desp.ejecutar("bailar")
    assert diario[-1] == ("mmd", "parar") and not m.activo
    assert ("baile", "bailar") not in diario[diario.index(("mmd", "pausa", None)):]
    assert not b.bailando
    e.desmontar()
    ocio.desmontar()


# ── Con las clases de verdad (contrato con los agentes C y D) ─────────────────

class ProcesoFalso:
    """lune_core.minecraft_proceso.ProcesoBot sin node: nada se lanza."""

    def __init__(self):
        self.vivo = False
        self.on_evento = self.on_log = self.on_fin = None
        self.arranques, self.paradas, self.instalaciones = [], [], 0

    def requisitos(self, refrescar=False):
        return {"node": "v24.19.0", "node_ok": True, "npm": True, "instalado": True}

    def instalado(self):
        return True

    def instalar(self, cancelar=None):
        self.instalaciones += 1
        return True, "Instalado."

    def arrancar(self, cfg, probar=False):
        self.arranques.append(cfg)
        self.vivo = True
        return True, "Arrancando…"

    def parar(self, espera_s=4.0):
        self.paradas.append(espera_s)
        self.vivo = False

    def orden(self, id_, texto):
        return True

    def decir(self, texto):
        return True

    def pausa_llm(self, on):
        return True

    def pausa_autonomo(self, on):
        return True


def test_las_fabricas_por_defecto_casan_con_las_firmas_de_c_y_d():
    """Sin crear nada (la biblioteca por defecto está en la raíz del repo): la llamada de
    las fábricas por defecto encaja en los constructores de verdad."""
    from ui.minecraft_qt import ControlMinecraft
    from ui.mmd_qt import ControlMMD
    inspect.signature(ControlMMD).bind("esc", "cfg", anfitrion=None, en_ui=None, parent=None)
    inspect.signature(ControlMinecraft).bind("esc", "cfg", anfitrion=None, voice=None, en_ui=None, parent=None)
    assert me.FABRICAS_DEFECTO == {"mmd": me._mmd_defecto, "minecraft": me._minecraft_defecto}
    for nombre in ("iniciar", "detener", "set_asistente", "ceder", "reanudar", "evento_asistente", "pedir_vista",
                   "herramientas", "parar", "pausa", "estado"):
        assert callable(getattr(ControlMMD, nombre, None)), nombre
    assert isinstance(ControlMMD.activo, property)
    for nombre in ("iniciar", "detener", "set_asistente", "alternar_reacciones", "conectar_bot", "desconectar_bot",
                   "herramientas", "estado", "instalar_bot"):
        assert callable(getattr(ControlMinecraft, nombre, None)), nombre
    assert isinstance(ControlMinecraft.reaccionando, property) and isinstance(ControlMinecraft.bot_conectado, property)


def test_con_las_clases_de_verdad(qapp, tmp_path):
    from bailes_falsos import hacer_baile
    from nucleo.bailes import Biblioteca
    from ui.minecraft_qt import ControlMinecraft
    from ui.mmd_qt import ControlMMD
    cfg = ConfigFalsa()
    hacer_baile(tmp_path / "bailes", "Senbonzakura", meta={"titulo": "Senbonzakura", "autor_cancion": "Kurousa-P"})
    proceso = ProcesoFalso()
    fab = {
        "mmd": lambda esc, c, **kw: ControlMMD(esc, c, biblioteca=Biblioteca(tmp_path / "bailes", tmp_path / "cache",
                                                                             config=c), hilo=False, **kw),
        "minecraft": lambda esc, c, **kw: ControlMinecraft(esc, c, proceso=proceso, rutas=lambda: [],
                                                           datos_mc=lambda: {"host": "localhost", "port": 25565,
                                                                             "dueno": "Diego_01"},
                                                           personaje=lambda: {"nombre": "Lune"},
                                                           llm=lambda: {"proveedor": "ollama"},
                                                           hilo=lambda fn, *a, **k: fn(), **kw),
    }
    h = montar(qapp, anfitrion=AnfitrionFalso("normal"), fab=fab, cfg=cfg)
    e, d = h.e, h.s4.despachador
    try:
        assert isinstance(e.mmd, ControlMMD) and isinstance(e.minecraft, ControlMinecraft)
        assert h.esc._controlador_de_actividad("mmd") is e.mmd
        assert (tmp_path / "bailes" / "LEEME.txt").is_file(), "iniciar crea la carpeta con su LEEME"
        for id_ in IDS:
            assert d.tiene(id_), id_
        assert set(HERRAMIENTAS) <= set(h.tools.h)
        vistas = []
        e.mmd.vista_pedida.connect(vistas.append)
        d.ejecutar("bailes")
        assert vistas == ["bailes"] and h.s4.anfitrion.diario == ["mostrar"]
        assert [b["titulo"] for b in e.mmd.lista("senbon")] == ["Senbonzakura"]
        assert d.marcado("minecraft") is False
        d.ejecutar("minecraft")
        assert cfg.get("minecraft", "reaccionar") is True and d.marcado("minecraft") is True
        d.ejecutar("minecraft_bot")
        assert proceso.arranques and proceso.arranques[-1]["host"] == "localhost"
        assert proceso.instalaciones == 0 and h.avisos[-1].startswith("Conectando el bot")
        d.ejecutar("minecraft_bot")                               # vivo → lo desconecta
        assert proceso.paradas and h.avisos[-1] == "Desconecto el bot."
        proceso.paradas.clear()
        proceso.vivo = True                                       # para comprobar que desmontar lo para
    finally:
        e.desmontar()
    assert h.esc.obtener("mmd") is None and not d.tiene("minecraft_bot")
    assert proceso.paradas, "al desmontar se para el bot (no queda node huérfano)"
