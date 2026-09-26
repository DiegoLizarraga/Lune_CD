"""
Tests de servicios/win_entrada: inactividad, detector de entrada nueva y mando.

Todo con una API falsa o con DLLs falsas que rellenan las estructuras de
ctypes: sin pantalla, sin teclado y sin mando de verdad. El detector NO debe
leer teclas: solo la marca de GetLastInputInfo, el cursor y el botón izquierdo.
"""
import ctypes
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import win_entrada as W  # noqa: E402
from servicios.win_entrada import (  # noqa: E402
    ApiEntradaNula, ApiEntradaWin32, DetectorEntrada, EstadoMando, LectorMando,
    mando_en_reposo, ms_desde, segundos_inactivo,
)

RAIZ = Path(__file__).resolve().parent.parent
REPOSO = EstadoMando(1, 0, 0, 0, 0, 0, 0, 0)


class ApiFalsa:
    """Una sesión de Windows de mentira que el test va moviendo a mano."""

    def __init__(self, tick=10_000, ultima=10_000, pos=(100, 100), clic=False,
                 xinput=True, mandos=None):
        self.t = tick
        self.ultima = ultima
        self.pos = pos
        self.clic = clic
        self.xinput = xinput
        self.mandos = dict(mandos or {})       # indice → EstadoMando
        self.consultas_mando = []

    def tick(self):
        return self.t

    def ultima_entrada(self):
        return self.ultima

    def cursor(self):
        return self.pos

    def boton_izquierdo(self):
        return self.clic

    def hay_xinput(self):
        return self.xinput

    def estado_mando(self, i):
        self.consultas_mando.append(i)
        return self.mandos.get(i)


# ── Inactividad ───────────────────────────────────────────────────────────────

def test_segundos_inactivo_basico():
    assert segundos_inactivo(ApiFalsa(tick=10_000, ultima=4_000)) == pytest.approx(6.0)


def test_segundos_inactivo_sobrevive_a_la_vuelta_de_gettickcount():
    """GetTickCount es de 32 bits y vuelve a 0 cada 49,7 días."""
    api = ApiFalsa(tick=5, ultima=0xFFFFFFF0)
    assert segundos_inactivo(api) == pytest.approx(0.021)
    assert ms_desde(5, 0xFFFFFFF0) == 21
    assert ms_desde(0x0000_0100, 0x0000_0100) == 0


def test_segundos_inactivo_sin_dato_es_cero():
    assert segundos_inactivo(ApiFalsa(ultima=None)) == 0.0
    assert segundos_inactivo(ApiEntradaNula()) == 0.0


def test_segundos_inactivo_nunca_lanza():
    class Rota(ApiFalsa):
        def ultima_entrada(self):
            raise OSError("sin sesión")
    assert segundos_inactivo(Rota()) == 0.0


# ── DetectorEntrada ───────────────────────────────────────────────────────────

def test_la_primera_lectura_solo_toma_la_linea_base():
    api = ApiFalsa(clic=True)
    d = DetectorEntrada(api)
    assert d.poll() is False            # el clic que ya estaba no cuenta
    assert d.poll() is False            # nada cambió


def test_tecla_sin_mover_el_cursor_es_entrada():
    api = ApiFalsa()
    d = DetectorEntrada(api)
    d.poll()
    api.ultima += 50                     # algo tocó el PC; el cursor quieto
    assert d.poll() is True
    assert d.ultimo_motivo == "entrada"
    assert d.poll() is False             # la misma marca no se cuenta dos veces


def test_mover_el_raton_no_es_entrada():
    api = ApiFalsa()
    d = DetectorEntrada(api)
    d.poll()
    api.ultima += 16
    api.pos = (140, 90)
    assert d.poll() is False
    api.ultima += 16
    api.pos = (180, 80)
    assert d.poll() is False
    # Y en cuanto el cursor se para y llega otra entrada, sí cuenta.
    api.ultima += 30
    assert d.poll() is True


