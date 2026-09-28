"""
ui/puente_alarmas.py (objeto `alarmas` del QWebChannel, window.luneAlarmas) y ui/puentes_ocio.py.

Con dobles de ControlAlarmasQt y ControlPantallaGrande (QObject con las mismas señales):
  · validación y rechazo de lo que manda la página (JSON, ids, hora, días, textos, rangos, tipos);
  · lo que llega al controlador es exactamente el contrato (dict de guardar_alarma/crear_temporizador);
  · servicios tardíos (registrar_puentes_ocio antes de setUrl y enlazar después) y soltarlos al
    desmontar ServiciosCorte4 (su _deshacer) o al cerrar;
  · señales de los controladores reemitidas (normalizadas) hacia la página;
  · sin servicios, estado por defecto; la config se lee y se guarda igual (Config real en tmp).
"""
import json
import os
from dataclasses import dataclass, field
from typing import Any, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from ui import puente_alarmas as pa  # noqa: E402
from ui.puentes_ocio import PuentesOcio, registrar_puentes_ocio  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PyQt6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


# ── Dobles ─────────────────────────────────────────────────────────────────────

class AlarmasFalsas(QObject):
    """Como ControlAlarmasQt: listar() con la forma real (hora «HH:MM», dias en letras + dias_mask)."""
    sonando = pyqtSignal(str)
    apagada = pyqtSignal()
    cambio = pyqtSignal(str)
    perdidas = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas: List[tuple] = []
        self.alarmas = [
            {"id": "a2", "hora": "21:00", "h": 21, "m": 0, "minuto": 0, "dias": "sd", "dias_mask": 96, "una_vez": False,
             "texto": "cena", "activa": True, "proxima": 1700050000.0},
            {"id": "a1", "hora": "07:30", "h": 7, "m": 30, "minuto": 30, "dias": "lmxjv", "dias_mask": 31, "una_vez": False,
             "texto": "gimnasio‮\x07", "activa": False, "proxima": None},
            {"id": "mal id", "hora": "07:30", "minuto": 30},
        ]
        self.temps = [{"id": "t1", "duracion_s": 300, "texto": "té", "objetivo": 1700000065.0, "restante_s": 300, "activo": True},
                      {"id": "t2", "duracion_s": 60, "texto": "", "objetivo": 0, "restante_s": 0, "activo": False}]
        self.resp_guardar: Any = None

    def listar(self):
        return {"activo": True, "alarmas": self.alarmas, "temporizadores": self.temps, "ahora": 1700000000.0,
                "proxima": {"id": "a2", "tipo": "alarma", "texto": "cena", "cuando": 1700050000.0, "cuando_texto": "hoy"},
                "sonando": None}

    def guardar_alarma(self, d):
        self.llamadas.append(("guardar_alarma", d))
        return self.resp_guardar if self.resp_guardar is not None else {"ok": True, "error": "", "id": d.get("id", "a3")}

    def crear_temporizador(self, d):
        self.llamadas.append(("crear_temporizador", d))
        return {"ok": True, "error": "", "id": "t3"}

    def borrar(self, id_):
        self.llamadas.append(("borrar", id_))
        return id_ in ("a1", "t1")

    def temporizador_accion(self, id_, accion):
        self.llamadas.append(("temporizador_accion", id_, accion))
        return True

    def apagar(self, forzar=False):
        self.llamadas.append(("apagar", forzar))
        return True

    def posponer(self):
        self.llamadas.append(("posponer",))
        return True

    def probar(self):
        self.llamadas.append(("probar",))
        return True

    def recargar_config(self):
        self.llamadas.append(("recargar_config",))

    def de(self, n):
        return [c[1:] for c in self.llamadas if c[0] == n]


class GrandeFalsa(QObject):
    """Como ControlPantallaGrande: alternar() devuelve si queda activa."""
    cambio = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.activo, self.motivo = False, ""
        self.llamadas: List[tuple] = []

    def estado(self):
        return {"activo": self.activo, "motivo": self.motivo if self.activo else "", "fase": "", "vista": ""}

    def alternar(self):
        self.llamadas.append(("alternar",))
        self.activo = not self.activo
        self.motivo = "manual" if self.activo else ""
        return self.activo

    def probar_salvapantallas(self):
        self.llamadas.append(("probar_salvapantallas",))
        return True

    def recargar_config(self):
        self.llamadas.append(("recargar_config",))


