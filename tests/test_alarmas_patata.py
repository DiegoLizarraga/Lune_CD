"""
Tests de servicios/alarmas_patata.AlarmasTerminal (sin Qt), con la ConsolaAsincrona
de verdad (API de Windows falsa, stdin que no llega) y mutex, mezclador y relojes falsos:

- comandos: /alarma, /alarma probar, /alarmas [on|off], /borrar_alarma <id|n>,
  /timer, /timers, /apagar, /posponer; lo que no es suyo → None;
- al sonar: banner encima del prompt, `\\a` + parpadeo, capa de título «⏰ …» con
  prioridad 60 (o `titulo` si la consola no tiene capas) y reclamo «Enter apaga»;
- Enter durante el bloqueo se consume con «(espera N s)»; después apaga; «p»
  pospone; otra línea apaga y sigue al chat; el prompt cuenta atrás;
- sin mutex no dispara; el hilo arranca y `detener` suelta el mutex;
- herramientas en un ToolManager.
"""
import io
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.alarmas import Almacen  # noqa: E402
from servicios.alarmas_aviso import ControlAviso  # noqa: E402
from servicios.alarmas_patata import AlarmasTerminal  # noqa: E402


class Cfg:
    def __init__(self, **alarmas):
        self.d = {"alarmas": {"activo": True, "bloqueo_s": 5, "posponer_min": 5, "decir_texto": True,
                              "recuperar_min": 10}}
        self.d["alarmas"].update(alarmas)

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = v


class Relojes:
    def __init__(self):
        self.pared = datetime(2026, 9, 26, 7, 29, 58)
        self.mono = 50.0

    def avanzar(self, s):
        self.pared += timedelta(seconds=s)
        self.mono += s

    def ahora(self):
        return self.pared

    def epoch(self):
        return self.pared.timestamp()

    def monotono(self):
        return self.mono


class Mutex:
    def __init__(self, libre=True):
        self.libre, self.es_dueno, self.liberado = libre, False, 0

    def adquirir(self):
        self.es_dueno = self.libre
        return self.libre

    def liberar(self):
        self.liberado += 1
        self.es_dueno = False


class Mezclador:
    def __init__(self):
        self.sonando = {}
        self._n = 0

    def cargar_wav(self, r):
        return Path(r).name

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self._n += 1
        self.sonando[self._n] = (buf, bucle, canal)
        return self._n

    def detener(self, sid):
        self.sonando.pop(sid, None)

    def detener_canal(self, canal):
        self.sonando = {k: v for k, v in self.sonando.items() if v[2] != canal}


class ApiFalsa:
    def __init__(self):
        self.titulos, self.parpadeos = [], 0

    def habilitar_vt(self):
        return False

    def es_consola_entrada(self):
        return False

    def titulo(self, t):
        self.titulos.append(t)
        return True

    def parpadear(self, veces=3, hasta_foco=True):
        self.parpadeos += 1
        return True


class StdinQueNoLlega:
    def __init__(self):
        self.fin = threading.Event()

    def readline(self):
        self.fin.wait()
        return ""


class Voz:
    def __init__(self):
        self.dicho = []

    def speak(self, t):
        self.dicho.append(t)


@pytest.fixture
def terminal(tmp_path):
    from nucleo.consola import ConsolaAsincrona
    creados = []

    def crear(*, mutex=None, consola=None, cfg=None, mutex_app=None):
        r = Relojes()
        salida = io.StringIO()
        api = ApiFalsa()
        stdin = StdinQueNoLlega()
        con = consola or ConsolaAsincrona("tú > ", stdout=salida, stdin=stdin, api=api, ansi=False)
        alm = Almacen(tmp_path / "alarmas.json", reloj=r.epoch)
        mez = Mezclador()
        voz = Voz()
        colores = {"red": "<R>", "bold": "<B>", "dim": "<D>", "reset": "</>", "cyan": "", "yellow": ""}
        term = AlarmasTerminal(con, cfg or Cfg(), voice=voz, colores=colores, almacen=alm, mezclador=mez,
                               mutex=mutex or Mutex(), reloj=r.monotono, ahora=r.ahora, epoch=r.epoch,
                               lanzar_sonido=lambda f: f(), mutex_app=mutex_app)
        e = type("E", (), dict(t=term, con=con, salida=salida, api=api, alm=alm, mez=mez, r=r, voz=voz,
                               stdin=stdin))()
        creados.append(e)
        return e

    yield crear
    for e in creados:
        e.t.detener()
        e.stdin.fin.set()
        try:
            e.con.detener()
        except Exception:
            pass


