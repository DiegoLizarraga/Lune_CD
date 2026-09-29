"""
ui/acciones_qt.py — El Ejecutor de acciones del modelo (lune_core/acciones.py)
enchufado a Qt: hilos, aprobaciones que un humano VE y resultados.

Para qué sirve
--------------
El modelo pide acciones con `<|CALL ["herramienta", {args}]|>`. El Ejecutor
las valida y las pasa por la Política; lo que falta para usarlo en una app Qt
es siempre lo mismo, y aquí está una sola vez para la nativa (main.py) y la
piel web (ui/web_bridge.py):

  · Hilos. Lo que pasa tras una aprobación (o su caducidad a los 60 s, que llega
    en el hilo de un temporizador) se lleva al hilo de Qt con una señal. Los
    resultados salen SIEMPRE por la señal `resultado(ResultadoAccion)` en el
    hilo de Qt.
  · Aprobaciones visibles (crítica d). Con la ventana principal a la vista:
    `preguntar(pendiente, responder)` si quien lo usa pone su propia pregunta
    (el modal web), o un QMessageBox no bloqueante sobre la ventana. Si la
    ventana no está a la vista (bandeja, solo la mascota): `DialogoAprobacion`
    pequeño, siempre encima, junto a la mascota, con cuenta atrás. Sin
    respuesta en 60 s, rechazada; cerrar = No.
  · Conversación nueva: `nueva_conversacion()` repone el presupuesto y cierra
    las preguntas abiertas sin ejecutar nada.

Uso (nativa):

    self.acciones = AccionesQt(self.tools, ventana=self,
                               ancla=lambda: mascota.frameGeometry() if mascota else None)
    self.acciones.resultado.connect(self._on_resultado_accion)
    ...
    texto, llamadas = self.acciones.procesar(respuesta, worker.origen, ctx)
    self.acciones.ejecutar(llamadas, worker.origen, ctx)      # al terminar la respuesta

Uso (web): igual, con `preguntar=` que emite `aprobacion_pedida(json)` y
`cerrar_pregunta=` que avisa a la página; el slot `resolver_aprobacion(id, ok)`
llama a `self.acciones.resolver(id, ok)`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from lune_core.acciones import (AVISO_CONTAMINADO, AVISO_LLAMADA, AVISO_OFRECIDA, AVISO_REMOTO,
                                NO_CONFIABLE, REMOTO, USUARIO, Llamada, ResultadoAccion,
                                limpiar_texto)

_log = logging.getLogger(__name__)

TITULO_PREGUNTA = "Lune pide permiso"
# Delante de la pregunta cuando la orden llegó desde Telegram (origen 'remoto').
PREFIJO_REMOTO = "Pedido desde Telegram"
# Delante de la pregunta cuando se oyó en el modo llamada (pendiente["llamada"]).
PREFIJO_LLAMADA = "Lo oí en la llamada"


def _prefijo(pendiente: dict) -> str:
    """De dónde vino lo que se pregunta, para ponerlo delante ("" si de ti, aquí)."""
    if es_remota(pendiente):
        return PREFIJO_REMOTO
    return PREFIJO_LLAMADA if pendiente.get("llamada") else ""


def es_remota(pendiente: dict) -> bool:
    """¿La pregunta es de una orden que llegó desde Telegram?"""
    return bool(pendiente.get("remoto")) or str(pendiente.get("origen") or "") == REMOTO


def texto_pregunta(pendiente: dict) -> str:
    """Texto plano de la pregunta (herramienta, resumen, argumentos y plazo)."""
    from ui.aprobacion_qt import formatear_args, limpiar
    herramienta = pendiente.get("herramienta") or "herramienta"
    resumen = limpiar(pendiente.get("resumen") or pendiente.get("descripcion") or herramienta, 300)
    try:
        segundos = int(float(pendiente.get("timeout") or 60))
    except (TypeError, ValueError):
        segundos = 60
    remota = es_remota(pendiente)
    prefijo = _prefijo(pendiente)
    partes = [f"{prefijo}: {resumen}" if prefijo else f"{resumen}",
              f"Herramienta: {limpiar(herramienta, 60)}"]
    args = formatear_args(pendiente.get("args"))
    if args:
        partes.append(args)
    if remota:
        partes.append("Ojo: " + AVISO_REMOTO)
    elif pendiente.get("origen") and pendiente.get("origen") != USUARIO:
        partes.append("Ojo: la petición salió de un texto externo, no de ti.")
    if pendiente.get("llamada"):
        partes.append("Ojo: " + AVISO_LLAMADA)
    if pendiente.get("contaminado"):
        partes.append("Ojo: " + AVISO_CONTAMINADO)
    if pendiente.get("ofrecida"):
        partes.append("Ojo: " + AVISO_OFRECIDA)
    partes.append(f"¿Lo hago? Si no contestas en {segundos} s, no lo hago.")
    return "\n\n".join(partes)


class AccionesQt(QObject):
    """Ejecutor + aprobaciones visibles + resultados en el hilo de Qt."""

    # ResultadoAccion de cada llamada (hecha, rechazada, caducada, error…), en el hilo de Qt.
    resultado = pyqtSignal(object)
    _en_qt = pyqtSignal(object)

    def __init__(self, tools: Any, *, ventana: Optional[QWidget] = None,
                 ventana_visible: Optional[Callable[[], bool]] = None,
                 ancla: Optional[Callable[[], Any]] = None,
                 preguntar: Optional[Callable[[dict, Callable[[bool], None]], None]] = None,
                 cerrar_pregunta: Optional[Callable[[str], None]] = None,
                 opciones_dialogo: Optional[dict] = None,
                 parent: Optional[QObject] = None, **opciones_ejecutor):
        """
        tools              servicios.tools.ToolManager (con `crear_ejecutor`).
        ventana            ventana principal: padre del QMessageBox y, si no se da
                           `ventana_visible`, la que decide si está «a la vista».
        ventana_visible()  ¿la ventana principal se ve? (por defecto: visible y no
                           minimizada).
        ancla()            rectángulo global de la mascota (o None) para colocar el
                           DialogoAprobacion cuando la ventana no se ve.
        preguntar(p, r)    pregunta propia con la ventana a la vista (modal web).
        cerrar_pregunta(id) cierra esa pregunta propia (caducó o se canceló).
        opciones_ejecutor  van a `tools.crear_ejecutor` (audit_path, programar, reloj…).
        """
        super().__init__(parent)
        self.ventana = ventana
        self._ventana_visible = ventana_visible
        self._ancla = ancla
        self._preguntar_fuera = preguntar
        self._cerrar_fuera = cerrar_pregunta
        self._opciones_dialogo = dict(opciones_dialogo or {})
        self.abiertas: Dict[str, Any] = {}      # id → QMessageBox | DialogoAprobacion | "fuera"
        self._en_qt.connect(self._correr)
        self.ejecutor = tools.crear_ejecutor(self._pedir_aprobacion, despachar=self._en_qt.emit,
                                             cerrar_aprobacion=self._cerrar_aprobacion,
                                             **opciones_ejecutor)

    # ── Texto y ejecución ──────────────────────────────────────────────────────
    def procesar(self, texto: str, origen: str = USUARIO, ctx: Any = None):
        """(texto_limpio, llamadas). Nunca lanza: si algo falla, texto limpio y nada que hacer."""
        try:
            return self.ejecutor.procesar(texto or "", origen, ctx)
        except Exception:
            return limpiar_texto(texto or ""), []

    def ejecutar(self, llamadas: List[Llamada], origen: str = NO_CONFIABLE, ctx: Any = None) -> None:
        """Corre las llamadas (al terminar la respuesta). Resultados por `resultado`."""
        if llamadas:
            self.ejecutor.ejecutar_llamadas(llamadas, origen, ctx, self.resultado.emit)

    def resolver(self, pendiente_id: str, ok: Any) -> bool:
        """Respuesta que llega por id (p. ej. el modal web). False si ya no estaba.
        Si esa pregunta también estaba abierta aquí (caja o diálogo), se cierra."""
        pid = str(pendiente_id)
        hecho = self.ejecutor.resolver(pid, ok)
        abierta = self.abiertas.pop(pid, None)
        if abierta is not None and abierta != "fuera":
            self._cerrar_ui(pid, abierta)
        return hecho

    def pendientes(self) -> List[dict]:
        return self.ejecutor.pendientes()

    def disponibles(self, modo: Optional[str] = None) -> List[str]:
        return self.ejecutor.disponibles(modo)

    def nueva_conversacion(self) -> None:
        """Presupuesto repuesto; las preguntas abiertas se cierran sin ejecutar nada."""
        self.ejecutor.nueva_conversacion()
        # Lo que el Ejecutor no llegó a cerrar (p. ej. sin pregunta registrada).
        for pid in list(self.abiertas):
            self._cerrar_aprobacion(pid)

    def cerrar(self) -> None:
        """Al salir: nada pendiente."""
        try:
            self.nueva_conversacion()
        except Exception:
            _log.exception("acciones: no pude cerrar las aprobaciones")

    # ── Hilos ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _correr(fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            _log.exception("acciones: fallo en el hilo de Qt")

    # ── Aprobaciones ───────────────────────────────────────────────────────────
    def ventana_a_la_vista(self) -> bool:
        if self._ventana_visible is not None:
            try:
                return bool(self._ventana_visible())
            except Exception:
                return False
        v = self.ventana
        if v is None:
            return False
        try:
            return bool(v.isVisible() and not v.isMinimized())
        except Exception:
            return False

    def _pedir_aprobacion(self, pendiente: dict, responder: Callable[[bool], None]) -> None:
        # Puede llegar desde el hilo que siguió a una aprobación: siempre a Qt.
        self._en_qt.emit(lambda: self._preguntar(dict(pendiente), responder))

    def _preguntar(self, pendiente: dict, responder: Callable[[bool], None]) -> None:
        pid = str(pendiente.get("id") or "")
        try:
            if self.ventana_a_la_vista():
                if self._preguntar_fuera is not None:
                    self.abiertas[pid] = "fuera"
                    self._preguntar_fuera(dict(pendiente), responder)
                    return
                if self.ventana is not None:
                    self.abiertas[pid] = self._caja(pid, pendiente, responder)
                    return
            self.abiertas[pid] = self._dialogo(pid, pendiente, responder)
        except Exception as e:
            _log.exception("acciones: no pude enseñar la pregunta")
            self.abiertas.pop(pid, None)
            responder(False)
            self.resultado.emit(ResultadoAccion(
                False, f"No pude preguntarte por «{pendiente.get('herramienta', '?')}» ({e}).",
                str(pendiente.get("herramienta") or ""), "error", dict(pendiente.get("args") or {}), pid))

    def _caja(self, pid: str, pendiente: dict, responder: Callable[[bool], None]) -> QMessageBox:
        """QMessageBox NO bloqueante (open()): el bucle de Qt sigue y puede caducar."""
        caja = QMessageBox(self.ventana)
        caja.setIcon(QMessageBox.Icon.Question)
        caja.setWindowTitle(TITULO_PREGUNTA)
        caja.setTextFormat(Qt.TextFormat.PlainText)     # nada del modelo se interpreta como HTML
        caja.setText(texto_pregunta(pendiente))
        si, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
        caja.setStandardButtons(si | no)
        caja.setDefaultButton(no)                       # un Enter perdido no aprueba nada
        caja.setEscapeButton(no)
        caja.button(si).setText("Sí, hazlo")
        caja.button(no).setText("No")
        caja.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        caja.setProperty("lune_cerrada", False)

        def al_terminar(_codigo=None, c=caja):
            if c.property("lune_cerrada"):
                return                                  # la cerró el Ejecutor: no cuenta
            c.setProperty("lune_cerrada", True)
            self.abiertas.pop(pid, None)
            boton = c.clickedButton()
            responder(boton is not None and c.standardButton(boton) == si)

        caja.finished.connect(al_terminar)
        caja.open()
        return caja

    def _dialogo(self, pid: str, pendiente: dict, responder: Callable[[bool], None]):
        """DialogoAprobacion junto a la mascota (ventana principal oculta)."""
        from ui.aprobacion_qt import DialogoAprobacion
        try:
            segundos = int(float(pendiente.get("timeout") or 60))
        except (TypeError, ValueError):
            segundos = 60
        resumen = str(pendiente.get("resumen") or "")
        # El diálogo pequeño solo enseña el resumen: los avisos van delante y, antes,
        # de dónde vino (Telegram, la llamada). Pueden ir los dos (orden remota en una
        # conversación con contenido externo).
        if pendiente.get("contaminado"):
            resumen = "Ojo: la conversación contiene contenido externo. " + resumen
        prefijo = _prefijo(pendiente)
        if prefijo:
            resumen = f"{prefijo}: {resumen}"
        dlg = DialogoAprobacion(str(pendiente.get("herramienta") or ""),
                                resumen, pendiente.get("args"),
                                riesgo=str(pendiente.get("riesgo") or ""), segundos=segundos,
                                id_aprobacion=pid, **self._opciones_dialogo)

        def al_resolver(ok: bool):
            self.abiertas.pop(pid, None)
            responder(bool(ok))

        dlg.resuelto.connect(al_resolver)
        rect = None
        if self._ancla is not None:
            try:
                rect = self._ancla()
            except Exception:
                rect = None
        dlg.mostrar_junto_a(rect)
        return dlg

    def _cerrar_aprobacion(self, pid: str) -> None:
        """El Ejecutor la dio por cerrada (caducó o conversación nueva): fuera sin contestar."""
        pid = str(pid)
        abierta = self.abiertas.pop(pid, None)
        if abierta is not None:
            self._cerrar_ui(pid, abierta)

    def _cerrar_ui(self, pid: str, abierta: Any) -> None:
        try:
            if abierta == "fuera":
                if self._cerrar_fuera is not None:
                    self._cerrar_fuera(pid)
            elif isinstance(abierta, QMessageBox):
                abierta.setProperty("lune_cerrada", True)
                abierta.done(int(QMessageBox.StandardButton.No.value))
            else:
                abierta.descartar()
        except RuntimeError:
            pass                                        # ya destruida por Qt
        except Exception:
            _log.exception("acciones: no pude cerrar la pregunta %s", pid)
