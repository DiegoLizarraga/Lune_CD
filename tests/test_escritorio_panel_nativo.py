"""
Tests de ui/escritorio_panel_nativo.py: tema, modo juego, rendimiento, atajos y
menú radial en la interfaz nativa.

Offscreen, con un config de mentira (secciones en .config, save() que cuenta) y
dobles del gestor de atajos y de las apps abiertas. Se comprueba lo que queda
escrito y las señales `cambiado(seccion)`, no el texto de los widgets.
"""
import copy
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import tema  # noqa: E402
from nucleo.config import Config  # noqa: E402

DEF = Config.DEFAULT_CONFIG


class ConfigFalsa:
    def __init__(self, secciones=None):
        self.config = copy.deepcopy({k: DEF[k] for k in ("tema", "juego", "avatar", "sistema", "interfaz",
                                                         "atajos", "menu_radial", "menu")})
        for s, v in (secciones or {}).items():
            self.config.setdefault(s, {}).update(v)
        self.escrituras = 0

    def save(self):
        self.escrituras += 1


class AtajosFalsos:
    """Lo que el panel usa de GestorAtajosQt: capturando() y estado()."""

    def __init__(self, estado=None):
        self.capturas = []
        self._estado = estado or []

    def capturando(self, on, timeout_ms=15000):
        self.capturas.append(bool(on))

    def estado(self):
        return self._estado


@pytest.fixture
def hacer(qapp):
    creados = []

    def _hacer(cfg=None, **kw):
        from ui.escritorio_panel_nativo import PanelEscritorioNativo
        cfg = cfg if cfg is not None else ConfigFalsa()
        p = PanelEscritorioNativo(cfg, **kw)
        p.senales = []
        p.cambiado.connect(p.senales.append)
        creados.append(p)
        return p, cfg

    yield _hacer
    for p in creados:
        p._timer.stop()
        p._timer_captura.stop()
        p.deleteLater()


def test_arranca_con_lo_que_hay_en_config(hacer):
    p, cfg = hacer(ConfigFalsa({"tema": {"preset": "violeta", "saturacion": 1.4, "tenir_fondo": True},
                                "juego": {"apps": ["Game.EXE", "mal/../x", "game.exe"], "fps": 12},
                                "avatar": {"fps_max": 90}}))
    assert p.tema_ui() == tema.normalizar({"preset": "violeta", "saturacion": 1.4, "tenir_fondo": True})
    from ui.escritorio_panel_nativo import normalizar_app
    assert p.apps() == [normalizar_app("game.exe"), normalizar_app("x")], "normalizadas, sin repetir ni rutas"
    assert p.apps()[0] == "game.exe"
    assert p.spin_juego_fps.value() == 12 and p.spin_fps_max.value() == 90
    assert p.radial() == DEF["menu_radial"]["principal"]
    assert [i for i in p.filas_atajo] == [a["id"] for a in DEF["atajos"]["lista"]]
    assert p.combo_atajo("mostrar_lune") == "ctrl+alt+shift+l"
    assert not p.pendiente and cfg.escrituras == 0 and p.senales == []


def test_tema_se_guarda_una_vez_y_avisa(hacer):
    p, cfg = hacer()
    p.combo_preset.setCurrentIndex(p.combo_preset.findData("magenta_mate"))
    p.slider_sat.setValue(150)
    p.chk_pop.setChecked(True)
    assert p.pendiente and cfg.escrituras == 0
    assert p.guardar_ya() == ["tema"]
    assert cfg.escrituras == 1 and p.senales == ["tema"]
    assert cfg.config["tema"] == {"preset": "magenta_mate", "hue": round(tema.PRESETS["magenta_mate"] * 360, 2),
                                  "saturacion": 1.5, "tenir_pop": True, "tenir_fondo": False}
    assert "Reinicia" in p.aviso_tema.text(), "la ventana nativa cambia al reiniciar"
    # Mover el tono pasa a personalizado
    p.slider_tono.setValue(200)
    assert p.combo_preset.currentData() == tema.PERSONALIZADO
    p.guardar_ya()
    assert cfg.config["tema"]["preset"] == tema.PERSONALIZADO and cfg.config["tema"]["hue"] == 200
    # Restablecer: el cian de siempre, sin aviso de reinicio
    p.restablecer_tema()
    p.guardar_ya()
    assert cfg.config["tema"] == tema.DEFECTO
    assert p.senales == ["tema", "tema", "tema"] and "Reinicia" not in p.aviso_tema.text()


def test_la_escritura_espera_quieta(qapp, hacer):
    from PyQt6.QtTest import QTest
    p, cfg = hacer(retardo_ms=20)
    for v in (10, 20, 30, 40):
        p.slider_tono.setValue(v)
    p.chk_juego.setChecked(False)
    QTest.qWait(120)
    assert cfg.escrituras == 1 and p.senales == ["tema", "juego"]
    assert cfg.config["tema"]["hue"] == 40 and cfg.config["juego"]["activo"] is False


