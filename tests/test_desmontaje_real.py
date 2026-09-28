"""
Desmontaje REAL de los servicios de escritorio (corte 4 + cortes 5/6) con trabajo en
marcha, como el cambio de interfaz en caliente: `servicios.desmontar()`,
`escritorio.cerrar()`, la mascota fuera y el dueño (la «ventana vieja») borrado con
deleteLater, en plena faena:

  · «Liberar memoria» en su hilo (el recorte sigue hasta después del cambio y avisa a un
    objeto que ya se fue), el radial esperando el ancla de la mascota, los atajos
    capturando una tecla y una vista previa del tema;
  · escenario «ocio»: una alarma sonando que abre la pantalla grande (VentanaReloj);
  · escenario «baile»: baile a mano con el detector de música de verdad en su hilo
    (sesión de Spotify simulada que manda el pulso) y el modo juego forzado encima.

Todo es el código de verdad (montar_escritorio, montar_ocio, ControlTema,
GestorAtajosQt, ControlMenuRadial, BandejaLune, ControlModoJuego, ControlAlarmasQt,
ControlPantallaGrande, ControlBaile, DetectorMusica…). Solo hay dobles de lo que toca
el sistema: RegisterHotKey (gestor de atajos), el audio (mezclador y sesiones de
WASAPI), el mutex de las alarmas, la prioridad del proceso, EmptyWorkingSet, la
entrada de Windows (GetLastInputInfo, cursor, XInput), el primer plano (el detector de
juegos no lee la pantalla: se fuerza) y QtWebEngine (no carga páginas en este entorno).

Corre en un proceso aparte (este mismo archivo como script): con el sys.excepthook de
serie una excepción en un slot aborta el proceso, igual que «QThread: Destroyed while
thread is still running». Además el hijo apunta las excepciones de los slots y los
avisos de Qt de hilos cruzados, y sale con 1 si hubo alguno.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Avisos de Qt que delatan un fallo aunque no aborten el proceso.
AVISOS_FATALES = (
    "Destroyed while thread", "Timers cannot be", "Cannot create children for a parent",
    "different thread", "wrapped C/C++ object", "QObject::connect: Cannot queue",
)


# ═══ El test (pytest) ═══════════════════════════════════════════════════════════

def _correr(escenario: str):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(Path(__file__).resolve()), escenario],
                          cwd=str(RAIZ), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def _comprobar(r, *esperado):
    salida = f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    assert r.returncode == 0, f"el desmontaje abortó o dejó errores (exit {r.returncode})\n{salida}"
    assert "FIN sin errores" in r.stdout, salida
    for texto in esperado:
        assert texto in r.stdout, f"falta «{texto}»\n{salida}"


def test_desmontaje_real_con_alarma_y_pantalla_grande():
    r = _correr("ocio")
    _comprobar(r, "alarma sonando: True", "pantalla grande: True", "con el recorte en marcha (True)",
               "hilo de música vivo: False", "liberar memoria terminó: True")


def test_desmontaje_real_con_baile_y_modo_juego_forzado():
    r = _correr("baile")
    _comprobar(r, "baile a mano: True", "detector midiendo: True", "modo juego: True",
               "con el recorte en marcha (True)", "hilo de música vivo: False",
               "liberar memoria terminó: True")


# ═══ El escenario (proceso hijo) ═══════════════════════════════════════════════

def _escenario(esc: str) -> int:                                    # pragma: no cover (hijo)
    import tempfile
    import threading
    import time
    from dataclasses import dataclass

    sys.path.insert(0, str(RAIZ))
    from nucleo.runtime_win import precargar_msvc
    precargar_msvc()
    from PyQt6.QtCore import QTimer, pyqtSignal, qInstallMessageHandler
    from PyQt6.QtWidgets import QApplication, QWidget

    errores = []

    def gancho(tipo, valor, tb):
        import traceback
        errores.append(f"{tipo.__name__}: {valor}")
        print("EXCEPCIÓN EN UN SLOT:", "".join(traceback.format_exception(tipo, valor, tb)), flush=True)

    sys.excepthook = gancho

    def mensajes_qt(_modo, _ctx, texto):
        if any(a in texto for a in AVISOS_FATALES):
            errores.append(texto)
            print("AVISO DE QT:", texto, flush=True)

    qInstallMessageHandler(mensajes_qt)

    app = QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    tmp = Path(tempfile.mkdtemp(prefix="lune_desmontaje_"))

    from nucleo import alarmas as al
    from nucleo.config import Config
    from servicios import modo_juego as mj
    from servicios import win_entrada as we
    from servicios.alarmas_aviso import ControlAviso
    from servicios.musica_detector import DetectorMusica
    from ui.escritorio import ServiciosEscritorio
    from ui.montaje_escritorio import montar_escritorio

    cfg = Config(str(tmp / "config.json"))
    cfg.set("salvapantallas", "activo", False)
    cfg.set("juego", "activo", False)          # el detector no lee la pantalla: se fuerza a mano

    t0 = time.monotonic()
    TOPE_S = 5.0

    def log(m):
        print(f"[{time.monotonic() - t0:5.2f}] {m}", flush=True)

    # ── Dobles de lo que toca el sistema ─────────────────────────────────────
    class GestorAtajosFalso:                      # RegisterHotKey
        errores = {}

        def __init__(self):
            self._vivo, self.reg, self._on_atajo = False, {}, None

        def activo(self): return self._vivo
        def iniciar(self): self._vivo = True; return True        # noqa: E702
        def detener(self): self._vivo = False
        def registrar(self, id_, combo): self.reg[id_] = combo
        def quitar(self, id_): self.reg.pop(id_, None)
        def quitar_todos(self): self.reg.clear()
        def registrados(self): return dict(self.reg)

    class MezcladorFalso:                         # la tarjeta de sonido
        def cargar_wav(self, ruta): return b""
        def reproducir(self, *a, **k): return 1
        def detener(self, *a, **k): pass
        def detener_canal(self, *a, **k): pass

    class MutexFalso:                             # mutex con nombre de Windows
        def intentar(self, *a, **k): return True
        adquirir = intentar
        def liberar(self): pass
        def __getattr__(self, n): return lambda *a, **k: True

    class EntradaWindowsFalsa:                    # GetLastInputInfo, cursor, XInput
        def ultima_entrada(self): return 1000
        def tick(self): return 1000 + int((time.monotonic() - t0) * 1000)
        def cursor(self): return (10, 10)
        def boton_izquierdo(self): return False
        def hay_xinput(self): return False
        def estado_mando(self, i): return None

    @dataclass(frozen=True)
    class Sesion:
        pid: int
        exe: str
        pico: float
        clave: str

    class MedidorFalso:                           # sesiones de audio (WASAPI por COM)
        def __init__(self):
            self.lecturas = 0

        def abrir(self): pass
        def cerrar(self): pass

        def sesiones(self, umbral_nombre=None):
            return [Sesion(4242, "Spotify", 0.6, "spotify")]

        def pico(self, clave):
            self.lecturas += 1
            return 0.6 if (self.lecturas // 12) % 2 == 0 else 0.1   # pulsa a ~2 Hz a 50 Hz

    class MascotaFalsa(QWidget):                  # la flotante: solo lo que reciben los servicios
        visibilidad = pyqtSignal(bool)
        menu_pedido = pyqtSignal(str, object)
        cerrado = False
        render = "sprites"
        durmiendo = False

        def ancla_menu(self, cb): pass            # nunca contesta: el radial espera su ancla
        def set_menu_abierto(self, on): pass
        def bailar(self, on, opciones=None): pass
        def pulso(self, *a): pass
        def mostrar_alarma(self, *a, **k): pass
        def ocultar_alarma(self): pass
        def aplicar_plan_juego(self, p): pass
        def aplicar_tema(self, css): pass
        def despertar(self): return False

    class Anfitrion:
        modo = "normal"
        soporta_llamada = True

        def __init__(self): self.avisos = []
        def mostrar_ventana(self): pass
        def mascota(self): return None
        def alternar_mascota(self): return False
        def voz_on(self): return False
        def alternar_voz(self): return False
        def llamada_on(self): return False
        def alternar_llamada(self): return False
        def abrir_ajustes(self, s=""): pass
        def salir(self): pass
        def aviso(self, t): self.avisos.append(t)
        def set_aburrimiento(self, a): pass
        def en_barra_on(self): return True
        def set_en_barra(self, on): pass
        def ventana_visible(self): return True

    recortando, soltar_recorte, liberado = threading.Event(), threading.Event(), threading.Event()

    def recortar_lento():                         # EmptyWorkingSet: sigue en su hilo hasta después del cambio
        recortando.set()
        soltar_recorte.wait(TOPE_S)
        liberado.set()
        return (100.0, 80.0)

    api_entrada = EntradaWindowsFalsa()
    detectores, medidores = [], []

    def juego_fab(escritorio, config, *, voice=None, parent=None):
        from ui.modo_juego_qt import ControlModoJuego
        return ControlModoJuego(escritorio, config, voice=voice,
                                detector=mj.DetectorJuego(config, pids=[os.getpid()]),
                                recortar=lambda: (1.0, 1.0), prioridad=lambda baja: None,
                                intervalo_ms=100, parent=parent)

    def grande_fab(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
        from ui.pantalla_grande_qt import ControlPantallaGrande
        return ControlPantallaGrande(escritorio, config, anfitrion=anfitrion, en_ui=en_ui,
                                     api_entrada=api_entrada, hay_webengine=lambda: False, parent=parent)

    def alarmas_fab(escritorio, config, *, voice=None, grande=None, avisar=None, en_ui=None, parent=None):
        from ui.alarmas_qt import ControlAlarmasQt
        alm = al.Almacen(tmp / "alarmas.json")
        return ControlAlarmasQt(escritorio, config, voice=voice, grande=grande, avisar=avisar, en_ui=en_ui,
                                almacen=alm, aviso=ControlAviso(mezclador=MezcladorFalso(), almacen=alm),
                                mutex=MutexFalso(), entrada=we.DetectorEntrada(api_entrada),
                                parent=parent, retraso_entrada_ms=200)

    def baile_fab(escritorio, config, *, en_ui=None, parent=None):
        from ui.baile_qt import ControlBaile
        medidores.append(MedidorFalso())
        d = DetectorMusica(config, medidor=medidores[-1], pids=[os.getpid()])
        detectores.append(d)
        return ControlBaile(escritorio, config, detector=d, en_ui=en_ui, parent=parent)

    # ── Montaje ──────────────────────────────────────────────────────────────
    duenio = QWidget()                            # la «ventana vieja»
    escritorio = ServiciosEscritorio(cfg, parent=duenio)
    m = MascotaFalsa()
    escritorio.set_mascota(m, render="sprites")
    anf = Anfitrion()
    fab = {"gestor_atajos": GestorAtajosFalso(), "recortar": recortar_lento, "autoinicio": None,
           "sonar": lambda n: None, "mezclador": MezcladorFalso, "traer_al_frente": None,
           "modelos_vrm": lambda: [], "juego": juego_fab,
           "ocio": {"grande": grande_fab, "alarmas": alarmas_fab, "baile": baile_fab},
           "escenario": False}
    s = montar_escritorio(escritorio, anf, cfg, fabricas=fab)
    escritorio.iniciar()
    montados = [n for n in ("tema", "atajos", "juego", "radial", "bandeja") if getattr(s, n) is not None]
    ocio = [n for n in ("grande", "alarmas", "baile") if getattr(s.ocio, n, None) is not None]
    log(f"montado: {montados} ocio={ocio}")
    if len(montados) != 5 or len(ocio) != 3:
        errores.append("no se montó todo")
    m.show()

    def en_vuelo():
        log("en vuelo: liberar memoria (hilo), atajos capturando, vista previa del tema")
        s.despachador.ejecutar("liberar_memoria")
        s.atajos.capturando(True)
        s.tema.previsualizar({"hue": 200, "preset": "personalizado"})
        if esc == "ocio":
            a = s.ocio.alarmas
            a.aviso.disparar(al.Disparo("prueba", "Hola", "prueba", 0.0, "", time.time()))
            log(f"alarma sonando: {a.aviso.sonando is not None}")
            log(f"pantalla grande: {bool(s.ocio.grande.activo) or s.ocio.grande.entrar('manual')}")
        else:
            log(f"baile a mano: {s.ocio.baile.bailar(10)}")

    def listo_para_cambiar() -> bool:
        if not recortando.is_set():
            return False                          # el recorte aún no empezó en su hilo
        return esc != "baile" or any(x.lecturas > 0 for x in medidores)   # el detector ya mide (50 Hz)

    def justo_antes():
        if esc == "baile":
            log(f"detector midiendo: {any(x.lecturas > 0 for x in medidores)}")
            s.despachador.ejecutar("modo_juego_forzar", "on")
            log(f"modo juego: {s.juego.activo()}")
        s.radial.abrir("principal")               # espera el ancla (350 ms): el cambio llega antes

    def cambio():
        log(f"cambio de interfaz con el recorte en marcha ({not liberado.is_set()}): desmontar + "
            "escritorio.cerrar + mascota fuera + dueño.deleteLater")
        s.desmontar()
        escritorio.cerrar()
        m.close()
        m.deleteLater()
        duenio.deleteLater()
        soltar_recorte.set()                      # el hilo acaba y avisa a un objeto que ya se fue

    # Por condiciones (con tope amplio), no por tiempos fijos: estable bajo carga.
    fase = {"n": 0, "t": time.monotonic()}

    def paso():
        n, desde = fase["n"], time.monotonic() - fase["t"]
        if n == 0:
            en_vuelo()
        elif n == 1:
            if not listo_para_cambiar() and desde < TOPE_S:
                return
            justo_antes()
            QTimer.singleShot(100, cambio)
        elif n == 2:
            if not liberado.is_set() and desde < TOPE_S:
                return
            reloj.stop()
            QTimer.singleShot(400, app.quit)      # los deleteLater y los avisos en cola, atendidos
        fase["n"], fase["t"] = n + 1, time.monotonic()

    reloj = QTimer()
    reloj.timeout.connect(paso)
    reloj.start(50)
    QTimer.singleShot(int(4 * TOPE_S * 1000), app.quit)   # red de seguridad
    app.exec()

    vivos = [d for d in detectores if d._hilo is not None and d._hilo.is_alive()]
    musica = any(h.name == "lune-musica" and h.is_alive() for h in threading.enumerate())
    log(f"hilo de música vivo: {bool(vivos) or musica}")
    log(f"liberar memoria terminó: {liberado.is_set()}")
    if vivos or musica:
        errores.append("el detector de música sigue en marcha")
    if errores:
        log(f"FIN con errores: {errores}")
        return 1
    log("FIN sin errores")
    return 0


if __name__ == "__main__":                                          # pragma: no cover (hijo)
    sys.exit(_escenario(sys.argv[1] if len(sys.argv) > 1 else "ocio"))
