"""
nucleo/tareas.py (la lista de tareas estilo Microsoft To Do, 10.9) y lo que necesita de nucleo/memoria.py.

Herméticos: SIEMPRE MemoriaManager(path=tmp_path / "memoria.json"), nunca el memoria.json de verdad.
  · agregar (texto limpio, ≤ 200, vacío → ValueError), completar/descompletar, quitar (solo tareas);
  · Mi día por fecha con un reloj falso (al día siguiente ya no están; «Ayer» en las sugerencias);
  · sugerencias: Ayer / Agregado recientemente (14 días, máx. 8, las más nuevas primero) / Más antiguas;
  · recuerdos viejos sin los campos nuevos = pendientes fuera de Mi día; lo anotado hoy desde el chat, en Mi día;
  · resumen_texto en la voz de Lune; el bot de Telegram (datos_clave) y los recuerdos de otros tipos, intactos;
  · memoria: buscar/actualizar/quitar por id, al_cambiar (oyentes que fallan no rompen nada), _sincronizar
    tras una escritura externa (otro MemoriaManager = patata) sin pisar lo del otro, archivo a medio escribir;
  · el system prompt sin las tareas hechas y estable entre mensajes.
"""
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import memoria as nm  # noqa: E402
from nucleo.memoria import MemoriaManager  # noqa: E402
from nucleo.tareas import MAX_RECIENTES, Tareas, disponible, fecha_larga, limpiar_texto  # noqa: E402


class Reloj:
    def __init__(self, t=datetime(2026, 9, 29, 10, 0)):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, **kw):
        self.t = self.t + timedelta(**kw)


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "memoria.json"


@pytest.fixture
def memoria(ruta):
    return MemoriaManager(path=ruta)


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def tareas(memoria, reloj):
    return Tareas(memoria, ahora=reloj)


def _en_disco(ruta):
    return json.loads(ruta.read_text("utf-8"))


def _viejo(ruta, recuerdos, **extra):
    """memoria.json de antes de la 10.9 (sin hecha/hecha_en/mi_dia)."""
    ruta.write_text(json.dumps({"usuario": {"nombre": "Diego", "preferencias": [], "contexto": ""},
                                "recuerdos": recuerdos, "datos_clave": {"ciudad": "Culiacán"},
                                "resumen_sesion_anterior": "", "estadisticas": {"total_mensajes": 12}, **extra},
                               ensure_ascii=False), encoding="utf-8")


# ── Utilidades ──────────────────────────────────────────────────────────────────

def test_fecha_larga_en_espanol_sin_locale():
    assert fecha_larga(datetime(2026, 9, 29).date()) == "martes, 29 de septiembre"
    assert fecha_larga(datetime(2027, 1, 3).date()) == "domingo, 3 de enero"


def test_limpiar_texto():
    assert limpiar_texto("  comprar\t\n pan\x07  ") == "comprar pan"
    assert limpiar_texto("a‮b") == "a b"
    assert len(limpiar_texto("x" * 500)) == 200
    assert limpiar_texto(None) == ""


def test_disponible_solo_con_la_memoria_de_verdad(memoria):
    assert disponible(memoria)
    assert not disponible(object())
    assert not disponible(None)


# ── agregar / completar / quitar ────────────────────────────────────────────────

def test_agregar_a_mi_dia_con_texto_limpio(tareas, ruta, reloj):
    t = tareas.agregar("  Comprar   pan\x07 ")
    assert t == {"id": t["id"], "texto": "Comprar pan", "lista": "Tareas", "creada": "2026-09-29T10:00:00",
                 "hecha": False, "hecha_en": "", "en_mi_dia": True}
    r = next(x for x in _en_disco(ruta)["recuerdos"] if x["id"] == t["id"])
    assert r["tipo"] == "tarea" and r["contenido"] == "Comprar pan"
    assert r["mi_dia"] == "2026-09-29" and r["hecha"] is False and r["hecha_en"] == ""
    assert r["fecha"] == "2026-09-29T10:00:00", "con el reloj de Tareas"
    assert tareas.mi_dia()["pendientes"] == [t]


