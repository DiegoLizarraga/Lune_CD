"""
red_service.py — La presencia de este Lune en la red local.

Anuncia este dispositivo por mDNS (con su rol y capacidades) y descubre a los
demás, para poder elegir cuál aloja el modelo. Traduce el "rol" amable
(host/interacción/híbrido) al mecanismo de transporte (hub.modo: host/terminal/
local) de datos.json.

    host        → sirve el modelo/memoria/voz: hub.modo = host
    interaccion → chat y avatar usando otro equipo: hub.modo = terminal
    hibrido     → todo aquí: hub.modo = local

El anuncio (red.anunciar, apagado de serie desde la 11.3) nunca va en el hilo de Qt:
importar zeroconf son ~0,6 s y register_service espera al sondeo mDNS (1–2 s), así
que `anunciar()` y `reanunciar()` leen aquí lo que hace falta (nombre, rol, puerto,
capacidades) y el resto lo hace un hilo. Uno a la vez y por generaciones: si llega
otro anuncio o `detener()` mientras uno arranca, el viejo se retira al terminar.
"""
from __future__ import annotations

import threading
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
        self._lock = threading.RLock()
        self._gen = 0                     # sube con cada anuncio y con detener()
        self._hilo: Optional[threading.Thread] = None

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
        # ¿tiene avatar VRM disponible? En la carpeta de modelos de verdad (nucleo.vrm),
        # no en un «modelo_vrm» relativo al directorio de trabajo.
        try:
            from nucleo import vrm
            if vrm.CARPETA.exists() and any(vrm.CARPETA.glob("*.vrm")):
                caps["vrm"] = "1"
        except Exception:
            pass
        return caps

    # ── Anuncio ────────────────────────────────────────────────────────────────
    def anunciar(self) -> bool:
        """Se anuncia en la LAN en un hilo (nunca bloquea a quien llama). False si no
        toca (red.anunciar apagado o sin zeroconf)."""
        if not self.config.get("red", "anunciar", False):
            return False
        if not D.zeroconf_disponible():
            from nucleo import rutas
            log_info(f"[red] zeroconf no instalado: este equipo no se anuncia ({rutas.como_instalar('zeroconf')})")
            return False
        nombre, rol, puerto, caps = self.nombre(), self.rol(), datos.hub_puerto(), self.capacidades()
        with self._lock:
            self._gen += 1
            gen = self._gen
            viejo, self._anuncio = self._anuncio, None
        self._lanzar(self._anunciar_en_hilo, gen, viejo, nombre, rol, puerto, caps)
        return True

    def _lanzar(self, fn, *args) -> None:
        self._hilo = threading.Thread(target=fn, args=args, name="lune-red-anuncio", daemon=True)
        self._hilo.start()

    def _anunciar_en_hilo(self, gen, viejo, nombre, rol, puerto, caps) -> None:
        if viejo is not None:
            viejo.detener()
        anuncio = D.AnuncioLune(nombre, rol, puerto, caps)
        ok = anuncio.iniciar()
        with self._lock:
            vigente = gen == self._gen
            if ok and vigente:
                self._anuncio = anuncio
        if ok and not vigente:                 # llegó otro anuncio o detener() mientras arrancaba
            anuncio.detener()
            return
        if ok:
            log_info(f"[red] anunciado como «{nombre}» ({rol})")

    def reanunciar(self):
        """Tras cambiar el rol o el modelo, refresca el anuncio (en un hilo)."""
        with self._lock:
            actual = self._anuncio
        if actual is None:
            self.anunciar()
            return
        rol, caps = self.rol(), self.capacidades()
        self._lanzar(actual.actualizar, rol, caps)

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
        """Retira el anuncio (al salir: aquí mismo, para que no quede publicado). Uno que
        aún esté arrancando en su hilo se retira solo al terminar."""
        with self._lock:
            self._gen += 1
            anuncio, self._anuncio = self._anuncio, None
        if anuncio is not None:
            anuncio.detener()
