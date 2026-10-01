"""
packaging/rth_msvc.py — Runtime hook de PyInstaller: el runtime de C++ bueno, antes que Qt.

Es el crash de «pulso el micrófono y Lune se cierra» (nucleo/runtime_win.py), versión
instalada. Desde el código basta con que main.py llame a precargar_msvc() antes de importar
PyQt6. Empaquetada no: el runtime hook de PyInstaller para PyQt6 (pyi_rth_pyqt6) importa
PyQt6.QtCore ANTES de main.py y con él entra la msvcp140.dll que haya a mano; main.py
llegaría tarde. Los runtime hooks propios (este, en packaging/lune.spec) corren antes que
los de PyInstaller, así que aquí se precarga a tiempo.

Además el build quita las msvcp140*/vcruntime140* de PyQt6/Qt6/bin (la 14.26 de 2020) y
en _internal queda una sola copia nueva: precargar_msvc() elige la más nueva entre esa y
la de System32. Nunca lanza: si algo falla, Lune arranca igual (sin dictado seguro).
"""


def _precargar():
    try:
        from nucleo.runtime_win import precargar_msvc
        precargar_msvc()
    except Exception:
        pass


_precargar()
del _precargar
