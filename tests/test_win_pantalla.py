"""
Tests de servicios/win_pantalla: QUNS, ventana en primer plano, pantalla
completa contra SU monitor, pids de Lune (con caché), monitores y barra de
tareas (por diferencia de rects y auto-oculta).

Con una API falsa que describe un escritorio de dos monitores; sin pantalla.
"""
import ctypes
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import win_pantalla as P  # noqa: E402
from servicios.win_pantalla import (  # noqa: E402
    ApiPantallaNula, ApiPantallaWin32, InfoVentana, Monitor, PidsLune, Rect,
    barra_tareas, es_de_lune, es_escritorio, es_pantalla_completa,
    estado_notificaciones, franjas_reservadas, lado_barra, monitor_de_ventana,
    monitores, quns_indica_juego, tiene_titulo, ventana_primer_plano,
)

RAIZ = Path(__file__).resolve().parent.parent

MON1 = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032), True, r"\\.\DISPLAY1")
MON2 = Monitor(202, Rect(1920, 0, 4480, 1440), Rect(1920, 0, 4480, 1440), False, r"\\.\DISPLAY2")

WS_POPUP_VISIBLE = 0x90000000
WS_OVERLAPPEDWINDOW = 0x00CF0000


class Ventana:
    def __init__(self, pid, clase, titulo, rect, estilo, hmon):
        self.pid, self.clase, self.titulo = pid, clase, titulo
        self.rect, self.estilo, self.hmon = rect, estilo, hmon


class ApiFalsa:
    """Dos monitores; el 1 con barra abajo de 48 px y el 2 sin franja reservada."""

    def __init__(self, quns=5, activa=0, ventanas=None, monitores_=(MON1, MON2),
                 bandejas=None, auto_oculta=False, pid_propio=1000, hijos=None, nombres=None):
        self.quns = quns
        self.activa = activa
        self.ventanas = dict(ventanas or {})
        self.mons = {m.hmon: m for m in monitores_}
        self.orden = [m.hmon for m in monitores_]
        self.bandejas = dict(bandejas or {})          # clase → [hwnd]
        self.auto_oculta = auto_oculta
        self._pid = pid_propio
        self._hijos = list(hijos or [])
        self.nombres = dict(nombres or {})
        self.llamadas_hijos = 0

    def estado_notificaciones(self):
        return self.quns

    def ventana_activa(self):
        return self.activa

    def pid_ventana(self, h):
        return self.ventanas[h].pid

    def clase_ventana(self, h):
        return self.ventanas[h].clase

    def titulo_ventana(self, h):
        return self.ventanas[h].titulo

    def rect_ventana(self, h):
        v = self.ventanas.get(h)
        return v.rect if v else None

    def estilo_ventana(self, h):
        return self.ventanas[h].estilo

    def monitor_de_ventana(self, h):
        return self.ventanas[h].hmon

    def info_monitor(self, hmon):
        return self.mons.get(hmon)

    def lista_monitores(self):
        return list(self.orden)

    def buscar_ventanas(self, clase):
        return list(self.bandejas.get(clase, []))

    def barra_auto_oculta(self):
        return self.auto_oculta

    def pid_propio(self):
        return self._pid

    def nombre_proceso(self, pid):
        return self.nombres.get(pid, "")

    def ruta_proceso(self, pid):
        return r"C:\Program Files (x86)\Steam\steamapps\common\Juego\juego.exe" if pid == 55 else ""

    def hijos(self, pid):
        self.llamadas_hijos += 1
        assert pid == self._pid
        return list(self._hijos)


def _info(rect, monitor=MON1, estilo=WS_POPUP_VISIBLE, clase="UnityWndClass"):
    return InfoVentana(1, 55, clase, "Juego", Rect(*rect), monitor.rect, estilo, "juego.exe", monitor.hmon)


# ── QUNS ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor", [2, 3, 4, 5])
def test_estado_notificaciones_devuelve_el_valor(valor):
    assert estado_notificaciones(ApiFalsa(quns=valor)) == valor