def test_flanco_del_clic_izquierdo_y_clic_mantenido():
    api = ApiFalsa()
    d = DetectorEntrada(api)
    d.poll()
    api.clic = True
    api.pos = (300, 300)                 # aunque se mueva a la vez
    api.ultima += 10
    assert d.poll() is True
    assert d.ultimo_motivo == "clic"
    assert d.poll() is False             # mantenido: sin flanco nuevo
    api.clic = False
    assert d.poll() is False             # soltar no es entrada nueva
    api.clic = True
    assert d.poll() is True


def test_reiniciar_vuelve_a_tomar_linea_base():
    api = ApiFalsa()
    d = DetectorEntrada(api)
    d.poll()
    api.ultima += 5
    d.reiniciar()
    assert d.poll() is False             # la entrada previa al reinicio no cuenta
    api.ultima += 5
    assert d.poll() is True


def test_detector_sin_datos_no_inventa_entrada():
    api = ApiFalsa(ultima=None)
    d = DetectorEntrada(api)
    d.poll()
    assert d.poll() is False


def test_detector_nunca_lanza():
    class Rota(ApiFalsa):
        def cursor(self):
            raise OSError("escritorio seguro")
    assert DetectorEntrada(Rota()).poll() is False


def test_detector_con_mando_cuenta_el_flanco_del_mando():
    api = ApiFalsa(mandos={0: REPOSO})
    d = DetectorEntrada(api, con_mando=True, lector_mando=LectorMando(api, reloj=lambda: 0.0))
    d.poll()
    api.mandos[0] = EstadoMando(2, 0x1000, 0, 0, 0, 0, 0, 0)     # botón A
    assert d.poll() is True
    assert d.ultimo_motivo == "mando"
    assert d.poll() is False             # sigue pulsado: sin flanco
    api.mandos[0] = REPOSO
    assert d.poll() is False


def test_detector_sin_mando_no_consulta_xinput():
    api = ApiFalsa(mandos={0: EstadoMando(2, 0x1000, 0, 0, 0, 0, 0, 0)})
    d = DetectorEntrada(api)
    d.poll()
    d.poll()
    assert api.consultas_mando == []


# ── Mando ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("estado, en_reposo", [
    (REPOSO, True),
    (EstadoMando(9, 0, 0, 0, 7000, -7000, 8000, -8000), True),     # dentro de las zonas muertas
    (EstadoMando(9, 0, 30, 30, 0, 0, 0, 0), True),                 # gatillos apenas rozados
    (EstadoMando(9, 0x0010, 0, 0, 0, 0, 0, 0), False),              # START
    (EstadoMando(9, 0, 31, 0, 0, 0, 0, 0), False),
    (EstadoMando(9, 0, 0, 0, 7850, 0, 0, 0), False),
    (EstadoMando(9, 0, 0, 0, 0, 0, 0, -8690), False),
])
def test_reposo_del_mando(estado, en_reposo):
    assert mando_en_reposo(estado) is en_reposo


def test_mando_activo_sin_xinput_es_false():
    assert LectorMando(ApiFalsa(xinput=False)).activo() is False
    assert LectorMando(ApiEntradaNula()).activo() is False


def test_mando_activo_con_stick_movido():
    api = ApiFalsa(mandos={2: EstadoMando(5, 0, 0, 0, 0, 32000, 0, 0)})
    assert LectorMando(api, reloj=lambda: 0.0).activo() is True


def test_mando_quieto_con_paquetes_nuevos_no_cuenta():
    """Un stick con deriva cambia el nº de paquete sin parar: eso no es jugar."""
    api = ApiFalsa(mandos={0: REPOSO})
    lector = LectorMando(api, reloj=lambda: 0.0)
    assert lector.activo() is False
    api.mandos[0] = REPOSO._replace(paquete=99, lx=300)
    assert lector.activo() is False


