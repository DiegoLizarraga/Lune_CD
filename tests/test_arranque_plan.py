"""
Tests del plan de arranque (nucleo/arranque.py): a mano, o con Windows en la
bandeja, con la mascota o con la ventana, y los límites de la espera.
"""
import pytest

from nucleo import arranque as ar
from nucleo.arranque import Opciones, Plan


def _cfg(como="bandeja", retraso=20):
    return {"sistema": {"autoinicio": True, "autoinicio_como": como, "autoinicio_retraso_s": retraso}}


@pytest.mark.parametrize("argv, auto", [
    ([], False),
    (["--autoinicio"], True),
    (["/autoinicio"], True),
    (["/AutoInicio"], True),
    (["main.py", "--otra", "--autoinicio"], True),
    (["--autoiniciox"], False),
    (None, False),
])
def test_parsear_args(argv, auto):
    assert ar.parsear_args(argv) == Opciones(autoinicio=auto)


def test_a_mano_pantalla_de_inicio_y_ventana():
    assert ar.plan_arranque(_cfg("mascota", 60), Opciones()) == Plan(True, True, False, 0, False)


def test_con_windows_en_la_bandeja():
    assert ar.plan_arranque(_cfg("bandeja"), Opciones(True)) == Plan(False, False, False, 20, True)


def test_con_windows_con_la_mascota():
    assert ar.plan_arranque(_cfg("mascota"), Opciones(True)) == Plan(False, False, True, 20, True)


def test_con_windows_con_la_ventana():
    assert ar.plan_arranque(_cfg("ventana", 5), Opciones(True)) == Plan(False, True, False, 5, True)


@pytest.mark.parametrize("valor, esperado", [
    (0, 0), (-5, 0), (300, 300), (999, 300), (45.7, 45), ("30", 30), ("abc", 20), (None, 20), (True, 20),
])
def test_limites_de_la_espera(valor, esperado):
    assert ar.plan_arranque(_cfg("bandeja", valor), Opciones(True)).retraso_s == esperado


def test_como_desconocido_es_la_bandeja():
    p = ar.plan_arranque(_cfg("escritorio"), Opciones(True))
    assert (p.mostrar_ventana, p.abrir_mascota) == (False, False)


def test_sin_config_la_bandeja_con_20_s():
    assert ar.plan_arranque(None, Opciones(True)) == Plan(False, False, False, 20, True)


def test_con_la_config_de_verdad_por_defecto_bandeja_y_20_s(tmp_path):
    """D3: por defecto «en la bandeja» con 20 s de espera."""
    from nucleo.config import Config
    cfg = Config(str(tmp_path / "config.json"))
    p = ar.plan_arranque(cfg, ar.parsear_args(["--autoinicio"]))
    assert p == Plan(splash=False, mostrar_ventana=False, abrir_mascota=False, retraso_s=20, silencioso=True)
    assert ar.COMOS == ("bandeja", "mascota", "ventana")