def test_estado_notificaciones_sin_dato_es_cero():
    assert estado_notificaciones(ApiFalsa(quns=None)) == 0
    assert estado_notificaciones(ApiPantallaNula()) == 0


@pytest.mark.parametrize("valor, esperado", [(2, True), (3, True), (4, True), (5, False), (1, False), (0, False)])
def test_quns_indica_juego(valor, esperado):
    assert quns_indica_juego(valor) is esperado


def test_quns_ocupado_depende_de_videos_y_de_la_propia_pantalla_completa():
    assert quns_indica_juego(2, incluir_videos=False) is False
    assert quns_indica_juego(2, lune_a_pantalla_completa=True) is False
    # Un juego D3D o una presentación cuentan siempre.
    assert quns_indica_juego(3, incluir_videos=False, lune_a_pantalla_completa=True) is True
    assert quns_indica_juego(4, incluir_videos=False, lune_a_pantalla_completa=True) is True


# ── Ventana en primer plano ───────────────────────────────────────────────────

def test_ventana_primer_plano_reune_todo():
    api = ApiFalsa(activa=7, nombres={55: "juego.exe"}, ventanas={
        7: Ventana(55, "UnityWndClass", "Mi juego", Rect(1920, 0, 4480, 1440), WS_POPUP_VISIBLE, 202),
    })
    info = ventana_primer_plano(api)
    assert info == InfoVentana(7, 55, "UnityWndClass", "Mi juego", Rect(1920, 0, 4480, 1440),
                               MON2.rect, WS_POPUP_VISIBLE, "juego.exe", 202)
    assert es_pantalla_completa(info) is True


def test_sin_ventana_activa_es_none():
    assert ventana_primer_plano(ApiFalsa(activa=0)) is None
    assert ventana_primer_plano(ApiPantallaNula()) is None


def test_ventana_primer_plano_nunca_lanza():
    api = ApiFalsa(activa=9)                 # hwnd que no existe en el diccionario
    assert ventana_primer_plano(api) is None


# ── Pantalla completa contra SU monitor ───────────────────────────────────────

def test_geometria_exacta_y_con_tolerancia():
    assert es_pantalla_completa(_info((0, 0, 1920, 1080))) is True
    assert es_pantalla_completa(_info((2, -2, 1918, 1082))) is True
    assert es_pantalla_completa(_info((3, 0, 1920, 1080))) is False
    assert es_pantalla_completa(_info((0, 0, 1920, 1077))) is False


def test_maximizada_con_marco_no_es_pantalla_completa():
    """Maximizada, el marco sobresale ~8 px por cada lado."""
    info = _info((-8, -8, 1928, 1040), estilo=WS_OVERLAPPEDWINDOW)
    assert es_pantalla_completa(info) is False
    assert tiene_titulo(info) is True


def test_se_compara_con_su_monitor_no_con_el_principal():
    en_el_2 = _info((1920, 0, 4480, 1440), monitor=MON2)
    assert es_pantalla_completa(en_el_2) is True
    # El mismo rect contra el monitor 1 no cuadra.
    assert es_pantalla_completa(en_el_2._replace(rect_monitor=MON1.rect)) is False
    # Cubrir el monitor 1 estando «en» el 2 tampoco.
    assert es_pantalla_completa(_info((0, 0, 1920, 1080), monitor=MON2)) is False


def test_rects_vacios_no_son_pantalla_completa():
    assert es_pantalla_completa(None) is False
    assert es_pantalla_completa(_info((0, 0, 0, 0))._replace(rect_monitor=Rect(0, 0, 0, 0))) is False


def test_titulo_y_escritorio():
    assert tiene_titulo(_info((0, 0, 10, 10), estilo=WS_POPUP_VISIBLE)) is False
    # Solo WS_BORDER (0x00800000) no es una barra de título.
    assert tiene_titulo(_info((0, 0, 10, 10), estilo=0x00800000)) is False
    for clase in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        assert es_escritorio(_info((0, 0, 1920, 1080), clase=clase)) is True
    assert es_escritorio(_info((0, 0, 1920, 1080))) is False
    assert tiene_titulo(None) is False and es_escritorio(None) is False


