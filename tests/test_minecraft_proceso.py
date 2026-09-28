"""
Tests de lune_core/minecraft_proceso.py: el bot de Minecraft como proceso hijo.

Nunca se lanza el bot de verdad ni npm: `popen` lanza un hijo FALSO
(`sys.executable -c …`) que habla el mismo protocolo, y `ejecutar`/`which` son dobles.
Se prueban el token al principio de la línea, el tope de 8 KB, UTF-8, que la primera
línea de stdin es la configuración, el entorno limpio, la clave del modelo fuera del
log, la parada (salir → cerrar stdin → terminate) y la instalación con los argumentos
exactos de npm ci.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import minecraft_proceso as mp  # noqa: E402

NODE = str(Path("C:/falso/node/node.exe"))

# Hijo falso: lee la configuración, cuenta cosas con líneas marcadas y hace eco de lo que
# le manda Lune. Con MODO=terco ignora «salir» y el cierre de stdin; con MODO=cierre sale
# con 7 al cerrarse stdin (y no con «salir»).
HIJO = r'''
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
tok = os.environ.get("LUNE_MC_TOKEN", "")
modo = os.environ.get("MC_MODO_PRUEBA", "")
def marca(d):
    print("@@LUNE " + tok + " " + json.dumps(d), flush=True)
cfg = json.loads(sys.stdin.readline())
lune_env = sorted(k for k in os.environ if k.upper().startswith("LUNE_"))
marca({"tipo": "listo", "cfg_tipo": cfg.get("tipo"), "nick": cfg.get("nick"), "env": lune_env,
       "hijo": os.environ.get("LUNE_BOT_HIJO"), "node_options": os.environ.get("NODE_OPTIONS")})
print("la clave es " + str((cfg.get("llm") or {}).get("clave")) + " y el token " + tok, flush=True)
print("texto @@LUNE " + tok + " " + json.dumps({"tipo": "chat"}), flush=True)
print("@@LUNE " + tok + " " + json.dumps({"tipo": "chat", "texto": "x" * 9000}), flush=True)
print("@@LUNE " + "0" * 32 + " " + json.dumps({"tipo": "chat", "de": "Malo"}), flush=True)
print("@@LUNE " + tok + " " + json.dumps({"tipo": "inventado"}), flush=True)
marca({"tipo": "chat", "de": "Steve", "texto": "hola 💎 ñandú"})
if modo == "terco":
    while True:
        time.sleep(0.2)
for linea in sys.stdin:
    m = json.loads(linea)
    marca({"tipo": "respuesta", "texto": linea.strip()})
    if m.get("tipo") == "salir" and modo != "cierre":
        sys.exit(0)
sys.exit(7 if modo == "cierre" else 0)
'''


def esperar(cond, tope=8.0):
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture
def carpeta(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bot.js").write_text("// bot", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    return tmp_path


def instalar_falso(carpeta: Path):
    p = carpeta / "node_modules" / "mineflayer"
    p.mkdir(parents=True, exist_ok=True)
    (p / "package.json").write_text("{}", encoding="utf-8")


def ejecutar_falso(version="v24.19.0", ayuda="  --permission   enable\n  --allow-fs-read=...\n", registro=None,
                   resultado=None):
    def run(args, **kw):
        if registro is not None:
            registro.append((list(args), kw))
        if args[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout=version + "\n", stderr="")
        if args[-1] == "--help":
            return SimpleNamespace(returncode=0, stdout=ayuda, stderr="")
        if callable(resultado):
            return resultado(args, **kw)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


class NpmFalso:
    """Popen de npm de mentira: communicate() devuelve lo que diga `resultado(args, **kw)`."""

    def __init__(self, args, resultado=None, **kw):
        self.args, self.kw = list(args), kw
        self.pid, self.returncode, self._r = 4242, None, resultado

    def communicate(self, timeout=None):
        r = self._r(self.args, timeout=timeout, **self.kw) if callable(self._r) else \
            SimpleNamespace(returncode=0, stdout="", stderr="")
        self.returncode = r.returncode
        return r.stdout, r.stderr

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def popen_npm(registro=None, resultado=None):
    def popen(args, **kw):
        if registro is not None:
            registro.append((list(args), kw))
        return NpmFalso(args, resultado, **kw)
    return popen


class Recogedor:
    def __init__(self):
        self.eventos, self.logs, self.fines = [], [], []

    def evento(self, m):
        self.eventos.append(m)

    def log(self, linea):
        self.logs.append(linea)

    def fin(self, codigo):
        self.fines.append(codigo)

    def tipos(self):
        return [e["tipo"] for e in self.eventos]


def proceso(carpeta, rec, *, modo="", registro=None, ayuda=None, monkeypatch=None):
    lanzados = []

    def popen(args, **kw):
        lanzados.append((list(args), dict(kw)))
        env = dict(kw.pop("env"))
        env["MC_MODO_PRUEBA"] = modo
        return subprocess.Popen([sys.executable, "-c", HIJO], env=env, **kw)
    kwargs = {} if ayuda is None else {"ayuda": ayuda}
    p = mp.ProcesoBot(carpeta, node=NODE, popen=popen, ejecutar=ejecutar_falso(registro=registro, **kwargs),
                      on_evento=rec.evento, on_log=rec.log, on_fin=rec.fin)
    return p, lanzados


CFG = {"host": "localhost", "port": 25565, "nick": "Lune", "dueno": "Diego_01",
       "llm": {"proveedor": "openrouter", "clave": "sk-or-v1-SECRETA-123456"}}


# ── Validación y configuración ─────────────────────────────────────────────────

def test_nick_y_host():
    assert mp.nick_valido("Diego_01") == "Diego_01"
    for malo in ("ab", "con espacio", "x" * 17, "Dié", None, 5.5):
        assert mp.nick_valido(malo) is None
    for h in ("localhost", "mc.example.com", "192.168.1.9", "::1"):
        assert mp.validar_host(h) == h
    for h in ("http://x", "x/y", "a b", "", "1.2.3.4:25565", None, "x" * 254):
        assert mp.validar_host(h) is None
    assert mp.nick_desde_nombre("Lúne") == "Lune"
    assert mp.nick_desde_nombre("Mi") == "Mi_bot"
    assert mp.nick_desde_nombre("") == "Lune_bot"
    assert mp.nick_desde_nombre("Una Chica Muy Larga De Nombre") == "Una_Chica_Muy_La"


def test_config_bot_pide_dueno_y_saca_el_nick_del_personaje():
    with pytest.raises(ValueError, match="dueño"):
        mp.config_bot({"dueno": ""}, {"nombre": "Lune"}, None)
    cfg = mp.config_bot({"dueno": "Diego_01", "host": "mc.local", "port": "25566", "pensar_cada_s": 5},
                        {"nombre": "Lúne", "systemPrompt": "Eres Lune."}, None)
    assert cfg["tipo"] == "config" and cfg["nick"] == "Lune" and cfg["port"] == 25566
    assert cfg["pensar_cada_s"] == 30                         # nunca por debajo de 30 s
    assert cfg["persona"]["nombre"] == "Lúne" and "Eres Lune." in cfg["persona"]["prompt"]   # el nombre, tal cual
    assert cfg["llm"] is None and cfg["solo_dueno"] is True and cfg["estilo"] == "personaje"
    assert mp.config_bot({"dueno": "Lune"}, {"nombre": "Lune"}, None)["nick"] == "Lune_bot"
    assert mp.config_bot({"dueno": "Diego_01", "usuario": "MiBot"}, {"nombre": "Lune"}, None)["nick"] == "MiBot"


@pytest.mark.parametrize("cambio,texto", [({"host": "http://x"}, "servidor"), ({"port": 0}, "puerto"),
                                          ({"version": "latest"}, "versión")])
def test_config_bot_rechaza(cambio, texto):
    with pytest.raises(ValueError, match=texto):
        mp.config_bot({"dueno": "Diego_01", **cambio}, {}, None)


def test_config_bot_persona_sin_memoria_y_con_tope():
    personaje = {"nombre": "Lune", "systemPrompt": "Hola. " * 800, "memoria": "vive en Madrid",
                 "frases_minecraft": {"muerte": ["¡Otra vez!", 3], "mal-cat": ["x"]}}
    cfg = mp.config_bot({"dueno": "Diego_01"}, personaje, None)
    assert len(cfg["persona"]["prompt"]) <= mp.MAX_PERSONA
    assert "Madrid" not in json.dumps(cfg)
    assert cfg["persona"]["frases"] == {"muerte": ["¡Otra vez!"]}


def test_config_bot_llm():
    ok = {"proveedor": "ollama", "url": "http://localhost:11434/", "modelo": "qwen", "num_ctx": 999999, "timeout_ms": 1}
    llm = mp.config_bot({"dueno": "Diego_01"}, {}, ok)["llm"]
    assert llm == {"proveedor": "ollama", "url": "http://localhost:11434", "modelo": "qwen", "clave": "",
                   "keep_alive": "30m", "num_ctx": 262144, "timeout_ms": 1000}
    for malo in ({"proveedor": "ollama", "url": "http://x", "modelo": ""}, {"proveedor": "x", "url": "http://x", "modelo": "m"},
                 {"proveedor": "ollama", "url": "file:///x", "modelo": "m"},
                 {"proveedor": "openrouter", "url": "https://openrouter.ai/api/v1", "modelo": "m", "clave": ""}):
        assert mp.config_bot({"dueno": "Diego_01"}, {}, malo)["llm"] is None


def test_config_llm_desde_datos():
    datos = SimpleNamespace(
        get_bot=lambda: {"proveedor": "ollama"}, ollama_url=lambda: "http://pc:11434", ollama_model=lambda: "qwen",
        ollama_keep_alive=lambda: "10m", ollama_num_ctx=lambda: 4096, ollama_timeout=lambda: 300,
        openrouter_model=lambda: "openrouter/auto", openrouter_key=lambda: "sk", compat_url=lambda: "localhost:1234",
        compat_model=lambda: "local", compat_key=lambda: "", compat_timeout=lambda: 60)
    assert mp.config_llm(datos) == {"proveedor": "ollama", "url": "http://pc:11434", "modelo": "qwen", "clave": "",
                                    "keep_alive": "10m", "num_ctx": 4096, "timeout_ms": 120000}
    datos.get_bot = lambda: {"proveedor": "openrouter"}
    assert mp.config_llm(datos)["url"] == mp.URL_OPENROUTER and mp.config_llm(datos)["clave"] == "sk"
    datos.get_bot = lambda: {"proveedor": "compat"}
    assert mp.config_llm(datos)["url"].startswith("http://localhost:1234")
    datos.get_bot = lambda: {"proveedor": "raro"}
    assert mp.config_llm(datos)["proveedor"] == "openrouter"


# ── Requisitos, permisos e instalación ─────────────────────────────────────────

def test_requisitos(carpeta, tmp_path):
    p = mp.ProcesoBot(carpeta, node=NODE, ejecutar=ejecutar_falso("v17.9.0"), which=lambda n: None)
    assert p.requisitos() == {"node": "v17.9.0", "node_ok": False, "npm": False, "instalado": False}
    instalar_falso(carpeta)
    p = mp.ProcesoBot(carpeta, node=NODE, ejecutar=ejecutar_falso("v24.19.0"), which=lambda n: "C:/x/npm.cmd")
    assert p.requisitos() == {"node": "v24.19.0", "node_ok": True, "npm": True, "instalado": True}
    sin = mp.ProcesoBot(carpeta, node=None, which=lambda n: None)
    assert sin.requisitos()["node"] is None and sin.requisitos()["node_ok"] is False


def test_npm_sin_shell_junto_a_node(carpeta, tmp_path):
    base = tmp_path / "nodejs"
    cli = base / "node_modules" / "npm" / "bin"
    cli.mkdir(parents=True)
    (cli / "npm-cli.js").write_text("//", encoding="utf-8")
    node = str(base / "node.exe")
    registro = []
    instalar_falso(carpeta)
    topes = []

    def npm_ok(args, timeout=None, **kw):
        topes.append(timeout)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    p = mp.ProcesoBot(carpeta, node=node, ejecutar=ejecutar_falso(), popen=popen_npm(registro, npm_ok),
                      which=lambda n: None)
    ok, texto = p.instalar()
    assert ok, texto
    args, kw = registro[-1]
    assert args == [node, str((cli / "npm-cli.js").resolve()), "ci", "--omit=optional", "--ignore-scripts",
                    "--no-audit", "--no-fund"]
    assert kw["cwd"] == str(carpeta) and topes == [900] and "shell" not in kw


def test_permisos_segun_node(carpeta):
    p = mp.ProcesoBot(carpeta, node=NODE, ejecutar=ejecutar_falso())
    assert p.permisos() == ["--permission", f"--allow-fs-read={carpeta.resolve()}"]
    p = mp.ProcesoBot(carpeta, node=NODE, ejecutar=ejecutar_falso(ayuda="  --permission\n  --allow-net   red\n"))
    assert p.permisos()[-1] == "--allow-net"
    p = mp.ProcesoBot(carpeta, node=NODE, ejecutar=ejecutar_falso(ayuda="  --experimental-permission\n"))
    assert p.permisos() == []


def test_instalar_argumentos_exactos_y_entorno_limpio(carpeta, monkeypatch):
    monkeypatch.setenv("LUNE_ORDENES_TOKEN", "no-debe-pasar")
    registro = []

    def npm_ok(args, **kw):
        instalar_falso(carpeta)
        return SimpleNamespace(returncode=0, stdout="added 93 packages", stderr="")
    p = mp.ProcesoBot(carpeta, node=NODE, npm=["npm-falso"], ejecutar=ejecutar_falso(),
                      popen=popen_npm(registro, npm_ok))
    assert p.instalar() == (True, "Bot de Minecraft instalado.")
    assert not (carpeta / mp.MARCA_INSTALANDO).exists()                     # la marca se quita al acabar
    args, kw = registro[-1]
    assert args == ["npm-falso", "ci", "--omit=optional", "--ignore-scripts", "--no-audit", "--no-fund"]
    assert not any(k.upper().startswith("LUNE_") for k in kw["env"])
    assert kw["stdin"] == subprocess.DEVNULL


def test_instalar_falla_con_las_ultimas_lineas_y_sin_lockfile(carpeta):
    def npm_mal(args, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="npm ERR! code EINTEGRITY\nnpm ERR! sha512 no coincide")
    p = mp.ProcesoBot(carpeta, node=NODE, npm=["npm"], ejecutar=ejecutar_falso(), popen=popen_npm(resultado=npm_mal))
    ok, texto = p.instalar()
    assert not ok and "EINTEGRITY" in texto and "código 1" in texto
    (carpeta / "package-lock.json").unlink()
    ok, texto = p.instalar()
    assert not ok and "package-lock" in texto
    viejo = mp.ProcesoBot(carpeta, node=NODE, npm=["npm"], ejecutar=ejecutar_falso("v16.0.0"))
    assert viejo.instalar() == (False, mp.AVISO_SIN_NODE)


def test_instalar_con_tope_de_tiempo(carpeta):
    def lento(args, **kw):
        raise subprocess.TimeoutExpired(args, kw["timeout"])
    registro = []
    p = mp.ProcesoBot(carpeta, node=NODE, npm=["npm"], ejecutar=ejecutar_falso(registro=registro),
                      popen=popen_npm(resultado=lento))
    ok, texto = p.instalar()
    assert not ok and "15 minutos" in texto
    assert p.instalando is False
    if os.name == "nt":                     # sin Job (hijo falso): taskkill del árbol por SU pid, nunca por nombre
        assert ["taskkill", "/T", "/F", "/PID", "4242"] in [a for a, _ in registro]


# ── Canal con el hijo (falso) ──────────────────────────────────────────────────

def test_arrancar_sin_instalar_o_sin_node(carpeta):
    rec = Recogedor()
    p, lanzados = proceso(carpeta, rec)
    assert p.arrancar(dict(CFG)) == (False, mp.AVISO_INSTALAR)
    assert lanzados == []
    sin = mp.ProcesoBot(carpeta, node=None, which=lambda n: None)
    assert sin.arrancar(dict(CFG)) == (False, mp.AVISO_SIN_NODE)


def test_canal_completo_con_el_hijo_falso(carpeta, monkeypatch):
    monkeypatch.setenv("LUNE_MC_TOKEN", "heredado-de-fuera")
    monkeypatch.setenv("LUNE_ALGO", "1")
    monkeypatch.setenv("NODE_OPTIONS", "--require evil.js")
    instalar_falso(carpeta)
    rec = Recogedor()
    p, lanzados = proceso(carpeta, rec)
    ok, _ = p.arrancar(dict(CFG))
    assert ok and p.vivo
    args, kw = lanzados[0]
    assert args == [NODE, "--permission", f"--allow-fs-read={carpeta.resolve()}", os.path.join("src", "bot.js")]
    assert kw["cwd"] == str(carpeta) and kw["stdin"] == subprocess.PIPE and kw["stderr"] == subprocess.STDOUT
    assert "shell" not in kw
    if os.name == "nt":
        assert kw["creationflags"] & 0x08000000
    assert esperar(lambda: "chat" in rec.tipos())
    listo, chat = rec.eventos[0], rec.eventos[1]
    # La primera línea de stdin es la configuración; el entorno es limpio.
    assert listo["tipo"] == "listo" and listo["cfg_tipo"] == "config" and listo["nick"] == "Lune"
    assert listo["env"] == ["LUNE_BOT_HIJO", "LUNE_MC_TOKEN"] and listo["hijo"] == "1"
    assert listo["node_options"] is None
    # Solo la línea marcada, con el token y ≤8 KB, de tipo conocido; UTF-8 bien.
    assert rec.tipos() == ["listo", "chat"]
    assert chat["texto"] == "hola 💎 ñandú" and chat["de"] == "Steve"
    # El log: sin la clave ni el token; la línea con la marca a mitad no aparece.
    assert any("la clave es" in l for l in rec.logs)
    assert all("SECRETA" not in l and p._token not in l for l in rec.logs)
    assert not any("@@LUNE" in l for l in rec.logs)
    # Órdenes después de la configuración, en orden.
    assert p.orden("a1", "sigueme") and p.decir("hola\na todos") and p.pausa_llm(True) and p.pausa_autonomo(False)
    assert p.pedir_estado()
    assert esperar(lambda: rec.tipos().count("respuesta") == 5)
    enviados = [json.loads(e["texto"]) for e in rec.eventos if e["tipo"] == "respuesta"]
    assert enviados == [{"tipo": "orden", "id": "a1", "texto": "sigueme"}, {"tipo": "decir", "texto": "hola a todos"},
                        {"tipo": "pausa_llm", "on": True}, {"tipo": "pausa_autonomo", "on": False}, {"tipo": "estado"}]
    assert p.orden("id malo!", "x") is False and p.enviar({"tipo": "inventado"}) is False
    p.parar()
    assert esperar(lambda: rec.fines == [0])
    assert not p.vivo
    assert p.arrancar(dict(CFG))[0] is True                   # se puede volver a lanzar (token nuevo)
    p.parar()


def test_parar_cierra_stdin_si_ignora_salir(carpeta):
    instalar_falso(carpeta)
    rec = Recogedor()
    p, _ = proceso(carpeta, rec, modo="cierre")
    p.arrancar(dict(CFG))
    assert esperar(lambda: "chat" in rec.tipos())
    t0 = time.monotonic()
    p.parar(espera_s=0.3)
    assert esperar(lambda: rec.fines == [7])                  # salió al cerrarse su stdin
    assert time.monotonic() - t0 < 5


def test_parar_termina_un_hijo_terco_e_idempotente(carpeta):
    instalar_falso(carpeta)
    rec = Recogedor()
    p, _ = proceso(carpeta, rec, modo="terco")
    p.arrancar(dict(CFG))
    assert esperar(lambda: "chat" in rec.tipos())
    t0 = time.monotonic()
    p.parar(espera_s=0.3)
    assert time.monotonic() - t0 < 8
    assert not p.vivo
    assert esperar(lambda: len(rec.fines) == 1)
    p.parar()                                                  # otra vez: nada
    assert p.enviar({"tipo": "estado"}) is False


def test_procesar_linea_sin_hijo():
    rec = Recogedor()
    p = mp.ProcesoBot(Path("."), on_evento=rec.evento, on_log=rec.log)
    p._token = "ab" * 16
    p._secretos = [p._token, "clave-secreta"]
    t = p._token
    p.procesar_linea(f'@@LUNE {t} {{"tipo":"estado","vida":20}}\n')
    p.procesar_linea(f'  @@LUNE {t} {{"tipo":"estado"}}')              # no al principio
    p.procesar_linea(f'@@LUNE {"cd" * 16} {{"tipo":"estado"}}')          # otro token
    p.procesar_linea(f'@@LUNE {t} {{"tipo":"config"}}')                  # tipo de Lune, no del bot
    p.procesar_linea(f'@@LUNE {t} [1,2]')
    p.procesar_linea(f'@@LUNE {t} {{"tipo":"chat","texto":"{"x" * 9000}"}}')
    p.procesar_linea("[bot] clave-secreta " + t + " " + "y" * 400)
    assert rec.eventos == [{"tipo": "estado", "vida": 20}]
    assert len(rec.logs) == 1 and len(rec.logs[0]) == mp.MAX_LOG
    assert "clave-secreta" not in rec.logs[0] and t not in rec.logs[0] and "***" in rec.logs[0]


def test_enviar_no_bloquea_con_la_tuberia_llena():
    suelta = threading.Event()

    class Tuberia:
        def write(self, _):
            suelta.wait(5)

        def flush(self):
            pass

    falso = SimpleNamespace(stdin=Tuberia(), poll=lambda: None)
    p = mp.ProcesoBot(Path("."))
    p._proceso = falso
    t0 = time.monotonic()
    resultados = [p.enviar({"tipo": "estado"}) for _ in range(300)]
    assert time.monotonic() - t0 < 1.0
    assert resultados.count(True) <= mp.COLA_ENVIOS + 1 and resultados[-1] is False
    suelta.set()
    p._proceso = None


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="Node no está instalado")
def test_bot_js_de_verdad_en_modo_probar_sin_conectarse():
    """El bot.js real con el Node real (y --permission si lo tiene): el canal con token y la
    configuración funcionan de punta a punta. --probar no se conecta a nada; sin
    node_modules contesta que hay que instalarlo."""
    rec = Recogedor()
    p = mp.ProcesoBot(on_evento=rec.evento, on_log=rec.log, on_fin=rec.fin)
    cfg = mp.config_bot({"dueno": "Diego_01", "host": "localhost", "port": 25565},
                        {"nombre": "Lune", "systemPrompt": "Eres Lune. ñandú 💎"}, None)
    ok, texto = p.arrancar(cfg, probar=True)
    assert ok, texto
    assert esperar(lambda: rec.fines, tope=20)
    if p.instalado():
        assert rec.tipos() == ["listo"] and rec.eventos[0]["probar"] is True
        assert rec.fines == [0]
    else:
        assert rec.tipos() == ["error"] and "instálalo" in rec.eventos[0]["mensaje"]
        assert rec.fines == [1]
    assert all(l.startswith("[bot] ") for l in rec.logs), rec.logs
    assert all(p._token not in l for l in rec.logs)


# ── Revisión final: persona medida como en JS (BM6), instalar cancelable (RR2), árbol (RR7) ──

def test_persona_con_emojis_medida_en_unidades_utf16():
    """BM6: config.js mide la persona con .length (UTF-16: un emoji cuenta 2). Python la
    recortaba a 2000 puntos de código → con emojis el bot rechazaba la configuración."""
    assert mp.largo_utf16("ab💎") == 4 and mp.largo_utf16("ñandú") == 5
    personaje = {"nombre": "Lune 💎" * 10, "systemPrompt": "💎 " * 1500,
                 "frases_minecraft": {"muerte": ["🎉" * 100]}}
    cfg = mp.config_bot({"dueno": "Diego_01"}, personaje, None)
    per = cfg["persona"]
    assert 1500 < mp.largo_utf16(per["prompt"]) <= mp.MAX_PERSONA
    assert mp.largo_utf16(per["nombre"]) <= 40 and mp.largo_utf16(per["frases"]["muerte"][0]) <= 120
    assert per["prompt"].endswith("💎")                                  # nunca medio emoji
    assert mp._recortar("hola", 10) == "hola"


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="Node no está instalado")
def test_persona_con_emojis_la_acepta_el_bot_de_verdad():
    """BM6 de punta a punta con el Node real: bot.js --probar valida la configuración."""
    rec = Recogedor()
    p = mp.ProcesoBot(on_evento=rec.evento, on_log=rec.log, on_fin=rec.fin)
    cfg = mp.config_bot({"dueno": "Diego_01", "host": "localhost", "port": 25565},
                        {"nombre": "Lune 💎", "systemPrompt": "Eres Lune 💎. " + "✨🎮 " * 900}, None)
    ok, texto = p.arrancar(cfg, probar=True)
    assert ok, texto
    assert esperar(lambda: rec.fines, tope=20)
    errores = [e.get("mensaje", "") for e in rec.eventos if e["tipo"] == "error"]
    assert not any("persona" in m for m in errores), errores


def test_ruta_node_de_un_gestor_de_versiones_usa_el_exe(carpeta):
    rutas = {"node": "C:/gestor/node.cmd", "node.exe": "C:/gestor/v24/node.exe"}
    p = mp.ProcesoBot(carpeta, which=rutas.get)
    esperado = "C:/gestor/v24/node.exe" if os.name == "nt" else "C:/gestor/node.cmd"
    assert p.ruta_node() == esperado
    assert mp.ProcesoBot(carpeta, which={"node": "C:/gestor/node.cmd"}.get).ruta_node() == "C:/gestor/node.cmd"


def test_no_se_instala_con_el_bot_en_marcha(carpeta):
    """BM11: npm ci borra node_modules, que el bot vivo está usando."""
    lanzados = []
    p = mp.ProcesoBot(carpeta, node=NODE, npm=["npm"], ejecutar=ejecutar_falso(), popen=popen_npm(lanzados))
    p._proceso = SimpleNamespace(poll=lambda: None)
    assert p.instalar() == (False, mp.AVISO_BOT_VIVO) and lanzados == []
    p._proceso = None


def _vivo(pid) -> bool:
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True,
                       creationflags=0x08000000)
    return str(int(pid)) in r.stdout


def _matar_pid(pid) -> None:
    """Limpieza del test: solo ESE pid (nunca por nombre)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(int(pid))], capture_output=True, creationflags=0x08000000)
    else:
        try:
            os.kill(int(pid), 9)
        except OSError:
            pass


