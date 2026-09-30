"""
Tests de servicios/ventanas_ajenas.py (corte 7, sentarse en ventanas) con una API
falsa: los filtros de candidatas de Mate-Engine (IsSitEligibleWindow,
IsEffectivelyTransparentWindow, IsLikelyUniWindow…), la barra marcada, el
tope de 128, la oclusión subiendo por GW_HWNDPREV, el estado de la ventana, el
orden Z, la barra de abajo del monitor de la asistente (auto-oculta = borde del
monitor) y el marshalling de la API real con DLLs falsas. Sin Win32 real.
"""
import ctypes
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from servicios import ventanas_ajenas as va  # noqa: E402
from servicios.win_pantalla import Monitor, Rect  # noqa: E402
from ventanas_falsas_c78 import (MON1, MON2, PID_LUNE, LWA_ALPHA, LWA_COLORKEY, WS_EX_LAYERED,  # noqa: E402
                                 WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT,
                                 ApiVentanasFalsa, PantallaFalsa, V)

BLOC = (300, 400, 1100, 900)


def _ids(cands):
    return [c.hwnd for c in cands]


# ── Candidatas ─────────────────────────────────────────────────────────────────

def test_filtros_de_candidatas_como_mate_engine():
    vs = {
        1: V((0, 1032, 1920, 1080), clase="Shell_TrayWnd", ex=WS_EX_TOPMOST, titulo=0),
        2: V(BLOC),                                                     # buena
        3: V(BLOC, clase="Progman"),
        4: V(BLOC, clase="WorkerW"),
        5: V(BLOC, clase="#32770"),
        6: V(BLOC, clase="MiDesktopWindow"),
        7: V((0, 0, 199, 500)),                                         # < 200 de ancho
        8: V((0, 0, 500, 59)),                                          # < 60 de alto
        9: V(BLOC, titulo=0),                                           # sin título
        10: V(BLOC, padre=2),                                           # hija / con dueño
        11: V(BLOC, raiz=2),
        12: V(BLOC, cloaked=True),
        13: V(BLOC, minimizada=True),
        14: V(BLOC, ex=WS_EX_LAYERED, capas=(200, LWA_ALPHA)),         # alfa ≤ 230
        15: V(BLOC, ex=WS_EX_LAYERED, capas=(240, LWA_ALPHA)),         # alfa 240: vale
        16: V(BLOC, ex=WS_EX_LAYERED | WS_EX_TRANSPARENT),
        17: V(BLOC, ex=WS_EX_LAYERED, capas=(255, LWA_COLORKEY)),
        18: V(BLOC, ex=WS_EX_LAYERED | WS_EX_TOOLWINDOW),
        19: V(BLOC, ex=WS_EX_LAYERED, capas=(254, LWA_ALPHA), clase="UnityWndClass"),   # Mate-Engine
        20: V((0, 0, 1920, 1080)),                                      # pantalla completa en su monitor
        21: V((1920, 0, 3840, 1080), monitor=MON2),                     # pantalla completa en el 2.º
        22: V(BLOC, pid=PID_LUNE),                                      # propia (la burbuja…)
        23: V(BLOC, pid=PID_LUNE, clase="Qt6QWindowIcon"),              # la principal de Lune: permitida
        24: V(BLOC, visible=False),
        25: V(BLOC, maximizada=True),
        26: V((1920, 0, 3000, 1000), monitor=MON1),                     # «pantalla completa» contra otro monitor: no
        27: V((300, -20, 1100, 500)),                                   # el borde por encima del monitor
    }
    api = ApiVentanasFalsa(vs)
    cands = va.listar_candidatas(api, excluir_pid=PID_LUNE, permitir=(23,))
    assert _ids(cands) == [1, 2, 15, 23, 26]
    barra = cands[0]
    assert barra.es_barra and barra.topmost and barra.rect == Rect(0, 1032, 1920, 1080)
    assert not any(c.es_barra for c in cands[1:])


def test_la_parece_asistente_sin_titulo_y_en_capas():
    api = ApiVentanasFalsa({
        1: V(BLOC, ex=WS_EX_LAYERED | WS_EX_NOACTIVATE, estilo=0, titulo=0),
        2: V(BLOC, ex=WS_EX_LAYERED, capas=(250, LWA_ALPHA), estilo=0, titulo=1),
        3: V(BLOC, ex=WS_EX_LAYERED, capas=(250, LWA_ALPHA), titulo=12),        # con título y marco: vale
    })
    assert va.parece_asistente(api, 2, "Otra") is True
    assert va.es_transparente(api, 1, "Otra") is True
    assert _ids(va.listar_candidatas(api, excluir_pid=PID_LUNE)) == [3]


