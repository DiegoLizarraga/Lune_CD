"""
Instalación y lanzamiento del bot de Telegram (servicios/telegram_worker.py), con el
mismo endurecimiento que el bot de Minecraft (revisión final, SS4):

  · `npm ci --omit=optional --ignore-scripts --no-audit --no-fund` con el
    package-lock.json del repo (antes `npm install` con shell, sin lockfile ni
    --ignore-scripts); sin lockfile no instala.
  · npm como `node <npm-cli.js>` SIN shell (o el npm del PATH), sin NODE_OPTIONS ni
    LUNE_* heredadas, con tope de tiempo; stop() mata el árbol de npm y el bot ya
    no se lanza.
  · Si node_modules/grammy ya está, no se toca (el bot sigue arrancando).
  · El lockfile commiteado: todo de registry.npmjs.org, sha512 y sin installScripts.

NADA de npm real: el «npm» es un python que duerme (y lanza un nieto, para ver que se
mata el árbol entero) o un doble.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("PyQt6.QtCore")

from servicios import telegram_worker as tw  # noqa: E402

NPM_FALSO = r"""
import json, os, subprocess, sys, time
d = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(d, "llamada.json"), "w", encoding="utf-8") as f:
    json.dump({"args": sys.argv[1:], "cwd": os.getcwd(),
               "node_options": os.environ.get("NODE_OPTIONS"),
               "lune": sorted(k for k in os.environ if k.upper().startswith("LUNE_")),
               "stdin_tty": sys.stdin is not None and sys.stdin.isatty()}, f)
modo = open(os.path.join(d, "modo.txt"), encoding="utf-8").read().strip()
if modo == "ok":
    g = os.path.join(os.getcwd(), "node_modules", "grammy")
    os.makedirs(g, exist_ok=True)
    open(os.path.join(g, "package.json"), "w").write("{}")
    print("added 10 packages")
    sys.exit(0)
if modo == "falla":
    print("npm ERR! code EINTEGRITY")
    sys.exit(1)
# «colgado»: un nieto (como npm → node) y los dos duermen
nieto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
with open(os.path.join(d, "pids.txt"), "w") as f:
    f.write(f"{os.getpid()} {nieto.pid}")
