"""
Tests de ui/atajos_qt.py (GestorAtajosQt) con un GestorAtajos falso: solo se
registran las acciones con handler, la pausa del modo juego deja solo
mostrar_lune, «Detectar» los quita todos y vuelven solos, cambiar guarda la
combinación normalizada (o vuelve a la anterior si otra app la tiene) y la
pulsación llega por señal al hilo de Qt.
"""
import copy
import json
import os
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PyQt6.QtWidgets")

from nucleo.config import Config  # noqa: E402
from servicios.atajos_globales import normalizar  # noqa: E402
from ui.atajos_qt import GestorAtajosQt  # noqa: E402


class GestorFalso:
    """Lo que GestorAtajosQt usa de servicios.atajos_globales.GestorAtajos."""

    def __init__(self):
        self._on_atajo = None
        self.activos = {}                   # id → combo normalizado (lo que tendría Windows)
        self.ocupados = set()               # combos que «otra app» ya tiene
        self.vivo = False
        self.diario = []

    def activo(self):
        return self.vivo

    def iniciar(self):
        self.vivo = True
        self.diario.append("iniciar")
        return True

    def detener(self):
        self.vivo = False
        self.diario.append("detener")

    def registrar(self, id_, combo):
        n = normalizar(combo)
        if n in self.ocupados:
            return f"{combo} ya lo usa otra aplicación (o Windows). Elige otro atajo."
        for otro, c in self.activos.items():
            if otro != id_ and c == n:
                return f"{combo} ya lo usa «{otro}»."
        self.activos[id_] = n
        return None

    def quitar(self, id_):
        self.activos.pop(id_, None)

    def quitar_todos(self):
        self.activos.clear()
        self.diario.append("quitar_todos")

    def pulsar(self, id_):
        self._on_atajo(id_)


class ConfigFalsa:
    def __init__(self):
        self.d = copy.deepcopy(Config.DEFAULT_CONFIG)
        self.escrituras = 0

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = copy.deepcopy(v)
        self.escrituras += 1


# Sin handler todavía: pantalla_grande y baile_pausa (cortes 5 y 6).
CON_HANDLER = {"mostrar_lune", "asistente", "menu_radial", "comentar", "voz", "llamada", "fantasma", "dormir"}


@pytest.fixture
def at(qapp):
    cfg = ConfigFalsa()
    g = GestorFalso()
    disp = set(CON_HANDLER)
    q = GestorAtajosQt(cfg, disponible=lambda i: i in disp, gestor=g)
    q.cfg, q.g, q.disp = cfg, g, disp
    cambios = []
    q.cambio.connect(cambios.append)
    q.cambios = cambios
    yield q
    q.detener()


def combos(cfg):
    return {e["id"]: e["combo"] for e in cfg.get("atajos", "lista")}


def test_solo_se_registran_las_acciones_con_handler(at):
    at.iniciar()
    assert at.g.vivo
    assert set(at.g.activos) == CON_HANDLER
    assert at.g.activos["mostrar_lune"] == "ctrl+alt+shift+l"
    e = {x["id"]: x for x in at.estado()}
    assert e["pantalla_grande"]["disponible"] is False and e["pantalla_grande"]["registrado"] is False
    assert e["mostrar_lune"]["texto"] == "Ctrl+Alt+Shift+L" and e["mostrar_lune"]["siempre"]
    assert json.loads(at.cambios[-1])[0]["id"] == "mostrar_lune"


def test_sin_activo_no_registra_nada(at):
    at.cfg.d["atajos"]["activo"] = False
    at.iniciar()
    assert at.g.activos == {} and not at.g.vivo
    at.activar(True)
    assert at.cfg.d["atajos"]["activo"] is True and set(at.g.activos) == CON_HANDLER
    at.activar(False)
    assert at.g.activos == {} and at.cfg.d["atajos"]["activo"] is False


def test_pausa_de_juego_deja_solo_mostrar_lune(at):
    at.iniciar()
    at.set_pausa(True)
    assert set(at.g.activos) == {"mostrar_lune"}
    at.set_pausa(False)
    assert set(at.g.activos) == CON_HANDLER
    at.cfg.d["atajos"]["pausar_en_juegos"] = False
    at.set_pausa(True)
    assert set(at.g.activos) == CON_HANDLER


def test_capturando_los_quita_todos_y_vuelven_solos(at):
    from PyQt6.QtTest import QTest
    at.iniciar()
    at.capturando(True)
    assert at.g.activos == {} and at.en_captura
    at.capturando(False)
    assert set(at.g.activos) == CON_HANDLER
    at.capturando(True, timeout_ms=500)
    QTest.qWait(700)
    assert not at.en_captura and set(at.g.activos) == CON_HANDLER


