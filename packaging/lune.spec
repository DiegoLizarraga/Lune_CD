# -*- mode: python ; coding: utf-8 -*-
"""
packaging/lune.spec — Cómo PyInstaller empaqueta Lune: UNA carpeta con DOS exe.

    dist/Lune CD/
      Lune.exe          las ventanas (main.py; sin consola)
      LunePatata.exe    la terminal (patata.py; con consola)
      _internal/        lo que comparten: Python, las librerías, Qt y lo que trae Lune
                        (ui_web/, assets/, fonts/, lune_face/, sonidos/default/…), con la
                        misma estructura que el repo (nucleo/rutas.py: RECURSOS = _internal)

No se usa a mano: packaging/construir.py prepara la copia limpia (build/fuente, sacada de
git ls-files, sin tus datos ni node_modules), la pasa en LUNE_FUENTE y llama a PyInstaller
con este archivo. Lo que hay aquí sale de la auditoría del empaquetado (11.2):

  · Cada exe lleva su PYZ; COLLECT junta binarios y datos sin repetirlos.
  · hiddenimports: lo que se importa con una cadena (importlib) y las extensiones Cython de
    zeroconf, que se importan entre sí desde C. LunePatata además lleva todo lo que
    comprueba `--comprobar` (servicios/diagnostico.modulos_empaquetados).
  · faster_whisper trae el VAD (silero_vad_v6.onnx) como dato y ctranslate2 carga sus DLL a
    mano: ningún hook los recoge.
  · Fuera: otros bindings de Qt (PyQt5/PySide: pyi_rth_pyqt6 aborta si ve dos), tkinter,
    IPython, pandas, scipy, pytest, torch…
  · MSVCP140 (el crash del dictado, nucleo/runtime_win.py): se quitan las msvcp140*/
    vcruntime140*/concrt140 de PyQt6/Qt6/bin (la 14.26 de 2020), en la raíz de _internal va
    UNA copia nueva de cada una (las de System32 de quien construye) y Lune.exe lleva el
    runtime hook rth_msvc.py, que precarga el runtime nuevo ANTES que pyi_rth_pyqt6.
  · LunePatata.exe no carga Qt al arrancar: se le quita pyi_rth_pyqt6 (Qt solo entra si
    `--comprobar` lo importa, y entonces ya se precargó el runtime).
  · De WebEngine solo quedan los idiomas es y en (qtwebengine_locales y translations).
  · optimize=0: con 2 se van los docstrings y /ayuda de patata sale de __doc__.
  · upx=False: UPX rompe DLL de Qt y de ctranslate2 y dispara los antivirus.
"""
import importlib.util
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (collect_data_files, collect_dynamic_libs,
                                     collect_submodules, copy_metadata)
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                 StringTable, VarFileInfo, VarStruct,
                                                 VSVersionInfo)

AQUI = Path(SPECPATH).resolve()
REPO = AQUI.parent
FUENTE = Path(os.environ.get("LUNE_FUENTE") or REPO / "build" / "fuente").resolve()
if not (FUENTE / "main.py").is_file() or not (FUENTE / "patata.py").is_file():
    raise SystemExit(f"No encuentro la copia a empaquetar en {FUENTE}. Usa: python packaging/construir.py")

NOMBRE_CARPETA = "Lune CD"
EXE_APP = "Lune"              # nucleo/rutas.EXE_APP = "Lune.exe"
EXE_PATATA = "LunePatata"     # nucleo/rutas.EXE_PATATA = "LunePatata.exe"
ICONO = str(FUENTE / "assets" / "lune_icon.ico")

# ── Versión (version.py manda: el recurso de versión de los exe dice lo mismo) ────
_texto_version = (FUENTE / "version.py").read_text(encoding="utf-8")
VERSION = re.search(r"""^APP_VERSION\s*=\s*["']([^"']+)["']""", _texto_version, re.M).group(1)
_numeros = [int(n) for n in re.findall(r"\d+", VERSION)][:4]
VERSION_WIN = tuple((_numeros + [0, 0, 0, 0])[:4])


