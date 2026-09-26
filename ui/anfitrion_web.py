"""
ui/anfitrion_web.py — El «anfitrión» de la piel web para montar_escritorio (corte 4).

Traduce el contrato `Anfitrion` (ui/montaje_escritorio.py) a lo que YA existe en
LuneBridge (ui/web_bridge.py) y VentanaWeb (ui/web_shell.py): no los modifica.
Lo que aún no es público se busca con getattr y un respaldo:

- aburrimiento: `bridge.pausar_aburrimiento(on)` si existe (integración final);
  si no, para `_aburrida_t` o lo rearma con `_rearmar_aburrimiento()`;
- «Salir»: `ventana.salir_de_verdad()` (cambio de interfaz) o `_salir_de_verdad()`;
- ir a Ajustes: `navegar("settings")` si la integración lo conecta a la señal
  `navegar` del puente web (ui/puente_escritorio.py); si no, solo enseña la ventana;
- Lune en la barra lateral (la flotante guardada): `mascota_barra()` la cuenta como
  mascota para expresiones y baile, y `expresion_barra()` le pone la cara (`acto`).

Mostrar/ocultar la ventana de la barra de tareas es común a web y nativa:
`poner_en_barra()` (WS_EX_TOOLWINDOW por servicios/win_ventana del agente A).
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any, Callable, Optional

_log = logging.getLogger("lune.anfitrion")


def _cfg(config: Any, seccion: str, clave: str, defecto: Any = None) -> Any:
    try:
        if hasattr(config, "get") and not isinstance(config, dict):
            return config.get(seccion, clave, defecto)
        return (config or {}).get(seccion, {}).get(clave, defecto)
    except Exception:
        return defecto


def _cfg_set(config: Any, seccion: str, clave: str, valor: Any) -> None:
    try:
        if hasattr(config, "set") and not isinstance(config, dict):
            config.set(seccion, clave, valor)
        elif isinstance(config, dict):
            config.setdefault(seccion, {})[clave] = valor
    except Exception:
        _log.exception("anfitrión: no pude guardar %s.%s", seccion, clave)


def ventana_visible(v: Any) -> bool:
    if v is None:
        return False
    try:
        return bool(v.isVisible() and not v.isMinimized())
    except Exception:
        return False


def poner_en_barra(ventana: Any, on: bool, config: Any, *, set_en_barra: Optional[Callable] = None) -> bool:
    """Guarda interfaz.en_barra_tareas y quita/pone la ventana de la barra de
    tareas. WS_EX_TOOLWINDOW solo se nota al volver a mostrarla: si está a la
    vista, se oculta y se enseña otra vez. Devuelve el valor guardado."""
    on = bool(on)
    _cfg_set(config, "interfaz", "en_barra_tareas", on)
    if ventana is None:
        return on
    f = set_en_barra
    if f is None and sys.platform == "win32":
        try:
            from servicios import win_ventana       # corte 4, agente A
            f = getattr(win_ventana, "set_en_barra", None)
        except Exception:
            f = None
    if f is None:
        return on
    try:
        visible = bool(ventana.isVisible())
        if visible:
            ventana.hide()
        f(int(ventana.winId()), on)
        if visible:
            ventana.show()
    except Exception:
        _log.exception("anfitrión: no pude cambiar la ventana en la barra de tareas")
    return on


class AnfitrionWeb:
    """Anfitrión de la piel web (modo «normal»)."""

    modo = "normal"
    soporta_llamada = True

    def __init__(self, bridge: Any, ventana: Any = None, *, navegar: Optional[Callable[[str], Any]] = None):
        self.bridge = bridge
        self.ventana = ventana
        self.navegar = navegar          # la integración: puente_escritorio.navegar.emit
        self._expr_barra = 0            # la última expresión puesta en la barra (su turno)

    @property
    def config(self) -> Any:
        return getattr(self.bridge, "config", None)

    # ── Ventana ────────────────────────────────────────────────────────────
    def mostrar_ventana(self) -> None:
        v = self.ventana
        if v is None:
            return
        f = getattr(v, "_mostrar", None) or getattr(v, "mostrar", None)
        if callable(f):
            f()
            return
        v.showNormal()
        v.raise_()
        v.activateWindow()

    def ventana_visible(self) -> bool:
        return ventana_visible(self.ventana)

    def abrir_ajustes(self, seccion: str = "") -> None:
        """Enseña la ventana y va a Ajustes (`navegar("settings")` o
        "settings#<sección>"; la sección solo con [a-z0-9_-], 32 como mucho)."""
        self.mostrar_ventana()
        nav = self.navegar
        if callable(nav):
            sec = str(seccion or "")
            vista = f"settings#{sec}" if re.fullmatch(r"[a-z0-9_-]{1,32}", sec) else "settings"
            try:
                nav(vista)
            except Exception:
                _log.exception("anfitrión web: navegar falló")

    def salir(self) -> None:
        v = self.ventana
        f = (getattr(v, "salir_de_verdad", None) or getattr(v, "_salir_de_verdad", None)) if v else None
        if callable(f):
            f()
            return
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def aviso(self, texto: str) -> None:
        s = getattr(self.bridge, "aviso", None)
        if s is not None and hasattr(s, "emit"):
            s.emit(str(texto))

    def en_barra_on(self) -> bool:
        return bool(_cfg(self.config, "interfaz", "en_barra_tareas", True))

    def set_en_barra(self, on: bool) -> None:
        poner_en_barra(self.ventana, on, self.config)

    # ── Mascota ────────────────────────────────────────────────────────────
    def mascota(self) -> Any:
        f = getattr(self.bridge, "_mascota_viva", None)
        if callable(f):
            return f()
        ov = getattr(self.bridge, "_overlay", None)
        return None if ov is None or getattr(ov, "cerrado", False) else ov

    def alternar_mascota(self) -> bool:
        return bool(self.bridge.mascota_toggle())

    def comentar(self) -> bool:
        return bool(self.bridge.comentar_pantalla())

    # ── Lune en la barra lateral (la flotante guardada) ────────────────────
    def mascota_barra(self) -> bool:
        """¿Se ve a Lune en la barra lateral? Con la ventana a la vista y la flotante
        guardada: con la flotante fuera, la barra no la dibuja (sidebar.jsx). Ahí se
        abre el radial SVG y ella pone las expresiones y baila (nucleo/acciones_ui)."""
        if not self.ventana_visible():
            return False
        m = self.mascota()
        try:
            return not (m is not None and m.isVisible())
        except Exception:
            return True

    def expresion_barra(self, estado: str, ms: int = 4000) -> bool:
        """La cara de Lune en la barra (señal `acto` del puente, la de las respuestas)
        durante `ms`; luego vuelve a «normal» si no se puso otra entretanto ni está
        respondiendo (entonces la cara la lleva la respuesta)."""
        senal = getattr(self.bridge, "acto", None)
        if senal is None or not hasattr(senal, "emit"):
            return False
        try:
            senal.emit(str(estado))
        except RuntimeError:                       # el puente ya no existe
            return False
        self._expr_barra += 1
        turno = self._expr_barra

        def volver():
            if turno != self._expr_barra:
                return
            w = getattr(self.bridge, "_worker", None)
            try:
                if w is not None and w.isRunning():
                    return
            except RuntimeError:
                pass
            try:
                senal.emit("normal")
            except RuntimeError:
                pass
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(max(0, int(ms)), volver)
        return True

    # ── Voz y llamada ──────────────────────────────────────────────────────
    def voz_on(self) -> bool:
        return bool(getattr(getattr(self.bridge, "voice", None), "_enabled", False))

    def alternar_voz(self) -> bool:
        return bool(self.bridge.voz_toggle())

    def llamada_on(self) -> bool:
        return getattr(self.bridge, "_llamada", None) is not None

    def alternar_llamada(self) -> bool:
        return bool(self.bridge.llamada_toggle())

    # ── Aburrimiento (modo juego lo para) ──────────────────────────────────
    def set_aburrimiento(self, activo: bool) -> None:
        b = self.bridge
        f = getattr(b, "pausar_aburrimiento", None)
        if callable(f):
            f(not activo)
            return
        if activo:
            r = getattr(b, "_rearmar_aburrimiento", None)
            if callable(r):
                r()
        else:
            t = getattr(b, "_aburrida_t", None)
            if t is not None:
                try:
                    t.stop()
                except RuntimeError:
                    pass
