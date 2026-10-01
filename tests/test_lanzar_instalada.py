"""
Lanzar, relanzar y arrancar Lune desde el código y como programa instalado (11.2).

Instalada se simula con nucleo.rutas parcheado (INSTALADA=True y PROGRAMA en una carpeta
temporal con Lune.exe / LunePatata.exe de mentira): nunca se lanza nada de verdad salvo
un python -c propio para probar la espera de un PID.

- main._lanzar_patata: LunePatata.exe instalada; desde el código, la orden de siempre.
- patata.lanzar_app_qt: Lune.exe instalada, sin buscar PyQt6 ni hablar de pip.
- --esperar-pid N (nucleo/arranque) y actualizador.reiniciar(): sin carrera con la
  instancia única.
- preparar_instalada(): freeze_support, HF_HOME, carpeta de trabajo y stdout.
- AppUserModelID fijo, mutex «Lune está abierta».
- Notas de voz del bot de Telegram: PYTHON = LunePatata.exe y `-m edge_tts` en patata.
- «Instalar componentes…» y estado de los opcionales, instalada.
"""
import inspect
import json
import os
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo import arranque as ar  # noqa: E402
from nucleo import rutas  # noqa: E402
from nucleo.arranque import Opciones  # noqa: E402


@pytest.fixture
def instalada(monkeypatch, tmp_path):
    """rutas como si Lune estuviera instalada en tmp_path/programa (con sus dos .exe)."""
    programa = tmp_path / "programa"
    programa.mkdir()
    for exe in (rutas.EXE_APP, rutas.EXE_PATATA):
        (programa / exe).write_bytes(b"")
    datos = tmp_path / "datos"
    datos.mkdir()
    monkeypatch.setattr(rutas, "INSTALADA", True)
    monkeypatch.setattr(rutas, "PROGRAMA", programa)
    monkeypatch.setattr(rutas, "DATOS", datos)
    monkeypatch.setattr(rutas, "LOCAL", tmp_path / "local")
    return programa


class ProcFalso:
    def __init__(self, codigo=None):
        self.codigo = codigo

    def wait(self, timeout=None):
        if self.codigo is None:
            raise subprocess.TimeoutExpired("x", timeout)
        return self.codigo


# ── --esperar-pid (nucleo/arranque) ────────────────────────────────────────────

@pytest.mark.parametrize("argv, pid", [
    ([], 0),
    (["--esperar-pid", "123"], 123),
    (["--esperar-pid=77", "--autoinicio"], 77),
    (["--ESPERAR-PID", "9"], 9),
    (["main.py", "--esperar-pid"], 0),
    (["--esperar-pid", "abc"], 0),
    (["--esperar-pid", "-5"], 0),
    (None, 0),
])
def test_parsear_esperar_pid(argv, pid):
    assert ar.parsear_args(argv).esperar_pid == pid


def test_esperar_pid_convive_con_autoinicio():
    assert ar.parsear_args(["--autoinicio", "--esperar-pid", "5"]) == Opciones(autoinicio=True, esperar_pid=5)
    assert ar.parsear_args(["--autoinicio"]) == Opciones(autoinicio=True)


def test_sin_esperar_pid_quita_los_de_un_reinicio_anterior():
    assert ar.sin_esperar_pid(["py", "main.py", "--esperar-pid", "1", "--autoinicio", "--esperar-pid=2"]) == [
        "py", "main.py", "--autoinicio"]
    assert ar.sin_esperar_pid([]) == []


def test_esperar_a_que_muera_con_reloj_falso():
    t = {"ahora": 0.0}
    vivos = iter([True, True, False])

    def dormir(s):
        t["ahora"] += s
    assert ar.esperar_a_que_muera(4321, 10, vivo=lambda pid: next(vivos), dormir=dormir,
                                  reloj=lambda: t["ahora"]) is True
    t["ahora"] = 0.0
    assert ar.esperar_a_que_muera(4321, 1, vivo=lambda pid: True, dormir=dormir,
                                  reloj=lambda: t["ahora"]) is False
    assert 1.0 <= t["ahora"] < 1.3


def test_nunca_se_espera_a_si_mismo_ni_a_basura():
    siempre = lambda pid: True     # noqa: E731
    assert ar.esperar_a_que_muera(os.getpid(), 5, vivo=siempre) is True
    assert ar.esperar_a_que_muera(0, 5, vivo=siempre) is True
    assert ar.esperar_a_que_muera("x", 5, vivo=siempre) is True


