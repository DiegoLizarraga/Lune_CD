"""
El actualizador en las ventanas (ui/actualizacion_qt.py), sin red ni procesos de verdad:

- ControlActualizacion (la tarjeta de la web y la nativa instalada): buscar → hay/al día,
  descargar con el progreso como mucho ~4 veces por segundo → lista, «Instalar y reiniciar»
  (descarga si falta, lanza el Setup y cierra con el «Salir» de verdad), cancelar, omitir,
  «Buscar al iniciar» y desde el código (git pull + reiniciar). ultima_comprobacion se escribe
  en el hilo de Qt.
- AvisoInicio: una vez al día, nunca en modo juego (ni busca ni avisa hasta que acabe la
  partida) y a la ventana que haya entonces.
- Contratos: la señal y las ranuras de LuneBridge que usa extra/actualizaciones.jsx, la
  tarjeta cargada en index.html y puesta en Sistema (settings.jsx), main programa el aviso y
  la nativa instalada no llama a git.
Offscreen; las búsquedas y descargas son funciones falsas y el trabajo corre en el mismo hilo.
"""
import copy
import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QCoreApplication, QMetaMethod  # noqa: E402

from servicios import actualizador as A  # noqa: E402
from ui import actualizacion_qt as AQ  # noqa: E402

KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
CARD = KIT / "extra" / "actualizaciones.jsx"


class Cfg:
    def __init__(self, **act):
        self.d = {"actualizaciones": {"rama": "master", "comprobar_al_iniciar": True,
                                      "ultima_comprobacion": "", "omitir_version": "", **act}}
        self.escrito_en = []

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.escrito_en.append((k, threading.get_ident()))
        self.d.setdefault(s, {})[k] = v


def girar(cond=lambda: False, tope_s=2.0):
    """Procesa eventos de Qt hasta que `cond()` (o se acabe el tope)."""
    fin = time.monotonic() + tope_s
    app = QCoreApplication.instance()
    while time.monotonic() < fin:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    app.processEvents()
    return cond()


def rel(version="11.4", **extra):
    r = {"ok": True, "hay_novedades": True, "nueva": True, "omitida": False, "version": version,
         "actual": "11.3", "notas": "Me actualizo sola.", "fecha": "", "pagina": A.URL_RELEASES,
         "asset": {"nombre": f"LuneCD-Setup-{version}.exe", "url": "u", "tamano": 1000},
         "sha256": "a" * 64, "instalable": True, "mensaje": f"Hay una versión nueva de mí: la {version}."}
    r.update(extra)
    return r


class Falsas:
    """Las funciones de servicios/actualizador que usa ControlActualizacion, apuntando."""

    def __init__(self, busqueda=None, pasos=(250, 500, 750, 1000), descarga=None):
        self.busqueda = busqueda if busqueda is not None else rel()
        self.pasos = pasos
        self.descarga = descarga
        self.llamadas = []
        self.hilos = []

    def buscar(self, modo, rama=None):
        self.llamadas.append(("buscar", modo, rama))
        self.hilos.append(threading.get_ident())
        return dict(self.busqueda)

    def descargar(self, info, on_progreso=None, cancelar=None):
        self.llamadas.append(("descargar", info.get("version")))
        for n in self.pasos:
            if cancelar is not None and cancelar.is_set():
                return {"ok": False, "cancelado": True, "mensaje": "Cancelé la descarga."}
            on_progreso(n, 1000)
        return self.descarga or {"ok": True, "ruta": "C:/x/LuneCD-Setup-11.4.exe", "mensaje": "Descargado y comprobado."}

    def instalar(self, ruta, sha256=""):
        self.llamadas.append(("instalar", ruta, sha256))
        return True

    def actualizar(self, rama, on_progreso=None):
        self.llamadas.append(("actualizar", rama))
        on_progreso("Trayendo cambios…")
        return {"ok": True, "actualizado": True, "requisitos_ok": True, "mensaje": "Actualizado a abc1234."}

    def reiniciar(self, salir=None):
        self.llamadas.append(("reiniciar",))
        salir(0)
        return None

    def todas(self):
        return {"buscar": self.buscar, "descargar": self.descargar, "instalar": self.instalar,
                "actualizar": self.actualizar, "reiniciar": self.reiniciar}


