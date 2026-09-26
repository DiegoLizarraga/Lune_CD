"""
Tests del panel nativo de ajustes (ui/settings_panel.py), corte 2:
voz de edge-tts por país + velocidad/tono + acento de gTTS + «Probar», y la
sección «API compatible con OpenAI». Sin red, sin git y sin tocar el registro
de Windows (autoinicio) ni el datos.json de verdad.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import settings_panel as SP  # noqa: E402
from servicios import voces  # noqa: E402


# ── Funciones puras ──────────────────────────────────────────────────────────────

def test_textos_de_los_deslizadores():
    assert SP.texto_rate(10) == "+10%" and SP.texto_rate(-5) == "-5%" and SP.texto_rate(0) == "+0%"
    assert SP.texto_pitch(-50) == "-50Hz" and SP.texto_pitch(7) == "+7Hz"
    assert SP.numero_ajuste("+10%", "%") == 10 and SP.numero_ajuste("-80Hz", "Hz") == -50
    assert SP.numero_ajuste("basura", "%") == 0 and SP.numero_ajuste(None, "Hz") == 0


def test_items_voces_agrupa_por_pais_con_mexico_primero_y_multilingues_al_final():
    items = SP.items_voces(voces.voces_estaticas())
    cabeceras = [t for t, vid in items if vid is None]
    assert cabeceras[0] == "── México ──" and cabeceras[-1] == f"── {SP.MULTILINGUES} ──"
    ids = [vid for _, vid in items if vid]
    assert "es-MX-DaliaNeural" in ids and len(ids) == len(voces.voces_estaticas())
    assert any("Dalia (F) · es-MX-DaliaNeural" == t for t, _ in items)


def test_voz_para_personaje():
    base = {"motor": "edge", "id": "es-MX-DaliaNeural", "rate": "+0%"}
    v = SP.voz_para_personaje(base, "auto", "es-AR-ElenaNeural", "ef_dora", "+10%", "-5Hz", "es")
    assert "motor" not in v and v["id"] == "es-AR-ElenaNeural"
    assert (v["rate"], v["pitch"], v["tld"]) == ("+10%", "-5Hz", "es")
    assert SP.voz_para_personaje(base, "kokoro", "x", "em_alex", "+0%", "+0Hz", "com.mx")["id"] == "em_alex"
    g = SP.voz_para_personaje(base, "gtts", "x", "y", "+0%", "+0Hz", "us")
    assert g["motor"] == "gtts" and g["id"] == "es-MX-DaliaNeural"        # el id no se toca


# ── El panel ─────────────────────────────────────────────────────────────────────

class VozFalsa:
    def __init__(self):
        self.probadas = []
        self.ultimo_error = ""

    def probar_voz(self, params=None, texto=None):
        self.probadas.append(params)
        return True


DATOS = {
    "apis": {"openrouter_key": ""},
    "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": ""},
    "bot": {"personaje_default": "Lune"},
    "personajes": [{"nombre": "Lune", "systemPrompt": "x", "fraseInicial": "hola"}],
}


@pytest.fixture
def panel(qapp, tmp_path, monkeypatch):
    from nucleo.config import Config
    from servicios import autoinicio
    guardados = []
    estado = {"datos": copy.deepcopy(DATOS)}
    monkeypatch.setattr(SP.datos, "cargar", lambda: copy.deepcopy(estado["datos"]))
    monkeypatch.setattr(SP.datos, "guardar", lambda d: guardados.append(copy.deepcopy(d)))
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: ["faster-whisper"])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(autoinicio, "establecer", lambda on: None)
    # La voz del personaje la resuelve nucleo.personajes con el datos.json real:
    # que no se cuele un personaje de verdad.
    monkeypatch.setattr(voces, "_voz_personaje", lambda p: SP.voz_de(p))
    cfg = Config(str(tmp_path / "config.json"))
    voz = VozFalsa()

    def crear(datos=None):
        if datos is not None:
            estado["datos"] = copy.deepcopy(datos)
        p = SP.SettingsPanel(cfg, voice=voz)
        return p
    yield {"crear": crear, "cfg": cfg, "voz": voz, "guardados": guardados}


def test_voz_edge_por_defecto_y_cabeceras_no_seleccionables(panel):
    p = panel["crear"]()
    assert p.edge_voz_combo.currentData() == "es-MX-DaliaNeural"
    modelo = p.edge_voz_combo.model()
    cabecera = p.edge_voz_combo.findText("── México ──")
    assert cabecera >= 0 and not modelo.item(cabecera).isEnabled()
    assert p.voz_rate_slider.value() == 0 and p.lbl_voz_rate.text() == "+0%"
    p.voz_pitch_slider.setValue(-12)
    assert p.lbl_voz_pitch.text() == "-12Hz"


def test_probar_voz_usa_lo_elegido_sin_guardar(panel):
    p = panel["crear"]()
    p.edge_voz_combo.setCurrentIndex(p.edge_voz_combo.findData("es-AR-ElenaNeural"))
    p.voz_rate_slider.setValue(15)
    p.voz_motor_combo.setCurrentIndex(p.voz_motor_combo.findData("edge"))
    p._probar_voz()
    prm = panel["voz"].probadas[-1]
    assert prm["motor"] == "edge" and prm["id"] == "es-AR-ElenaNeural" and prm["rate"] == "+15%"
    assert panel["guardados"] == []                                     # probar no guarda
    assert voces.params_desde(prm).id == "es-AR-ElenaNeural"


def test_guardar_voz_y_compat_en_config_y_datos(panel):
    p = panel["crear"]()
    p.edge_voz_combo.setCurrentIndex(p.edge_voz_combo.findData("es-ES-ElviraNeural"))
    p.voz_rate_slider.setValue(-10)
    p.voz_pitch_slider.setValue(5)
    p.gtts_tld_combo.setCurrentIndex(p.gtts_tld_combo.findData("es"))
    p.fields["compat_url"].setText("http://localhost:1234/v1/")
    p.fields["compat_key"].setText(" sk-1 ")
    p.fields["compat_model"].setText("qwen2.5-7b")
    p._save()
    cfg = panel["cfg"]
    assert cfg.get("voz", "edge_voz") == "es-ES-ElviraNeural"
    assert (cfg.get("voz", "edge_rate"), cfg.get("voz", "edge_pitch")) == ("-10%", "+5Hz")
    assert cfg.get("voz", "gtts_tld") == "es"
    d = panel["guardados"][-1]
    assert d["modelos"]["compat_url"] == "http://localhost:1234/v1"
    assert d["modelos"]["compat_key"] == "sk-1" and d["modelos"]["compat_model"] == "qwen2.5-7b"
    assert "voz" not in d["personajes"][0]                   # sin voz propia: solo config


def test_personaje_con_voz_propia_la_recibe_al_guardar(panel):
    datos = copy.deepcopy(DATOS)
    datos["personajes"][0]["voz"] = {"motor": "edge", "id": "es-CO-SalomeNeural", "rate": "+20%"}
    p = panel["crear"](datos)
    assert p.edge_voz_combo.currentData() == "es-CO-SalomeNeural"      # la del personaje manda
    assert p.voz_rate_slider.value() == 20
    antes = copy.deepcopy(panel["cfg"].config.get("voz", {}))
    p.edge_voz_combo.setCurrentIndex(p.edge_voz_combo.findData("es-MX-JorgeNeural"))
    p._save()
    voz = panel["guardados"][-1]["personajes"][0]["voz"]
    assert voz == {"motor": "edge", "id": "es-MX-JorgeNeural", "rate": "+20%"}   # ni pitch ni tld inventados
    # A1: el cambio va a la voz del personaje; la global (config.voz) no se toca.
    assert panel["cfg"].config.get("voz", {}) == antes


def test_guardar_otra_cosa_no_pisa_la_voz_global_con_la_del_personaje(panel):
    """A1: con un personaje con voz propia (edge) y la global en Kokoro, guardar
    cualquier otra cosa no convierte la global en edge ni toca la del personaje."""
    datos = copy.deepcopy(DATOS)
    datos["personajes"][0]["voz"] = {"motor": "edge", "id": "es-CO-SalomeNeural", "rate": "+20%"}
    cfg = panel["cfg"]
    for clave, valor in (("motor_salida", "kokoro"), ("kokoro_voz", "em_alex"), ("edge_rate", "-5%")):
        cfg.config.setdefault("voz", {})[clave] = valor
    antes = copy.deepcopy(cfg.config["voz"])
    p = panel["crear"](datos)
    assert p.voz_motor_combo.currentData() == "edge"                    # se ve la que suena
    p.fields["compat_model"].setText("qwen2.5-7b")
    p._save()
    d = panel["guardados"][-1]
    assert d["personajes"][0]["voz"] == {"motor": "edge", "id": "es-CO-SalomeNeural", "rate": "+20%"}
    assert cfg.config["voz"] == antes
    assert d["modelos"]["compat_model"] == "qwen2.5-7b"


def test_sin_voz_propia_solo_se_escribe_en_config_lo_cambiado(panel):
    cfg = panel["cfg"]
    cfg.config.setdefault("voz", {})["motor_salida"] = "kokoro"
    p = panel["crear"]()
    p.voz_rate_slider.setValue(12)
    p._save()
    assert cfg.get("voz", "edge_rate") == "+12%"
    assert cfg.get("voz", "motor_salida") == "kokoro"                   # no lo tocaste: sigue
    assert "voz" not in panel["guardados"][-1]["personajes"][0]


def test_la_voz_de_kokoro_del_personaje_se_ve_y_no_se_pisa(panel):
    datos = copy.deepcopy(DATOS)
    datos["personajes"][0]["voz"] = {"motor": "kokoro", "id": "em_alex"}
    p = panel["crear"](datos)
    assert p.kokoro_voz_combo.currentData() == "em_alex"
    p.voz_pitch_slider.setValue(3)
    p._save()
    assert panel["guardados"][-1]["personajes"][0]["voz"] == {"motor": "kokoro", "id": "em_alex",
                                                              "pitch": "+3Hz"}


def test_vaciar_la_clave_compat_quita_tambien_el_alias_de_apis(panel):
    datos = copy.deepcopy(DATOS)
    datos["apis"]["compat_key"] = "gsk_viejo"
    p = panel["crear"](datos)
    assert p.fields["compat_key"].text() == "gsk_viejo"
    p.fields["compat_key"].setText("")
    p._save()
    d = panel["guardados"][-1]
    assert d["modelos"]["compat_key"] == "" and "compat_key" not in d["apis"]


# ── Guardar no deshace lo que otros escribieron mientras (G2) ─────────────────────

@pytest.fixture
def panel_real(qapp, tmp_path, monkeypatch):
    """El panel con un datos.json de verdad en una carpeta temporal."""
    import json
    from nucleo import datos as D
    from nucleo.config import Config
    from servicios import autoinicio
    ruta = tmp_path / "datos.json"
    base = copy.deepcopy(DATOS)
    base["personajes"].append({"nombre": "Aria", "systemPrompt": "y", "fraseInicial": "hey"})
    ruta.write_text(json.dumps(base), "utf-8")
    monkeypatch.setattr(D, "_PATH", ruta)
    D.invalidar()
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: ["faster-whisper"])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(autoinicio, "establecer", lambda on: None)
    cfg = Config(str(tmp_path / "config.json"))
    p = SP.SettingsPanel(cfg, voice=VozFalsa())
    yield p, cfg
    p.vrm_panel._timer.stop()
    D.invalidar()


def test_guardar_no_deshace_lo_que_otros_escribieron(panel_real):
    from nucleo import datos as D, personajes
    p, cfg = panel_real                         # construido con «Lune» activa
    # Mientras el panel estaba construido: panel VRM, herramienta cambiar_voz,
    # cambio de personaje, pack del personaje y la temperatura desde patata.
    d = D.cargar()
    d["personajes"][0]["vrm"] = "b_otra.vrm"
    d["personajes"][0]["voz"] = {"motor": "edge", "id": "es-AR-ElenaNeural"}
    d["modelos"]["temperatura"] = 1.3
    D.guardar(d)
    personajes.set_activo("Aria")
    cfg.set("avatar", "pack", "otro_pack")
    # Solo se cambia el modelo de OpenRouter y el saludo (del personaje editado: Lune).
    p.fields["openrouter_model"].setText("meta/llama-3")
    p.fields["bot_saludo"].setPlainText("¡Hola de nuevo!")
    p._save()
    D.invalidar()
    lune, aria = D.get_personajes()
    assert lune["vrm"] == "b_otra.vrm" and lune["voz"] == {"motor": "edge", "id": "es-AR-ElenaNeural"}
    assert lune["fraseInicial"] == "¡Hola de nuevo!" and aria["fraseInicial"] == "hey"
    assert D.get_bot()["personaje_default"] == "Aria"                    # sigue la elegida
    assert D.get_modelos()["temperatura"] == 1.3                         # no la tocaste aquí
    assert D.get_modelos()["openrouter_model"] == "meta/llama-3"
    assert cfg.get("avatar", "pack") == "otro_pack"
    # Un segundo guardado sin cambios no escribe nada nuevo encima.
    d = D.cargar(); d["modelos"]["temperatura"] = 0.2; D.guardar(d)
    p._save()
    D.invalidar()
    assert D.get_modelos()["temperatura"] == 0.2


def test_renombrar_el_personaje_activo_lo_deja_activo(panel_real):
    from nucleo import datos as D
    p, _cfg = panel_real
    p.fields["bot_nombre"].setText("Luna")
    p._save()
    D.invalidar()
    assert [x["nombre"] for x in D.get_personajes()] == ["Luna", "Aria"]
    assert D.get_bot()["personaje_default"] == "Luna"
    p.fields["bot_system"].setPlainText("nuevo prompt")
    p._save()                                                            # sigue editando «Luna»
    D.invalidar()
    assert D.get_personajes()[0]["systemPrompt"] == "nuevo prompt"


def test_probar_compat_sin_url_avisa_y_con_url_usa_lo_escrito(panel, monkeypatch):
    p = panel["crear"]()
    p._probar_compat()
    assert "URL" in p.lbl_compat.text() and p._prueba_compat is None
    pedidos = []

    class Falso:
        def __init__(self, url, clave, modelo):
            pedidos.append((url, clave, modelo))

        def probar(self):
            return {"ok": True, "mensaje": "Conectado", "ms": 12, "modelos": ["a", {"id": "b"}]}

    import servicios.ai_manager as AM
    monkeypatch.setattr(AM, "CompatProvider", Falso)
    p.fields["compat_url"].setText("http://localhost:1234/v1")
    p._probar_compat()
    p._prueba_compat.wait(5000)
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    assert pedidos == [("http://localhost:1234/v1", "", "")]
    assert "Conectado (12 ms)" in p.lbl_compat.text() and "a, b" in p.lbl_compat.text()
