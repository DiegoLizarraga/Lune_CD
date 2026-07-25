"""
Tests de la memoria personal.

El bug que motivó estos tests: los patrones se buscaban con `re.search` sin
anclar, así que «me gustaría saber cómo funciona python» casaba con
`me gusta(.+)`, se guardaba como recuerdo y —lo peor— consumía el turno,
de modo que el usuario nunca recibía respuesta de la IA.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoria import MemoriaManager  # noqa: E402


@pytest.fixture
def memoria(tmp_path):
    return MemoriaManager(path=tmp_path / "memoria.json")


# ── Conversación normal: NUNCA se consume el turno ─────────────────────────────

@pytest.mark.parametrize("mensaje", [
    "me gustaría saber cómo funciona python",
    "no me gusta cómo quedó, hazlo de nuevo",
    "prefiero que me expliques esto paso a paso",
    "trabajo en un script y no me compila, ayuda",
    "tengo un problema con años bisiestos en mi código",
    "vivo pensando en refactorizar este proyecto la verdad",
    "memoria",
    "recuerdos",
    "olvida lo que te dije antes y empecemos otra vez",
    "¿cuánta memoria RAM tengo?",
])
def test_la_conversacion_normal_llega_a_la_ia(memoria, mensaje):
    assert memoria.procesar_mensaje_usuario(mensaje) is None


def test_el_ruido_no_ensucia_la_memoria(memoria):
    for mensaje in ["me gustaría saber de python",
                    "trabajo en un script y no me compila",
                    "prefiero que lo hagas de otra forma"]:
        memoria.procesar_mensaje_usuario(mensaje)

    assert memoria.get_todos_recuerdos() == []
    assert memoria._data["datos_clave"] == {}
    assert memoria.get_nombre_usuario() is None


# ── Guardado explícito: sí consume el turno ────────────────────────────────────

@pytest.mark.parametrize("mensaje,contenido", [
    ("recuerda que mi cumpleaños es el 3 de mayo", "mi cumpleaños es el 3 de mayo"),
    ("anota que tengo junta el lunes", "tengo junta el lunes"),
    ("apunta que el wifi es MiRed", "el wifi es MiRed"),
    ("no olvides que debo pagar la luz", "debo pagar la luz"),
])
def test_guardado_explicito(memoria, mensaje, contenido):
    respuesta = memoria.procesar_mensaje_usuario(mensaje)
    assert respuesta is not None
    assert contenido in respuesta
    assert any(r["contenido"] == contenido for r in memoria.get_todos_recuerdos())


# ── Extracción silenciosa: guarda de fondo, sin cortar la conversación ─────────

def test_el_nombre_se_extrae_sin_consumir_el_turno(memoria):
    assert memoria.procesar_mensaje_usuario("hola, me llamo Diego y necesito ayuda") is None
    assert memoria.get_nombre_usuario() == "Diego"


@pytest.mark.parametrize("mensaje,campo,valor", [
    ("tengo 25 años", "edad", "25"),
    ("vivo en Culiacán", "ciudad", "Culiacán"),
    ("trabajo como ingeniero", "trabajo", "ingeniero"),
])
def test_datos_de_perfil(memoria, mensaje, campo, valor):
    assert memoria.procesar_mensaje_usuario(mensaje) is None
    assert memoria._data["datos_clave"][campo] == valor


# ── Comandos ───────────────────────────────────────────────────────────────────

def test_comandos_requieren_barra(memoria):
    memoria.procesar_mensaje_usuario("recuerda que me gusta el café")
    assert memoria.procesar_mensaje_usuario("/memoria") is not None
    assert memoria.procesar_mensaje_usuario("memoria") is None


def test_olvida_todo(memoria):
    memoria.procesar_mensaje_usuario("recuerda que algo importante")
    memoria.procesar_mensaje_usuario("me llamo Diego")
    assert memoria.get_todos_recuerdos()

    respuesta = memoria.procesar_mensaje_usuario("/olvida todo")
    assert respuesta is not None
    assert memoria.get_todos_recuerdos() == []
    assert memoria.get_nombre_usuario() is None


def test_olvida_por_id(memoria):
    rid = memoria.agregar_recuerdo("comprar pan", "tarea")
    memoria.procesar_mensaje_usuario(f"/olvida {rid}")
    assert memoria.get_todos_recuerdos() == []


def test_la_memoria_persiste_entre_sesiones(tmp_path):
    ruta = tmp_path / "memoria.json"
    m1 = MemoriaManager(path=ruta)
    m1.procesar_mensaje_usuario("me llamo Diego")
    m1.procesar_mensaje_usuario("recuerda que el proyecto se entrega el viernes")
    m1.cerrar_sesion("resumen de prueba")

    m2 = MemoriaManager(path=ruta)
    assert m2.get_nombre_usuario() == "Diego"
    assert len(m2.get_todos_recuerdos()) == 1
    assert "Diego" in m2.obtener_contexto_para_prompt()