def test_esperar_a_que_muera_un_proceso_de_verdad():
    pytest.importorskip("psutil")
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert ar.esperar_a_que_muera(p.pid, 0.3) is False          # sigue vivo
    finally:
        p.kill()                                                    # el nuestro, por su PID
        p.wait(10)
    assert ar.esperar_a_que_muera(p.pid, 5) is True


# ── preparar_instalada ─────────────────────────────────────────────────────────

def test_preparar_instalada_desde_el_codigo_no_hace_nada():
    entorno, dirs = {}, []
    assert ar.preparar_instalada(instalada=False, entorno=entorno, cambiar_dir=dirs.append,
                                 congelar=lambda: pytest.fail("no toca")) is False
    assert entorno == {} and dirs == []
    assert ar.preparar_instalada(entorno=entorno, cambiar_dir=dirs.append) is False   # rutas.INSTALADA


def test_preparar_instalada(instalada):
    entorno, dirs, congelados = {}, [], []
    falso_sys = types.SimpleNamespace(stdout=None, stderr=sys.stderr)
    assert ar.preparar_instalada(entorno=entorno, modulo_sys=falso_sys, cambiar_dir=dirs.append,
                                 congelar=lambda: congelados.append(1)) is True
    try:
        assert congelados == [1]
        assert entorno["HF_HOME"] == str(rutas.LOCAL / "cache" / "huggingface")
        assert dirs == [str(rutas.DATOS)]
        assert falso_sys.stdout is not None and falso_sys.stderr is sys.stderr
        falso_sys.stdout.write("nadie lo lee")
    finally:
        falso_sys.stdout.close()
    # Un HF_HOME tuyo se respeta.
    entorno = {"HF_HOME": "D:\\modelos"}
    ar.preparar_instalada(entorno=entorno, modulo_sys=types.SimpleNamespace(stdout=sys.stdout, stderr=sys.stderr),
                          cambiar_dir=lambda d: None, congelar=lambda: None)
    assert entorno["HF_HOME"] == "D:\\modelos"


# ── main.py ────────────────────────────────────────────────────────────────────

def _popen_que_apunta(llamadas):
    def popen(args, **kw):
        llamadas.append((list(args), kw))
        return ProcFalso()
    return popen


def test_lanzar_patata_desde_el_codigo_la_orden_de_siempre(monkeypatch):
    import main
    monkeypatch.setattr(rutas, "INSTALADA", False)
    monkeypatch.setattr(main, "_patata_ya_abierta", lambda mostrar=True: False)
    llamadas = []
    monkeypatch.setattr(subprocess, "Popen", _popen_que_apunta(llamadas))
    assert main._lanzar_patata() is True
    args, kw = llamadas[-1]
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe") and Path(exe).with_name("python.exe").exists():
        exe = str(Path(exe).with_name("python.exe"))
    assert args[0] == exe and len(args) == 2
    assert Path(args[1]) == Path(main.__file__).resolve().parent / "patata.py"
    assert Path(kw["cwd"]) == Path(main.__file__).resolve().parent


def test_lanzar_patata_instalada_abre_lunepatata_exe(monkeypatch, instalada):
    import main
    monkeypatch.setattr(main, "_patata_ya_abierta", lambda mostrar=True: False)
    llamadas = []
    monkeypatch.setattr(subprocess, "Popen", _popen_que_apunta(llamadas))
    assert main._lanzar_patata(autoinicio=True) is True
    args, kw = llamadas[-1]
    assert args == [str(instalada / "LunePatata.exe"), "--autoinicio"]
    assert kw["cwd"] == str(instalada)
    if os.name == "nt":
        assert kw["creationflags"] & subprocess.CREATE_NEW_CONSOLE
        assert kw["startupinfo"].wShowWindow == 7                  # minimizada, sin foco
    assert main._lanzar_patata() is True
    assert llamadas[-1][0] == [str(instalada / "LunePatata.exe")] and "startupinfo" not in llamadas[-1][1]
    (instalada / "LunePatata.exe").unlink()
    n = len(llamadas)
    assert main._lanzar_patata() is False and len(llamadas) == n    # sin exe: a la nativa, sin lanzar nada


