"""
Tests de servicios/mutex_win: el dueño se decide con WaitForSingleObject(h, 0)
y el perdedor CIERRA su handle, para poder serlo más adelante.

Con una API falsa que imita un kernel (un mutex con dueño y cuenta de
handles) y, en Windows, con mutex reales repartidos entre hilos (la propiedad
de un mutex de Windows es por hilo).
"""
import sys
import threading
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import mutex_win as M  # noqa: E402
from servicios.mutex_win import (  # noqa: E402
    WAIT_ABANDONED, WAIT_FAILED, WAIT_OBJECT_0, WAIT_TIMEOUT, ApiMutexWin32,
    MutexNombrado, normalizar_nombre,
)


class ApiFalsa:
    """Registra las llamadas y devuelve lo que el test pida en `esperas`."""

    def __init__(self, esperas=(WAIT_OBJECT_0,), handle=42):
        self.esperas = list(esperas)
        self.handle = handle
        self.llamadas = []
        self.abiertos = set()
        self._siguiente = handle

    def crear(self, nombre):
        self.llamadas.append(("crear", nombre))
        if not self.handle:
            return 0
        h = self._siguiente
        self._siguiente += 1
        self.abiertos.add(h)
        return h

    def esperar(self, h, ms):
        self.llamadas.append(("esperar", h, ms))
        return self.esperas.pop(0) if self.esperas else WAIT_TIMEOUT

    def soltar(self, h):
        self.llamadas.append(("soltar", h))
        return True

    def cerrar(self, h):
        self.llamadas.append(("cerrar", h))
        self.abiertos.discard(h)
        return True

    def ultimo_error(self):
        return 5


# ── Nombres ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, salida", [
    ("Lune_CD_Alarmas", "Local\\Lune_CD_Alarmas"),
    ("Local\\Lune_CD_Alarmas", "Local\\Lune_CD_Alarmas"),
    ("Global\\LuneDiscordRPC", "Global\\LuneDiscordRPC"),
    ("Local\\a\\b", "Local\\a_b"),
    ("raro\\nombre", "Local\\raro_nombre"),
    ("", "Local\\Lune_CD"),
])
def test_normalizar_nombre(entrada, salida):
    assert normalizar_nombre(entrada) == salida


# ── Con la API falsa ──────────────────────────────────────────────────────────

def test_dueno_con_wait_object_0_y_liberar_suelta_y_cierra():
    api = ApiFalsa(esperas=[WAIT_OBJECT_0])
    m = MutexNombrado("Lune_CD_Alarmas", api=api)
    assert m.adquirir() is True
    assert m.es_dueno and not m.abandonado
    assert api.llamadas == [("crear", "Local\\Lune_CD_Alarmas"), ("esperar", 42, 0)]
    assert api.abiertos == {42}                   # el dueño conserva su handle
    m.liberar()
    assert api.llamadas[-2:] == [("soltar", 42), ("cerrar", 42)]
    assert not m.es_dueno and api.abiertos == set()
    m.liberar()                                   # idempotente
    assert len(api.llamadas) == 4


def test_el_perdedor_cierra_su_handle_y_puede_reintentar():
    """La crítica: con ERROR_ALREADY_EXISTS el perdedor se quedaba el handle y nunca era dueño."""
    api = ApiFalsa(esperas=[WAIT_TIMEOUT, WAIT_TIMEOUT, WAIT_OBJECT_0])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is False
    assert api.abiertos == set()                  # cerrado en el acto
    assert ("cerrar", 42) in api.llamadas
    assert m.adquirir() is False
    assert api.abiertos == set()
    assert m.adquirir() is True                   # el dueño se fue: ahora sí
    assert m.es_dueno and api.abiertos == {44}
    assert [c for c in api.llamadas if c[0] == "crear"] == [("crear", "Local\\X")] * 3


def test_abandonado_tambien_es_dueno():
    api = ApiFalsa(esperas=[WAIT_ABANDONED])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is True
    assert m.abandonado is True


def test_wait_failed_no_es_dueno_y_cierra():
    api = ApiFalsa(esperas=[WAIT_FAILED])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is False
    assert api.abiertos == set()