# npm de mentira: lanza un hijo (como npm lanza node) y los dos duermen; apunta los PID.
NPM_DORMIDO = r'''
import os, subprocess, sys, time
nieto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
open(sys.argv[1] + ".tmp", "w").write(f"{os.getpid()} {nieto.pid}")
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(60)
'''


def test_instalar_se_cancela_matando_el_arbol_y_la_marca_es_de_la_carpeta(carpeta, tmp_path):
    """RR2: npm ci (≤15 min) se corta: cancelar_instalacion (detener/salir) mata npm y sus
    hijos. Mientras dura, otra instancia (otra ventana, patata) ve la marca y no lanza otro."""
    pids = tmp_path / "pids.txt"
    npm = [sys.executable, "-c", NPM_DORMIDO, str(pids)]
    p1 = mp.ProcesoBot(carpeta, node=NODE, npm=npm, ejecutar=ejecutar_falso())
    p2 = mp.ProcesoBot(carpeta, node=NODE, npm=npm, ejecutar=ejecutar_falso())
    resultado = []
    h = threading.Thread(target=lambda: resultado.append(p1.instalar()), daemon=True)
    h.start()
    try:
        assert esperar(pids.exists, tope=15), "el npm falso no arrancó"
        hijo, nieto = pids.read_text().split()
        assert p1.instalando and p2.instalando                                 # la otra ventana lo ve
        assert (carpeta / mp.MARCA_INSTALANDO).is_file()
        assert p2.instalar() == (False, "Ya se está instalando (desde otra ventana de Lune).")
        t0 = time.monotonic()
        assert p1.cancelar_instalacion() is True
        h.join(10)
        assert resultado == [(False, "Instalación cancelada.")]
        assert time.monotonic() - t0 < 8
        assert esperar(lambda: not _vivo(hijo), tope=8)
        if os.name == "nt":                                                  # el Job mata también al nieto
            assert esperar(lambda: not _vivo(nieto), tope=8)
        assert not p1.instalando and not p2.instalando
        assert not (carpeta / mp.MARCA_INSTALANDO).exists()
        assert p1.cancelar_instalacion() is False                            # nada en marcha
    finally:
        if pids.exists():
            for pid in pids.read_text().split():
                _matar_pid(pid)