def test_rect_visible_sin_el_borde_invisible():
    api = ApiVentanasFalsa({2: V((292, 400, 1108, 908), rect_visible=(300, 400, 1100, 900))})
    (c,) = va.listar_candidatas(api, excluir_pid=PID_LUNE)
    assert c.rect == Rect(300, 400, 1100, 900) and not c.es_barra and not c.topmost


def test_solo_ventanas_o_solo_barras():
    api = ApiVentanasFalsa({1: V((0, 1032, 1920, 1080), clase="Shell_TrayWnd"), 2: V(BLOC)})
    assert _ids(va.listar_candidatas(api, excluir_pid=PID_LUNE, barras=False)) == [2]
    assert _ids(va.listar_candidatas(api, excluir_pid=PID_LUNE, ventanas=False)) == [1]
    assert va.listar_candidatas(api, excluir_pid=PID_LUNE, ventanas=False, barras=False) == []


def test_tope_de_128_candidatas():
    api = ApiVentanasFalsa({h: V(BLOC) for h in range(1, 301)})
    assert len(va.listar_candidatas(api, excluir_pid=PID_LUNE)) == va.MAX_CANDIDATAS == 128
    assert len(va.listar_candidatas(api, excluir_pid=PID_LUNE, maximo=5)) == 5


def test_una_ventana_que_falla_no_rompe_la_lista():
    class Rota(ApiVentanasFalsa):
        def clase(self, h):
            if h == 1:
                raise OSError("se cerró entre medias")
            return super().clase(h)

    api = Rota({1: V(BLOC), 2: V(BLOC)})
    assert _ids(va.listar_candidatas(api, excluir_pid=PID_LUNE)) == [2]


# ── Oclusión y orden Z ─────────────────────────────────────────────────────────

def test_ocluida_por_una_ventana_de_arriba_que_tapa_el_punto():
    api = ApiVentanasFalsa({9: V((200, 300, 600, 700)), 2: V(BLOC)}, orden=[9, 2])
    assert va.ocluida_en(api, 2, 400, 402, excluir_pid=PID_LUNE) is True
    assert va.ocluida_en(api, 2, 900, 402, excluir_pid=PID_LUNE) is False     # fuera de la de arriba


@pytest.mark.parametrize("encima", [
    V((0, 0, 1920, 1080), pid=PID_LUNE),                                    # propia (la asistente)
    V((0, 0, 1920, 1080), visible=False),
    V((0, 0, 1920, 1080), cloaked=True),
    V((0, 0, 1920, 1080), minimizada=True),
    V((0, 0, 1920, 1080), ex=WS_EX_LAYERED, capas=(100, LWA_ALPHA)),         # transparente
    V((0, 0, 1920, 1080), ex=WS_EX_TRANSPARENT),                            # deja pasar los clics
    V((0, 0, 1920, 1080), ex=WS_EX_LAYERED, capas=(5, LWA_ALPHA), clase="X"),
])
def test_lo_que_no_tapa_se_salta(encima):
    api = ApiVentanasFalsa({9: encima, 2: V(BLOC)}, orden=[9, 2])
    assert va.ocluida_en(api, 2, 400, 402, excluir_pid=PID_LUNE) is False


def test_oclusion_con_tope_de_pasos():
    vs = {h: V((0, 0, 10, 10)) for h in range(1, 3001)}                     # 3000 por encima, lejos del punto
    vs[1] = V((0, 0, 1920, 1080))                                           # la de más arriba sí tapa
    vs[5000] = V(BLOC)
    api = ApiVentanasFalsa(vs, orden=list(range(1, 3001)) + [5000])
    assert va.ocluida_en(api, 5000, 400, 402, excluir_pid=PID_LUNE) is False   # no llega (tope 2048)
    assert va.ocluida_en(api, 5000, 400, 402, excluir_pid=PID_LUNE, pasos=3000) is True