def test_ruta_proceso_pasa_por_la_api():
    api = ApiFalsa()
    assert "steamapps" in P.ruta_proceso(55, api)
    assert P.ruta_proceso(1, api) == ""


# ── ¿Es Lune? ─────────────────────────────────────────────────────────────────

def test_pid_propio_y_hijos_webengine_son_de_lune():
    api = ApiFalsa(pid_propio=1000, hijos=[(1001, "QtWebEngineProcess.exe"),
                                           (1002, "node.exe"),
                                           (1003, "qtwebengineprocess.exe")])
    ids = PidsLune(api, reloj=lambda: 0.0)
    assert ids.contiene(1000) is True
    assert ids.contiene(1001) is True
    assert ids.contiene(1003) is True
    assert ids.contiene(1002) is False       # otro hijo (bot, juego lanzado por Lune): NO
    assert ids.contiene(4242) is False
    assert ids.contiene(0) is False


def test_los_hijos_se_cachean_y_caducan():
    reloj = [0.0]
    api = ApiFalsa(hijos=[(1001, "QtWebEngineProcess.exe")])
    ids = PidsLune(api, ttl=5.0, reloj=lambda: reloj[0])
    for _ in range(10):
        ids.contiene(4242)
    assert api.llamadas_hijos == 1
    api._hijos.append((1005, "QtWebEngineProcess.exe"))
    reloj[0] = 4.9
    assert ids.contiene(1005) is False
    reloj[0] = 5.0
    assert ids.contiene(1005) is True
    assert api.llamadas_hijos == 2


def test_ttl_de_los_hijos_es_de_30_s():
    """Los QtWebEngineProcess casi no cambian: la instantánea de procesos, cada 30 s."""
    assert P.TTL_PIDS_S == 30.0
    reloj = [0.0]
    api = ApiFalsa(hijos=[(1001, "QtWebEngineProcess.exe")])
    ids = PidsLune(api, reloj=lambda: reloj[0])
    ids.contiene(4242)
    reloj[0] = 29.9
    ids.contiene(4242)
    assert api.llamadas_hijos == 1
    reloj[0] = 30.0
    ids.contiene(4242)
    assert api.llamadas_hijos == 2


def test_invalidar_pids_fuerza_el_recalculo_en_todos():
    """Crear o cerrar la asistente cambia los hijos: todos los PidsLune vuelven a listar."""
    api = ApiFalsa(hijos=[(1001, "QtWebEngineProcess.exe")])
    a = PidsLune(api, reloj=lambda: 0.0)
    b = PidsLune(api, reloj=lambda: 0.0)
    assert a.contiene(1001) and b.contiene(1001)
    assert api.llamadas_hijos == 2
    api._hijos.append((1007, "QtWebEngineProcess.exe"))
    assert a.contiene(1007) is False                  # dentro del TTL: la lista vieja
    P.invalidar_pids()
    assert a.contiene(1007) is True and b.contiene(1007) is True
    assert api.llamadas_hijos == 4
    a.contiene(1007)
    assert api.llamadas_hijos == 4                    # y vuelve a la caché


def test_el_pid_propio_no_necesita_listar_hijos():
    api = ApiFalsa()
    assert PidsLune(api).contiene(1000) is True
    assert api.llamadas_hijos == 0


def test_es_de_lune_de_modulo_con_api_inyectada():
    api = ApiFalsa(hijos=[(1001, "QtWebEngineProcess.exe")])
    assert es_de_lune(1001, api) is True
    assert es_de_lune(77, api) is False
    otra = ApiFalsa(pid_propio=5)             # otra API → otra caché
    assert es_de_lune(1001, otra) is False
    assert es_de_lune(5, otra) is True


def test_hijos_que_fallan_no_rompen():
    class Rota(ApiFalsa):
        def hijos(self, pid):
            raise RuntimeError("psutil")
    assert PidsLune(Rota(), reloj=lambda: 0.0).contiene(1001) is False


