"""
Respuestas instantáneas sin modelo (nucleo/respuestas.py, 10.9): el banco ahora
también contesta «qué tareas tengo» con las tareas guardadas, sin gastar el modelo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.respuestas import AVISO_MASCOTA_SIN_NUBE, COMENTARIO_VACIO, BancoRespuestas  # noqa: E402


@pytest.mark.parametrize("frase", ["qué tareas tengo", "¿Qué tareas tengo pendientes?", "mis tareas",
                                   "mis pendientes", "qué tengo pendiente hoy", "¿qué tengo que hacer hoy?",
                                   "lista de tareas", "qué hay en mi día"])
def test_las_tareas_se_contestan_sin_modelo(frase):
    b = BancoRespuestas(tareas=lambda: "Tienes 2 tareas pendientes: · pan · correo.")
    assert b.responder(frase) == "Tienes 2 tareas pendientes: · pan · correo."


def test_sin_resumen_de_tareas_la_pregunta_va_a_la_ia():
    assert BancoRespuestas().responder("qué tareas tengo") is None             # sin módulo de tareas
    assert BancoRespuestas(tareas=lambda: None).responder("mis tareas") is None
    assert BancoRespuestas(tareas=lambda: "").responder("mis tareas") is None

    def roto():
        raise RuntimeError("memoria.json ilegible")
    assert BancoRespuestas(tareas=roto).responder("mis tareas") is None


def test_una_tarea_suelta_en_la_frase_no_se_come_el_mensaje():
    """Solo la pregunta entera: «anota que tengo tareas de mates» no es una consulta."""
    b = BancoRespuestas(tareas=lambda: "Tienes 1 tarea pendiente.")
    assert b.responder("ayúdame con mis tareas de mates") is None
    assert b.responder("tengo muchas tareas y no sé por dónde empezar") is None


@pytest.mark.parametrize("frase", ["sí", "si", "ok", "vale", "dale", "hazlo", "de acuerdo"])
def test_un_si_nunca_lo_contesta_el_banco(frase):
    """Tras «¿quieres que te ponga uno?» el «sí» tiene que llegar al modelo."""
    assert BancoRespuestas(tareas=lambda: "x").responder(frase) is None


def test_lo_de_siempre_sigue_igual():
    b = BancoRespuestas(nombre_usuario="Diego")
    assert b.responder("hola") and b.responder("gracias") and b.responder("qué hora es").startswith("Son las")
    assert b.responder("¿qué día es hoy?").startswith("Hoy es")
    assert b.responder("explícame los punteros en C") is None
    assert BancoRespuestas(categorias_desactivadas={"saludo"}).responder("hola") is None


def test_las_frases_de_la_mascota():
    assert "OpenRouter" in AVISO_MASCOTA_SIN_NUBE and "AJUSTES" in AVISO_MASCOTA_SIN_NUBE
    assert COMENTARIO_VACIO == "Mmm… nada me pareció interesante."
