"""
Tests de nucleo/alarmas_nl.detectar: frases en español → temporizador o alarma
(con argumentos que cumplen el esquema del catálogo), y None cuando no hay una
hora ni una duración explícitas (eso sigue yendo a la memoria o al modelo).
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.alarmas_nl import detectar  # noqa: E402

SAB_14H = datetime(2026, 9, 26, 14, 0)     # sábado a las 14:00
SAB_3H = datetime(2026, 9, 26, 3, 0)


@pytest.mark.parametrize("frase,segundos,texto", [
    ("avísame en 10 minutos", 600, ""),
    ("Avísame en 5 min que saque la pizza", 300, "saque la pizza"),
    ("pon un temporizador de 1 hora y media", 5400, ""),
    ("recuérdame en media hora llamar a mamá", 1800, "llamar a mamá"),
    ("temporizador de 90 segundos", 90, ""),
    ("despiértame en 20 minutos", 1200, ""),
    ("pon una alarma en 15 minutos", 900, ""),
    ("recuérdame sacar la ropa en 2 horas", 7200, "sacar la ropa"),
    ("¿me puedes avisar en 10 minutos?", 600, ""),
    ("en 15 minutos avísame que apague el horno", 900, "apague el horno"),
    ("pon un temporizador de 1:30", 90, ""),
    ("avísame dentro de una hora y veinte minutos", 4800, ""),
    ("pon un timer de 3 minutos y 30 segundos para el té", 210, "el té"),
    ("avisame en un cuarto de hora", 900, ""),
])
def test_temporizadores(frase, segundos, texto):
    assert detectar(frase, SAB_14H) == ("temporizador", {"segundos": segundos, "texto": texto})


@pytest.mark.parametrize("frase,hora,dias,texto,fecha", [
    ("pon una alarma a las 7:30 de la mañana", "07:30", "", "", None),
    ("programa una alarma a las 10 de la noche de lunes a viernes", "22:00", "lmxjv", "", None),
    ("crea una alarma para las 6 y media los sábados y domingos para correr", "06:30", "sd", "correr", None),
    ("recuérdame que a las 5 tengo cita", "17:00", "", "tengo cita", None),
    ("despiértame mañana a las 7", "07:00", "", "", "2026-09-27"),
    ("alarma a las 8 menos cuarto todos los días", "07:45", "lmxjvsd", "", None),
    ("avísame a las 3 pm para la reunión", "15:00", "", "la reunión", None),
    ("oye Lune, pon una alarma a las 19:45 para la cena", "19:45", "", "la cena", None),
    ("recuérdame el lunes a las 9 llamar al banco", "09:00", "", "llamar al banco", "2026-09-28"),
    ("alarma a las 6 los lunes, miércoles y viernes gimnasio", "06:00", "lxv", "gimnasio", None),
    ("pon una alarma al mediodía", "12:00", "", "", None),
    ("despiértame a las 12 de la noche", "00:00", "", "", None),
    ("pon una alarma a las 7 de la tarde", "19:00", "", "", None),
])
def test_alarmas(frase, hora, dias, texto, fecha):
    tipo, args = detectar(frase, SAB_14H)
    esperado = {"hora": hora, "dias": dias, "texto": texto}
    if fecha:
        esperado["fecha"] = fecha
    assert (tipo, args) == ("alarma", esperado)


def test_hora_ambigua_toma_la_proxima():
    # «a las 5» sin más: a las 14:00 → 17:00; a las 03:00 → 05:00.
    assert detectar("recuérdame que a las 5 tengo cita", SAB_14H)[1]["hora"] == "17:00"
    assert detectar("recuérdame que a las 5 tengo cita", SAB_3H)[1]["hora"] == "05:00"
    # Con días de la semana, tal cual.
    assert detectar("pon una alarma a las 7 los lunes", SAB_14H)[1]["hora"] == "07:00"


@pytest.mark.parametrize("frase", [
    "recuerda que mi cumple es el 5",
    "recuerda que mañana tengo cita",
    "recuérdame comprar pan",
    "¿qué hora es?",
    "no me avises en 5 minutos",
    "busca un temporizador de cocina en amazon",
    "tengo que estudiar 2 horas",
    "a las 5 hay partido",
    "",
    "hola lune",
])
def test_no_es_alarma(frase):
    assert detectar(frase, SAB_14H) is None


@pytest.mark.parametrize("frase", [
    # Revisión 4-5-6 (MO1/RH1): frases que NO son peticiones y antes creaban un
    # temporizador o una alarma comiéndose el turno de la IA.
    "cancela el temporizador de 10 minutos",
    "quita el temporizador de 5 minutos",
    "borra la alarma de las 7",
    "para el temporizador de 10 minutos",
    "apaga la alarma de las 7",
    "cambia la alarma de las 7 a las 8",
    "pospón la alarma 10 minutos",
    "pon una alarma a las 7 y quita la de las 8",
    "¿cuánto le queda al temporizador de 10 minutos?",
    "el temporizador de 10 minutos ya sonó",
    "temporizador de 10 minutos ya sonó",
    "¿cómo puedo poner una alarma a las 7 en mi celular?",
    "¿cómo se pone una alarma a las 7 en el móvil?",
    "pon una alarma a las 7 en mi celular",
    "ayer se me olvidó poner la alarma a las 7 y llegué tarde",
    "se me olvidó poner la alarma a las 7",
    "¿puedes explicarme cómo funciona un temporizador de 10 minutos?",
    "cómo hago un temporizador de 5 minutos en python",
    "crea un temporizador de 5 minutos en python",
    "alarma a las 7 no funciona en mi móvil",
    "mi jefe me dijo: avísame en 10 minutos",
    "¿por qué no sonó la alarma de las 7?",
    "el temporizador de la cocina es de 5 minutos",
    "¿qué alarma tengo a las 7?",
    "¿avísame en 10 minutos?",
    "no pongas una alarma a las 7",
    "nunca me avises a las 3",
    "ponle a la pizza un temporizador de 15 minutos",
])
def test_lo_que_no_es_una_peticion_no_se_detecta(frase):
    assert detectar(frase, SAB_14H) is None


@pytest.mark.parametrize("frase,esperado", [
    ("oye Lune, porfa avísame en 10 minutos", ("temporizador", {"segundos": 600, "texto": ""})),
    ("Lune, pon un temporizador de 5 minutos", ("temporizador", {"segundos": 300, "texto": ""})),
    ("quiero que me avises en 5 minutos", ("temporizador", {"segundos": 300, "texto": ""})),
    ("¿me podrías poner una alarma a las 7 de la tarde?", ("alarma", {"hora": "19:00", "dias": "", "texto": ""})),
    ("porfa recuérdame a las 9 de la noche tomar la pastilla",
     ("alarma", {"hora": "21:00", "dias": "", "texto": "tomar la pastilla"})),
])
def test_peticiones_con_relleno_delante(frase, esperado):
    assert detectar(frase, SAB_14H) == esperado


def test_esta_manana_no_es_manana():
    # MO9: «esta mañana» califica la hora; antes ganaba «mañana» (fecha de mañana y texto «esta»).
    a_las_9 = datetime(2026, 9, 26, 9, 0)
    assert detectar("pon una alarma esta mañana a las 11", a_las_9) == (
        "alarma", {"hora": "11:00", "dias": "", "texto": ""})
    assert detectar("avísame esta tarde a las 5", a_las_9) == ("alarma", {"hora": "17:00", "dias": "", "texto": ""})
    assert detectar("recuérdame esta noche a las 10 sacar la basura", a_las_9) == (
        "alarma", {"hora": "22:00", "dias": "", "texto": "sacar la basura"})
    # «mañana» sigue siendo mañana
    assert detectar("pon una alarma mañana a las 11", a_las_9)[1]["fecha"] == "2026-09-27"


def test_despiertame_es_por_la_manana():
    # RH5: «despiértame a las 8» a las 09:25 → 08:00 (sin fecha: suena la próxima vez, mañana), no 20:00.
    assert detectar("despiértame a las 8", datetime(2026, 9, 26, 9, 25)) == (
        "alarma", {"hora": "08:00", "dias": "", "texto": ""})
    assert detectar("despiértame a las 8", datetime(2026, 9, 26, 3, 0))[1]["hora"] == "08:00"
    assert detectar("despiértame a las 8 de la noche", SAB_14H)[1]["hora"] == "20:00"
    # Sin «despiértame», la hora ambigua sigue siendo la próxima que llegue.
    assert detectar("avísame a las 8", datetime(2026, 9, 26, 9, 25))[1]["hora"] == "20:00"


def test_los_argumentos_cumplen_el_esquema_del_catalogo():
    from lune_core import catalogo_herramientas as cat
    frases = ["avísame en 5 min que saque la pizza", "pon una alarma a las 7:30 de lunes a viernes",
              "despiértame mañana a las 7", "recuérdame que a las 5 tengo cita"]
    for f in frases:
        nombre, args = detectar(f, SAB_14H)
        limpio, ignorados = cat.validar(args, cat.obtener(nombre).args)
        assert set(ignorados) <= {"fecha"}
        assert limpio["texto"] == args["texto"]


def test_duracion_fuera_del_catalogo_no_se_detecta():
    assert detectar("pon un temporizador de 30 horas", SAB_14H) is None


def test_texto_largo_se_recorta():
    _, args = detectar("avísame en 5 minutos que " + "x" * 200, SAB_14H)
    assert len(args["texto"]) <= 60
