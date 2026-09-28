"""
ui/puente_escenario.py (objeto `escenario` del QWebChannel, window.luneEscenario), cortes 9 y 10.

Con dobles de ControlMMD y ControlMinecraft (QObject con sus señales), un nucleo.datos falso
(minecraft() y guardar_minecraft()) y la Config de verdad en una carpeta temporal:
  · validación estricta de cada ranura (JSON ≤ 16 KB, claves conocidas, tipos, enums y rangos;
    ids de la biblioteca de 12 hex; NUNCA una ruta de la página: el latest.log solo puede ser
    uno de los detectados) y rechazo sin tocar nada;
  · sin servicios: estado por defecto y la config (baile.*, minecraft.* y datos.json) se lee y
    se guarda igual;
  · servicios tardíos (ServiciosCorte4.escenario, ServiciosEscenario o el escritorio), señales
    reemitidas normalizadas (el chat de Minecraft solo como texto) y soltarse al desmontar;
  · con las clases de verdad de los agentes C y D (biblioteca temporal, bot falso).
En Python nunca se crea un QWebEnginePage: el canal es un doble con registerObject.
"""
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from nucleo.config import Config  # noqa: E402
from ui import puente_escenario as pe  # noqa: E402
from ui.puente_escenario import PuenteEscenario, registrar_puente_escenario  # noqa: E402

ID = "0123456789ab"
ID2 = "fedcba987654"


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PyQt6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def cfg(tmp_path):
    return Config(str(tmp_path / "config.json"))


def cap(senal) -> List[str]:
    out: List[str] = []
    senal.connect(out.append)
    return out


def J(s):
    return json.loads(s)


class CanalFalso(QObject):
    def __init__(self):
        super().__init__()
        self.registrados, self.quitados = {}, []

    def registerObject(self, nombre, obj):
        self.registrados[nombre] = obj

    def deregisterObject(self, obj):
        self.quitados.append(obj)


class MMDFalso(QObject):
    estado_cambio = pyqtSignal(str)
    biblioteca_cambio = pyqtSignal(str)
    importado = pyqtSignal(str)
    vista_pedida = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas = []
        self.e = {"fase": "sonando", "id": ID, "titulo": "Senbonzakura\x07", "autor": "Kurousa-P", "t": 12.345,
                  "total": 240.0, "modo": "vrm", "al_terminar": "siguiente", "volumen": 0.4, "en_el_sitio": False,
                  "error": "", "pausado": False, "modo_mascota": "vrm", "sin_esqueleto": False, "raro": "<script>"}
        self.bailes = [
            {"id": ID, "titulo": "Senbonzakura", "tipo": "vmd", "autor_cancion": "Kurousa-P", "autor_mmd": "x",
             "duracion": 240.04, "audio": True, "favorito": True, "desactivado": False, "problema": "",
             "offset_ms": 40, "brazo_a_grados": 35.0, "en_el_sitio": None, "bpm": None, "ruta": "C:/secreto"},
            {"id": "../../etc", "titulo": "malo"},
            {"id": ID2, "titulo": "\u202eOtro\x00", "tipo": "exe", "duracion": float("inf"), "offset_ms": 9999},
        ]

    def estado(self):
        return dict(self.e)

    def lista(self, texto=""):
        self.llamadas.append(("lista", texto))
        return self.bailes

    def refrescar(self):
        self.llamadas.append(("refrescar",))

    def reproducir(self, id_=None, *, origen="usuario"):
        self.llamadas.append(("reproducir", id_, origen))
        return True, "¡A bailar «Senbonzakura»!"

    def pausa(self, on=None):
        self.llamadas.append(("pausa", on))
        return True

    def parar(self):
        self.llamadas.append(("parar",))
        return True

    def siguiente(self):
        self.llamadas.append(("siguiente",))
        return False, "No hay más bailes."

    def anterior(self):
        self.llamadas.append(("anterior",))
        return True, "¡A bailar «Otro»!"

    def volumen(self, v):
        self.llamadas.append(("volumen", v))

    def set_al_terminar(self, m):
        self.llamadas.append(("al_terminar", m))
        return True

    def set_en_el_sitio(self, on):
        self.llamadas.append(("en_el_sitio", on))

    def guardar_meta(self, id_, cambios):
        self.llamadas.append(("meta", id_, cambios))
        return True, "Guardado."

    def favorito(self, id_, on):
        self.llamadas.append(("favorito", id_, on))
        return True

    def desactivar(self, id_, on):
        self.llamadas.append(("desactivar", id_, on))
        return True

    def importar_dialogo(self, parent=None):
        self.llamadas.append(("importar", parent))

    def quitar(self, id_):
        self.llamadas.append(("quitar", id_))
        return True, "Lo moví a bailes/.quitados."

    def abrir_carpeta(self):
        self.llamadas.append(("carpeta",))
        return True


