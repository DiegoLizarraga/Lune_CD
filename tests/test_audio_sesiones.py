"""
Tests de servicios/audio_sesiones: el medidor de pico por sesión de audio.

Con un backend COM FALSO (misma forma que ComAudio): varias salidas, sonidos
del sistema, pid 0, sesiones que mueren a mitad, nombre desde el identificador
y el medidor en caché para el bucle rápido. Nada de COM real.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import audio_sesiones as A  # noqa: E402
from servicios.audio_sesiones import MedidorSesiones, Sesion, exe_de_identificador  # noqa: E402

DEV = "{0.0.0.00000000}.{89da6f9f-d36d-4895-986a-46e47b9d4cb0}"


def ident(ruta_exe, pid=None):
    base = f"{DEV}|{ruta_exe}%b{{00000000-0000-0000-0000-000000000000}}"
    return base if pid is None else f"{base}|1%b{pid}"


class Medidor:
    def __init__(self, pico):
        self.valor = pico
        self.muerto = False
        self.lecturas = 0

    def GetPeakValue(self):
        self.lecturas += 1
        if self.muerto:
            raise OSError("AUDCLNT_E_DEVICE_INVALIDATED")
        return self.valor


class Control:
    def __init__(self, pid, ruta="", pico=0.0, sistema=False, muere_en_info=False, muere_en_medidor=False):
        self.pid, self.ruta, self.sistema = pid, ruta, sistema
        self.muere_en_info, self.muere_en_medidor = muere_en_info, muere_en_medidor
        self.med = Medidor(pico)


class ComFalso:
    """Backend con la forma de ComAudio: endpoints → sesiones → info/medidor/pico."""

    def __init__(self, salidas):
        self.salidas = salidas            # {id_endpoint: [Control…]}
        self.iniciado = False
        self.finalizado = False
        self.hilo_init = None
        self.llamadas = []

    def inicializar(self):
        self.iniciado = True
        self.hilo_init = threading.get_ident()

    def finalizar(self):
        self.finalizado = True

    def endpoints(self):
        self.llamadas.append("endpoints")
        return [(k, k) for k in self.salidas]

    def sesiones(self, dispositivo):
        return list(self.salidas[dispositivo])

    def info(self, c):
        if c.muere_en_info:
            raise OSError("el proceso ya no existe")
        inst = ident(c.ruta, c.pid) if c.ruta else f"{DEV}|#%b{{x}}|1%b#"
        return c.pid, c.sistema, ident(c.ruta) if c.ruta else f"{DEV}|#%b{{x}}", inst

    def medidor(self, c):
        if c.muere_en_medidor:
            raise OSError("sesión caducada")
        return c.med

    def pico(self, med):
        return med.GetPeakValue()


SPOTIFY = r"\Device\HarddiskVolume3\Users\x\AppData\Roaming\Spotify\Spotify.exe"
FIREFOX = r"\Device\HarddiskVolume3\Program Files\Mozilla Firefox\firefox.exe"
VLC = r"\Device\HarddiskVolume3\Program Files\VideoLAN\VLC\vlc.EXE"


def test_exe_desde_el_identificador_sin_abrir_el_proceso():
    assert exe_de_identificador(ident(SPOTIFY)) == "Spotify"
    assert exe_de_identificador(ident(SPOTIFY, 1234)) == "Spotify"
    assert exe_de_identificador(ident(VLC)) == "vlc"
    assert exe_de_identificador(f"{DEV}|#%b{{A9EF3FD9-4240-455E-A4D5-F2B3301887B2}}") == ""
    assert exe_de_identificador("") == ""
    assert exe_de_identificador(f"{DEV}|\\Device\\algo\\sin_extension%b{{0}}") == ""
    assert exe_de_identificador("Spotify.exe") == "Spotify"


def test_varios_endpoints_saltando_sistema_pid0_y_sesiones_que_mueren():
    com = ComFalso({
        "altavoces": [Control(0, "", 0.9, sistema=True),                  # sonidos del sistema
                      Control(1968, "", 0.9, sistema=True),               # sistema con pid
                      Control(100, SPOTIFY, 0.5),
                      Control(101, FIREFOX, 0.1, muere_en_info=True)],   # murió al preguntar
        "auriculares": [Control(0, SPOTIFY, 0.7),                         # pid 0
                        Control(200, VLC, 0.3),
                        Control(201, FIREFOX, 0.2, muere_en_medidor=True)],
    })
    nombres = []
    m = MedidorSesiones(com=com, nombre_pid=lambda pid: nombres.append(pid) or "x")
    m.abrir()
    ss = m.sesiones()
    assert {(s.pid, s.exe, round(s.pico, 2)) for s in ss} == {(100, "Spotify", 0.5), (200, "vlc", 0.3)}
    assert all(isinstance(s, Sesion) and s.clave for s in ss)
    assert nombres == []                     # el nombre sale del identificador: ni psutil
    m.cerrar()
    assert com.finalizado


def test_pico_con_el_medidor_en_cache_y_sesion_que_muere_despues():
    c = Control(100, SPOTIFY, 0.4)
    com = ComFalso({"a": [c]})
    m = MedidorSesiones(com=com)
    m.abrir()
    (s,) = m.sesiones()
    c.med.valor = 0.8
    assert m.pico(s.clave) == pytest.approx(0.8)
    assert com.llamadas == ["endpoints"]     # el bucle rápido no vuelve a enumerar
    c.med.muerto = True
    assert m.pico(s.clave) is None           # murió: None y fuera de la caché
    c.med.muerto = False
    assert m.pico(s.clave) is None
    assert m.pico("no-existe") is None


def test_pico_acotado_a_0_1():
    com = ComFalso({"a": [Control(100, SPOTIFY, 1.7), Control(101, VLC, -0.2)]})
    m = MedidorSesiones(com=com)
    m.abrir()
    assert sorted(s.pico for s in m.sesiones()) == [0.0, 1.0]


def test_nombre_por_psutil_solo_por_encima_del_umbral():
    com = ComFalso({"a": [Control(300, "", 0.6), Control(301, "", 0.01)]})
    # sin exe en el identificador (el falso da uno de sistema, pero no marcado como tal)
    pedidos = []
    m = MedidorSesiones(com=com, nombre_pid=lambda pid: pedidos.append(pid) or f"app{pid}")
    m.abrir()
    ss = {s.pid: s.exe for s in m.sesiones()}
    assert ss == {300: "", 301: ""}          # por defecto nunca pregunta
    ss = {s.pid: s.exe for s in m.sesiones(umbral_nombre=0.2)}
    assert ss == {300: "app300", 301: ""} and pedidos == [300]
    m.sesiones(umbral_nombre=0.2)
    assert pedidos == [300]                  # en caché


def test_sin_abrir_o_desde_otro_hilo_no_toca_com():
    com = ComFalso({"a": [Control(100, SPOTIFY, 0.4)]})
    m = MedidorSesiones(com=com)
    assert m.sesiones() == [] and com.llamadas == []
    caja = {}

    def abrir():
        m.abrir()
        caja["ss"] = m.sesiones()
    h = threading.Thread(target=abrir)
    h.start(); h.join()
    assert com.hilo_init == h.ident and len(caja["ss"]) == 1
    assert m.sesiones() == []                # COM es del hilo que lo abrió
    assert m.pico(caja["ss"][0].clave) is None


def test_abrir_sin_comtypes_lanza_y_no_se_queda_abierto():
    class Roto:
        def inicializar(self):
            raise ImportError("No module named 'comtypes'")
    m = MedidorSesiones(com=Roto())
    with pytest.raises(ImportError):
        m.abrir()
    assert not m.abierto and m.sesiones() == []


def test_enumerar_que_falla_devuelve_lista_vacia():
    com = ComFalso({"a": []})
    com.endpoints = lambda: (_ for _ in ()).throw(OSError("sin audio"))
    m = MedidorSesiones(com=com)
    m.abrir()
    assert m.sesiones() == []


def test_interfaces_com_en_el_orden_de_la_vtable():
    pytest.importorskip("comtypes")
    i = A._interfaces()
    nombres = lambda cls: [m[1] for m in cls._methods_]          # noqa: E731
    assert nombres(i["IMMDeviceEnumerator"]) == [
        "EnumAudioEndpoints", "GetDefaultAudioEndpoint", "GetDevice",
        "RegisterEndpointNotificationCallback", "UnregisterEndpointNotificationCallback"]
    assert nombres(i["IMMDevice"]) == ["Activate", "OpenPropertyStore", "GetId", "GetState"]
    assert nombres(i["IAudioSessionManager2"]) == [
        "GetSessionEnumerator", "RegisterSessionNotification", "UnregisterSessionNotification",
        "RegisterDuckNotification", "UnregisterDuckNotification"]
    assert i["IAudioSessionManager2"].__mro__[1] is i["IAudioSessionManager"]
    assert len(i["IAudioSessionControl"]._methods_) == 9
    assert nombres(i["IAudioSessionControl2"]) == [
        "GetSessionIdentifier", "GetSessionInstanceIdentifier", "GetProcessId",
        "IsSystemSoundsSession", "SetDuckingPreference"]
    assert nombres(i["IAudioMeterInformation"])[0] == "GetPeakValue"
    assert str(i["IAudioSessionManager2"]._iid_) == "{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"
    assert str(i["IAudioMeterInformation"]._iid_) == "{C02216F6-8C67-4B5B-9D00-D008E73E0064}"


def test_finalizar_no_llama_al_recolector(monkeypatch):
    # El hilo del detector no puede hacer gc.collect(): destruiría fuera del hilo de
    # Qt objetos de Qt que estén en ciclos. Los punteros COM se sueltan por recuento.
    import gc
    llamadas = []
    monkeypatch.setattr(gc, "collect", lambda *a, **k: llamadas.append(a) or 0)

    class Ole:
        def __init__(self):
            self.un = 0

        def CoUninitialize(self):                                  # noqa: N802 (Win32)
            self.un += 1
    com = A.ComAudio()
    com._enum, com._co, com._ole32 = object(), True, Ole()
    ole = com._ole32
    com.finalizar()
    assert llamadas == [] and com._enum is None and ole.un == 1
    com.finalizar()
    assert ole.un == 1                                             # equilibrado: una vez


def test_preparar_comtypes_importa_en_el_hilo_que_llama(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "win32")
    hilos = []
    assert A.preparar_comtypes(lambda n: hilos.append((n, threading.get_ident()))) is True
    assert hilos == [("comtypes", threading.get_ident())]

    def sin_comtypes(n):
        raise ImportError("No module named 'comtypes'")
    assert A.preparar_comtypes(sin_comtypes) is False                # sin comtypes: nada, sin lanzar
    monkeypatch.setattr(A.sys, "platform", "linux")
    assert A.preparar_comtypes(lambda n: hilos.append(n)) is False and len(hilos) == 1


def test_el_detector_importa_comtypes_al_construirse_en_su_hilo(monkeypatch):
    # comtypes se importa por primera vez en el hilo que construye el detector (el de
    # Qt o el de patata), no en el hilo lune-musica: su CoInitialize y el
    # CoUninitialize de atexit quedan en el hilo principal.
    from servicios.musica_detector import DetectorMusica
    hilos = []
    monkeypatch.setattr(A, "preparar_comtypes", lambda: hilos.append(threading.get_ident()) or True)
    DetectorMusica({"baile": {}})
    assert hilos == [threading.get_ident()]
    DetectorMusica({"baile": {}}, medidor=object())                # medidor inyectado: no hace falta
    assert len(hilos) == 1