def control(qapp, modo="instalada", falsas=None, cfg=None, lanzar=None):
    falsas = falsas or Falsas()
    cfg = cfg or Cfg()
    salidas = []
    c = AQ.ControlActualizacion(cfg, modo=modo, salir=lambda: salidas.append(1), funciones=falsas.todas(),
                                lanzar=lanzar or (lambda fn: fn()))
    fases = []
    c.cambio.connect(lambda d: fases.append(dict(d)))
    return c, falsas, cfg, salidas, fases


# ── ControlActualizacion ───────────────────────────────────────────────────────

def test_buscar_hay_version_y_apunta_la_comprobacion_en_el_hilo_de_qt(qapp):
    def en_otro_hilo(fn):
        threading.Thread(target=fn, daemon=True).start()
    c, f, cfg, _, fases = control(qapp, lanzar=en_otro_hilo)
    assert c.buscar() is True and c.buscar() is False                  # una búsqueda a la vez
    assert fases[0]["fase"] == "buscando"
    assert girar(lambda: fases[-1]["fase"] == "hay")
    d = fases[-1]
    assert d["version"] == "11.4" and d["notas"] == "Me actualizo sola." and d["instalable"] and d["total"] == 1000
    assert f.hilos[0] != threading.get_ident()                         # la red, fuera del hilo de Qt
    assert cfg.d["actualizaciones"]["ultima_comprobacion"].endswith("Z")
    assert cfg.escrito_en == [("ultima_comprobacion", threading.get_ident())]
    assert not c.ocupado and c.info()["estado"]["fase"] == "hay"


def test_al_dia_y_error(qapp):
    c, *_, fases = control(qapp, falsas=Falsas(busqueda=rel("11.3", hay_novedades=False, nueva=False,
                                                              mensaje="Estoy al día: tengo la 11.3.")))
    c.buscar(); girar(lambda: fases[-1]["fase"] == "al_dia")
    assert fases[-1]["mensaje"].startswith("Estoy al día")
    c, *_, fases = control(qapp, falsas=Falsas(busqueda={"ok": False, "mensaje": "GitHub me pidió un respiro."}))
    c.buscar(); girar(lambda: fases[-1]["fase"] == "error")
    assert "respiro" in fases[-1]["mensaje"]


def test_descargar_con_progreso_limitado_y_lista(qapp, monkeypatch):
    c, f, _, _, fases = control(qapp, falsas=Falsas(pasos=list(range(10, 1001, 10))))
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    assert c.descargar() is True
    assert girar(lambda: fases[-1]["fase"] == "lista")
    progreso = [d for d in fases if d["fase"] == "descargando" and d["bytes"]]
    # 100 trozos casi a la vez → el primero (y, como mucho, alguno más), no 100 avisos.
    assert 1 <= len(progreso) <= 3
    assert fases[-1]["pct"] == 100 and c.info()["descargado"] is True


def test_limitador():
    t = {"v": 0.0}
    lim = AQ.Limitador(0.25, reloj=lambda: t["v"])
    assert lim(1, 100) and not lim(2, 100)
    t["v"] = 0.2
    assert not lim(3, 100)
    t["v"] = 0.26
    assert lim(4, 100) and lim(100, 100)                                 # el último siempre


def test_instalar_y_reiniciar_descarga_lanza_y_sale_de_verdad(qapp, monkeypatch):
    monkeypatch.setattr(AQ, "ESPERA_SALIR_MS", 0)
    c, f, _, salidas, fases = control(qapp)
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    assert c.instalar() is True                                          # sin descargar aún: descarga y sigue
    assert girar(lambda: salidas == [1])
    assert [x[0] for x in f.llamadas] == ["buscar", "descargar", "instalar"]
    assert f.llamadas[-1] == ("instalar", "C:/x/LuneCD-Setup-11.4.exe", "a" * 64)
    assert any(d["fase"] == "instalando" and "vuelvo a abrirme" in d["mensaje"].lower() for d in fases)