class MCFalso(QObject):
    estado_cambio = pyqtSignal(str)
    evento = pyqtSignal(str)
    chat = pyqtSignal(str)
    log_bot = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas = []
        self.instalando = False

    def estado(self):
        return {"reaccionar": True, "log": {"ruta": "C:/mc/logs/latest.log", "activo": True, "yo": "Diego_01"},
                "bot": {"instalado": True, "instalando": self.instalando, "conectando": False, "conectado": True,
                        "servidor": "localhost:25565", "nick": "Lune", "vida": 18, "hambre": 99, "dia": True,
                        "lluvia": "sí", "error": ""},
                "requisitos": {"node": "v24.19.0", "node_ok": True, "npm": True}, "juego": False, "pensando": True}

    def recargar_config(self):
        self.llamadas.append(("recargar",))

    def instalar_bot(self):
        self.llamadas.append(("instalar",))

    def conectar_bot(self):
        self.llamadas.append(("conectar",))
        return True, "Conectando el bot a localhost:25565 como Lune…"

    def desconectar_bot(self):
        self.llamadas.append(("desconectar",))
        return True

    def orden(self, texto, *, origen="usuario"):
        self.llamadas.append(("orden", texto, origen))
        return True, "Se lo he mandado al bot."

    def decir(self, texto):
        self.llamadas.append(("decir", texto))
        return True, "Dicho."

    def eventos_recientes(self, n=50):
        return [{"tipo": "muerte", "texto": "¡Otra vez el creeper!", "estado": "sad", "fuente": "log", "t": 1.5,
                 "entregado": True},
                {"tipo": "<img>", "texto": "x"}]


class DatosFalsos:
    def __init__(self):
        self.mc = {"host": "localhost", "port": 25565, "version": "", "usuario": "", "dueno": "Diego_01",
                   "pensar_cada_s": 45, "defender": True, "solo_dueno": True, "estilo_frases": "personaje",
                   "visor": False, "clave_secreta": "sk-xxx"}
        self.guardados = []

    def minecraft(self):
        return dict(self.mc)

    def guardar_minecraft(self, cambios):
        self.guardados.append(dict(cambios))
        if "port" in cambios and not 1 <= cambios["port"] <= 65535:
            raise ValueError("El puerto tiene que estar entre 1 y 65535.")
        self.mc.update(cambios)
        return dict(self.mc)


def puente(cfg, *, mmd=None, mc=None, datos=None, rutas=None, diferir=None, ventana=None):
    p = PuenteEscenario(cfg, datos=datos or DatosFalsos(), rutas_log=rutas or (lambda: []),
                        diferir=diferir or (lambda f: f()), ventana=ventana)
    if mmd is not None or mc is not None:
        p.enlazar(SimpleNamespace(mmd=mmd, minecraft=mc))
    return p


# ── Registro y ciclo de vida ─────────────────────────────────────────────────

def test_registrar_antes_de_la_pagina_y_cerrar(cfg):
    canal = CanalFalso()
    p = registrar_puente_escenario(canal, cfg, datos=DatosFalsos())
    assert canal.registrados == {"escenario": p} and p.parent() is canal
    assert p.mmd is None and p.minecraft is None
    p.cerrar()
    p.cerrar()
    assert canal.quitados == [p]