SALE_A_MEDIAS = r'''
import sys, threading, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from lune_core import minecraft_proceso as mp
carpeta, pids = Path(sys.argv[2]), Path(sys.argv[3])
npm = [sys.executable, "-c", sys.argv[4], str(pids)]
ver = lambda args, **kw: type("R", (), {"returncode": 0, "stdout": "v24.19.0", "stderr": ""})()
p = mp.ProcesoBot(carpeta, node="node", npm=npm, ejecutar=ver)
threading.Thread(target=p.instalar, daemon=True).start()        # como el hilo de la app
fin = time.monotonic() + 15
while not pids.exists() and time.monotonic() < fin:
    time.sleep(0.05)
'''


@pytest.mark.skipif(os.name != "nt", reason="el Job con KILL_ON_JOB_CLOSE es de Windows")
def test_salir_de_lune_con_npm_a_medias_no_lo_deja_huerfano(carpeta, tmp_path):
    """RR2: Lune se cierra (o se cae) con «Instalar» en marcha: Windows cierra el Job y npm y
    sus hijos mueren (antes seguían hasta 15 min)."""
    pids = tmp_path / "pids.txt"
    raiz = str(Path(__file__).resolve().parent.parent)
    r = subprocess.run([sys.executable, "-c", SALE_A_MEDIAS, raiz, str(carpeta), str(pids), NPM_DORMIDO],
                       capture_output=True, text=True, timeout=60, creationflags=0x08000000)
    try:
        assert r.returncode == 0, r.stderr
        hijo, nieto = pids.read_text().split()
        assert esperar(lambda: not _vivo(hijo) and not _vivo(nieto), tope=10)
    finally:
        if pids.exists():
            for pid in pids.read_text().split():
                _matar_pid(pid)


