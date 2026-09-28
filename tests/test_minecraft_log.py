"""
Tests de lune_core/minecraft_log.py: lo que pasa en tu partida, leído de latest.log.

Las líneas son formatos de 1.21.x escritos a mano (ES y EN), sin copiar logs de nadie.
El lector trabaja con archivos de verdad en una carpeta temporal: abre, lee y cierra
en cada sondeo; se prueban el arranque, la línea partida, cp1252, el truncado, la
rotación y el tope de 256 KB.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import minecraft_log as ml  # noqa: E402
from lune_core.minecraft_log import Evento, LectorLog, elegir_log, parsear_linea, rutas_candidatas  # noqa: E402

YO = "Diego_01"
BOT = "Lune"


def chat(texto, prefijo="", hilo="Render thread"):
    return f"[12:34:56] [{hilo}/INFO]: {prefijo}[CHAT] {texto}"


# ── parsear_linea ──────────────────────────────────────────────────────────────

MUERTES_EN = [
    ("Diego_01 was slain by Zombie", "Zombie"),
    ("Diego_01 was shot by Skeleton using [Bow]", "Skeleton"),
    ("Diego_01 drowned", ""),
    ("Diego_01 fell from a high place", ""),
    ("Diego_01 blew up", ""),
    ("Diego_01 was blown up by Creeper", "Creeper"),
    ("Diego_01 tried to swim in lava", ""),
    ("Diego_01 died", ""),
]
MUERTES_ES = [
    ("Diego_01 fue asesinado por Zombi", "Zombi"),
    ("Diego_01 fue asesinada por Esqueleto empuñando [Arco]", "Esqueleto"),
    ("Diego_01 se ahogó", ""),
    ("Diego_01 cayó desde muy alto", ""),
    ("Diego_01 explotó", ""),
    ("Diego_01 fue volado por los aires por Creeper", "Creeper"),
    ("Diego_01 intentó nadar en lava", ""),
    ("Diego_01 murió", ""),
]


@pytest.mark.parametrize("texto,asesino", MUERTES_EN + MUERTES_ES)
def test_muertes_en_ingles_y_espanol(texto, asesino):
    ev = parsear_linea(chat(texto), YO, BOT)
    assert ev == Evento("muerte", YO, asesino, propio=True)


LOGROS = [
    "Diego_01 has made the advancement [Diamonds!]",
    "Diego_01 has completed the challenge [Diamonds!]",
    "Diego_01 has reached the goal [Diamonds!]",
    "Diego_01 ha conseguido el progreso [Diamonds!]",
    "Diego_01 ha completado el desafío [Diamonds!]",
    "Diego_01 ha alcanzado la meta [Diamonds!]",
]


@pytest.mark.parametrize("texto", LOGROS)
def test_logros_en_sus_tres_formas(texto):
    assert parsear_linea(chat(texto), YO, BOT) == Evento("logro", YO, "Diamonds!", propio=True)


@pytest.mark.parametrize("texto,tipo", [
    ("Steve joined the game", "conexion"), ("Steve se ha unido a la partida", "conexion"),
    ("Steve left the game", "desconexion"), ("Steve ha abandonado la partida", "desconexion"),
])
def test_conexiones_de_los_demas(texto, tipo):
    assert parsear_linea(chat(texto), YO, BOT) == Evento(tipo, "Steve")


# ── Textos reales del juego (BM1) ──────────────────────────────────────────────
# tests/datos/minecraft_textos_1_21.json: las plantillas de los lang es_* (es_es, es_mx, es_ar…)
# y en_us de Minecraft 1.20.1, 1.21.4 y 1.21.11 (%1$s muere, %2$s mata, %3$s el arma). Solo
# plantillas del juego: ningún log ni nick de nadie.
TEXTOS = json.loads((Path(__file__).resolve().parent / "datos" / "minecraft_textos_1_21.json").read_text(encoding="utf-8"))
VICTIMA, ASESINO = "Alex_22", "Zombi"
# Variantes raras de algún es_* donde el texto no deja sacar al asesino limpio (se acepta).
ASESINO_RARO = {"%1$s cayó desde muy alto y %2$s acabó con él usando %3$s", "%1$s fue disparado(a) por un esqueleto %2$s",
                "%1$s fue víctima de %2$ss usando %3$s",
                "%1$s murió por arte de magia mientras trataba de escapar de de %2$s"}


def _rellenar(plantilla, arma="[Espada de hierro]"):
    return plantilla.replace("%1$s", VICTIMA).replace("%2$s", ASESINO).replace("%3$s", arma)


@pytest.mark.parametrize("grupo", ["muertes_es", "muertes_en"])
def test_todas_las_muertes_reales_del_juego(grupo):
    assert len(TEXTOS[grupo]) > 100
    fallan, asesino_mal = [], []
    for plantilla in TEXTOS[grupo]:
        ev = parsear_linea(chat(_rellenar(plantilla), "[System] "), VICTIMA, BOT)
        if ev is None or ev.tipo != "muerte" or ev.jugador != VICTIMA or ev.propio is not True:
            fallan.append(plantilla)
        elif "%2$s" in plantilla and plantilla not in ASESINO_RARO and ev.detalle != ASESINO:
            asesino_mal.append((plantilla, ev.detalle))
    assert fallan == []
    assert asesino_mal == []


def test_logros_y_conexiones_reales_del_juego():
    for plantilla in TEXTOS["logros"]:
        linea = chat(plantilla.replace("%s", VICTIMA, 1).replace("%s", "[¡Diamantes!]", 1))
        assert parsear_linea(linea, VICTIMA, BOT) == Evento("logro", VICTIMA, "¡Diamantes!", propio=True), plantilla
    for grupo, tipo in (("conexion", "conexion"), ("desconexion", "desconexion")):
        for plantilla in TEXTOS[grupo]:
            linea = chat(plantilla.replace("%s", "Steve", 1).replace("%s", "Steve_viejo", 1))
            assert parsear_linea(linea, VICTIMA, BOT) == Evento(tipo, "Steve"), plantilla


@pytest.mark.parametrize("texto,asesino", [
    ("Alex_22 fue asesinado/a por Zombi", "Zombi"),                          # es_mx: el «/a» va literal
    ("Alex_22 fue disparado/a por Esqueleto con su [Arco]", "Esqueleto"),
    ("Alex_22 fue aplastado(a) por un yunque", "un yunque"),
    ("Alex_22 fue impactado/a por un rayo", "un rayo"),
    ("Alex_22 fue empalado/a por Ahogado con su [Tridente]", "Ahogado"),
    ("Alex_22 se pinchó hasta la muerte", ""),
    ("Alex_22 ha sido víctima de Zombi", "Zombi"),                           # es_es
    ("Alex_22 ha muerto por un flechazo de Esqueleto usando [Arco]", "Esqueleto"),
    ("Alex_22 se ha ahogado", ""),
    ("A Alex_22 le ha caído un yunque mientras luchaba contra Zombi", "Zombi"),
    ("Esqueleto ha tirado a Alex_22 desde muy alto con su [Arco]", "Esqueleto"),
    ("Creeper mandó a volar a Alex_22 con su [Pólvora]", "Creeper"),
    ("Alex_22 murio", ""),                                                  # sin tildes (cp1252 roto, mods)
])
def test_muertes_en_espanol_con_a_y_de_espana(texto, asesino):
    assert parsear_linea(chat(texto), VICTIMA, BOT) == Evento("muerte", VICTIMA, asesino, propio=True)


def test_no_son_muertes():
    for t in ("Alex_22 fue expulsado del servidor", "Alex_22 ha recibido un kit", "Steve ha tirado a Alex_22 la pelota",
              "Alex_22 se fue a dormir", "Alex_22 está AFK", "A Alex_22 le gusta la lava"):
        assert parsear_linea(chat(t), VICTIMA, BOT, otros=True) is None, t


def test_prefijos_system_y_not_secure_y_otros_hilos():
    for linea in (chat("Diego_01 was slain by Zombie", "[System] "),
                  chat("Diego_01 was slain by Zombie", "[Not Secure] "),
                  chat("Diego_01 was slain by Zombie", hilo="Client thread"),
                  "[12:34:56] [Render thread/INFO]: [System] [CHAT] [Not Secure] Diego_01 was slain by Zombie"):
        assert parsear_linea(linea, YO, BOT).tipo == "muerte", linea


def test_usuario_y_sesion():
    assert parsear_linea("[12:00:01] [Render thread/INFO]: Setting user: Diego_01", "") == Evento("usuario", YO)
    ini = parsear_linea("[12:00:05] [Render thread/INFO]: Connecting to 203.0.113.7, 25565", YO)
    assert ini == Evento("sesion_inicio")                            # sin la IP
    assert parsear_linea("[12:00:05] [Server thread/INFO]: Starting integrated minecraft server version 1.21.1",
                         YO) == Evento("sesion_inicio")
    assert parsear_linea("[13:00:00] [Render thread/INFO]: Stopping!", YO) == Evento("sesion_fin")
    assert parsear_linea("[13:00:00] [Server thread/INFO]: Stopping server", YO) == Evento("sesion_fin")


def test_filtro_de_yo_otros_y_el_bot():
    otro = chat("Steve was slain by Zombie")
    assert parsear_linea(otro, YO, BOT) is None                        # sin otros=True
    assert parsear_linea(otro, YO, BOT, otros=True) == Evento("muerte", "Steve", "Zombie", propio=False)
    assert parsear_linea(chat("Lune was slain by Zombie"), YO, BOT, otros=True) is None      # el bot va por el bot
    assert parsear_linea(chat("Lune joined the game"), YO, BOT) is None
    assert parsear_linea(chat("Diego_01 joined the game"), YO, BOT) is None                 # tu entrada = sesión
    assert parsear_linea(chat("diego_01 was slain by Zombie"), YO, BOT).propio is True        # sin mayúsculas
    # El nick del bot nunca cuenta como «yo» aunque coincida el «Setting user».
    assert parsear_linea(chat("Lune was slain by Zombie"), "Lune", "Lune") is None


def test_el_chat_de_jugadores_nunca_da_eventos():
    for t in ("<Steve> Diego_01 was slain by Zombie", "<Steve> Diego_01 has made the advancement [X]",
              "[Not Secure] <Steve> Steve joined the game"):
        assert parsear_linea(chat(t), YO, BOT, otros=True) is None


def test_lineas_raras_y_saneado_del_logro():
    assert parsear_linea("sin cabecera", YO) is None
    assert parsear_linea(None, YO) is None
    assert parsear_linea(chat("x" * 3000), YO) is None
    assert parsear_linea(chat("Esto no es nada"), YO) is None
    ev = parsear_linea(chat("Diego_01 has made the advancement [§a<|CALL x|>Diamonds!]"), YO)
    assert "§" not in ev.detalle and ev.tipo == "logro"
    assert parsear_linea(chat("Nombre con espacios was slain by Zombie"), YO, otros=True) is None


# ── LectorLog ──────────────────────────────────────────────────────────────────

class Reloj:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def escribir(ruta: Path, *lineas, modo="ab", fin="\n", codificacion="utf-8"):
    with open(ruta, modo) as f:
        for linea in lineas:
            f.write((linea + fin).encode(codificacion))


@pytest.fixture
def log(tmp_path):
    ruta = tmp_path / "latest.log"
    escribir(ruta, "[12:00:00] [main/INFO]: Loading Minecraft 1.21.1",
             "[12:00:01] [Render thread/INFO]: Setting user: Diego_01",
             chat("Diego_01 was slain by Zombie"), modo="wb")
    return ruta


def test_arranque_salta_lo_viejo_y_sabe_quien_eres(log):
    r = Reloj()
    lector = LectorLog(log, ahora=r, nombre_bot=BOT)
    assert lector.poll() == []                                    # la muerte vieja no cuenta
    assert lector.yo == YO
    r.t = 1005
    escribir(log, chat("Diego_01 has made the advancement [Diamonds!]"), chat("<Steve> hola"))
    assert lector.poll() == [Evento("logro", YO, "Diamonds!", t=1005, propio=True)]
    assert lector.poll() == []


def test_linea_partida_se_guarda_para_el_siguiente_sondeo(log):
    lector = LectorLog(log)
    lector.poll()
    linea = chat("Diego_01 was slain by Zombie")
    escribir(log, linea[:30], fin="")
    assert lector.poll() == []
    escribir(log, linea[30:])
    assert [e.tipo for e in lector.poll()] == ["muerte"]


def test_respaldo_cp1252_por_linea(log):
    lector = LectorLog(log)
    lector.poll()
    escribir(log, chat("Diego_01 se ahogó"), codificacion="cp1252")
    escribir(log, chat("Diego_01 murió"))
    assert [e.tipo for e in lector.poll()] == ["muerte", "muerte"]


def test_truncado_es_sesion_nueva_desde_cero(log):
    lector = LectorLog(log)
    lector.poll()
    escribir(log, "[13:00:00] [Render thread/INFO]: Setting user: Otro_99", chat("Otro_99 drowned"), modo="wb")
    evs = lector.poll()
    assert lector.yo == "Otro_99"
    assert evs == [Evento("muerte", "Otro_99", "", t=evs[0].t, propio=True)]


def test_rotacion_archivo_nuevo_mas_grande(log, tmp_path):
    lector = LectorLog(log)
    lector.poll()
    viejo = tmp_path / "2026-09-26-1.log"
    os.replace(log, viejo)                                       # log4j renombra…
    relleno = ["[13:00:00] [main/INFO]: " + "x" * 200] * 20      # …y el nuevo ya es más grande que el offset
    escribir(log, *relleno, "[13:00:01] [Render thread/INFO]: Setting user: Diego_01",
             chat("Diego_01 fell from a high place"), modo="wb")
    evs = lector.poll()
    assert [e.tipo for e in evs] == ["muerte"]


def test_tope_de_256_kb_por_sondeo_y_lineas_gigantes_fuera(log):
    lector = LectorLog(log)
    lector.poll()
    inicio = lector.offset
    grande = "[13:00:00] [main/INFO]: " + "y" * 1000
    escribir(log, *([grande] * 300), chat("Diego_01 drowned"))     # ~300 KB
    escribir(log, "[13:00:00] [main/INFO]: " + "z" * 5000)         # >2 KB: se ignora
    escribir(log, chat("Diego_01 died"))
    primero = lector.poll()
    assert primero == []                                          # solo ha leído 256 KB
    assert lector.offset - inicio == ml.MAX_LECTURA
    segundo = lector.poll()
    assert [e.tipo for e in segundo] == ["muerte", "muerte"]


def test_retomar_el_mismo_archivo_no_pierde_lo_que_lo_desperto(log):
    """BM10: el lector se suelta tras 10 min sin cambios; al volver a abrir el MISMO latest.log
    sigue desde donde se quedó (antes el nuevo saltaba al final y perdía la línea)."""
    viejo = LectorLog(log)
    viejo.poll()
    escribir(log, chat("Diego_01 was slain by Zo"), fin="")          # una línea a medias
    viejo.poll()
    foto = viejo.instantanea()
    escribir(log, "mbie", chat("Diego_01 has made the advancement [Diamonds!]"))   # lo que lo despierta
    nuevo = LectorLog(log)
    assert nuevo.retomar(foto) is True
    assert [(e.tipo, e.detalle) for e in nuevo.poll()] == [("muerte", "Zombie"), ("logro", "Diamonds!")]
    assert nuevo.yo == YO
    # Sin retomar (u otro archivo), como siempre: salta lo viejo.
    assert LectorLog(log).poll() == []
    assert LectorLog(log.with_name("otro.log")).retomar(foto) is False
    assert LectorLog(log).retomar({"ruta": str(log)}) is False       # una foto de un lector sin arrancar


def test_retomar_tras_rotacion_lee_la_sesion_nueva(log, tmp_path):
    viejo = LectorLog(log)
    viejo.poll()
    foto = viejo.instantanea()
    os.replace(log, tmp_path / "2026-09-26-2.log")
    escribir(log, "[13:00:01] [Render thread/INFO]: Setting user: Diego_01",
             "[13:00:05] [Render thread/INFO]: Connecting to 203.0.113.7, 25565", modo="wb")
    nuevo = LectorLog(log)
    assert nuevo.retomar(foto)
    assert [e.tipo for e in nuevo.poll()] == ["sesion_inicio"]


def test_sin_archivo_no_rompe(tmp_path):
    lector = LectorLog(tmp_path / "latest.log")
    assert lector.poll() == []
    assert lector.error


def test_abre_y_cierra_en_cada_sondeo(log):
    abiertos = []

    def abrir(ruta, modo):
        f = open(ruta, modo)
        abiertos.append(f)
        return f
    lector = LectorLog(log, abrir=abrir)
    lector.poll()
    escribir(log, chat("Diego_01 died"))
    lector.poll()
    assert len(abiertos) == 2 and all(f.closed for f in abiertos)


def test_inactivo(log):
    r = Reloj(100)
    lector = LectorLog(log, ahora=r)
    lector.poll()
    r.t = 800
    assert lector.inactivo_s() == 700
    escribir(log, chat("Diego_01 died"))
    lector.poll()
    assert lector.inactivo_s() == 0


# ── Dónde está latest.log ──────────────────────────────────────────────────────

def _log_en(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    p = carpeta / "latest.log"
    p.write_text("x", encoding="utf-8")
    return p


def test_rutas_candidatas_en_los_sitios_habituales(tmp_path):
    appdata, perfil = tmp_path / "AppData" / "Roaming", tmp_path / "perfil"
    esperadas = {
        _log_en(appdata / ".minecraft" / "logs"),
        _log_en(appdata / "PrismLauncher" / "instances" / "Fabric 1.21" / ".minecraft" / "logs"),
        _log_en(appdata / "PrismLauncher" / "instances" / "Vanilla" / "minecraft" / "logs"),
        _log_en(appdata / "MultiMC" / "instances" / "A" / ".minecraft" / "logs"),
        _log_en(appdata / "ModrinthApp" / "profiles" / "Perfil" / "logs"),
        _log_en(appdata / "com.modrinth.theseus" / "profiles" / "Viejo" / "logs"),
        _log_en(perfil / "curseforge" / "minecraft" / "Instances" / "Pack" / "logs"),
    }
    (appdata / "PrismLauncher" / "instances" / "vacia").mkdir(parents=True)
    got = rutas_candidatas({"APPDATA": str(appdata), "USERPROFILE": str(perfil)})
    assert set(got) == esperadas
    assert rutas_candidatas({}) == []


def test_rutas_candidatas_con_tope(tmp_path):
    base = tmp_path / "PrismLauncher" / "instances"
    for i in range(80):
        _log_en(base / f"i{i:03d}" / ".minecraft" / "logs")
    assert len(rutas_candidatas({"APPDATA": str(tmp_path)})) == 64


def test_elegir_log_por_mtime_y_reciente(tmp_path):
    a = _log_en(tmp_path / "a")
    b = _log_en(tmp_path / "b")
    ahora = time.time()
    os.utime(a, (ahora - 30, ahora - 30))
    os.utime(b, (ahora - 5000, ahora - 5000))
    assert elegir_log("", [b, a], ahora=ahora) == a
    assert elegir_log("", [b], ahora=ahora, reciente_s=600) is None
    assert elegir_log("", [b], ahora=ahora, reciente_s=None) == b
    assert elegir_log("", [tmp_path / "no" / "latest.log"], ahora=ahora) is None
    assert elegir_log("", [a], ahora=lambda: ahora, reciente_s=60) == a


def test_elegir_log_configurado(tmp_path):
    a = _log_en(tmp_path / "logs")
    otro = tmp_path / "otro.txt"
    otro.write_text("x", encoding="utf-8")
    assert elegir_log(str(a), [], ahora=0) == a
    assert elegir_log(f'"{a}"', [], ahora=0) == a
    assert elegir_log(str(otro), [a], ahora=0) is None               # no termina en latest.log
    assert elegir_log(r"\\servidor\recurso\latest.log", [a], ahora=0) is None     # UNC fuera
    assert elegir_log("//servidor/recurso/latest.log", [a], ahora=0) is None
    assert elegir_log(str(tmp_path / "falta" / "latest.log"), [a], ahora=0) is None
