"""
Tests del empaquetado (11.2) SIN construir nada: packaging/lune.spec, lune.iss, rth_msvc.py,
construir.py (con un árbol falso: nunca tus datos ni node_modules), notas_release.py,
compilar_web.mjs (con un HTML falso, por node) y el workflow de GitHub que publica.
"""
import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PK = RAIZ / "packaging"
sys.path.insert(0, str(RAIZ))

from nucleo import rutas  # noqa: E402


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


construir = _cargar("lune_pk_construir", PK / "construir.py")
notas_release = _cargar("lune_pk_notas", PK / "notas_release.py")

SPEC = (PK / "lune.spec").read_text(encoding="utf-8")
ISS_BYTES = (PK / "lune.iss").read_bytes()
ISS = ISS_BYTES.decode("utf-8-sig").replace("\r\n", "\n")        # en GitHub el checkout trae CRLF
RELEASE = (RAIZ / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
GUID = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")


# ── lune.spec ───────────────────────────────────────────────────────────────────

def test_el_spec_tiene_lo_esencial():
    for trozo in ('"main.py"', '"patata.py"', "console=False", "console=True", "upx=False", "optimize=0",
                  "rth_msvc.py", 'collect_submodules("zeroconf")', '"ifaddr"', 'collect_data_files("faster_whisper")',
                  'collect_dynamic_libs("ctranslate2")', 'copy_metadata, "huggingface_hub"', '"hf_xet"', '"tqdm"',
                  '"edge_tts.util"', '"edge_tts.__main__"', "lune_icon.ico", "COLLECT(", "contents_directory=\"_internal\"",
                  "pyi_rth_pyqt6", "modulos_empaquetados", "LUNE_FUENTE", "VSVersionInfo",
                  '"CompanyName", "Lune CD"', '"ProductName", "Lune CD"'):
        assert trozo in SPEC, trozo
    for excluido in ("PyQt5", "PySide6", "tkinter", "IPython", "matplotlib", "pandas", "scipy", "pytest", "torch"):
        assert f'"{excluido}"' in SPEC, excluido


def test_los_nombres_del_spec_coinciden_con_rutas():
    app = re.search(r'^EXE_APP = "([^"]+)"', SPEC, re.M).group(1)
    patata = re.search(r'^EXE_PATATA = "([^"]+)"', SPEC, re.M).group(1)
    carpeta = re.search(r'^NOMBRE_CARPETA = "([^"]+)"', SPEC, re.M).group(1)
    assert app + ".exe" == rutas.EXE_APP == construir.EXE_APP
    assert patata + ".exe" == rutas.EXE_PATATA == construir.EXE_PATATA
    assert carpeta == construir.NOMBRE_CARPETA == "Lune CD"


def test_el_spec_es_python_valido():
    ast.parse(SPEC)


def _poda():
    """fuera_del_paquete() del spec, sin PyInstaller (se sacan sus trozos con ast)."""
    arbol = ast.parse(SPEC)
    nodos = [n for n in arbol.body
             if (isinstance(n, ast.FunctionDef) and n.name == "fuera_del_paquete")
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("_RUNTIME_VIEJO", "_IDIOMAS_QT")
                                                   for t in n.targets))]
    ns = {"re": re}
    exec(compile(ast.Module(body=nodos, type_ignores=[]), "lune.spec", "exec"), ns)
    return ns["fuera_del_paquete"]


def test_la_poda_quita_el_runtime_viejo_de_qt_y_deja_el_nuevo():
    fuera = _poda()
    for d in (r"PyQt6\Qt6\bin\MSVCP140.dll", "PyQt6/Qt6/bin/msvcp140_1.dll", "PyQt6/Qt6/bin/msvcp140_2.dll",
              "PyQt6/Qt6/bin/VCRUNTIME140.dll", "PyQt6/Qt6/bin/vcruntime140_1.dll", "PyQt6/Qt6/bin/concrt140.dll"):
        assert fuera(d), d
    for d in ("msvcp140.dll", "vcruntime140.dll", "PyQt6/Qt6/bin/Qt6Core.dll", "PyQt6/Qt6/bin/QtWebEngineProcess.exe",
              "ctranslate2/ctranslate2.dll", "av.libs/msvcp140-0f2ea95580b32bcfc81c235d5751ce78.dll"):
        assert not fuera(d), d


