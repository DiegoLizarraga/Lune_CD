"""
Tests del IPC con Discord (servicios/discord_ipc.py) contra un Discord falso en memoria.

`DiscordFalso` hace de extremo servidor de `\\\\.\\pipe\\discord-ipc-N`: entiende las
tramas que Lune escribe (cabecera <II + JSON) y contesta como el cliente de
Discord (READY, respuesta a SET_ACTIVITY con el mismo nonce, ERROR, CLOSE 4000,
PING). Nada toca una tubería de verdad.
"""
import ctypes
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from servicios import discord_ipc as di  # noqa: E402
from discord_falso import ID, DiscordFalso, Reloj  # noqa: E402


def _cliente(falso, n_ok=0, reloj=None, client_id=ID):
    reloj = reloj or Reloj()
    intentos = []

    def abrir(n):
        intentos.append(n)
        return falso if n == n_ok else None

    c = di.ClienteIPC(client_id, abrir=abrir, reloj=reloj, dormir=reloj.dormir)
    return c, intentos


# ── Tramas ─────────────────────────────────────────────────────────────────────

def test_empaquetar_pone_cabecera_little_endian_y_json_utf8():
    b = di.empaquetar(di.OP_FRAME, {"state": "Bailando ♪", "n": 1})
    op, largo = struct.unpack("<II", b[:8])
    assert op == 1
    assert largo == len(b) - 8
    assert json.loads(b[8:].decode("utf-8")) == {"state": "Bailando ♪", "n": 1}


def test_desempaquetar_junta_lecturas_partidas():
    datos = di.empaquetar(1, {"a": "ñandú"}) + di.empaquetar(3, {"b": 2})
    resto, vistas = b"", []
    for i in range(len(datos)):                     # llega byte a byte
        tramas, resto = di.desempaquetar(resto + datos[i:i + 1])
        vistas.extend(tramas)
    assert vistas == [(1, {"a": "ñandú"}), (3, {"b": 2})]
    assert resto == b""


def test_desempaquetar_devuelve_el_resto_incompleto():
    datos = di.empaquetar(1, {"x": 1})
    tramas, resto = di.desempaquetar(datos + datos[:5])
    assert tramas == [(1, {"x": 1})]
    assert resto == datos[:5]


def test_una_trama_imposible_es_un_error():
    with pytest.raises(di.ErrorTrama):
        di.desempaquetar(struct.pack("<II", 1, di.MAX_TRAMA + 1) + b"x")
    with pytest.raises(di.ErrorTrama):
        di.empaquetar(1, {"x": "a" * (di.MAX_TRAMA + 10)})


def test_nombre_de_la_tuberia():
    assert di.nombre_tuberia(3) == "\\\\.\\pipe\\discord-ipc-3"


# ── Conexión ───────────────────────────────────────────────────────────────────

def test_handshake_con_client_id_y_ready_con_el_usuario():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    r = c.conectar()
    assert r["ok"] is True and r["usuario"] == "Diego"
    assert c.conectado is True
    assert falso.recibidas[0] == (di.OP_HANDSHAKE, {"v": 1, "client_id": ID})


def test_tuberia_0_ocupada_prueba_las_siguientes():
    falso = DiscordFalso()
    c, intentos = _cliente(falso, n_ok=2)
    assert c.conectar()["ok"] is True
    assert intentos == [0, 1, 2]
    assert c.numero == 2


def test_sin_discord_prueba_las_diez_y_falla_sin_codigo():
    c = di.ClienteIPC(ID, abrir=lambda n: None)
    r = c.conectar()
    assert r["ok"] is False and r["codigo"] == 0
    assert r["error"] == di.TXT_SIN_DISCORD


def test_client_id_no_valido_no_abre_ninguna_tuberia():
    abiertas = []
    for malo in ("", "abc", "123", "1" * 25, "12345678901234567x"):
        c = di.ClienteIPC(malo, abrir=lambda n: abiertas.append(n))
        r = c.conectar()
        assert r["ok"] is False and r["codigo"] == di.CODIGO_ID_NO_VALIDO
    assert abiertas == []