def test_huecos_vacios_se_consultan_con_espera():
    reloj = [0.0]
    api = ApiFalsa(mandos={0: REPOSO})
    lector = LectorMando(api, reloj=lambda: reloj[0])
    lector.activo()
    assert sorted(api.consultas_mando) == [0, 1, 2, 3]
    api.consultas_mando.clear()
    reloj[0] = 1.0
    lector.activo()
    assert api.consultas_mando == [0]                # 1..3 siguen en espera
    api.consultas_mando.clear()
    reloj[0] = 1.0 + W.ESPERA_DESCONECTADO_S
    lector.activo()
    assert sorted(api.consultas_mando) == [0, 1, 2, 3]


def test_mando_activo_de_modulo_usa_la_api_que_se_le_pasa():
    assert W.mando_activo(ApiFalsa(mandos={})) is False
    assert W.mando_activo(ApiFalsa(mandos={1: EstadoMando(1, 0x2000, 0, 0, 0, 0, 0, 0)})) is True


# ── ApiEntradaWin32 con DLLs falsas (marshalling de ctypes sin Windows) ──────

class _Dll:
    """Objeto con atributos de función; admite argtypes/restype como una DLL."""


def _fn(impl):
    def f(*args):
        return impl(*args)
    return f


def _dlls(ultima=1234, tick=5000, pos=(7, -3), estado_boton=0, llamadas=None, xinput=None):
    llamadas = llamadas if llamadas is not None else []
    user32, kernel32 = _Dll(), _Dll()

    def get_last_input_info(ref):
        assert ref._obj.cbSize == ctypes.sizeof(W.LASTINPUTINFO)
        ref._obj.dwTime = ultima
        return 1

    def get_cursor_pos(ref):
        ref._obj.x, ref._obj.y = pos
        return 1

    def get_async_key_state(vk):
        llamadas.append(vk)
        return estado_boton

    user32.GetLastInputInfo = _fn(get_last_input_info)
    user32.GetCursorPos = _fn(get_cursor_pos)
    user32.GetAsyncKeyState = _fn(get_async_key_state)
    kernel32.GetTickCount = _fn(lambda: tick)
    return ApiEntradaWin32(user32=user32, kernel32=kernel32, xinput=xinput), llamadas


def test_api_win32_rellena_las_estructuras():
    api, _ = _dlls(ultima=1234, tick=5000, pos=(7, -3))
    assert api.ultima_entrada() == 1234
    assert api.tick() == 5000
    assert api.cursor() == (7, -3)
    assert segundos_inactivo(api) == pytest.approx(3.766)


def test_api_win32_boton_izquierdo_lee_solo_vk_lbutton():
    api, llamadas = _dlls(estado_boton=-32768)            # bit alto: pulsado
    assert api.boton_izquierdo() is True
    api2, llamadas2 = _dlls(estado_boton=1)                # solo el bit de «se pulsó antes»
    assert api2.boton_izquierdo() is False
    assert set(llamadas) | set(llamadas2) == {0x01}


def test_api_win32_fallos_devuelven_none():
    user32, kernel32 = _Dll(), _Dll()
    user32.GetLastInputInfo = _fn(lambda ref: 0)
    user32.GetCursorPos = _fn(lambda ref: 0)
    user32.GetAsyncKeyState = _fn(lambda vk: 0)
    kernel32.GetTickCount = _fn(lambda: 0)
    api = ApiEntradaWin32(user32=user32, kernel32=kernel32, xinput=None)
    assert api.ultima_entrada() is None
    assert api.cursor() is None
    assert api.hay_xinput() is False
    assert api.estado_mando(0) is None


def test_api_win32_lee_xinput():
    xinput = _Dll()

    def get_state(indice, ref):
        if indice != 1:
            return W.ERROR_DEVICE_NOT_CONNECTED
        st = ref._obj
        st.dwPacketNumber = 77
        st.Gamepad.wButtons = 0x1000
        st.Gamepad.bLeftTrigger = 200
        st.Gamepad.sThumbLX = -32768
        return W.ERROR_SUCCESS

    xinput.XInputGetState = _fn(get_state)
    api, _ = _dlls(xinput=xinput)
    assert api.hay_xinput() is True
    assert api.estado_mando(0) is None
    est = api.estado_mando(1)
    assert est == EstadoMando(77, 0x1000, 200, 0, -32768, 0, 0, 0)
    assert LectorMando(api, reloj=lambda: 0.0).activo() is True


