"""
Tests de servicios/modo_juego.py: las reglas del detector de juegos (QUNS, sin
bordes, lista, rutas), la exclusión de Lune y del escritorio, la histéresis 2/3,
forzar, la caché de rutas (un handle por pid y minuto), el plan desde la config,
normalizar_app, la prioridad (solo los procesos de Lune, y se restaura) y la
lista de apps con ventana.

Con una API de pantalla falsa y un psutil falso: sin Win32 real.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import modo_juego as mj  # noqa: E402
from servicios.win_pantalla import Monitor, PidsLune, Rect  # noqa: E402

MON = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032), True, r"\\.\DISPLAY1")
WS_POPUP_VISIBLE = 0x90000000          # sin WS_CAPTION: juego sin bordes
WS_OVERLAPPEDWINDOW = 0x00CF0000       # con barra de título
PANTALLA = (0, 0, 1920, 1080)
MAXIMIZADA = (-8, -8, 1928, 1040)      # maximizada con marco: sobresale y no cubre la barra

PID_LUNE = 1000
PID_WEBENGINE = 1001
PID_JUEGO = 55
RUTA_STEAM = r"C:\Program Files (x86)\Steam\steamapps\common\Hollow\hollow.exe"


class Ventana:
    def __init__(self, pid=PID_JUEGO, clase="UnityWndClass", titulo="Juego", rect=PANTALLA,
                 estilo=WS_POPUP_VISIBLE, hwnd=7):
        self.pid, self.clase, self.titulo = pid, clase, titulo
        self.rect, self.estilo, self.hwnd = Rect(*rect), estilo, hwnd


class ApiJuego:
    """Un monitor, una ventana activa (o ninguna), el QUNS y los procesos."""

    def __init__(self, quns=5, ventana=None, nombres=None, rutas=None, visibles=()):
        self.quns = quns
        self.ventana = ventana
        self.nombres = {PID_JUEGO: "hollow.exe", PID_LUNE: "python.exe",
                        PID_WEBENGINE: "QtWebEngineProcess.exe", **(nombres or {})}
        self.rutas = dict(rutas or {})
        self.visibles = list(visibles)
        self.llamadas_ruta = []

    # QUNS y ventana activa
    def estado_notificaciones(self): return self.quns
    def ventana_activa(self): return self.ventana.hwnd if self.ventana else 0
    def pid_ventana(self, h): return self.ventana.pid
    def clase_ventana(self, h): return self.ventana.clase
    def titulo_ventana(self, h): return self.ventana.titulo
    def rect_ventana(self, h): return self.ventana.rect
    def estilo_ventana(self, h): return self.ventana.estilo
    def monitor_de_ventana(self, h): return MON.hmon
    def info_monitor(self, h): return MON if h == MON.hmon else None
    def lista_monitores(self): return [MON.hmon]
    def buscar_ventanas(self, clase): return []
    def barra_auto_oculta(self): return False
    def ventanas_visibles(self): return list(self.visibles)

    # procesos
    def pid_propio(self): return PID_LUNE
    def hijos(self, pid): return [(PID_WEBENGINE, "QtWebEngineProcess.exe"), (77, "juego_lanzado.exe")]
    def nombre_proceso(self, pid): return self.nombres.get(pid, "")

    def ruta_proceso(self, pid):
        self.llamadas_ruta.append(pid)
        return self.rutas.get(pid, "")


def leer(api, **cfg):
    juego = {"activo": True, "incluir_videos": True, "rutas_juego": True, "apps": []}
    juego.update(cfg)
    return mj.evaluar_una_vez({"juego": juego}, api, pids=PidsLune(api))


# ── Regla 1: QUNS ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quns, motivo", [(3, "quns3"), (4, "quns4")])
def test_quns_3_y_4_siempre_son_juego(quns, motivo):
    api = ApiJuego(quns=quns, ventana=Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW))
    lectura = leer(api, incluir_videos=False)
    assert lectura.juego and lectura.motivo == motivo and lectura.exe == "hollow.exe"


def test_quns_2_solo_con_videos_y_sin_lune_en_grande():
    normal = Ventana(pid=66, clase="Chrome_WidgetWin_1", rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW)
    api = ApiJuego(quns=2, ventana=normal, nombres={66: "chrome.exe"})
    assert leer(api).motivo == "quns2"
    assert leer(api, incluir_videos=False).juego is False
    pids = PidsLune(api)
    en_grande = mj.evaluar_una_vez({"juego": {"incluir_videos": True}}, api, pids=pids,
                                   lune_a_pantalla_completa=True)
    assert en_grande.juego is False


# ── Regla 2: sin bordes a pantalla completa ───────────────────────────────────

def test_sin_bordes_que_cubre_su_monitor_es_juego():
    assert leer(ApiJuego(ventana=Ventana())).motivo == "sin_bordes"
    # ±2 px de tolerancia, como Mate-Engine
    assert leer(ApiJuego(ventana=Ventana(rect=(1, -2, 1921, 1082)))).motivo == "sin_bordes"


def test_maximizada_o_con_titulo_no_es_juego():
    assert leer(ApiJuego(ventana=Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW))).juego is False
    # cubre el monitor pero tiene barra de título (p. ej. una ventana estirada a mano)
    assert leer(ApiJuego(ventana=Ventana(estilo=WS_OVERLAPPEDWINDOW))).juego is False
    # sin bordes pero sin cubrir el monitor
    assert leer(ApiJuego(ventana=Ventana(rect=(100, 100, 900, 700)))).juego is False


@pytest.mark.parametrize("clase", ["Progman", "WorkerW", "Shell_TrayWnd"])
def test_el_escritorio_no_es_juego(clase):
    api = ApiJuego(ventana=Ventana(pid=4, clase=clase, titulo=""), rutas={4: RUTA_STEAM})
    assert leer(api).juego is False
    assert api.llamadas_ruta == []                   # tampoco se mira su ruta


def test_f11_en_el_navegador_depende_de_incluir_videos():
    f11 = Ventana(pid=66, clase="Chrome_WidgetWin_1", titulo="YouTube")
    api = ApiJuego(ventana=f11, nombres={66: "Chrome.exe"})
    assert leer(api, incluir_videos=True).motivo == "sin_bordes"
    assert leer(api, incluir_videos=False).juego is False


# ── Regla 0: Lune no es un juego ──────────────────────────────────────────────

@pytest.mark.parametrize("pid", [PID_LUNE, PID_WEBENGINE])
def test_la_ventana_de_lune_nunca_es_juego(pid):
    # su pantalla grande cubre el monitor sin bordes, y aunque el QUNS diga 3
    api = ApiJuego(quns=3, ventana=Ventana(pid=pid, clase="Qt663QWindowToolSaveBits"),
                   rutas={pid: RUTA_STEAM})
    assert leer(api).juego is False
    assert api.llamadas_ruta == []


def test_un_hijo_de_lune_que_no_es_webengine_si_puede_ser_juego():
    # un juego lanzado por una herramienta es hijo de Lune, pero no es Lune
    api = ApiJuego(ventana=Ventana(pid=77))
    assert leer(api).motivo == "sin_bordes"


# ── Reglas 3 y 4: lista y rutas ───────────────────────────────────────────────

def test_lista_del_usuario_sin_mayusculas_y_con_o_sin_exe():
    ventana = Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW)
    api = ApiJuego(ventana=ventana, nombres={PID_JUEGO: "Hollow.EXE"})
    assert leer(api).juego is False
    assert leer(api, apps=["HOLLOW"]).motivo == "lista"
    assert leer(api, apps=["hollow.exe"]).motivo == "lista"
    assert leer(api, apps=["otro.exe", r"C:\hollow.exe"]).juego is False     # rutas no valen


def test_ruta_de_steam_con_y_sin_rutas_juego():
    ventana = Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW)
    api = ApiJuego(ventana=ventana, rutas={PID_JUEGO: RUTA_STEAM})
    assert leer(api).motivo == "ruta"
    api.llamadas_ruta.clear()
    assert leer(api, rutas_juego=False).juego is False
    assert api.llamadas_ruta == []


@pytest.mark.parametrize("ruta", [
    r"D:\Epic Games\Fortnite\FortniteClient.exe",
    r"C:\Riot Games\VALORANT\live\VALORANT.exe",
    r"C:\XboxGames\Forza\Content\forza.exe",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Witcher\witcher3.exe",
])
def test_otras_tiendas(ruta):
    api = ApiJuego(ventana=Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW), rutas={PID_JUEGO: ruta})
    assert leer(api).motivo == "ruta"


def test_la_ruta_solo_se_mira_si_fallan_las_anteriores():
    api = ApiJuego(quns=3, ventana=Ventana(), rutas={PID_JUEGO: RUTA_STEAM})
    assert leer(api).motivo == "quns3"
    assert leer(ApiJuego(ventana=Ventana(), rutas={PID_JUEGO: RUTA_STEAM})).motivo == "sin_bordes"
    assert api.llamadas_ruta == []


def test_sin_ventana_activa_ni_quns_no_hay_juego():
    assert leer(ApiJuego()).juego is False
    assert leer(ApiJuego(quns=3)).motivo == "quns3"


def test_detector_apagado_no_lee_nada():
    api = ApiJuego(quns=3, ventana=Ventana())
    assert leer(api, activo=False) == mj.Lectura(False, "")


# ── Caché de rutas ────────────────────────────────────────────────────────────

class Reloj:
    def __init__(self, t=100.0): self.t = t
    def __call__(self): return self.t


def test_ruta_proceso_una_vez_por_pid_y_minuto():
    reloj = Reloj()
    api = ApiJuego(ventana=Ventana(rect=MAXIMIZADA, estilo=WS_OVERLAPPEDWINDOW), rutas={PID_JUEGO: RUTA_STEAM})
    det = mj.DetectorJuego({"juego": {"activo": True}}, api, pids=PidsLune(api),
                           cache=mj.CacheRutas(reloj=reloj))
    for _ in range(5):
        det.evaluar()
    assert api.llamadas_ruta == [PID_JUEGO] and det.activo
    reloj.t += 61
    det.evaluar()
    assert api.llamadas_ruta == [PID_JUEGO, PID_JUEGO]


# ── Histéresis y forzar ───────────────────────────────────────────────────────

def test_histeresis_dos_para_entrar_tres_para_salir():
    api = ApiJuego(quns=3)
    det = mj.DetectorJuego({"juego": {"activo": True}}, api, pids=PidsLune(api))
    assert det.evaluar() == (False, False, "")        # 1.ª positiva: aún no
    assert det.evaluar() == (True, True, "quns3")     # 2.ª: entra
    api.quns = 5
    assert det.evaluar() == (False, True, "quns3")    # 1.ª negativa
    api.quns = 3
    assert det.evaluar() == (False, True, "quns3")    # una positiva reinicia la cuenta
    api.quns = 5
    assert det.evaluar()[1] is True
    assert det.evaluar()[1] is True
    assert det.evaluar() == (True, False, "")         # 3.ª negativa seguida: sale
    assert det.estado() == {"activo": False, "motivo": "", "forzado": None, "exe": ""}


def test_una_positiva_suelta_no_entra():
    api = ApiJuego(quns=3)
    det = mj.DetectorJuego({"juego": {}}, api, pids=PidsLune(api))
    det.evaluar()
    api.quns = 5
    det.evaluar()
    api.quns = 3
    assert det.evaluar() == (False, False, "")


def test_forzar_manda_y_none_vuelve_a_detectar():
    api = ApiJuego()
    det = mj.DetectorJuego({"juego": {"activo": True}}, api, pids=PidsLune(api))
    det.forzar(True)
    assert det.evaluar() == (True, True, "forzado")
    assert det.estado()["forzado"] is True
    det.forzar(None)
    for _ in range(2):
        assert det.evaluar()[1] is True               # sale con histéresis (sin juego)
    assert det.evaluar() == (True, False, "")
    api.quns = 3
    det.forzar(False)
    for _ in range(4):
        assert det.evaluar()[1] is False              # forzado a no, aunque haya juego


def test_forzar_funciona_con_el_detector_apagado_y_apagar_sale_ya():
    api = ApiJuego(quns=3)
    cfg = {"juego": {"activo": False}}
    det = mj.DetectorJuego(cfg, api, pids=PidsLune(api))
    assert not det.detectando()
    det.forzar(True)
    assert det.detectando() and det.evaluar()[1] is True
    det.forzar(None)
    assert det.evaluar() == (True, False, "")        # apagado: sale sin histéresis


# ── Plan y config ─────────────────────────────────────────────────────────────

def test_plan_desde_la_config():
    p = mj.plan({"juego": {"accion": "fondo", "fps": 30, "silenciar": False, "prioridad_baja": False,
                           "recortar_ram": True}, "atajos": {"pausar_en_juegos": False}})
    assert p == mj.PlanJuego(accion="fondo", fps=30, silenciar_voz=False, prioridad_baja=False,
                             recortar_ram=True, pausar_atajos=False)
    assert p.parar_comentarios and p.bloquear_capturas and p.parar_aburrimiento


@pytest.mark.parametrize("accion, fps, esperado", [
    ("bailar", 200, ("ocultar", 60)), (None, -5, ("ocultar", 0)), ("nada", "x", ("nada", 0)),
])
def test_plan_sanea_accion_y_fps(accion, fps, esperado):
    p = mj.plan({"juego": {"accion": accion, "fps": fps}})
    assert (p.accion, p.fps) == esperado


def test_plan_con_config_real_y_defectos_iguales(tmp_path):
    from nucleo.config import Config
    assert mj.DEFECTOS_JUEGO == Config.DEFAULT_CONFIG["juego"]
    cfg = Config(config_path=str(tmp_path / "config.json"))
    p = mj.plan(cfg)
    assert p == mj.PlanJuego(accion="ocultar", fps=0, silenciar_voz=True, prioridad_baja=True,
                             recortar_ram=True, pausar_atajos=True)
    cfg.set("juego", "accion", "fondo")
    assert mj.plan(cfg).accion == "fondo"


@pytest.mark.parametrize("nombre, esperado", [
    ("Game.EXE", "game.exe"), ("game", "game.exe"), ("  Mi Juego (x64).exe ", "mi juego (x64).exe"),
    ("javaw.exe", "javaw.exe"), (r"C:\Juegos\game.exe", None), ("../game", None), ("..", None),
    ("", None), ("a" * 81, None), ("jue*go", None), ('"x"', None), (None, None), (42, None),
])
def test_normalizar_app(nombre, esperado):
    assert mj.normalizar_app(nombre) == esperado


# ── Prioridad: solo los procesos de Lune ──────────────────────────────────────

class ProcFalso:
    def __init__(self, ps, pid, nombre, nice):
        self.ps, self.pid, self._nombre, self._nice = ps, pid, nombre, nice

    def name(self): return self._nombre

    def nice(self, valor=None):
        if valor is None:
            return self._nice
        self.ps.cambios.append((self.pid, valor))
        self._nice = valor

    def children(self, recursive=False):
        assert recursive
        return [self.ps.procs[p] for p in self.ps.hijos.get(self.pid, [])]

    def memory_info(self):
        class M:
            rss = self.ps.rss.get(self.pid, 0)
        return M()


class PsutilFalso:
    BELOW_NORMAL_PRIORITY_CLASS = 0x4000
    NORMAL_PRIORITY_CLASS = 0x20
    ABOVE_NORMAL_PRIORITY_CLASS = 0x8000

    def __init__(self):
        N = self.NORMAL_PRIORITY_CLASS
        self.procs = {}
        self.cambios = []
        self.pedidos = []
        self.rss = {}
        for pid, nombre, nice in [(PID_LUNE, "python.exe", N),
                                  (PID_WEBENGINE, "QtWebEngineProcess.exe", self.ABOVE_NORMAL_PRIORITY_CLASS),
                                  (77, "juego_lanzado.exe", N), (4321, "juego.exe", N)]:
            self.procs[pid] = ProcFalso(self, pid, nombre, nice)
        self.hijos = {PID_LUNE: [PID_WEBENGINE, 77]}

    def Process(self, pid):
        self.pedidos.append(pid)
        if pid not in self.procs:
            raise ProcessLookupError(pid)
        return self.procs[pid]


@pytest.fixture
def previas_limpias():
    mj._PREVIAS.clear()
    yield
    mj._PREVIAS.clear()


def test_prioridad_baja_solo_a_lune_y_se_restaura(previas_limpias):
    ps = PsutilFalso()
    pids = PidsLune(ApiJuego())
    assert mj.aplicar_prioridad(True, psutil_mod=ps, pids=pids) == 2
    bajo = ps.BELOW_NORMAL_PRIORITY_CLASS
    assert ps.procs[PID_LUNE]._nice == bajo and ps.procs[PID_WEBENGINE]._nice == bajo
    assert ps.procs[77]._nice == ps.NORMAL_PRIORITY_CLASS            # el juego lanzado por Lune, no
    assert {pid for pid, _ in ps.cambios} == {PID_LUNE, PID_WEBENGINE}
    mj.aplicar_prioridad(True, psutil_mod=ps, pids=pids)             # dos veces: la previa no se pisa
    assert mj.aplicar_prioridad(False, psutil_mod=ps, pids=pids) == 2
    assert ps.procs[PID_LUNE]._nice == ps.NORMAL_PRIORITY_CLASS
    assert ps.procs[PID_WEBENGINE]._nice == ps.ABOVE_NORMAL_PRIORITY_CLASS   # la que tenía
    assert mj._PREVIAS == {}


def test_prioridad_rechaza_pids_ajenos_colados_en_la_lista(previas_limpias):
    ps = PsutilFalso()

    class PidsTrampa:                                 # un PidsLune que dice que 4321 y 77 son de Lune
        api = ApiJuego()
        def pids(self): return {PID_LUNE, 4321, 77}

    assert mj.aplicar_prioridad(True, psutil_mod=ps, pids=PidsTrampa()) == 1
    assert [pid for pid, _ in ps.cambios] == [PID_LUNE]
    assert 4321 not in ps.pedidos and 77 not in ps.pedidos           # ni se abren
    # un conjunto de pids suelto tampoco cuela un proceso ajeno
    ps.cambios.clear()
    mj.aplicar_prioridad(True, psutil_mod=ps, pids={4321})
    assert ps.cambios == []


def test_el_hijo_que_nace_con_la_baja_vuelve_a_normal(previas_limpias):
    ps = PsutilFalso()
    pids = PidsLune(ApiJuego())
    mj.aplicar_prioridad(True, psutil_mod=ps, pids=pids)
    # nace otro QtWebEngineProcess durante la partida (hereda BELOW_NORMAL)
    ps.procs[1005] = ProcFalso(ps, 1005, "QtWebEngineProcess.exe", ps.BELOW_NORMAL_PRIORITY_CLASS)
    ps.hijos[PID_LUNE].append(1005)

    class PidsNuevos:
        api = ApiJuego()
        def pids(self): return {PID_LUNE, PID_WEBENGINE, 1005}

    mj.aplicar_prioridad(False, psutil_mod=ps, pids=PidsNuevos())
    assert ps.procs[1005]._nice == ps.NORMAL_PRIORITY_CLASS


def test_prioridad_tolera_fallos(previas_limpias):
    class PsRoto(PsutilFalso):
        def Process(self, pid):
            raise PermissionError("acceso denegado")
    assert mj.aplicar_prioridad(True, psutil_mod=PsRoto(), pids=PidsLune(ApiJuego())) == 0


# ── Apps con ventana ──────────────────────────────────────────────────────────

def test_apps_con_ventana_sin_lune_ni_shell_y_sin_repetir():
    api = ApiJuego(visibles=[(1, PID_LUNE, "Lune"), (2, PID_WEBENGINE, "x"), (3, 55, "Juego"),
                             (4, 56, "Explorador"), (5, 57, "Juego 2"), (6, 58, "raro")],
                   nombres={55: "Hollow.exe", 56: "explorer.exe", 57: "hollow.exe", 58: r"C:\raro.exe"})
    assert mj.apps_con_ventana(api) == ["hollow.exe"]
