"""
red_service.py — La presencia de este Lune en la red local.

Anuncia este dispositivo por mDNS (con su rol y capacidades) y descubre a los
demás, para poder elegir cuál aloja el modelo. Traduce el "rol" amable
(host/interacción/híbrido) al mecanismo de transporte (hub.modo: host/terminal/
local) de datos.json.

    host        → sirve el modelo/memoria/voz: hub.modo = host
    interaccion → chat y avatar usando otro equipo: hub.modo = terminal
    hibrido     → todo aquí: hub.modo = local
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from nucleo import datos

from nucleo.utils import log_info, log_error
from lune_core import descubrimiento as D


def rol_a_modo(rol: str) -> str:
    return {D.ROL_HOST: "host", D.ROL_INTERACCION: "terminal",
            D.ROL_HIBRIDO: "local"}.get(rol, "local")


def modo_a_rol(modo: str) -> str:
    return {"host": D.ROL_HOST, "terminal": D.ROL_INTERACCION,
            "local": D.ROL_HIBRIDO}.get(modo, D.ROL_HIBRIDO)


class BuscarWorker(QThread):
    listo = pyqtSignal(object)     # List[DispositivoLune]

    def __init__(self, timeout: float, excluir_puerto: Optional[int]):
        super().__init__()
        self.timeout = timeout
        self.excluir_puerto = excluir_puerto

    def run(self):
        try:
            self.listo.emit(D.buscar_dispositivos(self.timeout, self.excluir_puerto))
        except Exception as e:
            log_error(f"[red] búsqueda falló: {e}")
            self.listo.emit([])


class RedService(QObject):
    dispositivos = pyqtSignal(object)   # resultado de una búsqueda

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._anuncio = None
        self._worker = None

    # ── Identidad de este equipo ───────────────────────────────────────────────
    def rol(self) -> str:
        r = str(self.config.get("red", "rol", D.ROL_HIBRIDO))
        return r if r in D.ROLES else D.ROL_HIBRIDO

    def nombre(self) -> str:
        return str(self.config.get("red", "nombre", "") or D.nombre_por_defecto())

    def capacidades(self) -> dict:
        """Qué ofrece este equipo, para que los demás lo vean."""
        caps = {}
        modelo = datos.ollama_model()
        if modelo and self.rol() in (D.ROL_HOST, D.ROL_HIBRIDO):
            caps["modelo"] = modelo
        # ¿tiene avatar VRM disponible? (hoy sprites; VRM cuando exista)
        try:
            from pathlib import Path
            if any(Path("modelo_vrm").glob("*.vrm")) if Path("modelo_vrm").exists() else False:
                caps["vrm"] = "1"
        except Exception:
            pass
        return caps

    # ── Anuncio ────────────────────────────────────────────────────────────────
    def anunciar(self):
        if not self.config.get("red", "anunciar", True):
            return
        if not D.zeroconf_disponible():
            log_info("[red] zeroconf no instalado: este equipo no se anuncia (pip install zeroconf)")
            return
        self.detener()
        self._anuncio = D.AnuncioLune(self.nombre(), self.rol(),
                                      datos.hub_puerto(), self.capacidades())
        if self._anuncio.iniciar():
            log_info(f"[red] anunciado como «{self.nombre()}» ({self.rol()})")
        else:
            self._anuncio = None

    def reanunciar(self):
        """Tras cambiar el rol o el modelo, refresca el anuncio."""
        if self._anuncio is not None:
            self._anuncio.actualizar(self.rol(), self.capacidades())
        else:
            self.anunciar()

    # ── Descubrimiento ─────────────────────────────────────────────────────────
    def buscar(self, timeout: float = 3.0):
        if not D.zeroconf_disponible():
            self.dispositivos.emit([])
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = BuscarWorker(timeout, datos.hub_puerto())
        self._worker.listo.connect(self.dispositivos.emit)
        self._worker.start()

    # ── Elegir host ────────────────────────────────────────────────────────────
    def usar_como_host(self, disp: "D.DispositivoLune"):
        """
        Este equipo pasa a INTERACCIÓN y apunta al dispositivo dado como host.
        Escribe el modo/URL en datos.json (el token se pide aparte).
        """
        d = datos.cargar()
        h = d.setdefault("hub", {})
        h["modo"] = "terminal"
        h["url_host"] = disp.url_hub
        datos.guardar(d)
        self.config.set("red", "rol", D.ROL_INTERACCION)

    def detener(self):
        if self._anuncio is not None:
            self._anuncio.detener()
            self._anuncio = None