def test_sin_servicios_estado_por_defecto_y_config(cfg):
    p = puente(cfg)
    assert J(p.bailes_lista("")) == {"bailes": [], "servicio": False}
    e = J(p.mmd_estado_json())
    assert e["servicio"] is False and e["fase"] == "parado" and e["id"] == ""
    assert (e["al_terminar"], e["volumen"], e["en_el_sitio"]) == ("parar", 0.25, True)
    r = J(p.mmd_reproducir(ID))
    assert r["ok"] is False and "app" in r["texto"]
    assert J(p.mmd_pausa())["ok"] is False and J(p.mmd_parar())["ok"] is False
    assert p.bailes_importar() is False and p.bailes_abrir_carpeta() is False and p.bailes_refrescar() is False
    # lo que es solo config se guarda igual
    r = J(p.mmd_config_guardar(json.dumps({"volumen": 0.6, "al_terminar": "aleatorio", "en_el_sitio": False})))
    assert r["ok"] and (r["estado"]["volumen"], r["estado"]["al_terminar"], r["estado"]["en_el_sitio"]) == (0.6, "aleatorio", False)
    # (en memoria: hasta que la integración ponga baile.al_terminar en DEFAULT_CONFIG, recargar la poda)
    assert cfg.get("baile", "al_terminar") == "aleatorio" and cfg.get("baile", "volumen") == 0.6
    assert Config(cfg.config_path).get("baile", "volumen") == 0.6
    m = J(p.mc_estado_json())
    assert m["servicio"] is False and m["reaccionar"] is False and m["bot"]["conectado"] is False
    c = J(p.mc_config())
    assert c["bot"]["dueno"] == "Diego_01" and "visor" not in c["bot"] and "clave_secreta" not in json.dumps(c)
    assert c["config"] == pe.CONFIG_MC_DEFECTO
    r = J(p.mc_config_guardar(json.dumps({"reaccionar": True, "voz_reacciones": True})))
    assert r["ok"] and r["config"]["config"]["reaccionar"] is True and cfg.get("minecraft", "voz_reacciones") is True
    assert J(p.mc_bot_conectar())["ok"] is False and p.mc_bot_desconectar() is False
    assert J(p.mc_bot_instalar())["ok"] is False and J(p.mc_orden("sígueme"))["ok"] is False
    assert J(p.mc_eventos()) == []


# ── Bailes: validación ───────────────────────────────────────────────────────

@pytest.mark.parametrize("malo", ["../x", "ABCDEF012345", "0123456789a", "0123456789abc", "C:\\bailes\\a.vmd",
                                  "/bailes/a.vmd", " 0123456789ab"])
def test_reproducir_solo_ids_de_la_biblioteca(cfg, malo):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    r = J(p.mmd_reproducir(malo))
    assert r["ok"] is False and r["texto"] == "Ese baile no existe."
    assert not [x for x in m.llamadas if x[0] == "reproducir"]
    assert J(p.baile_quitar(malo))["ok"] is False and p.baile_favorito(malo, True) is False
    assert J(p.baile_meta_guardar(malo, '{"offset_ms": 10}'))["ok"] is False
    assert not [x for x in m.llamadas if x[0] in ("quitar", "favorito", "meta")]


def test_ranuras_de_bailes_con_servicio(cfg):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    r = J(p.mmd_reproducir(ID))
    assert r["ok"] and r["texto"].startswith("¡A bailar") and m.llamadas[-1] == ("reproducir", ID, "usuario")
    assert J(p.mmd_reproducir(""))["ok"] and m.llamadas[-1] == ("reproducir", None, "usuario"), "«» = seguir"
    assert J(p.mmd_pausa())["ok"] and m.llamadas[-1] == ("pausa", None)
    assert J(p.mmd_parar())["ok"] and m.llamadas[-1] == ("parar",)
    s = J(p.mmd_siguiente())
    assert s["ok"] is False and s["texto"] == "No hay más bailes."
    assert J(p.mmd_anterior())["ok"] is True
    assert p.baile_favorito(ID, True) and m.llamadas[-1] == ("favorito", ID, True)
    assert p.baile_desactivar(ID, False) and m.llamadas[-1] == ("desactivar", ID, False)
    assert p.baile_favorito(ID, "sí") is False                              # bool estricto
    assert J(p.baile_quitar(ID))["texto"].startswith("Lo moví") and m.llamadas[-1] == ("quitar", ID)
    assert p.bailes_abrir_carpeta() and p.bailes_refrescar() and m.llamadas[-1] == ("refrescar",)
    # la búsqueda se recorta a 60 y se limpia
    p.bailes_lista("senbon\x00" + "z" * 200)
    assert m.llamadas[-1] == ("lista", "senbon" + "z" * 54)


