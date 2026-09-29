"""
El instalador para usuarios nuevos (instalar_lune.bat + instalador.py, 2026-09):
Python de verdad (no el atajo de la Microsoft Store), lo recomendado ya marcado,
cada opcional por separado (uno que falla no tumba al resto), PyQt6-WebEngine con la
versión de PyQt6, acceso directo en el escritorio y el menú Inicio, y «Abrir Lune».
Nada de esto instala ni crea nada de verdad: todo va con dobles.
"""
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import instalador as I  # noqa: E402

BAT = RAIZ / "instalar_lune.bat"
PATATA_BAT = RAIZ / "lune_patata.bat"


def _componente(nombre):
    nucleo, opcionales = I._tablas()
    return {**nucleo, **opcionales}[nombre]


# ── Lo que se marca solo ───────────────────────────────────────────────────────

def test_lo_recomendado_es_lo_de_requirements_mas_la_interfaz_completa():
    base = I.requisitos()
    assert {"pyqt6", "numpy", "edge-tts", "pypdf", "pillow"} <= base
    for nombre in ("Interfaz completa (piel web animada)", "Voz de salida (Lune habla)", "Leer PDF",
                   "Optimizador del sistema", "Comentar lo que ves en pantalla"):
        assert I.recomendado(_componente(nombre), base), nombre
    for pesado in ("Voz de entrada (dictado)", "Voz 100% local (Kokoro)", "Conversión de voz RVC (experimental)"):
        assert not I.recomendado(_componente(pesado), base), pesado


def test_aviso_de_la_version_de_python():
    assert I.aviso_python((3, 13, 1)) == "" and I.aviso_python((3, 10, 0)) == ""
    assert "3.10 o más nuevo" in I.aviso_python((3, 9, 7))
    assert "3.13" in I.aviso_python((3, 14, 0))


# ── El plan: núcleo junto, cada opcional por separado ─────────────────────────

def test_plan_pip_primero_nucleo_junto_y_opcionales_sueltos():
    a = {"modulos": {"PyQt6": "PyQt6"}, "nota": ""}
    b = {"modulos": {"numpy": "numpy"}, "nota": ""}
    c = {"modulos": {"pypdf": "pypdf"}, "nota": ""}
    d = {"modulos": {"faster_whisper": "faster-whisper"}, "nota": ""}
    pasos = I.plan_instalacion([("A", a, True), ("C", c, False), ("B", b, True), ("D", d, False)])
    assert [t for t, _i, _o in pasos] == ["pip al día", "Núcleo de Lune", "C", "D"]
    assert pasos[1][1]["modulos"] == {"PyQt6": "PyQt6", "numpy": "numpy"}


def test_webengine_va_con_la_version_de_pyqt6():
    web = {"modulos": {"PyQt6.QtWebEngineWidgets": "PyQt6-WebEngine"}}
    assert I.paquetes_para(web, "6.9.2") == ["PyQt6-WebEngine==6.9.*"]
    assert I.paquetes_para(web, "") == ["PyQt6-WebEngine"]
    assert I.paquetes_para({"modulos": {"pypdf": "pypdf"}}, "6.9.2") == ["pypdf"]


def test_si_un_opcional_falla_los_demas_siguen_y_el_resumen_lo_dice():
    ordenes = []

    def ejecutar(orden, escribir):
        ordenes.append(orden)
        return 1 if "faster-whisper" in orden else 0

    pasos = I.plan_instalacion([
        ("Núcleo", {"modulos": {"PyQt6": "PyQt6"}}, True),
        ("Dictado", {"modulos": {"faster_whisper": "faster-whisper"}}, False),
        ("PDF", {"modulos": {"pypdf": "pypdf"}}, False),
    ])
    texto = []
    hechos = I.ejecutar_plan(pasos, texto.append, ejecutar=ejecutar, pyqt=lambda: "6.9.2")
    assert hechos == {"ok": ["Núcleo de Lune", "PDF"], "fallo": ["Dictado"]}
    assert ordenes[0][-2:] == ["--upgrade", "pip"]                     # pip al día, primero
    assert any("pypdf" in o for o in ordenes)                            # siguió tras el fallo
    assert all(o[:4] == [sys.executable, "-m", "pip", "install"] for o in ordenes)


def test_webengine_sin_esa_version_exacta_prueba_la_mas_nueva():
    ordenes = []

    def ejecutar(orden, escribir):
        ordenes.append(orden[-1])
        return 1 if orden[-1].endswith(".*") else 0

    pasos = I.plan_instalacion([("Web", {"modulos": {"PyQt6.QtWebEngineWidgets": "PyQt6-WebEngine"}}, False)])
    hechos = I.ejecutar_plan(pasos, lambda t: None, ejecutar=ejecutar, pyqt=lambda: "6.9.2")
    assert ordenes[1:] == ["PyQt6-WebEngine==6.9.*", "PyQt6-WebEngine"] and hechos["ok"] == ["Web"]


