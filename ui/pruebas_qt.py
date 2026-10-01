"""
ui/pruebas_qt.py — Los «Probar» y «Comprobar que todo funciona» con Qt, sin congelar nada.

  · PruebaWorker(fn): corre `fn()` (una de servicios/pruebas: OpenRouter, Telegram…) en un
    hilo y emite `listo(dict)`. Si fn lanza, {ok: False, mensaje}. Lo usa la nativa
    (ui/settings_panel.py: PROBAR CLAVE, PROBAR BOT).
  · DiagnosticoWorker(red=True): servicios/diagnostico.comprobar en un hilo, con el
    contexto de dentro de la app (diagnostico.contexto_en_app: no carga QtWebEngine ni lo
    del dictado solo para mirarlo). Emite `evento(str)` con JSON: primero {tipo: inicio},
    luego un {tipo: item} por comprobación según sale y al final {tipo: fin} con el
    resumen (diagnostico.evento_*). requestInterruption() lo para antes de la siguiente
    comprobación. Lo usan la tarjeta de la web (la señal `diagnostico` del puente) y el
    diálogo de la nativa.
  · DialogoDiagnostico: el informe de la nativa (COMPROBAR QUE TODO FUNCIONA, en
    Ajustes): la lista por secciones, con bien / mal / no aplica y el detalle, que se va
    pintando según avanza. Al cerrarlo, el hilo se para (y se retiene hasta que acabe:
    una comprobación de red puede tardar unos segundos).

`soltar(hilo)`: para un hilo de estos al cerrar (desconecta sus señales y, si aún corre,
lo retiene hasta que acabe; ui/cambio_interfaz.soltar_hilos).
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

MARCAS = {True: "BIEN", False: "MAL", None: "NO APLICA"}


class PruebaWorker(QThread):
    """`fn()` en un hilo → `listo(dict)` (siempre un dict con ok y mensaje)."""
    listo = pyqtSignal(object)

    def __init__(self, fn: Callable[[], Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            r = self.fn()
        except Exception as e:                       # noqa: BLE001
            r = {"ok": False, "mensaje": f"No pude probarlo ({type(e).__name__})."}
        if not isinstance(r, dict):
            r = {"ok": bool(r), "mensaje": str(r or "")}
        self.listo.emit(r)


class DiagnosticoWorker(QThread):
    """«Comprobar que todo funciona»: emite `evento(json)` (inicio, un item por comprobación, fin)."""
    evento = pyqtSignal(str)

    def __init__(self, red: bool = True, parent=None, *, comprobar: Optional[Callable[..., Any]] = None,
                 contexto: Optional[Callable[[], Any]] = None):
        """`comprobar` y `contexto` son para los tests (sin ellos, los de servicios/diagnostico)."""
        super().__init__(parent)
        self.red = bool(red)
        self._comprobar = comprobar
        self._contexto = contexto
        self.resultado: Optional[Dict[str, Any]] = None

    def _emitir(self, obj: Dict[str, Any]) -> None:
        self.evento.emit(json.dumps(obj, ensure_ascii=False, default=str))

    def run(self):
        from servicios import diagnostico as D
        self._emitir(D.evento_inicio(self.red))
        try:
            ctx = (self._contexto or D.contexto_en_app)()
            r = (self._comprobar or D.comprobar)(self.red, ctx=ctx,
                                                 al_avanzar=lambda i: self._emitir(D.evento_item(i)),
                                                 parar=self.isInterruptionRequested)
        except Exception as e:                       # noqa: BLE001 (no debería: comprobar no lanza)
            r = {"ok": False, "version": "?", "modo": "", "items": [],
                 "error": f"{type(e).__name__}: {e}"}
        self.resultado = r
        fin = D.evento_fin(r)
        if r.get("error"):
            fin["resumen"] = f"No pude terminar la comprobación ({r['error'][:160]})."
        self._emitir(fin)


def soltar(hilo: Any, espera_ms: int = 0) -> None:
    """Para un hilo de estos al cerrar: pide la parada, desconecta sus señales, espera como
    mucho `espera_ms` a que acabe y, si aún corre, lo retiene hasta que acabe."""
    if hilo is None:
        return
    for metodo in ("requestInterruption", "parar"):
        f = getattr(hilo, metodo, None)
        if callable(f):
            try:
                f()
            except RuntimeError:
                pass
    for nombre in ("evento", "progreso", "listo"):
        s = getattr(hilo, nombre, None)
        try:
            s.disconnect()
        except (TypeError, RuntimeError, AttributeError):
            pass
    if espera_ms > 0:
        try:
            hilo.wait(int(espera_ms))
        except (RuntimeError, AttributeError):
            pass
    try:
        from ui.cambio_interfaz import soltar_hilos
        soltar_hilos(hilo)
    except Exception:                                # noqa: BLE001
        pass


# ── El informe de la nativa ──────────────────────────────────────────────────

def _colores() -> Dict[str, str]:
    try:
        from ui.theme import COLORS
        return COLORS
    except Exception:                                # noqa: BLE001
        return {}


class DialogoDiagnostico(QDialog):
    """La lista de comprobaciones de la nativa; arranca sola al abrirse (`iniciar`)."""

    def __init__(self, parent=None, *, red: bool = True, worker: Optional[Callable[..., QThread]] = None):
        """`worker(red, parent)` crea el hilo (los tests pasan uno falso)."""
        super().__init__(parent)
        self.setWindowTitle("Lune · comprobar que todo funciona")
        self.setModal(False)
        self.resize(640, 560)
        self.red = red
        self._fabrica = worker or (lambda red, parent: DiagnosticoWorker(red, parent))
        self._hilo: Optional[QThread] = None
        # El hilo va sin padre: si el diálogo se borra sin cerrarse (se va la ventana), un QThread
        # hijo vivo tumbaría el proceso. Al borrarse, se suelta (sin tocar ya el diálogo).
        caja: Dict[str, Any] = {"h": None}
        self._caja = caja
        self.destroyed.connect(lambda *_: soltar(caja.get("h")))
        self.items: List[Dict[str, Any]] = []
        self.fin: Optional[Dict[str, Any]] = None
        self._seccion = None
        c = _colores()
        self._c = c
        self.setStyleSheet(f"QDialog{{background:{c.get('bg', '#080B16')};}}")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 16, 18, 16)
        raiz.setSpacing(10)
        titulo = QLabel("COMPROBAR QUE TODO FUNCIONA")
        titulo.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        titulo.setStyleSheet(f"color:{c.get('accent', '#00E5FF')};letter-spacing:1px;")
        raiz.addWidget(titulo)
        self.lbl_estado = QLabel("Miro lo que traigo, tus carpetas, tu equipo y los servicios que usas…")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet(f"color:{c.get('text_muted', '#9AA4C0')};")
        raiz.addWidget(self.lbl_estado)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        cont = QWidget()
        self.lista = QVBoxLayout(cont)
        self.lista.setContentsMargins(0, 0, 0, 0)
        self.lista.setSpacing(4)
        self.lista.addStretch(1)
        scroll.setWidget(cont)
        raiz.addWidget(scroll, 1)
        fila = QHBoxLayout()
        self.btn_otra = QPushButton("COMPROBAR OTRA VEZ")
        self.btn_otra.clicked.connect(self.iniciar)
        self.btn_otra.setEnabled(False)
        self.btn_cerrar = QPushButton("CERRAR")
        self.btn_cerrar.clicked.connect(self.close)
        for b in (self.btn_otra, self.btn_cerrar):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(32)
            b.setStyleSheet(f"QPushButton{{background:{c.get('surface2', '#141A2E')};color:{c.get('accent', '#00E5FF')};"
                            f"border:2px solid {c.get('cyan_dark', '#00808F')};border-radius:3px;padding:0 14px;}}"
                            f"QPushButton:disabled{{color:{c.get('text_dim', '#5A6380')};}}")
        fila.addStretch(1)
        fila.addWidget(self.btn_otra)
        fila.addWidget(self.btn_cerrar)
        raiz.addLayout(fila)

    # ── Hilo ──────────────────────────────────────────────────────────────────
    def corriendo(self) -> bool:
        h = self._hilo
        try:
            return h is not None and h.isRunning()
        except RuntimeError:
            return False

    def iniciar(self) -> bool:
        if self.corriendo():
            return False
        self._limpiar()
        self.btn_otra.setEnabled(False)
        self.lbl_estado.setText("Comprobando… (lo de la red puede tardar unos segundos)")
        self.parar()                                 # uno anterior que ya acabó
        self._hilo = self._fabrica(self.red, None)
        self._caja["h"] = self._hilo
        self._hilo.evento.connect(self.recibir)
        self._hilo.start()
        return True

    def parar(self) -> None:
        h, self._hilo = self._hilo, None
        self._caja["h"] = None
        soltar(h)

    def closeEvent(self, ev):                        # noqa: N802 (Qt)
        self.parar()
        super().closeEvent(ev)

    # ── Pintar ────────────────────────────────────────────────────────────────
    def _limpiar(self) -> None:
        self.items, self.fin, self._seccion = [], None, None
        while self.lista.count() > 1:
            it = self.lista.takeAt(0)
            w = it.widget() if it is not None else None
            if w is not None:
                w.deleteLater()

    def _poner(self, w: QWidget) -> None:
        self.lista.insertWidget(self.lista.count() - 1, w)

    def recibir(self, payload: str) -> None:
        """Un evento del hilo (JSON): inicio, item o fin."""
        try:
            e = json.loads(payload)
        except (TypeError, ValueError):
            return
        if not isinstance(e, dict):
            return
        c = self._c
        tipo = e.get("tipo")
        if tipo == "item":
            self.items.append(e)
            if e.get("seccion") != self._seccion:
                self._seccion = e.get("seccion")
                t = QLabel(str(e.get("seccion_nombre") or self._seccion or "").upper())
                t.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                t.setStyleSheet(f"color:{c.get('accent', '#00E5FF')};padding-top:8px;")
                self._poner(t)
            ok = e.get("ok")
            color = c.get("success", "#5BE49B") if ok is True else (
                c.get("error", "#FF5370") if ok is False else c.get("text_dim", "#5A6380"))
            detalle = str(e.get("detalle") or "")
            fila = QLabel(f"<b style='color:{color}'>{MARCAS.get(ok, 'NO APLICA')}</b>&nbsp;&nbsp;"
                          f"{_html(e.get('nombre'))}"
                          + (f"<br><span style='color:{c.get('text_muted', '#9AA4C0')}'>{_html(detalle)}</span>"
                             if detalle else ""))
            fila.setWordWrap(True)
            fila.setTextFormat(Qt.TextFormat.RichText)
            fila.setStyleSheet(f"color:{c.get('text', '#E6EAF5')};")
            self._poner(fila)
        elif tipo == "fin":
            self.fin = e
            self.btn_otra.setEnabled(True)
            ok = e.get("ok")
            self.lbl_estado.setText(str(e.get("resumen") or ""))
            self.lbl_estado.setStyleSheet(
                f"color:{c.get('success', '#5BE49B') if ok else c.get('warning', '#FFB547')};")


def _html(texto: Any) -> str:
    return (str(texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


__all__ = ("PruebaWorker", "DiagnosticoWorker", "DialogoDiagnostico", "soltar", "MARCAS")
