import os
import json

class Config:
    def __init__(self):
        self.config_file = "lune_config.json"
        self.default_config = {
            "screen_monitoring": {
                "enabled": True,
                "interval": 60,  # segundos
                "save_screenshots": False
            },
            "notifications": {
                "enabled": True,
                "duration": 5,  # segundos
                "sound": False
            },
            "reminders": {
                "enabled": True,
                "check_interval": 30  # segundos
            },
            "ui": {
                "position": "bottom-left",
                "size": 170,
                "always_on_top": True
            }
        }
        self.config = self.load_config()
    
    def load_config(self):
        """Carga la configuración desde el archivo"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                # Combinar con la configuración por defecto para añadir nuevas opciones
                config = self.default_config.copy()
                config.update(loaded_config)
                return config
            except:
                return self.default_config.copy()
        else:
            self.save_config()
            return self.default_config.copy()
    
    def save_config(self):
        """Guarda la configuración en el archivo"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except:
            return False
    
    def get(self, key, default=None):
        """Obtiene un valor de configuración"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key, value):
        """Establece un valor de configuración"""
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        return self.save_config()