def test_encima_de_sube_por_el_orden_z_con_tope():
    api = ApiVentanasFalsa({h: V(BLOC) for h in (1, 2, 3)}, orden=[1, 2, 3])
    assert va.encima_de(api, 1, 3) and va.encima_de(api, 2, 3)
    assert not va.encima_de(api, 3, 1) and not va.encima_de(api, 2, 2)
    api2 = ApiVentanasFalsa({h: V(BLOC) for h in range(1, 3002)}, orden=list(range(1, 3002)))
    assert not va.encima_de(api2, 1, 3001)
    assert va.encima_de(api2, 1, 3001, pasos=3000)


# ── Estado de la ventana objetivo ──────────────────────────────────────────────

@pytest.mark.parametrize("v,esperado", [
    (V(BLOC), "ok"),
    (V(BLOC, existe=False), "cerrada"),
    (V(BLOC, visible=False), "oculta"),
    (V(BLOC, minimizada=True), "minimizada"),
    (V(BLOC, cloaked=True), "cloaked"),
    (V(BLOC, maximizada=True), "maximizada"),
    (V((0, 0, 1920, 1080)), "pantalla_completa"),
    (V((-1, 1, 1921, 1079)), "pantalla_completa"),                          # ±2 px
    (V((-8, -8, 1928, 1040)), "ok"),                                        # maximizada con marco no cuenta
])
def test_estado_ventana(v, esperado):
    assert va.estado_ventana(ApiVentanasFalsa({2: v}), 2) == esperado


def test_estado_de_una_que_no_existe():
    assert va.estado_ventana(ApiVentanasFalsa({}), 77) == "cerrada"
    assert va.estado_ventana(ApiVentanasFalsa({}), 0) == "cerrada"


# ── Barra donde sentarse ───────────────────────────────────────────────────────

def test_barra_de_abajo_del_monitor_de_la_asistente():
    p = PantallaFalsa()
    b = va.barra_asiento(Rect(200, 500, 500, 1000), p)
    assert b == va.Candidata(0x100, Rect(0, 1032, 1920, 1080), True, True)
    b2 = va.barra_asiento(Rect(2500, 300, 2800, 800), p)                   # en el segundo monitor
    assert b2.hwnd == 0x200 and b2.rect == Rect(1920, 1040, 3840, 1080)
    assert va.barra_asiento(101, p).rect.arriba == 1032                    # también con el hmon
    assert va.barra_asiento(MON2, p).rect.arriba == 1040


def test_barra_lateral_o_arriba_no_vale():
    izq = Monitor(101, Rect(0, 0, 1920, 1080), Rect(60, 0, 1920, 1080), True, "D1")
    arr = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 48, 1920, 1080), True, "D1")
    assert va.barra_asiento(Rect(200, 200, 400, 400),
                            PantallaFalsa((izq,), {"Shell_TrayWnd": {1: Rect(0, 0, 60, 1080)}})) is None
    assert va.barra_asiento(Rect(200, 200, 400, 400),
                            PantallaFalsa((arr,), {"Shell_TrayWnd": {1: Rect(0, 0, 1920, 48)}})) is None


def test_barra_auto_oculta_es_el_borde_del_monitor():
    sin_franja = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080), True, "D1")
    for bandeja in (Rect(0, 1078, 1920, 1126), Rect(0, 1032, 1920, 1080)):   # oculta y desplegada
        p = PantallaFalsa((sin_franja,), {"Shell_TrayWnd": {7: bandeja}}, auto_oculta=True)
        b = va.barra_asiento(Rect(200, 500, 500, 1000), p)
        assert b is not None and b.hwnd == 7 and b.rect.arriba == 1080, bandeja   # no sigue al desplegarse


def test_sin_monitor_o_sin_barra_es_none():
    assert va.barra_asiento(Rect(9000, 9000, 9100, 9100), PantallaFalsa()) is None
    sin = Monitor(101, Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080), True, "D1")
    assert va.barra_asiento(Rect(0, 0, 100, 100), PantallaFalsa((sin,), {})) is None


# ── APIs ───────────────────────────────────────────────────────────────────────

def test_api_nula_responde_vacio():
    api = va.ApiVentanasNula()
    assert api.enumerar() == [] and api.rect(1) is None and api.monitor(1) is None
    assert va.listar_candidatas(api, excluir_pid=1) == []
    assert va.estado_ventana(api, 5) == "cerrada"
    assert va.ocluida_en(api, 5, 0, 0, excluir_pid=1) is False


class _Dll:
    pass


def _fn(impl):
    def f(*args):
        return impl(*args)
    return f


