"""
Tests de servicios/win_ventana.py con una user32 falsa: los flags de SetWindowPos
(siempre SWP_NOACTIVATE, sin mover ni redimensionar), el orden Z pedido, el
cambio de estilo de la barra de tareas y que NUNCA se toca una ventana de otro
proceso (un juego). Sin Win32 real.
"""
import ctypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import win_ventana as wv  # noqa: E402

PROPIA, AJENA = 0x1234, 0x5678


class User32:
    def __init__(self, exstyle=0x00000100):
        self.llamadas = []
        self.exstyle = exstyle

    def GetWindowThreadProcessId(self, hwnd, ref):
        ref._obj.value = os.getpid() if hwnd == PROPIA else 4321
        return 1

    def SetWindowPos(self, hwnd, despues, x, y, cx, cy, flags):
        self.llamadas.append(("pos", hwnd, despues, flags))
        return 1

    def GetWindowLongW(self, hwnd, indice):
        assert indice == wv.GWL_EXSTYLE
        return ctypes.c_long(self.exstyle).value

    def SetWindowLongW(self, hwnd, indice, valor):
        self.llamadas.append(("estilo", hwnd, indice, valor & 0xFFFFFFFF))
        self.exstyle = valor & 0xFFFFFFFF
        return 1

    def SetForegroundWindow(self, hwnd):
        self.llamadas.append(("frente", hwnd))
        return 1


def _pos(u):
    return [(d, f) for (tipo, h, d, f) in (x for x in u.llamadas if x[0] == "pos")]


def test_set_encima_y_quitar_encima():
    u = User32()
    assert wv.set_encima(PROPIA, True, user32=u) is True
    assert wv.set_encima(PROPIA, False, user32=u) is True
    (d1, f1), (d2, f2) = _pos(u)
    assert (d1, d2) == (wv.HWND_TOPMOST, wv.HWND_NOTOPMOST)
    for f in (f1, f2):
        assert f & wv.SWP_NOACTIVATE and f & wv.SWP_NOMOVE and f & wv.SWP_NOSIZE


def test_al_fondo_quita_topmost_y_va_detras():
    u = User32()
    assert wv.al_fondo(PROPIA, user32=u) is True
    assert [d for d, _ in _pos(u)] == [wv.HWND_NOTOPMOST, wv.HWND_BOTTOM]
    assert all(f & wv.SWP_NOACTIVATE for _, f in _pos(u))


def test_traer_al_frente():
    u = User32()
    assert wv.traer_al_frente(PROPIA, user32=u) is True
    assert u.llamadas[0][0] == "pos" and u.llamadas[0][2] == wv.HWND_TOP
    assert u.llamadas[0][3] & wv.SWP_NOACTIVATE
    assert u.llamadas[1] == ("frente", PROPIA)


def test_nunca_toca_ventanas_de_otro_proceso():
    u = User32()
    assert wv.set_encima(AJENA, True, user32=u) is False
    assert wv.al_fondo(AJENA, user32=u) is False
    assert wv.traer_al_frente(AJENA, user32=u) is False
    assert wv.set_en_barra(AJENA, True, user32=u) is False
    assert wv.set_encima(0, True, user32=u) is False
    assert u.llamadas == []
    assert wv.es_propia(PROPIA, user32=u) and not wv.es_propia(AJENA, user32=u)


def test_set_en_barra_cambia_toolwindow_y_appwindow():
    u = User32(exstyle=wv.WS_EX_TOOLWINDOW | 0x100)
    assert wv.set_en_barra(PROPIA, True, user32=u) is True
    assert u.exstyle & wv.WS_EX_APPWINDOW and not u.exstyle & wv.WS_EX_TOOLWINDOW
    assert u.exstyle & 0x100                          # el resto del estilo se conserva
    pos = [x for x in u.llamadas if x[0] == "pos"][-1]
    assert pos[3] & wv.SWP_FRAMECHANGED and pos[3] & wv.SWP_NOZORDER and pos[3] & wv.SWP_NOACTIVATE
    assert wv.set_en_barra(PROPIA, False, user32=u) is True
    assert u.exstyle & wv.WS_EX_TOOLWINDOW and not u.exstyle & wv.WS_EX_APPWINDOW


def test_set_en_barra_con_el_bit_alto_no_desborda():
    u = User32(exstyle=0x80000000 | wv.WS_EX_TOOLWINDOW)
    assert wv.set_en_barra(PROPIA, True, user32=u) is True
    assert u.exstyle == 0x80000000 | wv.WS_EX_APPWINDOW


def test_fuera_de_windows_no_hace_nada(monkeypatch):
    monkeypatch.setattr(wv.sys, "platform", "linux")
    monkeypatch.setattr(wv, "_user32_real", None)
    assert wv.set_encima(PROPIA, True) is False
    assert wv.al_fondo(PROPIA) is False
    assert wv.set_en_barra(PROPIA, True) is False


# ── Sentarse (corte 7): rect_propia, mover, colocar_sobre, encima_de ──────────

OBJ, ENCIMA, INVISIBLE = 0x9000, 0x9100, 0x9200
FLAGS_Z = wv.SWP_NOMOVE | wv.SWP_NOSIZE | wv.SWP_NOACTIVATE | wv.SWP_NOOWNERZORDER


