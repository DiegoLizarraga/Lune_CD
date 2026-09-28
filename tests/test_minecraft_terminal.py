"""
Tests de Minecraft en patata (servicios/minecraft_terminal.MinecraftTerminal, corte 10):

- `/mc bot on host[:puerto]` valida el servidor (nombre/IP y 1–65535) y lo guarda con
  datos.guardar_minecraft; conecta con config_bot (sin dueño → el texto del ValueError); sin
  Node o sin instalar → aviso; `/mc bot off`; `/mc di` saneado; `/mc <orden>` por la lista
  blanca; `/mc instalar` (D3, solo a mano);
- reacciones del log con Cadencia: «Lune: …» por consola.aviso + capa del título que se quita
  al vencer; deduplicadas; apagadas → nada; voz si voz_reacciones;
- modo juego (D4): con el bot conectado lo dice el bot en el chat; sin bot, resumen al salir;
  pausa_autonomo al entrar y salir; `pensando` → pausa_llm;
- mensajes del bot: el tipo del evento va en msg["evento"]; propio = jugador == dueño; el chat
  de otros no se imprime; nada de secuencias ANSI de fuera;
- herramientas del modelo; detener para el bot;
- contrato con lune_core/minecraft_proceso.ProcesoBot DE VERDAD y un hijo falso
  (`sys.executable -c`) que habla el protocolo @@LUNE: conectado, evento y respuesta.
Sin red, sin node, sin archivos del juego; sin hilos (pasos a mano) salvo el hijo falso.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import minecraft_proceso as mp  # noqa: E402
from lune_core.minecraft_log import Evento  # noqa: E402
from servicios.minecraft_terminal import (  # noqa: E402
    AYUDA, CAPA, PRIORIDAD_TITULO, MinecraftTerminal, servidor_de,
)


class Config:
    def __init__(self, **mc):
        self.d = {"minecraft": {"reaccionar": True, "ruta_log": "", "voz_reacciones": False, "auto_con_juego": True,
                                "decir_en_juego": True, "resumen_al_salir": True, "pensar_en_juego": False,
                                "reaccionar_otros": False, **mc}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = v


class Proceso:
    def __init__(self, instalado=True, node_ok=True):
        self.vivo = False
        self._instalado = instalado
        self.node_ok = node_ok
        self.arranques, self.ordenes, self.dichos, self.pausas, self.paradas = [], [], [], [], []
        self.on_evento = self.on_log = self.on_fin = None
        self.instalaciones = 0

    def requisitos(self, refrescar=False):
        return {"node": "v24.19.0" if self.node_ok else None, "node_ok": self.node_ok, "npm": True,
                "instalado": self._instalado}

    def instalado(self):
        return self._instalado

    def instalar(self, cancelar=None):
        self.instalaciones += 1
        self._instalado = True
        return True, "Bot de Minecraft instalado."

    def arrancar(self, cfg, probar=False):
        self.arranques.append(cfg)
        self.vivo = True
        return True, "Arrancando el bot…"

    def orden(self, id_, texto):
        self.ordenes.append((id_, texto))
        return True

    def decir(self, texto):
        self.dichos.append(texto)
        return True

    def pausa_llm(self, on):
        self.pausas.append(("llm", on))
        return True

    def pausa_autonomo(self, on):
        self.pausas.append(("autonomo", on))
        return True

    def parar(self, espera_s=4.0):
        self.paradas.append(espera_s)
        self.vivo = False


class Lector:
    def __init__(self):
        self.ruta = Path("C:/juego/logs/latest.log")
        self.pendientes = []
        self.yo, self.otros, self.nombre_bot = "Diego_01", False, ""

    def poll(self):
        e, self.pendientes = self.pendientes, []
        return e

    def inactivo_s(self):
        return 0.0


class Consola:
    ansi = True

    def __init__(self):
        self.avisos, self.capas = [], []

    def aviso(self, t):
        self.avisos.append(t)

    def titulo_capa(self, capa, texto, prioridad=0):
        self.capas.append((capa, texto, prioridad))
        return True


class Voz:
    def __init__(self):
        self.dichos = []

    def speak(self, t):
        self.dichos.append(t)


class Azar:
    def random(self):
        return 0.0


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def montar(*, proceso=None, lector="fijo", datos=None, config=None, voz=None, juego=None, pensando=None):
    guardados = []
    datos_mc = dict(datos or {"dueno": "Diego_01", "host": "localhost", "port": 25565})

    def guardar(cambios):
        if "host" in cambios and not mp.validar_host(cambios["host"]):
            raise ValueError("host malo")
        guardados.append(dict(cambios))
        datos_mc.update(cambios)
        return dict(datos_mc)
    estado = {"juego": False, "pensando": False}
    reloj = Reloj()
    consola = Consola()
    term = MinecraftTerminal(
        consola, config or Config(), proceso=proceso or Proceso(), lector=Lector() if lector == "fijo" else lector,
        voice=voz, colores={"cyan": "", "dim": "", "reset": ""}, en_juego=juego or (lambda: estado["juego"]),
        pensando=pensando or (lambda: estado["pensando"]), reloj=reloj, ahora=lambda: 5000.0, rng=Azar(),
        rutas=lambda: [], datos_mc=lambda: dict(datos_mc), guardar_mc=guardar,
        personaje=lambda: {"nombre": "Lune", "systemPrompt": "Eres Lune."}, llm=lambda: None, hilo=False)
    term.consola_, term.reloj_, term.estado_, term.guardados_, term.datos_ = consola, reloj, estado, guardados, datos_mc
    return term


# ── Servidor, conectar y órdenes ────────────────────────────────────────────────

def test_servidor_de():
    assert servidor_de("mc.example.com:25570") == ("mc.example.com", 25570, "")
    assert servidor_de("192.168.1.9") == ("192.168.1.9", None, "")
    assert servidor_de("[::1]:25565") == ("::1", 25565, "")
    for malo in ("http://x", "a b", "x:0", "x:70000", "x:abc", "", "x/y:25565"):
        assert servidor_de(malo)[2], malo


def test_bot_on_guarda_el_servidor_y_conecta_con_config_bot():
    t = montar()
    r = t.comando("/mc bot on mc.casa.lan:25570")
    assert r == "Conectando el bot a mc.casa.lan:25570 como Lune…"
    assert t.guardados_ == [{"host": "mc.casa.lan", "port": 25570}]
    cfg = t.proceso.arranques[0]
    assert cfg["tipo"] == "config" and cfg["host"] == "mc.casa.lan" and cfg["port"] == 25570
    assert cfg["dueno"] == "Diego_01" and cfg["nick"] == "Lune" and cfg["llm"] is None
    assert cfg["pausa_autonomo"] is False and cfg["pausa_llm"] is False
    assert t.estado()["bot"]["conectando"] is True
    assert t.comando("/mc bot on") == "El bot ya está conectado."
    assert t.comando("/mc bot off") == "Desconecto el bot."
    assert t.proceso.paradas and not t.proceso.vivo
    assert t.comando("/mc bot off") == "El bot no estaba conectado."


@pytest.mark.parametrize("caso,esperado", [
    ("host", "no es un nombre ni una IP"), ("puerto", "entre 1 y 65535"), ("sin_node", "Node.js 18"),
    ("sin_instalar", "/mc instalar"), ("sin_dueno", "datos.json"),
])
def test_bot_on_no_conecta(caso, esperado):
    proceso = Proceso(instalado=caso != "sin_instalar", node_ok=caso != "sin_node")
    t = montar(proceso=proceso, datos={"host": "localhost", "port": 25565} if caso == "sin_dueno" else None)
    linea = {"host": "/mc bot on http://evil", "puerto": "/mc bot on x.lan:99999"}.get(caso, "/mc bot on")
    r = t.comando(linea)
    assert esperado in r, r
    assert proceso.arranques == [] and t.guardados_ == []


def test_decir_y_ordenes_por_la_lista_blanca():
    t = montar()
    assert "no está conectado" in t.comando("/mc di hola")
    assert "no está conectado" in t.comando("/mc sígueme")
    t.comando("/mc bot on")
    t.proceso.on_evento({"tipo": "conectado", "nick": "Lune"})
    assert t.bot_conectado
    assert t.comando("/mc di /op\x1b[31m hola") == "Dicho."
    assert t.proceso.dichos == ["op [31m hola"], "sin / inicial ni controles"
    assert t.comando("/mc sígueme") == "Se lo he mandado al bot."
    assert t.comando("/mc mina 10 hierro") == "Se lo he mandado al bot."
    assert [o for _, o in t.proceso.ordenes] == ["sigueme", "mina 10 hierro"]
    assert "no entiende" in t.comando("/mc borra el mundo")
    assert len(t.proceso.ordenes) == 2
    assert t.comando("/mc ayuda").startswith("Uso: " + AYUDA)
    assert t.comando("/otra cosa") is None and t.comando("/mcx") is None


def test_instalar_solo_a_mano_y_estado():
    p = Proceso(instalado=False)
    t = montar(proceso=p)
    assert "Bot de Minecraft: sin instalar" in t.comando("/mc")
    assert t.comando("/mc instalar") == "Instalación terminada."
    assert p.instalaciones == 1 and t.consola_.avisos[-1] == "♪ Bot de Minecraft instalado."
    assert "desconectado" in t.comando("/mc estado")
    p2 = Proceso(instalado=False, node_ok=False)
    t2 = montar(proceso=p2)
    assert "Node.js 18" in t2.comando("/mc instalar") and p2.instalaciones == 0


# ── Reacciones ─────────────────────────────────────────────────────────────────

def test_reacciones_del_log_con_cadencia_titulo_y_voz():
    voz = Voz()
    t = montar(voz=voz, config=Config(voz_reacciones=True))
    t.iniciar()
    t.lector_ = t._lector
    t._lector.pendientes = [Evento("muerte", "Diego_01", "Zombie", propio=True)]
    t.paso()
    av = t.consola_.avisos[-1]
    assert av.startswith("Lune: ") and len(t.consola_.avisos) == 1
    capa, texto, prio = t.consola_.capas[-1]
    assert capa == CAPA and texto.startswith("Lune: ") and prio == PRIORIDAD_TITULO
    assert voz.dichos == [av[len("Lune: "):]]
    # la misma muerte otra vez en 5 s: una sola
    t._lector.pendientes = [Evento("muerte", "Diego_01", "Zombie", propio=True)]
    t.paso()
    assert len(t.consola_.avisos) == 1
    # la capa se quita al vencer
    t.reloj_.t += 11
    t.paso()
    assert t.consola_.capas[-1] == (CAPA, None, PRIORIDAD_TITULO)
    # reacciones apagadas: nada del log
    assert t.comando("/mc log off") == "Vale: ya no miro tu partida."
    assert t.config.get("minecraft", "reaccionar") is False
    t._lector.pendientes = [Evento("logro", "Diego_01", "Cazamonstruos", propio=True)]
    t.paso()
    t._leer()
    assert len(t.consola_.avisos) == 1
    assert "miro tu partida" in t.comando("/mc log on")


def test_modo_juego_con_bot_lo_dice_el_bot_y_sin_bot_resumen_al_salir():
    t = montar()
    t.iniciar()
    t.comando("/mc bot on")
    t.proceso.on_evento({"tipo": "conectado", "nick": "Lune"})
    t.estado_["juego"] = True
    t.paso()
    assert ("autonomo", True) in t.proceso.pausas, "el cerebro autónomo en pausa mientras juegas (D4)"
    n = len(t.consola_.avisos)
    t._lector.pendientes = [Evento("muerte", "Diego_01", "Zombie", propio=True)]
    t.paso()
    assert len(t.proceso.dichos) == 1 and len(t.consola_.avisos) == n, "lo dice el bot en el chat del juego"
    t.estado_["juego"] = False
    t.paso()
    assert ("autonomo", False) in t.proceso.pausas
    assert t.consola_.avisos[-1] == "Lune: Mientras jugabas: 1 muerte."
    # sin bot: se apunta y sale el resumen
    t2 = montar()
    t2.iniciar()
    t2.estado_["juego"] = True
    t2.paso()
    t2._lector.pendientes = [Evento("logro", "Diego_01", "Cazamonstruos", propio=True)]
    t2.paso()
    assert t2.consola_.avisos == [] and t2.proceso.dichos == []
    t2.estado_["juego"] = False
    t2.paso()
    assert t2.consola_.avisos == ["Lune: Mientras jugabas: 1 logro (Cazamonstruos)."]


def test_pensando_pausa_el_modelo_del_bot():
    t = montar()
    t.comando("/mc bot on")
    t.estado_["pensando"] = True
    t.paso()
    t.estado_["pensando"] = False
    t.paso()
    assert [p for p in t.proceso.pausas if p[0] == "llm"] == [("llm", True), ("llm", False)]


def test_mensajes_del_bot_evento_propio_chat_y_respuesta():
    t = montar()
    t.iniciar()
    t.comando("/mc bot on")
    t.proceso.on_evento({"tipo": "conectado", "nick": "Lune"})
    assert t.consola_.avisos[-1].startswith("Lune: "), "bot_conectado"
    n = len(t.consola_.avisos)
    t.proceso.on_evento({"tipo": "evento", "evento": "muerte", "jugador": "Steve", "detalle": "Zombie"})
    assert len(t.consola_.avisos) == n, "muertes de otros solo con reaccionar_otros"
    t.proceso.on_evento({"tipo": "evento", "evento": "muerte", "jugador": "Diego_01", "detalle": "Zombie"})
    assert len(t.consola_.avisos) == n + 1, "la del dueño (propio) sí"
    t.proceso.on_evento({"tipo": "chat", "de": "Steve", "texto": "\x1b[2J hola"})
    assert len(t.consola_.avisos) == n + 1, "el chat de otros no se imprime"
    t.proceso.on_evento({"tipo": "respuesta", "id": "a1", "texto": "Voy\x1b[31m contigo"})
    assert t.consola_.avisos[-1] == "bot: Voy [31m contigo" and "\x1b" not in t.consola_.avisos[-1]
    t.proceso.on_evento({"tipo": "estado", "vida": 18, "hambre": 20, "dia": True, "lluvia": False})
    assert "vida 18/20" in t.comando("/mc")
    t.proceso.on_fin(1)
    assert not t.bot_conectado and "código 1" in t.estado()["bot"]["error"]


def test_herramientas_y_detener():
    t = montar()
    handlers = {}

    class Tools:
        def registrar_handler(self, nombre, fn):
            handlers[nombre] = fn
    t.registrar_herramientas(Tools())
    assert set(handlers) == {"minecraft_estado", "minecraft_orden", "minecraft_bot"}
    assert "Bot de Minecraft: desconectado" in handlers["minecraft_estado"]({}, None)
    assert handlers["minecraft_orden"]({"orden": "sigueme"}, None)[0] is False
    assert handlers["minecraft_bot"]({"accion": "conectar"}, None).startswith("Conectando el bot")
    t.proceso.on_evento({"tipo": "conectado", "nick": "Lune"})
    assert handlers["minecraft_orden"]({"orden": "sígueme"}, None).startswith("Se lo he mandado")
    assert handlers["minecraft_bot"]({"accion": "desconectar"}, None) == "Desconecto el bot de Minecraft."
    t.comando("/mc bot on")
    t.iniciar()
    t.detener()
    assert t.proceso.paradas[-1] == 2.0 and not t.proceso.vivo


# ── Contrato con ProcesoBot de verdad y un hijo falso ──────────────────────────
HIJO = r'''
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
tok = os.environ.get("LUNE_MC_TOKEN", "")
def marca(d):
    print("@@LUNE " + tok + " " + json.dumps(d), flush=True)
cfg = json.loads(sys.stdin.readline())
marca({"tipo": "listo"})
marca({"tipo": "conectado", "nick": cfg.get("nick")})
marca({"tipo": "evento", "evento": "logro", "jugador": cfg.get("dueno"), "detalle": "Cazamonstruos"})
print("@@LUNE " + "0" * 32 + " " + json.dumps({"tipo": "evento", "evento": "muerte", "jugador": cfg.get("dueno")}), flush=True)
for linea in sys.stdin:
    m = json.loads(linea)
    if m.get("tipo") == "orden":
        marca({"tipo": "respuesta", "id": m.get("id"), "texto": "Voy: " + m.get("texto", "")})
    if m.get("tipo") == "salir":
        sys.exit(0)
'''


def test_contrato_con_proceso_bot_de_verdad(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bot.js").write_text("// bot", encoding="utf-8")
    (tmp_path / "node_modules" / "mineflayer").mkdir(parents=True)
    (tmp_path / "node_modules" / "mineflayer" / "package.json").write_text("{}", encoding="utf-8")

    def ejecutar(args, **kw):
        if args[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="v24.19.0\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def popen(args, **kw):
        return subprocess.Popen([sys.executable, "-c", HIJO], **kw)

    proceso = mp.ProcesoBot(tmp_path, node="C:/falso/node.exe", popen=popen, ejecutar=ejecutar)
    t = montar(proceso=proceso)
    try:
        t.iniciar()
        assert t.comando("/mc bot on").startswith("Conectando el bot a localhost:25565 como Lune")
        fin = time.monotonic() + 8
        while time.monotonic() < fin and len(t.consola_.avisos) < 2:
            time.sleep(0.02)
        assert t.bot_conectado
        textos = [a for a in t.consola_.avisos if a.startswith("Lune: ")]
        assert len(textos) == 2, t.consola_.avisos      # bot_conectado + el logro del dueño (la marca falsa, fuera)
        assert any("Cazamonstruos" in a for a in textos)
        assert t.comando("/mc ven") == "Se lo he mandado al bot."
        while time.monotonic() < fin and not any(a.startswith("bot: ") for a in t.consola_.avisos):
            time.sleep(0.02)
        assert "bot: Voy: ven" in t.consola_.avisos
    finally:
        t.detener()
    assert not proceso.vivo


# ── Revisión final (RR2, BM9, BM10, BM11) ───────────────────────────────────────

def test_detener_corta_la_instalacion():
    class ProcesoInstalando(Proceso):
        cancelados = 0

        def cancelar_instalacion(self):
            self.cancelados += 1
            return True
    t = montar(proceso=ProcesoInstalando())
    t.iniciar()
    t.detener()
    assert t.proceso.cancelados == 1


def test_instalar_con_el_bot_en_marcha_o_instalando_en_otra_ventana():
    t = montar()
    t.comando("/mc bot on")
    r = t.comando("/mc instalar")
    assert "Desconecta el bot (/mc bot off)" in r and t.proceso.instalaciones == 0
    t.comando("/mc bot off")
    otro = Proceso(instalado=False)
    otro.instalando = True                                    # la marca de minecraft-bot/: otra ventana
    t2 = montar(proceso=otro)
    assert t2.comando("/mc instalar") == "Ya se está instalando el bot."
    assert t2.estado()["bot"]["instalando"] is True
    ok, texto = t2.conectar_bot()
    assert not ok and "instalación" in texto and otro.instalaciones == 0


def test_el_resumen_se_vacia_al_entrar_en_modo_juego():
    t = montar()
    t.iniciar()
    t._resumen.anotar(Evento("muerte", "Diego_01", "Creeper", propio=True))       # de otra partida
    t.estado_["juego"] = True
    t.paso()
    assert t._resumen.vacio
    t.detener()


def test_registro_soltado_por_inactividad_sigue_donde_se_quedo(tmp_path):
    """BM10 (patata): el lector nuevo del MISMO latest.log sigue desde donde se quedó."""
    from lune_core.minecraft_log import LectorLog
    log = tmp_path / "latest.log"
    log.write_text("[12:00:01] [Render thread/INFO]: Setting user: Diego_01\n", encoding="utf-8")
    t_log = [1000.0]
    creados = []

    def fabrica(ruta):
        lec = LectorLog(ruta, ahora=lambda: t_log[0])
        creados.append(lec)
        return lec
    t = montar(lector=fabrica, config=Config(auto_con_juego=False))
    t._rutas = lambda: [log]
    t.iniciar()
    t.paso()
    assert len(creados) == 1
    t_log[0] += 700                                           # 11 min sin cambios → se suelta
    t.paso()
    assert t._lector is None
    with open(log, "a", encoding="utf-8") as f:
        f.write("[12:12:00] [Render thread/INFO]: [System] [CHAT] Diego_01 fue asesinado/a por Zombi\n")
    t.reloj_.t += 20
    t.paso()
    assert len(creados) == 2
    assert [e["tipo"] for e in t.eventos_recientes()] == ["muerte"]
    t.detener()
