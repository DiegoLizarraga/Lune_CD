"""
Tests de la política de herramientas (lune_core/herramientas.py).

Lo crítico: fail-closed (sin descriptor no se ejecuta), la aprobación la da un
humano y no el modelo, la deny-list se respeta, y el presupuesto frena bucles.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import herramientas as H  # noqa: E402


@pytest.fixture
def sesion(tmp_path):
    reg = H.registro_por_defecto()
    return H.Sesion(reg, presupuesto=10, audit_path=tmp_path / "audit.jsonl")


# ── Política ────────────────────────────────────────────────────────────────────

def test_lectura_se_permite_sin_aprobacion(sesion):
    r = sesion.solicitar("sistema_info")
    assert r["estado"] == "permitida"


def test_lanzar_app_requiere_aprobacion(sesion):
    r = sesion.solicitar("lanzar_app", {"app": "paint"})
    assert r["estado"] == "aprobacion_requerida" and r["pendiente_id"]


def test_herramienta_no_registrada_se_deniega_fail_closed(sesion):
    """La regla de oro: lo que no está registrado, no se ejecuta."""
    r = sesion.solicitar("formatear_disco")
    assert r["estado"] == "denegada"
    assert r["veredicto"]["decision"] == "denegar"


@pytest.mark.parametrize("app", ["1Password", "el administrador de credenciales",
                                 "regedit", "Lune CD", "cmd"])
def test_deny_list_de_apps(sesion, app):
    r = sesion.solicitar("lanzar_app", {"app": app})
    assert r["estado"] == "denegada"


def test_teclas_prohibidas():
    reg = H.Registro()
    reg.registrar(H.Descriptor("teclas", "enviar teclas", H.Riesgo.ESCRITURA))
    s = H.Sesion(reg)
    assert s.solicitar("teclas", {"teclas": "alt+f4"})["estado"] == "denegada"
    assert s.solicitar("teclas", {"teclas": "ctrl+alt+supr"})["estado"] == "denegada"


# ── Aprobación humana ───────────────────────────────────────────────────────────

def test_aprobacion_humana_devuelve_la_accion(sesion):
    r = sesion.solicitar("lanzar_app", {"app": "notepad"})
    pid = r["pendiente_id"]
    assert len(sesion.listar_pendientes()) == 1
    ap = sesion.aprobar(pid)
    assert ap["ok"] and ap["herramienta"] == "lanzar_app" and ap["args"]["app"] == "notepad"
    assert sesion.listar_pendientes() == []


def test_rechazo_descarta_la_accion(sesion):
    pid = sesion.solicitar("lanzar_app", {"app": "notepad"})["pendiente_id"]
    assert sesion.rechazar(pid, "no quiero")["ok"]
    assert sesion.listar_pendientes() == []
    # aprobar algo ya rechazado no hace nada
    assert sesion.aprobar(pid)["ok"] is False


def test_el_modelo_no_puede_aprobar():
    """
    No hay ninguna herramienta 'aprobar' en el registro: la aprobación vive fuera
    del catálogo que ve el modelo. (En AIRI el LLM podía aprobarse a sí mismo.)
    """
    reg = H.registro_por_defecto()
    assert not any("aprob" in n.lower() for n in reg.nombres())


# ── Presupuesto ─────────────────────────────────────────────────────────────────

def test_presupuesto_frena_bucles():
    reg = H.Registro()
    reg.registrar(H.Descriptor("accion", "algo", H.Riesgo.ESCRITURA,
                               requiere_aprobacion=False, coste=1))
    s = H.Sesion(reg, presupuesto=3)
    for _ in range(3):
        assert s.solicitar("accion")["estado"] == "permitida"
    assert s.solicitar("accion")["estado"] == "sin_presupuesto"


def test_lectura_no_gasta_presupuesto(sesion):
    for _ in range(50):
        assert sesion.solicitar("sistema_info")["estado"] == "permitida"


# ── Auditoría ───────────────────────────────────────────────────────────────────

def test_todo_queda_en_el_audit(tmp_path):
    audit = tmp_path / "audit.jsonl"
    s = H.Sesion(H.registro_por_defecto(), audit_path=audit)
    pid = s.solicitar("lanzar_app", {"app": "paint"})["pendiente_id"]
    s.aprobar(pid)
    s.registrar_resultado("lanzar_app", ok=True, detalle="abierto")
    lineas = [json.loads(l) for l in audit.read_text("utf-8").splitlines()]
    eventos = [l["evento"] for l in lineas]
    assert "solicitud" in eventos and "encolada" in eventos
    assert "aprobada" in eventos and "resultado" in eventos


def test_audit_registra_denegaciones(tmp_path):
    audit = tmp_path / "audit.jsonl"
    s = H.Sesion(H.registro_por_defecto(), audit_path=audit)
    s.solicitar("lanzar_app", {"app": "1password"})
    lineas = [json.loads(l) for l in audit.read_text("utf-8").splitlines()]
    assert any(l["evento"] == "solicitud" and l["decision"] == "denegar" for l in lineas)


# ── Registro para el prompt ─────────────────────────────────────────────────────

def test_esquema_para_prompt_lista_las_herramientas():
    esquema = H.registro_por_defecto().esquema_para_prompt()
    assert "sistema_info" in esquema and "lanzar_app" in esquema
    assert "confirmación" in esquema      # lanzar_app la pide


def test_destructivo_siempre_pide_aprobacion_aunque_la_bandera_diga_que_no():
    reg = H.Registro()
    reg.registrar(H.Descriptor("borrar", "borrar archivos", H.Riesgo.DESTRUCTIVO,
                               requiere_aprobacion=False))   # bandera mal puesta
    s = H.Sesion(reg)
    assert s.solicitar("borrar")["estado"] == "aprobacion_requerida"


def test_escritura_sin_aprobacion_se_permite():
    reg = H.Registro()
    reg.registrar(H.Descriptor("abrir_url", "abrir web", H.Riesgo.ESCRITURA,
                               requiere_aprobacion=False))
    s = H.Sesion(reg)
    assert s.solicitar("abrir_url", {"url": "https://x.com"})["estado"] == "permitida"
