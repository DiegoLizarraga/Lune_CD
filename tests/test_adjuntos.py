"""Tests de la lectura de documentos e imágenes."""
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adjuntos  # noqa: E402


# PNG 1x1 real, para no depender de tener Pillow
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ── Documentos de texto ────────────────────────────────────────────────────────

def test_lee_texto_plano(tmp_path):
    f = tmp_path / "notas.txt"
    f.write_text("hola mundo", encoding="utf-8")
    a = adjuntos.cargar(f)
    assert a["tipo"] == "documento"
    assert a["texto"] == "hola mundo"
    assert a["nombre"] == "notas.txt"
    assert a["truncado"] is False


def test_lee_codigo(tmp_path):
    f = tmp_path / "script.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    assert "def x()" in adjuntos.cargar(f)["texto"]


def test_lee_cp1252(tmp_path):
    """Windows escupe cp1252 constantemente; no debe fallar."""
    f = tmp_path / "viejo.txt"
    f.write_bytes("acentuación española".encode("cp1252"))
    assert "espa" in adjuntos.cargar(f)["texto"]


def test_recorta_documentos_largos(tmp_path):
    f = tmp_path / "gordo.txt"
    f.write_text("a" * 5000, encoding="utf-8")
    a = adjuntos.cargar(f, max_caracteres=1000)
    assert a["truncado"] is True
    assert len(a["texto"]) < 1200
    assert "recortado" in a["texto"]


def test_csv_se_tabula(tmp_path):
    f = tmp_path / "datos.csv"
    f.write_text("nombre,edad\nDiego,25\nAna,30\n", encoding="utf-8")
    texto = adjuntos.cargar(f)["texto"]
    assert "nombre | edad" in texto
    assert "Diego | 25" in texto


def test_archivo_vacio_da_error(tmp_path):
    f = tmp_path / "vacio.txt"
    f.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="vacío"):
        adjuntos.cargar(f)


def test_archivo_inexistente():
    with pytest.raises(ValueError, match="no existe"):
        adjuntos.cargar("no_existe_en_ningun_lado.txt")


def test_extension_no_soportada(tmp_path):
    f = tmp_path / "raro.xyz"
    f.write_text("contenido", encoding="utf-8")
    with pytest.raises(ValueError, match="No sé leer"):
        adjuntos.cargar(f)


# ── Imágenes ───────────────────────────────────────────────────────────────────

def test_lee_imagen(tmp_path):
    f = tmp_path / "foto.png"
    f.write_bytes(PNG_1x1)
    a = adjuntos.cargar(f)
    assert a["tipo"] == "imagen"
    assert a["mime"] == "image/png"
    assert base64.b64decode(a["base64"]) == PNG_1x1


def test_imagen_demasiado_grande(tmp_path):
    f = tmp_path / "enorme.png"
    f.write_bytes(b"\x00" * (adjuntos.MAX_BYTES_IMAGEN + 1))
    with pytest.raises(ValueError, match="límite"):
        adjuntos.cargar(f)


@pytest.mark.parametrize("nombre,esperado", [
    ("foto.png", True), ("foto.JPG", True), ("doc.pdf", False), ("x.txt", False),
])
def test_es_imagen(nombre, esperado):
    assert adjuntos.es_imagen(nombre) is esperado


# ── Composición del prompt ─────────────────────────────────────────────────────

def test_bloque_para_prompt_incluye_documentos(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("contenido secreto", encoding="utf-8")
    bloque = adjuntos.bloque_para_prompt([adjuntos.cargar(f)])
    assert "contenido secreto" in bloque
    assert "a.txt" in bloque
    assert "INICIO DE" in bloque and "FIN DE" in bloque


def test_las_imagenes_no_van_en_el_prompt_de_texto(tmp_path):
    f = tmp_path / "foto.png"; f.write_bytes(PNG_1x1)
    imagen = adjuntos.cargar(f)
    assert adjuntos.bloque_para_prompt([imagen]) == ""
    assert adjuntos.imagenes_base64([imagen]) == [imagen["base64"]]


def test_sin_adjuntos_no_hay_bloque():
    assert adjuntos.bloque_para_prompt([]) == ""
    assert adjuntos.imagenes_base64([]) == []


def test_resumen(tmp_path):
    f = tmp_path / "a.txt"; f.write_text("hola", encoding="utf-8")
    assert "a.txt" in adjuntos.resumen([adjuntos.cargar(f)])
    assert adjuntos.resumen([]) == ""


# ── PDF y DOCX (se saltan si faltan las librerías) ─────────────────────────────

def test_pdf_real(tmp_path):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    f = tmp_path / "doc.pdf"
    w = PdfWriter(); w.add_blank_page(width=200, height=200)
    with open(f, "wb") as fh:
        w.write(fh)
    # Una página en blanco no tiene texto → debe avisar, no reventar
    with pytest.raises(ValueError, match="texto extraíble"):
        adjuntos.cargar(f)


def test_docx_real(tmp_path):
    pytest.importorskip("docx")
    import docx
    f = tmp_path / "doc.docx"
    d = docx.Document(); d.add_paragraph("Párrafo de prueba"); d.save(str(f))
    assert "Párrafo de prueba" in adjuntos.cargar(f)["texto"]
