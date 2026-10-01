"""
Tests de servicios/copia_bots.py: traer el código de los bots de Node (lo que trae
Lune) a la carpeta donde corren, y de cómo lo usan servicios/telegram_worker.py y
lune_core/minecraft_proceso.py.

Instalada, el código viene dentro del programa y los bots corren en DATOS (Telegram,
para que su «..» sea DATOS) y LOCAL (Minecraft). Se copian solo *.js, package.json,
package-lock.json y src/, sin tocar nunca node_modules/, data/ ni .instalando. Desde
el código son la misma carpeta y no se copia nada. Nunca se lanza node ni npm.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from servicios import copia_bots as cb  # noqa: E402
from lune_core import minecraft_proceso as mp  # noqa: E402


def _escribir(ruta: Path, texto: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


@pytest.fixture
def origen(tmp_path):
    """Un bot como los del paquete, con lo que NUNCA se copia al lado."""
    o = tmp_path / "paquete" / "bot"
    _escribir(o / "bot.js", "// bot v2")
    _escribir(o / "config.js", "// config")
    _escribir(o / "package.json", '{"name": "bot"}')
    _escribir(o / "package-lock.json", '{"lockfileVersion": 3}')
    _escribir(o / "src" / "canal.js", "// canal")
    _escribir(o / "src" / "sub" / "util.js", "// util")
    _escribir(o / "LEEME.md", "léeme")
    _escribir(o / ".gitignore", ".instalando")
    _escribir(o / "node_modules" / "grammy" / "package.json", '{"del": "paquete"}')
    _escribir(o / "data" / "memoria_1.json", '{"del": "paquete"}')
    _escribir(o / ".instalando", "{}")
    _escribir(o / "src" / "node_modules" / "x.js", "// nunca")
    return o


def _relativos(carpeta: Path):
    return sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*") if p.is_file())


def test_copia_solo_el_codigo_del_bot(origen, tmp_path):
    destino = tmp_path / "datos" / "bot"
    assert cb.sincronizar(origen, destino) is True
    assert _relativos(destino) == ["bot.js", "config.js", "package-lock.json", "package.json",
                                   "src/canal.js", "src/sub/util.js"]
    assert (destino / "bot.js").read_text("utf-8") == "// bot v2"
    assert not list(destino.glob(".*.tmp")), "sin temporales"


def test_no_toca_node_modules_data_ni_la_marca_del_destino(origen, tmp_path):
    destino = tmp_path / "datos" / "bot"
    nm = _escribir(destino / "node_modules" / "grammy" / "package.json", '{"mio": 1}')
    memoria = _escribir(destino / "data" / "memoria_1.json", '{"recuerdos": ["hola"]}')
    marca = _escribir(destino / ".instalando", '{"lune": 1}')
    viejo = _escribir(destino / "src" / "quitado.js", "// de una versión anterior")
    assert cb.sincronizar(origen, destino) is True
    assert nm.read_text("utf-8") == '{"mio": 1}'
    assert memoria.read_text("utf-8") == '{"recuerdos": ["hola"]}'
    assert marca.read_text("utf-8") == '{"lune": 1}'
    assert viejo.exists(), "no se borra nada del destino"


def test_actualiza_lo_cambiado_y_deja_lo_igual(origen, tmp_path, monkeypatch):
    destino = tmp_path / "bot"
    cb.sincronizar(origen, destino)
    _escribir(origen / "bot.js", "// bot v3")
    _escribir(origen / "src" / "nuevo.js", "// nuevo")
    copiados = []
    real = cb.shutil.copyfile
    monkeypatch.setattr(cb.shutil, "copyfile", lambda a, b: copiados.append(Path(a).name) or real(a, b))
    assert cb.sincronizar(origen, destino) is True
    assert sorted(copiados) == ["bot.js", "nuevo.js"]
    assert (destino / "bot.js").read_text("utf-8") == "// bot v3"
    copiados.clear()
    assert cb.sincronizar(origen, destino) is True and copiados == [], "ya estaba al día"


def test_misma_carpeta_no_copia_nada(origen, monkeypatch):
    monkeypatch.setattr(cb.shutil, "copyfile", lambda *a: pytest.fail("no debería copiar"))
    assert cb.sincronizar(origen, origen) is True
    assert cb.sincronizar(origen, origen / "src" / "..") is True
    assert cb.misma_carpeta(origen, str(origen) + "/.")


def test_sin_origen_o_con_un_fallo_da_false(origen, tmp_path, monkeypatch):
    assert cb.sincronizar(tmp_path / "no_existe", tmp_path / "destino") is False
    assert not (tmp_path / "destino").exists()

    def falla(a, b):
        raise PermissionError(13, "denegado")
    monkeypatch.setattr(cb.shutil, "copyfile", falla)
    assert cb.sincronizar(origen, tmp_path / "destino2") is False
    assert not list((tmp_path / "destino2").rglob("*.tmp"))


def test_los_bots_reales_del_repo():
    """Lo que se copiaría de los bots del repo: su código, nunca node_modules ni data/."""
    tg = cb.archivos_del_bot(RAIZ / "telegram-bot-or")
    assert Path("bot.js") in tg and Path("package-lock.json") in tg and Path("config.js") in tg
    mc = cb.archivos_del_bot(RAIZ / "minecraft-bot")
    assert Path("src/bot.js") in mc and Path("package.json") in mc
    for rel in tg + mc:
        assert not cb.NUNCA.intersection(rel.parts), rel
        assert rel.suffix in (".js", ".json"), rel


# ── Telegram ──────────────────────────────────────────────────────────────────

def test_telegram_se_copia_al_arrancar_desde_su_origen(qapp, origen, tmp_path, monkeypatch):
    from servicios import telegram_worker as tw
    destino = tmp_path / "datos" / "telegram-bot-or"
    monkeypatch.setattr(tw.TelegramBotWorker, "BOT_ORIGEN", origen)
    monkeypatch.setattr(tw.TelegramBotWorker, "BOT_DIR", destino)
    monkeypatch.setattr(tw.shutil, "which", lambda *a, **k: None)          # sin node: no lanza nada
    w = tw.TelegramBotWorker()
    logs = []
    w.log_signal.connect(logs.append)
    w.run()
    assert (destino / "bot.js").read_text("utf-8") == "// bot v2"
    assert not (destino / "node_modules").exists() and not (destino / "data").exists()
    assert logs == [tw.AVISO_SIN_NODE]
    # y la comprobación del botón de la ventana nativa (main.py) también la prepara
    (destino / "bot.js").unlink()
    assert tw.TelegramBotWorker.preparar_carpeta() is True
    assert (destino / "bot.js").exists()


def test_telegram_con_bot_dir_de_la_instancia_no_copia(qapp, origen, tmp_path, monkeypatch):
    from servicios import telegram_worker as tw
    llamadas = []
    monkeypatch.setattr(cb, "sincronizar", lambda *a: llamadas.append(a) or True)
    monkeypatch.setattr(tw.TelegramBotWorker, "BOT_ORIGEN", origen)
    w = tw.TelegramBotWorker()
    w.BOT_DIR = tmp_path / "a_mano"                                      # como los tests de siempre
    w._sincronizar()
    assert llamadas == []
    w2 = tw.TelegramBotWorker()
    w2._sincronizar()
    assert llamadas == [(origen, tw.TelegramBotWorker.BOT_DIR)]


def test_telegram_desde_el_codigo_es_la_carpeta_del_repo_en_datos(qapp):
    from nucleo import rutas
    from servicios import telegram_worker as tw
    assert tw.TelegramBotWorker.BOT_DIR == rutas.dato("telegram-bot-or")
    assert tw.TelegramBotWorker.BOT_ORIGEN == rutas.recurso("telegram-bot-or")


# ── Minecraft ─────────────────────────────────────────────────────────────────

def _instalar_mineflayer(carpeta: Path):
    _escribir(carpeta / "node_modules" / "mineflayer" / "package.json", "{}")


def test_minecraft_por_defecto_trae_el_codigo_de_su_origen(origen, tmp_path, monkeypatch):
    destino = tmp_path / "local" / "minecraft-bot"
    monkeypatch.setattr(mp, "BOT_DIR", destino)
    monkeypatch.setattr(mp, "BOT_ORIGEN", origen)
    p = mp.ProcesoBot(node="C:/falso/node.exe")
    assert p.carpeta == destino and p.origen == origen
    assert p.instalado() is False                   # copia el código, pero sin node_modules
    assert (destino / "src" / "canal.js").exists()
    assert not (destino / "node_modules").exists()


def test_minecraft_con_carpeta_explicita_no_copia(origen, tmp_path):
    p = mp.ProcesoBot(tmp_path / "a_mano")
    assert p.origen is None
    assert p.preparar() is True and not (tmp_path / "a_mano").exists()


def test_minecraft_arrancar_copia_antes_de_buscar_bot_js(origen, tmp_path):
    destino = tmp_path / "local" / "minecraft-bot"
    _escribir(origen / "src" / "bot.js", "// el de minecraft")

    def popen(*a, **k):
        raise AssertionError("sin npm ci no se lanza el bot")
    p = mp.ProcesoBot(destino, origen=origen, node="C:/falso/node.exe", popen=popen,
                      ejecutar=lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    ok, texto = p.arrancar({"dueno": "Diego_01"})
    assert (destino / "src" / "canal.js").exists()
    assert not ok and texto == mp.AVISO_INSTALAR          # el código ya está; falta npm ci


def test_minecraft_un_package_lock_nuevo_pide_reinstalar(origen, tmp_path):
    destino = tmp_path / "local" / "minecraft-bot"
    p = mp.ProcesoBot(destino, origen=origen, node="C:/falso/node.exe")
    p.preparar()
    _instalar_mineflayer(destino)
    marca = destino / "node_modules" / mp.ARCHIVO_HASH_LOCK
    # una instalación de antes (sin marca) adopta el lockfile de ahora
    assert p.instalado() is True and marca.is_file()
    # llega una actualización con otras dependencias
    _escribir(origen / "package-lock.json", '{"lockfileVersion": 3, "otra": "dependencia"}')
    p.preparar(forzar=True)
    assert p.instalado() is False, "otro lockfile: hay que volver a hacer npm ci"
    p._anotar_lock()                                  # lo que hace un npm ci que sale bien
    assert p.instalado() is True


def test_minecraft_npm_ci_bueno_guarda_el_hash_del_lockfile(origen, tmp_path):
    destino = tmp_path / "local" / "minecraft-bot"

    class Npm:
        def __init__(self, args, **kw):
            _instalar_mineflayer(destino)
            self.pid, self.returncode = 4242, None

        def communicate(self, timeout=None):
            self.returncode = 0
            return "", ""

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

    ver = lambda *a, **k: SimpleNamespace(returncode=0, stdout="v24.19.0", stderr="")   # noqa: E731
    p = mp.ProcesoBot(destino, origen=origen, node="C:/falso/node.exe", npm=["npm"],
                      popen=Npm, ejecutar=ver)
    ok, texto = p.instalar()
    assert ok, texto
    marca = destino / "node_modules" / mp.ARCHIVO_HASH_LOCK
    import hashlib
    esperado = hashlib.sha256((origen / "package-lock.json").read_bytes()).hexdigest()
    assert marca.read_text("ascii").strip() == esperado
    assert not (destino / mp.MARCA_INSTALANDO).exists()


def test_minecraft_desde_el_codigo_es_la_carpeta_del_repo_en_local():
    from nucleo import rutas
    assert mp.BOT_DIR == rutas.local("minecraft-bot")
    assert mp.BOT_ORIGEN == rutas.recurso("minecraft-bot")
    assert json.loads((mp.BOT_ORIGEN / "package.json").read_text("utf-8"))