def test_close_4000_en_el_handshake():
    falso = DiscordFalso(cierre_handshake=4000)
    c, _ = _cliente(falso)
    r = c.conectar()
    assert r["ok"] is False and r["codigo"] == 4000
    assert c.conectado is False and falso.cerrada is True


def test_sin_ready_se_rinde_al_timeout_sin_esperar_de_verdad():
    falso = DiscordFalso(ready=False)
    reloj = Reloj()
    c, _ = _cliente(falso, reloj=reloj)
    r = c.conectar(timeout_s=1.0)
    assert r["ok"] is False and r["error"] == di.TXT_NO_RESPONDE
    assert 1.0 <= reloj.t < 1.2
    assert falso.cerrada is True


def test_conectar_se_puede_cancelar():
    falso = DiscordFalso(ready=False)
    c, _ = _cliente(falso)
    r = c.conectar(timeout_s=5.0, cancelar=lambda: True)
    assert r["ok"] is False and falso.cerrada is True


def test_lecturas_partidas_en_la_tuberia():
    falso = DiscordFalso(trozo=3)
    c, _ = _cliente(falso)
    assert c.conectar()["ok"] is True
    assert c.set_activity({"state": "Hablando"}, 77)["ok"] is True


# ── Actividad ──────────────────────────────────────────────────────────────────

def test_set_activity_lleva_pid_y_un_nonce_distinto_cada_vez():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    assert c.set_activity({"details": "Lune CD · Ventana", "state": "Charlando"}, 1234)["ok"] is True
    assert c.set_activity(None, 1234)["ok"] is True
    ordenes = falso.ordenes("SET_ACTIVITY")
    assert [o["args"]["pid"] for o in ordenes] == [1234, 1234]
    assert ordenes[0]["args"]["activity"] == {"details": "Lune CD · Ventana", "state": "Charlando"}
    assert ordenes[1]["args"]["activity"] is None
    nonces = [o["nonce"] for o in ordenes]
    assert all(isinstance(n, str) and n for n in nonces) and nonces[0] != nonces[1]


def test_evt_error_de_discord():
    falso = DiscordFalso(error_actividad="child \"state\" fails")
    c, _ = _cliente(falso)
    c.conectar()
    r = c.set_activity({"state": "x"}, 1)
    assert r["ok"] is False and "fails" in r["error"]
    assert c.conectado is True                   # un error de actividad no corta la conexión


def test_set_activity_sin_respuesta_no_se_queda_colgado():
    falso = DiscordFalso(responde_actividad=False)
    reloj = Reloj()
    c, _ = _cliente(falso, reloj=reloj)
    c.conectar()
    t0 = reloj.t
    r = c.set_activity({"state": "x"}, 1, timeout_s=2.0)
    assert r["ok"] is False and r.get("sin_respuesta") is True
    assert reloj.t - t0 < 2.2


# ── Sesión ─────────────────────────────────────────────────────────────────────

def test_ping_se_contesta_con_pong_y_los_mismos_datos():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    falso.mandar(di.OP_PING, {"latido": 7})
    c.atender()
    assert (di.OP_PONG, {"latido": 7}) in falso.recibidas
    assert c.conectado is True


def test_close_en_mitad_de_la_sesion():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    falso.mandar(di.OP_CLOSE, {"code": 4000, "message": "Invalid Client ID"})
    c.atender()
    assert c.conectado is False and c.codigo_cierre == 4000
    assert falso.cerrada is True


def test_discord_se_cierra_y_la_tuberia_se_rompe():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    falso.rota = True
    c.atender()
    assert c.conectado is False
    assert c.set_activity({"state": "x"}, 1)["ok"] is False