def test_agregar_valida(tareas):
    for vacio in ("", "   ", "\x07\n", None):
        with pytest.raises(ValueError):
            tareas.agregar(vacio)
    with pytest.raises(ValueError):
        tareas.agregar("algo", tipo="hecho")
    largo = tareas.agregar("x" * 450)
    assert len(largo["texto"]) == 200
    fuera = tareas.agregar("Leer", mi_dia=False)
    assert fuera["en_mi_dia"] is False
    rec = tareas.agregar("Cita el lunes", tipo="recordatorio")
    assert rec["lista"] == "Recordatorios"


def test_completar_y_descompletar(tareas, reloj, ruta):
    t = tareas.agregar("Regar las plantas")
    reloj.avanzar(minutes=30)
    h = tareas.completar(t["id"])
    assert h["hecha"] is True and h["hecha_en"] == "2026-09-29T10:30:00"
    md = tareas.mi_dia()
    assert md["pendientes"] == [] and [x["id"] for x in md["hechas"]] == [t["id"]]
    d = tareas.completar(t["id"], False)
    assert d["hecha"] is False and d["hecha_en"] == ""
    assert [x["id"] for x in tareas.mi_dia()["pendientes"]] == [t["id"]]
    r = next(x for x in _en_disco(ruta)["recuerdos"] if x["id"] == t["id"])
    assert r["hecha"] is False and r["hecha_en"] == ""


def test_id_que_no_es_tarea(tareas, memoria):
    hecho = memoria.agregar_recuerdo("mi cumpleaños es el 3 de mayo", "hecho")
    for rid in ("noexiste", hecho, "", None):
        with pytest.raises(KeyError):
            tareas.completar(rid)
        with pytest.raises(KeyError):
            tareas.al_mi_dia(rid)
        assert tareas.quitar(rid) is False
    assert memoria.buscar_recuerdo(hecho) is not None, "un recuerdo de otro tipo no se toca"


def test_quitar(tareas, ruta):
    a, b = tareas.agregar("A"), tareas.agregar("B")
    assert tareas.quitar(a["id"]) is True
    assert tareas.quitar(a["id"]) is False
    assert [x["id"] for x in tareas.lista()] == [b["id"]]
    assert [x["id"] for x in _en_disco(ruta)["recuerdos"]] == [b["id"]]


# ── Mi día por fecha y sugerencias ─────────────────────────────────────────────

def test_mi_dia_cambia_con_el_dia_y_ayer_sale_en_sugerencias(tareas, reloj):
    a = tareas.agregar("Llamar al banco")
    b = tareas.agregar("Estudiar", mi_dia=False)
    h = tareas.agregar("Tender la ropa")
    tareas.completar(h["id"])
    md = tareas.mi_dia()
    assert md["fecha"] == "2026-09-29" and md["fecha_larga"] == "martes, 29 de septiembre"
    assert [x["id"] for x in md["pendientes"]] == [a["id"]]
    assert [x["id"] for x in md["hechas"]] == [h["id"]]
    sg = tareas.sugerencias()
    assert sg["ayer"] == [] and [x["id"] for x in sg["recientes"]] == [b["id"]]
    assert tareas.contador() == {"hoy": 1, "total": 2}

    reloj.avanzar(days=1)
    md = tareas.mi_dia()
    assert md["fecha_larga"] == "miércoles, 30 de septiembre"
    assert md["pendientes"] == [] and md["hechas"] == [], "Mi día empieza vacío cada día"
    sg = tareas.sugerencias()
    assert {x["id"] for x in sg["ayer"]} == {a["id"], b["id"]}, "estuvo en Mi día ayer o se creó ayer"
    assert sg["recientes"] == [] and sg["antes"] == []
    assert tareas.contador() == {"hoy": 0, "total": 2}

    tareas.al_mi_dia(a["id"])
    assert [x["id"] for x in tareas.mi_dia()["pendientes"]] == [a["id"]]
    assert [x["id"] for x in tareas.sugerencias()["ayer"]] == [b["id"]]
    tareas.al_mi_dia(a["id"], False)
    assert tareas.mi_dia()["pendientes"] == []

    reloj.avanzar(days=1)
    sg = tareas.sugerencias()
    assert sg["ayer"] == [] and {x["id"] for x in sg["recientes"]} == {a["id"], b["id"]}


