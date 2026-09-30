"""
Tests de nucleo/pantalla_grande.py (sin Qt): pasos del salvapantallas, la máquina
de entrada/salida de la pantalla grande, la regla del salvapantallas y la
herramienta `asistente_pantalla_grande`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import pantalla_grande as pg  # noqa: E402
from nucleo.estado_asistente import EstadoAsistente  # noqa: E402
from nucleo.pantalla_grande import MaquinaGrande, ReglaSalvapantallas  # noqa: E402


def nombres(acciones):
    return [a if a != "fase" else f"fase:{d['fase']}" for a, d in acciones]


# ── Pasos ────────────────────────────────────────────────────────────────────

def test_once_pasos_como_mate_engine():
    assert pg.TIEMPOS == (30, 60, 300, 900, 1800, 2700, 3600, 5400, 7200, 9000, 10800)
    assert len(pg.ETIQUETAS) == 11
    assert [pg.segundos(i) for i in range(11)] == list(pg.TIEMPOS)
    assert pg.etiqueta(0) == "30 s"
    assert pg.etiqueta(2) == "5 min"
    assert pg.etiqueta(7) == "1 h 30 min"
    assert pg.etiqueta(10) == "3 h"


@pytest.mark.parametrize("entrada, paso", [(-3, 0), (99, 10), ("4", 4), (2.6, 3), (None, 0),
                                           ("x", 0), (float("nan"), 0), (float("inf"), 0)])
def test_paso_fuera_de_rango_se_acota(entrada, paso):
    assert pg.paso_valido(entrada) == paso


# ── Máquina ──────────────────────────────────────────────────────────────────

def test_entrada_planeo_monitor_fundido_activa():
    m = MaquinaGrande()
    a = m.pedir_entrar("manual", 0.0)
    assert nombres(a) == ["guardar_geom", "fase:glide"]
    assert a[1][1]["ms"] == pg.GLIDE_MS
    assert m.estado == "entrando" and m.en_transicion
    assert m.avanzar(0.39) == []                       # aún planeando
    a = m.avanzar(0.40)
    assert nombres(a) == ["geom_monitor", "fase:entrar"]
    assert a[1][1]["ms"] == pg.FADE_MS
    assert m.avanzar(0.85) == []
    a = m.avanzar(0.90)
    assert nombres(a) == ["activa"]
    assert a[0][1]["motivo"] == "manual"
    assert m.estado == "activa" and not m.en_transicion


def test_salida_inversa_y_fin():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.avanzar(10.0)
    m.avanzar(10.0)
    assert m.estado == "activa"
    a = m.pedir_salir(20.0)
    assert nombres(a) == ["fase:salir"]
    assert m.estado == "saliendo"
    assert nombres(m.avanzar(20.5)) == ["restaurar_geom", "fase:volver"]
    a = m.avanzar(20.9)
    assert nombres(a) == ["fase:fin", "fin"]
    assert a[-1][1]["motivo"] == "manual"
    assert m.estado is None and m.motivo == ""


def test_un_salto_de_tiempo_encadena_los_pasos():
    m = MaquinaGrande()
    m.pedir_entrar("herramienta", 0.0)
    assert nombres(m.avanzar(5.0)) == ["geom_monitor", "fase:entrar", "activa"]


def test_entrar_durante_la_salida_se_encola():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.avanzar(1.0)
    m.avanzar(1.0)
    m.pedir_salir(2.0)
    assert m.pedir_entrar("alarma", 2.1) == []
    assert m.encolado == "alarma"
    m.avanzar(2.5)
    a = m.avanzar(2.9)
    # termina la salida y empieza la entrada encolada
    assert nombres(a) == ["fase:fin", "fin", "guardar_geom", "fase:glide"]
    assert m.estado == "entrando" and m.motivo == "alarma"
    assert m.encolado is None


def test_entrar_con_la_entrada_en_marcha_o_activa_no_hace_nada():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    assert m.pedir_entrar("alarma", 0.1) == []
    assert m.motivo == "manual"
    m.avanzar(1.0)
    m.avanzar(1.0)
    assert m.pedir_entrar("alarma", 2.0) == []
    assert m.estado == "activa" and m.motivo == "manual"


def test_salir_durante_la_entrada_sale_al_llegar():
    m = MaquinaGrande()
    m.pedir_entrar("salvapantallas", 0.0)
    assert m.pedir_salir(0.1) == []
    assert m.estado == "entrando"
    m.avanzar(0.4)
    a = m.avanzar(0.9)
    assert nombres(a) == ["activa", "fase:salir"]
    assert m.estado == "saliendo"


def test_salir_con_motivo_solo_si_coincide():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.avanzar(1.0)
    m.avanzar(1.0)
    assert m.pedir_salir(2.0, motivo="alarma") == []      # la alarma no quita la grande manual
    assert m.estado == "activa"
    assert nombres(m.pedir_salir(2.0, motivo="manual")) == ["fase:salir"]


def test_salir_con_motivo_anula_la_cola_de_ese_motivo():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.avanzar(1.0)
    m.avanzar(1.0)
    m.pedir_salir(2.0)
    m.pedir_entrar("alarma", 2.1)
    m.pedir_salir(2.2, motivo="alarma")
    assert m.encolado is None
    m.avanzar(3.0)
    m.avanzar(4.0)
    assert m.estado is None


def test_cambiar_motivo():
    m = MaquinaGrande()
    m.cambiar_motivo("alarma")                          # sin pantalla grande: nada
    assert m.motivo == ""
    m.pedir_entrar("salvapantallas", 0.0)
    m.avanzar(1.0)
    m.avanzar(1.0)
    m.cambiar_motivo("alarma")
    assert m.motivo == "alarma"
    assert m.pedir_salir(2.0, motivo="salvapantallas") == []
    assert nombres(m.pedir_salir(2.0, motivo="alarma")) == ["fase:salir"]


def test_salir_ya_sin_animacion_y_sin_cola():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.avanzar(0.5)                                      # ya en el monitor
    a = m.salir_ya(0.6)
    assert nombres(a) == ["restaurar_geom", "fase:fin", "fin"]
    assert m.estado is None
    # durante la salida con cola: salir_ya la descarta
    m.pedir_entrar("manual", 1.0)
    m.avanzar(2.0)
    m.avanzar(2.0)
    m.pedir_salir(3.0)
    m.pedir_entrar("alarma", 3.1)
    a = m.salir_ya(3.2)
    assert nombres(a) == ["restaurar_geom", "fase:fin", "fin"]
    assert m.estado is None and m.encolado is None
    assert m.salir_ya(4.0) == []


def test_abortar_olvida_todo():
    m = MaquinaGrande()
    m.pedir_entrar("manual", 0.0)
    m.abortar()
    assert m.estado is None and m.avanzar(5.0) == []


# ── Regla del salvapantallas ─────────────────────────────────────────────────

def test_regla_apagada_nunca_activa():
    r = ReglaSalvapantallas(False, 0)
    assert r.motivo_no(EstadoAsistente()) == "apagado"
    assert r.debe_activar(10_000, EstadoAsistente()) is False


def test_regla_umbral_del_paso():
    r = ReglaSalvapantallas(True, 2)                    # 5 min
    assert r.umbral_s == 300 and r.etiqueta == "5 min"
    assert r.debe_activar(299, EstadoAsistente()) is False
    assert r.debe_activar(300, EstadoAsistente()) is True


@pytest.mark.parametrize("campo, valor, motivo", [
    ("juego", True, "juego"), ("alarma", True, "alarma"), ("grande", True, "grande"),
    ("salvapantallas", True, "salvapantallas"), ("arrastrando", True, "arrastrando"),
    ("menu_abierto", True, "menu_abierto"), ("hablando", True, "hablando"),
    ("llamada", True, "llamada"), ("pensando", True, "pensando"),
    ("bailando", "musica", "bailando"), ("bailando", "mmd", "bailando"),
])
def test_regla_bloqueos(campo, valor, motivo):
    r = ReglaSalvapantallas(True, 0)
    est = EstadoAsistente(**{campo: valor})
    assert r.motivo_no(est) == motivo
    assert r.debe_activar(9999, est) is False


def test_regla_dormida_cuenta_como_reposo():
    r = ReglaSalvapantallas(True, 0)
    assert r.debe_activar(31, EstadoAsistente(durmiendo=True, visible=True, render="vrm")) is True


def test_regla_pensando_mando_y_pantalla_requerida():
    r = ReglaSalvapantallas(True, 0)
    est = EstadoAsistente()
    assert r.motivo_no(est, pensando=True) == "pensando"
    assert r.motivo_no(est, mando=True) == "mando"
    assert r.motivo_no(est, pantalla_requerida=True) == "pantalla_requerida"
    assert r.debe_activar(60, est, pantalla_requerida=True) is False
    assert r.debe_activar(60, est) is True


def test_regla_acepta_dict_y_none_y_valores_raros():
    r = ReglaSalvapantallas(True, 0)
    assert r.motivo_no({"juego": True}) == "juego"
    assert r.motivo_no(None) == ""
    assert r.debe_activar("x", None) is False
    assert r.debe_activar(float("nan"), None) is False


def test_regla_desde_config():
    cfg = {"salvapantallas": {"activo": True, "paso": 3}}
    r = ReglaSalvapantallas.desde_config(cfg)
    assert r.activo and r.paso == 3 and r.umbral_s == 900

    class Cfg:
        def get(self, s, k, d=None):
            return {"activo": True, "paso": 42}.get(k, d) if s == "salvapantallas" else d
    r = ReglaSalvapantallas.desde_config(Cfg())
    assert r.activo and r.paso == 10


# ── Herramienta ──────────────────────────────────────────────────────────────

class GrandeFalsa:
    def __init__(self, ok=True):
        self.ok = ok
        self.activo = False
        self.diario = []
        self.ultimo_error = "hay un juego delante"

    def entrar(self, motivo="manual", minutos=None):
        self.diario.append(("entrar", motivo, minutos))
        if self.ok:
            self.activo = True
        return self.ok

    def salir(self, motivo=None, inmediato=False):
        self.diario.append(("salir", motivo))
        self.activo = False
        return True


def test_herramienta_activa_con_minutos_por_en_ui():
    g = GrandeFalsa()
    hilos = []

    def en_ui(fn):
        hilos.append("ui")
        return fn()
    r = pg.herramienta({"activar": True, "minutos": 5}, {"grande": g, "en_ui": en_ui})
    assert isinstance(r, str) and "5 min" in r
    assert g.diario == [("entrar", "herramienta", 5)]
    assert hilos                                        # todo pasó por el hilo de Qt


def test_herramienta_minutos_se_acotan_y_textos():
    g = GrandeFalsa()
    pg.herramienta({"activar": "true", "minutos": 999}, {"grande": g})
    assert g.diario[-1] == ("entrar", "herramienta", 120)
    r = pg.herramienta({"activar": False}, {"grande": g})
    assert "vuelvo" in r and g.diario[-1] == ("salir", None)
    r = pg.herramienta({"activar": False}, {"grande": g})
    assert r == "No estaba en pantalla grande."


def test_herramienta_errores():
    assert pg.herramienta({"activar": True}, {})[0] is False
    assert pg.herramienta({}, {"grande": GrandeFalsa()})[0] is False
    ok, motivo = pg.herramienta({"activar": True}, {"grande": GrandeFalsa(ok=False)})
    assert ok is False and "juego" in motivo

    def en_ui_roto(fn):
        raise TimeoutError("la asistente no respondió a tiempo")
    ok, motivo = pg.herramienta({"activar": True}, {"grande": GrandeFalsa(), "en_ui": en_ui_roto})
    assert ok is False and "respondió" in motivo


def test_herramienta_ctx_envuelto_por_el_ejecutor():
    class Ctx:
        pass
    c = Ctx()
    c.grande = GrandeFalsa()
    r = pg.herramienta({"activar": True}, {"contexto": c})
    assert isinstance(r, str) and c.grande.activo
