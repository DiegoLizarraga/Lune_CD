"""
Tests de servicios/atajos_globales: parseo, validación y el hilo de RegisterHotKey.

Sin Windows real: se inyecta un user32 falso con su propia cola de mensajes
(GetMessageW bloquea en una queue.Queue y PostThreadMessageW escribe en ella)
para comprobar que las altas y bajas se hacen DESDE el hilo del gestor (así lo
exige RegisterHotKey), que siempre va MOD_NOREPEAT, que un WM_HOTKEY llega al
callback con el id de Lune y que detener() lo suelta todo. Al final hay una
prueba con el user32 de verdad que se salta fuera de Windows.
"""
import queue
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import atajos_globales as A  # noqa: E402

CAS = A.MOD_CONTROL | A.MOD_ALT | A.MOD_SHIFT


# ── Parseo ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("combo, esperado", [
    ("ctrl+alt+shift+l", (CAS, 0x4C)),
    ("Ctrl + Shift + F5", (A.MOD_CONTROL | A.MOD_SHIFT, 0x74)),
    ("SHIFT+CTRL+ALT+L", (CAS, 0x4C)),
    ("f13", (0, 0x7C)),
    ("f24", (0, 0x87)),
    ("ctrl+shift+space", (A.MOD_CONTROL | A.MOD_SHIFT, 0x20)),
    ("ctrl+alt+shift+period", (CAS, 0xBE)),
    ("ctrl+alt+shift+.", (CAS, 0xBE)),
    ("ctrl+comma", (A.MOD_CONTROL, 0xBC)),
    ("ctrl+shift+escape", (A.MOD_CONTROL | A.MOD_SHIFT, 0x1B)),
    ("ctrl+shift+esc", (A.MOD_CONTROL | A.MOD_SHIFT, 0x1B)),
    ("ctrl+1", (A.MOD_CONTROL, 0x31)),
    ("ctrl++", (A.MOD_CONTROL, 0xBB)),
    ("win+shift+up", (A.MOD_WIN | A.MOD_SHIFT, 0x26)),
    ("ctrl+numpad5", (A.MOD_CONTROL, 0x65)),
    # Lo que manda el botón «Detectar» (KeyboardEvent.code de JS)
    ("Control+Shift+KeyL", (A.MOD_CONTROL | A.MOD_SHIFT, 0x4C)),
    ("ControlLeft+AltRight+Digit3", (A.MOD_CONTROL | A.MOD_ALT, 0x33)),
    ("Ctrl+ArrowUp", (A.MOD_CONTROL, 0x26)),
])
def test_parsear_combo(combo, esperado):
    assert A.parsear_combo(combo) == esperado


@pytest.mark.parametrize("combo", [
    "", "   ", "ctrl+alt", "ctrl+l+k", "ctrl+tecla_rara", "ctrl++alt", "+ctrl",
    "altgr+e",
])
def test_parsear_combo_invalido(combo):
    with pytest.raises(ValueError):
        A.parsear_combo(combo)


def test_parsear_no_incluye_norepeat():
    mods, _ = A.parsear_combo("ctrl+alt+shift+l")
    assert not mods & A.MOD_NOREPEAT


def test_texto_y_normalizar():
    assert A.texto_combo(CAS, 0x4C) == "Ctrl+Alt+Shift+L"
    assert A.texto_combo(A.MOD_CONTROL, 0x20) == "Ctrl+Espacio"
    assert A.normalizar("Shift+CTRL+l") == "ctrl+shift+l"
    assert A.normalizar("ctrl+alt+shift+.") == "ctrl+alt+shift+period"
    assert A.normalizar("Control+KeyK") == "ctrl+k"


# ── Validación ─────────────────────────────────────────────────────────────────

def test_validar_exige_modificador_salvo_f():
    assert A.validar("l") is not None             # una letra sola no
    assert A.validar("space") is not None
    assert A.validar("f5") is None                # F1–F24 sí
    assert A.validar("f20") is None
    assert A.validar("ctrl+l") is None


def test_validar_rechaza_win_alt():
    err = A.validar("win+alt+r")
    assert err and "Win+Alt" in err and not A.es_aviso(err)
    assert A.validar("ctrl+win+alt+k") is not None


def test_validar_shift_solo_con_tecla_que_escribe():
    assert A.validar("shift+a") is not None       # escribiría «A»
    assert A.validar("shift+f5") is None


def test_validar_f12_reservada():
    assert A.validar("f12") is not None
    assert A.validar("ctrl+f12") is not None


def test_validar_avisa_altgr():
    msg = A.validar("ctrl+alt+e")
    assert msg and "AltGr" in msg and A.es_aviso(msg)
    error, aviso = A.comprobar("ctrl+alt+e")
    assert error is None and "Shift" in aviso
    # Con Shift, o con una tecla que no escribe, no hay aviso
    assert A.validar("ctrl+alt+shift+e") is None
    assert A.validar("ctrl+alt+f5") is None


def test_validar_combo_que_no_parsea():
    assert "No conozco" in A.validar("ctrl+patata")


# ── Gestor con un user32 falso ─────────────────────────────────────────────────