class _ProcPs:
    def __init__(self, pid, nombre, hijos=()):
        self.pid, self._nombre, self._hijos = pid, nombre, list(hijos)
    def name(self): return self._nombre
    def children(self, recursive=False): return list(self._hijos)


class _Psutil:
    """psutil falso: 1000 (Lune) con hijos 1001 (WebEngine) y 1002 (un juego lanzado)."""
    def __init__(self):
        self.pedidos = []
        web, juego = _ProcPs(1001, "QtWebEngineProcess.exe"), _ProcPs(1002, "juego.exe")
        self.procs = {1000: _ProcPs(1000, "python.exe", [web, juego])}
    def Process(self, pid):
        self.pedidos.append(pid)
        if pid not in self.procs:
            raise ProcessLookupError(pid)
        return self.procs[pid]


def test_pids_propios_solo_lune_y_sus_webengine():
    api = ApiFalsa(pid_propio=1000, hijos=[(1001, "QtWebEngineProcess.exe"), (1002, "juego.exe")])
    assert P.pids_propios(PidsLune(api, reloj=lambda: 0.0), _Psutil()) == [1000, 1001]


def test_pids_propios_rechaza_lo_que_no_es_hijo_webengine():
    class Trampa:                                      # dice que un pid ajeno y el juego son de Lune
        api = ApiFalsa(pid_propio=1000)
        def pids(self): return {1000, 1002, 4321}
    ps = _Psutil()
    assert P.pids_propios(Trampa(), ps) == [1000]
    assert 4321 not in ps.pedidos and 1002 not in ps.pedidos
    assert P.pids_propios({4321}, _Psutil()) == []    # un conjunto suelto sin el propio: nada
    assert P.pids_propios({os.getpid()}, _Psutil()) == [os.getpid()]


def test_pids_propios_sin_psutil_se_queda_con_el_propio():
    class PsRoto:
        def Process(self, pid): raise RuntimeError("psutil")
    api = ApiFalsa(pid_propio=1000, hijos=[(1001, "QtWebEngineProcess.exe")])
    assert P.pids_propios(PidsLune(api, reloj=lambda: 0.0), PsRoto()) == [1000]


# ── Ventanas visibles ─────────────────────────────────────────────────────────

def test_ventanas_visibles_de_la_api_y_tolerante():
    class ConVentanas(ApiFalsa):
        def ventanas_visibles(self):
            return [(10, 55, "Juego"), ("basura",), (11, None, None)]
    assert P.ventanas_visibles(ConVentanas()) == [P.VentanaVisible(10, 55, "Juego"),
                                                  P.VentanaVisible(11, 0, "")]

    class Rota(ApiFalsa):
        def ventanas_visibles(self): raise OSError("x")
    assert P.ventanas_visibles(Rota()) == []
    assert P.ventanas_visibles(ApiFalsa()) == []           # API sin el método (vieja): vacío
    assert ApiPantallaNula().ventanas_visibles() == []


def test_api_win32_ventanas_visibles_filtra_con_dlls_falsas():
    user32, shell32 = _Dll(), _Dll()
    ventanas = {
        1: dict(visible=True, ex=0, titulo="Juego", pid=55),
        2: dict(visible=False, ex=0, titulo="Oculta", pid=56),
        3: dict(visible=True, ex=P.WS_EX_TOOLWINDOW, titulo="Herramienta", pid=57),
        4: dict(visible=True, ex=0, titulo="", pid=58),
        5: dict(visible=True, ex=-2147483648, titulo="Bit alto", pid=59),   # 0x80000000 con signo
    }

    def enum_windows(callback, lparam):
        for h in ventanas:
            if not callback(h, lparam):
                break
        return 1

    def get_long(h, idx):
        return ventanas[h]["ex"] if idx == P.GWL_EXSTYLE else 0

    def get_text_len(h):
        return len(ventanas[h]["titulo"])

    def get_text(h, buf, n):
        buf.value = ventanas[h]["titulo"][: n - 1]
        return len(buf.value)

    def get_pid(h, ref):
        ref._obj.value = ventanas[h]["pid"]
        return 1

    for nombre in ("GetForegroundWindow", "GetClassNameW", "GetWindowRect", "MonitorFromWindow",
                   "GetMonitorInfoW", "EnumDisplayMonitors", "FindWindowExW"):
        setattr(user32, nombre, _fn(lambda *a: 0))
    shell32.SHQueryUserNotificationState = _fn(lambda ref: 0)
    shell32.SHAppBarMessage = _fn(lambda msg, ref: 0)
    user32.EnumWindows = _fn(enum_windows)
    user32.IsWindowVisible = _fn(lambda h: ventanas[h]["visible"])
    user32.GetWindowLongW = _fn(get_long)
    user32.GetWindowTextLengthW = _fn(get_text_len)
    user32.GetWindowTextW = _fn(get_text)
    user32.GetWindowThreadProcessId = _fn(get_pid)

    api = ApiPantallaWin32(user32=user32, shell32=shell32)
    assert api.ventanas_visibles() == [(1, 55, "Juego"), (5, 59, "Bit alto")]