def _sonar(e, texto="gimnasio"):
    e.alm.crear_alarma(7, 30, texto=texto)
    e.t.tic()
    e.r.avanzar(3)
    e.t.tic()


def _linea(e, texto):
    """Como si la persona escribiera `texto` + Enter."""
    e.con._despachar(texto)


def test_comandos_alarmas(terminal):
    e = terminal()
    assert e.t.comando("hola") is None and e.t.comando("/ayuda") is None
    assert "Uso" in e.t.comando("/alarma")
    r = e.t.comando("/alarma 07:30 lmxjv gimnasio")
    assert "a1" in r and "de lunes a viernes" in r and "gimnasio" in r
    r = e.t.comando("/alarma 22:00 pastillas de la noche")
    a2 = e.alm.obtener("a2")
    assert (a2.una_vez, a2.dias, a2.texto) == (True, 0, "pastillas de la noche") and "una vez" in r
    e.t.comando("/alarma 6:15 todos correr")
    a3 = e.alm.obtener("a3")
    assert (a3.una_vez, a3.dias, a3.texto) == (False, 127, "correr")
    assert "hora no válida" in e.t.comando("/alarma 25:00 x")
    lista = e.t.comando("/alarmas")
    assert "a1 · 07:30" in lista and "a2 · 22:00" in lista
    assert "Quitado la alarma «pastillas de la noche» (a2)" in e.t.comando("/borrar_alarma a2")
    assert "(a1)" in e.t.comando("/borrar_alarma 1")                   # por número de la lista
    assert "No encuentro" in e.t.comando("/borrar_alarma 9")
    assert "Uso" in e.t.comando("/borrar_alarma")


def test_comandos_timer(terminal):
    e = terminal()
    assert "Uso" in e.t.comando("/timer")
    r = e.t.comando("/timer 10m sacar la pizza")
    t, = e.alm.temporizadores()
    assert (t.duracion_s, t.texto, t.una_vez) == (600, "sacar la pizza", True) and "t1" in r
    e.t.comando("/timer 5 min té")
    assert e.alm.obtener("t2").duracion_s == 300 and e.alm.obtener("t2").texto == "té"
    assert "No entiendo" in e.t.comando("/timer ya mismo")
    r = e.t.comando("/timers")
    assert "t1 · 10 min · sacar la pizza · quedan 10:00" in r
    assert e.t.comando("/apagar") == "No suena ninguna alarma."


def test_alarmas_on_off(terminal):
    e = terminal()
    assert "apagadas" in e.t.comando("/alarmas off")
    assert e.t.config.get("alarmas", "activo") is False
    assert "/alarmas on" in e.t.comando("/alarmas")
    assert e.t.comando("/alarmas on") == "Alarmas encendidas."


def test_al_sonar_banner_titulo_parpadeo_y_reclamo(terminal):
    e = terminal()
    _sonar(e)
    out = e.salida.getvalue()
    assert "<R><B>⏰ ALARMA</> <B>07:30</>  <B>gimnasio</>" in out
    assert "Enter apaga · p pospone 5 min" in out
    assert "\a" in out and e.api.parpadeos == 1
    assert any("⏰ gimnasio" in t for t in e.api.titulos)
    assert e.con.reclamada
    (buf, bucle, canal), = e.mez.sonando.values()
    assert bucle and canal == "alarma"


def test_enter_durante_el_bloqueo_espera_y_luego_apaga(terminal):
    e = terminal()
    _sonar(e)
    e.r.avanzar(2)
    _linea(e, "")
    assert "(espera 3 s)" in e.salida.getvalue()
    assert e.t.aviso.sonando is not None and e.con.reclamada          # se consumió y vuelve a esperar
    e.r.avanzar(4)
    _linea(e, "")
    assert e.t.aviso.sonando is None and not e.con.reclamada
    assert e.mez.sonando == {} and e.voz.dicho == ["gimnasio"]
    assert e.alm.sonando() == []