def test_recientes_maximo_8_las_mas_nuevas_primero_y_el_resto_mas_antiguas(tareas, reloj):
    ids = []
    for i in range(12):
        ids.append(tareas.agregar(f"T{i}", mi_dia=False)["id"])
        reloj.avanzar(hours=1)
    viejo = reloj.t
    reloj.t = viejo - timedelta(days=40)
    muy_vieja = tareas.agregar("Del mes pasado", mi_dia=False)["id"]
    reloj.t = viejo + timedelta(days=3)
    sg = tareas.sugerencias()
    assert len(sg["recientes"]) == MAX_RECIENTES == 8
    assert [x["id"] for x in sg["recientes"]] == list(reversed(ids))[:8]
    assert [x["id"] for x in sg["antes"]] == list(reversed(ids))[8:] + [muy_vieja], "nada pendiente se pierde"


def test_recuerdos_viejos_sin_los_campos_nuevos(ruta, reloj):
    _viejo(ruta, [
        {"id": "v1", "fecha": "2026-09-20T09:00:00", "tipo": "tarea", "contenido": "pagar la luz", "tags": []},
        {"id": "v2", "fecha": "2026-09-28T18:00:00", "tipo": "recordatorio", "contenido": "dentista el lunes", "tags": []},
        {"id": "v3", "fecha": "2026-09-01T09:00:00", "tipo": "hecho", "contenido": "me gusta el café", "tags": []},
        {"id": "v4", "fecha": "roto", "tipo": "tarea", "contenido": "sin fecha buena", "tags": []},
        {"id": 5, "fecha": "2026-09-20T09:00:00", "tipo": "tarea", "contenido": "id raro"},
        "no soy un recuerdo",
    ])
    t = Tareas(MemoriaManager(path=ruta), ahora=reloj)
    lista = {x["id"]: x for x in t.lista()}
    assert set(lista) == {"v1", "v2", "v4"}, "solo tareas y recordatorios con id"
    assert all(not x["hecha"] and not x["en_mi_dia"] for x in lista.values()), "pendientes, fuera de Mi día"
    assert lista["v2"]["lista"] == "Recordatorios"
    sg = t.sugerencias()
    assert [x["id"] for x in sg["ayer"]] == ["v2"]
    assert [x["id"] for x in sg["recientes"]] == ["v1"]
    assert [x["id"] for x in sg["antes"]] == ["v4"]
    assert t.mi_dia()["pendientes"] == []


def test_lo_anotado_hoy_desde_el_chat_sale_en_mi_dia(memoria, reloj):
    reloj.t = datetime.now()                       # el chat usa la hora de verdad
    t = Tareas(memoria, ahora=reloj)
    assert memoria.procesar_mensaje_usuario("recuerda que tengo que comprar leche") is not None
    md = t.mi_dia()
    assert [x["texto"] for x in md["pendientes"]] == ["tengo que comprar leche"]
    reloj.avanzar(days=1)
    assert t.mi_dia()["pendientes"] == []
    assert [x["texto"] for x in t.sugerencias()["ayer"]] == ["tengo que comprar leche"]


def test_pendientes_primero_las_de_mi_dia(tareas, reloj):
    a = tareas.agregar("Fuera", mi_dia=False)
    reloj.avanzar(minutes=1)
    b = tareas.agregar("Hoy 1")
    reloj.avanzar(minutes=1)
    c = tareas.agregar("Hoy 2")
    h = tareas.agregar("Hecha")
    tareas.completar(h["id"])
    assert [x["id"] for x in tareas.pendientes()] == [c["id"], b["id"], a["id"]]


# ── resumen_texto ──────────────────────────────────────────────────────────────

def test_resumen_texto(tareas):
    assert tareas.resumen_texto() == "No tienes tareas pendientes. ¡Día libre!"
    tareas.agregar("Comprar pan.")
    assert tareas.resumen_texto() == "Tienes 1 tarea pendiente: · Comprar pan. Las tienes a la vista en Menú → Tareas."
    tareas.agregar("Llamar a mamá", mi_dia=False)
    tareas.agregar("Estudiar")
    assert tareas.resumen_texto() == ("Tienes 3 tareas pendientes: · Estudiar · Comprar pan · Llamar a mamá. "
                                      "Las tienes a la vista en Menú → Tareas.")
    assert tareas.resumen_texto(max_items=2) == ("Tienes 3 tareas pendientes: · Estudiar · Comprar pan … y 1 más. "
                                                 "Las tienes a la vista en Menú → Tareas.")
    for x in tareas.pendientes():
        tareas.completar(x["id"])
    assert tareas.resumen_texto() == "No tienes tareas pendientes. ¡Día libre!"


