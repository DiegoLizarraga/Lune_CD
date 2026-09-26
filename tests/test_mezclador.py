"""
Tests de servicios/mezclador: suma de fuentes, recorte, bucle, velocidad,
posición, canales, cierre del stream tras 5 s de silencio, elección de
dispositivo por nombre aproximado y plan B con winsound.

Sin tarjeta de sonido: se inyecta un `sounddevice` falso cuyo OutputStream
guarda el callback, y el test «tira» de él como haría PortAudio. El reloj es
falso para probar el cierre por silencio sin esperar. winsound también es
falso (nunca suena nada de verdad). ffmpeg se simula; hay una prueba extra con
el ffmpeg de imageio-ffmpeg que se salta si no está instalado.
"""
import struct
import sys
import types
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import mezclador as M  # noqa: E402

SR = M.FRECUENCIA
SILENCIO = M.SILENCIO_CIERRE_S

DISPOSITIVOS = [
    {"name": "Microsoft Sound Mapper - Output", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
    {"name": "Speakers (2- Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
    {"name": "Auriculares (WH-1000XM4 Stereo", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
    {"name": "Microphone Array (Realtek)", "max_output_channels": 0, "hostapi": 0, "default_samplerate": 44100.0},
    {"name": "Primary Sound Driver", "max_output_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
    {"name": "Auriculares (WH-1000XM4 Stereo Hands-Free)", "max_output_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
    {"name": "Speakers (2- Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 2, "default_samplerate": 48000.0},
    {"name": "Auriculares (WH-1000XM4 Stereo Hands-Free)", "max_output_channels": 2, "hostapi": 2, "default_samplerate": 48000.0},
    {"name": "Speakers (Steam Streaming Speakers)", "max_output_channels": 2, "hostapi": 2, "default_samplerate": 48000.0},
    {"name": "Speakers 1 (Realtek HD Audio output with SST)", "max_output_channels": 2, "hostapi": 3, "default_samplerate": 44100.0},
]
HOSTAPIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"},
            {"name": "Windows WDM-KS"}]
WASAPI_REALTEK = 6
WASAPI_WH = 7


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _sd_falso(fallan=()):
    """Módulo sounddevice de mentira. `sd.fallan`: (device, samplerate) que no
    abren; ("*", "*") = ninguno (se puede cambiar a mitad de un test)."""
    sd = types.ModuleType("sounddevice")
    sd.abiertos = []
    sd.fallan = set(fallan)

    class WasapiSettings:
        def __init__(self, exclusive=False, auto_convert=False, explicit_sample_format=False):
            self.exclusive, self.auto_convert = exclusive, auto_convert

    class OutputStream:
        def __init__(self, samplerate=None, channels=None, dtype=None, device=None,
                     callback=None, extra_settings=None, finished_callback=None, **kw):
            if (device, samplerate) in sd.fallan or ("*", "*") in sd.fallan:
                raise RuntimeError(f"Error opening OutputStream: {device}@{samplerate}")
            self.samplerate, self.channels, self.dtype = samplerate, channels, dtype
            self.device, self.callback, self.extra = device, callback, extra_settings
            self.finished_callback = finished_callback
            self.iniciado = self.parado = self.cerrado = False
            self.active = False
            sd.abiertos.append(self)

        def start(self):
            self.iniciado = self.active = True

        def stop(self):
            self.parado, self.active = True, False

        def close(self):
            self.cerrado, self.active = True, False

        def morir(self):
            """El dispositivo desaparece: PortAudio lo marca inactivo y deja de
            llamar al callback (sin avisar por finished_callback)."""
            self.active = False

        def tirar(self, frames):
            out = np.full((frames, self.channels), 9.0, np.float32)   # basura: el callback debe pisarla
            self.callback(out, frames, None, None)
            return out

    sd.WasapiSettings = WasapiSettings
    sd.OutputStream = OutputStream
    sd.query_devices = lambda: [dict(d) for d in DISPOSITIVOS]
    sd.query_hostapis = lambda: [dict(h) for h in HOSTAPIS]
    return sd


class WinsoundFalso:
    SND_FILENAME = 0x20000
    SND_ASYNC = 0x1
    SND_LOOP = 0x8
    SND_NODEFAULT = 0x2

    def __init__(self):
        self.llamadas = []

    def PlaySound(self, sonido, flags):
        if sonido is not None:
            assert Path(sonido).is_file()
            with wave.open(sonido, "rb") as w:
                self.llamadas.append((sonido, flags, w.getnframes(), w.getframerate()))
        else:
            self.llamadas.append((None, flags, 0, 0))


@pytest.fixture
def entorno():
    sd, reloj, ws = _sd_falso(), Reloj(), WinsoundFalso()
    m = M.Mezclador(sd=sd, winsound=ws, reloj=reloj, vigilante=False)
    yield m, sd, reloj, ws
    m.cerrar()


def cte(valor, n, canales=2):
    return np.full((n, canales), valor, np.float32)


# ── Mezcla ─────────────────────────────────────────────────────────────────────

def test_no_abre_el_stream_hasta_reproducir(entorno):
    m, sd, reloj, ws = entorno
    assert sd.abiertos == [] and not m.abierto
    m.reproducir(cte(0.1, 100))
    assert len(sd.abiertos) == 1 and m.abierto
    st = sd.abiertos[0]
    assert (st.samplerate, st.channels, st.dtype, st.device) == (SR, 2, "float32", None)
    assert st.iniciado


def test_suma_de_fuentes(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.2, 1000))
    m.reproducir(cte(0.3, 1000))
    out = sd.abiertos[0].tirar(256)
    assert np.allclose(out, 0.5)
    assert len(sd.abiertos) == 1                    # un único stream para todo


def test_recorte(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.8, 500))
    m.reproducir(cte(0.8, 500))
    m.reproducir(cte(-0.3, 500))                     # 1.3 → 1.0
    out = sd.abiertos[0].tirar(64)
    assert np.allclose(out, 1.0)
    m.detener_todo()
    m.reproducir(cte(-0.9, 500))
    m.reproducir(cte(-0.9, 500))
    assert np.allclose(sd.abiertos[0].tirar(64), -1.0)


def test_volumen_y_volumen_de_canal(entorno):
    m, sd, reloj, ws = entorno
    a = m.reproducir(cte(0.5, 1000), vol=0.5, canal="sfx")
    m.reproducir(cte(0.2, 1000), canal="alarma")
    m.set_volumen_canal("alarma", 0.5)
    assert np.allclose(sd.abiertos[0].tirar(10), 0.25 + 0.1)
    m.set_volumen(a, 0.0)
    assert np.allclose(sd.abiertos[0].tirar(10), 0.1)


def test_mono_entero_se_convierte(entorno):
    m, sd, reloj, ws = entorno
    mono16 = np.full(100, 16384, np.int16)             # 0.5 en int16
    m.reproducir(mono16)
    out = sd.abiertos[0].tirar(10)
    assert out.shape == (10, 2) and np.allclose(out, 0.5)


def test_sin_bucle_termina_y_rellena_con_silencio(entorno):
    m, sd, reloj, ws = entorno
    sid = m.reproducir(cte(0.4, 100))
    out = sd.abiertos[0].tirar(150)
    assert np.allclose(out[:100], 0.4) and np.allclose(out[100:], 0.0)
    assert not m.activo(sid)
    assert m.posicion(sid) is None


def test_bucle(entorno):
    m, sd, reloj, ws = entorno
    rampa = np.array([0.1, 0.2, 0.3], np.float32)
    sid = m.reproducir(rampa, bucle=True)
    out = sd.abiertos[0].tirar(8)
    assert np.allclose(out[:, 0], [0.1, 0.2, 0.3, 0.1, 0.2, 0.3, 0.1, 0.2])
    assert m.activo(sid)
    out = sd.abiertos[0].tirar(4)                     # sigue donde iba
    assert np.allclose(out[:, 1], [0.3, 0.1, 0.2, 0.3])
    assert m.activo(sid)


def test_velocidad_doble_y_mitad(entorno):
    m, sd, reloj, ws = entorno
    rampa = np.arange(10, dtype=np.float32) / 10
    sid = m.reproducir(rampa, velocidad=2.0)
    out = sd.abiertos[0].tirar(6)
    assert np.allclose(out[:, 0], [0.0, 0.2, 0.4, 0.6, 0.8, 0.0])
    assert not m.activo(sid)
    m.reproducir(rampa, velocidad=0.5)
    out = sd.abiertos[0].tirar(5)
    assert np.allclose(out[:, 0], [0.0, 0.05, 0.1, 0.15, 0.2])


def test_velocidad_con_bucle(entorno):
    m, sd, reloj, ws = entorno
    rampa = np.arange(4, dtype=np.float32) / 10       # 0, .1, .2, .3
    m.reproducir(rampa, velocidad=1.5, bucle=True)
    out = sd.abiertos[0].tirar(4)
    # posiciones 0, 1.5, 3.0, 4.5→0.5 (interpolando entre el final y el principio)
    assert np.allclose(out[:, 0], [0.0, 0.15, 0.3, 0.05])


def test_posicion_en_segundos(entorno):
    m, sd, reloj, ws = entorno
    sid = m.reproducir(cte(0.1, 3 * SR))
    for _ in range(10):
        sd.abiertos[0].tirar(SR // 10)
    assert m.posicion(sid) == pytest.approx(1.0)
    rapido = m.reproducir(cte(0.1, 3 * SR), velocidad=2.0)
    sd.abiertos[0].tirar(SR // 2)
    assert m.posicion(rapido) == pytest.approx(1.0)


def test_detener_y_detener_canal(entorno):
    m, sd, reloj, ws = entorno
    a = m.reproducir(cte(0.1, 1000), canal="sfx")
    b = m.reproducir(cte(0.2, 1000), canal="sfx")
    c = m.reproducir(cte(0.4, 1000), canal="alarma", bucle=True)
    m.detener(a)
    assert not m.activo(a) and m.activo(b)
    m.detener_canal("sfx")
    assert not m.activo(b) and m.activo(c)
    assert np.allclose(sd.abiertos[0].tirar(10), 0.4)
    m.detener(999)                                  # id desconocido: nada


def test_pausar_conserva_posicion(entorno):
    m, sd, reloj, ws = entorno
    rampa = np.arange(10, dtype=np.float32) / 10
    sid = m.reproducir(rampa)
    sd.abiertos[0].tirar(3)
    m.pausar(sid)
    assert np.allclose(sd.abiertos[0].tirar(4), 0.0)
    assert m.activo(sid) and m.posicion(sid) == pytest.approx(3 / SR)
    m.pausar(sid, False)
    assert np.allclose(sd.abiertos[-1].tirar(2)[:, 0], [0.3, 0.4])


def test_buffer_vacio_no_abre_nada(entorno):
    m, sd, reloj, ws = entorno
    sid = m.reproducir(np.zeros((0, 2), np.float32))
    assert not m.activo(sid) and sd.abiertos == []


# ── Cierre por silencio ────────────────────────────────────────────────────────

def test_cierra_tras_5_s_de_silencio_y_reabre(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.1, 100))
    st = sd.abiertos[0]
    assert m.revisar_cierre() is False              # aún suena
    st.tirar(200)                                    # se acaba en t=1000
    reloj.t += 4.9
    assert m.revisar_cierre() is False and m.abierto
    reloj.t += 0.2
    assert m.revisar_cierre() is True
    assert st.parado and st.cerrado and not m.abierto
    # El callback de un stream cerrado ya no mezcla nada
    m.reproducir(cte(0.3, 100))
    assert np.allclose(st.tirar(10), 0.0)
    assert len(sd.abiertos) == 2 and np.allclose(sd.abiertos[1].tirar(10), 0.3)


def test_no_cierra_mientras_suena_un_bucle(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.1, 10), bucle=True, canal="alarma")
    for _ in range(120):                              # 60 s con PortAudio pidiendo audio
        reloj.t += 0.5
        sd.abiertos[0].tirar(512)
        assert m.revisar_cierre() is False
    assert len(sd.abiertos) == 1                      # ni se cerró ni se reabrió


def test_el_silencio_cuenta_desde_el_ultimo_sonido(entorno):
    m, sd, reloj, ws = entorno
    a = m.reproducir(cte(0.1, 10))
    sd.abiertos[0].tirar(20)                         # silencio desde t=1000
    reloj.t += 3
    m.reproducir(cte(0.1, 10))                       # vuelve a sonar en t=1003
    sd.abiertos[0].tirar(20)                         # silencio desde t=1003
    reloj.t += 3                                     # 6 s desde el primero, 3 desde el segundo
    assert m.revisar_cierre() is False
    reloj.t += 2.1
    assert m.revisar_cierre() is True
    assert not m.activo(a)


def test_detener_tambien_cuenta_como_silencio(entorno):
    m, sd, reloj, ws = entorno
    sid = m.reproducir(cte(0.1, 10), bucle=True)
    m.detener(sid)
    reloj.t += 5.01
    assert m.revisar_cierre() is True


# ── Stream muerto (dispositivo perdido) ────────────────────────────────────────

def test_stream_inactivo_se_reabre_al_reproducir(entorno):
    """El caso de la revisión: se va el dispositivo mientras suena un efecto y
    PortAudio deja de llamar al callback. Antes el efecto seguía «activo» para
    siempre y una alarma nueva se añadía a ese stream muerto sin sonar."""
    m, sd, reloj, ws = entorno
    efecto = m.reproducir(cte(0.1, SR // 10))
    viejo = sd.abiertos[0]
    viejo.morir()
    alarma = m.reproducir(cte(0.2, 100), bucle=True, canal="alarma")
    assert len(sd.abiertos) == 2 and viejo.cerrado and m.abierto
    nuevo = sd.abiertos[1]
    assert nuevo.iniciado and nuevo.active
    assert np.allclose(nuevo.tirar(10), 0.3)          # el efecto sigue por donde iba + la alarma
    nuevo.tirar(SR // 10)
    assert not m.activo(efecto) and m.activo(alarma)


def test_el_vigilante_reabre_un_stream_inactivo(entorno):
    m, sd, reloj, ws = entorno
    sid = m.reproducir(cte(0.1, SR // 10))
    sd.abiertos[0].morir()
    reloj.t += 0.5
    assert m.revisar_cierre() is False                # reabierto, no cerrado
    assert len(sd.abiertos) == 2 and sd.abiertos[0].cerrado and m.abierto
    for _ in range(3):
        reloj.t += 0.5
        assert m.revisar_cierre() is False
    assert len(sd.abiertos) == 2
    sd.abiertos[1].tirar(SR // 10 + 10)
    assert not m.activo(sid)                          # esta vez sí termina
    reloj.t += SILENCIO + 0.1
    assert m.revisar_cierre() is True                 # y el silencio lo cierra como siempre


def test_finished_callback_marca_el_stream_como_muerto(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.1, 1000))
    viejo = sd.abiertos[0]
    viejo.finished_callback()                         # PortAudio: el stream se paró solo
    assert m.revisar_cierre() is False
    assert len(sd.abiertos) == 2 and viejo.cerrado


def test_el_finished_callback_de_un_stream_que_cerramos_no_cuenta(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.1, 10))
    viejo = sd.abiertos[0]
    viejo.tirar(20)
    reloj.t += SILENCIO + 0.1
    assert m.revisar_cierre() is True                 # cerrado por silencio
    m.reproducir(cte(0.1, 100))
    viejo.finished_callback()                         # llega tarde, del stream viejo
    m.reproducir(cte(0.1, 100))
    assert len(sd.abiertos) == 2 and not sd.abiertos[1].cerrado


def test_callback_mudo_con_algo_sonando_reabre(entorno):
    """Algunos backends dejan de llamar al callback sin marcar el stream inactivo."""
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.1, 10), bucle=True, canal="alarma")
    st = sd.abiertos[0]
    st.tirar(100)
    reloj.t += M.CALLBACK_MUDO_S - 0.1
    assert m.revisar_cierre() is False and len(sd.abiertos) == 1
    reloj.t += 0.2                                    # más de CALLBACK_MUDO_S sin callback
    assert m.revisar_cierre() is False
    assert len(sd.abiertos) == 2 and st.cerrado
    assert np.allclose(sd.abiertos[1].tirar(5), 0.1)


def test_si_ningun_stream_llama_al_callback_deja_de_insistir(entorno):
    """Un driver que abre pero nunca pide audio no provoca reaperturas sin fin."""
    m, sd, reloj, ws = entorno
    alarma = m.reproducir(cte(0.2, 100), bucle=True, canal="alarma")
    for _ in range(M.MAX_REAPERTURAS_MUDAS):
        reloj.t += M.CALLBACK_MUDO_S + 0.1
        assert m.revisar_cierre() is False
    assert len(sd.abiertos) == 1 + M.MAX_REAPERTURAS_MUDAS
    reloj.t += M.CALLBACK_MUDO_S + 0.1
    assert m.revisar_cierre() is True and not m.abierto
    assert len(sd.abiertos) == 1 + M.MAX_REAPERTURAS_MUDAS
    assert ws.llamadas[-1][1] & ws.SND_LOOP and m.activo(alarma)
    assert "winsound" in m.ultimo_error


def test_un_callback_reinicia_la_cuenta_de_reaperturas(entorno):
    m, sd, reloj, ws = entorno
    m.reproducir(cte(0.2, 100), bucle=True, canal="alarma")
    for _ in range(2 * M.MAX_REAPERTURAS_MUDAS):
        reloj.t += M.CALLBACK_MUDO_S + 0.1
        assert m.revisar_cierre() is False
        sd.abiertos[-1].tirar(10)                     # el stream nuevo sí suena
        reloj.t += M.CALLBACK_MUDO_S + 0.1            # …y luego se queda mudo otra vez
    assert m.abierto and len(sd.abiertos) == 1 + 2 * M.MAX_REAPERTURAS_MUDAS


def test_sin_dispositivo_lo_que_sonaba_pasa_a_winsound(entorno):
    m, sd, reloj, ws = entorno
    alarma = m.reproducir(cte(0.2, SR // 2), bucle=True, canal="alarma")
    efecto = m.reproducir(cte(0.1, SR))
    sd.abiertos[0].morir()
    sd.fallan.add(("*", "*"))                         # y ya no abre ninguna salida
    reloj.t += 0.5
    assert m.revisar_cierre() is True and not m.abierto
    ruta, flags, frames, sr = ws.llamadas[-1]
    assert flags & ws.SND_LOOP and frames == SR // 2  # suena la alarma, no el efecto
    assert m.activo(alarma) and not m.activo(efecto)
    assert "No se pudo abrir" in m.ultimo_error


def test_reproducir_con_el_stream_muerto_y_sin_salida_usa_winsound(entorno):
    m, sd, reloj, ws = entorno
    viejo_efecto = m.reproducir(cte(0.1, SR))
    sd.abiertos[0].morir()
    sd.fallan.add(("*", "*"))
    nuevo = m.reproducir(cte(0.3, SR // 4))
    assert ws.llamadas[-1][2] == SR // 4 and not m.abierto
    assert m.activo(nuevo) and not m.activo(viejo_efecto)


def test_vigilante_real_cierra_el_stream():
    """Con el hilo vigilante de verdad y un cierre corto."""
    import time
    sd = _sd_falso()
    m = M.Mezclador(sd=sd, winsound=WinsoundFalso(), cierre_s=0.05)
    try:
        m.reproducir(cte(0.1, 10))
        sd.abiertos[0].tirar(20)
        limite = time.monotonic() + 3
        while m.abierto and time.monotonic() < limite:
            time.sleep(0.05)
        assert not m.abierto and sd.abiertos[0].cerrado
    finally:
        m.cerrar()


# ── Dispositivo ────────────────────────────────────────────────────────────────

def test_similitud_nombres():
    assert M.similitud_nombres("Speakers (Realtek(R) Audio)", "Speakers (2- Realtek(R) Audio)") == 1.0
    # MME recorta a 31 caracteres: es el mismo aparato
    assert M.similitud_nombres("Auriculares (WH-1000XM4 Stereo Hands-Free)",
                               "Auriculares (WH-1000XM4 Stereo") == 1.0
    assert M.similitud_nombres("Speakers (Steam Streaming Micro",
                               "Speakers (Steam Streaming Microphone)") == 1.0
    # Otro prefijo cualquiera se parece, pero menos
    assert M.similitud_nombres("Auriculares (WH-1000XM4)", "Auriculares (WH-1000XM4) Hands-Free") == 0.95
    assert M.similitud_nombres("Speakers (Steam Streaming Speakers)",
                               "Speakers (Steam Streaming Microphone)") < 0.8
    assert M.similitud_nombres("", "Speakers") == 0.0


def test_set_dispositivo_prefiere_wasapi(entorno):
    m, sd, reloj, ws = entorno
    assert m.set_dispositivo("Auriculares (WH-1000XM4 Stereo Hands-Free)") == \
        "Auriculares (WH-1000XM4 Stereo Hands-Free)"
    m.reproducir(cte(0.1, 10))
    st = sd.abiertos[0]
    assert st.device == WASAPI_WH and st.samplerate == SR
    assert st.extra is not None and st.extra.auto_convert and not st.extra.exclusive


def test_nombre_recortado_por_mme_tambien_va_por_wasapi(entorno):
    m, sd, reloj, ws = entorno
    assert m.set_dispositivo("Auriculares (WH-1000XM4 Stereo") == \
        "Auriculares (WH-1000XM4 Stereo Hands-Free)"
    m.reproducir(cte(0.1, 10))
    assert sd.abiertos[0].device == WASAPI_WH


def test_set_dispositivo_nombre_de_sdl_con_indice_de_windows(entorno):
    m, sd, reloj, ws = entorno
    # pygame lo guardó sin el «2- » que Windows añadió después
    assert m.set_dispositivo("Speakers (Realtek(R) Audio)") == "Speakers (2- Realtek(R) Audio)"
    m.reproducir(cte(0.1, 10))
    assert sd.abiertos[0].device == WASAPI_REALTEK


def test_set_dispositivo_desconocido_usa_el_del_sistema(entorno):
    m, sd, reloj, ws = entorno
    assert m.set_dispositivo("Altavoz Bluetooth (JBL Flip 5)") is None
    m.reproducir(cte(0.1, 10))
    assert sd.abiertos[0].device is None
    assert m.set_dispositivo("") is None


def test_nunca_wdm_ks_ni_alias():
    sd = _sd_falso()
    assert M.buscar_dispositivo(sd, "Speakers 1 (Realtek HD Audio output with SST)") is None
    assert M.buscar_dispositivo(sd, "Primary Sound Driver") is None


def test_cambiar_dispositivo_sonando_no_corta(entorno):
    m, sd, reloj, ws = entorno
    rampa = np.arange(10, dtype=np.float32) / 10
    m.reproducir(rampa)
    sd.abiertos[0].tirar(4)
    m.set_dispositivo("Speakers (Realtek(R) Audio)")
    viejo, nuevo = sd.abiertos
    assert viejo.cerrado and nuevo.device == WASAPI_REALTEK
    assert np.allclose(nuevo.tirar(2)[:, 0], [0.4, 0.5])     # sigue por donde iba


def test_wasapi_a_44k_falla_y_abre_a_48k(entorno):
    m, sd, reloj, ws = entorno
    sd2 = _sd_falso(fallan={(WASAPI_REALTEK, SR)})
    m = M.Mezclador(sd=sd2, winsound=ws, reloj=reloj, vigilante=False)
    m.set_dispositivo("Speakers (Realtek(R) Audio)")
    rampa = np.arange(0, 1, 0.1, dtype=np.float32)
    m.reproducir(rampa)
    st = sd2.abiertos[0]
    assert (st.device, st.samplerate) == (WASAPI_REALTEK, 48000)
    # A 48 kHz cada muestra de salida avanza 44100/48000 del buffer
    out = st.tirar(3)[:, 0]
    assert np.allclose(out, [0.0, 0.091875, 0.18375], atol=1e-5)
    m.cerrar()


def test_cae_a_winsound_si_sounddevice_no_abre(entorno):
    m, sd, reloj, ws = entorno
    m = M.Mezclador(sd=_sd_falso(fallan={("*", "*")}), winsound=ws, reloj=reloj, vigilante=False)
    sid = m.reproducir(cte(0.5, SR // 2), vol=0.5, bucle=True, canal="alarma")
    ruta, flags, frames, sr = ws.llamadas[-1]
    assert flags & ws.SND_ASYNC and flags & ws.SND_LOOP and flags & ws.SND_FILENAME
    assert ruta.endswith(".wav") and frames == SR // 2 and sr == SR
    with wave.open(ruta, "rb") as w:
        muestras = np.frombuffer(w.readframes(10), "<i2")
    assert np.allclose(muestras / 32767, 0.25, atol=1e-3)     # vol aplicado
    assert m.activo(sid)
    reloj.t += 0.2
    assert m.posicion(sid) == pytest.approx(0.2)
    m.detener_canal("alarma")
    assert ws.llamadas[-1][0] is None and not m.activo(sid)
    assert "No se pudo abrir" in m.ultimo_error
    m.cerrar()
    assert not Path(ruta).exists()


def test_winsound_sin_mezcla_el_ultimo_corta(entorno):
    m, sd, reloj, ws = entorno
    m = M.Mezclador(sd=_sd_falso(fallan={("*", "*")}), winsound=ws, reloj=reloj, vigilante=False)
    a = m.reproducir(cte(0.1, SR))
    b = m.reproducir(cte(0.1, SR // 4), velocidad=2.0)
    assert ws.llamadas[-1][2] == SR // 8                  # remuestreado al doble de rápido
    assert not m.activo(a) and m.activo(b)
    reloj.t += 0.2
    assert not m.activo(b)                                # 0.125 s de duración real
    m.cerrar()


def test_sin_sounddevice_instalado(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)      # import → ImportError
    ws = WinsoundFalso()
    m = M.Mezclador(winsound=ws, vigilante=False)
    assert m.modo == "winsound"
    m.reproducir(cte(0.1, 100))
    assert ws.llamadas and ws.llamadas[-1][0].endswith(".wav")
    m.cerrar()


def test_instancia_es_unica():
    assert M.Mezclador.instancia() is M.Mezclador.instancia()


# ── Carga de audio ─────────────────────────────────────────────────────────────

def _wav_pcm16(ruta, datos, sr, canales):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(canales)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.asarray(datos) * 32767).astype("<i2").tobytes())


def _wav_float(ruta, datos, sr, canales):
    cuerpo = np.asarray(datos, "<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, canales, sr, sr * 4 * canales, 4 * canales, 32)
    riff = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(cuerpo)) + cuerpo)
    Path(ruta).write_bytes(b"RIFF" + struct.pack("<I", len(riff)) + riff)


def test_cargar_wav_mono_16_bits(tmp_path):
    ruta = tmp_path / "blip.wav"
    _wav_pcm16(ruta, np.full(SR // 10, 0.5), SR, 1)
    buf = M.cargar_wav(ruta)
    assert buf.shape == (SR // 10, 2) and buf.dtype == np.float32
    assert np.allclose(buf, 0.5, atol=1e-4)
    assert not buf.flags.writeable
    assert M.cargar_wav(ruta) is buf                     # de la caché


def test_cargar_wav_remuestrea_a_44k(tmp_path):
    ruta = tmp_path / "lento.wav"
    _wav_pcm16(ruta, np.linspace(0, 0.5, 22050), 22050, 1)
    buf = M.cargar_wav(ruta)
    assert len(buf) == SR
    assert buf[0, 0] == pytest.approx(0.0, abs=1e-4) and buf[-2, 1] == pytest.approx(0.5, abs=1e-3)


def test_cargar_wav_float_estereo(tmp_path):
    ruta = tmp_path / "f.wav"
    datos = np.stack([np.full(100, 0.25), np.full(100, -0.75)], axis=1).reshape(-1)
    _wav_float(ruta, datos, SR, 2)
    buf = M.cargar_wav(ruta)
    assert np.allclose(buf[:, 0], 0.25) and np.allclose(buf[:, 1], -0.75)


def test_la_cache_no_guarda_wav_largos(tmp_path, monkeypatch):
    """Una canción en WAV ocupa ~21 MB por minuto en float32 estéreo: no se queda en RAM."""
    monkeypatch.setattr(M, "_cache", M.OrderedDict())
    ruta = tmp_path / "cancion.wav"
    _wav_pcm16(ruta, np.zeros(SR * 7), SR, 1)         # 7 s → ~2.5 MB
    a = M.cargar_wav(ruta)
    assert a.nbytes > M._CACHE_BUFFER_MAX_BYTES
    assert len(M._cache) == 0
    assert M.cargar_wav(ruta) is not a                  # se vuelve a leer
    assert not a.flags.writeable


def test_la_cache_tiene_tope_de_bytes_y_expulsa_lo_menos_usado(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "_cache", M.OrderedDict())
    n = SR // 10                                        # 0.1 s → n·2·4 bytes
    monkeypatch.setattr(M, "_CACHE_MAX_BYTES", 3 * n * 8)
    rutas = []
    for i in range(4):
        r = tmp_path / f"e{i}.wav"
        _wav_pcm16(r, np.full(n, 0.1 * (i + 1)), SR, 1)
        rutas.append(r)
    a, b, c = (M.cargar_wav(r) for r in rutas[:3])
    assert M.cargar_wav(rutas[0]) is a                  # a pasa a ser el más reciente
    M.cargar_wav(rutas[3])                              # no cabe: sale b
    assert sum(x.nbytes for x in M._cache.values()) <= M._CACHE_MAX_BYTES
    assert len(M._cache) == 3
    assert M.cargar_wav(rutas[0]) is a and M.cargar_wav(rutas[2]) is c
    assert M.cargar_wav(rutas[1]) is not b


def test_cachear_false_y_la_musica_no_se_guardan(entorno, tmp_path, monkeypatch):
    m, sd, reloj, ws = entorno
    monkeypatch.setattr(M, "_cache", M.OrderedDict())
    ruta = tmp_path / "corto.wav"
    _wav_pcm16(ruta, np.full(100, 0.5), SR, 1)
    M.cargar_wav(ruta, cachear=False)
    M.cargar_audio(ruta, cachear=False)
    m.reproducir(str(ruta), canal="musica")
    assert len(M._cache) == 0
    m.reproducir(str(ruta), canal="sfx")                # un efecto sí
    assert len(M._cache) == 1


def test_cargar_wav_errores(tmp_path):
    with pytest.raises(M.ErrorAudio):
        M.cargar_wav(tmp_path / "no_existe.wav")
    malo = tmp_path / "malo.wav"
    malo.write_bytes(b"esto no es un wav")
    with pytest.raises(M.ErrorAudio):
        M.cargar_wav(malo)


class _Resultado:
    def __init__(self, stdout=b"", returncode=0, stderr=b""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _wav_tuberia(datos, canales, sr=SR):
    """WAV f32le como lo saca ffmpeg por una tubería (tamaños 0xFFFFFFFF)."""
    cuerpo = np.asarray(datos, "<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, canales, sr, sr * 4 * canales, 4 * canales, 32) + b"\x00\x00"
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE" + b"fmt " + struct.pack("<I", len(fmt))
            + fmt + b"data" + struct.pack("<I", 0xFFFFFFFF) + cuerpo)


def test_cargar_audio_mp3_por_ffmpeg(tmp_path):
    mp3 = tmp_path / "cancion.mp3"
    mp3.write_bytes(b"ID3 falso")
    pcm = np.array([[0.1, -0.1], [0.2, -0.2], [0.3, -0.3]], "<f4")
    vistos = []

    def ejecutar(cmd, **kw):
        vistos.append(cmd)
        return _Resultado(stdout=_wav_tuberia(pcm.reshape(-1), 2))

    buf = M.cargar_audio(mp3, ffmpeg="ffmpeg.exe", ejecutar=ejecutar)
    assert np.allclose(buf, pcm) and buf.dtype == np.float32
    assert len(vistos) == 1
    cmd = vistos[0]
    assert cmd[0] == "ffmpeg.exe" and str(mp3) in cmd
    assert cmd[cmd.index("-f") + 1] == "wav" and cmd[cmd.index("-acodec") + 1] == "pcm_f32le"
    assert cmd[cmd.index("-ar") + 1] == "44100" and "-ac" not in cmd
    assert cmd[-1] == "pipe:1"


def test_cargar_audio_mono_se_duplica_sin_perder_volumen(tmp_path):
    ogg = tmp_path / "blip.ogg"
    ogg.write_bytes(b"OggS")
    buf = M.cargar_audio(ogg, ffmpeg="ffmpeg.exe",
                         ejecutar=lambda cmd, **kw: _Resultado(stdout=_wav_tuberia([0.5, 0.5, 0.5], 1)))
    assert buf.shape == (3, 2) and np.allclose(buf, 0.5)


def test_cargar_audio_51_pide_la_mezcla_a_ffmpeg(tmp_path):
    flac = tmp_path / "peli.flac"
    flac.write_bytes(b"fLaC")
    vistos = []

    def ejecutar(cmd, **kw):
        vistos.append(cmd)
        if "-ac" in cmd:
            return _Resultado(stdout=_wav_tuberia([0.2, 0.4] * 4, 2))
        return _Resultado(stdout=_wav_tuberia(np.zeros(6 * 4), 6))

    buf = M.cargar_audio(flac, ffmpeg="ffmpeg.exe", ejecutar=ejecutar)
    assert len(vistos) == 2 and vistos[1][vistos[1].index("-ac") + 1] == "2"
    assert buf.shape == (4, 2) and np.allclose(buf[:, 0], 0.2) and np.allclose(buf[:, 1], 0.4)


def test_cargar_audio_error_de_ffmpeg(tmp_path):
    ogg = tmp_path / "roto.ogg"
    ogg.write_bytes(b"OggS")
    with pytest.raises(M.ErrorAudio, match="Invalid data"):
        M.cargar_audio(ogg, ffmpeg="ffmpeg.exe",
                       ejecutar=lambda cmd, **kw: _Resultado(returncode=1, stderr=b"x\nInvalid data found"))


def test_cargar_audio_sin_ffmpeg_da_error_claro(tmp_path, monkeypatch):
    flac = tmp_path / "tema.flac"
    flac.write_bytes(b"fLaC")
    monkeypatch.setattr(M, "ruta_ffmpeg", lambda: None)
    with pytest.raises(M.ErrorAudio, match="imageio-ffmpeg"):
        M.cargar_audio(flac)


def test_cargar_audio_wav_no_necesita_ffmpeg(tmp_path, monkeypatch):
    ruta = tmp_path / "a.wav"
    _wav_pcm16(ruta, np.full(10, 0.5), SR, 1)
    monkeypatch.setattr(M, "ruta_ffmpeg", lambda: None)
    assert np.allclose(M.cargar_audio(ruta), 0.5, atol=1e-4)


def test_reproducir_acepta_ruta(entorno, tmp_path):
    m, sd, reloj, ws = entorno
    ruta = tmp_path / "a.wav"
    _wav_pcm16(ruta, np.full(50, 0.5), SR, 1)
    m.reproducir(str(ruta))
    assert np.allclose(sd.abiertos[0].tirar(10), 0.5, atol=1e-4)


@pytest.mark.skipif(M.ruta_ffmpeg() is None, reason="sin ffmpeg (pip install imageio-ffmpeg)")
def test_cargar_audio_con_ffmpeg_real(tmp_path):
    """El comando real de ffmpeg: se le da un WAV de 22 kHz mono con extensión .bin."""
    ruta = tmp_path / "tono.wav"
    t = np.arange(22050) / 22050
    _wav_pcm16(ruta, 0.5 * np.sin(2 * np.pi * 440 * t), 22050, 1)
    disfrazado = tmp_path / "tono.bin"
    disfrazado.write_bytes(ruta.read_bytes())
    buf = M.cargar_audio(disfrazado)
    assert buf.shape[1] == 2 and abs(len(buf) - SR) < 200
    assert 0.45 < float(np.abs(buf).max()) <= 0.51