def test_p_pospone(terminal):
    e = terminal()
    _sonar(e)
    e.r.avanzar(6)
    _linea(e, "p")
    t, = e.alm.temporizadores()
    assert t.pospuesta and t.duracion_s == 300 and "Pospuesta 5 min" in e.salida.getvalue()
    assert e.t.aviso.sonando is None and e.voz.dicho == []


def test_otra_linea_apaga_y_sigue_al_chat(terminal):
    e = terminal()
    _sonar(e)
    e.r.avanzar(1)
    _linea(e, "hola lune")                    # durante el bloqueo: no se pierde, va al chat
    assert e.t.aviso.sonando is not None and e.con.reclamada
    assert list(e.con._cola_chat)[-1][0] == "hola lune"
    e.r.avanzar(5)
    _linea(e, "qué tal")
    assert e.t.aviso.sonando is None and not e.con.reclamada
    assert list(e.con._cola_chat)[-1][0] == "qué tal"


def test_prompt_cuenta_atras(terminal):
    e = terminal()
    _sonar(e)
    assert e.t._reclamo["prompt"] == "⏰ espera 5 s… > "
    e.r.avanzar(2.5)
    e.t.tic()
    assert e.t._reclamo["prompt"] == "⏰ espera 3 s… > "
    e.r.avanzar(3)
    e.t.tic()
    assert e.t._reclamo["prompt"] == "⏰ Enter apaga · p pospone > "


def test_cola_de_dos(terminal):
    e = terminal()
    e.alm.crear_alarma(7, 30, texto="uno")
    e.alm.crear_alarma(7, 30, texto="dos")
    e.r.avanzar(3)
    e.t.tic()
    assert "⏰ En espera: dos" in e.salida.getvalue()
    e.r.avanzar(6)
    _linea(e, "")
    assert e.t.aviso.sonando.texto == "dos" and e.con.reclamada
    e.r.avanzar(6)
    _linea(e, "/apagar")
    assert e.t.aviso.sonando is None and not e.con.reclamada


def test_sin_mutex_no_dispara(terminal):
    e = terminal(mutex=Mutex(libre=False))
    _sonar(e)
    assert e.t.aviso.sonando is None and e.mez.sonando == {}
    assert not e.t.dueno


def test_capa_de_titulo_si_la_consola_la_tiene():
    class Con:
        def __init__(self):
            self.capas, self.avisos = [], []

        def titulo_capa(self, capa, texto, prioridad=0):
            self.capas.append((capa, texto, prioridad))

        def aviso(self, t):
            self.avisos.append(t)

        def parpadear(self, **kw):
            pass

        def reclamar(self, fn, prompt=None):
            return lambda: None

    con = Con()
    t = AlarmasTerminal(con, Cfg(), mutex=Mutex(), mezclador=Mezclador(), lanzar_sonido=lambda f: f())
    t.probar()
    assert con.capas == [("alarma", "⏰ Prueba de alarma", 60)]
    t.aviso.apagar(forzar=True)
    assert con.capas[-1] == ("alarma", None, 60)


def test_hilo_arranca_y_detener_suelta_el_mutex(tmp_path):
    class Con:
        def __init__(self):
            self.avisos = []

        def aviso(self, t):
            self.avisos.append(t)

        def titulo(self, t):
            pass

        def parpadear(self, **kw):
            pass

        def reclamar(self, fn, prompt=None):
            return lambda: None

    alm = Almacen(tmp_path / "alarmas.json")
    alm.crear_temporizador(1, "rápido")
    m = Mutex()
    con = Con()
    t = AlarmasTerminal(con, Cfg(), almacen=alm, mutex=m, mezclador=Mezclador(), intervalo_s=0.05,
                        lanzar_sonido=lambda f: f())
    t.iniciar()
    limite = time.monotonic() + 5
    while t.aviso.sonando is None and time.monotonic() < limite:
        time.sleep(0.05)
    assert t.aviso.sonando is not None and t.aviso.sonando.texto == "rápido"
    t.detener()
    assert m.liberado == 1 and t.aviso.sonando is None
    assert [d.origen for d in alm.sonando()] == ["t1"]          # queda para la próxima vez