class CanalFalso:
    def __init__(self):
        self.registrados, self.quitados = {}, []

    def registerObject(self, nombre, obj):
        self.registrados[nombre] = obj

    def deregisterObject(self, obj):
        self.quitados.append(obj)


@dataclass
class OcioFalso:
    alarmas: Any = None
    grande: Any = None
    baile: Any = None


@dataclass
class ServiciosFalsos:
    ocio: Any = None
    escritorio: Any = None
    _deshacer: list = field(default_factory=list)

    def desmontar(self):
        for f in reversed(self._deshacer):
            f()
        self._deshacer.clear()


class Reloj:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


def _puente(config=None, **kw):
    return pa.PuenteAlarmas(config=config if config is not None else {}, **kw)


def _j(s):
    return json.loads(s)


def _senal(senal):
    recibido = []
    senal.connect(lambda *a: recibido.append(a))
    return recibido


# ── Sin servicios ──────────────────────────────────────────────────────────────

def test_sin_servicios_estado_por_defecto_y_nada_lanza():
    p = _puente(reloj=lambda: 1234.5)
    e = _j(p.alarmas_json())
    assert e == {"disponible": False, "activo": True, "ahora": 1234.5, "alarmas": [], "temporizadores": [],
                 "sonando": None, "proxima": None}
    r = _j(p.alarma_guardar(json.dumps({"hora": "07:00"})))
    assert r["ok"] is False and "en marcha" in r["error"] and r["estado"]["disponible"] is False
    assert _j(p.temporizador_crear('{"segundos": 60}'))["ok"] is False
    assert _j(p.alarma_borrar("a1"))["ok"] is False
    assert _j(p.temporizador_accion("t1", "parar"))["ok"] is False
    assert p.alarma_apagar() is False and p.alarma_posponer() is False and p.alarma_probar() is False
    assert _j(p.grande_estado_json()) == {"activa": False, "motivo": "", "disponible": False}
    assert p.grande_alternar() is False and p.salvapantallas_probar() is False
    c = _j(p.config_alarmas())
    assert c["volumen"] == 0.8 and c["sonido"] == "azar" and c["sonidos"] == ["azar", "alarma_1", "alarma_2", "alarma_3"]
    g = _j(p.config_grande())
    assert g["activo"] is False and g["paso"] == 0 and len(g["pasos"]) == 11
    assert [x["etiqueta"] for x in g["pasos"]][:3] == ["30 s", "1 min", "5 min"]


# ── Validación de lo que manda la página ───────────────────────────────────────

@pytest.mark.parametrize("payload", [
    "", "no json", "[]", "{}", '{"hora": NaN}', json.dumps({"hora": "7:00", "x": 1}),
    json.dumps({"hora": "24:00"}), json.dumps({"hora": "7"}), json.dumps({"hora": 7}),
    json.dumps({"hora": "07:00", "dias": "lmm"}), json.dumps({"hora": "07:00", "dias": "abc"}),
    json.dumps({"hora": "07:00", "dias": 128}), json.dumps({"hora": "07:00", "dias": True}),
    json.dumps({"hora": "07:00", "una_vez": "true"}), json.dumps({"hora": "07:00", "activa": 1}),
    json.dumps({"hora": "07:00", "texto": 5}), json.dumps({"id": "../x", "activa": False}),
    json.dumps({"texto": "sin hora"}), json.dumps({"hora": "07:00", "texto": "x" * 20000}),
])
def test_alarma_guardar_rechaza_lo_que_no_vale(payload):
    a = AlarmasFalsas()
    p = _puente(alarmas=a)
    r = _j(p.alarma_guardar(payload))
    assert r["ok"] is False and r["error"]
    assert a.de("guardar_alarma") == []
    assert r["estado"]["disponible"] is True