def test_la_poda_deja_solo_espanol_e_ingles():
    fuera = _poda()
    loc = "PyQt6/Qt6/translations/qtwebengine_locales/"
    for pak in ("de.pak", "fr.pak", "zh-CN.pak", "en-GB.pak"):
        assert fuera(loc + pak), pak
    for pak in ("es.pak", "es-419.pak", "en-US.pak"):
        assert not fuera(loc + pak), pak
    assert fuera("PyQt6/Qt6/translations/qtbase_de.qm")
    assert fuera("PyQt6/Qt6/translations/qt_zh_CN.qm")
    assert not fuera("PyQt6/Qt6/translations/qtbase_es.qm")
    assert not fuera("PyQt6/Qt6/translations/qt_en.qm")
    assert not fuera("PyQt6/Qt6/resources/qtwebengine_resources.pak")


def test_el_runtime_hook_precarga_sin_importar_qt():
    texto = (PK / "rth_msvc.py").read_text(encoding="utf-8")
    assert "precargar_msvc" in texto
    ast.parse(texto)
    arbol = ast.parse(texto)
    importados = {getattr(n, "module", None) for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    importados |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    assert not any(str(m).startswith("PyQt6") for m in importados)


# ── lune.iss ────────────────────────────────────────────────────────────────────

def test_el_iss_tiene_lo_esencial():
    for trozo in ("PrivilegesRequired=lowest", r"DefaultDirName={autopf}\Lune CD", "DisableProgramGroupPage=yes",
                  "WizardStyle=modern", "ArchitecturesAllowed=x64compatible",
                  "ArchitecturesInstallIn64BitMode=x64compatible", "MinVersion=10.0", "Compression=lzma2/ultra64",
                  "SolidCompression=yes", "SetupIconFile=", r"UninstallDisplayIcon={app}\Lune.exe",
                  "VersionInfoVersion={#VersionWin}", "CloseApplications=yes", "RestartApplications=no",
                  "OutputBaseFilename=LuneCD-Setup-{#Version}", r"compiler:Languages\Spanish.isl",
                  "AppName=Lune CD", "AppVersion={#Version}", "AppPublisher=Diego Lizarraga",
                  "https://github.com/DiegoLizarraga/Lune_CD", r"{autoprograms}\Lune CD (terminal)",
                  "LunePatata.exe", 'AppUserModelID: "{#AppUserModelID}"', '"DiegoLizarraga.LuneCD"',
                  "Flags: unchecked", "postinstall skipifsilent nowait", "RELANZAR", "CheckForMutexes",
                  "InitializeSetup", "InitializeUninstall", "usPostUninstall", "MB_DEFBUTTON2",
                  r"Software\Microsoft\Windows\CurrentVersion\Run",
                  r"Explorer\StartupApproved\Run", "{userappdata}", "{localappdata}"):
        assert trozo in ISS, trozo
    assert f"'{rutas.MUTEX_ABIERTA}'" in ISS
    assert "PrivilegesRequiredOverridesAllowed" not in ISS       # sin elegir otra cosa


def test_el_iss_tiene_un_appid_fijo_y_bom():
    m = re.search(r"^AppId=\{\{(" + GUID.pattern + r")\}", ISS, re.M)
    assert m, "AppId con GUID fijo"
    assert ISS_BYTES.startswith(b"\xef\xbb\xbf")                # Inno lee UTF-8 solo con BOM (tildes)


def test_el_iss_solo_borra_run_si_apunta_a_la_instalacion():
    cuerpo = ISS.split("procedure QuitarArranqueConWindows;")[1].split("end;\n\nprocedure")[0]
    assert "Pos(Carpeta" in cuerpo and "{app}" in cuerpo
    assert cuerpo.index("Pos(Carpeta") < cuerpo.index("RegDeleteValue")


def test_el_iss_no_toca_tus_datos_sin_preguntar():
    """DelTree de tus datos solo tras el MsgBox (por defecto No) y nunca en silencio."""
    antes, despues = ISS.split("usPostUninstall")[0], ISS.split("usPostUninstall")[1]
    assert "DelTree" not in antes
    assert "not UninstallSilent" in despues.split("MsgBox")[0]
    assert despues.index("IDYES") < despues.index("DelTree")
    # [UninstallDelete] e [InstallDelete] solo tocan _internal (nunca {app} entero ni tus datos).
    for seccion in ("[UninstallDelete]", "[InstallDelete]"):
        bloque = ISS.split(seccion)[1].split("\n[")[0]
        nombres = re.findall(r'Name: "([^"]+)"', bloque)
        assert nombres == [r"{app}\_internal"], (seccion, nombres)


# ── construir.py ────────────────────────────────────────────────────────────────

ARBOL_FALSO = [
    "main.py", "patata.py", "version.py", "datos.example.json", "README.md", "requirements.txt", "pytest.ini",
    "instalador.py", "instalar_lune.bat", "iniciar_lune.vbs", "lune_patata.bat", ".gitignore",
    "datos.json", "config.json", "memoria.json", "alarmas.json",
    "nucleo/__init__.py", "nucleo/rutas.py", "nucleo/__pycache__/rutas.cpython-313.pyc",
    "servicios/__init__.py", "servicios/diagnostico.py", "ui/__init__.py", "ui/web_shell.py",
    "lune_core/__init__.py", "lune_core/hub.py", "lune_core/__main__.py", "lune_core/web_server.py",
    "lune_core/servicio_chat.py", "lune_core/web/terminal.html",
    "ui_web/_ds_bundle.js", "ui_web/styles.css", "ui_web/companion.html", "ui_web/SKILL.md", "ui_web/readme.md",
    "ui_web/_adherence.oxlintrc.json", "ui_web/_ds_manifest.json", "ui_web/thumbnail.html", "ui_web/.thumbnail",
    "ui_web/components/boton.jsx", "ui_web/guidelines/marca.html", "ui_web/ui_kits/lune-desktop/index.html",
    "ui_web/ui_kits/lune-desktop/app.jsx", "ui_web/vendor/babel.min.js", "ui_web/assets/sfx/clic.wav",
    "assets/lune_icon.ico", "assets/inicio.mp4", "fonts/SpaceGrotesk.ttf", "lune_face/lune_normal.png",
    "lune_face/packs/README.md", "sonidos/default/pack.json", "sonidos/mio/pack.json",
    "minecraft-bot/package.json", "minecraft-bot/package-lock.json", "minecraft-bot/LEEME.md",
    "minecraft-bot/.gitignore", "minecraft-bot/src/bot.js", "minecraft-bot/.instalando",
    "minecraft-bot/node_modules/mineflayer/package.json",
    "telegram-bot-or/bot.js", "telegram-bot-or/voz.js", "telegram-bot-or/package.json",
    "telegram-bot-or/package-lock.json", "telegram-bot-or/data/memoria_1.json", "telegram-bot-or/datos.json",
    "telegram-bot-or/node_modules/grammy/package.json", "telegram-bot-or/README.md",
    "tests/test_algo.py", "scripts/generar_sfx.py", ".github/workflows/tests.yml", "packaging/construir.py",
    "chats/2026.json", "notas/a.md", "bailes/baile.vmd", "modelo_vrm/lune.vrm", "logs/hoy.log", "cache/x.bin",
]

ESPERADO = {
    "main.py", "patata.py", "version.py", "datos.example.json",
    "nucleo/__init__.py", "nucleo/rutas.py", "servicios/__init__.py", "servicios/diagnostico.py",
    "ui/__init__.py", "ui/web_shell.py", "lune_core/__init__.py", "lune_core/hub.py",
    "ui_web/_ds_bundle.js", "ui_web/styles.css", "ui_web/companion.html", "ui_web/ui_kits/lune-desktop/index.html",
    "ui_web/ui_kits/lune-desktop/app.jsx", "ui_web/vendor/babel.min.js", "ui_web/assets/sfx/clic.wav",
    "assets/lune_icon.ico", "assets/inicio.mp4", "fonts/SpaceGrotesk.ttf", "lune_face/lune_normal.png",
    "lune_face/packs/README.md", "sonidos/default/pack.json",
    "minecraft-bot/package.json", "minecraft-bot/package-lock.json", "minecraft-bot/LEEME.md",
    "minecraft-bot/src/bot.js",
    "telegram-bot-or/bot.js", "telegram-bot-or/voz.js", "telegram-bot-or/package.json",
    "telegram-bot-or/package-lock.json",
}


def _arbol(raiz: Path, rutas_=ARBOL_FALSO, contenido=None):
    contenido = contenido or {}
    for r in rutas_:
        f = raiz / r
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenido.get(r, "# " + r), encoding="utf-8")
    return raiz