def test_instalar_sin_buscar_o_sin_sha_no_hace_nada(qapp):
    c, f, _, salidas, fases = control(qapp)
    assert c.instalar() is False and f.llamadas == [] and fases[-1]["fase"] == "error"
    c, f, _, salidas, fases = control(qapp, falsas=Falsas(busqueda=rel(instalable=False, sha256="")))
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    assert c.descargar() is False and "SHA-256" in fases[-1]["mensaje"]
    assert [x[0] for x in f.llamadas] == ["buscar"] and salidas == []


def test_instalar_si_el_setup_no_arranca(qapp, monkeypatch):
    monkeypatch.setattr(AQ, "ESPERA_SALIR_MS", 0)
    c, f, _, salidas, fases = control(qapp)
    c._f["instalar"] = lambda ruta, sha256="": False
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    c.descargar(); girar(lambda: fases[-1]["fase"] == "lista")
    assert c.instalar() is False
    girar(tope_s=0.1)
    assert salidas == [] and fases[-1]["fase"] == "error"


def test_cancelar_la_descarga(qapp):
    trabajos = []
    c, f, *_ , fases = control(qapp, lanzar=trabajos.append)
    c.buscar(); trabajos.pop()(); girar(lambda: fases[-1]["fase"] == "hay")
    assert c.cancelar() is False                                         # nada que cancelar
    c.descargar()
    assert c.cancelar() is True
    trabajos.pop()()
    assert girar(lambda: fases[-1]["fase"] == "hay")
    assert "Cancelé" in fases[-1]["mensaje"] and not c.ocupado


def test_omitir_y_buscar_al_iniciar(qapp):
    c, f, cfg, _, fases = control(qapp)
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    assert c.omitir("v11.4") is True and cfg.d["actualizaciones"]["omitir_version"] == "11.4"
    assert fases[-1]["fase"] == "al_dia" and fases[-1]["omitida"]
    assert c.omitir("") is True and cfg.d["actualizaciones"]["omitir_version"] == ""
    assert fases[-1]["fase"] == "hay"
    assert c.omitir("basura") is False
    assert c.al_iniciar(False) is True and cfg.d["actualizaciones"]["comprobar_al_iniciar"] is False
    i = c.info()
    assert i["al_iniciar"] is False and i["modo"] == "instalada" and i["version"] == A.version_actual()


def test_desde_el_codigo_git_pull_y_reinicio(qapp, monkeypatch):
    monkeypatch.setattr(AQ, "ESPERA_SALIR_MS", 0)
    git = {"ok": True, "hay_novedades": True, "pendientes": 2, "commits": ["abc uno", "def dos"],
           "limpio": True, "modificados": [], "mensaje": "Hay 2 cambio(s) nuevo(s) esperando."}
    c, f, _, salidas, fases = control(qapp, modo="git", falsas=Falsas(busqueda=git))
    c.buscar(); girar(lambda: fases[-1]["fase"] == "hay")
    assert fases[-1]["commits"] == ["abc uno", "def dos"]
    assert c.instalar() is True                                          # pull + pip y reinicio
    assert girar(lambda: salidas == [1])
    assert [x[0] for x in f.llamadas] == ["buscar", "actualizar", "reiniciar"]


def test_copia_sin_git_solo_avisa(qapp):
    c, f, *_ = control(qapp, modo="carpeta")
    c.buscar(); girar(lambda: not c.ocupado)
    assert c.descargar() is False and c.instalar() is False
    assert [x[0] for x in f.llamadas] == ["buscar"]


def test_detener_corta_y_ya_no_avisa(qapp):
    trabajos = []
    c, f, *_ , fases = control(qapp, lanzar=trabajos.append)
    c.buscar()
    c.detener()
    n = len(fases)
    trabajos.pop()()
    girar(tope_s=0.1)
    assert len(fases) == n                                               # el resultado tardío no llega


def test_recibir_el_aviso_de_inicio(qapp):
    c, *_ , fases = control(qapp)
    c.recibir(rel())
    assert fases[-1]["fase"] == "hay" and c.info()["estado"]["version"] == "11.4"


# ── AvisoInicio ───────────────────────────────────────────────────────────────

class Ventana:
    def __init__(self):
        self.avisos = []

    def avisar_actualizacion(self, res):
        self.avisos.append(res)