def test_modo_juego(hacer):
    abiertas = ["Discord.exe", "steam.exe", "juego.exe", "C:\\Games\\Elden Ring\\eldenring.exe", "<mal>"]
    p, cfg = hacer(apps_visibles=lambda: abiertas)
    p.combo_accion.setCurrentIndex(p.combo_accion.findData("fondo"))
    p.spin_juego_fps.setValue(20)
    p.chk_juego_opciones["incluir_videos"].setChecked(False)
    p.chk_juego_opciones["silenciar"].setChecked(False)
    assert p.anadir_app("Juego.EXE") and p.apps() == ["juego.exe"]
    assert not p.anadir_app("juego.exe"), "sin repetir"
    assert not p.anadir_app("rm -rf /; x"), "nombre no válido"
    assert not p.anadir_app("")
    assert p.apps_abiertas() == ["discord.exe", "eldenring.exe", "steam.exe"]
    assert p.anadir_app("C:\\Program Files\\Otro\\Otro.exe") and p.apps()[-1] == "otro.exe"
    p.lista_apps.setCurrentRow(0)
    assert p.quitar_app() and p.apps() == ["otro.exe"]
    p.guardar_ya()
    j = cfg.config["juego"]
    assert j["accion"] == "fondo" and j["fps"] == 20 and j["incluir_videos"] is False
    assert j["silenciar"] is False and j["apps"] == ["otro.exe"]
    assert p.senales == ["juego"] and cfg.escrituras == 1
    rota, _ = hacer(apps_visibles=lambda: 1 / 0)
    assert rota.apps_abiertas() == []


def test_rendimiento_va_a_sus_secciones(hacer):
    llamadas = []
    p, cfg = hacer(liberar_memoria=lambda: (llamadas.append(1) or (412.4, 188.9)))
    p.spin_fps_max.setValue(30)
    p.chk_encima.setChecked(False)
    p.chk_recorte.setChecked(True)
    p.chk_barra.setChecked(False)
    assert p.guardar_ya() == ["rendimiento"]
    assert cfg.config["avatar"]["fps_max"] == 30 and cfg.config["avatar"]["siempre_encima"] is False
    assert cfg.config["sistema"]["recorte_ram_auto"] is True
    assert cfg.config["interfaz"]["en_barra_tareas"] is False
    assert not p.btn_liberar.isHidden()
    p.liberar_memoria()
    assert llamadas == [1] and "412 MB → 189 MB" in p.estado_rendimiento.text()
    sin, _ = hacer()
    assert sin.btn_liberar.isHidden()
    rota, _ = hacer(liberar_memoria=lambda: 1 / 0)
    rota.liberar_memoria()
    assert "No pude" in rota.estado_rendimiento.text()


def test_atajos_valida_y_guarda_normalizado(hacer):
    p, cfg = hacer()
    assert p.cambiar_atajo("voz", "Shift + CTRL + alt + J")
    p.guardar_ya()
    lista = cfg.config["atajos"]["lista"]
    assert [a["id"] for a in lista] == [a["id"] for a in DEF["atajos"]["lista"]], "mismo orden, mismos ids"
    assert next(a for a in lista if a["id"] == "voz")["combo"] == "ctrl+alt+shift+j"
    assert p.senales == ["atajos"]
    # Errores: no se guardan y se enseñan
    for malo in ("F12", "l", "shift+a", "win+alt+r", "ctrl+altgr+x", "ctrl+alt+shift+xyz"):
        assert not p.cambiar_atajo("voz", malo), malo
        assert p.filas_atajo["voz"]["estado"].text()
    assert p.combo_atajo("voz") == "ctrl+alt+shift+j"
    # Duplicado con otro atajo
    assert not p.cambiar_atajo("voz", "ctrl+alt+shift+l")
    from ui.escritorio_panel_nativo import etiqueta
    assert etiqueta("mostrar_lune") in p.filas_atajo["voz"]["estado"].text()
    # Aviso de AltGr: se guarda y se avisa
    assert p.cambiar_atajo("dormir", "ctrl+alt+e")
    assert p.filas_atajo["dormir"]["estado"].text().startswith("Aviso:")
    # Vacío = sin atajo
    assert p.cambiar_atajo("llamada", "")
    p.guardar_ya()
    lista = {a["id"]: a["combo"] for a in cfg.config["atajos"]["lista"]}
    assert lista["dormir"] == "ctrl+alt+e" and lista["llamada"] == "" and lista["voz"] == "ctrl+alt+shift+j"
    p.chk_atajos_juego.setChecked(False)
    p.restablecer_atajos()
    p.guardar_ya()
    assert cfg.config["atajos"]["lista"] == DEF["atajos"]["lista"]
    assert cfg.config["atajos"]["pausar_en_juegos"] is False


