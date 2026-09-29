"""
ui/puente_tareas.py — objeto `tareas` del QWebChannel (window.luneTareas), Lune CD 10.9.

Lo usa la piel web (ui_web/ui_kits/lune-desktop/extra/tareas.jsx: la vista «tareas», estilo
Microsoft To Do, y la entrada «Tareas» de la barra lateral) para ver y tocar las tareas que
Lune guarda en memoria.json (nucleo/tareas.Tareas sobre la MISMA memoria del puente web:
`VentanaWeb.bridge.memoria`; nunca otra instancia, que reescribiría el archivo entero).

Se registra en `VentanaWeb.__init__` ANTES de `setUrl` (el JS solo ve lo registrado al crear
su QWebChannel). Con una memoria que no sirve (un doble de test, la MemoriaRemota de un
terminal sin respaldo), el objeto está igual y dice `disponible: false`.

Ranuras (JS: el resultado llega por callback, `luneTareas.x(args…, cb)`), todas devuelven JSON:
    estado() → str               {disponible, mi_dia: {fecha, fecha_larga, pendientes, hechas},
                                  sugerencias: {ayer, recientes, antes}, contador: {hoy, total}}
                                  tarea = {id, texto, lista, creada, hecha, hecha_en, en_mi_dia}
    agregar(texto) → str         {ok, error, tarea, estado}   a Mi día de hoy (≤ 200 caracteres)
    completar(id, hecha) → str   {ok, error, tarea, estado}
    al_mi_dia(id, si) → str      {ok, error, tarea, estado}
    quitar(id) → str             {ok, error, estado}
Señal:
    cambio(str)   JSON de estado(): la memoria cambió (Lune anotó algo desde el chat, otra ventana
                  o patata escribieron memoria.json, o cambió el día).

Hilos y objetos borrados: la memoria avisa (MemoriaManager.al_cambiar) desde el hilo que la
cambió (el chat, el hub, Telegram…). El oyente es un `PuenteHilo` (ui/escritorio.py): resuelve
la señal interna en cada llamada, mira sip.isdeleted y atrapa RuntimeError/AttributeError; la
señal interna va SIEMPRE en cola al hilo de Qt (también desde él: el PuenteHilo emite con su
candado cogido y armar el estado vuelve a leer la memoria, que puede volver a avisar) y allí se
arma el estado y sale `cambio` (en los tests: processEvents). `cerrar()` (en `_liberar_todo`) y
la destrucción del objeto dan de baja al oyente. El sondeo (memoria.json tocado por otro
proceso, cambio de día) es un QTimer hijo del puente: muere con él.

    puente = registrar_puente_tareas(canal, memoria)
    puente.cerrar()                  # en _liberar_todo
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from nucleo import tareas as nt
from ui.escritorio import PuenteHilo
from ui.puentes_ocio import dump, id_valido

_log = logging.getLogger("lune.puente_tareas")

MAX_ENTRADA = 4000             # caracteres que se aceptan de la página (luego se recorta a 200)
SONDEO_MS = 4000               # memoria.json tocado por otro proceso (patata) y cambio de día


def resolver_memoria(memoria: Any) -> Any:
    """La MemoriaManager con la que trabajar: la misma que se da o, si es una MemoriaRemota
    (terminal de la red), su respaldo local. None si ninguna sirve."""
    if memoria is not None and nt.disponible(memoria):
        return memoria
    respaldo = getattr(memoria, "respaldo", None) if memoria is not None else None
    if respaldo is not None and nt.disponible(respaldo):
        return respaldo
    return None


class _Baja:
    """Da de baja al oyente `fn` de la memoria. Se conecta a `destroyed` del puente (objeto
    Python normal: PyQt lo guarda, no hay lambda que muera con nadie)."""

    def __init__(self, memoria: Any, fn: Callable):
        self._memoria, self._fn = memoria, fn

    def __call__(self, *_args: Any) -> None:
        m, self._memoria = self._memoria, None
        quitar = getattr(m, "quitar_oyente", None) if m is not None else None
        if callable(quitar):
            try:
                quitar(self._fn)
            except Exception:
                pass


def _vacio(hoy: Optional[date] = None) -> Dict[str, Any]:
    hoy = hoy or date.today()
    return {
        "disponible": False,
        "mi_dia": {"fecha": hoy.isoformat(), "fecha_larga": nt.fecha_larga(hoy), "pendientes": [], "hechas": []},
        "sugerencias": {"ayer": [], "recientes": [], "antes": []},
        "contador": {"hoy": 0, "total": 0},
    }


class PuenteTareas(QObject):
    NOMBRE = "tareas"
    cambio = pyqtSignal(str)
    _aviso = pyqtSignal(str)               # interna: la memoria cambió (desde cualquier hilo)

    def __init__(self, memoria: Any = None, parent: Optional[QObject] = None, *,
                 ahora: Optional[Callable[[], datetime]] = None, sondeo_ms: int = SONDEO_MS):
        super().__init__(parent)
        self._canal: Any = None
        self._cerrado = False
        self._memoria = resolver_memoria(memoria)
        self._ahora = ahora or datetime.now
        self.tareas: Optional[nt.Tareas] = nt.Tareas(self._memoria, ahora=self._ahora) if self._memoria is not None else None
        self._dia = self._hoy()
        # SIEMPRE en cola (también desde el hilo de Qt): el oyente de la memoria (PuenteHilo) emite
        # con su candado cogido y _on_aviso vuelve a leer la memoria, que puede avisar otra vez.
        self._aviso.connect(self._on_aviso, Qt.ConnectionType.QueuedConnection)
        self._oyente = PuenteHilo(self, "_aviso")
        self._baja: Optional[_Baja] = None
        if self.tareas is not None:
            al_cambiar = getattr(self._memoria, "al_cambiar", None)
            if callable(al_cambiar):
                try:
                    al_cambiar(self._oyente)
                    self._baja = _Baja(self._memoria, self._oyente)
                    self.destroyed.connect(self._baja)
                except Exception:
                    _log.exception("tareas: no pude escuchar los cambios de la memoria")
        self._timer = QTimer(self)
        self._timer.setInterval(max(250, int(sondeo_ms or 0)) if sondeo_ms else 0)
        self._timer.timeout.connect(self._sondear)
        if self.tareas is not None and sondeo_ms:
            self._timer.start()

    # ── Utilidades ─────────────────────────────────────────────────────────────
    @property
    def disponible(self) -> bool:
        return self.tareas is not None and not self._cerrado

    def _hoy(self) -> date:
        try:
            return self._ahora().date()
        except Exception:
            return date.today()

    def _estado(self) -> Dict[str, Any]:
        if not self.disponible:
            return _vacio(self._hoy())
        try:
            e = self.tareas.estado()
        except Exception as ex:
            _log.exception("tareas: no pude leer las tareas")
            e = _vacio(self._hoy())
            e["error"] = f"No pude leer las tareas: {ex}"
            return e
        return {"disponible": True, **e}

    def _respuesta(self, ok: bool, error: str = "", tarea: Optional[dict] = None) -> str:
        r: Dict[str, Any] = {"ok": bool(ok), "error": error, "estado": self._estado()}
        if tarea is not None:
            r["tarea"] = tarea
        return dump(r)

    def _id_ok(self, rid: Any) -> bool:
        return id_valido(rid)

    # ── Señales ────────────────────────────────────────────────────────────────
    def _on_aviso(self, _motivo: str = "") -> None:
        if self._cerrado:
            return
        self._dia = self._hoy()
        self.cambio.emit(dump(self._estado()))

    def _sondear(self) -> None:
        """Otro proceso (patata) escribió memoria.json → la memoria se recarga y avisa (sale
        `cambio` por el oyente). Si cambió el día, Mi día es otro: también sale `cambio`."""
        if not self.disponible:
            return
        try:
            self.tareas.sincronizar()
        except Exception:
            pass
        if self._hoy() != self._dia:
            self._on_aviso("dia")

    # ── Ranuras ────────────────────────────────────────────────────────────────
    @pyqtSlot(result=str)
    def estado(self) -> str:
        return dump(self._estado())

    @pyqtSlot(str, result=str)
    def agregar(self, texto: str) -> str:
        if not self.disponible:
            return self._respuesta(False, "Las tareas no están disponibles ahora.")
        if not isinstance(texto, str) or len(texto) > MAX_ENTRADA:
            return self._respuesta(False, "Eso no parece una tarea.")
        if not nt.limpiar_texto(texto):
            return self._respuesta(False, "Escribe la tarea primero.")
        try:
            t = self.tareas.agregar(texto, mi_dia=True)
        except Exception as ex:
            _log.exception("tareas: agregar")
            return self._respuesta(False, f"No pude anotarla: {ex}")
        return self._respuesta(True, "", t)

    @pyqtSlot(str, bool, result=str)
    def completar(self, rid: str, hecha: bool) -> str:
        return self._cambiar(rid, "completar", bool(hecha))

    @pyqtSlot(str, bool, result=str)
    def al_mi_dia(self, rid: str, si: bool) -> str:
        return self._cambiar(rid, "al_mi_dia", bool(si))

    def _cambiar(self, rid: Any, metodo: str, valor: bool) -> str:
        if not self.disponible:
            return self._respuesta(False, "Las tareas no están disponibles ahora.")
        if not self._id_ok(rid):
            return self._respuesta(False, "Esa tarea no existe.")
        try:
            t = getattr(self.tareas, metodo)(rid, valor)
        except KeyError:
            return self._respuesta(False, "Esa tarea ya no está (¿la borraste desde otro sitio?).")
        except Exception as ex:
            _log.exception("tareas: %s", metodo)
            return self._respuesta(False, f"No pude cambiarla: {ex}")
        return self._respuesta(True, "", t)

    @pyqtSlot(str, result=str)
    def quitar(self, rid: str) -> str:
        if not self.disponible:
            return self._respuesta(False, "Las tareas no están disponibles ahora.")
        if not self._id_ok(rid):
            return self._respuesta(False, "Esa tarea no existe.")
        try:
            ok = self.tareas.quitar(rid)
        except Exception as ex:
            _log.exception("tareas: quitar")
            return self._respuesta(False, f"No pude quitarla: {ex}")
        return self._respuesta(ok, "" if ok else "Esa tarea ya no está.")

    # ── Cierre ─────────────────────────────────────────────────────────────────
    def cerrar(self) -> None:
        """Deja de escuchar la memoria, para el sondeo y sale del canal. Idempotente."""
        if self._cerrado:
            return
        self._cerrado = True
        try:
            self._timer.stop()
        except (RuntimeError, AttributeError):
            pass
        self._oyente.cerrar()
        baja, self._baja = self._baja, None
        if baja is not None:
            baja()
        canal, self._canal = self._canal, None
        dereg = getattr(canal, "deregisterObject", None) if canal is not None else None
        if callable(dereg):
            try:
                dereg(self)
            except (TypeError, RuntimeError):
                pass


def registrar_puente_tareas(canal: Any, memoria: Any, **kw) -> PuenteTareas:
    """Crea `PuenteTareas` con `memoria` (la del puente web), lo registra en `canal` como
    «tareas» y lo devuelve. Antes de que la página cree su QWebChannel (antes de setUrl).
    Queda como hijo del canal. `kw` (tests): `ahora`, `sondeo_ms`."""
    padre = canal if isinstance(canal, QObject) else None
    puente = PuenteTareas(memoria, parent=padre, **{k: kw[k] for k in ("ahora", "sondeo_ms") if k in kw})
    reg = getattr(canal, "registerObject", None)
    if callable(reg):
        try:
            reg(PuenteTareas.NOMBRE, puente)
            puente._canal = canal
        except Exception:
            _log.exception("puente tareas: no pude registrar «tareas» en el canal")
    return puente


__all__ = ("PuenteTareas", "registrar_puente_tareas", "resolver_memoria", "SONDEO_MS")
