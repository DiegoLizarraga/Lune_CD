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


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
