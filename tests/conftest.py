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


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