def aviso_inicio(qapp, cfg, ventana, jugando, buscar=None):
    busquedas = []

    def buscar_(rama=None):
        busquedas.append(rama)
        return (buscar or (lambda: rel()))()
    a = AQ.AvisoInicio(cfg, ventana=lambda: ventana, retraso_ms=0, reintento_ms=1, buscar=buscar_,
                       lanzar=lambda fn: fn(), en_juego=lambda v: jugando["on"])
    return a, busquedas


def test_aviso_al_iniciar_una_vez_al_dia(qapp):
    cfg, v, jugando = Cfg(), Ventana(), {"on": False}
    a, busquedas = aviso_inicio(qapp, cfg, v, jugando)
    assert a.iniciar() is True
    assert girar(lambda: len(v.avisos) == 1)
    assert busquedas == ["master"] and v.avisos[0]["version"] == "11.4"
    assert cfg.d["actualizaciones"]["ultima_comprobacion"]
    # Otra vez el mismo día: no toca.
    a2, b2 = aviso_inicio(qapp, cfg, v, jugando)
    assert a2.iniciar() is False
    girar(tope_s=0.05)
    assert b2 == [] and len(v.avisos) == 1
    # Apagado en Ajustes: tampoco.
    a3, b3 = aviso_inicio(qapp, Cfg(comprobar_al_iniciar=False), v, jugando)
    assert a3.iniciar() is False


def test_aviso_al_iniciar_nunca_en_modo_juego(qapp):
    cfg, v, jugando = Cfg(), Ventana(), {"on": True}
    a, busquedas = aviso_inicio(qapp, cfg, v, jugando)
    a.reintento_ms = 5
    a.iniciar()
    girar(tope_s=0.15)
    assert busquedas == [] and v.avisos == [] and cfg.d["actualizaciones"]["ultima_comprobacion"] == ""
    jugando["on"] = False                                    # acabó la partida
    assert girar(lambda: len(v.avisos) == 1)
    assert busquedas == ["master"]
    a.detener()


def test_aviso_espera_a_que_acabe_la_partida_para_avisar(qapp):
    cfg, v, jugando = Cfg(), Ventana(), {"on": False}

    def buscar():
        jugando["on"] = True                                  # empezó una partida mientras buscaba
        return rel()
    a, _ = aviso_inicio(qapp, cfg, v, jugando, buscar=buscar)
    a.reintento_ms = 5
    a.iniciar()
    girar(tope_s=0.15)
    assert v.avisos == []
    jugando["on"] = False
    assert girar(lambda: len(v.avisos) == 1)
    a.detener()


def test_sin_novedades_no_avisa(qapp):
    cfg, v = Cfg(), Ventana()
    a, busquedas = aviso_inicio(qapp, cfg, v, {"on": False},
                                buscar=lambda: rel(hay_novedades=False, omitida=True))
    a.iniciar()
    assert girar(lambda: busquedas == ["master"])
    girar(tope_s=0.05)
    assert v.avisos == [] and cfg.d["actualizaciones"]["ultima_comprobacion"]


def test_en_juego_y_destino_de_la_ventana():
    class Bus:
        def __init__(self, on):
            self.on = on

        def actual(self):
            return type("E", (), {"juego": self.on})()
    web = type("W", (), {})()
    web.bridge = type("B", (), {"escritorio": type("Esc", (), {"estado": Bus(True)})(),
                                "avisar_actualizacion": lambda self, r: None})()
    assert AQ.en_juego(web) is True and AQ.destino_aviso(web) is not None
    nativa = type("N", (), {"escritorio": type("Esc", (), {"estado": Bus(False)})()})()
    assert AQ.en_juego(nativa) is False and AQ.destino_aviso(nativa) is None
    assert AQ.en_juego(None) is False


def test_salir_de_verdad_sube_por_los_padres(qapp):
    from PyQt6.QtCore import QObject

    class Ventana(QObject):
        salidas = 0

        def salir_de_verdad(self):
            Ventana.salidas += 1
    v = Ventana()
    hijo = QObject(v)
    nieto = QObject(hijo)
    AQ.salir_de_verdad_de(nieto)()
    assert Ventana.salidas == 1


