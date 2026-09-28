"""
Integración de los cortes 7 y 8 (sentarse en ventanas y en la barra, comida, Discord y
arranque con Windows): las clases DE VERDAD cumplen lo que las otras les llaman.

- Mascotas (ui/companion.CompanionFlotante, ui/avatar_overlay.AvatarOverlay): lo que les
  piden ControlAsiento, ControlComida y el montaje (`antes_de_colocar`). Los sprites NO
  tienen delegado de arrastre (así ControlAsiento sabe que el arrastre es nativo).
- Controladores: lo que llaman ui/montaje_vida, ui/puente_vida, ui/panel_vida_nativo y
  las herramientas; el puente tiene las ranuras y señales que usa extra/vida.jsx.
- servicios/autoinicio, nucleo/arranque, SistemaTerminal y ComidaTerminal: lo que usan
  main.py, patata.py, el puente y el panel.
- El montaje de verdad (montar_escritorio → montar_vida) con los controladores de verdad y
  dobles del sistema (tests/vida_falsa_c78.py): acciones con handler, las 2 herramientas en
  el ToolManager, «te doy un batido» → Llamada → Ejecutor → reacción con su sonido,
  «siéntate en la barra» → la mascota sentada; desmontar lo quita todo.
- Con Lune sentada, «Llevar a la esquina» (el Despachador y el menú propio de la mascota)
  la baja antes (si no, ControlAsiento la volvería a clavar en el borde).
- Catálogo, config y la detección de pedidos: imperativos claros sí; preguntas,
  negaciones, pasado y frases sobre el tema, no.
Offscreen; nada de Win32 que cambie algo, ni audio, ni Discord, ni el registro.
"""
import copy
import inspect
import os
import re
import sys
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

from nucleo.config import Config  # noqa: E402
from ocio_falso_c56 import admite  # noqa: E402
import vida_falsa_c78 as vf  # noqa: E402
from test_mascota_c78 import config, lune_activa, mascota, web_falso  # noqa: E402,F401  (fixtures)

JSX = RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "extra"
ACCIONES_VIDA = ("sentarse", "bajar", "comer_batido", "comer_pastel", "guardar_comida", "comida", "discord")
HERRAMIENTAS_VIDA = ("mascota_sentarse", "dar_de_comer")


def _propiedad(cls, nombre) -> bool:
    return isinstance(inspect.getattr_static(cls, nombre, None), property)


def _metodo(cls, nombre):
    f = inspect.getattr_static(cls, nombre, None)
    assert callable(f), f"{cls.__name__}.{nombre} no existe"
    return f


def _senales(cls, *nombres):
    for n in nombres:
        s = getattr(cls, n, None)
        assert s is not None and type(s).__name__ == "pyqtSignal", f"{cls.__name__}.{n}"


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)

    def feature(self, n, d=True):
        return d


def _cb(*_a):
    pass


# ═══ Mascotas ═══════════════════════════════════════════════════════════════════

# (método, args, kwargs) tal como los llaman ControlAsiento (ui/asiento_qt.py), ControlComida
# (ui/comida_qt.py) y el montaje (ui/montaje_vida.py, «esquina»).
LLAMADAS_VIDA = [
    ("hwnd", (), {}),
    ("punto_asiento", (_cb,), {}),
    ("asiento", (True, "barra", 0), {"cb": _cb}),
    ("asiento", (True, "ventana", 3), {}),
    ("asiento", (False,), {}),
    ("restaurar_orden_z", (), {}),
    ("cabeza", (_cb,), {}),
    ("comer", ("beber", 2500), {}),
    ("comer", ("comer",), {}),
    ("set_comida_activa", (True,), {}),
    ("llevar_a_esquina", (), {}),
]


