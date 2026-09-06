"""
Tests del actualizador.

Lo crítico: que NUNCA haga `git pull` con cambios locales sin guardar. Un pull
sobre un árbol sucio puede acabar en conflicto o en trabajo perdido.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import actualizador  # noqa: E402


def test_se_niega_a_actualizar_con_cambios_sin_guardar(monkeypatch):
    monkeypatch.setattr(actualizador, "estado", lambda: {
        "ok": True, "rama": "master", "commit": "abc123", "remoto": "origin",
        "limpio": False, "modificados": ["main.py", "config.py"],
    })
    # Si llegara a llamar a git, el test falla en vez de tocar el repo de verdad
    def _prohibido(*a, **k):
        raise AssertionError("¡Intentó ejecutar git con el árbol sucio!")
    monkeypatch.setattr(actualizador, "_git", _prohibido)

    res = actualizador.actualizar()
    assert res["ok"] is False
    assert res["actualizado"] is False
    assert "sin guardar" in res["mensaje"]
    assert "main.py" in res["mensaje"]


def test_sin_git_avisa_en_vez_de_reventar(monkeypatch):
    monkeypatch.setattr(actualizador, "hay_git", lambda: False)
    est = actualizador.estado()
    assert est["ok"] is False
    assert "Git" in est["mensaje"]


def test_fuera_de_un_repositorio(monkeypatch):
    monkeypatch.setattr(actualizador, "hay_git", lambda: True)
    monkeypatch.setattr(actualizador, "es_repositorio", lambda: False)
    est = actualizador.estado()
    assert est["ok"] is False
    assert "repositorio git" in est["mensaje"]


def test_comprobar_no_falla_sin_remoto(monkeypatch):
    monkeypatch.setattr(actualizador, "estado", lambda: {
        "ok": True, "rama": "master", "commit": "abc", "remoto": "",
        "limpio": True, "modificados": [],
    })
    res = actualizador.comprobar()
    assert res["ok"] is False
    assert res["hay_novedades"] is False


# ── Registro de dependencias opcionales ────────────────────────────────────────

def test_estado_opcionales_devuelve_todo():
    estados = actualizador.estado_opcionales()
    funciones = {o["funcion"] for o in estados}
    assert "Leer PDF" in funciones
    assert "Voz de entrada (dictado)" in funciones
    for o in estados:
        assert isinstance(o["disponible"], bool)
        # Si falta algo, tiene que decir exactamente cómo instalarlo
        if not o["disponible"]:
            assert o["comando"].startswith("pip install")
            assert o["faltan"]
        else:
            assert o["comando"] == ""


def test_las_dependencias_declaradas_existen_de_verdad():
    """Cada módulo del registro debe ser importable si dice estar disponible."""
    import importlib.util
    for funcion, info in actualizador.OPCIONALES.items():
        for modulo in info["modulos"]:
            # find_spec no debe lanzar: si el nombre está mal escrito, salta aquí
            importlib.util.find_spec(modulo)


def test_psutil_declarado_coincide_con_la_realidad():
    estados = {o["funcion"]: o for o in actualizador.estado_opcionales()}
    opt = estados["Optimizador del sistema"]
    try:
        import psutil  # noqa: F401
        instalado = True
    except ImportError:
        instalado = False
    assert opt["disponible"] is instalado