class User32Z(User32):
    """Con orden Z (lista de arriba abajo), estilos por ventana y visibilidad."""

    def __init__(self, orden, topmost=(), invisibles=()):
        super().__init__()
        self.orden = list(orden)
        self.topmost = set(topmost)
        self.invisibles = set(invisibles)

    def GetWindowLongW(self, hwnd, indice):
        assert indice == wv.GWL_EXSTYLE
        return wv.WS_EX_TOPMOST if hwnd in self.topmost else 0

    def GetWindow(self, hwnd, cmd):
        assert cmd == wv.GW_HWNDPREV
        i = self.orden.index(hwnd)
        return self.orden[i - 1] if i > 0 else None

    def IsWindowVisible(self, hwnd):
        return hwnd not in self.invisibles

    def GetWindowRect(self, hwnd, ref):
        ref._obj.left, ref._obj.top, ref._obj.right, ref._obj.bottom = (10, 20, 310, 520)
        return 1


def _pos_completas(u):
    return [x for x in u.llamadas if x[0] == "pos"]


def test_rect_propia_y_de_una_ajena_nada():
    u = User32Z([PROPIA, AJENA])
    assert wv.rect_propia(PROPIA, user32=u) == (10, 20, 310, 520)
    assert wv.rect_propia(PROPIA, user32=u).alto == 500
    assert wv.rect_propia(AJENA, user32=u) is None


def test_mover_con_flags_exactos_y_px_fisicos():
    llamadas = []

    class U(User32Z):
        def SetWindowPos(self, hwnd, despues, x, y, cx, cy, flags):
            llamadas.append((hwnd, despues, x, y, cx, cy, flags))
            return 1

    u = U([PROPIA])
    assert wv.mover(PROPIA, 1234.4, -56.6, user32=u) is True
    assert llamadas == [(PROPIA, 0, 1234, -57, 0, 0, wv.SWP_NOSIZE | wv.SWP_NOZORDER | wv.SWP_NOACTIVATE)]


def test_mover_o_colocar_una_ventana_ajena_no_llama_a_setwindowpos():
    u = User32Z([AJENA, OBJ, PROPIA])
    assert wv.mover(AJENA, 1, 2, user32=u) is False
    assert wv.colocar_sobre(AJENA, OBJ, user32=u) is False
    assert wv.encima_de(AJENA, OBJ, user32=u) is False
    assert wv.colocar_sobre(PROPIA, 0, user32=u) is False
    assert wv.colocar_sobre(PROPIA, PROPIA, user32=u) is False
    assert u.llamadas == []


def test_ya_encima_no_llama():
    u = User32Z([ENCIMA, PROPIA, OBJ])
    assert wv.encima_de(PROPIA, OBJ, user32=u) is True
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True
    assert u.llamadas == []


def test_encima_saltando_ventanas_invisibles():
    u = User32Z([PROPIA, INVISIBLE, OBJ], invisibles={INVISIBLE})
    assert wv.encima_de(PROPIA, OBJ, user32=u) is True
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True and u.llamadas == []
    u2 = User32Z([PROPIA, ENCIMA, OBJ])                     # una visible entre medias: no
    assert wv.encima_de(PROPIA, OBJ, user32=u2) is False


def test_colocar_sobre_un_objetivo_normal():
    u = User32Z([PROPIA, ENCIMA, OBJ])
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True
    assert _pos_completas(u) == [("pos", PROPIA, ENCIMA, FLAGS_Z)]      # detrás de la que tapa al objetivo


def test_colocar_sobre_un_objetivo_normal_estando_la_propia_siempre_encima():
    u = User32Z([PROPIA, ENCIMA, OBJ], topmost={PROPIA})
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True
    assert _pos_completas(u) == [("pos", PROPIA, wv.HWND_NOTOPMOST, FLAGS_Z), ("pos", PROPIA, ENCIMA, FLAGS_Z)]


def test_objetivo_normal_con_una_siempre_encima_justo_arriba_va_a_hwnd_top():
    u = User32Z([ENCIMA, OBJ, PROPIA], topmost={ENCIMA})
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True
    assert _pos_completas(u) == [("pos", PROPIA, wv.HWND_TOP, FLAGS_Z)]
    u2 = User32Z([OBJ, PROPIA])                               # nada encima del objetivo
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u2) is True
    assert _pos_completas(u2) == [("pos", PROPIA, wv.HWND_TOP, FLAGS_Z)]


def test_objetivo_siempre_encima():
    u = User32Z([ENCIMA, OBJ, PROPIA], topmost={ENCIMA, OBJ})
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u) is True
    assert _pos_completas(u) == [("pos", PROPIA, wv.HWND_TOPMOST, FLAGS_Z), ("pos", PROPIA, ENCIMA, FLAGS_Z)]
    u2 = User32Z([OBJ, PROPIA], topmost={OBJ, PROPIA})        # el primero de todos y la propia ya topmost
    assert wv.colocar_sobre(PROPIA, OBJ, user32=u2) is True
    assert _pos_completas(u2) == [("pos", PROPIA, wv.HWND_TOPMOST, FLAGS_Z)]


def test_nunca_se_reordena_ni_se_mueve_el_objetivo():
    for orden, top in (([PROPIA, ENCIMA, OBJ], {PROPIA}), ([ENCIMA, OBJ, PROPIA], {ENCIMA, OBJ})):
        u = User32Z(orden, topmost=top)
        wv.colocar_sobre(PROPIA, OBJ, user32=u)
        wv.mover(PROPIA, 5, 5, user32=u)
        assert {x[1] for x in u.llamadas if x[0] == "pos"} == {PROPIA}


def test_sentarse_fuera_de_windows_no_hace_nada(monkeypatch):
    monkeypatch.setattr(wv.sys, "platform", "linux")
    monkeypatch.setattr(wv, "_user32_real", None)
    assert wv.rect_propia(PROPIA) is None
    assert wv.mover(PROPIA, 1, 1) is False
    assert wv.colocar_sobre(PROPIA, OBJ) is False
    assert wv.encima_de(PROPIA, OBJ) is False
