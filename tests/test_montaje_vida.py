"""
Tests de ui/montaje_vida.py (montar_vida, ServiciosVida) con el ServiciosEscritorio y el
Despachador de verdad y fábricas falsas de las piezas de los agentes A (sentarse), C
(comida) y D (Discord); al final, una vez con las clases de verdad. Offscreen.
"""
import copy
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
from ui.escritorio import ServiciosEscritorio  # noqa: E402
from ui.montaje_ocio import EnHiloQt  # noqa: E402
from ui.montaje_vida import ServiciosVida, hwnd_principal_de, montar_vida  # noqa: E402


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


class AsientoFalso(Controlador):
    cambio = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__("asiento", diario, kw)
        self.sentada_en = ""

    def sentar(self, sitio):
        self.diario.append(("asiento", "sentar", sitio))
        if sitio == "ventana":
            return False, "Sentarme en ventanas está desactivado (Ajustes → Sentarse)."
        self.sentada_en = sitio
        return True, "Me senté en la barra de tareas."

    def bajar(self, motivo="usuario"):
        self.diario.append(("asiento", "bajar"))
        estaba, self.sentada_en = bool(self.sentada_en), ""
        return estaba

    def herramientas(self):
        return {"asistente_sentarse": lambda args=None, ctx=None: "ok"}


class ComidaFalsa(Controlador):
    cambio = pyqtSignal(str)
    comida_web = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__("comida", diario, kw)
        self.activa = None
        self.ultima = ""

    def alternar(self, id_):
        self.diario.append(("comida", "alternar", id_))
        if self.activa and self.activa[0] == id_:
            self.activa = None
            return "guarda"
        accion = "cambia" if self.activa else "aparece"
        self.activa, self.ultima = (id_, "fresa"), id_
        return accion

    def guardar(self, sonido=True):
        self.diario.append(("comida", "guardar"))
        estaba, self.activa = self.activa is not None, None
        return estaba

    def herramientas(self):
        return {"dar_de_comer": lambda args=None, ctx=None: "*glup glup*"}


class DiscordFalso(Controlador):
    estado_cambio = pyqtSignal(str)

    def __init__(self, diario, **kw):
        super().__init__("discord", diario, kw)
        self.activo = False

    def alternar(self):
        self.activo = not self.activo
        self.diario.append(("discord", "alternar"))
        return self.activo


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


class AsistenteFalsa:
    def __init__(self, visible=True):
        self.visible = visible

    def isVisible(self):
        return self.visible


class AnfitrionFalso:
    def __init__(self, modo="normal", hwnd=4242, ventana_visible=True, asistente=None):
        self.modo = modo
        self.diario = []
        self._hwnd = hwnd
        self._ventana_visible = ventana_visible
        self._asistente = asistente

    def hwnd_principal(self):
        return self._hwnd

    def mostrar_ventana(self):
        self.diario.append("mostrar")
        self._ventana_visible = True

    def ventana_visible(self):
        return self._ventana_visible

    def asistente(self):
        return self._asistente

    def alternar_asistente(self):
        return False

    def aviso(self, texto):
        self.diario.append(("aviso", texto))


def fabricas(diario, **extra):
    f = {
        "asiento": lambda esc, cfg, **kw: AsientoFalso(diario, **kw),
        "comida": lambda esc, cfg, **kw: ComidaFalsa(diario, **kw),
        "discord": lambda esc, cfg, **kw: DiscordFalso(diario, **kw),
    }
    f.update(extra)
    return f


def montar(qapp, *, anfitrion=None, iniciado=True, fab=None, diario=None):
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tools = ToolsFalsas()
    esc.conectar_herramientas(tools)
    if iniciado:
        esc.iniciar()
    avisos = []
    s4 = SimpleNamespace(escritorio=esc, despachador=Despachador(), atajos=AtajosFalsos(),
                         anfitrion=anfitrion or AnfitrionFalso(), avisar=avisos.append, _deshacer=[])
    diario = diario if diario is not None else []
    vida = montar_vida(s4, cfg, voice="voz", fabricas=fab or fabricas(diario))
    return SimpleNamespace(cfg=cfg, esc=esc, s4=s4, vida=vida, diario=diario, tools=tools, avisos=avisos)