# ── pantalla_requerida (powrprof falso) ──────────────────────────────────────

def _powrprof(estado=0, status=0, llamadas=None):
    llamadas = llamadas if llamadas is not None else []
    dll = _Dll()

    def call_nt(nivel, entrada, tam_entrada, salida, tam_salida):
        llamadas.append((nivel, entrada, tam_entrada, tam_salida))
        salida._obj.value = estado
        return status

    dll.CallNtPowerInformation = _fn(call_nt)
    return dll, llamadas


def test_pantalla_requerida_lee_es_display_required():
    dll, llamadas = _powrprof(estado=W.ES_DISPLAY_REQUIRED | W.ES_SYSTEM_REQUIRED)
    api, _ = _dlls()
    api = ApiEntradaWin32(user32=api._u, kernel32=api._k, xinput=None, powrprof=dll)
    assert api.estado_ejecucion() == 3
    assert W.pantalla_requerida(api) is True
    # Nivel SystemExecutionState, sin búfer de entrada y un ULONG de salida.
    assert llamadas[0] == (W.SYSTEM_EXECUTION_STATE, None, 0, ctypes.sizeof(ctypes.c_ulong))


def test_pantalla_requerida_solo_el_sistema_no_cuenta():
    dll, _ = _powrprof(estado=W.ES_SYSTEM_REQUIRED)       # descargando algo: el PC despierto, la pantalla no
    base, _ = _dlls()
    api = ApiEntradaWin32(user32=base._u, kernel32=base._k, xinput=None, powrprof=dll)
    assert W.pantalla_requerida(api) is False


def test_pantalla_requerida_con_error_o_sin_dll_es_false():
    dll, _ = _powrprof(estado=W.ES_DISPLAY_REQUIRED, status=-1073741811)   # STATUS_INVALID_PARAMETER
    base, _ = _dlls()
    api = ApiEntradaWin32(user32=base._u, kernel32=base._k, xinput=None, powrprof=dll)
    assert api.estado_ejecucion() is None
    assert W.pantalla_requerida(api) is False
    sin = ApiEntradaWin32(user32=base._u, kernel32=base._k, xinput=None, powrprof=None)
    assert sin.estado_ejecucion() is None
    assert W.pantalla_requerida(sin) is False


def test_pantalla_requerida_con_apis_sin_el_metodo_o_que_fallan():
    assert W.pantalla_requerida(ApiFalsa()) is False          # API sin estado_ejecucion
    assert W.pantalla_requerida(ApiEntradaNula()) is False

    class Rota:
        def estado_ejecucion(self):
            raise OSError("roto")
    assert W.pantalla_requerida(Rota()) is False


# ── Anticheat: el módulo no puede parecer un keylogger ───────────────────────

def test_el_modulo_no_recorre_teclas_ni_usa_ganchos():
    src = (RAIZ / "servicios" / "win_entrada.py").read_text(encoding="utf-8")
    # Cada llamada a GetAsyncKeyState es con VK_LBUTTON, nunca con una variable de bucle.
    llamadas = re.findall(r"GetAsyncKeyState\(([^)]*)\)", src)
    assert llamadas, "se esperaba al menos la lectura del botón izquierdo"
    assert all(arg.strip() == "VK_LBUTTON" for arg in llamadas), llamadas
    for prohibido in ("import keyboard", "pynput", "SetWindowsHook", "GetKeyboardState",
                      "WriteProcessMemory", "CreateRemoteThread"):
        assert prohibido not in src


# ── En Windows de verdad (humo: que no falle) ────────────────────────────────

@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_en_windows_real_no_falla():
    W._api_defecto = None
    s = segundos_inactivo()
    assert isinstance(s, float) and s >= 0.0
    d = DetectorEntrada(con_mando=True)
    assert d.poll() is False
    assert isinstance(d.poll(), bool)
    assert isinstance(W.mando_activo(), bool)
    assert isinstance(W.pantalla_requerida(), bool)
