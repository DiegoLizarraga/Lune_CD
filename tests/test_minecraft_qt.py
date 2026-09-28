"""
Tests de ControlMinecraft (ui/minecraft_qt.py) con el ServiciosEscritorio de verdad
(BusEstado y estado_cambio) y dobles para todo lo demás: proceso del bot, lector del
log, mascota, anfitrión, voz y config. Nada de red, de node ni de archivos del juego.
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import minecraft_proceso as mp  # noqa: E402
from lune_core.minecraft_log import Evento  # noqa: E402


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
    def __init__(self, ruta="C:/juego/logs/latest.log"):
        self.ruta = Path(ruta)
        self.pendientes = []
        self.yo = "Diego_01"
        self.otros = False
        self.nombre_bot = ""
        self.sondeos = 0

    def poll(self):
        self.sondeos += 1
        evs, self.pendientes = self.pendientes, []
        return evs

    def inactivo_s(self):
        return 0.0


class Mascota:
    def __init__(self, visible=True, acepta=True):
        self.visible = visible
        self.acepta = acepta
        self.dichas = []

    def isVisible(self):
        return self.visible

    def decir_reaccion(self, texto, estado="happy", ms=8000):
        self.dichas.append((texto, estado, ms))
        return self.acepta


class Anfitrion:
    def __init__(self):
        self.avisos, self.reacciones = [], []

    def aviso(self, t):
        self.avisos.append(t)

    def reaccion(self, estado, ms=2500):
        self.reacciones.append((estado, ms))
        return True


class Voz:
    def __init__(self, silenciada=False):
        self.silenciada = silenciada
        self.dichos = []

    def speak(self, t):
        self.dichos.append(t)


class Juego:
    def __init__(self, exe=""):
        self.exe = exe

    def estado(self):
        return {"exe": self.exe, "activo": False}


class Azar:
    def random(self):
        return 0.0


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def escritorio(qapp):
    from ui.escritorio import ServiciosEscritorio
    e = ServiciosEscritorio(None)
    yield e
    e.deleteLater()


def montar(escritorio, *, config=None, proceso=None, lector="fijo", mascota=None, anfitrion=None, voz=None,
           datos=None, personaje=None, rutas=None, juego=None, **kw):
    from ui.minecraft_qt import ControlMinecraft
    if juego is not None:
        escritorio.registrar("juego", juego)
    lec = Lector() if lector == "fijo" else lector
    reloj = Reloj()
    ctl = ControlMinecraft(
        escritorio, config or Config(), anfitrion=anfitrion, voice=voz, proceso=proceso or Proceso(), lector=lec,
        reloj=reloj, rng=Azar(), rutas=rutas or (lambda: []), ahora=lambda: 5000.0,
        datos_mc=lambda: dict(datos or {"dueno": "Diego_01", "host": "localhost", "port": 25565}),
        personaje=lambda: dict(personaje or {"nombre": "Lune", "systemPrompt": "Eres Lune."}),
        llm=lambda: None, hilo=lambda fn, *a: fn(), **kw)
    if mascota is not None:
        ctl.set_mascota(mascota)
    ctl.reloj = reloj
    ctl.lec = lec
    return ctl


def señales(ctl):
    capt = {"estado": [], "evento": [], "chat": [], "log": []}
    ctl.estado_cambio.connect(lambda s: capt["estado"].append(json.loads(s)))
    ctl.evento.connect(lambda s: capt["evento"].append(json.loads(s)))
    ctl.chat.connect(lambda s: capt["chat"].append(json.loads(s)))
    ctl.log_bot.connect(lambda s: capt["log"].append(s))
    return capt


MUERTE = Evento("muerte", "Diego_01", "Zombie", propio=True)


# ── Reacciones ─────────────────────────────────────────────────────────────────

def test_reaccion_en_la_mascota_con_cara_y_voz(escritorio):
    m, voz = Mascota(), Voz()
    ctl = montar(escritorio, config=Config(voz_reacciones=True), mascota=m, voz=voz)
    capt = señales(ctl)
    ctl.iniciar()
    ctl.lec.pendientes = [MUERTE]
    ctl._leer()
    assert len(m.dichas) == 1 and m.dichas[0][1] == "sad" and 4000 <= m.dichas[0][2] <= 10000
    assert voz.dichos == [m.dichas[0][0]]
    assert capt["evento"][-1]["tipo"] == "muerte" and capt["evento"][-1]["entregado"] is True
    assert ctl.eventos_recientes(1)[0]["texto"] == m.dichas[0][0]
    ctl.detener()


def test_voz_silenciada_no_habla(escritorio):
    m, voz = Mascota(), Voz(silenciada=True)
    ctl = montar(escritorio, config=Config(voz_reacciones=True), mascota=m, voz=voz)
    ctl.iniciar()
    ctl._recibir(MUERTE)
    assert m.dichas and voz.dichos == []
    ctl.detener()


def test_sin_mascota_aviso_y_cara_del_anfitrion(escritorio):
    a = Anfitrion()
    ctl = montar(escritorio, anfitrion=a, mascota=Mascota(visible=False))
    ctl.iniciar()
    ctl._recibir(Evento("logro", "Diego_01", "Diamonds!", propio=True))
    assert a.avisos == ["¡Logro! «Diamonds!». Me lo apunto."]
    assert a.reacciones and a.reacciones[0][0] == "happy"
    ctl.detener()


@pytest.mark.parametrize("campo", ["arrastrando", "menu_abierto", "alarma", "grande", "salvapantallas",
                                   "hablando", "pensando"])
def test_filtro_de_estados_sin_burbuja_y_fuera_del_modo_juego_sin_resumen(escritorio, campo):
    """BM9: fuera del modo juego lo que no se puede decir NO va al resumen (antes se mezclaba
    con el de la partida siguiente); queda en los eventos recientes sin entregar."""
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    escritorio.estado.actualizar(**{campo: True})
    ctl._recibir(MUERTE)
    ctl._recibir(Evento("conexion", "Steve"))
    assert m.dichas == []
    assert ctl._resumen.vacio
    assert ctl.eventos_recientes()[0]["entregado"] is False
    ctl.detener()


def test_la_burbuja_de_la_ia_manda(escritorio):
    m = Mascota(acepta=False)
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    ctl._recibir(MUERTE)
    assert len(m.dichas) == 1 and ctl._resumen.vacio
    ctl.detener()


def test_el_resumen_es_solo_de_la_partida_en_modo_juego(escritorio, qapp, monkeypatch):
    """BM9: lo apuntado antes (o de otra partida) se vacía al ENTRAR en modo juego."""
    import ui.minecraft_qt as mq
    monkeypatch.setattr(mq, "RETRASO_RESUMEN_MS", 0)
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    ctl._resumen.anotar(Evento("muerte", "Diego_01", "Creeper", propio=True))     # de antes
    escritorio.estado.actualizar(juego=True)
    assert ctl._resumen.vacio
    ctl._recibir(Evento("logro", "Diego_01", "Cazamonstruos", propio=True))
    escritorio.estado.actualizar(juego=False)
    fin = time.monotonic() + 2
    while not m.dichas and time.monotonic() < fin:
        qapp.processEvents()
    assert m.dichas[0][0] == "Mientras jugabas: 1 logro (Cazamonstruos)."
    ctl.detener()


def test_duplicado_del_log_y_del_bot_cuenta_una_vez(escritorio):
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    ctl._recibir(MUERTE)
    ctl._recibir(Evento("muerte", "Diego_01", "zombie", fuente="bot", propio=True))
    assert len(m.dichas) == 1
    ctl.reloj.t += 9                                       # pasado el hueco (y el enfriamiento de 8 s)
    ctl._recibir(Evento("muerte", "Diego_01", "Zombie", fuente="bot", propio=True))
    assert len(m.dichas) == 2
    ctl.detener()


def test_eventos_del_bot_via_on_evento(escritorio, qapp):
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    ctl.proceso.on_evento({"tipo": "evento", "evento": "muerte", "jugador": "Diego_01", "detalle": "Zombie"})
    ctl.proceso.on_evento({"tipo": "evento", "evento": "muerte", "jugador": "Steve", "detalle": "Zombie"})
    ctl.proceso.on_evento({"tipo": "evento", "evento": "inventado", "jugador": "Diego_01"})
    qapp.processEvents()
    assert len(m.dichas) == 1 and m.dichas[0][1] == "sad"
    ctl.detener()


# ── Modo juego ─────────────────────────────────────────────────────────────────

def conectado(ctl):
    ok, _ = ctl.conectar_bot()
    assert ok
    ctl._on_bot({"tipo": "conectado", "nick": "Lune"})


def test_en_juego_lo_dice_el_bot_y_pausa_su_cerebro(escritorio):
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    ctl.iniciar()
    conectado(ctl)
    m.dichas.clear()
    escritorio.estado.actualizar(juego=True)
    assert ("autonomo", True) in ctl.proceso.pausas
    ctl.reloj.t += 10
    ctl._recibir(MUERTE)
    ctl._recibir(Evento("conexion", "Steve"))
    assert m.dichas == []
    assert len(ctl.proceso.dichos) == 1 and ctl.proceso.dichos[0].startswith("¿Otra vez?")
    assert ctl._resumen.muertes == 1
    escritorio.estado.actualizar(juego=False)
    assert ("autonomo", False) in ctl.proceso.pausas
    ctl.detener()


def test_sin_bot_en_juego_al_salir_sale_el_resumen(escritorio, qapp, monkeypatch):
    import ui.minecraft_qt as mq
    monkeypatch.setattr(mq, "RETRASO_RESUMEN_MS", 0)
    m = Mascota()
    ctl = montar(escritorio, mascota=m)
    capt = señales(ctl)
    ctl.iniciar()
    escritorio.estado.actualizar(juego=True)
    ctl._recibir(MUERTE)
    ctl.reloj.t += 9
    ctl._recibir(Evento("muerte", "Diego_01", "Creeper", propio=True))
    ctl.reloj.t += 9
    ctl._recibir(Evento("logro", "Diego_01", "Cazamonstruos", propio=True))
    assert m.dichas == [] and ctl.proceso.dichos == []
    escritorio.estado.actualizar(juego=False)
    fin = time.monotonic() + 2
    while not m.dichas and time.monotonic() < fin:
        qapp.processEvents()
    assert m.dichas[0][0] == "Mientras jugabas: 2 muertes, 1 logro (Cazamonstruos)."
    assert capt["evento"][-1]["tipo"] == "resumen"
    assert ctl._resumen.vacio
    ctl.detener()


def test_pensar_en_juego_no_pausa_y_pensando_pausa_el_llm(escritorio):
    ctl = montar(escritorio, config=Config(pensar_en_juego=True))
    ctl.iniciar()
    conectado(ctl)
    escritorio.estado.actualizar(juego=True)
    escritorio.estado.actualizar(pensando=True)
    escritorio.estado.actualizar(pensando=False)
    assert ctl.proceso.pausas == [("llm", True), ("llm", False)]
    ctl.detener()


# ── Timers y log ───────────────────────────────────────────────────────────────

def test_nada_corre_sin_reaccionar_ni_bot(escritorio):
    ctl = montar(escritorio, config=Config(reaccionar=False), lector=None)
    ctl.iniciar()
    assert not ctl._t_detectar.isActive() and not ctl._t_leer.isActive()
    assert ctl.alternar_reacciones() is True
    assert ctl._t_detectar.isActive()
    assert ctl.alternar_reacciones() is False
    assert not ctl._t_detectar.isActive() and not ctl._t_leer.isActive()
    assert ctl.config.d["minecraft"]["reaccionar"] is False
    ctl.detener()


def test_autodeteccion_con_juego(escritorio, tmp_path):
    import os
    log = tmp_path / "latest.log"
    log.write_text("x\n", encoding="utf-8")
    viejo = time.time() - 3600
    os.utime(log, (viejo, viejo))
    creados = []

    def fabrica(ruta):
        lec = Lector(str(ruta))
        creados.append(lec)
        return lec
    juego = Juego("")
    ctl = montar(escritorio, lector=fabrica, rutas=lambda: [log], juego=juego)
    ctl._ahora = time.time
    ctl.iniciar()
    assert creados == []                                   # log viejo y el juego no es Minecraft
    juego.exe = "javaw.exe"
    ctl._detectar()
    assert len(creados) == 1 and ctl._t_leer.isActive()
    assert creados[0].sondeos == 1                         # la primera lectura salta lo viejo
    assert ctl.estado()["log"] == {"ruta": str(log), "activo": True, "yo": "Diego_01"}
    ctl.detener()
    assert not ctl._t_leer.isActive() and not ctl._t_detectar.isActive()


def test_sin_auto_lee_el_log_mas_reciente(escritorio, tmp_path):
    log = tmp_path / "latest.log"
    log.write_text("x\n", encoding="utf-8")
    creados = []
    ctl = montar(escritorio, config=Config(auto_con_juego=False), lector=lambda r: creados.append(r) or Lector(str(r)),
                 rutas=lambda: [log])
    ctl.iniciar()
    assert creados == [log]
    ctl.detener()


# ── Bot ────────────────────────────────────────────────────────────────────────

def test_conectar_valida_antes_de_lanzar(escritorio):
    sin_instalar = montar(escritorio, proceso=Proceso(instalado=False))
    assert sin_instalar.conectar_bot() == (False, mp.AVISO_INSTALAR)
    sin_node = montar(escritorio, proceso=Proceso(node_ok=False))
    assert sin_node.conectar_bot() == (False, mp.AVISO_SIN_NODE)
    sin_dueno = montar(escritorio, datos={"dueno": ""})
    ok, texto = sin_dueno.conectar_bot()
    assert not ok and "dueño" in texto and sin_dueno.proceso.arranques == []


def test_conectar_manda_la_config_con_las_pausas(escritorio):
    ctl = montar(escritorio)
    capt = señales(ctl)
    ctl.iniciar()
    escritorio.estado.actualizar(juego=True, pensando=True)
    ok, texto = ctl.conectar_bot()
    assert ok and "localhost:25565" in texto
    cfg = ctl.proceso.arranques[0]
    assert cfg["tipo"] == "config" and cfg["nick"] == "Lune" and cfg["dueno"] == "Diego_01"
    assert cfg["pausa_autonomo"] is True and cfg["pausa_llm"] is True
    assert capt["estado"][-1]["bot"]["conectando"] is True
    assert ctl.conectar_bot() == (False, "El bot ya está conectado.")
    ctl._on_bot({"tipo": "conectado", "nick": "Lune"})
    assert ctl.bot_conectado and ctl.lec.nombre_bot == "Lune"
    assert capt["estado"][-1]["bot"]["conectado"] is True
    ctl.detener()


def test_desconectar_y_detener_paran_el_proceso(escritorio):
    ctl = montar(escritorio)
    ctl.iniciar()
    conectado(ctl)
    assert ctl.desconectar_bot() is True
    assert ctl.proceso.paradas == [4.0]
    assert ctl.desconectar_bot() is False
    conectado(ctl)
    ctl.detener()
    assert ctl.proceso.paradas[-1] == 2.0 and not ctl.proceso.vivo
    ctl.detener()                                          # idempotente


def test_ordenes_lista_blanca_y_desconectado(escritorio):
    ctl = montar(escritorio)
    capt = señales(ctl)
    ctl.iniciar()
    assert ctl.orden("sígueme") == (False, "El bot no está conectado.")
    conectado(ctl)
    assert ctl.orden("Sígueme", origen="modelo") == (True, "Se lo he mandado al bot.")
    assert ctl.proceso.ordenes[0][1] == "sigueme"
    ok, texto = ctl.orden("/op Diego")
    assert not ok and "no entiende" in texto and len(ctl.proceso.ordenes) == 1
    assert capt["evento"][-1]["tipo"] == "orden" and capt["evento"][-1]["fuente"] == "modelo"
    assert ctl.decir("/hola\nmundo") == (True, "Dicho.")
    assert ctl.proceso.dichos[-1] == "hola mundo"
    ctl.detener()


def test_chat_respuesta_error_y_fin(escritorio):
    ctl = montar(escritorio)
    capt = señales(ctl)
    ctl.iniciar()
    conectado(ctl)
    ctl._on_bot({"tipo": "chat", "de": "Steve", "texto": "<b>hola</b>\u0007"})
    ctl._on_bot({"tipo": "chat", "de": "<script>", "texto": "x"})
    assert capt["chat"] == [{"de": "Steve", "texto": "<b>hola</b>", "t": 5000.0}]    # texto: se pinta como texto
    assert all(e.get("tipo") != "chat" for e in ctl.eventos_recientes())
    ctl._on_bot({"tipo": "respuesta", "id": "ab12", "texto": "Voy contigo."})
    assert capt["evento"][-1]["tipo"] == "respuesta" and capt["evento"][-1]["texto"] == "Voy contigo."
    ctl._on_bot({"tipo": "estado", "vida": 18, "hambre": "mucha", "dia": False, "lluvia": 1})
    bot = ctl.estado()["bot"]
    assert (bot["vida"], bot["hambre"], bot["dia"], bot["lluvia"]) == (18, None, False, None)
    ctl._on_bot({"tipo": "error", "mensaje": "No hay ningún servidor", "fatal": True})
    assert ctl.estado()["bot"]["error"] == "No hay ningún servidor"
    ctl.proceso.vivo = False
    ctl._on_fin(1)
    assert ctl.estado()["bot"]["conectado"] is False
    ctl.detener()


def test_instalar_solo_con_el_boton_y_avisa(escritorio, qapp):
    a = Anfitrion()
    ctl = montar(escritorio, proceso=Proceso(instalado=False), anfitrion=a)
    capt = señales(ctl)
    ctl.iniciar()
    ctl.instalar_bot()
    assert capt["estado"][-1]["bot"]["instalando"] is True
    assert ctl.proceso.instalaciones == 1
    qapp.processEvents()                                   # el resultado vuelve del hilo en cola
    assert "Bot de Minecraft instalado." in a.avisos
    assert capt["estado"][-1]["bot"]["instalado"] is True and capt["estado"][-1]["bot"]["instalando"] is False
    # Las herramientas del modelo nunca instalan.
    herr = ctl.herramientas()
    assert set(herr) == {"minecraft_estado", "minecraft_orden", "minecraft_bot"}
    ctl.proceso._instalado = False
    ctl._requisitos = None
    r = herr["minecraft_bot"]({"accion": "conectar"}, {})
    assert r == (False, mp.AVISO_INSTALAR) and ctl.proceso.instalaciones == 1
    ctl.detener()


def test_herramientas_con_en_ui(escritorio):
    llamadas = []
    ctl = montar(escritorio, en_ui=lambda fn: (llamadas.append(1), fn())[1])
    ctl.iniciar()
    conectado(ctl)
    herr = ctl.herramientas()
    assert herr["minecraft_orden"]({"orden": "ven"}, None).startswith("Se lo he mandado")
    assert herr["minecraft_estado"]({}, {}).startswith("Bot de Minecraft: conectado como Lune")
    assert len(llamadas) == 2
    ctl.detener()


def test_estado_forma(escritorio, qapp):
    ctl = montar(escritorio)
    pendientes = []
    ctl._hilo = lambda fn, *a: pendientes.append(fn)        # un hilo de verdad: acaba luego
    capt = señales(ctl)
    ctl.iniciar()
    assert capt["estado"][0]["requisitos"] == {"node": None, "node_ok": None, "npm": None}   # comprobando
    pendientes.pop()()
    qapp.processEvents()                                   # los requisitos llegan del hilo
    e = ctl.estado()
    assert set(e) == {"reaccionar", "log", "bot", "requisitos", "juego", "pensando"}
    assert set(e["bot"]) >= {"instalado", "instalando", "conectando", "conectado", "servidor", "nick", "vida",
                             "hambre", "dia", "lluvia", "error"}
    assert e["requisitos"] == {"node": "v24.19.0", "node_ok": True, "npm": True}
    json.dumps(e)
    ctl.detener()


def test_con_reacciones_apagadas_solo_el_estado_del_bot(escritorio):
    m = Mascota()
    ctl = montar(escritorio, config=Config(reaccionar=False), mascota=m, lector=None)
    ctl.iniciar()
    ctl._recibir(MUERTE)
    ctl._recibir(Evento("peligro", "Diego_01", "zombie", fuente="bot"))
    assert m.dichas == []
    ctl._recibir(Evento("bot_conectado", "Lune", fuente="bot"))
    assert len(m.dichas) == 1 and m.dichas[0][1] == "happy"
    ctl.detener()


def test_desconexion_pedida_no_deja_error(escritorio):
    ctl = montar(escritorio)
    ctl.iniciar()
    conectado(ctl)
    ctl.desconectar_bot()
    ctl._on_bot({"tipo": "desconectado", "motivo": "disconnect.quitting"})
    ctl._on_fin(0)
    assert ctl.estado()["bot"]["error"] == ""
    conectado(ctl)
    ctl._on_bot({"tipo": "desconectado", "motivo": "Kicked: spam"})
    assert ctl.estado()["bot"]["error"] == "Kicked: spam"
    ctl.detener()


# ── Revisión final (RR1, RR7, BM10, BM11) ──────────────────────────────────────

def test_avisar_tras_borrar_el_controlador_no_rompe(qapp):
    """RR1: el hilo lector del bot guarda on_evento/on_log/on_fin; si avisa cuando el
    controlador ya está borrado (deleteLater tras detener, el bot aún cerrándose) no puede
    emitir sobre memoria liberada. detener suelta los avisos ANTES de parar."""
    import threading
    from PyQt6 import sip
    from PyQt6.QtCore import QObject
    from ui.minecraft_qt import ControlMinecraft
    padre = QObject()
    proceso = Proceso()
    ctl = ControlMinecraft(None, Config(), proceso=proceso, lector=Lector(), parent=padre, rutas=lambda: [],
                           datos_mc=lambda: {"dueno": "Diego_01"}, personaje=lambda: {"nombre": "Lune"},
                           llm=lambda: None, hilo=lambda fn, *a: fn())
    en_el_hilo = (proceso.on_evento, proceso.on_log, proceso.on_fin)        # lo que ya tiene el hilo lector
    ctl.detener()
    assert (proceso.on_evento, proceso.on_log, proceso.on_fin) == (None, None, None)
    del ctl
    sip.delete(padre)                                                      # el QObject de C++ ya no existe
    qapp.processEvents()
    errores = []

    def avisar():
        try:
            en_el_hilo[0]({"tipo": "conectado", "nick": "Lune"})
            en_el_hilo[1]("[bot] hola")
            en_el_hilo[2](0)
        except Exception as e:                                             # noqa: BLE001
            errores.append(e)
    avisar()
    h = threading.Thread(target=avisar)
    h.start()
    h.join(5)
    qapp.processEvents()
    assert errores == []


def test_aviso_de_un_objeto_vivo_y_cerrado(escritorio, qapp):
    from ui.minecraft_qt import _Aviso
    ctl = montar(escritorio)
    capt = señales(ctl)
    a = _Aviso(ctl, "_log_hilo")
    a("[bot] uno")
    qapp.processEvents()
    assert capt["log"] == ["[bot] uno"]
    a.cerrar()
    a("[bot] dos")
    qapp.processEvents()
    assert capt["log"] == ["[bot] uno"] and a.abierto is False
    ctl.detener()


def test_conectar_antes_de_saber_si_hay_node_conecta_al_saberlo(escritorio, qapp):
    """RR7: node --version / --help van en un hilo; «Conectar» (o el relevo) antes de saberlo no
    bloquea: conecta cuando llega la respuesta."""
    ctl = montar(escritorio)
    pendientes = []
    ctl._hilo = lambda fn, *a: pendientes.append(fn)
    ctl.iniciar()
    ok, texto = ctl.conectar_bot()
    assert ok and "Node.js" in texto and ctl.proceso.arranques == []
    while pendientes:
        pendientes.pop(0)()
    qapp.processEvents()
    assert len(ctl.proceso.arranques) == 1 and ctl.estado()["bot"]["conectando"] is True
    ctl.detener()


def test_detener_para_el_bot_en_un_hilo(escritorio):
    """RR7: detener no espera al bot en el hilo de Qt (parar puede tardar 4 s si node no
    contesta): lo manda a un hilo; ProcesoBot pone el tope y mata el árbol."""
    ctl = montar(escritorio)
    ctl.iniciar()
    conectado(ctl)
    pendientes = []
    ctl._hilo = lambda fn, *a: pendientes.append(fn)
    ctl.detener()
    assert ctl.proceso.paradas == [] and ctl.estado()["bot"]["conectado"] is False
    assert len(pendientes) == 1
    pendientes.pop()()
    assert ctl.proceso.paradas == [2.0] and not ctl.proceso.vivo


def test_detener_corta_la_instalacion(escritorio):
    class ProcesoInstalando(Proceso):
        cancelados = 0

        def cancelar_instalacion(self):
            self.cancelados += 1
            return True
    ctl = montar(escritorio, proceso=ProcesoInstalando())
    ctl.iniciar()
    ctl.detener()
    assert ctl.proceso.cancelados == 1


def test_reinstalar_con_el_bot_conectado_se_rechaza(escritorio):
    """BM11: npm ci borra node_modules, que el bot vivo está usando."""
    a = Anfitrion()
    ctl = montar(escritorio, anfitrion=a)
    ctl.iniciar()
    conectado(ctl)
    ok, texto = ctl.instalar_bot()
    assert not ok and "Desconecta el bot" in texto and ctl.proceso.instalaciones == 0
    assert ctl.estado()["bot"]["instalando"] is False and a.avisos[-1] == texto
    ctl.detener()


def test_instalando_en_otra_ventana_cuenta(escritorio):
    """RR2: la marca de «instalando» es de la carpeta del bot (otra ventana o patata)."""
    proceso = Proceso(instalado=False)
    proceso.instalando = True
    ctl = montar(escritorio, proceso=proceso)
    ctl.iniciar()
    assert ctl.estado()["bot"]["instalando"] is True
    assert ctl.instalar_bot() == (False, "Ya se está instalando.")
    assert ctl.conectar_bot() == (False, "Espera a que termine la instalación.")
    assert proceso.instalaciones == 0
    ctl.detener()


def test_log_soltado_por_inactividad_sigue_donde_se_quedo(escritorio, tmp_path):
    """BM10: tras 10 min sin cambios se suelta el lector; al volver a moverse el MISMO
    latest.log, el lector nuevo sigue desde donde se quedó (antes saltaba al final y se
    perdía la muerte que lo había despertado)."""
    from lune_core.minecraft_log import LectorLog
    log = tmp_path / "latest.log"
    log.write_text("[12:00:01] [Render thread/INFO]: Setting user: Diego_01\n", encoding="utf-8")
    t = [1000.0]
    creados = []

    def fabrica(ruta):
        lec = LectorLog(ruta, ahora=lambda: t[0])
        creados.append(lec)
        return lec
    m = Mascota()
    ctl = montar(escritorio, config=Config(auto_con_juego=False), lector=fabrica, rutas=lambda: [log], mascota=m)
    ctl.iniciar()
    assert len(creados) == 1
    t[0] += 700                                          # 11 min sin cambios → se suelta
    ctl._leer()
    assert ctl._lector is None
    with open(log, "a", encoding="utf-8") as f:
        f.write("[12:12:00] [Render thread/INFO]: [System] [CHAT] Diego_01 fue asesinado/a por Zombi\n")
    ctl._detectar()
    assert len(creados) == 2
    assert len(m.dichas) == 1 and m.dichas[0][1] == "sad"
    # Soltado a propósito (reacciones apagadas y encendidas): desde el final, como siempre.
    ctl.alternar_reacciones()
    ctl.alternar_reacciones()
    assert ctl._foto_log is None
    ctl.detener()
