"""
Tests de ui/vrm_panel_nativo.py: el panel de modelos VRM de la interfaz nativa.

Con QT_QPA_PLATFORM=offscreen, la carpeta de modelos en tmp (monkeypatch de
nucleo.vrm.CARPETA, como tests/test_mascota_vrm.py) y datos.json de mentira para
los personajes. Los GLB sintéticos son los de tests/test_vrm_miniatura.py.
"""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_vrm_miniatura import ConfigFalsa, vrm0_con_miniatura, vrm1_con_miniatura, vrm1_sin_nada  # noqa: E402


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    from nucleo import vrm
    c = tmp_path / "modelo_vrm"; c.mkdir()
    (c / "a_luna.vrm").write_bytes(vrm1_con_miniatura())      # lookAt por huesos de los ojos
    (c / "b_vieja.vrm").write_bytes(vrm0_con_miniatura())     # lookAt por blendshapes
    (c / "c_pelada.vrm").write_bytes(vrm1_sin_nada())         # sin lookAt ni miniatura
    (c / "roto.vrm").write_bytes(b"esto no es un glb")
    monkeypatch.setattr(vrm, "CARPETA", c)
    vrm._miniatura_url.cache_clear()
    return c


@pytest.fixture
def almacen(monkeypatch):
    from nucleo import datos, personajes
    alm = {"bot": {"personaje_default": "Aria"},
           "personajes": [{"nombre": "Lune", "systemPrompt": "x", "vrm": "a_luna.vrm"},
                          {"nombre": "Aria", "systemPrompt": "y", "vrm": "b_vieja.vrm"}]}
    monkeypatch.setattr(personajes, "_load", lambda: alm)
    monkeypatch.setattr(personajes, "_save", lambda d: None)
    monkeypatch.setattr(datos, "invalidar", lambda: None)
    return alm


def aria(alm):
    return next(p for p in alm["personajes"] if p["nombre"] == "Aria")


@pytest.fixture
def panel(qapp, carpeta, almacen):
    from ui.vrm_panel_nativo import VrmPanelNativo
    p = VrmPanelNativo(ConfigFalsa({"peso_torso": 0.5}))
    p.senales = []
    p.cambiado.connect(lambda: p.senales.append(1))
    yield p
    p._timer.stop()
    p.deleteLater()


def elegir(panel, archivo):
    i = panel.combo.findData(archivo)
    assert i >= 0, archivo
    panel.combo.setCurrentIndex(i)
    assert panel.modelo == archivo


# ── Lista y ficha ────────────────────────────────────────────────────────────────

def test_lista_los_validos_y_elige_el_del_personaje_activo(panel):
    datos = [panel.combo.itemData(i) for i in range(panel.combo.count())]
    assert datos == ["a_luna.vrm", "b_vieja.vrm", "c_pelada.vrm"]          # roto.vrm no
    assert panel.modelo == "b_vieja.vrm"                                    # el de Aria (activa)
    assert panel.combo.isEnabled()
    assert panel.btn_asignar.text() == "USAR CON ARIA"
    assert not panel.btn_asignar.isEnabled()                                # ya lo usa
    assert panel.btn_quitar.isEnabled()
    ficha = panel.ficha.text()
    assert "VRM 0.x" in ficha and "Vieja" in ficha and "Alguien" in ficha and "Aria" in ficha
    assert not panel.miniatura.pixmap().isNull()                            # el PNG del modelo
    elegir(panel, "c_pelada.vrm")
    assert panel.miniatura.pixmap().isNull() and panel.miniatura.text() == "3D"
    assert "VRM 1.0" in panel.ficha.text()


def test_sin_personaje_con_modelo_usa_el_de_config_o_el_primero(qapp, carpeta, almacen):
    from ui.vrm_panel_nativo import VrmPanelNativo
    aria(almacen).pop("vrm")
    p = VrmPanelNativo(ConfigFalsa({"vrm_archivo": "c_pelada.vrm"}))
    assert p.modelo == "c_pelada.vrm" and not p.btn_quitar.isEnabled()
    q = VrmPanelNativo(None)
    assert q.modelo == "a_luna.vrm"


def test_sin_modelos(qapp, tmp_path, monkeypatch, almacen):
    from nucleo import vrm
    from ui.vrm_panel_nativo import VrmPanelNativo
    vacia = tmp_path / "vacia"
    monkeypatch.setattr(vrm, "CARPETA", vacia)                              # ni siquiera existe
    p = VrmPanelNativo(None)
    assert p.modelo == "" and not p.combo.isEnabled()
    assert "No hay modelos" in p.combo.currentText()
    assert not p.btn_asignar.isEnabled()
    assert p.btn_importar.isEnabled()
    assert all(not s.isEnabled() for s in p.sliders.values())
    assert "Importar" in p.ficha.text()


# ── Seguimiento ──────────────────────────────────────────────────────────────────

def test_sliders_muestran_pesos_del_modelo_de_config_y_por_defecto(panel, carpeta):
    from nucleo import vrm
    vrm.guardar_ajustes_modelo("a_luna.vrm", {"pesoCabeza": 0.3})
    panel.recargar(elegir="a_luna.vrm")
    assert panel.sliders["pesoCabeza"].value() == 30                       # del modelo
    assert panel.sliders["pesoTorso"].value() == 50                        # avatar.peso_torso
    assert panel.sliders["pesoOjos"].value() == 100                        # por defecto
    assert panel._valores["pesoCabeza"].text() == "30 %"
    assert panel.senales == []                                              # cargar no es cambiar
    assert not panel.pendiente


