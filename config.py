import json
from pathlib import Path
from typing import Any, Dict

class Config:
    """Gestor de configuración visual para Lune CD"""

    DEFAULT_CONFIG = {
        "ui": {
            "theme": "dark", "language": "es", "window_width": 1100,
            "window_height": 760, "always_on_top": False,
            "start_minimized": False, "show_tray_icon": True, "font_size": 13,
        },
        "behavior": {
            "auto_respond": False, "show_typing_indicator": True,
            "response_timeout": 60, "history_limit": 100,
            "auto_clear_chat": False, "chat_clear_after_hours": 24,
        },
        "paths": {
            "documents": "./documents", "downloads": "./downloads",
            "cache": "./cache", "logs": "./logs",
        },
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_or_create()
        self._ensure_directories()

    def _load_or_create(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return self._merge_defaults(loaded, self.DEFAULT_CONFIG)
            except Exception: pass
        self._save_config(self.DEFAULT_CONFIG.copy())
        return self.DEFAULT_CONFIG.copy()

    def _save_config(self, data: dict):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e: print(f"Error guardando config: {e}")

    def save(self):
        self._save_config(self.config)

    def _merge_defaults(self, loaded: Dict, default: Dict) -> Dict:
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(value, result[key])
            else: result[key] = value
        return result

    def _ensure_directories(self):
        for path in self.config.get("paths", {}).values():
            Path(path).mkdir(parents=True, exist_ok=True)