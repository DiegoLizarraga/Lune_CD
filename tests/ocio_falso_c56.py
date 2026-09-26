"""
Dobles de la integración de los cortes 5 y 6 (tests/test_contratos_c56.py y
tests/test_anfitriones_c56.py). No es un archivo de tests: lo importan.

`fabricas_ocio(reg)` da las fábricas de ui/montaje_ocio.montar_ocio con los
controladores DE VERDAD (ControlPantallaGrande, ControlAlarmasQt, ControlBaile) y lo
que tocaría el sistema cambiado por dobles, apuntado en un `Registro`:
  · alarmas.json en una carpeta temporal (nunca el de verdad);
  · el mutex del dueño de las alarmas (`Local\\Lune_CD_Alarmas`) con UN dueño a la vez,
    compartido entre todas las ventanas de la prueba (como el de Windows);
  · el detector de música (sin COM) y la entrada global (sin Win32);
  · el mezclador (mudo) y la VentanaReloj / la tarjeta de la alarma (sin ventanas).
`MascotaGrande` es una mascota con pantalla grande (VRM/animada) cuyas llamadas se
comprueban contra las firmas de la CompanionFlotante de verdad.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, List

from PyQt6.QtCore import QObject, QRect, pyqtSignal

try:
    # La CompanionFlotante de verdad (sus firmas), ANTES de que un test ponga una falsa en
    # sys.modules. Importa QtWebEngine: este módulo se importa antes de crear la QApplication.
    from ui.companion import CompanionFlotante as _COMPANION_REAL
except ImportError:                                   # sin QtWebEngine
    _COMPANION_REAL = None


class Registro:
    """Lo que el «sistema» ve: dueño del mutex, detectores vivos, controladores creados."""

    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.dueno = None                     # MutexFalso que tiene el mutex del dueño
        self.mutex: List["MutexFalso"] = []
        self.detectores: List["DetectorFalso"] = []
        self.grandes: List[Any] = []
        self.alarmas: List[Any] = []
        self.bailes: List[Any] = []
        self.mez = MezFalso()
        self.t = 1000.0                       # reloj monótono de la pantalla grande

    def reloj(self) -> float:
        return self.t

    @property
    def detectores_vivos(self) -> list:
        return [d for d in self.detectores if d.vivo]

    @property
    def alarmas_en_marcha(self) -> list:
        return [a for a in self.alarmas if getattr(a, "_iniciado", False)]

    @property
    def ruta_alarmas(self) -> Path:
        return self.carpeta / "alarmas.json"


class MutexFalso:
    """MutexNombrado de mentira: un solo dueño en todo el Registro."""

    def __init__(self, reg: Registro):
        self.reg = reg
        reg.mutex.append(self)

    def adquirir(self) -> bool:
        if self.reg.dueno in (None, self):
            self.reg.dueno = self
            return True
        return False

    def liberar(self) -> None:
        if self.reg.dueno is self:
            self.reg.dueno = None

    @property
    def es_dueno(self) -> bool:
        return self.reg.dueno is self


class DetectorFalso:
    """servicios.musica_detector.DetectorMusica sin COM."""

    def __init__(self, reg: Registro):
        self.vivo = False
        self.on_cambio = self.on_pulso = self.on_sesiones = None
        self.disponible = True
        self.forzados: List[bool] = []
        reg.detectores.append(self)

    def iniciar(self):
        self.vivo = True

    def detener(self):
        self.vivo = False

    def forzar_pulso(self, on):
        self.forzados.append(bool(on))

    def pedir_sondeo(self):
        pass

    def reanudar_auto(self):
        pass

    def silenciar_hasta_silencio(self):
        pass

    def estado(self) -> dict:
        return {"vivo": self.vivo}

    def apps_sonando(self) -> list:
        return []


class EntradaFalsa:
    """win_entrada.DetectorEntrada: `hubo = True` simula un clic o una tecla."""

    def __init__(self):
        self.hubo = False

    def reiniciar(self):
        self.hubo = False

    def poll(self) -> bool:
        h, self.hubo = self.hubo, False
        return h


class MezFalso:
    def __init__(self):
        self.reproducidos: List[tuple] = []
        self.parados: List[str] = []

    def cargar_wav(self, ruta):
        return b""

    def reproducir(self, buf, vol=1.0, bucle=False, canal=""):
        self.reproducidos.append((canal, bool(bucle)))
        return len(self.reproducidos)

    def detener(self, sid):
        pass

    def detener_canal(self, canal):
        self.parados.append(canal)


class VentanaRelojFalsa(QObject):
    """ui/ventana_reloj.VentanaReloj sin ventana."""
    apagar = pyqtSignal()
    posponer = pyqtSignal()
    cerrar_pedido = pyqtSignal()

    def __init__(self, *a, **k):
        super().__init__()
        self.modo, self.visible, self.alarma = "", False, None
        self.ocultandose = False

    def mostrar(self, modo, *, pantalla=None, fondo_oscuro=True, reloj=True, cara="normal"):
        self.modo, self.visible = modo, True

    def set_alarma(self, texto, *, bloqueo_ms=0, **k):
        self.alarma = texto

    def ocultar(self, ms=500):
        self.visible = False

    def isVisible(self):
        return self.visible


class DialogoFalso(QObject):
    """ui/alarmas_dialogo.DialogoAlarma sin ventana."""
    apagar = pyqtSignal()
    posponer = pyqtSignal()

    def __init__(self, *a, **k):
        super().__init__()
        self.visible, self.texto = False, None

    def set_disparo(self, texto, **k):
        self.texto = texto

    def mostrar(self):
        self.visible = True

    def cerrar(self):
        self.visible = False

    def close(self):
        self.visible = False


def fabricas_ocio(reg: Registro) -> dict:
    """Fábricas de montar_ocio con los controladores de verdad y dobles del sistema."""
    from nucleo.alarmas import Almacen
    from servicios.alarmas_aviso import ControlAviso
    from ui.alarmas_qt import ControlAlarmasQt
    from ui.baile_qt import ControlBaile
    from ui.pantalla_grande_qt import ControlPantallaGrande

    def grande(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
        g = ControlPantallaGrande(escritorio, config, anfitrion=anfitrion, en_ui=en_ui,
                                  entrada=EntradaFalsa(), api_entrada=object(),
                                  fabrica_reloj=VentanaRelojFalsa, reloj=reg.reloj,
                                  hay_webengine=lambda: False, parent=parent)
        reg.grandes.append(g)
        return g

    def alarmas(escritorio, config, *, voice=None, grande=None, avisar=None, en_ui=None, parent=None):
        almacen = Almacen(reg.ruta_alarmas)
        aviso = ControlAviso(mezclador=reg.mez, almacen=almacen, lanzar=lambda f: f())
        a = ControlAlarmasQt(escritorio, config, voice=voice, grande=grande, avisar=avisar, en_ui=en_ui,
                             almacen=almacen, aviso=aviso, mutex=MutexFalso(reg), entrada=EntradaFalsa(),
                             dialogo=DialogoFalso, retraso_entrada_ms=0, parent=parent)
        reg.alarmas.append(a)
        return a

    def baile(escritorio, config, *, en_ui=None, parent=None):
        b = ControlBaile(escritorio, config, detector=DetectorFalso(reg), en_ui=en_ui, parent=parent)
        reg.bailes.append(b)
        return b

    return {"grande": grande, "alarmas": alarmas, "baile": baile}


# ── Mascota con pantalla grande, con las firmas de la de verdad ─────────────────

def admite(fn, *args, **kw) -> bool:
    """¿`fn` acepta esta llamada? (sin llamarla)"""
    try:
        inspect.signature(fn).bind(*args, **kw)
        return True
    except TypeError:
        return False


class MascotaGrande(QObject):
    """Mascota VRM/animada a la vista con la página lista. Cada llamada del contrato
    de ocio se apunta en `diario` y se comprueba contra la firma del método de
    ui.companion.CompanionFlotante (si no encaja: AssertionError en `malas`)."""
    visibilidad = pyqtSignal(bool)
    render = "vrm"
    cerrado = False

    def __init__(self, geom=QRect(40, 60, 320, 480)):
        super().__init__()
        self._real = _COMPANION_REAL
        self._geom = QRect(geom)
        self.diario: List[tuple] = []
        self.malas: List[tuple] = []
        self.durmiendo = False
        self.soporta_grande = True

    def _apuntar(self, nombre, *a, **k):
        if self._real is not None and not admite(getattr(self._real, nombre), None, *a, **k):
            self.malas.append((nombre, a, k))
        self.diario.append((nombre,) + a + ((k,) if k else ()))

    def isVisible(self):
        return True

    def geometria(self):
        self._apuntar("geometria")
        return QRect(self._geom)

    def set_geometria(self, r):
        self._apuntar("set_geometria", r)
        self._geom = QRect(r)

    def grande_fase(self, fase, opciones=None):
        self._apuntar("grande_fase", fase, opciones)

    def set_salvapantallas(self, on, *, fondo_oscuro=True, reloj=True):
        self._apuntar("set_salvapantallas", on, fondo_oscuro=fondo_oscuro, reloj=reloj)
        self.durmiendo = bool(on)

    def mostrar_alarma(self, texto, *a, **k):
        self._apuntar("mostrar_alarma", texto, *a, **k)

    def ocultar_alarma(self):
        self._apuntar("ocultar_alarma")

    def bailar(self, on, opciones=None):
        if opciones is None:
            self._apuntar("bailar", on)
        else:
            self._apuntar("bailar", on, opciones)

    def pulso(self, bpm, fase, energia):
        self._apuntar("pulso", bpm, fase, energia)

    def despertar(self, *a, **k):
        self.durmiendo = False
        self.diario.append(("despertar",))

    def close(self):
        self.diario.append(("close",))

    def nombres(self) -> List[str]:
        return [x[0] for x in self.diario]

    def fases(self) -> List[str]:
        return [x[1] for x in self.diario if x[0] == "grande_fase"]
