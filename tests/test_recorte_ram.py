"""
Tests de servicios/recorte_ram.py: `recortar()` vacía el working set SOLO de los
procesos de Lune (el propio y sus QtWebEngineProcess), con el acceso justo
(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION), cierra cada handle, tolera
fallos y mide antes/después; gc solo en el hilo principal. Y `ProgramadorRecorte`
(0, 10 y 15 s tras activarlo y luego cada 600 s; nunca mientras anima).

Con psapi, kernel32 y psutil falsos: ningún proceso real se toca.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import recorte_ram as rr  # noqa: E402
from servicios.win_pantalla import PidsLune  # noqa: E402

PID_LUNE, PID_WEBENGINE, PID_LANZADO, PID_AJENO = 1000, 1001, 77, 4321


class ApiPids:
    def pid_propio(self): return PID_LUNE
    def hijos(self, pid): return [(PID_WEBENGINE, "QtWebEngineProcess.exe"), (PID_LANZADO, "juego.exe")]


class Proc:
    def __init__(self, ps, pid, nombre):
        self.ps, self.pid, self._nombre = ps, pid, nombre

    def name(self): return self._nombre

    def children(self, recursive=False):
        return [self.ps.procs[p] for p in (PID_WEBENGINE, PID_LANZADO)] if self.pid == PID_LUNE else []

    def memory_info(self):
        rss = self.ps.rss[self.pid]
        class M:
            pass
        m = M(); m.rss = rss
        return m


class Psutil:
    def __init__(self):
        self.procs = {p: Proc(self, p, n) for p, n in [(PID_LUNE, "python.exe"),
                                                       (PID_WEBENGINE, "QtWebEngineProcess.exe"),
                                                       (PID_LANZADO, "juego.exe"), (PID_AJENO, "otro.exe")]}
        self.rss = {PID_LUNE: 300 * rr.MB, PID_WEBENGINE: 200 * rr.MB, PID_LANZADO: 999 * rr.MB,
                    PID_AJENO: 999 * rr.MB}

    def Process(self, pid):
        return self.procs[pid]


class Kernel32:
    def __init__(self, fallar=()):
        self.abiertos, self.cerrados = [], []
        self.fallar = set(fallar)

    def OpenProcess(self, acceso, heredar, pid):
        assert acceso == rr.PROCESS_SET_QUOTA | rr.PROCESS_QUERY_INFORMATION == 0x0500
        assert heredar is False
        self.abiertos.append(pid)
        if pid in self.fallar:
            return 0                                   # acceso denegado
        return 10_000 + pid

    def CloseHandle(self, h):
        self.cerrados.append(h)
        return 1


class Psapi:
    def __init__(self, ps, fallar=()):
        self.ps, self.vaciados, self.fallar = ps, [], set(fallar)

    def EmptyWorkingSet(self, h):
        pid = h - 10_000
        if pid in self.fallar:
            raise OSError("no se pudo")
        self.vaciados.append(pid)
        self.ps.rss[pid] = 50 * rr.MB
        return 1


def test_recorta_solo_los_procesos_de_lune():
    ps = Psutil()
    k, p = Kernel32(), None
    p = Psapi(ps)
    antes, despues = rr.recortar(pids=PidsLune(ApiPids()), psapi=p, kernel32=k, psutil_mod=ps,
                                 recolectar=False)
    assert k.abiertos == [PID_LUNE, PID_WEBENGINE]      # ni el juego lanzado ni ajenos
    assert p.vaciados == [PID_LUNE, PID_WEBENGINE]
    assert sorted(k.cerrados) == [10_000 + PID_LUNE, 10_000 + PID_WEBENGINE]
    assert (antes, despues) == (500.0, 100.0)


def test_rechaza_pids_ajenos_colados_en_la_lista():
    ps = Psutil()
    k, p = Kernel32(), Psapi(ps)

    class PidsTrampa:
        api = ApiPids()
        def pids(self): return {PID_LUNE, PID_AJENO, PID_LANZADO}

    rr.recortar(pids=PidsTrampa(), psapi=p, kernel32=k, psutil_mod=ps, recolectar=False)
    assert k.abiertos == [PID_LUNE] and p.vaciados == [PID_LUNE]
    k2 = Kernel32()
    rr.recortar(pids={PID_AJENO}, psapi=Psapi(ps), kernel32=k2, psutil_mod=ps, recolectar=False)
    assert k2.abiertos == []


def test_tolera_procesos_que_no_se_dejan_abrir_o_fallan():
    ps = Psutil()
    k = Kernel32(fallar={PID_LUNE})
    p = Psapi(ps, fallar={PID_WEBENGINE})
    antes, despues = rr.recortar(pids=PidsLune(ApiPids()), psapi=p, kernel32=k, psutil_mod=ps,
                                 recolectar=False)
    assert p.vaciados == []
    assert k.cerrados == [10_000 + PID_WEBENGINE]     # el handle que sí se abrió se cierra igual
    assert antes == despues == 500.0


def test_sin_psutil_ni_dlls_no_falla(monkeypatch):
    class PsRoto:
        def Process(self, pid): raise RuntimeError("sin psutil")
    r = rr.recortar(pids=PidsLune(ApiPids()), psapi=Psapi(Psutil()), kernel32=Kernel32(),
                    psutil_mod=PsRoto(), recolectar=False)
    assert r == (0.0, 0.0)


def test_gc_solo_en_el_hilo_principal(monkeypatch):
    llamadas = []
    monkeypatch.setattr(rr.gc, "collect", lambda *a: llamadas.append(threading.current_thread().name) or 0)
    ps = Psutil()
    rr.recortar(pids=PidsLune(ApiPids()), psapi=Psapi(ps), kernel32=Kernel32(), psutil_mod=ps)
    assert llamadas == [threading.main_thread().name]
    llamadas.clear()
    hilo = threading.Thread(target=lambda: rr.recortar(pids=PidsLune(ApiPids()), psapi=Psapi(ps),
                                                       kernel32=Kernel32(), psutil_mod=ps), name="otro")
    hilo.start(); hilo.join()
    assert llamadas == []


# ── Programador ───────────────────────────────────────────────────────────────

class Reloj:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


def test_programador_0_10_15_y_cada_600():
    reloj = Reloj()
    prog = rr.ProgramadorRecorte(reloj=reloj)
    assert prog.toca() is False                       # apagado
    prog.activar(True)
    disparos = []
    for s in range(0, 1300, 2):
        reloj.t = 1000.0 + s
        if prog.toca():
            disparos.append(s)
    assert disparos == [0, 10, 16, 600, 1200]


def test_programador_no_toca_mientras_anima_y_lo_hace_despues():
    reloj = Reloj()
    prog = rr.ProgramadorRecorte(reloj=reloj)
    prog.activar(True)
    assert prog.toca(animando=True) is False
    reloj.t += 12
    assert prog.toca(animando=True) is False
    assert prog.toca() is True                        # los pasos 0 y 10 pendientes: uno solo
    assert prog.toca() is False
    reloj.t += 4
    assert prog.toca() is True                        # el de 15 s


def test_programador_apagar_y_reactivar_empieza_de_cero():
    reloj = Reloj()
    prog = rr.ProgramadorRecorte(reloj=reloj)
    prog.activar(True)
    assert prog.toca()
    prog.activar(False)
    reloj.t += 700
    assert prog.toca() is False
    prog.activar(True)
    assert prog.toca() is True and prog.activo