# ── Memoria: por id, oyentes, sincronizar ─────────────────────────────────────────

def test_buscar_actualizar_y_quitar_por_id(memoria, ruta):
    rid = memoria.agregar_recuerdo("comprar pan", "tarea", mi_dia="2026-09-29")
    otro = memoria.agregar_recuerdo("comprar pan integral", "tarea")
    assert memoria.buscar_recuerdo(rid)["mi_dia"] == "2026-09-29"
    r = memoria.actualizar_recuerdo(rid, hecha=True, id="pisado")
    assert r["hecha"] is True and r["id"] == rid, "el id no se cambia"
    assert memoria.actualizar_recuerdo("nada", hecha=True) is None
    assert memoria.quitar_recuerdo("comprar") is None, "por id exacto, no por texto"
    assert memoria.quitar_recuerdo(rid)["contenido"] == "comprar pan"
    assert [x["id"] for x in _en_disco(ruta)["recuerdos"]] == [otro]


def test_al_cambiar_avisa_de_cada_cambio_y_un_oyente_roto_no_rompe_nada(memoria):
    vistos = []

    def roto(motivo):
        raise RuntimeError("oyente roto")
    memoria.al_cambiar(roto)
    quitar = memoria.al_cambiar(vistos.append)
    memoria.al_cambiar(vistos.append)                  # dos veces: una sola
    rid = memoria.agregar_recuerdo("A", "tarea")
    memoria.actualizar_recuerdo(rid, hecha=True)
    memoria.quitar_recuerdo(rid)
    assert memoria.procesar_mensaje_usuario("recuerda que tengo que votar") is not None
    assert memoria.procesar_mensaje_usuario("hola, ¿qué tal?") is None
    memoria.procesar_mensaje_usuario("/olvida votar")
    memoria.agregar_recuerdo("B", "tarea")
    memoria.procesar_mensaje_usuario("/olvida todo")
    assert vistos == ["agregar", "actualizar", "olvidar", "agregar", "olvidar", "agregar", "olvidar_todo"]
    quitar()
    memoria.agregar_recuerdo("C", "tarea")
    assert len(vistos) == 7
    memoria.quitar_oyente(roto)
    assert memoria._oyentes == []


def test_sincronizar_tras_escritura_externa_sin_pisar_al_otro(ruta, reloj):
    app = MemoriaManager(path=ruta)
    patata = MemoriaManager(path=ruta)                 # otro proceso, su propio MemoriaManager
    ta, tp = Tareas(app, ahora=reloj), Tareas(patata, ahora=reloj)
    vistos = []
    app.al_cambiar(vistos.append)
    a = ta.agregar("Desde la app")
    p = tp.agregar("Desde patata")                     # patata recarga antes de escribir: no pisa la de la app
    assert {x["texto"] for x in tp.lista()} == {"Desde la app", "Desde patata"}
    assert {x["texto"] for x in ta.lista()} == {"Desde la app", "Desde patata"}, "la app recarga al leer"
    assert "recargar" in vistos
    tp.completar(a["id"])
    app.procesar_mensaje_usuario("hola")               # mutación de la app: recarga antes
    app.procesar_respuesta_lune("¡Hola!")
    d = _en_disco(ruta)
    assert {x["id"]: x.get("hecha") for x in d["recuerdos"]} == {a["id"]: True, p["id"]: False}
    ta.quitar(p["id"])
    assert [x["id"] for x in tp.lista()] == [a["id"]]