def test_detectar_pausa_los_atajos_y_captura(hacer):
    from PyQt6.QtCore import Qt
    M = Qt.KeyboardModifier
    gestor = AtajosFalsos()
    p, cfg = hacer(atajos=gestor)
    assert p.detectar("comentar") and p.capturando == "comentar"
    assert gestor.capturas == [True], "los atajos globales se pausan mientras se detecta"
    assert p.capturar(Qt.Key.Key_Control, M.ControlModifier) is None, "solo el modificador: sigue esperando"
    assert p.capturando == "comentar"
    combo = p.capturar(Qt.Key.Key_U, M.ControlModifier | M.AltModifier | M.ShiftModifier)
    assert combo == "ctrl+alt+shift+u" and p.capturando is None
    assert gestor.capturas == [True, False]
    # Esc cancela y deja lo que había
    p.detectar("fantasma")
    assert p.capturar(Qt.Key.Key_Escape, M.NoModifier) is None
    assert p.capturando is None and p.combo_atajo("fantasma") == "ctrl+alt+shift+g"
    assert p.filas_atajo["fantasma"]["edit"].text() == "ctrl+alt+shift+g"
    # Una combinación inválida detectada no se guarda
    p.detectar("fantasma")
    assert p.capturar(Qt.Key.Key_F12, M.NoModifier) is None
    assert p.combo_atajo("fantasma") == "ctrl+alt+shift+g"
    # Con Shift, «!» es la tecla 1 (tecla virtual 0x31)
    p.detectar("dormir")
    assert p.capturar(Qt.Key.Key_Exclam, M.ControlModifier | M.ShiftModifier, 0x31) == "ctrl+shift+1"
    p.guardar_ya()
    lista = {a["id"]: a["combo"] for a in cfg.config["atajos"]["lista"]}
    assert lista["comentar"] == "ctrl+alt+shift+u" and lista["dormir"] == "ctrl+shift+1"
    assert gestor.capturas.count(True) == gestor.capturas.count(False)


def test_detectar_se_cancela_solo_y_con_teclas_de_verdad(qapp, hacer):
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtTest import QTest
    gestor = AtajosFalsos()
    p, _ = hacer(atajos=gestor)
    p._timer_captura.setInterval(20)
    p.detectar("voz")
    QTest.qWait(80)
    assert p.capturando is None and gestor.capturas == [True, False], "a los 15 s (aquí 20 ms) se reanudan"
    # Un QKeyEvent de verdad al campo en captura
    p.detectar("voz")
    edit = p.filas_atajo["voz"]["edit"]
    M = Qt.KeyboardModifier
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_P, M.ControlModifier | M.AltModifier | M.ShiftModifier)
    assert p.eventFilter(edit, ev) is True
    assert p.combo_atajo("voz") == "ctrl+alt+shift+p" and p.capturando is None


def test_estado_del_gestor_y_atajos_no_disponibles(hacer):
    gestor = AtajosFalsos([{"id": "pantalla_grande", "disponible": False},
                           {"id": "llamada", "disponible": True, "error": "Otra aplicación ya usa Ctrl+Alt+Shift+K."}])
    p, _ = hacer(atajos=gestor)
    fila = p.filas_atajo["pantalla_grande"]
    assert not fila["edit"].isEnabled() and not fila["boton"].isEnabled()
    assert "Otra aplicación" in p.filas_atajo["llamada"]["estado"].text()
    assert p.filas_atajo["voz"]["edit"].isEnabled()


def test_menu_radial(hacer):
    p, cfg = hacer()
    assert len(p.radial()) == 10
    assert not p.anadir_radial("fantasma"), "como mucho 10"
    assert not p.btn_radial_anadir.isEnabled()
    p.lista_radial.setCurrentRow(9)
    assert p.quitar_radial()
    assert p.anadir_radial("fantasma") and p.radial()[-1] == "fantasma"
    assert not p.anadir_radial("chat"), "sin repetir"
    assert not p.anadir_radial("no_existe")
    p.lista_radial.setCurrentRow(0)
    assert p.mover_radial(1) and p.radial()[:2] == ["chat", "ajustes"]
    assert not p.mover_radial(-5)
    p.chk_menu_sonidos.setChecked(False)
    p.slider_menu_vol.setValue(35)
    assert p.guardar_ya() == ["radial"]
    assert cfg.config["menu_radial"]["principal"] == p.radial()
    assert cfg.config["menu_radial"]["secundario"] == DEF["menu_radial"]["secundario"], "el del clic central no se toca"
    assert cfg.config["menu"] == {"sonidos": False, "volumen": 0.35}