# «node.cmd» de mentira: un proceso intermedio (como cmd.exe) que lanza el bot falso con sus
# tuberías y apunta el PID del «node» de verdad.
INTERMEDIO = r'''
import os, subprocess, sys
hijo = subprocess.Popen([sys.executable, "-c", os.environ["MC_HIJO"]])
open(os.environ["MC_PIDS"], "w").write(str(hijo.pid))
sys.exit(hijo.wait())
'''


@pytest.mark.skipif(os.name != "nt", reason="el Job con KILL_ON_JOB_CLOSE es de Windows")
def test_parar_mata_el_arbol_aunque_node_vaya_tras_un_cmd(carpeta, tmp_path):
    """RR7 / sospecha: con un node.cmd, terminate() solo mataba el intermedio y node seguía."""
    instalar_falso(carpeta)
    rec = Recogedor()
    pids = tmp_path / "node.pid"

    def popen(args, **kw):
        env = dict(kw.pop("env"))
        env.update(MC_MODO_PRUEBA="terco", MC_HIJO=HIJO, MC_PIDS=str(pids))
        return subprocess.Popen([sys.executable, "-c", INTERMEDIO], env=env, **kw)
    p = mp.ProcesoBot(carpeta, node=NODE, popen=popen, ejecutar=ejecutar_falso(), on_evento=rec.evento,
                      on_log=rec.log, on_fin=rec.fin)
    try:
        assert p.arrancar(dict(CFG))[0]
        assert esperar(lambda: "chat" in rec.tipos()) and esperar(pids.exists)
        node = pids.read_text().strip()
        t0 = time.monotonic()
        p.parar(espera_s=0.3)
        assert time.monotonic() - t0 < 8
        assert esperar(lambda: not _vivo(node), tope=8)
        assert esperar(lambda: len(rec.fines) == 1)
    finally:
        if pids.exists():
            _matar_pid(pids.read_text().strip())
