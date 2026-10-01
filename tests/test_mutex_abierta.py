"""
Tests del mutex «Lune está abierta» (servicios/mutex_win.marcar_abierta): main.py y
patata.py lo crean al arrancar SIN pedir la propiedad y guardan el handle hasta salir;
el instalador (CheckForMutexes con nucleo.rutas.MUTEX_ABIERTA) espera a que no exista.
"""
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import rutas  # noqa: E402
from servicios import mutex_win as M  # noqa: E402


class ApiFalsa:
    def __init__(self, handle=77):
        self.handle = handle
        self.llamadas = []

    def crear(self, nombre):
        self.llamadas.append(("crear", nombre))
        return self.handle

    def esperar(self, h, ms):                         # nunca se pide la propiedad
        raise AssertionError("marcar_abierta no debe esperar al mutex")

    def cerrar(self, h):
        self.llamadas.append(("cerrar", h))
        return True


@pytest.fixture(autouse=True)
def _limpio():
    M.desmarcar_abierta()
    yield
    M.desmarcar_abierta()


def test_crea_el_mutex_con_el_nombre_de_rutas_sin_tomarlo():
    api = ApiFalsa()
    assert M.marcar_abierta(api=api) == 77
    assert api.llamadas == [("crear", "Local\\" + rutas.MUTEX_ABIERTA)]
    assert rutas.MUTEX_ABIERTA == "LuneCD_Abierta"


def test_una_vez_por_proceso_y_el_handle_se_guarda():
    api = ApiFalsa()
    assert M.marcar_abierta(api=api) == 77
    assert M.marcar_abierta(api=ApiFalsa(handle=99)) == 77          # el mismo, sin crear otro
    assert api.llamadas == [("crear", "Local\\LuneCD_Abierta")]
    M.desmarcar_abierta()
    assert api.llamadas[-1] == ("cerrar", 77)


def test_si_falla_devuelve_cero_y_se_puede_reintentar():
    assert M.marcar_abierta(api=ApiFalsa(handle=0)) == 0

    class Rota(ApiFalsa):
        def crear(self, nombre):
            raise OSError("kernel32")
    assert M.marcar_abierta(api=Rota()) == 0
    assert M.marcar_abierta(api=ApiFalsa(handle=5)) == 5


def test_fuera_de_windows_no_hace_nada(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert M.marcar_abierta() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_windows_real_el_mutex_existe_mientras_lune_esta_abierta():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenMutexW.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    SYNCHRONIZE = 0x00100000
    nombre = f"LuneCD_Abierta_test_{uuid.uuid4().hex[:8]}"

    def existe():
        h = k.OpenMutexW(SYNCHRONIZE, False, nombre)           # como lo mira el instalador
        if h:
            k.CloseHandle(h)
        return bool(h)

    assert not existe()
    assert M.marcar_abierta(nombre) != 0
    assert existe()
    # Otro proceso de Lune (la app y patata a la vez) también puede crearlo: no hay dueño.
    otro = M.ApiMutexWin32()
    h2 = otro.crear(M.normalizar_nombre(nombre))
    assert h2
    otro.cerrar(h2)
    assert existe()
    M.desmarcar_abierta()
    assert not existe()


def test_main_y_patata_lo_marcan_al_arrancar():
    import inspect
    raiz = Path(__file__).resolve().parent.parent
    main_src = (raiz / "main.py").read_text("utf-8")
    assert "from servicios.mutex_win import marcar_abierta" in main_src
    patata_src = (raiz / "patata.py").read_text("utf-8")
    assert "from servicios.mutex_win import marcar_abierta" in patata_src
    import patata
    fuente = inspect.getsource(patata.main)
    # Tras la instancia única (la patata que se va enseguida no lo marca).
    assert fuente.index("inst.adquirir()") < fuente.index("_marcar_abierta()")
