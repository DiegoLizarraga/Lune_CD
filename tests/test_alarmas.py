"""
Tests de nucleo/alarmas.py (sin Qt, con reloj falso y alarmas.json temporal):

- disparo en el minuto exacto; máscara de días (0 = todos); `una_vez` se desactiva;
- sin doble disparo; dos Programador sobre el mismo archivo en hilos distintos
  disparan UNA vez (reclamo atómico);
- recuperación tras un hueco: ≤ recuperar_min suena con «(hace N min)», más → Perdida;
  temporizador vencido al reabrir; `sonando` recuperado (y lo viejo se tira);
- cambio de hora hacia atrás no repite; `fecha` («mañana a las 9»);
- ids cortos, JSON corrupto apartado, `cambio()` y escritura atómica;
- parsers, resumen y las cuatro herramientas por el ToolManager (esquema del catálogo).
"""
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import alarmas as al  # noqa: E402
from nucleo.alarmas import Almacen, Disparo, Perdida, Programador  # noqa: E402


class Reloj:
    """time.time() falso para el almacén (objetivos de los temporizadores)."""

    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t


def ep(dt: datetime) -> float:
    return dt.timestamp()


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "alarmas.json"


# Sábado 26/09/2026 (weekday 5)
SAB = datetime(2026, 9, 26, 7, 29, 50)


def test_suena_en_el_minuto_exacto_y_no_antes(ruta):
    alm = Almacen(ruta, reloj=Reloj(ep(SAB)))
    a = alm.crear_alarma(7, 30, texto="gimnasio")
    prog = Programador(alm)
    assert prog.tick(SAB, ep(SAB)) == ([], [])
    t = SAB + timedelta(seconds=10)                      # 07:30:00
    disparos, perdidas = prog.tick(t, ep(t))
    assert perdidas == []
    assert [(d.origen, d.texto, d.tipo, d.programado) for d in disparos] == [(a.id, "gimnasio", "alarma", "07:30")]
    assert disparos[0].atraso_s == 0.0
    # Ni en el mismo minuto ni un segundo después vuelve a sonar.
    for s in (1, 20, 59):
        t2 = t + timedelta(seconds=s)
        assert prog.tick(t2, ep(t2)) == ([], [])
    # Queda apuntada en `sonando` y con la clave del minuto.
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["alarmas"][0]["ultimo_minuto"] == "2026-09-26T07:30"
    assert [s["origen"] for s in datos["sonando"]] == [a.id]


def test_mascara_de_dias_cero_es_todos_y_bits_por_dia(ruta):
    alm = Almacen(ruta)
    todos = alm.crear_alarma(8, 0, dias=0)
    lv = alm.crear_alarma(8, 0, dias=al.parsear_dias("lmxjv"))
    sd = alm.crear_alarma(8, 0, dias=al.parsear_dias("sd"))
    prog = Programador(alm)
    sab = datetime(2026, 9, 26, 8, 0, 5)
    lun = datetime(2026, 9, 28, 8, 0, 5)
    assert {d.origen for d in prog.tick(sab, ep(sab))[0]} == {todos.id, sd.id}
    prog2 = Programador(alm)
    assert {d.origen for d in prog2.tick(lun, ep(lun))[0]} == {todos.id, lv.id}


