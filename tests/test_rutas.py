"""
Tests de nucleo/rutas.py (dónde vive cada cosa de Lune) y de que los módulos que
escriben datos del usuario cuelgan de rutas.DATOS / rutas.LOCAL, nunca del repo.

conftest.py pone LUNE_CD_DATOS en una carpeta temporal antes de importar nada de
nucleo: aquí se comprueba que eso de verdad aparta TODO lo que Lune escribe.
Las funciones carpeta_datos/carpeta_local se prueban con un entorno falso y
`instalada` forzado, sin tocar el entorno del proceso.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import rutas  # noqa: E402


# ── carpeta_datos / carpeta_local ─────────────────────────────────────────────

def test_desde_el_codigo_datos_y_local_son_la_raiz_del_repo():
    assert rutas.carpeta_datos({}, instalada=False) == RAIZ
    assert rutas.carpeta_local({}, instalada=False) == RAIZ
    # APPDATA y LOCALAPPDATA no pintan nada desde el código
    entorno = {"APPDATA": "C:/Roaming", "LOCALAPPDATA": "C:/Local"}
    assert rutas.carpeta_datos(entorno, instalada=False) == RAIZ
    assert rutas.carpeta_local(entorno, instalada=False) == RAIZ


def test_instalada_datos_en_appdata_y_local_en_localappdata(tmp_path):
    entorno = {"APPDATA": str(tmp_path / "Roaming"), "LOCALAPPDATA": str(tmp_path / "Local")}
    assert rutas.carpeta_datos(entorno, instalada=True) == tmp_path / "Roaming" / "Lune CD"
    assert rutas.carpeta_local(entorno, instalada=True) == tmp_path / "Local" / "Lune CD"
    assert rutas.NOMBRE_CARPETA_DATOS == "Lune CD"


def test_instalada_sin_variables_cae_en_el_perfil():
    assert rutas.carpeta_datos({}, instalada=True) == Path.home() / "AppData" / "Roaming" / "Lune CD"
    assert rutas.carpeta_local({"APPDATA": "  "}, instalada=True) == Path.home() / "AppData" / "Local" / "Lune CD"


@pytest.mark.parametrize("instalada", [False, True])
def test_lune_cd_datos_fuerza_las_dos(tmp_path, instalada):
    forzada = tmp_path / "portatil"
    entorno = {rutas.VARIABLE_DATOS: str(forzada), "APPDATA": "C:/Roaming", "LOCALAPPDATA": "C:/Local"}
    assert rutas.carpeta_datos(entorno, instalada=instalada) == forzada.resolve()
    assert rutas.carpeta_local(entorno, instalada=instalada) == forzada.resolve()
    assert not forzada.exists(), "calcular la ruta no crea la carpeta"


def test_lune_cd_datos_vacia_no_cuenta(tmp_path):
    entorno = {rutas.VARIABLE_DATOS: "   ", "APPDATA": str(tmp_path)}
    assert rutas.carpeta_datos(entorno, instalada=True) == tmp_path / "Lune CD"
    assert rutas.carpeta_datos(entorno, instalada=False) == RAIZ


def test_en_los_tests_datos_y_local_son_la_carpeta_temporal():
    temporal = Path(os.environ[rutas.VARIABLE_DATOS]).resolve()
    assert rutas.DATOS == temporal and rutas.LOCAL == temporal
    assert rutas.DATOS.is_dir()
    assert rutas.RECURSOS == rutas.CODIGO == RAIZ          # desde el código
    assert not rutas.INSTALADA and rutas.PROGRAMA == RAIZ


def test_recurso_dato_local():
    assert rutas.recurso("ui_web", "index.html") == RAIZ / "ui_web" / "index.html"
    assert rutas.recurso() == rutas.RECURSOS
    assert rutas.dato("chats") == rutas.DATOS / "chats"
    assert rutas.dato("cache", "bailes") == rutas.DATOS / "cache" / "bailes"
    assert rutas.local("logs", "audit.jsonl") == rutas.LOCAL / "logs" / "audit.jsonl"
    assert rutas.recurso("datos.example.json").is_file()


# ── como_instalar ─────────────────────────────────────────────────────────────

def test_como_instalar_desde_el_codigo_da_la_orden_de_pip(monkeypatch):
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert rutas.como_instalar("kokoro-onnx") == "pip install kokoro-onnx"
    assert rutas.como_instalar("a", "", "b") == "pip install a b"


def test_como_instalar_instalada_no_habla_de_pip(monkeypatch):
    monkeypatch.setattr(rutas, "INSTALADA", True)
    texto = rutas.como_instalar("kokoro-onnx")
    assert texto == rutas.AVISO_NO_INCLUIDO and "pip" not in texto


# ── Órdenes para lanzar Lune ──────────────────────────────────────────────────

def test_ordenes_desde_el_codigo():
    app = rutas.orden_app("--autoinicio")
    assert app[1:] == [str(RAIZ / "main.py"), "--autoinicio"]
    assert Path(app[0]).name.lower() in ("pythonw.exe", Path(sys.executable).name.lower())
    patata = rutas.orden_patata()
    assert patata[1:] == [str(RAIZ / "patata.py")]
    assert Path(patata[0]).name.lower() in ("python.exe", Path(sys.executable).name.lower())
    assert rutas.orden_reinicio() == [sys.executable, *sys.argv]


def test_ordenes_instalada(monkeypatch, tmp_path):
    monkeypatch.setattr(rutas, "INSTALADA", True)
    monkeypatch.setattr(rutas, "PROGRAMA", tmp_path)
    assert rutas.orden_app("--autoinicio") == [str(tmp_path / rutas.EXE_APP), "--autoinicio"]
    assert rutas.orden_patata() == [str(tmp_path / rutas.EXE_PATATA)]
    assert rutas.orden_reinicio() == [sys.executable, *sys.argv[1:]]
    assert rutas.EXE_APP == "Lune.exe" and rutas.EXE_PATATA == "LunePatata.exe"


# ── Nada de lo que escribe Lune cae en el repo ────────────────────────────────

def _dentro(ruta, carpeta) -> bool:
    try:
        Path(ruta).resolve().relative_to(Path(carpeta).resolve())
        return True
    except ValueError:
        return False


def test_los_modulos_migrados_escriben_en_datos_o_local():
    from nucleo import alarmas, bailes, config, conversaciones, datos, memoria, packs_sonido, utils, vrm
    from servicios import tools, voces
    from lune_core import minecraft_proceso
    from lune_core.voz import kokoro_backend

    de_datos = {
        "config.RAIZ": config.RAIZ,
        "config.RUTA_CONFIG": config.RUTA_CONFIG,
        "datos._PATH": datos._PATH,
        "memoria.MEMORIA_PATH": memoria.MEMORIA_PATH,
        "conversaciones.CHATS_DIR": conversaciones.CHATS_DIR,
        "alarmas.RUTA": alarmas.RUTA,
        "bailes.CARPETA": bailes.CARPETA,
        "vrm.CARPETA": vrm.CARPETA,
        "packs_sonido.CARPETA_SONIDOS": packs_sonido.CARPETA_SONIDOS,
        "kokoro_backend.RAIZ": kokoro_backend.RAIZ,
    }
    de_local = {
        "bailes.CACHE": bailes.CACHE,
        "voces.RUTA_CACHE": voces.RUTA_CACHE,
        "tools.AUDIT_POR_DEFECTO": tools.AUDIT_POR_DEFECTO,
        "utils.carpeta_logs()": utils.carpeta_logs(),
        "minecraft_proceso.BOT_DIR": minecraft_proceso.BOT_DIR,
    }
    for nombre, ruta in de_datos.items():
        assert _dentro(ruta, rutas.DATOS), (nombre, ruta)
        assert not _dentro(ruta, RAIZ), (nombre, ruta)
    for nombre, ruta in de_local.items():
        assert _dentro(ruta, rutas.LOCAL), (nombre, ruta)
        assert not _dentro(ruta, RAIZ), (nombre, ruta)
    # el logger global ya escribe ahí
    carpetas = [getattr(h, "carpeta", None) for h in utils.logger.logger.handlers]
    assert rutas.local("logs") in carpetas
    # la plantilla de datos.json sí es de Lune
    assert datos._EJEMPLO == RAIZ / "datos.example.json"


def test_los_modulos_de_qt_migrados(qapp):
    from servicios.telegram_worker import TelegramBotWorker
    from ui import lune_face, servidor_web

    assert TelegramBotWorker.BOT_DIR == rutas.dato("telegram-bot-or")
    assert TelegramBotWorker.BOT_ORIGEN == RAIZ / "telegram-bot-or"
    assert lune_face.PACKS_DIR == rutas.dato("lune_face", "packs")
    assert lune_face.FACE_DIR == RAIZ / "lune_face"
    assert servidor_web.RAIZ == rutas.RECURSOS and servidor_web.DIR_WEB == RAIZ / "ui_web"


def test_lune_face_crea_la_carpeta_de_packs_con_su_readme(qapp, monkeypatch, tmp_path):
    from ui import lune_face
    destino = tmp_path / "datos" / "lune_face" / "packs"
    monkeypatch.setattr(lune_face, "PACKS_DIR", destino)
    assert lune_face.listar_packs() == ["default"]
    assert destino.is_dir()
    leeme = lune_face.FACE_DIR / "packs" / "README.md"
    if leeme.is_file():
        assert (destino / "README.md").read_bytes() == leeme.read_bytes()
    (destino / "mio").mkdir()
    assert lune_face.listar_packs() == ["default", "mio"]


def test_rutas_relativas_al_cwd_ya_no(monkeypatch, tmp_path):
    """notas.carpeta relativa y el VRM de la red cuelgan de DATOS, no del cwd."""
    from servicios.notas_service import NotasService

    class Cfg:
        def __init__(self, carpeta):
            self.carpeta = carpeta

        def get(self, seccion, clave, defecto=None):
            return self.carpeta if (seccion, clave) == ("notas", "carpeta") else defecto

    monkeypatch.chdir(tmp_path)
    assert NotasService(Cfg("notas")).carpeta() == rutas.DATOS / "notas"
    assert NotasService(Cfg("")).carpeta() == rutas.DATOS / "notas"
    otra = tmp_path / "mis_notas"
    assert NotasService(Cfg(str(otra))).carpeta() == otra
    # voz.kokoro_carpeta («modelos_voz» de serie): la resuelve kokoro_backend contra DATOS
    from lune_core.voz import kokoro_backend
    onnx, voces = kokoro_backend._rutas("modelos_voz")
    assert onnx.parent == voces.parent == rutas.DATOS / "modelos_voz"


def test_capacidades_de_red_miran_la_carpeta_de_vrm(qapp, monkeypatch, tmp_path):
    from nucleo import vrm
    from servicios import red_service

    class Cfg:
        def get(self, seccion, clave, defecto=None):
            return defecto

    monkeypatch.chdir(tmp_path)
    (tmp_path / "modelo_vrm").mkdir()
    (tmp_path / "modelo_vrm" / "x.vrm").write_bytes(b"glTF")        # en el cwd: no cuenta
    carpeta = tmp_path / "datos_vrm"
    carpeta.mkdir()
    monkeypatch.setattr(vrm, "CARPETA", carpeta)
    svc = red_service.RedService(Cfg())
    assert "vrm" not in svc.capacidades()
    (carpeta / "lune.vrm").write_bytes(b"glTF")
    assert svc.capacidades().get("vrm") == "1"


def test_otra_carpeta_de_datos_en_un_proceso_nuevo(tmp_path):
    """Con LUNE_CD_DATOS en otra carpeta, importar nucleo copia ahí la plantilla de
    datos.json y todo apunta ahí; el repo no se entera."""
    datos_dir = tmp_path / "otra"
    codigo = (
        "import json\n"
        "from nucleo import rutas, config, datos, memoria, conversaciones, bailes, vrm\n"
        "print(json.dumps([str(rutas.DATOS), str(config.RUTA_CONFIG), str(datos._PATH),\n"
        "                  str(memoria.MEMORIA_PATH), str(conversaciones.CHATS_DIR),\n"
        "                  str(bailes.CACHE), str(vrm.CARPETA)]))\n"
    )
    env = dict(os.environ, **{rutas.VARIABLE_DATOS: str(datos_dir), "PYTHONIOENCODING": "utf-8"})
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    import json
    rutas_hijo = [Path(p) for p in json.loads(r.stdout.strip().splitlines()[-1])]
    base = datos_dir.resolve()
    assert rutas_hijo[0] == base
    assert all(_dentro(p, base) for p in rutas_hijo), rutas_hijo
    assert (base / "datos.json").is_file(), "la plantilla se copia al importar nucleo.datos"