def test_alarma_guardar_manda_el_contrato_exacto_y_devuelve_el_id():
    a = AlarmasFalsas()
    p = _puente(alarmas=a)
    r = _j(p.alarma_guardar(json.dumps({"hora": "7:05", "dias": "vl", "una_vez": False, "texto": "  pan‮ \x07 "})))
    assert r["ok"] is True and r["id"] == "a3"
    assert a.de("guardar_alarma") == [({"hora": 7, "minuto": 5, "dias": 0b10001, "una_vez": False, "texto": "pan",
                                        "activa": True},)]
    # Nueva sin días ni texto: por defecto todos los días; «todos» y la máscara también valen
    p.alarma_guardar(json.dumps({"hora": "23:59"}))
    assert a.de("guardar_alarma")[-1][0] == {"hora": 23, "minuto": 59, "dias": 0, "una_vez": False, "texto": "", "activa": True}
    p.alarma_guardar(json.dumps({"hora": "06:00", "dias": 96}))
    assert a.de("guardar_alarma")[-1][0]["dias"] == 96
    # Editar: parcial, con id
    p.alarma_guardar(json.dumps({"id": "a1", "activa": False}))
    assert a.de("guardar_alarma")[-1][0] == {"id": "a1", "activa": False}
    # El controlador dice que no: el error llega a la página
    a.resp_guardar = {"ok": False, "error": "no existe esa alarma"}
    r = _j(p.alarma_guardar(json.dumps({"id": "zz", "activa": True})))
    assert r == {**r, "ok": False, "error": "no existe esa alarma"}


def test_temporizadores_validacion_y_contrato():
    a = AlarmasFalsas()
    p = _puente(alarmas=a)
    for malo in ('{"segundos": 0}', '{"segundos": 86401}', '{"segundos": 1.5}', '{"segundos": "60"}',
                 '{"h": 1, "m": 60}', '{"h": -1}', '{"segundos": 60, "m": 1}', '{"segundos": 60, "iniciar": "si"}',
                 '{"segundos": 60, "otra": 1}', '{}'):
        assert _j(p.temporizador_crear(malo))["ok"] is False, malo
    assert a.de("crear_temporizador") == []
    r = _j(p.temporizador_crear(json.dumps({"h": 1, "m": 2, "s": 3, "texto": " té ", "iniciar": False})))
    assert r["ok"] is True and r["id"] == "t3"
    p.temporizador_crear('{"segundos": 600}')
    assert a.de("crear_temporizador") == [({"segundos": 3723, "texto": "té", "iniciar": False},),
                                         ({"segundos": 600, "texto": "", "iniciar": True},)]
    assert _j(p.temporizador_accion("t1", "parar"))["ok"] is True
    assert _j(p.temporizador_accion("t1", "borrar"))["ok"] is True
    assert _j(p.temporizador_accion("t1", "explotar"))["ok"] is False
    assert _j(p.temporizador_accion("t 1", "parar"))["ok"] is False
    assert a.de("temporizador_accion") == [("t1", "parar")]
    assert a.de("borrar") == [("t1",)]
    assert _j(p.alarma_borrar("a1"))["ok"] is True
    assert _j(p.alarma_borrar("nada"))["ok"] is False
    assert _j(p.alarma_borrar("<a>"))["ok"] is False
    assert p.alarma_apagar() is True and a.de("apagar") == [(False,)], "respeta el bloqueo: sin forzar"
    assert p.alarma_posponer() is True and p.alarma_probar() is True


def test_alarmas_json_normaliza_la_forma_de_listar():
    a = AlarmasFalsas()
    p = _puente(alarmas=a)
    e = _j(p.alarmas_json())
    assert e["disponible"] is True and e["ahora"] == 1700000000.0, "el reloj del controlador"
    assert [x["id"] for x in e["alarmas"]] == ["a1", "a2"], "ordenadas por hora; el id malo fuera"
    a1 = e["alarmas"][0]
    assert a1 == {"id": "a1", "activa": False, "hora": 7, "minuto": 30, "dias": 31, "una_vez": False,
                  "texto": "gimnasio", "fecha": "", "proxima": 0}
    assert e["alarmas"][1]["dias"] == 96 and e["alarmas"][1]["proxima"] == 1700050000.0
    assert e["temporizadores"] == [
        {"id": "t1", "activo": True, "duracion_s": 300, "objetivo": 1700000065.0, "restante_s": 300, "texto": "té"},
        {"id": "t2", "activo": False, "duracion_s": 60, "objetivo": 0, "restante_s": 60, "texto": ""},
    ]
    assert e["proxima"] == {"id": "a2", "tipo": "alarma", "texto": "cena", "cuando": 1700050000.0}
    # Un Alarma suelto (dataclass con la máscara en «dias») también vale
    from dataclasses import make_dataclass
    Alarma = make_dataclass("Alarma", [("id", str), ("hora", int), ("minuto", int), ("dias", int), ("texto", str)])
    assert pa.normalizar_alarma(Alarma("a9", 6, 0, 3, "x"))["dias"] == 3


