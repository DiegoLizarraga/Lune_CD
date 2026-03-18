import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    """Gestor de configuración para Lune CD"""

    DEFAULT_CONFIG = {
        "ui": {
            "theme": "dark",
            "language": "es",
            "window_width": 1100,
            "window_height": 760,
            "always_on_top": False,
            "start_minimized": False,
            "show_tray_icon": True,
            "font_size": 13,
        },
        "behavior": {
            "auto_respond": False,
            "show_typing_indicator": True,
            "response_timeout": 30,
            "history_limit": 100,
            "auto_clear_chat": False,
            "chat_clear_after_hours": 24,
        },
        "paths": {
            "documents": "./documents",
            "downloads": "./downloads",
            "cache": "./cache",
            "logs": "./logs",
        },
    }

    API_KEYS_FILE = "api_keys.json"

    DEFAULT_KEYS = {
        "_comment": "Guarda aquí tus API keys. Este archivo NO debe subirse a GitHub.",
        "character_ai": {"api_key": ""},
        "deepseek": {"api_key": "", "model": "deepseek-chat"},
        "claude": {"api_key": "", "model": "claude-3-5-haiku-20241022"},
        "ollama": {"url": "http://localhost:11434", "model": "nova"},
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_or_create()
        self.keys = self._load_or_create_keys()
        self._ensure_directories()

    # ── config.json ──────────────────────────────────────────────────────────

    def _load_or_create(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return self._merge_defaults(loaded, self.DEFAULT_CONFIG)
            except Exception as e:
                print(f"⚠️  Error cargando config: {e}. Usando defaults…")
        self._save_config(self.DEFAULT_CONFIG.copy())
        return self.DEFAULT_CONFIG.copy()

    def _save_config(self, data: dict):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def save(self):
        self._save_config(self.config)

    # ── api_keys.json ─────────────────────────────────────────────────────────

    def _load_or_create_keys(self) -> Dict[str, Any]:
        p = Path(self.API_KEYS_FILE)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  Error cargando api_keys: {e}")
        # Crear archivo de ejemplo
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.DEFAULT_KEYS, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error creando api_keys.json: {e}")
        return self.DEFAULT_KEYS.copy()

    def save_keys(self):
        try:
            with open(Path(self.API_KEYS_FILE), "w", encoding="utf-8") as f:
                json.dump(self.keys, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando api_keys.json: {e}")

    def get_key(self, provider: str, field: str = "api_key", default: str = "") -> str:
        return self.keys.get(provider, {}).get(field, default)

    def set_key(self, provider: str, field: str, value: str):
        if provider not in self.keys:
            self.keys[provider] = {}
        self.keys[provider][field] = value
        self.save_keys()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _merge_defaults(self, loaded: Dict, default: Dict) -> Dict:
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(value, result[key])
            else:
                result[key] = value
        return result

    def _ensure_directories(self):
        for path in self.config.get("paths", {}).values():
            Path(path).mkdir(parents=True, exist_ok=True)

    def get(self, *keys: str, default: Any = None) -> Any:
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return value if value is not None else default

    def set(self, *keys: str, value: Any) -> None:
        if not keys:
            return
        cfg = self.config
        for key in keys[:-1]:
            if key not in cfg:
                cfg[key] = {}
            cfg = cfg[key]
        cfg[keys[-1]] = value
        self.save()

    def reset_to_defaults(self):
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()

    def __repr__(self):
        return f"<Config: {self.config_path}>"