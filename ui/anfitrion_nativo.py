"""
ui/anfitrion_nativo.py — El «anfitrión» de la interfaz nativa (bajos recursos)
para montar_escritorio (corte 4).

Traduce el contrato `Anfitrion` (ui/montaje_escritorio.py) a los métodos que YA
tiene main.LuneCDWindow (_restore_from_tray, _toggle_overlay, _toggle_voice,
_toggle_keys_panel, _quit_app, _mascota_viva…), sin modificarla. La nativa no
tiene modo llamada ni aburrimiento: `llamada_on()` es False y la acción
«llamada» no se registra (soporta_llamada = False).

Cortes 7/8: `reaccion(estado, ms)` pone la carita de la ventana (lune_face) cuando se
come sin la mascota a la vista, y `hwnd_principal()` da el HWND de la ventana para
que la mascota pueda sentarse en ella.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ui.anfitrion_web import _cfg, hwnd_de, poner_en_barra, ventana_visible

_log = logging.getLogger("lune.anfitrion")

INDICE_AJUSTES = 1        # página de ajustes en win.stack (ver main._build_main)
# El mismo texto que ui/web_bridge.AVISO_JUEGO_PANTALLA (sin importar el puente web).
AVISO_JUEGO_PANTALLA = "En modo juego no miro la pantalla. Cuando termines la partida, pídemelo otra vez."


class AnfitrionNativo:
    """Anfitrión de LuneCDWindow (modo «br»)."""

    modo = "br"
    soporta_llamada = False

    def __init__(self, win: Any):
        self.win = win

    @property
    def config(self) -> Any:
        return getattr(self.win, "config", None)

    # ── Ventana ────────────────────────────────────────────────────────────
    def mostrar_ventana(self) -> None:
        f = getattr(self.win, "_restore_from_tray", None)
        if callable(f):
            f()
            return
        self.win.showNormal()
        self.win.raise_()
        self.win.activateWindow()

    def ventana_visible(self) -> bool:
        return ventana_visible(self.win)

    def hwnd_principal(self) -> int:
        """HWND de la ventana principal (0 si no hay)."""
        return hwnd_de(self.win)

    def reaccion(self, estado: str, ms: int = 2500) -> bool:
        """La carita de la ventana (lune_face) durante `ms` (0.2–10 s): comer sin la
        mascota a la vista. False si la ventana no tiene carita."""
        e = str(estado or "").strip().lower()
        cara = getattr(self.win, "lune_face", None)
        f = getattr(cara, "set_state", None) if cara is not None else None
        if not callable(f) or not re.fullmatch(r"[a-z_]{1,24}", e):
            return False
        try:
            n = int(ms)
        except (TypeError, ValueError):
            n = 2500
        try:
            f(e, auto_revert_ms=max(200, min(10000, n)))
            return True
        except Exception:
            _log.exception("anfitrión nativo: la carita no reaccionó")
            return False

    def abrir_ajustes(self, seccion: str = "") -> None:
        self.mostrar_ventana()
        stack = getattr(self.win, "stack", None)
        try:
            actual = stack.currentIndex() if stack is not None else None
        except Exception:
            actual = None
        if actual == INDICE_AJUSTES:
            return
        f = getattr(self.win, "_toggle_keys_panel", None)
        if callable(f):
            f()
        elif stack is not None:
            stack.setCurrentIndex(INDICE_AJUSTES)

    def salir(self) -> None:
        f = getattr(self.win, "salir_de_verdad", None) or getattr(self.win, "_quit_app", None)
        if callable(f):
            f()

    def aviso(self, texto: str) -> None:
        f = getattr(self.win, "_set_status", None)
        if callable(f):
            try:
                from ui.theme import COLORS
                color = COLORS.get("accent", "#00E5FF")
            except Exception:
                color = "#00E5FF"
            try:
                f(str(texto), color)
            except Exception:
                _log.exception("anfitrión nativo: aviso falló")

    def en_barra_on(self) -> bool:
        return bool(_cfg(self.config, "interfaz", "en_barra_tareas", True))

    def set_en_barra(self, on: bool) -> None:
        poner_en_barra(self.win, on, self.config)

    # ── Mascota ────────────────────────────────────────────────────────────
    def mascota(self) -> Any:
        f = getattr(self.win, "_mascota_viva", None)
        if callable(f):
            return f()
        ov = getattr(self.win, "_overlay", None)
        return None if ov is None or getattr(ov, "cerrado", False) else ov

    def _mascota_visible(self) -> bool:
        m = self.mascota()
        try:
            return bool(m is not None and m.isVisible())
        except Exception:
            return False

    def alternar_mascota(self) -> bool:
        self.win._toggle_overlay()
        return self._mascota_visible()

    def _en_modo_juego(self) -> bool:
        """¿Hay partida? (BusEstado.juego de los servicios de escritorio)."""
        try:
            return bool(self.win.escritorio.estado.actual().juego)
        except Exception:
            return False

    def comentar(self) -> bool:
        """Saca la mascota (si hace falta) y le pide comentar la pantalla. En modo
        juego no: ni captura ni comentario (anticheat y rendimiento) y la mascota que
        escondió el juego no se saca para eso (como la web, web_bridge.comentar_pantalla)."""
        if self._en_modo_juego():
            self.aviso(AVISO_JUEGO_PANTALLA)
            return False
        if not self._mascota_visible():
            self.win._toggle_overlay()                  # la crea o la enseña
        m = self.mascota()
        f = getattr(m, "comentar_pantalla", None)
        if not callable(f):
            self.aviso("Comentar la pantalla necesita la mascota 3D (Ajustes → Mascota).")
            return False
        try:
            f()
            return True
        except Exception:
            _log.exception("anfitrión nativo: comentar_pantalla falló")
            return False

    # ── Voz (sin llamada ni aburrimiento en la nativa) ─────────────────────
    def voz_on(self) -> bool:
        return bool(getattr(getattr(self.win, "voice", None), "_enabled", False))

    def alternar_voz(self) -> bool:
        self.win._toggle_voice()
        return self.voz_on()

    def llamada_on(self) -> bool:
        return False

    def alternar_llamada(self) -> bool:
        return False

    def set_aburrimiento(self, activo: bool) -> None:
        return None