# ── Contratos con la web ──────────────────────────────────────────────────────

def _qt_de(cls):
    mo = cls.staticMetaObject
    ranuras, senales = {}, set()
    for i in range(mo.methodCount()):
        m = mo.method(i)
        nombre = bytes(m.name()).decode()
        if m.methodType() == QMetaMethod.MethodType.Slot:
            ranuras[nombre] = (bytes(m.methodSignature()).decode(), m.typeName())
        elif m.methodType() == QMetaMethod.MethodType.Signal:
            senales.add(nombre)
    return ranuras, senales


def test_el_puente_tiene_la_senal_y_las_ranuras_que_usa_la_tarjeta():
    from ui.web_bridge import LuneBridge
    ranuras, senales = _qt_de(LuneBridge)
    esperadas = {
        "actualizacion_info": ("actualizacion_info()", "QString"),
        "actualizacion_buscar": ("actualizacion_buscar()", "bool"),
        "actualizacion_descargar": ("actualizacion_descargar()", "bool"),
        "actualizacion_cancelar": ("actualizacion_cancelar()", "bool"),
        "actualizacion_instalar": ("actualizacion_instalar()", "bool"),
        "actualizacion_omitir": ("actualizacion_omitir(QString)", "bool"),
        "actualizacion_al_iniciar": ("actualizacion_al_iniciar(bool)", "bool"),
    }
    for n, firma in esperadas.items():
        assert ranuras.get(n) == firma, n
    assert "actualizacion" in senales
    texto = CARD.read_text(encoding="utf-8")
    llamadas = set(re.findall(r"llamar\('([a-z_]+)'", texto))
    escuchadas = set(re.findall(r"conectar\('([a-z_]+)'", texto))
    assert llamadas == set(esperadas), llamadas ^ set(esperadas)
    assert escuchadas == {"actualizacion"}
    # avisar_actualizacion NO es una ranura (la página no puede fingir un aviso).
    assert "avisar_actualizacion" not in ranuras


def test_la_tarjeta_se_carga_y_va_en_sistema():
    html = (KIT / "index.html").read_text(encoding="utf-8")
    assert html.count('<script type="text/babel" src="extra/actualizaciones.jsx"></script>') == 1
    assert html.index("extra/actualizaciones.jsx") < html.index('src="app.jsx"')
    ajustes = (KIT / "settings.jsx").read_text(encoding="utf-8")
    assert ajustes.count("<window.ActualizacionesCard />") == 1
    # Justo después de la tarjeta «Calidad de vida» (Sistema).
    assert ajustes.index('title="Calidad de vida"') < ajustes.index("<window.ActualizacionesCard />")


def test_avisar_actualizacion_del_puente(qapp):
    from ui.web_bridge import LuneBridge

    class Senal:
        def __init__(self):
            self.emitidos = []

        def emit(self, t):
            self.emitidos.append(t)
    recibidos = []
    falso = type("Puente", (), {})()
    falso.aviso = Senal()
    falso._actualizaciones = lambda: type("C", (), {"recibir": lambda self, r: recibidos.append(r)})()
    falso._ventana = lambda: None                         # sin servicios: toast por la señal aviso
    LuneBridge.avisar_actualizacion(falso, {**rel(), "modo": "instalada"})
    assert recibidos and falso.aviso.emitidos == [
        "Hay una versión nueva de mí (11.4). Ajustes → Sistema → Actualizaciones"]


# ── Nativa y main ─────────────────────────────────────────────────────────────

@pytest.fixture
def panel_nativo(qapp, tmp_path, monkeypatch):
    from test_settings_voz_compat import DATOS, VozFalsa
    from nucleo.config import Config
    from servicios import autoinicio, voces
    from ui import settings_panel as SP
    monkeypatch.setattr(SP.datos, "cargar", lambda: copy.deepcopy(DATOS))
    monkeypatch.setattr(SP.datos, "guardar", lambda d: None)
    monkeypatch.setattr(SP.voces, "listar_edge", lambda *a, **k: voces.voces_estaticas())
    monkeypatch.setattr(SP.voz_entrada, "dependencias_faltantes", lambda: [])
    monkeypatch.setattr(SP.voz_entrada, "listar_entradas", lambda: [])
    monkeypatch.setattr(SP, "listar_salidas", lambda: [])
    monkeypatch.setattr(SP.actualizador, "estado", lambda: {"ok": False, "mensaje": "test"})
    monkeypatch.setattr(autoinicio, "activo", lambda: False)
    monkeypatch.setattr(voces, "_voz_personaje", lambda p: SP.voz_de(p))
    cfg = Config(str(tmp_path / "config.json"))
    return SP, cfg, VozFalsa