def test_cambiar_guarda_normalizado(at):
    at.iniciar()
    assert at.cambiar("voz", "Shift + CTRL + alt + J") is None
    assert combos(at.cfg)["voz"] == "ctrl+alt+shift+j"
    assert at.g.activos["voz"] == "ctrl+alt+shift+j"
    assert json.loads(at.cambios[-1])                                   # avisó a la web
    # sin atajo
    assert at.cambiar("voz", "") is None
    assert combos(at.cfg)["voz"] == "" and "voz" not in at.g.activos
    # acción que no tenía entrada en la lista
    at.disp.add("liberar_memoria")
    assert at.cambiar("liberar_memoria", "ctrl+alt+shift+r") is None
    assert combos(at.cfg)["liberar_memoria"] == "ctrl+alt+shift+r" and "liberar_memoria" in at.g.activos


def test_cambiar_rechaza_sin_tocar_la_config(at):
    at.iniciar()
    antes = copy.deepcopy(at.cfg.d["atajos"]["lista"])
    escrituras = at.cfg.escrituras
    assert "F12" in at.cambiar("voz", "f12")
    assert at.cambiar("voz", "ctrl+alt+shift+l")                        # ya es de mostrar_lune
    assert at.cambiar("voz", "q")                                       # sin modificador
    assert at.cambiar("tema", "ctrl+alt+shift+t")                       # «tema» no admite atajo
    assert at.cambiar("inventada", "ctrl+alt+shift+t")
    assert at.cfg.d["atajos"]["lista"] == antes and at.cfg.escrituras == escrituras


def test_cambiar_a_un_combo_de_otra_app_vuelve_al_anterior(at):
    at.iniciar()
    at.g.ocupados.add("ctrl+alt+shift+x")
    err = at.cambiar("voz", "ctrl+alt+shift+x")
    assert err and "otra aplicación" in err
    assert combos(at.cfg)["voz"] == "ctrl+alt+shift+v"
    assert at.g.activos["voz"] == "ctrl+alt+shift+v"


def test_aviso_de_altgr_no_impide(at):
    at.iniciar()
    assert at.cambiar("voz", "ctrl+alt+e") is None
    e = next(x for x in at.estado() if x["id"] == "voz")
    assert e["aviso"] and "AltGr" in e["aviso"] and e["error"] is None


def test_validar(at):
    at.iniciar()
    v = at.validar("alt + ctrl + shift + v")
    assert v["ok"] and v["combo"] == "ctrl+alt+shift+v" and v["texto"] == "Ctrl+Alt+Shift+V"
    assert v["conflicto"] == "voz"
    assert at.validar("ctrl+alt+shift+v", id_="voz")["conflicto"] == ""
    mal = at.validar("win+alt+g")
    assert not mal["ok"] and "Win+Alt" in mal["error"]


def test_error_de_otra_app_al_arrancar_se_ve_en_estado(at):
    at.g.ocupados.add("ctrl+alt+shift+m")
    at.iniciar()
    e = next(x for x in at.estado() if x["id"] == "asistente")
    assert e["error"] and not e["registrado"]


def test_pulsacion_llega_en_el_hilo_de_qt(at, qapp):
    at.iniciar()
    hilo_qt = threading.get_ident()
    recibidos = []
    at.accion.connect(lambda i: recibidos.append((i, threading.get_ident())))
    t = threading.Thread(target=at.g.pulsar, args=("voz",))
    t.start()
    t.join()
    assert recibidos == []                                  # en cola
    qapp.processEvents()
    assert recibidos == [("voz", hilo_qt)]
    # un atajo quitado (pausa) que llega tarde no dispara
    at.set_pausa(True)
    at.g.pulsar("voz")
    at.g.pulsar("mostrar_lune")
    qapp.processEvents()
    assert [r[0] for r in recibidos] == ["voz", "mostrar_lune"]


def test_restablecer_y_recargar(at):
    at.iniciar()
    at.cambiar("voz", "ctrl+alt+shift+j")
    estado = at.restablecer()
    assert combos(at.cfg)["voz"] == "ctrl+alt+shift+v"
    assert any(e["id"] == "voz" and e["combo"] == "ctrl+alt+shift+v" for e in estado)
    at.cfg.d["atajos"]["lista"] = [{"id": "voz", "combo": "ctrl+alt+shift+n"}, {"id": "voz", "combo": "x"},
                                   {"id": "nada", "combo": "ctrl+alt+shift+q"}, "basura"]
    at.recargar()
    assert at.g.activos == {"voz": "ctrl+alt+shift+n"}


def test_detener_suelta_todo(at):
    at.iniciar()
    at.detener()
    assert at.g.activos == {} and "quitar_todos" in at.g.diario and at.g.diario[-1] == "detener"
    at.g.pulsar("voz")                                      # ya no entrega nada
    recibidos = []
    at.accion.connect(recibidos.append)
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
    assert recibidos == []


def test_con_el_gestor_real_sin_windows_no_revienta(qapp, monkeypatch):
    # GestorAtajos real con user32/kernel32 ausentes fuera de Windows: iniciar da False.
    from servicios import atajos_globales
    monkeypatch.setattr(atajos_globales.sys, "platform", "linux")
    q = GestorAtajosQt(ConfigFalsa(), disponible=lambda i: True)
    q.iniciar()
    assert isinstance(q.estado(), list)
    q.detener()
