"""
El instalador (instalador.py) ofrece todo lo que pide requirements.txt
(revisión de regresiones, anexo F: faltaban numpy, imageio-ffmpeg, pywin32 y comtypes).
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import instalador  # noqa: E402


def _requisitos() -> set:
    """Paquetes de requirements.txt que aplican a esta plataforma (sin versión)."""
    nombres = set()
    for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        paquete, _, marca = linea.partition(";")
        if "win32" in marca and sys.platform != "win32":
            continue
        nombres.add(re.split(r"[<>=!~ \[]", paquete.strip(), maxsplit=1)[0].lower())
    return nombres


def _ofrecidos(tablas) -> set:
    return {p.lower() for tabla in tablas for info in tabla.values() for p in info["modulos"].values()}


def test_el_instalador_ofrece_todo_lo_de_requirements():
    faltan = _requisitos() - _ofrecidos(instalador._tablas())
    assert not faltan, f"requirements.txt pide {sorted(faltan)} y el instalador no lo ofrece"


def test_tambien_con_las_tablas_de_respaldo():
    tablas = instalador._con_extras(instalador._NUCLEO_RESPALDO, instalador._OPCIONALES_RESPALDO)
    assert _requisitos() - _ofrecidos(tablas) == set()


def test_los_extras_no_duplican_lo_que_ya_esta():
    nucleo, opc = instalador._con_extras({"A": {"modulos": {"numpy": "numpy"}, "nota": ""}}, {})
    todos = [p for t in (nucleo, opc) for i in t.values() for p in i["modulos"].values()]
    assert todos.count("numpy") == 1 and "imageio-ffmpeg" in todos