def test_api_win32_con_dlls_falsas():
    u, d = _Dll(), _Dll()
    orden = [11, 22, 33]

    def enum_windows(callback, lparam):
        for h in orden:
            if not callback(h, lparam):
                break
        return 1

    def rect(h, ref):
        ref._obj.left, ref._obj.top, ref._obj.right, ref._obj.bottom = (92, 40, 1108, 908)
        return 1

    def dwm(h, attr, ref, n):
        obj = ref._obj
        assert n == ctypes.sizeof(obj)
        if attr == va.DWMWA_EXTENDED_FRAME_BOUNDS:
            obj.left, obj.top, obj.right, obj.bottom = (100, 40, 1100, 900)
            return 0
        if attr == va.DWMWA_CLOAKED:
            obj.value = 2 if h == 33 else 0
            return 0
        return -1

    def capas(h, key, alfa, flags):
        alfa._obj.value, flags._obj.value = 200, LWA_ALPHA
        return 1

    def pid(h, ref):
        ref._obj.value = 4321
        return 1

    def clase(h, buf, n):
        buf.value = "Notepad"
        return 7

    def info(hmon, ref):
        mi = ref._obj
        mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom = (0, 0, 1920, 1080)
        mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom = (0, 0, 1920, 1032)
        return 1

    u.EnumWindows = _fn(enum_windows)
    u.GetForegroundWindow = _fn(lambda: 22)
    u.IsWindowVisible = _fn(lambda h: h != 11)
    u.IsWindow = _fn(lambda h: 1)
    u.IsIconic = _fn(lambda h: 0)
    u.IsZoomed = _fn(lambda h: h == 22)
    u.GetWindowRect = _fn(rect)
    u.GetClassNameW = _fn(clase)
    u.GetWindowTextLengthW = _fn(lambda h: 9)
    u.GetWindowLongW = _fn(lambda h, idx: -2147483648 if idx == va.GWL_EXSTYLE else 0x00CF0000)
    u.GetParent = _fn(lambda h: None)
    u.GetAncestor = _fn(lambda h, flag: h)
    u.GetWindow = _fn(lambda h, cmd: {33: 22, 22: 11}.get(h) if cmd == va.GW_HWNDPREV else None)
    u.GetLayeredWindowAttributes = _fn(capas)
    u.GetWindowThreadProcessId = _fn(pid)
    u.MonitorFromWindow = _fn(lambda h, flags: 101)
    u.GetMonitorInfoW = _fn(info)
    d.DwmGetWindowAttribute = _fn(dwm)

    api = va.ApiVentanasWin32(user32=u, dwmapi=d)
    assert api.enumerar() == [11, 22, 33]
    assert api.activa() == 22
    assert not api.visible(11) and api.visible(22)
    assert api.rect(22) == Rect(92, 40, 1108, 908)
    assert api.rect_visible(22) == Rect(100, 40, 1100, 900)
    assert api.cloaked(33) and not api.cloaked(22)
    assert api.capas(22) == (200, LWA_ALPHA)
    assert api.estilo_ex(22) == 0x80000000 and api.estilo(22) == 0x00CF0000
    assert api.clase(22) == "Notepad" and api.largo_titulo(22) == 9
    assert api.padre(22) == 0 and api.raiz(22) == 22 and api.maximizada(22) and not api.minimizada(22)
    assert api.anterior(33) == 22 and api.anterior(11) == 0
    assert api.pid(22) == 4321 and api.existe(22)
    assert api.monitor(22) == (Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1032))


def test_solo_lee_y_sin_ganchos_ni_procesos_ajenos():
    """El módulo no engancha eventos del sistema ni abre procesos ni escribe en ventanas ajenas."""
    src = (Path(va.__file__)).read_text(encoding="utf-8")
    for prohibido in ("SetWin" + "EventHook", "SetWindows" + "Hook", "Open" + "Process", "SetWindow" + "Pos",
                      "Move" + "Window(", "SetWindow" + "LongW", "Post" + "Message", "Send" + "Message"):
        assert prohibido not in src, prohibido


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_en_windows_real_solo_leyendo_no_falla():
    va._api_defecto = None
    api = va.api_defecto()
    assert isinstance(api, va.ApiVentanasWin32)
    cands = va.listar_candidatas(api, excluir_pid=0)
    assert isinstance(cands, list) and len(cands) <= va.MAX_CANDIDATAS
    for c in cands[:3]:
        assert va.estado_ventana(api, c.hwnd) in va.ESTADOS
