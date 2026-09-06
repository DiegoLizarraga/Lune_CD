"""
Tests del saneamiento de herramientas.

Estas funciones reciben texto que puede venir del MODELO (el system prompt le
enseña a emitir `TOOL:lanzar_app:...`), así que se tratan como entrada no
confiable: antes se pasaban por `os.system` con f-strings.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios.tools import ToolManager, _nombre_app_seguro, _url_segura  # noqa: E402


# ── Nombres de aplicación ──────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", ["paint", "Bloc de notas", "notepad", "vlc", "calc"])
def test_nombres_normales_se_aceptan(nombre):
    assert _nombre_app_seguro(nombre) == nombre


@pytest.mark.parametrize("nombre", [
    'x" & del /q C:\\*',
    "calc && shutdown -s -t 0",
    "notepad; rm -rf /",
    "notepad | curl evil.com",
    "..\\..\\Windows\\System32\\cmd",
    "C:/Windows/System32/cmd.exe",
    "$(whoami)",
    "`whoami`",
    "a" * 80,
    "",
    None,
])
def test_inyeccion_de_comandos_se_rechaza(nombre):
    assert _nombre_app_seguro(nombre) is None


# ── URLs ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,esperada", [
    ("https://youtube.com", "https://youtube.com"),
    ("http://192.168.1.50:11434", "http://192.168.1.50:11434"),
    ("wikipedia.org", "https://wikipedia.org"),
    ("  https://x.com/algo  ", "https://x.com/algo"),
])
def test_urls_validas(url, esperada):
    assert _url_segura(url) == esperada


@pytest.mark.parametrize("url", [
    "file:///C:/Users/secretos.txt",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "ftp://servidor/archivo",
    "vbscript:msgbox(1)",
    "",
    None,
])
def test_esquemas_peligrosos_se_rechazan(url):
    assert _url_segura(url) is None


def test_abrir_url_no_abre_nada_peligroso():
    """El resultado debe ser un fallo controlado, no una excepción."""
    resultado = ToolManager()._cmd_abrir_url("file:///C:/Windows/System32/config/SAM")
    assert resultado.ok is False


def test_lanzar_app_rechaza_inyeccion():
    resultado = ToolManager()._cmd_lanzar_app('calc" & del /q C:\\*')
    assert resultado.ok is False
    assert "no es válido" in resultado.mensaje


# ── Parseo de la respuesta de la IA ────────────────────────────────────────────

def test_parseo_extrae_acciones_y_limpia_el_texto():
    tm = ToolManager()
    respuesta = "Claro, te abro el buscador.\nABRIR_BUSQUEDA:gatos graciosos"
    limpio, acciones = tm.parsear_respuesta_ia(respuesta)

    assert "ABRIR_BUSQUEDA" not in limpio
    assert acciones == [{"herramienta": "buscar_web", "args": "gatos graciosos"}]


def test_parseo_sin_acciones_no_toca_el_texto():
    tm = ToolManager()
    texto = "Esta es una respuesta normal, sin herramientas."
    limpio, acciones = tm.parsear_respuesta_ia(texto)

    assert limpio == texto
    assert acciones == []


def test_herramienta_desconocida_no_revienta():
    resultado = ToolManager().ejecutar("herramienta_que_no_existe", args="x")
    assert resultado.ok is False