def test_cerrar_borra_la_actividad_y_manda_close():
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    c.set_activity({"state": "Hablando"}, 99)
    c.cerrar()
    ops = [op for op, _ in falso.recibidas]
    assert ops[-1] == di.OP_CLOSE
    ultima = falso.ordenes("SET_ACTIVITY")[-1]
    assert ultima["args"]["activity"] is None and ultima["args"]["pid"] == 99
    assert falso.cerrada is True and c.conectado is False
    c.cerrar()                                     # idempotente


# ── TuberiaWin32 con un kernel32 falso (sin tuberías reales) ──────────────────

class Kernel32Falso:
    def __init__(self, handle=1234, datos=b""):
        self.handle = handle
        self.datos = bytearray(datos)
        self.escrito = b""
        self.abiertas = []
        self.cerrados = []

    def CreateFileW(self, nombre, acceso, compartir, seg, disp, flags, plantilla):
        self.abiertas.append((nombre, acceso, disp))
        return self.handle

    def PeekNamedPipe(self, h, buf, n, leidos, total, resto):
        total._obj.value = len(self.datos)
        return 1

    def ReadFile(self, h, buf, n, leidos, sol):
        trozo = bytes(self.datos[:n])
        del self.datos[:n]
        ctypes.memmove(buf, trozo, len(trozo))
        leidos._obj.value = len(trozo)
        return 1

    def WriteFile(self, h, datos, n, escritos, sol):
        self.escrito += bytes(datos)[:n]
        escritos._obj.value = n
        return 1

    def CloseHandle(self, h):
        self.cerrados.append(h)
        return 1


def test_tuberia_win32_abre_lee_escribe_y_cierra_con_kernel32_falso():
    k = Kernel32Falso(datos=b"hola")
    t = di.TuberiaWin32.abrir(0, kernel32=k)
    assert t is not None
    nombre, acceso, disp = k.abiertas[0]
    assert nombre == di.nombre_tuberia(0)
    assert acceso == 0x80000000 | 0x40000000 and disp == 3
    assert t.disponibles() == 4
    assert t.leer(4) == b"hola"
    t.escribir(b"\x01\x02")
    assert k.escrito == b"\x01\x02"
    t.cerrar()
    t.cerrar()
    assert k.cerrados == [1234]
    with pytest.raises(OSError):
        t.disponibles()


def test_tuberia_win32_handle_invalido_es_none():
    assert di.TuberiaWin32.abrir(0, kernel32=Kernel32Falso(handle=ctypes.c_void_p(-1).value)) is None
    assert di.TuberiaWin32.abrir(0, kernel32=Kernel32Falso(handle=0)) is None


# ── Revisión 7-10: códigos imposibles y Discord que no lee ────────────────────

def test_un_codigo_infinito_de_discord_no_tumba_el_hilo():
    """SN2: `{"code": 1e400}` llega del JSON como infinito; int() lanzaba OverflowError
    fuera de atender() y set_activity() (el hilo de la presencia se caía)."""
    falso = DiscordFalso()
    c, _ = _cliente(falso)
    c.conectar()
    cuerpo = b'{"code":1e400,"message":"raro"}'
    falso.salida += struct.pack("<II", di.OP_CLOSE, len(cuerpo)) + cuerpo
    c.atender()
    assert c.conectado is False and c.codigo_cierre == 0
    # y en la respuesta de una actividad
    falso2 = DiscordFalso(responde_actividad=False)
    c2, _ = _cliente(falso2)
    c2.conectar()
    cuerpo = b'{"cmd":"SET_ACTIVITY","evt":"ERROR","nonce":"%s","data":{"code":1e400,"message":"x"}}'
    orig = falso2.escribir

    def escribir(b):
        orig(b)
        orden = falso2.ordenes("SET_ACTIVITY")
        if orden:
            txt = cuerpo % orden[-1]["nonce"].encode()
            falso2.salida += struct.pack("<II", di.OP_FRAME, len(txt)) + txt
    falso2.escribir = escribir
    r = c2.set_activity({"state": "x"}, 1)
    assert r["ok"] is False and r["codigo"] == 0 and "x" in r["error"]
    assert di._int(float("inf")) == 0 and di._int(float("nan")) == 0 and di._int("12") == 12


