"""
Dobles de la integración de los cortes 7 y 8 (sentarse, comida, Discord): fábricas de
ui/montaje_vida.montar_vida con los controladores DE VERDAD (ui/asiento_qt.ControlAsiento,
ui/comida_qt.ControlComida, ui/discord_qt.ControlDiscord) sobre dobles del sistema:
ventanas, pantalla y ventana propia falsas (tests/ventanas_falsas_c78.py), mezclador,
cursor de la comida y presencia de Discord falsos. Nada de Win32 que cambie algo, ni
audio, ni la tubería de Discord.

    reg = Registro()
    fab = {"vida": fabricas_vida(reg)}        # para montar_escritorio / FABRICAS_C4
    reg.asientos_vivos() · reg.discords_vivos() · reg.presencias_publicando()
"""
import random
from typing import Any, List

from ventanas_falsas_c78 import ApiVentanasFalsa, EntradaFalsa, PantallaFalsa, VentanaPropiaFalsa


class MezFalso:
    """servicios/mezclador.Mezclador de mentira (lo que usa nucleo.comida.SonidosComida)."""

    def __init__(self):
        self.reproducidos: List[tuple] = []

    def cargar_wav(self, ruta):
        return b""

    def reproducir(self, buf, vol=1.0, velocidad=1.0, canal="", **kw):
        self.reproducidos.append((canal, round(float(velocidad), 3)))
        return len(self.reproducidos)


class CursorFalso:
    """ui/comida_qt.ComidaCursor sin ventana."""

    def __init__(self):
        self.llamadas: List[tuple] = []
        self.visible = False

    def mostrar(self, id_, variante, tam_px, centro=None):
        self.llamadas.append(("mostrar", id_, variante))
        self.visible = True

    def ocultar(self, animado=True):
        self.llamadas.append(("ocultar", animado))
        self.visible = False

    def paso(self, dt, cursor):
        pass

    def close(self):
        self.visible = False


class PresenciaFalsa:
    """servicios/discord_presencia.Presencia sin hilo ni tubería: ¿quién publicaría?"""

    def __init__(self):
        self.habilitada = False
        self.cerrada = 0
        self.actualizaciones = 0
        self.estado_fn = None
        self.on_estado = None

    def habilitar(self, on):
        self.habilitada = bool(on)

    def actualizar(self):
        self.actualizaciones += 1

    def estado(self):
        return {"activo": self.habilitada, "conectado": False, "usuario": "", "error": "",
                "publicando": None, "sin_id": False}

    def cerrar(self, timeout=1.0):
        self.habilitada = False
        self.cerrada += 1


class Registro:
    """Lo que crearon las fábricas (de todas las ventanas de un test)."""

    def __init__(self, ventanas=None):
        self.api = ApiVentanasFalsa(ventanas or {})
        self.pantalla = PantallaFalsa()
        self.win = VentanaPropiaFalsa({})
        self.cursor = EntradaFalsa(500, 500)
        self.mez = MezFalso()
        self.asientos: List[Any] = []
        self.comidas: List[Any] = []
        self.discords: List[Any] = []
        self.presencias: List[PresenciaFalsa] = []

    def asientos_vivos(self):
        return [a for a in self.asientos if getattr(a, "_iniciado", False)]

    def comidas_vivas(self):
        return [c for c in self.comidas if getattr(c, "_iniciado", False)]

    def discords_vivos(self):
        return [d for d in self.discords if getattr(d, "_iniciado", False)]

    def presencias_publicando(self):
        return [p for p in self.presencias if p.habilitada]


def fabricas_vida(reg: Registro) -> dict:
    """Las fábricas de montar_vida con las clases de verdad y los dobles de `reg`."""
    from ui.asiento_qt import ControlAsiento
    from ui.comida_qt import ControlComida
    from ui.discord_qt import ControlDiscord

    def asiento(escritorio, config, *, hwnd_principal=None, en_ui=None, parent=None):
        a = ControlAsiento(escritorio, config, api=reg.api, ventana=reg.win, entrada=reg.cursor,
                           pantalla=reg.pantalla, hwnd_principal=hwnd_principal, en_ui=en_ui,
                           parent=parent, azar=random.Random(3))
        reg.asientos.append(a)
        return a

    def comida(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
        c = ControlComida(escritorio, config, anfitrion=anfitrion, mezclador=reg.mez,
                          fabrica_cursor=CursorFalso, azar=random.Random(4), en_ui=en_ui,
                          parent=parent, lanzar_sonido=lambda f: f())
        reg.comidas.append(c)
        return c

    def discord(escritorio, config, *, modo="normal", nombre_modelo=None, parent=None):
        p = PresenciaFalsa()
        reg.presencias.append(p)
        d = ControlDiscord(escritorio, config, modo=modo, presencia=p, nombre_modelo=nombre_modelo,
                           parent=parent)
        reg.discords.append(d)
        return d

    return {"asiento": asiento, "comida": comida, "discord": discord}