def test_sincronizar_suma_los_mensajes_sin_guardar(ruta):
    app, patata = MemoriaManager(path=ruta), MemoriaManager(path=ruta)
    base = app.get_stats().get("total_mensajes", 0)
    app.procesar_mensaje_usuario("uno")                # contado, aún sin escribir
    patata.agregar_recuerdo("algo", "tarea")
    app.procesar_respuesta_lune("respuesta")           # recarga y suma el suyo
    d = _en_disco(ruta)
    assert d["estadisticas"]["total_mensajes"] == base + 1
    assert [x["contenido"] for x in d["recuerdos"]] == ["algo"]


def test_un_archivo_a_medio_escribir_no_se_recarga(ruta, memoria):
    rid = memoria.agregar_recuerdo("importante", "tarea")
    ruta.write_text('{"recuerdos": [', encoding="utf-8")   # otro proceso a medias
    assert memoria._sincronizar() is False
    assert [x["id"] for x in memoria.get_todos_recuerdos()] == [rid], "se queda lo que había"
    memoria.agregar_recuerdo("otra", "tarea")
    assert len(_en_disco(ruta)["recuerdos"]) == 2, "y al guardar deja un JSON entero"


def test_guardado_atomico_sin_temporales(ruta, memoria, monkeypatch):
    memoria.agregar_recuerdo("a", "tarea")
    assert [p.name for p in ruta.parent.iterdir()] == ["memoria.json"]
    # os.replace bloqueado (el otro proceso lo tiene abierto en Windows): escribe directamente
    monkeypatch.setattr(nm.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError("en uso")))
    monkeypatch.setattr(nm, "_PAUSA_REEMPLAZO_S", 0)
    memoria.agregar_recuerdo("b", "tarea")
    assert [p.name for p in ruta.parent.iterdir()] == ["memoria.json"]
    assert [x["contenido"] for x in _en_disco(ruta)["recuerdos"]] == ["a", "b"]


def test_compatible_con_telegram_y_versiones_viejas(ruta, reloj):
    _viejo(ruta, [{"id": "v1", "fecha": "2026-09-20T09:00:00", "tipo": "tarea", "contenido": "pagar", "tags": []}],
           extra_del_bot={"x": 1})
    m = MemoriaManager(path=ruta)
    t = Tareas(m, ahora=reloj)
    t.completar("v1")
    d = _en_disco(ruta)
    assert d["datos_clave"] == {"ciudad": "Culiacán"} and d["extra_del_bot"] == {"x": 1}
    assert set(d["recuerdos"][0]) >= {"id", "fecha", "tipo", "contenido", "tags", "hecha", "hecha_en"}


def test_varios_hilos_no_rompen_el_json(memoria, ruta):
    t = Tareas(memoria)
    errores = []

    def anotar(n):
        try:
            for i in range(15):
                t.agregar(f"{n}-{i}")
        except Exception as e:                          # pragma: no cover - lo que se comprueba
            errores.append(e)
    hilos = [threading.Thread(target=anotar, args=(n,)) for n in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(20)
    assert errores == []
    assert len(_en_disco(ruta)["recuerdos"]) == 60


# ── System prompt ───────────────────────────────────────────────────────────────

def test_el_prompt_no_lleva_las_hechas_y_es_estable(memoria, reloj):
    t = Tareas(memoria, ahora=reloj)
    a = t.agregar("comprar pan")
    b = t.agregar("llamar al banco")
    memoria.agregar_recuerdo("me gusta el café", "preferencia")
    t.completar(a["id"])
    ctx = memoria.obtener_contexto_para_prompt()
    assert "llamar al banco" in ctx and "me gusta el café" in ctx
    assert "comprar pan" not in ctx, "la hecha no va como pendiente"
    assert "Mi día" not in ctx and "10:00" not in ctx
    assert memoria.obtener_contexto_para_prompt() == ctx, "estable entre mensajes"
    memoria.procesar_mensaje_usuario("hola")
    assert memoria.obtener_contexto_para_prompt() == ctx
    t.al_mi_dia(b["id"], False)
    assert memoria.obtener_contexto_para_prompt() == ctx, "Mi día no cambia el prompt"
    t.completar(a["id"], False)
    assert "comprar pan" in memoria.obtener_contexto_para_prompt()


def test_memoria_listar_marca_las_hechas(memoria):
    t = Tareas(memoria)
    a = t.agregar("comprar pan")
    t.completar(a["id"])
    assert "comprar pan (hecha)" in memoria._cmd_listar()