# ── Servicios tardíos, señales y cierre ────────────────────────────────────────

def test_registro_antes_de_la_pagina_servicios_tardios_y_senales_reemitidas():
    canal = CanalFalso()
    mono = Reloj(100.0)
    puentes = registrar_puentes_ocio(canal, {}, reloj=lambda: 1.0)
    assert set(canal.registrados) == {"alarmas", "musica"}
    p = canal.registrados["alarmas"]
    p._mono = mono
    assert _j(p.alarmas_json())["disponible"] is False
    cambios, sonando, apagadas, grande = (_senal(p.alarmas_cambio), _senal(p.alarma_sonando), _senal(p.alarma_apagada),
                                          _senal(p.grande_estado))
    a, g = AlarmasFalsas(), GrandeFalsa()
    s4 = ServiciosFalsos(ocio=OcioFalso(alarmas=a, grande=g))
    puentes.enlazar(s4)
    assert _j(cambios[-1][0])["disponible"] is True, "la página ya cargada recibe el estado nuevo"
    assert _j(grande[-1][0])["disponible"] is True
    # sonando → alarma_sonando normalizado; y en alarmas_json con el bloqueo descontado
    a.sonando.emit(json.dumps({"texto": "gimnasio\x1b[31m", "texto_base": "x", "tipo": "raro", "atraso_s": 420.123,
                               "programado": "07:30", "apagar_en_ms": 5000, "cola": 2, "visual": "grande", "posponer_min": 7}))
    s = _j(sonando[-1][0])
    assert s == {"texto": "gimnasio[31m", "tipo": "alarma", "atraso_s": 420.1, "programado": "07:30",
                 "apagar_en_ms": 5000, "cola": 2, "posponer_min": 7}
    mono.t += 2.0
    assert _j(p.alarmas_json())["sonando"]["apagar_en_ms"] == 3000
    mono.t += 10.0
    assert _j(p.alarmas_json())["sonando"]["apagar_en_ms"] == 0
    a.apagada.emit()
    assert len(apagadas) == 1 and _j(p.alarmas_json())["sonando"] is None
    a.cambio.emit("{}")
    assert _j(cambios[-1][0])["alarmas"][0]["id"] == "a1", "alarmas_cambio con el estado fresco"
    g.cambio.emit(True, "alarma")
    assert _j(grande[-1][0]) == {"activa": True, "motivo": "alarma", "disponible": True}
    g.cambio.emit(False, "")
    assert _j(grande[-1][0])["activa"] is False
    # Desmontar los servicios (cambio de interfaz): el puente los suelta, sigue registrado
    n = len(sonando)
    s4.desmontar()
    assert _j(p.alarmas_json())["disponible"] is False
    a.sonando.emit(json.dumps({"texto": "x"}))
    assert len(sonando) == n, "ya no escucha al controlador viejo"
    assert canal.quitados == []
    # Otros servicios después (ventana nueva): se enlazan igual
    a2 = AlarmasFalsas()
    s4b = ServiciosFalsos(ocio=OcioFalso(alarmas=a2))
    puentes.enlazar(s4b)
    assert _j(p.alarmas_json())["disponible"] is True
    puentes.enlazar(s4b)
    assert len(s4b._deshacer) == 1, "no se apunta dos veces"
    # Cerrar: fuera del canal, sin señales, idempotente; enlazar después ya no hace nada
    puentes.cerrar()
    puentes.cerrar()
    assert set(map(id, canal.quitados)) == {id(canal.registrados["alarmas"]), id(canal.registrados["musica"])}
    assert len(canal.quitados) == 2
    a2.sonando.emit(json.dumps({"texto": "x"}))
    assert len(sonando) == n
    puentes.enlazar(s4b)
    assert _j(p.alarmas_json())["disponible"] is False


