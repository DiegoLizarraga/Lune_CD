"""
Tests del renderizador de markdown.

Lo importante aquí es que el HTML que sale sea seguro (nada de inyectar
etiquetas desde la respuesta del modelo) y que no se rompa a medio streaming,
cuando las cercas ``` todavía están sin cerrar.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import markdown_qt as md  # noqa: E402


# ── Separación en bloques ──────────────────────────────────────────────────────

def test_separa_texto_y_codigo():
    bloques = md.dividir_bloques("Mira esto:\n```python\nx = 1\n```\nY ya.")
    tipos = [b[0] for b in bloques]
    assert tipos == ["texto", "codigo", "texto"]
    assert bloques[1][1] == "x = 1"
    assert bloques[1][2] == "python"


def test_cerca_sin_cerrar_durante_el_streaming():
    """Mientras el modelo escribe, el ``` de cierre aún no ha llegado."""
    bloques = md.dividir_bloques("Toma:\n```js\nconst x = 1;")
    assert [b[0] for b in bloques] == ["texto", "codigo"]
    assert bloques[1][1] == "const x = 1;"


def test_texto_sin_codigo_es_un_solo_bloque():
    bloques = md.dividir_bloques("Solo texto normal.")
    assert len(bloques) == 1 and bloques[0][0] == "texto"


def test_varios_bloques_de_codigo():
    texto = "Uno:\n```py\na\n```\nDos:\n```sh\nb\n```"
    codigos = [b for b in md.dividir_bloques(texto) if b[0] == "codigo"]
    assert [c[1] for c in codigos] == ["a", "b"]
    assert [c[2] for c in codigos] == ["py", "sh"]


# ── Seguridad: nada de HTML inyectado ──────────────────────────────────────────

@pytest.mark.parametrize("peligroso", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<a href='file:///C:/'>clic</a>",
    "<style>body{display:none}</style>",
])
def test_el_html_del_modelo_se_escapa(peligroso):
    salida = md.a_html(peligroso)
    assert "<script" not in salida.lower()
    assert "<img" not in salida.lower()
    assert "<style" not in salida.lower()
    assert "onerror" not in salida.lower() or "&lt;" in salida
    assert "&lt;" in salida


# ── Formato ────────────────────────────────────────────────────────────────────

def test_negritas_y_cursivas():
    assert "<b>hola</b>" in md.a_html("**hola**")
    assert "<i>hola</i>" in md.a_html("*hola*")
    assert "<b><i>hola</i></b>" in md.a_html("***hola***")


def test_el_codigo_en_linea_no_se_reinterpreta():
    """Los ** dentro de `código` deben salir literales, no en negrita."""
    salida = md.a_html("usa `**esto**` tal cual")
    assert "<b>" not in salida
    assert "**esto**" in salida


def test_listas():
    assert "<ul>" in md.a_html("- uno\n- dos")
    assert "<ol>" in md.a_html("1. uno\n2. dos")
    assert md.a_html("- uno\n- dos").count("<li>") == 2


def test_titulos():
    assert "font-weight:bold" in md.a_html("# Título")


def test_enlaces():
    salida = md.a_html("mira [aquí](https://ejemplo.com)")
    assert 'href="https://ejemplo.com"' in salida
    assert ">aquí<" in salida


def test_enlaces_no_http_no_se_convierten():
    salida = md.a_html("[malo](javascript:alert(1))")
    assert "href=" not in salida


def test_url_suelta_se_hace_enlace():
    assert "href=" in md.a_html("visita https://ollama.com hoy")


# ── Detección rápida ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("hola qué tal", False),
    ("esto es **negrita**", True),
    ("```py\nx\n```", True),
    ("- lista", True),
    ("# título", True),
    ("", False),
])
def test_tiene_formato(texto, esperado):
    assert md.tiene_formato(texto) is esperado
