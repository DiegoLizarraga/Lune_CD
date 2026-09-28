"""
Integración de los cortes 5 y 6 (alarmas y temporizadores, pantalla grande y
salvapantallas, baile): las clases DE VERDAD cumplen lo que las otras les llaman.

- Mascotas (ui/companion.CompanionFlotante, ui/avatar_overlay.AvatarOverlay): lo que
  les piden ControlPantallaGrande, ControlAlarmasQt y ControlBaile.
- Controladores, VentanaReloj, la tarjeta de la alarma, los puentes web (con las
  ranuras y señales que usan extra/alarmas.jsx y extra/baile.jsx), el panel nativo y
  ServiciosOcio.
- El montaje real (montar_escritorio → montar_ocio) con los controladores de verdad y
  dobles del sistema (tests/ocio_falso_c56.py): acciones, las 7 herramientas en el
  ToolManager, atajos, «avísame en 1 minuto» → Llamada → Ejecutor → alarmas.json
  temporal; desmontar lo quita todo.
- Cómo encajan las piezas: la secuencia de la pantalla grande que espera la mascota
  (agente D) y la alarma que llega con el salvapantallas puesto (agentes A y B).
- Catálogo, config por defecto y la detección de pedidos (origen usuario / remoto).
Offscreen; nada de Win32 que cambie algo, ni audio, ni alarmas.json de verdad.
"""
import copy
import inspect
import os
import re
import sys
import time
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

from PyQt6.QtCore import QMetaMethod, QObject, QRect  # noqa: E402

from nucleo.config import Config  # noqa: E402
import ocio_falso_c56 as of  # noqa: E402

admite = of.admite
JSX = RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "extra"


def _propiedad(cls, nombre) -> bool:
    return isinstance(inspect.getattr_static(cls, nombre, None), property)


def _metodo(cls, nombre):
    f = inspect.getattr_static(cls, nombre, None)
    assert callable(f), f"{cls.__name__}.{nombre} no existe"
    return f


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)

    def feature(self, n, d=True):
        return d


# ═══ Mascotas ═══════════════════════════════════════════════════════════════════

# (método, args, kwargs) tal como los llaman ControlAlarmasQt, ControlBaile y
# ControlPantallaGrande (ui/alarmas_qt.py, ui/baile_qt.py, ui/pantalla_grande_qt.py).
LLAMADAS_COMUNES = [
    ("bailar", (True, {"estilo": "rebote", "cambiar": False, "cambiarS": 15, "particulas": True}), {}),
    ("bailar", (False,), {}),
    ("pulso", (124.0, 0.25, 0.7), {}),
    ("mostrar_alarma", ("⏰ Pizza",), {}),
    ("ocultar_alarma", (), {}),
    ("despertar", (), {}),
]
LLAMADAS_GRANDE = [
    ("geometria", (), {}),
    ("set_geometria", (QRect(0, 0, 800, 600),), {}),
    ("grande_fase", ("glide", {"ms": 400, "motivo": "manual"}), {}),
    ("grande_fase", ("fin", {"ms": 0}), {}),
    ("set_salvapantallas", (True,), {"fondo_oscuro": True, "reloj": False}),
    ("set_salvapantallas", (False,), {}),
]


def test_companion_cumple_el_contrato_de_ocio():
    C = pytest.importorskip("ui.companion").CompanionFlotante
    for nombre, a, k in LLAMADAS_COMUNES + LLAMADAS_GRANDE:
        assert admite(_metodo(C, nombre), None, *a, **k), f"CompanionFlotante.{nombre}{a}{k}"
    for prop in ("soporta_grande", "en_grande", "salvapantallas", "alarma_visible", "bailando", "durmiendo"):
        assert _propiedad(C, prop), prop
    assert callable(getattr(C, "close")) and callable(getattr(C, "isVisible"))  # mascota temporal