def test_crear_falla():
    api = ApiFalsa(handle=0)
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is False
    assert m.ultimo_error == 5
    assert not any(c[0] in ("esperar", "cerrar") for c in api.llamadas)


def test_adquirir_dos_veces_no_abre_otro_handle():
    api = ApiFalsa(esperas=[WAIT_OBJECT_0])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() and m.adquirir()
    assert [c[0] for c in api.llamadas].count("crear") == 1


def test_context_manager():
    api = ApiFalsa(esperas=[WAIT_OBJECT_0])
    with MutexNombrado("X", api=api) as m:
        assert m.es_dueno
    assert not m.es_dueno
    assert api.abiertos == set()


def test_context_manager_sin_ser_dueno_no_suelta_nada():
    api = ApiFalsa(esperas=[WAIT_TIMEOUT])
    with MutexNombrado("X", api=api) as m:
        assert not m.es_dueno
    assert not any(c[0] == "soltar" for c in api.llamadas)


def test_api_que_lanza_no_rompe():
    class Rota(ApiFalsa):
        def crear(self, nombre):
            raise OSError("kernel32")
    assert MutexNombrado("X", api=Rota()).adquirir() is False


def test_fuera_de_windows_siempre_adquiere(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    m = MutexNombrado("Lune_CD_Alarmas")
    assert m.adquirir() is True and m.es_dueno
    m.liberar()
    assert not m.es_dueno
    with MutexNombrado("otro") as m2:
        assert m2.es_dueno


# ── ApiMutexWin32 con una kernel32 falsa ──────────────────────────────────────

class _Dll:
    pass


def _fn(impl):
    def f(*args):
        return impl(*args)
    return f


def test_api_win32_llama_a_kernel32_como_toca():
    k = _Dll()
    llamadas = []
    k.CreateMutexW = _fn(lambda sa, inicial, nombre: llamadas.append(("crear", sa, inicial, nombre)) or 0x1234)
    k.WaitForSingleObject = _fn(lambda h, ms: llamadas.append(("esperar", h, ms)) or WAIT_OBJECT_0)
    k.ReleaseMutex = _fn(lambda h: llamadas.append(("soltar", h)) or 1)
    k.CloseHandle = _fn(lambda h: llamadas.append(("cerrar", h)) or 1)
    m = MutexNombrado("Y", api=ApiMutexWin32(kernel32=k))
    assert m.adquirir() is True
    m.liberar()
    assert llamadas == [("crear", None, False, "Local\\Y"), ("esperar", 0x1234, 0),
                        ("soltar", 0x1234), ("cerrar", 0x1234)]


# ── Windows de verdad: la propiedad es por hilo ───────────────────────────────

def _en_hilo(fn):
    resultado = {}

    def correr():
        resultado["v"] = fn()
    t = threading.Thread(target=correr)
    t.start()
    t.join(5)
    return resultado.get("v")


def _nombre_unico():
    return f"Local\\LuneTest_{uuid.uuid4().hex}"


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_windows_real_un_solo_dueno_y_relevo():
    nombre = _nombre_unico()
    a = MutexNombrado(nombre)
    assert a.adquirir() is True

    b = MutexNombrado(nombre)
    assert _en_hilo(b.adquirir) is False          # otro hilo: no es dueño
    assert b._h == 0                               # y no se quedó ningún handle

    a.liberar()

    def b_toma_y_suelta():
        ok = b.adquirir()
        abandonado = b.abandonado
        b.liberar()
        return ok, abandonado
    assert _en_hilo(b_toma_y_suelta) == (True, False)


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_windows_real_el_hilo_que_llamo_puede_terminar_sin_perder_el_mutex():
    """La revisión: adquirir() desde un hilo que termina dejaba el mutex
    abandonado; otro lo tomaba y este seguía diciendo que era el dueño."""
    nombre = _nombre_unico()
    a = MutexNombrado(nombre)
    assert _en_hilo(a.adquirir) is True             # el hilo que llamó ya terminó
    assert a.es_dueno and a.adquirir() is True      # y seguimos siendo dueños de verdad
    b = MutexNombrado(nombre)
    assert _en_hilo(b.adquirir) is False and b.adquirir() is False
    a.liberar()                                      # desde otro hilo distinto: funciona igual
    assert not a.es_dueno
    assert b.adquirir() is True and b.abandonado is False   # soltado bien, no abandonado
    b.liberar()


_HIJO = r'''
import os, sys
sys.path.insert(0, {raiz!r})
from servicios.mutex_win import MutexNombrado
m = MutexNombrado({nombre!r})
print(int(m.adquirir()), int(m.abandonado), flush=True)
if {morir}:
    os._exit(0)          # muere sin soltarlo (ni finalizadores)
m.liberar()
'''


def _otro_proceso(nombre, morir=False):
    import subprocess
    codigo = _HIJO.format(raiz=str(Path(__file__).resolve().parent.parent), nombre=nombre, morir=morir)
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    ok, abandonado = r.stdout.split()
    return bool(int(ok)), bool(int(abandonado))


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_windows_real_otro_proceso_no_lo_toma_si_el_hilo_que_llamo_termino():
    nombre = _nombre_unico()
    a = MutexNombrado(nombre)
    assert _en_hilo(a.adquirir) is True
    assert _otro_proceso(nombre) == (False, False)  # antes: (True, True) con los dos «dueños»
    assert a.es_dueno
    a.liberar()
    assert _otro_proceso(nombre) == (True, False)


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_windows_real_proceso_que_muere_deja_el_mutex_abandonado():
    nombre = _nombre_unico()
    api = M.ApiMutexWin32()
    testigo = api.crear(nombre)                      # mantiene vivo el objeto cuando el hijo muere
    try:
        assert _otro_proceso(nombre, morir=True) == (True, False)
        heredero = MutexNombrado(nombre)
        assert heredero.adquirir() is True
        assert heredero.abandonado is True
        heredero.liberar()
    finally:
        api.cerrar(testigo)


# ── El hilo propio (con la API falsa) ─────────────────────────────────────────

class ApiConHilos(ApiFalsa):
    """Apunta en qué hilo se hace cada llamada."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.hilos = []

    def crear(self, nombre):
        self.hilos.append(("crear", threading.get_ident()))
        return super().crear(nombre)

    def soltar(self, h):
        self.hilos.append(("soltar", threading.get_ident()))
        return super().soltar(h)


def test_todas_las_llamadas_van_por_el_hilo_propio():
    api = ApiConHilos(esperas=[WAIT_OBJECT_0])
    m = MutexNombrado("X", api=api)
    assert _en_hilo(m.adquirir) is True             # adquiere un hilo que termina…
    m.liberar()                                      # …y suelta el principal
    (_, h_crear), (_, h_soltar) = api.hilos
    assert h_crear == h_soltar != threading.get_ident()
    assert api.llamadas[-2:] == [("soltar", 42), ("cerrar", 42)]


def test_si_el_hilo_propio_muere_deja_de_ser_dueno_y_reintenta():
    api = ApiFalsa(esperas=[WAIT_OBJECT_0, WAIT_ABANDONED])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is True and m.es_dueno
    m._hilo.parar()                                  # su hilo ya no vive: mutex abandonado
    assert m.es_dueno is False
    assert m.adquirir() is True and m.abandonado is True
    assert ("cerrar", 42) in api.llamadas            # soltó el handle viejo
    assert [c[0] for c in api.llamadas].count("crear") == 2 and api.abiertos == {43}
    m.liberar()
    assert api.abiertos == set()


def test_liberar_para_el_hilo_propio_tambien_al_perdedor():
    api = ApiFalsa(esperas=[WAIT_TIMEOUT])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is False
    hilo = m._hilo._hilo
    assert hilo.is_alive()                           # el perdedor lo conserva para reintentar
    m.liberar()
    assert not hilo.is_alive()


def test_una_instancia_olvidada_suelta_y_para_su_hilo():
    import gc
    import time
    api = ApiFalsa(esperas=[WAIT_OBJECT_0])
    m = MutexNombrado("X", api=api)
    assert m.adquirir() is True
    hilo = m._hilo._hilo
    del m
    gc.collect()
    hilo.join(5)
    assert not hilo.is_alive()
    limite = time.monotonic() + 5
    while api.abiertos and time.monotonic() < limite:
        time.sleep(0.01)
    assert ("soltar", 42) in api.llamadas and api.abiertos == set()