def test_construir_elige_bien_con_un_arbol_falso(tmp_path):
    raiz = _arbol(tmp_path / "repo")
    assert set(construir.elegir(raiz, ARBOL_FALSO)) == ESPERADO


def test_construir_copia_solo_lo_elegido(tmp_path):
    raiz = _arbol(tmp_path / "repo")
    destino = tmp_path / "build" / "fuente"
    (destino / "viejo").mkdir(parents=True)
    (destino / "viejo" / "resto.txt").write_text("de otro build", encoding="utf-8")
    elegidos = construir.elegir(raiz, ARBOL_FALSO)
    assert construir.copiar(raiz, destino, elegidos) > 0
    copiados = {p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file()}
    assert copiados == ESPERADO                                 # y lo del build anterior, fuera
    for nunca in ("datos.json", "config.json", "memoria.json", "alarmas.json"):
        assert not list(destino.rglob(nunca)), nunca
    assert not list(destino.rglob("node_modules"))


@pytest.mark.parametrize("ruta", [
    "datos.json", "config.json", "memoria.json", "alarmas.json", "ui_web/datos.json", "telegram-bot-or/datos.json",
    "telegram-bot-or/data/memoria_1.json", "minecraft-bot/node_modules/x/package.json",
    "telegram-bot-or/node_modules/grammy/bot.js", "ui_web/node_modules/a.js", "nucleo/__pycache__/a.pyc",
    "chats/x.json", "notas/n.md", "bailes/b.vmd", "modelo_vrm/a.vrm", "logs/l.log", "cache/c", "tests/test_x.py",
    "sonidos/mio/pack.json", ".env",
])
def test_nunca_entra_lo_tuyo_aunque_git_lo_liste(ruta):
    assert construir.seleccionar([ruta]) == []