def info_version(descripcion, archivo):
    texto = ".".join(map(str, VERSION_WIN))
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_WIN, prodvers=VERSION_WIN, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("080A04B0", [          # español de México, Unicode
                StringStruct("CompanyName", "Lune CD"),
                StringStruct("FileDescription", descripcion),
                StringStruct("FileVersion", texto),
                StringStruct("InternalName", Path(archivo).stem),
                StringStruct("LegalCopyright", "Diego Lizarraga"),
                StringStruct("OriginalFilename", archivo),
                StringStruct("ProductName", "Lune CD"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x080A, 1200])]),
        ],
    )


# ── Lo que trae Lune (misma estructura que el repo) ───────────────────────────────
_CARPETAS = ("ui_web", "assets", "fonts", "lune_face", "sonidos", "minecraft-bot", "telegram-bot-or",
             "lune_core/web")        # esta última solo si construir.py la copió (si se alcanza)
DATOS_LUNE = [(str(FUENTE / c), c) for c in _CARPETAS if (FUENTE / c).is_dir()]
DATOS_LUNE.append((str(FUENTE / "datos.example.json"), "."))


def _opcional(fn, *args):
    """copy_metadata de algo que quizá no esté instalado: sin él, nada."""
    try:
        return fn(*args)
    except Exception:
        return []


DATOS_LIBRERIAS = (collect_data_files("faster_whisper")               # el VAD: silero_vad_v6.onnx
                   + _opcional(copy_metadata, "huggingface_hub")
                   + _opcional(copy_metadata, "hf_xet")                # si no, descarga sin xet (más lento)
                   + _opcional(copy_metadata, "tqdm"))
BINARIOS = collect_dynamic_libs("ctranslate2")                         # ctranslate2.dll, libiomp5md, cudnn