def test_companion_cumple_el_contrato_de_sentarse_y_comida():
    C = pytest.importorskip("ui.companion").CompanionFlotante
    for nombre, a, k in LLAMADAS_VIDA + [("set_arrastre_delegado", (None,), {}),
                                         ("set_arrastre_delegado", (lambda: True,), {})]:
        assert admite(_metodo(C, nombre), None, *a, **k), f"CompanionFlotante.{nombre}{a}{k}"
    _senales(C, "arrastre_cambio", "antes_de_colocar", "menu_pedido")
    assert _propiedad(C, "sentada") and _propiedad(C, "comida_activa")
    for n in ("devicePixelRatioF", "isVisible", "windowHandle"):
        assert callable(getattr(C, n)), n


def test_avatar_overlay_cumple_lo_que_aplica_y_su_arrastre_es_nativo():
    from ui.avatar_overlay import AvatarOverlay as A
    for nombre, a, k in LLAMADAS_VIDA:
        assert admite(_metodo(A, nombre), None, *a, **k), f"AvatarOverlay.{nombre}{a}{k}"
    _senales(A, "arrastre_cambio", "antes_de_colocar", "menu_pedido")
    assert _propiedad(A, "sentada")
    # Sin delegado: así ControlAsiento sabe que el arrastre es el del SO (encaja al soltar).
    assert getattr(A, "set_arrastre_delegado", None) is None


# ═══ Controladores, montaje, puente y panel ═══════════════════════════════════════

def test_controladores_cumplen_lo_que_llaman_montaje_puente_panel_y_herramientas():
    from ui.asiento_qt import ControlAsiento as S
    from ui.comida_qt import ControlComida as C
    from ui.discord_qt import ControlDiscord as D
    # Lo que pasan las fábricas por defecto de ui/montaje_vida.py.
    assert admite(S.__init__, None, None, None, hwnd_principal=lambda: 0, en_ui=None, parent=None)
    assert admite(C.__init__, None, None, None, anfitrion=None, en_ui=None, parent=None)
    assert admite(D.__init__, None, None, None, modo="normal", nombre_modelo=None, parent=None)
    # Contrato de controlador de ServiciosEscritorio (ui/escritorio.py).
    for cls in (S, C, D):
        for n, a in (("iniciar", ()), ("detener", ()), ("set_mascota", (None,)), ("recargar_config", ())):
            assert admite(_metodo(cls, n), None, *a), f"{cls.__name__}.{n}"
    for cls in (S, C):                                   # tienen actividades: sentada, comida
        for n in ("ceder", "reanudar"):
            assert admite(_metodo(cls, n), None, None), f"{cls.__name__}.{n}"
        assert admite(_metodo(cls, "herramientas"), None)
    # Sentarse: montaje (sentarse/bajar/esquina), puente, panel, nucleo.asiento.herramienta.
    for n, a in (("sentar", ("barra",)), ("sentar", ("ventana",)), ("bajar", ()), ("bajar", ("usuario",)),
                 ("estado", ())):
        assert admite(_metodo(S, n), None, *a), f"ControlAsiento.{n}{a}"
    assert _propiedad(S, "sentada_en")
    _senales(S, "cambio", "sentada", "levantada")
    # Comida: montaje (comer_*, guardar_comida, comida), puente (acierto_web), herramienta.
    for n, a, k in (("alternar", ("batido",), {}), ("guardar", (), {}), ("guardar", (), {"sonido": False}),
                    ("acierto_web", ("pastel",), {}), ("comer_directo", ("batido",), {}), ("estado", (), {})):
        assert admite(_metodo(C, n), None, *a, **k), f"ControlComida.{n}{a}"
    for p in ("activa", "ultima", "vista"):
        assert _propiedad(C, p), p
    _senales(C, "cambio", "comida_web")
    # Discord: montaje (discord), puente y panel.
    for n in ("alternar", "estado", "vista_previa"):
        assert admite(_metodo(D, n), None), f"ControlDiscord.{n}"
    assert _propiedad(D, "activo")
    _senales(D, "estado_cambio")