def test_la_lista_sale_con_lista_blanca_de_campos(cfg):
    p = puente(cfg, mmd=MMDFalso())
    r = J(p.bailes_lista(""))
    assert r["servicio"] is True and [b["id"] for b in r["bailes"]] == [ID, ID2]
    b0, b1 = r["bailes"]
    assert "ruta" not in b0 and b0["duracion"] == 240.0 and b0["favorito"] is True and b0["en_el_sitio"] is None
    assert b1["titulo"] == "Otro" and b1["tipo"] == "" and b1["duracion"] is None and b1["offset_ms"] == 0


@pytest.mark.parametrize("payload", [
    "", "no es json", "[]", '{"volumen": 2}', '{"volumen": "0.5"}', '{"volumen": NaN}', '{"al_terminar": "bucle"}',
    '{"en_el_sitio": 1}', '{"otra": true}', json.dumps({"volumen": 0.5, "x": "a" * 20000}),
])
def test_config_de_bailes_rechaza_sin_tocar_nada(cfg, payload):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    antes = json.dumps(cfg.config, sort_keys=True)
    r = J(p.mmd_config_guardar(payload))
    assert r["ok"] is False and r["error"]
    assert m.llamadas == [] and json.dumps(cfg.config, sort_keys=True) == antes


def test_config_de_bailes_va_al_controlador(cfg):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    estados = cap(p.mmd_estado)
    J(p.mmd_config_guardar(json.dumps({"volumen": 0.123456, "al_terminar": "repetir", "en_el_sitio": True})))
    assert ("volumen", 0.123) in m.llamadas and ("al_terminar", "repetir") in m.llamadas
    assert ("en_el_sitio", True) in m.llamadas and estados
    # el doble no guarda en la config: el puente lo guarda él (un controlador viejo)
    assert cfg.get("baile", "al_terminar") == "repetir"


@pytest.mark.parametrize("payload, texto", [
    ('{"offset_ms": 600}', "sincronía"), ('{"offset_ms": 12.5}', "sincronía"), ('{"offset_ms": "10"}', "sincronía"),
    ('{"brazo_a_grados": 50}', "brazos"), ('{"en_el_sitio": "si"}', "sitio"), ('{"bpm": 300}', "pulso"),
    ('{"titulo": 3}', "texto corto"), ('{"ruta": "C:/x"}', "no válidos"), ("{}", "no válidos"),
])
def test_meta_del_baile_valida(cfg, payload, texto):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    r = J(p.baile_meta_guardar(ID, payload))
    assert r["ok"] is False and texto in r["texto"]
    assert m.llamadas == []


def test_meta_del_baile_limpia_y_guarda(cfg):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    r = J(p.baile_meta_guardar(ID, json.dumps({"titulo": "  Senbon\x07zakura\u202e ", "autor_mmd": "a" * 120,
                                               "offset_ms": -120, "brazo_a_grados": 30.04, "en_el_sitio": None,
                                               "bpm": None})))
    assert r == {"ok": True, "texto": "Guardado."}
    _, id_, cambios = m.llamadas[-1]
    assert id_ == ID and cambios == {"titulo": "Senbonzakura", "autor_mmd": "a" * 80, "offset_ms": -120,
                                     "brazo_a_grados": 30.0, "en_el_sitio": None, "bpm": None}


def test_importar_abre_el_dialogo_diferido_y_uno_a_la_vez(cfg):
    m = MMDFalso()
    pendientes = []
    ventana = object()
    p = puente(cfg, mmd=m, diferir=pendientes.append, ventana=ventana)
    assert p.bailes_importar() is True
    assert p.bailes_importar() is False, "ya hay un diálogo abierto"
    assert not [x for x in m.llamadas if x[0] == "importar"]
    pendientes.pop()()
    assert m.llamadas[-1] == ("importar", ventana)
    assert p.bailes_importar() is True                    # cerrado el diálogo, se puede otra vez
    p2 = puente(cfg, mmd=MMDFalso(), ventana=lambda: "la ventana")
    p2.bailes_importar()
    assert p2.mmd.llamadas[-1] == ("importar", "la ventana")