def test_comprobar_nucleo():
    bien = I.comprobar_nucleo(ejecutar=lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    assert bien[0] is True
    mal = I.comprobar_nucleo(ejecutar=lambda *a, **k: subprocess.CompletedProcess(
        a, 1, "", "Traceback…\nModuleNotFoundError: No module named 'numpy'"))
    assert mal[0] is False and "numpy" in mal[1]


# ── Acceso directo y «Abrir Lune» ─────────────────────────────────────────────

def test_el_acceso_directo_abre_el_vbs_con_el_icono_y_escapa_las_comillas():
    raiz = Path(r"C:\Users\O'Brien)\Lune_CD")
    ps = I.orden_accesos_directos(raiz)
    assert ps.count("CreateShortcut") == 2 and "'Desktop'" in ps and "'Programs'" in ps
    assert "'Lune CD.lnk'" in ps and "wscript.exe" in ps
    assert "O''Brien)" in ps and "O'Brien)" not in ps.replace("O''Brien)", "")   # ' escapada
    assert '"C:\\Users\\O\'\'Brien)\\Lune_CD\\iniciar_lune.vbs"' in ps           # el .vbs entre comillas
    assert "lune_icon.ico" in ps
    solo = I.orden_accesos_directos(raiz, escritorio=True, menu_inicio=False)
    assert solo.count("CreateShortcut") == 1 and "'Programs'" not in solo


def test_crear_accesos_directos_llama_a_powershell(monkeypatch):
    monkeypatch.setattr(I.sys, "platform", "win32")
    llamadas = []

    def ejecutar(orden, **k):
        llamadas.append(orden)
        return subprocess.CompletedProcess(orden, 0, "", "")

    ok, texto = I.crear_accesos_directos(Path("C:/Lune"), ejecutar=ejecutar)
    assert ok and "escritorio" in texto and "menú Inicio" in texto
    assert llamadas[0][0] == "powershell" and "-NoProfile" in llamadas[0]
    monkeypatch.setattr(I.sys, "platform", "linux")
    assert I.crear_accesos_directos(Path("/lune"), ejecutar=ejecutar)[0] is False
    assert len(llamadas) == 1


def test_abrir_lune_usa_el_mismo_lanzador_que_el_acceso_directo(monkeypatch):
    lanzado = []
    monkeypatch.setattr(I.sys, "platform", "win32")
    I.abrir_lune(Path("C:/Lune"), lanzar=lambda orden, **k: lanzado.append(orden))
    assert lanzado[0][0] == "wscript.exe" and lanzado[0][1].endswith("iniciar_lune.vbs")


# ── Los .bat ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bat", [BAT, PATATA_BAT])
def test_los_bat_prueban_que_python_ejecuta_de_verdad(bat):
    """«where python» encontraba el atajo de la Microsoft Store (no ejecuta nada) y se
    daba por bueno. Ahora cada candidato tiene que correr y ser 3.10 o más nuevo."""
    texto = bat.read_text("ascii")
    assert "sys.version_info >= (3, 10)" in texto and ":buscar_python" in texto
    assert "where python" not in texto
    assert "LOCALAPPDATA%\\Programs\\Python\\Python%%V\\python.exe" in texto


@pytest.mark.parametrize("lanzador", ["instalar_lune.bat", "lune_patata.bat", "iniciar_lune.vbs"])
def test_los_lanzadores_van_con_crlf(lanzador):
    """Con solo LF, cmd.exe puede no encontrar las etiquetas (call :buscar_python)."""
    datos = (RAIZ / lanzador).read_bytes()
    assert datos.count(b"\n") == datos.count(b"\r\n") > 0
    assert "*.bat text eol=crlf" in (RAIZ / ".gitattributes").read_text("utf-8")


def test_el_instalador_ofrece_python_con_winget_y_se_arregla_sin_pip_ni_tkinter():
    texto = BAT.read_text("ascii")
    assert "winget install -e --id Python.Python.3.13 --scope user" in texto
    assert "choice /c SN" in texto                        # se pregunta antes de instalar
    assert "ensurepip" in texto and "import tkinter" in texto
    assert "pip install -r requirements.txt" in texto     # sin ventana: lo básico en la consola
    assert "python.org/downloads" in texto


def test_el_vbs_encuentra_el_python_que_instala_winget():
    vbs = (RAIZ / "iniciar_lune.vbs").read_text("latin-1")
    assert "Programs\\Python\\Python313\\pythonw.exe" in vbs      # el de winget --scope user
    assert "Python314" in vbs and "Python310" in vbs


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe solo en Windows")
def test_el_bat_en_modo_probar_elige_un_python_que_funciona():
    r = subprocess.run(f'cmd /c ""{BAT}" /probar"', capture_output=True, text=True, timeout=120)
    linea = [x for x in r.stdout.splitlines() if x.startswith("python=")]
    assert r.returncode == 0 and linea, r.stdout + r.stderr
    elegido = linea[0][len("python="):].strip()
    assert elegido, "no encontró ningún Python"
    prueba = subprocess.run(f'{elegido} -c "import sys; print(sys.version_info >= (3, 10))"',
                            capture_output=True, text=True, timeout=60, shell=True)
    assert prueba.stdout.strip() == "True"