# ── Monitores ─────────────────────────────────────────────────────────────────

def test_monitores_en_orden_y_principal():
    ms = monitores(ApiFalsa())
    assert [m.hmon for m in ms] == [101, 202]
    assert [m.principal for m in ms] == [True, False]
    assert monitores(ApiPantallaNula()) == []


def test_monitor_de_ventana():
    api = ApiFalsa(ventanas={3: Ventana(1, "X", "", Rect(2000, 10, 2100, 110), 0, 202)})
    assert monitor_de_ventana(3, api) == MON2
    assert monitor_de_ventana(99, api) is None


# ── Barra de tareas ───────────────────────────────────────────────────────────

def test_franjas_por_diferencia_de_rects():
    m = Rect(0, 0, 1920, 1080)
    assert franjas_reservadas(m, Rect(0, 0, 1920, 1032)) == [Rect(0, 1032, 1920, 1080)]
    assert franjas_reservadas(m, Rect(0, 40, 1920, 1080)) == [Rect(0, 0, 1920, 40)]
    assert franjas_reservadas(m, Rect(62, 0, 1920, 1080)) == [Rect(0, 0, 62, 1080)]
    assert franjas_reservadas(m, Rect(0, 0, 1858, 1080)) == [Rect(1858, 0, 1920, 1080)]
    assert franjas_reservadas(m, m) == []


def test_barra_abajo_por_diferencia_de_rects():
    api = ApiFalsa(ventanas={50: Ventana(9, "Shell_TrayWnd", "", Rect(0, 1032, 1920, 1080), 0, 101)},
                   bandejas={"Shell_TrayWnd": [50]})
    barra = barra_tareas(101, api)
    assert barra == Rect(0, 1032, 1920, 1080)
    assert lado_barra(barra, MON1.rect) == "abajo"


def test_barra_sin_encontrar_la_ventana_usa_la_franja():
    assert barra_tareas(101, ApiFalsa()) == Rect(0, 1032, 1920, 1080)


def test_acepta_un_monitor_en_vez_del_hmon():
    assert barra_tareas(MON1, ApiFalsa()) == Rect(0, 1032, 1920, 1080)


def test_monitor_sin_barra_es_none():
    assert barra_tareas(202, ApiFalsa()) is None
    assert barra_tareas(999, ApiFalsa()) is None
    assert barra_tareas(0, ApiFalsa()) is None
    assert barra_tareas(101, ApiPantallaNula()) is None


def test_barra_auto_oculta_en_el_monitor_principal():
    """Auto-oculta: el área de trabajo es el monitor entero y la barra asoma 2 px."""
    mon = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080), True, "")
    api = ApiFalsa(monitores_=(mon, MON2), auto_oculta=True,
                   ventanas={50: Ventana(9, "Shell_TrayWnd", "", Rect(0, 1078, 1920, 1126), 0, 101)},
                   bandejas={"Shell_TrayWnd": [50]})
    barra = barra_tareas(101, api)
    assert barra == Rect(0, 1078, 1920, 1080)
    assert lado_barra(barra, mon.rect) == "abajo"
    # Mostrada (el ratón encima): la ventana entera dentro del monitor.
    api.ventanas[50].rect = Rect(0, 1032, 1920, 1080)
    assert barra_tareas(101, api) == Rect(0, 1032, 1920, 1080)