def test_copiar_se_niega_con_algo_prohibido(tmp_path):
    raiz = _arbol(tmp_path / "repo", ["datos.json"])
    with pytest.raises(RuntimeError):
        construir.copiar(raiz, tmp_path / "fuera", ["datos.json"])
    assert not (tmp_path / "fuera" / "datos.json").exists()


def test_lune_core_aparte_entra_solo_si_algo_lo_importa(tmp_path):
    rutas_ = ["patata.py", "lune_core/__init__.py", "lune_core/__main__.py", "lune_core/web_server.py",
              "lune_core/servicio_chat.py", "lune_core/web/terminal.html"]
    contenido = {"patata.py": "from lune_core.web_server import ServidorWeb\n",
                 "lune_core/web_server.py": "from .servicio_chat import ServicioChat\n"}
    raiz = _arbol(tmp_path / "repo", rutas_, contenido)
    elegidos = set(construir.elegir(raiz, rutas_))
    assert {"lune_core/web_server.py", "lune_core/servicio_chat.py", "lune_core/web/terminal.html"} <= elegidos
    assert "lune_core/__main__.py" not in elegidos
    # Sin nadie que los importe, fuera.
    raiz2 = _arbol(tmp_path / "repo2", rutas_)
    assert set(construir.elegir(raiz2, rutas_)) == {"patata.py", "lune_core/__init__.py"}


