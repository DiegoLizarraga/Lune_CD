"""
Tests de servicios/instancia_patata.py y de su uso en patata.main y main._lanzar_patata
(revisión 7-10, SV4): una sola patata a la vez. La patata del arranque con Windows y un
doble clic en iniciar_lune.vbs daban dos terminales con Lune.

Con dobles (mutex y API de eventos) y, en Windows, con un mutex y un evento de verdad
de nombre propio al azar (nunca los de una patata real). Sin procesos.
"""
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import instancia_patata as ip  # noqa: E402


class MutexFalso:
    def __init__(self, libre=True):
        self.libre, self.liberado = libre, 0

    def adquirir(self):
        return self.libre

    def liberar(self):
        self.liberado += 1


class ApiFalsa:
    """Eventos con nombre en memoria (compartidos entre «procesos» del test)."""

    def __init__(self, eventos=None):
        self.eventos = eventos if eventos is not None else {}    # nombre → threading.Event
        self.h = {}
        self.permisos = 0
        self.al_frente = []

    def crear(self, nombre):
        ev = self.eventos.setdefault(nombre, threading.Event())
        h = len(self.h) + 100
        self.h[h] = ev
        return h

    def abrir(self, nombre):
        if nombre not in self.eventos:
            return 0
        h = len(self.h) + 100
        self.h[h] = self.eventos[nombre]
        return h

    def senalar(self, h):
        self.h[h].set()
        return True

    def esperar(self, h, ms):
        ev = self.h[h]
        if ev.wait(ms / 1000.0):
            ev.clear()                      # reinicio automático
            return ip.WAIT_OBJECT_0
        return 0x102

    def cerrar(self, h):
        self.h.pop(h, None)

    def permitir_primer_plano(self):
        self.permisos += 1

    def traer_consola(self):
        self.al_frente.append(1)
        return True


def _esperar(cond, s=3.0):
    fin = time.monotonic() + s
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_la_primera_es_duena_y_la_segunda_avisa_para_que_se_ensene():
    api = ApiFalsa()
    viva = ip.InstanciaPatata(mutex=MutexFalso(True), api=api)
    assert viva.adquirir() is True and ip.NOMBRE_EVENTO in api.eventos
    pedidos = []
    assert viva.escuchar(lambda: pedidos.append(1)) is True
    otra = ip.InstanciaPatata(mutex=MutexFalso(False), api=ApiFalsa(api.eventos))
    assert otra.adquirir() is False
    assert otra.pedir_mostrar() is True
    assert _esperar(lambda: pedidos == [1])
    viva.liberar()
    assert viva._hilo is None and viva._mutex.liberado == 1
    viva.liberar()                                            # idempotente
    assert viva._mutex.liberado == 1


def test_sin_patata_viva_nadie_contesta():
    api = ApiFalsa()
    assert ip.pedir_mostrar(api) is False and ip.patata_viva(api) is False
    api.crear(ip.NOMBRE_EVENTO)
    assert ip.patata_viva(api) is True and not api.eventos[ip.NOMBRE_EVENTO].is_set()   # mirar no avisa
    assert ip.pedir_mostrar(api) is True and api.permisos == 1


def test_fuera_de_windows_siempre_es_la_unica():
    inst = ip.InstanciaPatata(mutex=MutexFalso(True), api=ip.ApiEventoNula())
    assert inst.adquirir() is True and inst.escuchar(lambda: None) is False
    assert ip.pedir_mostrar(ip.ApiEventoNula()) is False
    inst.liberar()


@pytest.mark.skipif(sys.platform != "win32", reason="mutex y eventos con nombre de Windows")
def test_con_mutex_y_evento_de_verdad():
    from servicios.mutex_win import MutexNombrado
    sufijo = uuid.uuid4().hex
    nm, ne = f"Local\\Lune_test_patata_{sufijo}", f"Local\\Lune_test_patata_evento_{sufijo}"
    viva = ip.InstanciaPatata(mutex=MutexNombrado(nm), nombre_evento=ne)
    otra = ip.InstanciaPatata(mutex=MutexNombrado(nm), nombre_evento=ne)
    try:
        assert viva.adquirir() is True
        pedidos = []
        viva.escuchar(lambda: pedidos.append(1))
        assert otra.adquirir() is False
        assert ip.patata_viva(nombre_evento=ne) is True
        assert otra.pedir_mostrar() is True
        assert _esperar(lambda: pedidos == [1])
    finally:
        viva.liberar()
        otra.liberar()
    assert ip.patata_viva(nombre_evento=ne) is False             # se fue: el evento ya no existe
    tercera = ip.InstanciaPatata(mutex=MutexNombrado(nm), nombre_evento=ne)
    try:
        assert tercera.adquirir() is True
    finally:
        tercera.liberar()