def test_enlazar_con_serviciosocio_directo_o_el_escritorio():
    a, g = AlarmasFalsas(), GrandeFalsa()
    p = _puente()
    puentes = PuentesOcio(p, None)
    puentes.enlazar(OcioFalso(alarmas=a, grande=g))
    assert p.alarmas is a and p.grande is g

    class Esc:
        def obtener(self, n):
            return {"alarmas": a, "grande": g}.get(n)
    p2 = _puente()
    PuentesOcio(p2, None).enlazar(ServiciosFalsos(ocio=None, escritorio=Esc()))
    assert p2.alarmas is a and p2.grande is g, "sin .ocio: los registrados en el escritorio"


def test_pantalla_grande_alternar_y_probar():
    g = GrandeFalsa()
    p = _puente(grande=g)
    assert p.grande_alternar() is True
    assert _j(p.grande_estado_json()) == {"activa": True, "motivo": "manual", "disponible": True}
    assert p.grande_alternar() is True, "salir también es un éxito (alternar devuelve False al salir)"
    assert _j(p.grande_estado_json())["activa"] is False

    class Bloqueada(GrandeFalsa):
        def alternar(self):
            return False                        # un juego no la deja entrar
    assert _puente(grande=Bloqueada()).grande_alternar() is False
    assert p.salvapantallas_probar() is True
    g.motivo, g.activo = "<script>", True
    assert _j(p.grande_estado_json())["motivo"] == ""


# ── Config ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def config_real(tmp_path):
    from nucleo.config import Config
    return Config(str(tmp_path / "config.json"))


def test_config_alarmas_rangos_y_guardado(config_real):
    a = AlarmasFalsas()
    p = _puente(config=config_real, alarmas=a)
    cambios = _senal(p.alarmas_cambio)
    for malo in ('{"volumen": 1.5}', '{"volumen": "0.5"}', '{"bloqueo_s": 31}', '{"bloqueo_s": 2.5}', '{"posponer_min": 0}',
                 '{"recuperar_min": 121}', '{"sonido": "bomba"}', '{"activo": "no"}', '{"otra": 1}', '{}', 'x'):
        r = _j(p.config_alarmas_guardar(malo))
        assert r["ok"] is False and r["error"], malo
    assert a.de("recargar_config") == []
    r = _j(p.config_alarmas_guardar(json.dumps({"volumen": 0.35, "sonido": "alarma_2", "bloqueo_s": 10, "decir_texto": False})))
    assert r["ok"] is True
    assert r["estado"]["volumen"] == 0.35 and r["estado"]["sonido"] == "alarma_2" and r["estado"]["bloqueo_s"] == 10
    assert config_real.get("alarmas", "sonido") == "alarma_2" and config_real.get("alarmas", "decir_texto") is False
    from nucleo.config import Config
    releida = Config(config_real.config_path)
    assert releida.get("alarmas", "bloqueo_s") == 10 and releida.get("alarmas", "decir_texto") is False, "escrito en disco"
    # alarmas.volumen/sonido los añade a DEFAULT_CONFIG la integración (Config poda lo que no está ahí)
    if "volumen" in Config.DEFAULT_CONFIG.get("alarmas", {}):
        assert releida.get("alarmas", "volumen") == 0.35 and releida.get("alarmas", "sonido") == "alarma_2"
    assert a.de("recargar_config") == [()]
    assert cambios == []
    p.config_alarmas_guardar('{"activo": false}')
    assert _j(cambios[-1][0])["disponible"] is True, "al pausar/activar, la vista se refresca"


