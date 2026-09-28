"""
Tests de ui/alarmas_qt.ControlAlarmasQt (offscreen, con ServiciosEscritorio de
verdad y mutex, entrada, pantalla grande, mascota, voz, tarjeta y mezclador falsos):

- al sonar: prioridad «alarma» en el bus; `grande.entrar("alarma")` +
  `mostrar_alarma(texto)`; sin pantalla grande → burbuja + tarjeta; si la
  grande no puede, burbuja; dormida → la despierta; señal `sonando` en JSON;
- con un juego → discreto (sonido + `avisar`), D3;
- la entrada falsa solo apaga tras el bloqueo; `ceder` por un juego mantiene el
  sonido y quita lo visual;
- al apagar: fuera la grande, `prioridad.terminar`, `apagada`, voz;
- `detener` deja `sonando` en alarmas.json y el siguiente dueño lo recupera;
- sin mutex no dispara (y reintenta cada 10 s); `cambio` si otro proceso edita
  el archivo; al reactivar `alarmas.activo` no se recupera nada; `perdidas`;
- API del puente: guardar_alarma (formas «HH:MM» y {hora, minuto}), parcial,
  crear_temporizador, borrar, temporizador_accion, rapido, probar, listar;
- herramientas() crean y listan y emiten `cambio`.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")

from nucleo.alarmas import Almacen  # noqa: E402
from servicios.alarmas_aviso import ControlAviso  # noqa: E402


class Cfg:
    def __init__(self, **alarmas):
        self.datos = {"alarmas": {"activo": True, "bloqueo_s": 5, "pantalla_grande": True,
                                  "decir_texto": True, "recuperar_min": 10, "posponer_min": 5}}
        self.datos["alarmas"].update(alarmas)

    def get(self, s, k, d=None):
        return self.datos.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.datos.setdefault(s, {})[k] = v


class Relojes:
    """Pared (datetime), epoch y monótono que avanzan juntos."""

    def __init__(self, inicio=datetime(2026, 9, 26, 7, 29, 58)):
        self.pared = inicio
        self.mono = 100.0

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
        self.libre = libre
        self.intentos = 0
        self.es_dueno = False
        self.liberado = 0

    def adquirir(self):
        self.intentos += 1
        self.es_dueno = self.libre
        return self.libre

    def liberar(self):
        self.liberado += 1
        self.es_dueno = False


class Entrada:
    def __init__(self):
        self.hay = False
        self.reinicios = 0

    def reiniciar(self):
        self.reinicios += 1

    def poll(self):
        h, self.hay = self.hay, False
        return h


class Grande:
    def __init__(self, diario, puede=True):
        self.diario, self.puede = diario, puede

    def entrar(self, motivo="manual", minutos=None):
        self.diario.append(("grande.entrar", motivo))
        return self.puede

    def mostrar_alarma(self, texto):
        self.diario.append(("grande.alarma", texto))
        return True

    def salir(self, motivo=None, inmediato=False):
        self.diario.append(("grande.salir", motivo))
        return True


class Mascota:
    render = "vrm"

    def __init__(self, diario):
        self.diario = diario

    def isVisible(self):
        return True

    def mostrar_alarma(self, texto, retraso_ms=3000):
        self.diario.append(("mascota.alarma", texto))

    def ocultar_alarma(self):
        self.diario.append(("mascota.ocultar",))

    def despertar(self):
        self.diario.append(("mascota.despertar",))


class Voz:
    def __init__(self):
        self.dicho = []

    def speak(self, t):
        self.dicho.append(t)


class Mezclador:
    def __init__(self):
        self.sonando = {}
        self._n = 0

    def cargar_wav(self, ruta):
        return Path(ruta).name

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self._n += 1
        self.sonando[self._n] = (buf, bucle, canal)
        return self._n

    def detener(self, sid):
        self.sonando.pop(sid, None)

    def detener_canal(self, canal):
        self.sonando = {k: v for k, v in self.sonando.items() if v[2] != canal}


def _dialogo_falso(diario):
    from PyQt6.QtCore import QObject, pyqtSignal

    class Dialogo(QObject):
        apagar = pyqtSignal()
        posponer = pyqtSignal()

        def set_disparo(self, texto, **kw):
            diario.append(("dialogo.texto", texto, kw.get("bloqueo_ms")))

        def mostrar(self):
            diario.append(("dialogo.mostrar",))

        def cerrar(self):
            diario.append(("dialogo.cerrar",))

    return Dialogo


@pytest.fixture
def entorno(qapp, tmp_path):
    from ui.escritorio import ServiciosEscritorio
    from ui.alarmas_qt import ControlAlarmasQt

    creados = []

    def crear(cfg=None, *, mutex=None, grande=True, juego=False, ruta=None, puede_grande=True, mutex_app=None):
        r = Relojes()
        diario = []
        cfg = cfg or Cfg()
        esc = ServiciosEscritorio(config=cfg)
        alm = Almacen(ruta or (tmp_path / "alarmas.json"), reloj=r.epoch)
        mez = Mezclador()
        aviso = ControlAviso(mezclador=mez, almacen=alm, reloj=r.monotono, epoch=r.epoch, lanzar=lambda f: f())
        avisos = []
        m = Mascota(diario)
        g = Grande(diario, puede_grande) if grande else None
        voz = Voz()
        ctl = ControlAlarmasQt(esc, cfg, voice=voz, grande=g, avisar=avisos.append, almacen=alm,
                               aviso=aviso, mutex=mutex or Mutex(), entrada=Entrada(),
                               ahora=r.ahora, epoch=r.epoch, reloj=r.monotono,
                               dialogo=_dialogo_falso(diario), intervalo_ms=10 ** 6, retraso_entrada_ms=0,
                               mutex_app=mutex_app)
        esc.registrar("alarmas", ctl, ("alarma",))
        esc.set_mascota(m)
        if juego:
            esc.prioridad.iniciar("juego")
        esc.iniciar()
        senales = {"sonando": [], "apagada": [], "cambio": [], "perdidas": []}
        ctl.sonando.connect(lambda s: senales["sonando"].append(json.loads(s)))
        ctl.apagada.connect(lambda: senales["apagada"].append(1))
        ctl.cambio.connect(lambda s: senales["cambio"].append(json.loads(s)))
        ctl.perdidas.connect(lambda s: senales["perdidas"].append(json.loads(s)))
        e = type("E", (), dict(ctl=ctl, esc=esc, alm=alm, mez=mez, relojes=r, diario=diario, avisos=avisos,
                               voz=voz, senales=senales, mascota=m, grande=g, cfg=cfg))()
        creados.append(e)
        return e

    yield crear
    for e in creados:
        e.esc.detener()


def _sonar_alarma(e, texto="gimnasio"):
    e.alm.crear_alarma(7, 30, texto=texto)
    e.ctl._tic()                     # 07:29:58: nada
    e.relojes.avanzar(3)             # 07:30:01
    e.ctl._tic()


def test_suena_con_pantalla_grande_y_prioridad(entorno):
    e = entorno()
    _sonar_alarma(e)
    assert e.ctl.aviso.sonando is not None and e.ctl.aviso.sonando.texto == "gimnasio"
    assert e.esc.estado.actual().alarma is True
    assert ("grande.entrar", "alarma") in e.diario and ("grande.alarma", "gimnasio") in e.diario
    (buf, bucle, canal), = e.mez.sonando.values()
    assert bucle and canal == "alarma"
    s, = e.senales["sonando"]
    assert s["texto"] == "gimnasio" and s["tipo"] == "alarma" and s["programado"] == "07:30"
    assert s["apagar_en_ms"] == 5000 and s["visual"] == "grande" and s["cola"] == 0
    # Tras apagar: sale de la grande, suelta la prioridad, emite apagada y habla.
    e.relojes.avanzar(6)
    assert e.ctl.apagar()
    assert ("grande.salir", "alarma") in e.diario
    assert e.esc.estado.actual().alarma is False
    assert e.senales["apagada"] == [1] and e.voz.dicho == ["gimnasio"] and e.mez.sonando == {}


def test_juego_discreto_suena_y_avisa(entorno):
    e = entorno(juego=True)
    _sonar_alarma(e)
    assert e.mez.sonando                                     # D3: suena aunque haya juego
    assert not any(x[0].startswith("grande") for x in e.diario)
    assert e.avisos == ["⏰ gimnasio"]
    assert e.senales["sonando"][0]["visual"] == "discreto"
    assert e.esc.estado.actual().alarma is False and e.esc.estado.actual().juego is True
    e.relojes.avanzar(6)
    e.ctl.apagar()
    assert e.esc.estado.actual().juego is True             # no se toca el juego


def test_sin_pantalla_grande_burbuja_y_tarjeta(entorno):
    e = entorno(Cfg(pantalla_grande=False))
    _sonar_alarma(e)
    assert ("mascota.alarma", "gimnasio") in e.diario
    assert ("dialogo.texto", "gimnasio", 5000) in e.diario and ("dialogo.mostrar",) in e.diario
    assert e.senales["sonando"][0]["visual"] == "burbuja"
    e.relojes.avanzar(6)
    e.ctl._dialogo.apagar.emit()                            # botón «Apagar» de la tarjeta
    assert e.ctl.aviso.sonando is None
    assert ("dialogo.cerrar",) in e.diario and ("mascota.ocultar",) in e.diario


def test_si_la_grande_no_puede_va_a_burbuja(entorno):
    e = entorno(puede_grande=False)
    _sonar_alarma(e)
    assert e.senales["sonando"][0]["visual"] == "burbuja"
    assert ("mascota.alarma", "gimnasio") in e.diario
    e.relojes.avanzar(6)
    e.ctl.apagar()
    assert ("grande.salir", "alarma") not in e.diario


def test_despierta_a_la_mascota_dormida(entorno):
    e = entorno()
    e.esc.estado.actualizar(durmiendo=True)
    _sonar_alarma(e)
    assert ("mascota.despertar",) in e.diario


def test_entrada_solo_apaga_tras_el_bloqueo(entorno):
    e = entorno()
    _sonar_alarma(e)
    ent = e.ctl._entrada
    assert ent.reinicios >= 1
    e.relojes.avanzar(2)
    ent.hay = True
    e.ctl._tic_entrada()                                     # durante el bloqueo: se consume
    assert e.ctl.aviso.sonando is not None
    e.relojes.avanzar(4)
    e.ctl._tic_entrada()                                     # sin entrada nueva: nada
    assert e.ctl.aviso.sonando is not None
    ent.hay = True
    e.ctl._tic_entrada()
    assert e.ctl.aviso.sonando is None and e.senales["apagada"] == [1]


def test_ceder_por_juego_mantiene_el_sonido(entorno):
    e = entorno()
    _sonar_alarma(e)
    e.esc.prioridad.iniciar("juego")                         # entra un juego con la alarma sonando
    assert e.mez.sonando and e.ctl.aviso.sonando is not None
    assert ("mascota.ocultar",) in e.diario
    assert e.avisos == ["⏰ gimnasio (sigue sonando)"]
    assert e.senales["sonando"][-1]["visual"] == "discreto"
    e.relojes.avanzar(6)
    e.ctl.apagar()
    assert e.esc.estado.actual().juego is True and e.senales["apagada"] == [1]


def test_detener_persiste_sonando_y_el_siguiente_lo_recupera(entorno, tmp_path):
    e = entorno()
    _sonar_alarma(e)
    e.esc.detener()
    assert e.mez.sonando == {} and e.ctl._mutex.liberado == 1
    assert [d.origen for d in e.alm.sonando()] == ["a1"]
    assert e.esc.estado.actual().alarma is False
    # Otra interfaz (u otro proceso) arranca 2 minutos después sobre el mismo archivo.
    e2 = entorno()
    e2.relojes.pared = e.relojes.pared + timedelta(minutes=2)
    e2.ctl._tic()
    d = e2.ctl.aviso.sonando
    assert d is not None and d.origen == "a1"
    assert e2.senales["sonando"][0]["texto"] == "gimnasio (hace 2 min)"


def test_sin_mutex_no_dispara_y_reintenta_cada_10_s(entorno):
    m = Mutex(libre=False)
    e = entorno(mutex=m)
    _sonar_alarma(e)
    assert e.ctl.aviso.sonando is None and m.intentos == 1
    e.relojes.avanzar(5)
    e.ctl._tic()
    assert m.intentos == 1
    e.relojes.avanzar(6)
    m.libre = True
    e.ctl._tic()
    assert m.intentos == 2 and e.ctl.dueno
    assert e.ctl.aviso.sonando is not None                   # 07:30 con ≤10 min: se recupera
    assert e.senales["sonando"][0]["texto"] == "gimnasio"


def test_cambio_si_otro_proceso_edita(entorno, tmp_path):
    e = entorno(mutex=Mutex(libre=False))
    e.ctl._tic()
    antes = len(e.senales["cambio"])
    Almacen(tmp_path / "alarmas.json").crear_alarma(9, 0, texto="de fuera")
    e.ctl._tic()
    assert len(e.senales["cambio"]) == antes + 1
    assert e.senales["cambio"][-1]["alarmas"][0]["texto"] == "de fuera"
    e.ctl._tic()
    assert len(e.senales["cambio"]) == antes + 1             # sin cambios, sin señal


def test_reactivar_no_recupera(entorno):
    cfg = Cfg()
    e = entorno(cfg)
    e.alm.crear_alarma(7, 30)
    e.ctl._tic()
    cfg.set("alarmas", "activo", False)
    e.ctl._tic()
    e.relojes.avanzar(5 * 60)                                # 07:35 con las alarmas apagadas
    e.ctl._tic()
    cfg.set("alarmas", "activo", True)
    e.ctl._tic()
    assert e.ctl.aviso.sonando is None and e.senales["perdidas"] == []


def test_desactivar_calla_lo_que_suena(entorno):
    cfg = Cfg()
    e = entorno(cfg)
    _sonar_alarma(e)
    cfg.set("alarmas", "activo", False)
    e.ctl._tic()
    assert e.ctl.aviso.sonando is None and e.alm.sonando() == [] and e.senales["apagada"] == [1]


def test_perdidas_se_avisan(entorno, tmp_path):
    alm = Almacen(tmp_path / "alarmas.json")
    alm.crear_alarma(7, 0, texto="gimnasio")
    alm.marcar_visto(datetime(2026, 9, 26, 6, 0).timestamp())
    e = entorno()
    e.ctl._tic()                                              # 07:29:58: se pasó hace 30 min
    assert e.ctl.aviso.sonando is None
    assert e.avisos == ["Se pasó la alarma de las 07:00 «gimnasio» mientras Lune no estaba"]
    p, = e.senales["perdidas"][0]
    assert p["cuando"] == "07:00" and p["texto"] == "gimnasio"


def test_cola_y_texto_siguiente(entorno):
    e = entorno()
    e.alm.crear_alarma(7, 30, texto="uno")
    e.alm.crear_alarma(7, 30, texto="dos")
    e.relojes.avanzar(3)
    e.ctl._tic()
    assert e.ctl.aviso.sonando.texto == "uno" and len(e.ctl.aviso.cola) == 1
    assert [(s["texto"], s["cola"]) for s in e.senales["sonando"]] == [("uno", 0), ("uno", 1)]
    e.relojes.avanzar(6)
    e.ctl.apagar()
    assert e.ctl.aviso.sonando.texto == "dos"
    assert ("grande.alarma", "dos") in e.diario
    assert e.esc.estado.actual().alarma is True              # sigue la alarma: no se suelta
    assert e.senales["apagada"] == []


def test_posponer_crea_pospuesta_y_emite_cambio(entorno):
    e = entorno()
    _sonar_alarma(e)
    e.relojes.avanzar(6)
    n = len(e.senales["cambio"])
    assert e.ctl.posponer()
    t, = e.alm.temporizadores()
    assert t.pospuesta and t.duracion_s == 300 and len(e.senales["cambio"]) == n + 1
    assert e.voz.dicho == []


def test_api_guardar_y_listar(entorno):
    e = entorno()
    r = e.ctl.guardar_alarma({"hora": "07:30", "dias": "lmxjv", "texto": "gimnasio"})
    assert r["ok"] and r["id"] == "a1"
    r = e.ctl.guardar_alarma({"hora": 22, "minuto": 15, "dias": 96, "una_vez": False, "texto": "x",
                              "activa": True})                       # forma de ui/puente_alarmas.py
    assert r["ok"]
    a2 = e.alm.obtener(r["id"])
    assert (a2.hora, a2.minuto, a2.dias) == (22, 15, 96)
    assert e.ctl.guardar_alarma({"id": "a1", "activa": False})["ok"]
    assert e.alm.obtener("a1").activa is False and e.alm.obtener("a1").hhmm == "07:30"
    assert not e.ctl.guardar_alarma({"hora": "25:00"})["ok"]
    assert not e.ctl.guardar_alarma({"texto": "sin hora"})["ok"]
    assert not e.ctl.guardar_alarma({"id": "../x", "hora": "07:00"})["ok"]
    est = e.ctl.listar()
    a1 = est["alarmas"][0]
    assert a1["hora"] == "07:30" and a1["minuto"] == 30 and a1["dias"] == "lmxjv"
    assert a1["dias_texto"] == "de lunes a viernes" and a1["activa"] is False
    assert est["activo"] is True and est["sonando"] is None


def test_api_temporizadores(entorno):
    e = entorno()
    r = e.ctl.crear_temporizador({"h": 0, "m": 10, "s": 0, "texto": "pizza"})
    assert r["ok"]
    t = e.ctl.listar()["temporizadores"][0]
    assert t["duracion_s"] == 600 and t["corriendo"] and t["falta_s"] == 600
    assert e.ctl.temporizador_accion(t["id"], "parar")
    assert not e.ctl.listar()["temporizadores"][0]["corriendo"]
    assert not e.ctl.temporizador_accion(t["id"], "volar")
    assert e.ctl.crear_temporizador({"segundos": 90, "iniciar": False})["ok"]
    assert not e.ctl.crear_temporizador({"segundos": 0})["ok"]
    assert e.ctl.borrar(t["id"]) and not e.ctl.borrar(t["id"])
    r = e.ctl.rapido(5)
    assert r["ok"]
    rap = e.alm.obtener(r["id"])
    assert rap.duracion_s == 300 and rap.una_vez


def test_probar_suena_sin_guardarse(entorno):
    e = entorno()
    assert e.ctl.probar()
    assert e.ctl.aviso.sonando.tipo == "prueba" and e.alm.sonando() == []
    e.relojes.avanzar(6)
    e.ctl.apagar()
    assert e.voz.dicho == []


def test_herramientas_crean_listan_y_avisan(entorno, qapp):
    e = entorno()
    h = e.ctl.herramientas()
    assert set(h) == {"temporizador", "alarma", "cancelar_alarma", "listar_alarmas"}
    n = len(e.senales["cambio"])
    assert "t1" in h["temporizador"]({"segundos": 60, "texto": "té"}, None)
    assert "a1" in h["alarma"]({"hora": "08:00", "dias": "", "texto": "café"}, {"origen": "modelo"})
    assert "té" in h["listar_alarmas"]({}, None)
    qapp.processEvents()
    assert len(e.senales["cambio"]) >= n + 1
    assert [x["texto"] for x in e.senales["cambio"][-1]["temporizadores"]] == ["té"]


def test_herramientas_en_el_escritorio(entorno):
    from servicios.tools import ToolManager
    e = entorno()
    tm = ToolManager()
    e.esc.conectar_herramientas(tm)
    for nombre, fn in e.ctl.herramientas().items():
        e.esc.registrar_herramienta(nombre, fn)
    r = tm.ejecutar("temporizador", args={"segundos": 120})
    assert r.ok and e.alm.temporizadores()[0].duracion_s == 120


# ── Revisión 4-5-6 ─────────────────────────────────────────────────────────────

def test_la_app_tiene_el_mutex_de_presencia_mientras_esta_en_marcha(entorno):
    """MO8: la app es la dueña preferente: mientras sus alarmas están en marcha tiene el
    mutex `…_app` (patata lo ve y le cede las alarmas); lo suelta al detenerse."""
    app = Mutex()
    e = entorno(mutex_app=app)
    assert app.es_dueno and app.intentos == 1
    e.ctl._tic()
    assert app.intentos == 1, "ya lo tiene: no lo vuelve a pedir"
    e.esc.detener()
    assert app.liberado == 1 and not app.es_dueno


def test_el_mutex_de_presencia_se_reintenta_cada_10_s(entorno):
    app = Mutex(libre=False)
    e = entorno(mutex_app=app)
    assert app.intentos == 1
    e.relojes.avanzar(5)
    e.ctl._tic()
    assert app.intentos == 1
    app.libre = True
    e.relojes.avanzar(6)
    e.ctl._tic()
    assert app.intentos == 2 and app.es_dueno


def test_el_tic_que_falla_traza_una_vez_y_vuelve_a_trazar_si_cambia(entorno, caplog):
    """SB1: con un fallo permanente (p. ej. alarmas.json imposible) el tic dejaba una traza
    por segundo en el log."""
    import logging
    e = entorno()
    fallo = {"msg": "'int' object is not iterable"}

    def roto(*_a):
        if fallo["msg"]:
            raise TypeError(fallo["msg"])
        return [], []
    e.ctl.programador.tick = roto
    with caplog.at_level(logging.ERROR, logger="lune.alarmas"):
        for _ in range(5):
            e.relojes.avanzar(1)
            e.ctl._tic()
        assert sum("el tic falló" in r.getMessage() for r in caplog.records) == 1
        fallo["msg"] = ""                                   # se arregla…
        e.ctl._tic()
        fallo["msg"] = "otra cosa"                          # …y vuelve a fallar: nueva traza
        e.ctl._tic()
        e.ctl._tic()
    assert sum("el tic falló" in r.getMessage() for r in caplog.records) == 2


def test_detener_borra_la_tarjeta_y_el_editor(entorno, qapp):
    """VS8: tarjeta y editor (sin padre) se quedaban huérfanos en cada cambio de interfaz:
    detener() solo los cerraba y el editor seguía en `_editor`."""
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    from ui.alarmas_dialogo import DialogoAlarma, DialogoAlarmas
    e = entorno()
    tarjeta = DialogoAlarma()
    editor = DialogoAlarmas(e.ctl)
    e.ctl._dialogo, e.ctl._editor = tarjeta, editor
    e.esc.detener()
    assert e.ctl._dialogo is None and e.ctl._editor is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    assert sip.isdeleted(tarjeta) and sip.isdeleted(editor)


# ── Revisión 7-10 (sospecha RR1) ───────────────────────────────────────────────

def test_herramienta_en_curso_con_el_controlador_ya_borrado(entorno, qapp, caplog):
    """Una herramienta del modelo en curso (hilo del Ejecutor) mientras el cambio de
    interfaz borra el controlador: `al_cambiar` era el `emit` ligado de `_refresco` y se
    llamaba sobre el objeto borrado (AttributeError tragado… o una access violation).
    Ahora pasa por un PuenteHilo: cerrado en `detener`, no hace nada."""
    import logging
    import threading
    from PyQt6 import sip
    e = entorno()
    h = e.ctl.herramientas()["temporizador"]
    e.esc.quitar("alarmas")                          # el desmontaje: detener…
    sip.delete(e.ctl)                                # …y el objeto de C++ se va
    caplog.set_level(logging.DEBUG, logger="lune.alarmas")
    caja = {}
    hilo = threading.Thread(target=lambda: caja.update(r=h({"segundos": 60, "texto": "té"}, None)))
    hilo.start()
    hilo.join()
    qapp.processEvents()
    assert "t1" in caja["r"] and e.alm.temporizadores()[0].texto == "té"
    assert not [r for r in caplog.records if "al_cambiar" in r.getMessage()]


def test_detener_e_iniciar_otra_vez_vuelve_a_avisar_del_cambio(entorno, qapp):
    e = entorno()
    h = e.ctl.herramientas()["temporizador"]
    e.ctl.detener()
    e.ctl.iniciar()
    n = len(e.senales["cambio"])
    import threading
    hilo = threading.Thread(target=lambda: h({"segundos": 30, "texto": "otra"}, None))
    hilo.start()
    hilo.join()
    for _ in range(10):
        qapp.processEvents()
    assert len(e.senales["cambio"]) > n
