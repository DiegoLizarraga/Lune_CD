import os
import sys
import json
import logging
from pathlib import Path
from typing import Any, Optional
from datetime import datetime


class Logger:
    """Sistema de logging mejorado"""
    
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
        
        # Limpiar handlers existentes
        self.logger.handlers = []
        
        # Crear directorio de logs
        Path("logs").mkdir(exist_ok=True)
        
        # Handler de archivo
        log_file = f"logs/lune_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Handler de consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formato
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
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
    
    def critical(self, msg: str):
        self.logger.critical(msg)


# Instancia global del logger
logger = Logger()


class FileManager:
    """Gestor de archivos mejorado"""
    
    @staticmethod
    def ensure_dir(path: str) -> Path:
        """Asegurar que un directorio existe"""
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return p
    
    @staticmethod
    def read_json(path: str) -> dict:
        """Leer archivo JSON"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Archivo no encontrado: {path}")
            return {}
        except json.JSONDecodeError:
            logger.error(f"JSON inválido en: {path}")
            return {}
        except Exception as e:
            logger.error(f"Error leyendo {path}: {e}")
            return {}
    
    @staticmethod
    def write_json(path: str, data: dict) -> bool:
        """Escribir archivo JSON"""
        try:
            FileManager.ensure_dir(os.path.dirname(path) or ".")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error escribiendo {path}: {e}")
            return False
    
    @staticmethod
    def read_file(path: str) -> str:
        """Leer archivo de texto"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error leyendo {path}: {e}")
            return ""
    
    @staticmethod
    def write_file(path: str, content: str) -> bool:
        """Escribir archivo de texto"""
        try:
            FileManager.ensure_dir(os.path.dirname(path) or ".")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Error escribiendo {path}: {e}")
            return False
    
    @staticmethod
    def get_size(path: str) -> str:
        """Obtener tamaño de archivo/directorio"""
        try:
            size = Path(path).stat().st_size
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024:
                    return f"{size:.2f} {unit}"
                size /= 1024
            return f"{size:.2f} PB"
        except:
            return "Desconocido"
    
    @staticmethod
    def file_exists(path: str) -> bool:
        """Verificar si un archivo existe"""
        return Path(path).exists()
    
    @staticmethod
    def delete_file(path: str) -> bool:
        """Eliminar un archivo"""
        try:
            Path(path).unlink()
            return True
        except Exception as e:
            logger.error(f"Error eliminando {path}: {e}")
            return False


class SystemInfo:
    """Información del sistema"""
    
    @staticmethod
    def get_os() -> str:
        """Obtener sistema operativo"""
        if sys.platform == 'win32':
            return "Windows"
        elif sys.platform == 'darwin':
            return "macOS"
        else:
            return "Linux"
    
    @staticmethod
    def get_python_version() -> str:
        """Obtener versión de Python"""
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    @staticmethod
    def get_app_info() -> dict:
        """Obtener información de la app"""
        return {
            "name": "Lune CD",
            "version": "4.5",
            "os": SystemInfo.get_os(),
            "python": SystemInfo.get_python_version(),
            "timestamp": datetime.now().isoformat()
        }


class StringUtils:
    """Utilidades para strings"""
    
    @staticmethod
    def truncate(text: str, length: int = 50) -> str:
        """Truncar texto"""
        if len(text) > length:
            return text[:length] + "..."
        return text
    
    @staticmethod
    def sanitize(text: str) -> str:
        """Sanitizar texto"""
        return text.strip().replace('\n', ' ').replace('\t', ' ')
    
    @staticmethod
    def format_timestamp(dt: datetime = None) -> str:
        """Formatear timestamp"""
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    
    @staticmethod
    def format_time_12h(dt: datetime = None) -> str:
        """Formatear hora en formato 12h"""
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%I:%M %p")
    
    @staticmethod
    def format_time_24h(dt: datetime = None) -> str:
        """Formatear hora en formato 24h"""
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%H:%M:%S")


class ValidationUtils:
    """Validaciones"""
    
    @staticmethod
    def is_valid_api_key(key: str) -> bool:
        """Validar API key"""
        if not key:
            return False
        if len(key) < 10:
            return False
        return True
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validar URL"""
        if not url:
            return False
        return url.startswith(('http://', 'https://'))
    
    @staticmethod
    def is_valid_model_name(name: str) -> bool:
        """Validar nombre de modelo"""
        if not name or len(name) < 2:
            return False
        # Permitir letras, números, guiones y guiones bajos
        return all(c.isalnum() or c in '-_' for c in name)


# Funciones de conveniencia
def log_debug(msg: str):
    logger.debug(msg)

def log_info(msg: str):
    logger.info(msg)

def log_warning(msg: str):
    logger.warning(msg)

def log_error(msg: str):
    logger.error(msg)

def log_critical(msg: str):
    logger.critical(msg)