time.sleep(120)
"""


@pytest.fixture
def npm_falso(tmp_path, monkeypatch):
    """Carpeta del bot con lockfile y un «npm» que es python (modo ok/falla/colgado)."""
    bot = tmp_path / "bot"
    bot.mkdir()
    (bot / "package-lock.json").write_text("{}", "utf-8")
    herramientas = tmp_path / "npm"
    herramientas.mkdir()
    script = herramientas / "npm_falso.py"
    script.write_text(NPM_FALSO, "utf-8")
    monkeypatch.setattr(tw, "comando_npm", lambda node, which=None: [sys.executable, str(script)])
    monkeypatch.setenv("NODE_OPTIONS", "--require=C:/malo.js")
    monkeypatch.setenv("LUNE_ORDENES_TOKEN", "heredado")

    def modo(m):
        (herramientas / "modo.txt").write_text(m, "utf-8")

    def llamada():
        return json.loads((herramientas / "llamada.json").read_text("utf-8"))

    def pids():
        f = herramientas / "pids.txt"
        return [int(x) for x in f.read_text().split()] if f.exists() else []

    return bot, modo, llamada, pids


def _worker(bot):
    w = tw.TelegramBotWorker(ordenes=True)
    w.BOT_DIR = bot
    w._node = "node"
    logs, parados = [], []
    w.log_signal.connect(logs.append)
    w.stopped.connect(lambda: parados.append(1))
    return w, logs, parados


def _vivo(pid):
    psutil = pytest.importorskip("psutil")
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _limpiar(pids):
    try:
        import psutil
    except ImportError:
        return
    for pid in pids:
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass


class _LanzaSoloNpm:
    """Popen real para npm (y para el taskkill de matar_arbol, que va por subprocess.run);
    el bot (`node bot.js`) es un doble. `llamadas`: npm y bot, en orden."""
    def __init__(self):
        self.real = subprocess.Popen
        self.llamadas = []

    def __call__(self, args, **kw):
        if list(args)[:1] == ["taskkill"]:
            return self.real(args, **kw)
        self.llamadas.append((list(args), kw))
        if list(args)[-1:] != ["bot.js"]:
            return self.real(args, **kw)
        p = MagicMock()
        p.stdout = iter(())
        p.poll.return_value = 0
        p.wait.return_value = 0
        return p


def test_instala_con_npm_ci_lockfile_sin_shell_y_luego_lanza_node(qapp, npm_falso, monkeypatch):
    bot, modo, llamada, _pids = npm_falso
    modo("ok")
    popen = _LanzaSoloNpm()
    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w, logs, parados = _worker(bot)
    w.run()
    (args_npm, kw_npm), (args_bot, kw_bot) = popen.llamadas
    assert args_npm[2:] == ["ci", "--omit=optional", "--ignore-scripts", "--no-audit", "--no-fund"]
    assert not kw_npm.get("shell") and kw_npm["stdin"] is subprocess.DEVNULL
    hecho = llamada()
    assert hecho["args"] == list(tw.ARGS_NPM_CI) and Path(hecho["cwd"]) == bot
    assert hecho["node_options"] is None and hecho["lune"] == []   # nada heredado
    assert args_bot == ["node", "bot.js"] and not kw_bot.get("shell")
    assert "NODE_OPTIONS" not in kw_bot["env"] and kw_bot["env"][tw.ENV_TOKEN] == w._token
    assert "Instalando dependencias (npm ci)..." in logs and parados == [1]


def test_stop_durante_la_instalacion_mata_el_arbol_de_npm_y_no_lanza(qapp, npm_falso, monkeypatch):
    bot, modo, _llamada, pids = npm_falso
    modo("colgado")
    monkeypatch.setattr(tw, "TIMEOUT_INSTALAR_S", 60)       # red de seguridad del test
    popen = _LanzaSoloNpm()
    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w, logs, parados = _worker(bot)
    vistos = []

    def parar_cuando_arranque():
        fin = time.monotonic() + 20
        while time.monotonic() < fin and len(pids()) < 2:
            time.sleep(0.05)
        vistos.extend(pids())
        w.stop()                                              # apagar el bot / cambiar de interfaz

    h = threading.Thread(target=parar_cuando_arranque, daemon=True)
    h.start()
    t0 = time.monotonic()
    try:
        w.run()
        dura = time.monotonic() - t0
        h.join(5)
        assert len(vistos) == 2, "el npm falso no arrancó"
        assert dura < 15, f"run() siguió {dura:.1f} s tras stop()"
        fin = time.monotonic() + 5
        while time.monotonic() < fin and any(_vivo(p) for p in vistos):
            time.sleep(0.05)
        assert not any(_vivo(p) for p in vistos), "npm o su hijo siguen vivos (huérfanos)"
        assert len(popen.llamadas) == 1 and parados == [1]     # el bot no se lanzó
        assert w._instalador is None
    finally:
        _limpiar(vistos or pids())


def test_npm_colgado_se_corta_por_tiempo(qapp, npm_falso, monkeypatch):
    bot, modo, _llamada, pids = npm_falso
    modo("colgado")
    monkeypatch.setattr(tw, "TIMEOUT_INSTALAR_S", 3)
    popen = _LanzaSoloNpm()
    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w, logs, parados = _worker(bot)
    try:
        t0 = time.monotonic()
        w.run()
        assert time.monotonic() - t0 < 15
        vistos = pids()
        fin = time.monotonic() + 5
        while time.monotonic() < fin and any(_vivo(p) for p in vistos):
            time.sleep(0.05)
        assert vistos and not any(_vivo(p) for p in vistos)
        assert any("tardó más de 10 minutos" in l for l in logs)
        assert len(popen.llamadas) == 1 and parados == [1]
    finally:
        _limpiar(pids())


def test_npm_que_falla_avisa_y_no_lanza(qapp, npm_falso, monkeypatch):
    bot, modo, _llamada, _pids = npm_falso
    modo("falla")
    popen = _LanzaSoloNpm()
    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    w, logs, parados = _worker(bot)
    w.run()
    assert any("npm ci falló (código 1)" in l and "EINTEGRITY" in l for l in logs)
    assert len(popen.llamadas) == 1 and parados == [1]


def test_sin_lockfile_o_sin_node_no_instala(qapp, tmp_path, monkeypatch):
    lanzados = []
    monkeypatch.setattr(tw.subprocess, "Popen", lambda *a, **k: lanzados.append(a) or MagicMock())
    monkeypatch.setattr(tw, "comando_npm", lambda node, which=None: ["npm"])
    w, logs, parados = _worker(tmp_path)                      # sin package-lock.json
    w.run()
    assert lanzados == [] and parados == [1]
    assert any("package-lock.json" in l and "versiones fijas" in l for l in logs)
    monkeypatch.setattr(tw.shutil, "which", lambda n: None)
    w2, logs2, parados2 = _worker(tmp_path)
    w2._node = None                                           # sin Node en el PATH
    w2.run()
    assert lanzados == [] and parados2 == [1] and logs2 == [tw.AVISO_SIN_NODE]


def test_con_grammy_instalado_no_toca_node_modules(qapp, tmp_path, monkeypatch):
    """Lo que ya está instalado se respeta: ni npm ci (que borraría node_modules) ni nada."""
    g = tmp_path / "node_modules" / "grammy"
    g.mkdir(parents=True)
    (g / "package.json").write_text('{"version": "1.41.1"}', "utf-8")
    marca = tmp_path / "node_modules" / "otro.txt"
    marca.write_text("x", "utf-8")
    llamadas = []

    def popen(args, **k):
        llamadas.append(list(args))
        p = MagicMock()
        p.stdout = iter(())
        p.poll.return_value = 0
        p.wait.return_value = 0
        return p

    monkeypatch.setattr(tw.subprocess, "Popen", popen)
    monkeypatch.setattr(tw, "comando_npm", lambda *a, **k: pytest.fail("no debía instalar"))
    w, _logs, _parados = _worker(tmp_path)
    w.run()
    assert llamadas == [["node", "bot.js"]] and marca.exists()


def test_una_copia_a_medias_de_node_modules_se_reinstala(qapp, tmp_path):
    """Como la de este equipo (copiada sin las carpetas lib/ y dist/): grammy está pero
    node-fetch no tiene su «main» → el bot no arrancaría → no cuenta como instalado."""
    (tmp_path / "package-lock.json").write_text(json.dumps({"packages": {
        "": {"dependencies": {"grammy": "1.41.1"}},
        "node_modules/grammy": {"version": "1.41.1"},
        "node_modules/node-fetch": {"version": "2.7.0"},
        "node_modules/ms": {"version": "2.1.3"},
        "node_modules/encoding": {"version": "0.1.13", "optional": True},   # no se instala
    }}), "utf-8")
    nm = tmp_path / "node_modules"
    for pkg, main in (("grammy", "./out/mod.js"), ("node-fetch", "lib/index.js"), ("ms", "./index")):
        (nm / pkg).mkdir(parents=True)
        (nm / pkg / "package.json").write_text(json.dumps({"main": main}), "utf-8")
    (nm / "grammy" / "out").mkdir()
    (nm / "grammy" / "out" / "mod.js").write_text("", "utf-8")
    (nm / "ms" / "index.js").write_text("", "utf-8")                     # «./index» → index.js
    w, _logs, _parados = _worker(tmp_path)
    assert w.instalado() is False                                         # falta lib/index.js
    (nm / "node-fetch" / "lib").mkdir()
    (nm / "node-fetch" / "lib" / "index.js").write_text("", "utf-8")
    assert w.instalado() is True
    (nm / "ms" / "package.json").unlink()                                 # paquete sin package.json
    assert w.instalado() is False


def test_comando_npm_usa_el_npm_cli_junto_a_node_y_si_no_el_del_path(tmp_path):
    carpeta = tmp_path / "nodejs"
    cli = carpeta / "node_modules" / "npm" / "bin" / "npm-cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", "utf-8")
    node = carpeta / "node.exe"
    node.write_text("", "utf-8")
    assert tw.comando_npm(str(node), which=lambda n: None) == [str(node), str(cli.resolve())]
    assert tw.comando_npm(str(tmp_path / "otro" / "node.exe"), which=lambda n: "C:/x/npm.cmd") == ["C:/x/npm.cmd"]
    assert tw.comando_npm(None, which=lambda n: None) is None


def test_el_lockfile_del_repo_es_de_fiar():
    """telegram-bot-or/package-lock.json: coincide con package.json (versión exacta) y todo
    viene de registry.npmjs.org con sha512 y sin scripts de instalación."""
    carpeta = RAIZ / "telegram-bot-or"
    pkg = json.loads((carpeta / "package.json").read_text("utf-8"))
    lock = json.loads((carpeta / "package-lock.json").read_text("utf-8"))
    raiz = lock["packages"][""]
    assert (lock["name"], lock["version"]) == (pkg["name"], pkg["version"])
    assert raiz["dependencies"] == pkg["dependencies"]
    for nombre, version in pkg["dependencies"].items():
        assert version[:1].isdigit(), f"{nombre}: versión exacta, no un rango ({version})"
        assert lock["packages"][f"node_modules/{nombre}"]["version"] == version
    paquetes = {k: v for k, v in lock["packages"].items() if k}
    assert paquetes
    for k, v in paquetes.items():
        assert v["resolved"].startswith("https://registry.npmjs.org/"), k
        assert v["integrity"].startswith("sha512-"), k
        assert not v.get("hasInstallScript"), k