def test_barra_auto_oculta_secundaria_va_con_su_monitor():
    mon2 = MON2
    api = ApiFalsa(auto_oculta=True, monitores_=(MON1, mon2), ventanas={
        50: Ventana(9, "Shell_TrayWnd", "", Rect(0, 1032, 1920, 1080), 0, 101),
        60: Ventana(9, "Shell_SecondaryTrayWnd", "", Rect(1920, 1438, 4480, 1486), 0, 202),
    }, bandejas={"Shell_TrayWnd": [50], "Shell_SecondaryTrayWnd": [60]})
    assert barra_tareas(202, api) == Rect(1920, 1438, 4480, 1440)


def test_sin_auto_ocultar_una_bandeja_sin_franja_no_cuenta():
    api = ApiFalsa(auto_oculta=False, ventanas={
        60: Ventana(9, "Shell_SecondaryTrayWnd", "", Rect(1920, 1438, 4480, 1486), 0, 202)},
        bandejas={"Shell_SecondaryTrayWnd": [60]})
    assert barra_tareas(202, api) is None


def test_con_otra_appbar_se_elige_la_franja_de_la_barra():
    """Una appbar arriba (otra app) y la barra de Windows a la izquierda."""
    mon = Monitor(101, Rect(0, 0, 1920, 1080), Rect(62, 30, 1920, 1080), True, "")
    api = ApiFalsa(monitores_=(mon,), ventanas={50: Ventana(9, "Shell_TrayWnd", "", Rect(0, 0, 62, 1080), 0, 101)},
                   bandejas={"Shell_TrayWnd": [50]})
    barra = barra_tareas(101, api)
    assert barra == Rect(0, 0, 62, 1080)
    assert lado_barra(barra, mon.rect) == "izq"


def test_appbar_ajena_y_barra_auto_oculta():
    mon = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 30, 1920, 1080), True, "")
    api = ApiFalsa(monitores_=(mon,), auto_oculta=True,
                   ventanas={50: Ventana(9, "Shell_TrayWnd", "", Rect(0, 1078, 1920, 1126), 0, 101)},
                   bandejas={"Shell_TrayWnd": [50]})
    assert barra_tareas(101, api) == Rect(0, 1078, 1920, 1080)


@pytest.mark.parametrize("barra, lado", [
    (Rect(0, 0, 1920, 40), "arriba"),
    (Rect(0, 1040, 1920, 1080), "abajo"),
    (Rect(0, 0, 60, 1080), "izq"),
    (Rect(1860, 0, 1920, 1080), "der"),
])
def test_lado_barra(barra, lado):
    assert lado_barra(barra, Rect(0, 0, 1920, 1080)) == lado


def test_rect_utilidades():
    r = Rect(10, 20, 110, 70)
    assert (r.ancho, r.alto, r.area) == (100, 50, 5000)
    assert r.centro == (60.0, 45.0)
    assert r.contiene(10, 20) and not r.contiene(110, 20)
    assert r.interseccion(Rect(100, 0, 200, 30)) == Rect(100, 20, 110, 30)
    assert r.interseccion(Rect(500, 500, 600, 600)).vacio
    assert Rect(5, 5, 5, 9).area == 0


# ── ApiPantallaWin32 con DLLs falsas ──────────────────────────────────────────

class _Dll:
    pass


def _fn(impl):
    def f(*args):
        return impl(*args)
    return f