def _qt_de(obj):
    """(ranuras, señales) del QMetaObject de un QObject (lo que ve QWebChannel)."""
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


def test_el_puente_vida_tiene_las_ranuras_y_senales_que_usa_vida_jsx(qapp):
    from ui.puente_vida import PuenteVida, registrar_puente_vida
    p = PuenteVida(None)
    ranuras, senales = _qt_de(p)
    texto = (JSX / "vida.jsx").read_text(encoding="utf-8")
    pedidas = (set(re.findall(r"\bpedir\('([a-z_]+)'", texto))
               | set(re.findall(r"\buseEstado\('([a-z_]+)'", texto))
               | set(re.findall(r"\bguardador\('([a-z_]+)'", texto)))
    escuchadas = (set(re.findall(r"\bconectar\('([a-z_]+)'", texto))
                  | set(re.findall(r"\buseEstado\('[a-z_]+',\s*'([a-z_]+)'", texto)))
    assert {"asiento_estado", "comida_alternar", "comida_evento", "discord_estado", "autoinicio_estado"} <= pedidas
    assert {"comida_web", "asiento_cambio"} <= escuchadas
    assert pedidas <= ranuras, f"vida.jsx llama a ranuras que PuenteVida no tiene: {pedidas - ranuras}"
    assert escuchadas <= senales, f"vida.jsx escucha señales que no existen: {escuchadas - senales}"
    assert admite(PuenteVida.enlazar, None, None) and admite(PuenteVida.cerrar, None)
    assert admite(registrar_puente_vida, None, None, None)
    p.cerrar()
    # index.html expone el objeto del canal como window.luneVida (antes de app.jsx).
    html = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "index.html").read_text(encoding="utf-8")
    assert "channel.objects.vida" in html
    assert html.index('src="extra/vida.jsx"') < html.index('src="app.jsx"')


def test_servicios_vida_montaje_panel_y_anfitriones_firmas():
    from ui.anfitrion_nativo import AnfitrionNativo
    from ui.anfitrion_web import AnfitrionWeb
    from ui.montaje_escritorio import ServiciosCorte4
    from ui.montaje_vida import ServiciosVida, montar_vida
    from ui.panel_vida_nativo import PanelVidaNativo
    assert {"asiento", "comida", "discord", "en_ui"} <= set(ServiciosVida.__dataclass_fields__)
    assert "vida" in ServiciosCorte4.__dataclass_fields__
    assert admite(ServiciosVida.desmontar, None) and ServiciosVida.detener is ServiciosVida.desmontar
    assert admite(montar_vida, None, None, voice=None, fabricas=None)
    assert admite(PanelVidaNativo.__init__, None, None, None, asiento=None, comida=None, discord=None,
                  retardo_ms=300, autoinicio=None)
    assert admite(PanelVidaNativo.enlazar, None, None) and admite(PanelVidaNativo.guardar_ya, None)
    _senales(PanelVidaNativo, "cambiado")
    for A in (AnfitrionWeb, AnfitrionNativo):
        assert admite(_metodo(A, "reaccion"), None, "happy", 2500), A.__name__
        assert admite(_metodo(A, "hwnd_principal"), None), A.__name__
        assert admite(_metodo(A, "aviso"), None, "hola"), A.__name__