def test_avatar_overlay_cumple_lo_que_aplica_y_no_hace_pantalla_grande():
    from ui.avatar_overlay import AvatarOverlay as A
    for nombre, a, k in LLAMADAS_COMUNES:
        assert admite(_metodo(A, nombre), None, *a, **k), f"AvatarOverlay.{nombre}{a}{k}"
    for prop in ("soporta_grande", "bailando", "durmiendo"):
        assert _propiedad(A, prop), prop
    # Sprites: sin pantalla grande ni salvapantallas → VentanaReloj (D2).
    assert inspect.getattr_static(A, "soporta_grande").fget(None) is False


# ═══ Controladores, ventanas y diálogos ═════════════════════════════════════════

def _senales(cls, *nombres):
    for n in nombres:
        s = getattr(cls, n, None)
        assert s is not None and type(s).__name__ == "pyqtSignal", f"{cls.__name__}.{n}"


def test_controladores_cumplen_lo_que_llaman_montaje_puentes_panel_y_herramientas():
    from ui.alarmas_qt import ControlAlarmasQt as A
    from ui.baile_qt import ControlBaile as B
    from ui.pantalla_grande_qt import ControlPantallaGrande as G
    # Lo que pasan las fábricas por defecto de ui/montaje_ocio.py.
    assert admite(A.__init__, None, None, None, voice=None, grande=None, avisar=None, en_ui=None, parent=None)
    assert admite(G.__init__, None, None, None, anfitrion=None, en_ui=None, parent=None)
    assert admite(B.__init__, None, None, None, en_ui=None, parent=None)
    # Contrato de controlador de ServiciosEscritorio (ui/escritorio.py).
    for cls in (A, B, G):
        for n, a in (("iniciar", ()), ("detener", ()), ("set_mascota", (None,)), ("ceder", (None,)),
                     ("reanudar", (None,)), ("recargar_config", ()), ("herramientas", ())):
            assert admite(_metodo(cls, n), None, *a), f"{cls.__name__}.{n}"
    # Alarmas: montaje_ocio, puente_alarmas, panel_ocio_nativo.
    for n, a, k in (("apagar", (), {"forzar": True}), ("apagar", (), {}), ("posponer", (), {}), ("probar", (), {}),
                    ("rapido", (5,), {}), ("abrir_dialogo", (None,), {}), ("abrir_dialogo", (), {}),
                    ("listar", (), {}), ("guardar_alarma", ({},), {}), ("crear_temporizador", ({},), {}),
                    ("borrar", ("a1",), {}), ("temporizador_accion", ("t1", "parar"), {})):
        assert admite(_metodo(A, n), None, *a, **k), f"ControlAlarmasQt.{n}"
    _senales(A, "sonando", "apagada", "cambio", "perdidas")
    # Pantalla grande: alarmas, puente, panel, nucleo.pantalla_grande.herramienta.
    for n, a, k in (("entrar", ("alarma",), {}), ("entrar", ("herramienta", 5), {}), ("salir", ("alarma",), {}),
                    ("salir", (), {"inmediato": True}), ("salir", (), {}), ("mostrar_alarma", ("x",), {}),
                    ("mostrar_alarma", (None,), {}), ("alternar", (), {}), ("estado", (), {}),
                    ("probar_salvapantallas", (), {})):
        assert admite(_metodo(G, n), None, *a, **k), f"ControlPantallaGrande.{n}"
    assert _propiedad(G, "activo") and _propiedad(G, "motivo")
    _senales(G, "cambio", "pedir_apagar_alarma", "pedir_posponer_alarma")
    # Baile: montaje (bailar/parar/pausa), puente_musica, panel, nucleo.baile.herramienta_*.
    for n, a, k in (("bailar", (), {}), ("bailar", (None,), {}), ("bailar", (30,), {"origen": "manual"}),
                    ("parar", (), {}), ("pausa", (), {}), ("estado", (), {}), ("apps_sonando", (True,), {}),
                    ("permitir_app", ("Spotify",), {}), ("quitar_app", ("Spotify",), {})):
        assert admite(_metodo(B, n), None, *a, **k), f"ControlBaile.{n}"
    assert _propiedad(B, "bailando")
    _senales(B, "estado_cambio", "pulso", "apps_cambio")