def test_aumid_fijo_y_orden_del_arranque():
    import main
    pedidos = []
    shell = types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=pedidos.append)
    assert main._fijar_aumid(shell) is True
    assert pedidos == ["DiegoLizarraga.LuneCD"] and rutas.AUMID == "DiegoLizarraga.LuneCD"
    fuente = inspect.getsource(main.main)
    assert "APP_VERSION" not in fuente and "LuneCD.v" not in fuente
    assert fuente.index("preparar_instalada()") < fuente.index("QApplication(sys.argv)")
    assert fuente.index("_fijar_aumid()") < fuente.index("QApplication(sys.argv)")
    # Tras un reinicio se espera a la vieja ANTES de mirar la instancia única; el mutex, después.
    assert fuente.index("_esperar_a_la_anterior(opc)") < fuente.index("_ya_hay_una_instancia(")
    assert fuente.index("_ya_hay_una_instancia(") < fuente.index("_marcar_abierta()")


def test_esperar_a_la_anterior():
    import main
    pedidos = []
    assert main._esperar_a_la_anterior(Opciones(), esperar=lambda pid: pedidos.append(pid)) is True
    assert pedidos == []
    assert main._esperar_a_la_anterior(Opciones(esperar_pid=4321),
                                       esperar=lambda pid: pedidos.append(pid) or True) is True
    assert pedidos == [4321]
    assert main._esperar_a_la_anterior(Opciones(esperar_pid=4321), esperar=lambda pid: False) is False


def test_marcar_abierta_nunca_tumba_el_arranque(monkeypatch):
    import main
    from servicios import mutex_win
    monkeypatch.setattr(mutex_win, "marcar_abierta", lambda: (_ for _ in ()).throw(OSError("x")))
    assert main._marcar_abierta() == 0
    monkeypatch.setattr(mutex_win, "marcar_abierta", lambda: 42)
    assert main._marcar_abierta() == 42


# ── patata.py ──────────────────────────────────────────────────────────────────

def test_lanzar_app_qt_instalada_abre_lune_exe_sin_buscar_pyqt6(monkeypatch, instalada):
    import importlib.util
    import patata
    buscados = []
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre, *a: buscados.append(nombre) or real(nombre, *a))
    llamadas = []

    def popen(codigo):
        def _p(args, **kw):
            llamadas.append((list(args), kw))
            return ProcFalso(codigo)
        return _p

    assert patata.lanzar_app_qt("web", popen=popen(None), espera_s=0.01, extra=("--autoinicio",)) is True
    args, kw = llamadas[-1]
    assert args == [str(instalada / "Lune.exe"), "--autoinicio"] and kw["cwd"] == str(instalada)
    assert "PyQt6" not in buscados
    if sys.platform == "win32":
        assert kw["creationflags"] & patata._DETACHED_PROCESS
        assert kw["creationflags"] & patata._CREATE_NEW_PROCESS_GROUP
    # Murió al arrancar: la pista habla de los registros y de reinstalar, no de pip.
    with pytest.raises(RuntimeError) as e:
        patata.lanzar_app_qt("web", popen=popen(1), espera_s=0.01)
    texto = str(e.value)
    assert "reinstala" in texto and str(rutas.LOCAL / "logs") in texto
    assert "pip" not in texto and "instalar_lune" not in texto
    (instalada / "Lune.exe").unlink()
    with pytest.raises(RuntimeError, match="Lune.exe"):
        patata.lanzar_app_qt("web", popen=popen(None))


def test_lanzar_app_qt_desde_el_codigo_sigue_diciendo_pip(monkeypatch):
    import importlib.util
    import patata
    monkeypatch.setattr(rutas, "INSTALADA", False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre, *a: None)
    with pytest.raises(RuntimeError) as e:
        patata.lanzar_app_qt("web", popen=lambda *a, **k: pytest.fail("no lanza"))
    assert "pip install -r requirements.txt" in str(e.value) and "instalar_lune.bat" in str(e.value)