def test_arranque_autoinicio_y_terminal_cumplen_lo_que_usan_main_patata_puente_y_panel():
    from nucleo import arranque
    from servicios import autoinicio
    from servicios.comida_terminal import ComidaTerminal
    from servicios.sistema_terminal import SistemaTerminal
    # main.py (_preparar_arranque, _reparar_autoinicio, _guardar_modo_interfaz), patata, panel y puente.
    assert admite(arranque.parsear_args, ["--autoinicio"]) and admite(arranque.plan_arranque, None, None)
    assert admite(arranque.como, None) and admite(arranque.retraso_s, None)
    assert set(arranque.COMOS) == {"bandeja", "mascota", "ventana"}
    plan = arranque.plan_arranque({"sistema": {"autoinicio_como": "mascota", "autoinicio_retraso_s": 7}},
                                  arranque.parsear_args(["--autoinicio"]))
    assert (plan.splash, plan.mostrar_ventana, plan.abrir_mascota, plan.retraso_s, plan.silencioso) == (
        False, False, True, 7, True)
    assert arranque.plan_arranque(None, arranque.parsear_args([])).splash is True
    for fn, a, k in ((autoinicio.reparar, (None, "patata"), {}), (autoinicio.reparar, (None,), {"modo": "web"}),
                     (autoinicio.establecer, (True, "patata"), {}), (autoinicio.estado, ("web",), {}),
                     (autoinicio.activo, (), {})):
        assert admite(fn, *a, **k), fn.__name__
    # patata.py
    assert admite(SistemaTerminal.__init__, None, None, None, en_juego=lambda: False, pensando=lambda: False,
                  autoinicio=None)
    for n in ("iniciar", "detener", "actualizar", "alternar_discord"):
        assert admite(_metodo(SistemaTerminal, n), None), n
    assert admite(SistemaTerminal.comando, None, "/discord estado") and _propiedad(SistemaTerminal, "discord_activo")
    assert admite(ComidaTerminal.__init__, None, None, None, colores={}, en_juego=lambda: False,
                  nombre=lambda: "Lune")
    for n, a in (("iniciar", ()), ("detener", ()), ("comando", ("/comer",)), ("registrar_herramientas", (None,))):
        assert admite(_metodo(ComidaTerminal, n), None, *a), n


# ═══ El montaje de verdad ═══════════════════════════════════════════════════════

@pytest.fixture
def montaje(qapp):
    import test_montaje_escritorio as tme
    from servicios.tools import ToolManager
    from ui.escritorio import ServiciosEscritorio
    from ui.montaje_escritorio import montar_escritorio
    reg = vf.Registro()
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tm = ToolManager()
    esc.conectar_herramientas(tm)
    esc.iniciar()
    gestor = tme.GestorFalso()
    fab = {"tema": lambda c, p: tme.TemaFalso(c, p), "juego": tme.JuegoFalso, "gestor_atajos": gestor,
           "tray": tme.TrayFalso, "autoinicio": tme.AutoinicioFalso(), "sonar": lambda n: None,
           "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": False, "vida": vf.fabricas_vida(reg),
           "escenario": False}
    anf = tme.AnfitrionFalso(modo="normal")
    s = montar_escritorio(esc, anf, cfg, fabricas=fab)
    s.reg, s.cfg, s.esc, s.tm, s.gestor, s.anf = reg, cfg, esc, tm, gestor, anf
    yield s
    s.desmontar()
    esc.cerrar()


def test_montaje_real_registra_todo_y_desmontar_lo_quita(montaje):
    from ui.asiento_qt import ControlAsiento
    from ui.comida_qt import ControlComida
    from ui.discord_qt import ControlDiscord
    from ui.montaje_vida import ServiciosVida
    s, reg = montaje, montaje.reg
    v = s.vida
    assert isinstance(v, ServiciosVida)
    assert isinstance(v.asiento, ControlAsiento) and isinstance(v.comida, ControlComida)
    assert isinstance(v.discord, ControlDiscord)
    assert list(s.esc.controladores())[-3:] == ["asiento", "comida", "discord"]
    for id_ in ACCIONES_VIDA:
        assert s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS_VIDA:
        assert s.tm.tiene_handler(h), h
    # Arrancaron con el escritorio (uno de cada).
    assert reg.asientos_vivos() == [v.asiento] and reg.discords_vivos() == [v.discord]
    # «discord» del radial/bandeja: la presencia se enciende (y queda en config).
    assert s.despachador.ejecutar("discord")
    assert s.cfg.get("discord", "activo") is True and reg.presencias_publicando() == [reg.presencias[-1]]

    s.desmontar()
    for id_ in ACCIONES_VIDA:
        assert not s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS_VIDA:
        assert not s.tm.tiene_handler(h), h
    assert not {"asiento", "comida", "discord"} & set(s.esc.controladores())
    assert reg.asientos_vivos() == [] and reg.discords_vivos() == [] and reg.presencias_publicando() == []
    assert v.desmontado
    s.desmontar()                                                              # idempotente