IDS = ("sentarse", "bajar", "comer_batido", "comer_pastel", "guardar_comida", "comida", "discord")
HERRAMIENTAS = ("asistente_sentarse", "dar_de_comer")


def test_controladores_y_actividades_registrados(qapp):
    h = montar(qapp)
    esc, v = h.esc, h.vida
    assert isinstance(v, ServiciosVida)
    assert esc.obtener("asiento") is v.asiento
    assert esc.obtener("comida") is v.comida
    assert esc.obtener("discord") is v.discord
    assert esc._controlador_de_actividad("sentada") is v.asiento
    assert esc._controlador_de_actividad("comida") is v.comida
    # Discord no hace ninguna actividad de la tabla: nunca recibe ceder/reanudar
    assert v.discord not in [esc._controlador_de_actividad(a) for a in ("juego", "alarma", "grande", "baile")]
    # arrancaron (el escritorio ya estaba iniciado) en orden: asiento, comida, discord
    assert [x[0] for x in h.diario if x[1] == "iniciar"] == ["asiento", "comida", "discord"]


def test_inyeccion_de_dependencias(qapp):
    h = montar(qapp, anfitrion=AnfitrionFalso(modo="br", hwnd=777))
    v = h.vida
    assert isinstance(v.en_ui, EnHiloQt)
    for ctl in (v.asiento, v.comida):
        assert ctl.kw["en_ui"] is v.en_ui
    for ctl in (v.asiento, v.comida, v.discord):
        assert ctl.kw["parent"] is h.esc
    assert v.asiento.kw["hwnd_principal"]() == 777          # la ventana principal sí es asiento
    assert v.comida.kw["anfitrion"] is h.s4.anfitrion
    assert v.discord.kw["modo"] == "br" and v.discord.kw["nombre_modelo"] is None


def test_hwnd_principal_con_un_anfitrion_de_antes(qapp):
    class Ventana:
        def winId(self):
            return 99

    viejo = SimpleNamespace(modo="normal", ventana=Ventana())
    assert hwnd_principal_de(viejo)() == 99
    nativo = SimpleNamespace(modo="br", win=Ventana())
    assert hwnd_principal_de(nativo)() == 99
    assert hwnd_principal_de(SimpleNamespace(modo="normal"))() == 0

    class Rompe:
        def hwnd_principal(self):
            raise RuntimeError("ya no está")
    assert hwnd_principal_de(Rompe())() == 0


def test_ids_del_despachador_con_handler(qapp):
    h = montar(qapp)
    desp, v = h.s4.despachador, h.vida
    for id_ in IDS:
        assert desp.tiene(id_), id_
    # sentarse → barra por defecto, con el texto de vuelta como aviso; «ventana» por arg
    assert desp.ejecutar("sentarse")
    assert ("asiento", "sentar", "barra") in h.diario and h.avisos == ["Me senté en la barra de tareas."]
    desp.ejecutar("sentarse", "ventana")
    assert h.avisos[-1].startswith("Sentarme en ventanas está desactivado")
    desp.ejecutar("sentarse", "<script>")                  # un arg raro → la barra
    assert h.diario.count(("asiento", "sentar", "barra")) == 2
    desp.ejecutar("bajar")
    assert ("asiento", "bajar") in h.diario
    # comida: aparece, cambia, guarda
    desp.ejecutar("comer_batido")
    assert v.comida.activa == ("batido", "fresa")
    assert desp.marcado("comida") is True
    desp.ejecutar("comer_pastel")
    assert v.comida.activa[0] == "pastel"
    desp.ejecutar("guardar_comida")
    assert v.comida.activa is None and desp.marcado("comida") is False
    desp.ejecutar("comida")                                 # la última que salió
    assert v.comida.activa[0] == "pastel"
    desp.ejecutar("comida")
    assert v.comida.activa is None
    v.comida.ultima = ""
    desp.ejecutar("comida")                                 # nunca salió ninguna → batido
    assert v.comida.activa[0] == "batido"
    # discord: interruptor con su marcado
    assert desp.marcado("discord") is False
    desp.ejecutar("discord")
    assert v.discord.activo and desp.marcado("discord") is True


