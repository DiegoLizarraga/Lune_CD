"""
ui/discord_qt.py — La presencia de Discord en la app (web y nativa).

`ControlDiscord` es un controlador de `ServiciosEscritorio` (ui/escritorio.py):
lo registra el montaje (`("discord", d)`, sin actividades de la tabla) y recibe
`iniciar`, `detener` y `set_mascota` como los demás.

- Escucha `escritorio.estado_cambio` (hilo de Qt) y guarda una FOTO del estado
  (los campos del BusEstado + el modo del anfitrión + el nombre del modelo si
  `discord.mostrar_modelo`). El hilo «LuneDiscordRPC» de
  servicios/discord_presencia.Presencia lee esa foto (copia bajo lock): nunca
  toca objetos de Qt ni bloquea este hilo.
- Solo despierta a la presencia cuando cambia algo que se publica (no con cada
  emoción).
- `alternar()` guarda `discord.activo` y enciende o apaga; `recargar_config()`
  (la tarjeta guardó el Application ID, el botón…) vuelve a mirar sin reiniciar:
  en cuanto hay Application ID, conecta (D1).
- `estado()` → {activo, conectado, usuario, error, publicando, sin_id,
  client_id_ok, vista_previa}. `vista_previa` es lo que Discord vería AHORA
  ({details, state} o None con un juego), para la línea «Discord ve: …» de la
  tarjeta aunque todavía no haya conexión. `estado_cambio(str)` lleva ese JSON.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from pathlib import PurePath
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal

from servicios import discord_presencia as dp
from servicios.discord_ipc import ID_OK

_log = logging.getLogger("lune.discord")

# Campos del BusEstado que cambian lo que se publica (la emoción, por ejemplo, no).
CAMPOS_PUBLICADOS = frozenset({
    "render", "visible", "arrastrando", "durmiendo", "pensando", "hablando", "llamada",
    "bailando", "sentada", "grande", "salvapantallas", "alarma", "comiendo", "juego",
})


class ControlDiscord(QObject):
    """Presencia de Discord de la app (ver el docstring del módulo)."""

    estado_cambio = pyqtSignal(str)
    _desde_hilo = pyqtSignal(object)

    def __init__(self, escritorio: Any, config: Any, *, modo: str = "normal", presencia: Any = None,
                 nombre_modelo: Optional[Callable[[], str]] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.escritorio = escritorio
        self.config = config
        self.modo = str(modo or "normal")
        self._nombre_modelo = nombre_modelo
        self._lock = threading.Lock()
        self._foto: dict = {"modo": self.modo}
        self._iniciado = False
        self._conectado_bus = False
        self._mascota = getattr(escritorio, "mascota", None)
        self._presencia = presencia if presencia is not None else dp.Presencia(config, self.foto)
        try:
            self._presencia.estado_fn = self.foto
        except Exception:
            pass
        try:
            self._presencia.on_estado = self._desde_hilo.emit
        except Exception:
            pass
        self._desde_hilo.connect(self._on_estado_presencia, Qt.ConnectionType.QueuedConnection)

    # ── Contrato de controlador ────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        senal = getattr(self.escritorio, "estado_cambio", None)
        if senal is not None and hasattr(senal, "connect"):
            try:
                senal.connect(self._on_bus)
                self._conectado_bus = True
            except (TypeError, RuntimeError):
                self._conectado_bus = False
        self._refrescar_foto()
        self._presencia.habilitar(self.activo)
        self._emitir()

    def detener(self) -> None:
        if not self._iniciado:
            return
        self._iniciado = False
        if self._conectado_bus:
            try:
                self.escritorio.estado_cambio.disconnect(self._on_bus)
            except (TypeError, RuntimeError, AttributeError):
                pass
            self._conectado_bus = False
        try:
            self._presencia.cerrar(timeout=1.0)
        except Exception:
            _log.exception("discord: cerrar la presencia falló")

    def set_mascota(self, v: Any) -> None:
        self._mascota = v
        self._refrescar_foto()
        if self._iniciado and self.activo:
            self._presencia.actualizar()

    def recargar_config(self) -> None:
        """La config cambió (activo, Application ID, mostrar_modelo, botón)."""
        self._refrescar_foto()
        if not self._iniciado:
            return
        self._presencia.habilitar(self.activo)
        self._presencia.actualizar()
        self._emitir()

    # ── Interruptor ────────────────────────────────────────────────────────────
    @property
    def activo(self) -> bool:
        try:
            return bool(self.config.get("discord", "activo", False))
        except Exception:
            return False

    def alternar(self) -> bool:
        """Enciende o apaga la presencia y lo guarda. → el estado nuevo."""
        nuevo = not self.activo
        try:
            self.config.set("discord", "activo", nuevo)
        except Exception:
            _log.exception("discord: no pude guardar discord.activo")
        if self._iniciado:
            self._presencia.habilitar(nuevo)
        self._emitir()
        return nuevo

    def estado(self) -> dict:
        try:
            e = dict(self._presencia.estado())
        except Exception:
            e = {}
        for clave, defecto in (("conectado", False), ("usuario", ""), ("error", ""),
                               ("publicando", None), ("sin_id", False)):
            e.setdefault(clave, defecto)
        e["activo"] = self.activo
        cid = dp.client_id(self.config)
        e["client_id_ok"] = bool(ID_OK.match(cid))
        e["sin_id"] = bool(self.activo and not cid)
        e["vista_previa"] = self.vista_previa()
        return e

    def vista_previa(self) -> Optional[dict]:
        """{details, state} que Discord vería ahora mismo (None: nada, hay un juego)."""
        try:
            act = dp.actividad_de(self.foto(), config=self.config, inicio_ms=0)
        except Exception:
            return None
        if act is None:
            return None
        return {"details": act.get("details", ""), "state": act.get("state", "")}

    # ── Foto del estado (la lee el hilo de la presencia) ───────────────────────
    def foto(self) -> dict:
        with self._lock:
            return dict(self._foto)

    def _refrescar_foto(self, est: Any = None) -> None:
        if est is None:
            bus = getattr(self.escritorio, "estado", None)
            try:
                est = bus.actual() if bus is not None else None
            except Exception:
                est = None
        foto: dict = {}
        if est is not None:
            if dataclasses.is_dataclass(est):
                foto = dataclasses.asdict(est)
            elif isinstance(est, dict):
                foto = dict(est)
        foto["modo"] = self.modo
        foto["modelo"] = self._modelo() if foto.get("render") == "vrm" else ""
        with self._lock:
            self._foto = foto

    def _modelo(self) -> str:
        """Nombre del modelo VRM, solo si el usuario pidió enseñarlo."""
        try:
            if not bool(self.config.get("discord", "mostrar_modelo", False)):
                return ""
        except Exception:
            return ""
        if callable(self._nombre_modelo):
            try:
                return str(self._nombre_modelo() or "")
            except Exception:
                return ""
        try:
            archivo = str(self.config.get("avatar", "vrm_archivo", "") or "")
        except Exception:
            archivo = ""
        return PurePath(archivo.replace("\\", "/")).stem if archivo else ""

    # ── Señales ────────────────────────────────────────────────────────────────
    def _on_bus(self, est: Any, cambios: Any = None) -> None:
        self._refrescar_foto(est)
        if not self._iniciado or not self.activo:
            return
        if isinstance(cambios, dict) and cambios and not (set(cambios) & CAMPOS_PUBLICADOS):
            return
        self._presencia.actualizar()

    def _on_estado_presencia(self, _estado: Any = None) -> None:
        self._emitir()

    def _emitir(self) -> None:
        try:
            self.estado_cambio.emit(json.dumps(self.estado(), ensure_ascii=False))
        except Exception:
            _log.debug("discord: no pude emitir el estado", exc_info=True)


__all__ = ("ControlDiscord", "CAMPOS_PUBLICADOS")