def test_varias_secciones_una_escritura_y_senales_en_orden(hacer):
    p, cfg = hacer()
    p.lista_radial.setCurrentRow(0)
    p.quitar_radial()
    p.chk_barra.setChecked(False)
    p.chk_juego.setChecked(False)
    p.chk_fondo.setChecked(True)
    p.cambiar_atajo("voz", "ctrl+alt+shift+j")
    assert p.guardar_ya() == ["tema", "juego", "rendimiento", "atajos", "radial"]
    assert p.senales == ["tema", "juego", "rendimiento", "atajos", "radial"]
    assert cfg.escrituras == 1
    assert p.guardar_ya() == [] and cfg.escrituras == 1


def test_recargar_no_escribe_y_trae_lo_nuevo(hacer):
    p, cfg = hacer()
    cfg.config["tema"] = {"preset": "ambar", "hue": 0, "saturacion": 0.5}
    cfg.config["menu_radial"]["principal"] = ["chat", "chat", "no_existe", "voz"]
    cfg.config["atajos"]["lista"] = [{"id": "mostrar_lune", "combo": "Ctrl+Shift+Alt+F2"}]
    p.recargar()
    assert p.tema_ui()["preset"] == "ambar" and p.tema_ui()["saturacion"] == 0.5
    assert p.radial() == ["chat", "voz"]
    assert list(p.filas_atajo) == ["mostrar_lune"] and p.combo_atajo("mostrar_lune") == "ctrl+alt+shift+f2"
    assert not p.pendiente and cfg.escrituras == 0 and p.senales == []


def test_con_config_real_en_carpeta_temporal(hacer, tmp_path):
    ruta = tmp_path / "config.json"
    cfg = Config(str(ruta))
    p, _ = hacer(cfg)
    p.combo_preset.setCurrentIndex(p.combo_preset.findData("rojo_neon"))
    p.spin_fps_max.setValue(48)
    p.cambiar_atajo("mascota", "ctrl+alt+shift+n")
    p.guardar_ya()
    disco = json.loads(ruta.read_text(encoding="utf-8"))
    assert disco["tema"]["preset"] == "rojo_neon" and disco["avatar"]["fps_max"] == 48
    assert {a["id"]: a["combo"] for a in disco["atajos"]["lista"]}["mascota"] == "ctrl+alt+shift+n"
    assert disco["voz"] == DEF["voz"], "lo demás no se toca"


def test_combo_de_tecla():
    from PyQt6.QtCore import Qt
    from ui.escritorio_panel_nativo import combo_de_tecla
    M = Qt.KeyboardModifier
    todos = M.ControlModifier | M.AltModifier | M.ShiftModifier
    assert combo_de_tecla(Qt.Key.Key_L, todos) == "ctrl+alt+shift+l"
    assert combo_de_tecla(Qt.Key.Key_Space, todos) == "ctrl+alt+shift+space"
    assert combo_de_tecla(Qt.Key.Key_Period, todos) == "ctrl+alt+shift+period"
    assert combo_de_tecla(Qt.Key.Key_F5, M.NoModifier) == "f5"
    assert combo_de_tecla(Qt.Key.Key_5, M.ControlModifier | M.KeypadModifier) == "ctrl+numpad5"
    assert combo_de_tecla(Qt.Key.Key_Up, M.MetaModifier | M.ControlModifier) == "ctrl+win+up"
    assert combo_de_tecla(Qt.Key.Key_Shift, M.ShiftModifier) is None
    assert combo_de_tecla(Qt.Key.Key_AltGr, M.NoModifier) is None
    assert combo_de_tecla(Qt.Key.Key_Exclam, M.ShiftModifier | M.ControlModifier, 0x31) == "ctrl+shift+1"
    assert combo_de_tecla(Qt.Key.Key_Exclam, M.ShiftModifier, 0) is None
    assert combo_de_tecla(int(Qt.Key.Key_A), int(M.ControlModifier.value)) == "ctrl+a"


def test_normalizar_app_y_etiquetas():
    from ui.escritorio_panel_nativo import etiqueta, normalizar_app, validar_radial
    assert normalizar_app("  Game.EXE ") == "game.exe"
    assert normalizar_app('"C:\\Juegos\\Elden Ring\\ELDENRING.exe"') == "eldenring.exe"
    assert normalizar_app("a" * 81) is None and normalizar_app("x;y") is None and normalizar_app(None) is None
    assert etiqueta("mostrar_lune") and etiqueta("id_raro") == "id_raro"
    assert validar_radial(["chat", "chat", 3, "nada", "voz"] + ["ajustes"] * 3) == ["chat", "voz", "ajustes"]
    assert len(validar_radial(DEF["menu_radial"]["principal"] + ["fantasma"])) == 10