def test_importar_diferido_no_se_abre_si_el_puente_se_borra_antes(cfg):
    """Sin `diferir` inyectado va un QTimer HIJO del puente (no singleShot con un cierre sobre
    él): si el puente se borra antes de la vuelta del bucle (Salir, cambio de interfaz), el
    diálogo modal ya no se abre sobre una interfaz desmontada."""
    from PyQt6 import sip
    from PyQt6.QtWidgets import QApplication
    m = MMDFalso()
    p = PuenteEscenario(cfg, datos=DatosFalsos(), rutas_log=lambda: [], ventana="v")
    p.enlazar(SimpleNamespace(mmd=m, minecraft=None))
    assert p.bailes_importar() is True
    sip.delete(p)
    for _ in range(3):
        QApplication.processEvents()
    assert not [x for x in m.llamadas if x[0] == "importar"]
    p2 = PuenteEscenario(cfg, datos=DatosFalsos(), rutas_log=lambda: [], ventana="v")
    p2.enlazar(SimpleNamespace(mmd=m, minecraft=None))
    assert p2.bailes_importar() is True
    for _ in range(3):
        QApplication.processEvents()
    assert m.llamadas[-1] == ("importar", "v") and p2.bailes_importar() is True
    p2.cerrar()


# ── Bailes: señales ───────────────────────────────────────────────────────────

def test_senales_de_bailes_normalizadas(cfg):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    est, bail, imp, vis = cap(p.mmd_estado), cap(p.bailes_cambio), cap(p.mmd_importado), cap(p.vista_pedida)
    m.e.update(fase="bailoteo", id="../x", modo_mascota="animado", t=-3, total=1e9)
    m.estado_cambio.emit("{}")
    e = J(est[-1])
    assert e["fase"] == "parado" and e["id"] == "" and e["sin_esqueleto"] is True and e["modo_mascota"] == "animado"
    assert e["t"] == 0.0 and e["total"] == 0.0 and e["titulo"] == "Senbonzakura" and "raro" not in e
    assert e["servicio"] is True
    m.biblioteca_cambio.emit(json.dumps(m.bailes))
    assert [b["id"] for b in J(bail[-1])["bailes"]] == [ID, ID2]
    m.biblioteca_cambio.emit("no json")
    assert J(bail[-1]) == {"bailes": [], "servicio": True}
    m.importado.emit(json.dumps({"ok": True, "texto": "Importado «x».\x00", "id": ID}))
    m.importado.emit(json.dumps({"ok": False, "texto": "No vale", "id": "C:/x"}))
    assert [J(x) for x in imp] == [{"ok": True, "texto": "Importado «x».", "id": ID},
                                   {"ok": False, "texto": "No vale", "id": None}]
    for v in ("bailes", "javascript:alert(1)", "settings", "minecraft"):
        m.vista_pedida.emit(v)
    assert vis == ["bailes", "minecraft"]


def test_una_biblioteca_grande_pasa_entera_y_se_corta_a_500(cfg):
    m = MMDFalso()
    p = puente(cfg, mmd=m)
    bail = cap(p.bailes_cambio)
    grande = [{"id": f"{i:012x}", "titulo": f"Baile {i} " + "x" * 60} for i in range(700)]
    m.biblioteca_cambio.emit(json.dumps(grande))                 # > 16 KB: viene de Python, no de la página
    assert len(J(bail[-1])["bailes"]) == 500


# ── Minecraft: validación ─────────────────────────────────────────────────────

def test_estado_de_minecraft_normalizado(cfg):
    p = puente(cfg, mc=MCFalso())
    e = J(p.mc_estado_json())
    assert e["servicio"] and e["reaccionar"] and e["log"] == {"ruta": "C:/mc/logs/latest.log", "activo": True, "yo": "Diego_01"}
    b = e["bot"]
    assert b["conectado"] and b["nick"] == "Lune" and b["vida"] == 18 and b["hambre"] is None and b["lluvia"] is None
    assert e["requisitos"] == {"node": "v24.19.0", "node_ok": True, "npm": True} and e["pensando"] is True


