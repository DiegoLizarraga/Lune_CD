"""utils.py — Logging de Lune: un archivo diario en logs/ y salida por consola.

logs/ vive en la carpeta local (rutas.LOCAL: la raíz del repo desde el código,
%LOCALAPPDATA%\\Lune CD instalada). La app y patata escriben a la vez en el mismo
archivo del día, así que:
- Cada día es un archivo nuevo (lune_AAAAMMDD.log) y el cambio de día lo hace el
  propio handler al escribir. Nada de TimedRotatingFileHandler: rota RENOMBRANDO el
  archivo y en Windows eso falla si el otro proceso lo tiene abierto.
- Al arrancar se borran los lune_*.log de más de DIAS_LOGS días y, si aun así la
  carpeta pasa de MAX_BYTES_LOGS, los más viejos. El de hoy nunca.
- Sin consola (Lune.exe, pythonw) sys.stderr es None: no se añade el StreamHandler.
- Instalada, el archivo guarda desde INFO; desde el código, desde DEBUG como siempre.
"""
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from nucleo import rutas

PREFIJO_LOG = "lune_"
DIAS_LOGS = 14
MAX_BYTES_LOGS = 20 * 1024 * 1024


def carpeta_logs() -> Path:
    """Dónde van los logs (sin crearla)."""
    return rutas.local("logs")


class ArchivoDiarioHandler(logging.Handler):
    """Escribe en <carpeta>/<prefijo>AAAAMMDD.log según el día de cada registro.

    Abre en modo «a» y, cuando llega un registro de otro día, cierra el archivo y
    abre el nuevo. No renombra nunca: dos procesos pueden escribir en el mismo."""

    def __init__(self, carpeta, prefijo: str = PREFIJO_LOG, encoding: str = "utf-8"):
        super().__init__()
        self.carpeta = Path(carpeta)
        self.prefijo = prefijo
        self.encoding = encoding
        self.fecha: Optional[str] = None
        self._stream = None

    def ruta_de(self, fecha: str) -> Path:
        return self.carpeta / f"{self.prefijo}{fecha}.log"

    @property
    def ruta_actual(self) -> Optional[Path]:
        return self.ruta_de(self.fecha) if self.fecha else None

    def _cerrar_archivo(self):
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None

    def _abrir(self, fecha: str):
        self._cerrar_archivo()
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._stream = open(self.ruta_de(fecha), "a", encoding=self.encoding)
        self.fecha = fecha

    def emit(self, record: logging.LogRecord):
        try:
            mensaje = self.format(record)
            fecha = datetime.fromtimestamp(record.created).strftime("%Y%m%d")
            if self._stream is None or fecha != self.fecha:
                self._abrir(fecha)
            self._stream.write(mensaje + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        self.acquire()
        try:
            self._cerrar_archivo()
        finally:
            self.release()
        super().close()


def limpiar_logs(carpeta, *, dias: int = DIAS_LOGS, max_bytes: int = MAX_BYTES_LOGS,
                 ahora: Optional[float] = None, prefijo: str = PREFIJO_LOG) -> List[Path]:
    """Borra los <prefijo>*.log de más de `dias` días y, si lo que queda pasa de
    `max_bytes`, los más viejos hasta bajar de ahí. El del día de hoy no se toca.
    Devuelve los borrados. Nunca lanza (un log abierto por otro proceso se queda)."""
    carpeta = Path(carpeta)
    ahora = time.time() if ahora is None else ahora
    hoy = f"{prefijo}{datetime.fromtimestamp(ahora).strftime('%Y%m%d')}.log"
    try:
        archivos = list(carpeta.glob(f"{prefijo}*.log"))
    except OSError:
        return []
    total = 0
    candidatos = []
    for ruta in archivos:
        try:
            if not ruta.is_file():
                continue
            st = ruta.stat()
        except OSError:
            continue
        total += st.st_size
        if ruta.name != hoy:
            candidatos.append((st.st_mtime, st.st_size, ruta))
    candidatos.sort()                                   # los más viejos primero
    limite = ahora - dias * 86400
    borrados: List[Path] = []
    for mtime, tam, ruta in candidatos:
        if mtime >= limite and total <= max_bytes:
            continue
        try:
            ruta.unlink()
        except OSError:
            continue
        total -= tam
        borrados.append(ruta)
    return borrados


class Logger:
    """Logger único (singleton) a archivo diario y a consola."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, name: str = "lune"):
        if hasattr(self, '_initialized'):
            return

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []

        # Carpeta de logs anclada a rutas (no al directorio de trabajo): lanzando la
        # app desde otra carpeta los logs acababan dispersos.
        logs_dir = carpeta_logs()
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            limpiar_logs(logs_dir)
        except OSError:
            pass

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

        file_handler = ArchivoDiarioHandler(logs_dir)
        file_handler.setLevel(logging.INFO if rutas.INSTALADA else logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Sin consola (Lune.exe, pythonw) no hay stderr al que escribir.
        if sys.stderr is not None:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        self._initialized = True

    def debug(self, msg: str):
        self.logger.debug(msg)

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)


# Instancia global del logger
logger = Logger()


def log_info(msg: str):
    logger.info(msg)


def log_error(msg: str):
    logger.error(msg)
