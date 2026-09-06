"""utils.py — Logging de Lune: un archivo diario en logs/ y salida por consola."""
import logging
from pathlib import Path
from datetime import datetime


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

        # Directorio de logs relativo al proyecto, no al directorio de trabajo:
        # lanzando la app desde otra carpeta los logs acababan dispersos.
        logs_dir = Path(__file__).parent.parent / "logs"
        logs_dir.mkdir(exist_ok=True)

        log_file = logs_dir / f"lune_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
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
