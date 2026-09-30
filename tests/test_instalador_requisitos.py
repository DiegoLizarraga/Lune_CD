"""
El instalador (instalador.py) ofrece todo lo que pide requirements.txt
(revisión de regresiones, anexo F: faltaban numpy, imageio-ffmpeg, pywin32 y comtypes).
"""
import re
import subprocess
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


# ── Revisión final (RR8 / X5): lo que se importa arriba del todo es obligatorio ──

def _importados_arriba() -> dict:
    """{paquete pip: [archivos]} de los módulos de terceros que la app importa a nivel de
    módulo (fuera de try): sin ellos esos módulos ni cargan (numpy en bailes, mezclador…)."""
    import ast
    locales = {p.name for p in RAIZ.iterdir() if p.is_dir()} | {p.stem for p in RAIZ.glob("*.py")}
    pip = {"PyQt6": "pyqt6", "numpy": "numpy", "requests": "requests", "urllib3": "requests",
           "websockets": "websockets"}
    archivos = [*RAIZ.glob("*.py")] + [f for d in ("nucleo", "servicios", "lune_core", "ui")
                                       for f in (RAIZ / d).rglob("*.py")]
    salida = {}
    for f in archivos:
        for n in ast.parse(f.read_text("utf-8")).body:
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods = [n.module]
            else:
                continue
            for m in mods:
                top = m.split(".")[0]
                if top in sys.stdlib_module_names or top in locales or top == "__future__":
                    continue
                assert top in pip, f"{f.name} importa {top} arriba del todo: añádelo al núcleo del instalador"
                salida.setdefault(pip[top], []).append(f.name)
    return salida


def test_lo_que_la_app_importa_arriba_del_todo_va_en_el_nucleo():
    importados = _importados_arriba()
    assert "numpy" in importados                            # bailes, pulso, mezclador, canción
    for tablas in (instalador._tablas(),
                   instalador._con_extras(instalador._NUCLEO_RESPALDO, instalador._OPCIONALES_RESPALDO)):
        nucleo = _ofrecidos([tablas[0]])
        faltan = set(importados) - nucleo
        assert not faltan, f"{sorted(faltan)} se importan al cargar y el instalador no los marca: {importados}"
        for p in ("sounddevice", "imageio-ffmpeg"):         # mezclador y mp3/ogg de alarmas y bailes
            assert p in nucleo
        if sys.platform == "win32":
            assert {"comtypes", "pywin32"} <= nucleo         # detector de música, asistente fantasma


def test_los_extras_del_nucleo_suben_al_nucleo_aunque_esten_como_opcionales():
    nucleo, opc = instalador._con_extras({}, {"Sprites": {"modulos": {"numpy": "numpy"}, "nota": ""}})
    assert "numpy" in _ofrecidos([nucleo])                  # antes se quedaba solo en opcional


def test_node_se_avisa_como_requisito_externo():
    def correr(version):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=version + "\n")

    sin = instalador.estado_node(which=lambda n: None)
    assert sin["ok"] is False and "nodejs.org" in sin["mensaje"] and "Telegram" in sin["mensaje"]
    viejo = instalador.estado_node(which=lambda n: "C:/node/node.exe", ejecutar=correr("v16.20.2"))
    assert viejo["ok"] is False and "v16.20.2" in viejo["mensaje"]
    bueno = instalador.estado_node(which=lambda n: "C:/node/node.exe", ejecutar=correr("v24.19.0"))
    assert bueno == {"ok": True, "version": "v24.19.0",
                     "mensaje": "Node.js v24.19.0: OK (bots de Telegram y Minecraft)."}