def test_patata_ejecuta_edge_tts_como_python_m(monkeypatch):
    import patata
    corridas = []
    antes = list(sys.argv)

    def ejecutar(nombre, run_name=None, alter_sys=False):
        corridas.append((nombre, run_name, alter_sys, list(sys.argv)))
        raise SystemExit(0)

    argv = ["-m", "edge_tts", "--text=hola", "--write-media=C:\\x\\voz.mp3"]
    assert patata._modulo_edge_tts(argv, ejecutar=ejecutar) == 0
    assert corridas == [("edge_tts", "__main__", True, ["edge_tts", "--text=hola", "--write-media=C:\\x\\voz.mp3"])]
    assert sys.argv == antes                                           # se devuelve como estaba

    def falla(nombre, **kw):
        raise SystemExit("error: argumentos")
    assert patata._modulo_edge_tts(["-m", "edge_tts"], ejecutar=falla) == 1
    assert patata._modulo_edge_tts(["-m", "edge_tts"], ejecutar=lambda n, **kw: None) == 0
    assert patata._modulo_edge_tts(["-m", "os"], ejecutar=ejecutar) is None      # solo edge_tts
    assert patata._modulo_edge_tts(["--autoinicio"], ejecutar=ejecutar) is None
    assert patata._modulo_edge_tts([], ejecutar=ejecutar) is None


def test_patata_main_atiende_edge_tts_antes_de_validar_argumentos(monkeypatch):
    import patata
    monkeypatch.setattr(patata, "_modulo_edge_tts", lambda argv: 0 if list(argv[:2]) == ["-m", "edge_tts"] else None)
    monkeypatch.setattr(patata, "_argumentos_raros", lambda argv: pytest.fail("no debía validar"))
    monkeypatch.setattr(patata, "_nueva_instancia", lambda: pytest.fail("no debía abrir patata"))
    assert patata.main(["-m", "edge_tts", "--list-voices"]) == 0


def test_patata_ayuda_instalada_nombra_el_exe(monkeypatch, capsys):
    import patata
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert patata.main(["--help"]) == 0 and "Uso: python patata.py" in capsys.readouterr().out
    monkeypatch.setattr(rutas, "INSTALADA", True)
    monkeypatch.setattr(ar, "preparar_instalada", lambda **k: True)       # sin tocar el proceso de pytest
    assert patata.main(["--help"]) == 0
    salida = capsys.readouterr().out
    assert "Uso: LunePatata.exe" in salida and "python patata.py" not in salida


def test_patata_edge_tts_de_verdad_con_help(capsys):
    pytest.importorskip("edge_tts")
    import patata
    assert patata._modulo_edge_tts(["-m", "edge_tts", "--help"]) == 0
    assert "--write-media" in capsys.readouterr().out                  # la ayuda de edge_tts


# ── actualizador ───────────────────────────────────────────────────────────────

def test_reiniciar_desde_el_codigo_pasa_esperar_pid(monkeypatch):
    from servicios import actualizador as A
    monkeypatch.setattr(rutas, "INSTALADA", False)
    monkeypatch.setattr(sys, "argv", ["C:\\Lune\\main.py", "--autoinicio", "--esperar-pid", "11"])
    llamadas, salidas = [], []
    A.reiniciar(popen=lambda orden, **kw: llamadas.append((orden, kw)), salir=salidas.append)
    orden, kw = llamadas[0]
    assert orden == [sys.executable, "C:\\Lune\\main.py", "--autoinicio", "--esperar-pid", str(os.getpid())]
    assert kw["cwd"] == str(rutas.PROGRAMA) and salidas == [0]


def test_reiniciar_instalada_no_repite_el_exe(monkeypatch, instalada):
    from servicios import actualizador as A
    exe = str(instalada / "Lune.exe")
    monkeypatch.setattr(sys, "executable", exe)
    monkeypatch.setattr(sys, "argv", [exe, "--autoinicio"])
    llamadas, salidas = [], []
    A.reiniciar(popen=lambda orden, **kw: llamadas.append((orden, kw)), salir=salidas.append)
    assert llamadas[0][0] == [exe, "--autoinicio", "--esperar-pid", str(os.getpid())]
    assert llamadas[0][1]["cwd"] == str(instalada) and salidas == [0]


def test_reiniciar_si_no_puede_lanzar_no_se_va():
    from servicios import actualizador as A
    salidas = []

    def popen(*a, **k):
        raise OSError("no")
    assert A.reiniciar(popen=popen, salir=salidas.append) is False and salidas == []