def test_ventana_reloj_y_tarjeta_de_alarma_cumplen_lo_que_les_llaman():
    from ui.alarmas_dialogo import DialogoAlarma
    from ui.ventana_reloj import VentanaReloj
    # ControlPantallaGrande._mostrar_reloj / _poner_alarma_reloj / salir.
    assert admite(VentanaReloj.mostrar, None, "salvapantallas", pantalla=None, fondo_oscuro=True, reloj=True)
    assert admite(VentanaReloj.set_alarma, None, "texto", bloqueo_ms=5000)
    assert admite(VentanaReloj.set_alarma, None, None)
    assert admite(VentanaReloj.ocultar, None, 0) and admite(VentanaReloj.ocultar, None)
    _senales(VentanaReloj, "apagar", "posponer", "cerrar_pedido")
    # ControlAlarmasQt._mostrar_dialogo.
    assert admite(DialogoAlarma.set_disparo, None, "texto", tipo="alarma", programado="07:30",
                  bloqueo_ms=5000, posponer_min=5, cola=1)
    assert admite(DialogoAlarma.mostrar, None) and admite(DialogoAlarma.cerrar, None)
    _senales(DialogoAlarma, "apagar", "posponer")


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


def _usos_jsx(archivo):
    texto = (JSX / archivo).read_text(encoding="utf-8")
    return (set(re.findall(r"\bpedir\('([a-z_]+)'", texto)), set(re.findall(r"\bconectar\('([a-z_]+)'", texto)))


def test_los_puentes_tienen_las_ranuras_y_senales_que_usa_la_pagina(qapp):
    from ui.puente_alarmas import PuenteAlarmas
    from ui.puente_musica import PuenteMusica
    for archivo, puente in (("alarmas.jsx", PuenteAlarmas(None)), ("baile.jsx", PuenteMusica(None))):
        ranuras, senales = _qt_de(puente)
        pedidas, escuchadas = _usos_jsx(archivo)
        assert pedidas and escuchadas
        assert pedidas <= ranuras, f"{archivo} llama a ranuras que {type(puente).__name__} no tiene: {pedidas - ranuras}"
        assert escuchadas <= senales, f"{archivo} escucha señales que no existen: {escuchadas - senales}"
        assert admite(type(puente).cerrar, None)
        puente.cerrar()
    assert admite(PuenteAlarmas.enlazar, None, alarmas=None, grande=None)
    assert admite(PuenteMusica.enlazar, None, baile=None)


def test_servicios_ocio_panel_nativo_y_puentes_ocio_firmas():
    from ui.montaje_escritorio import ServiciosCorte4
    from ui.montaje_ocio import EnHiloQt, ServiciosOcio, montar_ocio
    from ui.panel_ocio_nativo import PanelOcioNativo
    from ui.puentes_ocio import PuentesOcio, registrar_puentes_ocio
    assert {"alarmas", "grande", "baile", "en_ui"} <= set(ServiciosOcio.__dataclass_fields__)
    assert "ocio" in ServiciosCorte4.__dataclass_fields__
    assert admite(ServiciosOcio.desmontar, None) and ServiciosOcio.detener is ServiciosOcio.desmontar
    assert admite(montar_ocio, None, None, voice=None, fabricas=None)
    assert admite(EnHiloQt.__call__, None, lambda: 1, 5.0)
    assert admite(PanelOcioNativo.__init__, None, None, None, alarmas=None, grande=None, baile=None, retardo_ms=300)
    assert admite(PanelOcioNativo.enlazar, None, None) and admite(PanelOcioNativo.guardar_ya, None)
    _senales(PanelOcioNativo, "cambiado")
    assert admite(registrar_puentes_ocio, None, None, None)
    assert admite(PuentesOcio.enlazar, None, None) and admite(PuentesOcio.cerrar, None)