def test_lo_que_no_existe_en_disco_no_se_copia(tmp_path):
    raiz = _arbol(tmp_path / "repo", ["main.py"])
    assert construir.elegir(raiz, ["main.py", "patata.py"]) == ["main.py"]


def test_con_el_repo_de_verdad():
    """La selección real (solo lista archivos de git; no lee ni copia tus datos)."""
    if not shutil.which("git"):
        pytest.skip("sin git")
    try:
        elegidos = construir.elegir(RAIZ, construir.listar_git(RAIZ))
    except subprocess.CalledProcessError:
        pytest.skip("no es un repo de git")
    for r in ("main.py", "patata.py", "version.py", "datos.example.json", "nucleo/rutas.py",
              "servicios/diagnostico.py", "ui_web/ui_kits/lune-desktop/index.html", "ui_web/vendor/babel.min.js",
              "assets/inicio.mp4", "assets/lune_icon.ico", "sonidos/default/pack.json", "minecraft-bot/src/bot.js",
              "telegram-bot-or/bot.js"):
        assert r in elegidos, r
    for r in elegidos:
        assert not construir.prohibido(r), r
        assert not r.startswith(("tests/", "scripts/", "packaging/", ".github/", "ui_web/components/")), r


def test_version_y_nombres():
    from version import APP_VERSION
    assert construir.leer_version(RAIZ) == APP_VERSION
    assert construir.version_windows("11.2") == "11.2.0.0"
    assert construir.version_windows("11.2.3") == "11.2.3.0"
    assert construir.nombre_setup("11.2") == "LuneCD-Setup-11.2.exe" == notas_release.nombre_setup("11.2")


def test_buscar_iscc_con_ruta_dada(tmp_path):
    falso = tmp_path / "ISCC.exe"
    falso.write_bytes(b"MZ")
    assert construir.buscar_iscc(str(falso)) == falso
    assert construir.buscar_iscc(str(tmp_path / "no.exe")) is None


def test_sha256_con_el_formato_de_sha256sum(tmp_path):
    setup = tmp_path / "LuneCD-Setup-11.2.exe"
    setup.write_bytes(b"hola")
    archivo = construir.escribir_sha256(setup)
    assert archivo.name == "LuneCD-Setup-11.2.exe.sha256"
    assert archivo.read_bytes() == (b"b221d9dbb083a7f33428d7c2a3c3198ae925614d70210e28716ccaa7cd4ddb79"
                                    b"  LuneCD-Setup-11.2.exe\n")


def _dist_falso(tmp_path, copias, runtime=True):
    """Un dist/Lune CD falso: con runtime=True, las cinco DLL del runtime en _internal."""
    carpeta = tmp_path / "Lune CD"
    todas = ([(f"_internal/{n}", None) for n in construir.RUNTIME_CPP] if runtime else []) + list(copias)
    for rel, origen in todas:
        f = carpeta / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if origen:
            shutil.copyfile(origen, f)
        else:
            f.write_bytes(b"MZ")
    return carpeta


