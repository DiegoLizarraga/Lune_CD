"""
Tests del RAG sobre notas (lune_core/rag.py).

Se usa el embebedor determinista sin red (EmbedderHash) para que el pipeline
—troceado, indexado, caché, recuperación, ranking— sea verificable sin Ollama.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import rag as R  # noqa: E402


# ── Troceado ────────────────────────────────────────────────────────────────────

def test_trocea_por_encabezados():
    md = "# Título\ntexto uno\n\n## Sección\ntexto dos\n\n## Otra\ntexto tres"
    trozos = R.trocear_markdown(md, doc="notas.md")
    titulos = [t.titulo for t in trozos]
    assert titulos == ["Título", "Sección", "Otra"]
    assert all(t.doc == "notas.md" for t in trozos)
    assert [t.orden for t in trozos] == [0, 1, 2]


def test_seccion_larga_se_parte_con_solape():
    cuerpo = "# T\n" + ("frase. " * 400)   # ~2800 chars
    trozos = R.trocear_markdown(cuerpo, doc="d", max_chars=1000, solape=100)
    assert len(trozos) >= 3
    assert all(len(t.texto) <= 1100 for t in trozos)


def test_ids_distintos_por_trozo():
    trozos = R.trocear_markdown("# A\nuno\n## B\ndos", doc="d")
    assert len({t.id for t in trozos}) == len(trozos)


# ── Similitud ───────────────────────────────────────────────────────────────────

def test_coseno():
    assert R.coseno([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    assert R.coseno([1, 0], [0, 1]) == pytest.approx(0.0)
    assert R.coseno([0, 0], [1, 1]) == 0.0        # vector nulo no revienta


# ── Indexado y recuperación ─────────────────────────────────────────────────────

@pytest.fixture
def almacen(tmp_path):
    a = R.AlmacenRAG(tmp_path / "rag.db", R.EmbedderHash(dim=128))
    yield a
    a.cerrar()


def test_indexar_y_recuperar(almacen):
    almacen.indexar_texto(
        "# Café\nMi café favorito es el espresso italiano.\n"
        "# Perros\nTengo un perro llamado Toby que ladra mucho.",
        doc="sobre_mi.md")
    assert almacen.contar() == 2
    hits = almacen.buscar("háblame de mi perro Toby", umbral=0.0, k=1)
    assert hits and "Toby" in hits[0]["texto"]


def test_recuperacion_ordena_por_relevancia(almacen):
    almacen.indexar_texto("# Uno\nel cielo es azul y las nubes blancas", doc="a.md")
    almacen.indexar_texto("# Dos\nla programación en python es divertida", doc="b.md")
    hits = almacen.buscar("dime sobre python y programación", umbral=0.0, k=2)
    assert hits[0]["doc"] == "b.md"       # el trozo de python primero


def test_umbral_filtra(almacen):
    almacen.indexar_texto("# X\ncontenido totalmente distinto sobre astronomía", doc="a.md")
    # umbral alto: nada supera la barra para una consulta no relacionada
    assert almacen.buscar("recetas de cocina italiana", umbral=0.99) == []


def test_recencia_desempata(almacen):
    # dos trozos casi idénticos, uno viejo y uno nuevo
    ahora = time.time()
    almacen.indexar_texto("# Nota\nrecordatorio importante del proyecto",
                          doc="viejo.md", ahora=ahora - 60 * 86400)   # 60 días
    almacen.indexar_texto("# Nota\nrecordatorio importante del proyecto",
                          doc="nuevo.md", ahora=ahora)
    hits = almacen.buscar("recordatorio del proyecto", umbral=0.0, k=2,
                          vida_media_dias=30, ahora=ahora)
    assert hits[0]["doc"] == "nuevo.md"   # el reciente gana por el término de recencia


# ── Caché de embeddings ─────────────────────────────────────────────────────────

def test_reindexar_reusa_lo_que_no_cambio(tmp_path):
    llamadas = {"n": 0}

    class EmbContado(R.EmbedderHash):
        def embed(self, textos):
            llamadas["n"] += len(textos)
            return super().embed(textos)

    a = R.AlmacenRAG(tmp_path / "rag.db", EmbContado(dim=64))
    a.indexar_texto("# A\nuno\n# B\ndos", doc="d.md")
    assert llamadas["n"] == 2
    # reindexar el MISMO contenido no recalcula nada
    a.indexar_texto("# A\nuno\n# B\ndos", doc="d.md")
    assert llamadas["n"] == 2
    # cambiar un trozo recalcula solo ese
    a.indexar_texto("# A\nuno\n# B\ndos cambiado", doc="d.md")
    assert llamadas["n"] == 3
    a.cerrar()


def test_olvidar_doc(almacen):
    almacen.indexar_texto("# A\nuno", doc="a.md")
    almacen.indexar_texto("# B\ndos", doc="b.md")
    almacen.olvidar_doc("a.md")
    assert almacen.contar() == 1
    assert all(h["doc"] == "b.md" for h in almacen.buscar("cualquier cosa", umbral=0.0, k=5))


# ── Carpeta y formato para el prompt ────────────────────────────────────────────

def test_indexar_carpeta(tmp_path, almacen):
    (tmp_path / "n1.md").write_text("# Uno\ncontenido uno", encoding="utf-8")
    (tmp_path / "n2.txt").write_text("# Dos\ncontenido dos", encoding="utf-8")
    (tmp_path / "ignora.png").write_bytes(b"x")
    resumen = almacen.indexar_carpeta(tmp_path)
    assert set(resumen) == {"n1.md", "n2.txt"}


def test_contexto_para_prompt_cita_la_fuente(almacen):
    almacen.indexar_texto("# Proyecto Lune\nla fecha de entrega es el viernes", doc="agenda.md")
    ctx = almacen.contexto_para("cuándo entrego el proyecto", umbral=0.0, k=1)
    assert ctx and ctx[0][0].startswith("notas:agenda.md")
    assert "viernes" in ctx[0][1]


def test_persiste_entre_aperturas(tmp_path):
    db = tmp_path / "rag.db"
    a = R.AlmacenRAG(db, R.EmbedderHash())
    a.indexar_texto("# T\nun dato que debe persistir", doc="d.md")
    a.cerrar()
    b = R.AlmacenRAG(db, R.EmbedderHash())
    assert b.contar() == 1
    assert b.buscar("dato que persiste", umbral=0.0, k=1)
    b.cerrar()
