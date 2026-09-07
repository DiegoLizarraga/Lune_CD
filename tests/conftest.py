"""
Configuración compartida de los tests.

Los tests que tocan widgets necesitan una QApplication viva, y solo puede haber
una por proceso. Se crea en modo offscreen para que no abra ventanas de verdad
durante la ejecución.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Igual que main.py: el runtime de C++ del sistema antes que el de PyQt6, para
# que los tests que mezclan Qt con librerías C++ (Whisper, ONNX) no revienten.
from nucleo.runtime_win import precargar_msvc  # noqa: E402

precargar_msvc()


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