def test_revisar_runtime_quiere_una_copia_de_cada_en_internal(tmp_path):
    dos = _dist_falso(tmp_path / "a", [("_internal/otra/MSVCP140.dll", None)])
    with pytest.raises(RuntimeError, match="UNA msvcp140.dll"):
        construir.revisar_runtime(dos)
    ninguna = _dist_falso(tmp_path / "b", [("_internal/python313.dll", None)], runtime=False)
    with pytest.raises(RuntimeError, match="UNA"):
        construir.revisar_runtime(ninguna)
    # Sin msvcp140_1 (la que piden Qt6Core y onnxruntime): Qt no arrancaría sin el Redistributable.
    sin_1 = _dist_falso(tmp_path / "c", [])
    (sin_1 / "_internal" / "msvcp140_1.dll").unlink()
    with pytest.raises(RuntimeError, match="msvcp140_1.dll"):
        construir.revisar_runtime(sin_1)
    # Una copia que no está en la raíz de _internal tampoco vale.
    fuera = _dist_falso(tmp_path / "d", [])
    (fuera / "_internal" / "msvcp140_2.dll").unlink()
    (fuera / "_internal" / "sub").mkdir()
    (fuera / "_internal" / "sub" / "msvcp140_2.dll").write_bytes(b"MZ")
    with pytest.raises(RuntimeError, match="msvcp140_2.dll"):
        construir.revisar_runtime(fuera)
    # Las de delvewheel (numpy.libs/msvcp140-<hash>.dll) llevan otro nombre: no cuentan.
    en_qt = _dist_falso(tmp_path / "e", [("_internal/numpy.libs/msvcp140-a4c2229b.dll", None),
                                         ("_internal/PyQt6/Qt6/bin/concrt140.dll", None)])
    with pytest.raises(RuntimeError, match="PyQt6/Qt6/bin"):
        construir.revisar_runtime(en_qt)


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_revisar_runtime_con_la_de_system32(tmp_path):
    sistema = Path(r"C:\Windows\System32\msvcp140.dll")
    if not sistema.exists():
        pytest.skip("sin msvcp140 en System32")
    from nucleo.runtime_win import version_dll
    if version_dll(str(sistema))[:2] < (14, 40):
        pytest.skip("la de este equipo es vieja")
    buena = _dist_falso(tmp_path / "b", [])
    shutil.copyfile(sistema, buena / "_internal" / "msvcp140.dll")
    assert construir.revisar_runtime(buena).startswith("_internal")
    vieja = _dist_falso(tmp_path / "v", [])                    # sin versión: 0.0
    with pytest.raises(RuntimeError, match="vieja"):
        construir.revisar_runtime(vieja)


def test_el_spec_pone_el_runtime_nuevo_en_la_raiz():
    tupla = re.search(r"^RUNTIME_CPP = \(([^)]*)\)", SPEC, re.M).group(1)
    assert set(re.findall(r'"([^"]+)"', tupla)) == set(construir.RUNTIME_CPP)
    assert "con_runtime_cpp(podar(a.binaries))" in SPEC


def test_entorno_limpio_quita_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", r"C:\algo")
    env = construir.entorno_limpio(LUNE_CD_DATOS="x")
    assert "PYTHONPATH" not in env and env["LUNE_CD_DATOS"] == "x"


# ── notas_release.py ────────────────────────────────────────────────────────────

README_FALSO = """# Lune

| Versión | Algo |
|---|---|
| **v11.2** | esta no es la tabla del historial |

## Historial de versiones

| Versión | Cambios principales |
|---|---|
| **v11.2** | **Me instalo como un programa**: `LuneCD-Setup-11.2.exe`, con `<\\|ACT\\|>` dentro. |
| **v11.1** | Migración. |
| v9.x | Red de dispositivos. |

---
"""


def test_notas_toma_la_fila_del_historial():
    assert notas_release.fila_historial(README_FALSO, "11.2").startswith("**Me instalo como un programa**")
    assert notas_release.fila_historial(README_FALSO, "11.2").endswith("dentro.")
    assert notas_release.fila_historial(README_FALSO, "9.x") == "Red de dispositivos."
    assert notas_release.fila_historial(README_FALSO, "12.0") is None
    assert notas_release.fila_historial("sin historial", "11.2") is None


