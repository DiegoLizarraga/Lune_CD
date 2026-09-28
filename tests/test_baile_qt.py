"""
Tests de ui/baile_qt.ControlBaile (offscreen): la tabla de prioridades, dormida
no baila (y baila al despertar), ceder/reanudar, baile a mano con metrónomo y
duración, pausa hasta el silencio, el JSON de `estado_cambio`, el pulso ≤ 2 Hz y
las llamadas a la mascota. Detector y mascota falsos; ServiciosEscritorio real.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Config:
    def __init__(self, **baile):
        self.d = {"baile": {"auto": True, "umbral": 0.2, "apps": ["Spotify", "vlc"], **baile}}

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor


class DetectorFalso:
    def __init__(self):
        self.on_cambio = self.on_pulso = self.on_sesiones = None
        self.llamadas = []
        self.disponible = True

    def iniciar(self):
        self.llamadas.append("iniciar")

    def detener(self):
        self.llamadas.append("detener")

    def forzar_pulso(self, on):
        self.llamadas.append(("forzar", on))

    def silenciar_hasta_silencio(self):
        self.llamadas.append("silenciar")

    def reanudar_auto(self):
        self.llamadas.append("reanudar_auto")

    def pedir_sondeo(self):
        self.llamadas.append("sondeo")

    # lo que haría el hilo del detector
    def musica(self, on, app="Spotify"):
        self.on_cambio(on, app if on else "")


class MascotaFalsa:
    def __init__(self):
        self.bailes, self.pulsos = [], []
        self.durmiendo = False
        self.despertares = 0

    def bailar(self, on, opciones=None):
        self.bailes.append((on, opciones))

    def pulso(self, bpm, fase, energia):
        self.pulsos.append((bpm, fase, energia))

    def despertar(self):
        self.despertares += 1
        self.durmiendo = False
        return True


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def montaje(qapp):
    from ui.baile_qt import ControlBaile
    from ui.escritorio import ServiciosEscritorio
    esc = ServiciosEscritorio(Config())
    cfg = esc.config
    det = DetectorFalso()
    reloj = Reloj()
    en_ui_llamadas = []

    def en_ui(fn):
        en_ui_llamadas.append(fn)
        return fn()
    ctl = ControlBaile(esc, cfg, detector=det, en_ui=en_ui, reloj=reloj)
    esc.registrar("baile", ctl, ("baile",))
    esc.iniciar()
    m = MascotaFalsa()
    ctl.set_mascota(m)
    ctl.estados = []
    ctl.pulsos = []
    ctl.estado_cambio.connect(lambda s: ctl.estados.append(json.loads(s)))
    ctl.pulso.connect(lambda s: ctl.pulsos.append(json.loads(s)))

    class M:
        pass
    x = M()
    x.esc, x.cfg, x.det, x.ctl, x.m, x.reloj, x.en_ui = esc, cfg, det, ctl, m, reloj, en_ui_llamadas
    yield x
    esc.cerrar()
    ctl.deleteLater()


def bailando_bus(x):
    return x.esc.estado.actual().bailando


def test_musica_pide_la_prioridad_y_la_mascota_baila(montaje):
    x = montaje
    assert "iniciar" in x.det.llamadas and x.det.on_cambio is not None
    x.det.musica(True)
    assert x.ctl.bailando and bailando_bus(x) == "musica"
    on, opts = x.m.bailes[-1]
    assert on is True and set(opts) == {"estilo", "cambiar", "cambiarS", "particulas"}
    e = x.ctl.estados[-1]
    assert e["bailando"] and e["origen"] == "auto" and e["musica"] and e["app"] == "Spotify"
    assert set(e) >= {"bailando", "origen", "musica", "app", "estilo", "bpm", "energia", "auto",
                      "pausado_hasta_silencio"}
    assert x.m.pulsos, "el primer pulso sale al empezar"
    x.det.musica(False)                                  # 6 s sin música (lo decide el detector)
    assert not x.ctl.bailando and bailando_bus(x) == "" and x.m.bailes[-1] == (False, None)


def test_empezar_con_musica_llama_una_sola_vez_a_la_mascota(montaje):
    # MO10: prioridad.iniciar avisa al bus dentro de bailar(); _on_bus no puede empezar
    # otro baile (otro estilo, fundido de 2 s) antes de que este marque _bailando.
    import random
    x = montaje
    for semilla in range(6):
        random.seed(semilla)
        x.m.bailes.clear()
        x.det.llamadas.clear()
        x.det.musica(True)
        assert [on for on, _ in x.m.bailes] == [True], semilla
        assert [c for c in x.det.llamadas if isinstance(c, tuple)] == [("forzar", False)]
        assert x.ctl.bailando and bailando_bus(x) == "musica"
        x.det.musica(False)
        assert not x.ctl.bailando


def test_bailar_a_mano_con_musica_llama_una_sola_vez(montaje):
    x = montaje
    x.det.musica(True)
    x.ctl.parar()                                        # pausado hasta que se calle la música
    x.ctl._pausado = False                               # (la vuelve a permitir sin que empiece sola)
    x.m.bailes.clear()
    assert x.ctl.bailar(30) is True
    assert [on for on, _ in x.m.bailes] == [True]
    assert x.ctl.estado()["origen"] == "manual"


def test_pulso_como_mucho_2_hz_desde_el_detector(montaje):
    from nucleo.pulso import Pulso
    x = montaje
    x.det.musica(True)
    assert x.ctl._t_pulso.interval() == 500 and x.ctl._t_pulso.isActive()
    x.det.on_pulso(Pulso(128.0, 0.25, 0.8, 0.9, x.reloj.t))
    x.reloj.t += 0.5
    x.ctl._tic_pulso()
    bpm, fase, energia = x.m.pulsos[-1]
    assert bpm == 128.0 and fase == pytest.approx((0.25 + 0.5 * 128 / 60) % 1.0) and energia == 0.8
    assert x.ctl.pulsos[-1] == {"bpm": 128.0, "fase": round(fase, 4), "energia": 0.8}
    x.det.on_pulso(Pulso(90.0, 0.0, 0.2, 0.05, x.reloj.t))   # confianza baja: se sigue el bueno
    x.ctl._tic_pulso()
    assert x.m.pulsos[-1][0] == 128.0 and x.m.pulsos[-1][2] == 0.2


def test_dormida_no_baila_y_baila_al_despertar(montaje):
    x = montaje
    x.esc.estado.actualizar(durmiendo=True)
    x.det.musica(True)
    assert not x.ctl.bailando and x.m.despertares == 0      # no se la despierta (D5)
    x.esc.estado.actualizar(durmiendo=False)
    assert x.ctl.bailando and bailando_bus(x) == "musica"


def test_no_empieza_con_pantalla_grande_y_si_al_acabar(montaje):
    x = montaje
    assert x.esc.prioridad.iniciar("grande")
    x.det.musica(True)
    assert not x.ctl.bailando and x.m.bailes == []
    x.esc.prioridad.terminar("grande")
    assert x.ctl.bailando


def test_ceder_por_juego_y_reanudar_si_sigue_la_musica(montaje):
    x = montaje
    x.det.musica(True)
    x.esc.prioridad.iniciar("juego")
    assert not x.ctl.bailando and x.m.bailes[-1] == (False, None)
    x.esc.prioridad.terminar("juego")
    assert x.ctl.bailando and bailando_bus(x) == "musica" and x.m.bailes[-1][0] is True


def test_reanudar_sin_musica_suelta_la_actividad(montaje):
    x = montaje
    x.det.musica(True)
    x.esc.prioridad.iniciar("alarma")
    assert not x.ctl.bailando
    x.ctl._musica = False                                # la música paró durante la alarma…
    x.esc.prioridad.terminar("alarma")                   # …la tabla la reanuda, pero no baila
    assert not x.ctl.bailando and bailando_bus(x) == ""


def test_musica_que_para_durante_el_juego_no_se_reanuda(montaje):
    x = montaje
    x.det.musica(True)
    x.esc.prioridad.iniciar("juego")
    x.det.musica(False)                                  # en juego el detector la da por acabada
    x.esc.prioridad.terminar("juego")
    assert not x.ctl.bailando and bailando_bus(x) == ""


def test_manual_sin_musica_metronomo_y_dura_n_segundos(montaje):
    x = montaje
    x.m.durmiendo = True
    assert x.ctl.bailar(10) is True
    assert x.m.despertares == 1                          # a mano sí se despierta
    assert bailando_bus(x) == "manual" and ("forzar", True) in x.det.llamadas
    assert x.ctl._t_fin.isActive() and x.ctl._t_fin.interval() == 10_000
    bpm, fase, _ = x.m.pulsos[-1]
    assert bpm == 120.0 and fase == pytest.approx(0.0)
    x.reloj.t += 0.25
    x.ctl._tic_pulso()
    assert x.m.pulsos[-1][1] == pytest.approx(0.5)       # metrónomo de 120
    x.ctl._fin_manual()                                  # pasaron los 10 s
    assert not x.ctl.bailando and bailando_bus(x) == "" and x.det.llamadas[-1] == ("forzar", False)


def test_manual_que_acaba_con_musica_sigue_en_automatico(montaje):
    x = montaje
    x.ctl.bailar(5)
    x.det.musica(True)
    x.ctl._fin_manual()
    assert x.ctl.bailando and x.ctl.estado()["origen"] == "auto" and bailando_bus(x) == "musica"


def test_manual_no_puede_con_alarma_y_da_el_motivo(montaje):
    x = montaje
    x.esc.prioridad.iniciar("alarma")
    assert x.ctl.bailar(10) is False and x.ctl.ultimo_motivo == "alarma"


def test_pausa_hasta_el_silencio(montaje):
    x = montaje
    x.det.musica(True)
    assert x.ctl.pausa() is True
    assert not x.ctl.bailando and "silenciar" in x.det.llamadas
    assert x.ctl.estado()["pausado_hasta_silencio"] is True
    x.esc.estado.actualizar(hablando=True)               # otro cambio del bus: no vuelve sola
    assert not x.ctl.bailando
    assert x.ctl.pausa() is True                         # deshacer la pausa: vuelve a bailar
    assert "reanudar_auto" in x.det.llamadas and x.ctl.bailando
    x.ctl.pausa()
    x.det.musica(False)                                  # la música se calla: fin de la pausa
    assert x.ctl.estado()["pausado_hasta_silencio"] is False
    x.det.musica(True)
    assert x.ctl.bailando


def test_parar_por_la_herramienta_no_vuelve_sola(montaje):
    x = montaje
    x.det.musica(True)
    h = x.ctl.herramientas()
    assert set(h) == {"mascota_bailar", "parar_baile"}
    assert h["parar_baile"]({}, None) == "Vale, dejo de bailar."
    assert x.en_ui, "la herramienta pasa por en_ui"
    assert not x.ctl.bailando and x.ctl.estado()["pausado_hasta_silencio"]
    assert h["mascota_bailar"]({"segundos": 20}, {}) == "¡A bailar! 20 s."
    assert x.ctl.bailando and x.ctl.estado()["origen"] == "manual"


def test_set_mascota_mientras_baila(montaje):
    x = montaje
    x.det.musica(True)
    otra = MascotaFalsa()
    x.ctl.set_mascota(otra)
    assert otra.bailes and otra.bailes[-1][0] is True and otra.pulsos


def test_recargar_config_sin_auto_para_el_automatico(montaje):
    x = montaje
    x.det.musica(True)
    x.cfg.set("baile", "auto", False)
    x.ctl.recargar_config()
    assert not x.ctl.bailando and x.ctl.estado()["auto"] is False


def test_apps_permitir_quitar_y_suenan_ahora(montaje):
    x = montaje
    assert x.ctl.permitir_app("C:\\Apps\\Deezer.exe") == ["Spotify", "vlc", "Deezer"]
    assert x.cfg.get("baile", "apps") == ["Spotify", "vlc", "Deezer"]
    assert x.ctl.permitir_app("spotify") == ["Spotify", "vlc", "Deezer"]      # sin repetir
    assert x.ctl.quitar_app("VLC") == ["Spotify", "Deezer"]
    assert x.ctl.permitir_app("a*b") == ["Spotify", "Deezer"]
    recibidas = []
    x.ctl.apps_cambio.connect(lambda s: recibidas.append(json.loads(s)))
    x.det.on_sesiones(["firefox", "Spotify"])
    assert recibidas == [["firefox", "Spotify"]]
    assert x.ctl.apps_sonando() == ["firefox", "Spotify"] and "sondeo" in x.det.llamadas


def test_detener_para_y_suelta_el_detector(montaje):
    x = montaje
    x.det.musica(True)
    x.esc.detener()
    assert not x.ctl.bailando and bailando_bus(x) == "" and "detener" in x.det.llamadas
    assert x.det.on_cambio is None


def test_con_el_detector_de_verdad_y_medidor_falso(qapp):
    """Del detector (sondear a mano) al baile, pasando por las señales."""
    from servicios.audio_sesiones import Sesion
    from servicios.musica_detector import DetectorMusica
    from ui.baile_qt import ControlBaile
    from ui.escritorio import ServiciosEscritorio

    class Medidor:
        nivel = 0.5

        def abrir(self):
            pass

        def cerrar(self):
            pass

        def sesiones(self, umbral_nombre=None):
            return [Sesion(77, "Spotify", self.nivel, "k")]

        def pico(self, clave):
            return self.nivel
    med = Medidor()
    esc = ServiciosEscritorio(Config())
    reloj = Reloj()
    det = DetectorMusica(esc.config, medidor=med, pids={1}, reloj=reloj)
    det.iniciar = lambda: None                           # sin hilo: pasos a mano
    ctl = ControlBaile(esc, esc.config, detector=det, reloj=reloj)
    esc.registrar("baile", ctl, ("baile",))
    esc.iniciar()
    m = MascotaFalsa()
    ctl.set_mascota(m)
    det.sondear()
    reloj.t += 2
    det.sondear()
    assert ctl.bailando and m.bailes[-1][0] is True and esc.estado.actual().bailando == "musica"
    esc.cerrar()


def test_ctx_de_las_herramientas_lleva_el_reproductor_de_bailes(montaje):
    """Corte 9: con el ControlMMD registrado como «mmd», «bailar {cancion}» va a él."""
    x = montaje

    class MMDFalso:
        activo = False
        ultimo_motivo = ""

        def __init__(self):
            self.textos = []

        def reproducir_por_texto(self, texto):
            self.textos.append(texto)
            return True, "¡A bailar «Uno»!"
    mmd = MMDFalso()
    x.esc.registrar("mmd", mmd)
    h = x.ctl.herramientas()
    assert h["mascota_bailar"]({"cancion": "uno"}, {"origen": "usuario"}) == "¡A bailar «Uno»!"
    assert mmd.textos == ["uno"] and x.en_ui and not x.ctl.bailando
    x.esc.quitar("mmd")
    assert "reproductor" in h["mascota_bailar"]({"cancion": "uno"}, {})
