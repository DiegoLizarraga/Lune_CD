"""Tests del canal de control <|ACT|>/<|DELAY|> y del vocabulario de emociones."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import marcadores as M  # noqa: E402


# ── Normalización de emociones ─────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperada", [
    ("happy", "happy"), ("HAPPY", "happy"), ("normal", "neutral"),
    ("typing", "think"), ("error", "sad"), ("inventada", "neutral"),
    (None, "neutral"), ("surprise", "surprised"),
])
def test_normalizar_emocion(entrada, esperada):
    assert M.normalizar_emocion(entrada) == esperada


@pytest.mark.parametrize("payload,emo,inten", [
    ("happy", "happy", 1.0),
    ({"emotion": "sad", "intensity": 0.5}, "sad", 0.5),
    ({"emotion": {"name": "angry", "intensity": 0.9}, "motion": "wave"}, "angry", 0.9),
    ({"emotion": "happy", "intensity": 5}, "happy", 1.0),      # clamp alto
    ({"emotion": "happy", "intensity": -2}, "happy", 0.0),     # clamp bajo
    ({"emotion": "happy", "intensity": "no-num"}, "happy", 1.0),
])
def test_normalizar_act(payload, emo, inten):
    r = M.normalizar_act(payload)
    assert r["emotion"] == emo and r["intensity"] == inten


def test_normalizar_act_conserva_motion():
    assert M.normalizar_act({"emotion": "happy", "motion": "shrug"})["motion"] == "shrug"


# ── Parseo completo ────────────────────────────────────────────────────────────

def test_separa_texto_y_act():
    hablable, control = M.separar('Hola <|ACT {"emotion":"happy","intensity":0.8}|> mundo')
    assert hablable == "Hola  mundo"
    assert control == [("act", {"emotion": "happy", "intensity": 0.8, "motion": None})]


def test_delay_y_emocion_suelta():
    hablable, control = M.separar("Un momento <|DELAY 1.5|> listo <|ACT happy|>")
    assert "Un momento" in hablable and "listo" in hablable
    clases = [c for c, _ in control]
    assert clases == ["delay", "act"]
    assert control[0][1] == 1.5
    assert control[1][1]["emotion"] == "happy"


def test_call_lista():
    _, control = M.separar('Busco eso <|CALL ["buscar_web", {"q": "gatos"}]|>')
    assert control == [("call", ["buscar_web", {"q": "gatos"}])]


def test_marcador_invalido_queda_como_texto():
    hablable, control = M.separar("esto <|ACT no-es-json ni-emocion|> queda")
    assert control == []
    assert "<|ACT no-es-json ni-emocion|>" in hablable


def test_menor_que_normal_no_es_marcador():
    hablable, control = M.separar("si a < b entonces c > d")
    assert hablable == "si a < b entonces c > d"
    assert control == []


# ── Streaming incremental ──────────────────────────────────────────────────────

def test_marcador_partido_entre_chunks():
    p = M.ParserMarcadores()
    piezas = []
    # el <|ACT …|> llega en cuatro trozos
    for chunk in ["Hola ", "<|ACT ", '{"emotion":"sad"', '}|>', " adiós"]:
        piezas += p.consumir(chunk)
    piezas += p.vaciar()
    texto = "".join(v for c, v in piezas if c == "texto")
    acts = [v for c, v in piezas if c == "act"]
    assert texto == "Hola  adiós"
    assert acts and acts[0]["emotion"] == "sad"


def test_menor_que_final_se_retiene():
    p = M.ParserMarcadores()
    # un "<" al final del chunk podría ser el inicio de "<|": no debe emitirse aún
    piezas = p.consumir("texto <")
    assert "".join(v for c, v in piezas if c == "texto") == "texto "
    piezas = p.consumir('|ACT happy|>')
    assert any(c == "act" for c, _ in piezas)


def test_texto_sin_marcadores_pasa_entero():
    p = M.ParserMarcadores()
    assert p.consumir("solo texto normal") == [("texto", "solo texto normal")]
