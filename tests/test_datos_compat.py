"""
Tests de nucleo/datos.py para la IA avanzada y Minecraft: proveedor 'compat',
parámetros de muestreo con presets, sección `minecraft`, escritura atómica y
la plantilla datos.example.json.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import datos  # noqa: E402

_PLANTILLA = Path(__file__).resolve().parent.parent / "datos.example.json"


@pytest.fixture
def modelos(monkeypatch):
    m = {}
    monkeypatch.setattr(datos, "get_modelos", lambda: m)
    monkeypatch.setattr(datos, "get_apis", lambda: {})
    return m


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    """datos.json en una carpeta temporal (la caché se limpia al entrar y al salir)."""
    ruta = tmp_path / "datos.json"
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


# ── Proveedor compatible con OpenAI ────────────────────────────────────────────

def test_compat_vacio_por_defecto(modelos):
    assert datos.compat_url() == ""
    assert datos.compat_key() == ""
    assert datos.compat_model() == ""
    assert datos.compat_timeout() == 120


def test_compat_limpia_los_valores(modelos, monkeypatch):
    modelos.update({"compat_url": "  http://localhost:1234/v1/ ", "compat_key": " sk-x ",
                    "compat_model": " qwen ", "compat_timeout": "1"})
    assert datos.compat_url() == "http://localhost:1234/v1"
    assert datos.compat_key() == "sk-x"
    assert datos.compat_model() == "qwen"
    assert datos.compat_timeout() == 5          # mínimo


def test_compat_key_tambien_en_apis(modelos, monkeypatch):
    monkeypatch.setattr(datos, "get_apis", lambda: {"compat_key": "gsk_1"})
    assert datos.compat_key() == "gsk_1"
    modelos["compat_key"] = "manda_modelos"
    assert datos.compat_key() == "manda_modelos"


# ── Parámetros de muestreo ─────────────────────────────────────────────────────

def test_parametros_por_defecto(modelos):
    p = datos.parametros_muestreo()
    assert p == {"preset": "equilibrado", "temperatura": 0.7, "top_p": None, "top_k": None,
                 "min_p": None, "repeat_penalty": None, "num_predict": None, "seed": None,
                 "num_ctx": 8192}
    assert datos.temperatura() == 0.7


@pytest.mark.parametrize("preset, temp", [("equilibrado", 0.7), ("creativo", 1.0),
                                          ("personalizado", 0.7), ("CREATIVO", 1.0),
                                          ("inventado", 0.7)])
def test_presets_de_temperatura(modelos, preset, temp):
    modelos["preset_muestreo"] = preset
    p = datos.parametros_muestreo()
    assert p["temperatura"] == temp
    assert p["top_k"] is None
    assert p["preset"] in datos.PRESETS_MUESTREO or p["preset"] == "personalizado"


def test_preset_preciso(modelos):
    modelos["preset_muestreo"] = "preciso"
    p = datos.parametros_muestreo()
    assert (p["temperatura"], p["top_p"], p["top_k"], p["min_p"], p["repeat_penalty"]) == \
        (0.2, 0.9, 40, 0.05, 1.1)
    assert isinstance(p["top_k"], int)


def test_lo_explicito_manda_sobre_el_preset(modelos):
    """El campo de temperatura del panel nativo sigue funcionando con cualquier preset."""
    modelos.update({"preset_muestreo": "preciso", "temperatura": 0.5, "top_k": "20",
                    "seed": 7, "num_predict": 300, "ollama_num_ctx": 4096})
    p = datos.parametros_muestreo()
    assert p["temperatura"] == 0.5 and p["top_k"] == 20
    assert p["top_p"] == 0.9                      # lo no tocado sigue del preset
    assert p["seed"] == 7 and p["num_predict"] == 300 and p["num_ctx"] == 4096


def test_valores_raros_se_limitan_o_se_ignoran(modelos):
    modelos.update({"temperatura": 5, "top_p": 0, "top_k": 0, "min_p": "abc",
                    "repeat_penalty": 9, "num_predict": -1, "seed": -1})
    p = datos.parametros_muestreo()
    assert p["temperatura"] == 2.0
    assert p["top_p"] == 0.01
    assert p["top_k"] is None and p["num_predict"] is None and p["seed"] is None
    assert p["min_p"] is None
    assert p["repeat_penalty"] == 2.0
    modelos.update({"temperatura": float("nan"), "top_p": True, "seed": ""})
    p = datos.parametros_muestreo()
    assert p["temperatura"] == 0.7 and p["top_p"] is None and p["seed"] is None


def test_aplicar_preset_reescribe_sus_valores(datos_tmp):
    datos_tmp.write_text(json.dumps({"modelos": {"temperatura": 0.9, "seed": 3,
                                                 "ollama_model": "qwen"}}), "utf-8")
    datos.invalidar()

    p = datos.aplicar_preset_muestreo("preciso")
    assert p["temperatura"] == 0.2 and p["top_k"] == 40 and p["seed"] == 3
    guardado = json.loads(datos_tmp.read_text("utf-8"))["modelos"]
    assert guardado["preset_muestreo"] == "preciso" and guardado["top_p"] == 0.9
    assert guardado["ollama_model"] == "qwen"           # lo demás no se toca

    p = datos.aplicar_preset_muestreo("Creativo")
    guardado = json.loads(datos_tmp.read_text("utf-8"))["modelos"]
    assert p["temperatura"] == 1.0 and p["top_k"] is None and p["top_p"] is None
    assert "top_k" not in guardado and guardado["temperatura"] == 1.0
    assert guardado["seed"] == 3                        # seed no es del preset

    datos.aplicar_preset_muestreo("personalizado")
    guardado = json.loads(datos_tmp.read_text("utf-8"))["modelos"]
    assert guardado["preset_muestreo"] == "personalizado" and guardado["temperatura"] == 1.0

    with pytest.raises(ValueError):
        datos.aplicar_preset_muestreo("turbo")


def test_guardar_es_atomico(datos_tmp):
    datos.guardar({"modelos": {"compat_url": "http://localhost:1234/v1"}})
    assert json.loads(datos_tmp.read_text("utf-8"))["modelos"]["compat_url"] == \
        "http://localhost:1234/v1"
    assert not datos_tmp.with_name("datos.json.tmp").exists()
    assert datos.compat_url() == "http://localhost:1234/v1"


# ── Minecraft ──────────────────────────────────────────────────────────────────

def test_minecraft_por_defecto(monkeypatch):
    monkeypatch.setattr(datos, "_load", lambda: {})
    assert datos.minecraft() == {
        "host": "localhost", "port": 25565, "version": "", "usuario": "", "dueno": "",
        "pensar_cada_s": 45, "defender": True, "solo_dueno": True,
        "estilo_frases": "personaje", "visor": False,
    }


def test_minecraft_valida(monkeypatch):
    crudo = {"_nota": "x", "host": " 192.168.1.9 ", "port": "25566", "version": "1.20.4",
             "usuario": " LuneBot ", "dueno": "Diego", "pensar_cada_s": 2,
             "defender": "false", "solo_dueno": 0, "visor": "sí", "estilo_frases": "",
             "extra_corte_10": 1}
    monkeypatch.setattr(datos, "_load", lambda: {"minecraft": crudo})
    mc = datos.minecraft()
    assert mc["host"] == "192.168.1.9" and mc["port"] == 25566
    assert mc["usuario"] == "LuneBot" and mc["dueno"] == "Diego" and mc["version"] == "1.20.4"
    assert mc["pensar_cada_s"] == 10                     # mínimo: comparte Ollama con el chat
    assert mc["defender"] is False and mc["solo_dueno"] is False and mc["visor"] is True
    assert mc["estilo_frases"] == "personaje"
    assert mc["extra_corte_10"] == 1 and "_nota" not in mc


@pytest.mark.parametrize("puerto", ["abc", 0, 70000, None, -5])
def test_minecraft_puerto_invalido(monkeypatch, puerto):
    monkeypatch.setattr(datos, "_load", lambda: {"minecraft": {"port": puerto}})
    assert datos.minecraft()["port"] == 25565


def test_minecraft_seccion_corrupta(monkeypatch):
    monkeypatch.setattr(datos, "_load", lambda: {"minecraft": ["no", "es", "dict"]})
    assert datos.minecraft() == datos.MINECRAFT_DEFECTO


# ── Plantilla ──────────────────────────────────────────────────────────────────

def test_plantilla_declara_compat_preset_voz_y_minecraft(monkeypatch):
    d = json.loads(_PLANTILLA.read_text("utf-8"))
    m = d["modelos"]
    assert m["compat_url"] == "" and m["compat_key"] == "" and m["compat_model"] == ""
    assert m["preset_muestreo"] == "equilibrado"

    lune = d["personajes"][0]
    assert lune["voz"] == {"motor": "edge", "id": "es-MX-DaliaNeural",
                           "rate": "+0%", "pitch": "+0Hz"}
    assert lune["frases_asistente"] == {}
    assert "voz" in d["_nota"] and "frases_asistente" in d["_nota"]

    mc = {k: v for k, v in d["minecraft"].items() if not k.startswith("_")}
    assert mc == datos.MINECRAFT_DEFECTO

    # Con la plantilla tal cual, el comportamiento es el de siempre.
    monkeypatch.setattr(datos, "_load", lambda: d)
    p = datos.parametros_muestreo()
    assert p["preset"] == "equilibrado" and p["temperatura"] == 0.7
    assert all(p[k] is None for k in ("top_p", "top_k", "min_p", "repeat_penalty",
                                      "num_predict", "seed"))
    assert datos.compat_url() == "" and datos.minecraft() == datos.MINECRAFT_DEFECTO