@pytest.mark.parametrize("obj, texto", [
    ({"ruta_log": "C:/Windows/win.ini"}, "Detectar"),
    ({"ruta_log": "C:/otra/logs/latest.log"}, "Detectar"),
    ({"ruta_log": 3}, "no vale"),
    ({"port": "25565"}, "enteros"),
    ({"port": 70000}, "65535"),
    ({"pensar_cada_s": 1.5}, "enteros"),
    ({"defender": "sí"}, "sí o no"),
    ({"estilo_frases": "kawaii"}, "personaje"),
    ({"host": ["a"]}, "texto"),
    ({"reaccionar": 1}, "sí o no"),
    ({"visor": True}, "no válidos"),
    ({}, "no válidos"),
])
def test_config_de_minecraft_rechaza_sin_tocar_nada(cfg, tmp_path, obj, texto):
    log = tmp_path / "mc" / "logs" / "latest.log"
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")
    datos = DatosFalsos()
    mc = MCFalso()
    p = puente(cfg, mc=mc, datos=datos, rutas=lambda: [log])
    antes = json.dumps(cfg.config, sort_keys=True)
    r = J(p.mc_config_guardar(json.dumps(obj)))
    assert r["ok"] is False and texto in r["error"], r["error"]
    assert json.dumps(cfg.config, sort_keys=True) == antes
    assert mc.llamadas == []
    if "port" not in obj or obj["port"] != 70000:
        assert datos.guardados == []


def test_config_de_minecraft_guarda_config_y_datos(cfg, tmp_path):
    log = tmp_path / "PrismLauncher" / "logs" / "latest.log"
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")
    datos = DatosFalsos()
    mc = MCFalso()
    p = puente(cfg, mc=mc, datos=datos, rutas=lambda: [log])
    estados = cap(p.mc_estado)
    r = J(p.mc_config_guardar(json.dumps({"reaccionar": True, "decir_en_juego": False, "ruta_log": str(log).upper(),
                                          "host": " mi.servidor.net ", "port": 25566, "usuario": "Lune_bot",
                                          "solo_dueno": False, "estilo_frases": "sobrio", "pensar_cada_s": 90})))
    assert r["ok"] and r["error"] == ""
    assert datos.guardados == [{"host": "mi.servidor.net", "port": 25566, "usuario": "Lune_bot", "solo_dueno": False,
                                "estilo_frases": "sobrio", "pensar_cada_s": 90}]
    assert cfg.get("minecraft", "reaccionar") is True and cfg.get("minecraft", "decir_en_juego") is False
    assert cfg.get("minecraft", "ruta_log") == str(log), "la ruta tal cual la encontró «Detectar»"
    assert r["config"]["bot"]["host"] == "mi.servidor.net" and r["config"]["config"]["ruta_log"] == str(log)
    assert mc.llamadas == [("recargar",)] and estados
    assert J(p.mc_config_guardar('{"ruta_log": ""}'))["ok"] and cfg.get("minecraft", "ruta_log") == ""


def test_detectar_el_log_sugiere_el_mas_reciente(cfg, tmp_path):
    viejo = tmp_path / "a" / "logs" / "latest.log"
    nuevo = tmp_path / "b" / "logs" / "latest.log"
    for i, f in enumerate((viejo, nuevo)):
        f.parent.mkdir(parents=True)
        f.write_text("x", encoding="utf-8")
        os.utime(f, (time.time() - 1000 + i * 500,) * 2)
    p = puente(cfg, rutas=lambda: [viejo, nuevo])
    r = J(p.mc_log_detectar())
    assert r == {"ok": True, "rutas": [str(viejo), str(nuevo)], "sugerida": str(nuevo), "actual": ""}
    assert J(puente(cfg).mc_log_detectar()) == {"ok": False, "rutas": [], "sugerida": "", "actual": ""}