# ── Imports que PyInstaller no ve ────────────────────────────────────────────────
def _modulos_del_diagnostico():
    """servicios/diagnostico.modulos_empaquetados() de la copia (no importa nada pesado)."""
    ruta = FUENTE / "servicios" / "diagnostico.py"
    if not ruta.is_file():
        return []
    spec = importlib.util.spec_from_file_location("_lune_diagnostico_spec", ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod            # dataclasses lo busca en sys.modules
    try:
        spec.loader.exec_module(mod)
        return list(mod.modulos_empaquetados())
    finally:
        sys.modules.pop(spec.name, None)


OCULTOS = (
    collect_submodules("zeroconf") + ["ifaddr"]
    + [
        # importlib.import_module con cadena (patata.ayuda, puente_alarmas, puente_escritorio,
        # audio_sesiones y la tarjeta de comprobación): llegan también de forma estática,
        # pero por si un día dejan de hacerlo.
        "servicios.bailes_terminal", "servicios.minecraft_terminal", "nucleo.pantalla_grande",
        "nucleo.acciones_ui", "nucleo.tema", "servicios.modo_juego", "comtypes",
        "servicios.diagnostico",
    ]
    + _modulos_del_diagnostico()
)

EXCLUIDOS = [
    # Otros bindings de Qt: pyi_rth_pyqt6 ABORTA el arranque si entra más de uno.
    "PyQt5", "PyQt5.sip", "PySide2", "PySide6",
    # Solo los usa instalador.py (modo código); además se ahorra Tcl/Tk.
    "tkinter", "_tkinter", "customtkinter",
    # tqdm.auto intenta IPython; nada de esto lo usa Lune.
    "IPython", "ipykernel", "ipywidgets", "jedi", "matplotlib", "matplotlib_inline",
    "pandas", "scipy", "nltk", "pytest", "_pytest", "setuptools", "pkg_resources",
    # Opcionales que no van en la versión instalada (Kokoro, RVC).
    "torch", "torchaudio", "torchvision", "transformers", "kokoro_onnx", "rvc_python",
]

# ── Poda de binarios y datos ─────────────────────────────────────────────────────
_RUNTIME_VIEJO = re.compile(r"^(msvcp140.*|vcruntime140.*|concrt140)\.dll$", re.I)
_IDIOMAS_QT = re.compile(r"_(es|en)(_[a-z]+)?\.qm$", re.I)


def fuera_del_paquete(destino):
    """True si ese archivo (ruta de destino dentro de _internal) sobra."""
    d = destino.replace("\\", "/").lower()
    nombre = d.rsplit("/", 1)[-1]
    if d.startswith("pyqt6/qt6/bin/") and _RUNTIME_VIEJO.match(nombre):
        return True             # el runtime de C++ de 2020 que trae Qt (el crash del dictado)
    if "/qtwebengine_locales/" in d and nombre.endswith(".pak"):
        return not (nombre.startswith("es") or nombre == "en-us.pak")
    if d.startswith("pyqt6/qt6/translations/") and nombre.endswith(".qm"):
        return not _IDIOMAS_QT.search(nombre)
    return False


def podar(toc):
    return [e for e in toc if not fuera_del_paquete(e[0])]


# Las copias de Qt eran las ÚNICAS msvcp140_1/_2 del paquete (Qt6Core, Qt6Gui y onnxruntime
# las piden): sin ellas, en un Windows sin el Visual C++ Redistributable Lune no arrancaría.
# Van todas en la raíz de _internal, sacadas del System32 del equipo que construye (≥ 14.40).
RUNTIME_CPP = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll")
SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"


def con_runtime_cpp(toc):
    en_raiz = {e[0].lower() for e in toc if "/" not in e[0].replace("\\", "/")}
    extra = [(n, str(SYSTEM32 / n), "BINARY") for n in RUNTIME_CPP
             if n not in en_raiz and (SYSTEM32 / n).is_file()]
    return list(toc) + extra


comunes = dict(
    pathex=[str(FUENTE)],
    binaries=BINARIOS,
    hookspath=[],
    hooksconfig={},
    excludes=EXCLUIDOS,
    noarchive=False,
    optimize=0,
)

a_lune = Analysis(
    [str(FUENTE / "main.py")],
    datas=DATOS_LUNE + DATOS_LIBRERIAS,
    hiddenimports=OCULTOS,
    runtime_hooks=[str(AQUI / "rth_msvc.py")],     # ANTES que pyi_rth_pyqt6
    **comunes,
)
a_patata = Analysis(
    [str(FUENTE / "patata.py")],
    datas=DATOS_LIBRERIAS,                          # lo de Lune ya va en a_lune (COLLECT lo junta)
    # «LunePatata.exe -m edge_tts …» (notas de voz del bot de Telegram): runpy busca __main__.
    hiddenimports=OCULTOS + ["edge_tts.__main__", "edge_tts.util"],
    runtime_hooks=[],
    **comunes,
)

for a in (a_lune, a_patata):
    a.binaries = con_runtime_cpp(podar(a.binaries))
    a.datas = podar(a.datas)

# La terminal no arranca Qt: fuera el runtime hook de PyQt6 (importaría QtCore al abrir).
a_patata.scripts = [s for s in a_patata.scripts if s[0] != "pyi_rth_pyqt6"]

pyz_lune = PYZ(a_lune.pure)
pyz_patata = PYZ(a_patata.pure)

exe_lune = EXE(
    pyz_lune,
    a_lune.scripts,
    [],
    exclude_binaries=True,
    name=EXE_APP,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=ICONO,
    version=info_version("Lune CD", EXE_APP + ".exe"),
    contents_directory="_internal",
)
exe_patata = EXE(
    pyz_patata,
    a_patata.scripts,
    [],
    exclude_binaries=True,
    name=EXE_PATATA,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=ICONO,
    version=info_version("Lune CD (terminal)", EXE_PATATA + ".exe"),
    contents_directory="_internal",
)

coll = COLLECT(
    exe_lune,
    a_lune.binaries,
    a_lune.datas,
    exe_patata,
    a_patata.binaries,
    a_patata.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NOMBRE_CARPETA,
)
