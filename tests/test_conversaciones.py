"""Tests del historial de conversaciones."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.conversaciones import GestorConversaciones  # noqa: E402


@pytest.fixture
def gestor(tmp_path):
    return GestorConversaciones(directorio=tmp_path / "chats")


def test_una_conversacion_sobrevive_al_cierre(tmp_path):
    """Lo que se rompía antes: cerrar la app perdía todo el chat."""
    dir_chats = tmp_path / "chats"
    g1 = GestorConversaciones(directorio=dir_chats)
    g1.nueva_sesion(proveedor="ollama", personaje="Lune")
    g1.agregar("user", "¿cómo hago un bucle?")
    g1.agregar("assistant", "Con `for`.")
    sesion_id = g1.sesion_id

    g2 = GestorConversaciones(directorio=dir_chats)
    cargada = g2.cargar(sesion_id)
    assert cargada is not None
    assert len(cargada["mensajes"]) == 2
    assert cargada["mensajes"][0]["contenido"] == "¿cómo hago un bucle?"


def test_el_titulo_sale_del_primer_mensaje(gestor):
    gestor.nueva_sesion()
    gestor.agregar("user", "explícame los decoradores de python por favor")
    assert gestor.listar()[0]["titulo"].startswith("explícame los decoradores")


def test_titulo_largo_se_recorta(gestor):
    gestor.nueva_sesion()
    gestor.agregar("user", "x" * 200)
    assert gestor.listar()[0]["titulo"].endswith("…")
    assert len(gestor.listar()[0]["titulo"]) <= 50


def test_las_sesiones_vacias_no_se_escriben(gestor):
    gestor.nueva_sesion()
    gestor.guardar()
    assert gestor.listar() == []


def test_orden_por_actualizacion(gestor):
    gestor.nueva_sesion(); gestor.agregar("user", "primera")
    gestor.nueva_sesion(); gestor.agregar("user", "segunda")
    titulos = [s["titulo"] for s in gestor.listar()]
    assert titulos[0] == "segunda"


def test_poda_las_mas_viejas(tmp_path):
    g = GestorConversaciones(directorio=tmp_path / "chats", max_sesiones=3)
    for i in range(6):
        g.nueva_sesion()
        g.agregar("user", f"conversación {i}")
    assert len(g.listar()) == 3


def test_borrar_una(gestor):
    gestor.nueva_sesion(); gestor.agregar("user", "hola")
    sid = gestor.sesion_id
    assert gestor.borrar(sid) is True
    assert gestor.listar() == []


def test_borrar_todo(gestor):
    for i in range(3):
        gestor.nueva_sesion(); gestor.agregar("user", f"m{i}")
    assert gestor.borrar_todo() == 3
    assert gestor.listar() == []


def test_como_historial_para_el_modelo(gestor):
    gestor.nueva_sesion()
    gestor.agregar("user", "hola")
    gestor.agregar("assistant", "buenas")
    assert gestor.como_historial() == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "buenas"},
    ]


def test_como_historial_respeta_el_limite(gestor):
    gestor.nueva_sesion()
    for i in range(30):
        gestor.agregar("user", f"p{i}")
        gestor.agregar("assistant", f"r{i}")
    assert len(gestor.como_historial(limite_turnos=5)) == 10


def test_se_guardan_los_adjuntos_y_el_uso(gestor):
    gestor.nueva_sesion()
    gestor.agregar("user", "mira esto", adjuntos=[{"nombre": "informe.pdf"}])
    gestor.agregar("assistant", "visto", uso={"total": 350, "costo": 0.001})
    mensajes = gestor.mensajes_actuales()
    assert mensajes[0]["adjuntos"] == ["informe.pdf"]
    assert mensajes[1]["uso"]["total"] == 350


def test_ultima_devuelve_la_mas_reciente(gestor):
    gestor.nueva_sesion(); gestor.agregar("user", "vieja")
    gestor.nueva_sesion(); gestor.agregar("user", "nueva")
    assert gestor.ultima()["mensajes"][0]["contenido"] == "nueva"


def test_un_archivo_corrupto_no_rompe_el_listado(gestor):
    gestor.nueva_sesion(); gestor.agregar("user", "buena")
    (gestor.dir / "chat_rota.json").write_text("{esto no es json", encoding="utf-8")
    assert len(gestor.listar()) == 1


def test_ultima_es_correcta_aunque_el_reloj_no_avance(tmp_path, monkeypatch):
    """
    Reloj congelado a propósito: simula la resolución de ~15 ms de
    datetime.now() en Windows con Python 3.11, donde dos sesiones seguidas
    compartían 'actualizado' y ultima() devolvía la vieja.
    """
    from nucleo import conversaciones as c

    from datetime import datetime as _dt
    fijo = _dt(2026, 1, 1, 12, 0, 0)

    class RelojParado:
        @staticmethod
        def now():
            return fijo

    monkeypatch.setattr(c, "datetime", RelojParado)
    g = c.GestorConversaciones(directorio=tmp_path / "chats")
    g.nueva_sesion(); g.agregar("user", "vieja")
    g.nueva_sesion(); g.agregar("user", "nueva")
    assert g.ultima()["mensajes"][0]["contenido"] == "nueva"
