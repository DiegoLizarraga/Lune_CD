"""
Tests de nucleo/runtime_win: la precarga del runtime de C++ que evita el
APPCRASH de Whisper dentro de PyQt6 (ver la cabecera del módulo).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import runtime_win as R  # noqa: E402


def test_version_de_dll_inexistente_es_cero():
    assert R.version_dll(r"C:\no\existe\jamas.dll") == (0, 0, 0, 0)


def test_precargar_nunca_lanza_y_devuelve_lista():
    assert isinstance(R.precargar_msvc(), list)
    assert isinstance(R.ultimo_informe, str) and R.ultimo_informe


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_en_windows_lee_versiones_reales():
    sistema = Path(r"C:\Windows\System32\msvcp140.dll")
    if not sistema.exists():
        pytest.skip("sin msvcp140 en System32")
    v = R.version_dll(str(sistema))
    assert v[0] == 14 and v[1] >= 20          # 14.x: es el runtime de VS 2015-2022


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_en_windows_no_carga_un_runtime_mas_viejo_que_el_de_qt(monkeypatch):
    """Si el de System32 fuera más viejo que el de PyQt6, NO se toca (Qt no arrancaría)."""
    qt_bin = R.carpeta_qt_bin()
    if qt_bin is None or not (qt_bin / "msvcp140.dll").exists():
        pytest.skip("PyQt6 sin Qt6/bin en este entorno")
    monkeypatch.delitem(sys.modules, "PyQt6.QtCore", raising=False)

    def version_falsa(ruta):
        return (14, 0, 0, 0) if "System32" in ruta else (14, 99, 0, 0)
    monkeypatch.setattr(R, "version_dll", version_falsa)
    assert R.precargar_msvc() == []
    assert "más viejo" in R.ultimo_informe


def test_fuera_de_windows_no_hace_nada(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert R.precargar_msvc() == []
    assert R.ultimo_informe == "no es Windows"


def test_main_precarga_antes_de_importar_pyqt6():
    """La llamada tiene que ir ANTES del primer import de PyQt6 en main.py."""
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    assert src.index("precargar_msvc()") < src.index("from PyQt6")