def test_config_grande_pasos_y_guardado(config_real):
    g = GrandeFalsa()

    class PG:
        TIEMPOS = (30, 60, 300)

        @staticmethod
        def etiqueta(paso):
            return f"P{paso}"
    p = _puente(config=config_real, grande=g, pantalla_grande_mod=PG)
    c = _j(p.config_grande())
    assert c["pasos"] == [{"paso": 0, "segundos": 30, "etiqueta": "P0"}, {"paso": 1, "segundos": 60, "etiqueta": "P1"},
                          {"paso": 2, "segundos": 300, "etiqueta": "P2"}]
    assert _j(p.config_grande_guardar('{"paso": 3}'))["ok"] is False
    for malo in ('{"paso": -1}', '{"paso": 1.5}', '{"reloj": 1}', '{"fondo": true}', '{}'):
        assert _j(p.config_grande_guardar(malo))["ok"] is False, malo
    r = _j(p.config_grande_guardar(json.dumps({"activo": True, "paso": 2, "clic_sale_de_todo": False})))
    assert r["ok"] is True and r["estado"]["activo"] is True and r["estado"]["paso"] == 2
    assert config_real.get("salvapantallas", "clic_sale_de_todo") is False
    assert g.llamadas == [("recargar_config",)]
    # Con el módulo de verdad (nucleo/pantalla_grande.py): 11 pasos y sus etiquetas
    real = _j(_puente(config=config_real).config_grande())
    assert len(real["pasos"]) == 11 and real["pasos"][7]["etiqueta"] == "1 h 30 min"


def test_utilidades_puras():
    assert pa.parsear_hora("7:05") == (7, 5) and pa.parsear_hora("07:60") is None and pa.parsear_hora(705) is None
    assert pa.mascara_dias("lmxjv") == 31 and pa.mascara_dias("todos") == 0 and pa.mascara_dias("") == 0
    assert pa.mascara_dias("ll") is None and pa.mascara_dias(True) is None and pa.mascara_dias(-1) is None
    assert pa.texto_dias(0) == "todos" and pa.texto_dias(96) == "sd"
    assert [pa.etiqueta_tiempo(s) for s in (30, 300, 5400, 7200)] == ["30 s", "5 min", "1 h 30 min", "2 h"]
    assert pa.normalizar_sonando("no json") is None
    assert pa.normalizar_sonando({"texto": "x", "apagar_en_ms": 1e9, "cola": [1, 2, 3]})["apagar_en_ms"] == 60000
    assert pa.normalizar_sonando({"texto": "x", "cola": [1, 2, 3]})["cola"] == 3
    assert pa.normalizar_proxima({"id": "a1", "cuando": 0}) is None


def test_la_pagina_recibe_la_fecha_de_las_alarmas_de_un_dia():
    """Revisión 4-5-6 (MO3): «despiértame mañana a las 7» tiene fecha; la página no la
    recibía (la enseñaba como «Una vez» a secas y al editarla la fecha quedaba oculta)."""
    a = AlarmasFalsas()
    a.alarmas = [{"id": "a1", "hora": "07:00", "h": 7, "m": 0, "minuto": 0, "dias": "", "dias_mask": 0,
                  "una_vez": True, "texto": "", "activa": True, "fecha": "2026-09-27"},
                 {"id": "a2", "hora": "08:00", "h": 8, "m": 0, "minuto": 0, "dias": "", "dias_mask": 0,
                  "una_vez": True, "texto": "", "activa": True, "fecha": "<img src=x>"}]
    e = _j(_puente(alarmas=a).alarmas_json())
    assert [x["fecha"] for x in e["alarmas"]] == ["2026-09-27", ""], "solo AAAA-MM-DD"


def test_editar_con_dias_por_el_puente_quita_la_fecha(qapp, tmp_path):
    """MO3 de punta a punta: página → puente → ControlAlarmasQt → Almacen."""
    from nucleo.alarmas import Almacen
    from ui.alarmas_qt import ControlAlarmasQt

    class Mutex:
        es_dueno = False

        def adquirir(self):
            return False

    alm = Almacen(tmp_path / "alarmas.json")
    x = alm.crear_alarma(7, 0, fecha="2026-09-27")
    ctl = ControlAlarmasQt(None, None, almacen=alm, mutex=Mutex(), intervalo_ms=10 ** 6)
    p = _puente(alarmas=ctl)
    fila, = _j(p.alarmas_json())["alarmas"]
    assert fila["fecha"] == "2026-09-27" and fila["una_vez"] is True
    r = _j(p.alarma_guardar('{"id": "a1", "hora": "07:00", "dias": "lmxjv", "una_vez": false, "texto": ""}'))
    assert r["ok"] is True
    a = alm.obtener(x.id)
    assert (a.fecha, a.dias, a.una_vez) == ("", 31, False)
    assert r["estado"]["alarmas"][0]["fecha"] == ""
