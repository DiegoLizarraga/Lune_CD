"""
Tests de configuración: datos.json (APIs/modelos) y config.json (preferencias).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos  # noqa: E402
from config import Config  # noqa: E402
from respuestas import BancoRespuestas  # noqa: E402


# ── config.py ──────────────────────────────────────────────────────────────────

def test_config_se_crea_con_los_valores_por_defecto(tmp_path):
    ruta = tmp_path / "config.json"
    cfg = Config(config_path=str(ruta))
    assert ruta.exists()
    assert cfg.feature("respuestas_predeterminadas") is True
    assert cfg.feature("acciones_ia") is True


def test_set_feature_no_contamina_los_valores_por_defecto(tmp_path):
    """
    DEFAULT_CONFIG se copiaba en superficial, así que las secciones anidadas
    eran el MISMO dict y set_feature() mutaba la clase entera.
    """
    cfg1 = Config(config_path=str(tmp_path / "a.json"))
    cfg1.set_feature("animaciones_video", False)

    cfg2 = Config(config_path=str(tmp_path / "b.json"))
    assert cfg2.feature("animaciones_video") is True
    assert Config.DEFAULT_CONFIG["features"]["animaciones_video"] is True


def test_el_esquema_crece_sin_perder_lo_guardado(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"features": {"voz_auto": True}}), encoding="utf-8")

    cfg = Config(config_path=str(ruta))
    assert cfg.feature("voz_auto") is True          # se conserva lo del usuario
    assert cfg.feature("minimizar_a_bandeja") is True  # y aparecen las nuevas


# ── datos.py ───────────────────────────────────────────────────────────────────

def test_valores_por_defecto_de_ollama(monkeypatch):
    monkeypatch.setattr(datos, "get_modelos", lambda: {})
    assert datos.ollama_url() == "http://localhost:11434"
    assert datos.ollama_keep_alive() == "30m"
    assert datos.ollama_num_ctx() == 8192
    assert datos.ollama_timeout() == 300
    assert datos.temperatura() == 0.7
    assert datos.openrouter_model() == "openrouter/auto"


def test_valores_corruptos_caen_al_defecto(monkeypatch):
    """La UI puede escribir texto vacío o basura; no debe reventar el motor."""
    monkeypatch.setattr(datos, "get_modelos", lambda: {
        "ollama_num_ctx": "", "ollama_timeout": "abc", "temperatura": None,
    })
    assert datos.ollama_num_ctx() == 8192
    assert datos.ollama_timeout() == 300
    assert datos.temperatura() == 0.7


def test_max_historial(monkeypatch):
    monkeypatch.setattr(datos, "get_bot", lambda: {"max_historial": 5})
    assert datos.max_historial() == 5
    monkeypatch.setattr(datos, "get_bot", lambda: {})
    assert datos.max_historial() == 20


def test_la_url_se_normaliza_al_guardar():
    from ollama_client import normalizar_url
    assert normalizar_url("192.168.1.50") == "http://192.168.1.50:11434"
    assert normalizar_url("localhost:11434") == "http://localhost:11434"
    assert normalizar_url("http://pc-potente:11434/") == "http://pc-potente:11434"
    assert normalizar_url("") == "http://localhost:11434"


# ── respuestas.py ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mensaje", ["hola", "gracias", "adiós", "¿qué hora es?",
                                     "quién eres", "cuéntame un chiste"])
def test_el_banco_responde_a_frases_comunes(mensaje):
    assert BancoRespuestas().responder(mensaje) is not None


@pytest.mark.parametrize("mensaje", [
    "hola, necesito que me escribas una función en python",
    "gracias a eso el programa falla, ¿por qué?",
    "explícame qué hace este código",
])
def test_el_banco_deja_pasar_las_peticiones_reales(mensaje):
    assert BancoRespuestas().responder(mensaje) is None


# ── Plantilla y bot de Telegram ────────────────────────────────────────────────

def test_la_plantilla_declara_el_proveedor_del_bot():
    """
    El bot elige proveedor con `bot.proveedor` y reutiliza las claves de
    `modelos` de la app. Si alguien las renombra, el bot pierde el modelo local
    sin que Python se entere: este test es el aviso.
    """
    ruta = Path(__file__).resolve().parent.parent / "datos.example.json"
    d = json.loads(ruta.read_text("utf-8"))
    assert d["bot"]["proveedor"] in ("ollama", "openrouter")
    for clave in ("ollama_url", "ollama_model", "ollama_keep_alive",
                  "ollama_num_ctx", "ollama_timeout", "temperatura"):
        assert clave in d["modelos"], clave