def test_notas_de_una_version(tmp_path):
    sha = "a" * 64
    texto = notas_release.notas("11.2", README_FALSO, sha)
    for trozo in ("## Lune CD 11.2", "**Me instalo como un programa**", "LuneCD-Setup-11.2.exe", "SmartScreen",
                  "Más información", "Ejecutar de todas formas", "menú Inicio", "**Lune**", r"%APPDATA%\Lune CD",
                  r"%LOCALAPPDATA%\Lune CD", f"{sha}  LuneCD-Setup-11.2.exe", "Get-FileHash"):
        assert trozo in texto, trozo


def test_notas_caen_a_la_fila_de_la_serie():
    """Desde la 11 el README lleva una fila por serie («v11»), no una por versión: 11.3 sin fila propia
    usa la de su serie; la exacta, si la hay, gana."""
    serie = README_FALSO.replace("| v9.x | Red de dispositivos. |", "| **v11** | **Toda la serie 11**. |\n| v9.x | Red de dispositivos. |")
    assert notas_release.candidatas("11.3") == ["11.3", "11.x", "11"]
    assert notas_release.candidatas("v12") == ["12", "12.x"]
    assert notas_release.fila_para(serie, "11.3") == "**Toda la serie 11**."
    assert notas_release.fila_para(serie, "11.2").startswith("**Me instalo como un programa**")
    assert notas_release.fila_para(README_FALSO, "9.4") == "Red de dispositivos."
    assert notas_release.fila_para(README_FALSO, "12.0") is None
    assert "**Toda la serie 11**." in notas_release.notas("11.3", serie)


def test_notas_sin_fila_ni_hash():
    texto = notas_release.notas("12.0", README_FALSO)
    assert "Una versión nueva de Lune" in texto
    assert "LuneCD-Setup-12.0.exe.sha256" in texto


def test_leer_sha256(tmp_path):
    h = "B" * 64
    assert notas_release.leer_sha256(h, "11.2") == h.lower()
    archivo = tmp_path / "x.sha256"
    archivo.write_text(f"{'c' * 64}  LuneCD-Setup-11.2.exe\n", encoding="utf-8")
    assert notas_release.leer_sha256(str(archivo), "11.2") == "c" * 64
    assert notas_release.leer_sha256(None, "11.2", raiz=tmp_path) is None
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "LuneCD-Setup-11.2.exe.sha256").write_text(f"{'d' * 64}  x\n", encoding="utf-8")
    assert notas_release.leer_sha256(None, "11.2", raiz=tmp_path) == "d" * 64


def test_notas_main_escribe_utf8(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README_FALSO, encoding="utf-8")
    salida = tmp_path / "notas.md"
    assert notas_release.main(["11.2", "--readme", str(readme), "--sha256", "e" * 64, "-o", str(salida)]) == 0
    texto = salida.read_text(encoding="utf-8")
    assert "Cómo instalarme" in texto and "e" * 64 in texto


def test_notas_con_el_readme_de_verdad():
    """Sale algo con sentido para la versión actual (con su fila o el texto genérico)."""
    from version import APP_VERSION
    texto = notas_release.notas(APP_VERSION, (RAIZ / "README.md").read_text(encoding="utf-8"))
    assert f"## Lune CD {APP_VERSION}" in texto


# ── compilar_web.mjs (por node, con un HTML falso) ──────────────────────────────

HTML_FALSO = """<!doctype html>
<html><head>
  <script src="../../vendor/react.development.js"></script>
  <script src="../../vendor/react-dom.development.js"></script>
  <script>window.React || document.write('<script src="https://unpkg.com/react@18/umd/react.development.js"><\\/script>');</script>
  <script src="../../vendor/babel.min.js"></script>
</head><body>
  <div id="r"></div>
  <script type="text/babel" src="app.jsx"></script>
  <script type="text/babel">
    ReactDOM.createRoot(document.getElementById('r')).render(<App titulo="hola" />);
  </script>
</body></html>
"""