def test_ordenes_decir_bot_e_instalar(cfg):
    mc = MCFalso()
    p = puente(cfg, mc=mc)
    assert J(p.mc_orden("x" * 201))["ok"] is False and J(p.mc_orden("   "))["ok"] is False
    assert J(p.mc_orden(123))["ok"] is False and J(p.mc_decir(None))["ok"] is False
    r = J(p.mc_orden("sígueme"))
    assert r == {"ok": True, "texto": "Se lo he mandado al bot."} and mc.llamadas[-1] == ("orden", "sígueme", "usuario")
    assert J(p.mc_decir("x" * 101))["ok"] is False
    assert J(p.mc_decir("hola"))["ok"] and mc.llamadas[-1] == ("decir", "hola")
    r = J(p.mc_bot_conectar())
    assert r["ok"] and r["texto"].startswith("Conectando") and r["estado"]["bot"]["conectado"]
    assert p.mc_bot_desconectar() is True
    assert ("instalar",) not in mc.llamadas
    r = J(p.mc_bot_instalar())
    assert r["ok"] and "400 MB" in r["texto"] and mc.llamadas[-1] == ("instalar",)
    mc.instalando = True
    assert J(p.mc_bot_instalar())["ok"] is False and mc.llamadas.count(("instalar",)) == 1


def test_senales_de_minecraft_solo_texto(cfg):
    mc = MCFalso()
    p = puente(cfg, mc=mc)
    ev, chat, log, est = cap(p.mc_evento), cap(p.mc_chat), cap(p.mc_log), cap(p.mc_estado)
    mc.evento.emit(json.dumps({"tipo": "logro", "texto": "¡Cazamonstruos!", "estado": "happy", "fuente": "log", "t": 2,
                               "entregado": True, "extra": 1}))
    mc.evento.emit(json.dumps({"tipo": "<b>x</b>", "texto": "no"}))
    assert [J(x) for x in ev] == [{"tipo": "logro", "texto": "¡Cazamonstruos!", "estado": "happy", "fuente": "log",
                                   "t": 2.0, "entregado": True}]
    mc.chat.emit(json.dumps({"de": "Steve", "texto": "<b>hola</b>\x1b[31m @@LUNE x"}))
    mc.chat.emit(json.dumps({"de": "<script>", "texto": "hola"}))
    mc.chat.emit(json.dumps({"de": "Alex_2", "texto": "\x00\x07"}))
    assert [J(x) for x in chat] == [{"de": "Steve", "texto": "<b>hola</b>[31m @@LUNE x", "t": 0.0}]
    mc.log_bot.emit("conectado\x00 " + "y" * 400)
    mc.log_bot.emit("\x00")
    assert len(log) == 1 and len(log[0]) == 300 and "\x00" not in log[0]
    mc.estado_cambio.emit("{}")
    assert J(est[-1])["servicio"] is True
    assert [e["tipo"] for e in J(p.mc_eventos())] == ["muerte"]


# ── Servicios tardíos ─────────────────────────────────────────────────────────

def test_enlazar_tarde_con_serviciocorte4_y_soltar_al_desmontar(cfg):
    p = puente(cfg)
    m, mc = MMDFalso(), MCFalso()
    est_mmd, est_mc = cap(p.mmd_estado), cap(p.mc_estado)
    s4 = SimpleNamespace(escenario=SimpleNamespace(mmd=m, minecraft=mc), _deshacer=[])
    p.enlazar(s4)
    assert p.mmd is m and p.minecraft is mc
    assert J(est_mmd[-1])["servicio"] and J(est_mc[-1])["servicio"]
    p.enlazar(s4)                                                     # otra vez: un solo «soltar»
    assert len(s4._deshacer) == 1
    for f in reversed(s4._deshacer):                                  # el cambio de interfaz
        f()
    assert p.mmd is None and p.minecraft is None and J(est_mmd[-1])["servicio"] is False
    m.estado_cambio.emit("{}")                                        # ya no escucha
    assert J(est_mmd[-1])["servicio"] is False


def test_enlazar_con_el_escritorio_como_respaldo(cfg):
    m, mc = MMDFalso(), MCFalso()
    esc = SimpleNamespace(obtener=lambda n: {"mmd": m, "minecraft": mc}.get(n))
    p = puente(cfg)
    p.enlazar(SimpleNamespace(escritorio=esc, _deshacer=[]))
    assert p.mmd is m and p.minecraft is mc
    p.cerrar()
    assert p.mmd is None
    p.enlazar(SimpleNamespace(mmd=m))                                 # cerrado: no vuelve a tomar nada
    assert p.mmd is None