def test_una_vez_se_desactiva_al_sonar(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(9, 15, una_vez=True, texto="pastilla")
    prog = Programador(alm)
    t = datetime(2026, 9, 26, 9, 15, 3)
    assert [d.origen for d in prog.tick(t, ep(t))[0]] == [a.id]
    assert alm.obtener(a.id).activa is False
    manana = t + timedelta(days=1)
    assert Programador(alm).tick(manana, ep(manana)) == ([], [])


def test_alarma_apagada_no_suena(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(9, 15)
    assert alm.actualizar(a.id, activa=False)
    t = datetime(2026, 9, 26, 9, 15, 3)
    assert Programador(alm).tick(t, ep(t)) == ([], [])


def test_dos_programadores_en_hilos_disparan_una_sola_vez(ruta):
    Almacen(ruta).crear_alarma(7, 30, texto="una sola vez")
    t = datetime(2026, 9, 26, 7, 30, 1)
    Almacen(ruta, reloj=Reloj(ep(t) - 61)).crear_temporizador(60, "tempo")
    resultados = []
    barrera = threading.Barrier(2)

    def correr():
        prog = Programador(Almacen(ruta, reloj=Reloj(ep(t))))   # su propio almacén y su caché
        prog.almacen.leer()                                     # la caché ve la alarma sin reclamar
        barrera.wait()
        resultados.append(prog.tick(t, ep(t))[0])               # el temporizador también venció

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    todos = [d for r in resultados for d in r]
    assert sorted(d.tipo for d in todos) == ["alarma", "temporizador"]   # cada una UNA vez
    assert sum(len(r) for r in resultados) == 2


def test_dos_procesos_simulados_no_duplican_temporizador(ruta):
    alm = Almacen(ruta, reloj=Reloj(1000.0))
    t = alm.crear_temporizador(30, "pizza")
    a, b = Programador(Almacen(ruta)), Programador(Almacen(ruta))
    ahora = datetime(2026, 9, 26, 12, 0, 0)
    d1, _ = a.tick(ahora, 1031.0)
    d2, _ = b.tick(ahora, 1031.5)
    assert [d.origen for d in d1] == [t.id] and d2 == []
    assert d1[0].tipo == "temporizador" and d1[0].texto == "pizza"


def test_recuperacion_tras_suspension_hace_n_min(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(7, 30, texto="gimnasio")
    prog = Programador(alm, recuperar_min=10)
    antes = datetime(2026, 9, 26, 7, 25, 0)
    prog.tick(antes, ep(antes))
    despierta = datetime(2026, 9, 26, 7, 36, 10)            # el PC durmió 11 min
    disparos, perdidas = prog.tick(despierta, ep(despierta))
    assert perdidas == []
    assert len(disparos) == 1 and disparos[0].origen == a.id
    assert 6 * 60 <= disparos[0].atraso_s < 7 * 60
    assert al.texto_visible(disparos[0]) == "gimnasio (hace 6 min)"
    assert abs(disparos[0].t - ep(datetime(2026, 9, 26, 7, 30))) < 1


def test_mas_de_recuperar_min_es_perdida(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(7, 30, texto="gimnasio")
    prog = Programador(alm, recuperar_min=10)
    antes = datetime(2026, 9, 26, 7, 0, 0)
    prog.tick(antes, ep(antes))
    tarde = datetime(2026, 9, 26, 7, 55, 0)
    disparos, perdidas = prog.tick(tarde, ep(tarde))
    assert disparos == []
    assert perdidas == [Perdida(a.id, "gimnasio", datetime(2026, 9, 26, 7, 30), "alarma")]
    assert al.texto_perdida(perdidas[0], tarde) == (
        "Se pasó la alarma de las 07:30 «gimnasio» mientras Lune no estaba")
    # Y ya no vuelve a salir.
    assert prog.tick(tarde + timedelta(seconds=1), ep(tarde) + 1) == ([], [])


def test_recuperacion_al_arrancar_desde_visto_hasta(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(7, 30, texto="café")
    cerrada = datetime(2026, 9, 26, 7, 20, 0)
    Programador(alm).tick(cerrada, ep(cerrada))              # escribe visto_hasta
    assert alm.visto_hasta() == pytest.approx(ep(cerrada))
    # La app se cierra y se abre a las 07:34 con un Programador nuevo.
    reabre = datetime(2026, 9, 26, 7, 34, 0)
    disparos, perdidas = Programador(Almacen(ruta)).tick(reabre, ep(reabre))
    assert [d.origen for d in disparos] == [a.id] and perdidas == []
    assert al.texto_visible(disparos[0]) == "café (hace 4 min)"


def test_sin_visto_hasta_no_se_recupera_nada(ruta):
    alm = Almacen(ruta)
    alm.crear_alarma(7, 30)
    reabre = datetime(2026, 9, 26, 7, 34, 0)
    assert Programador(alm).tick(reabre, ep(reabre)) == ([], [])


def test_marcar_visto_evita_recuperar(ruta):
    alm = Almacen(ruta)
    alm.crear_alarma(7, 30)
    Programador(alm).tick(datetime(2026, 9, 26, 7, 0), ep(datetime(2026, 9, 26, 7, 0)))
    reactiva = datetime(2026, 9, 26, 7, 35)
    alm.marcar_visto(ep(reactiva))
    assert Programador(alm).tick(reactiva, ep(reactiva)) == ([], [])


def test_temporizador_vencido_al_reabrir(ruta):
    reloj = Reloj(10_000.0)
    alm = Almacen(ruta, reloj=reloj)
    t_ok = alm.crear_temporizador(300, "pizza")
    t_viejo = alm.crear_temporizador(60, "té")
    # Se reabre 8 min después: la pizza venció hace 3 min (suena), el té hace 7 min (suena).
    ahora = datetime(2026, 9, 26, 12, 8, 0)
    disparos, perdidas = Programador(Almacen(ruta)).tick(ahora, 10_000.0 + 480)
    assert {d.origen for d in disparos} == {t_ok.id, t_viejo.id} and perdidas == []
    pizza = next(d for d in disparos if d.origen == t_ok.id)
    assert al.texto_visible(pizza) == "pizza (hace 3 min)"
    # Otro que venció hace 30 min: Perdida.
    alm2 = Almacen(ruta, reloj=Reloj(20_000.0))
    t3 = alm2.crear_temporizador(60, "ropa")
    d, p = Programador(Almacen(ruta)).tick(ahora, 20_000.0 + 60 + 1800)
    assert d == [] and [x.origen for x in p] == [t3.id] and p[0].tipo == "temporizador"
    assert "Se acabó el temporizador «ropa»" in al.texto_perdida(p[0], ahora)


def test_temporizador_no_una_vez_se_rearma_y_una_vez_se_borra(ruta):
    reloj = Reloj(0.0)
    alm = Almacen(ruta, reloj=reloj)
    fijo = alm.crear_temporizador(10, "fijo")
    rapido = alm.crear_temporizador(10, "rápido", una_vez=True)
    ahora = datetime(2026, 9, 26, 12, 0, 0)
    d, _ = Programador(alm).tick(ahora, 11.0)
    assert {x.origen for x in d} == {fijo.id, rapido.id}
    assert alm.obtener(rapido.id) is None
    f = alm.obtener(fijo.id)
    assert (f.activo, f.objetivo, f.restante_s) == (False, 0.0, 10)


def test_pospuesta_suena_como_pospuesta(ruta):
    alm = Almacen(ruta, reloj=Reloj(0.0))
    alm.crear_temporizador(300, "gimnasio", una_vez=True, pospuesta=True)
    d, _ = Programador(alm).tick(datetime(2026, 9, 26, 12, 5), 300.5)
    assert d[0].tipo == "pospuesta" and d[0].texto == "gimnasio"


def test_sonando_recuperado_y_lo_viejo_se_tira(ruta):
    alm = Almacen(ruta, reloj=Reloj(5000.0))
    reciente = Disparo("a1", "gimnasio", "alarma", 0.0, "07:30", 5000.0 - 240)
    viejo = Disparo("a2", "viejo", "alarma", 0.0, "06:00", 5000.0 - 3600)
    prueba = Disparo("prueba", "Prueba", "prueba", 0.0, "07:00", 4990.0)
    for d in (reciente, viejo, prueba):
        alm.anotar_sonando(d)
    assert [d.origen for d in alm.sonando()] == ["a1", "a2"]      # la prueba no se guarda
    rec = Programador(alm, recuperar_min=10).recuperar_sonando(5000.0)
    assert [d.origen for d in rec] == ["a1"]
    assert al.texto_visible(rec[0]) == "gimnasio (hace 4 min)"
    assert [d.origen for d in alm.sonando()] == ["a1"]            # sigue sonando hasta apagarla
    alm.quitar_sonando(rec[0])
    assert alm.sonando() == []


def test_cambio_de_hora_hacia_atras_no_repite(ruta):
    alm = Almacen(ruta)
    alm.crear_alarma(2, 30)
    prog = Programador(alm)
    t = datetime(2026, 10, 25, 2, 30, 5)
    assert len(prog.tick(t, ep(t))[0]) == 1
    # El reloj retrocede una hora (horario de verano o a mano): 02:30 otra vez.
    atras = datetime(2026, 10, 25, 2, 30, 5)
    assert prog.tick(atras - timedelta(hours=1), ep(t) + 60) == ([], [])
    assert prog.tick(atras, ep(t) + 3600) == ([], [])


def test_fecha_solo_ese_dia_y_la_pasada_se_apaga(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(9, 0, texto="médico", fecha="2026-09-27")
    assert a.una_vez
    hoy = datetime(2026, 9, 26, 9, 0, 5)
    assert Programador(alm).tick(hoy, ep(hoy)) == ([], [])
    manana = datetime(2026, 9, 27, 9, 0, 5)
    d, _ = Programador(alm).tick(manana, ep(manana))
    assert [x.origen for x in d] == [a.id] and alm.obtener(a.id).activa is False
    # Una con fecha que ya pasó (creada tarde): se apaga sola sin sonar.
    b = alm.crear_alarma(7, 0, fecha="2026-09-27")
    luego = datetime(2026, 9, 27, 10, 0, 0)
    assert Programador(alm).tick(luego, ep(luego)) == ([], [])
    assert alm.obtener(b.id).activa is False


def test_ids_cortos_y_sin_repetir(ruta):
    alm = Almacen(ruta)
    ids = [alm.crear_alarma(7, i).id for i in range(3)] + [alm.crear_temporizador(60).id for _ in range(2)]
    assert ids == ["a1", "a2", "a3", "t1", "t2"]
    assert alm.borrar("a2") and not alm.borrar("a2")
    assert alm.crear_alarma(8, 0).id == "a4"


def test_json_corrupto_se_aparta(ruta):
    ruta.write_text("{esto no es json", encoding="utf-8")
    alm = Almacen(ruta)
    assert alm.alarmas() == []
    apartados = list(ruta.parent.glob("alarmas.json.corrupto-*"))
    assert len(apartados) == 1 and apartados[0].read_text(encoding="utf-8") == "{esto no es json"
    a = alm.crear_alarma(7, 0)
    assert json.loads(ruta.read_text(encoding="utf-8"))["alarmas"][0]["id"] == a.id


def test_entradas_invalidas_se_descartan(ruta):
    ruta.write_text(json.dumps({"version": 1, "alarmas": [
        {"id": "a1", "hora": 7, "minuto": 30},
        {"id": "a2", "hora": 25, "minuto": 0},
        {"id": "mal id!", "hora": 7, "minuto": 0},
        "basura",
    ], "temporizadores": [{"id": "t1", "duracion_s": 0}, {"id": "t2", "duracion_s": 60}]}), encoding="utf-8")
    alm = Almacen(ruta)
    assert [a.id for a in alm.alarmas()] == ["a1"]
    assert [t.id for t in alm.temporizadores()] == ["t2"]


def test_cambio_detecta_otros_escritores_y_no_visto_hasta(ruta):
    mio, otro = Almacen(ruta), Almacen(ruta)
    assert mio.cambio() is False
    otro.crear_alarma(7, 0)
    assert mio.cambio() is True and mio.cambio() is False
    mio.crear_alarma(8, 0)
    assert mio.cambio() is True
    otro.marcar_visto(123456.0)
    assert mio.cambio() is False
    assert mio.visto_hasta() == 123456.0


def test_escritura_atomica_sin_temporales(ruta):
    alm = Almacen(ruta)
    for i in range(5):
        alm.crear_alarma(7, i)
    assert [p.name for p in ruta.parent.iterdir()] == ["alarmas.json"]


def test_temporizador_iniciar_parar_reiniciar(ruta):
    reloj = Reloj(100.0)
    alm = Almacen(ruta, reloj=reloj)
    t = alm.crear_temporizador(600, "horno", iniciar=False)
    assert not alm.obtener(t.id).corriendo
    assert alm.temporizador(t.id, "iniciar")
    assert alm.obtener(t.id).objetivo == 700.0
    reloj.t = 350.0
    assert alm.temporizador(t.id, "parar")
    x = alm.obtener(t.id)
    assert (x.corriendo, x.restante_s) == (False, 350)
    reloj.t = 1000.0
    alm.temporizador(t.id, "iniciar")
    assert alm.obtener(t.id).objetivo == 1350.0
    assert alm.temporizador(t.id, "reiniciar")
    x = alm.obtener(t.id)
    assert (x.corriendo, x.restante_s) == (False, 600)
    assert not alm.temporizador(t.id, "explotar") and not alm.temporizador("t99", "iniciar")


def test_actualizar_valida(ruta):
    alm = Almacen(ruta)
    a = alm.crear_alarma(7, 0)
    assert alm.actualizar(a.id, hora=8, minuto=15, dias="lx", texto="  hola\x07 mundo ")
    x = alm.obtener(a.id)
    assert (x.hora, x.minuto, x.dias, x.texto) == (8, 15, 0b101, "hola mundo")
    with pytest.raises(ValueError):
        alm.actualizar(a.id, hora=30)
    with pytest.raises(ValueError):
        alm.actualizar(a.id, color="rojo")
    assert not alm.actualizar("a9", hora=1)
    with pytest.raises(ValueError):
        alm.crear_alarma(24, 0)


def test_proxima(ruta):
    alm = Almacen(ruta, reloj=Reloj(ep(datetime(2026, 9, 26, 10, 0))))
    alm.crear_alarma(7, 0, dias="lmxjv", texto="trabajo")
    ahora = datetime(2026, 9, 26, 10, 0)                          # sábado
    o, obj = alm.proxima(ahora)
    assert o == datetime(2026, 9, 28, 7, 0) and obj.texto == "trabajo"
    alm.crear_temporizador(600, "té")
    o, obj = alm.proxima(ahora)
    assert o == datetime(2026, 9, 26, 10, 10) and obj.texto == "té"


# ── Parsers ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("txt,esperado", [
    ("7", (7, 0)), ("07:30", (7, 30)), ("7.05", (7, 5)), ("19h", (19, 0)), ("7pm", (19, 0)),
    ("12am", (0, 0)), ("12 pm", (12, 0)), ("7:30 a.m.", (7, 30)), ("1945", (19, 45)),
])
def test_parsear_hora(txt, esperado):
    assert al.parsear_hora(txt) == esperado


@pytest.mark.parametrize("txt", ["", "25:00", "7:61", "13pm", "hola", "7:3"])
def test_parsear_hora_invalida(txt):
    with pytest.raises(ValueError):
        al.parsear_hora(txt)


@pytest.mark.parametrize("txt,esperado", [
    ("", 0), ("lmxjv", 0b0011111), ("sd", 0b1100000), ("todos", 127), ("laborables", 31),
    ("lunes, viernes", 0b10001), ("sábado y domingo", 96), (5, 5),
])
def test_parsear_dias(txt, esperado):
    assert al.parsear_dias(txt) == esperado


def test_texto_dias():
    assert al.texto_dias(0) == al.texto_dias(127) == "todos los días"
    assert al.texto_dias(31) == "de lunes a viernes"
    assert al.texto_dias(96) == "sábados y domingos"
    assert al.texto_dias(0b10101) == "lunes, miércoles y viernes"
    assert al.letras_dias(0b10101) == "lxv"


@pytest.mark.parametrize("txt,seg", [
    ("10m", 600), ("1h30", 5400), ("90s", 90), ("1:30", 90), ("1:00:00", 3600), ("10", 600),
    ("1.5h", 5400), ("2 horas y 10 minutos", 7800), ("5 min", 300),
])
def test_parsear_duracion(txt, seg):
    assert al.parsear_duracion(txt) == seg


@pytest.mark.parametrize("txt", ["", "0", "abc", "10x", "1:75", "999h"])
def test_parsear_duracion_invalida(txt):
    with pytest.raises(ValueError):
        al.parsear_duracion(txt)


def test_formatos():
    assert al.formato_duracion(90) == "1 min 30 s"
    assert al.formato_duracion(5400) == "1 h 30 min"
    assert al.reloj_restante(272) == "4:32" and al.reloj_restante(3872) == "1:04:32"


# ── Resumen y herramientas ───────────────────────────────────────────────────────

def test_resumen_con_ids(ruta):
    reloj = Reloj(ep(datetime(2026, 9, 26, 10, 0)))
    alm = Almacen(ruta, reloj=reloj)
    assert al.resumen(alm) == "No hay alarmas ni temporizadores."
    a = alm.crear_alarma(7, 30, dias="lmxjv", texto="gimnasio")
    b = alm.crear_alarma(22, 0, una_vez=True, texto="pastillas")
    alm.actualizar(b.id, activa=False)
    t = alm.crear_temporizador(600, "pizza")
    texto = al.resumen(alm, datetime(2026, 9, 26, 10, 0), reloj.t + 128)
    assert f"{a.id} · 07:30 · de lunes a viernes · gimnasio" in texto
    assert f"{b.id} · 22:00 · una vez · pastillas (apagada)" in texto
    assert f"{t.id} · 10 min · pizza · quedan 7:52" in texto
    assert "Próxima: hoy a las 10:10 (pizza)" in texto


def _tools(alm, config=None):
    from servicios.tools import ToolManager
    tm = ToolManager()
    al.registrar_herramientas(tm, alm, config)
    return tm


def test_herramientas_por_el_toolmanager(ruta):
    alm = Almacen(ruta)
    tm = _tools(alm)
    for n in ("temporizador", "alarma", "cancelar_alarma", "listar_alarmas"):
        assert tm.tiene_handler(n)
    r = tm.ejecutar("temporizador", args={"segundos": 300, "texto": "sacar la pizza"})
    assert r.ok and "5 min" in r.mensaje and "«sacar la pizza»" in r.mensaje
    t = alm.temporizadores()[0]
    assert (t.duracion_s, t.una_vez, t.corriendo) == (300, True, True)
    r = tm.ejecutar("alarma", args={"hora": "07:30", "dias": "lmxjv", "texto": "gimnasio"})
    assert r.ok and "de lunes a viernes" in r.mensaje
    r = tm.ejecutar("alarma", args={"hora": "22:00", "dias": "", "texto": "pastillas"})
    assert r.ok and "una sola vez" in r.mensaje
    alarmas = alm.alarmas()
    assert [(x.hhmm, x.dias, x.una_vez) for x in alarmas] == [("07:30", 31, False), ("22:00", 0, True)]
    listado = tm.ejecutar("listar_alarmas", args={})
    assert listado.ok and "a1" in listado.mensaje and "t1" in listado.mensaje
    r = tm.ejecutar("cancelar_alarma", args={"id": "a1"})
    assert r.ok and "gimnasio" in r.mensaje
    r = tm.ejecutar("cancelar_alarma", args={"id": "a1"})
    assert not r.ok
    # El esquema del catálogo manda: fuera de rango no llega al handler.
    assert not tm.ejecutar("temporizador", args={"segundos": 0}).ok
    assert not tm.ejecutar("alarma", args={"hora": "25:00"}).ok


def test_herramienta_alarma_con_fecha_y_aviso_apagadas(ruta):
    class Cfg:
        def get(self, s, k, d=None):
            return False if (s, k) == ("alarmas", "activo") else d
    alm = Almacen(ruta)
    h = al.handlers(alm, Cfg())
    r = h["alarma"]({"hora": "09:00", "dias": "", "texto": "médico", "fecha": "2026-09-27"}, None)
    assert "apagadas" in r
    a = alm.alarmas()[0]
    assert (a.fecha, a.una_vez) == ("2026-09-27", True)


def test_handlers_llaman_al_cambiar(ruta):
    avisos = []
    h = al.handlers(Almacen(ruta), al_cambiar=lambda: avisos.append(1))
    h["temporizador"]({"segundos": 60}, None)
    h["listar_alarmas"]({}, None)
    assert avisos == [1]


# ── Revisión 4-5-6 ─────────────────────────────────────────────────────────────

def test_cambio_al_horario_de_verano_suena_al_saltar(ruta):
    """MO12: el reloj de pared salta de 02:00 a 03:00 con Lune abierta (en un segundo de
    verdad): la alarma de las 02:30 suena al saltar, sin «(hace N min)»; antes era una
    Perdida («…mientras Lune no estaba») y las de <10 min sonaban «(hace N min)»."""
    alm = Almacen(ruta)
    a = alm.crear_alarma(2, 30, texto="pastilla")
    b = alm.crear_alarma(2, 55, texto="otra")
    prog = Programador(alm, recuperar_min=10)
    antes = datetime(2027, 3, 28, 1, 59, 59)
    e = 1_806_000_000.0
    assert prog.tick(antes, e) == ([], [])
    despues = datetime(2027, 3, 28, 3, 0, 0)                 # 1 s de verdad después
    disparos, perdidas = prog.tick(despues, e + 1)
    assert perdidas == []
    assert sorted(d.origen for d in disparos) == [a.id, b.id]
    assert all(d.atraso_s <= 1 for d in disparos)
    assert [al.texto_visible(d) for d in sorted(disparos, key=lambda d: d.origen)] == ["pastilla", "otra"]
    assert all(abs(d.t - e) <= 1 for d in disparos)
    # Una suspensión de verdad (el epoch también avanza) sigue siendo una Perdida.
    alm2 = Almacen(ruta.with_name("otro.json"))
    c = alm2.crear_alarma(2, 30)
    prog2 = Programador(alm2, recuperar_min=10)
    prog2.tick(antes, e)
    d2, p2 = prog2.tick(despues, e + 3601)
    assert d2 == [] and [p.origen for p in p2] == [c.id]


def test_editar_una_alarma_con_fecha_y_ponerle_dias_quita_la_fecha(ruta):
    """MO3: «despiértame mañana a las 7» editada a lunes-viernes conservaba la fecha oculta
    y no volvía a sonar nunca (aunque salía «activa»)."""
    alm = Almacen(ruta)
    a = alm.crear_alarma(7, 0, fecha="2026-09-27")
    assert alm.actualizar(a.id, hora=7, minuto=0, dias=al.parsear_dias("lmxjv"), una_vez=False, texto="", activa=True)
    x = alm.obtener(a.id)
    assert x.fecha == "" and x.dias == al.LABORABLES and not x.una_vez
    lunes = datetime(2026, 9, 28, 6, 0)
    assert al.ocurrencia_siguiente(x, lunes) == datetime(2026, 9, 28, 7, 0)
    t = datetime(2026, 9, 28, 7, 0, 5)
    assert [d.origen for d in Programador(alm).tick(t, ep(t))[0]] == [a.id]
    # Quitar «una vez» (todos los días) también la quita.
    b = alm.crear_alarma(8, 0, fecha="2026-09-27")
    alm.actualizar(b.id, una_vez=False)
    assert alm.obtener(b.id).fecha == ""
    # Cambiar solo la hora (sigue siendo «mañana, una vez») la conserva.
    c = alm.crear_alarma(9, 0, fecha="2026-09-27")
    alm.actualizar(c.id, hora=10, minuto=0, dias=0, una_vez=True, texto="x")
    assert alm.obtener(c.id).fecha == "2026-09-27"
    # Y quien la manda explícitamente manda.
    alm.actualizar(c.id, dias=al.parsear_dias("s"), fecha="2026-10-03")
    assert alm.obtener(c.id).fecha == "2026-10-03"


@pytest.mark.parametrize("contenido", [
    '{"alarmas": 5}',
    '{"alarmas": "x", "temporizadores": 7, "sonando": 7}',
    '{"alarmas": {"a": 1}}',
    '{"alarmas": [{"id": "a1", "hora": Infinity, "minuto": 0}]}',
    '{"alarmas": [{"id": "a1", "hora": 7, "minuto": 0, "dias": -Infinity}]}',
    '{"temporizadores": [{"id": "t1", "duracion_s": NaN}]}',
    '{"alarmas": [{"id": "a1", "hora": 1e308, "minuto": 0, "dias": 1e300}]}',
    '{"temporizadores": [{"id": "t1", "duracion_s": 10, "restante_s": 1e400}]}',
    '{"temporizadores": [{"id": "t1", "duracion_s": 10, "objetivo": 1e300, "activo": true}]}',
    '{"sonando": [{"tipo": "alarma", "t": 1e300, "texto": "x"}], "visto_hasta": 1e300}',
    '{"alarmas": [{"id": "a1", "hora": 7, "minuto": 0, "texto": {"a": [1, 2]}, "fecha": 5}]}',
])
def test_alarmas_json_valido_con_tipos_raros_no_rompe_nada(ruta, contenido):
    """SB1: JSON válido pero con tipos imposibles (números enormes, Infinity/NaN, listas que
    no son listas): antes cada lectura, tick y creación lanzaban (TypeError/OverflowError)."""
    ruta.write_text(contenido, encoding="utf-8")
    alm = Almacen(ruta)
    ahora = datetime(2026, 9, 26, 7, 0)
    alm.leer()
    alm.proxima(ahora)
    alm.sonando()
    al.resumen(alm, ahora, ep(ahora))
    Programador(alm).tick(ahora, ep(ahora))
    Programador(alm).recuperar_sonando(ep(ahora))
    a = alm.crear_alarma(8, 0, texto="nueva")
    assert [x.id for x in alm.alarmas() if x.texto == "nueva"] == [a.id]
    guardado = json.loads(ruta.read_text(encoding="utf-8"))           # lo que se escribe es JSON limpio
    assert isinstance(guardado["alarmas"], list) and isinstance(guardado["sonando"], list)


def test_infinity_o_nan_apartan_el_archivo_como_corrupto(ruta):
    ruta.write_text('{"alarmas": [{"id": "a1", "hora": Infinity, "minuto": 0}]}', encoding="utf-8")
    assert Almacen(ruta).alarmas() == []
    assert len(list(ruta.parent.glob("alarmas.json.corrupto-*"))) == 1


def test_normalizar_que_lanza_aparta_el_archivo(ruta, monkeypatch):
    """Si aun así la normalización revienta con algo imprevisto, el archivo se aparta como
    corrupto y se sigue vacío (antes la excepción salía en cada lectura, cada segundo)."""
    ruta.write_text('{"alarmas": []}', encoding="utf-8")

    def roto(_crudo):
        raise RuntimeError("tipo imposible")
    monkeypatch.setattr(al, "_normalizar", roto)
    alm = Almacen(ruta)
    assert alm.leer()["alarmas"] == []
    assert len(list(ruta.parent.glob("alarmas.json.corrupto-*"))) == 1
    monkeypatch.undo()
    assert alm.crear_alarma(7, 0).id == "a1"