# ═══ El montaje de verdad ═══════════════════════════════════════════════════════

HERRAMIENTAS = ("temporizador", "alarma", "cancelar_alarma", "listar_alarmas",
                "mascota_bailar", "parar_baile", "mascota_pantalla_grande")
ACCIONES = ("alarma", "temporizador_rapido", "pantalla_grande", "bailar", "baile_pausa")


def _esperar(qapp, cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return cond()


@pytest.fixture
def montaje(qapp, tmp_path):
    """montar_escritorio de verdad (piezas del corte 4 falsas, las de tests/
    test_montaje_escritorio.py) + montar_ocio con los controladores de verdad."""
    import test_montaje_escritorio as tme
    from servicios.tools import ToolManager
    from ui.escritorio import ServiciosEscritorio
    from ui.montaje_escritorio import montar_escritorio
    reg = of.Registro(tmp_path)
    cfg = ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    tm = ToolManager()
    esc.conectar_herramientas(tm)
    esc.iniciar()
    gestor = tme.GestorFalso()
    fab = {"tema": lambda c, p: tme.TemaFalso(c, p), "juego": tme.JuegoFalso, "gestor_atajos": gestor,
           "tray": tme.TrayFalso, "autoinicio": tme.AutoinicioFalso(), "sonar": lambda n: None,
           "modelos_vrm": lambda: [], "traer_al_frente": None, "ocio": of.fabricas_ocio(reg),
           "vida": False,                 # cortes 7/8 aparte (tests/test_contratos_c78.py)
           "escenario": False}            # cortes 9/10 aparte (tests/test_contratos_c910.py)
    anf = tme.AnfitrionFalso(modo="br")
    s = montar_escritorio(esc, anf, cfg, fabricas=fab)
    s.reg, s.cfg, s.esc, s.tm, s.gestor, s.anf = reg, cfg, esc, tm, gestor, anf
    yield s
    s.desmontar()
    esc.cerrar()


def test_montaje_real_registra_todo_y_desmontar_lo_quita(montaje, qapp):
    from ui.alarmas_qt import ControlAlarmasQt
    from ui.baile_qt import ControlBaile
    from ui.montaje_ocio import ServiciosOcio
    from ui.pantalla_grande_qt import ControlPantallaGrande
    s, reg = montaje, montaje.reg
    ocio = s.ocio
    assert isinstance(ocio, ServiciosOcio)
    assert isinstance(ocio.grande, ControlPantallaGrande) and isinstance(ocio.alarmas, ControlAlarmasQt)
    assert isinstance(ocio.baile, ControlBaile) and ocio.alarmas.grande is ocio.grande
    assert list(s.esc.controladores())[-3:] == ["grande", "alarmas", "baile"]
    for id_ in ACCIONES:
        assert s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS:
        assert s.tm.tiene_handler(h), h
    assert {"pantalla_grande", "baile_pausa"} <= set(s.gestor.activos)          # atajos con handler
    # Arrancaron con el escritorio: un detector de música; el mutex del dueño en el primer tic.
    assert reg.detectores_vivos == [ocio.baile.detector] and reg.alarmas_en_marcha == [ocio.alarmas]
    ocio.alarmas._tic()
    assert reg.dueno is ocio.alarmas._mutex
    # La nativa: «alarma» abre el editor (aquí, sin ventana).
    abiertos = []
    ocio.alarmas.abrir_dialogo = lambda parent=None: abiertos.append(parent)
    assert s.despachador.ejecutar("alarma") and abiertos == [None]
    # Temporizador rápido del radial/bandeja → alarmas.json temporal.
    assert s.despachador.ejecutar("temporizador_rapido", "10")
    assert [t.duracion_s for t in ocio.alarmas.almacen.temporizadores()] == [600]
    assert reg.ruta_alarmas.exists() and ocio.alarmas.almacen.ruta == reg.ruta_alarmas   # el temporal

    s.desmontar()
    for id_ in ACCIONES:
        assert not s.despachador.tiene(id_), id_
    for h in HERRAMIENTAS:
        assert not s.tm.tiene_handler(h), h
    assert not {"grande", "alarmas", "baile"} & set(s.esc.controladores())
    assert reg.detectores_vivos == [] and reg.alarmas_en_marcha == [] and reg.dueno is None
    assert not {"pantalla_grande", "baile_pausa"} & set(s.gestor.activos)
    assert ocio.desmontado
    s.desmontar()                                                              # idempotente


def test_avisame_en_un_minuto_llamada_por_el_ejecutor_al_almacen(montaje):
    from lune_core.acciones import USUARIO
    from servicios.tools import ctx_acciones
    s = montaje
    llamadas = s.tm.detectar_llamadas("avísame en 1 minuto que saque la ropa")
    assert [(ll.herramienta, ll.args, ll.origen, ll.directa) for ll in llamadas] == [
        ("temporizador", {"segundos": 60, "texto": "saque la ropa"}, USUARIO, True)]
    assert s.ocio.alarmas.almacen.temporizadores() == []                       # detectar no ejecuta nada
    resultados = []
    ej = s.tm.crear_ejecutor(audit_path=None)
    ej.ejecutar_llamadas(llamadas, USUARIO, ctx_acciones(None, "", "br"), resultados.append)
    assert resultados and resultados[0].ok, resultados
    t = s.ocio.alarmas.almacen.temporizadores()
    assert [(x.duracion_s, x.texto) for x in t] == [(60, "saque la ropa")]


def test_orden_remota_pide_permiso_antes_de_poner_la_alarma(montaje):
    from lune_core.acciones import REMOTO
    from servicios.tools import ctx_acciones
    s = montaje
    pedidas = []
    ej = s.tm.crear_ejecutor(lambda pendiente, responder: pedidas.append((pendiente, responder)),
                             audit_path=None, despachar=lambda fn: fn())
    llamadas = s.tm.detectar_llamadas("pon una alarma a las 7:30 de lunes a viernes para el gimnasio")
    assert [ll.herramienta for ll in llamadas] == ["alarma"]
    resultados = []
    ctx = ctx_acciones(None, "", "br")
    ctx["origen"] = REMOTO
    ej.ejecutar_llamadas(llamadas, REMOTO, ctx, resultados.append)
    assert len(pedidas) == 1 and s.ocio.alarmas.almacen.alarmas() == []        # nada sin tu permiso
    pedidas[0][1](True)
    assert [(a.hhmm, a.texto) for a in s.ocio.alarmas.almacen.alarmas()] == [("07:30", "el gimnasio")]
    assert resultados and resultados[-1].ok


# ═══ Cómo encajan las piezas ════════════════════════════════════════════════════

@pytest.fixture
def con_mascota(montaje, qapp):
    m = of.MascotaGrande()
    montaje.esc.set_mascota(m, render="vrm")
    montaje.m = m
    yield montaje
    montaje.esc.set_mascota(None)


def _avanzar(s, segundos):
    s.reg.t += segundos
    s.ocio.grande._tic_maquina()


def test_secuencia_de_pantalla_grande_la_que_espera_la_mascota(con_mascota):
    """Agente D: geometria() → «glide» → a los 400 ms set_geometria(monitor) + «entrar»;
    salida: «salir» → set_geometria(la de antes) + «volver» → «fin». Inmediata:
    la geometría de antes y «fin» en el acto."""
    s, m, g = con_mascota, con_mascota.m, con_mascota.ocio.grande
    antes = m.geometria()
    m.diario.clear()
    assert g.entrar("manual") is True and s.esc.estado.actual().grande
    assert m.nombres() == ["geometria", "grande_fase"] and m.fases() == ["glide"]
    _avanzar(s, 0.41)
    assert m.nombres()[-2:] == ["set_geometria", "grande_fase"] and m.fases()[-1] == "entrar"
    assert m.diario[-2][1] != antes                                            # el monitor entero
    _avanzar(s, 0.51)
    assert g.activo and g.estado()["fase"] == "activa"
    m.diario.clear()
    assert g.salir() is True
    assert m.fases() == ["salir"]
    _avanzar(s, 0.51)
    assert m.diario[-2] == ("set_geometria", antes) and m.fases()[-1] == "volver"
    _avanzar(s, 0.41)
    assert m.fases()[-1] == "fin" and not g.activo and not s.esc.estado.actual().grande
    # Salida inmediata (entra un juego): la geometría de antes y «fin» a la vez.
    g.entrar("manual")
    _avanzar(s, 0.41)
    _avanzar(s, 0.51)
    m.diario.clear()
    g.salir(inmediato=True)
    assert ("set_geometria", antes) in m.diario and m.fases() == ["fin"] and not g.activo
    assert m.malas == []                                                       # firmas de CompanionFlotante


def test_alarma_con_el_salvapantallas_puesto_sigue_en_grande_y_sale_al_apagarla(con_mascota):
    """Agentes A y B: con el salvapantallas puesto, la alarma lo cede, la pantalla grande
    sigue (motivo «alarma»), grande.entrar("alarma") dice True (sin burbuja) y al apagar
    la alarma se sale de todo."""
    s, m, g, a = con_mascota, con_mascota.m, con_mascota.ocio.grande, con_mascota.ocio.alarmas
    assert g.probar_salvapantallas() is True
    _avanzar(s, 0.41)
    _avanzar(s, 0.51)
    est = s.esc.estado.actual()
    assert est.salvapantallas and g.motivo == "salvapantallas" and m.durmiendo
    m.diario.clear()
    assert a.probar() is True
    est = s.esc.estado.actual()
    assert est.alarma and est.grande and not est.salvapantallas
    assert g.activo and g.motivo == "alarma" and a._visual == "grande"
    assert ("set_salvapantallas", False, {"fondo_oscuro": True, "reloj": True}) in m.diario   # la despierta
    assert any(x[0] == "mostrar_alarma" and "Prueba" in x[1] for x in m.diario)
    assert s.reg.mez.reproducidos[-1] == ("alarma", True)                     # por el Mezclador, en bucle
    m.diario.clear()
    assert a.apagar(forzar=True) is True
    assert ("ocultar_alarma",) in m.diario and m.fases() == ["salir"]
    _avanzar(s, 0.51)
    _avanzar(s, 0.41)
    est = s.esc.estado.actual()
    assert not g.activo and not est.alarma and not est.grande and not est.salvapantallas
    assert m.fases()[-1] == "fin" and m.malas == []


def test_botones_de_ventana_reloj_llegan_a_la_alarma(montaje):
    """Sin mascota: la alarma en VentanaReloj; sus botones → ControlAlarmasQt."""
    s, g, a = montaje, montaje.ocio.grande, montaje.ocio.alarmas
    assert a.probar() is True
    assert a._visual == "grande" and g.activo and g._vista == "reloj"
    v = g._ventana
    assert v.modo == "alarma" and v.alarma
    a.aviso.bloqueo_s = 0
    v.apagar.emit()
    assert a.aviso.sonando is None and not g.activo


def test_baile_llega_a_la_mascota_y_la_pantalla_grande_lo_cede(con_mascota):
    s, m, b, g = con_mascota, con_mascota.m, con_mascota.ocio.baile, con_mascota.ocio.grande
    assert b.bailar(30) is True and b.bailando and s.esc.estado.actual().bailando
    assert any(x[0] == "bailar" and x[1] is True for x in m.diario)
    assert b.detector.forzados == [True]                                       # manual: pulso de la más fuerte
    g.entrar("manual")
    assert not s.esc.estado.actual().bailando and ("bailar", False) in m.diario  # la grande quita el baile
    g.salir(inmediato=True)
    b.parar()
    assert m.malas == []


# ═══ Catálogo, config y detección de pedidos ════════════════════════════════════

def test_catalogo_de_ocio_handlers_importables_y_fecha_de_alarma():
    import importlib
    from lune_core import catalogo_herramientas as cat
    for nombre in HERRAMIENTAS:
        h = cat.obtener(nombre)
        mod, _, fn = h.handler.rpartition(".")
        assert callable(getattr(importlib.import_module(mod), fn)), h.handler
    args, _ = cat.validar({"hora": "07:00", "dias": "", "texto": "cita", "fecha": "2026-09-27"},
                          cat.obtener("alarma").args)
    assert args["fecha"] == "2026-09-27"
    with pytest.raises(cat.ArgumentosInvalidos):
        cat.validar({"hora": "07:00", "fecha": "mañana"}, cat.obtener("alarma").args)


def test_config_por_defecto_de_los_cortes_5_y_6():
    d = Config.DEFAULT_CONFIG
    assert d["baile"]["umbral"] == 0.05                                        # D1
    assert d["alarmas"]["volumen"] == 0.8 and d["alarmas"]["sonido"] == "azar"


def test_config_real_conserva_volumen_y_sonido_de_alarmas(tmp_path):
    """_merge_defaults poda lo desconocido: con las claves en DEFAULT_CONFIG se guardan."""
    c = Config(str(tmp_path / "config.json"))
    c.set("alarmas", "volumen", 0.3)
    c.set("alarmas", "sonido", "alarma_2")
    c2 = Config(str(tmp_path / "config.json"))
    assert c2.get("alarmas", "volumen") == 0.3 and c2.get("alarmas", "sonido") == "alarma_2"


@pytest.mark.parametrize("texto, esperado", [
    ("avísame en 5 minutos", ("temporizador", {"segundos": 300, "texto": ""})),
    ("recuérdame que a las 5 de la tarde tengo cita", ("alarma", {"hora": "17:00", "dias": "", "texto": "tengo cita"})),
    ("¡baila!", ("mascota_bailar", {"segundos": 30})),
    ("para de bailar", ("parar_baile", {})),
    ("abre youtube", ("abrir_url", {"url": "https://www.youtube.com"})),
    ("recuerda que mi cumple es el 5", None),
    ("bailas muy bien", None),
])
def test_detectar_llamadas_de_ocio(texto, esperado):
    from lune_core.acciones import USUARIO
    from servicios.tools import ToolManager
    ll = ToolManager().detectar_llamadas(texto)
    if esperado is None:
        assert ll == []
        return
    assert [(x.herramienta, x.args, x.origen, x.directa, x.error) for x in ll] == [
        (esperado[0], esperado[1], USUARIO, True, None)]


def test_gitignore_no_versiona_las_alarmas():
    lineas = {ln.strip() for ln in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert {"alarmas.json", "alarmas.json.corrupto-*"} <= lineas


def test_refresco_en_cola_con_el_controlador_de_alarmas_ya_borrado(qapp, tmp_path):
    """Una herramienta del modelo (otro hilo) pide refrescar y, antes de que llegue, el
    cambio de interfaz borra el controlador: Qt descarta el refresco (antes, una lambda
    llamaba a un objeto borrado y PyQt abortaba el proceso)."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    reg = of.Registro(tmp_path)
    a = of.fabricas_ocio(reg)["alarmas"](None, ConfigFalsa())
    cambios = []
    a.cambio.connect(cambios.append)
    a._refresco.emit()                                                 # en cola
    a.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    assert cambios == []