def test_te_doy_un_batido_llamada_por_el_ejecutor_a_la_comida_de_verdad(montaje):
    from lune_core.acciones import USUARIO
    from servicios.tools import ctx_acciones
    s = montaje
    llamadas = s.tm.detectar_llamadas("Te doy un batido")
    assert [(ll.herramienta, ll.args, ll.origen, ll.directa) for ll in llamadas] == [
        ("dar_de_comer", {"comida": "batido"}, USUARIO, True)]
    assert s.reg.mez.reproducidos == []                                       # detectar no hace nada
    resultados = []
    ej = s.tm.crear_ejecutor(audit_path=None)
    ej.ejecutar_llamadas(llamadas, USUARIO, ctx_acciones(None, "", "normal"), resultados.append)
    assert resultados and resultados[0].ok, resultados
    assert "glup" in resultados[0].mensaje.lower() and "batido" in resultados[0].mensaje
    assert s.reg.mez.reproducidos and all(canal == "sfx" for canal, _ in s.reg.mez.reproducidos)
    # Sin la mascota a la vista, la reacción la pone el anfitrión.
    assert s.esc.estado.actual().comiendo is True


def test_sientate_en_la_barra_llamada_por_el_ejecutor_a_la_mascota(montaje):
    from lune_core.acciones import USUARIO
    from servicios.tools import ctx_acciones
    from test_asiento_qt import MascotaFalsa, PROPIA, RECT_M
    from servicios.win_pantalla import Rect
    s = montaje
    s.reg.win.rects[PROPIA] = Rect(*RECT_M)
    m = MascotaFalsa()
    s.esc.set_mascota(m)
    llamadas = s.tm.detectar_llamadas("oye Lune, siéntate en la barra")
    assert [(ll.herramienta, ll.args) for ll in llamadas] == [("mascota_sentarse", {"sitio": "barra"})]
    ej = s.tm.crear_ejecutor(audit_path=None)
    resultados = []
    # Sin la mascota a la vista (modo «normal»), no: el Ejecutor la rechaza sin tocar nada.
    ej.ejecutar_llamadas(llamadas, USUARIO, ctx_acciones(None, "", "normal"), resultados.append)
    assert resultados[-1].ok is False and m.asientos == []
    # Con ella (sprites o animada: modo «mascota»), se sienta.
    ej.ejecutar_llamadas(llamadas, USUARIO, ctx_acciones(None, "", "mascota"), resultados.append)
    assert resultados[-1].ok, resultados[-1]
    assert m.asientos[-1] == (True, "barra", 0) and s.vida.asiento.sentada_en == "barra"
    assert s.esc.estado.actual().sentada == "barra"
    # «bájate» por el mismo camino.
    ej.ejecutar_llamadas(s.tm.detectar_llamadas("bájate"), USUARIO, ctx_acciones(None, "", "mascota"),
                         resultados.append)
    assert resultados[-1].ok and s.vida.asiento.sentada_en == "" and m.asientos[-1] == (False, "", 0)
    s.esc.set_mascota(None)


# ═══ «Llevar a la esquina» con Lune sentada ═════════════════════════════════════

@pytest.fixture
def sprites(montaje, monkeypatch):
    """La mascota de sprites DE VERDAD (AvatarOverlay, offscreen) en el montaje."""
    from nucleo import personajes
    from servicios.win_pantalla import Rect
    from ui.avatar_overlay import AvatarOverlay
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Lune"})
    ov = AvatarOverlay(config=None)
    ov.show()
    h = ov.hwnd()
    montaje.reg.win.rects[h] = Rect(100, 100, 100 + ov.width(), 100 + ov.height())
    montaje.esc.set_mascota(ov)
    montaje.ov = ov
    yield montaje
    montaje.esc.set_mascota(None)
    ov.close()


