"""
ui/audio_prueba.py — «Probar micrófono» sin congelar la interfaz.

Graba ~1.5 s del micrófono elegido en un hilo y devuelve cuánto se oyó. Lo usan
los dos paneles de ajustes (web y nativo): pulsas el botón, hablas, y Lune te
dice si te oye y con qué nivel. Es la forma rápida de saber si elegiste el
micrófono correcto antes de lanzarte a dictar o a una llamada.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QThread, pyqtSignal


class ProbadorMic(QThread):
    """Emite `listo(json)` con {ok, nivel, pico, nombre, sr, error, mensaje}."""
    listo = pyqtSignal(str)

    def __init__(self, dispositivo=None, segundos: float = 1.5, parent=None):
        super().__init__(parent)
        self.dispositivo = dispositivo
        self.segundos = segundos

    def run(self):
        from servicios import voz_entrada
        try:
            r = voz_entrada.probar_microfono(self.dispositivo, self.segundos)
        except Exception as e:
            r = {"ok": False, "nivel": 0, "pico": 0, "nombre": "", "sr": 0, "error": str(e)}
        r["mensaje"] = mensaje_prueba(r)
        self.listo.emit(json.dumps(r, ensure_ascii=False))


def mensaje_prueba(r: dict) -> str:
    """Una frase para el usuario a partir del resultado de la prueba."""
    if r.get("error"):
        return f"No pude abrir el micrófono: {r['error']}"
    nombre = r.get("nombre") or "micrófono"
    pico = float(r.get("pico") or 0)
    if r.get("ok"):
        fuerza = "fuerte y claro" if pico > 0.08 else "bien" if pico > 0.03 else "flojito"
        return f"Te oigo {fuerza} por «{nombre}» (pico {pico:.2f})."
    return (f"No oí nada por «{nombre}». ¿Es el micrófono correcto? ¿Está silenciado en "
            "Windows o el headset apagado?")