def test_etiquetas_en_el_radial_con_los_handlers(qapp):
    h = montar(qapp)
    desp = h.s4.despachador
    est = EstadoAsistente(render="vrm", visible=True)
    ctx = Contexto(modo="normal", render="vrm", asistente_visible=True)
    items = items_radial(desp, est, ctx, ["sentarse", "comida", "discord", "bajar"])
    assert [(i.id, i.etiqueta) for i in items] == [("sentarse", "Sentarse en la barra"), ("comida", "Comida"),
                                                   ("discord", "Discord")]
    desp.ejecutar("comida")
    [c] = items_radial(desp, est, ctx, ["comida"])
    assert c.etiqueta == "Guardar la comida"


def test_comida_en_la_web_con_la_ventana_oculta_la_ensena_antes(qapp):
    oculta = AnfitrionFalso(modo="normal", ventana_visible=False)
    h = montar(qapp, anfitrion=oculta)
    h.s4.despachador.ejecutar("comer_batido")
    assert oculta.diario == ["mostrar"]
    h.s4.despachador.ejecutar("comer_batido")               # guardarla no enseña nada
    assert oculta.diario == ["mostrar"]
    # con la asistente flotante a la vista, la comida va al escritorio: no hace falta la ventana
    con_asistente = AnfitrionFalso(modo="normal", ventana_visible=False, asistente=AsistenteFalsa(True))
    h2 = montar(qapp, anfitrion=con_asistente)
    h2.s4.despachador.ejecutar("comer_pastel")
    assert con_asistente.diario == []
    # en la nativa la saca ControlComida (no la ventana)
    nativa = AnfitrionFalso(modo="br", ventana_visible=False)
    h3 = montar(qapp, anfitrion=nativa)
    h3.s4.despachador.ejecutar("comer_pastel")
    assert nativa.diario == []


def test_herramientas_en_el_escritorio_y_en_el_toolmanager(qapp):
    h = montar(qapp)
    for n in HERRAMIENTAS:
        assert n in h.esc._herramientas, n
        assert n in h.tools.h, n


def test_atajos_recargados(qapp):
    h = montar(qapp)
    assert h.s4.atajos.recargas == 1


def test_desmontar_idempotente_lo_quita_todo(qapp):
    h = montar(qapp)
    v, esc, desp = h.vida, h.esc, h.s4.despachador
    assert v.desmontar in h.s4._deshacer
    v.desmontar()
    assert v.desmontado
    for id_ in IDS:
        assert not desp.tiene(id_), id_
    for n in HERRAMIENTAS:
        assert n not in esc._herramientas and n not in h.tools.h
    for n in ("asiento", "comida", "discord"):
        assert esc.obtener(n) is None
    assert esc._controlador_de_actividad("sentada") is None
    assert esc._controlador_de_actividad("comida") is None
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["discord", "comida", "asiento"]
    assert h.s4.atajos.recargas == 2
    assert v.asiento.borrado and v.comida.borrado and v.discord.borrado
    v.desmontar()                                         # otra vez: nada
    assert h.s4.atajos.recargas == 2
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["discord", "comida", "asiento"]


def test_desmontar_con_el_cambio_de_interfaz(qapp):
    h = montar(qapp)
    for f in reversed(h.s4._deshacer):                    # lo que hace ServiciosCorte4.desmontar
        f()
    assert h.vida.desmontado and not h.s4.despachador.tiene("sentarse")


def test_desmontar_sin_escritorio_iniciado_detiene_igual(qapp):
    h = montar(qapp, iniciado=False)
    h.vida.desmontar()
    assert [x[0] for x in h.diario if x[1] == "detener"] == ["discord", "comida", "asiento"]


def test_no_quita_un_handler_que_ya_no_es_suyo(qapp):
    h = montar(qapp)
    otro = lambda: None  # noqa: E731
    h.s4.despachador.registrar("discord", otro)
    h.vida.desmontar()
    assert h.s4.despachador.tiene("discord")
    assert not h.s4.despachador.tiene("sentarse")


