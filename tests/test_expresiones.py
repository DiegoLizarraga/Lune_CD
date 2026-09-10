"""
Tests del plan de expresiones (lune_core/expresiones.py), del vocabulario nuevo
(laughing, bored) y de que todas las capas lo cubren: gramática del prompt,
caritas del modo patata, mapas de la mascota (barra lateral, video, sprites, 3D).
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import expresiones as X  # noqa: E402
from lune_core import marcadores as M  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


# ── Plan de una respuesta ──────────────────────────────────────────────────────

def test_planificar_tres_tramos_y_texto_inicial_hereda_la_primera():
    r = ('Bueno, <|ACT {"emotion":"happy","intensity":0.7}|>¡qué buena noticia! '
         '<|ACT laughing|>jaja, no me lo creo. <|ACT {"emotion":"curious","intensity":0.4}|>¿Y ahora qué?')
    plan = X.planificar(r)
    assert [t.emocion for t in plan] == ["happy", "laughing", "curious"]
    assert plan[0].texto == "Bueno, ¡qué buena noticia! "      # lo de antes del 1er marcador
    assert plan[1].texto == "jaja, no me lo creo. "
    assert abs(plan[0].intensidad - 0.7) < 1e-9 and abs(plan[2].intensidad - 0.4) < 1e-9
    assert X.hablable(plan) == "Bueno, ¡qué buena noticia! jaja, no me lo creo. ¿Y ahora qué?"
    assert X.emociones(plan) == ["happy", "laughing", "curious"]
    assert X.final(plan) == "curious"


def test_planificar_sin_marcadores():
    plan = X.planificar("Hola, sin dramas.")
    assert len(plan) == 1 and plan[0].emocion == "" and plan[0].texto == "Hola, sin dramas."
    assert X.emociones(plan) == [] and X.final(plan, "happy") == "happy"
    assert X.horario(plan) == []


def test_marcadores_seguidos_se_funden_y_el_ultimo_manda():
    plan = X.planificar("<|ACT happy|><|ACT angry|>Pues no. <|ACT sad|>")
    assert [t.emocion for t in plan] == ["angry", "sad"]
    assert plan[0].texto == "Pues no. " and plan[1].texto == ""
    assert X.final(plan) == "sad"                       # un marcador al final también cuenta


def test_delay_y_call_no_tocan_el_plan():
    plan = X.planificar('<|ACT happy|>Uno <|DELAY 1|>dos <|CALL ["abrir","x"]|>tres')
    assert len(plan) == 1 and plan[0].texto == "Uno dos tres"


def test_horario_al_ritmo_de_lectura():
    plan = [X.Tramo("happy", 0.8, "a" * 32), X.Tramo("laughing", 1.0, "b" * 16), X.Tramo("sad", 0.5, "c")]
    h = X.horario(plan)
    assert [e for _, e, _ in h] == ["happy", "laughing", "sad"]
    assert h[0][0] == 0.0
    assert abs(h[1][0] - 32 / X.CARACTERES_POR_SEGUNDO) < 1e-6
    assert abs(h[2][0] - (32 + 16) / X.CARACTERES_POR_SEGUNDO) < 1e-6
    assert X.duracion_lectura("hola") == X.MINIMO_TRAMO_S      # nada dura menos que el mínimo


def test_segmentos_voz_traduce_y_omite_tramos_vacios():
    plan = X.planificar("<|ACT happy|>Hola. <|ACT laughing|>  <|ACT sad|>Adiós.")
    segs = X.segmentos_voz(plan, lambda e: e.upper())
    assert segs == [("HAPPY", "Hola. "), ("SAD", "  Adiós.")]     # el texto se conserva entero
    assert X.segmentos_voz([X.Tramo("", 1.0, "sin emoción")]) == [("", "sin emoción")]


def test_seguidor_de_actos_en_streaming():
    s = X.SeguidorActs()
    assert s.nuevos("Hola ") == []
    assert s.nuevos("Hola <|ACT hap") == []                    # a medias: aún no
    nuevos = s.nuevos('Hola <|ACT happy|> qué tal <|ACT {"emotion":"laughing"}|>')
    assert [a["emotion"] for a in nuevos] == ["happy", "laughing"]
    assert s.nuevos('Hola <|ACT happy|> qué tal <|ACT {"emotion":"laughing"}|> y más') == []
    assert s.vistos == 2


# ── Vocabulario nuevo en todas las capas ───────────────────────────────────────

def test_vocabulario_tiene_laughing_y_bored():
    assert "laughing" in M.EMOCIONES and "bored" in M.EMOCIONES
    for alias, esperada in (("jaja", "laughing"), ("lol", "laughing"), ("laugh", "laughing"),
                            ("aburrida", "bored"), ("meh", "bored"), ("boring", "bored")):
        assert M.normalizar_emocion(alias) == esperada


def test_la_gramatica_pide_hasta_tres_marcadores_delante_del_tramo():
    from lune_core.prompt import GRAMATICA_EMOCIONES as G
    assert "laughing" in G and "bored" in G
    assert "máximo tres" in G and "JUSTO" in G and "se queda con el último" in G


def test_todas_las_capas_cubren_todas_las_emociones():
    import patata
    from ui.web_bridge import EMOCION_A_MASCOTA
    from ui.companion import EMOCION_A_ESTADO
    from ui.lune_face import EMOCION_A_ESTADO as SPRITES
    for e in M.EMOCIONES:
        assert e in patata.CARITAS, f"patata sin carita para {e}"
        assert e in EMOCION_A_MASCOTA, f"puente sin estado para {e}"
        assert e in EMOCION_A_ESTADO, f"companion sin estado para {e}"
        assert e in SPRITES, f"sprites sin estado para {e}"
    estados = set(EMOCION_A_MASCOTA.values()) | set(EMOCION_A_ESTADO.values())
    # los clips de la barra lateral y de la mascota en video
    side = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "sidebar.jsx").read_text("utf-8")
    vid = side[side.index("const VID = {"):side.index("const VID_DIR")]
    comp = (RAIZ / "ui_web" / "companion.html").read_text("utf-8")
    mapa = comp[comp.index("var MAP = {"):comp.index("var vid")]
    for est in estados:
        assert re.search(rf"\b{est}\s*:", vid), f"sidebar.jsx sin clip para {est}"
        assert re.search(rf"\b{est}\s*:", mapa), f"companion.html sin clip para {est}"


def test_clips_nuevos_convertidos_a_webm():
    carpeta = RAIZ / "ui_web" / "assets" / "mascot" / "anime-videos"
    for est in ("laughing", "bored", "sad", "curious", "listening", "talking", "working", "dismiss"):
        assert (carpeta / f"lune-{est}.webm").is_file(), f"falta lune-{est}.webm (scripts/convertir_mascota.py)"


def test_la_ui_web_deja_la_expresion_y_el_puente_la_lleva():
    app = (RAIZ / "ui_web" / "ui_kits" / "lune-desktop" / "app.jsx").read_text("utf-8")
    assert "if (mascota) setMascot(mascota)" in app
    assert "setTimeout(() => setMascot('normal'), holdRef" not in app
    assert "setTyping(false); setMascot('typing')" not in app
    bridge = (RAIZ / "ui" / "web_bridge.py").read_text("utf-8")
    for nombre in ("_on_chunk", "_al_segmento_voz", "_al_terminar_voz", "_programar_plan", "_voz_lee_al_final"):
        assert f"def {nombre}" in bridge
    assert "al_terminar=lambda g=gen, est=mascota: self._al_terminar_voz(est, g)" in bridge
    # tras Detener el proveedor no puede quedarse con cancel_flag levantado
    assert "cancel_flag = False" in bridge and "self._gen += 1" in bridge
    assert "self.voice.cancelar()" in bridge
    principal = (RAIZ / "main.py").read_text("utf-8")
    assert "speak_segmentos(" in principal and "_programar_plan" in principal
    # las emociones se quedan (auto_revert 0); solo los estados de proceso vuelven al idle
    assert "_ESTADOS_PROCESO" in principal
    assert "self.lune_face.set_state(emotion, auto_revert_ms=6000)" not in principal
