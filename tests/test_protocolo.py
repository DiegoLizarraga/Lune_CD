"""Tests del contrato del hub (lune_core/protocolo.py)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import protocolo as P  # noqa: E402

F = P.Fuente(id="test-app", kind="app")


def test_ida_y_vuelta_conserva_todo():
    ev = P.nuevo_evento(P.Tipo.INPUT_TEXT, {"text": "hola", "n": 1}, F, to=["bot"])
    texto = P.codificar(ev)
    de = P.decodificar(texto)
    assert de.type == "input:text"
    assert de.data == {"text": "hola", "n": 1}
    assert de.meta.source.id == "test-app" and de.meta.source.kind == "app"
    assert de.meta.id == ev.meta.id
    assert de.route == {"to": ["bot"]}


def test_sin_route_no_se_serializa():
    ev = P.nuevo_evento(P.Tipo.PING, {}, F)
    assert "route" not in json.loads(P.codificar(ev))
    assert P.decodificar(P.codificar(ev)).route is None


def test_parent_id_correlaciona_respuestas():
    pregunta = P.nuevo_evento(P.Tipo.MEMORY_QUERY, {"que": "nombre"}, F)
    respuesta = P.nuevo_evento(P.Tipo.MEMORY_RESULT, {"resultado": "Diego"}, F, parent_id=pregunta.meta.id)
    assert P.decodificar(P.codificar(respuesta)).responde_a() == pregunta.meta.id


@pytest.mark.parametrize("crudo", [
    "esto no es json",
    "[1,2,3]",
    '{"data": {}}',
    '{"type": "", "data": {}}',
    '{"type": "x", "data": "no soy objeto", "meta": {"source": {"id": "a", "kind": "b"}, "id": "1"}}',
    '{"type": "x", "data": {}, "meta": {"id": "1"}}',
    '{"type": "x", "data": {}, "meta": {"source": {"id": "a", "kind": "b"}}}',
    '{"type": "x", "data": {}, "meta": {"source": {"id": "a", "kind": "b"}, "id": "1"}, "route": {"to": "no-lista"}}',
])
def test_rechaza_eventos_mal_formados(crudo):
    with pytest.raises(P.ErrorProtocolo):
        P.decodificar(crudo)


def test_acepta_json_minimo_de_otro_lenguaje():
    """Un cliente en Node o en un navegador solo tiene que mandar esto."""
    crudo = json.dumps({"type": "input:text", "data": {"text": "hola"},
                        "meta": {"source": {"id": "bot", "kind": "bot"}, "id": "abc"}})
    ev = P.decodificar(crudo)
    assert ev.type == "input:text" and ev.meta.id == "abc" and ev.meta.parent_id is None


def test_errores_distinguen_terminal_de_recuperable():
    e1 = P.error_evento(P.CodigoError.TOKEN_INVALIDO, F)
    e2 = P.error_evento(P.CodigoError.NO_AUTENTICADO, F, parent_id="p")
    assert e1.data["terminal"] is True
    assert e2.data["terminal"] is False and e2.meta.parent_id == "p"
    assert all(c in P.ERRORES for c in P.CodigoError)


def test_tipos_conocidos():
    assert P.es_tipo_conocido("memory:query")
    assert not P.es_tipo_conocido("memory:inventado")


# ── Token ──────────────────────────────────────────────────────────────────────

def test_comparar_token():
    assert P.comparar_token("abc123", "abc123") is True
    assert P.comparar_token("abc124", "abc123") is False
    assert P.comparar_token("abc12", "abc123") is False      # distinta longitud
    assert P.comparar_token(None, "abc123") is False
    assert P.comparar_token("lo-que-sea", "") is True         # host sin token = abierto


def test_generar_token_es_largo_y_distinto():
    a, b = P.generar_token(), P.generar_token()
    assert a != b and len(a) >= 24
