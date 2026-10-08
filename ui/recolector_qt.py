"""
ui/recolector_qt.py — La basura con ciclos se recoge en el hilo de Qt, nunca en otro.

POR QUÉ
-------
El recolector automático de Python salta dentro del hilo que esté reservando memoria en
ese momento, sea cual sea. Lune tiene muchos hilos de Python (el vigilante de la voz, el
detector de música, los sondeos, el diagnóstico, las actualizaciones…) y la basura con
ciclos suele llevar objetos de Qt: una ventana o un diálogo cerrados cuyos botones apuntan
a lambdas que apuntan a la propia ventana. Si esa basura se recoge en uno de esos hilos,
Qt destruye widgets fuera de su hilo y el proceso muere sin aviso (0xC0000409). Lo vimos
en los tests de GitHub Actions en la 10.9 y en la 11.3 (test_pruebas_qt: el panel de un
test se recogía dentro del hilo del diagnóstico del siguiente).

El código ya evitaba los gc.collect() a mano fuera del hilo de Qt (servicios/recorte_ram,
voz_entrada.soltar_modelo, audio_sesiones); esto cierra la puerta que quedaba: el
automático.

CÓMO
----
`iniciar()` apaga el automático (gc.disable) y un QTimer del hilo de Qt mira cada medio
segundo los contadores de gc y recoge lo que habría recogido Python, con sus mismos
umbrales (la generación 0 y, cuando toca, la 1 o la 2). Mirar los contadores no cuesta
nada. `detener()` lo deja como estaba. Solo lo usa main.py (la app de ventanas); patata no
tiene Qt y sigue con el automático.
"""
from __future__ import annotations

import gc
from typing import Any

from PyQt6.QtCore import QObject, QTimer

INTERVALO_MS = 500


class RecolectorQt(QObject):
    """Recoge la basura con ciclos desde el hilo de Qt (el suyo) en vez del automático."""

    def __init__(self, parent=None, *, intervalo_ms: int = INTERVALO_MS, gc_mod: Any = gc):
        super().__init__(parent)
        self._gc = gc_mod
        self._umbral = tuple(gc_mod.get_threshold())
        self._estaba_activo = bool(gc_mod.isenabled())
        self.activo = False
        self._timer = QTimer(self)
        self._timer.setInterval(int(intervalo_ms))
        self._timer.timeout.connect(self.revisar)

    def iniciar(self) -> "RecolectorQt":
        """Apaga el automático y empieza a mirar. Devuelve self."""
        self._gc.disable()
        self._timer.start()
        self.activo = True
        return self

    def detener(self) -> None:
        """Para el temporizador y deja el automático como estaba antes de iniciar()."""
        self._timer.stop()
        if self.activo and self._estaba_activo:
            self._gc.enable()
        self.activo = False

    def revisar(self) -> int:
        """Una pasada: si el automático habría recogido, recoge la generación que toque
        (0, 1 o 2). Devuelve la generación recogida, o -1 si no tocaba."""
        try:
            c0, c1, c2 = self._gc.get_count()[:3]
            u0, u1, u2 = self._umbral[:3]
        except (TypeError, ValueError):
            return -1
        if u0 <= 0 or c0 <= u0:
            return -1
        # Como el automático: la generación más vieja cuyo contador pasó su umbral.
        generacion = 2 if c2 > u2 else (1 if c1 > u1 else 0)
        try:
            self._gc.collect(generacion)
        except Exception:                             # noqa: BLE001 (nunca tumba el temporizador)
            return -1
        return generacion


def instalar(app: Any) -> RecolectorQt:
    """Crea el recolector colgado de `app` (la QApplication), lo arranca y lo devuelve."""
    return RecolectorQt(app).iniciar()


__all__ = ("INTERVALO_MS", "RecolectorQt", "instalar")