# ── Con las clases de verdad (agentes C y D) ──────────────────────────────────

class ProcesoFalso:
    def __init__(self):
        self.vivo = False
        self.on_evento = self.on_log = self.on_fin = None
        self.arranques, self.paradas = [], []

    def requisitos(self, refrescar=False):
        return {"node": "v24.19.0", "node_ok": True, "npm": True, "instalado": True}

    def instalado(self):
        return True

    def instalar(self, cancelar=None):
        return True, "Instalado."

    def arrancar(self, cfg, probar=False):
        self.arranques.append(cfg)
        self.vivo = True
        return True, "Arrancando…"

    def parar(self, espera_s=4.0):
        self.paradas.append(espera_s)
        self.vivo = False

    def orden(self, id_, texto):
        return True

    def decir(self, texto):
        return True

    def pausa_llm(self, on):
        return True

    def pausa_autonomo(self, on):
        return True


def test_con_las_clases_de_verdad(cfg, tmp_path):
    from bailes_falsos import hacer_baile
    from nucleo.bailes import Biblioteca
    from ui.escritorio import ServiciosEscritorio
    from ui.minecraft_qt import ControlMinecraft
    from ui.mmd_qt import ControlMMD
    carpeta = tmp_path / "bailes"
    hacer_baile(carpeta, "Senbonzakura", meta={"titulo": "Senbonzakura", "autor_cancion": "Kurousa-P"})
    esc = ServiciosEscritorio(cfg)
    m = ControlMMD(esc, cfg, biblioteca=Biblioteca(carpeta, tmp_path / "cache", config=cfg), hilo=False)
    proceso = ProcesoFalso()
    mc = ControlMinecraft(esc, cfg, proceso=proceso, rutas=lambda: [],
                          datos_mc=lambda: {"host": "localhost", "port": 25565, "dueno": "Diego_01"},
                          personaje=lambda: {"nombre": "Lune"}, llm=lambda: {"proveedor": "ollama"},
                          hilo=lambda fn, *a, **k: fn())
    esc.registrar("mmd", m, ("mmd",))
    esc.registrar("minecraft", mc)
    esc.iniciar()
    p = puente(cfg)
    bail = cap(p.bailes_cambio)
    try:
        p.enlazar(SimpleNamespace(escritorio=esc, _deshacer=[]))
        assert p.bailes_refrescar() and bail and J(bail[-1])["bailes"][0]["titulo"] == "Senbonzakura"
        [b] = J(p.bailes_lista("kurousa"))["bailes"]
        id_ = b["id"]
        assert p.baile_favorito(id_, True) and id_ in cfg.get("baile", "favoritos")
        r = J(p.baile_meta_guardar(id_, json.dumps({"offset_ms": 120, "en_el_sitio": False})))
        assert r["ok"], r
        assert J(p.bailes_lista(""))["bailes"][0]["offset_ms"] == 120
        r = J(p.mmd_config_guardar(json.dumps({"volumen": 0.5, "al_terminar": "repetir", "en_el_sitio": False})))
        assert r["ok"] and cfg.get("baile", "volumen") == 0.5 and cfg.get("baile", "al_terminar") == "repetir"
        r = J(p.mmd_reproducir(id_))                                      # sin mascota: espera a que salga
        assert r["ok"] and r["estado"]["pendiente"] is True and r["estado"]["id"] == id_
        assert J(p.mmd_parar())["ok"] and J(p.mmd_estado_json())["fase"] == "parado"
        e = J(p.mc_estado_json())
        assert e["servicio"] and e["requisitos"]["node_ok"] in (None, True) and e["bot"]["instalado"]
        r = J(p.mc_bot_conectar())
        assert r["ok"] and proceso.arranques[-1]["host"] == "localhost"
        assert r["estado"]["requisitos"] == {"node": "v24.19.0", "node_ok": True, "npm": True}
        assert J(p.mc_orden("hackea el servidor"))["ok"] is False
    finally:
        esc.detener()
        m.deleteLater()
        mc.deleteLater()