def test_el_menu_propio_de_la_mascota_la_baja_antes_de_llevarla_a_la_esquina(sprites):
    s, ov = sprites, sprites.ov
    a = s.vida.asiento
    assert a.sentar("barra")[0] is True
    assert ov.sentada == "barra" and a.sentada_en == "barra"
    levantadas = []
    a.levantada.connect(levantadas.append)
    ov.llevar_a_esquina()                        # lo que hace «Llevar a la esquina» de su bandeja
    assert ov.sentada == "" and a.sentada_en == "" and levantadas == ["usuario"]
    assert s.esc.estado.actual().sentada == ""
    ov.llevar_a_esquina()                        # de pie: nada más que moverla
    assert levantadas == ["usuario"]


def test_la_accion_esquina_del_despachador_tambien_la_baja(sprites):
    s, ov = sprites, sprites.ov
    a = s.vida.asiento
    assert a.sentar("barra")[0] is True and ov.sentada == "barra"
    assert s.despachador.ejecutar("esquina")
    assert ov.sentada == "" and a.sentada_en == ""


def test_llevarla_a_la_esquina_durante_una_cesion_ya_no_la_devuelve(sprites):
    """Revisión 7-10 (SV2): sentada, un baile MMD le quita «sentada» (cedida, de pie); la
    llevas a la esquina por su menú o por el Despachador y, al acabar el baile, volvía a
    cruzar la pantalla hasta la barra."""
    s, ov = sprites, sprites.ov
    a = s.vida.asiento
    for colocar in (ov.llevar_a_esquina, lambda: s.despachador.ejecutar("esquina")):
        assert a.sentar("barra")[0] is True and ov.sentada == "barra"
        assert s.esc.prioridad.iniciar("mmd")
        assert a.cedida and ov.sentada == ""
        colocar()
        assert not a.cedida
        s.esc.prioridad.terminar("mmd")
        assert ov.sentada == "" and a.sentada_en == "" and s.esc.estado.actual().sentada == ""


def test_el_enganche_sigue_a_la_mascota_y_se_suelta_al_desmontar(sprites):
    s, ov = sprites, sprites.ov
    assert ov.receivers(ov.antes_de_colocar) == 1
    s.esc.set_mascota(None)
    assert ov.receivers(ov.antes_de_colocar) == 0
    s.esc.set_mascota(ov)
    assert ov.receivers(ov.antes_de_colocar) == 1
    s.vida.desmontar()
    assert ov.receivers(ov.antes_de_colocar) == 0


def test_la_companion_avisa_antes_de_moverse(mascota):
    """CompanionFlotante: `antes_de_colocar` sale ANTES de moverla a la esquina."""
    c = mascota
    c.move(300, 300)
    vistas = []
    c.antes_de_colocar.connect(lambda: vistas.append((c.x(), c.y())))
    c.llevar_a_esquina()
    assert vistas == [(300, 300)], "avisa antes de moverla"
    assert (c.x(), c.y()) != (300, 300)


# ═══ Catálogo, config y detección ═══════════════════════════════════════════════

def test_catalogo_de_vida_modos_y_handlers_importables():
    import importlib
    from lune_core import catalogo_herramientas as C
    h = C.CATALOGO["mascota_sentarse"]
    assert h.modos == frozenset({"mascota", "vrm"}) and "se apoyan en el borde" in h.descripcion
    assert set(h.args["sitio"].enum) == {"barra", "ventana", "bajar"}
    d = C.CATALOGO["dar_de_comer"]
    assert d.disponible_en("patata") and d.disponible_en("normal") and d.disponible_en("mascota")
    for nombre in HERRAMIENTAS_VIDA:
        mod, fn = C.CATALOGO[nombre].handler.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(mod), fn)), nombre