def test_nativa_instalada_usa_releases_y_no_llama_a_git(panel_nativo, monkeypatch):
    SP, cfg, VozFalsa = panel_nativo
    monkeypatch.setattr(SP.actualizador, "modo", lambda *a, **k: "instalada")

    def sin_git(*a, **k):
        raise AssertionError("la instalada no debe llamar a git")
    monkeypatch.setattr(SP, "EstadoGitWorker", sin_git)
    monkeypatch.setattr(SP, "GitWorker", sin_git)
    p = SP.SettingsPanel(cfg, voice=VozFalsa())
    assert p._act is not None and p._act.modo == "instalada"
    assert not p.btn_actualizar.isEnabled() and p.barra_update.isHidden()
    p._pintar_actualizacion({"fase": "descargando", "pct": 40, "nueva": True, "instalable": True,
                             "mensaje": "Descargando 4 MB de 10 MB (40 %)…", "version": "11.4"})
    assert not p.barra_update.isHidden() and p.barra_update.value() == 40 and not p.btn_cancelar_update.isHidden()
    p._pintar_actualizacion({**rel(), "fase": "hay"})
    assert p.btn_actualizar.isEnabled() and not p.btn_omitir.isHidden() and p.lbl_notas_update.text() == "Me actualizo sola."
    # «Buscar al abrirme» guarda al momento.
    p.chk_buscar_inicio.setChecked(False)
    assert cfg.get("actualizaciones", "comprobar_al_iniciar") is False
    p.recibir_novedad(rel())
    assert p._act.estado()["fase"] == "hay"


def test_nativa_desde_el_codigo_sigue_con_git(panel_nativo, monkeypatch):
    SP, cfg, VozFalsa = panel_nativo
    monkeypatch.setattr(SP.actualizador, "modo", lambda *a, **k: "git")
    p = SP.SettingsPanel(cfg, voice=VozFalsa())
    assert p._act is None and p.btn_actualizar.text() == "ACTUALIZAR Y REINICIAR"
    p._estado_git.wait(5000)
    p.recibir_novedad({"ok": True, "hay_novedades": True, "mensaje": "Hay 1 cambio(s) nuevo(s) esperando.",
                       "commits": ["abc uno"]})
    assert "abc uno" in p.lbl_update.text()


def test_nativa_copia_sin_git_da_el_enlace(panel_nativo, monkeypatch):
    SP, cfg, VozFalsa = panel_nativo
    monkeypatch.setattr(SP.actualizador, "modo", lambda *a, **k: "carpeta")
    p = SP.SettingsPanel(cfg, voice=VozFalsa())
    assert p._act is None and not hasattr(p, "btn_actualizar")


def test_main_programa_el_aviso_una_vez_y_no_lanza(qapp):
    import main
    creados = []

    class AvisoFalso:
        def __init__(self, config, ventana=None, parent=None):
            self.ventana = ventana
            creados.append(self)

        def iniciar(self):
            return True
    gestor = type("G", (), {"ventana": "la ventana"})()
    aviso = main._programar_aviso_actualizacion(gestor, Cfg(), fabrica=AvisoFalso)
    assert aviso is creados[0] and aviso.ventana() == "la ventana"

    def revienta(*a, **k):
        raise RuntimeError("no")
    assert main._programar_aviso_actualizacion(gestor, Cfg(), fabrica=revienta) is None
    # La nativa ya no busca por su cuenta con git al arrancar: lo hace el aviso común.
    fuente = Path(main.__file__).read_text(encoding="utf-8")
    assert "_comprobar_updates_silencioso" not in fuente
    assert callable(getattr(main.LuneCDWindow, "avisar_actualizacion", None))