class Kernel32SinSitio(Kernel32Falso):
    """Discord no lee: la tubería sin espera nunca tiene sitio (WriteFile escribe 0)."""

    def __init__(self, sitio=65536, **kw):
        super().__init__(**kw)
        self.sitio = sitio
        self.modos = []
        self.intentos = 0

    def GetNamedPipeInfo(self, h, flags, salida, entrada, maximo):
        entrada._obj.value = self.sitio
        return 1

    def SetNamedPipeHandleState(self, h, modo, a, b):
        self.modos.append(modo._obj.value)
        return 1

    def WriteFile(self, h, datos, n, escritos, sol):
        self.intentos += 1
        escritos._obj.value = 0
        return 1


def test_escribir_se_rinde_si_discord_no_lee_sin_esperar_de_verdad():
    k = Kernel32SinSitio()
    t = di.TuberiaWin32.abrir(0, kernel32=k)
    assert t.sin_espera is True and k.modos == [0x1]            # PIPE_NOWAIT
    reloj = Reloj()
    t._reloj, t._dormir = reloj, reloj.dormir
    with pytest.raises(OSError):
        t.escribir(b"x" * 700, tope_s=1.0)
    assert 1.0 <= reloj.t < 1.1 and k.intentos > 10


def test_con_poco_sitio_en_discord_la_tuberia_sigue_bloqueante():
    k = Kernel32SinSitio(sitio=1024)
    t = di.TuberiaWin32.abrir(0, kernel32=k)
    assert t.sin_espera is False and k.modos == []
    with pytest.raises(OSError):                                   # como antes: 0 bytes = error
        t.escribir(b"x")
    assert k.intentos == 1


@pytest.mark.skipif(sys.platform != "win32", reason="tuberías con nombre de Windows")
def test_tuberia_real_discord_colgado_no_deja_el_hilo_parado():
    """Una tubería de verdad (propia, nombre al azar) cuyo servidor NUNCA lee, con los
    64 KB de libuv (el Discord de escritorio): antes WriteFile bloqueaba para siempre
    en cuanto se llenaba; ahora `escribir` lanza OSError al tope."""
    import threading
    import uuid
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k.CreateNamedPipeW.restype = wintypes.HANDLE
    k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                           ctypes.c_void_p]
    k.ReadFile.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    ruta = "\\\\.\\pipe\\lune-test-" + uuid.uuid4().hex
    srv = k.CreateNamedPipeW(ruta, 3, 0, 1, 65536, 65536, 0, None)     # dúplex, bytes, espera
    assert srv and srv != ctypes.c_void_p(-1).value
    t = None
    try:
        t = di.TuberiaWin32.abrir_ruta(ruta)
        assert t is not None and t.sin_espera is True
        trama = di.empaquetar(di.OP_FRAME, {"cmd": "SET_ACTIVITY", "relleno": "x" * 600})
        caja = {}

        def llenar():
            n = 0
            try:
                while n < 1000:
                    t.escribir(trama, tope_s=0.3)
                    n += 1
            except OSError as e:
                caja["error"] = e
            caja["n"] = n
        hilo = threading.Thread(target=llenar, daemon=True)
        hilo.start()
        hilo.join(10)
        assert not hilo.is_alive(), "escribir se quedó bloqueado con Discord sin leer"
        assert isinstance(caja.get("error"), OSError) and 50 < caja["n"] < 1000
        # el servidor lee y vuelve a haber sitio: la siguiente sale entera
        buf = ctypes.create_string_buffer(65536)
        leidos = wintypes.DWORD(0)
        assert k.ReadFile(srv, buf, 65536, ctypes.byref(leidos), None) and leidos.value > 0
        t.escribir(trama, tope_s=0.3)
    finally:
        if t is not None:
            t.cerrar()
        k.CloseHandle(srv)
