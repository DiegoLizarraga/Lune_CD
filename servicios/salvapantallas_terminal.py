"""
servicios/salvapantallas_terminal.py — El salvapantallas del modo patata.

En la terminal no hay ventana que llevar a pantalla completa: el salvapantallas
es el TÍTULO de la consola. Tras `salvapantallas.paso` sin tocar el PC (los
mismos 11 pasos de nucleo/pantalla_grande.py) el título pasa a
«(-_-) zzZ 23:41» (sin la hora si `salvapantallas.reloj` está apagado) y la hora
se refresca cada minuto. Vuelve en cuanto hay entrada (cualquier tecla, clic o
movimiento del ratón: aquí no hay nada que cerrar a propósito) o un mando.

Un hilo sondea cada segundo `win_entrada.segundos_inactivo()` (GetLastInputInfo)
y `mando_activo()` (XInput). No arma con un juego delante (`en_juego`) ni si
alguien pide la pantalla encendida (`pantalla_requerida`: un vídeo).

El título va por capas (`consola.titulo_capa("salvapantallas", texto, 10)`;
prioridades de patata: alarma 60, juego 50, baile 20, salvapantallas 10). Con una
consola sin capas se usa `titulo(texto)` y, al volver, `restaurar_titulo()` si se
dio (patata: `_poner_titulo`).

    s = SalvapantallasTerminal(consola, config, en_juego=lambda: patata._juego_activo)
    s.iniciar() ... s.detener()
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

from nucleo import pantalla_grande as pg
from servicios import win_entrada as we

_log = logging.getLogger("lune.salvapantallas")

CAPA = "salvapantallas"
PRIORIDAD = 10
CARA = "(-_-) zzZ"
INTERVALO_S = 1.0


class SalvapantallasTerminal:
    """El título de la consola como salvapantallas (ver el docstring del módulo)."""

    def __init__(self, consola: Any, config: Any, *, api: Any = None,
                 en_juego: Callable[[], bool] = lambda: False,
                 reloj: Callable[[], float] = time.monotonic,
                 hora: Callable[[], datetime] = datetime.now,
                 restaurar_titulo: Optional[Callable[[], None]] = None,
                 intervalo_s: float = INTERVALO_S):
        self.consola = consola
        self.config = config
        self._api = api
        self._en_juego = en_juego
        self._reloj = reloj
        self._hora = hora
        self._restaurar = restaurar_titulo
        self._intervalo = max(0.05, float(intervalo_s))
        self._activo = False
        self._texto = ""
        self._previo = 0.0
        self._ultima_actividad = reloj()
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── Ciclo de vida ────────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        with self._lock:
            if self._hilo is not None:
                return
            self._parar.clear()
            self._ultima_actividad = self._reloj()
            self._hilo = threading.Thread(target=self._bucle, name="lune-salvapantallas", daemon=True)
            self._hilo.start()

    def detener(self) -> None:
        with self._lock:
            hilo, self._hilo = self._hilo, None
        self._parar.set()
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(timeout=2.0)
        if self._activo:
            self._salir()

    @property
    def activo(self) -> bool:
        return self._activo

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                self.tic()
            except Exception:
                _log.exception("salvapantallas de la terminal: el tic falló")
            self._parar.wait(self._intervalo)

    # ── Un paso ──────────────────────────────────────────────────────────────────
    def tic(self) -> bool:
        """Mira la inactividad una vez. → ¿está puesto el salvapantallas?"""
        activo_cfg = bool(self._cfg("activo", False))
        juego = self._juego()
        if not activo_cfg or juego:
            if self._activo:
                self._salir()
            return False
        ahora = self._reloj()
        if self._mando():
            self._ultima_actividad = ahora
        inactivo = min(self._segundos_inactivo(), max(0.0, ahora - self._ultima_actividad))
        if self._activo:
            if inactivo + 0.5 < self._previo:          # hubo entrada: la marca volvió a cero
                self._ultima_actividad = ahora
                self._salir()
                self._previo = inactivo
                return False
            self._previo = inactivo
            texto = self.texto()
            if texto != self._texto:                     # cambió el minuto
                self._poner(texto)
            return True
        self._previo = inactivo
        if inactivo < pg.segundos(self._cfg("paso", 0)):
            return False
        if self._pantalla_requerida():
            return False
        self._activo = True
        self._poner(self.texto())
        return True

    def texto(self) -> str:
        """«(-_-) zzZ 23:41» (o sin la hora)."""
        if not self._cfg("reloj", True):
            return CARA
        try:
            return f"{CARA} {self._hora().strftime('%H:%M')}"
        except Exception:
            return CARA

    # ── Título ───────────────────────────────────────────────────────────────────
    def _poner(self, texto: str) -> None:
        self._texto = texto
        capa = getattr(self.consola, "titulo_capa", None)
        try:
            if callable(capa):
                capa(CAPA, texto, PRIORIDAD)
            else:
                self.consola.titulo(texto)
        except Exception:
            _log.debug("salvapantallas de la terminal: no pude poner el título", exc_info=True)

    def _salir(self) -> None:
        self._activo = False
        self._texto = ""
        capa = getattr(self.consola, "titulo_capa", None)
        try:
            if callable(capa):
                capa(CAPA, None, PRIORIDAD)
            elif callable(self._restaurar):
                self._restaurar()
            else:
                self.consola.titulo("Lune · patata")
        except Exception:
            _log.debug("salvapantallas de la terminal: no pude quitar el título", exc_info=True)

    # ── Lecturas ─────────────────────────────────────────────────────────────────
    def _cfg(self, clave: str, defecto: Any) -> Any:
        try:
            if isinstance(self.config, dict):
                return self.config.get("salvapantallas", {}).get(clave, defecto)
            return self.config.get("salvapantallas", clave, defecto)
        except Exception:
            return defecto

    def _juego(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _segundos_inactivo(self) -> float:
        try:
            return float(we.segundos_inactivo(self._api))
        except Exception:
            return 0.0

    def _mando(self) -> bool:
        try:
            return bool(we.mando_activo(self._api))
        except Exception:
            return False

    def _pantalla_requerida(self) -> bool:
        try:
            return bool(we.pantalla_requerida(self._api))
        except Exception:
            return False


__all__ = ("SalvapantallasTerminal", "CAPA", "PRIORIDAD", "CARA")