def test_compilar_web_con_un_html_falso(tmp_path):
    node = shutil.which("node")
    babel = RAIZ / "ui_web" / "vendor" / "babel.min.js"
    if not node or not babel.exists():
        pytest.skip("sin node o sin Babel vendorizado")
    ui = tmp_path / "ui_web"
    kit = ui / "ui_kits" / "lune-desktop"
    kit.mkdir(parents=True)
    (ui / "vendor").mkdir()
    shutil.copyfile(babel, ui / "vendor" / "babel.min.js")
    for f in ("react.development.js", "react-dom.development.js", "react.production.min.js",
              "react-dom.production.min.js"):
        (ui / "vendor" / f).write_text("//", encoding="utf-8")
    (kit / "index.html").write_text(HTML_FALSO, encoding="utf-8")
    (kit / "app.jsx").write_text("function App({ titulo, ...resto }) { return <div className=\"x\">{titulo}</div>; }\n",
                                 encoding="utf-8")
    r = subprocess.run([node, str(PK / "compilar_web.mjs"), str(ui)], capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    html = (kit / "index.html").read_text(encoding="utf-8")
    assert '<script defer src="app.js"></script>' in html
    assert '<script defer src="arranque.js"></script>' in html
    assert "react.production.min.js" in html and "react-dom.production.min.js" in html
    assert "text/babel" not in html and "babel.min.js" not in html and ".development.js" not in html
    assert "unpkg.com" not in html
    app = (kit / "app.js").read_text(encoding="utf-8")
    assert "createElement" in app and "<div" not in app
    assert "createElement" in (kit / "arranque.js").read_text(encoding="utf-8")
    assert not (ui / "vendor" / "babel.min.js").exists()
    assert not (ui / "vendor" / "react.development.js").exists()
    assert (ui / "vendor" / "react.production.min.js").exists()


# ── GitHub: release.yml, requisitos y .gitignore ────────────────────────────────

def test_el_workflow_de_release():
    for trozo in ("workflow_run:", "workflows: [Tests]", "types: [completed]", "branches: [master]",
                  "workflow_dispatch:", "contents: write", "concurrency:", "windows-latest",
                  "github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.event == 'push'",
                  "github.event.workflow_run.head_sha", "gh release view", "gh release create", "--target",
                  '--title "Lune CD $ver"', "--notes-file", "packaging/notas_release.py",
                  "packaging/requisitos-release.txt", "python packaging/construir.py", "choco install innosetup",
                  "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CURRENTUSER", "--comprobar", "unins000.exe",
                  "LUNE_CD_DATOS", ".exe.sha256", 'python-version: "3.13"'):
        assert trozo in RELEASE, trozo
    tests_yml = (RAIZ / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert re.search(r"^name:\s*Tests\s*$", tests_yml, re.M)       # el nombre que escucha workflow_run


def test_el_workflow_busca_la_entrada_de_desinstalacion_del_iss():
    appid = re.search(r"^AppId=\{\{(" + GUID.pattern + r")\}", ISS, re.M).group(1)
    assert "{" + appid + "}_is1" in RELEASE


def test_requisitos_release_con_versiones_exactas():
    lineas = [l.strip() for l in (PK / "requisitos-release.txt").read_text(encoding="utf-8").splitlines()]
    paquetes = {}
    for l in lineas:
        if not l or l.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([\w.\-]+)$", l)
        assert m, f"sin versión exacta: {l}"
        paquetes[m.group(1).lower().replace("_", "-")] = m.group(2)
    for p in ("pyinstaller", "pyinstaller-hooks-contrib", "pyqt6", "pyqt6-webengine", "faster-whisper", "ctranslate2"):
        assert p in paquetes, p
    assert paquetes["pyqt6"].split(".")[:2] == paquetes["pyqt6-webengine"].split(".")[:2]
    # Todo lo de requirements.txt va también (con su versión fija).
    for l in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        l = l.split("#")[0].strip()
        if l:
            nombre = re.split(r"[<>=!;\s\[]", l)[0].lower().replace("_", "-")
            assert nombre in paquetes, nombre


def test_gitignore_con_build_y_dist():
    lineas = {l.strip() for l in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert lineas & {"build/", "/build/"} and lineas & {"dist/", "/dist/"}