def test_mover_un_slider_guarda_en_el_lune_json(panel, carpeta):
    elegir(panel, "a_luna.vrm")
    archivo = carpeta / "a_luna.lune.json"
    panel.sliders["pesoTorso"].setValue(70)
    assert panel.pendiente and panel._timer.isActive()
    assert not archivo.exists()                                             # espera a que se quede quieto
    panel.sliders["pesoTorso"].setValue(75)
    assert panel.guardar_ya() is True
    assert json.loads(archivo.read_text("utf-8")) == {"pesoTorso": 0.75}
    assert panel.senales == [1] and not panel.pendiente
    assert "guardado" in panel.estado.text().lower()
    assert panel.guardar_ya() is False                                      # nada pendiente


def test_el_temporizador_escribe_solo(panel, carpeta):
    from PyQt6.QtTest import QTest
    from ui.vrm_panel_nativo import ESPERA_GUARDADO_MS
    elegir(panel, "a_luna.vrm")
    panel.sliders["pesoCabeza"].setValue(40)
    QTest.qWait(ESPERA_GUARDADO_MS + 250)
    assert json.loads((carpeta / "a_luna.lune.json").read_text("utf-8")) == {"pesoCabeza": 0.4}
    assert panel.senales == [1]


def test_cambiar_de_modelo_guarda_lo_pendiente_en_el_anterior(panel, carpeta):
    elegir(panel, "a_luna.vrm")
    panel.sliders["pesoOjos"].setValue(20)
    elegir(panel, "b_vieja.vrm")
    assert json.loads((carpeta / "a_luna.lune.json").read_text("utf-8")) == {"pesoOjos": 0.2}
    assert not (carpeta / "b_vieja.lune.json").exists()
    assert panel.sliders["pesoOjos"].value() == 100                        # el de b_vieja


def test_modelo_sin_lookat_avisa_y_apaga_los_ojos(panel):
    elegir(panel, "c_pelada.vrm")
    assert not panel.aviso_ojos.isHidden()
    assert "no mueve los ojos" in panel.aviso_ojos.text()
    assert not panel.sliders["pesoOjos"].isEnabled()
    assert panel.sliders["pesoCabeza"].isEnabled() and panel.sliders["pesoTorso"].isEnabled()
    elegir(panel, "a_luna.vrm")
    assert panel.aviso_ojos.isHidden() and panel.sliders["pesoOjos"].isEnabled()
    elegir(panel, "b_vieja.vrm")                                            # VRM 0 con blendshapes de mirada
    assert panel.aviso_ojos.isHidden()


# ── Importar ─────────────────────────────────────────────────────────────────────

def test_importar(panel, carpeta, tmp_path):
    descargas = tmp_path / "descargas"; descargas.mkdir()
    nuevo = descargas / "nuevo.vrm"; nuevo.write_bytes(vrm1_sin_nada())
    panel._elegir_archivo = lambda: str(nuevo)
    assert panel.importar() == "nuevo.vrm"
    assert (carpeta / "nuevo.vrm").read_bytes() == nuevo.read_bytes()
    assert panel.modelo == "nuevo.vrm"
    assert panel.combo.findData("nuevo.vrm") >= 0
    assert panel.senales == [1]
    assert "Importado" in panel.estado.text()


def test_importar_cancelado_o_malo(panel, tmp_path):
    panel._elegir_archivo = lambda: ""
    assert panel.importar() == ""
    malo = tmp_path / "malo.vrm"; malo.write_bytes(b"basura")
    panel._elegir_archivo = lambda: str(malo)
    assert panel.importar() == ""
    assert "No pude importar" in panel.estado.text()
    foto = tmp_path / "foto.png"; foto.write_bytes(b"\x89PNG")
    panel._elegir_archivo = lambda: str(foto)
    assert panel.importar() == ""

    def roto():
        raise RuntimeError("sin diálogo")
    panel._elegir_archivo = roto
    assert panel.importar() == ""
    assert panel.senales == []
    assert panel.modelo == "b_vieja.vrm"


# ── Asignar al personaje activo ──────────────────────────────────────────────────

def test_asignar_y_quitar(panel, almacen):
    elegir(panel, "a_luna.vrm")
    assert panel.btn_asignar.isEnabled()
    panel.btn_asignar.click()
    assert aria(almacen)["vrm"] == "a_luna.vrm"
    assert panel.senales == [1]
    assert not panel.btn_asignar.isEnabled()                               # ya lo usa
    assert "Aria" in panel.ficha.text()                                     # «Lo usa: Lune, Aria»
    panel.btn_quitar.click()
    assert "vrm" not in aria(almacen)
    assert panel.senales == [1, 1]
    assert not panel.btn_quitar.isEnabled() and panel.btn_asignar.isEnabled()
    assert "por defecto" in panel.estado.text()


def test_asignar_sin_personaje_activo(qapp, carpeta, monkeypatch, almacen):
    from nucleo import personajes
    from ui.vrm_panel_nativo import VrmPanelNativo
    monkeypatch.setattr(personajes, "get_activo", lambda: {})
    p = VrmPanelNativo(None)
    assert p.asignar() is False and "No hay personaje activo" in p.estado.text()


# ── Estilo ───────────────────────────────────────────────────────────────────────

def test_usa_los_colores_del_tema(panel):
    from ui.theme import COLORS
    assert COLORS["accent"] in panel.btn_importar.styleSheet()
    assert COLORS["surface2"] in panel.combo.styleSheet()
    assert COLORS["accent"] in panel.sliders["pesoCabeza"].styleSheet()
    assert COLORS["warning"] in panel.aviso_ojos.styleSheet()