def test_api_win32_rellena_estructuras_con_dlls_falsas():
    user32, shell32 = _Dll(), _Dll()

    def quns(ref):
        ref._obj.value = 3
        return 0

    def get_window_rect(h, ref):
        ref._obj.left, ref._obj.top, ref._obj.right, ref._obj.bottom = (-5, 0, 1915, 1080)
        return 1

    def get_monitor_info(hmon, ref):
        mi = ref._obj
        assert mi.cbSize == ctypes.sizeof(P.MONITORINFOEXW)
        mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom = (0, 0, 1920, 1080)
        mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom = (0, 0, 1920, 1032)
        mi.dwFlags = P.MONITORINFOF_PRIMARY
        mi.szDevice = r"\\.\DISPLAY1"
        return 1

    def get_pid(h, ref):
        ref._obj.value = 4321
        return 99

    def get_class(h, buf, n):
        buf.value = "UnityWndClass"
        return len(buf.value)

    def get_text(h, buf, n):
        buf.value = "Juego"[: n - 1]
        return len(buf.value)

    def enum_monitores(hdc, clip, callback, lparam):
        callback(101, None, None, 0)
        callback(202, None, None, 0)
        return 1

    def app_bar(msg, ref):
        assert msg == P.ABM_GETSTATE and ref._obj.cbSize == ctypes.sizeof(P.APPBARDATA)
        return P.ABS_AUTOHIDE

    bandejas = iter([555, None])
    shell32.SHQueryUserNotificationState = _fn(quns)
    shell32.SHAppBarMessage = _fn(app_bar)
    user32.GetForegroundWindow = _fn(lambda: 777)
    user32.GetWindowThreadProcessId = _fn(get_pid)
    user32.GetClassNameW = _fn(get_class)
    user32.GetWindowTextLengthW = _fn(lambda h: 5)
    user32.GetWindowTextW = _fn(get_text)
    user32.GetWindowRect = _fn(get_window_rect)
    user32.GetWindowLongW = _fn(lambda h, idx: -1879048192)           # 0x90000000 con signo
    user32.MonitorFromWindow = _fn(lambda h, flags: 101)
    user32.GetMonitorInfoW = _fn(get_monitor_info)
    user32.EnumDisplayMonitors = _fn(enum_monitores)
    user32.FindWindowExW = _fn(lambda parent, after, clase, nombre: next(bandejas) if clase == "Shell_TrayWnd" else None)

    api = ApiPantallaWin32(user32=user32, shell32=shell32)
    assert api.estado_notificaciones() == 3
    assert api.ventana_activa() == 777
    assert api.pid_ventana(777) == 4321
    assert api.clase_ventana(777) == "UnityWndClass"
    assert api.titulo_ventana(777) == "Juego"
    assert api.rect_ventana(777) == Rect(-5, 0, 1915, 1080)
    assert api.estilo_ventana(777) == 0x90000000
    assert api.info_monitor(101) == Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032),
                                            True, r"\\.\DISPLAY1")
    assert api.lista_monitores() == [101, 202]
    assert api.buscar_ventanas("Shell_TrayWnd") == [555]
    assert api.buscar_ventanas("Shell_SecondaryTrayWnd") == []
    assert api.barra_auto_oculta() is True


# ── Privacidad y anticheat ───────────────────────────────────────────────────

def test_no_lee_la_linea_de_comandos_de_procesos_ajenos():
    src = (RAIZ / "servicios" / "win_pantalla.py").read_text(encoding="utf-8")
    for prohibido in ("cmdline", "memory_maps", "ReadProcessMemory", "WriteProcessMemory",
                      "CreateRemoteThread", "SetWindowsHook", "pynput", "import keyboard"):
        assert prohibido not in src


# ── En Windows de verdad (humo: que no falle) ────────────────────────────────

@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_en_windows_real_no_falla():
    P._api_defecto = None
    assert 0 <= estado_notificaciones() <= 7
    ms = monitores()
    assert ms, "Windows siempre tiene al menos un monitor (aunque sea virtual)"
    assert all(not m.rect.vacio for m in ms)
    principal = [m for m in ms if m.principal] or ms
    barra = barra_tareas(principal[0].hmon)
    assert barra is None or isinstance(barra, Rect)
    info = ventana_primer_plano()
    assert info is None or isinstance(info, InfoVentana)
    if info is not None:
        assert isinstance(es_pantalla_completa(info), bool)
    assert es_de_lune(os.getpid()) is True