def test_no_importa_qt():
    import subprocess
    raiz = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-c", "import sys, servicios.instancia_patata; "
                        "print(any(m.startswith('PyQt') for m in sys.modules))"],
                       cwd=str(raiz), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "False", r.stderr


# ── patata.main ────────────────────────────────────────────────────────────────

class InstanciaFalsa:
    def __init__(self, duena=True, viva=True):
        self.duena, self.viva = duena, viva
        self.escuchando, self.liberada, self.pedidos = None, 0, 0

    def adquirir(self):
        return self.duena

    def pedir_mostrar(self):
        self.pedidos += 1
        return self.viva

    def escuchar(self, fn):
        self.escuchando = fn
        return True

    def liberar(self):
        self.liberada += 1


def test_patata_main_con_otra_patata_viva_no_abre_otra(monkeypatch, capsys):
    import patata
    creadas, esperas = [], []
    monkeypatch.setattr(patata, "Patata", lambda **k: creadas.append(k))
    inst = InstanciaFalsa(duena=False)
    assert patata.main([], instancia=inst, esperar=esperas.append) == 0
    assert creadas == [] and inst.pedidos == 1 and esperas == [patata.ESPERA_YA_ABIERTA_S]
    salida = capsys.readouterr().out
    assert patata.TXT_YA_ABIERTA in salida and "al frente" in salida
    # la del arranque con Windows (consola minimizada) se va sin esperar
    monkeypatch.setattr(patata, "arranque_con_windows", lambda **k: None)
    assert patata.main(["--autoinicio"], instancia=InstanciaFalsa(duena=False), esperar=esperas.append) == 0
    assert esperas == [patata.ESPERA_YA_ABIERTA_S] and creadas == []


def test_patata_main_dueña_escucha_y_suelta_al_salir(monkeypatch):
    import patata
    traidas = []

    class P:
        def __init__(self, color=True, con_windows=False):
            pass

        def traer_al_frente(self):
            traidas.append(1)

        def correr(self):
            return 0
    monkeypatch.setattr(patata, "Patata", P)
    inst = InstanciaFalsa()
    assert patata.main([], instancia=inst) == 0
    assert inst.liberada == 1 and callable(inst.escuchando)
    inst.escuchando()
    assert traidas == [1]


def test_patata_trae_su_consola_o_parpadea_y_lo_dice(monkeypatch):
    import patata
    avisos, parpadeos = [], []
    p = patata.Patata.__new__(patata.Patata)
    p.c = {k: "" for k in ("cyan", "yellow", "reset", "dim", "bold")}
    p.consola = type("C", (), {"aviso": lambda self, t: avisos.append(t),
                               "parpadear": lambda self, **k: parpadeos.append(k)})()
    monkeypatch.setattr(p, "_en_estilo", lambda cara: cara, raising=False)
    monkeypatch.setattr(ip, "traer_consola_al_frente", lambda api=None: False)
    p.traer_al_frente()
    assert parpadeos and "Sigo aquí" in avisos[-1]
    monkeypatch.setattr(ip, "traer_consola_al_frente", lambda api=None: True)
    p.traer_al_frente()
    assert len(parpadeos) == 1 and len(avisos) == 2


# ── main.py en modo patata ─────────────────────────────────────────────────────

def test_main_en_modo_patata_no_abre_otra_terminal_si_ya_hay_una(monkeypatch):
    import subprocess
    import main
    lanzadas, pedidos = [], []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: lanzadas.append(a))
    monkeypatch.setattr(ip, "patata_viva", lambda *a, **k: True)
    monkeypatch.setattr(ip, "pedir_mostrar", lambda *a, **k: pedidos.append(1) or True)
    assert main._lanzar_patata() is True and lanzadas == [] and pedidos == [1]
    assert main._lanzar_patata(autoinicio=True) is True and lanzadas == [] and pedidos == [1]   # callada
    monkeypatch.setattr(ip, "patata_viva", lambda *a, **k: False)
    assert main._lanzar_patata() is True and len(lanzadas) == 1
