import json
import os
from pathlib import Path
from typing import Any, Dict

class Config:
    """Gestor de configuración para Lune CD"""
    
    DEFAULT_CONFIG = {
        # ===== IA =====
        "ai": {
            "provider": "groq",  # groq, ollama, openai
            "groq": {
                "api_key": "",
                "model": "mixtral-8x7b-32768"
            },
            "ollama": {
                "url": "http://localhost:11434",
                "model": "mistral"
            },
            "openai": {
                "api_key": "",
                "model": "gpt-4"
            }
        },
        
        # ===== INTERFAZ =====
        "ui": {
            "theme": "light",  # dark, light
            "language": "es",  # es, en
            "window_width": 900,
            "window_height": 700,
            "always_on_top": False,
            "start_minimized": False,
            "show_tray_icon": True,
            "font_size": 13,
        },
        
        # ===== AGENTES =====
        "agents": {
            "writer": {
                "enabled": True,
                "auto_save": True,
                "save_path": "./documents"
            },
            "researcher": {
                "enabled": True,
                "search_depth": "medium",
                "max_sources": 5
            },
            "automation": {
                "enabled": True,
                "safety_mode": True
            }
        },
        
        # ===== COMPORTAMIENTO =====
        "behavior": {
            "auto_respond": False,
            "show_typing_indicator": True,
            "response_timeout": 30,
            "history_limit": 100,
            "auto_clear_chat": False,
            "chat_clear_after_hours": 24
        },
        
        # ===== DIRECTORIOS =====
        "paths": {
            "documents": "./documents",
            "downloads": "./downloads",
            "cache": "./cache",
            "logs": "./logs"
        }
    }
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_or_create()
        self._ensure_directories()
    
    def _load_or_create(self) -> Dict[str, Any]:
        """Cargar configuración existente o crear una nueva"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Fusionar con defaults para nuevas opciones
                    return self._merge_defaults(loaded)
            except Exception as e:
                print(f"⚠️  Error cargando config: {e}. Usando defaults...")
        
        # Crear nueva configuración
        self.save()
        return self.DEFAULT_CONFIG.copy()
    
    def _merge_defaults(self, loaded: Dict) -> Dict:
        """Fusionar config cargada con defaults"""
        def merge(default, loaded):
            result = default.copy()
            for key, value in loaded.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        return merge(self.DEFAULT_CONFIG, loaded)
    
    def _ensure_directories(self):
        """Crear directorios necesarios"""
        for key, path in self.config.get("paths", {}).items():
            Path(path).mkdir(parents=True, exist_ok=True)
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """Obtener valor de configuración"""
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return value if value is not None else default
    
    def set(self, *keys: str, value: Any) -> None:
        """Establecer valor de configuración"""
        if not keys:
            return
        
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self.save()
    
    def save(self) -> None:
        """Guardar configuración a archivo"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")
    
    def reset_to_defaults(self) -> None:
        """Restaurar configuración por defecto"""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
    
    def __repr__(self) -> str:
        return f"<Config: {self.config_path}>"