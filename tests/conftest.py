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

# Igual que main.py: el runtime de C++ del sistema antes que el de PyQt6, para
# que los tests que mezclan Qt con librerías C++ (Whisper, ONNX) no revienten.
from nucleo.runtime_win import precargar_msvc  # noqa: E402

precargar_msvc()

# El config.json de verdad no se toca NUNCA desde los tests. Config() sin ruta
# cuelga de nucleo.config.RAIZ (el repo): leía y, con un cambio de esquema,
# REESCRIBÍA el config.json del usuario; un test que guardara un ajuste lo
# cambiaba de verdad. Aquí RAIZ pasa a una carpeta temporal vacía por proceso:
# los tests arrancan con los valores por defecto, igual en cualquier equipo.
# nucleo/alarmas.py toma RAIZ de aquí, así que alarmas.json también queda a
# salvo. (RUTA_CONFIG, la constante, se deja: hay un test que comprueba su valor.)
from nucleo import config as _config_mod  # noqa: E402

_RAIZ_TESTS = Path(tempfile.mkdtemp(prefix="lune_tests_cfg_")).resolve()
_config_mod.RAIZ = _RAIZ_TESTS
atexit.register(shutil.rmtree, _RAIZ_TESTS, True)

# Lo mismo con datos.json (las API keys): nucleo.datos es el único que lo toca y
# guardar_config() de la web lo relee y lo REESCRIBE entero aunque no cambie nada; un
# test que lo llamaba sin datos temporales reescribía el de verdad. Aquí todos los tests
# parten de una copia de datos.example.json (sin claves). Los que ya lo desvían con
# monkeypatch (datos_tmp y compañía) siguen igual.
from nucleo import datos as _datos_mod  # noqa: E402

_DATOS_TESTS = _RAIZ_TESTS / "datos.json"
_ejemplo = Path(_datos_mod._EJEMPLO)
if _ejemplo.exists():
    shutil.copyfile(_ejemplo, _DATOS_TESTS)
else:
    _DATOS_TESTS.write_text("{}", encoding="utf-8")
_datos_mod._PATH = _DATOS_TESTS
_datos_mod.invalidar()


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
