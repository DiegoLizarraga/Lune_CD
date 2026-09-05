"""
config.py — Preferencias locales de Lune CD (config.json).

Regla de la casa: aquí SOLO viven claves que algún módulo lee de verdad.
Antes había 14 que no leía nadie (`ui`, `behavior`, `paths` enteras): daban
la falsa impresión de ser configurables y editarlas no hacía nada. Si añades
una clave nueva, añade también el código que la usa — o no la añadas.

Las APIs, modelos y personalidad viven en datos.json (ver datos.py).
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict


class Config:
    """Gestor de preferencias y toggles de rendimiento."""

    DEFAULT_CONFIG = {
        # Activa/desactiva funciones para ajustar rendimiento y consumo.
        "features": {
            "respuestas_predeterminadas": True,  # respuestas instantáneas sin IA
            "animaciones_video": True,           # caras .mp4 (cuesta CPU/GPU)
            "fondo_estrellas": True,             # splash animado al iniciar
            "voz_auto": False,                   # leer en voz alta cada respuesta
            "efectos_hover": True,               # microanimaciones en la UI
            "streaming_tokens": True,            # mostrar respuesta letra por letra
            "minimizar_a_bandeja": True,         # al cerrar, ocultar en la bandeja
            "acciones_ia": True,                 # dejar que la IA abra webs y lance apps
            "markdown": True,                    # formatear negritas, listas y código
            "guardar_conversaciones": True,      # historial de chats en disco
            "contador_tokens": True,             # mostrar tokens y costo por respuesta
            "emociones": True,                   # la IA emite <|ACT|> y la cara reacciona
        },
        # Avatar/expresiones: permite cambiar el "modelo" visual de Lune.
        "avatar": {
            "pack": "default",                   # carpeta lune_face/ por defecto
        },
        # Optimizador estilo Stacer: qué categorías limpiar por defecto.
        "optimizador": {
            "categorias_activas": [
                "temp_usuario", "temp_windows", "miniaturas", "cache_navegadores",
            ],
            "confirmar_antes_de_limpiar": True,
        },
        # Historial de conversaciones (ver conversaciones.py).
        "chat": {
            "max_sesiones": 50,                  # cuántas conversaciones se conservan
            "restaurar_ultima": True,            # reabrir la última al arrancar
        },
        # Adjuntos: documentos e imágenes (ver adjuntos.py).
        "adjuntos": {
            "max_caracteres": 20000,             # texto máximo por documento
        },
        # Voz de entrada con Whisper (ver voz_entrada.py).
        "voz": {
            "modelo_whisper": "base",            # tiny · base · small · medium · large-v3
            "idioma": "es",
        },
        # Actualizaciones por git (ver actualizador.py).
        "actualizaciones": {
            "rama": "master",
            "comprobar_al_iniciar": False,
        },
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = self._merge_defaults(loaded, self.DEFAULT_CONFIG)
                # Persistir si el esquema cambió (secciones nuevas o claves podadas)
                if merged != loaded:
                    self._save_config(merged)
                return merged
            except Exception:
                pass
        # copy() era superficial: las secciones anidadas quedaban compartidas
        # con DEFAULT_CONFIG y set_feature() mutaba los valores por defecto.
        inicial = copy.deepcopy(self.DEFAULT_CONFIG)
        self._save_config(inicial)
        return inicial

    def _save_config(self, data: dict):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def save(self):
        self._save_config(self.config)

    # ── Acceso cómodo a features ───────────────────────────────────────────────
    def feature(self, nombre: str, default: bool = True) -> bool:
        """Devuelve si una función está activada (sección 'features')."""
        return bool(self.config.get("features", {}).get(nombre, default))

    def set_feature(self, nombre: str, valor: bool):
        self.config.setdefault("features", {})[nombre] = bool(valor)
        self.save()

    def get(self, seccion: str, clave: str, default=None):
        return self.config.get(seccion, {}).get(clave, default)

    def set(self, seccion: str, clave: str, valor):
        self.config.setdefault(seccion, {})[clave] = valor
        self.save()

    # ── Fusión con los valores por defecto ─────────────────────────────────────
    def _merge_defaults(self, loaded: Dict, default: Dict) -> Dict:
        """
        Conserva lo que el usuario configuró y añade las claves nuevas.

        PODA las claves que ya no existen en DEFAULT_CONFIG: así las secciones
        muertas desaparecen solas del config.json de quien viene de una versión
        anterior, en vez de quedarse ahí engañando.
        """
        result = copy.deepcopy(default)
        for key, value in loaded.items():
            if key not in default:
                continue  # clave obsoleta → se descarta
            if isinstance(default[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(value, default[key])
            else:
                result[key] = value
        return result