def test_llevar_a_la_esquina_la_baja_antes(qapp):
    """Con Lune sentada, colocarla por código (esquina) la baja primero; si no, ControlAsiento
    la volvería a clavar en el borde. De pie, la esquina de siempre. Al desmontar, el original."""
    diario = []
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    esc.iniciar()
    desp = Despachador()
    hechas = []

    def esquina(*, origen=""):
        hechas.append(("esquina", origen))
    desp.registrar("esquina", esquina)                      # lo pone montar_escritorio antes
    s4 = SimpleNamespace(escritorio=esc, despachador=desp, atajos=AtajosFalsos(), anfitrion=AnfitrionFalso(),
                         avisar=lambda t: None, _deshacer=[])
    v = montar_vida(s4, cfg, fabricas=fabricas(diario))
    assert desp.ejecutar("esquina", origen="bandeja")
    assert hechas == [("esquina", "bandeja")] and ("asiento", "bajar") not in diario, "de pie: no se baja"
    desp.ejecutar("sentarse")
    assert v.asiento.sentada_en == "barra"
    assert desp.ejecutar("esquina", origen="radial")
    assert diario[-1] == ("asiento", "bajar") and hechas[-1] == ("esquina", "radial")
    assert v.asiento.sentada_en == ""
    # un fallo del original sigue contando como fallo
    desp_malo = Despachador()
    desp_malo.registrar("esquina", lambda: 1 / 0)
    s4m = SimpleNamespace(escritorio=None, despachador=desp_malo, atajos=None, anfitrion=AnfitrionFalso(), _deshacer=[])
    vm = montar_vida(s4m, cfg, fabricas=fabricas([]))
    assert desp_malo.ejecutar("esquina") is False
    vm.desmontar()
    # al desmontar vuelve el handler de siempre
    v.desmontar()
    assert desp._fns["esquina"] is esquina
    desp.ejecutar("esquina")
    assert hechas[-1] == ("esquina", "")


def test_una_pieza_que_falla_no_tumba_las_demas(qapp):
    diario = []

    def rompe(*a, **k):
        raise RuntimeError("sin ventanas_ajenas")
    h = montar(qapp, fab=fabricas(diario, asiento=rompe), diario=diario)
    assert h.vida.asiento is None
    assert h.vida.comida is not None and h.vida.discord is not None
    desp = h.s4.despachador
    assert not desp.tiene("sentarse") and not desp.tiene("bajar")
    assert desp.tiene("comer_batido") and desp.tiene("discord")
    assert "asistente_sentarse" not in h.esc._herramientas and "dar_de_comer" in h.esc._herramientas
    h.vida.desmontar()


def test_sin_despachador_ni_escritorio(qapp):
    s4 = SimpleNamespace(escritorio=None, despachador=None, atajos=None, anfitrion=None, _deshacer=[])
    diario = []
    v = montar_vida(s4, ConfigFalsa(), fabricas=fabricas(diario))
    assert v.asiento is not None and v.desmontar in s4._deshacer
    v.desmontar()
    assert [x[0] for x in diario if x[1] == "detener"] == ["discord", "comida", "asiento"]


def test_con_las_clases_de_verdad(qapp):
    """Las fábricas por defecto casan con las firmas de A, C y D (sin asistente: nada se mueve)."""
    from ui.asiento_qt import ControlAsiento
    from ui.comida_qt import ControlComida
    from ui.discord_qt import ControlDiscord
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tools = ToolsFalsas()
    esc.conectar_herramientas(tools)
    esc.iniciar()
    avisos = []
    s4 = SimpleNamespace(escritorio=esc, despachador=Despachador(), atajos=AtajosFalsos(),
                         anfitrion=AnfitrionFalso(modo="br"), avisar=avisos.append, _deshacer=[])
    v = montar_vida(s4, cfg)
    try:
        assert isinstance(v.asiento, ControlAsiento)
        assert isinstance(v.comida, ControlComida)
        assert isinstance(v.discord, ControlDiscord)
        assert v.discord.modo == "br"
        for id_ in IDS:
            assert s4.despachador.tiene(id_), id_
        assert set(HERRAMIENTAS) <= set(tools.h)
        # sin la asistente a la vista, sentarse no hace nada y lo dice
        s4.despachador.ejecutar("sentarse")
        assert avisos and "sácame primero" in avisos[-1]
        assert s4.despachador.marcado("comida") is False
        assert s4.despachador.marcado("discord") is False
        assert v.asiento._permitir() == (4242,)
    finally:
        v.desmontar()
    assert esc.obtener("asiento") is None and not s4.despachador.tiene("discord")