def test_registrar_herramientas(terminal):
    from servicios.tools import ToolManager
    e = terminal()
    tm = ToolManager()
    e.t.registrar_herramientas(tm)
    r = tm.ejecutar("alarma", args={"hora": "07:30", "dias": "", "texto": "café"})
    assert r.ok and e.alm.alarmas()[0].texto == "café"


# ── Revisión 4-5-6 ─────────────────────────────────────────────────────────────

def test_el_enter_de_la_alarma_gana_a_una_aprobacion_pendiente(terminal):
    """MO5: con «¿Lo hago? [s/N]» pendiente (reclamo de prioridad 0, como patata.py), el
    Enter para apagar la alarma se lo llevaba la aprobación como «no» y la alarma seguía."""
    e = terminal()
    respuestas = []
    e.con.reclamar(lambda linea: respuestas.append(linea), prompt="¿Lo hago? [s/N] ")
    _sonar(e)
    assert e.con._texto_prompt().startswith("⏰")               # se ve el prompt de la alarma
    e.r.avanzar(6)
    _linea(e, "")
    assert e.t.aviso.sonando is None, "el Enter apagó la alarma"
    assert respuestas == [], "la aprobación no recibió el Enter"
    _linea(e, "s")                                              # y la aprobación sigue esperando
    assert respuestas == ["s"]


def test_la_p_de_la_alarma_no_la_recibe_la_aprobacion(terminal):
    e = terminal()
    respuestas = []
    e.con.reclamar(lambda linea: respuestas.append(linea), prompt="¿Lo hago? [s/N] ")
    _sonar(e)
    e.r.avanzar(6)
    _linea(e, "p")
    assert e.t.aviso.sonando is None and respuestas == []
    assert e.alm.temporizadores()[0].pospuesta


def test_con_la_app_abierta_patata_no_coge_las_alarmas(terminal):
    """MO8: la app es la dueña preferente. Si su mutex `…_app` está cogido, patata no se
    hace dueña aunque el de dueño esté libre."""
    m = Mutex()
    e = terminal(mutex=m, mutex_app=Mutex(libre=False))
    _sonar(e)
    assert not e.t.dueno and e.t.aviso.sonando is None and not m.es_dueno


def test_patata_cede_a_la_app_cuando_no_suena_nada(terminal):
    """MO8: patata era la dueña y se abre la app: le cede el mutex, pero una alarma sonando
    no se corta (espera a que se apague)."""
    m, app = Mutex(), Mutex()
    e = terminal(mutex=m, mutex_app=app)
    _sonar(e)                                                    # sin app: patata es la dueña y suena
    assert e.t.dueno and e.t.aviso.sonando is not None
    assert app.liberado >= 1, "comprobó que no había app y soltó su mutex al momento"
    app.libre = False                                            # se abre la app
    e.r.avanzar(11)
    e.t.tic()
    assert e.t.dueno and e.t.aviso.sonando is not None and m.liberado == 0, "sonando: no cede"
    _linea(e, "")                                                # se apaga
    assert e.t.aviso.sonando is None
    e.r.avanzar(1)
    e.t.tic()
    assert not e.t.dueno and m.liberado == 1
    assert "ella se encarga ahora de las alarmas" in e.salida.getvalue()
    # Mientras la app siga abierta, no la vuelve a coger; si se cierra, sí.
    e.r.avanzar(30)
    e.t.tic()
    assert not e.t.dueno
    app.libre = True
    e.r.avanzar(11)
    e.t.tic()
    assert e.t.dueno


def test_el_tic_que_falla_traza_una_vez(terminal, caplog):
    """SB1: un tic que falla siempre igual dejaba una traza por segundo en el log."""
    import logging
    e = terminal()

    def roto(*_a):
        raise TypeError("'int' object is not iterable")
    e.t.programador.tick = roto
    with caplog.at_level(logging.ERROR, logger="lune.alarmas"):
        for _ in range(5):
            e.r.avanzar(1)
            e.t.tic()
    assert sum("el tic falló" in r.getMessage() for r in caplog.records) == 1
