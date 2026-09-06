"""
Tests del arranque: pantalla de inicio y lanzador .vbs.

Los dos fallos que motivaron estos tests:
  · El .vbs adivinaba la ruta de pythonw y acertaba con un Python SIN PyQt6,
    así que la app moría al importar y —al ir oculta— no pasaba nada visible.
  · Varias vías (fin del video, botón de saltar, temporizador de seguridad)
    llamaban a la transición y se abrían dos ventanas principales.
"""
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


# ── Lanzador .vbs ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def vbs():
    return (RAIZ / "iniciar_lune.vbs").read_text("latin-1")


def test_el_vbs_verifica_el_interprete(vbs):
    """No basta con que exista pythonw.exe: tiene que poder importar PyQt6."""
    assert "SirveEsteInterprete" in vbs
    assert "import PyQt6" in vbs


def test_el_vbs_prueba_todos_los_candidatos_por_orden(vbs):
    """El del PATH (el que usó pip) debe ir antes que las rutas adivinadas."""
    pos_path = vbs.index('"pythonw.exe"')
    pos_adivinada = vbs.index("Program Files\\Python313")
    assert pos_path < pos_adivinada


def test_el_vbs_avisa_si_no_encuentra_python(vbs):
    """El modo silencioso era el problema: sin ventana no había ni pista."""
    assert "MsgBox" in vbs
    assert "requirements.txt" in vbs


def test_el_vbs_usa_rutas_relativas_al_script(vbs):
    assert "WScript.ScriptFullName" in vbs
    assert "GetParentFolderName" in vbs


def test_el_vbs_no_lanza_la_app_en_modo_oculto(vbs):
    """
    El fallo más caro de todos: `shell.Run cmd, 0, False`.

    Windows pasa ese estilo de ventana al proceso hijo vía STARTUPINFO y Qt lo
    aplica a la primera ventana de nivel superior. Con 0 (SW_HIDE) la pantalla
    de inicio se creaba INVISIBLE: el proceso corría, el video se reproducía y
    en pantalla no aparecía nada. Comprobado con A/B: con 0 IsWindowVisible es
    False, con 1 es True.

    pythonw.exe ya arranca sin consola, así que ocultar no aportaba nada.
    """
    lanzamientos = re.findall(r"shell\.Run\s+[^,\n]+,\s*(\d+)\s*,\s*False", vbs)
    assert lanzamientos, "No encontré el shell.Run que lanza la app"
    for estilo in lanzamientos:
        assert estilo != "0", (
            "El .vbs lanza la app con estilo de ventana 0 (oculta). "
            "Tiene que ser 1, o la ventana nunca se ve."
        )


def test_el_codigo_deshace_el_arranque_oculto():
    """Cinturón y tirantes por si otro lanzador pasa SW_HIDE."""
    codigo = (RAIZ / "main.py").read_text("utf-8")
    assert "_mostrar_de_verdad" in codigo
    assert "showNormal" in codigo
    assert "activateWindow" in codigo


# ── Pantalla de inicio ─────────────────────────────────────────────────────────

def test_el_splash_no_abre_dos_ventanas(qapp):
    from ui.splash import PantallaInicio
    llamadas = []
    s = PantallaInicio(al_terminar=lambda: llamadas.append(1))
    # Fin del video + botón de saltar + red de seguridad, casi a la vez
    s.entrar(); s.entrar(); s.entrar()
    assert len(llamadas) == 1


def test_el_splash_marca_que_termino(qapp):
    from ui.splash import PantallaInicio
    s = PantallaInicio(al_terminar=lambda: None)
    assert s._terminado is False
    s.entrar()
    assert s._terminado is True


def test_el_fondo_no_es_el_padre_del_video(qapp):
    """
    El fondo repinta a 30 fps y el video va a 24: si el video colgara de él,
    lo taparía de negro entre fotogramas. Deben ser hermanos.
    """
    from ui.splash import PantallaInicio
    s = PantallaInicio(al_terminar=lambda: None)
    if not hasattr(s, "video_widget"):
        pytest.skip("Sin multimedia o sin inicio.mp4")
    assert s.marco_video.parent() is not s.fondo
    assert s.fondo.parent() is s.centralWidget()


def test_el_video_no_es_una_ventana_suelta(qapp):
    """
    El video tiene que ser un widget hijo, no una ventana independiente.

    Marcarlo con WA_NativeWindow antes de darle padre hacía que Qt lo creara
    como ventana de nivel superior: aparecía una ventana fantasma suelta y la
    jerarquía del splash quedaba rota. No hace falta ninguna ventana nativa —
    el fondo de estrellas ya es hermano del contenido, no su padre.
    """
    from ui.splash import PantallaInicio
    s = PantallaInicio(al_terminar=lambda: None)
    if not hasattr(s, "video_widget"):
        pytest.skip("Sin multimedia o sin inicio.mp4")
    assert s.video_widget.isWindow() is False
    assert s.video_widget.parent() is not None


# ── Instancia única ────────────────────────────────────────────────────────────

def test_hay_guardia_de_instancia_unica():
    codigo = (RAIZ / "main.py").read_text("utf-8")
    assert "_ya_hay_una_instancia" in codigo
    assert "QLocalServer" in codigo
    # Un servidor huérfano de un cierre a lo bruto bloquearía el arranque
    assert "removeServer" in codigo