def test_config_por_defecto_de_los_cortes_7_y_8():
    D = Config.DEFAULT_CONFIG
    assert D["discord"]["client_id"] == "" and D["discord"]["activo"] is False            # D1
    assert D["avatar"]["sentarse_ventanas"] is False and D["avatar"]["sentarse_barra"] is True   # D2
    assert (D["sistema"]["autoinicio_como"], D["sistema"]["autoinicio_retraso_s"]) == ("bandeja", 20)  # D3
    assert D["comida"]["activa"] is True
    assert D["menu_radial"]["secundario"] == ["comer_batido", "comer_pastel", "guardar_comida"]
    assert {"comida", "discord"} <= set(D["bandeja"]["acciones"])


@pytest.mark.parametrize("texto, esperado", [
    ("siéntate", ("mascota_sentarse", {"sitio": "barra"})),
    ("Siéntate en la barra", ("mascota_sentarse", {"sitio": "barra"})),
    ("oye Lune, siéntate en la barra de tareas porfa", ("mascota_sentarse", {"sitio": "barra"})),
    ("¡Siéntate, Lune!", ("mascota_sentarse", {"sitio": "barra"})),
    ("ponte en la barra", ("mascota_sentarse", {"sitio": "barra"})),
    ("siéntate en una ventana", ("mascota_sentarse", {"sitio": "ventana"})),
    ("Lune, siéntate en esta ventana.", ("mascota_sentarse", {"sitio": "ventana"})),
    ("bájate", ("mascota_sentarse", {"sitio": "bajar"})),
    ("bájate de ahí", ("mascota_sentarse", {"sitio": "bajar"})),
    ("baja de ahí, porfa", ("mascota_sentarse", {"sitio": "bajar"})),
    ("ya bájate de la barra", ("mascota_sentarse", {"sitio": "bajar"})),
    ("toma un batido", ("dar_de_comer", {"comida": "batido"})),
    ("Te doy un pastel", ("dar_de_comer", {"comida": "pastel"})),
    ("ten un pastelito", ("dar_de_comer", {"comida": "pastel"})),
    ("tómate un batido de fresa", ("dar_de_comer", {"comida": "batido"})),
    ("porfa Lune, toma un batidito", ("dar_de_comer", {"comida": "batido"})),
])
def test_detectar_ordenes_de_vida(texto, esperado):
    from lune_core.acciones import USUARIO
    from servicios.tools import ToolManager
    ll = ToolManager().detectar_llamadas(texto)
    assert [(x.herramienta, x.args, x.origen, x.directa, x.error) for x in ll] == [
        (esperado[0], esperado[1], USUARIO, True, None)]


@pytest.mark.parametrize("texto", [
    # preguntas
    "¿te puedes sentar?", "¿te sientas en la barra?", "siéntate?", "¿siéntate?", "¿bajas?", "¿te bajas?",
    "¿quieres un batido?", "¿me das un pastel?", "toma un batido?", "¿cómo hago un batido?",
    # negaciones
    "no te sientes", "no te sientes en la barra", "no te bajes", "no te doy un pastel", "no, siéntate",
    # pasado
    "te sentaste en la barra", "me tomé un batido", "te di un pastel", "ayer me dieron un pastel",
    # frases sobre el tema u otra persona
    "me siento cansada", "siéntate conmigo a ver una peli", "la barra de tareas está llena",
    "mi perro se sienta en la ventana", "baja el volumen", "baja", "bájate la app", "baja de ahí el volumen",
    "toma un batido y dime algo", "toma un batido, Ana", "siéntate tú, Ana", "hazme un pastel",
    "quiero un batido", "siéntate bien en la silla",
])
def test_lo_que_no_es_una_orden_lo_decide_el_modelo(texto):
    from servicios.tools import ToolManager
    assert ToolManager().detectar_llamadas(texto) == [], texto
