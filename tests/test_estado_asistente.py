"""
Tests de nucleo/estado_asistente: el bus de estado compartido y la tabla de
prioridades (juego > alarma > grande/salvapantallas > mmd > sentada > comida >
baile > idle), incluida la memoria de «volver a sentarla».
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import estado_asistente as E  # noqa: E402
from nucleo.estado_asistente import BusEstado, EstadoAsistente  # noqa: E402


def estado(**kw) -> EstadoAsistente:
    return EstadoAsistente(**kw)


# ── EstadoAsistente y BusEstado ────────────────────────────────────────────────────
def test_estado_por_defecto_tiene_todos_los_campos():
    e = EstadoAsistente()
    for campo in ("render", "visible", "arrastrando", "durmiendo", "pensando", "hablando",
                  "llamada", "bailando", "sentada", "grande", "salvapantallas", "alarma",
                  "comiendo", "menu_abierto", "juego", "emocion"):
        assert hasattr(e, campo)
    assert e.emocion == "neutral" and e.sentada == "" and e.visible is False


def test_estado_es_inmutable():
    with pytest.raises(Exception):
        EstadoAsistente().visible = True


def test_actualizar_solo_notifica_si_cambia():
    bus = BusEstado()
    recibidos = []
    bus.suscribir(lambda est, cambios: recibidos.append(cambios))
    assert bus.actualizar(visible=True, render="vrm") is True
    assert bus.actualizar(visible=True) is False          # igual: nada
    assert bus.actualizar(visible=True, render="vrm") is False
    assert recibidos == [{"visible": (False, True), "render": ("", "vrm")}]
    assert bus.actual().visible is True and bus.actual().render == "vrm"


def test_suscriptor_recibe_el_estado_nuevo():
    bus = BusEstado()
    vistos = []
    bus.suscribir(lambda est, cambios: vistos.append(est))
    bus.actualizar(hablando=True)
    assert vistos[-1].hablando is True
    assert vistos[-1] is bus.actual()


def test_cancelar_suscripcion():
    bus = BusEstado()
    n = []
    cancelar = bus.suscribir(lambda est, c: n.append(1))
    bus.actualizar(pensando=True)
    cancelar()
    cancelar()                                            # dos veces no rompe
    bus.actualizar(pensando=False)
    assert n == [1]


def test_campo_desconocido_es_error():
    bus = BusEstado()
    with pytest.raises(TypeError):
        bus.actualizar(visble=True)


def test_campos_de_texto_normalizan_none_y_false():
    bus = BusEstado(EstadoAsistente(sentada="barra", bailando="musica"))
    bus.actualizar(sentada=False, bailando=None)
    assert bus.actual().sentada == "" and bus.actual().bailando == ""
    with pytest.raises(TypeError):
        bus.actualizar(sentada=True)                      # ¿dónde? hay que decirlo


def test_un_suscriptor_que_falla_no_rompe_a_los_demas():
    bus = BusEstado()
    ok = []

    def malo(est, c):
        raise RuntimeError("boom")
    bus.suscribir(malo)
    bus.suscribir(lambda est, c: ok.append(est.durmiendo))
    bus.actualizar(durmiendo=True)
    assert ok == [True]


def test_cambio_desde_un_suscriptor_se_notifica_despues_y_en_orden():
    bus = BusEstado()
    orden = []

    def reacciona(est, cambios):
        orden.append(dict(cambios))
        if "alarma" in cambios and est.alarma:
            bus.actualizar(emocion="surprised")           # anidado: se encola
    bus.suscribir(reacciona)
    bus.suscribir(lambda est, c: orden.append(("segundo", tuple(c))))
    bus.actualizar(alarma=True)
    assert orden == [
        {"alarma": (False, True)},
        ("segundo", ("alarma",)),
        {"emocion": ("neutral", "surprised")},
        ("segundo", ("emocion",)),
    ]


def test_es_seguro_entre_hilos():
    bus = BusEstado()
    cuenta = {"n": 0}
    lock = threading.Lock()

    def sub(est, cambios):
        with lock:
            cuenta["n"] += 1
    bus.suscribir(sub)

    def trabajar(i):
        for k in range(200):
            bus.actualizar(emocion=f"e{i}-{k}")
    hilos = [threading.Thread(target=trabajar, args=(i,)) for i in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    assert cuenta["n"] == 8 * 200                         # cada cambio, una notificación
    assert bus.actual().emocion.endswith("-199")


# ── Tabla de prioridades (funciones puras) ───────────────────────────────────────
def test_orden_de_prioridades():
    p = E.PRIORIDAD
    assert p["juego"] > p["alarma"] > p["grande"] > p["mmd"] > p["sentada"] > p["comida"] > p["baile"] > p["idle"]
    assert p["grande"] == p["salvapantallas"]


def test_actividades_activas():
    e = estado(juego=True, sentada="barra", bailando="mmd", comiendo=True)
    assert E.actividades_activas(e) == ["juego", "mmd", "sentada", "comida"]
    assert E.actividades_activas(estado(bailando="musica")) == ["baile"]
    assert E.actividades_activas(EstadoAsistente()) == []


def test_juego_bloquea_todo_lo_demas():
    e = estado(juego=True)
    for a in ("alarma", "grande", "salvapantallas", "mmd", "sentada", "comida", "baile", "idle"):
        assert not E.puede(a, e), a
    assert E.puede("juego", e)


def test_puede_por_prioridad():
    sentada = estado(sentada="barra")
    assert E.puede("grande", sentada)
    assert E.puede("mmd", sentada)
    assert not E.puede("baile", sentada)                  # el baile automático no la levanta
    assert not E.puede("idle", sentada)
    assert E.puede("sentada", sentada)                    # cambiar de sitio se permite


def test_grande_y_salvapantallas_no_se_interrumpen_entre_si():
    assert not E.puede("salvapantallas", estado(grande=True))
    assert not E.puede("grande", estado(salvapantallas=True))


def test_pares_que_coexisten():
    assert E.puede("grande", estado(alarma=True))         # la alarma usa la pantalla grande
    assert E.que_ceder("grande", estado(alarma=True)) == []
    assert E.puede("comida", estado(sentada="barra"))     # comer sentada
    assert E.que_ceder("comida", estado(sentada="barra")) == []


def test_bloqueos_del_salvapantallas():
    for campo in ("arrastrando", "menu_abierto", "hablando", "llamada"):
        assert not E.puede("salvapantallas", estado(**{campo: True})), campo
    assert E.puede("salvapantallas", EstadoAsistente())


def test_que_ceder_ordena_de_mayor_a_menor():
    e = estado(sentada="barra", bailando="mmd", comiendo=True)
    assert E.que_ceder("alarma", e) == ["mmd", "sentada", "comida"]
    assert E.que_ceder("grande", estado(sentada="ventana")) == ["sentada"]
    assert E.que_ceder("juego", estado(grande=True, alarma=True)) == ["alarma", "grande"]


def test_que_ceder_vacio_si_no_puede():
    assert E.que_ceder("sentada", estado(grande=True)) == []


def test_actividad_desconocida():
    with pytest.raises(ValueError):
        E.puede("volar", EstadoAsistente())


# ── BusEstado: iniciar / terminar y reanudar ─────────────────────────────────────
def test_pantalla_grande_levanta_a_la_sentada_y_luego_la_vuelve_a_sentar():
    bus = BusEstado()
    assert bus.iniciar_actividad("sentada", "ventana")
    assert bus.actual().sentada == "ventana"

    r = bus.iniciar_actividad("grande")
    assert r and r.ok
    assert [c.actividad for c in r.ceder] == ["sentada"]
    assert r.ceder[0].valor == "ventana" and r.ceder[0].por == "grande" and r.ceder[0].reanudar
    assert bus.actual().grande is True and bus.actual().sentada == ""

    volver = bus.terminar_actividad("grande")
    assert [(c.actividad, c.valor) for c in volver] == [("sentada", "ventana")]
    assert bus.actual().grande is False
    # el llamador la vuelve a sentar
    assert bus.iniciar_actividad(volver[0].actividad, volver[0].valor)
    assert bus.actual().sentada == "ventana"


def test_no_permitido_no_toca_nada():
    bus = BusEstado(EstadoAsistente(juego=True, sentada="barra"))
    r = bus.iniciar_actividad("grande")
    assert not r and r.motivo == "juego"
    assert bus.actual().grande is False and bus.actual().sentada == "barra"
    assert bus.pendientes() == {}


def test_bloqueo_por_condicion_da_el_motivo():
    bus = BusEstado(EstadoAsistente(arrastrando=True))
    r = bus.iniciar_actividad("salvapantallas")
    assert not r and r.motivo == "arrastrando"


def test_la_comida_se_cancela_y_no_se_reanuda():
    bus = BusEstado()
    bus.iniciar_actividad("comida")
    r = bus.iniciar_actividad("alarma")
    assert [(c.actividad, c.reanudar) for c in r.ceder] == [("comida", False)]
    assert bus.actual().comiendo is False
    assert bus.terminar_actividad("alarma") == []


def test_mmd_apaga_el_baile_automatico_y_lo_recuerda():
    bus = BusEstado()
    bus.iniciar_actividad("baile")
    assert bus.actual().bailando == "musica"
    r = bus.iniciar_actividad("mmd")
    assert [c.actividad for c in r.ceder] == ["baile"]
    assert bus.actual().bailando == "mmd"
    assert [c.actividad for c in bus.terminar_actividad("mmd")] == ["baile"]
    assert bus.actual().bailando == ""


def test_lo_pendiente_pasa_a_quien_interrumpe_a_la_que_interrumpio():
    """Sentada → pantalla grande → empieza un juego: se sienta al acabar el juego."""
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    bus.iniciar_actividad("grande")
    r = bus.iniciar_actividad("juego")
    assert [c.actividad for c in r.ceder] == ["grande"]
    assert "grande" not in bus.pendientes()
    assert [c.actividad for c in bus.pendientes()["juego"]] == ["sentada"]
    assert bus.terminar_actividad("grande") == []         # ya no estaba activa
    volver = bus.terminar_actividad("juego")
    assert [(c.actividad, c.valor) for c in volver] == [("sentada", "barra")]


def test_si_al_terminar_sigue_bloqueada_espera_a_la_que_bloquea():
    """La alarma levanta a la sentada y abre la pantalla grande; al apagar la
    alarma la pantalla grande sigue: se sienta cuando se cierre la grande."""
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    r = bus.iniciar_actividad("alarma")
    assert [c.actividad for c in r.ceder] == ["sentada"]
    assert bus.iniciar_actividad("grande")                # coexiste con la alarma
    assert bus.terminar_actividad("alarma") == []         # la grande sigue: no puede
    assert [c.actividad for c in bus.pendientes()["grande"]] == ["sentada"]
    volver = bus.terminar_actividad("grande")
    assert [(c.actividad, c.valor) for c in volver] == [("sentada", "barra")]


def test_al_terminar_solo_se_reanuda_lo_compatible_de_mayor_a_menor():
    """Sentada → MMD → pantalla grande. Al acabar la grande vuelve el MMD y la
    sentada espera al MMD. Antes se devolvían las dos (primero la sentada) y el
    llamador la sentaba para levantarla en el acto al reanudar el MMD."""
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    bus.iniciar_actividad("mmd")
    bus.iniciar_actividad("grande")
    assert [c.actividad for c in bus.pendientes()["grande"]] == ["sentada", "mmd"]
    volver = bus.terminar_actividad("grande")
    assert [c.actividad for c in volver] == ["mmd"]
    assert [(c.actividad, c.valor, c.por) for c in bus.pendientes()["mmd"]] == [("sentada", "barra", "mmd")]
    assert bus.actual().grande is False and bus.actual().bailando == ""   # el estado real no se toca
    r = bus.iniciar_actividad("mmd")
    assert r and r.ceder == ()                            # nada que levantar
    assert [c.actividad for c in bus.pendientes()["mmd"]] == ["sentada"]
    assert [(c.actividad, c.valor) for c in bus.terminar_actividad("mmd")] == [("sentada", "barra")]


def test_lo_de_menor_prioridad_no_se_devuelve_aunque_este_antes():
    """Baile → sentada (lo cede) → MMD: al acabar el MMD se sienta y el baile
    automático espera a que se levante (no se devuelve para cederse después)."""
    bus = BusEstado()
    bus.iniciar_actividad("baile")
    bus.iniciar_actividad("sentada", "ventana")
    bus.iniciar_actividad("mmd")
    assert [c.actividad for c in bus.pendientes()["mmd"]] == ["baile", "sentada"]
    volver = bus.terminar_actividad("mmd")
    assert [(c.actividad, c.valor) for c in volver] == [("sentada", "ventana")]
    assert [c.actividad for c in bus.pendientes()["sentada"]] == ["baile"]
    for c in volver:
        assert bus.iniciar_actividad(c.actividad, c.valor)
    assert [c.actividad for c in bus.terminar_actividad("sentada")] == ["baile"]


def test_reanudar_despues():
    bus = BusEstado()
    c = E.Cesion("sentada", "barra", "grande", True)
    assert bus.reanudar_despues(c, "juego") is True
    assert bus.reanudar_despues(c, "juego") is True       # sin duplicar
    assert [(x.actividad, x.por) for x in bus.pendientes()["juego"]] == [("sentada", "juego")]
    assert bus.reanudar_despues(c, "arrastrando") is False   # una condición no «termina»
    assert bus.reanudar_despues(E.Cesion("comida", True, "x", False), "juego") is False
    bus.actualizar(juego=True)
    assert [c.actividad for c in bus.terminar_actividad("juego")] == ["sentada"]


def test_no_se_reanuda_lo_que_ya_esta_activo_otra_vez():
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    bus.iniciar_actividad("alarma")
    bus.terminar_actividad("alarma")                      # devuelve la sentada…
    bus.iniciar_actividad("sentada", "barra")             # …y se sienta
    bus.iniciar_actividad("grande")
    bus.actualizar(sentada="barra")                       # alguien la sentó a mano
    assert bus.terminar_actividad("grande") == []


def test_olvidar_reanudar():
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    bus.iniciar_actividad("grande")
    bus.olvidar_reanudar("sentada")                       # «bájate» durante la grande
    assert bus.terminar_actividad("grande") == []
    bus.iniciar_actividad("sentada", "barra")
    bus.iniciar_actividad("grande")
    bus.olvidar_reanudar()
    assert bus.pendientes() == {}


def test_iniciar_y_terminar_notifican_una_vez():
    bus = BusEstado()
    bus.iniciar_actividad("sentada", "barra")
    cambios = []
    bus.suscribir(lambda est, c: cambios.append(c))
    bus.iniciar_actividad("grande")
    assert cambios == [{"sentada": ("barra", ""), "grande": (False, True)}]
    bus.terminar_actividad("grande")
    assert cambios[-1] == {"grande": (True, False)}


def test_sentada_sin_sitio_va_a_la_barra():
    bus = BusEstado()
    bus.iniciar_actividad("sentada")
    assert bus.actual().sentada == "barra"


def test_iniciar_actividad_concurrente_solo_gana_una_del_mismo_nivel():
    bus = BusEstado()
    barrera = threading.Barrier(2)
    resultados = []

    def intenta(act):
        barrera.wait()
        resultados.append((act, bool(bus.iniciar_actividad(act))))
    hilos = [threading.Thread(target=intenta, args=(a,)) for a in ("grande", "salvapantallas")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(5)
    assert sum(ok for _, ok in resultados) == 1
    e = bus.actual()
    assert e.grande != e.salvapantallas