class User32Falso:
    """Cola de mensajes por proceso y tabla de atajos, como haría Windows."""

    def __init__(self, ocupados=()):
        self._cola = queue.Queue()
        self.registrados = {}               # num → (mods, vk)
        self.hilos = set()                  # hilos que tocaron Register/Unregister
        self.ocupados = set(ocupados)       # (mods, vk) que tiene otra aplicación
        self.ultimo_error = 0
        self.llamadas = []

    def PeekMessageW(self, pmsg, hwnd, a, b, flags):
        return 0

    def GetMessageW(self, pmsg, hwnd, a, b):
        m, w, l = self._cola.get()
        pmsg.contents.message = m
        pmsg.contents.wParam = w
        pmsg.contents.lParam = l
        return 0 if m == A.WM_QUIT else 1

    def PostThreadMessageW(self, tid, m, w, l):
        self._cola.put((m, w, l))
        return 1

    def RegisterHotKey(self, hwnd, num, mods, vk):
        self.hilos.add(threading.get_ident())
        self.llamadas.append(("reg", num, mods, vk))
        par = (mods & ~A.MOD_NOREPEAT, vk)
        tomados = {(m & ~A.MOD_NOREPEAT, v) for m, v in self.registrados.values()}
        if par in self.ocupados or par in tomados:
            self.ultimo_error = A.ERROR_HOTKEY_ALREADY_REGISTERED
            return 0
        self.registrados[num] = (mods, vk)
        return 1

    def UnregisterHotKey(self, hwnd, num):
        self.hilos.add(threading.get_ident())
        self.llamadas.append(("unreg", num))
        return 1 if self.registrados.pop(num, None) else 0

    def pulsar(self, combo):
        """Simula que el usuario pulsa `combo`: Windows manda WM_HOTKEY con su num."""
        mods, vk = A.parsear_combo(combo)
        for num, (m, v) in self.registrados.items():
            if (m & ~A.MOD_NOREPEAT, v) == (mods, vk):
                self._cola.put((A.WM_HOTKEY, num, 0))
                return True
        return False


class Kernel32Falso:
    def GetCurrentThreadId(self):
        return threading.get_ident()


class Recogedor:
    def __init__(self):
        self.ids = []
        self.evento = threading.Event()
        self.hilo = None

    def __call__(self, id_):
        self.ids.append(id_)
        self.hilo = threading.get_ident()
        self.evento.set()

    def esperar(self):
        assert self.evento.wait(2), "no llegó el atajo"
        self.evento.clear()
        return self.ids[-1]


@pytest.fixture
def entorno():
    u32 = User32Falso(ocupados={(A.MOD_CONTROL | A.MOD_SHIFT, 0x1B)})   # Ctrl+Shift+Esc
    rec = Recogedor()
    g = A.GestorAtajos(rec, user32=u32, kernel32=Kernel32Falso(),
                       obtener_error=lambda: u32.ultimo_error)
    yield g, u32, rec
    g.detener()


def test_registrar_antes_de_iniciar_y_pulsar(entorno):
    g, u32, rec = entorno
    assert g.registrar("mostrar_lune", "ctrl+alt+shift+l") is None
    assert u32.registrados == {}                    # aún no hay hilo
    assert g.iniciar()
    hilo_gestor = g._hilo.ident
    assert list(u32.registrados.values()) == [(CAS | A.MOD_NOREPEAT, 0x4C)]
    assert u32.hilos == {hilo_gestor} and threading.get_ident() not in u32.hilos
    assert u32.pulsar("ctrl+alt+shift+l")
    assert rec.esperar() == "mostrar_lune"
    assert rec.hilo == hilo_gestor                  # el callback corre en el hilo de atajos


