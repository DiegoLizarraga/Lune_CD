"""
Tests de nucleo/acciones_ui.py: el catálogo común de acciones (bandeja, radial,
atajos, web y /menu de patata), el Despachador y lo que pintan el radial y la
bandeja. Sin Qt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import acciones_ui as au  # noqa: E402
from nucleo.acciones_ui import ACCIONES, Contexto, Despachador, ItemMenu  # noqa: E402
from nucleo.config import Config  # noqa: E402
from nucleo.estado_mascota import EstadoMascota  # noqa: E402

D = Config.DEFAULT_CONFIG


def desp_con(*ids, diario=None):
    d = Despachador()
    for i in ids:
        d.registrar(i, (lambda i=i: diario.append(i)) if diario is not None else (lambda: None))
    return d


CTX = Contexto(modo="normal", render="vrm", mascota_visible=True)
EST = EstadoMascota(render="vrm", visible=True)


# ── Catálogo y config ─────────────────────────────────────────────────────────

def test_ids_de_default_config_existen_y_admiten_su_sitio():
    radial = D["menu_radial"]["principal"] + D["menu_radial"]["secundario"]
    bandeja = D["bandeja"]["acciones"]
    atajos = [e["id"] for e in D["atajos"]["lista"]]
    for ids, uso in ((radial, "radial"), (bandeja, "bandeja"), (atajos, "atajo")):
        for i in ids:
            assert i in ACCIONES, i
            assert uso in ACCIONES[i].usos, (i, uso)
    # Iconos y etiquetas siempre presentes
    for a in ACCIONES.values():
        assert a.etiqueta and a.icono and a.grupo and a.modos


def test_iconos_del_catalogo_existen_en_ui_icons():
    pytest.importorskip("PyQt6.QtSvg")
    from ui.icons import ICONS
    usados = {a.icono for a in ACCIONES.values()} | {a.icono_on for a in ACCIONES.values() if a.icono_on}
    usados |= {e[2] for e in au.EXPRESIONES}
    assert usados <= set(ICONS), usados - set(ICONS)


# ── Validar listas ────────────────────────────────────────────────────────────

def test_validar_lista():
    assert au.validar_lista("voz") == []
    assert au.validar_lista(None) == []
    assert au.validar_lista(["voz", "nada", 3, "voz", "dormir"]) == ["voz", "dormir"]
    assert au.validar_lista(["voz", "dormir", "chat"], maximo=2) == ["voz", "dormir"]
    # «tema» no puede ir en el radial; «menu_radial» solo es atajo
    assert au.validar_lista(["tema", "menu_radial", "voz"], uso="radial") == ["voz"]
    assert au.validar_lista(["menu_radial", "tema"], uso="atajo") == ["menu_radial"]
    # La interna «expresion» no se puede elegir en ninguna lista
    assert au.validar_lista(["expresion"], uso="radial") == []


# ── Visibilidad ───────────────────────────────────────────────────────────────

def test_sin_handler_se_ocultan_en_radial_bandeja_y_disponibles():
    d = desp_con("voz", "dormir", "salir", "mostrar_lune")
    ids = D["menu_radial"]["principal"]           # bailar, alarma, bajar… sin handler
    items = au.items_radial(d, EST, CTX, ids)
    assert [i.id for i in items] == ["voz", "dormir"]
    assert d.disponibles(EST, CTX) == ["mostrar_lune", "salir", "dormir", "voz"]
    todo = au.menu_bandeja(d, EST, CTX, D["bandeja"]["acciones"], ["cian"])
    planos = _planos(todo)
    assert "bailar" not in planos and "pantalla_grande" not in planos and "tema" not in planos


def test_reglas_de_visibilidad():
    v = au.visible
    grande = EstadoMascota(render="vrm", visible=True, grande=True)
    assert v("ajustes", EST, CTX) and not v("ajustes", grande, CTX)
    assert not v("chat", grande, CTX)
    assert not v("bajar", EST, CTX)
    assert v("bajar", EstadoMascota(visible=True, sentada="barra"), CTX)
    # tamaño y encuadre solo con la mascota 3D a la vista
    assert v("tamano", EST, CTX)
    assert not v("tamano", EST, CTX._replace(render="animado"))
    assert not v("encuadre", EST, CTX._replace(mascota_visible=False))
    # llamada solo en la web
    assert v("llamada", EST, CTX) and not v("llamada", EST, CTX._replace(modo="br"))
    # sprites no comentan la pantalla
    assert not v("comentar", EST, CTX._replace(render="sprites"))
    # sin mascota: dormir/esquina/expresiones fuera, pero sacarla sí
    sin = CTX._replace(mascota_visible=False)
    for i in ("dormir", "esquina", "expresiones", "cerrar_mascota"):
        assert not v(i, EST, sin), i
    assert v("mascota", EST, sin) and v("fantasma", EST, sin)
    assert not v("desconocida", EST, CTX)


def test_etiquetas_segun_estado():
    d = desp_con("dormir", "mascota", "voz")
    dormida = EstadoMascota(render="vrm", visible=True, durmiendo=True)
    [it] = au.items_radial(d, dormida, CTX, ["dormir"])
    assert it.etiqueta == "Despertar" and it.icono == "sun" and it.marcado is None
    [it] = au.items_radial(d, EST, CTX, ["dormir"])
    assert it.etiqueta == "Dormir" and it.icono == "moon"
    [m] = au.items_radial(d, EST, CTX, ["mascota"])
    assert m.etiqueta == "Guardar a la mascota"
    [voz] = au.items_radial(d, EST, CTX._replace(voz_on=True), ["voz"])
    assert voz.marcado is True                           # interruptor: punto de encendido


def test_radial_como_mucho_diez_botones():
    ids = [i for i, a in ACCIONES.items() if "radial" in a.usos]
    d = desp_con(*ids)
    ctx = CTX._replace(varios_vrm=True)
    est = EstadoMascota(render="vrm", visible=True, sentada="barra", bailando="musica")
    items = au.items_radial(d, est, ctx, ids + ids)
    assert len(items) == au.MAX_RADIAL == 10
    assert len({i.id for i in items}) == 10


def test_expresiones_del_segundo_radial():
    assert au.items_expresiones(Despachador()) == []
    d = desp_con("expresion")
    items = au.items_expresiones(d)
    assert [i.arg for i in items] == ["happy", "sad", "angry", "surprised", "thinking", "wave"]
    assert all(i.id == "expresion" for i in items)


# ── Bandeja ───────────────────────────────────────────────────────────────────

def _planos(items):
    out = []
    for it in items:
        if it.hijos:
            out += _planos(it.hijos)
        elif not it.separador:
            out.append(it.id)
    return out


def _sin_separadores_malos(items):
    assert items and not items[0].separador and not items[-1].separador
    for a, b in zip(items, items[1:]):
        assert not (a.separador and b.separador)
    for it in items:
        if it.hijos:
            _sin_separadores_malos(it.hijos)


def test_menu_bandeja_empieza_abrir_lune_y_acaba_salir():
    ids = list(ACCIONES)
    d = desp_con(*ids)
    ctx = CTX._replace(voz_on=True, tema_preset="violeta", juego_activo=True, juego_motivo="quns3",
                       tamano="grande", encuadre="cuerpo", autoinicio_on=False)
    items = au.menu_bandeja(d, EST, ctx, D["bandeja"]["acciones"], ["cian", ("violeta", "Violeta")])
    assert items[0] == ItemMenu("mostrar_lune", "Abrir Lune", negrita=True)
    assert items[-1].id == "salir" and items[-1].etiqueta == "Salir"
    _sin_separadores_malos(items)
    titulos = [i.etiqueta for i in items if i.hijos]
    assert titulos == ["Mascota", "Lune", "Tema"]
    mascota = next(i for i in items if i.etiqueta == "Mascota")
    sub = {i.etiqueta: i for i in mascota.hijos if i.hijos}
    assert [h.marcado for h in sub["Tamaño"].hijos] == [False, False, True]
    assert [h.arg for h in sub["Encuadre"].hijos] == ["retrato", "cuerpo"]
    juego = next(i for i in items if i.id == "modo_juego_forzar")
    assert juego.marcado is True and "pantalla completa" in juego.etiqueta
    tema = next(i for i in items if i.etiqueta == "Tema")
    assert [(h.arg, h.marcado) for h in tema.hijos] == [("cian", False), ("violeta", True)]
    lune = next(i for i in items if i.etiqueta == "Lune")
    voz = next(i for i in lune.hijos if i.id == "voz")
    assert voz.marcado is True
    auto = next(i for i in items if i.id == "autoinicio")
    assert auto.marcado is False
    # Las rápidas respetan el orden de bandeja.acciones y descartan lo que no va en bandeja
    assert [i.id for i in lune.hijos][:3] == ["mascota", "comentar", "voz"]


def test_menu_bandeja_juego_forzado_y_mascota_oculta():
    d = desp_con("mostrar_lune", "salir", "modo_juego_forzar", "mascota", "dormir", "fantasma")
    ctx = CTX._replace(mascota_visible=False, juego_forzado=True, juego_activo=True)
    items = au.menu_bandeja(d, EST, ctx, [], [])
    j = next(i for i in items if i.id == "modo_juego_forzar")
    assert j.etiqueta.endswith("(forzado)")
    mascota = next(i for i in items if i.etiqueta == "Mascota")
    assert [h.id for h in mascota.hijos if not h.separador] == ["mascota", "fantasma"]   # sin «Dormir»
    ctx = ctx._replace(juego_forzado=False, juego_activo=False)
    j = next(i for i in au.menu_bandeja(d, EST, ctx, [], []) if i.id == "modo_juego_forzar")
    assert j.etiqueta.endswith("(apagado a mano)") and j.marcado is False


# ── Despachador ───────────────────────────────────────────────────────────────

def test_despachador_pasa_lo_que_acepta_cada_handler():
    d = Despachador()
    visto = []
    d.registrar("voz", lambda: visto.append("voz"))
    d.registrar("tema", lambda arg: visto.append(("tema", arg)))
    d.registrar("ajustes", lambda arg="", origen="": visto.append(("ajustes", arg, origen)))
    d.registrar("salir", lambda **kw: visto.append(("salir", kw)))
    assert d.ejecutar("voz", origen="atajo") is True
    assert d.ejecutar("tema", "ambar", origen="bandeja") is True
    assert d.ejecutar("ajustes", "", origen="radial") is True
    assert d.ejecutar("salir", origen="bandeja") is True
    assert visto == ["voz", ("tema", "ambar"), ("ajustes", "", "radial"), ("salir", {"origen": "bandeja"})]


def test_despachador_errores():
    d = Despachador()
    with pytest.raises(ValueError):
        d.registrar("no_existe", lambda: None)
    with pytest.raises(TypeError):
        d.registrar("voz", "no invocable")
    assert d.ejecutar("voz") is False                    # sin handler
    d.registrar("voz", lambda: 1 / 0)
    assert d.ejecutar("voz") is False                    # el fallo no se propaga
    d.registrar("mascota", lambda: False)
    assert d.ejecutar("mascota") is True                 # devolver False no es fallar
    assert d.tiene("voz") and d.quitar("voz") and not d.tiene("voz") and not d.quitar("voz")


def test_marcado_del_handler_manda_sobre_el_contexto():
    d = Despachador()
    d.registrar("voz", lambda: None, marcado=lambda: True)
    d.registrar("fantasma", lambda: None)
    d.registrar("autoinicio", lambda: None, marcado=lambda: 1 / 0)
    ctx = CTX._replace(voz_on=False, fantasma_on=True, autoinicio_on=True)
    assert d.marcado_en("voz", EST, ctx) is True
    assert d.marcado_en("fantasma", EST, ctx) is True     # del contexto
    assert d.marcado_en("autoinicio", EST, ctx) is True   # su marcado falló → contexto


def test_catalogo_para_la_web():
    d = desp_con("voz", "llamada", "dormir")
    todo = au.catalogo(d, EST, CTX._replace(modo="br", voz_on=True))
    por_id = {e["id"]: e for e in todo}
    assert set(por_id) == set(ACCIONES)
    assert por_id["voz"]["disponible"] and por_id["voz"]["visible"] and por_id["voz"]["marcado"] is True
    assert not por_id["llamada"]["disponible"]           # la nativa no tiene llamada
    assert not por_id["bailar"]["disponible"] and not por_id["bailar"]["visible"]
    radial = au.catalogo(d, EST, CTX, tipo="radial")
    assert all("radial" in e["usos"] for e in radial)
    assert "tema" not in {e["id"] for e in radial}


def test_en_patata_solo_lo_que_sabe_hacer_la_terminal():
    d = desp_con(*ACCIONES)
    ctx = Contexto(modo="patata")
    est = EstadoMascota()
    assert d.disponibles(est, ctx) == ["salir", "voz", "modo_juego_forzar", "tema", "autoinicio",
                                       "liberar_memoria"]
    assert au.en_modo("tema", "patata") and not au.en_modo("mascota", "patata")
