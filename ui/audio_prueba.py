"""
ui/audio_prueba.py — «Probar micrófono» y «Probar dictado» sin congelar la interfaz.

ProbadorMic graba ~1.5 s del micrófono elegido en un hilo y devuelve cuánto se oyó. Lo
usan los dos paneles de ajustes (web y nativo): pulsas el botón, hablas, y Lune te
dice si te oye y con qué nivel. Es la forma rápida de saber si elegiste el
micrófono correcto antes de lanzarte a dictar o a una llamada.

ProbadorDictado hace el dictado de verdad: graba ~3 s (servicios/voz_entrada.Grabadora)
y lo transcribe con Whisper (voz_entrada.transcribir, lo mismo que el micrófono del
chat). La primera vez descarga el modelo (~145 MB el «base»): lo avisa antes. Sirve
además para probar el dictado en el .exe. Emite `progreso(json)` en cada paso:
    {fase: grabando|descargando|transcribiendo|listo|error, ok, texto, mensaje}
(ok None mientras va; listo/error lo traen True o False). `parar()` corta la grabación;
la transcripción no se puede cortar (quien lo cierra lo retiene hasta que acabe:
ui/cambio_interfaz.soltar_hilos).
"""
from __future__ import annotations

import json
import threading

from PyQt6.QtCore import QThread, pyqtSignal

SEGUNDOS_DICTADO = 3.0


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


def aviso_descarga(modelo: str) -> str:
    """«La primera vez descargo el modelo…» (vacío si ya está bajado o no se puede saber)."""
    from servicios import pruebas, voz_entrada
    try:
        if voz_entrada.modelo_descargado(modelo):
            return ""
    except Exception:
        return ""
    mb = pruebas.WHISPER_MB.get(str(modelo))
    peso = f" (~{mb} MB)" if mb else ""
    return (f"La primera vez descargo el modelo «{modelo}»{peso}: necesita internet y tarda un poco "
            "(un par de minutos).")


class ProbadorDictado(QThread):
    """Graba `segundos` del micrófono y lo transcribe con Whisper; emite `progreso(json)`."""
    progreso = pyqtSignal(str)

    def __init__(self, dispositivo=None, modelo: str = "base", idioma: str = "es",
                 segundos: float = SEGUNDOS_DICTADO, parent=None):
        super().__init__(parent)
        self.dispositivo = dispositivo
        self.modelo = str(modelo or "base")
        self.idioma = idioma
        self.segundos = float(segundos)
        self._parar = threading.Event()

    def parar(self) -> None:
        """Corta la grabación ya (lo grabado hasta ahí se transcribe si llega a ~0.4 s)."""
        self._parar.set()

    def _emitir(self, fase: str, ok=None, texto: str = "", mensaje: str = "") -> None:
        self.progreso.emit(json.dumps({"fase": fase, "ok": ok, "texto": texto, "mensaje": mensaje},
                                      ensure_ascii=False))

    def run(self):
        from servicios import voz_entrada
        from nucleo import rutas
        faltan = voz_entrada.dependencias_faltantes()
        if faltan:
            self._emitir("error", False, mensaje=f"El dictado necesita {', '.join(faltan)} "
                                                 f"({rutas.como_instalar(*faltan)}).")
            return
        descarga = aviso_descarga(self.modelo)
        try:
            grab = voz_entrada.Grabadora(self.dispositivo)
            grab.iniciar()
        except Exception as e:
            self._emitir("error", False, mensaje=f"No pude abrir el micrófono: {e}")
            return
        self._emitir("grabando", None, mensaje=f"Grabando {self.segundos:g} s: dime una frase."
                                                + (f" {descarga}" if descarga else ""))
        self._parar.wait(self.segundos)
        try:
            ruta = grab.detener()
        except Exception:
            ruta = None
        if not ruta:
            self._emitir("error", False, mensaje="No grabé nada: ¿el micrófono está silenciado o es otro?")
            return
        if descarga:
            self._emitir("descargando", None, mensaje=f"Descargando el modelo «{self.modelo}» (solo esta vez) "
                                                      "y transcribiendo…")
        else:
            self._emitir("transcribiendo", None, mensaje="Transcribiendo…")
        try:
            texto = (voz_entrada.transcribir(ruta, self.modelo, self.idioma) or "").strip()
        except Exception as e:
            self._emitir("error", False, mensaje=str(e) or "No pude transcribir.")
            return
        if texto:
            self._emitir("listo", True, texto[:500], f"Te entendí: «{texto[:200]}». El dictado funciona.")
        else:
            self._emitir("listo", False, "", "No entendí nada: habla un poco más fuerte o prueba otro micrófono.")