def test_registrar_con_hilo_en_marcha_lo_hace_el_hilo(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    assert g.registrar("pantalla_grande", "ctrl+alt+shift+g") is None
    assert u32.hilos == {g._hilo.ident}
    assert g.registrados() == {"pantalla_grande": "Ctrl+Alt+Shift+G"}
    u32.pulsar("ctrl+alt+shift+g")
    assert rec.esperar() == "pantalla_grande"


def test_combo_ocupado_por_otra_app(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    err = g.registrar("abrir", "ctrl+shift+escape")
    assert err and "otra aplicación" in err
    assert g.errores["abrir"] == err
    assert "abrir" not in g.registrados()


def test_combo_repetido_entre_acciones_de_lune(entorno):
    g, u32, rec = entorno
    assert g.registrar("a", "ctrl+alt+shift+k") is None
    err = g.registrar("b", "shift+alt+ctrl+k")
    assert err and "«a»" in err
    assert g.iniciar()
    err = g.registrar("b", "ctrl+alt+shift+k")
    assert err and "«a»" in err


def test_combo_invalido_no_llega_a_windows(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    assert g.registrar("x", "l") is not None
    assert g.registrar("x", "win+alt+r") is not None
    assert u32.llamadas == []


def test_aviso_altgr_no_impide_registrar(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    assert g.registrar("x", "ctrl+alt+e") is None
    assert (A.MOD_CONTROL | A.MOD_ALT | A.MOD_NOREPEAT, 0x45) in u32.registrados.values()


def test_cambiar_combo_de_un_id(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    assert g.registrar("x", "ctrl+alt+shift+1") is None
    assert g.registrar("x", "ctrl+alt+shift+2") is None
    assert list(u32.registrados.values()) == [(CAS | A.MOD_NOREPEAT, 0x32)]
    assert not u32.pulsar("ctrl+alt+shift+1")
    u32.pulsar("ctrl+alt+shift+2")
    assert rec.esperar() == "x"


def test_cambio_fallido_conserva_el_anterior(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    assert g.registrar("x", "ctrl+alt+shift+1") is None
    assert g.registrar("x", "ctrl+shift+escape") is not None      # ocupado fuera
    assert list(u32.registrados.values()) == [(CAS | A.MOD_NOREPEAT, 0x31)]
    assert g.registrados() == {"x": "Ctrl+Alt+Shift+1"}
    u32.pulsar("ctrl+alt+shift+1")
    assert rec.esperar() == "x"


def test_quitar_y_quitar_todos(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    g.registrar("a", "ctrl+alt+shift+a")
    g.registrar("b", "ctrl+alt+shift+b")
    g.quitar("a")
    assert list(u32.registrados.values()) == [(CAS | A.MOD_NOREPEAT, 0x42)]
    assert set(g.registrados()) == {"b"}
    g.quitar("no_existe")                          # no revienta
    g.quitar_todos()
    assert u32.registrados == {} and g.registrados() == {}
    assert u32.hilos == {g._hilo.ident}


def test_detener_suelta_todo_desde_su_hilo_y_reiniciar_los_repone(entorno):
    g, u32, rec = entorno
    assert g.iniciar()
    hilo = g._hilo
    g.registrar("a", "ctrl+alt+shift+a")
    g.registrar("b", "f20")
    g.detener()
    assert not hilo.is_alive() and not g.activo()
    assert u32.registrados == {}
    assert sum(1 for ll in u32.llamadas if ll[0] == "unreg") == 2
    assert u32.hilos == {hilo.ident}
    # Recuerda los atajos: al volver a iniciar se registran otra vez
    assert set(g.registrados()) == {"a", "b"}
    assert g.iniciar()
    assert len(u32.registrados) == 2
    u32.pulsar("f20")
    assert rec.esperar() == "b"


def test_callback_que_falla_no_mata_el_hilo(entorno):
    g, u32, rec = entorno
    llamadas = []

    def malo(id_):
        llamadas.append(id_)
        if len(llamadas) == 1:
            raise RuntimeError("uy")
        rec(id_)

    g._on_atajo = malo
    assert g.iniciar()
    g.registrar("x", "ctrl+alt+shift+x")
    u32.pulsar("ctrl+alt+shift+x")
    u32.pulsar("ctrl+alt+shift+x")
    assert rec.esperar() == "x"
    assert g.activo()


def test_registrar_desde_el_callback_no_se_bloquea(entorno):
    g, u32, rec = entorno
    resultado = {}

    def cb(id_):
        resultado["err"] = g.registrar("otro", "ctrl+alt+shift+o")
        rec(id_)

    g._on_atajo = cb
    assert g.iniciar()
    g.registrar("x", "ctrl+alt+shift+x")
    u32.pulsar("ctrl+alt+shift+x")
    assert rec.esperar() == "x"
    assert resultado["err"] is None
    assert "otro" in g.registrados()


def test_sin_windows_no_arranca(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "linux")
    g = A.GestorAtajos(lambda i: None)
    assert g.registrar("x", "ctrl+alt+shift+x") is None     # se guarda igual
    assert g.iniciar() is False
    assert not g.activo()


def test_sin_hooks_ni_librerias_de_teclado():
    """El módulo solo usa RegisterHotKey: nada de hooks ni librerías que lean todo el teclado."""
    fuente = (Path(A.__file__)).read_text(encoding="utf-8")
    prohibidos = ["import " + "keyboard", "pyn" + "put", "SetWindows" + "HookEx",
                  "WriteProcess" + "Memory", "CreateRemote" + "Thread"]
    for p in prohibidos:
        assert p not in fuente


# ── Con el user32 de verdad (solo Windows) ─────────────────────────────────────

@pytest.mark.skipif(sys.platform != "win32", reason="RegisterHotKey solo existe en Windows")
def test_win32_real_registra_y_recibe_wm_hotkey():
    rec = Recogedor()
    g = A.GestorAtajos(rec)
    try:
        assert g.iniciar()
        err = g.registrar("prueba", "ctrl+alt+shift+f23")
        if err and "otra aplicación" in err:
            pytest.skip("Ctrl+Alt+Shift+F23 ya está cogido en este equipo")
        assert err is None
        # Simula la pulsación mandando el mismo WM_HOTKEY que mandaría Windows
        num = g._nums["prueba"]
        assert g._u32.PostThreadMessageW(g._tid, A.WM_HOTKEY, num, 0)
        assert rec.esperar() == "prueba"
        g.quitar("prueba")
        assert g.registrados() == {}
    finally:
        g.detener()
    assert not g.activo()