def test_estado_opcionales_instalada_sin_pip_ni_nucleo(monkeypatch):
    import importlib.util
    from servicios import actualizador as A
    monkeypatch.setattr(rutas, "INSTALADA", True)
    monkeypatch.setattr(importlib.util, "find_spec", lambda nombre, *a: None)       # falta todo
    estados = A.estado_opcionales()
    solo_nucleo = set(A.NUCLEO) - set(A.OPCIONALES)
    assert estados and not ({o["funcion"] for o in estados} & solo_nucleo)
    assert all(o["comando"] == rutas.AVISO_NO_INCLUIDO for o in estados)


# ── Bot de Telegram: notas de voz sin Python ───────────────────────────────────

def test_telegram_instalada_da_lunepatata_como_python(monkeypatch, instalada):
    pytest.importorskip("PyQt6.QtCore")
    from servicios import telegram_worker as tw
    monkeypatch.setenv("PYTHON", "C:\\otro\\python.exe")
    env = tw.TelegramBotWorker()._entorno()
    assert env["PYTHON"] == str(instalada / "LunePatata.exe")
    assert tw.TelegramBotWorker()._entorno(hijo=False)["PYTHON"] == "C:\\otro\\python.exe"   # npm: el de siempre


def test_telegram_desde_el_codigo_no_toca_python(monkeypatch):
    pytest.importorskip("PyQt6.QtCore")
    from servicios import telegram_worker as tw
    monkeypatch.setattr(rutas, "INSTALADA", False)
    monkeypatch.delenv("PYTHON", raising=False)
    assert "PYTHON" not in tw.TelegramBotWorker()._entorno()


# ── Autoinicio en la terminal ──────────────────────────────────────────────────

def test_autoinicio_en_patata_nombra_el_lanzador_que_toca():
    from servicios.sistema_terminal import _lanzador_de
    from servicios import autoinicio
    assert _lanzador_de(autoinicio) == "iniciar_lune.vbs"
    assert _lanzador_de(object()) == "el lanzador de Lune"


# ── Piel web: «Instalar componentes…» y avisos ─────────────────────────────────

@pytest.fixture
def puente(qapp, tmp_path, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({"apis": {}, "modelos": {}, "bot": {},
                                "personajes": [{"nombre": "Lune", "systemPrompt": "Eres Lune."}]}), "utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    import ui.web_bridge as wb
    from nucleo.config import Config
    from PyQt6 import sip
    voz = types.SimpleNamespace(_enabled=False, available=False, on_error=None, al_hablar=None,
                                cancelar=lambda: None, invalidar_params=lambda: None,
                                reiniciar_motor=lambda: None)
    ai = types.SimpleNamespace(providers={}, clear_history=lambda: None, reload_provider=lambda: None)
    memoria = MagicMock()
    memoria.obtener_contexto_para_prompt.return_value = ""
    b = wb.LuneBridge(config=Config(str(tmp_path / "config.json")), ai_manager=ai, memoria=memoria, voice=voz,
                      opciones_acciones={"audit_path": None, "programar": lambda s, fn: MagicMock()})
    yield b
    b.cerrar_escritorio()
    sip.delete(b)
    datos.invalidar()


def test_web_instalada_sin_instalar_componentes(monkeypatch, puente, instalada):
    avisos = []
    puente.aviso.connect(avisos.append)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("instalada no abre instalador.py"))
    assert puente.abrir_instalador() is False
    assert avisos and "pip" not in avisos[-1]
    assert json.loads(puente.get_config())["instalada"] is True


def test_web_desde_el_codigo_instalada_es_false(monkeypatch, puente):
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert json.loads(puente.get_config())["instalada"] is False


def test_web_dispositivos_audio_manda_como_instalar(monkeypatch, puente):
    from servicios import voz_entrada, voice
    monkeypatch.setattr(voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(voz_entrada, "dependencias_faltantes", lambda: ["faster-whisper"])
    monkeypatch.setattr(voz_entrada, "modelo_descargado", lambda m: False)
    monkeypatch.setattr(voice, "listar_salidas", lambda: [])
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert json.loads(puente.dispositivos_audio())["instalar"] == "pip install faster-whisper"
    monkeypatch.setattr(rutas, "INSTALADA", True)
    assert json.loads(puente.dispositivos_audio())["instalar"] == rutas.AVISO_NO_INCLUIDO
