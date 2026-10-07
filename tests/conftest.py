"""
Configuración compartida de los tests.

Los tests que tocan widgets necesitan una QApplication viva, y solo puede haber
una por proceso. Se crea en modo offscreen para que no abra ventanas de verdad
durante la ejecución.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Los datos de verdad (config.json, datos.json con las API keys, memoria.json,
# alarmas.json, chats/, logs/, bailes/, modelo_vrm/…) no se tocan NUNCA desde los
# tests. Antes Config() sin ruta leía y, con un cambio de esquema, REESCRIBÍA el
# config.json del usuario, y guardar_config() de la web reescribía datos.json entero.
# Ahora todo cuelga de nucleo/rutas.py, y LUNE_CD_DATOS lleva DATOS y LOCAL a una
# carpeta temporal vacía por sesión. Tiene que ponerse ANTES del primer import de
# nucleo: rutas calcula sus carpetas al importarse y nucleo.datos copia ahí la
# plantilla (datos.example.json, sin claves) al importarse. Así todos los tests
# arrancan con los valores por defecto, igual en cualquier equipo, y los subprocess
# de los tests (patata, main) heredan la variable. Los que ya desvían algo con
# monkeypatch (datos_tmp y compañía) siguen igual.
_DATOS_TESTS = Path(tempfile.mkdtemp(prefix="lune_tests_datos_")).resolve()
os.environ["LUNE_CD_DATOS"] = str(_DATOS_TESTS)


def _borrar_datos_tests():
    # El log del día sigue abierto hasta logging.shutdown (que va después): en Windows
    # no se podría borrar la carpeta con él abierto.
    import logging
    for h in logging.getLogger("lune").handlers[:]:
        try:
            h.close()
        except Exception:
            pass
    shutil.rmtree(_DATOS_TESTS, True)


atexit.register(_borrar_datos_tests)

# Igual que main.py: el runtime de C++ del sistema antes que el de PyQt6, para
# que los tests que mezclan Qt con librerías C++ (Whisper, ONNX) no revienten.
from nucleo.runtime_win import precargar_msvc  # noqa: E402

precargar_msvc()

# Red de seguridad: si algo hubiera importado nucleo.rutas antes que este archivo, sus
# carpetas serían las de verdad. Mejor no correr ningún test.
from nucleo import rutas as _rutas  # noqa: E402

if _rutas.DATOS != _DATOS_TESTS or _rutas.LOCAL != _DATOS_TESTS:
    raise RuntimeError(f"tests: nucleo.rutas apunta a {_rutas.DATOS}, no a la carpeta temporal "
                       f"{_DATOS_TESTS}; no toco los datos de verdad")


@pytest.fixture(autouse=True, scope="module")
def _recoger_basura_en_el_hilo_principal():
    """Al acabar cada archivo de tests, la basura con ciclos se recoge AQUÍ, en el hilo
    principal. Si no, el recolector automático puede saltar dentro de un hilo de fondo
    (el hub, el cliente de websockets…) y destruir allí objetos de Qt o de Windows de
    tests anteriores: en GitHub Actions (Qt 6.11) eso tumbaba la suite con 0xC0000409 al
    procesar eventos en un test posterior (lo vimos con test_puente_tareas → test_hub →
    test_servicio_chat → test_tema_qt)."""
    yield
    import gc
    gc.collect()


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


# ── Rastro para GitHub Actions ────────────────────────────────────────────────
# tests.yml pone LUNE_CI_RASTRO=<archivo>: cada test se apunta al empezar y al acabar. Si el
# proceso muere a mitad (sin junit.xml ni resumen), el último «empieza» sin su «acaba» dice en
# qué test fue, y el paso «Qué test falló» lo publica como aviso. En casa no se activa.
_RASTRO = os.environ.get("LUNE_CI_RASTRO", "").strip()
if _RASTRO:
    _rastro = open(_RASTRO, "a", encoding="utf-8")

    def pytest_runtest_logstart(nodeid, location):
        print(f"empieza {nodeid}", file=_rastro, flush=True)

    def pytest_runtest_logfinish(nodeid, location):
        print(f"acaba {nodeid}", file=_rastro, flush=True)
